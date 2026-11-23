"""Công thức thuần của Radar UID (D16; đặc tả docs/radar-uid.md §3, §5.1-§5.4, §7.1-§7.2).

Thuần tuý: không I/O, không mạng, không sqlite3, không đọc token. Nhận snapshot/ứng viên đã chuẩn hoá (dict), trả số.

Quy ước:
- Id (UID, video_id) luôn là chuỗi 19 chữ số; không bao giờ ép sang số.
- Thiếu/không đọc được ⇒ `None`, không điền 0. Số đếm thật (0 video) mới là 0.
- Giờ không có múi giờ được hiểu là giờ VN (UTC+7), kể cả `publish_time` (§2.3.6, C3 chưa đo).
- Mẫu số giờ của mọi Δ là chênh `lay_luc` của chính ta; `update_time` của video KHÔNG dùng (§2.3.2).
- Ngưỡng nằm ở một chỗ: `NGUONG` (§5.4). Mọi ngưỡng là đề xuất chưa kiểm chứng, xem lại sau 14 ngày dữ liệu.
"""
from __future__ import annotations

import math
import re
import statistics
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from typing import Any, NamedTuple, TypedDict

MUI_GIO_VN = timezone(timedelta(hours=7))

RE_UID = re.compile(r"^\d{19}\Z", re.ASCII)

NGUONG: dict[str, Any] = {
    "KY_GIO": (8, 54),
    "TUOI_SONG_NGAY": 90,
    "DU_LIEU_CU_GIO": 36,
    "TANG_TOC_MIN": 2.0,
    "SNAPSHOT_TOI_THIEU": 4,
    "SAN_TOP5": 250,
    "PHU_GIO_TOI_THIEU": 70,
    "TOP5_TOI_THIEU": 1000,
    "VIDEO_TOI_THIEU": 8,
    "FOLLOWER_NHO": 10_000,
    "CREATOR_TOI_THIEU": 3,
    "VIEW_CAO_NHO": 5_000,
    "KHONG_LAM_MOI_DOI_TOI_DA": 1,
    "CREATOR_NHO_TOI_THIEU": 3,
    "CAP_NHAT_KHONG_DOI_KY": 2,
    "TUOI_MOI_NGAY": 14,
    "TUOI_NHO_PHU_NGAY": 30,
    "VIDEO_MOI_NGAY": 30,
    "CREATOR_CHI_PHOI_PT": 50,
    "TOP_N": 5,
    "ADS_BAT": False,
    "ADS_PROMOTE_PT": 30,
    "NGAY_HA_UU_TIEN": 7,
    "TRANG_VIDEO_TOI_DA": 1,
}

# Ngoài bảng §5.4 (§3 bước 5): lọc tìm tương tự.
DO_GIONG_TOI_THIEU = 0.35
GIA_CAN_DUOI = 0.5
GIA_CAN_TREN = 2.0
SO_TUONG_TU_TOI_DA = 10
DO_PHAN_GIAI_NGUONG_SAI_SO = 20          # §5.1: sai_so_tong > 20 (mức M/B) mới xét |Δ| > sai_so_tong
SO_KY_SPARK = 7
SO_SNAPSHOT_TINH_KY = SO_KY_SPARK + 2    # 9 snapshot ⇒ 8 kỳ: đủ spark 7 kỳ, kỳ cũ nhất có kỳ liền trước để xét "đứng yên"

TU_QUANG_CAO: frozenset[str] = frozenset({
    "freeship", "chính hãng", "giá rẻ", "hot", "trend", "mới", "sale", "cao cấp", "loại 1", "siêu", "đẹp", "xịn",
    "tặng", "combo", "set", "bộ", "cái", "chiếc", "nhập khẩu", "uy tín", "tiktok", "shop", "hàng",
})

CO_CHAN = ("DU_LIEU_CU", "GAP", "KHONG_LAM_MOI", "THIEU_MAU")
CAU_KHONG_VIDEO_14 = "không có video ≤ 14 ngày"
CAU_KHONG_CREATOR_NHO = "không có creator nhỏ (follower đọc được < 10.000) trong video ≤ 14 ngày"
CAU_KHONG_VIDEO_MOI_30 = "Không có video mới 30 ngày"

