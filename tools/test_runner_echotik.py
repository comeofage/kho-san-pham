# -*- coding: utf-8 -*-
"""Test client EchoTik (RU-A1). Mock transport, KHÔNG gọi mạng thật, token giả."""
from __future__ import annotations

import ast
import email.message
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from runner import echotik  # noqa: E402
from runner.echotik import (  # noqa: E402
    EchoTik, HetNganSach, LoiEchoTik, anh_bia, anh_ung_vien, chuan_meta, chuan_ung_vien, chuan_video,
)

TOKEN_GIA = "TOKEN_GIA_zq81xk-secret"
TOKEN_GIA_2 = "TOKEN_GIA_moi_77aa-secret"
UID = "1729420930611055346"          # 19 số (> 2^53)


# ------------------------------------------------------------------ giả lập


class PhanHoi:
    """Giả `http.client.HTTPResponse` (đủ: context manager, status, headers, read)."""

    def __init__(self, status: int = 200, body: object = b"", ctype: str = "application/json; charset=utf-8"):
        self.status = status
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self._body = body
        self.headers = email.message.Message()
        self.headers["Content-Type"] = ctype

    def read(self, n: int = -1) -> bytes:
        return self._body if n is None or n < 0 else self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def loi_http(code: int, body: bytes = b"TOKEN_GIA_zq81xk-secret trong than loi") -> urllib.error.HTTPError:
    h = email.message.Message()
    h["Content-Type"] = "application/json"
    import io
    return urllib.error.HTTPError("https://echotik.live/x", code, "msg", h, io.BytesIO(body))


class Mang:
    """mo_url giả: phát lần lượt kịch bản; mỗi phần tử là PhanHoi hoặc Exception."""

    def __init__(self, kich_ban, dong_ho=None):
        self.kich_ban = list(kich_ban)
        self.yeu_cau: list = []
        self.timeouts: list = []
        self.gio_goi: list[float] = []
        self.dong_ho = dong_ho

    def __call__(self, req, timeout=None):
        self.yeu_cau.append(req)
        self.timeouts.append(timeout)
        if self.dong_ho is not None:
            self.gio_goi.append(self.dong_ho())
        if not self.kich_ban:
            raise AssertionError("het kich ban mang")
        x = self.kich_ban.pop(0)
        if isinstance(x, BaseException):
            raise x
        return x


class DongHo:
    """Đồng hồ giả: chỉ tiến khi `ngu` được gọi."""

    def __init__(self):
        self.t = 1000.0
        self.ngu_goi: list[float] = []

    def __call__(self) -> float:
        return self.t

    def ngu(self, s: float) -> None:
        self.ngu_goi.append(s)
        self.t += s


@pytest.fixture
def file_token(tmp_path):
    p = tmp_path / "echotik_token.json"
    p.write_text(json.dumps({"token": TOKEN_GIA, "user_id": "u-12345", "email": "a@b.c"}), encoding="utf-8")
    return p


def dung(file_token, kich_ban, **kw):
    dh = DongHo()
    mang = Mang(kich_ban, dh)
    cli = EchoTik(file_token, mo_url=mang, ngu=dh.ngu, dong_ho=dh, **kw)
    return cli, mang, dh


E1_OK = {"data": {"product_id": UID, "product_name": "Binh giu nhiet", "price": "$19.37", "real_price": "499.390₫",
                  "sale_cnt": "10.17K", "commission": "10%", "total_stock_cnt": 562,
                  "update_time": "2026-11-22 07:55", "seller": {"seller_name": "Shop A"}}}
E2_OK = {"data": [
    {"video_id": "7400000000000000001", "views_count": "21.81K", "publish_time": "2026-07-18 10:00:00",
     "update_time": "2026-11-23 10:00:01", "influencer": {"unique_id": "abc", "follower_count": "2.54K"},
     "is_promote": False},
    {"video_id": "7400000000000000002", "views_count": 326, "publish_time": "2025-01-02 09:00:00",
     "update_time": "2026-11-23 10:00:01", "influencer": {"unique_id": "xyz", "follower_count": "N/A"},
     "is_promote": True},
], "meta": {"current_page": 1, "from": 1, "last_page": 1, "links": []}}
E4_OK = {"data": [{"product_id": "1729420930611055346", "product_name": "Binh giu nhiet 500ml",
                   "avg_price": "$12.7", "total_sale_7d_cnt": "36"}]}


