"""Hạn mức (D5, docs/bo-chay-viec.md §10, §6.3).

Trần là HẰNG SỐ trong code. cau_hinh.json chỉ được HẠ: hieu_luc = min(tran_code, gia_tri_file).
Muốn nới phải sửa code và cài lại (có duyệt).
"""
from __future__ import annotations

import json
import math
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .kieu import ThamSoLoi, VuotHanMuc, gio_vn

if TYPE_CHECKING:
    from .kho_viec import KhoViec

HAN_MUC_TRAN: dict[str, int | float] = {
    # đợt cao nhất được mở; tăng = sửa code + cài lại (có duyệt). Đợt 5: B-4 — người dùng đã đồng ý mở (D11,
    # 17/11/2026 "Cho sửa + mở đợt 5"). cau_hinh.json hạ về 4 để đóng taovideo.
    "dot_bat": 5,
    "claude_usd_ngay": 999999, "claude_viec_ngay": 999999,
    "viec_tao_ngay_moi_nguoi": 30, "con_toi_da_xu_ly_link": 5,
    "muse_clip_moi_viec": 10, "muse_clip_ngay": 15,
    "genmax_ban_moi_viec": 999999, "genmax_viec_ngay": 999999,
    # poster_video_ngay_toi_da: trần video/ngày của MỘT việc VÀ tổng so_video_ngay mỗi tài khoản mỗi ngày
    # (người dùng chốt FX-11: 100 video/tài khoản/ngày; vẫn ≤ poster_len_lich_ngay việc/ngày).
    "poster_len_lich_ngay": 2, "poster_video_ngay_toi_da": 100,
    # taovideo (D11 §7.5): taovideo_ngay đếm VIỆC/ngày; taovideo_lan_ngay đếm LẦN TIÊU lời duyệt/ngày.
    # Trần trong MỘT phiên sống: USD-ước-tính (Σ chênh lệch total_cost_usd), số voice *_adam.mp3 mới (file thật),
    # codex_luot_viec lượt Codex (đặt lại khi tiêu lời duyệt mới). Vòng chạy (A-5) đo và giết cây khi vượt.
    "taovideo_ngay": 10, "codex_luot_viec": 999999,   # 19/11/2026: 1 → 10 để xếp nhiều SP vào hàng chờ (GPU vẫn 1 việc một lúc)
    # 20/11/2026 chủ shop: KHÔNG giới hạn chi phí — usd/mp3/codex/claude/genmax = 999999 (usd phải in ra không dạng 1e+06 cho --max-budget-usd)
    "taovideo_usd_viec": 999999, "taovideo_mp3_viec": 999999, "taovideo_lan_ngay": 10,
    # D10 (docs/sua-video.md §7.3): số việc sua_video + hoan_tac_sua TẠO trong ngày VN (chặn bấm lặp làm bận GPU).
    "sua_video_ngay": 60,
    # D15 (docs/hoc-tu-dong.md §4.3). Hạ về 0: hoc_bat_ngay = tắt tự áp dụng VÀ tắt gợi ý vào phiếu (cầu dao,
    # phieu.lay_goi_y_hoc); hoc_hieu_luc_toi_da = không bài nào vào phiếu; quet_view_ngay = tắt lịch quét
    # (việc quet_view_hang_ngay TẠO/ngày, gồm cả tự tạo lẫn Chạy lại).
    "hoc_bat_ngay": 1, "hoc_hieu_luc_toi_da": 5, "quet_view_ngay": 3,
}
# Loại tính chung trần sua_video_ngay (miễn phí, làn gpu, dot=4 — không cần nâng dot_bat).
LOAI_SUA_VIDEO: tuple[str, ...] = ("sua_video", "hoan_tac_sua")
# D15: loại đếm trần quet_view_ngay lúc tạo (danh_muc.LOAI_CHI_HE_THONG; đặt tên ở đây vì danh_muc import han_muc).
LOAI_QUET_VIEW = "quet_view_hang_ngay"
TRAN_LUOT: dict[str, int] = {"radar_ban_tin": 40, "phan_tich_uid": 250, "muse_clip": 120,
                             "poster_len_lich": 60, "taovideo": 1500}
