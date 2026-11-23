"""Test vòng chạy việc (§4.3–4.7, §5.1, §6.1–6.3) — chạy:
PYTHONIOENCODING=utf-8 python -B -m pytest tools/test_runner_vong_lap.py -q

Mọi tiến trình con là chương trình giả `python` viết vào tmp_path (Claude giả, kho.py giả, agy giả).
DB, log, dữ liệu đều ở tmp_path. Không gọi claude.exe/agy.exe thật, không đụng E:\\kho-runner (chỉ so chuỗi).
"""
import dataclasses
import json
import os
import subprocess
import sys
import textwrap
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import psutil
import pytest

TOOLS = Path(__file__).parent
sys.path.insert(0, str(TOOLS))
from runner import vong_lap as vl  # noqa: E402
from runner import thuc_thi as tt  # noqa: E402
from runner.danh_muc import DANH_MUC, LoaiViec  # noqa: E402
from runner.du_an import ma_du_an  # noqa: E402
from runner.han_muc import HAN_MUC_TRAN  # noqa: E402
from runner.kho_viec import KhoViec  # noqa: E402
from runner.kieu import MUI_GIO_VN, BuocChay, CanNguoiDung, MoiTruong  # noqa: E402

PY = sys.executable
UID = "1729384756102938475"
UID2 = "1729384756102938476"

CLAUDE_GIA = r'''
import json, os, sys, time
kb_path = sys.argv[1]
args = sys.argv[2:]
stdin = sys.stdin.buffer.read().decode("utf-8")
kb = json.load(open(kb_path, encoding="utf-8"))
ghi = kb_path + ".goi.jsonl"
n = sum(1 for _ in open(ghi, encoding="utf-8")) if os.path.exists(ghi) else 0
with open(ghi, "a", encoding="utf-8") as f:
    f.write(json.dumps({"args": args, "stdin": stdin, "pid": os.getpid()}, ensure_ascii=False) + "\n")
lan = kb[min(n, len(kb) - 1)]
sid = args[args.index("--resume") + 1] if "--resume" in args else args[args.index("--session-id") + 1]
def out(o):
    sys.stdout.write(json.dumps(o, ensure_ascii=False) + "\n"); sys.stdout.flush()
if lan.get("asst_truoc_init"):
    out({"type": "assistant", "parent_tool_use_id": None,
         "message": {"id": f"m{n}_truoc", "content": [{"type": "text", "text": "chưa init"}]}})
if lan.get("init", True):
    init = {"type": "system", "subtype": "init", "session_id": sid, "model": "gia", "permissionMode": "dontAsk",
            "apiKeySource": "none", "agents": [], "tools": lan.get("tools", ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill"]),
            "mcp_servers": lan.get("mcp", [])}
    if lan.get("khong_sid"):
        del init["session_id"]
    if lan.get("bo_tools"):
        del init["tools"]
    out(init)
for i in range(lan.get("so_msg", 1)):
    tu = [{"type": "tool_use", "id": f"tu{n}_{i}_{j}", "name": t["name"] if isinstance(t, dict) else t,
           "input": t.get("input", {}) if isinstance(t, dict) else {}}
          for j, t in enumerate(lan.get("tool_use", []))]
    out({"type": "assistant", "parent_tool_use_id": None,
         "message": {"id": f"m{n}_{i}", "content": [{"type": "text", "text": "đang làm"}] + tu}})
time.sleep(lan.get("ngu", 0))
if lan.get("ket_qua") is not None:
    out({"type": "result", "subtype": "success", "is_error": lan.get("is_error", False), "session_id": sid,
         "total_cost_usd": lan.get("usd", 0.01), "num_turns": lan.get("so_msg", 1), "duration_ms": 5,
         "result": lan["ket_qua"], "permission_denials": lan.get("tu_choi", [])})
sys.exit(lan.get("ma", 0))
'''


# ---------------- tiện ích ----------------

class Dong:
    def __init__(self, t: datetime):
        self.t = t

    def __call__(self):
        return self.t


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


def loai_script(ma: str, lan: str, argv, *, tai_nguyen=(), het_gio=60, dk=None, dau_ra="xong",
                tu_chay_lai=True) -> LoaiViec:
    def lap(ts, viec, mt):
        a = argv(ts, viec, mt) if callable(argv) else argv
        return [BuocChay("s", list(a), str(mt.thu_muc_du_lieu), None, {}, False, het_gio)]
    return LoaiViec(ma=ma, ten=ma, dot=3, lan_chay=lan, ton_tien=False, agent=None, tu_chay_lai=tu_chay_lai,
                    het_gio_s=het_gio, tai_nguyen=frozenset(tai_nguyen), tham_so=(),
                    kiem_tham_so=lambda ts, mt: ts, tinh_khoa=lambda ts: str(ts.get("k", "x")),
                    trang_thai_dau=lambda ts: ("cho", "chay"), dieu_kien_truoc=dk or (lambda ts, mt: None),
                    lap_buoc=lap, kiem_dau_ra=lambda ts, viec, mt: dau_ra)


def loai_claude(tmp: Path, kich_ban: list[dict], dau_ra="xong") -> tuple[LoaiViec, Path]:
    """phan_tich_uid thật (lệnh + phiếu thật), chỉ thay argv[0] bằng Claude giả chạy bằng python."""
    fake = tmp / "claude_gia.py"
    fake.write_text(CLAUDE_GIA, encoding="utf-8")
    kb = tmp / f"kb_{uuid.uuid4().hex[:6]}.json"
    kb.write_text(json.dumps(kich_ban, ensure_ascii=False), encoding="utf-8")
    goc = DANH_MUC["phan_tich_uid"]

    def lap(ts, viec, mt):
        b = goc.lap_buoc(ts, viec, mt)[0]
        assert b.argv[0] == str(mt.claude_exe) and b.la_claude
        return [dataclasses.replace(b, argv=[PY, str(fake), str(kb)] + b.argv[1:], cwd=str(tmp))]
    loai = dataclasses.replace(goc, dieu_kien_truoc=lambda ts, mt: None, lap_buoc=lap,
                               kiem_dau_ra=lambda ts, viec, mt: dau_ra)
    return loai, kb


def cac_lan_goi(kb: Path) -> list[dict]:
    p = Path(str(kb) + ".goi.jsonl")
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def lam_bo(tmp: Path, mt: MoiTruong, dm: dict, hm=None, kho=None, **kw) -> tuple[vl.BoChay, KhoViec]:
    kho = kho or KhoViec(tmp / "data" / "runner.db", mt.bay_gio)
    bo = vl.BoChay(kho, mt, dict(hm or HAN_MUC_TRAN), tmp / "data" / "log", lambda s: s.replace("BIMAT123456789", "***"),
                   danh_muc=dm, nghi_s=0.05, **kw)
    return bo, kho


def tao(kho: KhoViec, loai: LoaiViec, ts: dict, khoa: str | None = None) -> dict:
    return kho.tao(loai.ma, khoa or str(ts.get("k") or ts.get("uid") or "x"), ts, loai.lan_chay, "cho", "nhan",
                   session_id=str(uuid.uuid4()) if loai.agent else None)


def chay_lan(bo: vl.BoChay, lan: str) -> dict | None:
    v = bo.nhan_viec(lan)
    if v is not None:
        bo.chay_mot(v)
    return v


def tra_loi(kho: KhoViec, id: str, gia_tri: str) -> None:
    """Giống api.p_tra_loi: thêm câu trả lời rồi can_tra_loi → cho."""
    v = kho.lay(id)
    kho.them_tra_loi(id, "nhan", v["cau_hoi"]["noi_dung"], gia_tri)
    kho.chuyen(id, ["can_tra_loi"], "cho", "nhan", f"trả lời: {gia_tri}")


