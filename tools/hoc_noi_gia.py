"""Harness cho test nối dây xuyên chặng "Học tự động mỗi ngày" (HT-T1, docs/hoc-tu-dong.md §8.4, §8.1, §3.10).

Chạy: python -B tools/hoc_noi_gia.py   (cf/test/hoc-noi-day.test.mjs tự spawn, cwd = gốc repo)

- Đặt KHO_HOC_TEST=1 (và KHO_POSTER_TEST=1, KHO_POSTER_WEB=0, KHO_VIDEO_PORT=0) TRƯỚC khi import mã thật; import
  `runner.*` đúng một kiểu (gói `runner`, §3.10) nên trong tiến trình chỉ có MỘT bản `runner.kho_hoc`.
- Mọi dữ liệu trong một thư mục tạm (tempfile.mkdtemp): hoc.db, runner.db (KhoViec), DB Poster giả, repo giả.
  Tự kiểm `quet_view.kiem_duong_dan_thu` trên thư mục tạm trước khi tạo gì. Không đụng E:\\kho-runner, v2_data.db thật,
  view-poster; không gọi mạng ngoài, không yt-dlp.
- Sinh cặp khoá Ed25519 test (khoá công khai → runner, khoá riêng PKCS8 DER base64 → Worker KY_RIENG), khoá runner
  và khoá video ngẫu nhiên.
- Dựng 3 server 127.0.0.1 cổng 0 (không bao giờ 8787/8788/8023):
    runner   : api.tao_handler THẬT (KhoViec + KhoHoc trên thư mục tạm, hạn mức HAN_MUC_TRAN) — không in cổng ra ngoài;
    video    : video_server.H THẬT (chỉ tắt log ra stdout), RUNNER_ORIGIN trỏ vào runner ở trên;
    điều khiển (chỉ test gọi):
      POST /__ngay {"ngay": "YYYY-MM-DD", "cau_hoi": "khong"|"deu"|"pha"} → thêm lô dữ liệu của ngày đó vào DB Poster giả,
           đặt đồng hồ giả = ngày đó 12:00 VN rồi chạy runner.hoc_tu_dong.chay() THẬT (bay_gio giả) →
           {"ma": mã thoát, "ra": dòng JSON chay() in ra}
      POST /__gio  {"ngay", "gio"} → đặt đồng hồ giả (dùng chung cho KhoHoc của API) → {"luc": ISO}
      GET  /__bai → {"bai": [mọi dòng bai_hoc, đọc mode=ro]}
      GET  /__mot_ban → {"cung_lop": api.SaiTrangThaiHoc is runner.kho_hoc.SaiTrangThaiHoc, "module_kho_hoc": [...]}
- In ĐÚNG 1 dòng JSON {"video", "khoa_rieng_pkcs8", "video_key", "runner_key", "dieu_khien", "tam"} ra stdout rồi chờ
  stdin đóng; stdin đóng (tiến trình cha đóng/chết) → tắt 3 server, đóng kết nối SQLite, xoá thư mục tạm, thoát.

Fixture (§8.2, cùng khuôn tools/test_runner_hoc_tu_dong.py): 20 UID, mỗi UID 12 caption = 3 × {có số, không số} ×
{có "?", không "?"}; mỗi ngày D một lô 12 video/UID đăng lúc D−7 12:00, đo ở D−4, D−2, D (view chuẩn = view ngày D).
View = 100 × 2 (có số) × 2 (có "?" và hiệu ứng câu hỏi bật cho UID đó). Lô của ngày trước bị "rút": ngày D mỗi video cũ
nhận thêm một snapshot ngày D (số đổi → vẫn là lần đo thật của ngày D) KHÔNG có posted_ts → hoc_tu_dong loại
(bo_thieu_posted_ts) trước khi tính video hợp lệ, nên số đo ngày D chỉ phản ánh lô ngày D và nguồn không bị
poster_thieu / poster_lech_noi. `cau_hoi`: "khong" = không hiệu ứng câu hỏi; "deu" = 20/20 UID; "pha" = 11/20 UID (55%).
"""
from __future__ import annotations

