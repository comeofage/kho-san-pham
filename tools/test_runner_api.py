"""Test HTTP API runner (B-2, docs/bo-chay-viec.md §8.1, §4.3, §8.3).

Chạy: python -B -m pytest tools/test_runner_api.py -q

Server THẬT (ThreadingHTTPServer) ở 127.0.0.1 cổng ngẫu nhiên; DB SQLite trong tmp_path;
khoá runner + khoá Ed25519 đều sinh trong test (không đụng %LOCALAPPDATA%\\kho-runner, không cổng 8788).
"""
import hashlib
import http.client
import json
import os
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

    def __init__(self, tmp_path, mt, dong, hm=None, trang_thai_lan=None, doc_log=None, che=None, **them):
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
                            **({} if che is None else {"che": che}), **them)
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
    assert d["dem"]["cho"] == 1 and d["dot_bat"] == 5 and d["chi_phi_hom_nay_usd"] == 0
    assert d["canh_bao"] == ["cau_hinh.json: thử cảnh báo"]
    assert d["han_muc"]["claude_viec_ngay"] == 12
    assert d["luc"] == "2026-11-17T09:00:00+07:00" and d["phien_ban"] == "nguon"


def test_danh_muc_dot_4(may):
    s, d = may.goi("GET", "/danh-muc")
    assert s == 200
    ma = {x["ma"] for x in d["loai"]}
    assert ma == {"radar_ban_tin", "phan_tich_uid", "douyin_uid", "xu_ly_link_moi", "poster_day_folder", "voice_pv",
                  "muse_clip", "voice_genmax", "poster_len_lich",
                  "sua_video", "hoan_tac_sua", "taovideo", "poster_bo_loai"}           # B-L1                   # B-4: đã mở đợt 5
    r = next(x for x in d["loai"] if x["ma"] == "radar_ban_tin")
    assert set(r) == {"ma", "ten", "dot", "ton_tien", "lan_chay", "tham_so"}
    assert [t["ten"] for t in r["tham_so"]] == ["top_n", "chay_bu"]
    muse = next(x for x in d["loai"] if x["ma"] == "muse_clip")
    assert muse["dot"] == 4 and muse["ton_tien"] is True
    assert [t["ten"] for t in muse["tham_so"]] == ["uid", "du_an", "mau", "thoi_luong", "ti_le"]


def test_danh_muc_an_dot_cao_hon_dot_bat(tmp_path, mt, dong, monkeypatch):
    monkeypatch.setitem(dm.DANH_MUC, "thu_dot5", replace(dm.DANH_MUC["phan_tich_uid"], ma="thu_dot5", dot=6))
    m = May(tmp_path, mt, dong)
    try:
        assert "thu_dot5" not in {x["ma"] for x in m.goi("GET", "/danh-muc")[1]["loai"]}
        s, _ = _tao(m, loai="thu_dot5")
        assert s == 400 and m.kho.ds() == []
    finally:
        m.dong_lai()
    # hm nới dot_bat quá trần code (dict truyền vào bị sửa) vẫn không mở đợt 6 (loại thử gắn dot=6)
    m2 = May(tmp_path / "b", mt, dong, hm={**HAN_MUC_TRAN, "dot_bat": 9})
    try:
        assert "thu_dot5" not in {x["ma"] for x in m2.goi("GET", "/danh-muc")[1]["loai"]}
    finally:
        m2.dong_lai()
    # cau_hinh hạ dot_bat = 3 → ẩn đợt 4, tạo việc đợt 4 bị 400
    m4 = May(tmp_path / "d", mt, dong, hm={**HAN_MUC_TRAN, "dot_bat": 3})
    try:
        ds = {x["ma"] for x in m4.goi("GET", "/danh-muc")[1]["loai"]}
        assert "muse_clip" not in ds and "radar_ban_tin" in ds
        assert _tao(m4, loai="muse_clip", tham_so={"uid": UID})[0] == 400
    finally:
        m4.dong_lai()
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


def test_poster_folders_va_duyet_404_khi_ha_ve_dot_3(tmp_path, mt, dong):
    m = May(tmp_path, mt, dong, hm={**HAN_MUC_TRAN, "dot_bat": 3})
    try:
        assert m.goi("GET", "/poster/folders")[0] == 404
        v = m.kho.tao("phan_tich_uid", "k", {"uid": UID}, "nhe", "cho_duyet", "nhan")
        s, _ = m.goi("POST", f"/viec/{v['id']}/duyet",
                     {"loi_duyet": "ok", "duyet_luc": "x", "boi": "nhan", "chu_ky_duyet": "x"})
        assert s == 404 and m.kho.lay(v["id"])["trang_thai"] == "cho_duyet"
    finally:
        m.dong_lai()


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
    assert s == 200 and len(d["viec"]) == 3 and d["tong"] == 3
    assert all("session_id" not in v and "pid" not in v for v in d["viec"])
    assert {v["id"] for v in may.goi("GET", "/viec?trang_thai=huy")[1]["viec"]} == {c["viec"]["id"]}
    assert may.goi("GET", "/viec?trang_thai=huy")[1]["tong"] == 1
    assert len(may.goi("GET", "/viec?trang_thai=cho,huy")[1]["viec"]) == 3
    s, d = may.goi("GET", f"/viec?uid={UID}")
    assert {v["id"] for v in d["viec"]} == {a["viec"]["id"], b["viec"]["id"]}
    assert "tong" not in d        # nhánh lọc theo uid giữ nguyên như cũ, không phân trang
    assert len(may.goi("GET", "/viec?gioi_han=1")[1]["viec"]) == 1
    s, d = may.goi("GET", "/viec?tom_tat=1")
    assert s == 200 and d["dem"]["cho"] == 2 and d["dem"]["huy"] == 1 and "viec" not in d
    for q in ("trang_thai=la", "uid=12", "gioi_han=abc", "gioi_han=0", "offset=abc", "offset=-1"):
        assert may.goi("GET", f"/viec?{q}")[0] == 400, q


def test_ds_viec_offset_phan_trang(may, mt):
    """GET /viec?offset=… lật trang thật; tổng (`tong`) khớp bộ lọc trang_thai đang áp, không đổi theo trang."""
    ds_id = []
    for loai, ts in [("phan_tich_uid", {"uid": UID}), ("douyin_uid", {"uid": UID}),
                     ("voice_pv", {"uid": UID, "du_an": ma_du_an(mt._p), "me": ME})]:
        _, d = _tao(may, loai=loai, tham_so=ts)
        ds_id.append(d["viec"]["id"])
    moi_nhat_truoc = list(reversed(ds_id))
    s, d = may.goi("GET", "/viec?gioi_han=2")
    assert s == 200 and [v["id"] for v in d["viec"]] == moi_nhat_truoc[:2] and d["tong"] == 3
    s, d = may.goi("GET", "/viec?gioi_han=2&offset=2")
    assert s == 200 and [v["id"] for v in d["viec"]] == moi_nhat_truoc[2:3] and d["tong"] == 3
    s, d = may.goi("GET", "/viec?gioi_han=2&offset=10")
    assert s == 200 and d["viec"] == [] and d["tong"] == 3
    # việc đã ẩn/lưu trữ không tính vào tong
    may.kho.chuyen(ds_id[0], ["cho"], "xong", "he_thong")
    may.goi("POST", f"/viec/{ds_id[0]}/luu-tru", {"boi": "nhan"})
    s, d = may.goi("GET", "/viec")
    assert s == 200 and d["tong"] == 2 and ds_id[0] not in {v["id"] for v in d["viec"]}


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


# ---------- luu-tru, bo-luu-tru ----------

def test_luu_tru_viec_da_xong(may):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    may.kho.chuyen(id_, ["cho"], "xong", "he_thong")
    s, d = may.goi("POST", f"/viec/{id_}/luu-tru", {"boi": "comeofage"})
    assert s == 200 and d["viec"]["id"] == id_ and d["viec"]["luu_tru"] == 1
    assert d["viec"]["trang_thai"] == "xong"            # không đổi trang_thai
    assert id_ not in {v["id"] for v in may.goi("GET", "/viec")[1]["viec"]}
    assert may.kho.lay(id_)["luu_tru"] == 1             # vẫn còn nguyên trong DB, chỉ ẩn khỏi ds()


def test_bo_luu_tru(may):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    may.kho.chuyen(id_, ["cho"], "huy", "nhan")
    may.goi("POST", f"/viec/{id_}/luu-tru", {"boi": "nhan"})
    s, d = may.goi("POST", f"/viec/{id_}/bo-luu-tru", {"boi": "nhan"})
    assert s == 200 and d["viec"]["luu_tru"] == 0
    assert id_ in {v["id"] for v in may.goi("GET", "/viec")[1]["viec"]}


def test_luu_tru_viec_chua_ket_thuc_400(may):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    s, d = may.goi("POST", f"/viec/{id_}/luu-tru", {"boi": "nhan"})
    assert s == 400 and may.kho.lay(id_)["luu_tru"] == 0
    may.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    assert may.goi("POST", f"/viec/{id_}/luu-tru", {"boi": "nhan"})[0] == 400


def test_luu_tru_viec_khong_co_404(may):
    assert may.goi("POST", "/viec/j20261117090000zzzz/luu-tru", {"boi": "nhan"})[0] == 404
    assert may.goi("POST", "/viec/j20261117090000zzzz/bo-luu-tru", {"boi": "nhan"})[0] == 404


def test_luu_tru_ghi_su_kien_ai_lam(may):
    """P3 (reviewer): p_luu_tru/p_bo_luu_tru trước đây gọi _boi(body) chỉ để validate rồi bỏ — không ghi vết ai
    đã ẩn/bỏ ẩn. Giờ phải truyền boi vào dat_luu_tru() và ghi được một dòng su_kien."""
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    may.kho.chuyen(id_, ["cho"], "xong", "he_thong")
    may.goi("POST", f"/viec/{id_}/luu-tru", {"boi": "comeofage"})
    sk = may.kho.su_kien(id_)[-1]
    assert sk["boi"] == "comeofage" and "ẩn" in sk["ghi_chu"]
    may.goi("POST", f"/viec/{id_}/bo-luu-tru", {"boi": "nhan"})
    sk2 = may.kho.su_kien(id_)[-1]
    assert sk2["boi"] == "nhan" and "ẩn" in sk2["ghi_chu"]


def test_luu_tru_thieu_boi_400(may):
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    may.kho.chuyen(id_, ["cho"], "huy", "nhan")
    assert may.goi("POST", f"/viec/{id_}/luu-tru", {})[0] == 400


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


def test_chay_tiep_sau_khi_an_xoa_luu_tru(may):
    """P1 (moi:an-viec-roi-chay-lai-an-tang-hinh), qua đúng luồng web: ẩn việc lỗi rồi bấm Chạy tiếp không được
    để việc biến mất khỏi mọi danh sách ⚙ Việc (chỉ nơi duy nhất có nút Dừng)."""
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    _vao_loi(may, id_, phien=1, so_lan=1)
    s, _ = may.goi("POST", f"/viec/{id_}/luu-tru", {"boi": "nhan"})
    assert s == 200 and may.kho.lay(id_)["luu_tru"] == 1
    assert id_ not in {v["id"] for v in may.goi("GET", "/viec")[1]["viec"]}
    s, d = may.goi("POST", f"/viec/{id_}/chay-tiep", {"boi": "comeofage"})
    assert s == 200 and d["viec"]["trang_thai"] == "cho" and d["viec"]["luu_tru"] == 0
    assert may.kho.lay(id_)["luu_tru"] == 0
    assert id_ in {v["id"] for v in may.goi("GET", "/viec")[1]["viec"]}


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


# ================================================================ đợt 4 (B-3): tạo, duyệt có chữ ký, hạn mức

FOLDERS = [{"id": 7, "name": "Bình nước 1729420930611055346", "videos": 20}, {"id": 9, "ten": "Ví"}]


@pytest.fixture
def mt4(mt):
    mt._cong[dm.CONG_VIDEO_BATCH] = True
    mt.ds_ma_voice = lambda _p, _me: ["A1", "A2"]
    mt.doc_folder_poster = lambda: list(FOLDERS)
    return mt


@pytest.fixture
def may4(tmp_path, mt4, dong):
    m = May(tmp_path, mt4, dong)
    yield m
    m.dong_lai()


def _muse_ts(mt, n=2):
    return {"uid": UID, "du_an": ma_du_an(mt._p), "mau": list(dm.MAU_PROMPT_MUSE)[:n], "thoi_luong": 10,
            "ti_le": "9:16"}


def _gm_ts(mt):
    return {"uid": UID, "du_an": ma_du_an(mt._p), "me": ME}


def _luc_duyet(dong, lech_s=0):
    return (api.gio_vn(dong()) + timedelta(seconds=lech_s)).isoformat(timespec="seconds")


def _ky_duyet(may, id_, *, loi="Duyệt, làm đúng như ước tính", boi="nhan", duyet_luc, khoa=None,
              tham_so_chuan=None, id_ky=None, boi_ky=None, loi_ky=None, loai_ky=None):
    ct = may.goi("GET", f"/viec/{id_}")[1]
    chuoi = chu_ky.chuoi_ky_duyet(id_ky or id_, loai_ky or ct["viec"]["loai"],
                                  ct["tham_so_chuan"] if tham_so_chuan is None else tham_so_chuan,
                                  loi if loi_ky is None else loi_ky, duyet_luc, boi_ky or boi)
    return _b64url((khoa or may.khoa_ky).sign(chuoi))


