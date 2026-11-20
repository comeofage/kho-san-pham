"""Test đọc sự kiện stream-json (§6.2) — chạy: python -B -m pytest tools/test_runner_stream_json.py -q

Fixture theo TÊN TRƯỜNG đã được spike S-1 xác nhận (A-2):
- system/init: session_id, tools, permissionMode, model, apiKeySource, agents, mcp_servers
- assistant: message, parent_tool_use_id, error
- result: subtype, is_error, session_id, total_cost_usd, num_turns, duration_ms, result, permission_denials
init.session_id == --session-id; result.session_id == init.session_id.
Giá trị trong fixture là giá trị giả (không chép dữ liệu thật của máy).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from runner import stream_json as sj  # noqa: E402

SID = "0b6f3f7e-9d7c-4c1e-8a59-2d3c1b9a7e11"

# Mỗi dòng một sự kiện, đúng dạng giả định §6.2.
FIXTURE = [
    {"type": "system", "subtype": "init", "session_id": SID, "model": "claude-x",
     "tools": ["Read", "Write"], "cwd": "E:\\du-an", "permissionMode": "dontAsk", "apiKeySource": "none",
     "agents": ["thu-runner"], "mcp_servers": []},
    {"type": "assistant", "session_id": SID, "parent_tool_use_id": None,
     "message": {"id": "msg_01", "role": "assistant",
                 "content": [{"type": "text", "text": "Đang đọc file sản phẩm."}]}},
    {"type": "assistant", "session_id": SID, "parent_tool_use_id": None,
     "message": {"id": "msg_02", "role": "assistant",
                 "content": [{"type": "tool_use", "id": "tu_1", "name": "Read",
                              "input": {"file_path": "E:\\du-an\\a.md"}},
                             {"type": "tool_use", "id": "tu_2", "name": "Agent",
                              "input": {"subagent_type": "codex:rescue", "prompt": "x"}}]}},
    {"type": "user", "session_id": SID,
     "message": {"role": "user", "content": [
         {"type": "tool_result", "tool_use_id": "tu_1", "content": "nội dung file", "is_error": False}]}},
    {"type": "result", "subtype": "success", "session_id": SID, "total_cost_usd": 0.1234,
     "num_turns": 3, "duration_ms": 4321, "is_error": False, "result": "TRẠNG THÁI: DONE\nXong.",
     "permission_denials": [{"tool_name": "Write", "tool_input": {"file_path": "x"}}]},
]


def dong(i: int) -> str:
    return json.dumps(FIXTURE[i], ensure_ascii=False)


# ---------------- doc_su_kien ----------------

def test_doc_su_kien_json_hop_le():
    sk = sj.doc_su_kien(dong(0))
    assert sk["type"] == "system"


def test_doc_su_kien_chiu_khoang_trang_va_crlf():
    assert sj.doc_su_kien("  " + dong(0) + "\r\n")["subtype"] == "init"


def test_doc_su_kien_khong_phai_json_tra_none():
    for x in ["", "   ", "không phải json", "{hỏng", "[1,2]", "123", '"chuoi"', "null"]:
        assert sj.doc_su_kien(x) is None, x


# ---------------- la_khoi_tao ----------------

def test_la_khoi_tao():
    assert sj.la_khoi_tao(FIXTURE[0]) == SID
    for i in range(1, 5):
        assert sj.la_khoi_tao(FIXTURE[i]) is None
    assert sj.la_khoi_tao({"type": "system", "subtype": "init"}) is None          # thiếu session_id
    assert sj.la_khoi_tao({"type": "system", "subtype": "khac", "session_id": SID}) is None
    assert sj.la_khoi_tao({"type": "system", "subtype": "init", "session_id": 123}) is None


# ---------------- la_ket_qua ----------------

def test_la_ket_qua_thanh_cong():
    kq = sj.la_ket_qua(FIXTURE[4])
    assert kq == {"session_id": SID, "chi_phi_usd": 0.1234, "so_luot": 3, "loi": False,
                  "van_ban": "TRẠNG THÁI: DONE\nXong.",
                  "bi_tu_choi": [{"tool_name": "Write", "tool_input": {"file_path": "x"}}]}


def test_la_ket_qua_loi_va_thieu_truong():
    kq = sj.la_ket_qua({"type": "result", "subtype": "error_during_execution", "is_error": False})
    assert kq["loi"] is True                       # subtype error_* cũng là lỗi
    assert kq["chi_phi_usd"] == 0.0 and kq["so_luot"] == 0
    assert kq["van_ban"] == "" and kq["bi_tu_choi"] == [] and kq["session_id"] is None
    assert sj.la_ket_qua({"type": "result", "is_error": True, "total_cost_usd": "x"})["loi"] is True


def test_la_ket_qua_khong_phai_result():
    for i in range(4):
        assert sj.la_ket_qua(FIXTURE[i]) is None


# ---------------- dem_luot / ma_message ----------------

def test_dem_luot():
    assert [sj.dem_luot(sk) for sk in FIXTURE] == [0, 1, 1, 0, 0]
    assert sj.dem_luot({"type": "assistant"}) == 0           # không có message
    assert sj.ma_message(FIXTURE[1]) == "msg_01"
    assert sj.ma_message(FIXTURE[0]) is None


# ---------------- ten_cong_cu ----------------

def test_ten_cong_cu():
    assert sj.ten_cong_cu(FIXTURE[1]) == []
    assert sj.ten_cong_cu(FIXTURE[2]) == [
        ("Read", {"file_path": "E:\\du-an\\a.md"}),
        ("Agent", {"subagent_type": "codex:rescue", "prompt": "x"})]
    assert sj.ten_cong_cu(FIXTURE[3]) == []
    assert sj.ten_cong_cu({"type": "assistant", "message": {"content": "chuoi"}}) == []
    assert sj.ten_cong_cu({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash"}]}}) == [("Bash", {})]


def test_van_ban_assistant():
    assert sj.van_ban_assistant(FIXTURE[1]) == "Đang đọc file sản phẩm."
    assert sj.van_ban_assistant(FIXTURE[2]) is None
    assert sj.van_ban_assistant(FIXTURE[4]) is None


# ---------------- dich_dong ----------------

def test_dich_dong():
    d = [sj.dich_dong(sk) for sk in FIXTURE]
    assert SID in d[0]
    assert "Đang đọc file sản phẩm." in d[1]
    assert "Read" in d[2] and "Agent" in d[2] and "a.md" in d[2]
    assert "nội dung file" in d[3]
    assert "0.1234" in d[4] and "3 lượt" in d[4] and "từ chối 1" in d[4]
    assert sj.dich_dong({"type": "stream_event"}) is None


def test_dich_dong_cat_ngan_input_dai():
    sk = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Write", "input": {"content": "x" * 5000}}]}}
    assert len(sj.dich_dong(sk)) < 600


# ---------------- trường S-1 xác nhận: init.tools / mcp_servers, assistant.error ----------------

INIT_LOT_MCP = {"type": "system", "subtype": "init", "session_id": SID, "model": "claude-x",
                "tools": ["Read", "Glob", "mcp__engram__mem_save", "mcp__boardroom__x"],
                "permissionMode": "dontAsk", "apiKeySource": "ANTHROPIC_API_KEY", "agents": [],
                "mcp_servers": [{"name": "engram", "status": "connected"}]}


def test_thong_tin_khoi_tao():
    tt = sj.thong_tin_khoi_tao(FIXTURE[0])
    assert tt == {"session_id": SID, "cong_cu": ["Read", "Write"], "che_do_quyen": "dontAsk",
                  "model": "claude-x", "nguon_khoa": "none", "mcp": []}
    assert sj.thong_tin_khoi_tao(FIXTURE[1]) is None
    t2 = sj.thong_tin_khoi_tao(INIT_LOT_MCP)
    assert t2["mcp"] == ["engram"]
    # trường hỏng không làm vỡ
    t3 = sj.thong_tin_khoi_tao({"type": "system", "subtype": "init", "session_id": SID, "tools": "x",
                                "mcp_servers": [1, {"name": 2}, "abc"]})
    assert t3["cong_cu"] == [] and t3["mcp"] == ["abc"]


def test_cong_cu_ngoai_danh_sach():
    """S-1: --tools không chặn được công cụ MCP người dùng → runner tự soát sự kiện init."""
    assert sj.cong_cu_ngoai(FIXTURE[0], ("Read", "Write", "Glob")) == []
    assert sj.cong_cu_ngoai(INIT_LOT_MCP, ("Read", "Glob")) == ["mcp__engram__mem_save", "mcp__boardroom__x"]
    assert sj.cong_cu_ngoai(FIXTURE[1], ("Read",)) == []          # không phải init
    # init báo mcp server dù tools không liệt kê → vẫn coi là lọt
    sk = dict(FIXTURE[0], mcp_servers=[{"name": "boardroom", "status": "connected"}])
    assert sj.cong_cu_ngoai(sk, ("Read", "Write")) == ["mcp:boardroom"]


# ---------------- P2-1 (R-05): soát công cụ trên MỌI sự kiện, có trạng thái init ----------------

CP = ("Read", "Write", "Glob")


def _asst(*ten, mid="m1"):
    return {"type": "assistant", "parent_tool_use_id": None,
            "message": {"id": mid, "content": [{"type": "tool_use", "id": f"t{i}", "name": t, "input": {}}
                                               for i, t in enumerate(ten)]}}


def test_soat_init_thieu_tools_la_vi_pham():
    """(a) init thiếu `tools` → không biết bộ công cụ → dừng phiên."""
    sk = {k: v for k, v in FIXTURE[0].items() if k != "tools"}
    s = sj.SoatCongCu(CP)
    vp = s.xet(sk)
    assert vp and "tools" in vp[0]


def test_soat_init_tools_sai_dang_la_vi_pham():
    """(a) `tools` không phải list (hoặc phần tử không phải chuỗi) → vi phạm."""
    for sai in ("Read,Write", {"Read": 1}, None, 5, ["Read", 3], ["Read", ""]):
        vp = sj.SoatCongCu(CP).xet(dict(FIXTURE[0], tools=sai))
        assert vp and "tools" in vp[0], sai


def test_soat_init_khong_session_id_van_soat_mcp():
    """init không có session_id mà có mcp__* → vẫn bị bắt (trước đây lọt vì chỉ xét init có session_id)."""
    sk = {k: v for k, v in INIT_LOT_MCP.items() if k != "session_id"}
    assert sj.SoatCongCu(("Read", "Glob")).xet(sk) == ["mcp__engram__mem_save", "mcp__boardroom__x"]
    assert sj.cong_cu_ngoai(sk, ("Read", "Glob")) == ["mcp__engram__mem_save", "mcp__boardroom__x"]


def test_soat_assistant_tool_use_ngoai_danh_sach():
    """(b) assistant gọi tool_use mcp__* (init sạch) → vi phạm."""
    s = sj.SoatCongCu(CP)
    assert s.xet(FIXTURE[0]) == []
    assert s.xet(_asst("Read", "mcp__engram__mem_save")) == ["mcp__engram__mem_save"]
    assert s.xet(_asst("Bash")) == ["Bash"]


def test_soat_tool_use_ten_rong_so_va_server_tool_use_la_vi_pham():
    """R-06 P3-2: tool_use tên rỗng/số/thiếu và mọi khối *tool_use (server_tool_use…) ngoài danh sách → vi phạm."""
    def asst(*khoi):
        return {"type": "assistant", "parent_tool_use_id": None,
                "message": {"id": "mx", "content": [{"id": f"t{i}", "input": {}, **k} for i, k in enumerate(khoi)]}}
    s = sj.SoatCongCu(CP)
    assert s.xet(FIXTURE[0]) == []
    for k in ({"type": "tool_use", "name": ""}, {"type": "tool_use", "name": 5}, {"type": "tool_use"},
              {"type": "tool_use", "name": None}, {"type": "server_tool_use", "name": ""}):
        vp = s.xet(asst(k))
        assert len(vp) == 1 and "không hợp lệ" in vp[0], (k, vp)
    assert s.xet(asst({"type": "server_tool_use", "name": "web_search"})) == ["server_tool_use:web_search"]
    assert s.xet(asst({"type": "mcp_tool_use", "name": "mcp__x__y"})) == ["mcp_tool_use:mcp__x__y"]
    # khối *tool_use mà tên nằm trong danh sách, và khối không phải tool_use → không vi phạm
    assert s.xet(asst({"type": "tool_use", "name": "Read"}, {"type": "server_tool_use", "name": "Read"},
                      {"type": "tool_result", "name": 5}, {"type": "text", "text": "x"})) == []
    assert sj.cong_cu_ngoai(asst({"type": "tool_use", "name": 7}), CP)


def test_soat_assistant_truoc_init_la_vi_pham():
    """(c) có sự kiện assistant trước khi thấy init → dừng phiên (kể cả assistant chỉ có text)."""
    s = sj.SoatCongCu(CP)
    vp = s.xet(FIXTURE[1])
    assert vp and "init" in vp[0]
    s2 = sj.SoatCongCu(CP)
    assert s2.xet(_asst("Read")) and "init" in s2.xet(_asst("Read"))[0]


def test_soat_phien_hop_le_khong_bi_chan():
    s = sj.SoatCongCu(CP + ("Agent",))
    for sk in FIXTURE:
        assert s.xet(sk) == [], sk
    s = sj.SoatCongCu(CP)
    for sk in [FIXTURE[0], FIXTURE[1], _asst("Read", "Write"), FIXTURE[3], FIXTURE[4],
               {"type": "system", "subtype": "khac"}, {"type": "stream_event"}, {}]:
        assert s.xet(sk) == [], sk
    # init tools rỗng là list hợp lệ (không công cụ nào)
    assert sj.SoatCongCu(CP).xet(dict(FIXTURE[0], tools=[])) == []


def test_loi_assistant():
    sk = {"type": "assistant", "parent_tool_use_id": None, "error": "authentication_failed",
          "message": {"id": "m9", "content": [{"type": "text", "text": "Invalid API key · Please run /login"}]}}
    assert sj.loi_assistant(sk) == "authentication_failed"
    assert sj.loi_assistant(FIXTURE[1]) is None
    assert sj.loi_assistant({"type": "assistant", "error": {"type": "rate_limit"}}) == '{"type": "rate_limit"}'
    assert sj.loi_assistant({"type": "result", "error": "x"}) is None
    assert "[lỗi agent] authentication_failed" in sj.dich_dong(sk)


def test_ket_qua_loi_dang_nhap_chi_phi_0():
    """Dạng result S-1 thấy khi claude báo Invalid API key: is_error true, total_cost_usd 0."""
    kq = sj.la_ket_qua({"type": "result", "subtype": "success", "is_error": True, "session_id": SID,
                        "total_cost_usd": 0, "num_turns": 1, "duration_ms": 900,
                        "result": "Invalid API key · Please run /login", "permission_denials": []})
    assert kq["loi"] is True and kq["chi_phi_usd"] == 0.0 and kq["session_id"] == SID


def test_ham_khong_vo_voi_su_kien_la():
    la = [{}, {"type": None}, {"type": "assistant", "message": None},
          {"type": "assistant", "message": {"content": [None, 1, "x"]}},
          {"type": "user", "message": {"content": [{"type": "tool_result", "content": [
              {"type": "text", "text": "a"}, {"type": "image"}]}]}},
          {"type": "result", "permission_denials": "khong-phai-list"}]
    for sk in la:
        sj.la_khoi_tao(sk); sj.la_ket_qua(sk); sj.dem_luot(sk)
        sj.ten_cong_cu(sk); sj.dich_dong(sk); sj.ma_message(sk); sj.van_ban_assistant(sk)
        sj.thong_tin_khoi_tao(sk); sj.cong_cu_ngoai(sk, ("Read",)); sj.loi_assistant(sk)
    assert sj.la_ket_qua(la[-1])["bi_tu_choi"] == []


# ---------------- FX-5 (R-07 P2-2): che trên bản đầy đủ TRƯỚC khi cắt ----------------

KHOA_32 = "Qz7v" * 8                       # 32 ký tự, không khớp mẫu bí mật → chỉ che theo giá trị


def _che_khoa(s: str) -> str:
    return s.replace(KHOA_32, "***")


def _tien_to_lo(s: str, khoa: str = KHOA_32, toi_thieu: int = 8) -> list[str]:
    """Mọi tiền tố ≥ `toi_thieu` ký tự của khoá còn nằm trong `s` (rỗng = không lộ)."""
    return [khoa[:n] for n in range(toi_thieu, len(khoa) + 1) if khoa[:n] in s]


def test_dich_dong_input_cong_cu_che_truoc_khi_cat_300():
    """input 270 ký tự + khoá 32 → điểm cắt 300 rơi giữa khoá; phải che bản đủ rồi mới cắt."""
    sk = {"type": "assistant", "message": {"id": "m", "content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": "x" * 270 + KHOA_32}}]}}
    assert _tien_to_lo(sj.dich_dong(sk)), "điều kiện test: không che thì phải lộ tiền tố"
    d = sj.dich_dong(sk, _che_khoa)
    assert _tien_to_lo(d) == [] and "***" in d


def test_dich_dong_van_ban_va_ket_qua_cong_cu_che_truoc_khi_cat():
    van_ban = {"type": "assistant", "message": {"id": "m", "content": [
        {"type": "text", "text": "a" * 1990 + KHOA_32}]}}
    ket_qua = {"type": "user", "message": {"content": [
        {"type": "tool_result", "content": "b" * 290 + KHOA_32, "is_error": False}]}}
    loi = {"type": "assistant", "error": "c" * 290 + KHOA_32, "message": {"id": "m", "content": []}}
    for sk in (van_ban, ket_qua, loi):
        assert _tien_to_lo(sj.dich_dong(sk)), sk
        d = sj.dich_dong(sk, _che_khoa)
        assert _tien_to_lo(d) == [] and "***" in d, d[-80:]


def test_dich_dong_khong_truyen_che_giu_nguyen_hanh_vi():
    for sk in FIXTURE:
        assert sj.dich_dong(sk) == sj.dich_dong(sk, None) == sj.dich_dong(sk, lambda s: s)


# ---------------- B-5 (§7.3): phiên sống ----------------
# Tên trường theo .culiapp/test-spike-s3.json `lan_goi[0].loai_su_kien_va_truong` (giá trị giả).

def test_khong_doi_ham_cu_va_co_ket_thuc_nen():
    assert sj.KET_THUC_NEN == frozenset({"completed", "failed", "killed", "stopped", "error", "cancelled"})


def test_la_cap_cao():
    assert sj.la_cap_cao({"type": "result"}) is True                       # result thật không có trường này
    assert sj.la_cap_cao({"type": "assistant", "parent_tool_use_id": None}) is True
    assert sj.la_cap_cao({"type": "assistant", "parent_tool_use_id": ""}) is True
    assert sj.la_cap_cao({"type": "assistant", "parent_tool_use_id": "toolu_01"}) is False
    assert sj.la_cap_cao({"type": "assistant", "parent_tool_use_id": 0}) is False   # dạng lạ: không coi là cấp cao


def test_viec_nen_bat_dau():
    sk = {"type": "system", "subtype": "task_started", "task_id": "byftlkkuc", "tool_use_id": "toolu_1",
          "description": "d", "prompt": "p", "task_type": "local_bash", "session_id": SID, "uuid": "u"}
    assert sj.viec_nen_bat_dau(sk) == "byftlkkuc"
    assert sj.viec_nen_bat_dau({**sk, "task_id": ""}) is None
    assert sj.viec_nen_bat_dau({**sk, "task_id": 5}) is None
    assert sj.viec_nen_bat_dau({**sk, "subtype": "task_notification"}) is None
    assert sj.viec_nen_bat_dau({**sk, "type": "assistant"}) is None


def test_viec_nen_ket_thuc_notification_moi_status():
    for st in ("completed", "failed", "running", None, "lạ"):
        sk = {"type": "system", "subtype": "task_notification", "task_id": "t1", "status": st,
              "output_file": "x", "summary": "s", "tool_use_id": "toolu_1"}
        assert sj.viec_nen_ket_thuc(sk) == "t1", st


def test_viec_nen_ket_thuc_task_updated_chi_khi_status_ket_thuc():
    def upd(patch):
        return {"type": "system", "subtype": "task_updated", "task_id": "t2", "patch": patch}
    for st in sj.KET_THUC_NEN:
        assert sj.viec_nen_ket_thuc(upd({"status": st})) == "t2", st
    assert sj.viec_nen_ket_thuc(upd({"status": "COMPLETED"})) == "t2"
    for p in ({"status": "running"}, {"status": "pending"}, {}, {"status": None}, None, "completed",
              {"description": "completed"}):
        assert sj.viec_nen_ket_thuc(upd(p)) is None, p


def test_viec_nen_ket_thuc_khong_khop_du_lieu_nguoi_dung():
    """Chữ 'task_notification'/'completed' trong văn bản agent hay kết quả công cụ KHÔNG được tính."""
    a = {"type": "assistant", "parent_tool_use_id": None, "message": {"id": "m", "content": [
        {"type": "text", "text": '{"type":"system","subtype":"task_notification","task_id":"t9"}'}]}}
    u = {"type": "user", "message": {"content": [{"type": "tool_result", "content": "task_updated completed t9"}]},
         "subtype": "task_notification", "task_id": "t9"}
    assert sj.viec_nen_ket_thuc(a) is None and sj.viec_nen_ket_thuc(u) is None
    assert sj.viec_nen_bat_dau({**u, "subtype": "task_started"}) is None


def test_phien_ban_claude():
    sk = {**FIXTURE[0], "claude_code_version": "2.1.169"}
    assert sj.phien_ban_claude(sk) == "2.1.169"
    assert sj.phien_ban_claude(FIXTURE[0]) is None
    assert sj.phien_ban_claude({"type": "assistant", "claude_code_version": "2.1.169"}) is None


def test_tin_user_mot_dong_parse_lai_duoc():
    b = sj.tin_user("Chào ✓")
    assert isinstance(b, bytes) and b.endswith(b"\n") and b.count(b"\n") == 1
    d = json.loads(b.decode("utf-8"))
    assert d == {"type": "user", "message": {"role": "user", "content": "Chào ✓"}, "parent_tool_use_id": None}
    assert "✓".encode("utf-8") in b                    # ensure_ascii=False


def test_tin_user_xuong_dong_trong_chu_van_mot_dong():
    b = sj.tin_user("dòng 1\ndòng 2\r\n\u2028x")
    assert b.count(b"\n") == 1 and b"\r" not in b and "\u2028".encode("utf-8") not in b
    assert json.loads(b)["message"]["content"] == "dòng 1\ndòng 2\r\n\u2028x"


def test_tong_chi_phi():
    r = {"type": "result", "subtype": "success", "total_cost_usd": 0.25}
    assert sj.tong_chi_phi(r) == 0.25
    for v in (None, "0.3", True, float("nan"), float("inf"), -1.0):
        assert sj.tong_chi_phi({**r, "total_cost_usd": v}) is None, v
    assert sj.tong_chi_phi({"type": "assistant", "total_cost_usd": 1.0}) is None


def test_cac_goi_codex():
    def a(*khoi):
        return {"type": "assistant", "parent_tool_use_id": "toolu_cha", "message": {"id": "m", "content": list(khoi)}}
    sk = a({"type": "tool_use", "id": "t1", "name": "Agent", "input": {"subagent_type": "codex:codex-rescue"}},
           {"type": "tool_use", "id": "t2", "name": "Skill", "input": {"skill": "codex:rescue", "args": "x"}},
           {"type": "tool_use", "id": "t3", "name": "Task", "input": {"subagent_type": "Codex-rescue"}},
           {"type": "tool_use", "id": "t4", "name": "Agent", "input": {"subagent_type": "general-purpose",
                                                                        "prompt": "gọi codex:rescue"}},
           {"type": "tool_use", "id": "t5", "name": "Skill", "input": {"skill": "codexlike"}},
           {"type": "tool_use", "id": "t6", "name": "Bash", "input": {"command": "codex exec"}},
           {"type": "text", "text": "subagent_type codex:rescue"})
    # FX-28 (R-22 P2-3): Bash gọi codex cũng tính; trong subagent (parent_tool_use_id) Bash codex-companion dùng id cha
    assert sj.cac_goi_codex(sk) == ["t1", "t2", "t3", "t6"]
    assert sj.cac_goi_codex(a({"type": "tool_use", "name": "Skill", "input": {"skill": "codex:x"}})) == [None]
    assert sj.cac_goi_codex({"type": "user", "message": {"content": [
        {"type": "tool_use", "id": "t1", "name": "Agent", "input": {"subagent_type": "codex"}}]}}) == []


def _bash(lenh, id_="b1", cha=None, **them):
    return {"type": "assistant", "parent_tool_use_id": cha,
            "message": {"id": "m", "content": [{"type": "tool_use", "id": id_, "name": "Bash",
                                                "input": {"command": lenh, **them}}]}}


@pytest.mark.parametrize("lenh", [
    "codex exec \"chấm kịch bản\"",
    "CODEX exec --full-auto x",
    "cd /e/du-an && codex exec -m gpt-5 'x'",
    "status=1; codex",
    "\"C:\\\\Users\\\\Mi\\\\bin\\\\codex.exe\" exec x",
    "& 'C:/tools/codex.cmd' exec x",
    "npx @openai/codex exec x",
    "node \"C:/Users/Mi/.claude/plugins/cache/openai-codex/codex/1.0.6/scripts/codex-companion.mjs\" task --write x",
    "node ${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs review",
    "node x/codex-companion.mjs adversarial-review \"$ARGUMENTS\"",
    "node x/codex-companion.mjs",                                  # thiếu lệnh con → tính (hướng an toàn)
    "node x/codex-companion.mjs status && node x/codex-companion.mjs task y",
    "node x/codex-companion.mjs status; codex exec y",
    "python run_codex.py --ma ud1",                                 # script tên có codex
    "node C:/x/codex-cli.js exec",
    "echo codex",                                                   # mơ hồ → tính là gọi Codex (hướng an toàn)
    "grep -n codex file.txt",
])
def test_cac_goi_codex_bash_tinh(lenh):
    assert sj.cac_goi_codex(_bash(lenh)) == ["b1"], lenh


@pytest.mark.parametrize("lenh", [
    "python c2_kiem.py --project P --batch 20261117-cq01 --codex --ghi-soat",
    "cat kich-ban/20261117-cq01_codex-review.md",
    "python tao_voice.py --batch 20261117-cq01",
    "ls C:/Users/Mi/.claude/plugins/cache/openai-codex/codex/1.0.6",
    "node x/codex-companion.mjs status --json",
    "node x/codex-companion.mjs result abc",
    "node x/codex-companion.mjs cancel abc",
    "node \"x/codex-companion.mjs\" task-resume-candidate --json",
    "node x/codex-companion.mjs setup --json",
    "echo xong",
])
def test_cac_goi_codex_bash_khong_tinh(lenh):
    assert sj.cac_goi_codex(_bash(lenh)) == [], lenh


def test_cac_goi_codex_bash_trong_subagent_codex_khong_dem_doi():
    # agent codex-rescue (id A1) gọi đúng 1 Bash codex-companion task: cùng id A1 → bên gọi khử trùng, đếm 1 lần
    assert sj.cac_goi_codex(_bash("node x/codex-companion.mjs task --write y", "b9", cha="A1")) == ["A1"]
    # codex exec trong subagent: id riêng (không gộp vào cha — subagent thường gọi nhiều lần vẫn bị đếm đủ)
    assert sj.cac_goi_codex(_bash("codex exec y", "b8", cha="A2")) == ["b8"]
    # run_in_background không đổi cách đếm
    assert sj.cac_goi_codex(_bash("codex exec y", "b7", run_in_background=True)) == ["b7"]
    # command sai dạng → không tính, không ném
    for x in (None, 3, ["codex"], ""):
        assert sj.cac_goi_codex(_bash(x)) == []
