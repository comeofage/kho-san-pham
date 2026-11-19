"""Test hạn mức — chạy: python -B -m pytest tools/test_runner_han_muc.py -q"""
import base64
import hashlib
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from runner import han_muc  # noqa: E402
from runner.han_muc import HAN_MUC_TRAN, TRAN_LUOT, WM_CHO_PHEP, han_muc_hieu_luc, kiem_han_muc  # noqa: E402
from runner.kho_viec import KhoViec  # noqa: E402
from runner.kieu import ThamSoLoi, VuotHanMuc  # noqa: E402


@pytest.fixture(autouse=True)
def _du_lieu_tam(tmp_path, monkeypatch):
    monkeypatch.setenv("KHO_RUNNER_DIR", str(tmp_path))


@pytest.fixture
def kho(tmp_path):
    return KhoViec(tmp_path / "runner.db", lambda: datetime(2026, 11, 17, 9, 0, 0))


def test_hang_so_dung_tai_lieu():
    assert HAN_MUC_TRAN == {
        "dot_bat": 5, "claude_usd_ngay": 40, "claude_viec_ngay": 12,
        "viec_tao_ngay_moi_nguoi": 30, "con_toi_da_xu_ly_link": 5,
        "muse_clip_moi_viec": 10, "muse_clip_ngay": 15,
        "genmax_ban_moi_viec": 25, "genmax_viec_ngay": 2,
        "poster_len_lich_ngay": 2, "poster_video_ngay_toi_da": 100,
        "taovideo_ngay": 10, "codex_luot_viec": 6,
        "taovideo_usd_viec": 60, "taovideo_mp3_viec": 25, "taovideo_lan_ngay": 10,
        "sua_video_ngay": 60,
    }
    assert TRAN_LUOT == {"radar_ban_tin": 40, "phan_tich_uid": 250, "muse_clip": 120,
                         "poster_len_lich": 60, "taovideo": 1500}
    assert WM_CHO_PHEP == ("nha.cua.mit",)          # người dùng chốt (D11): nha.cua.mit hoặc không watermark
    assert han_muc.HET_GIO_TAOVIDEO == {"lam_s": 8 * 3600, "cho_s": 3 * 3600, "nen_s": 4 * 3600,
                                        "tong_s": 24 * 3600}


def test_hieu_luc_rong_bang_tran():
    hm, cb = han_muc_hieu_luc({})
    assert hm == HAN_MUC_TRAN and cb == []
    assert hm is not HAN_MUC_TRAN


def test_file_chi_duoc_ha_khong_duoc_noi():
    hm, cb = han_muc_hieu_luc({"claude_usd_ngay": 10, "claude_viec_ngay": 99, "dot_bat": 6,
                               "muse_clip_ngay": 15})
    assert hm["claude_usd_ngay"] == 10
    assert hm["claude_viec_ngay"] == 12 and hm["dot_bat"] == 5 and hm["muse_clip_ngay"] == 15
    assert any("claude_viec_ngay" in c for c in cb) and any("dot_bat" in c for c in cb)


@pytest.mark.parametrize("gia_tri", [True, "5", None, -1, float("nan"), float("inf"), [1]])
def test_gia_tri_hong_bi_bo(gia_tri):
    hm, cb = han_muc_hieu_luc({"claude_viec_ngay": gia_tri})
    assert hm["claude_viec_ngay"] == 12 and len(cb) == 1


def test_khoa_la_bi_bo_va_canh_bao():
    hm, cb = han_muc_hieu_luc({"tran_moi": 100})
    assert "tran_moi" not in hm and len(cb) == 1


def test_file_khong_phai_dict():
    hm, cb = han_muc_hieu_luc(["x"])  # type: ignore[arg-type]
    assert hm == HAN_MUC_TRAN and len(cb) == 1


def test_dot_bat_5_mo_taovideo_va_ha_duoc_ve_4():
    """B-4: người dùng ĐÃ đồng ý mở đợt 5 (D11 "Cho sửa + mở đợt 5") → trần code dot_bat = 5, mở taovideo.
    sua_video/hoan_tac_sua vẫn dot=4. cau_hinh.json hạ dot_bat = 4 thì taovideo đóng lại."""
    from runner.danh_muc import DANH_MUC, lay_loai
    assert HAN_MUC_TRAN["dot_bat"] == 5
    for ma in ("sua_video", "hoan_tac_sua"):
        assert lay_loai(ma, int(HAN_MUC_TRAN["dot_bat"])).dot == 4
    assert lay_loai("taovideo", int(HAN_MUC_TRAN["dot_bat"])).dot == 5
    hm4, cb = han_muc_hieu_luc({"dot_bat": 4})
    assert hm4["dot_bat"] == 4 and cb == []
    with pytest.raises(ThamSoLoi):
        lay_loai("taovideo", int(hm4["dot_bat"]))
    assert DANH_MUC["taovideo"].dot == HAN_MUC_TRAN["dot_bat"]


# ---------- đợt 5: taovideo (§7.5, §7.7) ----------

def test_het_gio_taovideo_chi_duoc_ha():
    f = han_muc.het_gio_taovideo
    assert f({}) == han_muc.HET_GIO_TAOVIDEO and f({}) is not han_muc.HET_GIO_TAOVIDEO
    assert f({"taovideo_cho_s": 60, "taovideo_lam_s": 10 ** 9})["cho_s"] == 60
    assert f({"taovideo_lam_s": 10 ** 9})["lam_s"] == 8 * 3600                     # nới → bỏ
    for hong in (True, "60", -1, float("nan"), 0, None):
        assert f({"taovideo_nen_s": hong})["nen_s"] == 4 * 3600
    assert f("rac") == han_muc.HET_GIO_TAOVIDEO                                     # type: ignore[arg-type]
    # cau_hinh.json được hạ đồng hồ (khoá taovideo_<tên>), không được nới
    hm, cb = han_muc_hieu_luc({"taovideo_cho_s": 1800, "taovideo_tong_s": 10 ** 6})
    assert f(hm)["cho_s"] == 1800 and f(hm)["tong_s"] == 24 * 3600 and len(cb) == 1
    assert han_muc_hieu_luc({"taovideo_usd_viec": 30})[0]["taovideo_usd_viec"] == 30
    assert han_muc_hieu_luc({"taovideo_usd_viec": 61})[0]["taovideo_usd_viec"] == 60


