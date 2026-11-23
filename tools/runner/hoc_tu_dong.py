"""Script đo của "Học tự động mỗi ngày" (D15; đặc tả docs/hoc-tu-dong.md §3.3, §3.5, §3.6, §4.4, §6.1).

Chạy (cwd = thư mục chứa gói `runner`, §3.10):
    python -B -m runner.hoc_tu_dong --ngay YYYY-MM-DD --hoc-db <hoc.db> --poster-db <v2_data.db>
        --runner-db <runner.db> --repo <repo kho> (--viec-id <j…> | --chi-doc) --bat-ngay N --hieu-luc-toi-da N

- Việc runner (`--viec-id`): `KhoHoc.mo()` → `bat_dau_lan` (False → `da_hoc`) → đo 3 nguồn → `ap_ket_qua_ngay`
  → `ghi_tuan_thu` → `ket_thuc_lan`. Lỗi bất ngờ → `ket_thuc_lan(..., "loi", "loi_bat_ngo")`, thoát 1.
- `--chi-doc`: `KhoHoc(chi_doc=True)`, KHÔNG `mo()`, không ghi gì; in kết quả dự kiến (`du_kien_ngay`).
- Mọi DB nguồn mở `mode=ro` (không bao giờ tạo file); `quet_view.kiem_duong_dan_thu` chạy TRƯỚC mọi lần mở.
- stdout: đúng 1 dòng JSON ASCII `{"trang_thai","ly_do","so_thay_doi"}` (+ `chi_doc`, `du_kien` khi `--chi-doc`).
  Mã thoát 0 = xong | tu_dung | da_hoc; 1 = loi.

Mọi chữ đọc từ DB Poster, runner.db, captions.txt, info.json là KHÔNG TIN CẬY (§6.1): chỉ đi qua
`hoc_danh_muc.chuan_hoa_caption/than_caption/muc_khop_caption/dac_trung_caption` hoặc so chuỗi cố định của danh
mục, rồi ra thành số đếm / mã enum. Không chữ nào của chúng vào `do_luong`, `so_lieu`, stdout hay log.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from . import hoc_danh_muc as dm
from .kho_hoc import DoLuong, KhoHoc
from .kieu import MUI_GIO_VN, ThamSoLoi, gio_vn
from .quet_view import doc_ket_qua, kiem_duong_dan_thu

log = logging.getLogger("kho_runner.hoc_tu_dong")

GIAY_MOT_NGAY = 86400
CUA_SO_TRUNG_VI_NGAY = 7          # poster_thieu: so với trung vị số lần đo thật của 7 ngày trước
PT_TOI_THIEU_NGUON = 50           # poster_thieu / poster_lech_noi: dưới 50% → tự dừng (§3.6, §4.4)
DONG_JSON_TOI_DA = 4000           # dòng JSON dài hơn (trong tom_tat/loi của việc quét) → bỏ, không parse
SO_VIEC_TOI_DA = 200_000          # trần số dòng runner.db đọc (chặn DB bị phình bất thường)
TRANG_THAI_VIEC_DONG = ("xong", "loi")
LOAI_QUET_VIEW = "quet_view_hang_ngay"
# trạng thái việc runner → quet_hom_nay.trang_thai của BaoCao (§3.8)
TRANG_THAI_QUET: dict[str, str] = {"xong": "ok", "loi": "loi", "cho": "cho", "dang_chay": "dang_chay", "huy": "huy",
                                   "can_tra_loi": "cho", "cho_duyet": "cho"}
# trạng thái file <du_lieu>/quet_view/<ngay>.json phải khớp trạng thái việc mới được dùng làm dự phòng
_FILE_QUET_KHOP: dict[str, str] = {"xong": "ok", "loi": "loi"}
_LY_DO_QUET_XONG = frozenset({"ok", "da_quet"})          # việc quét thoát 0 chỉ với 2 mã này (quet_view.chay)
# trường chữ của việc mà khoá vận hành so (bảng §3.6): mặc định `loi`; riêng thiếu đầu ra so `ket_qua.lo_ngai`
TRUONG_VAN_HANH: dict[str, str] = {"pt_thieu_dau_ra": "lo_ngai"}
SUA_TAY: dict[str, str] = {"trang_thai": "chua_co_nguon"}
TRANG_THAI_POSTER: dict[str, str] = {"": "ok", "poster_cu": "cu", "poster_thieu": "thieu",
                                     "poster_lech_noi": "lech", "poster_khong_mo_duoc": "loi",
                                     "repo_khong_doc_duoc": "loi"}

# Theo dõi tuân thủ (§3.6): caption của SP đã nhận gợi ý có "làm theo" không. Con số PHẢI đúng con số trong mẫu câu
# `hoc_danh_muc.DANH_MUC_HOC[khoa].goi_y[huong]` (test khoá điều này):
# - ("it_nhat", n): tỉ lệ caption có đặc trưng ≥ n%;  ("toi_da", n): ≤ n%;  ("duoi", 50): < 50% ("phần lớn" ngược lại).
NGUONG_TUAN_THU: dict[tuple[str, str], tuple[str, int]] = {
    ("cap_co_so", "tang"): ("it_nhat", 40), ("cap_co_so", "giam"): ("toi_da", 20),
    ("cap_ngan", "tang"): ("it_nhat", 40), ("cap_ngan", "giam"): ("duoi", 50),
    ("cap_nhac_usp", "tang"): ("it_nhat", 40), ("cap_nhac_usp", "giam"): ("toi_da", 20),
    ("cap_goi_ban", "tang"): ("it_nhat", 30), ("cap_goi_ban", "giam"): ("toi_da", 15),
    ("cap_menh_lenh", "tang"): ("it_nhat", 30), ("cap_menh_lenh", "giam"): ("toi_da", 15),
    ("cap_cau_hoi", "tang"): ("it_nhat", 30), ("cap_cau_hoi", "giam"): ("toi_da", 15),
    ("cap_emoji", "tang"): ("it_nhat", 40), ("cap_emoji", "giam"): ("toi_da", 20),
}

_RE_NGAY = re.compile(r"^\d{4}-\d{2}-\d{2}\Z", re.ASCII)
_RE_UID = re.compile(r"^\d{19}\Z", re.ASCII)
_RE_VIEC_ID = re.compile(r"^j\d{14}[a-z0-9]{4}\Z", re.ASCII)

# Biên lùi khi đọc video_view_snapshots (HT-B4 mục 4 — bảng phình triệu dòng sau vài tháng, không đọc hết):
# - video được đo phải đăng trong cua_so_dang_ngay (60) ngày tính tới `ngay` → mọi snapshot của nó có collected_at
#   ≥ ngay − 60 (snapshot không thể có trước ngày đăng);
# - + tuổi đo tối đa (tuoi_video_ngay[1] = 7) và + cửa sổ trung vị poster_thieu (CUA_SO_TRUNG_VI_NGAY = 7): đệm để
#   `lan_do_that` của các ngày trong cửa sổ trung vị vẫn thấy snapshot LIỀN TRƯỚC của video cũ (bản chép số cũ không
#   bị đếm thành lần đo mới). Video cũ không được chụp suốt > 74 ngày rồi chụp lại số y hệt mới bị đếm lệch — chấp nhận.
# Tổng = 60 + 7 + 7 = 74 ngày; trên: collected_at ≤ ngay (học bù không đọc dữ liệu tương lai).
SNAP_LUI_NGAY = (int(dm.NGUONG["cua_so_dang_ngay"]) + cast("tuple[int, int]", dm.NGUONG["tuoi_video_ngay"])[1]
                 + CUA_SO_TRUNG_VI_NGAY)
_SQL_SNAP = ("SELECT video_id, collected_at, product_id, account_id, view_count, like_count, comment_count, "
             "posted_ts, scraped_at FROM video_view_snapshots WHERE collected_at >= ? AND collected_at <= ?")
# chỉ chạy khi biên rỗng (HT-B4b mục 3); so chuỗi ≤ ngày học loại cả ngày tương lai lẫn chuỗi hỏng bắt đầu bằng chữ
_SQL_SNAP_MOI_NHAT = "SELECT MAX(collected_at) FROM video_view_snapshots WHERE collected_at <= ?"
# queue: chỉ dòng của video còn snapshot trong biên (chỉ chúng mới nối caption được); so dạng TEXT như phía Python
_SQL_QUEUE = ("SELECT video_id, product_id, caption FROM queue WHERE video_id IS NOT NULL AND video_id <> '' "
              "AND CAST(video_id AS TEXT) IN (SELECT CAST(video_id AS TEXT) FROM video_view_snapshots "
              "WHERE collected_at >= ? AND collected_at <= ?)")


# ---------------------------------------------------------------------------------------------------------------
# Tiện ích chung
# ---------------------------------------------------------------------------------------------------------------
def ty_le_pt(k: int, n: int) -> int:
    """% LÀM TRÒN XUỐNG (100*k//n): 79,5% không thành 80 (ngưỡng Q7). n = 0 → 0."""
    return 100 * k // n if n > 0 else 0


def _uri_ro(p: Path) -> str:
    return f"file:{quote(Path(p).resolve().as_posix(), safe='/:')}?mode=ro"


class _ChuHong:
    """Giá trị thay cho một ô TEXT không phải UTF-8. Không phải `str` (mọi kiểm `isinstance(x, str)` loại nó) và
    không mang byte nào của dữ liệu gốc, nên chữ hỏng không thể lọt ra stdout/log/so_lieu."""
    __slots__ = ()

    def __repr__(self) -> str:
        return "<chu_hong>"


CHU_HONG = _ChuHong()


def _giai_ma_text(b: bytes) -> str | _ChuHong:
    """text_factory: UTF-8 chặt; byte không giải mã được → CHU_HONG (thay vì OperationalError làm dừng cả nguồn)."""
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return CHU_HONG


def _co_chu_hong(dong: Iterable[Any]) -> bool:
    return any(x is CHU_HONG for x in dong)


def _mo_ro(p: Path) -> sqlite3.Connection:
    """Kết nối CHỈ ĐỌC (`mode=ro` không bao giờ tạo file; thiếu file → sqlite3.OperationalError). Ô TEXT không phải
    UTF-8 đọc thành CHU_HONG (người gọi đếm/bỏ dòng đó)."""
    c = sqlite3.connect(_uri_ro(p), uri=True, timeout=30)
    c.text_factory = _giai_ma_text
    c.execute("PRAGMA query_only=ON")
    return c


def _ngay_hop_le(s: Any) -> date | None:
    if not isinstance(s, str) or not _RE_NGAY.fullmatch(s):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _moc_trua(ngay: date) -> float:
    """12:00 giờ VN của một ngày (epoch giây)."""
    return datetime(ngay.year, ngay.month, ngay.day, 12, tzinfo=MUI_GIO_VN).timestamp()


def _la_so_duong(x: Any) -> bool:
    return type(x) in (int, float) and math.isfinite(x) and x > 0


def kiem_duong_dan(hoc_db: Path, poster_db: Path, runner_db: Path, repo: Path) -> None:
    """Chặn chạm production khi chạy thử/test (§3.6): `hoc_db` không nằm ở thư mục runner thật mà nguồn lại là
    đường dẫn thật → RuntimeError. Gọi TRƯỚC mọi lần mở file."""
    kiem_duong_dan_thu(Path(hoc_db).parent, Path(poster_db), Path(runner_db), Path(repo) / "data")


# ---------------------------------------------------------------------------------------------------------------
# Nguồn poster_view: lấy số chặt (§3.6 bước 1–2)
# ---------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Snap:
    """Một dòng video_view_snapshots đã kiểm: ngày thu, thời điểm đo (epoch s), (view, like, comment)."""
    ngay: str
    t: float
    so: tuple


def _thoi_diem_do(collected_at: str, scraped_at: Any) -> float:
    """`scraped_at` đọc được (ISO, không múi giờ = giờ máy = giờ VN) → dùng; ngược lại `collected_at` 12:00 VN."""
    if isinstance(scraped_at, str) and 10 <= len(scraped_at.strip()) <= 40:
        try:
            return gio_vn(datetime.fromisoformat(scraped_at.strip())).timestamp()
        except ValueError:
            log.debug("scraped_at không đọc được — dùng collected_at 12:00")     # nhánh dự phòng theo đặc tả
    return _moc_trua(date.fromisoformat(collected_at))


def lan_do_that(snaps: list[Snap]) -> list[Snap]:
    """Snapshot đầu tiên + mọi snapshot có (view, like, comment) khác snapshot LIỀN TRƯỚC. Bản chép số cũ của
    `ghi_view_poster.py` (S3, K16, K17) bị gộp vào lần đo thật trước đó."""
    ra: list[Snap] = []
    truoc = None
    for s in snaps:
        if truoc is None or s.so != truoc:
            ra.append(s)
        truoc = s.so
    return ra


def view_chuan(snaps: list[Snap], posted_ts: Any, ngay: date) -> tuple[str, int | None]:
    """('ok', view chuẩn) hoặc (mã loại, None). `snaps` đã xếp theo ngày thu, chỉ gồm ngày ≤ `ngay`.

    View chuẩn = view của lần đo thật CUỐI CÙNG có tuổi ≤ 7 (phải ≥ 3); video phải đăng trong 60 ngày tính tới
    `ngay` và snapshot mới nhất có tuổi ≥ 7 (§3.6 bước 2, NGUONG['tuoi_video_ngay'])."""
    lo, hi = cast("tuple[int, int]", dm.NGUONG["tuoi_video_ngay"])
    if not snaps or not _la_so_duong(posted_ts):
        return "bo_thieu_posted_ts", None
    if (_moc_trua(ngay) - posted_ts) / GIAY_MOT_NGAY > dm.NGUONG["cua_so_dang_ngay"]:
        return "bo_qua_60_ngay", None

    def tuoi(s: Snap) -> float:
        return (s.t - posted_ts) / GIAY_MOT_NGAY

    if tuoi(snaps[-1]) < hi:
        return "bo_chua_du_7_ngay", None
    ok = [s for s in lan_do_that(snaps) if tuoi(s) <= hi]
    if not ok or tuoi(ok[-1]) < lo:
        return "bo_khong_do_3_7", None
    v = ok[-1].so[0]
    if type(v) is not int or v < 0:
        return "bo_so_lieu_hong", None
    return "ok", v


# ---------------------------------------------------------------------------------------------------------------
# Repo kho: info.json, captions.txt (chỉ so khớp trong bộ nhớ, không lưu nội dung)
# ---------------------------------------------------------------------------------------------------------------
class KhoRepo:
    """Đọc `<repo>/data/<UID>/{info.json, captions.txt}` có cache. UID phải khớp ^\\d{19}$ TRƯỚC khi dựng đường dẫn
    (product_id từ DB Poster là chuỗi không tin cậy: '../../x' không bao giờ thành đường dẫn)."""

    def __init__(self, repo: Path) -> None:
        self.data = Path(repo) / "data"
        self._co: dict[str, bool] = {}
        self._cap: dict[str, tuple[str, ...]] = {}
        self._usp: dict[str, tuple[str, ...]] = {}
        self.so_file_loi = 0

    def doc_duoc(self) -> bool:
        return self.data.is_dir()

    def co(self, uid: Any) -> bool:
        if not isinstance(uid, str) or not _RE_UID.fullmatch(uid):
            return False
        if uid not in self._co:
            self._co[uid] = (self.data / uid / "info.json").is_file()
        return self._co[uid]

    def _doc(self, uid: str, ten: str) -> str | None:
        p = self.data / uid / ten
        try:
            return p.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError) as e:
            self.so_file_loi += 1
            log.warning("không đọc được %s của UID %s (%s) — coi như không có", ten, uid, type(e).__name__)
            return None

    def captions(self, uid: str) -> tuple[str, ...]:
        if uid not in self._cap:
            vb = self._doc(uid, "captions.txt") if self.co(uid) else None
            self._cap[uid] = tuple(d for d in (vb or "").splitlines() if d.strip())
        return self._cap[uid]

    def tu_khoa(self, uid: str) -> tuple[str, ...]:
        if uid not in self._usp:
            ra: tuple[str, ...] = ()
            vb = self._doc(uid, "info.json") if self.co(uid) else None
            if vb is not None:
                try:
                    info = json.loads(vb)
                except (ValueError, RecursionError) as e:
                    self.so_file_loi += 1
                    log.warning("info.json của UID %s hỏng (%s) — không có từ khoá USP", uid, type(e).__name__)
                    info = None
                usp = info.get("usp") if isinstance(info, dict) else None
                tk = usp.get("tu_khoa") if isinstance(usp, dict) else None
                if isinstance(tk, list):
                    ra = tuple(x for x in tk if isinstance(x, str))
            self._usp[uid] = ra
        return self._usp[uid]