def _duyet(may, dong, id_, *, loi="Duyệt, làm đúng như ước tính", boi="nhan", lech_s=0, **kw):
    luc = _luc_duyet(dong, lech_s)
    ky = _ky_duyet(may, id_, loi=loi, boi=boi, duyet_luc=luc, **kw)
    return may.goi("POST", f"/viec/{id_}/duyet", {"loi_duyet": loi, "duyet_luc": luc, "boi": boi,
                                                  "chu_ky_duyet": ky})


def _sua_db(may, id_, **cot):
    import sqlite3
    with sqlite3.connect(may.kho.duong_dan_db) as c:
        for k, v in cot.items():
            c.execute(f"UPDATE viec SET {k}=? WHERE id=?", (v, id_))


def test_poster_folders(may4, mt4):
    s, d = may4.goi("GET", "/poster/folders")
    assert s == 200 and d == {"folders": [{"id": 7, "ten": "Bình nước 1729420930611055346"}, {"id": 9, "ten": "Ví"}]}
    assert may4.goi("GET", "/poster/folders", khoa=False)[0] == 401

    def hong():
        raise OSError("venv Poster lỗi")
    mt4.doc_folder_poster = hong
    s, d = may4.goi("GET", "/poster/folders")
    assert s == 502 and "Poster" in d["loi"] and "venv" not in d["loi"]


def test_poster_folders_khong_lo_duong_dan(may4, mt4):
    """B-L1 (§4.9): runner giữ duong_dan nội bộ để chặn poster_len_lich; KHÔNG trả đường dẫn ổ máy nhà ra web."""
    mt4.doc_folder_poster = lambda: [{"id": 7, "name": "Bình nước", "duong_dan": "E:/oneshottramcanh/x/output_poster"},
                                     {"id": 9, "ten": "Ví"}]
    s, d = may4.goi("GET", "/poster/folders")
    assert s == 200 and d == {"folders": [{"id": 7, "ten": "Bình nước"}, {"id": 9, "ten": "Ví"}]}
    assert "oneshottramcanh" not in json.dumps(d)


def test_tao_poster_bo_loai(may, mt):
    s, d = _tao(may, loai="poster_bo_loai", tham_so={"uid": UID})
    assert s == 201 and d["viec"]["trang_thai"] == "cho" and d["viec"]["khoa"] == UID
    assert d["viec"]["lan_chay"] == "nhe"
    assert _tao(may, loai="poster_bo_loai", tham_so={"uid": UID})[0] == 409            # khoá chống trùng theo uid
    assert _tao(may, loai="poster_bo_loai", tham_so={"uid": UID, "goc": "E:/x"})[0] == 400


def test_tao_ton_tien_trang_thai_dau(may4, mt4):
    s, d = _tao(may4, "muse_clip", _muse_ts(mt4))
    assert s == 201 and d["viec"]["trang_thai"] == "cho_duyet" and d["viec"]["buoc"] == "chay"
    assert d["viec"]["co_session"] is True
    s, g = _tao(may4, "voice_genmax", _gm_ts(mt4))
    assert s == 201 and (g["viec"]["trang_thai"], g["viec"]["buoc"]) == ("cho", "uoc_tinh")
    assert g["viec"]["tham_so"]["ma_ban"] == ["A1", "A2"] and g["viec"]["co_session"] is False
    s, p = _tao(may4, "poster_len_lich", {"folder_id": 7, "so_video_ngay": 3})
    assert s == 201 and p["viec"]["trang_thai"] == "cho_duyet" and p["viec"]["khoa"] == "folder:7"
    assert _tao(may4, "poster_len_lich", {"folder_id": 8, "so_video_ngay": 3})[0] == 400
    assert _tao(may4, "voice_genmax", {**_gm_ts(mt4), "ma_ban": ["A1"]})[0] == 400   # web không tự gửi mã bản
    # GET chi tiết trả tham_so_chuan đúng JSON chuẩn để Worker ký
    ct = may4.goi("GET", f"/viec/{g['viec']['id']}")[1]
    assert ct["tham_so_chuan"] == chu_ky.json_chuan(g["viec"]["tham_so"])


def test_tao_ton_tien_dieu_kien_truoc_khong_lam_mat_duyet(may4, mt4):
    """Loại cho_duyet tạo thẳng ở cho_duyet dù app chưa mở — điều kiện trước kiểm lúc chạy."""
    mt4._cong[dm.CONG_VIDEO_BATCH] = False
    s, d = _tao(may4, "muse_clip", _muse_ts(mt4))
    assert s == 201 and d["viec"]["trang_thai"] == "cho_duyet"


def test_duyet_hop_le(may4, mt4, dong):
    _, d = _tao(may4, "muse_clip", _muse_ts(mt4))
    id_ = d["viec"]["id"]
    s, r = _duyet(may4, dong, id_, boi="comeofage")
    assert s == 200, r
    v = r["viec"]
    assert (v["trang_thai"], v["buoc"], v["duyet_boi"]) == ("cho", "chay", "comeofage")
    assert v["loi_duyet"] == "Duyệt, làm đúng như ước tính" and v["duyet_luc"] == _luc_duyet(dong)
    assert "chu_ky_duyet" not in v
    luu = may4.kho.lay(id_)
    assert chu_ky.kiem_duyet(may4.khoa_ky.public_key(), luu) is True
    sk = may4.kho.su_kien(id_)[-1]
    assert (sk["tu"], sk["den"], sk["boi"]) == ("cho_duyet", "cho", "comeofage")
    # duyệt lần 2 → 409 (không còn cho_duyet)
    assert _duyet(may4, dong, id_)[0] == 409


def test_duyet_genmax_sau_uoc_tinh_doi_buoc_chay(may4, mt4, dong):
    _, d = _tao(may4, "voice_genmax", _gm_ts(mt4))
    id_ = d["viec"]["id"]
    assert _duyet(may4, dong, id_)[0] == 409             # đang ước tính, chưa tới cho_duyet
    may4.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    may4.kho.chuyen(id_, ["dang_chay"], "cho_duyet", "he_thong", uoc_tinh="Kế hoạch: 2 lượt GenMax, 900 ký tự")
    assert may4.goi("GET", f"/viec/{id_}")[1]["xem_truoc"].startswith("Kế hoạch")
    s, r = _duyet(may4, dong, id_)
    assert s == 200 and (r["viec"]["trang_thai"], r["viec"]["buoc"]) == ("cho", "chay")
    # lệnh pha chạy sinh từ việc đã duyệt: có --dong-y, ghim đúng mã bản đã ký, không --gui-lai-ma
    luu = may4.kho.lay(id_)
    argv = dm.DANH_MUC["voice_genmax"].lap_buoc(luu["tham_so"], luu, mt4)[0].argv
    assert "--dong-y" in argv and argv[argv.index("--ma") + 1:] == ["A1", "A2"]
    assert not any("gui-lai" in x for x in argv)


@pytest.mark.parametrize("sai", ["khoa_khac", "tham_so_khac", "id_khac", "boi_khac", "loi_khac", "loai_khac",
                                 "chu_ky_rac"])
def test_duyet_chu_ky_sai_401(may4, mt4, dong, sai):
    _, d = _tao(may4, "muse_clip", _muse_ts(mt4))
    id_ = d["viec"]["id"]
    kw = {"khoa_khac": {"khoa": Ed25519PrivateKey.generate()},
          "tham_so_khac": {"tham_so_chuan": chu_ky.json_chuan(_muse_ts(mt4, 3))},
          "id_khac": {"id_ky": "j20261117090000zzzz"}, "boi_khac": {"boi_ky": "comeofage"},
          "loi_khac": {"loi_ky": "Duyệt 1 clip thôi"}, "loai_khac": {"loai_ky": "voice_genmax"}}.get(sai, {})
    if sai == "chu_ky_rac":
        luc = _luc_duyet(dong)
        s, r = may4.goi("POST", f"/viec/{id_}/duyet", {"loi_duyet": "ok", "duyet_luc": luc, "boi": "nhan",
                                                       "chu_ky_duyet": "x" * 86})
    else:
        s, r = _duyet(may4, dong, id_, **kw)
    assert s == 401, r
    v = may4.kho.lay(id_)
    assert v["trang_thai"] == "cho_duyet" and v["loi_duyet"] is None and v["chu_ky_duyet"] is None


def test_duyet_nguoi_khong_duoc_duyet_403(may4, mt4, dong):
    _, d = _tao(may4, "muse_clip", _muse_ts(mt4))
    s, _ = _duyet(may4, dong, d["viec"]["id"], boi="khach")
    assert s == 403 and may4.kho.lay(d["viec"]["id"])["trang_thai"] == "cho_duyet"


@pytest.mark.parametrize("body", [
    {"loi_duyet": "", "duyet_luc": "__LUC__", "boi": "nhan", "chu_ky_duyet": "x"},
    {"loi_duyet": "   ", "duyet_luc": "__LUC__", "boi": "nhan", "chu_ky_duyet": "x"},
    {"loi_duyet": 5, "duyet_luc": "__LUC__", "boi": "nhan", "chu_ky_duyet": "x"},
    {"loi_duyet": "x" * 2001, "duyet_luc": "__LUC__", "boi": "nhan", "chu_ky_duyet": "x"},
    {"duyet_luc": "__LUC__", "boi": "nhan", "chu_ky_duyet": "x"},
    {"loi_duyet": "ok", "duyet_luc": "hôm nay", "boi": "nhan", "chu_ky_duyet": "x"},
    {"loi_duyet": "ok", "duyet_luc": "2026-11-17T09:00:00", "boi": "nhan", "chu_ky_duyet": "x"},   # thiếu múi giờ
    {"loi_duyet": "ok", "duyet_luc": 1763344800000, "boi": "nhan", "chu_ky_duyet": "x"},
    {"loi_duyet": "ok", "duyet_luc": "__LUC__", "boi": "nhan", "chu_ky_duyet": 5},
    {"loi_duyet": "ok", "duyet_luc": "__LUC__", "boi": "nhan"},
])
def test_duyet_body_sai_400(may4, mt4, dong, body):
    _, d = _tao(may4, "muse_clip", _muse_ts(mt4))
    b = {k: (_luc_duyet(dong) if v == "__LUC__" else v) for k, v in body.items()}
    s, _ = may4.goi("POST", f"/viec/{d['viec']['id']}/duyet", b)
    assert s == 400 and may4.kho.lay(d["viec"]["id"])["trang_thai"] == "cho_duyet"


def test_duyet_luc_lech_qua_10_phut_400(may4, mt4, dong):
    _, d = _tao(may4, "muse_clip", _muse_ts(mt4))
    assert _duyet(may4, dong, d["viec"]["id"], lech_s=-601)[0] == 400
    assert _duyet(may4, dong, d["viec"]["id"], lech_s=601)[0] == 400
    assert _duyet(may4, dong, d["viec"]["id"], lech_s=-300)[0] == 200


def test_duyet_loai_mien_phi_409(may4, dong):
    v = may4.kho.tao("phan_tich_uid", "k", {"uid": UID}, "nhe", "cho_duyet", "nhan")
    s, _ = _duyet(may4, dong, v["id"])
    assert s == 409 and may4.kho.lay(v["id"])["trang_thai"] == "cho_duyet"


def test_duyet_viec_khong_co_404(may4, dong):
    s, _ = may4.goi("POST", "/viec/j20261117090000zzzz/duyet",
                    {"loi_duyet": "ok", "duyet_luc": _luc_duyet(dong), "boi": "nhan", "chu_ky_duyet": "x"})
    assert s == 404


# ---------- hạn mức ở 3 thời điểm ----------

def test_han_muc_luc_tao_429(may4, mt4):
    assert _tao(may4, "muse_clip", {**_muse_ts(mt4), "mau": list(dm.MAU_PROMPT_MUSE)[:7]})[0] == 201
    may4.mt.ds_ma_voice = lambda _p, _me: [f"A{i}" for i in range(26)]
    s, d = _tao(may4, "voice_genmax", _gm_ts(mt4))
    assert s == 429 and "25" in d["loi"]
    assert _tao(may4, "poster_len_lich", {"folder_id": 7, "so_video_ngay": 5})[0] == 201
    assert _tao(may4, "poster_len_lich", {"folder_id": 9, "so_video_ngay": 5})[0] == 201
    assert len(may4.kho.ds()) == 3
    s, d = _tao(may4, "poster_len_lich", {"folder_id": 9, "so_video_ngay": 101})
    assert s == 400                                       # 101 > khoảng 1–100 của tham số
    may4.hm["poster_video_ngay_toi_da"] = 3
    may4.mt.doc_folder_poster = lambda: [{"id": 11, "name": "x"}]
    s, d = _tao(may4, "poster_len_lich", {"folder_id": 11, "so_video_ngay": 4})
    assert s == 429                                       # trần đã hạ còn 3 (và đã đủ 2 việc/ngày)


def test_han_muc_muse_ngay_luc_tao(may4, mt4, tmp_path):
    p2 = mt4.gocs[0] / f"Ví {UID}"
    (p2 / "kich-ban").mkdir(parents=True)
    assert _tao(may4, "muse_clip", {**_muse_ts(mt4), "mau": list(dm.MAU_PROMPT_MUSE)[:7]})[0] == 201
    ts2 = {**_muse_ts(mt4), "du_an": ma_du_an(p2), "mau": list(dm.MAU_PROMPT_MUSE)[:7]}
    assert _tao(may4, "muse_clip", ts2)[0] == 201                       # 14 ≤ 15
    p3 = mt4.gocs[0] / f"Ba {UID}"
    (p3 / "kich-ban").mkdir(parents=True)
    s, d = _tao(may4, "muse_clip", {**_muse_ts(mt4), "du_an": ma_du_an(p3)})   # +2 = 16
    assert s == 429 and "15" in d["loi"]


