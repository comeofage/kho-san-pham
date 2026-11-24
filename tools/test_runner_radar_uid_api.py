"""Test nối Radar UID vào runner: 8 route /radar/* của api.py (docs/radar-uid.md §7, §7.1) + khoá TypedDict §7.2.

Chạy: PYTHONIOENCODING=utf-8 python -B -m pytest tools/test_runner_radar_uid_api.py -q -p no:cacheprovider

Server API thật (ThreadingHTTPServer cổng ngẫu nhiên, request ký Ed25519 như Worker) + KhoViec thật + KhoRadarUid thật,
mọi file ở tmp_path. Không gọi EchoTik, không chạm E:\\kho-runner, không mở radar_uid.db thật.
"""
import ast
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import pytest

TOOLS = Path(__file__).parent
sys.path.insert(0, str(TOOLS))
from runner import api  # noqa: E402
from runner import danh_muc as dm  # noqa: E402
from runner import echotik as et  # noqa: E402
from runner import kho_radar_uid as krm  # noqa: E402
from runner import radar_uid_tinh as rut  # noqa: E402
from runner.han_muc import HAN_MUC_TRAN  # noqa: E402
from runner.kho_radar_uid import KhoRadarUid  # noqa: E402
from runner.kieu import MoiTruong  # noqa: E402
from test_runner_api import Dong, May  # noqa: E402

G1 = "1737422436677814024"        # > 2^53: id luôn là chuỗi ở mọi chặng
G2 = "1737422436677814025"
NGAY = "2026-11-23"
LOI_CHUA_BAT = {"loi": "Radar UID chưa bật"}


def uid_n(n: int) -> str:
    return f"17374224366778{n:05d}"


class KhoRadarDem(KhoRadarUid):
    """KhoRadarUid thật, đếm số lần đóng kết nối (mỗi request phải đóng kết nối của luồng HTTP, như _goi_kho_hoc)."""

    so_dong = 0

    def dong(self) -> None:
        type(self).so_dong += 1
        super().dong()


@pytest.fixture(autouse=True)
def _du_lieu_tam(tmp_path, monkeypatch):
    monkeypatch.setenv("KHO_RUNNER_DIR", str(tmp_path / "du_lieu"))
    KhoRadarDem.so_dong = 0


@pytest.fixture
def dong():
    return Dong(datetime(2026, 11, 23, 10, 12, 0))


@pytest.fixture
def mt(tmp_path, dong):
    for d in ("goc", "repo", "scripts", "radar", "sp"):
        (tmp_path / d).mkdir(exist_ok=True)
    return MoiTruong(
        gocs=[tmp_path / "goc"], repo_kho=tmp_path / "repo", thu_muc_scripts=tmp_path / "scripts",
        python_poster=tmp_path / "poster" / "python.exe", claude_exe=tmp_path / "claude.exe",
        agy_exe=tmp_path / "agy.exe", thu_muc_radar=tmp_path / "radar", thu_muc_sp=tmp_path / "sp",
        thu_muc_du_lieu=tmp_path / "du_lieu", cong_song=lambda c: True, chan_doan_kho=lambda r: None,
        ffmpeg_ngoai=lambda: False, thoi_luong_media=lambda f: 3.0, bay_gio=dong)


@pytest.fixture
def kr(tmp_path, dong):
    k = KhoRadarDem(tmp_path / "du_lieu" / "radar_uid.db", dong)
    k.mo()
    yield k
    k.dong()


@pytest.fixture
def may(tmp_path, mt, dong, kr):
    m = May(tmp_path, mt, dong, kho_radar=kr)
    yield m
    m.dong_lai()


def _may(tmp_path, mt, dong, kr, **hm_ha):
    return May(tmp_path, mt, dong, hm={**HAN_MUC_TRAN, **hm_ha}, kho_radar=kr)


# ---------- dữ liệu mẫu ----------

def _them_nhom(kr, goc=G1, trang_thai="da_tim", so_tt=0, boi="nhan"):
    kr.them_goc(goc, boi)
    kr.ghi_san_pham(goc, f"Sản phẩm gốc {goc[-4:]}", "Shop A")
    if so_tt:
        kr.ghi_tuong_tu(goc, [{"uid": uid_n(i + 1), "ten": f"Tương tự {i}", "gia": None, "ban_7d": None}
                              for i in range(so_tt)], "2026-11-23T09:00:00+07:00")
    kr.dat_trang_thai_nhom(goc, trang_thai)


def _video(i: int, view: int, creator: str | None = None, dang="2026-11-10T08:00:00+07:00") -> dict:
    return {"video_id": f"7300000000000000{i:03d}", "creator": creator or f"c{i % 4}", "follower": "5000",
            "view": str(view), "ban": None, "dang_luc": dang, "is_promote": 0}


def _chup(kr, uid, ngay, view_goc, gio=10, n_video=10):
    luc = f"{ngay}T{gio:02d}:00:00+07:00"
    assert kr.bat_dau_chup(uid, ngay, luc)
    kr.ghi_chup_ok({"uid": uid, "ngay": ngay, "lay_luc": luc, "echotik_cap_nhat": f"{ngay} 07:55", "ban_tong": "10",
                    "gia": "499.390₫", "hoa_hong": "10%", "ton": "562", "tong_creator": "6", "so_trang": 1,
                    "tong_trang": 1,
                    "videos": {v["video_id"]: v for v in (_video(i, view_goc + i * 100) for i in range(n_video))}})


def _nhieu_ngay(kr, uid, so_ngay=5, tang=300):
    d0 = datetime(2026, 11, 23) - timedelta(days=so_ngay - 1)
    for k in range(so_ngay):
        _chup(kr, uid, (d0 + timedelta(days=k)).date().isoformat(), 1000 + k * tang)


UID_RA_THEO_7_1 = {
    "uid", "vai", "trang_thai", "ten", "shop", "do_giong", "xep_loai", "uu_tien", "tam", "trung_vi", "trung_vi_truoc",
    "tong_delta_top5", "tong_delta_top5_truoc", "tang_toc", "tang_dot_ngot", "ly_do_tang_toc", "n_video", "n_creator",
    "n_doi", "ti_le_doi", "view_nho_trung_vi", "n_creator_nho", "cau_view_nho", "view_nho_30_trung_vi",
    "n_creator_nho_30", "follower_khong_doc", "trung_vi_14", "n_video_14", "n_video_moi_30", "cau_video_moi",
    "promote_x", "promote_y", "spark", "d_ban_ngay", "creator_moi_ngay", "gia", "hoa_hong", "ton", "du_lieu_luc",
    "echotik_cap_nhat", "so_snapshot", "phu_gio", "co", "co_canh_bao", "ly_do_thieu", "duoi_do_phan_giai"}


KHOA_UID_MOI_B11 = {"anh", "ban_tong", "chi_so", "xu_huong"}            # RU-B11 (+ xu hướng): shop/gia đã có sẵn trong UidRa
KHOA_NHOM_CU = {"goc", "ten", "trang_thai", "ly_do", "ten_ly_do", "tim_luc", "bat_dau_ngay", "ds"}
KHOA_NHOM_MOI_B11 = {"anh", "shop", "gia", "n_tuong_tu", "n_ghim"}
ANH_G = "https://cdn.echotik.live/img/goc.jpg"
ANH_1 = "https://cdn.echotik.live/img/tt1.jpg"


