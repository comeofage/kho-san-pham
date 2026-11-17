"""In danh sách folder Poster V2 dạng JSON [{"id": int, "ten": str}] (docs/bo-chay-viec.md §5.2, §13 A-3).

Chạy bằng python của venv Poster V2 (vòng chạy gọi qua `MoiTruong.doc_folder_poster`):
    E:/tool/tiktok_poster_v2/.venv/Scripts/python.exe -B -I poster_ds_folder.py --poster E:/tool/tiktok_poster_v2

- CHỈ gọi `ApiClient().list_folders()` (GET /api/v2/folders/, chỉ đọc). Không gọi API ghi nào, không ghi file nào.
- ApiClient tự đọc bearer token từ `.env` của app; script không in token/header.
- Thành công: một dòng JSON (ASCII, an toàn mọi code page) ra stdout, mã 0.
- Lỗi: thông điệp ra stderr, mã ≠ 0 (2 = không nạp được ApiClient/đầu vào; 3 = gọi API lỗi; 4 = dữ liệu lạ).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TEN_TOI_DA = 120
LOI_TOI_DA = 300


def chuan_hoa(ds: object) -> list[dict]:
    """Danh sách folder thô của Poster → [{id:int, ten:str}]. Mục hỏng (id không phải số nguyên dương) bị bỏ."""
    if not isinstance(ds, list):
        raise ValueError(f"list_folders trả {type(ds).__name__}, cần list")
    ra: list[dict] = []
    for f in ds:
        if not isinstance(f, dict):
            continue
        fid = f.get("id")
        if isinstance(fid, str) and fid.isascii() and fid.isdigit() and len(fid) <= 9:
            fid = int(fid)
        if isinstance(fid, bool) or not isinstance(fid, int) or not 0 < fid < 10 ** 9:
            continue
        ten = f.get("name")
        ra.append({"id": fid, "ten": ten[:TEN_TOI_DA] if isinstance(ten, str) else ""})
    return ra


def _cat(s: str) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= LOI_TOI_DA else s[:LOI_TOI_DA] + "…"


def main(argv: list[str] | None = None) -> int:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="In danh sách folder Poster V2 (chỉ đọc)")
    ap.add_argument("--poster", required=True, help="thư mục gốc Poster V2 (có src/desktop/api_client.py)")
    a = ap.parse_args(argv)
    poster = Path(a.poster)
    if not (poster / "src" / "desktop" / "api_client.py").is_file():
        print(f"[LỖI] không thấy {(poster / 'src' / 'desktop' / 'api_client.py').as_posix()}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(poster))           # api_client dùng relative import → nạp như package src.desktop
    try:
        from src.desktop.api_client import ApiClient
    except Exception as e:  # noqa: BLE001 — venv thiếu gói, mã Poster lỗi… → báo rõ, không traceback dài
        print(f"[LỖI] không nạp được ApiClient: {type(e).__name__}: {_cat(e)}", file=sys.stderr)
        return 2
    try:
        tho = ApiClient().list_folders()
    except Exception as e:  # noqa: BLE001 — Poster tắt, 401, quá giờ…
        print(f"[LỖI] không đọc được danh sách folder Poster: {type(e).__name__}: {_cat(e)}", file=sys.stderr)
        return 3
    try:
        ra = chuan_hoa(tho)
    except ValueError as e:
        print(f"[LỖI] {e}", file=sys.stderr)
        return 4
    sys.stdout.write(json.dumps(ra, ensure_ascii=True) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
