"""Chữ ký Ed25519 của Worker cho runner (D7, docs/bo-chay-viec.md §8.3).

HỢP ĐỒNG BYTE-ĐÚNG với Worker (cf/src/worker.js) — kiểm chéo qua
``tools/runner/vector_ky.json``. Đổi bất kỳ chi tiết nào dưới đây phải đổi cả
Worker và sinh lại vector.

Quy ước chung
-------------
- Mọi chuỗi được mã hoá **UTF-8** (không BOM) trước khi ký / băm.
- ``sha256_hex(x)`` = SHA-256 của bytes UTF-8, viết **hex chữ thường**, 64 ký tự.
- Dấu phân cách là đúng một ký tự ``"\\n"`` (0x0A); không có ``"\\n"`` ở cuối.
- Không trường nào được chứa ``"\\n"`` hoặc ``"\\r"`` (hàm dựng chuỗi ném
  ``ValueError``), để không thể ghép trường làm lệch ranh giới.
- Chữ ký Ed25519 (64 byte) viết bằng **base64url KHÔNG padding** (86 ký tự
  ``[A-Za-z0-9_-]``). Có ``=`` ở cuối → bị từ chối.

Chuỗi ký request (mọi POST tới runner)
--------------------------------------
::

    "kho-runner-v1" "\\n" METHOD "\\n" PATH "\\n" NGAY "\\n" NONCE "\\n" sha256_hex(BODY)

- ``METHOD``: chữ in hoa (``POST``). Hàm tự ``upper()``.
- ``PATH``: đường dẫn runner nhận, KHÔNG có tiền tố ``/r``, bắt đầu bằng ``/``,
  không kèm query string. Ví dụ ``/viec``, ``/viec/j20261117210000ab12/huy``.
- ``NGAY``: unix **mili giây**, số nguyên thập phân không dấu, không số 0 thừa
  ở đầu (giống ``String(Date.now())`` trong JS).
- ``NONCE``: đúng 32 ký tự hex chữ thường.
- ``BODY``: đúng các byte thân request (body rỗng → sha256 của b"").

Header: ``x-ky-ngay: NGAY``, ``x-ky-nonce: NONCE``, ``x-ky: base64url(chữ ký)``.

Runner kiểm theo thứ tự: header hợp lệ → ``|bây giờ − NGAY| ≤ 120 000 ms`` →
chữ ký đúng → nonce chưa dùng (``dung_nonce`` ghi nhận luôn). Sai → lý do (401).
Nonce chỉ được ghi khi chữ ký đã đúng, nên request lệch giờ hoặc chữ ký sai
không tiêu nonce và không làm phình bảng nonce.

Chuỗi ký lời duyệt
------------------
::

    "kho-duyet-v1" "\\n" ID "\\n" LOAI "\\n" sha256_hex(THAM_SO_CHUAN) "\\n"
    sha256_hex(LOI_DUYET) "\\n" DUYET_LUC "\\n" BOI

- ``THAM_SO_CHUAN`` = ``json_chuan(tham_so)``:
  ``json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)``
  rồi UTF-8. Worker KHÔNG tự chuẩn hoá: nó băm nguyên chuỗi ``tham_so_chuan``
  nhận từ ``GET /r/viec/<id>``.
- ``LOI_DUYET``, ``BOI``, ``DUYET_LUC`` là chuỗi nguyên văn (không trim, không
  chuẩn hoá Unicode).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

log = logging.getLogger(__name__)

TIEN_TO_REQUEST = "kho-runner-v1"
TIEN_TO_DUYET = "kho-duyet-v1"
LECH_TOI_DA_MS = 120_000

_RE_NONCE = re.compile(r"[0-9a-f]{32}")
_RE_NGAY = re.compile(r"0|[1-9][0-9]{0,15}")
_RE_CHU_KY = re.compile(r"[A-Za-z0-9_-]{86}")


def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _kiem_truong(ten: str, gia_tri: str) -> str:
    if not isinstance(gia_tri, str):
        raise ValueError(f"{ten} phải là str, nhận {type(gia_tri).__name__}")
    if "\n" in gia_tri or "\r" in gia_tri:
        raise ValueError(f"{ten} chứa ký tự xuống dòng")
    return gia_tri


def json_chuan(obj: Any) -> str:
    """JSON chuẩn: sort_keys, separators (',', ':'), ensure_ascii=False.

    Phải trùng ``kieu.tham_so_chuan`` (B-1) và cột ``viec.tham_so`` (§4.2).
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def chuoi_ky_request(method: str, path: str, ngay_ms: int, nonce: str, body: bytes) -> bytes:
    """Dựng chuỗi ký request (xem docstring module). Trả bytes UTF-8."""
    method = _kiem_truong("method", method).upper()
    path = _kiem_truong("path", path)
    if not path.startswith("/") or "?" in path:
        raise ValueError("path phải bắt đầu bằng '/' và không kèm query")
    if isinstance(ngay_ms, bool) or not isinstance(ngay_ms, int) or ngay_ms < 0:
        raise ValueError("ngay_ms phải là int không âm")
    if not isinstance(nonce, str) or not _RE_NONCE.fullmatch(nonce):
        raise ValueError("nonce phải là 32 hex chữ thường")
    if not isinstance(body, (bytes, bytearray)):
        raise ValueError("body phải là bytes")
    phan = [TIEN_TO_REQUEST, method, path, str(ngay_ms), nonce, _sha256_hex(bytes(body))]
    return "\n".join(phan).encode("utf-8")