# ---------------------------------------------------------------------------------------------------------------
# Nguồn poster_view: đo đặc trưng caption (§3.6 bước 3–8)
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class _Caption:
    """Một caption (theo THÂN) trong một nhóm (UID, tài khoản): view chuẩn các video dùng nó + đặc trưng."""
    views: list[int] = field(default_factory=list)
    dac_trung: frozenset[str] = frozenset()
    goc: str | None = None              # caption gốc nhỏ nhất (tất định) — chỉ để tính đặc trưng, không lưu


def _lift_pt(d: float) -> int:
    x = round((math.exp(min(d, 30.0)) - 1) * 100)
    return max(-100, min(int(x), dm.SO_TOI_DA))


def _do_mot_khoa(khoa: str, nhom: Mapping[tuple[str, Any], Mapping[str, _Caption]]) -> DoLuong:
    can = cast(int, dm.NGUONG["caption_moi_ben_toi_thieu"])
    d_nhom: dict[str, list[float]] = defaultdict(list)
    tk: dict[str, Counter] = defaultdict(Counter)
    for (uid, _tai_khoan), caps in nhom.items():
        # đơn vị = caption KHÁC NHAU (theo thân); view của caption = trung vị view chuẩn các video dùng nó
        co = [math.log1p(statistics.median(c.views)) for c in caps.values() if khoa in c.dac_trung]
        khong = [math.log1p(statistics.median(c.views)) for c in caps.values() if khoa not in c.dac_trung]
        if len(co) < can or len(khong) < can:
            continue
        d_nhom[uid].append(statistics.median(co) - statistics.median(khong))
        tk[uid].update(so_nhom=1, so_caption=len(co) + len(khong), so_video=sum(len(c.views) for c in caps.values()))
    d_uid = {u: statistics.median(ds) for u, ds in d_nhom.items()}        # gộp các nhóm (UID, tài khoản) về UID
    n = len(d_uid)
    lift = _lift_pt(statistics.median(d_uid.values())) if n else 0
    huong = "tang" if lift > 0 else "giam"
    cung = sum(1 for d in d_uid.values() if (d > 0 if huong == "tang" else d < 0))     # d = 0 không cùng chiều
    muc_uid: list[dict[str, Any]] = [{"uid": u, "so_nhom": tk[u]["so_nhom"], "so_caption": tk[u]["so_caption"],
                                      "so_video": tk[u]["so_video"], "lift_pt": _lift_pt(d)} for u, d in d_uid.items()]
    ds_uid = sorted(muc_uid, key=lambda x: (-x["so_caption"], x["uid"]))[:30]
    dl: dict[str, Any] = {
        "khoa": khoa, "huong": huong, "nguon": "poster_view", "so_uid": n,
        "so_nhom": sum(t["so_nhom"] for t in tk.values()), "so_video": sum(t["so_video"] for t in tk.values()),
        "so_caption": sum(t["so_caption"] for t in tk.values()), "lift_pt": lift, "nhat_quan_pt": ty_le_pt(cung, n),
        "ds_uid": ds_uid}
    dat, giu, thieu = dm.xet_nguong(dl)
    dl.update(dat=dat, giu=giu, thieu=thieu)
    return dl  # type: ignore[return-value]