def _post(m, duong, body=None, **kw):
    return m.goi("POST", duong, {"boi": "nhan"} if body is None else body, **kw)


def _viec_radar(may_, loai=None):
    return [v for v in may_.kho.ds(None, gioi_han=100) if v["loai"].startswith("radar_uid")
            and (loai is None or v["loai"] == loai)]


def _viec_da_huy(m, loai, khoa, ts, boi="nhan"):
    """Một việc radar đã tạo hôm nay rồi huỷ (đã huỷ vẫn tính vào radar_uid_chay_ngay: đếm theo ngày tạo)."""
    v = m.kho.tao(loai, khoa, ts, "nhe", "cho", boi)
    m.kho.chuyen(v["id"], ["cho"], "huy", "nhan")
    return v


def _su_kien(kr):
    with sqlite3.connect(f"file:{kr.duong_dan.as_posix()}?mode=ro", uri=True) as c:
        return c.execute("SELECT boi, hanh_dong, goc, uid FROM su_kien ORDER BY id").fetchall()


# ================================================================ 503 khi Radar chưa bật

ROUTE_503 = [("GET", "/radar/bang"), ("GET", f"/radar/uid/{G1}"), ("POST", "/radar/goc"), ("POST", "/radar/chup-lai"),
             ("POST", f"/radar/goc/{G1}/tim-lai"), ("POST", f"/radar/goc/{G1}/ngung"),
             ("POST", f"/radar/goc/{G1}/theo-lai"), ("POST", f"/radar/goc/{G1}/them-tay"),
             ("POST", f"/radar/goc/{G1}/uid/{G2}/ghim"), ("POST", f"/radar/goc/{G1}/uid/{G2}/bo-ghim"),
             ("POST", f"/radar/goc/{G1}/uid/{G2}/loai"), ("POST", f"/radar/goc/{G1}/uid/{G2}/bo-loai")]


@pytest.mark.parametrize("pt,duong", ROUTE_503)
def test_kho_radar_none_moi_route_503(tmp_path, mt, dong, pt, duong):
    m = May(tmp_path, mt, dong)                                   # không truyền kho_radar
    try:
        body = {"boi": "nhan", "uid": G2}
        assert m.goi(pt, duong, None if pt == "GET" else body) == (503, LOI_CHUA_BAT)
        assert m.kho.ds() == []
    finally:
        m.dong_lai()


def test_auth_truoc_khi_xet_radar(may):
    assert may.goi("GET", "/radar/bang", khoa=False)[0] == 401
    assert may.goi("GET", "/radar/bang", khoa="sai-khoa")[0] == 401
    assert may.goi("POST", "/radar/goc", {"boi": "nhan", "uid": G1}, ky=False)[0] == 401
    assert may.goi("POST", "/radar/goc", {"boi": "nhan", "uid": G1}, khoa=False)[0] == 401
    assert _viec_radar(may) == []


# ================================================================ GET /radar/bang

def test_bang_rong(may):
    s, d = may.goi("GET", "/radar/bang")
    assert s == 200
    assert set(d) == {"luc", "ngay", "token", "han_muc", "lan", "nhom"}
    assert d["luc"] == "2026-11-23T10:12:00+07:00" and d["ngay"] == NGAY
    assert d["token"] == {"trang_thai": "chua_kiem", "cau": ""}
    assert d["han_muc"] == {"bat": 1, "goi_ngay_toi_da": 60, "goi_hom_nay": 0, "goc_toi_da": 2}
    assert d["lan"] == {"trang_thai": "chua_chay", "ly_do": "", "ngay": "", "ten_ly_do": ""}
    assert d["nhom"] == []


def test_bang_han_muc_hieu_luc_chi_ha(tmp_path, mt, dong, kr):
    m = _may(tmp_path, mt, dong, kr, radar_uid_bat=0, radar_uid_goi_ngay=40)
    m2 = _may(tmp_path / "b", mt, dong, kr, radar_uid_goi_ngay=999)           # dict bị nới vẫn kẹp về trần code
    try:
        assert m.goi("GET", "/radar/bang")[1]["han_muc"] == {"bat": 0, "goi_ngay_toi_da": 40, "goi_hom_nay": 0,
                                                              "goc_toi_da": 2}
        assert m2.goi("GET", "/radar/bang")[1]["han_muc"]["goi_ngay_toi_da"] == 60
    finally:
        m.dong_lai()
        m2.dong_lai()


def test_bang_goi_hom_nay_token_va_lan(may, kr):
    assert kr.tinh_goi(NGAY, 22, 60)
    kr.ghi_token("thieu", "token_thieu")
    kr.bat_dau_lan(NGAY, "hang-ngay", "j20261123100000abcd")
    kr.ket_thuc_lan(NGAY, "hang-ngay", "j20261123100000abcd", "tu_dung", "het_han_muc_goi", 60)
    s, d = may.goi("GET", "/radar/bang")
    assert s == 200
    assert d["han_muc"]["goi_hom_nay"] == 22
    assert d["token"] == {"trang_thai": "thieu", "cau": "Chưa có token EchoTik: đăng nhập EchoTik trên Chrome để "
                                                       "tạo lại file token."}
    assert d["lan"] == {"trang_thai": "tu_dung", "ly_do": "het_han_muc_goi", "ngay": NGAY,
                        "ten_ly_do": "Hết ngân sách gọi EchoTik hôm nay (22/60)."}
    kr.ghi_token("het_han", "token_het_han")
    assert may.goi("GET", "/radar/bang")[1]["token"]["cau"].startswith("EchoTik trả trang lỗi: token hết hạn")
    kr.ghi_token("ok", "")
    assert may.goi("GET", "/radar/bang")[1]["token"] == {"trang_thai": "ok", "cau": ""}


@pytest.mark.parametrize("ly_do,cau", [
    ("token_thieu", "Chưa có token EchoTik: đăng nhập EchoTik trên Chrome để tạo lại file token."),
    ("rate_limit", "EchoTik giới hạn lượt gọi: thử lại ngày mai."),
    ("mang_lien_tiep", "Mất mạng tới EchoTik."),
    ("khong_tim_thay", "EchoTik không có UID này."),
    ("khong_co_video", "EchoTik chưa có video nào cho UID này."),
    ("dinh_dang", "EchoTik trả dữ liệu lạ."),
    ("keyword_khong_loc", "EchoTik không lọc theo từ khoá nên không tìm được tương tự: thêm tay UID."),
])
def test_ten_ly_do_theo_bang_6_3(ly_do, cau):
    assert api.ten_ly_do_radar(ly_do, 0, 60) == cau


@pytest.mark.parametrize("ly_do", ["nhom_ngung", "khong_co_nhom", "loi_bat_ngo", "tham_so_sai", "khong_chup_duoc"])
def test_ten_ly_do_bon_ma_con_thieu_co_cau_sach(ly_do):
    cau = api.ten_ly_do_radar(ly_do, 0, 60)
    assert cau.strip() != ""
    assert ly_do in api.TEN_LY_DO_RADAR
    for cam in (":\\", ":/", "Traceback", "token", "Token"):
        assert cam not in cau


def test_ten_ly_do_la_hoac_rong():
    assert api.ten_ly_do_radar("", 0, 60) == ""
    assert api.ten_ly_do_radar("ma_la_khong_co", 0, 60) == ""
    assert api.ten_ly_do_radar("het_han_muc_goi", 60, 60) == "Hết ngân sách gọi EchoTik hôm nay (60/60)."