_RE_NGOAC = re.compile(r"\[[^\]]*\]|\([^)]*\)|【[^】]*】")
_RE_TU = re.compile(r"[^\W_]+")
_RE_SO_DON_VI = re.compile(r"^\d+(?:ml|g|kg|cm|mm|m|l|w|v|mah)$")
_RE_SO_TRAN = re.compile(r"^\d+\Z", re.ASCII)
_RE_RUT_GON = re.compile(r"^(\d+(?:\.\d+)?)([KMB])\Z", re.ASCII)
_SAI_SO_RUT_GON = {"K": (1_000, 5), "M": (1_000_000, 5_000), "B": (1_000_000_000, 5_000_000)}


# --------------------------------------------------------------------------- kiểu (§7.2, mỗi module khai báo bản của mình)

class HangVideo(TypedDict):
    video_id: str
    creator: str
    follower: str | None
    view: str
    ban: str | None
    dang_luc: str
    is_promote: int | None


class Snapshot(TypedDict):
    uid: str
    ngay: str
    lay_luc: str
    echotik_cap_nhat: str | None
    ban_tong: str | None
    gia: str | None
    hoa_hong: str | None
    ton: str | None
    tong_creator: str | None
    so_trang: int
    tong_trang: int | None
    videos: dict[str, HangVideo]


class MetaTrang(TypedDict):
    current_page: int | None
    last_page: int | None


class UngVien(TypedDict):
    uid: str
    ten: str
    gia: str | None
    ban_7d: str | None


class KetQuaTimKiem(TypedDict):
    ds: list[UngVien]
    meta: MetaTrang


class KyDo(TypedDict):
    gio: float
    hop_le: bool
    n_video: int                 # tập "đang sống"
    n_creator: int               # tập "đang sống"
    n_doi: int
    ti_le_doi: float | None      # % trên mọi video đo được; chỉ để hiển thị
    trung_vi: int | None
    tong_delta_top5: int | None
    khong_lam_moi: bool
    ds_d24: list[tuple[str, str, int]]     # (video_id, creator, d24) của tập "đang sống"
    loai: dict[str, int]                   # duoi_do_phan_giai, khong_doc_view


class SoRutGon(NamedTuple):
    gia_tri: int
    sai_so: int


# --------------------------------------------------------------------------- tiện ích nhỏ

def doc_so_rut_gon(s: object) -> SoRutGon | None:
    """`125`/`"125"` ⇒ (125, 0); `"21.81K"` ⇒ (21810, 5); `M` ±5.000; `B` ±5.000.000; `N/A`/rỗng/lạ ⇒ None."""
    if isinstance(s, bool):
        return None
    if isinstance(s, int):
        return SoRutGon(s, 0) if s >= 0 else None
    if not isinstance(s, str):
        return None
    chuoi = s.strip()
    if _RE_SO_TRAN.match(chuoi):
        return SoRutGon(int(chuoi), 0)
    m = _RE_RUT_GON.match(chuoi)
    if m is None:
        return None
    he_so, sai_so = _SAI_SO_RUT_GON[m.group(2)]
    return SoRutGon(int(round(Decimal(m.group(1)) * he_so)), sai_so)


def _gio(s: object) -> datetime:
    """Đọc giờ ISO/`YYYY-MM-DD HH:MM[:SS]`; không múi giờ ⇒ giờ VN. Hỏng ⇒ ValueError (không nuốt)."""
    if isinstance(s, datetime):
        t = s
    elif isinstance(s, str):
        t = datetime.fromisoformat(s.strip())
    else:
        raise ValueError(f"không đọc được giờ: {s!r}")
    return t if t.tzinfo is not None else t.replace(tzinfo=MUI_GIO_VN)


def _gio_hoac_none(s: object) -> datetime | None:
    try:
        return _gio(s)
    except ValueError:
        return None


def _trung_vi_nguyen(gia_tri: list[Any]) -> int:
    return math.floor(statistics.median(gia_tri))


def _dem_video_trong(sau: Snapshot, ngay: int) -> int:
    t = _gio(sau["lay_luc"])
    gioi_han = timedelta(days=ngay)
    dem = 0
    for v in sau["videos"].values():
        dang = _gio_hoac_none(v["dang_luc"])
        if dang is not None and t - dang <= gioi_han:
            dem += 1
    return dem


# --------------------------------------------------------------------------- §3 tìm tương tự

def bo_dau(s: str) -> str:
    phan_ra = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in phan_ra if unicodedata.category(c) != "Mn")


_CUM_QUANG_CAO: tuple[tuple[str, ...], ...] = tuple(
    sorted((tuple(c.split()) for c in TU_QUANG_CAO), key=len, reverse=True))


