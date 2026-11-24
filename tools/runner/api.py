"""HTTP API của bộ chạy việc (docs/bo-chay-viec.md §8.1, §4.3, §8.3) — phiếu B-2 (đợt 3), B-3 (đợt 4).

Hai lớp kiểm cho mọi request:
- `x-runner-key` (so hằng thời gian bằng hmac.compare_digest) cho MỌI route, kể cả route lạ;
- chữ ký Ed25519 của Worker (`chu_ky.kiem_request`) cho MỌI POST. `boi` chỉ được tin vì nằm trong body đã ký.

`tra-loi` chỉ nhận giá trị nút (quy tắc khớp Worker: chuỗi 1–120 đơn vị UTF-16, không ký tự điều khiển
[\\x00-\\x1f\\x7f] kể cả \\t).

Đợt 4 (chỉ khi dot_bat hiệu lực ≥ 4, ngược lại 404):
- `GET /poster/folders` → `{"folders": [{"id": int, "ten": str}]}` (502 khi không đọc được Poster);
- `POST /viec/<id>/duyet` body `{loi_duyet, duyet_luc, boi, chu_ky_duyet}`: chỉ việc `ton_tien` đang `cho_duyet`,
  người duyệt ∈ NGUOI_DUYET (403), chữ ký `kho-duyet-v1` khớp dữ liệu ĐANG LƯU (401), hạn mức lúc duyệt (429)
  → `cho` + `buoc='chay'` + lưu 4 trường duyệt.
- D9 (FX-11): lời duyệt chỉ tiêu một lần (sổ trên Worker). `POST /viec/<id>/chay-tiep` với việc tốn tiền → 409
  `{"loi": "Việc tốn tiền: cần duyệt lại"}`; `POST /viec/<id>/xin-duyet-lai` (chỉ tốn tiền, đang loi/can_tra_loi)
  → `cho_duyet` + xoá 4 trường duyệt (genmax chưa có ước tính → `cho` + `buoc='uoc_tinh'`); trả `{viec}`.
- FX-14: `POST /viec/<id>/tra-loi` với việc tốn tiền → 409 (A-D9b); `xin-duyet-lai` ghi `ket_qua.duyet_lai_tu`
  + `ket_qua.ly_do_duyet_lai` (§5.2) cho lượt resume; `GET /suc-khoe` có `chan_ton_tien` (bool).
- `GET /viec/<id>` trả `tham_so_chuan` (chuỗi JSON chuẩn) để Worker ký lời duyệt.

Đợt 5 (D11, B-4 — §7.6, §8.1): `taovideo` chạy bằng phiên sống.
- `viec` trả ra thêm `phien_song` (bool, do `co_phien_song(id)` của vòng chạy) và `co_the_xin_duyet_lai` (bool; False
  khi còn phiên sống). `xin-duyet-lai` khi còn phiên sống → 409.
- `POST /viec/<id>/tra-loi` với `taovideo`: body `{tra_loi, boi, da_xac_nhan_mat_khau?}` (cờ do Worker đặt sau khi
  kiểm mật khẩu; phải là bool). `kiem_tra_loi_dot5`: chon/cau_hoi cần cờ = true (thiếu → 403); viec_tay/khong_ro chỉ
  nút. Hợp lệ → `tra_loi_song(id, boi, gia_tri)` (BoChay, A-5) xếp tin vào stdin, không tiêu lời duyệt. Không có phiên
  → 409 `LOI_PHIEN_DA_DONG`. Loại tốn tiền khác giữ 409 (A-D9b).
- `POST /viec` taovideo `du_an_b:"tu_tim"` không chốt được → 400 `{loi, ung_vien_b:[{ma, ten, co_takes}]}`.

Đợt 6 — sửa video (D10, docs/sua-video.md §8.1; mở khi dot_bat hiệu lực ≥ dot của sua_video = 4, ngược lại 404):
- `GET /sua-video/<uid>` → `{videos: [VideoSua bỏ duong_dan + viec_mo]}`;
- `GET /sua-video/<uid>/<ma_video>` → chi tiết + phụ đề + cảnh + lịch sử (video không sửa được vẫn 200, kèm ly_do);
- `GET /sua-video/<uid>/<ma_video>/ung-vien?seg=<0–199>` → `{ung_vien}`;
- `POST /sua-video/<uid>/<ma_video>/ban-sua` (ký) → 201 `{ban_sua, du_an, tom_tat}` · 400 · 404 · 409 · 413.
`sua_luc` là MILI GIÂY (st_mtime_ns // 1_000_000, như sua_video.py). Việc `sua_video` tạo qua `POST /viec` có sẵn:
api kiểm ban_sua có trong bảng, đúng video, sua_luc còn khớp; `hoan_tac_sua` chỉ khi viec_goc là lần sửa ĐÃ xong gần
nhất chưa hoàn tác. Hai loại không bao giờ cùng mở trên một ma_video (409 `trung`).
FX-22 (§7.2a): sua_video mà ban_sua có `phu_de` → `chay-lai`/`chay-tiep` 409 LOI_SUA_CHU_CAN_MAT_KHAU, `viec` có
`co_the_chay_lai`/`co_the_chay_tiep` = false + `can_luu_lai_mat_khau` = true. Việc sửa video `loi` do mã thoát 2/5:
`ket_qua` thêm {ma_thoat, kiem_tay, do_dang, chua_doi_gi, bo_qua, ly_do_sua, canh_bao_sua, thong_diep}.
FX-24: `kiem_tay` = true → `co_the_chay_tiep` = false và `chay-tiep` 409 `{loi: thong_diep, kiem_tay: true}`.
`tra-loi` phiên sống cần `ma_cau_hoi` (^q[0-9a-f]{12}$) bằng `cau_hoi.ma` đang lưu; thiếu/sai/lệch → 409
LOI_CAU_HOI_DA_DOI; đúng → `tra_loi_song(id, boi, gia_tri, ma_cau_hoi)`. Việc khác bỏ qua `ma_cau_hoi`.
`POST /viec/<id>/nhan-tin` {noi_dung, ngat, boi, da_xac_nhan_mat_khau} (docs §7.6a): chỉ đạo việc phiên sống →
`nhan_tin_song(id, boi, noi_dung, ngat)`; thiếu cờ mật khẩu 403, không có phiên 409, nhắn khi đang hỏi 409.

Mọi lỗi bất ngờ trong handler → 500 JSON (không lộ chi tiết), log đủ traceback; server vẫn sống.
"""
from __future__ import annotations

import hmac
import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import chu_ky
from . import hoc_danh_muc as hdm
from . import radar_uid_tinh as rut
from . import sua_video as sv
from .danh_muc import (DANH_MUC, LOAI_CHI_HE_THONG, LOAI_KHONG_CHAY_LAI, LoaiViec, ds_folder_poster, lay_loai,
                       tham_so_chuan, video_cua_tham_so)
from .du_an import ds_du_an
from .han_muc import HAN_MUC_TRAN, LOAI_SUA_VIDEO, han_muc_hoc, han_muc_radar, kiem_han_muc
from .kho_hoc import KhoHoc, KhongCoBaiHoc, SaiTrangThaiHoc
from .kho_radar_uid import GOC_TOI_DA, LOI_DANG_TIM, RE_ANH, KhongCoRadar, KhoRadarUid, SaiTrangThaiRadar
from .kho_viec import RE_BAN_SUA, KhoViec
from .danh_muc import KHOA_ANH_CHUP_KHO, LOAI_PHIEN_SONG, anh_chup_kho_taovideo
from .kieu import (DANG_MO, RE_MA_CAU_HOI, TRANG_THAI, CanNguoiDung, KhongCoPhien, MoiTruong, SaiTrangThai, ThamSoLoi,
                   TrungViec, VuotHanMuc, gio_vn)
from .phieu import CAU_CHI_DAO, GIA_TRI_KHONG_RO, GIA_TRI_VIEC_TAY, lam_sach_chu

log = logging.getLogger(__name__)

BODY_TOI_DA = 16 * 1024            # khớp video_server / Worker (§3.2)
BODY_XA_TOI_DA = 256 * 1024        # body lớn hơn mức này: không đọc xả, đóng kết nối
TRA_LOI_TOI_DA_UTF16 = 120         # khớp Worker TRA_LOI_TOI_DA (JS String.length = đơn vị UTF-16)
GIOI_HAN_MAC_DINH = 50
GIOI_HAN_TOI_DA = 500
BI_TU_CHOI_TOI_DA = 20             # số mục ket_qua.bi_tu_choi tối đa trả ra (R-05 P2-2)
BI_TU_CHOI_INPUT_TOI_DA = 200      # ký tự tối đa của mỗi `input`/`tool_name`

# Khoá do runner tự gắn vào tham_so (không phải input web). Bỏ đi trước khi kiểm lại ở chay-lai (P3-2).
KHOA_RUNNER_GAN = ("ngay_tao", "ma_ban")
# Đợt 4: người được duyệt việc tốn tiền (người dùng chốt Q2 = A: cả hai).
NGUOI_DUYET = ("nhan", "comeofage")
DOT_DUYET = 4
LOI_DUYET_TOI_DA = 2000            # khớp phieu.TOI_DA_LOI_DUYET
DUYET_LUC_TOI_DA = 40
DUYET_LUC_LECH_TOI_DA_S = 600      # duyet_luc (Worker ký) lệch giờ runner tối đa 10 phút
# Trường của §4.2 KHÔNG trả ra ngoài (§8.1).
TRUONG_AN = ("pid", "pid_tao_luc", "session_id", "chu_ky_duyet")

_RE_ID = r"j\d{14}[a-z0-9]{4}"
_RE_ROUTE_ID = re.compile(rf"^/viec/({_RE_ID})$", re.ASCII)
_RE_ROUTE_LOG = re.compile(rf"^/viec/({_RE_ID})/log$", re.ASCII)
_RE_ROUTE_HANH_DONG = re.compile(
    rf"^/viec/({_RE_ID})/(tra-loi|duyet|tu-choi|huy|chay-tiep|chay-lai|xin-duyet-lai|nhan-tin|luu-tru|bo-luu-tru)$",
    re.ASCII)
LOI_CAN_DUYET_LAI = "Việc tốn tiền: cần duyệt lại"
# D9/A-D9b (FX-14): việc tốn tiền ở can_tra_loi không được trả lời trực tiếp.
LOI_TRA_LOI_TON_TIEN = "Việc tốn tiền: bấm Xin duyệt lại rồi duyệt bằng mật khẩu"
CAU_HOI_LY_DO_TOI_DA = 500         # §5.2: cắt nội dung câu hỏi trong lý do duyệt lại
LY_DO_LOI_KHONG_RO = "lỗi không rõ"
# D9: việc tốn tiền ở trạng thái này được xin duyệt lại (→ cho_duyet, xoá lời duyệt cũ).
TRANG_THAI_XIN_DUYET_LAI = ("loi", "can_tra_loi")
_RE_ROUTE_DU_AN = re.compile(r"^/du-an/(\d{19})$", re.ASCII)
# Đợt 6: sửa video (§8.1). GET: danh sách / chi tiết / ứng viên; POST: ban-sua.
_RE_ROUTE_SUA_GET = re.compile(r"^/sua-video/(\d{19})(?:/([0-9a-f]{16})(/ung-vien)?)?$", re.ASCII)
_RE_ROUTE_SUA_POST = re.compile(r"^/sua-video/(\d{19})/([0-9a-f]{16})/ban-sua$", re.ASCII)
_RE_SEG = re.compile(r"^\d{1,3}$", re.ASCII)
SEG_TOI_DA = 199                   # khớp Worker SUA_SEG_TOI_DA
# Loại chạy tiếp được bằng CÙNG id việc (không cần phiên Claude): bộ chuyển đổi đọc nhật ký _sua/<id>.json để làm
# nốt/hoàn nguyên (§6.1 mã thoát 5, §6.3). Miễn phí; vẫn chặn khi tiến trình cũ có thể còn sống.
LOAI_CHAY_TIEP_NHAT_KY = LOAI_SUA_VIDEO
TRANG_THAI_CHAY_LAI = ("loi", "huy")
LOI_KHONG_THAY_VIDEO = "Không thấy video này (có thể đã bị xoá hoặc đổi tên)"
_RE_UID = re.compile(r"^\d{19}$", re.ASCII)
_RE_SO = re.compile(r"^\d{1,9}$", re.ASCII)
_RE_BOI = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$", re.ASCII)
_RE_DIEU_KHIEN = re.compile("[\x00-\x1f\x7f]")
# Đợt 5: chữ tự do trả lời trong phiên sống. Khớp Worker TRA_LOI_CHU_TOI_DA (code point = len() Python) và
# RE_DIEU_KHIEN_TRU_XUONG_DONG (cấm ký tự điều khiển trừ \n).
TRA_LOI_CHU_TOI_DA = 1000
_RE_DIEU_KHIEN_TRU_XUONG_DONG = re.compile("[\x00-\x09\x0b-\x1f\x7f]")
LOI_PHIEN_DA_DONG = "Phiên đã đóng — dùng Xin duyệt lại"
LOI_CAN_MAT_KHAU_CHU = "Trả lời bằng chữ cần nhập mật khẩu"
LOI_CAN_MAT_KHAU_CHON = "Chọn trong phiên đang chạy cần nhập mật khẩu"
LOI_XIN_DUYET_LAI_KHI_SONG = "Việc đang có phiên sống — trả lời câu hỏi hoặc Huỷ trước khi xin duyệt lại"
# FX-24 (§7.6, S-4 #4): trả lời phiên sống thiếu / sai dạng / lệch mã câu hỏi đang lưu.
LOI_CAU_HOI_DA_DOI = "Câu hỏi đã đổi — tải lại để xem câu mới"
LOI_CHI_DAO_CAN_MAT_KHAU = "Chỉ đạo cần nhập mật khẩu"
LOI_CHI_DAO_DANG_HOI = "Agent đang hỏi — trả lời câu hỏi, hoặc dùng Ngắt & nhắn"
# Việc phiên sống KHÔNG còn phiên ở các trạng thái này: chỉ đạo chỉ được lưu cho lần chạy tiếp.
TRANG_THAI_GHI_CHI_DAO = ("loi", "cho_duyet")
# D15 (docs/hoc-tu-dong.md §3.8): học tự động. Câu 503 web so khớp NGUYÊN VĂN — không đổi chữ.
LOI_HOC_CHUA_BAT = "Học tự động chưa bật"
LOI_CHI_HE_THONG = "loại này chỉ runner tự tạo"
# `ma` sai dạng → không khớp tuyến → 404 (hợp đồng 3 chặng P3-7). Mẫu mã = hoc_danh_muc.RE_MA_BAI_HOC.
_RE_ROUTE_HOC_POST = re.compile(r"^/hoc/bai-hoc/(bh\d{8}[a-z0-9]{4})/(hoan-tac|bat-lai)$", re.ASCII)
_RE_NGAY_HOC = re.compile(r"^\d{4}-\d{2}-\d{2}$", re.ASCII)
HOC_GIOI_HAN_MAC_DINH = 50
HOC_GIOI_HAN_TOI_DA = 200
# 404 của /hoc/*: chỉ 2 câu cố định trong danh mục (web đọc hoc_danh_muc.py để đối chiếu).
_LOI_404_HOC = (hdm.TEN_LY_DO["chua_co_lan_hoc"], hdm.TEN_LY_DO["khong_co_bai_hoc"])


