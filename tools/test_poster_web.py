"""Test tools/poster_web.py + móc /p/* trong video_server (docs/poster-v2-tren-web.md §9 B-P1).

Chạy: python -B -m pytest tools/test_poster_web.py -q -p no:cacheprovider
Mọi test dùng backend giả HTTP cổng ngẫu nhiên; KHÔNG BAO GIỜ gọi 127.0.0.1:8023 hay đọc E:/tool/tiktok_poster_v2.
"""
import hashlib
import http.client
import importlib.util
import json
import secrets
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import poster_web as pw  # noqa: E402

_spec = importlib.util.spec_from_file_location("video_server_pw", _TOOLS / "video_server.py")
vs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vs)

KHOA = "khoa-test-poster"
TOKEN = "tok-gia-" + secrets.token_hex(8)
CAU_B3 = "Đường dẫn phải là thư mục/tệp trên ổ đĩa máy nhà"


# ---------------------------------------------------------------- fixture chung (luật test §9)
@pytest.fixture(autouse=True)
def moi_truong(tmp_path, monkeypatch):
    for k in ("KHO_POSTER_DIR", "TT_API_BEARER_TOKEN", "TT_API_PORT", "KHO_POSTER_NHAT_KY",
              "KHO_POSTER_WEB", "KHO_POSTER_TEST"):
        monkeypatch.delenv(k, raising=False)
    pd = tmp_path / "poster"
    pd.mkdir()
    monkeypatch.setenv("KHO_POSTER_DIR", str(pd))
    monkeypatch.setenv("KHO_POSTER_NHAT_KY", str(tmp_path / "nk" / "nhat-ky.jsonl"))
    monkeypatch.setattr(pw, "BANG", pw.BangLenh(pw._su_kien_bang))
    monkeypatch.setattr(pw, "_CACHE_ENV", {})
    return pd


class Gia:
    """Backend giả: ghi lại mọi request; cấu hình trả lời theo (method, path)."""

    def __init__(self):
        self.nhan: list[dict] = []
        self.lock = threading.Lock()
        self.tra: dict[tuple[str, str], dict] = {}

    def dem(self, method=None, path=None) -> int:
        with self.lock:
            return sum(1 for n in self.nhan if (method is None or n["method"] == method)
                       and (path is None or n["path"] == path))


def _lam_handler(gia: Gia):
    class B(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _xu(self):
            n = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(n) if n else b""
            u = urlsplit(self.path)
            with gia.lock:
                gia.nhan.append({"method": self.command, "path": u.path, "query": u.query,
                                 "headers": {k.lower(): v for k, v in self.headers.items()},
                                 "body": body})
            cfg = gia.tra.get((self.command, u.path)) or {}
            if cfg.get("cham"):
                time.sleep(cfg["cham"])
            st = cfg.get("status", 200)
            if "raw" in cfg:
                b = cfg["raw"]
            else:
                b = json.dumps(cfg.get("body", {"ok": True, "method": self.command, "path": u.path}),
                               ensure_ascii=False).encode()
            try:
                if cfg.get("nho_giot_ca"):  # nhả cả dòng trạng thái + header + body từng byte
                    tho = (f"HTTP/1.0 {st} OK\r\ncontent-type: application/json\r\n"
                           f"content-length: {len(b)}\r\n\r\n").encode() + b
                    for i in range(len(tho)):
                        self.wfile.write(tho[i:i + 1]); self.wfile.flush(); time.sleep(cfg["nho_giot_ca"])
                    return
                self.send_response(st)
                self.send_header("content-type", cfg.get("ct", "application/json"))
                self.send_header("content-length", str(len(b)))
                self.end_headers()
                if cfg.get("nho_giot"):
                    for i in range(len(b)):
                        self.wfile.write(b[i:i + 1]); self.wfile.flush(); time.sleep(cfg["nho_giot"])
                else:
                    self.wfile.write(b)
            except OSError:
                pass

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _xu

    return B


@pytest.fixture
def be(moi_truong, monkeypatch):
    gia = Gia()
    s = ThreadingHTTPServer(("127.0.0.1", 0), _lam_handler(gia))
    port = s.server_address[1]
    assert port != 8023
    t = threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    t.start()
    monkeypatch.setenv("TT_API_PORT", str(port))
    (moi_truong / ".env").write_text(f"# env giả\n\nTT_API_BEARER_TOKEN=\"{TOKEN}\"\n", encoding="utf-8")
    gia.port = port
    try:
        yield gia
    finally:
        s.shutdown(); s.server_close(); t.join(5)


@pytest.fixture
def vsrv(monkeypatch):
    monkeypatch.setattr(vs.H, "khoa", KHOA)
    s = ThreadingHTTPServer(("127.0.0.1", 0), vs.H)
    t = threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    t.start()
    try:
        yield s.server_address[1]
    finally:
        s.shutdown(); s.server_close(); t.join(5)


def goi(port, method, path, body=None, ct="application/json", khoa=KHOA, headers=None, timeout=30):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    h = {}
    if khoa is not None:
        h["x-key"] = khoa
    if body is not None:
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body).encode()
        if ct:
            h["content-type"] = ct
    h.update(headers or {})
    try:
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        data = r.read()
        hd = {k.lower(): v for k, v in r.getheaders()}
    finally:
        c.close()
    try:
        obj = json.loads(data) if data else None
    except ValueError:
        obj = data
    return r.status, hd, obj


def goi_tho(port, dong: bytes) -> int:
    """Gửi request thô (path có ký tự http.client không cho gửi), trả status."""
    with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
        s.sendall(dong + b" HTTP/1.0\r\nx-key: " + KHOA.encode() + b"\r\n\r\n")
        tra = b""
        while chunk := s.recv(65536):
            tra += chunk
    return int(tra.split(b" ", 2)[1])


def cho_kq(port, ma, toi_da=15.0) -> dict:
    het = time.monotonic() + toi_da
    while time.monotonic() < het:
        st, _, o = goi(port, "GET", f"/p/_kq/{ma}")
        assert st == 200, (st, o)
        if o.get("xong"):
            return o
        time.sleep(0.05)
    raise AssertionError("lệnh nền không xong")


def tra_ve(port, method, path, body=None, **kw):
    """Gọi /p…; nếu 202 thì chờ _kq, trả (status, body) cuối cùng."""
    st, hd, o = goi(port, method, path, body, **kw)
    if st == 202 and isinstance(o, dict) and "cho" in o:
        k = cho_kq(port, o["cho"])
        return k["status"], k["body"]
    return st, o


def doc_nhat_ky(tmp_path) -> list[dict]:
    f = tmp_path / "nk" / "nhat-ky.jsonl"
    if not f.exists():
        return []
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


# ---------------------------------------------------------------- chống chạm production
class _DemKetNoi:
    def __init__(self):
        self.n = 0

    def __call__(self, *a, **k):
        self.n += 1
        raise AssertionError("không được mở kết nối")


def test_chot_test_cong_8023_nem_loi_khong_mo_socket(tmp_path, monkeypatch):
    dem = _DemKetNoi()
    monkeypatch.setattr(http.client, "HTTPConnection", dem)
    with pytest.raises(RuntimeError, match="Poster V2 thật"):
        pw.chot_test(8023, tmp_path)
    assert dem.n == 0


def test_chot_test_thu_muc_that_nem_loi(monkeypatch):
    dem = _DemKetNoi()
    monkeypatch.setattr(http.client, "HTTPConnection", dem)
    with pytest.raises(RuntimeError, match="Poster V2 thật"):
        pw.chot_test(54321, Path("E:/tool/tiktok_poster_v2"))
    with pytest.raises(RuntimeError):
        pw.chot_test(54321, Path("e:\\tool\\tiktok_poster_v2\\"))
    assert dem.n == 0


def test_chot_test_cho_qua_khi_khong_trung(tmp_path):
    pw.chot_test(54321, tmp_path)  # không ném