def tinh_do_luong_caption(nhom: Mapping[tuple[str, Any], Mapping[str, _Caption]]) -> list[DoLuong]:
    """Thuần: 7 khoá caption theo thứ tự danh mục (luôn đủ 7, khoá chưa có nhóm nào → so_uid 0)."""
    return [_do_mot_khoa(k, nhom) for k, d in dm.DANH_MUC_HOC.items() if d.nguon == "poster_view"]


def _so_lieu_poster_rong() -> dict[str, Any]:
    return {"trang_thai": "loi", "ly_do": "", "ngay_moi_nhat": None, "so_ngay_cu": None, "so_video_doc": 0,
            "so_video_hop_le": 0, "so_video_dung": 0, "so_uid": 0, "so_nhom": 0, "so_lan_do_ngay": 0,
            "trung_vi_lan_do_7_ngay": 0, "bo_caption_ngoai_kho": 0, "bo_mo_ho": 0, "bo_khong_noi": 0,
            "bo_ngoai_kho": 0, "bo_thieu_posted_ts": 0, "bo_qua_60_ngay": 0, "bo_chua_du_7_ngay": 0,
            "bo_khong_do_3_7": 0, "bo_so_lieu_hong": 0, "bo_dong_hong": 0, "so_file_loi": 0}


