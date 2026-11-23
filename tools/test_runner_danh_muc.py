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

# D15: 2 loại chỉ-hệ-thống (dot=3, web không tạo được) có test riêng ở cuối file
DOT3 = {m: l for m, l in dm.DANH_MUC.items() if l.dot == 3 and m not in dm.LOAI_CHI_HE_THONG}


def test_danh_muc_dot_3():
    assert set(DOT3) == {"radar_ban_tin", "phan_tich_uid", "douyin_uid", "xu_ly_link_moi",
                         "poster_day_folder", "voice_pv", "poster_bo_loai"}
    for ma, l in DOT3.items():
        assert l.ma == ma and l.dot == 3 and l.ton_tien is False and l.tu_chay_lai is True
    assert dm.DANH_MUC["voice_pv"].lan_chay == "gpu"
    assert {m for m, l in DOT3.items() if "kho" in l.tai_nguyen} == {"phan_tich_uid", "douyin_uid",
                                                                       "xu_ly_link_moi", "poster_bo_loai"}
    assert dm.DANH_MUC["poster_day_folder"].tai_nguyen == frozenset({"poster"})
    assert {m: l.het_gio_s for m, l in DOT3.items()} == {
        "radar_ban_tin": 2700, "phan_tich_uid": 5400, "douyin_uid": 2400, "xu_ly_link_moi": 300,
        "poster_day_folder": 900, "voice_pv": 14400, "poster_bo_loai": 600}
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
    for ma in ("muse_clip", "voice_genmax", "poster_len_lich"):
        with pytest.raises(ThamSoLoi):
            dm.lay_loai(ma, 3)
        assert dm.lay_loai(ma, 4).ma == ma
    with pytest.raises(ThamSoLoi):
        dm.lay_loai("taovideo", 4)
    assert dm.lay_loai("taovideo", 5).ma == "taovideo"


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
    for l in DOT3.values():
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
    assert a[:6] == [str(mt.claude_exe), "-p", "--model", dm.MODEL_CLAUDE, "--agent", "aff-radar"]
    assert dm.MODEL_CLAUDE == "claude-sonnet-5-5"
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
    "Bash(pip *)", "Bash(*--gui-lai-ma*)", "Bash(*kho-runner*)",
    # Radar UID §6.6: giảm chạm nhầm file token EchoTik (cùng user nên KHÔNG phải bảo vệ tuyệt đối)
    "Read(//E:/timsanpham/.echotik_token.json)")
_CAM_CU = ("Edit(//C:/Users/Mi/AppData/Local/kho-runner/**)", "Write(//C:/Users/Mi/AppData/Local/kho-runner/**)",
           "Read(//C:/Users/Mi/AppData/Local/kho-runner/**)")


_PHAN_CAM = ("app/**", "app.moi/**", "app.cu/**", "log/**", "runner.db*", ".runner_key", "runner.lock",
             "runner.log*", "cau_hinh.json", "hoc.db*", "quet_view/**", "radar_uid.db*")


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
                  # D15 §6.1: hoc.db (agent sửa được thì đầu độc gợi ý) + log lượt quét (chữ TikTok)
                  "E:/kho-runner/hoc.db", "E:/kho-runner/hoc.db-wal", "E:/kho-runner/hoc.db-shm",
                  "E:/kho-runner/quet_view/2026-11-17.json", "E:/kho-runner/quet_view/2026-11-17-kenh.log",
                  # Radar UID §6.6: radar_uid.db* (agent không được sửa số liệu xếp hạng)
                  "E:/kho-runner/radar_uid.db", "E:/kho-runner/radar_uid.db-wal", "E:/kho-runner/radar_uid.db-shm",
                  "C:/Users/Mi/AppData/Local/kho-runner/radar/x.json"):
            assert _bi_cam(cam, cc, p), (cc, p)
    # mọi thư mục --add-dir của danh mục đều không bị cấm
    mt_gia = type("MT", (), {"thu_muc_du_lieu": Path(r"E:\kho-runner")})()
    for loai in dm.DANH_MUC.values():
        if loai.ma in dm.LOAI_PHIEN_SONG:      # taovideo: --add-dir cần tham số thật (dự án B) — kiểm riêng dưới
            continue
        for d in loai.them_thu_muc({}, mt_gia):
            assert not _bi_cam(cam, "Read", Path(d).as_posix() + "/x.json"), (loai.ma, d)
    for d in (dm.thu_muc_engine().as_posix(), dm.THU_MUC_SKILLS, "E:/oneshottramcanh/sp 1729420930611055346"):
        assert not _bi_cam(cam, "Read", d + "/x.json"), d


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


# ================================================================ đợt 4 (B-3, §5.2) + khung taovideo (§5.3)

DOT4 = ("muse_clip", "voice_genmax", "poster_len_lich")
SUA = ("sua_video", "hoan_tac_sua")
DUYET = {"loi_duyet": "Duyệt", "duyet_boi": "nhan", "duyet_luc": "2026-11-17T09:00:00+07:00",
         "chu_ky_duyet": "A" * 86}


def _muse_ts(mt, **kw) -> dict:
    ts = {"uid": UID, "du_an": du_an.ma_du_an(mt._p), "mau": ["xoay_360", "cam_tay"], "thoi_luong": 15,
          "ti_le": "9:16"}
    ts.update(kw)
    return ts


def _gm_ts(mt) -> dict:
    return {"uid": UID, "du_an": du_an.ma_du_an(mt._p), "me": ME}


def test_danh_muc_dot_4_va_khung_taovideo():
    # đợt 4 = 3 loại tốn tiền + phụ lục đợt 6 miễn phí (D10: sua_video, hoan_tac_sua gắn dot=4)
    assert {m for m, l in dm.DANH_MUC.items() if l.dot == 4 and l.ton_tien} == set(DOT4)
    assert {m for m, l in dm.DANH_MUC.items() if l.dot == 4 and not l.ton_tien} == set(SUA)
    assert dm.DANH_MUC["taovideo"].dot == 5
    for ma in (*DOT4, "taovideo"):
        l = dm.DANH_MUC[ma]
        assert l.ma == ma and l.ton_tien is True and l.tu_chay_lai is False, ma
        assert dm.kiem_dau_ra_an_toan(l, {}, _viec(ma, {}), None) == "khong_ro"   # không tự đoán, không tự chạy lại
        for kq in ("chua", "khong_ro"):
            assert dm.quyet_dinh_sau_khoi_dong(_viec(ma, {}), kq, l)[0] == "loi", (ma, kq)
    M, G, P, T = (dm.DANH_MUC[m] for m in (*DOT4, "taovideo"))
    assert (M.lan_chay, G.lan_chay, P.lan_chay, T.lan_chay) == ("nhe", "gpu", "nhe", "gpu")
    assert (M.tai_nguyen, G.tai_nguyen, P.tai_nguyen, T.tai_nguyen) == (
        frozenset(), frozenset(), frozenset({"poster"}), frozenset({"kho"}))   # FX-B2: không giữ kho (đụng khoá → ban)
    assert (M.agent, G.agent, P.agent, T.agent) == ("aff-muse", None, "aff-poster", "aff-taovideo")
    assert M.bo_cong_cu == P.bo_cong_cu == ("Read", "Write", "Edit", "Glob", "Grep", "Bash")
    assert T.bo_cong_cu == dm.BO_CONG_CU_TAOVIDEO == (
        "Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill", "Agent", "Task", "TaskOutput", "TaskStop",
        "TodoWrite")                                       # §7.9: không SendMessage; có cả Agent và Task
    assert (M.tran_usd_moi_luot, P.tran_usd_moi_luot, T.tran_usd_moi_luot) == (3.0, 2.0, 40.0)
    assert (M.tran_luot, P.tran_luot, T.tran_luot) == (120, 60, 1500)
    assert M.trang_thai_dau({}) == P.trang_thai_dau({}) == T.trang_thai_dau({}) == ("cho_duyet", "chay")
    assert G.trang_thai_dau({}) == ("cho", "uoc_tinh")


def test_mau_prompt_muse_co_dinh():
    M = dm.MAU_PROMPT_MUSE
    assert 6 <= len(M) <= 8 and set(M) == set(dm.TEN_MAU_MUSE)
    for k, v in M.items():
        assert re.fullmatch(r"[a-z0-9_]{1,20}", k), k
        assert isinstance(v, str) and 20 <= len(v) <= 1000 and "\n" not in v and "@SP" in v, k
    mo_ta = {t["ten"]: t for t in dm.DANH_MUC["muse_clip"].tham_so}
    assert [x["ma"] for x in mo_ta["mau"]["lua_chon"]] == list(M)
    assert mo_ta["mau"]["max"] == 10 and mo_ta["thoi_luong"]["lua_chon"] == [10, 15]
    assert mo_ta["ti_le"]["lua_chon"] == ["9:16"]


def test_kiem_tham_so_muse(mt):
    ma = du_an.ma_du_an(mt._p)
    K = dm.DANH_MUC["muse_clip"].kiem_tham_so
    assert K(_muse_ts(mt), mt) == {"uid": UID, "du_an": ma, "mau": ["xoay_360", "cam_tay"], "thoi_luong": 15,
                                   "ti_le": "9:16"}
    assert K({"uid": UID, "du_an": ma, "mau": ["xoay_360"]}, mt) == {
        "uid": UID, "du_an": ma, "mau": ["xoay_360"], "thoi_luong": 10, "ti_le": "9:16"}
    for sai in (dict(mau=[]), dict(mau="xoay_360"), dict(mau=["khong_co"]), dict(mau=["xoay_360", "xoay_360"]),
                dict(mau=[1]), dict(thoi_luong=20), dict(thoi_luong="10"), dict(thoi_luong=True),
                dict(ti_le="16:9"), dict(lenh="x"), dict(du_an="0" * 12), dict(prompt="tự do")):
        with pytest.raises(ThamSoLoi):
            K(_muse_ts(mt, **sai), mt)


def test_kiem_tham_so_genmax_gan_ma_ban(mt):
    K = dm.DANH_MUC["voice_genmax"].kiem_tham_so
    assert K(_gm_ts(mt), mt) == {**_gm_ts(mt), "ma_ban": ["ab1", "ab2"]}
    with pytest.raises(ThamSoLoi):                       # web không được tự gửi danh sách mã
        K({**_gm_ts(mt), "ma_ban": ["ab1"]}, mt)
    for ds in (None, [], ["ab1", "--gui-lai-ma"], ["ab1", "ab1"], ["../x"]):
        mt._st["ma"] = ds
        with pytest.raises(ThamSoLoi):
            K(_gm_ts(mt), mt)
    mt._st["ma"] = ["ab1"]
    with pytest.raises(ThamSoLoi):
        K({**_gm_ts(mt), "me": "20261119-z"}, mt)


def test_ds_folder_poster_va_kiem_tham_so(mt):
    mt.doc_folder_poster = lambda: [{"id": 7, "name": "Bình nước", "videos": 9, "duong_dan": "E:/a/output_poster"},
                                    {"id": "9", "ten": "Ví", "duong_dan": 5},
                                    {"id": True, "name": "x"}, {"name": "thiếu id"}, "rác", {"id": -1}]
    # B-L1: duong_dan giữ NỘI BỘ (api bỏ trước khi trả web); không phải chuỗi → ""
    assert dm.ds_folder_poster(mt) == [{"id": 7, "ten": "Bình nước", "duong_dan": "E:/a/output_poster"},
                                       {"id": 9, "ten": "Ví", "duong_dan": ""}]
    K = dm.DANH_MUC["poster_len_lich"].kiem_tham_so
    assert K({"folder_id": 7, "so_video_ngay": 3}, mt) == {"folder_id": 7, "so_video_ngay": 3}
    assert K({"folder_id": 9, "so_video_ngay": 5}, mt) == {"folder_id": 9, "so_video_ngay": 5}
    assert K({"folder_id": 9, "so_video_ngay": 100}, mt) == {"folder_id": 9, "so_video_ngay": 100}   # 1–100
    assert dm.POSTER_VIDEO_NGAY == (1, 100)
    mo_ta = {t["ten"]: t for t in dm.DANH_MUC["poster_len_lich"].tham_so}["so_video_ngay"]
    assert (mo_ta["min"], mo_ta["max"]) == (1, 100)
    for sai in ({"folder_id": 8, "so_video_ngay": 3}, {"folder_id": "7", "so_video_ngay": 3},
                {"folder_id": 7, "so_video_ngay": 0}, {"folder_id": 7, "so_video_ngay": 101},
                {"folder_id": 7, "so_video_ngay": True}, {"folder_id": 7}, {"folder_id": 7, "so_video_ngay": 3,
                                                                              "account": "x"}):
        with pytest.raises(ThamSoLoi):
            K(sai, mt)

    def hong():
        raise RuntimeError("Poster tắt")
    mt.doc_folder_poster = hong
    with pytest.raises(ThamSoLoi, match="Poster"):
        dm.ds_folder_poster(mt)
    with pytest.raises(ThamSoLoi):
        K({"folder_id": 7, "so_video_ngay": 3}, mt)
    mt.doc_folder_poster = lambda: {"khong": "phai list"}
    with pytest.raises(ThamSoLoi):
        dm.ds_folder_poster(mt)


# ---------- đợt 5: taovideo (B-4, §5.3, §7.2, §7.8, §7.9, §7.10) ----------

TAO_LUC = "2026-11-17T09:00:00+07:00"


def _b(mt) -> Path:
    """Dự án B giả: goc2/Khác <UID> có takes/*.mp4."""
    b = mt.gocs[1] / f"Khác {UID}"
    (b / "takes").mkdir(exist_ok=True)
    (b / "takes" / "t1.mp4").write_bytes(b"x")
    return b


def _a_raw(mt) -> Path:
    (mt._p / "raw").mkdir(exist_ok=True)
    return mt._p


def _tv_ts(mt, **kw) -> dict:
    ts = {"uid": UID, "du_an_a": du_an.ma_du_an(_a_raw(mt)), "du_an_b": du_an.ma_du_an(_b(mt)), "wm": "khong"}
    ts.update(kw)
    return ts


def test_kiem_tham_so_taovideo(mt):
    K = dm.DANH_MUC["taovideo"].kiem_tham_so
    ts = _tv_ts(mt)
    assert K(dict(ts), mt) == ts                                         # gia bỏ trống → không lưu khoá gia
    assert K(dict(ts, gia=None), mt) == ts
    assert K(dict(ts, wm="nha.cua.mit", gia=1000), mt) == dict(ts, wm="nha.cua.mit", gia=1000)
    assert K(dict(ts, gia=10_000_000), mt)["gia"] == 10_000_000
    assert K(dict(ts, du_an_b=ts["du_an_a"]), mt)["du_an_b"] == ts["du_an_a"]   # 1 thư mục cho cả 2 bước
    sai = [dict(ts, wm="khac.kenh"), dict(ts, wm=""), dict(ts, gia=999), dict(ts, gia=10_000_001),
           dict(ts, gia="5000"), dict(ts, gia=True), dict(ts, gia=1.5), dict(ts, du_an_a="0" * 12),
           dict(ts, du_an_b="0" * 12), dict(ts, du_an_b="TU_TIM"), dict(ts, uid=UID2), dict(ts, lenh="x"),
           {k: v for k, v in ts.items() if k != "wm"}, {k: v for k, v in ts.items() if k != "du_an_b"},
           dict(ts, du_an_a=du_an.ma_du_an(_b(mt)))]                     # A phải có raw/
    for s in sai:
        with pytest.raises(ThamSoLoi):
            K(s, mt)
    mo_ta = {t["ten"]: t for t in dm.DANH_MUC["taovideo"].tham_so}
    assert mo_ta["wm"]["lua_chon"] == ["khong", "nha.cua.mit"]
    assert (mo_ta["gia"]["min"], mo_ta["gia"]["max"]) == (1000, 10_000_000)


