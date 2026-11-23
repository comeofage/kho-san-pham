"""Danh mục học tự động — khoá đặc trưng, ngưỡng, mẫu câu, nhãn lý do (docs/hoc-tu-dong.md §3.6, §3.7, §4.1, §4.1b).

Nguyên tắc (§6.1):
- Thuần, chỉ stdlib, KHÔNG I/O, không đọc env hay đường dẫn lúc import.
- Mọi chữ đi ra ngoài (mã, tên, mẫu câu gợi ý, câu lỗi) là HẰNG trong file này. `ghep_goi_y`/`render_goi_y` chỉ ghép
  mẫu cố định với SỐ NGUYÊN đã kiểm — không bao giờ nhận chuỗi tự do từ caption, log hay `hoc.db`.
- Caption/từ khoá USP chỉ đi qua `chuan_hoa_caption`/`than_caption`/`muc_khop_caption`/`dac_trung_caption` và ra
  thành mã enum; không lưu, không trả lại nội dung.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------------------------------------------
# Mã cố định
# ---------------------------------------------------------------------------------------------------------------
# \Z thay cho $ để "bh…\n" không lọt khi bên gọi dùng .match (moi:so-khop-chuoi-con)
RE_MA_BAI_HOC: re.Pattern = re.compile(r"^bh\d{8}[a-z0-9]{4}\Z", re.ASCII)
NGUON: tuple[str, ...] = ("poster_view", "van_hanh", "sua_tay")
HUONG: tuple[str, ...] = ("tang", "giam")

LY_DO_DUNG: tuple[str, ...] = (
    "poster_khong_mo_duoc", "poster_cu", "poster_thieu", "poster_lech_noi", "repo_khong_doc_duoc",
    "runner_db_khong_mo_duoc", "loi_bat_ngo", "hoc_db_khong_mo_ro",
)
# 8 mã của §9 + 4 mã chuyển "thường ngày" (lịch sử đầy đủ trong su_kien_hoc; KHÔNG hiện ở thay_doi của báo cáo)
LY_DO_CHUYEN: tuple[str, ...] = (
    "dat_nguong_3_ngay", "cho_suc_chua", "dut_chuoi", "het_bang_chung", "doi_chieu", "het_han", "nguoi_hoan_tac",
    "nguoi_bat_lai",
    "dat_lan_dau", "dem_chuoi", "dat_lai_chuoi", "gia_han", "cap_nhat_so_do",
)
LY_DO_THUONG_NGAY: frozenset[str] = frozenset({"dem_chuoi", "dat_lai_chuoi", "gia_han", "cap_nhat_so_do"})
# Bản sao ĐÚNG quet_view.LY_DO_QUET (§3.4a) — test HT-B2 so hai bộ bằng nhau
LY_DO_QUET: tuple[str, ...] = ("ok", "da_quet", "qua_so_lan", "lech_ngay", "thieu_ytdlp", "kenh_cau_hinh_la",
                               "ytdlp_co_cookie", "kenh_loi", "ghi_loi", "duong_dan_thu", "loi_bat_ngo")
# 409: 1 câu của Hoàn tác + 5 câu của Bật lại (§3.8, §4.2) — theo đúng thứ tự xét của bat_lai
LY_DO_409: tuple[str, ...] = ("khong_con_hieu_luc", "khong_the_bat_lai", "qua_han_bat_lai", "trung_dong_mo",
                              "du_hieu_luc", "tat_tu_ap_dung")
LY_DO_KHAC: tuple[str, ...] = ("khong_co_bai_hoc", "chua_co_lan_hoc", "lan_hoc_khong_mo")

# ---------------------------------------------------------------------------------------------------------------
# Ngưỡng (người dùng chốt Q5 + Q7 + Q8 ngày 2026-11-22) — đổi = đổi code + review + cài lại (D8)
# ---------------------------------------------------------------------------------------------------------------
NGUONG: dict[str, int | tuple[int, int]] = {
    "tuoi_video_ngay": (3, 7),             # lần đo thật ở tuổi [3, 7]; video phải ≥ 7 ngày tuổi
    "cua_so_dang_ngay": 60,                # chỉ video đăng trong 60 ngày
    "caption_moi_ben_toi_thieu": 3,        # 3 + 3 caption KHÁC NHAU mỗi nhóm (UID, tài khoản)
    "so_uid_toi_thieu": 20,
    "so_video_toi_thieu": 200,
    "lift_toi_thieu_pt": 15,               # trị tuyệt đối
    "nhat_quan_toi_thieu_pt": 80,          # Q7 (b): ≥ 16/20 cùng chiều
    "ngay_lien_tiep": 3,                   # ngày LỊCH liên tiếp có dữ liệu mới
    "giu_nhat_quan_pt": 60,                # giữ: ≥ 60% cùng chiều và so_uid ≥ 20
    "han_dung_ngay": 14,                   # gia hạn mỗi ngày còn giữ
    "cam_sau_hoan_tac_ngay": 30,           # tính từ tat_luc của dòng ĐANG hoan_tac
    "bat_lai_sau_hoan_tac_ngay": 7,        # Q8 (b): hoàn tác ngày D → bật lại được tới hết D+7
}
NGUONG_VAN_HANH: dict[str, int] = {
    "cua_so_ngay": 14,
    "so_lan_toi_thieu": 3,
    "ty_le_toi_thieu_pt": 20,
    "ngay_lien_tiep": 3,
    "han_dung_ngay": 28,                   # cố định từ bat_luc, không gia hạn, không tự tắt vì hết bằng chứng
}

SO_TOI_DA = 10_000_000                     # trần chung cho mọi số đếm nhận vào

# Theo dõi tuân thủ (§3.6) — HT-B2 tính, `KhoHoc.ghi_tuan_thu` lưu, `BaiHocRa.tuan_thu` đọc ra. Mỗi bài chỉ nhận
# ĐÚNG bộ khoá của nguồn của nó, giá trị là số nguyên ≥ 0:
# - poster_view: so_sp_da_ap = số SP (UID) đã nhận gợi ý (ap_dung); so_sp_theo = số SP trong đó caption làm theo
#   gợi ý (≤ so_sp_da_ap); ty_le_pt = tỉ lệ làm theo, % làm tròn xuống (0–100).
# - van_hanh: lan_truoc = số lần lỗi trong cửa sổ trước khi bật; lan_sau = số lần lỗi trong cửa sổ gần nhất;
#   cua_so_ngay = độ dài cửa sổ (1–366, mặc định NGUONG_VAN_HANH['cua_so_ngay']).
KHOA_TUAN_THU: dict[str, tuple[str, ...]] = {
    "poster_view": ("so_sp_da_ap", "so_sp_theo", "ty_le_pt"),
    "van_hanh": ("lan_truoc", "lan_sau", "cua_so_ngay"),
}

# ---------------------------------------------------------------------------------------------------------------
# Nhãn tiếng Việt cố định cho MỌI mã ở trên
# ---------------------------------------------------------------------------------------------------------------
TEN_LY_DO: dict[str, str] = {
    "": "",
    # tự dừng / lỗi lần học (§4.4)
    "poster_khong_mo_duoc": "Không mở được DB Poster hoặc thiếu bảng/cột",
    "poster_cu": "Nguồn view hôm nay chưa có số mới",
    "poster_thieu": "Lượt đo view hôm nay ít hơn một nửa bình thường",
    "poster_lech_noi": "Dưới một nửa video nối được sản phẩm kho và caption",
    "repo_khong_doc_duoc": "Không đọc được thư mục data/ của kho",
    "runner_db_khong_mo_duoc": "Không mở được runner.db",
    "loi_bat_ngo": "Lỗi bất ngờ",
    "hoc_db_khong_mo_ro": "Không mở được hoc.db ở chế độ chỉ đọc",
    # chuyển trạng thái (§4.2)
    "dat_nguong_3_ngay": "Đạt ngưỡng 3 ngày liên tiếp, bắt đầu áp dụng",
    "cho_suc_chua": "Đủ ngày nhưng hết chỗ áp dụng, đang chờ",
    "dut_chuoi": "Không còn đạt ngưỡng, ứng viên dừng",
    "het_bang_chung": "Hết bằng chứng giữ, tự tắt",
    "doi_chieu": "Số đo đổi chiều, tự tắt",
    "het_han": "Hết hạn dùng",
    "nguoi_hoan_tac": "Chủ kho hoàn tác",
    "nguoi_bat_lai": "Chủ kho bật lại",
    "dat_lan_dau": "Đạt ngưỡng lần đầu, thành ứng viên",
    "dem_chuoi": "Đạt thêm một ngày liên tiếp",
    "dat_lai_chuoi": "Có ngày trống, đếm lại từ 1",
    "gia_han": "Còn đủ bằng chứng, gia hạn",
    "cap_nhat_so_do": "Cập nhật số đo mới, không đổi hạn",
    # lượt quét view (§3.4a)
    "ok": "Quét xong",
    "da_quet": "Hôm nay đã quét xong trước đó",
    "qua_so_lan": "Đã thử quét đủ 3 lần hôm nay",
    "lech_ngay": "Ngày quét khác ngày của máy",
    "thieu_ytdlp": "Máy chưa có yt-dlp",
    "kenh_cau_hinh_la": "channels.json có kênh cấu hình lạ, đã chặn",
    "ytdlp_co_cookie": "Cấu hình yt-dlp có cookie, đã chặn",
    "kenh_loi": "Có kênh quét lỗi, không ghi DB",
    "ghi_loi": "Ghi số view vào DB Poster lỗi",
    "duong_dan_thu": "Đường dẫn thử trỏ vào dữ liệu thật, đã chặn",
    # 409 (câu cố định, web hiện nguyên văn)
    "khong_con_hieu_luc": "bài học không còn hiệu lực",
    "khong_the_bat_lai": ("chỉ bật lại được gợi ý đã từng hiệu lực rồi tự tắt hoặc hết hạn, "
                          "hoặc gợi ý bị hoàn tác trong 7 ngày gần nhất"),
    "qua_han_bat_lai": "đã quá 7 ngày kể từ lúc hoàn tác, không bật lại được nữa",
    "trung_dong_mo": "đang có gợi ý cùng loại đang mở",
    "du_hieu_luc": "đã đủ {so} gợi ý đang dùng",            # {so} = số nguyên hieu_luc_toi_da
    "tat_tu_ap_dung": "đang tắt tự áp dụng (cau_hinh.json)",
    # khác
    "khong_co_bai_hoc": "không có bài học",
    "chua_co_lan_hoc": "chưa có lần học nào",
    "lan_hoc_khong_mo": "lần học của ngày này không ở trạng thái đang chạy",
}

# Mã "thiếu" của một số đo (DoLuong.thieu) → nhãn
TEN_THIEU: dict[str, str] = {
    "so_uid": f"chưa đủ {NGUONG['so_uid_toi_thieu']} sản phẩm",
    "so_video": f"chưa đủ {NGUONG['so_video_toi_thieu']} video",
    "lift": f"lệch dưới {NGUONG['lift_toi_thieu_pt']}%",
    "nhat_quan": f"chưa đủ {NGUONG['nhat_quan_toi_thieu_pt']}% sản phẩm cùng chiều",
    "huong_lech": "hướng không khớp dấu của độ lệch",
    "so_lan": f"chưa đủ {NGUONG_VAN_HANH['so_lan_toi_thieu']} lần trong {NGUONG_VAN_HANH['cua_so_ngay']} ngày",
    "ty_le": f"tỉ lệ dưới {NGUONG_VAN_HANH['ty_le_toi_thieu_pt']}%",
    "chua_co_nguon": "chưa có nguồn",
}


# ---------------------------------------------------------------------------------------------------------------
# Chuẩn hoá caption (§3.6 bước 4, bảng L1–L5 ở §2.2)
# ---------------------------------------------------------------------------------------------------------------
_RE_SO_THU_TU = re.compile(r"^\s*\d+\.\s*")
_RE_TRANG = re.compile(r"\s+")
_RE_HASHTAG = re.compile(r"#\S+")
L4_DO_DAI_TOI_THIEU = 20


def chuan_hoa_caption(s: str) -> str:
    """NFC → strip → bỏ số thứ tự đầu dòng `N.` → gộp khoảng trắng."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFC", s).strip()
    s = _RE_SO_THU_TU.sub("", s, count=1)
    return _RE_TRANG.sub(" ", s).strip()