def test_chot_test_nhan_ca_bien_KHO_POSTER_TEST(monkeypatch, tmp_path):
    monkeypatch.delitem(sys.modules, "pytest")
    pw.chot_test(8023, tmp_path)  # ngoài test: không chặn
    monkeypatch.setenv("KHO_POSTER_TEST", "1")
    with pytest.raises(RuntimeError):
        pw.chot_test(8023, tmp_path)


def test_mac_dinh_tro_poster_that_bi_chan_khong_mo_socket(monkeypatch):
    """Không đặt gì: poster_dir() là thư mục thật, cổng 8023 → cau_hinh/goi_backend ném, 0 kết nối."""
    monkeypatch.delenv("KHO_POSTER_DIR")
    dem = _DemKetNoi()
    monkeypatch.setattr(http.client, "HTTPConnection", dem)
    assert pw.poster_dir() == Path("E:/tool/tiktok_poster_v2")
    with pytest.raises(RuntimeError):
        pw.cau_hinh()
    with pytest.raises(RuntimeError):
        pw.goi_backend("GET", "/health", None, 1.0)
    assert dem.n == 0


def test_cong_8023_tu_env_bi_chan(moi_truong, monkeypatch):
    dem = _DemKetNoi()
    monkeypatch.setattr(http.client, "HTTPConnection", dem)
    monkeypatch.setenv("TT_API_PORT", "8023")
    with pytest.raises(RuntimeError):
        pw.goi_backend("GET", "/health", None, 1.0)
    assert dem.n == 0


def test_cau_hinh_doc_env_sau_import(moi_truong, tmp_path, monkeypatch):
    khac = tmp_path / "poster2"
    khac.mkdir()
    (khac / ".env").write_text("TT_API_BEARER_TOKEN='abc'\nTT_API_PORT=45678\n", encoding="utf-8")
    monkeypatch.setenv("KHO_POSTER_DIR", str(khac))
    assert pw.poster_dir() == khac
    assert pw.cau_hinh() == ("abc", 45678)
    monkeypatch.setenv("TT_API_BEARER_TOKEN", "tu-env")
    monkeypatch.setenv("TT_API_PORT", "45679")
    assert pw.cau_hinh() == ("tu-env", 45679)


def test_env_file_doi_thi_doc_lai_theo_mtime(moi_truong, monkeypatch):
    monkeypatch.setenv("TT_API_PORT", "45678")
    f = moi_truong / ".env"
    f.write_text("TT_API_BEARER_TOKEN=mot\n", encoding="utf-8")
    assert pw.cau_hinh()[0] == "mot"
    f.write_text("# đổi\nTT_API_BEARER_TOKEN=\"hai\"\n", encoding="utf-8")
    import os
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    assert pw.cau_hinh()[0] == "hai"


# ---------------------------------------------------------------- chuyển tiếp bảng §2.2
POST_DIRECT = "POST_DIRECT"
TUYEN = [
    ("GET", "/health", "", None),
    ("GET", "/api/v2/system/health", "", None),
    ("GET", "/api/v2/stats/", "", None),
    ("GET", "/api/v2/logs/", "limit=50&offset=0&status=failed", None),
    ("GET", "/api/v2/logs/affiliate-stats", "product_id=123", None),
    ("GET", "/api/v2/accounts/", "", None),
    ("POST", "/api/v2/accounts/", "", {"name": "acc1", "cookies_path": "E:\\c\\a.json"}),
    ("PUT", "/api/v2/accounts/3", "", {"name": "acc1"}),
    ("DELETE", "/api/v2/accounts/3", "", None),
    ("POST", "/api/v2/accounts/3/test-cookies", "", {}),
    ("POST", "/api/v2/accounts/3/cooldown", "", {"minutes": 30}),
    ("DELETE", "/api/v2/accounts/3/cooldown", "", None),
    ("POST", "/api/v2/accounts/clean_profiles", "", {}),
    ("POST", "/api/v2/accounts/login_and_capture", "", {"name": "acc1", "proxy": ""}),
    ("POST", "/api/v2/accounts/cookies_from_json", "", {"name": "acc1", "cookies": [{"name": "a", "value": "b"}]}),
    ("GET", "/api/v2/views/health/3", "", None),
    ("GET", "/api/v2/folders/", "archived=0", None),
    ("POST", "/api/v2/folders/", "", {"name": "f", "path": "E:\\v", "source": "local"}),
    ("PUT", "/api/v2/folders/3", "", {"path": "E:/v"}),
    ("PATCH", "/api/v2/folders/3", "", {"archived": True}),
    ("DELETE", "/api/v2/folders/3", "", None),
    ("GET", "/api/v2/folders/3/suggest_phase", "n=5", None),
    ("GET", "/api/v2/folders/cadence_forecast", "days=7", None),
    ("GET", "/api/v2/folders/3/drive-test", "", None),
    ("POST", "/api/v2/folders/3/post_now", "", {"visibility": "everyone"}),
    ("POST", "/api/v2/folders/batch_schedule", "", {"folder_ids": [3]}),
    ("GET", "/api/v2/queue/", "limit=50&offset=0&status=pending", None),
    ("GET", "/api/v2/queue/status", "", None),
    ("POST", "/api/v2/queue/3/post", "", {}),
    ("POST", "/api/v2/queue/3/retry", "", {}),
    ("DELETE", "/api/v2/queue/3", "", None),
    ("POST", "/api/v2/queue/unstick", "", {}),
    ("DELETE", "/api/v2/queue/pending/clear", "", None),
    ("POST", "/api/v2/queue/reset-all", "", {}),
    ("POST", "/api/v2/queue/random_shuffle", "", {}),
    ("GET", "/api/v2/settings/", "", None),
    ("POST", "/api/v2/settings/autopost-on", "", {}),
    ("POST", "/api/v2/settings/autopost-off", "", {}),
    ("PUT", "/api/v2/settings/headless", "", {"value": "true"}),
    ("GET", "/api/v2/calendar/month", "year=2026&month=11&account_id=3", None),
    ("POST", "/api/v2/calendar/plans", "", {"account_id": 3, "date": "2026-11-20"}),
    ("DELETE", "/api/v2/calendar/plans/3", "", None),
    ("GET", "/api/v2/views/summary", "", None),
    ("POST", "/api/v2/views/refresh", "", {}),
    ("POST", "/api/v2/post/direct", "", POST_DIRECT),
    ("POST", "/api/v2/queue/3/run", "", {}),
    ("GET", "/api/v2/settings/telegram_chat_id", "", None),
    # ngoài bảng (Q1 "mở hết /api/v2/")
    ("POST", "/api/v2/settings/backup-now", "", {}),
    ("GET", "/api/v2/system/config", "", None),
]
LOP_MONG = {"/api/v2/accounts/login_and_capture": "DN", "/api/v2/queue/3/post": "L",
            "/api/v2/post/direct": "L", "/api/v2/queue/3/run": "L"}


def _thu_muc_folder(tmp_path) -> Path:
    d = tmp_path / "vid"
    d.mkdir(exist_ok=True)
    (d / "a.mp4").write_bytes(b"x" * 10)
    return d


@pytest.mark.parametrize("method,path,query,body", TUYEN, ids=[f"{m} {p}?{q}" for m, p, q, _ in TUYEN])
def test_moi_tuyen_chuyen_dung(vsrv, be, tmp_path, method, path, query, body):
    if body == POST_DIRECT:
        d = _thu_muc_folder(tmp_path)
        be.tra[("GET", "/api/v2/folders/7")] = {"body": {"id": 7, "path": str(d), "source": "local"}}
        body = {"folder_id": 7, "video_path": str(d / "a.mp4"), "caption": "c", "visibility": "everyone"}
    assert pw.lop_cua(method, path) == LOP_MONG.get(path, "S")
    st, hd, o = goi(vsrv, method, "/p" + path + ("?" + query if query else ""), body)
    if path in LOP_MONG:
        assert st == 202 and len(o["cho"]) == 32 and o["trung"] is False
        o = cho_kq(vsrv, o["cho"])
        assert o["status"] == 200
        o = o["body"]
    else:
        assert st == 200, o
        assert hd["content-type"].startswith("application/json")
    assert o["method"] == method and o["path"] == path
    n = be.nhan[-1]
    assert (n["method"], n["path"], n["query"]) == (method, path, query)
    assert n["body"] == (json.dumps(body).encode() if body is not None else b"")
    assert be.dem(method, path) == 1


