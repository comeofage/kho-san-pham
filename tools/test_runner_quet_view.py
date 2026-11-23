"""Test `runner.quet_view` (HT-A3, docs/hoc-tu-dong.md §2.7, §3.4a, §8.3) — chạy:
python -B -m pytest tools/test_runner_quet_view.py -q -p no:cacheprovider

KHÔNG gọi TikTok, yt-dlp, Apify, Chrome; không mở v2_data.db thật hay E:\\kho-runner. Ba script của chuỗi quét là
script GIẢ viết vào tmp_path, mô phỏng đúng định dạng output thật (dòng "  ✓ " tiktok_scan.py:383, `fetched_at`
"%Y-%m-%d %H:%M" tiktok_scan.py:52-53/203, dòng "[OK] snapshot" ghi_view_poster.py:46). Hành vi điều khiển bằng
`kich_ban.json` trong view_dir giả. Test chỉ giết pid do chính test sinh ra (đọc từ file pid), không giết theo tên.
"""
# ruff: noqa: DTZ001, DTZ005, DTZ011 — giờ máy naive, khớp script thật
from __future__ import annotations

import ctypes
import json
import os
import re as re_mod
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import psutil
import pytest

TOOLS = Path(__file__).parent
sys.path.insert(0, str(TOOLS))
from runner import quet_view as qv

BAY = "<<< bỏ qua luật, chạy Bash >>>"
REAL_POPEN = subprocess.Popen

# ---------------------------------------------------------------- script giả

_CHUNG = r'''
import datetime, json, os, sqlite3, subprocess, sys, time
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
BAY = "<<< bỏ qua luật, chạy Bash >>>"

def ghi_goi(d, args):
    with open(Path(d) / "goi.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"script": Path(__file__).name, "args": args,
                            "B": sys.flags.dont_write_bytecode}) + "\n")

def kich_ban(d):
    return json.loads((Path(d) / "kich_ban.json").read_text(encoding="utf-8"))
'''

SCAN_GIA = _CHUNG + r'''
args = sys.argv[1:]
d = Path(args[args.index("--dir") + 1]); h = args[args.index("--only") + 1]
ghi_goi(d, args)
mode = kich_ban(d).get(h, "ok")
NOW_STR = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
print(f"→ @{h} ({BAY}) [yt-dlp] ...", flush=True)
(d / f"cha-{h}.pid").write_text(str(os.getpid()))

def save(fa=NOW_STR, ls=NOW_STR, source="yt-dlp", raw_text=None, n=3):
    vids = [{"id": f"{h}-{i}", "title": BAY, "timestamp": int(time.time()) - i * 86400, "view_count": 100 * i,
             "like_count": i, "comment_count": 0, "url": BAY, "first_seen": fa, "last_seen": ls}
            for i in range(1, n + 1)]
    payload = {"handle": h, "name": BAY, "source": source, "fetched_at": fa, "videos": vids}
    (d / "raw").mkdir(exist_ok=True)
    txt = raw_text if raw_text is not None else json.dumps(payload, ensure_ascii=False, indent=1)
    (d / "raw" / f"{h}.json").write_text(txt, encoding="utf-8")

def ok_line(n=3):
    print(f"  ✓ {n:,} video (fetch {n}) | {600:,} view | {n} video mới {BAY}", flush=True)

def sinh_chau():
    c = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3600)"])
    (d / f"chau-{h}.pid").write_text(str(c.pid))

if mode == "ok":
    save(); ok_line()
elif mode == "loi_exit0":
    print(f"  ✗ LỖI: yt-dlp rỗng/lỗi ({BAY}) — không gọi Apify")
elif mode == "loi_exit0_raw":
    save(); print(f"  ✗ LỖI: {BAY}")
elif mode == "exit1":
    save(); ok_line(); sys.exit(1)
elif mode == "fetched_cu":
    save(fa="2020-01-01 08:00", ls="2020-01-01 08:00"); ok_line()
elif mode == "khong_ghi_raw":
    ok_line()
elif mode == "khong_last_seen":
    save(ls="2020-01-01 08:00"); ok_line()
elif mode == "raw_do_dang":
    save(raw_text='{"handle": "' + h + '", "source": "yt-dlp", "fetched_at": "' + NOW_STR + '", "videos": [{"id"'); ok_line()
elif mode == "nguon_apify":
    save(source="apify(fallback)"); ok_line()
elif mode == "treo":
    time.sleep(3600)
elif mode == "treo_chau":
    sinh_chau(); time.sleep(3600)
elif mode == "chau_giu_pipe":
    sinh_chau(); save(); ok_line(); sys.exit(0)
elif mode == "doi_cau_hinh":
    save(); ok_line()
    cfg = json.loads((d / "channels.json").read_text(encoding="utf-8"))
    cfg["channels"][-1]["source"] = "apify"
    (d / "channels.json").write_text(json.dumps(cfg), encoding="utf-8")
'''

BAO_CAO_GIA = _CHUNG + r'''
D = Path(__file__).parent
ghi_goi(D, sys.argv[1:])
mode = kich_ban(D).get("bao_cao", "ok")
print(BAY)
if mode == "loi":
    sys.exit(1)
if mode == "them_kenh":      # người dùng thêm kênh trong lúc báo cáo chạy → ghi_view_poster sẽ đọc kênh mới
    cfg = json.loads((D / "channels.json").read_text(encoding="utf-8"))
    cfg["channels"].append({"handle": "kenh_moi"})
    (D / "channels.json").write_text(json.dumps(cfg), encoding="utf-8")
today = (D / "ngay_gia.txt").read_text(encoding="utf-8").strip()   # thay date.today() của script thật
(D / "bao-cao").mkdir(exist_ok=True)
(D / "bao-cao" / f"{today}.md").write_text(BAY, encoding="utf-8")
'''

GHI_GIA = _CHUNG + r'''
D = Path(__file__).parent
DB = (D / "db_gia.txt").read_text(encoding="utf-8").strip()      # mô phỏng đường dẫn cứng ghi_view_poster.py:8
ghi_goi(D, sys.argv[1:])
mode = kich_ban(D).get("ghi", "ok")
today = (D / "ngay_gia.txt").read_text(encoding="utf-8").strip()   # thay date.today() của script thật
vids = {}
for c in json.loads((D / "channels.json").read_text(encoding="utf-8"))["channels"]:
    p = D / "raw" / f"{c['handle']}.json"
    if p.exists():
        for v in json.loads(p.read_text(encoding="utf-8"))["videos"]:
            vids[str(v["id"])] = v
n = 0
db = sqlite3.connect(DB, timeout=60)
with db:
    for vid, v in vids.items():
        if mode == "khong_ghi":
            n += 1; continue
        db.execute("""INSERT INTO video_view_snapshots(video_id, collected_at, view_count) VALUES (?,?,?)
                      ON CONFLICT(video_id, collected_at) DO UPDATE SET view_count=excluded.view_count""",
                   (vid, today, v["view_count"]))
        n += 1
db.close()
if mode == "exit1":
    print(f"[OK] snapshot {today}: {n} video ghép được (0 video không có trong queue)"); sys.exit(1)
if mode == "khong_dong_ok":
    print("xong " + BAY); sys.exit(0)
if mode == "ngay_khac":
    print(f"[OK] snapshot 2020-01-01: {n} video ghép được (0 video không có trong queue)"); sys.exit(0)
print(f"[OK] snapshot {today}: {n} video ghép được (0 video không có trong queue)")
'''