def test_chot_du_an_b_tu_tim(mt):
    _a_raw(mt)
    with pytest.raises(dm.ChuaChotDuAnB) as e0:                          # 0 dự án có takes/*.mp4
        dm.chot_du_an_b(UID, "tu_tim", mt)
    assert {d["ma"] for d in e0.value.them["ung_vien_b"]} == {d["ma"] for d in du_an.ds_du_an(UID, mt.gocs)}
    assert all(d["co_takes"] is False for d in e0.value.them["ung_vien_b"])
    b = _b(mt)
    assert dm.chot_du_an_b(UID, "tu_tim", mt) == du_an.ma_du_an(b)       # đúng 1
    (mt._p / "takes").mkdir()
    (mt._p / "takes" / "khong_phai_mp4.txt").write_text("x", encoding="utf-8")
    assert dm.chot_du_an_b(UID, "tu_tim", mt) == du_an.ma_du_an(b)       # takes/ không có mp4 → không tính
    (mt._p / "takes" / "a.MP4").write_bytes(b"x")
    with pytest.raises(dm.ChuaChotDuAnB, match="2") as e2:              # 2 dự án → 400 kèm danh sách
        dm.chot_du_an_b(UID, "tu_tim", mt)
    assert sorted(d["ma"] for d in e2.value.them["ung_vien_b"] if d["co_takes"]) == sorted(
        [du_an.ma_du_an(b), du_an.ma_du_an(mt._p)])
    assert isinstance(e2.value, ThamSoLoi)
    # mã cụ thể: chỉ cần dự án có thật của UID
    assert dm.chot_du_an_b(UID, du_an.ma_du_an(b), mt) == du_an.ma_du_an(b)
    for sai in ("0" * 12, "x", 5, None):
        with pytest.raises(ThamSoLoi):
            dm.chot_du_an_b(UID, sai, mt)
    # kiem_tham_so "tu_tim" → lưu mã đã chốt (không lưu chữ tu_tim)
    (mt._p / "takes" / "a.MP4").unlink()
    ts = dm.DANH_MUC["taovideo"].kiem_tham_so(dict(_tv_ts(mt), du_an_b="tu_tim"), mt)
    assert ts["du_an_b"] == du_an.ma_du_an(b)


def _tv_viec(mt, **kw) -> dict:
    return _viec("taovideo", _tv_ts(mt), tao_luc=TAO_LUC, **DUYET, **kw)


def test_lenh_claude_song(mt):
    T = dm.DANH_MUC["taovideo"]
    v = _tv_viec(mt, phien_da_tao=1)                                     # kể cả đã có phiên: KHÔNG --resume
    a = dm.lenh_claude_song(T, v, mt, 60)
    assert a[:2] == [str(mt.claude_exe), "-p"]
    for i, c in enumerate(("--input-format", "stream-json")):
        assert a[a.index("--input-format") + i] == c
    assert a[a.index("--output-format") + 1] == "stream-json" and "--verbose" in a
    assert "--strict-mcp-config" in a and a[a.index("--agent") + 1] == "aff-taovideo"
    assert a[a.index("--session-id") + 1] == SID and "--resume" not in a
    assert a[a.index("--permission-mode") + 1] == "dontAsk"
    assert a[a.index("--max-budget-usd") + 1] == "60"
    assert a[a.index("--tools") + 1] == ",".join(dm.BO_CONG_CU_TAOVIDEO)
    allowed = a[a.index("--allowedTools") + 1:a.index("--disallowedTools")]
    assert tuple(allowed) == dm.BO_CONG_CU_TAOVIDEO and "Agent" in allowed and "Task" in allowed
    assert not any("SendMessage" in x for x in a)
    cam = a[a.index("--disallowedTools") + 1:a.index("--max-budget-usd")]
    assert "AskUserQuestion" in cam and set(dm.cong_cu_cam_chung()) <= set(cam)
    them = [a[i + 1] for i, x in enumerate(a) if x == "--add-dir"]
    assert them == [_b(mt).as_posix(), dm.thu_muc_engine().as_posix(), dm.THU_MUC_SKILLS]
    with pytest.raises(ThamSoLoi):
        dm.lenh_claude_song(T, dict(v, session_id="khong-phai-uuid"), mt, 60)
    with pytest.raises(ThamSoLoi):
        dm.lenh_claude_song(dm.DANH_MUC["phan_tich_uid"], v, mt, 60)
    with pytest.raises(ThamSoLoi):                                       # taovideo không đi lệnh theo lượt (--resume)
        dm.lenh_claude(T, v, mt)


def test_lap_buoc_taovideo_mot_buoc_song(mt):
    from runner.han_muc import HAN_MUC_TRAN
    T = dm.DANH_MUC["taovideo"]
    v = _tv_viec(mt)
    ds = T.lap_buoc(v["tham_so"], v, mt)
    assert len(ds) == 1
    b = ds[0]
    assert (b.ten, b.la_claude, b.song, b.cwd) == ("claude_song", True, True, str(mt._p))
    assert b.het_gio_s == 8 * 3600 and b.env_them == {}
    assert b.argv == dm.lenh_claude_song(T, v, mt, float(HAN_MUC_TRAN["taovideo_usd_viec"]))
    assert "CHẾ ĐỘ CHẠY: MỘT phiên sống" in b.stdin and _b(mt).as_posix() in b.stdin
    with pytest.raises(ThamSoLoi):                                       # chưa duyệt → không dựng phiếu
        T.lap_buoc(v["tham_so"], dict(v, loi_duyet=None), mt)


def test_lap_buoc_taovideo_theo_han_muc_hieu_luc(mt):
    """FX-29: _buoc_taovideo nhận hm (vòng chạy đang giữ) → phiếu, --max-budget-usd, het_gio theo trần hiệu lực;
    lap_buoc_hieu_luc (vòng chạy gọi) đưa hm vào phiếu của loại phiên sống, kể cả khi lap_buoc bị bọc."""
    import dataclasses
    from runner.han_muc import HAN_MUC_TRAN, han_muc_hieu_luc
    T = dm.DANH_MUC["taovideo"]
    v = _tv_viec(mt)
    hm, _ = han_muc_hieu_luc({"codex_luot_viec": 2, "taovideo_usd_viec": 30, "taovideo_lam_s": 3600})
    b = dm._buoc_taovideo(v["tham_so"], v, mt, hm)[0]
    assert "Codex ≤ 2 lần" in b.stdin and "Claude ≤ 30 USD-ước-tính" in b.stdin and "≤ 1 giờ" in b.stdin
    assert b.argv[b.argv.index("--max-budget-usd") + 1] == "30" and b.het_gio_s == 3600
    # không truyền hm → như cũ (trần code; không có cau_hinh.json)
    b0 = dm._buoc_taovideo(v["tham_so"], v, mt)[0]
    assert "Codex ≤ 6 lần" in b0.stdin and b0.het_gio_s == 8 * 3600
    assert b0.argv[b0.argv.index("--max-budget-usd") + 1] == "60"
    # vòng chạy gọi lap_buoc_hieu_luc
    assert "Codex ≤ 2 lần" in dm.lap_buoc_hieu_luc(T, v["tham_so"], v, mt, hm)[0].stdin

    def boc(ts, viec, m):                                                # như test thay argv[0] bằng Claude giả
        return [dataclasses.replace(T.lap_buoc(ts, viec, m)[0], argv=["gia", "-p"])]
    b2 = dm.lap_buoc_hieu_luc(dataclasses.replace(T, lap_buoc=boc), v["tham_so"], v, mt, hm)[0]
    assert b2.argv == ["gia", "-p"] and "Codex ≤ 2 lần" in b2.stdin and b2.song
    # loại không phải phiên sống: đúng như lap_buoc
    P = dm.DANH_MUC["radar_ban_tin"]
    vr = _viec("radar_ban_tin", {"top_n": 10, "chay_bu": False, "ngay_tao": "2026-11-17"})
    assert dm.lap_buoc_hieu_luc(P, vr["tham_so"], vr, mt, hm) == P.lap_buoc(vr["tham_so"], vr, mt)
    assert HAN_MUC_TRAN["codex_luot_viec"] == 6                          # không sửa hằng số


def test_dieu_kien_truoc_taovideo(mt):
    D = dm.DANH_MUC["taovideo"].dieu_kien_truoc
    ts = _tv_ts(mt)
    assert D(ts, mt) is None
    mt._st["ffmpeg"] = True
    assert D(ts, mt) == "ban"
    mt._st["ffmpeg"] = False
    mt._st["kho"] = "ban"
    assert D(ts, mt) == "ban"
    mt._st["kho"] = None
    cnd = D(dict(ts, du_an_b="0" * 12), mt)
    assert isinstance(cnd, CanNguoiDung) and cnd.loai == "viec_tay"


def _cay_doi_soat(mt, moi: float, cu: float, *, dong_b: bool = True, partial: bool = False,
                  mp4_b_moi: bool = True) -> dict:
    a, b = _a_raw(mt), _b(mt)
    kb = a / "kich-ban"
    (kb / "_log").mkdir(exist_ok=True)
    for me, t in (("20261117-cq01", moi), ("20261001-cq01", cu)):
        f = kb / f"{me}_trang-thai.json"
        f.write_text(json.dumps({"batch": me, "buoc": {"verify": {"xong": True}, "ban_giao": {"xong": True}}}),
                     encoding="utf-8")
        _mtime(f, t)
        (kb / "_log" / f"{me}_tron_goi.xong.json").write_text('{"exit": 0, "buoc": "verify"}', encoding="utf-8")
    (b / "output").mkdir(exist_ok=True)
    for ten in ("v1.mp4", "v2.mp4") + (("v3.partial.mp4",) if partial else ()):
        (b / "output" / ten).write_bytes(b"x")
        _mtime(b / "output" / ten, moi if mp4_b_moi else cu)
    (b / "output" / "cu.mp4").write_bytes(b"x")
    _mtime(b / "output" / "cu.mp4", cu)
    poster = [{"folder": 1, "so_video": 20, "duong_dan": f"{a.as_posix()}/output_poster", "nhan": ""}]
    if dong_b:
        poster.append({"folder": 2, "so_video": 2, "duong_dan": f"{b.as_posix()}/output", "nhan": "nha.cua.mit"})
    info = mt.repo_kho / "data" / UID / "info.json"
    info.write_text(json.dumps({"uid": UID, "da_lam_video": {"xong": True, "poster": poster}}), encoding="utf-8")
    return _tv_viec(mt)


@pytest.fixture
def cam_tien_trinh(monkeypatch):
    import subprocess

    def cam(*_a, **_k):
        raise AssertionError("doi_soat_taovideo không được chạy lệnh")
    for ten in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, ten, cam)
    monkeypatch.setattr(os, "system", cam)


def test_doi_soat_taovideo_du_thi_xong(mt, cam_tien_trinh):
    v = _cay_doi_soat(mt, TS_BAT_DAU + 60, TS_BAT_DAU - 86400)
    kq, tt = dm.doi_soat_taovideo(v["tham_so"], v, mt)
    assert kq == "xong", tt
    assert "20261117-cq01" in tt and "20261001-cq01" not in tt                 # mẻ cũ bị bỏ qua
    assert "Bước B: 2 mp4" in tt and "0 partial" in tt and len(tt) <= 800
    assert dm.DANH_MUC["taovideo"].kiem_dau_ra(v["tham_so"], v, mt) == "xong"


# ---- FX-28 (R-22 P2-4): 'xong' đòi Bước B có mp4 MỚI, 0 partial, và dòng kho mới so với ảnh chụp lúc tạo việc ----

def test_doi_soat_taovideo_buoc_b_chua_lam_thi_chua(mt, cam_tien_trinh):
    # sản phẩm từng làm (dòng kho A + B, mp4 cũ ở B) + phiên chết sau Bước A → KHÔNG được 'xong'
    v = _cay_doi_soat(mt, TS_BAT_DAU + 60, TS_BAT_DAU - 86400, mp4_b_moi=False)
    kq, tt = dm.doi_soat_taovideo(v["tham_so"], v, mt)
    assert kq == "chua", tt
    assert "Bước B: 0 mp4 mới" in tt


def test_doi_soat_taovideo_con_partial_thi_chua(mt, cam_tien_trinh):
    v = _cay_doi_soat(mt, TS_BAT_DAU + 60, TS_BAT_DAU - 86400, partial=True)
    kq, tt = dm.doi_soat_taovideo(v["tham_so"], v, mt)
    assert kq == "chua" and "1 partial" in tt, tt


def _info_poster(mt) -> list[dict]:
    d = json.loads((mt.repo_kho / "data" / UID / "info.json").read_text(encoding="utf-8"))
    return d["da_lam_video"]["poster"]


def _ghi_poster(mt, poster: list[dict]) -> None:
    f = mt.repo_kho / "data" / UID / "info.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["da_lam_video"]["poster"] = poster
    f.write_text(json.dumps(d), encoding="utf-8")


def test_anh_chup_kho_taovideo(mt, cam_tien_trinh):
    v = _cay_doi_soat(mt, TS_BAT_DAU + 60, TS_BAT_DAU - 86400)
    ac = dm.anh_chup_kho_taovideo(v["tham_so"], mt)
    assert ac == {"a": [[1, 20]], "b": [[2, 2]]}
    json.dumps(ac)                                                       # lưu được vào ket_qua (JSON)
    (mt.repo_kho / "data" / UID / "info.json").unlink()                  # chưa có info.json → rỗng, không ném
    assert dm.anh_chup_kho_taovideo(v["tham_so"], mt) == {"a": [], "b": []}


def test_doi_soat_taovideo_anh_chup_khong_doi_thi_chua(mt, cam_tien_trinh):
    v = _cay_doi_soat(mt, TS_BAT_DAU + 60, TS_BAT_DAU - 86400)
    v["ket_qua"] = {"kho_luc_tao": dm.anh_chup_kho_taovideo(v["tham_so"], mt)}
    kq, tt = dm.doi_soat_taovideo(v["tham_so"], v, mt)
    assert kq == "chua", tt                                              # dòng kho y như lúc tạo việc
    assert "chưa có dòng mới" in tt


def test_doi_soat_taovideo_anh_chup_dong_moi_thi_xong(mt, cam_tien_trinh):
    v = _cay_doi_soat(mt, TS_BAT_DAU + 60, TS_BAT_DAU - 86400)
    v["ket_qua"] = {"kho_luc_tao": dm.anh_chup_kho_taovideo(v["tham_so"], mt)}
    p = _info_poster(mt)
    p.append(dict(p[0], folder=11, so_video=19))                          # A: folder mới
    _ghi_poster(mt, p)
    assert dm.doi_soat_taovideo(v["tham_so"], v, mt)[0] == "chua"        # B vẫn như cũ
    p[1]["so_video"] = 22                                                # B: đẩy lại cùng folder, so_video tăng
    _ghi_poster(mt, p)
    kq, tt = dm.doi_soat_taovideo(v["tham_so"], v, mt)
    assert kq == "xong", tt
    # ảnh chụp lúc chưa có dòng nào → dòng hiện có đều là mới
    v["ket_qua"] = {"kho_luc_tao": {"a": [], "b": []}, "so_codex": 2}
    assert dm.doi_soat_taovideo(v["tham_so"], v, mt)[0] == "xong"


