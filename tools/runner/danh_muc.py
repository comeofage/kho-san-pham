"""Danh mục việc cố định (D3, docs/bo-chay-viec.md §5.1, §5.2, §6.1, §4.6).

Web không gửi đường dẫn hay lệnh: mọi argv dựng ở đây từ tham số đã validate chặt.
Đợt 3: radar_ban_tin, phan_tich_uid, douyin_uid, xu_ly_link_moi, poster_day_folder, voice_pv; poster_bo_loai (B-L1,
docs/giao-dien-menu-trai.md §4.9 — miễn phí, dời video bị chấm Loại khỏi thư mục đăng, bo_loai.py).
Đợt 4 (tốn tiền, luôn cần duyệt có chữ ký): muse_clip, voice_genmax (2 pha), poster_len_lich.
Đợt 5 (D11, B-4): taovideo — MỘT phiên Claude sống (lenh_claude_song, BuocChay.song=True), tốn tiền, đối soát
chỉ đọc file (doi_soat_taovideo).
Đợt 6 (D10, docs/sua-video.md §7): sua_video, hoan_tac_sua — miễn phí, làn gpu, gắn dot=4 (không nâng dot_bat để
khỏi mở taovideo). Chữ phụ đề KHÔNG BAO GIỜ vào argv: chỉ nằm trong file DATA/sua/<ban_sua>.json runner tự ghi.

Loại tốn tiền KHÔNG BAO GIỜ tự chạy lại (tu_chay_lai=False, đối soát 'khong_ro'). voice_genmax chỉ thêm
`--dong-y` khi việc ở bước 'chay' VÀ đã có đủ trường duyệt; không đường nào sinh `--gui-lai-ma`.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from . import bo_loai as bl
from . import sua_video as sv
from .du_an import RE_MA, RE_ME, ds_du_an, ds_me, kiem_uid, tim_du_an
from .han_muc import TRAN_LUOT
from .kho_viec import RE_BAN_SUA, TEN_DB, doc_ban_sua_chi_doc
from .kieu import DAU_RA, BuocChay, CanNguoiDung, MoiTruong, ThamSoLoi, gio_vn

log = logging.getLogger(__name__)

PYTHON = "python"
RADAR_XUAT = Path(__file__).with_name("radar_xuat.py")
BO_LOAI = Path(__file__).with_name("bo_loai.py")   # B-L1 (§4.9 giao-dien-menu-trai.md); cai_runner chép cùng bản cài
THU_MUC_SKILL_DOUYIN = "C:/Users/Mi/.gemini/config/skills/timvideodouyin"
CONG_POSTER = 8023
CONG_PERFECTVOICE = 7890
CONG_VIDEO_BATCH = 3786          # app Video Batch Local (Muse), aff-muse.md
TAO_VOICE = "tao_voice.py"       # script GenMax trong thư mục scripts skill tao-video-tu-canh-quay

# ---------- đợt 6: sửa video (docs/sua-video.md §6.1, §6.2, §7) ----------
PYTHON_ENGINE_MAC_DINH = Path(r"F:\auto video oneshot\.venv\Scripts\python.exe")
THU_MUC_ENGINE_MAC_DINH = Path(r"F:\auto video oneshot")
KHOA_MAY_MAC_DINH = Path(r"E:\oneshottramcanh\.render-may.lock")   # khoá toàn máy của cầu nối Adam (KhoaPlan)
BO_CHUYEN_DOI = Path(__file__).with_name("sua_video_engine.py")   # A-6; cai_runner chép cùng bản cài (D8)
KHOA_RENDER_TUOI_S = 180         # = het_han của KhoaPlan: khoá có mtime mới hơn → mẻ đang dựng → 'ban'
THU_MUC_BAN_SUA = "sua"          # DATA/sua/<ban_sua>.json
_ENV_ENGINE = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
_GHI_THU_LAI = 6                 # os.replace thử lại khi NTFS khoá tạm (Search Indexer/Antivirus)


def python_engine() -> Path:
    return Path(os.environ.get("KHO_PYTHON_ENGINE") or PYTHON_ENGINE_MAC_DINH)


def thu_muc_engine() -> Path:
    return Path(os.environ.get("KHO_ENGINE_DIR") or THU_MUC_ENGINE_MAC_DINH)


def khoa_may_render() -> Path:
    return Path(os.environ.get("AUTOVIDEO_KHOA_MAY") or KHOA_MAY_MAC_DINH)

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

# ---------- đợt 5: taovideo (D11, docs/bo-chay-viec.md §5.3, §7) ----------
# §7.9: không SendMessage (không có trong -p); có cả Agent (tên tool_use) và Task (tên trong init.tools).
BO_CONG_CU_TAOVIDEO: tuple[str, ...] = ("Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill", "Agent", "Task",
                                        "TaskOutput", "TaskStop", "TodoWrite")
LOAI_PHIEN_SONG: tuple[str, ...] = ("taovideo",)     # loại chạy bằng phiên sống (§7.2), không theo lượt + --resume
THU_MUC_SKILLS = "C:/Users/Mi/.claude/skills"
TU_TIM_DU_AN_B = "tu_tim"
WM_KHONG = "khong"
GIA_TAOVIDEO = (1_000, 10_000_000)
NHAN_KHO_BUOC_B = "nha.cua.mit"  # account Poster của autovideo-oneshot (kho.py video --nhan), không phải watermark
TOM_TAT_DOI_SOAT_TOI_DA = 800
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
    """Danh sách folder Poster đã chuẩn hoá [{id:int, ten:str, duong_dan:str}] từ `mt.doc_folder_poster()`.
    `duong_dan` (path của folder, "" nếu thiếu) CHỈ dùng nội bộ (B-L1 `_dk_poster_len_lich`): api bỏ trước khi trả
    ra web. Mục hỏng bị bỏ. Không đọc được (Poster tắt, venv lỗi…) → ThamSoLoi."""
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
        dd = f.get("duong_dan")
        ra.append({"id": fid, "ten": ten[:120] if isinstance(ten, str) else "",
                   "duong_dan": dd if isinstance(dd, str) else ""})
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


class ChuaChotDuAnB(ThamSoLoi):
    """§7.10: "tu_tim" ra 0 hoặc ≥ 2 dự án có takes/*.mp4 → 400 kèm danh sách để web cho chọn (`them` gộp vào JSON)."""

    def __init__(self, thong_diep: str, ung_vien: list[dict]):
        super().__init__(thong_diep)
        self.them = {"ung_vien_b": ung_vien}


def _co_takes_mp4(p: Path) -> bool:
    """`<p>/takes/*.mp4` có ít nhất một file (không đệ quy, không phân biệt hoa thường đuôi)."""
    t = p / "takes"
    try:
        return t.is_dir() and any(f.suffix.lower() == ".mp4" and f.is_file() for f in t.iterdir())
    except OSError as e:
        log.warning("không đọc được %s: %s — coi như không có takes", t, e)
        return False


def chot_du_an_b(uid: str, gia_tri: str, mt: MoiTruong) -> str:
    """§7.10 (luật taomevideo SKILL.md:36-43, làm lúc TẠO việc thay vì hỏi giữa chừng).
    "tu_tim" → mã dự án DUY NHẤT của UID có takes/*.mp4; 0 hoặc ≥ 2 → ChuaChotDuAnB kèm danh sách mọi dự án của UID
    ({ma, ten, co_takes}). Mã cụ thể → phải là dự án có thật của UID (người dùng đã chỉ định; không bắt có takes —
    Bước 0 của autovideo-oneshot được chép take từ thư mục anh em khi dự án B do người dùng chọn)."""
    uid = kiem_uid(uid)
    if gia_tri == TU_TIM_DU_AN_B:
        ung_vien = [{"ma": d["ma"], "ten": d["ten"], "co_takes": _co_takes_mp4(Path(d["goc"]) / d["ten"])}
                    for d in ds_du_an(uid, mt.gocs)]
        co = [d["ma"] for d in ung_vien if d["co_takes"]]
        if len(co) == 1:
            return co[0]
        if not co:
            raise ChuaChotDuAnB("Không có dự án nào của UID có takes/*.mp4 — quay takes trước hoặc chọn dự án B",
                                ung_vien)
        raise ChuaChotDuAnB(f"Có {len(co)} dự án của UID có takes/*.mp4 — chọn một dự án B", ung_vien)
    if not isinstance(gia_tri, str) or not RE_MA.fullmatch(gia_tri):
        raise ThamSoLoi(f"du_an_b phải là mã 12 hex hoặc {TU_TIM_DU_AN_B!r}")
    _du_an({"uid": uid, "du_an": gia_tri}, mt)
    return gia_tri


def wm_cho_phep() -> tuple[str, ...]:
    from .han_muc import WM_CHO_PHEP
    return (WM_KHONG, *WM_CHO_PHEP)


def _ts_taovideo(ts: dict, mt: MoiTruong) -> dict:
    """§5.3/§7.10: uid, du_an_a (có raw/), du_an_b (mã | "tu_tim" → runner chốt), wm ∈ ("khong", *WM_CHO_PHEP),
    gia int 1.000–10.000.000 hoặc bỏ trống/null (null không lưu). Không nhận chữ tự do."""
    _chi_khoa(_la_dict(ts), {"uid", "du_an_a", "du_an_b", "wm", "gia"})
    uid = kiem_uid(ts.get("uid"))
    a = ts.get("du_an_a")
    if not isinstance(a, str) or not RE_MA.fullmatch(a):
        raise ThamSoLoi("du_an_a phải là mã 12 hex")
    pa = _du_an({"uid": uid, "du_an": a}, mt)
    if not (pa / "raw").is_dir():
        raise ThamSoLoi("dự án A chưa có thư mục raw/ (cảnh quay) — chọn dự án khác")
    b = chot_du_an_b(uid, ts.get("du_an_b"), mt)
    wm = ts.get("wm")
    if not isinstance(wm, str) or wm not in wm_cho_phep():
        raise ThamSoLoi(f"wm phải là một trong {list(wm_cho_phep())}")
    ra: dict = {"uid": uid, "du_an_a": a, "du_an_b": b, "wm": wm}
    gia = ts.get("gia")
    if gia is not None:
        if not _la_so_nguyen(gia) or not GIA_TAOVIDEO[0] <= gia <= GIA_TAOVIDEO[1]:
            raise ThamSoLoi(f"gia phải là số nguyên {GIA_TAOVIDEO[0]}–{GIA_TAOVIDEO[1]} (đồng) hoặc bỏ trống")
        ra["gia"] = gia
    return ra


def _kiem_ma_video(ma: object) -> str:
    if not isinstance(ma, str) or not sv.RE_MA_VIDEO.fullmatch(ma):
        raise ThamSoLoi("ma_video phải là 16 ký tự hex thường")
    return ma


def video_cua_tham_so(ts: dict, mt: MoiTruong) -> tuple[Path, "sv.VideoSua"]:
    """(thư mục dự án, video) theo uid + du_an + ma_video. Runner tự dò đường dẫn — web không gửi đường dẫn.
    Không thấy dự án/video → ThamSoLoi."""
    ma = _kiem_ma_video(ts.get("ma_video"))
    p = _du_an(ts, mt)
    try:
        return p, sv.tim_video(p, p.parent, ma)
    except sv.KhongTraDuoc as e:
        raise ThamSoLoi(e.ly_do) from e


def _ts_sua_chung(ts: object, mt: MoiTruong, them: str) -> dict:
    _chi_khoa(_la_dict(ts), {"uid", "du_an", "ma_video", them})
    co_ban = _ts_poster({"uid": ts.get("uid"), "du_an": ts.get("du_an")}, mt)
    ma = _kiem_ma_video(ts.get("ma_video"))
    video_cua_tham_so({**co_ban, "ma_video": ma}, mt)      # phải có trong ds_video_sua của dự án
    return {**co_ban, "ma_video": ma}


def _ts_sua_video(ts: dict, mt: MoiTruong) -> dict:
    """§7.1. Chỉ hình dạng + video có thật; `ban_sua` có trong bảng, cùng uid/du_an/ma_video → api kiểm (có KhoViec)."""
    co_ban = _ts_sua_chung(ts, mt, "ban_sua")
    bs = ts.get("ban_sua")
    if not isinstance(bs, str) or not RE_BAN_SUA.fullmatch(bs):
        raise ThamSoLoi("ban_sua phải là 'b' + 16 hex")
    return {**co_ban, "ban_sua": bs}


def _ts_hoan_tac_sua(ts: dict, mt: MoiTruong) -> dict:
    """§7.1. `viec_goc` là việc sua_video ĐÃ xong của cùng video → api kiểm (có KhoViec)."""
    co_ban = _ts_sua_chung(ts, mt, "viec_goc")
    vg = ts.get("viec_goc")
    if not isinstance(vg, str) or not sv.RE_VIEC.fullmatch(vg):
        raise ThamSoLoi("viec_goc phải là mã việc j + 14 số + 4 ký tự")
    return {**co_ban, "viec_goc": vg}


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


def _dk_bo_loai(ts: dict, mt: MoiTruong) -> CanNguoiDung | str | None:
    """poster_bo_loai (FX-B3 P3-6): chỉ `git fetch` + đọc ref remote, không đụng cây làm việc → KHÔNG đòi data/ sạch
    như _dk_kho (việc cũ từng kẹt can_tra_loi vì data/ bẩn). Chỉ chờ ('ban') khi chẩn đoán thấy git kho đang bận;
    các nhánh việc tay khác của chẩn đoán (data/ bẩn, khoá index cũ…) không liên quan fetch → bỏ qua."""
    kiem_uid(ts.get("uid"))
    return "ban" if mt.chan_doan_kho(mt.repo_kho) == "ban" else None


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


TB_NGUNG_DANG = "Sản phẩm đang gắn ⛔ Ngừng đăng — gỡ thẻ trước khi lên lịch"


def _ngung_dang(du_lieu: bytes | None, nguon: str) -> bool:
    """Thẻ ⛔ Ngừng đăng trong info.json (cùng cách đọc của kho.py:292 — `bool(info.ngung_dang)`).
    Chưa có info.json → không có thẻ. Hỏng → LoiDuLieu (không đoán là không có thẻ)."""
    if du_lieu is None:
        return False
    try:
        info = json.loads(du_lieu.decode("utf-8-sig"))
    except ValueError as e:              # UnicodeDecodeError và JSONDecodeError đều là ValueError
        raise bl.LoiDuLieu(f"{nguon} không đọc được: {e}") from e
    if not isinstance(info, dict):
        raise bl.LoiDuLieu(f"{nguon} không phải object")
    return bool(info.get("ngung_dang"))


def _dk_poster_len_lich(ts: dict, mt: MoiTruong) -> CanNguoiDung | str | None:
    """Poster sống + (B-L1, §4.9) folder không còn video bị chấm Loại ở cấp trên + (P2-3) sản phẩm không gắn
    ⛔ Ngừng đăng. Vòng chạy gọi hàm này TRƯỚC khi tiêu lời duyệt (FX-18), nên chặn ở đây không mất lời duyệt —
    chỉ phải Xin duyệt lại.
    Dữ liệu chấm + thẻ đọc BẢN MỚI NHẤT trên remote (web ghi thẳng lên GitHub): `git fetch` (có timeout) rồi đọc
    ref upstream — không pull, không đụng cây làm việc. Fetch/đọc lỗi → việc tay, KHÔNG cho qua.
    ⛔ kiểm cho MỌI folder có thư mục cha kết thúc bằng UID (cả compose_output của creator); fetch vướng khoá ref
    (git/kho.py khác đang ghi) → 'ban' (chờ). Đếm Loại chỉ cho `<GOC>/*<UID>/output_poster|output`; folder không
    nhận ra UID → không biết → không chặn. KHÔNG giữ mutex `kho`: fetch chỉ ghi ref remote, đụng khoá → 'ban'."""
    if not mt.cong_song(CONG_POSTER):
        return _viec_tay(f"Mở Poster V2 trên máy (cổng {CONG_POSTER} chưa sống) rồi bấm Đã làm xong")
    fid = ts.get("folder_id")
    try:
        ds = ds_folder_poster(mt)
    except ThamSoLoi as e:
        return _viec_tay(f"{e} — không kiểm được video bị Loại trong folder. Mở Poster V2 rồi bấm Đã làm xong")
    f = next((x for x in ds if x["id"] == fid), None)
    if f is None:
        return _viec_tay(f"Poster không còn folder id {fid} (đã xoá?) — kiểm trong app Poster")
    # FX-B2 P2-3: UID từ thư mục cha với MỌI thư mục con (kể cả compose_output của creator, gốc lạ) → kiểm ⛔ TRƯỚC.
    uid = bl.uid_cua_folder(f["duong_dan"])
    if uid is None:
        return None
    repo = Path(mt.repo_kho)
    try:
        ref = bl.lay_ban_moi_nhat(repo, fetch=True)
    except bl.LoiGit as e:
        if e.tam_thoi:                   # chắc chắn chỉ là khoá ref do git/kho.py khác giữ → chờ rồi thử lại
            log.info("folder Poster %s: git kho đang bận (%s) — chờ", fid, e)
            return "ban"
        log.warning("folder Poster %s: không lấy được bản kho mới nhất: %s", fid, e)
        return _viec_tay("Không lấy được dữ liệu mới nhất của kho từ GitHub (git fetch lỗi/quá giờ) nên chưa biết "
                         "sản phẩm có bị Ngừng đăng hay còn video Loại không — kiểm mạng/git trên máy rồi bấm Đã "
                         "làm xong")
    duong_info = f"data/{uid}/info.json"
    try:
        ngung = _ngung_dang(bl.doc_file_ban_moi(repo, ref, duong_info), duong_info)
    except bl.LoiDuLieu as e:            # gồm LoiGit
        log.warning("folder Poster %s: không đọc được info.json: %s", fid, e)
        return _viec_tay("Không đọc được thông tin sản phẩm (info.json) nên chưa biết có gắn ⛔ Ngừng đăng không "
                         "— kiểm trên máy rồi bấm Đã làm xong")
    if ngung:
        return _viec_tay(TB_NGUNG_DANG)
    fk = bl.folder_cua_kho(f["duong_dan"], list(mt.gocs))
    if fk is None:                       # chỉ output_poster|output dưới gốc kho mới đếm Loại được
        return None
    try:
        loai = bl.loai_trong_folder_tu(fk, bl.doc_ket_qua_duyet_ref(repo, ref, fk.uid))
    except bl.LoiDuLieu as e:            # gồm LoiGit
        log.warning("folder Poster %s: không đếm được video Loại: %s", fid, e)
        return _viec_tay("Không đọc được dữ liệu chấm (duyet.json) của sản phẩm nên chưa biết folder còn video "
                         "Loại không — kiểm trên máy rồi bấm Đã làm xong")
    if loai:
        return _viec_tay(f"Folder còn {len(loai)} video bị Loại: chạy 'Gỡ video Loại' ở trang Đăng bài, xong rồi "
                         "Xin duyệt lại")
    return None


def _khoa_con_tuoi(f: Path) -> bool:
    """Khoá render (định dạng KhoaPlan, nhịp tim os.utime 30 s) có mtime trong KHOA_RENDER_TUOI_S giây gần nhất.
    So với đồng hồ THẬT (mtime file là giờ thật). Khoá cũ hơn = bị bỏ rơi → không chặn (bộ chuyển đổi tự xử)."""
    try:
        return f.is_file() and time.time() - f.stat().st_mtime < KHOA_RENDER_TUOI_S
    except OSError as e:
        log.warning("không đọc được khoá render %s: %s — coi như đang bận", f, e)
        return True


def _dk_sua_video(ts: dict, mt: MoiTruong) -> CanNguoiDung | str | None:
    """§7.2 (cả sua_video và hoan_tac_sua). Không có việc mở của loại kia trên cùng ma_video: api chặn lúc tạo/chạy
    tiếp (cần KhoViec) — hai loại không bao giờ cùng mở."""
    p = _dk_du_an(ts, mt)
    if isinstance(p, CanNguoiDung):
        return p
    py = python_engine()
    if not py.is_file():
        return _viec_tay(f"Không thấy Python của app dựng video {py.as_posix()} — kiểm ổ F rồi bấm Đã làm xong")
    if mt.ffmpeg_ngoai():
        return "ban"
    if _khoa_con_tuoi(p / ".render.lock") or _khoa_con_tuoi(khoa_may_render()):
        log.info("Đang có mẻ dựng video (khoá render còn tươi) — chờ")
        return "ban"
    return None


def _dk_taovideo(ts: dict, mt: MoiTruong) -> CanNguoiDung | str | None:
    """Dự án A và B còn trên đĩa; không có ffmpeg ngoài đang chạy (người dùng dựng tay) → đợi; chẩn đoán kho."""
    for khoa in ("du_an_a", "du_an_b"):
        p = _dk_du_an({"uid": ts.get("uid"), "du_an": ts.get(khoa)}, mt)
        if isinstance(p, CanNguoiDung):
            return p
    if mt.ffmpeg_ngoai():
        return "ban"
    return mt.chan_doan_kho(mt.repo_kho)


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


def _buoc_bo_loai(ts: dict, viec: dict, mt: MoiTruong) -> list[BuocChay]:
    """B-L1 (§4.9): bo_loai.py --tu-remote = git fetch (có timeout) + đọc duyet.json ở ref upstream (bản web vừa
    ghi). KHÔNG dùng kho.py xem (git pull --rebase --autostash trên cây làm việc có code chưa commit)."""
    uid = kiem_uid(ts.get("uid"))
    repo = Path(mt.repo_kho)
    het = DANH_MUC["poster_bo_loai"].het_gio_s
    goc = [x for g in mt.gocs for x in ("--goc", Path(g).as_posix())]
    return [_buoc("bo_loai", [PYTHON, "-B", "-I", str(BO_LOAI), "--repo-kho", repo.as_posix(), "--uid", uid, *goc,
                              "--tu-remote"], repo, het)]


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


def _them_thu_muc_taovideo(ts: dict, mt: MoiTruong) -> tuple[str, ...]:
    """§7.2 `--add-dir`: dự án B (cwd là dự án A), engine autovideo, thư mục skills."""
    b = _du_an({"uid": ts.get("uid"), "du_an": ts.get("du_an_b")}, mt)
    return (b.as_posix(), thu_muc_engine().as_posix(), THU_MUC_SKILLS)


def _buoc_taovideo(ts: dict, viec: dict, mt: MoiTruong, hm: dict | None = None) -> list[BuocChay]:
    """§7.2: MỘT bước phiên sống, cwd = dự án A, stdin = phiếu lần đầu (vòng chạy thay bằng lap_phieu_tiep_taovideo
    khi chạy sau xin duyệt lại), het_gio_s = đồng hồ làm (lam_s).
    FX-29: `hm` = hạn mức hiệu lực vòng chạy đang giữ → --max-budget-usd, đồng hồ, phiếu in trần theo nó.
    None → trần code cho argv/đồng hồ, phiếu tự đọc cau_hinh.json (phieu._tran_taovideo)."""
    from .han_muc import HAN_MUC_TRAN, _gia_tri, het_gio_taovideo
    from .phieu import lap_phieu
    loai = DANH_MUC["taovideo"]
    nguon = HAN_MUC_TRAN if hm is None else hm
    a = _du_an({"uid": ts.get("uid"), "du_an": ts.get("du_an_a")}, mt)
    argv = lenh_claude_song(loai, viec, mt, float(_gia_tri(nguon, "taovideo_usd_viec")))
    stdin = lap_phieu(loai, viec, mt, int(_gia_tri(nguon, "dot_bat")), hm)
    b = _buoc("claude_song", argv, a, het_gio_taovideo(nguon)["lam_s"], stdin=stdin, la_claude=True)
    return [replace(b, song=True)]


def lap_buoc_hieu_luc(loai: "LoaiViec", ts: dict, viec: dict, mt: MoiTruong, hm: dict) -> list[BuocChay]:
    """FX-29: vòng chạy lập bước bằng hàm này để phiếu phiên sống in trần theo `hm` nó đang giữ.
    `loai.lap_buoc` vẫn là nguồn bước (argv/cwd/đồng hồ — test có thể bọc lại); với loại phiên sống, stdin của bước
    song được lập lại bằng lap_phieu(..., hm). Loại khác: trả nguyên lap_buoc."""
    from .han_muc import _gia_tri
    from .phieu import lap_phieu
    ds = loai.lap_buoc(ts, viec, mt)
    if loai.ma not in LOAI_PHIEN_SONG:
        return ds
    phieu = lap_phieu(loai, viec, mt, int(_gia_tri(hm, "dot_bat")), hm)
    return [replace(b, stdin=phieu) if b.song and isinstance(b.stdin, str) and b.stdin.strip() else b for b in ds]


def _id_viec(viec: dict) -> str:
    id_ = viec.get("id")
    if not isinstance(id_, str) or not sv.RE_VIEC.fullmatch(id_):
        raise ThamSoLoi("mã việc không hợp lệ")
    return id_


def _ghi_nguyen_tu(f: Path, noi: str) -> None:
    """Ghi file tạm rồi os.replace; thử lại có giãn cách khi NTFS khoá tạm (PermissionError)."""
    f.parent.mkdir(parents=True, exist_ok=True)
    tam = f.with_name(f"{f.name}.{os.getpid()}.tmp")
    tam.write_text(noi, encoding="utf-8", newline="\n")
    cho = 0.05
    for lan in range(_GHI_THU_LAI):
        try:
            os.replace(tam, f)
            return
        except PermissionError as e:
            if lan == _GHI_THU_LAI - 1:
                try:
                    tam.unlink()
                except OSError as e2:
                    log.warning("không xoá được file tạm %s: %s", tam, e2)
                raise ThamSoLoi(f"không ghi được {f.name} (file đang bị khoá): {e}") from e
            log.warning("os.replace %s bị khoá (lần %d): %s — thử lại", f, lan + 1, e)
            time.sleep(cho)
            cho *= 2


def ghi_file_ban_sua(ts: dict, mt: MoiTruong) -> Path:
    """§7.2 lap_buoc: đọc bảng ban_sua (DB runner, chỉ đọc) → ghi DATA/sua/<ban_sua>.json = JSON chuẩn của bản sửa.
    Chặn mọi lệch: không có dòng, khác uid/du_an/ma_video, nội dung không băm ra đúng mã (DB bị sửa tay)."""
    bs = ts.get("ban_sua")
    if not isinstance(bs, str) or not RE_BAN_SUA.fullmatch(bs):
        raise ThamSoLoi("ban_sua sai định dạng")
    data = Path(mt.thu_muc_du_lieu)
    try:
        dong = doc_ban_sua_chi_doc(data / TEN_DB, bs)
    except sqlite3.Error as e:
        log.warning("không đọc được bảng ban_sua (%s): %s", bs, e)
        raise ThamSoLoi(f"không đọc được bản sửa {bs} trong DB runner ({type(e).__name__})") from e
    if dong is None:
        raise ThamSoLoi(f"không còn bản sửa {bs} (đã dọn sau 30 ngày?) — mở lại video và lưu lại")
    if (dong["uid"], dong["du_an"], dong["ma_video"]) != (ts.get("uid"), ts.get("du_an"), ts.get("ma_video")):
        raise ThamSoLoi("bản sửa không thuộc video của việc này")
    noi = dong["noi_dung"]
    if not isinstance(noi, dict) or sv.ma_ban_sua(noi) != bs or noi.get("ma_video") != ts.get("ma_video"):
        log.error("bản sửa %s trong DB không khớp mã nội dung — từ chối chạy", bs)
        raise ThamSoLoi("bản sửa trong DB không khớp mã (bị sửa ngoài?) — không chạy")
    f = data / THU_MUC_BAN_SUA / f"{bs}.json"
    _ghi_nguyen_tu(f, tham_so_chuan(noi))
    return f


def _lenh_engine(lenh: str, p: Path, v: "sv.VideoSua", them: list[str], id_: str) -> list[str]:
    """argv §6.1: chỉ giá trị runner tự dò (đường dẫn dự án, thư mục/tên video trên đĩa đã qua RE_TEN) hoặc mã đã
    kiểm định dạng (ban_sua là đường dẫn file runner ghi, viec_goc/viec). Không chữ nào từ web."""
    if not sv.RE_TEN.fullmatch(v.ten) or v.thu_muc not in sv.THU_MUC:
        raise ThamSoLoi("tên/thư mục video không hợp lệ để dựng lại")
    return [str(python_engine()), str(BO_CHUYEN_DOI), lenh, "--project", str(p), "--thu-muc", v.thu_muc,
            "--video", v.ten, *them, "--viec", id_]


def _buoc_sua_video(ts: dict, viec: dict, mt: MoiTruong) -> list[BuocChay]:
    id_ = _id_viec(viec)
    p, v = video_cua_tham_so(ts, mt)
    f = ghi_file_ban_sua(ts, mt)
    b = _buoc("sua_video", _lenh_engine("ap-dung", p, v, ["--ban-sua", str(f)], id_), thu_muc_engine(),
              DANH_MUC["sua_video"].het_gio_s)
    return [replace(b, env_them=dict(_ENV_ENGINE))]


def _buoc_hoan_tac_sua(ts: dict, viec: dict, mt: MoiTruong) -> list[BuocChay]:
    id_ = _id_viec(viec)
    vg = ts.get("viec_goc")
    if not isinstance(vg, str) or not sv.RE_VIEC.fullmatch(vg):
        raise ThamSoLoi("viec_goc sai định dạng")
    p, v = video_cua_tham_so(ts, mt)
    b = _buoc("hoan_tac_sua", _lenh_engine("hoan-tac", p, v, ["--viec-goc", vg], id_), thu_muc_engine(),
              DANH_MUC["hoan_tac_sua"].het_gio_s)
    return [replace(b, env_them=dict(_ENV_ENGINE))]


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


def _dau_ra_bo_loai(ts: dict, viec: dict, mt: MoiTruong) -> str:
    """Quét lại theo duyet.json bản mới nhất trên remote (fetch, như bước chạy): thư mục đăng đã khớp kết quả chấm
    (không còn gì để dời chiều nào) → xong; còn → chua. Fetch/đọc lỗi → khong_ro (không đoán)."""
    uid = kiem_uid(ts.get("uid"))
    try:
        kq = bl.doc_ket_qua_duyet_moi_nhat(Path(mt.repo_kho), uid, fetch=True)
        con = bl.viec_con(bl.lap_ke_hoach_tu(kq, uid, list(mt.gocs)))   # "giu" cần người chấm lại
    except bl.LoiDuLieu as e:            # gồm LoiGit
        log.warning("đối soát poster_bo_loai %s: %s", uid, e)
        return "khong_ro"
    return "chua" if con else "xong"


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


_THU_MUC_NHAT_KY = tuple(dict.fromkeys((*sv.THU_MUC, *sv.OUT_A)))   # nơi file_ra có thể nằm (C: output*, A: out)


def _doc_nhat_ky_viec(p: Path, id_: str) -> dict | None:
    """Nhật ký `<thư mục file_ra>/_sua/<id>.json` (sua_video.duong_nhat_ky). Không dựa vào tra_ban_ghi: sau khi dựng
    lại, bản ghi có thể đổi (vd luồng A: plan mới hơn video). Không có → None; hỏng/trùng/không phải của việc này →
    ValueError (bên gọi trả khong_ro — không đoán, không tự chạy lại mù)."""
    if not sv.RE_VIEC.fullmatch(id_):
        raise ValueError("mã việc không hợp lệ")
    thay = [(p / d / "_sua" / f"{id_}.json") for d in _THU_MUC_NHAT_KY]
    ds = [nk for f in thay if (nk := sv.doc_nhat_ky(f)) is not None]
    if not ds:
        return None
    if len(ds) > 1:
        raise ValueError(f"nhiều nhật ký cho việc {id_}")
    nk = ds[0]
    if nk.get("viec") not in (None, id_):
        raise ValueError(f"nhật ký {id_} ghi mã việc khác")
    return nk


def _file_khop(p: Path, rel: object, mong: object) -> bool | None:
    """File `P/rel` có đúng {size, mtime_ns}? None = dữ liệu nhật ký không dùng được (đường dẫn lạ/thoát khỏi P)."""
    if not isinstance(rel, str) or not rel or not isinstance(mong, dict):
        return None
    size, ns = mong.get("size"), mong.get("mtime_ns")
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (size, ns)):
        return None
    goc = p.resolve()
    f = (goc / rel).resolve()
    if not f.is_relative_to(goc):
        log.warning("nhật ký trỏ ra ngoài dự án: %r", rel)
        return None
    try:
        st = f.stat()
    except FileNotFoundError:
        return False
    return st.st_size == size and st.st_mtime_ns == ns


def _dau_ra_sua_video(ts: dict, viec: dict, mt: MoiTruong) -> str:
    """§7.2: nhật ký 'xong' + file_ra khớp `moi` → xong; có nhật ký chưa xong / chưa có → chua (chạy lại CÙNG id thì
    bộ chuyển đổi đọc nhật ký làm nốt hoặc hoàn nguyên, §6.3); xong mà file khác, nhật ký hỏng → khong_ro."""
    try:
        p = _du_an(ts, mt)
        nk = _doc_nhat_ky_viec(p, _id_viec(viec))
    except (ThamSoLoi, ValueError, OSError) as e:
        log.warning("đối soát sua_video %s: %s", viec.get("id"), e)
        return "khong_ro"
    if nk is None or nk.get("buoc") != "xong":
        return "chua"
    khop = _file_khop(p, nk.get("video"), nk.get("moi"))
    return "xong" if khop else "khong_ro"


def _dau_ra_hoan_tac_sua(ts: dict, viec: dict, mt: MoiTruong) -> str:
    """Video đã trở về đúng `cu` của việc gốc (os.replace giữ mtime) và nhật ký hoàn tác (nếu có) đã xong → xong;
    còn đúng `moi` của việc gốc hoặc nhật ký hoàn tác dở → chua; còn lại (file lạ, thiếu nhật ký gốc) → khong_ro."""
    try:
        p = _du_an(ts, mt)
        vg = ts.get("viec_goc")
        if not isinstance(vg, str):
            raise ThamSoLoi("viec_goc thiếu")
        goc = _doc_nhat_ky_viec(p, vg)
        rieng = _doc_nhat_ky_viec(p, _id_viec(viec))
    except (ThamSoLoi, ValueError, OSError) as e:
        log.warning("đối soát hoan_tac_sua %s: %s", viec.get("id"), e)
        return "khong_ro"
    if goc is None:
        return "khong_ro"
    if rieng is not None and rieng.get("buoc") != "xong":
        return "chua"
    ve_cu = _file_khop(p, goc.get("video"), goc.get("cu"))
    if ve_cu:
        return "xong"
    if rieng is None and _file_khop(p, goc.get("video"), goc.get("moi")):
        return "chua"
    return "khong_ro"


def _doc_json_file(f: Path) -> object | None:
    """JSON trong file; thiếu/hỏng → None (bên gọi ghi "không đọc được" vào tóm tắt, không đoán)."""
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        log.warning("không đọc được JSON %s: %s", f, e)
        return None


def _buoc_xong(trang_thai: object, buoc: str) -> bool:
    b = trang_thai.get("buoc") if isinstance(trang_thai, dict) else None
    m = b.get(buoc) if isinstance(b, dict) else None
    return isinstance(m, dict) and m.get("xong") is True


def _thuoc_du_an(duong_dan: object, p: Path) -> bool:
    """`duong_dan` (chuỗi trong kho) nằm trong thư mục dự án `p` (so không phân biệt hoa thường, `/` hay `\\`)."""
    if not isinstance(duong_dan, str) or not duong_dan.strip():
        return False
    d = os.path.normcase(os.path.abspath(duong_dan.strip()))
    g = os.path.normcase(os.path.abspath(p)).rstrip("\\/")
    return d == g or d.startswith(g + os.sep)


def _moc_tao_viec(viec: dict) -> float:
    s = viec.get("tao_luc")
    try:
        return gio_vn(datetime.fromisoformat(s)).timestamp()
    except (TypeError, ValueError) as e:
        raise ThamSoLoi(f"việc thiếu/sai tao_luc: {s!r}") from e


def _me_moi_buoc_a(a: Path, moc: float) -> list[str]:
    """Mã mẻ có `<A>/kich-ban/<B>_trang-thai.json` mtime ≥ moc (tên mẻ đúng RE_ME), theo thứ tự tên."""
    kb = a / "kich-ban"
    ra: list[str] = []
    try:
        ds = sorted(kb.glob("*_trang-thai.json"))
    except OSError as e:
        log.warning("không liệt kê được %s: %s", kb, e)
        return ra
    for f in ds:
        me = f.name[:-len("_trang-thai.json")]
        if not RE_ME.fullmatch(me):
            continue
        try:
            if f.stat().st_mtime >= moc:
                ra.append(me)
        except OSError as e:
            log.warning("không đọc được mtime %s: %s", f, e)
    return ra


def _dem_mp4_moi(thu: Path, moc: float) -> tuple[int, int]:
    """(số *.mp4 hoàn chỉnh mtime ≥ moc, số *.partial.mp4 bất kể mtime) trong `thu` (không đệ quy)."""
    xong = do = 0
    try:
        ds = list(thu.iterdir()) if thu.is_dir() else []
    except OSError as e:
        log.warning("không liệt kê được %s: %s", thu, e)
        return 0, 0
    for f in ds:
        ten = f.name.lower()
        if not ten.endswith(".mp4"):
            continue
        if ten.endswith(".partial.mp4"):
            do += 1
            continue
        try:
            if f.is_file() and f.stat().st_mtime >= moc:
                xong += 1
        except OSError as e:
            log.warning("không đọc được mtime %s: %s", f, e)
    return xong, do


KHOA_ANH_CHUP_KHO = "kho_luc_tao"     # ket_qua[KHOA_ANH_CHUP_KHO] = anh_chup_kho_taovideo(...) lúc tạo việc


def _dong_kho_taovideo(uid: str, a: Path, b: Path, mt: MoiTruong) -> tuple[dict | None, list[dict], list[dict]]:
    """(info.json hoặc None, dòng Poster của Bước A, dòng Poster của Bước B) — chỉ đọc file.
    A: nhan ≠ nha.cua.mit và duong_dan thuộc dự án A; B: nhan == nha.cua.mit và duong_dan thuộc dự án B."""
    info = _doc_json_file(Path(mt.repo_kho) / "data" / uid / "info.json")
    dlv = info.get("da_lam_video") if isinstance(info, dict) else None
    poster = dlv.get("poster") if isinstance(dlv, dict) else None
    dong = [d for d in poster if isinstance(d, dict)] if isinstance(poster, list) else []
    dong_a = [d for d in dong if d.get("nhan") != NHAN_KHO_BUOC_B and _thuoc_du_an(d.get("duong_dan"), a)]
    dong_b = [d for d in dong if d.get("nhan") == NHAN_KHO_BUOC_B and _thuoc_du_an(d.get("duong_dan"), b)]
    return (info if isinstance(info, dict) else None), dong_a, dong_b


def _cap_dong(d: dict) -> list:
    return [d.get("folder"), d.get("so_video")]


def _khoa_cap(cap: list) -> str:
    return json.dumps(cap, sort_keys=True, ensure_ascii=False)


def anh_chup_kho_taovideo(ts: dict, mt: MoiTruong) -> dict[str, list[list]]:
    """Ảnh chụp dòng kho Poster của việc taovideo (lưu vào ket_qua["kho_luc_tao"] lúc tạo việc): {"a": [[folder,
    so_video]…], "b": […]} theo đúng luật lọc của doi_soat_taovideo. Chỉ đọc file; chưa có info.json → danh sách rỗng."""
    uid = kiem_uid(ts.get("uid"))
    a = _du_an({"uid": uid, "du_an": ts.get("du_an_a")}, mt)
    b = _du_an({"uid": uid, "du_an": ts.get("du_an_b")}, mt)
    _info, dong_a, dong_b = _dong_kho_taovideo(uid, a, b, mt)
    return {"a": [_cap_dong(d) for d in dong_a], "b": [_cap_dong(d) for d in dong_b]}


def _doc_anh_chup(viec: dict) -> tuple[bool, dict[str, set[str]] | None]:
    """(có ảnh chụp không, {"a": tập khoá cặp, "b": …} hoặc None nếu hỏng). Mỗi cặp là [folder, so_video]."""
    kq = viec.get("ket_qua")
    if not isinstance(kq, dict) or KHOA_ANH_CHUP_KHO not in kq:
        return False, None
    ac = kq[KHOA_ANH_CHUP_KHO]
    if not isinstance(ac, dict):
        return True, None
    ra: dict[str, set[str]] = {}
    for phia in ("a", "b"):
        ds = ac.get(phia)
        if not isinstance(ds, list) or not all(isinstance(c, list) and len(c) == 2 for c in ds):
            return True, None
        ra[phia] = {_khoa_cap(c) for c in ds}
    return True, ra


def _co_dong_moi(dong: list[dict], cu: set[str] | None) -> bool:
    """Không có ảnh chụp (cu None) → có dòng là đủ; có ảnh chụp → phải có dòng (folder, so_video) chưa có lúc tạo việc
    (folder mới hoặc đẩy lại cùng folder với so_video khác)."""
    if cu is None:
        return bool(dong)
    return any(_khoa_cap(_cap_dong(d)) not in cu for d in dong)


def doi_soat_taovideo(ts: dict, viec: dict, mt: MoiTruong) -> tuple[str, str]:
    """§7.8, CHỈ ĐỌC FILE (không chạy lệnh, không git pull, không cần mutex kho). ('xong'|'chua', tóm tắt ≤800).

    - Bước A: mỗi `<A>/kich-ban/<B>_trang-thai.json` mtime ≥ tao_luc → buoc.verify.xong, `_log/<B>_tron_goi.xong.json`
      exit, buoc.ban_giao.xong.
    - Kho: `data/<UID>/info.json` → da_lam_video.poster[]: dòng nhan ≠ nha.cua.mit có duong_dan thuộc dự án A, và
      dòng nhan == nha.cua.mit có duong_dan thuộc dự án B. Dòng kho không có thời gian, nên (FX-28) nếu việc có ảnh chụp
      kho lúc tạo (`ket_qua.kho_luc_tao`, xem anh_chup_kho_taovideo) thì mỗi bước phải có dòng MỚI so với ảnh chụp;
      ảnh chụp hỏng → 'chua'. Không có ảnh chụp → dòng nào khớp cũng tính, Bước B dựa vào mp4 mới.
    - Bước B: số `<B>/output/*.mp4` mtime ≥ tao_luc, số *.partial.mp4.
    xong ⇔ ≥ 1 mẻ A verify xong + tron-goi exit 0 + cả 2 dòng kho (mới, nếu có ảnh chụp) + Bước B ≥ 1 mp4 mới và
    0 partial. Tham số hỏng / thiếu tao_luc → ThamSoLoi (kiem_dau_ra_an_toan đổi thành 'khong_ro')."""
    uid = kiem_uid(ts.get("uid"))
    a = _du_an({"uid": uid, "du_an": ts.get("du_an_a")}, mt)
    b = _du_an({"uid": uid, "du_an": ts.get("du_an_b")}, mt)
    moc = _moc_tao_viec(viec)
    phan: list[str] = []
    me_dat = False
    ds_me_moi = _me_moi_buoc_a(a, moc)
    if not ds_me_moi:
        phan.append("Bước A: chưa có mẻ mới từ lúc tạo việc")
    for me in ds_me_moi:
        tt = _doc_json_file(a / "kich-ban" / f"{me}_trang-thai.json")
        if not isinstance(tt, dict):
            phan.append(f"Bước A mẻ {me}: không đọc được file trạng thái")
            continue
        verify = _buoc_xong(tt, "verify")
        tg = _doc_json_file(a / "kich-ban" / "_log" / f"{me}_tron_goi.xong.json")
        ma_thoat = tg.get("exit") if isinstance(tg, dict) else None
        exit_0 = ma_thoat == 0 and not isinstance(ma_thoat, bool)
        me_dat = me_dat or (verify and exit_0)
        tg_ghi = "chưa xong" if ma_thoat is None else f"exit {ma_thoat}"
        phan.append(f"Bước A mẻ {me}: verify {'ĐẠT' if verify else 'chưa đạt'}, tron-goi {tg_ghi}, bàn giao "
                    f"{'xong' if _buoc_xong(tt, 'ban_giao') else 'chưa'}")
    info, dong_a, dong_b = _dong_kho_taovideo(uid, a, b, mt)
    if info is None:
        phan.append("Kho: không đọc được info.json")
    co_anh, anh = _doc_anh_chup(viec)
    if co_anh and anh is None:
        phan.append("Kho: ảnh chụp kho lúc tạo việc hỏng — không xác nhận được dòng mới")
    cu_a = anh["a"] if anh is not None else None
    cu_b = anh["b"] if anh is not None else None
    co_a = (not co_anh or anh is not None) and _co_dong_moi(dong_a, cu_a)
    co_b = (not co_anh or anh is not None) and _co_dong_moi(dong_b, cu_b)

    def ghi_kho(co: bool, dong: list[dict]) -> str:
        if co:
            return "đã ghi kho" if not co_anh else "đã ghi kho (dòng mới)"
        return "chưa có dòng mới trong kho" if co_anh and dong else "chưa ghi kho"
    phan.append(f"Bước A: Poster {ghi_kho(co_a, dong_a)}")
    n_mp4, n_do = _dem_mp4_moi(b / "output", moc)
    b_xong = n_mp4 >= 1 and n_do == 0
    phan.append(f"Bước B: {n_mp4} mp4 mới, {n_do} partial, {ghi_kho(co_b, dong_b)}")
    ket = "xong" if me_dat and co_a and co_b and b_xong else "chua"
    return ket, " · ".join(phan)[:TOM_TAT_DOI_SOAT_TOI_DA]


def _dau_ra_taovideo(ts: dict, viec: dict, mt: MoiTruong) -> str:
    return doi_soat_taovideo(ts, viec, mt)[0]


def mp3_adam_moi(p: Path, tu: datetime) -> frozenset[str]:
    """§7.5 trần voice GenMax: tên TƯƠNG ĐỐI (posix, từ thư mục dự án) của `voice/**/*_adam.mp3` có mtime ≥ `tu`.
    Bên gọi hợp các lần quét (tập đã từng thấy): file dời sang voice/_hong/ là tên mới nên số không giảm."""
    thu = Path(p) / "voice"
    if not thu.is_dir():
        return frozenset()
    moc = gio_vn(tu).timestamp()
    ra: set[str] = set()
    try:
        ds = list(thu.rglob("*_adam.mp3"))
    except OSError as e:
        log.warning("không quét được %s: %s", thu, e)
        return frozenset()
    for f in ds:
        try:
            if f.is_file() and f.stat().st_mtime >= moc:
                ra.add(f.relative_to(p).as_posix())
        except OSError as e:
            log.warning("không đọc được mtime %s: %s", f, e)
    return frozenset(ra)


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
    # B-L1 (docs/giao-dien-menu-trai.md §4.9): miễn phí, idempotent — dời video Loại sang _loai/ và trả về khi chấm lại.
    # Giữ "kho" (git fetch ghi ref remote trong .git, mutex D1) và "poster" (không chạy song song với đẩy/lên lịch).
    "poster_bo_loai": LoaiViec(
        ma="poster_bo_loai", ten="Gỡ video Loại khỏi folder đăng", dot=3, lan_chay="nhe", ton_tien=False,
        agent=None, tu_chay_lai=True, het_gio_s=10 * 60, tai_nguyen=frozenset({"poster", "kho"}),
        tham_so=_ts_mo_ta(_UID), kiem_tham_so=_ts_uid, tinh_khoa=lambda ts: str(ts["uid"]),
        trang_thai_dau=_cho_chay, dieu_kien_truoc=_dk_bo_loai, lap_buoc=_buoc_bo_loai,
        kiem_dau_ra=_dau_ra_bo_loai),
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
        # KHÔNG giữ "kho" (trưởng phòng chốt, FX-B2): điều kiện trước chỉ `git fetch` — ghi ref remote trong .git,
        # không đụng cây làm việc/index. Đụng khoá ref của git/kho.py khác (`.lock': File exists`) → 'ban' (vòng chạy
        # hoãn rồi thử lại). Giữ mutex kho sẽ chặn xu_ly_link_moi/douyin_uid/poster_bo_loai suốt phiên (≤30').
        tu_chay_lai=False, het_gio_s=30 * 60, tai_nguyen=frozenset({"poster"}),
        tham_so=_ts_mo_ta({"ten": "folder_id", "kieu": "folder_poster", "bat_buoc": True},
                          {"ten": "so_video_ngay", "kieu": "int", "bat_buoc": True, "min": POSTER_VIDEO_NGAY[0],
                           "max": POSTER_VIDEO_NGAY[1]}),
        kiem_tham_so=_ts_poster_len_lich, tinh_khoa=lambda ts: f"folder:{ts['folder_id']}",
        trang_thai_dau=_cho_duyet, dieu_kien_truoc=_dk_poster_len_lich, lap_buoc=_buoc_poster_len_lich,
        kiem_dau_ra=_dau_ra_khong_ro,
        bo_cong_cu=("Read", "Write", "Edit", "Glob", "Grep", "Bash"), cong_cu_cam=_CAM_POSTER,
        tran_usd_moi_luot=2.0),
    # ----- đợt 6 (D10, docs/sua-video.md §7.1): miễn phí, gắn dot=4 (phụ lục đợt 4) để KHÔNG nâng dot_bat -----
    # Tự chạy lại sau khi máy tắt: CÙNG id việc → bộ chuyển đổi đọc nhật ký _sua/<id>.json làm nốt/hoàn nguyên.
    # sua_video chỉ tạo qua POST /api/viec/sua-video/<uid>/<ma>/luu của Worker (sau ban-sua); api kiểm ban_sua.
    "sua_video": LoaiViec(
        ma="sua_video", ten="Sửa và dựng lại 1 video", dot=4, lan_chay="gpu", ton_tien=False, agent=None,
        tu_chay_lai=True, het_gio_s=20 * 60, tai_nguyen=frozenset(),
        tham_so=_ts_mo_ta(_UID, _DU_AN, {"ten": "ma_video", "kieu": "ma_video", "bat_buoc": True},
                          {"ten": "ban_sua", "kieu": "ban_sua", "bat_buoc": True}),
        kiem_tham_so=_ts_sua_video, tinh_khoa=lambda ts: str(ts["ma_video"]), trang_thai_dau=_cho_chay,
        dieu_kien_truoc=_dk_sua_video, lap_buoc=_buoc_sua_video, kiem_dau_ra=_dau_ra_sua_video),
    "hoan_tac_sua": LoaiViec(
        ma="hoan_tac_sua", ten="Dùng lại bản cũ (hoàn tác sửa video)", dot=4, lan_chay="gpu", ton_tien=False,
        agent=None, tu_chay_lai=True, het_gio_s=10 * 60, tai_nguyen=frozenset(),
        tham_so=_ts_mo_ta(_UID, _DU_AN, {"ten": "ma_video", "kieu": "ma_video", "bat_buoc": True},
                          {"ten": "viec_goc", "kieu": "viec", "bat_buoc": True}),
        kiem_tham_so=_ts_hoan_tac_sua, tinh_khoa=lambda ts: str(ts["ma_video"]), trang_thai_dau=_cho_chay,
        dieu_kien_truoc=_dk_sua_video, lap_buoc=_buoc_hoan_tac_sua, kiem_dau_ra=_dau_ra_hoan_tac_sua),
    # ----- đợt 5 (D11, B-4): phiên sống; 1 lời duyệt = 1 phiên; đối soát chỉ đọc file; KHÔNG tự chạy lại -----
    "taovideo": LoaiViec(
        ma="taovideo", ten="Làm video affiliate hoàn chỉnh", dot=5, lan_chay="gpu", ton_tien=True,
        agent="aff-taovideo", tu_chay_lai=False, het_gio_s=8 * 3600, tai_nguyen=frozenset({"kho"}),
        tham_so=_ts_mo_ta(_UID, {"ten": "du_an_a", "kieu": "du_an", "bat_buoc": True},
                          {"ten": "du_an_b", "kieu": "du_an_hoac_tu_tim", "bat_buoc": True,
                           "mac_dinh": TU_TIM_DU_AN_B},
                          {"ten": "wm", "kieu": "chon", "lua_chon": list(wm_cho_phep()), "bat_buoc": True},
                          {"ten": "gia", "kieu": "int", "min": GIA_TAOVIDEO[0], "max": GIA_TAOVIDEO[1],
                           "bat_buoc": False}),
        kiem_tham_so=_ts_taovideo, tinh_khoa=lambda ts: str(ts["uid"]), trang_thai_dau=_cho_duyet,
        dieu_kien_truoc=_dk_taovideo, lap_buoc=_buoc_taovideo, kiem_dau_ra=_dau_ra_taovideo,
        bo_cong_cu=BO_CONG_CU_TAOVIDEO, tran_usd_moi_luot=40.0, them_thu_muc=_them_thu_muc_taovideo),
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
    if loai.ma in LOAI_PHIEN_SONG:
        raise ThamSoLoi(f"loại {loai.ma} chạy phiên sống (lenh_claude_song), không bao giờ --resume")
    sid = _session_id(viec)
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