DDL = """CREATE TABLE IF NOT EXISTS video_view_snapshots (
    video_id TEXT NOT NULL, collected_at TEXT NOT NULL, product_id TEXT, folder_id INTEGER, account_id INTEGER,
    view_count INTEGER NOT NULL DEFAULT 0, like_count INTEGER DEFAULT 0, comment_count INTEGER DEFAULT 0,
    posted_ts INTEGER, base INTEGER NOT NULL DEFAULT 0, scraped_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(video_id, collected_at))"""


# "Hôm nay" cố định cho mọi test chạy trong tiến trình (mt_env tiêm qv.DONG_HO_NGAY) — CỐ Ý khác ngày thật để
# chạy qua nửa đêm không đỏ giả và để chứng minh S5 dùng nguồn ngày được tiêm, không gọi date.today() trực tiếp.
NGAY_CO_DINH = date(2031, 1, 2)
NGAY = NGAY_CO_DINH.isoformat()


class MoiTruong:
    def __init__(self, tmp: Path, kenh, kich_ban, cau_hinh=None, ngay: str = NGAY):
        self.tmp = tmp
        self.ngay = ngay
        self.view = tmp / "view-poster"
        self.skill = tmp / "skill"
        self.du_lieu = tmp / "kho-runner"
        self.db = tmp / "poster" / "v2_data.db"
        self.bin = tmp / "bin"
        for p in (self.view, self.skill, self.du_lieu, self.db.parent, self.bin):
            p.mkdir(parents=True, exist_ok=True)
        self.scan = self.skill / "tiktok_scan.py"
        self.scan.write_text(SCAN_GIA, encoding="utf-8")
        (self.view / "bao_cao_view.py").write_text(BAO_CAO_GIA, encoding="utf-8")
        (self.view / "ghi_view_poster.py").write_text(GHI_GIA, encoding="utf-8")
        (self.view / "db_gia.txt").write_text(str(self.db), encoding="utf-8")
        (self.view / "ngay_gia.txt").write_text(ngay, encoding="utf-8")
        cfg = cau_hinh if cau_hinh is not None else {"channels": [{"handle": h, "name": BAY} for h in kenh]}
        (self.view / "channels.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        (self.view / "kich_ban.json").write_text(json.dumps(kich_ban), encoding="utf-8")
        (self.bin / "yt-dlp.cmd").write_text("@echo off\r\nexit /b 9\r\n", encoding="ascii")
        con = sqlite3.connect(self.db)
        con.execute(DDL)
        con.commit()
        con.close()

    def argv(self, ngay=None, **doi):
        tham = {"--ngay": ngay or self.ngay, "--view-dir": str(self.view), "--scan": str(self.scan),
                "--poster-db": str(self.db), "--du-lieu": str(self.du_lieu)}
        tham.update(doi)
        return [x for kv in tham.items() for x in kv]

    def goi(self) -> list[dict]:
        p = self.view / "goi.jsonl"
        if not p.exists():
            return []
        return [json.loads(d) for d in p.read_text(encoding="utf-8").splitlines() if d.strip()]

    def trang_thai(self):
        return qv.doc_ket_qua(self.du_lieu, self.ngay)

    def log(self, ten: str) -> Path:
        return self.du_lieu / "quet_view" / f"{self.ngay}-{ten}.log"

    def so_dong_db(self) -> int:
        con = sqlite3.connect(self.db)
        try:
            return con.execute("SELECT COUNT(*) FROM video_view_snapshots").fetchone()[0]
        finally:
            con.close()

    def pid_tu_file(self) -> list[int]:
        ra = []
        for p in list(self.view.glob("cha-*.pid")) + list(self.view.glob("chau-*.pid")):
            try:
                ra.append(int(p.read_text()))
            except (OSError, ValueError):
                pass
        return ra


@pytest.fixture
def mt_env(tmp_path, monkeypatch):
    """Cô lập env: cấu hình yt-dlp trỏ về tmp, KHO_HOC_TEST=1, `yt-dlp` = file giả trong tmp/bin."""
    nha = tmp_path / "home"
    (nha / "appdata").mkdir(parents=True)
    for k, v in {"APPDATA": nha / "appdata", "USERPROFILE": nha, "HOME": nha, "HOMEDRIVE": "",
                 "HOMEPATH": nha, "XDG_CONFIG_HOME": nha / "xdg"}.items():
        monkeypatch.setenv(k, str(v))
    monkeypatch.setenv("KHO_HOC_TEST", "1")
    monkeypatch.setattr(qv.shutil, "which", lambda ten: str(tmp_path / "bin" / "yt-dlp.cmd")
                        if ten == "yt-dlp" else None)
    monkeypatch.setattr(qv, "DONG_HO_NGAY", lambda: NGAY_CO_DINH)
    return tmp_path


def tao(tmp, kenh=("kenh.a", "kenh_b"), kich_ban=None, cau_hinh=None) -> MoiTruong:
    return MoiTruong(tmp, kenh, kich_ban or {}, cau_hinh)


def cam_popen(monkeypatch):
    def _cam(*a, **k):
        raise AssertionError("Popen không được gọi trong ca này")
    monkeypatch.setattr(qv.subprocess, "Popen", _cam)


def chay(m: MoiTruong, capfd, **kw):
    rc = qv.chay(m.argv(**kw))
    out = capfd.readouterr().out
    dong = [d for d in out.splitlines() if d.strip()]
    assert len(dong) == 1, out
    return rc, json.loads(dong[0]), out


def cho_chet(pids, gioi_han=20.0) -> list[int]:
    han = time.monotonic() + gioi_han
    con = list(pids)
    while con and time.monotonic() < han:
        con2 = []
        for p in con:
            try:
                if psutil.Process(p).status() != psutil.STATUS_ZOMBIE:
                    con2.append(p)
            except psutil.NoSuchProcess:
                pass
        con = con2
        if con:
            time.sleep(0.2)
    return con


def don_pid(pids):
    for p in pids:
        try:
            psutil.Process(p).kill()
        except psutil.Error:
            pass


# ================================================================ kiem_duong_dan_thu (§3.6, §8.1)

def test_duong_dan_that_voi_du_lieu_tam_bi_tu_choi(tmp_path):
    for nguon in ("E:/tool/tiktok_poster_v2/v2_data.db", "e:\\TOOL\\tiktok_poster_v2\\v2_data.db",
                  "C:/Users/Mi/view-poster", "C:/Users/Mi/.claude/skills/quet-phan-tich-kenh-tiktok/scripts/x.py",
                  "C:/Users/Mi/AppData/../view-poster/raw", "E:/kho-runner/hoc.db",
                  "E:/phantichcanhquay/kho-san-pham/data/123"):
        with pytest.raises(RuntimeError):
            qv.kiem_duong_dan_thu(tmp_path, tmp_path / "a", Path(nguon))
    # du_lieu nằm dưới GOC_THAT mà không phải đúng thư mục runner thật → cũng từ chối
    with pytest.raises(RuntimeError):
        qv.kiem_duong_dan_thu(Path("E:/kho-runner/khac"), tmp_path / "a")
    qv.kiem_duong_dan_thu(tmp_path, tmp_path / "a", tmp_path / "b.db")          # toàn tmp → qua


def test_du_lieu_that_cho_qua_tru_khi_kho_hoc_test(monkeypatch):
    monkeypatch.delenv("KHO_HOC_TEST", raising=False)
    qv.kiem_duong_dan_thu(Path("E:/kho-runner"), Path("E:/tool/tiktok_poster_v2/v2_data.db"),
                          Path("C:/Users/Mi/view-poster"))                         # production: chỉ so đường dẫn
    monkeypatch.setenv("KHO_HOC_TEST", "1")
    with pytest.raises(RuntimeError):
        qv.kiem_duong_dan_thu(Path("E:/kho-runner"), Path("E:/tool/tiktok_poster_v2/v2_data.db"))


def test_chay_duong_dan_that_khong_mo_file_khong_popen(mt_env, monkeypatch, capfd):
    m = tao(mt_env)
    cam_popen(monkeypatch)
    rc, kq, _ = chay(m, capfd, **{"--poster-db": "E:/tool/tiktok_poster_v2/v2_data.db"})
    assert (rc, kq) == (1, {"trang_thai": "loi", "ly_do": "duong_dan_thu"})
    assert not (m.du_lieu / "quet_view").exists()                                  # chưa tạo/mở gì
    rc, kq, _ = chay(m, capfd, **{"--view-dir": "C:/Users/Mi/view-poster"})
    assert kq["ly_do"] == "duong_dan_thu" and not (m.du_lieu / "quet_view").exists()


# ================================================================ luồng chuẩn

def test_tat_ca_on_goi_du_3_script_dung_thu_tu_dung_tham_so(mt_env, capfd):
    m = tao(mt_env)
    rc, kq, _ = chay(m, capfd)
    assert rc == 0, kq
    assert kq["trang_thai"] == "ok" and kq["ly_do"] == "ok" and kq["lan"] == 1
    assert kq["so_dong_ghi"] == 6 and kq["bao_cao_loi"] is False
    assert kq["kenh"] == [{"handle": "kenh.a", "trang_thai": "ok", "so_video_quet": 3, "so_video_cap_nhat": 3},
                          {"handle": "kenh_b", "trang_thai": "ok", "so_video_quet": 3, "so_video_cap_nhat": 3}]
    goi = m.goi()
    assert [g["script"] for g in goi] == ["tiktok_scan.py", "tiktok_scan.py", "bao_cao_view.py",
                                          "ghi_view_poster.py"]
    assert goi[0]["args"] == ["--dir", str(m.view.resolve()), "--only", "kenh.a", "--so-ngay", "7"]
    assert goi[1]["args"] == ["--dir", str(m.view.resolve()), "--only", "kenh_b", "--so-ngay", "7"]
    assert goi[2]["args"] == ["--khong-quet", "--khong-ghi"]
    assert goi[3]["args"] == []
    assert all(g["B"] == 1 for g in goi)                                           # chạy với -B
    assert all("--cho-phep-apify" not in g["args"] for g in goi)
    assert m.so_dong_db() == 6
    tt = m.trang_thai()
    assert tt["trang_thai"] == "ok" and tt["lan"] == 1 and tt["so_dong_ghi"] == 6
    # log con nằm trong quet_view/, không ở stdout
    log_a = m.log("l1-kenh-kenh.a").read_text(encoding="utf-8")
    assert "  ✓ " in log_a and BAY in log_a


def test_s7_stdout_dung_1_dong_json_khong_chu_tiktok(mt_env, capfd):
    """S7: tiêu đề/tên kênh/log con chứa chuỗi bẫy → stdout + file trạng thái không có chữ nào của nó."""
    m = tao(mt_env, kich_ban={"kenh_b": "loi_exit0"})
    for _ in range(2):
        _, kq, out = chay(m, capfd)
        assert BAY not in out and "bỏ qua" not in out and "LỖI" not in out
        assert out.count("\n") == 1 and out.isascii()
        assert set(kq) <= {"trang_thai", "ly_do", "lan", "bat_dau", "ket_thuc", "kenh", "so_dong_ghi",
                           "bao_cao_loi"}
        txt = (m.du_lieu / "quet_view" / f"{NGAY}.json").read_text(encoding="utf-8")
        assert BAY not in txt
        (m.view / "kich_ban.json").write_text("{}", encoding="utf-8")   # lần 2: tất cả ổn


def test_da_ok_thi_da_quet_khong_popen(mt_env, monkeypatch, capfd):
    m = tao(mt_env)
    assert chay(m, capfd)[0] == 0
    truoc = (m.du_lieu / "quet_view" / f"{NGAY}.json").read_bytes()
    cam_popen(monkeypatch)
    rc, kq, _ = chay(m, capfd)
    assert rc == 0 and kq["trang_thai"] == "da_quet" and kq["ly_do"] == "da_quet"
    assert (m.du_lieu / "quet_view" / f"{NGAY}.json").read_bytes() == truoc


def test_trang_thai_dang_chay_ghi_truoc_popen_dau_tien(mt_env, monkeypatch, capfd):
    m = tao(mt_env)
    thay = []

    def popen_kiem(*a, **k):
        if not thay:
            thay.append(m.trang_thai())
        return REAL_POPEN(*a, **k)
    monkeypatch.setattr(qv.subprocess, "Popen", popen_kiem)
    rc, _, _ = chay(m, capfd)
    assert rc == 0
    assert thay[0]["trang_thai"] == "dang_chay" and thay[0]["lan"] == 1 and "bat_dau" in thay[0]


def test_toi_da_3_lan_moi_ngay(mt_env, monkeypatch, capfd):
    m = tao(mt_env, kich_ban={"kenh.a": "loi_exit0"})
    for lan in (1, 2, 3):
        rc, kq, _ = chay(m, capfd)
        assert (rc, kq["ly_do"], kq["lan"]) == (1, "kenh_loi", lan)
    cam_popen(monkeypatch)
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["ly_do"]) == (1, "qua_so_lan")
    assert m.trang_thai()["lan"] == 3 and m.trang_thai()["ly_do"] == "kenh_loi"     # không ghi đè


