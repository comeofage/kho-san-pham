"""Test theo dõi phiên sống (§7.3, phiếu B-5) — chạy: python -B -m pytest tools/test_runner_theo_doi_phien.py -q

Fixture dựng theo TÊN TRƯỜNG thật ở `.culiapp/test-spike-s3.json` `lan_goi[0].loai_su_kien_va_truong`
(giá trị giả): system/init{session_id, tools, claude_code_version…}, assistant{message, parent_tool_use_id…},
system/task_started{task_id, tool_use_id, task_type…}, system/task_notification{task_id, status…},
system/task_updated{task_id, patch}, result/success{is_error, result, total_cost_usd…} (result KHÔNG có
parent_tool_use_id).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from runner.theo_doi_phien import TheoDoiPhien, TinhTrang  # noqa: E402

SID = "79dc1e4d-0000-4b13-b601-000000000000"
IM = 10.0


def init(ver: str = "2.1.169", sid: str = SID) -> dict:
    return {"type": "system", "subtype": "init", "session_id": sid, "tools": ["Task", "Bash", "TaskOutput", "TaskStop"],
            "claude_code_version": ver, "permissionMode": "dontAsk", "model": "m", "apiKeySource": "none",
            "agents": [], "mcp_servers": [], "uuid": "u"}


def asst(mid: str | None, *khoi, cha: str | None = None) -> dict:
    msg = {"role": "assistant", "content": list(khoi) or [{"type": "text", "text": "đang làm"}]}
    if mid is not None:
        msg["id"] = mid
    return {"type": "assistant", "message": msg, "parent_tool_use_id": cha, "session_id": SID, "uuid": "u"}


def user_kq(cha: str | None = None) -> dict:
    return {"type": "user", "parent_tool_use_id": cha, "session_id": SID, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}]}}


def result(text: str = "TRẠNG THÁI: DONE\nxong", tong: float | None = 0.1, *, loi: bool = False,
           subtype: str = "success", **them) -> dict:
    sk = {"type": "result", "subtype": subtype, "is_error": loi, "result": text, "num_turns": 1,
          "duration_ms": 10, "session_id": SID, "permission_denials": [], "uuid": "u", **them}
    if tong is not None:
        sk["total_cost_usd"] = tong
    return sk


def bat_dau(tid: str) -> dict:
    return {"type": "system", "subtype": "task_started", "task_id": tid, "tool_use_id": "toolu_n",
            "description": "d", "prompt": "p", "task_type": "local_bash", "session_id": SID, "uuid": "u"}


def thong_bao(tid: str, status: str = "completed") -> dict:
    return {"type": "system", "subtype": "task_notification", "task_id": tid, "status": status,
            "output_file": "x", "summary": "s", "tool_use_id": "toolu_n", "session_id": SID, "uuid": "u"}


def cap_nhat(tid: str, patch) -> dict:
    return {"type": "system", "subtype": "task_updated", "task_id": tid, "patch": patch, "session_id": SID, "uuid": "u"}


def nap_het(td: TheoDoiPhien, ds: list[dict], t0: float = 100.0, buoc: float = 1.0) -> float:
    """Nạp lần lượt, mỗi sự kiện cách nhau `buoc` giây; trả lúc của sự kiện cuối."""
    t = t0
    for i, sk in enumerate(ds):
        t = t0 + i * buoc
        td.nap(sk, t)
    return t


# ---------------- kết luận lượt ----------------

def test_chua_co_su_kien_la_dang_lam():
    tt = TheoDoiPhien(5).tinh_trang(1000.0, IM)
    assert tt == TinhTrang("dang_lam", None, "", 0, 0)


def test_result_cap_cao_im_lang_10s_ket_luot_9s_dang_lam():
    td = TheoDoiPhien(5)
    t = nap_het(td, [init(), asst("m1"), result()])
    assert td.tinh_trang(t + 9.0, IM).loai == "dang_lam"
    assert td.tinh_trang(t + 9.999, IM).loai == "dang_lam"
    tt = td.tinh_trang(t + 10.0, IM)
    assert tt.loai == "ket_luot" and tt.so_ket_luot == 1 and tt.so_viec_nen == 0
    assert tt.ket_qua is not None and tt.ket_qua.trang_thai == "DONE"
    assert tt.van_ban == "TRẠNG THÁI: DONE\nxong"


def test_result_cua_subagent_khong_ket_luan_luot():
    td = TheoDoiPhien(5)
    t = nap_het(td, [init(), asst("m1"), asst("m2", cha="toolu_cha"),
                     result("TRẠNG THÁI: DONE", 0.5, parent_tool_use_id="toolu_cha")])
    tt = td.tinh_trang(t + 60, IM)
    assert tt.loai == "dang_lam" and tt.so_ket_luot == 0 and tt.ket_qua is None
    assert td.chi_phi_usd == 0.0                     # chi phí chỉ lấy từ result cấp cao


def test_hoat_dong_cap_cao_sau_result_ve_dang_lam_roi_ket_luot_moi():
    td = TheoDoiPhien(5)
    t = nap_het(td, [init(), asst("m1"), result("vòng 1", 0.1)])
    assert td.tinh_trang(t + 20, IM).so_ket_luot == 1
    td.nap(asst("m2"), t + 30)                       # agent tự thức
    assert td.tinh_trang(t + 100, IM).loai == "dang_lam"   # im lặng lâu nhưng chưa có result mới
    td.nap(user_kq(), t + 31)
    assert td.tinh_trang(t + 100, IM).loai == "dang_lam"
    td.nap(result("TRẠNG THÁI: BLOCKED\nkẹt", 0.2), t + 32)
    tt = td.tinh_trang(t + 42, IM)
    assert tt.loai == "ket_luot" and tt.so_ket_luot == 2 and tt.ket_qua.trang_thai == "BLOCKED"


def test_su_kien_subagent_sau_result_chi_lui_dong_ho_im_lang():
    """Việc nền là subagent chạy sau result chính: sự kiện của nó KHÔNG huỷ kết luận, chỉ đặt lại đồng hồ."""
    td = TheoDoiPhien(5)
    t = nap_het(td, [init(), bat_dau("a1"), result("đã giao việc nền", 0.1)])
    td.nap(asst("s1", cha="toolu_cha"), t + 20)
    assert td.tinh_trang(t + 25, IM).loai == "dang_lam"         # mới 5 s im lặng
    tt = td.tinh_trang(t + 30, IM)
    assert tt.loai == "ket_luot" and tt.so_ket_luot == 1 and tt.so_viec_nen == 1
    assert tt.ket_qua.trang_thai == "KHONG_RO"


def test_thong_bao_nen_sau_result_khong_thuc_day_van_ket_luot_cu():
    """Đúng chuỗi S-3: result → (im) → task_notification → task_updated → (agent có thể tự thức hoặc không)."""
    td = TheoDoiPhien(5)
    t = nap_het(td, [init(), bat_dau("byftlkkuc"), result("giao nền", 0.11)])
    assert td.tinh_trang(t + 15, IM).so_viec_nen == 1
    td.nap(thong_bao("byftlkkuc"), t + 60)
    td.nap(cap_nhat("byftlkkuc", {"status": "completed"}), t + 60.1)
    assert td.tinh_trang(t + 65, IM).loai == "dang_lam"
    tt = td.tinh_trang(t + 70.1, IM)
    assert tt.loai == "ket_luot" and tt.so_ket_luot == 1 and tt.so_viec_nen == 0


def test_loi_luot_is_error_va_subtype_error():
    td = TheoDoiPhien(5)
    t = nap_het(td, [init(), result("Prompt is too long", 0.1, loi=True)])
    tt = td.tinh_trang(t + IM, IM)
    assert tt.loai == "loi_luot" and tt.ket_qua is None and "Prompt is too long" in tt.van_ban
    assert tt.so_ket_luot == 1
    assert td.tinh_trang(t + 1, IM).loai == "dang_lam"          # vẫn phải chờ im lặng

    td2 = TheoDoiPhien(5)
    t = nap_het(td2, [init(), result("", 0.1, subtype="error_max_turns")])
    tt = td2.tinh_trang(t + IM, IM)
    assert tt.loai == "loi_luot" and "error_max_turns" in tt.van_ban


# ---------------- CẦN_USER ----------------

KHOI_CAU_HOI = "Đã xong bước giá.\nCẦN_USER: Giá deal hiện là bao nhiêu?\nLOẠI: cau_hoi\n"


def test_can_user_cau_hoi_dot5():
    td = TheoDoiPhien(5)
    t = nap_het(td, [init(), result(KHOI_CAU_HOI, 0.1)])
    kq = td.tinh_trang(t + IM, IM).ket_qua
    assert kq.trang_thai == "CAN_USER" and kq.cau_hoi.loai == "cau_hoi"
    assert kq.cau_hoi.noi_dung == "Giá deal hiện là bao nhiêu?"


def test_can_user_cau_hoi_dot4_ve_viec_tay():
    td = TheoDoiPhien(4)
    t = nap_het(td, [init(), result(KHOI_CAU_HOI, 0.1)])
    assert td.tinh_trang(t + IM, IM).ket_qua.cau_hoi.loai == "viec_tay"


def test_can_user_chi_doc_tu_result_khong_doc_van_ban_assistant():
    td = TheoDoiPhien(5)
    t = nap_het(td, [init(), asst("m1", {"type": "text", "text": KHOI_CAU_HOI}), result("TRẠNG THÁI: DONE", 0.1)])
    assert td.tinh_trang(t + IM, IM).ket_qua.trang_thai == "DONE"


def test_che_ap_len_van_ban_va_ket_qua():
    khoa = "Qz7v" * 8
    td = TheoDoiPhien(5, che=lambda s: s.replace(khoa, "***"))
    t = nap_het(td, [init(), result(f"TRẠNG THÁI: DONE\nkhoá {khoa}", 0.1)])
    tt = td.tinh_trang(t + IM, IM)
    assert khoa not in tt.van_ban and "***" in tt.van_ban
    assert khoa not in tt.ket_qua.tom_tat


# ---------------- việc nền ----------------

def test_task_started_roi_notification_cung_id_tap_rong():
    td = TheoDoiPhien(5)
    td.nap(bat_dau("t1"), 1)
    td.nap(bat_dau("t2"), 2)
    assert td.viec_nen_mo == frozenset({"t1", "t2"})
    td.nap(thong_bao("t1", "failed"), 3)
    assert td.viec_nen_mo == frozenset({"t2"})
    td.nap(thong_bao("t2"), 4)
    assert td.viec_nen_mo == frozenset()


def test_task_updated_completed_dong_running_khong():
    td = TheoDoiPhien(5)
    td.nap(bat_dau("t1"), 1)
    td.nap(cap_nhat("t1", {"status": "running"}), 2)
    assert td.viec_nen_mo == frozenset({"t1"})
    td.nap(cap_nhat("t1", {"status": "completed"}), 3)
    assert td.viec_nen_mo == frozenset()
    td.nap(thong_bao("t1"), 4)                       # thông báo đến sau cập nhật: không lỗi
    assert td.viec_nen_mo == frozenset()


def test_ket_thuc_den_truoc_bat_dau_khong_mo_lai():
    td = TheoDoiPhien(5)
    td.nap(thong_bao("t1"), 1)
    td.nap(bat_dau("t1"), 2)
    assert td.viec_nen_mo == frozenset()


def test_viec_nen_cua_subagent_cung_tinh():
    td = TheoDoiPhien(5)
    td.nap({**bat_dau("t9"), "parent_tool_use_id": "toolu_cha"}, 1)
    assert td.viec_nen_mo == frozenset({"t9"})


def test_viec_nen_mo_la_frozenset_ban_sao():
    td = TheoDoiPhien(5)
    td.nap(bat_dau("t1"), 1)
    v = td.viec_nen_mo
    assert isinstance(v, frozenset)
    td.nap(thong_bao("t1"), 2)
    assert v == frozenset({"t1"})


# ---------------- chi phí chênh lệch ----------------

def test_chi_phi_chenh_lech_va_dem_lai():
    td = TheoDoiPhien(5)
    d1 = td.nap(result("a", 0.10), 1)
    d2 = td.nap(result("b", 0.30), 2)
    d3 = td.nap(result("c", 0.25), 3)                # tổng giảm → phiên đếm lại
    assert d1 == pytest.approx(0.10) and d2 == pytest.approx(0.20) and d3 == pytest.approx(0.25)
    assert td.chi_phi_usd == pytest.approx(0.10 + 0.20 + 0.25)


def test_chi_phi_cac_su_kien_khac_bang_0_va_thieu_truong_khong_doi_moc():
    td = TheoDoiPhien(5)
    assert td.nap(init(), 1) == 0.0 and td.nap(asst("m"), 2) == 0.0
    assert td.nap(result("a", 0.30), 3) == pytest.approx(0.30)
    assert td.nap(result("b", None), 4) == 0.0       # thiếu total_cost_usd: không coi là đếm lại
    assert td.nap(result("c", "1.0"), 5) == 0.0      # sai dạng
    assert td.nap(result("d", float("nan")), 6) == 0.0
    assert td.nap(result("e", 0.35), 7) == pytest.approx(0.05)
    assert td.chi_phi_usd == pytest.approx(0.35)


def test_chi_phi_result_loi_van_tinh():
    td = TheoDoiPhien(5)
    assert td.nap(result("x", 0.2, loi=True), 1) == pytest.approx(0.2)


def test_chi_phi_so_lieu_that_s3():
    """Bốn total_cost_usd của S-3 (cộng dồn) → tổng chênh lệch = số cuối."""
    td = TheoDoiPhien(5)
    for i, v in enumerate([0.1187635, 0.12641275, 0.172612, 0.18194475]):
        assert td.nap(result("x", v), i) >= 0
    assert td.chi_phi_usd == pytest.approx(0.18194475)


# ---------------- init, lượt, Codex, sự kiện lạ ----------------

def test_init_lay_session_va_phien_ban_moi_nhat():
    td = TheoDoiPhien(5)
    assert td.session_id is None and td.phien_ban is None
    td.nap(init("2.1.169"), 1)
    assert td.session_id == SID and td.phien_ban == "2.1.169"
    td.nap(init("2.1.170"), 2)                       # S-3: mỗi lượt một init
    assert td.phien_ban == "2.1.170"


def test_so_luot_khu_trung_message_id_moi_cap():
    td = TheoDoiPhien(5)
    for i, sk in enumerate([asst("m1"), asst("m1"), asst("m2", cha="toolu_cha"), asst("m2", cha="toolu_cha"),
                            asst("m3"), asst(None), asst(None)]):
        td.nap(sk, i)
    assert td.so_luot == 5                           # m1, m2, m3 + 2 message không id (đếm từng cái)


def test_so_codex_moi_cap_khu_trung_tool_use_id():
    td = TheoDoiPhien(5)
    goi = {"type": "tool_use", "id": "tu_c1", "name": "Agent", "input": {"subagent_type": "codex:codex-rescue"}}
    skill = {"type": "tool_use", "id": "tu_c2", "name": "Skill", "input": {"skill": "codex:rescue"}}
    td.nap(asst("m1", goi), 1)
    td.nap(asst("m1", goi), 2)                       # cùng khối phát lại
    td.nap(asst("m2", skill, cha="toolu_cha"), 3)
    td.nap(asst("m3", {"type": "text", "text": "Agent subagent_type codex:rescue"}), 4)
    assert td.so_codex == 2


def test_luc_su_kien_cuoi_moi_su_kien():
    td = TheoDoiPhien(5)
    td.nap({"type": "rate_limit_event", "rate_limit_info": {}}, 42.0)
    assert td.luc_su_kien_cuoi == 42.0


def test_su_kien_khong_phai_dict_bo_qua():
    td = TheoDoiPhien(5)
    for x in (None, "chuỗi", 5, [1]):
        assert td.nap(x, 1.0) == 0.0
    assert td.luc_su_kien_cuoi == 0.0 and td.so_luot == 0 and td.tinh_trang(99.0, IM).loai == "dang_lam"


def test_su_kien_khong_ro_sau_result_khong_huy_ket_luot():
    """rate_limit_event / hook / thinking_tokens / init sau result: không phải hoạt động của agent."""
    td = TheoDoiPhien(5)
    t = nap_het(td, [init(), result("TRẠNG THÁI: DONE", 0.1)])
    td.nap({"type": "rate_limit_event", "rate_limit_info": {}}, t + 1)
    td.nap({"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 3}, t + 2)
    td.nap(init(), t + 3)
    assert td.tinh_trang(t + 13, IM).loai == "ket_luot"
