"""Test phiên sống `taovideo` (§7.2–7.8, phiếu A-5) — chạy:
PYTHONIOENCODING=utf-8 python -B -m pytest tools/test_runner_phien_song.py -q -p no:cacheprovider

Claude giả = script Python đọc dòng JSON từ stdin, phát sự kiện stream-json theo kịch bản (CLAUDE_SONG). Đồng hồ thu
nhỏ bằng tham số (im_lang 0,3 s, nhịp 0,1 s, cau_hinh taovideo_*_s = 1–2 s). Không gọi claude.exe thật, không đụng
E:\\kho-runner, cổng 8787/8788; DB/log/dự án đều ở tmp_path.
"""
import base64
import dataclasses
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import psutil
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

TOOLS = Path(__file__).parent
sys.path.insert(0, str(TOOLS))
from runner import api as _api  # noqa: E402
from runner import chu_ky  # noqa: E402
from runner import phien_song as ps  # noqa: E402
from runner import thuc_thi as tt  # noqa: E402
from runner import vong_lap as vl  # noqa: E402
from runner.danh_muc import DANH_MUC  # noqa: E402
from runner.du_an import ma_du_an  # noqa: E402
from runner.han_muc import HAN_MUC_TRAN  # noqa: E402
from runner.kho_viec import KhoViec  # noqa: E402
from runner.kieu import DANG_MO, MUI_GIO_VN, RE_MA_CAU_HOI, CanNguoiDung, KhongCoPhien, MoiTruong, SaiTrangThai  # noqa: E402,E501
from runner.phieu import TIN_NHAC, TIN_TRAN_CODEX  # noqa: E402
from runner.theo_doi_phien import TheoDoiPhien  # noqa: E402

PY = sys.executable
UID = "1729384756102938475"
IM_LANG = 0.3

CLAUDE_SONG = r'''
import json, os, queue, subprocess, sys, threading, time
kb_path = sys.argv[1]
args = sys.argv[2:]
kb = json.load(open(kb_path, encoding="utf-8"))
ghi = kb_path + ".goi.jsonl"
khoa = threading.Lock()
def log(o):
    o["t"] = time.time()
    with khoa:
        with open(ghi, "a", encoding="utf-8") as f:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
n = 0
if os.path.exists(ghi):
    n = sum(1 for d in open(ghi, encoding="utf-8") if json.loads(d).get("loai") == "bat_dau")
kich = kb[min(n, len(kb) - 1)]
sid = args[args.index("--session-id") + 1] if "--session-id" in args else None
log({"loai": "bat_dau", "args": args, "pid": os.getpid(), "cwd": os.getcwd(), "lan": n})
q = queue.Queue()
def doc():
    for b in iter(sys.stdin.buffer.readline, b""):
        try:
            m = json.loads(b.decode("utf-8"))
            noi = m["message"]["content"]
        except Exception:
            m, noi = {"hong": repr(b[:200])}, None
        log({"loai": "tin", "noi": noi, "tho": m})
        q.put(noi)
    log({"loai": "eof"})
    q.put(None)
threading.Thread(target=doc, daemon=True).start()
def out(o):
    sys.stdout.write(json.dumps(o, ensure_ascii=False) + "\n")
    sys.stdout.flush()
dem = [0]
def lam(v):
    k = v["k"]
    if k == "asst":
        dem[0] += 1
        c = [{"type": "text", "text": v.get("text", "đang làm")}]
        for j, t in enumerate(v.get("tools", [])):
            c.append({"type": "tool_use", "id": f"tu{n}_{dem[0]}_{j}", "name": t["name"], "input": t.get("input", {})})
        out({"type": "assistant", "parent_tool_use_id": v.get("parent"), "session_id": sid,
             "message": {"id": f"m{n}_{dem[0]}", "content": c}})
    elif k == "ngu":
        time.sleep(v["s"])
    elif k == "nen_bat":
        out({"type": "system", "subtype": "task_started", "task_id": v["id"], "session_id": sid})
    elif k == "nen_xong":
        out({"type": "system", "subtype": "task_notification", "task_id": v["id"], "status": "completed",
             "session_id": sid})
    elif k == "mp3":
        d = os.path.join(os.getcwd(), "voice", "me1")
        os.makedirs(d, exist_ok=True)
        for i in range(v["n"]):
            open(os.path.join(d, f"x{i:02d}_adam.mp3"), "wb").write(b"ID3")
    elif k == "con":
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
        log({"loai": "con", "pid": p.pid})
    elif k == "ket":
        out({"type": "result", "subtype": v.get("subtype", "success"), "is_error": v.get("loi", False),
             "session_id": sid, "total_cost_usd": v.get("usd", 0.01), "num_turns": 1, "duration_ms": 5,
             "result": v.get("text", "")})
        log({"loai": "ket", "text": v.get("text", "")})
    elif k == "moc":
        log({"loai": "moc", "ten": v["ten"]})
    elif k == "stderr":
        sys.stderr.write(v["text"] + "\n")
        sys.stderr.flush()
    elif k == "thoat":
        log({"loai": "thoat", "ma": v.get("ma", 0)})
        os._exit(v.get("ma", 0))
luot = kich.get("luot", [])
cho_tin = True
i = 0
da_init = False
while True:
    if cho_tin or i >= len(luot):
        noi = q.get()
        if noi is None:
            break
        if i >= len(luot):
            continue
    if not da_init:
        da_init = True
        out({"type": "system", "subtype": "init", "session_id": sid, "permissionMode": "dontAsk",
             "tools": kich.get("tools", ["Task", "Bash", "Read", "Write", "Edit", "Glob", "Grep", "Skill",
                                          "TaskOutput", "TaskStop", "TodoWrite"]),
             "mcp_servers": [], "claude_code_version": kich.get("ver", "2.1.169")})
    l = luot[i]
    i += 1
    for v in l.get("viec", []):
        lam(v)
    cho_tin = not l.get("tu_thuc", False)
sys.exit(kich.get("ma_eof", 0))
'''

DONE = "Báo cáo cuối.\nTRẠNG THÁI: DONE\nXong cả 2 bước."
CAN_CHON = "Cần chốt.\nCẦN_USER: Tạo lại voice hỏng?\nLOẠI: chon\nLỰA_CHỌN: Tạo lại | Bỏ qua"


# ================================================================ tiện ích

def _ket(text, usd=0.01, **kw):
    return dict({"k": "ket", "text": text, "usd": usd}, **kw)


def _asst(text="đang làm", tools=(), parent=None):
    return {"k": "asst", "text": text, "tools": list(tools), "parent": parent}


def ghi_kb(tmp: Path, kich_ban: list[dict]) -> tuple[Path, Path]:
    fake = tmp / "claude_song_gia.py"
    fake.write_text(CLAUDE_SONG, encoding="utf-8")
    kb = tmp / f"kb_{uuid.uuid4().hex[:6]}.json"
    kb.write_text(json.dumps(kich_ban, ensure_ascii=False), encoding="utf-8")
    return fake, kb