def test_lop_cua_bang():
    assert pw.lop_cua("POST", "/api/v2/queue/123/post") == "L"
    assert pw.lop_cua("POST", "/api/v2/queue/123/run") == "L"
    assert pw.lop_cua("GET", "/api/v2/queue/123/post") == "S"
    assert pw.lop_cua("POST", "/api/v2/queue/abc/post") == "S"
    assert pw.lop_cua("POST", "/api/v2/accounts/login_and_capture") == "DN"
    assert pw.lop_cua("PUT", "/api/v2/khong-co") == "S"


# ---------------------------------------------------------------- lọc path
@pytest.mark.parametrize("p", [
    "/p/api/v2/../x", "/p/api/v2/a/../b", "/p/api/v2/./x", "/p/api/v2/a/.", "/p/api/v2//x", "/p//api/v2/x",
    "/p/api/v2/%2e%2e/x", "/p/api/v2/a%2fb", "/p/api/v2/a%5cb", "/p/api/v2/a\\b",
    "/p/api/v1/x", "/p/api/v2", "/p/api/v2/", "/p/healthz", "/p", "/p/", "/p/abc", "/p/_kq/xyz",
    "/p/api/v2/" + "a" * 201, "/p/_video/abc", "/p/_video/1234567890",
])
def test_loc_path_404_khong_goi_backend(vsrv, be, p):
    st, _, o = goi(vsrv, "GET", p)
    assert st == 404
    assert be.dem() == 0


def test_loc_path_ky_tu_dieu_khien_404(vsrv, be):
    assert goi_tho(vsrv, b"GET /p/api/v2/a\x01b") == 404
    assert goi_tho(vsrv, b"GET /p/api/v2/a\x7fb") == 404
    assert be.dem() == 0


def test_query_qua_dai_hoac_xau_400(vsrv, be):
    assert goi(vsrv, "GET", "/p/api/v2/logs/?" + "a" * 513)[0] == 400
    assert goi_tho(vsrv, b"GET /p/api/v2/logs/?a=\x01") == 400
    assert goi_tho(vsrv, b"GET /p/api/v2/logs/?a=1#b") == 400
    assert be.dem() == 0
    assert goi(vsrv, "GET", "/p/api/v2/logs/?" + "a" * 512)[0] == 200


def test_head_options_khong_chuyen(vsrv, be):
    assert goi(vsrv, "HEAD", "/p/api/v2/stats/")[0] in (405, 501)
    assert goi(vsrv, "OPTIONS", "/p/api/v2/stats/")[0] in (405, 501)
    assert be.dem() == 0


def test_kiem_path_ham():
    assert pw.kiem_path("/health") and pw.kiem_path("/api/v2/folders/") and pw.kiem_path("/api/v2/a..b")
    for p in ("/api/v2/..", "/api/v2/a/./b", "/api/v2//a", "/api/v2/%41", "/health/", "/api/v2/a b", "/api/v2/\x00"):
        assert not pw.kiem_path(p), p


# ---------------------------------------------------------------- x-key
@pytest.mark.parametrize("khoa", [None, "", "sai", "khoa-test-posteR", "khóa"])
def test_x_key_sai_401_co_header(vsrv, be, khoa):
    st, hd, o = goi(vsrv, "GET", "/p/api/v2/stats/", khoa=khoa)
    assert st == 401 and hd.get("x-kho-tu-choi") == "khoa"
    st, hd, _ = goi(vsrv, "POST", "/p/api/v2/queue/unstick", {}, khoa=khoa)
    assert st == 401 and hd.get("x-kho-tu-choi") == "khoa"
    assert be.dem() == 0


def test_v_sai_khoa_van_401_nhu_cu(vsrv):
    st, hd, o = goi(vsrv, "GET", "/v/1731141980888533631/ds", khoa="sai")
    assert st == 401 and o == {"loi": "Sai khoá"} and "x-kho-tu-choi" not in hd


def test_r_put_van_405(vsrv):
    assert goi(vsrv, "PUT", "/r/viec", {})[0] == 405
    assert goi(vsrv, "DELETE", "/v/1731141980888533631/ds")[0] == 405


def test_khoa_rong_o_server_khong_cho_qua(vsrv, be, monkeypatch):
    monkeypatch.setattr(vs.H, "khoa", "")
    st, hd, _ = goi(vsrv, "GET", "/p/api/v2/stats/", khoa="")
    assert st == 401 and hd.get("x-kho-tu-choi") == "khoa"


# ---------------------------------------------------------------- hợp đồng §2.1
def test_delete_khong_body_khong_content_type(vsrv, be):
    st, _, _ = goi(vsrv, "DELETE", "/p/api/v2/queue/3")
    assert st == 200
    n = be.nhan[-1]
    assert n["method"] == "DELETE" and n["body"] == b"" and "content-type" not in n["headers"]


def test_delete_co_body_400(vsrv, be):
    assert goi(vsrv, "DELETE", "/p/api/v2/queue/3", {"a": 1})[0] == 400
    assert be.dem() == 0


def test_get_co_body_400(vsrv, be):
    assert goi(vsrv, "GET", "/p/api/v2/stats/", {"a": 1})[0] == 400
    assert be.dem() == 0


def test_post_rong_ngoac_nhon(vsrv, be):
    st, _, _ = goi(vsrv, "POST", "/p/api/v2/queue/unstick", {})
    assert st == 200
    n = be.nhan[-1]
    assert n["body"] == b"{}" and n["headers"]["content-type"] == "application/json"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
def test_post_put_patch_loi_hop_dong(vsrv, be, method):
    p = "/p/api/v2/folders/3"
    assert goi(vsrv, method, p, headers={"content-type": "application/json"})[0] == 400   # rỗng
    assert goi(vsrv, method, p, b"")[0] == 400
    assert goi(vsrv, method, p)[0] == 415                                    # rỗng, không content-type
    assert goi(vsrv, method, p, {"a": 1}, ct="text/plain")[0] == 415
    assert goi(vsrv, method, p, {"a": 1}, ct=None)[0] == 415
    assert goi(vsrv, method, p, b"{hong")[0] == 400
    assert goi(vsrv, method, p, b"\xff\xfe")[0] == 400
    assert goi(vsrv, method, p, b'{"x":"' + b"a" * (256 * 1024) + b'"}')[0] == 413
    assert be.dem() == 0
    st, _, _ = goi(vsrv, method, p, {"a": 1}, ct="application/json; charset=utf-8")
    assert st == 200 and be.nhan[-1]["headers"]["content-type"] == "application/json"


def test_header_toi_backend_chi_gom_cho_phep(vsrv, be):
    goi(vsrv, "POST", "/p/api/v2/queue/unstick", {}, headers={
        "cookie": "kho_s=1", "x-poster-boi": "nhan", "x-runner-key": "r", "x-pv": "1", "x-ky": "k",
        "authorization": "Bearer cua-trinh-duyet"})
    goi(vsrv, "GET", "/p/api/v2/stats/", headers={"cookie": "a=b"})
    post, get = be.nhan[-2]["headers"], be.nhan[-1]["headers"]
    assert post["authorization"] == f"Bearer {TOKEN}" and get["authorization"] == f"Bearer {TOKEN}"
    assert post["accept"] == "application/json" and post["content-type"] == "application/json"
    assert "content-type" not in get
    cho_phep = {"authorization", "accept", "content-type", "content-length", "host", "accept-encoding"}
    assert set(post) <= cho_phep and set(get) <= cho_phep, (post, get)