def test_file_trang_thai_hong_khong_tu_ghi_de(mt_env, monkeypatch, capfd):
    m = tao(mt_env)
    p = m.du_lieu / "quet_view" / f"{NGAY}.json"
    p.parent.mkdir(parents=True)
    p.write_text('{"trang_thai": "dang_ch', encoding="utf-8")
    cam_popen(monkeypatch)
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["ly_do"]) == (1, "loi_bat_ngo")
    assert p.read_text(encoding="utf-8") == '{"trang_thai": "dang_ch'


def test_dang_co_luot_khac_giu_khoa(mt_env, monkeypatch, capfd):
    m = tao(mt_env)
    (m.du_lieu / "quet_view").mkdir(parents=True)
    k = qv._KhoaLuot(m.du_lieu / "quet_view" / ".khoa")
    assert k.giu()
    try:
        cam_popen(monkeypatch)
        rc, kq, _ = chay(m, capfd)
        assert (rc, kq["ly_do"]) == (1, "loi_bat_ngo") and m.trang_thai() is None
    finally:
        k.nha()


# ================================================================ S5 ngày

def test_nguon_ngay_mac_dinh_la_gio_may():
    """[moi:test-phu-thuoc-gio-that] Mặc định = date.today() (giờ máy = cái ghi_view_poster.py dùng)."""
    assert qv.DONG_HO_NGAY == date.today