def nhat_ky(kb: Path) -> list[dict]:
    p = Path(str(kb) + ".goi.jsonl")
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def tin_nhan(kb: Path, lan: int | None = None) -> list[str]:
    """Nội dung các tin user Claude giả nhận được (lần sinh `lan`, None = mọi lần)."""
    ra, hien = [], -1
    for d in nhat_ky(kb):
        if d["loai"] == "bat_dau":
            hien = d["lan"]
        elif d["loai"] == "tin" and (lan is None or hien == lan):
            ra.append(d["noi"])
    return ra


def song(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def cho(dk, han_s=20.0, buoc=0.05):
    het = time.monotonic() + han_s
    while time.monotonic() < het:
        v = dk()
        if v:
            return v
        time.sleep(buoc)
    raise AssertionError("hết giờ chờ điều kiện")


@pytest.fixture(autouse=True)
def nhip_nhanh(monkeypatch):
    monkeypatch.setattr(ps, "NHIP_S", 0.1)


# ================================================================ PhienSong (module, không DB)

def lam_phien(tmp: Path, kich_ban: list[dict], im_lang=IM_LANG, cho_thoat=5.0):
    fake, kb = ghi_kb(tmp, kich_ban)
    ch = ps.CauHinhPhien(argv=[PY, str(fake), str(kb), "--session-id", str(uuid.uuid4())], cwd=str(tmp),
                         env=tt.env_toi_thieu({}), file_log=tmp / "p.log", file_jsonl=tmp / "p.jsonl",
                         im_lang_s=im_lang, cho_thoat_s=cho_thoat)
    return ps.PhienSong(ch, TheoDoiPhien(5), lambda s: s.replace("BIMAT123456789", "***")), kb


def test_tin_gui_luc_dang_lam_chi_ghi_sau_ket_luot(tmp_path):
    """Tiêu chí 4 (S-4 mục 1): gui() lúc agent đang làm → nằm hàng đợi, chỉ ghi stdin sau result + im lặng."""
    p, kb = lam_phien(tmp_path, [{"luot": [{"viec": [_asst(), {"k": "ngu", "s": 1.5}, _ket("đang chờ")]}]}])
    assert p.gui("PHIẾU")
    trang = {"chen": False, "luc_chen": None}

    def nhip(tinh, luc):
        if not trang["chen"] and tinh.loai == "dang_lam" and nhat_ky(kb) and any(
                d["loai"] == "tin" for d in nhat_ky(kb)):
            trang["chen"] = p.gui("TIN CHEN")
            trang["luc_chen"] = time.time()
        elif trang["chen"] and tinh.loai == "ket_luot" and p.so_tin_cho == 0 and len(tin_nhan(kb)) == 2:
            p.dong()
    kq = p.chay(lambda pid, tl: None, lambda sk, luc, d: None, nhip, threading.Event())
    assert kq.ly_do_dung == "dong_stdin" and kq.ma_thoat == 0 and not kq.khong_giet_duoc, kq
    nk = nhat_ky(kb)
    tin = [d for d in nk if d["loai"] == "tin"]
    ket = [d for d in nk if d["loai"] == "ket"][0]
    assert [t["noi"] for t in tin] == ["PHIẾU", "TIN CHEN"]
    assert trang["luc_chen"] < ket["t"] < tin[1]["t"]                  # gửi lúc đang làm, tới SAU result
    assert tin[1]["t"] - ket["t"] >= IM_LANG * 0.9                       # và sau khoảng im lặng
    assert not p.gui("muộn") and not p.con_song()                        # đã đóng → False


def test_bo_hang_doi_va_dong_stdin_thoat_gon(tmp_path):
    p, kb = lam_phien(tmp_path, [{"luot": [{"viec": [_ket("TRẠNG THÁI: DONE")]}]}])
    p.gui("PHIẾU")
    da = {"n": None}

    def nhip(tinh, luc):
        if tinh.loai == "ket_luot" and da["n"] is None:
            p.dat_cau_hoi("q00000000000a", tinh.so_ket_luot)
            p.gui("a", "q00000000000a")
            p.gui("TIN HỆ THỐNG")
            p.gui("b", "q00000000000a")
            da["n"] = p.bo_hang_doi()                    # FX-27: chỉ huỷ tin trả lời (có mã câu hỏi)
            da["con"] = p.so_tin_cho
            p.dong()
    kq = p.chay(lambda pid, tl: None, lambda sk, luc, d: None, nhip, threading.Event())
    assert da["n"] == 2 and da["con"] == 1 and tin_nhan(kb) == ["PHIẾU"] and kq.ly_do_dung == "dong_stdin"
    assert any(d["loai"] == "eof" for d in nhat_ky(kb))


def test_tu_thoat_va_jsonl_log_che(tmp_path):
    p, kb = lam_phien(tmp_path, [{"luot": [{"viec": [_asst("khoá BIMAT123456789"), {"k": "stderr",
                                                                                    "text": "lỗi BIMAT123456789"},
                                                     {"k": "thoat", "ma": 3}]}]}])
    p.gui("PHIẾU")
    su_kien = []
    kq = p.chay(lambda pid, tl: None, lambda sk, luc, d: su_kien.append(sk["type"]), lambda t, l: None,
                threading.Event())
    assert kq.ly_do_dung == "tu_thoat" and kq.ma_thoat == 3 and kq.pid and kq.pid_tao_luc
    assert "system" in su_kien and "assistant" in su_kien
    log_txt = (tmp_path / "p.log").read_text(encoding="utf-8")
    assert "BIMAT123456789" not in log_txt and "***" in log_txt
    assert "BIMAT123456789" not in kq.duoi_stderr and "lỗi ***" in kq.duoi_stderr
    assert all(json.loads(d) for d in (tmp_path / "p.jsonl").read_text(encoding="utf-8").splitlines())


def test_huy_giet_ca_cay_ke_ca_con(tmp_path):
    p, kb = lam_phien(tmp_path, [{"luot": [{"viec": [{"k": "con"}, _ket(CAN_CHON)]}]}])
    p.gui("PHIẾU")
    huy = threading.Event()

    def nhip(tinh, luc):
        if tinh.loai == "ket_luot":
            huy.set()
    kq = p.chay(lambda pid, tl: None, lambda sk, luc, d: None, nhip, huy)
    assert kq.ly_do_dung.startswith("giet:") and "huỷ" in kq.ly_do_dung
    con = [d["pid"] for d in nhat_ky(kb) if d["loai"] == "con"][0]
    assert not song(kq.pid) and cho(lambda: not song(con), 10)


def test_callback_nem_loi_thi_giet_cay_va_nem_lai(tmp_path):
    p, kb = lam_phien(tmp_path, [{"luot": [{"viec": [_asst(), {"k": "ngu", "s": 30}]}]}])
    p.gui("PHIẾU")

    def su_kien(sk, luc, d):
        if sk.get("type") == "assistant":
            raise RuntimeError("công cụ lạ")
    t0 = time.monotonic()
    with pytest.raises(RuntimeError, match="công cụ lạ"):
        p.chay(lambda pid, tl: None, su_kien, lambda t, l: None, threading.Event())
    assert time.monotonic() - t0 < 20
    pid = [d["pid"] for d in nhat_ky(kb) if d["loai"] == "bat_dau"][0]
    assert not song(pid)


def test_giet_tu_nhip_va_chenh_lech_chi_phi(tmp_path):
    p, kb = lam_phien(tmp_path, [{"luot": [{"viec": [_ket("a", 0.1), {"k": "ngu", "s": 0.1}, _ket("b", 0.3),
                                                     {"k": "ngu", "s": 30}]}]}])
    p.gui("PHIẾU")
    d_all = []
    kq = p.chay(lambda pid, tl: None, lambda sk, luc, d: d_all.append(d),
                lambda t, l: p.giet("thử giết") if t.so_ket_luot >= 2 else None, threading.Event())
    assert kq.ly_do_dung == "giet:thử giết" and not song(kq.pid)
    assert round(sum(d_all), 6) == 0.3


def test_dong_ma_khong_thoat_trong_han_thi_giet(tmp_path):
    """Đóng stdin mà tiến trình không thoát trong cho_thoat_s → giết cây."""
    fake = tmp_path / "lì.py"
    fake.write_text("import sys,time,json\nsys.stdin.readline()\n"
                    "print(json.dumps({'type':'system','subtype':'init','session_id':'s','tools':[]}),flush=True)\n"
                    "sys.stdin.read()\ntime.sleep(60)\n", encoding="utf-8")
    ch = ps.CauHinhPhien(argv=[PY, str(fake)], cwd=str(tmp_path), env=tt.env_toi_thieu({}),
                         file_log=tmp_path / "p.log", file_jsonl=tmp_path / "p.jsonl", im_lang_s=IM_LANG,
                         cho_thoat_s=1.0)
    p = ps.PhienSong(ch, TheoDoiPhien(5), lambda s: s)
    p.gui("x")
    kq = p.chay(lambda pid, tl: None, lambda sk, luc, d: p.dong(), lambda t, l: None, threading.Event())
    assert kq.ly_do_dung.startswith("giet:") and not song(kq.pid)


# ================================================================ BoChay + phiên sống (taovideo)

def lam_mt(tmp: Path, **kw) -> MoiTruong:
    for d in ("goc", "repo", "scripts", "radar", "sp", "data"):
        (tmp / d).mkdir(exist_ok=True)
    gt = dict(gocs=[tmp / "goc"], repo_kho=tmp / "repo", thu_muc_scripts=tmp / "scripts", python_poster=Path(PY),
              claude_exe=Path(PY), agy_exe=Path(PY), thu_muc_radar=tmp / "radar", thu_muc_sp=tmp / "sp",
              thu_muc_du_lieu=tmp / "data", cong_song=lambda c: True, chan_doan_kho=lambda r: None,
              ffmpeg_ngoai=lambda: False, thoi_luong_media=lambda p: 1.0,
              bay_gio=lambda: datetime.now(MUI_GIO_VN))
    gt.update(kw)
    return MoiTruong(**gt)


def du_an_tv(tmp: Path) -> tuple[Path, Path]:
    a = tmp / "goc" / f"A_{UID}"
    (a / "raw").mkdir(parents=True, exist_ok=True)
    (a / "kich-ban").mkdir(exist_ok=True)
    b = tmp / "goc" / f"B_{UID}"
    (b / "takes").mkdir(parents=True, exist_ok=True)
    (b / "takes" / "t.mp4").write_bytes(b"x")
    (b / "output").mkdir(exist_ok=True)
    return a, b


def loai_tv(tmp: Path, kich_ban: list[dict]):
    """taovideo THẬT (lap_buoc thật: lenh_claude_song + phiếu + 1 BuocChay song=True), chỉ thay argv[0] bằng Claude
    giả chạy bằng python. Đối soát thật (doi_soat_taovideo) trên cây tạm."""
    fake, kb = ghi_kb(tmp, kich_ban)
    goc = DANH_MUC["taovideo"]

    def lap(ts, viec, mt):
        ds = goc.lap_buoc(ts, viec, mt)
        assert len(ds) == 1 and ds[0].song and ds[0].argv[0] == str(mt.claude_exe)
        return [dataclasses.replace(ds[0], argv=[PY, str(fake), str(kb)] + ds[0].argv[1:])]
    return dataclasses.replace(goc, lap_buoc=lap), kb


def khoa_test() -> Ed25519PrivateKey:
    v = json.loads((TOOLS / "runner" / "vector_ky.json").read_text(encoding="utf-8"))
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(v["seed_test_hex"]))