# Watermark người dùng cho chọn ở taovideo (D11: "nha.cua.mit hoặc không"); "khong" luôn có, không nằm ở đây.
WM_CHO_PHEP: tuple[str, ...] = ("nha.cua.mit",)
# §7.7 đồng hồ của phiên sống taovideo (giây). cau_hinh.json chỉ được HẠ qua khoá "taovideo_<tên>" (vd taovideo_cho_s).
HET_GIO_TAOVIDEO: dict[str, int] = {"lam_s": 8 * 3600, "cho_s": 3 * 3600, "nen_s": 4 * 3600, "tong_s": 24 * 3600}
_TIEN_TO_HET_GIO = "taovideo_"

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
        tran_het_gio = _tran_het_gio(k)
        if k not in HAN_MUC_TRAN and tran_het_gio is None:
            canh_bao.append(f"cau_hinh.json: khoá lạ {k!r} — bỏ qua")
            continue
        if not _la_so_hop_le(v) or (tran_het_gio is not None and v <= 0):
            canh_bao.append(f"cau_hinh.json: {k} = {v!r} không phải số hợp lệ — bỏ qua")
            continue
        tran = HAN_MUC_TRAN[k] if tran_het_gio is None else tran_het_gio
        if v > tran:
            canh_bao.append(f"cau_hinh.json: {k} = {v} vượt trần code {tran} — bỏ qua (file chỉ được hạ)")
            continue
        hm[k] = max(1, int(v)) if tran_het_gio is not None else (int(v) if k in _KHOA_SO_NGUYEN else v)
    return hm, canh_bao


def _tran_het_gio(k: object) -> int | None:
    """Trần code của khoá đồng hồ taovideo trong cau_hinh (`taovideo_lam_s`…); None nếu không phải khoá đó."""
    if not isinstance(k, str) or not k.startswith(_TIEN_TO_HET_GIO):
        return None
    return HET_GIO_TAOVIDEO.get(k[len(_TIEN_TO_HET_GIO):])


def het_gio_taovideo(hm: dict) -> dict[str, int]:
    """§7.7: đồng hồ phiên sống = min(hằng số, hm["taovideo_<tên>"]). Chỉ được HẠ; giá trị hỏng/≤0/nới → hằng số."""
    ra = dict(HET_GIO_TAOVIDEO)
    if not isinstance(hm, dict):
        return ra
    for ten, tran in HET_GIO_TAOVIDEO.items():
        v = hm.get(_TIEN_TO_HET_GIO + ten)
        if _la_so_hop_le(v) and 0 < v < tran:
            ra[ten] = max(1, int(v))
    return ra


def _gia_tri(hm: dict, k: str) -> int | float:
    """Phòng thủ: hm truyền vào bị nới/thiếu khoá/hỏng vẫn không vượt trần code."""
    tran = HAN_MUC_TRAN[k]
    v = hm.get(k, tran) if isinstance(hm, dict) else tran
    return min(v, tran) if _la_so_hop_le(v) else tran


def tran_taovideo(hm: dict) -> dict[str, int | float]:
    """FX-28: trần HIỆU LỰC của MỘT lần duyệt taovideo (cau_hinh chỉ hạ): usd (USD-ước-tính), mp3 (voice mới),
    codex (lượt), gio (đồng hồ làm lam_s, giờ). Cùng nguồn với vòng chạy (_gia_tri, het_gio_taovideo)."""
    return {"usd": _gia_tri(hm, "taovideo_usd_viec"), "mp3": int(_gia_tri(hm, "taovideo_mp3_viec")),
            "codex": int(_gia_tri(hm, "codex_luot_viec")), "gio": het_gio_taovideo(hm)["lam_s"] / 3600}


def han_muc_hoc(hm: dict | None) -> tuple[int, int]:
    """D15 §4.3: (hoc_bat_ngay, hoc_hieu_luc_toi_da) HIỆU LỰC — min(trần code, hm); hm thiếu/hỏng/nới → trần code.
    Dùng chung cho API /hoc/*, lệnh việc hoc_hang_ngay và cầu dao gợi ý vào phiếu (kho_hoc không có mặc định)."""
    return int(_gia_tri(hm, "hoc_bat_ngay")), int(_gia_tri(hm, "hoc_hieu_luc_toi_da"))


