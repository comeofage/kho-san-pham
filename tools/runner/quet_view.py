"""Bọc chuỗi quét view video của mình (D15; đặc tả: docs/hoc-tu-dong.md §2.7, §3.4a, §6).

Chạy: `python -B -m runner.quet_view --ngay YYYY-MM-DD --view-dir <view-poster> --scan <tiktok_scan.py>
--poster-db <v2_data.db> --du-lieu <thư mục runner> [--nguon runner|tay]` (cwd = thư mục chứa gói `runner`;
`--nguon` tuỳ chọn, mặc định `tay`, chỉ để gắn vào nhật ký).

Nhật ký trong `<du_lieu>/quet_view/`: `<ngay>-chay.log` (của script này, ghi nối, mỗi dòng có `luot=<pid-giờ>
nguon=<runner|tay> lan=<n|->`); log tiến trình con theo lần chạy, không bao giờ ghi đè: `<ngay>-l<lan>-kenh-<h>.log`,
`<ngay>-l<lan>-bao-cao.log`, `<ngay>-l<lan>-ghi.log` (trùng tên → hậu tố `-2`, `-3`...).

Chuỗi ngoài (KHÔNG sửa): `tiktok_scan.py` (yt-dlp) ×N kênh → `bao_cao_view.py --khong-quet --khong-ghi`
→ `ghi_view_poster.py` (UPSERT `video_view_snapshots`). Script này chặn các điểm không an toàn S1–S7 (§2.7):
- S1 Apify tốn phí: `channels.json` có `source` khác `yt-dlp`/có `maxItems` → từ chối trước mọi tiến trình;
  không bao giờ truyền `--cho-phep-apify`; `raw` ghi nguồn khác `yt-dlp` → kênh lỗi; hash `channels.json` kiểm lại
  trước mỗi kênh, trước báo cáo và trước ghi DB.
- S2 kênh lỗi vẫn thoát 0: kênh chỉ `ok` khi có đủ bằng chứng quét thật (mã 0, dòng "  ✓ ", `raw` mới ghi,
  `fetched_at` ≥ phút bắt đầu, ≥ 1 video `last_seen == fetched_at`).
- S3 tất cả kênh ổn mới ghi DB.
- S4 mỗi bước có giới hạn giờ; quá giờ / xong bước → giết cả cây (Job Object + psutil + taskkill dự phòng).
- S5 `--ngay` phải bằng `DONG_HO_NGAY()` = `date.today()` (giờ máy, đúng cái `ghi_view_poster.py` dùng).
- S6 `dang_ban()`: mutex Radar / lần chạy tay → runner hoãn.
- S7 output con vào file log riêng; stdout chỉ đúng 1 dòng JSON (mã + số + handle đã kiểm regex).

Mọi chữ của chuỗi ngoài (tên kênh, tiêu đề, stderr yt-dlp) là dữ liệu KHÔNG tin cậy: chỉ rút ra số/enum.
Chỉ stdlib + psutil. Không hằng nào đọc env/đường dẫn lúc import.
"""
# Giờ máy (naive) là CỐ Ý: phải khớp tiktok_scan.py (datetime.now) và ghi_view_poster.py (date.today).
# ruff: noqa: DTZ005, DTZ007
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

import psutil

log = logging.getLogger("kho_runner.quet_view")

# ---------------------------------------------------------------- Hằng (interface §3.4a)

GOC_THAT: tuple[str, ...] = ("E:/kho-runner", "E:/tool/tiktok_poster_v2", "E:/phantichcanhquay/kho-san-pham/data",
                             "C:/Users/Mi/view-poster", "C:/Users/Mi/.claude/skills")
THU_MUC_RUNNER_THAT = "E:/kho-runner"
MUTEX_RADAR = "Global\\QuetKenhAntiPipeline"
SCRIPT_CHAY_TAY = ("tiktok_scan.py", "bao_cao_view.py", "ghi_view_poster.py")
RE_HANDLE = re.compile(r"^[A-Za-z0-9._]{2,24}$", re.ASCII)
HET_GIO_KENH_S, HET_GIO_BAO_CAO_S, HET_GIO_GHI_S, SO_LAN_TOI_DA_NGAY, SO_KENH_TOI_DA = 300, 120, 180, 3, 10
# Mẫu vị trí file cấu hình yt-dlp (K25 + portable/system/home). Chỉ mở rộng lúc gọi, không lúc import.
# Đối chiếu yt_dlp 2026.08.19 `options.py:56-87` + `utils/_utils.py:4738-4760` + `update.py:57-112`:
# - "Home" = os.path.join(<-P home, mặc định ''>, 'yt-dlp.conf') = cwd của tiến trình yt-dlp → {CWD}. tiktok_scan.py
#   :107-110 gọi yt-dlp không `-P`, không đặt cwd → cwd yt-dlp = cwd tiktok_scan = cwd con của script này.
# - "Portable" = thư mục exe (bản đóng gói) hoặc site-packages (pip). CreateProcess tìm "yt-dlp" ở thư mục python.exe
#   rồi tới cwd TRƯỚC PATH → {PYDIR}, {CWD} cũng có thể là thư mục portable.
# - "System" = os.path.join('/etc', ...) → trên Windows là ổ đĩa của cwd con → mọi mẫu tương đối/thiếu ổ được ghép
#   với cwd con (ds_file_cau_hinh_ytdlp), không với cwd của script này.
FILE_CAU_HINH_YTDLP: tuple[str, ...] = (
    "{APPDATA}/yt-dlp/config", "{APPDATA}/yt-dlp/config.txt", "{APPDATA}/yt-dlp.conf",
    "{HOME}/yt-dlp.conf", "{HOME}/yt-dlp.conf.txt", "{HOME}/.yt-dlp/config", "{HOME}/.yt-dlp/config.txt",
    "{HOME}/.config/yt-dlp/config", "{HOME}/.config/yt-dlp/config.txt", "{HOME}/.config/yt-dlp.conf",
    "{XDG}/yt-dlp/config", "{XDG}/yt-dlp/config.txt", "{XDG}/yt-dlp.conf",
    "{EXE}/yt-dlp.conf", "{EXE}/../Lib/site-packages/yt-dlp.conf",
    "{CWD}/yt-dlp.conf", "{PYDIR}/yt-dlp.conf",
    "/etc/yt-dlp.conf", "/etc/yt-dlp/config", "/etc/yt-dlp/config.txt",
)
LY_DO_QUET = ("ok", "da_quet", "qua_so_lan", "lech_ngay", "thieu_ytdlp", "kenh_cau_hinh_la", "ytdlp_co_cookie",
              "kenh_loi", "ghi_loi", "duong_dan_thu", "loi_bat_ngo")