def ky_duyet(khoa, v: dict, loi: str) -> dict:
    luc = datetime.now(MUI_GIO_VN).isoformat(timespec="seconds")
    chuoi = chu_ky.chuoi_ky_duyet(v["id"], v["loai"], chu_ky.json_chuan(v["tham_so"]), loi, luc, "nhan")
    ky = base64.urlsafe_b64encode(khoa.sign(chuoi)).rstrip(b"=").decode("ascii")
    return {"loi_duyet": loi, "duyet_boi": "nhan", "duyet_luc": luc, "chu_ky_duyet": ky}


class SoGia:
    """Sổ tiêu giả (như KV Worker), gọi qua vl.tieu_duyet thật."""

    def __init__(self, khoa):
        self.khoa = khoa
        self.da: set[str] = set()
        self.goi: list[dict] = []

    def http(self, url, headers, body, timeout_s):
        d = json.loads(body)
        self.goi.append(d)
        if d["chu_ky_duyet"] in self.da:
            return 409, b"{}"
        self.da.add(d["chu_ky_duyet"])
        ky = base64.urlsafe_b64encode(self.khoa.sign(chu_ky.chuoi_tieu_duyet(d["id"], d["chu_ky_duyet"], d["nonce"])))
        return 200, json.dumps({"ky": ky.rstrip(b"=").decode("ascii")}).encode()

    def __call__(self, id, ckd):
        return vl.tieu_duyet("https://worker.test", "K" * 64, self.khoa.public_key(), id, ckd, goi_http=self.http)


def duyet_lan(kho: KhoViec, khoa, id: str, n: int) -> None:
    kho.chuyen(id, ["cho_duyet"], "cho", "nhan", "duyệt (chữ ký hợp lệ)", buoc="chay",
               **ky_duyet(khoa, kho.lay(id), f"Duyệt lần {n}"))


def sua_db(tmp: Path, id: str, **cot) -> None:
    c = sqlite3.connect(tmp / "data" / "runner.db")
    try:
        c.execute(f"UPDATE viec SET {', '.join(f'{k}=?' for k in cot)} WHERE id=?", (*cot.values(), id))
        c.commit()
    finally:
        c.close()