def chuoi_ky_duyet(id: str, loai: str, tham_so_chuan: str, loi_duyet: str,  # noqa: A002
                   duyet_luc: str, boi: str) -> bytes:
    """Dựng chuỗi ký lời duyệt (xem docstring module). Trả bytes UTF-8.

    ``tham_so_chuan`` và ``loi_duyet`` chỉ đi vào chuỗi dưới dạng sha256 nên
    được phép chứa xuống dòng; các trường còn lại thì không.
    """
    for ten, gia_tri in (("tham_so_chuan", tham_so_chuan), ("loi_duyet", loi_duyet)):
        if not isinstance(gia_tri, str):
            raise ValueError(f"{ten} phải là str")
    phan = [
        TIEN_TO_DUYET,
        _kiem_truong("id", id),
        _kiem_truong("loai", loai),
        _sha256_hex(tham_so_chuan.encode("utf-8")),
        _sha256_hex(loi_duyet.encode("utf-8")),
        _kiem_truong("duyet_luc", duyet_luc),
        _kiem_truong("boi", boi),
    ]
    return "\n".join(phan).encode("utf-8")


def nap_khoa_cong_khai(pem: bytes) -> Ed25519PublicKey:
    """Nạp khoá công khai PEM (SubjectPublicKeyInfo). Không phải Ed25519 → ValueError."""
    khoa = serialization.load_pem_public_key(pem)
    if not isinstance(khoa, Ed25519PublicKey):
        raise ValueError(f"khoá công khai không phải Ed25519: {type(khoa).__name__}")
    return khoa


def _giai_chu_ky(s: str | None) -> bytes | None:
    """base64url không padding → 64 byte; sai định dạng → None."""
    if not isinstance(s, str) or not _RE_CHU_KY.fullmatch(s):
        return None
    try:
        raw = base64.urlsafe_b64decode(s + "==")
    except (binascii.Error, ValueError):
        return None
    return raw if len(raw) == 64 else None


def _xac_minh(kcc: Ed25519PublicKey, chu_ky: bytes, du_lieu: bytes) -> bool:
    # Ed25519 verify của OpenSSL so sánh hằng thời gian; không tự so bằng ==.
    try:
        kcc.verify(chu_ky, du_lieu)
    except InvalidSignature:
        return False
    return True


def _lay_header(headers: Mapping[str, str], ten: str) -> str | None:
    gia_tri = headers.get(ten)
    if gia_tri is not None:
        return gia_tri
    ten_thuong = ten.lower()
    for k, v in headers.items():
        if isinstance(k, str) and k.lower() == ten_thuong:
            return v
    return None