def test_bang_nhom_loi_tim_co_ten_ly_do(may, kr):
    _them_nhom(kr, trang_thai="loi_tim")
    kr.dat_trang_thai_nhom(G1, "loi_tim", "keyword_khong_loc")
    n = may.goi("GET", "/radar/bang")[1]["nhom"][0]
    assert (n["goc"], n["trang_thai"], n["ly_do"]) == (G1, "loi_tim", "keyword_khong_loc")
    assert n["ten_ly_do"].startswith("EchoTik không lọc theo từ khoá")
    assert set(n) == {"goc", "ten", "trang_thai", "ly_do", "ten_ly_do", "tim_luc", "bat_dau_ngay", "ds",
                      "anh", "shop", "gia", "n_tuong_tu", "n_ghim"}      # RU-B11 chỉ thêm khoá
    assert n["bat_dau_ngay"] == NGAY and n["tim_luc"] is None


def test_bang_dung_xep_hang_uid_dung_7_1_id_la_chuoi(may, kr):
    _them_nhom(kr, so_tt=2)
    _nhieu_ngay(kr, G1)
    _nhieu_ngay(kr, uid_n(1), tang=900)
    s, d = may.goi("GET", "/radar/bang")
    assert s == 200 and len(d["nhom"]) == 1
    n = d["nhom"][0]
    assert n["goc"] == G1 and isinstance(n["goc"], str) and n["ten"] == f"Sản phẩm gốc {G1[-4:]}"
    assert n["trang_thai"] == "da_tim"
    ds = {u["uid"]: u for u in n["ds"]}
    assert set(ds) == {G1, uid_n(1), uid_n(2)} and all(isinstance(k, str) for k in ds)
    hom_nay = datetime(2026, 11, 23, 10, 12, 0)
    for uid, u in ds.items():
        assert UID_RA_THEO_7_1 <= set(u), UID_RA_THEO_7_1 - set(u)      # khoá cũ còn nguyên (RU-B11 chỉ THÊM khoá)
        assert set(u) - UID_RA_THEO_7_1 == KHOA_UID_MOI_B11
        snaps = kr.doc_snapshots(uid, "2000-01-01")
        mong = rut.xep_hang_uid(snaps, hom_nay, NGAY)                  # NGUỒN SỰ THẬT: đúng hàm đã duyệt
        for k, v in mong.items():
            assert u[k] == v, (uid, k)
    assert (ds[G1]["vai"], ds[G1]["trang_thai"], ds[G1]["do_giong"], ds[G1]["shop"]) == ("goc", "dang_theo", None,
                                                                                         "Shop A")
    assert ds[uid_n(1)]["vai"] == "tuong_tu" and ds[uid_n(1)]["ten"] == "Tương tự 0"
    assert ds[uid_n(2)]["so_snapshot"] == 0 and ds[uid_n(2)]["xep_loai"] == "chua_du" and ds[uid_n(2)]["co"] == [
        "THIEU_MAU"]                                                   # UID chưa chụp: vẫn có dòng, kèm lý do, không 0
    assert ds[uid_n(2)]["trung_vi"] is None and ds[uid_n(2)]["ly_do_thieu"] == ["chưa có snapshot"]
    assert ds[G1]["so_snapshot"] == 5 and ds[G1]["spark"] and ds[G1]["gia"] == "499.390₫"
    # JSON thô: id không bao giờ là số (cấm Number() ở chặng web)
    tho = may.goi("GET", "/radar/bang")
    assert tho[0] == 200
    assert not re.search(r'"(goc|uid)":\s*\d', json.dumps(tho[1], ensure_ascii=False))


def test_bang_them_anh_shop_gia_ban_tong_dem(may, kr):
    _them_nhom(kr, so_tt=2)
    kr.ghi_san_pham(G1, "Sản phẩm gốc", "Shop A", ANH_G)
    kr.ghi_san_pham(uid_n(1), "Tương tự 0", "Shop B", ANH_1)               # uid_n(2): chưa có ảnh, chưa chụp
    kr.dat_uid(G1, uid_n(1), "ghim", "nhan")
    _nhieu_ngay(kr, G1)
    _nhieu_ngay(kr, uid_n(1))
    s, d = may.goi("GET", "/radar/bang")
    assert s == 200
    n = d["nhom"][0]
    assert KHOA_NHOM_CU | KHOA_NHOM_MOI_B11 == set(n)
    assert (n["anh"], n["shop"], n["gia"], n["n_tuong_tu"], n["n_ghim"]) == (ANH_G, "Shop A", "499.390₫", 2, 1)
    ds = {u["uid"]: u for u in n["ds"]}
    assert (ds[G1]["anh"], ds[G1]["shop"], ds[G1]["gia"], ds[G1]["ban_tong"]) == (ANH_G, "Shop A", "499.390₫", 10)
    assert (ds[uid_n(1)]["anh"], ds[uid_n(1)]["shop"], ds[uid_n(1)]["ban_tong"]) == (ANH_1, "Shop B", 10)
    chua = ds[uid_n(2)]                                                    # chưa ảnh / chưa chụp ⇒ '' và null, đủ khoá
    assert chua["anh"] == "" and chua["gia"] is None and chua["ban_tong"] is None and isinstance(chua["shop"], str)
    assert all(isinstance(u["uid"], str) for u in n["ds"]) and isinstance(n["goc"], str)
    assert not re.search(r'"(goc|uid)":\s*\d', json.dumps(d, ensure_ascii=False))


def test_bang_nhom_chua_chup_gia_null_anh_rong(may, kr):
    _them_nhom(kr)
    n = may.goi("GET", "/radar/bang")[1]["nhom"][0]
    assert n["anh"] == "" and n["gia"] is None and n["n_tuong_tu"] == 0 and n["n_ghim"] == 0
    assert n["ds"][0]["ban_tong"] is None


def test_bang_anh_la_trong_db_tra_rong(may, kr):
    _them_nhom(kr, so_tt=1)
    with sqlite3.connect(kr.duong_dan.as_posix()) as c:                     # DB cũ/bị sửa tay: ghi thẳng giá trị lạ
        c.execute("UPDATE san_pham SET anh=? WHERE uid=?", ("http://evil.example/x.jpg", G1))
        c.execute("UPDATE san_pham SET anh=? WHERE uid=?", (r"C:\Users\Mi\x.jpg", uid_n(1)))
    n = may.goi("GET", "/radar/bang")[1]["nhom"][0]
    assert n["anh"] == "" and all(u["anh"] == "" for u in n["ds"])


def test_bang_khong_ro_duong_dan_hay_token(may, kr):
    _them_nhom(kr, so_tt=1)
    kr.ghi_san_pham(G1, "Sản phẩm gốc", "Shop A", ANH_G)
    _nhieu_ngay(kr, G1)
    tho = json.dumps(may.goi("GET", "/radar/bang")[1], ensure_ascii=False)
    for cam in ("radar_uid.db", str(kr.duong_dan.parent), "Users", "C:\\", "\\\\", "token_tt", "Bearer"):
        assert cam not in tho, cam


def _khoa_sap(u):
    rank = {"dang_co_da": 0, "chua_co_da": 1, "chua_du": 2, "chan": 3}
    return (u["trang_thai"] == "loai", rank[u["xep_loai"]], u["trung_vi"] is None, -(u["trung_vi"] or 0),
            -(u["n_video"] or 0), u["uid"])