def lam_tv(tmp: Path, kich_ban: list[dict], **hm_them):
    """(bo, kho, viec đã duyệt ở 'cho', kb, sổ tiêu, khoá, dự án A)."""
    a, b = du_an_tv(tmp)
    loai, kb = loai_tv(tmp, kich_ban)
    khoa = khoa_test()
    so = SoGia(khoa)
    mt = lam_mt(tmp)
    kho = KhoViec(tmp / "data" / "runner.db", mt.bay_gio)
    bo = vl.BoChay(kho, mt, dict(HAN_MUC_TRAN, **hm_them), tmp / "data" / "log",
                   lambda s: s.replace("BIMAT123456789", "***"), danh_muc={"taovideo": loai}, nghi_s=0.05,
                   khoa_cong_khai=khoa.public_key(), tieu=so, im_lang_song_s=IM_LANG, quet_mp3_s=0.1)
    ts = {"uid": UID, "du_an_a": ma_du_an(a), "du_an_b": ma_du_an(b), "wm": "khong"}
    v = kho.tao("taovideo", UID, ts, "gpu", "cho_duyet", "nhan", session_id=str(uuid.uuid4()))
    duyet_lan(kho, khoa, v["id"], 1)
    return bo, kho, kho.lay(v["id"]), kb, so, khoa, a


def chay_nen(bo: vl.BoChay) -> tuple[dict, threading.Thread]:
    v = bo.nhan_viec("gpu")
    assert v is not None
    t = threading.Thread(target=bo.chay_mot, args=(v,), daemon=True)
    t.start()
    return v, t


def xong_luong(t: threading.Thread, han_s=40) -> None:
    t.join(han_s)
    assert not t.is_alive(), "chay_mot không kết thúc"


def trang(kho, id, *tt_) -> dict | None:
    v = kho.lay(id)
    return v if v["trang_thai"] in tt_ else None


def ghi_chu_su_kien(kho, id) -> list[str]:
    return [e["ghi_chu"] for e in kho.su_kien(id)]


def log_viec(tmp: Path, id: str) -> str:
    p = tmp / "data" / "log" / f"{id}.log"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def ps_re_ma(x) -> bool:
    return isinstance(x, str) and bool(RE_MA_CAU_HOI.fullmatch(x))


_CODEX = {"name": "Agent", "input": {"subagent_type": "codex:codex-rescue", "prompt": "x"}}


def test_1_hoi_chon_tra_loi_qua_stdin_roi_done_thi_xong(tmp_path):
    bo, kho, v, kb, so, _, _ = lam_tv(tmp_path, [{"luot": [
        {"viec": [_asst(), _ket(CAN_CHON, 0.1)]},
        {"viec": [_asst("làm tiếp"), _ket(DONE, 0.2)]}]}])
    id = v["id"]
    _, t = chay_nen(bo)
    s = cho(lambda: trang(kho, id, "can_tra_loi"))
    assert s["pid"] and s["pid_tao_luc"] and s["cau_hoi"]["loai"] == "chon"            # giữ pid khi chờ
    assert s["cau_hoi"]["lua_chon"] == ["Tạo lại", "Bỏ qua"]
    assert bo.co_phien_song(id) and bo.trang_thai_lan()["phien_song"] == [id]
    assert ps_re_ma(s["cau_hoi"]["ma"])                                                # c) mã câu hỏi
    moi = bo.tra_loi_song(id, "nhan", "Tạo lại", s["cau_hoi"]["ma"])
    assert moi["trang_thai"] == "dang_chay" and moi["pid"] == s["pid"] and moi["cau_hoi"] is None
    xong_luong(t)
    s = kho.lay(id)
    assert s["trang_thai"] == "xong" and s["pid"] is None, s
    assert s["ket_qua"]["trang_thai_agent"] == "DONE" and "doi_soat" in s["ket_qua"]
    assert round(s["chi_phi_usd"], 6) == 0.2 and s["so_lan_claude"] == 1
    msg = tin_nhan(kb)
    assert len(msg) == 2 and msg[0].startswith("PHIẾU " + id) and "CHẾ ĐỘ CHẠY" in msg[0]
    assert "TRẢ LỜI CỦA NGƯỜI DÙNG" in msg[1] and "Tạo lại" in msg[1]
    assert any(d["loai"] == "eof" for d in nhat_ky(kb))                                # đóng stdin gọn
    assert [(r["cau_hoi"], r["noi_dung"]) for r in kho.tra_loi_cua(id)] == [("Tạo lại voice hỏng?", "Tạo lại")]
    assert not bo.co_phien_song(id) and bo.trang_thai_lan()["phien_song"] == []
    assert len(so.goi) == 1 and s["so_lan_tieu"] == 1                                   # tiêu đúng 1 lần
    args = nhat_ky(kb)[0]["args"]
    assert "--input-format" in args and "--resume" not in args
    assert args[args.index("--session-id") + 1] == s["session_id"] != v["session_id"]    # session_id mới mỗi lần sinh


def test_2_viec_nen_cho_nen_roi_tu_thuc_done(tmp_path):
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": [{"viec": [
        {"k": "nen_bat", "id": "t1"}, _asst("render nền"), _ket("Đã chạy render nền, chờ thông báo.", 0.1),
        {"k": "ngu", "s": 1.2}, {"k": "nen_xong", "id": "t1"}, _asst("render xong"), _ket(DONE, 0.2)]}]}])
    _, t = chay_nen(bo)
    xong_luong(t)
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong", s
    assert any("việc nền" in g for g in ghi_chu_su_kien(kho, v["id"])), kho.su_kien(v["id"])
    assert len(tin_nhan(kb)) == 1                                                       # không nhắc khi chờ nền
    assert s["can_ban"] is None


def test_3_khong_ro_nhac_mot_lan_roi_hoi_khong_ro(tmp_path):
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"ver": "2.1.999", "luot": [
        {"viec": [_ket("Đang làm dở…")]}, {"viec": [_ket("Vẫn đang làm")]}, {"viec": [_ket(DONE)]}]}])
    id = v["id"]
    _, t = chay_nen(bo)
    s = cho(lambda: trang(kho, id, "can_tra_loi"))
    assert s["cau_hoi"]["loai"] == "khong_ro", s
    msg = tin_nhan(kb)
    assert msg[1:] == [TIN_NHAC]
    assert any("2.1.999" in (g or "") for g in ghi_chu_su_kien(kho, id) + [s.get("can_ban") or ""])
    bo.tra_loi_song(id, "nhan", "tiep_tuc", s["cau_hoi"]["ma"])
    xong_luong(t)
    s = kho.lay(id)
    assert s["trang_thai"] == "xong" and tin_nhan(kb).count(TIN_NHAC) == 1
    assert any("2.1.999" in c for c in s["ket_qua"]["canh_bao"]), s["ket_qua"]   # FX-27 P3-2: không mất sau 'hoi'
    assert "2.1.999" in log_viec(tmp_path, id)