TRANG_THAI_KENH = ("ok", "loi", "qua_gio", "rong")

# Ngoài interface — chỉnh được trong test.
HET_GIO_TONG_S = 22 * 60       # runner giết ở 25 phút; tự dừng sớm hơn để kịp ghi trạng thái
CHU_KY_CHUP_S = 0.5            # chụp con cháu khi chờ (lưới khi Job Object không gắn được)
CHO_GIET_S = 5
SO_LAN_THU_GHI = 20            # os.replace bị khoá (Windows) → thử lại
NGHI_THU_GHI_S = 0.1

RE_NGAY = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)
RE_FETCHED_AT = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", re.ASCII)   # tiktok_scan NOW_STR "%Y-%m-%d %H:%M"
DAU_DONG_OK_KENH = "  ✓ "                                                 # tiktok_scan.py:383
RE_DONG_GHI_OK = re.compile(r"\[OK\] snapshot (\d{4}-\d{2}-\d{2}): (\d+) video", re.ASCII)  # ghi_view_poster.py:46
NGUON_YTDLP = "yt-dlp"
TRANG_THAI_FILE = ("dang_chay", "ok", "loi")


class LoiQuet(Exception):
    """Dừng lượt với một mã thuộc LY_DO_QUET."""

    def __init__(self, ly_do: str):
        assert ly_do in LY_DO_QUET, ly_do
        super().__init__(ly_do)
        self.ly_do = ly_do


# ---------------------------------------------------------------- Chặn chạm production (§3.6, §8.1)

def _chuan(p) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(p)))


def _nam_duoi(p: str, goc: str) -> bool:
    return p == goc or p.startswith(goc.rstrip("\\/") + os.sep)


def kiem_duong_dan_thu(du_lieu: Path, *nguon: Path) -> None:
    """`du_lieu` là thư mục runner thật (và không có KHO_HOC_TEST=1) → cho qua. Ngược lại: `du_lieu` hoặc bất kỳ
    `nguon` nằm dưới một GOC_THAT → RuntimeError. Gọi TRƯỚC mọi lần mở file / sinh tiến trình. Không dựa riêng vào
    env (tiến trình con của runner chạy env tối thiểu): kiểm theo cặp đường dẫn."""
    la_test = os.environ.get("KHO_HOC_TEST") == "1"
    if not la_test and _chuan(du_lieu) == _chuan(THU_MUC_RUNNER_THAT):
        return
    goc = [_chuan(g) for g in GOC_THAT]
    for p in (du_lieu, *nguon):
        c = _chuan(p)
        if any(_nam_duoi(c, g) for g in goc):
            raise RuntimeError("đường dẫn thật trong lúc chạy thử/test — từ chối (du_lieu không phải thư mục "
                               "runner thật)")


# ---------------------------------------------------------------- Đang bận (S6)

_K32 = None


def _k32():
    global _K32
    if _K32 is None:
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        k.OpenMutexW.restype = wintypes.HANDLE
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        k.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        k.SetInformationJobObject.restype = wintypes.BOOL
        k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k.AssignProcessToJobObject.restype = wintypes.BOOL
        k.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k.TerminateJobObject.restype = wintypes.BOOL
        _K32 = k
    return _K32


_SYNCHRONIZE = 0x00100000
_ERROR_FILE_NOT_FOUND = 2
_ERROR_ACCESS_DENIED = 5


def _mutex_ton_tai(ten: str) -> bool:
    k = _k32()
    h = k.OpenMutexW(_SYNCHRONIZE, False, ten)
    if h:
        k.CloseHandle(h)
        return True
    ma = ctypes.get_last_error()
    if ma == _ERROR_FILE_NOT_FOUND:
        return False
    if ma == _ERROR_ACCESS_DENIED:     # có mutex nhưng không đủ quyền mở → vẫn là đang có pipeline giữ
        return True
    raise OSError(ma, f"OpenMutexW lỗi {ma}")


def _ten_file(arg: str) -> str:
    return re.split(r"[\\/]", arg)[-1].lower()


def _la_python(ten: str) -> bool:
    t = (ten or "").lower()
    return t.startswith("python") or t in ("py.exe", "py", "pyw.exe")


def _co_chay_tay(script: tuple[str, ...], goc_runner: int) -> bool:
    can = {s.lower() for s in script}
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if p.info["pid"] == goc_runner or not _la_python(p.info.get("name")):
                continue
            if not any(_ten_file(a) in can for a in (p.cmdline() or [])):
                continue
            if goc_runner in {a.pid for a in p.parents()}:
                continue                                    # thuộc cây của runner/quet_view
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False


