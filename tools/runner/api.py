"""HTTP API của bộ chạy việc (docs/bo-chay-viec.md §8.1, §4.3, §8.3) — phiếu B-2, đợt 3.

Hai lớp kiểm cho mọi request:
- `x-runner-key` (so hằng thời gian bằng hmac.compare_digest) cho MỌI route, kể cả route lạ;
- chữ ký Ed25519 của Worker (`chu_ky.kiem_request`) cho MỌI POST. `boi` chỉ được tin vì nằm trong body đã ký.

Đợt 3: `/poster/folders` và `/viec/<id>/duyet` trả 404; `tra-loi` chỉ nhận giá trị nút
(quy tắc khớp Worker: chuỗi 1–120 đơn vị UTF-16, không ký tự điều khiển [\\x00-\\x1f\\x7f] kể cả \\t).

Mọi lỗi bất ngờ trong handler → 500 JSON (không lộ chi tiết), log đủ traceback; server vẫn sống.
"""
from __future__ import annotations

import hmac
import json
import logging
import re
import threading
import time
import uuid
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import chu_ky
from .danh_muc import DANH_MUC, LoaiViec, lay_loai, tham_so_chuan
from .du_an import ds_du_an
from .han_muc import HAN_MUC_TRAN, kiem_han_muc
from .kho_viec import KhoViec
from .kieu import (DANG_MO, TRANG_THAI, CanNguoiDung, MoiTruong, SaiTrangThai, ThamSoLoi, TrungViec,
                   VuotHanMuc, gio_vn)
from .phieu import GIA_TRI_KHONG_RO, GIA_TRI_VIEC_TAY

log = logging.getLogger(__name__)

BODY_TOI_DA = 16 * 1024            # khớp video_server / Worker (§3.2)
BODY_XA_TOI_DA = 256 * 1024        # body lớn hơn mức này: không đọc xả, đóng kết nối
TRA_LOI_TOI_DA_UTF16 = 120         # khớp Worker TRA_LOI_TOI_DA (JS String.length = đơn vị UTF-16)
GIOI_HAN_MAC_DINH = 50
GIOI_HAN_TOI_DA = 500
BI_TU_CHOI_TOI_DA = 20             # số mục ket_qua.bi_tu_choi tối đa trả ra (R-05 P2-2)
BI_TU_CHOI_INPUT_TOI_DA = 200      # ký tự tối đa của mỗi `input`/`tool_name`

# Khoá do runner tự gắn vào tham_so (không phải input web). Bỏ đi trước khi kiểm lại ở chay-lai (P3-2).
KHOA_RUNNER_GAN = ("ngay_tao",)
# Trường của §4.2 KHÔNG trả ra ngoài (§8.1).
TRUONG_AN = ("pid", "pid_tao_luc", "session_id", "chu_ky_duyet")

_RE_ID = r"j\d{14}[a-z0-9]{4}"
_RE_ROUTE_ID = re.compile(rf"^/viec/({_RE_ID})$", re.ASCII)
_RE_ROUTE_LOG = re.compile(rf"^/viec/({_RE_ID})/log$", re.ASCII)
_RE_ROUTE_HANH_DONG = re.compile(rf"^/viec/({_RE_ID})/(tra-loi|duyet|tu-choi|huy|chay-tiep|chay-lai)$", re.ASCII)
_RE_ROUTE_DU_AN = re.compile(r"^/du-an/(\d{19})$", re.ASCII)
_RE_UID = re.compile(r"^\d{19}$", re.ASCII)
_RE_SO = re.compile(r"^\d{1,9}$", re.ASCII)
_RE_BOI = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$", re.ASCII)
_RE_DIEU_KHIEN = re.compile("[\x00-\x1f\x7f]")


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


def viec_ra(v: dict, chi_tiet: bool = True, che: Callable[[str], str] | None = None) -> dict:
    """Việc trả ra web (§8.1): bỏ trường nhạy cảm, thêm co_session / co_the_chay_tiep.

    `ket_qua.bi_tu_choi`: danh sách (chi_tiet=False) bỏ hẳn; chi tiết → bản gọn (bi_tu_choi_gon).
    `che` (R-06 P3-3): che mọi chuỗi trả ra (loi, ghi_chu, can_ban, cau_hoi, ket_qua…) — dữ liệu cũ trong DB
    có thể chưa che. None = không che (giữ chữ ký cũ). Không sửa dict `v` gốc.
    """
    d = {k: x for k, x in v.items() if k not in TRUONG_AN}
    kq = d.get("ket_qua")
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
    d["co_the_chay_tiep"] = co_the_chay_tiep(v)
    return d


def tien_trinh_cu_con_song(v: dict) -> bool:
    """R-07 P2-4: vòng chạy không giết được tiến trình của việc → đánh dấu `ket_qua.khong_giet_duoc`."""
    kq = v.get("ket_qua")
    return isinstance(kq, dict) and kq.get("khong_giet_duoc") is True


