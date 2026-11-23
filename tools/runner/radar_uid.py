"""Script chạy việc của Radar UID (docs/radar-uid.md §3, §6.2-§6.6). Việc runner `radar_uid_hang_ngay` / `radar_uid_nap`.

Chạy (cwd = thư mục chứa gói `runner`):
    python -B -m runner.radar_uid --che-do {nap,hang-ngay} --ngay YYYY-MM-DD --db <radar_uid.db>
        --token-file <đường dẫn file token> --viec-id <id> --tran-goi N [--goc <UID 19 số>]

- `hang-ngay`: chụp E1 + E2 cho mọi UID chưa `ok` hôm nay của các nhóm `da_tim` và `loi_tim` (xoay: UID chụp cũ
  nhất đi trước). Nhóm `cho_tim`/`dang_tim`/`ngung` bị bỏ qua (thuộc luồng nạp hoặc đã ngừng).
- `nap --goc`: E1 gốc → tìm tương tự (≤ 3 từ khoá, cổng `keyword_co_loc` từng từ khoá) → `ghi_tuong_tu` → nhóm
  `da_tim` → chụp gốc + tương tự chưa chụp hôm nay. E1 của gốc dùng lại cho cả việc tìm lẫn việc chụp (ngân sách
  = 2×N + số GET tìm).
- Ngân sách: mỗi GET được cộng vào `goi_ngay` qua `KhoRadarUid.tinh_goi` TRƯỚC khi gọi (qua callback của client
  EchoTik); trước khi bắt đầu một UID còn kiểm đủ chỗ cho cả 2 GET, để không để UID dở dang vì hết ngân sách.
- Dừng đúng bảng §6.3: token_thieu | token_het_han | rate_limit | het_han_muc_goi | mang_lien_tiep (5) | dinh_dang
  (3 UID liên tiếp) → `tu_dung`, thoát 0. Lỗi bất ngờ → `loi` / `loi_bat_ngo`, thoát 1.
  `hang-ngay` có ≥ 1 UID được thử mà 0 UID chụp OK (và không dừng có chủ đích) → `loi` / `khong_chup_duoc`, thoát 1.
- stdout đúng 1 dòng JSON ASCII `{"trang_thai","ly_do","so_uid","so_goi"}` ở MỌI đường ra.
- Token chỉ đi qua đường dẫn file: không vào argv/log/stdout/DB. Log chỉ có tên kiểu ngoại lệ.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import radar_uid_tinh as tinh
from .echotik import EchoTik, HetNganSach, LoiEchoTik, chuan_ung_vien, chuan_video
from .kho_radar_uid import ChiDoc, KhoRadarUid, KhongCoRadar, SaiTrangThaiRadar
from .kieu import MUI_GIO_VN, ThamSoLoi, gio_vn

log = logging.getLogger("kho_runner.radar_uid")

CHE_DO = ("nap", "hang-ngay")
TRAN_GOI_TOI_DA = 1000
MANG_LIEN_TIEP_TOI_DA = 5        # §6.3: 5 lỗi mạng liên tiếp (mỗi lỗi đã qua thử lại trong client) ⇒ tu_dung
DINH_DANG_LIEN_TIEP_TOI_DA = 3   # §6.3: ≥ 3 UID liên tiếp dữ liệu lạ ⇒ tu_dung
MOI_TRANG = 50
GET_MOT_UID = 2                  # E1 + E2 trang 1

_RE_NGAY = re.compile(r"^\d{4}-\d{2}-\d{2}\Z", re.ASCII)
_RE_UID = re.compile(r"^\d{19}\Z", re.ASCII)


class _ThamSoSai(Exception):
    pass


class _Dung(Exception):
    """Dừng cả lượt theo bảng §6.3 (`tu_dung`, thoát 0). `ly_do` là mã ngắn [a-z0-9_]."""

    def __init__(self, ly_do: str) -> None:
        super().__init__(ly_do)
        self.ly_do = ly_do


class _LoiViec(Exception):
    """Việc không làm được vì điều kiện đầu vào (ví dụ chưa có nhóm): `loi`, thoát 1, ly_do cố định."""

    def __init__(self, ly_do: str) -> None:
        super().__init__(ly_do)
        self.ly_do = ly_do


def _bay_gio_that() -> datetime:
    return datetime.now(MUI_GIO_VN)


def _txt(v: object) -> str | None:
    """Chuỗi/số từ E1 → chuỗi; kiểu khác (dict, list, bool, None) → None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return str(v)
    return None