def test_sap_xep_5_4_loai_o_cuoi():
    def u(uid, xep, tv, nv, tt="dang_theo"):
        return {"uid": uid, "xep_loai": xep, "trung_vi": tv, "n_video": nv, "trang_thai": tt}
    ds = [u("9", "chan", 50, 9), u("8", "chua_du", None, 3), u("7", "chua_co_da", 10, 9), u("6", "dang_co_da", 5, 9),
          u("5", "dang_co_da", 700, 2), u("4", "chua_du", 30, 3), u("3", "dang_co_da", 700, 8),
          u("2", "chua_co_da", 10, 9), u("1", "dang_co_da", 700, 8, "loai"), u("0", "chua_du", None, 7)]
    ra = [x["uid"] for x in api.sap_xep_uid_ra(ds)]
    # dang_co_da: trung_vi giảm (700,700,5) rồi n_video giảm (8 > 2); chua_co_da cùng số → uid; chua_du: số trước, null cuối
    assert ra == ["3", "5", "6", "2", "7", "4", "0", "8", "9", "1"]


def test_bang_ds_sap_dung_quy_tac(may, kr):
    _them_nhom(kr, so_tt=3)
    for k, uid in enumerate((G1, uid_n(1), uid_n(3))):
        _nhieu_ngay(kr, uid, tang=100 * (k + 1))
    kr.dat_uid(G1, uid_n(2), "loai", "nhan")
    ds = may.goi("GET", "/radar/bang")[1]["nhom"][0]["ds"]
    assert [u["uid"] for u in ds] == [u["uid"] for u in sorted(ds, key=_khoa_sap)]
    assert ds[-1]["uid"] == uid_n(2) and ds[-1]["trang_thai"] == "loai"        # loại ẩn xuống cuối, vẫn trả để Bỏ loại


def test_bang_nhieu_nhom_va_nhom_ngung_van_hien(may, kr):
    _them_nhom(kr, G1, so_tt=1)
    _them_nhom(kr, G2, trang_thai="cho_tim")
    kr.dat_goc(G2, "ngung", "nhan")
    d = may.goi("GET", "/radar/bang")[1]
    assert [(n["goc"], n["trang_thai"]) for n in d["nhom"]] == [(G1, "da_tim"), (G2, "ngung")]


def test_bang_che_bi_mat_va_dong_ket_noi(tmp_path, mt, dong, kr):
    m = May(tmp_path, mt, dong, kho_radar=kr, che=lambda s: s.replace("BIMAT-123", "***"))
    try:
        kr.them_goc(G1, "nhan")
        kr.ghi_san_pham(G1, "Áo BIMAT-123", "Shop BIMAT-123")
        before = KhoRadarDem.so_dong
        s, d = m.goi("GET", "/radar/bang")
        assert s == 200 and "BIMAT" not in json.dumps(d, ensure_ascii=False)
        assert d["nhom"][0]["ten"] == "Áo ***"
        assert KhoRadarDem.so_dong > before                          # đóng kết nối luồng HTTP sau mỗi request
    finally:
        m.dong_lai()


# ================================================================ GET /radar/uid/<uid>

def test_chi_tiet_uid(may, kr):
    _them_nhom(kr, so_tt=1)
    _nhieu_ngay(kr, G1, so_ngay=6)
    s, d = may.goi("GET", f"/radar/uid/{G1}")
    assert s == 200
    assert set(d) == UID_RA_THEO_7_1 | {"chuoi", "video"}
    tu_bang = next(u for u in may.goi("GET", "/radar/bang")[1]["nhom"][0]["ds"] if u["uid"] == G1)
    for k in UID_RA_THEO_7_1:                                             # ChiTiet = UidRa + chuoi + video
        assert d[k] == tu_bang[k], k
    assert len(d["chuoi"]) == 5 and all(set(k) == {"ngay", "gio", "hop_le", "trung_vi", "tong_delta_top5", "n_video",
                                                   "n_creator", "n_doi", "ti_le_doi"} for k in d["chuoi"])
    assert [k["ngay"] for k in d["chuoi"]] == ["2026-11-19", "2026-11-20", "2026-11-21", "2026-11-22", NGAY]
    assert all(k["hop_le"] and k["gio"] == 24.0 for k in d["chuoi"])
    # kỳ cuối của chuỗi khớp đúng chỉ số chính của UidRa (bắt lệch giữa chuoi và xep_hang_uid)
    assert (d["chuoi"][-1]["trung_vi"], d["chuoi"][-1]["tong_delta_top5"], d["chuoi"][-1]["n_video"]) == (
        d["trung_vi"], d["tong_delta_top5"], d["n_video"])
    assert 0 < len(d["video"]) <= 50
    assert all(set(v) == {"video_id", "creator", "follower", "view", "d24", "dang_luc", "is_promote"} for v in d["video"])
    assert all(isinstance(v["video_id"], str) for v in d["video"])
    assert any(isinstance(v["d24"], (int, float)) for v in d["video"])
    assert {v["video_id"] for v in d["video"]} == {_video(i, 0)["video_id"] for i in range(10)}


def test_chi_tiet_chuoi_toi_da_14_ky_va_video_toi_da_50(may, kr):
    _them_nhom(kr)
    d0 = datetime(2026, 11, 23) - timedelta(days=19)
    for k in range(20):
        _chup(kr, G1, (d0 + timedelta(days=k)).date().isoformat(), 1000 + k * 50, n_video=60)
    d = may.goi("GET", f"/radar/uid/{G1}")[1]
    assert len(d["chuoi"]) == 14 and d["chuoi"][-1]["ngay"] == NGAY
    assert len(d["video"]) == 50


def test_chi_tiet_uid_chua_chup_chuoi_va_video_rong(may, kr):
    _them_nhom(kr)
    d = may.goi("GET", f"/radar/uid/{G1}")[1]
    assert d["chuoi"] == [] and d["video"] == [] and d["xep_loai"] == "chua_du"


@pytest.mark.parametrize("uid", [uid_n(99), "1" * 19, "abc", "123", "1" * 20, "１７３７４２２４３６６７７８１４０２４"])
def test_chi_tiet_404_ke_ca_uid_sai_dang(may, kr, uid):
    _them_nhom(kr)
    assert may.goi("GET", f"/radar/uid/{quote(uid)}") == (404, {"loi": "Không có UID này trong Radar"})


def test_chi_tiet_uid_chi_o_san_pham_khong_o_nhom_404(may, kr):
    kr.ghi_san_pham(uid_n(77), "mồ côi", "")
    assert may.goi("GET", f"/radar/uid/{uid_n(77)}")[0] == 404


# ================================================================ POST /radar/goc

def test_goc_moi_202_tao_viec_nap(may, kr):
    s, d = _post(may, "/radar/goc", {"boi": "nhan", "uid": G1})
    assert s == 202 and d["da_co"] is False and d["goc"] == G1 and re.fullmatch(r"j\d{14}[a-z0-9]{4}", d["viec_id"])
    v = may.kho.lay(d["viec_id"])
    assert (v["loai"], v["khoa"], v["tham_so"], v["tao_boi"], v["trang_thai"], v["lan_chay"]) == (
        "radar_uid_nap", G1, {"goc": G1}, "nhan", "cho", "nhe")
    n = may.goi("GET", "/radar/bang")[1]["nhom"][0]
    assert (n["goc"], n["trang_thai"]) == (G1, "cho_tim")
    assert ("nhan", "them_goc", G1, G1) in _su_kien(kr)                 # mọi lệnh ghi vào su_kien
    assert KhoRadarDem.so_dong > 0