def than_caption(s: str) -> str:
    """`chuan_hoa_caption` + bỏ mọi `#hashtag` (gộp lại khoảng trắng để so khớp ổn định)."""
    return _RE_TRANG.sub(" ", _RE_HASHTAG.sub("", chuan_hoa_caption(s))).strip()


def muc_khop_caption(caption: str, dong_captions: Iterable[str]) -> str:
    """'L1'..'L5' — so caption đã đăng với các dòng captions.txt của CHÍNH UID. So nguyên chuỗi / so đầu chuỗi
    (L4), không bao giờ so chuỗi con."""
    if not isinstance(caption, str) or not caption.strip():
        return "L5"
    dong = [d for d in dong_captions if isinstance(d, str)]
    if caption.strip() in {d.strip() for d in dong}:
        return "L1"
    if chuan_hoa_caption(caption) in {chuan_hoa_caption(d) for d in dong}:
        return "L2"
    b = than_caption(caption)
    if not b:
        return "L5"
    thans = {than_caption(d) for d in dong}
    if b in thans:
        return "L3"
    if len(b) >= L4_DO_DAI_TOI_THIEU and any(
            len(x) >= L4_DO_DAI_TOI_THIEU and (x.startswith(b) or b.startswith(x)) for x in thans):
        return "L4"
    return "L5"


