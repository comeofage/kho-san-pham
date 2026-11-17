"""Danh mục việc cố định (D3, docs/bo-chay-viec.md §5.1, §5.2, §6.1, §4.6).

Web không gửi đường dẫn hay lệnh: mọi argv dựng ở đây từ tham số đã validate chặt.
Đợt 3: radar_ban_tin, phan_tich_uid, douyin_uid, xu_ly_link_moi, poster_day_folder, voice_pv.
Đợt 4 (tốn tiền, luôn cần duyệt có chữ ký): muse_clip, voice_genmax (2 pha), poster_len_lich.
Đợt 5: khung taovideo (chưa mở — phiếu B-4).

Loại tốn tiền KHÔNG BAO GIỜ tự chạy lại (tu_chay_lai=False, đối soát 'khong_ro'). voice_genmax chỉ thêm
`--dong-y` khi việc ở bước 'chay' VÀ đã có đủ trường duyệt; không đường nào sinh `--gui-lai-ma`.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from .du_an import RE_MA, RE_ME, ds_me, kiem_uid, tim_du_an
from .han_muc import TRAN_LUOT
from .kieu import DAU_RA, BuocChay, CanNguoiDung, MoiTruong, ThamSoLoi, gio_vn

log = logging.getLogger(__name__)

PYTHON = "python"
RADAR_XUAT = Path(__file__).with_name("radar_xuat.py")
THU_MUC_SKILL_DOUYIN = "C:/Users/Mi/.gemini/config/skills/timvideodouyin"
CONG_POSTER = 8023
CONG_PERFECTVOICE = 7890
CONG_VIDEO_BATCH = 3786          # app Video Batch Local (Muse), aff-muse.md
TAO_VOICE = "tao_voice.py"       # script GenMax trong thư mục scripts skill tao-video-tu-canh-quay

# ---------- đợt 4: mẫu prompt Muse cố định (web chỉ chọn MÃ, không gửi chữ) ----------
# `@SP` = tag ảnh tham chiếu sản phẩm; agent aff-muse thay bằng tag thật (sp<6 số cuối UID>_<n>).
MAU_PROMPT_MUSE: dict[str, str] = {
    "xoay_360": ("Sản phẩm @SP đặt giữa nền trơn sáng, camera xoay chậm 360 độ quanh sản phẩm, ánh sáng studio "
                 "mềm, giữ đúng hình dáng và màu sắc như ảnh, không chữ, không logo lạ"),
    "cam_tay": ("Bàn tay người cầm sản phẩm @SP giơ lên trước ống kính rồi xoay nhẹ cho thấy các mặt, nền phòng "
                "khách sáng tự nhiên, quay dọc cận cảnh, giữ đúng sản phẩm như ảnh"),
    "can_canh": ("Cận cảnh macro chi tiết bề mặt và chất liệu của sản phẩm @SP, camera lia chậm từ trái sang phải, "
                 "ánh sáng bên tạo khối, nét căng, không chữ"),
    "dung_that": ("Người đang dùng sản phẩm @SP đúng công dụng trong bối cảnh đời thường tại nhà, chuyển động tự "
                  "nhiên, góc quay ngang tầm mắt, sản phẩm giữ đúng như ảnh"),
    "dat_ban": ("Sản phẩm @SP được đặt nhẹ xuống mặt bàn gỗ sáng, camera đẩy chậm vào gần, nắng sớm qua cửa sổ, "
                "không khí gọn gàng, không chữ"),
    "mo_hop": ("Đôi tay mở hộp giao hàng, lấy sản phẩm @SP ra và đặt lên bàn, góc quay từ trên xuống, ánh sáng "
               "ấm, sản phẩm giữ đúng như ảnh"),
    "truoc_sau": ("Khung hình chia đôi trước và sau khi dùng sản phẩm @SP, bên trái lộn xộn, bên phải gọn gàng "
                  "sạch sẽ, chuyển cảnh mượt, không chữ"),
}
TEN_MAU_MUSE: dict[str, str] = {
    "xoay_360": "Xoay 360° nền trơn", "cam_tay": "Cầm tay xoay", "can_canh": "Cận cảnh chất liệu",
    "dung_that": "Dùng thật tại nhà", "dat_ban": "Đặt lên bàn", "mo_hop": "Mở hộp", "truoc_sau": "Trước / sau",
}
MUSE_THOI_LUONG = (10, 15)
MUSE_TI_LE = ("9:16",)
POSTER_VIDEO_NGAY = (1, 100)     # FX-11: người dùng chốt ≤100 video/tài khoản/ngày (han_muc kiểm tổng)
_RE_MA_BAN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]{0,19}$", re.ASCII)
_TRUONG_DUYET = ("loi_duyet", "duyet_boi", "duyet_luc", "chu_ky_duyet")

_CAM_MUSE: tuple[str, ...] = (
    "Bash(*/api/accounts*)", "Bash(*/api/settings*)", "Bash(*/api/stop*)", "Bash(*/api/jobs/archive*)",
    "Bash(*/api/refs/remove*)", "Bash(*Start.cmd*)", "Bash(*taskkill*)",
)
_CAM_POSTER: tuple[str, ...] = (
    "Bash(*post_now*)", "Bash(*post_video_direct*)", "Bash(*post_queue_item*)", "Bash(*queue_reset_all*)",
    "Bash(*queue_clear_pending*)", "Bash(*delete_*)", "Bash(*v2_data.db*)", "Bash(*uvicorn*)",
    "Edit(//E:/tool/tiktok_poster_v2/**)", "Write(//E:/tool/tiktok_poster_v2/**)",
    # [P2-3] route ghi HTTP (backend/routers/queue.py, core/poster_api.py, settings/accounts/folders/calendar).
    # Chỉ plan_folder (/folders/<id>/plan) và batch_schedule (/folders/batch_schedule) được phép ghi.
    "Bash(*/run*)", "Bash(*/post*)", "Bash(*reset-all*)", "Bash(*reset_all*)", "Bash(*autopost*)",
    "Bash(*-X DELETE*)", "Bash(*-XDELETE*)", "Bash(*--request DELETE*)",
    "Bash(*-X PUT*)", "Bash(*-XPUT*)", "Bash(*--request PUT*)",
    "Bash(*-X PATCH*)", "Bash(*-XPATCH*)", "Bash(*--request PATCH*)",
    "Bash(*pending/clear*)", "Bash(*post/direct*)", "Bash(*/queue/batch*)", "Bash(*unstick*)",
    "Bash(*random_shuffle*)", "Bash(*/retry*)", "Bash(*reschedule-overdue*)", "Bash(*autogen-captions*)",
    "Bash(*calendar/plans*)", "Bash(*cooldown*)", "Bash(*login_and_capture*)", "Bash(*cookies_from_json*)",
    "Bash(*test-cookies*)", "Bash(*clean_profiles*)", "Bash(*clean-profile*)", "Bash(*drive-reauth*)",
    "Bash(*backup-now*)",
    # hàm ghi của desktop/api_client.py ApiClient (aff-poster gọi qua python -c)
    "Bash(*add_to_queue*)", "Bash(*queue_batch*)", "Bash(*queue_unstick*)", "Bash(*queue_random_shuffle*)",
    "Bash(*queue_retry*)", "Bash(*create_account*)", "Bash(*update_account*)", "Bash(*create_folder*)",
    "Bash(*update_folder*)", "Bash(*archive_folder*)", "Bash(*update_setting*)", "Bash(*account_clean_profile*)",
    "Bash(*account_login_capture*)", "Bash(*test_cookies*)", "Bash(*clean_all_profiles*)",
    "Bash(*create_calendar_plan*)", "Bash(*update_calendar_plan*)", "Bash(*views_refresh*)",
)

_CONG_CU_CAM_CO_DINH: tuple[str, ...] = (
    "AskUserQuestion", "Bash(git push*)", "Bash(*wrangler*)", "Bash(*deploy_cloudflare*)", "Bash(*gui_telegram*)",
    "Bash(pip *)", "Bash(*--gui-lai-ma*)", "Bash(*kho-runner*)",
)
# Thư mục runner cũ (%LOCALAPPDATA%\kho-runner, trước FX-7): vẫn chặn để bản cài cũ còn sót không bị đụng.
_THU_MUC_RUNNER_CU = "C:/Users/Mi/AppData/Local/kho-runner"


# FX-7b: chỉ cấm phần của chính runner (bản cài, khoá, DB, log, cấu hình) — KHÔNG cấm cả thư mục, vì thư mục dữ
# liệu việc (vd `radar/`, truyền cho Claude qua --add-dir) nằm trong đó và agent phải đọc/ghi được.
PHAN_CAM_THU_MUC_RUNNER: tuple[str, ...] = (
    "app/**", "app.moi/**", "app.cu/**", "log/**", "runner.db*", ".runner_key", "runner.lock", "runner.log*",
    "cau_hinh.json",
)


def _mau_cam_thu_muc(posix: str) -> tuple[str, ...]:
    return (f"Edit(//{posix}/**)", f"Write(//{posix}/**)", f"Read(//{posix}/**)")


def thu_muc_runner_posix() -> str:
    """Thư mục runner THỰC TẾ lúc gọi (KHO_RUNNER_DIR hoặc E:\\kho-runner), tuyệt đối, dấu `/`, không `/` cuối."""
    from .vong_lap import thu_muc_runner   # import trong hàm: vong_lap import danh_muc ở cấp module
    return Path(os.path.abspath(thu_muc_runner())).as_posix().rstrip("/")


def cong_cu_cam_chung() -> tuple[str, ...]:
    """`--disallowedTools` chung (§6.1). Mẫu Edit/Write/Read cho từng phần trong PHAN_CAM_THU_MUC_RUNNER của thư
    mục runner thực tế lúc gọi, kèm mẫu cả thư mục cũ AppData (bản cài trước FX-7). Là hàm (không phải hằng chụp
    lúc import) để luôn khớp `thu_muc_runner()` hiện hành."""
    hien = thu_muc_runner_posix()
    mau = _CONG_CU_CAM_CO_DINH + tuple(f"{cc}(//{hien}/{phan})" for phan in PHAN_CAM_THU_MUC_RUNNER
                                       for cc in ("Edit", "Write", "Read"))
    if os.path.normcase(hien) != os.path.normcase(_THU_MUC_RUNNER_CU):
        mau += _mau_cam_thu_muc(_THU_MUC_RUNNER_CU)
    return mau

_RE_SESSION = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_RE_NGAY = re.compile(r"^\d{4}-\d{2}-\d{2}$", re.ASCII)
_RE_CAN_BAN_DOUYIN = re.compile(r"(?i)captcha|验证|滑块|đăng nhập|login")
_GHI_STDIN_RA_FILE = ("import os,sys,pathlib;p=pathlib.Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True);"
                      "t=p.with_name(p.name+'.tmp');t.write_bytes(sys.stdin.buffer.read());os.replace(t,p)")


def _khong_them_thu_muc(_ts: dict, _mt: MoiTruong) -> tuple[str, ...]:
    return ()


@dataclass(frozen=True)
class LoaiViec:
    ma: str
    ten: str
    dot: int
    lan_chay: str
    ton_tien: bool
    agent: str | None
    tu_chay_lai: bool
    het_gio_s: int
    tai_nguyen: frozenset[str]
    tham_so: tuple[dict, ...]
    kiem_tham_so: Callable[[dict, MoiTruong], dict]
    tinh_khoa: Callable[[dict], str]
    trang_thai_dau: Callable[[dict], tuple[str, str]]
    dieu_kien_truoc: Callable[[dict, MoiTruong], CanNguoiDung | str | None]  # 'ban' = đợi
    lap_buoc: Callable[[dict, dict, MoiTruong], list[BuocChay]]              # (tham_so, viec, mt)
    kiem_dau_ra: Callable[[dict, dict, MoiTruong], str]                      # (tham_so, viec, mt) → DAU_RA
    bo_cong_cu: tuple[str, ...] = ()
    cong_cu_cam: tuple[str, ...] = ()
    tran_usd_moi_luot: float = 0
    # MỞ RỘNG (ngoài chữ ký §13, có mặc định): thư mục `--add-dir` cho Claude (§6.1 `loai.them_thu_muc`).
    them_thu_muc: Callable[[dict, MoiTruong], tuple[str, ...]] = field(default=_khong_them_thu_muc)

    @property
    def tran_luot(self) -> int | None:
        return TRAN_LUOT.get(self.ma)


# ---------- tiện ích ----------

def tham_so_chuan(tham_so: dict) -> str:
    return json.dumps(tham_so, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _la_dict(ts: object) -> dict:
    if not isinstance(ts, dict):
        raise ThamSoLoi("tham_so phải là object")
    return ts


def _chi_khoa(ts: dict, cho_phep: set[str]) -> None:
    la = set(ts) - cho_phep
    if la:
        raise ThamSoLoi(f"tham số lạ: {sorted(la)}")


def _ngay_vn(mt: MoiTruong) -> str:
    return gio_vn(mt.bay_gio()).date().isoformat()


def _ts_bat_dau(viec: dict) -> float | None:
    s = viec.get("bat_dau_luc")
    if not s:
        return None
    return gio_vn(datetime.fromisoformat(s)).timestamp()


def _moi_tu_bat_dau(p: Path, viec: dict) -> bool:
    """File có và mtime ≥ bat_dau_luc của lần chạy hiện tại."""
    ts = _ts_bat_dau(viec)
    if ts is None:
        return False
    try:
        return p.is_file() and p.stat().st_mtime >= ts
    except OSError as e:
        log.warning("không đọc được mtime %s: %s", p, e)
        return False


def _du_an(ts: dict, mt: MoiTruong) -> Path:
    p = tim_du_an(ts.get("du_an"), kiem_uid(ts.get("uid")), mt.gocs)
    if p is None:
        raise ThamSoLoi("không tìm thấy dự án theo mã + UID (thư mục đã đổi tên/xoá?)")
    return p


def _viec_tay(noi_dung: str) -> CanNguoiDung:
    return CanNguoiDung("viec_tay", noi_dung)


# ---------- kiểm tham số ----------

def _ts_radar(ts: dict, mt: MoiTruong) -> dict:
    _chi_khoa(_la_dict(ts), {"top_n", "chay_bu"})
    top_n = ts.get("top_n", 10)
    if not isinstance(top_n, int) or isinstance(top_n, bool) or not 5 <= top_n <= 30:
        raise ThamSoLoi("top_n phải là số nguyên 5–30")
    chay_bu = ts.get("chay_bu", False)
    if not isinstance(chay_bu, bool):
        raise ThamSoLoi("chay_bu phải là true/false")
    # ngay_tao do runner gắn (khoá chống trùng theo ngày VN lúc tạo, §4.5); web không gửi được khoá này.
    return {"top_n": top_n, "chay_bu": chay_bu, "ngay_tao": _ngay_vn(mt)}


def _ts_uid(ts: dict, mt: MoiTruong) -> dict:
    _chi_khoa(_la_dict(ts), {"uid"})
    return {"uid": kiem_uid(ts.get("uid"))}


def _ts_rong(ts: dict, mt: MoiTruong) -> dict:
    _chi_khoa(_la_dict(ts), set())
    return {}


def _ts_poster(ts: dict, mt: MoiTruong) -> dict:
    _chi_khoa(_la_dict(ts), {"uid", "du_an"})
    uid = kiem_uid(ts.get("uid"))
    ma = ts.get("du_an")
    if not isinstance(ma, str) or not RE_MA.fullmatch(ma):
        raise ThamSoLoi("du_an phải là mã 12 hex")
    _du_an({"uid": uid, "du_an": ma}, mt)
    return {"uid": uid, "du_an": ma}


def _ts_voice(ts: dict, mt: MoiTruong) -> dict:
    _chi_khoa(_la_dict(ts), {"uid", "du_an", "me"})
    co_ban = _ts_poster({"uid": ts.get("uid"), "du_an": ts.get("du_an")}, mt)
    me = ts.get("me")
    if not isinstance(me, str) or not RE_ME.fullmatch(me):
        raise ThamSoLoi("me sai định dạng YYYYMMDD-xxx")
    if me not in ds_me(_du_an(co_ban, mt)):
        raise ThamSoLoi("mẻ không có file *_kich-ban-da-cham.md trong dự án")
    return {**co_ban, "me": me}


def _la_so_nguyen(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _ts_muse(ts: dict, mt: MoiTruong) -> dict:
    _chi_khoa(_la_dict(ts), {"uid", "du_an", "mau", "thoi_luong", "ti_le"})
    co_ban = _ts_poster({"uid": ts.get("uid"), "du_an": ts.get("du_an")}, mt)
    mau = ts.get("mau")
    if not isinstance(mau, list) or not 1 <= len(mau) <= len(MAU_PROMPT_MUSE):
        raise ThamSoLoi(f"mau phải là danh sách 1–{len(MAU_PROMPT_MUSE)} mã mẫu")
    if any(not isinstance(m, str) or m not in MAU_PROMPT_MUSE for m in mau):
        raise ThamSoLoi(f"mau chỉ nhận mã trong danh mục: {sorted(MAU_PROMPT_MUSE)}")
    if len(set(mau)) != len(mau):
        raise ThamSoLoi("mau bị trùng mã")
    thoi_luong = ts.get("thoi_luong", MUSE_THOI_LUONG[0])
    if not _la_so_nguyen(thoi_luong) or thoi_luong not in MUSE_THOI_LUONG:
        raise ThamSoLoi(f"thoi_luong phải là một trong {list(MUSE_THOI_LUONG)}")
    ti_le = ts.get("ti_le", MUSE_TI_LE[0])
    if ti_le not in MUSE_TI_LE:
        raise ThamSoLoi(f"ti_le phải là một trong {list(MUSE_TI_LE)}")
    return {**co_ban, "mau": list(mau), "thoi_luong": thoi_luong, "ti_le": ti_le}


MA_BAN_TOI_DA_DOC = 200      # chỉ chặn dữ liệu vô lý lúc đọc; trần hạn mức (25) do kiem_han_muc → 429


def _kiem_ma_ban(ma_ban: object, tran: int | None = None) -> list[str]:
    """Danh sách mã bản GenMax: 1–`tran` (mặc định trần code genmax_ban_moi_viec), mỗi mã an toàn cho argv
    (không bắt đầu bằng '-'), không trùng."""
    if tran is None:
        from .han_muc import HAN_MUC_TRAN
        tran = int(HAN_MUC_TRAN["genmax_ban_moi_viec"])
    if not isinstance(ma_ban, list) or not 1 <= len(ma_ban) <= tran:
        raise ThamSoLoi(f"danh sách mã bản phải có 1–{tran} mã")
    if any(not isinstance(m, str) or not _RE_MA_BAN.fullmatch(m) for m in ma_ban):
        raise ThamSoLoi("mã bản sai định dạng")
    if len(set(ma_ban)) != len(ma_ban):
        raise ThamSoLoi("mã bản bị trùng")
    return list(ma_ban)


def _ts_genmax(ts: dict, mt: MoiTruong) -> dict:
    """Như voice_pv + runner tự gắn `ma_ban` (trang_thai.py ma) để lời duyệt ký đúng danh sách bản sẽ gửi.
    Web KHÔNG gửi được `ma_ban` (khoá lạ → 400)."""
    co_ban = _ts_voice(ts, mt)
    p = _du_an(co_ban, mt)
    try:
        ds = mt.ds_ma_voice(p, co_ban["me"])
    except Exception as e:   # noqa: BLE001 — subprocess trang_thai.py (quá giờ, OSError…): báo rõ thay vì 500
        log.warning("ds_ma_voice lỗi: %r", e)
        ds = None
    if ds is None:
        raise ThamSoLoi("không lấy được danh sách mã bản của mẻ (trang_thai.py ma lỗi) — kiểm trên máy")
    return {**co_ban, "ma_ban": _kiem_ma_ban(ds, MA_BAN_TOI_DA_DOC)}


def ds_folder_poster(mt: MoiTruong) -> list[dict]:
    """Danh sách folder Poster đã chuẩn hoá [{id:int, ten:str}] từ `mt.doc_folder_poster()`.
    Mục hỏng bị bỏ. Không đọc được (Poster tắt, venv lỗi…) → ThamSoLoi."""
    try:
        tho = mt.doc_folder_poster()
    except Exception as e:   # noqa: BLE001 — hàm do A-3 cấp (subprocess venv Poster): lỗi gì cũng phải thành thông báo
        log.warning("không đọc được danh sách folder Poster: %r", e)
        raise ThamSoLoi(f"không đọc được danh sách folder Poster ({type(e).__name__}) — Poster V2 đã mở chưa?") from e
    if not isinstance(tho, list):
        raise ThamSoLoi("danh sách folder Poster không đúng dạng")
    ra: list[dict] = []
    for f in tho:
        if not isinstance(f, dict):
            continue
        fid = f.get("id")
        if isinstance(fid, str) and fid.isascii() and fid.isdigit() and len(fid) <= 9:
            fid = int(fid)
        if not _la_so_nguyen(fid) or not 0 < fid < 10 ** 9:
            continue
        ten = f.get("ten", f.get("name"))
        ra.append({"id": fid, "ten": ten[:120] if isinstance(ten, str) else ""})
    return ra


def _ts_poster_len_lich(ts: dict, mt: MoiTruong) -> dict:
    _chi_khoa(_la_dict(ts), {"folder_id", "so_video_ngay"})
    fid = ts.get("folder_id")
    if not _la_so_nguyen(fid) or not 0 < fid < 10 ** 9:
        raise ThamSoLoi("folder_id phải là số nguyên dương (lấy từ danh sách folder Poster)")
    n = ts.get("so_video_ngay")
    if not _la_so_nguyen(n) or not POSTER_VIDEO_NGAY[0] <= n <= POSTER_VIDEO_NGAY[1]:
        raise ThamSoLoi(f"so_video_ngay phải là số nguyên {POSTER_VIDEO_NGAY[0]}–{POSTER_VIDEO_NGAY[1]}")
    if fid not in {f["id"] for f in ds_folder_poster(mt)}:
        raise ThamSoLoi(f"không có folder Poster id {fid}")
    return {"folder_id": fid, "so_video_ngay": n}


def _ts_taovideo(_ts: dict, _mt: MoiTruong) -> dict:
    raise ThamSoLoi("taovideo chưa mở (đợt 5, phiếu B-4)")


def _cho_chay(_ts: dict) -> tuple[str, str]:
    return ("cho", "chay")


def _cho_duyet(_ts: dict) -> tuple[str, str]:
    return ("cho_duyet", "chay")


def _cho_uoc_tinh(_ts: dict) -> tuple[str, str]:
    return ("cho", "uoc_tinh")


# ---------- điều kiện trước ----------

def _dk_khong(_ts: dict, _mt: MoiTruong) -> None:
    return None


def _dk_kho(_ts: dict, mt: MoiTruong) -> CanNguoiDung | str | None:
    return mt.chan_doan_kho(mt.repo_kho)


def _dk_douyin(ts: dict, mt: MoiTruong) -> CanNguoiDung | str | None:
    uid = kiem_uid(ts.get("uid"))
    sp = Path(mt.thu_muc_sp) / f"sp_{uid}"
    if not sp.is_dir():
        return _viec_tay(f"Chưa có thư mục {sp.as_posix()} — chạy Phân tích sản phẩm (bộ cảnh quay) trước, "
                         "rồi bấm Đã làm xong")
    return mt.chan_doan_kho(mt.repo_kho)


def _dk_du_an(ts: dict, mt: MoiTruong) -> Path | CanNguoiDung:
    try:
        return _du_an(ts, mt)
    except ThamSoLoi:
        return _viec_tay("Không còn thấy thư mục dự án (đổi tên/xoá/ổ đĩa chưa cắm?). Kiểm trên máy rồi bấm "
                         "Đã làm xong")


def _dk_poster(ts: dict, mt: MoiTruong) -> CanNguoiDung | str | None:
    p = _dk_du_an(ts, mt)
    if isinstance(p, CanNguoiDung):
        return p
    if not mt.cong_song(CONG_POSTER):
        return _viec_tay(f"Mở Poster V2 trên máy (cổng {CONG_POSTER} chưa sống) rồi bấm Đã làm xong")
    if not (p / "kich-ban" / "poster_captions.txt").is_file():
        return _viec_tay(f"Dự án chưa có file caption {(p / 'kich-ban' / 'poster_captions.txt').as_posix()}")
    return None


def _dk_muse(ts: dict, mt: MoiTruong) -> CanNguoiDung | str | None:
    p = _dk_du_an(ts, mt)
    if isinstance(p, CanNguoiDung):
        return p
    if not mt.cong_song(CONG_VIDEO_BATCH):
        return _viec_tay(f"Mở app Video Batch Local trên máy (Start.cmd; cổng {CONG_VIDEO_BATCH} chưa sống) rồi bấm "
                         "Đã làm xong")
    return None


def _dk_genmax(ts: dict, mt: MoiTruong) -> CanNguoiDung | str | None:
    p = _dk_du_an(ts, mt)
    if isinstance(p, CanNguoiDung):
        return p
    if mt.ffmpeg_ngoai():
        return "ban"
    return None


def _dk_poster_len_lich(_ts: dict, mt: MoiTruong) -> CanNguoiDung | str | None:
    if not mt.cong_song(CONG_POSTER):
        return _viec_tay(f"Mở Poster V2 trên máy (cổng {CONG_POSTER} chưa sống) rồi bấm Đã làm xong")
    return None


def _dk_voice(ts: dict, mt: MoiTruong) -> CanNguoiDung | str | None:
    p = _dk_du_an(ts, mt)
    if isinstance(p, CanNguoiDung):
        return p
    if mt.ffmpeg_ngoai():
        return "ban"
    if not mt.cong_song(CONG_PERFECTVOICE):
        return _viec_tay(f"Mở PerfectVoice trên máy (cổng {CONG_PERFECTVOICE} chưa sống) rồi bấm Đã làm xong")
    return None


# ---------- lập bước ----------

def _buoc(ten: str, argv: list[str], cwd: Path | str, het_gio_s: int, *, stdin: str | None = None,
          la_claude: bool = False, hien_cua_so: bool = False, file_log_phu: Path | None = None) -> BuocChay:
    return BuocChay(ten=ten, argv=argv, cwd=str(cwd), stdin=stdin, env_them={}, la_claude=la_claude,
                    het_gio_s=het_gio_s, hien_cua_so=hien_cua_so,
                    file_log_phu=str(file_log_phu) if file_log_phu is not None else None)


def _buoc_claude(loai: "LoaiViec", viec: dict, mt: MoiTruong, cwd: Path) -> BuocChay:
    from .han_muc import HAN_MUC_TRAN
    from .phieu import lap_phieu
    # Lần đầu: stdin = phiếu. Đã có phiên (resume): vòng chạy điền tin tiếp (trả lời/duyệt/chạy tiếp).
    stdin = None if viec.get("phien_da_tao") else lap_phieu(loai, viec, mt, int(HAN_MUC_TRAN["dot_bat"]))
    return _buoc("claude", lenh_claude(loai, viec, mt), cwd, loai.het_gio_s, stdin=stdin, la_claude=True)


def _radar_ngay_ok(db: Path, ngay: str) -> bool:
    """scan_runs của `ngay` đã 'ok'? Mở DB CHỈ ĐỌC. DB thiếu/lỗi → False (chạy bù miễn phí, an toàn)."""
    if not db.is_file():
        return False
    try:
        uri = f"file:{quote(db.as_posix(), safe='/:')}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=5)) as c:
            return c.execute("SELECT 1 FROM scan_runs WHERE scan_date=? AND status='ok' LIMIT 1",
                             (ngay,)).fetchone() is not None
    except sqlite3.Error as e:
        log.warning("không đọc được scan_runs ở %s: %s — coi như chưa ok", db, e)
        return False


def _json_radar(viec: dict, mt: MoiTruong) -> Path:
    return Path(mt.thu_muc_du_lieu) / "radar" / f"{viec['id']}.json"


def _buoc_radar(ts: dict, viec: dict, mt: MoiTruong) -> list[BuocChay]:
    loai = DANH_MUC["radar_ban_tin"]
    goc = Path(mt.thu_muc_radar)
    hom_nay = _ngay_vn(mt)
    buoc: list[BuocChay] = []
    if ts.get("chay_bu") is True and not _radar_ngay_ok(goc / "tiktok_7ngay.db", hom_nay):
        buoc.append(_buoc("quet_bu", [PYTHON, "quet_dot_bien_7ngay.py", "--workers", "6"], goc, 1800))
    ngay = ["--ngay", hom_nay] if ts.get("chay_bu") is True else []
    buoc.append(_buoc("xuat_radar", [PYTHON, str(RADAR_XUAT), *ngay, "--ra", str(_json_radar(viec, mt))],
                      mt.thu_muc_du_lieu, 300))
    buoc.append(_buoc_claude(loai, viec, mt, goc))
    return buoc


def _buoc_phan_tich(ts: dict, viec: dict, mt: MoiTruong) -> list[BuocChay]:
    kiem_uid(ts.get("uid"))
    return [_buoc_claude(DANH_MUC["phan_tich_uid"], viec, mt, Path(mt.thu_muc_sp))]


def _file_mau_douyin(uid: str, mt: MoiTruong) -> Path:
    data = Path(mt.repo_kho) / "data"
    try:
        ds = sorted(d for d in data.iterdir() if d.is_dir() and d.name != uid)
    except OSError as e:
        raise ThamSoLoi(f"không đọc được {data}: {e}") from e
    for d in ds:
        if (d / "douyin.md").is_file():
            return d / "douyin.md"
    raise ThamSoLoi("kho chưa có data/<uid>/douyin.md nào để làm file mẫu")


def _buoc_douyin(ts: dict, viec: dict, mt: MoiTruong) -> list[BuocChay]:
    from .phieu import lap_prompt_douyin
    uid = kiem_uid(ts.get("uid"))
    sp = Path(mt.thu_muc_sp) / f"sp_{uid}"
    prompt = lap_prompt_douyin(uid, sp, _file_mau_douyin(uid, mt))
    return [
        _buoc("ghi_prompt", [PYTHON, "-c", _GHI_STDIN_RA_FILE, str(sp / "douyin" / "_prompt_antigravity.txt")],
              mt.thu_muc_sp, 60, stdin=prompt),
        _buoc("agy", [str(mt.agy_exe), "--dangerously-skip-permissions",
                      "--add-dir", Path(mt.thu_muc_sp).as_posix(),
                      "--add-dir", THU_MUC_SKILL_DOUYIN,
                      "-p", prompt, "--output-format", "text", "--print-timeout", "0"],
              mt.thu_muc_sp, DANH_MUC["douyin_uid"].het_gio_s, hien_cua_so=True,
              file_log_phu=sp / "douyin" / "_antigravity_log.txt"),
        _buoc("kho_ghi", [PYTHON, (Path(mt.repo_kho) / "tools" / "kho.py").as_posix(), "ghi", uid,
                          "--tu", sp.as_posix()], mt.repo_kho, 600),
    ]


def _buoc_link(ts: dict, viec: dict, mt: MoiTruong) -> list[BuocChay]:
    return [_buoc("kho_cho", [PYTHON, (Path(mt.repo_kho) / "tools" / "kho.py").as_posix(), "cho"], mt.repo_kho,
                  DANH_MUC["xu_ly_link_moi"].het_gio_s)]


def _buoc_poster(ts: dict, viec: dict, mt: MoiTruong) -> list[BuocChay]:
    uid = kiem_uid(ts.get("uid"))
    p = _du_an(ts, mt)
    P = p.as_posix()
    goc = [str(mt.python_poster), (Path(mt.thu_muc_scripts) / "day_len_poster.py").as_posix(), "--project", P,
           "--link", f"https://shop.tiktok.com/vn/pdp/{uid}", "--captions", f"{P}/kich-ban/poster_captions.txt"]
    het = DANH_MUC["poster_day_folder"].het_gio_s
    return [_buoc("poster_xem", goc + ["--xem"], p, het), _buoc("poster_day", list(goc), p, het)]


def _buoc_voice(ts: dict, viec: dict, mt: MoiTruong) -> list[BuocChay]:
    p = _du_an(ts, mt)
    me = ts.get("me")
    if not isinstance(me, str) or not RE_ME.fullmatch(me):
        raise ThamSoLoi("me sai định dạng")
    return [_buoc("voice_pv", [PYTHON, (Path(mt.thu_muc_scripts) / "tao_voice_pv.py").as_posix(),
                               "--project", p.as_posix(), "--batch", me], p, DANH_MUC["voice_pv"].het_gio_s)]


def _co_du_duyet(viec: dict) -> bool:
    return all(isinstance(viec.get(k), str) and viec.get(k) for k in _TRUONG_DUYET)


def _buoc_genmax(ts: dict, viec: dict, mt: MoiTruong) -> list[BuocChay]:
    """§5.2 hai pha. Pha 'chay' (gọi API, TỐN TIỀN) chỉ khi viec['buoc'] == 'chay' ĐÚNG NGUYÊN VĂN và việc đã có đủ
    trường duyệt; mọi giá trị khác → pha ước tính (không --dong-y, không gọi API).
    Chữ ký duyệt do vòng chạy kiểm (chu_ky.kiem_duyet) ngay trước khi nhận — ở đây chỉ chặn thêm một lớp.
    `--ma` ghim đúng danh sách bản đã ký duyệt; KHÔNG có đường nào thêm `--gui-lai-ma`."""
    p = _du_an(ts, mt)
    me = ts.get("me")
    if not isinstance(me, str) or not RE_ME.fullmatch(me):
        raise ThamSoLoi("me sai định dạng")
    ma_ban = _kiem_ma_ban(ts.get("ma_ban"))
    pha_chay = viec.get("buoc") == "chay"
    if pha_chay and not _co_du_duyet(viec):
        raise ThamSoLoi("voice_genmax chưa có lời duyệt đầy đủ — không chạy pha gọi API")
    argv = [PYTHON, (Path(mt.thu_muc_scripts) / TAO_VOICE).as_posix(), "--project", p.as_posix(), "--batch", me]
    if pha_chay:
        argv.append("--dong-y")
    argv += ["--ma", *ma_ban]
    b = _buoc("genmax_chay" if pha_chay else "genmax_uoc_tinh", argv, p, DANH_MUC["voice_genmax"].het_gio_s)
    khoa = os.environ.get("GENMAX_API_KEY", "").strip()
    if pha_chay and khoa:      # §4.7: chỉ pha chay mới nhận key; không có thì tao_voice tự đọc biến tài khoản
        b = replace(b, env_them={"GENMAX_API_KEY": khoa})
    return [b]


def _buoc_muse(ts: dict, viec: dict, mt: MoiTruong) -> list[BuocChay]:
    return [_buoc_claude(DANH_MUC["muse_clip"], viec, mt, _du_an(ts, mt))]


def _buoc_poster_len_lich(ts: dict, viec: dict, mt: MoiTruong) -> list[BuocChay]:
    return [_buoc_claude(DANH_MUC["poster_len_lich"], viec, mt, Path(mt.thu_muc_du_lieu))]


def _buoc_taovideo(_ts: dict, _viec: dict, _mt: MoiTruong) -> list[BuocChay]:
    raise ThamSoLoi("taovideo chưa mở (đợt 5, phiếu B-4)")


# ---------- nội dung phiếu đợt 4 (cho phieu.py dùng lại; khoá giống phieu._noi_dung_loai) ----------

def noi_dung_phieu_dot4(loai: "LoaiViec", viec: dict, mt: MoiTruong) -> dict[str, str]:
    """Mục tiêu/đầu vào/được ghi/cấm/xong khi cố định cho muse_clip, poster_len_lich. Chỉ chèn giá trị đã validate
    và prompt CỐ ĐỊNH trong MAU_PROMPT_MUSE (mã lạ → ThamSoLoi, không chèn chữ tuỳ ý)."""
    ts = viec.get("tham_so") or {}
    if loai.ma == "muse_clip":
        p = _du_an(ts, mt)
        mau = ts.get("mau")
        if not isinstance(mau, list) or not mau or any(m not in MAU_PROMPT_MUSE for m in mau):
            raise ThamSoLoi("mau trong việc không hợp lệ")
        tl, tile = ts.get("thoi_luong"), ts.get("ti_le")
        if tl not in MUSE_THOI_LUONG or tile not in MUSE_TI_LE:
            raise ThamSoLoi("thoi_luong/ti_le trong việc không hợp lệ")
        P = p.as_posix()
        ds = "\n".join(f"- {m}: {MAU_PROMPT_MUSE[m]}" for m in mau)
        return {
            "muc_tieu": (f"tạo {len(mau)} clip b-roll Muse, mỗi clip {tl} giây, tỉ lệ {tile}, cho sản phẩm UID "
                         f"{kiem_uid(ts.get('uid'))}, mỗi clip đúng một mẫu prompt liệt kê bên dưới"),
            "dau_vao": f"thư mục dự án {P} (ảnh sản phẩm trong {P}/anh/pdp/), app Video Batch Local 127.0.0.1:3786",
            "duoc_ghi": f"{P}/muse/ (clip, nhật ký 00-muse-log.md, _ref/, _frames/) và thêm ảnh tag mới vào app",
            "cam": ("tạo quá số clip ở trên, đổi prompt ngoài mẫu (chỉ được thay @SP bằng tag ảnh), /api/accounts*, "
                    "/api/settings, /api/stop, /api/jobs/archive, /api/refs/remove, đụng job không phải của mình, "
                    "bật/tắt app, sửa raw/ cuts/ takes/"),
            "xong_khi": "mỗi clip có ffprobe + 3 frame đã đọc, ghi đạt/không đạt trong 00-muse-log.md",
            "them": "Mẫu prompt (cố định, @SP = tag ảnh sản phẩm):\n" + ds,
        }
    if loai.ma == "poster_len_lich":
        fid, n = ts.get("folder_id"), ts.get("so_video_ngay")
        if not _la_so_nguyen(fid) or not _la_so_nguyen(n) or not POSTER_VIDEO_NGAY[0] <= n <= POSTER_VIDEO_NGAY[1]:
            raise ThamSoLoi("folder_id/so_video_ngay trong việc không hợp lệ")
        return {
            "muc_tieu": (f"lên lịch đăng cho đúng folder {fid} trên Poster V2 với {n} video/ngày "
                         "(plan_folder/batch_schedule theo file agent), không đổi gì khác"),
            "dau_vao": f"folder Poster id {fid}; backend 127.0.0.1:{CONG_POSTER}",
            "duoc_ghi": "chỉ lịch đăng của đúng folder trên; báo cáo trong thư mục làm việc hiện tại",
            "cam": ("post_now, post_video_direct, post_queue_item, đổi account/caption/UID/path, xoá folder/video/"
                    "hàng đợi, đụng folder khác, bật/tắt autopost, sửa file trong E:/tool/tiktok_poster_v2"),
            "xong_khi": "list_queue/calendar của folder cho thấy đúng số video/ngày đã lên lịch, chép số liệu thật",
            "them": "",
        }
    raise ThamSoLoi(f"loại {loai.ma} không có phiếu đợt 4")


# ---------- đối soát đầu ra (§4.6, §5.1) ----------

def _dau_ra_radar(ts: dict, viec: dict, mt: MoiTruong) -> str:
    j = _json_radar(viec, mt)
    if not j.is_file():
        return "chua"
    try:
        scan_date = json.loads(j.read_text(encoding="utf-8")).get("scan_date")
    except (OSError, ValueError, AttributeError) as e:
        log.warning("JSON radar %s hỏng: %s", j, e)
        return "khong_ro"
    if not isinstance(scan_date, str) or not _RE_NGAY.fullmatch(scan_date):
        return "khong_ro"
    md = Path(mt.thu_muc_radar) / "de-xuat" / f"{scan_date}-de-xuat-san-pham.md"
    return "xong" if _moi_tu_bat_dau(md, viec) else "chua"


def _dau_ra_phan_tich(ts: dict, viec: dict, mt: MoiTruong) -> str:
    """P2-4: rui_ro + douyin.md → xong; da_phan_tich + rui_ro, thiếu douyin.md → xong_lo_ngai; còn lại → chua."""
    uid = kiem_uid(ts.get("uid"))
    thu = Path(mt.repo_kho) / "data" / uid
    f = thu / "info.json"
    if not f.is_file():
        return "chua"
    try:
        info = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("info.json hỏng %s: %s", f, e)
        return "khong_ro"
    if not isinstance(info, dict):
        return "khong_ro"
    co_rui_ro = bool(info.get("rui_ro"))
    if co_rui_ro and (thu / "douyin.md").is_file():
        return "xong"
    if co_rui_ro and info.get("da_phan_tich") is True:
        return "xong_lo_ngai"
    return "chua"


def _dau_ra_douyin(ts: dict, viec: dict, mt: MoiTruong) -> str:
    uid = kiem_uid(ts.get("uid"))
    return "xong" if _moi_tu_bat_dau(Path(mt.repo_kho) / "data" / uid / "douyin.md", viec) else "chua"


def _dau_ra_link(ts: dict, viec: dict, mt: MoiTruong) -> str:
    return "chua"          # chỉ đọc danh sách link chờ; chạy lại vô hại (kho.py cho)


def _dau_ra_poster(ts: dict, viec: dict, mt: MoiTruong) -> str:
    # Không có dấu vết đầu ra đọc được an toàn (trạng thái nằm trong app Poster) → không tự đoán, không tự chạy lại.
    return "khong_ro"


def _dau_ra_voice(ts: dict, viec: dict, mt: MoiTruong) -> str:
    try:
        p = _du_an(ts, mt)
    except ThamSoLoi:
        return "khong_ro"
    me = ts.get("me")
    ds_ma = mt.ds_ma_voice(p, me)
    if not ds_ma:
        return "khong_ro"
    for ma in ds_ma:
        f = p / "voice" / f"{me}_{ma}_adam.mp3"
        if not f.is_file():
            return "chua"
        tl = mt.thoi_luong_media(f)
        if tl is None or tl <= 0:
            return "chua"
    return "xong"


def _dau_ra_khong_ro(_ts: dict, _viec: dict, _mt: MoiTruong) -> str:
    # Loại tốn tiền: không đoán đầu ra, không bao giờ tự chạy lại (CL21).
    return "khong_ro"


def kiem_dau_ra_an_toan(loai: "LoaiViec", tham_so: dict, viec: dict, mt: MoiTruong) -> str:
    """Bọc kiem_dau_ra cho bước khởi động lại: lỗi bất ngờ không được làm sập runner → 'khong_ro' + log."""
    try:
        kq = loai.kiem_dau_ra(tham_so, viec, mt)
    except Exception:
        log.exception("đối soát đầu ra việc %s (%s) lỗi — coi là khong_ro", viec.get("id"), loai.ma)
        return "khong_ro"
    if kq not in DAU_RA:
        log.error("kiem_dau_ra %s trả giá trị lạ %r — coi là khong_ro", loai.ma, kq)
        return "khong_ro"
    return kq


# ---------- danh mục ----------

def _ts_mo_ta(*ds: dict) -> tuple[dict, ...]:
    return tuple(ds)


_UID = {"ten": "uid", "kieu": "uid", "bat_buoc": True}
_DU_AN = {"ten": "du_an", "kieu": "du_an", "bat_buoc": True}
_ME = {"ten": "me", "kieu": "me", "bat_buoc": True}

DANH_MUC: dict[str, LoaiViec] = {
    "radar_ban_tin": LoaiViec(
        ma="radar_ban_tin", ten="Bản tin radar", dot=3, lan_chay="nhe", ton_tien=False, agent="aff-radar",
        tu_chay_lai=True, het_gio_s=45 * 60, tai_nguyen=frozenset(),
        tham_so=_ts_mo_ta({"ten": "top_n", "kieu": "int", "min": 5, "max": 30, "mac_dinh": 10},
                          {"ten": "chay_bu", "kieu": "bool", "mac_dinh": False}),
        kiem_tham_so=_ts_radar, tinh_khoa=lambda ts: str(ts["ngay_tao"]), trang_thai_dau=_cho_chay,
        dieu_kien_truoc=_dk_khong, lap_buoc=_buoc_radar, kiem_dau_ra=_dau_ra_radar,
        bo_cong_cu=("Read", "Write", "Glob"), tran_usd_moi_luot=3.0,
        them_thu_muc=lambda _ts, mt: (str(Path(mt.thu_muc_du_lieu) / "radar"),)),
    "phan_tich_uid": LoaiViec(
        ma="phan_tich_uid", ten="Phân tích sản phẩm (bộ cảnh quay)", dot=3, lan_chay="nhe", ton_tien=False,
        agent="aff-san-pham", tu_chay_lai=True, het_gio_s=90 * 60, tai_nguyen=frozenset({"kho"}),
        tham_so=_ts_mo_ta(_UID), kiem_tham_so=_ts_uid, tinh_khoa=lambda ts: str(ts["uid"]),
        trang_thai_dau=_cho_chay, dieu_kien_truoc=_dk_kho, lap_buoc=_buoc_phan_tich, kiem_dau_ra=_dau_ra_phan_tich,
        bo_cong_cu=("Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill"), tran_usd_moi_luot=8.0),
    "douyin_uid": LoaiViec(
        ma="douyin_uid", ten="Tìm video Douyin", dot=3, lan_chay="nhe", ton_tien=False, agent=None,
        tu_chay_lai=True, het_gio_s=40 * 60, tai_nguyen=frozenset({"kho"}),
        tham_so=_ts_mo_ta(_UID), kiem_tham_so=_ts_uid, tinh_khoa=lambda ts: str(ts["uid"]),
        trang_thai_dau=_cho_chay, dieu_kien_truoc=_dk_douyin, lap_buoc=_buoc_douyin, kiem_dau_ra=_dau_ra_douyin),
    "xu_ly_link_moi": LoaiViec(
        ma="xu_ly_link_moi", ten="Xử lý link mới", dot=3, lan_chay="nhe", ton_tien=False, agent=None,
        tu_chay_lai=True, het_gio_s=5 * 60, tai_nguyen=frozenset({"kho"}),
        tham_so=(), kiem_tham_so=_ts_rong, tinh_khoa=lambda _ts: "kho",
        trang_thai_dau=_cho_chay, dieu_kien_truoc=_dk_kho, lap_buoc=_buoc_link, kiem_dau_ra=_dau_ra_link),
    "poster_day_folder": LoaiViec(
        ma="poster_day_folder", ten="Đẩy folder lên Poster", dot=3, lan_chay="nhe", ton_tien=False, agent=None,
        tu_chay_lai=True, het_gio_s=15 * 60, tai_nguyen=frozenset({"poster"}),
        tham_so=_ts_mo_ta(_UID, _DU_AN), kiem_tham_so=_ts_poster, tinh_khoa=lambda ts: str(ts["du_an"]),
        trang_thai_dau=_cho_chay, dieu_kien_truoc=_dk_poster, lap_buoc=_buoc_poster, kiem_dau_ra=_dau_ra_poster),
    "voice_pv": LoaiViec(
        ma="voice_pv", ten="Voice PerfectVoice", dot=3, lan_chay="gpu", ton_tien=False, agent=None,
        tu_chay_lai=True, het_gio_s=4 * 3600, tai_nguyen=frozenset(),
        tham_so=_ts_mo_ta(_UID, _DU_AN, _ME), kiem_tham_so=_ts_voice,
        tinh_khoa=lambda ts: f"{ts['du_an']}:{ts['me']}",
        trang_thai_dau=_cho_chay, dieu_kien_truoc=_dk_voice, lap_buoc=_buoc_voice, kiem_dau_ra=_dau_ra_voice),
    # ----- đợt 4: tốn tiền / rủi ro — luôn cần duyệt có chữ ký, không tự chạy lại -----
    "muse_clip": LoaiViec(
        ma="muse_clip", ten="Sinh clip AI (Muse)", dot=4, lan_chay="nhe", ton_tien=True, agent="aff-muse",
        tu_chay_lai=False, het_gio_s=90 * 60, tai_nguyen=frozenset(),
        tham_so=_ts_mo_ta(_UID, _DU_AN,
                          {"ten": "mau", "kieu": "chon_nhieu", "bat_buoc": True, "min": 1, "max": 10,
                           "lua_chon": [{"ma": k, "ten": TEN_MAU_MUSE[k]} for k in MAU_PROMPT_MUSE]},
                          {"ten": "thoi_luong", "kieu": "chon", "lua_chon": list(MUSE_THOI_LUONG),
                           "mac_dinh": MUSE_THOI_LUONG[0]},
                          {"ten": "ti_le", "kieu": "chon", "lua_chon": list(MUSE_TI_LE), "mac_dinh": MUSE_TI_LE[0]}),
        kiem_tham_so=_ts_muse, tinh_khoa=lambda ts: str(ts["du_an"]), trang_thai_dau=_cho_duyet,
        dieu_kien_truoc=_dk_muse, lap_buoc=_buoc_muse, kiem_dau_ra=_dau_ra_khong_ro,
        bo_cong_cu=("Read", "Write", "Edit", "Glob", "Grep", "Bash"), cong_cu_cam=_CAM_MUSE, tran_usd_moi_luot=3.0),
    "voice_genmax": LoaiViec(
        ma="voice_genmax", ten="Voice GenMax (Adam)", dot=4, lan_chay="gpu", ton_tien=True, agent=None,
        tu_chay_lai=False, het_gio_s=3 * 3600, tai_nguyen=frozenset(),
        tham_so=_ts_mo_ta(_UID, _DU_AN, _ME), kiem_tham_so=_ts_genmax,
        tinh_khoa=lambda ts: f"{ts['du_an']}:{ts['me']}",
        trang_thai_dau=_cho_uoc_tinh, dieu_kien_truoc=_dk_genmax, lap_buoc=_buoc_genmax,
        kiem_dau_ra=_dau_ra_khong_ro),
    "poster_len_lich": LoaiViec(
        ma="poster_len_lich", ten="Lên lịch đăng Poster", dot=4, lan_chay="nhe", ton_tien=True, agent="aff-poster",
        tu_chay_lai=False, het_gio_s=30 * 60, tai_nguyen=frozenset({"poster"}),
        tham_so=_ts_mo_ta({"ten": "folder_id", "kieu": "folder_poster", "bat_buoc": True},
                          {"ten": "so_video_ngay", "kieu": "int", "bat_buoc": True, "min": POSTER_VIDEO_NGAY[0],
                           "max": POSTER_VIDEO_NGAY[1]}),
        kiem_tham_so=_ts_poster_len_lich, tinh_khoa=lambda ts: f"folder:{ts['folder_id']}",
        trang_thai_dau=_cho_duyet, dieu_kien_truoc=_dk_poster_len_lich, lap_buoc=_buoc_poster_len_lich,
        kiem_dau_ra=_dau_ra_khong_ro,
        bo_cong_cu=("Read", "Write", "Edit", "Glob", "Grep", "Bash"), cong_cu_cam=_CAM_POSTER,
        tran_usd_moi_luot=2.0),
    # ----- đợt 5: khung, CHƯA mở (B-4 hoàn thiện §5.3) -----
    "taovideo": LoaiViec(
        ma="taovideo", ten="Làm video affiliate hoàn chỉnh", dot=5, lan_chay="gpu", ton_tien=True,
        agent="aff-taovideo", tu_chay_lai=False, het_gio_s=8 * 3600, tai_nguyen=frozenset({"kho"}),
        tham_so=_ts_mo_ta(_UID, {"ten": "du_an_a", "kieu": "du_an", "bat_buoc": True},
                          {"ten": "du_an_b", "kieu": "du_an_hoac_tu_tim", "bat_buoc": True},
                          {"ten": "wm", "kieu": "chon", "lua_chon": [], "bat_buoc": True},
                          {"ten": "gia", "kieu": "int", "min": 1000, "max": 10_000_000, "bat_buoc": False}),
        kiem_tham_so=_ts_taovideo, tinh_khoa=lambda ts: str(ts["uid"]), trang_thai_dau=_cho_duyet,
        dieu_kien_truoc=_dk_kho, lap_buoc=_buoc_taovideo, kiem_dau_ra=_dau_ra_khong_ro,
        bo_cong_cu=("Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill", "Agent", "SendMessage", "TodoWrite"),
        tran_usd_moi_luot=40.0),
}


def lay_loai(ma: str, dot_bat: int) -> LoaiViec:
    loai = DANH_MUC.get(ma) if isinstance(ma, str) else None
    if loai is None:
        raise ThamSoLoi(f"loại việc không có trong danh mục: {ma!r}")
    if loai.dot > dot_bat:
        raise ThamSoLoi(f"loại {ma} thuộc đợt {loai.dot}, chưa mở (đợt đang bật {dot_bat})")
    return loai


def lenh_claude(loai: LoaiViec, viec: dict, mt: MoiTruong) -> list[str]:
    """§6.1. Lần đầu `--session-id`; chỉ `--resume` khi phien_da_tao=1.

    `--strict-mcp-config` (không kèm `--mcp-config`): spike cho thấy `--tools` KHÔNG chặn công cụ MCP của
    người dùng (mcp__engram__*, mcp__boardroom__*) → phải tắt hẳn mọi MCP server ở cả hai lượt (R-05 P1-1).
    """
    if not loai.agent or not loai.bo_cong_cu:
        raise ThamSoLoi(f"loại {loai.ma} không chạy Claude")
    sid = viec.get("session_id")
    if not isinstance(sid, str) or not _RE_SESSION.fullmatch(sid):
        raise ThamSoLoi("việc thiếu session_id UUID")
    phien = ["--resume", sid] if viec.get("phien_da_tao") else ["--session-id", sid]
    them: list[str] = []
    for d in loai.them_thu_muc(viec.get("tham_so") or {}, mt):
        them += ["--add-dir", d]
    return [str(mt.claude_exe), "-p",
            "--agent", loai.agent,
            "--strict-mcp-config",
            "--tools", ",".join(loai.bo_cong_cu),
            "--permission-mode", "dontAsk",
            "--allowedTools", *loai.bo_cong_cu,
            "--disallowedTools", *cong_cu_cam_chung(), *loai.cong_cu_cam,
            "--output-format", "stream-json", "--verbose",
            "--max-budget-usd", str(loai.tran_usd_moi_luot),
            *phien, *them]


def kiem_truoc_buoc(loai: LoaiViec, ten_buoc: str, tham_so: dict, viec: dict, mt: MoiTruong) -> CanNguoiDung | None:
    """Điều kiện chạy một bước giữa chừng. douyin_uid bước kho_ghi: cần canh_quay_an_tien.md mới (§5.1 (3))."""
    if loai.ma == "douyin_uid" and ten_buoc == "kho_ghi":
        uid = kiem_uid(tham_so.get("uid"))
        f = Path(mt.thu_muc_sp) / f"sp_{uid}" / "douyin" / "canh_quay_an_tien.md"
        if not _moi_tu_bat_dau(f, viec):
            return _viec_tay("Douyin bị captcha hoặc cần đăng nhập. Mở Chrome profile Douyin trên máy, giải xong "
                             "bấm Đã làm xong để chạy lại tìm video")
    return None


def can_ban_douyin(doan_log: str) -> str | None:
    """Thông báo KHÔNG chặn khi log agy có dấu hiệu captcha/đăng nhập (§5.1 douyin_uid (2))."""
    if _RE_CAN_BAN_DOUYIN.search(doan_log or ""):
        return "Douyin đòi captcha/đăng nhập — giải trong cửa sổ trên máy nếu đang ngồi máy"
    return None


def phan_tich_poster(stdout: str, buoc_xem: bool) -> tuple[str, bool]:
    """('xong'|'loi', co_lo_ngai) theo dòng quy ước của day_len_poster.py (chỉ đầu dòng). Exit code do vòng chạy kiểm."""
    dong = [d.strip() for d in (stdout or "").splitlines()]
    if any(d.startswith("[LỖI]") for d in dong):
        return "loi", False
    if buoc_xem:
        return "xong", False
    if not any(d.startswith("soát lại:") for d in dong):
        return "loi", False
    return "xong", any(d.startswith("[CẢNH BÁO]") for d in dong)


def quyet_dinh_sau_khoi_dong(viec: dict, ket_qua_kiem: str, loai: LoaiViec) -> tuple[str, str]:
    """§4.6 bảng đối soát. Trả (trạng thái mới, ghi chú). Vòng chạy tự tăng lan_thu khi về 'cho'."""
    if ket_qua_kiem not in DAU_RA:
        raise ThamSoLoi(f"kết quả đối soát lạ: {ket_qua_kiem!r}")
    if ket_qua_kiem in ("xong", "xong_lo_ngai"):
        return "xong", "đối soát sau khởi động lại: đã có đầu ra"
    lan_thu = int(viec.get("lan_thu") or 1)
    if ket_qua_kiem == "chua" and loai.tu_chay_lai and not loai.ton_tien and lan_thu < 3:
        ghi = f"bị ngắt khi máy tắt — tự chạy lại (lần {lan_thu + 1})"
        if viec.get("phien_da_tao"):
            ghi += ", resume phiên Claude cũ"
        return "cho", ghi
    return "loi", "Bị ngắt khi máy tắt — kiểm rồi bấm Chạy tiếp/Chạy lại"


_RE_DONG_UID = re.compile(r"^(\d{19})\t", re.M | re.ASCII)
_RE_DONG_TAM = re.compile(r"^(tam-\d{10,24})\t", re.M | re.ASCII)


def con_tu_xu_ly_link(stdout: str, gioi_han: int) -> tuple[list[str], list[str]]:
    """(UID cần tạo job con phan_tich_uid ≤ gioi_han, id 'tam-…' chưa phân giải). Chỉ đọc dòng `id\\t…` ở đầu dòng."""
    uids = list(dict.fromkeys(_RE_DONG_UID.findall(stdout or "")))
    tam = list(dict.fromkeys(_RE_DONG_TAM.findall(stdout or "")))
    return uids[:max(0, int(gioi_han))], tam


def mp3_hong(p: Path, me: str, bat_dau: datetime, mt: MoiTruong) -> list[Path]:
    """P2-7: mp3 của mẻ có mtime ≥ bat_dau mà ffprobe lỗi (None) hoặc thời lượng ≤ 0. CHỈ liệt kê, không đổi tên."""
    if not isinstance(me, str) or not RE_ME.fullmatch(me):
        raise ThamSoLoi("me sai định dạng")
    thu = Path(p) / "voice"
    if not thu.is_dir():
        return []
    moc = gio_vn(bat_dau).timestamp()
    kq: list[Path] = []
    for f in sorted(thu.glob(f"{me}_*_adam.mp3")):
        try:
            if not f.is_file() or f.stat().st_mtime < moc:
                continue
        except OSError as e:
            log.warning("không đọc được %s: %s", f, e)
            continue
        tl = mt.thoi_luong_media(f)
        if tl is None or tl <= 0:
            kq.append(f)
    return kq
