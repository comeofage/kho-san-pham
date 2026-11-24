# -*- coding: utf-8 -*-
"""Client EchoTik chỉ đọc (GET) cho Radar UID. Hợp đồng: docs/radar-uid.md §2, §6.3, §6.5, §6.6, §7.2.

- Header đúng §2.1; `x-region: VN` ở header, KHÔNG region trong URL.
- Token đọc từ file MỖI lần gọi (cache theo (đường dẫn, mtime)); không vào log/thông báo lỗi/repr.
- Lỗi chỉ mang mã cố định (+ mã HTTP), không chép thân phản hồi.
- Nhịp >= 1,3 s giữa hai GET; timeout/5xx/ngắt kết nối thử lại <= 2 lần (3 s, 6 s); 4xx/429/HTML không thử lại.
- Không `print`.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, TypedDict

log = logging.getLogger("runner.echotik")

GOC = "https://echotik.live"
TIMEOUT_S = 30
DOC_TOI_DA = 8 * 1024 * 1024            # chặn thân phản hồi quá lớn
CHO_THU_LAI_S = (3.0, 6.0)              # §6.5: tối đa 2 lần thử lại
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
RE_UID = re.compile(r"^\d{19}$")

MA_LOI = ("token_thieu", "token_het_han", "rate_limit", "mang", "dinh_dang", "khong_tim_thay")


# ------------------------------------------------------------------ kiểu (§7.2, bản riêng của module)


class HangVideo(TypedDict):
    video_id: str
    creator: str
    follower: str | None
    view: str
    ban: str | None
    dang_luc: str
    is_promote: int | None


class MetaTrang(TypedDict):
    current_page: int | None
    last_page: int | None


class UngVien(TypedDict):
    uid: str
    ten: str
    gia: str | None
    ban_7d: str | None


class LoiEchoTik(Exception):
    """`ma` ∈ MA_LOI. Thông điệp chỉ gồm mã (+ mã HTTP), tuyệt đối không token/thân phản hồi."""

    def __init__(self, ma: str, http: int | None = None) -> None:
        self.ma = ma
        self.http = http
        super().__init__(ma if http is None else f"{ma} (HTTP {http})")


class HetNganSach(Exception):
    """`tinh_goi` từ chối: hết ngân sách gọi trong ngày."""


class _ChanRedirect(urllib.request.HTTPRedirectHandler):
    """Không theo redirect: `None` ⇒ urllib ném `HTTPError` mang mã 3xx, không gửi lại request (kể cả header
    Authorization/token) tới host khác."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401, ARG002
        return None


_OPENER = urllib.request.build_opener(_ChanRedirect)


def mo_url_khong_theo_redirect(req, timeout=None):
    """Thay `urlopen` mặc định: mọi 3xx thành `HTTPError` (client coi là `dinh_dang`)."""
    return _OPENER.open(req, timeout=timeout)


# ------------------------------------------------------------------ client