def test_tran_taovideo_hieu_luc():
    """FX-28 (R-22 P3-1): trần của MỘT lần duyệt taovideo theo hiệu lực (cau_hinh chỉ hạ)."""
    f = han_muc.tran_taovideo
    assert f({}) == {"usd": 60, "mp3": 25, "codex": 6, "gio": 8}
    hm, _ = han_muc_hieu_luc({"taovideo_usd_viec": 30, "taovideo_mp3_viec": 10, "codex_luot_viec": 2,
                              "taovideo_lam_s": 2 * 3600 + 1800})
    assert f(hm) == {"usd": 30, "mp3": 10, "codex": 2, "gio": 2.5}
    # hm bị nới / hỏng → vẫn không vượt trần code
    assert f({"taovideo_usd_viec": 999, "codex_luot_viec": True, "taovideo_mp3_viec": -1}) == f({})
    assert f("rac") == f({})                                                       # type: ignore[arg-type]


def test_han_muc_tu_thu_muc(tmp_path):
    """Đọc cau_hinh.json của thư mục runner giống chay_runner (utf-8-sig, thiếu → trần, hỏng → trần + cảnh báo)."""
    f = han_muc.han_muc_tu_thu_muc
    hm, cb = f(tmp_path)
    assert hm == HAN_MUC_TRAN and cb == []
    (tmp_path / "cau_hinh.json").write_text('﻿{"codex_luot_viec": 3, "taovideo_usd_viec": 99}',
                                            encoding="utf-8")
    hm, cb = f(tmp_path)
    assert hm["codex_luot_viec"] == 3 and hm["taovideo_usd_viec"] == 60 and len(cb) == 1
    (tmp_path / "cau_hinh.json").write_text("{hỏng", encoding="utf-8")
    hm, cb = f(tmp_path)
    assert hm == HAN_MUC_TRAN and cb and "hỏng" in cb[0]


TV = {"uid": "1" * 19, "du_an_a": "abcdef012345", "du_an_b": "fedcba543210", "wm": "khong"}


def test_taovideo_viec_thu_2_cung_ngay_bi_chan_o_tao(kho):
    """taovideo_ngay = 1 VIỆC/ngày (đếm việc, không đếm lần tiêu) khi cau_hinh hạ trần từ 10 xuống 1."""
    hm, _ = han_muc_hieu_luc({"taovideo_ngay": 1})
    kiem_han_muc(kho, "taovideo", TV, hm, "tao", "nhan")
    kho.tao("taovideo", "1" * 19, TV, "gpu", "cho_duyet", "nhan")
    with pytest.raises(VuotHanMuc, match="việc"):
        kiem_han_muc(kho, "taovideo", dict(TV, uid="2" * 19), hm, "tao", "comeofage")
    # việc bị từ chối khi chưa duyệt (chưa tốn gì) → không tính nữa
    v = kho.ds()[0]
    kho.chuyen(v["id"], ["cho_duyet"], "huy", "nhan", "từ chối duyệt")
    kiem_han_muc(kho, "taovideo", dict(TV, uid="2" * 19), hm, "tao", "comeofage")


def test_taovideo_duyet_lai_lan_2_qua_lan_4_bi_chan(kho):
    """taovideo_lan_ngay = 3 lần tiêu/ngày (cau_hinh hạ từ 10); duyệt lại cùng việc KHÔNG bị taovideo_ngay chặn."""
    hm, _ = han_muc_hieu_luc({"taovideo_ngay": 1, "taovideo_lan_ngay": 3})
    a = kho.tao("taovideo", "1" * 19, TV, "gpu", "cho_duyet", "nhan")
    kiem_han_muc(kho, "taovideo", TV, hm, "duyet", "nhan", viec_id=a["id"])
    _duyet(kho, a["id"])
    kiem_han_muc(kho, "taovideo", {}, hm, "nhan", "he_thong", viec_id=a["id"])
    _tieu(kho, a["id"])                                                      # lần tiêu 1
    for lan in (2, 3):
        kho.chuyen(a["id"], ["cho"], "loi", "he_thong", loi="bị ngắt")
        _xin_duyet_lai(kho, a["id"])
        kiem_han_muc(kho, "taovideo", TV, hm, "duyet", "nhan", viec_id=a["id"])   # lần 2, 3: qua
        _duyet(kho, a["id"])
        kiem_han_muc(kho, "taovideo", {}, hm, "nhan", "he_thong", viec_id=a["id"])
        _tieu(kho, a["id"], goc=f"L{lan}")
    kho.chuyen(a["id"], ["cho"], "loi", "he_thong", loi="bị ngắt")
    _xin_duyet_lai(kho, a["id"])
    with pytest.raises(VuotHanMuc, match="lần"):                              # lần 4 cùng ngày: chặn
        kiem_han_muc(kho, "taovideo", TV, hm, "duyet", "nhan", viec_id=a["id"])
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "taovideo", {}, hm, "nhan", "he_thong", viec_id=a["id"])
    # hạ trần lần/ngày qua cau_hinh
    hm1, _ = han_muc_hieu_luc({"taovideo_lan_ngay": 1})
    b_kho = KhoViec(kho.duong_dan_db.with_name("r_b.db"), kho.bay_gio)
    b = b_kho.tao("taovideo", "1" * 19, TV, "gpu", "cho_duyet", "nhan")
    _duyet(b_kho, b["id"])
    _tieu(b_kho, b["id"])
    b_kho.chuyen(b["id"], ["cho"], "loi", "he_thong", loi="x")
    _xin_duyet_lai(b_kho, b["id"])
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(b_kho, "taovideo", TV, hm1, "duyet", "nhan", viec_id=b["id"])