def test_han_muc_luc_duyet_429(may4, mt4, dong):
    _, a = _tao(may4, "poster_len_lich", {"folder_id": 7, "so_video_ngay": 3})
    _, b = _tao(may4, "poster_len_lich", {"folder_id": 9, "so_video_ngay": 3})
    assert _duyet(may4, dong, a["viec"]["id"])[0] == 200
    may4.hm["poster_len_lich_ngay"] = 1                  # cau_hinh hạ trần sau khi tạo
    s, d = _duyet(may4, dong, b["viec"]["id"])
    assert s == 429 and may4.kho.lay(b["viec"]["id"])["trang_thai"] == "cho_duyet"
    may4.hm["poster_len_lich_ngay"] = 2
    may4.hm["poster_video_ngay_toi_da"] = 2              # hạ trần mỗi việc → việc 3 video/ngày bị chặn khi duyệt
    assert _duyet(may4, dong, b["viec"]["id"])[0] == 429


def test_han_muc_luc_duyet_lai_sau_xin_duyet_lai_429(may4, mt4, dong):
    """D9: việc tốn tiền lỗi không chạy tiếp được; xin duyệt lại rồi duyệt → hạn mức kiểm lại lúc duyệt."""
    _, d = _tao(may4, "muse_clip", _muse_ts(mt4, 5))
    id_ = d["viec"]["id"]
    assert _duyet(may4, dong, id_)[0] == 200
    _vao_loi(may4, id_, phien=1, so_lan=1)
    assert may4.goi("POST", f"/viec/{id_}/xin-duyet-lai", {"boi": "nhan"})[0] == 200
    may4.hm["muse_clip_moi_viec"] = 4
    s, r = _duyet(may4, dong, id_)
    assert s == 429 and may4.kho.lay(id_)["trang_thai"] == "cho_duyet"
    may4.hm["muse_clip_moi_viec"] = 10
    s, r = _duyet(may4, dong, id_)
    assert s == 200 and r["viec"]["trang_thai"] == "cho"


def test_sua_tham_so_db_sau_duyet_bi_tu_choi(may4, mt4, dong):
    """Xong khi B-3: sửa tham_so trong DB sau duyệt → chữ ký duyệt không còn khớp (vòng chạy từ chối khi nhận),
    chay-tiep 409."""
    _, d = _tao(may4, "muse_clip", _muse_ts(mt4, 2))
    id_ = d["viec"]["id"]
    assert _duyet(may4, dong, id_)[0] == 200
    pub = may4.khoa_ky.public_key()
    assert chu_ky.kiem_duyet(pub, may4.kho.lay(id_)) is True
    _sua_db(may4, id_, tham_so=chu_ky.json_chuan(_muse_ts(mt4, 7)))
    assert chu_ky.kiem_duyet(pub, may4.kho.lay(id_)) is False
    _vao_loi(may4, id_, phien=1, so_lan=1)
    s, r = may4.goi("POST", f"/viec/{id_}/chay-tiep", {"boi": "nhan"})
    assert s == 409 and r["loi"] == "Việc tốn tiền: cần duyệt lại" and may4.kho.lay(id_)["trang_thai"] == "loi"
    # sửa người duyệt / lời duyệt cũng vậy
    _sua_db(may4, id_, tham_so=chu_ky.json_chuan(_muse_ts(mt4, 2)))
    assert chu_ky.kiem_duyet(pub, may4.kho.lay(id_)) is True
    _sua_db(may4, id_, duyet_boi="comeofage")
    assert chu_ky.kiem_duyet(pub, may4.kho.lay(id_)) is False


def test_sua_trang_thai_db_thanh_cho_khong_qua_duyet(may4, mt4, dong):
    """Sửa DB đưa việc chưa duyệt từ cho_duyet sang cho → không có chữ ký → kiem_duyet False (vòng chạy chặn);
    genmax dù bị sửa buoc='chay' cũng không dựng được lệnh --dong-y khi thiếu trường duyệt."""
    _, d = _tao(may4, "muse_clip", _muse_ts(mt4))
    _sua_db(may4, d["viec"]["id"], trang_thai="cho")
    assert chu_ky.kiem_duyet(may4.khoa_ky.public_key(), may4.kho.lay(d["viec"]["id"])) is False
    _, g = _tao(may4, "voice_genmax", _gm_ts(mt4))
    _sua_db(may4, g["viec"]["id"], buoc="chay")
    luu = may4.kho.lay(g["viec"]["id"])
    with pytest.raises(api.ThamSoLoi):
        dm.DANH_MUC["voice_genmax"].lap_buoc(luu["tham_so"], luu, mt4)


def test_chay_lai_ton_tien(may4, mt4, dong):
    _, g = _tao(may4, "voice_genmax", _gm_ts(mt4))
    gid = g["viec"]["id"]
    may4.kho.chuyen(gid, ["cho"], "huy", "nhan")
    mt4.ds_ma_voice = lambda _p, _me: ["A1", "A2", "A3"]
    s, r = may4.goi("POST", f"/viec/{gid}/chay-lai", {"boi": "nhan"})
    assert s == 201 and (r["viec"]["trang_thai"], r["viec"]["buoc"]) == ("cho", "uoc_tinh")
    assert r["viec"]["tham_so"]["ma_ban"] == ["A1", "A2", "A3"]           # tính lại, không chép mã cũ
    _, m = _tao(may4, "muse_clip", _muse_ts(mt4))
    mid = m["viec"]["id"]
    assert _duyet(may4, dong, mid)[0] == 200
    may4.kho.chuyen(mid, ["cho"], "huy", "nhan")
    s, r = may4.goi("POST", f"/viec/{mid}/chay-lai", {"boi": "comeofage"})
    assert s == 201 and r["viec"]["trang_thai"] == "cho_duyet"            # tốn tiền → duyệt lại
    assert r["viec"]["loi_duyet"] is None and r["viec"]["duyet_boi"] is None


# ---------- FX-11 / D9: chạy tiếp việc tốn tiền phải duyệt lại ----------

def _muse_loi(may, mt, dong, **kw_loi):
    _, d = _tao(may, "muse_clip", _muse_ts(mt))
    id_ = d["viec"]["id"]
    assert _duyet(may, dong, id_)[0] == 200
    may.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    may.kho.danh_dau_phien(id_)
    may.kho.cong_chi_phi(id_, 0.5, 3, True)
    may.kho.chuyen(id_, ["dang_chay"], "loi", "he_thong", loi="quá giờ", **kw_loi)
    return id_


def test_chay_tiep_ton_tien_409_can_duyet_lai(may4, mt4, dong):
    id_ = _muse_loi(may4, mt4, dong)
    assert chu_ky.kiem_duyet(may4.khoa_ky.public_key(), may4.kho.lay(id_)) is True   # duyệt cũ còn đúng chữ ký
    assert may4.goi("GET", f"/viec/{id_}")[1]["viec"]["co_the_chay_tiep"] is False
    s, r = may4.goi("POST", f"/viec/{id_}/chay-tiep", {"boi": "nhan"})
    assert (s, r) == (409, {"loi": "Việc tốn tiền: cần duyệt lại"})
    assert may4.kho.lay(id_)["trang_thai"] == "loi"


def test_co_the_chay_tiep_sai_voi_loai_ton_tien():
    v = {"trang_thai": "loi", "phien_da_tao": 1, "so_lan_claude": 1}
    for ma in ("muse_clip", "voice_genmax", "poster_len_lich", "taovideo"):
        assert api.co_the_chay_tiep(dict(v, loai=ma)) is False, ma
    assert api.co_the_chay_tiep(dict(v, loai="phan_tich_uid")) is True


def test_xin_duyet_lai_tu_loi(may4, mt4, dong):
    id_ = _muse_loi(may4, mt4, dong)
    ky_cu = may4.kho.lay(id_)["chu_ky_duyet"]
    s, r = may4.goi("POST", f"/viec/{id_}/xin-duyet-lai", {"boi": "comeofage"})
    assert s == 200, r
    v = r["viec"]
    assert (v["trang_thai"], v["buoc"]) == ("cho_duyet", "chay")
    assert v["loi_duyet"] is None and v["duyet_boi"] is None and v["duyet_luc"] is None
    assert "chu_ky_duyet" not in v
    luu = may4.kho.lay(id_)
    assert luu["chu_ky_duyet"] is None and luu["session_id"]            # giữ phiên để resume sau duyệt
    sk = may4.kho.su_kien(id_)[-1]
    assert (sk["tu"], sk["den"], sk["boi"]) == ("loi", "cho_duyet", "comeofage") and "duyệt lại" in sk["ghi_chu"]
    # chưa duyệt lại thì vòng chạy không có chữ ký để chạy
    assert chu_ky.kiem_duyet(may4.khoa_ky.public_key(), luu) is False
    # duyệt lại bằng chữ ký MỚI (mật khẩu nhập lại trên web) → cho
    dong.toi(60)
    s, r = _duyet(may4, dong, id_, boi="nhan")
    assert s == 200 and r["viec"]["trang_thai"] == "cho" and r["viec"]["duyet_boi"] == "nhan"
    assert may4.kho.lay(id_)["chu_ky_duyet"] != ky_cu
    # xin lại lần nữa khi đang cho → 409
    assert may4.goi("POST", f"/viec/{id_}/xin-duyet-lai", {"boi": "nhan"})[0] == 409


def test_xin_duyet_lai_sau_khi_an_xoa_luu_tru(may4, mt4, dong):
    """Cùng bất biến P1, qua đường "xin duyệt lại" (việc tốn tiền, đi qua API thật)."""
    id_ = _muse_loi(may4, mt4, dong)
    may4.kho.dat_luu_tru(id_, True, "nhan")
    assert may4.kho.lay(id_)["luu_tru"] == 1
    s, r = may4.goi("POST", f"/viec/{id_}/xin-duyet-lai", {"boi": "comeofage"})
    assert s == 200 and r["viec"]["luu_tru"] == 0
    assert may4.kho.lay(id_)["luu_tru"] == 0


def test_xin_duyet_lai_khong_dung_lai_duyet_cu(may4, mt4, dong):
    """Gửi lại đúng body duyệt cũ (chữ ký cũ, duyet_luc cũ) sau khi xin duyệt lại: duyet_luc cũ quá 10 phút → 400;
    không đường nào đưa việc về cho mà không có lời duyệt mới."""
    _, d = _tao(may4, "muse_clip", _muse_ts(mt4))
    id_ = d["viec"]["id"]
    luc = _luc_duyet(dong)
    ky = _ky_duyet(may4, id_, duyet_luc=luc)
    body = {"loi_duyet": "Duyệt, làm đúng như ước tính", "duyet_luc": luc, "boi": "nhan", "chu_ky_duyet": ky}
    assert may4.goi("POST", f"/viec/{id_}/duyet", body)[0] == 200
    may4.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    may4.kho.chuyen(id_, ["dang_chay"], "loi", "he_thong", loi="x")
    assert may4.goi("POST", f"/viec/{id_}/xin-duyet-lai", {"boi": "nhan"})[0] == 200
    dong.toi(3600)
    assert may4.goi("POST", f"/viec/{id_}/duyet", body)[0] == 400
    assert may4.kho.lay(id_)["trang_thai"] == "cho_duyet"


def test_xin_duyet_lai_tu_can_tra_loi(may4, mt4, dong):
    _, d = _tao(may4, "muse_clip", _muse_ts(mt4))
    id_ = d["viec"]["id"]
    assert _duyet(may4, dong, id_)[0] == 200
    _vao_can_tra_loi(may4, id_, CanNguoiDung("chon", "Tag nào?", ("A", "B")))
    s, r = may4.goi("POST", f"/viec/{id_}/xin-duyet-lai", {"boi": "nhan"})
    assert s == 200 and r["viec"]["trang_thai"] == "cho_duyet" and r["viec"]["loi_duyet"] is None


def test_xin_duyet_lai_bi_tu_choi(may4, mt4, dong):
    # loại miễn phí
    _, d = _tao(may4)
    pid = d["viec"]["id"]
    _vao_loi(may4, pid, phien=1, so_lan=1)
    s, r = may4.goi("POST", f"/viec/{pid}/xin-duyet-lai", {"boi": "nhan"})
    assert s == 409 and may4.kho.lay(pid)["trang_thai"] == "loi"
    # trạng thái không phải loi/can_tra_loi
    _, m = _tao(may4, "muse_clip", _muse_ts(mt4))
    mid = m["viec"]["id"]
    assert may4.goi("POST", f"/viec/{mid}/xin-duyet-lai", {"boi": "nhan"})[0] == 409      # cho_duyet
    may4.kho.chuyen(mid, ["cho_duyet"], "huy", "nhan")
    assert may4.goi("POST", f"/viec/{mid}/xin-duyet-lai", {"boi": "nhan"})[0] == 409      # huy
    # tiến trình cũ có thể còn sống → không mở đường chạy song song (CL21)
    p2 = mt4.gocs[0] / f"Ví {UID}"
    (p2 / "kich-ban").mkdir(parents=True)
    _, m2 = _tao(may4, "muse_clip", {**_muse_ts(mt4), "du_an": ma_du_an(p2)})
    id2 = m2["viec"]["id"]
    assert _duyet(may4, dong, id2)[0] == 200
    may4.kho.chuyen(id2, ["cho"], "dang_chay", "he_thong")
    may4.kho.chuyen(id2, ["dang_chay"], "loi", "he_thong", loi="x", ket_qua={"khong_giet_duoc": True})
    s, r = may4.goi("POST", f"/viec/{id2}/xin-duyet-lai", {"boi": "nhan"})
    assert s == 409 and "còn sống" in r["loi"] and may4.kho.lay(id2)["trang_thai"] == "loi"
    # thiếu boi / không ký / không có việc / sai phương thức
    assert may4.goi("POST", f"/viec/{id2}/xin-duyet-lai", {})[0] == 400
    assert may4.goi("POST", f"/viec/{id2}/xin-duyet-lai", {"boi": "nhan"}, ky=False)[0] == 401
    assert may4.goi("POST", "/viec/j20261117090000zzzz/xin-duyet-lai", {"boi": "nhan"})[0] == 404
    assert may4.goi("GET", f"/viec/{id2}/xin-duyet-lai")[0] == 404