def test_goc_da_co_khong_tao_viec_moi(may, kr):
    _post(may, "/radar/goc", {"boi": "nhan", "uid": G1})
    s, d = _post(may, "/radar/goc", {"boi": "nhan", "uid": G1})
    assert (s, d) == (202, {"da_co": True, "goc": G1})
    assert len(_viec_radar(may)) == 1


@pytest.mark.parametrize("body", [{"boi": "nhan"}, {"boi": "nhan", "uid": None}, {"boi": "nhan", "uid": 1737422436677814024},
                                  {"boi": "nhan", "uid": "123"}, {"boi": "nhan", "uid": G1 + "0"},
                                  {"boi": "nhan", "uid": G1 + "\n"}, {"boi": "nhan", "uid": "１７３７４２２４３６６７７８１４０２４"}])
def test_goc_uid_sai_400(may, kr, body):
    s, d = _post(may, "/radar/goc", body)
    assert (s, d) == (400, {"loi": "UID phải đủ 19 chữ số"})
    assert _viec_radar(may) == [] and kr.ds_nhom() == []


def test_goc_thieu_boi_400(may, kr):
    assert _post(may, "/radar/goc", {"uid": G1})[0] == 400
    assert kr.ds_nhom() == []


def test_goc_du_2_goc_409(may, kr):
    _post(may, "/radar/goc", {"boi": "nhan", "uid": G1})
    _post(may, "/radar/goc", {"boi": "nhan", "uid": G2})
    s, d = _post(may, "/radar/goc", {"boi": "nhan", "uid": uid_n(50)})
    assert (s, d) == (409, {"loi": "Đã đủ 2 UID gốc: ngừng bớt"})
    assert len(_viec_radar(may)) == 2 and len(kr.ds_nhom()) == 2


def test_goc_du_24_uid_409(may, kr):
    _them_nhom(kr, G1, so_tt=10)
    kr.them_tay(G1, uid_n(60), "nhan")
    kr.them_tay(G1, uid_n(61), "nhan")
    kr.them_tay(G1, uid_n(62), "nhan")                                   # nhóm 1: 1 + 10 + 3 = 14
    kr.them_goc(G2, "nhan")
    kr.ghi_tuong_tu(G2, [{"uid": uid_n(100 + i), "ten": "x", "gia": None, "ban_7d": None} for i in range(12)],
                    "2026-11-23T09:00:00+07:00")                         # chạm trần 24 toàn DB
    s, d = _post(may, f"/radar/goc/{G2}/them-tay", {"boi": "nhan", "uid": uid_n(200)})
    assert (s, d) == (409, {"loi": "Đã đủ 24 UID theo dõi"})


def test_goc_cau_dao_tat_409_khong_ghi_gi(tmp_path, mt, dong, kr):
    m = _may(tmp_path, mt, dong, kr, radar_uid_bat=0)
    try:
        s, d = _post(m, "/radar/goc", {"boi": "nhan", "uid": G1})
        assert (s, d) == (409, {"loi": "Radar UID đang tắt"})
        assert kr.ds_nhom() == [] and _viec_radar(m) == []
        assert m.goi("GET", "/radar/bang")[0] == 200                     # đọc vẫn được khi tắt
    finally:
        m.dong_lai()


def test_goc_vuot_6_viec_ngay_429_khong_tao_nhom(may, kr):
    for i in range(6):                                                    # 6 việc radar do API tạo hôm nay
        _viec_da_huy(may, "radar_uid_nap", uid_n(300 + i), {"goc": uid_n(300 + i)})
    s, d = _post(may, "/radar/goc", {"boi": "nhan", "uid": G1})
    assert s == 429 and "radar_uid_chay_ngay" in d["loi"]
    assert kr.ds_nhom() == []                                             # chặn TRƯỚC khi ghi nhóm: không để nhóm mồ côi
    assert len(_viec_radar(may)) == 6


def test_goc_viec_he_thong_khong_tinh_vao_6_viec(may, kr):
    for i in range(6):
        _viec_da_huy(may, "radar_uid_hang_ngay", NGAY if i == 0 else f"2026-11-{i:02d}", {"ngay": NGAY}, "he_thong")
    assert _post(may, "/radar/goc", {"boi": "nhan", "uid": G1})[0] == 202


def test_goc_body_qua_lon_413(may):
    s, d = may.goi("POST", "/radar/goc", raw=b'{"boi":"nhan","uid":"%s","x":"%s"}' % (G1.encode(), b"a" * 20000))
    assert s == 413


def test_goc_body_khong_phai_object_400(may):
    assert may.goi("POST", "/radar/goc", raw=b"[1]")[0] == 400


# ================================================================ tim-lai

def test_tim_lai_202_dat_cho_tim_va_tao_viec(may, kr):
    _them_nhom(kr, so_tt=2)
    s, d = _post(may, f"/radar/goc/{G1}/tim-lai")
    assert s == 202 and set(d) == {"viec_id"}
    v = may.kho.lay(d["viec_id"])
    assert (v["loai"], v["khoa"], v["tham_so"], v["tao_boi"]) == ("radar_uid_nap", G1, {"goc": G1}, "nhan")
    assert may.goi("GET", "/radar/bang")[1]["nhom"][0]["trang_thai"] == "cho_tim"


def test_tim_lai_404(may, kr):
    assert _post(may, f"/radar/goc/{G2}/tim-lai") == (404, {"loi": "Không có UID này trong Radar"})
    assert _viec_radar(may) == []


def test_tim_lai_dang_tim_khong_viec_mo_la_ket_nen_tim_lai_200(may, kr):
    """Việc nạp đã huỷ/hết lần thử/runner chết ⇒ nhóm kẹt dang_tim không việc mở: tim-lai gỡ kẹt, tạo đúng 1 việc nạp."""
    _them_nhom(kr, trang_thai="dang_tim")
    v0 = _viec_da_huy(may, "radar_uid_nap", G1, {"goc": G1})
    s, d = _post(may, f"/radar/goc/{G1}/tim-lai")
    assert s == 202 and set(d) == {"viec_id"}
    moi = [v for v in _viec_radar(may, "radar_uid_nap") if v["id"] != v0["id"]]
    assert [v["id"] for v in moi] == [d["viec_id"]] and moi[0]["khoa"] == G1
    assert may.goi("GET", "/radar/bang")[1]["nhom"][0]["trang_thai"] != "dang_tim"
    assert _post(may, f"/radar/goc/{G1}/tim-lai")[0] == 409          # giờ đã có việc mở: không tạo trùng
    assert len(_viec_radar(may, "radar_uid_nap")) == 2


def test_tim_lai_dang_tim_co_viec_mo_409_nhu_cu(may, kr):
    _them_nhom(kr, trang_thai="dang_tim")
    may.kho.tao("radar_uid_nap", G1, {"goc": G1}, "nhe", "cho", "nhan")
    assert _post(may, f"/radar/goc/{G1}/tim-lai") == (409, {"loi": "Nhóm đang được tìm: chờ xong"})
    assert len(_viec_radar(may)) == 1
    assert may.goi("GET", "/radar/bang")[1]["nhom"][0]["trang_thai"] == "dang_tim"


