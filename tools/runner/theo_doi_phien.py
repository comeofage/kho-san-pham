"""Theo dõi một phiên sống `claude -p --input-format stream-json` (§7.3, phiếu B-5). THUẦN: không I/O, không đồng hồ.

Bên gọi (luồng làn, A-5) nạp từng sự kiện đã đọc kèm thời điểm nhận (`nap`), rồi hỏi tình trạng (`tinh_trang`).
Mọi chỗ đọc tên trường stream-json nằm ở `stream_json`; file này chỉ ghép trạng thái.

Quy ước (§7.3):
- Sự kiện CẤP CAO = `parent_tool_use_id` thiếu/None/rỗng. Chỉ `result` cấp cao kết luận lượt; chỉ `assistant`/`user`
  cấp cao SAU result đó mới huỷ kết luận (agent đã làm tiếp). Sự kiện khác (của subagent, task_*, init,
  rate_limit_event, hook…) chỉ đặt lại đồng hồ im lặng.
- Việc nền: task_started mở, task_notification / task_updated(patch.status kết thúc) đóng — ở MỌI cấp.
- Chi phí: `total_cost_usd` cộng dồn trong phiên → chênh lệch `d = tong − moc` (tong ≥ moc), ngược lại `d = tong`.
- Lượt: message assistant khác nhau ở mọi cấp (khử trùng theo message.id). Codex: khử trùng theo id tool_use.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import stream_json as sj
from .kieu import KetQuaAgent
from .phieu import phan_tich_ket_qua

_LOAI_HOAT_DONG = ("assistant", "user")        # loại sự kiện cấp cao cho thấy agent đang làm lượt mới


@dataclass(frozen=True)
class TinhTrang:
    loai: str                          # 'dang_lam' | 'ket_luot' | 'loi_luot'
    ket_qua: KetQuaAgent | None        # có khi loai == 'ket_luot'
    van_ban: str                       # văn bản result cấp cao cuối (đã che)
    so_viec_nen: int
    so_ket_luot: int                   # số result cấp cao đã thấy (bên gọi biết có kết luận MỚI)


@dataclass(frozen=True)
class _KetLuot:
    loi: bool
    van_ban: str                       # đã che
    ket_qua: KetQuaAgent | None        # None khi loi


class TheoDoiPhien:
    def __init__(self, dot_bat: int, che: Callable[[str], str] | None = None):
        self._dot_bat = dot_bat
        self._che = che
        self.session_id: str | None = None
        self.phien_ban: str | None = None
        self.so_luot: int = 0
        self.so_codex: int = 0                  # MỞ RỘNG ngoài chữ ký §13: lượt gọi Codex (§7.5), mọi cấp
        self.chi_phi_usd: float = 0.0
        self.luc_su_kien_cuoi: float = 0.0
        self._viec_nen: set[str] = set()
        self._viec_nen_da_xong: set[str] = set()
        self._message_da_thay: set[str] = set()
        self._codex_da_thay: set[str] = set()
        self._moc_chi_phi: float = 0.0
        self._so_ket_luot: int = 0
        self._van_ban_cuoi: str = ""
        self._ket_luot: _KetLuot | None = None   # result cấp cao CHƯA bị hoạt động cấp cao mới huỷ

    @property
    def viec_nen_mo(self) -> frozenset[str]:
        return frozenset(self._viec_nen)

    # ------------------------------------------------------------ nạp

    def nap(self, sk: dict, luc: float) -> float:
        """Ghi nhận một sự kiện nhận lúc `luc`. Trả chênh lệch USD do sự kiện này (≥ 0)."""
        if not isinstance(sk, dict):
            return 0.0
        self.luc_su_kien_cuoi = luc
        cap_cao = sj.la_cap_cao(sk)

        sid = sj.la_khoi_tao(sk)
        if sid is not None:
            self.session_id = sid
        ver = sj.phien_ban_claude(sk)
        if ver is not None:
            self.phien_ban = ver

        self._nap_viec_nen(sk)
        self._nap_luot_va_codex(sk)

        if cap_cao and sk.get("type") in _LOAI_HOAT_DONG:
            self._ket_luot = None

        kq = sj.la_ket_qua(sk) if cap_cao else None
        if kq is None:
            return 0.0
        self._nhan_ket_luot(kq, sk.get("subtype"))
        return self._chenh_lech(sj.tong_chi_phi(sk))

    def _nap_viec_nen(self, sk: dict) -> None:
        tid = sj.viec_nen_bat_dau(sk)
        if tid is not None and tid not in self._viec_nen_da_xong:
            self._viec_nen.add(tid)
        tid = sj.viec_nen_ket_thuc(sk)
        if tid is not None:
            self._viec_nen.discard(tid)
            self._viec_nen_da_xong.add(tid)

    def _nap_luot_va_codex(self, sk: dict) -> None:
        if sj.dem_luot(sk):
            mid = sj.ma_message(sk)
            if mid is None:
                self.so_luot += 1
            elif mid not in self._message_da_thay:
                self._message_da_thay.add(mid)
                self.so_luot += 1
        for ma in sj.cac_goi_codex(sk):
            if ma is None:
                self.so_codex += 1
            elif ma not in self._codex_da_thay:
                self._codex_da_thay.add(ma)
                self.so_codex += 1

    def _nhan_ket_luot(self, kq: dict, subtype: object) -> None:
        self._so_ket_luot += 1
        van_ban_tho = kq["van_ban"]
        van_ban = self._che(van_ban_tho) if self._che is not None else van_ban_tho
        if kq["loi"]:
            if not van_ban.strip():
                van_ban = f"lượt lỗi, không có văn bản kết quả (subtype={str(subtype)[:60]})"
            self._ket_luot = _KetLuot(True, van_ban, None)
        else:
            self._ket_luot = _KetLuot(False, van_ban, phan_tich_ket_qua(van_ban_tho, self._dot_bat, self._che))
        self._van_ban_cuoi = van_ban

    def _chenh_lech(self, tong: float | None) -> float:
        if tong is None:                  # thiếu/sai dạng: không đổi mốc, không tính
            return 0.0
        d = tong - self._moc_chi_phi if tong >= self._moc_chi_phi else tong
        self._moc_chi_phi = tong
        self.chi_phi_usd += d
        return d

    # ------------------------------------------------------------ tình trạng

    def tinh_trang(self, bay_gio: float, im_lang_s: float) -> TinhTrang:
        kl = self._ket_luot
        nen = len(self._viec_nen)
        if kl is None or bay_gio - self.luc_su_kien_cuoi < im_lang_s:
            return TinhTrang("dang_lam", None, self._van_ban_cuoi, nen, self._so_ket_luot)
        if kl.loi:
            return TinhTrang("loi_luot", None, kl.van_ban, nen, self._so_ket_luot)
        return TinhTrang("ket_luot", kl.ket_qua, kl.van_ban, nen, self._so_ket_luot)