def _dung(so: dict[str, Any], ly_do: str) -> dict[str, Any]:
    so["ly_do"] = ly_do
    so["trang_thai"] = TRANG_THAI_POSTER[ly_do]
    return so


def _doc_poster(poster_db: Path, ngay: date) -> tuple[list[tuple], list[tuple]]:
    """(snapshot có collected_at trong [ngay − SNAP_LUI_NGAY, ngay], dòng queue của các video đó). Lọc trong SQL,
    tham số hoá. Dòng có collected_at hỏng/NULL nằm ngoài so sánh chuỗi → không đọc (trước đây đếm bo_dong_hong)."""
    bien = ((ngay - timedelta(days=SNAP_LUI_NGAY)).isoformat(), ngay.isoformat())
    with closing(_mo_ro(poster_db)) as c:
        return c.execute(_SQL_SNAP, bien).fetchall(), c.execute(_SQL_QUEUE, bien).fetchall()


def _ngay_snap_moi_nhat(poster_db: Path, ngay: date) -> str | None:
    """HT-B4b mục 3: biên SNAP_LUI_NGAY không còn snapshot hợp lệ → ngày snapshot mới nhất ≤ `ngay` (chỉ đọc, tham
    số hoá) để web vẫn báo "Nguồn view đã cũ N ngày". Chuỗi hỏng/không đúng dạng ngày → None. Lỗi SQLite → log, None
    (nguồn đã tự dừng poster_cu; chỉ mất con số tuổi dữ liệu)."""
    try:
        with closing(_mo_ro(poster_db)) as c:
            r = c.execute(_SQL_SNAP_MOI_NHAT, (ngay.isoformat(),)).fetchone()
    except sqlite3.Error as e:
        log.warning("không đọc được ngày snapshot mới nhất của DB Poster (%s)", type(e).__name__)
        return None
    d = r[0] if r else None
    return d if _ngay_hop_le(d) is not None else None


def do_poster(poster_db: Path, repo: Path, ngay: date) -> tuple[dict, list[DoLuong]]:
    """(so_lieu.nguon.poster_view, 7 DoLuong caption). `ly_do` ≠ '' → nguồn tự dừng, danh sách DoLuong rỗng.
    Chỉ dùng snapshot có `collected_at` ≤ `ngay`. Lỗi SQLite (không mở được, thiếu bảng/cột) → poster_khong_mo_duoc;
    lỗi khác là lỗi bất ngờ, ném tiếp cho `chay`."""
    so = _so_lieu_poster_rong()
    try:
        snaps_tho, queue_tho = _doc_poster(poster_db, ngay)
    except sqlite3.Error as e:
        log.warning("không đọc được DB Poster (%s) — tự dừng nguồn poster_view", type(e).__name__)
        return _dung(so, "poster_khong_mo_duoc"), []
    ngay_s = ngay.isoformat()

    # 1. gom snapshot theo video (chỉ ngày ≤ ngay học)
    theo_video: dict[str, list[tuple]] = defaultdict(list)
    for r in snaps_tho:
        vid, d = r[0], r[1]
        if vid is None or _ngay_hop_le(d) is None or _co_chu_hong(r):
            so["bo_dong_hong"] += 1
            continue
        if d <= ngay_s:
            theo_video[str(vid)].append(r)
    so["so_video_doc"] = len(theo_video)
    cac_ngay = sorted({r[1] for ds in theo_video.values() for r in ds})
    moi_nhat = cac_ngay[-1] if cac_ngay else _ngay_snap_moi_nhat(poster_db, ngay)
    so["ngay_moi_nhat"] = moi_nhat
    so["so_ngay_cu"] = (ngay - date.fromisoformat(moi_nhat)).days if moi_nhat else None
    if not cac_ngay or cac_ngay[-1] < ngay_s:
        return _dung(so, "poster_cu"), []

    video: dict[str, tuple[tuple, list[Snap]]] = {}
    for vid, ds in theo_video.items():
        ds.sort(key=lambda r: r[1])
        snaps = [Snap(r[1], _thoi_diem_do(r[1], r[8]), (r[4], r[5], r[6])) for r in ds]
        video[vid] = (ds[-1], snaps)

    # 2. dữ liệu mới của ngày: số lần đo thật hôm nay so với trung vị 7 ngày trước (ngày có dữ liệu)
    lan_do = Counter(s.ngay for _, snaps in video.values() for s in lan_do_that(snaps))
    truoc = {(ngay - timedelta(days=i)).isoformat() for i in range(1, CUA_SO_TRUNG_VI_NGAY + 1)}
    mau = [lan_do.get(d, 0) for d in cac_ngay if d in truoc]
    so["so_lan_do_ngay"] = lan_do.get(ngay_s, 0)
    trung_vi = statistics.median(mau) if mau else 0
    so["trung_vi_lan_do_7_ngay"] = int(trung_vi)
    if mau and so["so_lan_do_ngay"] * 100 < PT_TOI_THIEU_NGUON * trung_vi:
        return _dung(so, "poster_thieu"), []

    # 3. video hợp lệ (luật lấy số chặt)
    hop_le: list[tuple[str, str, Any, int]] = []           # (video_id, product_id, account_id, view chuẩn)
    for vid, (cuoi, snaps) in video.items():
        ma, view = view_chuan(snaps, cuoi[7], ngay)
        if view is None:                                   # view_chuan: None ⇔ ma ≠ 'ok'
            so[ma] += 1
            continue
        hop_le.append((vid, str(cuoi[2]) if cuoi[2] is not None else "", cuoi[3], view))
    so["so_video_hop_le"] = len(hop_le)

    # 4. nối (video_id, product_id) → caption; khớp captions.txt của chính UID (L1–L4)
    kho = KhoRepo(repo)
    if not kho.doc_duoc():
        return _dung(so, "repo_khong_doc_duoc"), []
    q: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)    # (vid, pid) → {caption chuẩn hoá: caption gốc}
    for r in queue_tho:
        if _co_chu_hong(r):
            so["bo_dong_hong"] += 1
            continue
        vid, pid, cap = r
        goc = cap if isinstance(cap, str) else ""
        k = dm.chuan_hoa_caption(goc)
        cu = q[(str(vid), str(pid))].get(k)
        if cu is None or goc < cu:
            q[(str(vid), str(pid))][k] = goc
    nhom: dict[tuple[str, Any], dict[str, _Caption]] = defaultdict(dict)
    uid_dung: set[str] = set()
    for vid, pid, tai_khoan, view in hop_le:
        if not kho.co(pid):
            so["bo_ngoai_kho"] += 1
            continue
        caps = q.get((vid, pid))
        if not caps:
            so["bo_khong_noi"] += 1
            continue
        if len(caps) > 1:
            so["bo_mo_ho"] += 1
            continue
        goc = next(iter(caps.values()))
        if dm.muc_khop_caption(goc, kho.captions(pid)) == "L5":
            so["bo_caption_ngoai_kho"] += 1
            continue
        than = dm.than_caption(goc)
        c = nhom[(pid, tai_khoan)].setdefault(than, _Caption())
        c.views.append(view)
        if c.goc is None or goc < c.goc:
            c.goc = goc
        uid_dung.add(pid)
        so["so_video_dung"] += 1
    so["so_file_loi"] = kho.so_file_loi
    so["so_uid"] = len(uid_dung)
    so["so_nhom"] = len(nhom)
    if so["so_video_hop_le"] and so["so_video_dung"] * 100 < PT_TOI_THIEU_NGUON * so["so_video_hop_le"]:
        return _dung(so, "poster_lech_noi"), []

    # 5. đặc trưng tính trên caption đã đăng; đo 7 khoá
    for (uid, _tk), cap_nhom in nhom.items():
        tu_khoa = kho.tu_khoa(uid)
        for cap in cap_nhom.values():
            cap.dac_trung = dm.dac_trung_caption(cap.goc or "", tu_khoa)
            cap.goc = None                                 # không giữ chữ lâu hơn cần
    so["so_file_loi"] = kho.so_file_loi
    return _dung(so, ""), tinh_do_luong_caption(nhom)


