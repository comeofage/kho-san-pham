"""Test danh mục việc đợt 3 + dò dự án — chạy: python -B -m pytest tools/test_runner_danh_muc.py -q"""
import json
import os
import re
import sqlite3
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from runner import danh_muc as dm  # noqa: E402
from runner import du_an  # noqa: E402
from runner.kieu import MUI_GIO_VN, CanNguoiDung, MoiTruong, ThamSoLoi  # noqa: E402

UID = "1729420930611055346"
UID2 = "1729482409825635197"
ME = "20261117-a"
BAY_GIO = datetime(2026, 11, 17, 9, 0, 0)
BAT_DAU = "2026-11-17T09:00:00+07:00"
TS_BAT_DAU = datetime(2026, 11, 17, 9, 0, 0, tzinfo=MUI_GIO_VN).timestamp()
ID = "j20261117090000abcd"
SID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def _du_lieu_tam(tmp_path, monkeypatch):
    monkeypatch.setenv("KHO_RUNNER_DIR", str(tmp_path / "du_lieu"))


def _mtime(p: Path, ts: float) -> None:
    os.utime(p, (ts, ts))


@pytest.fixture
def mt(tmp_path):
    goc1, goc2 = tmp_path / "goc1", tmp_path / "goc2"
    p = goc1 / f"Bình nước {UID}"
    (p / "kich-ban").mkdir(parents=True)
    (p / "voice").mkdir()
    (p / "kich-ban" / "poster_captions.txt").write_text("cap\n", encoding="utf-8")
    (p / "kich-ban" / f"{ME}_kich-ban-da-cham.md").write_text("x", encoding="utf-8")
    (p / "kich-ban" / "20261118-b_kich-ban-da-cham.md").write_text("x", encoding="utf-8")
    (p / "kich-ban" / "20261118-b_kich-ban.md").write_text("x", encoding="utf-8")
    (goc2 / f"Khác {UID}").mkdir(parents=True)
    (goc2 / f"Lạ 9{UID}").mkdir()          # 20 chữ số: không phải UID này
    (goc2 / f"SP {UID2}").mkdir()
    repo = tmp_path / "repo"
    (repo / "data" / UID).mkdir(parents=True)
    (repo / "data" / UID2).mkdir(parents=True)
    (repo / "data" / UID2 / "douyin.md").write_text("mẫu", encoding="utf-8")
    (repo / "tools").mkdir()
    sp = tmp_path / "pcq"
    (sp / f"sp_{UID}").mkdir(parents=True)
    radar = tmp_path / "radar_goc"
    radar.mkdir()
    cong = {8023: True, 7890: True}
    st = {"ffmpeg": False, "kho": None, "ma": ["ab1", "ab2"], "tl": {}}
    m = MoiTruong(
        gocs=[goc1, goc2], repo_kho=repo, thu_muc_scripts=tmp_path / "scripts",
        python_poster=tmp_path / "poster" / "python.exe", claude_exe=tmp_path / "claude.exe",
        agy_exe=tmp_path / "agy.exe", thu_muc_radar=radar, thu_muc_sp=sp, thu_muc_du_lieu=tmp_path / "du_lieu",
        cong_song=lambda c: cong.get(c, False), chan_doan_kho=lambda _r: st["kho"],
        ffmpeg_ngoai=lambda: st["ffmpeg"], thoi_luong_media=lambda f: st["tl"].get(f.name, 3.0),
        bay_gio=lambda: BAY_GIO, ds_ma_voice=lambda _p, _me: st["ma"])
    m._cong = cong  # type: ignore[attr-defined]
    m._st = st  # type: ignore[attr-defined]
    m._p = p  # type: ignore[attr-defined]
    return m


def _viec(loai: str, tham_so: dict, **kw) -> dict:
    v = {"id": ID, "loai": loai, "tham_so": tham_so, "session_id": SID, "phien_da_tao": 0, "tao_boi": "nhan",
         "bat_dau_luc": BAT_DAU, "lan_thu": 1, "loi_duyet": None}
    v.update(kw)
    return v


# ---------- du_an ----------

def test_gocs_mac_dinh_sao_y_video_server():
    nguon = (Path(__file__).parent / "video_server.py").read_text(encoding="utf-8")
    m = re.search(r'^GOCS = .*?os\.environ\.get\("KHO_VIDEO_GOC", "([^"]*)"\)', nguon, re.M)
    assert m, "không tìm thấy dòng GOCS trong tools/video_server.py"
    assert du_an.GOCS_MAC_DINH == [g for g in m.group(1).split(";") if g.strip()]


def test_gocs_tu_moi_truong(monkeypatch):
    monkeypatch.delenv("KHO_VIDEO_GOC", raising=False)
    assert du_an.gocs_tu_moi_truong() == [Path(g) for g in du_an.GOCS_MAC_DINH]
    monkeypatch.setenv("KHO_VIDEO_GOC", "X:/a; ;Y:/b")
    assert du_an.gocs_tu_moi_truong() == [Path("X:/a"), Path("Y:/b")]