# ---------- Radar UID (docs/radar-uid.md §7, §7.1): 8 route /radar/* ----------
# Câu 503/409 web so khớp NGUYÊN VĂN — không đổi chữ.
LOI_RADAR_CHUA_BAT = "Radar UID chưa bật"
LOI_RADAR_TAT = "Radar UID đang tắt"
LOI_DANG_CHUP = "Đang có lượt chụp chạy"
LOI_NHOM_NGUNG = "Nhóm đã ngừng: bật theo dõi lại trước"
# Uid trong đường dẫn GET: nhận mọi đoạn (sai dạng cũng đi tới kho để ra đúng 404 "Không có UID này trong Radar").
_RE_ROUTE_RADAR_UID = re.compile(r"^/radar/uid/([^/]+)$")
_RE_ROUTE_RADAR_GOC = re.compile(r"^/radar/goc/(\d{19})/(tim-lai|ngung|theo-lai|them-tay)$", re.ASCII)
_RE_ROUTE_RADAR_UID_HD = re.compile(r"^/radar/goc/(\d{19})/uid/(\d{19})/(ghim|bo-ghim|loai|bo-loai)$", re.ASCII)
RADAR_NGAY_DOC = 20                # đọc snapshot trong chừng này ngày (đủ cho chuỗi 14 kỳ + spark 7 kỳ)
RADAR_CHUOI_TOI_DA = 14            # ChiTiet.chuoi: tối đa 14 kỳ gần nhất
RADAR_VIDEO_TOI_DA = 50            # ChiTiet.video: tối đa 50 video của snapshot mới nhất
# Mã ly_do (docs/radar-uid.md §6.3) → câu lời thường cho UI. het_han_muc_goi có số nên dựng trong ten_ly_do_radar.
TEN_LY_DO_RADAR: dict[str, str] = {
    "token_thieu": "Chưa có token EchoTik: đăng nhập EchoTik trên Chrome để tạo lại file token.",
    "token_het_han": "EchoTik trả trang lỗi: token hết hạn hoặc EchoTik từ chối tham số. "
                     "Đăng nhập lại EchoTik trên máy nhà.",
    "rate_limit": "EchoTik giới hạn lượt gọi: thử lại ngày mai.",
    "mang_lien_tiep": "Mất mạng tới EchoTik.",
    "keyword_khong_loc": "EchoTik không lọc theo từ khoá nên không tìm được tương tự: thêm tay UID.",
    "khong_tim_thay": "EchoTik không có UID này.",
    "khong_co_video": "EchoTik chưa có video nào cho UID này.",
    "dinh_dang": "EchoTik trả dữ liệu lạ.",
    "nhom_ngung": "Nhóm đã ngừng theo dõi nên không chụp.",
    "khong_co_nhom": "Chưa có nhóm theo dõi cho UID này: thêm UID gốc trước.",
    "loi_bat_ngo": "Lỗi bất ngờ khi chạy: xem runner.log.",
    "tham_so_sai": "Tham số chạy việc sai (lỗi hệ thống): báo người bảo trì.",
    "khong_chup_duoc": "Không chụp được UID nào hôm nay: kiểm tra EchoTik và mạng, rồi bấm Chụp lại.",
}
CAU_TOKEN_RADAR: dict[str, str] = {"thieu": TEN_LY_DO_RADAR["token_thieu"], "het_han": TEN_LY_DO_RADAR["token_het_han"]}
_HANG_XEP_RADAR = {"dang_co_da": 0, "chua_co_da": 1, "chua_du": 2, "chan": 3}


def ten_ly_do_radar(ly_do: object, goi_hom_nay: int, tran_goi: int) -> str:
    """Câu UI của một mã ly_do (§6.3); mã lạ/rỗng → "" (UI tự có câu dự phòng)."""
    if ly_do == "het_han_muc_goi":
        return f"Hết ngân sách gọi EchoTik hôm nay ({goi_hom_nay}/{tran_goi})."
    return TEN_LY_DO_RADAR.get(ly_do, "") if isinstance(ly_do, str) else ""


def _khoa_sap_radar(u: dict) -> tuple:
    tv, nv = u.get("trung_vi"), u.get("n_video")
    return (u.get("trang_thai") == "loai", _HANG_XEP_RADAR.get(u.get("xep_loai"), len(_HANG_XEP_RADAR)),
            tv is None, -(tv or 0), -(nv or 0), u["uid"])


def sap_xep_uid_ra(ds: list[dict]) -> list[dict]:
    """§5.4: dang_co_da → chua_co_da → chua_du → chan; trong mỗi lớp trung_vi giảm (null cuối), rồi n_video giảm, rồi uid.
    UID đã loại xuống cuối (UI ẩn, vẫn trả để có nút Bỏ loại)."""
    return sorted(ds, key=_khoa_sap_radar)


def dung_uid_ra(lk: dict, snaps: list, hom_nay: datetime, bat_dau_ngay: str) -> dict:
    """UidRa (§7.1) = liên kết (uid/vai/trang_thai/ten/shop/do_giong) + mọi chỉ số của radar_uid_tinh.xep_hang_uid."""
    ra = {"uid": lk["uid"], "vai": lk["vai"], "trang_thai": lk["trang_thai"], "ten": lk["ten"], "shop": lk["shop"],
          "do_giong": lk["do_giong"]}
    ra.update(rut.xep_hang_uid(snaps, hom_nay, bat_dau_ngay))
    return ra


def anh_hop_le(anh: object) -> str:
    """Chỉ trả ảnh khớp RE_ANH (phòng thủ DB cũ/sửa tay); mọi giá trị khác → ''."""
    return anh if isinstance(anh, str) and RE_ANH.fullmatch(anh) is not None else ""


def ban_tong_so(snaps: list) -> int | None:
    """ban_tong của snapshot mới nhất → số nguyên; thiếu/không đọc được → None."""
    if not snaps:
        return None
    moi = max(snaps, key=lambda s: (s["ngay"], s["lay_luc"]))
    so = rut.doc_so_rut_gon(moi["ban_tong"])
    return so.gia_tri if so is not None else None


def _them_nhom_radar(n: dict, ds: list[dict]) -> dict:
    """Khoá thêm RU-B11 của một nhóm: anh/shop từ kho; gia = giá snapshot mới nhất của UID gốc (đã có trong `ds`)."""
    goc = next((u for u in ds if u["uid"] == n["goc"]), None)
    return {"anh": anh_hop_le(n.get("anh")), "shop": n.get("shop") or "", "gia": goc["gia"] if goc else None,
            "n_tuong_tu": int(n.get("n_tuong_tu") or 0), "n_ghim": int(n.get("n_ghim") or 0)}


def dung_chuoi_va_video(snaps: list) -> tuple[list[dict], list[dict]]:
    """ChiTiet.chuoi (≤ 14 kỳ gần nhất) + ChiTiet.video (≤ 50 của snapshot mới nhất, kèm d24 của kỳ cuối nếu hợp lệ).
    Dùng đúng _chuoi_ky của radar_uid_tinh (cùng cách xét "đứng yên" với xep_hang_uid) — test đối chiếu kỳ cuối."""
    snaps = sorted(snaps, key=lambda s: (s["ngay"], s["lay_luc"]))[-(RADAR_CHUOI_TOI_DA + 1):]
    if not snaps:
        return [], []
    cac_ky = rut._chuoi_ky(snaps)
    chuoi = [{"ngay": k.sau["ngay"], "gio": round(k.ky["gio"], 1), "hop_le": k.ky["hop_le"],
              "trung_vi": k.ky["trung_vi"], "tong_delta_top5": k.ky["tong_delta_top5"], "n_video": k.ky["n_video"],
              "n_creator": k.ky["n_creator"], "n_doi": k.ky["n_doi"], "ti_le_doi": k.ky["ti_le_doi"]} for k in cac_ky]
    ky_cuoi = cac_ky[-1].ky if cac_ky else None
    d24 = {vid: d for vid, _creator, d in ky_cuoi["ds_d24"]} if ky_cuoi is not None and ky_cuoi["hop_le"] else {}

    def so_view(v: dict) -> int:
        s = rut.doc_so_rut_gon(v["view"])
        return s.gia_tri if s is not None else -1
    video = [{"video_id": v["video_id"], "creator": v["creator"], "follower": v["follower"], "view": v["view"],
              "d24": d24.get(v["video_id"]), "dang_luc": v["dang_luc"], "is_promote": v["is_promote"]}
             for v in snaps[-1]["videos"].values()]
    video.sort(key=lambda v: (v["d24"] is None, -(v["d24"] or 0), -so_view(v), v["video_id"]))
    return chuoi, video[:RADAR_VIDEO_TOI_DA]


class LoiApi(Exception):
    """Lỗi có mã HTTP chủ động trả (4xx)."""

    def __init__(self, ma: int, thong_diep: str, them: dict | None = None):
        super().__init__(thong_diep)
        self.ma = ma
        self.thong_diep = thong_diep
        self.them = them or {}


# ---------- hàm thuần (test được không cần HTTP) ----------

def do_dai_utf16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def kiem_gia_tri_nut(tra_loi: object) -> str:
    """Cùng quy tắc Worker (cf/src/worker.js traLoiBangNut): chuỗi, khác rỗng, ≤120 UTF-16, không ký tự điều khiển."""
    if not isinstance(tra_loi, str) or not tra_loi:
        raise ThamSoLoi("tra_loi phải là chuỗi khác rỗng")
    if do_dai_utf16(tra_loi) > TRA_LOI_TOI_DA_UTF16:
        raise ThamSoLoi(f"tra_loi dài quá {TRA_LOI_TOI_DA_UTF16} ký tự")
    if _RE_DIEU_KHIEN.search(tra_loi):
        raise ThamSoLoi("tra_loi chứa ký tự điều khiển")
    return tra_loi


def kiem_tra_loi_dot3(cau_hoi: CanNguoiDung, tra_loi: object) -> str:
    """Đợt 3 chỉ nhận giá trị nút. `chon`: so ĐÚNG chuỗi lựa chọn đã lưu. `cau_hoi` (chữ tự do) → ThamSoLoi."""
    gt = kiem_gia_tri_nut(tra_loi)
    if cau_hoi.loai == "chon":
        if gt not in cau_hoi.lua_chon:
            raise ThamSoLoi("trả lời không khớp lựa chọn nào")
        return gt
    if cau_hoi.loai == "viec_tay":
        if gt != GIA_TRI_VIEC_TAY:
            raise ThamSoLoi(f"việc tay chỉ nhận {GIA_TRI_VIEC_TAY!r}")
        return gt
    if cau_hoi.loai == "khong_ro":
        if gt != GIA_TRI_KHONG_RO:
            raise ThamSoLoi(f"không rõ chỉ nhận {GIA_TRI_KHONG_RO!r}")
        return gt
    raise ThamSoLoi("câu hỏi này cần chữ tự do — chưa mở ở đợt 3 (chỉ trả lời bằng nút)")