# ---------------------------------------------------------------------------------------------------------------
# Đặc trưng caption (7 khoá, định nghĩa theo K20 — §2.2)
# ---------------------------------------------------------------------------------------------------------------
CAPTION_NGAN_DUOI = 60
_RE_EMOJI = re.compile("[" + chr(0x1F300) + "-" + chr(0x1FAFF) + chr(0x2600) + "-" + chr(0x27BF) + "]")
_RE_SO = re.compile(r"\d")
# Tập động từ mà `cap_menh_lenh` ĐO (giữ nguyên để số đo cũ so được với số đo mới)
DONG_TU_MENH_LENH: tuple[str, ...] = ("mua", "đừng", "thử", "xem", "săm", "chốt", "lưu", "tậu")
# Động từ hối thúc mua — đo nhưng KHÔNG bao giờ khuyên (mẫu chiều tăng nói "không hối thúc", HT-B4 mục 3(iv)).
# HT-B4b mục 1: "săm" là cách viết lóng của "sắm" (mua sắm); "đừng" dễ dẫn tới mẫu FOMO "Đừng bỏ lỡ…"
DONG_TU_HOI_THUC: frozenset[str] = frozenset({"mua", "chốt", "tậu", "săm", "đừng"})
# Động từ mẫu gợi ý chiều tăng được liệt kê: tập con của tập đo (không khuyên điều chưa đo), bỏ động từ hối thúc
DONG_TU_GOI_Y_MENH_LENH: tuple[str, ...] = tuple(x for x in DONG_TU_MENH_LENH if x not in DONG_TU_HOI_THUC)
# "lưu ý" là câu dặn, không phải rủ hành động → neo `lưu(?! ý)` (than_caption đã gộp khoảng trắng)
_PHU_DINH_SAU: dict[str, str] = {"lưu": "(?! ý)"}
_RE_MENH_LENH = re.compile(
    "(" + "|".join(re.escape(x) + _PHU_DINH_SAU.get(x, "") for x in DONG_TU_MENH_LENH) + r")\b", re.IGNORECASE)