def test_ds_du_an_va_tim(mt):
    ds = du_an.ds_du_an(UID, mt.gocs)
    assert [d["ten"] for d in ds] == [f"Bình nước {UID}", f"Khác {UID}"]
    d0 = ds[0]
    assert d0["ma"] == du_an.ma_du_an(mt._p) and re.fullmatch(r"[0-9a-f]{12}", d0["ma"])
    assert d0["me"] == [ME, "20261118-b"] and d0["co_captions"] is True and ds[1]["co_captions"] is False
    assert set(d0) == {"ma", "ten", "goc", "me", "co_captions"}
    assert du_an.tim_du_an(d0["ma"], UID, mt.gocs) == mt._p
    assert du_an.tim_du_an(d0["ma"], UID2, mt.gocs) is None
    assert du_an.tim_du_an("0" * 12, UID, mt.gocs) is None
    for sai in ("ABCDEF123456", "../x", "1" * 13, 5):
        with pytest.raises(ThamSoLoi):
            du_an.tim_du_an(sai, UID, mt.gocs)
    with pytest.raises(ThamSoLoi):
        du_an.ds_du_an("*", mt.gocs)
    assert du_an.ds_du_an(UID, [mt.gocs[0].parent / "khong_co"]) == []


# ---------- danh mục, tham số ----------

def test_danh_muc_dot_3():
    assert set(dm.DANH_MUC) == {"radar_ban_tin", "phan_tich_uid", "douyin_uid", "xu_ly_link_moi",
                                "poster_day_folder", "voice_pv"}
    for ma, l in dm.DANH_MUC.items():
        assert l.ma == ma and l.dot == 3 and l.ton_tien is False and l.tu_chay_lai is True
    assert dm.DANH_MUC["voice_pv"].lan_chay == "gpu"
    assert {m for m, l in dm.DANH_MUC.items() if "kho" in l.tai_nguyen} == {"phan_tich_uid", "douyin_uid",
                                                                              "xu_ly_link_moi"}
    assert dm.DANH_MUC["poster_day_folder"].tai_nguyen == frozenset({"poster"})
    assert {m: l.het_gio_s for m, l in dm.DANH_MUC.items()} == {
        "radar_ban_tin": 2700, "phan_tich_uid": 5400, "douyin_uid": 2400, "xu_ly_link_moi": 300,
        "poster_day_folder": 900, "voice_pv": 14400}
    assert dm.DANH_MUC["radar_ban_tin"].bo_cong_cu == ("Read", "Write", "Glob")
    assert dm.DANH_MUC["phan_tich_uid"].bo_cong_cu == ("Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill")
    assert dm.DANH_MUC["radar_ban_tin"].agent == "aff-radar" and dm.DANH_MUC["phan_tich_uid"].agent == "aff-san-pham"
    assert dm.DANH_MUC["voice_pv"].agent is None


def test_lay_loai():
    assert dm.lay_loai("voice_pv", 3).ma == "voice_pv"
    with pytest.raises(ThamSoLoi):
        dm.lay_loai("voice_pv", 2)
    with pytest.raises(ThamSoLoi):
        dm.lay_loai("rm_rf", 5)


def test_tham_so_chuan():
    assert dm.tham_so_chuan({"b": 1, "a": "Bình"}) == '{"a":"Bình","b":1}'


def test_kiem_tham_so_hop_le(mt):
    ma = du_an.ma_du_an(mt._p)
    assert dm.DANH_MUC["radar_ban_tin"].kiem_tham_so({}, mt) == {"top_n": 10, "chay_bu": False,
                                                                   "ngay_tao": "2026-11-17"}
    assert dm.DANH_MUC["radar_ban_tin"].kiem_tham_so({"top_n": 30, "chay_bu": True}, mt)["top_n"] == 30
    assert dm.DANH_MUC["phan_tich_uid"].kiem_tham_so({"uid": UID}, mt) == {"uid": UID}
    assert dm.DANH_MUC["douyin_uid"].kiem_tham_so({"uid": UID}, mt) == {"uid": UID}
    assert dm.DANH_MUC["xu_ly_link_moi"].kiem_tham_so({}, mt) == {}
    assert dm.DANH_MUC["poster_day_folder"].kiem_tham_so({"uid": UID, "du_an": ma}, mt) == {"uid": UID, "du_an": ma}
    assert dm.DANH_MUC["voice_pv"].kiem_tham_so({"uid": UID, "du_an": ma, "me": ME}, mt) == \
        {"uid": UID, "du_an": ma, "me": ME}


@pytest.mark.parametrize("loai,tham_so", [
    ("radar_ban_tin", {"top_n": 4}), ("radar_ban_tin", {"top_n": 31}), ("radar_ban_tin", {"top_n": "10"}),
    ("radar_ban_tin", {"top_n": True}), ("radar_ban_tin", {"top_n": 10.5}), ("radar_ban_tin", {"chay_bu": "true"}),
    ("radar_ban_tin", {"chay_bu": 1}), ("radar_ban_tin", {"lenh": "x"}), ("radar_ban_tin", {"ngay_tao": "2026-01-01"}),
    ("phan_tich_uid", {}), ("phan_tich_uid", {"uid": int(UID)}), ("phan_tich_uid", {"uid": UID[:-1]}),
    ("phan_tich_uid", {"uid": UID + "\n"}), ("phan_tich_uid", {"uid": UID, "x": 1}),
    ("phan_tich_uid", {"uid": "１" * 19}),
    ("douyin_uid", {"uid": "abc"}), ("xu_ly_link_moi", {"uid": UID}),
    ("poster_day_folder", {"uid": UID}), ("poster_day_folder", {"uid": UID, "du_an": "0" * 12}),
    ("poster_day_folder", {"uid": UID, "du_an": "E:/oneshottramcanh/x"}),
    ("poster_day_folder", {"uid": UID2, "du_an": "__MA__"}),
    ("voice_pv", {"uid": UID, "du_an": "__MA__"}), ("voice_pv", {"uid": UID, "du_an": "__MA__", "me": "20261119-z"}),
    ("voice_pv", {"uid": UID, "du_an": "__MA__", "me": "../../x"}),
    ("voice_pv", {"uid": UID, "du_an": "__MA__", "me": "20261117-A"}),
])
def test_kiem_tham_so_tu_choi(mt, loai, tham_so):
    ts = {k: (du_an.ma_du_an(mt._p) if v == "__MA__" else v) for k, v in tham_so.items()}
    with pytest.raises(ThamSoLoi):
        dm.DANH_MUC[loai].kiem_tham_so(ts, mt)