def test_taovideo_ngay_moi_dat_lai_va_viec_hom_qua_khong_chan(tmp_path):
    kho, luc = _kho_dong_ho(tmp_path, datetime(2026, 11, 17, 9, 0, 0))
    hm, _ = han_muc_hieu_luc({"taovideo_ngay": 1})
    a = kho.tao("taovideo", "1" * 19, TV, "gpu", "cho_duyet", "nhan")
    _duyet(kho, a["id"])
    _tieu(kho, a["id"])
    kho.chuyen(a["id"], ["cho"], "xong", "he_thong")
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "taovideo", dict(TV, uid="2" * 19), hm, "tao", "nhan")
    luc["t"] = datetime(2026, 11, 18, 9, 0, 0)
    kiem_han_muc(kho, "taovideo", dict(TV, uid="2" * 19), hm, "tao", "nhan")


def _sua(kho, loai, i, boi="nhan"):
    return kho.tao(loai, f"{i:016x}", {"ma_video": f"{i:016x}"}, "gpu", "cho", boi)


def test_sua_video_ngay_dem_ca_hai_loai(kho):
    """§7.3: sua_video_ngay đếm việc sua_video + hoan_tac_sua TẠO trong ngày (mọi người, mọi trạng thái)."""
    hm, _ = han_muc_hieu_luc({"sua_video_ngay": 3, "viec_tao_ngay_moi_nguoi": 30})
    kiem_han_muc(kho, "sua_video", {}, hm, "tao", "nhan")
    a = _sua(kho, "sua_video", 1)
    _sua(kho, "hoan_tac_sua", 2, boi="comeofage")
    kho.chuyen(a["id"], ["cho"], "huy", "nhan")           # huỷ vẫn tính (chặn bấm lặp)
    kiem_han_muc(kho, "hoan_tac_sua", {}, hm, "tao", "nhan")
    _sua(kho, "sua_video", 3)
    for loai in ("sua_video", "hoan_tac_sua"):
        with pytest.raises(VuotHanMuc):
            kiem_han_muc(kho, loai, {}, hm, "tao", "nhan")
    # việc khác không bị trần này chặn; lúc nhận không đếm lại (đã tính lúc tạo)
    kiem_han_muc(kho, "voice_pv", {}, hm, "tao", "nhan")
    kiem_han_muc(kho, "sua_video", {}, hm, "nhan", "nhan")


def test_sua_video_ngay_sang_ngay_moi_dat_lai(tmp_path):
    luc = {"t": datetime(2026, 11, 17, 23, 0, 0)}
    kho = KhoViec(tmp_path / "r2.db", lambda: luc["t"])
    hm, _ = han_muc_hieu_luc({"sua_video_ngay": 1})
    _sua(kho, "sua_video", 1)
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "sua_video", {}, hm, "tao", "nhan")
    luc["t"] = datetime(2026, 11, 18, 0, 30, 0)
    kiem_han_muc(kho, "sua_video", {}, hm, "tao", "nhan")


def test_sua_video_ngay_tran_code_khong_noi_duoc(kho):
    hm, cb = han_muc_hieu_luc({"sua_video_ngay": 999})
    assert hm["sua_video_ngay"] == 60 and cb


def test_kiem_han_muc_chan_claude_viec_ngay(kho):
    hm, _ = han_muc_hieu_luc({"claude_viec_ngay": 2})
    for i in range(2):
        v = kho.tao("phan_tich_uid", str(i) * 19, {}, "nhe", "cho", "nhan")
        kho.nhan_viec_ke("nhe", set(), lambda _l: frozenset())
        kho.cong_chi_phi(v["id"], 0.1, 1, True)
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "phan_tich_uid", {}, hm, "nhan", "nhan")
    # việc không dùng Claude không bị chốt này chặn
    kiem_han_muc(kho, "voice_pv", {}, hm, "nhan", "nhan")


def test_kiem_han_muc_claude_usd(kho):
    hm, _ = han_muc_hieu_luc({"claude_usd_ngay": 1})
    v = kho.tao("radar_ban_tin", "2026-11-17", {}, "nhe", "cho", "nhan")
    kho.nhan_viec_ke("nhe", set(), lambda _l: frozenset())
    kiem_han_muc(kho, "radar_ban_tin", {}, hm, "nhan", "nhan")
    kho.cong_chi_phi(v["id"], 1.0, 1, True)
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "radar_ban_tin", {}, hm, "nhan", "nhan")


def test_kiem_han_muc_tao_moi_nguoi(kho):
    hm, _ = han_muc_hieu_luc({"viec_tao_ngay_moi_nguoi": 2})
    kho.tao("phan_tich_uid", "1" * 19, {}, "nhe", "cho", "nhan")
    kiem_han_muc(kho, "phan_tich_uid", {}, hm, "tao", "nhan")
    kho.tao("phan_tich_uid", "2" * 19, {}, "nhe", "cho", "nhan")
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "phan_tich_uid", {}, hm, "tao", "nhan")
    kiem_han_muc(kho, "phan_tich_uid", {}, hm, "tao", "comeofage")


def test_hm_thieu_khoa_hoac_noi_van_dung_tran(kho):
    """hm truyền vào bị sửa nới / thiếu khoá vẫn không vượt trần code."""
    for i in range(12):
        v = kho.tao("phan_tich_uid", f"{i:019d}", {}, "nhe", "cho", "nhan")
        kho.nhan_viec_ke("nhe", set(), lambda _l: frozenset())
        kho.cong_chi_phi(v["id"], 0.0, 1, True)
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "phan_tich_uid", {}, {"claude_viec_ngay": 1000}, "nhan", "nhan")
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "phan_tich_uid", {}, {}, "nhan", "nhan")


def test_kiem_han_muc_tham_so_sai(kho):
    with pytest.raises(ThamSoLoi):
        kiem_han_muc(kho, "phan_tich_uid", {}, dict(HAN_MUC_TRAN), "luc_la", "nhan")
    with pytest.raises(ThamSoLoi):
        kiem_han_muc(kho, "loai_la", {}, dict(HAN_MUC_TRAN), "tao", "nhan")