def song(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


# ---------------- logic thuần ----------------

def test_ly_do_tiep_tuc_bo_qua_tam_hoan():
    sk = [{"tu": None, "den": "cho", "ghi_chu": "tạo"},
          {"tu": "cho", "den": "dang_chay", "ghi_chu": ""},
          {"tu": "dang_chay", "den": "can_tra_loi", "ghi_chu": ""},
          {"tu": "can_tra_loi", "den": "cho", "ghi_chu": "trả lời: A"},
          {"tu": "cho", "den": "dang_chay", "ghi_chu": ""},
          {"tu": "dang_chay", "den": "cho", "ghi_chu": vl.TIEN_TO_HOAN + "git kho đang bận"},
          {"tu": "cho", "den": "dang_chay", "ghi_chu": ""}]
    assert vl.ly_do_tiep_tuc(sk) == ("tra_loi", "trả lời: A")
    assert vl.ly_do_tiep_tuc(sk[:2]) == ("moi", "tạo")
    assert vl.ly_do_tiep_tuc([{"tu": "loi", "den": "cho", "ghi_chu": "chạy tiếp"}])[0] == "chay_tiep"
    assert vl.ly_do_tiep_tuc([{"tu": "dang_chay", "den": "cho", "ghi_chu": "bị ngắt"}]) == ("khoi_dong", "bị ngắt")
    assert vl.ly_do_tiep_tuc([{"tu": "cho_duyet", "den": "cho", "ghi_chu": ""}])[0] == "duyet"
    assert vl.ly_do_tiep_tuc([]) == ("moi", "")


def test_cat_bien_utf8():
    s = "aé漢😀".encode("utf-8")
    for i in range(len(s) + 1):
        c = vl.cat_bien_utf8(s[:i], False)
        c.decode("utf-8")                         # không ném = không dở ký tự
        assert s[:i].startswith(c) and len(s[:i]) - len(c) < 4
    assert vl.cat_bien_utf8(b"dong1\ndong2 do", True) == b"dong1\n"


def test_phan_loai_ket_thuc_claude():
    def kq(**k):
        g = dict(ma_thoat=0, het_gio=False, bi_huy=False, vuot_luot=False, ket_qua=None, van_ban_cuoi="",
                 session_id=None, so_luot=0)
        g.update(k)
        return tt.KetQuaTienTrinh(**g)
    ok = {"session_id": "s", "chi_phi_usd": 0.1, "so_luot": 1, "loi": False, "van_ban": "TRẠNG THÁI: DONE",
          "bi_tu_choi": []}
    assert vl.phan_loai_ket_thuc_claude(kq(ket_qua=ok), 250, 60) is None
    assert vl.phan_loai_ket_thuc_claude(kq(bi_huy=True), 250, 60)[0] == "huy"
    assert vl.phan_loai_ket_thuc_claude(kq(het_gio=True), 250, 5400)[1]["loi"].startswith("Quá giờ 90 phút")
    den, tr, tam = vl.phan_loai_ket_thuc_claude(kq(vuot_luot=True), 250, 60)
    assert den == "can_tra_loi" and tr["cau_hoi"].loai == "khong_ro" and "250" in tr["cau_hoi"].noi_dung
    den, tr, tam = vl.phan_loai_ket_thuc_claude(
        kq(ket_qua=dict(ok, loi=True, van_ban="Claude AI usage limit reached"), ma_thoat=1), 250, 60)
    assert den == "loi" and tam is True
    den, tr, tam = vl.phan_loai_ket_thuc_claude(kq(ket_qua=dict(ok, loi=True, van_ban="Invalid API key")), 250, 60)
    assert den == "loi" and tam is False and "Invalid API key" in tr["loi"]
    # báo cáo DONE có nhắc "rate limit" (dữ liệu sản phẩm) KHÔNG bị coi là lỗi
    assert vl.phan_loai_ket_thuc_claude(kq(ket_qua=dict(ok, van_ban="TRẠNG THÁI: DONE\nDouyin rate limit")),
                                        250, 60) is None
    assert vl.phan_loai_ket_thuc_claude(kq(ma_thoat=1), 250, 60)[0] == "loi"


def test_chan_doan_kho_4_nhanh(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    bay = time.time()

    def git(nhanh="main", status="", rc_nhanh=0):
        def chay(args):
            if args[0] == "symbolic-ref":
                return (rc_nhanh, nhanh + "\n", "fatal: ref HEAD is not a symbolic ref" if rc_nhanh else "")
            assert args[:2] == ["status", "--porcelain"] and args[-2:] == ["--", "data"]
            return (0, status, "")
        return chay

    kw = dict(git_dang_chay=lambda: False, chay_git=git(), bay_gio_ts=bay)
    assert vl.chan_doan_kho_tu(repo, **kw) is None
    lock = repo / ".git" / "index.lock"
    lock.write_text("")
    os.utime(lock, (bay - 60, bay - 60))
    assert vl.chan_doan_kho_tu(repo, **kw) == "ban"                                # (1) khoá mới
    os.utime(lock, (bay - 3600, bay - 3600))
    assert vl.chan_doan_kho_tu(repo, **dict(kw, git_dang_chay=lambda: True)) == "ban"   # (1) git.exe đang chạy
    c = vl.chan_doan_kho_tu(repo, **kw)                                            # (2) khoá cũ, không git
    assert isinstance(c, CanNguoiDung) and c.loai == "viec_tay" and "index.lock" in c.noi_dung
    lock.unlink()
    c = vl.chan_doan_kho_tu(repo, **dict(kw, chay_git=git(nhanh="thu-nghiem")))   # (3) nhánh khác
    assert c.loai == "viec_tay" and "`thu-nghiem`" in c.noi_dung
    c = vl.chan_doan_kho_tu(repo, **dict(kw, chay_git=git(rc_nhanh=128)))           # HEAD tách rời
    assert c.loai == "viec_tay" and "main" in c.noi_dung
    ban_data = "".join(f" M data/{i}/info.json\n" for i in range(12))
    c = vl.chan_doan_kho_tu(repo, **dict(kw, chay_git=git(status=ban_data)))           # (4) data bẩn
    assert c.loai == "viec_tay" and "data/0/info.json" in c.noi_dung and "data/9/" in c.noi_dung
    assert "data/10/" not in c.noi_dung and "(+2)" in c.noi_dung


def test_ten_mutex_khong_dung_ten_that(tmp_path, monkeypatch):
    # chỉ so chuỗi đường dẫn: ten_mutex không tạo/ghi thư mục
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    assert vl.ten_mutex(Path(r"E:\kho-runner")) == tt.TEN_MUTEX
    assert vl.ten_mutex(Path("E:/kho-runner")) == tt.TEN_MUTEX
    # thư mục cũ %LOCALAPPDATA%\kho-runner không còn là mặc định → không dùng tên mutex thật
    assert vl.ten_mutex(tmp_path / "la" / "kho-runner") != tt.TEN_MUTEX
    a, b = vl.ten_mutex(tmp_path / "x"), vl.ten_mutex(tmp_path / "y")
    assert a != tt.TEN_MUTEX and a != b and a.startswith(tt.TEN_MUTEX + "-")


def test_thu_muc_runner_mac_dinh_la_o_e(tmp_path, monkeypatch):
    """FX-7: không đặt KHO_RUNNER_DIR → E:\\kho-runner (không rơi về %LOCALAPPDATA% bị MSIX chuyển hướng)."""
    monkeypatch.delenv("KHO_RUNNER_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    assert vl.thu_muc_runner() == Path(r"E:\kho-runner")
    assert vl.THU_MUC_RUNNER_MAC_DINH == Path(r"E:\kho-runner")
    monkeypatch.setenv("KHO_RUNNER_DIR", "")            # rỗng = coi như không đặt
    assert vl.thu_muc_runner() == Path(r"E:\kho-runner")
    assert not (tmp_path / "la").exists()


def test_thu_muc_runner_theo_bien_moi_truong(tmp_path, monkeypatch):
    monkeypatch.setenv("KHO_RUNNER_DIR", str(tmp_path / "du_lieu"))
    assert vl.thu_muc_runner() == tmp_path / "du_lieu"
    assert vl.ten_mutex(vl.thu_muc_runner()) != tt.TEN_MUTEX
    assert not (tmp_path / "du_lieu").exists()           # chỉ trả đường dẫn, không tạo thư mục


# ---------------- Claude giả ----------------

def test_claude_xong_danh_dau_phien_va_chi_phi(tmp_path):
    mt = lam_mt(tmp_path)
    # tool_use nằm trong bộ công cụ cho phép → KHÔNG bị chặn (R-05 P2-1, ca hợp lệ)
    loai, kb = loai_claude(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE\nXong.", "so_msg": 3, "usd": 0.25,
                                       "tool_use": ["Read", "Bash", "Skill"]}])
    bo, kho = lam_bo(tmp_path, mt, {"phan_tich_uid": loai})
    v = tao(kho, loai, {"uid": UID})
    assert chay_lan(bo, "nhe")["id"] == v["id"]
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong", s
    assert s["phien_da_tao"] == 1 and s["so_lan_claude"] == 1 and s["so_luot_claude"] == 3
    assert abs(s["chi_phi_usd"] - 0.25) < 1e-9 and s["pid"] is None
    goi = cac_lan_goi(kb)
    assert len(goi) == 1
    a = goi[0]["args"]
    assert a[a.index("--session-id") + 1] == v["session_id"] and "--resume" not in a
    assert "--tools" in a and goi[0]["stdin"].startswith("PHIẾU " + v["id"])
    assert (tmp_path / "data" / "log" / f"{v['id']}.jsonl").is_file()
    assert bo.trang_thai_lan()["lan"] == {"gpu": None, "nhe": None}


def test_claude_can_user_chon_roi_resume(tmp_path):
    mt = lam_mt(tmp_path)
    loai, kb = loai_claude(tmp_path, [
        {"ket_qua": "Cần chốt.\nCẦN_USER: Chọn thư mục nào?\nLOẠI: chon\nLỰA_CHỌN: Thư mục A | Thư mục B"},
        {"ket_qua": "TRẠNG THÁI: DONE\nĐã dùng B."}])
    bo, kho = lam_bo(tmp_path, mt, {"phan_tich_uid": loai})
    v = tao(kho, loai, {"uid": UID})
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "can_tra_loi"
    assert s["cau_hoi"] == {"loai": "chon", "noi_dung": "Chọn thư mục nào?", "lua_chon": ["Thư mục A", "Thư mục B"]}
    tra_loi(kho, v["id"], "Thư mục B")
    chay_lan(bo, "nhe")
    assert kho.lay(v["id"])["trang_thai"] == "xong"
    goi = cac_lan_goi(kb)
    assert len(goi) == 2
    a2 = goi[1]["args"]
    assert a2[a2.index("--resume") + 1] == v["session_id"] and "--session-id" not in a2
    st = goi[1]["stdin"]
    assert st.startswith("TRẢ LỜI CỦA NGƯỜI DÙNG cho \"Chọn thư mục nào?\"")
    assert "<<<\nThư mục B\n>>>" in st and "PHIẾU" not in st
    assert kho.lay(v["id"])["so_lan_claude"] == 2


def test_claude_chua_tao_phien_thi_lan_2_dung_session_id(tmp_path):
    mt = lam_mt(tmp_path)
    # so_msg 0: phiên không có init thì cũng không được có assistant (assistant trước init = vi phạm, R-05 P2-1)
    loai, kb = loai_claude(tmp_path, [{"init": False, "so_msg": 0, "ket_qua": None, "ma": 1},
                                      {"ket_qua": "TRẠNG THÁI: DONE"}])
    bo, kho = lam_bo(tmp_path, mt, {"phan_tich_uid": loai})
    v = tao(kho, loai, {"uid": UID})
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and s["phien_da_tao"] == 0 and "không có sự kiện kết quả" in s["loi"]
    kho.chuyen(v["id"], ["loi"], "cho", "he_thong", "chạy lại thử")
    chay_lan(bo, "nhe")
    assert kho.lay(v["id"])["trang_thai"] == "xong"
    a2 = cac_lan_goi(kb)[1]
    assert "--resume" not in a2["args"] and a2["args"][a2["args"].index("--session-id") + 1] == v["session_id"]
    assert a2["stdin"].startswith("PHIẾU ")


def test_claude_vuot_tran_luot(tmp_path):
    mt = lam_mt(tmp_path)
    loai, kb = loai_claude(tmp_path, [{"so_msg": 260, "ngu": 30, "ket_qua": "TRẠNG THÁI: DONE"}])
    assert loai.tran_luot == 250
    bo, kho = lam_bo(tmp_path, mt, {"phan_tich_uid": loai})
    v = tao(kho, loai, {"uid": UID})
    t0 = time.monotonic()
    chay_lan(bo, "nhe")
    assert time.monotonic() - t0 < 25
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "can_tra_loi" and s["cau_hoi"]["loai"] == "khong_ro"
    assert "trần 250 lượt" in s["cau_hoi"]["noi_dung"]
    assert not song(cac_lan_goi(kb)[0]["pid"])


@pytest.mark.parametrize("kich_ban, phai_co", [
    ({"tools": ["Read", "mcp__engram__mem_save"]}, "mcp__engram__mem_save"),             # init lọt mcp
    ({"bo_tools": True}, "tools"),                                                      # (a) init thiếu tools
    ({"tools": "Read,Write"}, "tools"),                                                 # (a) tools sai dạng
    ({"khong_sid": True, "tools": ["Read", "mcp__boardroom__x"]}, "mcp__boardroom__x"),  # init không session_id
    ({"tool_use": ["Read", "mcp__engram__mem_save"]}, "mcp__engram__mem_save"),         # (b) assistant gọi mcp
    ({"asst_truoc_init": True}, "init"),                                                # (c) assistant trước init
])
def test_claude_co_cong_cu_ngoai_danh_sach_thi_dung_ngay(tmp_path, kich_ban, phai_co):
    """Không phụ thuộc argv thật của lệnh claude (cờ MCP do danh_muc quyết): Claude giả tự phát sự kiện
    vi phạm, runner phải giết phiên và chuyển việc sang loi."""
    mt = lam_mt(tmp_path)
    loai, kb = loai_claude(tmp_path, [dict(kich_ban, ngu=30, ket_qua="TRẠNG THÁI: DONE")])
    bo, kho = lam_bo(tmp_path, mt, {"phan_tich_uid": loai})
    v = tao(kho, loai, {"uid": UID})
    t0 = time.monotonic()
    chay_lan(bo, "nhe")
    assert time.monotonic() - t0 < 25
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and "ngoài danh sách" in s["loi"] and phai_co in s["loi"], s
    assert not song(cac_lan_goi(kb)[0]["pid"])
    assert bo.trang_thai_lan()["lan"]["nhe"] is None


def test_claude_che_cau_hoi_va_lua_chon(tmp_path):
    """R-05 P2-2: cau_hoi.noi_dung và từng lua_chon đi ra web đã che bí mật."""
    mt = lam_mt(tmp_path)
    loai, kb = loai_claude(tmp_path, [{"ket_qua": "Cần chốt.\nCẦN_USER: Dùng khoá BIMAT123456789 không?\n"
                                                  "LOẠI: chon\nLỰA_CHỌN: Dùng BIMAT123456789 | Bỏ"}])
    bo, kho = lam_bo(tmp_path, mt, {"phan_tich_uid": loai})
    v = tao(kho, loai, {"uid": UID})
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "can_tra_loi"
    assert s["cau_hoi"] == {"loai": "chon", "noi_dung": "Dùng khoá *** không?", "lua_chon": ["Dùng ***", "Bỏ"]}
    assert "BIMAT123456789" not in json.dumps(s, ensure_ascii=False)


def test_claude_needs_approval_che_loi_va_gon_bi_tu_choi(tmp_path):
    """R-05 P2-2: loi (nhánh NEEDS_APPROVAL việc miễn phí) đã che; bi_tu_choi chỉ giữ {tool_name, input}
    đã che, input ≤200 ký tự, tối đa 20 mục."""
    mt = lam_mt(tmp_path)
    tu_choi = [{"tool_name": "Bash", "tool_input": {"command": f"curl -H BIMAT123456789 {i} " + "x" * 500},
                "tool_use_id": f"tu_{i}"} for i in range(25)]
    loai, kb = loai_claude(tmp_path, [{"ket_qua": "TRẠNG THÁI: NEEDS_APPROVAL\nCần gọi API với khoá BIMAT123456789",
                                       "tu_choi": tu_choi}])
    bo, kho = lam_bo(tmp_path, mt, {"phan_tich_uid": loai})
    v = tao(kho, loai, {"uid": UID})
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and "***" in s["loi"], s
    btc = s["ket_qua"]["bi_tu_choi"]
    assert len(btc) == 20
    for m in btc:
        assert set(m) == {"tool_name", "input"} and m["tool_name"] == "Bash"
        assert isinstance(m["input"], str) and len(m["input"]) <= 200 and "***" in m["input"]
    assert "BIMAT123456789" not in json.dumps(s, ensure_ascii=False)


def test_gon_bi_tu_choi_logic_thuan():
    che = lambda s: s.replace("BIMAT", "***")                       # noqa: E731
    ds = [{"tool_name": "Write", "tool_input": {"file_path": "BIMAT.txt"}}, "rác", {"tool_input": "y" * 999},
          {"tool_name": "x" * 500, "tool_input": None}]
    g = vl.gon_bi_tu_choi(ds, che)
    assert g[0] == {"tool_name": "Write", "input": '{"file_path": "***.txt"}'}
    assert g[1] == {"tool_name": "?", "input": '"rác"'}
    assert g[2]["tool_name"] == "?" and len(g[2]["input"]) == 200
    assert len(g[3]["tool_name"]) <= 100 and g[3]["input"] == "null"
    assert len(vl.gon_bi_tu_choi([{}] * 50, che)) == 20
    assert vl.gon_bi_tu_choi("khong-list", che) == []


def test_cong_chi_phi_sai_trang_thai_thi_log_warning(tmp_path, caplog):
    """R-05 P3-7: không ghi được chi phí lượt Claude → phải có log.warning (không mất dấu vết)."""
    mt = lam_mt(tmp_path)
    loai, kb = loai_claude(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE", "usd": 0.5}])
    bo, kho = lam_bo(tmp_path, mt, {"phan_tich_uid": loai})
    v = tao(kho, loai, {"uid": UID})
    goc = kho.cong_chi_phi

    def cong(id, usd, so_luot, bat_dau):
        if not bat_dau:
            raise vl.SaiTrangThai("đã bị huỷ từ web")
        return goc(id, usd, so_luot, bat_dau)
    kho.cong_chi_phi = cong
    with caplog.at_level("WARNING", logger="kho_runner.vong_lap"):
        chay_lan(bo, "nhe")
    assert any(r.levelname == "WARNING" and v["id"] in r.getMessage() and "0.5" in r.getMessage()
               for r in caplog.records), caplog.records


def test_claude_het_quota_tam_dung_claude_nhung_script_van_chay(tmp_path):
    mt = lam_mt(tmp_path)
    loai, kb = loai_claude(tmp_path, [{"ket_qua": "Claude AI usage limit reached", "is_error": True, "ma": 1}])
    s_loai = loai_script("s_nhe", "nhe", [PY, "-c", "print('ok')"])
    bo, kho = lam_bo(tmp_path, mt, {"phan_tich_uid": loai, "s_nhe": s_loai})
    v1 = tao(kho, loai, {"uid": UID})
    chay_lan(bo, "nhe")
    assert kho.lay(v1["id"])["trang_thai"] == "loi"
    assert bo.trang_thai_lan()["tam_dung_claude_den"] is not None
    v2 = tao(kho, loai, {"uid": UID2})
    v3 = tao(kho, s_loai, {"k": "a"})
    assert chay_lan(bo, "nhe")["id"] == v3["id"]                 # Claude đứng chờ, script vẫn chạy
    assert kho.lay(v2["id"])["trang_thai"] == "cho"
    assert chay_lan(bo, "nhe") is None


def test_cham_claude_viec_ngay_thi_dung_cho(tmp_path):
    mt = lam_mt(tmp_path)
    loai, kb = loai_claude(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE"}])
    s_loai = loai_script("s_nhe", "nhe", [PY, "-c", "print('ok')"])
    hm = dict(HAN_MUC_TRAN, claude_viec_ngay=1)
    bo, kho = lam_bo(tmp_path, mt, {"phan_tich_uid": loai, "s_nhe": s_loai}, hm=hm)
    v1 = tao(kho, loai, {"uid": UID})
    chay_lan(bo, "nhe")
    assert kho.lay(v1["id"])["trang_thai"] == "xong"
    v2 = tao(kho, loai, {"uid": UID2})
    v3 = tao(kho, s_loai, {"k": "a"})
    assert chay_lan(bo, "nhe")["id"] == v3["id"]
    assert kho.lay(v2["id"])["trang_thai"] == "cho"
    assert chay_lan(bo, "nhe") is None
    assert len(cac_lan_goi(kb)) == 1


def test_viec_resume_tu_hom_qua_khong_tu_dem_minh(tmp_path):
    """P3-8: kiem_han_muc gọi TRƯỚC khi nhận → bat_dau_luc cũ (hôm qua) chưa bị đổi thành hôm nay."""
    dong = Dong(datetime.now(MUI_GIO_VN) - timedelta(days=1))
    mt = lam_mt(tmp_path, bay_gio=dong)
    loai, kb = loai_claude(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE"}])
    hm = dict(HAN_MUC_TRAN, claude_viec_ngay=1)
    bo, kho = lam_bo(tmp_path, mt, {"phan_tich_uid": loai}, hm=hm)
    v = tao(kho, loai, {"uid": UID})
    kho.nhan_viec_ke("nhe", set(), lambda m: frozenset())
    kho.cong_chi_phi(v["id"], 0.1, 2, True)
    kho.danh_dau_phien(v["id"])
    kho.chuyen(v["id"], ["dang_chay"], "loi", "he_thong", "lỗi", loi="mất mạng")
    kho.chuyen(v["id"], ["loi"], "cho", "nhan", "chạy tiếp (resume phiên Claude)")
    dong.t = datetime.now(MUI_GIO_VN)
    assert chay_lan(bo, "nhe")["id"] == v["id"]
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong"
    st = cac_lan_goi(kb)[0]
    assert "--resume" in st["args"] and st["stdin"].startswith("Phiên trước dừng vì: mất mạng.")


# ---------------- script giả ----------------

def test_qua_gio_giet_ca_cay(tmp_path):
    mt = lam_mt(tmp_path)
    s = loai_script("cham", "nhe", [PY, "-c", "import time; time.sleep(60)"], het_gio=1)
    bo, kho = lam_bo(tmp_path, mt, {"cham": s})
    v = tao(kho, s, {"k": "a"})
    pid = {}
    goc = kho.ghi_tien_trinh

    def ghi(id, p, tl):
        pid["p"] = p
        goc(id, p, tl)
    kho.ghi_tien_trinh = ghi
    t0 = time.monotonic()
    chay_lan(bo, "nhe")
    assert time.monotonic() - t0 < 20
    st = kho.lay(v["id"])
    assert st["trang_thai"] == "loi" and "Quá giờ" in st["loi"] and st["pid"] is None
    assert not song(pid["p"])


def test_dieu_kien_truoc_hong_luc_nhan_tra_ve_cho_va_khong_chan_lan(tmp_path):
    """§4.3 dang_chay→cho + P3-3: việc đầu hàng bị hoãn không chặn việc sau trong làn."""
    mt = lam_mt(tmp_path)
    a = loai_script("loai_a", "nhe", [PY, "-c", "print(1)"], dk=lambda ts, mt: "ban", tai_nguyen=("kho",))
    b = loai_script("loai_b", "nhe", [PY, "-c", "print(2)"])
    bo, kho = lam_bo(tmp_path, mt, {"loai_a": a, "loai_b": b}, cho_lai_s=0.5)
    va = tao(kho, a, {"k": "a"})
    time.sleep(1.1)                                    # tao_luc khác giây → FIFO rõ ràng
    vb = tao(kho, b, {"k": "b"})
    assert chay_lan(bo, "nhe")["id"] == va["id"]
    sa = kho.lay(va["id"])
    assert sa["trang_thai"] == "cho"
    ev = kho.su_kien(va["id"])[-1]
    assert ev["tu"] == "dang_chay" and ev["den"] == "cho" and "git kho đang bận" in ev["ghi_chu"]
    assert "loai_a" in bo.trang_thai_lan()["tam_hoan"]
    assert bo.trang_thai_lan()["tai_nguyen"]["kho"] is None        # đã nhả kho
    assert chay_lan(bo, "nhe")["id"] == vb["id"]                    # không bị chặn đầu hàng
    assert kho.lay(vb["id"])["trang_thai"] == "xong"
    assert chay_lan(bo, "nhe") is None                              # loai_a còn trong 0.5 s hoãn
    time.sleep(0.6)
    assert chay_lan(bo, "nhe")["id"] == va["id"]                    # hết hoãn → thử lại


def test_dieu_kien_truoc_viec_tay(tmp_path):
    mt = lam_mt(tmp_path)
    a = loai_script("a", "nhe", [PY, "-c", "print(1)"], dk=lambda ts, mt: CanNguoiDung("viec_tay", "Mở Poster"))
    bo, kho = lam_bo(tmp_path, mt, {"a": a})
    v = tao(kho, a, {"k": "a"})
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "can_tra_loi" and s["cau_hoi"]["noi_dung"] == "Mở Poster"


def test_mutex_kho_hai_lan_khong_chay_cung_luc(tmp_path):
    mt = lam_mt(tmp_path)
    vet = tmp_path / "vet.txt"
    ma = ("import sys,time;f=open(sys.argv[1],'a');f.write(f'{sys.argv[2]} bd {time.time()}\\n');f.flush();"
          "time.sleep(1.5);f.write(f'{sys.argv[2]} kt {time.time()}\\n');f.close()")
    g = loai_script("k_gpu", "gpu", [PY, "-c", ma, str(vet), "gpu"], tai_nguyen=("kho",))
    n = loai_script("k_nhe", "nhe", [PY, "-c", ma, str(vet), "nhe"], tai_nguyen=("kho",))
    bo, kho = lam_bo(tmp_path, mt, {"k_gpu": g, "k_nhe": n})
    vg = tao(kho, g, {"k": "g"})
    vn = tao(kho, n, {"k": "n"})
    # tất định: làn gpu giữ kho → làn nhe không nhận được
    v = bo.nhan_viec("gpu")
    assert v["id"] == vg["id"] and bo.trang_thai_lan()["tai_nguyen"]["kho"] == vg["id"]
    assert bo.nhan_viec("nhe") is None
    bo.chay_mot(v)
    assert bo.trang_thai_lan()["tai_nguyen"]["kho"] is None
    # chạy thật 2 làn song song với 2 việc kho mới
    kho.tao("k_gpu", "g2", {"k": "g2"}, "gpu", "cho", "nhan")
    kho.tao("k_nhe", "n2", {"k": "n2"}, "nhe", "cho", "nhan")
    vet.write_text("")
    bo.bat_lan()
    try:
        han = time.monotonic() + 30
        while time.monotonic() < han and kho.dem()["xong"] < 4:
            time.sleep(0.1)
    finally:
        bo.dung()
    assert kho.dem()["xong"] == 4, kho.ds()
    moc = {}
    for d in vet.read_text().splitlines():
        lan, loai_moc, t = d.split()
        moc.setdefault(lan, {})[loai_moc] = float(t)
    assert set(moc) == {"gpu", "nhe"}
    a, b = sorted(moc.values(), key=lambda x: x["bd"])
    assert a["kt"] <= b["bd"], moc                       # không chồng thời gian


def test_khoa_chung_hai_luong_nhan_dong_thoi(tmp_path):
    """P3-4: 2 luồng nhận cùng lúc 2 việc cùng tài nguyên → chỉ một luồng được."""
    g = loai_script("k_gpu", "gpu", [PY, "-c", "1"], tai_nguyen=("kho",))
    n = loai_script("k_nhe", "nhe", [PY, "-c", "1"], tai_nguyen=("kho",))
    for vong in range(15):
        thu = tmp_path / f"v{vong}"
        thu.mkdir()
        bo, kho = lam_bo(thu, lam_mt(thu), {"k_gpu": g, "k_nhe": n})
        tao(kho, g, {"k": "g"})
        tao(kho, n, {"k": "n"})
        kq = {}
        rao = threading.Barrier(2)

        def lay(lan):
            rao.wait()
            kq[lan] = bo.nhan_viec(lan)
        ts = [threading.Thread(target=lay, args=(l,)) for l in ("gpu", "nhe")]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert sum(1 for v in kq.values() if v is not None) == 1, kq


def test_huy_khi_dang_chay(tmp_path):
    mt = lam_mt(tmp_path)
    s = loai_script("cham", "nhe", [PY, "-c", "import time; time.sleep(60)"])
    bo, kho = lam_bo(tmp_path, mt, {"cham": s})
    v = tao(kho, s, {"k": "a"})
    viec = bo.nhan_viec("nhe")
    t = threading.Thread(target=bo.chay_mot, args=(viec,))
    t.start()
    han = time.monotonic() + 10
    while time.monotonic() < han and not (kho.lay(v["id"]) or {}).get("pid"):
        time.sleep(0.05)
    pid = kho.lay(v["id"])["pid"]
    kho.chuyen(v["id"], ["dang_chay"], "huy", "nhan", "huỷ từ web")     # như api.p_huy
    bo.bao_huy(v["id"])
    t.join(timeout=20)
    assert not t.is_alive()
    assert kho.lay(v["id"])["trang_thai"] == "huy" and not song(pid)
    assert bo.trang_thai_lan()["lan"]["nhe"] is None


@pytest.mark.parametrize("co_job", [True, False])
def test_khoi_dong_lai_giet_cay_va_ve_cho_lan_thu_2(tmp_path, monkeypatch, co_job):
    """R-07 P2-1: PID tái dùng (create_time lệch) = gốc cũ đã chết, giống NoSuchProcess. Có Job Object → về cho;
    KHÔNG có Job Object → cháu mồ côi có thể sống → loi kiểm tay (trước đây về cho bất kể)."""
    monkeypatch.setattr(tt, "_JOB_RUNNER", object() if co_job else None)
    mt = lam_mt(tmp_path)
    s = loai_script("s", "nhe", [PY, "-c", "print(1)"], dau_ra="chua")
    bo, kho = lam_bo(tmp_path, mt, {"s": s})
    p1 = subprocess.Popen([PY, "-c", "import time; time.sleep(60)"])
    p2 = subprocess.Popen([PY, "-c", "import time; time.sleep(60)"])
    try:
        v1 = tao(kho, s, {"k": "a"})
        kho.nhan_viec_ke("nhe", set(), lambda m: frozenset())
        kho.ghi_tien_trinh(v1["id"], p1.pid, psutil.Process(p1.pid).create_time())
        v2 = tao(kho, s, {"k": "b"})
        kho.nhan_viec_ke("nhe", set(), lambda m: frozenset())
        kho.ghi_tien_trinh(v2["id"], p2.pid, psutil.Process(p2.pid).create_time() + 100)   # PID bị tái dùng
        kq = bo.khoi_dong()
        p1.wait(timeout=15)
        assert p1.poll() is not None
        assert p2.poll() is None                                    # không đụng PID đã bị tái dùng
        assert kq["giet"] == [p1.pid]
        st1 = kho.lay(v1["id"])
        assert st1["trang_thai"] == "cho" and st1["lan_thu"] == 2 and st1["pid"] is None
        st2 = kho.lay(v2["id"])
        if co_job:
            assert st2["trang_thai"] == "cho" and st2["lan_thu"] == 2 and st2["pid"] is None
            assert kq["con_song"] == []
        else:
            assert st2["trang_thai"] == "loi" and "kiểm tay" in st2["loi"] and st2["lan_thu"] == 1, st2
            assert kq["con_song"] == [p2.pid] and v2["id"] not in kq["doi_soat"]
        assert chay_lan(bo, "nhe")["id"] in (v1["id"], v2["id"])
    finally:
        for p in (p1, p2):
            if p.poll() is None:
                p.kill()
                p.wait(timeout=10)


def test_khoi_dong_lai_giet_khong_duoc_thi_loi_khong_ve_cho(tmp_path, monkeypatch):
    """R-05 P2-3: giet_cay trả False (tiến trình cũ còn sống) → việc sang loi, KHÔNG về cho (tránh chạy trùng)."""
    mt = lam_mt(tmp_path)
    s = loai_script("s", "nhe", [PY, "-c", "print(1)"], dau_ra="chua")
    bo, kho = lam_bo(tmp_path, mt, {"s": s})
    p1 = subprocess.Popen([PY, "-c", "import time; time.sleep(60)"])
    goi = []
    monkeypatch.setattr(vl.tt, "giet_cay", lambda pid, tl: goi.append(pid) or False)
    try:
        v1 = tao(kho, s, {"k": "a"})
        kho.nhan_viec_ke("nhe", set(), lambda m: frozenset())
        kho.ghi_tien_trinh(v1["id"], p1.pid, psutil.Process(p1.pid).create_time())
        kq = bo.khoi_dong()
        assert goi == [p1.pid]
        st = kho.lay(v1["id"])
        assert st["trang_thai"] == "loi" and "còn sống" in st["loi"] and str(p1.pid) in st["loi"], st
        assert st["lan_thu"] == 1
        assert kq["giet"] == [] and kq["con_song"] == [p1.pid]
        assert v1["id"] not in kq["doi_soat"]
        assert chay_lan(bo, "nhe") is None                          # không có gì để chạy lại tự động
    finally:
        if p1.poll() is None:
            p1.kill()
            p1.wait(timeout=10)


def test_trang_thai_lan_tra_id_va_loai(tmp_path):
    """R-05 P3-2: lan.gpu/lan.nhe là {id, loai} khi đang chạy, None khi rảnh."""
    mt = lam_mt(tmp_path)
    g = loai_script("k_gpu", "gpu", [PY, "-c", "1"])
    bo, kho = lam_bo(tmp_path, mt, {"k_gpu": g})
    v = tao(kho, g, {"k": "g"})
    viec = bo.nhan_viec("gpu")
    assert bo.trang_thai_lan()["lan"] == {"gpu": {"id": v["id"], "loai": "k_gpu"}, "nhe": None}
    bo.chay_mot(viec)
    assert bo.trang_thai_lan()["lan"] == {"gpu": None, "nhe": None}


def test_khoi_dong_lai_claude_co_phien_thi_resume_voi_tin_bi_ngat(tmp_path):
    mt = lam_mt(tmp_path)
    loai, kb = loai_claude(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE"}], dau_ra="chua")
    bo, kho = lam_bo(tmp_path, mt, {"phan_tich_uid": loai})
    v = tao(kho, loai, {"uid": UID})
    kho.nhan_viec_ke("nhe", set(), lambda m: frozenset())
    kho.danh_dau_phien(v["id"])
    bo.khoi_dong()
    st = kho.lay(v["id"])
    assert st["trang_thai"] == "cho" and st["lan_thu"] == 2
    chay_lan(bo, "nhe")
    g = cac_lan_goi(kb)[0]
    assert "--resume" in g["args"] and "bị ngắt khi máy tắt" in g["stdin"]


def test_voice_pv_doi_ten_mp3_hong_khi_khoi_dong_lai(tmp_path):
    me = "20261117-a"
    p = tmp_path / "goc" / f"du_an_{UID}"
    (p / "kich-ban").mkdir(parents=True)
    (p / "kich-ban" / f"{me}_kich-ban-da-cham.md").write_text("x")
    (p / "voice").mkdir()
    tl = {"a01": None, "a02": 3.5, "a03": 0.0}
    mt = lam_mt(tmp_path, thoi_luong_media=lambda f: tl[f.name.split("_")[1]],
                ds_ma_voice=lambda pp, m: ["a01", "a02"])
    loai = DANH_MUC["voice_pv"]
    bo, kho = lam_bo(tmp_path, mt, {"voice_pv": loai})
    ts = {"uid": UID, "du_an": ma_du_an(p), "me": me}
    v = kho.tao("voice_pv", f"{ts['du_an']}:{me}", ts, "gpu", "cho", "nhan")
    kho.nhan_viec_ke("gpu", set(), lambda m: frozenset())
    bd = datetime.fromisoformat(kho.lay(v["id"])["bat_dau_luc"]).timestamp()
    for ma, moc in (("a01", bd + 5), ("a02", bd + 5), ("a03", bd - 3600)):
        f = p / "voice" / f"{me}_{ma}_adam.mp3"
        f.write_bytes(b"x")
        os.utime(f, (moc, moc))
    bo.khoi_dong()
    ten = sorted(f.name for f in (p / "voice").iterdir())
    assert ten == sorted([f"{me}_a01_adam.mp3.hong-{v['id']}", f"{me}_a02_adam.mp3", f"{me}_a03_adam.mp3"])
    st = kho.lay(v["id"])
    assert st["trang_thai"] == "cho" and st["lan_thu"] == 2           # a01 thiếu → 'chua' → tự chạy lại


def test_xu_ly_link_moi_sinh_viec_con(tmp_path):
    mt = lam_mt(tmp_path)
    (tmp_path / "repo" / "tools").mkdir(parents=True)
    dong = [f"{UID}\thttps://a\tx", f"{UID2}\thttps://b\ty", f"{UID}\thttps://a\tlap", "tam-123456789012\thttps://vt\tz",
            "rác không khớp"]
    (tmp_path / "repo" / "tools" / "kho.py").write_text(
        "import sys\nprint(" + repr("\n".join(dong)) + ")\n", encoding="utf-8")
    dm = {"xu_ly_link_moi": DANH_MUC["xu_ly_link_moi"], "phan_tich_uid": DANH_MUC["phan_tich_uid"]}
    bo, kho = lam_bo(tmp_path, mt, dm)
    co_san = kho.tao("phan_tich_uid", UID2, {"uid": UID2}, "nhe", "can_tra_loi", "comeofage",
                     cau_hoi=CanNguoiDung("viec_tay", "x"), session_id=str(uuid.uuid4()))   # mở nhưng không nhận
    v = kho.tao("xu_ly_link_moi", "kho", {}, "nhe", "cho", "nhan")
    assert chay_lan(bo, "nhe")["id"] == v["id"]
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong", s
    kq = s["ket_qua"]
    assert kq["uid_trung"] == [UID2] and kq["link_tam"] == ["tam-123456789012"] and len(kq["viec_con"]) == 1
    con = kho.lay(kq["viec_con"][0])
    assert con["loai"] == "phan_tich_uid" and con["khoa"] == UID and con["cha_id"] == v["id"]
    assert con["trang_thai"] == "cho" and con["tao_boi"] == "nhan" and con["session_id"]
    assert kho.lay(co_san["id"])["cha_id"] is None


def test_douyin_agy_loi_thi_viec_tay_va_bao_can_ban(tmp_path):
    mt = lam_mt(tmp_path)
    (tmp_path / "sp" / f"sp_{UID}").mkdir()
    (tmp_path / "repo" / "data" / UID2).mkdir(parents=True)
    (tmp_path / "repo" / "data" / UID2 / "douyin.md").write_text("mẫu", encoding="utf-8")
    agy = tmp_path / "agy_gia.py"
    agy.write_text("print('Douyin hiện 验证 captcha'); import sys; sys.exit(2)", encoding="utf-8")
    goc = DANH_MUC["douyin_uid"]

    def lap(ts, viec, mt_):
        ds = goc.lap_buoc(ts, viec, mt_)
        assert [b.ten for b in ds] == ["ghi_prompt", "agy", "kho_ghi"] and ds[1].hien_cua_so
        return [ds[0], dataclasses.replace(ds[1], argv=[PY, str(agy)]), ds[2]]
    loai = dataclasses.replace(goc, lap_buoc=lap)
    bo, kho = lam_bo(tmp_path, mt, {"douyin_uid": loai})
    v = kho.tao("douyin_uid", UID, {"uid": UID}, "nhe", "cho", "nhan")
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "can_tra_loi" and s["cau_hoi"]["loai"] == "viec_tay"
    assert "captcha" in s["cau_hoi"]["noi_dung"]
    assert s["can_ban"] and "captcha" in s["can_ban"]
    d = tmp_path / "sp" / f"sp_{UID}" / "douyin"
    assert (d / "_prompt_antigravity.txt").read_text(encoding="utf-8").startswith("Đây là VIỆC THỰC TẾ")
    assert "验证" in (d / "_antigravity_log.txt").read_text(encoding="utf-8")


def test_doc_log_offset_va_che(tmp_path):
    mt = lam_mt(tmp_path)
    s = loai_script("s", "nhe", [PY, "-c", "print('khoá BIMAT123456789 ở đây'); print('dòng 2')"])
    bo, kho = lam_bo(tmp_path, mt, {"s": s})
    v = tao(kho, s, {"k": "a"})
    chay_lan(bo, "nhe")
    r = bo.doc_log(v["id"], 0)
    assert "BIMAT123456789" not in r["noi_dung"] and "khoá *** ở đây" in r["noi_dung"]
    assert r["het"] is True and r["den"] == (tmp_path / "data" / "log" / f"{v['id']}.log").stat().st_size
    r2 = bo.doc_log(v["id"], r["den"])
    assert r2["noi_dung"] == "" and r2["tu"] == r["den"]
    assert bo.doc_log(v["id"], 10 ** 9)["tu"] == r["den"]
    with pytest.raises(Exception):
        bo.doc_log("../runner", 0)
    # log > 64 KB: đọc theo khung, ghép lại đủ
    lon = tmp_path / "data" / "log" / "j20261117000000abcd.log"
    lon.write_bytes(("dòng tiếng Việt có dấu\n" * 6000).encode("utf-8"))
    tu, gom = 0, []
    while True:
        r = bo.doc_log("j20261117000000abcd", tu)
        gom.append(r["noi_dung"])
        if r["den"] == tu:
            break
        tu = r["den"]
    assert "".join(gom) == "dòng tiếng Việt có dấu\n" * 6000


def test_tong_kiem(tmp_path):
    (tmp_path / "runner").mkdir()
    (tmp_path / "runner" / "a.py").write_text("x")
    (tmp_path / "chay_runner.py").write_text("y")
    assert vl.kiem_tong(tmp_path)[0].startswith("không có TONG_KIEM.json")
    (tmp_path / "TONG_KIEM.json").write_text(json.dumps(vl.tinh_tong_kiem(tmp_path)))
    assert vl.kiem_tong(tmp_path) == []
    (tmp_path / "runner" / "a.py").write_text("bị sửa", encoding="utf-8")
    assert "runner/a.py" in vl.kiem_tong(tmp_path)[0]


# ---------------- FX-4 (R-06) ----------------

BI_MAT_VL = "Pw" + "4hN" * 20 + "z9"        # 64 ký tự, không khớp mẫu → chỉ che theo giá trị


def _che_vl(s: str) -> str:
    return s.replace(BI_MAT_VL, "***")


def lam_bo_che(tmp: Path, mt: MoiTruong, dm: dict, **kw) -> tuple[vl.BoChay, KhoViec]:
    kho = KhoViec(tmp / "data" / "runner.db", mt.bay_gio)
    return vl.BoChay(kho, mt, dict(HAN_MUC_TRAN), tmp / "data" / "log", _che_vl, danh_muc=dm, nghi_s=0.05,
                     **kw), kho


def test_doc_log_chua_het_khi_da_huy_ma_runner_con_giu(tmp_path):
    """R-06 P2-1: api chuyển huy TRƯỚC rồi bao_huy; runner còn ghi đuôi log → het phải False tới khi runner nhả id."""
    mt = lam_mt(tmp_path)
    s = loai_script("s", "nhe", [PY, "-c", "1"])
    bo, kho = lam_bo(tmp_path, mt, {"s": s})
    v = tao(kho, s, {"k": "a"})
    viec = bo.nhan_viec("nhe")
    assert viec["id"] == v["id"]
    bo._ghi_log(v["id"], "dòng 1")
    kho.chuyen(v["id"], ["dang_chay"], "huy", "nhan", "huỷ từ web")     # như api.p_huy
    r = bo.doc_log(v["id"], 0)
    assert r["het"] is False and "dòng 1" in r["noi_dung"]
    bo._ghi_log(v["id"], "kết thúc: mã 1 · bị huỷ")                      # đuôi ghi sau khi DB đã là huy
    bo._nha(v["id"], "nhe")
    r2 = bo.doc_log(v["id"], r["den"])
    assert "bị huỷ" in r2["noi_dung"] and r2["het"] is True


def test_doc_log_viec_mo_chua_chay_thi_chua_het(tmp_path):
    mt = lam_mt(tmp_path)
    s = loai_script("s", "nhe", [PY, "-c", "1"])
    bo, kho = lam_bo(tmp_path, mt, {"s": s})
    v = tao(kho, s, {"k": "a"})
    assert bo.doc_log(v["id"], 0)["het"] is False                       # 'cho' = mở → log còn có thể ghi
    kho.chuyen(v["id"], ["cho"], "huy", "nhan", "huỷ")
    assert bo.doc_log(v["id"], 0)["het"] is True


def test_doc_log_doc_trang_thai_truoc_roi_moi_stat(tmp_path, monkeypatch):
    """Thứ tự đọc: trạng thái DB trước, cỡ file sau (đọc ngược sẽ het=True sớm khi đuôi ghi giữa 2 lần đọc)."""
    mt = lam_mt(tmp_path)
    s = loai_script("s", "nhe", [PY, "-c", "1"])
    bo, kho = lam_bo(tmp_path, mt, {"s": s})
    v = tao(kho, s, {"k": "a"})
    bo._ghi_log(v["id"], "x")
    thu_tu = []
    lay_goc = kho.lay
    monkeypatch.setattr(kho, "lay", lambda id: thu_tu.append("lay") or lay_goc(id))
    stat_goc = Path.stat

    def stat_ghi(self, *a, **k):
        if self.suffix == ".log":
            thu_tu.append("stat")
        return stat_goc(self, *a, **k)
    monkeypatch.setattr(Path, "stat", stat_ghi)
    bo.doc_log(v["id"], 0)
    assert thu_tu[:2] == ["lay", "stat"], thu_tu


def test_script_loi_bi_mat_vat_qua_diem_cat_1200_khong_lo(tmp_path):
    """R-06 P3-1: bí mật vắt qua điểm cắt -1200 của đuôi stdout → che bản đủ rồi mới cắt."""
    mt = lam_mt(tmp_path)
    # đuôi sau bí mật dài 1180 ký tự → điểm cắt -1200 rơi vào giữa bí mật
    ma = f"import sys; print('{BI_MAT_VL}' + 'b' * 1180); sys.exit(3)"
    s = loai_script("s", "nhe", [PY, "-c", ma])
    bo, kho = lam_bo_che(tmp_path, mt, {"s": s})
    v = tao(kho, s, {"k": "a"})
    chay_lan(bo, "nhe")
    st = kho.lay(v["id"])
    assert st["trang_thai"] == "loi" and "thoát mã 3" in st["loi"]
    assert BI_MAT_VL[-20:] not in st["loi"] and BI_MAT_VL[:20] not in st["loi"], st["loi"][:80]


def test_script_xong_tom_tat_bi_mat_vat_qua_diem_cat_1500_khong_lo(tmp_path):
    mt = lam_mt(tmp_path)
    ma = f"print('{BI_MAT_VL}' + 'c' * 1470)"
    s = loai_script("s", "nhe", [PY, "-c", ma])
    bo, kho = lam_bo_che(tmp_path, mt, {"s": s})
    v = tao(kho, s, {"k": "a"})
    chay_lan(bo, "nhe")
    st = kho.lay(v["id"])
    assert st["trang_thai"] == "xong"
    assert BI_MAT_VL[-20:] not in st["ket_qua"]["tom_tat"] and st["ket_qua"]["tom_tat"].startswith("***")


def test_claude_tom_tat_bi_mat_o_vi_tri_1480_khong_lo(tmp_path):
    """Đúng ví dụ reviewer: khoá 64 ký tự ở vị trí 1480 của tom_tat → trước đây lộ 20 ký tự."""
    mt = lam_mt(tmp_path)
    dau = "TRẠNG THÁI: DONE\n"
    bao_cao = dau + "a" * (1480 - len(dau)) + BI_MAT_VL + " hết"
    loai, kb = loai_claude(tmp_path, [{"ket_qua": bao_cao}])
    bo, kho = lam_bo_che(tmp_path, mt, {"phan_tich_uid": loai})
    v = tao(kho, loai, {"uid": UID})
    chay_lan(bo, "nhe")
    st = kho.lay(v["id"])
    assert st["trang_thai"] == "xong", st
    assert BI_MAT_VL[:12] not in st["ket_qua"]["tom_tat"] and st["ket_qua"]["tom_tat"].endswith("*** hết")


def test_phan_loai_ket_thuc_claude_che_truoc_khi_cat():
    def kq(**k):
        g = dict(ma_thoat=1, het_gio=False, bi_huy=False, vuot_luot=False, ket_qua=None, van_ban_cuoi="",
                 session_id=None, so_luot=0)
        g.update(k)
        return tt.KetQuaTienTrinh(**g)
    vb = "x" * 780 + BI_MAT_VL                                          # cắt [:800] rơi giữa bí mật
    ok = {"session_id": "s", "chi_phi_usd": 0.0, "so_luot": 1, "loi": True, "van_ban": vb, "bi_tu_choi": []}
    assert BI_MAT_VL[:20] in vl.phan_loai_ket_thuc_claude(kq(ket_qua=ok), 250, 60)[1]["loi"]   # lỗi cũ
    loi = vl.phan_loai_ket_thuc_claude(kq(ket_qua=ok), 250, 60, _che_vl)[1]["loi"]
    assert BI_MAT_VL[:20] not in loi and loi.endswith("***")
    vb2 = BI_MAT_VL + "y" * 480                                         # cắt [-500:] rơi giữa bí mật
    loi2 = vl.phan_loai_ket_thuc_claude(kq(van_ban_cuoi=vb2), 250, 60, _che_vl)[1]["loi"]
    assert BI_MAT_VL[-20:] not in loi2 and "***" in loi2


def test_loi_bo_chay_viec_va_lap_buoc_duoc_che(tmp_path):
    """Thông điệp lỗi ra web (lỗi bộ chạy việc, không lập được lệnh, không chạy được bước) đều đã che."""
    from runner.kieu import ThamSoLoi

    mt = lam_mt(tmp_path)

    def lap_loi(ts, viec, mt_):
        raise ThamSoLoi("tham số hỏng " + BI_MAT_VL)

    def lap_no(ts, viec, mt_):
        raise RuntimeError("x" * 790 + BI_MAT_VL)
    a = dataclasses.replace(loai_script("a", "nhe", [PY]), lap_buoc=lap_loi)
    b = dataclasses.replace(loai_script("b", "nhe", [PY]), lap_buoc=lap_no)
    c = loai_script("c", "nhe", [str(tmp_path / ("khong_co_" + BI_MAT_VL + ".exe"))])
    bo, kho = lam_bo_che(tmp_path, mt, {"a": a, "b": b, "c": c})
    ids = [tao(kho, l, {"k": l.ma}, khoa=l.ma)["id"] for l in (a, b, c)]
    for _ in ids:
        chay_lan(bo, "nhe")
    for id in ids:
        st = kho.lay(id)
        assert st["trang_thai"] == "loi", st
        assert BI_MAT_VL[:20] not in json.dumps(st, ensure_ascii=False), st["loi"][-120:]
        for e in kho.su_kien(id):
            assert BI_MAT_VL[:20] not in (e.get("ghi_chu") or "")


def test_huy_ma_khong_giet_duoc_dua_canh_bao_ra_suc_khoe(tmp_path, monkeypatch):
    """R-06 P3-5: huỷ, giet_cay thất bại → thuc_thi bỏ chờ sau hạn, vong_lap đưa cảnh báo vào list canh_bao."""
    monkeypatch.setattr(tt, "giet_cay", lambda pid, tl: False)
    monkeypatch.setattr(tt, "_tao_job_rieng", lambda proc: None)
    monkeypatch.setattr(tt, "CHO_SAU_GIET_S", 1.0)
    mt = lam_mt(tmp_path)
    s = loai_script("cham", "nhe", [PY, "-c", "import time; time.sleep(120)"])
    canh_bao = ["có sẵn"]
    bo, kho = lam_bo(tmp_path, mt, {"cham": s}, canh_bao=canh_bao)
    v = tao(kho, s, {"k": "a"})
    viec = bo.nhan_viec("nhe")
    t = threading.Thread(target=bo.chay_mot, args=(viec,))
    t.start()
    han = time.monotonic() + 10
    while time.monotonic() < han and not (kho.lay(v["id"]) or {}).get("pid"):
        time.sleep(0.05)
    pid = kho.lay(v["id"])["pid"]
    try:
        kho.chuyen(v["id"], ["dang_chay"], "huy", "nhan", "huỷ từ web")
        bo.bao_huy(v["id"])
        t.join(timeout=30)
        assert not t.is_alive()                                          # không kẹt vô hạn
        assert song(pid)                                                 # mô phỏng: thật sự chưa chết
        assert canh_bao[0] == "có sẵn" and len(canh_bao) == 2
        assert str(pid) in canh_bao[1] and v["id"] in canh_bao[1] and "không giết được" in canh_bao[1]
        assert kho.lay(v["id"])["trang_thai"] == "huy"
        r = bo.doc_log(v["id"], 0)
        assert r["het"] is True and "CẢNH BÁO" in r["noi_dung"]
    finally:
        try:
            psutil.Process(pid).kill()
        except psutil.Error:
            pass


def _viec_dang_chay_pid_chet(kho, s):
    p = subprocess.Popen([PY, "-c", "pass"])
    tl = psutil.Process(p.pid).create_time()
    p.wait(timeout=30)
    v = tao(kho, s, {"k": "a"})
    kho.nhan_viec_ke("nhe", set(), lambda m: frozenset())
    kho.ghi_tien_trinh(v["id"], p.pid, tl)
    return v, p.pid


def test_khoi_dong_lai_khong_job_object_goc_chet_thi_loi_kiem_tay(tmp_path, monkeypatch):
    """R-06 P3-6: không có Job Object runner + gốc đã chết (NoSuchProcess) → cháu mồ côi có thể sống → loi."""
    monkeypatch.setattr(tt, "_JOB_RUNNER", None)
    mt = lam_mt(tmp_path)
    s = loai_script("s", "nhe", [PY, "-c", "print(1)"], dau_ra="chua")
    bo, kho = lam_bo(tmp_path, mt, {"s": s})
    v, pid = _viec_dang_chay_pid_chet(kho, s)
    kq = bo.khoi_dong()
    st = kho.lay(v["id"])
    assert st["trang_thai"] == "loi" and "Job Object" in st["loi"] and "kiểm tay" in st["loi"], st
    assert kq["con_song"] == [pid] and v["id"] not in kq["doi_soat"]
    assert chay_lan(bo, "nhe") is None


def test_khoi_dong_lai_co_job_object_goc_chet_thi_doi_soat_binh_thuong(tmp_path, monkeypatch):
    monkeypatch.setattr(tt, "_JOB_RUNNER", object())                    # giả: runner đã nằm trong Job Object
    mt = lam_mt(tmp_path)
    s = loai_script("s", "nhe", [PY, "-c", "print(1)"], dau_ra="chua")
    bo, kho = lam_bo(tmp_path, mt, {"s": s})
    v, pid = _viec_dang_chay_pid_chet(kho, s)
    kq = bo.khoi_dong()
    st = kho.lay(v["id"])
    assert st["trang_thai"] == "cho" and st["lan_thu"] == 2 and kq["con_song"] == []


def test_doc_log_dang_ghi_khong_tra_dong_do_bi_mat_khong_bi_cat_doi(tmp_path):
    """R-06 P3-1: việc đang chạy, log dừng giữa dòng chứa nửa bí mật → không trả dòng dở; lượt sau đọc trọn rồi che."""
    mt = lam_mt(tmp_path)
    s = loai_script("s", "nhe", [PY, "-c", "1"])
    bo, kho = lam_bo_che(tmp_path, mt, {"s": s})
    v = tao(kho, s, {"k": "a"})
    bo.nhan_viec("nhe")
    f = tmp_path / "data" / "log" / f"{v['id']}.log"
    f.write_bytes(("dòng 1\n" + BI_MAT_VL[:30]).encode("utf-8"))
    r = bo.doc_log(v["id"], 0)
    assert r["noi_dung"] == "dòng 1\n" and r["het"] is False
    with open(f, "ab") as g:
        g.write((BI_MAT_VL[30:] + " đuôi\n").encode("utf-8"))
    r2 = bo.doc_log(v["id"], r["den"])
    assert r2["noi_dung"] == "*** đuôi\n"
    bo._nha(v["id"], "nhe")
    kho.chuyen(v["id"], ["dang_chay"], "xong", "he_thong", "xong")
    with open(f, "ab") as g:
        g.write(b"khong xuong dong")
    r3 = bo.doc_log(v["id"], r2["den"])
    assert r3["noi_dung"] == "khong xuong dong" and r3["het"] is True      # đã dừng → trả cả dòng cuối dở


# ---------------- FX-5 (R-07) ----------------

def test_khoi_dong_lai_tien_trinh_sinh_truoc_lan_khoi_dong_may_thi_doi_soat_binh_thuong(tmp_path, monkeypatch):
    """R-07 P3-5: sau reboot, tiến trình cũ (pid_tao_luc < boot_time) chắc chắn đã chết cả cây → đối soát bình
    thường dù runner không có Job Object."""
    monkeypatch.setattr(tt, "_JOB_RUNNER", None)
    mt = lam_mt(tmp_path)
    s = loai_script("s", "nhe", [PY, "-c", "print(1)"], dau_ra="chua")
    bo, kho = lam_bo(tmp_path, mt, {"s": s})
    p = subprocess.Popen([PY, "-c", "pass"])
    p.wait(timeout=30)
    v = tao(kho, s, {"k": "a"})
    kho.nhan_viec_ke("nhe", set(), lambda m: frozenset())
    kho.ghi_tien_trinh(v["id"], p.pid, psutil.boot_time() - 3600)          # sinh trước lần bật máy này
    kq = bo.khoi_dong()
    st = kho.lay(v["id"])
    assert st["trang_thai"] == "cho" and st["lan_thu"] == 2 and kq["con_song"] == [], st


def test_khoi_dong_lai_pid_tai_dung_truoc_boot_va_khong_job_van_doi_soat(tmp_path, monkeypatch):
    """PID đang sống nhưng là tiến trình khác (create_time lệch), pid_tao_luc trước boot → gốc cũ đã chết chắc."""
    monkeypatch.setattr(tt, "_JOB_RUNNER", None)
    mt = lam_mt(tmp_path)
    s = loai_script("s", "nhe", [PY, "-c", "print(1)"], dau_ra="chua")
    bo, kho = lam_bo(tmp_path, mt, {"s": s})
    p = subprocess.Popen([PY, "-c", "import time; time.sleep(60)"])
    try:
        v = tao(kho, s, {"k": "a"})
        kho.nhan_viec_ke("nhe", set(), lambda m: frozenset())
        kho.ghi_tien_trinh(v["id"], p.pid, psutil.boot_time() - 3600)
        bo.khoi_dong()
        assert p.poll() is None                                            # không đụng tiến trình lạ
        assert kho.lay(v["id"])["trang_thai"] == "cho"
    finally:
        p.kill()
        p.wait(timeout=10)


def _cho_pid(kho, id, han_s=10):
    han = time.monotonic() + han_s
    while time.monotonic() < han and not (kho.lay(id) or {}).get("pid"):
        time.sleep(0.05)
    return kho.lay(id)["pid"]


def _gia_khong_giet(monkeypatch):
    monkeypatch.setattr(tt, "giet_cay", lambda pid, tl: False)
    monkeypatch.setattr(tt, "_tao_job_rieng", lambda proc: None)
    monkeypatch.setattr(tt, "CHO_SAU_GIET_S", 1.0)
    monkeypatch.setattr(tt, "CHO_DON_S", 1.0)


def _giet_that(pid):
    try:
        p = psutil.Process(pid)
        p.kill()
        p.wait(timeout=15)
    except psutil.Error:
        pass


def test_qua_gio_khong_giet_duoc_thi_loi_giu_lan_va_tai_nguyen_toi_khi_pid_chet(tmp_path, monkeypatch):
    """R-07 P2-4: quá giờ, giết không được → loi "tiến trình còn sống — kiểm tay", ket_qua đánh dấu (chặn Chạy tiếp),
    GIỮ làn + tài nguyên; pid chết thật → lần nhận kế nhả và chạy việc khác; cảnh báo của pid đó bị xoá."""
    _gia_khong_giet(monkeypatch)
    mt = lam_mt(tmp_path)
    cham = loai_script("cham", "nhe", [PY, "-c", "import time; time.sleep(120)"], het_gio=1, tai_nguyen=("kho",))
    nhanh = loai_script("nhanh", "nhe", [PY, "-c", "print(1)"])
    kho_gpu = loai_script("kho_gpu", "gpu", [PY, "-c", "print(1)"], tai_nguyen=("kho",))
    canh_bao = ["có sẵn"]
    bo, kho = lam_bo(tmp_path, mt, {"cham": cham, "nhanh": nhanh, "kho_gpu": kho_gpu}, canh_bao=canh_bao,
                     kiem_song_s=0)
    v = tao(kho, cham, {"k": "a"})
    viec = bo.nhan_viec("nhe")
    t = threading.Thread(target=bo.chay_mot, args=(viec,))
    t.start()
    pid = _cho_pid(kho, v["id"])
    try:
        t.join(timeout=40)
        assert not t.is_alive() and song(pid)
        st = kho.lay(v["id"])
        assert st["trang_thai"] == "loi" and "còn sống" in st["loi"] and "kiểm tay" in st["loi"], st
        assert st["ket_qua"]["khong_giet_duoc"] is True and st["ket_qua"]["pid"] == pid
        tl = bo.trang_thai_lan()
        assert tl["lan"]["nhe"]["id"] == v["id"] and tl["tai_nguyen"]["kho"] == v["id"]   # còn giữ
        assert tl["con_song"] == {v["id"]: pid}
        assert sum(1 for c in canh_bao if str(pid) in c) == 1
        v2 = tao(kho, nhanh, {"k": "b"})
        v3 = tao(kho, kho_gpu, {"k": "c"})
        assert chay_lan(bo, "nhe") is None and chay_lan(bo, "gpu") is None              # làn nhe + kho bị giữ
        assert kho.lay(v2["id"])["trang_thai"] == "cho" and kho.lay(v3["id"])["trang_thai"] == "cho"
        assert bo.doc_log(v["id"], 0)["het"] is True                                    # web không chờ log mãi
        _giet_that(pid)
        assert chay_lan(bo, "gpu")["id"] == v3["id"]                                    # đã nhả kho
        assert chay_lan(bo, "nhe")["id"] == v2["id"]                                    # đã nhả làn
        assert bo.trang_thai_lan()["con_song"] == {}
        assert canh_bao == ["có sẵn"]                                                   # P3-6: xoá cảnh báo pid đã chết
    finally:
        _giet_that(pid)


def test_claude_cong_cu_ngoai_ma_khong_giet_duoc_thi_loi_kiem_tay_va_giu_lan(tmp_path, monkeypatch):
    """R-07 P3-1 + P2-4: đường ngoại lệ (CongCuNgoai) mà proc.wait hết giờ → cùng xử lý: loi kiểm tay, giữ làn."""
    _gia_khong_giet(monkeypatch)
    mt = lam_mt(tmp_path)
    loai, kb = loai_claude(tmp_path, [{"tool_use": ["mcp__engram__mem_save"], "ngu": 120, "ket_qua": "x"}])
    bo, kho = lam_bo(tmp_path, mt, {"phan_tich_uid": loai}, kiem_song_s=0)
    v = tao(kho, loai, {"uid": UID})
    t0 = time.monotonic()
    chay_lan(bo, "nhe")
    pid = cac_lan_goi(kb)[0]["pid"]
    try:
        assert time.monotonic() - t0 < 30 and song(pid)
        st = kho.lay(v["id"])
        assert st["trang_thai"] == "loi" and "còn sống" in st["loi"] and "kiểm tay" in st["loi"], st
        assert st["ket_qua"]["khong_giet_duoc"] is True
        assert bo.trang_thai_lan()["lan"]["nhe"]["id"] == v["id"]
        _giet_that(pid)
        assert chay_lan(bo, "nhe") is None                                   # không còn việc, nhưng làn đã nhả
        assert bo.trang_thai_lan()["lan"]["nhe"] is None
    finally:
        _giet_that(pid)


def test_canh_bao_gioi_han_50_va_bo_trung(tmp_path):
    """R-07 P3-6: canh_bao không phình vô hạn; mục trùng không thêm lần hai; mục khởi động giữ nguyên."""
    mt = lam_mt(tmp_path)
    canh_bao = ["khởi động: thiếu Job Object"]
    bo, kho = lam_bo(tmp_path, mt, {}, canh_bao=canh_bao)
    bo._them_canh_bao("trùng")
    bo._them_canh_bao("trùng")
    assert canh_bao.count("trùng") == 1
    for i in range(200):
        bo._them_canh_bao(f"c{i}")
    assert len(canh_bao) == vl.CANH_BAO_TOI_DA
    assert canh_bao[0] == "khởi động: thiếu Job Object" and canh_bao[-1] == "c199"


# ================ A-3: loại tốn tiền (§5.2, §10, §13 A-3) ================

import base64  # noqa: E402
import hashlib  # noqa: E402
import sqlite3  # noqa: E402

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from runner import chu_ky  # noqa: E402

ME = "20261117-a"

TAO_VOICE_GIA = r'''
import json, os, sys
goc = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
with open(os.path.join(goc, "goi_tao_voice.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps({"args": args, "co_key": "GENMAX_API_KEY" in os.environ}, ensure_ascii=False) + "\n")
cfg = json.load(open(os.path.join(goc, "tao_voice_cfg.json"), encoding="utf-8"))
if cfg.get("im_lang"):
    print("không in kế hoạch"); sys.exit(0)
ma = args[args.index("--ma") + 1:] if "--ma" in args else []
bo = cfg.get("bo_qua", [])
for m in bo:
    print(f"  [bỏ qua] {m}: đã có voice")
can = [m for m in ma if m not in bo]
print(f"Kế hoạch: {len(can)} lượt GenMax, tổng {450 * len(can)} ký tự: {can} · model eleven_v4 · tăng tốc 1.1")
if "--dong-y" not in args:
    if can:
        print("CHƯA gọi API. Hỏi người dùng đồng ý số lượt + ký tự ở trên, rồi chạy lại với --dong-y.")
    sys.exit(0)
print("KẾT LUẬN: ĐẠT — xong %d/%d" % (len(can), len(can)))
'''


def ky_duyet(khoa, v: dict, loi="Duyệt, làm đúng như ước tính", boi="nhan", luc=None) -> dict:
    """4 trường duyệt như W-4 ký (chu_ky.chuoi_ky_duyet trên tham_so ĐANG LƯU)."""
    luc = luc or datetime.now(MUI_GIO_VN).isoformat(timespec="seconds")
    chuoi = chu_ky.chuoi_ky_duyet(v["id"], v["loai"], chu_ky.json_chuan(v["tham_so"]), loi, luc, boi)
    ky = base64.urlsafe_b64encode(khoa.sign(chuoi)).rstrip(b"=").decode("ascii")
    return {"loi_duyet": loi, "duyet_boi": boi, "duyet_luc": luc, "chu_ky_duyet": ky}


def duyet(kho: KhoViec, khoa, id: str) -> None:
    """Giống api.p_duyet: cho_duyet → cho, buoc='chay', lưu 4 trường duyệt."""
    kho.chuyen(id, ["cho_duyet"], "cho", "nhan", "duyệt (chữ ký hợp lệ)", buoc="chay", **ky_duyet(khoa, kho.lay(id)))


def sua_db(tmp: Path, id: str, **cot) -> None:
    """Sửa thẳng runner.db (giả lập ai đó đổi DB sau khi duyệt)."""
    c = sqlite3.connect(tmp / "data" / "runner.db")
    try:
        c.execute(f"UPDATE viec SET {', '.join(f'{k}=?' for k in cot)} WHERE id=?", (*cot.values(), id))
        c.commit()
    finally:
        c.close()


def du_an_genmax(tmp: Path, **cfg) -> Path:
    p = tmp / "goc" / f"du_an_{UID}"
    (p / "kich-ban").mkdir(parents=True, exist_ok=True)
    (p / "kich-ban" / f"{ME}_kich-ban-da-cham.md").write_text("x", encoding="utf-8")
    sc = tmp / "scripts"
    sc.mkdir(exist_ok=True)
    (sc / "tao_voice.py").write_text(TAO_VOICE_GIA, encoding="utf-8")
    (sc / "tao_voice_cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
    return p


def goi_tao_voice(tmp: Path) -> list[dict]:
    f = tmp / "scripts" / "goi_tao_voice.jsonl"
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def loai_genmax() -> LoaiViec:
    """voice_genmax THẬT (lap_buoc thật: --dong-y chỉ khi buoc=='chay' + đủ duyệt); chỉ đổi argv[0] 'python' → PY."""
    goc = DANH_MUC["voice_genmax"]

    def lap(ts, viec, mt):
        return [dataclasses.replace(b, argv=[PY] + list(b.argv[1:])) for b in goc.lap_buoc(ts, viec, mt)]
    return dataclasses.replace(goc, lap_buoc=lap)


def tao_genmax(kho: KhoViec, p: Path, ma_ban=("a01", "a02"), khoa: str | None = None, **kw) -> dict:
    ts = {"uid": UID, "du_an": ma_du_an(p), "me": ME, "ma_ban": list(ma_ban)}
    return kho.tao("voice_genmax", khoa or f"{ts['du_an']}:{ME}", ts, "gpu", kw.pop("trang_thai", "cho"), "nhan",
                   buoc=kw.pop("buoc", "uoc_tinh"), **kw)


VECTOR = json.loads((TOOLS / "runner" / "vector_ky.json").read_text(encoding="utf-8"))


def khoa_vector() -> Ed25519PrivateKey:
    """Khoá TEST seed cố định trong vector_ky.json (cùng khoá ký duyệt và ký tiêu như Worker thật)."""
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(VECTOR["seed_test_hex"]))


@pytest.fixture
def khoa_ky():
    return khoa_vector()


class SoGia:
    """Sổ tiêu giả trong bộ nhớ (giống KV Worker): lần đầu ký `ky`, các lần sau 409. Gọi qua vl.tieu_duyet thật."""

    def __init__(self, khoa):
        self.khoa = khoa
        self.da = set()
        self.goi: list[dict] = []

    def http(self, url, headers, body, timeout_s):
        d = json.loads(body)
        self.goi.append(d)
        k = hashlib.sha256(d["chu_ky_duyet"].encode("utf-8")).hexdigest()
        if k in self.da:
            return 409, json.dumps({"loi": "L\u1eddi duy\u1ec7t \u0111\u00e3 d\u00f9ng"}).encode()
        self.da.add(k)
        ky = base64.urlsafe_b64encode(self.khoa.sign(chu_ky.chuoi_tieu_duyet(d["id"], d["chu_ky_duyet"], d["nonce"])))
        return 200, json.dumps({"ky": ky.rstrip(b"=").decode("ascii")}).encode()

    def __call__(self, id, ckd):
        return vl.tieu_duyet("https://worker.test", "K" * 64, self.khoa.public_key(), id, ckd, goi_http=self.http)


# ---------- logic thuần ----------

def test_doc_uoc_tinh_genmax_logic_thuan():
    out = ("  [bỏ qua] a03: đã có voice\n"
           "Kế hoạch: 2 lượt GenMax, tổng 900 ký tự: ['a01', 'a02'] · model eleven_v4 · tăng tốc 1.1\n"
           "CHƯA gọi API. Hỏi người dùng đồng ý số lượt + ký tự ở trên, rồi chạy lại với --dong-y.")
    u = vl.doc_uoc_tinh_genmax(out)
    assert (u["so_ban"], u["ky_tu"], u["ma"], u["bo_qua"], u["chua_goi_api"]) == (2, 900, ["a01", "a02"], ["a03"], True)
    assert u["dong"].startswith("Kế hoạch: 2 lượt GenMax")
    assert vl.doc_uoc_tinh_genmax("không có dòng kế hoạch") is None
    u0 = vl.doc_uoc_tinh_genmax("Kế hoạch: 0 lượt GenMax, tổng 0 ký tự: [] · model x")
    assert u0["so_ban"] == 0 and u0["ma"] == [] and u0["chua_goi_api"] is False
    assert vl.doc_uoc_tinh_genmax("Kế hoạch: 3 lượt GenMax, tổng 9 ký tự: ['a01']") is None   # lệch số mã → không tin
    # dòng [!] (voice cũ quá dài) giữ làm cảnh báo
    u2 = vl.doc_uoc_tinh_genmax("[!] voice Adam ≥ 45s — KHÔNG ghi voice xong cho: a09\n" + out)
    assert u2["canh_bao"] and "a09" in u2["canh_bao"][0]


def test_can_kiem_duyet_logic_thuan():
    G = DANH_MUC["voice_genmax"]
    assert vl.can_kiem_duyet(G, {"buoc": "chay"}) is True
    assert vl.can_kiem_duyet(G, {"buoc": "uoc_tinh"}) is False      # pha ước tính không gọi API (danh_muc)
    assert vl.can_kiem_duyet(DANH_MUC["muse_clip"], {"buoc": "uoc_tinh"}) is True
    assert vl.can_kiem_duyet(DANH_MUC["poster_len_lich"], {"buoc": "chay"}) is True
    assert vl.can_kiem_duyet(DANH_MUC["phan_tich_uid"], {"buoc": "chay"}) is False


def test_dem_codex_va_tran_codex_logic_thuan():
    def tu(ten, sub):
        return {"type": "tool_use", "id": ten + str(sub), "name": ten, "input": {"subagent_type": sub}}
    sk = {"type": "assistant", "message": {"id": "m", "content": [
        tu("Agent", "codex:codex-rescue"), tu("Agent", "general-purpose"), tu("Bash", "codex"),
        tu("Agent", "Codex-x"), tu("Agent", None), {"type": "text", "text": "codex"}]}}
    assert vl.dem_codex(sk) == 2
    assert vl.dem_codex({"type": "user", "message": {"content": [tu("Agent", "codex")]}}) == 0
    assert vl.tran_codex(HAN_MUC_TRAN) == 6
    assert vl.tran_codex({"codex_luot_viec": 99}) == 6            # file chỉ được hạ
    assert vl.tran_codex({"codex_luot_viec": 2}) == 2
    assert vl.tran_codex({"codex_luot_viec": "x"}) == 6


def test_doc_folder_poster_tu_logic_thuan(tmp_path):
    goi = []

    def chay(kq):
        def f(argv, het_gio_s):
            goi.append((argv, het_gio_s))
            if isinstance(kq, BaseException):
                raise kq
            return kq
        return f
    py, sc, po = tmp_path / "py.exe", tmp_path / "poster_ds_folder.py", tmp_path / "poster"
    ds = vl.doc_folder_poster_tu(py, sc, po, chay=chay((0, 'canh bao\n[{"id": 3, "ten": "V\\u00ed"}]\n', "")))
    assert ds == [{"id": 3, "ten": "Ví"}]
    assert goi[0][0] == [str(py), "-B", "-I", str(sc), "--poster", str(po)] and goi[0][1] == vl.HET_GIO_DS_FOLDER_S
    with pytest.raises(OSError, match="mã 3.*Connection refused"):
        vl.doc_folder_poster_tu(py, sc, po, chay=chay((3, "", "[LỖI] ConnectionError: Connection refused")))
    with pytest.raises(OSError, match="JSON"):
        vl.doc_folder_poster_tu(py, sc, po, chay=chay((0, "không phải json", "")))
    with pytest.raises(OSError, match="JSON"):
        vl.doc_folder_poster_tu(py, sc, po, chay=chay((0, '{"id": 1}', "")))
    with pytest.raises(OSError, match="quá giờ"):
        vl.doc_folder_poster_tu(py, sc, po, chay=chay(subprocess.TimeoutExpired(["x"], 20)))


# ---------- poster_ds_folder.py chạy thật với Poster GIẢ (tmp_path) ----------

API_CLIENT_GIA = r'''
import json, os
_GOC = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
class ApiClient:
    def __init__(self):
        self._cfg = json.load(open(os.path.join(_GOC, "cfg.json"), encoding="utf-8"))
    def _ghi(self, ten):
        with open(os.path.join(_GOC, "goi.txt"), "a", encoding="utf-8") as f:
            f.write(ten + "\n")
    def list_folders(self):
        self._ghi("list_folders")
        if self._cfg.get("loi"):
            raise ConnectionError("Connection refused (giả)")
        return self._cfg["folders"]
    def create_folder(self, data):
        self._ghi("create_folder")
    def delete_folder(self, fid):
        self._ghi("delete_folder")
'''


def poster_gia(tmp: Path, **cfg) -> Path:
    po = tmp / "poster"
    (po / "src" / "desktop").mkdir(parents=True, exist_ok=True)
    (po / "src" / "__init__.py").write_text("", encoding="utf-8")
    (po / "src" / "desktop" / "__init__.py").write_text("", encoding="utf-8")
    (po / "src" / "desktop" / "api_client.py").write_text(API_CLIENT_GIA, encoding="utf-8")
    (po / "cfg.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return po


def test_poster_ds_folder_script_chi_goi_list_folders(tmp_path):
    po = poster_gia(tmp_path, folders=[{"id": 3, "name": "Ví da nam", "path": "E:/x"}, {"id": "7", "name": "Đèn"},
                                       {"id": "x", "name": "hỏng"}, {"id": True, "name": "bool"}, {"id": 9}, "rác"])
    ds = vl.doc_folder_poster_tu(Path(PY), vl.POSTER_DS_FOLDER, po)
    assert ds == [{"id": 3, "ten": "Ví da nam", "duong_dan": "E:/x"}, {"id": 7, "ten": "Đèn"}, {"id": 9, "ten": ""}]
    assert (po / "goi.txt").read_text(encoding="utf-8").split() == ["list_folders"]     # không gọi API ghi nào


def test_poster_ds_folder_script_loi_thi_oserror_co_thong_diep(tmp_path):
    po = poster_gia(tmp_path, loi=True)
    with pytest.raises(OSError, match="Connection refused"):
        vl.doc_folder_poster_tu(Path(PY), vl.POSTER_DS_FOLDER, po)
    with pytest.raises(OSError, match="api_client"):
        vl.doc_folder_poster_tu(Path(PY), vl.POSTER_DS_FOLDER, tmp_path / "khong_co")


def test_tao_moi_truong_doc_folder_poster_goi_script(tmp_path, monkeypatch):
    po = poster_gia(tmp_path, folders=[{"id": 4, "name": "Kệ"}])
    monkeypatch.setenv("KHO_PYTHON_POSTER", PY)
    monkeypatch.setenv("KHO_THU_MUC_POSTER", str(po))
    mt = vl.tao_moi_truong()
    assert mt.doc_folder_poster() == [{"id": 4, "ten": "Kệ"}]
    monkeypatch.setenv("KHO_PYTHON_POSTER", str(tmp_path / "khong_co_python.exe"))
    with pytest.raises(OSError, match="khong_co_python"):
        vl.tao_moi_truong().doc_folder_poster()


# ---------- voice_genmax 2 pha ----------

def test_genmax_uoc_tinh_sang_cho_duyet_roi_duyet_moi_chay_dong_y(tmp_path, khoa_ky, monkeypatch):
    monkeypatch.delenv("GENMAX_API_KEY", raising=False)
    p = du_an_genmax(tmp_path, bo_qua=["a03"])
    mt = lam_mt(tmp_path)
    so = SoGia(khoa_ky)
    bo, kho = lam_bo(tmp_path, mt, {"voice_genmax": loai_genmax()}, khoa_cong_khai=khoa_ky.public_key(), tieu=so)
    v = tao_genmax(kho, p, ma_ban=("a01", "a02", "a03"))
    assert chay_lan(bo, "gpu")["id"] == v["id"]
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "cho_duyet", s
    ut = s["ket_qua"]["uoc_tinh"]
    assert (ut["so_ban"], ut["ky_tu"], ut["ma"], ut["bo_qua"]) == (2, 900, ["a01", "a02"], ["a03"])
    assert "2 bản" in s["uoc_tinh"] and "900 ký tự" in s["uoc_tinh"]          # cột uoc_tinh → api xem_truoc
    g = goi_tao_voice(tmp_path)
    assert len(g) == 1 and "--dong-y" not in g[0]["args"] and "--gui-lai-ma" not in g[0]["args"]
    assert chay_lan(bo, "gpu") is None                                        # cho_duyet: không làn nào nhận
    duyet(kho, khoa_ky, v["id"])
    assert chay_lan(bo, "gpu")["id"] == v["id"]
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong", s
    g = goi_tao_voice(tmp_path)
    assert len(g) == 2 and "--dong-y" in g[1]["args"] and "--gui-lai-ma" not in g[1]["args"]
    assert g[1]["args"][g[1]["args"].index("--ma") + 1:] == ["a01", "a02", "a03"]
    assert len(so.goi) == 1 and kho.lay(v["id"])["so_lan_tieu"] == 1     # pha ước tính KHÔNG tiêu; pha chạy tiêu 1


def test_genmax_uoc_tinh_khong_co_ban_nao_thi_xong_khong_can_duyet(tmp_path, khoa_ky):
    p = du_an_genmax(tmp_path, bo_qua=["a01", "a02"])
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"voice_genmax": loai_genmax()}, khoa_cong_khai=khoa_ky.public_key())
    v = tao_genmax(kho, p)
    chay_lan(bo, "gpu")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong" and s["ket_qua"]["uoc_tinh"]["so_ban"] == 0, s
    assert len(goi_tao_voice(tmp_path)) == 1


def test_genmax_uoc_tinh_khong_doc_duoc_thi_loi(tmp_path, khoa_ky):
    p = du_an_genmax(tmp_path, im_lang=True)
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"voice_genmax": loai_genmax()}, khoa_cong_khai=khoa_ky.public_key())
    v = tao_genmax(kho, p)
    chay_lan(bo, "gpu")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and "Kế hoạch" in s["loi"], s


@pytest.mark.parametrize("sua", [
    {"tham_so": None},                       # đổi tham_so (thêm mã bản) sau duyệt
    {"duyet_boi": "ke_gian"},
    {"loi_duyet": "Duyệt 25 bản"},
    {"duyet_luc": "2026-11-17T00:00:01+07:00"},
    {"chu_ky_duyet": None},
])
def test_genmax_sua_db_sau_duyet_bi_chan_luc_nhan(tmp_path, khoa_ky, sua):
    p = du_an_genmax(tmp_path)
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"voice_genmax": loai_genmax()}, khoa_cong_khai=khoa_ky.public_key())
    v = tao_genmax(kho, p)
    chay_lan(bo, "gpu")
    assert kho.lay(v["id"])["trang_thai"] == "cho_duyet"
    duyet(kho, khoa_ky, v["id"])
    if "tham_so" in sua:
        ts = dict(kho.lay(v["id"])["tham_so"], ma_ban=["a01", "a02", "a99"])
        sua = {"tham_so": chu_ky.json_chuan(ts)}
    sua_db(tmp_path, v["id"], **sua)
    chay_lan(bo, "gpu")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and "chữ ký duyệt không hợp lệ" in s["loi"], s
    g = goi_tao_voice(tmp_path)
    assert len(g) == 1 and not any("--dong-y" in x["args"] for x in g)       # pha chay KHÔNG bao giờ chạy