def test_token_env_ghi_de_va_khong_lo(vsrv, be, tmp_path, monkeypatch, capfd):
    monkeypatch.setenv("TT_API_BEARER_TOKEN", "tok-env-" + TOKEN)
    st, hd, o = goi(vsrv, "POST", "/p/api/v2/queue/unstick", {}, headers={"x-poster-boi": "nhan"})
    assert be.nhan[-1]["headers"]["authorization"] == "Bearer tok-env-" + TOKEN
    st2, hd2, o2 = goi(vsrv, "GET", "/p/_thong_tin")
    ra = capfd.readouterr()
    for chuoi in (json.dumps(o), json.dumps(hd), json.dumps(o2), json.dumps(hd2), ra.out, ra.err,
                  json.dumps(doc_nhat_ky(tmp_path))):
        assert TOKEN not in chuoi


# ---------------------------------------------------------------- B1
@pytest.mark.parametrize("ten", ["a/b", "a\\b", "C:x", ".", "..", "x" * 101, "", "a\x01b", 5, None])
@pytest.mark.parametrize("method,path", [("POST", "/api/v2/accounts/"), ("PUT", "/api/v2/accounts/3"),
                                         ("PATCH", "/api/v2/accounts/3"),
                                         ("POST", "/api/v2/accounts/cookies_from_json")])
def test_b1_ten_account_sai_400(vsrv, be, ten, method, path):
    st, _, o = goi(vsrv, method, "/p" + path, {"name": ten, "cookies": []})
    assert st == 400 and o["loi"] == "Tên account không hợp lệ"
    assert be.dem() == 0


def test_b1_ten_hop_le_qua(vsrv, be):
    assert goi(vsrv, "PATCH", "/p/api/v2/accounts/3", {"name": "a..b"})[0] == 200
    assert goi(vsrv, "POST", "/p/api/v2/accounts/", {"name": "x" * 100})[0] == 200
    assert goi(vsrv, "POST", "/p/api/v2/accounts/3/cooldown", {"minutes": 5})[0] == 200  # không có name


def test_cookies_from_json_cookies_phai_la_mang(vsrv, be):
    st, _, o = goi(vsrv, "POST", "/p/api/v2/accounts/cookies_from_json", {"name": "a", "cookies": "x"})
    assert st == 400 and be.dem() == 0


# ---------------------------------------------------------------- B2
def _b2(tmp_path, be, src="local", path=None):
    d = _thu_muc_folder(tmp_path)
    (d / "b.txt").write_text("x")
    (tmp_path / "ngoai.mp4").write_bytes(b"x")
    be.tra[("GET", "/api/v2/folders/7")] = {"body": {"id": 7, "path": path if path is not None else str(d),
                                                     "source": src}}
    return d


@pytest.mark.parametrize("ca", ["ngoai", "duoi", "khong_co", "drive", "unc", "folder_id", "video_path"])
def test_b2_post_direct_sai_400(vsrv, be, tmp_path, ca):
    d = _b2(tmp_path, be, src="drive" if ca == "drive" else "local",
            path="\\\\host\\share\\vid" if ca == "unc" else None)
    vp = {"ngoai": str(tmp_path / "ngoai.mp4"), "duoi": str(d / "b.txt"),
          "khong_co": str(d / "z.mp4")}.get(ca, str(d / "a.mp4"))
    body = {"folder_id": 7, "video_path": vp}
    if ca == "folder_id":
        body["folder_id"] = "7"
    if ca == "video_path":
        body["video_path"] = 5
    st, o = tra_ve(vsrv, "POST", "/p/api/v2/post/direct", body)
    assert st == 400, o
    assert be.dem("POST") == 0


def test_b2_dung_thi_chuyen_va_tra_404_folder(vsrv, be, tmp_path):
    d = _b2(tmp_path, be)
    st, o = tra_ve(vsrv, "POST", "/p/api/v2/post/direct", {"folder_id": 7, "video_path": str(d / "a.mp4")})
    assert st == 200 and be.dem("POST", "/api/v2/post/direct") == 1
    be.tra[("GET", "/api/v2/folders/8")] = {"status": 404, "body": {"detail": "Folder not found"}}
    st, o = tra_ve(vsrv, "POST", "/p/api/v2/post/direct", {"folder_id": 8, "video_path": str(d / "a.mp4")})
    assert st == 404 and o == {"detail": "Folder not found"}
    assert be.dem("POST", "/api/v2/post/direct") == 1


# ---------------------------------------------------------------- B3
@pytest.mark.parametrize("xau", ["\\\\host\\share\\x", "//host/x", "\\\\?\\C:\\x", "relative\\x", "\\\\.\\C:\\x",
                                 "E:\\a\x00b", "/abs/x"])
@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/v2/folders/", lambda x: {"items": [{"a": {"path": x}}]}),
    ("PUT", "/api/v2/accounts/3", lambda x: {"cookies_path": x}),
    ("POST", "/api/v2/accounts/", lambda x: {"name": "a", "chrome_profile_dir": x}),
    ("POST", "/api/v2/folders/batch_schedule", lambda x: [{"video_path": x}]),
    ("POST", "/_dem", lambda x: {"duong_dan": x}),
])
def test_b3_duong_dan_mang_400(vsrv, be, xau, method, path, body):
    st, _, o = goi(vsrv, method, "/p" + path, body(xau))
    assert st == 400 and o["loi"].startswith(CAU_B3), o
    assert be.dem() == 0


def test_b3_o_dia_qua(vsrv, be):
    assert goi(vsrv, "PUT", "/p/api/v2/folders/3", {"path": "E:\\x"})[0] == 200
    assert goi(vsrv, "PUT", "/p/api/v2/folders/3", {"path": "E:/x", "cookies_path": ""})[0] == 200
    assert pw.la_duong_dan_o_dia("e:/x") and not pw.la_duong_dan_o_dia("E:") and not pw.la_duong_dan_o_dia(5)


# ---------------------------------------------------------------- C1
SETTINGS = {"telegram_bot_token": "123:abc", "anthropic_api_key": "sk-x", "x_password": "p", "y_secret": "s",
            "rong_token": "", "headless": "true", "telegram_chat_id": "42"}


def test_c1_che_settings(vsrv, be):
    be.tra[("GET", "/api/v2/settings/")] = {"body": SETTINGS}
    st, _, o = goi(vsrv, "GET", "/p/api/v2/settings/")
    assert st == 200
    assert o == {"telegram_bot_token": "***", "anthropic_api_key": "***", "x_password": "***", "y_secret": "***",
                 "rong_token": "", "headless": "true", "telegram_chat_id": "42"}


def test_c1_dang_key_value(vsrv, be):
    be.tra[("GET", "/api/v2/settings/telegram_bot_token")] = {"body": {"key": "telegram_bot_token", "value": "123:abc"}}
    be.tra[("PUT", "/api/v2/settings/anthropic_api_key")] = {"body": {"key": "anthropic_api_key", "value": "sk"}}
    be.tra[("GET", "/api/v2/settings/headless")] = {"body": {"key": "headless", "value": "true"}}
    assert goi(vsrv, "GET", "/p/api/v2/settings/telegram_bot_token")[2] == {"key": "telegram_bot_token", "value": "***"}
    assert goi(vsrv, "PUT", "/p/api/v2/settings/anthropic_api_key", {"value": "sk"})[2]["value"] == "***"
    assert goi(vsrv, "GET", "/p/api/v2/settings/headless")[2] == {"key": "headless", "value": "true"}
    be.tra[("GET", "/api/v2/stats/")] = {"body": {"telegram_bot_token": "lo"}}  # ngoài settings: không che
    assert goi(vsrv, "GET", "/p/api/v2/stats/")[2] == {"telegram_bot_token": "lo"}


def test_c1_qua_kq_cung_che(vsrv, be, monkeypatch):
    monkeypatch.setattr(pw, "HAN_CHO_DONG_BO", 0.3)
    be.tra[("GET", "/api/v2/settings/")] = {"body": SETTINGS, "cham": 0.8}
    st, _, o = goi(vsrv, "GET", "/p/api/v2/settings/")
    assert st == 202
    k = cho_kq(vsrv, o["cho"])
    assert k["status"] == 200 and k["body"]["telegram_bot_token"] == "***" and "123:abc" not in json.dumps(k)