def dang_ban(ten_mutex: str = MUTEX_RADAR, *, script_chay_tay: tuple[str, ...] = SCRIPT_CHAY_TAY,
             goc_runner: int | None = None) -> str | None:
    """'radar_dang_quet' (mutex pipeline Radar đang có) | 'dang_chay_tay' (có tiến trình python chạy một trong
    `script_chay_tay`, không thuộc cây `goc_runner` — mặc định chính tiến trình gọi) | None.
    Lỗi bất kỳ → None + log (không chặn vĩnh viễn). `script_chay_tay`/`goc_runner` chỉ để test cô lập."""
    try:
        if sys.platform == "win32" and _mutex_ton_tai(ten_mutex):
            return "radar_dang_quet"
        if _co_chay_tay(tuple(script_chay_tay), os.getpid() if goc_runner is None else int(goc_runner)):
            return "dang_chay_tay"
        return None
    except Exception as e:  # noqa: BLE001 — hợp đồng: lỗi → None + log
        log.warning("dang_ban() lỗi, coi như không bận: %r", e)
        return None


# ---------------------------------------------------------------- File trạng thái

def _thu_muc_qv(du_lieu: Path) -> Path:
    return Path(du_lieu) / "quet_view"


def _file_trang_thai(du_lieu: Path, ngay: str) -> Path:
    return _thu_muc_qv(du_lieu) / f"{ngay}.json"


def _hop_le(d) -> bool:
    return (isinstance(d, dict) and d.get("trang_thai") in TRANG_THAI_FILE
            and isinstance(d.get("lan"), int) and not isinstance(d.get("lan"), bool) and d["lan"] >= 0)


def _doc_file_trang_thai(p: Path) -> tuple[bool, dict | None]:
    """(có file?, dict hợp lệ hoặc None nếu hỏng). File bị khoá tạm → thử lại vài lần."""
    for i in range(SO_LAN_THU_GHI):
        try:
            raw = p.read_bytes()
            break
        except FileNotFoundError:
            return False, None
        except PermissionError:
            if i == SO_LAN_THU_GHI - 1:
                return True, None
            time.sleep(NGHI_THU_GHI_S)
        except OSError:
            return True, None
    try:
        d = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return True, None
    return True, (d if _hop_le(d) else None)


def doc_ket_qua(du_lieu: Path, ngay: str) -> dict | None:
    """Đọc `<du_lieu>/quet_view/<ngay>.json`. Thiếu / hỏng / sai dạng → None."""
    if not isinstance(ngay, str) or not RE_NGAY.fullmatch(ngay):
        return None
    _, d = _doc_file_trang_thai(_file_trang_thai(du_lieu, ngay))
    return d


def ghi_nguyen_tu(p: Path, du_lieu: dict) -> None:
    """Ghi file tạm cùng thư mục rồi os.replace; đích bị khoá (người đọc/antivirus) → thử lại; hết lượt → ném."""
    tam = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    try:
        tam.write_text(json.dumps(du_lieu, ensure_ascii=True), encoding="utf-8")
        for i in range(SO_LAN_THU_GHI):
            try:
                os.replace(tam, p)
                return
            except PermissionError:
                if i == SO_LAN_THU_GHI - 1:
                    raise
                time.sleep(NGHI_THU_GHI_S)
    finally:
        if tam.exists():
            try:
                tam.unlink()
            except OSError as e:
                log.error("Không xoá được file tạm %s: %s", tam, e)


# ---------------------------------------------------------------- Kiểm trước (S1, S5, cookie)

def kiem_kenh(du_lieu_cau_hinh) -> list[str]:
    """Hàm thuần: `channels.json` đã parse → danh sách handle. Sai bất kỳ điều gì → LoiQuet('kenh_cau_hinh_la').
    Chặn S1: kênh có khoá `source` mà giá trị (lower) khác 'yt-dlp', hoặc có `maxItems`."""
    if not isinstance(du_lieu_cau_hinh, dict) or not isinstance(du_lieu_cau_hinh.get("channels"), list):
        raise LoiQuet("kenh_cau_hinh_la")
    ds = du_lieu_cau_hinh["channels"]
    if not 1 <= len(ds) <= SO_KENH_TOI_DA:
        raise LoiQuet("kenh_cau_hinh_la")
    handles: list[str] = []
    for c in ds:
        if not isinstance(c, dict):
            raise LoiQuet("kenh_cau_hinh_la")
        h = c.get("handle")
        if not isinstance(h, str) or not RE_HANDLE.fullmatch(h) or set(h) == {"."} or h in handles:
            raise LoiQuet("kenh_cau_hinh_la")
        if "source" in c and not (isinstance(c["source"], str) and c["source"].lower() == NGUON_YTDLP):
            raise LoiQuet("kenh_cau_hinh_la")
        if "maxItems" in c:
            raise LoiQuet("kenh_cau_hinh_la")
        handles.append(h)
    return handles


