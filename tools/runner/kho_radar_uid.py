"""Kho SQLite `radar_uid.db` của Radar UID (docs/radar-uid.md §4, §6.2-§6.5, §7).

Nguyên tắc (theo mẫu `kho_hoc.py`):
- Import và `KhoRadarUid(...)` KHÔNG mở/tạo file. Schema chỉ tạo/nâng trong `mo()`. Kết nối thường mở `mode=rw`
  (không tự tạo file); `chi_doc=True` mở `mode=ro`, thiếu file thì coi như rỗng, mọi hàm ghi ném `ChiDoc`.
- Mỗi luồng một kết nối (`threading.local`), `isolation_level=None`, mọi ghi trong `BEGIN IMMEDIATE`.
- "Hôm nay" luôn lấy qua `bay_gio` tiêm vào (giờ VN).
- Id (UID sản phẩm, video_id) luôn là chuỗi/TEXT, không bao giờ qua số.
- Không lưu token, không lưu `update_time` của video. `ghi_token` chỉ nhận mã ngắn [a-z0-9_].
- File tự đủ: không import `radar_uid_tinh`.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import quote

from .kieu import ThamSoLoi, gio_vn

log = logging.getLogger(__name__)

PHIEN_BAN_SCHEMA = "3"
GIU_CHUP_NGAY = 90                          # mo() dọn chup_video (và chup_uid tương ứng) cũ hơn chừng này
GOC_TOI_DA = 2
TUONG_TU_TOI_DA = 10                        # mỗi nhóm, gồm cả UID đang ghim
THEM_TAY_TOI_DA = 3
UID_TOI_DA = 24                             # UID khác nhau toàn DB, trạng thái ≠ loai/ngung
SO_LAN_THU_TOI_DA = 2                       # chup_uid.so_lan_thu tối đa mỗi (uid, ngày) — §6.5
TEN_TOI_DA = 200

RE_UID = re.compile(r"^\d{19}\Z", re.ASCII)
# Chỉ ảnh bìa CDN EchoTik mới được lưu (chống URL tuỳ ý/XSS). Dùng `fullmatch` để `$` không nhận xuống dòng cuối.
RE_ANH = re.compile(r"^https://cdn\.echotik\.live/[A-Za-z0-9._/-]{1,300}$")
_RE_NGAY = re.compile(r"^\d{4}-\d{2}-\d{2}\Z", re.ASCII)
_RE_LUC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:[+-]\d{2}:\d{2}|Z)?\Z", re.ASCII)
_RE_BOI = re.compile(r"^[\w.@\-]{1,64}\Z")
_RE_MA = re.compile(r"^[a-z0-9_]{1,40}\Z", re.ASCII)
_RE_MA_RONG = re.compile(r"^[a-z0-9_]{0,40}\Z", re.ASCII)
_RE_CHE_DO = re.compile(r"^[a-z_\-]{1,20}\Z", re.ASCII)
_RE_VIEC_ID = re.compile(r"^[\w\-]{1,40}\Z", re.ASCII)
_RE_DIEU_KHIEN = re.compile(r"[\x00-\x1f\x7f]")

TRANG_THAI_NHOM = ("cho_tim", "dang_tim", "da_tim", "loi_tim", "ngung")
TRANG_THAI_TOKEN = ("ok", "thieu", "het_han", "chua_kiem")
TRANG_THAI_KET_THUC = ("xong", "tu_dung", "loi")
HANH_DONG_UID = ("ghim", "bo-ghim", "loai", "bo-loai")
HANH_DONG_GOC = ("ngung", "theo-lai")

# Câu 404/409 cố định (docs/radar-uid.md §7, bảng lỗi).
LOI_KHONG_CO = "Không có UID này trong Radar"
LOI_DU_GOC = "Đã đủ 2 UID gốc: ngừng bớt"
LOI_DU_UID = "Đã đủ 24 UID theo dõi"
LOI_DU_THEM_TAY = "Đã đủ 3 UID thêm tay"
LOI_DU_TUONG_TU = "Đã đủ 10 UID tương tự"
LOI_DANG_LOAI = "UID này đang bị loại: bỏ loại trước"
LOI_UID_GOC = "Không đổi được UID gốc"
LOI_DANG_TIM = "Nhóm đang được tìm: chờ xong"
LOI_CHUA_CHUP = "Chưa bắt đầu chụp UID này hôm nay"
LOI_LAN_KHONG_MO = "Lượt chạy không ở trạng thái đang chạy"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS san_pham (uid TEXT PRIMARY KEY CHECK(length(uid)=19 AND uid NOT GLOB '*[^0-9]*'),
  ten TEXT NOT NULL DEFAULT '', shop TEXT NOT NULL DEFAULT '', cap_nhat_luc TEXT,
  anh TEXT NOT NULL DEFAULT '', anh_luc TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS nhom (goc TEXT PRIMARY KEY REFERENCES san_pham(uid),
  trang_thai TEXT NOT NULL CHECK(trang_thai IN ('cho_tim','dang_tim','da_tim','loi_tim','ngung')),
  ly_do TEXT NOT NULL DEFAULT '', them_luc TEXT NOT NULL, them_boi TEXT NOT NULL, tim_luc TEXT, bat_dau_ngay TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lien_ket (goc TEXT NOT NULL REFERENCES nhom(goc), uid TEXT NOT NULL REFERENCES san_pham(uid),
  vai TEXT NOT NULL CHECK(vai IN ('goc','tuong_tu','them_tay')),
  trang_thai TEXT NOT NULL CHECK(trang_thai IN ('dang_theo','ghim','loai')),
  do_giong REAL, them_luc TEXT NOT NULL, them_boi TEXT NOT NULL, PRIMARY KEY (goc, uid));
CREATE TABLE IF NOT EXISTS chup_uid (uid TEXT NOT NULL, ngay TEXT NOT NULL,
  trang_thai TEXT NOT NULL CHECK(trang_thai IN ('dang_chup','ok','loi')), ma_loi TEXT NOT NULL DEFAULT '',
  lay_luc TEXT NOT NULL,
  echotik_cap_nhat TEXT,
  ban_tong TEXT, gia TEXT, hoa_hong TEXT, ton TEXT, tong_creator TEXT,
  so_trang INTEGER NOT NULL DEFAULT 0, tong_trang INTEGER, so_lan_thu INTEGER NOT NULL DEFAULT 0,
  them TEXT NOT NULL DEFAULT '', PRIMARY KEY (uid, ngay));
CREATE TABLE IF NOT EXISTS chup_video (uid TEXT NOT NULL, ngay TEXT NOT NULL, video_id TEXT NOT NULL, creator TEXT NOT NULL,
  follower TEXT, view TEXT NOT NULL, ban TEXT, dang_luc TEXT NOT NULL, is_promote INTEGER,
  PRIMARY KEY (uid, ngay, video_id), FOREIGN KEY (uid, ngay) REFERENCES chup_uid(uid, ngay));
CREATE TABLE IF NOT EXISTS lan_chay (ngay TEXT NOT NULL, che_do TEXT NOT NULL, viec_id TEXT NOT NULL, trang_thai TEXT NOT NULL,
  ly_do TEXT NOT NULL DEFAULT '', bat_dau TEXT NOT NULL, ket_thuc TEXT, so_goi INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (ngay, che_do, viec_id));
CREATE TABLE IF NOT EXISTS goi_ngay (ngay TEXT PRIMARY KEY, so_goi INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS token_tt (id INTEGER PRIMARY KEY CHECK(id=1), trang_thai TEXT NOT NULL,
  ma TEXT NOT NULL DEFAULT '', luc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS su_kien (id INTEGER PRIMARY KEY, luc TEXT NOT NULL, boi TEXT NOT NULL,
  hanh_dong TEXT NOT NULL, goc TEXT, uid TEXT);
CREATE INDEX IF NOT EXISTS lien_ket_uid ON lien_ket(uid)
"""