@pytest.mark.parametrize("loai", sorted(dm.DANH_MUC))
def test_tham_so_khong_phai_dict(mt, loai):
    with pytest.raises(ThamSoLoi):
        dm.DANH_MUC[loai].kiem_tham_so(["uid"], mt)  # type: ignore[arg-type]


def test_khoa_va_trang_thai_dau(mt):
    ma = du_an.ma_du_an(mt._p)
    K = {m: l.tinh_khoa for m, l in dm.DANH_MUC.items()}
    assert K["radar_ban_tin"]({"top_n": 10, "chay_bu": False, "ngay_tao": "2026-11-17"}) == "2026-11-17"
    assert K["phan_tich_uid"]({"uid": UID}) == UID and K["douyin_uid"]({"uid": UID}) == UID
    assert K["xu_ly_link_moi"]({}) == "kho"
    assert K["poster_day_folder"]({"uid": UID, "du_an": ma}) == ma
    assert K["voice_pv"]({"uid": UID, "du_an": ma, "me": ME}) == f"{ma}:{ME}"
    for l in dm.DANH_MUC.values():
        assert l.trang_thai_dau({}) == ("cho", "chay")


# ---------- điều kiện trước ----------

def test_dieu_kien_truoc(mt):
    ma = du_an.ma_du_an(mt._p)
    poster = {"uid": UID, "du_an": ma}
    voice = {"uid": UID, "du_an": ma, "me": ME}
    D = {m: l.dieu_kien_truoc for m, l in dm.DANH_MUC.items()}
    assert D["poster_day_folder"](poster, mt) is None
    assert D["voice_pv"](voice, mt) is None
    assert D["radar_ban_tin"]({}, mt) is None
    mt._cong[8023] = False
    r = D["poster_day_folder"](poster, mt)
    assert isinstance(r, CanNguoiDung) and r.loai == "viec_tay" and "Poster" in r.noi_dung
    mt._cong[8023] = True
    (mt._p / "kich-ban" / "poster_captions.txt").unlink()
    r = D["poster_day_folder"](poster, mt)
    assert isinstance(r, CanNguoiDung) and "caption" in r.noi_dung.lower()
    mt._st["ffmpeg"] = True
    assert D["voice_pv"](voice, mt) == "ban"
    mt._st["ffmpeg"] = False
    mt._cong[7890] = False
    r = D["voice_pv"](voice, mt)
    assert isinstance(r, CanNguoiDung) and "PerfectVoice" in r.noi_dung
    # chẩn đoán kho
    assert D["phan_tich_uid"]({"uid": UID}, mt) is None
    mt._st["kho"] = "ban"
    for m in ("phan_tich_uid", "douyin_uid", "xu_ly_link_moi"):
        assert D[m]({"uid": UID}, mt) == "ban"
    viec_tay = CanNguoiDung("viec_tay", "Có khoá git cũ")
    mt._st["kho"] = viec_tay
    assert D["xu_ly_link_moi"]({}, mt) == viec_tay
    mt._st["kho"] = None
    r = D["douyin_uid"]({"uid": UID2}, mt)       # chưa có sp_<UID2>
    assert isinstance(r, CanNguoiDung) and r.loai == "viec_tay"
    assert D["douyin_uid"]({"uid": UID}, mt) is None


def test_dieu_kien_truoc_du_an_bien_mat(mt):
    ma = du_an.ma_du_an(mt._p)
    mt._p.rename(mt._p.with_name("doi_ten"))
    r = dm.DANH_MUC["voice_pv"].dieu_kien_truoc({"uid": UID, "du_an": ma, "me": ME}, mt)
    assert isinstance(r, CanNguoiDung) and r.loai == "viec_tay"


# ---------- lệnh Claude ----------

