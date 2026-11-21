"""Kho việc SQLite (WAL, CAS) — docs/bo-chay-viec.md §4.2–4.5.

Nguyên tắc:
- Mỗi luồng một kết nối riêng (threading.local).
- Mọi chuyển trạng thái là CAS `UPDATE … WHERE id=? AND trang_thai IN (…)`; rowcount 0 → SaiTrangThai.
- Không bao giờ đổi tên / xoá / tạo lại DB khi gặp lỗi: trạng thái và khoá chống trùng không được "quên".
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import sqlite3
import string
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from contextlib import closing, contextmanager
from urllib.parse import quote

from .chu_ky import giai_chu_ky
from .kieu import DANG_MO, LAN_CHAY, TRANG_THAI, CanNguoiDung, SaiTrangThai, ThamSoLoi, TrungViec, gio_vn

log = logging.getLogger(__name__)

PHIEN_BAN_SCHEMA = "4"
TEN_DB = "runner.db"            # <thu_muc_runner>/runner.db (tools/chay_runner.py); danh_muc đọc bảng ban_sua ở đây
# Nâng schema tại chỗ, chạy trong CÙNG giao dịch BEGIN IMMEDIATE với việc đổi meta; lỗi → rollback cả cụm, DB giữ
# nguyên schema cũ. KHÔNG bao giờ xoá/tạo lại DB cũ.
# - '1' → '2' (D9, §10): thêm 2 cột tiêu (bảng da_tieu do SCHEMA `CREATE … IF NOT EXISTS` tạo);
# - '2' → '3' (D10, docs/sua-video.md §7.3): chỉ thêm bảng ban_sua (SCHEMA `CREATE … IF NOT EXISTS`), không đụng bảng cũ.
# - '3' → '4' (phiếu DP-1, ẩn/lưu trữ việc đã xong khỏi danh sách): chỉ thêm cột `luu_tru` (mặc định 0, không ai bị
#   ẩn sẵn), không đụng cột/bảng cũ.
NANG_1_LEN_2: tuple[str, ...] = (
    "ALTER TABLE viec ADD COLUMN so_lan_tieu INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE viec ADD COLUMN tieu_luc_dau TEXT",
)
NANG_3_LEN_4: tuple[str, ...] = (
    "ALTER TABLE viec ADD COLUMN luu_tru INTEGER NOT NULL DEFAULT 0",
)
SCHEMA_NANG_DUOC = ("1", "2", "3")
BAN_SUA_GIU_NGAY = 30           # §7.3: dòng ban_sua cũ hơn bị xoá ở bước dọn khởi động (trừ dòng việc mở còn dùng)
RE_BAN_SUA = re.compile(r"^b[0-9a-f]{16}$", re.ASCII)
_RE_UID = re.compile(r"^\d{19}$", re.ASCII)
_RE_DU_AN = re.compile(r"^[0-9a-f]{12}$", re.ASCII)
_RE_MA_VIDEO = re.compile(r"^[0-9a-f]{16}$", re.ASCII)

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(khoa TEXT PRIMARY KEY, gia_tri TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS viec(
  id TEXT PRIMARY KEY,
  loai TEXT NOT NULL, khoa TEXT NOT NULL,
  tham_so TEXT NOT NULL,
  lan_chay TEXT NOT NULL CHECK(lan_chay IN ('gpu','nhe')),
  trang_thai TEXT NOT NULL CHECK(trang_thai IN ('cho','dang_chay','can_tra_loi','cho_duyet','xong','loi','huy')),
  buoc TEXT NOT NULL DEFAULT 'chay',
  tao_boi TEXT NOT NULL, tao_luc TEXT NOT NULL, cap_nhat_luc TEXT NOT NULL,
  bat_dau_luc TEXT, ket_thuc_luc TEXT,
  lan_thu INTEGER NOT NULL DEFAULT 1, cha_id TEXT REFERENCES viec(id), chay_lai_tu TEXT REFERENCES viec(id),
  pid INTEGER, pid_tao_luc REAL,
  session_id TEXT,
  phien_da_tao INTEGER NOT NULL DEFAULT 0,
  cau_hoi TEXT,
  can_ban TEXT,
  uoc_tinh TEXT,
  loi_duyet TEXT, duyet_boi TEXT, duyet_luc TEXT, chu_ky_duyet TEXT,
  ket_qua TEXT,
  loi TEXT, ghi_chu TEXT,
  chi_phi_usd REAL NOT NULL DEFAULT 0, so_luot_claude INTEGER NOT NULL DEFAULT 0, so_lan_claude INTEGER NOT NULL DEFAULT 0,
  so_lan_tieu INTEGER NOT NULL DEFAULT 0, tieu_luc_dau TEXT,
  luu_tru INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS viec_dang_mo ON viec(loai, khoa)
  WHERE trang_thai IN ('cho','dang_chay','can_tra_loi','cho_duyet');
CREATE INDEX IF NOT EXISTS viec_tt ON viec(trang_thai, lan_chay, tao_luc);
CREATE TABLE IF NOT EXISTS su_kien(id INTEGER PRIMARY KEY AUTOINCREMENT, viec_id TEXT NOT NULL REFERENCES viec(id),
  luc TEXT NOT NULL, tu TEXT, den TEXT NOT NULL, boi TEXT NOT NULL, ghi_chu TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS tra_loi(id INTEGER PRIMARY KEY AUTOINCREMENT, viec_id TEXT NOT NULL REFERENCES viec(id),
  luc TEXT NOT NULL, boi TEXT NOT NULL, cau_hoi TEXT NOT NULL, noi_dung TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS nonce(gia_tri TEXT PRIMARY KEY, luc REAL NOT NULL);
CREATE TABLE IF NOT EXISTS da_tieu(khoa TEXT PRIMARY KEY, viec_id TEXT NOT NULL, luc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ban_sua(
  id TEXT PRIMARY KEY,
  uid TEXT NOT NULL, du_an TEXT NOT NULL, ma_video TEXT NOT NULL,
  noi_dung TEXT NOT NULL,
  tao_boi TEXT NOT NULL, tao_luc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ban_sua_tao_luc ON ban_sua(tao_luc)
"""