def test_xin_duyet_lai_404_khi_ha_ve_dot_3(tmp_path, mt4, dong):
    m = May(tmp_path, mt4, dong, hm={**HAN_MUC_TRAN, "dot_bat": 3})
    try:
        v = m.kho.tao("muse_clip", "k", _muse_ts(mt4), "nhe", "cho", "nhan")
        m.kho.chuyen(v["id"], ["cho"], "loi", "he_thong", loi="x")
        assert m.goi("POST", f"/viec/{v['id']}/xin-duyet-lai", {"boi": "nhan"})[0] == 404
        assert m.kho.lay(v["id"])["trang_thai"] == "loi"
    finally:
        m.dong_lai()


def test_xin_duyet_lai_genmax_co_uoc_tinh_giu_buoc_chay(may4, mt4, dong):
    _, d = _tao(may4, "voice_genmax", _gm_ts(mt4))
    id_ = d["viec"]["id"]
    may4.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    may4.kho.chuyen(id_, ["dang_chay"], "cho_duyet", "he_thong", uoc_tinh="Kế hoạch: 2 bản GenMax, tổng 900 ký tự")
    assert _duyet(may4, dong, id_)[0] == 200
    may4.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    may4.kho.chuyen(id_, ["dang_chay"], "loi", "he_thong", loi="GenMax 500")
    s, r = may4.goi("POST", f"/viec/{id_}/xin-duyet-lai", {"boi": "nhan"})
    assert s == 200 and (r["viec"]["trang_thai"], r["viec"]["buoc"]) == ("cho_duyet", "chay")
    assert r["viec"]["uoc_tinh"].startswith("Kế hoạch") and r["viec"]["duyet_luc"] is None
    luu = may4.kho.lay(id_)
    with pytest.raises(api.ThamSoLoi):                  # chưa duyệt lại: không dựng được lệnh --dong-y
        dm.DANH_MUC["voice_genmax"].lap_buoc(luu["tham_so"], luu, mt4)


def test_xin_duyet_lai_genmax_chua_co_uoc_tinh_ve_uoc_tinh(may4, mt4, dong):
    """Lỗi ngay ở pha ước tính (chưa có uoc_tinh) → không đưa đi duyệt khi chưa biết tốn bao nhiêu: về cho +
    buoc uoc_tinh (pha miễn phí), xong ước tính vòng chạy tự đưa sang cho_duyet."""
    _, d = _tao(may4, "voice_genmax", _gm_ts(mt4))
    id_ = d["viec"]["id"]
    may4.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    may4.kho.chuyen(id_, ["dang_chay"], "loi", "he_thong", loi="không đọc được ước tính")
    s, r = may4.goi("POST", f"/viec/{id_}/xin-duyet-lai", {"boi": "nhan"})
    assert s == 200 and (r["viec"]["trang_thai"], r["viec"]["buoc"]) == ("cho", "uoc_tinh")
    assert r["viec"]["uoc_tinh"] is None


def test_get_viec_tra_tham_so_chuan_chuoi(may4, mt4):
    _, d = _tao(may4, "poster_len_lich", {"folder_id": 7, "so_video_ngay": 100})
    ct = may4.goi("GET", f"/viec/{d['viec']['id']}")[1]
    assert isinstance(ct["tham_so_chuan"], str)
    assert ct["tham_so_chuan"] == '{"folder_id":7,"so_video_ngay":100}'


def test_poster_tong_100_video_moi_tai_khoan_api(may4, mt4, dong):
    assert _tao(may4, "poster_len_lich", {"folder_id": 7, "so_video_ngay": 100})[0] == 201
    s, r = _tao(may4, "poster_len_lich", {"folder_id": 9, "so_video_ngay": 100})
    assert s == 201                                      # tài khoản (folder) khác: hạn mức riêng
    assert _tao(may4, "poster_len_lich", {"folder_id": 9, "so_video_ngay": 1})[0] == 429   # >2 việc/ngày


# ---------- FX-14 / D9: tra-loi việc tốn tiền, chan_ton_tien, lý do duyệt lại ----------

LOI_TRA_LOI_TON_TIEN = "Việc tốn tiền: bấm Xin duyệt lại rồi duyệt bằng mật khẩu"


@pytest.mark.parametrize("cau_hoi,tra_loi", [
    (CanNguoiDung("chon", "Tag nào?", ("A", "B")), "A"),
    (CanNguoiDung("khong_ro", "Không rõ kết quả"), "tiep_tuc"),
    (CanNguoiDung("viec_tay", "Mở app"), "da_lam_xong"),
])
def test_tra_loi_ton_tien_409_khong_doi_trang_thai(may4, mt4, dong, cau_hoi, tra_loi):
    _, d = _tao(may4, "muse_clip", _muse_ts(mt4))
    id_ = d["viec"]["id"]
    assert _duyet(may4, dong, id_)[0] == 200
    _vao_can_tra_loi(may4, id_, cau_hoi)
    so_sk = len(may4.kho.su_kien(id_))
    s, r = may4.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": tra_loi, "boi": "nhan"})
    assert (s, r) == (409, {"loi": LOI_TRA_LOI_TON_TIEN})
    luu = may4.kho.lay(id_)
    assert luu["trang_thai"] == "can_tra_loi" and luu["cau_hoi"]["noi_dung"] == cau_hoi.noi_dung
    assert may4.kho.tra_loi_cua(id_) == [] and len(may4.kho.su_kien(id_)) == so_sk


def test_tra_loi_mien_phi_van_nhan(may4):
    _, d = _tao(may4)
    id_ = d["viec"]["id"]
    _vao_can_tra_loi(may4, id_, CanNguoiDung("chon", "Tag nào?", ("A", "B")))
    s, r = may4.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "A", "boi": "nhan"})
    assert s == 200 and r["viec"]["trang_thai"] == "cho"


def test_suc_khoe_chan_ton_tien(tmp_path, mt, dong, may):
    s, d = may.goi("GET", "/suc-khoe")
    assert s == 200 and d["chan_ton_tien"] is False            # trang_thai_lan không có khoá → False
    for tl, mong in (({"chan_ton_tien": True}, True), ({"chan_ton_tien": False}, False),
                     ({"chan_ton_tien": None}, False), (None, False)):
        m = May(tmp_path / f"m{len(str(tl))}", mt, dong, trang_thai_lan=lambda tl=tl: tl)
        try:
            s, d = m.goi("GET", "/suc-khoe")
            assert s == 200 and d["chan_ton_tien"] is mong, (tl, d)
        finally:
            m.dong_lai()


def test_xin_duyet_lai_tu_can_tra_loi_ghi_ly_do(may4, mt4, dong):
    """§5.2: lần chạy sau khi duyệt lại từ can_tra_loi phải báo agent người dùng không trả lời câu hỏi."""
    _, d = _tao(may4, "muse_clip", _muse_ts(mt4))
    id_ = d["viec"]["id"]
    assert _duyet(may4, dong, id_)[0] == 200
    may4.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    cau = "Tag nào? " + "x" * 600
    may4.kho.chuyen(id_, ["dang_chay"], "can_tra_loi", "he_thong", cau_hoi=CanNguoiDung("chon", cau, ("A", "B")),
                    ket_qua={"tom_tat": "đã làm 1 clip", "so_codex": 2})
    s, r = may4.goi("POST", f"/viec/{id_}/xin-duyet-lai", {"boi": "nhan"})
    assert s == 200, r
    kq = may4.kho.lay(id_)["ket_qua"]
    assert kq["tom_tat"] == "đã làm 1 clip" and kq["so_codex"] == 2       # không làm mất ket_qua cũ (B7)
    assert kq["duyet_lai_tu"] == "can_tra_loi"
    ly = kq["ly_do_duyet_lai"]
    assert ly == (f"Người dùng không trả lời câu hỏi trước ({cau[:500]}) mà duyệt lại để làm tiếp. "
                  "Không hỏi lại câu đó; chỗ nào cần quyết định thì chọn phương án an toàn nhất "
                  "(không tốn thêm tiền), không làm được thì dừng và báo")
    assert r["viec"]["ket_qua"]["ly_do_duyet_lai"] == ly
    assert may4.kho.lay(id_)["cau_hoi"]["noi_dung"] == cau                # giữ câu hỏi để resume


def test_xin_duyet_lai_tu_loi_ghi_ly_do_la_loi_cu(may4, mt4, dong):
    id_ = _muse_loi(may4, mt4, dong)
    s, r = may4.goi("POST", f"/viec/{id_}/xin-duyet-lai", {"boi": "nhan"})
    assert s == 200, r
    kq = may4.kho.lay(id_)["ket_qua"]
    assert (kq["duyet_lai_tu"], kq["ly_do_duyet_lai"]) == ("loi", "quá giờ")
    # duyệt lại → chạy → lại can_tra_loi → xin duyệt lại lần nữa: lý do ghi đè theo lần mới
    assert _duyet(may4, dong, id_)[0] == 200
    _vao_can_tra_loi(may4, id_, CanNguoiDung("khong_ro", "Kết quả lạ"))
    assert may4.goi("POST", f"/viec/{id_}/xin-duyet-lai", {"boi": "nhan"})[0] == 200
    kq = may4.kho.lay(id_)["ket_qua"]
    assert kq["duyet_lai_tu"] == "can_tra_loi" and "(Kết quả lạ)" in kq["ly_do_duyet_lai"]


# ---------- đợt 6: sửa video (docs/sua-video.md §7, §8.1, D10) ----------
# Dự án GIẢ luồng C trong tmp_path (helper test lõi B-6); Python engine giả; không đụng runner thật 8788.

import test_runner_danh_muc as tdm  # noqa: E402
from runner import sua_video as sv  # noqa: E402


@pytest.fixture
def ms(tmp_path, mt, dong, monkeypatch):
    tdm.dung_du_an_c(mt._p)
    py = tmp_path / "engine" / "python.exe"
    py.parent.mkdir(parents=True)
    py.write_bytes(b"")
    monkeypatch.setenv("KHO_PYTHON_ENGINE", str(py))
    monkeypatch.setenv("KHO_ENGINE_DIR", str(py.parent))
    monkeypatch.setenv("AUTOVIDEO_KHOA_MAY", str(tmp_path / "khoa" / ".render-may.lock"))
    m = May(tmp_path, mt, dong)
    m.v = tdm.video_sua(mt._p)  # type: ignore[attr-defined]
    m.du_an = ma_du_an(mt._p)  # type: ignore[attr-defined]
    yield m
    m.dong_lai()


def _body_sua(ms, **kw) -> dict:
    _, d = ms.goi("GET", f"/sua-video/{UID}/{ms.v.ma_video}")
    b = {"sua_luc": d["video"]["sua_luc"], "phu_de_sha": d["phu_de"]["sha"],
         "phu_de": [{"i": 1, "text": "Xe chạy êm, cực bền"}],
         "doi_clip": [{"seg": 1, "clip": "raw-4_002_proof_canh-2.mp4"}], "doi_cho": [], "boi": "nhan"}
    b.update(kw)
    return b


def _luu(ms, **kw) -> tuple[int, dict]:
    """Như Worker /luu: (1) ban-sua rồi (2) tạo việc sua_video."""
    s, d = ms.goi("POST", f"/sua-video/{UID}/{ms.v.ma_video}/ban-sua", _body_sua(ms, **kw))
    assert s == 201, d
    return _tao(ms, "sua_video", {"uid": UID, "du_an": d["du_an"], "ma_video": ms.v.ma_video,
                                  "ban_sua": d["ban_sua"]})


def _den(ms, id_: str, *ds: str) -> None:
    tu = ms.kho.lay(id_)["trang_thai"]
    for den in ds:
        ms.kho.chuyen(id_, [tu], den, "he_thong")
        tu = den


def test_get_ds_video_sua(ms):
    s, d = ms.goi("GET", f"/sua-video/{UID}")
    assert s == 200
    ten = [v["ten"] for v in d["videos"]]
    assert ten == ["50oto2809_060.mp4", "50oto2809_061.mp4", "50oto2809_062.mp4"]
    v = d["videos"][1]
    assert set(v) == {"ma_video", "du_an", "goc", "thu_muc", "ten", "sua_luc", "luong", "sua_duoc", "ly_do",
                      "viec_mo"}                                         # KHÔNG có duong_dan
    assert v["ma_video"] == ms.v.ma_video and v["du_an"] == ms.du_an and v["thu_muc"] == "output_poster"
    assert v["goc"] == ms.mt.gocs[0].as_posix() and v["luong"] == "C" and v["sua_duoc"] is True
    assert v["sua_luc"] == tdm.tsv.T_VIDEO // 1_000_000 and v["viec_mo"] is None   # mili giây (chốt B-6)
    assert ms.goi("GET", f"/sua-video/{UID2}")[1] == {"videos": []}
    assert ms.goi("GET", "/sua-video/123")[0] == 404
    assert ms.goi("GET", f"/sua-video/{UID}", khoa=False)[0] == 401


