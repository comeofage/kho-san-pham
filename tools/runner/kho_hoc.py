"""Kho bài học SQLite `hoc.db` + máy trạng thái (docs/hoc-tu-dong.md §3.5, §3.7, §3.8, §4.1–§4.4).

Nguyên tắc:
- Import và `KhoHoc(...)` KHÔNG mở/tạo file. Schema chỉ tạo/nâng trong `mo()` (gọi sau mutex runner, hoặc từ script
  khi không `--chi-doc`). Kết nối thường mở `mode=rw` (không tự tạo file); `chi_doc=True` mở `mode=ro`, thiếu file
  thì coi như rỗng, mọi hàm ghi ném `ChiDoc`.
- Mô hình luồng như `KhoViec`: mỗi luồng một kết nối (`threading.local`), `check_same_thread=True`,
  `isolation_level=None`, mọi ghi trong `BEGIN IMMEDIATE`. Chuyển trạng thái của người là CAS trên `trang_thai`.
- "Hôm nay" luôn lấy qua `bay_gio` tiêm vào (giờ VN). Hết hạn xét CẢ lúc đọc (trạng thái hiệu dụng).
- Không cột nào chứa chữ từ caption/log: mọi giá trị ghi vào đều qua kiểm kiểu + regex + enum.
- Đọc ra cũng lọc lại (agent cùng user có thể sửa tay hoc.db): mọi chữ trong BaoCao/BaiHocRa phải thuộc enum/danh mục
  hoặc khớp regex; sai → null, hoặc bỏ cả dòng khi mã/khoá/hướng/nguồn/trạng thái lạ.
- Không có hạn mức mặc định: hàm cần `bat_ngay`/`hieu_luc_toi_da` bắt bên gọi truyền hạn mức thật.
"""
from __future__ import annotations

import json
import logging
import math
import re
import secrets
import sqlite3
import string
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import quote

from . import hoc_danh_muc as dm
from .kieu import ThamSoLoi, gio_vn

log = logging.getLogger(__name__)

PHIEN_BAN_SCHEMA = "1"
GIU_LAN_HOC_NGAY = 180                      # mo() dọn lan_hoc/do_luong cũ hơn chừng này
TRANG_THAI_BAI = ("ung_vien", "hieu_luc", "het_han", "tat_tu_dong", "hoan_tac")
TRANG_THAI_MO = ("ung_vien", "hieu_luc")
TRANG_THAI_LAN = ("dang_chay", "xong", "tu_dung", "loi")
TRANG_THAI_KET_THUC = ("xong", "tu_dung", "loi")
BOI_HE_THONG = "he_thong"
# Không có hạn mức mặc định (HT-B1b mục 4): mọi hàm cần `bat_ngay`/`hieu_luc_toi_da` bắt bên gọi truyền hạn mức THẬT
# đang áp dụng (cau_hinh.json đã hạ), để không bao giờ tính bằng trần 1/5 khi người dùng đã hạ về 0.
DA_TAT_TOI_DA = 50                         # số bài "đã tắt" tối đa trong báo cáo
DS_UID_TOI_DA = 30
SO_LIEU_TOI_DA_BYTE = 64 * 1024