def test_ngay_theo_gio_vn(tmp_path):
    """00:30 giờ VN ngày 18 vẫn là ngày 18 (bay_gio có múi giờ UTC)."""
    luc = datetime(2026, 11, 17, 17, 30, tzinfo=timezone.utc)  # = 00:30 18/11 giờ VN
    kho = KhoViec(tmp_path / "r.db", lambda: luc)
    assert han_muc.ngay_vn(luc).isoformat() == "2026-11-18"
    kho.tao("phan_tich_uid", "1" * 19, {}, "nhe", "cho", "nhan")
    assert kho.ds()[0]["tao_luc"].startswith("2026-11-18T00:30")


# ---------- đợt 4: hạn mức riêng của loại tốn tiền (B-3, §5.2, §10) ----------
# Quy tắc tính ngày: việc "đã tiêu" = đã duyệt (có duyet_luc) HOẶC còn mở; tính vào ngày duyệt (nếu đã duyệt),
# ngược lại vào ngày tạo. Việc bị từ chối/huỷ/lỗi mà CHƯA duyệt thì không tính (chưa tốn gì).

MA = "abcdef012345"
MUSE = {"uid": "1" * 19, "du_an": MA, "mau": ["xoay_360"], "thoi_luong": 10, "ti_le": "9:16"}
GENMAX = {"uid": "1" * 19, "du_an": MA, "me": "20261117-a", "ma_ban": ["A1", "A2"]}
POSTER = {"folder_id": 7, "so_video_ngay": 3}


def _muse(n: int) -> dict:
    return dict(MUSE, mau=[f"m{i}" for i in range(n)])


def _duyet(kho, id_, luc="2026-11-17T09:00:00+07:00", boi="nhan"):
    return kho.chuyen(id_, ["cho_duyet"], "cho", boi, "duyệt", loi_duyet="ok", duyet_boi=boi, duyet_luc=luc,
                      chu_ky_duyet="x" * 86, buoc="chay")


def test_muse_clip_moi_viec_chan_o_ca_3_luc(kho):
    hm = dict(HAN_MUC_TRAN)
    kiem_han_muc(kho, "muse_clip", _muse(10), hm, "tao", "nhan")
    for luc in ("tao", "duyet", "nhan"):
        with pytest.raises(VuotHanMuc, match="clip"):
            kiem_han_muc(kho, "muse_clip", _muse(11), hm, luc, "nhan")
    hm_ha, _ = han_muc_hieu_luc({"muse_clip_moi_viec": 3})
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "muse_clip", _muse(4), hm_ha, "tao", "nhan")
    # hm bị nới quá trần code vẫn không cho > 10
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "muse_clip", _muse(11), {**HAN_MUC_TRAN, "muse_clip_moi_viec": 99}, "tao", "nhan")


def test_muse_clip_ngay_cong_ca_viec_dang_mo_va_da_duyet(kho):
    hm = dict(HAN_MUC_TRAN)
    a = kho.tao("muse_clip", "a", _muse(8), "nhe", "cho_duyet", "nhan")
    kho.tao("muse_clip", "b", _muse(5), "nhe", "cho_duyet", "comeofage")       # đang mở → tính
    kiem_han_muc(kho, "muse_clip", _muse(2), hm, "tao", "nhan")                 # 8+5+2 = 15
    with pytest.raises(VuotHanMuc, match="15"):
        kiem_han_muc(kho, "muse_clip", _muse(3), hm, "tao", "nhan")             # 16
    # bị từ chối khi chưa duyệt → không tính nữa
    kho.chuyen(a["id"], ["cho_duyet"], "huy", "nhan", "từ chối duyệt")
    kiem_han_muc(kho, "muse_clip", _muse(10), hm, "tao", "nhan")                # 5+10
    # đã duyệt rồi mới huỷ (có thể đã tốn lượt) → vẫn tính
    c = kho.tao("muse_clip", "c", _muse(6), "nhe", "cho_duyet", "nhan")
    _duyet(kho, c["id"])
    kho.chuyen(c["id"], ["cho"], "huy", "nhan", "huỷ")
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "muse_clip", _muse(5), hm, "tao", "nhan")             # 5+6+5 = 16


def test_duyet_khong_tinh_trung_chinh_viec_do(kho):
    hm = dict(HAN_MUC_TRAN)
    kho.tao("muse_clip", "a", _muse(10), "nhe", "cho_duyet", "nhan")
    b = kho.tao("muse_clip", "b", _muse(5), "nhe", "cho_duyet", "nhan")
    kiem_han_muc(kho, "muse_clip", _muse(5), hm, "duyet", "nhan", viec_id=b["id"])   # 10 + 5, không đếm b 2 lần
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "muse_clip", _muse(6), hm, "duyet", "nhan", viec_id=b["id"])


def test_nhan_theo_ngay_duyet(tmp_path):
    """§10 (D9): lúc nhận, việc đang xét luôn cộng so_luong × (so_lan_tieu + 1) vào hôm nay (sắp tiêu hôm nay), kể cả
    khi được duyệt hôm qua — trước D9 việc duyệt hôm qua được bỏ qua và có thể vượt trần ngày khi chạy hôm nay."""
    luc = {"t": datetime(2026, 11, 17, 23, 0, 0)}
    kho = KhoViec(tmp_path / "r.db", lambda: luc["t"])
    hm = dict(HAN_MUC_TRAN)
    a = kho.tao("voice_genmax", "a", GENMAX, "gpu", "cho_duyet", "nhan")
    _duyet(kho, a["id"], luc="2026-11-17T23:00:00+07:00")
    luc["t"] = datetime(2026, 11, 18, 8, 0, 0)
    for k in ("b", "c"):
        v = kho.tao("voice_genmax", k, GENMAX, "gpu", "cho_duyet", "nhan")
        _duyet(kho, v["id"], luc="2026-11-18T08:00:00+07:00")
    # hôm nay đã có 2 (b, c) = trần; a duyệt hôm qua nhưng sẽ tiêu hôm nay → bị chặn
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "voice_genmax", GENMAX, hm, "nhan", "he_thong", viec_id=a["id"])
    kiem_han_muc(kho, "voice_genmax", {}, hm, "nhan", "he_thong")              # cách gọi cũ: tổng hôm nay ≤ trần
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "voice_genmax", GENMAX, hm, "tao", "nhan")
    # hạ trần qua cau_hinh xuống 1 → nhận bị chặn cả 2 cách gọi
    hm1, _ = han_muc_hieu_luc({"genmax_viec_ngay": 1})
    b_id = [v for v in kho.ds() if v["khoa"] == "b"][0]["id"]
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "voice_genmax", GENMAX, hm1, "nhan", "he_thong", viec_id=b_id)
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "voice_genmax", {}, hm1, "nhan", "he_thong")


