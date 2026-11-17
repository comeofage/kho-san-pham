"""Test hạn mức — chạy: python -B -m pytest tools/test_runner_han_muc.py -q"""
import sys
from datetime import datetime, timezone
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
        "dot_bat": 3, "claude_usd_ngay": 40, "claude_viec_ngay": 12,
        "viec_tao_ngay_moi_nguoi": 30, "con_toi_da_xu_ly_link": 5,
        "muse_clip_moi_viec": 10, "muse_clip_ngay": 15,
        "genmax_ban_moi_viec": 25, "genmax_viec_ngay": 2,
        "poster_len_lich_ngay": 2, "poster_video_ngay_toi_da": 5,
        "taovideo_ngay": 1, "codex_luot_viec": 6,
    }
    assert TRAN_LUOT == {"radar_ban_tin": 40, "phan_tich_uid": 250, "muse_clip": 120,
                         "poster_len_lich": 60, "taovideo": 1500}
    assert WM_CHO_PHEP == ()


def test_hieu_luc_rong_bang_tran():
    hm, cb = han_muc_hieu_luc({})
    assert hm == HAN_MUC_TRAN and cb == []
    assert hm is not HAN_MUC_TRAN


def test_file_chi_duoc_ha_khong_duoc_noi():
    hm, cb = han_muc_hieu_luc({"claude_usd_ngay": 10, "claude_viec_ngay": 99, "dot_bat": 5,
                               "muse_clip_ngay": 15})
    assert hm["claude_usd_ngay"] == 10
    assert hm["claude_viec_ngay"] == 12 and hm["dot_bat"] == 3 and hm["muse_clip_ngay"] == 15
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