def test_doi_soat_taovideo_anh_chup_hong_thi_chua(mt, cam_tien_trinh):
    v = _cay_doi_soat(mt, TS_BAT_DAU + 60, TS_BAT_DAU - 86400)
    for hong in ({"a": "x", "b": []}, {"a": []}, "rác", [[1, 20]], {"a": [[1]], "b": []}):
        v["ket_qua"] = {"kho_luc_tao": hong}
        kq, tt = dm.doi_soat_taovideo(v["tham_so"], v, mt)
        assert kq == "chua" and "ảnh chụp kho" in tt, (hong, tt)
    v["ket_qua"] = {"tom_tat": "x"}                                      # không có ảnh chụp → dựa vào mp4 mới
    assert dm.doi_soat_taovideo(v["tham_so"], v, mt)[0] == "xong"


def test_doi_soat_taovideo_thieu_dong_nha_cua_mit_thi_chua(mt, cam_tien_trinh):
    v = _cay_doi_soat(mt, TS_BAT_DAU + 60, TS_BAT_DAU - 86400, dong_b=False)
    kq, tt = dm.doi_soat_taovideo(v["tham_so"], v, mt)
    assert kq == "chua" and "Bước B" in tt and "chưa ghi kho" in tt
    assert dm.kiem_dau_ra_an_toan(dm.DANH_MUC["taovideo"], v["tham_so"], v, mt) == "chua"


def test_doi_soat_taovideo_chi_co_me_cu_thi_chua(mt, cam_tien_trinh):
    v = _cay_doi_soat(mt, TS_BAT_DAU - 3600, TS_BAT_DAU - 86400)             # mọi mẻ có mtime < tao_luc
    kq, tt = dm.doi_soat_taovideo(v["tham_so"], v, mt)
    assert kq == "chua" and "Bước A" in tt and "chưa có mẻ" in tt


def test_doi_soat_taovideo_verify_chua_xong_hoac_exit_khac_0(mt, cam_tien_trinh):
    v = _cay_doi_soat(mt, TS_BAT_DAU + 60, TS_BAT_DAU - 86400)
    kb = mt._p / "kich-ban"
    (kb / "_log" / "20261117-cq01_tron_goi.xong.json").write_text('{"exit": 2}', encoding="utf-8")
    assert dm.doi_soat_taovideo(v["tham_so"], v, mt)[0] == "chua"
    (kb / "_log" / "20261117-cq01_tron_goi.xong.json").unlink()
    assert dm.doi_soat_taovideo(v["tham_so"], v, mt)[0] == "chua"
    f = kb / "20261117-cq01_trang-thai.json"
    f.write_text("{hỏng", encoding="utf-8")
    _mtime(f, TS_BAT_DAU + 60)
    kq, tt = dm.doi_soat_taovideo(v["tham_so"], v, mt)
    assert kq == "chua" and "đọc được" in tt
    # info.json hỏng / thiếu → chua, không ném
    (mt.repo_kho / "data" / UID / "info.json").write_text("rác", encoding="utf-8")
    assert dm.doi_soat_taovideo(v["tham_so"], v, mt)[0] == "chua"
    # tham số hỏng → kiem_dau_ra_an_toan: khong_ro (không tự đoán)
    assert dm.kiem_dau_ra_an_toan(dm.DANH_MUC["taovideo"], {}, v, mt) == "khong_ro"


def test_doi_soat_taovideo_dong_kho_adam_phai_thuoc_du_an_a(mt, cam_tien_trinh):
    v = _cay_doi_soat(mt, TS_BAT_DAU + 60, TS_BAT_DAU - 86400)
    info = mt.repo_kho / "data" / UID / "info.json"
    d = json.loads(info.read_text(encoding="utf-8"))
    d["da_lam_video"]["poster"][0]["duong_dan"] = "E:/khac/du-an-khac/output_poster"
    info.write_text(json.dumps(d), encoding="utf-8")
    kq, tt = dm.doi_soat_taovideo(v["tham_so"], v, mt)
    assert kq == "chua" and "Poster chưa ghi kho" in tt


def test_mp3_adam_moi(mt, tmp_path):
    p = mt._p
    (p / "voice" / "_hong").mkdir()
    for ten, t in (("voice/20261117-cq01_ud1_adam.mp3", TS_BAT_DAU + 5),
                   ("voice/_hong/20261117-cq01_ud2_adam.mp3", TS_BAT_DAU + 5),
                   ("voice/20261117-cq01_ud3_adam.mp3", TS_BAT_DAU - 5),        # cũ
                   ("voice/20261117-cq01_ud4.mp3", TS_BAT_DAU + 5)):           # không phải *_adam.mp3
        (p / ten).write_bytes(b"x")
        _mtime(p / ten, t)
    tu = datetime(2026, 11, 17, 9, 0, 0, tzinfo=MUI_GIO_VN)
    assert dm.mp3_adam_moi(p, tu) == frozenset({"voice/20261117-cq01_ud1_adam.mp3",
                                                "voice/_hong/20261117-cq01_ud2_adam.mp3"})
    assert dm.mp3_adam_moi(tmp_path / "khong_co", tu) == frozenset()


def test_khoa_dot_4(mt):
    ma = du_an.ma_du_an(mt._p)
    assert dm.DANH_MUC["muse_clip"].tinh_khoa(_muse_ts(mt)) == ma
    assert dm.DANH_MUC["voice_genmax"].tinh_khoa({**_gm_ts(mt), "ma_ban": ["ab1"]}) == f"{ma}:{ME}"
    assert dm.DANH_MUC["poster_len_lich"].tinh_khoa({"folder_id": 7, "so_video_ngay": 3}) == "folder:7"


def test_dieu_kien_truoc_dot_4(mt):
    M, G, P = (dm.DANH_MUC[m].dieu_kien_truoc for m in DOT4)
    r = M(_muse_ts(mt), mt)
    assert isinstance(r, CanNguoiDung) and r.loai == "viec_tay" and "Video Batch Local" in r.noi_dung
    mt._cong[dm.CONG_VIDEO_BATCH] = True
    assert M(_muse_ts(mt), mt) is None
    assert G({**_gm_ts(mt), "ma_ban": ["ab1"]}, mt) is None
    mt._st["ffmpeg"] = True
    assert G({**_gm_ts(mt), "ma_ban": ["ab1"]}, mt) == "ban"
    mt._st["ffmpeg"] = False
    mt.doc_folder_poster = lambda: [{"id": 7, "name": "Bình nước"}]   # B-L1: điều kiện đọc folder để đếm Loại
    assert P({"folder_id": 7, "so_video_ngay": 3}, mt) is None
    mt._cong[8023] = False
    r = P({"folder_id": 7, "so_video_ngay": 3}, mt)
    assert isinstance(r, CanNguoiDung) and "Poster" in r.noi_dung
    mt._p.rename(mt._p.with_name("doi_ten"))
    assert isinstance(M(_muse_ts(mt), mt), CanNguoiDung)
    assert isinstance(G({**_gm_ts(mt), "ma_ban": ["ab1"]}, mt), CanNguoiDung)


# ---------- voice_genmax 2 pha: KHÔNG đường nào sinh --gui-lai-ma; --dong-y chỉ sau duyệt ----------

def _gm_viec(mt, buoc, **kw):
    ts = {**_gm_ts(mt), "ma_ban": ["ab1", "ab2"]}
    return ts, _viec("voice_genmax", ts, session_id=None, buoc=buoc, **kw)


def test_lap_buoc_genmax_uoc_tinh_khong_goi_api(mt, monkeypatch):
    monkeypatch.setenv("GENMAX_API_KEY", "khoa-genmax-thu-123456")
    ts, v = _gm_viec(mt, "uoc_tinh")
    b = dm.DANH_MUC["voice_genmax"].lap_buoc(ts, v, mt)
    assert len(b) == 1 and not b[0].la_claude
    assert b[0].argv == ["python", (mt.thu_muc_scripts / "tao_voice.py").as_posix(), "--project", mt._p.as_posix(),
                         "--batch", ME, "--ma", "ab1", "ab2"]
    assert b[0].env_them == {} and b[0].cwd == str(mt._p)
    assert b[0].het_gio_s == dm.DANH_MUC["voice_genmax"].het_gio_s


def test_lap_buoc_genmax_chay_sau_duyet(mt, monkeypatch):
    monkeypatch.setenv("GENMAX_API_KEY", "khoa-genmax-thu-123456")
    ts, v = _gm_viec(mt, "chay", **DUYET)
    b = dm.DANH_MUC["voice_genmax"].lap_buoc(ts, v, mt)
    assert len(b) == 1
    a = b[0].argv
    assert a[:6] == ["python", (mt.thu_muc_scripts / "tao_voice.py").as_posix(), "--project", mt._p.as_posix(),
                     "--batch", ME]
    assert a.count("--dong-y") == 1 and a[a.index("--ma") + 1:] == ["ab1", "ab2"]
    assert a.index("--dong-y") < a.index("--ma")
    assert b[0].env_them == {"GENMAX_API_KEY": "khoa-genmax-thu-123456"}
    monkeypatch.delenv("GENMAX_API_KEY")
    assert dm.DANH_MUC["voice_genmax"].lap_buoc(ts, v, mt)[0].env_them == {}   # tao_voice tự đọc biến tài khoản


@pytest.mark.parametrize("thieu", ["loi_duyet", "duyet_boi", "duyet_luc", "chu_ky_duyet"])
def test_lap_buoc_genmax_chay_thieu_duyet_thi_tu_choi(mt, thieu):
    ts, v = _gm_viec(mt, "chay", **{**DUYET, thieu: None})
    with pytest.raises(ThamSoLoi):
        dm.DANH_MUC["voice_genmax"].lap_buoc(ts, v, mt)


@pytest.mark.parametrize("buoc", [None, "", "CHAY", "chay ", "uoc_tinh", "khac"])
def test_lap_buoc_genmax_buoc_la_thi_chi_uoc_tinh(mt, buoc):
    ts, v = _gm_viec(mt, buoc, **DUYET)
    assert "--dong-y" not in dm.DANH_MUC["voice_genmax"].lap_buoc(ts, v, mt)[0].argv


@pytest.mark.parametrize("ma_ban", [["--gui-lai-ma"], ["-x"], [], "ab1", [f"A{i}" for i in range(26)], ["ab1", 2],
                                    ["ab1", "ab1"]])
def test_lap_buoc_genmax_ma_ban_hong(mt, ma_ban):
    ts, v = _gm_viec(mt, "chay", **DUYET)
    ts["ma_ban"] = ma_ban
    with pytest.raises(ThamSoLoi):
        dm.DANH_MUC["voice_genmax"].lap_buoc(ts, v, mt)