# ---------------------------------------------------------------------------------------------------------------
# Ngoại lệ + kiểu (TypedDict §7.2, khai báo bản riêng của module này)
# ---------------------------------------------------------------------------------------------------------------
class KhongCoRadar(LookupError):
    """404: không có UID/nhóm (kể cả UID sai dạng). `.loi` là câu cố định."""

    def __init__(self, loi: str = LOI_KHONG_CO) -> None:
        super().__init__(loi)
        self.loi = loi


class SaiTrangThaiRadar(RuntimeError):
    """409: `.loi` là câu cố định (docs/radar-uid.md §7)."""

    def __init__(self, loi: str) -> None:
        super().__init__(loi)
        self.loi = loi


class ChiDoc(RuntimeError):
    """Gọi hàm ghi (hoặc `mo()`) trên `KhoRadarUid(chi_doc=True)`."""


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


class UngVien(TypedDict):
    uid: str
    ten: str
    gia: str | None
    ban_7d: str | None


# ---------------------------------------------------------------------------------------------------------------
# Kiểm tham số
# ---------------------------------------------------------------------------------------------------------------
def _la_uid(uid: object) -> bool:
    return isinstance(uid, str) and RE_UID.fullmatch(uid) is not None


def _kiem_uid(uid: object) -> str:
    if not _la_uid(uid):
        raise ThamSoLoi("UID phải đủ 19 chữ số")
    return uid  # type: ignore[return-value]


def _kiem_uid_404(uid: object) -> str:
    """UID tra cứu: sai dạng cũng là 404 (§7 dòng 2)."""
    if not _la_uid(uid):
        raise KhongCoRadar()
    return uid  # type: ignore[return-value]


def _kiem_ngay(ngay: object) -> str:
    if not isinstance(ngay, str) or not _RE_NGAY.fullmatch(ngay):
        raise ThamSoLoi("ngay phải dạng YYYY-MM-DD")
    return ngay


def _kiem_luc(luc: object, ten: str = "lay_luc") -> str:
    if not isinstance(luc, str) or not _RE_LUC.fullmatch(luc):
        raise ThamSoLoi(f"{ten} phải là ISO 8601 (YYYY-MM-DDTHH:MM:SS[+07:00])")
    return luc


def _kiem_boi(boi: object) -> str:
    if not isinstance(boi, str) or not _RE_BOI.fullmatch(boi):
        raise ThamSoLoi("boi không hợp lệ")
    return boi


def _kiem_ma(ma: object, ten: str, *, cho_rong: bool = False) -> str:
    if not isinstance(ma, str) or not (_RE_MA_RONG if cho_rong else _RE_MA).fullmatch(ma):
        raise ThamSoLoi(f"{ten} phải là mã ngắn [a-z0-9_]")
    return ma


def _sach_ten(s: object, ten: str) -> str:
    if not isinstance(s, str):
        raise ThamSoLoi(f"{ten} phải là chuỗi")
    return _RE_DIEU_KHIEN.sub("", s)[:TEN_TOI_DA]


def _chuoi_hoac_none(v: object, ten: str) -> str | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (str, int, float)):
        raise ThamSoLoi(f"{ten} phải là chuỗi hoặc null")
    return str(v)


def _so_nguyen_hoac_none(v: object, ten: str) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int):
        raise ThamSoLoi(f"{ten} phải là số nguyên hoặc null")
    return v


def _chuan_them(v: object) -> str:
    """`them` (chỉ số xu hướng của một snapshot) -> chuỗi JSON để lưu. None/{} -> ''. Sai kiểu -> ThamSoLoi."""
    if v is None or v == {}:
        return ""
    if not isinstance(v, dict) or len(v) > 20:
        raise ThamSoLoi("them phải là dict ≤ 20 khoá")
    for k, x in v.items():
        if not isinstance(k, str) or not k or len(k) > 32:
            raise ThamSoLoi("khoá của them phải là chuỗi 1–32 ký tự")
        if isinstance(x, bool) or not isinstance(x, (str, int, float)) or (isinstance(x, str) and len(x) > 32):
            raise ThamSoLoi("giá trị của them phải là chuỗi ≤ 32 ký tự hoặc số")
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _rollback_giu_loi_goc(c: sqlite3.Connection) -> None:
    """ROLLBACK sau một lỗi trong giao dịch; SQLite có thể đã tự rollback (BUSY/FULL/IOERR) → bỏ qua."""
    if not c.in_transaction:
        return
    try:
        c.execute("ROLLBACK")
    except sqlite3.Error:
        log.exception("radar_uid.db: ROLLBACK thất bại sau một lỗi trong giao dịch — ném lại lỗi gốc")