def lam_sach_ten(ten: str) -> list[str]:
    """Tên → danh sách âm tiết sạch (§3 bước 1): NFC, chữ thường, bỏ ngoặc/ký tự lạ/số-đơn vị/số trần/từ quảng cáo."""
    s = unicodedata.normalize("NFC", ten).lower()
    s = _RE_NGOAC.sub(" ", s)
    tu = _RE_TU.findall(s)
    out: list[str] = []
    i = 0
    while i < len(tu):
        cum = next((c for c in _CUM_QUANG_CAO if tuple(tu[i:i + len(c)]) == c), None)
        if cum is not None:
            i += len(cum)
            continue
        t = tu[i]
        i += 1
        if _RE_SO_DON_VI.match(t) or _RE_SO_TRAN.match(t):
            continue
        out.append(t)
    return out


def tu_khoa_tim(ten: str) -> list[str]:
    """4, 3, 2 âm tiết đầu của tên sạch; tên ngắn hơn thì bỏ chuỗi trùng (không gọi E4 hai lần cùng từ khoá)."""
    tu = lam_sach_ten(ten)
    out: list[str] = []
    for n in (4, 3, 2):
        kw = " ".join(tu[:n])
        if kw and kw not in out:
            out.append(kw)
    return out


def _tap_am_tiet(ten: str) -> set[str]:
    return set(_RE_TU.findall(bo_dau(" ".join(lam_sach_ten(ten)))))


def do_giong(ten_goc: str, ten_ung: str) -> float:
    """Jaccard trên tập âm tiết bỏ dấu của hai tên đã làm sạch."""
    a, b = _tap_am_tiet(ten_goc), _tap_am_tiet(ten_ung)
    hop = a | b
    return len(a & b) / len(hop) if hop else 0.0


def keyword_co_loc(tu_khoa: str, ten_ung_vien: list[str]) -> bool:
    """Cổng §3 bước 4: ≥ 50% tên ứng viên chứa ≥ 1 âm tiết của từ khoá (bỏ dấu, không bỏ từ quảng cáo)."""
    am_tiet = set(_RE_TU.findall(bo_dau(unicodedata.normalize("NFC", tu_khoa)).lower()))
    if not am_tiet or not ten_ung_vien:
        return False
    khop = sum(1 for ten in ten_ung_vien
               if am_tiet & set(_RE_TU.findall(bo_dau(unicodedata.normalize("NFC", ten)).lower())))
    return khop * 2 >= len(ten_ung_vien)


def _gia_usd(s: str | None) -> float | None:
    """`'$12.7'` ⇒ 12.7; thiếu, khác USD (`'499.390₫'`) hoặc hỏng ⇒ None (bỏ lọc giá)."""
    if not isinstance(s, str) or not s.strip().startswith("$"):
        return None
    try:
        gia = float(s.strip()[1:].replace(",", "").strip())
    except ValueError:
        return None
    return gia if math.isfinite(gia) and gia > 0 else None


def chon_tuong_tu(goc_ten: str, goc_gia: str | None, ung_vien: list[UngVien], da_loai: frozenset[str],
                  so_luong: int = SO_TUONG_TU_TOI_DA) -> list[UngVien]:
    """§3 bước 5-6. `da_loai` PHẢI gồm cả UID gốc. Giữ `do_giong ≥ 0,35`; có giá cả hai bên thì trong [0,5×; 2×] giá gốc.

    Sắp `do_giong` giảm, rồi `ban_7d` giảm (không đọc được xếp cuối), rồi `uid`; khử trùng theo `uid`.
    """
    gia_goc = _gia_usd(goc_gia)
    da_thay: set[str] = set()
    giu: list[tuple[float, int, str, UngVien]] = []
    for uv in ung_vien:
        uid = uv["uid"]
        if uid in da_thay or uid in da_loai or not RE_UID.match(uid):
            continue
        da_thay.add(uid)
        dg = do_giong(goc_ten, uv["ten"])
        if dg < DO_GIONG_TOI_THIEU:
            continue
        gia = _gia_usd(uv.get("gia"))
        if gia_goc is not None and gia is not None and not (GIA_CAN_DUOI * gia_goc <= gia <= GIA_CAN_TREN * gia_goc):
            continue
        ban = doc_so_rut_gon(uv.get("ban_7d"))
        giu.append((dg, ban.gia_tri if ban is not None else -1, uid, uv))
    giu.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return [x[3] for x in giu[:max(0, so_luong)]]