def han_muc_tu_thu_muc(thu_muc: Path) -> tuple[dict, list[str]]:
    """Hạn mức hiệu lực từ `<thu_muc>/cau_hinh.json` (utf-8-sig): thiếu file → trần code; hỏng → trần code + cảnh báo.
    Cùng luật với chay_runner._doc_cau_hinh (nên gộp về đây khi được sửa chay_runner)."""
    p = Path(thu_muc) / "cau_hinh.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        d = {}
    except (OSError, ValueError) as e:
        hm, cb = han_muc_hieu_luc({})
        return hm, [f"cau_hinh.json hỏng ({e}) — dùng trần trong code"] + cb
    return han_muc_hieu_luc(d)


# ---------- đợt 4–5: hạn mức riêng của loại tốn tiền (B-3) ----------
# Hạn mức mỗi việc: (khoá tham số, khoá hạn mức, đơn vị, cách đo).
_MOI_VIEC: dict[str, tuple[str, str, str]] = {
    "muse_clip": ("mau", "muse_clip_moi_viec", "clip"),
    "voice_genmax": ("ma_ban", "genmax_ban_moi_viec", "bản"),
    "poster_len_lich": ("so_video_ngay", "poster_video_ngay_toi_da", "video/ngày"),
}
# Hạn mức mỗi ngày: (khoá hạn mức, đơn vị). muse tính theo số clip, còn lại theo số việc.
_MOI_NGAY: dict[str, tuple[str, str]] = {
    "muse_clip": ("muse_clip_ngay", "clip"),
    "voice_genmax": ("genmax_viec_ngay", "việc"),
    "poster_len_lich": ("poster_len_lich_ngay", "việc"),
    # taovideo KHÔNG đi đường chung (đếm theo lần tiêu): xem _kiem_taovideo (§7.5).
}
_TRANG_THAI_MO = ("cho", "dang_chay", "can_tra_loi", "cho_duyet")
DS_VIEC_TOI_DA = 500        # số việc gần nhất xét khi đếm theo ngày (≤30 việc/ngày/người → dư hơn 8 ngày)


def _do_moi_viec(ma_loai: str, tham_so: dict) -> int | None:
    """Độ lớn của một việc theo hạn mức mỗi việc; None nếu thiếu khoá. Sai kiểu → ThamSoLoi."""
    khoa, _, _ = _MOI_VIEC[ma_loai]
    if not isinstance(tham_so, dict) or khoa not in tham_so:
        return None
    v = tham_so[khoa]
    if khoa == "so_video_ngay":
        if not isinstance(v, int) or isinstance(v, bool):
            raise ThamSoLoi(f"{khoa} phải là số nguyên")
        return v
    if not isinstance(v, list):
        raise ThamSoLoi(f"{khoa} phải là danh sách")
    return len(v)


def _so_lan_tieu(x: object) -> int:
    return x if isinstance(x, int) and not isinstance(x, bool) and x > 0 else 0


def so_luong_ngay(ma_loai: str, tham_so: object, so_lan_tieu: int = 0) -> int:
    """Số đơn vị một việc ăn vào hạn mức ngày, × max(1, so_lan_tieu) (§10 D9: đếm theo số lần tiêu lời duyệt).
    muse = số mẫu (hỏng → trần code mỗi việc, thiên về chặt); loại khác = 1 việc.
    Đếm theo NGÀY dùng `da_dung_ngay` (mỗi lần tiêu vào ngày của nó) — không nhân so_lan_tieu vào một ngày."""
    if ma_loai != "muse_clip":
        mot = 1
    else:
        mau = tham_so.get("mau") if isinstance(tham_so, dict) else None
        mot = len(mau) if isinstance(mau, list) and mau else int(HAN_MUC_TRAN["muse_clip_moi_viec"])
    return mot * max(1, _so_lan_tieu(so_lan_tieu))