# ---------------------------------------------------------------------------------------------------------------
# Kho
# ---------------------------------------------------------------------------------------------------------------
class KhoRadarUid:
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
        """Đóng kết nối của luồng hiện tại."""
        c = getattr(self._cuc_bo, "c", None)
        if c is not None:
            self._cuc_bo.c = None
            c.close()

    def _kiem_ghi(self) -> None:
        if self.chi_doc:
            raise ChiDoc("KhoRadarUid đang mở chỉ đọc: không ghi")

    @contextmanager
    def _gd(self) -> Iterator[sqlite3.Connection]:
        """Giao dịch ghi BEGIN IMMEDIATE; lỗi giữa chừng ⇒ ROLLBACK hết, ném lại lỗi gốc."""
        self._kiem_ghi()
        c = self._ket_noi()
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.execute("COMMIT")
        except BaseException:
            _rollback_giu_loi_goc(c)
            raise

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
        """Tạo/nâng schema (idempotent) rồi dọn chụp cũ hơn 90 ngày. chi_doc → ChiDoc."""
        self._kiem_ghi()
        self.duong_dan.parent.mkdir(parents=True, exist_ok=True)
        c = self._ket_noi(tao=True)
        c.execute("PRAGMA journal_mode=WAL")
        with self._gd() as g:
            for cau in [x.strip() for x in SCHEMA.split(";") if x.strip()]:
                g.execute(cau)
            r = g.execute("SELECT v FROM meta WHERE k='schema_ban'").fetchone()
            if r is None:
                g.execute("INSERT INTO meta(k, v) VALUES('schema_ban', ?)", (PHIEN_BAN_SCHEMA,))
            elif r[0] in ("1", "2"):
                # v1/v2 -> v3 trong CÙNG giao dịch này (ALTER TABLE của SQLite có rollback): giữ nguyên dữ liệu.
                cot = {x[1] for x in g.execute("PRAGMA table_info(san_pham)")}
                for ten_cot in ("anh", "anh_luc"):
                    if ten_cot not in cot:
                        g.execute(f"ALTER TABLE san_pham ADD COLUMN {ten_cot} TEXT NOT NULL DEFAULT ''")
                cot_chup = {x[1] for x in g.execute("PRAGMA table_info(chup_uid)")}
                if "them" not in cot_chup:
                    g.execute("ALTER TABLE chup_uid ADD COLUMN them TEXT NOT NULL DEFAULT ''")
                g.execute("UPDATE meta SET v=? WHERE k='schema_ban'", (PHIEN_BAN_SCHEMA,))
            elif r[0] != PHIEN_BAN_SCHEMA:
                raise RuntimeError(f"radar_uid.db có schema {r[0]!r}, code cần {PHIEN_BAN_SCHEMA!r}: "
                                   f"KHÔNG tự xoá/tạo lại; kiểm tay {self.duong_dan}")
        # Dọn là việc phụ, giao dịch riêng: lỗi dọn không làm hỏng mo(), nhưng luôn ghi log đủ ngữ cảnh.
        moc = (self._hom_nay() - timedelta(days=GIU_CHUP_NGAY)).isoformat()
        try:
            with self._gd() as g:
                g.execute("DELETE FROM chup_video WHERE ngay < ?", (moc,))
                g.execute("DELETE FROM chup_uid WHERE ngay < ?", (moc,))
        except sqlite3.Error:
            log.exception("radar_uid.db: dọn chụp cũ hơn %s thất bại, giữ nguyên, chạy tiếp", moc)

    # ---------- đếm / giới hạn ----------
    @staticmethod
    def _uid_dang_theo(c: sqlite3.Connection, bo_nhom: str | None = None) -> set[str]:
        """Các UID khác nhau có liên kết ≠ loai ở nhóm ≠ ngung (bỏ qua nhóm `bo_nhom` nếu cho)."""
        cau = ("SELECT DISTINCT l.uid FROM lien_ket l JOIN nhom n ON n.goc = l.goc "
               "WHERE l.trang_thai <> 'loai' AND n.trang_thai <> 'ngung'")
        tham: tuple[Any, ...] = ()
        if bo_nhom is not None:
            cau += " AND l.goc <> ?"
            tham = (bo_nhom,)
        return {r[0] for r in c.execute(cau, tham)}

    @staticmethod
    def _can_nhom(c: sqlite3.Connection, goc: str) -> sqlite3.Row:
        r = c.execute("SELECT * FROM nhom WHERE goc=?", (goc,)).fetchone()
        if r is None:
            raise KhongCoRadar()
        return r

    @staticmethod
    def _su_kien(c: sqlite3.Connection, luc: str, boi: str, hanh_dong: str, goc: str | None, uid: str | None) -> None:
        c.execute("INSERT INTO su_kien(luc, boi, hanh_dong, goc, uid) VALUES(?,?,?,?,?)", (luc, boi, hanh_dong, goc, uid))

    @staticmethod
    def _kiem_cho_uid(c: sqlite3.Connection, uid: str, them: set[str] | None = None) -> None:
        """409 nếu thêm UID `uid` (hoặc tập `them`) làm vượt UID_TOI_DA."""
        hien = KhoRadarUid._uid_dang_theo(c)
        moi = {uid} if them is None else set(them)
        if len(hien | moi) > UID_TOI_DA:
            raise SaiTrangThaiRadar(LOI_DU_UID)

    # ---------- nhóm / UID ----------
    def them_goc(self, uid: str, boi: str) -> dict:
        """Thêm UID gốc (nhóm `cho_tim`). UID đã có nhóm ⇒ `da_co=True`, không ghi gì."""
        self._kiem_ghi()
        _kiem_uid(uid)
        _kiem_boi(boi)
        luc = self._luc()
        with self._gd() as c:
            if c.execute("SELECT 1 FROM nhom WHERE goc=?", (uid,)).fetchone():
                return {"da_co": True, "goc": uid}
            so_goc = c.execute("SELECT COUNT(*) FROM nhom WHERE trang_thai <> 'ngung'").fetchone()[0]
            if so_goc >= GOC_TOI_DA:
                raise SaiTrangThaiRadar(LOI_DU_GOC)
            self._kiem_cho_uid(c, uid)
            c.execute("INSERT INTO san_pham(uid, ten, shop, cap_nhat_luc) VALUES(?, '', '', NULL) "
                      "ON CONFLICT(uid) DO NOTHING", (uid,))
            c.execute("INSERT INTO nhom(goc, trang_thai, them_luc, them_boi, bat_dau_ngay) VALUES(?, 'cho_tim', ?, ?, ?)",
                      (uid, luc, boi, self._hom_nay().isoformat()))
            c.execute("INSERT INTO lien_ket(goc, uid, vai, trang_thai, do_giong, them_luc, them_boi) "
                      "VALUES(?, ?, 'goc', 'dang_theo', NULL, ?, ?)", (uid, uid, luc, boi))
            self._su_kien(c, luc, boi, "them_goc", uid, uid)
        return {"da_co": False, "goc": uid}

    def them_tay(self, goc: str, uid: str, boi: str) -> None:
        """Thêm tay UID vào nhóm (≤ 3, UID chưa bị loại)."""
        self._kiem_ghi()
        _kiem_uid_404(goc)
        _kiem_uid(uid)
        _kiem_boi(boi)
        luc = self._luc()
        with self._gd() as c:
            self._can_nhom(c, goc)
            lk = c.execute("SELECT trang_thai FROM lien_ket WHERE goc=? AND uid=?", (goc, uid)).fetchone()
            if lk is not None:
                if lk["trang_thai"] == "loai":
                    raise SaiTrangThaiRadar(LOI_DANG_LOAI)
                return                                                    # đã theo trong nhóm này: idempotent
            so_tay = c.execute("SELECT COUNT(*) FROM lien_ket WHERE goc=? AND vai='them_tay' AND trang_thai <> 'loai'",
                               (goc,)).fetchone()[0]
            if so_tay >= THEM_TAY_TOI_DA:
                raise SaiTrangThaiRadar(LOI_DU_THEM_TAY)
            self._kiem_cho_uid(c, uid)
            c.execute("INSERT INTO san_pham(uid, ten, shop, cap_nhat_luc) VALUES(?, '', '', NULL) "
                      "ON CONFLICT(uid) DO NOTHING", (uid,))
            c.execute("INSERT INTO lien_ket(goc, uid, vai, trang_thai, do_giong, them_luc, them_boi) "
                      "VALUES(?, ?, 'them_tay', 'dang_theo', NULL, ?, ?)", (goc, uid, luc, boi))
            self._su_kien(c, luc, boi, "them_tay", goc, uid)

    def dat_uid(self, goc: str, uid: str, hanh_dong: str, boi: str) -> dict:
        """ghim | bo-ghim | loai | bo-loai trên một UID của nhóm. Trả `{"uid", "trang_thai"}`."""
        self._kiem_ghi()
        if hanh_dong not in HANH_DONG_UID:
            raise ThamSoLoi(f"hanh_dong phải thuộc {HANH_DONG_UID}")
        _kiem_uid_404(goc)
        _kiem_uid_404(uid)
        _kiem_boi(boi)
        luc = self._luc()
        with self._gd() as c:
            self._can_nhom(c, goc)
            lk = c.execute("SELECT vai, trang_thai FROM lien_ket WHERE goc=? AND uid=?", (goc, uid)).fetchone()
            if lk is None:
                raise KhongCoRadar()
            if lk["vai"] == "goc":
                raise SaiTrangThaiRadar(LOI_UID_GOC)
            hien = lk["trang_thai"]
            if hanh_dong == "ghim":
                if hien == "loai":
                    raise SaiTrangThaiRadar(LOI_DANG_LOAI)
                moi = "ghim"
            elif hanh_dong == "bo-ghim":
                moi = "dang_theo" if hien == "ghim" else hien
            elif hanh_dong == "loai":
                moi = "loai"
            else:                                                           # bo-loai
                moi = hien
                if hien == "loai":
                    self._kiem_bo_loai(c, goc, uid, lk["vai"])
                    moi = "dang_theo"
            if moi != hien:
                c.execute("UPDATE lien_ket SET trang_thai=? WHERE goc=? AND uid=?", (moi, goc, uid))
                self._su_kien(c, luc, boi, hanh_dong, goc, uid)
        return {"uid": uid, "trang_thai": moi}

    def _kiem_bo_loai(self, c: sqlite3.Connection, goc: str, uid: str, vai: str) -> None:
        """Bỏ loại một UID làm tăng số đếm: kiểm trần theo vai rồi trần UID toàn DB."""
        if vai == "tuong_tu":
            n = c.execute("SELECT COUNT(*) FROM lien_ket WHERE goc=? AND vai='tuong_tu' AND trang_thai <> 'loai'",
                          (goc,)).fetchone()[0]
            if n >= TUONG_TU_TOI_DA:
                raise SaiTrangThaiRadar(LOI_DU_TUONG_TU)
        elif vai == "them_tay":
            n = c.execute("SELECT COUNT(*) FROM lien_ket WHERE goc=? AND vai='them_tay' AND trang_thai <> 'loai'",
                          (goc,)).fetchone()[0]
            if n >= THEM_TAY_TOI_DA:
                raise SaiTrangThaiRadar(LOI_DU_THEM_TAY)
        if c.execute("SELECT trang_thai FROM nhom WHERE goc=?", (goc,)).fetchone()[0] != "ngung":
            self._kiem_cho_uid(c, uid)

    def dat_goc(self, goc: str, hanh_dong: str, boi: str) -> dict:
        """ngung | theo-lai cả nhóm. Trả `{"goc", "trang_thai"}`."""
        self._kiem_ghi()
        if hanh_dong not in HANH_DONG_GOC:
            raise ThamSoLoi(f"hanh_dong phải thuộc {HANH_DONG_GOC}")
        _kiem_uid_404(goc)
        _kiem_boi(boi)
        luc = self._luc()
        with self._gd() as c:
            nh = self._can_nhom(c, goc)
            hien = nh["trang_thai"]
            if hanh_dong == "ngung":
                moi = "ngung"
            elif hien != "ngung":
                moi = hien                                                  # đang theo rồi: idempotent
            else:
                n_goc = c.execute("SELECT COUNT(*) FROM nhom WHERE trang_thai <> 'ngung'").fetchone()[0]
                if n_goc >= GOC_TOI_DA:
                    raise SaiTrangThaiRadar(LOI_DU_GOC)
                cua_nhom = {r[0] for r in c.execute(
                    "SELECT uid FROM lien_ket WHERE goc=? AND trang_thai <> 'loai'", (goc,))}
                self._kiem_cho_uid(c, goc, cua_nhom)
                moi = "da_tim" if nh["tim_luc"] else "cho_tim"
            if moi != hien:
                c.execute("UPDATE nhom SET trang_thai=?, ly_do='' WHERE goc=?", (moi, goc))
                self._su_kien(c, luc, boi, hanh_dong, goc, None)
        return {"goc": goc, "trang_thai": moi}

    def dat_trang_thai_nhom(self, goc: str, trang_thai: str, ly_do: str = "") -> None:
        """Script đổi trạng thái nhóm (cho_tim/dang_tim/da_tim/loi_tim/ngung). `cho_tim` khi đang `dang_tim` ⇒ 409."""
        self._kiem_ghi()
        if trang_thai not in TRANG_THAI_NHOM:
            raise ThamSoLoi(f"trang_thai phải thuộc {TRANG_THAI_NHOM}")
        _kiem_ma(ly_do, "ly_do", cho_rong=True)
        _kiem_uid_404(goc)
        with self._gd() as c:
            nh = self._can_nhom(c, goc)
            if trang_thai == "cho_tim" and nh["trang_thai"] == "dang_tim":
                raise SaiTrangThaiRadar(LOI_DANG_TIM)
            c.execute("UPDATE nhom SET trang_thai=?, ly_do=? WHERE goc=?", (trang_thai, ly_do, goc))

    # ---------- sản phẩm ----------
    def ghi_san_pham(self, uid: str, ten: str, shop: str, anh: str = "") -> None:
        """Ghi/đè tên + shop (bỏ ký tự điều khiển C0, cắt 200) và ảnh bìa.

        `anh` chỉ được lưu khi khớp RE_ANH (kèm `anh_luc`); rỗng/không khớp ⇒ giữ nguyên ảnh cũ, không ném, không log URL.
        """
        self._kiem_ghi()
        _kiem_uid(uid)
        ten_s, shop_s = _sach_ten(ten, "ten"), _sach_ten(shop, "shop")
        luc = self._luc()
        anh_ok = isinstance(anh, str) and RE_ANH.fullmatch(anh) is not None
        with self._gd() as c:
            if anh_ok:
                c.execute("INSERT INTO san_pham(uid, ten, shop, cap_nhat_luc, anh, anh_luc) VALUES(?,?,?,?,?,?) "
                          "ON CONFLICT(uid) DO UPDATE SET ten=excluded.ten, shop=excluded.shop, "
                          "cap_nhat_luc=excluded.cap_nhat_luc, anh=excluded.anh, anh_luc=excluded.anh_luc",
                          (uid, ten_s, shop_s, luc, anh, luc))
            else:
                c.execute("INSERT INTO san_pham(uid, ten, shop, cap_nhat_luc) VALUES(?,?,?,?) "
                          "ON CONFLICT(uid) DO UPDATE SET ten=excluded.ten, shop=excluded.shop, "
                          "cap_nhat_luc=excluded.cap_nhat_luc", (uid, ten_s, shop_s, luc))

    def ghi_tuong_tu(self, goc: str, ds: list[UngVien], tim_luc: str) -> int:
        """Thay các `tuong_tu` đang `dang_theo` bằng `ds` (giữ ghim, them_tay, loai, gốc). Trả số UID mới ghi.

        Bỏ qua ứng viên: sai dạng, trùng, là gốc, đã có liên kết trong nhóm (kể cả đang bị loại). Dừng khi nhóm đủ
        TUONG_TU_TOI_DA hoặc toàn DB đủ UID_TOI_DA (không ném: lần nạp vẫn ghi phần vừa chỗ).
        """
        self._kiem_ghi()
        _kiem_uid_404(goc)
        _kiem_luc(tim_luc, "tim_luc")
        luc = self._luc()
        with self._gd() as c:
            self._can_nhom(c, goc)
            c.execute("DELETE FROM lien_ket WHERE goc=? AND vai='tuong_tu' AND trang_thai='dang_theo'", (goc,))
            da_co = {r[0] for r in c.execute("SELECT uid FROM lien_ket WHERE goc=?", (goc,))}
            con_cho = TUONG_TU_TOI_DA - c.execute(
                "SELECT COUNT(*) FROM lien_ket WHERE goc=? AND vai='tuong_tu' AND trang_thai <> 'loai'",
                (goc,)).fetchone()[0]
            dang_theo = self._uid_dang_theo(c)
            nhom_ngung = c.execute("SELECT trang_thai FROM nhom WHERE goc=?", (goc,)).fetchone()[0] == "ngung"
            moi = 0
            for uv in ds:
                if moi >= con_cho:
                    break
                uid = uv.get("uid") if isinstance(uv, dict) else None
                if not _la_uid(uid) or uid in da_co:
                    continue
                if not nhom_ngung and uid not in dang_theo and len(dang_theo) >= UID_TOI_DA:
                    continue
                ten = _sach_ten(uv.get("ten", ""), "ten")
                dg = uv.get("do_giong")                                    # tuỳ chọn (UngVien §7.2 không có khoá này)
                dg_luu = float(dg) if isinstance(dg, (int, float)) and not isinstance(dg, bool) else None
                c.execute("INSERT INTO san_pham(uid, ten, shop, cap_nhat_luc) VALUES(?,?, '', ?) "
                          "ON CONFLICT(uid) DO UPDATE SET ten=CASE WHEN excluded.ten <> '' THEN excluded.ten "
                          "ELSE san_pham.ten END, cap_nhat_luc=excluded.cap_nhat_luc", (uid, ten, luc))
                c.execute("INSERT INTO lien_ket(goc, uid, vai, trang_thai, do_giong, them_luc, them_boi) "
                          "VALUES(?,?, 'tuong_tu', 'dang_theo', ?, ?, 'he_thong')", (goc, uid, dg_luu, luc))
                da_co.add(uid)
                dang_theo.add(uid)
                moi += 1
            c.execute("UPDATE nhom SET tim_luc=? WHERE goc=?", (tim_luc, goc))
        return moi

    # ---------- chụp ----------
    def ds_can_chup(self, ngay: str, goc: str | None = None) -> list[str]:
        """UID chưa `ok` ngày `ngay`, khử trùng. Xoay: lần chụp `ok` gần nhất cũ nhất trước, chưa từng chụp đứng đầu.

        Mặc định nhóm `da_tim` HOẶC `loi_tim` (tìm tương tự lỗi vẫn phải có chuỗi snapshot hằng ngày: gốc + UID thêm
        tay; nhóm cho_tim/dang_tim/ngung thuộc luồng nạp, §6.2). `goc` (tuỳ chọn): chỉ UID
        của nhóm đó, mọi trạng thái trừ `ngung` (luồng nạp chụp ngay sau khi tìm).
        """
        _kiem_ngay(ngay)
        if goc is not None:
            _kiem_uid_404(goc)
        with self._doc() as c:
            if c is None:
                return []
            dk = "n.trang_thai IN ('da_tim','loi_tim')" if goc is None else "n.trang_thai <> 'ngung' AND l.goc = ?"
            tham: tuple[Any, ...] = (ngay,) if goc is None else (goc, ngay)   # `l.goc = ?` đứng trước `h.ngay = ?`
            cau = (
                "SELECT l.uid AS uid, (SELECT MAX(k.lay_luc) FROM chup_uid k WHERE k.uid = l.uid AND k.trang_thai='ok') AS ok_cuoi "
                "FROM lien_ket l JOIN nhom n ON n.goc = l.goc "
                "WHERE l.trang_thai IN ('dang_theo','ghim') AND " + dk +
                " AND NOT EXISTS (SELECT 1 FROM chup_uid h WHERE h.uid = l.uid AND h.ngay = ? AND h.trang_thai='ok')"
                " GROUP BY l.uid")
            rows = c.execute(cau, tham).fetchall()
        rows.sort(key=lambda r: (r["ok_cuoi"] is not None, r["ok_cuoi"] or "", r["uid"]))
        return [r["uid"] for r in rows]

    def bat_dau_chup(self, uid: str, ngay: str, lay_luc: str) -> bool:
        """Ghi `dang_chup` TRƯỚC khi gọi mạng. False nếu đã `ok` hoặc hết SO_LAN_THU_TOI_DA lần thử."""
        self._kiem_ghi()
        _kiem_uid(uid)
        _kiem_ngay(ngay)
        _kiem_luc(lay_luc)
        with self._gd() as c:
            r = c.execute("SELECT trang_thai, so_lan_thu FROM chup_uid WHERE uid=? AND ngay=?", (uid, ngay)).fetchone()
            if r is None:
                c.execute("INSERT INTO chup_uid(uid, ngay, trang_thai, lay_luc, so_lan_thu) VALUES(?,?, 'dang_chup', ?, 1)",
                          (uid, ngay, lay_luc))
                return True
            if r["trang_thai"] == "ok" or r["so_lan_thu"] >= SO_LAN_THU_TOI_DA:
                return False
            c.execute("UPDATE chup_uid SET trang_thai='dang_chup', ma_loi='', lay_luc=?, so_lan_thu=so_lan_thu+1 "
                      "WHERE uid=? AND ngay=?", (lay_luc, uid, ngay))
            return True

    def ghi_chup_ok(self, snap: Snapshot) -> None:
        """Ghi snapshot trong MỘT giao dịch. `videos` rỗng ⇒ `loi`/`khong_co_video`, KHÔNG `ok`."""
        self._kiem_ghi()
        uid = _kiem_uid(snap.get("uid"))
        ngay = _kiem_ngay(snap.get("ngay"))
        lay_luc = _kiem_luc(snap.get("lay_luc"))
        videos = snap.get("videos") or {}
        if not isinstance(videos, dict):
            raise ThamSoLoi("videos phải là dict video_id → HangVideo")
        for vid in videos:
            if not isinstance(vid, str) or not vid:
                raise ThamSoLoi("video_id phải là chuỗi")
        cap_nhat = _chuoi_hoac_none(snap.get("echotik_cap_nhat"), "echotik_cap_nhat")
        cot = [_chuoi_hoac_none(snap.get(k), k) for k in ("ban_tong", "gia", "hoa_hong", "ton", "tong_creator")]
        so_trang = _so_nguyen_hoac_none(snap.get("so_trang"), "so_trang") or 0
        tong_trang = _so_nguyen_hoac_none(snap.get("tong_trang"), "tong_trang")
        them = _chuan_them(snap.get("them"))
        with self._gd() as c:
            r = c.execute("SELECT trang_thai FROM chup_uid WHERE uid=? AND ngay=?", (uid, ngay)).fetchone()
            if r is None or r["trang_thai"] != "dang_chup":
                raise SaiTrangThaiRadar(LOI_CHUA_CHUP)
            if not videos:
                c.execute("UPDATE chup_uid SET trang_thai='loi', ma_loi='khong_co_video', lay_luc=? WHERE uid=? AND ngay=?",
                          (lay_luc, uid, ngay))
                return
            c.execute("UPDATE chup_uid SET trang_thai='ok', ma_loi='', lay_luc=?, echotik_cap_nhat=?, ban_tong=?, gia=?, "
                      "hoa_hong=?, ton=?, tong_creator=?, so_trang=?, tong_trang=?, them=? WHERE uid=? AND ngay=?",
                      (lay_luc, cap_nhat, *cot, so_trang, tong_trang, them, uid, ngay))
            c.execute("DELETE FROM chup_video WHERE uid=? AND ngay=?", (uid, ngay))
            for vid, hv in videos.items():
                c.execute("INSERT INTO chup_video(uid, ngay, video_id, creator, follower, view, ban, dang_luc, is_promote) "
                          "VALUES(?,?,?,?,?,?,?,?,?)",
                          (uid, ngay, vid, hv.get("creator"), _chuoi_hoac_none(hv.get("follower"), "follower"),
                           _chuoi_hoac_none(hv.get("view"), "view"), _chuoi_hoac_none(hv.get("ban"), "ban"),
                           hv.get("dang_luc"), _is_promote(hv.get("is_promote"))))

    def ghi_them(self, uid: str, ngay: str, them: dict) -> bool:
        """Bổ sung `them` cho lần chụp `ok` đã có (chỉ khi nó đang rỗng). True nếu đã ghi."""
        self._kiem_ghi()
        _kiem_uid(uid)
        _kiem_ngay(ngay)
        chuoi = _chuan_them(them)
        if not chuoi:
            return False
        with self._gd() as c:
            cur = c.execute("UPDATE chup_uid SET them=? WHERE uid=? AND ngay=? AND trang_thai='ok' AND them=''",
                            (chuoi, uid, ngay))
            return cur.rowcount > 0

    def doc_them(self, uid: str, tu_ngay: str) -> dict[str, dict]:
        """ngày -> chỉ số xu hướng (dict) của các lần chụp `ok` từ `tu_ngay`. DB cũ chưa có cột / ô rỗng ⇒ bỏ qua."""
        _kiem_ngay(tu_ngay)
        if not _la_uid(uid):
            return {}
        with self._doc() as c:
            if c is None or not any(r[1] == "them" for r in c.execute("PRAGMA table_info(chup_uid)")):
                return {}
            ra: dict[str, dict] = {}
            for ngay, chuoi in c.execute("SELECT ngay, them FROM chup_uid WHERE uid=? AND ngay >= ? AND trang_thai='ok' "
                                         "ORDER BY ngay", (uid, tu_ngay)):
                try:
                    d = json.loads(chuoi) if chuoi else None
                except ValueError:
                    d = None
                if isinstance(d, dict):
                    ra[ngay] = d
            return ra

    def ghi_chup_loi(self, uid: str, ngay: str, ma_loi: str) -> None:
        """Đánh dấu lần chụp đang `dang_chup` là `loi`. Không hạ cấp một lần `ok`."""
        self._kiem_ghi()
        _kiem_uid(uid)
        _kiem_ngay(ngay)
        _kiem_ma(ma_loi, "ma_loi")
        with self._gd() as c:
            r = c.execute("SELECT trang_thai FROM chup_uid WHERE uid=? AND ngay=?", (uid, ngay)).fetchone()
            if r is None or r["trang_thai"] == "ok":
                raise SaiTrangThaiRadar(LOI_CHUA_CHUP)
            c.execute("UPDATE chup_uid SET trang_thai='loi', ma_loi=? WHERE uid=? AND ngay=?", (ma_loi, uid, ngay))

    def tinh_goi(self, ngay: str, so: int, tran: int) -> bool:
        """Cộng `so` GET vào ngân sách ngày TRƯỚC khi gọi. False (không cộng) nếu tổng sẽ vượt `tran`."""
        self._kiem_ghi()
        _kiem_ngay(ngay)
        if isinstance(so, bool) or not isinstance(so, int) or so < 1:
            raise ThamSoLoi("so phải là số nguyên ≥ 1")
        if isinstance(tran, bool) or not isinstance(tran, int) or tran < 0:
            raise ThamSoLoi("tran phải là số nguyên ≥ 0")
        with self._gd() as c:
            r = c.execute("SELECT so_goi FROM goi_ngay WHERE ngay=?", (ngay,)).fetchone()
            hien = r[0] if r else 0
            if hien + so > tran:
                return False
            c.execute("INSERT INTO goi_ngay(ngay, so_goi) VALUES(?,?) ON CONFLICT(ngay) DO UPDATE SET so_goi=excluded.so_goi",
                      (ngay, hien + so))
            return True

    def goi_hom_nay(self, ngay: str) -> int:
        _kiem_ngay(ngay)
        with self._doc() as c:
            if c is None:
                return 0
            r = c.execute("SELECT so_goi FROM goi_ngay WHERE ngay=?", (ngay,)).fetchone()
            return int(r[0]) if r else 0

    def doc_snapshots(self, uid: str, tu_ngay: str) -> list[Snapshot]:
        """Các lần chụp `ok` của `uid` từ `tu_ngay` (gồm), cũ → mới, kèm video."""
        _kiem_ngay(tu_ngay)
        if not _la_uid(uid):
            return []
        with self._doc() as c:
            if c is None:
                return []
            ra: list[Snapshot] = []
            for s in c.execute("SELECT * FROM chup_uid WHERE uid=? AND ngay >= ? AND trang_thai='ok' ORDER BY ngay",
                               (uid, tu_ngay)).fetchall():
                videos: dict[str, HangVideo] = {}
                for v in c.execute("SELECT * FROM chup_video WHERE uid=? AND ngay=? ORDER BY video_id", (uid, s["ngay"])):
                    videos[v["video_id"]] = HangVideo(
                        video_id=v["video_id"], creator=v["creator"], follower=v["follower"], view=v["view"],
                        ban=v["ban"], dang_luc=v["dang_luc"],
                        is_promote=None if v["is_promote"] is None else int(v["is_promote"]))
                ra.append(Snapshot(
                    uid=s["uid"], ngay=s["ngay"], lay_luc=s["lay_luc"], echotik_cap_nhat=s["echotik_cap_nhat"],
                    ban_tong=s["ban_tong"], gia=s["gia"], hoa_hong=s["hoa_hong"], ton=s["ton"],
                    tong_creator=s["tong_creator"], so_trang=s["so_trang"], tong_trang=s["tong_trang"], videos=videos))
            return ra

    # ---------- đọc nhóm ----------
    @staticmethod
    def _cot_anh(c: sqlite3.Connection) -> str:
        """Biểu thức cột ảnh. DB còn v1 (mở chỉ đọc, không nâng) thiếu cột `anh` ⇒ trả ''."""
        co = any(r[1] == "anh" for r in c.execute("PRAGMA table_info(san_pham)"))
        return "COALESCE(s.anh, '')" if co else "''"

    def ds_nhom(self) -> list[dict]:
        with self._doc() as c:
            if c is None:
                return []
            return [dict(r) for r in c.execute(
                "SELECT n.goc AS goc, COALESCE(s.ten, '') AS ten, n.trang_thai AS trang_thai, n.ly_do AS ly_do, "
                "n.them_luc AS them_luc, n.them_boi AS them_boi, n.tim_luc AS tim_luc, n.bat_dau_ngay AS bat_dau_ngay, "
                f"{self._cot_anh(c)} AS anh, COALESCE(s.shop, '') AS shop, "
                "(SELECT COUNT(*) FROM lien_ket l WHERE l.goc = n.goc AND l.vai <> 'goc' "
                "AND l.trang_thai IN ('dang_theo','ghim')) AS n_tuong_tu, "
                "(SELECT COUNT(*) FROM lien_ket l WHERE l.goc = n.goc AND l.vai <> 'goc' "
                "AND l.trang_thai = 'ghim') AS n_ghim "
                "FROM nhom n LEFT JOIN san_pham s ON s.uid = n.goc ORDER BY n.them_luc, n.goc")]

    def uid_cua_nhom(self, goc: str) -> list[dict]:
        """Liên kết của nhóm (gốc đứng đầu). Nhóm không có ⇒ KhongCoRadar."""
        _kiem_uid_404(goc)
        with self._doc() as c:
            if c is None:
                raise KhongCoRadar()
            if c.execute("SELECT 1 FROM nhom WHERE goc=?", (goc,)).fetchone() is None:
                raise KhongCoRadar()
            return [dict(r) for r in c.execute(
                "SELECT l.uid AS uid, l.vai AS vai, l.trang_thai AS trang_thai, l.do_giong AS do_giong, "
                "COALESCE(s.ten, '') AS ten, COALESCE(s.shop, '') AS shop, l.them_luc AS them_luc, "
                f"{self._cot_anh(c)} AS anh "
                "FROM lien_ket l LEFT JOIN san_pham s ON s.uid = l.uid WHERE l.goc = ? "
                "ORDER BY (l.vai <> 'goc'), l.them_luc, l.uid", (goc,))]

    # ---------- lần chạy ----------
    def bat_dau_lan(self, ngay: str, che_do: str, viec_id: str) -> bool:
        """True = được chạy (dòng mới, hoặc lần trước `dang_chay`/`loi` dở). False = đã `xong`/`tu_dung`."""
        self._kiem_ghi()
        _kiem_ngay(ngay)
        if not isinstance(che_do, str) or not _RE_CHE_DO.fullmatch(che_do):
            raise ThamSoLoi("che_do không hợp lệ")
        if not isinstance(viec_id, str) or not _RE_VIEC_ID.fullmatch(viec_id):
            raise ThamSoLoi("viec_id không hợp lệ")
        with self._gd() as c:
            r = c.execute("SELECT trang_thai FROM lan_chay WHERE ngay=? AND che_do=? AND viec_id=?",
                          (ngay, che_do, viec_id)).fetchone()
            if r is None:
                c.execute("INSERT INTO lan_chay(ngay, che_do, viec_id, trang_thai, bat_dau) VALUES(?,?,?, 'dang_chay', ?)",
                          (ngay, che_do, viec_id, self._luc()))
                return True
            if r[0] in ("xong", "tu_dung"):
                return False
            c.execute("UPDATE lan_chay SET trang_thai='dang_chay', ly_do='', bat_dau=?, ket_thuc=NULL, so_goi=0 "
                      "WHERE ngay=? AND che_do=? AND viec_id=?", (self._luc(), ngay, che_do, viec_id))
            return True

    def ket_thuc_lan(self, ngay: str, che_do: str, viec_id: str, trang_thai: str, ly_do: str, so_goi: int) -> None:
        self._kiem_ghi()
        _kiem_ngay(ngay)
        if trang_thai not in TRANG_THAI_KET_THUC:
            raise ThamSoLoi(f"trang_thai phải thuộc {TRANG_THAI_KET_THUC}")
        _kiem_ma(ly_do, "ly_do", cho_rong=True)
        if trang_thai != "xong" and not ly_do:
            raise ThamSoLoi("tu_dung/loi cần ly_do")
        if isinstance(so_goi, bool) or not isinstance(so_goi, int) or so_goi < 0:
            raise ThamSoLoi("so_goi phải là số nguyên ≥ 0")
        with self._gd() as c:
            cur = c.execute("UPDATE lan_chay SET trang_thai=?, ly_do=?, ket_thuc=?, so_goi=? "
                            "WHERE ngay=? AND che_do=? AND viec_id=? AND trang_thai='dang_chay'",
                            (trang_thai, ly_do, self._luc(), so_goi, ngay, che_do, viec_id))
            if cur.rowcount != 1:
                raise SaiTrangThaiRadar(LOI_LAN_KHONG_MO)

    def lan_gan_nhat(self) -> dict | None:
        with self._doc() as c:
            if c is None:
                return None
            r = c.execute("SELECT * FROM lan_chay ORDER BY bat_dau DESC, ngay DESC, viec_id DESC LIMIT 1").fetchone()
            return dict(r) if r else None

    def lan_cua_viec(self, ngay: str, che_do: str, viec_id: str) -> dict | None:
        _kiem_ngay(ngay)
        with self._doc() as c:
            if c is None:
                return None
            r = c.execute("SELECT * FROM lan_chay WHERE ngay=? AND che_do=? AND viec_id=?",
                          (ngay, che_do, viec_id)).fetchone()
            return dict(r) if r else None

    # ---------- token ----------
    def ghi_token(self, trang_thai: str, ma: str) -> None:
        """Ghi TRẠNG THÁI token (không bao giờ nội dung token): `ma` chỉ nhận mã ngắn [a-z0-9_]."""
        self._kiem_ghi()
        if trang_thai not in TRANG_THAI_TOKEN:
            raise ThamSoLoi(f"trang_thai phải thuộc {TRANG_THAI_TOKEN}")
        _kiem_ma(ma, "ma", cho_rong=True)
        with self._gd() as c:
            c.execute("INSERT INTO token_tt(id, trang_thai, ma, luc) VALUES(1,?,?,?) "
                      "ON CONFLICT(id) DO UPDATE SET trang_thai=excluded.trang_thai, ma=excluded.ma, luc=excluded.luc",
                      (trang_thai, ma, self._luc()))

    def doc_token(self) -> dict:
        with self._doc() as c:
            r = c.execute("SELECT trang_thai, ma, luc FROM token_tt WHERE id=1").fetchone() if c is not None else None
        if r is None:
            return {"trang_thai": "chua_kiem", "ma": "", "luc": ""}
        return {"trang_thai": r["trang_thai"], "ma": r["ma"], "luc": r["luc"]}


def _is_promote(v: object) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if v in (0, 1) and isinstance(v, int):
        return v
    raise ThamSoLoi("is_promote phải là 0, 1, bool hoặc null")