import base64
import contextlib
import gc
import io
import json
import os
import secrets
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from contextlib import closing
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlsplit

# ---- 1. Môi trường an toàn TRƯỚC khi import mã thật
os.environ["KHO_HOC_TEST"] = "1"
os.environ["KHO_POSTER_TEST"] = "1"
os.environ["KHO_POSTER_WEB"] = "0"
os.environ["KHO_VIDEO_PORT"] = "0"
for _k in ("KHO_RUNNER_ORIGIN", "TT_API_BEARER_TOKEN", "TT_API_PORT", "KHO_THU_MUC_POSTER", "KHO_THU_MUC_VIEW",
           "KHO_SCRIPT_QUET_KENH"):
    os.environ.pop(_k, None)

TAM = Path(tempfile.mkdtemp(prefix="kho-hoc-noi-"))
DU_LIEU = TAM / "du_lieu"
os.environ["KHO_RUNNER_DIR"] = str(DU_LIEU)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import video_server
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from runner import api, hoc_tu_dong, kho_hoc, quet_view
from runner.han_muc import HAN_MUC_TRAN, han_muc_hoc
from runner.kho_hoc import KhoHoc
from runner.kho_viec import KhoViec
from runner.kieu import MUI_GIO_VN, MoiTruong

UID = [f"18{i:017d}" for i in range(20)]           # 19 chữ số
SO_UID_PHA = 11                                    # "pha": 11/20 = 55% < 60% (giữ) → hết bằng chứng
CAU_HOI = ("khong", "deu", "pha")
COT_QUEUE = ("id INTEGER PRIMARY KEY AUTOINCREMENT, folder_id INTEGER, video_filename TEXT, video_path TEXT, "
             "caption TEXT, product_id TEXT, visibility TEXT, first_comment TEXT, status TEXT, scheduled_at TEXT, "
             "posted_at TEXT, error_msg TEXT, retry_count INTEGER, job_id TEXT, created_at TEXT, updated_at TEXT, "
             "drive_file_id TEXT, video_size INTEGER, video_created_date TEXT, video_id TEXT, video_url TEXT")
COT_VVS = ("video_id TEXT, collected_at TEXT, product_id TEXT, folder_id INTEGER, account_id INTEGER, "
           "view_count INTEGER, like_count INTEGER, comment_count INTEGER, posted_ts INTEGER, base INTEGER, "
           "scraped_at TEXT, PRIMARY KEY (video_id, collected_at)")
SQL_SNAP = ("INSERT INTO video_view_snapshots(video_id, collected_at, product_id, folder_id, account_id, view_count, "
            "like_count, comment_count, posted_ts, base) VALUES(?,?,?,1,1,?,?,0,?,0)")


def caption(k: int, so: bool, hoi: bool) -> str:
    """Thân < 60 ký tự, không emoji/"bạn"/động từ mở đầu/từ khoá USP → chỉ cap_co_so và cap_cau_hoi đổi giữa các caption."""
    than = f"Hộp kiểu {'ABC'[k]} gọn gàng cho bé" + (f" {k + 2} ngăn" if so else "") + (" dùng ổn không?" if hoi else "")
    return than + " #hop #be"


CAPTION = [(k, so, hoi, caption(k, so, hoi)) for so in (True, False) for hoi in (True, False) for k in range(3)]


class Dong:
    """Đồng hồ giả giờ VN, dùng chung cho hoc_tu_dong.chay() và KhoHoc của API."""

    def __init__(self, ngay: date) -> None:
        self._khoa = threading.Lock()
        self.luc = datetime(ngay.year, ngay.month, ngay.day, 12, tzinfo=MUI_GIO_VN)

    def __call__(self) -> datetime:
        with self._khoa:
            return self.luc

    def dat(self, ngay: date, gio: int = 12) -> None:
        with self._khoa:
            self.luc = datetime(ngay.year, ngay.month, ngay.day, gio, tzinfo=MUI_GIO_VN)