def test_genmax_ban_moi_viec(kho):
    hm = dict(HAN_MUC_TRAN)
    kiem_han_muc(kho, "voice_genmax", dict(GENMAX, ma_ban=[f"A{i}" for i in range(25)]), hm, "tao", "nhan")
    for luc in ("tao", "duyet", "nhan"):
        with pytest.raises(VuotHanMuc, match="25"):
            kiem_han_muc(kho, "voice_genmax", dict(GENMAX, ma_ban=[f"A{i}" for i in range(26)]), hm, luc, "nhan")


def test_genmax_viec_ngay_tinh_viec_dang_uoc_tinh(kho):
    hm = dict(HAN_MUC_TRAN)
    kho.tao("voice_genmax", "a", GENMAX, "gpu", "cho", "nhan", buoc="uoc_tinh")
    kho.tao("voice_genmax", "b", GENMAX, "gpu", "cho", "nhan", buoc="uoc_tinh")
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "voice_genmax", GENMAX, hm, "tao", "comeofage")
    # pha ước tính xong mà lỗi (chưa duyệt, chưa tốn tiền) → không tính
    v = kho.ds()[0]
    kho.chuyen(v["id"], ["cho"], "loi", "he_thong", loi="x")
    kiem_han_muc(kho, "voice_genmax", GENMAX, hm, "tao", "comeofage")


def test_poster_len_lich(kho):
    hm = dict(HAN_MUC_TRAN)
    kiem_han_muc(kho, "poster_len_lich", dict(POSTER, so_video_ngay=100), hm, "tao", "nhan")
    for luc in ("tao", "duyet", "nhan"):
        with pytest.raises(VuotHanMuc):
            kiem_han_muc(kho, "poster_len_lich", dict(POSTER, so_video_ngay=101), hm, luc, "nhan")
    hm3, _ = han_muc_hieu_luc({"poster_video_ngay_toi_da": 3})
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "poster_len_lich", dict(POSTER, so_video_ngay=4), hm3, "tao", "nhan")
    # cau_hinh không nới được quá trần code 100
    hm_noi, cb = han_muc_hieu_luc({"poster_video_ngay_toi_da": 500})
    assert hm_noi["poster_video_ngay_toi_da"] == 100 and cb
    kho.tao("poster_len_lich", "folder:1", dict(POSTER, folder_id=1), "nhe", "cho_duyet", "nhan")
    kho.tao("poster_len_lich", "folder:2", dict(POSTER, folder_id=2), "nhe", "cho_duyet", "nhan")
    with pytest.raises(VuotHanMuc, match="việc"):                      # vẫn ≤2 việc/ngày
        kiem_han_muc(kho, "poster_len_lich", dict(POSTER, folder_id=3), hm, "tao", "nhan")


def _poster(fid: int, n: int) -> dict:
    return {"folder_id": fid, "so_video_ngay": n}


def test_poster_tong_video_moi_tai_khoan_ngay(kho):
    """Người dùng chốt: tổng so_video_ngay của các việc poster tính vào hôm nay ≤ 100 MỖI TÀI KHOẢN.
    Chưa có trường tài khoản → một folder = một tài khoản (gom theo folder_id)."""
    hm = {**HAN_MUC_TRAN, "poster_len_lich_ngay": 2}
    kho.tao("poster_len_lich", "folder:7", _poster(7, 60), "nhe", "cho_duyet", "nhan")
    kiem_han_muc(kho, "poster_len_lich", _poster(7, 40), hm, "tao", "nhan")                # 60 + 40 = 100
    with pytest.raises(VuotHanMuc, match="100"):
        kiem_han_muc(kho, "poster_len_lich", _poster(7, 41), hm, "tao", "nhan")            # 101 cùng tài khoản
    kiem_han_muc(kho, "poster_len_lich", _poster(9, 100), hm, "tao", "nhan")               # tài khoản khác: riêng
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "poster_len_lich", _poster(7, 41), hm, "duyet", "nhan")
    # hạ trần qua cau_hinh: tổng tài khoản cũng hạ theo
    hm50 = {**hm, "poster_video_ngay_toi_da": 50}
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "poster_len_lich", _poster(7, 1), hm50, "tao", "nhan")           # 60 đã > 50


def test_poster_tong_tai_khoan_khong_dem_trung_va_theo_ngay(tmp_path):
    luc = {"t": datetime(2026, 11, 17, 9, 0, 0)}
    kho = KhoViec(tmp_path / "r.db", lambda: luc["t"])
    hm = dict(HAN_MUC_TRAN)
    a = kho.tao("poster_len_lich", "folder:7", _poster(7, 70), "nhe", "cho_duyet", "nhan")
    b = kho.tao("poster_len_lich", "folder:7b", _poster(7, 30), "nhe", "cho_duyet", "nhan")
    # duyệt a: không đếm a hai lần (70 + 30 = 100)
    kiem_han_muc(kho, "poster_len_lich", _poster(7, 70), hm, "duyet", "nhan", viec_id=a["id"])
    _duyet(kho, a["id"])
    kiem_han_muc(kho, "poster_len_lich", _poster(7, 30), hm, "duyet", "nhan", viec_id=b["id"])
    # nhận a (theo id): tổng hôm nay của tài khoản 7 = 100 → qua; nếu b thành 31 thì không
    kiem_han_muc(kho, "poster_len_lich", {}, hm, "nhan", "he_thong", viec_id=a["id"])
    kiem_han_muc(kho, "poster_len_lich", {}, hm, "nhan", "he_thong")                       # cách gọi cũ
    import sqlite3
    with sqlite3.connect(kho.duong_dan_db) as c:
        c.execute("UPDATE viec SET tham_so=? WHERE id=?", ('{"folder_id":7,"so_video_ngay":31}', b["id"]))
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "poster_len_lich", {}, hm, "nhan", "he_thong", viec_id=a["id"])
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "poster_len_lich", {}, hm, "nhan", "he_thong")
    # hôm sau: việc a đã duyệt hôm qua không ăn tổng hôm nay; b còn mở (tạo hôm qua) cũng thuộc hôm qua
    luc["t"] = datetime(2026, 11, 18, 9, 0, 0)
    kiem_han_muc(kho, "poster_len_lich", _poster(7, 100), hm, "tao", "nhan")