COT_JSON = ("tham_so", "cau_hoi", "ket_qua")
# Cột được phép ghi qua chuyen(**truong). id/loai/khoa/tham_so/trang_thai/tao_* KHÔNG được đổi qua đây.
COT_CHO_GHI = frozenset({
    "buoc", "bat_dau_luc", "ket_thuc_luc", "lan_thu", "pid", "pid_tao_luc", "session_id", "phien_da_tao",
    "cau_hoi", "can_ban", "uoc_tinh", "loi_duyet", "duyet_boi", "duyet_luc", "chu_ky_duyet", "ket_qua",
    "loi", "ghi_chu",
})
BUOC = ("chay", "uoc_tinh")
TRANG_THAI_DONG = ("xong", "loi", "huy")
_KY_TU_ID = string.ascii_lowercase + string.digits


def _json_chuan(x: Any) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _ma_hoa(cot: str, gia_tri: Any) -> Any:
    if cot in COT_JSON and gia_tri is not None:
        if isinstance(gia_tri, CanNguoiDung):
            gia_tri = gia_tri.thanh_dict()
        if not isinstance(gia_tri, (dict, list)):
            raise ThamSoLoi(f"cột {cot} cần dict/list")
        return _json_chuan(gia_tri)
    return gia_tri


def khoa_tieu(chu_ky_duyet: str) -> str:
    """Khoá sổ "đã tiêu" cục bộ = sha256_hex(64 BYTE chữ ký đã giải) — không lưu chữ ký thô.

    Băm byte (không băm chuỗi) và chỉ nhận base64url CHUẨN (``chu_ky.giai_chu_ky``): biến thể bit thừa của cùng
    chữ ký không thành khoá mới để tiêu lại (R-15 P1-1). Chuỗi không chuẩn/hỏng → ThamSoLoi.
    Với chuỗi chuẩn, chuỗi ↔ byte là 1-1 nên khoá này tương đương khoá KV Worker (sha256 của chuỗi, §8.3)."""
    raw = giai_chu_ky(chu_ky_duyet)
    if raw is None:
        raise ThamSoLoi("chu_ky_duyet không phải base64url chuẩn của chữ ký 64 byte")
    return hashlib.sha256(raw).hexdigest()


def _khoa_tieu_cu(chu_ky_duyet: str) -> str:
    """Khoá sổ trước R-15 (sha256 của CHUỖI). Chỉ dùng để nhận ra dòng da_tieu cũ — không ghi khoá này nữa."""
    return hashlib.sha256(chu_ky_duyet.encode("utf-8")).hexdigest()


def _cac_khoa_tieu(chu_ky_duyet: str) -> tuple[str, str]:
    """(khoá mới, khoá cũ) — ném ThamSoLoi nếu chuỗi không chuẩn."""
    return khoa_tieu(chu_ky_duyet), _khoa_tieu_cu(chu_ky_duyet)


_SQL_THAM_SO_TOI_DA = 500       # số tham số mỗi câu IN (...) — dưới giới hạn 999 của SQLite cũ


def _dong_thanh_dict(r: sqlite3.Row) -> dict:
    d = dict(r)
    for c in COT_JSON:
        if c in d and d[c] is not None:
            d[c] = json.loads(d[c])
    return d


def _kiem_id_ban_sua(id: object) -> str:
    if not isinstance(id, str) or not RE_BAN_SUA.fullmatch(id):
        raise ThamSoLoi("mã bản sửa phải là 'b' + 16 hex")
    return id


def _ban_sua_thanh_dict(r: sqlite3.Row | tuple, cot: Sequence[str]) -> dict:
    d = dict(zip(cot, r))
    d["noi_dung"] = json.loads(d["noi_dung"])
    return d