# ---------------------------------------------------------------------------------------------------------------
# Nguồn van_hanh (§3.6 bảng, §4.1b)
# ---------------------------------------------------------------------------------------------------------------
def _lo_ngai(ket_qua: Any) -> str | None:
    if not isinstance(ket_qua, str):
        return None
    try:
        kq = json.loads(ket_qua)
    except (ValueError, RecursionError):
        return None
    ln = kq.get("lo_ngai") if isinstance(kq, dict) else None
    return ln if isinstance(ln, str) else None


def phan_loai_viec(loai: Any, trang_thai: Any, loi: Any, ket_qua: Any) -> frozenset[str]:
    """Các khoá vận hành mà một việc ĐÃ KẾT THÚC khớp — so chuỗi cố định của danh mục (neo đầu / so nguyên câu)."""
    if trang_thai not in TRANG_THAI_VIEC_DONG:
        return frozenset()
    khop = set()
    for khoa, loai_khoa in dm.LOAI_VIEC_VAN_HANH.items():
        if loai_khoa != loai:
            continue
        chu = _lo_ngai(ket_qua) if TRUONG_VAN_HANH.get(khoa) == "lo_ngai" else loi
        if isinstance(chu, str) and dm.DANH_MUC_HOC[khoa].ham(chu, ()):
            khop.add(khoa)
    return frozenset(khop)


def khoang_can_doc(ngay: date, ngay_bat: Iterable[date] = ()) -> list[tuple[date, date]]:
    """Các khoảng ngày (đóng hai đầu) phải đọc từ runner.db, khoảng của `ngay` đứng ĐẦU (ưu tiên khi chạm trần):
    - cửa sổ đo [ngay − (cs−1), ngay];
    - với mỗi ngày bật của bài vận hành (theo dõi tuân thủ `lan_truoc`): [bat − cs, bat − 1].
    Khoảng chồng/kề nhau được gộp; phần sau `ngay` bị cắt."""
    cs = dm.NGUONG_VAN_HANH["cua_so_ngay"]
    chinh = (ngay - timedelta(days=cs - 1), ngay)
    phu = sorted({(b - timedelta(days=cs), min(b - timedelta(days=1), ngay)) for b in ngay_bat})
    gop: list[list[date]] = []
    for tu, den in sorted([chinh, *phu]):
        if tu > den:
            continue
        if gop and tu <= gop[-1][1] + timedelta(days=1):
            gop[-1][1] = max(gop[-1][1], den)
        else:
            gop.append([tu, den])
    # khoảng chứa `ngay` trước, còn lại từ mới tới cũ
    return sorted(((tu, den) for tu, den in gop), key=lambda k: (not (k[0] <= ngay <= k[1]), -k[1].toordinal()))


def _doc_viec(runner_db: Path, ngay: date, ngay_bat: Iterable[date] = ()) -> tuple[list[dict], bool]:
    """(việc tạo trong `khoang_can_doc` (giờ VN theo tao_luc) → [{loai (chỉ loại vận hành, khác → ''), ngay,
    trang_thai, khop}], bi_cat). Lọc khoảng ngày ngay trong SQL, mỗi khoảng xếp MỚI → CŨ; tổng số dòng chặn bởi
    SO_VIEC_TOI_DA — chạm trần thì bỏ phần CŨ NHẤT và báo bi_cat=True. Không giữ chữ nào của `loi`/`ket_qua`."""
    loai_vh = set(dm.LOAI_VIEC_VAN_HANH.values())
    ra: list[dict] = []
    con_lai = SO_VIEC_TOI_DA
    bi_cat = False
    with closing(_mo_ro(runner_db)) as c:
        for tu, den in khoang_can_doc(ngay, ngay_bat):
            bien = (tu.isoformat(), (den + timedelta(days=1)).isoformat())
            if con_lai <= 0:
                # hết trần đúng lúc: chỉ báo bị cắt khi khoảng còn lại THẬT có dòng (HT-B4 mục 5)
                if c.execute("SELECT 1 FROM viec WHERE tao_luc >= ? AND tao_luc < ? LIMIT 1", bien).fetchone():
                    bi_cat = True
                    break
                continue
            dong = c.execute("SELECT loai, tao_luc, trang_thai, loi, ket_qua FROM viec "
                             "WHERE tao_luc >= ? AND tao_luc < ? ORDER BY tao_luc DESC, rowid DESC LIMIT ?",
                             (*bien, con_lai + 1)).fetchall()
            if len(dong) > con_lai:
                bi_cat = True
                dong = dong[:con_lai]
            con_lai -= len(dong)
            for loai, tao_luc, tt, loi, kq in dong:
                d = _ngay_hop_le(tao_luc[:10]) if isinstance(tao_luc, str) else None
                if d is None or not _trong(d, tu, den):
                    continue
                la_vh = isinstance(loai, str) and loai in loai_vh
                ra.append({"loai": loai if la_vh else "", "ngay": d,
                           "trang_thai": tt if tt in TRANG_THAI_QUET else "",
                           "khop": phan_loai_viec(loai, tt, loi, kq) if la_vh else frozenset()})
    if bi_cat:
        log.warning("runner.db: số việc cần đọc vượt trần %d — bỏ phần cũ nhất, so_lieu.van_hanh.bi_cat=true",
                    SO_VIEC_TOI_DA)
    return ra, bi_cat


def _trong(d: date, tu: date, den: date) -> bool:
    return tu <= d <= den


def _ngay_bat(bat_luc: Any) -> date | None:
    """Ngày VN của `bat_luc` (ISO) của bài học; không đọc được → None."""
    if not isinstance(bat_luc, str):
        return None
    try:
        return gio_vn(datetime.fromisoformat(bat_luc)).date()
    except ValueError:
        return None