_RE_BAN = re.compile(r"\bbạn\b", re.IGNORECASE)


def _chuan_tu_khoa(tu_khoa_usp: Iterable[str]) -> tuple[str, ...]:
    ra = []
    for k in tu_khoa_usp or ():
        if isinstance(k, str):
            k = _RE_TRANG.sub(" ", unicodedata.normalize("NFC", k).lower()).strip()
            if k:                              # từ khoá rỗng sẽ "khớp" mọi caption → bỏ
                ra.append(k)
    return tuple(ra)


def _co_cum(than_lower: str, cum: str) -> bool:
    """Cụm xuất hiện NGUYÊN (không dính chữ hai đầu) — tránh 'da' khớp 'dao'."""
    return re.search(r"(?<!\w)" + re.escape(cum) + r"(?!\w)", than_lower) is not None


def _f_cau_hoi(c: str, _u: tuple[str, ...]) -> bool:
    return "?" in than_caption(c)


def _f_co_so(c: str, _u: tuple[str, ...]) -> bool:
    return _RE_SO.search(than_caption(c)) is not None


def _f_ngan(c: str, _u: tuple[str, ...]) -> bool:
    return len(than_caption(c)) < CAPTION_NGAN_DUOI


def _f_emoji(c: str, _u: tuple[str, ...]) -> bool:
    return _RE_EMOJI.search(c if isinstance(c, str) else "") is not None