# ---------------------------------------------------------------------------------------------------------------
# Trạng thái một lượt chạy
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class _Lan:
    kho: KhoRadarUid
    ngay: str
    che_do: str
    viec_id: str
    token_file: Path
    tran: int
    bay_gio: Callable[[], datetime]
    echotik_factory: Callable[..., Any]
    et: Any = None
    so_goi: int = 0
    so_uid: int = 0                                         # UID chụp OK (có video)
    so_thu: int = 0                                         # UID đã THỬ chụp (đã qua `bat_dau_chup`)
    da_bat_dau: set[str] = field(default_factory=set)       # UID đã `bat_dau_chup` trong lượt này
    dang_do: set[str] = field(default_factory=set)          # UID đang `dang_chup`, chưa chốt ok/loi
    e1_nho: dict[str, dict] = field(default_factory=dict)   # E1 đã lấy (dùng lại cho E2 của UID gốc trong nap)
    mang_lt: int = 0
    dinh_dang_lt: int = 0
    token_ok_da_ghi: bool = False

    def luc(self) -> str:
        return gio_vn(self.bay_gio()).isoformat(timespec="seconds")

    def tinh_goi(self, so: int) -> bool:
        """Callback của client: cộng ngân sách TRƯỚC khi gọi. False ⇒ client ném HetNganSach."""
        if self.kho.tinh_goi(self.ngay, so, self.tran):
            self.so_goi += so
            return True
        return False

    def du_cho(self, can: int) -> bool:
        return self.kho.goi_hom_nay(self.ngay) + can <= self.tran

    def tao_echotik(self) -> None:
        if self.et is None:
            self.et = self.echotik_factory(self.token_file, tinh_goi=self.tinh_goi)


def _kiem_file_token(lan: _Lan) -> None:
    """Chỉ kiểm file CÓ TỒN TẠI (không đọc nội dung). Thiếu ⇒ ghi trạng thái token rồi dừng."""
    if not lan.token_file.is_file():
        lan.kho.ghi_token("thieu", "token_thieu")
        raise _Dung("token_thieu")


def _ghi_token_ok(lan: _Lan) -> None:
    if not lan.token_ok_da_ghi:
        lan.kho.ghi_token("ok", "")
        lan.token_ok_da_ghi = True


def _chot_loi_chup(lan: _Lan, uid: str | None, ma: str) -> None:
    if uid is not None and uid in lan.dang_do:
        lan.kho.ghi_chup_loi(uid, lan.ngay, ma)
        lan.dang_do.discard(uid)


def _chot_dang_do(lan: _Lan, ma: str) -> None:
    for u in sorted(lan.dang_do):
        _chot_loi_chup(lan, u, ma)


def _xu_ly_loi(lan: _Lan, uid: str | None, e: LoiEchoTik) -> None:
    """Một lỗi EchoTik (§6.3). Ném `_Dung` nếu phải dừng cả lượt; trả bình thường nếu chỉ hỏng UID này."""
    ma = e.ma
    _chot_loi_chup(lan, uid, ma)
    if ma in ("token_thieu", "token_het_han"):
        lan.kho.ghi_token("thieu" if ma == "token_thieu" else "het_han", ma)
        raise _Dung(ma)
    if ma == "rate_limit":
        raise _Dung(ma)
    if ma == "mang":
        lan.mang_lt += 1
        lan.dinh_dang_lt = 0
        if lan.mang_lt >= MANG_LIEN_TIEP_TOI_DA:
            raise _Dung("mang_lien_tiep")
        return
    if ma == "dinh_dang":
        lan.dinh_dang_lt += 1
        lan.mang_lt = 0
        if lan.dinh_dang_lt >= DINH_DANG_LIEN_TIEP_TOI_DA:
            raise _Dung("dinh_dang")
        return
    lan.mang_lt = lan.dinh_dang_lt = 0                    # khong_tim_thay: máy chủ vẫn trả lời bình thường


