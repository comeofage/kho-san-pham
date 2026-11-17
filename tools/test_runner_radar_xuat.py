"""Test B-1b: tools/runner/radar_xuat.py (xuất dữ liệu radar từ SQLite chỉ đọc ra JSON).

Chỉ dùng DB SQLite giả trong tmp_path, tên bảng/cột sao y DB thật
(E:/quet-kenh-anti/tiktok_7ngay.db). KHÔNG mở DB thật trong test.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

_DUONG_MODULE = Path(__file__).parent / "runner" / "radar_xuat.py"


def _nap_module():
    # Nạp thẳng từ file: không phụ thuộc tools/runner/__init__.py (người khác viết).
    spec = importlib.util.spec_from_file_location("radar_xuat_test", _DUONG_MODULE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rx = _nap_module()

# Schema sao y DB thật (PRAGMA/sqlite_master đọc chỉ-đọc ngày 2026-11-17).
_SCHEMA = """
CREATE TABLE breakout_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date TEXT, video_id TEXT, handle TEXT, view_count INTEGER,
    median_view INTEGER, ratio_x REAL, delta_24h INTEGER DEFAULT 0,
    published_at TIMESTAMP, title TEXT, url TEXT, embed TEXT, created_at TIMESTAMP,
    product_name TEXT, has_shop INTEGER DEFAULT 1, follower_count INTEGER DEFAULT 0,
    velocity_h REAL, delta_hours REAL, shop_source TEXT, loai TEXT, view_gio REAL,
    UNIQUE (video_id, scan_date)
);
CREATE TABLE scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date TEXT, started_at INTEGER, ended_at INTEGER, channels_total INTEGER,
    channels_ok INTEGER, channels_fail INTEGER, alerts_raw INTEGER, alerts_shop INTEGER,
    status TEXT, note TEXT
);
"""


def _them_run(con, ngay, status, ok=900, total=960, shop=3, ended=1794885480):
    con.execute(
        "INSERT INTO scan_runs (scan_date, started_at, ended_at, channels_total, channels_ok,"
        " channels_fail, alerts_raw, alerts_shop, status, note) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (ngay, 1794879028, ended, total, ok, total - ok if ok is not None else None, 10, shop,
         status, None),
    )


def _them_alert(con, ngay, vid, has_shop=1, view=1000, product="Kẹp tóc", handle="kenh_a"):
    con.execute(
        "INSERT INTO breakout_alerts (scan_date, video_id, handle, view_count, median_view,"
        " ratio_x, delta_24h, published_at, title, url, embed, created_at, product_name,"
        " has_shop, follower_count, velocity_h, delta_hours, shop_source, loai, view_gio)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ngay, vid, handle, view, 100, view / 100, 500, "2026-11-16 10:00:00",
         f"Tiêu đề {vid} #xuhuong", f"https://www.tiktok.com/@{handle}/video/{vid}",
         "<embed>", "2026-11-17 08:00:00", product, has_shop, 1234, 12.5, 24.0,
         "html", "tang_toc", 41.6),
    )


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    duong = tmp_path / "tiktok_7ngay.db"
    with sqlite3.connect(duong) as con:
        con.executescript(_SCHEMA)
        _them_run(con, "2026-11-14", "ok", shop=1)
        _them_alert(con, "2026-11-14", "111", view=5000)
        _them_run(con, "2026-11-15", "ok", ok=897, shop=2)
        _them_alert(con, "2026-11-15", "221", view=3000)
        _them_alert(con, "2026-11-15", "222", view=9000, product=None)
        _them_alert(con, "2026-11-15", "223", has_shop=0)
        # Ngày mới nhất nhưng đang chạy dở: không được chọn làm "ok mới nhất".
        _them_run(con, "2026-11-16", "running", ok=None, shop=None, ended=None)
        _them_alert(con, "2026-11-16", "331")
    con.close()
    return duong


def test_chon_luot_ok_moi_nhat_bo_qua_running(db: Path, tmp_path: Path) -> None:
    ra = tmp_path / "radar" / "job1.json"
    kq = rx.xuat(db, None, ra)
    assert kq["scan_date"] == "2026-11-15"
    assert kq["status"] == "ok"
    assert kq["channels_ok"] == 897
    assert kq["channels_total"] == 960
    assert kq["alerts_shop"] == 2
    assert kq["so_dong"] == 2
    assert set(kq) == {"scan_date", "status", "channels_ok", "channels_total",
                       "alerts_shop", "so_dong", "bao_cao_md"}


def test_json_chi_co_has_shop_1_dung_ngay_dung_cot(db: Path, tmp_path: Path) -> None:
    ra = tmp_path / "radar" / "job1.json"
    rx.xuat(db, None, ra)
    du_lieu = json.loads(ra.read_text(encoding="utf-8"))
    assert du_lieu["scan_date"] == "2026-11-15"
    alerts = du_lieu["alerts"]
    assert [a["url"].rsplit("/", 1)[1] for a in alerts] == ["222", "221"]  # view giảm dần
    cot = {"handle", "view_count", "median_view", "ratio_x", "delta_24h", "velocity_h",
           "published_at", "title", "url", "product_name", "has_shop", "follower_count",
           "loai"}
    for a in alerts:
        assert cot <= set(a)
        assert a["has_shop"] == 1
        assert a["scan_date"] == "2026-11-15"
    assert alerts[1]["product_name"] == "Kẹp tóc"
    assert alerts[0]["product_name"] is None
    # scan_runs của đúng ngày đó
    assert [r["scan_date"] for r in du_lieu["scan_runs"]] == ["2026-11-15"]
    assert du_lieu["scan_runs"][0]["status"] == "ok"
    # UTF-8 thật, không escape \uXXXX
    assert "Kẹp tóc" in ra.read_text(encoding="utf-8")


def test_ngay_chi_dinh_khong_ok_van_xuat_va_bao_dung_status(db: Path, tmp_path: Path) -> None:
    ra = tmp_path / "ra.json"
    kq = rx.xuat(db, "2026-11-16", ra)
    assert kq["scan_date"] == "2026-11-16"
    assert kq["status"] == "running"
    assert kq["channels_ok"] is None
    assert kq["so_dong"] == 1


def test_ngay_khong_co_scan_runs(db: Path, tmp_path: Path) -> None:
    kq = rx.xuat(db, "2026-01-01", tmp_path / "ra.json")
    assert kq["scan_date"] == "2026-01-01"
    assert kq["status"] is None
    assert kq["so_dong"] == 0


def test_nhieu_luot_cung_ngay_uu_tien_ok_moi_nhat(db: Path, tmp_path: Path) -> None:
    with sqlite3.connect(db) as con:
        _them_run(con, "2026-11-15", "partial", ok=500, shop=7)
        _them_run(con, "2026-11-14", "ok", ok=950, shop=9)
        _them_run(con, "2026-11-16", "partial", ok=10, shop=1)
    con.close()
    kq = rx.xuat(db, "2026-11-15", tmp_path / "ra.json")
    assert (kq["status"], kq["channels_ok"]) == ("ok", 897)  # ok của ngày thắng partial sau đó
    kq = rx.xuat(db, "2026-11-14", tmp_path / "ra.json")
    assert (kq["status"], kq["channels_ok"], kq["alerts_shop"]) == ("ok", 950, 9)
    kq = rx.xuat(db, "2026-11-16", tmp_path / "ra.json")  # không có ok: lượt mới nhất
    assert (kq["status"], kq["channels_ok"]) == ("partial", 10)
    du_lieu = json.loads((tmp_path / "ra.json").read_text(encoding="utf-8"))
    assert [r["status"] for r in du_lieu["scan_runs"]] == ["running", "partial"]
    # Không chỉ định ngày: chọn theo NGÀY dữ liệu mới nhất có ok, không theo id.
    assert rx.xuat(db, None, tmp_path / "ra2.json")["scan_date"] == "2026-11-15"


def test_bao_cao_md_dung_ngay_khong_lay_file_cu(db: Path, tmp_path: Path) -> None:
    thu_muc = tmp_path / "data_dot_bien_7ngay"
    thu_muc.mkdir()
    cu = thu_muc / "Bao-Cao-Dot-Bien-7-Ngay-2026-11-14.md"
    cu.write_text("cũ", encoding="utf-8")
    kq = rx.xuat(db, None, tmp_path / "ra.json")
    assert kq["bao_cao_md"] is None  # 11-15 chưa có báo cáo; không được trả file 11-14
    dung = thu_muc / "Bao-Cao-Dot-Bien-7-Ngay-2026-11-15.md"
    dung.write_text("mới", encoding="utf-8")
    kq = rx.xuat(db, None, tmp_path / "ra.json")
    assert Path(kq["bao_cao_md"]) == dung


def test_thu_muc_bao_cao_mac_dinh_canh_db() -> None:
    p = rx.duong_bao_cao(Path("E:/quet-kenh-anti/tiktok_7ngay.db"), "2026-11-15")
    assert p == Path("E:/quet-kenh-anti/data_dot_bien_7ngay/Bao-Cao-Dot-Bien-7-Ngay-2026-11-15.md")


def test_khong_co_luot_ok_nao_thi_bao_loi_va_khong_de_file_cu(tmp_path: Path) -> None:
    duong = tmp_path / "rong.db"
    with sqlite3.connect(duong) as con:
        con.executescript(_SCHEMA)
        _them_run(con, "2026-11-16", "running", ok=None, ended=None)
    con.close()
    ra = tmp_path / "ra.json"
    ra.write_text('{"scan_date": "2026-11-01"}', encoding="utf-8")  # file cũ từ lần trước
    with pytest.raises(rx.KhongCoLuotOk):
        rx.xuat(duong, None, ra)
    assert not ra.exists()


def test_ngay_sai_dinh_dang(db: Path, tmp_path: Path) -> None:
    for sai in ("2026-1-5", "2026-11-15; DROP TABLE x", "../x", "2026-13-01"):
        with pytest.raises(ValueError):
            rx.xuat(db, sai, tmp_path / "ra.json")


def test_mo_db_chi_doc_khong_tao_db_moi(tmp_path: Path) -> None:
    khong_co = tmp_path / "khong_co.db"
    with pytest.raises(sqlite3.OperationalError):
        rx.xuat(khong_co, None, tmp_path / "ra.json")
    assert not khong_co.exists()


def test_db_khong_bi_ghi(db: Path, tmp_path: Path) -> None:
    truoc = db.read_bytes()
    rx.xuat(db, None, tmp_path / "ra.json")
    assert db.read_bytes() == truoc


def test_ghi_de_file_ra_cu(db: Path, tmp_path: Path) -> None:
    ra = tmp_path / "ra.json"
    ra.write_text('{"scan_date": "2026-11-01"}', encoding="utf-8")
    rx.xuat(db, "2026-11-14", ra)
    assert json.loads(ra.read_text(encoding="utf-8"))["scan_date"] == "2026-11-14"
    assert not list(tmp_path.glob("*.tmp"))


def test_cli(db: Path, tmp_path: Path) -> None:
    ra = tmp_path / "radar" / "cli.json"
    p = subprocess.run(
        [sys.executable, "-B", str(_DUONG_MODULE), "--db", str(db), "--ngay", "", "--ra", str(ra)],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert p.returncode == 0, p.stderr
    tom_tat = json.loads(p.stdout)
    assert tom_tat["scan_date"] == "2026-11-15"
    assert json.loads(ra.read_text(encoding="utf-8"))["so_dong"] == 2


def test_cli_loi_tra_ma_khac_0(tmp_path: Path) -> None:
    p = subprocess.run(
        [sys.executable, "-B", str(_DUONG_MODULE), "--db", str(tmp_path / "khong.db"),
         "--ra", str(tmp_path / "ra.json")],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert p.returncode != 0
    assert "[LỖI]" in p.stderr
    assert not (tmp_path / "ra.json").exists()


def test_cli_mac_dinh_db_that() -> None:
    # Chỉ kiểm hằng số, KHÔNG mở DB thật.
    assert rx.DB_MAC_DINH == Path("E:/quet-kenh-anti/tiktok_7ngay.db")
