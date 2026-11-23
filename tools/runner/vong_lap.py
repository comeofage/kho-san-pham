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
- A-3 (§5.2, P2-10): việc tốn tiền, NGAY TRƯỚC khi chạy (mọi lượt: đầu, sau duyệt, chạy tiếp, sau trả lời) — đọc lại
  bản đang lưu → `chu_ky.kiem_duyet` (sai → loi "chữ ký duyệt không hợp lệ") → `kiem_han_muc(luc='nhan', viec_id)`
  (vượt → về cho, hoãn loại). voice_genmax pha ước tính (buoc≠'chay', không gọi API) bỏ qua cổng này và xong pha thì
  sang cho_duyet kèm ước tính. Đếm subagent codex* mỗi việc (trần `codex_luot_viec`, §5.3).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
import re
import secrets
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import psutil

from . import chu_ky
from . import phien_song as ps
from . import phieu as phieu_mod
from . import stream_json as sj
from . import thuc_thi as tt
from .danh_muc import (DANH_MUC, LOAI_PHIEN_SONG, LoaiViec, can_ban_douyin, con_tu_xu_ly_link, doi_soat_taovideo,
                       kiem_dau_ra_an_toan, lap_buoc_hieu_luc, kiem_truoc_buoc, mp3_adam_moi, mp3_hong, phan_tich_poster,
                       quyet_dinh_sau_khoi_dong)
from .du_an import RE_ME, gocs_tu_moi_truong, tim_du_an
from .han_muc import HAN_MUC_TRAN, _gia_tri as _tran_hieu_luc, han_muc_radar, het_gio_taovideo, kiem_han_muc
from .kho_viec import KhoViec
from .kieu import (DANG_MO, MUI_GIO_VN, RE_MA_CAU_HOI, BuocChay, CanNguoiDung, KhongCoPhien, MoiTruong, SaiTrangThai,
                   ThamSoLoi, TrungViec, VuotHanMuc, gio_vn)
from .phieu import (CAU_CHI_DAO, TIN_NHAC, TIN_TRAN_CODEX, anh_xa_ket_luot_song, anh_xa_ket_qua,
                    lap_phieu_tiep_taovideo, lap_tin_chay_tiep, lap_tin_chi_dao, lap_tin_duyet, lap_tin_tiep,
                    phan_tich_ket_qua)
from .theo_doi_phien import TheoDoiPhien, TinhTrang

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
# "session limit": chữ thật S-4 đo khi hết hạn mức gói ("You've hit your session limit · resets …")
RE_QUOTA = re.compile(r"(?i)usage limit|rate limit|session limit|\b429\b|overloaded")
RE_ID = re.compile(r"^j\d{14}[a-z0-9]{4}$", re.ASCII)
# A-3 (§5.2, P2-10): loại tốn tiền
HOAN_HAN_MUC_S = 600               # vượt hạn mức lúc nhận / thiếu khoá công khai → hoãn loại 10 phút
LOI_CHU_KY_DUYET = "chữ ký duyệt không hợp lệ"
BUOC_UOC_TINH_GENMAX = "genmax_uoc_tinh"     # tên bước pha ước tính do danh_muc._buoc_genmax đặt
# D9 (FX-10): tiêu lời duyệt trên Worker ngay trước mỗi lần chạy pha tốn tiền (§5.2 bước 4, §8.3)
WORKER_ORIGIN = "https://kho-san-pham.kutidak.workers.dev"
DUONG_TIEU = "/api/runner/tieu-duyet"
HET_GIO_TIEU_S = 15.0
PHAN_HOI_TIEU_TOI_DA = 64 * 1024
LOI_DA_DUNG = "lời duyệt đã dùng"
LOI_DA_DUNG_DAY_DU = LOI_DA_DUNG + " — bấm Xin duyệt lại"
LY_DO_LECH_TONG_KIEM = "bản cài runner lệch tổng kiểm — cài lại runner"
CANH_BAO_LECH_TONG_KIEM = LY_DO_LECH_TONG_KIEM + ": mọi việc tốn tiền đang bị chặn (việc miễn phí vẫn chạy)"
_RE_NONCE = re.compile(r"^[0-9a-f]{32}$", re.ASCII)
# Đợt 5 (D11, A-5): phiên sống taovideo
PHIEN_BAN_CLAUDE_DA_DO = "2.1.169"  # §7.3: S-3/S-4 đo trên bản này; khác → can_ban cảnh báo (không chặn)
IM_LANG_SONG_S = 10.0              # §7.3 im_lang_s
QUET_MP3_S = 30.0                  # §7.5 quét *_adam.mp3 mới
TOI_DA_STDERR_LOI = 1200           # §7.8 ký tự stderr cuối (đã che) ghi vào loi khi phiên tự chết
HET_GIO_DS_FOLDER_S = 20           # GET /poster/folders: subprocess venv Poster
POSTER_DS_FOLDER = Path(__file__).resolve().parent / "poster_ds_folder.py"

# Đường dẫn mặc định của máy nhà (§1, §5.1). Ghi đè bằng biến môi trường (test luôn ghi đè).
MAC_DINH = {
    "KHO_REPO": "E:/phantichcanhquay/kho-san-pham",
    "KHO_THU_MUC_SCRIPTS": "C:/Users/Mi/.claude/skills/tao-video-tu-canh-quay/scripts",
    "KHO_PYTHON_POSTER": "E:/tool/tiktok_poster_v2/.venv/Scripts/python.exe",
    "KHO_THU_MUC_POSTER": "E:/tool/tiktok_poster_v2",
    "KHO_CLAUDE_EXE": r"C:\Users\Mi\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe",
    "KHO_AGY_EXE": "C:/Users/Mi/AppData/Local/agy/bin/agy.exe",
    "KHO_THU_MUC_RADAR": "E:/quet-kenh-anti",
    "KHO_THU_MUC_SP": "E:/phantichcanhquay",
    # D15 (docs/hoc-tu-dong.md §3.4a): chỉ dùng khi thư mục runner là mặc định (xem tao_moi_truong)
    "KHO_THU_MUC_VIEW": "C:/Users/Mi/view-poster",
    "KHO_SCRIPT_QUET_KENH": "C:/Users/Mi/.claude/skills/quet-phan-tich-kenh-tiktok/scripts/tiktok_scan.py",
    # Radar UID (docs/radar-uid.md §6.6): file token EchoTik, cũng chỉ dùng khi thư mục runner là mặc định
    "KHO_ECHOTIK_TOKEN_FILE": "E:/timsanpham/.echotik_token.json",
}
# D15 (§3.4): (loại việc hệ thống, giờ VN) — đến giờ thì làn nhe tạo 1 việc khoá = ngày VN hôm nay. Thứ tự trong tuple
# là thứ tự tạo trong cùng một vòng (quét trước, Radar UID 10:00, học sau). chay_runner.hen_gio_cho chỉ bật khi thư mục
# runner là mặc định.
HEN_GIO_MAC_DINH: tuple[tuple[str, int], ...] = (("quet_view_hang_ngay", 9), ("radar_uid_hang_ngay", 10),
                                                 ("hoc_hang_ngay", 12))
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class CongCuNgoai(Exception):
    """Phiên Claude có công cụ ngoài danh sách cho phép (S-1: MCP người dùng lọt qua --tools)."""


class VuotTranCodex(Exception):
    """§5.3: số lần gọi subagent codex* của việc vượt trần `codex_luot_viec` → giết cây."""

    def __init__(self, so: int, tran: int):
        super().__init__(f"{so} lần gọi subagent codex > trần {tran}")
        self.so = so
        self.tran = tran


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


def _chay_ds_folder(argv: list[str], het_gio_s: int) -> tuple[int, str, str]:
    """Chạy poster_ds_folder.py: dạng list, env tối thiểu (§4.7), có timeout. Không bắt lỗi ở đây."""
    env = tt.env_toi_thieu({"TT_API_SHORT_TIMEOUT": str(max(1, int(het_gio_s) - 5))})
    r = subprocess.run(argv, capture_output=True, timeout=het_gio_s, creationflags=_NO_WINDOW, env=env,
                       cwd=str(Path(argv[3]).parent) if len(argv) > 3 else None)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def doc_folder_poster_tu(python_poster: Path, script: Path, thu_muc_poster: Path, *,
                         chay: Callable[[list[str], int], tuple[int, str, str]] | None = None,
                         het_gio_s: int = HET_GIO_DS_FOLDER_S) -> list[dict]:
    """§5.2 / A-3: danh sách folder Poster qua `poster_ds_folder.py` chạy bằng python venv Poster (chỉ đọc).
    Mọi lỗi (không chạy được, quá giờ, mã ≠ 0, JSON hỏng) → OSError có thông điệp. `chay` tiêm được (test)."""
    argv = [str(python_poster), "-B", "-I", str(script), "--poster", str(thu_muc_poster)]
    try:
        rc, out, err = (chay or _chay_ds_folder)(argv, het_gio_s)
    except subprocess.TimeoutExpired as e:
        raise OSError(f"poster_ds_folder.py quá giờ {het_gio_s} s — Poster V2 treo?") from e
    except OSError as e:
        raise OSError(f"không chạy được poster_ds_folder.py bằng {python_poster}: {e}") from e
    if rc != 0:
        raise OSError(f"poster_ds_folder.py thoát mã {rc}: {(err or out).strip()[-300:]}")
    dong = [d for d in out.splitlines() if d.strip()]
    try:
        ds = json.loads(dong[-1])
    except (IndexError, ValueError) as e:
        raise OSError(f"poster_ds_folder.py không in JSON hợp lệ: {out.strip()[-200:]!r}") from e
    if not isinstance(ds, list):
        raise OSError(f"poster_ds_folder.py in JSON không phải danh sách: {type(ds).__name__}")
    return [f for f in ds if isinstance(f, dict)]


def nap_khoa_cong_khai_canh_ma():
    """Khoá công khai Worker cạnh mã đang chạy (cùng thứ tự chay_runner._khoa_cong_khai): bản cài
    `app/ky_cong_khai.pem`, chạy từ repo `tools/runner/ky_cong_khai.pem`. Không có → None; PEM hỏng → ném lỗi."""
    goc = Path(__file__).resolve().parent
    for p in (goc.parent / "ky_cong_khai.pem", goc / "ky_cong_khai.pem"):
        if p.is_file():
            return chu_ky.nap_khoa_cong_khai(p.read_bytes())
    return None


def worker_origin() -> str:
    """Origin Worker cho bước tiêu: KHO_WORKER_ORIGIN (test) nếu đặt, ngược lại WORKER_ORIGIN. Đổi sang máy chủ giả
    không bỏ qua được bước tiêu: máy chủ giả không có khoá riêng nên chữ ký phản hồi sai → không chạy."""
    return os.environ.get("KHO_WORKER_ORIGIN") or WORKER_ORIGIN


def origin_hop_le(origin: object) -> bool:
    """https://host (không path/query), hoặc http chỉ cho 127.0.0.1/localhost/::1 (Worker giả trong test).
    Không gửi x-runner-key qua http ra ngoài máy."""
    if not isinstance(origin, str) or not origin:
        return False
    try:
        u = urlsplit(origin)
        host = u.hostname
    except ValueError:
        return False
    if not host or u.path not in ("", "/") or u.query or u.fragment or u.username or u.password:
        return False
    if u.scheme == "https":
        return True
    return u.scheme == "http" and host in ("127.0.0.1", "localhost", "::1")


class _KhongChuyenHuong(urllib.request.HTTPRedirectHandler):
    """Không theo chuyển hướng: x-runner-key không được đi tới host khác; 3xx → HTTPError → 'chua_ro'."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


_MO_HTTP = urllib.request.build_opener(_KhongChuyenHuong())


def goi_http_urllib(url: str, headers: dict[str, str], body: bytes, timeout_s: float) -> tuple[int, bytes]:
    """POST bằng urllib (không chuyển hướng). Trả (mã HTTP, ≤64 KB thân). Lỗi mạng/hết giờ → ném (bên gọi bắt)."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with _MO_HTTP.open(req, timeout=timeout_s) as r:
            return int(r.status), r.read(PHAN_HOI_TIEU_TOI_DA)
    except urllib.error.HTTPError as e:
        try:
            b = e.read(PHAN_HOI_TIEU_TOI_DA) if e.fp is not None else b""
        except OSError:
            b = b""
        finally:
            e.close()
        return int(e.code), b