def _ngay_iso(s: object) -> date | None:
    if not isinstance(s, str) or not s:
        return None
    try:
        return ngay_vn(datetime.fromisoformat(s))
    except ValueError:
        return None


def ngay_tinh_han_muc(viec: dict) -> date | None:
    """Ngày VN mà việc ăn hạn mức; None = không tính (§10 D9).
    Tính khi: đã tiêu lời duyệt (so_lan_tieu > 0 — đã tốn tiền, kể cả khi xin duyệt lại đã xoá duyet_luc), hoặc đã
    duyệt (có duyet_luc), hoặc còn mở (có thể sẽ tốn).
    Ngày = tieu_luc_dau → duyet_luc → tao_luc (giá trị đầu tiên đọc được).
    Hạn mức số việc/clip theo ngày của việc ĐÃ tiêu dùng `ngay_cac_lan_tieu` (từng lần); hàm này dùng cho việc chưa
    tiêu lần nào và cho tổng video poster/tài khoản."""
    tinh = (_so_lan_tieu(viec.get("so_lan_tieu")) > 0 or bool(viec.get("duyet_luc"))
            or viec.get("trang_thai") in _TRANG_THAI_MO)
    if not tinh:
        return None
    return (_ngay_iso(viec.get("tieu_luc_dau")) or _ngay_iso(viec.get("duyet_luc"))
            or _ngay_iso(viec.get("tao_luc")))


def ngay_cac_lan_tieu(viec: dict, luc_tieu: Sequence[str] = ()) -> list[date]:
    """Ngày VN của TỪNG lần tiêu lời duyệt của việc (R-15 P2-1).

    `luc_tieu` = cột `luc` các dòng sổ da_tieu của việc (`KhoViec.luc_tieu_theo_viec`). Mỗi dòng là một lần tiêu,
    tính vào ngày của chính nó. Sổ thiếu dòng so với `so_lan_tieu` (sổ bị xoá/hỏng) → phần thiếu vẫn tính, vào ngày
    dự phòng tieu_luc_dau → duyet_luc → tao_luc; `luc` hỏng cũng dùng ngày dự phòng (không "quên" lần tốn tiền)."""
    du_phong = (_ngay_iso(viec.get("tieu_luc_dau")) or _ngay_iso(viec.get("duyet_luc"))
                or _ngay_iso(viec.get("tao_luc")))
    ds = [_ngay_iso(s) or du_phong for s in luc_tieu]
    ds += [du_phong] * max(0, _so_lan_tieu(viec.get("so_lan_tieu")) - len(ds))
    return [d for d in ds if d is not None]


def _don_vi_viec_ngay(ma_loai: str, viec: dict, ngay: date, luc_tieu: Sequence[str]) -> int:
    """Đơn vị hạn mức ngày `ngay` mà một việc (KHÁC việc đang xét) đã/đang chiếm.
    Đã tiêu ≥ 1 lần: so_luong × số lần tiêu rơi vào `ngay`. Chưa tiêu lần nào: như cũ (ngay_tinh_han_muc)."""
    mot = so_luong_ngay(ma_loai, viec.get("tham_so"))
    cac_ngay = ngay_cac_lan_tieu(viec, luc_tieu)
    if cac_ngay:
        return mot * cac_ngay.count(ngay)
    return mot if ngay_tinh_han_muc(viec) == ngay else 0


def da_dung_ngay(kho: "KhoViec", ma_loai: str, ngay: date, tru_id: str | None = None) -> int:
    """Tổng đơn vị hạn mức ngày `ngay` của loại, trừ việc `tru_id` — mỗi lần tiêu tính vào ngày của lần đó."""
    ds = [v for v in kho.ds(None, gioi_han=DS_VIEC_TOI_DA) if v.get("loai") == ma_loai and v.get("id") != tru_id]
    luc_tieu = kho.luc_tieu_theo_viec([v["id"] for v in ds])
    return sum(_don_vi_viec_ngay(ma_loai, v, ngay, luc_tieu.get(v["id"], ())) for v in ds)


