"""Test HTTP API runner (B-2, docs/bo-chay-viec.md §8.1, §4.3, §8.3).

Chạy: python -B -m pytest tools/test_runner_api.py -q

Server THẬT (ThreadingHTTPServer) ở 127.0.0.1 cổng ngẫu nhiên; DB SQLite trong tmp_path;
khoá runner + khoá Ed25519 đều sinh trong test (không đụng %LOCALAPPDATA%\\kho-runner, không cổng 8788).
"""
import hashlib
import http.client
import json
import re
import secrets
import sys
import threading
import time
import uuid
from dataclasses import replace
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).parent))
from runner import api  # noqa: E402
from runner import chu_ky  # noqa: E402
from runner import danh_muc as dm  # noqa: E402
from runner.du_an import ma_du_an  # noqa: E402
from runner.han_muc import HAN_MUC_TRAN  # noqa: E402
from runner.kho_viec import KhoViec  # noqa: E402
from runner.kieu import CanNguoiDung, MoiTruong  # noqa: E402

UID = "1729420930611055346"
UID2 = "1729999999999999999"
ME = "20261117-a"


class Dong:
    def __init__(self, luc: datetime):
        self.luc = luc

    def __call__(self) -> datetime:
        return self.luc

    def toi(self, giay: float) -> None:
        self.luc += timedelta(seconds=giay)