def kiem_chi_dao(noi_dung: object, ngat: object, da_xac_nhan: object) -> tuple[str, bool]:
    """Body `nhan-tin`: chữ 1–1000 ký tự (cho xuống dòng, không ký tự điều khiển khác), `ngat` bool, luôn cần
    `da_xac_nhan_mat_khau` = true (chỉ đạo có thể khiến agent tiêu thêm tiền trong trần). Trả (chữ đã làm sạch, ngat)."""
    if not isinstance(da_xac_nhan, bool):
        raise ThamSoLoi("da_xac_nhan_mat_khau phải là true/false")
    if not isinstance(ngat, bool):
        raise ThamSoLoi("ngat phải là true/false")
    if not isinstance(noi_dung, str) or len(noi_dung) > TRA_LOI_CHU_TOI_DA:
        raise ThamSoLoi(f"noi_dung phải là chữ 1–{TRA_LOI_CHU_TOI_DA} ký tự")
    if _RE_DIEU_KHIEN_TRU_XUONG_DONG.search(noi_dung):
        raise ThamSoLoi("noi_dung chứa ký tự điều khiển")
    try:
        noi_dung.encode("utf-8")
    except UnicodeEncodeError as e:
        raise ThamSoLoi("noi_dung có ký tự Unicode hỏng") from e
    sach = lam_sach_chu(noi_dung, TRA_LOI_CHU_TOI_DA)
    if not sach:
        raise ThamSoLoi("noi_dung rỗng")
    if not da_xac_nhan:
        raise LoiApi(403, LOI_CHI_DAO_CAN_MAT_KHAU)
    return sach, ngat


def kiem_tra_loi_dot5(cau_hoi: CanNguoiDung, tra_loi: object, da_xac_nhan: bool, ton_tien: bool) -> str:
    """§7.6 (D11). Trả giá trị đưa vào tin stdin; sai hình dạng → ThamSoLoi (400); thiếu mật khẩu → LoiApi 403.
    - chon: đúng một lựa chọn đã lưu; việc tốn tiền cần `da_xac_nhan` (lựa chọn có thể cho tiêu thêm tiền trong trần);
    - cau_hoi: chữ 1–1000 ký tự (không ký tự điều khiển trừ xuống dòng, không surrogate lẻ), luôn cần `da_xac_nhan`
      (D3); trả bản đã lam_sach_chu (lưu vào tra_loi và đưa vào phiếu lần chạy tiếp);
    - viec_tay: "da_lam_xong"; khong_ro: "tiep_tuc" — chỉ nút, không cần mật khẩu."""
    if not isinstance(da_xac_nhan, bool):
        raise ThamSoLoi("da_xac_nhan_mat_khau phải là true/false")
    if cau_hoi.loai == "cau_hoi":
        if not isinstance(tra_loi, str) or len(tra_loi) > TRA_LOI_CHU_TOI_DA:
            raise ThamSoLoi(f"tra_loi phải là chữ 1–{TRA_LOI_CHU_TOI_DA} ký tự")
        if _RE_DIEU_KHIEN_TRU_XUONG_DONG.search(tra_loi):
            raise ThamSoLoi("tra_loi chứa ký tự điều khiển")
        try:
            tra_loi.encode("utf-8")
        except UnicodeEncodeError as e:
            raise ThamSoLoi("tra_loi có ký tự Unicode hỏng") from e
        sach = lam_sach_chu(tra_loi, TRA_LOI_CHU_TOI_DA)
        if not sach:
            raise ThamSoLoi("tra_loi rỗng")
        if not da_xac_nhan:
            raise LoiApi(403, LOI_CAN_MAT_KHAU_CHU)
        return sach
    gt = kiem_gia_tri_nut(tra_loi)
    if cau_hoi.loai == "chon":
        if gt not in cau_hoi.lua_chon:
            raise ThamSoLoi("trả lời không khớp lựa chọn nào")
        if ton_tien and not da_xac_nhan:
            raise LoiApi(403, LOI_CAN_MAT_KHAU_CHON)
        return gt
    if cau_hoi.loai == "viec_tay":
        if gt != GIA_TRI_VIEC_TAY:
            raise ThamSoLoi(f"việc tay chỉ nhận {GIA_TRI_VIEC_TAY!r}")
        return gt
    if cau_hoi.loai == "khong_ro":
        if gt != GIA_TRI_KHONG_RO:
            raise ThamSoLoi(f"không rõ chỉ nhận {GIA_TRI_KHONG_RO!r}")
        return gt
    raise ThamSoLoi(f"loại câu hỏi lạ: {cau_hoi.loai!r}")


def kiem_body_duyet(body: dict, bay_gio: datetime) -> tuple[str, str, str]:
    """(loi_duyet, duyet_luc, chu_ky_duyet) NGUYÊN VĂN (chữ ký tính trên đúng các chuỗi này; không trim/chuẩn hoá).
    - loi_duyet: chuỗi 1–2000 ký tự, không chỉ toàn khoảng trắng (chèn vào phiếu sau khi lam_sach_chu);
    - duyet_luc: ISO 8601 CÓ múi giờ, ≤40 ký tự, lệch giờ runner ≤ 10 phút;
    - chu_ky_duyet: chuỗi (định dạng/độ đúng do chu_ky.kiem_duyet → 401)."""
    loi = body.get("loi_duyet")
    if not isinstance(loi, str) or not loi.strip() or len(loi) > LOI_DUYET_TOI_DA:
        raise ThamSoLoi(f"loi_duyet phải là chữ 1–{LOI_DUYET_TOI_DA} ký tự")
    luc = body.get("duyet_luc")
    if not isinstance(luc, str) or not luc or len(luc) > DUYET_LUC_TOI_DA or _RE_DIEU_KHIEN.search(luc):
        raise ThamSoLoi("duyet_luc sai định dạng")
    try:
        dt = datetime.fromisoformat(luc)
    except ValueError as e:
        raise ThamSoLoi("duyet_luc phải là ISO 8601 có múi giờ") from e
    if dt.tzinfo is None:
        raise ThamSoLoi("duyet_luc phải có múi giờ")
    if abs((dt - gio_vn(bay_gio)).total_seconds()) > DUYET_LUC_LECH_TOI_DA_S:
        raise ThamSoLoi(f"duyet_luc lệch giờ máy nhà quá {DUYET_LUC_LECH_TOI_DA_S // 60} phút")
    ky = body.get("chu_ky_duyet")
    if not isinstance(ky, str):
        raise ThamSoLoi("chu_ky_duyet thiếu")
    return loi, luc, ky


def _khong_che(s: str) -> str:
    return s


def _chuoi_ngan(x: object, toi_da: int, che: Callable[[str], str] = _khong_che) -> str:
    """Chuỗi hoá → che bí mật trên bản ĐẦY ĐỦ → rồi mới cắt (R-06 P3-1/P3-3)."""
    if x is None:
        return ""
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, sort_keys=True, default=str)
    return che(s)[:toi_da]