def _het_ngan_sach(lan: _Lan, uid: str | None) -> _Dung:
    _chot_loi_chup(lan, uid, "het_han_muc_goi")
    return _Dung("het_han_muc_goi")


# ---------------------------------------------------------------------------------------------------------------
# Chụp một UID: E1 + E2
# ---------------------------------------------------------------------------------------------------------------
def _lay_video(lan: _Lan, uid: str) -> tuple[list[dict], int | None, int]:
    """E2 trang 1; thêm trang khi `meta.last_page` > số trang đã lấy VÀ `TRANG_VIDEO_TOI_DA` cho phép (mặc định 1)."""
    ds, meta = lan.et.video(uid, 1, MOI_TRANG)
    tat_ca = list(ds)
    last = meta.get("last_page")
    trang = 1
    while last is not None and trang < last and trang < tinh.NGUONG["TRANG_VIDEO_TOI_DA"]:
        trang += 1
        them, _ = lan.et.video(uid, trang, MOI_TRANG)
        tat_ca.extend(them)
    return tat_ca, last, trang


def _ghi_san_pham_tu_e1(lan: _Lan, uid: str, e1: dict) -> str:
    ten = _txt(e1.get("product_name")) or ""
    sel = e1.get("seller")
    shop = (_txt(sel.get("seller_name")) or "") if isinstance(sel, dict) else ""
    if ten.strip():
        lan.kho.ghi_san_pham(uid, ten, shop)
    return ten


def _chup_mot(lan: _Lan, uid: str) -> None:
    """Chụp một UID. Hỏng riêng UID ⇒ ghi `loi` rồi trở về; lỗi phải dừng cả lượt ⇒ ném `_Dung`."""
    can = 1 if uid in lan.e1_nho else GET_MOT_UID
    if not lan.du_cho(can):
        raise _het_ngan_sach(lan, uid)
    if uid not in lan.da_bat_dau:
        if not lan.kho.bat_dau_chup(uid, lan.ngay, lan.luc()):    # ghi `dang_chup` TRƯỚC khi gọi mạng
            return                                                # đã ok / hết số lần thử trong ngày
        lan.da_bat_dau.add(uid)
        lan.dang_do.add(uid)
        lan.so_thu += 1
    try:
        e1 = lan.e1_nho.pop(uid, None)
        if e1 is None:
            e1 = lan.et.chi_tiet(uid)
        ds, last, trang = _lay_video(lan, uid)
    except LoiEchoTik as e:
        _xu_ly_loi(lan, uid, e)
        return
    except HetNganSach:
        raise _het_ngan_sach(lan, uid) from None
    lan.mang_lt = lan.dinh_dang_lt = 0
    _ghi_token_ok(lan)
    _ghi_san_pham_tu_e1(lan, uid, e1)
    videos = {}
    for raw in ds:
        hv = chuan_video(raw)                                     # thiếu views_count/video_id/publish_time ⇒ bỏ, không điền 0
        if hv is not None:
            videos.setdefault(hv["video_id"], hv)
    lan.kho.ghi_chup_ok({
        "uid": uid, "ngay": lan.ngay, "lay_luc": lan.luc(), "echotik_cap_nhat": _txt(e1.get("update_time")),
        "ban_tong": _txt(e1.get("sale_cnt")), "gia": _txt(e1.get("real_price")), "hoa_hong": _txt(e1.get("commission")),
        "ton": _txt(e1.get("total_stock_cnt")), "tong_creator": None, "so_trang": trang, "tong_trang": last,
        "videos": videos})                                        # videos rỗng ⇒ kho tự ghi loi/khong_co_video
    lan.dang_do.discard(uid)
    if videos:
        lan.so_uid += 1


def _chup_cac(lan: _Lan, ds: list[str]) -> None:
    for u in ds:
        _chup_mot(lan, u)