def test_genmax_db_bi_doi_trang_thai_bo_qua_duyet_thi_bi_chan(tmp_path, khoa_ky):
    """Ai đó sửa DB: cho_duyet → cho + buoc='chay' mà không có lời duyệt → bị chặn lúc nhận, không --dong-y."""
    p = du_an_genmax(tmp_path)
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"voice_genmax": loai_genmax()}, khoa_cong_khai=khoa_ky.public_key())
    v = tao_genmax(kho, p, trang_thai="cho_duyet")
    sua_db(tmp_path, v["id"], trang_thai="cho", buoc="chay")
    chay_lan(bo, "gpu")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and "chữ ký duyệt không hợp lệ" in s["loi"], s
    assert goi_tao_voice(tmp_path) == []


def test_genmax_chu_ky_cua_khoa_khac_bi_chan(tmp_path, khoa_ky):
    p = du_an_genmax(tmp_path)
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"voice_genmax": loai_genmax()}, khoa_cong_khai=khoa_ky.public_key())
    v = tao_genmax(kho, p, trang_thai="cho_duyet", buoc="chay")
    duyet(kho, Ed25519PrivateKey.generate(), v["id"])
    chay_lan(bo, "gpu")
    assert kho.lay(v["id"])["trang_thai"] == "loi"
    assert goi_tao_voice(tmp_path) == []