def _doc_kenh(view_dir: Path) -> tuple[list[str], str]:
    p = view_dir / "channels.json"
    try:
        b = p.read_bytes()
        d = json.loads(b.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise LoiQuet("kenh_cau_hinh_la") from None
    return kiem_kenh(d), hashlib.sha256(b).hexdigest()


def ds_file_cau_hinh_ytdlp(env: dict | None = None, ytdlp: str | None = None, cwd: Path | str | None = None,
                           python: str | None = None) -> list[Path]:
    """Mở rộng FILE_CAU_HINH_YTDLP lúc gọi. HOME lấy cả USERPROFILE / HOME / HOMEDRIVE+HOMEPATH (Python trên
    Windows dùng USERPROFILE cho `~`), dư còn hơn sót. `cwd` = cwd THẬT của tiến trình con (mặc định cwd hiện tại);
    mọi đường dẫn tương đối / thiếu ổ đĩa (`/etc/...`) được ghép với nó, đúng như yt-dlp chạy trong cwd đó tự hiểu.
    `python` = python chạy tiktok_scan (mặc định sys.executable, đúng cái lenh_quet dùng)."""
    env = os.environ if env is None else env
    cwd_con = os.fspath(cwd) if cwd is not None else os.getcwd()
    py = python if python is not None else sys.executable
    gia_tri: dict[str, list[str]] = {
        "APPDATA": [env["APPDATA"]] if env.get("APPDATA") else [],
        "HOME": [v for v in (env.get("USERPROFILE"), env.get("HOME"),
                             (env.get("HOMEDRIVE", "") + env.get("HOMEPATH", "")) or None) if v],
        "XDG": [env["XDG_CONFIG_HOME"]] if env.get("XDG_CONFIG_HOME") else [],
        "EXE": [str(Path(ytdlp).parent)] if ytdlp else [],
        "CWD": [cwd_con],
        "PYDIR": [str(Path(py).parent)] if py else [],
    }
    ra: list[Path] = []
    for mau in FILE_CAU_HINH_YTDLP:
        m = re.match(r"\{(\w+)\}", mau)
        goc = gia_tri[m.group(1)] if m else [""]
        for g in goc:
            p = Path(os.path.normpath(os.path.join(cwd_con, mau.replace(m.group(0), g) if m else mau)))
            if p not in ra:
                ra.append(p)
    return ra


# Nội dung cấu hình cấm (bytes đã lower): cookie; `--config-location(s)` (kéo file cấu hình khác mà danh sách trên
# không thấy); `-P`/`--paths` (đổi thư mục "Home" → yt-dlp đọc `<home>/yt-dlp.conf` ở chỗ khác, options.py:85).
RE_CAU_HINH_CAM = re.compile(rb"cookie|config-location|--paths|(?:^|\s)-[a-z]*p", re.ASCII)


def cau_hinh_cam(noi_dung: bytes) -> bool:
    """Hàm thuần: nội dung một file cấu hình yt-dlp có điều cấm (xem RE_CAU_HINH_CAM) → True. Dư còn hơn sót:
    `-p` (mật khẩu) cũng bị chặn — lượt quét không người canh không được đăng nhập."""
    return RE_CAU_HINH_CAM.search(noi_dung.lower()) is not None


def co_cookie_ytdlp(ds: list[Path]) -> bool:
    """File cấu hình nào tồn tại mà `cau_hinh_cam` (cookie, config-location, -P/--paths) → True.
    Tồn tại mà không đọc được → True (đóng an toàn)."""
    for p in ds:
        try:
            if not p.is_file():
                continue
            if cau_hinh_cam(p.read_bytes()):
                return True
        except OSError:
            return True
    return False


# ---------------------------------------------------------------- Dựng lệnh (thuần)

def lenh_quet(scan: Path, view_dir: Path, handle: str) -> list[str]:
    """Lệnh quét 1 kênh. KHÔNG bao giờ có `--cho-phep-apify`."""
    return [sys.executable, "-B", str(scan), "--dir", str(view_dir), "--only", handle, "--so-ngay", "7"]


def lenh_bao_cao(view_dir: Path) -> list[str]:
    return [sys.executable, "-B", str(view_dir / "bao_cao_view.py"), "--khong-quet", "--khong-ghi"]


def lenh_ghi(view_dir: Path) -> list[str]:
    return [sys.executable, "-B", str(view_dir / "ghi_view_poster.py")]


# ---------------------------------------------------------------- Chạy một bước + giết cây (S4, S7)

class KetQuaBuoc:
    __slots__ = ("con_sot", "ma", "qua_gio")

    def __init__(self, ma: int | None, qua_gio: bool, con_sot: list[int]):
        self.ma, self.qua_gio, self.con_sot = ma, qua_gio, con_sot


def _tao_job(proc: subprocess.Popen):
    """Job Object KILL_ON_JOB_CLOSE cho riêng bước này. None nếu không gắn được (dựa vào lưới psutil)."""
    if sys.platform != "win32":
        return None
    from ctypes import wintypes

    class _BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("a", "b", "c", "d", "e", "f")]

    class _EXT(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _BASIC), ("IoInfo", _IO),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k = _k32()
    job = k.CreateJobObjectW(None, None)
    if not job:
        log.warning("CreateJobObjectW lỗi %s", ctypes.get_last_error())
        return None
    info = _EXT()
    info.BasicLimitInformation.LimitFlags = 0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if (not k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
            or not k.AssignProcessToJobObject(job, int(proc._handle))):
        log.warning("Không gắn được Job Object cho pid %s: %s", proc.pid, ctypes.get_last_error())
        k.CloseHandle(job)
        return None
    return job


def _chup_con(goc: psutil.Process | None, da_thay: dict[int, psutil.Process]) -> None:
    if goc is None:
        return
    try:
        for c in goc.children(recursive=True):
            da_thay.setdefault(c.pid, c)
    except psutil.Error:
        pass


SAI_SO_TAO_LUC_S = 0.01     # create_time của CÙNG một tiến trình đọc lại phải trùng; lệch hơn → PID đã bị dùng lại


def la_con_minh(tao_luc_con: float | None, tao_luc_goc: float | None, tao_luc_pid_goc_bay_gio: float | None) -> bool:
    """Hàm thuần: tiến trình có ppid = pid gốc có phải con (mồ côi) của ĐÚNG tiến trình gốc mình sinh không.
    - Không biết lúc sinh gốc (`tao_luc_goc` None) hoặc của con → không chắc → False (không giết; Job Object lo).
    - Con sinh trước gốc (trừ sai số 1 s) → không phải con của gốc.
    - PID gốc hiện đang thuộc một tiến trình KHÁC (create_time lệch) → con nào sinh từ lúc kẻ mới xuất hiện trở đi là
      con của kẻ mới (Windows giữ ppid cũ, PID dùng lại được) → False. Con sinh trước đó vẫn là của mình."""
    if tao_luc_goc is None or tao_luc_con is None:
        return False
    if tao_luc_con < tao_luc_goc - 1.0:
        return False
    if tao_luc_pid_goc_bay_gio is not None and abs(tao_luc_pid_goc_bay_gio - tao_luc_goc) > SAI_SO_TAO_LUC_S:
        return tao_luc_con < tao_luc_pid_goc_bay_gio
    return True