# ---------------------------------------------------------------------------------------------------------------
# hang-ngay
# ---------------------------------------------------------------------------------------------------------------
def _chay_hang_ngay(lan: _Lan) -> str:
    ds = lan.kho.ds_can_chup(lan.ngay)                            # nhóm da_tim và loi_tim, đã xoay
    if not ds:
        return ""
    _kiem_file_token(lan)
    lan.tao_echotik()
    _chup_cac(lan, ds)
    if lan.so_thu > 0 and lan.so_uid == 0:                        # có thử mà không UID nào ok: không được báo "xong"
        raise _LoiViec("khong_chup_duoc")
    return ""


# ---------------------------------------------------------------------------------------------------------------
# nap
# ---------------------------------------------------------------------------------------------------------------
def _nhom(lan: _Lan, goc: str) -> dict | None:
    return next((n for n in lan.kho.ds_nhom() if n["goc"] == goc), None)


def _chuyen_nhom(lan: _Lan, goc: str, tu: tuple[str, ...], den: str, ly_do: str = "") -> bool:
    """Đọc lại trạng thái nhóm rồi mới đổi, và CHỈ đổi khi đang ở một trong `tu`. Nhờ vậy nhóm đã `ngung` giữa
    chừng (chủ bấm ngừng) không bị `dat_trang_thai_nhom` ghi đè. (Khe hở giữa đọc và ghi cỡ mili-giây: chấp nhận.)"""
    nh = _nhom(lan, goc)
    if nh is None or nh["trang_thai"] not in tu:
        return False
    lan.kho.dat_trang_thai_nhom(goc, den, ly_do)
    return True


def _chuan_ds_e4(ds: list[dict]) -> list[dict]:
    return [uv for uv in (chuan_ung_vien(x) for x in ds) if uv is not None]


def _tim_tuong_tu(lan: _Lan, goc: str, ten: str, gia_goc: str | None) -> list[dict] | None:
    """§3. None = không từ khoá nào qua cổng `keyword_co_loc` (nhóm `loi_tim`/`keyword_khong_loc`)."""
    hop: dict[str, dict] = {}
    co_tu_khoa_loc_duoc = False
    for kw in tinh.tu_khoa_tim(ten):
        ung, meta = lan.et.tim(kw, 1, MOI_TRANG)
        ds = _chuan_ds_e4(ung)
        if (meta.get("last_page") or 0) > 1:
            ung2, _ = lan.et.tim(kw, 2, MOI_TRANG)
            ds += _chuan_ds_e4(ung2)
        if not tinh.keyword_co_loc(kw, [u["ten"] for u in ds]):
            continue                                              # EchoTik bỏ qua `keyword`: bỏ cả từ khoá này
        co_tu_khoa_loc_duoc = True
        for u in ds:
            hop.setdefault(u["uid"], u)
    if not co_tu_khoa_loc_duoc:
        return None
    # Loại: gốc + UID đã có liên kết mà không phải "tương tự tự động" (ghim, thêm tay, đã loại). Các tương tự
    # `dang_theo` sắp bị thay nên vẫn được xét lại.
    da_loai = {goc} | {x["uid"] for x in lan.kho.uid_cua_nhom(goc)
                       if not (x["vai"] == "tuong_tu" and x["trang_thai"] == "dang_theo")}
    chon = tinh.chon_tuong_tu(ten, gia_goc, list(hop.values()), frozenset(da_loai), tinh.SO_TUONG_TU_TOI_DA)
    return [{**u, "do_giong": round(tinh.do_giong(ten, u["ten"]), 4)} for u in chon]


def _tim_va_ghi(lan: _Lan, goc: str, ten: str, gia_goc: str | None) -> str:
    """Trả ly_do của lần xong ('' hoặc 'nhom_ngung')."""
    try:
        ds = _tim_tuong_tu(lan, goc, ten, gia_goc)
    except LoiEchoTik as e:
        _xu_ly_loi(lan, None, e)                                  # dừng cả lượt, hoặc hỏng riêng lần tìm này
        _chuyen_nhom(lan, goc, ("dang_tim",), "loi_tim", e.ma)
        return ""
    except HetNganSach:
        raise _het_ngan_sach(lan, None) from None
    if ds is None:
        _chuyen_nhom(lan, goc, ("dang_tim",), "loi_tim", "keyword_khong_loc")
        return ""
    nh = _nhom(lan, goc)
    if nh is None or nh["trang_thai"] != "dang_tim":
        return "nhom_ngung"                                       # chủ ngừng nhóm giữa chừng: không ghi gì thêm
    lan.kho.ghi_tuong_tu(goc, ds, lan.luc())
    if not _chuyen_nhom(lan, goc, ("dang_tim",), "da_tim"):
        return "nhom_ngung"
    return ""