def _b64url(b: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


@pytest.fixture(autouse=True)
def _du_lieu_tam(tmp_path, monkeypatch):
    monkeypatch.setenv("KHO_RUNNER_DIR", str(tmp_path / "du_lieu"))


@pytest.fixture
def dong():
    return Dong(datetime(2026, 11, 17, 9, 0, 0))


@pytest.fixture
def mt(tmp_path, dong):
    goc = tmp_path / "goc1"
    p = goc / f"Bình nước {UID}"
    (p / "kich-ban").mkdir(parents=True)
    (p / "kich-ban" / "poster_captions.txt").write_text("cap\n", encoding="utf-8")
    (p / "kich-ban" / f"{ME}_kich-ban-da-cham.md").write_text("x", encoding="utf-8")
    repo = tmp_path / "repo"
    (repo / "data" / UID).mkdir(parents=True)
    (repo / "tools").mkdir()
    sp = tmp_path / "pcq"
    (sp / f"sp_{UID}").mkdir(parents=True)
    radar = tmp_path / "radar_goc"
    radar.mkdir()
    cong = {8023: True, 7890: True}
    st = {"ffmpeg": False, "kho": None}
    m = MoiTruong(
        gocs=[goc], repo_kho=repo, thu_muc_scripts=tmp_path / "scripts",
        python_poster=tmp_path / "poster" / "python.exe", claude_exe=tmp_path / "claude.exe",
        agy_exe=tmp_path / "agy.exe", thu_muc_radar=radar, thu_muc_sp=sp, thu_muc_du_lieu=tmp_path / "du_lieu",
        cong_song=lambda c: cong.get(c, False), chan_doan_kho=lambda _r: st["kho"],
        ffmpeg_ngoai=lambda: st["ffmpeg"], thoi_luong_media=lambda f: 3.0, bay_gio=dong)
    m._cong = cong  # type: ignore[attr-defined]
    m._st = st  # type: ignore[attr-defined]
    m._p = p  # type: ignore[attr-defined]
    return m


class May:
    """Server API thật + client ký request như Worker."""

    def __init__(self, tmp_path, mt, dong, hm=None, trang_thai_lan=None, doc_log=None, che=None):
        self.kho = KhoViec(tmp_path / "du_lieu" / "runner.db", dong)
        self.mt = mt
        self.khoa_runner = secrets.token_hex(32)
        self.khoa_ky = Ed25519PrivateKey.generate()
        self.huy: list[str] = []
        self.goi_log: list[tuple[str, int]] = []
        self.hm = dict(HAN_MUC_TRAN) if hm is None else hm
        self.canh_bao = ["cau_hinh.json: thử cảnh báo"]

        def _doc_log(id_, tu):
            self.goi_log.append((id_, tu))
            return {"tu": tu, "den": tu + 3, "noi_dung": "abc", "het": True}

        H = api.tao_handler(self.kho, mt, self.khoa_runner, self.khoa_ky.public_key(), self.hm, self.canh_bao,
                            self.huy.append, doc_log or _doc_log,
                            trang_thai_lan or (lambda: {"lan": {"gpu": None, "nhe": None},
                                                        "tai_nguyen": {"kho": False, "poster": False},
                                                        "tam_dung_claude_den": None}),
                            **({} if che is None else {"che": che}))
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.cong = self.srv.server_address[1]
        self.t = threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.t.start()

    def dong_lai(self):
        self.srv.shutdown()
        self.srv.server_close()

    def goi(self, method, path, body=None, *, khoa=True, ky=True, headers=None, raw=None,
            khoa_ky=None, ngay_ms=None, nonce=None):
        h = {}
        if khoa is True:
            h["x-runner-key"] = self.khoa_runner
        elif isinstance(khoa, str):
            h["x-runner-key"] = khoa
        data = raw if raw is not None else (None if body is None else
                                            json.dumps(body, ensure_ascii=False).encode("utf-8"))
        if method == "POST":
            data = data if data is not None else b""
            h["content-type"] = "application/json"
            if ky:
                ngay = int(time.time() * 1000) if ngay_ms is None else ngay_ms
                n = nonce or secrets.token_hex(16)
                duong = path.split("?")[0]
                chuoi = chu_ky.chuoi_ky_request("POST", duong, ngay, n, data)
                h.update({"x-ky-ngay": str(ngay), "x-ky-nonce": n,
                          "x-ky": _b64url((khoa_ky or self.khoa_ky).sign(chuoi))})
        h.update(headers or {})
        c = http.client.HTTPConnection("127.0.0.1", self.cong, timeout=10)
        try:
            c.request(method, path, body=data, headers=h)
            r = c.getresponse()
            noi = r.read()
            ct = r.getheader("content-type") or ""
        finally:
            c.close()
        assert ct.startswith("application/json"), (r.status, ct, noi[:200])
        return r.status, json.loads(noi.decode("utf-8"))


@pytest.fixture
def may(tmp_path, mt, dong):
    m = May(tmp_path, mt, dong)
    yield m
    m.dong_lai()


def _tao(may, loai="phan_tich_uid", tham_so=None, boi="nhan"):
    return may.goi("POST", "/viec", {"loai": loai, "tham_so": {"uid": UID} if tham_so is None else tham_so,
                                     "boi": boi})


def _vao_can_tra_loi(may, id_, cau_hoi: CanNguoiDung):
    may.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    may.kho.chuyen(id_, ["dang_chay"], "can_tra_loi", "he_thong", cau_hoi=cau_hoi)


# ---------- x-runner-key ----------

def test_get_thieu_hoac_sai_khoa_runner_401(may):
    assert may.goi("GET", "/suc-khoe", khoa=False)[0] == 401
    assert may.goi("GET", "/suc-khoe", khoa="sai")[0] == 401
    assert may.goi("GET", "/danh-muc", khoa=may.khoa_runner + "x")[0] == 401
    # khoá sai thì đường lạ cũng 401 (không lộ danh sách route)
    assert may.goi("GET", "/khong-co", khoa=False)[0] == 401
    assert may.goi("GET", "/khong-co")[0] == 404


def test_khoa_runner_so_hang_thoi_gian(may, monkeypatch):
    goi = []
    goc = api.hmac.compare_digest

    def ghi(a, b):
        goi.append((type(a), type(b)))
        return goc(a, b)

    monkeypatch.setattr(api.hmac, "compare_digest", ghi)
    assert may.goi("GET", "/suc-khoe")[0] == 200
    assert goi and goi[0] == (bytes, bytes)


def test_get_khong_can_chu_ky(may):
    assert may.goi("GET", "/danh-muc")[0] == 200


# ---------- chữ ký POST ----------

def test_post_khong_chu_ky_401_va_khong_tao(may):
    s, d = may.goi("POST", "/viec", {"loai": "phan_tich_uid", "tham_so": {"uid": UID}, "boi": "nhan"}, ky=False)
    assert s == 401 and "loi" in d
    assert may.kho.ds() == []


def test_post_sai_chu_ky_401(may):
    khac = Ed25519PrivateKey.generate()
    s, _ = may.goi("POST", "/viec", {"loai": "phan_tich_uid", "tham_so": {"uid": UID}, "boi": "nhan"},
                   khoa_ky=khac)
    assert s == 401 and may.kho.ds() == []


def test_post_nonce_lap_401(may):
    n = secrets.token_hex(16)
    s1, _ = may.goi("POST", "/viec", {"loai": "phan_tich_uid", "tham_so": {"uid": UID}, "boi": "nhan"}, nonce=n)
    s2, _ = may.goi("POST", "/viec", {"loai": "douyin_uid", "tham_so": {"uid": UID}, "boi": "nhan"}, nonce=n)
    assert (s1, s2) == (201, 401)
    assert [v["loai"] for v in may.kho.ds()] == ["phan_tich_uid"]


def test_post_lech_gio_401(may):
    s, _ = may.goi("POST", "/viec", {"loai": "phan_tich_uid", "tham_so": {"uid": UID}, "boi": "nhan"},
                   ngay_ms=int(time.time() * 1000) - 121_000)
    assert s == 401 and may.kho.ds() == []


def test_post_chu_ky_dung_nhung_body_khac_401(may):
    """Ký body A, gửi body B (đổi boi) → 401: boi chỉ được tin khi nằm trong body đã ký."""
    ky_tren = json.dumps({"loai": "phan_tich_uid", "tham_so": {"uid": UID}, "boi": "nhan"}).encode()
    gui = json.dumps({"loai": "phan_tich_uid", "tham_so": {"uid": UID}, "boi": "comeofage"}).encode()
    ngay, n = int(time.time() * 1000), secrets.token_hex(16)
    ky = _b64url(may.khoa_ky.sign(chu_ky.chuoi_ky_request("POST", "/viec", ngay, n, ky_tren)))
    s, _ = may.goi("POST", "/viec", raw=gui, ky=False, headers={"x-ky-ngay": str(ngay), "x-ky-nonce": n, "x-ky": ky})
    assert s == 401 and may.kho.ds() == []


def test_post_chu_ky_sai_path_401(may):
    """Chữ ký cho /viec không dùng được cho /viec/<id>/huy."""
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    body = json.dumps({"boi": "nhan"}).encode()
    ngay, n = int(time.time() * 1000), secrets.token_hex(16)
    ky = _b64url(may.khoa_ky.sign(chu_ky.chuoi_ky_request("POST", "/viec", ngay, n, body)))
    s, _ = may.goi("POST", f"/viec/{id_}/huy", raw=body, ky=False,
                   headers={"x-ky-ngay": str(ngay), "x-ky-nonce": n, "x-ky": ky})
    assert s == 401 and may.kho.lay(id_)["trang_thai"] == "cho"


def test_post_thieu_khoa_runner_401_du_chu_ky_dung(may):
    s, _ = may.goi("POST", "/viec", {"loai": "phan_tich_uid", "tham_so": {"uid": UID}, "boi": "nhan"}, khoa=False)
    assert s == 401 and may.kho.ds() == []


def test_post_body_qua_lon_413(may):
    s, _ = may.goi("POST", "/viec", raw=b'{"a":"' + b"x" * (17 * 1024) + b'"}')
    assert s == 413


def test_post_body_khong_phai_json_object_400(may):
    assert may.goi("POST", "/viec", raw=b"khong-json")[0] == 400
    assert may.goi("POST", "/viec", raw=b"[1,2]")[0] == 400


# ---------- GET /suc-khoe, /danh-muc, /du-an, /poster/folders ----------

def test_suc_khoe(may):
    _tao(may)
    s, d = may.goi("GET", "/suc-khoe")
    assert s == 200
    for k in ("luc", "phien_ban", "lan", "tai_nguyen", "dem", "chi_phi_hom_nay_usd", "viec_claude_hom_nay",
              "han_muc", "tam_dung_claude_den", "dot_bat", "canh_bao"):
        assert k in d, k
    assert d["lan"] == {"gpu": None, "nhe": None} and d["tai_nguyen"] == {"kho": False, "poster": False}
    assert d["dem"]["cho"] == 1 and d["dot_bat"] == 3 and d["chi_phi_hom_nay_usd"] == 0
    assert d["canh_bao"] == ["cau_hinh.json: thử cảnh báo"]
    assert d["han_muc"]["claude_viec_ngay"] == 12
    assert d["luc"] == "2026-11-17T09:00:00+07:00" and d["phien_ban"] == "nguon"


def test_danh_muc_dot_3(may):
    s, d = may.goi("GET", "/danh-muc")
    assert s == 200
    ma = {x["ma"] for x in d["loai"]}
    assert ma == {"radar_ban_tin", "phan_tich_uid", "douyin_uid", "xu_ly_link_moi", "poster_day_folder", "voice_pv"}
    r = next(x for x in d["loai"] if x["ma"] == "radar_ban_tin")
    assert set(r) == {"ma", "ten", "dot", "ton_tien", "lan_chay", "tham_so"}
    assert [t["ten"] for t in r["tham_so"]] == ["top_n", "chay_bu"]


def test_danh_muc_an_dot_cao_hon_dot_bat(tmp_path, mt, dong, monkeypatch):
    monkeypatch.setitem(dm.DANH_MUC, "thu_dot4", replace(dm.DANH_MUC["phan_tich_uid"], ma="thu_dot4", dot=4))
    m = May(tmp_path, mt, dong)
    try:
        assert "thu_dot4" not in {x["ma"] for x in m.goi("GET", "/danh-muc")[1]["loai"]}
        s, _ = _tao(m, loai="thu_dot4")
        assert s == 400 and m.kho.ds() == []
    finally:
        m.dong_lai()
    # hm nới dot_bat quá trần code (dict truyền vào bị sửa) vẫn không mở đợt 4
    m2 = May(tmp_path / "b", mt, dong, hm={**HAN_MUC_TRAN, "dot_bat": 9})
    try:
        assert "thu_dot4" not in {x["ma"] for x in m2.goi("GET", "/danh-muc")[1]["loai"]}
    finally:
        m2.dong_lai()
    # hạ dot_bat = 2 → ẩn hết đợt 3
    m3 = May(tmp_path / "c", mt, dong, hm={**HAN_MUC_TRAN, "dot_bat": 2})
    try:
        assert m3.goi("GET", "/danh-muc")[1]["loai"] == []
        assert _tao(m3)[0] == 400
    finally:
        m3.dong_lai()


def test_du_an(may, mt):
    s, d = may.goi("GET", f"/du-an/{UID}")
    assert s == 200
    assert [x["ma"] for x in d["du_an"]] == [ma_du_an(mt._p)]
    assert d["du_an"][0]["me"] == [ME] and d["du_an"][0]["co_captions"] is True
    assert may.goi("GET", f"/du-an/{UID2}")[1] == {"du_an": []}
    assert may.goi("GET", "/du-an/123")[0] == 404


def test_poster_folders_va_duyet_404_o_dot_3(may):
    assert may.goi("GET", "/poster/folders")[0] == 404
    _, d = _tao(may)
    s, _ = may.goi("POST", f"/viec/{d['viec']['id']}/duyet",
                   {"loi_duyet": "ok", "duyet_luc": "x", "boi": "nhan", "chu_ky_duyet": "x"})
    assert s == 404


def test_route_la_va_method_la(may):
    assert may.goi("GET", "/viec/j2026/log")[0] == 404
    assert may.goi("POST", "/khong-co", {"boi": "nhan"})[0] == 404
    assert may.goi("GET", "/viec/j20261117090000abcd/huy")[0] in (404, 405)


# ---------- POST /viec ----------

def test_tao_viec_claude(may):
    s, d = _tao(may)
    assert s == 201
    v = d["viec"]
    assert v["loai"] == "phan_tich_uid" and v["trang_thai"] == "cho" and v["khoa"] == UID
    assert v["tao_boi"] == "nhan" and v["tham_so"] == {"uid": UID}
    for an in ("pid", "pid_tao_luc", "session_id", "chu_ky_duyet"):
        assert an not in v
    assert v["co_session"] is True and v["co_the_chay_tiep"] is False
    sid = may.kho.lay(v["id"])["session_id"]
    assert uuid.UUID(sid).version == 4


def test_tao_viec_khong_claude_khong_session(may):
    s, d = _tao(may, loai="douyin_uid")
    assert s == 201 and d["viec"]["co_session"] is False
    assert may.kho.lay(d["viec"]["id"])["session_id"] is None


def test_tao_boi_lay_tu_body_da_ky(may):
    s, d = _tao(may, boi="comeofage")
    assert s == 201 and d["viec"]["tao_boi"] == "comeofage"
    assert may.kho.su_kien(d["viec"]["id"])[0]["boi"] == "comeofage"


@pytest.mark.parametrize("body", [
    {"loai": "khong_co", "tham_so": {}, "boi": "nhan"},
    {"loai": "phan_tich_uid", "tham_so": {"uid": "123"}, "boi": "nhan"},
    {"loai": "phan_tich_uid", "tham_so": {"uid": UID, "x": 1}, "boi": "nhan"},
    {"loai": "phan_tich_uid", "tham_so": [UID], "boi": "nhan"},
    {"loai": "radar_ban_tin", "tham_so": {"top_n": 10, "ngay_tao": "2020-01-01"}, "boi": "nhan"},
    {"loai": "radar_ban_tin", "tham_so": {"top_n": 4}, "boi": "nhan"},
    {"loai": "phan_tich_uid", "tham_so": {"uid": UID}},
    {"loai": "phan_tich_uid", "tham_so": {"uid": UID}, "boi": ""},
    {"loai": "phan_tich_uid", "tham_so": {"uid": UID}, "boi": "a\nb"},
    {"loai": 5, "tham_so": {"uid": UID}, "boi": "nhan"},
    {"tham_so": {"uid": UID}, "boi": "nhan"},
])
def test_tao_tham_so_sai_400(may, body):
    s, d = may.goi("POST", "/viec", body)
    assert s == 400 and "loi" in d
    assert may.kho.ds() == []


def test_tao_radar_gan_ngay_tao(may):
    s, d = _tao(may, loai="radar_ban_tin", tham_so={"top_n": 12})
    assert s == 201
    assert d["viec"]["tham_so"] == {"top_n": 12, "chay_bu": False, "ngay_tao": "2026-11-17"}
    assert d["viec"]["khoa"] == "2026-11-17"


def test_tao_trung_409(may):
    _, d1 = _tao(may)
    s, d = _tao(may)
    assert s == 409 and d["trung"]["id"] == d1["viec"]["id"]
    assert "session_id" not in d["trung"]


def test_tao_vuot_han_muc_429(tmp_path, mt, dong):
    m = May(tmp_path, mt, dong, hm={**HAN_MUC_TRAN, "viec_tao_ngay_moi_nguoi": 1})
    try:
        assert _tao(m, boi="nhan")[0] == 201
        s, d = _tao(m, loai="douyin_uid", boi="nhan")
        assert s == 429 and "loi" in d
        assert _tao(m, loai="douyin_uid", boi="comeofage")[0] == 201
    finally:
        m.dong_lai()


def test_tao_dieu_kien_truoc_hong_vao_can_tra_loi(may, mt):
    mt._cong[8023] = False
    s, d = _tao(may, loai="poster_day_folder", tham_so={"uid": UID, "du_an": ma_du_an(mt._p)})
    assert s == 201
    v = d["viec"]
    assert v["trang_thai"] == "can_tra_loi" and v["cau_hoi"]["loai"] == "viec_tay"
    assert "8023" in v["cau_hoi"]["noi_dung"]


def test_tao_dieu_kien_truoc_ban_van_cho(may, mt):
    mt._st["kho"] = "ban"
    s, d = _tao(may, loai="xu_ly_link_moi", tham_so={})
    assert s == 201 and d["viec"]["trang_thai"] == "cho"


def test_tao_dieu_kien_kho_viec_tay(may, mt):
    mt._st["kho"] = CanNguoiDung("viec_tay", "Có khoá git cũ")
    s, d = _tao(may)
    assert s == 201 and d["viec"]["trang_thai"] == "can_tra_loi"
    assert d["viec"]["cau_hoi"] == {"loai": "viec_tay", "noi_dung": "Có khoá git cũ", "lua_chon": []}


# ---------- GET /viec, /viec/<id>, /log ----------

def test_ds_viec_va_loc(may, mt):
    _, a = _tao(may)
    _, b = _tao(may, loai="voice_pv", tham_so={"uid": UID, "du_an": ma_du_an(mt._p), "me": ME})
    _, c = _tao(may, loai="xu_ly_link_moi", tham_so={})
    may.kho.chuyen(c["viec"]["id"], ["cho"], "huy", "nhan")
    s, d = may.goi("GET", "/viec")
    assert s == 200 and len(d["viec"]) == 3
    assert all("session_id" not in v and "pid" not in v for v in d["viec"])
    assert {v["id"] for v in may.goi("GET", "/viec?trang_thai=huy")[1]["viec"]} == {c["viec"]["id"]}
    assert len(may.goi("GET", "/viec?trang_thai=cho,huy")[1]["viec"]) == 3
    assert {v["id"] for v in may.goi("GET", f"/viec?uid={UID}")[1]["viec"]} == {a["viec"]["id"], b["viec"]["id"]}
    assert len(may.goi("GET", "/viec?gioi_han=1")[1]["viec"]) == 1
    s, d = may.goi("GET", "/viec?tom_tat=1")
    assert s == 200 and d["dem"]["cho"] == 2 and d["dem"]["huy"] == 1 and "viec" not in d
    for q in ("trang_thai=la", "uid=12", "gioi_han=abc", "gioi_han=0"):
        assert may.goi("GET", f"/viec?{q}")[0] == 400, q


def test_chi_tiet_viec(may):
    _, d = _tao(may, loai="radar_ban_tin", tham_so={"top_n": 7})
    id_ = d["viec"]["id"]
    s, d = may.goi("GET", f"/viec/{id_}")
    assert s == 200
    assert d["viec"]["id"] == id_ and d["tra_loi"] == [] and "xem_truoc" in d
    assert d["tham_so_chuan"] == dm.tham_so_chuan({"top_n": 7, "chay_bu": False, "ngay_tao": "2026-11-17"})
    assert d["tham_so_chuan"] == '{"chay_bu":false,"ngay_tao":"2026-11-17","top_n":7}'
    assert d["su_kien"][0]["den"] == "cho"
    assert may.goi("GET", "/viec/j20261117090000zzzz")[0] == 404


def _tu_choi_tho(n: int) -> list:
    """Dạng permission_denials thô của claude (dữ liệu cũ có thể đã lưu nguyên vào DB)."""
    ds: list = []
    for i in range(n):
        if i % 3 == 0:
            ds.append({"tool_name": "Bash", "tool_use_id": f"toolu_{i}", "tool_input": {"command": "x" * 500}})
        elif i % 3 == 1:
            ds.append({"tool_name": "Write", "tool_use_id": f"toolu_{i}",
                       "tool_input": {"file_path": f"C:/a/{i}.md", "content": "bí mật " * 200}})
        else:
            ds.append({"tool_name": "mcp__engram__mem_save", "tool_input": {"title": "t", "content": "y" * 900}})
    return ds


def test_bi_tu_choi_gon_ham_thuan():
    g = api.bi_tu_choi_gon(_tu_choi_tho(25) + ["chuoi", None, 7])
    assert len(g) == api.BI_TU_CHOI_TOI_DA == 20
    assert all(set(x) == {"tool_name", "input"} for x in g)
    assert all(isinstance(x["input"], str) and len(x["input"]) <= 200 for x in g)
    assert g[0] == {"tool_name": "Bash", "input": "x" * 200}
    assert g[1] == {"tool_name": "Write", "input": "C:/a/1.md"}
    assert g[2]["tool_name"] == "mcp__engram__mem_save" and len(g[2]["input"]) == 200
    # dạng đã gọn (spike) giữ nguyên; kiểu lạ → rỗng
    assert api.bi_tu_choi_gon([{"tool_name": "Edit", "input": "abc"}]) == [{"tool_name": "Edit", "input": "abc"}]
    assert api.bi_tu_choi_gon(None) == [] and api.bi_tu_choi_gon("x") == [] and api.bi_tu_choi_gon({}) == []
    assert api.bi_tu_choi_gon([{"tool_name": 5, "tool_input": "z" * 300}]) == [{"tool_name": "5", "input": "z" * 200}]


def test_viec_ra_khong_sua_dict_goc():
    v = {"id": "j1", "trang_thai": "loi", "ket_qua": {"tom_tat": "t", "bi_tu_choi": _tu_choi_tho(3)}}
    ds = api.viec_ra(v, chi_tiet=False)
    ct = api.viec_ra(v)
    assert "bi_tu_choi" not in ds["ket_qua"] and ds["ket_qua"]["tom_tat"] == "t"
    assert len(ct["ket_qua"]["bi_tu_choi"]) == 3
    assert "tool_use_id" in v["ket_qua"]["bi_tu_choi"][0]          # dict gốc không bị đổi
    assert api.viec_ra({"id": "j2", "ket_qua": None})["ket_qua"] is None


def test_ds_viec_khong_tra_bi_tu_choi_chi_tiet_thi_gon(may):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    may.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    may.kho.chuyen(id_, ["dang_chay"], "loi", "he_thong",
                   ket_qua={"tom_tat": "hỏng", "chi_phi_usd_luot": 0.5, "bi_tu_choi": _tu_choi_tho(25)})
    s, d = may.goi("GET", "/viec")
    assert s == 200
    (v,) = [x for x in d["viec"] if x["id"] == id_]
    assert v["ket_qua"] == {"tom_tat": "hỏng", "chi_phi_usd_luot": 0.5}
    s, d = may.goi("GET", f"/viec/{id_}")
    assert s == 200
    btc = d["viec"]["ket_qua"]["bi_tu_choi"]
    assert len(btc) == 20 and all(set(x) == {"tool_name", "input"} and len(x["input"]) <= 200 for x in btc)
    assert "bí mật" not in json.dumps(d, ensure_ascii=False)
    assert d["viec"]["ket_qua"]["tom_tat"] == "hỏng"


def test_log(may):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    s, d = may.goi("GET", f"/viec/{id_}/log?tu=5")
    assert s == 200 and d == {"tu": 5, "den": 8, "noi_dung": "abc", "het": True}
    assert may.goi("GET", f"/viec/{id_}/log")[0] == 200
    assert may.goi_log == [(id_, 5), (id_, 0)]
    assert may.goi("GET", f"/viec/{id_}/log?tu=-1")[0] == 400
    assert may.goi("GET", f"/viec/{id_}/log?tu=x")[0] == 400
    assert may.goi("GET", "/viec/j20261117090000zzzz/log")[0] == 404


# ---------- tra-loi ----------

def test_tra_loi_viec_tay(may):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    _vao_can_tra_loi(may, id_, CanNguoiDung("viec_tay", "Mở Poster"))
    s, d = may.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "da_lam_xong", "boi": "comeofage"})
    assert s == 200 and d["viec"]["trang_thai"] == "cho"
    tl = may.kho.tra_loi_cua(id_)
    assert len(tl) == 1 and tl[0]["noi_dung"] == "da_lam_xong" and tl[0]["boi"] == "comeofage"
    assert tl[0]["cau_hoi"] == "Mở Poster"
    assert may.kho.su_kien(id_)[-1]["boi"] == "comeofage"
    # lần 2: không còn can_tra_loi → 409, không ghi thêm
    s, _ = may.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "da_lam_xong", "boi": "nhan"})
    assert s == 409 and len(may.kho.tra_loi_cua(id_)) == 1