# ---------------------------------------------------------------- lỗi backend
def test_backend_tat_502(vsrv, moi_truong, monkeypatch):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    monkeypatch.setenv("TT_API_PORT", str(port))
    st, _, o = goi(vsrv, "GET", "/p/api/v2/stats/")
    assert st == 502 and o == {"loi": "Poster V2 trên máy nhà chưa mở", "ma": "chua_mo"}


def test_backend_401_get_goi_lai_1_lan_post_khong(vsrv, be):
    be.tra[("GET", "/api/v2/stats/")] = {"status": 401, "body": {"detail": "bad token"}}
    be.tra[("POST", "/api/v2/queue/unstick")] = {"status": 401, "body": {"detail": "bad token"}}
    st, _, o = goi(vsrv, "GET", "/p/api/v2/stats/")
    assert st == 502 and o == {"loi": "Poster V2 từ chối token (TT_API_BEARER_TOKEN lệch)", "ma": "token"}
    assert be.dem("GET", "/api/v2/stats/") == 2
    st, _, o = goi(vsrv, "POST", "/p/api/v2/queue/unstick", {})
    assert st == 502 and be.dem("POST", "/api/v2/queue/unstick") == 1


def test_backend_403_chuyen_nguyen(vsrv, be):
    be.tra[("GET", "/api/v2/stats/")] = {"status": 403, "body": {"detail": "License hết hạn"}}
    assert goi(vsrv, "GET", "/p/api/v2/stats/")[::2] == (403, {"detail": "License hết hạn"})


def test_backend_404_va_khong_phai_json(vsrv, be):
    be.tra[("GET", "/api/v2/khong-co")] = {"status": 404, "body": {"detail": "Not Found"}}
    assert goi(vsrv, "GET", "/p/api/v2/khong-co")[::2] == (404, {"detail": "Not Found"})
    be.tra[("GET", "/api/v2/loi")] = {"status": 500, "raw": b"Internal Server Error", "ct": "text/plain"}
    assert goi(vsrv, "GET", "/p/api/v2/loi")[::2] == (500, {"detail": "Internal Server Error"})


def test_backend_phan_hoi_qua_4mb_502(vsrv, be):
    be.tra[("GET", "/api/v2/to")] = {"raw": b'"' + b"a" * (4 * 1024 * 1024) + b'"'}
    assert goi(vsrv, "GET", "/p/api/v2/to")[0] == 502


# ---------------------------------------------------------------- hạn giờ
@pytest.fixture
def han_ngan(monkeypatch):
    monkeypatch.setattr(pw, "HAN_CHO_DONG_BO", 0.5)
    monkeypatch.setitem(pw.HAN_NEN, "S", 1.5)


def test_get_cham_1s_chuyen_nen_roi_xong(vsrv, be, han_ngan):
    be.tra[("GET", "/api/v2/folders/")] = {"cham": 1.0}
    t = time.monotonic()
    st, _, o = goi(vsrv, "GET", "/p/api/v2/folders/?archived=0")
    assert st == 202 and o["toi_da_giay"] == 1.5 and time.monotonic() - t < 1.0
    k = cho_kq(vsrv, o["cho"])
    assert k["status"] == 200 and k["body"]["path"] == "/api/v2/folders/"


def test_get_cham_3s_kq_504_cau_get(vsrv, be, han_ngan):
    be.tra[("GET", "/api/v2/folders/")] = {"cham": 3.0}
    st, _, o = goi(vsrv, "GET", "/p/api/v2/folders/")
    t = time.monotonic()
    k = cho_kq(vsrv, o["cho"])
    assert k["status"] == 504 and "quá chậm" in k["body"]["loi"] and "CÓ THỂ" not in k["body"]["loi"]
    assert time.monotonic() - t < 1.6


def test_post_cham_3s_kq_504_co_the_da_chay(vsrv, be, han_ngan):
    be.tra[("POST", "/api/v2/queue/unstick")] = {"cham": 3.0}
    st, _, o = goi(vsrv, "POST", "/p/api/v2/queue/unstick", {})
    assert st == 202
    k = cho_kq(vsrv, o["cho"])
    assert k["status"] == 504 and "CÓ THỂ đã chạy" in k["body"]["loi"]
    assert be.dem("POST") == 1


@pytest.mark.parametrize("kieu", ["nho_giot", "nho_giot_ca"])
def test_nha_nho_giot_van_cat_dung_han_tong(be, kieu):
    be.tra[("GET", "/api/v2/cham")] = {kieu: 0.3, "raw": b'"' + b"a" * 200 + b'"'}
    t = time.monotonic()
    st, o = pw.goi_backend("GET", "/api/v2/cham", None, 1.5)
    dt = time.monotonic() - t
    assert st == 504 and 1.4 <= dt < 2.2, dt


# ---------------------------------------------------------------- BangLenh: L, trùng khoá, chỗ chạy
def test_lenh_L_trung_khoa_va_het_cho(vsrv, be):
    be.tra[("POST", "/api/v2/queue/3/post")] = {"cham": 1.5}
    st, _, a = goi(vsrv, "POST", "/p/api/v2/queue/3/post", {})
    assert st == 202 and a["trung"] is False
    assert goi(vsrv, "GET", f"/p/_kq/{a['cho']}")[2] == {"xong": False}
    st, _, b = goi(vsrv, "POST", "/p/api/v2/queue/3/post", {})
    assert st == 202 and b["cho"] == a["cho"] and b["trung"] is True
    st, _, c = goi(vsrv, "POST", "/p/api/v2/queue/3/post", {"khac": 1})
    assert st == 429 and "Đang có lệnh đăng/login khác" in c["loi"]
    st, _, c = goi(vsrv, "POST", "/p/api/v2/queue/4/run", {})
    assert st == 429
    k = cho_kq(vsrv, a["cho"])
    assert k["xong"] is True and k["status"] == 200 and k["body"]["path"] == "/api/v2/queue/3/post"
    assert be.dem("POST") == 1
    # đã xong → khoá nhả, bấm lại là lệnh mới
    st, _, d = goi(vsrv, "POST", "/p/api/v2/queue/3/post", {})
    assert st == 202 and d["cho"] != a["cho"] and d["trung"] is False


def test_lenh_S_trung_khoa_song_song_goi_backend_1_lan(vsrv, be):
    be.tra[("GET", "/api/v2/folders/")] = {"cham": 1.0, "body": {"ds": [1, 2]}}
    kq = []

    def mot():
        kq.append(goi(vsrv, "GET", "/p/api/v2/folders/?archived=0"))

    t1 = threading.Thread(target=mot); t1.start(); time.sleep(0.3)
    t2 = threading.Thread(target=mot); t2.start()
    t1.join(10); t2.join(10)
    assert [(s, o) for s, _, o in kq] == [(200, {"ds": [1, 2]})] * 2
    assert be.dem("GET", "/api/v2/folders/") == 1


def test_S_het_cho_429(vsrv, be, monkeypatch):
    monkeypatch.setitem(pw.CHO_CHAY, "S", 1)
    monkeypatch.setattr(pw, "HAN_CHO_DONG_BO", 0.2)
    be.tra[("GET", "/api/v2/a")] = {"cham": 1.0}
    assert goi(vsrv, "GET", "/p/api/v2/a")[0] == 202
    st, _, o = goi(vsrv, "GET", "/p/api/v2/b")
    assert st == 429 and o == {"loi": "Poster V2 đang bận"}
    assert be.dem("GET", "/api/v2/b") == 0


def test_bang_day_50_muc_429():
    b = pw.BangLenh()
    su_kien = threading.Event()
    try:
        for i in range(pw.BANG_TOI_DA):
            b._lenh[f"{i:032x}"] = pw._Lenh(ma=f"{i:032x}", khoa=("GET", f"/x{i}", ""), lop="S", bat_dau=0.0,
                                            toi_da_giay=1.0, tom_tat={})
        with pytest.raises(pw.DayCho):
            b.nhan(("GET", "/moi", ""), "S", lambda: (200, {}), {}, 1.0)
    finally:
        su_kien.set()


