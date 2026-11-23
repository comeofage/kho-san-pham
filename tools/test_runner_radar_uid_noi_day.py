"""Test nối đầu-cuối Radar UID bằng máy chủ EchoTik GIẢ (docs/radar-uid.md RU-A3; §2.5, §6, §7, §7.1).

Chạy: PYTHONIOENCODING=utf-8 python -B -m pytest tools/test_runner_radar_uid_noi_day.py -q -p no:cacheprovider

Chuỗi nối thật, mọi file ở tmp_path, KHO_RUNNER_DIR tạm:
  POST /radar/goc (API ký như Worker, tạo nhóm + việc radar_uid_nap)
    → argv do danh_muc.lap_buoc_hieu_luc dựng (đúng thứ chạy thật)
    → runner.radar_uid.chay(argv) với client EchoTik THẬT trỏ về http.server giả 127.0.0.1:<cổng ngẫu nhiên>
    → radar_uid.db thật (KhoRadarUid) → kiem_dau_ra của danh_muc → GET /radar/bang qua tao_handler.

Cách tiêm host giả: echotik.GOC hardcode https://echotik.live nhưng EchoTik nhận `mo_url` (mặc định urlopen): factory
của test truyền một `mo_url` đổi host sang máy chủ giả (và CHẶN mọi URL không bắt đầu bằng GOC) — không sửa file nguồn.
Token là GIẢ ghi ở file tạm; KHÔNG đụng E:\\timsanpham\\.echotik_token.json, E:\\kho-runner, echotik.live thật.
"""
import io
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import threading
import urllib.request
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

TOOLS = Path(__file__).parent
sys.path.insert(0, str(TOOLS))
from runner import danh_muc as dm  # noqa: E402
from runner import echotik as et  # noqa: E402
from runner import radar_uid  # noqa: E402
from runner.kho_radar_uid import KhoRadarUid  # noqa: E402
from runner.kieu import MoiTruong  # noqa: E402
from test_runner_api import Dong, May  # noqa: E402

TOKEN = "FAKE-TOKEN-zz9f3a7c1d-khong-duoc-ro-ri"
USER_ID = "FAKE-USER-777"
GOC = "1729420930611055346"                      # id 19 số (E1 mẫu §2.5)
TEN_GOC = "[HOT] Kẹp tóc càng cua mini 8cm freeship"
MAU_SAC = ("xanh", "đỏ", "vàng", "tím", "hồng", "đen", "trắng", "nâu", "cam", "bạc")
SO_VIDEO = 39
NGAY0 = datetime(2026, 11, 20, 10, 0, 0)         # ngày nạp; hang-ngay ở NGAY0+1, +2, +3 ngày, cùng 10:00 (Δt = 24 giờ)
SO_HOT = {1: 12, 2: 12, 3: 12, 4: 12, 5: 12, 6: 12, 7: 12, 8: 12, 9: 0, 10: 2}   # k → số video tăng view mỗi ngày
CONG_DON = {0: 0, 1: 1, 2: 4, 3: 7}              # view tăng tích luỹ theo vòng: kỳ 1 ×1, kỳ 2 ×3, kỳ 3 ×3
SALE_CNT = ("10.17K", "10.20K", "10.25K", "10.31K")
KEYWORD_MONG_DOI = ["kẹp tóc càng cua", "kẹp tóc càng", "kẹp tóc"]


def uid_tt(k: int) -> str:
    """UID tương tự thứ k (1..10), 19 chữ số."""
    return f"17294209306120{k:05d}"


UID_TT = [uid_tt(k) for k in range(1, 11)]