def test_tra_loi_khi_khong_cho_tra_loi_409(may):
    _, d = _tao(may)
    s, _ = may.goi("POST", f"/viec/{d['viec']['id']}/tra-loi", {"tra_loi": "da_lam_xong", "boi": "nhan"})
    assert s == 409
    assert may.goi("POST", "/viec/j20261117090000zzzz/tra-loi", {"tra_loi": "x", "boi": "nhan"})[0] == 404


@pytest.mark.parametrize("cau_hoi,tra_loi,ok", [
    (CanNguoiDung("viec_tay", "x"), "da_lam_xong", True),
    (CanNguoiDung("viec_tay", "x"), "tiep_tuc", False),
    (CanNguoiDung("viec_tay", "x"), "Tôi đã làm xong rồi", False),     # chữ tự do đợt 3
    (CanNguoiDung("khong_ro", "x"), "tiep_tuc", True),
    (CanNguoiDung("khong_ro", "x"), "da_lam_xong", False),
    (CanNguoiDung("chon", "Chọn thư mục", ("Thư mục A", "Thư mục B")), "Thư mục B", True),
    (CanNguoiDung("chon", "Chọn thư mục", ("Thư mục A", "Thư mục B")), "Thư mục C", False),
    (CanNguoiDung("chon", "Chọn thư mục", ("Thư mục A", "Thư mục B")), "thư mục b", False),
    (CanNguoiDung("chon", "Chọn thư mục", ("Thư mục A", "Thư mục B")), " Thư mục B", False),
    (CanNguoiDung("chon", "Chọn", ("a\tb", "c")), "a\tb", False),          # \t: Worker từ chối → runner cũng vậy
    (CanNguoiDung("chon", "Chọn", ("a\x7fb", "c")), "a\x7fb", False),
    (CanNguoiDung("chon", "Chọn", ("😀" * 60, "c")), "😀" * 60, True),     # 120 đơn vị UTF-16
    (CanNguoiDung("chon", "Chọn", ("😀" * 61, "c")), "😀" * 61, False),    # 122 UTF-16 dù len() = 61
    (CanNguoiDung("chon", "Chọn", ("x" * 121, "c")), "x" * 121, False),
    (CanNguoiDung("cau_hoi", "Bạn muốn gì?"), "Tôi muốn A", False),        # cau_hoi chữ tự do: đợt 5
    (CanNguoiDung("viec_tay", "x"), "", False),
])
def test_tra_loi_chi_gia_tri_nut(may, cau_hoi, tra_loi, ok):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    _vao_can_tra_loi(may, id_, cau_hoi)
    s, d = may.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": tra_loi, "boi": "nhan"})
    if ok:
        assert s == 200 and d["viec"]["trang_thai"] == "cho"
        assert may.kho.tra_loi_cua(id_)[0]["noi_dung"] == tra_loi
    else:
        assert s == 400, d
        assert may.kho.lay(id_)["trang_thai"] == "can_tra_loi" and may.kho.tra_loi_cua(id_) == []