def test_ton_tien_vuot_han_muc_luc_nhan_thi_dung_cho_co_ghi_chu(tmp_path, khoa_ky):
    p = du_an_genmax(tmp_path)
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"voice_genmax": loai_genmax()}, khoa_cong_khai=khoa_ky.public_key())
    v = tao_genmax(kho, p, trang_thai="cho_duyet", buoc="chay")
    duyet(kho, khoa_ky, v["id"])
    hom_nay = datetime.now(MUI_GIO_VN).isoformat(timespec="seconds")
    for i in range(2):          # 2 việc genmax khác đã duyệt hôm nay (trần genmax_viec_ngay = 2)
        k = tao_genmax(kho, p, khoa=f"khac{i}")
        kho.chuyen(k["id"], ["cho"], "xong", "he_thong", "giả lập đã chạy", duyet_luc=hom_nay)
    assert chay_lan(bo, "gpu")["id"] == v["id"]
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "cho", s
    sk = kho.su_kien(v["id"])[-1]
    assert sk["tu"] == "dang_chay" and sk["den"] == "cho" and "hạn mức" in sk["ghi_chu"]
    assert sk["ghi_chu"].startswith(vl.TIEN_TO_HOAN)
    assert goi_tao_voice(tmp_path) == []
    assert "voice_genmax" in bo.trang_thai_lan()["tam_hoan"]
    assert chay_lan(bo, "gpu") is None                                        # loại đang hoãn