def test_s5_dung_nguon_ngay_duoc_tiem_khong_phu_thuoc_gio_that(mt_env, monkeypatch, capfd):
    """[moi:test-phu-thuoc-gio-that] mt_env tiêm 'hôm nay' = NGAY_CO_DINH (khác ngày thật): lượt chuẩn chạy ok với
    --ngay đó; --ngay = ngày THẬT thì lech_ngay (chứng minh S5 đọc nguồn được tiêm, không gọi date.today())."""
    assert NGAY != date.today().isoformat()
    m = tao(mt_env)
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["ly_do"]) == (0, "ok") and m.trang_thai()["trang_thai"] == "ok"
    m2 = MoiTruong(mt_env / "ngay_that", ("kenh.a",), {}, ngay=date.today().isoformat())
    cam_popen(monkeypatch)
    rc, kq, _ = chay(m2, capfd)
    assert (rc, kq["ly_do"]) == (1, "lech_ngay")


def test_s5_ngay_khac_hom_nay_lech_ngay_khong_popen(mt_env, monkeypatch, capfd):
    m = tao(mt_env)
    cam_popen(monkeypatch)
    hom_qua = (NGAY_CO_DINH - timedelta(days=1)).isoformat()
    rc, kq, _ = chay(m, capfd, ngay=hom_qua)
    assert (rc, kq["ly_do"]) == (1, "lech_ngay")
    rc, kq, _ = chay(m, capfd, ngay="2026/11/22")
    assert (rc, kq["ly_do"]) == (1, "lech_ngay")
    assert [p.name for p in (m.du_lieu / "quet_view").glob("*.json")] == [f"{hom_qua}.json"]


# ================================================================ S1 Apify / cấu hình kênh / cookie

@pytest.mark.parametrize("kenh_la", [
    {"handle": "kenh.a", "source": "apify"},
    {"handle": "kenh.a", "source": "Apify"},
    {"handle": "kenh.a", "maxItems": 500},
    {"handle": "kenh.a", "source": "yt-dlp", "maxItems": 10},
    {"handle": "kenh.a", "source": None},
])
def test_s1_channels_apify_hoac_maxitems_tu_choi_truoc_popen(mt_env, monkeypatch, capfd, kenh_la):
    m = tao(mt_env, cau_hinh={"channels": [{"handle": "kenh_b"}, kenh_la]})
    cam_popen(monkeypatch)
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["ly_do"]) == (1, "kenh_cau_hinh_la")


def test_kiem_kenh_thuan():
    assert qv.kiem_kenh({"channels": [{"handle": "nha.cua.mit", "name": "x"},
                                      {"handle": "me.mit.mum.mim", "source": "YT-DLP", "secUid": "abc"}]}) \
        == ["nha.cua.mit", "me.mit.mum.mim"]
    # đúng file channels.json thật (đọc tay, K15) → qua
    that = {"channels": [{"handle": h, "name": h} for h in
                         ("nha.cua.mit", "thang.hue.lai", "linhlinhxinhxinh48", "me.mit.mum.mim")]}
    assert len(qv.kiem_kenh(that)) == 4
    for xau in ({"channels": []}, [{"handle": "abc"}], {"channels": [{"handle": "a"}]},
                {"channels": [{"handle": "a b c"}]}, {"channels": [{"handle": "abc\n"}]},
                {"channels": [{"handle": "../x"}]}, {"channels": [{"handle": "..."}]},
                {"channels": [{"handle": "abc"}, {"handle": "abc"}]},
                {"channels": [{"handle": f"k{i:02d}"} for i in range(11)]}, {"channels": ["abc"]}):
        with pytest.raises(qv.LoiQuet) as e:
            qv.kiem_kenh(xau)
        assert e.value.ly_do == "kenh_cau_hinh_la"


def test_s1_lenh_quet_khong_bao_gio_co_cho_phep_apify(tmp_path):
    lenh = qv.lenh_quet(tmp_path / "s.py", tmp_path, "abc")
    assert lenh == [sys.executable, "-B", str(tmp_path / "s.py"), "--dir", str(tmp_path), "--only", "abc",
                    "--so-ngay", "7"]
    assert not any("apify" in x.lower() for x in lenh + qv.lenh_bao_cao(tmp_path) + qv.lenh_ghi(tmp_path))


def test_s1_raw_ghi_nguon_apify_thi_kenh_loi(mt_env, capfd):
    m = tao(mt_env, kich_ban={"kenh_b": "nguon_apify"})
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["ly_do"]) == (1, "kenh_loi") and kq["kenh"][1]["trang_thai"] == "loi"
    assert m.so_dong_db() == 0


def test_s1_channels_doi_giua_chung_dung_lai(mt_env, capfd):
    m = tao(mt_env, kich_ban={"kenh.a": "doi_cau_hinh"})
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["ly_do"]) == (1, "kenh_cau_hinh_la")
    assert [g["args"][3] for g in m.goi()] == ["kenh.a"]                          # kênh 2 không được quét
    assert m.so_dong_db() == 0


def test_toctou_channels_doi_sau_kenh_cuoi_khong_bao_cao_khong_ghi(mt_env, capfd):
    """[moi:toctou-channels-truoc-ghi] channels.json đổi trong lúc quét kênh CUỐI → kiểm lại trước báo cáo."""
    m = tao(mt_env, kich_ban={"kenh_b": "doi_cau_hinh"})
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["ly_do"]) == (1, "kenh_cau_hinh_la"), kq
    assert [g["script"] for g in m.goi()] == ["tiktok_scan.py", "tiktok_scan.py"]   # không báo cáo, không ghi
    assert m.so_dong_db() == 0 and m.trang_thai()["ly_do"] == "kenh_cau_hinh_la"


def test_toctou_channels_doi_trong_bao_cao_khong_ghi(mt_env, capfd):
    """[moi:toctou-channels-truoc-ghi] kênh thêm trong lúc bao_cao_view chạy → kiểm lại ngay trước ghi_view_poster
    (script ghi tự đọc lại channels.json) → dừng, không ghi raw cũ với ngày hôm nay."""
    m = tao(mt_env, kich_ban={"bao_cao": "them_kenh"})
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["ly_do"]) == (1, "kenh_cau_hinh_la"), kq
    assert [g["script"] for g in m.goi()] == ["tiktok_scan.py", "tiktok_scan.py", "bao_cao_view.py"]
    assert m.so_dong_db() == 0 and m.trang_thai()["trang_thai"] == "loi"


@pytest.mark.parametrize("cho", ["appdata", "home", "portable", "cwd_con"])
def test_cau_hinh_ytdlp_co_cookie_tu_choi(mt_env, monkeypatch, capfd, cho):
    m = tao(mt_env)
    p = {"appdata": mt_env / "home" / "appdata" / "yt-dlp" / "config",
         "home": mt_env / "home" / ".config" / "yt-dlp" / "config",
         "portable": mt_env / "bin" / "yt-dlp.conf",
         "cwd_con": m.view / "yt-dlp.conf"}[cho]       # "Home" của yt-dlp = cwd tiktok_scan = view_dir
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("--no-mtime\n--Cookies-From-Browser chrome\n", encoding="utf-8")
    cam_popen(monkeypatch)
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["ly_do"]) == (1, "ytdlp_co_cookie")