def _xong_luon(b: "pw.BangLenh", khoa, lop, kq=(200, {"ok": 1})) -> str:
    ma, trung = b.nhan(khoa, lop, lambda: kq, {}, 1.0)
    assert trung is False
    assert b.cho(ma, 5) == kq
    return ma


def test_p3_2_200_get_khong_day_mat_ket_qua_lenh_ghi_nen():
    b = pw.BangLenh()
    ma_l = _xong_luon(b, ("POST", "/api/v2/queue/3/post", "h1"), "L", (200, {"dang": 1}))
    # lệnh ghi S chuyển nền rồi mới xong (client sẽ hỏi _kq)
    nha = threading.Event()
    ma_s, _ = b.nhan(("POST", "/api/v2/queue/unstick", "h2"), "S", lambda: (nha.wait(5), (201, {"g": 2}))[1],
                     {}, 1.0)
    assert b.cho(ma_s, 0.01) is None
    nha.set()
    assert b.cho(ma_s, 5) == (201, {"g": 2})
    for i in range(200):  # thanh trạng thái + Dashboard: GET xong đồng bộ
        _xong_luon(b, ("GET", f"/api/v2/stats/?i={i}", ""), "S")
    assert b.ket_qua(ma_l) == {"xong": True, "status": 200, "body": {"dang": 1}}
    assert b.ket_qua(ma_s) == {"xong": True, "status": 201, "body": {"g": 2}}
    assert len(b._lenh) <= pw.BANG_TOI_DA


def test_p3_2_don_cho_uu_tien_get_nen_truoc_lenh_ghi_nen():
    b = pw.BangLenh()
    bay_gio = time.monotonic()

    def them(i, method, xong_luc):
        ma = f"{i:032x}"
        b._lenh[ma] = pw._Lenh(ma=ma, khoa=(method, f"/x{i}", ""), lop="S", bat_dau=0.0, toi_da_giay=1.0,
                               tom_tat={}, ket_qua=(200, {}), xong_luc=xong_luc, nen=True)
        return ma

    ma_ghi = them(0, "POST", bay_gio - 100)  # xong lâu nhất
    for i in range(1, pw.BANG_TOI_DA):
        them(i, "GET", bay_gio - 50 + i)
    ma, _ = b.nhan(("GET", "/moi", ""), "S", lambda: (200, {}), {}, 1.0)
    b.cho(ma, 5)
    assert b.ket_qua(ma_ghi) is not None
    assert b.ket_qua(f"{1:032x}") is None  # GET nền xong cũ nhất bị dọn thay cho lệnh ghi


def test_p3_2_muc_S_con_nguoi_doi_khong_bi_don():
    b = pw.BangLenh()
    nha = threading.Event()
    khoa = ("GET", "/api/v2/folders/", "")
    ma, _ = b.nhan(khoa, "S", lambda: (nha.wait(5), (200, {"ds": 1}))[1], {}, 1.0)
    assert b.nhan(khoa, "S", lambda: (200, {}), {}, 1.0) == (ma, True)  # request thứ 2 gắn vào
    nha.set()
    assert b.cho(ma, 5) == (200, {"ds": 1})  # request 1 nhận xong; request 2 chưa kịp gọi cho()
    for i in range(200):
        _xong_luon(b, ("GET", f"/g{i}", ""), "S")
    assert b.cho(ma, 5) == (200, {"ds": 1})


def test_p3_2_bang_toan_muc_dang_chay_van_429_va_khoa_trung_giu():
    b = pw.BangLenh()
    nha = threading.Event()
    try:
        ma, _ = b.nhan(("POST", "/api/v2/queue/3/post", "h"), "L", lambda: (nha.wait(5), (200, {}))[1], {}, 1.0)
        for i in range(200):
            _xong_luon(b, ("GET", f"/g{i}", ""), "S")
        assert b.nhan(("POST", "/api/v2/queue/3/post", "h"), "L", lambda: (200, {}), {}, 1.0) == (ma, True)
        with pytest.raises(pw.DayCho):
            b.nhan(("POST", "/api/v2/queue/4/run", "h"), "L", lambda: (200, {}), {}, 1.0)
    finally:
        nha.set()
    assert b.cho(ma, 5) == (200, {})


def test_kq_liet_ke_va_tom_tat(vsrv, be, tmp_path):
    d = _b2(tmp_path, be)
    be.tra[("POST", "/api/v2/post/direct")] = {"cham": 1.5}
    be.tra[("POST", "/api/v2/accounts/login_and_capture")] = {"cham": 1.5}
    _, _, a = goi(vsrv, "POST", "/p/api/v2/post/direct",
                  {"folder_id": 7, "video_path": str(d / "a.mp4"), "caption": "bi-mat-caption"})
    _, _, b = goi(vsrv, "POST", "/p/api/v2/accounts/login_and_capture",
                  {"name": "acc1", "proxy": "http://u:mk-proxy@h", "cookies": [{"v": "cookie-bi-mat"}]})
    t = time.monotonic()
    st, _, o = goi(vsrv, "GET", "/p/_kq")
    assert st == 200 and time.monotonic() - t < 0.5   # khoá bảng không bị giữ khi gọi backend
    ds = {x["cho"]: x for x in o["dang_chay"]}
    assert set(ds) == {a["cho"], b["cho"]}
    pd = ds[a["cho"]]
    assert pd["method"] == "POST" and pd["path"] == "/api/v2/post/direct" and pd["lop"] == "L"
    assert pd["tom_tat"] == {"folder_id": 7, "video": "a.mp4"} and pd["toi_da_giay"] == 300.0
    assert ds[b["cho"]]["tom_tat"] == {"name": "acc1"} and ds[b["cho"]]["lop"] == "DN"
    assert isinstance(pd["giay_da_chay"], (int, float))
    lo = json.dumps(o)
    for bi_mat in ("cookie-bi-mat", "mk-proxy", "bi-mat-caption", TOKEN, str(d)):
        assert bi_mat.replace("\\", "\\\\") not in lo
    cho_kq(vsrv, a["cho"]); cho_kq(vsrv, b["cho"])
    assert goi(vsrv, "GET", "/p/_kq")[2] == {"dang_chay": []}


def test_kq_ma_la_404(vsrv):
    st, _, o = goi(vsrv, "GET", "/p/_kq/" + "0" * 32)
    assert st == 404 and "Không còn theo dõi được lệnh này" in o["loi"]
    assert goi(vsrv, "POST", "/p/_kq", {})[0] == 405


def test_khoa_bang_khong_bi_giu_khi_lenh_treo(vsrv, be):
    be.tra[("POST", "/api/v2/queue/3/post")] = {"cham": 2.0}
    goi(vsrv, "POST", "/p/api/v2/queue/3/post", {})
    for _ in range(3):
        t = time.monotonic()
        assert goi(vsrv, "GET", "/p/_kq")[0] == 200
        assert time.monotonic() - t < 0.5


def test_viec_nem_loi_thanh_500_khong_treo():
    b = pw.BangLenh()

    def hong():
        raise ValueError("hỏng")

    ma, trung = b.nhan(("GET", "/x", ""), "S", hong, {}, 1.0)
    assert b.cho(ma, 5) == (500, {"loi": "Lỗi nội bộ video_server (ValueError)"})
    assert b.dang_chay() == []


# ---------------------------------------------------------------- _video, _dem, _thong_tin
def test_video_liet_ke_dung_thu_tu(vsrv, be, tmp_path):
    d = tmp_path / "vf"
    (d / "con").mkdir(parents=True)
    for ten in ("a.mp4", "b.mov", "c.webm", "d.avi", "e.mkv", "x_posted.mp4", "okkkk1.mp4", "ghi.txt"):
        (d / ten).write_bytes(b"x" * 7)
    (d / "con" / "s.mp4").write_bytes(b"x")
    be.tra[("GET", "/api/v2/folders/9")] = {"body": {"id": 9, "path": str(d), "source": "local"}}
    st, _, o = goi(vsrv, "GET", "/p/_video/9")
    assert st == 200 and o["ho_tro"] is True
    assert [v["name"] for v in o["video"]] == ["a.mp4", "b.mov", "d.avi", "e.mkv", "c.webm"]
    assert o["video"][0] == {"name": "a.mp4", "path": str(d / "a.mp4"), "size": 7}