def test_get_chi_tiet_va_ung_vien(ms):
    s, d = ms.goi("GET", f"/sua-video/{UID}/{ms.v.ma_video}")
    assert s == 200, d
    assert d["video"]["ten"] == "50oto2809_061.mp4" and "duong_dan" not in d["video"]
    assert (d["luong"], d["plan_id"], d["tien_to"], d["me"]) == ("C", 61, "50oto2809", None)
    assert d["ghi_chu_luong_a"] is False and d["viec_mo"] is None and d["lich_su"] == []
    assert [c["text"] for c in d["phu_de"]["cau"]] == ["Cái này là sàn trợ giá nè ba mẹ ơi!", "Xe chạy trớn, cực bền",
                                                       "Mua ngay kẻo hết"]
    assert re.fullmatch(r"[0-9a-f]{64}", d["phu_de"]["sha"]) and d["phu_de"]["co_words"] is True
    assert [c["kind"] for c in d["canh"]] == ["BASE", "OVL", "OVL"] and d["canh"][1]["doi_duoc"] is True
    s, u = ms.goi("GET", f"/sua-video/{UID}/{ms.v.ma_video}/ung-vien?seg=1")
    assert s == 200 and u["ung_vien"] and all(x["role"] == "proof" for x in u["ung_vien"])
    for q, ma in (("seg=0", 400), ("seg=200", 400), ("seg=abc", 400), ("", 400), ("seg=1&seg=-1", 400)):
        assert ms.goi("GET", f"/sua-video/{UID}/{ms.v.ma_video}/ung-vien?{q}")[0] == ma, q
    assert ms.goi("GET", f"/sua-video/{UID}/{'0' * 16}")[0] == 404
    assert ms.goi("GET", f"/sua-video/{UID}/{ms.v.ma_video.upper()}")[0] == 404


def test_post_ban_sua_luu_bang_va_tra_ma(ms):
    s, d = ms.goi("POST", f"/sua-video/{UID}/{ms.v.ma_video}/ban-sua", _body_sua(ms))
    assert s == 201, d
    assert set(d) == {"ban_sua", "du_an", "tom_tat"} and d["du_an"] == ms.du_an
    assert d["tom_tat"] == {"so_cau": 1, "so_clip": 1, "so_doi_cho": 0}
    row = ms.kho.lay_ban_sua(d["ban_sua"])
    assert row["uid"] == UID and row["ma_video"] == ms.v.ma_video and row["tao_boi"] == "nhan"
    assert sv.ma_ban_sua(row["noi_dung"]) == d["ban_sua"] and "boi" not in row["noi_dung"]
    # gửi lại y hệt → cùng mã; chữ khác dạng Unicode (NFD) nhưng cùng nghĩa → CÙNG mã (chuẩn hoá trước khi băm)
    import unicodedata
    assert ms.goi("POST", f"/sua-video/{UID}/{ms.v.ma_video}/ban-sua", _body_sua(ms))[1]["ban_sua"] == d["ban_sua"]
    nfd = _body_sua(ms, phu_de=[{"i": 1, "text": unicodedata.normalize("NFD", "Xe chạy êm, cực bền")}])
    assert ms.goi("POST", f"/sua-video/{UID}/{ms.v.ma_video}/ban-sua", nfd)[1]["ban_sua"] == d["ban_sua"]
    hoa = _body_sua(ms)
    hoa["phu_de_sha"] = hoa["phu_de_sha"].upper()                         # sha viết hoa vẫn cùng mã
    assert ms.goi("POST", f"/sua-video/{UID}/{ms.v.ma_video}/ban-sua", hoa)[1]["ban_sua"] == d["ban_sua"]


@pytest.mark.parametrize("sua, ma", [
    ({"sua_luc": 1}, 409),                                           # video đã đổi
    ({"phu_de_sha": "0" * 64}, 409),                                 # phụ đề đã đổi
    ({"phu_de": [{"i": 1, "text": "chữ {\\an8}"}]}, 400),            # thẻ ASS
    ({"phu_de": [{"i": 1, "text": "a --> b"}]}, 400),               # phá SRT
    ({"phu_de": [{"i": 1, "text": "hai\ndòng"}]}, 400),
    ({"phu_de": [{"i": 99, "text": "x"}]}, 400),
    ({"doi_clip": [{"seg": 0, "clip": "raw-4_002_proof_canh-2.mp4"}]}, 400),   # BASE không đổi được
    ({"doi_clip": [{"seg": 1, "clip": "raw-5_002_detail_canh-2.mp4"}]}, 400),  # khác vai
    ({"la": 1}, 400),
    ({"boi": "a b"}, 400),
    ({"phu_de": [], "doi_clip": []}, 400),                           # không có thay đổi
])
def test_post_ban_sua_tu_choi(ms, sua, ma):
    s, d = ms.goi("POST", f"/sua-video/{UID}/{ms.v.ma_video}/ban-sua", _body_sua(ms, **sua))
    assert s == ma and "loi" in d, (s, d)
    assert ms.kho._ket_noi().execute("SELECT COUNT(*) FROM ban_sua").fetchone()[0] == 0


def test_post_ban_sua_413_khong_ky_404(ms):
    to = _body_sua(ms, doi_cho=[[1, 2]] * 3000)
    assert ms.goi("POST", f"/sua-video/{UID}/{ms.v.ma_video}/ban-sua", to)[0] == 413
    assert ms.goi("POST", f"/sua-video/{UID}/{ms.v.ma_video}/ban-sua", _body_sua(ms), ky=False)[0] == 401
    assert ms.goi("POST", f"/sua-video/{UID}/{'0' * 16}/ban-sua", _body_sua(ms))[0] == 404
    assert ms.goi("POST", f"/sua-video/{UID}/{ms.v.ma_video}/khac", _body_sua(ms))[0] == 404
    assert ms.goi("GET", f"/sua-video/{UID}/{ms.v.ma_video}/ban-sua")[0] == 404


def test_tao_sua_video_va_trung_ma_video_409(ms):
    s, d = _luu(ms)
    assert s == 201, d
    v = d["viec"]
    assert v["loai"] == "sua_video" and v["trang_thai"] == "cho" and v["lan_chay"] == "gpu"
    assert v["tham_so"]["ma_video"] == ms.v.ma_video and v["co_session"] is False
    # Worker /luu lần 2 trong lúc việc còn mở → 409 kèm `trung` (Worker đọc trung.id)
    s2, d2 = _luu(ms, phu_de=[{"i": 1, "text": "Bản khác"}])
    assert s2 == 409 and d2["trung"]["id"] == v["id"]
    # hoàn tác trong lúc việc sửa còn mở → 409 (hai loại không bao giờ cùng mở trên một video)
    s3, d3 = _tao(ms, "hoan_tac_sua", {"uid": UID, "du_an": ms.du_an, "ma_video": ms.v.ma_video, "viec_goc": v["id"]})
    assert s3 == 409 and d3["trung"]["id"] == v["id"]
    # GET danh sách / chi tiết báo việc đang mở
    lst = ms.goi("GET", f"/sua-video/{UID}")[1]["videos"]
    assert [x["viec_mo"] for x in lst] == [None, v["id"], None]
    ct = ms.goi("GET", f"/sua-video/{UID}/{ms.v.ma_video}")[1]
    assert ct["viec_mo"] == v["id"] and ct["lich_su"][0]["viec"] == v["id"]
    assert set(ct["lich_su"][0]) == {"viec", "loai", "trang_thai", "luc", "boi", "viec_goc", "hoan_tac_duoc"}
    assert ct["lich_su"][0]["hoan_tac_duoc"] is False


def test_tao_sua_video_ban_sua_khong_hop_le(ms):
    s, d = ms.goi("POST", f"/sua-video/{UID}/{ms.v.ma_video}/ban-sua", _body_sua(ms))
    ts = {"uid": UID, "du_an": ms.du_an, "ma_video": ms.v.ma_video, "ban_sua": d["ban_sua"]}
    assert _tao(ms, "sua_video", dict(ts, ban_sua="b" + "f" * 16))[0] == 400          # không có trong bảng
    v60 = tdm.video_sua(ms.mt._p, "50oto2809_060.mp4")
    assert _tao(ms, "sua_video", dict(ts, ma_video=v60.ma_video))[0] == 400           # bản của video khác
    # video đã đổi sau khi lưu bản sửa (sua_luc lệch) → 409, không tạo việc dựng lại mù
    f = ms.mt._p / "output_poster" / "50oto2809_061.mp4"
    os.utime(f, ns=(tdm.tsv.T_VIDEO + 10**9, tdm.tsv.T_VIDEO + 10**9))
    assert _tao(ms, "sua_video", ts)[0] == 409
    assert ms.kho.ds() == []


def test_hoan_tac_sua_chi_khi_viec_goc_xong(ms):
    s, d = _luu(ms)
    goc = d["viec"]["id"]
    ts = {"uid": UID, "du_an": ms.du_an, "ma_video": ms.v.ma_video, "viec_goc": goc}
    _den(ms, goc, "dang_chay", "loi")
    s, r = _tao(ms, "hoan_tac_sua", ts)
    assert s == 400 and "xong" in r["loi"]                               # việc gốc không xong → từ chối
    assert _tao(ms, "hoan_tac_sua", dict(ts, viec_goc="j20261117090000zzzz"))[0] == 400   # không có
    _den(ms, goc, "cho", "dang_chay", "xong")
    v60 = tdm.video_sua(ms.mt._p, "50oto2809_060.mp4")
    assert _tao(ms, "hoan_tac_sua", dict(ts, ma_video=v60.ma_video))[0] == 400            # việc gốc của video khác
    ct = ms.goi("GET", f"/sua-video/{UID}/{ms.v.ma_video}")[1]
    assert ct["lich_su"][0]["hoan_tac_duoc"] is True
    s, r = _tao(ms, "hoan_tac_sua", ts)
    assert s == 201 and r["viec"]["loai"] == "hoan_tac_sua" and r["viec"]["trang_thai"] == "cho"
    ct = ms.goi("GET", f"/sua-video/{UID}/{ms.v.ma_video}")[1]
    assert ct["viec_mo"] == r["viec"]["id"]
    assert [x["loai"] for x in ct["lich_su"]] == ["hoan_tac_sua", "sua_video"]
    assert all(x["hoan_tac_duoc"] is False for x in ct["lich_su"])       # đang có việc mở
    assert ct["lich_su"][0]["viec_goc"] == goc and ct["lich_su"][1]["viec_goc"] is None
    # sửa mới trong lúc hoàn tác còn mở → 409
    assert _luu(ms, phu_de=[{"i": 1, "text": "Lần ba"}])[0] == 409
    # hoàn tác xong → lần sửa đó không hoàn tác được nữa
    _den(ms, r["viec"]["id"], "dang_chay", "xong")
    ct = ms.goi("GET", f"/sua-video/{UID}/{ms.v.ma_video}")[1]
    assert ct["viec_mo"] is None and all(x["hoan_tac_duoc"] is False for x in ct["lich_su"])


def test_sua_video_chay_tiep_cung_id(ms):
    """Mã thoát 5 (hỏng giữa lúc thay file): chạy tiếp CÙNG id để bộ chuyển đổi đọc nhật ký làm nốt (§6.1, §6.3).
    FX-22: chỉ bản sửa KHÔNG đổi chữ phụ đề (bản có chữ: xem test_sua_chu_chay_lai_chay_tiep_409)."""
    s, d = _luu(ms, phu_de=[])
    id_ = d["viec"]["id"]
    _den(ms, id_, "dang_chay", "loi")
    assert ms.goi("GET", f"/viec/{id_}")[1]["viec"]["co_the_chay_tiep"] is True
    # đang có hoàn tác mở trên cùng video → không chạy tiếp
    h = ms.kho.tao("hoan_tac_sua", ms.v.ma_video, {"ma_video": ms.v.ma_video}, "gpu", "cho", "nhan")
    s, r = ms.goi("POST", f"/viec/{id_}/chay-tiep", {"boi": "nhan"})
    assert s == 409 and r["trung"]["id"] == h["id"]
    ms.kho.chuyen(h["id"], ["cho"], "huy", "nhan")
    s, r = ms.goi("POST", f"/viec/{id_}/chay-tiep", {"boi": "nhan"})
    assert s == 200 and r["viec"]["id"] == id_ and r["viec"]["trang_thai"] == "cho"


LOI_SUA_CHU = "Sửa chữ phụ đề cần lưu lại và nhập mật khẩu — mở màn Sửa video để lưu lại"