def _tao_luc_pid(pid: int) -> float | None:
    try:
        return psutil.Process(pid).create_time()
    except psutil.Error:
        return None


def _con_mo_coi(pid_cha: int, tao_luc: float | None) -> list[psutil.Process]:
    """Tiến trình có ppid = pid gốc (Windows giữ ppid cũ khi cha chết) mà `la_con_minh`, cùng con cháu của chúng.
    Đối chiếu create_time của PID gốc LÚC NÀY với lúc sinh để không giết nhầm khi PID gốc đã bị dùng lại."""
    ra: list[psutil.Process] = []
    if tao_luc is None:
        log.warning("Không biết lúc sinh pid %s — bỏ qua tìm con mồ côi theo ppid", pid_cha)
        return ra
    tao_luc_bay_gio = _tao_luc_pid(pid_cha)
    for p in psutil.process_iter(["pid", "ppid", "create_time"]):
        try:
            if p.info["ppid"] != pid_cha or p.info["pid"] == pid_cha:
                continue
            if not la_con_minh(p.info["create_time"], tao_luc, tao_luc_bay_gio):
                continue
            ra.append(p)
            ra.extend(p.children(recursive=True))
        except psutil.Error:
            continue
    return ra


def _giet(ds: list[psutil.Process]) -> list[int]:
    """Giết danh sách; còn sống sau CHO_GIET_S → taskkill /T /F /PID (chỉ pid do chính mình sinh). Trả pid còn sống."""
    song = []
    for p in ds:
        try:
            if p.is_running():
                p.kill()
                song.append(p)
        except psutil.NoSuchProcess:
            pass
        except psutil.Error as e:
            log.error("kill pid %s lỗi: %s", p.pid, e)
            song.append(p)
    if not song:
        return []
    _, con = psutil.wait_procs(song, timeout=CHO_GIET_S)
    # is_running() so create_time với lúc ghi nhận: đã chết hoặc PID đã thuộc kẻ khác → không taskkill PID đó
    con = [p for p in con if p.is_running()]
    for p in con:
        try:
            r = subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, timeout=30, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode != 0:
                log.error("taskkill pid %s mã %s", p.pid, r.returncode)
        except (OSError, subprocess.TimeoutExpired) as e:
            log.error("taskkill pid %s lỗi: %s", p.pid, e)
    _, con = psutil.wait_procs(con, timeout=CHO_GIET_S)
    return [p.pid for p in con]


