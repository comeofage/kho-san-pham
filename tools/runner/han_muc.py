"""Hạn mức (D5, docs/bo-chay-viec.md §10, §6.3).

Trần là HẰNG SỐ trong code. cau_hinh.json chỉ được HẠ: hieu_luc = min(tran_code, gia_tri_file).
Muốn nới phải sửa code và cài lại (có duyệt).
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from .kieu import ThamSoLoi, VuotHanMuc, gio_vn

if TYPE_CHECKING:
    from .kho_viec import KhoViec

HAN_MUC_TRAN: dict[str, int | float] = {
    "dot_bat": 3,                       # đợt cao nhất được mở; tăng = sửa code + cài lại (có duyệt)
    "claude_usd_ngay": 40, "claude_viec_ngay": 12,
    "viec_tao_ngay_moi_nguoi": 30, "con_toi_da_xu_ly_link": 5,
    "muse_clip_moi_viec": 10, "muse_clip_ngay": 15,
    "genmax_ban_moi_viec": 25, "genmax_viec_ngay": 2,
    "poster_len_lich_ngay": 2, "poster_video_ngay_toi_da": 5,
    "taovideo_ngay": 1, "codex_luot_viec": 6,
}
TRAN_LUOT: dict[str, int] = {"radar_ban_tin": 40, "phan_tich_uid": 250, "muse_clip": 120,
                             "poster_len_lich": 60, "taovideo": 1500}
WM_CHO_PHEP: tuple[str, ...] = ()     # đợt 5 điền theo người dùng

LUC_KIEM = ("tao", "duyet", "nhan")
_KHOA_SO_NGUYEN = frozenset(k for k, v in HAN_MUC_TRAN.items() if isinstance(v, int))


def ngay_vn(dt: datetime) -> date:
    return gio_vn(dt).date()


def _la_so_hop_le(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0


def han_muc_hieu_luc(cau_hinh_file: dict) -> tuple[dict, list[str]]:
    """(giá trị hiệu lực, cảnh báo). Chỉ nhận giá trị số ≥ 0 và ≤ trần; còn lại bỏ + cảnh báo."""
    hm: dict[str, int | float] = dict(HAN_MUC_TRAN)
    canh_bao: list[str] = []
    if not isinstance(cau_hinh_file, dict):
        return hm, ["cau_hinh.json không phải object — bỏ qua, dùng trần trong code"]
    for k, v in cau_hinh_file.items():
        if k not in HAN_MUC_TRAN:
            canh_bao.append(f"cau_hinh.json: khoá lạ {k!r} — bỏ qua")
            continue
        if not _la_so_hop_le(v):
            canh_bao.append(f"cau_hinh.json: {k} = {v!r} không phải số ≥ 0 — bỏ qua")
            continue
        tran = HAN_MUC_TRAN[k]
        if v > tran:
            canh_bao.append(f"cau_hinh.json: {k} = {v} vượt trần code {tran} — bỏ qua (file chỉ được hạ)")
            continue
        hm[k] = int(v) if k in _KHOA_SO_NGUYEN else v
    return hm, canh_bao


def _gia_tri(hm: dict, k: str) -> int | float:
    """Phòng thủ: hm truyền vào bị nới/thiếu khoá/hỏng vẫn không vượt trần code."""
    tran = HAN_MUC_TRAN[k]
    v = hm.get(k, tran) if isinstance(hm, dict) else tran
    return min(v, tran) if _la_so_hop_le(v) else tran


def kiem_han_muc(kho: "KhoViec", ma_loai: str, tham_so: dict, hm: dict, luc: str, boi: str) -> None:
    """Raise VuotHanMuc nếu vượt. luc ∈ tao|duyet|nhan (nhan gồm cả chay-tiep).

    Đợt 3 kiểm:
    - tao: số việc người `boi` tạo trong ngày VN < viec_tao_ngay_moi_nguoi.
    - duyet/nhan, loại dùng Claude: tổng USD hôm nay < claude_usd_ngay; số job Claude hôm nay < claude_viec_ngay.
    Hạn mức riêng của đợt 4–5 (muse/genmax/poster_len_lich/taovideo) do phiếu B-3/B-4 bổ sung.
    """
    if luc not in LUC_KIEM:
        raise ThamSoLoi(f"lúc kiểm hạn mức lạ: {luc!r}")
    from .danh_muc import DANH_MUC  # import muộn: danh_muc dùng han_muc
    loai = DANH_MUC.get(ma_loai)
    if loai is None:
        raise ThamSoLoi(f"loại việc lạ: {ma_loai!r}")
    hom_nay = ngay_vn(kho.bay_gio())
    if luc == "tao":
        tran = _gia_tri(hm, "viec_tao_ngay_moi_nguoi")
        n = kho.dem_trong_ngay(None, hom_nay, boi=boi)
        if n >= tran:
            raise VuotHanMuc(f"{boi} đã tạo {n} việc hôm nay (trần {tran})")
        return
    if loai.agent is not None:
        tran_usd = _gia_tri(hm, "claude_usd_ngay")
        usd = kho.chi_phi_ngay(hom_nay)
        if usd >= tran_usd:
            raise VuotHanMuc(f"chi phí Claude hôm nay {usd:.2f} USD ≥ trần {tran_usd}")
        tran_viec = _gia_tri(hm, "claude_viec_ngay")
        n = kho.dem_trong_ngay(None, hom_nay, chi_claude=True)
        if n >= tran_viec:
            raise VuotHanMuc(f"đã chạy {n} việc Claude hôm nay (trần {tran_viec})")
