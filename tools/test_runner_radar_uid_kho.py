"""Test kho `radar_uid.db` (RU-B2, docs/radar-uid.md §4, §6.2-§6.5, §7).

Chạy: python -B -m pytest tools/test_runner_radar_uid_kho.py -q -p no:cacheprovider
Mọi DB chỉ nằm trong tmp_path; không mở DB thật, không gọi mạng.
"""
from __future__ import annotations

import ast
import sqlite3
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from runner import kho_radar_uid
from runner.kho_radar_uid import (GOC_TOI_DA, THEM_TAY_TOI_DA, TUONG_TU_TOI_DA, UID_TOI_DA, ChiDoc, KhoRadarUid,
                                  KhongCoRadar, SaiTrangThaiRadar)
from runner.kieu import MUI_GIO_VN, ThamSoLoi

NGAY = "2026-12-01"


def uid(i: int) -> str:
    """UID 19 số (> 2^53) để bắt lỗi lỡ đi qua số."""
    return f"17297066286569{i:05d}"


class Dong:
    def __init__(self, luc: datetime):
        self.luc = luc

    def __call__(self) -> datetime:
        return self.luc


@pytest.fixture
def dong():
    return Dong(datetime(2026, 12, 1, 12, 0, 0, tzinfo=MUI_GIO_VN))


@pytest.fixture
def kho(tmp_path, dong):
    k = KhoRadarUid(tmp_path / "radar_uid.db", dong)
    k.mo()
    yield k
    k.dong()


def _sql(kho: KhoRadarUid, cau: str, tham: tuple = ()) -> list[sqlite3.Row]:
    c = sqlite3.connect(kho.duong_dan)
    c.row_factory = sqlite3.Row
    try:
        return c.execute(cau, tham).fetchall()
    finally:
        c.close()


def _hv(i: int, **kw) -> dict:
    d = {"video_id": f"7300000000000000{i:03d}", "creator": f"c{i}", "follower": "2.54K", "view": "21.81K",
         "ban": None, "dang_luc": "2026-07-18 10:00:00", "is_promote": False}
    d.update(kw)
    return d


def _snap(u: str, ngay: str = NGAY, n: int = 3, lay_luc: str | None = None, **kw) -> dict:
    s = {"uid": u, "ngay": ngay, "lay_luc": lay_luc or f"{ngay}T10:00:00+07:00", "echotik_cap_nhat": "2026-11-22 07:55",
         "ban_tong": "10.17K", "gia": "499.390₫", "hoa_hong": "10%", "ton": "562", "tong_creator": None,
         "so_trang": 1, "tong_trang": 1, "videos": {h["video_id"]: h for h in (_hv(i) for i in range(n))}}
    s.update(kw)
    return s


def _chup_ok(kho: KhoRadarUid, u: str, ngay: str, lay_luc: str | None = None) -> None:
    ll = lay_luc or f"{ngay}T10:00:00+07:00"
    assert kho.bat_dau_chup(u, ngay, ll)
    kho.ghi_chup_ok(_snap(u, ngay, lay_luc=ll))


def _nhom_da_tim(kho: KhoRadarUid, goc: str, tuong_tu: list[str]) -> None:
    kho.them_goc(goc, "chu")
    kho.ghi_tuong_tu(goc, [{"uid": u, "ten": f"sp {u[-3:]}", "gia": None, "ban_7d": None} for u in tuong_tu],
                     "2026-12-01T10:00:00+07:00")
    kho.dat_trang_thai_nhom(goc, "da_tim")


# ---------------------------------------------------------------------------------------------------------------
# Mở / schema / chỉ đọc
# ---------------------------------------------------------------------------------------------------------------
def test_khoi_tao_khong_mo_file(tmp_path, dong):
    duong = tmp_path / "con" / "radar_uid.db"
    KhoRadarUid(duong, dong)
    KhoRadarUid(duong, dong, chi_doc=True)
    assert not duong.exists() and not duong.parent.exists()


def test_tu_du_khong_import_radar_uid_tinh_va_co_re_uid_rieng():
    nguon = Path(kho_radar_uid.__file__).read_text(encoding="utf-8")
    ten = set()
    for n in ast.walk(ast.parse(nguon)):
        if isinstance(n, ast.Import):
            ten |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            ten.add(("." * n.level) + (n.module or ""))
            ten |= {a.name for a in n.names}
    assert not any("radar_uid_tinh" in t for t in ten)
    assert kho_radar_uid.RE_UID.pattern.startswith("^\\d{19}")
    assert kho_radar_uid.RE_UID.fullmatch("1729706628656957720") and not kho_radar_uid.RE_UID.fullmatch("123")


def test_hang_so_gioi_han():
    assert (GOC_TOI_DA, TUONG_TU_TOI_DA, THEM_TAY_TOI_DA, UID_TOI_DA) == (2, 10, 3, 24)