@pytest.mark.parametrize("tra_loi", [None, 5, ["da_lam_xong"], {"a": 1}])
def test_tra_loi_kieu_sai_400(may, tra_loi):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    _vao_can_tra_loi(may, id_, CanNguoiDung("viec_tay", "x"))
    assert may.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": tra_loi, "boi": "nhan"})[0] == 400


# ---------- huy, tu-choi ----------

def test_huy_cho(may):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    s, d = may.goi("POST", f"/viec/{id_}/huy", {"boi": "comeofage"})
    assert s == 200 and d["viec"]["trang_thai"] == "huy"
    assert may.kho.su_kien(id_)[-1]["boi"] == "comeofage"
    assert may.huy == [id_]


def test_huy_dang_chay_bao_huy(may):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    may.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    s, d = may.goi("POST", f"/viec/{id_}/huy", {"boi": "nhan"})
    assert s == 200 and d["viec"]["trang_thai"] == "huy" and may.huy == [id_]


def test_huy_viec_da_dong_409(may):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    may.kho.chuyen(id_, ["cho"], "xong", "he_thong")
    s, _ = may.goi("POST", f"/viec/{id_}/huy", {"boi": "nhan"})
    assert s == 409 and may.kho.lay(id_)["trang_thai"] == "xong" and may.huy == []
    assert may.goi("POST", "/viec/j20261117090000zzzz/huy", {"boi": "nhan"})[0] == 404