def test_tim_lai_dang_tim_ket_van_ton_trong_han_muc_429_khong_doi_trang_thai(may, kr):
    _them_nhom(kr, trang_thai="dang_tim")
    for i in range(6):
        _viec_da_huy(may, "radar_uid_nap", uid_n(300 + i), {"goc": uid_n(300 + i)})
    s, d = _post(may, f"/radar/goc/{G1}/tim-lai")
    assert s == 429 and "radar_uid_chay_ngay" in d["loi"]
    assert may.goi("GET", "/radar/bang")[1]["nhom"][0]["trang_thai"] == "dang_tim"


def test_tim_lai_dang_tim_ket_cau_dao_tat_409(tmp_path, mt, dong, kr):
    _them_nhom(kr, trang_thai="dang_tim")
    m = _may(tmp_path, mt, dong, kr, radar_uid_bat=0)
    try:
        assert _post(m, f"/radar/goc/{G1}/tim-lai") == (409, {"loi": "Radar UID đang tắt"})
    finally:
        m.dong_lai()


def test_tim_lai_da_co_viec_nap_mo_409_khong_doi_trang_thai(may, kr):
    _them_nhom(kr, trang_thai="cho_tim")
    may.kho.tao("radar_uid_nap", G1, {"goc": G1}, "nhe", "cho", "nhan")
    assert _post(may, f"/radar/goc/{G1}/tim-lai") == (409, {"loi": "Nhóm đang được tìm: chờ xong"})
    assert len(_viec_radar(may)) == 1


def test_tim_lai_nhom_ngung_409(may, kr):
    _them_nhom(kr)
    kr.dat_goc(G1, "ngung", "nhan")
    s, d = _post(may, f"/radar/goc/{G1}/tim-lai")
    assert s == 409 and "ngừng" in d["loi"]
    assert _viec_radar(may) == [] and may.goi("GET", "/radar/bang")[1]["nhom"][0]["trang_thai"] == "ngung"


def test_tim_lai_429_khong_doi_trang_thai(may, kr):
    _them_nhom(kr)
    for i in range(6):
        _viec_da_huy(may, "radar_uid_nap", uid_n(300 + i), {"goc": uid_n(300 + i)})
    s, d = _post(may, f"/radar/goc/{G1}/tim-lai")
    assert s == 429 and "radar_uid_chay_ngay" in d["loi"]
    assert may.goi("GET", "/radar/bang")[1]["nhom"][0]["trang_thai"] == "da_tim"


def test_tim_lai_cau_dao_tat_409(tmp_path, mt, dong, kr):
    _them_nhom(kr)
    m = _may(tmp_path, mt, dong, kr, radar_uid_bat=0)
    try:
        assert _post(m, f"/radar/goc/{G1}/tim-lai") == (409, {"loi": "Radar UID đang tắt"})
    finally:
        m.dong_lai()


# ================================================================ ngung / theo-lai

def test_ngung_va_theo_lai_200(may, kr):
    _them_nhom(kr, so_tt=1)                                               # đã tìm xong (có tim_luc) → theo-lai về da_tim
    assert _post(may, f"/radar/goc/{G1}/ngung") == (200, {"goc": G1, "trang_thai": "ngung"})
    assert _post(may, f"/radar/goc/{G1}/theo-lai") == (200, {"goc": G1, "trang_thai": "da_tim"})
    assert [(h, g) for _, h, g, _ in _su_kien(kr) if h in ("ngung", "theo-lai")] == [("ngung", G1), ("theo-lai", G1)]
    assert _viec_radar(may) == []                                         # đã có kết quả tìm: không cần nạp lại


def test_ngung_theo_lai_404(may, kr):
    for act in ("ngung", "theo-lai"):
        assert _post(may, f"/radar/goc/{G2}/{act}") == (404, {"loi": "Không có UID này trong Radar"})


def test_theo_lai_vuot_2_goc_409(may, kr):
    _them_nhom(kr, G1)
    _them_nhom(kr, G2)
    _post(may, f"/radar/goc/{G1}/ngung")
    kr.them_goc(uid_n(70), "nhan")                                        # đủ 2 gốc đang theo: G2 + uid_n(70)
    assert _post(may, f"/radar/goc/{G1}/theo-lai") == (409, {"loi": "Đã đủ 2 UID gốc: ngừng bớt"})


def test_theo_lai_chua_tim_tao_viec_nap_neu_khong_co(may, kr):
    kr.them_goc(G1, "nhan")                                               # nhóm cho_tim, chưa có việc nạp nào
    _post(may, f"/radar/goc/{G1}/ngung")
    s, d = _post(may, f"/radar/goc/{G1}/theo-lai")
    assert (s, d) == (200, {"goc": G1, "trang_thai": "cho_tim"})
    assert [v["tham_so"] for v in _viec_radar(may, "radar_uid_nap")] == [{"goc": G1}]


def test_theo_lai_chua_tim_viec_nap_dang_mo_van_200_khong_tao_trung(may, kr, caplog):
    kr.them_goc(G1, "nhan")
    may.kho.tao("radar_uid_nap", G1, {"goc": G1}, "nhe", "cho", "nhan")
    _post(may, f"/radar/goc/{G1}/ngung")
    with caplog.at_level("WARNING"):
        s, d = _post(may, f"/radar/goc/{G1}/theo-lai")
    assert (s, d) == (200, {"goc": G1, "trang_thai": "cho_tim"})
    assert len(_viec_radar(may)) == 1                                     # không tạo trùng việc nạp đang mở
    assert any("không tạo được việc nạp" in r.getMessage() for r in caplog.records)   # không nuốt lỗi: có log


def test_ngung_khi_cau_dao_tat_409(tmp_path, mt, dong, kr):
    _them_nhom(kr)
    m = _may(tmp_path, mt, dong, kr, radar_uid_bat=0)
    try:
        assert _post(m, f"/radar/goc/{G1}/ngung") == (409, {"loi": "Radar UID đang tắt"})
    finally:
        m.dong_lai()


# ================================================================ them-tay

def test_them_tay_200_va_su_kien(may, kr):
    _them_nhom(kr)
    s, d = _post(may, f"/radar/goc/{G1}/them-tay", {"boi": "nhan", "uid": uid_n(5)})
    assert s == 200 and d == {"goc": G1, "uid": uid_n(5)}
    ds = may.goi("GET", "/radar/bang")[1]["nhom"][0]["ds"]
    assert [(u["vai"], u["trang_thai"]) for u in ds if u["uid"] == uid_n(5)] == [("them_tay", "dang_theo")]
    assert ("nhan", "them_tay", G1, uid_n(5)) in _su_kien(kr)


@pytest.mark.parametrize("body", [{"boi": "nhan"}, {"boi": "nhan", "uid": "12"}, {"boi": "nhan", "uid": 5}])
def test_them_tay_400(may, kr, body):
    _them_nhom(kr)
    assert _post(may, f"/radar/goc/{G1}/them-tay", body) == (400, {"loi": "UID phải đủ 19 chữ số"})


def test_them_tay_404(may, kr):
    assert _post(may, f"/radar/goc/{G2}/them-tay", {"boi": "nhan", "uid": uid_n(5)})[0] == 404


def test_them_tay_du_3_409(may, kr):
    _them_nhom(kr)
    for i in range(3):
        assert _post(may, f"/radar/goc/{G1}/them-tay", {"boi": "nhan", "uid": uid_n(5 + i)})[0] == 200
    assert _post(may, f"/radar/goc/{G1}/them-tay", {"boi": "nhan", "uid": uid_n(9)}) == (
        409, {"loi": "Đã đủ 3 UID thêm tay"})