def test_poster_tham_so_hong_trong_db_tinh_chat(kho):
    """so_video_ngay hỏng trong DB → tính bằng trần (100); thiếu folder_id → coi như cùng mọi tài khoản."""
    kho.tao("poster_len_lich", "folder:7", {"folder_id": 7, "so_video_ngay": "hong"}, "nhe", "cho_duyet", "nhan")
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "poster_len_lich", _poster(7, 1), dict(HAN_MUC_TRAN), "tao", "nhan")
    kiem_han_muc(kho, "poster_len_lich", _poster(9, 100), dict(HAN_MUC_TRAN), "tao", "nhan")
    kho2 = KhoViec(kho.duong_dan_db.with_name("r2.db"), kho.bay_gio)
    kho2.tao("poster_len_lich", "x", {"so_video_ngay": 10}, "nhe", "cho_duyet", "nhan")
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho2, "poster_len_lich", _poster(9, 91), dict(HAN_MUC_TRAN), "tao", "nhan")
    kiem_han_muc(kho2, "poster_len_lich", _poster(9, 90), dict(HAN_MUC_TRAN), "tao", "nhan")


def test_khoa_tai_khoan_poster():
    assert han_muc.khoa_tai_khoan_poster({"folder_id": 7, "so_video_ngay": 3}) == "folder:7"
    assert han_muc.khoa_tai_khoan_poster({"folder_id": True}) is None
    assert han_muc.khoa_tai_khoan_poster({}) is None
    assert han_muc.khoa_tai_khoan_poster("rac") is None


def test_ton_tien_thieu_tham_so_luc_tao_duyet_bi_tu_choi(kho):
    for ma in ("muse_clip", "voice_genmax", "poster_len_lich"):
        for luc in ("tao", "duyet"):
            with pytest.raises(ThamSoLoi):
                kiem_han_muc(kho, ma, {}, dict(HAN_MUC_TRAN), luc, "nhan")
    with pytest.raises(ThamSoLoi):
        kiem_han_muc(kho, "muse_clip", dict(MUSE, mau="xoay_360"), dict(HAN_MUC_TRAN), "tao", "nhan")
    with pytest.raises(ThamSoLoi):
        kiem_han_muc(kho, "poster_len_lich", dict(POSTER, so_video_ngay=True), dict(HAN_MUC_TRAN), "tao", "nhan")


def test_tham_so_hong_trong_db_tinh_bang_tran(kho):
    """Dữ liệu cũ/hỏng trong DB không được làm hụt bộ đếm: mau hỏng → tính bằng trần mỗi việc (10)."""
    kho.tao("muse_clip", "a", dict(MUSE, mau="hong"), "nhe", "cho_duyet", "nhan")
    kiem_han_muc(kho, "muse_clip", _muse(5), dict(HAN_MUC_TRAN), "tao", "nhan")
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "muse_clip", _muse(6), dict(HAN_MUC_TRAN), "tao", "nhan")


def test_duyet_luc_hong_thi_tinh_theo_ngay_tao(kho):
    a = kho.tao("voice_genmax", "a", GENMAX, "gpu", "cho_duyet", "nhan")
    _duyet(kho, a["id"], luc="khong-phai-ngay")
    kho.tao("voice_genmax", "b", GENMAX, "gpu", "cho_duyet", "nhan")
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "voice_genmax", GENMAX, dict(HAN_MUC_TRAN), "tao", "nhan")


# ---------- §10 (D9): đếm theo số lần tiêu ----------

def _ky(nhan: str) -> str:
    """Chuỗi chữ ký base64url CHUẨN (86 ký tự, 64 byte) sinh tất định — sổ đã tiêu chỉ nhận dạng chuẩn (R-15 P1-1)."""
    return base64.urlsafe_b64encode(hashlib.sha512(nhan.encode("utf-8")).digest()).rstrip(b"=").decode("ascii")


def _tieu(kho, id_, n=1, goc="T"):
    for i in range(n):
        kho.ghi_tieu(id_, _ky(f"{goc}{id_}{i}"))


def test_so_luong_ngay_nhan_so_lan_tieu():
    assert han_muc.so_luong_ngay("muse_clip", _muse(4)) == 4
    assert han_muc.so_luong_ngay("muse_clip", _muse(4), 0) == 4
    assert han_muc.so_luong_ngay("muse_clip", _muse(4), 3) == 12
    assert han_muc.so_luong_ngay("voice_genmax", GENMAX, 2) == 2
    assert han_muc.so_luong_ngay("voice_genmax", GENMAX, "rac") == 1      # hỏng → coi như 0 lần (×1)


def test_ngay_tinh_han_muc_uu_tien_tieu_luc_dau():
    f = han_muc.ngay_tinh_han_muc
    from datetime import date
    assert f({"tieu_luc_dau": "2026-11-15T10:00:00+07:00", "duyet_luc": "2026-11-16T10:00:00+07:00",
              "tao_luc": "2026-11-14T10:00:00+07:00", "so_lan_tieu": 1, "trang_thai": "loi"}) == date(2026, 11, 15)
    # xin duyệt lại xoá duyet_luc nhưng việc đã tiêu vẫn bị tính (không "quên" lần tốn tiền)
    assert f({"tieu_luc_dau": "2026-11-15T10:00:00+07:00", "duyet_luc": None, "so_lan_tieu": 1,
              "tao_luc": "2026-11-14T10:00:00+07:00", "trang_thai": "loi"}) == date(2026, 11, 15)
    assert f({"so_lan_tieu": 0, "duyet_luc": None, "tao_luc": "2026-11-14T10:00:00+07:00",
              "trang_thai": "loi"}) is None