def ngay_bat_van_hanh(hoc_db: Path) -> list[date]:
    """Ngày bật của mọi bài học nguồn van_hanh trong hoc.db (mở `mode=ro`) — để biết khoảng runner.db mà
    `tuan_thu` cần (`lan_truoc`). Chưa có file → []. Lỗi SQLite ném tiếp cho người gọi."""
    db = Path(hoc_db)
    if not db.is_file():
        return []
    with closing(_mo_ro(db)) as c:
        rows = c.execute("SELECT bat_luc FROM bai_hoc WHERE nguon='van_hanh'").fetchall()
    return sorted({d for (b,) in rows if (d := _ngay_bat(b)) is not None})


def do_van_hanh(runner_db: Path, ngay: date, ngay_bat: Iterable[date] = ()
                ) -> tuple[dict, list[DoLuong], list[dict] | None]:
    """(so_lieu.nguon.van_hanh, 5 DoLuong vận hành, danh sách việc đã phân loại cho theo dõi tuân thủ).
    `ngay_bat` = ngày bật các bài vận hành (đọc thêm 14 ngày trước mỗi ngày cho `tuan_thu`).
    Không mở được runner.db → ly_do runner_db_khong_mo_duoc, DoLuong rỗng, danh sách việc None."""
    try:
        viec, bi_cat = _doc_viec(runner_db, ngay, ngay_bat)
    except sqlite3.Error as e:
        log.warning("không đọc được runner.db (%s) — tự dừng nguồn van_hanh", type(e).__name__)
        return ({"trang_thai": "loi", "ly_do": "runner_db_khong_mo_duoc", "so_viec": 0, "so_loi": 0,
                 "bi_cat": False}, [], None)
    cs = dm.NGUONG_VAN_HANH["cua_so_ngay"]
    tu = ngay - timedelta(days=cs - 1)
    trong = [v for v in viec if _trong(v["ngay"], tu, ngay)]
    ds: list[DoLuong] = []
    for khoa, loai in dm.LOAI_VIEC_VAN_HANH.items():
        mau = [v for v in trong if v["loai"] == loai and v["trang_thai"] in TRANG_THAI_VIEC_DONG]
        m = sum(1 for v in mau if khoa in v["khop"])
        dl: dict[str, Any] = {"khoa": khoa, "huong": "tang", "nguon": "van_hanh", "so_uid": m, "so_nhom": 0,
                              "so_video": len(mau), "so_caption": 0, "lift_pt": 0,
                              "nhat_quan_pt": ty_le_pt(m, len(mau)), "ds_uid": []}
        dat, giu, thieu = dm.xet_nguong(dl)
        dl.update(dat=dat, giu=giu, thieu=thieu)
        ds.append(dl)  # type: ignore[arg-type]
    vh = {"trang_thai": "ok", "ly_do": "", "so_viec": len(trong),
          "so_loi": sum(1 for v in trong if v["trang_thai"] == "loi"), "bi_cat": bi_cat}
    return vh, ds, viec


# ---------------------------------------------------------------------------------------------------------------
# Trạng thái lượt quét view hôm nay (§3.6 "Dữ liệu mới của ngày", §3.4a)
# ---------------------------------------------------------------------------------------------------------------
def _ly_do_tu_chu(chu: Any) -> str | None:
    """Mã `ly_do` trong dòng JSON CUỐI của stdout việc quét (tom_tat / loi). Chỉ nhận mã thuộc LY_DO_QUET."""
    if not isinstance(chu, str):
        return None
    for dong_tho in reversed(chu.splitlines()):
        dong = dong_tho.strip()
        if len(dong) > DONG_JSON_TOI_DA or not (dong.startswith("{") and dong.endswith("}")):
            continue
        try:
            d = json.loads(dong)
        except (ValueError, RecursionError):
            continue
        if not isinstance(d, dict):
            continue
        ld = d.get("ly_do")
        return ld if isinstance(ld, str) and ld in dm.LY_DO_QUET else None
    return None


def _ly_do_khop_viec(ly_do: str | None, trang_thai_viec: str) -> str | None:
    """Việc quét thoát 0 (xong) chỉ với ok/da_quet; thoát 1 (loi) với mã khác. Lệch → không nhận."""
    if ly_do is None:
        return None
    if trang_thai_viec == "xong":
        return ly_do if ly_do in _LY_DO_QUET_XONG else None
    if trang_thai_viec == "loi":
        return ly_do if ly_do not in _LY_DO_QUET_XONG else None
    return None


def trang_thai_quet(runner_db: Path, ngay: date) -> dict:
    """nguon.poster_view.quet_hom_nay: việc `quet_view_hang_ngay` khoá = `ngay` MỚI NHẤT trong runner.db.
    `ly_do` lấy từ dòng JSON cuối của việc (ket_qua.tom_tat khi xong, loi khi lỗi); không có thì dự phòng bằng
    `quet_view.doc_ket_qua(<thư mục runner>, ngay)` — chỉ khi việc ĐÃ KẾT THÚC và file cùng ngày có trạng thái khớp.
    Việc còn mở → ly_do None (không nhận kết quả của lần chạy trước). Không có việc / không đọc được → chua_tao."""
    rong = {"trang_thai": "chua_tao", "ly_do": None, "viec_id": None}
    ngay_s = ngay.isoformat()
    try:
        with closing(_mo_ro(runner_db)) as c:
            r = c.execute("SELECT id, trang_thai, ket_qua, loi FROM viec WHERE loai=? AND khoa=? "
                          "ORDER BY tao_luc DESC, rowid DESC LIMIT 1", (LOAI_QUET_VIEW, ngay_s)).fetchone()
    except sqlite3.Error as e:
        log.warning("không đọc được việc quét hôm nay trong runner.db (%s)", type(e).__name__)
        return rong
    if r is None:
        return rong
    vid, tt, kq, loi = r
    viec_id = vid if isinstance(vid, str) and _RE_VIEC_ID.fullmatch(vid) else None
    if tt not in TRANG_THAI_QUET:
        return {"trang_thai": "chua_tao", "ly_do": None, "viec_id": viec_id}
    ly_do = None
    if tt == "xong":
        kq_d = None
        try:
            kq_d = json.loads(kq) if isinstance(kq, str) else None
        except (ValueError, RecursionError):
            kq_d = None
        ly_do = _ly_do_khop_viec(_ly_do_tu_chu(kq_d.get("tom_tat") if isinstance(kq_d, dict) else None), tt)
    elif tt == "loi":
        ly_do = _ly_do_khop_viec(_ly_do_tu_chu(loi), tt)
    if ly_do is None and tt in _FILE_QUET_KHOP:
        f = doc_ket_qua(Path(runner_db).parent, ngay_s)
        if isinstance(f, dict) and f.get("trang_thai") == _FILE_QUET_KHOP[tt]:
            ld = f.get("ly_do")
            ly_do = _ly_do_khop_viec(ld if isinstance(ld, str) and ld in dm.LY_DO_QUET else None, tt)
    return {"trang_thai": TRANG_THAI_QUET[tt], "ly_do": ly_do, "viec_id": viec_id}