def test_huy_thieu_boi_400(may):
    _, d = _tao(may)
    assert may.goi("POST", f"/viec/{d['viec']['id']}/huy", {})[0] == 400


def test_tu_choi(may):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    assert may.goi("POST", f"/viec/{id_}/tu-choi", {"boi": "nhan"})[0] == 409   # đang cho, không phải cho_duyet
    v = may.kho.tao("phan_tich_uid", "k-duyet", {"uid": UID}, "nhe", "cho_duyet", "nhan")
    s, d = may.goi("POST", f"/viec/{v['id']}/tu-choi", {"boi": "comeofage"})
    assert s == 200 and d["viec"]["trang_thai"] == "huy"


# ---------- chay-tiep ----------

def _vao_loi(may, id_, phien=0, so_lan=0):
    may.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    if phien:
        may.kho.danh_dau_phien(id_)
    if so_lan:
        may.kho.cong_chi_phi(id_, 0.5, 3, True)
    may.kho.chuyen(id_, ["dang_chay"], "loi", "he_thong", loi="quá giờ")


def test_chay_tiep_phien_chua_tao_409(may):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    _vao_loi(may, id_, phien=0, so_lan=1)
    assert may.goi("GET", f"/viec/{id_}")[1]["viec"]["co_the_chay_tiep"] is False
    s, _ = may.goi("POST", f"/viec/{id_}/chay-tiep", {"boi": "nhan"})
    assert s == 409 and may.kho.lay(id_)["trang_thai"] == "loi"