def _f_menh_lenh(c: str, _u: tuple[str, ...]) -> bool:
    return _RE_MENH_LENH.match(than_caption(c)) is not None


def _f_goi_ban(c: str, _u: tuple[str, ...]) -> bool:
    return _RE_BAN.search(than_caption(c)) is not None


def _f_nhac_usp(c: str, u: tuple[str, ...]) -> bool:
    than = than_caption(c).lower()
    return any(_co_cum(than, k) for k in _chuan_tu_khoa(u))


# ---------------------------------------------------------------------------------------------------------------
# Khoá vận hành (§3.6 "Nguồn van_hanh") — so chuỗi cố định do runner sinh, neo đầu/so nguyên
# ---------------------------------------------------------------------------------------------------------------
_MAU_THIEU_DAU_RA = ("agent báo xong nhưng chưa thấy đầu ra",      # phieu.py:460
                     "chưa thấy đủ đầu ra sau khi chạy")            # vong_lap.py:1669
_RE_QUA_GIO = re.compile(r"^Quá giờ ")                             # vong_lap.py:1742
_RE_VOICE_PV_MA_2 = re.compile(r"^Bước voice_pv thoát mã 2(?::|\s|\Z)")   # vong_lap.py:1747-1748 (không khớp mã 21)
_RE_TU_THOAT = re.compile(r"^Phiên Claude tự thoát")              # vong_lap.py:2342


def _f_pt_thieu_dau_ra(lo_ngai: str, _u: tuple[str, ...]) -> bool:
    """`ket_qua.lo_ngai` là các câu nối bằng '; ' (vong_lap.py:1675) → so NGUYÊN từng câu."""
    if not isinstance(lo_ngai, str):
        return False
    return any(p.strip() in _MAU_THIEU_DAU_RA for p in lo_ngai.split(";"))


def _f_qua_gio(loi: str, _u: tuple[str, ...]) -> bool:
    return isinstance(loi, str) and _RE_QUA_GIO.match(loi) is not None


def _f_voice_pv_ma_2(loi: str, _u: tuple[str, ...]) -> bool:
    return isinstance(loi, str) and _RE_VOICE_PV_MA_2.match(loi) is not None


def _f_tu_thoat(loi: str, _u: tuple[str, ...]) -> bool:
    return isinstance(loi, str) and _RE_TU_THOAT.match(loi) is not None


@dataclass(frozen=True)
class DacTrung:
    khoa: str
    ten: str
    nguon: str
    ham: Callable[[str, tuple[str, ...]], bool]
    goi_y: dict[str, str]          # 'tang'|'giam' → mẫu str.format({lift_pt},{so_uid},{so_cung_chieu},{so_viec})
    ap_phieu: bool


_SO_CAP = "({so_uid} sản phẩm, {so_cung_chieu}/{so_uid} cùng chiều)"
_CAO = "view trung vị cao hơn {lift_pt}% " + _SO_CAP + "."
_THAP = "view trung vị thấp hơn {lift_pt}% " + _SO_CAP + "."


def _cap(khoa: str, ten: str, ham: Callable[[str, tuple[str, ...]], bool], tang: str, giam: str) -> DacTrung:
    return DacTrung(khoa, ten, "poster_view", ham,
                    {"tang": f"{ten}: {_CAO} {tang}", "giam": f"{ten}: {_THAP} {giam}"}, True)


def _vh(khoa: str, ten: str, ham: Callable[[str, tuple[str, ...]], bool], mau: str, ap_phieu: bool) -> DacTrung:
    return DacTrung(khoa, ten, "van_hanh", ham, {"tang": mau}, ap_phieu)


