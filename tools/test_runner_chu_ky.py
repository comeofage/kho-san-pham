"""Test B-1c: chữ ký Ed25519 của Worker (D7, docs/bo-chay-viec.md §8.3).

Mọi khoá trong file này là khoá TEST (seed cố định hoặc sinh trong tmp_path),
không bao giờ là khoá thật.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

THU_MUC_RUNNER = Path(__file__).resolve().parent / "runner"
sys.path.insert(0, str(THU_MUC_RUNNER))

import chu_ky  # noqa: E402
import spike_claude  # noqa: E402
import tao_khoa_ky  # noqa: E402

SEED_TEST = bytes(range(32))
NGAY = 1_763_380_800_000  # ms
NONCE = "0123456789abcdef0123456789abcdef"


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


@pytest.fixture()
def khoa() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(SEED_TEST)


@pytest.fixture()
def kcc(khoa: Ed25519PrivateKey) -> Ed25519PublicKey:
    pem = khoa.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return chu_ky.nap_khoa_cong_khai(pem)


class NonceGia:
    """dung_nonce giả: True lần đầu, False khi lặp."""

    def __init__(self) -> None:
        self.da_dung: dict[str, float] = {}

    def __call__(self, nonce: str, luc: float) -> bool:
        if nonce in self.da_dung:
            return False
        self.da_dung[nonce] = luc
        return True


def _headers_ky(khoa: Ed25519PrivateKey, method: str, path: str, body: bytes,
                ngay: int = NGAY, nonce: str = NONCE) -> dict[str, str]:
    chuoi = chu_ky.chuoi_ky_request(method, path, ngay, nonce, body)
    return {"x-ky-ngay": str(ngay), "x-ky-nonce": nonce, "x-ky": _b64url(khoa.sign(chuoi))}


# ---------- chuỗi ký: đúng từng byte ----------

def test_chuoi_ky_request_dung_dinh_dang() -> None:
    body = '{"boi":"nhan","loai":"radar_ban_tin","tham_so":{"ghi_chu":"Việt"}}'.encode()
    sha = hashlib.sha256(body).hexdigest()
    mong = f"kho-runner-v1\nPOST\n/viec\n{NGAY}\n{NONCE}\n{sha}".encode("utf-8")
    assert chu_ky.chuoi_ky_request("POST", "/viec", NGAY, NONCE, body) == mong


def test_chuoi_ky_duyet_dung_dinh_dang() -> None:
    ts = '{"uid":"7000000000000000001"}'
    loi = "Duyệt, làm luôn"
    mong = (
        "kho-duyet-v1\nj20261117210000ab12\nvoice_genmax\n"
        + hashlib.sha256(ts.encode()).hexdigest() + "\n"
        + hashlib.sha256(loi.encode("utf-8")).hexdigest() + "\n"
        + "2026-11-17T21:05:00+07:00\nnhan"
    ).encode("utf-8")
    assert chu_ky.chuoi_ky_duyet(
        "j20261117210000ab12", "voice_genmax", ts, loi, "2026-11-17T21:05:00+07:00", "nhan"
    ) == mong


def test_chuoi_ky_tu_choi_xuong_dong_trong_truong() -> None:
    with pytest.raises(ValueError):
        chu_ky.chuoi_ky_request("POST", "/viec\nx", NGAY, NONCE, b"")
    with pytest.raises(ValueError):
        chu_ky.chuoi_ky_duyet("j1", "a\nb", "{}", "x", "t", "nhan")


def test_json_chuan_khop_quy_uoc() -> None:
    ts = {"b": 1, "a": "Việt Nam", "c": [True, None]}
    assert chu_ky.json_chuan(ts) == '{"a":"Việt Nam","b":1,"c":[true,null]}'


# ---------- kiem_request ----------

def test_kiem_request_dung_tra_none(khoa, kcc) -> None:
    body = '{"boi":"nhan"}'.encode()
    h = _headers_ky(khoa, "POST", "/viec", body)
    assert chu_ky.kiem_request(kcc, h, "POST", "/viec", body, NGAY + 5_000, NonceGia()) is None


def test_kiem_request_header_khong_phan_biet_hoa_thuong(khoa, kcc) -> None:
    body = b"{}"
    h = {k.upper(): v for k, v in _headers_ky(khoa, "POST", "/viec", body).items()}
    assert chu_ky.kiem_request(kcc, h, "POST", "/viec", body, NGAY, NonceGia()) is None


def test_kiem_request_sai_chu_ky(khoa, kcc) -> None:
    body = b"{}"
    h = _headers_ky(khoa, "POST", "/viec", body)
    khac = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    h["x-ky"] = _b64url(khac.sign(chu_ky.chuoi_ky_request("POST", "/viec", NGAY, NONCE, body)))
    assert chu_ky.kiem_request(kcc, h, "POST", "/viec", body, NGAY, NonceGia()) is not None


def test_kiem_request_body_doi_1_byte(khoa, kcc) -> None:
    body = b'{"boi":"nhan"}'
    h = _headers_ky(khoa, "POST", "/viec", body)
    doi = b'{"boi":"nhao"}'
    assert chu_ky.kiem_request(kcc, h, "POST", "/viec", doi, NGAY, NonceGia()) is not None


def test_kiem_request_path_hoac_method_doi(khoa, kcc) -> None:
    body = b"{}"
    h = _headers_ky(khoa, "POST", "/viec/j1/huy", body)
    assert chu_ky.kiem_request(kcc, h, "POST", "/viec/j2/huy", body, NGAY, NonceGia()) is not None
    assert chu_ky.kiem_request(kcc, h, "PUT", "/viec/j1/huy", body, NGAY, NonceGia()) is not None


@pytest.mark.parametrize("lech_ms", [121_000, -121_000])
def test_kiem_request_lech_121s(khoa, kcc, lech_ms) -> None:
    body = b"{}"
    h = _headers_ky(khoa, "POST", "/viec", body)
    ly_do = chu_ky.kiem_request(kcc, h, "POST", "/viec", body, NGAY + lech_ms, NonceGia())
    assert ly_do is not None and "giờ" in ly_do


@pytest.mark.parametrize("lech_ms", [120_000, -120_000])
def test_kiem_request_lech_dung_120s_van_qua(khoa, kcc, lech_ms) -> None:
    body = b"{}"
    h = _headers_ky(khoa, "POST", "/viec", body)
    assert chu_ky.kiem_request(kcc, h, "POST", "/viec", body, NGAY + lech_ms, NonceGia()) is None


def test_kiem_request_nonce_lap(khoa, kcc) -> None:
    body = b"{}"
    h = _headers_ky(khoa, "POST", "/viec", body)
    nonce = NonceGia()
    assert chu_ky.kiem_request(kcc, h, "POST", "/viec", body, NGAY, nonce) is None
    ly_do = chu_ky.kiem_request(kcc, h, "POST", "/viec", body, NGAY, nonce)
    assert ly_do is not None and "nonce" in ly_do


def test_kiem_request_thu_tu_lech_gio_khong_tieu_nonce(khoa, kcc) -> None:
    body = b"{}"
    h = _headers_ky(khoa, "POST", "/viec", body)
    nonce = NonceGia()
    assert chu_ky.kiem_request(kcc, h, "POST", "/viec", body, NGAY + 200_000, nonce) is not None
    assert nonce.da_dung == {}


def test_kiem_request_chu_ky_sai_khong_ghi_nonce(khoa, kcc) -> None:
    """Chữ ký sai không được tiêu nonce (chống DoS phình bảng nonce, R-04 P3-1)."""
    body = b"{}"
    h = _headers_ky(khoa, "POST", "/viec", body)
    nonce = NonceGia()
    gia = dict(h, **{"x-ky": _b64url(bytes(64))})
    ly_do = chu_ky.kiem_request(kcc, gia, "POST", "/viec", body, NGAY, nonce)
    assert ly_do is not None and "chữ ký" in ly_do
    assert nonce.da_dung == {}
    # Body/path bị sửa cũng là chữ ký sai -> không tiêu nonce.
    assert chu_ky.kiem_request(kcc, h, "POST", "/viec", b"[]", NGAY, nonce) is not None
    assert chu_ky.kiem_request(kcc, h, "POST", "/viec/x", body, NGAY, nonce) is not None
    assert nonce.da_dung == {}
    # Kẻ tấn công không "đốt" được nonce của request thật: request đúng vẫn qua, lặp lại thì bị chặn.
    assert chu_ky.kiem_request(kcc, h, "POST", "/viec", body, NGAY, nonce) is None
    assert list(nonce.da_dung) == [NONCE]
    ly_do = chu_ky.kiem_request(kcc, h, "POST", "/viec", body, NGAY, nonce)
    assert ly_do is not None and "nonce" in ly_do


def test_kiem_request_khong_dung_duoc_chuoi_ky_khong_ghi_nonce(khoa, kcc) -> None:
    body = b"{}"
    h = _headers_ky(khoa, "POST", "/viec", body)
    nonce = NonceGia()
    assert chu_ky.kiem_request(kcc, h, "POST", "/viec\nx", body, NGAY, nonce) is not None
    assert nonce.da_dung == {}


def test_kiem_request_dung_nonce_tu_choi_thi_tra_ly_do(khoa, kcc) -> None:
    """Chữ ký đúng nhưng kho nonce từ chối (đầy / lỗi ghi) -> vẫn chặn (fail-closed)."""
    body = b"{}"
    h = _headers_ky(khoa, "POST", "/viec", body)
    ly_do = chu_ky.kiem_request(kcc, h, "POST", "/viec", body, NGAY, lambda n, t: False)
    assert ly_do is not None and "nonce" in ly_do


@pytest.mark.parametrize("sua", [
    {"x-ky": None},
    {"x-ky-nonce": None},
    {"x-ky-ngay": None},
    {"x-ky-nonce": "0123456789ABCDEF0123456789ABCDEF"},
    {"x-ky-nonce": "abc"},
    {"x-ky-ngay": "12.5"},
    {"x-ky-ngay": "-1"},
    {"x-ky": "!!!"},
    {"x-ky": "AAAA"},
])
def test_kiem_request_header_hong(khoa, kcc, sua) -> None:
    body = b"{}"
    h = _headers_ky(khoa, "POST", "/viec", body)
    for k, v in sua.items():
        if v is None:
            h.pop(k)
        else:
            h[k] = v
    assert chu_ky.kiem_request(kcc, h, "POST", "/viec", body, NGAY, NonceGia()) is not None


def test_kiem_request_chu_ky_co_padding_bi_tu_choi(khoa, kcc) -> None:
    body = b"{}"
    h = _headers_ky(khoa, "POST", "/viec", body)
    h["x-ky"] = h["x-ky"] + "=="
    assert chu_ky.kiem_request(kcc, h, "POST", "/viec", body, NGAY, NonceGia()) is not None


def test_kiem_request_dung_so_sanh_hang_thoi_gian_va_ed25519_verify() -> None:
    # So sánh chữ ký giao cho Ed25519 verify (hằng thời gian trong OpenSSL);
    # module không được so chuỗi chữ ký bằng ==.
    nguon = (THU_MUC_RUNNER / "chu_ky.py").read_text(encoding="utf-8")
    assert ".verify(" in nguon


# ---------- BoNhoNonce ----------

def test_bo_nho_nonce_chan_lap_va_xoa_theo_thoi_gian() -> None:
    bn = chu_ky.BoNhoNonce(song_s=300, toi_da=10)
    assert bn("a" * 32, 1000.0) is True
    assert bn("a" * 32, 1001.0) is False
    # Hết hạn sống → đã bị xoá khỏi bộ nhớ; lúc này lệch giờ đã chặn request cũ.
    assert bn("b" * 32, 1400.0) is True
    assert len(bn) == 1
    assert bn("a" * 32, 1400.0) is True


def test_bo_nho_nonce_day_thi_tu_choi_khong_day_nonce_con_han() -> None:
    bn = chu_ky.BoNhoNonce(song_s=300, toi_da=3)
    for i in range(3):
        assert bn(f"{i:032x}", 1000.0 + i) is True
    assert bn(f"{9:032x}", 1010.0) is False  # đầy, fail-closed
    assert bn(f"{0:032x}", 1010.0) is False  # nonce cũ vẫn còn, vẫn bị chặn
    assert bn(f"{9:032x}", 1301.0) is True   # nonce 0 hết hạn → có chỗ


def test_bo_nho_nonce_song_ngan_hon_cua_so_lech_bi_tu_choi() -> None:
    with pytest.raises(ValueError):
        chu_ky.BoNhoNonce(song_s=200, toi_da=10)


# ---------- kiem_duyet ----------

def _viec_da_duyet(khoa: Ed25519PrivateKey) -> dict:
    tham_so = {"uid": "7000000000000000001", "ghi_chu": "giọng nữ"}
    viec = {
        "id": "j20261117210000ab12",
        "loai": "voice_genmax",
        "tham_so": chu_ky.json_chuan(tham_so),
        "loi_duyet": "Duyệt, làm luôn",
        "duyet_luc": "2026-11-17T21:05:00+07:00",
        "duyet_boi": "nhan",
    }
    chuoi = chu_ky.chuoi_ky_duyet(viec["id"], viec["loai"], viec["tham_so"],
                                 viec["loi_duyet"], viec["duyet_luc"], viec["duyet_boi"])
    viec["chu_ky_duyet"] = _b64url(khoa.sign(chuoi))
    return viec


def test_kiem_duyet_dung(khoa, kcc) -> None:
    assert chu_ky.kiem_duyet(kcc, _viec_da_duyet(khoa)) is True


def test_kiem_duyet_tham_so_dict_cung_duoc(khoa, kcc) -> None:
    viec = _viec_da_duyet(khoa)
    viec["tham_so"] = json.loads(viec["tham_so"])
    assert chu_ky.kiem_duyet(kcc, viec) is True


@pytest.mark.parametrize("truong,gia_tri", [
    ("tham_so", '{"ghi_chu":"giọng nữ","uid":"7000000000000000002"}'),
    ("loi_duyet", "Duyệt, làm luôn!"),
    ("loai", "taovideo"),
    ("id", "j20261117210000ab13"),
    ("duyet_luc", "2026-11-17T21:06:00+07:00"),
    ("duyet_boi", "comeofage"),
    ("chu_ky_duyet", None),
    ("loi_duyet", None),
    ("tham_so", "khong-phai-json"),
])
def test_kiem_duyet_sai_khi_bi_sua(khoa, kcc, truong, gia_tri) -> None:
    viec = _viec_da_duyet(khoa)
    viec[truong] = gia_tri
    assert chu_ky.kiem_duyet(kcc, viec) is False


def test_kiem_duyet_thieu_truong(khoa, kcc) -> None:
    viec = _viec_da_duyet(khoa)
    del viec["chu_ky_duyet"]
    assert chu_ky.kiem_duyet(kcc, viec) is False


# ---------- tiêu lời duyệt (D9: sổ trên Cloudflare) ----------

ID_TIEU = "j20261117210000ab12"
KY_DUYET = "ob8h6j5Xfe7h_Lnuj3ykdYAtLGk_Rb1VKKT-7uDzV2eUXJIMEj8-kqYvGNV6PPnH8yjXK0uMz1AunJx2dM-WDg"


def test_chuoi_tieu_duyet_dung_dinh_dang() -> None:
    mong = ("kho-tieu-v1\n" + ID_TIEU + "\n" + hashlib.sha256(KY_DUYET.encode("utf-8")).hexdigest()
            + "\n" + NONCE).encode("utf-8")
    assert chu_ky.chuoi_tieu_duyet(ID_TIEU, KY_DUYET, NONCE) == mong


def test_chuoi_tieu_duyet_bam_nguyen_van_utf8() -> None:
    """chu_ky_duyet chỉ đi vào chuỗi dưới dạng sha256 UTF-8, không chuẩn hoá."""
    a = chu_ky.chuoi_tieu_duyet(ID_TIEU, "Việt", NONCE)
    assert a.split(b"\n")[2] == hashlib.sha256("Việt".encode("utf-8")).hexdigest().encode()


@pytest.mark.parametrize("id_,ky,nonce", [
    ("j1", KY_DUYET, NONCE),                                   # id sai regex việc
    ("J20261117210000ab12", KY_DUYET, NONCE),
    ("j20261117210000AB12", KY_DUYET, NONCE),
    (ID_TIEU + "\n", KY_DUYET, NONCE),
    (ID_TIEU, KY_DUYET + "\n", NONCE),                         # xuống dòng trong chu_ky_duyet
    (ID_TIEU, "a\rb", NONCE),
    (ID_TIEU, KY_DUYET, NONCE.upper()),                        # nonce chữ hoa
    (ID_TIEU, KY_DUYET, NONCE[:-1]),
    (ID_TIEU, KY_DUYET, NONCE + "\n"),
    (ID_TIEU, None, NONCE),
    (None, KY_DUYET, NONCE),
    (ID_TIEU, KY_DUYET, None),
    (ID_TIEU, "", NONCE),                                      # chu_ky_duyet rỗng: không có gì để tiêu
])
def test_chuoi_tieu_duyet_tu_choi_truong_hong(id_, ky, nonce) -> None:
    with pytest.raises(ValueError):
        chu_ky.chuoi_tieu_duyet(id_, ky, nonce)


def _ky_tieu(khoa: Ed25519PrivateKey, id_: str = ID_TIEU, ky_duyet: str = KY_DUYET,
             nonce: str = NONCE) -> str:
    return _b64url(khoa.sign(chu_ky.chuoi_tieu_duyet(id_, ky_duyet, nonce)))


def test_kiem_tieu_dung(khoa, kcc) -> None:
    assert chu_ky.kiem_tieu(kcc, ID_TIEU, KY_DUYET, NONCE, _ky_tieu(khoa)) is True


@pytest.mark.parametrize("sua", ["id", "ky_duyet", "nonce", "khoa_khac", "padding", "rac", "ngan",
                                 "chuoi_duyet_khac"])
def test_kiem_tieu_sai_tra_false(khoa, kcc, sua) -> None:
    ky = _ky_tieu(khoa)
    id_, ky_duyet, nonce = ID_TIEU, KY_DUYET, NONCE
    if sua == "id":
        id_ = "j20261117210000ab13"
    elif sua == "ky_duyet":
        ky_duyet = KY_DUYET[:-1] + "A"
    elif sua == "nonce":
        nonce = "f" * 32
    elif sua == "khoa_khac":
        ky = _ky_tieu(Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33))))
    elif sua == "padding":
        ky = ky + "=="
    elif sua == "rac":
        ky = "!" * 86
    elif sua == "ngan":
        ky = ky[:-1]
    elif sua == "chuoi_duyet_khac":
        # chữ ký của chuỗi DUYỆT (khác tiền tố) không được dùng làm chữ ký TIÊU
        ky = _b64url(khoa.sign(chu_ky.chuoi_ky_duyet(ID_TIEU, "voice_genmax", "{}", "x", "t", "nhan")))
    assert chu_ky.kiem_tieu(kcc, id_, ky_duyet, nonce, ky) is False


@pytest.mark.parametrize("id_,ky_duyet,nonce,ky", [
    ("j1", KY_DUYET, NONCE, "A" * 86),
    (ID_TIEU, KY_DUYET + "\n", NONCE, "A" * 86),
    (ID_TIEU, KY_DUYET, "XYZ", "A" * 86),
    (None, None, None, None),
    (123, b"x", 4.5, ["k"]),
])
def test_kiem_tieu_dau_vao_hong_tra_false_khong_nem(kcc, id_, ky_duyet, nonce, ky) -> None:
    assert chu_ky.kiem_tieu(kcc, id_, ky_duyet, nonce, ky) is False


# ---------- base64url phải ở dạng CHUẨN (R-15 P1-1) ----------
# 64 byte = 512 bit → 86 ký tự × 6 bit = 516 bit: 4 bit thấp của ký tự thứ 86 là bit thừa. Bộ giải lỏng bỏ qua
# chúng → 16 chuỗi khác nhau giải ra cùng 64 byte. Chỉ dạng chuẩn (4 bit thừa = 0) được nhận.

_BANG_B64URL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def _bien_the_ky_tu_cuoi(s: str) -> list[str]:
    """15 chuỗi khác `s` chỉ ở 4 bit thừa của ký tự cuối (cùng 64 byte nếu giải lỏng)."""
    goc = _BANG_B64URL.index(s[-1]) & ~0b1111
    ds = [s[:-1] + _BANG_B64URL[goc | k] for k in range(16)]
    ds.remove(s)
    assert len(ds) == 15
    for b in ds:                         # chứng minh test có nghĩa: bộ giải lỏng coi chúng là một
        assert base64.urlsafe_b64decode(b + "==") == base64.urlsafe_b64decode(s + "==")
    return ds


def test_giai_chu_ky_chuan_tra_64_byte(khoa) -> None:
    raw = khoa.sign(b"x")
    assert chu_ky.giai_chu_ky(_b64url(raw)) == raw
    assert chu_ky._giai_chu_ky(_b64url(raw)) == raw


def test_giai_chu_ky_tu_choi_bit_thua_khac_0(khoa) -> None:
    s = _b64url(khoa.sign(b"x"))
    for b in _bien_the_ky_tu_cuoi(s):
        assert chu_ky.giai_chu_ky(b) is None, b


def test_kiem_duyet_16_bien_the_ky_tu_cuoi_chi_ban_chuan_qua(khoa, kcc) -> None:
    viec = _viec_da_duyet(khoa)
    assert chu_ky.kiem_duyet(kcc, viec) is True
    for b in _bien_the_ky_tu_cuoi(viec["chu_ky_duyet"]):
        assert chu_ky.kiem_duyet(kcc, dict(viec, chu_ky_duyet=b)) is False, b


def test_kiem_request_bien_the_x_ky_bi_tu_choi_khong_tieu_nonce(khoa, kcc) -> None:
    body = b"{}"
    h = _headers_ky(khoa, "POST", "/viec", body)
    nonce = NonceGia()
    for b in _bien_the_ky_tu_cuoi(h["x-ky"]):
        ly_do = chu_ky.kiem_request(kcc, dict(h, **{"x-ky": b}), "POST", "/viec", body, NGAY, nonce)
        assert ly_do is not None and "x-ky" in ly_do, b
    assert nonce.da_dung == {}
    assert chu_ky.kiem_request(kcc, h, "POST", "/viec", body, NGAY, nonce) is None


def test_kiem_tieu_bien_the_ky_bi_tu_choi(khoa, kcc) -> None:
    ky = _ky_tieu(khoa)
    assert chu_ky.kiem_tieu(kcc, ID_TIEU, KY_DUYET, NONCE, ky) is True
    for b in _bien_the_ky_tu_cuoi(ky):
        assert chu_ky.kiem_tieu(kcc, ID_TIEU, KY_DUYET, NONCE, b) is False, b


def test_vector_chu_ky_deu_o_dang_chuan() -> None:
    v = json.loads((THU_MUC_RUNNER / "vector_ky.json").read_text(encoding="utf-8"))
    for s in [r["x_ky"] for r in v["request"]] + [d["chu_ky_duyet"] for d in v["duyet"]] + \
             [t["ky"] for t in v["tieu"]]:
        assert chu_ky.giai_chu_ky(s) is not None, s


# ---------- nap_khoa_cong_khai ----------

def test_nap_khoa_cong_khai_tu_choi_khoa_khong_phai_ed25519() -> None:
    from cryptography.hazmat.primitives.asymmetric import ec
    pem = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with pytest.raises(ValueError):
        chu_ky.nap_khoa_cong_khai(pem)


# ---------- tao_khoa_ky.py ----------

def test_tao_khoa_ky_in_pkcs8_va_ghi_pem(tmp_path: Path) -> None:
    pem_path = tmp_path / "ky_cong_khai.pem"
    out = io.StringIO()
    with redirect_stdout(out):
        ma = tao_khoa_ky.main(["--ghi-cong-khai", str(pem_path)])
    assert ma == 0
    dong = out.getvalue().strip()
    assert "\n" not in dong
    der = base64.b64decode(dong, validate=True)
    rieng = serialization.load_der_private_key(der, password=None)
    assert isinstance(rieng, Ed25519PrivateKey)
    kcc = chu_ky.nap_khoa_cong_khai(pem_path.read_bytes())
    chuoi = chu_ky.chuoi_ky_request("POST", "/viec", NGAY, NONCE, b"{}")
    kcc.verify(rieng.sign(chuoi), chuoi)
    # Chỉ có file PEM, không có file khoá riêng hay file tạm sót lại.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ky_cong_khai.pem"]


def test_tao_khoa_ky_bat_buoc_tham_so() -> None:
    with pytest.raises(SystemExit):
        tao_khoa_ky.main([])


def _chay_help_qua_pipe(script: Path) -> subprocess.CompletedProcess:
    """--help với stdout là pipe và mã hoá mặc định cp1252 (giả lập Windows cũ)."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env["PYTHONIOENCODING"] = "cp1252"
    return subprocess.run([sys.executable, "-B", str(script), "--help"], capture_output=True,
                          env=env, timeout=60, check=False)