# ---------------------------------------------------------------------------------------------------------------
# Theo dõi tuân thủ (§3.6) → KhoHoc.ghi_tuan_thu
# ---------------------------------------------------------------------------------------------------------------
def _lam_theo(khoa: str, huong: str, captions: tuple[str, ...], tu_khoa: tuple[str, ...]) -> bool:
    n = len(captions)
    luat = NGUONG_TUAN_THU.get((khoa, huong))
    if n == 0 or luat is None:
        return False
    co = sum(1 for c in captions if khoa in dm.dac_trung_caption(c, tu_khoa))
    kieu, pt = luat
    if kieu == "it_nhat":
        return co * 100 >= pt * n
    if kieu == "toi_da":
        return co * 100 <= pt * n
    return co * 100 < pt * n


def _dem_khop(viec: Iterable[dict], khoa: str, tu: date, den: date) -> int:
    return sum(1 for v in viec if khoa in v["khop"] and _trong(v["ngay"], tu, den))


def tuan_thu(repo: Path, kho: KhoHoc, ngay: date, viec: list[dict] | None) -> dict[str, dict]:
    """{mã bài học: số tuân thủ} đúng bộ khoá `hoc_danh_muc.KHOA_TUAN_THU[nguồn]` — chỉ báo cáo, không tự quyết.

    - poster_view (bài có ≥ 1 dòng `ap_dung`): so_sp_da_ap = số UID đã nhận gợi ý; so_sp_theo = số UID mà
      captions.txt làm theo mẫu câu gợi ý (NGUONG_TUAN_THU); ty_le_pt = làm tròn xuống.
    - van_hanh (bài đã từng bật, cần `viec` đọc được): số lần khớp 14 ngày TRƯỚC ngày bật / 14 ngày gần nhất.
    Đọc hoc.db bằng kết nối `mode=ro` riêng (KhoHoc không có hàm công khai trả UID của ap_dung); thiếu file → {}."""
    db = Path(kho.duong_dan)
    if not db.is_file():
        return {}
    with closing(_mo_ro(db)) as c:
        bai = c.execute("SELECT ma, khoa, huong, nguon, bat_luc FROM bai_hoc").fetchall()
        ap = c.execute("SELECT ma, uid FROM ap_dung").fetchall()
    uid_cua: dict[str, set[str]] = defaultdict(set)
    for ma, uid in ap:
        if isinstance(uid, str) and _RE_UID.fullmatch(uid):
            uid_cua[ma].add(uid)
    cs = dm.NGUONG_VAN_HANH["cua_so_ngay"]
    repo_kho = KhoRepo(repo)
    ra: dict[str, dict] = {}
    for ma, khoa, huong, nguon, bat_luc in bai:
        dt = dm.DANH_MUC_HOC.get(khoa) if isinstance(khoa, str) else None
        if (not isinstance(ma, str) or not dm.RE_MA_BAI_HOC.fullmatch(ma) or dt is None or nguon != dt.nguon
                or huong not in dt.goi_y):
            continue
        if nguon == "poster_view" and uid_cua.get(ma):
            uids = sorted(uid_cua[ma])
            theo = sum(1 for u in uids if _lam_theo(khoa, huong, repo_kho.captions(u), repo_kho.tu_khoa(u)))
            ra[ma] = {"so_sp_da_ap": len(uids), "so_sp_theo": theo, "ty_le_pt": ty_le_pt(theo, len(uids))}
        elif nguon == "van_hanh" and viec is not None:
            bat = _ngay_bat(bat_luc)
            if bat is None:
                continue
            ra[ma] = {"lan_truoc": _dem_khop(viec, khoa, bat - timedelta(days=cs), bat - timedelta(days=1)),
                      "lan_sau": _dem_khop(viec, khoa, ngay - timedelta(days=cs - 1), ngay), "cua_so_ngay": cs}
    return ra


# ---------------------------------------------------------------------------------------------------------------
# Gộp một ngày đo
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class KetQuaDo:
    trang_thai: str                     # 'xong' | 'tu_dung' (theo poster_view, §4.4)
    ly_do: str
    tu_dung: frozenset[str]
    do_luong: list[DoLuong]
    so_lieu: dict
    viec: list[dict] | None


def do_mot_ngay(poster_db: Path, runner_db: Path, repo: Path, ngay: date,
                ngay_bat: Iterable[date] = ()) -> KetQuaDo:
    """Đo cả 3 nguồn. Tự dừng THEO TỪNG NGUỒN: poster dừng thì chỉ bỏ DoLuong caption, vận hành vẫn đo, và ngược
    lại. lan_hoc = 'tu_dung' khi poster_view dừng, 'xong' khi poster_view có dữ liệu mới (ly_do = mã của nguồn
    vận hành nếu chỉ vận hành dừng). `ngay_bat`: xem `do_van_hanh`."""
    pv, dl_pv = do_poster(poster_db, repo, ngay)
    vh, dl_vh, viec = do_van_hanh(runner_db, ngay, ngay_bat)
    pv["quet_hom_nay"] = trang_thai_quet(runner_db, ngay)
    tu_dung = frozenset(n for n, x in (("poster_view", pv), ("van_hanh", vh)) if x["ly_do"])
    so_lieu = {"du_lieu_moi": not pv["ly_do"], "nguon": {"poster_view": pv, "van_hanh": vh, "sua_tay": dict(SUA_TAY)}}
    return KetQuaDo("tu_dung" if pv["ly_do"] else "xong", pv["ly_do"] or vh["ly_do"], tu_dung,
                    [*dl_pv, *dl_vh], so_lieu, viec)


# ---------------------------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------------------------
class _ThamSoSai(Exception):
    pass