def _chay_nap(lan: _Lan, goc: str) -> str:
    if not _chuyen_nhom(lan, goc, ("cho_tim", "dang_tim", "da_tim", "loi_tim"), "dang_tim"):
        if _nhom(lan, goc) is None:
            raise _LoiViec("khong_co_nhom")
        return "nhom_ngung"
    try:
        ly_do = _nap_trong_nhom(lan, goc)
    except _Dung as d:
        _chuyen_nhom(lan, goc, ("dang_tim",), "loi_tim", d.ly_do)
        raise
    return ly_do


def _nap_trong_nhom(lan: _Lan, goc: str) -> str:
    _kiem_file_token(lan)
    lan.tao_echotik()
    # E1 của gốc: ghi `dang_chup` TRƯỚC khi gọi, rồi dùng lại cho E2 của gốc
    if lan.kho.bat_dau_chup(goc, lan.ngay, lan.luc()):
        lan.da_bat_dau.add(goc)
        lan.dang_do.add(goc)
    try:
        e1 = lan.et.chi_tiet(goc)
    except LoiEchoTik as e:
        _xu_ly_loi(lan, goc, e)
        _chuyen_nhom(lan, goc, ("dang_tim",), "loi_tim", e.ma)
        return ""
    except HetNganSach:
        raise _het_ngan_sach(lan, goc) from None
    lan.mang_lt = lan.dinh_dang_lt = 0
    _ghi_token_ok(lan)
    ten = _ghi_san_pham_tu_e1(lan, goc, e1)
    if goc in lan.da_bat_dau:
        lan.e1_nho[goc] = e1
    ly_do = _tim_va_ghi(lan, goc, ten, _txt(e1.get("price")))
    ds = lan.kho.ds_can_chup(lan.ngay, goc=goc)                   # mọi trạng thái trừ ngung
    _chup_cac(lan, ds)
    _chot_dang_do(lan, "nhom_ngung")                              # gốc đã bắt đầu chụp mà nhóm bị ngừng: không để dở
    return ly_do


# ---------------------------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------------------------
def _phan_tich(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="runner.radar_uid", add_help=False, allow_abbrev=False)
    ap.add_argument("--che-do", required=True, choices=CHE_DO)
    ap.add_argument("--ngay", required=True)
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--token-file", required=True, type=Path)
    ap.add_argument("--viec-id", required=True)
    ap.add_argument("--tran-goi", required=True, type=int)
    ap.add_argument("--goc")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:                                       # argparse đã in lý do ra stderr
        raise _ThamSoSai("tham số dòng lệnh sai") from e
    if not _RE_NGAY.fullmatch(a.ngay):
        raise _ThamSoSai("--ngay phải dạng YYYY-MM-DD")
    try:
        datetime.strptime(a.ngay, "%Y-%m-%d")
    except ValueError as e:
        raise _ThamSoSai("--ngay không phải ngày có thật") from e
    if not 0 <= a.tran_goi <= TRAN_GOI_TOI_DA:
        raise _ThamSoSai("--tran-goi phải trong [0, 1000]")
    if (a.che_do == "nap") != (a.goc is not None):
        raise _ThamSoSai("--goc bắt buộc với nap và chỉ dùng cho nap")
    if a.goc is not None and not _RE_UID.fullmatch(a.goc):
        raise _ThamSoSai("--goc phải đủ 19 chữ số")
    return a