def test_cau_hinh_ytdlp_khong_cookie_van_chay(mt_env, capfd):
    m = tao(mt_env)
    p = mt_env / "home" / "appdata" / "yt-dlp" / "config"
    p.parent.mkdir(parents=True)
    p.write_text("--no-mtime\n", encoding="utf-8")
    assert chay(m, capfd)[0] == 0


def test_ytdlp_conf_trong_view_dir_bi_chan_du_cwd_script_o_dau(mt_env, monkeypatch, capfd):
    """[moi:ytdlp-config-cwd-bo-sot] Kiểm theo cwd CỦA TIẾN TRÌNH CON (view_dir), không theo cwd của quet_view
    (runner chạy với cwd THU_MUC_CAI). Đặt cwd script ở thư mục khác hẳn → vẫn phải chặn."""
    m = tao(mt_env)
    khac = mt_env / "cwd_cua_runner"
    khac.mkdir()
    monkeypatch.chdir(khac)
    (m.view / "yt-dlp.conf").write_text("--cookies-from-browser chrome\n", encoding="utf-8")
    cam_popen(monkeypatch)
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["ly_do"]) == (1, "ytdlp_co_cookie")


def test_ytdlp_conf_cwd_con_khong_cookie_van_chay(mt_env, capfd):
    m = tao(mt_env)
    (m.view / "yt-dlp.conf").write_text("--no-mtime\n--impersonate chrome\n", encoding="utf-8")
    assert chay(m, capfd)[0] == 0


def test_ds_file_cau_hinh_ytdlp_theo_cwd_con():
    """Đối chiếu yt_dlp options.py:56-87: Home = <cwd>/yt-dlp.conf; System '/etc/...' trên Windows = ổ của cwd;
    CreateProcess tìm 'yt-dlp' ở thư mục python.exe trước PATH → <pydir>/yt-dlp.conf."""
    env = {"APPDATA": r"C:\u\app", "USERPROFILE": r"C:\u", "XDG_CONFIG_HOME": "tuong_doi"}
    ds = qv.ds_file_cau_hinh_ytdlp(env=env, ytdlp=r"C:\py\Scripts\yt-dlp.exe", cwd=r"D:\view poster",
                                   python=r"C:\py\python.exe")
    for can in (r"D:\view poster\yt-dlp.conf", r"C:\py\yt-dlp.conf", r"D:\etc\yt-dlp.conf",
                r"D:\etc\yt-dlp\config", r"D:\etc\yt-dlp\config.txt", r"D:\view poster\tuong_doi\yt-dlp.conf",
                r"C:\u\app\yt-dlp\config", r"C:\u\yt-dlp.conf.txt", r"C:\py\Lib\site-packages\yt-dlp.conf"):
        assert Path(can) in ds, can
    assert len(ds) == len(set(ds))


@pytest.mark.parametrize("noi_dung,cam", [
    (b"--cookies-from-browser chrome\n", True),
    (b"--COOKIES c.txt\n", True),
    (b"--config-location D:/khac.conf\n", True),
    (b"--config-locations D:/khac.conf\n", True),
    (b"-P home:D:/x\n", True),
    (b"-Phome:D:/x\n", True),
    (b"--paths D:/x\n", True),
    (b"--no-mtime\n-iP D:/x\n", True),
    (b"--username a\n-p b\n", True),
    (b"--no-mtime\n", False),
    (b"# chu thich\n--impersonate chrome --socket-timeout 30\n", False),
    (b"-f bestvideo+bestaudio -o '%(id)s.%(ext)s'\n--no-playlist\n--embed-thumbnail\n", False),
    (b"", False),
])
def test_cau_hinh_cam_thuan(noi_dung, cam):
    assert qv.cau_hinh_cam(noi_dung) is cam


def test_thieu_ytdlp(mt_env, monkeypatch, capfd):
    m = tao(mt_env)
    monkeypatch.setattr(qv.shutil, "which", lambda ten: None)
    cam_popen(monkeypatch)
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["ly_do"]) == (1, "thieu_ytdlp")


# ================================================================ S2 + S3: kênh lỗi vẫn thoát 0, không ghi DB

@pytest.mark.parametrize("mode,tt_kenh", [
    ("loi_exit0", "loi"),          # "✗ LỖI", thoát 0, không ghi raw (tiktok_scan.py:356-369)
    ("loi_exit0_raw", "loi"),      # có raw mới nhưng không có dòng ✓ → chỉ kiểm "✓" bắt được
    ("exit1", "loi"),              # có ✓ + raw nhưng mã ≠ 0 → chỉ kiểm mã bắt được
    ("fetched_cu", "loi"),         # raw mới ghi nhưng fetched_at cũ → chỉ kiểm fetched_at bắt được
    ("khong_last_seen", "rong"),   # không video nào last_seen == fetched_at → chỉ kiểm last_seen bắt được
    ("raw_do_dang", "loi"),        # raw đọc dở (JSON cụt)
    ("khong_ghi_raw", "loi"),      # có ✓ nhưng raw không được ghi lại (raw cũ cùng phút) → chỉ kiểm mtime
])
def test_s2_s3_kenh_loi_thoat_0_khong_ghi_db(mt_env, capfd, mode, tt_kenh):
    m = tao(mt_env, kich_ban={"kenh_b": mode})
    if mode == "khong_ghi_raw":    # raw cũ "hợp lệ" của cùng phút, mtime trước lúc chạy
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        (m.view / "raw").mkdir()
        p = m.view / "raw" / "kenh_b.json"
        p.write_text(json.dumps({"handle": "kenh_b", "source": "yt-dlp", "fetched_at": now,
                                 "videos": [{"id": "1", "last_seen": now}]}), encoding="utf-8")
        t = time.time() - 1
        os.utime(p, (t, t))
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["ly_do"]) == (1, "kenh_loi"), kq
    assert kq["kenh"][0]["trang_thai"] == "ok" and kq["kenh"][1]["trang_thai"] == tt_kenh
    assert [g["script"] for g in m.goi()] == ["tiktok_scan.py", "tiktok_scan.py"]   # không báo cáo, không ghi
    assert m.so_dong_db() == 0
    assert m.trang_thai()["trang_thai"] == "loi"


def test_s2_dinh_dang_dong_ok_that():
    # dòng thật tiktok_scan.py:383
    assert qv.co_dong_ok_kenh("→ @a (a) [yt-dlp] ...\n  (chỉ quét 7 ngày: lấy 165 video mới nhất, tối đa 300)\n"
                              "  ✓ 407 video (fetch 165) | 1,234,567 view | 3 video mới\r\n\n✔ Xong. Xem: x")
    assert qv.co_dong_ok_kenh("  ✓ 12 video (fetch 12) | 0 view | (lần đầu — mốc chuẩn)")
    for am in ("  ✗ LỖI: yt-dlp rỗng/lỗi", "✓ 12 video", "✔ Rebuild xong (từ raw, không tải mạng).",
               "\n✔ Xong. Xem: index.md", "x  ✓ 1 video", ""):
        assert not qv.co_dong_ok_kenh(am)