# ------------------------------------------------------------------ header + URL


def test_header_dung_muc_2_1(file_token):
    cli, mang, _ = dung(file_token, [PhanHoi(body=E1_OK)])
    cli.chi_tiet(UID)
    req = mang.yeu_cau[0]
    h = {k.lower(): v for k, v in req.header_items()}
    assert h["authorization"] == "Bearer " + TOKEN_GIA
    assert h["token"] == TOKEN_GIA
    assert h["x-user-id"] == "u-12345" and h["user_id"] == "u-12345"
    assert h["x-region"] == "VN"
    assert h["origin"] == "https://echotik.live"
    assert h["referer"].startswith("https://echotik.live")
    assert "Chrome" in h["user-agent"]
    assert req.get_method() == "GET"
    assert "region" not in req.full_url.lower()


def test_url_chi_tiet_va_timeout(file_token):
    cli, mang, _ = dung(file_token, [PhanHoi(body=E1_OK)])
    cli.chi_tiet(UID)
    assert mang.yeu_cau[0].full_url == f"https://echotik.live/api/v1/data/products/{UID}"
    assert mang.timeouts[0] and mang.timeouts[0] > 0


def test_url_video_order_publish_time_desc(file_token):
    cli, mang, _ = dung(file_token, [PhanHoi(body=E2_OK)])
    cli.video(UID, trang=2, moi_trang=50)
    u = urllib.parse.urlsplit(mang.yeu_cau[0].full_url)
    assert u.path == f"/api/v1/data/products/{UID}/videos"
    q = dict(urllib.parse.parse_qsl(u.query))
    assert q == {"page": "2", "per_page": "50", "order": "publish_time", "sort": "desc"}


def test_url_tim_keyword_duoc_ma_hoa_an_toan(file_token):
    cli, mang, _ = dung(file_token, [PhanHoi(body=E4_OK)])
    kw = "binh & giu=nhiet#x?y/../ đồ uống"
    cli.tim(kw, trang=1, moi_trang=50)
    raw = mang.yeu_cau[0].full_url
    u = urllib.parse.urlsplit(raw)
    assert u.path == "/api/v1/data/products" and u.fragment == ""
    q = dict(urllib.parse.parse_qsl(u.query))
    assert q["keyword"] == kw                      # round-trip nguyên vẹn
    assert q["order"] == "total_sale_7d_cnt" and q["sort"] == "desc" and q["dateRange"] == "7"
    assert q["page"] == "1" and q["per_page"] == "50"
    assert " " not in raw and "region" not in raw.lower()
    assert u.query.count("keyword=") == 1          # không tiêm tham số thừa


@pytest.mark.parametrize("uid", ["123", "../../etc", UID + "0", "abc" * 7, ""])
def test_uid_sai_dang_bi_tu_choi_truoc_khi_goi(file_token, uid):
    cli, mang, _ = dung(file_token, [])
    with pytest.raises(LoiEchoTik) as e:
        cli.chi_tiet(uid)
    assert e.value.ma == "dinh_dang"
    with pytest.raises(LoiEchoTik):
        cli.video(uid)
    assert mang.yeu_cau == [] and cli.so_goi == 0


# ------------------------------------------------------------------ lỗi mã cố định


def test_html_oops_la_token_het_han(file_token):
    cli, _, _ = dung(file_token, [PhanHoi(200, "<html><body>Oops</body></html>", "text/html; charset=utf-8")])
    with pytest.raises(LoiEchoTik) as e:
        cli.chi_tiet(UID)
    assert e.value.ma == "token_het_han"


def test_html_du_content_type_json_van_bi_bat(file_token):
    cli, _, _ = dung(file_token, [PhanHoi(200, "<!doctype html><title>Oops</title>", "application/json")])
    with pytest.raises(LoiEchoTik) as e:
        cli.chi_tiet(UID)
    assert e.value.ma == "token_het_han"


@pytest.mark.parametrize("code", [401, 403])
def test_401_403_la_token_het_han_khong_thu_lai(file_token, code):
    cli, mang, dh = dung(file_token, [loi_http(code)])
    with pytest.raises(LoiEchoTik) as e:
        cli.chi_tiet(UID)
    assert e.value.ma == "token_het_han"
    assert len(mang.yeu_cau) == 1 and dh.ngu_goi == []