# Mẫu câu caption (HT-B4 mục 3): là ƯU TIÊN MỀM — chiều tăng dạng "Nếu sản phẩm có … thì ưu tiên khoảng N/100", không
# quota cứng (quota dễ khiến agent bịa thông số; skill chỉ cho tả điều có trong mô tả/ảnh). Mọi mẫu phải để caption
# làm theo vẫn qua `tools/kho.py: kiem_captions` (không mở đầu dòng bằng con số, không lặp một vế ≥ 4 chữ ở > 4 dòng).
# Con số N phải khớp `hoc_tu_dong.NGUONG_TUAN_THU` (test khoá).
DANH_MUC_HOC: dict[str, DacTrung] = {d.khoa: d for d in (
    _cap("cap_co_so", "Caption có con số cụ thể", _f_co_so,
         "Nếu trang hoặc ảnh sản phẩm có số đo, dung tích, số món thì ưu tiên khoảng 40/100 caption nhắc số đó, "
         "không mở đầu dòng bằng con số; không dùng giá, %, số đã bán hay khuyến mãi.",
         "Trong 100 caption, nên để không quá khoảng 20/100 caption có con số; còn lại tả công dụng bằng lời."),
    _cap("cap_ngan", "Caption ngắn (thân dưới 60 ký tự)", _f_ngan,
         "Nếu sản phẩm tả gọn được thì ưu tiên khoảng 40/100 caption có thân dưới 60 ký tự (chưa tính hashtag), "
         "vẫn đủ 5 hashtag.",
         "Trong 100 caption, viết phần lớn caption có thân từ 60 ký tự trở lên, cả dòng vẫn không quá 150 ký tự."),
    _cap("cap_nhac_usp", "Caption nhắc từ khoá USP", _f_nhac_usp,
         "Nếu usp.json có tu_khoa thì ưu tiên khoảng 40/100 caption lồng một cụm tu_khoa vào câu, mỗi caption "
         "diễn đạt khác nhau, không lặp nguyên một vế câu ở nhiều dòng.",
         "Trong 100 caption, nên để không quá khoảng 20/100 caption nhắc nguyên văn cụm trong tu_khoa của "
         "usp.json; còn lại tả lợi ích bằng lời khác."),
    _cap("cap_goi_ban", "Caption gọi người xem là \"bạn\"", _f_goi_ban,
         "Nếu hợp giọng của sản phẩm thì ưu tiên khoảng 30/100 caption nói trực tiếp với người xem bằng "
         "chữ \"bạn\".",
         "Trong 100 caption, nên để không quá khoảng 15/100 caption có chữ \"bạn\"; còn lại tả sản phẩm trực tiếp."),
    _cap("cap_menh_lenh", "Caption mở đầu bằng động từ rủ hành động", _f_menh_lenh,
         "Nếu hợp tình huống thì ưu tiên khoảng 30/100 caption mở đầu bằng động từ "
         + ", ".join(DONG_TU_GOI_Y_MENH_LENH) + "; không hối thúc, không khuyến mãi, "
         "không dùng 'ngay', 'kẻo hết', 'đừng bỏ lỡ'.",
         "Trong 100 caption, nên để không quá khoảng 15/100 caption mở đầu bằng động từ rủ hành động; "
         "còn lại mở đầu bằng tên hoặc công dụng sản phẩm."),
    _cap("cap_cau_hoi", "Caption có câu hỏi", _f_cau_hoi,
         "Nếu sản phẩm có tình huống dùng rõ thì ưu tiên khoảng 30/100 caption có một câu hỏi ngắn gợi tình huống "
         "đó.",
         "Trong 100 caption, nên để không quá khoảng 15/100 caption có dấu hỏi."),
    _cap("cap_emoji", "Caption có emoji", _f_emoji,
         "Nếu hợp nội dung thì ưu tiên khoảng 40/100 caption có 1 đến 2 emoji hợp nội dung.",
         "Trong 100 caption, nên để không quá khoảng 20/100 caption có emoji."),
    _vh("pt_thieu_dau_ra", "Phân tích báo xong mà thiếu đầu ra", _f_pt_thieu_dau_ra,
        "Nhắc từ vận hành: {so_uid}/{so_viec} lần phân tích gần đây báo xong mà thiếu đầu ra. Chỉ báo DONE khi "
        "kho.py ghi đã in \"✓ đã đẩy lên GitHub\" và kho.py rui-ro đã nhận.", True),
    _vh("pt_qua_gio", "Phân tích bị quá giờ", _f_qua_gio,
        "Nhắc từ vận hành: {so_uid}/{so_viec} lần phân tích gần đây bị quá giờ. Làm gọn: ghi file ngay sau mỗi "
        "bước, không làm lại bước đã xong, không mở thêm việc ngoài phiếu.", True),
    _vh("voice_pv_ma_2", "Voice PerfectVoice thoát mã 2", _f_voice_pv_ma_2,
        "Báo cáo vận hành: {so_uid}/{so_viec} lần voice PerfectVoice gần đây thoát mã 2.", False),
    _vh("douyin_qua_gio", "Tìm Douyin bị quá giờ", _f_qua_gio,
        "Báo cáo vận hành: {so_uid}/{so_viec} lần tìm Douyin gần đây bị quá giờ.", False),
    _vh("taovideo_tu_thoat", "Tạo video: phiên Claude tự thoát", _f_tu_thoat,
        "Báo cáo vận hành: {so_uid}/{so_viec} lần tạo video gần đây có phiên Claude tự thoát.", False),
)}