def test_ton_tien_khong_nap_duoc_khoa_cong_khai_thi_hoan_va_canh_bao(tmp_path, khoa_ky):
    p = du_an_genmax(tmp_path)
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"voice_genmax": loai_genmax()}, khoa_cong_khai=None)
    v = tao_genmax(kho, p, trang_thai="cho_duyet", buoc="chay")
    duyet(kho, khoa_ky, v["id"])
    chay_lan(bo, "gpu")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "cho" and "khoá công khai" in kho.su_kien(v["id"])[-1]["ghi_chu"], s
    assert any("khoá công khai" in c for c in bo.canh_bao)
    assert goi_tao_voice(tmp_path) == []


def test_khoa_cong_khai_mac_dinh_nap_canh_ma():
    k = vl.nap_khoa_cong_khai_canh_ma()
    assert k is not None and len(k.public_bytes_raw()) == 32     # repo có tools/runner/ky_cong_khai.pem


# ---------- Claude tốn tiền: chữ ký trước khi gọi Claude ----------

def loai_claude_ton_tien(tmp: Path, kich_ban: list[dict]) -> tuple[LoaiViec, Path]:
    loai, kb = loai_claude(tmp, kich_ban, dau_ra="khong_ro")
    return dataclasses.replace(loai, ma="muse_clip", dot=4, ton_tien=True, tu_chay_lai=False), kb


def test_claude_ton_tien_duyet_hop_le_moi_goi_claude(tmp_path, khoa_ky):
    loai, kb = loai_claude_ton_tien(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE\nXong."}])
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"muse_clip": loai}, khoa_cong_khai=khoa_ky.public_key(),
                     tieu=SoGia(khoa_ky))
    ts = {"uid": UID, "mau": ["m1", "m2"]}
    sai = kho.tao("muse_clip", "a", ts, "nhe", "cho_duyet", "nhan", session_id=str(uuid.uuid4()))
    duyet(kho, khoa_ky, sai["id"])
    sua_db(tmp_path, sai["id"], tham_so=chu_ky.json_chuan(dict(ts, mau=["m1", "m2", "m3"])))
    chay_lan(bo, "nhe")
    assert kho.lay(sai["id"])["trang_thai"] == "loi" and cac_lan_goi(kb) == []      # Claude KHÔNG được gọi
    dung = kho.tao("muse_clip", "b", ts, "nhe", "cho_duyet", "nhan", session_id=str(uuid.uuid4()))
    duyet(kho, khoa_ky, dung["id"])
    chay_lan(bo, "nhe")
    assert kho.lay(dung["id"])["trang_thai"] == "xong"
    assert len(cac_lan_goi(kb)) == 1


def test_claude_ton_tien_chay_tiep_cung_kiem_lai_chu_ky(tmp_path, khoa_ky):
    """loi → cho (chạy tiếp) với chữ ký cũ bị sửa → bị chặn lúc nhận dù đã chạy được lượt đầu."""
    loai, kb = loai_claude_ton_tien(tmp_path, [{"ket_qua": None, "ma": 1}, {"ket_qua": "TRẠNG THÁI: DONE"}])
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"muse_clip": loai}, khoa_cong_khai=khoa_ky.public_key(),
                     tieu=SoGia(khoa_ky))
    v = kho.tao("muse_clip", "a", {"uid": UID, "mau": ["m1"]}, "nhe", "cho_duyet", "nhan",
                session_id=str(uuid.uuid4()))
    duyet(kho, khoa_ky, v["id"])
    chay_lan(bo, "nhe")
    assert kho.lay(v["id"])["trang_thai"] == "loi" and len(cac_lan_goi(kb)) == 1
    sua_db(tmp_path, v["id"], duyet_boi="ke_gian")
    kho.chuyen(v["id"], ["loi"], "cho", "nhan", "chạy tiếp (resume phiên Claude)")
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and "chữ ký duyệt không hợp lệ" in s["loi"], s
    assert len(cac_lan_goi(kb)) == 1


# ---------- đếm subagent codex* (§5.3, trần codex_luot_viec) ----------

def loai_claude_agent(tmp: Path, kich_ban: list[dict]) -> tuple[LoaiViec, Path]:
    loai, kb = loai_claude(tmp, kich_ban)
    return dataclasses.replace(loai, bo_cong_cu=tuple(loai.bo_cong_cu) + ("Agent",)), kb


_TOOLS_AGENT = ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill", "Agent"]


def _codex(sub="codex:codex-rescue"):
    return {"name": "Agent", "input": {"subagent_type": sub, "prompt": "x"}}