def kiem_request(kcc: Ed25519PublicKey, headers: Mapping[str, str], method: str, path: str,
                 body: bytes, bay_gio_ms: int,
                 dung_nonce: Callable[[str, float], bool]) -> str | None:
    """Kiểm chữ ký request ghi. None = hợp lệ; ngược lại trả lý do (để log, trả 401).

    ``dung_nonce(nonce, luc_giay)`` phải ghi nhận nonce một cách nguyên tử và trả
    True nếu nonce mới, False nếu đã dùng (hoặc không ghi nhận được). Nó chỉ được
    gọi SAU khi lệch giờ và chữ ký đều đã qua.
    """
    ngay_s = _lay_header(headers, "x-ky-ngay")
    nonce = _lay_header(headers, "x-ky-nonce")
    ky_s = _lay_header(headers, "x-ky")
    if ngay_s is None or nonce is None or ky_s is None:
        return "thiếu header chữ ký (x-ky-ngay, x-ky-nonce, x-ky)"
    if not _RE_NGAY.fullmatch(ngay_s):
        return "x-ky-ngay sai định dạng"
    if not _RE_NONCE.fullmatch(nonce):
        return "x-ky-nonce sai định dạng (cần 32 hex chữ thường)"
    chu_ky = _giai_chu_ky(ky_s)
    if chu_ky is None:
        return "x-ky sai định dạng (cần base64url không padding, 64 byte)"

    ngay_ms = int(ngay_s)
    if abs(bay_gio_ms - ngay_ms) > LECH_TOI_DA_MS:
        return f"lệch giờ quá {LECH_TOI_DA_MS // 1000} s ({(bay_gio_ms - ngay_ms) / 1000:.0f} s)"

    try:
        chuoi = chuoi_ky_request(method, path, ngay_ms, nonce, body)
    except ValueError as e:
        return f"không dựng được chuỗi ký: {e}"
    if not _xac_minh(kcc, chu_ky, chuoi):
        return "chữ ký sai"

    # Ghi nonce SAU khi chữ ký đúng: request giả mạo không tiêu/ghi được nonce.
    if not dung_nonce(nonce, bay_gio_ms / 1000):
        return "nonce đã dùng (phát lại)"
    return None


def kiem_duyet(kcc: Ed25519PublicKey, viec: dict) -> bool:
    """Kiểm ``chu_ky_duyet`` với các trường ĐANG LƯU của việc.

    Dùng ``viec['id']``, ``loai``, ``tham_so`` (chuỗi JSON hoặc dict — luôn
    chuẩn hoá lại bằng ``json_chuan``), ``loi_duyet``, ``duyet_luc``,
    ``duyet_boi`` (= BOI trong chuỗi ký), ``chu_ky_duyet``. Thiếu/sai → False.
    """
    viec_id = viec.get("id")
    try:
        tham_so = viec["tham_so"]
        if isinstance(tham_so, str):
            tham_so = json.loads(tham_so)
        chuoi = chuoi_ky_duyet(viec["id"], viec["loai"], json_chuan(tham_so),
                               viec["loi_duyet"], viec["duyet_luc"], viec["duyet_boi"])
    except (KeyError, ValueError, TypeError) as e:
        log.warning("kiem_duyet %s: dữ liệu duyệt hỏng: %s", viec_id, e)
        return False
    chu_ky = _giai_chu_ky(viec.get("chu_ky_duyet"))
    if chu_ky is None:
        log.warning("kiem_duyet %s: chu_ky_duyet thiếu hoặc sai định dạng", viec_id)
        return False
    if not _xac_minh(kcc, chu_ky, chuoi):
        log.warning("kiem_duyet %s: chữ ký duyệt KHÔNG khớp dữ liệu đang lưu", viec_id)
        return False
    return True


class BoNhoNonce:
    """Bộ nhớ nonce trong RAM, có hạn, xoá theo thời gian; dùng làm ``dung_nonce``.

    - ``song_s`` phải ≥ 2 × cửa sổ lệch (240 s): nonce chỉ được quên khi mọi
      request mang nó chắc chắn đã bị chặn bởi kiểm lệch giờ.
    - Đầy mà không xoá được nonce hết hạn → từ chối (fail-closed), không đẩy
      nonce còn hạn ra (đẩy ra sẽ mở đường phát lại).
    Runner thật dùng bảng ``nonce`` trong SQLite; lớp này cho test và dự phòng.
    """

    def __init__(self, song_s: float = 300.0, toi_da: int = 100_000) -> None:
        if song_s < 2 * LECH_TOI_DA_MS / 1000:
            raise ValueError("song_s phải ≥ 240 s (2 × cửa sổ lệch giờ)")
        if toi_da < 1:
            raise ValueError("toi_da phải ≥ 1")
        self._song_s = song_s
        self._toi_da = toi_da
        self._da_dung: OrderedDict[str, float] = OrderedDict()
        self._khoa = threading.Lock()

    def __len__(self) -> int:
        with self._khoa:
            return len(self._da_dung)

    def _don(self, luc: float) -> None:
        moc = luc - self._song_s
        while self._da_dung:
            nonce_dau, luc_dau = next(iter(self._da_dung.items()))
            if luc_dau >= moc:
                break
            self._da_dung.popitem(last=False)

    def __call__(self, nonce: str, luc: float) -> bool:
        with self._khoa:
            self._don(luc)
            if nonce in self._da_dung:
                return False
            if len(self._da_dung) >= self._toi_da:
                log.warning("BoNhoNonce đầy (%d), từ chối nonce mới", self._toi_da)
                return False
            self._da_dung[nonce] = luc
            return True
