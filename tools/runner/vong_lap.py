"""Vòng chạy việc: 2 làn, mutex tài nguyên, khởi động lại (docs/bo-chay-viec.md §4.3–4.7, §5.1, §6.1–6.3).

Nguyên tắc:
- MỘT khoá chung `_khoa` bao trọn: tính tài nguyên bận → `nhan_viec_ke` → giữ tài nguyên (P3-4). Nhả tài
  nguyên cũng dưới khoá đó, luôn trong `finally` của `chay_mot`.
- Không chặn đầu hàng (P3-3): việc bị trả `dang_chay→cho` (điều kiện trước 'ban') làm LOẠI đó "tạm hoãn"
  `cho_lai_s` giây bằng một tài nguyên giả `~hoan:<loại>` đưa vào `tai_nguyen_ban` → `nhan_viec_ke` bỏ qua
  việc đó và nhận việc kế trong làn. Không sửa `kho_viec.py`. Theo loại (không theo id) vì mọi nguồn 'ban'
  của đợt 3 đều không phụ thuộc tham số (git kho bận, ffmpeg ngoài).
- Hạn mức Claude kiểm TRƯỚC khi nhận (P3-8): loại bị chặn nhận tài nguyên giả `~han:<loại>`; việc resume chưa
  bị đổi `bat_dau_luc` nên không tự đếm mình (trừ khi chính nó đã chạy Claude trong hôm nay — vẫn tính, an toàn chi phí).
- Mọi chuyển trạng thái đi qua `KhoViec.chuyen` (CAS). Việc đã bị đổi ngoài (huỷ từ web) → SaiTrangThai → bỏ qua.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import psutil

from . import stream_json as sj
from . import thuc_thi as tt
from .danh_muc import (DANH_MUC, LoaiViec, can_ban_douyin, con_tu_xu_ly_link, kiem_dau_ra_an_toan,
                       kiem_truoc_buoc, mp3_hong, phan_tich_poster, quyet_dinh_sau_khoi_dong)
from .du_an import RE_ME, gocs_tu_moi_truong, tim_du_an
from .han_muc import HAN_MUC_TRAN, kiem_han_muc
from .kho_viec import KhoViec
from .kieu import (DANG_MO, MUI_GIO_VN, BuocChay, CanNguoiDung, MoiTruong, SaiTrangThai, ThamSoLoi, TrungViec,
                   VuotHanMuc, gio_vn)
from .phieu import (anh_xa_ket_qua, lap_tin_chay_tiep, lap_tin_duyet, lap_tin_tiep, phan_tich_ket_qua)

log = logging.getLogger("kho_runner.vong_lap")

LAN = ("gpu", "nhe")
CHO_LAI_S = 60                     # §4.3 dang_chay→cho: thử lại sau 60 s
NGHI_S = 2.0                       # làn rảnh: chờ giữa 2 lần nhận
TAM_DUNG_CLAUDE_S = 30 * 60        # §6.3 hết quota / quá tải
GIU_FILE_NGAY = 30                 # §4.6 bước 3
LOG_TOI_DA = 64 * 1024             # §4.7 ≤ 64 KB mỗi lần đọc log
DONG_GIU_TOI_DA = 20000            # số dòng stdout giữ lại cho bước script (đọc link con / poster)
CHU_KY_CAN_BAN_S = 15              # §5.1 douyin: 15 s đọc log một lần
TIEN_TO_HOAN = "tạm hoãn: "        # ghi chú sự kiện dang_chay→cho; ly_do_tiep_tuc bỏ qua các sự kiện này
CANH_BAO_TOI_DA = 50               # R-07 P3-6: số mục tối đa của list canh_bao (/suc-khoe)
KIEM_SONG_S = 5.0                  # R-07 P2-4: chu kỳ kiểm pid không giết được đã chết chưa (để nhả làn/tài nguyên)
BUOC_BO_QUA_MA_THOAT = frozenset({"agy"})   # §5.1 douyin: agy thoát (kể cả mã ≠ 0) → bước kế tự kiểm file
LOAI_KHONG_DOI_SOAT_SCRIPT = frozenset({"xu_ly_link_moi", "poster_day_folder"})
RE_QUOTA = re.compile(r"(?i)usage limit|rate limit|\b429\b|overloaded")
RE_ID = re.compile(r"^j\d{14}[a-z0-9]{4}$", re.ASCII)

# Đường dẫn mặc định của máy nhà (§1, §5.1). Ghi đè bằng biến môi trường (test luôn ghi đè).
MAC_DINH = {
    "KHO_REPO": "E:/phantichcanhquay/kho-san-pham",
    "KHO_THU_MUC_SCRIPTS": "C:/Users/Mi/.claude/skills/tao-video-tu-canh-quay/scripts",
    "KHO_PYTHON_POSTER": "E:/tool/tiktok_poster_v2/.venv/Scripts/python.exe",
    "KHO_CLAUDE_EXE": r"C:\Users\Mi\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe",
    "KHO_AGY_EXE": "C:/Users/Mi/AppData/Local/agy/bin/agy.exe",
    "KHO_THU_MUC_RADAR": "E:/quet-kenh-anti",
    "KHO_THU_MUC_SP": "E:/phantichcanhquay",
}
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class CongCuNgoai(Exception):
    """Phiên Claude có công cụ ngoài danh sách cho phép (S-1: MCP người dùng lọt qua --tools)."""


# ================================================================ thư mục, mutex, tổng kiểm

THU_MUC_RUNNER_MAC_DINH = Path(r"E:\kho-runner")


def thu_muc_runner() -> Path:
    """Thư mục dữ liệu + bản cài của runner (§4.1): KHO_RUNNER_DIR nếu đặt (khác rỗng), ngược lại `E:\\kho-runner`.

    Không dùng %LOCALAPPDATA% nữa (FX-7): app Claude desktop chạy dạng MSIX nên mọi tiến trình con ghi vào
    %LOCALAPPDATA% bị Windows chuyển sang `…\\Packages\\Claude_…\\LocalCache\\Local\\…`; runner bật từ Startup
    (ngoài app) sẽ không thấy bản cài/khoá/DB. Ổ E không bị chuyển hướng. Hàm chỉ trả đường dẫn, không tạo thư mục.
    """
    g = os.environ.get("KHO_RUNNER_DIR")
    if g:
        return Path(g)
    return _thu_muc_mac_dinh()


def _thu_muc_mac_dinh() -> Path:
    return THU_MUC_RUNNER_MAC_DINH


def _chuan(p: Path) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def ten_mutex(thu_muc: Path) -> str:
    """Thư mục dữ liệu mặc định → `Local\\kho-runner` (§4.1). Thư mục khác (test) → tên riêng suy từ đường dẫn,
    để test không bao giờ đụng mutex của runner thật. runner.lock trong thư mục vẫn là lưới thứ hai."""
    if _chuan(thu_muc) == _chuan(_thu_muc_mac_dinh()):
        return tt.TEN_MUTEX
    return tt.TEN_MUTEX + "-" + hashlib.sha1(_chuan(thu_muc).encode("utf-8")).hexdigest()[:12]


def tinh_tong_kiem(thu_muc: Path) -> dict[str, str]:
    """sha256 mọi file trong thư mục cài (đường dẫn tương đối dạng posix), trừ TONG_KIEM.json và __pycache__."""
    thu_muc = Path(thu_muc)
    kq: dict[str, str] = {}
    for f in sorted(thu_muc.rglob("*")):
        if not f.is_file() or f.name == "TONG_KIEM.json" or "__pycache__" in f.parts:
            continue
        kq[f.relative_to(thu_muc).as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
    return kq


def kiem_tong(thu_muc: Path) -> list[str]:
    """§8.3: so file bản cài với TONG_KIEM.json. Trả danh sách cảnh báo (rỗng = khớp)."""
    f = Path(thu_muc) / "TONG_KIEM.json"
    try:
        ghi = json.loads(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ["không có TONG_KIEM.json — đang chạy từ mã nguồn hoặc bản cài thiếu tổng kiểm"]
    except (OSError, ValueError) as e:
        return [f"TONG_KIEM.json hỏng: {e}"]
    if not isinstance(ghi, dict):
        return ["TONG_KIEM.json không phải object"]
    that = tinh_tong_kiem(thu_muc)
    lech = sorted(k for k in set(ghi) | set(that) if ghi.get(k) != that.get(k))
    if lech:
        return [f"bản cài lệch tổng kiểm ({len(lech)} file): {', '.join(lech[:10])} — có thể bị sửa sau khi cài"]
    return []


# ================================================================ môi trường thật (MoiTruong)

def _chay_lenh(argv: list[str], cwd: str | None = None, timeout: int = 30) -> tuple[int, str, str]:
    """Chạy lệnh ngắn, dạng list, có timeout. Lỗi chạy → (-1, '', mô tả)."""
    try:
        r = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout, creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, "", f"{type(e).__name__}: {e}"
    return (r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace"))


def chan_doan_kho_tu(repo: Path, *, git_dang_chay: Callable[[], bool],
                     chay_git: Callable[[list[str]], tuple[int, str, str]],
                     bay_gio_ts: float) -> CanNguoiDung | str | None:
    """§4.4 chẩn đoán kho, 4 nhánh. None = sạch; 'ban' = đợi; CanNguoiDung = việc tay. Logic thuần (tiêm git)."""
    khoa = Path(repo) / ".git" / "index.lock"
    try:
        mtime = khoa.stat().st_mtime
    except FileNotFoundError:
        mtime = None
    except OSError as e:
        log.warning("không đọc được %s: %s — coi như git đang bận", khoa, e)
        return "ban"
    if mtime is not None:
        if git_dang_chay() or bay_gio_ts - mtime < 600:
            return "ban"
        return CanNguoiDung("viec_tay", (
            f"Có khoá git cũ `{khoa}` (lần chạy trước bị ngắt). Kiểm không có cửa sổ git nào rồi xoá file "
            "này, bấm Đã làm xong"))
    rc, out, err = chay_git(["symbolic-ref", "-q", "--short", "HEAD"])
    if rc != 0:
        chi_tiet = (err or out).strip()[:300] or "HEAD đang tách rời (detached)"
        return CanNguoiDung("viec_tay", f"Không đọc được nhánh của thư mục kho: {chi_tiet}. Chuyển về main")
    nhanh = out.strip()
    if nhanh != "main":
        return CanNguoiDung("viec_tay", f"Thư mục kho đang ở nhánh `{nhanh}`; chuyển về main")
    rc, out, err = chay_git(["status", "--porcelain", "--", "data"])
    if rc != 0:
        return CanNguoiDung("viec_tay", f"Không đọc được trạng thái git kho: {(err or out).strip()[:300]}")
    ban = [d[3:] if len(d) > 3 else d for d in out.splitlines() if d.strip()]
    if ban:
        return CanNguoiDung("viec_tay", "Dữ liệu kho có thay đổi chưa đẩy: " + ", ".join(ban[:10])
                            + (f" (+{len(ban) - 10})" if len(ban) > 10 else ""))
    return None


def _git_exe_dang_chay() -> bool:
    for p in psutil.process_iter(["name"]):
        if (p.info.get("name") or "").lower() in ("git.exe", "git"):
            return True
    return False


def chan_doan_kho(repo: Path) -> CanNguoiDung | str | None:
    def chay_git(args: list[str]) -> tuple[int, str, str]:
        return _chay_lenh(["git", "--no-optional-locks", "-c", "core.quotepath=false", "-C", str(repo), *args])
    return chan_doan_kho_tu(Path(repo), git_dang_chay=_git_exe_dang_chay, chay_git=chay_git,
                            bay_gio_ts=time.time())


def cong_song(cong: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(cong)), timeout=1):
            return True
    except OSError:
        return False


def thoi_luong_ffprobe(p: Path) -> float | None:
    rc, out, err = _chay_lenh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                               str(p)], timeout=60)
    if rc != 0:
        log.info("ffprobe %s mã %s: %s", p, rc, err.strip()[:300])
        return None
    try:
        return float(out.strip().splitlines()[0])
    except (ValueError, IndexError):
        return None


_RE_MA_VOICE = re.compile(r"^[A-Za-z0-9_-]{1,20}$", re.ASCII)


def _ds_ma_voice_tu(thu_muc_scripts: Path) -> Callable[[Path, str], list[str] | None]:
    def ds_ma(p: Path, me: str) -> list[str] | None:
        if not isinstance(me, str) or not RE_ME.fullmatch(me):
            return None
        rc, out, err = _chay_lenh(["python", (Path(thu_muc_scripts) / "trang_thai.py").as_posix(),
                                   "--project", Path(p).as_posix(), "--batch", me, "ma"], timeout=60)
        if rc != 0:
            log.warning("trang_thai.py ma lỗi mã %s: %s", rc, (err or out).strip()[:300])
            return None
        ma = out.split()
        if not ma or not all(_RE_MA_VOICE.fullmatch(m) for m in ma):
            return None
        return ma
    return ds_ma


def _bay_gio() -> datetime:
    return datetime.now(MUI_GIO_VN)


def tao_moi_truong() -> MoiTruong:
    """MoiTruong thật. Đường dẫn ghi đè được bằng biến môi trường KHO_* (xem MAC_DINH)."""
    def g(k: str) -> Path:
        return Path(os.environ.get(k) or MAC_DINH[k])
    pid_runner = os.getpid()
    scripts = g("KHO_THU_MUC_SCRIPTS")
    return MoiTruong(
        gocs=gocs_tu_moi_truong(), repo_kho=g("KHO_REPO"), thu_muc_scripts=scripts,
        python_poster=g("KHO_PYTHON_POSTER"), claude_exe=g("KHO_CLAUDE_EXE"), agy_exe=g("KHO_AGY_EXE"),
        thu_muc_radar=g("KHO_THU_MUC_RADAR"), thu_muc_sp=g("KHO_THU_MUC_SP"), thu_muc_du_lieu=thu_muc_runner(),
        cong_song=cong_song, chan_doan_kho=chan_doan_kho,
        ffmpeg_ngoai=lambda: tt.ffmpeg_ngoai({pid_runner}),
        thoi_luong_media=thoi_luong_ffprobe, bay_gio=_bay_gio, ds_ma_voice=_ds_ma_voice_tu(scripts))


# ================================================================ logic thuần

def ly_do_tiep_tuc(su_kien: list[dict]) -> tuple[str, str]:
    """Vì sao việc quay lại `cho` lần gần nhất: 'tra_loi' | 'duyet' | 'chay_tiep' | 'khoi_dong' | 'moi'.
    Bỏ qua sự kiện tạm hoãn (dang_chay→cho do điều kiện trước 'ban') để không làm mất câu trả lời."""
    for e in reversed(su_kien):
        if e.get("den") != "cho":
            continue
        ghi = e.get("ghi_chu") or ""
        if ghi.startswith(TIEN_TO_HOAN):
            continue
        tu = e.get("tu")
        if tu == "can_tra_loi":
            return "tra_loi", ghi
        if tu == "cho_duyet":
            return "duyet", ghi
        if tu == "loi":
            return "chay_tiep", ghi
        if tu == "dang_chay":
            return "khoi_dong", ghi
        return "moi", ghi
    return "moi", ""


def _cau_hoi_tu_tra_loi(tl: dict) -> CanNguoiDung:
    """Phòng khi việc không còn cau_hoi: suy loại câu hỏi từ giá trị nút đã lưu."""
    nd = tl.get("noi_dung") or ""
    if nd == "da_lam_xong":
        return CanNguoiDung("viec_tay", tl.get("cau_hoi") or "")
    if nd == "tiep_tuc":
        return CanNguoiDung("khong_ro", tl.get("cau_hoi") or "")
    return CanNguoiDung("chon", tl.get("cau_hoi") or "", (nd,))


def lap_tin_resume(viec: dict, su_kien: list[dict], tra_loi: list[dict]) -> str:
    """stdin cho lượt `--resume` (§6.4). ThamSoLoi nếu thiếu dữ liệu trả lời."""
    ly, ghi = ly_do_tiep_tuc(su_kien)
    if ly == "tra_loi":
        if not tra_loi:
            raise ThamSoLoi("việc vừa được trả lời nhưng không thấy câu trả lời trong DB")
        tl = tra_loi[-1]
        ch = viec.get("cau_hoi")
        cau_hoi = CanNguoiDung.tu_dict(ch) if isinstance(ch, dict) else _cau_hoi_tu_tra_loi(tl)
        return lap_tin_tiep(viec, cau_hoi, tl.get("noi_dung") or "")
    if ly == "duyet":
        return lap_tin_duyet(viec)
    if ly == "chay_tiep":
        return lap_tin_chay_tiep(viec, viec.get("loi") or "lỗi không rõ")
    if ly == "khoi_dong":
        return lap_tin_chay_tiep(viec, ghi or "bị ngắt khi máy tắt")
    return lap_tin_chay_tiep(viec, "phiên trước kết thúc mà không rõ lý do")


def _khong_che(s: str) -> str:
    return s


def _boot_time() -> float | None:
    """psutil.boot_time(); lỗi → None (không biết = không kết luận được gì)."""
    try:
        return float(psutil.boot_time())
    except (psutil.Error, OSError, ValueError) as e:
        log.warning("không đọc được thời điểm khởi động máy: %s", e)
        return None


def sinh_truoc_lan_bat_may(pid_tao_luc: float, boot: float | None) -> bool:
    """R-07 P3-5: tiến trình tạo TRƯỚC lần khởi động máy hiện tại (dung sai 1 s) → chắc chắn đã chết. Logic thuần."""
    return boot is not None and pid_tao_luc < boot - 1.0


def tien_trinh_con_song(pid: int, pid_tao_luc: float | None) -> bool:
    """Tiến trình `pid` (đúng lần tạo `pid_tao_luc`, lệch ≤1 s) còn sống? Không đọc được → coi là còn sống (an toàn)."""
    try:
        p = psutil.Process(int(pid))
        if pid_tao_luc is not None and abs(p.create_time() - float(pid_tao_luc)) > 1.0:
            return False                                     # PID đã bị tái dùng → gốc cũ đã chết
        return p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except psutil.Error as e:
        log.warning("không kiểm được pid %s còn sống không: %s — coi như còn sống", pid, e)
        return True


def phan_loai_ket_thuc_claude(kq: tt.KetQuaTienTrinh, tran_luot: int | None, het_gio_s: int,
                              che: Callable[[str], str] = _khong_che) -> tuple[str, dict, bool] | None:
    """Kết thúc bất thường của bước Claude → (trạng thái, trường, tạm_dừng_claude). None = đọc kết quả bình thường.
    `che` áp lên văn bản ĐẦY ĐỦ trước khi cắt (R-06 P3-1); RE_QUOTA vẫn soát bản gốc."""
    if kq.bi_huy:
        return "huy", {}, False
    if kq.het_gio:
        return "loi", {"loi": f"Quá giờ {het_gio_s // 60} phút — Claude bị dừng cả cây"}, False
    if kq.vuot_luot:
        return "can_tra_loi", {"cau_hoi": CanNguoiDung(
            "khong_ro", f"Đã chạm trần {tran_luot} lượt — bấm Tiếp tục để chạy thêm hoặc Huỷ")}, False
    k = kq.ket_qua
    vb = (k or {}).get("van_ban") or kq.van_ban_cuoi or ""
    if k is None:
        tam = bool(RE_QUOTA.search(vb))
        return "loi", {"loi": f"Claude thoát mã {kq.ma_thoat} mà không có sự kiện kết quả: {che(vb)[-500:]}".strip()}, tam
    if k.get("loi") or kq.ma_thoat not in (0, None):
        tam = bool(RE_QUOTA.search(vb))
        tien_to = "Hết quota/quá tải — tạm dừng việc Claude 30 phút. " if tam else ""
        return "loi", {"loi": f"{tien_to}Claude báo lỗi (mã {kq.ma_thoat}): {che(vb)[:800]}".strip()}, tam
    return None


BI_TU_CHOI_TOI_DA = 20             # R-05 P2-2: số mục permission_denials giữ trong ket_qua
BI_TU_CHOI_INPUT_TOI_DA = 200      # ký tự input (đã che) mỗi mục
_TEN_CONG_CU_TOI_DA = 100


def gon_bi_tu_choi(ds, che: Callable[[str], str]) -> list[dict]:
    """permission_denials thô → [{tool_name, input}] (input = JSON đã che bí mật, ≤200 ký tự), tối đa 20 mục.
    Logic thuần: không giữ tool_use_id hay trường lạ nào của dữ liệu thô."""
    if not isinstance(ds, list):
        return []
    ra = []
    for m in ds[:BI_TU_CHOI_TOI_DA]:
        ten = m.get("tool_name") if isinstance(m, dict) else None
        ten = che(ten)[:_TEN_CONG_CU_TOI_DA] if isinstance(ten, str) and ten else "?"
        inp = m.get("tool_input") if isinstance(m, dict) else m
        try:
            s = json.dumps(inp, ensure_ascii=False)
        except (TypeError, ValueError):
            s = repr(inp)
        ra.append({"tool_name": ten, "input": che(s)[:BI_TU_CHOI_INPUT_TOI_DA]})
    return ra


def che_truong_ket_thuc(truong: dict, che: Callable[[str], str]) -> dict:
    """R-05 P2-2: che bí mật các trường đi ra web khi kết thúc bước Claude: `loi`, `cau_hoi.noi_dung`,
    từng `cau_hoi.lua_chon`. Trả dict mới (không sửa đầu vào)."""
    ra = dict(truong)
    if isinstance(ra.get("loi"), str):
        ra["loi"] = che(ra["loi"])
    ch = ra.get("cau_hoi")
    if isinstance(ch, dict):
        ch = CanNguoiDung.tu_dict(ch)
    if isinstance(ch, CanNguoiDung):
        ra["cau_hoi"] = CanNguoiDung(ch.loai, che(ch.noi_dung), tuple(che(x) for x in ch.lua_chon))
    return ra


def cat_bien_utf8(b: bytes, day: bool) -> bytes:
    """Cắt đoạn log đọc được: đầy khung → cắt ở cuối dòng; luôn không để dở ký tự UTF-8 ở cuối."""
    if day:
        i = b.rfind(b"\n")
        if i >= 0:
            return b[:i + 1]
    for k in range(1, min(4, len(b)) + 1):
        c = b[-k]
        if c & 0xC0 == 0x80:            # byte tiếp nối → lùi tiếp
            continue
        can = 2 if c & 0xE0 == 0xC0 else 3 if c & 0xF0 == 0xE0 else 4 if c & 0xF8 == 0xF0 else 1
        return b[:-k] if can > k else b
    return b


# ================================================================ BoChay

class BoChay:
    def __init__(self, kho: KhoViec, mt: MoiTruong, hm: dict, thu_muc_log: Path, che: Callable[[str], str], *,
                 danh_muc: dict[str, LoaiViec] | None = None, cho_lai_s: float = CHO_LAI_S,
                 nghi_s: float = NGHI_S, tam_dung_claude_s: float = TAM_DUNG_CLAUDE_S,
                 canh_bao: list[str] | None = None, kiem_song_s: float = KIEM_SONG_S):
        self.kho = kho
        self.mt = mt
        self.hm = hm
        self.thu_muc_log = Path(thu_muc_log)
        self.thu_muc_log.mkdir(parents=True, exist_ok=True)
        self.che = che
        # R-06 P3-5: cùng list `canh_bao` mà api đọc cho /suc-khoe (chay_runner truyền vào); append là nguyên tử
        self.canh_bao: list[str] = canh_bao if canh_bao is not None else []
        # R-07 P3-6: list dùng chung với api → chỉ sửa TẠI CHỖ (append/del/remove), dưới khoá riêng. Các mục có sẵn
        # lúc tạo (cảnh báo khởi động: Job Object, tổng kiểm…) không bị cắt khi vượt CANH_BAO_TOI_DA.
        self._khoa_canh_bao = threading.Lock()
        self._canh_bao_goc = len(self.canh_bao)
        self._canh_bao_pid: dict[int, str] = {}              # pid không giết được → mục cảnh báo của nó
        self._dm = DANH_MUC if danh_muc is None else danh_muc
        tran = int(HAN_MUC_TRAN["dot_bat"])
        v = hm.get("dot_bat", tran) if isinstance(hm, dict) else tran
        self._dot_bat = int(min(v, tran)) if isinstance(v, (int, float)) and not isinstance(v, bool) else tran
        self.cho_lai_s = cho_lai_s
        self.nghi_s = nghi_s
        self.tam_dung_claude_s = tam_dung_claude_s
        self._khoa = threading.Lock()                       # P3-4: MỘT khoá cho tính bận → nhận → giữ
        self._tn_giu: dict[str, str] = {}                   # tài nguyên → id việc đang giữ
        self._lan_dang: dict[str, str | None] = {l: None for l in LAN}
        self._lan_loai: dict[str, str | None] = {l: None for l in LAN}    # loại việc đang chạy ở làn (P3-2)
        self._hoan: dict[str, float] = {}                   # loại → hạn (monotonic) tạm hoãn
        self._tam_dung_den: datetime | None = None
        self._huy: dict[str, threading.Event] = {}
        self._huy_that: set[str] = set()                    # id bị huỷ từ web (khác với tắt runner)
        self._dung = threading.Event()
        self._luong: list[threading.Thread] = []
        # R-07 P2-4: việc có tiến trình không giết được → (pid, pid_tao_luc). Làn + tài nguyên của việc đó KHÔNG được
        # nhả ở _nha; _kiem_con_song nhả khi pid gốc đã chết (kiểm định kỳ trong nhan_viec).
        self._con_song: dict[str, tuple[int, float | None]] = {}
        self.kiem_song_s = kiem_song_s
        self._kiem_song_luc = float("-inf")

    # ---------------------------------------------------------------- tiện ích
    def _loai(self, ma: str) -> LoaiViec:
        loai = self._dm.get(ma) if isinstance(ma, str) else None
        if loai is None:
            raise ThamSoLoi(f"loại việc không có trong danh mục: {ma!r}")
        if loai.dot > self._dot_bat:
            raise ThamSoLoi(f"loại {ma} thuộc đợt {loai.dot}, chưa mở (đợt đang bật {self._dot_bat})")
        return loai

    def _bay_gio(self) -> datetime:
        return gio_vn(self.mt.bay_gio())

    def _ket_thuc(self, id: str, den: str, ghi_chu: str, **truong) -> dict | None:
        """dang_chay → den (CAS). Việc đã bị đổi ngoài (vd huỷ từ web) → log, trả None.
        R-06 P3-1: lưới cuối — che `ghi_chu`, `loi`, `cau_hoi` (mọi chuỗi đi ra web). Bên gọi cắt chuỗi thì
        PHẢI che bản đầy đủ trước khi cắt (che ở đây không cứu được bí mật đã bị cắt dở)."""
        ghi_chu = self.che(ghi_chu)
        truong = che_truong_ket_thuc(truong, self.che)
        truong.setdefault("pid", None)
        truong.setdefault("pid_tao_luc", None)
        try:
            return self.kho.chuyen(id, ["dang_chay"], den, "he_thong", ghi_chu, **truong)
        except SaiTrangThai as e:
            log.info("việc %s không còn dang_chay khi định chuyển sang %s: %s", id, den, e)
            return None

    def _ghi_log(self, id: str, s: str) -> None:
        try:
            with open(self.thu_muc_log / f"{id}.log", "a", encoding="utf-8", newline="\n") as f:
                f.write(f"[runner {datetime.now():%Y-%m-%d %H:%M:%S}] {s}\n")
        except OSError as e:
            log.error("không ghi được log việc %s: %s", id, e)

    def _ly_do_chan_claude(self) -> str | None:
        if self._tam_dung_den is not None and self._bay_gio() < self._tam_dung_den:
            return f"tạm dừng việc Claude tới {self._tam_dung_den.isoformat(timespec='seconds')}"
        return None

    # ---------------------------------------------------------------- nhận việc (P3-3, P3-4, P3-8)
    def _tai_nguyen_cua(self, ma: str) -> frozenset[str]:
        loai = self._loai(ma)                        # loại lạ/đợt chưa mở → nhan_viec_ke bỏ qua việc đó
        return frozenset(loai.tai_nguyen) | {f"~hoan:{ma}", f"~han:{ma}"}

    def _ban_hien_tai(self, lan: str) -> set[str]:
        """Gọi khi ĐANG giữ self._khoa."""
        bay = time.monotonic()
        self._hoan = {k: v for k, v in self._hoan.items() if v > bay}
        ban = set(self._tn_giu) | {f"~hoan:{ma}" for ma in self._hoan}
        chan = self._ly_do_chan_claude()
        for ma, loai in self._dm.items():
            if not loai.agent or loai.lan_chay != lan:
                continue
            if chan:
                ban.add(f"~han:{ma}")
                continue
            try:
                kiem_han_muc(self.kho, ma, {}, self.hm, "nhan", "he_thong")   # P3-8: TRƯỚC khi nhận
            except VuotHanMuc as e:
                log.info("làn %s: loại %s đứng chờ — %s", lan, ma, e)
                ban.add(f"~han:{ma}")
            except ThamSoLoi as e:
                log.error("không kiểm được hạn mức loại %s (%s) — chặn loại này", ma, e)
                ban.add(f"~han:{ma}")
        return ban

    def nhan_viec(self, lan: str) -> dict | None:
        """Nhận việc kế của làn và giữ tài nguyên của nó (MỞ RỘNG ngoài §13: dùng cho vòng làn và test).
        Bên gọi PHẢI gọi chay_mot(viec) sau đó (chay_mot luôn nhả tài nguyên)."""
        if lan not in LAN:
            raise ThamSoLoi(f"làn lạ: {lan!r}")
        with self._khoa:
            self._kiem_con_song()                   # R-07 P2-4: TRƯỚC khi xét làn bận (làn có thể đang bị giữ)
            if self._dung.is_set() or self._lan_dang[lan] is not None:
                return None
            ban = self._ban_hien_tai(lan)
            viec = self.kho.nhan_viec_ke(lan, ban, self._tai_nguyen_cua)
            if viec is None:
                return None
            loai = self._loai(viec["loai"])
            trung = set(loai.tai_nguyen) & set(self._tn_giu)
            if trung:      # không thể xảy ra khi mọi nhận việc đi qua khoá này — vẫn chặn cho chắc
                log.error("việc %s nhận trúng tài nguyên đang bận %s — trả về cho", viec["id"], trung)
                self.kho.chuyen(viec["id"], ["dang_chay"], "cho", "he_thong", TIEN_TO_HOAN + "tài nguyên bận")
                return None
            for tn in loai.tai_nguyen:
                self._tn_giu[tn] = viec["id"]
            self._lan_dang[lan] = viec["id"]
            self._lan_loai[lan] = viec["loai"]
            self._huy[viec["id"]] = threading.Event()
            return viec

    def _nha(self, id: str, lan: str | None) -> None:
        with self._khoa:
            if id not in self._con_song:            # R-07 P2-4: tiến trình còn sống → giữ làn + tài nguyên
                self._nha_lan_tai_nguyen(id)
            self._huy.pop(id, None)
            self._huy_that.discard(id)

    def _nha_lan_tai_nguyen(self, id: str) -> None:
        """Gọi khi ĐANG giữ self._khoa."""
        for tn in [k for k, v in self._tn_giu.items() if v == id]:
            del self._tn_giu[tn]
        for l in LAN:
            if self._lan_dang[l] == id:
                self._lan_dang[l] = None
                self._lan_loai[l] = None

    def _kiem_con_song(self) -> None:
        """R-07 P2-4: pid không giết được đã chết → nhả làn + tài nguyên của việc đó, xoá cảnh báo (P3-6).
        Gọi khi ĐANG giữ self._khoa; tối đa một lần mỗi `kiem_song_s` giây."""
        if not self._con_song:
            return
        bay = time.monotonic()
        if bay - self._kiem_song_luc < self.kiem_song_s:
            return
        self._kiem_song_luc = bay
        for id, (pid, tl) in list(self._con_song.items()):
            if tien_trinh_con_song(pid, tl):
                continue
            del self._con_song[id]
            if id not in self._huy:                 # chay_mot của việc đã xong (nếu chưa, _nha của nó sẽ nhả)
                self._nha_lan_tai_nguyen(id)
            self._bo_canh_bao_pid(pid)
            log.warning("việc %s: tiến trình pid %s không giết được trước đó nay đã chết — nhả làn/tài nguyên", id, pid)
            self._ghi_log(id, f"tiến trình pid {pid} (không giết được trước đó) nay đã chết — nhả làn/tài nguyên")

    # ---------------------------------------------------------------- cảnh báo (/suc-khoe)
    def _them_canh_bao(self, c: str, pid: int | None = None) -> None:
        """R-07 P3-6: thêm cảnh báo — bỏ trùng, tối đa CANH_BAO_TOI_DA mục (cắt mục runtime cũ nhất, giữ mục khởi
        động). `pid` khác None → cảnh báo bị xoá khi pid đó chết (_bo_canh_bao_pid)."""
        with self._khoa_canh_bao:
            if pid is not None:
                self._canh_bao_pid[int(pid)] = c
            if c in self.canh_bao:
                return
            self.canh_bao.append(c)
            while len(self.canh_bao) > CANH_BAO_TOI_DA and len(self.canh_bao) > self._canh_bao_goc + 1:
                del self.canh_bao[self._canh_bao_goc]

    def _bo_canh_bao_pid(self, pid: int) -> None:
        with self._khoa_canh_bao:
            c = self._canh_bao_pid.pop(int(pid), None)
            if c is not None and c in self.canh_bao:
                self.canh_bao.remove(c)

    def _hoan_loai(self, ma: str) -> None:
        with self._khoa:
            self._hoan[ma] = time.monotonic() + self.cho_lai_s

    def _tam_dung_claude(self) -> None:
        with self._khoa:
            self._tam_dung_den = self._bay_gio() + timedelta(seconds=self.tam_dung_claude_s)
        log.warning("tạm dừng mọi việc Claude tới %s", self._tam_dung_den)

    # ---------------------------------------------------------------- API cho api.py / chay_runner
    def bao_huy(self, id: str) -> None:
        with self._khoa:
            ev = self._huy.get(id)
            if ev is not None:
                self._huy_that.add(id)
                ev.set()

    def trang_thai_lan(self) -> dict:
        """`lan`: {gpu|nhe: {id, loai} khi đang chạy, None khi rảnh} (R-05 P3-2)."""
        with self._khoa:
            bay = time.monotonic()
            return {"lan": {l: ({"id": self._lan_dang[l], "loai": self._lan_loai[l]}
                                if self._lan_dang[l] is not None else None) for l in LAN},
                    "tai_nguyen": {"kho": self._tn_giu.get("kho"), "poster": self._tn_giu.get("poster")},
                    "tam_dung_claude_den": (self._tam_dung_den.isoformat(timespec="seconds")
                                            if self._tam_dung_den and self._bay_gio() < self._tam_dung_den
                                            else None),
                    "tam_hoan": {k: round(v - bay) for k, v in self._hoan.items() if v > bay},
                    # R-07 P2-4: việc → pid không giết được (làn/tài nguyên của việc đó đang bị giữ)
                    "con_song": {k: v[0] for k, v in self._con_song.items()}}

    def doc_log(self, id: str, tu: int) -> dict:
        """§4.7/§8.1: ≤64 KB từ offset byte `tu`, đã che bí mật."""
        if not isinstance(id, str) or not RE_ID.fullmatch(id):
            raise ThamSoLoi("id việc sai định dạng")
        # R-06 P2-1: đọc trạng thái TRƯỚC, cỡ file SAU. Việc đã sang huy/xong… nhưng runner còn đang ghi đuôi log
        # (giết cây, "kết thúc: mã …") → chưa het. het chỉ khi việc không mở VÀ runner không còn giữ id.
        v = self.kho.lay(id)
        with self._khoa:
            # R-07 P2-4: làn bị giữ vì tiến trình không giết được thì runner KHÔNG còn ghi log việc đó
            runner_giu = id in self._huy or (id in self._lan_dang.values() and id not in self._con_song)
        dang_ghi = runner_giu or (v is not None and v["trang_thai"] in DANG_MO)
        p = self.thu_muc_log / f"{id}.log"
        try:
            co = p.stat().st_size
        except FileNotFoundError:
            co = 0
        tu = max(0, int(tu))
        if tu > co:
            tu = co
        b = b""
        if co > tu:
            with open(p, "rb") as f:
                f.seek(tu)
                b = f.read(LOG_TOI_DA)
            if len(b) >= LOG_TOI_DA:
                b = cat_bien_utf8(b, True)
            elif dang_ghi and not b.endswith(b"\n"):
                # R-06 P3-1: log còn đang ghi → chỉ trả dòng đã trọn; dòng dở (có thể đang chứa nửa bí mật) để lượt
                # sau đọc trọn rồi mới che, tránh bí mật bị cắt đôi qua 2 lượt đọc.
                i = b.rfind(b"\n")
                b = b[:i + 1] if i >= 0 else b""
            else:
                b = cat_bien_utf8(b, False)
        den = tu + len(b)
        het = den >= co and not dang_ghi
        return {"tu": tu, "den": den, "noi_dung": self.che(b.decode("utf-8", "replace")), "het": het}

    # ---------------------------------------------------------------- khởi động lại (§4.6)
    def khoi_dong(self) -> dict:
        """Bước 4 của main(): chỉ gọi khi ĐÃ giành được khoá đơn instance."""
        kq: dict = {"giet": [], "con_song": [], "doi_soat": {}, "loai_la": [], "xoa_file": 0}
        for v in self.kho.ds(["dang_chay"], gioi_han=500):
            id = v["id"]
            pid, tl = v.get("pid"), v.get("pid_tao_luc")
            con_song: str | None = None          # R-05 P2-3: khác None = tiến trình cũ có thể còn sống
            if pid and tl is not None and sinh_truoc_lan_bat_may(float(tl), _boot_time()):
                # R-07 P3-5: tiến trình sinh trước lần bật máy này → cả cây chắc chắn đã chết; không đụng pid (đã có
                # thể bị tái dùng), đối soát bình thường.
                log.info("việc %s: pid %s sinh trước lần khởi động máy hiện tại — cây cũ đã chết", id, pid)
            elif pid and tl is not None:
                goc_khong_con = False            # R-07 P2-1: gốc cũ đã chết (NoSuchProcess) HOẶC PID đã bị tái dùng
                try:
                    p = psutil.Process(int(pid))
                    if abs(p.create_time() - float(tl)) <= 1.0:
                        if tt.giet_cay(int(pid), float(tl)):
                            kq["giet"].append(int(pid))
                        else:
                            con_song = f"Tiến trình cũ (pid {pid}) còn sống sau khi giết cả cây"
                    else:
                        log.info("việc %s: pid %s đã bị tái dùng — không đụng (gốc cũ đã chết)", id, pid)
                        goc_khong_con = True
                except psutil.NoSuchProcess:
                    goc_khong_con = True
                except psutil.Error as e:
                    log.error("việc %s: không kiểm được pid %s: %s", id, pid, e)
                    con_song = f"Không kiểm được tiến trình cũ (pid {pid}: {type(e).__name__})"
                if goc_khong_con and not tt.da_gan_job_object():
                    # R-06 P3-6 / R-07 P2-1: mất gốc thì không dò được cháu; không có Job Object runner
                    # (KILL_ON_JOB_CLOSE) thì cháu mồ côi có thể vẫn chạy → không tự về cho, chuyển loi kiểm tay.
                    con_song = (f"Tiến trình gốc (pid {pid}) không còn (đã chết hoặc PID đã bị tái dùng) nhưng runner "
                                "không có Job Object — tiến trình cháu mồ côi có thể còn sống")
            if con_song is not None:
                # không về cho: chạy lại khi bản cũ còn sống = trùng GPU/file. Không đối soát, không đổi tên mp3.
                kq["con_song"].append(int(pid))
                log.error("việc %s: %s — chuyển loi, không tự chạy lại", id, con_song)
                self._ghi_log(id, f"khởi động lại: {con_song} — chuyển loi, kiểm tay")
                self._ket_thuc(id, "loi", "khởi động lại: tiến trình cũ còn sống", loi=(
                    f"{con_song} — tiến trình cũ còn sống, kiểm tay trên máy (Task Manager) rồi mới "
                    "Chạy tiếp/Chạy lại"))
                continue
            try:
                loai = self._loai(v["loai"])
            except ThamSoLoi as e:
                kq["loai_la"].append(id)
                self._ket_thuc(id, "loi", "khởi động lại: loại không chạy được", loi=str(e))
                continue
            self._doi_ten_mp3_hong(loai, v)
            dau_ra = kiem_dau_ra_an_toan(loai, v.get("tham_so") or {}, v, self.mt)
            den, ghi = quyet_dinh_sau_khoi_dong(v, dau_ra, loai)
            truong: dict = {}
            if den == "cho":
                truong["lan_thu"] = int(v.get("lan_thu") or 1) + 1
            elif den == "loi":
                truong["loi"] = ghi
            elif den == "xong":
                truong["ket_qua"] = {"trang_thai_agent": None, "co_lo_ngai": dau_ra == "xong_lo_ngai",
                                     "tom_tat": ghi, "file_ra": [], "goi_y_viec": []}
            self._ket_thuc(id, den, ghi, **truong)
            kq["doi_soat"][id] = [dau_ra, den]
        for v in self.kho.ds(["cho"], gioi_han=500):
            try:
                self._loai(v["loai"])
            except ThamSoLoi as e:
                kq["loai_la"].append(v["id"])
                try:
                    self.kho.chuyen(v["id"], ["cho"], "loi", "he_thong", "khởi động lại: loại không chạy được",
                                    loi=str(e))
                except SaiTrangThai as e2:
                    log.debug("việc %s đã đổi trạng thái ngoài trước khi đánh dấu loại lạ: %s", v["id"], e2)
        kq["xoa_file"] = self._don_file_cu()
        self.kho.don_cu(self._bay_gio() - timedelta(days=1))
        return kq

    def _don_file_cu(self) -> int:
        moc = time.time() - GIU_FILE_NGAY * 86400
        n = 0
        ds = [(self.thu_muc_log, ("*.log", "*.jsonl")), (Path(self.mt.thu_muc_du_lieu) / "radar", ("*.json",))]
        for thu, mau in ds:
            if not thu.is_dir():
                continue
            for m in mau:
                for f in thu.glob(m):
                    try:
                        if f.is_file() and f.stat().st_mtime < moc:
                            f.unlink()
                            n += 1
                    except OSError as e:
                        log.warning("không xoá được file cũ %s: %s", f, e)
        return n

    def _doi_ten_mp3_hong(self, loai: LoaiViec, viec: dict) -> list[Path]:
        """P2-7: voice_pv bị ngắt → đổi tên mp3 hỏng sinh trong lần chạy thành <tên>.hong-<id> (hoàn tác được)."""
        if loai.ma != "voice_pv" or not viec.get("bat_dau_luc"):
            return []
        ts = viec.get("tham_so") or {}
        try:
            p = tim_du_an(ts.get("du_an"), ts.get("uid"), self.mt.gocs)
            if p is None:
                return []
            hong = mp3_hong(p, ts.get("me"), datetime.fromisoformat(viec["bat_dau_luc"]), self.mt)
        except (ThamSoLoi, ValueError) as e:
            log.warning("việc %s: không dò được mp3 hỏng: %s", viec["id"], e)
            return []
        da_doi = []
        for f in hong:
            moi = f.with_name(f"{f.name}.hong-{viec['id']}")
            try:
                f.rename(moi)
                da_doi.append(moi)
                self._ghi_log(viec["id"], f"đổi tên mp3 hỏng {f.name} → {moi.name}")
            except OSError as e:
                log.error("không đổi tên được %s: %s", f, e)
        return da_doi

    # ---------------------------------------------------------------- làn
    def bat_lan(self) -> None:
        for lan in LAN:
            t = threading.Thread(target=self._vong, args=(lan,), name=f"lan-{lan}", daemon=True)
            t.start()
            self._luong.append(t)

    def dung(self, cho_s: float = 15) -> None:
        """Tắt runner: không nhận việc mới; giết tiến trình đang chạy nhưng KHÔNG đổi trạng thái việc
        (lần khởi động sau đối soát, §4.6)."""
        self._dung.set()
        with self._khoa:
            for ev in self._huy.values():
                ev.set()
        for t in self._luong:
            t.join(timeout=cho_s)

    def _vong(self, lan: str) -> None:
        while not self._dung.is_set():
            try:
                viec = self.nhan_viec(lan)
            except Exception:  # noqa: BLE001 — làn không được chết vì lỗi DB tạm thời
                log.exception("làn %s: lỗi khi nhận việc", lan)
                self._dung.wait(self.nghi_s * 5)
                continue
            if viec is None:
                self._dung.wait(self.nghi_s)
                continue
            self.chay_mot(viec)

    # ---------------------------------------------------------------- chạy một việc
    def chay_mot(self, viec: dict) -> None:
        """Chạy trọn một việc đã ở dang_chay. Không bao giờ ném lỗi; luôn nhả tài nguyên."""
        id = viec["id"]
        with self._khoa:
            huy = self._huy.setdefault(id, threading.Event())
        try:
            self._chay(viec, huy)
        except Exception as e:  # noqa: BLE001
            log.exception("việc %s: lỗi bộ chạy việc", id)
            self._ghi_log(id, f"lỗi bộ chạy việc: {type(e).__name__}: {e}")
            try:
                if not self._khong_giet_tu_loi(id, e):
                    self._ket_thuc(id, "loi", "lỗi bộ chạy việc",
                                   loi=self.che(f"Lỗi bộ chạy việc: {type(e).__name__}: {e}")[:800])
            except Exception:  # noqa: BLE001
                log.exception("việc %s: không ghi được trạng thái loi", id)
        finally:
            self._nha(id, viec.get("lan_chay"))           # giữ làn/tài nguyên nếu tiến trình còn sống (P2-4)

    # ---------------------------------------------------------------- không giết được (R-06 P3-5, R-07 P2-4/P3-1)
    def _khong_giet(self, id: str, pid: int | None, tl: float | None, boi_canh: str) -> None:
        """Tiến trình của việc không giết được: GIỮ làn + tài nguyên tới khi pid chết (_kiem_con_song), cảnh báo lên
        /suc-khoe + log việc, chuyển việc dang_chay → loi "tiến trình còn sống — kiểm tay" và đánh dấu
        `ket_qua.khong_giet_duoc` (api chặn Chạy tiếp). Việc đã huỷ từ web giữ nguyên huy (CAS thất bại, đã log)."""
        if pid:
            with self._khoa:
                self._con_song[id] = (int(pid), tl)
        c = (f"Việc {id}: không giết được tiến trình (pid {pid}) {boi_canh} — có thể còn chạy, kiểm tay trên máy "
             "(Task Manager); làn/tài nguyên của việc được giữ tới khi tiến trình chết")
        log.error("%s", c)
        self._ghi_log(id, "CẢNH BÁO: " + c)
        self._them_canh_bao(c, pid)
        ht = self.kho.lay(id) or {}
        kq = dict(ht["ket_qua"]) if isinstance(ht.get("ket_qua"), dict) else {}
        kq.update({"khong_giet_duoc": True, "pid": pid, "pid_tao_luc": tl})
        self._ket_thuc(id, "loi", "tiến trình còn sống — kiểm tay", ket_qua=kq, loi=(
            f"Không giết được tiến trình (pid {pid}) {boi_canh} — tiến trình còn sống, kiểm tay trên máy (Task "
            "Manager). Không Chạy tiếp được; kiểm xong thì dùng Chạy lại"))

    def _bao_khong_giet(self, id: str, kq: tt.KetQuaTienTrinh, boi_canh: str) -> bool:
        """True nếu thuc_thi báo không giết được (đã xử lý qua _khong_giet — bên gọi dừng việc)."""
        if not getattr(kq, "khong_giet_duoc", False):
            return False
        self._khong_giet(id, kq.pid, getattr(kq, "pid_tao_luc", None), boi_canh)
        return True

    def _khong_giet_tu_loi(self, id: str, e: BaseException) -> bool:
        """R-07 P3-1: ngoại lệ từ chay_tien_trinh mang cờ không giết được → xử lý như P2-4. True = đã xử lý."""
        v = tt.khong_giet_tu_loi(e)
        if v is None:
            return False
        self._khong_giet(id, v[0], v[1], f"khi dọn sau lỗi {type(e).__name__}")
        return True

    def _xu_ly_dung(self, id: str, loai: LoaiViec, viec: dict, ly_do: str) -> None:
        """Tiến trình bị giết vì huỷ (web) hoặc vì tắt runner."""
        self._doi_ten_mp3_hong(loai, viec)
        with self._khoa:
            huy_that = id in self._huy_that
        if huy_that or not self._dung.is_set():
            self._ket_thuc(id, "huy", ly_do)
        else:
            self._ghi_log(id, "runner tắt giữa chừng — để dang_chay cho lần khởi động sau đối soát")

    def _chay(self, viec: dict, huy: threading.Event) -> None:
        id = viec["id"]
        ts = viec.get("tham_so") or {}
        try:
            loai = self._loai(viec["loai"])
        except ThamSoLoi as e:
            self._ket_thuc(id, "loi", "loại không chạy được", loi=str(e))
            return
        self._ghi_log(id, f"lần {viec.get('lan_thu')}: bắt đầu {loai.ma}")

        dk = loai.dieu_kien_truoc(ts, self.mt)
        if dk == "ban":
            ly = ("git kho đang bận (có thể bạn đang chạy kho.py tay)" if "kho" in loai.tai_nguyen
                  else "tài nguyên đang bận (vd ffmpeg ngoài runner đang dùng GPU)")
            self._hoan_loai(loai.ma)
            self._ghi_log(id, f"{ly} — thử lại sau {int(self.cho_lai_s)} s")
            self._ket_thuc(id, "cho", TIEN_TO_HOAN + ly + f" — thử lại sau {int(self.cho_lai_s)} s",
                           pid=None, pid_tao_luc=None)
            return
        if isinstance(dk, CanNguoiDung):
            self._ket_thuc(id, "can_tra_loi", "điều kiện trước chưa đạt", cau_hoi=dk)
            return
        if dk is not None:
            self._ket_thuc(id, "loi", "điều kiện trước trả giá trị lạ", loi=f"điều kiện trước lạ: {dk!r}")
            return

        try:
            ds_buoc = loai.lap_buoc(ts, viec, self.mt)
        except ThamSoLoi as e:
            self._ket_thuc(id, "loi", "không lập được các bước", loi=f"Không lập được lệnh: {e}")
            return

        lo_ngai: list[str] = []
        them_kq: dict = {}
        kq_claude: dict | None = None
        dong_cuoi = ""
        for i, b in enumerate(ds_buoc):
            la_cuoi = i == len(ds_buoc) - 1
            if huy.is_set():
                self._xu_ly_dung(id, loai, viec, "huỷ trước bước " + b.ten)
                return
            ht = self.kho.lay(id)
            if ht is None or ht["trang_thai"] != "dang_chay":
                log.info("việc %s không còn dang_chay trước bước %s — dừng", id, b.ten)
                return
            cnd = kiem_truoc_buoc(loai, b.ten, ts, ht, self.mt)
            if cnd is not None:
                self._ket_thuc(id, "can_tra_loi", f"trước bước {b.ten}", cau_hoi=cnd)
                return
            if b.la_claude:
                kq_claude = self._buoc_claude(loai, ht, b, huy, la_cuoi)
                if kq_claude is None:
                    return                          # đã chuyển trạng thái
                continue
            ok, dong = self._buoc_script(loai, ht, b, huy)
            if not ok:
                return
            dong_cuoi = "\n".join(dong[-40:])
            if b.ten in ("poster_xem", "poster_day"):
                ket, co_ln = phan_tich_poster("\n".join(dong), b.ten == "poster_xem")
                if ket == "loi":
                    self._ket_thuc(id, "loi", f"Poster báo lỗi ở bước {b.ten}",
                                   loi=f"Poster báo lỗi ở bước {b.ten}: {self.che(dong_cuoi)[-800:]}")
                    return
                if co_ln:
                    lo_ngai.append("Poster có [CẢNH BÁO] — xem log")
            elif b.ten == "kho_cho":
                them_kq.update(self._tao_con_link(viec, "\n".join(dong)))

        if kq_claude is not None:
            ket_qua = dict(kq_claude)
        else:
            dau_ra = kiem_dau_ra_an_toan(loai, ts, self.kho.lay(id) or viec, self.mt)
            if loai.ma not in LOAI_KHONG_DOI_SOAT_SCRIPT and dau_ra in ("chua", "xong_lo_ngai"):
                lo_ngai.append("chưa thấy đủ đầu ra sau khi chạy" if dau_ra == "chua"
                               else "đầu ra chính đã có nhưng còn thiếu phần phụ")
            ket_qua = {"trang_thai_agent": None, "co_lo_ngai": False, "tom_tat": self.che(dong_cuoi)[-1500:],
                       "file_ra": [], "goi_y_viec": [], "doi_soat": dau_ra}
        if lo_ngai:
            ket_qua["co_lo_ngai"] = True
            ket_qua["lo_ngai"] = "; ".join(filter(None, [ket_qua.get("lo_ngai"), *lo_ngai]))
        ket_qua.update(them_kq)
        self._ket_thuc(id, "xong", "xong", ket_qua=ket_qua)

    # ---------------------------------------------------------------- bước script
    def _buoc_script(self, loai: LoaiViec, viec: dict, b: BuocChay, huy: threading.Event) -> tuple[bool, list[str]]:
        id = viec["id"]
        dong: list[str] = []
        f_phu = None
        trang = {"luc": 0.0, "dem": [], "da_bao": bool(viec.get("can_ban"))}

        def khi_doc_dong(s: str) -> None:
            if len(dong) < DONG_GIU_TOI_DA:
                dong.append(s)
            if f_phu is not None:
                f_phu.write(s + "\n")
                f_phu.flush()
            if loai.ma == "douyin_uid" and b.ten == "agy" and not trang["da_bao"]:
                trang["dem"].append(s)
                bay = time.monotonic()
                if bay - trang["luc"] >= CHU_KY_CAN_BAN_S:
                    trang["luc"] = bay
                    tb = can_ban_douyin("\n".join(trang["dem"]))
                    trang["dem"] = []
                    if tb:
                        trang["da_bao"] = True
                        try:   # giữ nguyên bat_dau_luc (chuyen tự đặt lại nếu không truyền)
                            self.kho.chuyen(id, ["dang_chay"], "dang_chay", "he_thong", "cần bạn (không chặn)",
                                            can_ban=tb, bat_dau_luc=viec.get("bat_dau_luc"))
                        except SaiTrangThai as e:
                            log.debug("việc %s không còn dang_chay khi đặt can_ban: %s", id, e)

        try:
            if b.file_log_phu:
                Path(b.file_log_phu).parent.mkdir(parents=True, exist_ok=True)
                f_phu = open(b.file_log_phu, "w", encoding="utf-8", newline="\n")
            kq = tt.chay_tien_trinh(
                list(b.argv), b.cwd, b.stdin, tt.env_toi_thieu(dict(b.env_them)), self.thu_muc_log / f"{id}.log",
                None, b.het_gio_s, False, b.hien_cua_so, None,
                khi_bat_dau=lambda pid, tl: self.kho.ghi_tien_trinh(id, pid, tl),
                khi_co_session=lambda _s: None, khi_doc_dong=khi_doc_dong, huy=huy, che=self.che)
        except OSError as e:
            if not self._khong_giet_tu_loi(id, e):
                self._ket_thuc(id, "loi", f"không chạy được bước {b.ten}", loi=f"Không chạy được bước {b.ten}: {e}")
            return False, dong
        finally:
            if f_phu is not None:
                try:
                    f_phu.close()
                except OSError as e:
                    log.error("không đóng được %s: %s", b.file_log_phu, e)

        if self._bao_khong_giet(id, kq, f"sau khi {'huỷ' if kq.bi_huy else 'quá giờ'} ở bước {b.ten}"):
            return False, dong
        if kq.bi_huy:
            self._xu_ly_dung(id, loai, viec, f"huỷ khi đang chạy bước {b.ten}")
            return False, dong
        if kq.het_gio:
            self._doi_ten_mp3_hong(loai, viec)
            self._ket_thuc(id, "loi", "quá giờ", loi=f"Quá giờ {b.het_gio_s // 60} phút ở bước {b.ten} — đã dừng cả cây")
            return False, dong
        if kq.ma_thoat != 0 and b.ten not in BUOC_BO_QUA_MA_THOAT:
            self._doi_ten_mp3_hong(loai, viec)
            duoi = self.che("\n".join(dong[-30:]))[-1200:]           # che bản đủ rồi mới cắt (R-06 P3-1)
            self._ket_thuc(id, "loi", f"bước {b.ten} thoát mã {kq.ma_thoat}",
                           loi=f"Bước {b.ten} thoát mã {kq.ma_thoat}:\n{duoi}")
            return False, dong
        return True, dong

    def _tao_con_link(self, viec: dict, stdout: str) -> dict:
        """§5.1 xu_ly_link_moi: tạo job con phan_tich_uid (≤ con_toi_da_xu_ly_link), trùng thì bỏ qua."""
        tran = int(min(self.hm.get("con_toi_da_xu_ly_link", HAN_MUC_TRAN["con_toi_da_xu_ly_link"]),
                       HAN_MUC_TRAN["con_toi_da_xu_ly_link"]))
        uids, tam = con_tu_xu_ly_link(stdout, tran)
        kq = {"viec_con": [], "uid_trung": [], "link_tam": tam, "loi_con": []}
        try:
            loai_con = self._loai("phan_tich_uid")
        except ThamSoLoi as e:
            kq["loi_con"].append(str(e))
            return kq
        for uid in uids:
            try:
                ts = loai_con.kiem_tham_so({"uid": uid}, self.mt)
                tt0, buoc = loai_con.trang_thai_dau(ts)
                kiem_han_muc(self.kho, loai_con.ma, ts, self.hm, "tao", viec["tao_boi"])
                con = self.kho.tao(loai_con.ma, loai_con.tinh_khoa(ts), ts, loai_con.lan_chay, tt0, viec["tao_boi"],
                                   buoc=buoc, session_id=str(uuid.uuid4()) if loai_con.agent else None,
                                   cha_id=viec["id"])
                kq["viec_con"].append(con["id"])
            except TrungViec:
                kq["uid_trung"].append(uid)
            except (VuotHanMuc, ThamSoLoi) as e:
                kq["loi_con"].append(f"{uid}: {e}")
        if tam:
            kq["ghi_chu_tam"] = "link rút gọn chưa phân giải: " + ", ".join(tam)
        return kq

    # ---------------------------------------------------------------- bước Claude
    def _buoc_claude(self, loai: LoaiViec, viec: dict, b: BuocChay, huy: threading.Event,
                     la_cuoi: bool) -> dict | None:
        """Chạy bước Claude. Trả ket_qua (dict) nếu xong và còn bước sau; None nếu đã chuyển trạng thái."""
        id = viec["id"]
        stdin = b.stdin
        if viec.get("phien_da_tao"):
            if "--resume" not in b.argv:
                self._ket_thuc(id, "loi", "lệnh Claude sai", loi="phiên đã tạo nhưng lệnh không có --resume")
                return None
            try:
                stdin = lap_tin_resume(viec, self.kho.su_kien(id), self.kho.tra_loi_cua(id))
            except ThamSoLoi as e:
                self._ket_thuc(id, "loi", "không lập được tin tiếp", loi=f"Không lập được tin resume: {e}")
                return None
        if stdin is None:
            self._ket_thuc(id, "loi", "thiếu phiếu", loi="bước Claude không có stdin (phiếu)")
            return None
        sid_goc = viec.get("session_id")
        soat = sj.SoatCongCu(loai.bo_cong_cu)            # mỗi lượt chạy một bộ soát mới (trạng thái init)

        def khi_bat_dau(pid: int, tl: float) -> None:
            self.kho.ghi_tien_trinh(id, pid, tl)
            self.kho.cong_chi_phi(id, 0.0, 0, True)          # §6.3 chốt 2: đếm lần gọi ngay khi bắt đầu

        def khi_co_session(sid: str) -> None:
            if sid != sid_goc:
                log.warning("việc %s: phiên Claude đổi id %s → %s", id, sid_goc, sid)
                self.kho.chuyen(id, ["dang_chay"], "dang_chay", "he_thong", "phiên Claude đổi id", session_id=sid,
                                bat_dau_luc=viec.get("bat_dau_luc"))
            self.kho.danh_dau_phien(id)

        def khi_doc_dong(s: str) -> None:
            sk = sj.doc_su_kien(s)
            if sk is not None:
                ngoai = soat.xet(sk)
                if ngoai:
                    raise CongCuNgoai(", ".join(ngoai))

        try:
            kq = tt.chay_tien_trinh(
                list(b.argv), b.cwd, stdin, tt.env_toi_thieu(dict(b.env_them)), self.thu_muc_log / f"{id}.log",
                self.thu_muc_log / f"{id}.jsonl", b.het_gio_s, True, b.hien_cua_so, loai.tran_luot,
                khi_bat_dau=khi_bat_dau, khi_co_session=khi_co_session, khi_doc_dong=khi_doc_dong, huy=huy,
                che=self.che)
        except CongCuNgoai as e:
            ly = self.che(str(e))[:500]
            self._ghi_log(id, f"DỪNG: phiên Claude có công cụ ngoài danh sách: {ly}")
            if not self._khong_giet_tu_loi(id, e):
                self._ket_thuc(id, "loi", "Claude có công cụ ngoài danh sách", loi=(
                    f"Phiên Claude có công cụ ngoài danh sách cho phép ({ly}) — đã dừng ngay. Kiểm cấu hình "
                    "MCP/agent của Claude trên máy trước khi chạy lại."))
            return None
        except OSError as e:
            if not self._khong_giet_tu_loi(id, e):
                self._ket_thuc(id, "loi", "không chạy được Claude", loi=f"Không chạy được Claude: {e}")
            return None

        k = kq.ket_qua or {}
        usd = float(k.get("chi_phi_usd") or 0.0)
        try:
            self.kho.cong_chi_phi(id, usd, int(kq.so_luot), False)
        except SaiTrangThai as e:
            # P3-7: không im lặng — chi phí lượt này không vào DB thì hạn mức USD/ngày đếm thiếu
            log.warning("việc %s: KHÔNG ghi được chi phí lượt Claude (%.4f USD, %s lượt): %s",
                        id, usd, kq.so_luot, e)
            self._ghi_log(id, f"cảnh báo: không ghi được chi phí lượt ({usd:.4f} USD, {kq.so_luot} lượt): {e}")
        # sau khi đã ghi chi phí (lượt vẫn tốn tiền dù không giết được)
        ly_giet = "huỷ" if kq.bi_huy else "quá giờ" if kq.het_gio else "vượt trần lượt" if kq.vuot_luot else "giết"
        if self._bao_khong_giet(id, kq, f"sau khi {ly_giet} (bước Claude)"):
            return None

        bat_thuong = phan_loai_ket_thuc_claude(kq, loai.tran_luot, b.het_gio_s, self.che)
        if bat_thuong is not None:
            den, truong, tam = bat_thuong
            if tam:
                self._tam_dung_claude()
            if den == "huy":
                self._xu_ly_dung(id, loai, viec, "huỷ khi Claude đang chạy")
                return None
            truong = che_truong_ket_thuc(truong, self.che)
            self._ket_thuc(id, den, "Claude kết thúc bất thường", **truong)
            return None

        kqa = phan_tich_ket_qua(kq.van_ban_cuoi, self._dot_bat, self.che)   # R-06 P3-1: che trước khi cắt
        dau_ra = kiem_dau_ra_an_toan(loai, viec.get("tham_so") or {}, self.kho.lay(id) or viec, self.mt)
        den, truong = anh_xa_ket_qua(loai, kqa, dau_ra)
        truong = che_truong_ket_thuc(truong, self.che)      # R-05 P2-2: cau_hoi, lua_chon, loi
        ket_qua = dict(truong.get("ket_qua") or {})
        ket_qua["tom_tat"] = self.che(ket_qua.get("tom_tat") or "")
        if isinstance(ket_qua.get("lo_ngai"), str):
            ket_qua["lo_ngai"] = self.che(ket_qua["lo_ngai"])
        ket_qua["chi_phi_usd_luot"] = usd
        ket_qua["so_luot_luot"] = int(kq.so_luot)
        if k.get("bi_tu_choi"):
            ket_qua["bi_tu_choi"] = gon_bi_tu_choi(k["bi_tu_choi"], self.che)
        truong["ket_qua"] = ket_qua
        if den == "xong" and not la_cuoi:
            return ket_qua
        self._ket_thuc(id, den, f"agent: {kqa.trang_thai}", **truong)
        return None
