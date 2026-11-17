"""Test kho việc SQLite — chạy: python -B -m pytest tools/test_runner_kho_viec.py -q"""
import sqlite3
import sys
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from runner.kieu import CanNguoiDung, SaiTrangThai, ThamSoLoi, TrungViec  # noqa: E402
from runner.kho_viec import KhoViec  # noqa: E402


class Dong:
    def __init__(self, luc: datetime):
        self.luc = luc

    def __call__(self) -> datetime:
        return self.luc

    def toi(self, giay: float) -> None:
        self.luc += timedelta(seconds=giay)


@pytest.fixture(autouse=True)
def _du_lieu_tam(tmp_path, monkeypatch):
    monkeypatch.setenv("KHO_RUNNER_DIR", str(tmp_path))


@pytest.fixture
def dong():
    return Dong(datetime(2026, 11, 17, 9, 0, 0))


@pytest.fixture
def kho(tmp_path, dong):
    return KhoViec(tmp_path / "runner.db", dong)


def _tao(kho, loai="phan_tich_uid", khoa="1729420930611055346", lan="nhe", tt="cho", boi="nhan", **kw):
    return kho.tao(loai, khoa, {"uid": khoa}, lan, tt, boi, **kw)


def test_tao_va_lay(kho):
    v = _tao(kho, session_id="abc")
    assert v["id"].startswith("j20261117090000") and len(v["id"]) == 19
    assert v["trang_thai"] == "cho" and v["tham_so"] == {"uid": "1729420930611055346"}
    assert v["session_id"] == "abc" and v["phien_da_tao"] == 0 and v["lan_thu"] == 1
    assert kho.lay(v["id"])["id"] == v["id"]
    assert kho.lay("j00000000000000zzzz") is None
    sk = kho.su_kien(v["id"])
    assert sk[0]["tu"] is None and sk[0]["den"] == "cho" and sk[0]["boi"] == "nhan"


def test_schema_dung_phien_ban(kho, tmp_path):
    with sqlite3.connect(tmp_path / "runner.db") as c:
        assert c.execute("SELECT gia_tri FROM meta WHERE khoa='schema'").fetchone()[0] == "1"
        assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_schema_la_thi_khong_xoa_ma_bao_loi(tmp_path, dong):
    db = tmp_path / "runner.db"
    KhoViec(db, dong)
    with sqlite3.connect(db) as c:
        c.execute("UPDATE meta SET gia_tri='9' WHERE khoa='schema'")
    with pytest.raises(RuntimeError):
        KhoViec(db, dong)
    assert db.exists()  # không đổi tên, không tạo lại rỗng


def test_trung_viec(kho):
    v = _tao(kho)
    with pytest.raises(TrungViec) as e:
        _tao(kho)
    assert e.value.viec["id"] == v["id"]
    # việc đã đóng thì tạo lại được
    kho.chuyen(v["id"], ["cho"], "huy", "nhan")
    v2 = _tao(kho)
    assert v2["id"] != v["id"]


def test_trung_viec_khi_mo_lai(kho):
    v = _tao(kho)
    kho.chuyen(v["id"], ["cho"], "loi", "he_thong")
    v2 = _tao(kho)
    with pytest.raises(TrungViec):
        kho.chuyen(v["id"], ["loi"], "cho", "nhan")
    assert kho.lay(v["id"])["trang_thai"] == "loi" and kho.lay(v2["id"])["trang_thai"] == "cho"


def test_tao_tu_choi_gia_tri_la(kho):
    with pytest.raises(ThamSoLoi):
        _tao(kho, lan="cpu")
    with pytest.raises(ThamSoLoi):
        _tao(kho, tt="xong")
    with pytest.raises(ThamSoLoi):
        _tao(kho, buoc="la")


def test_cas_sai_trang_thai(kho):
    v = _tao(kho)
    with pytest.raises(SaiTrangThai):
        kho.chuyen(v["id"], ["dang_chay"], "xong", "he_thong")
    with pytest.raises(SaiTrangThai):
        kho.chuyen("j20990101000000aaaa", ["cho"], "huy", "nhan")
    with pytest.raises(ThamSoLoi):
        kho.chuyen(v["id"], ["cho"], "bay", "nhan")
    with pytest.raises(ThamSoLoi):
        kho.chuyen(v["id"], ["cho"], "huy", "nhan", trang_thai="xong")
    with pytest.raises(ThamSoLoi):
        kho.chuyen(v["id"], ["cho"], "huy", "nhan", **{"loi=1;--": "x"})
    assert kho.lay(v["id"])["trang_thai"] == "cho"


def test_chuyen_ghi_truong_json_va_su_kien(kho, dong):
    v = _tao(kho)
    dong.toi(5)
    cau = CanNguoiDung("chon", "Chọn thư mục", ("A", "B"))
    v2 = kho.chuyen(v["id"], ["cho"], "can_tra_loi", "he_thong", "hỏi", cau_hoi=cau,
                    ket_qua={"tom_tat": "x"})
    assert v2["cau_hoi"] == {"loai": "chon", "noi_dung": "Chọn thư mục", "lua_chon": ["A", "B"]}
    assert v2["ket_qua"] == {"tom_tat": "x"}
    assert v2["cap_nhat_luc"].startswith("2026-11-17T09:00:05")
    sk = kho.su_kien(v["id"])
    assert [(s["tu"], s["den"], s["ghi_chu"]) for s in sk][-1] == ("cho", "can_tra_loi", "hỏi")
    v3 = kho.chuyen(v["id"], ["can_tra_loi"], "xong", "he_thong")
    assert v3["ket_thuc_luc"] is not None