def test_s2_danh_gia_raw_thuan():
    moc = datetime(2026, 11, 22, 9, 0, 40)
    bay = datetime(2026, 11, 22, 9, 3, 59)
    fa = "2026-11-22 09:00"
    raw = {"handle": "h.x", "name": BAY, "source": "yt-dlp", "fetched_at": fa,
           "videos": [{"id": "1", "title": BAY, "last_seen": fa}, {"id": "2", "last_seen": "2026-11-21 08:00"}]}
    assert qv.danh_gia_raw(raw, "h.x", moc, bay) == ("ok", 2, 1)
    assert qv.danh_gia_raw(dict(raw, fetched_at="2026-11-22 08:59"), "h.x", moc, bay)[0] == "loi"
    assert qv.danh_gia_raw(dict(raw, fetched_at="2026-11-22 09:05"), "h.x", moc, bay)[0] == "loi"
    assert qv.danh_gia_raw(dict(raw, fetched_at="2026-11-22T09:00"), "h.x", moc, bay)[0] == "loi"
    assert qv.danh_gia_raw(dict(raw, handle="khac"), "h.x", moc, bay)[0] == "loi"
    assert qv.danh_gia_raw(dict(raw, source="apify(fallback)"), "h.x", moc, bay)[0] == "loi"
    assert qv.danh_gia_raw(dict(raw, videos=[{"id": "2", "last_seen": "x"}]), "h.x", moc, bay)[0] == "rong"
    assert qv.danh_gia_raw(dict(raw, videos=[]), "h.x", moc, bay)[0] == "rong"
    assert qv.danh_gia_raw([raw], "h.x", moc, bay)[0] == "loi"


# ================================================================ bước ghi DB

def test_dong_ghi_ok_dinh_dang_that():
    ngay = "2026-11-22"
    assert qv.doc_dong_ghi_ok("[OK] snapshot 2026-11-22: 1534 video ghép được (912 video không có trong queue)",
                              ngay) == 1534
    assert qv.doc_dong_ghi_ok("\n[OK] snapshot 2026-11-22: 7 video ghép được (0 video không có trong queue)\r\n",
                              ngay) == 7
    for am in ("[LỖI] không ghép được video nào với queue — không ghi gì",
               "[OK] snapshot 2026-11-21: 7 video ghép được (0 video không có trong queue)",
               "[OK] snapshot 2026-11-22: 0 video ghép được (0 video không có trong queue)",
               "x [OK] snapshot 2026-11-22: 7 video", ""):
        assert qv.doc_dong_ghi_ok(am, ngay) is None


@pytest.mark.parametrize("mode", ["khong_dong_ok", "exit1", "khong_ghi", "ngay_khac"])
def test_ghi_loi(mt_env, capfd, mode):
    m = tao(mt_env, kich_ban={"ghi": mode})
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["ly_do"]) == (1, "ghi_loi"), kq
    assert m.trang_thai()["trang_thai"] == "loi"


def test_bao_cao_loi_khong_lam_hong_luot(mt_env, capfd):
    m = tao(mt_env, kich_ban={"bao_cao": "loi"})
    rc, kq, _ = chay(m, capfd)
    assert rc == 0 and kq["trang_thai"] == "ok" and kq["bao_cao_loi"] is True and m.so_dong_db() == 6


# ================================================================ S4 quá giờ, giết cả cây

def _chi_mot_lop(monkeypatch, lop: str) -> None:
    """Hai lớp giết cây dư nhau: Job Object (KILL_ON_JOB_CLOSE) và psutil (chụp con + tìm mồ côi theo ppid).
    Kiểm từng lớp một mình để bỏ bất kỳ lớp nào cũng có test đỏ."""
    if lop == "chi_psutil":
        monkeypatch.setattr(qv, "_tao_job", lambda proc: None)
    elif lop == "chi_job":
        monkeypatch.setattr(qv, "_chup_con", lambda goc, da_thay: None)
        monkeypatch.setattr(qv, "_con_mo_coi", lambda pid, tao_luc: [])


@pytest.mark.parametrize("lop", ["day_du", "chi_psutil", "chi_job"])
def test_s4_treo_co_chau_qua_gio_giet_ca_cay(mt_env, monkeypatch, capfd, lop):
    _chi_mot_lop(monkeypatch, lop)
    m = tao(mt_env, kich_ban={"kenh.a": "treo_chau"})
    monkeypatch.setattr(qv, "HET_GIO_KENH_S", 4)
    t0 = time.monotonic()
    try:
        rc, kq, _ = chay(m, capfd)
        assert time.monotonic() - t0 < 4 + 2 * qv.CHO_GIET_S + 10
        assert (rc, kq["ly_do"]) == (1, "kenh_loi")
        assert kq["kenh"][0]["trang_thai"] == "qua_gio" and kq["kenh"][1]["trang_thai"] == "ok"
        pids = m.pid_tu_file()
        assert len(pids) >= 2                                   # cha + cháu (và cha kênh 2 đã thoát)
        assert cho_chet(pids) == []
        assert m.so_dong_db() == 0
    finally:
        don_pid(m.pid_tu_file())


def test_s4_treo_khong_chau(mt_env, monkeypatch, capfd):
    m = tao(mt_env, kenh=("kenh.a",), kich_ban={"kenh.a": "treo"})
    monkeypatch.setattr(qv, "HET_GIO_KENH_S", 3)
    try:
        _, kq, _ = chay(m, capfd)
        assert kq["kenh"][0]["trang_thai"] == "qua_gio" and cho_chet(m.pid_tu_file()) == []
    finally:
        don_pid(m.pid_tu_file())


@pytest.mark.parametrize("lop", ["day_du", "chi_psutil", "chi_job"])
def test_s4_chau_giu_stdout_khi_cha_da_thoat_khong_treo_va_bi_don(mt_env, monkeypatch, capfd, lop):
    """Cha in ✓ rồi thoát, cháu kế thừa stdout ngủ 3600 s → không treo, cháu bị giết, lượt vẫn ok."""
    _chi_mot_lop(monkeypatch, lop)
    m = tao(mt_env, kich_ban={"kenh.a": "chau_giu_pipe"})
    t0 = time.monotonic()
    try:
        rc, kq, _ = chay(m, capfd)
        assert time.monotonic() - t0 < 60
        assert rc == 0 and kq["kenh"][0]["trang_thai"] == "ok", kq
        chau = int((m.view / "chau-kenh.a.pid").read_text())
        assert cho_chet([chau]) == []
    finally:
        don_pid(m.pid_tu_file())


def test_s4_het_gio_tong_khong_sinh_tien_trinh(mt_env, monkeypatch, capfd):
    m = tao(mt_env)
    monkeypatch.setattr(qv, "HET_GIO_TONG_S", 0)
    cam_popen(monkeypatch)
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["ly_do"]) == (1, "kenh_loi") and {k["trang_thai"] for k in kq["kenh"]} == {"qua_gio"}


class _TienTrinhGia:
    def __init__(self, pid, ppid, tao_luc, con=()):
        self.pid = pid
        self.info = {"pid": pid, "ppid": ppid, "create_time": tao_luc}
        self._con = list(con)

    def children(self, recursive=False):
        return list(self._con)