def test_5a_cau_hoi_bi_rut_lai_viec_ve_dang_chay(tmp_path):
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": [{"viec": [
        {"k": "nen_bat", "id": "t1"}, _ket(CAN_CHON), {"k": "ngu", "s": 1.5}, {"k": "nen_xong", "id": "t1"},
        _asst("tự thức"), {"k": "nen_bat", "id": "t2"}, _ket("Chờ render tiếp"), {"k": "moc", "ten": "xong"},
        {"k": "ngu", "s": 60}]}]}])
    id = v["id"]
    _, t = chay_nen(bo)
    cho(lambda: trang(kho, id, "can_tra_loi"))
    s = cho(lambda: (lambda x: x if x["trang_thai"] == "dang_chay" and x["can_ban"] else None)(kho.lay(id)))
    assert s["cau_hoi"] is None and s["pid"], s
    assert any("rút" in g for g in ghi_chu_su_kien(kho, id))
    kho.chuyen(id, list(DANG_MO), "huy", "nhan", "huỷ từ web")
    bo.bao_huy(id)
    xong_luong(t)
    assert kho.lay(id)["trang_thai"] == "huy"


def test_5b_tra_loi_xep_hang_cho_cau_bi_rut_lai_thi_bi_huy(tmp_path):
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": [{"viec": [
        {"k": "nen_bat", "id": "t1"}, _ket(CAN_CHON), {"k": "ngu", "s": 1.0}, {"k": "nen_xong", "id": "t1"},
        _asst("tự thức"), {"k": "moc", "ten": "thuc"}, {"k": "ngu", "s": 2.0}, {"k": "nen_bat", "id": "t2"},
        _ket("Chờ render tiếp"), {"k": "ngu", "s": 60}]}]}])
    id = v["id"]
    _, t = chay_nen(bo)
    ma = cho(lambda: trang(kho, id, "can_tra_loi"))["cau_hoi"]["ma"]
    cho(lambda: any(d["loai"] == "moc" for d in nhat_ky(kb)))
    time.sleep(0.3)                                              # runner chắc chắn đã đọc sự kiện assistant (dang_lam)
    bo.tra_loi_song(id, "nhan", "Tạo lại", ma)                   # agent đang làm → tin nằm hàng đợi
    cho(lambda: "huỷ 1 tin" in log_viec(tmp_path, id))
    time.sleep(0.5)
    assert len(tin_nhan(kb)) == 1                                # câu trả lời KHÔNG tới stdin
    assert kho.lay(id)["trang_thai"] == "dang_chay"
    kho.chuyen(id, list(DANG_MO), "huy", "nhan", "huỷ từ web")
    bo.bao_huy(id)
    xong_luong(t)


def test_6_chi_phi_chenh_lech_ghi_db(tmp_path):
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": [{"viec": [
        {"k": "nen_bat", "id": "t1"}, _ket("chờ 1", 0.1), {"k": "ngu", "s": 0.8}, {"k": "nen_xong", "id": "t1"},
        {"k": "nen_bat", "id": "t2"}, _asst(), _ket("chờ 2", 0.3), {"k": "ngu", "s": 0.8},
        {"k": "nen_xong", "id": "t2"}, _asst(), _ket(DONE, 0.25)]}]}])
    _, t = chay_nen(bo)
    xong_luong(t)
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong" and round(s["chi_phi_usd"], 6) == 0.55, s


def test_6b_vuot_tran_usd_giet_va_max_budget_bang_tran_hieu_luc(tmp_path):
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": [{"viec": [
        {"k": "nen_bat", "id": "t1"}, _ket("chờ 1", 0.1), {"k": "ngu", "s": 0.8}, {"k": "nen_xong", "id": "t1"},
        {"k": "nen_bat", "id": "t2"}, _asst(), _ket("chờ 2", 0.3), {"k": "ngu", "s": 0.8},
        {"k": "nen_xong", "id": "t2"}, _asst(), _ket("chờ 3", 0.25), {"k": "ngu", "s": 60}]}]}],
        taovideo_usd_viec=0.5)
    _, t = chay_nen(bo)
    xong_luong(t)
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and "USD" in s["loi"] and s["pid"] is None, s
    args = nhat_ky(kb)[0]["args"]
    assert args[args.index("--max-budget-usd") + 1] == "0.5"                   # c) trần hiệu lực (cau_hinh hạ)
    assert not song(nhat_ky(kb)[0]["pid"])


def test_16_error_max_budget_usd_dong_stdin_loi_cham_tran_usd(tmp_path):
    """Tiêu chí 16 (S-4 #5): result error_max_budget_usd → ĐÓNG stdin (không giết) → loi "Chạm trần USD";
    mã thoát 1 sau đó không coi là tự chết; argv có --max-budget-usd 60."""
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"ma_eof": 1, "luot": [{"viec": [
        _ket("", 60.01, loi=True, subtype="error_max_budget_usd")]}]}])
    _, t = chay_nen(bo)
    xong_luong(t)
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and "Chạm trần USD" in s["loi"] and "tự thoát" not in s["loi"], s
    assert any(d["loai"] == "eof" for d in nhat_ky(kb))                        # đóng stdin, không giết
    assert "giết cả cây" not in log_viec(tmp_path, v["id"])
    args = nhat_ky(kb)[0]["args"]
    assert args[args.index("--max-budget-usd") + 1] == "60"


def test_15_hai_tin_xep_hang_moi_result_mot_tin(tmp_path):
    """Tiêu chí 15a (S-4 #4): 2 tin xếp hàng cùng lúc → tin đầu ghi sau result 1, tin sau chờ result 2."""
    p, kb = lam_phien(tmp_path, [{"luot": [{"viec": [_ket("a")]}, {"viec": [_ket("b")]}, {"viec": [_ket("c")]}]}])
    p.gui("PHIẾU")
    da = {"gui": False}

    def nhip(tinh, luc):
        if tinh.loai == "ket_luot" and tinh.so_ket_luot == 1 and not da["gui"]:
            da["gui"] = p.gui("X") and p.gui("Y")
        elif tinh.loai == "ket_luot" and tinh.so_ket_luot == 3:
            p.dong()
    kq = p.chay(lambda pid, tl: None, lambda sk, luc, d: None, nhip, threading.Event())
    assert kq.ly_do_dung == "dong_stdin"
    nk = nhat_ky(kb)
    tin = [d for d in nk if d["loai"] == "tin"]
    ket = [d for d in nk if d["loai"] == "ket"]
    assert [t["noi"] for t in tin] == ["PHIẾU", "X", "Y"]
    # So theo thứ tự dòng nhật ký của Claude giả (một luồng ghi tuần tự), không so time.time(): trên Windows hai
    # mốc liền nhau có thể bằng nhau tới từng chữ số → so "<" chặt chập chờn.
    vt = {id(d): i for i, d in enumerate(nk)}
    assert vt[id(ket[0])] < vt[id(tin[1])] < vt[id(ket[1])] < vt[id(tin[2])] < vt[id(ket[2])]