_RE_NGAY = re.compile(r"^\d{4}-\d{2}-\d{2}\Z", re.ASCII)
_RE_VIEC_ID = re.compile(r"^j\d{14}[a-z0-9]{4}\Z", re.ASCII)       # khớp KhoViec._id_moi
_RE_UID = re.compile(r"^\d{19}\Z", re.ASCII)
_RE_BOI = re.compile(r"^[\w.@\-]{1,64}\Z")
_RE_MA_NGAN = re.compile(r"^[a-z0-9_]{1,40}\Z", re.ASCII)          # khoá JSON, mã "thiếu"
_RE_CHUOI_SO_LIEU = re.compile(r"^[A-Za-z0-9_.:+\-]{0,64}\Z", re.ASCII)   # ngày, ISO, mã — không có khoảng trắng
_RE_LUC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:[+-]\d{2}:\d{2}|Z)?\Z", re.ASCII)
CUA_SO_TUAN_THU_TOI_DA = 366
_KY_TU_MA = string.ascii_lowercase + string.digits

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(khoa TEXT PRIMARY KEY, gia_tri TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lan_hoc(
  ngay TEXT PRIMARY KEY, viec_id TEXT NOT NULL,
  trang_thai TEXT NOT NULL CHECK(trang_thai IN ('dang_chay','xong','tu_dung','loi')),
  ly_do TEXT NOT NULL DEFAULT '', bat_dau_luc TEXT NOT NULL, ket_thuc_luc TEXT,
  so_lieu TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS do_luong(
  ngay TEXT NOT NULL REFERENCES lan_hoc(ngay), khoa TEXT NOT NULL, huong TEXT NOT NULL CHECK(huong IN ('tang','giam')),
  nguon TEXT NOT NULL CHECK(nguon IN ('poster_view','van_hanh','sua_tay')),
  so_uid INTEGER NOT NULL, so_nhom INTEGER NOT NULL, so_video INTEGER NOT NULL, so_caption INTEGER NOT NULL,
  lift_pt INTEGER NOT NULL, nhat_quan_pt INTEGER NOT NULL, dat INTEGER NOT NULL, giu INTEGER NOT NULL,
  thieu TEXT NOT NULL DEFAULT '[]', ds_uid TEXT NOT NULL DEFAULT '[]',
  PRIMARY KEY (ngay, khoa));
CREATE TABLE IF NOT EXISTS bai_hoc(
  ma TEXT PRIMARY KEY, khoa TEXT NOT NULL, huong TEXT NOT NULL CHECK(huong IN ('tang','giam')),
  nguon TEXT NOT NULL CHECK(nguon IN ('poster_view','van_hanh','sua_tay')),
  trang_thai TEXT NOT NULL CHECK(trang_thai IN ('ung_vien','hieu_luc','het_han','tat_tu_dong','hoan_tac')),
  ngay_dat_lien_tiep INTEGER NOT NULL DEFAULT 1, ngay_dat_cuoi TEXT NOT NULL,
  bang_chung TEXT NOT NULL, tao_luc TEXT NOT NULL, bat_luc TEXT, het_han_luc TEXT, tat_luc TEXT, tat_boi TEXT,
  ly_do_tat TEXT, tuan_thu TEXT, tuan_thu_ngay TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS bai_hoc_mo ON bai_hoc(khoa) WHERE trang_thai IN ('ung_vien','hieu_luc');
CREATE TABLE IF NOT EXISTS su_kien_hoc(id INTEGER PRIMARY KEY AUTOINCREMENT, ma TEXT NOT NULL REFERENCES bai_hoc(ma),
  ngay TEXT NOT NULL, luc TEXT NOT NULL, tu TEXT, den TEXT NOT NULL, boi TEXT NOT NULL, ly_do TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ap_dung(ma TEXT NOT NULL REFERENCES bai_hoc(ma), viec_id TEXT NOT NULL, uid TEXT NOT NULL,
  luc TEXT NOT NULL, PRIMARY KEY (ma, viec_id))
"""


# ---------------------------------------------------------------------------------------------------------------
# Ngoại lệ + kiểu
# ---------------------------------------------------------------------------------------------------------------
class KhongCoBaiHoc(LookupError):
    """404: không có bài học (kể cả mã sai dạng), hoặc chưa có lần học nào (`bao_cao(None)`)."""

    def __init__(self, loi: str = dm.TEN_LY_DO["khong_co_bai_hoc"]) -> None:
        super().__init__(loi)
        self.loi = loi


class SaiTrangThaiHoc(RuntimeError):
    """409: `.loi` là câu cố định trong `hoc_danh_muc.TEN_LY_DO`, `.ma_ly_do` là mã của câu đó."""

    def __init__(self, loi: str, ma_ly_do: str = "") -> None:
        super().__init__(loi)
        self.loi = loi
        self.ma_ly_do = ma_ly_do


class ChiDoc(RuntimeError):
    """Gọi hàm ghi (hoặc `mo()`) trên `KhoHoc(chi_doc=True)`."""


class DoLuong(TypedDict):
    khoa: str
    huong: str
    nguon: str
    so_uid: int
    so_nhom: int
    so_video: int
    so_caption: int
    lift_pt: int
    nhat_quan_pt: int
    dat: bool
    giu: bool
    thieu: list[str]
    ds_uid: list[dict]


_KHOA_DO_LUONG = frozenset(DoLuong.__annotations__)


def _sai_409(ma_ly_do: str, **so: int) -> SaiTrangThaiHoc:
    return SaiTrangThaiHoc(dm.TEN_LY_DO[ma_ly_do].format(**so), ma_ly_do)


# ---------------------------------------------------------------------------------------------------------------
# Kiểm đầu vào (thuần)
# ---------------------------------------------------------------------------------------------------------------
def _kiem_ngay(s: Any, ten: str = "ngay") -> date:
    if not isinstance(s, str) or not _RE_NGAY.fullmatch(s):
        raise ThamSoLoi(f"{ten} phải dạng YYYY-MM-DD")
    try:
        return date.fromisoformat(s)
    except ValueError as e:
        raise ThamSoLoi(f"{ten} không phải ngày có thật") from e


def _kiem_so(x: Any, ten: str, lo: int, hi: int) -> int:
    if type(x) is not int or not (lo <= x <= hi):
        raise ThamSoLoi(f"{ten} phải là số nguyên trong [{lo}, {hi}]")
    return x


def _kiem_tu_dung(tu_dung: Any) -> frozenset[str]:
    if not isinstance(tu_dung, (set, frozenset)) or not all(isinstance(x, str) and x in dm.NGUON for x in tu_dung):
        raise ThamSoLoi(f"tu_dung phải là tập con của {dm.NGUON}")
    return frozenset(tu_dung)


def _kiem_ma(ma: Any) -> str:
    """Mã sai dạng = không có bài học (404, hợp đồng §3.8 P3-7)."""
    if not isinstance(ma, str) or not dm.RE_MA_BAI_HOC.fullmatch(ma):
        raise KhongCoBaiHoc()
    return ma


def _kiem_boi(boi: Any) -> str:
    if not isinstance(boi, str) or not _RE_BOI.fullmatch(boi):
        raise ThamSoLoi("boi phải là tên người dùng 1–64 ký tự chữ/số/._@-")
    return boi


def kiem_do_luong(dl: Any) -> dict:
    """Kiểm một DoLuong (đủ đúng 13 trường, đúng kiểu, trong khoảng, khoá thuộc danh mục) → bản sao sạch.
    Sai → ThamSoLoi. Không trường nào được mang chữ tự do."""
    if not isinstance(dl, Mapping):
        raise ThamSoLoi("do_luong phải là dict")
    if set(dl) != _KHOA_DO_LUONG:
        raise ThamSoLoi(f"do_luong thiếu/thừa trường: {sorted(set(dl) ^ _KHOA_DO_LUONG)}")
    khoa = dl["khoa"]
    dt = dm.DANH_MUC_HOC.get(khoa) if isinstance(khoa, str) else None
    if dt is None:
        raise ThamSoLoi("khoa không thuộc danh mục")
    if dl["nguon"] != dt.nguon:
        raise ThamSoLoi("nguon không khớp danh mục của khoá")
    if dl["huong"] not in dm.HUONG:
        raise ThamSoLoi("huong phải là tang/giam")
    if dl["huong"] not in dt.goi_y:                    # khoá vận hành chỉ có mẫu 'tang' (HT-B1b mục 6) → từ chối
        raise ThamSoLoi(f"khoá {khoa} chỉ nhận huong {'/'.join(dt.goi_y)}")
    ra: dict[str, Any] = {"khoa": khoa, "huong": dl["huong"], "nguon": dt.nguon}
    for ten in ("so_uid", "so_nhom", "so_video", "so_caption"):
        ra[ten] = _kiem_so(dl[ten], ten, 0, dm.SO_TOI_DA)
    ra["lift_pt"] = _kiem_so(dl["lift_pt"], "lift_pt", -100, dm.SO_TOI_DA)
    ra["nhat_quan_pt"] = _kiem_so(dl["nhat_quan_pt"], "nhat_quan_pt", 0, 100)
    for ten in ("dat", "giu"):
        if type(dl[ten]) is not bool:
            raise ThamSoLoi(f"{ten} phải là true/false")
        ra[ten] = dl[ten]
    thieu = dl["thieu"]
    if not isinstance(thieu, list) or len(thieu) > 20 or not all(
            isinstance(x, str) and _RE_MA_NGAN.fullmatch(x) for x in thieu):
        raise ThamSoLoi("thieu phải là danh sách mã [a-z0-9_]")
    ra["thieu"] = list(thieu)
    ds_uid = dl["ds_uid"]
    if not isinstance(ds_uid, list) or len(ds_uid) > DS_UID_TOI_DA:
        raise ThamSoLoi(f"ds_uid phải là danh sách ≤ {DS_UID_TOI_DA} mục")
    ra["ds_uid"] = []
    for m in ds_uid:
        if not isinstance(m, Mapping) or not isinstance(m.get("uid"), str) or not _RE_UID.fullmatch(m["uid"]):
            raise ThamSoLoi("ds_uid: mỗi mục phải có uid 19 chữ số")
        sach: dict[str, Any] = {"uid": m["uid"]}
        for k, v in m.items():
            if k == "uid":
                continue
            if not isinstance(k, str) or not _RE_MA_NGAN.fullmatch(k):
                raise ThamSoLoi("ds_uid: khoá lạ")
            if v is not None and (type(v) is not int or abs(v) > dm.SO_TOI_DA):
                raise ThamSoLoi("ds_uid: giá trị chỉ được là số nguyên")
            sach[k] = v
        ra["ds_uid"].append(sach)
    return ra


def _kiem_so_lieu(x: Any, sau: int = 0) -> Any:
    """so_lieu chỉ chứa số đếm/mã: số, bool, None, chuỗi mã ngắn không khoảng trắng; dict khoá [a-z0-9_]."""
    if sau > 5:
        raise ThamSoLoi("so_lieu lồng quá sâu")
    if x is None or type(x) in (bool, int):
        return x
    if type(x) is float:
        if not math.isfinite(x):
            raise ThamSoLoi("so_lieu có số không hữu hạn")
        return x
    if isinstance(x, str):
        if not _RE_CHUOI_SO_LIEU.fullmatch(x):
            raise ThamSoLoi("so_lieu chỉ nhận chuỗi mã ngắn (không chữ tự do)")
        return x
    if isinstance(x, list):
        if len(x) > 200:
            raise ThamSoLoi("so_lieu: danh sách quá dài")
        return [_kiem_so_lieu(v, sau + 1) for v in x]
    if isinstance(x, Mapping):
        ra = {}
        for k, v in x.items():
            if not isinstance(k, str) or not _RE_MA_NGAN.fullmatch(k):
                raise ThamSoLoi("so_lieu: khoá lạ")
            ra[k] = _kiem_so_lieu(v, sau + 1)
        return ra
    raise ThamSoLoi("so_lieu có kiểu không nhận")


def _ngay_vn_cua(luc: Any) -> date | None:
    """Ngày VN của một mốc ISO (tat_luc, bat_luc…). Hỏng → None."""
    if not isinstance(luc, str):
        return None
    try:
        return gio_vn(datetime.fromisoformat(luc)).date()
    except ValueError:
        return None


def _ngay_hoac_none(s: Any) -> date | None:
    if not isinstance(s, str) or not _RE_NGAY.fullmatch(s):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _luc_hoac_none(s: Any) -> str | None:
    """Mốc ISO (bat_luc, tat_luc, bat_dau_luc…) đọc từ hoc.db: đúng dạng và parse được → giữ; ngược lại None."""
    if not isinstance(s, str) or not _RE_LUC.fullmatch(s):
        return None
    try:
        datetime.fromisoformat(s)
    except ValueError:
        return None
    return s


def _dong_bai_hop_le(r: Mapping[str, Any]) -> dm.DacTrung | None:
    """Dòng bai_hoc đọc từ hoc.db (agent cùng user có thể sửa) có được ra ngoài không: mã đúng dạng, khoá thuộc danh
    mục, nguồn khớp danh mục, hướng có mẫu, trạng thái thuộc enum. Sai một điều → None (bỏ cả dòng)."""
    ma, khoa = r.get("ma"), r.get("khoa")
    if not isinstance(ma, str) or not dm.RE_MA_BAI_HOC.fullmatch(ma):
        return None
    dt = dm.DANH_MUC_HOC.get(khoa) if isinstance(khoa, str) else None
    if dt is None or r.get("nguon") != dt.nguon or r.get("huong") not in dt.goi_y:
        return None
    if r.get("trang_thai") not in TRANG_THAI_BAI:
        return None
    return dt


def kiem_tuan_thu(so: Any) -> tuple[str, dict[str, int]]:
    """Một mục tuân thủ → (nguồn, bản sao sạch). Phải có ĐÚNG bộ khoá `hoc_danh_muc.KHOA_TUAN_THU[nguon]`, mọi giá
    trị là số nguyên ≥ 0 (không bool/float/chuỗi); ty_le_pt ≤ 100; so_sp_theo ≤ so_sp_da_ap; cua_so_ngay 1–366.
    Sai → ThamSoLoi."""
    if not isinstance(so, Mapping):
        raise ThamSoLoi("tuan_thu: mỗi mục phải là dict")
    nguon = next((n for n, k in dm.KHOA_TUAN_THU.items() if set(so) == set(k)), None)
    if nguon is None:
        raise ThamSoLoi(f"tuan_thu: khoá phải đúng một bộ trong {dm.KHOA_TUAN_THU}")
    ra = {k: _kiem_so(so[k], k, 0, dm.SO_TOI_DA) for k in dm.KHOA_TUAN_THU[nguon]}
    if nguon == "poster_view":
        _kiem_so(ra["ty_le_pt"], "ty_le_pt", 0, 100)
        _kiem_so(ra["so_sp_theo"], "so_sp_theo", 0, ra["so_sp_da_ap"])
    else:
        _kiem_so(ra["cua_so_ngay"], "cua_so_ngay", 1, CUA_SO_TUAN_THU_TOI_DA)
    return nguon, ra


def _doc_tuan_thu(s: Any, ngay: Any, nguon: str) -> dict | None:
    """tuan_thu từ hoc.db → {"ngay", ...số} hoặc None (thiếu, hỏng JSON, sai khoá/kiểu, khác nguồn của bài)."""
    if not isinstance(s, str) or _ngay_hoac_none(ngay) is None:
        return None
    try:
        nguon_so, so = kiem_tuan_thu(json.loads(s))
    except (ValueError, RecursionError):               # ThamSoLoi là ValueError; JSON lồng quá sâu → RecursionError
        return None
    return {"ngay": ngay, **so} if nguon_so == nguon else None


def la_ap_phieu(khoa: Any) -> bool:
    """Khoá thuộc danh mục VÀ được vào phiếu (`ap_phieu`). Khoá "Chỉ báo cáo" (§3.6) → False: không thành bài học,
    không chiếm lượt tự bật / chỗ hiệu lực (HT-B4 mục 1)."""
    dt = dm.DANH_MUC_HOC.get(khoa) if isinstance(khoa, str) else None
    return dt is not None and dt.ap_phieu


def _la_chi_bao_cao(khoa: Any) -> bool:
    """Khoá THUỘC danh mục nhưng `ap_phieu=False`. Khoá lạ/None → False (không coi là chỉ báo cáo)."""
    dt = dm.DANH_MUC_HOC.get(khoa) if isinstance(khoa, str) else None
    return dt is not None and not dt.ap_phieu


def han_dung_ngay(nguon: str) -> int:
    return dm.NGUONG_VAN_HANH["han_dung_ngay"] if nguon == "van_hanh" else int(dm.NGUONG["han_dung_ngay"])


def trang_thai_hieu_dung(bai: Mapping[str, Any], hom_nay: date) -> str:
    """Trạng thái HIỆU DỤNG (§4.2 "Hết hạn tính lúc đọc"): dòng `hieu_luc` mà `het_han_luc` hỏng, đã qua, hoặc xa
    hơn hạn dùng tối đa (+1 ngày cho việc học của hôm qua) → 'het_han'. Còn lại = trạng thái đã ghi."""
    tt = bai.get("trang_thai")
    if tt != "hieu_luc":
        return tt
    het = _ngay_hoac_none(bai.get("het_han_luc"))
    if het is None or hom_nay > het or het > hom_nay + timedelta(days=han_dung_ngay(bai.get("nguon")) + 1):
        return "het_han"
    return "hieu_luc"


def _so_cung_chieu(nhat_quan_pt: int, so_uid: int) -> int:
    return min(so_uid, (nhat_quan_pt * so_uid + 50) // 100)


def _bang_chung(x: Mapping[str, Any], d: date) -> dict:
    return {"ngay": d.isoformat(), "so_uid": x["so_uid"], "so_nhom": x["so_nhom"], "so_video": x["so_video"],
            "so_caption": x["so_caption"], "lift_pt": x["lift_pt"], "nhat_quan_pt": x["nhat_quan_pt"],
            "so_cung_chieu": _so_cung_chieu(x["nhat_quan_pt"], x["so_uid"])}


_KHOA_BANG_CHUNG = ("so_uid", "so_nhom", "so_video", "so_caption", "lift_pt", "nhat_quan_pt", "so_cung_chieu")


def _doc_bang_chung(s: Any) -> dict:
    """bang_chung từ hoc.db (agent cùng user có thể sửa) → chỉ giữ số nguyên + ngày đúng dạng."""
    try:
        d = json.loads(s) if isinstance(s, str) else {}
    except ValueError:
        log.warning("bang_chung hỏng JSON — bỏ qua")
        d = {}
    if not isinstance(d, dict):
        return {}
    ra: dict[str, Any] = {k: d[k] for k in _KHOA_BANG_CHUNG if type(d.get(k)) is int}
    if _ngay_hoac_none(d.get("ngay")) is not None:
        ra["ngay"] = d["ngay"]
    return ra


# ---------------------------------------------------------------------------------------------------------------
# Máy trạng thái thuần (§4.2)
# ---------------------------------------------------------------------------------------------------------------
def _doi(bai: Mapping[str, Any], den: str, ly_do: str, **them: Any) -> dict:
    ra = {"ma": bai["ma"], "khoa": bai["khoa"], "huong": bai["huong"], "nguon": bai["nguon"],
          "tu": bai["trang_thai"], "den": den, "ly_do": ly_do,
          "ngay_dat_lien_tiep": int(bai.get("ngay_dat_lien_tiep") or 1), "ngay_dat_cuoi": bai.get("ngay_dat_cuoi"),
          "het_han_luc": bai.get("het_han_luc"), "bang_chung": None}
    ra.update(them)
    return ra


def tinh_thay_doi(bai_hoc: list[dict], do_luong: list[DoLuong], ngay: str, bat_ngay: int, hieu_luc_toi_da: int,
                  tu_dung: frozenset[str], cam: frozenset[tuple[str, str]]) -> list[dict]:
    """Thuần (không I/O, không đổi đầu vào). Trả danh sách thay đổi cần áp, mỗi mục:
    {ma (None = dòng mới), khoa, huong, nguon, tu (None = dòng mới), den, ly_do, ngay_dat_lien_tiep, ngay_dat_cuoi,
     het_han_luc, bang_chung (None = giữ nguyên)}.

    - `bai_hoc`: các dòng bài học (chỉ dòng ung_vien/hieu_luc được xét); `bat_ngay`: số lần TỰ bật còn lại hôm nay
      (bên gọi đã trừ số lần tự bật trong NGÀY LỊCH VN hiện tại); `hieu_luc_toi_da`: trần số bài hiệu lực;
      `tu_dung`: nguồn tự dừng hôm nay; `cam`: (khoa, huong) đang bị cấm.
    - `hieu_luc_toi_da` = 0 (§4.3 "không bài nào vào phiếu"): KHÔNG gia hạn bài caption nào — chúng hết hạn tự nhiên;
      luật giữ (tắt khi hết bằng chứng / đổi chiều) và hết hạn vẫn áp như thường; không bật thêm bài nào.
    - Bài vận hành hiệu lực (§4.1b): không gia hạn, không tự tắt vì hết bằng chứng, nhưng `bang_chung` được làm mới
      (ly_do 'cap_nhat_so_do', thường ngày) mỗi lần đo của khoá có số liệu (`so_video` ≥ 1, cùng hướng) — để câu
      "{n}/{m} lần gần đây" không cũ dần suốt 28 ngày. Không phụ thuộc hạn mức (không phải gia hạn).
    - `dat`/`giu` hiệu dụng = cờ của bên đo VÀ `hoc_danh_muc.xet_nguong` (không tin cờ một mình).
    - Khoá "Chỉ báo cáo" (`ap_phieu=False`, §3.6) KHÔNG BAO GIỜ thành bài học (HT-B4 mục 1, hướng a): không tạo dòng
      mới; dòng cũ của chúng (bản trước) chỉ còn được cho hết hạn, không đếm vào `so_hieu_luc`, không được đẩy lên
      hieu_luc, không gia hạn/làm mới. Số đo của chúng vẫn ghi `do_luong` (báo cáo `canh_bao_van_hanh`)."""
    d = _kiem_ngay(ngay)
    bat_con = _kiem_so(bat_ngay, "bat_ngay", 0, 1000)
    toi_da = _kiem_so(hieu_luc_toi_da, "hieu_luc_toi_da", 0, 1000)
    tu_dung = _kiem_tu_dung(tu_dung)
    cam = frozenset(cam)
    ds = [kiem_do_luong(x) for x in do_luong]
    theo_khoa: dict[str, dict] = {}
    for x in ds:
        if x["khoa"] in theo_khoa:
            raise ThamSoLoi(f"do_luong lặp khoá {x['khoa']}")
        theo_khoa[x["khoa"]] = x
    hieu_dung: dict[str, tuple[bool, bool]] = {}
    for k, x in theo_khoa.items():
        dat, giu, _ = dm.xet_nguong(x)
        hieu_dung[k] = (x["dat"] and dat, x["giu"] and giu)
    can_lien_tiep = {"poster_view": int(dm.NGUONG["ngay_lien_tiep"]), "van_hanh": dm.NGUONG_VAN_HANH["ngay_lien_tiep"]}

    thay: list[dict] = []
    cho_bat: list[tuple[tuple, dict]] = []     # (khoá xếp ưu tiên, thay đổi) — ứng viên đủ ngày
    sau: dict[str, str] = {}                   # ma → trạng thái sau lượt này
    mo = sorted((b for b in bai_hoc if b.get("trang_thai") in TRANG_THAI_MO and b.get("khoa") in dm.DANH_MUC_HOC),
                key=lambda b: (str(b.get("tao_luc") or ""), str(b["ma"])))
    for b in mo:
        ma, khoa, huong, nguon = b["ma"], b["khoa"], b["huong"], b["nguon"]
        if trang_thai_hieu_dung(b, d) == "het_han":            # xét cả ngày tự dừng
            thay.append(_doi(b, "het_han", "het_han"))
            continue
        if not la_ap_phieu(khoa):                              # dòng cũ của khoá chỉ báo cáo: đứng yên, không đếm
            continue
        sau[ma] = b["trang_thai"]
        if nguon in tu_dung:                                   # đứng yên: không +1, không tắt, không gia hạn
            continue
        x = theo_khoa.get(khoa)
        dat, giu = hieu_dung.get(khoa, (False, False))
        cung = x is not None and x["huong"] == huong
        if b["trang_thai"] == "hieu_luc":
            if nguon == "van_hanh":                            # §4.1b: không có luật giữ, sống trọn 28 ngày
                if cung and x["so_video"] > 0:                 # chỉ làm mới số đo, không đổi hạn
                    bc = _bang_chung(x, d)
                    if bc != _doc_bang_chung(b.get("bang_chung")):
                        thay.append(_doi(b, "hieu_luc", "cap_nhat_so_do", bang_chung=bc))
                continue
            if cung and giu:
                het = (d + timedelta(days=han_dung_ngay(nguon))).isoformat()
                if toi_da > 0 and het != b.get("het_han_luc"):     # hạn mức 0 → không gia hạn (§4.3)
                    thay.append(_doi(b, "hieu_luc", "gia_han", het_han_luc=het, bang_chung=_bang_chung(x, d)))
            else:
                ly = "doi_chieu" if x is not None and x["huong"] != huong else "het_bang_chung"
                thay.append(_doi(b, "tat_tu_dong", ly))
                sau[ma] = "tat_tu_dong"
            continue
        # ung_vien
        if not (cung and dat):
            thay.append(_doi(b, "tat_tu_dong", "dut_chuoi"))
            sau[ma] = "tat_tu_dong"
            continue
        cuoi = _ngay_hoac_none(b.get("ngay_dat_cuoi"))
        so = int(b.get("ngay_dat_lien_tiep") or 1)
        if cuoi is not None and cuoi >= d:                     # đã tính ngày này rồi
            so_moi, ly, cuoi_moi = so, None, cuoi
        elif cuoi == d - timedelta(days=1):
            so_moi, ly, cuoi_moi = so + 1, "dem_chuoi", d
        else:                                                  # có ngày trống (tự dừng, máy tắt, lỗi) → đặt lại 1
            so_moi, ly, cuoi_moi = 1, "dat_lai_chuoi", d
        ch = _doi(b, "ung_vien", ly or "", ngay_dat_lien_tiep=so_moi, ngay_dat_cuoi=cuoi_moi.isoformat(),
                  bang_chung=_bang_chung(x, d))
        if so_moi >= can_lien_tiep[nguon]:
            cho_bat.append(((-so_moi, str(b.get("tao_luc") or ""), ma), ch))
        elif ly:
            thay.append(ch)

    khoa_mo = {b["khoa"] for b in mo if sau.get(b["ma"]) in TRANG_THAI_MO}
    for khoa in dm.DANH_MUC_HOC:                               # thứ tự danh mục → kết quả tất định
        x = theo_khoa.get(khoa)
        if not la_ap_phieu(khoa):                              # chỉ báo cáo → không bao giờ có dòng bai_hoc
            continue
        if x is None or x["nguon"] in tu_dung or khoa in khoa_mo or not hieu_dung[khoa][0]:
            continue
        if (khoa, x["huong"]) in cam:
            continue
        ch = {"ma": None, "khoa": khoa, "huong": x["huong"], "nguon": x["nguon"], "tu": None, "den": "ung_vien",
              "ly_do": "dat_lan_dau", "ngay_dat_lien_tiep": 1, "ngay_dat_cuoi": d.isoformat(), "het_han_luc": None,
              "bang_chung": _bang_chung(x, d)}
        if 1 >= can_lien_tiep[x["nguon"]]:
            cho_bat.append(((-1, "~", khoa), ch))
        else:
            thay.append(ch)

    so_hieu_luc = sum(1 for v in sau.values() if v == "hieu_luc")
    for _, ch in sorted(cho_bat, key=lambda t: t[0]):
        if bat_con > 0 and so_hieu_luc < toi_da:
            ch.update(den="hieu_luc", ly_do="dat_nguong_3_ngay",
                      het_han_luc=(d + timedelta(days=han_dung_ngay(ch["nguon"]))).isoformat())
            bat_con -= 1
            so_hieu_luc += 1
        elif ch["tu"] is None:
            ch["ly_do"] = "dat_lan_dau"                        # (chỉ khi ngay_lien_tiep = 1) chờ như ứng viên mới
        else:
            ch["ly_do"] = "cho_suc_chua"
        thay.append(ch)
    return thay


# ---------------------------------------------------------------------------------------------------------------
# Kho
# ---------------------------------------------------------------------------------------------------------------
def _rollback_giu_loi_goc(c: sqlite3.Connection) -> None:
    """ROLLBACK sau một lỗi trong giao dịch. SQLite có thể đã TỰ rollback (SQLITE_FULL/IOERR/BUSY…, CL15) → không còn
    giao dịch thì bỏ qua; ROLLBACK lỗi thì chỉ log, để bên gọi ném lại lỗi gốc thay vì "no transaction is active"."""
    if not c.in_transaction:
        return
    try:
        c.execute("ROLLBACK")
    except sqlite3.Error:
        log.exception("hoc.db: ROLLBACK thất bại sau một lỗi trong giao dịch — ném lại lỗi gốc")


class KhoHoc:
    def __init__(self, duong_dan: Path, bay_gio: Callable[[], datetime], *, chi_doc: bool = False) -> None:
        """Không mở/tạo file ở đây."""
        self.duong_dan = Path(duong_dan)
        self.bay_gio = bay_gio
        self.chi_doc = bool(chi_doc)
        self._cuc_bo = threading.local()

    # ---------- kết nối ----------
    def _uri(self, mode: str) -> str:
        return f"file:{quote(self.duong_dan.resolve().as_posix(), safe='/:')}?mode={mode}"

    def _ket_noi(self, tao: bool = False) -> sqlite3.Connection | None:
        """Kết nối của luồng hiện tại. chi_doc + thiếu file → None (coi như rỗng, KHÔNG tạo file)."""
        c = getattr(self._cuc_bo, "c", None)
        if c is not None:
            return c
        if self.chi_doc:
            if not self.duong_dan.is_file():
                return None
            mode = "ro"
        else:
            mode = "rwc" if tao else "rw"
        c = sqlite3.connect(self._uri(mode), uri=True, timeout=10, isolation_level=None, check_same_thread=True)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout=5000")
        if not self.chi_doc:
            c.execute("PRAGMA foreign_keys=ON")
        self._cuc_bo.c = c
        return c

    def dong(self) -> None:
        """Đóng kết nối của luồng hiện tại (luồng khác giữ kết nối riêng)."""
        c = getattr(self._cuc_bo, "c", None)
        if c is not None:
            self._cuc_bo.c = None
            c.close()

    def _kiem_ghi(self) -> None:
        if self.chi_doc:
            raise ChiDoc("KhoHoc đang mở chỉ đọc — không ghi")

    @contextmanager
    def _gd(self) -> Iterator[sqlite3.Connection]:
        """Giao dịch ghi BEGIN IMMEDIATE."""
        self._kiem_ghi()
        c = self._ket_noi()
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.execute("COMMIT")
        except BaseException:
            _rollback_giu_loi_goc(c)
            raise                                      # luôn là lỗi GỐC (lỗi ROLLBACK chỉ được log)

    @contextmanager
    def _doc(self) -> Iterator[sqlite3.Connection | None]:
        """Giao dịch đọc (ảnh chụp nhất quán). None khi chi_doc và thiếu file."""
        c = self._ket_noi()
        if c is None:
            yield None
            return
        c.execute("BEGIN")
        try:
            yield c
        except BaseException:
            _rollback_giu_loi_goc(c)
            raise
        else:
            c.execute("COMMIT")

    # ---------- thời gian ----------
    def _bay_gio_vn(self) -> datetime:
        return gio_vn(self.bay_gio())

    def _luc(self) -> str:
        return self._bay_gio_vn().isoformat(timespec="seconds")

    def _hom_nay(self) -> date:
        return self._bay_gio_vn().date()

    # ---------- schema ----------
    def mo(self) -> None:
        """Tạo/nâng schema (idempotent) rồi dọn lan_hoc/do_luong > 180 ngày. chi_doc → ChiDoc."""
        self._kiem_ghi()
        self.duong_dan.parent.mkdir(parents=True, exist_ok=True)
        c = self._ket_noi(tao=True)
        c.execute("PRAGMA journal_mode=WAL")
        with self._gd() as g:
            for cau in [x.strip() for x in SCHEMA.split(";") if x.strip()]:
                g.execute(cau)
            r = g.execute("SELECT gia_tri FROM meta WHERE khoa='schema'").fetchone()
            if r is None:
                g.execute("INSERT INTO meta(khoa, gia_tri) VALUES('schema', ?)", (PHIEN_BAN_SCHEMA,))
            elif r[0] != PHIEN_BAN_SCHEMA:
                raise RuntimeError(f"hoc.db có schema {r[0]!r}, code cần {PHIEN_BAN_SCHEMA!r} — "
                                   f"KHÔNG tự xoá/tạo lại; kiểm tay {self.duong_dan}")
        # Dọn là việc phụ, giao dịch riêng: lỗi dọn không làm hỏng mo() (CL6), nhưng luôn ghi log đủ ngữ cảnh.
        moc = (self._hom_nay() - timedelta(days=GIU_LAN_HOC_NGAY)).isoformat()
        try:
            with self._gd() as g:
                g.execute("DELETE FROM do_luong WHERE ngay < ?", (moc,))
                g.execute("DELETE FROM lan_hoc WHERE ngay < ?", (moc,))
        except sqlite3.Error:
            log.exception("hoc.db: dọn lan_hoc/do_luong cũ hơn %s thất bại — giữ nguyên, chạy tiếp", moc)

    # ---------- lần học ----------
    def bat_dau_lan(self, ngay: str, viec_id: str) -> bool:
        """True = được học ngày này (dòng mới, hoặc lần trước dang_chay/loi dở). False = đã xong/tu_dung (da_hoc)."""
        self._kiem_ghi()
        _kiem_ngay(ngay)
        if not isinstance(viec_id, str) or not _RE_VIEC_ID.fullmatch(viec_id):
            raise ThamSoLoi("viec_id phải dạng j + 14 số + 4 ký tự")
        with self._gd() as c:
            r = c.execute("SELECT trang_thai FROM lan_hoc WHERE ngay=?", (ngay,)).fetchone()
            if r is None:
                c.execute("INSERT INTO lan_hoc(ngay, viec_id, trang_thai, bat_dau_luc) VALUES(?,?, 'dang_chay', ?)",
                          (ngay, viec_id, self._luc()))
                return True
            if r[0] in ("xong", "tu_dung"):
                return False
            c.execute("UPDATE lan_hoc SET viec_id=?, trang_thai='dang_chay', ly_do='', bat_dau_luc=?, "
                      "ket_thuc_luc=NULL, so_lieu='{}' WHERE ngay=? AND trang_thai IN ('dang_chay','loi')",
                      (viec_id, self._luc(), ngay))
            return True

    def ket_thuc_lan(self, ngay: str, trang_thai: str, ly_do: str, so_lieu: dict) -> None:
        self._kiem_ghi()
        _kiem_ngay(ngay)
        if trang_thai not in TRANG_THAI_KET_THUC:
            raise ThamSoLoi(f"trang_thai phải thuộc {TRANG_THAI_KET_THUC}")
        if not isinstance(ly_do, str) or (ly_do and ly_do not in dm.LY_DO_DUNG):
            raise ThamSoLoi("ly_do phải thuộc LY_DO_DUNG")
        if trang_thai != "xong" and not ly_do:
            raise ThamSoLoi("tu_dung/loi cần ly_do")
        if not isinstance(so_lieu, Mapping):
            raise ThamSoLoi("so_lieu phải là dict")
        s = json.dumps(_kiem_so_lieu(so_lieu), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(s.encode("utf-8")) > SO_LIEU_TOI_DA_BYTE:
            raise ThamSoLoi("so_lieu quá lớn")
        with self._gd() as c:
            cur = c.execute("UPDATE lan_hoc SET trang_thai=?, ly_do=?, ket_thuc_luc=?, so_lieu=? "
                            "WHERE ngay=? AND trang_thai='dang_chay'", (trang_thai, ly_do, self._luc(), s, ngay))
            if cur.rowcount != 1:
                raise _sai_409("lan_hoc_khong_mo")

    # ---------- áp kết quả ----------
    @staticmethod
    def _cam(c: sqlite3.Connection, d: date) -> frozenset[tuple[str, str]]:
        """(khoa, huong) của dòng ĐANG hoan_tac mà ngày VN của tat_luc > d − 30 (§4.2). Chỉ đọc bai_hoc."""
        moc = d - timedelta(days=int(dm.NGUONG["cam_sau_hoan_tac_ngay"]))
        ra = set()
        for r in c.execute("SELECT ma, khoa, huong, tat_luc FROM bai_hoc WHERE trang_thai='hoan_tac'"):
            t = _ngay_vn_cua(r["tat_luc"])
            if t is None:
                log.warning("bài %s hoan_tac có tat_luc hỏng — không tính cấm", r["ma"])
                continue
            if t > moc:
                ra.add((r["khoa"], r["huong"]))
        return frozenset(ra)

    @staticmethod
    def _dong_mo(c: sqlite3.Connection) -> list[dict]:
        return [dict(r) for r in c.execute(
            "SELECT * FROM bai_hoc WHERE trang_thai IN ('ung_vien','hieu_luc') ORDER BY tao_luc, ma")]

    @staticmethod
    def _da_tu_bat(c: sqlite3.Connection, hom_nay: date) -> int:
        """Số lần TỰ bật mà THỜI ĐIỂM bật (`su_kien_hoc.luc`, đổi sang giờ VN) rơi vào ngày lịch `hom_nay` — không theo
        ngày học: học bù hôm qua sau nửa đêm rồi học hôm nay vẫn chỉ được 1 lần/ngày lịch (HT-B1b mục 7).
        Lượt bật của khoá chỉ báo cáo (dòng cũ, bản trước) không tính (HT-B4 mục 1). LEFT JOIN: sự kiện mất dòng
        bai_hoc (không thể với FK, nhưng hoc.db có thể bị sửa tay) vẫn bị tính — thà chặt hơn là bật quá trần."""
        return sum(1 for luc, khoa in c.execute(
            "SELECT s.luc, b.khoa FROM su_kien_hoc s LEFT JOIN bai_hoc b ON b.ma = s.ma "
            "WHERE s.ly_do='dat_nguong_3_ngay' AND s.boi=?", (BOI_HE_THONG,))
            if _ngay_vn_cua(luc) == hom_nay and not _la_chi_bao_cao(khoa))

    def _ghi_su_kien(self, c: sqlite3.Connection, ma: str, ngay: str, tu: str | None, den: str, boi: str,
                     ly_do: str) -> None:
        c.execute("INSERT INTO su_kien_hoc(ma, ngay, luc, tu, den, boi, ly_do) VALUES(?,?,?,?,?,?,?)",
                  (ma, ngay, self._luc(), tu, den, boi, ly_do))

    def _ma_moi(self, c: sqlite3.Connection, d: date) -> str:
        for _ in range(50):
            ma = "bh" + d.strftime("%Y%m%d") + "".join(secrets.choice(_KY_TU_MA) for _ in range(4))
            if c.execute("SELECT 1 FROM bai_hoc WHERE ma=?", (ma,)).fetchone() is None:
                return ma
        raise RuntimeError("không sinh được mã bài học mới sau 50 lần")

    def _ap_mot(self, c: sqlite3.Connection, t: dict, ngay: str) -> str:
        luc = self._luc()
        bc = json.dumps(t["bang_chung"], sort_keys=True, separators=(",", ":")) if t["bang_chung"] else None
        if t["tu"] is None:
            ma = self._ma_moi(c, date.fromisoformat(ngay))
            bat_luc = luc if t["den"] == "hieu_luc" else None
            c.execute("INSERT INTO bai_hoc(ma, khoa, huong, nguon, trang_thai, ngay_dat_lien_tiep, ngay_dat_cuoi, "
                      "bang_chung, tao_luc, bat_luc, het_han_luc) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (ma, t["khoa"], t["huong"], t["nguon"], t["den"], t["ngay_dat_lien_tiep"], t["ngay_dat_cuoi"],
                       bc or "{}", luc, bat_luc, t["het_han_luc"]))
        else:
            ma = t["ma"]
            cot = ["trang_thai=?", "ngay_dat_lien_tiep=?", "ngay_dat_cuoi=?", "het_han_luc=?"]
            ts: list[Any] = [t["den"], t["ngay_dat_lien_tiep"], t["ngay_dat_cuoi"], t["het_han_luc"]]
            if bc is not None:
                cot.append("bang_chung=?")
                ts.append(bc)
            if t["tu"] == "ung_vien" and t["den"] == "hieu_luc":
                cot += ["bat_luc=?", "tat_luc=NULL", "tat_boi=NULL", "ly_do_tat=NULL"]
                ts.append(luc)
            if t["den"] in ("tat_tu_dong", "het_han"):
                cot += ["tat_luc=?", "tat_boi=?", "ly_do_tat=?"]
                ts += [luc, BOI_HE_THONG, t["ly_do"]]
            cur = c.execute(f"UPDATE bai_hoc SET {', '.join(cot)} WHERE ma=? AND trang_thai=?", (*ts, ma, t["tu"]))
            if cur.rowcount != 1:
                raise RuntimeError(f"bài {ma} đổi trạng thái giữa chừng (CAS {t['tu']} → {t['den']} trượt)")
        self._ghi_su_kien(c, ma, ngay, t["tu"], t["den"], BOI_HE_THONG, t["ly_do"])
        return ma

    @staticmethod
    def _thay_doi_ra(t: Mapping[str, Any], boi: str | None = BOI_HE_THONG) -> dict:
        """Thay đổi → dạng ra. `t` phải đã kiểm (khoá thuộc danh mục); tên chỉ lấy từ danh mục, không bao giờ từ khoá."""
        dt = dm.DANH_MUC_HOC.get(t["khoa"])
        return {"ma": t["ma"], "khoa": t["khoa"], "ten": dt.ten if dt else None, "huong": t["huong"],
                "tu": t["tu"], "den": t["den"], "ly_do": t["ly_do"], "ten_ly_do": dm.TEN_LY_DO.get(t["ly_do"], ""),
                "boi": boi}

    @staticmethod
    def _su_kien_ra(t: Mapping[str, Any]) -> dict | None:
        """Dòng su_kien_hoc ⨝ bai_hoc (đọc từ hoc.db) → mục `thay_doi` của BaoCao, hoặc None (bỏ dòng) khi mã/khoá/
        hướng/trạng thái/lý do không thuộc enum hay danh mục. `boi` sai dạng → None."""
        ma, khoa = t["ma"], t["khoa"]
        if not isinstance(ma, str) or not dm.RE_MA_BAI_HOC.fullmatch(ma):
            return None
        dt = dm.DANH_MUC_HOC.get(khoa) if isinstance(khoa, str) else None
        if dt is None or t["huong"] not in dt.goi_y:
            return None
        if (t["tu"] is not None and t["tu"] not in TRANG_THAI_BAI) or t["den"] not in TRANG_THAI_BAI:
            return None
        if t["ly_do"] not in dm.LY_DO_CHUYEN:
            return None
        boi = t["boi"] if isinstance(t["boi"], str) and _RE_BOI.fullmatch(t["boi"]) else None
        return KhoHoc._thay_doi_ra({"ma": ma, "khoa": khoa, "huong": t["huong"], "tu": t["tu"], "den": t["den"],
                                    "ly_do": t["ly_do"]}, boi)

    def _chuan_bi(self, ngay: str, do_luong: list[DoLuong], bat_ngay: int, hieu_luc_toi_da: int,
                  tu_dung: frozenset[str]) -> tuple[date, list[dict]]:
        d = _kiem_ngay(ngay)
        _kiem_so(bat_ngay, "bat_ngay", 0, 1000)
        _kiem_so(hieu_luc_toi_da, "hieu_luc_toi_da", 0, 1000)
        _kiem_tu_dung(tu_dung)
        if not isinstance(do_luong, list):
            raise ThamSoLoi("do_luong phải là danh sách")
        return d, [kiem_do_luong(x) for x in do_luong]

    def ap_ket_qua_ngay(self, ngay: str, do_luong: list[DoLuong], bat_ngay: int, hieu_luc_toi_da: int,
                        tu_dung: frozenset[str]) -> list[dict]:
        """MỘT giao dịch BEGIN IMMEDIATE: ghi do_luong của ngày, đọc bài học + cấm TRONG giao dịch, áp máy trạng
        thái, ghi su_kien_hoc. Lỗi ở bất kỳ bước nào → rollback toàn bộ. Cần `bat_dau_lan(ngay)` trước.
        `bat_ngay` = trần tự bật trong NGÀY LỊCH VN của `bay_gio` (đếm theo thời điểm bật, không theo `ngay` học).
        `hieu_luc_toi_da` = 0 → không gia hạn bài nào (xem `tinh_thay_doi`).
        Trả các thay đổi (bỏ loại thường ngày): [{ma, khoa, ten, huong, tu, den, ly_do, ten_ly_do, boi}]."""
        self._kiem_ghi()
        d, ds = self._chuan_bi(ngay, do_luong, bat_ngay, hieu_luc_toi_da, tu_dung)
        with self._gd() as c:
            r = c.execute("SELECT trang_thai FROM lan_hoc WHERE ngay=?", (ngay,)).fetchone()
            if r is None or r[0] != "dang_chay":
                raise _sai_409("lan_hoc_khong_mo")
            c.execute("DELETE FROM do_luong WHERE ngay=?", (ngay,))
            for x in ds:
                dat, giu, thieu = dm.xet_nguong(x)
                thieu_gop = list(dict.fromkeys([*x["thieu"], *thieu]))
                c.execute("INSERT INTO do_luong(ngay, khoa, huong, nguon, so_uid, so_nhom, so_video, so_caption, "
                          "lift_pt, nhat_quan_pt, dat, giu, thieu, ds_uid) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (ngay, x["khoa"], x["huong"], x["nguon"], x["so_uid"], x["so_nhom"], x["so_video"],
                           x["so_caption"], x["lift_pt"], x["nhat_quan_pt"], int(x["dat"] and dat),
                           int(x["giu"] and giu), json.dumps(thieu_gop), json.dumps(x["ds_uid"])))
            con_bat = max(0, bat_ngay - self._da_tu_bat(c, self._hom_nay()))
            thay = tinh_thay_doi(self._dong_mo(c), ds, ngay, con_bat, hieu_luc_toi_da, frozenset(tu_dung),
                                 self._cam(c, d))
            ra = []
            for t in thay:
                t = dict(t, ma=self._ap_mot(c, t, ngay))
                if t["ly_do"] not in dm.LY_DO_THUONG_NGAY:
                    ra.append(self._thay_doi_ra(t))
            return ra

    def du_kien_ngay(self, ngay: str, do_luong: list[DoLuong], bat_ngay: int, hieu_luc_toi_da: int,
                     tu_dung: frozenset[str]) -> list[dict]:
        """Như `ap_ket_qua_ngay` nhưng CHỈ ĐỌC (dùng được với chi_doc). Dòng mới có ma = None."""
        d, ds = self._chuan_bi(ngay, do_luong, bat_ngay, hieu_luc_toi_da, tu_dung)
        with self._doc() as c:
            if c is None:
                bai, cam, da_bat = [], frozenset(), 0
            else:
                bai, cam, da_bat = self._dong_mo(c), self._cam(c, d), self._da_tu_bat(c, self._hom_nay())
        thay = tinh_thay_doi(bai, ds, ngay, max(0, bat_ngay - da_bat), hieu_luc_toi_da, frozenset(tu_dung), cam)
        return [self._thay_doi_ra(t) for t in thay if t["ly_do"] not in dm.LY_DO_THUONG_NGAY]

    # ---------- người bấm (CAS) ----------
    @staticmethod
    def _lay(c: sqlite3.Connection, ma: str) -> dict | None:
        r = c.execute("SELECT * FROM bai_hoc WHERE ma=?", (ma,)).fetchone()
        return dict(r) if r else None

    def _ly_do_khong_bat_lai(self, c: sqlite3.Connection, bai: Mapping[str, Any], hom_nay: date, bat_ngay: int,
                             hieu_luc_toi_da: int) -> SaiTrangThaiHoc | None:
        """5 điều kiện Bật lại theo ĐÚNG thứ tự §4.2; None = bật lại được. Dòng của khoá chỉ báo cáo (bản trước) không
        bao giờ bật lại được (HT-B4 mục 1) → câu cố định `khong_the_bat_lai`; chúng cũng không chiếm chỗ hiệu lực."""
        tt = trang_thai_hieu_dung(bai, hom_nay)
        if not la_ap_phieu(bai.get("khoa")):
            return _sai_409("khong_the_bat_lai")
        if not ((tt in ("tat_tu_dong", "het_han") and bai.get("bat_luc")) or tt == "hoan_tac"):
            return _sai_409("khong_the_bat_lai")
        if tt == "hoan_tac":
            den = self._bat_lai_den(bai)
            if den is None or hom_nay > den:
                return _sai_409("qua_han_bat_lai")
        if c.execute("SELECT 1 FROM bai_hoc WHERE khoa=? AND ma<>? AND trang_thai IN ('ung_vien','hieu_luc')",
                     (bai["khoa"], bai["ma"])).fetchone():
            return _sai_409("trung_dong_mo")
        if self._dich_bat_lai(bai, tt) == "hieu_luc":
            so = sum(1 for r in c.execute("SELECT * FROM bai_hoc WHERE trang_thai='hieu_luc' AND ma<>?", (bai["ma"],))
                     if la_ap_phieu(r["khoa"]) and trang_thai_hieu_dung(dict(r), hom_nay) == "hieu_luc")
            if so >= hieu_luc_toi_da:
                return _sai_409("du_hieu_luc", so=hieu_luc_toi_da)
        if bat_ngay <= 0:
            return _sai_409("tat_tu_ap_dung")
        return None

    @staticmethod
    def _dich_bat_lai(bai: Mapping[str, Any], tt: str) -> str:
        return "ung_vien" if tt == "hoan_tac" and not bai.get("bat_luc") else "hieu_luc"

    @staticmethod
    def _bat_lai_den(bai: Mapping[str, Any]) -> date | None:
        t = _ngay_vn_cua(bai.get("tat_luc"))
        return None if t is None else t + timedelta(days=int(dm.NGUONG["bat_lai_sau_hoan_tac_ngay"]))

    def hoan_tac(self, ma: str, boi: str, *, bat_ngay: int, hieu_luc_toi_da: int) -> dict:
        """CAS ung_vien|hieu_luc (hiệu dụng) → hoan_tac. 404 KhongCoBaiHoc (kể cả dòng sai dạng mà API không hiện) ·
        409 SaiTrangThaiHoc. Trả BaiHocRa; `bat_ngay`/`hieu_luc_toi_da` (bắt buộc, hạn mức THẬT đang áp dụng) chỉ dùng
        để tính `co_the_bat_lai` của bản trả về."""
        self._kiem_ghi()
        ma = _kiem_ma(ma)
        boi = _kiem_boi(boi)
        _kiem_so(bat_ngay, "bat_ngay", 0, 1000)
        _kiem_so(hieu_luc_toi_da, "hieu_luc_toi_da", 0, 1000)
        hom_nay = self._hom_nay()
        with self._gd() as c:
            bai = self._lay(c, ma)
            if bai is None or _dong_bai_hop_le(bai) is None:
                raise KhongCoBaiHoc()
            tt = trang_thai_hieu_dung(bai, hom_nay)
            if tt not in TRANG_THAI_MO:
                raise _sai_409("khong_con_hieu_luc")
            cur = c.execute("UPDATE bai_hoc SET trang_thai='hoan_tac', tat_luc=?, tat_boi=?, ly_do_tat='nguoi_hoan_tac'"
                            " WHERE ma=? AND trang_thai=?", (self._luc(), boi, ma, bai["trang_thai"]))
            if cur.rowcount != 1:
                raise _sai_409("khong_con_hieu_luc")
            self._ghi_su_kien(c, ma, hom_nay.isoformat(), tt, "hoan_tac", boi, "nguoi_hoan_tac")
        return self._mot_ra(ma, bat_ngay, hieu_luc_toi_da)

    def bat_lai(self, ma: str, boi: str, bat_ngay: int, hieu_luc_toi_da: int) -> dict:
        """Bật lại (quyết định (i) + Q8 b): tat_tu_dong/het_han có bat_luc → hieu_luc; hoan_tac ≤ 7 ngày → hieu_luc
        (nếu từng hiệu lực) hoặc ung_vien (giữ chuỗi). Mọi nhánh xoá tat_luc/tat_boi/ly_do_tat → dòng hết gây cấm.
        404 KhongCoBaiHoc (kể cả dòng sai dạng mà API không hiện) · 409 SaiTrangThaiHoc (.loi = 1 trong 5 câu §4.2).
        Không tính vào bat_ngay. `bat_ngay`/`hieu_luc_toi_da` = hạn mức THẬT, dùng cho cả điều kiện lẫn BaiHocRa trả về."""
        self._kiem_ghi()
        ma = _kiem_ma(ma)
        boi = _kiem_boi(boi)
        _kiem_so(bat_ngay, "bat_ngay", 0, 1000)
        _kiem_so(hieu_luc_toi_da, "hieu_luc_toi_da", 0, 1000)
        hom_nay = self._hom_nay()
        with self._gd() as c:
            bai = self._lay(c, ma)
            if bai is None or _dong_bai_hop_le(bai) is None:
                raise KhongCoBaiHoc()
            loi = self._ly_do_khong_bat_lai(c, bai, hom_nay, bat_ngay, hieu_luc_toi_da)
            if loi is not None:
                raise loi
            tt = trang_thai_hieu_dung(bai, hom_nay)
            den = self._dich_bat_lai(bai, tt)
            if den == "hieu_luc":
                het = (hom_nay + timedelta(days=han_dung_ngay(bai["nguon"]))).isoformat()
                cur = c.execute("UPDATE bai_hoc SET trang_thai='hieu_luc', bat_luc=?, het_han_luc=?, ngay_dat_cuoi=?, "
                                "tat_luc=NULL, tat_boi=NULL, ly_do_tat=NULL WHERE ma=? AND trang_thai=?",
                                (self._luc(), het, hom_nay.isoformat(), ma, bai["trang_thai"]))
            else:
                cur = c.execute("UPDATE bai_hoc SET trang_thai='ung_vien', tat_luc=NULL, tat_boi=NULL, "
                                "ly_do_tat=NULL WHERE ma=? AND trang_thai=?", (ma, bai["trang_thai"]))
            if cur.rowcount != 1:
                raise _sai_409("khong_the_bat_lai")
            self._ghi_su_kien(c, ma, hom_nay.isoformat(), tt, den, boi, "nguoi_bat_lai")
        return self._mot_ra(ma, bat_ngay, hieu_luc_toi_da)

    # ---------- đọc ----------
    def goi_y_hieu_luc(self, hieu_luc_toi_da: int) -> list[dict]:
        """Bài học được vào phiếu: hieu_luc HIỆU DỤNG (het_han_luc ≥ hôm nay theo bay_gio), dòng hợp lệ, khoá ap_phieu.
        Mỗi mục là dữ liệu cấu trúc cho `hoc_danh_muc.render_goi_y` — không có chữ tự do.

        `hieu_luc_toi_da` (bắt buộc) = hạn mức THẬT `hoc_hieu_luc_toi_da`: ≤ 0 → [] không đọc DB (§4.3 "không bài nào
        vào phiếu"); > 0 → tối đa N bài, thứ tự ổn định: bật sớm nhất trước (`bat_luc` tăng dần, rồi `ma`) — bài mới
        bật không đẩy bài đang dùng ra khỏi phiếu. Sai kiểu (bool, float, chuỗi) → ThamSoLoi."""
        if type(hieu_luc_toi_da) is not int:
            raise ThamSoLoi("hieu_luc_toi_da phải là số nguyên")
        if hieu_luc_toi_da <= 0:
            return []
        hom_nay = self._hom_nay()
        with self._doc() as c:
            if c is None:
                return []
            rows = self._chon_goi_y(c, hom_nay, hieu_luc_toi_da)
        return [self._muc_goi_y(r) for r in rows]

    @staticmethod
    def _chon_goi_y(c: sqlite3.Connection, hom_nay: date, hieu_luc_toi_da: int) -> list[dict]:
        """Các dòng bai_hoc mà `goi_y_hieu_luc` trả (MỘT nguồn sự thật cho cả phiếu lẫn `vao_phieu` của báo cáo):
        hieu_luc hiệu dụng, dòng hợp lệ, khoá ap_phieu, ghép được câu gợi ý (HT-B4b mục 2: bang_chung hỏng làm
        `ghep_goi_y` trả None thì phiếu sẽ bỏ bài đó → không tính vào phiếu, không chiếm chỗ hạn mức), thứ tự
        `bat_luc` rồi `ma`, tối đa `hieu_luc_toi_da`."""
        if hieu_luc_toi_da <= 0:
            return []
        ra: list[dict] = []
        for x in c.execute("SELECT * FROM bai_hoc WHERE trang_thai='hieu_luc' AND het_han_luc >= ? "
                           "ORDER BY bat_luc, ma", (hom_nay.isoformat(),)):
            r = dict(x)
            dt = _dong_bai_hop_le(r)
            if dt is None or not dt.ap_phieu or trang_thai_hieu_dung(r, hom_nay) != "hieu_luc":
                continue
            if dm.ghep_goi_y(KhoHoc._muc_goi_y(r)) is None:
                log.warning("bài %s có bang_chung không ghép được câu gợi ý — không vào phiếu", r["ma"])
                continue
            ra.append(r)
            if len(ra) >= hieu_luc_toi_da:
                break
        return ra

    @classmethod
    def _ma_vao_phieu(cls, c: sqlite3.Connection, hom_nay: date, bat_ngay: int, hieu_luc_toi_da: int) -> frozenset:
        """Mã các bài mà phiếu phan_tich_uid sẽ nhận, theo ĐÚNG cầu dao `phieu.lay_goi_y_hoc` (phieu.py:142-151):
        n = 0 nếu bat_ngay == 0, ngược lại hieu_luc_toi_da; n ≤ 0 → không bài nào; còn lại = `goi_y_hieu_luc(n)`."""
        n = 0 if bat_ngay == 0 else hieu_luc_toi_da
        return frozenset(r["ma"] for r in cls._chon_goi_y(c, hom_nay, n))

    @staticmethod
    def _muc_goi_y(r: Mapping[str, Any]) -> dict:
        bc = _doc_bang_chung(r.get("bang_chung"))
        return {"ma": r["ma"], "khoa": r["khoa"], "huong": r["huong"], "nguon": r["nguon"], "trang_thai": "hieu_luc",
                "het_han_luc": r.get("het_han_luc"), "lift_pt": bc.get("lift_pt"), "so_uid": bc.get("so_uid"),
                "so_cung_chieu": bc.get("so_cung_chieu"), "so_viec": bc.get("so_video")}

    def ghi_ap_dung(self, ds_ma: list[str], viec_id: str, uid: str) -> None:
        """Ghi vết bài học đã vào phiếu của việc `viec_id` (UID `uid`). Mã không có trong kho → bỏ (log)."""
        self._kiem_ghi()
        if not isinstance(ds_ma, list) or not all(isinstance(m, str) and dm.RE_MA_BAI_HOC.fullmatch(m) for m in ds_ma):
            raise ThamSoLoi("ds_ma phải là danh sách mã bài học")
        if not isinstance(viec_id, str) or not _RE_VIEC_ID.fullmatch(viec_id):
            raise ThamSoLoi("viec_id sai dạng")
        if not isinstance(uid, str) or not _RE_UID.fullmatch(uid):
            raise ThamSoLoi("uid phải là 19 chữ số")
        ds = list(dict.fromkeys(ds_ma))
        if not ds:
            return
        with self._gd() as c:
            co = {r[0] for r in c.execute(f"SELECT ma FROM bai_hoc WHERE ma IN ({','.join('?' * len(ds))})", ds)}
            for ma in ds:
                if ma not in co:
                    log.warning("ghi_ap_dung: bỏ mã %s không có trong hoc.db (việc %s)", ma, viec_id)
                    continue
                c.execute("INSERT OR IGNORE INTO ap_dung(ma, viec_id, uid, luc) VALUES(?,?,?,?)",
                          (ma, viec_id, uid, self._luc()))

    def ghi_tuan_thu(self, ngay: str, ds: dict[str, dict]) -> None:
        """Lưu số tuân thủ (§3.6) mỗi bài: `ds` = {mã bài học: {khoá: số nguyên ≥ 0}}, bộ khoá ĐÚNG bằng
        `hoc_danh_muc.KHOA_TUAN_THU[nguồn của bài]` (xem `kiem_tuan_thu`). `ngay` = ngày tính (YYYY-MM-DD), lưu kèm.
        Ghi đè bản cũ của bài. Mã không có trong kho → bỏ (log). Sai dạng/kiểu/khoá, hoặc bộ khoá khác nguồn của bài
        → ThamSoLoi và KHÔNG ghi mục nào (một giao dịch). `chi_doc` → ChiDoc. `ds` rỗng → không làm gì."""
        self._kiem_ghi()
        _kiem_ngay(ngay)
        if not isinstance(ds, Mapping):
            raise ThamSoLoi("ds phải là dict {mã bài học: số tuân thủ}")
        sach: dict[str, tuple[str, dict[str, int]]] = {}
        for ma, so in ds.items():
            if not isinstance(ma, str) or not dm.RE_MA_BAI_HOC.fullmatch(ma):
                raise ThamSoLoi("ds: mã bài học sai dạng")
            sach[ma] = kiem_tuan_thu(so)
        if not sach:
            return
        with self._gd() as c:
            for ma, (nguon, so) in sach.items():
                r = c.execute("SELECT nguon FROM bai_hoc WHERE ma=?", (ma,)).fetchone()
                if r is None:
                    log.warning("ghi_tuan_thu: bỏ mã %s không có trong hoc.db", ma)
                    continue
                if r[0] != nguon:
                    raise ThamSoLoi(f"ds: bài {ma} cần bộ khoá tuân thủ của nguồn khác")
                c.execute("UPDATE bai_hoc SET tuan_thu=?, tuan_thu_ngay=? WHERE ma=?",
                          (json.dumps(so, sort_keys=True, separators=(",", ":")), ngay, ma))

    def su_kien(self, ma: str) -> list[dict]:
        """Lịch sử chuyển trạng thái của một bài học (cũ → mới)."""
        ma = _kiem_ma(ma)
        with self._doc() as c:
            if c is None:
                return []
            return [dict(r) for r in c.execute("SELECT * FROM su_kien_hoc WHERE ma=? ORDER BY id", (ma,))]

    def _ra(self, c: sqlite3.Connection, r: Mapping[str, Any], hom_nay: date, bat_ngay: int, hieu_luc_toi_da: int,
            so_sp: Mapping[str, int], vao: frozenset) -> dict | None:
        """Dòng bai_hoc → BaiHocRa (§3.8), hoặc None khi dòng sai dạng (`_dong_bai_hop_le`) — bên gọi bỏ dòng.
        Chữ chỉ lấy từ danh mục; mọi trường khác qua regex/enum/kiểu, sai → null (HT-B1b mục 1).
        `vao` = `_ma_vao_phieu(...)`; `vao_phieu` (HT-B4 mục 2) = trạng thái hiệu dụng hieu_luc VÀ mã thuộc `vao`."""
        dt = _dong_bai_hop_le(r)
        if dt is None:
            log.warning("hoc.db: bỏ một dòng bai_hoc sai dạng khi đọc (khoá/mã/hướng/nguồn/trạng thái lạ)")
            return None
        tt = trang_thai_hieu_dung(r, hom_nay)
        ly_do_tat = r.get("ly_do_tat") if r.get("ly_do_tat") in dm.LY_DO_CHUYEN else None
        if tt == "het_han" and r["trang_thai"] == "hieu_luc":
            ly_do_tat = "het_han"                              # hết hạn tính lúc đọc, chưa ghi
        tat_boi = r.get("tat_boi") if isinstance(r.get("tat_boi"), str) and _RE_BOI.fullmatch(r["tat_boi"]) else None
        bat_lai_den = self._bat_lai_den(r) if tt == "hoan_tac" else None
        return {
            "ma": r["ma"], "khoa": r["khoa"], "ten": dt.ten, "goi_y": dm.ghep_goi_y(self._muc_goi_y(r)) or "",
            "huong": r["huong"], "nguon": r["nguon"], "trang_thai": tt,
            "ngay_dat_lien_tiep": _int_hoac(r.get("ngay_dat_lien_tiep"), None),
            "bat_luc": _luc_hoac_none(r.get("bat_luc")),
            "het_han_luc": r.get("het_han_luc") if _ngay_hoac_none(r.get("het_han_luc")) else None,
            "tat_luc": _luc_hoac_none(r.get("tat_luc")), "tat_boi": tat_boi, "ly_do_tat": ly_do_tat,
            "ten_ly_do_tat": dm.TEN_LY_DO.get(ly_do_tat, "") if ly_do_tat else None,
            "bang_chung": _doc_bang_chung(r.get("bang_chung")), "so_sp_da_ap": int(so_sp.get(r["ma"], 0)),
            "tuan_thu": _doc_tuan_thu(r.get("tuan_thu"), r.get("tuan_thu_ngay"), dt.nguon),
            "co_the_hoan_tac": tt in TRANG_THAI_MO,
            "co_the_bat_lai": self._ly_do_khong_bat_lai(c, r, hom_nay, bat_ngay, hieu_luc_toi_da) is None,
            "bat_lai_den": bat_lai_den.isoformat() if bat_lai_den else None,
            "vao_phieu": tt == "hieu_luc" and r["ma"] in vao,
        }

    @staticmethod
    def _so_sp(c: sqlite3.Connection) -> dict[str, int]:
        return {r[0]: r[1] for r in c.execute("SELECT ma, COUNT(DISTINCT uid) FROM ap_dung GROUP BY ma")}

    def _mot_ra(self, ma: str, bat_ngay: int, hieu_luc_toi_da: int) -> dict:
        """BaiHocRa của một mã. Không có file (chi_doc), không có dòng, hoặc dòng sai dạng → KhongCoBaiHoc (404)."""
        hom_nay = self._hom_nay()
        with self._doc() as c:
            r = self._lay(c, ma) if c is not None else None
            ra = self._ra(c, r, hom_nay, bat_ngay, hieu_luc_toi_da, self._so_sp(c),
                          self._ma_vao_phieu(c, hom_nay, bat_ngay, hieu_luc_toi_da)) if r else None
        if ra is None:
            raise KhongCoBaiHoc()
        return ra

    def ds_bai_hoc(self, gioi_han: int = 50, *, bat_ngay: int, hieu_luc_toi_da: int) -> list[dict]:
        """BaiHocRa mới nhất trước (dòng sai dạng bị bỏ). `bat_ngay`/`hieu_luc_toi_da` (bắt buộc, hạn mức THẬT đang
        áp dụng) chỉ dùng để tính `co_the_bat_lai`."""
        gioi_han = max(1, min(_kiem_so(gioi_han, "gioi_han", -10**9, 10**9), 200))
        _kiem_so(bat_ngay, "bat_ngay", 0, 1000)
        _kiem_so(hieu_luc_toi_da, "hieu_luc_toi_da", 0, 1000)
        hom_nay = self._hom_nay()
        with self._doc() as c:
            if c is None:
                return []
            so_sp = self._so_sp(c)
            vao = self._ma_vao_phieu(c, hom_nay, bat_ngay, hieu_luc_toi_da)
            rows = c.execute("SELECT * FROM bai_hoc ORDER BY tao_luc DESC, rowid DESC LIMIT ?", (gioi_han,)).fetchall()
            ra = [self._ra(c, dict(r), hom_nay, bat_ngay, hieu_luc_toi_da, so_sp, vao) for r in rows]
        return [x for x in ra if x is not None]

    # ---------- báo cáo ----------
    @staticmethod
    def _lan_ra(r: Mapping[str, Any] | None, so_lieu: Mapping[str, Any]) -> dict:
        if r is None:
            return {"trang_thai": "khong_chay", "ly_do": "", "ten_ly_do": "", "viec_id": None, "bat_dau_luc": None,
                    "ket_thuc_luc": None, "du_lieu_moi": False}
        ly_do = r["ly_do"] if r["ly_do"] in dm.LY_DO_DUNG else ""
        viec_id = r["viec_id"]
        return {"trang_thai": r["trang_thai"] if r["trang_thai"] in TRANG_THAI_LAN else "loi", "ly_do": ly_do,
                "ten_ly_do": dm.TEN_LY_DO.get(ly_do, ""),
                "viec_id": viec_id if isinstance(viec_id, str) and _RE_VIEC_ID.fullmatch(viec_id) else None,
                "bat_dau_luc": _luc_hoac_none(r["bat_dau_luc"]), "ket_thuc_luc": _luc_hoac_none(r["ket_thuc_luc"]),
                "du_lieu_moi": so_lieu.get("du_lieu_moi") is True}

    @staticmethod
    def _so_lieu(r: Mapping[str, Any] | None) -> dict:
        if r is None:
            return {}
        try:
            d = json.loads(r["so_lieu"] or "{}")
        except ValueError:
            log.warning("lan_hoc %s: so_lieu hỏng JSON — coi như rỗng", r["ngay"])
            return {}
        return d if isinstance(d, dict) else {}

    def bao_cao(self, ngay: str | None, *, bat_ngay: int, hieu_luc_toi_da: int) -> dict:
        """BaoCao §3.8 — phần lấy được từ hoc.db. `ngay=None` → lần học mới nhất có ngày đúng dạng (chưa có lần nào →
        KhongCoBaiHoc "chưa có lần học nào", API trả 404). Ngày chưa chạy → lan.trang_thai = 'khong_chay'. Trạng thái
        bài học là trạng thái HIỆU DỤNG theo `bay_gio`. `bat_ngay`/`hieu_luc_toi_da` (bắt buộc, hạn mức THẬT) dùng để
        tính `co_the_bat_lai`, `vao_phieu` của từng bài, và trả lại nguyên ở `han_muc` (HT-B4 mục 2). Mọi chữ đọc từ
        hoc.db đều qua enum/danh mục/regex: sai → null hoặc bỏ cả dòng."""
        if ngay is not None:
            _kiem_ngay(ngay)
        _kiem_so(bat_ngay, "bat_ngay", 0, 1000)
        _kiem_so(hieu_luc_toi_da, "hieu_luc_toi_da", 0, 1000)
        hom_nay = self._hom_nay()
        with self._doc() as c:
            if ngay is None:
                ngay = next((r[0] for r in c.execute("SELECT ngay FROM lan_hoc ORDER BY ngay DESC")
                             if _ngay_hoac_none(r[0]) is not None), None) if c else None
                if ngay is None:
                    raise KhongCoBaiHoc(dm.TEN_LY_DO["chua_co_lan_hoc"])
            d = _kiem_ngay(ngay)
            if c is None:
                lan, thay, do_luong, bai, cua_so = None, [], [], [], []
            else:
                lan = c.execute("SELECT * FROM lan_hoc WHERE ngay=?", (ngay,)).fetchone()
                thay = [dict(x) for x in c.execute(
                    "SELECT s.ma, s.tu, s.den, s.boi, s.ly_do, b.khoa, b.huong FROM su_kien_hoc s "
                    "LEFT JOIN bai_hoc b ON b.ma = s.ma WHERE s.ngay=? ORDER BY s.id", (ngay,))]
                do_luong = [dict(x) for x in c.execute("SELECT * FROM do_luong WHERE ngay=? ORDER BY rowid", (ngay,))]
                so_sp = self._so_sp(c)
                vao = self._ma_vao_phieu(c, hom_nay, bat_ngay, hieu_luc_toi_da)
                bai = [self._ra(c, dict(x), hom_nay, bat_ngay, hieu_luc_toi_da, so_sp, vao)
                       for x in c.execute("SELECT * FROM bai_hoc ORDER BY tao_luc DESC, rowid DESC")]
                cua_so = [dict(x) for x in c.execute("SELECT * FROM lan_hoc WHERE ngay BETWEEN ? AND ?",
                                                     ((d - timedelta(days=6)).isoformat(), ngay))]
        so_lieu = self._so_lieu(lan)
        bai = [b for b in bai if b is not None]
        # dòng cũ của khoá chỉ báo cáo (HT-B4 mục 1): không vào ds "đang dùng"/ứng viên của báo cáo
        dang_mo = [b for b in bai if la_ap_phieu(b["khoa"])]
        dl_ra = [x for x in map(_do_luong_ra, do_luong) if x is not None]
        thay_ra = [x for x in map(self._su_kien_ra, thay) if x is not None]
        da_tat = sorted((b for b in bai if b["trang_thai"] in ("tat_tu_dong", "het_han", "hoan_tac")),
                        key=lambda b: b["tat_luc"] or b["het_han_luc"] or "", reverse=True)[:DA_TAT_TOI_DA]
        return {
            "ngay": ngay,
            # hạn mức THẬT đang áp dụng (HT-B4 mục 2) — web hiện "tắt tự áp dụng"/"đã hạ trần" từ đây
            "han_muc": {"bat_ngay": bat_ngay, "hieu_luc_toi_da": hieu_luc_toi_da},
            "lan": self._lan_ra(lan, so_lieu),
            "nguon": _lam_sach_nguon(so_lieu),
            "thay_doi": [t for t in thay_ra if t["ly_do"] not in dm.LY_DO_THUONG_NGAY],
            "hieu_luc": [b for b in dang_mo if b["trang_thai"] == "hieu_luc"],
            "ung_vien": [b for b in dang_mo if b["trang_thai"] == "ung_vien"],
            "da_tat": da_tat,
            "do_luong": dl_ra,
            "canh_bao_van_hanh": [
                {"khoa": x["khoa"], "ten": x["ten"], "so_lan": x["so_uid"], "so_viec": x["so_video"],
                 "cua_so_ngay": dm.NGUONG_VAN_HANH["cua_so_ngay"]}
                for x in dl_ra if x["nguon"] == "van_hanh" and x["so_uid"] > 0],
            "chi_so_7_ngay": _chi_so_7_ngay(cua_so, self._so_lieu),
            "nguong": {**{k: (list(v) if isinstance(v, tuple) else v) for k, v in dm.NGUONG.items()},
                       "van_hanh": dict(dm.NGUONG_VAN_HANH)},
        }


# ---------------------------------------------------------------------------------------------------------------
# Báo cáo — làm sạch dữ liệu đọc từ hoc.db (agent cùng user có thể sửa file)
# ---------------------------------------------------------------------------------------------------------------
_SO_DO_LUONG_RA = (("so_uid", 0, dm.SO_TOI_DA), ("so_nhom", 0, dm.SO_TOI_DA), ("so_caption", 0, dm.SO_TOI_DA),
                   ("so_video", 0, dm.SO_TOI_DA), ("lift_pt", -100, dm.SO_TOI_DA), ("nhat_quan_pt", 0, 100))


def _do_luong_ra(x: Mapping[str, Any]) -> dict | None:
    """Dòng do_luong đọc từ hoc.db → mục `do_luong` của BaoCao, hoặc None (bỏ dòng) khi khoá ngoài danh mục, nguồn/
    hướng không khớp, số sai kiểu/khoảng, `dat` không phải 0/1. Tên chỉ lấy từ danh mục."""
    khoa = x["khoa"]
    dt = dm.DANH_MUC_HOC.get(khoa) if isinstance(khoa, str) else None
    if dt is None or x["nguon"] != dt.nguon or x["huong"] not in dt.goi_y:
        return None
    if any(type(x[ten]) is not int or not (lo <= x[ten] <= hi) for ten, lo, hi in _SO_DO_LUONG_RA):
        return None
    if type(x["dat"]) is not int or x["dat"] not in (0, 1):
        return None
    try:
        tho = json.loads(x["thieu"])
        thieu = [t for t in tho if isinstance(t, str) and _RE_MA_NGAN.fullmatch(t)] if isinstance(tho, list) else []
    except (ValueError, TypeError, RecursionError):
        thieu = []
    return {"khoa": khoa, "ten": dt.ten, "nguon": dt.nguon, "huong": x["huong"],
            **{ten: x[ten] for ten, _, _ in _SO_DO_LUONG_RA}, "dat": x["dat"] == 1, "thieu": thieu}


def _int_hoac(v: Any, mac_dinh: int | None) -> int | None:
    return v if type(v) is int and 0 <= v <= dm.SO_TOI_DA else mac_dinh


def _lam_sach_nguon(so_lieu: Mapping[str, Any]) -> dict:
    """so_lieu.nguon (do HT-B2 ghi qua ket_thuc_lan) → khối `nguon` của BaoCao, chỉ giữ giá trị đúng kiểu/enum."""
    ng = so_lieu.get("nguon") if isinstance(so_lieu.get("nguon"), dict) else {}
    pv = ng.get("poster_view") if isinstance(ng.get("poster_view"), dict) else {}
    vh = ng.get("van_hanh") if isinstance(ng.get("van_hanh"), dict) else {}
    q = pv.get("quet_hom_nay") if isinstance(pv.get("quet_hom_nay"), dict) else {}
    ly_do_q = q.get("ly_do") if q.get("ly_do") in dm.LY_DO_QUET else None
    viec_q = q.get("viec_id") if isinstance(q.get("viec_id"), str) and _RE_VIEC_ID.fullmatch(q["viec_id"]) else None
    ngay_moi = pv.get("ngay_moi_nhat") if _ngay_hoac_none(pv.get("ngay_moi_nhat")) else None

    def _bo(ten: str) -> int:
        return _int_hoac(pv.get(ten), None) or _int_hoac(so_lieu.get(ten), 0) or 0

    return {
        "poster_view": {
            "trang_thai": pv.get("trang_thai") if pv.get("trang_thai") in ("ok", "cu", "thieu", "lech", "loi")
            else "loi",
            "ngay_moi_nhat": ngay_moi, "so_ngay_cu": _int_hoac(pv.get("so_ngay_cu"), None),
            "so_video_hop_le": _int_hoac(pv.get("so_video_hop_le"), 0), "so_uid": _int_hoac(pv.get("so_uid"), 0),
            "so_lan_do_ngay": _int_hoac(pv.get("so_lan_do_ngay"), 0),
            "trung_vi_lan_do_7_ngay": _int_hoac(pv.get("trung_vi_lan_do_7_ngay"), 0),
            "bo_caption_ngoai_kho": _bo("bo_caption_ngoai_kho"), "bo_mo_ho": _bo("bo_mo_ho"),
            "quet_hom_nay": {
                "trang_thai": q.get("trang_thai") if q.get("trang_thai") in (
                    "ok", "loi", "cho", "dang_chay", "chua_tao", "huy") else "chua_tao",
                "ly_do": ly_do_q, "ten_ly_do": dm.TEN_LY_DO[ly_do_q] if ly_do_q else None, "viec_id": viec_q},
        },
        "van_hanh": {"trang_thai": vh.get("trang_thai") if vh.get("trang_thai") in ("ok", "loi") else "loi",
                     "so_viec": _int_hoac(vh.get("so_viec"), 0), "so_loi": _int_hoac(vh.get("so_loi"), 0)},
        "sua_tay": {"trang_thai": "chua_co_nguon"},
    }


def _chi_so_7_ngay(cua_so: list[dict], doc_so_lieu: Callable[[Mapping[str, Any]], dict]) -> dict:
    """Từ lan_hoc 7 ngày (tính cả ngày báo cáo). `ngay_may_bat` = số ngày có lần học (bộ học chỉ chạy khi máy bật);
    `ngay_quet_ok` đọc từ so_lieu.nguon.poster_view.quet_hom_nay.trang_thai do HT-B2 ghi."""
    ra = {"ngay_may_bat": 0, "ngay_quet_ok": 0, "ngay_hoc_chay": 0, "ngay_du_lieu_moi": 0}
    for r in cua_so:
        sl = doc_so_lieu(r)
        ra["ngay_may_bat"] += 1
        if r["trang_thai"] in ("xong", "tu_dung"):
            ra["ngay_hoc_chay"] += 1
        if r["trang_thai"] == "xong" and sl.get("du_lieu_moi") is True:
            ra["ngay_du_lieu_moi"] += 1
        if _lam_sach_nguon(sl)["poster_view"]["quet_hom_nay"]["trang_thai"] == "ok":
            ra["ngay_quet_ok"] += 1
    return ra