@pytest.mark.parametrize("tt", ["loi", "huy"])
def test_sua_chu_chay_lai_chay_tiep_409(ms, tt):
    """FX-22 (§7.2a, D10 Q3): bản sửa có chữ phụ đề → chay-lai / chay-tiep 409, cờ co_the_chay_* = False."""
    s, d = _luu(ms)                                                      # _body_sua mặc định có sửa chữ câu 1
    assert s == 201, d
    id_ = d["viec"]["id"]
    _den(ms, id_, *(("dang_chay", "loi") if tt == "loi" else ("huy",)))
    v = ms.goi("GET", f"/viec/{id_}")[1]["viec"]
    assert v["co_the_chay_lai"] is False and v["co_the_chay_tiep"] is False and v["can_luu_lai_mat_khau"] is True
    assert [x for x in ms.goi("GET", "/viec")[1]["viec"] if x["id"] == id_][0]["co_the_chay_lai"] is False
    so_truoc = len(ms.kho.ds())
    s, r = ms.goi("POST", f"/viec/{id_}/chay-lai", {"boi": "nhan"})
    assert (s, r["loi"]) == (409, LOI_SUA_CHU)
    s, r = ms.goi("POST", f"/viec/{id_}/chay-tiep", {"boi": "nhan"})
    assert (s, r["loi"]) == (409, LOI_SUA_CHU)
    assert len(ms.kho.ds()) == so_truoc and ms.kho.lay(id_)["trang_thai"] == tt


def test_chi_doi_clip_van_chay_lai_duoc(ms):
    s, d = _luu(ms, phu_de=[])
    id_ = d["viec"]["id"]
    _den(ms, id_, "dang_chay", "loi")
    v = ms.goi("GET", f"/viec/{id_}")[1]["viec"]
    assert v["co_the_chay_lai"] is True and v["co_the_chay_tiep"] is True and v["can_luu_lai_mat_khau"] is False
    s, r = ms.goi("POST", f"/viec/{id_}/chay-lai", {"boi": "nhan"})
    assert s == 201 and r["viec"]["id"] != id_ and r["viec"]["tham_so"]["ban_sua"] == d["viec"]["tham_so"]["ban_sua"]


def test_viec_ra_co_the_chay_lai_loai_khac():
    v = {"id": "j1", "loai": "phan_tich_uid", "trang_thai": "loi"}
    assert api.viec_ra(v)["co_the_chay_lai"] is True and api.viec_ra(v)["can_luu_lai_mat_khau"] is False
    assert api.viec_ra(dict(v, trang_thai="huy"))["co_the_chay_lai"] is True
    assert api.viec_ra(dict(v, trang_thai="xong"))["co_the_chay_lai"] is False
    assert api.viec_ra(dict(v, trang_thai="loi"), sua_chu=True)["co_the_chay_lai"] is False


def test_viec_ra_kiem_tay_tu_loi_vong_lap():
    """FX-22 lỗi 2: mã 5 do bỏ qua có chủ đích → ket_qua.kiem_tay true + thông điệp liệt kê mục; không sửa dict gốc."""
    loi = ("Bước hoan_tac_sua thoát mã 5:\n[sua_video] mã 5: Video đã về bản cũ nhưng hoàn tác bỏ qua phụ đề "
           "(việc khác đã đổi) — kiểm tay\nKET_QUA_JSON " + json.dumps(
               {"trang_thai": "do_dang", "ly_do": "Video đã về bản cũ nhưng hoàn tác bỏ qua phụ đề (việc khác đã đổi)"
                " — kiểm tay", "canh_bao": ["c1"], "sao_luu": None, "video": "a.mp4", "giay": 1}, ensure_ascii=False))
    v = {"id": "j1", "loai": "hoan_tac_sua", "trang_thai": "loi", "loi": loi, "ket_qua": None}
    kq = api.viec_ra(v)["ket_qua"]
    assert kq["kiem_tay"] is True and kq["bo_qua"] == ["phụ đề"] and "phụ đề" in kq["thong_diep"]
    assert v["ket_qua"] is None
    # ket_qua sẵn có được giữ, chỉ thêm khoá
    assert api.viec_ra(dict(v, ket_qua={"khong_giet_duoc": False}))["ket_qua"]["khong_giet_duoc"] is False
    # loại khác / trạng thái khác: không suy
    assert api.viec_ra(dict(v, loai="phan_tich_uid"))["ket_qua"] is None
    assert api.viec_ra(dict(v, trang_thai="xong"))["ket_qua"] is None


def test_get_viec_sua_video_ma_5_kiem_tay(ms):
    s, d = _luu(ms, phu_de=[])
    id_ = d["viec"]["id"]
    ms.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    ly_do = "Hoàn nguyên bỏ qua render_batch.json vì việc khác đã đổi — không làm lại, kiểm tay"
    ms.kho.chuyen(id_, ["dang_chay"], "loi", "he_thong", loi=f"Bước sua_video thoát mã 5:\n[sua_video] mã 5: {ly_do}")
    v = ms.goi("GET", f"/viec/{id_}")[1]["viec"]
    assert v["trang_thai"] == "loi" and v["ket_qua"]["kiem_tay"] is True
    assert v["ket_qua"]["bo_qua"] == ["render_batch.json"] and v["ket_qua"]["ma_thoat"] == 5


def test_sua_video_ngay_429(tmp_path, mt, dong, monkeypatch):
    tdm.dung_du_an_c(mt._p)
    py = tmp_path / "py.exe"
    py.write_bytes(b"")
    monkeypatch.setenv("KHO_PYTHON_ENGINE", str(py))
    m = May(tmp_path, mt, dong, hm=dict(HAN_MUC_TRAN, sua_video_ngay=1))
    try:
        m.v = tdm.video_sua(mt._p)  # type: ignore[attr-defined]
        s, d = _luu(m)
        assert s == 201
        m.kho.chuyen(d["viec"]["id"], ["cho"], "huy", "nhan")
        assert _luu(m, phu_de=[{"i": 1, "text": "Lần hai"}])[0] == 429
    finally:
        m.dong_lai()


def test_sua_video_dong_khi_dot_bat_thap(tmp_path, mt, dong):
    tdm.dung_du_an_c(mt._p)
    m = May(tmp_path, mt, dong, hm=dict(HAN_MUC_TRAN, dot_bat=3))
    try:
        v = tdm.video_sua(mt._p)
        assert m.goi("GET", f"/sua-video/{UID}")[0] == 404
        assert m.goi("GET", f"/sua-video/{UID}/{v.ma_video}")[0] == 404
        assert m.goi("POST", f"/sua-video/{UID}/{v.ma_video}/ban-sua", {"boi": "nhan"})[0] == 404
        assert _tao(m, "sua_video", {"uid": UID})[0] == 400
    finally:
        m.dong_lai()


def test_chi_tiet_video_khong_sua_duoc_van_tra_lich_su(ms):
    s, d = _luu(ms)
    _den(ms, d["viec"]["id"], "dang_chay", "xong")
    (ms.mt._p / "output_poster" / "50oto2809_061.done.json").unlink()   # mất bằng chứng nguồn gốc
    s, ct = ms.goi("GET", f"/sua-video/{UID}/{ms.v.ma_video}")
    assert s == 200 and ct["video"]["sua_duoc"] is False and ct["video"]["ly_do"]
    assert ct["phu_de"] is None and ct["canh"] == [] and ct["lich_su"][0]["hoan_tac_duoc"] is True
    assert ms.goi("GET", f"/sua-video/{UID}/{ms.v.ma_video}/ung-vien?seg=1")[0] == 409
    assert ms.goi("POST", f"/sua-video/{UID}/{ms.v.ma_video}/ban-sua", {"boi": "nhan", "sua_luc": 1})[0] == 409


# ================================================================ đợt 5 (B-4, D11): taovideo, trả lời phiên sống

from runner.kieu import KhongCoPhien, SaiTrangThai  # noqa: E402


@pytest.mark.parametrize("cau_hoi,tra_loi,xac,ton_tien,ket", [
    (CanNguoiDung("chon", "Tạo lại voice?", ("Đồng ý", "Bỏ qua")), "Đồng ý", True, True, "Đồng ý"),
    (CanNguoiDung("chon", "Tạo lại voice?", ("Đồng ý", "Bỏ qua")), "Đồng ý", False, True, 403),
    (CanNguoiDung("chon", "Tạo lại voice?", ("Đồng ý", "Bỏ qua")), "Đồng ý", False, False, "Đồng ý"),
    (CanNguoiDung("chon", "Tạo lại voice?", ("Đồng ý", "Bỏ qua")), "Khác", True, True, 400),
    (CanNguoiDung("cau_hoi", "Giá deal?"), "159k, deal 129k\n(hết 30/11)", True, True, "159k, deal 129k\n(hết 30/11)"),
    (CanNguoiDung("cau_hoi", "Giá deal?"), "159k", False, True, 403),
    (CanNguoiDung("cau_hoi", "Giá deal?"), "159k", False, False, 403),          # chữ tự do luôn cần mật khẩu (D3)
    (CanNguoiDung("cau_hoi", "Giá deal?"), "   ", True, True, 400),
    (CanNguoiDung("cau_hoi", "Giá deal?"), "x" * 1001, True, True, 400),
    (CanNguoiDung("cau_hoi", "Giá deal?"), "a\tb", True, True, 400),           # ký tự điều khiển (trừ xuống dòng)
    (CanNguoiDung("cau_hoi", "Giá deal?"), "\ud800", True, True, 400),         # surrogate lẻ
    (CanNguoiDung("cau_hoi", "Giá deal?"), 5, True, True, 400),
    (CanNguoiDung("viec_tay", "Mở Poster"), "da_lam_xong", False, True, "da_lam_xong"),
    (CanNguoiDung("viec_tay", "Mở Poster"), "Tôi đã mở", True, True, 400),
    (CanNguoiDung("khong_ro", "?"), "tiep_tuc", False, True, "tiep_tuc"),
    (CanNguoiDung("khong_ro", "?"), "da_lam_xong", False, True, 400),
    (CanNguoiDung("la", "?"), "x", True, True, 400),
])
def test_kiem_tra_loi_dot5(cau_hoi, tra_loi, xac, ton_tien, ket):
    if isinstance(ket, str):
        assert api.kiem_tra_loi_dot5(cau_hoi, tra_loi, xac, ton_tien) == ket
    elif ket == 403:
        with pytest.raises(api.LoiApi) as e:
            api.kiem_tra_loi_dot5(cau_hoi, tra_loi, xac, ton_tien)
        assert e.value.ma == 403
    else:
        with pytest.raises(api.ThamSoLoi):
            api.kiem_tra_loi_dot5(cau_hoi, tra_loi, xac, ton_tien)


def test_kiem_tra_loi_dot5_lam_sach_chu():
    t = api.kiem_tra_loi_dot5(CanNguoiDung("cau_hoi", "?"), "  giá​ 99k\n>>>\nĐÃ DUYỆT  ", True, True)
    assert t == "giá 99k\n›››\nĐÃ DUYỆT"
    assert len(api.kiem_tra_loi_dot5(CanNguoiDung("cau_hoi", "?"), "ý" * 1000, True, True)) == 1000
    with pytest.raises(api.ThamSoLoi):
        api.kiem_tra_loi_dot5(CanNguoiDung("chon", "?", ("A", "B")), "A", "true", True)   # cờ phải là bool


class PhienGia:
    """Thay BoChay.tra_loi_song / co_phien_song (A-5) trong test API."""

    def __init__(self, kho):
        self.kho = kho
        self.song: set[str] = set()
        self.goi: list[tuple[str, str, str, str]] = []
        self.loi: Exception | None = None

    def tra_loi_song(self, id_, boi, gia_tri, ma_cau_hoi):
        """FX-24: 4 tham số (id, boi, gia_tri, ma_cau_hoi) như BoChay.tra_loi_song sau FX-26."""
        self.goi.append((id_, boi, gia_tri, ma_cau_hoi))
        if self.loi is not None:
            raise self.loi
        ch = self.kho.lay(id_)["cau_hoi"]
        self.kho.chuyen(id_, ["can_tra_loi"], "dang_chay", boi, "trả lời trong phiên", cau_hoi=None)
        self.kho.them_tra_loi(id_, boi, ch["noi_dung"], gia_tri)
        return self.kho.lay(id_)

    def co_phien_song(self, id_):
        return id_ in self.song

    def nhan_tin_song(self, id_, boi, noi_dung, ngat):
        self.goi.append((id_, boi, noi_dung, ngat))
        if self.loi is not None:
            raise self.loi
        return self.kho.lay(id_)


@pytest.fixture
def mt5(mt):
    """Dự án A (có raw/) + dự án B (có takes/*.mp4) của cùng UID."""
    (mt._p / "raw").mkdir()
    b = mt.gocs[0] / f"Bình nước output {UID}"
    (b / "takes").mkdir(parents=True)
    (b / "takes" / "t1.mp4").write_bytes(b"x")
    mt._b = b  # type: ignore[attr-defined]
    return mt


@pytest.fixture
def may5(tmp_path, mt5, dong):
    pg = PhienGia(None)
    m = May(tmp_path, mt5, dong, tra_loi_song=pg.tra_loi_song, co_phien_song=pg.co_phien_song,
            nhan_tin_song=pg.nhan_tin_song)
    pg.kho = m.kho
    m.pg = pg  # type: ignore[attr-defined]
    yield m
    m.dong_lai()


def _tv_ts(mt, **kw):
    ts = {"uid": UID, "du_an_a": ma_du_an(mt._p), "du_an_b": "tu_tim", "wm": "nha.cua.mit"}
    ts.update(kw)
    return ts


MA_CH = "q0123456789ab"          # mã câu hỏi (§7.6) mà vòng chạy gắn khi hỏi trong phiên sống