def che_sau(x: object, che: Callable[[str], str]) -> object:
    """Che mọi chuỗi (giá trị, kể cả lồng trong dict/list) — trả bản mới, không sửa đầu vào."""
    if isinstance(x, str):
        return che(x)
    if isinstance(x, dict):
        return {k: che_sau(v, che) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [che_sau(v, che) for v in x]
    return x


def bi_tu_choi_gon(ds: object, che: Callable[[str], str] | None = None) -> list[dict]:
    """R-05 P2-2: chỉ trả [{tool_name, input ≤200 ký tự}] tối đa 20 mục — kể cả dữ liệu cũ trong DB
    còn nguyên dạng permission_denials thô (tool_use_id, tool_input đầy đủ nội dung file…).
    R-06 P3-3: `che` áp lên chuỗi đầy đủ TRƯỚC khi cắt (dữ liệu cũ trong DB có thể chưa che)."""
    che = che or _khong_che
    if not isinstance(ds, list):
        return []
    ra: list[dict] = []
    for x in ds:
        if len(ra) >= BI_TU_CHOI_TOI_DA:
            break
        if not isinstance(x, dict):
            continue
        if "input" in x and "tool_input" not in x:
            dau_vao: object = x.get("input")
        else:
            ti = x.get("tool_input")
            if isinstance(ti, dict):
                dau_vao = next((ti[k] for k in ("command", "file_path", "path", "pattern", "url")
                                if isinstance(ti.get(k), str)), ti)
            else:
                dau_vao = ti
        ra.append({"tool_name": _chuoi_ngan(x.get("tool_name"), BI_TU_CHOI_INPUT_TOI_DA, che),
                   "input": _chuoi_ngan(dau_vao, BI_TU_CHOI_INPUT_TOI_DA, che)})
    return ra


def co_the_chay_lai(v: dict, sua_chu: bool = False, hom_nay: str | None = None) -> bool:
    """Nút Chạy lại: việc loi/huy, không phải bản sửa có chữ phụ đề (FX-22). D15: loại LOAI_KHONG_CHAY_LAI không bao
    giờ; loại chỉ-hệ-thống còn lại (quet_view_hang_ngay) chỉ lượt của hôm nay (`hom_nay` YYYY-MM-DD, None = không xét
    ngày). Chặn thật nằm ở _tao_viec/kiem_tham_so; cờ này chỉ để web không hiện nút sẽ bị 400."""
    if v.get("trang_thai") not in TRANG_THAI_CHAY_LAI or sua_chu:
        return False
    loai = v.get("loai")
    if loai in LOAI_KHONG_CHAY_LAI:
        return False
    if loai in LOAI_CHI_HE_THONG and hom_nay is not None:
        ts = v.get("tham_so")
        return isinstance(ts, dict) and ts.get("ngay") == hom_nay
    return True


def viec_ra(v: dict, chi_tiet: bool = True, che: Callable[[str], str] | None = None,
            phien_song: bool = False, sua_chu: bool = False, hom_nay: str | None = None) -> dict:
    """Việc trả ra web (§8.1): bỏ trường nhạy cảm, thêm co_session / co_the_chay_tiep / co_the_chay_lai /
    co_the_xin_duyet_lai / can_luu_lai_mat_khau / phien_song (đợt 5: vòng chạy đang giữ phiên Claude sống của việc —
    handler hỏi `co_phien_song`).

    `sua_chu` (FX-22, §7.2a): việc sua_video mà bản sửa có đổi chữ phụ đề (handler tra bảng ban_sua) → không chạy
    lại / chạy tiếp bằng nút, phải lưu lại qua màn Sửa video kèm mật khẩu.
    Việc sửa video ở `loi` do bộ chuyển đổi thoát mã 2/5: `ket_qua` thêm kiem_tay/do_dang/chua_doi_gi/bo_qua/
    thong_diep… (sua_video.doc_ket_thuc_loi, suy từ `loi`, không lưu DB).
    `ket_qua.bi_tu_choi`: danh sách (chi_tiet=False) bỏ hẳn; chi tiết → bản gọn (bi_tu_choi_gon).
    `che` (R-06 P3-3): che mọi chuỗi trả ra (loi, ghi_chu, can_ban, cau_hoi, ket_qua…) — dữ liệu cũ trong DB
    có thể chưa che. None = không che (giữ chữ ký cũ). Không sửa dict `v` gốc.
    """
    d = {k: x for k, x in v.items() if k not in TRUONG_AN}
    kq = d.get("ket_qua")
    if v.get("trang_thai") == "loi":
        them = sv.doc_ket_thuc_loi(v.get("loai"), v.get("loi"))
        if them is not None:
            kq = {**(kq if isinstance(kq, dict) else {}), **them}
            d["ket_qua"] = kq
    bi_tu_choi = None
    if isinstance(kq, dict) and "bi_tu_choi" in kq:
        kq = dict(kq)
        bi_tu_choi = kq.pop("bi_tu_choi")
        d["ket_qua"] = kq
    if che is not None:
        d = che_sau(d, che)
    if bi_tu_choi is not None and chi_tiet:
        d["ket_qua"]["bi_tu_choi"] = bi_tu_choi_gon(bi_tu_choi, che)
    d["co_session"] = bool(v.get("session_id"))
    d["co_the_chay_tiep"] = co_the_chay_tiep(v, sua_chu)
    d["co_the_chay_lai"] = co_the_chay_lai(v, sua_chu, hom_nay)
    d["can_luu_lai_mat_khau"] = bool(sua_chu)
    d["phien_song"] = bool(phien_song)
    d["co_the_xin_duyet_lai"] = co_the_xin_duyet_lai(v, bool(phien_song))
    return d


def tien_trinh_cu_con_song(v: dict) -> bool:
    """R-07 P2-4: vòng chạy không giết được tiến trình của việc → đánh dấu `ket_qua.khong_giet_duoc`."""
    kq = v.get("ket_qua")
    return isinstance(kq, dict) and kq.get("khong_giet_duoc") is True


def la_ton_tien(v: dict) -> bool:
    """Loại của việc là tốn tiền (theo danh mục trong code, không theo dữ liệu việc)."""
    loai = DANH_MUC.get(v.get("loai")) if isinstance(v.get("loai"), str) else None
    return loai is not None and loai.ton_tien


def thong_diep_kiem_tay(v: dict) -> str | None:
    """FX-24 (từ FX-22): việc sửa video `loi` vì bộ chuyển đổi CỐ Ý bỏ qua mục việc khác đã đổi (`kiem_tay`) → thông
    điệp cho người dùng; chạy tiếp không giúp được. Suy từ `loi` bằng sv.doc_ket_thuc_loi (như viec_ra), hoặc
    `ket_qua.kiem_tay` đã lưu. Không phải trường hợp đó → None."""
    if v.get("loai") not in LOAI_SUA_VIDEO or v.get("trang_thai") != "loi":
        return None
    them = sv.doc_ket_thuc_loi(v.get("loai"), v.get("loi"))
    if them is not None and them.get("kiem_tay") is True:
        return str(them.get("thong_diep") or "Cần kiểm tay — chạy tiếp không giúp được")
    kq = v.get("ket_qua")
    if isinstance(kq, dict) and kq.get("kiem_tay") is True:
        td = kq.get("thong_diep")
        return td if isinstance(td, str) and td else "Cần kiểm tay — chạy tiếp không giúp được"
    return None


def co_the_chay_tiep(v: dict, sua_chu: bool = False) -> bool:
    """D9: việc tốn tiền KHÔNG chạy tiếp bằng lời duyệt cũ — phải xin duyệt lại (POST …/xin-duyet-lai).
    Việc Claude: cần phiên đã tạo + đã gọi Claude. Loại sửa video (LOAI_CHAY_TIEP_NHAT_KY): chạy tiếp cùng id, trừ
    bản sửa có đổi chữ phụ đề (`sua_chu`, FX-22 §7.2a: phải lưu lại kèm mật khẩu) và việc cần kiểm tay
    (thong_diep_kiem_tay, FX-24)."""
    if v.get("trang_thai") != "loi" or tien_trinh_cu_con_song(v) or la_ton_tien(v) or sua_chu:
        return False
    if thong_diep_kiem_tay(v) is not None:
        return False
    if v.get("loai") in LOAI_CHAY_TIEP_NHAT_KY:
        return True
    return int(v.get("phien_da_tao") or 0) == 1 and int(v.get("so_lan_claude") or 0) > 0


def co_the_xin_duyet_lai(v: dict, phien_song: bool = False) -> bool:
    """D9 + §7.4: việc tốn tiền ở loi/can_tra_loi, tiến trình cũ chắc chắn đã chết, và KHÔNG còn phiên sống."""
    return (la_ton_tien(v) and v.get("trang_thai") in TRANG_THAI_XIN_DUYET_LAI and not tien_trinh_cu_con_song(v)
            and not phien_song)


def video_sua_ra(v: "sv.VideoSua", viec_mo: str | None) -> dict:
    """VideoSua trả ra web (§8.1): BỎ duong_dan (không lộ đường dẫn máy nhà), thêm viec_mo."""
    return {"ma_video": v.ma_video, "du_an": v.du_an, "goc": v.goc, "thu_muc": v.thu_muc, "ten": v.ten,
            "sua_luc": v.sua_luc, "luong": v.luong, "sua_duoc": v.sua_duoc, "ly_do": v.ly_do, "viec_mo": viec_mo}


def lich_su_sua(ds: list[dict], viec_mo: str | None) -> list[dict]:
    """Lịch sử sửa/hoàn tác của MỘT video, `ds` mới → cũ. hoan_tac_duoc: đúng lần sua_video ĐÃ xong gần nhất, chưa
    có hoan_tac_sua xong nào trỏ vào nó, và video không có việc mở."""
    co_the = lan_sua_hoan_tac_duoc(ds)
    ra = []
    for v in ds:
        ts = v.get("tham_so") if isinstance(v.get("tham_so"), dict) else {}
        vg = ts.get("viec_goc") if v.get("loai") == "hoan_tac_sua" else None
        ra.append({"viec": v.get("id"), "loai": v.get("loai"), "trang_thai": v.get("trang_thai"),
                   "luc": v.get("tao_luc"), "boi": v.get("tao_boi"), "viec_goc": vg if isinstance(vg, str) else None,
                   "hoan_tac_duoc": viec_mo is None and v.get("id") == co_the})
    return ra


def lan_sua_hoan_tac_duoc(ds: list[dict]) -> str | None:
    """id lần sua_video xong gần nhất (ds mới → cũ) nếu chưa bị hoàn tác xong; không có → None."""
    gan_nhat = next((v for v in ds if v.get("loai") == "sua_video" and v.get("trang_thai") == "xong"), None)
    if gan_nhat is None:
        return None
    da_hoan = any(v.get("loai") == "hoan_tac_sua" and v.get("trang_thai") == "xong"
                  and isinstance(v.get("tham_so"), dict) and v["tham_so"].get("viec_goc") == gan_nhat.get("id")
                  for v in ds)
    return None if da_hoan else gan_nhat.get("id")


def _uoc_tinh_genmax_hop_le(v: dict) -> bool:
    """genmax đã qua pha ước tính (có bản ước tính đã hiện cho người duyệt) và đang ở bước chạy."""
    ut = v.get("uoc_tinh")
    return v.get("buoc") == "chay" and isinstance(ut, str) and bool(ut.strip())


def ly_do_duyet_lai(v: dict) -> str:
    """§5.2: lý do cho lần chạy sau khi xin duyệt lại rồi duyệt lại.
    - từ can_tra_loi → người dùng không trả lời câu hỏi (cắt 500 ký tự); không hỏi lại, chọn phương án an toàn;
    - từ loi → nguyên văn `loi` cũ."""
    if v.get("trang_thai") == "can_tra_loi":
        ch = v.get("cau_hoi")
        nd = ch.get("noi_dung") if isinstance(ch, dict) else None
        nd = (nd if isinstance(nd, str) else "")[:CAU_HOI_LY_DO_TOI_DA]
        return (f"Người dùng không trả lời câu hỏi trước ({nd}) mà duyệt lại để làm tiếp. "
                "Không hỏi lại câu đó; chỗ nào cần quyết định thì chọn phương án an toàn nhất "
                "(không tốn thêm tiền), không làm được thì dừng và báo")
    loi = v.get("loi")
    return loi if isinstance(loi, str) and loi else LY_DO_LOI_KHONG_RO


def ket_qua_xin_duyet_lai(v: dict) -> dict:
    """ket_qua mới khi xin duyệt lại: GIỮ mọi khoá cũ (so_codex, tom_tat… — B7) + `duyet_lai_tu`, `ly_do_duyet_lai`
    để vòng chạy đưa vào stdin lượt resume sau khi duyệt lại. Không sửa dict gốc."""
    kq = dict(v["ket_qua"]) if isinstance(v.get("ket_qua"), dict) else {}
    kq["duyet_lai_tu"] = v.get("trang_thai")
    kq["ly_do_duyet_lai"] = ly_do_duyet_lai(v)
    return kq


def dot_bat_hieu_luc(hm: dict) -> int:
    """min(trần code, hm) — hm truyền vào bị nới/hỏng vẫn không mở đợt cao hơn trần."""
    tran = int(HAN_MUC_TRAN["dot_bat"])
    v = hm.get("dot_bat", tran) if isinstance(hm, dict) else tran
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        return tran
    return int(min(v, tran))


def tham_so_tho_tu_luu(tham_so: dict) -> dict:
    """P3-2: bỏ khoá runner tự gắn (ngay_tao) để kiem_tham_so chạy lại như input web."""
    return {k: v for k, v in (tham_so or {}).items() if k not in KHOA_RUNNER_GAN}


def _phien_ban() -> str:
    f = Path(__file__).with_name("PHIEN_BAN")
    try:
        return f.read_text(encoding="utf-8").strip() or "khong-ro"
    except FileNotFoundError:
        return "nguon"           # chạy từ repo (chưa cài)
    except OSError as e:
        log.warning("không đọc được %s: %s", f, e)
        return "khong-ro"


# ---------- handler ----------

def tao_handler(kho: KhoViec, mt: MoiTruong, khoa: str, khoa_cong_khai, hm: dict, canh_bao: list[str],
                bao_huy: Callable[[str], None], doc_log: Callable[[str, int], dict],
                trang_thai_lan: Callable[[], dict],
                che: Callable[[str], str] | None = None, *,
                tra_loi_song: Callable[[str, str, str, str], dict] | None = None,
                co_phien_song: Callable[[str], bool] = lambda _id: False,
                nhan_tin_song: Callable[[str, str, str, bool], dict] | None = None,
                kho_hoc: KhoHoc | None = None,
                kho_radar: KhoRadarUid | None = None) -> type[BaseHTTPRequestHandler]:
    """Tạo lớp handler gắn sẵn phụ thuộc. Dùng với ThreadingHTTPServer(("127.0.0.1", cong), H).

    D15 (docs/hoc-tu-dong.md §3.8): `kho_hoc` = KhoHoc đã mo() (chay_runner, sau mutex). None (mở hoc.db lỗi / chưa
    bật) → mọi route /hoc/* hợp lệ trả 503 {"loi": LOI_HOC_CHUA_BAT}. Hạn mức truyền vào kho là hạn mức HIỆU LỰC đọc
    từ `hm` ở MỖI request (han_muc.han_muc_hoc).

    Radar UID (docs/radar-uid.md §7): `kho_radar` = KhoRadarUid đã mo() (chay_runner, sau mutex). None (mở radar_uid.db
    lỗi / chưa bật) → mọi route /radar/* hợp lệ trả 503 {"loi": LOI_RADAR_CHUA_BAT}. Cầu dao radar_uid_bat = 0 (hạ ở
    cau_hinh.json, `hm` đọc một lần lúc khởi động) → route GHI trả 409 "Radar UID đang tắt", route đọc vẫn chạy.

    `che` (R-06 P3-3): hàm che bí mật áp lên mọi văn bản việc trả ra web (viec_ra, su_kien, tra_loi).
    None = không che (giữ tương thích chữ ký cũ); runner thật luôn truyền bộ che.
    Đợt 5 (A-5 nối, FX-24/FX-26): `tra_loi_song(id, boi, gia_tri, ma_cau_hoi) -> viec` xếp câu trả lời vào stdin phiên
    sống (ném KhongCoPhien / SaiTrangThai — cả khi mã lệch); `co_phien_song(id)` = vòng chạy đang giữ phiên sống của
    việc. Thiếu → mọi trả lời taovideo 409."""
    if not isinstance(khoa, str) or len(khoa) < 16:
        raise ValueError("khoá runner phải là chuỗi ≥16 ký tự")
    khoa_b = khoa.encode("utf-8")
    khoa_ghi = threading.Lock()     # tuần tự hoá mọi thao tác ghi qua API (hạn mức + tạo, trả lời + chuyển)

    def _phien_song(v: dict) -> bool:
        return v.get("loai") in LOAI_PHIEN_SONG and bool(co_phien_song(v["id"]))

    def _sua_chu(v: dict) -> bool:
        """FX-22 (§7.2a): việc sua_video ở loi/huy mà bản sửa có đổi chữ phụ đề. Mã ban_sua sai dạng / dòng đã bị
        dọn → False (chạy lại vẫn bị _kiem_sua_video chặn 400 vì không có bản sửa)."""
        if v.get("loai") != "sua_video" or v.get("trang_thai") not in TRANG_THAI_CHAY_LAI:
            return False
        ts = v.get("tham_so")
        bs = ts.get("ban_sua") if isinstance(ts, dict) else None
        if not isinstance(bs, str) or not RE_BAN_SUA.fullmatch(bs):
            return False
        dong = kho.lay_ban_sua(bs)
        return dong is not None and sv.co_sua_chu(dong.get("noi_dung"))

    def _ra(v: dict, chi_tiet: bool = True) -> dict:
        return viec_ra(v, chi_tiet, che, _phien_song(v), _sua_chu(v), _hom_nay().isoformat())

    def _che_ds(ds: list) -> list:
        return ds if che is None else che_sau(ds, che)

    def _hom_nay():
        return gio_vn(kho.bay_gio()).date()

    def _boi(body: dict) -> str:
        boi = body.get("boi")
        if not isinstance(boi, str) or not _RE_BOI.fullmatch(boi):
            raise ThamSoLoi("boi thiếu hoặc sai định dạng")
        return boi

    def _lay_viec(id_: str) -> dict:
        v = kho.lay(id_)
        if v is None:
            raise LoiApi(404, "không có việc này")
        return v

    def _trang_thai_dau(loai: LoaiViec, ts: dict) -> tuple[str, str, CanNguoiDung | None]:
        """§4.3: loại miễn phí 'cho' mà điều kiện trước hỏng (việc tay) → tạo thẳng ở can_tra_loi."""
        tt, buoc = loai.trang_thai_dau(ts)
        if tt != "cho":
            return tt, buoc, None
        dk = loai.dieu_kien_truoc(ts, mt)
        if isinstance(dk, CanNguoiDung):
            return "can_tra_loi", buoc, dk
        return tt, buoc, None    # None = sạch; 'ban' = đợi, vòng chạy thử lại

    # ----- sửa video (đợt 6) -----
    def _ds_viec_sua(ma: str) -> list[dict]:
        """Việc sua_video/hoan_tac_sua của một video, mới → cũ (khoá chống trùng của cả hai loại = ma_video)."""
        return [v for v in kho.ds(None, khoa=ma, gioi_han=GIOI_HAN_TOI_DA)
                if v.get("loai") in LOAI_SUA_VIDEO and isinstance(v.get("tham_so"), dict)
                and v["tham_so"].get("ma_video") == ma]

    def _kiem_sua_video(loai: LoaiViec, ts: dict, tru_id: str | None = None) -> None:
        """Gọi trong khoa_ghi trước khi tạo/chạy tiếp việc sửa video (cần KhoViec nên không nằm ở danh_muc):
        - không có việc MỞ của loại kia trên cùng ma_video (cùng loại: chỉ mục viec_dang_mo) → TrungViec (409);
        - tạo mới (tru_id None): sua_video cần ban_sua có trong bảng, đúng uid/du_an/ma_video, sua_luc còn khớp video
          (lệch → 409, không dựng lại mù); hoan_tac_sua cần viec_goc = lần sửa xong gần nhất chưa hoàn tác."""
        if loai.ma not in LOAI_SUA_VIDEO:
            return
        ma = ts.get("ma_video")
        ds = _ds_viec_sua(ma) if isinstance(ma, str) else []
        for v in ds:
            if v["loai"] != loai.ma and v["trang_thai"] in DANG_MO and v["id"] != tru_id:
                raise TrungViec(v)
        if tru_id is not None:
            return
        dinh_danh = (ts.get("uid"), ts.get("du_an"), ma)
        if loai.ma == "sua_video":
            bs = kho.lay_ban_sua(ts.get("ban_sua"))
            if bs is None or (bs["uid"], bs["du_an"], bs["ma_video"]) != dinh_danh:
                raise ThamSoLoi("bản sửa không có hoặc không thuộc video này — mở lại màn sửa và lưu lại")
            _, video = video_cua_tham_so(ts, mt)
            if not isinstance(bs["noi_dung"], dict) or bs["noi_dung"].get("sua_luc") != video.sua_luc:
                raise LoiApi(409, "Video đã đổi từ lúc bạn sửa — mở lại video rồi sửa lại")
            return
        goc = kho.lay(ts.get("viec_goc"))
        ts_goc = goc.get("tham_so") if goc and isinstance(goc.get("tham_so"), dict) else {}
        if (goc is None or goc.get("loai") != "sua_video" or goc.get("trang_thai") != "xong"
                or (ts_goc.get("uid"), ts_goc.get("du_an"), ts_goc.get("ma_video")) != dinh_danh):
            raise ThamSoLoi("viec_goc phải là việc sửa video đã xong của chính video này")
        if lan_sua_hoan_tac_duoc(ds) != goc["id"]:
            raise ThamSoLoi("Chỉ hoàn tác được lần sửa gần nhất chưa hoàn tác")

    def _tao_viec(loai: LoaiViec, ts_tho: dict, boi: str, chay_lai_tu: str | None = None) -> dict:
        # D15 §3.8 (P3-5): MỌI đường tạo việc của API đi qua đây (p_tao, p_chay_lai) → một chỗ chặn phủ cả hai.
        # Loại chỉ-hệ-thống: web không tạo mới; chạy lại chỉ loại không nằm trong LOAI_KHONG_CHAY_LAI (quét view —
        # kiem_tham_so còn đòi ngay = hôm nay).
        if loai.ma in LOAI_CHI_HE_THONG and (chay_lai_tu is None or loai.ma in LOAI_KHONG_CHAY_LAI):
            raise LoiApi(400, LOI_CHI_HE_THONG)
        ts = loai.kiem_tham_so(ts_tho, mt)        # chỉ gọi trên input thô (P3-2)
        with khoa_ghi:
            return _tao_viec_da_khoa(loai, ts, boi, chay_lai_tu)

    def _tao_viec_da_khoa(loai: LoaiViec, ts: dict, boi: str, chay_lai_tu: str | None = None) -> dict:
        """Phần tạo việc của _tao_viec: bên gọi ĐÃ giữ khoa_ghi và `ts` đã qua loai.kiem_tham_so."""
        khoa_chong_trung = loai.tinh_khoa(ts)
        _kiem_sua_video(loai, ts)
        kiem_han_muc(kho, loai.ma, ts, hm, "tao", boi)
        tt, buoc, cau_hoi = _trang_thai_dau(loai, ts)
        sid = str(uuid.uuid4()) if loai.agent else None
        # FX-29 (§7.8): ảnh chụp dòng kho Poster lúc tạo việc (ts đã chốt du_an_b) — đối soát đòi dòng MỚI so với nó
        anh = anh_chup_kho_taovideo(ts, mt) if loai.ma == "taovideo" else None
        v = kho.tao(loai.ma, khoa_chong_trung, ts, loai.lan_chay, tt, boi, buoc=buoc, cau_hoi=cau_hoi,
                    session_id=sid, chay_lai_tu=chay_lai_tu)
        if anh is None:
            return v
        try:
            return kho.chuyen(v["id"], [tt], tt, boi, "ảnh chụp kho lúc tạo việc",
                              ket_qua={KHOA_ANH_CHUP_KHO: anh})
        except SaiTrangThai as e:
            # việc vừa tạo đã đổi trạng thái (huỷ ngay) — không có ảnh chụp thì đối soát dựa vào mp4 mới
            log.warning("việc %s: không ghi được ảnh chụp kho lúc tạo (%s)", v["id"], e)
            return kho.lay(v["id"]) or v

    # ----- GET -----
    def g_suc_khoe(_q) -> tuple[int, dict]:
        tl = trang_thai_lan() or {}
        hom_nay = _hom_nay()
        return 200, {
            "luc": gio_vn(kho.bay_gio()).isoformat(timespec="seconds"),
            "phien_ban": _phien_ban(),
            "lan": tl.get("lan", {}),
            "tai_nguyen": tl.get("tai_nguyen", {}),
            "dem": kho.dem(),
            "chi_phi_hom_nay_usd": round(kho.chi_phi_ngay(hom_nay), 4),
            "viec_claude_hom_nay": kho.dem_trong_ngay(None, hom_nay, chi_claude=True),
            "han_muc": dict(hm),
            "tam_dung_claude_den": tl.get("tam_dung_claude_den"),
            "dot_bat": dot_bat_hieu_luc(hm),
            "chan_ton_tien": bool(tl.get("chan_ton_tien")),   # D9: bản cài lệch TONG_KIEM
            "canh_bao": list(canh_bao),
        }

    def g_danh_muc(_q) -> tuple[int, dict]:
        dot = dot_bat_hieu_luc(hm)
        return 200, {"loai": [{"ma": l.ma, "ten": l.ten, "dot": l.dot, "ton_tien": l.ton_tien,
                               "lan_chay": l.lan_chay, "tham_so": [dict(t) for t in l.tham_so]}
                              for l in DANH_MUC.values() if l.dot <= dot and l.ma not in LOAI_CHI_HE_THONG]}

    def g_ds_viec(q: dict) -> tuple[int, dict]:
        if q.get("tom_tat") == "1":
            return 200, {"dem": kho.dem()}
        tt = None
        if q.get("trang_thai"):
            tt = [t for t in q["trang_thai"].split(",") if t]
            if not tt or any(t not in TRANG_THAI for t in tt):
                raise ThamSoLoi("trang_thai lạ")
        gioi_han = GIOI_HAN_MAC_DINH
        if "gioi_han" in q:
            if not _RE_SO.fullmatch(q["gioi_han"]) or not 1 <= int(q["gioi_han"]) <= GIOI_HAN_TOI_DA:
                raise ThamSoLoi(f"gioi_han phải là số 1–{GIOI_HAN_TOI_DA}")
            gioi_han = int(q["gioi_han"])
        offset = 0
        if "offset" in q:
            if not _RE_SO.fullmatch(q["offset"]):
                raise ThamSoLoi("offset phải là số nguyên ≥ 0")
            offset = int(q["offset"])
        uid = q.get("uid")
        if uid is not None and not _RE_UID.fullmatch(uid):
            raise ThamSoLoi("uid phải là 19 chữ số")
        if uid is None:
            ds = kho.ds(tt, gioi_han=gioi_han, offset=offset)
            return 200, {"viec": [_ra(v, chi_tiet=False) for v in ds], "tong": kho.dem_loc(tt)}
        ds = [v for v in kho.ds(tt, gioi_han=GIOI_HAN_TOI_DA)
              if isinstance(v.get("tham_so"), dict) and v["tham_so"].get("uid") == uid][:gioi_han]
        return 200, {"viec": [_ra(v, chi_tiet=False) for v in ds]}

    def g_viec(id_: str, _q) -> tuple[int, dict]:
        v = _lay_viec(id_)
        return 200, {"viec": _ra(v), "tra_loi": _che_ds(kho.tra_loi_cua(id_)), "su_kien": _che_ds(kho.su_kien(id_)),
                     "xem_truoc": v.get("uoc_tinh"), "tham_so_chuan": tham_so_chuan(v.get("tham_so") or {})}

    def g_log(id_: str, q: dict) -> tuple[int, dict]:
        _lay_viec(id_)
        tu = q.get("tu", "0")
        if not _RE_SO.fullmatch(tu):
            raise ThamSoLoi("tu phải là số nguyên ≥ 0")
        return 200, doc_log(id_, int(tu))

    def g_du_an(uid: str, _q) -> tuple[int, dict]:
        return 200, {"du_an": ds_du_an(uid, mt.gocs)}

    def _dot_4_mo() -> None:
        if dot_bat_hieu_luc(hm) < DOT_DUYET:
            raise LoiApi(404, "không có API này")

    def g_poster_folders(_q) -> tuple[int, dict]:
        _dot_4_mo()
        try:
            ds = ds_folder_poster(mt)
        except ThamSoLoi as e:
            raise LoiApi(502, str(e)) from e
        # B-L1 (§4.9): duong_dan chỉ dùng nội bộ (_dk_poster_len_lich) — không trả đường dẫn ổ máy nhà ra web.
        return 200, {"folders": [{"id": f["id"], "ten": f["ten"]} for f in ds]}

    # ----- sửa video (đợt 6, §8.1) -----
    def _sua_mo() -> None:
        if DANH_MUC["sua_video"].dot > dot_bat_hieu_luc(hm):
            raise LoiApi(404, "không có API này")

    def _viec_mo_theo_video() -> dict[str, str]:
        mo: dict[str, str] = {}
        for v in kho.ds(list(DANG_MO), gioi_han=GIOI_HAN_TOI_DA):
            if v.get("loai") in LOAI_SUA_VIDEO:
                mo.setdefault(v["khoa"], v["id"])
        return mo

    def _du_an_cua_uid(uid: str) -> list[tuple[Path, Path]]:
        """[(thư mục dự án, gốc)] — gốc cùng định dạng video_server (chuỗi `goc` ghép thẻ Duyệt)."""
        return [(Path(d["goc"]) / d["ten"], Path(d["goc"])) for d in ds_du_an(uid, mt.gocs)]

    def _tim_video_uid(uid: str, ma: str) -> tuple[Path, "sv.VideoSua"]:
        for p, goc in _du_an_cua_uid(uid):
            try:
                return p, sv.tim_video(p, goc, ma)
            except sv.KhongTraDuoc:
                continue
        raise LoiApi(404, LOI_KHONG_THAY_VIDEO)

    def _ban_ghi_sua_duoc(p: Path, v: "sv.VideoSua") -> "sv.BanGhi":
        if not v.sua_duoc:
            raise LoiApi(409, v.ly_do or "Video này không sửa được trên web")
        return sv.tra_ban_ghi(p, v)          # KhongTraDuoc → 409 (bọc ở _chay)

    def g_sua_ds(uid: str, _q) -> tuple[int, dict]:
        _sua_mo()
        mo = _viec_mo_theo_video()
        return 200, {"videos": [video_sua_ra(v, mo.get(v.ma_video))
                                for p, goc in _du_an_cua_uid(uid) for v in sv.ds_video_sua(p, goc)]}

    def g_sua_chi_tiet(uid: str, ma: str, _q) -> tuple[int, dict]:
        _sua_mo()
        p, v = _tim_video_uid(uid, ma)
        ds = _ds_viec_sua(ma)
        viec_mo = next((x["id"] for x in ds if x["trang_thai"] in DANG_MO), None)
        video = video_sua_ra(v, viec_mo)
        kq: dict[str, Any] = {"video": video, "luong": v.luong, "me": None, "tien_to": None, "plan_id": None,
                              "phu_de": None, "loi_phu_de": "", "canh": [], "ghi_chu_luong_a": v.luong == "A",
                              "canh_bao": [], "viec_mo": viec_mo, "lich_su": lich_su_sua(ds, viec_mo)}
        if not v.sua_duoc:
            return 200, kq
        try:
            b = sv.tra_ban_ghi(p, v)
        except sv.KhongTraDuoc as e:          # dữ liệu đổi giữa hai lần đọc: báo như video không sửa được
            video.update(sua_duoc=False, ly_do=e.ly_do)
            return 200, kq
        kq.update(luong=b.luong, me=b.me, tien_to=b.tien_to, plan_id=b.plan.get("plan_id"),
                  canh=sv.doc_canh(b, p), ghi_chu_luong_a=b.luong == "A", canh_bao=list(b.canh_bao))
        try:
            kq["phu_de"] = sv.doc_phu_de(b)
        except sv.KhongTraDuoc as e:
            kq["loi_phu_de"] = e.ly_do
        return 200, kq

    def g_sua_ung_vien(uid: str, ma: str, q: dict) -> tuple[int, dict]:
        _sua_mo()
        seg = q.get("seg")
        if not isinstance(seg, str) or not _RE_SEG.fullmatch(seg) or int(seg) > SEG_TOI_DA:
            raise ThamSoLoi(f"seg phải là số 0–{SEG_TOI_DA}")
        p, v = _tim_video_uid(uid, ma)
        b = _ban_ghi_sua_duoc(p, v)
        return 200, {"ung_vien": sv.ung_vien(p, b, int(seg))}

    def p_ban_sua(uid: str, ma: str, body: dict) -> tuple[int, dict]:
        """§8.1: kiểm đầy đủ bản sửa với dữ liệu thật rồi lưu bảng ban_sua. Không tạo việc (Worker gọi POST /viec)."""
        _sua_mo()
        boi = _boi(body)
        p, v = _tim_video_uid(uid, ma)
        b = _ban_ghi_sua_duoc(p, v)
        try:
            ban = sv.kiem_ban_sua(body, sv.lap_chi_tiet(p, v, b))
        except (sv.BanSuaLech, sv.BanSuaQuaLon) as e:
            raise LoiApi(e.ma_http, str(e)) from e
        id_ = sv.ma_ban_sua(ban)
        with khoa_ghi:
            kho.luu_ban_sua(id_, uid, v.du_an, v.ma_video, ban, boi)
        return 201, {"ban_sua": id_, "du_an": v.du_an,
                     "tom_tat": {"so_cau": len(ban["phu_de"]), "so_clip": len(ban["doi_clip"]),
                                 "so_doi_cho": len(ban["doi_cho"])}}

    # ----- POST -----
    def p_tao(body: dict) -> tuple[int, dict]:
        boi = _boi(body)
        ma = body.get("loai")
        if not isinstance(ma, str):
            raise ThamSoLoi("loai thiếu")
        loai = lay_loai(ma, dot_bat_hieu_luc(hm))
        ts_tho = body.get("tham_so", {})
        return 201, {"viec": _ra(_tao_viec(loai, ts_tho, boi))}

    def _tra_loi_phien_song(v: dict, boi: str, tra_loi: object, da_xac_nhan: bool, ma_cau_hoi: object) -> dict:
        """§7.6 nhánh taovideo: chỉ khi vòng chạy còn giữ phiên sống; KHÔNG tiêu lời duyệt, không sinh tiến trình.
        `ma_cau_hoi` (S-4 #4) phải đúng dạng RE_MA_CAU_HOI và bằng `cau_hoi.ma` đang lưu — kiểm TRƯỚC giá trị trả lời
        để câu hỏi đã đổi luôn báo 409 "tải lại" thay vì 400/403 theo câu mới."""
        id_ = v["id"]
        if tra_loi_song is None or not _phien_song(v):
            raise LoiApi(409, LOI_PHIEN_DA_DONG)
        if v["trang_thai"] != "can_tra_loi":
            raise LoiApi(409, "việc không còn chờ trả lời")
        if not isinstance(v.get("cau_hoi"), dict):
            raise LoiApi(409, "việc không có câu hỏi đang chờ")
        cau_hoi = CanNguoiDung.tu_dict(v["cau_hoi"])
        if (not isinstance(ma_cau_hoi, str) or not RE_MA_CAU_HOI.fullmatch(ma_cau_hoi)
                or ma_cau_hoi != cau_hoi.ma):
            log.info("trả lời %s: mã câu hỏi thiếu/sai/lệch (gửi %r, đang lưu %r)", id_,
                     ma_cau_hoi if isinstance(ma_cau_hoi, str) and len(ma_cau_hoi) <= 40 else type(ma_cau_hoi).__name__,
                     cau_hoi.ma)
            raise LoiApi(409, LOI_CAU_HOI_DA_DOI)
        gt = kiem_tra_loi_dot5(cau_hoi, tra_loi, da_xac_nhan, ton_tien=True)
        try:
            moi = tra_loi_song(id_, boi, gt, ma_cau_hoi)
        except KhongCoPhien as e:
            log.info("trả lời %s: phiên sống đã đóng (%s)", id_, e)
            raise LoiApi(409, LOI_PHIEN_DA_DONG) from e
        except SaiTrangThai as e:
            # BoChay kiểm lại dưới khoá của nó: việc vừa rời can_tra_loi hoặc agent vừa hỏi câu khác (mã lệch).
            log.info("trả lời %s: vòng chạy từ chối (%s)", id_, e)
            raise LoiApi(409, LOI_CAU_HOI_DA_DOI) from e
        return moi if isinstance(moi, dict) else _lay_viec(id_)

    def p_tra_loi(id_: str, body: dict) -> tuple[int, dict]:
        boi = _boi(body)
        da_xac_nhan = body.get("da_xac_nhan_mat_khau", False)
        if not isinstance(da_xac_nhan, bool):
            raise ThamSoLoi("da_xac_nhan_mat_khau phải là true/false")
        with khoa_ghi:
            v = _lay_viec(id_)
            if v.get("loai") in LOAI_PHIEN_SONG:
                return 200, {"viec": _ra(_tra_loi_phien_song(v, boi, body.get("tra_loi"), da_xac_nhan,
                                                             body.get("ma_cau_hoi")))}
            if la_ton_tien(v):
                # A-D9b: trả lời rồi chạy tiếp = tiêu lại lời duyệt cũ → phải xin duyệt lại (mật khẩu).
                raise LoiApi(409, LOI_TRA_LOI_TON_TIEN)
            if v["trang_thai"] != "can_tra_loi":
                raise LoiApi(409, "việc không còn chờ trả lời")
            if not isinstance(v.get("cau_hoi"), dict):
                raise LoiApi(409, "việc không có câu hỏi đang chờ")
            cau_hoi = CanNguoiDung.tu_dict(v["cau_hoi"])
            gt = kiem_tra_loi_dot3(cau_hoi, body.get("tra_loi"))
            # Ghi trả lời TRƯỚC khi chuyển sang `cho`: vòng chạy nhận việc là đã thấy trả lời.
            # Trong khoá ghi + đã kiểm can_tra_loi, và chỉ API đưa việc ra khỏi can_tra_loi → CAS dưới không hụt.
            kho.them_tra_loi(id_, boi, cau_hoi.noi_dung, gt)
            moi = kho.chuyen(id_, ["can_tra_loi"], "cho", boi, f"trả lời: {gt}")
        return 200, {"viec": _ra(moi)}

    def p_huy(id_: str, body: dict) -> tuple[int, dict]:
        boi = _boi(body)
        with khoa_ghi:
            _lay_viec(id_)
            moi = kho.chuyen(id_, list(DANG_MO), "huy", boi, "huỷ từ web")
        kq: dict[str, Any] = {"viec": _ra(moi)}
        # Sau CAS: việc không thể bị làn nhận lại; nếu đang chạy thì báo vòng chạy giết cây.
        try:
            bao_huy(id_)
        except Exception as e:   # noqa: BLE001 — trạng thái đã là huy; báo rõ cho web thay vì 500 gây hiểu nhầm
            log.exception("bao_huy(%s) lỗi — việc đã huỷ trong DB nhưng tiến trình có thể còn chạy", id_)
            kq["canh_bao"] = f"Đã huỷ nhưng chưa dừng được tiến trình ({type(e).__name__}) — kiểm trên máy"
        return 200, kq

    def p_luu_tru(id_: str, body: dict) -> tuple[int, dict]:
        boi = _boi(body)
        with khoa_ghi:
            _lay_viec(id_)
            moi = kho.dat_luu_tru(id_, True, boi)
        return 200, {"viec": _ra(moi)}

    def p_bo_luu_tru(id_: str, body: dict) -> tuple[int, dict]:
        boi = _boi(body)
        with khoa_ghi:
            _lay_viec(id_)
            moi = kho.dat_luu_tru(id_, False, boi)
        return 200, {"viec": _ra(moi)}

    def p_tu_choi(id_: str, body: dict) -> tuple[int, dict]:
        boi = _boi(body)
        with khoa_ghi:
            _lay_viec(id_)
            moi = kho.chuyen(id_, ["cho_duyet"], "huy", boi, "từ chối duyệt")
        return 200, {"viec": _ra(moi)}

    def p_chay_tiep(id_: str, body: dict) -> tuple[int, dict]:
        boi = _boi(body)
        with khoa_ghi:
            v = _lay_viec(id_)
            if la_ton_tien(v):
                # D9: lời duyệt chỉ tiêu được một lần; chạy tiếp việc tốn tiền phải duyệt lại (nhập mật khẩu).
                raise LoiApi(409, LOI_CAN_DUYET_LAI)
            if tien_trinh_cu_con_song(v):
                raise LoiApi(409, "không chạy tiếp được: tiến trình cũ của việc có thể còn sống (runner không giết "
                                  "được) — kiểm tay trên máy rồi dùng Chạy lại")
            if _sua_chu(v):
                raise LoiApi(409, sv.LOI_SUA_CHU_CAN_MAT_KHAU)
            td_kiem_tay = thong_diep_kiem_tay(v)
            if td_kiem_tay is not None:                # FX-24: bỏ qua có chủ đích → chạy tiếp không giúp được
                raise LoiApi(409, td_kiem_tay if che is None else che(td_kiem_tay), {"kiem_tay": True})
            if not co_the_chay_tiep(v):
                raise LoiApi(409, "không chạy tiếp được: cần trạng thái lỗi và phiên Claude đã tạo")
            loai = lay_loai(v["loai"], dot_bat_hieu_luc(hm))
            _kiem_sua_video(loai, v.get("tham_so") or {}, tru_id=id_)
            kiem_han_muc(kho, loai.ma, v.get("tham_so") or {}, hm, "nhan", boi, viec_id=id_)
            ghi = ("chạy tiếp cùng mã việc (bộ chuyển đổi đọc nhật ký để làm nốt/hoàn nguyên)"
                   if loai.ma in LOAI_CHAY_TIEP_NHAT_KY else "chạy tiếp (resume phiên Claude)")
            moi = kho.chuyen(id_, ["loi"], "cho", boi, ghi)
        return 200, {"viec": _ra(moi)}

    def p_chay_lai(id_: str, body: dict) -> tuple[int, dict]:
        boi = _boi(body)
        v = _lay_viec(id_)
        if v["trang_thai"] not in TRANG_THAI_CHAY_LAI:
            raise LoiApi(409, "chỉ chạy lại được việc lỗi hoặc đã huỷ")
        if _sua_chu(v):
            # FX-22 (§7.2a, D10 Q3): chữ phụ đề cần mật khẩu MỖI lần lưu — không dùng lại ban_sua cũ qua nút bấm
            # (sau hoàn tác mtime cũ được giữ nên sua_luc của bản cũ lại hợp lệ).
            raise LoiApi(409, sv.LOI_SUA_CHU_CAN_MAT_KHAU)
        loai = lay_loai(v["loai"], dot_bat_hieu_luc(hm))
        moi = _tao_viec(loai, tham_so_tho_tu_luu(v.get("tham_so") or {}), boi, chay_lai_tu=id_)
        return 201, {"viec": _ra(moi)}

    def p_duyet(id_: str, body: dict) -> tuple[int, dict]:
        """§4.3 cho_duyet → cho. Chữ ký kiểm trên dữ liệu ĐANG LƯU (id, loai, tham_so) + lời duyệt gửi kèm;
        lưu cả 4 trường để vòng chạy kiểm lại mỗi lần nhận (sửa DB sau duyệt → chữ ký lệch → bị chặn)."""
        _dot_4_mo()
        boi = _boi(body)
        loi_duyet, duyet_luc, ky = kiem_body_duyet(body, kho.bay_gio())
        if boi not in NGUOI_DUYET:
            raise LoiApi(403, "người này không được duyệt việc tốn tiền")
        with khoa_ghi:
            v = _lay_viec(id_)
            loai = lay_loai(v["loai"], dot_bat_hieu_luc(hm))
            if not loai.ton_tien:
                raise LoiApi(409, "loại việc này không cần duyệt")
            if v["trang_thai"] != "cho_duyet":
                raise LoiApi(409, "việc không còn chờ duyệt")
            ung_vien = {**v, "loi_duyet": loi_duyet, "duyet_luc": duyet_luc, "duyet_boi": boi, "chu_ky_duyet": ky}
            if not chu_ky.kiem_duyet(khoa_cong_khai, ung_vien):
                log.warning("từ chối duyệt %s: chữ ký duyệt không khớp (boi=%s)", id_, boi)
                raise LoiApi(401, "chữ ký duyệt không hợp lệ")
            kiem_han_muc(kho, loai.ma, v.get("tham_so") or {}, hm, "duyet", boi, viec_id=id_)
            moi = kho.chuyen(id_, ["cho_duyet"], "cho", boi, "duyệt (chữ ký hợp lệ)", loi_duyet=loi_duyet,
                             duyet_boi=boi, duyet_luc=duyet_luc, chu_ky_duyet=ky, buoc="chay")
        return 200, {"viec": _ra(moi)}

    def p_xin_duyet_lai(id_: str, body: dict) -> tuple[int, dict]:
        """D9: việc tốn tiền đang loi/can_tra_loi → cho_duyet, xoá 4 trường duyệt cũ (lời duyệt cũ không dùng lại
        được). genmax: giữ buoc 'chay' nếu đã có ước tính hợp lệ; chưa có → về cho + buoc 'uoc_tinh' (pha miễn
        phí) để người duyệt luôn thấy ước tính trước khi duyệt. Không kiểm hạn mức ở đây (chưa tốn gì): hạn mức
        kiểm lại lúc duyệt và lúc nhận."""
        _dot_4_mo()
        boi = _boi(body)
        with khoa_ghi:
            v = _lay_viec(id_)
            loai = lay_loai(v["loai"], dot_bat_hieu_luc(hm))
            if not loai.ton_tien:
                raise LoiApi(409, "loại việc này không cần duyệt — dùng Chạy tiếp/Chạy lại")
            if v["trang_thai"] not in TRANG_THAI_XIN_DUYET_LAI:
                raise LoiApi(409, "chỉ xin duyệt lại được việc tốn tiền đang lỗi hoặc chờ trả lời")
            if _phien_song(v):                  # §7.4: còn phiên sống → không mở đường sinh phiên thứ hai (CL21)
                raise LoiApi(409, LOI_XIN_DUYET_LAI_KHI_SONG)
            if tien_trinh_cu_con_song(v):
                raise LoiApi(409, "không xin duyệt lại được: tiến trình cũ của việc có thể còn sống (runner không "
                                  "giết được) — kiểm tay trên máy rồi dùng Chạy lại")
            xoa = {"loi_duyet": None, "duyet_boi": None, "duyet_luc": None, "chu_ky_duyet": None,
                   "ket_qua": ket_qua_xin_duyet_lai(v)}
            if loai.ma == "voice_genmax" and not _uoc_tinh_genmax_hop_le(v):
                moi = kho.chuyen(id_, list(TRANG_THAI_XIN_DUYET_LAI), "cho", boi,
                                 "xin duyệt lại: chưa có ước tính — chạy lại pha ước tính (không gọi API)",
                                 buoc="uoc_tinh", uoc_tinh=None, **xoa)
            else:
                moi = kho.chuyen(id_, list(TRANG_THAI_XIN_DUYET_LAI), "cho_duyet", boi,
                                 "xin duyệt lại (lời duyệt cũ đã huỷ)", buoc="chay", **xoa)
        return 200, {"viec": _ra(moi)}

    def p_nhan_tin(id_: str, body: dict) -> tuple[int, dict]:
        """Chỉ đạo việc phiên sống đang chạy. body {noi_dung, ngat, boi, da_xac_nhan_mat_khau}."""
        boi = _boi(body)
        nd, ngat = kiem_chi_dao(body.get("noi_dung"), body.get("ngat", False),
                                body.get("da_xac_nhan_mat_khau", False))
        with khoa_ghi:
            v = _lay_viec(id_)
            if v.get("loai") not in LOAI_PHIEN_SONG:
                raise LoiApi(409, "loại việc này không nhận chỉ đạo khi đang chạy")
            if not _phien_song(v) and v["trang_thai"] in TRANG_THAI_GHI_CHI_DAO:
                # Không còn phiên: chỉ lưu, phiếu LẦN CHẠY TIẾP (sau Xin duyệt lại → Duyệt) mang theo.
                kho.them_tra_loi(id_, boi, CAU_CHI_DAO, nd)
                giu = {"ket_thuc_luc": v.get("ket_thuc_luc")} if v["trang_thai"] == "loi" else {}
                moi = kho.chuyen(id_, [v["trang_thai"]], v["trang_thai"], boi,
                                 f"ghi chỉ đạo cho lần chạy tiếp: {nd}"[:300], **giu)
                return 200, {"viec": _ra(moi), "luu_cho_lan_sau": True}
            if nhan_tin_song is None or not _phien_song(v):
                raise LoiApi(409, LOI_PHIEN_DA_DONG)
            if not ngat and v["trang_thai"] == "can_tra_loi":
                raise LoiApi(409, LOI_CHI_DAO_DANG_HOI)
            try:
                moi = nhan_tin_song(id_, boi, nd, ngat)
            except KhongCoPhien as e:
                log.info("chỉ đạo %s: phiên sống đã đóng (%s)", id_, e)
                raise LoiApi(409, LOI_PHIEN_DA_DONG) from e
            except SaiTrangThai as e:
                log.info("chỉ đạo %s: vòng chạy từ chối (%s)", id_, e)
                raise LoiApi(409, "việc vừa đổi trạng thái — tải lại") from e
        return 200, {"viec": _ra(moi if isinstance(moi, dict) else _lay_viec(id_))}

    # ----- học tự động (D15, docs/hoc-tu-dong.md §3.8) -----
    def _kho_hoc_mo() -> KhoHoc:
        if kho_hoc is None:
            raise LoiApi(503, LOI_HOC_CHUA_BAT)
        return kho_hoc

    def _han_muc_hoc() -> dict[str, int]:
        """Hạn mức HIỆU LỰC (cau_hinh.json đã hạ, kẹp trần code) đọc từ `hm` tại lúc gọi — kho không có mặc định."""
        bat_ngay, hieu_luc_toi_da = han_muc_hoc(hm)
        return {"bat_ngay": bat_ngay, "hieu_luc_toi_da": hieu_luc_toi_da}

    def _goi_kho_hoc(lam: Callable[[KhoHoc], Any]) -> Any:
        """Gọi kho học: KhongCoBaiHoc → 404 (chỉ 2 câu cố định), SaiTrangThaiHoc → 409 (câu cố định của kho);
        ThamSoLoi → 400 và lỗi khác → 500 do _chay xử lý. Luôn đóng kết nối SQLite của luồng HTTP này (mỗi request một
        luồng — không để kết nối mồ côi giữ hoc.db)."""
        k = _kho_hoc_mo()
        try:
            return lam(k)
        except KhongCoBaiHoc as e:
            loi = e.loi if e.loi in _LOI_404_HOC else hdm.TEN_LY_DO["khong_co_bai_hoc"]
            raise LoiApi(404, loi) from e
        except SaiTrangThaiHoc as e:
            raise LoiApi(409, str(e.loi)) from e
        finally:
            try:
                k.dong()
            except sqlite3.Error:
                log.warning("hoc.db: đóng kết nối luồng HTTP lỗi", exc_info=True)

    def _ra_hoc(d: dict) -> dict:
        return d if che is None else che_sau(d, che)

    def g_hoc_bao_cao(q: dict) -> tuple[int, dict]:
        _kho_hoc_mo()
        ngay = q.get("ngay")
        if ngay is not None and not _RE_NGAY_HOC.fullmatch(ngay):
            raise ThamSoLoi("ngay phải dạng YYYY-MM-DD")
        hmh = _han_muc_hoc()
        return 200, _ra_hoc(_goi_kho_hoc(lambda k: k.bao_cao(ngay, **hmh)))

    def g_hoc_bai_hoc(q: dict) -> tuple[int, dict]:
        _kho_hoc_mo()
        gioi_han = HOC_GIOI_HAN_MAC_DINH
        if "gioi_han" in q:
            if not _RE_SO.fullmatch(q["gioi_han"]) or not 1 <= int(q["gioi_han"]) <= HOC_GIOI_HAN_TOI_DA:
                raise ThamSoLoi(f"gioi_han phải là số 1–{HOC_GIOI_HAN_TOI_DA}")
            gioi_han = int(q["gioi_han"])
        hmh = _han_muc_hoc()
        return 200, _ra_hoc({"bai_hoc": _goi_kho_hoc(lambda k: k.ds_bai_hoc(gioi_han, **hmh))})

    def p_hoc(ma: str, act: str, body: dict) -> tuple[int, dict]:
        """POST /hoc/bai-hoc/<ma>/(hoan-tac|bat-lai) — đã qua x-runner-key + chữ ký D7 + nonce ở do_POST; `boi` chỉ
        tin vì nằm trong body đã ký (Worker tự dựng {"boi": phien.user})."""
        _kho_hoc_mo()
        boi = _boi(body)
        hmh = _han_muc_hoc()
        if act == "hoan-tac":
            bai = _goi_kho_hoc(lambda k: k.hoan_tac(ma, boi, **hmh))
        else:
            bai = _goi_kho_hoc(lambda k: k.bat_lai(ma, boi, **hmh))
        log.info("học: %s %s bởi %s", act, ma, boi)
        return 200, _ra_hoc({"bai_hoc": bai})

    # ----- Radar UID (docs/radar-uid.md §7, §7.1) -----
    def _kho_radar_mo() -> KhoRadarUid:
        if kho_radar is None:
            raise LoiApi(503, LOI_RADAR_CHUA_BAT)
        return kho_radar

    def _radar_bat() -> None:
        """Cầu dao radar_uid_bat (hạn mức HIỆU LỰC): 0 → mọi route GHI 409. Gọi sau khi biết kho đã mở."""
        if han_muc_radar(hm)[0] < 1:
            raise LoiApi(409, LOI_RADAR_TAT)

    def _goi_radar(lam: Callable[[KhoRadarUid], Any]) -> Any:
        """Gọi kho Radar: KhongCoRadar → 404 (câu cố định của kho), SaiTrangThaiRadar → 409 (câu cố định); ThamSoLoi
        → 400 và lỗi khác → 500 do _chay xử lý. Luôn đóng kết nối SQLite của luồng HTTP này (mỗi request một luồng)."""
        k = _kho_radar_mo()
        try:
            return lam(k)
        except KhongCoRadar as e:
            raise LoiApi(404, e.loi) from e
        except SaiTrangThaiRadar as e:
            raise LoiApi(409, e.loi) from e
        finally:
            try:
                k.dong()
            except sqlite3.Error:
                log.warning("radar_uid.db: đóng kết nối luồng HTTP lỗi", exc_info=True)

    def _ra_radar(d: Any) -> Any:
        return d if che is None else che_sau(d, che)

    def _nhom_radar(k: KhoRadarUid, goc: str) -> dict:
        for n in k.ds_nhom():
            if n["goc"] == goc:
                return n
        raise KhongCoRadar()

    def _ds_uid_ra(k: KhoRadarUid, goc: str, bat_dau_ngay: str, bay: datetime) -> list[dict]:
        """ds của /radar/bang = UidRa (§7.1, không đổi) + khoá thêm RU-B11 `anh`, `ban_tong` (chỉ ở bảng, không ở chi tiết)."""
        tu_ngay = (bay.date() - timedelta(days=RADAR_NGAY_DOC)).isoformat()
        ra = []
        for lk in k.uid_cua_nhom(goc):
            snaps = k.doc_snapshots(lk["uid"], tu_ngay)
            u = dung_uid_ra(lk, snaps, bay, bat_dau_ngay)
            u["anh"] = anh_hop_le(lk.get("anh"))
            u["ban_tong"] = ban_tong_so(snaps)
            ra.append(u)
        return sap_xep_uid_ra(ra)

    def g_radar_bang(_q: dict) -> tuple[int, dict]:
        _kho_radar_mo()
        bay = gio_vn(kho.bay_gio())
        ngay = bay.date().isoformat()

        def lam(k: KhoRadarUid) -> dict:
            bat, tran_goi, _ = han_muc_radar(hm)
            goi = k.goi_hom_nay(ngay)
            tk = k.doc_token()
            lan = k.lan_gan_nhat()
            nhom = [{"goc": n["goc"], "ten": n["ten"], "trang_thai": n["trang_thai"], "ly_do": n["ly_do"],
                     "ten_ly_do": ten_ly_do_radar(n["ly_do"], goi, tran_goi), "tim_luc": n["tim_luc"],
                     "bat_dau_ngay": n["bat_dau_ngay"], "ds": ds}
                    | _them_nhom_radar(n, ds)
                    for n in k.ds_nhom() for ds in [_ds_uid_ra(k, n["goc"], n["bat_dau_ngay"], bay)]]
            return {
                "luc": bay.isoformat(timespec="seconds"), "ngay": ngay,
                "token": {"trang_thai": tk["trang_thai"], "cau": CAU_TOKEN_RADAR.get(tk["trang_thai"], "")},
                "han_muc": {"bat": bat, "goi_ngay_toi_da": tran_goi, "goi_hom_nay": goi, "goc_toi_da": GOC_TOI_DA},
                "lan": ({"trang_thai": "chua_chay", "ly_do": "", "ngay": "", "ten_ly_do": ""} if lan is None else
                        {"trang_thai": lan["trang_thai"], "ly_do": lan["ly_do"], "ngay": lan["ngay"],
                         "ten_ly_do": ten_ly_do_radar(lan["ly_do"], goi, tran_goi)}),
                "nhom": nhom}
        return 200, _ra_radar(_goi_radar(lam))

    def g_radar_uid(uid: str, _q: dict) -> tuple[int, dict]:
        _kho_radar_mo()
        bay = gio_vn(kho.bay_gio())

        def lam(k: KhoRadarUid) -> dict:
            if not _RE_UID.fullmatch(uid):
                raise KhongCoRadar()                                  # uid sai dạng cũng 404 (§7 dòng 2)
            chon: tuple[dict, dict] | None = None
            for n in k.ds_nhom():                                     # ưu tiên nhóm đang theo; chung UID ở nhiều nhóm
                for lk in k.uid_cua_nhom(n["goc"]):
                    if lk["uid"] == uid and (chon is None or (chon[0]["trang_thai"] == "ngung"
                                                              and n["trang_thai"] != "ngung")):
                        chon = (n, lk)
            if chon is None:
                raise KhongCoRadar()
            n, lk = chon
            snaps = k.doc_snapshots(uid, (bay.date() - timedelta(days=RADAR_NGAY_DOC)).isoformat())
            ra = dung_uid_ra(lk, snaps, bay, n["bat_dau_ngay"])
            ra["chuoi"], ra["video"] = dung_chuoi_va_video(snaps)
            return ra
        return 200, _ra_radar(_goi_radar(lam))

    def _co_viec_mo(ma: str, khoa: str) -> bool:
        return any(v.get("loai") == ma and v.get("trang_thai") in DANG_MO for v in kho.ds(None, khoa=khoa, gioi_han=50))

    def _uid_trong_body(body: dict) -> str:
        uid = body.get("uid")
        if not isinstance(uid, str) or not _RE_UID.fullmatch(uid):
            raise ThamSoLoi("UID phải đủ 19 chữ số")
        return uid

    def p_radar_goc(body: dict) -> tuple[int, dict]:
        """POST /radar/goc {boi, uid}: thêm UID gốc (nhóm cho_tim) + tạo việc radar_uid_nap. UID đã có → da_co, không tạo
        việc. Hạn mức/cầu dao kiểm TRƯỚC khi ghi nhóm (429 không để lại nhóm mồ côi)."""
        _kho_radar_mo()
        _radar_bat()
        boi = _boi(body)
        uid = _uid_trong_body(body)
        loai = DANH_MUC["radar_uid_nap"]

        def lam(k: KhoRadarUid) -> tuple[int, dict]:
            ts = loai.kiem_tham_so({"goc": uid}, mt)
            with khoa_ghi:
                if any(n["goc"] == uid for n in k.ds_nhom()):
                    return 202, {"da_co": True, "goc": uid}
                kiem_han_muc(kho, loai.ma, ts, hm, "tao", boi)
                if k.them_goc(uid, boi)["da_co"]:
                    return 202, {"da_co": True, "goc": uid}
                v = _tao_viec_da_khoa(loai, ts, boi)
            log.info("radar: thêm UID gốc %s bởi %s, việc nạp %s", uid, boi, v["id"])
            return 202, {"da_co": False, "goc": uid, "viec_id": v["id"]}
        return _goi_radar(lam)

    def p_radar_tim_lai(goc: str, body: dict) -> tuple[int, dict]:
        """POST /radar/goc/<goc>/tim-lai: nhóm → cho_tim + việc nạp mới. 409 khi đang tìm / đã có việc nạp mở / nhóm
        ngừng; 429 kiểm TRƯỚC khi đổi trạng thái."""
        _kho_radar_mo()
        _radar_bat()
        boi = _boi(body)
        loai = DANH_MUC["radar_uid_nap"]

        def lam(k: KhoRadarUid) -> tuple[int, dict]:
            ts = loai.kiem_tham_so({"goc": goc}, mt)
            with khoa_ghi:
                n = _nhom_radar(k, goc)
                if _co_viec_mo(loai.ma, goc):
                    raise LoiApi(409, LOI_DANG_TIM)
                if n["trang_thai"] == "ngung":
                    raise LoiApi(409, LOI_NHOM_NGUNG)
                kiem_han_muc(kho, loai.ma, ts, hm, "tao", boi)
                if n["trang_thai"] == "dang_tim":
                    # kẹt: không có việc nạp mở (đã huỷ / hết lần thử / runner chết) mà nhóm vẫn dang_tim. Kho cấm
                    # dang_tim→cho_tim trực tiếp, nên đi qua loi_tim; cả hai bước nằm trong khoa_ghi và vừa kiểm
                    # không có việc mở, nên không đua với việc đang chạy.
                    log.warning("radar: nhóm %s kẹt dang_tim không có việc nạp mở — gỡ kẹt bởi %s", goc, boi)
                    k.dat_trang_thai_nhom(goc, "loi_tim")
                k.dat_trang_thai_nhom(goc, "cho_tim")
                try:
                    v = _tao_viec_da_khoa(loai, ts, boi)
                except TrungViec as e:
                    raise LoiApi(409, LOI_DANG_TIM) from e
            log.info("radar: tìm lại nhóm %s bởi %s, việc nạp %s", goc, boi, v["id"])
            return 202, {"viec_id": v["id"]}
        return _goi_radar(lam)

    def p_radar_nhom(goc: str, act: str, body: dict) -> tuple[int, dict]:
        """POST /radar/goc/<goc>/(tim-lai|ngung|theo-lai|them-tay)."""
        if act == "tim-lai":
            return p_radar_tim_lai(goc, body)
        _kho_radar_mo()
        _radar_bat()
        boi = _boi(body)
        if act == "them-tay":
            uid = body.get("uid")
            _goi_radar(lambda k: k.them_tay(goc, uid, boi))          # kho kiểm UID (400 "UID phải đủ 19 chữ số")
            return 200, {"goc": goc, "uid": uid}
        loai = DANH_MUC["radar_uid_nap"]

        def lam(k: KhoRadarUid) -> dict:
            with khoa_ghi:
                truoc = _nhom_radar(k, goc)["trang_thai"]
                kq = k.dat_goc(goc, act, boi)
                if act == "theo-lai" and truoc == "ngung" and kq["trang_thai"] == "cho_tim":
                    # nhóm chưa từng tìm xong: không có ai sẽ nạp nó → tạo việc nạp (lỗi hạn mức/trùng: log, nhóm giữ cho_tim)
                    try:
                        ts = loai.kiem_tham_so({"goc": goc}, mt)
                        _tao_viec_da_khoa(loai, ts, boi)
                    except (VuotHanMuc, TrungViec, ThamSoLoi) as e:
                        log.warning("radar: theo-lai %s không tạo được việc nạp (%s: %s) — bấm Tìm lại sau", goc,
                                    type(e).__name__, e)
            return kq
        return 200, _goi_radar(lam)

    def p_radar_uid(goc: str, uid: str, act: str, body: dict) -> tuple[int, dict]:
        """POST /radar/goc/<goc>/uid/<uid>/(ghim|bo-ghim|loai|bo-loai) → {uid, trang_thai}."""
        _kho_radar_mo()
        _radar_bat()
        boi = _boi(body)
        return 200, _goi_radar(lambda k: k.dat_uid(goc, uid, act, boi))

    def p_radar_chup_lai(body: dict) -> tuple[int, dict]:
        """POST /radar/chup-lai: tạo một lượt radar_uid_hang_ngay cho hôm nay (UID `ok` hôm nay được bỏ qua, chỉ chụp
        lại phần lỗi/chưa chụp). 409 khi đang có lượt mở; 429 khi vượt radar_uid_chay_ngay."""
        _kho_radar_mo()
        _radar_bat()
        boi = _boi(body)
        loai = DANH_MUC["radar_uid_hang_ngay"]
        ts = loai.kiem_tham_so({"ngay": _hom_nay().isoformat()}, mt)
        with khoa_ghi:
            if _co_viec_mo(loai.ma, ts["ngay"]):
                raise LoiApi(409, LOI_DANG_CHUP)
            try:
                v = _tao_viec_da_khoa(loai, ts, boi)
            except TrungViec as e:
                raise LoiApi(409, LOI_DANG_CHUP) from e
        log.info("radar: chụp lại %s bởi %s, việc %s", ts["ngay"], boi, v["id"])
        return 202, {"viec_id": v["id"]}

    HANH_DONG = {"tra-loi": p_tra_loi, "huy": p_huy, "tu-choi": p_tu_choi, "chay-tiep": p_chay_tiep,
                 "chay-lai": p_chay_lai, "duyet": p_duyet, "xin-duyet-lai": p_xin_duyet_lai,
                 "nhan-tin": p_nhan_tin, "luu-tru": p_luu_tru, "bo-luu-tru": p_bo_luu_tru}

    class Handler(BaseHTTPRequestHandler):
        server_version = "kho-runner"
        sys_version = ""

        def log_message(self, fmt: str, *args) -> None:   # không in ra stderr; đi qua logging
            log.info("%s %s", self.address_string(), fmt % args)

        # ----- tiện ích -----
        def _gui(self, ma: int, d: dict) -> None:
            noi = json.dumps(d, ensure_ascii=False).encode("utf-8")
            try:
                self.send_response(ma)
                self.send_header("content-type", "application/json; charset=utf-8")
                self.send_header("cache-control", "no-store")
                self.send_header("content-length", str(len(noi)))
                self.end_headers()
                self.wfile.write(noi)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as e:
                log.warning("client đóng kết nối trước khi nhận trả lời %s: %s", ma, e)

        def _co_khoa(self) -> bool:
            gui = self.headers.get("x-runner-key")
            if gui is None:
                return False
            return hmac.compare_digest(gui.encode("utf-8", "surrogateescape"), khoa_b)

        def _doc_body(self) -> bytes:
            """Đọc body (≤16 KB). Lớn hơn → 413 (xả bớt nếu vừa phải để client nhận được trả lời)."""
            cl = self.headers.get("content-length")
            if cl is None:
                return b""
            if not cl.isdigit():
                self.close_connection = True
                raise LoiApi(400, "content-length sai")
            n = int(cl)
            if n > BODY_TOI_DA:
                if n <= BODY_XA_TOI_DA:
                    self.rfile.read(n)
                self.close_connection = True
                raise LoiApi(413, "dữ liệu quá lớn")
            return self.rfile.read(n) if n else b""

        def _chay(self, viec_lam: Callable[[], tuple[int, dict]]) -> None:
            """Bọc mọi xử lý: lỗi nghiệp vụ → 4xx; lỗi bất ngờ → 500 JSON + log traceback (server sống tiếp)."""
            try:
                ma, d = viec_lam()
            except LoiApi as e:
                ma, d = e.ma, {"loi": e.thong_diep, **e.them}
            except TrungViec as e:
                ma, d = 409, {"loi": "đã có việc đang mở cùng loại và khoá", "trung": _ra(e.viec)}
            except SaiTrangThai as e:
                ma, d = 409, {"loi": f"trạng thái việc không cho thao tác này ({e})"}
            except VuotHanMuc as e:
                ma, d = 429, {"loi": f"vượt hạn mức: {e}"}
            except ThamSoLoi as e:
                them = getattr(e, "them", None)          # vd ChuaChotDuAnB: ung_vien_b cho web chọn lại
                ma, d = 400, {"loi": str(e), **(them if isinstance(them, dict) else {})}
            except sv.KhongTraDuoc as e:      # video/bản ghi dựng không còn lần được (dữ liệu đĩa đổi)
                ma, d = 409, {"loi": e.ly_do}
            except Exception:   # noqa: BLE001 — chốt chặn cuối: không để một request làm sập vòng phục vụ
                log.exception("lỗi bất ngờ khi xử lý %s %s", self.command, self.path)
                ma, d = 500, {"loi": "lỗi nội bộ bộ chạy việc (xem log máy nhà)"}
            self._gui(ma, d)

        # ----- GET -----
        def do_GET(self) -> None:   # noqa: N802
            def lam() -> tuple[int, dict]:
                if not self._co_khoa():
                    raise LoiApi(401, "thiếu hoặc sai x-runner-key")
                u = urlsplit(self.path)
                q = {k: v[-1] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
                p = u.path
                if p == "/suc-khoe":
                    return g_suc_khoe(q)
                if p == "/danh-muc":
                    return g_danh_muc(q)
                if p == "/viec":
                    return g_ds_viec(q)
                if m := _RE_ROUTE_ID.fullmatch(p):
                    return g_viec(m.group(1), q)
                if m := _RE_ROUTE_LOG.fullmatch(p):
                    return g_log(m.group(1), q)
                if m := _RE_ROUTE_DU_AN.fullmatch(p):
                    return g_du_an(m.group(1), q)
                if p == "/poster/folders":
                    return g_poster_folders(q)
                if m := _RE_ROUTE_SUA_GET.fullmatch(p):
                    uid, ma, ung_vien = m.groups()
                    if ma is None:
                        return g_sua_ds(uid, q)
                    return g_sua_ung_vien(uid, ma, q) if ung_vien else g_sua_chi_tiet(uid, ma, q)
                if p == "/hoc/bao-cao":
                    return g_hoc_bao_cao(q)
                if p == "/hoc/bai-hoc":
                    return g_hoc_bai_hoc(q)
                if p == "/radar/bang":
                    return g_radar_bang(q)
                if m := _RE_ROUTE_RADAR_UID.fullmatch(p):
                    return g_radar_uid(m.group(1), q)
                raise LoiApi(404, "không có API này")
            self._chay(lam)

        # ----- POST -----
        def do_POST(self) -> None:   # noqa: N802
            def lam() -> tuple[int, dict]:
                body_b = self._doc_body()
                if not self._co_khoa():
                    raise LoiApi(401, "thiếu hoặc sai x-runner-key")
                p = urlsplit(self.path).path
                ly_do = chu_ky.kiem_request(khoa_cong_khai, self.headers, "POST", p, body_b,
                                            int(time.time() * 1000), kho.dung_nonce)
                if ly_do is not None:
                    log.warning("từ chối POST %s: %s", p, ly_do)
                    raise LoiApi(401, "chữ ký request không hợp lệ")
                try:
                    body = json.loads(body_b.decode("utf-8")) if body_b else None
                except (UnicodeDecodeError, ValueError) as e:
                    raise ThamSoLoi("body không phải JSON UTF-8") from e
                if not isinstance(body, dict):
                    raise ThamSoLoi("body phải là JSON object")
                if p == "/viec":
                    return p_tao(body)
                if m := _RE_ROUTE_HANH_DONG.fullmatch(p):
                    return HANH_DONG[m.group(2)](m.group(1), body)
                if m := _RE_ROUTE_SUA_POST.fullmatch(p):
                    return p_ban_sua(m.group(1), m.group(2), body)
                if m := _RE_ROUTE_HOC_POST.fullmatch(p):
                    return p_hoc(m.group(1), m.group(2), body)
                if p == "/radar/goc":
                    return p_radar_goc(body)
                if p == "/radar/chup-lai":
                    return p_radar_chup_lai(body)
                if m := _RE_ROUTE_RADAR_GOC.fullmatch(p):
                    return p_radar_nhom(m.group(1), m.group(2), body)
                if m := _RE_ROUTE_RADAR_UID_HD.fullmatch(p):
                    return p_radar_uid(m.group(1), m.group(2), m.group(3), body)
                raise LoiApi(404, "không có API này")
            self._chay(lam)

        def _khong_ho_tro(self) -> None:
            def lam() -> tuple[int, dict]:
                if not self._co_khoa():
                    raise LoiApi(401, "thiếu hoặc sai x-runner-key")
                raise LoiApi(405, "sai phương thức")
            self._chay(lam)

        do_PUT = do_DELETE = do_PATCH = _khong_ho_tro   # noqa: N815

    return Handler