def test_schema_dung_dac_ta_khong_co_update_time_video(kho):
    ten = {r["name"] for r in _sql(kho, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"meta", "san_pham", "nhom", "lien_ket", "chup_uid", "chup_video", "lan_chay", "goi_ngay", "token_tt",
            "su_kien"} <= ten
    cot = {r["name"] for r in _sql(kho, "PRAGMA table_info(chup_video)")}
    assert cot == {"uid", "ngay", "video_id", "creator", "follower", "view", "ban", "dang_luc", "is_promote"}
    assert "update_time" not in cot
    cot_uid = {r["name"] for r in _sql(kho, "PRAGMA table_info(chup_uid)")}
    assert cot_uid == {"uid", "ngay", "trang_thai", "ma_loi", "lay_luc", "echotik_cap_nhat", "ban_tong", "gia",
                       "hoa_hong", "ton", "tong_creator", "so_trang", "tong_trang", "so_lan_thu"}
    assert {r["name"] for r in _sql(kho, "PRAGMA table_info(lan_chay)")} == {
        "ngay", "che_do", "viec_id", "trang_thai", "ly_do", "bat_dau", "ket_thuc", "so_goi"}
    assert _sql(kho, "SELECT v FROM meta WHERE k='schema_ban'")[0]["v"] == "2"
    assert kho_radar_uid.PHIEN_BAN_SCHEMA == "2"
    assert {r["name"] for r in _sql(kho, "PRAGMA table_info(san_pham)")} == {
        "uid", "ten", "shop", "cap_nhat_luc", "anh", "anh_luc"}
    assert _sql(kho, "PRAGMA journal_mode")[0][0] == "wal"


def test_mo_lap_lai_an_toan_va_giu_du_lieu(kho):
    kho.them_goc(uid(1), "chu")
    kho.mo()
    kho.mo()
    assert [n["goc"] for n in kho.ds_nhom()] == [uid(1)]
    assert len(_sql(kho, "SELECT * FROM meta")) == 1


def test_schema_la_bao_loi_khong_tu_xoa(kho):
    c = sqlite3.connect(kho.duong_dan)
    c.execute("UPDATE meta SET v='9' WHERE k='schema_ban'")
    c.commit()
    c.close()
    kho.dong()
    with pytest.raises(RuntimeError, match="schema"):
        kho.mo()


def test_chi_doc_thieu_file_khong_tao_file_va_coi_nhu_rong(tmp_path, dong):
    duong = tmp_path / "radar_uid.db"
    k = KhoRadarUid(duong, dong, chi_doc=True)
    assert k.ds_nhom() == [] and k.ds_can_chup(NGAY) == [] and k.doc_snapshots(uid(1), NGAY) == []
    assert k.goi_hom_nay(NGAY) == 0 and k.lan_gan_nhat() is None and k.lan_cua_viec(NGAY, "nap", "j1") is None
    assert k.doc_token()["trang_thai"] == "chua_kiem"
    with pytest.raises(KhongCoRadar):
        k.uid_cua_nhom(uid(1))
    with pytest.raises(ChiDoc):
        k.mo()
    with pytest.raises(ChiDoc):
        k.them_goc(uid(1), "chu")
    assert not duong.exists()


def test_chi_doc_doc_duoc_db_co_san_va_moi_ham_ghi_bi_chan(tmp_path, dong):
    ghi = KhoRadarUid(tmp_path / "radar_uid.db", dong)
    ghi.mo()
    _nhom_da_tim(ghi, uid(1), [uid(2)])
    ghi.dong()
    doc = KhoRadarUid(tmp_path / "radar_uid.db", dong, chi_doc=True)
    assert [n["goc"] for n in doc.ds_nhom()] == [uid(1)]
    assert [x["uid"] for x in doc.uid_cua_nhom(uid(1))] == [uid(1), uid(2)]
    lenh = [
        lambda: doc.them_goc(uid(5), "x"), lambda: doc.them_tay(uid(1), uid(5), "x"),
        lambda: doc.dat_uid(uid(1), uid(2), "ghim", "x"), lambda: doc.dat_goc(uid(1), "ngung", "x"),
        lambda: doc.dat_trang_thai_nhom(uid(1), "da_tim"), lambda: doc.ghi_san_pham(uid(1), "a", "b"),
        lambda: doc.ghi_tuong_tu(uid(1), [], "2026-12-01T10:00:00+07:00"),
        lambda: doc.bat_dau_chup(uid(1), NGAY, "2026-12-01T10:00:00+07:00"), lambda: doc.ghi_chup_ok(_snap(uid(1))),
        lambda: doc.ghi_chup_loi(uid(1), NGAY, "x"), lambda: doc.tinh_goi(NGAY, 1, 60),
        lambda: doc.bat_dau_lan(NGAY, "nap", "j1"), lambda: doc.ket_thuc_lan(NGAY, "nap", "j1", "xong", "", 0),
        lambda: doc.ghi_token("ok", ""),
    ]
    for f in lenh:
        with pytest.raises(ChiDoc):
            f()
    doc.dong()


def test_moi_luong_mot_ket_noi(kho):
    kho.them_goc(uid(1), "chu")
    ket: dict = {}

    def doc_o_luong_khac() -> None:
        try:
            ket["nhom"] = kho.ds_nhom()
        finally:
            kho.dong()

    t = threading.Thread(target=doc_o_luong_khac)
    t.start()
    t.join()
    assert [n["goc"] for n in ket["nhom"]] == [uid(1)]


# ---------------------------------------------------------------------------------------------------------------
# Nhóm gốc
# ---------------------------------------------------------------------------------------------------------------
def test_them_goc_ghi_san_pham_nhom_lien_ket_va_id_la_chuoi(kho):
    assert kho.them_goc(uid(1), "chu") == {"da_co": False, "goc": uid(1)}
    nh = kho.ds_nhom()[0]
    assert nh["goc"] == uid(1) and nh["trang_thai"] == "cho_tim" and nh["bat_dau_ngay"] == NGAY
    assert nh["them_boi"] == "chu" and nh["tim_luc"] is None
    lk = kho.uid_cua_nhom(uid(1))
    assert [(x["uid"], x["vai"], x["trang_thai"]) for x in lk] == [(uid(1), "goc", "dang_theo")]
    assert _sql(kho, "SELECT typeof(uid) t FROM san_pham")[0]["t"] == "text"
    assert _sql(kho, "SELECT typeof(goc) t FROM nhom")[0]["t"] == "text"
    assert isinstance(nh["goc"], str) and isinstance(lk[0]["uid"], str)


def test_them_goc_da_co_khong_ghi_lai_ke_ca_khi_da_ngung(kho):
    kho.them_goc(uid(1), "chu")
    assert kho.them_goc(uid(1), "khac") == {"da_co": True, "goc": uid(1)}
    kho.dat_goc(uid(1), "ngung", "chu")
    assert kho.them_goc(uid(1), "khac") == {"da_co": True, "goc": uid(1)}
    assert kho.ds_nhom()[0]["them_boi"] == "chu" and kho.ds_nhom()[0]["trang_thai"] == "ngung"


@pytest.mark.parametrize("sai", ["", "123", "17297066286569578x0", "１７２９７０６６２８６５６９５７７２０", 1729706628656957720, None,
                                 "1729706628656957720\n", "17297066286569577200"])
def test_them_goc_uid_sai_dang_la_loi_tham_so(kho, sai):
    with pytest.raises(ThamSoLoi, match="19 chữ số"):
        kho.them_goc(sai, "chu")
    assert kho.ds_nhom() == []


def test_them_goc_toi_da_2_va_cau_409_dung(kho):
    kho.them_goc(uid(1), "chu")
    kho.them_goc(uid(2), "chu")
    with pytest.raises(SaiTrangThaiRadar) as e:
        kho.them_goc(uid(3), "chu")
    assert e.value.loi == "Đã đủ 2 UID gốc: ngừng bớt" and str(e.value) == e.value.loi
    assert len(kho.ds_nhom()) == 2
    kho.dat_goc(uid(1), "ngung", "chu")                                   # ngừng bớt ⇒ có chỗ
    kho.them_goc(uid(3), "chu")
    assert len(kho.ds_nhom()) == 3


def test_ngung_roi_theo_lai_vuot_2_goc_la_409(kho):
    for i in (1, 2):
        kho.them_goc(uid(i), "chu")
    kho.dat_goc(uid(1), "ngung", "chu")
    kho.them_goc(uid(3), "chu")
    with pytest.raises(SaiTrangThaiRadar) as e:
        kho.dat_goc(uid(1), "theo-lai", "chu")
    assert e.value.loi == "Đã đủ 2 UID gốc: ngừng bớt"
    kho.dat_goc(uid(3), "ngung", "chu")
    assert kho.dat_goc(uid(1), "theo-lai", "chu") == {"goc": uid(1), "trang_thai": "cho_tim"}


def test_theo_lai_tra_ve_da_tim_neu_da_tung_tim(kho):
    _nhom_da_tim(kho, uid(1), [uid(2)])
    assert kho.dat_goc(uid(1), "ngung", "chu") == {"goc": uid(1), "trang_thai": "ngung"}
    assert kho.dat_goc(uid(1), "theo-lai", "chu") == {"goc": uid(1), "trang_thai": "da_tim"}
    assert kho.dat_goc(uid(1), "theo-lai", "chu") == {"goc": uid(1), "trang_thai": "da_tim"}     # đã theo: idempotent
    assert kho.dat_goc(uid(1), "ngung", "chu")["trang_thai"] == "ngung"
    assert kho.dat_goc(uid(1), "ngung", "chu")["trang_thai"] == "ngung"                          # idempotent


def test_dat_goc_loi(kho):
    with pytest.raises(KhongCoRadar) as e:
        kho.dat_goc(uid(9), "ngung", "chu")
    assert e.value.loi == "Không có UID này trong Radar"
    with pytest.raises(KhongCoRadar):
        kho.dat_goc("12", "ngung", "chu")
    kho.them_goc(uid(1), "chu")
    with pytest.raises(ThamSoLoi):
        kho.dat_goc(uid(1), "xoa", "chu")


def test_dat_trang_thai_nhom(kho):
    kho.them_goc(uid(1), "chu")
    kho.dat_trang_thai_nhom(uid(1), "dang_tim")
    assert kho.ds_nhom()[0]["trang_thai"] == "dang_tim"
    with pytest.raises(SaiTrangThaiRadar) as e:
        kho.dat_trang_thai_nhom(uid(1), "cho_tim")
    assert e.value.loi == "Nhóm đang được tìm: chờ xong"
    kho.dat_trang_thai_nhom(uid(1), "loi_tim", "keyword_khong_loc")
    nh = kho.ds_nhom()[0]
    assert (nh["trang_thai"], nh["ly_do"]) == ("loi_tim", "keyword_khong_loc")
    kho.dat_trang_thai_nhom(uid(1), "cho_tim")                            # tìm lại sau lỗi: được
    assert kho.ds_nhom()[0]["ly_do"] == ""
    with pytest.raises(ThamSoLoi):
        kho.dat_trang_thai_nhom(uid(1), "bay")
    with pytest.raises(ThamSoLoi):
        kho.dat_trang_thai_nhom(uid(1), "loi_tim", "Có dấu / token abc")
    with pytest.raises(KhongCoRadar):
        kho.dat_trang_thai_nhom(uid(9), "da_tim")


# ---------------------------------------------------------------------------------------------------------------
# Thêm tay / ghim / loại / giới hạn
# ---------------------------------------------------------------------------------------------------------------
def test_them_tay_toi_da_3_va_cau_dung(kho):
    kho.them_goc(uid(1), "chu")
    for i in (2, 3, 4):
        kho.them_tay(uid(1), uid(i), "chu")
    with pytest.raises(SaiTrangThaiRadar) as e:
        kho.them_tay(uid(1), uid(5), "chu")
    assert e.value.loi == "Đã đủ 3 UID thêm tay"
    kho.dat_uid(uid(1), uid(2), "loai", "chu")                            # loại một ⇒ có chỗ
    kho.them_tay(uid(1), uid(5), "chu")
    assert [x["vai"] for x in kho.uid_cua_nhom(uid(1))].count("them_tay") == 4        # 3 đang theo + 1 đã loại


def test_them_tay_idempotent_loi_404_va_dang_loai(kho):
    kho.them_goc(uid(1), "chu")
    kho.them_tay(uid(1), uid(2), "chu")
    kho.them_tay(uid(1), uid(2), "chu")
    assert len(kho.uid_cua_nhom(uid(1))) == 2
    kho.dat_uid(uid(1), uid(2), "loai", "chu")
    with pytest.raises(SaiTrangThaiRadar) as e:
        kho.them_tay(uid(1), uid(2), "chu")
    assert e.value.loi == "UID này đang bị loại: bỏ loại trước"
    with pytest.raises(KhongCoRadar):
        kho.them_tay(uid(9), uid(3), "chu")
    with pytest.raises(ThamSoLoi, match="19 chữ số"):
        kho.them_tay(uid(1), "abc", "chu")


def test_tran_24_uid_toan_db(kho):
    # goc1: 1 + 10 tương tự + 3 thêm tay = 14; goc2: 1 + 9 tương tự = 10 ⇒ 24
    kho.them_goc(uid(1), "chu")
    kho.ghi_tuong_tu(uid(1), [{"uid": uid(100 + i), "ten": "a", "gia": None, "ban_7d": None} for i in range(10)],
                     "2026-12-01T10:00:00+07:00")
    for i in range(3):
        kho.them_tay(uid(1), uid(200 + i), "chu")
    kho.them_goc(uid(2), "chu")
    assert kho.ghi_tuong_tu(uid(2), [{"uid": uid(300 + i), "ten": "a", "gia": None, "ban_7d": None} for i in range(9)],
                            "2026-12-01T10:00:00+07:00") == 9
    with pytest.raises(SaiTrangThaiRadar) as e:
        kho.them_tay(uid(2), uid(400), "chu")
    assert e.value.loi == "Đã đủ 24 UID theo dõi"
    kho.them_tay(uid(2), uid(100), "chu")                                 # UID đã được theo ở nhóm khác: không tăng số đếm
    kho.dat_uid(uid(1), uid(200), "loai", "chu")                          # loại 1 ⇒ còn chỗ cho UID mới
    kho.them_tay(uid(2), uid(400), "chu")


def test_ngung_nhom_nha_cho_uid_va_goc(kho):
    kho.them_goc(uid(1), "chu")
    kho.ghi_tuong_tu(uid(1), [{"uid": uid(100 + i), "ten": "a", "gia": None, "ban_7d": None} for i in range(10)],
                     "2026-12-01T10:00:00+07:00")
    kho.them_goc(uid(2), "chu")
    kho.ghi_tuong_tu(uid(2), [{"uid": uid(300 + i), "ten": "a", "gia": None, "ban_7d": None} for i in range(10)],
                     "2026-12-01T10:00:00+07:00")
    kho.them_tay(uid(2), uid(400), "chu")
    kho.them_tay(uid(2), uid(401), "chu")                                 # 11 + 13 = 24
    with pytest.raises(SaiTrangThaiRadar):
        kho.them_tay(uid(2), uid(402), "chu")
    kho.dat_goc(uid(1), "ngung", "chu")
    kho.them_tay(uid(2), uid(402), "chu")                                 # nhóm 1 ngừng nên đã nhả 11 UID
    with pytest.raises(SaiTrangThaiRadar) as e:                           # bật lại nhóm 1 sẽ vượt 24
        kho.dat_goc(uid(1), "theo-lai", "chu")
    assert e.value.loi == "Đã đủ 24 UID theo dõi"


def test_dat_uid_ghim_bo_ghim_loai_bo_loai(kho):
    _nhom_da_tim(kho, uid(1), [uid(2), uid(3)])
    assert kho.dat_uid(uid(1), uid(2), "ghim", "chu") == {"uid": uid(2), "trang_thai": "ghim"}
    assert kho.dat_uid(uid(1), uid(2), "bo-ghim", "chu") == {"uid": uid(2), "trang_thai": "dang_theo"}
    assert kho.dat_uid(uid(1), uid(3), "loai", "chu") == {"uid": uid(3), "trang_thai": "loai"}
    assert kho.dat_uid(uid(1), uid(3), "loai", "chu")["trang_thai"] == "loai"             # idempotent
    assert kho.dat_uid(uid(1), uid(3), "bo-loai", "chu") == {"uid": uid(3), "trang_thai": "dang_theo"}
    assert kho.dat_uid(uid(1), uid(3), "bo-loai", "chu")["trang_thai"] == "dang_theo"
    assert kho.dat_uid(uid(1), uid(3), "bo-ghim", "chu")["trang_thai"] == "dang_theo"
    kho.dat_uid(uid(1), uid(3), "loai", "chu")
    with pytest.raises(SaiTrangThaiRadar) as e:                           # không ghim thẳng một UID đang bị loại
        kho.dat_uid(uid(1), uid(3), "ghim", "chu")
    assert e.value.loi == "UID này đang bị loại: bỏ loại trước"


def test_dat_uid_khong_doi_duoc_goc_va_404(kho):
    _nhom_da_tim(kho, uid(1), [uid(2)])
    for hd in ("ghim", "bo-ghim", "loai", "bo-loai"):
        with pytest.raises(SaiTrangThaiRadar) as e:
            kho.dat_uid(uid(1), uid(1), hd, "chu")
        assert e.value.loi == "Không đổi được UID gốc"
    with pytest.raises(KhongCoRadar) as e2:
        kho.dat_uid(uid(1), uid(9), "ghim", "chu")
    assert e2.value.loi == "Không có UID này trong Radar"
    with pytest.raises(KhongCoRadar):
        kho.dat_uid(uid(9), uid(2), "ghim", "chu")
    with pytest.raises(KhongCoRadar):
        kho.dat_uid(uid(1), "12", "ghim", "chu")
    with pytest.raises(ThamSoLoi):
        kho.dat_uid(uid(1), uid(2), "xoa", "chu")


def test_bo_loai_vuot_10_tuong_tu_la_409(kho):
    kho.them_goc(uid(1), "chu")
    ds = [{"uid": uid(100 + i), "ten": "a", "gia": None, "ban_7d": None} for i in range(10)]
    kho.ghi_tuong_tu(uid(1), ds, "2026-12-01T10:00:00+07:00")
    kho.dat_uid(uid(1), uid(100), "loai", "chu")
    moi = ds[1:] + [{"uid": uid(110), "ten": "a", "gia": None, "ban_7d": None}]
    assert kho.ghi_tuong_tu(uid(1), moi, "2026-12-02T10:00:00+07:00") == 10     # uid(100) đang loại ⇒ không chọn lại
    with pytest.raises(SaiTrangThaiRadar) as e:
        kho.dat_uid(uid(1), uid(100), "bo-loai", "chu")
    assert e.value.loi == "Đã đủ 10 UID tương tự"
    kho.dat_uid(uid(1), uid(101), "loai", "chu")
    assert kho.dat_uid(uid(1), uid(100), "bo-loai", "chu")["trang_thai"] == "dang_theo"


def test_su_kien_ghi_moi_lenh_ghi_nguoi_dung(kho):
    kho.them_goc(uid(1), "chu")
    kho.them_tay(uid(1), uid(2), "chu")
    kho.dat_uid(uid(1), uid(2), "ghim", "chu")
    kho.dat_goc(uid(1), "ngung", "chu")
    ev = _sql(kho, "SELECT hanh_dong, boi, goc, uid FROM su_kien ORDER BY id")
    assert [e["hanh_dong"] for e in ev] == ["them_goc", "them_tay", "ghim", "ngung"]
    assert all(e["boi"] == "chu" and e["goc"] == uid(1) for e in ev)


# ---------------------------------------------------------------------------------------------------------------
# Sản phẩm / tương tự
# ---------------------------------------------------------------------------------------------------------------
def test_ghi_san_pham_bo_ky_tu_dieu_khien_cat_200_va_cap_nhat(kho):
    kho.them_goc(uid(1), "chu")
    kho.ghi_san_pham(uid(1), "Kẹp\x00 tóc\n\x1f", "Shop\x7f A")
    r = _sql(kho, "SELECT ten, shop, cap_nhat_luc FROM san_pham WHERE uid=?", (uid(1),))[0]
    assert (r["ten"], r["shop"]) == ("Kẹp tóc", "Shop A") and r["cap_nhat_luc"].startswith(NGAY)
    kho.ghi_san_pham(uid(1), "x" * 500, "")
    assert _sql(kho, "SELECT length(ten) n FROM san_pham")[0]["n"] == 200
    kho.ghi_san_pham(uid(7), "mới", "s")                                  # chưa có dòng ⇒ tạo
    assert len(_sql(kho, "SELECT * FROM san_pham")) == 2
    with pytest.raises(ThamSoLoi):
        kho.ghi_san_pham("12", "a", "b")
    with pytest.raises(ThamSoLoi):
        kho.ghi_san_pham(uid(1), 5, "b")


def test_ghi_tuong_tu_giu_ghim_them_tay_loai_va_bo_qua_goc_trung(kho):
    kho.them_goc(uid(1), "chu")
    kho.ghi_tuong_tu(uid(1), [{"uid": uid(i), "ten": f"t{i}", "gia": "$1", "ban_7d": "3", "do_giong": 0.5 + i / 100}
                              for i in (2, 3, 4, 5)], "2026-12-01T10:00:00+07:00")
    kho.dat_uid(uid(1), uid(2), "ghim", "chu")
    kho.dat_uid(uid(1), uid(3), "loai", "chu")
    kho.them_tay(uid(1), uid(6), "chu")
    n = kho.ghi_tuong_tu(uid(1), [
        {"uid": uid(1), "ten": "gốc", "gia": None, "ban_7d": None},       # là gốc: bỏ
        {"uid": uid(3), "ten": "đã loại", "gia": None, "ban_7d": None},   # đang bị loại: không chọn lại
        {"uid": uid(2), "ten": "ghim", "gia": None, "ban_7d": None},      # đang ghim: không ghi đôi
        {"uid": uid(6), "ten": "thêm tay", "gia": None, "ban_7d": None},  # thêm tay: giữ vai
        {"uid": uid(7), "ten": "mới", "gia": None, "ban_7d": None},
        {"uid": uid(7), "ten": "mới lặp", "gia": None, "ban_7d": None},   # trùng trong ds: một lần
        {"uid": "abc", "ten": "sai dạng", "gia": None, "ban_7d": None},
        {"uid": uid(8), "ten": "mới 2", "gia": None, "ban_7d": None},
    ], "2026-12-02T10:00:00+07:00")
    assert n == 2
    lk = {x["uid"]: (x["vai"], x["trang_thai"]) for x in kho.uid_cua_nhom(uid(1))}
    assert lk == {uid(1): ("goc", "dang_theo"), uid(2): ("tuong_tu", "ghim"), uid(3): ("tuong_tu", "loai"),
                  uid(6): ("them_tay", "dang_theo"), uid(7): ("tuong_tu", "dang_theo"),
                  uid(8): ("tuong_tu", "dang_theo")}                      # uid(4), uid(5) bị thay ⇒ không còn
    assert kho.ds_nhom()[0]["tim_luc"] == "2026-12-02T10:00:00+07:00"
    assert _sql(kho, "SELECT ten FROM san_pham WHERE uid=?", (uid(7),))[0]["ten"] == "mới"
    assert _sql(kho, "SELECT typeof(uid) t FROM lien_ket WHERE uid=?", (uid(7),))[0]["t"] == "text"


def test_ghi_tuong_tu_toi_da_10_gom_ca_ghim(kho):
    kho.them_goc(uid(1), "chu")
    ds = [{"uid": uid(100 + i), "ten": "a", "gia": None, "ban_7d": None} for i in range(14)]
    assert kho.ghi_tuong_tu(uid(1), ds, "2026-12-01T10:00:00+07:00") == 10
    for i in (0, 1, 2):
        kho.dat_uid(uid(1), uid(100 + i), "ghim", "chu")
    assert kho.ghi_tuong_tu(uid(1), ds[3:] + ds[:3], "2026-12-02T10:00:00+07:00") == 7      # 3 ghim chiếm chỗ
    tt = [x for x in kho.uid_cua_nhom(uid(1)) if x["vai"] == "tuong_tu"]
    assert len(tt) == 10 and sum(x["trang_thai"] == "ghim" for x in tt) == 3


def test_ghi_tuong_tu_do_giong_tuy_chon_va_loi(kho):
    kho.them_goc(uid(1), "chu")
    kho.ghi_tuong_tu(uid(1), [{"uid": uid(2), "ten": "a", "gia": None, "ban_7d": None, "do_giong": 0.67},
                              {"uid": uid(3), "ten": "b", "gia": None, "ban_7d": None}], "2026-12-01T10:00:00+07:00")
    dg = {x["uid"]: x["do_giong"] for x in kho.uid_cua_nhom(uid(1))}
    assert dg[uid(2)] == pytest.approx(0.67) and dg[uid(3)] is None and dg[uid(1)] is None
    with pytest.raises(KhongCoRadar):
        kho.ghi_tuong_tu(uid(9), [], "2026-12-01T10:00:00+07:00")
    with pytest.raises(ThamSoLoi):
        kho.ghi_tuong_tu(uid(1), [], "hôm qua")


def test_ghi_tuong_tu_dung_o_tran_uid_khong_nem_loi(kho):
    kho.them_goc(uid(1), "chu")
    kho.ghi_tuong_tu(uid(1), [{"uid": uid(100 + i), "ten": "a", "gia": None, "ban_7d": None} for i in range(10)],
                     "2026-12-01T10:00:00+07:00")
    for i in range(3):
        kho.them_tay(uid(1), uid(200 + i), "chu")                         # nhóm 1 = 14
    kho.them_goc(uid(2), "chu")                                           # 15
    n = kho.ghi_tuong_tu(uid(2), [{"uid": uid(300 + i), "ten": "a", "gia": None, "ban_7d": None} for i in range(10)],
                         "2026-12-01T10:00:00+07:00")
    assert n == 9                                                         # chỉ còn 9 chỗ tới 24
    assert len({x["uid"] for g in (uid(1), uid(2)) for x in kho.uid_cua_nhom(g)}) == UID_TOI_DA


# ---------------------------------------------------------------------------------------------------------------
# Chụp: thứ tự xoay, bat_dau_chup, ghi_chup_ok
# ---------------------------------------------------------------------------------------------------------------
def test_ds_can_chup_chua_tung_chup_dung_dau_roi_cu_nhat_truoc(kho):
    _nhom_da_tim(kho, uid(1), [uid(2), uid(3), uid(4)])
    # uid(1) chụp ok hôm kia, uid(2) hôm qua, uid(3) chụp cũ nhất, uid(4) chưa từng
    _chup_ok(kho, uid(1), "2026-11-29")
    _chup_ok(kho, uid(2), "2026-11-30")
    _chup_ok(kho, uid(3), "2026-11-28")
    assert kho.ds_can_chup(NGAY) == [uid(4), uid(3), uid(1), uid(2)]
    _chup_ok(kho, uid(4), NGAY)                                           # chụp xong thì rời danh sách
    assert kho.ds_can_chup(NGAY) == [uid(3), uid(1), uid(2)]


def test_ds_can_chup_xoay_giua_cac_ngay_khong_co_dinh_thu_tu(kho):
    """Trần ngân sách chỉ đủ 2 UID/ngày: không UID nào bị đói."""
    uids = [uid(1), uid(2), uid(3), uid(4)]
    _nhom_da_tim(kho, uids[0], uids[1:])
    da_chup: list[str] = []
    for d in range(4):
        ngay = (datetime.fromisoformat(NGAY) + timedelta(days=d)).date().isoformat()
        for u in kho.ds_can_chup(ngay)[:2]:
            _chup_ok(kho, u, ngay)
            da_chup.append(u)
    assert set(da_chup[:4]) == set(uids)                                  # hai ngày đầu phủ đủ 4 UID
    assert set(da_chup[4:]) == set(uids)                                  # hai ngày sau lại phủ đủ
    assert da_chup[4:] == da_chup[:4]                                     # vòng xoay ổn định: cũ nhất lại đi trước


def test_ds_can_chup_loc_nhom_trang_thai_loai_va_trung(kho):
    _nhom_da_tim(kho, uid(1), [uid(2), uid(3)])
    kho.dat_uid(uid(1), uid(3), "loai", "chu")
    kho.them_goc(uid(10), "chu")                                          # cho_tim: thuộc luồng nạp
    kho.them_tay(uid(10), uid(2), "chu")                                  # UID dùng chung hai nhóm: khử trùng
    assert kho.ds_can_chup(NGAY) == [uid(1), uid(2)]
    assert kho.ds_can_chup(NGAY, goc=uid(10)) == [uid(2), uid(10)]        # luồng nạp: chỉ nhóm đó, mọi trạng thái trừ ngung
    kho.dat_trang_thai_nhom(uid(10), "dang_tim", "")
    assert kho.ds_can_chup(NGAY) == [uid(1), uid(2)]                      # dang_tim: thuộc luồng nạp, không chụp hằng ngày
    kho.dat_goc(uid(1), "ngung", "chu")
    assert kho.ds_can_chup(NGAY) == []
    assert kho.ds_can_chup(NGAY, goc=uid(1)) == []
    with pytest.raises(ThamSoLoi):
        kho.ds_can_chup("hôm nay")


def test_ds_can_chup_nhom_loi_tim_van_chup_hang_ngay_ca_goc_va_uid_them_tay(kho):
    """R-RU3 P1-1: nhóm loi_tim (tìm tương tự lỗi) vẫn phải có chuỗi snapshot hằng ngày."""
    kho.them_goc(uid(10), "chu")
    kho.them_tay(uid(10), uid(11), "chu")
    kho.dat_trang_thai_nhom(uid(10), "loi_tim", "keyword_khong_loc")
    assert kho.ds_can_chup(NGAY) == [uid(10), uid(11)]
    kho.dat_uid(uid(10), uid(11), "loai", "chu")                          # UID đã loại vẫn bị bỏ
    assert kho.ds_can_chup(NGAY) == [uid(10)]
    kho.dat_trang_thai_nhom(uid(10), "ngung", "")
    assert kho.ds_can_chup(NGAY) == []


def test_ds_can_chup_nhom_cho_tim_dang_tim_ngung_khong_chup_hang_ngay(kho):
    for i in (20, 21):                                                    # tối đa 2 gốc không ngung
        kho.them_goc(uid(i), "chu")
        kho.them_tay(uid(i), uid(i + 10), "chu")
    kho.dat_trang_thai_nhom(uid(21), "dang_tim", "")                      # uid(20) vẫn cho_tim
    assert kho.ds_can_chup(NGAY) == []
    kho.dat_trang_thai_nhom(uid(21), "ngung", "")
    assert kho.ds_can_chup(NGAY) == []


def test_ds_can_chup_van_tra_uid_loi_chua_het_luot_va_uid_ghim(kho):
    _nhom_da_tim(kho, uid(1), [uid(2), uid(3)])
    kho.dat_uid(uid(1), uid(2), "ghim", "chu")
    kho.bat_dau_chup(uid(3), NGAY, "2026-12-01T10:00:00+07:00")
    kho.ghi_chup_loi(uid(3), NGAY, "mang")
    assert set(kho.ds_can_chup(NGAY)) == {uid(1), uid(2), uid(3)}


def test_bat_dau_chup_ghi_dang_chup_truoc_va_toi_da_2_lan(kho):
    ll = "2026-12-01T10:00:00+07:00"
    assert kho.bat_dau_chup(uid(1), NGAY, ll) is True
    r = _sql(kho, "SELECT trang_thai, so_lan_thu, lay_luc FROM chup_uid WHERE uid=? AND ngay=?", (uid(1), NGAY))[0]
    assert (r["trang_thai"], r["so_lan_thu"], r["lay_luc"]) == ("dang_chup", 1, ll)
    assert kho.bat_dau_chup(uid(1), NGAY, "2026-12-01T10:05:00+07:00") is True      # thử lại lần 2 (dang_chup dở)
    assert _sql(kho, "SELECT so_lan_thu, lay_luc FROM chup_uid")[0]["so_lan_thu"] == 2
    assert kho.bat_dau_chup(uid(1), NGAY, "2026-12-01T10:10:00+07:00") is False     # hết 2 lần
    assert _sql(kho, "SELECT so_lan_thu FROM chup_uid")[0]["so_lan_thu"] == 2
    assert kho.bat_dau_chup(uid(1), "2026-12-02", ll) is True                       # ngày khác: tính lại


def test_bat_dau_chup_sau_loi_duoc_chup_lai_roi_het_luot(kho):
    ll = "2026-12-01T10:00:00+07:00"
    kho.bat_dau_chup(uid(1), NGAY, ll)
    kho.ghi_chup_loi(uid(1), NGAY, "mang")
    assert kho.bat_dau_chup(uid(1), NGAY, ll) is True
    r = _sql(kho, "SELECT trang_thai, ma_loi, so_lan_thu FROM chup_uid")[0]
    assert (r["trang_thai"], r["ma_loi"], r["so_lan_thu"]) == ("dang_chup", "", 2)
    kho.ghi_chup_loi(uid(1), NGAY, "mang")
    assert kho.bat_dau_chup(uid(1), NGAY, ll) is False


def test_bat_dau_chup_da_ok_tra_false_khong_doi_gi(kho):
    _chup_ok(kho, uid(1), NGAY)
    assert kho.bat_dau_chup(uid(1), NGAY, "2026-12-01T11:00:00+07:00") is False
    r = _sql(kho, "SELECT trang_thai, so_lan_thu, lay_luc FROM chup_uid")[0]
    assert (r["trang_thai"], r["so_lan_thu"], r["lay_luc"]) == ("ok", 1, "2026-12-01T10:00:00+07:00")


def test_bat_dau_chup_kiem_tham_so(kho):
    with pytest.raises(ThamSoLoi):
        kho.bat_dau_chup("12", NGAY, "2026-12-01T10:00:00+07:00")
    with pytest.raises(ThamSoLoi):
        kho.bat_dau_chup(uid(1), "1/12", "2026-12-01T10:00:00+07:00")
    with pytest.raises(ThamSoLoi):
        kho.bat_dau_chup(uid(1), NGAY, "10 giờ")
    assert _sql(kho, "SELECT * FROM chup_uid") == []


def test_ghi_chup_ok_ghi_du_va_doc_lai_dung(kho):
    kho.bat_dau_chup(uid(1), NGAY, "2026-12-01T10:00:00+07:00")
    snap = _snap(uid(1), n=3, videos={
        "7300000000000000001": _hv(1, video_id="7300000000000000001", view="1.79M", follower=None, ban="12", is_promote=True),
        "7300000000000000002": _hv(2, video_id="7300000000000000002", view=326, is_promote=None)})
    snap["tong_trang"] = 1
    kho.ghi_chup_ok(snap)
    r = _sql(kho, "SELECT * FROM chup_uid")[0]
    assert (r["trang_thai"], r["ma_loi"], r["ban_tong"], r["gia"], r["so_trang"]) == ("ok", "", "10.17K", "499.390₫", 1)
    [s] = kho.doc_snapshots(uid(1), "2026-11-01")
    assert s["uid"] == uid(1) and s["ngay"] == NGAY and s["echotik_cap_nhat"] == "2026-11-22 07:55"
    assert s["hoa_hong"] == "10%" and s["ton"] == "562" and s["tong_creator"] is None
    assert (s["so_trang"], s["tong_trang"]) == (1, 1)
    v1, v2 = s["videos"]["7300000000000000001"], s["videos"]["7300000000000000002"]
    assert v1 == {"video_id": "7300000000000000001", "creator": "c1", "follower": None, "view": "1.79M", "ban": "12",
                  "dang_luc": "2026-07-18 10:00:00", "is_promote": 1}
    assert v2["view"] == "326" and isinstance(v2["view"], str) and v2["is_promote"] is None
    assert "update_time" not in v1
    assert _sql(kho, "SELECT typeof(video_id) a, typeof(uid) b FROM chup_video")[0]["a"] == "text"


def test_ghi_chup_ok_video_rong_ghi_loi_khong_co_video_khong_ok(kho):
    kho.bat_dau_chup(uid(1), NGAY, "2026-12-01T10:00:00+07:00")
    kho.ghi_chup_ok(_snap(uid(1), videos={}))
    r = _sql(kho, "SELECT trang_thai, ma_loi FROM chup_uid")[0]
    assert (r["trang_thai"], r["ma_loi"]) == ("loi", "khong_co_video")
    assert _sql(kho, "SELECT * FROM chup_video") == []
    assert kho.doc_snapshots(uid(1), "2026-01-01") == []                  # không tham gia tính kỳ
    assert kho.bat_dau_chup(uid(1), NGAY, "2026-12-01T10:30:00+07:00") is True       # còn lượt 2


def test_ghi_chup_ok_hoan_tac_het_khi_loi_giua_chung(kho):
    kho.bat_dau_chup(uid(1), NGAY, "2026-12-01T10:00:00+07:00")
    xau = _snap(uid(1), n=0)
    xau["videos"] = {"7300000000000000001": _hv(1, video_id="7300000000000000001"),
                     "7300000000000000002": _hv(2, video_id="7300000000000000002", creator=None)}   # NOT NULL vỡ ở video 2
    with pytest.raises(sqlite3.IntegrityError):
        kho.ghi_chup_ok(xau)
    assert _sql(kho, "SELECT * FROM chup_video") == []                    # video 1 đã chèn phải được hoàn tác
    r = _sql(kho, "SELECT trang_thai, ban_tong FROM chup_uid")[0]
    assert (r["trang_thai"], r["ban_tong"]) == ("dang_chup", None)        # chup_uid cũng hoàn tác
    kho.ghi_chup_ok(_snap(uid(1)))                                        # kho vẫn dùng được, ghi lại bình thường
    assert _sql(kho, "SELECT trang_thai FROM chup_uid")[0]["trang_thai"] == "ok"
    assert len(_sql(kho, "SELECT * FROM chup_video")) == 3


def test_ghi_chup_ok_khong_ghi_de_ok_va_can_bat_dau_truoc(kho):
    with pytest.raises(SaiTrangThaiRadar):
        kho.ghi_chup_ok(_snap(uid(1)))
    _chup_ok(kho, uid(1), NGAY)
    with pytest.raises(SaiTrangThaiRadar):
        kho.ghi_chup_ok(_snap(uid(1), n=1))
    assert len(_sql(kho, "SELECT * FROM chup_video")) == 3


def test_ghi_chup_ok_kiem_tham_so(kho):
    kho.bat_dau_chup(uid(1), NGAY, "2026-12-01T10:00:00+07:00")
    with pytest.raises(ThamSoLoi):
        kho.ghi_chup_ok(_snap("12"))
    with pytest.raises(ThamSoLoi):
        kho.ghi_chup_ok(_snap(uid(1), lay_luc="x"))
    with pytest.raises(ThamSoLoi):
        kho.ghi_chup_ok(_snap(uid(1), videos={7300000000000000001: _hv(1)}))   # video_id là số: cấm
    with pytest.raises(ThamSoLoi):
        kho.ghi_chup_ok(_snap(uid(1), n=1, videos={"7300000000000000001": _hv(1, is_promote="yes")}))
    assert _sql(kho, "SELECT trang_thai FROM chup_uid")[0]["trang_thai"] == "dang_chup"


def test_ghi_chup_loi(kho):
    with pytest.raises(SaiTrangThaiRadar):
        kho.ghi_chup_loi(uid(1), NGAY, "khong_tim_thay")                  # chưa bat_dau_chup
    kho.bat_dau_chup(uid(1), NGAY, "2026-12-01T10:00:00+07:00")
    kho.ghi_chup_loi(uid(1), NGAY, "khong_tim_thay")
    r = _sql(kho, "SELECT trang_thai, ma_loi FROM chup_uid")[0]
    assert (r["trang_thai"], r["ma_loi"]) == ("loi", "khong_tim_thay")
    kho.bat_dau_chup(uid(1), NGAY, "2026-12-01T10:30:00+07:00")
    kho.ghi_chup_ok(_snap(uid(1)))
    with pytest.raises(SaiTrangThaiRadar):                                # không hạ một lần ok xuống loi
        kho.ghi_chup_loi(uid(1), NGAY, "mang")
    assert _sql(kho, "SELECT trang_thai FROM chup_uid")[0]["trang_thai"] == "ok"
    with pytest.raises(ThamSoLoi):
        kho.ghi_chup_loi(uid(1), NGAY, "Lỗi có dấu và dài")


def test_chup_lai_sau_loi_ghi_de_video_cu_khong_nhan_doi(kho):
    kho.bat_dau_chup(uid(1), NGAY, "2026-12-01T10:00:00+07:00")
    kho.ghi_chup_loi(uid(1), NGAY, "dinh_dang")
    kho.bat_dau_chup(uid(1), NGAY, "2026-12-01T10:30:00+07:00")
    kho.ghi_chup_ok(_snap(uid(1), n=2))
    assert len(_sql(kho, "SELECT * FROM chup_video")) == 2


def test_doc_snapshots_loc_tu_ngay_thu_tu_va_chi_lay_ok(kho):
    for ngay in ("2026-11-28", "2026-11-30", "2026-11-29"):
        _chup_ok(kho, uid(1), ngay)
    kho.bat_dau_chup(uid(1), NGAY, "2026-12-01T10:00:00+07:00")
    kho.ghi_chup_loi(uid(1), NGAY, "mang")
    _chup_ok(kho, uid(2), "2026-11-30")
    assert [s["ngay"] for s in kho.doc_snapshots(uid(1), "2026-11-29")] == ["2026-11-29", "2026-11-30"]
    assert len(kho.doc_snapshots(uid(1), "2026-01-01")) == 3
    assert kho.doc_snapshots(uid(5), "2026-01-01") == [] and kho.doc_snapshots("abc", "2026-01-01") == []


# ---------------------------------------------------------------------------------------------------------------
# Ngân sách gọi
# ---------------------------------------------------------------------------------------------------------------
def test_tinh_goi_cong_truoc_va_false_khi_vuot(kho):
    assert kho.goi_hom_nay(NGAY) == 0
    assert kho.tinh_goi(NGAY, 1, 3) is True
    assert kho.tinh_goi(NGAY, 2, 3) is True
    assert kho.goi_hom_nay(NGAY) == 3
    assert kho.tinh_goi(NGAY, 1, 3) is False
    assert kho.goi_hom_nay(NGAY) == 3                                     # từ chối thì không cộng
    assert kho.tinh_goi("2026-12-02", 1, 3) is True                       # ngày khác: ngân sách riêng
    assert kho.goi_hom_nay("2026-12-02") == 1


def test_tinh_goi_khong_dung_phan_le_va_tran_0(kho):
    assert kho.tinh_goi(NGAY, 2, 3) is True
    assert kho.tinh_goi(NGAY, 2, 3) is False and kho.goi_hom_nay(NGAY) == 2
    assert kho.tinh_goi("2026-12-03", 1, 0) is False and kho.goi_hom_nay("2026-12-03") == 0
    for so, tran in ((0, 3), (-1, 3), (True, 3), (1.5, 3), (1, -1), (1, None)):
        with pytest.raises(ThamSoLoi):
            kho.tinh_goi(NGAY, so, tran)


# ---------------------------------------------------------------------------------------------------------------
# Lần chạy / token
# ---------------------------------------------------------------------------------------------------------------
def test_vong_doi_lan_chay(kho, dong):
    assert kho.lan_gan_nhat() is None and kho.lan_cua_viec(NGAY, "hang-ngay", "j1") is None
    assert kho.bat_dau_lan(NGAY, "hang-ngay", "j1") is True
    r = kho.lan_cua_viec(NGAY, "hang-ngay", "j1")
    assert (r["trang_thai"], r["ly_do"], r["ket_thuc"], r["so_goi"]) == ("dang_chay", "", None, 0)
    assert r["bat_dau"] == "2026-12-01T12:00:00+07:00"
    assert kho.bat_dau_lan(NGAY, "hang-ngay", "j1") is True               # dang_chay dở (máy khởi động lại): chạy tiếp
    dong.luc = dong.luc + timedelta(minutes=5)
    kho.ket_thuc_lan(NGAY, "hang-ngay", "j1", "tu_dung", "het_han_muc_goi", 60)
    r = kho.lan_cua_viec(NGAY, "hang-ngay", "j1")
    assert (r["trang_thai"], r["ly_do"], r["so_goi"], r["ket_thuc"]) == ("tu_dung", "het_han_muc_goi", 60, "2026-12-01T12:05:00+07:00")
    assert kho.bat_dau_lan(NGAY, "hang-ngay", "j1") is False              # đã tu_dung: không chạy lại
    with pytest.raises(SaiTrangThaiRadar):
        kho.ket_thuc_lan(NGAY, "hang-ngay", "j1", "xong", "", 1)          # không còn dang_chay
    assert kho.lan_gan_nhat()["viec_id"] == "j1"


def test_lan_chay_loi_duoc_chay_lai_xong_thi_khoa_va_lan_gan_nhat(kho, dong):
    kho.bat_dau_lan(NGAY, "nap", "j1")
    kho.ket_thuc_lan(NGAY, "nap", "j1", "loi", "ngoai_le", 4)
    assert kho.bat_dau_lan(NGAY, "nap", "j1") is True
    r = kho.lan_cua_viec(NGAY, "nap", "j1")
    assert (r["trang_thai"], r["ly_do"], r["so_goi"]) == ("dang_chay", "", 0)
    kho.ket_thuc_lan(NGAY, "nap", "j1", "xong", "", 22)
    assert kho.bat_dau_lan(NGAY, "nap", "j1") is False
    dong.luc = dong.luc + timedelta(hours=1)
    assert kho.bat_dau_lan(NGAY, "hang-ngay", "j2") is True               # che_do/viec_id khác ⇒ dòng khác
    assert kho.lan_gan_nhat()["viec_id"] == "j2"
    assert kho.lan_cua_viec(NGAY, "nap", "j1")["trang_thai"] == "xong"


def test_lan_chay_kiem_tham_so(kho):
    with pytest.raises(ThamSoLoi):
        kho.bat_dau_lan("x", "nap", "j1")
    with pytest.raises(ThamSoLoi):
        kho.bat_dau_lan(NGAY, "Nạp", "j1")
    with pytest.raises(ThamSoLoi):
        kho.bat_dau_lan(NGAY, "nap", "")
    kho.bat_dau_lan(NGAY, "nap", "j1")
    with pytest.raises(ThamSoLoi):
        kho.ket_thuc_lan(NGAY, "nap", "j1", "dang_chay", "", 0)
    with pytest.raises(ThamSoLoi):
        kho.ket_thuc_lan(NGAY, "nap", "j1", "tu_dung", "", 0)             # dừng/lỗi phải có lý do
    with pytest.raises(ThamSoLoi):
        kho.ket_thuc_lan(NGAY, "nap", "j1", "xong", "", -1)
    with pytest.raises(SaiTrangThaiRadar):
        kho.ket_thuc_lan(NGAY, "nap", "j_khac", "xong", "", 0)


def test_token_chi_luu_trang_thai_va_ma_ngan_khong_luu_noi_dung(kho):
    assert kho.doc_token() == {"trang_thai": "chua_kiem", "ma": "", "luc": ""}
    kho.ghi_token("het_han", "token_het_han")
    assert kho.doc_token() == {"trang_thai": "het_han", "ma": "token_het_han", "luc": "2026-12-01T12:00:00+07:00"}
    kho.ghi_token("ok", "")
    assert kho.doc_token()["trang_thai"] == "ok" and len(_sql(kho, "SELECT * FROM token_tt")) == 1
    with pytest.raises(ThamSoLoi):
        kho.ghi_token("ok", "Bearer eyJhbGciOiJIUzI1NiJ9.AbC-123")        # nội dung giống token bị từ chối
    with pytest.raises(ThamSoLoi):
        kho.ghi_token("het", "")
    assert kho.doc_token()["trang_thai"] == "ok"


# ---------------------------------------------------------------------------------------------------------------
# Dọn 90 ngày
# ---------------------------------------------------------------------------------------------------------------
def test_mo_don_chup_cu_hon_90_ngay(kho, dong):
    _chup_ok(kho, uid(1), "2026-08-01")                                   # 122 ngày trước
    _chup_ok(kho, uid(1), "2026-09-03")                                   # 89 ngày trước
    _chup_ok(kho, uid(1), "2026-09-02")                                   # đúng 90 ngày: còn giữ
    kho.mo()
    ngay = [r["ngay"] for r in _sql(kho, "SELECT ngay FROM chup_uid ORDER BY ngay")]
    assert ngay == ["2026-09-02", "2026-09-03"]
    assert {r["ngay"] for r in _sql(kho, "SELECT ngay FROM chup_video")} == {"2026-09-02", "2026-09-03"}


# ---------------------------------------------------------------------------------------------------------------
# Đọc nhóm
# ---------------------------------------------------------------------------------------------------------------
def test_ds_nhom_va_uid_cua_nhom(kho, dong):
    kho.them_goc(uid(1), "chu")
    kho.ghi_san_pham(uid(1), "Kẹp tóc càng cua", "Shop A")
    dong.luc = dong.luc + timedelta(minutes=1)
    kho.them_goc(uid(2), "chu")
    kho.ghi_tuong_tu(uid(1), [{"uid": uid(3), "ten": "tương tự", "gia": None, "ban_7d": None, "do_giong": 0.6}],
                     "2026-12-01T12:00:00+07:00")
    kho.them_tay(uid(1), uid(4), "chu")
    ds = kho.ds_nhom()
    assert [n["goc"] for n in ds] == [uid(1), uid(2)]
    assert ds[0]["ten"] == "Kẹp tóc càng cua" and ds[1]["ten"] == ""
    assert set(ds[0]) >= {"goc", "ten", "trang_thai", "ly_do", "them_luc", "them_boi", "tim_luc", "bat_dau_ngay"}
    lk = kho.uid_cua_nhom(uid(1))
    assert lk[0]["uid"] == uid(1) and lk[0]["vai"] == "goc" and lk[0]["shop"] == "Shop A"
    assert {x["uid"]: x["vai"] for x in lk} == {uid(1): "goc", uid(3): "tuong_tu", uid(4): "them_tay"}
    assert all(isinstance(x["uid"], str) for x in lk) and lk[1]["ten"] in ("tương tự", "")
    with pytest.raises(KhongCoRadar):
        kho.uid_cua_nhom(uid(9))
    with pytest.raises(KhongCoRadar):
        kho.uid_cua_nhom("12")


# ---------------------------------------------------------------------------------------------------------------
# RU-B10: ảnh bìa + nâng schema v1 -> v2
# ---------------------------------------------------------------------------------------------------------------
ANH_OK = "https://cdn.echotik.live/abc123/0123456789abcdef/product-cover/1/1729706628656900001_0.webp"
ANH_OK2 = "https://cdn.echotik.live/abc123/fedcba9876543210/product-cover/1/1729706628656900001_0.webp"

V1_SCHEMA = """
CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE san_pham (uid TEXT PRIMARY KEY CHECK(length(uid)=19 AND uid NOT GLOB '*[^0-9]*'),
  ten TEXT NOT NULL DEFAULT '', shop TEXT NOT NULL DEFAULT '', cap_nhat_luc TEXT);
CREATE TABLE nhom (goc TEXT PRIMARY KEY REFERENCES san_pham(uid),
  trang_thai TEXT NOT NULL CHECK(trang_thai IN ('cho_tim','dang_tim','da_tim','loi_tim','ngung')),
  ly_do TEXT NOT NULL DEFAULT '', them_luc TEXT NOT NULL, them_boi TEXT NOT NULL, tim_luc TEXT, bat_dau_ngay TEXT NOT NULL);
CREATE TABLE lien_ket (goc TEXT NOT NULL REFERENCES nhom(goc), uid TEXT NOT NULL REFERENCES san_pham(uid),
  vai TEXT NOT NULL CHECK(vai IN ('goc','tuong_tu','them_tay')),
  trang_thai TEXT NOT NULL CHECK(trang_thai IN ('dang_theo','ghim','loai')),
  do_giong REAL, them_luc TEXT NOT NULL, them_boi TEXT NOT NULL, PRIMARY KEY (goc, uid));
CREATE TABLE chup_uid (uid TEXT NOT NULL, ngay TEXT NOT NULL,
  trang_thai TEXT NOT NULL CHECK(trang_thai IN ('dang_chup','ok','loi')), ma_loi TEXT NOT NULL DEFAULT '',
  lay_luc TEXT NOT NULL, echotik_cap_nhat TEXT,
  ban_tong TEXT, gia TEXT, hoa_hong TEXT, ton TEXT, tong_creator TEXT,
  so_trang INTEGER NOT NULL DEFAULT 0, tong_trang INTEGER, so_lan_thu INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (uid, ngay));
CREATE TABLE chup_video (uid TEXT NOT NULL, ngay TEXT NOT NULL, video_id TEXT NOT NULL, creator TEXT NOT NULL,
  follower TEXT, view TEXT NOT NULL, ban TEXT, dang_luc TEXT NOT NULL, is_promote INTEGER,
  PRIMARY KEY (uid, ngay, video_id), FOREIGN KEY (uid, ngay) REFERENCES chup_uid(uid, ngay));
CREATE TABLE lan_chay (ngay TEXT NOT NULL, che_do TEXT NOT NULL, viec_id TEXT NOT NULL, trang_thai TEXT NOT NULL,
  ly_do TEXT NOT NULL DEFAULT '', bat_dau TEXT NOT NULL, ket_thuc TEXT, so_goi INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (ngay, che_do, viec_id));
CREATE TABLE goi_ngay (ngay TEXT PRIMARY KEY, so_goi INTEGER NOT NULL DEFAULT 0);
CREATE TABLE token_tt (id INTEGER PRIMARY KEY CHECK(id=1), trang_thai TEXT NOT NULL,
  ma TEXT NOT NULL DEFAULT '', luc TEXT NOT NULL);
CREATE TABLE su_kien (id INTEGER PRIMARY KEY, luc TEXT NOT NULL, boi TEXT NOT NULL,
  hanh_dong TEXT NOT NULL, goc TEXT, uid TEXT);
CREATE INDEX lien_ket_uid ON lien_ket(uid);
"""


def _dung_db_v1(duong: Path) -> None:
    """DB schema '1' dựng tay: 1 nhóm (gốc + 1 tương tự), có chụp."""
    c = sqlite3.connect(duong)
    c.executescript(V1_SCHEMA)
    c.execute("INSERT INTO meta(k, v) VALUES('schema_ban', '1')")
    c.execute("INSERT INTO san_pham VALUES(?, 'Kẹp gốc', 'Shop A', '2026-12-01T09:00:00+07:00')", (uid(1),))
    c.execute("INSERT INTO san_pham VALUES(?, 'Kẹp tương tự', 'Shop B', '2026-12-01T09:00:00+07:00')", (uid(2),))
    c.execute("INSERT INTO nhom VALUES(?, 'da_tim', '', '2026-12-01T09:00:00+07:00', 'chu', '2026-12-01T09:30:00+07:00', ?)",
              (uid(1), NGAY))
    c.execute("INSERT INTO lien_ket VALUES(?, ?, 'goc', 'dang_theo', NULL, '2026-12-01T09:00:00+07:00', 'chu')", (uid(1), uid(1)))
    c.execute("INSERT INTO lien_ket VALUES(?, ?, 'tuong_tu', 'ghim', 0.7, '2026-12-01T09:30:00+07:00', 'he_thong')",
              (uid(1), uid(2)))
    c.execute("INSERT INTO chup_uid(uid, ngay, trang_thai, lay_luc, ban_tong) VALUES(?, ?, 'ok', '2026-12-01T10:00:00+07:00', '5K')",
              (uid(1), NGAY))
    c.execute("INSERT INTO chup_video VALUES(?, ?, '7300000000000000001', 'c1', NULL, '1K', NULL, '2026-07-18 10:00:00', 0)",
              (uid(1), NGAY))
    c.commit()
    c.close()


def _chup_db(duong: Path) -> dict:
    c = sqlite3.connect(duong)
    try:
        return {t: c.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall()
                for t in ("san_pham", "nhom", "lien_ket", "chup_uid", "chup_video", "meta")}
    finally:
        c.close()


def test_re_anh_dung_chu_hop_dong():
    assert kho_radar_uid.RE_ANH.pattern == r"^https://cdn\.echotik\.live/[A-Za-z0-9._/-]{1,300}$"


def test_mo_nang_v1_len_v2_giu_du_lieu_va_idempotent(tmp_path, dong):
    duong = tmp_path / "radar_uid.db"
    _dung_db_v1(duong)
    truoc = _chup_db(duong)
    k = KhoRadarUid(duong, dong)
    k.mo()
    cot = {r["name"] for r in _sql(k, "PRAGMA table_info(san_pham)")}
    assert {"anh", "anh_luc"} <= cot
    assert _sql(k, "SELECT v FROM meta WHERE k='schema_ban'")[0]["v"] == "2"
    sau = _chup_db(duong)
    for t in ("nhom", "lien_ket", "chup_uid", "chup_video"):
        assert sau[t] == truoc[t]
    assert [tuple(r[:4]) for r in sau["san_pham"]] == [tuple(r[:4]) for r in truoc["san_pham"]]
    assert all(r["anh"] == "" and r["anh_luc"] == "" for r in _sql(k, "SELECT anh, anh_luc FROM san_pham"))
    k.mo()                                                                # lần 2: không ADD COLUMN lại
    k.mo()
    assert len(_sql(k, "SELECT * FROM meta")) == 1
    assert [r["name"] for r in _sql(k, "PRAGMA table_info(san_pham)")].count("anh") == 1
    assert [n["goc"] for n in k.ds_nhom()] == [uid(1)]
    k.ghi_san_pham(uid(1), "Kẹp gốc", "Shop A", ANH_OK)
    assert k.ds_nhom()[0]["anh"] == ANH_OK
    k.dong()


def test_mo_nang_cap_hoan_tac_neu_loi_giua_chung(tmp_path, dong):
    """Giao dịch: schema lạ thì không đụng gì (không thêm cột)."""
    duong = tmp_path / "radar_uid.db"
    _dung_db_v1(duong)
    c = sqlite3.connect(duong)
    c.execute("UPDATE meta SET v='9' WHERE k='schema_ban'")
    c.commit()
    c.close()
    k = KhoRadarUid(duong, dong)
    with pytest.raises(RuntimeError, match="schema"):
        k.mo()
    k.dong()
    assert "anh" not in {r["name"] for r in _sql(k, "PRAGMA table_info(san_pham)")}
    assert _sql(k, "SELECT v FROM meta WHERE k='schema_ban'")[0]["v"] == "9"


def test_chi_doc_tren_v1_khong_ghi_gi_va_van_doc_duoc(tmp_path, dong):
    duong = tmp_path / "radar_uid.db"
    _dung_db_v1(duong)
    truoc = _chup_db(duong)
    cot_truoc = [tuple(r) for r in _sql(KhoRadarUid(duong, dong), "PRAGMA table_info(san_pham)")]
    doc = KhoRadarUid(duong, dong, chi_doc=True)
    ds = doc.ds_nhom()
    assert [n["goc"] for n in ds] == [uid(1)]
    assert ds[0]["anh"] == "" and ds[0]["shop"] == "Shop A" and ds[0]["n_tuong_tu"] == 1 and ds[0]["n_ghim"] == 1
    lk = doc.uid_cua_nhom(uid(1))
    assert [x["uid"] for x in lk] == [uid(1), uid(2)] and all(x["anh"] == "" for x in lk)
    assert lk[1]["ten"] == "Kẹp tương tự" and lk[1]["shop"] == "Shop B"
    with pytest.raises(ChiDoc):
        doc.mo()
    doc.dong()
    assert _chup_db(duong) == truoc
    assert [tuple(r) for r in _sql(KhoRadarUid(duong, dong), "PRAGMA table_info(san_pham)")] == cot_truoc
    assert _sql(KhoRadarUid(duong, dong), "SELECT v FROM meta WHERE k='schema_ban'")[0]["v"] == "1"


def test_ghi_san_pham_anh_hop_le_luu_kem_anh_luc(kho, dong):
    kho.ghi_san_pham(uid(1), "a", "b", ANH_OK)
    r = _sql(kho, "SELECT anh, anh_luc FROM san_pham WHERE uid=?", (uid(1),))[0]
    assert r["anh"] == ANH_OK and r["anh_luc"] == "2026-12-01T12:00:00+07:00"
    dong.luc = dong.luc + timedelta(hours=24)
    kho.ghi_san_pham(uid(1), "a", "b", ANH_OK2)                           # ghi đè mỗi lần chụp (URL hết hạn)
    r = _sql(kho, "SELECT anh, anh_luc FROM san_pham WHERE uid=?", (uid(1),))[0]
    assert r["anh"] == ANH_OK2 and r["anh_luc"] == "2026-12-02T12:00:00+07:00"


def test_ghi_san_pham_chu_ky_cu_van_goi_duoc(kho):
    kho.ghi_san_pham(uid(1), "a", "b")
    r = _sql(kho, "SELECT ten, shop, anh, anh_luc FROM san_pham")[0]
    assert (r["ten"], r["shop"], r["anh"], r["anh_luc"]) == ("a", "b", "", "")


@pytest.mark.parametrize("xau", [
    "http://cdn.echotik.live/a/b.webp",                                    # không https
    "https://evil.example.com/a/b.webp",                                   # host khác
    "https://cdn.echotik.live.evil.com/a.webp",                            # host lách
    "https://cdn.echotik.live@evil.com/a.webp",
    "https://cdn.echotik.live/a b.webp",                                   # khoảng trắng
    'https://cdn.echotik.live/a"onerror=x.webp',
    "https://cdn.echotik.live/a<script>.webp",
    "https://cdn.echotik.live/a>.webp",
    "https://cdn.echotik.live/a.webp\n",                                   # xuống dòng cuối ($ lỏng)
    "https://cdn.echotik.live/a?x=1.webp",
    "https://cdn.echotik.live/",                                           # rỗng sau host
    "https://cdn.echotik.live/" + "a" * 301,                               # quá dài
    "javascript:alert(1)",
    123,
    None,
])
def test_ghi_san_pham_url_la_bi_bo_va_giu_anh_cu(kho, xau):
    kho.ghi_san_pham(uid(1), "a", "b", ANH_OK)
    luc_cu = _sql(kho, "SELECT anh_luc FROM san_pham")[0]["anh_luc"]
    kho.ghi_san_pham(uid(1), "a2", "b2", xau)                              # không ném lỗi
    r = _sql(kho, "SELECT ten, shop, anh, anh_luc FROM san_pham")[0]
    assert (r["ten"], r["shop"]) == ("a2", "b2")                          # ten/shop vẫn cập nhật như cũ
    assert r["anh"] == ANH_OK and r["anh_luc"] == luc_cu


def test_ghi_san_pham_url_la_khi_chua_co_anh_van_rong(kho):
    kho.ghi_san_pham(uid(1), "a", "b", "http://x/y")
    r = _sql(kho, "SELECT anh, anh_luc FROM san_pham")[0]
    assert (r["anh"], r["anh_luc"]) == ("", "")


def test_ghi_san_pham_url_la_khong_vao_log(kho, caplog):
    with caplog.at_level("DEBUG"):
        kho.ghi_san_pham(uid(1), "a", "b", "https://evil.example.com/secret-path")
    assert "evil.example.com" not in caplog.text


def test_ghi_san_pham_anh_rong_khong_xoa_anh_cu(kho):
    kho.ghi_san_pham(uid(1), "a", "b", ANH_OK)
    kho.ghi_san_pham(uid(1), "a", "b", "")
    kho.ghi_san_pham(uid(1), "a", "b")
    r = _sql(kho, "SELECT anh, anh_luc FROM san_pham")[0]
    assert r["anh"] == ANH_OK and r["anh_luc"] == "2026-12-01T12:00:00+07:00"


def test_ds_nhom_co_anh_shop_n_tuong_tu_n_ghim(kho):
    kho.them_goc(uid(1), "chu")
    kho.ghi_san_pham(uid(1), "Gốc", "Shop A", ANH_OK)
    kho.them_goc(uid(2), "chu")                                           # gốc chưa có ảnh/shop
    kho.ghi_tuong_tu(uid(1), [{"uid": uid(i), "ten": f"t{i}", "gia": None, "ban_7d": None} for i in (3, 4, 5, 6)],
                     "2026-12-01T10:00:00+07:00")
    kho.dat_uid(uid(1), uid(3), "ghim", "chu")
    kho.dat_uid(uid(1), uid(4), "ghim", "chu")
    kho.dat_uid(uid(1), uid(5), "loai", "chu")                            # loại: không tính
    kho.them_tay(uid(1), uid(7), "chu")                                   # RU-B12: thêm tay TÍNH vào n_tuong_tu
    ds = {n["goc"]: n for n in kho.ds_nhom()}
    assert ds[uid(1)]["anh"] == ANH_OK and ds[uid(1)]["shop"] == "Shop A" and ds[uid(1)]["ten"] == "Gốc"
    assert ds[uid(1)]["n_tuong_tu"] == 4 and ds[uid(1)]["n_ghim"] == 2    # uid3, uid4 ghim; uid6 dang_theo; uid7 thêm tay
    assert ds[uid(2)]["anh"] == "" and ds[uid(2)]["shop"] == "" and ds[uid(2)]["n_tuong_tu"] == 0 and ds[uid(2)]["n_ghim"] == 0
    assert set(ds[uid(1)]) >= {"goc", "ten", "trang_thai", "ly_do", "them_luc", "them_boi", "tim_luc", "bat_dau_ngay"}


def test_ds_nhom_n_tuong_tu_gom_them_tay_khong_gom_loai(kho):
    kho.them_goc(uid(1), "chu")
    kho.ghi_tuong_tu(uid(1), [{"uid": uid(i), "ten": f"t{i}", "gia": None, "ban_7d": None} for i in (2, 3, 4)],
                     "2026-12-01T10:00:00+07:00")
    kho.dat_uid(uid(1), uid(4), "loai", "chu")
    kho.them_tay(uid(1), uid(5), "chu")
    n = kho.ds_nhom()[0]
    assert n["n_tuong_tu"] == 3 and n["n_ghim"] == 0                      # 2 tương tự + 1 thêm tay; loại không đếm
    assert n["n_tuong_tu"] == len([x for x in kho.uid_cua_nhom(uid(1))
                                   if x["vai"] != "goc" and x["trang_thai"] in ("dang_theo", "ghim")])


def test_ds_nhom_n_ghim_gom_them_tay_va_khong_vuot_n_tuong_tu(kho):
    kho.them_goc(uid(1), "chu")
    kho.ghi_tuong_tu(uid(1), [{"uid": uid(i), "ten": f"t{i}", "gia": None, "ban_7d": None} for i in (2, 3)],
                     "2026-12-01T10:00:00+07:00")
    kho.dat_uid(uid(1), uid(2), "ghim", "chu")
    kho.them_tay(uid(1), uid(5), "chu")
    kho.dat_uid(uid(1), uid(5), "ghim", "chu")
    n = kho.ds_nhom()[0]
    assert n["n_ghim"] == 2 and n["n_tuong_tu"] == 3 and n["n_ghim"] <= n["n_tuong_tu"]


def test_ds_nhom_chi_goc_thi_0_0(kho):
    kho.them_goc(uid(1), "chu")
    n = kho.ds_nhom()[0]
    assert n["n_tuong_tu"] == 0 and n["n_ghim"] == 0


def test_ds_nhom_goc_them_roi_them_tay_khop_chi_tiet(kho):
    kho.them_goc(uid(1), "chu")
    kho.them_tay(uid(1), uid(2), "chu")
    assert kho.ds_nhom()[0]["n_tuong_tu"] == 1


def test_uid_cua_nhom_co_anh(kho):
    _nhom_da_tim(kho, uid(1), [uid(2), uid(3)])
    kho.ghi_san_pham(uid(2), "tt", "Shop X", ANH_OK)
    lk = {x["uid"]: x for x in kho.uid_cua_nhom(uid(1))}
    assert lk[uid(2)]["anh"] == ANH_OK and lk[uid(2)]["shop"] == "Shop X" and lk[uid(2)]["ten"] == "tt"
    assert lk[uid(1)]["anh"] == "" and lk[uid(3)]["anh"] == ""
    assert set(lk[uid(2)]) >= {"uid", "vai", "trang_thai", "do_giong", "ten", "shop", "them_luc"}


def test_cau_loi_co_dinh_la_thuoc_tinh_loi(kho):
    assert KhongCoRadar().loi == "Không có UID này trong Radar"
    assert isinstance(KhongCoRadar(), LookupError) and isinstance(SaiTrangThaiRadar("x"), RuntimeError)