def _session_id(viec: dict) -> str:
    sid = viec.get("session_id")
    if not isinstance(sid, str) or not _RE_SESSION.fullmatch(sid):
        raise ThamSoLoi("việc thiếu session_id UUID")
    return sid


def lenh_claude_song(loai: LoaiViec, viec: dict, mt: MoiTruong, tran_usd: float) -> list[str]:
    """§7.2 (D11): MỘT tiến trình `claude -p` stream-json hai chiều, stdin giữ mở suốt việc.
    Luôn `--session-id viec['session_id']` (vòng chạy đặt uuid4 MỚI trước mỗi lần sinh), KHÔNG BAO GIỜ `--resume`.
    `--strict-mcp-config` tắt MCP của người dùng (R-05 P1-1). `tran_usd` = chốt phụ `--max-budget-usd`."""
    if loai.ma not in LOAI_PHIEN_SONG or not loai.agent or not loai.bo_cong_cu:
        raise ThamSoLoi(f"loại {loai.ma} không chạy phiên sống")
    sid = _session_id(viec)
    if (not isinstance(tran_usd, (int, float)) or isinstance(tran_usd, bool) or not math.isfinite(tran_usd)
            or tran_usd <= 0):
        raise ThamSoLoi("tran_usd phải là số dương")
    them: list[str] = []
    for d in loai.them_thu_muc(viec.get("tham_so") or {}, mt):
        them += ["--add-dir", d]
    return [str(mt.claude_exe), "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json", "--verbose",
            "--agent", loai.agent,
            "--strict-mcp-config",
            "--tools", ",".join(loai.bo_cong_cu),
            "--permission-mode", "dontAsk",
            "--allowedTools", *loai.bo_cong_cu,
            "--disallowedTools", *cong_cu_cam_chung(), *loai.cong_cu_cam,
            "--max-budget-usd", f"{tran_usd:g}",
            "--session-id", sid,
            *them]


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