def co_the_chay_tiep(v: dict) -> bool:
    return (v.get("trang_thai") == "loi" and int(v.get("phien_da_tao") or 0) == 1
            and int(v.get("so_lan_claude") or 0) > 0 and not tien_trinh_cu_con_song(v))


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
                che: Callable[[str], str] | None = None) -> type[BaseHTTPRequestHandler]:
    """Tạo lớp handler gắn sẵn phụ thuộc. Dùng với ThreadingHTTPServer(("127.0.0.1", cong), H).

    `che` (R-06 P3-3): hàm che bí mật áp lên mọi văn bản việc trả ra web (viec_ra, su_kien, tra_loi).
    None = không che (giữ tương thích chữ ký cũ); runner thật luôn truyền bộ che."""
    if not isinstance(khoa, str) or len(khoa) < 16:
        raise ValueError("khoá runner phải là chuỗi ≥16 ký tự")
    khoa_b = khoa.encode("utf-8")
    khoa_ghi = threading.Lock()     # tuần tự hoá mọi thao tác ghi qua API (hạn mức + tạo, trả lời + chuyển)

    def _ra(v: dict, chi_tiet: bool = True) -> dict:
        return viec_ra(v, chi_tiet, che)

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

    def _tao_viec(loai: LoaiViec, ts_tho: dict, boi: str, chay_lai_tu: str | None = None) -> dict:
        ts = loai.kiem_tham_so(ts_tho, mt)        # chỉ gọi trên input thô (P3-2)
        khoa_chong_trung = loai.tinh_khoa(ts)
        with khoa_ghi:
            kiem_han_muc(kho, loai.ma, ts, hm, "tao", boi)
            tt, buoc, cau_hoi = _trang_thai_dau(loai, ts)
            sid = str(uuid.uuid4()) if loai.agent else None
            return kho.tao(loai.ma, khoa_chong_trung, ts, loai.lan_chay, tt, boi, buoc=buoc, cau_hoi=cau_hoi,
                           session_id=sid, chay_lai_tu=chay_lai_tu)

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
            "canh_bao": list(canh_bao),
        }

    def g_danh_muc(_q) -> tuple[int, dict]:
        dot = dot_bat_hieu_luc(hm)
        return 200, {"loai": [{"ma": l.ma, "ten": l.ten, "dot": l.dot, "ton_tien": l.ton_tien,
                               "lan_chay": l.lan_chay, "tham_so": [dict(t) for t in l.tham_so]}
                              for l in DANH_MUC.values() if l.dot <= dot]}

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
        uid = q.get("uid")
        if uid is not None and not _RE_UID.fullmatch(uid):
            raise ThamSoLoi("uid phải là 19 chữ số")
        if uid is None:
            ds = kho.ds(tt, gioi_han=gioi_han)
        else:
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

    # ----- POST -----
    def p_tao(body: dict) -> tuple[int, dict]:
        boi = _boi(body)
        ma = body.get("loai")
        if not isinstance(ma, str):
            raise ThamSoLoi("loai thiếu")
        loai = lay_loai(ma, dot_bat_hieu_luc(hm))
        ts_tho = body.get("tham_so", {})
        return 201, {"viec": _ra(_tao_viec(loai, ts_tho, boi))}

    def p_tra_loi(id_: str, body: dict) -> tuple[int, dict]:
        boi = _boi(body)
        with khoa_ghi:
            v = _lay_viec(id_)
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
            if tien_trinh_cu_con_song(v):
                raise LoiApi(409, "không chạy tiếp được: tiến trình cũ của việc có thể còn sống (runner không giết "
                                  "được) — kiểm tay trên máy rồi dùng Chạy lại")
            if not co_the_chay_tiep(v):
                raise LoiApi(409, "không chạy tiếp được: cần trạng thái lỗi và phiên Claude đã tạo")
            loai = lay_loai(v["loai"], dot_bat_hieu_luc(hm))
            if loai.ton_tien and not chu_ky.kiem_duyet(khoa_cong_khai, v):
                raise LoiApi(409, "chữ ký duyệt cũ không khớp dữ liệu đang lưu — tạo lại việc")
            kiem_han_muc(kho, loai.ma, v.get("tham_so") or {}, hm, "nhan", boi)
            moi = kho.chuyen(id_, ["loi"], "cho", boi, "chạy tiếp (resume phiên Claude)")
        return 200, {"viec": _ra(moi)}

    def p_chay_lai(id_: str, body: dict) -> tuple[int, dict]:
        boi = _boi(body)
        v = _lay_viec(id_)
        if v["trang_thai"] not in ("loi", "huy"):
            raise LoiApi(409, "chỉ chạy lại được việc lỗi hoặc đã huỷ")
        loai = lay_loai(v["loai"], dot_bat_hieu_luc(hm))
        moi = _tao_viec(loai, tham_so_tho_tu_luu(v.get("tham_so") or {}), boi, chay_lai_tu=id_)
        return 201, {"viec": _ra(moi)}

    def p_duyet(_id: str, _body: dict) -> tuple[int, dict]:
        raise LoiApi(404, "duyệt chưa mở ở đợt 3")

    HANH_DONG = {"tra-loi": p_tra_loi, "huy": p_huy, "tu-choi": p_tu_choi, "chay-tiep": p_chay_tiep,
                 "chay-lai": p_chay_lai, "duyet": p_duyet}

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
                ma, d = 400, {"loi": str(e)}
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
                raise LoiApi(404, "không có API này")   # gồm /poster/folders (đợt 4)
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