def test_lenh_claude_session_va_resume(mt):
    l = dm.DANH_MUC["radar_ban_tin"]
    a = dm.lenh_claude(l, _viec("radar_ban_tin", {}), mt)
    assert a[:4] == [str(mt.claude_exe), "-p", "--agent", "aff-radar"]
    assert a[a.index("--tools") + 1] == "Read,Write,Glob"
    assert a[a.index("--permission-mode") + 1] == "dontAsk"
    i = a.index("--allowedTools")
    assert a[i + 1:i + 4] == ["Read", "Write", "Glob"] and a[i + 4] == "--disallowedTools"
    j = a.index("--disallowedTools")
    cam = dm.cong_cu_cam_chung()
    assert a[j + 1:j + 1 + len(cam)] == list(cam)
    assert a[a.index("--output-format") + 1] == "stream-json" and "--verbose" in a
    assert a[a.index("--max-budget-usd") + 1] == str(l.tran_usd_moi_luot)
    assert a[a.index("--session-id") + 1] == SID and "--resume" not in a
    assert a[-2:] == ["--add-dir", str(mt.thu_muc_du_lieu / "radar")]
    b = dm.lenh_claude(l, _viec("radar_ban_tin", {}, phien_da_tao=1), mt)
    assert b[b.index("--resume") + 1] == SID and "--session-id" not in b
    c = dm.lenh_claude(dm.DANH_MUC["phan_tich_uid"], _viec("phan_tich_uid", {"uid": UID}), mt)
    assert c[c.index("--tools") + 1] == "Read,Write,Edit,Glob,Grep,Bash,Skill" and "--add-dir" not in c
    assert c[c.index("--max-budget-usd") + 1] == str(dm.DANH_MUC["phan_tich_uid"].tran_usd_moi_luot)


def test_lenh_claude_strict_mcp_config_ca_hai_luot(mt):
    """R-05 P1-1: `--tools` không chặn MCP người dùng → bắt buộc `--strict-mcp-config`, không `--mcp-config`."""
    l = dm.DANH_MUC["radar_ban_tin"]
    for phien in (0, 1):
        a = dm.lenh_claude(l, _viec("radar_ban_tin", {}, phien_da_tao=phien), mt)
        assert a.count("--strict-mcp-config") == 1, (phien, a)
        assert "--mcp-config" not in a, (phien, a)
        # cờ không nằm trong danh sách biến thiên của --allowedTools/--disallowedTools
        i, j = a.index("--allowedTools"), a.index("--disallowedTools")
        assert not (i < a.index("--strict-mcp-config") < a.index("--output-format")), a
        assert a.index("--strict-mcp-config") < i < j
    c = dm.lenh_claude(dm.DANH_MUC["phan_tich_uid"], _viec("phan_tich_uid", {"uid": UID}, phien_da_tao=1), mt)
    assert "--strict-mcp-config" in c and "--resume" in c


def test_lenh_claude_tu_choi(mt):
    with pytest.raises(ThamSoLoi):
        dm.lenh_claude(dm.DANH_MUC["voice_pv"], _viec("voice_pv", {}), mt)
    with pytest.raises(ThamSoLoi):
        dm.lenh_claude(dm.DANH_MUC["radar_ban_tin"], _viec("radar_ban_tin", {}, session_id=None), mt)
    with pytest.raises(ThamSoLoi):
        dm.lenh_claude(dm.DANH_MUC["radar_ban_tin"], _viec("radar_ban_tin", {}, session_id="--x"), mt)


_CAM_CO_DINH = (
    "AskUserQuestion", "Bash(git push*)", "Bash(*wrangler*)", "Bash(*deploy_cloudflare*)", "Bash(*gui_telegram*)",
    "Bash(pip *)", "Bash(*--gui-lai-ma*)", "Bash(*kho-runner*)")
_CAM_CU = ("Edit(//C:/Users/Mi/AppData/Local/kho-runner/**)", "Write(//C:/Users/Mi/AppData/Local/kho-runner/**)",
           "Read(//C:/Users/Mi/AppData/Local/kho-runner/**)")


_PHAN_CAM = ("app/**", "app.moi/**", "app.cu/**", "log/**", "runner.db*", ".runner_key", "runner.lock",
             "runner.log*", "cau_hinh.json")


def _mau_hep(p: str) -> tuple[str, ...]:
    return tuple(f"{c}(//{p}/{phan})" for phan in _PHAN_CAM for c in ("Edit", "Write", "Read"))


def _glob_re(mau: str) -> re.Pattern:
    """Glob kiểu gitignore tối giản: `**` = mọi thứ kể cả `/`, `*` = trong một cấp."""
    out, i = "", 0
    while i < len(mau):
        if mau.startswith("**", i):
            out, i = out + ".*", i + 2
        elif mau[i] == "*":
            out, i = out + "[^/]*", i + 1
        else:
            out, i = out + re.escape(mau[i]), i + 1
    return re.compile(out + r"\Z", re.I)


def _bi_cam(cam: tuple[str, ...], cong_cu: str, duong_dan: str) -> bool:
    for m in cam:
        if m.startswith(cong_cu + "(//") and m.endswith(")"):
            if _glob_re(m[len(cong_cu) + 3:-1]).match(duong_dan):
                return True
    return False


def test_cong_cu_cam_chung_mac_dinh_o_e(monkeypatch):
    """FX-7/7b: không đặt KHO_RUNNER_DIR → cấm HẸP các phần runner trong E:/kho-runner (dấu /), giữ mẫu AppData cũ."""
    monkeypatch.delenv("KHO_RUNNER_DIR", raising=False)
    assert dm.cong_cu_cam_chung() == _CAM_CO_DINH + _mau_hep("E:/kho-runner") + _CAM_CU
    # không còn hằng chụp lúc import (sẽ lệch khi KHO_RUNNER_DIR đổi): chỉ còn hàm
    assert not hasattr(dm, "CONG_CU_CAM_CHUNG")