def test_khong_duong_nao_sinh_gui_lai_ma(mt):
    """Mọi argv của genmax ở cả 2 pha không có `--gui-lai-ma`; trong mã nguồn danh_muc/api chuỗi này chỉ xuất hiện
    trong mẫu CẤM `Bash(*--gui-lai-ma*)`."""
    for buoc in ("uoc_tinh", "chay"):
        ts, v = _gm_viec(mt, buoc, **DUYET)
        for b in dm.DANH_MUC["voice_genmax"].lap_buoc(ts, v, mt):
            assert not any("gui-lai" in x or "gui_lai" in x for x in b.argv), b.argv
    import ast
    goc = Path(__file__).parent / "runner"
    for f in ("danh_muc.py", "api.py", "han_muc.py"):
        cay = ast.parse((goc / f).read_text(encoding="utf-8"))
        doc = {id(n.body[0].value) for n in ast.walk(cay)
               if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
               and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        chuoi = [n.value for n in ast.walk(cay) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                 and id(n) not in doc and ("gui-lai" in n.value or "gui_lai" in n.value)]
        assert chuoi == (["Bash(*--gui-lai-ma*)"] if f == "danh_muc.py" else []), (f, chuoi)


# ---------- muse_clip / poster_len_lich: lệnh Claude + nội dung phiếu ----------

def test_lap_buoc_muse_va_poster_len_lich(mt):
    ts = _muse_ts(mt)
    v = _viec("muse_clip", ts, phien_da_tao=1, **DUYET)
    b = dm.DANH_MUC["muse_clip"].lap_buoc(ts, v, mt)
    assert len(b) == 1 and b[0].la_claude and b[0].cwd == str(mt._p)
    assert b[0].argv == dm.lenh_claude(dm.DANH_MUC["muse_clip"], v, mt)
    a = b[0].argv
    assert a[a.index("--tools") + 1] == "Read,Write,Edit,Glob,Grep,Bash" and a[a.index("--agent") + 1] == "aff-muse"
    j = a.index("--disallowedTools")
    assert "Bash(*/api/accounts*)" in a[j:] and "Bash(*/api/settings*)" in a[j:]
    tp = {"folder_id": 7, "so_video_ngay": 3}
    vp = _viec("poster_len_lich", tp, phien_da_tao=1, **DUYET)
    bp = dm.DANH_MUC["poster_len_lich"].lap_buoc(tp, vp, mt)
    assert len(bp) == 1 and bp[0].la_claude and bp[0].cwd == str(mt.thu_muc_du_lieu)
    ap = bp[0].argv
    assert ap[ap.index("--agent") + 1] == "aff-poster" and "Bash(*post_now*)" in ap[ap.index("--disallowedTools"):]
    for l in (dm.DANH_MUC["muse_clip"], dm.DANH_MUC["poster_len_lich"]):
        assert l.them_thu_muc(ts, mt) == ()


def _bash_bi_cam(cam: tuple[str, ...], lenh: str) -> bool:
    """Khớp mẫu `Bash(<glob>)` kiểu Claude Code: `*` khớp mọi ký tự (kể cả `/` và khoảng trắng)."""
    for m in cam:
        if m.startswith("Bash(") and m.endswith(")"):
            mau = "".join(".*" if c == "*" else re.escape(c) for c in m[5:-1])
            if re.fullmatch(mau, lenh, re.S):
                return True
    return False


PY_POSTER = "E:/tool/tiktok_poster_v2/.venv/Scripts/python.exe"
API = "http://127.0.0.1:8023/api/v2"


@pytest.mark.parametrize("lenh", [
    # route ghi của routers/queue.py
    f"curl -X POST {API}/queue/12/run",
    f"curl -X POST {API}/queue/12/post",
    f"curl -XPOST {API}/queue/reset-all",
    f"curl -X DELETE {API}/queue/12",
    f"curl -X DELETE '{API}/queue/pending/clear?folder_id=7'",
    f"curl -X POST {API}/queue/batch -d '{{}}'",
    f"curl -X POST {API}/queue/unstick",
    f"curl -X POST {API}/queue/random_shuffle",
    f"curl -X POST {API}/queue/12/retry",
    # core/poster_api.py
    f"curl -X POST {API}/post/direct -d @x.json",
    # settings / accounts / folders / calendar ghi
    f"curl -X PUT {API}/settings/autopost-enabled -d '{{}}'",
    f"curl -X POST {API}/settings/autopost-on",
    f"curl -X PATCH {API}/folders/7 -d '{{}}'",
    f"curl --request DELETE {API}/folders/7",
    f"curl -X POST {API}/folders/7/autogen-captions",
    f"curl -X POST {API}/folders/7/reschedule-overdue",
    f"curl -X POST {API}/accounts/3/cooldown",
    f"curl -X POST {API}/accounts/login_and_capture",
    f"curl -X POST {API}/calendar/plans -d '{{}}'",
    # hàm ghi của ApiClient (aff-poster gọi qua python -c)
    f"{PY_POSTER} -c \"from desktop.api_client import ApiClient as A; A().queue_reset_all()\"",
    f"{PY_POSTER} -c \"from desktop.api_client import ApiClient as A; A().add_to_queue({{}})\"",
    f"{PY_POSTER} -c \"from desktop.api_client import ApiClient as A; A().queue_batch([])\"",
    f"{PY_POSTER} -c \"from desktop.api_client import ApiClient as A; A().queue_retry(1)\"",
    f"{PY_POSTER} -c \"from desktop.api_client import ApiClient as A; A().set_autopost(True)\"",
    f"{PY_POSTER} -c \"from desktop.api_client import ApiClient as A; A().update_folder(7, {{}})\"",
    f"{PY_POSTER} -c \"from desktop.api_client import ApiClient as A; A().update_setting('k', 1)\"",
    f"{PY_POSTER} -c \"from desktop.api_client import ApiClient as A; A().create_calendar_plan({{}})\"",
    f"{PY_POSTER} -c \"from desktop.api_client import ApiClient as A; A().post_now(7)\"",
    f"{PY_POSTER} -c \"from desktop.api_client import ApiClient as A; A().queue_unstick()\"",
    f"{PY_POSTER} -c \"from desktop.api_client import ApiClient as A; A().archive_folder(7)\"",
])
def test_cam_poster_chan_route_ghi(lenh):
    """[P2-3] aff-poster (poster_len_lich) không được gọi route/hàm ghi nào ngoài plan_folder/batch_schedule."""
    cam = dm.DANH_MUC["poster_len_lich"].cong_cu_cam
    assert _bash_bi_cam(cam, lenh), lenh


@pytest.mark.parametrize("lenh", [
    f"curl -X POST '{API}/folders/7/plan?count=3'",
    f"curl -X POST {API}/folders/batch_schedule -d '{{\"folder_ids\":[7],\"per_day\":3}}'",
    f"{PY_POSTER} -c \"from desktop.api_client import ApiClient as A; print(A().plan_folder(7, 3))\"",
    f"{PY_POSTER} -c \"from desktop.api_client import ApiClient as A; print(A().batch_schedule([7], 3))\"",
    f"{PY_POSTER} -c \"from desktop.api_client import ApiClient as A; print(A().list_queue())\"",
    f"curl {API}/queue?folder_id=7",
    f"curl {API}/calendar/month?y=2026&m=11",
    f"{PY_POSTER} -c \"from desktop.api_client import ApiClient as A; print(A().list_folders())\"",
])
def test_cam_poster_van_cho_plan_va_doc(lenh):
    cam = dm.DANH_MUC["poster_len_lich"].cong_cu_cam
    assert not _bash_bi_cam(cam, lenh), lenh


def test_cam_poster_mau_phieu_yeu_cau_co_du():
    cam = dm.DANH_MUC["poster_len_lich"].cong_cu_cam
    for m in ("Bash(*/run*)", "Bash(*/post*)", "Bash(*reset-all*)", "Bash(*reset_all*)", "Bash(*autopost*)",
              "Bash(*-X DELETE*)", "Bash(*pending/clear*)", "Bash(*post/direct*)"):
        assert m in cam, m
    # mẫu cũ giữ nguyên
    for m in ("Bash(*post_now*)", "Bash(*post_video_direct*)", "Bash(*v2_data.db*)",
              "Edit(//E:/tool/tiktok_poster_v2/**)", "Write(//E:/tool/tiktok_poster_v2/**)"):
        assert m in cam, m


def test_noi_dung_phieu_dot_4(mt):
    ts = _muse_ts(mt)
    nd = dm.noi_dung_phieu_dot4(dm.DANH_MUC["muse_clip"], _viec("muse_clip", ts), mt)
    assert set(nd) == {"muc_tieu", "dau_vao", "duoc_ghi", "cam", "xong_khi", "them"}
    assert "2 clip" in nd["muc_tieu"] and "15 giây" in nd["muc_tieu"] and "9:16" in nd["muc_tieu"]
    for k in ("xoay_360", "cam_tay"):
        assert dm.MAU_PROMPT_MUSE[k] in nd["them"]
    for k in set(dm.MAU_PROMPT_MUSE) - {"xoay_360", "cam_tay"}:
        assert dm.MAU_PROMPT_MUSE[k] not in nd["them"]
    assert mt._p.as_posix() in nd["dau_vao"] and "/muse/" in nd["duoc_ghi"]
    tp = {"folder_id": 7, "so_video_ngay": 3}
    nd2 = dm.noi_dung_phieu_dot4(dm.DANH_MUC["poster_len_lich"], _viec("poster_len_lich", tp), mt)
    assert "folder 7" in nd2["muc_tieu"] and "3 video/ngày" in nd2["muc_tieu"]
    assert "post_now" in nd2["cam"]
    with pytest.raises(ThamSoLoi):
        dm.noi_dung_phieu_dot4(dm.DANH_MUC["voice_genmax"], _viec("voice_genmax", {}), mt)
    with pytest.raises(ThamSoLoi):                       # mẫu lạ trong DB → không chèn chữ tuỳ ý vào phiếu
        dm.noi_dung_phieu_dot4(dm.DANH_MUC["muse_clip"], _viec("muse_clip", dict(ts, mau=["la"])), mt)


# ---------- đợt 6: sửa video (docs/sua-video.md §7, D10) ----------
# Dự án GIẢ luồng C dựng bằng chính helper của test lõi B-6 (đường dẫn gốc cũ + .done.json khớp) — không đụng dữ liệu thật.

import test_runner_sua_video as tsv  # noqa: E402
from runner import sua_video as sv  # noqa: E402
from runner.kho_viec import KhoViec  # noqa: E402

TEN_SUA = "50oto2809_061.mp4"
CHU_WEB = "--project X:/khac; rm -rf chữ web"         # chữ tự do: chỉ được nằm trong file bản sửa, không vào argv


def dung_du_an_c(p: Path) -> None:
    """Luồng C tối thiểu trong `p`: cuts/ 13 vai, 1 take có .words.json, output_poster/render_batch.json (gốc cũ),
    3 video + .done.json khớp size/mtime."""
    G = tsv.GOC_CU
    tsv._kho_clip(p)
    tsv._take(p / "takes" / "0923 (1)(1)-85.mp4", take_idx=1)
    take = G + r"\takes\0923 (1)(1)-85.mp4"
    d = p / "output_poster"

    def plan(pid):
        return {"plan_id": pid, "take_path": take, "take_idx": 1, "duration": 6.0, "seed": 7,
                "segments": [tsv._seg("BASE", 0.0, 6.0, take, "take"),
                             tsv._seg("OVL", 1.0, 3.0, G + r"\cuts\raw-4_001_proof_canh-1.mp4", "proof", 3.0),
                             tsv._seg("OVL", 3.0, 4.5, G + r"\cuts\raw-5_001_detail_canh-1.mp4", "detail", 3.0)]}

    tsv._ghi_json(d / "render_batch.json", {"version": 1, "plans": [plan(60), plan(61), plan(62)],
                                            "options": {"workers": 2}, "config": {"prefix": "50oto2809"}})
    for pid in (60, 61, 62):
        f = tsv._ghi_bytes(d / f"50oto2809_{pid:03d}.mp4", 1000 + pid, tsv.T_VIDEO)
        tsv._ghi_json(d / f"50oto2809_{pid:03d}.done.json",
                      {"key": "k", "output": ["cu", f.stat().st_size, f.stat().st_mtime_ns]})


def video_sua(p: Path, ten: str = TEN_SUA) -> "sv.VideoSua":
    return next(v for v in sv.ds_video_sua(p, p.parent) if v.ten == ten)


def ban_sua_hop_le(p: Path, ten: str = TEN_SUA, text: str = CHU_WEB) -> dict:
    """Bản sửa chuẩn hoá thật (qua sua_video.kiem_ban_sua): sửa 1 câu + đổi 1 clip."""
    v = video_sua(p, ten)
    ct = sv.lap_chi_tiet(p, v, sv.tra_ban_ghi(p, v))
    body = {"sua_luc": v.sua_luc, "phu_de_sha": ct["phu_de"]["sha"], "phu_de": [{"i": 1, "text": text}],
            "doi_clip": [{"seg": 1, "clip": "raw-4_002_proof_canh-2.mp4"}], "boi": "nhan"}
    return sv.kiem_ban_sua(body, ct)


@pytest.fixture
def sua(mt, tmp_path, monkeypatch):
    """Dự án luồng C trong mt._p + Python engine giả + khoá máy trỏ thư mục tạm."""
    dung_du_an_c(mt._p)
    eng = tmp_path / "engine"
    (eng / ".venv" / "Scripts").mkdir(parents=True)
    py = eng / ".venv" / "Scripts" / "python.exe"
    py.write_bytes(b"")
    monkeypatch.setenv("KHO_PYTHON_ENGINE", str(py))
    monkeypatch.setenv("KHO_ENGINE_DIR", str(eng))
    monkeypatch.setenv("AUTOVIDEO_KHOA_MAY", str(tmp_path / "khoa_may" / ".render-may.lock"))
    v = video_sua(mt._p)
    ts = {"uid": UID, "du_an": du_an.ma_du_an(mt._p), "ma_video": v.ma_video}
    return {"p": mt._p, "v": v, "ts": ts, "py": py, "eng": eng, "khoa_may": tmp_path / "khoa_may" / ".render-may.lock"}


def test_danh_muc_sua_video_khung():
    S, H = dm.DANH_MUC["sua_video"], dm.DANH_MUC["hoan_tac_sua"]
    for l in (S, H):
        assert l.dot == 4 and l.lan_chay == "gpu" and l.ton_tien is False and l.agent is None
        assert l.tu_chay_lai is True and l.tai_nguyen == frozenset() and l.bo_cong_cu == ()
        assert l.trang_thai_dau({}) == ("cho", "chay")
        assert l.tinh_khoa({"ma_video": "a" * 16, "uid": UID}) == "a" * 16      # khoá trùng = ma_video
        assert dm.lay_loai(l.ma, 4) is l
        with pytest.raises(ThamSoLoi):
            dm.lay_loai(l.ma, 3)
    assert (S.het_gio_s, H.het_gio_s) == (20 * 60, 10 * 60)
    with pytest.raises(ThamSoLoi):
        dm.lay_loai("taovideo", 4)                     # dot=4 không mở taovideo


def test_kiem_tham_so_sua_video(sua, mt):
    K = dm.DANH_MUC["sua_video"].kiem_tham_so
    ts = {**sua["ts"], "ban_sua": "b" + "0" * 16}
    assert K(dict(ts), mt) == ts
    sai = [dict(ts, la=1), dict(ts, uid="123"), dict(ts, du_an="ABCDEF012345"), dict(ts, ma_video="A" * 16),
           dict(ts, ban_sua="b" + "0" * 15), dict(ts, ban_sua="x" + "0" * 16), dict(ts, ma_video="0" * 16),
           {k: v for k, v in ts.items() if k != "ban_sua"}, dict(ts, du_an="0" * 12), dict(ts, uid=UID2)]
    for s in sai:
        with pytest.raises(ThamSoLoi):
            K(s, mt)


def test_kiem_tham_so_hoan_tac_sua(sua, mt):
    K = dm.DANH_MUC["hoan_tac_sua"].kiem_tham_so
    ts = {**sua["ts"], "viec_goc": ID}
    assert K(dict(ts), mt) == ts
    for s in (dict(ts, viec_goc="j123"), dict(ts, viec_goc=ID.upper()), dict(ts, ban_sua="b" + "0" * 16),
              {k: v for k, v in ts.items() if k != "viec_goc"}, dict(ts, ma_video="f" * 16)):
        with pytest.raises(ThamSoLoi):
            K(s, mt)


def test_dieu_kien_truoc_sua_video(sua, mt, monkeypatch):
    import time as _t
    for ma in SUA:
        D = dm.DANH_MUC[ma].dieu_kien_truoc
        ts = dict(sua["ts"])
        assert D(ts, mt) is None
        mt._st["ffmpeg"] = True
        assert D(ts, mt) == "ban"
        mt._st["ffmpeg"] = False
        # khoá render của dự án / khoá máy còn tươi (< 180 s) → ban; khoá cũ (bỏ rơi) → không chặn
        for khoa in (sua["p"] / ".render.lock", sua["khoa_may"]):
            khoa.parent.mkdir(parents=True, exist_ok=True)
            khoa.write_text('{"batch":"x"}', encoding="utf-8")
            assert D(ts, mt) == "ban", khoa
            cu = _t.time() - 300
            os.utime(khoa, (cu, cu))
            assert D(ts, mt) is None, khoa
            khoa.unlink()
        # Python engine không có → việc tay, nêu rõ đường dẫn
        monkeypatch.setenv("KHO_PYTHON_ENGINE", str(sua["eng"] / "khong_co.exe"))
        r = D(ts, mt)
        assert isinstance(r, CanNguoiDung) and r.loai == "viec_tay" and "Python" in r.noi_dung
        monkeypatch.setenv("KHO_PYTHON_ENGINE", str(sua["py"]))
    # dự án biến mất → việc tay
    sua["p"].rename(sua["p"].with_name("doi_ten"))
    assert isinstance(dm.DANH_MUC["sua_video"].dieu_kien_truoc(dict(sua["ts"]), mt), CanNguoiDung)


def test_mac_dinh_duong_dan_engine(monkeypatch):
    for k in ("KHO_PYTHON_ENGINE", "KHO_ENGINE_DIR", "AUTOVIDEO_KHOA_MAY"):
        monkeypatch.delenv(k, raising=False)
    assert dm.python_engine() == Path(r"F:\auto video oneshot\.venv\Scripts\python.exe")
    assert dm.thu_muc_engine() == Path(r"F:\auto video oneshot")
    assert dm.khoa_may_render() == Path(r"E:\oneshottramcanh\.render-may.lock")


def _luu_ban(mt, sua, noi: dict, id_: str | None = None) -> str:
    id_ = id_ or sv.ma_ban_sua(noi)
    kho = KhoViec(Path(mt.thu_muc_du_lieu) / "runner.db", lambda: BAY_GIO)
    kho.luu_ban_sua(id_, UID, sua["ts"]["du_an"], sua["ts"]["ma_video"], noi, "nhan")
    return id_


def test_lap_buoc_sua_video_ghi_file_va_argv_khong_co_chu_web(sua, mt):
    noi = ban_sua_hop_le(sua["p"])
    assert noi["phu_de"] == [{"i": 1, "text": CHU_WEB}]
    bs = _luu_ban(mt, sua, noi)
    ts = {**sua["ts"], "ban_sua": bs}
    b = dm.DANH_MUC["sua_video"].lap_buoc(ts, _viec("sua_video", ts, session_id=None), mt)
    assert len(b) == 1 and b[0].ten == "sua_video" and not b[0].la_claude and b[0].stdin is None
    f = Path(mt.thu_muc_du_lieu) / "sua" / f"{bs}.json"
    assert b[0].argv == [str(sua["py"]), str(Path(dm.__file__).with_name("sua_video_engine.py")), "ap-dung",
                         "--project", str(sua["p"]), "--thu-muc", "output_poster", "--video", TEN_SUA,
                         "--ban-sua", str(f), "--viec", ID]
    assert b[0].cwd == str(sua["eng"]) and b[0].het_gio_s == 20 * 60
    assert b[0].env_them == {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"} and b[0].hien_cua_so is False
    # chữ tự do CHỈ nằm trong file bản sửa (JSON chuẩn = đúng nội dung bảng), không mảnh nào lọt vào argv
    assert f.read_text(encoding="utf-8") == dm.tham_so_chuan(noi)
    assert sv.ma_ban_sua(json.loads(f.read_text(encoding="utf-8"))) == bs
    for a in b[0].argv:
        assert "chữ web" not in a and "rm -rf" not in a and "X:/khac" not in a
    assert not list((Path(mt.thu_muc_du_lieu) / "sua").glob("*.tmp"))


def test_lap_buoc_sua_video_tu_choi_ban_sua_hong(sua, mt):
    S = dm.DANH_MUC["sua_video"]
    noi = ban_sua_hop_le(sua["p"])
    # chưa có trong bảng
    ts = {**sua["ts"], "ban_sua": sv.ma_ban_sua(noi)}
    with pytest.raises(ThamSoLoi):
        S.lap_buoc(ts, _viec("sua_video", ts), mt)
    # nội dung trong DB không khớp mã (DB bị sửa tay) → không chạy
    gia = "b" + "9" * 16
    _luu_ban(mt, sua, noi, gia)
    ts2 = {**sua["ts"], "ban_sua": gia}
    with pytest.raises(ThamSoLoi):
        S.lap_buoc(ts2, _viec("sua_video", ts2), mt)
    # bản của video khác
    noi3 = dict(noi, ma_video="c" * 16)
    bs3 = _luu_ban(mt, sua, noi3)
    ts3 = {**sua["ts"], "ban_sua": bs3}
    with pytest.raises(ThamSoLoi):
        S.lap_buoc(ts3, _viec("sua_video", ts3), mt)
    # id việc sai định dạng
    bs = _luu_ban(mt, sua, noi)
    ts4 = {**sua["ts"], "ban_sua": bs}
    with pytest.raises(ThamSoLoi):
        S.lap_buoc(ts4, _viec("sua_video", ts4, id="--x"), mt)
    assert not (Path(mt.thu_muc_du_lieu) / "sua" / f"{gia}.json").exists()


def test_lap_buoc_hoan_tac_sua(sua, mt):
    ts = {**sua["ts"], "viec_goc": "j20261117080000wxyz"}
    b = dm.DANH_MUC["hoan_tac_sua"].lap_buoc(ts, _viec("hoan_tac_sua", ts), mt)
    assert len(b) == 1 and b[0].het_gio_s == 10 * 60 and b[0].cwd == str(sua["eng"])
    assert b[0].argv == [str(sua["py"]), str(Path(dm.__file__).with_name("sua_video_engine.py")), "hoan-tac",
                         "--project", str(sua["p"]), "--thu-muc", "output_poster", "--video", TEN_SUA,
                         "--viec-goc", "j20261117080000wxyz", "--viec", ID]
    with pytest.raises(ThamSoLoi):
        dm.DANH_MUC["hoan_tac_sua"].lap_buoc(dict(ts, viec_goc="-x"), _viec("hoan_tac_sua", ts), mt)


def _nhat_ky(p: Path, id_viec: str, **kw) -> Path:
    f = p / "output_poster" / "_sua" / f"{id_viec}.json"
    nk = {"viec": id_viec, "ban_sua": "b" + "0" * 16, "luong": "C", "video": f"output_poster/{TEN_SUA}",
          "buoc": "xong", "cu": {"size": 1, "mtime_ns": 2}, "moi": None}
    nk.update(kw)
    tsv._ghi_json(f, nk)
    return f


def _st(p: Path) -> dict:
    s = (p / "output_poster" / TEN_SUA).stat()
    return {"size": s.st_size, "mtime_ns": s.st_mtime_ns}


def test_kiem_dau_ra_sua_video(sua, mt):
    S = dm.DANH_MUC["sua_video"]
    p = sua["p"]
    ts = {**sua["ts"], "ban_sua": "b" + "0" * 16}
    v = _viec("sua_video", ts)
    assert S.kiem_dau_ra(ts, v, mt) == "chua"                                   # chưa có nhật ký
    _nhat_ky(p, ID, buoc="render", moi=None)
    assert S.kiem_dau_ra(ts, v, mt) == "chua"                                   # dở dang → chạy lại làm nốt
    _nhat_ky(p, ID, buoc="xong", moi=_st(p))
    assert S.kiem_dau_ra(ts, v, mt) == "xong"
    _nhat_ky(p, ID, buoc="xong", moi={"size": 1, "mtime_ns": 2})
    assert S.kiem_dau_ra(ts, v, mt) == "khong_ro"                               # xong mà file khác → không đoán
    _nhat_ky(p, ID, buoc="xong", moi=_st(p), video="../ngoai.mp4")
    assert S.kiem_dau_ra(ts, v, mt) == "khong_ro"                               # đường dẫn thoát khỏi dự án
    _nhat_ky(p, ID, buoc="xong", moi=_st(p), viec="j20261117080000zzzz")
    assert S.kiem_dau_ra(ts, v, mt) == "khong_ro"                               # nhật ký của việc khác
    (p / "output_poster" / "_sua" / f"{ID}.json").write_text("{hỏng", encoding="utf-8")
    assert dm.kiem_dau_ra_an_toan(S, ts, v, mt) == "khong_ro"
    # luồng A: nhật ký nằm cạnh bản gốc output_daonguoc/_sua
    (p / "output_poster" / "_sua" / f"{ID}.json").unlink()
    tsv._ghi_json(p / "output_daonguoc" / "_sua" / f"{ID}.json",
                  {"viec": ID, "video": f"output_poster/{TEN_SUA}", "buoc": "xong", "moi": _st(p)})
    assert S.kiem_dau_ra(ts, v, mt) == "xong"
    # dự án biến mất → khong_ro
    p.rename(p.with_name("doi_ten"))
    assert S.kiem_dau_ra(ts, v, mt) == "khong_ro"


def test_doi_soat_sau_khoi_dong_sua_video(sua, mt):
    """§6.3 'chạy lại sau khi bị ngắt': chua → về cho (CÙNG id, engine đọc nhật ký làm nốt); khong_ro → loi."""
    S = dm.DANH_MUC["sua_video"]
    assert dm.quyet_dinh_sau_khoi_dong(_viec("sua_video", {}), "chua", S)[0] == "cho"
    assert dm.quyet_dinh_sau_khoi_dong(_viec("sua_video", {}, lan_thu=3), "chua", S)[0] == "loi"
    assert dm.quyet_dinh_sau_khoi_dong(_viec("sua_video", {}), "khong_ro", S)[0] == "loi"


def test_kiem_dau_ra_hoan_tac_sua(sua, mt):
    H = dm.DANH_MUC["hoan_tac_sua"]
    p = sua["p"]
    goc = "j20261117080000wxyz"
    ts = {**sua["ts"], "viec_goc": goc}
    v = _viec("hoan_tac_sua", ts)
    assert H.kiem_dau_ra(ts, v, mt) == "khong_ro"                               # không có nhật ký việc gốc
    hien = _st(p)
    _nhat_ky(p, goc, cu=hien, moi={"size": 9, "mtime_ns": 9})
    assert H.kiem_dau_ra(ts, v, mt) == "xong"                                   # file đã là bản cũ
    _nhat_ky(p, ID, buoc="nguon")                                               # nhật ký hoàn tác còn dở
    assert H.kiem_dau_ra(ts, v, mt) == "chua"
    (p / "output_poster" / "_sua" / f"{ID}.json").unlink()
    _nhat_ky(p, goc, cu={"size": 9, "mtime_ns": 9}, moi=hien)
    assert H.kiem_dau_ra(ts, v, mt) == "chua"                                   # vẫn là bản sửa → làm lại
    _nhat_ky(p, goc, cu={"size": 9, "mtime_ns": 9}, moi={"size": 8, "mtime_ns": 8})
    assert H.kiem_dau_ra(ts, v, mt) == "khong_ro"                               # file lạ → không đoán


# ---------- B-L1: poster_bo_loai + chặn poster_len_lich khi folder còn video Loại (docs/giao-dien-menu-trai.md §4.9) ----------

T_BL = 1_763_000_000


def _video_bl(f: Path, ts: int = T_BL) -> Path:
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"mp4")
    os.utime(f, (ts, ts))
    return f


def _noi_duyet(*muc) -> str:
    ds = [{"goc": g, "ten": t, "sua_luc": T_BL, "mb": 0.1, "ket_qua": kq, "gop_y": "", "boi": "Nhân", "luc": "x"}
          for g, t, kq in muc]
    return json.dumps({"videos": ds})


# [P1-1] Web (Worker) ghi duyet.json/info.json THẲNG lên GitHub: mô phỏng bằng remote bare tạm + một bản clone "web".
# Repo kho máy nhà (mt.repo_kho) KHÔNG được pull: cây làm việc giữ bản cũ, runner phải đọc bản fetch mới nhất.
_GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


def _git(cwd: Path, *args: str) -> str:
    import subprocess
    r = subprocess.run(["git", *_GIT_ID, *args], cwd=cwd, capture_output=True, timeout=60, check=False)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return r.stdout.decode("utf-8", "replace")


@pytest.fixture
def kho_git(mt, tmp_path):
    repo = Path(mt.repo_kho)
    tu_xa = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(tu_xa))
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "dau")
    _git(repo, "remote", "add", "origin", str(tu_xa))
    _git(repo, "push", "-q", "-u", "origin", "main")
    web = tmp_path / "web"
    _git(tmp_path, "clone", "-q", str(tu_xa), str(web))

    class G:
        pass
    g = G()
    g.tu_xa, g.web, g.repo = tu_xa, web, repo
    g.head = _git(repo, "rev-parse", "HEAD").strip()
    return g


