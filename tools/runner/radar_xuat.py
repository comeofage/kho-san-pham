"""Xuất dữ liệu Breakout Radar từ SQLite (CHỈ ĐỌC) ra JSON cho agent aff-radar (không cần Bash).

Hợp đồng: docs/bo-chay-viec.md §5.1 (radar_ban_tin, bước 2) và §13 mục B-1b.

    python radar_xuat.py --ngay <YYYY-MM-DD hoặc rỗng> --ra <data>/radar/<id>.json [--db ...]

- Mở DB bằng URI `file:...?mode=ro` (không bao giờ ghi, không tạo DB mới).
- `scan_date` = `--ngay` nếu có, ngược lại là NGÀY dữ liệu mới nhất có lượt `ok`.
- Trong một ngày có nhiều lượt: ưu tiên lượt `ok` mới nhất (id lớn nhất), không có `ok` thì lượt mới nhất.
- JSON gồm tóm tắt + mọi dòng `scan_runs` của ngày + `breakout_alerts` có `has_shop=1` của ngày.
- File `--ra` cũ bị xoá TRƯỚC khi làm, để lần xuất lỗi không để lại dữ liệu ngày cũ bị nhận nhầm.

Module chạy độc lập, chỉ dùng thư viện chuẩn (không import package runner).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

log = logging.getLogger("radar_xuat")

DB_MAC_DINH = Path("E:/quet-kenh-anti/tiktok_7ngay.db")
THU_MUC_BAO_CAO = "data_dot_bien_7ngay"
MAU_BAO_CAO = "Bao-Cao-Dot-Bien-7-Ngay-{ngay}.md"

# Cột breakout_alerts theo aff-radar.md:17, cộng scan_date để đối chiếu ngày.
COT_ALERT: tuple[str, ...] = (
    "scan_date", "handle", "view_count", "median_view", "ratio_x", "delta_24h", "velocity_h",
    "published_at", "title", "url", "product_name", "has_shop", "follower_count", "loai",
)
COT_SCAN_RUN: tuple[str, ...] = (
    "id", "scan_date", "started_at", "ended_at", "channels_total", "channels_ok",
    "channels_fail", "alerts_raw", "alerts_shop", "status", "note",
)

_MAU_NGAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SO_LAN_THU_GHI = 5


class KhongCoLuotOk(LookupError):
    """DB không có lượt quét `ok` nào khi không chỉ định `--ngay`."""


def kiem_ngay(ngay: str) -> str:
    """Trả lại `ngay` nếu đúng YYYY-MM-DD và là ngày có thật; ném ValueError nếu không."""
    if not _MAU_NGAY.match(ngay):
        raise ValueError(f"Ngày sai định dạng YYYY-MM-DD: {ngay!r}")
    date.fromisoformat(ngay)  # ném ValueError nếu tháng/ngày không tồn tại
    return ngay


def duong_bao_cao(db: Path, ngay: str) -> Path:
    """Báo cáo ngày nằm cạnh DB: <thư mục DB>/data_dot_bien_7ngay/Bao-Cao-...-<ngay>.md."""
    return db.parent / THU_MUC_BAO_CAO / MAU_BAO_CAO.format(ngay=kiem_ngay(ngay))


def _mo_chi_doc(db: Path) -> sqlite3.Connection:
    uri = Path(db).resolve().as_uri() + "?mode=ro"
    # DB thật dùng journal_mode=delete: lúc script quét đang ghi, reader phải chờ khoá.
    con = sqlite3.connect(uri, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def _chon_ngay_ok_moi_nhat(con: sqlite3.Connection) -> str:
    dong = con.execute(
        "SELECT scan_date FROM scan_runs WHERE status = ? AND scan_date IS NOT NULL"
        " ORDER BY scan_date DESC, id DESC LIMIT 1",
        ("ok",),
    ).fetchone()
    if dong is None:
        raise KhongCoLuotOk("Không có lượt quét 'ok' nào trong scan_runs")
    return str(dong["scan_date"])


def _doc_scan_runs(con: sqlite3.Connection, ngay: str) -> list[dict[str, Any]]:
    cot = ", ".join(COT_SCAN_RUN)  # hằng số trong code, không từ người dùng
    rows = con.execute(
        f"SELECT {cot} FROM scan_runs WHERE scan_date = ? ORDER BY id", (ngay,)
    ).fetchall()
    return [dict(r) for r in rows]


def _chon_luot(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    ok = [r for r in runs if r["status"] == "ok"]
    ung_vien = ok or runs
    return max(ung_vien, key=lambda r: r["id"]) if ung_vien else None


def _doc_alerts(con: sqlite3.Connection, ngay: str) -> list[dict[str, Any]]:
    cot = ", ".join(COT_ALERT)
    rows = con.execute(
        f"SELECT {cot} FROM breakout_alerts WHERE scan_date = ? AND has_shop = 1"
        " ORDER BY view_count DESC, id",
        (ngay,),
    ).fetchall()
    return [dict(r) for r in rows]


def _ghi_nguyen_tu(ra: Path, noi_dung: str) -> None:
    ra.parent.mkdir(parents=True, exist_ok=True)
    tam = ra.with_name(f"{ra.name}.{os.getpid()}.tmp")
    try:
        tam.write_text(noi_dung, encoding="utf-8")
        for lan in range(_SO_LAN_THU_GHI):
            try:
                os.replace(tam, ra)
                return
            except PermissionError as e:  # NTFS bị Indexer/Antivirus khoá tạm
                if lan == _SO_LAN_THU_GHI - 1:
                    raise OSError(f"Không thay được {ra} sau {_SO_LAN_THU_GHI} lần") from e
                log.warning("os.replace %s bị khoá (lần %d): %s", ra, lan + 1, e)
                time.sleep(0.1 * 2 ** lan)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tam.unlink()


def _xoa_file_cu(ra: Path) -> None:
    with contextlib.suppress(FileNotFoundError):
        ra.unlink()


def xuat(db: Path, ngay: str | None, ra: Path) -> dict[str, Any]:
    """Xuất radar của `ngay` (hoặc ngày ok mới nhất) ra `ra`; trả bản tóm tắt.

    Trả `{scan_date, status, channels_ok, channels_total, alerts_shop, so_dong, bao_cao_md}`.
    `status`/`channels_*`/`alerts_shop` là None khi ngày đó không có dòng scan_runs.
    Ném ValueError (ngày sai), KhongCoLuotOk, sqlite3.Error (DB không mở/đọc được), OSError.
    """
    db = Path(db)
    ra = Path(ra)
    ngay = ngay or None
    _xoa_file_cu(ra)  # trước mọi kiểm tra: lỗi ở đâu cũng không để lại file ngày cũ
    if ngay is not None:
        kiem_ngay(ngay)

    with contextlib.closing(_mo_chi_doc(db)) as con:
        scan_date = ngay if ngay is not None else _chon_ngay_ok_moi_nhat(con)
        runs = _doc_scan_runs(con, scan_date)
        alerts = _doc_alerts(con, scan_date)

    luot = _chon_luot(runs)
    bao_cao = duong_bao_cao(db, scan_date)
    tom_tat: dict[str, Any] = {
        "scan_date": scan_date,
        "status": luot["status"] if luot else None,
        "channels_ok": luot["channels_ok"] if luot else None,
        "channels_total": luot["channels_total"] if luot else None,
        "alerts_shop": luot["alerts_shop"] if luot else None,
        "so_dong": len(alerts),
        "bao_cao_md": str(bao_cao) if bao_cao.is_file() else None,
    }
    du_lieu = {**tom_tat, "db": str(db), "scan_runs": runs, "alerts": alerts}
    _ghi_nguyen_tu(ra, json.dumps(du_lieu, ensure_ascii=False, indent=1))
    return tom_tat


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Xuất dữ liệu Breakout Radar (chỉ đọc) ra JSON")
    ap.add_argument("--db", type=Path, default=DB_MAC_DINH)
    ap.add_argument("--ngay", default="", help="YYYY-MM-DD; rỗng = ngày ok mới nhất")
    ap.add_argument("--ra", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        tom_tat = xuat(args.db, args.ngay or None, args.ra)
    except (ValueError, LookupError, sqlite3.Error, OSError) as e:
        log.exception("Xuất radar thất bại (db=%s, ngay=%r, ra=%s)", args.db, args.ngay, args.ra)
        print(f"[LỖI] {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(json.dumps(tom_tat, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