# Khoá vận hành → loại việc runner.db mà HT-B2 đếm (bảng §3.6)
LOAI_VIEC_VAN_HANH: dict[str, str] = {
    "pt_thieu_dau_ra": "phan_tich_uid", "pt_qua_gio": "phan_tich_uid", "voice_pv_ma_2": "voice_pv",
    "douyin_qua_gio": "douyin_uid", "taovideo_tu_thoat": "taovideo",
}


def dac_trung_caption(caption: str, tu_khoa_usp: tuple[str, ...]) -> frozenset[str]:
    """Tập khoá caption (trong 7 khoá) mà caption có. `tu_khoa_usp` tự NFC + lower, bỏ cụm rỗng."""
    u = _chuan_tu_khoa(tu_khoa_usp)
    c = caption if isinstance(caption, str) else ""
    return frozenset(k for k, d in DANH_MUC_HOC.items() if d.nguon == "poster_view" and d.ham(c, u))


# ---------------------------------------------------------------------------------------------------------------
# Xét ngưỡng một số đo (dùng chung cho HT-B2 và kho_hoc — không tin cờ dat/giu do bên đo gửi một mình)
# ---------------------------------------------------------------------------------------------------------------
def xet_nguong(dl: Mapping[str, Any]) -> tuple[bool, bool, list[str]]:
    """(dat, giu, thieu) theo NGUONG / NGUONG_VAN_HANH. `dl` có các trường số của DoLuong.

    Gợi ý cho bên đo: tính `nhat_quan_pt` bằng phép chia LÀM TRÒN XUỐNG (100*k//n) để 79,5% không thành 80."""
    nguon = dl.get("nguon")
    so_uid = int(dl.get("so_uid", 0))
    nq = int(dl.get("nhat_quan_pt", 0))
    if nguon == "van_hanh":
        thieu = []
        if so_uid < NGUONG_VAN_HANH["so_lan_toi_thieu"]:
            thieu.append("so_lan")
        if nq < NGUONG_VAN_HANH["ty_le_toi_thieu_pt"]:
            thieu.append("ty_le")
        return not thieu, False, thieu               # vận hành không có luật "giữ" (§4.1b)
    if nguon != "poster_view":
        return False, False, ["chua_co_nguon"]
    lift = int(dl.get("lift_pt", 0))
    huong = dl.get("huong")
    lech = lift == 0 or (lift > 0) != (huong == "tang")
    thieu = []
    if lech:
        thieu.append("huong_lech")
    if so_uid < NGUONG["so_uid_toi_thieu"]:
        thieu.append("so_uid")
    if int(dl.get("so_video", 0)) < NGUONG["so_video_toi_thieu"]:
        thieu.append("so_video")
    if abs(lift) < NGUONG["lift_toi_thieu_pt"]:
        thieu.append("lift")
    if nq < NGUONG["nhat_quan_toi_thieu_pt"]:
        thieu.append("nhat_quan")
    giu = not lech and so_uid >= NGUONG["so_uid_toi_thieu"] and nq >= NGUONG["giu_nhat_quan_pt"]
    return not thieu, giu, thieu


