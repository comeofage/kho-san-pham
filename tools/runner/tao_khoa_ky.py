"""Sinh cặp khoá Ed25519 cho chữ ký Worker (D7, docs/bo-chay-viec.md §8.3).

Dùng thật (trưởng phòng chạy MỘT lần, khoá riêng đi thẳng qua pipe, không ghi đĩa)::

    python tools/runner/tao_khoa_ky.py --ghi-cong-khai tools/runner/ky_cong_khai.pem \
        | npx wrangler secret put KY_RIENG

- stdout: khoá riêng dạng PKCS8 DER base64 (chuẩn, có padding), một dòng.
- ``--ghi-cong-khai``: ghi khoá công khai PEM (SubjectPublicKeyInfo) nguyên tử.

Sinh lại vector test chéo (khoá TEST từ seed cố định, không bao giờ dùng thật)::

    python -B tools/runner/tao_khoa_ky.py --ghi-vector tools/runner/vector_ky.json
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chu_ky  # noqa: E402

# KHOÁ TEST: seed công khai, chỉ dùng sinh vector_ky.json. KHÔNG dùng cho KY_RIENG.
SEED_TEST = bytes(range(32))


def _ghi_nguyen_tu(dich: Path, du_lieu: bytes, so_lan: int = 5) -> None:
    """Ghi file tạm cùng thư mục rồi os.replace; retry backoff khi NTFS khoá file."""
    dich = Path(dich)
    dich.parent.mkdir(parents=True, exist_ok=True)
    fd, tam = tempfile.mkstemp(prefix=dich.name + ".", suffix=".tmp", dir=dich.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(du_lieu)
            f.flush()
            os.fsync(f.fileno())
        cho = 0.05
        for lan in range(so_lan):
            try:
                os.replace(tam, dich)
                return
            except PermissionError:
                if lan == so_lan - 1:
                    raise
                time.sleep(cho)
                cho *= 2
    finally:
        if os.path.exists(tam):
            os.remove(tam)


def _pkcs8_der(khoa: Ed25519PrivateKey) -> bytes:
    return khoa.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _pem_cong_khai(khoa: Ed25519PrivateKey) -> bytes:
    return khoa.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def lap_vector_ky() -> dict:
    """Dựng nội dung vector_ky.json (tất định: Ed25519 ký tất định, seed cố định)."""
    khoa = Ed25519PrivateKey.from_private_bytes(SEED_TEST)

    mau_request = [
        {
            "method": "POST",
            "path": "/viec",
            "ngay_ms": 1763380800000,
            "nonce": "00112233445566778899aabbccddeeff",
            "body_utf8": chu_ky.json_chuan({
                "boi": "nhan",
                "loai": "phan_tich_uid",
                "tham_so": {"ghi_chu": "Kênh bán đồ gia dụng – thử", "uid": "7000000000000000001"},
            }),
        },
        {
            "method": "POST",
            "path": "/viec/j20261117210000ab12/tra-loi",
            "ngay_ms": 1763380865432,
            "nonce": "fedcba9876543210fedcba9876543210",
            "body_utf8": '{"tra_loi":"da_lam_xong","boi":"comeofage"}',
        },
    ]
    request = []
    for m in mau_request:
        body = m["body_utf8"].encode("utf-8")
        chuoi = chu_ky.chuoi_ky_request(m["method"], m["path"], m["ngay_ms"], m["nonce"], body)
        request.append({
            **m,
            "body_sha256_hex": hashlib.sha256(body).hexdigest(),
            "chuoi_ky_utf8": chuoi.decode("utf-8"),
            "chuoi_ky_hex": chuoi.hex(),
            "x_ky": _b64url(khoa.sign(chuoi)),
        })

    tham_so = {"uid": "7000000000000000001", "giong": "Uyên Đan", "so_video": 20}
    tham_so_chuan = chu_ky.json_chuan(tham_so)
    d = {
        "id": "j20261117210000ab12",
        "loai": "voice_genmax",
        "tham_so": tham_so,
        "tham_so_chuan": tham_so_chuan,
        "loi_duyet": "Duyệt, làm luôn — tối đa 20 video",
        "duyet_luc": "2026-11-17T21:05:00+07:00",
        "boi": "nhan",
    }
    chuoi_d = chu_ky.chuoi_ky_duyet(d["id"], d["loai"], tham_so_chuan, d["loi_duyet"],
                                    d["duyet_luc"], d["boi"])
    d.update({
        "tham_so_chuan_sha256_hex": hashlib.sha256(tham_so_chuan.encode("utf-8")).hexdigest(),
        "loi_duyet_sha256_hex": hashlib.sha256(d["loi_duyet"].encode("utf-8")).hexdigest(),
        "chuoi_ky_utf8": chuoi_d.decode("utf-8"),
        "chuoi_ky_hex": chuoi_d.hex(),
        "chu_ky_duyet": _b64url(khoa.sign(chuoi_d)),
    })

    return {
        "canh_bao": "KHOÁ TEST — seed công khai, CHỈ dùng cho test chéo. "
                    "KHÔNG BAO GIỜ dùng làm KY_RIENG hay ky_cong_khai.pem thật.",
        "phien_ban": 1,
        "dinh_dang": {
            "chuoi_ky_request": "kho-runner-v1\\nMETHOD\\nPATH\\nNGAY_MS\\nNONCE\\nsha256_hex(BODY)",
            "chuoi_ky_duyet": "kho-duyet-v1\\nID\\nLOAI\\nsha256_hex(THAM_SO_CHUAN)"
                              "\\nsha256_hex(LOI_DUYET)\\nDUYET_LUC\\nBOI",
            "ma_hoa": "UTF-8; sha256_hex chữ thường; không xuống dòng cuối",
            "path": "không tiền tố /r, không query",
            "nonce": "32 hex chữ thường",
            "chu_ky": "Ed25519, base64url KHÔNG padding (86 ký tự)",
            "tham_so_chuan": "json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=False)",
            "headers": "x-ky-ngay, x-ky-nonce, x-ky",
        },
        "seed_test_hex": SEED_TEST.hex(),
        "khoa_rieng_test_pkcs8_der_b64": base64.b64encode(_pkcs8_der(khoa)).decode("ascii"),
        "khoa_cong_khai_pem": _pem_cong_khai(khoa).decode("ascii"),
        "khoa_cong_khai_raw_hex": khoa.public_key().public_bytes_raw().hex(),
        "request": request,
        "duyet": [d],
    }


def _stdio_utf8() -> None:
    """stdout/stderr UTF-8 TRƯỚC parse_args: --help tiếng Việt qua pipe cp1252 không vỡ."""
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass  # luồng không phải TextIOWrapper (vd. StringIO trong test) -> để nguyên


def main(argv: list[str] | None = None) -> int:
    _stdio_utf8()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    nhom = ap.add_mutually_exclusive_group(required=True)
    nhom.add_argument("--ghi-cong-khai", type=Path, metavar="PEM",
                      help="sinh cặp khoá THẬT; ghi khoá công khai PEM, in khoá riêng ra stdout")
    nhom.add_argument("--ghi-vector", type=Path, metavar="JSON",
                      help="ghi vector test chéo từ khoá TEST")
    ns = ap.parse_args(argv)

    if ns.ghi_vector is not None:
        noi_dung = json.dumps(lap_vector_ky(), ensure_ascii=False, indent=2) + "\n"
        _ghi_nguyen_tu(ns.ghi_vector, noi_dung.encode("utf-8"))
        return 0

    khoa = Ed25519PrivateKey.generate()
    _ghi_nguyen_tu(ns.ghi_cong_khai, _pem_cong_khai(khoa))
    sys.stdout.write(base64.b64encode(_pkcs8_der(khoa)).decode("ascii") + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