def test_cong_cu_cam_chung_khong_cam_ca_thu_muc_runner(monkeypatch):
    """FX-7b: radar/ (dữ liệu việc qua --add-dir) KHÔNG bị cấm; khoá, DB, bản cài, log bị cấm."""
    monkeypatch.delenv("KHO_RUNNER_DIR", raising=False)
    cam = dm.cong_cu_cam_chung()
    assert not any(m.endswith("(//E:/kho-runner/**)") for m in cam)
    for cc in ("Read", "Write", "Edit"):
        assert not _bi_cam(cam, cc, "E:/kho-runner/radar/x.json"), cc
        assert not _bi_cam(cam, cc, "E:/kho-runner/radar/j20261117090000abcd.json"), cc
        for p in ("E:/kho-runner/.runner_key", "E:/kho-runner/runner.db", "E:/kho-runner/runner.db-wal",
                  "E:/kho-runner/app/x.py", "E:/kho-runner/app/runner/vong_lap.py", "E:/kho-runner/app.cu/a.py",
                  "E:/kho-runner/app.moi/a.py", "E:/kho-runner/log/j1.log", "E:/kho-runner/runner.lock",
                  "E:/kho-runner/runner.log.1", "E:/kho-runner/cau_hinh.json",
                  "C:/Users/Mi/AppData/Local/kho-runner/radar/x.json"):
            assert _bi_cam(cam, cc, p), (cc, p)
    # mọi thư mục --add-dir của danh mục đều không bị cấm
    mt_gia = type("MT", (), {"thu_muc_du_lieu": Path(r"E:\kho-runner")})()
    for loai in dm.DANH_MUC.values():
        for d in loai.them_thu_muc({}, mt_gia):
            assert not _bi_cam(cam, "Read", Path(d).as_posix() + "/x.json"), (loai.ma, d)


def test_cong_cu_cam_chung_theo_bien_moi_truong(tmp_path, monkeypatch, mt):
    monkeypatch.setenv("KHO_RUNNER_DIR", str(tmp_path / "du_lieu"))
    p = (tmp_path / "du_lieu").as_posix()
    assert "\\" not in p
    cam = dm.cong_cu_cam_chung()
    assert cam == _CAM_CO_DINH + _mau_hep(p) + _CAM_CU
    assert not any("E:/kho-runner" in m for m in cam)
    assert _bi_cam(cam, "Read", f"{p}/.runner_key") and not _bi_cam(cam, "Read", f"{p}/radar/x.json")
    # lenh_claude dùng đúng danh sách theo môi trường tại thời điểm dựng lệnh
    a = dm.lenh_claude(dm.DANH_MUC["radar_ban_tin"], _viec("radar_ban_tin", {}), mt)
    j = a.index("--disallowedTools")
    assert a[j + 1:j + 1 + len(cam)] == list(cam)
    assert not (tmp_path / "du_lieu").exists()


# ---------- lap_buoc ----------

def _db_radar(mt, ngay: str, status: str) -> None:
    with sqlite3.connect(mt.thu_muc_radar / "tiktok_7ngay.db") as c:
        c.execute("CREATE TABLE IF NOT EXISTS scan_runs(id INTEGER PRIMARY KEY, scan_date TEXT, status TEXT)")
        c.execute("INSERT INTO scan_runs(scan_date, status) VALUES(?,?)", (ngay, status))
    c.close()


def test_lap_buoc_radar_co_chay_bu(mt):
    _db_radar(mt, "2026-11-17", "running")
    ts = {"top_n": 10, "chay_bu": True, "ngay_tao": "2026-11-17"}
    v = _viec("radar_ban_tin", ts)
    b = dm.DANH_MUC["radar_ban_tin"].lap_buoc(ts, v, mt)
    assert [x.ten for x in b] == ["quet_bu", "xuat_radar", "claude"]
    assert b[0].argv == ["python", "quet_dot_bien_7ngay.py", "--workers", "6"]
    assert b[0].cwd == str(mt.thu_muc_radar) and b[0].het_gio_s == 1800 and not b[0].la_claude
    assert b[1].argv == ["python", str(dm.RADAR_XUAT), "--ngay", "2026-11-17",
                         "--ra", str(mt.thu_muc_du_lieu / "radar" / f"{ID}.json")]
    assert b[2].la_claude and b[2].argv == dm.lenh_claude(dm.DANH_MUC["radar_ban_tin"], v, mt)
    assert b[2].cwd == str(mt.thu_muc_radar)
    assert b[2].stdin.startswith(f"PHIẾU {ID} — aff-radar")
    assert str(mt.thu_muc_du_lieu / "radar" / f"{ID}.json") in b[2].stdin
    assert all(x.env_them == {} and x.hien_cua_so is False for x in b)


def test_lap_buoc_radar_khong_chay_bu(mt):
    ts = {"top_n": 10, "chay_bu": False, "ngay_tao": "2026-11-17"}
    b = dm.DANH_MUC["radar_ban_tin"].lap_buoc(ts, _viec("radar_ban_tin", ts), mt)
    assert [x.ten for x in b] == ["xuat_radar", "claude"]
    assert b[0].argv == ["python", str(dm.RADAR_XUAT), "--ra", str(mt.thu_muc_du_lieu / "radar" / f"{ID}.json")]


def test_lap_buoc_radar_chay_bu_nhung_hom_nay_da_ok(mt):
    _db_radar(mt, "2026-11-17", "ok")
    ts = {"top_n": 10, "chay_bu": True, "ngay_tao": "2026-11-17"}
    b = dm.DANH_MUC["radar_ban_tin"].lap_buoc(ts, _viec("radar_ban_tin", ts), mt)
    assert [x.ten for x in b] == ["xuat_radar", "claude"]
    assert b[0].argv[2:4] == ["--ngay", "2026-11-17"]