def test_them_tay_dang_bi_loai_409(may, kr):
    _them_nhom(kr, so_tt=1)
    _post(may, f"/radar/goc/{G1}/uid/{uid_n(1)}/loai")
    assert _post(may, f"/radar/goc/{G1}/them-tay", {"boi": "nhan", "uid": uid_n(1)}) == (
        409, {"loi": "UID này đang bị loại: bỏ loại trước"})


# ================================================================ ghim / bo-ghim / loai / bo-loai

@pytest.mark.parametrize("act,truoc,sau", [("ghim", "dang_theo", "ghim"), ("bo-ghim", "ghim", "dang_theo"),
                                           ("loai", "dang_theo", "loai"), ("bo-loai", "loai", "dang_theo")])
def test_uid_hanh_dong_200(may, kr, act, truoc, sau):
    _them_nhom(kr, so_tt=2)
    if truoc == "ghim":
        kr.dat_uid(G1, uid_n(1), "ghim", "nhan")
    elif truoc == "loai":
        kr.dat_uid(G1, uid_n(1), "loai", "nhan")
    assert _post(may, f"/radar/goc/{G1}/uid/{uid_n(1)}/{act}") == (200, {"uid": uid_n(1), "trang_thai": sau})
    assert any(h == act and u == uid_n(1) and b == "nhan" for b, h, _, u in _su_kien(kr))


def test_uid_hanh_dong_404(may, kr):
    _them_nhom(kr, so_tt=1)
    assert _post(may, f"/radar/goc/{G1}/uid/{uid_n(40)}/ghim") == (404, {"loi": "Không có UID này trong Radar"})
    assert _post(may, f"/radar/goc/{G2}/uid/{uid_n(1)}/ghim")[0] == 404


@pytest.mark.parametrize("act", ["ghim", "bo-ghim", "loai", "bo-loai"])
def test_uid_goc_khong_doi_duoc_409(may, kr, act):
    _them_nhom(kr, so_tt=1)
    assert _post(may, f"/radar/goc/{G1}/uid/{G1}/{act}") == (409, {"loi": "Không đổi được UID gốc"})


def test_bo_loai_du_10_tuong_tu_409(may, kr):
    _them_nhom(kr, so_tt=10)
    kr.dat_uid(G1, uid_n(1), "loai", "nhan")
    kr.ghi_tuong_tu(G1, [{"uid": uid_n(100 + i), "ten": "n", "gia": None, "ban_7d": None} for i in range(10)],
                    "2026-11-23T09:30:00+07:00")
    assert _post(may, f"/radar/goc/{G1}/uid/{uid_n(1)}/bo-loai") == (409, {"loi": "Đã đủ 10 UID tương tự"})


@pytest.mark.parametrize("duong", ["/radar/goc/123/ngung", f"/radar/goc/{G1}/xoa", f"/radar/goc/{G1}/uid/{G2}/xoa",
                                   f"/radar/goc/{G1}/uid/12/ghim", "/radar/x", "/radar/bang/x"])
def test_duong_la_404(may, duong):
    assert may.goi("POST", duong, {"boi": "nhan"})[0] == 404


def test_get_tren_route_post_va_nguoc_lai_404(may):
    assert may.goi("GET", "/radar/goc")[0] == 404 and may.goi("GET", "/radar/chup-lai")[0] == 404
    assert may.goi("POST", "/radar/bang", {"boi": "nhan"})[0] == 404
    assert may.goi("PUT", "/radar/goc", {"boi": "nhan"})[0] == 405


# ================================================================ chup-lai

def test_chup_lai_202(may, kr):
    s, d = _post(may, "/radar/chup-lai")
    assert s == 202 and set(d) == {"viec_id"}
    v = may.kho.lay(d["viec_id"])
    assert (v["loai"], v["khoa"], v["tham_so"], v["tao_boi"], v["trang_thai"], v["lan_chay"]) == (
        "radar_uid_hang_ngay", NGAY, {"ngay": NGAY}, "nhan", "cho", "nhe")


def test_chup_lai_dang_co_luot_chay_409(may):
    assert _post(may, "/radar/chup-lai")[0] == 202
    assert _post(may, "/radar/chup-lai") == (409, {"loi": "Đang có lượt chụp chạy"})
    assert len(_viec_radar(may)) == 1


def test_chup_lai_sau_khi_xong_tao_duoc_luot_moi(may):
    id1 = _post(may, "/radar/chup-lai")[1]["viec_id"]
    may.kho.chuyen(id1, ["cho"], "huy", "nhan")
    assert _post(may, "/radar/chup-lai")[0] == 202


def test_chup_lai_luot_hen_gio_dang_mo_cung_409(may):
    may.kho.tao("radar_uid_hang_ngay", NGAY, {"ngay": NGAY}, "nhe", "cho", "he_thong")
    assert _post(may, "/radar/chup-lai") == (409, {"loi": "Đang có lượt chụp chạy"})


def test_chup_lai_vuot_6_viec_429(may):
    for i in range(6):
        v = _post(may, "/radar/chup-lai")
        assert v[0] == 202, (i, v)
        may.kho.chuyen(v[1]["viec_id"], ["cho"], "huy", "nhan")
    s, d = _post(may, "/radar/chup-lai")
    assert s == 429 and "radar_uid_chay_ngay" in d["loi"]


def test_chup_lai_han_muc_ha_thap(tmp_path, mt, dong, kr):
    m = _may(tmp_path, mt, dong, kr, radar_uid_chay_ngay=1)
    try:
        v = _post(m, "/radar/chup-lai")
        m.kho.chuyen(v[1]["viec_id"], ["cho"], "huy", "nhan")
        assert _post(m, "/radar/chup-lai")[0] == 429
    finally:
        m.dong_lai()


def test_chup_lai_cau_dao_tat_409(tmp_path, mt, dong, kr):
    m = _may(tmp_path, mt, dong, kr, radar_uid_bat=0)
    try:
        assert _post(m, "/radar/chup-lai") == (409, {"loi": "Radar UID đang tắt"})
        assert _viec_radar(m) == []
    finally:
        m.dong_lai()


def test_chup_lai_ngay_theo_gio_vn(tmp_path, mt, kr):
    from datetime import timezone
    dong_utc = Dong(datetime(2026, 11, 22, 20, 30, tzinfo=timezone.utc))      # = 2026-11-23 03:30 giờ VN
    m = May(tmp_path, mt, dong_utc, kho_radar=kr)
    try:
        s, d = _post(m, "/radar/chup-lai")
        assert s == 202 and m.kho.lay(d["viec_id"])["khoa"] == NGAY
    finally:
        m.dong_lai()


# ================================================================ web KHÔNG tạo / chạy lại việc radar qua /viec

@pytest.mark.parametrize("loai,ts", [("radar_uid_hang_ngay", {"ngay": NGAY}), ("radar_uid_nap", {"goc": G1}), ("radar_uid_nap", {})])
def test_post_viec_loai_radar_400(may, loai, ts):
    s, d = may.goi("POST", "/viec", {"loai": loai, "tham_so": ts, "boi": "nhan"})
    assert (s, d) == (400, {"loi": "loại này chỉ runner tự tạo"})
    assert may.kho.ds() == []