_COT_BAN_SUA = ("id", "uid", "du_an", "ma_video", "noi_dung", "tao_boi", "tao_luc")
_SQL_LAY_BAN_SUA = f"SELECT {', '.join(_COT_BAN_SUA)} FROM ban_sua WHERE id=?"


def doc_ban_sua_chi_doc(duong_dan_db: Path, id: str) -> dict | None:
    """Đọc 1 dòng ban_sua bằng kết nối CHỈ ĐỌC (danh_muc.lap_buoc dùng — không có KhoViec trong tay).
    DB không có → None (không bao giờ tạo DB rỗng). id sai định dạng → ThamSoLoi. Lỗi SQLite → ném tiếp."""
    _kiem_id_ban_sua(id)
    db = Path(duong_dan_db)
    if not db.is_file():
        return None
    uri = f"file:{quote(db.resolve().as_posix(), safe='/:')}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=10)) as c:
        c.execute("PRAGMA busy_timeout=5000")
        r = c.execute(_SQL_LAY_BAN_SUA, (id,)).fetchone()
    return _ban_sua_thanh_dict(r, _COT_BAN_SUA) if r else None


class KhoViec:
    NONCE_SONG_S = 86400.0      # khớp vong_lap: don_cu(bây giờ − 1 ngày) lúc khởi động (§4.5 bước 3)
    NONCE_DON_TOI_DA = 200      # mỗi lần ghi nonce chỉ xoá tối đa chừng này dòng (giới hạn chi phí)

    def __init__(self, duong_dan_db: Path, bay_gio: Callable[[], datetime]):
        self.duong_dan_db = Path(duong_dan_db)
        self.bay_gio = bay_gio
        self._cuc_bo = threading.local()
        self._khoi_tao()

    # ---------- kết nối ----------
    def _ket_noi(self) -> sqlite3.Connection:
        c = getattr(self._cuc_bo, "c", None)
        if c is None:
            c = sqlite3.connect(self.duong_dan_db, timeout=10, isolation_level=None, check_same_thread=True)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA busy_timeout=5000")
            c.execute("PRAGMA foreign_keys=ON")
            self._cuc_bo.c = c
        return c

    @contextmanager
    def _gd(self) -> Iterator[sqlite3.Connection]:
        """Giao dịch ghi BEGIN IMMEDIATE (khoá ghi ngay, tránh 2 luồng cùng đọc rồi cùng ghi)."""
        c = self._ket_noi()
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
        except BaseException:
            c.execute("ROLLBACK")
            raise
        else:
            c.execute("COMMIT")

    def _khoi_tao(self) -> None:
        self.duong_dan_db.parent.mkdir(parents=True, exist_ok=True)
        c = self._ket_noi()
        c.execute("PRAGMA journal_mode=WAL")
        with self._gd() as g:
            for cau in [x.strip() for x in SCHEMA.split(";") if x.strip()]:
                g.execute(cau)
            r = g.execute("SELECT gia_tri FROM meta WHERE khoa='schema'").fetchone()
            if r is None:
                g.execute("INSERT INTO meta(khoa, gia_tri) VALUES('schema', ?)", (PHIEN_BAN_SCHEMA,))
            elif r[0] in SCHEMA_NANG_DUOC:
                # Cột hiện có TRƯỚC khi ALTER bất kỳ — dùng chung để kiểm "đã có chưa" cho mọi mức xuất phát
                # (1/2/3), vì ALTER của NANG_1_LEN_2 không đụng cột của NANG_3_LEN_4 (tên khác nhau).
                cot = {x[1] for x in g.execute("PRAGMA table_info(viec)")}
                if r[0] == "1":
                    for cau in NANG_1_LEN_2:
                        ten = cau.split("ADD COLUMN", 1)[1].split()[0] if "ADD COLUMN" in cau else None
                        if ten is None or ten not in cot:
                            g.execute(cau)
                # '2' → '3': bảng ban_sua đã được SCHEMA tạo ở trên (CREATE … IF NOT EXISTS) trong cùng giao dịch.
                # '*' → '4': thêm cột luu_tru nếu chưa có (áp dụng cho cả 3 mức xuất phát 1/2/3).
                for cau in NANG_3_LEN_4:
                    ten = cau.split("ADD COLUMN", 1)[1].split()[0] if "ADD COLUMN" in cau else None
                    if ten is None or ten not in cot:
                        g.execute(cau)
                g.execute("UPDATE meta SET gia_tri=? WHERE khoa='schema'", (PHIEN_BAN_SCHEMA,))
                log.warning("đã nâng runner.db schema %r → %r tại chỗ (giữ nguyên dữ liệu): %s",
                            r[0], PHIEN_BAN_SCHEMA, self.duong_dan_db)
            elif r[0] != PHIEN_BAN_SCHEMA:
                raise RuntimeError(f"runner.db có schema {r[0]!r}, code cần {PHIEN_BAN_SCHEMA!r} — "
                                   f"KHÔNG tự xoá/tạo lại; kiểm tay {self.duong_dan_db}")

    # ---------- thời gian ----------
    def _luc(self) -> str:
        return gio_vn(self.bay_gio()).isoformat(timespec="seconds")

    def _id_moi(self) -> str:
        t = gio_vn(self.bay_gio()).strftime("%Y%m%d%H%M%S")
        return "j" + t + "".join(secrets.choice(_KY_TU_ID) for _ in range(4))

    # ---------- đọc ----------
    def _lay(self, c: sqlite3.Connection, id: str) -> dict | None:
        r = c.execute("SELECT * FROM viec WHERE id=?", (id,)).fetchone()
        return _dong_thanh_dict(r) if r else None

    def _dang_mo(self, c: sqlite3.Connection, loai: str, khoa: str) -> dict | None:
        r = c.execute(f"SELECT * FROM viec WHERE loai=? AND khoa=? AND trang_thai IN ({','.join('?' * len(DANG_MO))})",
                      (loai, khoa, *DANG_MO)).fetchone()
        return _dong_thanh_dict(r) if r else None

    def lay(self, id: str) -> dict | None:
        return self._lay(self._ket_noi(), id)

    @staticmethod
    def _dieu_kien_ds(trang_thai: Sequence[str] | None, khoa: str | None) -> tuple[list[str], list]:
        """Mệnh đề WHERE dùng chung cho `ds()`/`dem_loc()`: luôn loại việc đã ẩn/lưu trữ (`luu_tru=1`)."""
        dk, ts = ["luu_tru=0"], []
        if trang_thai:
            tt = list(trang_thai)
            for t in tt:
                if t not in TRANG_THAI:
                    raise ThamSoLoi(f"trạng thái lạ: {t!r}")
            dk.append(f"trang_thai IN ({','.join('?' * len(tt))})")
            ts += tt
        if khoa is not None:
            dk.append("khoa=?")
            ts.append(khoa)
        return dk, ts

    def ds(self, trang_thai: Sequence[str] | None = None, khoa: str | None = None, gioi_han: int = 50,
           offset: int = 0) -> list[dict]:
        dk, ts = self._dieu_kien_ds(trang_thai, khoa)
        gioi_han = max(1, min(int(gioi_han), 500))
        offset = max(0, int(offset))
        sql = "SELECT * FROM viec WHERE " + " AND ".join(dk) + \
              " ORDER BY tao_luc DESC, rowid DESC LIMIT ? OFFSET ?"
        return [_dong_thanh_dict(r) for r in self._ket_noi().execute(sql, (*ts, gioi_han, offset))]

    def dem_loc(self, trang_thai: Sequence[str] | None = None, khoa: str | None = None) -> int:
        """Đếm số việc khớp ĐÚNG điều kiện lọc của `ds()` (gồm loại bỏ `luu_tru=1`), không LIMIT/OFFSET."""
        dk, ts = self._dieu_kien_ds(trang_thai, khoa)
        sql = "SELECT COUNT(*) FROM viec WHERE " + " AND ".join(dk)
        return int(self._ket_noi().execute(sql, ts).fetchone()[0])

    def su_kien(self, id: str) -> list[dict]:
        return [dict(r) for r in self._ket_noi().execute(
            "SELECT * FROM su_kien WHERE viec_id=? ORDER BY id", (id,))]

    def tra_loi_cua(self, id: str) -> list[dict]:
        return [dict(r) for r in self._ket_noi().execute(
            "SELECT * FROM tra_loi WHERE viec_id=? ORDER BY id", (id,))]

    def dem(self) -> dict[str, int]:
        d = {t: 0 for t in TRANG_THAI}
        for r in self._ket_noi().execute("SELECT trang_thai, COUNT(*) FROM viec GROUP BY trang_thai"):
            d[r[0]] = r[1]
        return d

    def chi_phi_ngay(self, ngay: date) -> float:
        """Tổng chi_phi_usd của các job có lần chạy gần nhất (bat_dau_luc) rơi vào ngày VN này.
        Job chạy tiếp qua ngày bị tính toàn bộ chi phí vào ngày chạy sau cùng (thiên về chặt)."""
        r = self._ket_noi().execute("SELECT COALESCE(SUM(chi_phi_usd),0) FROM viec WHERE substr(bat_dau_luc,1,10)=?",
                                    (ngay.isoformat(),)).fetchone()
        return float(r[0])

    def dem_trong_ngay(self, loai: str | None, ngay: date, boi: str | None = None, chi_claude: bool = False) -> int:
        """Đếm job trong ngày VN.
        chi_claude=False: theo ngày TẠO (tao_luc), mọi trạng thái (kể cả huỷ) — dùng cho hạn mức tạo.
        chi_claude=True: job có so_lan_claude>0 và bat_dau_luc trong ngày (§6.3 chốt 2)."""
        cot = "bat_dau_luc" if chi_claude else "tao_luc"
        dk, ts = [f"substr({cot},1,10)=?"], [ngay.isoformat()]
        if chi_claude:
            dk.append("so_lan_claude>0")
        if loai is not None:
            dk.append("loai=?")
            ts.append(loai)
        if boi is not None:
            dk.append("tao_boi=?")
            ts.append(boi)
        return int(self._ket_noi().execute("SELECT COUNT(*) FROM viec WHERE " + " AND ".join(dk), ts).fetchone()[0])

    # ---------- ghi ----------
    def _ghi_su_kien(self, c: sqlite3.Connection, id: str, tu: str | None, den: str, boi: str, ghi_chu: str) -> None:
        c.execute("INSERT INTO su_kien(viec_id, luc, tu, den, boi, ghi_chu) VALUES(?,?,?,?,?,?)",
                  (id, self._luc(), tu, den, boi, ghi_chu or ""))

    def tao(self, loai: str, khoa: str, tham_so: dict, lan_chay: str, trang_thai_dau: str, boi: str, *,
            buoc: str = "chay", uoc_tinh: str | None = None, cau_hoi: CanNguoiDung | None = None,
            session_id: str | None = None, cha_id: str | None = None, chay_lai_tu: str | None = None) -> dict:
        if lan_chay not in LAN_CHAY:
            raise ThamSoLoi(f"làn lạ: {lan_chay!r}")
        if trang_thai_dau not in DANG_MO:
            raise ThamSoLoi(f"trạng thái đầu phải là trạng thái mở: {trang_thai_dau!r}")
        if buoc not in BUOC:
            raise ThamSoLoi(f"bước lạ: {buoc!r}")
        if not isinstance(tham_so, dict):
            raise ThamSoLoi("tham_so phải là dict")
        if not loai or not khoa or not boi:
            raise ThamSoLoi("thiếu loai/khoa/boi")
        luc = self._luc()
        for _ in range(5):
            id = self._id_moi()
            try:
                with self._gd() as c:
                    cu = self._dang_mo(c, loai, khoa)
                    if cu is not None:
                        raise TrungViec(cu)
                    c.execute(
                        "INSERT INTO viec(id, loai, khoa, tham_so, lan_chay, trang_thai, buoc, tao_boi, tao_luc,"
                        " cap_nhat_luc, cha_id, chay_lai_tu, session_id, cau_hoi, uoc_tinh)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (id, loai, khoa, _json_chuan(tham_so), lan_chay, trang_thai_dau, buoc, boi, luc, luc,
                         cha_id, chay_lai_tu, session_id, _ma_hoa("cau_hoi", cau_hoi), uoc_tinh))
                    self._ghi_su_kien(c, id, None, trang_thai_dau, boi, "tạo")
                    return self._lay(c, id)  # type: ignore[return-value]
            except sqlite3.IntegrityError as e:
                cu = self._dang_mo(self._ket_noi(), loai, khoa)
                if cu is not None:
                    raise TrungViec(cu) from e
                if "viec.id" in str(e):
                    log.warning("trùng id việc %s, sinh id khác", id)
                    continue
                raise
        raise RuntimeError("không sinh được id việc không trùng sau 5 lần")

    def chuyen(self, id: str, tu: Sequence[str], den: str, boi: str, ghi_chu: str = "", **truong) -> dict:
        tu = list(tu)
        if den not in TRANG_THAI or not tu or any(t not in TRANG_THAI for t in tu):
            raise ThamSoLoi(f"trạng thái lạ: {tu!r} → {den!r}")
        la = set(truong) - COT_CHO_GHI
        if la:
            raise ThamSoLoi(f"không được ghi cột: {sorted(la)}")
        luc = self._luc()
        gan = dict(truong)
        if den == "dang_chay" and "bat_dau_luc" not in gan:
            gan["bat_dau_luc"] = luc
        if den in TRANG_THAI_DONG and "ket_thuc_luc" not in gan:
            gan["ket_thuc_luc"] = luc
        if den not in TRANG_THAI_DONG:
            # Bất biến bắt buộc đúng mọi lúc: luu_tru=1 ⇒ trang_thai ∈ TRANG_THAI_DONG (phiếu DP-1, lỗi P1
            # "moi:an-viec-roi-chay-lai-an-tang-hinh"). Việc ẩn/lưu trữ chỉ đặt được khi đã kết thúc
            # (dat_luu_tru), nhưng MỌI đường đưa một việc ra khỏi TRANG_THAI_DONG đi qua chuyen() ở đây — nên
            # xoá cờ ngay tại chỗ duy nhất này, không cần sửa từng act (chay-tiep/xin-duyet-lai/...) trong api.py.
            # luu_tru là cột hệ thống tự quản (không phải cột caller được chọn ghi) nên không đi qua **truong.
            gan["luu_tru"] = 0
        cot = ["trang_thai=?", "cap_nhat_luc=?"] + [f"{k}=?" for k in gan]
        gia = [den, luc] + [_ma_hoa(k, v) for k, v in gan.items()]
        try:
            with self._gd() as c:
                r = c.execute("SELECT trang_thai, loai, khoa FROM viec WHERE id=?", (id,)).fetchone()
                if r is None or r["trang_thai"] not in tu:
                    raise SaiTrangThai(f"việc {id}: đang {r['trang_thai'] if r else 'không có'}, cần {tu}")
                cur = c.execute(f"UPDATE viec SET {', '.join(cot)} WHERE id=? AND trang_thai IN "
                                f"({','.join('?' * len(tu))})", (*gia, id, *tu))
                if cur.rowcount != 1:
                    raise SaiTrangThai(f"việc {id}: CAS thất bại")
                self._ghi_su_kien(c, id, r["trang_thai"], den, boi, ghi_chu)
                return self._lay(c, id)  # type: ignore[return-value]
        except sqlite3.IntegrityError as e:
            ht = self.lay(id)
            cu = self._dang_mo(self._ket_noi(), ht["loai"], ht["khoa"]) if ht else None
            if cu is not None and cu["id"] != id:
                raise TrungViec(cu) from e
            raise

    def dat_luu_tru(self, id: str, luu_tru: bool, boi: str, ghi_chu: str = "") -> dict:
        """Ẩn ('lưu trữ') hoặc bỏ ẩn một việc ĐÃ KẾT THÚC khỏi `ds()` — KHÔNG đổi `trang_thai` (không phải CAS của
        `chuyen()`: `luu_tru` là một cờ độc lập, không nằm trong CHECK constraint của trang_thai). Chỉ việc trong
        TRANG_THAI_DONG mới ẩn/bỏ ẩn được (việc còn mở phải huỷ/chạy xong trước).

        Ghi một dòng `su_kien` trong CÙNG giao dịch (P3, reviewer: trước đây hành động này vô vết — không biết
        ai đã ẩn/bỏ ẩn). `tu`/`den` chỉ là text lưu vào cột (không phải CAS của chuyen()) nên dùng
        `tu=den=trang_thai hiện tại`; hành động thật nằm ở `ghi_chu`."""
        with self._gd() as c:
            r = c.execute("SELECT trang_thai FROM viec WHERE id=?", (id,)).fetchone()
            if r is None:
                raise SaiTrangThai(f"việc {id}: không có")
            tt = r["trang_thai"]
            if tt not in TRANG_THAI_DONG:
                raise ThamSoLoi(f"việc {id}: chỉ ẩn/bỏ ẩn được việc đã kết thúc (xong/lỗi/huỷ), đang {tt!r}")
            c.execute("UPDATE viec SET luu_tru=? WHERE id=?", (1 if luu_tru else 0, id))
            mac_dinh = "ẩn/lưu trữ từ web" if luu_tru else "bỏ ẩn/lưu trữ từ web"
            self._ghi_su_kien(c, id, tt, tt, boi, ghi_chu or mac_dinh)
            return self._lay(c, id)  # type: ignore[return-value]

    def nhan_viec_ke(self, lan_chay: str, tai_nguyen_ban: set[str],
                     tai_nguyen_cua: Callable[[str], frozenset[str]]) -> dict | None:
        """Nhận job `cho` FIFO đầu tiên của làn mà mọi tài nguyên đều rảnh → `dang_chay` (CAS)."""
        if lan_chay not in LAN_CHAY:
            raise ThamSoLoi(f"làn lạ: {lan_chay!r}")
        with self._gd() as c:
            ds = c.execute("SELECT id, loai FROM viec WHERE trang_thai='cho' AND lan_chay=? ORDER BY tao_luc, rowid",
                           (lan_chay,)).fetchall()
            for r in ds:
                try:
                    tn = tai_nguyen_cua(r["loai"])
                except Exception:  # loại lạ trong DB không được làm sập cả làn — bỏ qua job này, ghi log
                    log.exception("không xác định được tài nguyên của việc %s (loại %s) — bỏ qua", r["id"], r["loai"])
                    continue
                if set(tn) & set(tai_nguyen_ban):
                    continue
                luc = self._luc()
                cur = c.execute("UPDATE viec SET trang_thai='dang_chay', bat_dau_luc=?, cap_nhat_luc=? "
                                "WHERE id=? AND trang_thai='cho'", (luc, luc, r["id"]))
                if cur.rowcount != 1:
                    continue
                self._ghi_su_kien(c, r["id"], "cho", "dang_chay", "he_thong", f"làn {lan_chay} nhận")
                return self._lay(c, r["id"])
        return None

    def _cap_nhat(self, id: str, sql_set: str, ts: tuple) -> None:
        with self._gd() as c:
            cur = c.execute(f"UPDATE viec SET {sql_set}, cap_nhat_luc=? WHERE id=?", (*ts, self._luc(), id))
            if cur.rowcount != 1:
                raise SaiTrangThai(f"không có việc {id}")

    def ghi_tien_trinh(self, id: str, pid: int | None, pid_tao_luc: float | None) -> None:
        self._cap_nhat(id, "pid=?, pid_tao_luc=?", (pid, pid_tao_luc))

    def danh_dau_phien(self, id: str) -> None:
        self._cap_nhat(id, "phien_da_tao=1", ())

    def cong_chi_phi(self, id: str, usd: float, so_luot: int, them_lan: bool) -> None:
        self._cap_nhat(id, "chi_phi_usd=chi_phi_usd+?, so_luot_claude=so_luot_claude+?, so_lan_claude=so_lan_claude+?",
                       (float(usd or 0), int(so_luot or 0), 1 if them_lan else 0))

    def them_tra_loi(self, id: str, boi: str, cau_hoi: str, noi_dung: str) -> None:
        with self._gd() as c:
            c.execute("INSERT INTO tra_loi(viec_id, luc, boi, cau_hoi, noi_dung) VALUES(?,?,?,?,?)",
                      (id, self._luc(), boi, cau_hoi, noi_dung))

    # ---------- sổ "đã tiêu" cục bộ (D9, §10) ----------
    @staticmethod
    def _co_trong_so(c: sqlite3.Connection, cac_khoa: tuple[str, str]) -> bool:
        return c.execute("SELECT 1 FROM da_tieu WHERE khoa IN (?,?) LIMIT 1", cac_khoa).fetchone() is not None

    def da_tieu_cuc_bo(self, chu_ky_duyet: str) -> bool:
        """Lời duyệt này đã tiêu trên máy này chưa (lớp chặn sớm; sổ thật nằm trên Worker KV).
        Nhận ra cả dòng ghi theo khoá cũ. Chuỗi không chuẩn → ThamSoLoi (bên gọi KHÔNG được chạy)."""
        return self._co_trong_so(self._ket_noi(), _cac_khoa_tieu(chu_ky_duyet))

    def danh_dau_da_tieu(self, chu_ky_duyet: str, id: str) -> None:
        """Ghi sổ cục bộ mà KHÔNG tăng so_lan_tieu (Worker báo 409: lời duyệt đã tiêu ở lần trước).
        Đã có (khoá mới hoặc cũ) → không thêm dòng."""
        cac_khoa = _cac_khoa_tieu(chu_ky_duyet)
        with self._gd() as c:
            if not self._co_trong_so(c, cac_khoa):
                c.execute("INSERT INTO da_tieu(khoa, viec_id, luc) VALUES(?,?,?)", (cac_khoa[0], id, self._luc()))

    def luc_tieu_theo_viec(self, ids: Sequence[str]) -> dict[str, list[str]]:
        """{viec_id: [luc của từng dòng da_tieu, tăng dần]} cho các việc trong `ids` (việc không có dòng → vắng mặt).
        Mỗi dòng = một lần lời duyệt của việc bị tiêu (ghi_tieu) hoặc được Worker báo đã tiêu (danh_dau_da_tieu)."""
        kq: dict[str, list[str]] = {}
        ds_id = list(dict.fromkeys(ids))
        c = self._ket_noi()
        for i in range(0, len(ds_id), _SQL_THAM_SO_TOI_DA):
            phan = ds_id[i:i + _SQL_THAM_SO_TOI_DA]
            for r in c.execute(f"SELECT viec_id, luc FROM da_tieu WHERE viec_id IN ({','.join('?' * len(phan))})"
                               " ORDER BY luc, rowid", phan):
                kq.setdefault(r[0], []).append(r[1])
        return kq

    def ghi_tieu(self, id: str, chu_ky_duyet: str) -> dict:
        """Worker đã nhận tiêu (200 + chữ ký đúng): MỘT giao dịch ghi sổ cục bộ + so_lan_tieu += 1 + tieu_luc_dau (nếu
        rỗng). Lời duyệt đã có trong sổ (khoá mới hoặc cũ) hoặc không có việc → SaiTrangThai, không ghi gì (bên gọi
        KHÔNG được chạy). Chuỗi không chuẩn → ThamSoLoi, không ghi gì."""
        k, k_cu = _cac_khoa_tieu(chu_ky_duyet)
        luc = self._luc()
        with self._gd() as c:
            if self._co_trong_so(c, (k, k_cu)):
                raise SaiTrangThai(f"việc {id}: lời duyệt đã có trong sổ đã tiêu")
            cur = c.execute("INSERT OR IGNORE INTO da_tieu(khoa, viec_id, luc) VALUES(?,?,?)", (k, id, luc))
            if cur.rowcount != 1:
                raise SaiTrangThai(f"việc {id}: lời duyệt đã có trong sổ đã tiêu")
            cur = c.execute("UPDATE viec SET so_lan_tieu=so_lan_tieu+1, tieu_luc_dau=COALESCE(tieu_luc_dau, ?),"
                            " cap_nhat_luc=? WHERE id=?", (luc, luc, id))
            if cur.rowcount != 1:
                raise SaiTrangThai(f"không có việc {id}")
            return self._lay(c, id)  # type: ignore[return-value]

    def dung_nonce(self, nonce: str, luc: float) -> bool:
        """Đánh dấu nonce đã dùng. False nếu đã dùng trước đó (phát lại).

        Kèm dọn định kỳ (R-05 P3-9): khi ghi được nonce MỚI, xoá tối đa NONCE_DON_TOI_DA dòng có
        `luc < luc_moi - NONCE_SONG_S` trong cùng giao dịch. Thời gian sống 1 ngày ≫ cửa sổ lệch giờ
        2×120 s của chu_ky, nên nonce còn có thể bị phát lại hợp lệ không bao giờ bị xoá.
        """
        luc = float(luc)
        with self._gd() as c:
            cur = c.execute("INSERT OR IGNORE INTO nonce(gia_tri, luc) VALUES(?,?)", (nonce, luc))
            moi = cur.rowcount == 1
            if moi:
                c.execute("DELETE FROM nonce WHERE rowid IN "
                          "(SELECT rowid FROM nonce WHERE luc < ? LIMIT ?)",
                          (luc - self.NONCE_SONG_S, self.NONCE_DON_TOI_DA))
            return moi

    # ---------- bản sửa video (đợt 6, docs/sua-video.md §7.3) ----------
    def luu_ban_sua(self, id: str, uid: str, du_an: str, ma_video: str, noi_dung: dict, boi: str) -> dict:
        """Lưu bản sửa ĐÃ qua `sua_video.kiem_ban_sua` (id = ma_ban_sua(noi_dung), bên gọi tính).
        Đã có cùng id: dữ liệu khớp → trả dòng cũ (gửi lại vô hại); khác → ThamSoLoi (không bao giờ ghi đè)."""
        _kiem_id_ban_sua(id)
        if not isinstance(uid, str) or not _RE_UID.fullmatch(uid):
            raise ThamSoLoi("uid phải là 19 chữ số")
        if not isinstance(du_an, str) or not _RE_DU_AN.fullmatch(du_an):
            raise ThamSoLoi("du_an phải là 12 hex")
        if not isinstance(ma_video, str) or not _RE_MA_VIDEO.fullmatch(ma_video):
            raise ThamSoLoi("ma_video phải là 16 hex")
        if not isinstance(noi_dung, dict):
            raise ThamSoLoi("noi_dung bản sửa phải là object")
        if not isinstance(boi, str) or not boi:
            raise ThamSoLoi("thiếu người tạo bản sửa")
        nd = _json_chuan(noi_dung)
        with self._gd() as c:
            c.execute("INSERT OR IGNORE INTO ban_sua(id, uid, du_an, ma_video, noi_dung, tao_boi, tao_luc)"
                      " VALUES(?,?,?,?,?,?,?)", (id, uid, du_an, ma_video, nd, boi, self._luc()))
            r = c.execute(_SQL_LAY_BAN_SUA, (id,)).fetchone()
            if tuple(r[k] for k in ("uid", "du_an", "ma_video", "noi_dung")) != (uid, du_an, ma_video, nd):
                raise ThamSoLoi("mã bản sửa đã dùng cho dữ liệu khác")
            return _ban_sua_thanh_dict(tuple(r), _COT_BAN_SUA)

    def lay_ban_sua(self, id: str) -> dict | None:
        r = self._ket_noi().execute(_SQL_LAY_BAN_SUA, (_kiem_id_ban_sua(id),)).fetchone()
        return _ban_sua_thanh_dict(tuple(r), _COT_BAN_SUA) if r else None

    def don_cu(self, truoc: datetime) -> None:
        """Dọn lúc khởi động (§4.5 bước 3): nonce trước `truoc`; ban_sua cũ hơn BAN_SUA_GIU_NGAY ngày (tính theo
        bay_gio) trừ bản mà một việc còn mở đang trỏ tới (lap_buoc của việc đó còn cần)."""
        moc_ban_sua = (gio_vn(self.bay_gio()) - timedelta(days=BAN_SUA_GIU_NGAY)).isoformat(timespec="seconds")
        with self._gd() as c:
            c.execute("DELETE FROM nonce WHERE luc < ?", (gio_vn(truoc).timestamp(),))
            n = c.execute(
                f"DELETE FROM ban_sua WHERE tao_luc < ? AND id NOT IN (SELECT json_extract(tham_so, '$.ban_sua') "
                f"FROM viec WHERE trang_thai IN ({','.join('?' * len(DANG_MO))}) "
                "AND json_extract(tham_so, '$.ban_sua') IS NOT NULL)", (moc_ban_sua, *DANG_MO)).rowcount
            if n:
                log.info("đã xoá %d bản sửa video cũ hơn %d ngày", n, BAN_SUA_GIU_NGAY)