def test_lap_buoc_phan_tich_uid(mt):
    v = _viec("phan_tich_uid", {"uid": UID})
    b = dm.DANH_MUC["phan_tich_uid"].lap_buoc({"uid": UID}, v, mt)
    assert len(b) == 1 and b[0].la_claude and b[0].cwd == str(mt.thu_muc_sp) and b[0].het_gio_s == 5400
    assert b[0].argv == dm.lenh_claude(dm.DANH_MUC["phan_tich_uid"], v, mt)
    assert UID in b[0].stdin and "TRẠNG THÁI" in b[0].stdin
    # đã có phiên → stdin do vòng chạy điền (tin trả lời), không gửi lại phiếu
    b2 = dm.DANH_MUC["phan_tich_uid"].lap_buoc({"uid": UID}, _viec("phan_tich_uid", {"uid": UID}, phien_da_tao=1), mt)
    assert b2[0].stdin is None and "--resume" in b2[0].argv


def test_lap_buoc_douyin(mt):
    v = _viec("douyin_uid", {"uid": UID})
    b = dm.DANH_MUC["douyin_uid"].lap_buoc({"uid": UID}, v, mt)
    assert [x.ten for x in b] == ["ghi_prompt", "agy", "kho_ghi"]
    sp = mt.thu_muc_sp / f"sp_{UID}"
    prompt_file = sp / "douyin" / "_prompt_antigravity.txt"
    assert b[0].argv[0] == "python" and b[0].argv[1] == "-c" and b[0].argv[3] == str(prompt_file)
    assert b[0].stdin and UID in b[0].stdin and b[0].hien_cua_so is False
    assert (mt.repo_kho / "data" / UID2 / "douyin.md").as_posix() in b[0].stdin
    assert b[1].argv == [str(mt.agy_exe), "--dangerously-skip-permissions",
                         "--add-dir", mt.thu_muc_sp.as_posix(),
                         "--add-dir", dm.THU_MUC_SKILL_DOUYIN,
                         "-p", b[0].stdin, "--output-format", "text", "--print-timeout", "0"]
    assert b[1].hien_cua_so is True and b[1].file_log_phu == str(sp / "douyin" / "_antigravity_log.txt")
    assert b[1].het_gio_s == 2400 and not b[1].la_claude
    assert b[2].argv == ["python", (mt.repo_kho / "tools" / "kho.py").as_posix(), "ghi", UID,
                         "--tu", sp.as_posix()]
    assert b[2].cwd == str(mt.repo_kho)


