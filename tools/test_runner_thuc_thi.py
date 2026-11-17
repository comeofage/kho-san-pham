"""Test thực thi tiến trình (§4.6, §4.7, §6.1) — chạy:
PYTHONIOENCODING=utf-8 python -B -m pytest tools/test_runner_thuc_thi.py -q

Mọi tiến trình con là chương trình giả `python` viết vào tmp_path. Không gọi claude.exe/agy.exe.
Test chỉ giết tiến trình do chính test sinh ra.
"""
import json
import os
import subprocess
import sys
import textwrap
import threading
import time
import uuid
from pathlib import Path

import psutil
import pytest

TOOLS = Path(__file__).parent
sys.path.insert(0, str(TOOLS))
from runner import thuc_thi as tt  # noqa: E402

PY = sys.executable
SID = "11111111-2222-3333-4444-555555555555"


# ---------------- tiện ích test ----------------

def viet_script(tmp_path: Path, ten: str, ma: str) -> Path:
    p = tmp_path / ten
    p.write_text(textwrap.dedent(ma), encoding="utf-8")
    return p


def chay(tmp_path, argv, **kw):
    """Gọi chay_tien_trinh với mặc định hợp lý; trả (kết quả, dict ghi nhận callback)."""
    ghi = {"bat_dau": [], "session": [], "dong": []}
    tham = dict(
        argv=argv, cwd=str(tmp_path), stdin_text=None, env=tt.env_toi_thieu({}),
        file_log=tmp_path / "viec.log", file_jsonl=None, het_gio_s=60, la_claude=False,
        hien_cua_so=False, tran_luot=None,
        khi_bat_dau=lambda pid, luc: ghi["bat_dau"].append((pid, luc)),
        khi_co_session=lambda s: ghi["session"].append(s),
        khi_doc_dong=lambda d: ghi["dong"].append(d),
        huy=threading.Event())
    tham.update(kw)
    return tt.chay_tien_trinh(**tham), ghi


def cho_chet(pids, gioi_han=15.0) -> list[int]:
    """Chờ các pid chết; trả danh sách pid còn sống sau giới hạn."""
    han = time.monotonic() + gioi_han
    con = list(pids)
    while con and time.monotonic() < han:
        con = [p for p in con if psutil.pid_exists(p) and psutil.Process(p).status() != psutil.STATUS_ZOMBIE]
        if con:
            time.sleep(0.2)
    return con


def don_pid(pids):
    """Dọn tiến trình do test sinh nếu test hỏng giữa chừng."""
    for p in pids:
        try:
            psutil.Process(p).kill()
        except psutil.Error:
            pass


def doc_pid_tu_file(p: Path, gioi_han=15.0) -> int:
    han = time.monotonic() + gioi_han
    while time.monotonic() < han:
        if p.exists() and p.read_text().strip():
            return int(p.read_text().strip())
        time.sleep(0.1)
    raise AssertionError(f"không thấy pid trong {p}")


# ---------------- env_toi_thieu (§4.7) ----------------

def test_env_toi_thieu_khong_lot_bien_la(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("BIEN_LA_CUA_TEST", "y")
    monkeypatch.setenv("GENMAX_API_KEY", "z")
    env = tt.env_toi_thieu({})
    assert "ANTHROPIC_API_KEY" not in env and "BIEN_LA_CUA_TEST" not in env and "GENMAX_API_KEY" not in env
    assert env["PYTHONUTF8"] == "1" and env["PYTHONIOENCODING"] == "utf-8"
    assert env["SYSTEMROOT"] and env["PATH"]
    assert set(env) <= set(tt.BIEN_MOI_TRUONG_CHEP) | {"PYTHONUTF8", "PYTHONIOENCODING"}
    env2 = tt.env_toi_thieu({"GENMAX_API_KEY": "z"})
    assert env2["GENMAX_API_KEY"] == "z"


# ---------------- bo_che (§4.7) ----------------

def _nguon(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"env": {
        "ANTHROPIC_AUTH_TOKEN": "tokenbimat-0123456789",
        "ANTHROPIC_BASE_URL": "https://proxy-bi-mat.example.com",
        "NGAN": "abc",                        # < 12 ký tự → không che
        "SO": 123}}), encoding="utf-8")
    khoa = tmp_path / ".video_key"
    khoa.write_text("videokey-ABCDEFGH1234\n", encoding="utf-8")
    radar = tmp_path / "cau-hinh.json"
    radar.write_text(json.dumps({"telegram": {"bot_token_x": "radar-secret-value-99", "chat": "chat-id-khong-che-1"},
                                 "ds": [{"password": "matkhau-dai-qua-12"}]}), encoding="utf-8")
    monkeypatch.setenv("BIEN_KHOA_TEST", "genmax-key-ZZZZZZZZ")
    return tt.NguonBiMat(settings_json=settings, file_khoa=[khoa, tmp_path / "khong-ton-tai.key"],
                         cau_hinh_radar=radar, ten_bien_moi_truong=["BIEN_KHOA_TEST", "BIEN_KHONG_CO"])


