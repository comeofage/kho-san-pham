"""Máy chạy giả cho test nối 3 chặng Poster V2 (docs/poster-v2-tren-web.md §9 T-P1).

Chạy: python -B tools/poster_noi_gia.py   (cf/test/poster-noi-3-chang.test.mjs tự spawn)

- Đặt KHO_POSTER_TEST=1, xoá TT_API_BEARER_TOKEN / TT_API_PORT / KHO_POSTER_WEB TRƯỚC khi import poster_web/video_server,
  để chot_test của poster_web luôn được kích và không thể trỏ vào Poster thật (127.0.0.1:8023, E:/tool/tiktok_poster_v2).
- Thư mục tạm (tempfile.mkdtemp) chứa .env giả (TT_API_BEARER_TOKEN=tok-gia, TT_API_PORT=<cổng backend giả>) và nhật ký;
  KHO_POSTER_DIR / KHO_POSTER_NHAT_KY trỏ vào đó.
- Backend giả: ThreadingHTTPServer cổng 0, ghi lại method/path/query/header/body của mọi request.
    GET  /__ghi  → {"ghi": [{method, path, query, headers (khoá chữ thường), body (chuỗi utf-8)}]}
    POST /__xoa  → xoá danh sách đã ghi + mọi cấu hình trả lời của /__tra
    POST /__tra  {"method", "path", "status", "body", "cham"} → cấu hình trả lời riêng cho (method, path)
    /api/v2/... và /health → {"ok": true, "method", "path"} ngay; riêng POST /api/v2/queue/7/post chờ 1,5 s.
- video_server.H thật (cổng 0, khoá "khoa-gia"; KHO_VIDEO_PORT=0, không đụng 8787).
- In ĐÚNG 1 dòng JSON {"backend": <cổng>, "video": <cổng>, "khoa": "khoa-gia"} ra stdout rồi chờ stdin đóng;
  stdin đóng (hoặc tiến trình cha chết) → tắt 2 server, xoá thư mục tạm, thoát.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

# ---- 1. Môi trường an toàn TRƯỚC khi import mã thật
os.environ["KHO_POSTER_TEST"] = "1"
for _k in ("TT_API_BEARER_TOKEN", "TT_API_PORT", "KHO_POSTER_WEB"):
    os.environ.pop(_k, None)
os.environ["KHO_VIDEO_PORT"] = "0"

TAM = Path(tempfile.mkdtemp(prefix="kho-poster-noi-"))
os.environ["KHO_POSTER_DIR"] = str(TAM)
os.environ["KHO_POSTER_NHAT_KY"] = str(TAM / "nhat-ky.jsonl")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import poster_web  # noqa: E402
import video_server  # noqa: E402

KHOA = "khoa-gia"
TOKEN = "tok-gia"
CHAM_MAC_DINH = {("POST", "/api/v2/queue/7/post"): 1.5}


class Gia:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.ghi: list[dict] = []
        self.tra: dict[tuple[str, str], dict] = {}


GIA = Gia()


class Backend(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):  # im lặng: stdout chỉ dành cho dòng JSON cổng
        pass

    def _gui(self, st: int, obj: object) -> None:
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(st)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        except OSError:
            pass

    def _xu(self) -> None:
        n = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(n) if n > 0 else b""
        u = urlsplit(self.path)
        if u.path == "/__ghi" and self.command == "GET":
            with GIA.lock:
                return self._gui(200, {"ghi": list(GIA.ghi)})
        if u.path == "/__xoa" and self.command == "POST":
            with GIA.lock:
                GIA.ghi.clear()
                GIA.tra.clear()
            return self._gui(200, {"ok": True})
        if u.path == "/__tra" and self.command == "POST":
            cfg = json.loads(body.decode("utf-8"))
            with GIA.lock:
                GIA.tra[(cfg["method"], cfg["path"])] = cfg
            return self._gui(200, {"ok": True})
        with GIA.lock:
            GIA.ghi.append({"method": self.command, "path": u.path, "query": u.query,
                            "headers": {k.lower(): v for k, v in self.headers.items()},
                            "co_content_length": "content-length" in {k.lower() for k in self.headers.keys()},
                            "body": body.decode("utf-8", "replace")})
            cfg = dict(GIA.tra.get((self.command, u.path)) or {})
        cham = cfg.get("cham", CHAM_MAC_DINH.get((self.command, u.path), 0))
        if cham:
            time.sleep(float(cham))
        if not (u.path == "/health" or u.path.startswith("/api/v2/")):
            return self._gui(404, {"detail": "Not Found"})
        self._gui(int(cfg.get("status", 200)), cfg.get("body", {"ok": True, "method": self.command, "path": u.path}))

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _xu


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    be = vs = None
    dang_chay: list = []  # server đã serve_forever (shutdown() trên server chưa chạy sẽ treo mãi)
    try:
        be = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        be.daemon_threads = True
        cong_be = be.server_address[1]
        (TAM / ".env").write_text(f"# .env giả của test nối 3 chặng\nTT_API_BEARER_TOKEN={TOKEN}\nTT_API_PORT={cong_be}\n",
                                  encoding="utf-8")
        # Tự kiểm chốt chống chạm production đã được kích và cấu hình trỏ đúng backend giả.
        try:
            poster_web.chot_test(8023, TAM)
        except RuntimeError:
            pass
        else:
            raise SystemExit("chot_test không kích (KHO_POSTER_TEST chưa có hiệu lực)")
        token, port = poster_web.cau_hinh()
        if port != cong_be or token != TOKEN or port == 8023:
            raise SystemExit("cấu hình Poster không trỏ vào backend giả")

        video_server.H.khoa = KHOA
        vs = ThreadingHTTPServer(("127.0.0.1", 0), video_server.H)
        vs.daemon_threads = True
        cong_vs = vs.server_address[1]
        video_server.H.cong = cong_vs
        for s in (be, vs):
            threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
            dang_chay.append(s)

        print(json.dumps({"backend": cong_be, "video": cong_vs, "khoa": KHOA}), flush=True)
        try:
            sys.stdin.buffer.read()  # chờ tiến trình cha đóng stdin (hoặc chết)
        except (OSError, KeyboardInterrupt):
            pass
        return 0
    finally:
        for s in (vs, be):
            if s is None:
                continue
            try:
                if s in dang_chay:
                    s.shutdown()
                s.server_close()
            except OSError:
                pass
        shutil.rmtree(TAM, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