def _taovideo_can_tra_loi(may, dong, cau_hoi):
    """Việc taovideo đã duyệt, đang can_tra_loi với câu hỏi mang mã MA_CH (nếu câu hỏi chưa có mã)."""
    s, d = _tao(may, "taovideo", _tv_ts(may.mt))
    assert s == 201, d
    id_ = d["viec"]["id"]
    assert _duyet(may, dong, id_, loi="Duyệt cả phiên")[0] == 200
    _vao_can_tra_loi(may, id_, cau_hoi if cau_hoi.ma else replace(cau_hoi, ma=MA_CH))
    may.pg.song.add(id_)
    return id_


def test_danh_muc_dot_5_co_taovideo(may5):
    s, d = may5.goi("GET", "/danh-muc")
    tv = next(x for x in d["loai"] if x["ma"] == "taovideo")
    assert tv["dot"] == 5 and tv["ton_tien"] is True and tv["lan_chay"] == "gpu"
    mo_ta = {t["ten"]: t for t in tv["tham_so"]}
    assert mo_ta["wm"]["lua_chon"] == ["khong", "nha.cua.mit"] and mo_ta["du_an_b"]["kieu"] == "du_an_hoac_tu_tim"


def test_tao_taovideo_tu_tim_va_400_kem_danh_sach(may5, mt5):
    s, d = _tao(may5, "taovideo", _tv_ts(mt5))
    assert s == 201, d
    v = d["viec"]
    assert v["trang_thai"] == "cho_duyet" and v["tham_so"]["du_an_b"] == ma_du_an(mt5._b)
    assert v["phien_song"] is False and v["co_the_xin_duyet_lai"] is False
    may5.kho.chuyen(v["id"], ["cho_duyet"], "huy", "nhan")
    # thêm dự án thứ 2 có takes → "tu_tim" không chốt được → 400 kèm danh sách cho web chọn
    b2 = mt5.gocs[0] / f"Bình nước 2 {UID}"
    (b2 / "takes").mkdir(parents=True)
    (b2 / "takes" / "x.mp4").write_bytes(b"x")
    s, d = _tao(may5, "taovideo", _tv_ts(mt5))
    assert s == 400 and "chọn" in d["loi"]
    assert {x["ma"] for x in d["ung_vien_b"] if x["co_takes"]} == {ma_du_an(mt5._b), ma_du_an(b2)}
    assert all(set(x) == {"ma", "ten", "co_takes"} for x in d["ung_vien_b"])
    # chọn tay → tạo được
    s, d = _tao(may5, "taovideo", _tv_ts(mt5, du_an_b=ma_du_an(b2), gia=129000))
    assert s == 201 and d["viec"]["tham_so"]["gia"] == 129000
    # wm ngoài danh sách → 400
    assert _tao(may5, "taovideo", _tv_ts(mt5, wm="kenh.khac"))[0] == 400


def test_tao_taovideo_ghi_anh_chup_kho_va_giu_qua_duyet_xin_duyet_lai(may5, mt5, dong):
    """FX-29: POST /viec taovideo ghi ket_qua.kho_luc_tao = anh_chup_kho_taovideo (sau khi chốt du_an_b); khoá còn
    nguyên qua duyệt và xin duyệt lại. Loại khác không có ảnh chụp."""
    import json as _json
    from runner.danh_muc import KHOA_ANH_CHUP_KHO
    f = mt5.repo_kho / "data" / UID / "info.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(_json.dumps({"uid": UID, "da_lam_video": {"xong": True, "poster": [
        {"folder": 7, "so_video": 20, "duong_dan": f"{mt5._p.as_posix()}/output_poster", "nhan": "Adam"},
        {"folder": 8, "so_video": 3, "duong_dan": f"{mt5._b.as_posix()}/output", "nhan": "nha.cua.mit"},
        {"folder": 9, "so_video": 5, "duong_dan": "E:/khac/output", "nhan": "nha.cua.mit"}]}}), encoding="utf-8")
    s, d = _tao(may5, "taovideo", _tv_ts(mt5))
    assert s == 201, d
    id_ = d["viec"]["id"]
    anh = {"a": [[7, 20]], "b": [[8, 3]]}
    v = may5.kho.lay(id_)
    assert v["trang_thai"] == "cho_duyet" and v["ket_qua"] == {KHOA_ANH_CHUP_KHO: anh}
    assert [e["den"] for e in may5.kho.su_kien(id_)][0] == "cho_duyet"
    assert _duyet(may5, dong, id_, loi="Duyệt cả phiên")[0] == 200
    assert may5.kho.lay(id_)["ket_qua"][KHOA_ANH_CHUP_KHO] == anh
    may5.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    may5.kho.chuyen(id_, ["dang_chay"], "loi", "he_thong", loi="phiên sống bị dừng",
                    ket_qua=dict(may5.kho.lay(id_)["ket_qua"], so_codex=2))
    assert may5.goi("POST", f"/viec/{id_}/xin-duyet-lai", {"boi": "nhan"})[0] == 200
    v = may5.kho.lay(id_)
    assert v["trang_thai"] == "cho_duyet" and v["ket_qua"][KHOA_ANH_CHUP_KHO] == anh, v
    # loại không phải taovideo: không ghi ket_qua lúc tạo
    s, d = _tao(may5, "phan_tich_uid")
    assert s == 201 and may5.kho.lay(d["viec"]["id"])["ket_qua"] is None


def test_tao_taovideo_chua_co_info_json_anh_chup_rong(may5, mt5):
    from runner.danh_muc import KHOA_ANH_CHUP_KHO
    s, d = _tao(may5, "taovideo", _tv_ts(mt5))
    assert s == 201, d
    assert may5.kho.lay(d["viec"]["id"])["ket_qua"] == {KHOA_ANH_CHUP_KHO: {"a": [], "b": []}}


def test_tra_loi_taovideo_chon_thieu_mat_khau_403(may5, dong):
    id_ = _taovideo_can_tra_loi(may5, dong, CanNguoiDung("chon", "Tạo lại voice ud3?", ("Đồng ý", "Bỏ qua")))
    s, r = may5.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "Đồng ý", "boi": "nhan", "ma_cau_hoi": MA_CH})
    assert s == 403 and may5.pg.goi == []
    s, r = may5.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "Đồng ý", "boi": "nhan",
                                                     "da_xac_nhan_mat_khau": False, "ma_cau_hoi": MA_CH})
    assert s == 403 and may5.pg.goi == [] and may5.kho.lay(id_)["trang_thai"] == "can_tra_loi"
    s, r = may5.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "Đồng ý", "boi": "nhan",
                                                     "da_xac_nhan_mat_khau": "true"})
    assert s == 400 and may5.pg.goi == []
    s, r = may5.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "Đồng ý", "boi": "comeofage",
                                                     "da_xac_nhan_mat_khau": True, "ma_cau_hoi": MA_CH})
    assert s == 200, r
    assert may5.pg.goi == [(id_, "comeofage", "Đồng ý", MA_CH)]
    assert r["viec"]["trang_thai"] == "dang_chay" and r["viec"]["phien_song"] is True
    assert may5.kho.lay(id_)["so_lan_tieu"] == 0                         # trả lời trong phiên không tiêu lời duyệt


def test_tra_loi_taovideo_cau_hoi_co_co_goi_tra_loi_song(may5, dong):
    id_ = _taovideo_can_tra_loi(may5, dong, CanNguoiDung("cau_hoi", "Giá/deal của sản phẩm?"))
    s, _ = may5.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "159k", "boi": "nhan", "ma_cau_hoi": MA_CH})
    assert s == 403 and may5.pg.goi == []
    s, r = may5.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "Giá 159k\n<<<deal>>> 129k", "boi": "nhan",
                                                     "da_xac_nhan_mat_khau": True, "ma_cau_hoi": MA_CH})
    assert s == 200, r
    assert may5.pg.goi == [(id_, "nhan", "Giá 159k\n‹‹‹deal››› 129k", MA_CH)]


@pytest.mark.parametrize("cau_hoi,tra_loi", [(CanNguoiDung("viec_tay", "Mở app Poster V2"), "da_lam_xong"),
                                             (CanNguoiDung("khong_ro", "?"), "tiep_tuc")])
def test_tra_loi_taovideo_nut_khong_can_mat_khau(may5, dong, cau_hoi, tra_loi):
    id_ = _taovideo_can_tra_loi(may5, dong, cau_hoi)
    s, r = may5.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": tra_loi, "boi": "nhan",
                                                     "da_xac_nhan_mat_khau": False, "ma_cau_hoi": MA_CH})
    assert s == 200 and may5.pg.goi == [(id_, "nhan", tra_loi, MA_CH)]


def test_tra_loi_taovideo_khong_co_phien_409(may5, dong):
    id_ = _taovideo_can_tra_loi(may5, dong, CanNguoiDung("chon", "?", ("A", "B")))
    may5.pg.song.discard(id_)
    s, r = may5.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "A", "boi": "nhan", "da_xac_nhan_mat_khau": True})
    assert (s, r) == (409, {"loi": api.LOI_PHIEN_DA_DONG}) and may5.pg.goi == []
    v = may5.goi("GET", f"/viec/{id_}")[1]["viec"]
    assert v["phien_song"] is False and v["co_the_xin_duyet_lai"] is True
    # BoChay báo hết phiên giữa chừng (KhongCoPhien) / CAS hụt (SaiTrangThai) → 409, không 500
    may5.pg.song.add(id_)
    may5.pg.loi = KhongCoPhien("đã đóng")
    s, r = may5.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "A", "boi": "nhan", "da_xac_nhan_mat_khau": True,
                                                     "ma_cau_hoi": MA_CH})
    assert (s, r) == (409, {"loi": api.LOI_PHIEN_DA_DONG}) and len(may5.pg.goi) == 1
    # SaiTrangThai từ BoChay (CAS hụt hoặc mã lệch vì agent vừa hỏi câu mới, §7.6 bước 1) → 409 "tải lại"
    may5.pg.loi = SaiTrangThai("cas")
    s, r = may5.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "A", "boi": "nhan", "da_xac_nhan_mat_khau": True,
                                                     "ma_cau_hoi": MA_CH})
    assert (s, r) == (409, {"loi": api.LOI_CAU_HOI_DA_DOI}) and len(may5.pg.goi) == 2
    assert may5.kho.lay(id_)["trang_thai"] == "can_tra_loi"


def test_tra_loi_taovideo_khi_runner_chua_noi_tra_loi_song_409(tmp_path, mt5, dong):
    m = May(tmp_path, mt5, dong, co_phien_song=lambda _id: True)        # có cờ nhưng thiếu hàm trả lời
    try:
        s, d = _tao(m, "taovideo", _tv_ts(mt5))
        id_ = d["viec"]["id"]
        assert _duyet(m, dong, id_)[0] == 200
        _vao_can_tra_loi(m, id_, CanNguoiDung("viec_tay", "Mở app"))
        s, r = m.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "da_lam_xong", "boi": "nhan"})
        assert (s, r) == (409, {"loi": api.LOI_PHIEN_DA_DONG})
    finally:
        m.dong_lai()


def test_phien_song_chan_xin_duyet_lai(may5, dong):
    id_ = _taovideo_can_tra_loi(may5, dong, CanNguoiDung("chon", "?", ("A", "B")))
    v = may5.goi("GET", f"/viec/{id_}")[1]["viec"]
    assert v["phien_song"] is True and v["co_the_xin_duyet_lai"] is False
    assert next(x for x in may5.goi("GET", "/viec")[1]["viec"] if x["id"] == id_)["phien_song"] is True
    s, r = may5.goi("POST", f"/viec/{id_}/xin-duyet-lai", {"boi": "nhan"})
    assert s == 409 and "phiên" in r["loi"] and may5.kho.lay(id_)["trang_thai"] == "can_tra_loi"
    may5.pg.song.discard(id_)                                            # phiên đã chết → xin duyệt lại được
    s, r = may5.goi("POST", f"/viec/{id_}/xin-duyet-lai", {"boi": "nhan"})
    assert s == 200 and r["viec"]["trang_thai"] == "cho_duyet"


def test_tra_loi_ton_tien_khac_van_409_va_mien_phi_khong_nhan_chu(may5, mt5, dong):
    _, d = _tao(may5, "muse_clip", {"uid": UID, "du_an": ma_du_an(mt5._p), "mau": ["xoay_360"]})
    mid = d["viec"]["id"]
    mt5._cong[dm.CONG_VIDEO_BATCH] = True
    assert _duyet(may5, dong, mid)[0] == 200
    _vao_can_tra_loi(may5, mid, CanNguoiDung("chon", "Tag?", ("A", "B")))
    may5.pg.song.add(mid)                                               # kể cả cờ phiên lỗi bật: không phải taovideo
    s, r = may5.goi("POST", f"/viec/{mid}/tra-loi", {"tra_loi": "A", "boi": "nhan", "da_xac_nhan_mat_khau": True})
    assert (s, r) == (409, {"loi": LOI_TRA_LOI_TON_TIEN}) and may5.pg.goi == []
    assert may5.goi("GET", f"/viec/{mid}")[1]["viec"]["phien_song"] is False
    # loại miễn phí: câu hỏi chữ tự do không trả lời được (Worker cũng chặn), nút vẫn như cũ
    _, d = _tao(may5)
    pid = d["viec"]["id"]
    _vao_can_tra_loi(may5, pid, CanNguoiDung("cau_hoi", "Giá?"))
    assert may5.goi("POST", f"/viec/{pid}/tra-loi", {"tra_loi": "99k", "boi": "nhan",
                                                     "da_xac_nhan_mat_khau": True})[0] == 400