def test_claude_dem_codex_luu_so_codex(tmp_path):
    loai, kb = loai_claude_agent(tmp_path, [{"tools": _TOOLS_AGENT, "ket_qua": "TRẠNG THÁI: DONE",
                                             "tool_use": [_codex(), _codex(), _codex("general-purpose")]}])
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"phan_tich_uid": loai})
    v = tao(kho, loai, {"uid": UID})
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong" and s["ket_qua"]["so_codex"] == 2, s


def test_claude_vuot_tran_codex_thi_giet_cay_va_can_tra_loi(tmp_path):
    loai, kb = loai_claude_agent(tmp_path, [{"tools": _TOOLS_AGENT, "ngu": 30, "ket_qua": "TRẠNG THÁI: DONE",
                                             "tool_use": [_codex(), _codex(), _codex()]}])
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"phan_tich_uid": loai}, hm=dict(HAN_MUC_TRAN, codex_luot_viec=2))
    v = tao(kho, loai, {"uid": UID})
    t0 = time.monotonic()
    chay_lan(bo, "nhe")
    assert time.monotonic() - t0 < 25
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "can_tra_loi" and s["cau_hoi"]["loai"] == "khong_ro", s
    assert "trần lượt Codex" in s["cau_hoi"]["noi_dung"] and s["ket_qua"]["so_codex"] == 3
    assert not song(cac_lan_goi(kb)[0]["pid"])
    assert bo.trang_thai_lan()["lan"]["nhe"] is None


def test_claude_so_codex_cong_don_qua_cac_luot(tmp_path):
    """Trần là MỖI VIỆC: lượt resume cộng tiếp số đã dùng ở lượt trước."""
    loai, kb = loai_claude_agent(tmp_path, [
        {"tools": _TOOLS_AGENT, "tool_use": [_codex()],
         "ket_qua": "Cần chốt.\nCẦN_USER: Chọn?\nLOẠI: chon\nLỰA_CHỌN: A | B"},
        {"tools": _TOOLS_AGENT, "tool_use": [_codex(), _codex()], "ngu": 30, "ket_qua": "TRẠNG THÁI: DONE"}])
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"phan_tich_uid": loai}, hm=dict(HAN_MUC_TRAN, codex_luot_viec=2))
    v = tao(kho, loai, {"uid": UID})
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "can_tra_loi" and s["ket_qua"]["so_codex"] == 1, s
    tra_loi(kho, v["id"], "A")
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "can_tra_loi" and "trần lượt Codex" in s["cau_hoi"]["noi_dung"], s
    assert s["ket_qua"]["so_codex"] == 3


# ---------- D9 / FX-10: tiêu lời duyệt trên Worker trước mỗi lần chạy pha tốn tiền ----------
# Worker giả = HTTP server thật trên 127.0.0.1 cổng ngẫu nhiên, ký phản hồi bằng khoá TEST seed (vector_ky.json).
# Không gọi Worker thật, không đụng E:\kho-runner.

import socket  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

KHOA_RUNNER_TEST = "khoa-runner-test-" + "a" * 40


class WorkerGia:
    """`che_do`: ok | loi500 | loi401 | json_hong | sai_ky (ký trên nonce khác) | khoa_khac | ngu (quá timeout)."""

    def __init__(self, khoa, che_do: str = "ok"):
        self.khoa = khoa
        self.che_do = che_do
        self.da: set[str] = set()
        self.goi: list[dict] = []
        ngoai = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("content-length") or 0)
                d = json.loads(self.rfile.read(n))
                ngoai.goi.append({"path": self.path, "key": self.headers.get("x-runner-key"), "body": d})
                ma, tl = ngoai._tra_loi(d)
                try:
                    self.send_response(ma)
                    self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(tl)))
                    self.end_headers()
                    self.wfile.write(tl)
                except OSError:
                    pass                                    # phía runner đã bỏ (hết giờ)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.origin = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def _tra_loi(self, d: dict) -> tuple[int, bytes]:
        cd = self.che_do
        if cd == "loi500":
            return 500, b'{"loi":"x"}'
        if cd == "loi401":
            return 401, b'{"loi":"khoa sai"}'
        if cd == "json_hong":
            return 200, b"khong phai json"
        if cd == "ngu":
            time.sleep(2)
        k = hashlib.sha256(d["chu_ky_duyet"].encode("utf-8")).hexdigest()
        if k in self.da:
            return 409, json.dumps({"loi": "Lời duyệt đã dùng"}).encode()
        self.da.add(k)
        nonce = "0" * 32 if cd == "sai_ky" else d["nonce"]
        khoa = Ed25519PrivateKey.generate() if cd == "khoa_khac" else self.khoa
        ky = base64.urlsafe_b64encode(khoa.sign(chu_ky.chuoi_tieu_duyet(d["id"], d["chu_ky_duyet"], nonce)))
        return 200, json.dumps({"ky": ky.rstrip(b"=").decode("ascii")}).encode()

    def tieu(self, timeout_s: float = 5.0):
        return vl.tao_ham_tieu(self.origin, KHOA_RUNNER_TEST, self.khoa.public_key(), timeout_s=timeout_s)

    def dong(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def worker():
    ds = []

    def tao_worker(che_do="ok"):
        w = WorkerGia(khoa_vector(), che_do)
        ds.append(w)
        return w
    yield tao_worker
    for w in ds:
        w.dong()


def cong_dong() -> str:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    cong = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{cong}"


T0 = VECTOR["tieu"][0]


def test_tieu_duyet_vector_co_dinh_khop_byte():
    """sinh_nonce cố định = nonce vector → `ky` của vector kiểm đúng → da_tieu (khớp chữ ký Worker từng byte)."""
    goi = []

    def http(url, headers, body, timeout_s):
        goi.append((url, headers, json.loads(body), timeout_s))
        return 200, json.dumps({"ky": T0["ky"]}).encode()
    kcc = khoa_vector().public_key()
    kq = vl.tieu_duyet("https://kho.test", KHOA_RUNNER_TEST, kcc, T0["id"], T0["chu_ky_duyet"],
                       goi_http=http, sinh_nonce=lambda: T0["nonce"])
    assert kq[0] == "da_tieu"
    url, h, body, to = goi[0]
    assert url == "https://kho.test/api/runner/tieu-duyet" and to == vl.HET_GIO_TIEU_S == 15.0
    assert h["x-runner-key"] == KHOA_RUNNER_TEST and body == {"id": T0["id"], "chu_ky_duyet": T0["chu_ky_duyet"],
                                                              "nonce": T0["nonce"]}
    # cùng `ky` nhưng nonce khác (phát lại phản hồi cũ) → chua_ro
    assert vl.tieu_duyet("https://kho.test", KHOA_RUNNER_TEST, kcc, T0["id"], T0["chu_ky_duyet"],
                         goi_http=http)[0] == "chua_ro"


def test_tieu_duyet_qua_http_cac_nhanh(worker):
    kcc = khoa_vector().public_key()
    w = worker()
    kq = vl.tieu_duyet(w.origin, KHOA_RUNNER_TEST, kcc, T0["id"], T0["chu_ky_duyet"])
    assert kq[0] == "da_tieu", kq
    g = w.goi[0]
    assert g["path"] == "/api/runner/tieu-duyet" and g["key"] == KHOA_RUNNER_TEST
    assert set(g["body"]) == {"id", "chu_ky_duyet", "nonce"} and vl._RE_NONCE.fullmatch(g["body"]["nonce"])
    kq2 = vl.tieu_duyet(w.origin, KHOA_RUNNER_TEST, kcc, T0["id"], T0["chu_ky_duyet"])
    assert kq2[0] == "da_dung" and w.goi[1]["body"]["nonce"] != g["body"]["nonce"]      # nonce mới mỗi lần
    for che_do in ("loi500", "loi401", "json_hong", "sai_ky", "khoa_khac"):
        w2 = worker(che_do)
        kq = vl.tieu_duyet(w2.origin, KHOA_RUNNER_TEST, kcc, T0["id"], T0["chu_ky_duyet"])
        assert kq[0] == "chua_ro" and KHOA_RUNNER_TEST not in kq[1], (che_do, kq)
    w3 = worker("ngu")
    t = time.monotonic()
    kq = vl.tieu_duyet(w3.origin, KHOA_RUNNER_TEST, kcc, T0["id"], T0["chu_ky_duyet"], timeout_s=0.5)
    assert kq[0] == "chua_ro" and time.monotonic() - t < 1.8, kq                         # hết giờ
    kq = vl.tieu_duyet(cong_dong(), KHOA_RUNNER_TEST, kcc, T0["id"], T0["chu_ky_duyet"], timeout_s=2)
    assert kq[0] == "chua_ro" and "mạng" in kq[1], kq                                     # không kết nối được


def test_tieu_duyet_tu_choi_truoc_khi_goi():
    goi = []

    def http(*a):
        goi.append(a)
        return 200, b"{}"
    kcc = khoa_vector().public_key()
    for origin in ("http://kho-san-pham.kutidak.workers.dev", "ftp://x.y", "https://x.y/duong", "", "https://u:p@x.y"):
        assert vl.tieu_duyet(origin, KHOA_RUNNER_TEST, kcc, T0["id"], T0["chu_ky_duyet"], goi_http=http)[0] \
            == "chua_ro", origin
    assert vl.tieu_duyet("https://x.y", KHOA_RUNNER_TEST, None, T0["id"], T0["chu_ky_duyet"], goi_http=http)[0] \
        == "chua_ro"
    assert vl.tieu_duyet("https://x.y", "", kcc, T0["id"], T0["chu_ky_duyet"], goi_http=http)[0] == "chua_ro"
    assert vl.tieu_duyet("https://x.y", KHOA_RUNNER_TEST, kcc, T0["id"], T0["chu_ky_duyet"], goi_http=http,
                         sinh_nonce=lambda: "ABC")[0] == "chua_ro"
    assert goi == []


def test_worker_origin_ghi_de_bang_bien_moi_truong(monkeypatch):
    monkeypatch.delenv("KHO_WORKER_ORIGIN", raising=False)
    assert vl.worker_origin() == vl.WORKER_ORIGIN == "https://kho-san-pham.kutidak.workers.dev"
    monkeypatch.setenv("KHO_WORKER_ORIGIN", "http://127.0.0.1:9")
    assert vl.worker_origin() == "http://127.0.0.1:9"


def _muse_duyet(kho, khoa, k="a"):
    v = kho.tao("muse_clip", k, {"uid": UID, "mau": ["m1"]}, "nhe", "cho_duyet", "nhan", session_id=str(uuid.uuid4()))
    duyet(kho, khoa, v["id"])
    return v


def test_r11_replay_sua_db_xong_ve_cho_bi_chan_khong_goi_claude_lan_2(tmp_path, khoa_ky, worker):
    """Kịch bản R-11 P1-1: việc tốn tiền đã chạy xong; sửa DB xong→cho (giữ chữ ký) → bị chặn, Claude không gọi lại."""
    w = worker()
    loai, kb = loai_claude_ton_tien(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE\nXong."}])
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"muse_clip": loai}, khoa_cong_khai=khoa_ky.public_key(),
                     tieu=w.tieu())
    v = _muse_duyet(kho, khoa_ky)
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong" and len(cac_lan_goi(kb)) == 1 and len(w.goi) == 1, s
    assert s["so_lan_tieu"] == 1 and s["tieu_luc_dau"]
    # (1) sổ cục bộ chặn ngay, không cần mạng
    sua_db(tmp_path, v["id"], trang_thai="cho")
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and vl.LOI_DA_DUNG in s["loi"] and "Xin duyệt lại" in s["loi"], s
    assert len(cac_lan_goi(kb)) == 1 and len(w.goi) == 1
    # (2) xoá luôn sổ cục bộ (ai đó sửa runner.db) → Worker 409 → vẫn chặn
    c = sqlite3.connect(tmp_path / "data" / "runner.db")
    c.execute("DELETE FROM da_tieu")
    c.commit()
    c.close()
    sua_db(tmp_path, v["id"], trang_thai="cho")
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and vl.LOI_DA_DUNG in s["loi"], s
    assert len(cac_lan_goi(kb)) == 1 and len(w.goi) == 2 and s["so_lan_tieu"] == 1
    assert kho.da_tieu_cuc_bo(s["chu_ky_duyet"])                    # 409 → ghi lại sổ cục bộ


@pytest.mark.parametrize("che_do", ["mang", "loi500", "sai_ky", "khoa_khac", "json_hong", "ngu"])
def test_worker_loi_hoac_chu_ky_sai_thi_dung_cho_khong_chay(tmp_path, khoa_ky, worker, che_do):
    if che_do == "mang":
        tieu = vl.tao_ham_tieu(cong_dong(), KHOA_RUNNER_TEST, khoa_ky.public_key(), timeout_s=2)
    else:
        tieu = worker(che_do).tieu(timeout_s=0.5)
    loai, kb = loai_claude_ton_tien(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE"}])
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"muse_clip": loai}, khoa_cong_khai=khoa_ky.public_key(),
                     tieu=tieu)
    v = _muse_duyet(kho, khoa_ky)
    assert chay_lan(bo, "nhe")["id"] == v["id"]
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "cho" and s["so_lan_tieu"] == 0 and not kho.da_tieu_cuc_bo(s["chu_ky_duyet"]), s
    sk = kho.su_kien(v["id"])[-1]
    assert sk["ghi_chu"].startswith(vl.TIEN_TO_HOAN) and "chưa tiêu được lời duyệt" in sk["ghi_chu"]
    assert cac_lan_goi(kb) == []                                     # Claude KHÔNG được gọi
    assert any("chưa tiêu được lời duyệt" in c for c in bo.canh_bao)
    assert bo.trang_thai_lan()["tam_hoan"]["muse_clip"] > 500        # hoãn cả loại 10 phút
    assert not any(KHOA_RUNNER_TEST in c for c in bo.canh_bao)
    assert KHOA_RUNNER_TEST not in (tmp_path / "data" / "log" / f"{v['id']}.log").read_text(encoding="utf-8")


def test_tieu_none_hoac_nem_loi_thi_dung_cho(tmp_path, khoa_ky):
    def no(id, ckd):
        raise RuntimeError("hỏng")
    for i, tieu in enumerate((None, no)):
        loai, kb = loai_claude_ton_tien(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE"}])
        bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"muse_clip": loai}, khoa_cong_khai=khoa_ky.public_key(),
                         tieu=tieu)
        v = _muse_duyet(kho, khoa_ky, k=f"k{i}")
        chay_lan(bo, "nhe")
        s = kho.lay(v["id"])
        assert s["trang_thai"] == "cho" and s["so_lan_tieu"] == 0 and cac_lan_goi(kb) == [], s


def test_chan_ton_tien_khong_goi_tieu_viec_mien_phi_van_chay(tmp_path, khoa_ky):
    so = SoGia(khoa_ky)
    loai, kb = loai_claude_ton_tien(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE"}])
    mien_phi = loai_script("voice_pv", "gpu", [PY, "-c", "print('ok')"])
    cb: list[str] = []
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"muse_clip": loai, "voice_pv": mien_phi},
                     khoa_cong_khai=khoa_ky.public_key(), tieu=so, chan_ton_tien=True, canh_bao=cb)
    assert bo.trang_thai_lan()["chan_ton_tien"] is True
    assert any("lệch tổng kiểm" in c for c in cb)                    # cùng list với /suc-khoe
    v = _muse_duyet(kho, khoa_ky)
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "cho" and "lệch tổng kiểm" in kho.su_kien(v["id"])[-1]["ghi_chu"], s
    assert so.goi == [] and cac_lan_goi(kb) == [] and s["so_lan_tieu"] == 0
    f = tao(kho, mien_phi, {"k": "free"})
    chay_lan(bo, "gpu")
    assert kho.lay(f["id"])["trang_thai"] == "xong"
    # genmax pha ước tính (miễn phí) vẫn chạy khi bị chặn, và không tiêu
    p = du_an_genmax(tmp_path)
    bo2, kho2 = lam_bo(tmp_path, lam_mt(tmp_path), {"voice_genmax": loai_genmax()},
                       kho=kho, khoa_cong_khai=khoa_ky.public_key(), tieu=so, chan_ton_tien=True)
    g = tao_genmax(kho2, p)
    chay_lan(bo2, "gpu")
    assert kho2.lay(g["id"])["trang_thai"] == "cho_duyet" and so.goi == []
    assert vl.BoChay(kho, lam_mt(tmp_path), dict(HAN_MUC_TRAN), tmp_path / "l2", str).trang_thai_lan()[
        "chan_ton_tien"] is False


GHI_SO_LAN_TIEU = r"""
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
n = c.execute("SELECT so_lan_tieu FROM viec WHERE id=?", (sys.argv[2],)).fetchone()[0]
open(sys.argv[3], "a", encoding="utf-8").write(f"{n}\n")
"""


def test_tieu_dung_mot_lan_moi_lan_chay_va_ghi_truoc_khi_sinh_tien_trinh(tmp_path, khoa_ky):
    """Pha tốn tiền 2 bước: tiêu đúng 1 lần, và so_lan_tieu đã = 1 khi bước ĐẦU TIÊN bắt đầu chạy."""
    so = SoGia(khoa_ky)
    db = tmp_path / "data" / "runner.db"
    ra = tmp_path / "so_lan.txt"
    sc = tmp_path / "ghi.py"
    sc.write_text(GHI_SO_LAN_TIEU, encoding="utf-8")
    goc = loai_script("poster_len_lich", "nhe", [])

    def lap(ts, viec, mt):
        return [BuocChay(t, [PY, str(sc), str(db), viec["id"], str(ra)], str(tmp_path), None, {}, False, 60)
                for t in ("b1", "b2")]
    loai = dataclasses.replace(goc, ton_tien=True, dot=4, lap_buoc=lap)
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"poster_len_lich": loai}, khoa_cong_khai=khoa_ky.public_key(),
                     tieu=so)
    v = kho.tao("poster_len_lich", "folder:1", {"folder_id": 1, "so_video_ngay": 1}, "nhe", "cho_duyet", "nhan")
    duyet(kho, khoa_ky, v["id"])
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong", s
    assert ra.read_text(encoding="utf-8").split() == ["1", "1"] and len(so.goi) == 1
    # chạy lại bằng cách sửa DB → không bước nào chạy thêm
    sua_db(tmp_path, v["id"], trang_thai="cho")
    chay_lan(bo, "nhe")
    assert kho.lay(v["id"])["trang_thai"] == "loi" and ra.read_text(encoding="utf-8").split() == ["1", "1"]


def test_dieu_kien_truoc_ban_khong_lam_mat_loi_duyet(tmp_path, khoa_ky):
    """Đứng chờ vì 'bận' xảy ra TRƯỚC bước tiêu → lời duyệt chưa tiêu, lần sau chạy được."""
    so = SoGia(khoa_ky)
    ban = {"v": "ban"}
    goc = loai_script("poster_len_lich", "nhe", [PY, "-c", "print(1)"], dk=lambda ts, mt: ban["v"])
    loai = dataclasses.replace(goc, ton_tien=True, dot=4)
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"poster_len_lich": loai}, khoa_cong_khai=khoa_ky.public_key(),
                     tieu=so, cho_lai_s=0.0)
    v = kho.tao("poster_len_lich", "folder:1", {"folder_id": 1, "so_video_ngay": 1}, "nhe", "cho_duyet", "nhan")
    duyet(kho, khoa_ky, v["id"])
    chay_lan(bo, "nhe")
    assert kho.lay(v["id"])["trang_thai"] == "cho" and so.goi == []
    ban["v"] = None
    chay_lan(bo, "nhe")
    assert kho.lay(v["id"])["trang_thai"] == "xong" and len(so.goi) == 1


# ---------- FX-15: lý do xin duyệt lại vào stdin lượt Claude kế tiếp, dùng đúng một lần ----------

from runner import api as _api  # noqa: E402

_CAN_USER = "Cần chốt.\nCẦN_USER: Tag nào?\nLOẠI: chon\nLỰA_CHỌN: A | B"