@pytest.mark.parametrize("loai,ts", [("radar_uid_hang_ngay", {"ngay": NGAY}), ("radar_uid_nap", {"goc": G1})])
def test_chay_lai_viec_radar_400_va_khong_co_the_chay_lai(may, loai, ts):
    v = may.kho.tao(loai, ts.get("goc") or ts["ngay"], ts, "nhe", "cho", "he_thong")
    may.kho.chuyen(v["id"], ["cho"], "huy", "nhan")
    assert may.goi("GET", f"/viec/{v['id']}")[1]["viec"]["co_the_chay_lai"] is False
    assert may.goi("POST", f"/viec/{v['id']}/chay-lai", {"boi": "nhan"}) == (400, {"loi": "loại này chỉ runner tự tạo"})


def test_danh_muc_web_khong_liet_ke_viec_radar(may):
    ma = {x["ma"] for x in may.goi("GET", "/danh-muc")[1]["loai"]}
    assert not (ma & {"radar_uid_hang_ngay", "radar_uid_nap"})


# ================================================================ khoá TypedDict §7.2 giữa 3 module

def _khoa_doc_7_2() -> dict[str, dict[str, str]]:
    """Đọc khối ```python của mục 7.2 trong docs/radar-uid.md → {tên lớp: {khoá: chú thích chuẩn hoá}}."""
    doc = (TOOLS.parent / "docs" / "radar-uid.md").read_text(encoding="utf-8")
    m = re.search(r"### 7\.2 .*?```python\n(.*?)```", doc, re.S)
    assert m, "không thấy khối code §7.2 trong docs/radar-uid.md"
    cay = ast.parse(m.group(1))
    ra: dict[str, dict[str, str]] = {}
    for nut in cay.body:
        if isinstance(nut, ast.ClassDef):
            ra[nut.name] = {x.target.id: ast.unparse(x.annotation) for x in nut.body
                            if isinstance(x, ast.AnnAssign) and isinstance(x.target, ast.Name)}
    return ra


def _khoa_module(mod, ten: str) -> dict[str, str]:
    lop = getattr(mod, ten)
    assert isinstance(lop, type) and hasattr(lop, "__required_keys__"), f"{mod.__name__}.{ten} không phải TypedDict"
    def chu(v: object) -> str:                       # TypedDict bọc chú thích chuỗi thành ForwardRef
        return v if isinstance(v, str) else getattr(v, "__forward_arg__", None) or getattr(v, "__name__", str(v))
    ann = {k: ast.unparse(ast.parse(chu(v), mode="eval")) for k, v in lop.__annotations__.items()}
    assert lop.__optional_keys__ == frozenset(), f"{mod.__name__}.{ten} có khoá tuỳ chọn"
    return ann


MODULE_THEO_LOP = {"HangVideo": (rut, krm, et), "Snapshot": (rut, krm), "MetaTrang": (rut, et),
                   "UngVien": (rut, krm, et), "KetQuaTimKiem": (rut,)}


@pytest.mark.parametrize("ten", sorted(MODULE_THEO_LOP))
def test_typeddict_7_2_khop_tai_lieu_va_giua_cac_module(ten):
    mong = _khoa_doc_7_2()[ten]
    for mod in MODULE_THEO_LOP[ten]:
        ann = _khoa_module(mod, ten)
        assert list(ann) == list(mong), (mod.__name__, ten, list(ann), list(mong))        # cùng khoá, cùng thứ tự
        assert ann == mong, (mod.__name__, ten)                                           # cùng kiểu từng khoá


def test_typeddict_7_2_du_5_lop_va_khong_lop_nao_thieu_o_module():
    assert set(_khoa_doc_7_2()) == set(MODULE_THEO_LOP)
    for ten, mods in MODULE_THEO_LOP.items():
        for mod in mods:
            assert hasattr(mod, ten), (mod.__name__, ten)


def test_typeddict_snapshot_cua_kho_dung_duoc_trong_xep_hang(kr):
    """Hợp đồng thực: Snapshot do kho.doc_snapshots trả có đúng bộ khoá mà radar_uid_tinh khai (không lệch tên/kiểu)."""
    _them_nhom(kr)
    _chup(kr, G1, NGAY, 1000)
    snap = kr.doc_snapshots(G1, "2000-01-01")[0]
    assert set(snap) == set(rut.Snapshot.__annotations__)
    assert set(next(iter(snap["videos"].values()))) == set(rut.HangVideo.__annotations__)


def _chup_them(kr, uid, ngay, them, ban_tong="10", n_video=10):
    luc = f"{ngay}T10:00:00+07:00"
    assert kr.bat_dau_chup(uid, ngay, luc)
    kr.ghi_chup_ok({"uid": uid, "ngay": ngay, "lay_luc": luc, "echotik_cap_nhat": f"{ngay} 07:55", "ban_tong": ban_tong,
                    "gia": "499.390₫", "hoa_hong": "10%", "ton": "562", "tong_creator": None, "so_trang": 1,
                    "tong_trang": 1, "them": them,
                    "videos": {v["video_id"]: v for v in (_video(i, 1000 + i * 100) for i in range(n_video))}})


def test_bang_co_chi_so_va_xu_huong_theo_ngay(may, kr):
    _them_nhom(kr, so_tt=1)
    _chup_them(kr, G1, "2026-11-22", {"sale_30d_cnt": "2.80K", "ifl_30d_cnt": 10, "total_ifl_cnt": 27,
                                       "video_30d_cnt": 45, "total_video_cnt": 100}, ban_tong="10.5K")
    _chup_them(kr, G1, "2026-11-23", {"sale_30d_cnt": "2.86K", "ifl_30d_cnt": 12, "total_ifl_cnt": 29,
                                       "video_30d_cnt": 49, "total_video_cnt": 105, "gmv_30d_amt": "$15.21K",
                                       "rating": 4.5, "review_count": 539, "hang_nganh": 258,
                                       "original_price": "155.579₫"}, ban_tong="10.62K")
    _chup(kr, uid_n(1), "2026-11-23", 1000)                           # UID chưa có `them`
    s, d = may.goi("GET", "/radar/bang")
    assert s == 200
    ds = {u["uid"]: u for u in d["nhom"][0]["ds"]}
    cs = ds[G1]["chi_so"]
    assert cs == {"ngay": "2026-11-23", "ban_30d": 2860, "gmv": None, "gmv_30d": "$15.21K", "creator_tong": 29,
                  "creator_30d": 12, "video_tong": 105, "video_30d": 49, "live_30d": None, "luot_danh_gia": 539,
                  "hang_nganh": 258, "gia_goc": "155.579₫", "danh_gia": 4.5}
    xh = ds[G1]["xu_huong"]
    assert [r["ngay"] for r in xh] == ["2026-11-22", "2026-11-23"]
    assert (xh[0]["ban_tong"], xh[0]["ban_30d"], xh[0]["creator_30d"]) == (10500, 2800, 10)
    assert (xh[1]["ban_tong"], xh[1]["ban_30d"], xh[1]["video_30d"], xh[1]["creator_tong"]) == (10620, 2860, 49, 29)
    assert ds[uid_n(1)]["chi_so"] is None                             # chưa có số thật: None, không 0
    assert ds[uid_n(1)]["xu_huong"][0]["ban_30d"] is None and ds[uid_n(1)]["xu_huong"][0]["ban_tong"] == 10