@pytest.mark.parametrize("folder,mong", [
    ({"path": "E:\\x", "source": "drive"}, {"ho_tro": False, "video": []}),
    ({"path": "", "source": "local"}, {"ho_tro": False, "video": []}),
    ({"path": "\\\\host\\share", "source": "local"}, {"ho_tro": False, "video": []}),
    ({"path": "//host/share", "source": "local"}, {"ho_tro": False, "video": []}),
])
def test_video_khong_ho_tro(vsrv, be, folder, mong):
    be.tra[("GET", "/api/v2/folders/9")] = {"body": folder}
    assert goi(vsrv, "GET", "/p/_video/9")[::2] == (200, mong)


def test_video_thu_muc_khong_co_va_folder_404(vsrv, be, tmp_path):
    be.tra[("GET", "/api/v2/folders/9")] = {"body": {"path": str(tmp_path / "khong"), "source": "local"}}
    assert goi(vsrv, "GET", "/p/_video/9")[::2] == (200, {"ho_tro": True, "video": []})
    be.tra[("GET", "/api/v2/folders/9")] = {"status": 404, "body": {"detail": "Folder not found"}}
    assert goi(vsrv, "GET", "/p/_video/9")[::2] == (404, {"detail": "Folder not found"})


def test_video_quet_qua_han_504(vsrv, be, tmp_path, monkeypatch):
    monkeypatch.setattr(pw, "HAN_QUET_DIA", 0.3)
    monkeypatch.setattr(pw, "ds_video", lambda f: (time.sleep(1.0), {"ho_tro": True, "video": []})[1])
    be.tra[("GET", "/api/v2/folders/9")] = {"body": {"path": str(tmp_path), "source": "local"}}
    st, _, o = goi(vsrv, "GET", "/p/_video/9")
    assert st == 504 and o == {"loi": "Quét thư mục quá 30 s"}


def test_dem_video(vsrv, be, tmp_path):
    d = tmp_path / "dem"
    d.mkdir()
    for ten in ("a.mp4", "b.MOV", "c.avi", "d.webm", "e.mkv", "f.txt"):
        (d / ten).write_bytes(b"x")
    assert goi(vsrv, "POST", "/p/_dem", {"duong_dan": str(d)})[::2] == (200, {"ton_tai": True, "so_video": 4})
    assert goi(vsrv, "POST", "/p/_dem", {"duong_dan": str(d / "khong")})[::2] == (200, {"ton_tai": False, "so_video": 0})
    assert goi(vsrv, "POST", "/p/_dem", {"duong_dan": "E:/" + "a" * 400})[0] == 400
    assert goi(vsrv, "POST", "/p/_dem", {"khac": 1})[0] == 400
    assert goi(vsrv, "GET", "/p/_dem")[0] == 405
    assert be.dem() == 0


def test_dem_qua_han_504(vsrv, monkeypatch, tmp_path):
    monkeypatch.setattr(pw, "HAN_QUET_DIA", 0.3)
    monkeypatch.setattr(pw, "dem_video", lambda s: (time.sleep(1.0), {})[1])
    st, _, o = goi(vsrv, "POST", "/p/_dem", {"duong_dan": str(tmp_path)})
    assert st == 504


def test_thong_tin_khong_co_token(vsrv, be, moi_truong):
    st, _, o = goi(vsrv, "GET", "/p/_thong_tin")
    assert st == 200
    assert o == {"backend": f"http://127.0.0.1:{be.port}", "co_token": True, "thu_muc": str(moi_truong),
                 "database": str(moi_truong / "v2_data.db"), "profiles": str(moi_truong / "profiles_v2")}
    assert be.dem() == 0


# ---------------------------------------------------------------- nhật ký, công tắc
def test_nhat_ky_moi_lenh_ghi_mot_dong(vsrv, be, tmp_path):
    goi(vsrv, "GET", "/p/api/v2/stats/", headers={"x-poster-boi": "nhan"})
    goi(vsrv, "POST", "/p/api/v2/folders/3/post_now", {"visibility": "gia-tri-bi-mat"},
        headers={"x-poster-boi": "nhan"})
    goi(vsrv, "POST", "/p/_dem", {"duong_dan": str(tmp_path)}, headers={"x-poster-boi": "nhan"})
    ds = doc_nhat_ky(tmp_path)
    assert len(ds) == 2, ds
    m = ds[0]
    assert m["boi"] == "nhan" and m["method"] == "POST" and m["path"] == "/api/v2/folders/3/post_now"
    assert m["status"] == 200 and m["trung"] is False and m["khoa_body"] == ["visibility"]
    assert m["body_sha256"] == hashlib.sha256(json.dumps({"visibility": "gia-tri-bi-mat"}).encode()).hexdigest()
    assert {"luc", "query", "ms", "cho"} <= set(m)
    assert ds[1]["path"] == "/_dem"
    assert "gia-tri-bi-mat" not in json.dumps(ds) and str(tmp_path).replace("\\", "\\\\") not in json.dumps(ds)


def test_nhat_ky_lenh_nen_co_dong_chuyen_nen_va_ket_thuc(vsrv, be, tmp_path, han_ngan):
    be.tra[("POST", "/api/v2/queue/3/post")] = {"cham": 0.5}
    _, _, a = goi(vsrv, "POST", "/p/api/v2/queue/3/post", {})
    _, _, b = goi(vsrv, "POST", "/p/api/v2/queue/3/post", {})
    cho_kq(vsrv, a["cho"])
    be.tra[("POST", "/api/v2/queue/unstick")] = {"cham": 0.8}
    _, _, c = goi(vsrv, "POST", "/p/api/v2/queue/unstick", {})
    cho_kq(vsrv, c["cho"])
    time.sleep(0.3)  # dòng ket_thuc ghi ngay sau khi kết quả được công bố
    ds = doc_nhat_ky(tmp_path)
    su = [(x.get("su_kien"), x.get("cho"), x.get("trung")) for x in ds]
    assert ("yeu_cau", a["cho"], False) in su and ("yeu_cau", a["cho"], True) in su
    assert ("ket_thuc", a["cho"], None) in su
    assert ("chuyen_nen", c["cho"], None) in su and ("ket_thuc", c["cho"], None) in su


def test_ghi_nhat_ky_loi_khong_hong_request(vsrv, be, tmp_path, monkeypatch, capfd):
    (tmp_path / "la-thu-muc").mkdir()
    monkeypatch.setenv("KHO_POSTER_NHAT_KY", str(tmp_path / "la-thu-muc"))
    assert goi(vsrv, "POST", "/p/api/v2/queue/unstick", {})[0] == 200
    assert "NHAT KY LOI" in capfd.readouterr().out


def test_nhat_ky_xoay_vong_5mb(tmp_path, monkeypatch):
    f = tmp_path / "nk" / "nhat-ky.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
    pw.ghi_nhat_ky({"a": 1})
    assert (tmp_path / "nk" / "nhat-ky.jsonl.1").stat().st_size == 5 * 1024 * 1024 + 1
    assert json.loads(f.read_text(encoding="utf-8")) == {"a": 1}


@pytest.mark.skipif(sys.platform != "win32", reason="khoá đổi tên file đang mở chỉ có trên Windows")
def test_p2_1_file_nhat_ky_bi_khoa_van_ghi_dong(tmp_path, monkeypatch, capfd):
    monkeypatch.setattr(pw, "NHAT_KY_TOI_DA", 100)
    monkeypatch.setattr(pw, "_xoay_nghi_den", 0.0)
    f = tmp_path / "nk" / "nhat-ky.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x" * 200)
    with open(f, "rb"):  # trình xem log / antivirus giữ file
        for i in range(3):
            pw.ghi_nhat_ky({"i": i})
    du = f.read_bytes()
    assert du[:200] == b"x" * 200
    assert [json.loads(x) for x in du[200:].decode("utf-8").splitlines()] == [{"i": 0}, {"i": 1}, {"i": 2}]
    assert not (tmp_path / "nk" / "nhat-ky.jsonl.1").exists()
    assert "NHAT KY LOI" in capfd.readouterr().out
    # hết khoá + hết thời gian nghỉ → lần sau xoay vòng bình thường
    monkeypatch.setattr(pw, "_xoay_nghi_den", 0.0)
    pw.ghi_nhat_ky({"i": 3})
    assert (tmp_path / "nk" / "nhat-ky.jsonl.1").stat().st_size == len(du)
    assert json.loads(f.read_text(encoding="utf-8")) == {"i": 3}


