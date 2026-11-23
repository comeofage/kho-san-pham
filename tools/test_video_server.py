"""Test video_server.py — chạy server thật trên cổng ngẫu nhiên với thư mục giả trong tmp_path.

Chạy: PYTHONIOENCODING=utf-8 python -B -m pytest tools/test_video_server.py -q
Không gọi mạng ngoài, không đụng cổng 8787/3786/7890/8023 thật.
"""
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlsplit

import pytest

_spec = importlib.util.spec_from_file_location("video_server", Path(__file__).with_name("video_server.py"))
vs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vs)

ID = "1731141980888533631"
KHOA = "khoa-test-123"


def _ghi(p: Path, n: int = 10) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(bytes(range(n)))
    return p


@pytest.fixture
def goc(tmp_path, monkeypatch):
    g = tmp_path / "goc"
    d = g / f"abc {ID}"
    _ghi(d / "raw" / "a.mp4"); _ghi(d / "raw" / "b.MOV"); _ghi(d / "raw" / "ghi-chu.txt")
    _ghi(d / "voice" / "v1.mp3"); _ghi(d / "voice" / "v2.wav"); _ghi(d / "voice" / "v3.mp4")
    _ghi(d / "output_poster" / "01.mp4", 100); _ghi(d / "output_poster" / "02.mp4", 50)
    (d / "raw" / "con").mkdir()
    _ghi(d / "raw" / "con" / "sau.mp4")  # không đệ quy
    # thư mục mới quay, chưa có output gì
    _ghi(g / f"moi {ID}" / "raw" / "x.mp4")
    g2 = tmp_path / "goc2"; g2.mkdir()
    monkeypatch.setattr(vs, "GOCS", [g, g2, tmp_path / "khong-ton-tai"])
    monkeypatch.setattr(vs, "GOC", g)
    monkeypatch.setattr(vs, "DY_GOC", tmp_path / "dy")
    return g


@pytest.fixture
def srv(goc, monkeypatch):
    monkeypatch.setattr(vs.H, "khoa", KHOA)
    s = ThreadingHTTPServer(("127.0.0.1", 0), vs.H)
    monkeypatch.setattr(vs.H, "cong", s.server_address[1])
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{s.server_address[1]}"
    finally:
        s.shutdown()
        s.server_close()
        t.join(5)