def _web_ghi(g, ten: str, noi: str, uid: str = UID) -> None:
    f = g.web / "data" / uid / ten
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(noi, encoding="utf-8")
    _git(g.web, "add", "-A")
    _git(g.web, "commit", "-q", "-m", f"web {ten}")
    _git(g.web, "push", "-q", "origin", "main")


def _cay_lam_viec_nguyen(g) -> bool:
    return _git(g.repo, "rev-parse", "HEAD").strip() == g.head and _git(g.repo, "status", "--porcelain") == ""


def _duyet_bl(g, *muc) -> None:
    _web_ghi(g, "duyet.json", _noi_duyet(*muc))


def test_poster_bo_loai_thuoc_tinh(mt):
    L = dm.DANH_MUC["poster_bo_loai"]
    assert (L.ma, L.dot, L.lan_chay, L.ton_tien, L.tu_chay_lai, L.agent) == ("poster_bo_loai", 3, "nhe", False,
                                                                            True, None)
    assert L.tai_nguyen == frozenset({"poster", "kho"})
    assert [t["ten"] for t in L.tham_so] == ["uid"]
    assert L.kiem_tham_so({"uid": UID}, mt) == {"uid": UID}
    for sai in ({}, {"uid": UID[:-1]}, {"uid": UID, "goc": "E:/x"}, {"uid": UID, "du_an": "a" * 12}):
        with pytest.raises(ThamSoLoi):
            L.kiem_tham_so(sai, mt)
    assert L.tinh_khoa({"uid": UID}) == UID
    assert L.trang_thai_dau({"uid": UID}) == ("cho", "chay")
    assert dm.lay_loai("poster_bo_loai", 3) is L
    # [FX-B3 P3-6] chỉ đọc ref remote (fetch) → không đòi data/ sạch; chỉ chờ khi git kho đang bận
    assert L.dieu_kien_truoc is dm._dk_bo_loai
    assert L.dieu_kien_truoc({"uid": UID}, mt) is None
    mt._st["kho"] = "ban"
    assert L.dieu_kien_truoc({"uid": UID}, mt) == "ban"
    mt._st["kho"] = CanNguoiDung("viec_tay", "data/ có thay đổi chưa commit")
    assert L.dieu_kien_truoc({"uid": UID}, mt) is None
    mt._st["kho"] = None
    with pytest.raises(ThamSoLoi):
        L.dieu_kien_truoc({"uid": "../x"}, mt)
    # khởi động lại khi đang chạy, đầu ra chưa đủ → tự chạy lại (miễn phí, idempotent)
    assert dm.quyet_dinh_sau_khoi_dong(_viec("poster_bo_loai", {"uid": UID}), "chua", L)[0] == "cho"


def test_poster_bo_loai_lap_buoc(mt):
    """[P1-1][P2-2] Một bước: bo_loai.py --tu-remote (git fetch + đọc ref upstream). KHÔNG còn kho.py xem
    (= git pull --rebase --autostash trên cây làm việc có code chưa commit)."""
    L = dm.DANH_MUC["poster_bo_loai"]
    ts = {"uid": UID}
    b = L.lap_buoc(ts, _viec("poster_bo_loai", ts), mt)
    assert [x.ten for x in b] == ["bo_loai"]
    repo = Path(mt.repo_kho)
    goc = [x for g in mt.gocs for x in ("--goc", Path(g).as_posix())]
    assert b[0].argv == [dm.PYTHON, "-B", "-I", str(dm.BO_LOAI), "--repo-kho", repo.as_posix(), "--uid", UID, *goc,
                         "--tu-remote"]
    assert b[0].cwd == str(repo) and not b[0].la_claude
    assert dm.BO_LOAI.name == "bo_loai.py" and dm.BO_LOAI.is_file()
    assert "--xem" not in b[0].argv and not any("kho.py" in x for x in b[0].argv)
    with pytest.raises(ThamSoLoi):
        L.lap_buoc({"uid": "../x"}, _viec("poster_bo_loai", {"uid": "../x"}), mt)