def _env_con() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def chay_buoc(lenh: list[str], cwd: Path, file_log: Path, het_gio_s: float) -> KetQuaBuoc:
    """Popen dạng list, stdin DEVNULL, stdout+stderr vào `file_log` (không pipe → cháu giữ handle không làm treo).
    Hết giờ → giết cả cây. Dù xong hay quá giờ đều dọn sạch con cháu còn sót (Job Object + psutil)."""
    f = proc = job = goc = None
    tao_luc = None
    da_thay: dict[int, psutil.Process] = {}
    ma: int | None = None
    qua_gio = False
    con_sot: list[int] = []
    try:
        f = open(file_log, "xb")  # noqa: SIM115 — "x": không bao giờ ghi đè log cũ; đóng trong finally sau khi cây chết
        proc = subprocess.Popen(lenh, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT,
                                env=_env_con(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        job = _tao_job(proc)
        try:
            goc = psutil.Process(proc.pid)
            tao_luc = goc.create_time()
        except psutil.Error:
            goc = None
        han = time.monotonic() + max(0.0, het_gio_s)
        while True:
            try:
                ma = proc.wait(timeout=max(0.01, min(CHU_KY_CHUP_S, han - time.monotonic())))
                break
            except subprocess.TimeoutExpired:
                _chup_con(goc, da_thay)
                if time.monotonic() >= han:
                    qua_gio = True
                    break
    finally:
        if proc is not None:
            _chup_con(goc, da_thay)
            ds = ([goc] if goc is not None else []) + list(da_thay.values()) + _con_mo_coi(proc.pid, tao_luc)
            if job is not None:
                k = _k32()
                if not k.TerminateJobObject(job, 1):
                    log.debug("TerminateJobObject: %s", ctypes.get_last_error())
                k.CloseHandle(job)
            con_sot = _giet(ds)
            if con_sot:
                log.error("Còn tiến trình sống sau khi giết cây: %s", con_sot)
            try:
                proc.wait(timeout=CHO_GIET_S)
            except subprocess.TimeoutExpired:
                con_sot.append(proc.pid)
        if f is not None:
            f.close()
    return KetQuaBuoc(None if qua_gio else ma, qua_gio, con_sot)


# ---------------------------------------------------------------- Đánh giá kênh (S2) — thuần

def co_dong_ok_kenh(van_ban: str) -> bool:
    return any(d.startswith(DAU_DONG_OK_KENH) for d in van_ban.splitlines())


def danh_gia_raw(raw, handle: str, moc_phut: datetime, bay_gio: datetime) -> tuple[str, int, int]:
    """Hàm thuần trên `raw/<h>.json` đã parse. Chỉ đọc handle/source/fetched_at/videos[].last_seen.
    Trả (trang_thai, so_video_quet = tổng video trong raw, so_video_cap_nhat = video có last_seen == fetched_at)."""
    if not isinstance(raw, dict) or raw.get("handle") != handle or raw.get("source") != NGUON_YTDLP:
        return "loi", 0, 0
    fa = raw.get("fetched_at")
    vids = raw.get("videos")
    if not isinstance(fa, str) or not RE_FETCHED_AT.fullmatch(fa) or not isinstance(vids, list):
        return "loi", 0, 0
    try:
        t_fa = datetime.strptime(fa, "%Y-%m-%d %H:%M")
    except ValueError:
        return "loi", 0, 0
    if t_fa < moc_phut.replace(second=0, microsecond=0) or t_fa > bay_gio:
        return "loi", 0, 0
    moi = sum(1 for v in vids if isinstance(v, dict) and v.get("last_seen") == fa and v.get("id"))
    if moi == 0:
        return "rong", len(vids), 0
    return "ok", len(vids), moi


def _mtime_ns(p: Path) -> int | None:
    try:
        return p.stat().st_mtime_ns
    except OSError:
        return None


def danh_gia_kenh(kq: KetQuaBuoc, file_log: Path, raw_p: Path, mtime_truoc: int | None, handle: str,
                  moc: datetime) -> dict:
    ra = {"handle": handle, "trang_thai": "loi", "so_video_quet": 0, "so_video_cap_nhat": 0}
    if kq.qua_gio:
        ra["trang_thai"] = "qua_gio"
        return ra
    if kq.ma != 0 or kq.con_sot:
        return ra
    try:
        van_ban = file_log.read_bytes().decode("utf-8", "replace")
    except OSError:
        return ra
    if not co_dong_ok_kenh(van_ban):
        return ra
    sau = _mtime_ns(raw_p)
    if sau is None or (mtime_truoc is not None and sau <= mtime_truoc) or sau < (moc.timestamp() - 2) * 1e9:
        return ra
    try:
        raw = json.loads(raw_p.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return ra
    tt, tong, moi = danh_gia_raw(raw, handle, moc, datetime.now().replace(second=59, microsecond=999999))
    ra.update(trang_thai=tt, so_video_quet=tong, so_video_cap_nhat=moi)
    return ra


# ---------------------------------------------------------------- Ghi DB (S3)

def doc_dong_ghi_ok(van_ban: str, ngay: str) -> int | None:
    """Số video từ dòng `[OK] snapshot <ngay>: <n> video` (ghi_view_poster.py:46); không có/khác ngày → None."""
    for d in van_ban.splitlines():
        m = RE_DONG_GHI_OK.match(d.strip())
        if m and m.group(1) == ngay and int(m.group(2)) > 0:
            return int(m.group(2))
    return None


def dem_dong_db(poster_db: Path, ngay: str) -> int:
    uri = Path(poster_db).resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        return int(con.execute("SELECT COUNT(*) FROM video_view_snapshots WHERE collected_at=?",
                               (ngay,)).fetchone()[0])
    finally:
        con.close()


# ---------------------------------------------------------------- Khoá đơn lượt (theo thư mục dữ liệu)

class _KhoaLuot:
    """msvcrt.locking không chờ trên `<du_lieu>/quet_view/.khoa`. Khoá gắn với fd: tiến trình chết là OS nhả,
    không có TTL. `nha()` không nuốt lỗi: ghi log rồi ném."""

    def __init__(self, p: Path):
        self.p = p
        self.fd: int | None = None

    def giu(self) -> bool:
        self.fd = os.open(self.p, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0))
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            os.close(self.fd)
            self.fd = None
            return False

    def nha(self) -> None:
        if self.fd is None:
            return
        fd, self.fd = self.fd, None
        loi = None
        try:
            if sys.platform == "win32":
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError as e:
            log.error("Không mở khoá %s: %s", self.p, e)
            loi = e
        try:
            os.close(fd)
        except OSError as e:
            log.error("Không đóng %s: %s", self.p, e)
            loi = loi or e
        if loi:
            raise loi


# ---------------------------------------------------------------- Luồng chính

# Nguồn "hôm nay" (S5). Mặc định = ngày theo giờ máy (máy nhà đặt giờ VN), ĐÚNG cái ghi_view_poster.py dùng
# (date.today()) để `collected_at` khớp `--ngay`. Ngoài interface: test thay bằng hàm trả ngày cố định.
DONG_HO_NGAY: Callable[[], date] = date.today

NGUON_KICH_HOAT = ("runner", "tay")      # --nguon, tuỳ chọn, mặc định "tay" (lệnh §10 bước 5 chạy nguyên văn)
DINH_DANG_NHAT_KY = "%(asctime)s %(levelname)s luot=%(luot)s nguon=%(nguon)s lan=%(lan)s %(message)s"
SO_LOG_TRUNG_TOI_DA = 1000


def _hom_nay() -> str:
    return DONG_HO_NGAY().isoformat()


def _gio_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _in(d: dict) -> None:
    sys.stdout.write(json.dumps(d, ensure_ascii=True) + "\n")
    sys.stdout.flush()


class _NgCanhLuot(logging.Filter):
    """Gắn `luot` (pid-giờ bắt đầu-6 hex ngẫu nhiên, riêng từng lần gọi), `nguon`, `lan` vào mọi dòng nhật ký.
    `lan` là '-' cho tới khi lượt nhận số lần trong file trạng thái (lượt dừng sớm: khoá bận, da_quet...)."""

    def __init__(self, nguon: str):
        super().__init__()
        self.luot = f"{os.getpid()}-{datetime.now().strftime('%H%M%S')}-{os.urandom(3).hex()}"
        self.nguon = nguon
        self.lan: int | str = "-"

    def filter(self, record: logging.LogRecord) -> bool:
        record.luot, record.nguon, record.lan = self.luot, self.nguon, self.lan
        return True


def file_log_buoc(qv: Path, ngay: str, lan: int, ten: str) -> Path:
    """`<ngay>-l<lan>-<ten>.log` trong quet_view/; đã có (vd file trạng thái bị xoá tay nên `lan` lặp lại) →
    `<ngay>-l<lan>-<ten>-2.log`, `-3`... Không bao giờ trả file đã tồn tại (chay_buoc mở bằng "x" để chắc)."""
    goc = f"{ngay}-l{lan}-{ten}"
    p = qv / f"{goc}.log"
    k = 2
    while p.exists():
        if k > SO_LOG_TRUNG_TOI_DA:
            raise OSError(f"quá {SO_LOG_TRUNG_TOI_DA} file log trùng tên")
        p = qv / f"{goc}-{k}.log"
        k += 1
    return p


def _phan_tich_tham_so(argv):
    ap = argparse.ArgumentParser(prog="runner.quet_view", add_help=False)
    for t in ("--ngay", "--view-dir", "--scan", "--poster-db", "--du-lieu"):
        ap.add_argument(t, required=True)
    ap.add_argument("--nguon", choices=NGUON_KICH_HOAT, default="tay")
    return ap.parse_args(argv)


def chay(argv: list[str] | None = None) -> int:
    """0 = ok | da_quet; 1 = lỗi. In đúng 1 dòng JSON (mã + số + handle đã kiểm) ra stdout."""
    try:
        a = _phan_tich_tham_so(argv)
    except SystemExit:
        _in({"trang_thai": "loi", "ly_do": "loi_bat_ngo"})
        return 1
    du_lieu, view_dir, scan, poster_db = (Path(a.du_lieu), Path(a.view_dir), Path(a.scan), Path(a.poster_db))
    ngay = a.ngay
    # 1. chặn chạm production TRƯỚC mọi lần mở file / sinh tiến trình
    try:
        kiem_duong_dan_thu(du_lieu, view_dir, scan, poster_db)
    except RuntimeError:
        _in({"trang_thai": "loi", "ly_do": "duong_dan_thu"})
        return 1
    if not isinstance(ngay, str) or not RE_NGAY.fullmatch(ngay):
        _in({"trang_thai": "loi", "ly_do": "lech_ngay"})       # không dựng được tên file trạng thái an toàn
        return 1
    qv = _thu_muc_qv(du_lieu)
    khoa = nhat_ky = None
    ng = _NgCanhLuot(a.nguon)
    muc_cu = log.level
    try:
        qv.mkdir(parents=True, exist_ok=True)
        # nhật ký của chính script → file trong quet_view/ (không ra stderr: runner gộp stderr vào log việc).
        # Một file/ngày, ghi nối (mode "a"); mỗi dòng mang luot/nguon/lan để tách từng lần chạy (CL20).
        nhat_ky = logging.FileHandler(qv / f"{ngay}-chay.log", encoding="utf-8")
        nhat_ky.setFormatter(logging.Formatter(DINH_DANG_NHAT_KY))
        nhat_ky.addFilter(ng)
        nhat_ky.setLevel(logging.INFO)
        log.addHandler(nhat_ky)
        log.setLevel(logging.INFO)
        log.info("bắt đầu ngay=%s", ngay)
        khoa = _KhoaLuot(qv / ".khoa")
        if not khoa.giu():
            khoa = None
            log.error("Đang có lượt quet_view khác giữ khoá %s", qv)
            _in({"trang_thai": "loi", "ly_do": "loi_bat_ngo"})
            return 1
        return _chay_trong_khoa(ngay, view_dir.resolve(), scan.resolve(), poster_db.resolve(), qv, ng)
    except Exception:  # không lộ chữ lỗi ra stdout
        log.exception("quet_view lỗi bất ngờ")
        _in({"trang_thai": "loi", "ly_do": "loi_bat_ngo"})
        return 1
    finally:
        if khoa is not None:
            try:
                khoa.nha()       # fd đã đóng trong nha() dù unlock lỗi → OS nhả khoá; lỗi được ghi log
            except OSError:
                pass
        if nhat_ky is not None:
            log.removeHandler(nhat_ky)
            nhat_ky.close()
        log.setLevel(muc_cu)


def _ghi_nhat_ky(qv: Path, ngay: str, dong: str) -> None:
    log.error("%s", dong)


def _cwd_con(view_dir: Path) -> Path:
    """cwd của MỌI tiến trình con (tiktok_scan → yt-dlp, bao_cao_view, ghi_view_poster). Kiểm cấu hình yt-dlp dùng
    đúng giá trị này (yt-dlp đọc `<cwd>/yt-dlp.conf`), nên đổi cwd con thì kiểm đi theo."""
    return view_dir


def _kenh_doi(view_dir: Path, bam: str) -> str | None:
    """channels.json đổi so với lúc kiểm (TOCTOU S1) hoặc hết hợp lệ → mã lỗi; nguyên vẹn → None."""
    try:
        return None if _doc_kenh(view_dir)[1] == bam else "kenh_cau_hinh_la"
    except LoiQuet as e:
        return e.ly_do


def _chay_trong_khoa(ngay: str, view_dir: Path, scan: Path, poster_db: Path, qv: Path,
                     ng: _NgCanhLuot | None = None) -> int:
    p_tt = qv / f"{ngay}.json"
    cwd = _cwd_con(view_dir)
    # 2. trạng thái ngày
    co_file, cu = _doc_file_trang_thai(p_tt)
    if co_file and cu is None:
        _ghi_nhat_ky(qv, ngay, "file trạng thái hỏng — không tự ghi đè, cần người xem")
        _in({"trang_thai": "loi", "ly_do": "loi_bat_ngo"})
        return 1
    if cu is not None and cu["trang_thai"] == "ok":
        log.info("kết thúc ly_do=da_quet (lan đã ok=%s)", cu["lan"])
        _in({"trang_thai": "da_quet", "ly_do": "da_quet", "lan": cu["lan"]})
        return 0
    lan_cu = cu["lan"] if cu is not None else 0
    if lan_cu >= SO_LAN_TOI_DA_NGAY:
        log.info("kết thúc ly_do=qua_so_lan (đã %s lần)", lan_cu)
        _in({"trang_thai": "loi", "ly_do": "qua_so_lan", "lan": lan_cu})
        return 1
    lan = lan_cu + 1
    tt = {"trang_thai": "dang_chay", "lan": lan, "bat_dau": _gio_iso()}
    ghi_nguyen_tu(p_tt, tt)              # ghi TRƯỚC khi gọi mạng; lỗi → ném → loi_bat_ngo, không quét
    if ng is not None:
        ng.lan = lan
    log.info("đã ghi dang_chay")
    bat_dau_tong = time.monotonic()

    def con_lai() -> float:
        return HET_GIO_TONG_S - (time.monotonic() - bat_dau_tong)

    def ket_thuc(ly_do: str, **them) -> int:
        tt.update(trang_thai="ok" if ly_do == "ok" else "loi", ly_do=ly_do, ket_thuc=_gio_iso(), **them)
        try:
            ghi_nguyen_tu(p_tt, tt)
        except OSError as e:
            log.error("Không ghi được trạng thái cuối: %s", e)
            _ghi_nhat_ky(qv, ngay, f"không ghi được trạng thái cuối ({type(e).__name__})")
            out = {k: v for k, v in tt.items()}
            out.update(trang_thai="loi", ly_do="loi_bat_ngo")
            _in(out)
            return 1
        log.info("kết thúc ly_do=%s", ly_do)
        _in(tt)
        return 0 if ly_do == "ok" else 1

    try:
        # 3. kiểm trước
        if ngay != _hom_nay():
            return ket_thuc("lech_ngay")
        ytdlp = shutil.which("yt-dlp")
        if ytdlp is None:
            return ket_thuc("thieu_ytdlp")
        try:
            handles, bam = _doc_kenh(view_dir)
        except LoiQuet as e:
            return ket_thuc(e.ly_do)
        if co_cookie_ytdlp(ds_file_cau_hinh_ytdlp(ytdlp=ytdlp, cwd=cwd)):
            return ket_thuc("ytdlp_co_cookie")
        if not (view_dir / "ghi_view_poster.py").is_file() or not poster_db.is_file():
            return ket_thuc("ghi_loi")

        # 4. quét từng kênh, tuần tự
        kenh: list[dict] = []
        for h in handles:
            ld = _kenh_doi(view_dir, bam)
            if ld:
                return ket_thuc(ld, kenh=kenh)
            raw_p = view_dir / "raw" / f"{h}.json"
            mtime_truoc = _mtime_ns(raw_p)
            moc = datetime.now()
            if con_lai() <= 0:
                kenh.append({"handle": h, "trang_thai": "qua_gio", "so_video_quet": 0, "so_video_cap_nhat": 0})
                continue
            file_log = file_log_buoc(qv, ngay, lan, f"kenh-{h}")
            kq = chay_buoc(lenh_quet(scan, view_dir, h), cwd, file_log, min(HET_GIO_KENH_S, con_lai()))
            kenh.append(danh_gia_kenh(kq, file_log, raw_p, mtime_truoc, h, moc))

        # 5. có kênh không ok → không ghi DB
        if any(k["trang_thai"] != "ok" for k in kenh):
            return ket_thuc("kenh_loi", kenh=kenh)

        # 6. báo cáo md (lỗi không làm hỏng lượt), rồi ghi DB. ghi_view_poster.py TỰ đọc lại channels.json
        # → kiểm lại hash ngay trước báo cáo và ngay trước ghi; lệch → dừng, không ghi (kênh thêm giữa chừng
        # sẽ bị ghi raw cũ với ngày hôm nay).
        ld = _kenh_doi(view_dir, bam)
        if ld:
            return ket_thuc(ld, kenh=kenh)
        bao_cao_loi = True
        if (view_dir / "bao_cao_view.py").is_file() and con_lai() > 0:
            kq = chay_buoc(lenh_bao_cao(view_dir), cwd, file_log_buoc(qv, ngay, lan, "bao-cao"),
                           min(HET_GIO_BAO_CAO_S, con_lai()))
            bao_cao_loi = kq.qua_gio or kq.ma != 0 or bool(kq.con_sot)
        if con_lai() <= 0:
            return ket_thuc("ghi_loi", kenh=kenh, bao_cao_loi=bao_cao_loi)
        ld = _kenh_doi(view_dir, bam)
        if ld:
            return ket_thuc(ld, kenh=kenh, bao_cao_loi=bao_cao_loi)
        file_ghi = file_log_buoc(qv, ngay, lan, "ghi")
        kq = chay_buoc(lenh_ghi(view_dir), cwd, file_ghi, min(HET_GIO_GHI_S, con_lai()))
        if kq.qua_gio or kq.ma != 0:
            return ket_thuc("ghi_loi", kenh=kenh, bao_cao_loi=bao_cao_loi)
        try:
            n = doc_dong_ghi_ok(file_ghi.read_bytes().decode("utf-8", "replace"), ngay)
        except OSError:
            n = None
        if n is None:
            return ket_thuc("ghi_loi", kenh=kenh, bao_cao_loi=bao_cao_loi)
        try:
            co = dem_dong_db(poster_db, ngay)
        except sqlite3.Error as e:
            _ghi_nhat_ky(qv, ngay, f"đếm DB lỗi ({type(e).__name__})")
            return ket_thuc("ghi_loi", kenh=kenh, bao_cao_loi=bao_cao_loi)
        if co < n:
            return ket_thuc("ghi_loi", kenh=kenh, bao_cao_loi=bao_cao_loi, so_dong_ghi=co)
        # 7.
        return ket_thuc("ok", kenh=kenh, so_dong_ghi=n, bao_cao_loi=bao_cao_loi)
    except Exception as e:
        log.exception("quet_view lỗi bất ngờ sau khi đã ghi trạng thái")
        _ghi_nhat_ky(qv, ngay, f"lỗi bất ngờ ({type(e).__name__})")
        return ket_thuc("loi_bat_ngo")


if __name__ == "__main__":
    sys.exit(chay())
