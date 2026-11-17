"""Thực thi tiến trình con cho bộ chạy việc (§4.1, §4.6, §4.7, §6.1).

- `tu_gan_job_object`: gắn chính runner vào Job Object KILL_ON_JOB_CLOSE → runner chết thì cả cây chết.
- `gianh_don_instance`: named mutex + msvcrt.locking trên runner.lock.
- `env_toi_thieu`: môi trường tối thiểu, không kế thừa toàn bộ os.environ.
- `chay_tien_trinh`: Popen dạng list (không shell), console ẩn dùng chung, đọc stdout UTF-8 từng
  dòng ở luồng riêng (vòng chính không bao giờ chặn trên pipe), quá giờ / huỷ / vượt trần lượt
  → giết cả cây. Dọn tiến trình, Job Object, handle, file luôn chạy trong `finally`; lỗi dọn
  được ghi log và ném ra, không nuốt.
- `giet_cay`, `ffmpeg_ngoai`, `bo_che` (che bí mật theo giá trị + mẫu).

Mọi chỗ đọc tên trường stream-json nằm ở `stream_json.py`.
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
from collections import deque
from ctypes import wintypes
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import psutil

from . import stream_json as sj

log = logging.getLogger("kho_runner.thuc_thi")

TEN_MUTEX = "Local\\kho-runner"
ERROR_ALREADY_EXISTS = 183

BIEN_MOI_TRUONG_CHEP = (
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "USERPROFILE", "USERNAME",
    "USERDOMAIN", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES",
    "PROGRAMFILES(X86)", "TEMP", "TMP", "COMPUTERNAME", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
)

CHO_GIET_S = 10          # §4.6: kill rồi chờ 10 s trước khi taskkill dự phòng
CHO_SAU_GIET_S = 30      # R-06 P3-5: đã giết (huỷ/quá giờ/vượt lượt) mà gốc vẫn sống quá mức này → bỏ chờ, báo cờ
CHO_DON_S = 30           # chờ tiến trình thoát sau khi giết (đường thường + đường dọn sau ngoại lệ)
CHO_EOF_S = 5            # tiến trình gốc đã thoát mà pipe chưa EOF → coi là con cháu giữ pipe
CHU_KY_CHUP_CON_S = 1.0  # chụp danh sách con cháu (lưới dự phòng khi không có Job Object riêng)
DUOI_GIU_DONG = 200      # số dòng cuối giữ lại cho van_ban_cuoi của script thường
TOI_DA_VAN_BAN_CUOI = 8000

SW_HIDE = 0
SW_SHOWMINNOACTIVE = 7

# ---------------------------------------------------------------- Win32 qua ctypes

_WIN = sys.platform == "win32"
if _WIN:
    import msvcrt

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION), ("IoInfo", _IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    _JobObjectExtendedLimitInformation = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

    _k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    _k32.SetInformationJobObject.restype = wintypes.BOOL
    _k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _k32.AssignProcessToJobObject.restype = wintypes.BOOL
    _k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _k32.TerminateJobObject.restype = wintypes.BOOL
    _k32.GetCurrentProcess.argtypes = []
    _k32.GetCurrentProcess.restype = wintypes.HANDLE
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.CloseHandle.restype = wintypes.BOOL
    _k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.CreateMutexW.restype = wintypes.HANDLE
    _k32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    _k32.ReleaseMutex.restype = wintypes.BOOL


def _loi_win(ham: str) -> OSError:
    ma = ctypes.get_last_error()
    return OSError(ma, f"{ham} thất bại (WinError {ma}): {ctypes.FormatError(ma).strip()}")


def _dong_handle(h) -> None:
    if h and not _k32.CloseHandle(h):
        raise _loi_win("CloseHandle")


# ---------------------------------------------------------------- Job Object (§4.6)

_JOB_RUNNER = None   # handle giữ suốt đời tiến trình; KHÔNG đóng (đóng = giết cả cây)


def da_gan_job_object() -> bool:
    """True nếu runner đã nằm trong Job Object KILL_ON_JOB_CLOSE (R-06 P3-6: quyết định đối soát khởi động lại)."""
    return _JOB_RUNNER is not None


def tu_gan_job_object() -> bool:
    """Gắn tiến trình hiện tại vào Job Object KILL_ON_JOB_CLOSE. True nếu đã gắn (hoặc đã gắn từ trước)."""
    global _JOB_RUNNER
    if _JOB_RUNNER is not None:
        return True
    if not _WIN:
        log.warning("Không gắn được Job Object — không phải Windows")
        return False
    job = _k32.CreateJobObjectW(None, None)
    if not job:
        log.error("Không gắn được Job Object — tiến trình con có thể mồ côi khi runner chết: %s",
                  _loi_win("CreateJobObjectW"))
        return False
    try:
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not _k32.SetInformationJobObject(job, _JobObjectExtendedLimitInformation,
                                            ctypes.byref(info), ctypes.sizeof(info)):
            raise _loi_win("SetInformationJobObject")
        if not _k32.AssignProcessToJobObject(job, _k32.GetCurrentProcess()):
            raise _loi_win("AssignProcessToJobObject")
    except OSError as e:
        log.error("Không gắn được Job Object — tiến trình con có thể mồ côi khi runner chết: %s", e)
        try:
            _dong_handle(job)
        except OSError as e2:
            log.error("Không đóng được handle Job Object hỏng: %s", e2)
        return False
    _JOB_RUNNER = job
    return True


def _tao_job_rieng(proc: subprocess.Popen):
    """Job Object riêng cho một lần chạy (không KILL_ON_JOB_CLOSE) để giết được cả con cháu mồ côi.
    Trả handle hoặc None (đã ghi log) — khi đó dựa vào lưới psutil."""
    if not _WIN:
        return None
    job = _k32.CreateJobObjectW(None, None)
    if not job:
        log.warning("Không tạo được Job Object riêng cho pid %s: %s", proc.pid, _loi_win("CreateJobObjectW"))
        return None
    if not _k32.AssignProcessToJobObject(job, int(proc._handle)):
        log.warning("Không gắn được pid %s vào Job Object riêng: %s", proc.pid, _loi_win("AssignProcessToJobObject"))
        try:
            _dong_handle(job)
        except OSError as e:
            log.error("Không đóng được handle Job Object riêng: %s", e)
        return None
    return job


# ---------------------------------------------------------------- Đơn instance (§4.1)

class KhoaDonInstance:
    """Giữ mutex + khoá runner.lock. Gọi `nha()` từ CHÍNH luồng đã giành (ReleaseMutex đòi vậy)."""

    def __init__(self, mutex, fd: int, duong_dan: Path):
        self.mutex = mutex
        self.fd = fd
        self.duong_dan = duong_dan

    def nha(self) -> None:
        """Nhả cả hai khoá. Mọi bước đều chạy; lỗi được ghi log và ném lỗi đầu tiên ra."""
        loi: list[BaseException] = []
        if self.fd is not None:
            try:
                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            except OSError as e:
                log.error("Không mở khoá được %s: %s", self.duong_dan, e)
                loi.append(e)
            try:
                os.close(self.fd)
            except OSError as e:
                log.error("Không đóng được %s: %s", self.duong_dan, e)
                loi.append(e)
            self.fd = None
        if self.mutex:
            if not _k32.ReleaseMutex(self.mutex):
                e = _loi_win("ReleaseMutex")
                log.error("%s", e)
                loi.append(e)
            try:
                _dong_handle(self.mutex)
            except OSError as e:
                log.error("%s", e)
                loi.append(e)
            self.mutex = None
        if loi:
            raise loi[0]


def gianh_don_instance(thu_muc: Path, ten_mutex: str = TEN_MUTEX) -> object | None:
    """Mutex `Local\\kho-runner` + msvcrt.locking `runner.lock`. None nếu đã có instance khác.
    `ten_mutex` chỉ để test đổi tên (tránh đụng runner thật); runner luôn dùng mặc định."""
    mutex = _k32.CreateMutexW(None, True, ten_mutex)
    ma = ctypes.get_last_error()
    if not mutex:
        raise _loi_win("CreateMutexW")
    if ma == ERROR_ALREADY_EXISTS:
        _dong_handle(mutex)   # không sở hữu (đã có chủ) → chỉ đóng handle
        return None

    def _tra_mutex():
        if not _k32.ReleaseMutex(mutex):
            log.error("%s", _loi_win("ReleaseMutex"))
        try:
            _dong_handle(mutex)
        except OSError as e:
            log.error("%s", e)

    duong_dan = Path(thu_muc) / "runner.lock"
    try:
        Path(thu_muc).mkdir(parents=True, exist_ok=True)
        fd = os.open(duong_dan, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0))
    except OSError:
        _tra_mutex()
        raise
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError:
        # lưới thứ hai: instance ở session khác đang giữ runner.lock
        try:
            os.close(fd)
        except OSError as e:
            log.error("Không đóng được %s: %s", duong_dan, e)
        _tra_mutex()
        return None
    return KhoaDonInstance(mutex, fd, duong_dan)


# ---------------------------------------------------------------- Môi trường tối thiểu (§4.7)

def env_toi_thieu(them: dict[str, str]) -> dict[str, str]:
    """Chỉ chép các biến hệ thống cần thiết + PYTHONUTF8/PYTHONIOENCODING, rồi cộng `them`."""
    env = {}
    for k in BIEN_MOI_TRUONG_CHEP:
        v = os.environ.get(k)
        if v is not None:
            env[k] = v
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(them)
    return env


# ---------------------------------------------------------------- Giết cây

def giet_cay(pid: int, tao_luc: float | None) -> bool:
    """Giết tiến trình `pid` và mọi con cháu (§4.6).

    `tao_luc` khác None mà lệch create_time quá 1 s → PID đã bị tái dùng, KHÔNG đụng, trả False.
    True = cây không còn sống (đã giết, hoặc vốn đã chết). False = không đụng hoặc vẫn còn sống
    sau cả `taskkill /T /F` (đã ghi log)."""
    try:
        goc = psutil.Process(pid)
        if tao_luc is not None and abs(goc.create_time() - tao_luc) > 1.0:
            log.warning("pid %s đã bị tái dùng (create_time lệch) — không giết", pid)
            return False
        cay = goc.children(recursive=True)
    except psutil.NoSuchProcess:
        return True
    except psutil.Error as e:
        log.error("Không đọc được cây tiến trình pid %s: %s", pid, e)
        cay, goc = [], None

    ds = ([goc] if goc else []) + cay
    for p in ds:   # gốc trước để nó không sinh thêm con
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
        except psutil.Error as e:
            log.error("kill pid %s lỗi: %s", p.pid, e)
    # con sinh ra giữa lúc chụp và lúc giết gốc
    for p in cay:
        try:
            for c in p.children(recursive=True):
                if c not in ds:
                    ds.append(c)
                    c.kill()
        except psutil.Error:
            pass
    _, con_song = psutil.wait_procs(ds, timeout=CHO_GIET_S)
    if not con_song:
        return True

    for p in con_song:
        lenh = ["taskkill", "/T", "/F", "/PID", str(p.pid)]
        try:
            r = subprocess.run(lenh, capture_output=True, timeout=30,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode != 0:
                log.error("taskkill pid %s mã %s: %s", p.pid, r.returncode,
                          (r.stderr or r.stdout).decode("utf-8", "replace")[:500])
        except (OSError, subprocess.TimeoutExpired) as e:
            log.error("taskkill pid %s lỗi: %s", p.pid, e)
    _, con_song = psutil.wait_procs(con_song, timeout=5)
    if con_song:
        log.error("Vẫn còn sống sau taskkill: %s", [p.pid for p in con_song])
        return False
    return True


# ---------------------------------------------------------------- ffmpeg ngoài cây runner (§4.4)

def _co_ffmpeg_ngoai(ds: list[tuple[int, list[int] | None]], pid_goc: set[int]) -> bool:
    """ds: (pid ffmpeg, danh sách pid tổ tiên hoặc None nếu không đọc được). Logic thuần."""
    for pid, to_tien in ds:
        if pid in pid_goc:
            continue
        if to_tien is None or not (set(to_tien) & pid_goc):
            return True
    return False


def ffmpeg_ngoai(pid_goc_cua_runner: set[int]) -> bool:
    """True nếu có ffmpeg.exe chạy NGOÀI cây tiến trình có gốc trong `pid_goc_cua_runner`.
    Không đọc được tổ tiên → coi là ngoài (an toàn cho GPU)."""
    ds = []
    for p in psutil.process_iter(["pid", "name"]):
        ten = (p.info.get("name") or "").lower()
        if ten not in ("ffmpeg.exe", "ffmpeg"):
            continue
        try:
            to_tien = [a.pid for a in p.parents()]
        except psutil.NoSuchProcess:
            continue
        except psutil.Error:
            to_tien = None
        ds.append((p.info["pid"], to_tien))
    return _co_ffmpeg_ngoai(ds, set(pid_goc_cua_runner))


# ---------------------------------------------------------------- Che bí mật (§4.7)

@dataclass
class NguonBiMat:
    settings_json: Path
    file_khoa: list[Path]
    cau_hinh_radar: Path
    ten_bien_moi_truong: list[str]


MAU_BI_MAT = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?:ghp_|github_pat_)[A-Za-z0-9_]{10,}"),
    re.compile(r"\d{8,10}:[A-Za-z0-9_-]{30,}"),
)
_KHOA_RADAR = re.compile(r"(?i)token|key|secret|pass")
DO_DAI_TOI_THIEU = 12
CACHE_CHE_S = 60


def _mtime(p: Path):
    try:
        return p.stat().st_mtime_ns
    except FileNotFoundError:
        return None
    except OSError as e:
        return ("loi", str(e))


def _doc_json(p: Path, ten: str):
    """(ok, dữ liệu). File không tồn tại → (True, None). Lỗi khác → ghi log, (False, None)."""
    try:
        return True, json.loads(p.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return True, None
    except (OSError, ValueError) as e:
        log.warning("Không đọc được %s (%s) để lấy giá trị cần che — giữ giá trị cũ: %s", ten, p, e)
        return False, None


def _gia_tri_settings(p: Path):
    ok, d = _doc_json(p, "settings.json")
    if not ok:
        return None
    env = d.get("env") if isinstance(d, dict) else None
    return [v for v in env.values() if isinstance(v, str)] if isinstance(env, dict) else []


def _gia_tri_radar(p: Path):
    ok, d = _doc_json(p, "cấu hình radar")
    if not ok:
        return None
    ra: list[str] = []

    def di(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(v, str) and isinstance(k, str) and _KHOA_RADAR.search(k):
                    ra.append(v)
                else:
                    di(v)
        elif isinstance(x, list):
            for v in x:
                di(v)
    di(d)
    return ra


def _gia_tri_file_khoa(p: Path):
    try:
        return [p.read_text(encoding="utf-8-sig").strip()]
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as e:
        log.warning("Không đọc được file khoá %s để che — giữ giá trị cũ: %s", p, e)
        return None


def bo_che(nguon: NguonBiMat) -> Callable[[str], str]:
    """Hàm che bí mật: theo GIÁ TRỊ (≥12 ký tự, dựng lại khi mtime nguồn đổi hoặc sau 60 s) rồi theo MẪU.
    Nguồn đọc lỗi → ghi log, giữ giá trị cũ của nguồn đó (không mất che vì file tạm hỏng)."""
    khoa_lock = threading.Lock()
    trang = {"chu_ky": object(), "luc": float("-inf"), "theo_nguon": {}, "gia_tri": []}

    def nguon_doc():
        yield ("settings", nguon.settings_json, lambda: _gia_tri_settings(nguon.settings_json))
        for i, p in enumerate(nguon.file_khoa):
            yield (f"khoa{i}", p, lambda p=p: _gia_tri_file_khoa(p))
        yield ("radar", nguon.cau_hinh_radar, lambda: _gia_tri_radar(nguon.cau_hinh_radar))

    def chu_ky():
        return (tuple(_mtime(Path(p)) for _, p, _ in nguon_doc()),
                tuple(os.environ.get(t) for t in nguon.ten_bien_moi_truong))

    def dung_lai():
        theo = trang["theo_nguon"]
        for ten, _, doc in nguon_doc():
            v = doc()
            if v is not None:
                theo[ten] = v
        theo["env"] = [os.environ[t] for t in nguon.ten_bien_moi_truong if os.environ.get(t)]
        tap = set()
        for ds in theo.values():
            for v in ds:
                if len(v) >= DO_DAI_TOI_THIEU:
                    tap.add(v)
                    thoat = json.dumps(v)[1:-1]          # dạng đã escape trong dòng JSON thô
                    if thoat != v and len(thoat) >= DO_DAI_TOI_THIEU:
                        tap.add(thoat)
        trang["gia_tri"] = sorted(tap, key=len, reverse=True)

    def che(s: str) -> str:
        with khoa_lock:
            ck = chu_ky()
            bay_gio = time.monotonic()
            if ck != trang["chu_ky"] or bay_gio - trang["luc"] >= CACHE_CHE_S:
                dung_lai()
                trang["chu_ky"] = ck
                trang["luc"] = bay_gio
            gia_tri = trang["gia_tri"]
        for v in gia_tri:
            if v in s:
                s = s.replace(v, "***")
        for m in MAU_BI_MAT:
            s = m.sub("***", s)
        return s

    return che


# ---------------------------------------------------------------- Chạy tiến trình

@dataclass
class KetQuaTienTrinh:
    ma_thoat: int | None
    het_gio: bool
    bi_huy: bool
    vuot_luot: bool
    ket_qua: dict | None          # stream_json.la_ket_qua(...)
    van_ban_cuoi: str
    session_id: str | None
    so_luot: int
    cong_cu_da_goi: list[str] = field(default_factory=list)
    khong_giet_duoc: bool = False  # R-06 P3-5: đã giết mà gốc vẫn sống sau CHO_SAU_GIET_S → bỏ chờ (kiểm tay)
    pid: int | None = None
    pid_tao_luc: float | None = None   # FX-5: để bên gọi kiểm định kỳ pid gốc đã chết chưa (chống PID tái dùng)


THUOC_TINH_KHONG_GIET = "kho_runner_khong_giet"   # gắn lên ngoại lệ: (pid, pid_tao_luc) của gốc chưa giết được


def khong_giet_tu_loi(e: BaseException) -> tuple[int, float | None] | None:
    """R-07 P3-1: ngoại lệ ném ra từ chay_tien_trinh mà tiến trình gốc vẫn còn sống sau khi giết + chờ → (pid,
    pid_tao_luc); ngược lại None."""
    v = getattr(e, THUOC_TINH_KHONG_GIET, None)
    return v if isinstance(v, tuple) and len(v) == 2 else None


def _gio() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _cach_mo(hien_cua_so: bool):
    """§6.1: console ẩn dùng chung (CREATE_NEW_CONSOLE + SW_HIDE), không dùng CREATE_NO_WINDOW."""
    if not _WIN:
        return 0, None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = SW_SHOWMINNOACTIVE if hien_cua_so else SW_HIDE
    return subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP, si


def _luong_doc(stream, nguon: str, q: queue.Queue) -> None:
    try:
        for b in iter(stream.readline, b""):
            q.put((nguon, b.decode("utf-8", "replace").rstrip("\r\n")))
    except (OSError, ValueError) as e:
        q.put(("runner", f"lỗi đọc {nguon}: {e}"))
    finally:
        q.put((nguon, None))   # EOF


def _luong_ghi_stdin(proc: subprocess.Popen, du_lieu: bytes, q: queue.Queue) -> None:
    try:
        proc.stdin.write(du_lieu)
        proc.stdin.flush()
    except OSError as e:   # BrokenPipe: con thoát trước khi đọc hết
        q.put(("runner", f"ghi stdin lỗi: {e}"))
    finally:
        try:
            proc.stdin.close()
        except OSError as e:
            q.put(("runner", f"đóng stdin lỗi: {e}"))


def chay_tien_trinh(argv: list[str], cwd: str, stdin_text: str | None, env: dict[str, str],
                    file_log: Path, file_jsonl: Path | None, het_gio_s: int, la_claude: bool, hien_cua_so: bool,
                    tran_luot: int | None, khi_bat_dau: Callable[[int, float], None],
                    khi_co_session: Callable[[str], None], khi_doc_dong: Callable[[str], None],
                    huy: threading.Event, che: Callable[[str], str] | None = None) -> KetQuaTienTrinh:
    """Chạy một bước, chặn tới khi xong. Popen lỗi (vd không có file chạy) → ghi log rồi ném OSError.

    - `khi_doc_dong` nhận MỌI dòng thô đã giải mã (stdout và stderr), trước khi xử lý.
    - Claude: stdout thô → `file_jsonl`, bản người đọc (stream_json.dich_dong) và stderr → `file_log`.
    - Script: stdout+stderr gộp → `file_log`.
    - `so_luot`: số message assistant khác nhau (khử trùng theo message.id); > `tran_luot` → giết cây.
    - Callback ném lỗi → tiến trình bị giết cả cây, lỗi được ném lại. Giết + chờ CHO_DON_S mà gốc vẫn sống → lỗi
      ném ra mang (pid, pid_tao_luc) đọc bằng `khong_giet_tu_loi` (R-07 P3-1).
    - `che` (R-07 P2-2): che bí mật trên bản đầy đủ trước khi cắt dòng người đọc ghi vào `file_log`.
    """
    q: queue.Queue = queue.Queue()
    f_log = open(file_log, "a", encoding="utf-8", newline="\n")
    f_jsonl = None
    proc = None
    job = None
    tao_luc = None
    luong: list[threading.Thread] = []
    con_chau: dict[int, psutil.Process] = {}
    loi_chinh: BaseException | None = None
    khong_giet_duoc = False

    def ghi_log(s: str) -> None:
        f_log.write(s + "\n")
        f_log.flush()

    def giet_het(ly_do: str) -> None:
        """Giết job riêng (bắt cả mồ côi) + cây psutil + con cháu đã chụp. Ghi log từng lỗi."""
        ghi_log(f"[runner {_gio()}] giết cả cây pid {proc.pid}: {ly_do}")
        if job:
            if not _k32.TerminateJobObject(job, 1):
                e = _loi_win("TerminateJobObject")
                log.error("%s", e)
                ghi_log(f"[runner] {e}")
        if not giet_cay(proc.pid, tao_luc):
            ghi_log(f"[runner] giet_cay pid {proc.pid} không chắc đã giết hết (xem log runner)")
        for p in list(con_chau.values()):
            try:
                if p.is_running():
                    p.kill()
            except psutil.NoSuchProcess:
                pass
            except psutil.Error as e:
                log.error("kill con cháu pid %s lỗi: %s", p.pid, e)
                ghi_log(f"[runner] kill con cháu pid {p.pid} lỗi: {e}")

    het_gio = bi_huy = vuot_luot = False
    session_id = None
    ket_qua = None
    so_luot = 0
    da_thay_msg: set[str] = set()
    cong_cu: list[str] = []
    van_ban_agent = ""
    duoi: deque[str] = deque(maxlen=DUOI_GIU_DONG)

    try:
        if file_jsonl is not None:
            f_jsonl = open(file_jsonl, "a", encoding="utf-8", newline="\n")
        flags, si = _cach_mo(hien_cua_so)
        ghi_log(f"[runner {_gio()}] bắt đầu: {Path(argv[0]).name} (cwd {cwd})")
        try:
            proc = subprocess.Popen(
                argv, cwd=cwd, env=env,
                stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE if la_claude else subprocess.STDOUT,
                creationflags=flags, startupinfo=si)
        except OSError as e:
            ghi_log(f"[runner {_gio()}] Không chạy được {argv[0]}: {e}")
            raise
        job = _tao_job_rieng(proc)
        try:
            tao_luc = psutil.Process(proc.pid).create_time()
        except psutil.Error:
            tao_luc = time.time()

        if stdin_text is not None:
            t = threading.Thread(target=_luong_ghi_stdin, args=(proc, stdin_text.encode("utf-8"), q),
                                 name=f"stdin-{proc.pid}", daemon=True)
            t.start()
            luong.append(t)
        cho_eof = {"out"}
        t = threading.Thread(target=_luong_doc, args=(proc.stdout, "out", q), name=f"out-{proc.pid}", daemon=True)
        t.start()
        luong.append(t)
        if la_claude:
            cho_eof.add("err")
            t = threading.Thread(target=_luong_doc, args=(proc.stderr, "err", q), name=f"err-{proc.pid}",
                                 daemon=True)
            t.start()
            luong.append(t)

        khi_bat_dau(proc.pid, tao_luc)

        han = time.monotonic() + het_gio_s
        lan_chup = 0.0
        thoat_luc = None
        da_giet_giu_pipe = False
        da_giet = False
        han_sau_giet = None
        khong_giet_duoc = False

        while True:
            try:
                nguon, dong = q.get(timeout=0.2)
            except queue.Empty:
                nguon, dong = None, None

            if nguon == "runner":
                ghi_log(f"[runner {_gio()}] {dong}")
            elif nguon is not None and dong is None:
                cho_eof.discard(nguon)
            elif nguon is not None:
                khi_doc_dong(dong)
                if la_claude and nguon == "out":
                    sk = sj.doc_su_kien(dong)
                    if sk is None:
                        ghi_log(dong)          # không phải JSON → chỉ vào .log, giữ .jsonl hợp lệ
                    else:
                        if f_jsonl is not None:
                            f_jsonl.write(dong + "\n")
                            f_jsonl.flush()
                        sid = sj.la_khoi_tao(sk)
                        if sid and sid != session_id:
                            session_id = sid
                            khi_co_session(sid)
                        if sj.dem_luot(sk):
                            ma = sj.ma_message(sk)
                            if ma is None or ma not in da_thay_msg:
                                if ma is not None:
                                    da_thay_msg.add(ma)
                                so_luot += 1
                        cong_cu.extend(ten for ten, _ in sj.ten_cong_cu(sk))
                        vb = sj.van_ban_assistant(sk)
                        if vb:
                            van_ban_agent = vb
                        kq = sj.la_ket_qua(sk)
                        if kq is not None:
                            ket_qua = kq
                            if session_id is None and kq["session_id"]:
                                session_id = kq["session_id"]
                        nguoi_doc = sj.dich_dong(sk, che)
                        if nguoi_doc:
                            ghi_log(nguoi_doc)
                elif la_claude:
                    ghi_log("[stderr] " + dong)
                else:
                    ghi_log(dong)
                duoi.append(dong)

            bay_gio = time.monotonic()
            dang_song = proc.poll() is None

            if not da_giet:
                ly_do = None
                if huy.is_set():
                    bi_huy, ly_do = True, "bị huỷ"
                elif bay_gio >= han:
                    het_gio, ly_do = True, f"quá giờ {het_gio_s} s"
                elif tran_luot is not None and so_luot > tran_luot:
                    vuot_luot, ly_do = True, f"vượt trần {tran_luot} lượt"
                if ly_do:
                    da_giet = True
                    giet_het(ly_do)
                    han_sau_giet = time.monotonic() + CHO_SAU_GIET_S
                    dang_song = proc.poll() is None
            elif dang_song and han_sau_giet is not None and bay_gio >= han_sau_giet:
                # R-06 P3-5: không để vòng chờ kẹt vô hạn khi giết thất bại
                khong_giet_duoc = True
                ghi_log(f"[runner {_gio()}] KHÔNG giết được pid {proc.pid} sau {CHO_SAU_GIET_S} s — bỏ chờ, "
                        "tiến trình có thể còn chạy (kiểm tay trên máy)")
                log.error("pid %s vẫn sống %s s sau khi giết — bỏ chờ", proc.pid, CHO_SAU_GIET_S)
                break

            if dang_song and bay_gio - lan_chup >= CHU_KY_CHUP_CON_S:
                lan_chup = bay_gio
                try:
                    for c in psutil.Process(proc.pid).children(recursive=True):
                        con_chau.setdefault(c.pid, c)
                except psutil.Error:
                    pass

            if not dang_song:
                if not cho_eof:
                    break
                if thoat_luc is None:
                    thoat_luc = bay_gio
                elif bay_gio - thoat_luc > CHO_EOF_S:
                    if not da_giet_giu_pipe:
                        da_giet_giu_pipe = True
                        thoat_luc = bay_gio
                        giet_het("tiến trình gốc đã thoát nhưng con cháu còn giữ pipe")
                    else:
                        ghi_log(f"[runner {_gio()}] pipe vẫn chưa đóng sau khi giết con cháu — bỏ đọc")
                        log.error("pid %s: pipe chưa EOF sau khi giết con cháu", proc.pid)
                        break

        ma_thoat = proc.poll() if khong_giet_duoc else proc.wait(timeout=CHO_DON_S)
        if la_claude:
            van_ban_cuoi = ket_qua["van_ban"] if ket_qua else van_ban_agent
        else:
            van_ban_cuoi = "\n".join(duoi)[-TOI_DA_VAN_BAN_CUOI:]
        ghi_log(f"[runner {_gio()}] kết thúc: mã {ma_thoat}"
                + (" · quá giờ" if het_gio else "") + (" · bị huỷ" if bi_huy else "")
                + (" · vượt trần lượt" if vuot_luot else "") + (" · KHÔNG giết được" if khong_giet_duoc else ""))
        return KetQuaTienTrinh(ma_thoat=ma_thoat, het_gio=het_gio, bi_huy=bi_huy, vuot_luot=vuot_luot,
                               ket_qua=ket_qua, van_ban_cuoi=van_ban_cuoi, session_id=session_id,
                               so_luot=so_luot, cong_cu_da_goi=cong_cu, khong_giet_duoc=khong_giet_duoc,
                               pid=proc.pid, pid_tao_luc=tao_luc)
    except BaseException as e:
        loi_chinh = e
        raise
    finally:
        loi_don: list[BaseException] = []

        def buoc(ten: str, f) -> None:
            try:
                f()
            except Exception as e:  # noqa: BLE001 — ghi lại, chạy tiếp các bước dọn còn lại
                log.error("Dọn %s lỗi: %s", ten, e, exc_info=True)
                loi_don.append(e)
                try:
                    if not f_log.closed:
                        ghi_log(f"[runner {_gio()}] dọn {ten} lỗi: {e}")
                except Exception:  # noqa: BLE001 — log file hỏng thì đã có log runner ở trên
                    pass

        if proc is not None and proc.poll() is None and not khong_giet_duoc:
            # khong_giet_duoc: đã giết và chờ đủ hạn — không chờ thêm (đã báo qua cờ trong kết quả)
            buoc("tiến trình còn sống", lambda: giet_het(f"dọn sau lỗi: {loi_chinh!r}"))
            buoc("chờ tiến trình", lambda: proc.wait(timeout=CHO_DON_S))
            if proc.poll() is None:
                # R-07 P3-1: không để cờ nằm im trong loi_don — gắn lên lỗi chính để vòng chạy giữ làn + kiểm tay
                khong_giet_duoc = True
                buoc("ghi log không giết được", lambda: ghi_log(
                    f"[runner {_gio()}] KHÔNG giết được pid {proc.pid} khi dọn sau lỗi — tiến trình có thể còn "
                    "chạy (kiểm tay trên máy)"))
                log.error("pid %s vẫn sống sau khi giết + chờ %s s (dọn sau lỗi)", proc.pid, CHO_DON_S)
                if loi_chinh is not None:
                    try:
                        setattr(loi_chinh, THUOC_TINH_KHONG_GIET, (proc.pid, tao_luc))
                    except (AttributeError, TypeError) as e:
                        log.error("không gắn được cờ không-giết-được lên lỗi %r: %s", loi_chinh, e)
        if job:
            buoc("handle Job Object riêng", lambda: _dong_handle(job))
        for t in luong:
            t.join(timeout=2)
            if t.is_alive():
                log.error("Luồng %s vẫn kẹt sau khi dọn (pipe bị giữ)", t.name)
        if proc is not None:
            for ten, tien_to, s in (("stdout", "out-", proc.stdout), ("stderr", "err-", proc.stderr)):
                # chỉ đóng khi luồng đọc đã xong; đóng pipe đang bị ReadFile chặn có thể treo
                if s is not None and not any(t.is_alive() and t.name.startswith(tien_to) for t in luong):
                    buoc(ten, s.close)
        if f_jsonl is not None:
            buoc("file jsonl", f_jsonl.close)
        buoc("file log", f_log.close)
        if loi_don and loi_chinh is None:
            raise loi_don[0]