# --------------------------------------------------------------------------- §5.1 kỳ đo

@dataclass(frozen=True)
class _KyChiTiet:
    """KyDo + giá trị d24 chính xác (Fraction) để trung vị/top 5/tỉ lệ không bị lệch do làm tròn từng video."""
    ky: KyDo
    gio: Fraction
    t_a: datetime
    t_b: datetime
    d24: list[tuple[str, str, Fraction]]
    sau: Snapshot
    truoc: Snapshot


def _ky_day_du(truoc: Snapshot, sau: Snapshot, cap_nhat_dung_yen: bool) -> _KyChiTiet:
    t_a, t_b = _gio(truoc["lay_luc"]), _gio(sau["lay_luc"])
    gio = Fraction((t_b - t_a) // timedelta(microseconds=1), 3_600_000_000)
    thap, cao = NGUONG["KY_GIO"]
    hop_le = thap <= gio <= cao
    loai = {"duoi_do_phan_giai": 0, "khong_doc_view": 0}
    do_duoc: list[tuple[str, str, Fraction, bool, bool]] = []     # video_id, creator, d24, doi, song
    if gio > 0:
        gioi_han_song = timedelta(days=NGUONG["TUOI_SONG_NGAY"])
        for vid, vb in sau["videos"].items():
            va = truoc["videos"].get(vid)
            if va is None:
                continue
            a, b = doc_so_rut_gon(va["view"]), doc_so_rut_gon(vb["view"])
            if a is None or b is None:
                loai["khong_doc_view"] += 1
                continue
            delta = b.gia_tri - a.gia_tri
            sai_so_tong = a.sai_so + b.sai_so
            if sai_so_tong > DO_PHAN_GIAI_NGUONG_SAI_SO and abs(delta) <= sai_so_tong:
                loai["duoi_do_phan_giai"] += 1
                continue
            doi = va["view"].strip() != vb["view"].strip()
            dang = _gio_hoac_none(vb["dang_luc"])
            song = doi or (dang is not None and t_b - dang <= gioi_han_song)
            do_duoc.append((vid, vb["creator"], Fraction(delta) * 24 / gio, doi, song))
    n_doi = sum(1 for x in do_duoc if x[3])
    song_ds = [(vid, cr, d) for vid, cr, d, _, song in do_duoc if song]
    dung_yen = (cap_nhat_dung_yen and truoc["echotik_cap_nhat"] is not None
                and truoc["echotik_cap_nhat"] == sau["echotik_cap_nhat"])
    khong_lam_moi = n_doi <= NGUONG["KHONG_LAM_MOI_DOI_TOI_DA"] or dung_yen
    trung_vi: int | None = None
    top5: int | None = None
    if hop_le and not khong_lam_moi and song_ds:
        trung_vi = _trung_vi_nguyen([d for _, _, d in song_ds])
        lon = sorted((d for _, _, d in song_ds), reverse=True)[:NGUONG["TOP_N"]]
        top5 = math.floor(sum((d for d in lon if d > 0), Fraction(0)))
    ky: KyDo = {
        "gio": float(gio), "hop_le": hop_le, "n_video": len(song_ds),
        "n_creator": len({cr for _, cr, _ in song_ds if cr}), "n_doi": n_doi,
        "ti_le_doi": round(n_doi * 100 / len(do_duoc), 1) if do_duoc else None,
        "trung_vi": trung_vi, "tong_delta_top5": top5, "khong_lam_moi": khong_lam_moi,
        "ds_d24": [(vid, cr, math.floor(d)) for vid, cr, d in song_ds], "loai": loai,
    }
    return _KyChiTiet(ky, gio, t_a, t_b, song_ds, sau, truoc)


def tinh_ky(truoc: Snapshot, sau: Snapshot, cap_nhat_dung_yen: bool = False) -> KyDo:
    """Một kỳ giữa hai snapshot `ok` liên tiếp. `cap_nhat_dung_yen`: `echotik_cap_nhat` không đổi ở kỳ liền trước
    (kỳ này cũng không đổi ⇒ 3 snapshot liền cùng giá trị ⇒ `KHONG_LAM_MOI`)."""
    return _ky_day_du(truoc, sau, cap_nhat_dung_yen).ky


def du_mau(ky: KyDo) -> bool:
    """DU_MAU §5.4: kỳ hợp lệ, không KHONG_LAM_MOI, n_video ≥ 8, n_creator ≥ 3 (tập "đang sống")."""
    return (ky["hop_le"] and not ky["khong_lam_moi"] and ky["n_video"] >= NGUONG["VIDEO_TOI_THIEU"]
            and ky["n_creator"] >= NGUONG["CREATOR_TOI_THIEU"])


def tinh_tang_toc(top5_nay: int, top5_truoc: int) -> tuple[float, bool]:
    """`tang_toc = top5_nay / max(top5_truoc, SAN_TOP5)` (làm tròn 2 số lẻ để hiện) và cờ "đột ngột" tính trên giá trị thô."""
    tho = top5_nay / max(top5_truoc, NGUONG["SAN_TOP5"])
    dot_ngot = tho >= NGUONG["TANG_TOC_MIN"] and top5_nay >= NGUONG["TOP5_TOI_THIEU"]
    return round(tho, 2), dot_ngot


def view_nho(sau: Snapshot, tuoi_ngay: int = NGUONG["TUOI_MOI_NGAY"]) -> tuple[int | None, int, int]:
    """Từ 1 snapshot: video đăng ≤ `tuoi_ngay` ngày của creator có follower ĐỌC ĐƯỢC và < 10.000.
    Trả (trung vị view | None, số creator nhỏ, số creator follower không đọc được); follower thiếu bị loại, không coi 0."""
    t = _gio(sau["lay_luc"])
    gioi_han = timedelta(days=tuoi_ngay)
    views: list[int] = []
    creator_nho: set[str] = set()
    khong_doc: set[str] = set()
    for v in sau["videos"].values():
        dang = _gio_hoac_none(v["dang_luc"])
        if dang is None or t - dang > gioi_han:
            continue
        fl = doc_so_rut_gon(v["follower"])
        if fl is None:
            khong_doc.add(v["creator"])
            continue
        view = doc_so_rut_gon(v["view"])
        if fl.gia_tri < NGUONG["FOLLOWER_NHO"] and view is not None:
            views.append(view.gia_tri)
            creator_nho.add(v["creator"])
    return (_trung_vi_nguyen(views) if views else None), len(creator_nho), len(khong_doc)


def view_nho_cao(trung_vi: int | None, n_creator: int) -> bool:
    """Tiêu chí 2: `view_nho_trung_vi ≥ 5.000` và `n_creator_nho ≥ 3`."""
    return (trung_vi is not None and trung_vi >= NGUONG["VIEW_CAO_NHO"]
            and n_creator >= NGUONG["CREATOR_NHO_TOI_THIEU"])


# --------------------------------------------------------------------------- xếp hạng một UID

def _chuoi_ky(snaps: list[Snapshot]) -> list[_KyChiTiet]:
    out: list[_KyChiTiet] = []
    for i in range(1, len(snaps)):
        cap_truoc = snaps[i - 2]["echotik_cap_nhat"] if i >= 2 else None
        dung_yen = cap_truoc is not None and cap_truoc == snaps[i - 1]["echotik_cap_nhat"]
        out.append(_ky_day_du(snaps[i - 1], snaps[i], dung_yen))
    return out


def _chuoi_lien_tuc(snaps: list[Snapshot]) -> tuple[int, float]:
    """(so_snapshot, phu_gio): chuỗi liên tục kết thúc ở snapshot mới nhất, mọi khoảng liền kề ∈ [8, 54] giờ."""
    if not snaps:
        return 0, 0.0
    thap, cao = NGUONG["KY_GIO"]
    t_cuoi = _gio(snaps[-1]["lay_luc"])
    dau, n = t_cuoi, 1
    for i in range(len(snaps) - 1, 0, -1):
        t_a, t_b = _gio(snaps[i - 1]["lay_luc"]), _gio(snaps[i]["lay_luc"])
        if not thap <= (t_b - t_a).total_seconds() / 3600 <= cao:
            break
        dau, n = t_a, n + 1
    return n, (t_cuoi - dau).total_seconds() / 3600


def _mau_top_video(cuoi: Snapshot) -> bool:
    tong = cuoi["tong_trang"]
    return tong is not None and tong > cuoi["so_trang"]


def _mot_creator_chi_phoi(ky: _KyChiTiet) -> bool:
    if ky.ky["trung_vi"] is None or ky.ky["n_creator"] < NGUONG["CREATOR_TOI_THIEU"]:
        return False
    theo_creator: dict[str, Fraction] = {}
    for _, cr, d in ky.d24:
        if d > 0:
            theo_creator[cr] = theo_creator.get(cr, Fraction(0)) + d
    tong = sum(theo_creator.values(), Fraction(0))
    return bool(tong > 0 and max(theo_creator.values()) * 100 >= NGUONG["CREATOR_CHI_PHOI_PT"] * tong)


def _promote(cuoi: Snapshot) -> tuple[int | None, int | None]:
    biet = [v["is_promote"] for v in cuoi["videos"].values() if v["is_promote"] is not None]
    return (sum(1 for p in biet if p), len(biet)) if biet else (None, None)


def _d_ban_ngay(ky: _KyChiTiet) -> float | None:
    if not ky.ky["hop_le"]:
        return None
    a, b = doc_so_rut_gon(ky.truoc["ban_tong"]), doc_so_rut_gon(ky.sau["ban_tong"])
    if a is None or b is None:
        return None
    delta, sai_so_tong = b.gia_tri - a.gia_tri, a.sai_so + b.sai_so
    if sai_so_tong > DO_PHAN_GIAI_NGUONG_SAI_SO and abs(delta) <= sai_so_tong:
        return None
    return round(float(Fraction(delta) * 24 / ky.gio), 1)


def _creator_moi_ngay(ky: _KyChiTiet) -> float | None:
    if not ky.ky["hop_le"]:
        return None
    moi = {v["creator"] for v in ky.sau["videos"].values()
           if (d := _gio_hoac_none(v["dang_luc"])) is not None and ky.t_a < d <= ky.t_b}
    return round(float(Fraction(len(moi)) * 24 / ky.gio), 1)


def _ly_do_tang_toc(gan: _KyChiTiet | None, truoc: _KyChiTiet | None) -> str:
    if truoc is None or gan is None:
        return "chưa có kỳ trước"
    if not gan.ky["hop_le"]:
        return "kỳ này GAP"
    if gan.ky["khong_lam_moi"]:
        return "kỳ này EchoTik không làm mới"
    if not truoc.ky["hop_le"]:
        return "kỳ trước GAP"
    if truoc.ky["khong_lam_moi"]:
        return "kỳ trước EchoTik không làm mới"
    return ""


def _ly_do_thieu_mau(gan: _KyChiTiet | None, so_snapshot: int, phu_gio: float) -> list[str]:
    ly_do: list[str] = []
    if so_snapshot < NGUONG["SNAPSHOT_TOI_THIEU"]:
        ly_do.append(f"so_snapshot {so_snapshot}/{NGUONG['SNAPSHOT_TOI_THIEU']}")
    if phu_gio < NGUONG["PHU_GIO_TOI_THIEU"]:
        ly_do.append(f"phu_gio {round(phu_gio, 1)}/{NGUONG['PHU_GIO_TOI_THIEU']}")
    if gan is None:
        ly_do.append("chưa có kỳ nào (cần ≥ 2 snapshot)")
        return ly_do
    ky = gan.ky
    if not ky["hop_le"]:
        ly_do.append("kỳ gần nhất ngoài khoảng 8-54 giờ")
    if ky["khong_lam_moi"]:
        ly_do.append("EchoTik không làm mới")
    if ky["n_video"] < NGUONG["VIDEO_TOI_THIEU"]:
        ly_do.append(f"n_video {ky['n_video']}/{NGUONG['VIDEO_TOI_THIEU']}")
    if ky["n_creator"] < NGUONG["CREATOR_TOI_THIEU"]:
        ly_do.append(f"n_creator {ky['n_creator']}/{NGUONG['CREATOR_TOI_THIEU']}")
    return ly_do


def _trong_rong(hom_nay: datetime, bat_dau_ngay: str) -> dict[str, Any]:
    """UID chưa có snapshot nào: mọi số là None, luôn kèm lý do."""
    ha = _ha_uu_tien(hom_nay, bat_dau_ngay)
    return {
        "xep_loai": "chua_du", "uu_tien": "ha" if ha else "thuong", "tam": False,
        "trung_vi": None, "trung_vi_truoc": None, "tong_delta_top5": None, "tong_delta_top5_truoc": None,
        "tang_toc": None, "tang_dot_ngot": False, "ly_do_tang_toc": "chưa có kỳ trước",
        "n_video": None, "n_creator": None, "n_doi": None, "ti_le_doi": None,
        "view_nho_trung_vi": None, "n_creator_nho": None, "cau_view_nho": "chưa có snapshot",
        "view_nho_30_trung_vi": None, "n_creator_nho_30": None, "follower_khong_doc": None,
        "trung_vi_14": None, "n_video_14": None, "n_video_moi_30": None, "cau_video_moi": "",
        "promote_x": None, "promote_y": None, "spark": [], "d_ban_ngay": None, "creator_moi_ngay": None,
        "gia": None, "hoa_hong": None, "ton": None, "du_lieu_luc": None, "echotik_cap_nhat": None,
        "so_snapshot": 0, "phu_gio": 0.0, "co": ["THIEU_MAU"], "co_canh_bao": [],
        "ly_do_thieu": ["chưa có snapshot"], "duoi_do_phan_giai": None,
    }


def _ha_uu_tien(hom_nay: datetime, bat_dau_ngay: str) -> bool:
    ngay_nay = hom_nay.astimezone(MUI_GIO_VN).date()
    return (ngay_nay - datetime.fromisoformat(bat_dau_ngay).date()).days >= NGUONG["NGAY_HA_UU_TIEN"]


def xep_hang_uid(snaps: list[Snapshot], hom_nay: datetime, bat_dau_ngay: str) -> dict[str, Any]:
    """Mọi chỉ số + cờ + xếp loại của một UID từ các snapshot `ok` của nó (khoá đúng UidRa §7.1, trừ
    uid/vai/ten/shop/do_giong/trang_thai). `hom_nay` không có múi giờ ⇒ giờ VN. `bat_dau_ngay` = `YYYY-MM-DD`."""
    hom_nay = _gio(hom_nay)
    if not snaps:
        return _trong_rong(hom_nay, bat_dau_ngay)
    snaps = sorted(snaps, key=lambda s: _gio(s["lay_luc"]))
    cuoi = snaps[-1]
    so_snapshot, phu_gio = _chuoi_lien_tuc(snaps)
    cac_ky = _chuoi_ky(snaps[-SO_SNAPSHOT_TINH_KY:])
    gan = cac_ky[-1] if cac_ky else None
    truoc = cac_ky[-2] if len(cac_ky) >= 2 else None

    # --- cờ
    co: list[str] = []
    if hom_nay - _gio(cuoi["lay_luc"]) > timedelta(hours=NGUONG["DU_LIEU_CU_GIO"]):
        co.append("DU_LIEU_CU")
    if gan is not None and not gan.ky["hop_le"]:
        co.append("GAP")
    if gan is not None and gan.ky["khong_lam_moi"]:
        co.append("KHONG_LAM_MOI")
    thieu_mau = (gan is None or not du_mau(gan.ky) or so_snapshot < NGUONG["SNAPSHOT_TOI_THIEU"]
                 or phu_gio < NGUONG["PHU_GIO_TOI_THIEU"])
    if thieu_mau:
        co.append("THIEU_MAU")
    promote_x, promote_y = _promote(cuoi)
    canh_bao: list[str] = []
    if _mau_top_video(cuoi):
        canh_bao.append("MAU_TOP_VIDEO")
    if gan is not None and _mot_creator_chi_phoi(gan):
        canh_bao.append("MOT_CREATOR_CHI_PHOI")
    if (NGUONG["ADS_BAT"] and promote_x is not None and promote_y and promote_x >= 3
            and promote_x * 100 >= NGUONG["ADS_PROMOTE_PT"] * promote_y):
        canh_bao.append("NGHI_ADS")

    # --- chỉ số chính, tăng tốc
    ky_gan: KyDo | None = gan.ky if gan else None
    ky_truoc: KyDo | None = truoc.ky if truoc else None
    top5 = ky_gan["tong_delta_top5"] if ky_gan else None
    top5_truoc = ky_truoc["tong_delta_top5"] if ky_truoc else None
    tang_toc: float | None = None
    dot_ngot = False
    ly_do_tang_toc = ""
    if top5 is not None and top5_truoc is not None:
        tang_toc, dot_ngot = tinh_tang_toc(top5, top5_truoc)
    else:
        ly_do_tang_toc = _ly_do_tang_toc(gan, truoc)

    # --- view creator nhỏ, video mới
    vn14, n_nho14, khong_doc = view_nho(cuoi, NGUONG["TUOI_MOI_NGAY"])
    vn30, n_nho30, _ = view_nho(cuoi, NGUONG["TUOI_NHO_PHU_NGAY"])
    cau_view_nho = ""
    if vn14 is None:
        cau_view_nho = (CAU_KHONG_CREATOR_NHO if _dem_video_trong(cuoi, NGUONG["TUOI_MOI_NGAY"])
                        else CAU_KHONG_VIDEO_14)
    n_moi_30 = _dem_video_trong(cuoi, NGUONG["VIDEO_MOI_NGAY"])
    trung_vi_14: int | None = None
    n_video_14: int | None = None
    if gan is not None and ky_gan is not None and ky_gan["trung_vi"] is not None:
        han = timedelta(days=NGUONG["TUOI_MOI_NGAY"])
        t_cuoi = _gio(cuoi["lay_luc"])
        gan_14 = [d for vid, _, d in gan.d24
                  if (dang := _gio_hoac_none(cuoi["videos"][vid]["dang_luc"])) is not None and t_cuoi - dang <= han]
        n_video_14 = len(gan_14)
        trung_vi_14 = _trung_vi_nguyen(gan_14) if gan_14 else None

    tieu_chi_1 = dot_ngot
    tieu_chi_2 = view_nho_cao(vn14, n_nho14)
    chan = any(c in co for c in ("DU_LIEU_CU", "GAP", "KHONG_LAM_MOI"))
    ly_do_thieu: list[str] = []
    if chan:
        xep_loai = "chan"
    elif thieu_mau:
        xep_loai = "chua_du"
    else:
        truoc_du_mau = ky_truoc is not None and du_mau(ky_truoc)
        xep_loai = "dang_co_da" if (truoc_du_mau and tieu_chi_1 and tieu_chi_2) else "chua_co_da"
        if xep_loai == "chua_co_da":
            if not truoc_du_mau:
                ly_do_thieu.append("kỳ trước chưa đủ mẫu")
            if not tieu_chi_1:
                ly_do_thieu.append("chưa đạt tiêu chí 1 (tăng đột ngột)"
                                   + (f": {ly_do_tang_toc}" if tang_toc is None else ""))
            if not tieu_chi_2:
                ly_do_thieu.append("chưa đạt tiêu chí 2 (view cao ở creator nhỏ)")
    if thieu_mau:
        ly_do_thieu = _ly_do_thieu_mau(gan, so_snapshot, phu_gio)

    spark = [c.ky["trung_vi"] for c in cac_ky[-SO_KY_SPARK:]]
    trung_vi = ky_gan["trung_vi"] if ky_gan else None
    return {
        "xep_loai": xep_loai,
        "uu_tien": "ha" if (xep_loai == "chua_du" and thieu_mau and _ha_uu_tien(hom_nay, bat_dau_ngay)) else "thuong",
        "tam": xep_loai == "chua_du" and trung_vi is not None,
        "trung_vi": trung_vi, "trung_vi_truoc": ky_truoc["trung_vi"] if ky_truoc else None,
        "tong_delta_top5": top5, "tong_delta_top5_truoc": top5_truoc,
        "tang_toc": tang_toc, "tang_dot_ngot": dot_ngot, "ly_do_tang_toc": ly_do_tang_toc,
        "n_video": ky_gan["n_video"] if ky_gan else None, "n_creator": ky_gan["n_creator"] if ky_gan else None,
        "n_doi": ky_gan["n_doi"] if ky_gan else None, "ti_le_doi": ky_gan["ti_le_doi"] if ky_gan else None,
        "view_nho_trung_vi": vn14, "n_creator_nho": n_nho14, "cau_view_nho": cau_view_nho,
        "view_nho_30_trung_vi": vn30, "n_creator_nho_30": n_nho30, "follower_khong_doc": khong_doc,
        "trung_vi_14": trung_vi_14, "n_video_14": n_video_14,
        "n_video_moi_30": n_moi_30, "cau_video_moi": CAU_KHONG_VIDEO_MOI_30 if n_moi_30 == 0 else "",
        "promote_x": promote_x, "promote_y": promote_y,
        "spark": spark, "d_ban_ngay": _d_ban_ngay(gan) if gan else None,
        "creator_moi_ngay": _creator_moi_ngay(gan) if gan else None,
        "gia": cuoi["gia"], "hoa_hong": cuoi["hoa_hong"], "ton": cuoi["ton"],
        "du_lieu_luc": cuoi["lay_luc"], "echotik_cap_nhat": cuoi["echotik_cap_nhat"],
        "so_snapshot": so_snapshot, "phu_gio": round(phu_gio, 1),
        "co": co, "co_canh_bao": canh_bao, "ly_do_thieu": ly_do_thieu,
        "duoi_do_phan_giai": ky_gan["loai"]["duoi_do_phan_giai"] if ky_gan else None,
    }