def tieu_duyet(origin: str, khoa_runner: str, kcc, id: str, chu_ky_duyet: str, *,  # noqa: A002
               goi_http: Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]] | None = None,
               sinh_nonce: Callable[[], str] = lambda: secrets.token_hex(16),
               timeout_s: float = HET_GIO_TIEU_S) -> tuple[str, str]:
    """§8.3 "Tiêu lời duyệt" phía runner. → ("da_tieu" | "da_dung" | "chua_ro", mô tả ngắn KHÔNG chứa khoá).
    - 200 + `ky` kiểm đúng bằng `chu_ky.kiem_tieu(kcc, id, chu_ky_duyet, nonce, ky)` → da_tieu;
    - 409 → da_dung;
    - mọi trường hợp khác (mạng, hết giờ, 3xx/4xx/5xx, JSON hỏng, chữ ký sai, thiếu khoá) → chua_ro (KHÔNG chạy).
    Nonce mới mỗi lần, chỉ nằm trong bộ nhớ."""
    if kcc is None:
        return "chua_ro", "runner không có khoá công khai để kiểm phản hồi tiêu"
    if not isinstance(khoa_runner, str) or not khoa_runner:
        return "chua_ro", "runner không có khoá .runner_key"
    if not origin_hop_le(origin):
        return "chua_ro", "origin Worker không hợp lệ (cần https)"
    nonce = sinh_nonce()
    if not isinstance(nonce, str) or not _RE_NONCE.fullmatch(nonce):
        return "chua_ro", "nonce sinh ra sai định dạng"
    body = json.dumps({"id": id, "chu_ky_duyet": chu_ky_duyet, "nonce": nonce},
                      separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {"content-type": "application/json", "x-runner-key": khoa_runner, "user-agent": "kho-runner"}
    goi = goi_http or goi_http_urllib
    try:
        ma, tho = goi(origin.rstrip("/") + DUONG_TIEU, headers, body, timeout_s)
    except Exception as e:  # noqa: BLE001 — mọi lỗi mạng/hết giờ → chua_ro (đã log, không nuốt im)
        log.warning("tiêu lời duyệt %s: lỗi gọi Worker %s: %s", id, type(e).__name__, str(e)[:200])
        return "chua_ro", f"lỗi mạng tới Worker ({type(e).__name__})"
    if ma == 409:
        return "da_dung", "Worker báo lời duyệt đã dùng (409)"
    if ma != 200:
        log.warning("tiêu lời duyệt %s: Worker trả HTTP %s", id, ma)
        return "chua_ro", f"Worker trả HTTP {ma}"
    try:
        d = json.loads((tho or b"").decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        log.warning("tiêu lời duyệt %s: phản hồi 200 không phải JSON", id)
        return "chua_ro", "phản hồi Worker không phải JSON"
    ky = d.get("ky") if isinstance(d, dict) else None
    if not isinstance(ky, str) or not chu_ky.kiem_tieu(kcc, id, chu_ky_duyet, nonce, ky):
        log.error("tiêu lời duyệt %s: chữ ký phản hồi của Worker SAI — không chạy", id)
        return "chua_ro", "chữ ký phản hồi của Worker sai"
    return "da_tieu", "Worker nhận tiêu (chữ ký đúng)"


def tao_ham_tieu(origin: str, khoa_runner: str | None, kcc, **kw) -> Callable[[str, str], tuple[str, str]]:
    """Gói tieu_duyet thành `tieu(id, chu_ky_duyet)` cho BoChay (cùng kcc với API — chay_runner nạp một lần)."""
    def tieu(id: str, chu_ky_duyet: str) -> tuple[str, str]:  # noqa: A002
        return tieu_duyet(origin, khoa_runner or "", kcc, id, chu_ky_duyet, **kw)
    return tieu


def tao_moi_truong() -> MoiTruong:
    """MoiTruong thật. Đường dẫn ghi đè được bằng biến môi trường KHO_* (xem MAC_DINH)."""
    def g(k: str) -> Path:
        return Path(os.environ.get(k) or MAC_DINH[k])
    pid_runner = os.getpid()
    scripts = g("KHO_THU_MUC_SCRIPTS")
    py_poster, thu_poster = g("KHO_PYTHON_POSTER"), g("KHO_THU_MUC_POSTER")
    # D15 (§3.6 "Chặn chạm production"): biến môi trường nếu đặt; không đặt thì đường dẫn thật mặc định CHỈ KHI thư mục
    # runner là mặc định — thư mục tạm (test) thiếu biến → None (lap_buoc của 2 loại hệ thống báo ThamSoLoi).
    la_mac_dinh = _chuan(thu_muc_runner()) == _chuan(_thu_muc_mac_dinh())

    def g3(k: str) -> Path | None:
        v = os.environ.get(k)
        if v:
            return Path(v)
        return Path(MAC_DINH[k]) if la_mac_dinh else None
    thu_poster_hoc = g3("KHO_THU_MUC_POSTER")
    return MoiTruong(
        gocs=gocs_tu_moi_truong(), repo_kho=g("KHO_REPO"), thu_muc_scripts=scripts,
        python_poster=py_poster, claude_exe=g("KHO_CLAUDE_EXE"), agy_exe=g("KHO_AGY_EXE"),
        thu_muc_radar=g("KHO_THU_MUC_RADAR"), thu_muc_sp=g("KHO_THU_MUC_SP"), thu_muc_du_lieu=thu_muc_runner(),
        cong_song=cong_song, chan_doan_kho=chan_doan_kho,
        ffmpeg_ngoai=lambda: tt.ffmpeg_ngoai({pid_runner}),
        thoi_luong_media=thoi_luong_ffprobe, bay_gio=_bay_gio, ds_ma_voice=_ds_ma_voice_tu(scripts),
        doc_folder_poster=lambda: doc_folder_poster_tu(py_poster, POSTER_DS_FOLDER, thu_poster),
        poster_db=thu_poster_hoc / "v2_data.db" if thu_poster_hoc is not None else None,
        thu_muc_view=g3("KHO_THU_MUC_VIEW"), script_quet_kenh=g3("KHO_SCRIPT_QUET_KENH"),
        echotik_token_file=g3("KHO_ECHOTIK_TOKEN_FILE"))


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


KHOA_DUYET_LAI = ("duyet_lai_tu", "ly_do_duyet_lai")     # FX-14 api xin-duyet-lai ghi; FX-15 dùng 1 lần rồi xoá


def ly_do_duyet_lai_can_dung(loai: LoaiViec, viec: dict, su_kien: list[dict]) -> str | None:
    """FX-15: lý do xin duyệt lại cần đưa vào stdin lượt Claude này, hoặc None.
    Chỉ khi việc tốn tiền, lần quay về `cho` gần nhất là do duyệt, và ket_qua có `ly_do_duyet_lai` (chuỗi khác rỗng)."""
    if not loai.ton_tien:
        return None
    kq = viec.get("ket_qua")
    ly = kq.get("ly_do_duyet_lai") if isinstance(kq, dict) else None
    if not isinstance(ly, str) or not ly.strip():
        return None
    return ly if ly_do_tiep_tuc(su_kien)[0] == "duyet" else None


def bo_khoa_duyet_lai(kq: object) -> dict:
    """Bản sao ket_qua bỏ 2 khoá duyệt lại (giữ so_codex, tom_tat…). Không sửa dict gốc."""
    return {k: v for k, v in kq.items() if k not in KHOA_DUYET_LAI} if isinstance(kq, dict) else {}


def lap_tin_sau_duyet_lai(viec: dict, ly_do: str, phieu: str | None) -> str:
    """FX-15: stdin lượt Claude sau xin duyệt lại → duyệt. `phieu` None (resume) → lý do + khối ĐÃ DUYỆT;
    có phiếu (chưa có phiên) → phiếu đầy đủ (đã chứa khối ĐÃ DUYỆT) + lý do. `ly_do` bên gọi đã che."""
    if phieu is None:
        return lap_tin_chay_tiep(viec, ly_do) + lap_tin_duyet(viec)
    return phieu + "\n" + lap_tin_chay_tiep(viec, ly_do)


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
    từng `cau_hoi.lua_chon`. GIỮ `cau_hoi.ma` (mã câu hỏi phiên sống, FX-26). Trả dict mới (không sửa đầu vào)."""
    ra = dict(truong)
    if isinstance(ra.get("loi"), str):
        ra["loi"] = che(ra["loi"])
    ch = ra.get("cau_hoi")
    if isinstance(ch, dict):
        ch = CanNguoiDung.tu_dict(ch)
    if isinstance(ch, CanNguoiDung):
        ra["cau_hoi"] = CanNguoiDung(ch.loai, che(ch.noi_dung), tuple(che(x) for x in ch.lua_chon), ch.ma)
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


# ---------------------------------------------------------------- A-3: loại tốn tiền (logic thuần)

def can_kiem_duyet(loai: LoaiViec, viec: dict) -> bool:
    """Việc này có cần chữ ký duyệt hợp lệ trước khi chạy không. Mọi loại tốn tiền đều cần, TRỪ voice_genmax pha
    ước tính: danh_muc._buoc_genmax chỉ chạy pha gọi API khi `buoc == 'chay'` đúng nguyên văn — mọi giá trị khác là
    pha ước tính (không --dong-y, không gọi API). Hai điều kiện phải khớp nhau từng ký tự."""
    if not loai.ton_tien:
        return False
    return loai.ma != "voice_genmax" or viec.get("buoc") == "chay"


def loi_khong_sinh_duoc(b: BuocChay) -> str | None:
    """FX-18 (R-15 P3-2): lỗi cấu hình làm bước KHÔNG sinh được tiến trình, phát hiện được TRƯỚC khi tiêu lời duyệt.
    None = hợp lệ. Chỉ bắt lỗi chắc chắn (không đoán PATH): argv rỗng/không phải chuỗi, argv[0] rỗng, cwd không phải
    thư mục, argv[0] là đường dẫn tuyệt đối mà không có file, stdin không phải chuỗi."""
    argv = b.argv
    if not isinstance(argv, (list, tuple)) or not argv:
        return "lệnh rỗng"
    if not all(isinstance(x, str) for x in argv) or not argv[0]:
        return "lệnh có phần tử không phải chuỗi hoặc tên chương trình rỗng"
    if not isinstance(b.cwd, str) or not b.cwd or not os.path.isdir(b.cwd):
        return f"thư mục chạy không tồn tại: {b.cwd!r}"
    if os.path.isabs(argv[0]) and not os.path.isfile(argv[0]):
        return f"không thấy chương trình: {argv[0]}"
    if b.stdin is not None and not isinstance(b.stdin, str):
        return "stdin của bước không phải chuỗi"
    return None


_RE_KE_HOACH = re.compile(r"^[ \t]*Kế hoạch: (\d+) lượt GenMax, tổng (\d+) ký tự: \[([^\]\n]*)\]", re.M)
_RE_BO_QUA = re.compile(r"^[ \t]*\[bỏ qua\] (\S+): đã có voice", re.M)
_RE_MA_TRONG_DS = re.compile(r"'([^'\n]*)'")
CANH_BAO_UOC_TINH_TOI_DA = 10


def doc_uoc_tinh_genmax(van_ban: str) -> dict | None:
    """Đọc output THẬT của `tao_voice.py` pha ước tính (không --dong-y):
    `Kế hoạch: N lượt GenMax, tổng K ký tự: ['m1', …] · model … · tăng tốc …`, các dòng `[bỏ qua] m: đã có voice`,
    dòng `[!] …` và `CHƯA gọi API. …`. Script không in credit nên không có trường credit.
    None nếu không có đúng MỘT dòng Kế hoạch hoặc số lượt lệch số mã (không tin được để đưa đi duyệt)."""
    ds = list(_RE_KE_HOACH.finditer(van_ban or ""))
    if len(ds) != 1:
        return None
    m = ds[0]
    so, ky_tu = int(m.group(1)), int(m.group(2))
    ma = _RE_MA_TRONG_DS.findall(m.group(3))
    if len(ma) != so:
        return None
    cuoi = van_ban.find("\n", m.start())
    dong = van_ban[m.start(): cuoi if cuoi >= 0 else len(van_ban)].strip()
    canh_bao = [d.strip() for d in van_ban.splitlines() if d.strip().startswith("[!]")]
    return {"so_ban": so, "ky_tu": ky_tu, "ma": ma, "bo_qua": _RE_BO_QUA.findall(van_ban),
            "chua_goi_api": "CHƯA gọi API" in van_ban, "canh_bao": canh_bao[:CANH_BAO_UOC_TINH_TOI_DA], "dong": dong}


def dem_codex(sk: dict) -> int:
    """§5.3: số tool_use tên `Agent` có `subagent_type` bắt đầu bằng `codex` (không phân biệt hoa thường)."""
    n = 0
    for ten, inp in sj.ten_cong_cu(sk):
        sub = inp.get("subagent_type") if isinstance(inp, dict) else None
        if ten == "Agent" and isinstance(sub, str) and sub.strip().lower().startswith("codex"):
            n += 1
    return n


def tran_codex(hm: dict) -> int:
    """Trần lượt Codex mỗi việc = min(trần code, cau_hinh) — file chỉ được hạ (§10)."""
    tran = int(HAN_MUC_TRAN["codex_luot_viec"])
    v = hm.get("codex_luot_viec", tran) if isinstance(hm, dict) else tran
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v < 0:
        return tran
    return int(min(v, tran))


def _so_nguyen_khong_am(x: object) -> int:
    return x if isinstance(x, int) and not isinstance(x, bool) and x >= 0 else 0


# ---------------------------------------------------------------- đợt 5: phiên sống (logic thuần)

def dat_max_budget(argv: list[str], tran_usd: float) -> list[str]:
    """A-5 c) + S-4 mục 2: `--max-budget-usd` CỘNG DỒN cả phiên → đặt bằng trần phiên HIỆU LỰC (cau_hinh chỉ hạ).
    Trả bản sao argv. Thiếu cờ / trần ≤ 0 → ThamSoLoi (không chạy)."""
    a = list(argv)
    if (isinstance(tran_usd, bool) or not isinstance(tran_usd, (int, float)) or tran_usd != tran_usd
            or tran_usd <= 0):
        raise ThamSoLoi(f"trần USD phiên sống không hợp lệ ({tran_usd!r}) — taovideo bị khoá bằng cau_hinh")
    try:
        i = a.index("--max-budget-usd")
    except ValueError:
        raise ThamSoLoi("lệnh phiên sống thiếu --max-budget-usd") from None
    if i + 1 >= len(a):
        raise ThamSoLoi("lệnh phiên sống: --max-budget-usd thiếu giá trị")
    a[i + 1] = f"{float(tran_usd):g}"
    return a


def gio_doc(giay: float) -> str:
    """Thời lượng cho người đọc: '8 giờ', '45 phút', '30 giây'."""
    g = float(giay)
    if g >= 3600:
        return f"{g / 3600:g} giờ"
    if g >= 60:
        return f"{g / 60:g} phút"
    return f"{g:g} giây"


class _TrangPhien:
    """Trạng thái DÙNG CHUNG giữa luồng làn (khi_nhip) và luồng API (tra_loi_song) — chỉ đọc/ghi dưới
    `BoChay._khoa_song`."""

    def __init__(self, phien: ps.PhienSong):
        self.phien = phien
        self.cau_hoi: CanNguoiDung | None = None    # câu đang hỏi (kể cả đã trả lời mà tin chưa ghi vào stdin)
        self.tra_loi_cho = False                    # đã trả lời, tin trả lời còn trong hàng đợi
        self.cho_tu: float | None = None            # monotonic: bắt đầu lần chờ trả lời hiện tại
        self.tong_cho = 0.0                         # tổng giây đã chờ người dùng (không tính vào lam_s)
        self.da_nhac = False                        # đã gửi TIN_NHAC kể từ lần hỏi/trả lời cuối
        self.bao_codex_cho = False                  # chạm trần Codex, TIN_TRAN_CODEX chưa gửi
        self.da_bao_codex = False
        self.chi_dao_cho = False                    # có chỉ đạo của chủ shop trong hàng đợi chưa ghi stdin
        self.ngat: Callable[[str], None] | None = None   # giết phiên với lý do (luồng làn gán khi sinh phiên)

    def ket_thuc_cho(self, luc: float) -> None:
        if self.cho_tu is not None:
            self.tong_cho += max(0.0, luc - self.cho_tu)
            self.cho_tu = None


# ================================================================ BoChay

class BoChay:
    def __init__(self, kho: KhoViec, mt: MoiTruong, hm: dict, thu_muc_log: Path, che: Callable[[str], str], *,
                 danh_muc: dict[str, LoaiViec] | None = None, cho_lai_s: float = CHO_LAI_S,
                 nghi_s: float = NGHI_S, tam_dung_claude_s: float = TAM_DUNG_CLAUDE_S,
                 canh_bao: list[str] | None = None, kiem_song_s: float = KIEM_SONG_S,
                 khoa_cong_khai=None, cho_lai_han_muc_s: float = HOAN_HAN_MUC_S,
                 chan_ton_tien: bool = False,
                 tieu: Callable[[str, str], tuple[str, str]] | None = None,
                 im_lang_song_s: float = IM_LANG_SONG_S, quet_mp3_s: float = QUET_MP3_S,
                 kho_hoc=None, hen_gio: tuple[tuple[str, int], ...] = (), kho_radar=None):
        """`kho_hoc` (D15): KhoHoc đã mo() — ghi vết bài học vào phiếu phan_tich_uid (§3.7); None = học tự động tắt
        (không ghi vết, hẹn giờ bỏ việc hoc_hang_ngay). `hen_gio` (D15 §3.4): ((loại, giờ VN), …); () = không hẹn giờ.
        `kho_radar` (Radar UID §6.1): KhoRadarUid đã mo(); None = Radar tắt (hẹn giờ bỏ việc radar_uid_hang_ngay).
        `khoa_cong_khai` (A-3, P3-1): khoá Ed25519 kiểm chữ ký duyệt lúc nhận việc tốn tiền — chay_runner truyền
        CÙNG đối tượng đã nạp cho API (không nạp lười). None = không có khoá → việc tốn tiền đứng chờ.
        `chan_ton_tien` (D9, R-11 P2-1): bản cài lệch TONG_KIEM → mọi việc tốn tiền đứng chờ, việc miễn phí vẫn chạy.
        `tieu(id, chu_ky_duyet)` (D9): tiêu lời duyệt trên Worker → ("da_tieu"|"da_dung"|"chua_ro", mô tả);
        None → mọi việc tốn tiền "chua_ro" (đứng chờ + cảnh báo)."""
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
        self.chan_ton_tien = bool(chan_ton_tien)
        if self.chan_ton_tien:
            c = CANH_BAO_LECH_TONG_KIEM
            if c not in self.canh_bao:
                self.canh_bao.append(c)                     # mục khởi động: không bị cắt khi vượt CANH_BAO_TOI_DA
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
        self._kcc = khoa_cong_khai
        self.cho_lai_han_muc_s = cho_lai_han_muc_s
        self._tieu = tieu
        # Đợt 5 (A-5): phiên sống đang giữ, theo id việc. Khoá riêng (KHÔNG lồng trong self._khoa): API giữ
        # khoa_ghi của api rồi mới lấy khoá này; luồng làn chỉ lấy khoá này.
        self.im_lang_song_s = float(im_lang_song_s)
        self.quet_mp3_s = float(quet_mp3_s)
        self._khoa_song = threading.RLock()
        self._phien: dict[str, _TrangPhien] = {}
        # D15: bộ học + hẹn giờ. _hen_da_xet: loại → ngày VN đã xét xong (đã tạo / đã có / bị chặn) — chỉ luồng làn nhe
        # đọc/ghi; khởi động lại thì rỗng, lớp chặn trùng thật nằm ở DB (_da_co_viec_ngay).
        self.kho_hoc = kho_hoc
        self.kho_radar = kho_radar
        self.hen_gio: tuple[tuple[str, int], ...] = tuple(hen_gio)
        self._hen_da_xet: dict[str, str] = {}

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

    def _ket_thuc(self, id: str, den: str, ghi_chu: str, *, tu: tuple[str, ...] | list[str] = ("dang_chay",),
                  **truong) -> dict | None:
        """dang_chay → den (CAS). Việc đã bị đổi ngoài (vd huỷ từ web) → log, trả None.
        R-06 P3-1: lưới cuối — che `ghi_chu`, `loi`, `cau_hoi` (mọi chuỗi đi ra web). Bên gọi cắt chuỗi thì
        PHẢI che bản đầy đủ trước khi cắt (che ở đây không cứu được bí mật đã bị cắt dở).
        `tu` (A-5, mặc định dang_chay): phiên sống kết thúc được cả từ can_tra_loi (§7.4)."""
        ghi_chu = self.che(ghi_chu)
        truong = che_truong_ket_thuc(truong, self.che)
        truong.setdefault("pid", None)
        truong.setdefault("pid_tao_luc", None)
        try:
            return self.kho.chuyen(id, list(tu), den, "he_thong", ghi_chu, **truong)
        except SaiTrangThai as e:
            log.info("việc %s không còn %s khi định chuyển sang %s: %s", id, "/".join(tu), den, e)
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

    def _hoan_loai(self, ma: str, giay: float | None = None) -> None:
        with self._khoa:
            self._hoan[ma] = time.monotonic() + (self.cho_lai_s if giay is None else giay)

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
        """`lan`: {gpu|nhe: {id, loai} khi đang chạy, None khi rảnh} (R-05 P3-2). `phien_song`: id việc đang giữ
        phiên Claude sống (A-5)."""
        with self._khoa_song:
            phien_song = sorted(self._phien)
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
                    "con_song": {k: v[0] for k, v in self._con_song.items()},
                    "chan_ton_tien": self.chan_ton_tien,
                    "phien_song": phien_song}

    def co_phien_song(self, id: str) -> bool:
        """§7.6: vòng chạy đang giữ phiên Claude sống của việc `id` — tính từ lúc đăng ký phiên tới khi luồng làn đã
        GHI XONG trạng thái cuối (FX-27 P2-2: cả khoảng tiến trình đang thoát/đổi tên mp3/đối soát, để api không mở
        Xin duyệt lại giữa chừng). Nhận trả lời thì còn đòi stdin mở (tra_loi_song kiểm con_song riêng)."""
        with self._khoa_song:
            return id in self._phien

    def tra_loi_song(self, id: str, boi: str, gia_tri: str, ma_cau_hoi: str) -> dict:
        """§7.6 bước 4 (API gọi khi đã kiểm giá trị bằng kiem_tra_loi_dot5): (1) còn phiên sống + việc can_tra_loi;
        (2) CAS can_tra_loi → dang_chay (xoá cau_hoi, GIỮ pid); (3) them_tra_loi; (4) xếp lap_tin_tiep vào hàng đợi
        stdin, GẮN `ma_cau_hoi` (PhienSong bỏ tin nếu câu hỏi đã đổi trước khi ghi). KHÔNG tiêu lời duyệt, không sinh
        tiến trình. Không có phiên → KhongCoPhien; sai trạng thái hoặc `ma_cau_hoi` ≠ `cau_hoi.ma` đang treo →
        SaiTrangThai; giá trị không hợp lệ với câu hỏi → ThamSoLoi."""
        with self._khoa_song:
            tp = self._phien.get(id)
            if tp is None or not tp.phien.con_song():
                raise KhongCoPhien(f"việc {id} không còn phiên Claude sống")
            v = self.kho.lay(id)
            if v is None or v["trang_thai"] != "can_tra_loi" or not isinstance(v.get("cau_hoi"), dict):
                raise SaiTrangThai(f"việc {id} không ở can_tra_loi có câu hỏi")
            ch = CanNguoiDung.tu_dict(v["cau_hoi"])
            if (not isinstance(ma_cau_hoi, str) or not RE_MA_CAU_HOI.fullmatch(ma_cau_hoi) or ma_cau_hoi != ch.ma
                    or tp.cau_hoi is None or tp.cau_hoi.ma != ma_cau_hoi):
                raise SaiTrangThai(f"việc {id}: mã câu hỏi {str(ma_cau_hoi)[:40]!r} không phải câu đang treo — câu "
                                   "hỏi đã đổi")
            tin = lap_tin_tiep(v, ch, gia_tri)                  # ThamSoLoi nếu giá trị sai loại câu hỏi
            moi = self.kho.chuyen(id, ["can_tra_loi"], "dang_chay", boi,
                                  self.che(f"trả lời trong phiên sống: {gia_tri}")[:300], cau_hoi=None,
                                  bat_dau_luc=v.get("bat_dau_luc"))
            self.kho.them_tra_loi(id, boi, ch.noi_dung, gia_tri)
            if not tp.phien.gui(tin, ma_cau_hoi):
                log.warning("việc %s: phiên vừa đóng — tin trả lời không vào được hàng đợi", id)
                self._ghi_log(id, "cảnh báo: phiên vừa đóng, tin trả lời không gửi được")
            tp.tra_loi_cho = True
            tp.ket_thuc_cho(time.monotonic())
            tp.da_nhac = False
            if tp.bao_codex_cho:
                tp.phien.gui(TIN_TRAN_CODEX.format(n=tran_codex(self.hm)))
                tp.bao_codex_cho, tp.da_bao_codex = False, True
            self._ghi_log(id, f"người dùng ({boi}) trả lời — xếp tin vào stdin phiên sống")
            return moi

    def nhan_tin_song(self, id: str, boi: str, noi_dung: str, ngat: bool) -> dict:
        """Chủ shop chỉ đạo việc phiên sống (API đã kiểm mật khẩu + làm sạch chữ). Chỉ đạo luôn lưu thành dòng
        tra_loi (câu CAU_CHI_DAO) để phiếu LẦN CHẠY TIẾP mang theo.
        - ngat=False: việc phải dang_chay; xếp tin vào hàng đợi stdin — agent nhận khi kết lượt (kể cả đang chờ việc
          nền). Khi còn chỉ đạo chưa ghi, khi_nhip không đóng/hỏi/nhắc.
        - ngat=True: dang_chay hoặc can_tra_loi; giết cả cây → việc về loi, chờ Xin duyệt lại.
        Không có phiên → KhongCoPhien; sai trạng thái → SaiTrangThai."""
        with self._khoa_song:
            tp = self._phien.get(id)
            if tp is None or not tp.phien.con_song():
                raise KhongCoPhien(f"việc {id} không còn phiên Claude sống")
            v = self.kho.lay(id)
            duoc = ("dang_chay", "can_tra_loi") if ngat else ("dang_chay",)
            if v is None or v["trang_thai"] not in duoc:
                raise SaiTrangThai(f"việc {id} không ở {'/'.join(duoc)}")
            tin = lap_tin_chi_dao(v, noi_dung)                  # ThamSoLoi nếu rỗng
            if ngat and tp.ngat is None:
                raise KhongCoPhien(f"việc {id}: phiên chưa sẵn sàng để ngắt")
            self.kho.them_tra_loi(id, boi, CAU_CHI_DAO, noi_dung)
            tom = self.che(noi_dung)[:200]
            if ngat:
                self._ghi_log(id, f"chủ shop ({boi}) ngắt phiên để chỉ đạo lại: {tom}")
                tp.ngat(f"Chủ shop ngắt để chỉ đạo lại: {tom}")
                ghi = f"ngắt để chỉ đạo: {tom}"
            else:
                if not tp.phien.gui(tin):
                    raise KhongCoPhien(f"việc {id}: phiên vừa đóng")
                tp.chi_dao_cho = True
                tp.da_nhac = False
                self._ghi_log(id, f"chủ shop ({boi}) chỉ đạo — xếp tin vào stdin, agent nhận khi xong bước đang làm")
                ghi = f"chỉ đạo: {tom}"
            moi = self.kho.chuyen(id, [v["trang_thai"]], v["trang_thai"], boi, ghi[:300],
                                  bat_dau_luc=v.get("bat_dau_luc"))
            return moi

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
        # §7.8 (A-5): phiên sống bị ngắt = taovideo ở dang_chay HOẶC can_tra_loi mà pid khác rỗng
        ds_mo = self.kho.ds(["dang_chay"], gioi_han=500) + [
            v for v in self.kho.ds(["can_tra_loi"], gioi_han=500) if v.get("loai") in LOAI_PHIEN_SONG and v.get("pid")]
        for v in ds_mo:
            id = v["id"]
            tu = (v["trang_thai"],)
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
                self._ket_thuc(id, "loi", "khởi động lại: tiến trình cũ còn sống", tu=tu, loi=(
                    f"{con_song} — tiến trình cũ còn sống, kiểm tay trên máy (Task Manager) rồi mới "
                    "Chạy tiếp/Chạy lại"))
                continue
            try:
                loai = self._loai(v["loai"])
            except ThamSoLoi as e:
                kq["loai_la"].append(id)
                self._ket_thuc(id, "loi", "khởi động lại: loại không chạy được", tu=tu, loi=str(e))
                continue
            if loai.ma in LOAI_PHIEN_SONG and pid:
                kq["doi_soat"][id] = self._khoi_dong_phien_song(loai, v)
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
                # FX-29 (B7): GỘP vào ket_qua cũ — giữ kho_luc_tao, so_codex… (không thay cả dict)
                kq_cu = dict(v["ket_qua"]) if isinstance(v.get("ket_qua"), dict) else {}
                kq_cu.update({"trang_thai_agent": None, "co_lo_ngai": dau_ra == "xong_lo_ngai",
                              "tom_tat": ghi, "file_ra": [], "goi_y_viec": []})
                truong["ket_qua"] = kq_cu
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

    def _khoi_dong_phien_song(self, loai: LoaiViec, v: dict) -> list[str]:
        """§7.8 bước 2–4 cho phiên sống bị ngắt (cây đã giết/đã chết ở bước 1): đổi tên mp3 hỏng, đối soát CHỈ ĐỌC
        FILE, xong → xong; chua → loi "Bị ngắt …" (+ ket_qua.cau_hoi_treo nếu đang hỏi). Không tự chạy lại (D5)."""
        id = v["id"]
        self._doi_ten_mp3_taovideo(v, None)
        ket, tom = self._doi_soat_song(v)
        kq = dict(v["ket_qua"]) if isinstance(v.get("ket_qua"), dict) else {}
        ch = v.get("cau_hoi")
        if v["trang_thai"] == "can_tra_loi" and isinstance(ch, dict) and str(ch.get("noi_dung") or "").strip():
            kq["cau_hoi_treo"] = str(ch["noi_dung"])
        self._ghi_log(id, f"khởi động lại: phiên sống bị ngắt — đối soát: {ket} · {tom}")
        tu = (v["trang_thai"],)
        if ket == "xong":
            kq.update({"trang_thai_agent": None, "co_lo_ngai": False, "tom_tat": tom, "doi_soat": tom})
            kq.pop("cau_hoi_treo", None)
            self._ket_thuc(id, "xong", "đối soát sau khởi động lại", tu=tu, ket_qua=kq, cau_hoi=None, can_ban=None)
            return [ket, "xong"]
        kq["doi_soat"] = tom
        self._ket_thuc(id, "loi", "khởi động lại: phiên sống bị ngắt", tu=tu, ket_qua=kq, cau_hoi=None, can_ban=None,
                       loi=(f"Bị ngắt (máy tắt/runner dừng) — {tom}. Mọi việc nền đã dừng. Kiểm log rồi bấm Xin "
                            "duyệt lại để làm tiếp"))
        return [ket, "loi"]

    def _doi_soat_song(self, v: dict) -> tuple[str, str]:
        """doi_soat_taovideo, lỗi bất ngờ → ('chua', mô tả) (không làm sập runner)."""
        try:
            ket, tom = doi_soat_taovideo(v.get("tham_so") or {}, v, self.mt)
        except Exception as e:  # noqa: BLE001 — đối soát hỏng thì coi là chưa xong, có log
            log.exception("đối soát taovideo %s lỗi", v.get("id"))
            return "chua", self.che(f"không đối soát được ({type(e).__name__}: {e})")[:800]
        return (ket if ket in ("xong", "chua") else "chua"), self.che(str(tom))[:800]

    def _doi_ten_mp3_taovideo(self, viec: dict, tu: datetime | None) -> list[Path]:
        """§7.7: mp3 Adam mới (mtime ≥ lúc sinh phiên / bat_dau_luc) của dự án A mà ffprobe lỗi hoặc thời lượng ≤ 0 →
        đổi tên `<tên>.hong-<id>` (hoàn tác được)."""
        ts = viec.get("tham_so") or {}
        try:
            if tu is None:
                tu = datetime.fromisoformat(viec["bat_dau_luc"])
            a = tim_du_an(ts.get("du_an_a"), ts.get("uid"), self.mt.gocs)
        except (KeyError, TypeError, ValueError, ThamSoLoi) as e:
            log.warning("việc %s: không dò được mp3 hỏng: %s", viec.get("id"), e)
            return []
        if a is None:
            return []
        da_doi = []
        for ten in sorted(mp3_adam_moi(a, tu)):
            f = a / ten
            tl = self.mt.thoi_luong_media(f)
            if tl is not None and tl > 0:
                continue
            moi = f.with_name(f"{f.name}.hong-{viec['id']}")
            try:
                f.rename(moi)
                da_doi.append(moi)
                self._ghi_log(viec["id"], f"đổi tên mp3 hỏng {ten} → {moi.name}")
            except OSError as e:
                log.error("không đổi tên được %s: %s", f, e)
        return da_doi

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
            if lan == "nhe" and self.hen_gio:
                try:
                    self._hen_gio()
                except Exception:  # noqa: BLE001 — §3.4: lỗi hẹn giờ chỉ log, không giết làn
                    log.exception("làn nhe: lỗi hẹn giờ việc hệ thống")
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

    # ---------------------------------------------------------------- D15: hẹn giờ (§3.4)
    def _da_co_viec_ngay(self, ma: str, ngay: str) -> bool:
        """Đã có việc loại `ma` khoá `ngay` ở BẤT KỲ trạng thái? Gồm cả việc đã ẩn/lưu trữ (ds() không thấy): đếm theo
        ngày tạo — việc hệ thống khoá = ngày VN hôm nay chỉ tạo được trong chính ngày đó (kiem_tham_so)."""
        if any(v.get("loai") == ma for v in self.kho.ds(None, khoa=ngay, gioi_han=50)):
            return True
        return self.kho.dem_trong_ngay(ma, datetime.fromisoformat(ngay).date()) > 0

    def _hen_gio(self) -> list[str]:
        """Đến giờ (VN) thì tạo việc hệ thống cho ngày hôm nay nếu chưa có. Trả id các việc vừa tạo.
        TrungViec / VuotHanMuc / ThamSoLoi → log 1 lần, ghi nhớ ngày (không thử lại trong ngày). Lỗi khác (DB) → ném
        (bên gọi log), không ghi nhớ → vòng sau thử lại."""
        bay = self._bay_gio()
        ngay = bay.date().isoformat()
        tao: list[str] = []
        for ma, gio in self.hen_gio:
            if bay.hour < gio or self._hen_da_xet.get(ma) == ngay:
                continue
            if ma == "hoc_hang_ngay" and self.kho_hoc is None:
                self._hen_da_xet[ma] = ngay
                log.warning("hẹn giờ: bỏ hoc_hang_ngay ngày %s — học tự động chưa bật (không mở được hoc.db)", ngay)
                continue
            if ma == "radar_uid_hang_ngay" and (self.kho_radar is None or han_muc_radar(self.hm)[0] < 1):
                self._hen_da_xet[ma] = ngay
                log.warning("hẹn giờ: bỏ radar_uid_hang_ngay ngày %s — %s", ngay,
                            "Radar UID chưa bật (không mở được radar_uid.db)" if self.kho_radar is None
                            else "cầu dao radar_uid_bat = 0")
                continue
            if self._da_co_viec_ngay(ma, ngay):
                self._hen_da_xet[ma] = ngay
                continue
            try:
                loai = self._loai(ma)
                ts = loai.kiem_tham_so({"ngay": ngay}, self.mt)
                tt0, buoc = loai.trang_thai_dau(ts)
                kiem_han_muc(self.kho, ma, ts, self.hm, "tao", "he_thong")
                v = self.kho.tao(ma, loai.tinh_khoa(ts), ts, loai.lan_chay, tt0, "he_thong", buoc=buoc)
            except (TrungViec, VuotHanMuc, ThamSoLoi) as e:
                self._hen_da_xet[ma] = ngay
                log.warning("hẹn giờ: không tạo %s ngày %s — %s: %s", ma, ngay, type(e).__name__, e)
                continue
            self._hen_da_xet[ma] = ngay
            tao.append(v["id"])
            log.info("hẹn giờ: đã tạo việc %s %s cho ngày %s", ma, v["id"], ngay)
        return tao

    # ---------------------------------------------------------------- D15: ghi vết áp dụng bài học (§3.7)
    def _ghi_ap_dung(self, loai: LoaiViec, viec: dict, ds_buoc: list[BuocChay]) -> None:
        """Sau lap_buoc_hieu_luc của phan_tich_uid: mã bài học runner đã chèn vào phiếu (stdin bước Claude) →
        kho_hoc.ghi_ap_dung. CHỈ bọc đúng chỗ ghi vết: lỗi → log.warning, KHÔNG làm hỏng việc phân tích (P3-8)."""
        if self.kho_hoc is None or loai.ma != "phan_tich_uid":
            return
        uid = str((viec.get("tham_so") or {}).get("uid") or "")
        for b in ds_buoc:
            if not b.la_claude:
                continue
            ma = phieu_mod.ma_goi_y_trong_phieu(b.stdin)
            if not ma:
                continue
            try:
                self.kho_hoc.ghi_ap_dung(ma, viec["id"], uid)
            except Exception as e:  # noqa: BLE001 — ghi vết là việc phụ, không chặn phân tích
                log.warning("việc %s: không ghi được vết áp dụng bài học (%s) — phân tích vẫn chạy",
                            viec.get("id"), type(e).__name__)

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

    # ---------------------------------------------------------------- A-3: cổng loại tốn tiền (§5.2, P2-10)
    def _khoa_cc(self):
        """Khoá công khai do chay_runner nạp MỘT lần (cùng đối tượng với API, P3-1). None → việc tốn tiền đứng chờ."""
        return self._kcc

    def _hoan_ton_tien(self, id: str, ma: str, ly: str) -> None:
        """dang_chay → cho (tạm hoãn cả loại `cho_lai_han_muc_s` giây), có ghi chú. Không tốn gì, không mất duyệt."""
        phut = max(1, int(round(self.cho_lai_han_muc_s / 60)))
        self._hoan_loai(ma, self.cho_lai_han_muc_s)
        self._ghi_log(id, f"{ly} — đứng chờ, thử lại sau {phut} phút")
        self._ket_thuc(id, "cho", TIEN_TO_HOAN + ly + f" — thử lại sau {phut} phút")

    def _chu_ky_hop_le(self, id: str, loai: LoaiViec, viec: dict) -> bool:
        """Kiểm chữ ký duyệt trên dữ liệu ĐANG LƯU. Sai → loi; thiếu khoá → hoãn. True = được chạy tiếp."""
        kcc = self._khoa_cc()
        if kcc is None:
            ly = "runner không có khoá công khai (ky_cong_khai.pem) để kiểm chữ ký duyệt"
            self._them_canh_bao(f"{ly} — việc tốn tiền đang đứng chờ; cài lại runner kèm khoá")
            self._hoan_ton_tien(id, loai.ma, ly)
            return False
        if chu_ky.kiem_duyet(kcc, viec):
            return True
        log.warning("việc %s (%s): %s — chặn lúc nhận", id, loai.ma, LOI_CHU_KY_DUYET)
        self._ghi_log(id, f"DỪNG: {LOI_CHU_KY_DUYET} — dữ liệu đang lưu không khớp lời duyệt đã ký")
        self._ket_thuc(id, "loi", LOI_CHU_KY_DUYET, loi=(
            f"{LOI_CHU_KY_DUYET}: tham số / lời duyệt / người duyệt / thời điểm duyệt đang lưu không khớp chữ ký, "
            "hoặc việc chưa được duyệt. Không chạy gì (không tốn tiền). Tạo lại việc và duyệt lại."))
        return False

    def _cong_ton_tien(self, id: str, loai: LoaiViec, viec: dict) -> bool:
        """Cổng §5.2 bước 1–3 khi nhận loại tốn tiền: (1) lệch tổng kiểm → hoãn; (2) chữ ký duyệt; (3) hạn mức lúc
        nhận. Bước 4 (tiêu lời duyệt) ở `_tieu_loi_duyet`, gọi NGAY trước lần sinh tiến trình đầu tiên của pha tốn
        tiền (sau điều kiện trước + lập lệnh + mọi kiểm cấu hình của bước — FX-18: lỗi cấu hình hay đứng chờ vì 'bận'
        không làm mất lời duyệt).
        True = được đi tiếp. False = đã chuyển trạng thái (loi / cho có ghi chú)."""
        if not can_kiem_duyet(loai, viec):
            return True                                     # genmax pha ước tính: không gọi API, chưa có duyệt
        if self.chan_ton_tien:
            self._them_canh_bao(CANH_BAO_LECH_TONG_KIEM)
            self._hoan_ton_tien(id, loai.ma, LY_DO_LECH_TONG_KIEM)
            return False
        if not self._chu_ky_hop_le(id, loai, viec):
            return False
        try:
            kiem_han_muc(self.kho, loai.ma, viec.get("tham_so") or {}, self.hm, "nhan",
                         viec.get("duyet_boi") or "he_thong", viec_id=id)
        except VuotHanMuc as e:
            self._hoan_ton_tien(id, loai.ma, f"vượt hạn mức lúc nhận: {e}")
            return False
        except ThamSoLoi as e:
            self._ket_thuc(id, "loi", "không kiểm được hạn mức", loi=f"Không kiểm được hạn mức lúc nhận: {e}")
            return False
        return True

    def _tieu_loi_duyet(self, id: str, loai: LoaiViec, ht: dict) -> bool:
        """§5.2 bước 4 (D9): tiêu lời duyệt MỘT lần cho lần chạy này, ngay trước khi sinh tiến trình tốn tiền.
        (a) sổ cục bộ đã có → loi; (b) Worker: da_tieu → ghi sổ + so_lan_tieu TRƯỚC khi chạy; da_dung → loi;
        chua_ro → đứng cho (hoãn loại) + cảnh báo. True = được sinh tiến trình."""
        ckd = ht.get("chu_ky_duyet")
        if not isinstance(ckd, str) or not ckd:          # _con_khop_duyet đã kiểm chữ ký; phòng thủ thêm
            self._ket_thuc(id, "loi", LOI_CHU_KY_DUYET, loi=f"{LOI_CHU_KY_DUYET}: thiếu chữ ký duyệt")
            return False
        if self.kho.da_tieu_cuc_bo(ckd):
            log.warning("việc %s (%s): %s (sổ cục bộ) — không chạy", id, loai.ma, LOI_DA_DUNG)
            self._chan_da_dung(id, "sổ đã tiêu trên máy này")
            return False
        if self._tieu is None:
            kq, mo_ta = "chua_ro", "runner chưa cấu hình bước tiêu lời duyệt"
        else:
            try:
                kq, mo_ta = self._tieu(id, ckd)
            except Exception as e:  # noqa: BLE001 — lỗi bất ngờ của bước tiêu: KHÔNG chạy, đứng chờ, có log
                log.exception("việc %s: lỗi bước tiêu lời duyệt", id)
                kq, mo_ta = "chua_ro", f"lỗi bước tiêu ({type(e).__name__})"
        mo_ta = self.che(str(mo_ta))[:200]
        if kq == "da_tieu":
            self.kho.ghi_tieu(id, ckd)                    # lỗi ghi → ném → chay_mot chuyển loi, KHÔNG chạy
            self._ghi_log(id, "đã tiêu lời duyệt trên Worker — bắt đầu pha tốn tiền")
            return True
        if kq == "da_dung":
            self.kho.danh_dau_da_tieu(ckd, id)
            self._chan_da_dung(id, mo_ta)
            return False
        ly = f"chưa tiêu được lời duyệt ({mo_ta})"
        self._them_canh_bao(f"Việc tốn tiền đứng chờ: {ly} — kiểm mạng tới Worker / khoá runner")
        self._hoan_ton_tien(id, loai.ma, ly)
        return False

    def _tieu_truoc_sinh(self, id: str, loai: LoaiViec, ht: dict, trang: dict) -> bool:
        """FX-18: gọi NGAY trước `tt.chay_tien_trinh`, sau mọi kiểm cấu hình của bước. Tiêu đúng 1 lần mỗi lần chạy
        (`trang['da']`). Việc không cần duyệt → True. True = được sinh tiến trình; False = đã chuyển trạng thái."""
        if trang["da"] or not loai.ton_tien or not can_kiem_duyet(loai, ht):
            return True
        if not self._tieu_loi_duyet(id, loai, ht):
            return False
        trang["da"] = True
        return True

    def _chan_da_dung(self, id: str, nguon: str) -> None:
        self._ghi_log(id, f"DỪNG: {LOI_DA_DUNG} ({nguon}) — không chạy gì (không tốn tiền)")
        self._ket_thuc(id, "loi", LOI_DA_DUNG, loi=(
            f"{LOI_DA_DUNG_DAY_DU}. Mỗi lời duyệt chỉ chạy được pha tốn tiền một lần ({nguon}). Không chạy gì "
            "(không tốn tiền)."))

    def _con_khop_duyet(self, id: str, loai: LoaiViec, viec: dict, ht: dict) -> bool:
        """Trước mỗi bước của việc tốn tiền: bản đang lưu vẫn là bản đã kiểm (tham_so, buoc) và chữ ký vẫn đúng."""
        if not can_kiem_duyet(loai, viec):
            return True
        if ht.get("tham_so") != viec.get("tham_so") or ht.get("buoc") != viec.get("buoc"):
            self._ket_thuc(id, "loi", LOI_CHU_KY_DUYET, loi=(
                f"{LOI_CHU_KY_DUYET}: tham số/bước của việc bị đổi trong lúc chạy — dừng, không chạy bước kế"))
            return False
        return self._chu_ky_hop_le(id, loai, ht)

    def _xong_uoc_tinh_genmax(self, id: str, ts: dict, dong: list[str]) -> None:
        """voice_genmax pha ước tính chạy xong → cho_duyet (có ước tính để web hiện). Không bao giờ → xong/chạy tiếp
        pha gọi API ở đây: pha chay chỉ đến sau POST /duyet (buoc='chay' + chữ ký)."""
        van_ban = "\n".join(dong)
        ut = doc_uoc_tinh_genmax(van_ban)
        duoi = self.che(van_ban)[-1500:]
        if ut is None:
            self._ket_thuc(id, "loi", "không đọc được ước tính GenMax", loi=(
                "Pha ước tính GenMax không in đúng một dòng 'Kế hoạch: N lượt GenMax, tổng K ký tự: […]' — không đưa "
                f"sang chờ duyệt. Cuối log:\n{duoi[-800:]}"))
            return
        ma_ban = ts.get("ma_ban") if isinstance(ts.get("ma_ban"), list) else []
        la = [m for m in ut["ma"] if m not in ma_ban]
        if la:
            self._ket_thuc(id, "loi", "ước tính GenMax lạ", loi=(
                f"Ước tính GenMax có mã ngoài danh sách đã ghim: {', '.join(la[:10])} — không đưa sang chờ duyệt"))
            return
        if ut["so_ban"] and not ut["chua_goi_api"]:
            self._ket_thuc(id, "loi", "ước tính GenMax thiếu xác nhận", loi=(
                "Pha ước tính GenMax không in 'CHƯA gọi API' — không chắc script chưa gọi API, kiểm tay log việc"))
            return
        uoc = {"so_ban": ut["so_ban"], "ky_tu": ut["ky_tu"], "ma": ut["ma"], "bo_qua": ut["bo_qua"],
               "canh_bao": [self.che(c)[:300] for c in ut["canh_bao"]], "dong": self.che(ut["dong"])[:500]}
        ket_qua = {"trang_thai_agent": None, "co_lo_ngai": bool(ut["canh_bao"]), "tom_tat": duoi,
                   "file_ra": [], "goi_y_viec": [], "uoc_tinh": uoc}
        if ut["so_ban"] == 0:
            ket_qua["tom_tat"] = "Không có bản nào cần tạo voice GenMax (đã có voice) — không cần duyệt, không tốn tiền"
            self._ket_thuc(id, "xong", "ước tính: 0 bản cần tạo", ket_qua=ket_qua)
            return
        tom = (f"Kế hoạch: {ut['so_ban']} bản GenMax, tổng {ut['ky_tu']} ký tự ({', '.join(ut['ma'])})"
               + (f"; bỏ qua {len(ut['bo_qua'])} bản đã có voice" if ut["bo_qua"] else "")
               + (f"; cảnh báo: {' | '.join(uoc['canh_bao'])}" if uoc["canh_bao"] else ""))
        self._ghi_log(id, "ước tính xong — chờ duyệt: " + tom)
        self._ket_thuc(id, "cho_duyet", "ước tính xong — chờ duyệt", uoc_tinh=self.che(tom), ket_qua=ket_qua)

    def _chay(self, viec: dict, huy: threading.Event) -> None:
        id = viec["id"]
        ts = viec.get("tham_so") or {}
        try:
            loai = self._loai(viec["loai"])
        except ThamSoLoi as e:
            self._ket_thuc(id, "loi", "loại không chạy được", loi=str(e))
            return
        self._ghi_log(id, f"lần {viec.get('lan_thu')}: bắt đầu {loai.ma}")

        if loai.ton_tien:
            # A-3 (P2-10): kiểm trên bản ĐANG LƯU, rồi lập lệnh từ chính bản đã kiểm
            moi = self.kho.lay(id)
            if moi is None or moi["trang_thai"] != "dang_chay":
                log.info("việc %s không còn dang_chay trước khi kiểm duyệt — dừng", id)
                return
            viec, ts = moi, moi.get("tham_so") or {}
            if not self._cong_ton_tien(id, loai, viec):
                return

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

        if loai.ma in LOAI_PHIEN_SONG:
            # §7.4 (A-5): mỗi lần sinh phiên sống dùng session_id uuid4 MỚI, phien_da_tao=0 (không bao giờ --resume)
            try:
                viec = self.kho.chuyen(id, ["dang_chay"], "dang_chay", "he_thong", "phiên sống: session_id mới",
                                       session_id=str(uuid.uuid4()), phien_da_tao=0,
                                       bat_dau_luc=viec.get("bat_dau_luc"))
            except SaiTrangThai as e:
                log.info("việc %s không còn dang_chay trước khi lập phiên sống: %s", id, e)
                return
            ts = viec.get("tham_so") or {}

        try:
            ds_buoc = lap_buoc_hieu_luc(loai, ts, viec, self.mt, self.hm)   # FX-29: phiếu theo hm đang giữ
        except ThamSoLoi as e:
            self._ket_thuc(id, "loi", "không lập được các bước", loi=f"Không lập được lệnh: {e}")
            return
        self._ghi_ap_dung(loai, viec, ds_buoc)               # D15 §3.7: lỗi ghi vết chỉ log, việc chạy tiếp

        lo_ngai: list[str] = []
        them_kq: dict = {}
        kq_claude: dict | None = None
        dong_cuoi = ""
        trang_tieu = {"da": False}                          # D9: tiêu lời duyệt đúng 1 lần mỗi lần chạy
        for i, b in enumerate(ds_buoc):
            la_cuoi = i == len(ds_buoc) - 1
            if huy.is_set():
                self._xu_ly_dung(id, loai, viec, "huỷ trước bước " + b.ten)
                return
            ht = self.kho.lay(id)
            if ht is None or ht["trang_thai"] != "dang_chay":
                log.info("việc %s không còn dang_chay trước bước %s — dừng", id, b.ten)
                return
            if loai.ton_tien and not self._con_khop_duyet(id, loai, viec, ht):
                return
            cnd = kiem_truoc_buoc(loai, b.ten, ts, ht, self.mt)
            if cnd is not None:
                self._ket_thuc(id, "can_tra_loi", f"trước bước {b.ten}", cau_hoi=cnd)
                return
            # FX-18 (R-15 P3-2): tiêu lời duyệt là việc CUỐI, ngay trước khi sinh tiến trình — chạy BÊN TRONG
            # _buoc_claude/_buoc_script sau mọi kiểm cấu hình (lệnh, cwd, resume, stdin/phiếu, file log phụ).
            def truoc_sinh(h: dict = ht) -> bool:
                return self._tieu_truoc_sinh(id, loai, h, trang_tieu)
            if b.song:
                self._buoc_claude_song(loai, ht, b, huy, truoc_sinh)    # tự chuyển trạng thái cuối
                return
            if b.la_claude:
                kq_claude = self._buoc_claude(loai, ht, b, huy, la_cuoi, truoc_sinh)
                if kq_claude is None:
                    return                          # đã chuyển trạng thái
                continue
            ok, dong = self._buoc_script(loai, ht, b, huy, truoc_sinh)
            if not ok:
                return
            if loai.ma == "voice_genmax" and b.ten == BUOC_UOC_TINH_GENMAX:
                self._xong_uoc_tinh_genmax(id, ts, dong)    # §5.2: pha ước tính → cho_duyet (0 bản → xong)
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
    def _buoc_script(self, loai: LoaiViec, viec: dict, b: BuocChay, huy: threading.Event,
                     truoc_sinh: Callable[[], bool] = lambda: True) -> tuple[bool, list[str]]:
        id = viec["id"]
        loi_cau_hinh = loi_khong_sinh_duoc(b)
        if loi_cau_hinh is not None:                       # FX-18: kiểm TRƯỚC khi tiêu lời duyệt
            self._ket_thuc(id, "loi", f"bước {b.ten} cấu hình sai",
                           loi=self.che(f"Không chạy được bước {b.ten}: {loi_cau_hinh} (chưa tiêu lời duyệt)"))
            return False, []
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
            if not truoc_sinh():                           # FX-18: tiêu lời duyệt — việc cuối trước khi sinh
                return False, dong                         # finally vẫn đóng f_phu
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
                     la_cuoi: bool, truoc_sinh: Callable[[], bool] = lambda: True) -> dict | None:
        """Chạy bước Claude. Trả ket_qua (dict) nếu xong và còn bước sau; None nếu đã chuyển trạng thái.
        FX-18: mọi kiểm cấu hình (lệnh/cwd, --resume, lập stdin) chạy TRƯỚC `truoc_sinh` (tiêu lời duyệt)."""
        id = viec["id"]
        loi_cau_hinh = loi_khong_sinh_duoc(b)
        if loi_cau_hinh is not None:
            self._ket_thuc(id, "loi", "lệnh Claude sai",
                           loi=self.che(f"Không chạy được Claude: {loi_cau_hinh} (chưa tiêu lời duyệt)"))
            return None
        stdin = b.stdin
        # FX-15: lượt đi từ duyệt lại (xin-duyet-lai) → báo agent lý do, đúng một lần
        ly_dl = ly_do_duyet_lai_can_dung(loai, viec, self.kho.su_kien(id)) if loai.ton_tien else None
        if viec.get("phien_da_tao"):
            if "--resume" not in b.argv:
                self._ket_thuc(id, "loi", "lệnh Claude sai", loi="phiên đã tạo nhưng lệnh không có --resume")
                return None
            try:
                stdin = (lap_tin_sau_duyet_lai(viec, self.che(ly_dl), None) if ly_dl is not None
                         else lap_tin_resume(viec, self.kho.su_kien(id), self.kho.tra_loi_cua(id)))
            except ThamSoLoi as e:
                self._ket_thuc(id, "loi", "không lập được tin tiếp", loi=f"Không lập được tin resume: {e}")
                return None
        elif ly_dl is not None and stdin is not None:
            stdin = lap_tin_sau_duyet_lai(viec, self.che(ly_dl), stdin)
        if stdin is None:
            self._ket_thuc(id, "loi", "thiếu phiếu", loi="bước Claude không có stdin (phiếu)")
            return None
        # FX-18: hết kiểm cấu hình → tiêu lời duyệt. Đặt TRƯỚC khi xoá khoá duyệt lại: tiêu chưa được (đứng chờ)
        # thì lý do duyệt lại vẫn còn cho lượt sau.
        if not truoc_sinh():
            return None
        sid_goc = viec.get("session_id")
        soat = sj.SoatCongCu(loai.bo_cong_cu)            # mỗi lượt chạy một bộ soát mới (trạng thái init)
        # §5.3: trần lượt Codex là MỖI VIỆC → cộng dồn từ ket_qua.so_codex của các lượt trước
        kq_truoc = viec.get("ket_qua") if isinstance(viec.get("ket_qua"), dict) else {}
        if ly_dl is not None:
            # FX-15: đã đưa lý do vào stdin → xoá 2 khoá khỏi ket_qua TRƯỚC khi sinh tiến trình (không sót sang lượt
            # sau, kể cả khi lượt này chết giữa chừng); giữ mọi khoá khác. Ghi hỏng → không chạy Claude.
            kq_truoc = bo_khoa_duyet_lai(kq_truoc)
            try:
                self.kho.chuyen(id, ["dang_chay"], "dang_chay", "he_thong", "đã đưa lý do duyệt lại vào lượt Claude",
                                ket_qua=kq_truoc, bat_dau_luc=viec.get("bat_dau_luc"))
            except SaiTrangThai as e:
                log.warning("việc %s: không xoá được lý do duyệt lại (việc không còn dang_chay) — không chạy Claude: %s",
                            id, e)
                self._ghi_log(id, f"dừng: không xoá được lý do duyệt lại khỏi ket_qua ({e}) — không chạy Claude")
                return None
        tran_cx = tran_codex(self.hm)
        codex = {"n": _so_nguyen_khong_am(kq_truoc.get("so_codex"))}

        def kq_codex(goc: object = None) -> dict:
            """ket_qua để ghi kèm so_codex: `goc` (dict) nếu có, ngược lại ket_qua đang lưu của việc."""
            d = dict(goc) if isinstance(goc, dict) else dict(kq_truoc)
            d["so_codex"] = codex["n"]
            return d

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
                n = dem_codex(sk)
                if n:
                    codex["n"] += n
                    if codex["n"] > tran_cx:
                        raise VuotTranCodex(codex["n"], tran_cx)

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
                    "MCP/agent của Claude trên máy trước khi chạy lại."),
                    **({"ket_qua": kq_codex()} if codex["n"] else {}))
            return None
        except VuotTranCodex as e:
            self._ghi_log(id, f"DỪNG: chạm trần lượt Codex ({e}) — đã giết cả cây Claude")
            log.warning("việc %s: chạm trần lượt Codex (%s)", id, e)
            if not self._khong_giet_tu_loi(id, e):
                self._ket_thuc(id, "can_tra_loi", "chạm trần lượt Codex", cau_hoi=CanNguoiDung("khong_ro", (
                    f"Đã chạm trần lượt Codex ({e.tran} lần gọi subagent codex mỗi việc; lần này là lần {e.so}) — "
                    "Claude đã bị dừng cả cây. Bấm Tiếp tục để chạy tiếp (gọi Codex thêm sẽ bị dừng lại) hoặc Huỷ")),
                    ket_qua=kq_codex())
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
            if codex["n"]:
                truong["ket_qua"] = kq_codex(truong.get("ket_qua"))
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
        ket_qua["so_codex"] = codex["n"]                     # §5.3: cộng dồn cả việc (A-3)
        if k.get("bi_tu_choi"):
            ket_qua["bi_tu_choi"] = gon_bi_tu_choi(k["bi_tu_choi"], self.che)
        if loai.ma == "phan_tich_uid" and den == "xong" and dau_ra == "xong_lo_ngai":
            ket_qua.update(self._tao_con_douyin(viec, ket_qua))      # A-5 b): thiếu douyin.md → việc con douyin_uid
        truong["ket_qua"] = ket_qua
        if den == "xong" and not la_cuoi:
            return ket_qua
        self._ket_thuc(id, den, f"agent: {kqa.trang_thai}", **truong)
        return None

    def _tao_con_douyin(self, viec: dict, ket_qua: dict) -> dict:
        """A-5 b): phan_tich_uid xong mà đối soát thiếu douyin.md (phiếu đã ghi DONG_DOUYIN_RIENG) → runner tự tạo việc
        con douyin_uid (miễn phí) cho cùng UID, như _tao_con_link. Đã có douyin_uid mở cho UID đó → không tạo trùng
        (khoá việc = uid, KhoViec.tao ném TrungViec). Tạo được / đã có → bỏ nút gợi ý "Chạy Douyin"."""
        ra: dict = {}
        uid = (viec.get("tham_so") or {}).get("uid")
        try:
            loai_con = self._loai("douyin_uid")
            ts = loai_con.kiem_tham_so({"uid": uid}, self.mt)
            tt0, buoc = loai_con.trang_thai_dau(ts)
            kiem_han_muc(self.kho, loai_con.ma, ts, self.hm, "tao", viec["tao_boi"])
            con = self.kho.tao(loai_con.ma, loai_con.tinh_khoa(ts), ts, loai_con.lan_chay, tt0, viec["tao_boi"],
                               buoc=buoc, session_id=None, cha_id=viec["id"])
            ra["viec_con_douyin"] = con["id"]
            ghi = f"Douyin do runner chạy riêng: đã tạo việc douyin_uid {con['id']}"
        except TrungViec as e:
            ra["viec_con_douyin"] = e.viec.get("id")
            ra["douyin_trung"] = True
            ghi = f"Douyin do runner chạy riêng: đã có việc douyin_uid {e.viec.get('id')} đang mở"
        except (VuotHanMuc, ThamSoLoi) as e:
            ra["loi_con_douyin"] = self.che(str(e))[:300]
            self._ghi_log(viec["id"], f"không tạo được việc con douyin_uid: {e}")
            return ra
        self._ghi_log(viec["id"], ghi)
        ra["goi_y_viec"] = [g for g in ket_qua.get("goi_y_viec") or [] if g != "douyin_uid"]
        ra["lo_ngai"] = ghi
        return ra

    # ---------------------------------------------------------------- bước Claude SỐNG (đợt 5, A-5, §7.2–7.8)
    def _ket_thuc_song(self, id: str, den: str, ghi_chu: str, **truong) -> dict | None:
        """Kết thúc phiên sống: dang_chay|can_tra_loi → den; xoá pid, câu hỏi, can_ban (§7.4)."""
        truong.setdefault("cau_hoi", None)
        truong.setdefault("can_ban", None)
        return self._ket_thuc(id, den, ghi_chu, tu=("dang_chay", "can_tra_loi"), **truong)

    def _chuyen_song(self, id: str, tu: list[str], den: str, ghi_chu: str, bat_dau_luc: str | None,
                     **truong) -> dict | None:
        """Chuyển trong phiên (giữ pid, giữ bat_dau_luc). Việc đã đổi ngoài (huỷ) → log, None."""
        if den == "dang_chay":
            truong["bat_dau_luc"] = bat_dau_luc
        try:
            return self.kho.chuyen(id, tu, den, "he_thong", self.che(ghi_chu),
                                   **che_truong_ket_thuc(truong, self.che))
        except SaiTrangThai as e:
            log.info("việc %s: bỏ qua chuyển %s → %s trong phiên sống: %s", id, tu, den, e)
            return None

    def _buoc_claude_song(self, loai: LoaiViec, viec: dict, b: BuocChay, huy: threading.Event,
                          truoc_sinh: Callable[[], bool]) -> None:
        """§7.2–7.8: MỘT phiên Claude sống cho cả việc. Luôn tự chuyển trạng thái cuối (hoặc để nguyên khi runner tắt
        để lần khởi động sau đối soát). Mọi kiểm cấu hình chạy TRƯỚC `truoc_sinh` (tiêu lời duyệt, FX-18)."""
        id = viec["id"]
        ts = viec.get("tham_so") or {}
        loi_cau_hinh = loi_khong_sinh_duoc(b)
        if loi_cau_hinh is not None:
            self._ket_thuc(id, "loi", "lệnh Claude sai",
                           loi=self.che(f"Không chạy được Claude: {loi_cau_hinh} (chưa tiêu lời duyệt)"))
            return
        hg = het_gio_taovideo(self.hm)
        lam_s = min(int(b.het_gio_s), hg["lam_s"]) if b.het_gio_s and b.het_gio_s > 0 else hg["lam_s"]
        tran_usd = float(_tran_hieu_luc(self.hm, "taovideo_usd_viec"))
        tran_mp3 = int(_tran_hieu_luc(self.hm, "taovideo_mp3_viec"))
        tran_cx = tran_codex(self.hm)
        tran_luot = loai.tran_luot
        ly_dl = ly_do_duyet_lai_can_dung(loai, viec, self.kho.su_kien(id))
        so_lan_truoc = _so_nguyen_khong_am(viec.get("so_lan_tieu"))
        try:
            argv = dat_max_budget(b.argv, tran_usd)
            a = tim_du_an(ts.get("du_an_a"), ts.get("uid"), self.mt.gocs)
            if a is None:
                raise ThamSoLoi("không còn thấy dự án A")
            if ly_dl is not None or so_lan_truoc > 0:
                # §7.10: lần chạy tiếp (sau xin duyệt lại) — phiên MỚI, phiếu "LẦN CHẠY TIẾP"
                ly = ly_dl if ly_dl is not None else (viec.get("loi") or "phiên trước đã dừng")
                stdin = lap_phieu_tiep_taovideo(loai, dict(viec, lan_thu=so_lan_truoc + 1), self.mt, self._dot_bat,
                                                self.che(ly), self.kho.tra_loi_cua(id), hm=self.hm)
            else:
                stdin = b.stdin
            if not isinstance(stdin, str) or not stdin.strip():
                raise ThamSoLoi("bước phiên sống không có phiếu")
        except ThamSoLoi as e:
            self._ket_thuc(id, "loi", "không lập được phiên sống",
                           loi=self.che(f"Không lập được phiên sống: {e} (chưa tiêu lời duyệt)"))
            return
        if not truoc_sinh():                                   # tiêu lời duyệt — việc cuối trước khi sinh
            return
        # §7.5: lời duyệt mới → Codex đếm lại từ 0; bỏ khoá duyệt lại + câu hỏi treo đã đưa vào phiếu
        kq_goc = {k: v for k, v in bo_khoa_duyet_lai(viec.get("ket_qua")).items() if k != "cau_hoi_treo"}
        kq_goc["so_codex"] = 0
        bat_dau_luc = viec.get("bat_dau_luc")
        if self._chuyen_song(id, ["dang_chay"], "dang_chay", "bắt đầu phiên sống (đã tiêu lời duyệt)", bat_dau_luc,
                             ket_qua=kq_goc, cau_hoi=None, can_ban=None) is None:
            self._ghi_log(id, "dừng: việc không còn dang_chay ngay sau khi tiêu lời duyệt — không sinh phiên")
            return

        td = TheoDoiPhien(self._dot_bat, self.che)
        ch = ps.CauHinhPhien(argv=argv, cwd=b.cwd, env=tt.env_toi_thieu(dict(b.env_them)),
                             file_log=self.thu_muc_log / f"{id}.log", file_jsonl=self.thu_muc_log / f"{id}.jsonl",
                             im_lang_s=self.im_lang_song_s)
        phien = ps.PhienSong(ch, td, self.che)
        tp = _TrangPhien(phien)
        soat = sj.SoatCongCu(set(loai.bo_cong_cu) | {"Agent", "Task"})   # S-4 mục 3: init báo Task, tool_use Agent
        sid_cho = viec.get("session_id")
        st: dict = {"loi": None, "cau_hoi_treo": None, "loi_luot": None, "dong": None, "bat_dau": None,
                    "moc_mp3": None, "mp3": set(), "lan_quet": float("-inf"), "cho_nen_tu": None, "kl": 0,
                    "luot_ghi": 0, "da_danh_dau": False, "bao_ver": False, "can_ban": None}

        def dung(ly: str) -> None:
            if st["loi"] is None:
                st["loi"] = ly
                self._ghi_log(id, f"DỪNG phiên sống: {ly}")
                log.warning("việc %s: dừng phiên sống — %s", id, ly)
            phien.giet(ly)

        def dat_can_ban(s: str | None) -> None:
            if st["can_ban"] == s:
                return
            st["can_ban"] = s
            self._chuyen_song(id, ["dang_chay"], "dang_chay", s or "hết chờ việc nền", bat_dau_luc, can_ban=s)

        def khi_bat_dau(pid: int, tl: float) -> None:
            st["bat_dau"] = time.monotonic()
            st["moc_mp3"] = datetime.fromtimestamp(float(tl), MUI_GIO_VN)
            self.kho.ghi_tien_trinh(id, pid, tl)
            self.kho.cong_chi_phi(id, 0.0, 0, True)          # §6.3: đếm lần gọi ngay khi bắt đầu

        def khi_su_kien(sk: dict, luc: float, d: float) -> None:
            ngoai = soat.xet(sk)
            if ngoai:
                dung("Phiên Claude có công cụ ngoài danh sách cho phép (" + self.che(", ".join(ngoai))[:300]
                     + ") — kiểm cấu hình MCP/agent của Claude trên máy trước khi chạy lại")
                return
            sid = sj.la_khoi_tao(sk)
            if sid is not None and not st["da_danh_dau"]:
                st["da_danh_dau"] = True
                if sid != sid_cho:
                    log.warning("việc %s: phiên sống đổi id %s → %s", id, sid_cho, sid)
                    self._chuyen_song(id, ["dang_chay", "can_tra_loi"], "dang_chay", "phiên Claude đổi id",
                                      bat_dau_luc, session_id=sid)
                self.kho.danh_dau_phien(id)
            ver = sj.phien_ban_claude(sk)
            if ver is not None and ver != PHIEN_BAN_CLAUDE_DA_DO and not st["bao_ver"]:
                st["bao_ver"] = True
                c = (f"Claude CLI bản {ver} khác bản đã đo {PHIEN_BAN_CLAUDE_DA_DO} — phiên sống có thể chạy khác "
                     "(không chặn)")
                self._ghi_log(id, "CẢNH BÁO: " + c)
                log.warning("việc %s: %s", id, c)
                # FX-27 P3-2: giữ cảnh báo trong ket_qua.canh_bao (can_ban bị nhánh 'hoi' xoá)
                kq_goc.setdefault("canh_bao", []).append(c)
                st["can_ban"] = c
                self._chuyen_song(id, ["dang_chay"], "dang_chay", c, bat_dau_luc, can_ban=c, ket_qua=dict(kq_goc))
            if sk.get("type") == "result" and sj.la_cap_cao(sk):
                so_moi = max(0, td.so_luot - st["luot_ghi"])
                st["luot_ghi"] = td.so_luot
                try:
                    self.kho.cong_chi_phi(id, d, so_moi, False)
                except SaiTrangThai as e:
                    log.warning("việc %s: KHÔNG ghi được chi phí phiên sống (%.4f USD): %s", id, d, e)
                    self._ghi_log(id, f"cảnh báo: không ghi được chi phí ({d:.4f} USD): {e}")
                if sk.get("subtype") == "error_max_budget_usd":
                    # §7.2 (S-4 #5): CLI đã chặn mọi lượt sau → đóng stdin (thoát gọn), loi; mã 1 không phải tự chết
                    if st["loi"] is None:
                        st["loi"] = (f"Chạm trần USD của phiên (--max-budget-usd {tran_usd:g} USD-ước-tính, Claude "
                                     "báo error_max_budget_usd)")
                        self._ghi_log(id, f"DỪNG phiên sống: {st['loi']} — đóng stdin")
                    phien.dong()
                    return
            if td.chi_phi_usd > tran_usd:
                dung(f"Vượt trần {tran_usd:g} USD-ước-tính của phiên (đã {td.chi_phi_usd:.2f} USD)")
            elif td.so_codex > tran_cx:
                dung(f"Vượt trần Codex: {td.so_codex} lần gọi Codex > trần {tran_cx} của lần duyệt này")
            elif tran_luot is not None and td.so_luot > tran_luot:
                dung(f"Vượt trần {tran_luot} lượt assistant của phiên")
            elif td.so_codex >= tran_cx:
                with self._khoa_song:
                    if not tp.da_bao_codex and not tp.bao_codex_cho:
                        tp.bao_codex_cho = True

        def khi_nhip(tinh: TinhTrang, luc: float) -> None:
            if st["loi"] is not None or st["dong"] is not None or st["loi_luot"] is not None:
                return
            if st["bat_dau"] is None:
                return
            if luc - st["lan_quet"] >= self.quet_mp3_s and st["moc_mp3"] is not None:
                st["lan_quet"] = luc
                st["mp3"] |= mp3_adam_moi(a, st["moc_mp3"])
                if len(st["mp3"]) > tran_mp3:
                    dung(f"vượt trần voice GenMax (đếm file thật): {len(st['mp3'])} file *_adam.mp3 mới > trần "
                         f"{tran_mp3}")
                    return
            with self._khoa_song:
                if tp.tra_loi_cho and tp.cau_hoi is not None and phien.da_ghi_tra_loi(tp.cau_hoi.ma):
                    # FX-27 P2-1: chính tin trả lời đã ghi stdin (không dựa so_tin_cho — tin hệ thống có thể còn chờ)
                    tp.tra_loi_cho = False
                    tp.cau_hoi = None
                cho_hien = (luc - tp.cho_tu) if tp.cho_tu is not None else 0.0
                lam = luc - st["bat_dau"] - tp.tong_cho - cho_hien
                cau_treo = tp.cau_hoi.noi_dung if (tp.cau_hoi is not None and not tp.tra_loi_cho) else None
            if luc - st["bat_dau"] > hg["tong_s"]:
                dung(f"Quá trần tuyệt đối {gio_doc(hg['tong_s'])} của phiên")
                return
            if lam > lam_s:
                dung(f"Quá giờ làm {gio_doc(lam_s)} — Claude bị dừng cả cây")
                return
            if st["cho_nen_tu"] is not None and luc - st["cho_nen_tu"] > hg["nen_s"]:
                dung(f"Việc nền chạy quá {gio_doc(hg['nen_s'])}")
                return
            if cau_treo is not None and cho_hien > hg["cho_s"]:
                st["loi"] = f"Hết giờ chờ trả lời câu hỏi: {cau_treo}"
                st["cau_hoi_treo"] = cau_treo
                if tinh.so_viec_nen == 0:
                    self._ghi_log(id, f"hết giờ chờ trả lời ({gio_doc(hg['cho_s'])}), không còn việc nền — đóng stdin")
                    phien.dong()
                else:
                    self._ghi_log(id, f"hết giờ chờ trả lời ({gio_doc(hg['cho_s'])}), còn {tinh.so_viec_nen} việc "
                                      "nền — giết cả cây")
                    phien.giet("hết giờ chờ trả lời khi còn việc nền")
                return
            if tinh.loai == "dang_lam":
                if st["cho_nen_tu"] is not None:
                    st["cho_nen_tu"] = None
                    dat_can_ban(None)
                return
            if tinh.so_ket_luot <= st["kl"]:
                return
            st["kl"] = tinh.so_ket_luot
            if tinh.loai == "loi_luot":
                st["loi_luot"] = tinh.van_ban
                self._ghi_log(id, "lượt Claude báo lỗi — đóng phiên")
                phien.dong()
                return
            kqa = tinh.ket_qua
            hd = anh_xa_ket_luot_song(kqa, tinh.so_viec_nen, tp.da_nhac)
            with self._khoa_song:
                if tp.chi_dao_cho:
                    if phien.so_tin_cho > 0:
                        # chỉ đạo của chủ shop chưa ghi: không đóng/hỏi/nhắc — PhienSong ghi nó ngay sau nhịp này
                        self._ghi_log(id, f"agent kết lượt ({getattr(kqa, 'trang_thai', '?')}) — gửi chỉ đạo của chủ "
                                          "shop trước")
                        return
                    tp.chi_dao_cho = False
                if tp.cau_hoi is not None:
                    n = phien.bo_hang_doi() if tp.tra_loi_cho else 0
                    if hd.loai != "hoi":
                        # §7.3: ket_luot mới không có CẦN_USER → câu cũ bị agent rút lại; tin trả lời xếp hàng bị huỷ
                        self._ghi_log(id, f"agent rút lại câu hỏi \"{tp.cau_hoi.noi_dung[:120]}\" — huỷ {n} tin trả "
                                          "lời chưa gửi")
                        tp.cau_hoi, tp.tra_loi_cho = None, False
                        tp.ket_thuc_cho(luc)
                        self._chuyen_song(id, ["can_tra_loi"], "dang_chay", "agent rút lại câu hỏi", bat_dau_luc,
                                          cau_hoi=None)
                    elif n:
                        self._ghi_log(id, f"agent hỏi câu mới — huỷ {n} tin trả lời cho câu cũ chưa gửi")
                elif phien.so_tin_cho > 0 and hd.loai != "dong":
                    return                         # tin đang chờ (vd TIN_TRAN_CODEX) sẽ thức agent; xét lượt sau
                if hd.loai == "dong":
                    st["dong"] = (kqa, hd.ghi_chu)
                    self._ghi_log(id, f"agent báo cáo cuối ({kqa.trang_thai}) — đóng stdin")
                    phien.dong()
                    return
                if hd.loai == "hoi":
                    # §7.6 (FX-26): mã câu hỏi mới, gắn với result sinh ra câu hỏi (PhienSong bỏ trả lời mã cũ)
                    ma = "q" + secrets.token_hex(6)
                    ch_ = che_truong_ket_thuc({"cau_hoi": dataclasses.replace(hd.cau_hoi, ma=ma)},
                                              self.che)["cau_hoi"]
                    phien.dat_cau_hoi(ma, tinh.so_ket_luot)
                    tp.ket_thuc_cho(luc)
                    tp.cau_hoi, tp.tra_loi_cho, tp.cho_tu, tp.da_nhac = ch_, False, luc, False
                    st["cho_nen_tu"] = None
                    st["can_ban"] = None
                    self._chuyen_song(id, ["dang_chay", "can_tra_loi"], "can_tra_loi", "agent hỏi (phiên sống)",
                                      bat_dau_luc, cau_hoi=ch_, can_ban=None)
                    self._ghi_log(id, f"agent hỏi ({ch_.loai}, mã {ma}): {ch_.noi_dung[:200]} — chờ trả lời ≤ "
                                      f"{gio_doc(hg['cho_s'])}")
                    return
                if tp.bao_codex_cho:
                    phien.gui(TIN_TRAN_CODEX.format(n=tran_cx))
                    tp.bao_codex_cho, tp.da_bao_codex = False, True
                    self._ghi_log(id, f"đã dùng hết {tran_cx} lượt Codex — gửi TIN_TRAN_CODEX")
                    if hd.loai == "nhac":
                        return
                if hd.loai == "nhac":
                    phien.gui(hd.tin_gui or TIN_NHAC)
                    tp.da_nhac = True
                    self._ghi_log(id, "agent kết lượt không rõ trạng thái, không còn việc nền — nhắc 1 lần")
                    return
            if hd.loai == "cho_nen":
                if st["cho_nen_tu"] is None:
                    st["cho_nen_tu"] = luc
                dat_can_ban(hd.ghi_chu)

        phien.gui(stdin)
        tp.ngat = dung
        with self._khoa_song:
            self._phien[id] = tp
        self._ghi_log(id, f"sinh phiên sống (trần: {tran_usd:g} USD, {tran_mp3} mp3, {tran_cx} Codex, làm "
                          f"{gio_doc(lam_s)}, chờ {gio_doc(hg['cho_s'])}, nền {gio_doc(hg['nen_s'])}, "
                          f"tổng {gio_doc(hg['tong_s'])})")
        kq: ps.KetQuaPhien | None = None
        loi_chay: BaseException | None = None
        try:
            try:
                kq = phien.chay(khi_bat_dau, khi_su_kien, khi_nhip, huy)
            except Exception as e:  # noqa: BLE001 — chốt trạng thái ở dưới (kể cả can_tra_loi), không để kẹt
                loi_chay = e
            self._ket_thuc_phien(loai, viec, kq, loi_chay, st, td, tp, huy, kq_goc)
        finally:
            # FX-27 P2-2: chỉ bỏ đăng ký SAU khi đã chốt trạng thái cuối → co_phien_song True suốt khoảng này
            with self._khoa_song:
                self._phien.pop(id, None)

    def _ket_thuc_phien(self, loai: LoaiViec, viec: dict, kq: "ps.KetQuaPhien | None", loi_chay: BaseException | None,
                        st: dict, td: TheoDoiPhien, tp: _TrangPhien, huy: threading.Event,
                        kq_goc: dict) -> None:
        """Chốt trạng thái sau khi phiên sống kết thúc (§7.4, §7.7, §7.8)."""
        id = viec["id"]
        ket_qua = dict(kq_goc)
        ket_qua.update({"so_codex": td.so_codex, "chi_phi_usd_phien": round(td.chi_phi_usd, 6),
                        "so_luot_phien": td.so_luot})
        tu_moc = st["moc_mp3"]
        # a) câu hỏi còn treo khi phiên đóng (hết giờ chờ, hoặc dừng vì lý do khác lúc đang hỏi) → phiếu LẦN CHẠY TIẾP
        with self._khoa_song:
            treo = st["cau_hoi_treo"] or (tp.cau_hoi.noi_dung if tp.cau_hoi is not None and not tp.tra_loi_cho
                                          else None)
        if loi_chay is not None:
            v = tt.khong_giet_tu_loi(loi_chay)
            if v is not None:
                self._chuyen_song(id, ["can_tra_loi"], "dang_chay", "phiên sống: không giết được",
                                  viec.get("bat_dau_luc"))
                self._khong_giet(id, v[0], v[1], f"khi dọn phiên sống sau lỗi {type(loi_chay).__name__}")
                return
            log.error("việc %s: lỗi phiên sống: %r", id, loi_chay)
            if isinstance(loi_chay, OSError) and st["bat_dau"] is None:
                ly = f"Không chạy được Claude: {loi_chay}"
            else:
                ly = f"Lỗi bộ chạy phiên sống: {type(loi_chay).__name__}: {loi_chay}"
            self._ghi_log(id, ly)
            if tu_moc is not None:
                self._doi_ten_mp3_taovideo(viec, tu_moc)
            if treo:
                ket_qua["cau_hoi_treo"] = treo
            self._ket_thuc_song(id, "loi", "lỗi phiên sống", loi=self.che(ly)[:800], ket_qua=ket_qua)
            return
        if kq.khong_giet_duoc:
            self._chuyen_song(id, ["can_tra_loi"], "dang_chay", "phiên sống: không giết được", viec.get("bat_dau_luc"))
            self._khong_giet(id, kq.pid, kq.pid_tao_luc, f"sau khi dừng phiên sống ({kq.ly_do_dung})")
            return
        if tu_moc is not None and kq.ly_do_dung != "dong_stdin":
            self._doi_ten_mp3_taovideo(viec, tu_moc)
        if st["loi"] is None and st["dong"] is None and st["loi_luot"] is None and huy.is_set():
            with self._khoa:
                huy_that = id in self._huy_that
            if huy_that or not self._dung.is_set():
                self._ket_thuc_song(id, "huy", "huỷ khi phiên sống đang chạy", ket_qua=ket_qua)
            else:
                self._ghi_log(id, "runner tắt giữa chừng — để nguyên trạng thái (giữ pid) cho lần khởi động sau "
                                  "đối soát (§7.8)")
            return
        ket, tom = self._doi_soat_song(self.kho.lay(id) or viec)
        ket_qua["doi_soat"] = tom
        if st["loi"] is not None:
            if treo:
                ket_qua["cau_hoi_treo"] = treo
            self._ket_thuc_song(id, "loi", "phiên sống bị dừng", ket_qua=ket_qua, loi=(
                f"{st['loi']}. Đối soát: {tom}. Mọi việc nền đã dừng — kiểm log rồi bấm Xin duyệt lại để làm tiếp"))
            return
        if st["loi_luot"] is not None:
            vb = st["loi_luot"]
            tam = bool(RE_QUOTA.search(vb))
            if tam:
                self._tam_dung_claude()
            tien_to = "Hết quota/quá tải — tạm dừng việc Claude 30 phút. " if tam else ""
            if treo:
                ket_qua["cau_hoi_treo"] = treo
            self._ket_thuc_song(id, "loi", "lượt Claude báo lỗi", ket_qua=ket_qua, loi=(
                f"{tien_to}Claude báo lỗi lượt: {self.che(vb)[:600]}. Đối soát: {tom}. Bấm Xin duyệt lại để làm tiếp"))
            return
        if st["dong"] is not None:
            kqa, ghi_chu = st["dong"]
            den, truong = anh_xa_ket_qua(loai, kqa, "xong" if ket == "xong" else "chua")
            kq_ag = dict(truong.get("ket_qua") or {})
            ket_qua.update(kq_ag)
            ket_qua["tom_tat"] = self.che(ket_qua.get("tom_tat") or "")
            ket_qua["doi_soat"] = tom
            if ghi_chu:
                ket_qua["co_lo_ngai"] = True
                ket_qua["lo_ngai"] = "; ".join(filter(None, [ket_qua.get("lo_ngai"), ghi_chu]))
            if kq.ly_do_dung != "dong_stdin":
                ket_qua["co_lo_ngai"] = True
                ket_qua["lo_ngai"] = "; ".join(filter(None, [ket_qua.get("lo_ngai"),
                                                              f"phiên kết thúc kiểu {kq.ly_do_dung}"]))
            self._ket_thuc_song(id, den, f"agent: {kqa.trang_thai}", ket_qua=ket_qua)
            return
        # tự chết giữa chừng (mã ≠ 0 hoặc thoát khi chưa báo cáo cuối) → đối soát (§7.8)
        if ket == "xong":
            ket_qua.update({"trang_thai_agent": None, "co_lo_ngai": True, "tom_tat": tom,
                            "lo_ngai": f"phiên tự thoát (mã {kq.ma_thoat}) nhưng đối soát đủ"})
            self._ket_thuc_song(id, "xong", "đối soát sau khi phiên tự thoát", ket_qua=ket_qua)
            return
        duoi = self.che(kq.duoi_stderr or "")[-TOI_DA_STDERR_LOI:]
        if treo:
            ket_qua["cau_hoi_treo"] = treo
        self._ket_thuc_song(id, "loi", "phiên sống tự thoát", ket_qua=ket_qua, loi=(
            f"Phiên Claude tự thoát (mã {kq.ma_thoat}) khi chưa báo cáo cuối — {tom}. Mọi việc nền đã dừng. Kiểm log "
            f"rồi bấm Xin duyệt lại để làm tiếp." + (f"\nstderr cuối:\n{duoi}" if duoi else "")))