def test_viec_ra_phien_song_va_co_the_xin_duyet_lai():
    v = {"id": "j1", "loai": "taovideo", "trang_thai": "loi"}
    assert api.viec_ra(v)["phien_song"] is False and api.viec_ra(v)["co_the_xin_duyet_lai"] is True
    assert api.viec_ra(v, phien_song=True)["co_the_xin_duyet_lai"] is False
    assert api.viec_ra(dict(v, trang_thai="cho_duyet"))["co_the_xin_duyet_lai"] is False
    assert api.viec_ra(dict(v, loai="phan_tich_uid"))["co_the_xin_duyet_lai"] is False
    assert api.viec_ra(dict(v, ket_qua={"khong_giet_duoc": True}))["co_the_xin_duyet_lai"] is False


# ================================================================ FX-24 (S-4 #4, §7.6): mã câu hỏi phiên sống

@pytest.mark.parametrize("ma", [None, "", 5, "q0123456789a", "Q0123456789AB", "q0123456789ab\n",
                                "qffffffffffff"])
def test_tra_loi_phien_song_thieu_sai_dang_lech_ma_409(may5, dong, ma):
    """Thiếu / sai dạng / lệch mã câu hỏi đang lưu → 409 "Câu hỏi đã đổi", không gọi tra_loi_song, việc giữ nguyên."""
    id_ = _taovideo_can_tra_loi(may5, dong, CanNguoiDung("viec_tay", "Mở app Poster V2"))
    body = {"tra_loi": "da_lam_xong", "boi": "nhan"}
    if ma is not None:
        body["ma_cau_hoi"] = ma
    s, r = may5.goi("POST", f"/viec/{id_}/tra-loi", body)
    assert (s, r) == (409, {"loi": "Câu hỏi đã đổi — tải lại để xem câu mới"})
    assert api.LOI_CAU_HOI_DA_DOI == r["loi"]
    assert may5.pg.goi == [] and may5.kho.lay(id_)["trang_thai"] == "can_tra_loi"


def test_tra_loi_phien_song_ma_kiem_truoc_gia_tri(may5, dong):
    """Câu hỏi đã đổi thì báo đổi (409), không báo "không khớp lựa chọn" của câu mới (400) hay đòi mật khẩu (403)."""
    id_ = _taovideo_can_tra_loi(may5, dong, CanNguoiDung("chon", "Tạo lại voice ud4?", ("Tạo lại", "Bỏ qua")))
    s, r = may5.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "Đồng ý", "boi": "nhan",
                                                     "ma_cau_hoi": "qaaaaaaaaaaaa"})
    assert (s, r["loi"]) == (409, api.LOI_CAU_HOI_DA_DOI) and may5.pg.goi == []


def test_tra_loi_phien_song_cau_hoi_cu_khong_co_ma_409(may5, dong):
    """Câu hỏi trong DB chưa có mã (vòng chạy cũ) → không có gì để khớp → 409, không gọi tra_loi_song."""
    id_ = _taovideo_can_tra_loi(may5, dong, CanNguoiDung("viec_tay", "Mở app"))
    _sua_db(may5, id_, cau_hoi=json.dumps({"loai": "viec_tay", "noi_dung": "Mở app", "lua_chon": []}))
    assert "ma" not in may5.kho.lay(id_)["cau_hoi"]
    s, r = may5.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "da_lam_xong", "boi": "nhan", "ma_cau_hoi": MA_CH})
    assert (s, r["loi"]) == (409, api.LOI_CAU_HOI_DA_DOI) and may5.pg.goi == []


def test_tra_loi_phien_song_dung_ma_goi_du_4_tham_so_va_get_tra_ma(may5, dong):
    ma = "q" + secrets.token_hex(6)
    id_ = _taovideo_can_tra_loi(may5, dong, CanNguoiDung("chon", "Bản trượt 2 vòng?", ("Giữ", "Bỏ"), ma))
    v = may5.goi("GET", f"/viec/{id_}")[1]["viec"]
    assert v["cau_hoi"]["ma"] == ma                                       # web đọc cau_hoi.ma để gửi lại
    s, r = may5.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "Giữ", "boi": "nhan", "da_xac_nhan_mat_khau": True,
                                                     "ma_cau_hoi": ma})
    assert s == 200, r
    assert may5.pg.goi == [(id_, "nhan", "Giữ", ma)] and r["viec"]["trang_thai"] == "dang_chay"


def test_tra_loi_khong_phai_phien_song_bo_qua_ma(may):
    """Việc miễn phí (không phải phiên sống): ma_cau_hoi sai/thừa bị bỏ qua — hành vi cũ."""
    _, d = _tao(may)
    id_ = d["viec"]["id"]
    _vao_can_tra_loi(may, id_, CanNguoiDung("viec_tay", "Mở Chrome"))
    s, r = may.goi("POST", f"/viec/{id_}/tra-loi", {"tra_loi": "da_lam_xong", "boi": "nhan",
                                                    "ma_cau_hoi": "rác không đúng dạng"})
    assert s == 200 and r["viec"]["trang_thai"] == "cho"


# ================================================================ FX-24 (từ FX-22): kiem_tay chặn chạy tiếp

LOI_KIEM_TAY = ("Bước sua_video thoát mã 5:\n[sua_video] mã 5: Hoàn nguyên bỏ qua render_batch.json vì việc khác "
                "đã đổi — không làm lại, kiểm tay")


def test_co_the_chay_tiep_false_khi_kiem_tay():
    v = {"id": "j1", "loai": "sua_video", "trang_thai": "loi", "loi": LOI_KIEM_TAY}
    assert api.co_the_chay_tiep(v) is False
    ra = api.viec_ra(v)
    assert ra["co_the_chay_tiep"] is False and ra["ket_qua"]["kiem_tay"] is True
    # mã 5 dở dang (không phải bỏ qua có chủ đích) → vẫn chạy tiếp được để bộ chuyển đổi làm nốt
    do_dang = dict(v, loi="Bước sua_video thoát mã 5:\n[sua_video] mã 5: dừng giữa lúc thay file")
    assert api.co_the_chay_tiep(do_dang) is True and api.viec_ra(do_dang)["co_the_chay_tiep"] is True
    ht = dict(v, loai="hoan_tac_sua", loi="Bước hoan_tac_sua thoát mã 5:\n[sua_video] mã 5: Video đã về bản cũ nhưng "
                                         "hoàn tác bỏ qua phụ đề (việc khác đã đổi) — kiểm tay")
    assert api.co_the_chay_tiep(ht) is False
    # ket_qua đã lưu sẵn kiem_tay (dù loi không suy ra được) cũng chặn
    assert api.co_the_chay_tiep(dict(v, loi="x", ket_qua={"kiem_tay": True})) is False


def test_chay_tiep_sua_video_kiem_tay_409_kem_thong_diep(ms):
    s, d = _luu(ms, phu_de=[])
    id_ = d["viec"]["id"]
    ms.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    ms.kho.chuyen(id_, ["dang_chay"], "loi", "he_thong", loi=LOI_KIEM_TAY)
    v = ms.goi("GET", f"/viec/{id_}")[1]["viec"]
    assert v["co_the_chay_tiep"] is False and v["ket_qua"]["kiem_tay"] is True
    assert [x for x in ms.goi("GET", "/viec")[1]["viec"] if x["id"] == id_][0]["co_the_chay_tiep"] is False
    s, r = ms.goi("POST", f"/viec/{id_}/chay-tiep", {"boi": "nhan"})
    assert s == 409 and r["loi"] == v["ket_qua"]["thong_diep"] and r["kiem_tay"] is True
    assert "Chạy tiếp không giúp được" in r["loi"]
    assert ms.kho.lay(id_)["trang_thai"] == "loi"


# ---------- nhan-tin: chỉ đạo việc phiên sống ----------

def _taovideo_dang_chay(may, dong):
    s, d = _tao(may, "taovideo", _tv_ts(may.mt))
    assert s == 201, d
    id_ = d["viec"]["id"]
    assert _duyet(may, dong, id_, loi="Duyệt cả phiên")[0] == 200
    may.kho.chuyen(id_, ["cho"], "dang_chay", "he_thong")
    may.pg.song.add(id_)
    return id_


def test_nhan_tin_can_mat_khau_va_kiem_body(may5, dong):
    id_ = _taovideo_dang_chay(may5, dong)
    url = f"/viec/{id_}/nhan-tin"
    assert may5.goi("POST", url, {"noi_dung": "Không nói giá", "boi": "nhan"})[0] == 403
    for sai in ({"noi_dung": "", "da_xac_nhan_mat_khau": True}, {"noi_dung": " \n ", "da_xac_nhan_mat_khau": True},
                {"noi_dung": "x" * 1001, "da_xac_nhan_mat_khau": True},
                {"noi_dung": "a\tb", "da_xac_nhan_mat_khau": True},
                {"noi_dung": "ok", "ngat": "true", "da_xac_nhan_mat_khau": True},
                {"noi_dung": "ok", "da_xac_nhan_mat_khau": "true"}, {"noi_dung": 5, "da_xac_nhan_mat_khau": True}):
        assert may5.goi("POST", url, dict(sai, boi="nhan"))[0] == 400, sai
    assert may5.pg.goi == []
    s, r = may5.goi("POST", url, {"noi_dung": "Không nói giá\n<<<x>>>", "boi": "comeofage",
                                  "da_xac_nhan_mat_khau": True})
    assert s == 200 and r["viec"]["phien_song"] is True, r
    s, r = may5.goi("POST", url, {"noi_dung": "Ngắt đi", "ngat": True, "boi": "nhan", "da_xac_nhan_mat_khau": True})
    assert s == 200
    assert may5.pg.goi == [(id_, "comeofage", "Không nói giá\n‹‹‹x›››", False), (id_, "nhan", "Ngắt đi", True)]


def test_nhan_tin_409_khong_phien_dang_hoi_va_loai_khac(may5, dong):
    id_ = _taovideo_dang_chay(may5, dong)
    body = {"noi_dung": "Không nói giá", "boi": "nhan", "da_xac_nhan_mat_khau": True}
    may5.pg.song.discard(id_)
    assert may5.goi("POST", f"/viec/{id_}/nhan-tin", body) == (409, {"loi": api.LOI_PHIEN_DA_DONG})
    may5.pg.song.add(id_)
    may5.pg.loi = KhongCoPhien("đóng")
    assert may5.goi("POST", f"/viec/{id_}/nhan-tin", body) == (409, {"loi": api.LOI_PHIEN_DA_DONG})
    may5.pg.loi = SaiTrangThai("cas")
    assert may5.goi("POST", f"/viec/{id_}/nhan-tin", body)[0] == 409
    may5.pg.loi = None
    may5.pg.goi.clear()
    may5.kho.chuyen(id_, ["dang_chay"], "huy", "nhan")
    id2 = _taovideo_can_tra_loi(may5, dong, CanNguoiDung("chon", "?", ("A", "B")))
    assert may5.goi("POST", f"/viec/{id2}/nhan-tin", body) == (409, {"loi": api.LOI_CHI_DAO_DANG_HOI})
    assert may5.goi("POST", f"/viec/{id2}/nhan-tin", dict(body, ngat=True))[0] == 200     # ngắt được khi đang hỏi
    s, d = _tao(may5, "phan_tich_uid")
    assert may5.goi("POST", f"/viec/{d['viec']['id']}/nhan-tin", body)[0] == 409
    assert may5.pg.goi == [(id2, "nhan", "Không nói giá", True)]


def test_nhan_tin_viec_loi_hoac_cho_duyet_chi_luu_cho_lan_chay_tiep(may5, dong):
    from runner.phieu import CAU_CHI_DAO
    id_ = _taovideo_dang_chay(may5, dong)
    may5.pg.song.discard(id_)
    kt = "2026-11-17T09:00:00+07:00"
    may5.kho.chuyen(id_, ["dang_chay"], "loi", "he_thong", loi="Phiên Claude tự thoát", ket_thuc_luc=kt)
    body = {"noi_dung": "Kịch bản không được nói giá", "boi": "nhan", "da_xac_nhan_mat_khau": True}
    assert may5.goi("POST", f"/viec/{id_}/nhan-tin", dict(body, da_xac_nhan_mat_khau=False))[0] == 403
    s, r = may5.goi("POST", f"/viec/{id_}/nhan-tin", body)
    assert s == 200 and r["luu_cho_lan_sau"] is True and r["viec"]["trang_thai"] == "loi", r
    v = may5.kho.lay(id_)
    assert v["ket_thuc_luc"] == kt and v["loi"] == "Phiên Claude tự thoát"
    assert [(t["cau_hoi"], t["noi_dung"]) for t in may5.kho.tra_loi_cua(id_)] == [(CAU_CHI_DAO, body["noi_dung"])]
    assert may5.pg.goi == []
    assert may5.goi("POST", f"/viec/{id_}/xin-duyet-lai", {"boi": "nhan"})[0] == 200
    assert may5.goi("POST", f"/viec/{id_}/nhan-tin", dict(body, noi_dung="Thêm: giữ giọng Adam"))[0] == 200
    assert len(may5.kho.tra_loi_cua(id_)) == 2 and may5.kho.lay(id_)["trang_thai"] == "cho_duyet"
    may5.kho.chuyen(id_, ["cho_duyet"], "huy", "nhan")
    assert may5.goi("POST", f"/viec/{id_}/nhan-tin", body) == (409, {"loi": api.LOI_PHIEN_DA_DONG})