def goi(url, khoa=KHOA, method="GET", headers=None):
    h = dict(headers or {})
    if khoa is not None:
        h["x-key"] = khoa
    req = urllib.request.Request(url, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict((k.lower(), v) for k, v in r.headers.items()), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict((k.lower(), v) for k, v in e.headers.items()), e.read()


# ---------- khoá ----------

@pytest.mark.parametrize("khoa", [None, "sai"])
@pytest.mark.parametrize("duong", ["/suc-khoe", f"/v/{ID}/tien-do", f"/v/{ID}/xem?ten=01.mp4"])
def test_sai_hoac_thieu_khoa_401(srv, khoa, duong):
    code, _, body = goi(srv + duong, khoa=khoa)
    assert code == 401
    assert json.loads(body) == {"loi": "Sai khoá"}


def test_duong_dan_la_404_va_post_moi_405(srv):
    assert goi(srv + f"/v/{ID}/linh-tinh")[0] == 404
    assert goi(srv + "/v/abc/tien-do")[0] == 404
    assert goi(srv + f"/v/{ID}/tien-do", method="POST")[0] == 405
    assert goi(srv + f"/v/{ID}/xem?ten=01.mp4", method="POST")[0] == 405
    assert goi(srv + "/suc-khoe", method="POST")[0] == 405


# ---------- tien-do ----------

def test_tien_do_dem_dung(srv, goc):
    code, _, body = goi(srv + f"/v/{ID}/tien-do")
    assert code == 200
    tm = json.loads(body)["thu_muc"]
    assert [x["ten"] for x in tm] == [f"abc {ID}", f"moi {ID}"]
    a, m = tm
    assert a == {"goc": goc.as_posix(), "ten": f"abc {ID}", "raw": 2, "takes": 0, "cuts": 0, "muse": 0,
                 "voice": 2, "output_poster": 2, "output": 0}
    assert m == {"goc": goc.as_posix(), "ten": f"moi {ID}", "raw": 1, "takes": 0, "cuts": 0, "muse": 0,
                 "voice": 0, "output_poster": 0, "output": 0}


def test_tien_do_id_khong_co_thu_muc(srv):
    code, _, body = goi(srv + "/v/1111111111111111111/tien-do")
    assert code == 200
    assert json.loads(body) == {"thu_muc": []}


# ---------- xem ----------

def test_xem_range_206_khong_xoa_khong_attachment(srv, goc):
    f = goc / f"abc {ID}" / "output_poster" / "01.mp4"
    code, h, body = goi(srv + f"/v/{ID}/xem?goc={quote(goc.as_posix())}&ten=01.mp4&xoa=1",
                        headers={"Range": "bytes=0-1"})
    assert code == 206
    assert body == bytes([0, 1])
    assert h["content-range"] == "bytes 0-1/100"
    assert "content-disposition" not in h
    code, h, body = goi(srv + f"/v/{ID}/xem?ten=01.mp4&xoa=1")
    assert code == 200 and len(body) == 100
    assert "content-disposition" not in h
    time.sleep(0.3)
    assert f.is_file()


def test_xem_khong_thay_404(srv):
    code, _, body = goi(srv + f"/v/{ID}/xem?ten=khong-co.mp4")
    assert code == 404
    assert json.loads(body) == {"loi": "Không thấy video"}


# ---------- ds ----------

def test_ds_co_chi_tiet_va_giu_truong_cu(srv, goc):
    f1 = goc / f"abc {ID}" / "output_poster" / "01.mp4"
    code, _, body = goi(srv + f"/v/{ID}/ds")
    assert code == 200
    j = json.loads(body)
    assert j["tong"] == 2 and j["ten"] == "01.mp4" and j["mb"] == 0.0 and j["co_folder"] is True
    ng = j["nguon"]
    assert len(ng) == 1
    n = ng[0]
    assert n["goc"] == goc.as_posix() and n["tong"] == 2 and n["ten"] == "01.mp4" and n["ds"] == ["01.mp4", "02.mp4"]
    assert [c["ten"] for c in n["chi_tiet"]] == n["ds"]
    c = n["chi_tiet"][0]
    assert isinstance(c["sua_luc"], int) and c["sua_luc"] == int(f1.stat().st_mtime)
    assert c["mb"] == 0.0


def _bien_mat_sau_liet_ke(monkeypatch, *files):
    """ds_nguon liệt kê xong thì các file này bị xoá (giả lập request khác vừa xoá giữa lúc liệt kê và stat)."""
    goc_ds = vs.ds_nguon

    def gia(id_):
        kq = goc_ds(id_)
        for f in files:
            f.unlink()
        return kq

    monkeypatch.setattr(vs, "ds_nguon", gia)


def test_ds_bo_qua_file_vua_bi_xoa_giu_ds_khop_chi_tiet(srv, goc, monkeypatch):
    op = goc / f"abc {ID}" / "output_poster"
    _bien_mat_sau_liet_ke(monkeypatch, op / "01.mp4")
    code, _, body = goi(srv + f"/v/{ID}/ds")
    assert code == 200
    j = json.loads(body)
    assert j["tong"] == 1 and j["ten"] == "02.mp4" and j["mb"] == 0.0
    n = j["nguon"][0]
    assert n["tong"] == 1 and n["ten"] == "02.mp4" and n["ds"] == ["02.mp4"]
    assert [c["ten"] for c in n["chi_tiet"]] == n["ds"]


def test_ds_moi_file_cua_mot_nguon_bien_mat_thi_bo_nguon(srv, goc, monkeypatch):
    op = goc / f"abc {ID}" / "output_poster"
    _bien_mat_sau_liet_ke(monkeypatch, op / "01.mp4", op / "02.mp4")
    code, _, body = goi(srv + f"/v/{ID}/ds")
    assert code == 200
    j = json.loads(body)
    assert j["tong"] == 0 and j["ten"] is None and j["mb"] == 0 and j["nguon"] == []
    assert j["co_folder"] is True


# ---------- suc-khoe ----------

def test_suc_khoe_cong_mo_dong(srv, monkeypatch):
    nghe = socket.socket(); nghe.bind(("127.0.0.1", 0)); nghe.listen(5)
    dong = socket.socket(); dong.bind(("127.0.0.1", 0)); cong_dong = dong.getsockname()[1]; dong.close()
    try:
        monkeypatch.setattr(vs, "APPS", [("muse", "Video Batch Local (Muse)", nghe.getsockname()[1]),
                                         ("perfectvoice", "PerfectVoice", cong_dong),
                                         ("poster", "TikTok Poster V2", cong_dong)])
        t0 = time.monotonic()
        code, _, body = goi(srv + "/suc-khoe")
        assert time.monotonic() - t0 < 4
    finally:
        nghe.close()
    assert code == 200
    j = json.loads(body)
    assert isinstance(j["luc"], str) and "T" in j["luc"]
    apps = {a["ma"]: a for a in j["apps"]}
    assert [a["ma"] for a in j["apps"]] == ["muse", "perfectvoice", "poster", "video_server"]
    assert apps["muse"]["song"] is True
    assert apps["perfectvoice"]["song"] is False and apps["poster"]["song"] is False
    assert apps["video_server"] == {"ma": "video_server", "ten": "Máy phát video",
                                    "cong": int(srv.rsplit(":", 1)[1]), "song": True}


def test_apps_mac_dinh_dung_hop_dong():
    assert vs.APPS == [("muse", "Video Batch Local (Muse)", 3786), ("perfectvoice", "PerfectVoice", 7890),
                       ("poster", "TikTok Poster V2", 8023), ("runner", "Bộ chạy việc", 8788)]


# ---------- hành vi cũ ----------

def test_file_xoa_1_van_xoa_sau_khi_gui_tron(srv, goc):
    f = goc / f"abc {ID}" / "output_poster" / "02.mp4"
    code, h, body = goi(srv + f"/v/{ID}/file?ten=02.mp4&xoa=1")
    assert code == 200 and len(body) == 50
    assert h["content-disposition"].startswith("attachment")
    for _ in range(50):
        if not f.exists():
            break
        time.sleep(0.05)
    assert not f.exists()
    assert (goc / f"abc {ID}" / "output_poster" / "01.mp4").is_file()


# ---------- chuyển tiếp /r/* sang runner (§3.2) ----------
# Runner GIẢ trên cổng ngẫu nhiên; KHÔNG BAO GIỜ gọi 127.0.0.1:8788 thật.

JID = "j20261117093000ab12"


class _RunnerGia(BaseHTTPRequestHandler):
    nhan: list = []          # fixture tạo lớp con với list mới mỗi test
    tra_code = 200
    tra_body = b'{"ok": true}'
    tra_header: dict = {}
    ngu = 0.0

    def log_message(self, *a):
        pass

    def _xu_ly(self):
        n = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(n) if n else b""
        type(self).nhan.append({"method": self.command, "path": self.path,
                                "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
        if type(self).ngu:
            time.sleep(type(self).ngu)
        self.send_response(type(self).tra_code)
        self.send_header("content-type", "application/json; charset=utf-8")
        for k, v in type(self).tra_header.items():
            self.send_header(k, v)
        self.send_header("content-length", str(len(type(self).tra_body)))
        self.end_headers()
        self.wfile.write(type(self).tra_body)

    do_GET = do_POST = do_PUT = _xu_ly


@pytest.fixture
def runner(monkeypatch):
    class R(_RunnerGia):
        nhan = []
        tra_header = {}
    s = ThreadingHTTPServer(("127.0.0.1", 0), R)
    cong = s.server_address[1]
    assert cong != 8788
    monkeypatch.setattr(vs, "RUNNER_ORIGIN", f"http://127.0.0.1:{cong}")
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    try:
        yield R
    finally:
        s.shutdown()
        s.server_close()
        t.join(5)


@pytest.fixture(autouse=True)
def _khong_bao_gio_goi_8788(monkeypatch):
    """Mặc định trỏ runner tới cổng đã đóng — test quên fixture `runner` cũng không chạm 8788 thật."""
    monkeypatch.setattr(vs, "RUNNER_ORIGIN", f"http://127.0.0.1:{_cong_dong()}")


def _cong_dong() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); c = s.getsockname()[1]; s.close()
    return c


def goi_r(url, khoa=KHOA, method="GET", headers=None, body=None):
    h = dict(headers or {})
    if khoa is not None:
        h["x-key"] = khoa
    req = urllib.request.Request(url, method=method, headers=h, data=body)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, dict((k.lower(), v) for k, v in r.headers.items()), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict((k.lower(), v) for k, v in e.headers.items()), e.read()


def test_runner_origin_mac_dinh_dung_hop_dong():
    sach = {k: v for k, v in os.environ.items() if k != "KHO_RUNNER_ORIGIN"}
    out = subprocess.run([sys.executable, "-B", "-c",
                          "import importlib.util,sys;s=importlib.util.spec_from_file_location('v',sys.argv[1]);"
                          "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                          "print(m.RUNNER_ORIGIN, m.RUNNER_TIMEOUT)", str(Path(vs.__file__))],
                         capture_output=True, text=True, env=sach, timeout=30)
    assert out.stdout.split() == ["http://127.0.0.1:8788", "10"], out.stderr


@pytest.mark.parametrize("duong", [
    "/r/suc-khoe", "/r/danh-muc", "/r/poster/folders", "/r/du-an/1731141980888533631",
    "/r/viec", f"/r/viec/{JID}", f"/r/viec/{JID}/log",
])
def test_r_get_hop_le_chuyen_tiep_bo_tien_to(srv, runner, duong):
    code, h, body = goi_r(srv + duong)
    assert code == 200 and json.loads(body) == {"ok": True}
    assert h["content-type"].startswith("application/json")
    assert len(runner.nhan) == 1
    assert runner.nhan[0]["method"] == "GET" and runner.nhan[0]["path"] == duong[2:]


@pytest.mark.parametrize("duong", [
    "/r", "/r/", "/r/linh-tinh", "/r/suc-khoe/", "/r/du-an/123", "/r/du-an/17311419808885336310",
    "/r/viec/j2026111709300AB12", f"/r/viec/{JID}/xoa", f"/r/viec/{JID}/log/x", "/r/../v/1/ds",
    "/r/viec%2Fj20261117093000ab12", "/r/poster/folders/x", "/rr/suc-khoe", "/r/viec/",
])
def test_r_path_ngoai_regex_404_khong_goi_runner(srv, runner, duong):
    code, _, _ = goi_r(srv + duong)
    assert code == 404
    # body rỗng: server từ chối trước khi đọc body (đóng kết nối) -> body thật dễ bị WinError 10053 phía client
    code, _, _ = goi_r(srv + duong, method="POST", headers={"content-type": "application/json"}, body=b"")
    assert code in (404, 405)
    assert runner.nhan == []


@pytest.mark.parametrize("khoa", [None, "sai"])
def test_r_thieu_sai_x_key_401_khong_goi_runner(srv, runner, khoa):
    code, _, body = goi_r(srv + "/r/suc-khoe", khoa=khoa, headers={"x-runner-key": "rk"})
    assert code == 401 and json.loads(body) == {"loi": "Sai khoá"}
    code, _, _ = goi_r(srv + f"/r/viec/{JID}/huy", khoa=khoa, method="POST",
                       headers={"content-type": "application/json"}, body=b"")
    assert code == 401
    assert runner.nhan == []


def test_r_query_chi_giu_khoa_va_gia_tri_hop_le(srv, runner):
    q = ("trang_thai=cho,loi&uid=1731141980888533631&gioi_han=20&tom_tat=1&tu=0"
         "&" + quote("lạ") + "=1&x-key=abc&gioi_han2=5&uid=%27%3Bdrop&tom_tat=" + "a" * 41)
    code, _, _ = goi_r(srv + "/r/viec?" + q)
    assert code == 200
    sp = urlsplit(runner.nhan[0]["path"])
    assert sp.path == "/viec"
    assert parse_qsl(sp.query, keep_blank_values=True) == [
        ("trang_thai", "cho,loi"), ("uid", "1731141980888533631"), ("gioi_han", "20"), ("tom_tat", "1"), ("tu", "0")]


def test_r_query_gia_tri_co_xuong_dong_bi_bo(srv, runner):
    goi_r(srv + "/r/viec/" + JID + "/log?tu=0%0A&uid=1%0D%0Ax")
    assert runner.nhan[0]["path"] == f"/viec/{JID}/log"


def test_r_query_toan_khoa_la_khong_them_dau_hoi(srv, runner):
    goi_r(srv + "/r/viec?la=1")
    assert runner.nhan[0]["path"] == "/viec"


def test_r_query_giu_offset(srv, runner):
    goi_r(srv + "/r/viec?offset=20&la=1")
    sp = urlsplit(runner.nhan[0]["path"])
    assert sp.path == "/viec"
    assert parse_qsl(sp.query, keep_blank_values=True) == [("offset", "20")]


def test_r_chi_chuyen_header_cho_phep(srv, runner):
    hdr = {"x-runner-key": "rk-1", "x-ky": "kyabc", "x-ky-ngay": "1763340000000", "x-ky-nonce": "ab" * 16,
           "content-type": "application/json", "cookie": "phien=1", "authorization": "Bearer t",
           "x-forwarded-for": "1.2.3.4", "x-ky-khac": "z", "connection": "close",
           "cf-connecting-ip": "1.2.3.4", "te": "trailers", "upgrade": "websocket"}
    body = json.dumps({"boi": "nhan"}).encode()
    code, _, _ = goi_r(srv + f"/r/viec/{JID}/chay-tiep", method="POST", headers=hdr, body=body)
    assert code == 200
    g = runner.nhan[0]
    assert g["method"] == "POST" and g["path"] == f"/viec/{JID}/chay-tiep"
    assert g["body"] == body
    h = g["headers"]
    for k in ("x-runner-key", "x-ky", "x-ky-ngay", "x-ky-nonce", "content-type"):
        assert h[k] == hdr[k], k
    for k in ("x-key", "cookie", "authorization", "x-forwarded-for", "x-ky-khac", "cf-connecting-ip", "te", "upgrade"):
        assert k not in h, k
    assert KHOA not in json.dumps(h)


def test_r_get_khong_chuyen_body(srv, runner):
    goi_r(srv + "/r/suc-khoe", headers={"x-runner-key": "rk"})
    g = runner.nhan[0]
    assert g["headers"]["x-runner-key"] == "rk" and "x-key" not in g["headers"]
    assert g["body"] == b""


def test_r_post_body_qua_16kb_413(srv, runner):
    lon = b'{"a":"' + b"x" * (16 * 1024) + b'"}'
    code, _, body = goi_r(srv + "/r/viec", method="POST", headers={"content-type": "application/json"}, body=lon)
    assert code == 413 and "loi" in json.loads(body)
    vua = b'{"a":"' + b"x" * (16 * 1024 - 8) + b'"}'
    assert len(vua) == 16 * 1024
    code, _, _ = goi_r(srv + "/r/viec", method="POST", headers={"content-type": "application/json"}, body=vua)
    assert code == 200
    assert len(runner.nhan) == 1 and runner.nhan[0]["body"] == vua


def test_r_post_sai_content_type_415(srv, runner):
    for ct in ("text/plain", "application/jsonx", "application/x-www-form-urlencoded"):
        code, _, _ = goi_r(srv + "/r/viec", method="POST", headers={"content-type": ct}, body=b"{}")
        assert code == 415, ct
    assert runner.nhan == []
    code, _, _ = goi_r(srv + "/r/viec", method="POST",
                       headers={"content-type": "application/json; charset=utf-8"}, body=b"{}")
    assert code == 200


def _tho(srv, yeu_cau: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", int(srv.rsplit(":", 1)[1])), timeout=5) as s:
        s.sendall(yeu_cau)
        return s.recv(4096).split(b"\r\n", 1)[0]


def test_r_post_chunked_hoac_length_hong_khong_chuyen(srv, runner):
    dau = f"POST /r/viec HTTP/1.1\r\nHost: x\r\nx-key: {KHOA}\r\ncontent-type: application/json\r\n"
    assert b" 411 " in _tho(srv, (dau + "transfer-encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n\r\n").encode())
    assert b" 400 " in _tho(srv, (dau + "content-length: -5\r\n\r\n").encode())
    assert b" 400 " in _tho(srv, (dau + "content-length: abc\r\n\r\n").encode())
    assert b" 400 " in _tho(srv, (dau + "content-length: 1\xb2\r\n\r\n").encode("latin-1"))
    assert runner.nhan == []


def test_r_post_body_thieu_byte_408_khong_treo(srv, runner, monkeypatch):
    monkeypatch.setattr(vs, "RUNNER_TIMEOUT", 0.5)
    t0 = time.monotonic()
    dong = _tho(srv, (f"POST /r/viec HTTP/1.1\r\nHost: x\r\nx-key: {KHOA}\r\ncontent-type: application/json\r\n"
                      "content-length: 100\r\n\r\n{}").encode())
    assert b" 408 " in dong and time.monotonic() - t0 < 4
    assert runner.nhan == []


@pytest.mark.parametrize("dong_dau, ct, mong", [
    ("POST /r/viec", "application/json", b" 413 "),          # quá 16 KB -> _tu_choi đọc bỏ body
    ("POST /r/viec", "text/plain", b" 415 "),                # sai content-type -> _tu_choi
    ("POST /r/khong-co", "application/json", b" 404 "),      # path ngoài regex -> _tu_choi
])
def test_r_tu_choi_body_lon_client_im_khong_treo(srv, runner, monkeypatch, dong_dau, ct, mong):
    """Client khai content-length lớn (≤1 MB) rồi im: _tu_choi không được đọc bỏ body mãi (R-04 P3-9)."""
    monkeypatch.setattr(vs, "RUNNER_TIMEOUT", 0.5)
    t0 = time.monotonic()
    with socket.create_connection(("127.0.0.1", int(srv.rsplit(":", 1)[1])), timeout=5) as s:
        s.sendall((f"{dong_dau} HTTP/1.1\r\nHost: x\r\nx-key: {KHOA}\r\ncontent-type: {ct}\r\n"
                   "content-length: 500000\r\n\r\n{\"a\":").encode())
        try:
            dong = s.recv(4096).split(b"\r\n", 1)[0]
        except TimeoutError:
            pytest.fail("server treo khi đọc bỏ body (không có timeout)")
    assert mong in dong, dong
    assert time.monotonic() - t0 < 4
    assert runner.nhan == []


def test_r_method_khac_khong_chuyen(srv, runner):
    # body rỗng: stdlib trả 501 mà không đọc body -> gửi body thật thì client Windows có thể bị WinError 10053
    code, _, _ = goi_r(srv + "/r/viec", method="PUT", headers={"content-type": "application/json"}, body=b"")
    assert code in (405, 501)
    assert runner.nhan == []


def test_r_runner_tat_502(srv):
    code, _, body = goi_r(srv + "/r/suc-khoe")
    assert code == 502 and json.loads(body) == {"loi": "Bộ chạy việc chưa bật"}
    code, _, body = goi_r(srv + f"/r/viec/{JID}/chay-tiep", method="POST",
                          headers={"content-type": "application/json"}, body=b'{"boi":"nhan"}')
    assert code == 502 and json.loads(body) == {"loi": "Bộ chạy việc chưa bật"}


def test_r_runner_qua_gio_504(srv, runner, monkeypatch):
    monkeypatch.setattr(vs, "RUNNER_TIMEOUT", 0.5)
    runner.ngu = 2.0
    t0 = time.monotonic()
    code, _, body = goi_r(srv + "/r/suc-khoe")
    assert time.monotonic() - t0 < 1.9
    assert code == 504 and "loi" in json.loads(body)


def test_r_status_body_tra_nguyen_khong_lo_header_runner(srv, runner):
    runner.tra_code = 409
    runner.tra_body = json.dumps({"trung": "j1"}).encode()
    runner.tra_header = {"x-noi-bo": "1", "set-cookie": "a=b", "keep-alive": "timeout=5"}
    code, h, body = goi_r(srv + "/r/viec", method="POST", headers={"content-type": "application/json"}, body=b"{}")
    assert code == 409 and body == runner.tra_body
    assert h["content-length"] == str(len(body))
    for k in ("x-noi-bo", "set-cookie", "keep-alive"):
        assert k not in h


def test_r_body_runner_qua_1mb_502(srv, runner):
    runner.tra_body = b"x" * (1024 * 1024 + 1)
    code, _, body = goi_r(srv + "/r/suc-khoe")
    assert code == 502 and "loi" in json.loads(body)


def test_r_khong_lam_hong_route_cu(srv, runner, monkeypatch):
    monkeypatch.setattr(vs, "APPS", [("runner", "Bộ chạy việc", _cong_dong())])  # không dò cổng thật
    assert goi(srv + f"/v/{ID}/tien-do")[0] == 200
    assert goi(srv + "/suc-khoe")[0] == 200
    assert runner.nhan == []


# ---------- sửa video: chuyển tiếp /r/sua-video/* (docs/sua-video.md §8.2) ----------

UID = "1731141980888533631"
MA_V = "0123456789abcdef"


@pytest.mark.parametrize("duong", [
    f"/r/sua-video/{UID}", f"/r/sua-video/{UID}/{MA_V}",
    f"/r/sua-video/{UID}/{MA_V}/ung-vien", f"/r/sua-video/{UID}/{MA_V}/ban-sua",
])
def test_r_sua_video_4_dang_hop_le_chuyen_tiep(srv, runner, duong):
    code, _, body = goi_r(srv + duong)
    assert code == 200 and json.loads(body) == {"ok": True}
    assert runner.nhan[0]["path"] == duong[2:]


@pytest.mark.parametrize("duong", [
    "/r/sua-video", "/r/sua-video/", f"/r/sua-video/{UID}/", "/r/sua-video/123",
    f"/r/sua-video/{UID}0", f"/r/sua-video/{UID}/{MA_V[:15]}", f"/r/sua-video/{UID}/{MA_V}0",
    f"/r/sua-video/{UID}/{MA_V.upper()}", f"/r/sua-video/{UID}/{MA_V}/xoa",
    f"/r/sua-video/{UID}/{MA_V}/ung-vien/x", f"/r/sua-video/{UID}/{MA_V}/ban-sua/",
    f"/r/sua-video/{UID}/../{MA_V}", f"/r/sua-video/{UID}/{MA_V}/ung-vien%2F..",
    "/r/sua-video/" + quote("１７３１１４１９８０８８８５３３６３１"),
])
def test_r_sua_video_dang_khac_404(srv, runner, duong):
    assert goi_r(srv + duong)[0] == 404
    assert runner.nhan == []


def test_r_sua_video_ung_vien_giu_seg_bo_khoa_la(srv, runner):
    goi_r(srv + f"/r/sua-video/{UID}/{MA_V}/ung-vien?seg=12&du_an=abc&ten=x.mp4&seg=3")
    sp = urlsplit(runner.nhan[0]["path"])
    assert sp.path == f"/sua-video/{UID}/{MA_V}/ung-vien"
    assert parse_qsl(sp.query) == [("seg", "12")]


def test_r_sua_video_ban_sua_post_chuyen_body(srv, runner):
    body = json.dumps({"sua_luc": 1, "boi": "nhan"}).encode()
    code, _, _ = goi_r(srv + f"/r/sua-video/{UID}/{MA_V}/ban-sua", method="POST",
                       headers={"content-type": "application/json", "x-ky": "k"}, body=body)
    assert code == 200
    g = runner.nhan[0]
    assert g["method"] == "POST" and g["body"] == body and g["headers"]["x-ky"] == "k"


def test_r_van_giu_xin_duyet_lai(srv, runner):
    assert goi_r(srv + f"/r/viec/{JID}/xin-duyet-lai")[0] == 200


@pytest.mark.parametrize("act", ["luu-tru", "bo-luu-tru"])
def test_r_act_luu_tru_bo_luu_tru_chuyen_tiep(srv, runner, act):
    code, _, body = goi_r(srv + f"/r/viec/{JID}/{act}", method="POST",
                          headers={"content-type": "application/json"}, body=b"{}")
    assert code == 200 and json.loads(body) == {"ok": True}
    assert runner.nhan[0]["method"] == "POST" and runner.nhan[0]["path"] == f"/viec/{JID}/{act}"


# ---------- học tự động: chuyển tiếp /r/hoc/* (docs/hoc-tu-dong.md §3.8, HT-A1) ----------
HOP_DONG_HOC = """Trích nguyên văn docs/hoc-tu-dong.md §3.8 (hợp đồng chung 3 chặng):

| Method + path | Query/body | Trả |
|---|---|---|
| `GET /hoc/bao-cao` | `ngay` tuỳ chọn `^\\d{4}-\\d{2}-\\d{2}$` | 200 `BaoCao` · 404 `{"loi":"chưa có lần học nào"}` · 400 ngày sai |
| `GET /hoc/bai-hoc` | `gioi_han` 1..200, mặc định 50 | 200 `{"bai_hoc":[BaiHocRa…]}` |
| `POST /hoc/bai-hoc/<ma>/hoan-tac` | `{"boi"}` | 200 `{"bai_hoc"}` · 404 không có · 409 `{"loi":"bài học không còn hiệu lực"}` khi trạng thái ∉ {`ung_vien`,`hieu_luc`} · 401 |
| `POST /hoc/bai-hoc/<ma>/bat-lai` | `{"boi"}` | 200 `{"bai_hoc"}` · 404 · 409 kèm 1 trong 5 câu cố định (§4.2), gồm "đã quá 7 ngày kể từ lúc hoàn tác, không bật lại được nữa" khi bài `hoan_tac` quá hạn Q8 · 401 |

`<ma>` sai dạng thì không khớp tuyến → 404. **Hợp đồng mã lỗi thống nhất ở cả 3 chặng (sửa P3-7): `ma` sai dạng = 404**,
không phải 400 (Worker `tuyenHoc` trả null → 404; video_server `RE_R` không khớp → 404; runner regex route không khớp → 404).
`export const RE_MA_BAI_HOC = /^bh\\d{8}[a-z0-9]{4}$/;`
Worker gọi máy nhà với `content-type: application/json` (cf/src/worker.js goiMayNha) + `x-ky*` (D7).

Bảng → test:
  GET /hoc/bao-cao (+ngay)          -> test_r_hoc_get_chuyen_tiep, test_r_hoc_query_dung_khoa_tung_tuyen
  GET /hoc/bai-hoc (+gioi_han)      -> test_r_hoc_get_chuyen_tiep, test_r_hoc_query_dung_khoa_tung_tuyen
  POST .../<ma>/hoan-tac|bat-lai    -> test_r_hoc_post_chuyen_nguyen_body_content_type_chu_ky
  cột "Trả" (200/404/409/401/400)   -> test_r_hoc_tra_nguyen_ma_loi_runner
  `ma` sai dạng = 404 (3 chặng)     -> test_r_hoc_ma_sai_dang_hoac_path_la_404_khong_goi_runner, test_r_hoc_ma_khop_dung_RE_MA_BAI_HOC
  method ngoài bảng                 -> test_r_hoc_sai_method_405_khong_goi_runner
  content-type lệch chặng (415)     -> test_r_hoc_post_sai_content_type_415_khong_goi_runner
"""

MA_BH = "bh20261123ab12"
RE_MA_BAI_HOC = r"bh\d{8}[a-z0-9]{4}"   # = /^bh\d{8}[a-z0-9]{4}$/ của cf/src/hoc.js (§3.8)
HDR_KY = {"x-runner-key": "rk-1", "x-ky": "kyabc", "x-ky-ngay": "1763340000000", "x-ky-nonce": "ab" * 16}


def test_hop_dong_hoc_trich_dung_tai_lieu():
    """Bảng trong docstring phải còn khớp §3.8 thật; tài liệu đổi mà test không đổi thì đỏ."""
    tl = (Path(__file__).resolve().parent.parent / "docs" / "hoc-tu-dong.md").read_text(encoding="utf-8")
    for dong in HOP_DONG_HOC.splitlines():
        if dong.startswith("| `"):
            assert dong in tl, dong


@pytest.mark.parametrize("duong, dich", [
    ("/r/hoc/bao-cao", "/hoc/bao-cao"),
    ("/r/hoc/bao-cao?ngay=2026-11-23", "/hoc/bao-cao?ngay=2026-11-23"),
    ("/r/hoc/bai-hoc", "/hoc/bai-hoc"),
    ("/r/hoc/bai-hoc?gioi_han=50", "/hoc/bai-hoc?gioi_han=50"),
])
def test_r_hoc_get_chuyen_tiep(srv, runner, duong, dich):
    code, h, body = goi_r(srv + duong, headers={"x-runner-key": "rk-1"})
    assert code == 200 and json.loads(body) == {"ok": True}
    assert h["content-type"].startswith("application/json")
    g = runner.nhan
    assert len(g) == 1 and g[0]["method"] == "GET" and g[0]["path"] == dich
    assert g[0]["headers"]["x-runner-key"] == "rk-1" and "x-key" not in g[0]["headers"]
    assert g[0]["body"] == b""


@pytest.mark.parametrize("duong, mong", [
    # chỉ khoá của chính tuyến; khoá của tuyến khác / khoá chung R_QUERY_KHOA / khoá lạ bị bỏ
    ("/r/hoc/bao-cao?ngay=2026-11-23&gioi_han=5&tu=0&offset=1&la=1&x-key=k", [("ngay", "2026-11-23")]),
    ("/r/hoc/bai-hoc?gioi_han=50&ngay=2026-11-23&uid=1&tom_tat=1", [("gioi_han", "50")]),
    ("/r/hoc/bao-cao?ngay=2026-11-23&ngay=2026-11-22", [("ngay", "2026-11-23")]),
    # giá trị ký tự lạ bị bỏ như lọc hiện có (Worker đã trả 400 trước đó, §3.8)
    ("/r/hoc/bao-cao?ngay=2026%2F11%2F23", []),
    ("/r/hoc/bao-cao?ngay=2026-11-23%0A", []),
    ("/r/hoc/bao-cao?ngay=..%2F..%2Fx", []),
    ("/r/hoc/bai-hoc?gioi_han=" + "9" * 41, []),
    # tuyến ghi không có query
    (f"/r/hoc/bai-hoc/{MA_BH}/hoan-tac?ngay=2026-11-23&gioi_han=5&boi=x", []),
])
def test_r_hoc_query_dung_khoa_tung_tuyen(srv, runner, duong, mong):
    post = "/hoan-tac" in duong
    code, _, _ = goi_r(srv + duong, method="POST" if post else "GET",
                       headers={"content-type": "application/json"} if post else None,
                       body=b'{"boi":"nhan"}' if post else None)
    assert code == 200
    sp = urlsplit(runner.nhan[0]["path"])
    assert sp.path == urlsplit(duong).path[2:]
    assert parse_qsl(sp.query, keep_blank_values=True) == mong
    assert "?" not in runner.nhan[0]["path"] or mong


def test_r_hoc_khong_noi_query_chung():
    """`ngay` chỉ mở cho /r/hoc/bao-cao, không thêm vào allowlist chung R_QUERY_KHOA."""
    assert "ngay" not in vs.R_QUERY_KHOA


def test_r_viec_khong_nhan_ngay(srv, runner):
    goi_r(srv + "/r/viec?ngay=2026-11-23&offset=10")
    assert parse_qsl(urlsplit(runner.nhan[0]["path"]).query) == [("offset", "10")]


@pytest.mark.parametrize("act", ["hoan-tac", "bat-lai"])
@pytest.mark.parametrize("ct", ["application/json", "application/json; charset=utf-8"])
def test_r_hoc_post_chuyen_nguyen_body_content_type_chu_ky(srv, runner, act, ct):
    hdr = dict(HDR_KY, **{"content-type": ct, "cookie": "phien=1", "authorization": "Bearer t", "x-ky-khac": "z"})
    body = json.dumps({"boi": "nhan"}).encode()
    code, _, rb = goi_r(srv + f"/r/hoc/bai-hoc/{MA_BH}/{act}", method="POST", headers=hdr, body=body)
    assert code == 200 and json.loads(rb) == {"ok": True}
    g = runner.nhan
    assert len(g) == 1
    assert g[0]["method"] == "POST" and g[0]["path"] == f"/hoc/bai-hoc/{MA_BH}/{act}"
    assert g[0]["body"] == body
    h = g[0]["headers"]
    for k in ("x-runner-key", "x-ky", "x-ky-ngay", "x-ky-nonce", "content-type"):
        assert h[k] == hdr[k], k          # content-type chuyển NGUYÊN chữ, không chuẩn hoá
    for k in ("x-key", "cookie", "authorization", "x-ky-khac"):
        assert k not in h, k


@pytest.mark.parametrize("act", ["hoan-tac", "bat-lai"])
def test_r_hoc_post_khong_chu_ky_van_chuyen_de_runner_401(srv, runner, act):
    """video_server không tự cho qua/không tự ký: thiếu x-ky* vẫn chuyển, runner trả 401 thì trả nguyên 401 (D7, §8.4 ca 4)."""
    runner.tra_code, runner.tra_body = 401, json.dumps({"loi": "Thiếu chữ ký"}).encode()
    code, _, rb = goi_r(srv + f"/r/hoc/bai-hoc/{MA_BH}/{act}", method="POST",
                        headers={"content-type": "application/json"}, body=b'{"boi":"nhan"}')
    assert code == 401 and rb == runner.tra_body
    assert not any(k.startswith("x-ky") for k in runner.nhan[0]["headers"])


@pytest.mark.parametrize("duong, method, code_r, body_r", [
    ("/r/hoc/bao-cao?ngay=2026-11-23", "GET", 404, {"loi": "chưa có lần học nào"}),
    ("/r/hoc/bao-cao?ngay=2026-13-45", "GET", 400, {"loi": "ngày sai"}),
    ("/r/hoc/bai-hoc", "GET", 503, {"loi": "Học tự động chưa bật"}),
    (f"/r/hoc/bai-hoc/{MA_BH}/hoan-tac", "POST", 409, {"loi": "bài học không còn hiệu lực"}),
    (f"/r/hoc/bai-hoc/{MA_BH}/bat-lai", "POST", 409,
     {"loi": "đã quá 7 ngày kể từ lúc hoàn tác, không bật lại được nữa"}),
    (f"/r/hoc/bai-hoc/{MA_BH}/hoan-tac", "POST", 404, {"loi": "không có"}),
])
def test_r_hoc_tra_nguyen_ma_loi_runner(srv, runner, duong, method, code_r, body_r):
    runner.tra_code, runner.tra_body = code_r, json.dumps(body_r, ensure_ascii=False).encode()
    post = method == "POST"
    code, _, rb = goi_r(srv + duong, method=method, headers=dict(HDR_KY, **{"content-type": "application/json"}),
                        body=b'{"boi":"nhan"}' if post else None)
    assert code == code_r and json.loads(rb) == body_r
    assert len(runner.nhan) == 1


@pytest.mark.parametrize("duong", [
    "/r/hoc", "/r/hoc/", "/r/hoc/xoa", "/r/hoc/bao-cao/", "/r/hoc/bai-hoc/", "/r/hoc/bao-cao/x",
    "/r/hoc/bai-hoc/../x", "/r/hoc/../viec", f"/r/hoc/bai-hoc/{MA_BH}", f"/r/hoc/bai-hoc/{MA_BH}/",
    f"/r/hoc/bai-hoc/{MA_BH}/xoa", f"/r/hoc/bai-hoc/{MA_BH}/hoan-tac/", f"/r/hoc/bai-hoc/{MA_BH}/bat-lai/x",
    f"/r/hoc/bai-hoc/{MA_BH}/../{MA_BH}/hoan-tac", f"/r/hoc/bai-hoc/{MA_BH}%2Fhoan-tac",
    f"/r/hoc/bai-hoc/{MA_BH}/hoan-tac%2F..", "/r/hoc%2Fbao-cao", "/r/HOC/bao-cao", "/r/hoc/BAO-CAO",
    # ma sai dạng
    "/r/hoc/bai-hoc/bh2026112ab12/hoan-tac",       # 7 số
    "/r/hoc/bai-hoc/bh202611230ab12/hoan-tac",     # 9 số + 4 đuôi = dài 1
    "/r/hoc/bai-hoc/bh20261123ab1/hoan-tac",       # đuôi 3
    "/r/hoc/bai-hoc/bh20261123ab123/bat-lai",      # đuôi 5
    "/r/hoc/bai-hoc/BH20261123ab12/hoan-tac",      # tiền tố hoa
    "/r/hoc/bai-hoc/bh20261123AB12/bat-lai",       # đuôi hoa
    "/r/hoc/bai-hoc/bh20261123ab-2/hoan-tac",      # ký tự lạ
    "/r/hoc/bai-hoc/j20261117093000ab12/hoan-tac", # mã việc, không phải mã bài học
    "/r/hoc/bai-hoc/%62h20261123ab12/hoan-tac",    # %-mã hoá
    "/r/hoc/bai-hoc/bh" + quote("２０２６１１２３") + "ab12/hoan-tac",  # số toàn chiều rộng
])
def test_r_hoc_ma_sai_dang_hoac_path_la_404_khong_goi_runner(srv, runner, duong):
    code, _, body = goi_r(srv + duong)
    assert code == 404 and json.loads(body) == {"loi": "Đường dẫn không hợp lệ"}
    # body rỗng: server từ chối trước khi đọc body (đóng kết nối) -> body thật dễ bị WinError 10053 phía client
    code, _, _ = goi_r(srv + duong, method="POST", headers=dict(HDR_KY, **{"content-type": "application/json"}),
                       body=b"")
    assert code == 404
    assert runner.nhan == []


@pytest.mark.parametrize("ma", [MA_BH, "bh00000000aaaa", "bh99999999zz99", "bh2026112ab12", "bh20261123ab1",
                                "bh20261123ab123", "BH20261123ab12", "bh20261123AB12", "bh20261123ab_2",
                                "xbh20261123ab12", "bh20261123ab12x"])
def test_r_hoc_ma_khop_dung_RE_MA_BAI_HOC(ma):
    """video_server nhận <ma> khi và chỉ khi RE_MA_BAI_HOC (Worker) nhận — lệch là lệch hợp đồng 3 chặng."""
    import re
    for act in ("hoan-tac", "bat-lai"):
        assert bool(vs.RE_R.fullmatch(f"/r/hoc/bai-hoc/{ma}/{act}")) == bool(re.fullmatch(RE_MA_BAI_HOC, ma)), ma


@pytest.mark.parametrize("duong, method", [
    ("/r/hoc/bao-cao", "POST"), ("/r/hoc/bai-hoc", "POST"),
    (f"/r/hoc/bai-hoc/{MA_BH}/hoan-tac", "GET"), (f"/r/hoc/bai-hoc/{MA_BH}/bat-lai", "GET"),
])
def test_r_hoc_sai_method_405_khong_goi_runner(srv, runner, duong, method):
    post = method == "POST"
    code, _, body = goi_r(srv + duong, method=method, headers=dict(HDR_KY, **{"content-type": "application/json"}),
                          body=b'{"boi":"nhan"}' if post else None)
    assert code == 405 and json.loads(body) == {"loi": "Sai phương thức"}
    assert runner.nhan == []


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH"])
def test_r_hoc_method_ghi_khac_khong_chuyen(srv, runner, method):
    code, _, _ = goi_r(srv + f"/r/hoc/bai-hoc/{MA_BH}/hoan-tac", method=method,
                       headers={"content-type": "application/json"}, body=b"")
    assert code in (405, 501)
    assert runner.nhan == []


@pytest.mark.parametrize("act", ["hoan-tac", "bat-lai"])
def test_r_hoc_post_sai_content_type_415_khong_goi_runner(srv, runner, act):
    for ct in ("text/plain", "application/x-www-form-urlencoded", "application/jsonx"):
        code, _, _ = goi_r(srv + f"/r/hoc/bai-hoc/{MA_BH}/{act}", method="POST",
                           headers=dict(HDR_KY, **{"content-type": ct}), body=b'{"boi":"nhan"}')
        assert code == 415, ct
    assert runner.nhan == []


@pytest.mark.parametrize("khoa", [None, "sai"])
def test_r_hoc_thieu_sai_x_key_401_khong_goi_runner(srv, runner, khoa):
    assert goi_r(srv + "/r/hoc/bao-cao", khoa=khoa)[0] == 401
    code, _, _ = goi_r(srv + f"/r/hoc/bai-hoc/{MA_BH}/hoan-tac", khoa=khoa, method="POST",
                       headers=dict(HDR_KY, **{"content-type": "application/json"}), body=b"")
    assert code == 401
    assert runner.nhan == []


# ---------- sửa video: act anh / clip trên /v/<id>/ ----------

CLIP1 = "c01_001_hook_mo-hop.mp4"        # ngay trong cuts/
CLIP2 = "c01_002_loi-ich (2).mp4"        # trong cuts/con/ (một cấp)
CLIP_SAU = "c01_003_sau.mp4"             # cuts/a/b/ (hai cấp) -> không nhận
CLIP_KHONG_FILE = "c01_004_mat.mp4"      # có trong index, không có file
CLIP_KHONG_ID = "khongso.mp4"            # không khớp ^(.+?_\d{3})_
CLIP_HAI_CHAM = "a..b_005_x.mp4"         # có '..'


@pytest.fixture
def cuts(goc):
    d = goc / f"abc {ID}"
    c = d / "cuts"
    _ghi(c / CLIP1, 200)
    _ghi(c / "con" / CLIP2, 30)
    _ghi(c / "a" / "b" / CLIP_SAU)
    _ghi(c / CLIP_KHONG_ID)
    _ghi(c / CLIP_HAI_CHAM)
    _ghi(c / "ngoai-index_001_x.mp4")
    clips = {t: {"role": "hook", "dur": 2.0}
             for t in (CLIP1, CLIP2, CLIP_SAU, CLIP_KHONG_FILE, CLIP_KHONG_ID, CLIP_HAI_CHAM)}
    (c / "clip_index.json").write_text(json.dumps({"version": 1, "clips": clips}), encoding="utf-8")
    fr = c / ".index_frames" / "c01_001"
    fr.mkdir(parents=True)
    (fr / "f_00.jpg").write_bytes(b"\xff\xd8anh0")
    (fr / "f_03.jpg").write_bytes(b"\xff\xd8anh3")
    (fr / "contact_sheet.jpg").write_bytes(b"\xff\xd8cs")
    return d


def _url(srv, act, d, ten, **them):
    q = f"du_an={vs.ma_du_an(d) if isinstance(d, Path) else d}&ten={quote(ten)}"
    for k, v in them.items():
        q += f"&{k}={quote(v)}"
    return srv + f"/v/{ID}/{act}?{q}"


def test_ma_du_an_khop_cheo_runner(tmp_path, goc, cuts):
    sys.path.insert(0, str(Path(__file__).parent))
    from runner import du_an
    for p in (cuts, tmp_path / "x y" / "Tên có dấu 123", Path("E:/oneshottramcanh/abc 1731141980888533631"),
              Path("F:\\2710\\1028\\sp 1")):
        assert vs.ma_du_an(p) == du_an.ma_du_an(p), p
    ds = du_an.ds_du_an(ID, vs.GOCS)
    assert {x["ma"] for x in ds} == {vs.ma_du_an(cuts), vs.ma_du_an(goc / f"moi {ID}")}
    assert all(vs.tim_du_an(ID, x["ma"]) == Path(x["goc"]) / x["ten"] for x in ds)


def test_anh_tra_jpeg(srv, cuts):
    code, h, body = goi(_url(srv, "anh", cuts, CLIP1, k="0"))
    assert code == 200 and body == b"\xff\xd8anh0" and h["content-type"] == "image/jpeg"
    assert "content-disposition" not in h
    assert goi(_url(srv, "anh", cuts, CLIP1, k="3"))[2] == b"\xff\xd8anh3"
    assert goi(_url(srv, "anh", cuts, CLIP1, k="cs"))[2] == b"\xff\xd8cs"


@pytest.mark.parametrize("k", ["", "10", "a", "-1", "cs2", "0/../x"])
def test_anh_k_sai_400(srv, cuts, k):
    assert goi(_url(srv, "anh", cuts, CLIP1, k=k))[0] == 400


def test_anh_thieu_k_400(srv, cuts):
    assert goi(_url(srv, "anh", cuts, CLIP1))[0] == 400


def test_anh_khong_co_khung_hoac_khong_co_clip_id_404(srv, cuts):
    assert goi(_url(srv, "anh", cuts, CLIP1, k="5"))[0] == 404
    assert goi(_url(srv, "anh", cuts, CLIP2, k="0"))[0] == 404     # chưa có .index_frames/c01_002
    assert goi(_url(srv, "anh", cuts, CLIP_KHONG_ID, k="0"))[0] == 404


def test_clip_range_206_khong_attachment(srv, cuts):
    code, h, body = goi(_url(srv, "clip", cuts, CLIP1), headers={"Range": "bytes=2-5"})
    assert code == 206 and body == bytes([2, 3, 4, 5])
    assert h["content-range"] == "bytes 2-5/200" and h["content-type"] == "video/mp4"
    assert h["accept-ranges"] == "bytes" and "content-disposition" not in h
    code, h, body = goi(_url(srv, "clip", cuts, CLIP1, xoa="1"))
    assert code == 200 and len(body) == 200 and "content-disposition" not in h
    time.sleep(0.2)
    assert (cuts / "cuts" / CLIP1).is_file()


def test_clip_trong_thu_muc_con_mot_cap(srv, cuts):
    code, _, body = goi(_url(srv, "clip", cuts, CLIP2))
    assert code == 200 and len(body) == 30


@pytest.mark.parametrize("ten", [
    CLIP_SAU, CLIP_KHONG_FILE, CLIP_HAI_CHAM, "ngoai-index_001_x.mp4",
    "../output_poster/01.mp4", "..\\output_poster\\01.mp4", "con/" + CLIP2, "con\\" + CLIP2,
    "clip_index.json", "", "c01_001_hook_mo-hop.MP4", ".index_frames", CLIP1 + "\n",
])
def test_clip_ten_xau_hoac_ngoai_index_404(srv, cuts, ten):
    code, _, body = goi(_url(srv, "clip", cuts, ten))
    assert code == 404, ten
    assert "loi" in json.loads(body)
    assert goi(_url(srv, "anh", cuts, ten, k="0"))[0] == 404


@pytest.mark.parametrize("du_an", ["", "abc", "0" * 12, "ABCDEF012345", "../../x", "THEM-0"])
def test_du_an_sai_hoac_khong_co_404(srv, cuts, du_an):
    d = vs.ma_du_an(cuts) + "0" if du_an == "THEM-0" else du_an
    assert goi(_url(srv, "clip", d, CLIP1))[0] == 404
    assert goi(_url(srv, "anh", d, CLIP1, k="0"))[0] == 404


def test_du_an_cua_id_khac_khong_dung_duoc(srv, cuts, goc):
    khac = "1111111111111111111"
    d2 = goc / f"zz {khac}"
    _ghi(d2 / "cuts" / CLIP1)
    (d2 / "cuts" / "clip_index.json").write_text(json.dumps({"clips": {CLIP1: {}}}), encoding="utf-8")
    assert goi(srv + f"/v/{ID}/clip?du_an={vs.ma_du_an(d2)}&ten={quote(CLIP1)}")[0] == 404
    assert goi(srv + f"/v/{khac}/clip?du_an={vs.ma_du_an(d2)}&ten={quote(CLIP1)}")[0] == 200


def test_clip_index_hong_404(srv, cuts):
    (cuts / "cuts" / "clip_index.json").write_text("{hong", encoding="utf-8")
    assert goi(_url(srv, "clip", cuts, CLIP1))[0] == 404
    (cuts / "cuts" / "clip_index.json").write_text(json.dumps({"clips": [CLIP1]}), encoding="utf-8")
    assert goi(_url(srv, "clip", cuts, CLIP1))[0] == 404


def test_anh_clip_post_405_va_thieu_khoa_401(srv, cuts):
    assert goi(_url(srv, "clip", cuts, CLIP1), method="POST")[0] == 405
    assert goi(_url(srv, "anh", cuts, CLIP1, k="0"), method="POST")[0] == 405
    assert goi(_url(srv, "clip", cuts, CLIP1), khoa=None)[0] == 401
    assert goi(_url(srv, "anh", cuts, CLIP1, k="0"), khoa="sai")[0] == 401


# ---------- bật/tắt app ----------

def test_lenh_bat_chi_cho_app_trong_APPS_khong_co_video_server():
    assert set(vs.LENH_BAT) <= {a[0] for a in vs.APPS}
    assert "video_server" not in vs.LENH_BAT


def test_suc_khoe_danh_dau_bat_tat(srv, monkeypatch):
    monkeypatch.setattr(vs, "cong_song", lambda c, cho=1.0: False)
    apps = {a["ma"]: a for a in json.loads(goi(srv + "/suc-khoe")[2])["apps"]}
    assert all(apps[m].get("bat_tat") is True for m in vs.LENH_BAT)
    assert "bat_tat" not in apps["video_server"]


def test_app_bat_tat_khoa_ma_la_phuong_thuc(srv, monkeypatch):
    goi_that = []
    monkeypatch.setattr(vs, "bat_app", lambda ma, c: (goi_that.append(("bat", ma, c)), (True, "Đang bật"))[1])
    monkeypatch.setattr(vs, "tat_app", lambda c: (goi_that.append(("tat", c)), (False, "cổng vẫn mở"))[1])
    monkeypatch.setattr(vs, "cong_song", lambda c, cho=1.0: False)
    assert goi(srv + "/app/muse/bat", method="POST", khoa=None)[0] == 401
    assert goi(srv + "/app/muse/bat", method="GET")[0] == 405
    assert goi(srv + "/app/video_server/tat", method="POST")[0] == 404
    assert goi(srv + "/app/la/bat", method="POST")[0] == 404
    assert goi_that == []
    code, _, body = goi(srv + "/app/muse/bat", method="POST")
    assert code == 200 and json.loads(body) == {"ma": "muse", "ok": True, "tin": "Đang bật", "song": False}
    code, _, body = goi(srv + "/app/runner/tat", method="POST")
    assert code == 500 and json.loads(body)["tin"] == "cổng vẫn mở"
    assert goi_that == [("bat", "muse", 3786), ("tat", 8788)]


def test_goc_can_giet_leo_cmd_nhung_khong_dung_to_tien_video_server():
    # 100 explorer → 200 cmd(chay_video.bat) → 300 python video_server ; 200 → 400 python runner
    # 300 → 500 cmd(Start.cmd) → 600 node muse
    bang = {100: (1, "explorer.exe"), 200: (100, "cmd.exe"), 300: (200, "python.exe"),
            400: (200, "python.exe"), 500: (300, "cmd.exe"), 600: (500, "node.exe")}
    cam = vs.to_tien(300, bang)
    assert cam == {300, 200, 100, 1}
    assert vs.goc_can_giet(600, bang, cam) == 500
    assert vs.goc_can_giet(400, bang, cam) == 400


def test_tat_app_khong_giet_chinh_minh(monkeypatch):
    monkeypatch.setattr(vs, "pid_nghe_cong", lambda c: {os.getpid()})
    monkeypatch.setattr(vs, "bang_tien_trinh", lambda: {})
    ok, tin = vs.tat_app(1)
    assert not ok and "chung tiến trình" in tin


def test_pid_nghe_cong_doc_netstat_that():
    nghe = socket.socket(); nghe.bind(("127.0.0.1", 0)); nghe.listen(1)
    try:
        assert os.getpid() in vs.pid_nghe_cong(nghe.getsockname()[1])
    finally:
        nghe.close()


# ---------- radar UID: chuyển tiếp /r/radar/* (docs/radar-uid.md §7, RU-B4) ----------
U1 = "1729706628656957720"   # > 2^53, giữ chuỗi
U2 = "1737422436677814024"
RADAR_GET = ["/r/radar/bang", f"/r/radar/uid/{U1}"]
RADAR_POST = ["/r/radar/chup-lai", "/r/radar/goc", f"/r/radar/goc/{U1}/tim-lai", f"/r/radar/goc/{U1}/ngung",
              f"/r/radar/goc/{U1}/theo-lai", f"/r/radar/goc/{U1}/them-tay"] + \
             [f"/r/radar/goc/{U1}/uid/{U2}/{a}" for a in ("ghim", "bo-ghim", "loai", "bo-loai")]


@pytest.mark.parametrize("duong", RADAR_GET)
def test_r_radar_get_chuyen_tiep_khong_query(srv, runner, duong):
    code, h, body = goi_r(srv + duong + "?tu=1&uid=2&gioi_han=5&ngay=2026-11-23", headers={"x-runner-key": "rk-1"})
    assert code == 200 and json.loads(body) == {"ok": True}
    g = runner.nhan
    assert len(g) == 1 and g[0]["method"] == "GET" and g[0]["path"] == duong[2:]  # query bị bỏ hết
    assert g[0]["headers"]["x-runner-key"] == "rk-1" and "x-key" not in g[0]["headers"]


@pytest.mark.parametrize("duong", RADAR_POST)
def test_r_radar_post_chuyen_nguyen_body_header_khong_query(srv, runner, duong):
    hdr = dict(HDR_KY, **{"content-type": "application/json", "cookie": "phien=1", "authorization": "Bearer t",
                          "x-ky-khac": "z"})
    body = json.dumps({"boi": "nhan", "uid": U1}).encode()
    code, _, rb = goi_r(srv + duong + "?uid=9&tu=1", method="POST", headers=hdr, body=body)
    assert code == 200 and json.loads(rb) == {"ok": True}
    g = runner.nhan
    assert len(g) == 1 and g[0]["method"] == "POST" and g[0]["path"] == duong[2:]
    assert g[0]["body"] == body
    h = g[0]["headers"]
    for k in ("x-runner-key", "x-ky", "x-ky-ngay", "x-ky-nonce", "content-type"):
        assert h[k] == hdr[k], k
    for k in ("x-key", "cookie", "authorization", "x-ky-khac"):
        assert k not in h, k


@pytest.mark.parametrize("duong", [
    "/r/radar", "/r/radar/", "/r/radar/x", "/r/radar/bang/", "/r/radar/uid", "/r/radar/uid/", "/r/radar/uid/12",
    f"/r/radar/uid/{U1}0", f"/r/radar/uid/{U1[:-1]}", "/r/radar/uid/" + quote("１" * 19), "/r/radar/uid/abcdefghijklmnopqrs",
    f"/r/radar/uid/{U1}/", f"/r/radar/goc/", f"/r/radar/goc/12/tim-lai", f"/r/radar/goc/{U1}", f"/r/radar/goc/{U1}/",
    f"/r/radar/goc/{U1}/xoa", f"/r/radar/goc/{U1}/tim-lai/", f"/r/radar/goc/{U1}/uid/{U2}",
    f"/r/radar/goc/{U1}/uid/{U2}/xoa", f"/r/radar/goc/{U1}/uid/12/ghim", f"/r/radar/goc/12/uid/{U2}/ghim",
    f"/r/radar/goc/{U1}/uid/{U2}/ghim/", "/r/radar/chup-lai/", "/r/radar/../viec", "/r/radar%2Fbang",
    "/r/RADAR/bang", "/r/radar/BANG", f"/r/radar/goc/{U1}/../{U1}/ngung",
])
def test_r_radar_path_la_404_khong_goi_runner(srv, runner, duong):
    code, _, body = goi_r(srv + duong)
    assert code == 404 and json.loads(body) == {"loi": "Đường dẫn không hợp lệ"}
    code, _, _ = goi_r(srv + duong, method="POST", headers=dict(HDR_KY, **{"content-type": "application/json"}),
                       body=b"")
    assert code == 404
    assert runner.nhan == []


@pytest.mark.parametrize("duong", RADAR_GET)
def test_r_radar_post_tren_route_get_405(srv, runner, duong):
    code, _, body = goi_r(srv + duong, method="POST", headers=dict(HDR_KY, **{"content-type": "application/json"}),
                          body=b'{"boi":"nhan"}')
    assert code == 405 and json.loads(body) == {"loi": "Sai phương thức"}
    assert runner.nhan == []


@pytest.mark.parametrize("duong", RADAR_POST)
def test_r_radar_get_tren_route_post_405(srv, runner, duong):
    code, _, body = goi_r(srv + duong)
    assert code == 405 and json.loads(body) == {"loi": "Sai phương thức"}
    assert runner.nhan == []


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH"])
def test_r_radar_method_khac_khong_chuyen(srv, runner, method):
    for duong in ("/r/radar/chup-lai", "/r/radar/bang"):
        code, _, _ = goi_r(srv + duong, method=method, headers={"content-type": "application/json"}, body=b"")
        assert code in (405, 501)
    assert runner.nhan == []


def test_r_radar_post_body_qua_16kb_413_khong_goi_runner(srv, runner):
    code, _, body = goi_r(srv + "/r/radar/goc", method="POST", headers=dict(HDR_KY, **{"content-type": "application/json"}),
                          body=b"x" * (16 * 1024 + 1))
    assert code == 413 and "loi" in json.loads(body)
    assert runner.nhan == []


def test_r_radar_post_sai_content_type_415_khong_goi_runner(srv, runner):
    for ct in ("text/plain", "application/x-www-form-urlencoded", "application/jsonx"):
        code, _, _ = goi_r(srv + "/r/radar/chup-lai", method="POST", headers=dict(HDR_KY, **{"content-type": ct}),
                           body=b'{"boi":"nhan"}')
        assert code == 415, ct
    assert runner.nhan == []


@pytest.mark.parametrize("khoa", [None, "sai"])
def test_r_radar_thieu_sai_x_key_401_khong_goi_runner(srv, runner, khoa):
    assert goi_r(srv + "/r/radar/bang", khoa=khoa)[0] == 401
    code, _, _ = goi_r(srv + "/r/radar/chup-lai", khoa=khoa, method="POST",
                       headers=dict(HDR_KY, **{"content-type": "application/json"}), body=b"")
    assert code == 401
    assert runner.nhan == []


def test_r_radar_post_khong_chu_ky_van_chuyen_de_runner_401(srv, runner):
    runner.tra_code, runner.tra_body = 401, json.dumps({"loi": "Thiếu chữ ký"}).encode()
    code, _, rb = goi_r(srv + "/r/radar/goc", method="POST", headers={"content-type": "application/json"},
                        body=b'{"boi":"nhan"}')
    assert code == 401 and rb == runner.tra_body
    assert not any(k.startswith("x-ky") for k in runner.nhan[0]["headers"])


def test_r_radar_khong_noi_query_chung_va_get_regex():
    assert vs.R_QUERY_KHOA == ("tu", "trang_thai", "uid", "gioi_han", "tom_tat", "seg", "offset")
    assert vs.R_RADAR_GET.pattern == r"^/r/radar/(bang|uid/\d{19})$"