def _xin_duyet_lai(kho: KhoViec, id: str) -> dict:
    """Giống api xin-duyet-lai (loai ≠ genmax): loi/can_tra_loi → cho_duyet, xoá 4 trường duyệt, ket_qua từ api."""
    v = kho.lay(id)
    kho.chuyen(id, list(_api.TRANG_THAI_XIN_DUYET_LAI), "cho_duyet", "nhan", "xin duyệt lại",
               loi_duyet=None, duyet_boi=None, duyet_luc=None, chu_ky_duyet=None,
               ket_qua=_api.ket_qua_xin_duyet_lai(v))
    return kho.lay(id)


def _duyet_lan(kho: KhoViec, khoa, id: str, n: int) -> None:
    """duyet() nhưng lời duyệt khác nhau mỗi lần (chữ ký khác → sổ tiêu giả không 409)."""
    kho.chuyen(id, ["cho_duyet"], "cho", "nhan", "duyệt (chữ ký hợp lệ)", buoc="chay",
               **ky_duyet(khoa, kho.lay(id), loi=f"Duyệt lần {n}"))


def test_ly_do_duyet_lai_can_dung_logic_thuan():
    M, P = DANH_MUC["muse_clip"], DANH_MUC["phan_tich_uid"]
    sk_duyet = [{"tu": "can_tra_loi", "den": "cho_duyet", "ghi_chu": "xin duyệt lại"},
                {"tu": "cho_duyet", "den": "cho", "ghi_chu": "duyệt"},
                {"tu": "cho", "den": "dang_chay", "ghi_chu": ""}]
    v = {"ket_qua": {"so_codex": 2, "duyet_lai_tu": "can_tra_loi", "ly_do_duyet_lai": "vì X"}}
    assert vl.ly_do_duyet_lai_can_dung(M, v, sk_duyet) == "vì X"
    assert vl.ly_do_duyet_lai_can_dung(P, v, sk_duyet) is None                  # không tốn tiền
    sk_tra_loi = [{"tu": "can_tra_loi", "den": "cho", "ghi_chu": "trả lời: A"}]
    assert vl.ly_do_duyet_lai_can_dung(M, v, sk_tra_loi) is None                # không đi từ duyệt
    sk_hoan = sk_duyet + [{"tu": "dang_chay", "den": "cho", "ghi_chu": vl.TIEN_TO_HOAN + "bận"}]
    assert vl.ly_do_duyet_lai_can_dung(M, v, sk_hoan) == "vì X"                  # tạm hoãn không làm mất
    for kq in (None, {}, {"ly_do_duyet_lai": ""}, {"ly_do_duyet_lai": 5}, "chuỗi"):
        assert vl.ly_do_duyet_lai_can_dung(M, {"ket_qua": kq}, sk_duyet) is None
    goc = {"so_codex": 2, "tom_tat": "t", "duyet_lai_tu": "loi", "ly_do_duyet_lai": "x"}
    assert vl.bo_khoa_duyet_lai(goc) == {"so_codex": 2, "tom_tat": "t"}
    assert "ly_do_duyet_lai" in goc                                              # không sửa dict gốc
    assert vl.bo_khoa_duyet_lai(None) == {}
    vd = {"id": "v1", "loi_duyet": "Duyệt", "duyet_boi": "nhan", "duyet_luc": "2026-11-17T10:00:00+07:00"}
    t = vl.lap_tin_sau_duyet_lai(vd, "vì X", None)
    assert t.startswith("Phiên trước dừng vì: vì X.") and t.count("vì X") == 1 and "ĐÃ DUYỆT: nhan" in t
    t = vl.lap_tin_sau_duyet_lai(vd, "vì X", "PHIẾU v1\nnội dung\n")
    assert t.startswith("PHIẾU v1\nnội dung\n") and t.count("vì X") == 1


def test_claude_ton_tien_duyet_lai_tu_can_tra_loi_resume_co_ly_do_mot_lan(tmp_path, khoa_ky):
    """FX-15: can_tra_loi → xin duyệt lại → duyệt → lượt resume có lý do (đúng 1 lần) + khối ĐÃ DUYỆT;
    ket_qua mất 2 khoá duyệt lại nhưng giữ so_codex; lượt sau (duyệt thường) không còn lý do."""
    so = SoGia(khoa_ky)
    loai, kb = loai_claude_ton_tien(tmp_path, [{"ket_qua": _CAN_USER}, {"ket_qua": _CAN_USER},
                                               {"ket_qua": "TRẠNG THÁI: DONE\nXong."}])
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"muse_clip": loai}, khoa_cong_khai=khoa_ky.public_key(), tieu=so)
    v = _muse_duyet(kho, khoa_ky)
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "can_tra_loi" and s["phien_da_tao"] == 1, s
    sua_db(tmp_path, v["id"], ket_qua=json.dumps(dict(s["ket_qua"], so_codex=2)))
    s = _xin_duyet_lai(kho, v["id"])
    ly = s["ket_qua"]["ly_do_duyet_lai"]
    assert s["ket_qua"]["duyet_lai_tu"] == "can_tra_loi" and "Tag nào?" in ly
    _duyet_lan(kho, khoa_ky, v["id"], 2)
    chay_lan(bo, "nhe")
    g = cac_lan_goi(kb)
    assert len(g) == 2 and "--resume" in g[1]["args"]
    st = g[1]["stdin"]
    assert st.startswith("Phiên trước dừng vì: " + ly[:40]) and st.count(ly[:60]) == 1, st
    assert "ĐÃ DUYỆT: nhan" in st and "Duyệt lần 2" in st
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "can_tra_loi", s
    assert "ly_do_duyet_lai" not in s["ket_qua"] and "duyet_lai_tu" not in s["ket_qua"], s["ket_qua"]
    assert s["ket_qua"]["so_codex"] == 2
    # lượt sau: duyệt lại KHÔNG qua xin-duyet-lai (giữ ket_qua đang lưu) → stdin không còn lý do cũ
    kho.chuyen(v["id"], ["can_tra_loi"], "cho_duyet", "nhan", "về chờ duyệt", loi_duyet=None, duyet_boi=None,
               duyet_luc=None, chu_ky_duyet=None)
    _duyet_lan(kho, khoa_ky, v["id"], 3)
    chay_lan(bo, "nhe")
    g = cac_lan_goi(kb)
    assert len(g) == 3 and "Tag nào?" not in g[2]["stdin"] and "Phiên trước dừng vì" not in g[2]["stdin"]
    assert g[2]["stdin"].startswith("ĐÃ DUYỆT: nhan") and "Duyệt lần 3" in g[2]["stdin"]
    assert kho.lay(v["id"])["trang_thai"] == "xong"


def test_claude_ton_tien_duyet_lai_tu_loi_chua_co_phien_phieu_day_du_kem_ly_do_da_che(tmp_path, khoa_ky):
    """FX-15: lượt đầu chết trước init (phien_da_tao=0) → loi; xin duyệt lại → phiếu đầy đủ + lý do (đã che bí mật).
    Claude lượt đó lại chết → ket_qua vẫn không còn lý do (đã dùng)."""
    so = SoGia(khoa_ky)
    loai, kb = loai_claude_ton_tien(tmp_path, [{"init": False, "ket_qua": None, "ma": 1},
                                               {"init": False, "ket_qua": None, "ma": 1}])
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"muse_clip": loai}, khoa_cong_khai=khoa_ky.public_key(), tieu=so)
    v = _muse_duyet(kho, khoa_ky)
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi" and s["phien_da_tao"] == 0, s
    sua_db(tmp_path, v["id"], loi="mạng rớt token BIMAT123456789 hết hạn")
    s = _xin_duyet_lai(kho, v["id"])
    assert s["ket_qua"]["ly_do_duyet_lai"] == "mạng rớt token BIMAT123456789 hết hạn"
    _duyet_lan(kho, khoa_ky, v["id"], 2)
    chay_lan(bo, "nhe")
    g = cac_lan_goi(kb)
    assert len(g) == 2 and "--resume" not in g[1]["args"]
    st = g[1]["stdin"]
    assert st.startswith("PHIẾU " + v["id"]) and "Duyệt lần 2" in st
    assert st.count("Phiên trước dừng vì: mạng rớt token *** hết hạn.") == 1, st
    assert "BIMAT123456789" not in st
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "loi", s
    assert not isinstance(s["ket_qua"], dict) or "ly_do_duyet_lai" not in s["ket_qua"], s["ket_qua"]


def test_script_ton_tien_duyet_lai_bo_qua_ly_do(tmp_path, khoa_ky):
    """FX-15: việc tốn tiền chạy script (genmax/poster) không dùng lý do: stdin bước script giữ nguyên."""
    so = SoGia(khoa_ky)
    ra = tmp_path / "stdin.txt"
    goc = loai_script("poster_len_lich", "nhe", [PY, "-c",
                      f"import sys; open({str(ra)!r}, 'w', encoding='utf-8').write(sys.stdin.read())"])
    loai = dataclasses.replace(goc, ton_tien=True, dot=4)
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"poster_len_lich": loai}, khoa_cong_khai=khoa_ky.public_key(),
                     tieu=so)
    v = kho.tao("poster_len_lich", "folder:1", {"folder_id": 1, "so_video_ngay": 1}, "nhe", "cho_duyet", "nhan")
    sua_db(tmp_path, v["id"], ket_qua=json.dumps({"so_codex": 0, "duyet_lai_tu": "loi", "ly_do_duyet_lai": "vì X"}))
    _duyet_lan(kho, khoa_ky, v["id"], 1)
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong" and ra.read_text(encoding="utf-8") == "", s


# ---------- FX-18 (R-15 P3-2): lỗi cấu hình phát hiện TRƯỚC khi tiêu lời duyệt ----------

def test_loi_khong_sinh_duoc_logic_thuan(tmp_path):
    def b(**kw):
        g = dict(ten="x", argv=[PY, "-c", "1"], cwd=str(tmp_path), stdin=None, env_them={}, la_claude=False,
                 het_gio_s=60)
        g.update(kw)
        return BuocChay(**g)
    assert vl.loi_khong_sinh_duoc(b()) is None
    assert vl.loi_khong_sinh_duoc(b(argv=["python", "-c", "1"], stdin="phiếu")) is None   # tên tương đối: không đoán PATH
    assert vl.loi_khong_sinh_duoc(b(argv=[PY, ""])) is None                              # tham số rỗng là hợp lệ
    assert "rỗng" in vl.loi_khong_sinh_duoc(b(argv=[]))
    assert vl.loi_khong_sinh_duoc(b(argv=["", "-c"])) is not None
    assert vl.loi_khong_sinh_duoc(b(argv=[PY, 5])) is not None
    assert "thư mục chạy" in vl.loi_khong_sinh_duoc(b(cwd=str(tmp_path / "khong_co")))
    assert "thư mục chạy" in vl.loi_khong_sinh_duoc(b(cwd=""))
    assert "không thấy chương trình" in vl.loi_khong_sinh_duoc(b(argv=[str(tmp_path / "khong.exe")]))
    assert vl.loi_khong_sinh_duoc(b(stdin=b"bytes")) is not None


def _chua_tieu(kho: KhoViec, so: "SoGia", id: str) -> dict:
    s = kho.lay(id)
    assert so.goi == [] and s["so_lan_tieu"] == 0 and not kho.da_tieu_cuc_bo(s["chu_ky_duyet"]), s
    return s


@pytest.mark.parametrize("hong", ["thieu_resume", "thieu_stdin", "cwd_mat", "exe_mat"])
def test_cau_hinh_claude_hong_khong_tieu_loi_duyet_sua_xong_chay_duoc(tmp_path, khoa_ky, hong):
    """Cấu hình bước Claude hỏng → loi, Worker tiêu KHÔNG được gọi, Claude không chạy; sửa cấu hình + Chạy tiếp →
    lời duyệt cũ vẫn dùng được (tiêu đúng 1 lần, Claude chạy 1 lần)."""
    so = SoGia(khoa_ky)
    loai0, kb = loai_claude_ton_tien(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE\nXong."}])
    con_hong = {"v": True}

    def lap(ts, viec, mt):
        b = loai0.lap_buoc(ts, viec, mt)[0]
        if not con_hong["v"]:
            return [b]
        if hong == "thieu_resume":
            return [dataclasses.replace(b, argv=[a for a in b.argv if a != "--resume"])]
        if hong == "thieu_stdin":
            return [dataclasses.replace(b, stdin=None)]
        if hong == "cwd_mat":
            return [dataclasses.replace(b, cwd=str(tmp_path / "khong_co"))]
        return [dataclasses.replace(b, argv=[str(tmp_path / "khong_co.exe")] + b.argv[1:])]
    loai = dataclasses.replace(loai0, lap_buoc=lap)
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"muse_clip": loai}, khoa_cong_khai=khoa_ky.public_key(), tieu=so)
    v = _muse_duyet(kho, khoa_ky)
    if hong == "thieu_resume":
        sua_db(tmp_path, v["id"], phien_da_tao=1)
    chay_lan(bo, "nhe")
    s = _chua_tieu(kho, so, v["id"])
    assert s["trang_thai"] == "loi" and cac_lan_goi(kb) == [], s
    con_hong["v"] = False
    kho.chuyen(v["id"], ["loi"], "cho", "nhan", "chạy tiếp (resume phiên Claude)")
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong" and len(so.goi) == 1 and s["so_lan_tieu"] == 1, s
    assert len(cac_lan_goi(kb)) == 1


def test_resume_khong_lap_duoc_tin_tiep_khong_tieu_loi_duyet(tmp_path, khoa_ky):
    """Đã có phiên, vừa 'trả lời' mà DB không có câu trả lời → lap_tin_resume ném ThamSoLoi → loi, chưa tiêu."""
    so = SoGia(khoa_ky)
    loai, kb = loai_claude_ton_tien(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE"}])
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"muse_clip": loai}, khoa_cong_khai=khoa_ky.public_key(), tieu=so)
    v = _muse_duyet(kho, khoa_ky)
    sua_db(tmp_path, v["id"], phien_da_tao=1, trang_thai="can_tra_loi")
    kho.chuyen(v["id"], ["can_tra_loi"], "cho", "nhan", "trả lời: A")       # không có dòng tra_loi
    chay_lan(bo, "nhe")
    s = _chua_tieu(kho, so, v["id"])
    assert s["trang_thai"] == "loi" and "resume" in s["loi"] and cac_lan_goi(kb) == [], s


@pytest.mark.parametrize("hong", ["cwd_mat", "log_phu_hong"])
def test_cau_hinh_script_hong_khong_tieu_loi_duyet(tmp_path, khoa_ky, hong):
    so = SoGia(khoa_ky)
    ra = tmp_path / "da_chay.txt"
    chan = tmp_path / "la_file"
    chan.write_text("x", encoding="utf-8")
    goc = loai_script("poster_len_lich", "nhe", [])

    def lap(ts, viec, mt):
        a = [PY, "-c", f"open({str(ra)!r}, 'w').write('1')"]
        if hong == "cwd_mat":
            return [BuocChay("s", a, str(tmp_path / "khong_co"), None, {}, False, 60)]
        return [BuocChay("s", a, str(tmp_path), None, {}, False, 60, file_log_phu=str(chan / "con" / "phu.log"))]
    loai = dataclasses.replace(goc, ton_tien=True, dot=4, lap_buoc=lap)
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"poster_len_lich": loai}, khoa_cong_khai=khoa_ky.public_key(),
                     tieu=so)
    v = kho.tao("poster_len_lich", "folder:1", {"folder_id": 1, "so_video_ngay": 1}, "nhe", "cho_duyet", "nhan")
    duyet(kho, khoa_ky, v["id"])
    chay_lan(bo, "nhe")
    s = _chua_tieu(kho, so, v["id"])
    assert s["trang_thai"] == "loi" and not ra.exists(), s


def test_tieu_chua_ro_giu_ly_do_duyet_lai_cho_luot_sau(tmp_path, khoa_ky):
    """FX-18: tiêu đặt TRƯỚC khi xoá khoá duyệt lại → Worker chưa tiêu được (đứng chờ) thì lý do vẫn còn;
    lần sau tiêu được → lý do vào stdin đúng 1 lần rồi mới bị xoá."""
    so = SoGia(khoa_ky)
    mo = {"v": False}

    def tieu(id, ckd):
        return so(id, ckd) if mo["v"] else ("chua_ro", "mạng rớt")
    loai, kb = loai_claude_ton_tien(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE\nXong."}])
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"muse_clip": loai}, khoa_cong_khai=khoa_ky.public_key(),
                     tieu=tieu, cho_lai_han_muc_s=0.0)
    v = kho.tao("muse_clip", "a", {"uid": UID, "mau": ["m1"]}, "nhe", "cho_duyet", "nhan",
                session_id=str(uuid.uuid4()))
    sua_db(tmp_path, v["id"], ket_qua=json.dumps({"so_codex": 1, "duyet_lai_tu": "loi", "ly_do_duyet_lai": "vì X"}))
    _duyet_lan(kho, khoa_ky, v["id"], 1)
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "cho" and s["ket_qua"]["ly_do_duyet_lai"] == "vì X" and cac_lan_goi(kb) == [], s
    mo["v"] = True
    chay_lan(bo, "nhe")
    g = cac_lan_goi(kb)
    assert len(g) == 1 and g[0]["stdin"].count("vì X") == 1, g
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong" and "ly_do_duyet_lai" not in s["ket_qua"] and len(so.goi) == 1, s


# ---------- A-5 b): phan_tich_uid thiếu douyin.md → runner tự tạo việc con douyin_uid (không trùng) ----------

@pytest.mark.parametrize("dau_ra", ["xong_lo_ngai", "xong"])
def test_phan_tich_uid_thieu_douyin_tu_tao_viec_con_douyin_khong_trung(tmp_path, dau_ra):
    loai, kb = loai_claude(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE\nXong."}], dau_ra=dau_ra)
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"phan_tich_uid": loai, "douyin_uid": DANH_MUC["douyin_uid"]})
    v = tao(kho, loai, {"uid": UID})
    chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong", s
    ds_douyin = [x for x in kho.ds(None, gioi_han=50) if x["loai"] == "douyin_uid"]
    if dau_ra == "xong":                                   # đủ douyin.md → không tạo gì
        assert ds_douyin == [] and "viec_con_douyin" not in s["ket_qua"]
        return
    assert len(ds_douyin) == 1
    con = ds_douyin[0]
    assert s["ket_qua"]["viec_con_douyin"] == con["id"]
    assert (con["cha_id"], con["tham_so"], con["trang_thai"], con["tao_boi"]) == (v["id"], {"uid": UID}, "cho",
                                                                                     "nhan")
    assert "douyin_uid" not in s["ket_qua"]["goi_y_viec"] and con["id"] in s["ket_qua"]["lo_ngai"]
    # phan_tich_uid lần 2 cùng UID trong khi douyin_uid còn mở → KHÔNG tạo trùng
    v2 = tao(kho, loai, {"uid": UID}, khoa="lan2")
    bo.chay_mot(kho.chuyen(v2["id"], ["cho"], "dang_chay", "nhan", "nhận tay (test)"))
    s2 = kho.lay(v2["id"])
    assert s2["trang_thai"] == "xong" and s2["ket_qua"]["viec_con_douyin"] == con["id"]
    assert s2["ket_qua"]["douyin_trung"] is True
    assert len([x for x in kho.ds(None, gioi_han=50) if x["loai"] == "douyin_uid"]) == 1


def test_trang_thai_lan_co_phien_song_rong_khi_khong_co_phien(tmp_path):
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {})
    assert bo.trang_thai_lan()["phien_song"] == [] and bo.co_phien_song("j20261118000000abcd") is False


# ---------------- FX-29: phiếu taovideo theo hm vòng chạy đang giữ; ket_qua giữ kho_luc_tao ----------------