def _in(d: dict) -> None:
    sys.stdout.write(json.dumps(d, ensure_ascii=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _phan_tich(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="runner.hoc_tu_dong", add_help=False, allow_abbrev=False)
    ap.add_argument("--ngay", required=True)
    for t in ("--hoc-db", "--poster-db", "--runner-db", "--repo"):
        ap.add_argument(t, required=True, type=Path)
    ap.add_argument("--viec-id")
    ap.add_argument("--chi-doc", action="store_true")
    ap.add_argument("--bat-ngay", required=True, type=int)
    ap.add_argument("--hieu-luc-toi-da", required=True, type=int)
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:                               # argparse đã in lý do ra stderr
        raise _ThamSoSai("tham số dòng lệnh sai") from e
    a.ngay_d = _ngay_hop_le(a.ngay)
    if a.ngay_d is None:
        raise _ThamSoSai("--ngay phải là ngày YYYY-MM-DD có thật")
    if a.chi_doc == (a.viec_id is not None):
        raise _ThamSoSai("cần đúng một trong --viec-id hoặc --chi-doc")
    for ten in ("bat_ngay", "hieu_luc_toi_da"):
        if not 0 <= getattr(a, ten) <= 1000:
            raise _ThamSoSai(f"--{ten.replace('_', '-')} phải trong [0, 1000]")
    return a


def _bay_gio_that() -> datetime:
    return datetime.now(MUI_GIO_VN)


_KetQuaChay = tuple[int, dict]                         # (mã thoát, dòng JSON sẽ in)


def _ra_loi(ly_do: str) -> _KetQuaChay:
    return 1, {"trang_thai": "loi", "ly_do": ly_do, "so_thay_doi": 0}


def chay(argv: list[str] | None = None, bay_gio: Callable[[], datetime] | None = None) -> int:
    """0 = xong | tu_dung | da_hoc; 1 = loi. In ĐÚNG 1 dòng JSON ASCII ra stdout ở MỌI đường ra (§3.3), kể cả lỗi
    bất ngờ: khi đó log chỉ tên kiểu ngoại lệ (message/traceback có thể mang chữ dữ liệu, §6.1) và ly_do
    loi_bat_ngo. `bay_gio` tiêm được (HT-T1)."""
    try:
        ma, dong = _chay_trong(argv, bay_gio)
    except Exception as e:  # noqa: BLE001 — chốt chặn cuối §3.3: stdout luôn có 1 dòng JSON; log chỉ tên kiểu (§6.1)
        log.error("hoc_tu_dong lỗi bất ngờ (%s)", type(e).__name__)
        ma, dong = _ra_loi("loi_bat_ngo")
    try:
        _in(dong)
    except Exception as e:  # noqa: BLE001 — json.dumps/stdout lỗi: vẫn cố in dòng dự phòng (HT-B4 mục 5)
        log.error("hoc_tu_dong: không in được kết quả (%s) — in dòng dự phòng loi_bat_ngo", type(e).__name__)
        ma, dong = _ra_loi("loi_bat_ngo")
        try:
            _in(dong)
        except Exception as e2:  # noqa: BLE001 — stdout hỏng hẳn: chỉ còn log + mã thoát 1
            log.error("hoc_tu_dong: không in được cả dòng dự phòng (%s)", type(e2).__name__)
    return ma


def _chay_trong(argv: list[str] | None, bay_gio: Callable[[], datetime] | None) -> _KetQuaChay:
    try:
        a = _phan_tich(argv)
    except _ThamSoSai as e:
        log.error("%s", e)                                # chỉ câu cố định của _phan_tich
        return _ra_loi("loi_bat_ngo")
    try:
        kiem_duong_dan(a.hoc_db, a.poster_db, a.runner_db, a.repo)
    except RuntimeError:
        log.error("đường dẫn thật trong lúc chạy thử — từ chối, không mở gì")
        return _ra_loi("duong_dan_thu")
    bay_gio = bay_gio or _bay_gio_that
    return _chay_chi_doc(a, bay_gio) if a.chi_doc else _chay_viec(a, bay_gio)


def _chay_viec(a: argparse.Namespace, bay_gio: Callable[[], datetime]) -> _KetQuaChay:
    ngay = a.ngay
    kho = KhoHoc(a.hoc_db, bay_gio)
    try:
        try:
            kho.mo()
            if not kho.bat_dau_lan(ngay, a.viec_id):
                return 0, {"trang_thai": "da_hoc", "ly_do": "", "so_thay_doi": 0}
        except (ThamSoLoi, RuntimeError, OSError, sqlite3.Error) as e:
            log.error("không mở/bắt đầu được lần học %s trong hoc.db (%s)", ngay, type(e).__name__)
            return _ra_loi("loi_bat_ngo")
        try:
            kq = do_mot_ngay(a.poster_db, a.runner_db, a.repo, a.ngay_d, ngay_bat_van_hanh(a.hoc_db))
            tt = tuan_thu(a.repo, kho, a.ngay_d, kq.viec)
            thay = kho.ap_ket_qua_ngay(ngay, kq.do_luong, a.bat_ngay, a.hieu_luc_toi_da, kq.tu_dung)
            kho.ghi_tuan_thu(ngay, tt)
            kho.ket_thuc_lan(ngay, kq.trang_thai, kq.ly_do, kq.so_lieu)
        except Exception as e:  # noqa: BLE001 — lỗi gì cũng phải thành lan_hoc=loi; log chỉ tên kiểu (§6.1)
            log.error("hoc_tu_dong lỗi bất ngờ (ngay=%s, %s) — ghi lan_hoc=loi", ngay, type(e).__name__)
            try:
                kho.ket_thuc_lan(ngay, "loi", "loi_bat_ngo", {"du_lieu_moi": False})
            except Exception as e2:  # noqa: BLE001 — đã đang xử lý lỗi; ghi log rồi vẫn trả loi_bat_ngo
                log.error("không ghi được lan_hoc=loi cho ngày %s (%s)", ngay, type(e2).__name__)
            return _ra_loi("loi_bat_ngo")
    finally:
        kho.dong()
    return 0, {"trang_thai": kq.trang_thai, "ly_do": kq.ly_do, "so_thay_doi": len(thay)}


def _do_luong_ra(dl: Mapping[str, Any]) -> dict:
    return {k: dl[k] for k in ("khoa", "nguon", "huong", "so_uid", "so_nhom", "so_caption", "so_video", "lift_pt",
                               "nhat_quan_pt", "dat", "thieu")}


def _chay_chi_doc(a: argparse.Namespace, bay_gio: Callable[[], datetime]) -> _KetQuaChay:
    """KhoHoc(chi_doc=True), KHÔNG mo(), không ghi bảng nào; 3 DB mở mode=ro. Lỗi SQLite của hoc.db →
    hoc_db_khong_mo_ro; lỗi khác (ThamSoLoi, …) ném lên `chay` → loi_bat_ngo."""
    kho = KhoHoc(a.hoc_db, bay_gio, chi_doc=True)
    try:
        try:
            ngay_bat = ngay_bat_van_hanh(a.hoc_db)
        except sqlite3.Error as e:
            log.error("không mở được hoc.db ở chế độ chỉ đọc (%s)", type(e).__name__)
            return _ra_loi("hoc_db_khong_mo_ro")
        kq = do_mot_ngay(a.poster_db, a.runner_db, a.repo, a.ngay_d, ngay_bat)
        try:
            tt = tuan_thu(a.repo, kho, a.ngay_d, kq.viec)
            thay = kho.du_kien_ngay(a.ngay, kq.do_luong, a.bat_ngay, a.hieu_luc_toi_da, kq.tu_dung)
        except sqlite3.Error as e:
            log.error("không mở được hoc.db ở chế độ chỉ đọc (%s)", type(e).__name__)
            return _ra_loi("hoc_db_khong_mo_ro")
    finally:
        kho.dong()
    return 0, {"trang_thai": kq.trang_thai, "ly_do": kq.ly_do, "so_thay_doi": len(thay), "chi_doc": True,
               "du_kien": {"so_lieu": kq.so_lieu, "do_luong": [_do_luong_ra(x) for x in kq.do_luong],
                           "thay_doi": thay, "tuan_thu": tt}}


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(chay())