def _ts(ngay: date) -> int:
    return int(datetime(ngay.year, ngay.month, ngay.day, 12, tzinfo=MUI_GIO_VN).timestamp())


class DuLieu:
    """DB Poster giả + repo giả + chạy hoc_tu_dong theo từng ngày (tuần tự, tăng dần)."""

    def __init__(self, dong: Dong) -> None:
        self.dong = dong
        self.poster_db = TAM / "poster" / "v2_data.db"
        self.repo = TAM / "repo"
        self.hoc_db = DU_LIEU / "hoc.db"
        self.runner_db = DU_LIEU / "runner.db"
        self.khoa = threading.Lock()
        self.ngay_cuoi: date | None = None
        self.video: list[list] = []                     # [video_id, product_id, view cuối]
        self._so = 7_400_000_000_000_000_000
        self.poster_db.parent.mkdir(parents=True)
        with closing(sqlite3.connect(self.poster_db)) as c, c:
            c.execute(f"CREATE TABLE queue({COT_QUEUE})")
            c.execute(f"CREATE TABLE video_view_snapshots({COT_VVS})")
        for u in UID:
            d = self.repo / "data" / u
            d.mkdir(parents=True)
            (d / "info.json").write_text(json.dumps({"usp": {"cau": "x", "tu_khoa": ["chống nước"]}}, ensure_ascii=False),
                                         encoding="utf-8")
            (d / "captions.txt").write_text("\n".join(f"{i + 1}. {x[3]}" for i, x in enumerate(CAPTION)) + "\n",
                                            encoding="utf-8")

    def _them_lo(self, ngay: date, cau_hoi: str) -> None:
        d = ngay.isoformat()
        pt = _ts(ngay) - 7 * 86400
        with closing(sqlite3.connect(self.poster_db)) as c, c:
            for v in self.video:                         # rút lô cũ: snapshot ngày D, số đổi, không posted_ts
                v[2] += 1
                c.execute(SQL_SNAP, (v[0], d, v[1], v[2], v[2] // 10, None))
            for i, u in enumerate(UID):
                bat_hoi = cau_hoi == "deu" or (cau_hoi == "pha" and i < SO_UID_PHA)
                for _k, so, hoi, cap in CAPTION:
                    view = 100 * (2 if so else 1) * (2 if hoi and bat_hoi else 1)
                    self._so += 1
                    vid = str(self._so)
                    c.execute("INSERT INTO queue(folder_id, caption, product_id, status, video_id) VALUES(1,?,?,'done',?)",
                              (cap, u, vid))
                    for lui, gt in ((-4, view // 3), (-2, view // 2), (0, view)):
                        c.execute(SQL_SNAP, (vid, (ngay + timedelta(days=lui)).isoformat(), u, gt, gt // 10, pt))
                    self.video.append([vid, u, view])

    def hoc_ngay(self, ngay: date, cau_hoi: str) -> dict:
        if cau_hoi not in CAU_HOI:
            raise ValueError("cau_hoi phải thuộc khong|deu|pha")
        with self.khoa:
            if self.ngay_cuoi is not None and ngay <= self.ngay_cuoi:
                raise ValueError("ngày học phải tăng dần")
            self._them_lo(ngay, cau_hoi)
            self.ngay_cuoi = ngay
            self.dong.dat(ngay, 12)
            bat_ngay, toi_da = han_muc_hoc(HAN_MUC_TRAN)
            argv = ["--ngay", ngay.isoformat(), "--hoc-db", str(self.hoc_db), "--poster-db", str(self.poster_db),
                    "--runner-db", str(self.runner_db), "--repo", str(self.repo),
                    "--viec-id", f"j{ngay.strftime('%Y%m%d')}120000abcd",
                    "--bat-ngay", str(bat_ngay), "--hieu-luc-toi-da", str(toi_da)]
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                ma = hoc_tu_dong.chay(argv, bay_gio=self.dong)
            dong_ra = [x for x in out.getvalue().splitlines() if x.strip()]
            if len(dong_ra) != 1:
                raise RuntimeError(f"hoc_tu_dong.chay() phải in đúng 1 dòng, in {len(dong_ra)}")
            return {"ma": ma, "ra": json.loads(dong_ra[0])}

    def bai_hoc(self) -> list[dict]:
        uri = f"file:{quote(self.hoc_db.resolve().as_posix(), safe='/:')}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=10)) as c:
            c.row_factory = sqlite3.Row
            return [dict(r) for r in c.execute("SELECT * FROM bai_hoc ORDER BY tao_luc, ma")]


def _ngay(s: object) -> date:
    if not isinstance(s, str) or len(s) != 10:
        raise ValueError("ngay phải dạng YYYY-MM-DD")
    return date.fromisoformat(s)


def tao_dieu_khien(du_lieu: DuLieu) -> type[BaseHTTPRequestHandler]:
    class DieuKhien(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *a) -> None:              # stdout chỉ dành cho dòng JSON
            pass

        def _gui(self, ma: int, obj: object) -> None:
            b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            try:
                self.send_response(ma)
                self.send_header("content-type", "application/json; charset=utf-8")
                self.send_header("content-length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            except OSError:
                pass

        def _body(self) -> dict:
            n = int(self.headers.get("content-length") or 0)
            d = json.loads(self.rfile.read(n).decode("utf-8")) if 0 < n <= 4096 else {}
            if not isinstance(d, dict):
                raise TypeError("body phải là JSON object")
            return d

        def _xu(self, lam) -> None:
            try:
                self._gui(200, lam())
            except (ValueError, TypeError, KeyError) as e:
                self._gui(400, {"loi": f"{type(e).__name__}: {e}"})
            except Exception as e:  # noqa: BLE001 — harness test: trả lỗi cho test đọc, server sống tiếp
                self._gui(500, {"loi": f"{type(e).__name__}: {e}"})

        def do_GET(self) -> None:
            p = urlsplit(self.path).path
            if p == "/__bai":
                return self._xu(lambda: {"bai": du_lieu.bai_hoc()})
            if p == "/__mot_ban":
                return self._xu(lambda: {
                    "cung_lop": api.SaiTrangThaiHoc is kho_hoc.SaiTrangThaiHoc
                    and api.KhongCoBaiHoc is kho_hoc.KhongCoBaiHoc,
                    "module_kho_hoc": sorted(k for k in sys.modules if k.split(".")[-1] == "kho_hoc")})
            self._gui(404, {"loi": "không có"})

        def do_POST(self) -> None:
            p = urlsplit(self.path).path
            if p == "/__ngay":
                def hoc() -> dict:
                    b = self._body()
                    return du_lieu.hoc_ngay(_ngay(b.get("ngay")), b.get("cau_hoi"))
                return self._xu(hoc)
            if p == "/__gio":
                def dat() -> dict:
                    b = self._body()
                    gio = b.get("gio", 12)
                    if type(gio) is not int or not 0 <= gio <= 23:
                        raise ValueError("gio phải là số 0–23")
                    du_lieu.dong.dat(_ngay(b.get("ngay")), gio)
                    return {"luc": du_lieu.dong().isoformat()}
                return self._xu(dat)
            self._gui(404, {"loi": "không có"})

    return DieuKhien


def _khoa_rieng_pkcs8_b64(k: Ed25519PrivateKey) -> str:
    der = k.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return base64.b64encode(der).decode("ascii")


def _dong_kv(kv: KhoViec) -> None:
    c = getattr(kv._cuc_bo, "c", None)
    if c is not None:
        kv._cuc_bo.c = None
        c.close()


def _xoa_tam() -> None:
    gc.collect()                                        # kết nối SQLite mồ côi của luồng HTTP đã kết thúc → đóng
    for _ in range(20):                                 # Windows: file SQLite có thể còn khoá trong tích tắc
        shutil.rmtree(TAM, ignore_errors=True)
        if not TAM.exists():
            return
        time.sleep(0.25)
    print(f"không xoá hết được thư mục tạm {TAM}", file=sys.stderr, flush=True)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # Chốt chống chạm production: thư mục tạm không được nằm dưới gốc dữ liệu thật nào.
    quet_view.kiem_duong_dan_thu(DU_LIEU, TAM, TAM / "poster" / "v2_data.db", TAM / "repo" / "data")
    if os.environ.get("KHO_HOC_TEST") != "1":
        raise SystemExit("KHO_HOC_TEST chưa có hiệu lực")
    may: list[ThreadingHTTPServer] = []
    dang_chay: list[ThreadingHTTPServer] = []      # shutdown() trên server chưa serve_forever sẽ treo mãi
    kv = None
    try:
        dong = Dong(date(2026, 12, 1))
        du_lieu = DuLieu(dong)
        kv = KhoViec(du_lieu.runner_db, dong)
        khg = KhoHoc(du_lieu.hoc_db, dong)
        khg.mo()
        khg.dong()
        khoa_runner = secrets.token_hex(32)
        khoa_video = secrets.token_urlsafe(24)
        ky = Ed25519PrivateKey.generate()
        mt = MoiTruong(
            gocs=[TAM / "goc"], repo_kho=du_lieu.repo, thu_muc_scripts=TAM / "scripts",
            python_poster=TAM / "khong-co" / "python.exe", claude_exe=TAM / "khong-co" / "claude.exe",
            agy_exe=TAM / "khong-co" / "agy.exe", thu_muc_radar=TAM / "radar", thu_muc_sp=TAM / "sp",
            thu_muc_du_lieu=DU_LIEU, cong_song=lambda _c: False, chan_doan_kho=lambda _r: None,
            ffmpeg_ngoai=lambda: False, thoi_luong_media=lambda _f: None, bay_gio=dong)
        runner_h = api.tao_handler(
            kv, mt, khoa_runner, ky.public_key(), dict(HAN_MUC_TRAN), [], lambda _id: None,
            lambda _id, tu: {"tu": tu, "den": tu, "noi_dung": "", "het": True},
            lambda: {"lan": {"gpu": None, "nhe": None}, "tai_nguyen": {"kho": False, "poster": False},
                     "tam_dung_claude_den": None},
            kho_hoc=KhoHoc(du_lieu.hoc_db, dong))
        rs = ThreadingHTTPServer(("127.0.0.1", 0), runner_h)
        may.append(rs)
        video_server.RUNNER_ORIGIN = f"http://127.0.0.1:{rs.server_address[1]}"

        class VideoIm(video_server.H):
            """video_server.H thật; chỉ tắt log ra stdout (stdout dành cho dòng JSON)."""

            def log_message(self, *a) -> None:
                pass

        VideoIm.khoa = khoa_video
        vs = ThreadingHTTPServer(("127.0.0.1", 0), VideoIm)
        may.append(vs)
        VideoIm.cong = vs.server_address[1]
        ds = ThreadingHTTPServer(("127.0.0.1", 0), tao_dieu_khien(du_lieu))
        may.append(ds)
        for s in may:
            if s.server_address[1] in (8787, 8788, 8023):
                raise SystemExit("cổng ngẫu nhiên trùng cổng thật")
            s.daemon_threads = True
            threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
            dang_chay.append(s)

        print(json.dumps({"video": vs.server_address[1], "khoa_rieng_pkcs8": _khoa_rieng_pkcs8_b64(ky),
                          "video_key": khoa_video, "runner_key": khoa_runner, "dieu_khien": ds.server_address[1],
                          "tam": str(TAM)}), flush=True)
        try:
            sys.stdin.buffer.read()                     # chờ tiến trình cha đóng stdin (hoặc chết)
        except (OSError, KeyboardInterrupt):
            pass
        return 0
    finally:
        for s in reversed(may):
            try:
                if s in dang_chay:
                    s.shutdown()
                s.server_close()
            except OSError:
                pass
        if kv is not None:
            with contextlib.suppress(sqlite3.Error):
                _dong_kv(kv)
        _xoa_tam()


if __name__ == "__main__":
    raise SystemExit(main())