# ====================================================================================== máy chủ EchoTik giả
class GiaEchoTik:
    """http.server giả: E1 /products/{pid}, E2 /products/{pid}/videos, E4 /products?keyword=... dạng §2.5."""

    RE_E1 = re.compile(r"^/api/v1/data/products/(\d{19})$")
    RE_E2 = re.compile(r"^/api/v1/data/products/(\d{19})/videos$")

    def __init__(self) -> None:
        self.vong = 0                              # 0 = ngày nạp, 1.. = hang-ngay; test đặt trước mỗi lượt chạy
        self.nhat_ky: list[dict] = []
        self._khoa = threading.Lock()
        self._dem_update = 0
        gia = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                gia._phuc_vu(self)

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.cong = self.srv.server_address[1]
        self.t = threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.t.start()

    def url(self) -> str:
        return f"http://127.0.0.1:{self.cong}"

    def dong(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()
        self.t.join(timeout=10)

    # --- dữ liệu
    def _so_hot(self, pid: str) -> int | None:
        if pid == GOC:
            return 12
        for k in range(1, 11):
            if pid == uid_tt(k):
                return SO_HOT[k]
        return None

    def _ten(self, pid: str) -> str:
        return TEN_GOC if pid == GOC else f"Kẹp tóc càng cua {MAU_SAC[UID_TT.index(pid)]}"

    def _e1(self, pid: str) -> dict:
        return {"data": {"product_id": pid, "product_name": self._ten(pid), "price": "$19.37", "real_price": "499.390₫",
                         "sale_cnt": SALE_CNT[self.vong], "commission": "10%", "total_stock_cnt": 562,
                         "update_time": f"2026-11-{20 + self.vong} 07:55", "seller": {"seller_name": "Shop Giả"}}}

    def _e2(self, pid: str) -> dict:
        hot = self._so_hot(pid)
        moi_nhat = datetime(2026, 7, 18, 10, 0, 0)
        ds = []
        for i in range(SO_VIDEO):
            if i < hot:
                view: object = 5000 + 10 * i + 100 * (i + 1) * CONG_DON[self.vong]      # int, đổi mỗi vòng
            elif i == 13:
                view = "21.81K"                                                          # chuỗi rút gọn, đứng yên
            elif i == 27:
                view = "9.4K"
            elif i == 20:
                view = 326                                                               # số nguyên, đứng yên
            else:
                view = 700 + i
            with self._khoa:
                self._dem_update += 1
                gio_goi = f"2026-11-{20 + self.vong} 10:{self._dem_update // 60 % 60:02d}:{self._dem_update % 60:02d}"
            ds.append({"video_id": f"73{pid[-6:]}{i:09d}", "views_count": view,
                       "publish_time": (moi_nhat - timedelta(days=11 * i)).strftime("%Y-%m-%d %H:%M:%S"),
                       "update_time": gio_goi,                                          # luôn đổi mỗi lần gọi (§2.3.2)
                       "influencer": {"unique_id": f"cr{i % 6}", "follower_count": f"{1.2 + i * 0.1:.2f}K"},
                       "is_promote": i == 20})                                          # đúng 1/39
        return {"data": ds, "meta": {"current_page": 1, "from": 1, "last_page": 1, "links": []}}

    def _e4(self) -> dict:                         # 10 phần tử, KHÔNG có meta (§2.5)
        return {"data": [{"product_id": uid_tt(k), "product_name": self._ten(uid_tt(k)), "avg_price": f"$12.{k}",
                          "total_sale_7d_cnt": str(200 - k * 7)} for k in range(1, 11)]}

    # --- phục vụ
    def _tra(self, h: BaseHTTPRequestHandler, ma: int, noi: dict | None) -> None:
        body = b"{}" if noi is None else json.dumps(noi, ensure_ascii=False).encode("utf-8")
        h.send_response(ma)
        h.send_header("Content-Type", "application/json; charset=utf-8")
        h.send_header("Content-Length", str(len(body)))
        h.end_headers()
        h.wfile.write(body)

    def _phuc_vu(self, h: BaseHTTPRequestHandler) -> None:
        u = urlsplit(h.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        hdr = {k.lower(): v for k, v in h.headers.items()}
        m1, m2 = self.RE_E1.match(u.path), self.RE_E2.match(u.path)
        if m2:
            loai, pid = "E2", m2.group(1)
        elif m1:
            loai, pid = "E1", m1.group(1)
        elif u.path == "/api/v1/data/products":
            loai, pid = "E4", ""
        else:
            loai, pid = "LA", ""
        with self._khoa:
            self.nhat_ky.append({"loai": loai, "pid": pid, "q": q, "h": hdr, "vong": self.vong})
        if hdr.get("authorization") != f"Bearer {TOKEN}":
            return self._tra(h, 401, None)
        if loai == "E4":
            return self._tra(h, 200, self._e4())
        if loai in ("E1", "E2") and self._so_hot(pid) is None:
            return self._tra(h, 404, None)
        if loai == "E1":
            return self._tra(h, 200, self._e1(pid))
        if loai == "E2":
            if q.get("page", "1") != "1":          # last_page=1: trang 2 rỗng (§2.3.5)
                return self._tra(h, 200, {"data": [], "meta": {"current_page": 2, "from": None, "last_page": 1, "links": []}})
            return self._tra(h, 200, self._e2(pid))
        return self._tra(h, 404, None)


# ====================================================================================== khung chạy nối
class _GhiLog(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.dong: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.dong.append(record.getMessage())


@dataclass
class KetQua:
    ma: int
    kq: dict
    out: str
    err: str
    logs: list[str]
    get: Counter
    viec_id: str
    argv: list[str]
    dau_ra: str
    nhat_ky: list[dict] = field(default_factory=list)


class NoiDay:
    def __init__(self, tmp: Path, gia: GiaEchoTik) -> None:
        self.tmp = tmp
        self.gia = gia
        self.du_lieu = tmp / "du_lieu"
        self.token_file = tmp / "token_gia" / "echotik_token.json"
        self.token_file.parent.mkdir(parents=True)
        self.token_file.write_text(json.dumps({"token": TOKEN, "user_id": USER_ID, "email": "gia@example.invalid",
                                               "updated_at": "2026-11-20"}), encoding="utf-8")
        self.dong = Dong(NGAY0)
        for d in ("goc", "repo", "scripts", "radar", "sp"):
            (tmp / d).mkdir(exist_ok=True)
        self.mt = MoiTruong(
            gocs=[tmp / "goc"], repo_kho=tmp / "repo", thu_muc_scripts=tmp / "scripts",
            python_poster=tmp / "poster" / "python.exe", claude_exe=tmp / "claude.exe", agy_exe=tmp / "agy.exe",
            thu_muc_radar=tmp / "radar", thu_muc_sp=tmp / "sp", thu_muc_du_lieu=self.du_lieu,
            cong_song=lambda c: True, chan_doan_kho=lambda r: None, ffmpeg_ngoai=lambda: False,
            thoi_luong_media=lambda f: 3.0, bay_gio=self.dong, echotik_token_file=self.token_file)
        self.db = self.du_lieu / "radar_uid.db"
        kr = KhoRadarUid(self.db, self.dong)
        kr.mo()
        kr.dong()
        self.kr = KhoRadarUid(self.db, self.dong)                 # bản của handler (kết nối theo luồng, đóng mỗi request)
        self.may = May(tmp, self.mt, self.dong, kho_radar=self.kr)
        self.mo_url = self._mo_url_ve_gia()

    def dong_lai(self) -> None:
        self.may.dong_lai()

    # --- tiêm host giả
    def _mo_url_ve_gia(self):
        co_so = self.gia.url()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # không đi qua proxy hệ thống

        def mo(req, timeout):
            url = req.full_url
            assert url.startswith(et.GOC + "/"), f"URL ngoài echotik.live: {url}"   # chặn mọi đường thoát ra mạng
            moi = urllib.request.Request(co_so + url[len(et.GOC):], headers=dict(req.header_items()), method="GET")
            return opener.open(moi, timeout=timeout)
        return mo

    def factory(self, token_file, tinh_goi=None):
        return et.EchoTik(token_file, mo_url=self.mo_url, ngu=lambda s: None, cach_toi_thieu_s=0, tinh_goi=tinh_goi)

    # --- một lượt
    def _dat_ngay(self, k: int) -> None:
        self.dong.luc = NGAY0 + timedelta(days=k)
        self.gia.vong = k

    def _chay_viec(self, viec_id: str, tran: int | None = None) -> KetQua:
        v = self.may.kho.lay(viec_id)
        loai = dm.DANH_MUC[v["loai"]]
        buoc = dm.lap_buoc_hieu_luc(loai, v["tham_so"], v, self.mt, self.may.hm)[0]
        assert buoc.argv[:4] == [dm.PYTHON, "-B", "-m", "runner.radar_uid"], buoc.argv
        assert Path(buoc.cwd).resolve() == TOOLS.resolve()
        argv = list(buoc.argv)
        assert TOKEN not in " ".join(argv)                                              # token không vào argv
        if tran is not None:
            argv[argv.index("--tran-goi") + 1] = str(tran)
        truoc = len(self.gia.nhat_ky)
        out, err, ghi = io.StringIO(), io.StringIO(), _GhiLog()
        goc_log = logging.getLogger()
        muc_cu = goc_log.level
        goc_log.addHandler(ghi)
        goc_log.setLevel(logging.DEBUG)
        try:
            with redirect_stdout(out), redirect_stderr(err):
                ma = radar_uid.chay(argv[4:], echotik_factory=self.factory, bay_gio=self.dong)
        finally:
            goc_log.removeHandler(ghi)
            goc_log.setLevel(muc_cu)
        dong_out = out.getvalue()
        assert dong_out.endswith("\n") and dong_out.count("\n") == 1, repr(dong_out)    # đúng 1 dòng
        assert dong_out.isascii()
        moi = self.gia.nhat_ky[truoc:]
        dau_ra = dm.kiem_dau_ra_an_toan(loai, v["tham_so"], v, self.mt)
        self.may.kho.chuyen(viec_id, ["cho"], "xong", "he_thong")                       # đóng việc như vòng chạy
        return KetQua(ma, json.loads(dong_out), dong_out, err.getvalue(), ghi.dong,
                      Counter(x["loai"] for x in moi), viec_id, argv, dau_ra, moi)

    def nap(self) -> KetQua:
        self._dat_ngay(0)
        s, d = self.may.goi("POST", "/radar/goc", {"boi": "nhan", "uid": GOC})
        assert s == 202 and d["da_co"] is False and d["goc"] == GOC and isinstance(d["viec_id"], str), (s, d)
        return self._chay_viec(d["viec_id"])

    def hang_ngay(self, k: int, tran: int | None = None) -> KetQua:
        self._dat_ngay(k)
        s, d = self.may.goi("POST", "/radar/chup-lai", {"boi": "nhan"})
        assert s == 202 and isinstance(d["viec_id"], str), (s, d)
        return self._chay_viec(d["viec_id"], tran)

    def bang(self) -> dict:
        s, d = self.may.goi("GET", "/radar/bang")
        assert s == 200, (s, d)
        return d

    def tat_ca_file_khong_co_token(self) -> None:
        for p in self.tmp.rglob("*"):
            if p.is_file() and p != self.token_file:
                assert TOKEN.encode() not in p.read_bytes(), f"token rò rỉ vào {p}"


# ====================================================================================== fixture
@pytest.fixture(autouse=True)
def _du_lieu_tam(tmp_path, monkeypatch):
    monkeypatch.setenv("KHO_RUNNER_DIR", str(tmp_path / "du_lieu"))
    monkeypatch.delenv("KHO_ECHOTIK_TOKEN_FILE", raising=False)


@pytest.fixture
def gia():
    g = GiaEchoTik()
    yield g
    g.dong()


@pytest.fixture
def nd(tmp_path, gia):
    n = NoiDay(tmp_path, gia)
    yield n
    n.dong_lai()


@pytest.fixture
def sau_nap(nd):
    nd.kq_nap = nd.nap()
    return nd


@pytest.fixture
def sau_3_ngay(sau_nap):
    sau_nap.kq_hang = [sau_nap.hang_ngay(1), sau_nap.hang_ngay(2)]
    return sau_nap


def _nhom(bang: dict) -> dict:
    assert len(bang["nhom"]) == 1
    return bang["nhom"][0]


def _uid_ra(bang: dict, uid: str) -> dict:
    return next(u for u in _nhom(bang)["ds"] if u["uid"] == uid)


# ====================================================================================== nạp
def test_nap_dung_ngan_sach_va_ghi_nhom(sau_nap):
    nd, kq = sau_nap, sau_nap.kq_nap
    assert kq.ma == 0 and kq.kq == {"trang_thai": "xong", "ly_do": "", "so_uid": 11, "so_goi": 25}, kq.kq
    # ngân sách = 2×N + GET tìm: E1 gốc dùng lại cho chụp gốc ⇒ E1×11, E2×11, E4×3 = 25
    assert kq.get == Counter({"E1": 11, "E2": 11, "E4": 3}), kq.get
    assert nd.kr.goi_hom_nay("2026-11-20") == 25
    assert kq.dau_ra == "xong"                                    # danh_muc.kiem_dau_ra đọc lan_chay của script thật
    e4 = [x for x in kq.nhat_ky if x["loai"] == "E4"]
    assert [x["q"]["keyword"] for x in e4] == KEYWORD_MONG_DOI
    for x in e4:
        assert (x["q"]["page"], x["q"]["per_page"], x["q"]["order"], x["q"]["sort"], x["q"]["dateRange"]) == \
               ("1", "50", "total_sale_7d_cnt", "desc", "7")
    for x in (y for y in kq.nhat_ky if y["loai"] == "E2"):
        assert (x["q"]["page"], x["q"]["per_page"], x["q"]["order"], x["q"]["sort"]) == ("1", "50", "publish_time", "desc")
    for x in kq.nhat_ky:                                           # header đúng §2.1, token đọc từ file tạm
        assert x["h"]["authorization"] == f"Bearer {TOKEN}" and x["h"]["x-region"] == "VN"
        assert x["h"]["token"] == TOKEN and x["h"]["x-user-id"] == USER_ID
        assert "region" not in x["q"]
    assert not any("echotik.live" in x["h"].get("host", "") for x in kq.nhat_ky)


def test_nap_db_nhom_da_tim_gom_goc_va_10_tuong_tu(sau_nap):
    nd = sau_nap
    assert str(nd.db.resolve()).startswith(str(nd.tmp.resolve()))
    assert not str(nd.db).lower().startswith("e:\\kho-runner")
    nh = nd.kr.ds_nhom()
    assert [(n["goc"], n["trang_thai"], n["ly_do"]) for n in nh] == [(GOC, "da_tim", "")]
    lk = nd.kr.uid_cua_nhom(GOC)
    assert [x["uid"] for x in lk if x["vai"] == "goc"] == [GOC]
    assert sorted(x["uid"] for x in lk if x["vai"] == "tuong_tu") == sorted(UID_TT)
    assert all(x["trang_thai"] == "dang_theo" and x["do_giong"] == pytest.approx(0.6667, abs=1e-4) for x in lk
               if x["vai"] == "tuong_tu")
    snaps = nd.kr.doc_snapshots(GOC, "2026-11-01")
    assert len(snaps) == 1
    s = snaps[0]
    assert (s["so_trang"], s["tong_trang"], len(s["videos"])) == (1, 1, SO_VIDEO)
    views = {v["view"] for v in s["videos"].values()}
    assert {"326", "21.81K"} <= views                              # số nguyên và chuỗi rút gọn lưu nguyên văn
    assert sum(1 for v in s["videos"].values() if v["is_promote"]) == 1
    assert s["echotik_cap_nhat"] == "2026-11-20 07:55" and s["ban_tong"] == "10.17K"
    assert (s["gia"], s["hoa_hong"], s["ton"]) == ("499.390₫", "10%", "562")
    assert nd.kr.doc_token()["trang_thai"] == "ok"


def test_bang_sau_nap_1_snapshot_chua_du_bang_chung(sau_nap):
    b = sau_nap.bang()
    n = _nhom(b)
    assert (n["goc"], n["trang_thai"]) == (GOC, "da_tim") and len(n["ds"]) == 11
    g = _uid_ra(b, GOC)
    assert g["xep_loai"] == "chua_du" and g["tam"] is False
    assert g["so_snapshot"] == 1 and g["trung_vi"] is None and g["tang_toc"] is None
    assert "so_snapshot 1/4" in g["ly_do_thieu"] and g["co"] == ["THIEU_MAU"]
    assert b["han_muc"]["goi_hom_nay"] == 25 and b["lan"]["trang_thai"] == "xong"


# ====================================================================================== hang-ngay
def test_hang_ngay_moi_lan_22_get_dung_ngan_sach_va_doi_view(sau_3_ngay):
    nd = sau_3_ngay
    for k, kq in zip((1, 2), nd.kq_hang):
        assert kq.ma == 0 and kq.kq == {"trang_thai": "xong", "ly_do": "", "so_uid": 11, "so_goi": 22}, kq.kq
        assert kq.get == Counter({"E1": 11, "E2": 11}), kq.get      # hang-ngay không gọi E4
        assert nd.kr.goi_hom_nay(f"2026-11-{20 + k}") == 22
        assert kq.dau_ra == "xong"
        assert not any(x["loai"] == "E2" and x["q"]["page"] != "1" for x in kq.nhat_ky)    # last_page=1: không trang 2
    # update_time video luôn đổi giữa các lần gọi nhưng không vào DB/tính toán
    cot = {r[1] for r in sqlite3.connect(nd.db).execute("PRAGMA table_info(chup_video)")}
    assert "update_time" not in cot
    # tìm tương tự chỉ chạy ở nạp: nhóm giữ nguyên 10 tương tự
    assert len([x for x in nd.kr.uid_cua_nhom(GOC) if x["vai"] == "tuong_tu"]) == 10


def test_hang_ngay_chay_lai_cung_viec_va_viec_moi_trong_ngay_khong_goi_them(sau_3_ngay):
    nd = sau_3_ngay
    truoc = len(nd.gia.nhat_ky)
    # cùng viec_id: bat_dau_lan trả False ⇒ báo lại kết quả cũ, không gọi mạng
    kq0 = nd.kq_hang[1]
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        ma = radar_uid.chay(kq0.argv[4:], echotik_factory=nd.factory, bay_gio=nd.dong)
    assert ma == 0 and json.loads(out.getvalue())["trang_thai"] == "xong" and len(nd.gia.nhat_ky) == truoc
    # viec mới cùng ngày (nút "Chụp lại"): mọi UID đã ok ⇒ 0 GET
    kq = nd.hang_ngay(2)
    assert kq.ma == 0 and kq.kq["trang_thai"] == "xong" and kq.kq["so_goi"] == 0 and sum(kq.get.values()) == 0
    assert nd.kr.goi_hom_nay("2026-11-22") == 22


def test_het_ngan_sach_giua_chung_roi_chup_tiep_phan_con_lai(sau_nap):
    nd = sau_nap
    kq = nd.hang_ngay(1, tran=5)                                   # 2 UID (4 GET); UID thứ 3 cần 2 ⇒ 6 > 5 ⇒ dừng
    assert kq.ma == 0 and kq.kq["trang_thai"] == "tu_dung" and kq.kq["ly_do"] == "het_han_muc_goi"
    assert kq.kq["so_goi"] == 4 and sum(kq.get.values()) == 4 and kq.dau_ra == "xong"
    b = nd.bang()
    assert b["lan"]["trang_thai"] == "tu_dung" and b["lan"]["ly_do"] == "het_han_muc_goi"
    assert b["lan"]["ten_ly_do"] == "Hết ngân sách gọi EchoTik hôm nay (4/60)."
    ok = {r[0] for r in sqlite3.connect(nd.db).execute("SELECT uid FROM chup_uid WHERE ngay='2026-11-21' AND trang_thai='ok'")}
    dang_do = sqlite3.connect(nd.db).execute("SELECT COUNT(*) FROM chup_uid WHERE trang_thai='dang_chup'").fetchone()[0]
    assert len(ok) == 2 and dang_do == 0                           # không để UID dở dang
    kq2 = nd.hang_ngay(1)                                          # lượt mới cùng ngày: chụp 9 UID còn lại
    assert kq2.kq["trang_thai"] == "xong" and kq2.kq["so_goi"] == 18 and sum(kq2.get.values()) == 18
    assert nd.kr.goi_hom_nay("2026-11-21") == 22


# ====================================================================================== GET /radar/bang
def test_bang_3_snapshot_chua_du_bang_chung_so_lieu_dung(sau_3_ngay):
    nd = sau_3_ngay
    nd.dong.luc = NGAY0 + timedelta(days=2, minutes=12)
    b = nd.bang()
    assert set(b) == {"luc", "ngay", "token", "han_muc", "lan", "nhom"}
    assert b["ngay"] == "2026-11-22" and b["luc"] == "2026-11-22T10:12:00+07:00"
    assert b["token"] == {"trang_thai": "ok", "cau": ""}
    assert b["han_muc"] == {"bat": 1, "goi_ngay_toi_da": 60, "goi_hom_nay": 22, "goc_toi_da": 2}
    assert b["lan"]["trang_thai"] == "xong" and b["lan"]["ngay"] == "2026-11-22"
    n = _nhom(b)
    assert n["goc"] == GOC and isinstance(n["goc"], str) and n["trang_thai"] == "da_tim" and n["bat_dau_ngay"] == "2026-11-20"
    assert len(n["ds"]) == 11
    for u in n["ds"]:                                               # id luôn là chuỗi 19 số
        assert isinstance(u["uid"], str) and re.fullmatch(r"\d{19}", u["uid"])
    assert {u["uid"] for u in n["ds"]} == {GOC, *UID_TT}
    assert n["ds"][0]["uid"] == GOC and n["ds"][0]["vai"] == "goc"

    g = _uid_ra(b, GOC)
    # kỳ 1: 12 video tăng 100..1200 ⇒ trung vị 650, top5 = 1200+1100+1000+900+800 = 5000; kỳ 2 ×3 ⇒ 1950, 15000
    assert (g["trung_vi_truoc"], g["trung_vi"]) == (650, 1950)
    assert (g["tong_delta_top5_truoc"], g["tong_delta_top5"]) == (5000, 15000)
    assert g["tang_toc"] == 3.0 and g["tang_dot_ngot"] is True and g["ly_do_tang_toc"] == ""
    assert (g["n_video"], g["n_creator"], g["n_doi"]) == (12, 6, 12)
    assert g["ti_le_doi"] == 30.8                                   # 12/39: update_time video đổi 39/39 mà KHÔNG bị tính là đổi
    assert g["spark"] == [650, 1950]
    # chưa đủ bằng chứng: 3/4 snapshot, phủ 48/70 giờ, số tạm hiện (tam)
    assert g["so_snapshot"] == 3 and g["phu_gio"] == 48.0
    assert g["xep_loai"] == "chua_du" and g["tam"] is True and g["co"] == ["THIEU_MAU"]
    assert "so_snapshot 3/4" in g["ly_do_thieu"] and "phu_gio 48.0/70" in g["ly_do_thieu"]
    assert (g["promote_x"], g["promote_y"]) == (1, 39)
    assert g["duoi_do_phan_giai"] == 0
    assert g["d_ban_ngay"] == 50.0                                  # '10.20K' → '10.25K' trong 24 giờ
    assert g["creator_moi_ngay"] == 0.0
    assert g["view_nho_trung_vi"] is None and g["cau_view_nho"]     # không có video ≤ 14 ngày: có lý do kèm
    assert g["n_video_moi_30"] == 0 and g["cau_video_moi"]
    assert (g["gia"], g["hoa_hong"], g["ton"]) == ("499.390₫", "10%", "562")
    assert g["du_lieu_luc"] == "2026-11-22T10:00:00+07:00" and g["echotik_cap_nhat"] == "2026-11-22 07:55"
    assert g["ten"] == TEN_GOC and g["shop"] == "Shop Giả"
    assert "MOT_CREATOR_CHI_PHOI" not in g["co_canh_bao"] and "NGHI_ADS" not in g["co_canh_bao"]
    # last_page=1 ⇒ KHÔNG được bật MAU_TOP_VIDEO (nếu đỏ ở đây: lỗi đã biết của radar_uid_tinh._mau_top_video, chờ RU-B5)
    assert "MAU_TOP_VIDEO" not in g["co_canh_bao"], g["co_canh_bao"]

    # UID đứng yên (0 video đổi view) ⇒ KHONG_LAM_MOI ⇒ chặn, số trống kèm lý do; xếp cuối
    dung_yen = _uid_ra(b, uid_tt(9))
    assert dung_yen["xep_loai"] == "chan" and "KHONG_LAM_MOI" in dung_yen["co"]
    assert dung_yen["trung_vi"] is None and dung_yen["n_doi"] == 0 and dung_yen["ti_le_doi"] == 0.0
    assert n["ds"][-1]["uid"] == uid_tt(9)
    it = _uid_ra(b, uid_tt(10))                                    # chỉ 2 video đổi: chưa đủ mẫu
    assert it["xep_loai"] == "chua_du" and it["n_video"] == 2
    # §5.4: dang_co_da → chua_co_da → chua_du → chan; trong lớp theo trung_vi giảm rồi uid
    assert [u["uid"] for u in n["ds"]] == [GOC, *UID_TT[:8], uid_tt(10), uid_tt(9)]
    assert all(_uid_ra(b, uid_tt(k))["xep_loai"] == "chua_du" for k in range(1, 9))

    for u in n["ds"]:                                               # đủ khoá UidRa §7.1
        assert {"uid", "vai", "trang_thai", "ten", "shop", "do_giong", "xep_loai", "uu_tien", "tam", "trung_vi",
                "tong_delta_top5", "tang_toc", "so_snapshot", "phu_gio", "co", "co_canh_bao", "ly_do_thieu"} <= set(u)
    tt = [u for u in n["ds"] if u["vai"] == "tuong_tu"]
    assert len(tt) == 10 and all(u["do_giong"] == pytest.approx(0.6667, abs=1e-4) for u in tt)


def test_bang_4_snapshot_du_cong_snapshot_va_phu_gio(sau_3_ngay):
    nd = sau_3_ngay
    kq = nd.hang_ngay(3)
    assert kq.kq["so_goi"] == 22 and kq.kq["trang_thai"] == "xong"
    nd.dong.luc = NGAY0 + timedelta(days=3, minutes=12)
    g = _uid_ra(nd.bang(), GOC)
    assert g["so_snapshot"] == 4 and g["phu_gio"] == 72.0
    assert "THIEU_MAU" not in g["co"] and g["tam"] is False
    assert (g["trung_vi_truoc"], g["trung_vi"]) == (1950, 1950) and g["tang_toc"] == 1.0
    assert g["tang_dot_ngot"] is False and g["xep_loai"] == "chua_co_da"          # đủ mẫu nhưng chưa đạt đủ 2 tiêu chí
    assert any("tiêu chí 1" in x for x in g["ly_do_thieu"]) and any("tiêu chí 2" in x for x in g["ly_do_thieu"])
    assert g["d_ban_ngay"] == 60.0
    assert "MAU_TOP_VIDEO" not in g["co_canh_bao"], g["co_canh_bao"]


# ====================================================================================== bí mật / biên
def test_token_khong_ro_ri_o_dau_ra_log_db_va_api(sau_3_ngay):
    nd = sau_3_ngay
    for kq in [nd.kq_nap, *nd.kq_hang]:
        assert TOKEN not in kq.out and TOKEN not in kq.err and USER_ID not in kq.out
        assert not any(TOKEN in d or USER_ID in d for d in kq.logs), kq.logs
        assert TOKEN not in " ".join(kq.argv)
    b = nd.bang()
    assert TOKEN not in json.dumps(b, ensure_ascii=False)
    nd.tat_ca_file_khong_co_token()                                # radar_uid.db(+wal), runner.db, mọi file tạm
    assert any(x["h"]["authorization"] == f"Bearer {TOKEN}" for x in nd.gia.nhat_ky)   # token thật sự được gửi tới máy giả


def test_token_het_han_401_tu_dung_va_bang_bao_token(sau_nap):
    nd = sau_nap
    nd.token_file.write_text(json.dumps({"token": "FAKE-TOKEN-SAI", "user_id": USER_ID}), encoding="utf-8")
    kq = nd.hang_ngay(1)
    assert kq.ma == 0 and kq.kq["trang_thai"] == "tu_dung" and kq.kq["ly_do"] == "token_het_han"
    assert kq.kq["so_goi"] == 1 and kq.dau_ra == "xong"
    b = nd.bang()
    assert b["token"]["trang_thai"] == "het_han" and "token hết hạn" in b["token"]["cau"]
    assert b["lan"]["ly_do"] == "token_het_han" and b["lan"]["ten_ly_do"].startswith("EchoTik trả trang lỗi")
    assert "FAKE-TOKEN-SAI" not in kq.out + kq.err + " ".join(kq.logs) + json.dumps(b)
    assert sqlite3.connect(nd.db).execute("SELECT COUNT(*) FROM chup_uid WHERE trang_thai='dang_chup'").fetchone()[0] == 0


def test_cli_that_token_thieu_khong_cham_mang(tmp_path):
    """Chạy `python -B -m runner.radar_uid` thật (subprocess). File token KHÔNG tồn tại ⇒ dừng `token_thieu` TRƯỚC khi
    tạo client EchoTik: không có kết nối mạng nào (không tiêm được host giả qua subprocess nên chỉ chạy đường này)."""
    db = tmp_path / "du_lieu" / "radar_uid.db"
    k = KhoRadarUid(db, lambda: datetime(2026, 11, 21, 10, 0, 0))
    k.mo()
    k.them_goc(GOC, "nhan")
    k.dat_trang_thai_nhom(GOC, "da_tim")
    k.dong()
    env = {**os.environ, "KHO_RUNNER_DIR": str(tmp_path / "du_lieu"), "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, "-B", "-m", "runner.radar_uid", "--che-do", "hang-ngay", "--ngay", "2026-11-21",
                        "--db", str(db), "--token-file", str(tmp_path / "khong_co" / "token.json"),
                        "--viec-id", "tay", "--tran-goi", "60"],
                       cwd=str(TOOLS), env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert r.stdout.count("\n") == 1
    assert json.loads(r.stdout) == {"trang_thai": "tu_dung", "ly_do": "token_thieu", "so_uid": 0, "so_goi": 0}
    assert "Traceback" not in r.stderr
    k2 = KhoRadarUid(db, lambda: datetime(2026, 11, 21, 10, 0, 0), chi_doc=True)
    assert k2.doc_token()["trang_thai"] == "thieu"
    k2.dong()