def test_429_la_rate_limit_khong_thu_lai(file_token):
    cli, mang, dh = dung(file_token, [loi_http(429)])
    with pytest.raises(LoiEchoTik) as e:
        cli.chi_tiet(UID)
    assert e.value.ma == "rate_limit"
    assert len(mang.yeu_cau) == 1 and dh.ngu_goi == []


def test_429_tra_ve_nhu_phan_hoi_cung_la_rate_limit(file_token):
    cli, _, _ = dung(file_token, [PhanHoi(429, b"{}")])
    with pytest.raises(LoiEchoTik) as e:
        cli.chi_tiet(UID)
    assert e.value.ma == "rate_limit"


def test_404_la_khong_tim_thay_khong_thu_lai(file_token):
    cli, mang, _ = dung(file_token, [loi_http(404)])
    with pytest.raises(LoiEchoTik) as e:
        cli.chi_tiet(UID)
    assert e.value.ma == "khong_tim_thay" and len(mang.yeu_cau) == 1


def test_4xx_khac_la_dinh_dang_khong_thu_lai(file_token):
    cli, mang, _ = dung(file_token, [loi_http(400)])
    with pytest.raises(LoiEchoTik) as e:
        cli.chi_tiet(UID)
    assert e.value.ma == "dinh_dang" and len(mang.yeu_cau) == 1


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
def test_3xx_la_dinh_dang_khong_thu_lai(file_token, code):
    cli, mang, _ = dung(file_token, [loi_http(code)])
    with pytest.raises(LoiEchoTik) as e:
        cli.chi_tiet(UID)
    assert e.value.ma == "dinh_dang" and e.value.http == code and len(mang.yeu_cau) == 1


def test_mo_url_mac_dinh_la_opener_chan_redirect(file_token):
    assert EchoTik(file_token)._mo_url is echotik.mo_url_khong_theo_redirect