def test_p2_1_doi_ten_loi_tam_thoi_thu_lai_roi_xoay(tmp_path, monkeypatch):
    monkeypatch.setattr(pw, "NHAT_KY_TOI_DA", 10)
    monkeypatch.setattr(pw, "XOAY_CHO", (0.0, 0.0, 0.0))
    monkeypatch.setattr(pw, "_xoay_nghi_den", 0.0)
    f = tmp_path / "nk" / "nhat-ky.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x" * 20)
    that = pw.os.replace
    lan = []

    def doi_ten(a, b):
        lan.append(1)
        if len(lan) < 3:
            raise PermissionError(32, "đang bị khoá")
        return that(a, b)

    monkeypatch.setattr(pw.os, "replace", doi_ten)
    pw.ghi_nhat_ky({"a": 1})
    assert len(lan) == 3
    assert (tmp_path / "nk" / "nhat-ky.jsonl.1").read_bytes() == b"x" * 20
    assert json.loads(f.read_text(encoding="utf-8")) == {"a": 1}


def test_p2_1_doi_ten_loi_mai_thi_nghi_khong_thu_moi_lan(tmp_path, monkeypatch, capfd):
    monkeypatch.setattr(pw, "NHAT_KY_TOI_DA", 10)
    monkeypatch.setattr(pw, "XOAY_CHO", (0.0, 0.0))
    monkeypatch.setattr(pw, "_xoay_nghi_den", 0.0)
    f = tmp_path / "nk" / "nhat-ky.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x" * 20)
    lan = []

    def doi_ten(a, b):
        lan.append(1)
        raise PermissionError(32, "đang bị khoá")

    monkeypatch.setattr(pw.os, "replace", doi_ten)
    for i in range(5):
        pw.ghi_nhat_ky({"i": i})
    assert len(lan) == 3  # 1 lần đầu + 2 lần thử lại, các lần ghi sau trong thời gian nghỉ không thử nữa
    assert [json.loads(x) for x in f.read_bytes()[20:].decode("utf-8").splitlines()] == [{"i": i} for i in range(5)]
    out = capfd.readouterr().out
    assert out.count("NHAT KY LOI") == 1 and "PermissionError" in out


def test_p3_1_ket_thuc_co_status_khong_co_body():
    su = []
    b = pw.BangLenh(lambda ten, mt: su.append((ten, mt)))
    ma, _ = b.nhan(("POST", "/api/v2/queue/3/post", "h"), "L", lambda: (409, {"bi_mat": "body-bi-mat"}), {}, 1.0)
    assert b.cho(ma, 5) == (409, {"bi_mat": "body-bi-mat"})
    for _ in range(50):
        if su:
            break
        time.sleep(0.02)
    assert [t for t, _ in su] == ["ket_thuc"]
    assert su[0][1]["status"] == 409 and "body-bi-mat" not in json.dumps(su)


def test_p3_1_nhat_ky_ket_thuc_ghi_status(vsrv, be, tmp_path, han_ngan):
    be.tra[("POST", "/api/v2/queue/unstick")] = {"cham": 0.8, "status": 500, "body": {"detail": "body-bi-mat"}}
    _, _, c = goi(vsrv, "POST", "/p/api/v2/queue/unstick", {})
    assert cho_kq(vsrv, c["cho"])["status"] == 500
    time.sleep(0.3)
    ds = doc_nhat_ky(tmp_path)
    kt = [x for x in ds if x.get("su_kien") == "ket_thuc" and x["cho"] == c["cho"]]
    assert len(kt) == 1 and kt[0]["status"] == 500
    cn = [x for x in ds if x.get("su_kien") == "chuyen_nen"]
    assert cn and "status" not in cn[0]
    assert "body-bi-mat" not in json.dumps(ds)


def test_cong_tac_tat_sau_import_503(vsrv, be, monkeypatch):
    monkeypatch.setenv("KHO_POSTER_WEB", "0")
    for m, p, b in (("GET", "/p/api/v2/stats/", None), ("POST", "/p/_dem", {"duong_dan": "E:/x"}),
                    ("GET", "/p/_kq", None), ("DELETE", "/p/api/v2/queue/3", None)):
        st, _, o = goi(vsrv, m, p, b)
        assert st == 503 and o == {"loi": "Poster trên web đang tắt ở máy nhà"}
    assert be.dem() == 0


# ---------------------------------------------------------------- POST /p/_bat_backend
class _ProcGia:
    def __init__(self, pid=4321):
        self.pid = pid

    def poll(self):
        return None


@pytest.fixture
def bat_gia(monkeypatch):
    goi_mo = []

    def mo(lenh, cwd, env):
        goi_mo.append({"lenh": lenh, "cwd": cwd, "env": env})
        return _ProcGia()
    monkeypatch.setattr(pw, "_mo_tien_trinh", mo)
    monkeypatch.setattr(pw, "_DA_BAT", {"proc": None, "luc": 0.0})
    monkeypatch.setattr(pw, "ai_giu_cong", lambda port: "relay.exe (PID 77)")
    return goi_mo


def _cong_trong() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    return port


def test_bat_backend_cong_trong_thi_mo_dung_lenh_va_cong(vsrv, moi_truong, monkeypatch, bat_gia):
    port = _cong_trong()
    monkeypatch.setenv("TT_API_PORT", str(port))
    st, _, o = goi(vsrv, "POST", "/p/_bat_backend", {})
    assert st == 200 and o == {"trang_thai": "dang_bat", "pid": 4321}
    assert len(bat_gia) == 1
    m = bat_gia[0]
    assert m["lenh"][1:] == ["-B", "-m", "src.backend.main"]
    assert Path(m["cwd"]) == moi_truong
    assert m["env"]["API_PORT"] == str(port) and m["env"]["TT_API_PORT"] == str(port)
    # bấm lại ngay: không mở tiến trình thứ hai
    st, _, o = goi(vsrv, "POST", "/p/_bat_backend", {})
    assert st == 200 and o == {"trang_thai": "dang_bat"} and len(bat_gia) == 1


def test_bat_backend_poster_dang_chay_thi_khong_mo(vsrv, be, bat_gia):
    be.tra[("GET", "/health")] = {"status": 200, "body": {"status": "healthy", "version": "2.0.0"}}
    st, _, o = goi(vsrv, "POST", "/p/_bat_backend", {})
    assert st == 200 and o == {"trang_thai": "da_chay"} and bat_gia == []


def test_bat_backend_cong_bi_chuong_trinh_khac_chiem_409(vsrv, be, bat_gia):
    be.tra[("GET", "/health")] = {"status": 502, "body": {"loi": "Máy nhà không trả lời"}}
    st, _, o = goi(vsrv, "POST", "/p/_bat_backend", {})
    assert st == 409 and o["ma"] == "cong_la" and "relay.exe (PID 77)" in o["loi"] and bat_gia == []


def test_bat_backend_get_405_va_thieu_body_400(vsrv, moi_truong, bat_gia):
    assert goi(vsrv, "GET", "/p/_bat_backend")[0] == 405
    assert bat_gia == []


def test_bat_backend_cong_that_bi_chan_khi_test(vsrv, moi_truong, monkeypatch, bat_gia):
    monkeypatch.setenv("TT_API_PORT", "8023")
    st, _, o = goi(vsrv, "POST", "/p/_bat_backend", {})
    assert st == 500 and bat_gia == []