def test_bo_che_theo_gia_tri_va_mau(tmp_path, monkeypatch):
    che = tt.bo_che(_nguon(tmp_path, monkeypatch))
    s = ("a tokenbimat-0123456789 b https://proxy-bi-mat.example.com/v1 c abc d videokey-ABCDEFGH1234 "
         "e radar-secret-value-99 f chat-id-khong-che-1 g matkhau-dai-qua-12 h genmax-key-ZZZZZZZZ "
         "i sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAA j ghp_abcdefghij12345 k 123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    r = che(s)
    for bi_mat in ["tokenbimat-0123456789", "proxy-bi-mat", "videokey-ABCDEFGH1234", "radar-secret-value-99",
                   "matkhau-dai-qua-12", "genmax-key-ZZZZZZZZ", "sk-ant-api03", "ghp_abcdefghij", "123456789:AAAA"]:
        assert bi_mat not in r, bi_mat
    assert " abc " in r                           # giá trị ngắn không che
    assert "chat-id-khong-che-1" in r             # khoá không khớp token|key|secret|pass
    assert r.count("***") >= 9


def test_bo_che_doc_lai_khi_mtime_doi(tmp_path, monkeypatch):
    nguon = _nguon(tmp_path, monkeypatch)
    che = tt.bo_che(nguon)
    assert "gia-tri-moi-sau-khi-sua" in che("x gia-tri-moi-sau-khi-sua")
    nguon.settings_json.write_text(json.dumps({"env": {"ANTHROPIC_API_KEY": "gia-tri-moi-sau-khi-sua"}}),
                                   encoding="utf-8")
    m = nguon.settings_json.stat().st_mtime + 5
    os.utime(nguon.settings_json, (m, m))
    assert "gia-tri-moi-sau-khi-sua" not in che("x gia-tri-moi-sau-khi-sua")


def test_bo_che_file_json_hong_giu_gia_tri_cu_va_ghi_log(tmp_path, monkeypatch, caplog):
    nguon = _nguon(tmp_path, monkeypatch)
    che = tt.bo_che(nguon)
    assert "tokenbimat" not in che("tokenbimat-0123456789")
    nguon.settings_json.write_text("{hỏng", encoding="utf-8")
    m = nguon.settings_json.stat().st_mtime + 5
    os.utime(nguon.settings_json, (m, m))
    with caplog.at_level("WARNING"):
        assert "tokenbimat" not in che("tokenbimat-0123456789")
    assert any("settings" in r.getMessage() for r in caplog.records)


# ---------------- ffmpeg_ngoai (§4.4) ----------------

def test_co_ffmpeg_ngoai_logic_thuan():
    goc = {100}
    assert tt._co_ffmpeg_ngoai([], goc) is False
    assert tt._co_ffmpeg_ngoai([(200, [150, 100, 4])], goc) is False      # con cháu của runner
    assert tt._co_ffmpeg_ngoai([(100, [4])], goc) is False                 # chính là gốc
    assert tt._co_ffmpeg_ngoai([(200, [150, 4])], goc) is True             # ngoài cây
    assert tt._co_ffmpeg_ngoai([(200, None)], goc) is True                 # không đọc được cha → coi là ngoài
    assert tt._co_ffmpeg_ngoai([(200, [100]), (300, [9])], goc) is True


def test_ffmpeg_ngoai_chay_that_tra_bool():
    assert isinstance(tt.ffmpeg_ngoai({os.getpid()}), bool)


# ---------------- chay_tien_trinh: Claude giả ----------------

CLAUDE_GIA = r"""
import json, sys, time
def p(o): print(json.dumps(o, ensure_ascii=False), flush=True)
phieu = sys.stdin.buffer.read().decode("utf-8")
p({"type": "system", "subtype": "init", "session_id": "%SID%"})
print("dòng không phải json", flush=True)
print("cảnh báo stderr", file=sys.stderr, flush=True)
so = int(sys.argv[1])
for i in range(so):
    # message 0 phát 2 sự kiện cùng id (2 khối content) → chỉ tính 1 lượt
    p({"type": "assistant", "message": {"id": f"m{i}", "content": [{"type": "text", "text": f"lượt {i}: " + phieu}]}})
    if i == 0:
        p({"type": "assistant", "message": {"id": "m0", "content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "a"}}]}})
ngu = float(sys.argv[2])
if ngu:
    time.sleep(ngu)
p({"type": "result", "subtype": "success", "session_id": "%SID%", "total_cost_usd": 0.05,
   "num_turns": so, "is_error": False, "result": "TRẠNG THÁI: DONE", "permission_denials": []})
""".replace("%SID%", SID)


def test_claude_gia_session_va_so_luot(tmp_path):
    sc = viet_script(tmp_path, "claude_gia.py", CLAUDE_GIA)
    jl = tmp_path / "viec.jsonl"
    kq, ghi = chay(tmp_path, [PY, str(sc), "2", "0"], stdin_text="Phiếu: đặng thị ữ", la_claude=True,
                   file_jsonl=jl, tran_luot=5)
    assert kq.ma_thoat == 0 and not kq.het_gio and not kq.bi_huy and not kq.vuot_luot
    assert kq.session_id == SID and ghi["session"] == [SID]
    assert kq.so_luot == 2
    assert kq.ket_qua["chi_phi_usd"] == 0.05 and kq.ket_qua["so_luot"] == 2
    assert kq.van_ban_cuoi == "TRẠNG THÁI: DONE"
    assert kq.cong_cu_da_goi == ["Read"]
    pid, luc = ghi["bat_dau"][0]
    assert pid > 0 and abs(luc - time.time()) < 120
    tho = jl.read_text(encoding="utf-8")
    assert tho.count('"type": "assistant"') == 3 and "dòng không phải json" not in tho
    log = (tmp_path / "viec.log").read_text(encoding="utf-8")
    assert "lượt 1: Phiếu: đặng thị ữ" in log                 # stdin tiếng Việt qua nguyên vẹn
    assert "[stderr] cảnh báo stderr" in log and "dòng không phải json" in log
    assert any("init" in d for d in ghi["dong"])


def test_vuot_tran_luot_giet_tien_trinh(tmp_path):
    sc = viet_script(tmp_path, "claude_gia.py", CLAUDE_GIA)
    t0 = time.monotonic()
    kq, ghi = chay(tmp_path, [PY, str(sc), "3", "60"], stdin_text="x", la_claude=True, tran_luot=2)
    pid = ghi["bat_dau"][0][0]
    try:
        assert kq.vuot_luot and not kq.het_gio
        assert kq.so_luot == 3
        assert kq.ket_qua is None
        assert time.monotonic() - t0 < 30
        assert cho_chet([pid]) == []
    finally:
        don_pid([pid])


def test_van_ban_cuoi_khi_khong_co_result(tmp_path):
    sc = viet_script(tmp_path, "c.py", r"""
        import json
        print(json.dumps({"type": "assistant", "message": {"id": "a", "content": [{"type": "text", "text": "câu đầu"}]}}))
        print(json.dumps({"type": "assistant", "message": {"id": "b", "content": [{"type": "text", "text": "câu cuối"}]}}))
        raise SystemExit(7)
    """)
    kq, _ = chay(tmp_path, [PY, str(sc)], la_claude=True)
    assert kq.ma_thoat == 7 and kq.ket_qua is None and kq.van_ban_cuoi == "câu cuối" and kq.session_id is None


# ---------------- chay_tien_trinh: script thường ----------------

def test_script_thuong_stdin_tieng_viet_va_ma_thoat(tmp_path):
    sc = viet_script(tmp_path, "s.py", r"""
        import sys
        b = sys.stdin.buffer.read()
        open(sys.argv[1], "wb").write(b)
        print("nhận:", b.decode("utf-8"))
        print("lỗi ra stderr", file=sys.stderr)
        raise SystemExit(3)
    """)
    chu = "Tiếng Việt có dấu: ắ ằ ẳ ẵ ặ — Đ đ ơ ư\nDòng 2 🙂"
    ra = tmp_path / "stdin_nhan.bin"
    kq, ghi = chay(tmp_path, [PY, str(sc), str(ra)], stdin_text=chu)
    assert ra.read_bytes() == chu.encode("utf-8")
    assert kq.ma_thoat == 3 and kq.session_id is None and kq.so_luot == 0
    assert "nhận: Tiếng Việt có dấu" in kq.van_ban_cuoi and "lỗi ra stderr" in kq.van_ban_cuoi
    assert "lỗi ra stderr" in ghi["dong"]


def test_qua_gio_giet_ca_cay(tmp_path):
    pid_con = tmp_path / "con.pid"
    sc = viet_script(tmp_path, "cha.py", r"""
        import subprocess, sys, time
        c = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        open(sys.argv[1], "w").write(str(c.pid))
        print("đã sinh con", flush=True)
        time.sleep(120)
    """)
    t0 = time.monotonic()
    kq, ghi = chay(tmp_path, [PY, str(sc), str(pid_con)], het_gio_s=3)
    cha = ghi["bat_dau"][0][0]
    con = doc_pid_tu_file(pid_con)
    try:
        assert kq.het_gio and not kq.bi_huy
        assert time.monotonic() - t0 < 30
        assert cho_chet([cha, con]) == []
        assert "quá giờ" in (tmp_path / "viec.log").read_text(encoding="utf-8")
    finally:
        don_pid([cha, con])


def test_huy_giet_tien_trinh(tmp_path):
    sc = viet_script(tmp_path, "ngu.py", "import time; print('bắt đầu', flush=True); time.sleep(120)\n")
    huy = threading.Event()
    threading.Timer(1.0, huy.set).start()
    kq, ghi = chay(tmp_path, [PY, str(sc)], huy=huy)
    pid = ghi["bat_dau"][0][0]
    try:
        assert kq.bi_huy and not kq.het_gio
        assert cho_chet([pid]) == []
    finally:
        don_pid([pid])


def test_huy_ma_giet_that_bai_khong_ket_vo_han(tmp_path, monkeypatch):
    """R-06 P3-5: huỷ mà giet_cay thất bại (tiến trình giả không chết) → sau CHO_SAU_GIET_S trả về với cờ
    khong_giet_duoc, không kẹt vô hạn, không ném lỗi dọn."""
    monkeypatch.setattr(tt, "giet_cay", lambda pid, tl: False)
    monkeypatch.setattr(tt, "_tao_job_rieng", lambda proc: None)       # Job riêng sẽ giết thật → tắt để mô phỏng
    monkeypatch.setattr(tt, "CHO_SAU_GIET_S", 1.0)
    sc = viet_script(tmp_path, "ngu.py", "import time; print('bắt đầu', flush=True); time.sleep(120)\n")
    huy = threading.Event()
    threading.Timer(0.5, huy.set).start()
    bd = time.monotonic()
    kq, ghi = chay(tmp_path, [PY, str(sc)], huy=huy)
    pid = ghi["bat_dau"][0][0]
    try:
        assert time.monotonic() - bd < 20
        assert kq.bi_huy and kq.khong_giet_duoc and kq.pid == pid and kq.ma_thoat is None
        assert kq.pid_tao_luc == ghi["bat_dau"][0][1]                  # FX-5: để vòng chạy kiểm pid còn sống
        assert psutil.pid_exists(pid)                                  # thật sự chưa chết (đúng mô phỏng)
        log = (tmp_path / "viec.log").read_text(encoding="utf-8")
        assert "KHÔNG giết được" in log
    finally:
        don_pid([pid])


def test_huy_giet_duoc_thi_co_khong_giet_duoc_false(tmp_path):
    sc = viet_script(tmp_path, "ngu.py", "import time; time.sleep(120)\n")
    huy = threading.Event()
    huy.set()
    kq, ghi = chay(tmp_path, [PY, str(sc)], huy=huy)
    try:
        assert kq.bi_huy and not kq.khong_giet_duoc
    finally:
        don_pid([ghi["bat_dau"][0][0]])


def test_chau_giu_pipe_khong_treo(tmp_path):
    """Cha thoát ngay nhưng cháu kế thừa stdout và ngủ 120 s → không được treo."""
    pid_chau = tmp_path / "chau.pid"
    sc = viet_script(tmp_path, "cha.py", r"""
        import subprocess, sys
        c = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], stdout=sys.stdout)
        open(sys.argv[1], "w").write(str(c.pid))
        print("cha thoát", flush=True)
    """)
    t0 = time.monotonic()
    kq, _ = chay(tmp_path, [PY, str(sc), str(pid_chau)])
    chau = doc_pid_tu_file(pid_chau)
    try:
        assert kq.ma_thoat == 0
        assert time.monotonic() - t0 < 40
        assert "cha thoát" in kq.van_ban_cuoi
        assert cho_chet([chau]) == []
    finally:
        don_pid([chau])


def test_callback_loi_van_giet_tien_trinh_va_nem_loi(tmp_path):
    sc = viet_script(tmp_path, "ngu.py", "import time; time.sleep(120)\n")
    ghi_pid = []

    def bat_dau_loi(pid, luc):
        ghi_pid.append(pid)
        raise RuntimeError("DB hỏng giả")

    try:
        with pytest.raises(RuntimeError, match="DB hỏng giả"):
            chay(tmp_path, [PY, str(sc)], khi_bat_dau=bat_dau_loi)
        assert cho_chet(ghi_pid) == []
    finally:
        don_pid(ghi_pid)


def test_lenh_khong_ton_tai_nem_loi_va_ghi_log(tmp_path):
    with pytest.raises(OSError):
        chay(tmp_path, [str(tmp_path / "khong-co.exe")])
    assert "Không chạy được" in (tmp_path / "viec.log").read_text(encoding="utf-8")


# ---------------- giet_cay ----------------

def _sinh_cha_con(tmp_path):
    pid_con = tmp_path / "con.pid"
    sc = viet_script(tmp_path, "cha.py", r"""
        import subprocess, sys, time
        c = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        open(sys.argv[1], "w").write(str(c.pid))
        time.sleep(120)
    """)
    p = subprocess.Popen([PY, str(sc), str(pid_con)], creationflags=subprocess.CREATE_NO_WINDOW)
    return p, doc_pid_tu_file(pid_con)


def test_giet_cay_giet_cha_va_con(tmp_path):
    p, con = _sinh_cha_con(tmp_path)
    try:
        assert tt.giet_cay(p.pid, psutil.Process(p.pid).create_time()) is True
        assert cho_chet([p.pid, con]) == []
    finally:
        don_pid([p.pid, con])


def test_giet_cay_pid_tai_dung_khong_dung(tmp_path):
    p, con = _sinh_cha_con(tmp_path)
    try:
        assert tt.giet_cay(p.pid, psutil.Process(p.pid).create_time() + 100) is False
        assert psutil.pid_exists(p.pid) and psutil.pid_exists(con)
    finally:
        don_pid([p.pid, con])


def test_giet_cay_pid_da_chet():
    p = subprocess.Popen([PY, "-c", "pass"])
    p.wait(timeout=30)
    assert tt.giet_cay(p.pid, None) is True or not psutil.pid_exists(p.pid)


# ---------------- gianh_don_instance (§4.1) ----------------

GIANH = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from runner import thuc_thi as tt
k = tt.gianh_don_instance(Path(sys.argv[2]), ten_mutex=sys.argv[3])
print("NONE" if k is None else "OK", flush=True)
if k is not None:
    sys.stdin.read()          # giữ khoá tới khi stdin đóng
    k.nha()
"""


def _gianh(tmp_path, thu_muc, ten):
    sc = tmp_path / "gianh.py"
    sc.write_text(GIANH, encoding="utf-8")
    p = subprocess.Popen([PY, "-B", str(sc), str(TOOLS), str(thu_muc), ten], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    return p, p.stdout.readline().decode().strip()


def test_gianh_don_instance_lan_hai_tra_none(tmp_path):
    thu_muc = tmp_path / "du_lieu"
    ten = "Local\\kho-runner-test-" + uuid.uuid4().hex
    a, kq_a = _gianh(tmp_path, thu_muc, ten)
    ds = [a]
    try:
        assert kq_a == "OK"
        b, kq_b = _gianh(tmp_path, thu_muc, ten)                  # cùng mutex, cùng thư mục
        ds.append(b)
        assert kq_b == "NONE"
        c, kq_c = _gianh(tmp_path, thu_muc, ten + "-khac")        # mutex khác → lưới thứ hai runner.lock
        ds.append(c)
        assert kq_c == "NONE"
        a.stdin.close()
        assert a.wait(timeout=30) == 0                            # nhả khoá không lỗi
        d, kq_d = _gianh(tmp_path, thu_muc, ten)
        ds.append(d)
        assert kq_d == "OK"                                       # đã nhả thì giành lại được
        d.stdin.close()
        assert d.wait(timeout=30) == 0
    finally:
        for p in ds:
            if p.poll() is None:
                p.kill()


# ---------------- tu_gan_job_object (§4.6) ----------------

TRUNG_GIAN = r"""
import subprocess, sys, time
sys.path.insert(0, sys.argv[1])
from runner import thuc_thi as tt
print("GAN", tt.tu_gan_job_object(), flush=True)
c = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
print("CON", c.pid, flush=True)
time.sleep(120)
"""


def test_job_object_giet_con_khi_cha_chet(tmp_path):
    sc = tmp_path / "trung_gian.py"
    sc.write_text(TRUNG_GIAN, encoding="utf-8")
    p = subprocess.Popen([PY, "-B", str(sc), str(TOOLS)], stdout=subprocess.PIPE,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    con = None
    try:
        assert p.stdout.readline().decode().split() == ["GAN", "True"]
        con = int(p.stdout.readline().decode().split()[1])
        assert psutil.pid_exists(con)
        p.kill()                                    # TerminateProcess: cha chết đột ngột
        p.wait(timeout=30)
        assert cho_chet([con]) == []                # con chết theo nhờ KILL_ON_JOB_CLOSE
    finally:
        if p.poll() is None:
            p.kill()
        if con:
            don_pid([con])


# ---------------- FX-5 (R-07) ----------------

KHOA_32 = "Qz7v" * 8


def test_log_claude_che_input_truoc_khi_cat_khong_lo_tien_to(tmp_path):
    """R-07 P2-2: input công cụ 270 ký tự + khoá 32 ký tự → .log không chứa tiền tố nào ≥8 ký tự của khoá."""
    sc = viet_script(tmp_path, "c.py", r"""
        import json, sys
        k = sys.argv[1]
        def p(o): print(json.dumps(o, ensure_ascii=False), flush=True)
        p({"type": "system", "subtype": "init", "session_id": "s1", "tools": ["Bash"]})
        p({"type": "assistant", "message": {"id": "m1", "content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "x" * 270 + k}},
            {"type": "text", "text": "a" * 1990 + k}]}})
        p({"type": "user", "message": {"content": [{"type": "tool_result", "content": "b" * 290 + k}]}})
        p({"type": "result", "subtype": "success", "session_id": "s1", "result": "xong"})
    """)
    kq, _ = chay(tmp_path, [PY, str(sc), KHOA_32], la_claude=True, file_jsonl=tmp_path / "v.jsonl",
                 che=lambda s: s.replace(KHOA_32, "***"))
    assert kq.ma_thoat == 0
    log = (tmp_path / "viec.log").read_text(encoding="utf-8")
    assert "[công cụ] Bash" in log and "[kết quả công cụ]" in log
    lo = [KHOA_32[:n] for n in range(8, 33) if KHOA_32[:n] in log]
    assert lo == [], lo[:1]


def test_ngoai_le_ma_khong_giet_duoc_gan_co_va_pid_len_loi(tmp_path, monkeypatch):
    """R-07 P3-1: callback ném lỗi, giết không được, proc.wait hết giờ → lỗi ném ra mang cờ khong_giet_duoc + pid
    (để vòng chạy xử lý như P2-4), không chỉ nằm im trong loi_don."""
    monkeypatch.setattr(tt, "giet_cay", lambda pid, tl: False)
    monkeypatch.setattr(tt, "_tao_job_rieng", lambda proc: None)
    monkeypatch.setattr(tt, "CHO_DON_S", 1.0)
    sc = viet_script(tmp_path, "ngu.py", "import time; print('bắt đầu', flush=True); time.sleep(120)\n")

    def doc_loi(d):
        raise RuntimeError("callback hỏng giả")
    pids = []
    try:
        with pytest.raises(RuntimeError, match="callback hỏng giả") as e:
            chay(tmp_path, [PY, str(sc)], khi_doc_dong=doc_loi,
                 khi_bat_dau=lambda pid, tl: pids.append((pid, tl)))
        pid, tl = pids[0]
        assert tt.khong_giet_tu_loi(e.value) == (pid, tl)
        assert psutil.pid_exists(pid)
        assert "KHÔNG giết được" in (tmp_path / "viec.log").read_text(encoding="utf-8")
    finally:
        don_pid([p for p, _ in pids])


def test_khong_giet_tu_loi_loi_thuong_tra_none():
    assert tt.khong_giet_tu_loi(RuntimeError("x")) is None
    assert tt.khong_giet_tu_loi(OSError(2, "y")) is None