@pytest.mark.parametrize("code", [301, 302, 307, 308])
def test_opener_that_khong_theo_redirect_khong_gui_lai_header(code, monkeypatch):
    import http.server
    import threading
    import urllib.request
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    thay: dict[str, list] = {"a": [], "b": []}

    class B(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            thay["b"].append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    sb = http.server.HTTPServer(("127.0.0.1", 0), B)

    class A(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            thay["a"].append(self.headers.get("Authorization"))
            self.send_response(code)
            self.send_header("Location", f"http://127.0.0.1:{sb.server_port}/lay-cap")
            self.end_headers()

        def log_message(self, *a):
            pass

    sa = http.server.HTTPServer(("127.0.0.1", 0), A)
    ts = [threading.Thread(target=s.serve_forever, daemon=True) for s in (sa, sb)]
    for t in ts:
        t.start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{sa.server_port}/x",
                                     headers={"Authorization": "Bearer TOKEN_GIA"}, method="GET")
        with pytest.raises(urllib.error.HTTPError) as e:
            echotik.mo_url_khong_theo_redirect(req, timeout=5)
        assert e.value.code == code
        assert thay["a"] == ["Bearer TOKEN_GIA"] and thay["b"] == []     # host đích không nhận gì
    finally:
        for s in (sa, sb):
            s.shutdown()
            s.server_close()


def test_5xx_thu_lai_2_lan_3s_roi_6s_moi_lan_tinh_goi(file_token):
    dem: list[int] = []
    cli, mang, dh = dung(file_token, [loi_http(503), loi_http(502), PhanHoi(body=E1_OK)],
                         tinh_goi=lambda n: dem.append(n) or True)
    d = cli.chi_tiet(UID)
    assert d["product_id"] == UID
    assert len(mang.yeu_cau) == 3
    assert [x for x in dh.ngu_goi if x >= 3] == [3.0, 6.0]
    assert dem == [1, 1, 1] and cli.so_goi == 3


def test_5xx_het_luot_thu_lai_la_mang(file_token):
    cli, mang, _ = dung(file_token, [loi_http(500)] * 3)
    with pytest.raises(LoiEchoTik) as e:
        cli.chi_tiet(UID)
    assert e.value.ma == "mang" and len(mang.yeu_cau) == 3     # 1 + đúng 2 lần thử lại


def test_timeout_va_ngat_ket_noi_thu_lai_roi_thanh_cong(file_token):
    cli, mang, dh = dung(file_token, [TimeoutError("het gio"), urllib.error.URLError("dut"), PhanHoi(body=E1_OK)])
    assert cli.chi_tiet(UID)["product_id"] == UID
    assert [x for x in dh.ngu_goi if x >= 3] == [3.0, 6.0]


def test_mang_that_bai_het_luot(file_token):
    cli, mang, _ = dung(file_token, [ConnectionResetError("x")] * 3)
    with pytest.raises(LoiEchoTik) as e:
        cli.chi_tiet(UID)
    assert e.value.ma == "mang" and len(mang.yeu_cau) == 3


def test_tinh_goi_false_la_het_ngan_sach_va_khong_goi_mang(file_token):
    cli, mang, _ = dung(file_token, [PhanHoi(body=E1_OK)], tinh_goi=lambda n: False)
    with pytest.raises(HetNganSach):
        cli.chi_tiet(UID)
    assert mang.yeu_cau == [] and cli.so_goi == 0


def test_het_ngan_sach_giua_cac_lan_thu_lai(file_token):
    cho = iter([True, False])
    cli, mang, _ = dung(file_token, [loi_http(503), PhanHoi(body=E1_OK)], tinh_goi=lambda n: next(cho))
    with pytest.raises(HetNganSach):
        cli.chi_tiet(UID)
    assert len(mang.yeu_cau) == 1


def test_json_hong_hoac_thieu_data_la_dinh_dang(file_token):
    for body in (b"khong phai json", {"meta": {}}, [1, 2], b'"x"'):
        cli, _, _ = dung(file_token, [PhanHoi(200, body)])
        with pytest.raises(LoiEchoTik) as e:
            cli.chi_tiet(UID)
        assert e.value.ma == "dinh_dang"


def test_chi_tiet_data_rong_la_khong_tim_thay(file_token):
    for body in ({"data": None}, {"data": {}}):
        cli, _, _ = dung(file_token, [PhanHoi(200, body)])
        with pytest.raises(LoiEchoTik) as e:
            cli.chi_tiet(UID)
        assert e.value.ma == "khong_tim_thay"


def test_chi_tiet_data_khong_phai_object_la_dinh_dang(file_token):
    cli, _, _ = dung(file_token, [PhanHoi(200, {"data": [1]})])
    with pytest.raises(LoiEchoTik) as e:
        cli.chi_tiet(UID)
    assert e.value.ma == "dinh_dang"


def test_video_va_tim_data_khong_phai_list_la_dinh_dang(file_token):
    cli, _, _ = dung(file_token, [PhanHoi(200, {"data": {"a": 1}})])
    with pytest.raises(LoiEchoTik) as e:
        cli.video(UID)
    assert e.value.ma == "dinh_dang"
    cli, _, _ = dung(file_token, [PhanHoi(200, {"data": "x"})])
    with pytest.raises(LoiEchoTik) as e:
        cli.tim("binh")
    assert e.value.ma == "dinh_dang"


# ------------------------------------------------------------------ token không rò rỉ


def test_thong_diep_loi_khong_chua_token_hay_than_phan_hoi(file_token, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    kich = [loi_http(401), loi_http(429), loi_http(500), loi_http(500), loi_http(500),
            PhanHoi(200, "<html>Oops " + TOKEN_GIA + "</html>", "text/html"),
            PhanHoi(200, "rac " + TOKEN_GIA)]
    gap = []
    for _ in range(5):
        cli, _, _ = dung(file_token, [kich.pop(0)] if _ != 2 else [kich.pop(0), kich.pop(0), kich.pop(0)])
        with pytest.raises(LoiEchoTik) as e:
            cli.chi_tiet(UID)
        gap.append(e.value)
    for ex in gap:
        for s in (str(ex), repr(ex), repr(ex.args), ex.ma):
            assert TOKEN_GIA not in s and "Bearer" not in s and "secret" not in s
        assert len(str(ex)) < 80
        assert ex.__cause__ is None and (ex.__context__ is None or ex.__suppress_context__)
    cli, _, _ = dung(file_token, [])
    assert TOKEN_GIA not in repr(cli) and TOKEN_GIA not in str(cli)
    assert TOKEN_GIA not in caplog.text
    cap = capsys.readouterr()
    assert cap.out == "" and cap.err == ""


def test_khong_co_print_trong_module():
    cay = ast.parse(Path(echotik.__file__).read_text(encoding="utf-8"))
    for n in ast.walk(cay):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            assert n.func.id != "print"


# ------------------------------------------------------------------ token file


def test_thieu_file_token(tmp_path):
    cli, mang, _ = dung(tmp_path / "khong_co.json", [])
    with pytest.raises(LoiEchoTik) as e:
        cli.chi_tiet(UID)
    assert e.value.ma == "token_thieu" and mang.yeu_cau == []


@pytest.mark.parametrize("noi_dung", ["{hong", json.dumps({"user_id": "1"}), json.dumps({"token": "  "}), "[]"])
def test_file_token_hong_hoac_thieu_khoa(tmp_path, noi_dung):
    p = tmp_path / "t.json"
    p.write_text(noi_dung, encoding="utf-8")
    cli, mang, _ = dung(p, [])
    with pytest.raises(LoiEchoTik) as e:
        cli.chi_tiet(UID)
    assert e.value.ma == "token_thieu" and mang.yeu_cau == []


def test_doc_file_token_moi_lan_goi_nhan_token_moi_khi_doi_mtime(file_token):
    cli, mang, _ = dung(file_token, [PhanHoi(body=E1_OK), PhanHoi(body=E1_OK), PhanHoi(body=E1_OK)])
    cli.chi_tiet(UID)
    cli.chi_tiet(UID)                      # file không đổi: vẫn token cũ (cache theo mtime)
    st = file_token.stat()
    file_token.write_text(json.dumps({"token": TOKEN_GIA_2, "user_id": "u-2"}), encoding="utf-8")
    os.utime(file_token, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    cli.chi_tiet(UID)
    auth = [dict((k.lower(), v) for k, v in r.header_items())["authorization"] for r in mang.yeu_cau]
    assert auth == ["Bearer " + TOKEN_GIA, "Bearer " + TOKEN_GIA, "Bearer " + TOKEN_GIA_2]


def test_file_token_bi_xoa_giua_chung_thanh_token_thieu(file_token):
    cli, _, _ = dung(file_token, [PhanHoi(body=E1_OK), PhanHoi(body=E1_OK)])
    cli.chi_tiet(UID)
    file_token.unlink()
    with pytest.raises(LoiEchoTik) as e:
        cli.chi_tiet(UID)
    assert e.value.ma == "token_thieu"


# ------------------------------------------------------------------ nhịp


def test_cach_toi_thieu_1_3s_giua_cac_get(file_token):
    cli, mang, dh = dung(file_token, [PhanHoi(body=E1_OK), PhanHoi(body=E2_OK), PhanHoi(body=E4_OK)])
    cli.chi_tiet(UID)
    cli.video(UID)
    cli.tim("binh")
    assert len(mang.gio_goi) == 3
    for a, b in zip(mang.gio_goi, mang.gio_goi[1:]):
        assert b - a >= 1.3 - 1e-9
    assert cli.so_goi == 3


def test_khong_cho_them_khi_da_qua_1_3s(file_token):
    cli, mang, dh = dung(file_token, [PhanHoi(body=E1_OK), PhanHoi(body=E1_OK)])
    cli.chi_tiet(UID)
    dh.t += 10.0
    cli.chi_tiet(UID)
    assert dh.ngu_goi == []


def test_cach_toi_thieu_tuy_chinh(file_token):
    cli, mang, dh = dung(file_token, [PhanHoi(body=E1_OK), PhanHoi(body=E1_OK)], cach_toi_thieu_s=2.5)
    cli.chi_tiet(UID)
    cli.chi_tiet(UID)
    assert mang.gio_goi[1] - mang.gio_goi[0] >= 2.5 - 1e-9


# ------------------------------------------------------------------ video / tim / meta


def test_video_tra_list_va_meta(file_token):
    cli, _, _ = dung(file_token, [PhanHoi(body=E2_OK)])
    ds, meta = cli.video(UID)
    assert len(ds) == 2 and ds[0]["video_id"] == "7400000000000000001"
    assert meta == {"current_page": 1, "last_page": 1}


def test_video_khong_co_meta(file_token):
    cli, _, _ = dung(file_token, [PhanHoi(body={"data": E2_OK["data"]})])
    ds, meta = cli.video(UID)
    assert len(ds) == 2 and meta == {"current_page": None, "last_page": None}


def test_video_data_rong_hop_le(file_token):
    cli, _, _ = dung(file_token, [PhanHoi(body={"data": [], "meta": {"current_page": 2, "last_page": 1}})])
    ds, meta = cli.video(UID, trang=2)
    assert ds == [] and meta["current_page"] == 2


def test_tim_tra_list_va_meta_none_khi_chua_co(file_token):
    cli, _, _ = dung(file_token, [PhanHoi(body=E4_OK)])
    ds, meta = cli.tim("binh giu nhiet")
    assert ds[0]["product_id"] == UID and meta == {"current_page": None, "last_page": None}


def test_chuan_meta():
    assert chuan_meta({"current_page": 1, "last_page": 3, "from": 1, "links": []}) == {"current_page": 1, "last_page": 3}
    assert chuan_meta({"current_page": "2", "last_page": "5"}) == {"current_page": 2, "last_page": 5}
    for xau in (None, [], "x", 3, {}, {"current_page": None}, {"last_page": True}, {"last_page": "abc"}, {"last_page": -1}):
        r = chuan_meta(xau)
        assert set(r) == {"current_page", "last_page"}
        assert r["last_page"] is None
    assert chuan_meta({"current_page": 1})["last_page"] is None


# ------------------------------------------------------------------ chuan_video


def test_chuan_video_view_chuoi_rut_gon_va_bo_update_time():
    h = chuan_video(E2_OK["data"][0])
    assert h == {"video_id": "7400000000000000001", "creator": "abc", "follower": "2.54K", "view": "21.81K",
                 "ban": None, "dang_luc": "2026-07-18 10:00:00", "is_promote": 0}
    assert "update_time" not in h


def test_chuan_video_view_int_thanh_chuoi_va_is_promote():
    h = chuan_video(E2_OK["data"][1])
    assert h["view"] == "326" and isinstance(h["view"], str)
    assert h["is_promote"] == 1 and h["follower"] == "N/A"


def test_chuan_video_id_19_so_la_chuoi_ke_ca_khi_la_int():
    h = chuan_video({"video_id": 7400000000000000001, "views_count": 5, "publish_time": "2026-01-01 00:00:00",
                     "influencer": {"unique_id": "u"}})
    assert h["video_id"] == "7400000000000000001" and isinstance(h["video_id"], str)


def test_chuan_video_truong_thieu_la_none_khong_phai_0():
    h = chuan_video({"video_id": "7400000000000000009", "views_count": "9.4K", "publish_time": "2026-01-01 00:00:00"})
    assert h["follower"] is None and h["ban"] is None and h["is_promote"] is None
    assert h["view"] == "9.4K"
    h2 = chuan_video({"video_id": "7400000000000000009", "views_count": 0, "publish_time": "x",
                      "influencer": {"unique_id": "u", "follower_count": None}, "is_promote": None, "sales": 12})
    assert h2["view"] == "0" and h2["follower"] is None and h2["is_promote"] is None and h2["ban"] == "12"


@pytest.mark.parametrize("bo", ["video_id", "publish_time"])
def test_chuan_video_thieu_khoa_bat_buoc_la_none(bo):
    raw = dict(E2_OK["data"][0])
    raw.pop(bo)
    assert chuan_video(raw) is None
    raw[bo] = ""
    assert chuan_video(raw) is None


def test_chuan_video_thieu_view_thi_bo_chu_khong_dien_0():
    raw = dict(E2_OK["data"][0])
    raw.pop("views_count")
    assert chuan_video(raw) is None
    raw["views_count"] = None
    assert chuan_video(raw) is None


def test_chuan_video_dau_vao_rac():
    for x in (None, [], "x", 5, {}):
        assert chuan_video(x) is None
    assert chuan_video({"video_id": True, "views_count": 1, "publish_time": "p"}) is None


def test_chuan_video_creator_du_phong():
    base = {"video_id": "7400000000000000003", "views_count": 1, "publish_time": "p"}
    assert chuan_video({**base, "influencer_name": "Ten"})["creator"] == "Ten"
    assert chuan_video({**base, "influencer_id": "123"})["creator"] == "123"
    assert chuan_video({**base})["creator"] == ""


# ------------------------------------------------------------------ chuan_ung_vien


def test_chuan_ung_vien():
    u = chuan_ung_vien(E4_OK["data"][0])
    assert u == {"uid": UID, "ten": "Binh giu nhiet 500ml", "gia": "$12.7", "ban_7d": "36"}


def test_chuan_ung_vien_ban_7d_so_va_thieu():
    u = chuan_ung_vien({"product_id": UID, "product_name": "A", "total_sale_7d_cnt": 36})
    assert u["ban_7d"] == "36" and u["gia"] is None
    u2 = chuan_ung_vien({"product_id": UID, "product_name": "A", "avg_price": "$1", "total_sale_7d_cnt": None})
    assert u2["ban_7d"] is None


def test_chuan_ung_vien_id_phai_19_so_chuoi():
    assert chuan_ung_vien({"product_id": 1729420930611055346, "product_name": "A"})["uid"] == UID
    for pid in ("123", "abc", None, "", UID + "1", True):
        assert chuan_ung_vien({"product_id": pid, "product_name": "A"}) is None
    assert chuan_ung_vien({"product_id": UID}) is None
    assert chuan_ung_vien({"product_id": UID, "product_name": ""}) is None
    assert chuan_ung_vien(None) is None


# ------------------------------------------------------------------ ảnh bìa (RU-A5)
ANH = "https://cdn.echotik.live/abc/def/product-cover/138/1729420930611055346_0.webp"


def test_anh_bia_lay_images_0():
    assert anh_bia({"images": [ANH, "https://cdn.echotik.live/x"]}) == ANH


@pytest.mark.parametrize("e1", [None, [], "x", {}, {"images": None}, {"images": []}, {"images": "u"}, {"images": {"0": ANH}},
                                {"images": [None, ANH]}, {"images": [""]}, {"images": ["  "]}, {"images": [5]}])
def test_anh_bia_du_lieu_la_thi_rong(e1):
    assert anh_bia(e1) == ""


def test_anh_bia_khong_kiem_host():
    assert anh_bia({"images": ["http://evil.example/a.png"]}) == "http://evil.example/a.png"


def test_anh_ung_vien_cover_url_va_khong_doi_khoa_ung_vien():
    raw = {**E4_OK["data"][0], "cover_url": ANH}
    assert anh_ung_vien(raw) == ANH
    assert set(chuan_ung_vien(raw)) == {"uid", "ten", "gia", "ban_7d"}      # UngVien (§7.2) KHÔNG đổi khoá
    for x in (None, [], {}, {"cover_url": None}, {"cover_url": ""}, {"cover_url": 5}, {"cover_url": [ANH]}):
        assert anh_ung_vien(x) == ""


def test_chi_so_them_chi_lay_khoa_duyet_va_bo_khoa_thieu():
    from runner.echotik import chi_so_them
    e1 = {"sale_30d_cnt": "2.86K", "gmv_30d_amt": "$15.21K", "ifl_30d_cnt": 12, "total_ifl_cnt": 29, "video_30d_cnt": 49,
          "total_video_cnt": 105, "review_count": 539, "original_price": "155.579₫", "labels": {"rating": 4.5,
          "total_category_sale_rank": 258}, "token": "bí-mật", "seller": {"x": 1}, "total_live_cnt": None,
          "live_30d_cnt": True, "gmv_amt": "x" * 40}
    r = chi_so_them(e1)
    assert r == {"sale_30d_cnt": "2.86K", "gmv_30d_amt": "$15.21K", "ifl_30d_cnt": 12, "total_ifl_cnt": 29,
                 "video_30d_cnt": 49, "total_video_cnt": 105, "review_count": 539, "original_price": "155.579₫",
                 "rating": 4.5, "hang_nganh": 258}
    assert chi_so_them({}) == {} and chi_so_them(None) == {} and chi_so_them({"labels": "x"}) == {}