def test_phieu_taovideo_dung_hm_vong_chay_ca_lan_dau_va_lan_chay_tiep(tmp_path, monkeypatch):
    """Vòng chạy giữ hm đã hạ (codex 2, mp3 10) mà thư mục runner không có cau_hinh.json → phiếu lần đầu
    (lap_buoc_hieu_luc) và phiếu LẦN CHẠY TIẾP (lap_phieu_tiep_taovideo) phải in trần theo hm đó."""
    import test_runner_phien_song as tps
    from runner import api as _api
    monkeypatch.setattr(tps.ps, "NHIP_S", 0.1)
    bo, kho, v, kb, _so, khoa, _a = tps.lam_tv(
        tmp_path, [{"luot": [{"viec": [tps._ket(tps.CAN_CHON)]}]}, {"luot": [{"viec": [tps._ket(tps.DONE)]}]}],
        taovideo_cho_s=1, codex_luot_viec=2, taovideo_mp3_viec=10)
    id = v["id"]
    assert not (tmp_path / "data" / "cau_hinh.json").exists()
    _, t = tps.chay_nen(bo)
    tps.xong_luong(t)
    s = kho.lay(id)
    assert s["trang_thai"] == "loi", s
    p1 = tps.tin_nhan(kb, 0)[0]
    assert "Codex ≤ 2 lần; voice GenMax ≤ 10 file mới" in p1
    kho.chuyen(id, ["loi"], "cho_duyet", "nhan", "xin duyệt lại", loi_duyet=None, duyet_boi=None, duyet_luc=None,
               chu_ky_duyet=None, ket_qua=_api.ket_qua_xin_duyet_lai(s))
    tps.duyet_lan(kho, khoa, id, 2)
    _, t = tps.chay_nen(bo)
    tps.xong_luong(t)
    p2 = tps.tin_nhan(kb, 1)[0]
    assert "LẦN CHẠY TIẾP" in p2 and "Codex ≤ 2 lần; voice GenMax ≤ 10 file mới" in p2


def test_phien_song_giu_kho_luc_tao_qua_duyet_lai_va_ket_thuc(tmp_path, monkeypatch):
    """ket_qua.kho_luc_tao (ảnh chụp lúc tạo việc) còn nguyên qua: bắt đầu phiên, kết thúc loi, xin duyệt lại,
    duyệt, phiên mới, kết thúc."""
    import test_runner_phien_song as tps
    from runner import api as _api
    from runner.danh_muc import KHOA_ANH_CHUP_KHO
    monkeypatch.setattr(tps.ps, "NHIP_S", 0.1)
    bo, kho, v, kb, _so, khoa, _a = tps.lam_tv(
        tmp_path, [{"luot": [{"viec": [tps._ket(tps.CAN_CHON)]}]}, {"luot": [{"viec": [tps._ket(tps.DONE)]}]}],
        taovideo_cho_s=1)
    id = v["id"]
    anh = {"a": [[1, 20]], "b": []}
    tps.sua_db(tmp_path, id, ket_qua=json.dumps({KHOA_ANH_CHUP_KHO: anh}))
    _, t = tps.chay_nen(bo)
    tps.xong_luong(t)
    s = kho.lay(id)
    assert s["trang_thai"] == "loi" and s["ket_qua"][KHOA_ANH_CHUP_KHO] == anh, s
    kho.chuyen(id, ["loi"], "cho_duyet", "nhan", "xin duyệt lại", loi_duyet=None, duyet_boi=None, duyet_luc=None,
               chu_ky_duyet=None, ket_qua=_api.ket_qua_xin_duyet_lai(s))
    assert kho.lay(id)["ket_qua"][KHOA_ANH_CHUP_KHO] == anh
    tps.duyet_lan(kho, khoa, id, 2)
    assert kho.lay(id)["ket_qua"][KHOA_ANH_CHUP_KHO] == anh
    _, t = tps.chay_nen(bo)
    tps.xong_luong(t)
    s = kho.lay(id)
    assert s["trang_thai"] in ("xong", "loi") and s["ket_qua"][KHOA_ANH_CHUP_KHO] == anh, s


def test_khoi_dong_lai_doi_soat_xong_gop_ket_qua_giu_khoa_cu(tmp_path):
    """FX-29: đối soát sau khởi động lại → xong: ket_qua GỘP vào ket_qua cũ (giữ kho_luc_tao, so_codex…), không thay
    cả dict (B7)."""
    mt = lam_mt(tmp_path)
    s = loai_script("s", "nhe", [PY, "-c", "print(1)"], dau_ra="xong")
    bo, kho = lam_bo(tmp_path, mt, {"s": s})
    v = tao(kho, s, {"k": "a"})
    kho.chuyen(v["id"], ["cho"], "dang_chay", "he_thong", "nhận",
               ket_qua={"kho_luc_tao": {"a": [], "b": []}, "so_codex": 3})
    bo.khoi_dong()
    st = kho.lay(v["id"])
    assert st["trang_thai"] == "xong", st
    assert st["ket_qua"]["kho_luc_tao"] == {"a": [], "b": []} and st["ket_qua"]["so_codex"] == 3
    assert st["ket_qua"]["tom_tat"].startswith("đối soát sau khởi động lại") and st["ket_qua"]["file_ra"] == []


# ---------------- D15 HT-A2: hẹn giờ trong làn nhe (docs/hoc-tu-dong.md §3.4, §8.3) ----------------
# Giờ giả lập qua Dong (bay_gio); không ngủ thật. DANH_MUC thật cho 2 loại hệ thống (kiem_tham_so, trang_thai_dau).

def gio(h: int, m: int = 0, ngay: int = 23) -> datetime:
    return datetime(2026, 11, ngay, h, m, tzinfo=MUI_GIO_VN)


class KhoHocGia:
    """Giả KhoHoc cho vòng chạy: chỉ ghi lại ghi_ap_dung; `loi` → ném lỗi đó."""

    def __init__(self, loi: Exception | None = None):
        self.loi, self.goi = loi, []

    def ghi_ap_dung(self, ds_ma, viec_id, uid):
        self.goi.append((list(ds_ma), viec_id, uid))
        if self.loi is not None:
            raise self.loi


def bo_hen_gio(tmp: Path, dong: Dong, *, hm=None, kho=None, kho_hoc="gia", hen_gio=None):
    hen_gio = vl.HEN_GIO_MAC_DINH if hen_gio is None else hen_gio
    mt = lam_mt(tmp, bay_gio=dong)
    kh = KhoHocGia() if kho_hoc == "gia" else kho_hoc
    return lam_bo(tmp, mt, DANH_MUC, hm=hm, kho=kho, kho_hoc=kh, hen_gio=hen_gio)


def viec_he_thong(kho: KhoViec) -> list[dict]:
    return [v for v in kho.ds(None, gioi_han=500) if v["loai"] in ("quet_view_hang_ngay", "hoc_hang_ngay")]


def test_hen_gio_hang_so_va_mac_dinh_tat():
    import inspect
    assert vl.HEN_GIO_MAC_DINH == (("quet_view_hang_ngay", 9), ("hoc_hang_ngay", 12))
    p = inspect.signature(vl.BoChay.__init__).parameters
    assert p["kho_hoc"].default is None and p["hen_gio"].default == ()
    assert p["kho_hoc"].kind is inspect.Parameter.KEYWORD_ONLY and p["hen_gio"].kind is inspect.Parameter.KEYWORD_ONLY


def test_hen_gio_dung_gio_moi_ngay_mot_viec_moi_loai(tmp_path):
    dong = Dong(gio(8, 59))
    bo, kho = bo_hen_gio(tmp_path, dong)
    assert bo._hen_gio() == [] and viec_he_thong(kho) == []            # 08:59 chưa tới giờ
    dong.t = gio(9, 0)
    ids = bo._hen_gio()
    assert len(ids) == 1
    q = kho.lay(ids[0])
    assert (q["loai"], q["khoa"], q["tham_so"], q["tao_boi"], q["trang_thai"], q["lan_chay"]) == (
        "quet_view_hang_ngay", "2026-11-23", {"ngay": "2026-11-23"}, "he_thong", "cho", "nhe")
    dong.t = gio(11, 59)
    assert bo._hen_gio() == []
    dong.t = gio(12, 0)
    ids2 = bo._hen_gio()
    assert len(ids2) == 1 and kho.lay(ids2[0])["loai"] == "hoc_hang_ngay"
    assert kho.lay(ids2[0])["tham_so"] == {"ngay": "2026-11-23"} and kho.lay(ids2[0])["tao_boi"] == "he_thong"
    for _ in range(100):
        assert bo._hen_gio() == []
    assert len(viec_he_thong(kho)) == 2
    # ngày hôm sau: tạo lại đúng 1 việc quét lúc 09:00
    dong.t = gio(9, 0, ngay=24)
    ids3 = bo._hen_gio()
    assert len(ids3) == 1 and kho.lay(ids3[0])["khoa"] == "2026-11-24"


def test_hen_gio_khoi_dong_lai_cung_ngay_khong_tao_them(tmp_path):
    dong = Dong(gio(12, 30))
    bo, kho = bo_hen_gio(tmp_path, dong)
    a, b = bo._hen_gio()
    # việc đã kết thúc (xong / huỷ) vẫn chặn tạo lại trong ngày
    kho.chuyen(a, ["cho"], "dang_chay", "he_thong", "nhận (test)")
    kho.chuyen(a, ["dang_chay"], "xong", "he_thong", "xong (test)")
    kho.chuyen(b, ["cho"], "huy", "nhan", "huỷ (test)")
    dong.t = gio(15, 0)
    bo2, _ = bo_hen_gio(tmp_path, dong, kho=kho)                         # runner mới, bộ nhớ rỗng
    assert bo2._hen_gio() == [] and len(viec_he_thong(kho)) == 2
    # việc đã ẩn/lưu trữ (ds() không thấy) cũng không bị tạo lại
    kho.dat_luu_tru(a, True, "nhan")
    bo3, _ = bo_hen_gio(tmp_path, dong, kho=kho)
    assert bo3._hen_gio() == []
    assert kho.dem_trong_ngay("quet_view_hang_ngay", gio(15).date()) == 1


def test_hen_gio_may_bat_muon_tao_quet_roi_hoc(tmp_path):
    bo, kho = bo_hen_gio(tmp_path, Dong(gio(13, 0)))
    ids = bo._hen_gio()
    assert [kho.lay(i)["loai"] for i in ids] == ["quet_view_hang_ngay", "hoc_hang_ngay"]
    # FIFO của làn nhe: việc quét được nhận trước
    v = kho.nhan_viec_ke("nhe", set(), lambda ma: frozenset())
    assert v["id"] == ids[0]


def test_hen_gio_vuot_han_muc_quet_khong_tao_chi_log_mot_lan(tmp_path, caplog):
    hm = dict(HAN_MUC_TRAN, quet_view_ngay=0)
    bo, kho = bo_hen_gio(tmp_path, Dong(gio(13, 0)), hm=hm)
    with caplog.at_level("INFO", logger="kho_runner.vong_lap"):
        for _ in range(5):
            bo._hen_gio()
    assert [v["loai"] for v in viec_he_thong(kho)] == ["hoc_hang_ngay"]  # học vẫn tạo, quét bị chặn
    log_quet = [r for r in caplog.records if "quet_view_hang_ngay" in r.getMessage()]
    assert len(log_quet) == 1 and "VuotHanMuc" in log_quet[0].getMessage(), [r.getMessage() for r in log_quet]


def test_hen_gio_khong_co_kho_hoc_bo_viec_hoc(tmp_path):
    bo, kho = bo_hen_gio(tmp_path, Dong(gio(13, 0)), kho_hoc=None)
    bo._hen_gio()
    assert [v["loai"] for v in viec_he_thong(kho)] == ["quet_view_hang_ngay"]


def test_hen_gio_rong_khong_tao_gi(tmp_path):
    bo, kho = bo_hen_gio(tmp_path, Dong(gio(13, 0)), hen_gio=())
    assert bo._hen_gio() == [] and viec_he_thong(kho) == []
    # mặc định BoChay (không truyền hen_gio) cũng không tạo
    bo2, _ = lam_bo(tmp_path, lam_mt(tmp_path, bay_gio=Dong(gio(13, 0))), DANH_MUC, kho=kho)
    assert bo2.hen_gio == () and bo2._hen_gio() == [] and viec_he_thong(kho) == []


def test_vong_nhe_goi_hen_gio_loi_khong_giet_lan(tmp_path, monkeypatch, caplog):
    bo, kho = bo_hen_gio(tmp_path, Dong(gio(13, 0)))
    goi = {"hen": 0, "nhe": 0, "gpu": 0}

    def hen_loi():
        goi["hen"] += 1
        raise RuntimeError("hỏng giả")

    def nhan(lan):
        goi[lan] += 1
        if goi[lan] >= 3:
            bo._dung.set()
        return None
    monkeypatch.setattr(bo, "_hen_gio", hen_loi)
    monkeypatch.setattr(bo, "nhan_viec", nhan)
    with caplog.at_level("ERROR", logger="kho_runner.vong_lap"):
        bo._vong("nhe")
    assert goi["nhe"] == 3 and goi["hen"] == 3                          # mỗi vòng nhe: hẹn giờ trước, nhận sau
    assert any("hẹn giờ" in r.getMessage() for r in caplog.records)
    bo._dung.clear()
    goi["hen"] = 0
    bo._vong("gpu")
    assert goi["hen"] == 0                                              # làn gpu không hẹn giờ


# ---------------- D15 HT-A2: ghi vết áp dụng bài học (§3.7, P3-8) ----------------

MA_BH1, MA_BH2 = "bh20261215k3x9", "bh20261217a1b2"
GOI_Y = [{"ma": MA_BH1, "khoa": "cap_co_so", "huong": "tang", "nguon": "poster_view", "trang_thai": "hieu_luc",
          "het_han_luc": "2026-12-30", "lift_pt": 22, "so_uid": 21, "so_cung_chieu": 15, "so_viec": 300},
         {"ma": MA_BH2, "khoa": "pt_thieu_dau_ra", "huong": "tang", "nguon": "van_hanh", "trang_thai": "hieu_luc",
          "het_han_luc": "2026-12-30", "lift_pt": 0, "so_uid": 4, "so_cung_chieu": 0, "so_viec": 15}]


def test_ghi_ap_dung_dung_ma_cua_phieu(tmp_path):
    kh = KhoHocGia()
    mt = lam_mt(tmp_path, goi_y_hoc=lambda n: list(GOI_Y))
    loai, kb = loai_claude(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE\nXong."}])
    bo, kho = lam_bo(tmp_path, mt, {"phan_tich_uid": loai}, kho_hoc=kh)
    v = tao(kho, loai, {"uid": UID})
    chay_lan(bo, "nhe")
    assert kho.lay(v["id"])["trang_thai"] == "xong"
    stdin = cac_lan_goi(kb)[0]["stdin"]
    assert f"[{MA_BH1}]" in stdin and f"[{MA_BH2}]" in stdin
    assert kh.goi == [([MA_BH1, MA_BH2], v["id"], UID)]


def test_ghi_ap_dung_khong_goi_khi_phieu_khong_co_khoi(tmp_path):
    kh = KhoHocGia()
    loai, kb = loai_claude(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE\nXong."}])
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path), {"phan_tich_uid": loai}, kho_hoc=kh)
    v = tao(kho, loai, {"uid": UID})
    chay_lan(bo, "nhe")
    assert kho.lay(v["id"])["trang_thai"] == "xong" and kh.goi == []


def test_ghi_ap_dung_loi_khong_lam_hong_viec_phan_tich(tmp_path, caplog):
    kh = KhoHocGia(loi=RuntimeError("hoc.db khoá"))
    mt = lam_mt(tmp_path, goi_y_hoc=lambda n: list(GOI_Y))
    loai, kb = loai_claude(tmp_path, [{"ket_qua": "TRẠNG THÁI: DONE\nXong."}])
    bo, kho = lam_bo(tmp_path, mt, {"phan_tich_uid": loai}, kho_hoc=kh)
    v = tao(kho, loai, {"uid": UID})
    with caplog.at_level("WARNING", logger="kho_runner.vong_lap"):
        chay_lan(bo, "nhe")
    s = kho.lay(v["id"])
    assert s["trang_thai"] == "xong", s                                # không thành loi
    assert len(cac_lan_goi(kb)) == 1 and len(kh.goi) == 1               # vẫn chạy bước Claude
    assert any("RuntimeError" in r.getMessage() and r.levelname == "WARNING" for r in caplog.records)


def test_ghi_ap_dung_bo_qua_loai_khac_phan_tich_uid(tmp_path):
    kh = KhoHocGia()
    s = loai_script("s", "nhe", [PY, "-c", "print(1)"])
    bo, kho = lam_bo(tmp_path, lam_mt(tmp_path, goi_y_hoc=lambda n: list(GOI_Y)), {"s": s}, kho_hoc=kh)
    tao(kho, s, {"k": "a"})
    chay_lan(bo, "nhe")
    assert kh.goi == []


# ---------------- D15 HT-A2: tao_moi_truong điền 3 đường dẫn (§3.6 "Chặn chạm production") ----------------

BIEN_3 = ("KHO_THU_MUC_POSTER", "KHO_THU_MUC_VIEW", "KHO_SCRIPT_QUET_KENH")


def test_mac_dinh_co_hai_duong_dan_moi():
    assert vl.MAC_DINH["KHO_THU_MUC_VIEW"] == "C:/Users/Mi/view-poster"
    assert vl.MAC_DINH["KHO_SCRIPT_QUET_KENH"] == (
        "C:/Users/Mi/.claude/skills/quet-phan-tich-kenh-tiktok/scripts/tiktok_scan.py")


def test_tao_moi_truong_thu_muc_tam_thieu_bien_thi_none(tmp_path, monkeypatch):
    monkeypatch.setenv("KHO_RUNNER_DIR", str(tmp_path / "du_lieu"))
    for k in BIEN_3:
        monkeypatch.delenv(k, raising=False)
    mt = vl.tao_moi_truong()
    assert (mt.poster_db, mt.thu_muc_view, mt.script_quet_kenh) == (None, None, None)


def test_tao_moi_truong_lay_tu_bien_moi_truong(tmp_path, monkeypatch):
    monkeypatch.setenv("KHO_RUNNER_DIR", str(tmp_path / "du_lieu"))
    monkeypatch.setenv("KHO_THU_MUC_POSTER", str(tmp_path / "poster"))
    monkeypatch.setenv("KHO_THU_MUC_VIEW", str(tmp_path / "view"))
    monkeypatch.setenv("KHO_SCRIPT_QUET_KENH", str(tmp_path / "scan.py"))
    mt = vl.tao_moi_truong()
    assert mt.poster_db == tmp_path / "poster" / "v2_data.db"
    assert mt.thu_muc_view == tmp_path / "view" and mt.script_quet_kenh == tmp_path / "scan.py"


def test_tao_moi_truong_thu_muc_mac_dinh_dung_mac_dinh(tmp_path, monkeypatch):
    """Thư mục runner = mặc định (giả bằng cách đổi _thu_muc_mac_dinh về tmp — không đụng E:\\kho-runner) và không
    đặt biến → 3 đường dẫn mặc định (chỉ so giá trị, không mở file nào)."""
    monkeypatch.setattr(vl, "_thu_muc_mac_dinh", lambda: tmp_path / "goc_gia")
    monkeypatch.setenv("KHO_RUNNER_DIR", str(tmp_path / "goc_gia"))
    for k in BIEN_3:
        monkeypatch.delenv(k, raising=False)
    mt = vl.tao_moi_truong()
    assert mt.poster_db == Path(vl.MAC_DINH["KHO_THU_MUC_POSTER"]) / "v2_data.db"
    assert mt.thu_muc_view == Path(vl.MAC_DINH["KHO_THU_MUC_VIEW"])
    assert mt.script_quet_kenh == Path(vl.MAC_DINH["KHO_SCRIPT_QUET_KENH"])
    assert not (tmp_path / "goc_gia").exists()
