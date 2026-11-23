"""Test công thức thuần `runner.radar_uid_tinh` (RU-B1, docs/radar-uid.md §3, §5.1 Ví dụ 1-5, §5.2, §5.4).

Chạy: python -B -m pytest tools/test_runner_radar_uid_tinh.py -q -p no:cacheprovider
Thuần: không I/O, không mạng. Dữ liệu là snapshot tổng hợp dựng trong test.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from runner import radar_uid_tinh as rt

VN = timezone(timedelta(hours=7))
UID = "1729706628656957720"          # > 2^53: phải luôn là chuỗi
T0 = datetime(2026, 11, 20, 10, 0, tzinfo=VN)

KHOA_UID_RA = {
    "xep_loai", "uu_tien", "tam", "trung_vi", "trung_vi_truoc", "tong_delta_top5", "tong_delta_top5_truoc",
    "tang_toc", "tang_dot_ngot", "ly_do_tang_toc", "n_video", "n_creator", "n_doi", "ti_le_doi",
    "view_nho_trung_vi", "n_creator_nho", "cau_view_nho", "view_nho_30_trung_vi", "n_creator_nho_30",
    "follower_khong_doc", "trung_vi_14", "n_video_14", "n_video_moi_30", "cau_video_moi", "promote_x",
    "promote_y", "spark", "d_ban_ngay", "creator_moi_ngay", "gia", "hoa_hong", "ton", "du_lieu_luc",
    "echotik_cap_nhat", "so_snapshot", "phu_gio", "co", "co_canh_bao", "ly_do_thieu", "duoi_do_phan_giai",
}


def iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def hv(vid: str, creator: str, view: object, dang: str = "2026-11-10 10:00:00",
       follower: str | None = "2.54K", promote: int | None = 0) -> dict[str, Any]:
    return {"video_id": vid, "creator": creator, "follower": follower, "view": str(view), "ban": None,
            "dang_luc": dang, "is_promote": promote}


def snap(t: datetime, videos: list[dict[str, Any]], cap: str | None = "x", ban: str | None = None,
         so_trang: int = 1, tong_trang: int | None = 1) -> dict[str, Any]:
    return {"uid": UID, "ngay": t.date().isoformat(), "lay_luc": iso(t), "echotik_cap_nhat": cap,
            "ban_tong": ban, "gia": "499.390₫", "hoa_hong": "10%", "ton": "562", "tong_creator": None,
            "so_trang": so_trang, "tong_trang": tong_trang, "videos": {v["video_id"]: v for v in videos}}


def dung_chuoi(cac_delta: list[list[int]], khoang_gio: list[float] | None = None, creators: list[str] | None = None,
               dang: str | list[str] = "2026-11-10 10:00:00", follower: str | None = "2.54K",
               cap: list[str | None] | None = None, promote: list[int | None] | None = None,
               gio_dau: datetime = T0) -> list[dict[str, Any]]:
    """Chuỗi snapshot: snapshot đầu rồi mỗi kỳ cộng `cac_delta[i]` view cho từng video (gio=24 ⇒ d24 = delta)."""
    n = len(cac_delta[0])
    ten = creators or [f"c{i // 2}" for i in range(n)]
    ngay_dang = dang if isinstance(dang, list) else [dang] * n
    views = [100_000] * n
    t = gio_dau
    out: list[dict[str, Any]] = []
    for i in range(len(cac_delta) + 1):
        if i > 0:
            t = t + timedelta(hours=(khoang_gio[i - 1] if khoang_gio else 24))
            views = [v + d for v, d in zip(views, cac_delta[i - 1])]
        vids = [hv(f"72{j:017d}", ten[j], views[j], ngay_dang[j], follower, promote[j] if promote else 0)
                for j in range(n)]
        out.append(snap(t, vids, cap=(cap[i] if cap else f"cap-{i}")))
    return out


def hom_nay_sau(snaps: list[dict[str, Any]], gio: float = 2) -> datetime:
    return datetime.fromisoformat(snaps[-1]["lay_luc"]) + timedelta(hours=gio)


# --- Ví dụ 1: bảng nguyên văn §5.1 ---
BANG_VI_DU_1 = [  # (creator, a, b)
    ("c1", 12400, 15100), ("c1", 8000, 9500), ("c2", 3200, 3900), ("c2", 5600, 6100), ("c3", 20000, 20900),
    ("c3", 1100, 1100), ("c4", 9000, 12300), ("c4", 4000, 4800), ("c5", 700, 1000), ("c5", 15000, 15400),
    ("c6", 6000, 6600),
]


def cap_vi_du_1(gio: float = 24.0) -> tuple[dict[str, Any], dict[str, Any]]:
    a = snap(T0, [hv(f"v{i + 1}", c, x) for i, (c, x, _) in enumerate(BANG_VI_DU_1)])
    b = snap(T0 + timedelta(hours=gio), [hv(f"v{i + 1}", c, y) for i, (c, _, y) in enumerate(BANG_VI_DU_1)], cap="y")
    return a, b


# ---------------------------------------------------------------- hằng, RE_UID, số rút gọn

def test_re_uid_va_nguong_du_khoa() -> None:
    assert rt.RE_UID.match("1729420930611055346") and not rt.RE_UID.match("172942093061105534")
    assert not rt.RE_UID.match("1729420930611055346\n") and not rt.RE_UID.match("17294209306110553a6")
    assert set(rt.NGUONG) == {
        "KY_GIO", "TUOI_SONG_NGAY", "DU_LIEU_CU_GIO", "TANG_TOC_MIN", "SNAPSHOT_TOI_THIEU", "SAN_TOP5",
        "PHU_GIO_TOI_THIEU", "TOP5_TOI_THIEU", "VIDEO_TOI_THIEU", "FOLLOWER_NHO", "CREATOR_TOI_THIEU",
        "VIEW_CAO_NHO", "KHONG_LAM_MOI_DOI_TOI_DA", "CREATOR_NHO_TOI_THIEU", "CAP_NHAT_KHONG_DOI_KY",
        "TUOI_MOI_NGAY", "TUOI_NHO_PHU_NGAY", "VIDEO_MOI_NGAY", "CREATOR_CHI_PHOI_PT", "TOP_N", "ADS_BAT",
        "ADS_PROMOTE_PT", "NGAY_HA_UU_TIEN", "TRANG_VIDEO_TOI_DA"}
    n = rt.NGUONG
    assert n["KY_GIO"] == (8, 54) and n["TUOI_SONG_NGAY"] == 90 and n["DU_LIEU_CU_GIO"] == 36
    assert n["TANG_TOC_MIN"] == 2.0 and n["SAN_TOP5"] == 250 and n["TOP5_TOI_THIEU"] == 1000
    assert n["SNAPSHOT_TOI_THIEU"] == 4 and n["PHU_GIO_TOI_THIEU"] == 70
    assert n["VIDEO_TOI_THIEU"] == 8 and n["CREATOR_TOI_THIEU"] == 3 and n["TOP_N"] == 5
    assert n["FOLLOWER_NHO"] == 10_000 and n["VIEW_CAO_NHO"] == 5_000 and n["CREATOR_NHO_TOI_THIEU"] == 3
    assert n["KHONG_LAM_MOI_DOI_TOI_DA"] == 1 and n["CAP_NHAT_KHONG_DOI_KY"] == 2
    assert (n["TUOI_MOI_NGAY"], n["TUOI_NHO_PHU_NGAY"], n["VIDEO_MOI_NGAY"]) == (14, 30, 30)
    assert n["CREATOR_CHI_PHOI_PT"] == 50 and n["ADS_BAT"] is False and n["ADS_PROMOTE_PT"] == 30
    assert n["NGAY_HA_UU_TIEN"] == 7 and n["TRANG_VIDEO_TOI_DA"] == 1


@pytest.mark.parametrize("vao, ra", [
    (125, (125, 0)), ("125", (125, 0)), ("21.81K", (21810, 5)), ("9.4K", (9400, 5)), ("1.79M", (1_790_000, 5000)),
    ("2.5B", (2_500_000_000, 5_000_000)), ("2.54K", (2540, 5)), ("7K", (7000, 5)), (" 38.11K ", (38110, 5)),
])
def test_doc_so_rut_gon_hop_le(vao: object, ra: tuple[int, int]) -> None:
    kq = rt.doc_so_rut_gon(vao)
    assert kq == ra and kq is not None and kq.gia_tri == ra[0] and kq.sai_so == ra[1]


@pytest.mark.parametrize("vao", ["N/A", "", "   ", None, "abc", "1.2.3K", "K", "12X", "-5", -5, 1.5, True, "1,5K"])
def test_doc_so_rut_gon_khong_doc_duoc_la_none(vao: object) -> None:
    assert rt.doc_so_rut_gon(vao) is None


# ---------------------------------------------------------------- §3 tìm tương tự

def test_bo_dau() -> None:
    assert rt.bo_dau("Kẹp tóc đẹp Đà Nẵng") == "Kep toc dep Da Nang"


def test_lam_sach_ten_vi_du_muc_3() -> None:
    assert rt.lam_sach_ten("[HOT] Kẹp tóc càng cua mini 8cm freeship") == ["kẹp", "tóc", "càng", "cua", "mini"]


def test_lam_sach_ten_bo_ngoac_don_vi_so_tran_va_cum_quang_cao() -> None:
    assert rt.lam_sach_ten("Bình giữ nhiệt 500ml (Chính hãng) 【Sale】 combo set 2 cái") == ["bình", "giữ", "nhiệt"]
    assert rt.lam_sach_ten("Áo thun loại 1 cao cấp, giá rẻ!") == ["áo", "thun"]
    assert rt.lam_sach_ten("Sạc 20W 5000mAh 2.5kg 12v") == ["sạc"]


def test_lam_sach_ten_chuan_nfc() -> None:
    phan_ra = "Kẹp tóc"                     # NFD
    assert rt.lam_sach_ten(phan_ra) == ["kẹp", "tóc"]


def test_tu_khoa_tim() -> None:
    assert rt.tu_khoa_tim("[HOT] Kẹp tóc càng cua mini 8cm freeship") == ["kẹp tóc càng cua", "kẹp tóc càng", "kẹp tóc"]
    assert rt.tu_khoa_tim("Kẹp tóc") == ["kẹp tóc"]                     # không trùng chuỗi
    assert rt.tu_khoa_tim("a b c") == ["a b c", "a b"]
    assert rt.tu_khoa_tim("freeship 12cm") == []


def test_do_giong_vi_du_muc_3() -> None:
    goc = "[HOT] Kẹp tóc càng cua mini 8cm freeship"
    assert rt.do_giong(goc, "Kẹp tóc càng cua to 12cm") == pytest.approx(4 / 6)
    assert rt.do_giong(goc, "Máy sấy tóc mini") == pytest.approx(2 / 7)
    assert rt.do_giong(goc, goc) == 1.0
    assert rt.do_giong(goc, "") == 0.0
    assert rt.do_giong("", "") == 0.0
    assert rt.do_giong("Đèn đỏ", "Den do") == 1.0                         # bỏ dấu, đ→d


def test_keyword_co_loc() -> None:
    assert rt.keyword_co_loc("kẹp tóc", ["Kẹp tóc càng cua", "Máy sấy", "Kẹp nơ"]) is True      # 2/3
    assert rt.keyword_co_loc("kẹp tóc", ["Kẹp tóc càng cua", "Máy sấy"]) is True                # đúng 50%
    assert rt.keyword_co_loc("kẹp tóc", ["Máy sấy", "Bàn là", "Kẹp nơ"]) is False               # 1/3
    assert rt.keyword_co_loc("kep toc", ["KẸP TÓC"]) is True                                    # bỏ dấu
    assert rt.keyword_co_loc("kẹp tóc", []) is False


def uv(uid: str, ten: str, gia: str | None, ban: str | None) -> dict[str, Any]:
    return {"uid": uid, "ten": ten, "gia": gia, "ban_7d": ban}


def test_chon_tuong_tu_loc_va_sap() -> None:
    goc = "[HOT] Kẹp tóc càng cua mini 8cm freeship"
    a = uv("1000000000000000001", "Kẹp tóc càng cua to 12cm", "$12.7", "36")               # 0,667 giữ
    b = uv("1000000000000000002", "Máy sấy tóc mini", "$12.7", "999")                       # 0,29 loại
    c = uv("1000000000000000003", "Kẹp tóc càng cua mini", "$50", "10")                     # giá > 2×19,37 loại
    d = uv("1000000000000000004", "Kẹp tóc càng cua mini", "$5", "10")                      # giá < 0,5×19,37 loại
    e = uv("1000000000000000005", "Kẹp tóc càng cua mini xinh", None, "500")                # thiếu giá ⇒ bỏ lọc giá
    f = uv("1000000000000000006", "Kẹp tóc càng cua mini xinh", "$12", "9999")              # đã loại
    h = uv("123", "Kẹp tóc càng cua mini xinh", "$12", "9999")                              # uid sai dạng
    kq = rt.chon_tuong_tu(goc, "$19.37", [a, b, c, d, e, f, a, h], frozenset({"1000000000000000006"}))
    assert [x["uid"] for x in kq] == ["1000000000000000005", "1000000000000000001"]
    assert all(isinstance(x["uid"], str) for x in kq)
    assert [x["uid"] for x in rt.chon_tuong_tu(goc, "$19.37", [a, e], frozenset(), so_luong=1)] == ["1000000000000000005"]


def test_chon_tuong_tu_hoa_do_giong_xep_theo_ban_7d_va_gioi_han() -> None:
    goc = "Kẹp tóc càng cua"
    x = uv("1729706628656957720", "Kẹp tóc càng cua", "$10", "36")
    y = uv("1729706628656957721", "Kẹp tóc càng cua", "$10", "1.2K")
    z = uv("1729706628656957722", "Kẹp tóc càng cua", "$10", None)
    assert [u["uid"] for u in rt.chon_tuong_tu(goc, "$10", [z, x, y], frozenset())] == [
        "1729706628656957721", "1729706628656957720", "1729706628656957722"]
    nhieu = [uv(f"17297066286569{i:05d}", "Kẹp tóc càng cua", "$10", str(i)) for i in range(30)]
    assert len(rt.chon_tuong_tu(goc, "$10", nhieu, frozenset())) == 10
    assert rt.chon_tuong_tu(goc, None, [x], frozenset()) == [x]                              # thiếu giá gốc
    assert rt.chon_tuong_tu(goc, "499.390₫", [x], frozenset()) == [x]                        # giá không cùng USD ⇒ bỏ lọc


# ---------------------------------------------------------------- Ví dụ 1: tinh_ky

def test_vi_du_1_trung_vi_700() -> None:
    ky = rt.tinh_ky(*cap_vi_du_1())
    assert ky["gio"] == 24.0 and ky["hop_le"] is True
    assert ky["n_video"] == 11 and ky["n_creator"] == 6 and ky["n_doi"] == 10
    assert ky["ti_le_doi"] == pytest.approx(90.9, abs=0.05)
    assert ky["khong_lam_moi"] is False
    assert ky["trung_vi"] == 700
    assert ky["tong_delta_top5"] == 9200
    assert sorted(d for _, _, d in ky["ds_d24"]) == [0, 300, 400, 500, 600, 700, 800, 900, 1500, 2700, 3300]
    assert {c for _, c, _ in ky["ds_d24"]} == {"c1", "c2", "c3", "c4", "c5", "c6"}
    assert ky["loai"]["duoi_do_phan_giai"] == 0


def test_vi_du_1_25_2_gio_v3_la_666() -> None:
    ky = rt.tinh_ky(*cap_vi_du_1(25.2))
    assert ky["gio"] == pytest.approx(25.2)
    d = {v: x for v, _, x in ky["ds_d24"]}
    assert d["v3"] == 666 and d["v1"] == 2571                        # 2700 / 1,05
    assert ky["hop_le"] is True


def test_vi_du_1_do_phan_giai_rut_gon() -> None:
    a = snap(T0, [hv("m", "c1", "1.79M"), hv("k", "c2", "38.11K"), hv("n", "c3", "100"), hv("p", "c4", "5.00K")])
    b = snap(T0 + timedelta(hours=24), [hv("m", "c1", "1.80M"), hv("k", "c2", "38.74K"), hv("n", "c3", "150"),
                                         hv("p", "c4", "N/A")], cap="y")
    ky = rt.tinh_ky(a, b)
    d = {v: x for v, _, x in ky["ds_d24"]}
    assert "m" not in d                                              # Δ 10.000 ≤ sai_so_tong 10.000 ⇒ loại
    assert d["k"] == 630                                            # sai_so_tong 10 ≤ 20 ⇒ giữ
    assert d["n"] == 50
    assert "p" not in d                                              # không đọc được view ⇒ không đo được
    assert ky["loai"]["duoi_do_phan_giai"] == 1


def test_do_phan_giai_giu_khi_delta_vuot_sai_so() -> None:
    a = snap(T0, [hv("m", "c1", "1.79M")])
    b = snap(T0 + timedelta(hours=24), [hv("m", "c1", "1.81M")], cap="y")      # Δ 20.000 > 10.000
    ky = rt.tinh_ky(a, b)
    assert [d for _, _, d in ky["ds_d24"]] == [20000] and ky["loai"]["duoi_do_phan_giai"] == 0


# ---------------------------------------------------------------- Ví dụ 2: KHONG_LAM_MOI

def test_vi_du_2_n_doi_0_la_khong_lam_moi() -> None:
    s = dung_chuoi([[0] * 39])
    ky = rt.tinh_ky(s[0], s[1])
    assert ky["n_doi"] == 0 and ky["khong_lam_moi"] is True
    assert ky["trung_vi"] is None and ky["tong_delta_top5"] is None
    assert ky["n_video"] == 39                                       # số thô vẫn trả (video đăng ≤ 90 ngày)


def test_vi_du_2_n_doi_1_van_la_khong_lam_moi_nhung_2_thi_khong() -> None:
    d1 = [0] * 39
    d1[0] = 500
    s = dung_chuoi([d1])
    assert rt.tinh_ky(s[0], s[1])["khong_lam_moi"] is True
    d2 = list(d1)
    d2[1] = 300
    s = dung_chuoi([d2])
    assert rt.tinh_ky(s[0], s[1])["khong_lam_moi"] is False


def test_vi_du_2_cap_nhat_dung_yen_hai_ky() -> None:
    a, b = cap_vi_du_1()
    a["echotik_cap_nhat"] = b["echotik_cap_nhat"] = "2026-11-22 07:55"
    assert rt.tinh_ky(a, b, cap_nhat_dung_yen=False)["khong_lam_moi"] is False      # mới đứng yên 1 kỳ
    ky = rt.tinh_ky(a, b, cap_nhat_dung_yen=True)
    assert ky["khong_lam_moi"] is True and ky["trung_vi"] is None and ky["tong_delta_top5"] is None
    b["echotik_cap_nhat"] = "2026-11-23 07:55"                                      # kỳ này có đổi ⇒ không đứng yên
    assert rt.tinh_ky(a, b, cap_nhat_dung_yen=True)["khong_lam_moi"] is False


def test_vi_du_2_ba_snapshot_cung_cap_nhat_thanh_co_chan() -> None:
    s = dung_chuoi([[100] * 11, [200] * 11], cap=["2026-11-22 07:55"] * 3)
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert "KHONG_LAM_MOI" in kq["co"] and kq["xep_loai"] == "chan"
    assert kq["trung_vi"] is None and kq["tong_delta_top5"] is None
    s2 = dung_chuoi([[100] * 11, [200] * 11], cap=["2026-11-21 07:55", "2026-11-22 07:55", "2026-11-22 07:55"])
    assert "KHONG_LAM_MOI" not in rt.xep_hang_uid(s2, hom_nay_sau(s2), "2026-11-20")["co"]      # chỉ đứng yên 1 kỳ


# ---------------------------------------------------------------- Ví dụ 3: tang_toc

@pytest.mark.parametrize("nay, truoc, ty_le, dot_ngot", [
    (9200, 1600, 5.75, True),
    (7770, 540, 14.39, True),
    (400, 100, 1.6, False),                  # 400/250 = 1,6 < 2
    (900, 0, 3.6, False),                    # 3,6 nhưng 900 < 1.000
    (1000, 500, 2.0, True),                  # đúng ngưỡng cả hai
    (999, 100, 3.996, False),
])
def test_tinh_tang_toc(nay: int, truoc: int, ty_le: float, dot_ngot: bool) -> None:
    kq, dn = rt.tinh_tang_toc(nay, truoc)
    assert kq == pytest.approx(ty_le, abs=0.01) and dn is dot_ngot


def test_vi_du_3_xep_hang_tang_toc_5_75() -> None:
    ky1 = [600, 400, 300, 200, 100, 0, 0, 0, 0, 0, 0]               # top5 = 1.600
    ky2 = [2700, 1500, 700, 500, 900, 0, 3300, 800, 300, 400, 600]  # top5 = 9.200
    s = dung_chuoi([ky1, ky2])
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["tong_delta_top5"] == 9200 and kq["tong_delta_top5_truoc"] == 1600
    assert kq["tang_toc"] == pytest.approx(5.75) and kq["tang_dot_ngot"] is True and kq["ly_do_tang_toc"] == ""


def test_vi_du_3_vai_video_bung_no_trung_vi_100_nhung_dot_ngot() -> None:
    ky1 = [200, 150, 100, 50, 40, 0, 0, 0, 0, 0, 0]                 # top5 = 540
    ky2 = [0, 0, 20, 40, 60, 100, 120, 150, 2000, 2500, 3000]
    s = dung_chuoi([ky1, ky2])
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["trung_vi"] == 100 and kq["tong_delta_top5"] == 7770
    assert kq["tang_toc"] == pytest.approx(14.39, abs=0.01) and kq["tang_dot_ngot"] is True


def test_vi_du_3_ky_truoc_gap_thi_tang_toc_none_co_ly_do() -> None:
    ky1 = [600, 400, 300, 200, 100, 0, 0, 0, 0, 0, 0]
    ky2 = [2700, 1500, 700, 500, 900, 0, 3300, 800, 300, 400, 600]
    s = dung_chuoi([ky1, ky2], khoang_gio=[60, 24])                 # kỳ trước 60 giờ > 54 ⇒ GAP
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["tang_toc"] is None and kq["tang_dot_ngot"] is False and kq["ly_do_tang_toc"] == "kỳ trước GAP"
    assert kq["tong_delta_top5_truoc"] is None and kq["trung_vi_truoc"] is None
    assert kq["tong_delta_top5"] == 9200 and "GAP" not in kq["co"]          # GAP là của kỳ gần nhất, không phải kỳ trước


def test_tang_toc_chua_co_ky_truoc() -> None:
    s = dung_chuoi([[600, 400, 300, 200, 100, 0, 0, 0, 0, 0, 0]])
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["tang_toc"] is None and kq["ly_do_tang_toc"] == "chưa có kỳ trước"


# ---------------------------------------------------------------- Ví dụ 4: view_nho

def snap_vi_du_4() -> dict[str, Any]:
    t = datetime(2026, 11, 23, 10, 0, tzinfo=VN)
    d = "2026-11-15 09:00:00"                                       # 8 ngày
    return snap(t, [
        hv("a1", "c1", 9800, d, "2.54K"), hv("a2", "c2", 6400, d, "8.1K"), hv("a3", "c3", 12000, d, "450"),
        hv("a4", "c4", 3100, d, "9.99K"), hv("a5", "c5", 40000, d, "15K"), hv("a6", "c6", 7200, d, "1.2K"),
        hv("a7", "c7", 50000, d, "N/A"),
    ])


def test_vi_du_4_view_nho() -> None:
    assert rt.view_nho(snap_vi_du_4()) == (7200, 5, 1)
    assert rt.view_nho_cao(7200, 5) is True
    assert rt.view_nho_cao(4999, 5) is False and rt.view_nho_cao(7200, 2) is False and rt.view_nho_cao(None, 0) is False


def test_vi_du_4_follower_thieu_khong_doc_duoc_bi_loai_khong_coi_la_0() -> None:
    s = snap_vi_du_4()
    s["videos"]["a8"] = hv("a8", "c8", 9000, "2026-11-15 09:00:00", None)
    s["videos"]["a9"] = hv("a9", "c9", 9000, "2026-11-15 09:00:00", "lạ")
    assert rt.view_nho(s) == (7200, 5, 3)                            # c7, c8, c9


def test_vi_du_4_khong_video_trong_14_ngay_view_nho_none() -> None:
    t = datetime(2026, 11, 23, 10, 0, tzinfo=VN)
    s = snap(t, [hv("o1", "c1", 9000, "2026-10-10 09:00:00", "1K"), hv("o2", "c2", 9000, "2026-11-01 09:00:00", "1K")])
    assert rt.view_nho(s) == (None, 0, 0)
    assert rt.view_nho(s, 30) == (9000, 1, 0)                        # cửa sổ phụ ≤ 30 ngày tính riêng


def test_view_nho_ranh_gioi_14_ngay_va_follower_10k() -> None:
    t = datetime(2026, 11, 23, 10, 0, tzinfo=VN)
    s = snap(t, [hv("r1", "c1", 8000, "2026-11-09 10:00:00", "9.99K"),         # đúng 14 ngày ⇒ lấy
                 hv("r2", "c2", 8000, "2026-11-09 09:59:00", "1K"),             # > 14 ngày
                 hv("r3", "c3", 8000, "2026-11-20 10:00:00", "10K")])           # follower = 10.000 ⇒ loại (< 10K)
    assert rt.view_nho(s) == (8000, 1, 0)


def test_xep_hang_cau_view_nho_va_cua_so_30() -> None:
    s = dung_chuoi([[100] * 11], dang="2026-10-30 10:00:00")        # 24 ngày tuổi ở lần chụp cuối
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["view_nho_trung_vi"] is None and kq["n_creator_nho"] == 0
    assert kq["cau_view_nho"] == "không có video ≤ 14 ngày"
    assert kq["view_nho_30_trung_vi"] == 100_100 and kq["n_creator_nho_30"] == 6
    ok = dung_chuoi([[100] * 11])
    kq2 = rt.xep_hang_uid(ok, hom_nay_sau(ok), "2026-11-20")
    assert kq2["view_nho_trung_vi"] == 100_100 and kq2["n_creator_nho"] == 6 and kq2["cau_view_nho"] == ""


def test_xep_hang_cau_view_nho_khi_co_video_moi_nhung_creator_lon() -> None:
    s = dung_chuoi([[100] * 11], follower="50K")
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["view_nho_trung_vi"] is None
    assert kq["cau_view_nho"] and kq["cau_view_nho"] != "không có video ≤ 14 ngày"


# ---------------------------------------------------------------- Ví dụ 5: UID mẫu 39 video

def snaps_vi_du_5() -> list[dict[str, Any]]:
    d24 = [4, 6, 9, 15, 30, 120] + [0] * 33
    creators = ["k0", "k0", "k1", "k1", "k2", "k3"] + [f"z{i}" for i in range(33)]
    return dung_chuoi([d24], creators=creators, dang="2025-03-01 10:00:00", promote=[1] + [0] * 38)


def test_vi_du_5_39_video_6_doi_khong_co_nhung_thieu_mau() -> None:
    s = snaps_vi_du_5()
    ky = rt.tinh_ky(s[0], s[1])
    assert ky["n_doi"] == 6 and ky["ti_le_doi"] == pytest.approx(15.4, abs=0.05) and ky["khong_lam_moi"] is False
    assert ky["n_video"] == 6 and ky["n_creator"] == 4 and ky["trung_vi"] == 12 and ky["tong_delta_top5"] == 180
    assert rt.du_mau(ky) is False
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert set(kq) == KHOA_UID_RA
    assert "KHONG_LAM_MOI" not in kq["co"] and "THIEU_MAU" in kq["co"]
    assert kq["xep_loai"] == "chua_du" and kq["tam"] is True and kq["trung_vi"] == 12 and kq["tong_delta_top5"] == 180
    assert kq["n_video"] == 6 and kq["n_creator"] == 4 and kq["n_doi"] == 6 and kq["ti_le_doi"] == 15.4
    assert any("n_video 6/8" in x for x in kq["ly_do_thieu"]) and "so_snapshot 2/4" in kq["ly_do_thieu"]
    assert kq["tang_toc"] is None and kq["ly_do_tang_toc"] == "chưa có kỳ trước"
    assert kq["view_nho_trung_vi"] is None and kq["cau_view_nho"] == "không có video ≤ 14 ngày"
    assert kq["n_video_moi_30"] == 0 and kq["cau_video_moi"] == "Không có video mới 30 ngày"
    assert (kq["promote_x"], kq["promote_y"]) == (1, 39)
    assert kq["so_snapshot"] == 2 and kq["phu_gio"] == 24.0


# ---------------------------------------------------------------- §5.2 cờ

def test_co_gap_55_gio_co_48_gio_khong() -> None:
    s = dung_chuoi([[100] * 11], khoang_gio=[55], gio_dau=datetime(2026, 11, 20, 8, 0, tzinfo=VN))
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert "GAP" in kq["co"] and kq["xep_loai"] == "chan"
    assert kq["trung_vi"] is None and kq["tong_delta_top5"] is None
    s2 = dung_chuoi([[100] * 11], khoang_gio=[48])
    kq2 = rt.xep_hang_uid(s2, hom_nay_sau(s2), "2026-11-20")
    assert "GAP" not in kq2["co"] and kq2["trung_vi"] == 50                 # 100 / (48/24)
    s3 = dung_chuoi([[100] * 11], khoang_gio=[7])
    assert "GAP" in rt.xep_hang_uid(s3, hom_nay_sau(s3), "2026-11-20")["co"]
    for gio in (8, 54):
        sx = dung_chuoi([[100] * 11], khoang_gio=[gio])
        assert "GAP" not in rt.xep_hang_uid(sx, hom_nay_sau(sx), "2026-11-20")["co"]


def test_co_du_lieu_cu_50_gio() -> None:
    s = [snap(datetime(2026, 11, 21, 8, 0, tzinfo=VN), [hv("a", "c1", 100)])]
    kq = rt.xep_hang_uid(s, datetime(2026, 11, 23, 10, 0, tzinfo=VN), "2026-11-20")
    assert "DU_LIEU_CU" in kq["co"] and kq["xep_loai"] == "chan"
    kq2 = rt.xep_hang_uid(s, datetime(2026, 11, 22, 20, 0, tzinfo=VN), "2026-11-20")        # 36 giờ đúng ⇒ chưa cũ
    assert "DU_LIEU_CU" not in kq2["co"]
    kq3 = rt.xep_hang_uid(s, datetime(2026, 11, 22, 20, 1, tzinfo=VN), "2026-11-20")
    assert "DU_LIEU_CU" in kq3["co"]


def test_hom_nay_khong_mui_gio_duoc_hieu_la_gio_vn() -> None:
    s = [snap(datetime(2026, 11, 21, 8, 0, tzinfo=VN), [hv("a", "c1", 100)])]
    assert "DU_LIEU_CU" in rt.xep_hang_uid(s, datetime(2026, 11, 23, 10, 0), "2026-11-20")["co"]
    assert "DU_LIEU_CU" not in rt.xep_hang_uid(s, datetime(2026, 11, 21, 20, 0), "2026-11-20")["co"]


def test_thieu_mau_n7_c2_tam_true_so_van_tra() -> None:
    s = dung_chuoi([[100, 200, 300, 400, 500, 600, 700]], creators=["c1", "c1", "c1", "c2", "c2", "c2", "c2"])
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert "THIEU_MAU" in kq["co"] and kq["xep_loai"] == "chua_du" and kq["tam"] is True
    assert kq["n_video"] == 7 and kq["n_creator"] == 2 and kq["trung_vi"] == 400
    assert any("n_creator 2/3" in x for x in kq["ly_do_thieu"]) and any("n_video 7/8" in x for x in kq["ly_do_thieu"])


def test_thieu_mau_khi_chi_co_1_snapshot_khong_tinh_duoc_so() -> None:
    s = dung_chuoi([[100] * 11])[:1]
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["xep_loai"] == "chua_du" and kq["tam"] is False
    assert kq["trung_vi"] is None and kq["n_video"] is None and kq["so_snapshot"] == 1
    assert kq["ly_do_thieu"]                                         # luôn kèm lý do, không "—" trơn


def test_khong_co_snapshot_nao() -> None:
    kq = rt.xep_hang_uid([], datetime(2026, 11, 23, 10, 0, tzinfo=VN), "2026-11-20")
    assert set(kq) == KHOA_UID_RA and kq["xep_loai"] == "chua_du" and kq["so_snapshot"] == 0
    assert kq["trung_vi"] is None and kq["ly_do_thieu"] and kq["du_lieu_luc"] is None


def test_thieu_mau_do_phu_gio_va_so_snapshot() -> None:
    s = dung_chuoi([[100] * 11] * 3, khoang_gio=[24, 24, 20])        # 68 giờ < 70
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["so_snapshot"] == 4 and kq["phu_gio"] == 68.0
    assert "THIEU_MAU" in kq["co"] and any(x.startswith("phu_gio 68") for x in kq["ly_do_thieu"])
    s2 = dung_chuoi([[100] * 11] * 3, khoang_gio=[24, 24, 22])       # 70 ⇒ đủ
    assert "THIEU_MAU" not in rt.xep_hang_uid(s2, hom_nay_sau(s2), "2026-11-20")["co"]


def test_chuoi_snapshot_lien_tuc_dung_o_gap() -> None:
    s = dung_chuoi([[100] * 11] * 4, khoang_gio=[60, 24, 24, 24])    # khoảng 60 giờ giữa snapshot 0 và 1
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["so_snapshot"] == 4 and kq["phu_gio"] == 72.0
    s2 = dung_chuoi([[100] * 11] * 4, khoang_gio=[24, 60, 24, 24])   # đứt giữa 1 và 2 ⇒ chỉ còn 3 snapshot
    kq2 = rt.xep_hang_uid(s2, hom_nay_sau(s2), "2026-11-20")
    assert kq2["so_snapshot"] == 3 and kq2["phu_gio"] == 48.0


def test_mau_top_video() -> None:
    s = dung_chuoi([[100] * 11])
    s[-1]["tong_trang"] = 2
    assert "MAU_TOP_VIDEO" in rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")["co_canh_bao"]
    s[-1]["tong_trang"] = 1
    assert "MAU_TOP_VIDEO" not in rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")["co_canh_bao"]
    s[-1]["tong_trang"] = None
    assert "MAU_TOP_VIDEO" not in rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")["co_canh_bao"]
    # Thứ tự ngày đăng KHÔNG ảnh hưởng cờ (DB đọc ORDER BY video_id, id tăng theo thời gian đăng):
    # chỉ last_page > số trang đã lấy mới bật.
    tang = dung_chuoi([[100] * 11], dang=[f"2026-11-{10 + i:02d} 10:00:00" for i in range(11)])    # đăng tăng dần theo id
    tang[-1]["tong_trang"] = 1
    assert "MAU_TOP_VIDEO" not in rt.xep_hang_uid(tang, hom_nay_sau(tang), "2026-11-20")["co_canh_bao"]
    tang[-1]["tong_trang"] = 2
    assert tang[-1]["so_trang"] == 1
    assert "MAU_TOP_VIDEO" in rt.xep_hang_uid(tang, hom_nay_sau(tang), "2026-11-20")["co_canh_bao"]
    giam = dung_chuoi([[100] * 11], dang=[f"2026-11-{20 - i:02d} 10:00:00" for i in range(11)])    # đăng giảm dần
    giam[-1]["tong_trang"] = 1
    assert "MAU_TOP_VIDEO" not in rt.xep_hang_uid(giam, hom_nay_sau(giam), "2026-11-20")["co_canh_bao"]
    lon = dung_chuoi([[100] * 11], dang=[f"2026-11-{d:02d} 10:00:00" for d in (15, 3, 19, 8, 12, 1, 20, 6, 17, 10, 4)])  # lộn xộn
    lon[-1]["tong_trang"] = 1
    assert "MAU_TOP_VIDEO" not in rt.xep_hang_uid(lon, hom_nay_sau(lon), "2026-11-20")["co_canh_bao"]


def test_mot_creator_chi_phoi() -> None:
    s = dung_chuoi([[9000, 1500, 1500]], creators=["c1", "c2", "c3"])
    assert "MOT_CREATOR_CHI_PHOI" in rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")["co_canh_bao"]
    a, b = cap_vi_du_1()                                              # 4.200/11.700 = 35,9% ⇒ không
    kq = rt.xep_hang_uid([a, b], hom_nay_sau([a, b]), "2026-11-20")
    assert "MOT_CREATOR_CHI_PHOI" not in kq["co_canh_bao"]
    hai = dung_chuoi([[9000, 1000]], creators=["c1", "c2"])           # n_creator = 2 < 3 ⇒ không xét
    assert "MOT_CREATOR_CHI_PHOI" not in rt.xep_hang_uid(hai, hom_nay_sau(hai), "2026-11-20")["co_canh_bao"]


def test_nghi_ads_khong_bao_gio_bat_khi_ads_bat_false(monkeypatch: pytest.MonkeyPatch) -> None:
    s = dung_chuoi([[100] * 11], promote=[1] * 11)
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert (kq["promote_x"], kq["promote_y"]) == (11, 11) and "NGHI_ADS" not in kq["co_canh_bao"]
    monkeypatch.setitem(rt.NGUONG, "ADS_BAT", True)                   # luật R1 chỉ sống sau công tắc
    assert "NGHI_ADS" in rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")["co_canh_bao"]
    ts = dung_chuoi([[100] * 11], promote=[1, 1] + [0] * 9)           # x = 2 < 3
    assert "NGHI_ADS" not in rt.xep_hang_uid(ts, hom_nay_sau(ts), "2026-11-20")["co_canh_bao"]


def test_promote_none_khi_khong_biet() -> None:
    s = dung_chuoi([[100] * 11], promote=[None] * 11)
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["promote_x"] is None and kq["promote_y"] is None


# ---------------------------------------------------------------- xếp loại

def chuoi_dang_co_da(**kw: Any) -> list[dict[str, Any]]:
    ky3 = kw.pop("ky3", [1000, 900, 800, 700, 600] + [100] * 6)
    return dung_chuoi([[100] * 11, [100] * 11, ky3], **kw)


def test_dang_co_da_can_ca_hai_tieu_chi() -> None:
    s = chuoi_dang_co_da()
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["xep_loai"] == "dang_co_da" and kq["tam"] is False and kq["co"] == []
    assert kq["tang_dot_ngot"] is True and kq["tong_delta_top5"] == 4000 and kq["tong_delta_top5_truoc"] == 500
    assert kq["tang_toc"] == pytest.approx(8.0) and kq["so_snapshot"] == 4 and kq["phu_gio"] == 72.0
    assert kq["spark"] == [100, 100, 100]


def test_chua_co_da_khi_thieu_tieu_chi_1() -> None:
    s = chuoi_dang_co_da(ky3=[100] * 11)
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["xep_loai"] == "chua_co_da" and kq["tang_dot_ngot"] is False
    assert any("tiêu chí 1" in x for x in kq["ly_do_thieu"]) and not any("tiêu chí 2" in x for x in kq["ly_do_thieu"])


def test_chua_co_da_khi_thieu_tieu_chi_2() -> None:
    s = chuoi_dang_co_da(follower="50K")
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["tang_dot_ngot"] is True and kq["xep_loai"] == "chua_co_da"
    assert any("tiêu chí 2" in x for x in kq["ly_do_thieu"]) and not any("tiêu chí 1" in x for x in kq["ly_do_thieu"])


def test_tieu_chi_1_none_do_ky_truoc_gap_thi_chi_la_chua_du() -> None:
    """Kỳ trước GAP luôn làm đứt chuỗi liên tục (so_snapshot < 4) nên UID nằm ở `chua_du`, không tới `chua_co_da`."""
    s = dung_chuoi([[100] * 11, [100] * 11, [1000, 900, 800, 700, 600] + [100] * 6], khoang_gio=[24, 60, 24])
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["tang_toc"] is None and kq["tang_dot_ngot"] is False and kq["ly_do_tang_toc"] == "kỳ trước GAP"
    assert kq["xep_loai"] == "chua_du" and kq["so_snapshot"] == 2


def test_chua_co_da_khi_tieu_chi_1_none_do_ky_truoc_khong_lam_moi() -> None:
    s = dung_chuoi([[100] * 11, [100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [1000, 900, 800, 700, 600] + [100] * 6])
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["tang_toc"] is None and kq["ly_do_tang_toc"] == "kỳ trước EchoTik không làm mới"
    assert kq["xep_loai"] == "chua_co_da"


def chuoi_du_mau_hai_ky(ky2: list[int]) -> list[dict[str, Any]]:
    """5 video mới (≤ 14 ngày, creator nhỏ) + 6 video cũ (> 90 ngày): video cũ chỉ "đang sống" khi view đổi."""
    dang = ["2026-11-15 10:00:00"] * 5 + ["2025-01-01 10:00:00"] * 6
    creators = [f"r{i}" for i in range(5)] + [f"o{i}" for i in range(6)]
    return dung_chuoi([[100] * 11, ky2, [1000, 900, 800, 700, 600] + [100] * 6], dang=dang, creators=creators)


def test_dang_co_da_can_du_mau_o_ca_hai_ky_gan_nhat() -> None:
    thieu = chuoi_du_mau_hai_ky([100] * 5 + [0] * 6)                  # kỳ trước: tập sống chỉ 5 video < 8
    kq = rt.xep_hang_uid(thieu, hom_nay_sau(thieu), "2026-11-20")
    assert kq["tang_dot_ngot"] is True and rt.view_nho_cao(kq["view_nho_trung_vi"], kq["n_creator_nho"]) is True
    assert "THIEU_MAU" not in kq["co"] and kq["xep_loai"] == "chua_co_da"
    assert "kỳ trước chưa đủ mẫu" in kq["ly_do_thieu"]
    du = chuoi_du_mau_hai_ky([100] * 11)
    assert rt.xep_hang_uid(du, hom_nay_sau(du), "2026-11-20")["xep_loai"] == "dang_co_da"


def test_du_lieu_cu_chan_dang_co_da() -> None:
    s = chuoi_dang_co_da()
    kq = rt.xep_hang_uid(s, hom_nay_sau(s, 50), "2026-11-20")
    assert "DU_LIEU_CU" in kq["co"] and kq["xep_loai"] == "chan"


def test_du_mau_dung_chung() -> None:
    base = {"gio": 24.0, "hop_le": True, "n_video": 8, "n_creator": 3, "n_doi": 5, "ti_le_doi": 60.0,
            "trung_vi": 10, "tong_delta_top5": 40, "khong_lam_moi": False, "ds_d24": [], "loai": {}}
    assert rt.du_mau(base) is True
    assert rt.du_mau({**base, "n_video": 7}) is False
    assert rt.du_mau({**base, "n_creator": 2}) is False
    assert rt.du_mau({**base, "hop_le": False}) is False
    assert rt.du_mau({**base, "khong_lam_moi": True}) is False


def test_uu_tien_ha_khi_thieu_mau_qua_7_ngay() -> None:
    s = dung_chuoi([[100] * 7])                                       # 7 video < 8 ⇒ THIEU_MAU
    hn = hom_nay_sau(s)                                               # 21/11
    assert rt.xep_hang_uid(s, hn, "2026-11-14")["uu_tien"] == "ha"    # 21/11 − 14/11 = 7 ngày
    assert rt.xep_hang_uid(s, hn, "2026-11-15")["uu_tien"] == "thuong"
    d = chuoi_dang_co_da()
    assert rt.xep_hang_uid(d, hom_nay_sau(d), "2026-01-01")["uu_tien"] == "thuong"    # không THIEU_MAU ⇒ không hạ


# ---------------------------------------------------------------- phụ: 14 ngày, 30 ngày, bán, creator mới, spark

def test_chi_so_phu_14_ngay_va_video_moi_30() -> None:
    dang = ["2026-11-20 08:00:00"] * 3 + ["2026-10-01 08:00:00"] * 8        # 3 video ≤ 14 ngày; 11 sống (≤ 90 ngày)
    s = dung_chuoi([[900, 300, 600, 10, 20, 30, 40, 50, 60, 70, 80]], dang=dang)
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["n_video_14"] == 3 and kq["trung_vi_14"] == 600
    assert kq["n_video_moi_30"] == 3 and kq["cau_video_moi"] == ""


def test_trung_vi_14_none_khi_khong_video_14_ngay() -> None:
    s = dung_chuoi([[100] * 11], dang="2026-10-01 08:00:00")
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["trung_vi_14"] is None and kq["n_video_14"] == 0


def test_d_ban_ngay_va_creator_moi_ngay() -> None:
    a, b = cap_vi_du_1(48)                                            # kỳ 48 giờ
    b["videos"]["vmoi1"] = hv("vmoi1", "cA", 100, "2026-11-21 10:00:00")        # đăng trong (a, b]
    b["videos"]["vmoi2"] = hv("vmoi2", "cA", 100, "2026-11-21 11:00:00")
    b["videos"]["vmoi3"] = hv("vmoi3", "cB", 100, "2026-11-20 09:00:00")        # trước a ⇒ không tính
    a["ban_tong"], b["ban_tong"] = "1000", "1096"
    kq = rt.xep_hang_uid([a, b], datetime(2026, 11, 22, 12, 0, tzinfo=VN), "2026-11-20")
    assert kq["d_ban_ngay"] == 48.0                                   # 96 / 2 ngày
    assert kq["creator_moi_ngay"] == 0.5                              # 1 creator / 2 ngày
    b["ban_tong"] = "N/A"
    assert rt.xep_hang_uid([a, b], datetime(2026, 11, 22, 12, 0, tzinfo=VN), "2026-11-20")["d_ban_ngay"] is None
    assert (kq["gia"], kq["hoa_hong"], kq["ton"]) == ("499.390₫", "10%", "562")


def test_spark_bay_ky_gan_nhat_cu_den_moi_null_o_ky_khong_hop_le() -> None:
    deltas = [[100 * (k + 1)] * 11 for k in range(9)]                # 10 snapshot, 9 kỳ
    gio = [24.0] * 9
    gio[6] = 60                                                       # kỳ thứ 7 GAP
    s = dung_chuoi(deltas, khoang_gio=gio)
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    # 7 kỳ cuối = kỳ index 2..8: d24 = delta*24/gio
    assert kq["spark"] == [300, 400, 500, 600, None, 800, 900] and kq["trung_vi"] == 900


def test_spark_ngan_khi_it_ky() -> None:
    s = dung_chuoi([[100] * 11, [200] * 11])
    kq = rt.xep_hang_uid(s, hom_nay_sau(s), "2026-11-20")
    assert kq["spark"] == [100, 200]


# ---------------------------------------------------------------- bất biến: id chuỗi, không 0 giả

def test_id_19_so_luon_la_chuoi() -> None:
    a = snap(T0, [hv("7290000000000000001", "c1", 100), hv("7290000000000000002", "c2", 100)])
    b = snap(T0 + timedelta(hours=24), [hv("7290000000000000001", "c1", 150), hv("7290000000000000002", "c2", 160)])
    ky = rt.tinh_ky(a, b)
    assert {v for v, _, _ in ky["ds_d24"]} == {"7290000000000000001", "7290000000000000002"}
    assert all(isinstance(v, str) for v, _, _ in ky["ds_d24"])


def test_view_khong_doc_duoc_khong_bien_thanh_0() -> None:
    a = snap(T0, [hv("x1", "c1", "N/A"), hv("x2", "c2", 100)])
    b = snap(T0 + timedelta(hours=24), [hv("x1", "c1", 500), hv("x2", "c2", 130)])
    ky = rt.tinh_ky(a, b)
    assert [v for v, _, _ in ky["ds_d24"]] == ["x2"] and ky["n_video"] == 1


def test_khong_co_video_chung_thi_khong_co_so() -> None:
    a = snap(T0, [hv("x1", "c1", 100)])
    b = snap(T0 + timedelta(hours=24), [hv("x2", "c2", 100)])
    ky = rt.tinh_ky(a, b)
    assert ky["n_video"] == 0 and ky["trung_vi"] is None and ky["tong_delta_top5"] is None and ky["ti_le_doi"] is None


def test_lay_luc_hong_thi_nem_loi_khong_nuot() -> None:
    a = snap(T0, [hv("x1", "c1", 100)])
    b = snap(T0 + timedelta(hours=24), [hv("x1", "c1", 100)])
    b["lay_luc"] = "khong-phai-gio"
    with pytest.raises(ValueError):
        rt.tinh_ky(a, b)


def test_delta_am_van_tinh_vao_trung_vi_nhung_khong_vao_top5() -> None:
    a = snap(T0, [hv("a", "c1", 1000), hv("b", "c2", 1000), hv("c", "c3", 1000)])
    b = snap(T0 + timedelta(hours=24), [hv("a", "c1", 900), hv("b", "c2", 800), hv("c", "c3", 1300)], cap="y")
    ky = rt.tinh_ky(a, b)
    assert sorted(d for _, _, d in ky["ds_d24"]) == [-200, -100, 300]
    assert ky["trung_vi"] == -100 and ky["tong_delta_top5"] == 300


def test_video_cu_dung_yen_khong_keo_trung_vi_ve_0() -> None:
    """§2.3.4: catalog cũ đứng yên (đăng > 90 ngày, view không đổi) nằm ngoài tập "đang sống"."""
    vs_a = [hv(f"n{i}", f"c{i}", 1000) for i in range(3)] + [hv(f"o{i}", f"k{i}", 5000, "2024-01-01 10:00:00") for i in range(20)]
    vs_b = [hv(f"n{i}", f"c{i}", 1000 + 100 * (i + 1)) for i in range(3)] + [hv(f"o{i}", f"k{i}", 5000, "2024-01-01 10:00:00") for i in range(20)]
    ky = rt.tinh_ky(snap(T0, vs_a), snap(T0 + timedelta(hours=24), vs_b, cap="y"))
    assert ky["n_video"] == 3 and ky["trung_vi"] == 200 and ky["n_doi"] == 3
    assert ky["ti_le_doi"] == pytest.approx(13.0, abs=0.05)           # 3/23