def _in(d: dict) -> None:
    sys.stdout.write(json.dumps(d, ensure_ascii=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _kq(trang_thai: str, ly_do: str, so_uid: int = 0, so_goi: int = 0) -> dict:
    return {"trang_thai": trang_thai, "ly_do": ly_do, "so_uid": so_uid, "so_goi": so_goi}


def _chay_trong(argv: list[str] | None, echotik_factory: Callable[..., Any],
                bay_gio: Callable[[], datetime]) -> tuple[int, dict]:
    try:
        a = _phan_tich(argv)
    except _ThamSoSai as e:
        log.error("%s", e)                                        # chỉ câu cố định của _phan_tich
        return 1, _kq("loi", "tham_so_sai")
    kho = KhoRadarUid(a.db, bay_gio)
    try:
        try:
            kho.mo()
            duoc_chay = kho.bat_dau_lan(a.ngay, a.che_do, a.viec_id)
        except ThamSoLoi:
            log.error("tham số bị kho từ chối (viec_id/che_do không hợp lệ)")
            return 1, _kq("loi", "tham_so_sai")
        if not duoc_chay:                                         # lần này đã xong/tu_dung: không làm lại, báo lại kết quả
            cu = kho.lan_cua_viec(a.ngay, a.che_do, a.viec_id) or {}
            return 0, _kq(cu.get("trang_thai", "xong"), cu.get("ly_do", ""), 0, int(cu.get("so_goi", 0)))
        lan = _Lan(kho=kho, ngay=a.ngay, che_do=a.che_do, viec_id=a.viec_id, token_file=a.token_file,
                   tran=a.tran_goi, bay_gio=bay_gio, echotik_factory=echotik_factory)
        trang_thai, ly_do = "xong", ""
        try:
            ly_do = _chay_nap(lan, a.goc) if a.che_do == "nap" else _chay_hang_ngay(lan)
        except _Dung as d:
            trang_thai, ly_do = "tu_dung", d.ly_do
            _chot_dang_do(lan, d.ly_do)
        except _LoiViec as e:
            return _ket_loi(lan, e.ly_do)
        except Exception as e:  # noqa: BLE001 — chốt chặn cuối: lượt phải được đóng `loi`; log chỉ tên kiểu (§6.6)
            log.error("radar_uid lỗi bất ngờ (%s)", type(e).__name__)
            return _ket_loi(lan, "loi_bat_ngo")
        kho.ket_thuc_lan(a.ngay, a.che_do, a.viec_id, trang_thai, ly_do, lan.so_goi)
        return 0, _kq(trang_thai, ly_do, lan.so_uid, lan.so_goi)
    finally:
        kho.dong()


def _ket_loi(lan: _Lan, ly_do: str) -> tuple[int, dict]:
    try:
        lan.kho.ket_thuc_lan(lan.ngay, lan.che_do, lan.viec_id, "loi", ly_do, lan.so_goi)
    except (sqlite3.Error, SaiTrangThaiRadar, ThamSoLoi, ChiDoc, KhongCoRadar) as e:
        log.error("không ghi được lan_chay=loi (%s)", type(e).__name__)
    return 1, _kq("loi", ly_do, lan.so_uid, lan.so_goi)


def chay(argv: list[str] | None = None, *, echotik_factory: Callable[..., EchoTik] = EchoTik,
         bay_gio: Callable[[], datetime] = _bay_gio_that) -> int:
    """0 = xong | tu_dung; 1 = lỗi. In ĐÚNG 1 dòng JSON ASCII ra stdout ở MỌI đường ra (kể cả lỗi bất ngờ)."""
    try:
        ma, dong = _chay_trong(argv, echotik_factory, bay_gio)
    except Exception as e:  # noqa: BLE001 — chốt chặn cuối: stdout luôn có 1 dòng JSON; log chỉ tên kiểu
        log.error("radar_uid lỗi bất ngờ ngoài lượt chạy (%s)", type(e).__name__)
        ma, dong = 1, _kq("loi", "loi_bat_ngo")
    try:
        _in(dong)
    except Exception as e:  # noqa: BLE001 — stdout hỏng: chỉ còn log + mã thoát 1
        log.error("radar_uid: không in được kết quả (%s)", type(e).__name__)
        ma = 1
    return ma


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(chay(sys.argv[1:]))