def _so_lan_tieu_trong_ngay(kho: "KhoViec", viec: dict, ngay: date) -> int:
    if not viec:
        return 0
    return ngay_cac_lan_tieu(viec, kho.luc_tieu_theo_viec([viec["id"]]).get(viec["id"], ())).count(ngay)


# ---------- poster_len_lich: tổng video/ngày theo TÀI KHOẢN ----------

def khoa_tai_khoan_poster(tham_so: object) -> str | None:
    """Khoá gom hạn mức tổng video/ngày của poster_len_lich; None = không xác định (coi như trùng mọi tài khoản).

    Dữ liệu folder Poster hiện chỉ có {id, ten} — chưa có trường tài khoản — nên một folder = một tài khoản
    (gom theo folder_id). Khi tham_so có khoá tài khoản (vd. do runner gắn từ danh sách folder), chỉ cần sửa
    hàm này để trả khoá tài khoản; phần đếm dùng nguyên khoá trả về."""
    if not isinstance(tham_so, dict):
        return None
    fid = tham_so.get("folder_id")
    if not isinstance(fid, int) or isinstance(fid, bool):
        return None
    return f"folder:{fid}"


def _video_ngay_poster(tham_so: object) -> int:
    """so_video_ngay của một việc poster; hỏng/thiếu → trần code (thiên về chặt)."""
    n = tham_so.get("so_video_ngay") if isinstance(tham_so, dict) else None
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        return int(HAN_MUC_TRAN["poster_video_ngay_toi_da"])
    return n


def video_poster_tai_khoan_ngay(kho: "KhoViec", khoa_tk: str | None, ngay: date, tru_id: str | None = None) -> int:
    """Tổng so_video_ngay của các việc poster_len_lich tính vào `ngay` (theo ngay_tinh_han_muc) cùng tài khoản
    `khoa_tk`, trừ việc `tru_id`. Việc có khoá None (hoặc khoa_tk None) bị tính vào mọi tài khoản."""
    tong = 0
    for v in kho.ds(None, gioi_han=DS_VIEC_TOI_DA):
        if v.get("loai") != "poster_len_lich" or v.get("id") == tru_id or ngay_tinh_han_muc(v) != ngay:
            continue
        k = khoa_tai_khoan_poster(v.get("tham_so"))
        if k is None or khoa_tk is None or k == khoa_tk:
            tong += _video_ngay_poster(v.get("tham_so"))
    return tong


def _kiem_poster_tai_khoan(kho: "KhoViec", tham_so: dict, hm: dict, luc: str, viec_id: str | None,
                           hom_nay: date) -> None:
    tran = _gia_tri(hm, "poster_video_ngay_toi_da")
    if luc in ("tao", "duyet"):
        ts_viec: object = tham_so
        them = _video_ngay_poster(tham_so)
    elif viec_id is not None:                   # nhan có id: số liệu ĐANG LƯU của chính việc, nếu thuộc hôm nay
        v = kho.lay(viec_id)
        ts_viec = v.get("tham_so") if v else None
        them = _video_ngay_poster(ts_viec) if v and ngay_tinh_han_muc(v) == hom_nay else 0
    else:                                       # nhan kiểu cũ: mọi tài khoản hôm nay (đã gồm việc sắp nhận) ≤ trần
        tk_hom_nay = {khoa_tai_khoan_poster(v.get("tham_so")) for v in kho.ds(None, gioi_han=DS_VIEC_TOI_DA)
                      if v.get("loai") == "poster_len_lich" and ngay_tinh_han_muc(v) == hom_nay}
        for k in tk_hom_nay:
            da = video_poster_tai_khoan_ngay(kho, k, hom_nay)
            if da > tran:
                raise VuotHanMuc(f"poster_len_lich hôm nay tài khoản {k or 'không rõ'} đã {da} video > trần "
                                 f"{tran} video/tài khoản/ngày")
        return
    k = khoa_tai_khoan_poster(ts_viec)
    da = video_poster_tai_khoan_ngay(kho, k, hom_nay, viec_id)
    if da + them > tran:
        raise VuotHanMuc(f"poster_len_lich hôm nay tài khoản {k or 'không rõ'} đã lên lịch {da} video + {them} "
                         f"video của việc này > trần {tran} video/tài khoản/ngày")