def test_nhan_viec_ke_fifo_va_tai_nguyen(kho, dong):
    a = _tao(kho, loai="phan_tich_uid", khoa="1" * 19)
    dong.toi(1)
    b = _tao(kho, loai="radar_ban_tin", khoa="2026-11-17")
    dong.toi(1)
    c = _tao(kho, loai="poster_day_folder", khoa="abcdefabcdef")
    g = _tao(kho, loai="voice_pv", khoa="abcdefabcdef:20261117-a", lan="gpu")
    tn = {"phan_tich_uid": frozenset({"kho"}), "radar_ban_tin": frozenset(),
          "poster_day_folder": frozenset({"poster"}), "voice_pv": frozenset()}
    # kho bận → bỏ qua a, lấy b
    v = kho.nhan_viec_ke("nhe", {"kho"}, tn.__getitem__)
    assert v["id"] == b["id"] and v["trang_thai"] == "dang_chay" and v["bat_dau_luc"]
    v = kho.nhan_viec_ke("nhe", set(), tn.__getitem__)
    assert v["id"] == a["id"]
    v = kho.nhan_viec_ke("nhe", {"poster"}, tn.__getitem__)
    assert v is None
    v = kho.nhan_viec_ke("nhe", set(), tn.__getitem__)
    assert v["id"] == c["id"]
    assert kho.nhan_viec_ke("nhe", set(), tn.__getitem__) is None
    assert kho.nhan_viec_ke("gpu", set(), tn.__getitem__)["id"] == g["id"]


def test_nhan_viec_ke_loai_la_khong_sap_lan(kho, dong):
    x = _tao(kho, loai="loai_cu", khoa="x")
    dong.toi(1)
    y = _tao(kho, loai="radar_ban_tin", khoa="2026-11-17")

    def tn(loai):
        if loai == "loai_cu":
            raise KeyError(loai)
        return frozenset()

    assert kho.nhan_viec_ke("nhe", set(), tn)["id"] == y["id"]
    assert kho.lay(x["id"])["trang_thai"] == "cho"