def test_chay_tiep_chua_goi_claude_409(may):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    _vao_loi(may, id_, phien=1, so_lan=0)
    assert may.goi("POST", f"/viec/{id_}/chay-tiep", {"boi": "nhan"})[0] == 409


def test_chay_tiep_hop_le(may):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    _vao_loi(may, id_, phien=1, so_lan=1)
    assert may.goi("GET", f"/viec/{id_}")[1]["viec"]["co_the_chay_tiep"] is True
    s, d = may.goi("POST", f"/viec/{id_}/chay-tiep", {"boi": "comeofage"})
    assert s == 200 and d["viec"]["trang_thai"] == "cho"
    assert d["viec"]["loi"] == "quá giờ"           # giữ lý do để vòng chạy dựng tin "Phiên trước dừng vì"
    sk = may.kho.su_kien(id_)[-1]
    assert (sk["tu"], sk["den"], sk["boi"]) == ("loi", "cho", "comeofage") and "chạy tiếp" in sk["ghi_chu"]


def test_chay_tiep_bi_chan_khi_tien_trinh_cu_khong_giet_duoc(may):
    """R-07 P2-4: ket_qua.khong_giet_duoc (tiến trình cũ còn sống) → co_the_chay_tiep False, POST chay-tiep 409."""
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    may.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    may.kho.danh_dau_phien(id_)
    may.kho.cong_chi_phi(id_, 0.5, 3, True)
    may.kho.chuyen(id_, ["dang_chay"], "loi", "he_thong", loi="tiến trình còn sống — kiểm tay",
                   ket_qua={"khong_giet_duoc": True, "pid": 4242})
    assert may.goi("GET", f"/viec/{id_}")[1]["viec"]["co_the_chay_tiep"] is False
    s, d = may.goi("POST", f"/viec/{id_}/chay-tiep", {"boi": "nhan"})
    assert s == 409 and "còn sống" in json.dumps(d, ensure_ascii=False)
    assert may.kho.lay(id_)["trang_thai"] == "loi"


def test_co_the_chay_tiep_logic_thuan():
    v = {"trang_thai": "loi", "phien_da_tao": 1, "so_lan_claude": 1}
    assert api.co_the_chay_tiep(v) is True
    assert api.co_the_chay_tiep(dict(v, ket_qua={"tom_tat": "x"})) is True
    assert api.co_the_chay_tiep(dict(v, ket_qua={"khong_giet_duoc": True})) is False
    assert api.co_the_chay_tiep(dict(v, ket_qua="hỏng")) is True


