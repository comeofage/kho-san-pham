"""Test script chạy việc `runner.radar_uid` (RU-A2, docs/radar-uid.md §6.2-§6.6).

Chạy: python -B -m pytest tools/test_runner_radar_uid_script.py -q -p no:cacheprovider
EchoTik GIẢ (echotik_factory tiêm vào), DB và file token giả chỉ nằm trong tmp_path. Không gọi mạng, không mở
E:\\timsanpham\\.echotik_token.json thật.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from runner import radar_uid, radar_uid_tinh as tinh
from runner.echotik import HetNganSach, LoiEchoTik
from runner.kho_radar_uid import KhoRadarUid
from runner.kieu import MUI_GIO_VN

NGAY = "2026-12-01"
SECRET = "TOKEN-BI-MAT-ABC123"
TEN_GOC = "[HOT] Kẹp tóc càng cua mini 8cm freeship"
KW4, KW3, KW2 = "kẹp tóc càng cua", "kẹp tóc càng", "kẹp tóc"
TEN_TT = "Kẹp tóc càng cua to 12cm"


def uid(i: int) -> str:
    """UID 19 số (> 2^53) để bắt lỗi lỡ đi qua số."""
    return f"17297066286569{i:05d}"


class Dong:
    def __init__(self, luc: datetime):
        self.luc = luc

    def __call__(self) -> datetime:
        return self.luc

    def tang(self, giay: float) -> None:
        self.luc += timedelta(seconds=giay)


def sql(db: Path, cau: str, tham: tuple = ()) -> list[sqlite3.Row]:
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    try:
        return c.execute(cau, tham).fetchall()
    finally:
        c.close()


def video_tho(u: str, n: int = 10) -> list[dict]:
    """n video; video_id tăng thì ngày đăng giảm (khớp thứ tự đọc ORDER BY video_id, không bật MAU_TOP_VIDEO oan)."""
    ra = []
    for i in range(n):
        ra.append({"video_id": f"7300{u[-6:]}{i:09d}", "views_count": 326 if i % 2 else "21.81K",
                   "publish_time": f"2026-07-{28 - i:02d} 10:00:00", "update_time": "gio-goi-luon-doi",
                   "influencer": {"unique_id": f"c{i % 4}", "follower_count": "2.54K"}, "is_promote": False})
    return ra


def ung_vien_tho(u: str, ten: str = TEN_TT, gia: str = "$12.7", ban: str = "36") -> dict:
    return {"product_id": u, "product_name": ten, "avg_price": gia, "total_sale_7d_cnt": ban}


def url_anh(u: str, ban: str = "") -> str:
    return f"https://cdn.echotik.live/md5{ban}/hex/product-cover/138/{u}_0.webp"


def them_cover(mt, anh) -> None:
    """Gắn cover_url (E4) cho mọi ứng viên đã cài: `anh` là hàm uid → URL."""
    for kw in (KW4, KW3, KW2):
        mt.kb.tim[(kw, 1)] = [{**x, "cover_url": anh(x["product_id"])} for x in mt.kb.tim[(kw, 1)]]


class KichBan:
    """Dữ liệu + lỗi cài sẵn cho EchoTik giả; ghi lại mọi GET."""

    def __init__(self, db: Path, dong: Dong):
        self.db, self.dong = db, dong
        self.sp: dict[str, dict] = {}
        self.video: dict[str, list[dict]] = {}
        self.last_page: dict[str, int] = {}
        self.tim: dict[tuple[str, int], list[dict]] = {}
        self.tim_last: dict[str, int] = {}
        self.loi: dict[tuple[str, str | None], Exception] = {}
        self.goi_phu: dict[str, int] = {}          # mô phỏng thử lại: ham → số lần tính ngân sách thêm
        self.goi: list[tuple[str, str]] = []
        self.trang_thai_luc_goi: list[tuple[str, str, str | None]] = []
        self.hook = None
        self.so_factory = 0

    def them_sp(self, u: str, ten: str = TEN_TT, n_video: int = 10, **kw) -> None:
        d = {"product_id": u, "product_name": ten, "price": "$19.37", "real_price": "499.390₫", "sale_cnt": "10.17K",
             "commission": "10%", "total_stock_cnt": 562, "update_time": "2026-11-22 07:55",
             "seller": {"seller_name": "Shop A"}}
        d.update(kw)
        self.sp[u] = d
        self.video[u] = video_tho(u, n_video)

    def ghi_trang_thai(self, ham: str, khoa: str) -> None:
        tt = None
        if ham in ("chi_tiet", "video") and self.db.is_file():
            r = sql(self.db, "SELECT trang_thai FROM chup_uid WHERE uid=? AND ngay=?", (khoa, NGAY))
            tt = r[0]["trang_thai"] if r else None
        self.trang_thai_luc_goi.append((ham, khoa, tt))

    def so_lan(self, ham: str) -> list[str]:
        return [k for h, k in self.goi if h == ham]


class GiaEchoTik:
    def __init__(self, kb: KichBan, token_file, tinh_goi=None, **_):
        self.kb, self.token_file, self._tinh = kb, token_file, tinh_goi

    def _goi(self, ham: str, khoa: str) -> None:
        if self._tinh is not None:
            for _ in range(1 + self.kb.goi_phu.get(ham, 0)):
                if not self._tinh(1):
                    raise HetNganSach("het ngan sach")
        self.kb.goi.append((ham, khoa))
        self.kb.ghi_trang_thai(ham, khoa)
        loi = self.kb.loi.get((ham, khoa)) or self.kb.loi.get((ham, None))
        if loi is not None:
            raise loi
        if self.kb.hook is not None:
            self.kb.hook(ham, khoa)

    def chi_tiet(self, u: str) -> dict:
        self._goi("chi_tiet", u)
        if u not in self.kb.sp:
            raise LoiEchoTik("khong_tim_thay", 404)
        return self.kb.sp[u]

    def video(self, u: str, trang: int = 1, moi_trang: int = 50):
        self._goi("video", u)
        return list(self.kb.video.get(u, [])), {"current_page": trang, "last_page": self.kb.last_page.get(u, 1)}

    def tim(self, tu_khoa: str, trang: int = 1, moi_trang: int = 50):
        self._goi("tim", tu_khoa)
        return (list(self.kb.tim.get((tu_khoa, trang), [])),
                {"current_page": trang, "last_page": self.kb.tim_last.get(tu_khoa, 1)})


@pytest.fixture
def mt(tmp_path):
    tok = tmp_path / "tok.json"
    tok.write_text(json.dumps({"token": SECRET, "user_id": "u1"}), encoding="utf-8")
    db = tmp_path / "radar_uid.db"
    dong = Dong(datetime(2026, 12, 1, 12, 0, 0, tzinfo=MUI_GIO_VN))
    kb = KichBan(db, dong)

    def factory(token_file, **kw):
        kb.so_factory += 1
        return GiaEchoTik(kb, token_file, **kw)

    return SimpleNamespace(db=db, tok=tok, dong=dong, kb=kb, factory=factory)


def mo_kho(mt) -> KhoRadarUid:
    k = KhoRadarUid(mt.db, mt.dong)
    k.mo()
    return k


def seed_nhom(mt, goc: str, tuong_tu: list[str], trang_thai: str = "da_tim") -> None:
    k = mo_kho(mt)
    try:
        k.them_goc(goc, "test")
        k.ghi_san_pham(goc, TEN_GOC, "Shop A")
        k.ghi_tuong_tu(goc, [{"uid": u, "ten": TEN_TT} for u in tuong_tu], "2026-12-01T09:00:00+07:00")
        k.dat_trang_thai_nhom(goc, trang_thai)
    finally:
        k.dong()
    for u in [goc, *tuong_tu]:
        mt.kb.them_sp(u)


def chay_script(mt, capsys, che_do: str = "hang-ngay", viec_id: str = "v1", *, goc: str | None = None,
                ngay: str = NGAY, tran: int = 60, factory="mac_dinh"):
    argv = ["--che-do", che_do, "--ngay", ngay, "--db", str(mt.db), "--token-file", str(mt.tok),
            "--viec-id", viec_id, "--tran-goi", str(tran)]
    if goc:
        argv += ["--goc", goc]
    kw = {"bay_gio": mt.dong}
    if factory == "mac_dinh":
        kw["echotik_factory"] = mt.factory
    elif factory is not None:
        kw["echotik_factory"] = factory
    ma = radar_uid.chay(argv, **kw)
    out = capsys.readouterr()
    dong = [d for d in out.out.splitlines() if d.strip()]
    assert len(dong) == 1, out.out
    return ma, json.loads(dong[0]), out


# ---------------------------------------------------------------------------------------------------------------
# hang-ngay
# ---------------------------------------------------------------------------------------------------------------
def test_stdout_dung_mot_dong_json_ascii_bon_khoa(mt, capsys):
    seed_nhom(mt, uid(1), [uid(2)])
    ma, j, out = chay_script(mt, capsys)
    assert ma == 0
    assert set(j) == {"trang_thai", "ly_do", "so_uid", "so_goi"}
    assert out.out.strip().isascii()
    assert j == {"trang_thai": "xong", "ly_do": "", "so_uid": 2, "so_goi": 4}


def test_ghi_dang_chup_truoc_moi_lan_goi_mang(mt, capsys):
    seed_nhom(mt, uid(1), [uid(2), uid(3)])
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 0 and j["so_uid"] == 3
    goi_uid = [x for x in mt.kb.trang_thai_luc_goi if x[0] in ("chi_tiet", "video")]
    assert len(goi_uid) == 6
    assert all(tt == "dang_chup" for _, _, tt in goi_uid)
    # mỗi UID: E1 rồi E2
    for u in (uid(1), uid(2), uid(3)):
        assert [h for h, k in mt.kb.goi if k == u] == ["chi_tiet", "video"]
    rows = sql(mt.db, "SELECT uid, trang_thai, so_lan_thu, so_trang, tong_trang, gia, ban_tong, hoa_hong, ton, "
                      "echotik_cap_nhat FROM chup_uid ORDER BY uid")
    assert [r["trang_thai"] for r in rows] == ["ok"] * 3
    assert all(r["so_lan_thu"] == 1 and r["so_trang"] == 1 and r["tong_trang"] == 1 for r in rows)
    assert rows[0]["gia"] == "499.390₫" and rows[0]["ban_tong"] == "10.17K" and rows[0]["ton"] == "562"
    assert rows[0]["echotik_cap_nhat"] == "2026-11-22 07:55"
    assert sql(mt.db, "SELECT COUNT(*) AS n FROM chup_video")[0]["n"] == 30
    # view 326 (số) và '21.81K' (chuỗi) đều thành chuỗi; update_time video KHÔNG được lưu
    views = {r["view"] for r in sql(mt.db, "SELECT view FROM chup_video")}
    assert views == {"326", "21.81K"}
    assert SECRET not in "".join(str(tuple(r)) for r in sql(mt.db, "SELECT * FROM chup_video"))
    assert sql(mt.db, "SELECT ten, shop FROM san_pham WHERE uid=?", (uid(1),))[0]["shop"] == "Shop A"
    assert KhoRadarUid(mt.db, mt.dong, chi_doc=True).doc_token()["trang_thai"] == "ok"


def test_ngan_sach_hai_lan_so_uid(mt, capsys):
    seed_nhom(mt, uid(1), [uid(2), uid(3), uid(4)])
    _, j, _ = chay_script(mt, capsys)
    assert j["so_goi"] == 8 and len(mt.kb.goi) == 8
    k = KhoRadarUid(mt.db, mt.dong, chi_doc=True)
    assert k.goi_hom_nay(NGAY) == 8
    assert k.lan_cua_viec(NGAY, "hang-ngay", "v1")["so_goi"] == 8


def test_chay_hai_lan_cung_ngay_idempotent(mt, capsys):
    seed_nhom(mt, uid(1), [uid(2), uid(3)])
    _, j1, _ = chay_script(mt, capsys, viec_id="v1")
    assert j1["so_goi"] == 6
    ma, j2, _ = chay_script(mt, capsys, viec_id="v2")                 # việc mới cùng ngày
    assert ma == 0 and j2 == {"trang_thai": "xong", "ly_do": "", "so_uid": 0, "so_goi": 0}
    ma, j3, _ = chay_script(mt, capsys, viec_id="v1")                 # cùng việc: đã xong, không làm lại
    assert ma == 0 and j3["trang_thai"] == "xong"
    assert len(mt.kb.goi) == 6
    assert [r["so_lan_thu"] for r in sql(mt.db, "SELECT so_lan_thu FROM chup_uid")] == [1, 1, 1]
    assert sql(mt.db, "SELECT COUNT(*) AS n FROM chup_video")[0]["n"] == 30


def test_thu_tu_chup_xoay_khong_doi_uid_cuoi(mt, capsys):
    seed_nhom(mt, uid(1), [uid(2), uid(3)])
    mt.kb.hook = lambda ham, khoa: mt.dong.tang(60)
    chup_theo_ngay = []
    for i in range(4):
        ngay = f"2026-12-{1 + i:02d}"
        mt.dong.luc = datetime(2026, 12, 1 + i, 12, 0, 0, tzinfo=MUI_GIO_VN)
        truoc = len(mt.kb.goi)
        _, j, _ = chay_script(mt, capsys, viec_id=f"v{i}", ngay=ngay, tran=2)     # chỉ đủ 1 UID mỗi ngày
        assert j["trang_thai"] == "tu_dung" and j["ly_do"] == "het_han_muc_goi" and j["so_uid"] == 1
        chup_theo_ngay.append([k for h, k in mt.kb.goi[truoc:] if h == "chi_tiet"][0])
    # a (chưa từng chụp) → b → c → a (cũ nhất): UID cuối không đói
    assert chup_theo_ngay == [uid(1), uid(2), uid(3), uid(1)]


def test_khong_bat_dau_uid_neu_khong_du_hai_get(mt, capsys):
    seed_nhom(mt, uid(1), [uid(2), uid(3)])
    ma, j, _ = chay_script(mt, capsys, tran=5)
    assert ma == 0 and j == {"trang_thai": "tu_dung", "ly_do": "het_han_muc_goi", "so_uid": 2, "so_goi": 4}
    da = {r["uid"] for r in sql(mt.db, "SELECT uid FROM chup_uid")}
    assert da == {uid(1), uid(2)}                                     # UID thứ ba không dở dang `dang_chup`
    assert KhoRadarUid(mt.db, mt.dong, chi_doc=True).lan_cua_viec(NGAY, "hang-ngay", "v1")["trang_thai"] == "tu_dung"


def test_het_ngan_sach_giua_uid_thanh_loi_va_tu_dung(mt, capsys):
    seed_nhom(mt, uid(1), [])
    mt.kb.goi_phu = {"chi_tiet": 1}                                   # E1 tốn thêm 1 (thử lại) → E2 vượt trần 2
    ma, j, _ = chay_script(mt, capsys, tran=2)
    assert ma == 0 and j["trang_thai"] == "tu_dung" and j["ly_do"] == "het_han_muc_goi" and j["so_goi"] == 2
    r = sql(mt.db, "SELECT trang_thai, ma_loi FROM chup_uid")[0]
    assert (r["trang_thai"], r["ma_loi"]) == ("loi", "het_han_muc_goi")


@pytest.mark.parametrize("ma_loi,http,token_tt", [("token_het_han", 401, "het_han"), ("rate_limit", 429, "chua_kiem")])
def test_dung_ngay_khi_token_het_han_hoac_rate_limit(mt, capsys, ma_loi, http, token_tt):
    seed_nhom(mt, uid(1), [uid(2), uid(3)])
    mt.kb.loi[("chi_tiet", None)] = LoiEchoTik(ma_loi, http)
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 0 and j == {"trang_thai": "tu_dung", "ly_do": ma_loi, "so_uid": 0, "so_goi": 1}
    assert len(mt.kb.goi) == 1                                        # dừng ngay, không thử lại
    k = KhoRadarUid(mt.db, mt.dong, chi_doc=True)
    assert k.doc_token()["trang_thai"] == token_tt
    if token_tt == "het_han":
        assert k.doc_token()["ma"] == "token_het_han"
    rows = sql(mt.db, "SELECT uid, trang_thai, ma_loi FROM chup_uid")
    assert [(r["trang_thai"], r["ma_loi"]) for r in rows] == [("loi", ma_loi)]
    assert k.lan_cua_viec(NGAY, "hang-ngay", "v1")["ly_do"] == ma_loi


def test_thieu_file_token_tu_dung_khong_goi_mang_khong_tao_echotik(mt, capsys):
    seed_nhom(mt, uid(1), [uid(2)])
    mt.tok.unlink()
    ma, j, _ = chay_script(mt, capsys, factory=None)                  # factory mặc định = EchoTik thật: không được dùng
    assert ma == 0 and j == {"trang_thai": "tu_dung", "ly_do": "token_thieu", "so_uid": 0, "so_goi": 0}
    assert KhoRadarUid(mt.db, mt.dong, chi_doc=True).doc_token()["trang_thai"] == "thieu"
    ma, j, _ = chay_script(mt, capsys, viec_id="v2")
    assert mt.kb.so_factory == 0


def test_mang_lien_tiep_nam_lan_thi_dung(mt, capsys):
    seed_nhom(mt, uid(1), [uid(i) for i in range(2, 8)])             # 7 UID
    mt.kb.loi[("chi_tiet", None)] = LoiEchoTik("mang", 503)
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 0 and j["trang_thai"] == "tu_dung" and j["ly_do"] == "mang_lien_tiep"
    assert len(mt.kb.goi) == 5 and j["so_goi"] == 5
    rows = sql(mt.db, "SELECT trang_thai, ma_loi FROM chup_uid")
    assert len(rows) == 5 and {(r["trang_thai"], r["ma_loi"]) for r in rows} == {("loi", "mang")}


def test_mang_khong_dung_neu_xen_ke_co_uid_thanh_cong(mt, capsys):
    us = [uid(i) for i in range(1, 10)]
    seed_nhom(mt, us[0], us[1:])
    for u in us[:4] + us[5:]:
        mt.kb.loi[("chi_tiet", u)] = LoiEchoTik("mang")
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 0 and j["trang_thai"] == "xong" and j["so_uid"] == 1


def test_dinh_dang_ba_uid_lien_tiep_thi_dung(mt, capsys):
    seed_nhom(mt, uid(1), [uid(2), uid(3), uid(4), uid(5)])
    mt.kb.loi[("chi_tiet", None)] = LoiEchoTik("dinh_dang", 200)
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 0 and j["trang_thai"] == "tu_dung" and j["ly_do"] == "dinh_dang" and len(mt.kb.goi) == 3
    assert {r["ma_loi"] for r in sql(mt.db, "SELECT ma_loi FROM chup_uid")} == {"dinh_dang"}


def test_dinh_dang_hai_lan_roi_thanh_cong_thi_tiep_tuc(mt, capsys):
    us = [uid(i) for i in range(1, 6)]
    seed_nhom(mt, us[0], us[1:])
    for u in (us[0], us[1], us[3], us[4]):
        mt.kb.loi[("chi_tiet", u)] = LoiEchoTik("dinh_dang", 200)
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 0 and j["trang_thai"] == "xong" and j["so_uid"] == 1


def test_khong_tim_thay_va_khong_co_video_chi_loi_uid_viec_van_tiep_tuc(mt, capsys):
    us = [uid(1), uid(2), uid(3)]
    seed_nhom(mt, us[0], us[1:])
    del mt.kb.sp[us[0]]                                               # E1 404 → khong_tim_thay
    mt.kb.video[us[1]] = []                                           # E2 0 video
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 0 and j == {"trang_thai": "xong", "ly_do": "", "so_uid": 1, "so_goi": 5}
    rows = {r["uid"]: (r["trang_thai"], r["ma_loi"]) for r in sql(mt.db, "SELECT uid, trang_thai, ma_loi FROM chup_uid")}
    assert rows == {us[0]: ("loi", "khong_tim_thay"), us[1]: ("loi", "khong_co_video"), us[2]: ("ok", "")}
    assert sql(mt.db, "SELECT COUNT(*) AS n FROM chup_video WHERE uid=?", (us[1],))[0]["n"] == 0


def _lan_hang_ngay(mt) -> dict:
    return KhoRadarUid(mt.db, mt.dong, chi_doc=True).lan_cua_viec(NGAY, "hang-ngay", "v1")


def test_hang_ngay_moi_uid_khong_tim_thay_thi_loi_khong_chup_duoc(mt, capsys):
    us = [uid(1), uid(2), uid(3)]
    seed_nhom(mt, us[0], us[1:])
    for u in us:
        del mt.kb.sp[u]                                               # E1 404 cả ba
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 1 and j == {"trang_thai": "loi", "ly_do": "khong_chup_duoc", "so_uid": 0, "so_goi": 3}
    lan = _lan_hang_ngay(mt)
    assert (lan["trang_thai"], lan["ly_do"]) == ("loi", "khong_chup_duoc")


def test_hang_ngay_moi_uid_khong_co_video_thi_loi_khong_chup_duoc(mt, capsys):
    us = [uid(1), uid(2)]
    seed_nhom(mt, us[0], us[1:])
    for u in us:
        mt.kb.video[u] = []
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 1 and j["trang_thai"] == "loi" and j["ly_do"] == "khong_chup_duoc" and j["so_uid"] == 0


def test_hang_ngay_it_hon_nam_loi_mang_khong_uid_nao_ok_thi_loi(mt, capsys):
    us = [uid(1), uid(2), uid(3)]
    seed_nhom(mt, us[0], us[1:])
    mt.kb.loi[("chi_tiet", None)] = LoiEchoTik("mang", 503)           # 3 < 5 lần liên tiếp: không tự dừng
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 1 and j["trang_thai"] == "loi" and j["ly_do"] == "khong_chup_duoc" and j["so_uid"] == 0
    assert _lan_hang_ngay(mt)["trang_thai"] == "loi"


def test_hang_ngay_co_it_nhat_mot_uid_ok_thi_van_xong(mt, capsys):
    us = [uid(1), uid(2), uid(3)]
    seed_nhom(mt, us[0], us[1:])
    del mt.kb.sp[us[0]]
    del mt.kb.sp[us[1]]
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 0 and j["trang_thai"] == "xong" and j["so_uid"] == 1


def test_hang_ngay_khong_co_uid_nao_de_thu_van_xong(mt, capsys):
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 0 and j == {"trang_thai": "xong", "ly_do": "", "so_uid": 0, "so_goi": 0}


def test_last_page_hai_bat_co_mau_top_video(mt, capsys):
    seed_nhom(mt, uid(1), [])
    mt.kb.last_page[uid(1)] = 2
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 0 and j["so_goi"] == 2 and len(mt.kb.so_lan("video")) == 1     # TRANG_VIDEO_TOI_DA = 1
    snaps = KhoRadarUid(mt.db, mt.dong, chi_doc=True).doc_snapshots(uid(1), "2026-11-01")
    assert snaps[0]["so_trang"] == 1 and snaps[0]["tong_trang"] == 2
    r = tinh.xep_hang_uid(snaps, mt.dong(), NGAY)
    assert "MAU_TOP_VIDEO" in r["co_canh_bao"]


def test_last_page_mot_khong_bat_co(mt, capsys):
    seed_nhom(mt, uid(1), [])
    chay_script(mt, capsys)
    snaps = KhoRadarUid(mt.db, mt.dong, chi_doc=True).doc_snapshots(uid(1), "2026-11-01")
    assert "MAU_TOP_VIDEO" not in tinh.xep_hang_uid(snaps, mt.dong(), NGAY)["co_canh_bao"]


@pytest.mark.parametrize("tt_khac", ["cho_tim", "dang_tim", "ngung"])
def test_hang_ngay_bo_qua_nhom_cho_tim_dang_tim_ngung(mt, capsys, tt_khac):
    seed_nhom(mt, uid(1), [uid(2)], "da_tim")
    seed_nhom(mt, uid(10), [uid(11)], tt_khac)
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 0 and j["so_uid"] == 2
    assert sorted(mt.kb.so_lan("chi_tiet")) == [uid(1), uid(2)]


def test_hang_ngay_van_chup_nhom_loi_tim(mt, capsys):
    seed_nhom(mt, uid(1), [uid(2)], "da_tim")
    seed_nhom(mt, uid(10), [uid(11)], "loi_tim")                      # gốc + UID thêm tay vẫn có chuỗi snapshot
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 0 and j["so_uid"] == 4 and j["trang_thai"] == "xong"
    assert sorted(mt.kb.so_lan("chi_tiet")) == [uid(1), uid(2), uid(10), uid(11)]


def test_hang_ngay_khong_co_viec_thi_xong_khong_can_token(mt, capsys):
    mo_kho(mt).dong()
    mt.tok.unlink()
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 0 and j == {"trang_thai": "xong", "ly_do": "", "so_uid": 0, "so_goi": 0}


# ---------------------------------------------------------------------------------------------------------------
# nap
# ---------------------------------------------------------------------------------------------------------------
def cai_nap(mt, *, goc: str = uid(1)) -> dict[str, str]:
    """Nhóm cho_tim + dữ liệu E4: trả {tên: uid}."""
    k = mo_kho(mt)
    try:
        k.them_goc(goc, "test")
        k.them_tay(goc, uid(90), "test")
        k.dat_uid(goc, uid(90), "loai", "test")                       # UID đã loại: phải bị bỏ dù E4 trả về
    finally:
        k.dong()
    mt.kb.them_sp(goc, TEN_GOC)
    c = {f"c{i}": uid(i) for i in range(2, 6)}
    for u in c.values():
        mt.kb.them_sp(u)
    tt = TEN_TT
    mt.kb.tim[(KW4, 1)] = [ung_vien_tho(c["c2"], tt), ung_vien_tho(c["c3"], tt), ung_vien_tho(goc, TEN_GOC),
                           ung_vien_tho(uid(90), tt)]
    mt.kb.tim[(KW3, 1)] = [ung_vien_tho(c["c3"], tt), ung_vien_tho(c["c4"], tt),
                           ung_vien_tho(uid(91), tt, gia="$100")]          # gấp > 2 lần giá gốc $19.37 → bị lọc giá
    mt.kb.tim[(KW2, 1)] = [ung_vien_tho(c["c5"], tt), ung_vien_tho(uid(92), "Máy sấy tóc mini")]   # do_giong 0,29
    return c


def test_nap_luong_day_du_ngan_sach_va_loc(mt, capsys):
    c = cai_nap(mt)
    goc = uid(1)
    ma, j, _ = chay_script(mt, capsys, "nap", "n1", goc=goc)
    # 5 UID (gốc + 4 tương tự) = 2×5, + 3 GET E4 (một GET/từ khoá)
    assert ma == 0 and j == {"trang_thai": "xong", "ly_do": "", "so_uid": 5, "so_goi": 13}
    assert mt.kb.so_lan("tim") == [KW4, KW3, KW2]
    assert mt.kb.so_lan("chi_tiet").count(goc) == 1                   # E1 của gốc dùng lại, không gọi hai lần
    assert mt.kb.so_lan("video").count(goc) == 1
    k = KhoRadarUid(mt.db, mt.dong, chi_doc=True)
    assert k.goi_hom_nay(NGAY) == 13
    lk = {x["uid"]: x for x in k.uid_cua_nhom(goc)}
    tuong_tu = {u for u, x in lk.items() if x["vai"] == "tuong_tu"}
    assert tuong_tu == set(c.values())                                # union 3 từ khoá, khử trùng; không có UID 91/92
    assert lk[goc]["vai"] == "goc" and lk[uid(90)]["trang_thai"] == "loai"
    assert all(abs(lk[u]["do_giong"] - 0.6667) < 0.001 for u in tuong_tu)
    assert lk[goc]["ten"] == TEN_GOC
    nhom = next(n for n in k.ds_nhom() if n["goc"] == goc)
    assert nhom["trang_thai"] == "da_tim" and nhom["ly_do"] == "" and nhom["tim_luc"]
    assert {r["uid"] for r in sql(mt.db, "SELECT uid FROM chup_uid WHERE trang_thai='ok'")} == {goc, *c.values()}
    # dang_chup đã ghi TRƯỚC mọi GET E1/E2 (gồm cả E1 của gốc dùng cho việc tìm)
    assert all(tt == "dang_chup" for h, _, tt in mt.kb.trang_thai_luc_goi if h in ("chi_tiet", "video"))


def test_nap_hai_lan_cung_ngay_khong_chup_lai(mt, capsys):
    cai_nap(mt)
    chay_script(mt, capsys, "nap", "n1", goc=uid(1))
    n_video_truoc = len(mt.kb.so_lan("video"))
    ma, j, _ = chay_script(mt, capsys, "nap", "n2", goc=uid(1))
    assert ma == 0 and j["trang_thai"] == "xong" and j["so_uid"] == 0
    assert len(mt.kb.so_lan("video")) == n_video_truoc                # không chụp lại UID đã ok
    assert j["so_goi"] == 1 + 3                                       # E1 gốc để tìm lại + 3 E4


def test_nap_cong_keyword_tung_tu_khoa_bo_tu_khoa_khong_loc(mt, capsys):
    cai_nap(mt)
    ngoai = [ung_vien_tho(uid(60), "Ốp lưng điện thoại A"), ung_vien_tho(uid(61), "Ốp lưng điện thoại B"),
             ung_vien_tho(uid(62), TEN_TT)]                           # 1/3 chứa âm tiết từ khoá < 50% → cổng loại cả từ khoá
    mt.kb.tim[(KW4, 1)] = ngoai
    mt.kb.them_sp(uid(62))
    chay_script(mt, capsys, "nap", "n1", goc=uid(1))
    k = KhoRadarUid(mt.db, mt.dong, chi_doc=True)
    uids = {x["uid"] for x in k.uid_cua_nhom(uid(1))}
    assert uid(62) not in uids and uid(60) not in uids
    assert {uid(4), uid(5)} <= uids                                   # hai từ khoá còn lại vẫn dùng được


def test_nap_ca_ba_tu_khoa_khong_loc_thi_loi_tim_khong_chon_ai(mt, capsys):
    cai_nap(mt)
    ngoai = [ung_vien_tho(uid(60), "Ốp lưng điện thoại A"), ung_vien_tho(uid(61), "Ốp lưng điện thoại B"),
             ung_vien_tho(uid(62), TEN_TT)]
    for kw in (KW4, KW3, KW2):
        mt.kb.tim[(kw, 1)] = ngoai
    ma, j, _ = chay_script(mt, capsys, "nap", "n1", goc=uid(1))
    assert ma == 0 and j["trang_thai"] == "xong"
    k = KhoRadarUid(mt.db, mt.dong, chi_doc=True)
    nhom = k.ds_nhom()[0]
    assert (nhom["trang_thai"], nhom["ly_do"]) == ("loi_tim", "keyword_khong_loc")
    assert [x["uid"] for x in k.uid_cua_nhom(uid(1)) if x["vai"] == "tuong_tu"] == []
    assert j["so_uid"] == 1                                           # vẫn chụp được UID gốc


def test_nap_lay_trang_hai_khi_meta_last_page_lon_hon_mot(mt, capsys):
    cai_nap(mt)
    mt.kb.tim_last[KW4] = 2
    mt.kb.tim[(KW4, 2)] = [ung_vien_tho(uid(6))]
    mt.kb.them_sp(uid(6))
    ma, j, _ = chay_script(mt, capsys, "nap", "n1", goc=uid(1))
    assert mt.kb.so_lan("tim") == [KW4, KW4, KW3, KW2]
    assert uid(6) in {x["uid"] for x in KhoRadarUid(mt.db, mt.dong, chi_doc=True).uid_cua_nhom(uid(1))}
    assert j["so_uid"] == 6 and j["so_goi"] == 2 * 6 + 4              # 2×N + 4 GET E4 (E1 gốc dùng lại)


def test_nap_giu_ghim_them_tay_va_loai_khi_tim_lai(mt, capsys):
    cai_nap(mt)
    goc = uid(1)
    chay_script(mt, capsys, "nap", "n1", goc=goc)
    k = mo_kho(mt)
    try:
        k.dat_uid(goc, uid(2), "ghim", "test")
        k.them_tay(goc, uid(70), "test")
    finally:
        k.dong()
    mt.kb.them_sp(uid(70))
    chay_script(mt, capsys, "nap", "n2", goc=goc)
    lk = {x["uid"]: x for x in KhoRadarUid(mt.db, mt.dong, chi_doc=True).uid_cua_nhom(goc)}
    assert lk[uid(2)]["trang_thai"] == "ghim" and lk[uid(70)]["vai"] == "them_tay"
    assert lk[uid(90)]["trang_thai"] == "loai"
    assert len([u for u, x in lk.items() if x["vai"] == "tuong_tu" and x["trang_thai"] != "loai"]) <= 10


def test_nap_nhom_ngung_giua_chung_khong_bi_ghi_de(mt, capsys):
    cai_nap(mt)
    goc = uid(1)

    def hook(ham, khoa):
        if ham == "tim" and khoa == KW4:
            k = mo_kho(mt)
            try:
                k.dat_goc(goc, "ngung", "chu")
            finally:
                k.dong()

    mt.kb.hook = hook
    ma, j, _ = chay_script(mt, capsys, "nap", "n1", goc=goc)
    assert ma == 0 and j["trang_thai"] == "xong" and j["ly_do"] == "nhom_ngung" and j["so_uid"] == 0
    k = KhoRadarUid(mt.db, mt.dong, chi_doc=True)
    assert k.ds_nhom()[0]["trang_thai"] == "ngung"                    # KHÔNG bị ghi đè thành da_tim
    assert [x["vai"] for x in k.uid_cua_nhom(goc)].count("tuong_tu") == 0
    r = sql(mt.db, "SELECT trang_thai, ma_loi FROM chup_uid WHERE uid=?", (goc,))[0]
    assert (r["trang_thai"], r["ma_loi"]) == ("loi", "nhom_ngung")    # không để dở `dang_chup`
    assert len(mt.kb.so_lan("video")) == 0


@pytest.mark.parametrize("ma_loi,http", [("token_het_han", 200), ("rate_limit", 429)])
def test_nap_dung_o_buoc_tim_thi_nhom_loi_tim_va_lan_tu_dung(mt, capsys, ma_loi, http):
    cai_nap(mt)
    mt.kb.loi[("tim", None)] = LoiEchoTik(ma_loi, http)
    ma, j, _ = chay_script(mt, capsys, "nap", "n1", goc=uid(1))
    assert ma == 0 and j == {"trang_thai": "tu_dung", "ly_do": ma_loi, "so_uid": 0, "so_goi": 2}
    k = KhoRadarUid(mt.db, mt.dong, chi_doc=True)
    nhom = k.ds_nhom()[0]
    assert (nhom["trang_thai"], nhom["ly_do"]) == ("loi_tim", ma_loi)
    r = sql(mt.db, "SELECT trang_thai, ma_loi FROM chup_uid")
    assert [(x["trang_thai"], x["ma_loi"]) for x in r] == [("loi", ma_loi)]
    assert (k.doc_token()["trang_thai"] == "het_han") == (ma_loi == "token_het_han")


def test_nap_goc_khong_tim_thay_thi_nhom_loi_tim(mt, capsys):
    cai_nap(mt)
    del mt.kb.sp[uid(1)]
    ma, j, _ = chay_script(mt, capsys, "nap", "n1", goc=uid(1))
    assert ma == 0 and j["trang_thai"] == "xong"
    nhom = KhoRadarUid(mt.db, mt.dong, chi_doc=True).ds_nhom()[0]
    assert (nhom["trang_thai"], nhom["ly_do"]) == ("loi_tim", "khong_tim_thay")
    assert mt.kb.so_lan("tim") == []


def test_nap_nhom_khong_ton_tai_la_loi(mt, capsys):
    mo_kho(mt).dong()
    ma, j, _ = chay_script(mt, capsys, "nap", "n1", goc=uid(1))
    assert ma == 1 and j["trang_thai"] == "loi" and j["ly_do"] == "khong_co_nhom"
    assert mt.kb.goi == []


def test_nap_het_ngan_sach_khi_tim_thi_loi_tim_het_han_muc(mt, capsys):
    cai_nap(mt)
    ma, j, _ = chay_script(mt, capsys, "nap", "n1", goc=uid(1), tran=3)    # E1 gốc + E4 + E4 = 3, E4 thứ ba bị chặn
    assert ma == 0 and j["trang_thai"] == "tu_dung" and j["ly_do"] == "het_han_muc_goi" and j["so_goi"] == 3
    nhom = KhoRadarUid(mt.db, mt.dong, chi_doc=True).ds_nhom()[0]
    assert (nhom["trang_thai"], nhom["ly_do"]) == ("loi_tim", "het_han_muc_goi")


# ---------------------------------------------------------------------------------------------------------------
# lỗi bất ngờ, tham số, bí mật
# ---------------------------------------------------------------------------------------------------------------
def test_loi_bat_ngo_exit_1_lan_loi_khong_lo_thong_diep(mt, capsys, caplog):
    seed_nhom(mt, uid(1), [])
    mt.kb.loi[("chi_tiet", None)] = RuntimeError("boom " + SECRET)
    with caplog.at_level(logging.DEBUG):
        ma, j, out = chay_script(mt, capsys)
    assert ma == 1 and j == {"trang_thai": "loi", "ly_do": "loi_bat_ngo", "so_uid": 0, "so_goi": 1}
    assert KhoRadarUid(mt.db, mt.dong, chi_doc=True).lan_cua_viec(NGAY, "hang-ngay", "v1")["trang_thai"] == "loi"
    for chu in (out.out, out.err, caplog.text):
        assert SECRET not in chu and "boom" not in chu
    assert "RuntimeError" in caplog.text


def test_khong_ro_ri_token_ra_stdout_stderr_log_db(mt, capsys, caplog):
    seed_nhom(mt, uid(1), [uid(2), uid(3)])
    mt.kb.loi[("chi_tiet", uid(2))] = LoiEchoTik("token_het_han", 401)
    with caplog.at_level(logging.DEBUG):
        _, j, out = chay_script(mt, capsys)
    assert j["ly_do"] == "token_het_han"
    for chu in (out.out, out.err, caplog.text):
        assert SECRET not in chu
    for p in mt.db.parent.iterdir():
        if p.name.startswith("radar_uid.db"):
            assert SECRET.encode() not in p.read_bytes()
    assert not any(SECRET in str(x) for x in mt.kb.goi)


@pytest.mark.parametrize("argv", [
    [],
    ["--che-do", "linh-tinh", "--ngay", NGAY, "--db", "x.db", "--token-file", "t", "--viec-id", "v", "--tran-goi", "60"],
    ["--che-do", "nap", "--ngay", NGAY, "--db", "x.db", "--token-file", "t", "--viec-id", "v", "--tran-goi", "60"],
    ["--che-do", "nap", "--ngay", NGAY, "--db", "x.db", "--token-file", "t", "--viec-id", "v", "--tran-goi", "60",
     "--goc", "123"],
    ["--che-do", "hang-ngay", "--ngay", "2026-13-40", "--db", "x.db", "--token-file", "t", "--viec-id", "v",
     "--tran-goi", "60"],
    ["--che-do", "hang-ngay", "--ngay", NGAY, "--db", "x.db", "--token-file", "t", "--viec-id", "v", "--tran-goi", "-1"],
    ["--che-do", "hang-ngay", "--ngay", NGAY, "--db", "x.db", "--token-file", "t", "--viec-id", "v", "--tran-goi", "60",
     "--goc", uid(1)],
])
def test_tham_so_sai_exit_1_van_in_mot_dong_json(tmp_path, capsys, monkeypatch, argv):
    monkeypatch.chdir(tmp_path)
    ma = radar_uid.chay(argv, echotik_factory=lambda *a, **k: pytest.fail("không được tạo EchoTik"),
                        bay_gio=Dong(datetime(2026, 12, 1, 12, tzinfo=MUI_GIO_VN)))
    out = capsys.readouterr().out.strip().splitlines()
    assert ma == 1 and len(out) == 1
    assert json.loads(out[0]) == {"trang_thai": "loi", "ly_do": "tham_so_sai", "so_uid": 0, "so_goi": 0}
    assert not list(tmp_path.iterdir())                                # tham số sai: không tạo file DB nào


def test_viec_id_sai_dang_exit_1(mt, capsys):
    ma, j, _ = chay_script(mt, capsys, viec_id="co khoang trang!")
    assert ma == 1 and j["ly_do"] == "tham_so_sai"


# ---------------------------------------------------------------------------------------------------------------
# Ảnh bìa (RU-A5 lượt 2)
# ---------------------------------------------------------------------------------------------------------------
def anh_kho(mt, goc: str) -> dict[str, str]:
    k = KhoRadarUid(mt.db, mt.dong, chi_doc=True)
    return {x["uid"]: x["anh"] for x in k.uid_cua_nhom(goc)}


def test_nap_ghi_anh_e4_cho_tuong_tu_va_e1_cho_goc(mt, capsys):
    c = cai_nap(mt)
    goc = uid(1)
    mt.kb.sp[goc]["images"] = [url_anh(goc, "G"), "https://cdn.echotik.live/khac"]
    them_cover(mt, lambda u: url_anh(u, "E4"))
    ma, j, out = chay_script(mt, capsys, "nap", "n1", goc=goc)
    assert ma == 0 and j == {"trang_thai": "xong", "ly_do": "", "so_uid": 5, "so_goi": 13}      # số GET không đổi
    assert len(mt.kb.goi) == 13
    a = anh_kho(mt, goc)
    assert a[goc] == url_anh(goc, "G")
    for u in c.values():
        assert a[u] == url_anh(u, "E4"), u                      # E1 giả của tương tự không có images ⇒ giữ ảnh E4
    assert "cdn.echotik.live" not in out.out and "cdn.echotik.live" not in out.err
    k = KhoRadarUid(mt.db, mt.dong, chi_doc=True)
    assert next(n for n in k.ds_nhom() if n["goc"] == goc)["anh"] == url_anh(goc, "G")


def test_nap_anh_e4_co_ngay_ca_khi_chua_chup_duoc_e2(mt, capsys):
    """Ảnh E4 được ghi lúc ghi nhóm, không phụ thuộc bước chụp."""
    c = cai_nap(mt)
    goc = uid(1)
    them_cover(mt, lambda u: url_anh(u, "E4"))
    mt.kb.loi[("video", None)] = LoiEchoTik("khong_tim_thay", 404)
    chay_script(mt, capsys, "nap", "n1", goc=goc)
    a = anh_kho(mt, goc)
    assert all(a[u] == url_anh(u, "E4") for u in c.values())


def test_nap_url_la_thi_anh_rong_va_luot_van_xong(mt, capsys):
    c = cai_nap(mt)
    goc = uid(1)
    mt.kb.sp[goc]["images"] = ["http://cdn.echotik.live/a.webp"]                   # http, không https
    them_cover(mt, lambda u: "https://evil.example/a.webp")
    for u in c.values():
        mt.kb.sp[u]["images"] = [None]
    ma, j, _ = chay_script(mt, capsys, "nap", "n1", goc=goc)
    assert ma == 0 and j["trang_thai"] == "xong" and j["so_uid"] == 5
    assert set(anh_kho(mt, goc).values()) == {""}


def test_chup_hang_ngay_e1_ghi_de_anh_cu(mt, capsys):
    seed_nhom(mt, uid(1), [uid(2)])
    k = mo_kho(mt)
    try:
        k.ghi_san_pham(uid(2), TEN_TT, "Shop A", url_anh(uid(2), "CU"))
    finally:
        k.dong()
    mt.kb.sp[uid(1)]["images"] = [url_anh(uid(1), "MOI")]
    mt.kb.sp[uid(2)]["images"] = [url_anh(uid(2), "MOI")]
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 0 and j["so_uid"] == 2 and j["so_goi"] == 4
    assert anh_kho(mt, uid(1)) == {uid(1): url_anh(uid(1), "MOI"), uid(2): url_anh(uid(2), "MOI")}


def test_chup_e1_la_giu_anh_cu(mt, capsys):
    seed_nhom(mt, uid(1), [uid(2)])
    k = mo_kho(mt)
    try:
        k.ghi_san_pham(uid(2), TEN_TT, "Shop A", url_anh(uid(2), "CU"))
    finally:
        k.dong()
    mt.kb.sp[uid(2)]["images"] = ["http://x/y"]
    ma, j, _ = chay_script(mt, capsys)
    assert ma == 0 and j["trang_thai"] == "xong"
    assert anh_kho(mt, uid(1))[uid(2)] == url_anh(uid(2), "CU")