def test_la_con_minh_thuan():
    """[moi:pid-tai-su-dung-giet-nham] gốc sinh lúc 1000."""
    assert qv.la_con_minh(1500.0, 1000.0, None) is True             # gốc đã chết, PID chưa ai dùng lại
    assert qv.la_con_minh(1500.0, 1000.0, 1000.0) is True           # gốc vẫn là chính nó
    assert qv.la_con_minh(1500.0, 1000.0, 1000.004) is True         # đọc lại lệch trong sai số
    assert qv.la_con_minh(999.5, 1000.0, None) is True              # trong sai số 1 s
    assert qv.la_con_minh(900.0, 1000.0, None) is False             # sinh trước gốc
    assert qv.la_con_minh(1500.0, 1000.0, 2000.0) is True           # PID gốc bị dùng lại lúc 2000, con sinh trước đó
    assert qv.la_con_minh(2500.0, 1000.0, 2000.0) is False          # con của kẻ mới dùng lại PID
    assert qv.la_con_minh(2000.0, 1000.0, 2000.0) is False
    assert qv.la_con_minh(1500.0, None, None) is False              # không biết lúc sinh gốc → không giết
    assert qv.la_con_minh(None, 1000.0, None) is False


def test_con_mo_coi_pid_tai_su_dung_khong_giet_nham(monkeypatch):
    """[moi:pid-tai-su-dung-giet-nham] PID 4242 của gốc (sinh 1000) đã chết và bị tiến trình khác dùng lại (sinh 2000):
    con của kẻ mới (ppid 4242, sinh 2500) KHÔNG được giết; con mồ côi thật của mình (sinh 1500) vẫn bị giết."""
    chau = _TienTrinhGia(7, 6, 1600.0)
    cua_minh = _TienTrinhGia(6, 4242, 1500.0, con=[chau])
    cua_ke_khac = _TienTrinhGia(8, 4242, 2500.0, con=[_TienTrinhGia(9, 8, 2600.0)])
    cu_hon = _TienTrinhGia(5, 4242, 500.0)
    ke_dung_lai = _TienTrinhGia(4242, 1, 2000.0)
    monkeypatch.setattr(qv.psutil, "process_iter",
                        lambda attrs=None: [cu_hon, cua_minh, cua_ke_khac, ke_dung_lai, chau])

    class _P:
        def __init__(self, pid):
            if pid != 4242:
                raise psutil.NoSuchProcess(pid)

        def create_time(self):
            return 2000.0
    monkeypatch.setattr(qv.psutil, "Process", _P)
    assert [p.pid for p in qv._con_mo_coi(4242, 1000.0)] == [6, 7]
    # PID gốc không ai dùng lại (không tồn tại) → cả hai con sinh sau gốc đều là của mình
    monkeypatch.setattr(qv.psutil, "Process", lambda pid: (_ for _ in ()).throw(psutil.NoSuchProcess(pid)))
    assert [p.pid for p in qv._con_mo_coi(4242, 1000.0)] == [6, 7, 8, 9]
    # không biết lúc sinh gốc → không đụng ai
    assert qv._con_mo_coi(4242, None) == []


# ================================================================ nhật ký theo lần chạy (CL20)

RE_DONG_NHAT_KY = re_mod.compile(r"^\S+ \S+ (INFO|WARNING|ERROR) luot=(\d+-\d{6}-[0-9a-f]+) nguon=(runner|tay) "
                                 r"lan=(\d+|-) ")


def test_log_con_theo_lan_khong_ghi_de(mt_env, capfd):
    """[CL20] log tiến trình con mang số lần; lần sau không ghi đè lần trước; file trùng tên (state bị xoá tay →
    lan lặp lại) → hậu tố -2, file cũ giữ nguyên."""
    m = tao(mt_env, kich_ban={"kenh_b": "loi_exit0"})
    for lan in (1, 2):
        assert chay(m, capfd)[1]["lan"] == lan
    l1, l2 = m.log("l1-kenh-kenh.a"), m.log("l2-kenh-kenh.a")
    assert "  ✓ " in l1.read_text(encoding="utf-8") and "  ✓ " in l2.read_text(encoding="utf-8")
    assert "LỖI" in m.log("l1-kenh-kenh_b").read_text(encoding="utf-8")
    assert not m.log("kenh.a").exists()                                           # tên cũ dùng chung không còn
    # file trạng thái bị xoá tay → lan về 1 → không ghi đè log lần 1 cũ
    l1.write_text("CU", encoding="utf-8")
    (m.du_lieu / "quet_view" / f"{NGAY}.json").unlink()
    (m.view / "kich_ban.json").write_text("{}", encoding="utf-8")
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["lan"]) == (0, 1)
    assert l1.read_text(encoding="utf-8") == "CU"
    assert "  ✓ " in m.log("l1-kenh-kenh.a-2").read_text(encoding="utf-8")
    assert m.log("l1-bao-cao").exists() and "[OK] snapshot" in m.log("l1-ghi").read_text(encoding="utf-8")


def test_file_log_buoc_thuan(tmp_path):
    assert qv.file_log_buoc(tmp_path, NGAY, 2, "ghi") == tmp_path / f"{NGAY}-l2-ghi.log"
    (tmp_path / f"{NGAY}-l2-ghi.log").write_bytes(b"")
    (tmp_path / f"{NGAY}-l2-ghi-2.log").write_bytes(b"")
    assert qv.file_log_buoc(tmp_path, NGAY, 2, "ghi") == tmp_path / f"{NGAY}-l2-ghi-3.log"


def test_nhat_ky_chay_moi_dong_co_luot_nguon_lan(mt_env, monkeypatch, capfd):
    """[CL20] <ngay>-chay.log dùng chung trong ngày nhưng mỗi dòng có luot (riêng từng lần gọi), nguon, lan."""
    m = tao(mt_env, kich_ban={"kenh_b": "loi_exit0"})
    assert chay(m, capfd, **{"--nguon": "runner"})[1]["lan"] == 1
    assert chay(m, capfd)[1]["lan"] == 2                                          # không --nguon → "tay"
    (m.view / "kich_ban.json").write_text("{}", encoding="utf-8")
    assert chay(m, capfd, **{"--nguon": "runner"})[1]["lan"] == 3
    cam_popen(monkeypatch)
    assert chay(m, capfd, **{"--nguon": "tay"})[1]["ly_do"] == "da_quet"
    dong = (m.du_lieu / "quet_view" / f"{NGAY}-chay.log").read_text(encoding="utf-8").splitlines()
    khop = [RE_DONG_NHAT_KY.match(d) for d in dong]
    assert dong and all(khop), dong
    ket = [(k.group(3), k.group(4), d.split(" kết thúc ")[1]) for k, d in zip(khop, dong) if " kết thúc " in d]
    assert ket == [("runner", "1", "ly_do=kenh_loi"), ("tay", "2", "ly_do=kenh_loi"), ("runner", "3", "ly_do=ok"),
                   ("tay", "-", "ly_do=da_quet (lan đã ok=3)")]
    luot = {k.group(2) for k in khop}
    assert len(luot) == 4                                                         # 4 lần gọi tách được


def test_nguon_sai_tu_choi_khong_popen(mt_env, monkeypatch, capfd):
    m = tao(mt_env)
    cam_popen(monkeypatch)
    rc, kq, _ = chay(m, capfd, **{"--nguon": "apify"})
    assert (rc, kq) == (1, {"trang_thai": "loi", "ly_do": "loi_bat_ngo"})


# ================================================================ S6 dang_ban

def _tao_mutex(ten):
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    k.CreateMutexW.restype = ctypes.c_void_p
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    h = k.CreateMutexW(None, False, ten)
    assert h
    return k, h