def test_poster_bo_loai_buoc_chay_that_doc_ban_moi(mt, kho_git):
    """Chạy đúng argv của bước (script độc lập, -I) trên repo git tạm: dời theo bản web vừa ghi, cây làm việc nguyên."""
    import subprocess
    L = dm.DANH_MUC["poster_bo_loai"]
    ts = {"uid": UID}
    op = mt._p / "output_poster"
    _video_bl(op / "a.mp4")
    _duyet_bl(kho_git, (Path(mt.gocs[0]).as_posix(), "a.mp4", "loai"))
    b = L.lap_buoc(ts, _viec("poster_bo_loai", ts), mt)[0]
    argv = [sys.executable if x == dm.PYTHON else x for x in b.argv]
    r = subprocess.run(argv, cwd=b.cwd, capture_output=True, timeout=120, check=False,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert (op / "_loai" / "a.mp4").is_file()
    assert _cay_lam_viec_nguyen(kho_git)


def test_poster_bo_loai_kiem_dau_ra(mt, kho_git):
    from runner import bo_loai
    L = dm.DANH_MUC["poster_bo_loai"]
    ts = {"uid": UID}
    v = _viec("poster_bo_loai", ts)
    op = mt._p / "output_poster"
    _video_bl(op / "a.mp4")
    _video_bl(op / "b.mp4")
    assert L.kiem_dau_ra(ts, v, mt) == "xong"                                    # chưa chấm gì → không có gì để dời
    goc_op = Path(mt.gocs[0]).as_posix()
    _duyet_bl(kho_git, (goc_op, "a.mp4", "loai"), (goc_op, "b.mp4", "dat"))
    assert L.kiem_dau_ra(ts, v, mt) == "chua"                                    # đọc bản remote, không bản cây cũ
    argv = ["--repo-kho", str(mt.repo_kho), "--uid", UID, *[x for g in mt.gocs for x in ("--goc", str(g))],
            "--tu-remote"]
    assert bo_loai.main(argv) == 0
    assert (op / "_loai" / "a.mp4").is_file() and L.kiem_dau_ra(ts, v, mt) == "xong"
    # bỏ chấm hẳn (Worker xoá mục) → video ở lại _loai/ (BO_QUA, cần chấm lại Đạt): không phải việc tự làm được
    _duyet_bl(kho_git, (goc_op, "b.mp4", "dat"))
    assert L.kiem_dau_ra(ts, v, mt) == "xong"
    _duyet_bl(kho_git, (goc_op, "a.mp4", "dat"), (goc_op, "b.mp4", "dat"))        # chấm lại Đạt → phải trả về
    assert L.kiem_dau_ra(ts, v, mt) == "chua"
    _web_ghi(kho_git, "duyet.json", "{hỏng")
    assert L.kiem_dau_ra(ts, v, mt) == "khong_ro"
    assert dm.kiem_dau_ra_an_toan(L, ts, v, mt) == "khong_ro"
    _git(kho_git.repo, "remote", "set-url", "origin", str(kho_git.tu_xa.parent / "khong_co.git"))
    assert L.kiem_dau_ra(ts, v, mt) == "khong_ro"                                 # fetch lỗi → không đoán
    assert _cay_lam_viec_nguyen(kho_git)


def _mt_folder(mt, duong_dan):
    f = {"id": 7, "name": "Bình nước"}
    if duong_dan is not None:
        f["duong_dan"] = duong_dan
    mt.doc_folder_poster = lambda: [f, {"id": 9, "name": "Ví", "duong_dan": "F:/khac/output"}]


def test_dk_poster_len_lich_chan_khi_folder_con_video_loai(mt, kho_git):
    P = dm.DANH_MUC["poster_len_lich"].dieu_kien_truoc
    ts = {"folder_id": 7, "so_video_ngay": 3}
    op = mt._p / "output_poster"
    for t in ("a.mp4", "b.mp4", "c.mp4"):
        _video_bl(op / t)
    goc_op = Path(mt.gocs[0]).as_posix()
    _duyet_bl(kho_git, (goc_op, "a.mp4", "loai"), (goc_op, "b.mp4", "loai"), (goc_op, "c.mp4", "dat"))
    for dd in (str(op), op.as_posix(), str(op).replace("/", "\\")):
        _mt_folder(mt, dd)
        r = P(ts, mt)
        assert isinstance(r, CanNguoiDung) and r.loai == "viec_tay", dd
        assert "2 video bị Loại" in r.noi_dung and "Gỡ video Loại" in r.noi_dung and "Xin duyệt lại" in r.noi_dung
        assert "a.mp4" not in r.noi_dung                       # không nhúng tên file (dữ liệu người dùng)
    # hết Loại (đã dời sang _loai/ hoặc chấm lại) → không chặn
    _duyet_bl(kho_git, (goc_op, "a.mp4", "dat"), (goc_op, "c.mp4", "dat"), (goc_op, "b.mp4", "dat"))
    assert P(ts, mt) is None
    # Poster tắt vẫn báo Poster trước
    _duyet_bl(kho_git, (goc_op, "a.mp4", "loai"))
    mt._cong[8023] = False
    r = P(ts, mt)
    assert isinstance(r, CanNguoiDung) and "8023" in r.noi_dung
    mt._cong[8023] = True
    # duyet.json hỏng → chặn (không đoán là sạch)
    _web_ghi(kho_git, "duyet.json", "{hỏng")
    r = P(ts, mt)
    assert isinstance(r, CanNguoiDung) and "duyet.json" in r.noi_dung
    assert _cay_lam_viec_nguyen(kho_git)


def test_dk_poster_len_lich_doc_ban_moi_khong_doc_cay_cu(mt, kho_git):
    """[P1-1] Việc ở cho_duyet; người dùng chấm Loại trên web (ghi thẳng GitHub); repo máy nhà chưa pull.
    Điều kiện phải thấy Loại (fetch + đọc ref upstream), và KHÔNG pull/đổi cây làm việc."""
    P = dm.DANH_MUC["poster_len_lich"].dieu_kien_truoc
    ts = {"folder_id": 7, "so_video_ngay": 3}
    op = mt._p / "output_poster"
    _video_bl(op / "a.mp4")
    goc_op = Path(mt.gocs[0]).as_posix()
    _mt_folder(mt, str(op))
    assert P(ts, mt) is None                                     # chưa chấm
    # cây làm việc có bản cũ (Đạt) — bản này KHÔNG được dùng
    (Path(mt.repo_kho) / "data" / UID / "duyet.json").write_text(_noi_duyet((goc_op, "a.mp4", "dat")),
                                                                 encoding="utf-8")
    _duyet_bl(kho_git, (goc_op, "a.mp4", "loai"))
    r = P(ts, mt)
    assert isinstance(r, CanNguoiDung) and "1 video bị Loại" in r.noi_dung
    assert _git(kho_git.repo, "rev-parse", "HEAD").strip() == kho_git.head
    assert (Path(mt.repo_kho) / "data" / UID / "duyet.json").read_text(encoding="utf-8") == \
        _noi_duyet((goc_op, "a.mp4", "dat"))


def test_dk_poster_len_lich_goc_khac_hoa_thuong(mt, kho_git):
    """[P2-1] KHO_VIDEO_GOC (video_server) viết khác hoa/thường, gạch so với gocs của runner vẫn khớp."""
    P = dm.DANH_MUC["poster_len_lich"].dieu_kien_truoc
    ts = {"folder_id": 7, "so_video_ngay": 3}
    op = mt._p / "output_poster"
    _video_bl(op / "a.mp4")
    _duyet_bl(kho_git, (str(mt.gocs[0]).swapcase().replace("/", "\\"), "a.mp4", "loai"))
    _mt_folder(mt, str(op))
    r = P(ts, mt)
    assert isinstance(r, CanNguoiDung) and "1 video bị Loại" in r.noi_dung


def test_dk_poster_len_lich_fetch_loi_thi_viec_tay(mt, kho_git, monkeypatch):
    """[P1-1] fetch lỗi / quá giờ / không có git → việc tay, không cho qua. Thông báo không lộ đường dẫn."""
    from runner import bo_loai
    P = dm.DANH_MUC["poster_len_lich"].dieu_kien_truoc
    ts = {"folder_id": 7, "so_video_ngay": 3}
    _video_bl(mt._p / "output_poster" / "a.mp4")
    _mt_folder(mt, str(mt._p / "output_poster"))
    _git(kho_git.repo, "remote", "set-url", "origin", str(kho_git.tu_xa.parent / "khong_co.git"))
    r = P(ts, mt)
    assert isinstance(r, CanNguoiDung) and r.loai == "viec_tay" and "git fetch" in r.noi_dung
    assert str(kho_git.tu_xa.parent) not in r.noi_dung and kho_git.tu_xa.parent.as_posix() not in r.noi_dung
    _git(kho_git.repo, "remote", "set-url", "origin", str(kho_git.tu_xa))
    assert P(ts, mt) is None

    def treo(argv, het_gio_s, *, env=None):
        raise bo_loai.LoiGit(f"git quá {het_gio_s:g} giây (mạng treo / chờ đăng nhập?)")
    monkeypatch.setattr(bo_loai, "_chay_gioi_han", treo)
    r = P(ts, mt)
    assert isinstance(r, CanNguoiDung) and r.loai == "viec_tay"


def test_dk_poster_len_lich_khoa_ref_thi_cho(mt, kho_git):
    """[FX-B2 P2-2] fetch vướng khoá ref (kho.py tay đang pull/push) → 'ban' (vòng chạy hoãn, thử lại), không việc tay."""
    P = dm.DANH_MUC["poster_len_lich"].dieu_kien_truoc
    ts = {"folder_id": 7, "so_video_ngay": 3}
    _video_bl(mt._p / "output_poster" / "a.mp4")
    _mt_folder(mt, str(mt._p / "output_poster"))
    _duyet_bl(kho_git, (Path(mt.gocs[0]).as_posix(), "a.mp4", "dat"))     # có commit mới → fetch phải ghi ref
    khoa = kho_git.repo / ".git" / "refs" / "remotes" / "origin" / "main.lock"
    khoa.write_text("", encoding="utf-8")
    try:
        assert P(ts, mt) == "ban"
    finally:
        khoa.unlink()
    assert P(ts, mt) is None


def test_poster_len_lich_khong_giu_mutex_kho():
    """[FX-B2 P2-2, trưởng phòng chốt] Không giữ mutex `kho` (giữ ≤30' sẽ chặn link mới/douyin/bo_loai): fetch chỉ
    ghi ref; đụng khoá ref → 'ban' (test_dk_poster_len_lich_khoa_ref_thi_cho)."""
    assert dm.DANH_MUC["poster_len_lich"].tai_nguyen == frozenset({"poster"})


def test_dk_poster_len_lich_khong_phai_repo_git_thi_viec_tay(mt):
    P = dm.DANH_MUC["poster_len_lich"].dieu_kien_truoc
    _video_bl(mt._p / "output_poster" / "a.mp4")
    _mt_folder(mt, str(mt._p / "output_poster"))
    r = P({"folder_id": 7, "so_video_ngay": 3}, mt)
    assert isinstance(r, CanNguoiDung) and r.loai == "viec_tay"


def test_dk_poster_len_lich_ngung_dang(mt, kho_git):
    """[P2-3] SP gắn ⛔ Ngừng đăng (info.json bản mới nhất) → việc tay, kể cả khi không có video Loại."""
    P = dm.DANH_MUC["poster_len_lich"].dieu_kien_truoc
    ts = {"folder_id": 7, "so_video_ngay": 3}
    _video_bl(mt._p / "output_poster" / "a.mp4")
    _mt_folder(mt, str(mt._p / "output_poster"))
    _web_ghi(kho_git, "info.json", json.dumps({"id": UID, "ngung_dang": False}))
    assert P(ts, mt) is None
    _web_ghi(kho_git, "info.json", json.dumps({"id": UID, "ngung_dang": True}))
    r = P(ts, mt)
    assert isinstance(r, CanNguoiDung) and r.loai == "viec_tay"
    assert r.noi_dung == "Sản phẩm đang gắn ⛔ Ngừng đăng — gỡ thẻ trước khi lên lịch"
    # cây làm việc không có thẻ (bản cũ) vẫn bị chặn: đọc bản mới nhất
    assert not (Path(mt.repo_kho) / "data" / UID / "info.json").exists() and _cay_lam_viec_nguyen(kho_git)
    # info.json hỏng → chặn (không đoán là không có thẻ)
    _web_ghi(kho_git, "info.json", "{hỏng")
    r = P(ts, mt)
    assert isinstance(r, CanNguoiDung) and "info.json" in r.noi_dung
    _web_ghi(kho_git, "info.json", "[]")
    r = P(ts, mt)
    assert isinstance(r, CanNguoiDung) and "info.json" in r.noi_dung


def test_dk_poster_len_lich_ngung_dang_folder_creator(mt, kho_git):
    """[FX-B2 P2-3] Folder creator `<dự án UID>/compose_output` (day_poster.py ưu tiên) — và cả folder ở gốc lạ —
    vẫn bị chặn khi SP gắn ⛔: UID lấy từ thư mục cha với MỌI thư mục con, kiểm Ngừng đăng TRƯỚC đếm Loại."""
    P = dm.DANH_MUC["poster_len_lich"].dieu_kien_truoc
    ts = {"folder_id": 7, "so_video_ngay": 3}
    _video_bl(mt._p / "compose_output" / "a.mp4")
    _web_ghi(kho_git, "info.json", json.dumps({"id": UID, "ngung_dang": True}))
    for dd in (str(mt._p / "compose_output"), f"X:/o_khac/SP {UID}/output_poster", str(mt._p / "output_poster")):
        _mt_folder(mt, dd)
        r = P(ts, mt)
        assert isinstance(r, CanNguoiDung) and r.noi_dung == dm.TB_NGUNG_DANG, dd
    _web_ghi(kho_git, "info.json", json.dumps({"id": UID, "ngung_dang": False}))
    # compose_output không đếm Loại (chỉ output_poster/output) → qua
    _duyet_bl(kho_git, (Path(mt.gocs[0]).as_posix(), "a.mp4", "loai"))
    _mt_folder(mt, str(mt._p / "compose_output"))
    assert P(ts, mt) is None


def test_dk_poster_len_lich_folder_ngoai_kho_khong_chan(mt):
    P = dm.DANH_MUC["poster_len_lich"].dieu_kien_truoc
    ts = {"folder_id": 7, "so_video_ngay": 3}
    _video_bl(mt._p / "compose_output" / "a.mp4")
    for dd in (None, "", "F:/creator/output", str(mt._p), "F:/creator 9" + UID + "/output"):
        _mt_folder(mt, dd)
        assert P(ts, mt) is None, dd                          # không nhận ra UID → không cần git, không chặn


def test_dk_poster_len_lich_khong_doc_duoc_folder(mt):
    P = dm.DANH_MUC["poster_len_lich"].dieu_kien_truoc
    ts = {"folder_id": 7, "so_video_ngay": 3}

    def hong():
        raise RuntimeError("Poster treo")
    mt.doc_folder_poster = hong
    r = P(ts, mt)
    assert isinstance(r, CanNguoiDung) and r.loai == "viec_tay" and "Poster" in r.noi_dung
    mt.doc_folder_poster = lambda: [{"id": 9, "name": "Ví", "duong_dan": "F:/x/output"}]
    r = P(ts, mt)                                              # folder đã bị xoá khỏi Poster
    assert isinstance(r, CanNguoiDung) and "7" in r.noi_dung


def test_poster_ds_folder_chuan_hoa_giu_duong_dan():
    """B-L1: poster_ds_folder.py trả thêm duong_dan (= path của folder Poster, day_len_poster.py:192)."""
    from runner import poster_ds_folder as pdf
    ds = pdf.chuan_hoa([{"id": 3, "name": "Ví", "path": "E:/g/Ví 1729420930611055346/output_poster"},
                        {"id": "7", "name": "Đèn"}, {"id": 9, "name": "x", "path": 5},
                        {"id": 4, "name": "dài", "path": "E:/" + "a" * 2000}, {"id": "x"}])
    assert ds == [{"id": 3, "ten": "Ví", "duong_dan": "E:/g/Ví 1729420930611055346/output_poster"},
                  {"id": 7, "ten": "Đèn"}, {"id": 9, "ten": "x"}, {"id": 4, "ten": "dài"}]   # không biết → không có khoá


# ---------- D15: hoc_hang_ngay + quet_view_hang_ngay (docs/hoc-tu-dong.md §3.3, §3.4a, §3.7, §9 HT-B3) ----------

HOM_NAY, HOM_QUA = "2026-11-17", "2026-11-16"


def _mt_hoc(mt, tmp_path, **kw):
    """mt có đủ 3 đường dẫn D15 (đều trong tmp_path — không đường dẫn thật nào)."""
    them = {"poster_db": tmp_path / "poster" / "v2_data.db", "thu_muc_view": tmp_path / "view",
            "script_quet_kenh": tmp_path / "scan" / "tiktok_scan.py"}
    them.update(kw)
    return replace(mt, **them)


def test_loai_he_thong_trong_danh_muc():
    # Radar UID (docs/radar-uid.md §6.1): 2 loại mới cũng chỉ runner tạo và không Chạy lại qua /viec
    assert dm.LOAI_CHI_HE_THONG == ("hoc_hang_ngay", "quet_view_hang_ngay", "radar_uid_hang_ngay", "radar_uid_nap")
    assert dm.LOAI_KHONG_CHAY_LAI == ("hoc_hang_ngay", "radar_uid_hang_ngay", "radar_uid_nap")
    assert dm.GIO_HOC_TOI_DA_CHO == 18
    assert dm.THU_MUC_CAI == Path(dm.__file__).resolve().parent.parent
    assert (dm.THU_MUC_CAI / "runner" / "danh_muc.py").is_file()
    h, q = dm.DANH_MUC["hoc_hang_ngay"], dm.DANH_MUC["quet_view_hang_ngay"]
    assert (h.ma, h.ten, h.dot, h.lan_chay, h.ton_tien, h.agent) == ("hoc_hang_ngay", "Học mỗi ngày", 3, "nhe",
                                                                     False, None)
    assert (h.tu_chay_lai, h.het_gio_s, h.tai_nguyen) == (True, 600, frozenset())
    assert (q.ma, q.ten, q.dot, q.lan_chay, q.ton_tien, q.agent) == (
        "quet_view_hang_ngay", "Quét view video của mình", 3, "nhe", False, None)
    assert (q.tu_chay_lai, q.het_gio_s, q.tai_nguyen) == (True, 25 * 60, frozenset())
    for l in (h, q):
        assert [t["ten"] for t in l.tham_so] == ["ngay"]
        assert l.tinh_khoa({"ngay": HOM_NAY}) == HOM_NAY
        assert l.trang_thai_dau({"ngay": HOM_NAY}) == ("cho", "chay")
        assert l.bo_cong_cu == () and l.tran_luot is None
    assert set(dm.LOAI_KHONG_CHAY_LAI) <= set(dm.LOAI_CHI_HE_THONG) <= set(dm.DANH_MUC)


def test_moi_truong_4_truong_moi_co_mac_dinh(mt):
    assert mt.poster_db is None and mt.thu_muc_view is None and mt.script_quet_kenh is None
    assert mt.goi_y_hoc(5) == [] and mt.goi_y_hoc(0) == []


def test_kiem_tham_so_hoc_va_quet_hop_le(mt):
    H, Q = dm.DANH_MUC["hoc_hang_ngay"], dm.DANH_MUC["quet_view_hang_ngay"]
    assert H.kiem_tham_so({"ngay": HOM_NAY}, mt) == {"ngay": HOM_NAY}
    assert H.kiem_tham_so({"ngay": HOM_QUA}, mt) == {"ngay": HOM_QUA}
    assert Q.kiem_tham_so({"ngay": HOM_NAY}, mt) == {"ngay": HOM_NAY}
    # "hôm nay" theo giờ VN: 2026-11-16 20:00 UTC = 2026-11-17 03:00 VN
    from datetime import timezone
    mt_utc = replace(mt, bay_gio=lambda: datetime(2026, 11, 16, 20, 0, tzinfo=timezone.utc))
    assert Q.kiem_tham_so({"ngay": HOM_NAY}, mt_utc) == {"ngay": HOM_NAY}
    with pytest.raises(ThamSoLoi):
        Q.kiem_tham_so({"ngay": HOM_QUA}, mt_utc)


@pytest.mark.parametrize("loai", ["hoc_hang_ngay", "quet_view_hang_ngay"])
@pytest.mark.parametrize("ts", [
    {}, {"ngay": None}, {"ngay": 20261117}, {"ngay": "2026/11/17"}, {"ngay": "2026-11-17\n"},
    {"ngay": " 2026-11-17"}, {"ngay": "２０２６-11-17"}, {"ngay": "2026-02-30"}, {"ngay": "2026-11-17T00:00"},
    {"ngay": "2026-11-15"}, {"ngay": "2026-11-18"}, {"ngay": HOM_NAY, "x": 1}, {"ngay": HOM_NAY, "ngay_tao": HOM_NAY},
])
def test_kiem_tham_so_hoc_va_quet_tu_choi(mt, loai, ts):
    with pytest.raises(ThamSoLoi):
        dm.DANH_MUC[loai].kiem_tham_so(ts, mt)


def test_quet_chi_chay_lai_luot_hom_nay(mt):
    with pytest.raises(ThamSoLoi, match="chỉ chạy lại lượt quét của hôm nay"):
        dm.DANH_MUC["quet_view_hang_ngay"].kiem_tham_so({"ngay": HOM_QUA}, mt)


def _kho_runner(mt):
    from runner.kho_viec import KhoViec
    Path(mt.thu_muc_du_lieu).mkdir(parents=True, exist_ok=True)
    return KhoViec(Path(mt.thu_muc_du_lieu) / "runner.db", lambda: BAY_GIO)


def test_dk_hoc_hoan_khi_viec_quet_cung_ngay_dang_mo(mt):
    """§3.3: việc quét cùng ngày đang cho/dang_chay và giờ VN < 18 → 'ban'; không thì None. Đọc runner.db mode=ro
    MỖI lần gọi (không dùng số liệu cũ)."""
    D = dm.DANH_MUC["hoc_hang_ngay"].dieu_kien_truoc
    db = Path(mt.thu_muc_du_lieu) / "runner.db"
    assert D({"ngay": HOM_NAY}, mt) is None and not db.exists()          # thiếu runner.db → không hoãn, không tạo file
    kho = _kho_runner(mt)
    assert D({"ngay": HOM_NAY}, mt) is None                               # chưa có việc quét
    v = kho.tao("quet_view_hang_ngay", HOM_NAY, {"ngay": HOM_NAY}, "nhe", "cho", "he_thong")
    assert D({"ngay": HOM_NAY}, mt) == "ban"
    assert D({"ngay": HOM_QUA}, mt) is None                               # việc quét của ngày khác
    kho.chuyen(v["id"], ["cho"], "dang_chay", "he_thong")
    assert D({"ngay": HOM_NAY}, mt) == "ban"
    for gio, ky_vong in ((datetime(2026, 11, 17, 17, 59, 59, tzinfo=MUI_GIO_VN), "ban"),
                         (datetime(2026, 11, 17, 18, 0, tzinfo=MUI_GIO_VN), None),
                         (datetime(2026, 11, 17, 23, 0, tzinfo=MUI_GIO_VN), None)):
        assert D({"ngay": HOM_NAY}, replace(mt, bay_gio=lambda g=gio: g)) == ky_vong, gio
    kho.chuyen(v["id"], ["dang_chay"], "loi", "he_thong", loi="kenh_loi")
    assert D({"ngay": HOM_NAY}, mt) is None                               # đọc lại: việc quét đã đóng
    # việc loại khác cùng khoá ngày không làm hoãn
    kho.tao("radar_ban_tin", HOM_NAY, {"top_n": 10, "chay_bu": False, "ngay_tao": HOM_NAY}, "nhe", "cho", "nhan")
    assert D({"ngay": HOM_NAY}, mt) is None


def test_dk_hoc_db_hong_khong_chan(mt, caplog):
    D = dm.DANH_MUC["hoc_hang_ngay"].dieu_kien_truoc
    Path(mt.thu_muc_du_lieu).mkdir(parents=True)
    (Path(mt.thu_muc_du_lieu) / "runner.db").write_bytes(b"khong phai sqlite" * 100)
    assert D({"ngay": HOM_NAY}, mt) is None
    assert any("runner.db" in r.getMessage() for r in caplog.records)


def test_dk_quet_view_dung_dang_ban(mt, monkeypatch):
    from runner import quet_view
    goi = []
    ket = {"v": "radar_dang_quet"}

    def gia(*a, **kw):
        goi.append((a, kw))
        return ket["v"]
    monkeypatch.setattr(quet_view, "dang_ban", gia)
    D = dm.DANH_MUC["quet_view_hang_ngay"].dieu_kien_truoc
    assert D({"ngay": HOM_NAY}, mt) == "ban"
    ket["v"] = "dang_chay_tay"
    assert D({"ngay": HOM_NAY}, mt) == "ban"
    ket["v"] = None
    assert D({"ngay": HOM_NAY}, mt) is None
    assert len(goi) == 3                                                  # hỏi lại mỗi lần, không nhớ kết quả cũ


def test_lap_buoc_hoc(mt, tmp_path):
    m = _mt_hoc(mt, tmp_path)
    H = dm.DANH_MUC["hoc_hang_ngay"]
    du = Path(m.thu_muc_du_lieu)
    ds = H.lap_buoc({"ngay": HOM_NAY}, _viec("hoc_hang_ngay", {"ngay": HOM_NAY}), m)
    assert len(ds) == 1
    b = ds[0]
    assert (b.ten, b.cwd, b.het_gio_s, b.la_claude, b.song, b.stdin) == ("hoc", str(dm.THU_MUC_CAI), 600, False,
                                                                         False, None)
    assert b.argv == [dm.PYTHON, "-B", "-m", "runner.hoc_tu_dong", "--ngay", HOM_NAY,
                      "--hoc-db", str(du / "hoc.db"), "--poster-db", str(m.poster_db),
                      "--runner-db", str(du / "runner.db"), "--repo", str(m.repo_kho), "--viec-id", ID]
    with pytest.raises(ThamSoLoi, match="DB Poster"):
        H.lap_buoc({"ngay": HOM_NAY}, _viec("hoc_hang_ngay", {"ngay": HOM_NAY}), mt)        # poster_db None
    with pytest.raises(ThamSoLoi):
        H.lap_buoc({"ngay": HOM_NAY}, _viec("hoc_hang_ngay", {"ngay": HOM_NAY}, id="../x"), m)
    with pytest.raises(ThamSoLoi):
        H.lap_buoc({"ngay": "2026-11-17 --x"}, _viec("hoc_hang_ngay", {}), m)


def test_lap_buoc_hieu_luc_hoc_noi_han_muc_hieu_luc(mt, tmp_path):
    """§3.3: lap_buoc_hieu_luc nối --bat-ngay/--hieu-luc-toi-da = hạn mức HIỆU LỰC (cau_hinh chỉ hạ)."""
    from runner.han_muc import HAN_MUC_TRAN, han_muc_hieu_luc
    m = _mt_hoc(mt, tmp_path)
    H = dm.DANH_MUC["hoc_hang_ngay"]
    v = _viec("hoc_hang_ngay", {"ngay": HOM_NAY})
    assert "--bat-ngay" not in H.lap_buoc(v["tham_so"], v, m)[0].argv
    b = dm.lap_buoc_hieu_luc(H, v["tham_so"], v, m, dict(HAN_MUC_TRAN))[0]
    assert b.argv[-4:] == ["--bat-ngay", "1", "--hieu-luc-toi-da", "5"]
    hm, _ = han_muc_hieu_luc({"hoc_bat_ngay": 0, "hoc_hieu_luc_toi_da": 2})
    b = dm.lap_buoc_hieu_luc(H, v["tham_so"], v, m, hm)[0]
    assert b.argv[-4:] == ["--bat-ngay", "0", "--hieu-luc-toi-da", "2"] and b.argv.count("--bat-ngay") == 1
    # dict bị nới vẫn kẹp về trần code
    b = dm.lap_buoc_hieu_luc(H, v["tham_so"], v, m, {**HAN_MUC_TRAN, "hoc_bat_ngay": 9})[0]
    assert b.argv[-4:] == ["--bat-ngay", "1", "--hieu-luc-toi-da", "5"]

    def boc(ts, viec, mm):                                               # test bọc lap_buoc (script giả)
        return [replace(H.lap_buoc(ts, viec, mm)[0], argv=["gia"])]
    b2 = dm.lap_buoc_hieu_luc(replace(H, lap_buoc=boc), v["tham_so"], v, m, hm)[0]
    assert b2.argv == ["gia", "--bat-ngay", "0", "--hieu-luc-toi-da", "2"]


def test_lap_buoc_quet_view(mt, tmp_path):
    m = _mt_hoc(mt, tmp_path)
    Q = dm.DANH_MUC["quet_view_hang_ngay"]
    v = _viec("quet_view_hang_ngay", {"ngay": HOM_NAY})
    ds = Q.lap_buoc(v["tham_so"], v, m)
    assert len(ds) == 1
    b = ds[0]
    assert (b.ten, b.cwd, b.het_gio_s, b.la_claude, b.stdin) == ("quet_view", str(dm.THU_MUC_CAI), 25 * 60, False,
                                                                 None)
    assert b.argv == [dm.PYTHON, "-B", "-m", "runner.quet_view", "--ngay", HOM_NAY,
                      "--view-dir", str(m.thu_muc_view), "--scan", str(m.script_quet_kenh),
                      "--poster-db", str(m.poster_db), "--du-lieu", str(m.thu_muc_du_lieu), "--nguon", "runner"]
    # CLI của quet_view nhận đúng bộ tham số này (bắt lệch hợp đồng giữa hai phiếu)
    from runner import quet_view
    a = quet_view._phan_tich_tham_so(b.argv[4:])
    assert (a.ngay, a.nguon, a.du_lieu) == (HOM_NAY, "runner", str(m.thu_muc_du_lieu))
    # lap_buoc_hieu_luc không đổi bước quét
    from runner.han_muc import HAN_MUC_TRAN
    assert dm.lap_buoc_hieu_luc(Q, v["tham_so"], v, m, dict(HAN_MUC_TRAN)) == ds
    for thieu in ("poster_db", "thu_muc_view", "script_quet_kenh"):
        with pytest.raises(ThamSoLoi):
            Q.lap_buoc(v["tham_so"], v, _mt_hoc(mt, tmp_path, **{thieu: None}))


def test_dau_ra_hoc(mt):
    from runner.kho_hoc import KhoHoc
    K = dm.DANH_MUC["hoc_hang_ngay"].kiem_dau_ra
    du = Path(mt.thu_muc_du_lieu)
    assert K({"ngay": HOM_NAY}, {}, mt) == "chua" and not (du / "hoc.db").exists()   # thiếu hoc.db: không tạo
    kho = KhoHoc(du / "hoc.db", lambda: BAY_GIO)
    kho.mo()
    assert K({"ngay": HOM_NAY}, {}, mt) == "chua"
    kho.bat_dau_lan(HOM_NAY, ID)
    assert K({"ngay": HOM_NAY}, {}, mt) == "chua"                         # dang_chay
    kho.ket_thuc_lan(HOM_NAY, "xong", "", {})
    assert K({"ngay": HOM_NAY}, {}, mt) == "xong"
    kho.bat_dau_lan(HOM_QUA, ID)
    kho.ket_thuc_lan(HOM_QUA, "tu_dung", "poster_cu", {})
    assert K({"ngay": HOM_QUA}, {}, mt) == "xong"
    kho.bat_dau_lan("2026-11-15", ID)
    kho.ket_thuc_lan("2026-11-15", "loi", "loi_bat_ngo", {})
    assert K({"ngay": "2026-11-15"}, {}, mt) == "chua"
    kho.dong()
    assert dm.kiem_dau_ra_an_toan(dm.DANH_MUC["hoc_hang_ngay"], {"ngay": HOM_NAY}, {}, mt) == "xong"


def test_dau_ra_hoc_db_hong(mt, caplog):
    du = Path(mt.thu_muc_du_lieu)
    du.mkdir(parents=True)
    (du / "hoc.db").write_bytes(b"rac" * 1000)
    assert dm.DANH_MUC["hoc_hang_ngay"].kiem_dau_ra({"ngay": HOM_NAY}, {}, mt) == "chua"
    assert any("hoc.db" in r.getMessage() for r in caplog.records)


def test_dau_ra_quet_view(mt):
    K = dm.DANH_MUC["quet_view_hang_ngay"].kiem_dau_ra
    qv = Path(mt.thu_muc_du_lieu) / "quet_view"
    assert K({"ngay": HOM_NAY}, {}, mt) == "chua"
    qv.mkdir(parents=True)
    f = qv / f"{HOM_NAY}.json"
    for noi, ky_vong in ((json.dumps({"trang_thai": "dang_chay", "lan": 1}), "chua"),
                         (json.dumps({"trang_thai": "loi", "lan": 2}), "chua"),
                         ("{hỏng", "chua"),
                         (json.dumps({"trang_thai": "ok", "lan": 1, "kenh": []}), "xong")):
        f.write_text(noi, encoding="utf-8")
        assert K({"ngay": HOM_NAY}, {}, mt) == ky_vong, noi
    assert K({"ngay": HOM_QUA}, {}, mt) == "chua"


def test_khoi_dong_lai_he_thong_tu_chay_lai(mt):
    for ma in dm.LOAI_CHI_HE_THONG:
        l = dm.DANH_MUC[ma]
        assert dm.quyet_dinh_sau_khoi_dong({"lan_thu": 1}, "chua", l)[0] == "cho"
        assert dm.quyet_dinh_sau_khoi_dong({"lan_thu": 3}, "chua", l)[0] == "loi"
        assert dm.quyet_dinh_sau_khoi_dong({"lan_thu": 1}, "xong", l)[0] == "xong"


def test_lap_buoc_hieu_luc_phan_tich_uid_goi_y_theo_hm(mt):
    """§3.7: phiếu phan_tich_uid lập lại theo hm vòng chạy đang giữ → gợi ý lấy với hạn mức HIỆU LỰC."""
    from runner import hoc_danh_muc as hdm
    from runner.han_muc import han_muc_hieu_luc
    goi: list[int] = []
    muc = {"ma": "bh20261117abcd", "khoa": "cap_co_so", "huong": "tang", "nguon": "poster_view",
           "trang_thai": "hieu_luc", "lift_pt": 22, "so_uid": 21, "so_cung_chieu": 16, "so_viec": 300}

    def goi_y(n):
        goi.append(n)
        return [muc][:n]
    m = replace(mt, goi_y_hoc=goi_y)
    P = dm.DANH_MUC["phan_tich_uid"]
    v = _viec("phan_tich_uid", {"uid": UID})
    hm, _ = han_muc_hieu_luc({"hoc_hieu_luc_toi_da": 2})
    b = dm.lap_buoc_hieu_luc(P, v["tham_so"], v, m, hm)[0]
    assert hdm.TIEU_DE_GOI_Y in b.stdin and "[bh20261117abcd]" in b.stdin and goi[-1] == 2
    hm0, _ = han_muc_hieu_luc({"hoc_bat_ngay": 0})
    b0 = dm.lap_buoc_hieu_luc(P, v["tham_so"], v, m, hm0)[0]
    assert hdm.TIEU_DE_GOI_Y not in b0.stdin and "bh20261117abcd" not in b0.stdin
    # resume (đã có phiên): không lập phiếu → không có khối
    br = dm.lap_buoc_hieu_luc(P, v["tham_so"], dict(v, phien_da_tao=1), m, hm)[0]
    assert br.stdin is None
# ---------- Radar UID: radar_uid_hang_ngay + radar_uid_nap (docs/radar-uid.md §6.1, §6.6, RU-B3) ----------

GOC_RADAR = "1737422436677814024"      # > 2^53: id luôn là chuỗi


def _mt_radar(mt, tmp_path, **kw):
    them = {"echotik_token_file": tmp_path / "token" / ".echotik_token.json"}
    them.update(kw)
    return replace(mt, **them)


def test_radar_uid_hai_loai_khai_bao_dung_phieu():
    h, n = dm.DANH_MUC["radar_uid_hang_ngay"], dm.DANH_MUC["radar_uid_nap"]
    for l in (h, n):
        assert (l.dot, l.lan_chay, l.ton_tien, l.agent, l.tu_chay_lai) == (3, "nhe", False, None, True)
        assert l.tai_nguyen == frozenset() and l.bo_cong_cu == () and l.tran_luot is None
        assert l.ma in dm.LOAI_CHI_HE_THONG and l.ma in dm.LOAI_KHONG_CHAY_LAI
    assert (h.het_gio_s, n.het_gio_s) == (1200, 900)
    assert [t["ten"] for t in h.tham_so] == ["ngay"] and [t["ten"] for t in n.tham_so] == ["goc"]
    assert h.tinh_khoa({"ngay": HOM_NAY}) == HOM_NAY and n.tinh_khoa({"goc": GOC_RADAR}) == GOC_RADAR
    assert h.trang_thai_dau({"ngay": HOM_NAY}) == ("cho", "chay")
    assert n.trang_thai_dau({"goc": GOC_RADAR}) == ("cho", "chay")
    from runner.han_muc import LOAI_RADAR_UID, TRAN_LUOT
    assert LOAI_RADAR_UID == ("radar_uid_hang_ngay", "radar_uid_nap") == dm.LOAI_RADAR_UID
    assert not (set(LOAI_RADAR_UID) & set(TRAN_LUOT))


def test_radar_uid_mien_phi_khong_phien_song():
    """Việc radar KHÔNG tốn tiền: không ton_tien, không phiên sống, không nằm trong loại nào của web."""
    ton = {m for m, l in dm.DANH_MUC.items() if l.ton_tien}
    assert not ({"radar_uid_hang_ngay", "radar_uid_nap"} & (ton | set(dm.LOAI_PHIEN_SONG)))


def test_radar_uid_kiem_tham_so_hop_le(mt):
    H, N = dm.DANH_MUC["radar_uid_hang_ngay"], dm.DANH_MUC["radar_uid_nap"]
    assert H.kiem_tham_so({"ngay": HOM_NAY}, mt) == {"ngay": HOM_NAY}
    assert H.kiem_tham_so({"ngay": HOM_QUA}, mt) == {"ngay": HOM_QUA}
    assert N.kiem_tham_so({"goc": GOC_RADAR}, mt) == {"goc": GOC_RADAR}


@pytest.mark.parametrize("ts", [
    {}, {"ngay": None}, {"ngay": "2026-11-17\n"}, {"ngay": "2026-02-30"}, {"ngay": "2026-11-15"},
    {"ngay": "2026-11-18"}, {"ngay": HOM_NAY, "goc": GOC_RADAR}, {"ngay": HOM_NAY, "x": 1},
])
def test_radar_uid_hang_ngay_tu_choi_tham_so(mt, ts):
    with pytest.raises(ThamSoLoi):
        dm.DANH_MUC["radar_uid_hang_ngay"].kiem_tham_so(ts, mt)


@pytest.mark.parametrize("ts", [
    {}, {"goc": None}, {"goc": 1737422436677814024}, {"goc": "123"}, {"goc": GOC_RADAR + "0"},
    {"goc": GOC_RADAR + "\n"}, {"goc": "１７３７４２２４３６６７７８１４０２４"}, {"goc": GOC_RADAR, "uid": GOC_RADAR},
    {"uid": GOC_RADAR}, {"goc": GOC_RADAR, "ngay": HOM_NAY},
])
def test_radar_uid_nap_tu_choi_tham_so(mt, ts):
    with pytest.raises(ThamSoLoi):
        dm.DANH_MUC["radar_uid_nap"].kiem_tham_so(ts, mt)


def test_lap_buoc_radar_uid_hang_ngay(mt, tmp_path):
    m = _mt_radar(mt, tmp_path)
    H = dm.DANH_MUC["radar_uid_hang_ngay"]
    du = Path(m.thu_muc_du_lieu)
    ds = H.lap_buoc({"ngay": HOM_NAY}, _viec("radar_uid_hang_ngay", {"ngay": HOM_NAY}), m)
    assert len(ds) == 1
    b = ds[0]
    assert (b.ten, b.cwd, b.het_gio_s, b.la_claude, b.song, b.stdin, b.env_them) == (
        "radar_uid", str(dm.THU_MUC_CAI), 1200, False, False, None, {})
    assert b.argv == [dm.PYTHON, "-B", "-m", "runner.radar_uid", "--che-do", "hang-ngay", "--ngay", HOM_NAY,
                      "--db", str(du / "radar_uid.db"), "--token-file", str(m.echotik_token_file),
                      "--viec-id", ID, "--tran-goi", "60"]
    assert "--goc" not in b.argv
    with pytest.raises(ThamSoLoi):
        H.lap_buoc({"ngay": HOM_NAY}, _viec("radar_uid_hang_ngay", {}, id="../x"), m)
    with pytest.raises(ThamSoLoi):
        H.lap_buoc({"ngay": "2026-11-17 --x"}, _viec("radar_uid_hang_ngay", {}), m)
    with pytest.raises(ThamSoLoi, match="token"):                    # echotik_token_file None: không tự đoán đường dẫn
        H.lap_buoc({"ngay": HOM_NAY}, _viec("radar_uid_hang_ngay", {"ngay": HOM_NAY}), mt)


def test_lap_buoc_radar_uid_nap(mt, tmp_path):
    m = _mt_radar(mt, tmp_path)
    N = dm.DANH_MUC["radar_uid_nap"]
    du = Path(m.thu_muc_du_lieu)
    ds = N.lap_buoc({"goc": GOC_RADAR}, _viec("radar_uid_nap", {"goc": GOC_RADAR}), m)
    assert len(ds) == 1
    b = ds[0]
    assert (b.ten, b.cwd, b.het_gio_s, b.la_claude) == ("radar_uid", str(dm.THU_MUC_CAI), 900, False)
    assert b.argv == [dm.PYTHON, "-B", "-m", "runner.radar_uid", "--che-do", "nap", "--ngay", HOM_NAY,
                      "--db", str(du / "radar_uid.db"), "--token-file", str(m.echotik_token_file),
                      "--viec-id", ID, "--tran-goi", "60", "--goc", GOC_RADAR]
    with pytest.raises(ThamSoLoi):
        N.lap_buoc({"goc": "12"}, _viec("radar_uid_nap", {}), m)


def test_lap_buoc_radar_uid_token_chi_la_duong_dan(mt, tmp_path):
    m = _mt_radar(mt, tmp_path)
    for ma, ts in (("radar_uid_hang_ngay", {"ngay": HOM_NAY}), ("radar_uid_nap", {"goc": GOC_RADAR})):
        b = dm.DANH_MUC[ma].lap_buoc(ts, _viec(ma, ts), m)[0]
        assert b.argv[b.argv.index("--token-file") + 1] == str(m.echotik_token_file)
        assert b.env_them == {}                                       # token không vào env, không có cờ truyền giá trị


def test_lap_buoc_hieu_luc_radar_noi_tran_goi_hieu_luc(mt, tmp_path):
    """lap_buoc_hieu_luc thay giá trị sau --tran-goi bằng radar_uid_goi_ngay HIỆU LỰC (cau_hinh chỉ hạ)."""
    from runner.han_muc import HAN_MUC_TRAN, han_muc_hieu_luc
    m = _mt_radar(mt, tmp_path)
    for ma, ts in (("radar_uid_hang_ngay", {"ngay": HOM_NAY}), ("radar_uid_nap", {"goc": GOC_RADAR})):
        L = dm.DANH_MUC[ma]
        v = _viec(ma, ts)
        goc_argv = L.lap_buoc(ts, v, m)[0].argv
        assert dm.lap_buoc_hieu_luc(L, ts, v, m, dict(HAN_MUC_TRAN))[0].argv == goc_argv
        hm, _ = han_muc_hieu_luc({"radar_uid_goi_ngay": 25})
        b = dm.lap_buoc_hieu_luc(L, ts, v, m, hm)[0]
        assert b.argv[b.argv.index("--tran-goi") + 1] == "25" and b.argv.count("--tran-goi") == 1
        assert len(b.argv) == len(goc_argv)
        b = dm.lap_buoc_hieu_luc(L, ts, v, m, {**HAN_MUC_TRAN, "radar_uid_goi_ngay": 999})[0]   # dict bị nới → kẹp
        assert b.argv[b.argv.index("--tran-goi") + 1] == "60"


def test_cli_radar_uid_khop_ten_cli_cua_ru_a2(mt, tmp_path):
    """Hợp đồng với RU-A2 (chỉ TÊN CLI): mọi cờ argv nằm trong bộ cờ đã khai ở phiếu; che_do đúng 'nap'/'hang-ngay'."""
    da_khai = {"--che-do", "--ngay", "--db", "--token-file", "--viec-id", "--tran-goi", "--goc"}
    m = _mt_radar(mt, tmp_path)
    for ma, ts, che_do in (("radar_uid_hang_ngay", {"ngay": HOM_NAY}, "hang-ngay"),
                           ("radar_uid_nap", {"goc": GOC_RADAR}, "nap")):
        argv = dm.DANH_MUC[ma].lap_buoc(ts, _viec(ma, ts), m)[0].argv
        assert argv[:4] == [dm.PYTHON, "-B", "-m", "runner.radar_uid"]
        assert {a for a in argv[4:] if a.startswith("--")} <= da_khai
        assert argv[argv.index("--che-do") + 1] == che_do


def _ket_thuc_lan_db(du: Path, ngay: str, che_do: str, viec_id: str, trang_thai: str) -> None:
    from runner.kho_radar_uid import KhoRadarUid
    k = KhoRadarUid(du / "radar_uid.db", lambda: BAY_GIO)
    k.mo()
    try:
        k.bat_dau_lan(ngay, che_do, viec_id)
        if trang_thai != "dang_chay":
            k.ket_thuc_lan(ngay, che_do, viec_id, trang_thai, "" if trang_thai == "xong" else "het_han_muc_goi", 0)
    finally:
        k.dong()


@pytest.mark.parametrize("ma,che_do,ts", [("radar_uid_hang_ngay", "hang-ngay", {"ngay": HOM_NAY}),
                                          ("radar_uid_nap", "nap", {"goc": GOC_RADAR})])
def test_dau_ra_radar_uid(mt, ma, che_do, ts):
    K = dm.DANH_MUC[ma].kiem_dau_ra
    du = Path(mt.thu_muc_du_lieu)
    viec = _viec(ma, ts)
    assert K(ts, viec, mt) == "chua" and not (du / "radar_uid.db").exists()      # thiếu DB: không tạo file
    _ket_thuc_lan_db(du, HOM_NAY, che_do, ID, "dang_chay")
    assert K(ts, viec, mt) == "chua"
    from runner.kho_radar_uid import KhoRadarUid
    k = KhoRadarUid(du / "radar_uid.db", lambda: BAY_GIO)
    k.ket_thuc_lan(HOM_NAY, che_do, ID, "xong", "", 3)
    k.dong()
    assert K(ts, viec, mt) == "xong"
    assert K(ts, _viec(ma, ts, id="j20261117090000zzzz"), mt) == "chua"          # việc khác không cho "xong" hộ
    khac = "nap" if che_do == "hang-ngay" else "hang-ngay"
    _ket_thuc_lan_db(du, HOM_NAY, khac, "j20261117090000yyyy", "xong")
    assert K(ts, _viec(ma, ts, id="j20261117090000yyyy"), mt) == "chua"          # che_do khác không khớp
    assert dm.kiem_dau_ra_an_toan(dm.DANH_MUC[ma], ts, viec, mt) == "xong"


@pytest.mark.parametrize("ma,che_do,ts", [("radar_uid_hang_ngay", "hang-ngay", {"ngay": HOM_NAY}),
                                          ("radar_uid_nap", "nap", {"goc": GOC_RADAR})])
def test_dau_ra_radar_uid_tu_dung_la_xong_loi_la_chua(mt, ma, che_do, ts):
    """Như _dau_ra_hoc: xong/tu_dung ⇒ xong; loi/đang chạy ⇒ chua. KHÔNG đòi mọi UID có chup_uid."""
    du = Path(mt.thu_muc_du_lieu)
    K = dm.DANH_MUC[ma].kiem_dau_ra
    _ket_thuc_lan_db(du, HOM_NAY, che_do, ID, "tu_dung")
    assert K(ts, _viec(ma, ts), mt) == "xong"
    _ket_thuc_lan_db(du, HOM_NAY, che_do, "j20261117090000loi1", "loi")
    assert K(ts, _viec(ma, ts, id="j20261117090000loi1"), mt) == "chua"
    with sqlite3.connect(f"file:{(du / 'radar_uid.db').as_posix()}?mode=ro", uri=True) as c:
        assert c.execute("SELECT COUNT(*) FROM chup_uid").fetchone()[0] == 0      # chưa chụp UID nào mà vẫn xong


def test_dau_ra_radar_uid_db_hong(mt, caplog):
    du = Path(mt.thu_muc_du_lieu)
    du.mkdir(parents=True)
    (du / "radar_uid.db").write_bytes(b"rac" * 1000)
    ts = {"ngay": HOM_NAY}
    assert dm.DANH_MUC["radar_uid_hang_ngay"].kiem_dau_ra(ts, _viec("radar_uid_hang_ngay", ts), mt) == "chua"
    assert any("radar_uid.db" in r.getMessage() for r in caplog.records)


def test_moi_truong_echotik_token_file_mac_dinh_none(mt):
    assert mt.echotik_token_file is None