def test_15_tin_mang_ma_cau_hoi_cu_bi_bo(tmp_path):
    """Tiêu chí 15b (mức PhienSong): tin trả lời gắn mã câu hỏi sinh ở result khác result hiện tại → bỏ + log."""
    p, kb = lam_phien(tmp_path, [{"luot": [{"viec": [_ket("hỏi")]}, {"viec": [_ket("tiếp")]}]}])
    p.gui("PHIẾU")
    da = {"n": 0}

    def nhip(tinh, luc):
        if tinh.loai == "ket_luot" and tinh.so_ket_luot == 1 and da["n"] == 0:
            da["n"] = 1
            p.dat_cau_hoi("q00000000000a", 0)            # câu hỏi của result trước (đã bị thay)
            p.gui("TRẢ LỜI CŨ", "q00000000000a")
            p.dat_cau_hoi("q00000000000b", 1)
            p.gui("TRẢ LỜI ĐÚNG", "q00000000000b")
        elif tinh.loai == "ket_luot" and tinh.so_ket_luot == 2:
            p.dong()
    kq = p.chay(lambda pid, tl: None, lambda sk, luc, d: None, nhip, threading.Event())
    assert kq.ly_do_dung == "dong_stdin"
    assert tin_nhan(kb) == ["PHIẾU", "TRẢ LỜI ĐÚNG"]
    assert "bỏ câu trả lời cho câu hỏi q00000000000a — câu hỏi đã đổi" in (tmp_path / "p.log").read_text(
        encoding="utf-8")


def test_15_q1_tu_thuc_hoi_q2_tra_loi_q1_bi_bo_ma_lech_sai_trang_thai(tmp_path):
    """Tiêu chí 15c: câu q1 → agent tự thức hỏi q2 → trả lời mang q1 không tới stdin; tra_loi_song mã lệch →
    SaiTrangThai; trả lời đúng q2 → tới stdin → DONE → xong."""
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": [
        {"viec": [{"k": "nen_bat", "id": "t1"}, _ket(CAN_CHON), {"k": "ngu", "s": 1.0}, {"k": "nen_xong", "id": "t1"},
                  _asst("tự thức"), {"k": "moc", "ten": "thuc"}, {"k": "ngu", "s": 2.0},
                  _ket("Cần chốt lại.\nCẦN_USER: Giá bán?\nLOẠI: chon\nLỰA_CHỌN: 99k | 129k")]},
        {"viec": [_ket(DONE)]}]}])
    id = v["id"]
    _, t = chay_nen(bo)
    q1 = cho(lambda: trang(kho, id, "can_tra_loi"))["cau_hoi"]["ma"]
    cho(lambda: any(d["loai"] == "moc" for d in nhat_ky(kb)))
    time.sleep(0.3)
    bo.tra_loi_song(id, "nhan", "Tạo lại", q1)                            # agent đang làm → xếp hàng
    s = cho(lambda: (lambda x: x if x["trang_thai"] == "can_tra_loi" and x["cau_hoi"]["noi_dung"] == "Giá bán?"
                     else None)(kho.lay(id)))
    q2 = s["cau_hoi"]["ma"]
    assert ps_re_ma(q1) and ps_re_ma(q2) and q1 != q2
    with pytest.raises(SaiTrangThai):
        bo.tra_loi_song(id, "nhan", "99k", q1)                            # mã lệch câu đang treo
    bo.tra_loi_song(id, "nhan", "129k", q2)
    xong_luong(t)
    msg = tin_nhan(kb)
    assert len(msg) == 2 and "129k" in msg[1] and not any("Tạo lại" in m and "TRẢ LỜI" in m for m in msg), msg
    assert kho.lay(id)["trang_thai"] == "xong"


def test_17_agent_foreground_task_started_va_notification_khong_cho_nen(tmp_path):
    """Tiêu chí 17 (S-4 #8): Agent foreground sinh task_started + task_notification completed → tập việc nền rỗng,
    KHONG_RO → nhắc (không đứng cho_nen)."""
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": [
        {"viec": [_asst(tools=[{"name": "Agent", "input": {"subagent_type": "general-purpose", "prompt": "x"}}]),
                  {"k": "nen_bat", "id": "a1"}, _asst("con đọc", tools=[{"name": "Read"}], parent="tu0_1_0"),
                  {"k": "nen_xong", "id": "a1"}, _ket("Subagent xong, đang tổng hợp")]},
        {"viec": [_ket(DONE)]}]}])
    _, t = chay_nen(bo)
    xong_luong(t)
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong", s
    assert tin_nhan(kb)[1] == TIN_NHAC
    assert not any("việc nền" in g for g in ghi_chu_su_kien(kho, v["id"]))


def test_d_che_truong_ket_thuc_giu_ma():
    ch = CanNguoiDung("chon", "khoá BIMAT123456789?", ("A", "B"), "q0123456789ab")
    ra = vl.che_truong_ket_thuc({"cau_hoi": ch}, lambda s: s.replace("BIMAT123456789", "***"))["cau_hoi"]
    assert ra == CanNguoiDung("chon", "khoá ***?", ("A", "B"), "q0123456789ab")
    ra = vl.che_truong_ket_thuc({"cau_hoi": ch.thanh_dict()}, lambda s: s)["cau_hoi"]
    assert ra.ma == "q0123456789ab"


# ---------------- đầu–cuối: BoChay thật + api.tao_handler thật (HTTP) + Claude giả ----------------

def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def test_dau_cuoi_http_cau_hoi_co_ma_tra_loi_dung_ma_toi_stdin_ma_cu_409(tmp_path):
    import http.client
    import secrets
    from http.server import ThreadingHTTPServer
    bo, kho, v, kb, _, khoa, _ = lam_tv(tmp_path, [{"luot": [
        {"viec": [_ket(CAN_CHON)]}, {"viec": [_ket(DONE)]}]}])
    id = v["id"]
    khoa_runner = secrets.token_hex(32)
    H = _api.tao_handler(kho, bo.mt, khoa_runner, khoa.public_key(), bo.hm, [], bo.bao_huy, bo.doc_log,
                         bo.trang_thai_lan, che=bo.che, tra_loi_song=bo.tra_loi_song, co_phien_song=bo.co_phien_song)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    th = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    th.start()

    def goi(method, path, body=None):
        h = {"x-runner-key": khoa_runner}
        data = None
        if method == "POST":
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            ngay, n = int(time.time() * 1000), secrets.token_hex(16)
            h.update({"content-type": "application/json", "x-ky-ngay": str(ngay), "x-ky-nonce": n,
                      "x-ky": _b64url(khoa.sign(chu_ky.chuoi_ky_request("POST", path, ngay, n, data)))})
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
        try:
            c.request(method, path, body=data, headers=h)
            r = c.getresponse()
            return r.status, json.loads(r.read().decode("utf-8"))
        finally:
            c.close()
    try:
        _, t = chay_nen(bo)
        cho(lambda: trang(kho, id, "can_tra_loi"))
        s, d = goi("GET", f"/viec/{id}")
        assert s == 200, d
        vr = d["viec"]
        ma = vr["cau_hoi"]["ma"]
        assert ps_re_ma(ma) and vr["phien_song"] is True
        s, d = goi("POST", f"/viec/{id}/tra-loi", {"tra_loi": "Tạo lại", "boi": "nhan", "da_xac_nhan_mat_khau": True,
                                                    "ma_cau_hoi": "q" + "0" * 12})
        assert s == 409, d                                                   # mã cũ/lệch
        assert kho.lay(id)["trang_thai"] == "can_tra_loi" and kho.tra_loi_cua(id) == []
        s, d = goi("POST", f"/viec/{id}/tra-loi", {"tra_loi": "Tạo lại", "boi": "nhan", "da_xac_nhan_mat_khau": True,
                                                    "ma_cau_hoi": ma})
        assert s == 200 and d["viec"]["trang_thai"] == "dang_chay", d
        xong_luong(t)
        msg = tin_nhan(kb)
        assert len(msg) == 2 and "TRẢ LỜI CỦA NGƯỜI DÙNG" in msg[1] and "Tạo lại" in msg[1]
        assert kho.lay(id)["trang_thai"] == "xong"
        s, d = goi("POST", f"/viec/{id}/tra-loi", {"tra_loi": "Tạo lại", "boi": "nhan", "da_xac_nhan_mat_khau": True,
                                                    "ma_cau_hoi": ma})
        assert s == 409, d                                                   # phiên đã đóng
    finally:
        srv.shutdown()
        srv.server_close()