def _viec_tinh_vao_ngay(kho: "KhoViec", viec: dict, ngay: date) -> tuple[bool, int]:
    """(việc có chiếm hạn mức VIỆC của `ngay` không, số lần tiêu rơi vào `ngay`).
    Đã tiêu ≥ 1 lần: chiếm ngày nào có lần tiêu. Chưa tiêu: theo ngay_tinh_han_muc (đã duyệt / còn mở)."""
    cac_ngay = ngay_cac_lan_tieu(viec, kho.luc_tieu_theo_viec([viec["id"]]).get(viec["id"], ()))
    if cac_ngay:
        n = cac_ngay.count(ngay)
        return n > 0, n
    return ngay_tinh_han_muc(viec) == ngay, 0


def _kiem_taovideo(kho: "KhoViec", hm: dict, luc: str, viec_id: str | None, hom_nay: date) -> None:
    """§7.5: taovideo_ngay = số VIỆC/ngày (việc đang xét tính 1, duyệt lại cùng việc không tính thêm);
    taovideo_lan_ngay = số LẦN TIÊU/ngày của mọi việc taovideo (lúc duyet/nhan cộng 1 lần sắp tiêu hôm nay)."""
    viec_khac = 0
    lan_khac = 0
    for v in kho.ds(None, gioi_han=DS_VIEC_TOI_DA):
        if v.get("loai") != "taovideo" or v.get("id") == viec_id:
            continue
        chiem, n = _viec_tinh_vao_ngay(kho, v, hom_nay)
        viec_khac += int(chiem)
        lan_khac += n
    # nhan kiểu cũ (vòng chạy truyền {} và không id, trước khi nhận): việc sắp nhận đã nằm trong viec_khac.
    kieu_cu = luc == "nhan" and viec_id is None
    tran_viec = _gia_tri(hm, "taovideo_ngay")
    if viec_khac + (0 if kieu_cu else 1) > tran_viec:
        raise VuotHanMuc(f"taovideo hôm nay đã có {viec_khac} việc"
                         + ("" if kieu_cu else " khác + việc này") + f" > trần {tran_viec} việc")
    if luc == "tao":
        return                                  # tạo chưa tiêu lời duyệt nào
    lan_rieng = _so_lan_tieu_trong_ngay(kho, kho.lay(viec_id) or {}, hom_nay) if viec_id is not None else 0
    tran_lan = _gia_tri(hm, "taovideo_lan_ngay")
    tong = lan_khac + lan_rieng + 1             # + 1 lần sắp tiêu hôm nay
    if tong > tran_lan:
        raise VuotHanMuc(f"taovideo hôm nay đã tiêu {lan_khac + lan_rieng} lần duyệt; thêm lần này > trần "
                         f"{tran_lan} lần/ngày")