def test_muse_da_tieu_1_lan_duyet_lai_10_clip_vuot_15(kho):
    hm = dict(HAN_MUC_TRAN)
    a = kho.tao("muse_clip", "a", _muse(10), "nhe", "cho_duyet", "nhan")
    _duyet(kho, a["id"])
    _tieu(kho, a["id"])
    # xin duyệt lại (xoá 4 trường duyệt) rồi duyệt lại cùng 10 clip: 10 × (1 + 1) = 20 > 15
    kho.chuyen(a["id"], ["cho"], "loi", "he_thong", loi="x")
    kho.chuyen(a["id"], ["loi"], "cho_duyet", "nhan", "xin duyệt lại", loi_duyet=None, duyet_boi=None,
               duyet_luc=None, chu_ky_duyet=None)
    with pytest.raises(VuotHanMuc, match="15"):
        kiem_han_muc(kho, "muse_clip", _muse(10), hm, "duyet", "nhan", viec_id=a["id"])
    # việc 5 clip đã tiêu 1 lần + duyệt lại → 10 ≤ 15 qua
    b = kho.tao("muse_clip", "b", _muse(5), "nhe", "cho_duyet", "nhan")
    kho.chuyen(a["id"], ["cho_duyet"], "huy", "nhan", "huỷ")          # a vẫn tính 10 (đã tiêu) → 10 + 5×1 = 15
    kiem_han_muc(kho, "muse_clip", _muse(5), hm, "duyet", "nhan", viec_id=b["id"])
    _duyet(kho, b["id"])
    _tieu(kho, b["id"])                                                  # b đã tiêu 1: nhận lần 2 → 10 + 5×2 = 20
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "muse_clip", {}, hm, "nhan", "he_thong", viec_id=b["id"])


def test_viec_khac_tieu_nhieu_lan_dem_theo_lan_tieu(kho):
    hm = dict(HAN_MUC_TRAN)
    a = kho.tao("voice_genmax", "a", GENMAX, "gpu", "cho_duyet", "nhan")
    _duyet(kho, a["id"])
    _tieu(kho, a["id"], 2)                                               # 2 lần tiêu = 2 việc/ngày = trần
    kho.chuyen(a["id"], ["cho"], "xong", "he_thong")
    with pytest.raises(VuotHanMuc, match="2"):
        kiem_han_muc(kho, "voice_genmax", GENMAX, hm, "tao", "nhan")
    assert han_muc.da_dung_ngay(kho, "voice_genmax", han_muc.ngay_vn(kho.bay_gio())) == 2


def test_poster_viec_tieu_nhieu_lan_chi_tinh_video_mot_lan(kho):
    """Chạy lại cùng lịch không tăng số video/ngày; nhưng số việc/ngày đếm theo lần tiêu."""
    hm = dict(HAN_MUC_TRAN)
    a = kho.tao("poster_len_lich", "folder:7", _poster(7, 60), "nhe", "cho_duyet", "nhan")
    _duyet(kho, a["id"])
    _tieu(kho, a["id"], 1)
    kiem_han_muc(kho, "poster_len_lich", _poster(7, 40), hm, "tao", "nhan")         # 60 + 40 video; 1 + 1 việc
    with pytest.raises(VuotHanMuc, match="video"):
        kiem_han_muc(kho, "poster_len_lich", _poster(7, 41), hm, "tao", "nhan")
    _tieu(kho, a["id"], 1, goc="U")                                                  # tiêu lần 2: video vẫn 60
    assert han_muc.video_poster_tai_khoan_ngay(kho, "folder:7", han_muc.ngay_vn(kho.bay_gio())) == 60
    with pytest.raises(VuotHanMuc, match="việc"):                                    # nhưng 2 lần tiêu = 2 việc
        kiem_han_muc(kho, "poster_len_lich", _poster(9, 1), hm, "tao", "nhan")


# ---------- R-15 P2-1: mỗi LẦN TIÊU tính vào ngày của chính lần đó ----------

def _kho_dong_ho(tmp_path, bat_dau: datetime):
    luc = {"t": bat_dau}
    return KhoViec(tmp_path / "r.db", lambda: luc["t"]), luc


def _xin_duyet_lai(kho, id_):
    kho.chuyen(id_, ["loi"], "cho_duyet", "nhan", "xin duyệt lại", loi_duyet=None, duyet_boi=None,
               duyet_luc=None, chu_ky_duyet=None)


def test_genmax_chay_lai_ngay_sau_tinh_vao_ngay_chay_lai(tmp_path):
    """Reviewer: GenMax A tiêu ngày 16, chạy lại ngày 17 cùng B, C → không được thành 3 lần ngày 17 > trần 2."""
    kho, luc = _kho_dong_ho(tmp_path, datetime(2026, 11, 16, 9, 0, 0))
    hm = dict(HAN_MUC_TRAN)
    a = kho.tao("voice_genmax", "a", GENMAX, "gpu", "cho_duyet", "nhan")
    _duyet(kho, a["id"], luc="2026-11-16T09:00:00+07:00")
    kiem_han_muc(kho, "voice_genmax", {}, hm, "nhan", "he_thong", viec_id=a["id"])
    _tieu(kho, a["id"])                                               # lần tiêu 1: ngày 16
    kho.chuyen(a["id"], ["cho"], "loi", "he_thong", loi="x")
    luc["t"] = datetime(2026, 11, 17, 9, 0, 0)
    _xin_duyet_lai(kho, a["id"])
    kiem_han_muc(kho, "voice_genmax", GENMAX, hm, "duyet", "nhan", viec_id=a["id"])
    _duyet(kho, a["id"], luc="2026-11-17T09:00:00+07:00")
    kiem_han_muc(kho, "voice_genmax", {}, hm, "nhan", "he_thong", viec_id=a["id"])
    _tieu(kho, a["id"], goc="U")                                      # lần tiêu 2: ngày 17
    assert han_muc.da_dung_ngay(kho, "voice_genmax", date(2026, 11, 16)) == 1
    assert han_muc.da_dung_ngay(kho, "voice_genmax", date(2026, 11, 17)) == 1
    kiem_han_muc(kho, "voice_genmax", GENMAX, hm, "tao", "nhan")       # B: A(17) + B = 2
    b = kho.tao("voice_genmax", "b", GENMAX, "gpu", "cho_duyet", "nhan")
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "voice_genmax", GENMAX, hm, "tao", "nhan")   # C: A(17) + B + C = 3 > 2
    kho.tao("voice_genmax", "c", GENMAX, "gpu", "cho_duyet", "comeofage")   # (chen qua đường khác)
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "voice_genmax", GENMAX, hm, "duyet", "nhan", viec_id=b["id"])
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "voice_genmax", {}, hm, "nhan", "he_thong")  # cách gọi cũ: tổng ngày 17 = 3 > 2