def test_nhan_viec_ke_hai_luong_khong_lay_trung(tmp_path, dong):
    db = tmp_path / "runner.db"
    kho = KhoViec(db, dong)
    for i in range(20):
        kho.tao("radar_ban_tin", f"k{i}", {}, "nhe", "cho", "nhan")
        dong.toi(1)
    lay: list[str] = []
    khoa = threading.Lock()
    rao = threading.Barrier(4)

    def chay():
        k = KhoViec(db, dong)
        rao.wait()
        while True:
            v = k.nhan_viec_ke("nhe", set(), lambda _l: frozenset())
            if v is None:
                return
            with khoa:
                lay.append(v["id"])

    ts = [threading.Thread(target=chay) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(lay) == 20 and len(set(lay)) == 20


def test_tien_trinh_phien_chi_phi(kho, dong):
    v = _tao(kho, session_id="s")
    kho.ghi_tien_trinh(v["id"], 1234, 1700000000.5)
    kho.danh_dau_phien(v["id"])
    kho.cong_chi_phi(v["id"], 0.5, 3, True)
    kho.cong_chi_phi(v["id"], 0.25, 2, False)
    x = kho.lay(v["id"])
    assert x["pid"] == 1234 and x["pid_tao_luc"] == 1700000000.5 and x["phien_da_tao"] == 1
    assert x["chi_phi_usd"] == 0.75 and x["so_luot_claude"] == 5 and x["so_lan_claude"] == 1
    with pytest.raises(SaiTrangThai):
        kho.cong_chi_phi("j20990101000000aaaa", 1, 1, True)


def test_tra_loi_nonce_dem(kho, dong):
    v = _tao(kho)
    kho.them_tra_loi(v["id"], "nhan", "Chọn?", "A")
    assert [(t["boi"], t["noi_dung"]) for t in kho.tra_loi_cua(v["id"])] == [("nhan", "A")]
    assert kho.dung_nonce("n1", 100.0) is True
    assert kho.dung_nonce("n1", 101.0) is False
    kho.dung_nonce("n2", dong().timestamp())
    kho.don_cu(dong() - timedelta(days=1))
    assert kho.dung_nonce("n1", 102.0) is True      # n1 cũ đã bị xoá
    assert kho.dung_nonce("n2", 1.0) is False
    d = kho.dem()
    assert d["cho"] == 1 and d["xong"] == 0 and set(d) >= {"cho", "dang_chay", "huy"}


def _so_nonce(kho) -> int:
    return kho._ket_noi().execute("SELECT COUNT(*) FROM nonce").fetchone()[0]


def test_nonce_don_dinh_ky_khi_ghi_moi(kho):
    """R-05 P3-9: mỗi lần ghi nonce mới, xoá dòng quá thời gian sống (không cần khởi động lại)."""
    song = KhoViec.NONCE_SONG_S
    assert song >= 86400                     # thời gian sống đang dùng (vong_lap: 1 ngày) — không rút ngắn
    t0 = 1_800_000_000.0
    assert kho.dung_nonce("cu1", t0) is True
    assert kho.dung_nonce("cu2", t0 + 1) is True
    assert kho.dung_nonce("vua", t0 + song - 10) is True
    assert _so_nonce(kho) == 3
    # ghi nonce mới lúc t0+song+5: cu1, cu2 quá hạn → bị xoá; "vua" còn trong hạn → giữ
    assert kho.dung_nonce("moi", t0 + song + 5) is True
    con = {r[0] for r in kho._ket_noi().execute("SELECT gia_tri FROM nonce")}
    assert con == {"vua", "moi"}
    # chống lặp không đổi: nonce trong hạn vẫn bị từ chối, kể cả lần dọn kế tiếp
    assert kho.dung_nonce("vua", t0 + song + 6) is False
    assert kho.dung_nonce("moi", t0 + song + 7) is False


def test_nonce_don_dinh_ky_co_gioi_han_chi_phi(kho):
    t0 = 1_800_000_000.0
    n = KhoViec.NONCE_DON_TOI_DA + 50
    with kho._gd() as c:
        c.executemany("INSERT INTO nonce(gia_tri, luc) VALUES(?,?)", [(f"x{i}", t0) for i in range(n)])
    assert kho.dung_nonce("moi1", t0 + KhoViec.NONCE_SONG_S + 1) is True
    assert _so_nonce(kho) == n - KhoViec.NONCE_DON_TOI_DA + 1      # mỗi lần chỉ xoá tối đa NONCE_DON_TOI_DA
    assert kho.dung_nonce("moi2", t0 + KhoViec.NONCE_SONG_S + 2) is True
    assert _so_nonce(kho) == 2                                      # lần sau dọn nốt


def test_nonce_lap_khong_don_va_khong_mat_nonce(kho):
    """Nonce lặp vẫn trả False; dọn không đụng nonce vừa ghi dù `luc` truyền vào lùi giờ."""
    assert kho.dung_nonce("a", 1000.0) is True
    assert kho.dung_nonce("b", 500.0) is True
    assert kho.dung_nonce("a", 2000.0) is False
    assert _so_nonce(kho) == 2


def test_ds_loc(kho, dong):
    a = _tao(kho, khoa="1" * 19)
    dong.toi(1)
    b = _tao(kho, khoa="2" * 19)
    kho.chuyen(a["id"], ["cho"], "huy", "nhan")
    assert [v["id"] for v in kho.ds()] == [b["id"], a["id"]]
    assert [v["id"] for v in kho.ds(trang_thai=["huy"])] == [a["id"]]
    assert [v["id"] for v in kho.ds(khoa="2" * 19)] == [b["id"]]
    assert len(kho.ds(gioi_han=1)) == 1


def test_dem_trong_ngay_va_chi_phi(kho, dong):
    hom_nay = date(2026, 11, 17)
    a = _tao(kho, khoa="1" * 19, boi="nhan", session_id="s1")
    b = _tao(kho, khoa="2" * 19, boi="comeofage")
    _tao(kho, loai="radar_ban_tin", khoa="2026-11-17", boi="nhan")
    assert kho.dem_trong_ngay(None, hom_nay) == 3
    assert kho.dem_trong_ngay(None, hom_nay, boi="nhan") == 2
    assert kho.dem_trong_ngay("radar_ban_tin", hom_nay) == 1
    assert kho.dem_trong_ngay(None, hom_nay, chi_claude=True) == 0
    tn = lambda _l: frozenset()  # noqa: E731
    kho.nhan_viec_ke("nhe", set(), tn)
    kho.cong_chi_phi(a["id"], 1.5, 4, True)
    assert kho.dem_trong_ngay(None, hom_nay, chi_claude=True) == 1
    assert kho.chi_phi_ngay(hom_nay) == 1.5
    assert kho.chi_phi_ngay(date(2026, 11, 18)) == 0
    assert kho.dem_trong_ngay(None, date(2026, 11, 18)) == 0
    assert b["tao_boi"] == "comeofage"


def test_tao_mat_ket_noi_khong_quen_trang_thai(tmp_path, dong):
    """Mở lại DB (khởi động lại) vẫn thấy việc đang mở → vẫn chặn trùng."""
    db = tmp_path / "runner.db"
    v = KhoViec(db, dong).tao("douyin_uid", "1" * 19, {"uid": "1" * 19}, "nhe", "cho", "nhan")
    with pytest.raises(TrungViec):
        KhoViec(db, dong).tao("douyin_uid", "1" * 19, {"uid": "1" * 19}, "nhe", "cho", "nhan")
    assert KhoViec(db, dong).lay(v["id"])["trang_thai"] == "cho"