def test_7_qua_25_mp3_adam_thi_giet(tmp_path):
    bo, kho, v, kb, _, _, a = lam_tv(tmp_path, [{"luot": [{"viec": [{"k": "mp3", "n": 26}, {"k": "ngu", "s": 60}]}]}])
    t0 = time.monotonic()
    _, t = chay_nen(bo)
    xong_luong(t)
    assert time.monotonic() - t0 < 30
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and "vượt trần voice GenMax (đếm file thật)" in s["loi"], s
    assert not song(nhat_ky(kb)[0]["pid"])


def test_8_codex_bang_tran_nhan_tin_vuot_thi_giet(tmp_path):
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": [
        {"viec": [_asst(tools=[_CODEX, _CODEX]), _ket("Đang làm")]},
        {"viec": [_asst(tools=[_CODEX]), {"k": "ngu", "s": 60}]}]}], codex_luot_viec=2)
    _, t = chay_nen(bo)
    xong_luong(t)
    s = kho.lay(v["id"])
    msg = tin_nhan(kb)
    assert msg[1] == TIN_TRAN_CODEX.format(n=2) and TIN_NHAC not in msg, msg
    assert s["trang_thai"] == "loi" and "Codex" in s["loi"] and s["ket_qua"]["so_codex"] == 3, s


@pytest.mark.parametrize("co_nen", [False, True])
def test_9_het_gio_cho_tra_loi(tmp_path, co_nen):
    viec = ([{"k": "nen_bat", "id": "t1"}] if co_nen else []) + [_ket(CAN_CHON)]
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": [{"viec": viec}]}], taovideo_cho_s=1)
    _, t = chay_nen(bo)
    xong_luong(t)
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and "Hết giờ chờ trả lời câu hỏi: Tạo lại voice hỏng?" in s["loi"], s
    assert s["ket_qua"]["cau_hoi_treo"] == "Tạo lại voice hỏng?"                     # a)
    eof = any(d["loai"] == "eof" for d in nhat_ky(kb))
    if co_nen:
        assert "giết cả cây" in log_viec(tmp_path, v["id"]) and not song(nhat_ky(kb)[0]["pid"])
    else:
        assert eof and "đóng stdin" in log_viec(tmp_path, v["id"])


def test_10_huy_luc_can_tra_loi_giet_ca_cay(tmp_path):
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": [{"viec": [{"k": "con"}, _ket(CAN_CHON)]}]}])
    id = v["id"]
    _, t = chay_nen(bo)
    cho(lambda: trang(kho, id, "can_tra_loi"))
    kho.chuyen(id, list(DANG_MO), "huy", "nhan", "huỷ từ web")          # như api.p_huy
    bo.bao_huy(id)
    xong_luong(t)
    assert kho.lay(id)["trang_thai"] == "huy"
    nk = nhat_ky(kb)
    con = [d["pid"] for d in nk if d["loai"] == "con"][0]
    assert not song(nk[0]["pid"]) and cho(lambda: not song(con), 10)
    assert not bo.co_phien_song(id) and bo.trang_thai_lan()["lan"]["gpu"] is None


def test_11_khoi_dong_lai_can_tra_loi_pid_chet_thi_loi_doi_soat_va_doi_ten_mp3(tmp_path, monkeypatch):
    monkeypatch.setattr(tt, "da_gan_job_object", lambda: True)
    a, b = du_an_tv(tmp_path)
    mt = lam_mt(tmp_path, thoi_luong_media=lambda p: None if p.name.startswith("hong") else 2.0)
    kho = KhoViec(tmp_path / "data" / "runner.db", mt.bay_gio)
    bo = vl.BoChay(kho, mt, dict(HAN_MUC_TRAN), tmp_path / "data" / "log", lambda s: s,
                   danh_muc={"taovideo": DANH_MUC["taovideo"]})
    ts = {"uid": UID, "du_an_a": ma_du_an(a), "du_an_b": ma_du_an(b), "wm": "khong"}
    v = kho.tao("taovideo", UID, ts, "gpu", "cho_duyet", "nhan", session_id=str(uuid.uuid4()))
    p = subprocess.Popen([PY, "-c", "pass"])
    p.wait(30)
    bat_dau = (datetime.now(MUI_GIO_VN) - timedelta(minutes=5)).isoformat(timespec="seconds")
    sua_db(tmp_path, v["id"], trang_thai="can_tra_loi", pid=p.pid, pid_tao_luc=time.time() - 60,
           bat_dau_luc=bat_dau, cau_hoi=json.dumps({"loai": "chon", "noi_dung": "Tạo lại voice hỏng?",
                                                  "lua_chon": ["A", "B"]}))
    (a / "voice").mkdir()
    (a / "voice" / "hong_01_adam.mp3").write_bytes(b"")
    (a / "voice" / "tot_01_adam.mp3").write_bytes(b"ID3")
    kq = bo.khoi_dong()
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and s["pid"] is None, s
    assert "Bị ngắt" in s["loi"] and "Bước A" in s["loi"] and "Xin duyệt lại" in s["loi"], s["loi"]
    assert s["ket_qua"]["cau_hoi_treo"] == "Tạo lại voice hỏng?"
    assert (a / "voice" / f"hong_01_adam.mp3.hong-{v['id']}").exists()
    assert (a / "voice" / "tot_01_adam.mp3").exists()
    assert v["id"] in kq["doi_soat"]


def test_12_tra_loi_song_khi_khong_co_phien(tmp_path):
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": []}])
    with pytest.raises(KhongCoPhien):
        bo.tra_loi_song(v["id"], "nhan", "A", "q0123456789ab")
    with pytest.raises(KhongCoPhien):
        bo.tra_loi_song("j20261118000000abcd", "nhan", "A", "q0123456789ab")
    assert bo.co_phien_song(v["id"]) is False