# ---------------------------------------------------------------------------------------------------------------
# Ghép câu gợi ý — CHỈ mẫu cố định + số nguyên đã kiểm (§3.7, §6.1)
# ---------------------------------------------------------------------------------------------------------------
TIEU_DE_GOI_Y = ("GỢI Ý ĐÃ HỌC TỪ VIEW THẬT (runner tự cập nhật; chỉ là ưu tiên mềm — luật caption/USP/rủi ro "
                 "của skill luôn đứng trên):")
SO_DONG_GOI_Y_TOI_DA = 6                   # cả khối, kể cả dòng tiêu đề → tối đa 5 bài học (= trần hiệu lực)


def _so(x: Any, lo: int, hi: int) -> int | None:
    """Đúng kiểu int (không bool, không float, không chuỗi) và trong [lo, hi]; ngược lại None."""
    if type(x) is not int or not (lo <= x <= hi):
        return None
    return x


def ghep_goi_y(muc: dict) -> str | None:
    """Câu gợi ý của một bài học (không gồm mã). Sai bất kỳ trường nào → None. Trường dùng: khoa, nguon, huong,
    so_uid, và lift_pt + so_cung_chieu (caption) hoặc so_viec (vận hành)."""
    if not isinstance(muc, Mapping):
        return None
    khoa = muc.get("khoa")
    dt = DANH_MUC_HOC.get(khoa) if isinstance(khoa, str) else None
    if dt is None or muc.get("nguon") != dt.nguon:
        return None
    huong = muc.get("huong")
    mau = dt.goi_y.get(huong) if huong in HUONG else None
    # vận hành: bằng chứng được làm mới mỗi lần đo (HT-B1b mục 8) nên số lần lỗi có thể về 0 — câu "0/m" vẫn đúng
    # và bài vẫn sống trọn hạn (§4.1b); caption cần ≥ 1 sản phẩm
    so_uid = _so(muc.get("so_uid"), 0 if dt.nguon == "van_hanh" else 1, SO_TOI_DA)
    if mau is None or so_uid is None:
        return None
    if dt.nguon == "van_hanh":
        so_viec = _so(muc.get("so_viec"), max(1, so_uid), SO_TOI_DA)
        if so_viec is None:
            return None
        return mau.format(lift_pt=0, so_uid=so_uid, so_cung_chieu=0, so_viec=so_viec)
    lift = _so(muc.get("lift_pt"), -100, SO_TOI_DA)
    so_cung = _so(muc.get("so_cung_chieu"), 0, so_uid)
    if lift is None or so_cung is None or lift == 0 or (lift > 0) != (huong == "tang"):
        return None
    return mau.format(lift_pt=abs(lift), so_uid=so_uid, so_cung_chieu=so_cung, so_viec=0)


def render_goi_y(ds: list[dict]) -> tuple[list[str], int]:
    """(các dòng của khối gợi ý cho phiếu phan_tich_uid, số mục bị bỏ).

    Mỗi mục phải: mã đúng RE_MA_BAI_HOC, chưa lặp, trang_thai == 'hieu_luc', khoá thuộc danh mục và được vào phiếu,
    `ghep_goi_y` hợp lệ. Sai một điều → bỏ cả mục. Khối = tiêu đề + tối đa 5 dòng; không có mục hợp lệ → ([], n)."""
    dong: list[str] = []
    da_co: set[str] = set()
    bo = 0
    for muc in ds if isinstance(ds, list) else []:
        cau = None
        if isinstance(muc, Mapping):
            ma = muc.get("ma")
            dt = DANH_MUC_HOC.get(muc.get("khoa")) if isinstance(muc.get("khoa"), str) else None
            if (isinstance(ma, str) and RE_MA_BAI_HOC.fullmatch(ma) and ma not in da_co
                    and muc.get("trang_thai") == "hieu_luc" and dt is not None and dt.ap_phieu):
                cau = ghep_goi_y(muc)
        if cau is None or len(dong) >= SO_DONG_GOI_Y_TOI_DA - 1:
            bo += 1
            continue
        da_co.add(muc["ma"])
        dong.append(f"- [{muc['ma']}] {cau}")
    return ([TIEU_DE_GOI_Y, *dong] if dong else []), bo