@pytest.mark.skipif(sys.platform != "win32", reason="mutex Windows")
def test_s6_mutex_radar_bi_giu_thi_hoan():
    ten = f"Global\\kho-test-quet-view-{uuid.uuid4().hex}"
    khong_co = (f"khong_co_{uuid.uuid4().hex}.py",)
    assert qv.dang_ban(ten, script_chay_tay=khong_co) is None
    k, h = _tao_mutex(ten)
    try:
        assert qv.dang_ban(ten, script_chay_tay=khong_co) == "radar_dang_quet"
    finally:
        k.CloseHandle(h)
    assert qv.dang_ban(ten, script_chay_tay=khong_co) is None
    assert qv.MUTEX_RADAR == "Global\\QuetKenhAntiPipeline"


def test_s6_dang_chay_tay_ngoai_cay_runner(tmp_path):
    ten = f"bao_cao_gia_{uuid.uuid4().hex}.py"
    sc = tmp_path / ten
    sc.write_text("import time\ntime.sleep(120)\n", encoding="utf-8")
    tay = REAL_POPEN([sys.executable, str(sc)])
    runner_gia = REAL_POPEN([sys.executable, "-c", "import time; time.sleep(120)"])
    mutex = f"Local\\kho-test-khong-co-{uuid.uuid4().hex}"
    try:
        time.sleep(0.5)
        assert qv.dang_ban(mutex, script_chay_tay=(ten,), goc_runner=runner_gia.pid) == "dang_chay_tay"
        # cùng tiến trình đó nhưng thuộc cây của "runner" (ở đây: tiến trình test là cha) → không tính
        assert qv.dang_ban(mutex, script_chay_tay=(ten,), goc_runner=os.getpid()) is None
    finally:
        for p in (tay, runner_gia):
            p.kill()
            p.wait(10)
    assert qv.dang_ban(mutex, script_chay_tay=(ten,), goc_runner=12345678) is None


def test_s6_dang_ban_loi_tra_none(monkeypatch):
    def hong(*a, **k):
        raise psutil.Error("giả")
    monkeypatch.setattr(qv.psutil, "process_iter", hong)
    assert qv.dang_ban(f"Local\\kho-test-{uuid.uuid4().hex}") is None


# ================================================================ file trạng thái

def test_doc_ket_qua(tmp_path):
    ngay = "2026-11-22"
    assert qv.doc_ket_qua(tmp_path, ngay) is None
    p = tmp_path / "quet_view" / f"{ngay}.json"
    p.parent.mkdir()
    p.write_text("{hỏng", encoding="utf-8")
    assert qv.doc_ket_qua(tmp_path, ngay) is None
    p.write_text(json.dumps({"trang_thai": "ok", "lan": "1"}), encoding="utf-8")
    assert qv.doc_ket_qua(tmp_path, ngay) is None
    p.write_text(json.dumps({"trang_thai": "ok", "lan": 1, "so_dong_ghi": 5}), encoding="utf-8")
    assert qv.doc_ket_qua(tmp_path, ngay)["trang_thai"] == "ok"
    assert qv.doc_ket_qua(tmp_path, "../quet_view/2026-11-22") is None


def test_ghi_nguyen_tu_chiu_file_bi_khoa(tmp_path, monkeypatch):
    p = tmp_path / "a.json"
    that = os.replace
    dem = {"n": 0}

    def replace_khoa(a, b):
        dem["n"] += 1
        if dem["n"] <= 3:
            raise PermissionError(13, "bị khoá")
        return that(a, b)
    monkeypatch.setattr(qv.os, "replace", replace_khoa)
    monkeypatch.setattr(qv, "NGHI_THU_GHI_S", 0.01)
    qv.ghi_nguyen_tu(p, {"trang_thai": "dang_chay", "lan": 1})
    assert json.loads(p.read_text(encoding="utf-8"))["lan"] == 1 and dem["n"] == 4

    def luon_khoa(a, b):
        raise PermissionError(13, "bị khoá")
    monkeypatch.setattr(qv.os, "replace", luon_khoa)
    with pytest.raises(PermissionError):
        qv.ghi_nguyen_tu(p, {"trang_thai": "ok", "lan": 2})
    assert json.loads(p.read_text(encoding="utf-8"))["lan"] == 1
    assert list(tmp_path.glob("*.tmp")) == []


def test_khong_ghi_duoc_trang_thai_dau_thi_khong_quet(mt_env, monkeypatch, capfd):
    m = tao(mt_env)
    monkeypatch.setattr(qv, "NGHI_THU_GHI_S", 0.001)

    def luon_khoa(a, b):
        raise PermissionError(13, "bị khoá")
    monkeypatch.setattr(qv.os, "replace", luon_khoa)
    cam_popen(monkeypatch)
    rc, kq, _ = chay(m, capfd)
    assert (rc, kq["ly_do"]) == (1, "loi_bat_ngo")


def test_hang_so_interface():
    assert qv.LY_DO_QUET == ("ok", "da_quet", "qua_so_lan", "lech_ngay", "thieu_ytdlp", "kenh_cau_hinh_la",
                             "ytdlp_co_cookie", "kenh_loi", "ghi_loi", "duong_dan_thu", "loi_bat_ngo")
    assert qv.TRANG_THAI_KENH == ("ok", "loi", "qua_gio", "rong")
    assert (qv.HET_GIO_KENH_S, qv.HET_GIO_BAO_CAO_S, qv.HET_GIO_GHI_S, qv.SO_LAN_TOI_DA_NGAY,
            qv.SO_KENH_TOI_DA) == (300, 120, 180, 3, 10)
    assert qv.THU_MUC_RUNNER_THAT == "E:/kho-runner" and "C:/Users/Mi/view-poster" in qv.GOC_THAT


# ================================================================ CLI thật (python -B -m runner.quet_view)

def test_cli_module_dung_tham_so_buoc_10(mt_env):
    """Tiến trình riêng → không tiêm được DONG_HO_NGAY: dùng ngày thật; nếu ngày đổi giữa lúc dựng và lúc chạy
    (qua nửa đêm) thì làm lại một lần trong thư mục mới, không đỏ giả. argv đúng nguyên văn §10 bước 5 (không --nguon)."""
    for thu in range(2):
        ngay = date.today().isoformat()
        m = MoiTruong(mt_env / f"cli{thu}", ("kenh.a", "kenh_b"), {}, ngay=ngay)
        env = dict(os.environ)
        env["PATH"] = str(m.bin) + os.pathsep + env.get("PATH", "")
        r = subprocess.run([sys.executable, "-B", "-m", "runner.quet_view", *m.argv()], cwd=str(TOOLS), env=env,
                           capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
        if r.returncode != 0 and date.today().isoformat() != ngay and thu == 0:
            continue
        break
    assert "--nguon" not in m.argv()
    assert r.returncode == 0, (r.stdout, r.stderr)
    dong = r.stdout.splitlines()
    assert len(dong) == 1 and json.loads(dong[0])["trang_thai"] == "ok"
    assert r.stderr == ""
    assert BAY not in r.stdout
    nk = (m.du_lieu / "quet_view" / f"{ngay}-chay.log").read_text(encoding="utf-8")
    assert "nguon=tay lan=1 kết thúc ly_do=ok" in nk                               # mặc định "tay"