def test_chay_tiep_khong_o_loi_409(may):
    _, d = _tao(may)
    assert may.goi("POST", f"/viec/{d['viec']['id']}/chay-tiep", {"boi": "nhan"})[0] == 409


def test_chay_tiep_vuot_han_muc_claude_429(tmp_path, mt, dong):
    m = May(tmp_path, mt, dong, hm={**HAN_MUC_TRAN, "claude_viec_ngay": 1})
    try:
        _, d = _tao(m)
        id_ = d["viec"]["id"]
        _vao_loi(m, id_, phien=1, so_lan=1)       # job này đã tính 1 việc Claude hôm nay
        s, _ = m.goi("POST", f"/viec/{id_}/chay-tiep", {"boi": "nhan"})
        assert s == 429 and m.kho.lay(id_)["trang_thai"] == "loi"
    finally:
        m.dong_lai()


# ---------- chay-lai ----------

def test_chay_lai_tao_job_moi(may):
    _, d = _tao(may)
    cu = d["viec"]["id"]
    _vao_loi(may, cu, phien=1, so_lan=1)
    s, d = may.goi("POST", f"/viec/{cu}/chay-lai", {"boi": "comeofage"})
    assert s == 201
    v = d["viec"]
    assert v["id"] != cu and v["chay_lai_tu"] == cu and v["trang_thai"] == "cho" and v["tao_boi"] == "comeofage"
    assert v["tham_so"] == {"uid": UID} and v["phien_da_tao"] == 0
    sid_moi, sid_cu = may.kho.lay(v["id"])["session_id"], may.kho.lay(cu)["session_id"]
    assert uuid.UUID(sid_moi).version == 4 and sid_moi != sid_cu


def test_chay_lai_radar_bo_ngay_tao_tinh_lai_khoa(may, dong):
    _, d = _tao(may, loai="radar_ban_tin", tham_so={"top_n": 12, "chay_bu": True})
    cu = d["viec"]["id"]
    may.kho.chuyen(cu, ["cho"], "huy", "nhan")
    dong.toi(86400)
    s, d = may.goi("POST", f"/viec/{cu}/chay-lai", {"boi": "nhan"})
    assert s == 201, d
    assert d["viec"]["tham_so"] == {"top_n": 12, "chay_bu": True, "ngay_tao": "2026-11-18"}
    assert d["viec"]["khoa"] == "2026-11-18"


def test_chay_lai_radar_cung_ngay_khi_job_cu_da_dong(may):
    _, d = _tao(may, loai="radar_ban_tin", tham_so={})
    cu = d["viec"]["id"]
    _vao_loi(may, cu)
    s, d = may.goi("POST", f"/viec/{cu}/chay-lai", {"boi": "nhan"})
    assert s == 201 and d["viec"]["khoa"] == "2026-11-17"


def test_chay_lai_khong_tu_loi_huy_409(may):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    assert may.goi("POST", f"/viec/{id_}/chay-lai", {"boi": "nhan"})[0] == 409
    may.kho.chuyen(id_, ["cho"], "xong", "he_thong")
    assert may.goi("POST", f"/viec/{id_}/chay-lai", {"boi": "nhan"})[0] == 409
    assert may.goi("POST", "/viec/j20261117090000zzzz/chay-lai", {"boi": "nhan"})[0] == 404


def test_chay_lai_trung_viec_dang_mo_409(may):
    _, d = _tao(may)
    cu = d["viec"]["id"]
    may.kho.chuyen(cu, ["cho"], "huy", "nhan")
    _, d2 = _tao(may)
    s, d = may.goi("POST", f"/viec/{cu}/chay-lai", {"boi": "nhan"})
    assert s == 409 and d["trung"]["id"] == d2["viec"]["id"]


def test_chay_lai_du_an_bien_mat_400(may, mt):
    _, d = _tao(may, loai="poster_day_folder", tham_so={"uid": UID, "du_an": ma_du_an(mt._p)})
    cu = d["viec"]["id"]
    may.kho.chuyen(cu, ["cho"], "huy", "nhan")
    mt._p.rename(mt._p.with_name(f"Đổi tên {UID}x"))
    s, _ = may.goi("POST", f"/viec/{cu}/chay-lai", {"boi": "nhan"})
    assert s == 400


def test_chay_lai_vuot_han_muc_429(tmp_path, mt, dong):
    m = May(tmp_path, mt, dong, hm={**HAN_MUC_TRAN, "viec_tao_ngay_moi_nguoi": 1})
    try:
        _, d = _tao(m)
        cu = d["viec"]["id"]
        m.kho.chuyen(cu, ["cho"], "huy", "nhan")
        assert m.goi("POST", f"/viec/{cu}/chay-lai", {"boi": "nhan"})[0] == 429
    finally:
        m.dong_lai()


# ---------- lỗi bất ngờ: 500 JSON, server vẫn sống ----------

def test_loi_bat_ngo_tra_500_server_van_song(tmp_path, mt, dong):
    def hong():
        raise RuntimeError("làn hỏng")

    def log_hong(_id, _tu):
        raise KeyError("x")

    m = May(tmp_path, mt, dong, trang_thai_lan=hong, doc_log=log_hong)
    try:
        s, d = m.goi("GET", "/suc-khoe")
        assert s == 500 and "loi" in d and "làn hỏng" not in json.dumps(d, ensure_ascii=False)
        _, v = _tao(m)
        assert m.goi("GET", f"/viec/{v['viec']['id']}/log")[0] == 500
        assert m.goi("GET", "/danh-muc")[0] == 200
    finally:
        m.dong_lai()


