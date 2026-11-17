"""Kho việc SQLite (WAL, CAS) — docs/bo-chay-viec.md §4.2–4.5.

Nguyên tắc:
- Mỗi luồng một kết nối riêng (threading.local).
- Mọi chuyển trạng thái là CAS `UPDATE … WHERE id=? AND trang_thai IN (…)`; rowcount 0 → SaiTrangThai.
- Không bao giờ đổi tên / xoá / tạo lại DB khi gặp lỗi: trạng thái và khoá chống trùng không được "quên".
"""
from __future__ import annotations

import json
import logging
import secrets
import sqlite3
import string
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from contextlib import contextmanager

from .kieu import DANG_MO, LAN_CHAY, TRANG_THAI, CanNguoiDung, SaiTrangThai, ThamSoLoi, TrungViec, gio_vn

log = logging.getLogger(__name__)

PHIEN_BAN_SCHEMA = "1"

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
  chi_phi_usd REAL NOT NULL DEFAULT 0, so_luot_claude INTEGER NOT NULL DEFAULT 0, so_lan_claude INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS viec_dang_mo ON viec(loai, khoa)
  WHERE trang_thai IN ('cho','dang_chay','can_tra_loi','cho_duyet');
CREATE INDEX IF NOT EXISTS viec_tt ON viec(trang_thai, lan_chay, tao_luc);
CREATE TABLE IF NOT EXISTS su_kien(id INTEGER PRIMARY KEY AUTOINCREMENT, viec_id TEXT NOT NULL REFERENCES viec(id),
  luc TEXT NOT NULL, tu TEXT, den TEXT NOT NULL, boi TEXT NOT NULL, ghi_chu TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS tra_loi(id INTEGER PRIMARY KEY AUTOINCREMENT, viec_id TEXT NOT NULL REFERENCES viec(id),
  luc TEXT NOT NULL, boi TEXT NOT NULL, cau_hoi TEXT NOT NULL, noi_dung TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS nonce(gia_tri TEXT PRIMARY KEY, luc REAL NOT NULL);
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


def _dong_thanh_dict(r: sqlite3.Row) -> dict:
    d = dict(r)
    for c in COT_JSON:
        if c in d and d[c] is not None:
            d[c] = json.loads(d[c])
    return d


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

    def ds(self, trang_thai: Sequence[str] | None = None, khoa: str | None = None, gioi_han: int = 50) -> list[dict]:
        dk, ts = [], []
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
        gioi_han = max(1, min(int(gioi_han), 500))
        sql = "SELECT * FROM viec" + (" WHERE " + " AND ".join(dk) if dk else "") + \
              " ORDER BY tao_luc DESC, rowid DESC LIMIT ?"
        return [_dong_thanh_dict(r) for r in self._ket_noi().execute(sql, (*ts, gioi_han))]

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

    def don_cu(self, truoc: datetime) -> None:
        with self._gd() as c:
            c.execute("DELETE FROM nonce WHERE luc < ?", (gio_vn(truoc).timestamp(),))