def test_buoc_ghi_prompt_chay_that(mt, tmp_path):
    """Bước ghi_prompt là chương trình python -c thật: ghi stdin UTF-8 ra file (tạo thư mục)."""
    import subprocess
    b = dm.DANH_MUC["douyin_uid"].lap_buoc({"uid": UID}, _viec("douyin_uid", {"uid": UID}), mt)[0]
    argv = [sys.executable if b.argv[0] == "python" else b.argv[0], *b.argv[1:]]
    r = subprocess.run(argv, input=b.stdin.encode("utf-8"), cwd=b.cwd, capture_output=True, timeout=30,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert r.returncode == 0, r.stderr
    assert Path(b.argv[3]).read_text(encoding="utf-8") == b.stdin


def test_kiem_truoc_buoc_douyin(mt):
    ts = {"uid": UID}
    v = _viec("douyin_uid", ts)
    f = mt.thu_muc_sp / f"sp_{UID}" / "douyin" / "canh_quay_an_tien.md"
    r = dm.kiem_truoc_buoc(dm.DANH_MUC["douyin_uid"], "kho_ghi", ts, v, mt)
    assert isinstance(r, CanNguoiDung) and r.loai == "viec_tay" and "captcha" in r.noi_dung
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("5 cảnh", encoding="utf-8")
    _mtime(f, TS_BAT_DAU - 60)                    # file cũ từ lần trước
    assert isinstance(dm.kiem_truoc_buoc(dm.DANH_MUC["douyin_uid"], "kho_ghi", ts, v, mt), CanNguoiDung)
    _mtime(f, TS_BAT_DAU + 60)
    assert dm.kiem_truoc_buoc(dm.DANH_MUC["douyin_uid"], "kho_ghi", ts, v, mt) is None
    assert dm.kiem_truoc_buoc(dm.DANH_MUC["douyin_uid"], "agy", ts, v, mt) is None


def test_can_ban_tu_log():
    assert dm.can_ban_douyin("... 请完成验证 ...") and dm.can_ban_douyin("need LOGIN")
    assert dm.can_ban_douyin("Tải xong 20 video") is None


def test_lap_buoc_xu_ly_link_moi(mt):
    b = dm.DANH_MUC["xu_ly_link_moi"].lap_buoc({}, _viec("xu_ly_link_moi", {}), mt)
    assert len(b) == 1 and b[0].argv == ["python", (mt.repo_kho / "tools" / "kho.py").as_posix(), "cho"]
    assert b[0].cwd == str(mt.repo_kho) and b[0].het_gio_s == 300


def test_lap_buoc_poster(mt):
    ma = du_an.ma_du_an(mt._p)
    ts = {"uid": UID, "du_an": ma}
    b = dm.DANH_MUC["poster_day_folder"].lap_buoc(ts, _viec("poster_day_folder", ts), mt)
    P = mt._p.as_posix()
    goc = [str(mt.python_poster), (mt.thu_muc_scripts / "day_len_poster.py").as_posix(), "--project", P,
           "--link", f"https://shop.tiktok.com/vn/pdp/{UID}", "--captions", f"{P}/kich-ban/poster_captions.txt"]
    assert [x.ten for x in b] == ["poster_xem", "poster_day"]
    assert b[0].argv == goc + ["--xem"] and b[1].argv == goc
    assert b[0].cwd == str(mt._p)


def test_lap_buoc_voice_pv(mt):
    ma = du_an.ma_du_an(mt._p)
    ts = {"uid": UID, "du_an": ma, "me": ME}
    b = dm.DANH_MUC["voice_pv"].lap_buoc(ts, _viec("voice_pv", ts), mt)
    assert len(b) == 1 and b[0].argv == ["python", (mt.thu_muc_scripts / "tao_voice_pv.py").as_posix(),
                                         "--project", mt._p.as_posix(), "--batch", ME]
    assert b[0].het_gio_s == 14400


def test_lap_buoc_du_an_bien_mat_thi_bao_loi(mt):
    ma = du_an.ma_du_an(mt._p)
    mt._p.rename(mt._p.with_name("khac"))
    with pytest.raises(ThamSoLoi):
        dm.DANH_MUC["voice_pv"].lap_buoc({"uid": UID, "du_an": ma, "me": ME}, _viec("voice_pv", {}), mt)


def test_phan_tich_poster():
    assert dm.phan_tich_poster("ok\n", True) == ("xong", False)
    assert dm.phan_tich_poster("[LỖI] caption\n", True) == ("loi", False)
    assert dm.phan_tich_poster("đã gửi\nsoát lại: name=x\n", False) == ("xong", False)
    assert dm.phan_tich_poster("đã gửi\n", False) == ("loi", False)
    assert dm.phan_tich_poster("soát lại: name=x\n[CẢNH BÁO] folder id\n", False) == ("xong", True)
    assert dm.phan_tich_poster("soát lại: name=[LỖI] giả trong tên\n", False) == ("xong", False)


# ---------- kiem_dau_ra ----------

def _info(mt, **d) -> None:
    (mt.repo_kho / "data" / UID / "info.json").write_text(json.dumps(d), encoding="utf-8")


def test_kiem_dau_ra_phan_tich_uid_3_nhanh(mt):
    k = dm.DANH_MUC["phan_tich_uid"].kiem_dau_ra
    ts, v = {"uid": UID}, _viec("phan_tich_uid", {"uid": UID})
    assert k(ts, v, mt) == "chua"                                    # chưa có info.json
    _info(mt, da_phan_tich=True)
    assert k(ts, v, mt) == "chua"                                    # chưa có rui_ro
    _info(mt, da_phan_tich=True, rui_ro={"ket_luan": {}})
    assert k(ts, v, mt) == "xong_lo_ngai"                            # thiếu douyin.md
    (mt.repo_kho / "data" / UID / "douyin.md").write_text("x", encoding="utf-8")
    assert k(ts, v, mt) == "xong"
    _info(mt, da_phan_tich=False, rui_ro=None)
    assert k(ts, v, mt) == "chua"
    (mt.repo_kho / "data" / UID / "info.json").write_text("{hỏng", encoding="utf-8")
    assert k(ts, v, mt) == "khong_ro"


def test_kiem_dau_ra_douyin(mt):
    k = dm.DANH_MUC["douyin_uid"].kiem_dau_ra
    ts = {"uid": UID}
    f = mt.repo_kho / "data" / UID / "douyin.md"
    assert k(ts, _viec("douyin_uid", ts), mt) == "chua"
    f.write_text("x", encoding="utf-8")
    _mtime(f, TS_BAT_DAU - 1)
    assert k(ts, _viec("douyin_uid", ts), mt) == "chua"
    _mtime(f, TS_BAT_DAU + 1)
    assert k(ts, _viec("douyin_uid", ts), mt) == "xong"
    assert k(ts, _viec("douyin_uid", ts, bat_dau_luc=None), mt) == "chua"


def test_kiem_dau_ra_radar(mt):
    k = dm.DANH_MUC["radar_ban_tin"].kiem_dau_ra
    ts = {"top_n": 10, "chay_bu": False, "ngay_tao": "2026-11-17"}
    v = _viec("radar_ban_tin", ts)
    assert k(ts, v, mt) == "chua"
    j = mt.thu_muc_du_lieu / "radar" / f"{ID}.json"
    j.parent.mkdir(parents=True)
    j.write_text(json.dumps({"scan_date": "2026-11-16"}), encoding="utf-8")
    assert k(ts, v, mt) == "chua"
    md = mt.thu_muc_radar / "de-xuat" / "2026-11-16-de-xuat-san-pham.md"
    md.parent.mkdir()
    md.write_text("x", encoding="utf-8")
    _mtime(md, TS_BAT_DAU - 5)
    assert k(ts, v, mt) == "chua"
    _mtime(md, TS_BAT_DAU + 5)
    assert k(ts, v, mt) == "xong"
    j.write_text(json.dumps({"scan_date": "../../x"}), encoding="utf-8")
    assert k(ts, v, mt) == "khong_ro"


def test_kiem_dau_ra_voice_pv(mt):
    ma = du_an.ma_du_an(mt._p)
    ts = {"uid": UID, "du_an": ma, "me": ME}
    v = _viec("voice_pv", ts)
    k = dm.DANH_MUC["voice_pv"].kiem_dau_ra
    for m in ("ab1", "ab2"):
        (mt._p / "voice" / f"{ME}_{m}_adam.mp3").write_bytes(b"x")
    assert k(ts, v, mt) == "xong"
    mt._st["tl"][f"{ME}_ab2_adam.mp3"] = 0.0
    assert k(ts, v, mt) == "chua"
    mt._st["tl"][f"{ME}_ab2_adam.mp3"] = None
    assert k(ts, v, mt) == "chua"
    mt._st["tl"].clear()
    (mt._p / "voice" / f"{ME}_ab2_adam.mp3").unlink()
    assert k(ts, v, mt) == "chua"
    mt._st["ma"] = None
    assert k(ts, v, mt) == "khong_ro"
    mt._st["ma"] = []
    assert k(ts, v, mt) == "khong_ro"


def test_kiem_dau_ra_poster_va_link_khong_tu_doan(mt):
    ma = du_an.ma_du_an(mt._p)
    assert dm.DANH_MUC["poster_day_folder"].kiem_dau_ra({"uid": UID, "du_an": ma}, _viec("p", {}), mt) == "khong_ro"
    assert dm.DANH_MUC["xu_ly_link_moi"].kiem_dau_ra({}, _viec("x", {}), mt) == "chua"


# ---------- mp3 hỏng (P2-7) ----------

def test_mp3_hong(mt):
    v = mt._p / "voice"
    tot, ngan, cu, khong_doc, khac_me = (v / f"{ME}_a1_adam.mp3", v / f"{ME}_a2_adam.mp3", v / f"{ME}_a3_adam.mp3",
                                         v / f"{ME}_a4_adam.mp3", v / "20261118-b_a5_adam.mp3")
    for f in (tot, ngan, cu, khong_doc, khac_me):
        f.write_bytes(b"x")
        _mtime(f, TS_BAT_DAU + 10)
    _mtime(cu, TS_BAT_DAU - 10)
    (v / f"{ME}_a6_adam.mp3.hong-jold").write_bytes(b"x")
    mt._st["tl"].update({ngan.name: 0.0, cu.name: 0.0, khong_doc.name: None, khac_me.name: 0.0})
    hong = dm.mp3_hong(mt._p, ME, datetime(2026, 11, 17, 9, 0, 0), mt)
    assert sorted(hong) == sorted([ngan, khong_doc])
    assert dm.mp3_hong(mt._p / "khong_co", ME, BAY_GIO, mt) == []
    with pytest.raises(ThamSoLoi):
        dm.mp3_hong(mt._p, "../x", BAY_GIO, mt)


# ---------- khởi động lại ----------

@pytest.mark.parametrize("kq,tu_chay,lan,mong", [
    ("xong", True, 1, "xong"), ("xong", False, 1, "xong"),
    ("chua", True, 1, "cho"), ("chua", False, 1, "loi"),
    ("khong_ro", True, 1, "loi"), ("khong_ro", False, 1, "loi"),
    ("chua", True, 3, "loi"), ("xong_lo_ngai", True, 1, "xong"),
])
def test_quyet_dinh_sau_khoi_dong(kq, tu_chay, lan, mong):
    l = replace(dm.DANH_MUC["phan_tich_uid"], tu_chay_lai=tu_chay)
    tt, ghi_chu = dm.quyet_dinh_sau_khoi_dong(_viec("phan_tich_uid", {}, lan_thu=lan), kq, l)
    assert tt == mong and ghi_chu
    if mong == "xong":
        assert "đối soát sau khởi động lại" in ghi_chu
    if mong == "loi":
        assert "Bị ngắt khi máy tắt" in ghi_chu


def test_quyet_dinh_sau_khoi_dong_ton_tien_khong_tu_chay():
    l = replace(dm.DANH_MUC["phan_tich_uid"], ton_tien=True)
    assert dm.quyet_dinh_sau_khoi_dong(_viec("x", {}), "chua", l)[0] == "loi"
    assert dm.quyet_dinh_sau_khoi_dong(_viec("x", {}, phien_da_tao=1), "chua",
                                       dm.DANH_MUC["phan_tich_uid"])[1].lower().count("resume") == 1
    with pytest.raises(ThamSoLoi):
        dm.quyet_dinh_sau_khoi_dong(_viec("x", {}), "la", l)


# ---------- xu_ly_link_moi ----------

def test_con_tu_xu_ly_link():
    out = (f"{UID}\thttps://shop.tiktok.com/vn/pdp/{UID}\tthêm bởi nhan lúc 2026-11-17\n"
           f"tam-1731000000\thttps://vt.tiktok.com/abc\tthêm bởi nhan\n"
           f"{UID}\tlặp\n"
           f"ghi chú có số {UID2}\tở giữa dòng\n"
           f"{UID2}x\tsai\n"
           + "".join(f"17000000000000000{i:02d}\tl\n" for i in range(6)))
    uids, tam = dm.con_tu_xu_ly_link(out, 5)
    assert uids == [UID] + [f"17000000000000000{i:02d}" for i in range(4)]
    assert tam == ["tam-1731000000"]
    assert dm.con_tu_xu_ly_link("Không có link nào chờ.\n", 5) == ([], [])