def test_bao_huy_loi_van_huy_va_bao_canh_bao(tmp_path, mt, dong):
    m = May(tmp_path, mt, dong)
    try:
        def bao_hong(_id):
            raise OSError("không giết được")
        # thay hàm bao_huy: tạo handler mới cùng kho
        H = api.tao_handler(m.kho, mt, m.khoa_runner, m.khoa_ky.public_key(), m.hm, [], bao_hong,
                            lambda i, t: {}, lambda: {})
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        m2 = May.__new__(May)
        m2.__dict__.update(m.__dict__)
        m2.cong = srv.server_address[1]
        try:
            _, d = _tao(m2)
            id_ = d["viec"]["id"]
            s, d = m2.goi("POST", f"/viec/{id_}/huy", {"boi": "nhan"})
            assert s == 200 and d["viec"]["trang_thai"] == "huy" and d.get("canh_bao")
            assert m2.goi("GET", "/danh-muc")[0] == 200
        finally:
            srv.shutdown()
            srv.server_close()
    finally:
        m.dong_lai()


def test_tao_dong_thoi_khong_vuot_han_muc(tmp_path, mt, dong):
    """2 request tạo cùng lúc của cùng người khi chỉ còn 1 suất → đúng 1 cái 201."""
    m = May(tmp_path, mt, dong, hm={**HAN_MUC_TRAN, "viec_tao_ngay_moi_nguoi": 1})
    try:
        kq = []
        loai = ["phan_tich_uid", "douyin_uid", "xu_ly_link_moi", "radar_ban_tin"]
        ts = [{"uid": UID}, {"uid": UID}, {}, {}]

        def chay(i):
            kq.append(_tao(m, loai=loai[i], tham_so=ts[i])[0])

        th = [threading.Thread(target=chay, args=(i,)) for i in range(4)]
        for t in th:
            t.start()
        for t in th:
            t.join()
        assert sorted(kq) == [201, 429, 429, 429]
    finally:
        m.dong_lai()


def test_khong_mo_cong_8788_va_khong_dung_localappdata(may):
    assert may.cong != 8788
    assert "kho-runner" not in str(may.kho.duong_dan_db).lower() or "du_lieu" in str(may.kho.duong_dan_db)


def test_ma_nguon_khong_so_khoa_bang_bang():
    nguon = (Path(__file__).parent / "runner" / "api.py").read_text(encoding="utf-8")
    assert "compare_digest" in nguon
    assert not re.search(r"==\s*self\.khoa|khoa\s*==|!=\s*khoa|khoa\s*!=", nguon)


# ---------- R-06 P3-3: che dữ liệu cũ trong DB khi trả ra web ----------

BI_MAT_API = "Zq" + "8wE" * 20 + "k1"       # 64 ký tự, không khớp mẫu → chỉ che theo giá trị


def _che_api(s: str) -> str:
    return s.replace(BI_MAT_API, "***")


def test_bi_tu_choi_gon_che_truoc_khi_cat():
    tho = [{"tool_name": "Bash", "tool_use_id": "x", "tool_input": {"command": "a" * 190 + BI_MAT_API}},
           {"tool_name": "Edit" + BI_MAT_API, "input": {"k": BI_MAT_API}}]
    assert BI_MAT_API[:10] in api.bi_tu_choi_gon(tho)[0]["input"]           # không che: lộ 10 ký tự đầu (lỗi cũ)
    g = api.bi_tu_choi_gon(tho, _che_api)
    assert g[0]["input"] == "a" * 190 + "***"
    assert g[1] == {"tool_name": "Edit***", "input": '{"k": "***"}'}
    assert all(BI_MAT_API[:8] not in json.dumps(x) for x in g)


def test_viec_ra_che_moi_truong_van_ban_khong_sua_goc():
    v = {"id": "j1", "trang_thai": "loi", "loi": "lỗi " + BI_MAT_API, "can_ban": BI_MAT_API,
         "cau_hoi": {"loai": "chon", "noi_dung": "hỏi " + BI_MAT_API, "lua_chon": ["A", BI_MAT_API]},
         "ket_qua": {"tom_tat": "x" * 1490 + BI_MAT_API, "lo_ngai": BI_MAT_API, "so": 3,
                     "bi_tu_choi": [{"tool_name": "Bash", "tool_input": {"command": BI_MAT_API}}]},
         "session_id": "s", "pid": 5}
    ra = api.viec_ra(v, True, _che_api)
    assert BI_MAT_API[:8] not in json.dumps(ra, ensure_ascii=False)
    assert ra["loi"] == "lỗi ***" and ra["cau_hoi"]["lua_chon"] == ["A", "***"] and ra["ket_qua"]["so"] == 3
    assert ra["ket_qua"]["bi_tu_choi"] == [{"tool_name": "Bash", "input": "***"}]
    assert "session_id" not in ra and "pid" not in ra and ra["co_session"] is True
    assert "bi_tu_choi" not in api.viec_ra(v, False, _che_api)["ket_qua"]
    assert v["loi"].endswith(BI_MAT_API) and v["ket_qua"]["bi_tu_choi"][0]["tool_input"]["command"] == BI_MAT_API
    assert api.viec_ra(v)["loi"].endswith(BI_MAT_API)                       # mặc định không che (chữ ký cũ)


def test_handler_co_che_che_viec_su_kien_va_ds(tmp_path, mt, dong):
    m = May(tmp_path, mt, dong, che=_che_api)
    try:
        ma, d = _tao(m)
        id_ = d["viec"]["id"]
        m.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
        m.kho.chuyen(id_, ["dang_chay"], "loi", "he_thong", "ghi chú " + BI_MAT_API, loi="cũ " + BI_MAT_API,
                     ket_qua={"tom_tat": BI_MAT_API, "bi_tu_choi": [{"tool_name": "Read",
                                                                     "tool_input": {"file_path": BI_MAT_API}}]})
        ma, ct = m.goi("GET", f"/viec/{id_}")
        assert ma == 200 and ct["viec"]["loi"] == "cũ ***"
        assert ct["viec"]["ket_qua"]["bi_tu_choi"] == [{"tool_name": "Read", "input": "***"}]
        ma, ds = m.goi("GET", "/viec")
        for x in (ct, ds):
            assert BI_MAT_API[:8] not in json.dumps(x, ensure_ascii=False)
    finally:
        m.dong_lai()