def test_muse_da_tieu_hom_truoc_chay_lai_hom_sau_khong_bi_chan_oan(tmp_path):
    """Reviewer: Muse 10 clip đã tiêu 1 lần (ngày 16) — trước đây 10 × (1 + 1) = 20 > 15 nên bị chặn VĨNH VIỄN mọi
    ngày sau. Đúng: ngày 17 chỉ cộng 1 lần sắp tiêu (10 ≤ 15); tiêu lần thứ hai CÙNG ngày 17 mới bị chặn."""
    kho, luc = _kho_dong_ho(tmp_path, datetime(2026, 11, 16, 9, 0, 0))
    hm = dict(HAN_MUC_TRAN)
    a = kho.tao("muse_clip", "a", _muse(10), "nhe", "cho_duyet", "nhan")
    _duyet(kho, a["id"], luc="2026-11-16T09:00:00+07:00")
    _tieu(kho, a["id"])
    kho.chuyen(a["id"], ["cho"], "loi", "he_thong", loi="x")
    luc["t"] = datetime(2026, 11, 17, 9, 0, 0)
    _xin_duyet_lai(kho, a["id"])
    kiem_han_muc(kho, "muse_clip", _muse(10), hm, "duyet", "nhan", viec_id=a["id"])
    _duyet(kho, a["id"], luc="2026-11-17T09:00:00+07:00")
    kiem_han_muc(kho, "muse_clip", {}, hm, "nhan", "he_thong", viec_id=a["id"])
    kiem_han_muc(kho, "muse_clip", {}, hm, "nhan", "he_thong")
    _tieu(kho, a["id"], goc="U")                                      # tiêu ngày 17
    kho.chuyen(a["id"], ["cho"], "loi", "he_thong", loi="x")
    _xin_duyet_lai(kho, a["id"])
    with pytest.raises(VuotHanMuc, match="15"):                       # cùng ngày 17: 10 + 10 = 20 > 15
        kiem_han_muc(kho, "muse_clip", _muse(10), hm, "duyet", "nhan", viec_id=a["id"])
    with pytest.raises(VuotHanMuc):                                   # việc khác ngày 17: 10 + 6 > 15
        kiem_han_muc(kho, "muse_clip", _muse(6), hm, "tao", "nhan")
    luc["t"] = datetime(2026, 11, 18, 9, 0, 0)
    kiem_han_muc(kho, "muse_clip", _muse(10), hm, "duyet", "nhan", viec_id=a["id"])   # ngày 18: lại được


def test_so_cuc_bo_mat_dong_van_dem_theo_so_lan_tieu(kho):
    """Dòng da_tieu bị xoá/thiếu (sổ hỏng) → phần thiếu so với so_lan_tieu vẫn tính, vào ngày tieu_luc_dau."""
    a = kho.tao("voice_genmax", "a", GENMAX, "gpu", "cho_duyet", "nhan")
    _duyet(kho, a["id"])
    _tieu(kho, a["id"], 2)
    kho.chuyen(a["id"], ["cho"], "xong", "he_thong")
    with sqlite3.connect(kho.duong_dan_db) as c:
        c.execute("DELETE FROM da_tieu")
    assert han_muc.da_dung_ngay(kho, "voice_genmax", han_muc.ngay_vn(kho.bay_gio())) == 2
    with pytest.raises(VuotHanMuc):
        kiem_han_muc(kho, "voice_genmax", GENMAX, dict(HAN_MUC_TRAN), "tao", "nhan")


def test_danh_dau_da_tieu_409_tinh_la_mot_lan_tieu(kho):
    """Worker báo lời duyệt đã tiêu (409) → dòng sổ ghi bù cũng tính là một lần tốn tiền (thiên về chặt)."""
    a = kho.tao("voice_genmax", "a", GENMAX, "gpu", "cho_duyet", "nhan")
    _duyet(kho, a["id"])
    kho.danh_dau_da_tieu(_ky("409"), a["id"])
    kho.chuyen(a["id"], ["cho"], "loi", "he_thong", loi="da_dung")
    assert han_muc.da_dung_ngay(kho, "voice_genmax", han_muc.ngay_vn(kho.bay_gio())) == 1


def test_ngay_cac_lan_tieu():
    f = han_muc.ngay_cac_lan_tieu
    v = {"so_lan_tieu": 2, "tieu_luc_dau": "2026-11-15T10:00:00+07:00", "tao_luc": "2026-11-14T10:00:00+07:00"}
    assert f(v, ["2026-11-15T10:00:00+07:00", "2026-11-16T23:59:59+07:00"]) == [date(2026, 11, 15), date(2026, 11, 16)]
    assert f(v, ["2026-11-16T10:00:00+07:00"]) == [date(2026, 11, 16), date(2026, 11, 15)]    # thiếu 1 → bù
    assert f(v, []) == [date(2026, 11, 15)] * 2
    assert f(v, ["hong", "2026-11-16T10:00:00+07:00"]) == [date(2026, 11, 15), date(2026, 11, 16)]  # hỏng → dự phòng
    assert f({"so_lan_tieu": 0, "tao_luc": "2026-11-14T10:00:00+07:00"}, []) == []
    assert f({"so_lan_tieu": 0, "tao_luc": "2026-11-14T10:00:00+07:00"}, ["2026-11-14T23:00:00+07:00"]) == \
        [date(2026, 11, 14)]