@pytest.mark.parametrize("ten", ["tao_khoa_ky.py", "spike_claude.py"])
def test_help_qua_pipe_cp1252_khong_vo(ten: str) -> None:
    kq = _chay_help_qua_pipe(THU_MUC_RUNNER / ten)
    assert kq.returncode == 0, kq.stderr.decode("utf-8", "replace")
    assert "usage:" in kq.stdout.decode("utf-8")


# ---------- spike_claude.py: đọc settings ----------

def test_spike_doc_settings_utf8_sig(tmp_path: Path, monkeypatch) -> None:
    p = tmp_path / "settings.json"
    p.write_bytes(b"\xef\xbb\xbf" + json.dumps({"env": {"X": "Việt"}}, ensure_ascii=False).encode("utf-8"))
    monkeypatch.setattr(spike_claude, "SETTINGS_NGUOI_DUNG", p)
    assert spike_claude._doc_settings() == {"env": {"X": "Việt"}}


def test_spike_doc_settings_thieu_file_la_rong(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(spike_claude, "SETTINGS_NGUOI_DUNG", tmp_path / "khong-co.json")
    assert spike_claude._doc_settings() == {}


@pytest.mark.parametrize("noi_dung", [b"{hong", b"[1,2]", b"\xff\xfe\x00rac"])
def test_spike_doc_settings_hong_thi_nem_loi(tmp_path: Path, monkeypatch, noi_dung: bytes) -> None:
    p = tmp_path / "settings.json"
    p.write_bytes(noi_dung)
    monkeypatch.setattr(spike_claude, "SETTINGS_NGUOI_DUNG", p)
    with pytest.raises(spike_claude.LoiDocSettings):
        spike_claude._doc_settings()


def test_spike_settings_hong_thi_dung_khong_chay_do(tmp_path: Path, monkeypatch, capsys) -> None:
    p = tmp_path / "settings.json"
    p.write_bytes(b"{hong")
    monkeypatch.setattr(spike_claude, "SETTINGS_NGUOI_DUNG", p)

    def _cam_chay(*a, **k):
        raise AssertionError("không được chạy đo khi không che được bí mật")

    monkeypatch.setattr(spike_claude, "chay_spike", _cam_chay)
    ma = spike_claude.main(["--chay", "--claude-exe", str(tmp_path / "khong-co.exe")])
    assert ma != 0
    err = capsys.readouterr().err
    assert "settings" in err and str(p) in err


# ---------- vector_ky.json ----------

def test_vector_tai_tao_duoc() -> None:
    file_vector = THU_MUC_RUNNER / "vector_ky.json"
    tren_dia = json.loads(file_vector.read_text(encoding="utf-8"))
    assert tao_khoa_ky.lap_vector_ky() == tren_dia


def test_vector_noi_dung_kiem_duoc(kcc) -> None:
    v = json.loads((THU_MUC_RUNNER / "vector_ky.json").read_text(encoding="utf-8"))
    assert v["seed_test_hex"] == SEED_TEST.hex()
    assert "TEST" in v["canh_bao"]
    kcc_v = chu_ky.nap_khoa_cong_khai(v["khoa_cong_khai_pem"].encode("ascii"))
    assert kcc_v.public_bytes_raw().hex() == v["khoa_cong_khai_raw_hex"]
    assert kcc_v.public_bytes_raw() == kcc.public_bytes_raw()
    rieng = serialization.load_der_private_key(
        base64.b64decode(v["khoa_rieng_test_pkcs8_der_b64"]), password=None)
    assert rieng.public_key().public_bytes_raw() == kcc.public_bytes_raw()

    assert len(v["request"]) == 2
    for r in v["request"]:
        body = r["body_utf8"].encode("utf-8")
        chuoi = chu_ky.chuoi_ky_request(r["method"], r["path"], r["ngay_ms"], r["nonce"], body)
        assert chuoi.hex() == r["chuoi_ky_hex"]
        assert chuoi.decode("utf-8") == r["chuoi_ky_utf8"]
        assert hashlib.sha256(body).hexdigest() == r["body_sha256_hex"]
        h = {"x-ky-ngay": str(r["ngay_ms"]), "x-ky-nonce": r["nonce"], "x-ky": r["x_ky"]}
        assert chu_ky.kiem_request(kcc_v, h, r["method"], r["path"], body,
                                   r["ngay_ms"], NonceGia()) is None
    assert any(any(ord(c) > 127 for c in r["body_utf8"]) for r in v["request"])

    assert len(v["duyet"]) == 1
    d = v["duyet"][0]
    assert any(ord(c) > 127 for c in d["loi_duyet"])
    assert chu_ky.json_chuan(d["tham_so"]) == d["tham_so_chuan"]
    chuoi = chu_ky.chuoi_ky_duyet(d["id"], d["loai"], d["tham_so_chuan"], d["loi_duyet"],
                                 d["duyet_luc"], d["boi"])
    assert chuoi.hex() == d["chuoi_ky_hex"]
    viec = {"id": d["id"], "loai": d["loai"], "tham_so": d["tham_so_chuan"],
            "loi_duyet": d["loi_duyet"], "duyet_luc": d["duyet_luc"], "duyet_boi": d["boi"],
            "chu_ky_duyet": d["chu_ky_duyet"]}
    assert chu_ky.kiem_duyet(kcc_v, viec) is True


def test_vector_tieu_kiem_duoc(kcc) -> None:
    v = json.loads((THU_MUC_RUNNER / "vector_ky.json").read_text(encoding="utf-8"))
    kcc_v = chu_ky.nap_khoa_cong_khai(v["khoa_cong_khai_pem"].encode("ascii"))
    assert len(v["tieu"]) >= 2
    # mục đầu tiêu đúng chữ ký duyệt của vector duyet[0] (luồng thật: duyệt rồi tiêu)
    assert v["tieu"][0]["id"] == v["duyet"][0]["id"]
    assert v["tieu"][0]["chu_ky_duyet"] == v["duyet"][0]["chu_ky_duyet"]
    assert len({t["nonce"] for t in v["tieu"]}) == len(v["tieu"])
    for t in v["tieu"]:
        chuoi = chu_ky.chuoi_tieu_duyet(t["id"], t["chu_ky_duyet"], t["nonce"])
        assert chuoi.hex() == t["chuoi_tieu_hex"]
        assert chuoi.decode("utf-8") == t["chuoi_tieu_utf8"]
        assert hashlib.sha256(t["chu_ky_duyet"].encode("utf-8")).hexdigest() == t["chu_ky_duyet_sha256_hex"]
        assert chuoi.decode("utf-8").startswith("kho-tieu-v1\n")
        assert len(t["ky"]) == 86 and "=" not in t["ky"]
        assert chu_ky.kiem_tieu(kcc_v, t["id"], t["chu_ky_duyet"], t["nonce"], t["ky"]) is True
        # tiêu lại cùng chu_ky_duyet với nonce khác: chữ ký cũ không dùng được
        assert chu_ky.kiem_tieu(kcc_v, t["id"], t["chu_ky_duyet"], "0" * 32, t["ky"]) is False


def test_vector_muc_cu_khong_doi() -> None:
    """Thêm mục tieu[] không được đổi byte nào của các mục cũ (Worker đã test chéo theo chúng)."""
    v = json.loads((THU_MUC_RUNNER / "vector_ky.json").read_text(encoding="utf-8"))
    assert v["phien_ban"] == 1
    assert v["request"][0]["x_ky"] == ("MMRGwbrfFcbUI0Ay0Sty97gVHfvex7vkAugyCSqGGjYh2G6afJrAkDboeH6a3Lqs1zYsE-eXeP_"
                                       "qiQjCVZ6KDQ")
    assert v["request"][1]["x_ky"] == ("iwcidd4SE2upQ0l5jTEE5sDWffYOwRQSGr2nqjd8Zf3tYxKGg1Igf2OKysJvcPWg4qdwemmbl_"
                                       "pnLeHS7lyADA")
    assert v["duyet"][0]["chu_ky_duyet"] == KY_DUYET
    assert set(v["dinh_dang"]) == {"chuoi_ky_request", "chuoi_ky_duyet", "ma_hoa", "path", "nonce", "chu_ky",
                                   "tham_so_chuan", "headers"}