def _kiem_ton_tien(kho: "KhoViec", ma_loai: str, tham_so: dict, hm: dict, luc: str,
                   viec_id: str | None, hom_nay: date) -> None:
    if ma_loai == "taovideo":
        _kiem_taovideo(kho, hm, luc, viec_id, hom_nay)
        return
    if ma_loai in _MOI_VIEC:
        khoa_ts, khoa_hm, don_vi = _MOI_VIEC[ma_loai]
        do = _do_moi_viec(ma_loai, tham_so)
        if do is None and luc != "nhan":        # nhan kiểu cũ (vòng chạy truyền {}) chỉ kiểm hạn mức ngày
            raise ThamSoLoi(f"thiếu tham số {khoa_ts} để kiểm hạn mức")
        tran = _gia_tri(hm, khoa_hm)
        if do is not None and do > tran:
            raise VuotHanMuc(f"{ma_loai}: {do} {don_vi} một việc vượt trần {tran} {don_vi}")
    if ma_loai not in _MOI_NGAY:
        return
    khoa_hm, don_vi = _MOI_NGAY[ma_loai]
    tran = _gia_tri(hm, khoa_hm)
    khac = da_dung_ngay(kho, ma_loai, hom_nay, viec_id)
    # Việc đang xét lúc duyet/nhan (R-15 P2-1): so_luong × (số lần ĐÃ tiêu rơi vào HÔM NAY + 1 lần sắp tiêu hôm nay).
    # Lần tiêu ở ngày khác thuộc hạn mức ngày đó, không cộng vào hôm nay. Lúc tao: so_luong (chưa tiêu lần nào).
    if luc == "tao":
        them = so_luong_ngay(ma_loai, tham_so)
    elif viec_id is not None:
        v = kho.lay(viec_id) or {}
        ts_viec = tham_so if luc == "duyet" else v.get("tham_so")
        them = so_luong_ngay(ma_loai, ts_viec) * (_so_lan_tieu_trong_ngay(kho, v, hom_nay) + 1)
    elif luc == "duyet":
        them = so_luong_ngay(ma_loai, tham_so)
    else:                                       # nhan kiểu cũ: tổng hôm nay (đã gồm việc sắp nhận) ≤ trần
        them = 0
    if khac + them > tran:
        raise VuotHanMuc(f"{ma_loai} hôm nay đã dùng {khac} {don_vi}"
                         + (f" + {them} {don_vi} của việc này" if them else "") + f" > trần {tran} {don_vi}")
    if ma_loai == "poster_len_lich":
        _kiem_poster_tai_khoan(kho, tham_so, hm, luc, viec_id, hom_nay)


def kiem_han_muc(kho: "KhoViec", ma_loai: str, tham_so: dict, hm: dict, luc: str, boi: str,
                 viec_id: str | None = None) -> None:
    """Raise VuotHanMuc nếu vượt. luc ∈ tao|duyet|nhan (nhan gồm cả chay-tiep).

    - tao: số việc người `boi` tạo trong ngày VN < viec_tao_ngay_moi_nguoi; loại sửa video (LOAI_SUA_VIDEO): tổng
      việc sua_video + hoan_tac_sua tạo trong ngày (mọi người) < sua_video_ngay.
    - duyet/nhan, loại dùng Claude: tổng USD hôm nay < claude_usd_ngay; số job Claude hôm nay < claude_viec_ngay.
    - Loại tốn tiền (đợt 4–5), cả 3 lúc: hạn mức mỗi việc (muse ≤10 clip, genmax ≤25 bản, poster ≤100 video/ngày)
      và hạn mức mỗi ngày (muse 15 clip, genmax 2 việc, poster_len_lich 2 việc + tổng so_video_ngay ≤100 mỗi tài
      khoản — khoa_tai_khoan_poster; taovideo 1 VIỆC + 3 LẦN TIÊU — _kiem_taovideo): mỗi lần tiêu tính vào ngày của lần đó, việc chưa tiêu theo
      `ngay_tinh_han_muc`; việc đang xét cộng (số lần đã tiêu hôm nay + 1). `viec_id` (MỞ RỘNG ngoài chữ ký §13, mặc định None): việc đang duyệt/nhận — để không
      đếm trùng chính nó. Lúc tao/duyet bắt buộc có tham số đo hạn mức mỗi việc (thiếu → ThamSoLoi).
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
        if ma_loai in LOAI_SUA_VIDEO:
            tran_sua = _gia_tri(hm, "sua_video_ngay")
            n_sua = sum(kho.dem_trong_ngay(l, hom_nay) for l in LOAI_SUA_VIDEO)
            if n_sua >= tran_sua:
                raise VuotHanMuc(f"hôm nay đã tạo {n_sua} việc sửa/hoàn tác video (trần {tran_sua})")
        if ma_loai == LOAI_QUET_VIEW:
            tran_q = _gia_tri(hm, "quet_view_ngay")
            n_q = kho.dem_trong_ngay(LOAI_QUET_VIEW, hom_nay)
            if n_q >= tran_q:
                raise VuotHanMuc(f"hôm nay đã tạo {n_q} việc quet_view_hang_ngay (trần quet_view_ngay {tran_q})")
    if loai.ton_tien:
        _kiem_ton_tien(kho, ma_loai, tham_so, hm, luc, viec_id, hom_nay)
    if luc == "tao":
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