@pytest.mark.parametrize("parent", [None, "toolu_cha"])
def test_13_cong_cu_ngoai_danh_sach_ke_ca_subagent_thi_giet(tmp_path, parent):
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"tools": ["Agent", "Task", "Bash", "Read"], "luot": [{"viec": [
        _asst(tools=[{"name": "Read"}]), _asst("con", tools=[{"name": "WebFetch", "input": {"url": "x"}}],
                                               parent=parent), {"k": "ngu", "s": 60}]}]}])
    _, t = chay_nen(bo)
    xong_luong(t)
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and "WebFetch" in s["loi"] and "ngoài danh sách" in s["loi"], s
    assert not song(nhat_ky(kb)[0]["pid"])


def test_14_xin_duyet_lai_phien_moi_lan_chay_tiep_tieu_mot_lan(tmp_path):
    bo, kho, v, kb, so, khoa, _ = lam_tv(tmp_path, [{"luot": [{"viec": [_asst(tools=[_CODEX]), _ket(CAN_CHON)]}]},
                                                    {"luot": [{"viec": [_ket(DONE)]}]}], taovideo_cho_s=1)
    id = v["id"]
    _, t = chay_nen(bo)
    xong_luong(t)
    s = kho.lay(id)
    assert s["trang_thai"] == "loi" and s["ket_qua"]["so_codex"] == 1 and len(so.goi) == 1, s
    kho.chuyen(id, ["loi"], "cho_duyet", "nhan", "xin duyệt lại", loi_duyet=None, duyet_boi=None, duyet_luc=None,
               chu_ky_duyet=None, ket_qua=_api.ket_qua_xin_duyet_lai(s))
    duyet_lan(kho, khoa, id, 2)
    _, t = chay_nen(bo)
    xong_luong(t)
    s = kho.lay(id)
    assert s["trang_thai"] == "xong", s
    bd = [d for d in nhat_ky(kb) if d["loai"] == "bat_dau"]
    sid = [d["args"][d["args"].index("--session-id") + 1] for d in bd]
    assert len(bd) == 2 and sid[0] != sid[1] and "--resume" not in bd[1]["args"]
    phieu2 = tin_nhan(kb, 1)[0]
    assert "LẦN CHẠY TIẾP" in phieu2 and "Hết giờ chờ trả lời câu hỏi" in phieu2
    assert "Câu hỏi còn treo: Tạo lại voice hỏng?" in phieu2 and "Duyệt lần 2" in phieu2
    assert len(so.goi) == 2 and s["so_lan_tieu"] == 2                                   # mỗi lần chạy tiêu 1 lần
    assert s["ket_qua"]["so_codex"] == 0                                                # đặt lại khi tiêu mới
    assert "ly_do_duyet_lai" not in s["ket_qua"] and "cau_hoi_treo" not in s["ket_qua"]


def test_tu_thoat_giua_chung_thi_loi_kem_stderr_va_doi_soat(tmp_path):
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": [{"viec": [
        _asst(), {"k": "stderr", "text": "panic BIMAT123456789"}, {"k": "thoat", "ma": 2}]}]}])
    _, t = chay_nen(bo)
    xong_luong(t)
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and "mã 2" in s["loi"] and "Bước A" in s["loi"], s
    assert "panic ***" in s["loi"] and "BIMAT123456789" not in s["loi"]


def test_loi_luot_het_quota_thi_dong_loi_va_tam_dung_claude(tmp_path):
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": [{"viec": [
        _ket("You've hit your session limit · resets 12:20am", loi=True)]}]}])
    _, t = chay_nen(bo)
    xong_luong(t)
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and "session limit" in s["loi"], s
    assert bo.trang_thai_lan()["tam_dung_claude_den"] is not None
    assert any(d["loai"] == "eof" for d in nhat_ky(kb))


def test_het_gio_lam_giet(tmp_path):
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": [{"viec": [_asst(), {"k": "ngu", "s": 60}]}]}],
                                     taovideo_lam_s=1)
    _, t = chay_nen(bo)
    xong_luong(t)
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and "Quá giờ làm" in s["loi"], s


# ---------------- FX-27 (review R-22) ----------------

def test_fx27_p2_1_tra_loi_kem_tin_codex_khong_bi_xoa_khong_ghi_nham_rut_cau_hoi(tmp_path):
    """P2-1: chạm trần Codex lúc đang hỏi → tra_loi_song xếp [trả lời, TIN_TRAN_CODEX]. Result sau câu trả lời KHÔNG
    được coi là rút câu hỏi, tin Codex phải tới stdin (không bị bo_hang_doi xoá, không bị thay bằng TIN_NHAC)."""
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": [
        {"viec": [_asst(tools=[_CODEX, _CODEX]), _ket(CAN_CHON)]},
        {"viec": [_ket("Đang làm tiếp")]},
        {"viec": [_ket(DONE)]}]}], codex_luot_viec=2)
    id = v["id"]
    _, t = chay_nen(bo)
    s = cho(lambda: trang(kho, id, "can_tra_loi"))
    bo.tra_loi_song(id, "nhan", "Tạo lại", s["cau_hoi"]["ma"])
    xong_luong(t)
    msg = tin_nhan(kb)
    assert len(msg) == 3 and "Tạo lại" in msg[1] and msg[2] == TIN_TRAN_CODEX.format(n=2), msg
    assert kho.lay(id)["trang_thai"] == "xong"
    assert "rút lại" not in log_viec(tmp_path, id)


def test_fx27_p2_2_co_phien_song_dung_toi_khi_chot_trang_thai_cuoi(tmp_path):
    """P2-2: hết giờ chờ (còn việc nền) → giết; trong lúc luồng làn còn đổi tên mp3/đối soát, co_phien_song phải
    còn True (api chặn Xin duyệt lại) tới khi trạng thái cuối đã ghi; sau đó False và việc là loi đủ trường."""
    bo, kho, v, kb, _, _, _ = lam_tv(tmp_path, [{"luot": [{"viec": [{"k": "nen_bat", "id": "t1"}, _ket(CAN_CHON)]}]}],
                                     taovideo_cho_s=1)
    id = v["id"]
    vao, tha = threading.Event(), threading.Event()
    goc = bo._doi_soat_song

    def doi_soat_cham(viec):
        vao.set()
        tha.wait(20)
        return goc(viec)
    bo._doi_soat_song = doi_soat_cham
    _, t = chay_nen(bo)
    assert vao.wait(20)
    s = kho.lay(id)
    assert s["trang_thai"] == "can_tra_loi" and s["pid"], s                 # đang chốt, chưa ghi trạng thái cuối
    assert bo.co_phien_song(id) is True                                     # → api từ chối Xin duyệt lại (409)
    tha.set()
    xong_luong(t)
    s = kho.lay(id)
    assert bo.co_phien_song(id) is False
    assert s["trang_thai"] == "loi" and s["pid"] is None and s["ket_qua"]["cau_hoi_treo"] == "Tạo lại voice hỏng?"
    assert "chi_phi_usd_phien" in s["ket_qua"] and "doi_soat" in s["ket_qua"]