class EchoTik:
    def __init__(self, token_file: Path, *, mo_url: Callable = mo_url_khong_theo_redirect,
                 ngu: Callable[[float], None] = time.sleep,
                 dong_ho: Callable[[], float] = time.monotonic, cach_toi_thieu_s: float = 1.3,
                 tinh_goi: Callable[[int], bool] | None = None) -> None:
        self._token_file = Path(token_file)
        self._mo_url = mo_url
        self._ngu = ngu
        self._dong_ho = dong_ho
        self._cach = cach_toi_thieu_s
        self._tinh_goi = tinh_goi
        self._lan_cuoi: float | None = None
        self._cache: tuple[tuple[str, int], tuple[str, str]] | None = None
        self.so_goi: int = 0

    def __repr__(self) -> str:                      # không để lộ token qua repr mặc định
        return f"<EchoTik so_goi={self.so_goi}>"

    # --- token

    def _doc_token(self) -> tuple[str, str]:
        try:
            khoa = (str(self._token_file), self._token_file.stat().st_mtime_ns)
        except OSError:
            self._cache = None
            raise LoiEchoTik("token_thieu") from None
        if self._cache is not None and self._cache[0] == khoa:
            return self._cache[1]
        try:
            d = json.loads(self._token_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._cache = None
            raise LoiEchoTik("token_thieu") from None
        tok = d.get("token") if isinstance(d, dict) else None
        if not isinstance(tok, str) or not tok.strip():
            self._cache = None
            raise LoiEchoTik("token_thieu")
        usr = str(d.get("user_id") or "")
        self._cache = (khoa, (tok.strip(), usr))
        return self._cache[1]

    def _headers(self) -> dict[str, str]:
        tok, usr = self._doc_token()
        return {
            "Authorization": f"Bearer {tok}", "X-User-Id": usr, "token": tok, "user_id": usr,
            "x-region": "VN",                                # PHẢI ở header, không để trong URL
            "User-Agent": UA, "Accept": "application/json, text/plain, */*",
            "Origin": GOC, "Referer": GOC + "/",
        }

    # --- một lần gửi (đã qua ngân sách + nhịp)

    def _cho_nhip(self) -> None:
        if self._lan_cuoi is None:
            return
        cho = self._cach - (self._dong_ho() - self._lan_cuoi)
        if cho > 0:
            self._ngu(cho)

    def _mot_lan(self, url: str, headers: dict[str, str]) -> tuple[int, str, bytes]:
        """Trả (status, content-type, thân). Lỗi mạng/HTTP đã chuyển thành mã; 5xx và mạng ném `_ThuLai`."""
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with self._mo_url(req, timeout=TIMEOUT_S) as r:
                status = int(getattr(r, "status", 200))
                ctype = str(r.headers.get("content-type", "") or "")
                body = r.read(DOC_TOI_DA) if status == 200 else b""
            return status, ctype, body
        except urllib.error.HTTPError as e:                   # trước URLError (là lớp con)
            return int(e.code), "", b""
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            raise _ThuLai(None) from None

    def _get(self, path: str, query: dict | None = None) -> dict:
        url = GOC + path + ("?" + urllib.parse.urlencode(query) if query else "")
        headers = self._headers()                              # đọc file token MỖI lần gọi
        lan = 0
        while True:
            if self._tinh_goi is not None and not self._tinh_goi(1):
                raise HetNganSach("het ngan sach goi EchoTik")
            self._cho_nhip()
            self.so_goi += 1
            try:
                status, ctype, body = self._mot_lan(url, headers)
            except _ThuLai as t:
                status, ctype, body = (t.http or 0), "", b""
                loi_tam = True
            else:
                loi_tam = status >= 500
            finally:
                self._lan_cuoi = self._dong_ho()
            if not loi_tam:
                return self._xu_ly(status, ctype, body)
            if lan >= len(CHO_THU_LAI_S):
                raise LoiEchoTik("mang", status or None)
            log.warning("echotik: loi tam thoi (%s), thu lai %d/%d", status or "mang", lan + 1, len(CHO_THU_LAI_S))
            self._ngu(CHO_THU_LAI_S[lan])
            lan += 1

    @staticmethod
    def _xu_ly(status: int, ctype: str, body: bytes) -> dict:
        if status in (401, 403):
            raise LoiEchoTik("token_het_han", status)
        if status == 429:
            raise LoiEchoTik("rate_limit", 429)
        if status == 404:
            raise LoiEchoTik("khong_tim_thay", 404)
        if status != 200:
            raise LoiEchoTik("dinh_dang", status)
        if "text/html" in ctype.lower() or body.lstrip()[:1] == b"<":
            raise LoiEchoTik("token_het_han", status)          # trang "Oops": token hết hạn hoặc tham số bị từ chối
        try:
            j = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise LoiEchoTik("dinh_dang", status) from None
        if not isinstance(j, dict) or "data" not in j:
            raise LoiEchoTik("dinh_dang", status)
        return j

    # --- API

    @staticmethod
    def _kiem_uid(uid: str) -> str:
        if not isinstance(uid, str) or not RE_UID.match(uid):
            raise LoiEchoTik("dinh_dang")
        return uid

    def chi_tiet(self, uid: str) -> dict:
        """E1: object sản phẩm thô."""
        j = self._get(f"/api/v1/data/products/{self._kiem_uid(uid)}")
        d = j["data"]
        if d is None or d == {}:
            raise LoiEchoTik("khong_tim_thay")
        if not isinstance(d, dict):
            raise LoiEchoTik("dinh_dang")
        return d

    def video(self, uid: str, trang: int = 1, moi_trang: int = 50) -> tuple[list[dict], MetaTrang]:
        """E2: video của sản phẩm, mới nhất trước (`order=publish_time&sort=desc`)."""
        j = self._get(f"/api/v1/data/products/{self._kiem_uid(uid)}/videos",
                      {"page": int(trang), "per_page": int(moi_trang), "order": "publish_time", "sort": "desc"})
        return _ds(j), chuan_meta(j.get("meta"))

    def tim(self, tu_khoa: str, trang: int = 1, moi_trang: int = 50) -> tuple[list[dict], MetaTrang]:
        """E4: tìm sản phẩm theo từ khoá (7 ngày, bán chạy trước)."""
        j = self._get("/api/v1/data/products",
                      {"page": int(trang), "per_page": int(moi_trang), "order": "total_sale_7d_cnt",
                       "sort": "desc", "dateRange": 7, "keyword": str(tu_khoa)})
        return _ds(j), chuan_meta(j.get("meta"))


class _ThuLai(Exception):
    def __init__(self, http: int | None) -> None:
        super().__init__()
        self.http = http


def _ds(j: dict) -> list[dict]:
    d = j["data"]
    if not isinstance(d, list):
        raise LoiEchoTik("dinh_dang")
    return d


# ------------------------------------------------------------------ chuẩn hoá


def _chuoi(v: object) -> str | None:
    """Chuỗi không rỗng, hoặc số nguyên -> chuỗi; còn lại None (không 0 giả)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return None


def _so_nguyen(v: object) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if v >= 0 else None
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def chuan_meta(raw: object) -> MetaTrang:
    if not isinstance(raw, dict):
        return {"current_page": None, "last_page": None}
    return {"current_page": _so_nguyen(raw.get("current_page")), "last_page": _so_nguyen(raw.get("last_page"))}


def chuan_video(raw: dict) -> HangVideo | None:
    """Một phần tử E2 -> HangVideo. Thiếu video_id/publish_time/views_count => None. BỎ `update_time` (§2.3.2)."""
    if not isinstance(raw, dict):
        return None
    vid = _chuoi(raw.get("video_id"))
    dang = _chuoi(raw.get("publish_time"))
    view = _chuoi(raw.get("views_count"))                    # 326 hoặc '21.81K' -> luôn chuỗi
    if vid is None or dang is None or view is None:
        return None
    inf = raw.get("influencer")
    inf = inf if isinstance(inf, dict) else {}
    creator = (_chuoi(inf.get("unique_id")) or _chuoi(raw.get("influencer_name"))
               or _chuoi(raw.get("influencer_id")) or "")
    kp = raw.get("is_promote")
    if isinstance(kp, bool):
        promote: int | None = int(kp)
    elif kp in (0, 1):
        promote = int(kp)
    else:
        promote = None
    return {"video_id": vid, "creator": creator, "follower": _chuoi(inf.get("follower_count")),
            "view": view, "ban": _chuoi(raw.get("sales")), "dang_luc": dang, "is_promote": promote}


def chuan_ung_vien(raw: dict) -> UngVien | None:
    """Một phần tử E4 -> UngVien. product_id phải là 19 chữ số (D3), có tên."""
    if not isinstance(raw, dict):
        return None
    uid = _chuoi(raw.get("product_id"))
    ten = _chuoi(raw.get("product_name"))
    if uid is None or ten is None or not RE_UID.match(uid):
        return None
    return {"uid": uid, "ten": ten, "gia": _chuoi(raw.get("avg_price")), "ban_7d": _chuoi(raw.get("total_sale_7d_cnt"))}


def anh_bia(e1: dict) -> str:
    """E1 -> URL ảnh bìa = `images[0]` nếu là chuỗi không rỗng, ngược lại "". KHÔNG kiểm host (kho kiểm RE_ANH)."""
    if not isinstance(e1, dict):
        return ""
    ds = e1.get("images")
    if not isinstance(ds, list) or not ds:
        return ""
    v = ds[0]
    return v if isinstance(v, str) and v.strip() else ""


_KHOA_THEM = ("sale_30d_cnt", "gmv_amt", "gmv_30d_amt", "total_ifl_cnt", "ifl_30d_cnt", "total_video_cnt",
              "video_30d_cnt", "total_live_cnt", "live_30d_cnt", "review_count", "original_price")


def chi_so_them(e1: dict) -> dict:
    """E1 -> các chỉ số xu hướng đã đo từ chính E1 (không tốn thêm GET): chỉ khoá trong danh sách, giá trị chuỗi/số
    (≤ 32 ký tự), thiếu thì bỏ khoá (không điền 0). `rating` và `hang_nganh` lấy từ `labels`."""
    if not isinstance(e1, dict):
        return {}
    ra: dict = {}

    def nhan(k: str, v: object) -> None:
        if isinstance(v, bool) or not isinstance(v, (str, int, float)):
            return
        if isinstance(v, str) and (not v.strip() or len(v) > 32):
            return
        ra[k] = v

    for k in _KHOA_THEM:
        nhan(k, e1.get(k))
    lb = e1.get("labels")
    if isinstance(lb, dict):
        nhan("rating", lb.get("rating"))
        nhan("hang_nganh", lb.get("total_category_sale_rank"))
    return ra


def anh_ung_vien(raw: dict) -> str:
    """Một phần tử E4 -> `cover_url` (chuỗi không rỗng) hoặc "". Hàm riêng, KHÔNG đổi `UngVien`/`chuan_ung_vien`
    (khoá TypedDict §7.2 được test so khớp giữa 3 module); script tự giữ map uid -> ảnh. KHÔNG kiểm host."""
    if not isinstance(raw, dict):
        return ""
    v = raw.get("cover_url")
    return v if isinstance(v, str) and v.strip() else ""
