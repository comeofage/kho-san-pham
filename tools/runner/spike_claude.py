"""Spike S-1: đo hành vi claude.exe headless cho bộ chạy việc (docs/bo-chay-viec.md §6, §13 S-1).

Chỉ dùng thư viện chuẩn. Mặc định (không cờ) chỉ in trợ giúp. `--chay` mới gọi
claude.exe THẬT (tốn quota, tạo phiên trong C:\\Users\\Mi\\.claude\\projects\\).
Kết quả: MỘT JSON trên stdout; tiến độ/hướng dẫn quan sát in ra stderr.
Mọi chuỗi trong JSON đi qua bộ che bí mật theo GIÁ TRỊ (settings.json env,
biến môi trường tên khớp token|key|secret|pass|ANTHROPIC) và theo MẪU (§4.7).
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

PHIEN_BAN = 1

CLAUDE_EXE_MAC_DINH = r"C:\Users\Mi\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe"
SETTINGS_NGUOI_DUNG = Path(r"C:\Users\Mi\.claude\settings.json")
THU_MUC_PROJECTS = Path(r"C:\Users\Mi\.claude\projects")

# §4.7 môi trường tối thiểu
BIEN_MOI_TRUONG_CHEP = [
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "USERPROFILE",
    "USERNAME", "USERDOMAIN", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA",
    "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "TEMP", "TMP", "COMPUTERNAME",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
]

# §6.1
CONG_CU_CAM_CHUNG = [
    "AskUserQuestion", "Bash(git push*)", "Bash(*wrangler*)", "Bash(*deploy_cloudflare*)",
    "Bash(*gui_telegram*)", "Bash(pip *)", "Bash(*--gui-lai-ma*)", "Bash(*kho-runner*)",
    "Edit(//E:/kho-runner/**)",
    "Write(//E:/kho-runner/**)",
    "Read(//E:/kho-runner/**)",
]

TEN_AGENT = "thu-runner"
DAU_AGENT = "THU-RUNNER-OK"
TU_KHOA_NHO = "CHIM-SE-42"
CAU_TIENG_VIET = "Tiếng Việt: Đường đi ổn định, nghiêng ngả ữ ỹ"
RE_CAN_USER = re.compile(r"^CẦN_USER:\s*(.+)$", re.M)
RE_HET_QUOTA = re.compile(r"(?i)usage limit|rate limit|\b429\b|overloaded")
RE_LOI_DANG_NHAP = re.compile(r"(?i)invalid api key|not logged in|please run /login|authentication|unauthorized|\b401\b|\b403\b")

HET_GIO_MOI_LAN_S = 240
NGU_NEN_S = 120  # tiến trình Bash nền ngủ bao lâu (mục 11)

# Windows
CREATE_NEW_CONSOLE = 0x00000010
CREATE_NEW_PROCESS_GROUP = 0x00000200
STARTF_USESHOWWINDOW = 0x00000001
SW_HIDE = 0

MO_TA_MUC = {
    "1_truong_su_kien": "init/result có đủ trường giả định §6.2 (session_id, total_cost_usd, num_turns, is_error, result, permission_denials)",
    "2_dontAsk_ghi_de_bypass": "--permission-mode dontAsk + --allowedTools Read: Write bị từ chối, file không được tạo (nếu không: thử --settings tối thiểu)",
    "3_tools_gioi_han": "--tools Read,Glob: Bash không có trong danh sách tools của init",
    "4_disallowed_sao_dau": "--disallowedTools \"Bash(*echo*)\" chặn được lệnh echo",
    "5_chi_phi_qua_proxy": "total_cost_usd > 0 khi đi qua cấu hình ANTHROPIC_BASE_URL hiện tại",
    "6_max_budget": "--max-budget-usd 0.01 có dừng lượt",
    "7_resume_nho_ngu_canh": "khối CẦN_USER ở lượt 1 -> --resume + stdin -> lượt 2 nhớ ngữ cảnh lượt 1",
    "8_dang_nhap_env_toi_thieu": "đăng nhập chạy được với env tối thiểu §4.7",
    "9_nhay_cua_so": "có nháy cửa sổ console khi agent gọi Bash python -c \"print(1)\" (người quan sát ghi nhận)",
    "10_thoi_gian_khoi_dong": "thời gian từ lúc sinh tiến trình tới sự kiện init / kết quả",
    "11_p_thoat_khi_con_bash_nen": "-p có thoát khi agent còn Bash chạy nền (run_in_background) không; tiến trình nền còn sống không",
    "12_stdin_cung_agent": "prompt qua stdin UTF-8 cùng --agents/--agent: agent nội tuyến có hiệu lực, tiếng Việt nguyên vẹn",
}


# ---------------------------------------------------------------- che bí mật

MAU_BI_MAT = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(ghp_|github_pat_)[A-Za-z0-9_]{10,}"),
    re.compile(r"\d{8,10}:[A-Za-z0-9_-]{30,}"),
]
RE_TEN_BI_MAT = re.compile(r"(?i)token|key|secret|pass|anthropic")


class LoiDocSettings(RuntimeError):
    """settings.json có mà không đọc/giải được -> không che được bí mật, phải dừng."""


def _doc_settings() -> dict:
    """Đọc settings.json người dùng (utf-8-sig: chịu BOM do Notepad ghi).

    Không có file -> {} (không có bí mật nào trong đó để che). Có file mà đọc,
    giải mã hay parse lỗi, hoặc gốc không phải object -> ``LoiDocSettings``
    (không im lặng tắt bộ che bí mật).
    """
    try:
        du_lieu = json.loads(SETTINGS_NGUOI_DUNG.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise LoiDocSettings(f"không đọc được {SETTINGS_NGUOI_DUNG}: {type(e).__name__}: {e}") from e
    if not isinstance(du_lieu, dict):
        raise LoiDocSettings(f"{SETTINGS_NGUOI_DUNG} không phải JSON object (gốc là {type(du_lieu).__name__})")
    return du_lieu


def _gia_tri_chuoi(x) -> list[str]:
    if isinstance(x, str):
        return [x]
    if isinstance(x, dict):
        return [s for v in x.values() for s in _gia_tri_chuoi(v)]
    if isinstance(x, list):
        return [s for v in x for s in _gia_tri_chuoi(v)]
    return []


def dung_bo_che(settings: dict):
    gia_tri: set[str] = set()
    env_st = settings.get("env") if isinstance(settings.get("env"), dict) else {}
    gia_tri.update(_gia_tri_chuoi(env_st))
    for ten, v in os.environ.items():
        if RE_TEN_BI_MAT.search(ten):
            gia_tri.add(v)
    ds = sorted((g for g in gia_tri if len(g) >= 12), key=len, reverse=True)

    def che(s: str) -> str:
        for g in ds:
            if g in s:
                s = s.replace(g, "***")
        for m in MAU_BI_MAT:
            s = m.sub("***", s)
        return s

    return che


def che_de_quy(x, che):
    if isinstance(x, str):
        return che(x)
    if isinstance(x, dict):
        return {che(str(k)): che_de_quy(v, che) for k, v in x.items()}
    if isinstance(x, list):
        return [che_de_quy(v, che) for v in x]
    return x


# ---------------------------------------------------------------- tiến trình

def env_toi_thieu() -> dict[str, str]:
    env = {k: os.environ[k] for k in BIEN_MOI_TRUONG_CHEP if k in os.environ}
    # os.environ trên Windows không phân biệt hoa thường; chép thêm theo tên gốc nếu thiếu
    for k, v in os.environ.items():
        if k.upper() in BIEN_MOI_TRUONG_CHEP and k.upper() not in {x.upper() for x in env}:
            env[k] = v
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def giet_cay(pid: int) -> str:
    try:
        r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                           timeout=30, encoding="utf-8", errors="replace")
        return f"taskkill rc={r.returncode}"
    except Exception as e:  # noqa: BLE001
        return f"taskkill loi: {type(e).__name__}"


def con_song(pid: int) -> bool | None:
    if os.name != "nt":
        return None
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        ma = ctypes.c_ulong(0)
        if not k32.GetExitCodeProcess(h, ctypes.byref(ma)):
            return None
        return ma.value == 259  # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def chay_claude(ten: str, argv: list[str], cwd: Path, stdin_text: str, env: dict[str, str],
                thu_muc_log: Path, het_gio_s: int = HET_GIO_MOI_LAN_S) -> dict:
    """Chạy một lượt claude.exe, console ẩn, đọc stream-json theo dòng có mốc thời gian."""
    kw: dict = {}
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= STARTF_USESHOWWINDOW
        si.wShowWindow = SW_HIDE
        kw["startupinfo"] = si
        kw["creationflags"] = CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP
    dong: list[tuple[float, str]] = []
    loi_ra: list[str] = []
    t0 = time.monotonic()
    ket: dict = {"ten": ten, "argv": argv, "cwd": str(cwd)}
    p = None
    try:
        p = subprocess.Popen(argv, cwd=str(cwd), env=env, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
    except OSError as e:
        ket.update(khoi_chay_loi=f"{type(e).__name__}: {e}", ma_thoat=None, het_gio=False,
                   su_kien=[], thoi_gian_s=0.0)
        return ket

    def doc_out():
        for b in iter(p.stdout.readline, b""):
            dong.append((time.monotonic() - t0, b.decode("utf-8", errors="replace").rstrip("\r\n")))

    def doc_err():
        for b in iter(p.stderr.readline, b""):
            loi_ra.append(b.decode("utf-8", errors="replace").rstrip("\r\n"))

    th = [threading.Thread(target=doc_out, daemon=True), threading.Thread(target=doc_err, daemon=True)]
    for t in th:
        t.start()
    try:
        p.stdin.write(stdin_text.encode("utf-8"))
        p.stdin.close()
    except OSError as e:
        ket["stdin_loi"] = f"{type(e).__name__}"
    het_gio = False
    try:
        p.wait(timeout=het_gio_s)
    except subprocess.TimeoutExpired:
        het_gio = True
        ket["giet"] = giet_cay(p.pid)
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            ket["giet"] += "; van con song"
    t_thoat = time.monotonic() - t0
    for t in th:
        t.join(timeout=10)
    ket["ma_thoat"] = p.returncode
    ket["het_gio"] = het_gio
    ket["thoi_gian_s"] = round(t_thoat, 2)
    ket["stderr_cuoi"] = "\n".join(loi_ra)[-800:]
    su_kien = []
    khong_json = 0
    with open(thu_muc_log / f"{ten}.jsonl", "w", encoding="utf-8") as f:
        for t, s in dong:
            f.write(s + "\n")
            try:
                sk = json.loads(s)
            except ValueError:
                khong_json += 1
                continue
            if isinstance(sk, dict):
                sk["__t"] = round(t, 2)
                su_kien.append(sk)
    ket["so_dong_khong_json"] = khong_json
    ket["su_kien"] = su_kien
    return ket


# ---------------------------------------------------------------- phân tích sự kiện

def tom_tat(ket: dict) -> dict:
    """Rút gọn một lượt chạy: tên trường, mốc thời gian, kết quả. Không giữ sự kiện thô."""
    sk = ket.get("su_kien", [])
    init = next((e for e in sk if e.get("type") == "system" and e.get("subtype") == "init"), None)
    res = next((e for e in reversed(sk) if e.get("type") == "result"), None)
    loai: dict[str, list[str]] = {}
    for e in sk:
        k = f"{e.get('type')}/{e.get('subtype')}" if e.get("subtype") else str(e.get("type"))
        loai.setdefault(k, sorted(x for x in e.keys() if x != "__t"))
    tool_use, tool_err = [], 0
    for e in sk:
        msg = e.get("message") if isinstance(e.get("message"), dict) else {}
        for c in msg.get("content") or []:
            if not isinstance(c, dict):
                continue
            if e.get("type") == "assistant" and c.get("type") == "tool_use":
                inp = c.get("input") if isinstance(c.get("input"), dict) else {}
                tool_use.append({"ten": c.get("name"), "lenh": str(inp.get("command", inp.get("file_path", "")))[:200],
                                 "nen": inp.get("run_in_background")})
            if e.get("type") == "user" and c.get("type") == "tool_result" and c.get("is_error"):
                tool_err += 1
    tt = {
        "ten": ket["ten"],
        "argv": ket["argv"],
        "ma_thoat": ket.get("ma_thoat"),
        "het_gio": ket.get("het_gio"),
        "khoi_chay_loi": ket.get("khoi_chay_loi"),
        "thoi_gian_s": ket.get("thoi_gian_s"),
        "t_init_s": init.get("__t") if init else None,
        "t_assistant_dau_s": next((e["__t"] for e in sk if e.get("type") == "assistant"), None),
        "t_result_s": res.get("__t") if res else None,
        "so_su_kien": len(sk),
        "so_dong_khong_json": ket.get("so_dong_khong_json"),
        "loai_su_kien_va_truong": loai,
        "so_message_assistant": sum(1 for e in sk if e.get("type") == "assistant"),
        "tool_use": tool_use,
        "so_tool_result_loi": tool_err,
        "stderr_cuoi": ket.get("stderr_cuoi"),
    }
    if init:
        tt["init"] = {
            "session_id": init.get("session_id"),
            "tools": init.get("tools"),
            "permissionMode": init.get("permissionMode"),
            "model": init.get("model"),
            "apiKeySource": init.get("apiKeySource"),
            "claude_code_version": init.get("claude_code_version"),
            "agents": init.get("agents"),
            "so_mcp_servers": len(init.get("mcp_servers") or []),
            "so_slash_commands": len(init.get("slash_commands") or []),
        }
    if res:
        den = res.get("permission_denials")
        tt["result"] = {
            "subtype": res.get("subtype"),
            "is_error": res.get("is_error"),
            "session_id": res.get("session_id"),
            "total_cost_usd": res.get("total_cost_usd"),
            "num_turns": res.get("num_turns"),
            "duration_ms": res.get("duration_ms"),
            "co_truong_result": "result" in res,
            "co_truong_permission_denials": "permission_denials" in res,
            "permission_denials": [
                {"tool_name": d.get("tool_name"),
                 "input": str((d.get("tool_input") or {}).get("command", (d.get("tool_input") or {}).get("file_path", "")))[:200]}
                for d in (den or []) if isinstance(d, dict)
            ] if isinstance(den, list) else den,
            "result_dau": str(res.get("result") or "")[:1500],
        }
    return tt


def van_ban(tt: dict) -> str:
    return (tt.get("result") or {}).get("result_dau", "")


def chi_phi(tt: dict):
    return (tt.get("result") or {}).get("total_cost_usd")


def bi_tu_choi(tt: dict, ten_cong_cu: str) -> bool:
    den = (tt.get("result") or {}).get("permission_denials") or []
    return any(isinstance(d, dict) and d.get("tool_name") == ten_cong_cu for d in den)


# ---------------------------------------------------------------- dựng lệnh

def agents_json() -> str:
    return json.dumps({TEN_AGENT: {
        "description": "Agent thử cho spike bộ chạy việc; trả lời ngắn, làm đúng chỉ dẫn.",
        "prompt": (f"Bạn là {TEN_AGENT}, agent kiểm thử. Dòng ĐẦU TIÊN của mọi câu trả lời cuối cùng "
                   f"phải là đúng chuỗi {DAU_AGENT}. Làm đúng và chỉ đúng các bước được yêu cầu. "
                   "Nếu một công cụ bị từ chối hoặc không có, KHÔNG tìm cách khác, chỉ báo lại."),
    }}, ensure_ascii=False)


def dung_argv(exe: str, *, tools: list[str], allowed: list[str], disallowed: list[str],
              session_id: str | None = None, resume: str | None = None,
              budget: float | None = None, settings_file: Path | None = None,
              model: str | None = None) -> list[str]:
    a = [exe, "-p", "--agents", agents_json(), "--agent", TEN_AGENT,
         "--tools", ",".join(tools),
         "--permission-mode", "dontAsk"]
    if allowed:
        a += ["--allowedTools", *allowed]
    if disallowed:
        a += ["--disallowedTools", *disallowed]
    a += ["--output-format", "stream-json", "--verbose"]
    if budget is not None:
        a += ["--max-budget-usd", str(budget)]
    if settings_file is not None:
        a += ["--settings", str(settings_file)]
    if model:
        a += ["--model", model]
    a += ["--resume", resume] if resume else ["--session-id", session_id or str(uuid.uuid4())]
    return a


def rut_argv(argv: list[str]) -> list[str]:
    """Bản in ra JSON: thay JSON agent dài bằng nhãn."""
    return ["<agents-json>" if x.startswith("{") else x for x in argv]


# ---------------------------------------------------------------- các phép đo

def log(s: str) -> None:
    print(f"[spike] {s}", file=sys.stderr, flush=True)


def chay_spike(exe: str, giu_tam: bool, model: str | None, cho_quan_sat_s: int) -> dict:
    settings = _doc_settings()
    env_st = settings.get("env") if isinstance(settings.get("env"), dict) else {}
    quyen = settings.get("permissions") if isinstance(settings.get("permissions"), dict) else {}
    out: dict = {
        "phien_ban_script": PHIEN_BAN,
        "claude_exe": exe,
        "claude_exe_ton_tai": Path(exe).is_file(),
        "moi_truong": {
            "settings_ten_khoa_env": sorted(env_st.keys()),
            "settings_co_ANTHROPIC_BASE_URL": "ANTHROPIC_BASE_URL" in env_st,
            "settings_co_permissions_defaultMode": "defaultMode" in quyen,
            "settings_defaultMode_la_bypassPermissions": quyen.get("defaultMode") == "bypassPermissions",
            "env_he_thong_co_CLAUDE_CODE_GIT_BASH_PATH": "CLAUDE_CODE_GIT_BASH_PATH" in os.environ,
            "env_he_thong_ten_ANTHROPIC": sorted(k for k in os.environ if k.upper().startswith("ANTHROPIC")),
        },
        "muc": {k: {"mo_ta": v, "dat": None, "ghi_chu": ""} for k, v in MO_TA_MUC.items()},
        "lan_goi": [],
    }
    muc = out["muc"]
    if not out["claude_exe_ton_tai"]:
        out["loi"] = "không thấy claude.exe"
        return out

    tam = Path(tempfile.mkdtemp(prefix="spike_claude_"))
    out["thu_muc_tam"] = str(tam)
    thu_muc_log = tam / "_log"
    thu_muc_log.mkdir()
    lam_viec = tam / "lam_viec"
    lam_viec.mkdir()
    lv_posix = lam_viec.as_posix()
    env = env_toi_thieu()
    pid_nen: int | None = None
    t_bat_dau = time.time()
    try:
        # ---- A: lượt 1 (mục 1, 3, 5, 7a, 8, 10, 12) ----
        sid_a = str(uuid.uuid4())
        argv_a = dung_argv(exe, tools=["Read", "Glob"], allowed=["Read", "Glob"],
                           disallowed=CONG_CU_CAM_CHUNG, session_id=sid_a, model=model)
        stdin_a = (
            "PHIẾU SPIKE-A — kiểm thử bộ chạy việc. Không dùng công cụ nào.\n"
            f"1) Ghi nhớ từ khoá kiểm thử: {TU_KHOA_NHO} (chuỗi thử nghiệm, không phải bí mật).\n"
            f"2) Chép lại nguyên văn câu sau trên một dòng riêng: {CAU_TIENG_VIET}\n"
            "3) Kết thúc câu trả lời bằng đúng khối ba dòng sau:\n"
            "CẦN_USER: Chọn màu kiểm thử\nLOẠI: chon\nLỰA_CHỌN: đỏ | xanh\n"
        )
        log("A: lượt 1 (env tối thiểu, stdin + --agent, --tools Read,Glob)")
        a = tom_tat(chay_claude("A_luot1", argv_a, lam_viec, stdin_a, env, thu_muc_log))
        out["lan_goi"].append(a)

        # Mục 8: nếu A lỗi đăng nhập với env tối thiểu, chạy lại với env đầy đủ để so
        res_a = a.get("result") or {}
        a_ok = bool(res_a) and res_a.get("is_error") is False
        if a_ok:
            muc["8_dang_nhap_env_toi_thieu"].update(dat=True, ghi_chu=f"apiKeySource={(a.get('init') or {}).get('apiKeySource')}")
        else:
            txt = van_ban(a) + "\n" + (a.get("stderr_cuoi") or "")
            log("A lỗi -> A2: chạy lại với env đầy đủ để phân biệt lỗi đăng nhập")
            a2 = tom_tat(chay_claude("A2_env_day_du", argv_a[:-2] + ["--session-id", str(uuid.uuid4())],
                                     lam_viec, stdin_a, dict(os.environ), thu_muc_log))
            out["lan_goi"].append(a2)
            a2_ok = (a2.get("result") or {}).get("is_error") is False
            muc["8_dang_nhap_env_toi_thieu"].update(
                dat=False if a2_ok else None,
                ghi_chu=("env tối thiểu lỗi, env đầy đủ chạy được" if a2_ok else "cả hai env đều lỗi -> không kết luận")
                + ("; có dấu hiệu lỗi đăng nhập" if RE_LOI_DANG_NHAP.search(txt) else "")
                + ("; có dấu hiệu hết quota/quá tải" if RE_HET_QUOTA.search(txt) else ""))

        init_a = a.get("init") or {}
        can = ["session_id", "total_cost_usd", "num_turns", "is_error"]
        thieu = [k for k in can if res_a.get(k) is None] if res_a else can
        if not res_a.get("co_truong_result"):
            thieu.append("result")
        if not res_a.get("co_truong_permission_denials"):
            thieu.append("permission_denials")
        muc["1_truong_su_kien"].update(
            dat=bool(init_a.get("session_id")) and not thieu if res_a else (False if a.get("so_su_kien") else None),
            ghi_chu=f"init.session_id {'có' if init_a.get('session_id') else 'KHÔNG'}; result thiếu: {thieu}; "
                    f"init.session_id == --session-id: {init_a.get('session_id') == sid_a}; "
                    f"result.session_id == init: {res_a.get('session_id') == init_a.get('session_id')}")
        tools_a = init_a.get("tools")
        if isinstance(tools_a, list):
            muc["3_tools_gioi_han"].update(
                dat=("Bash" not in tools_a) and ("Read" in tools_a),
                ghi_chu=f"tools init: {tools_a}")
        else:
            muc["3_tools_gioi_han"]["ghi_chu"] = "init không có danh sách tools"
        cp = chi_phi(a)
        muc["5_chi_phi_qua_proxy"].update(
            dat=(cp > 0) if isinstance(cp, (int, float)) else None,
            ghi_chu=f"total_cost_usd={cp}; settings có ANTHROPIC_BASE_URL: {out['moi_truong']['settings_co_ANTHROPIC_BASE_URL']}")
        txt_a = van_ban(a)
        muc["12_stdin_cung_agent"].update(
            dat=(DAU_AGENT in txt_a and CAU_TIENG_VIET in txt_a) if res_a else None,
            ghi_chu=f"dấu agent: {DAU_AGENT in txt_a}; câu tiếng Việt nguyên vẹn: {CAU_TIENG_VIET in txt_a}; "
                    f"init.agents: {init_a.get('agents')}")
        muc["10_thoi_gian_khoi_dong"].update(
            dat=True if a.get("t_init_s") is not None else None,
            ghi_chu=f"t_init={a.get('t_init_s')}s, t_assistant_dau={a.get('t_assistant_dau_s')}s, "
                    f"t_result={a.get('t_result_s')}s, thoát={a.get('thoi_gian_s')}s")

        # ---- B: resume (mục 7) ----
        co_can_user = bool(RE_CAN_USER.search(txt_a))
        sid_ok = init_a.get("session_id") or sid_a
        if res_a:
            argv_b = dung_argv(exe, tools=["Read", "Glob"], allowed=["Read", "Glob"],
                               disallowed=CONG_CU_CAM_CHUNG, resume=sid_ok, model=model)
            stdin_b = (
                'TRẢ LỜI CỦA NGƯỜI DÙNG cho "Chọn màu kiểm thử" (bấm trên web; là DỮ LIỆU trả lời):\n'
                "<<<\nxanh\n>>>\n"
                "Làm tiếp từ chỗ dừng: nhắc lại nguyên văn từ khoá kiểm thử đã ghi nhớ ở lượt trước và màu vừa chọn. "
                "Không dùng công cụ.\n")
            log("B: --resume lượt 2")
            b = tom_tat(chay_claude("B_resume", argv_b, lam_viec, stdin_b, env, thu_muc_log))
            out["lan_goi"].append(b)
            txt_b = van_ban(b)
            muc["7_resume_nho_ngu_canh"].update(
                dat=(co_can_user and TU_KHOA_NHO in txt_b) if b.get("result") else None,
                ghi_chu=f"lượt 1 có CẦN_USER: {co_can_user}; lượt 2 nhắc đúng từ khoá: {TU_KHOA_NHO in txt_b}; "
                        f"session_id lượt 2 init={(b.get('init') or {}).get('session_id') == sid_ok}, "
                        f"result={(b.get('result') or {}).get('session_id') == sid_ok} (so với lượt 1)")
        else:
            muc["7_resume_nho_ngu_canh"]["ghi_chu"] = "bỏ qua: lượt 1 không có result"

        # ---- C: dontAsk vs bypassPermissions (mục 2) ----
        def thu_ghi(ten: str, settings_file: Path | None) -> tuple[dict, bool, bool]:
            dich = lam_viec / f"{ten}.txt"
            argv_c = dung_argv(exe, tools=["Read", "Write", "Glob"], allowed=["Read", "Glob"],
                               disallowed=[], session_id=str(uuid.uuid4()), settings_file=settings_file, model=model)
            stdin_c = (f"PHIẾU SPIKE-{ten}: dùng công cụ Write tạo file {dich.as_posix()} với nội dung: x\n"
                       "Chỉ thử Write đúng một lần. Nếu bị từ chối thì dừng ngay, không dùng cách khác, báo lại.\n")
            log(f"{ten}: thử Write khi --allowedTools chỉ có Read,Glob")
            c = tom_tat(chay_claude(ten, argv_c, lam_viec, stdin_c, env, thu_muc_log))
            out["lan_goi"].append(c)
            return c, dich.exists(), bi_tu_choi(c, "Write")

        c, tao_file, tu_choi = thu_ghi("C_dontAsk", None)
        if tao_file:
            muc["2_dontAsk_ghi_de_bypass"].update(dat=False, ghi_chu="file ĐÃ được tạo -> dontAsk KHÔNG ghi đè; thử --settings")
            st_file = tam / "settings_toi_thieu.json"
            st_file.write_text(json.dumps({"permissions": {"defaultMode": "dontAsk"}}), encoding="utf-8")
            c2, tao2, tu_choi2 = thu_ghi("C2_dontAsk_settings", st_file)
            muc["2_dontAsk_ghi_de_bypass"]["thu_lai_settings"] = {
                "dat": (not tao2) and tu_choi2 if c2.get("result") else None,
                "file_tao": tao2, "Write_bi_tu_choi": tu_choi2}
        else:
            muc["2_dontAsk_ghi_de_bypass"].update(
                dat=True if tu_choi else None,
                ghi_chu=f"file không tạo; permission_denials có Write: {tu_choi}"
                        + ("" if tu_choi else " -> có thể model tự không gọi Write, không kết luận"))
        muc["2_dontAsk_ghi_de_bypass"]["permissionMode_init"] = (c.get("init") or {}).get("permissionMode")

        # ---- D: disallowed "*" đầu (mục 4) + nháy cửa sổ (mục 9) ----
        dich_d = lam_viec / "d_echo.txt"
        argv_d = dung_argv(exe, tools=["Read", "Bash"], allowed=["Read", "Bash"],
                           disallowed=["Bash(*echo*)"], session_id=str(uuid.uuid4()), model=model)
        stdin_d = (
            "PHIẾU SPIKE-D, làm đúng hai bước, mỗi bước một lần gọi công cụ Bash:\n"
            'Bước 1: chạy đúng lệnh: python -c "print(1)"\n'
            f"Bước 2: chạy đúng lệnh: echo hi > {dich_d.as_posix()}\n"
            "Nếu bước nào bị từ chối thì KHÔNG thử lệnh khác thay thế; báo lại kết quả từng bước.\n")
        print("\n" + "=" * 70 + "\n[QUAN SÁT MỤC 9] Trong khoảng 1-2 phút tới, nhìn màn hình: có cửa sổ\n"
              "console (đen) nào nháy lên khi agent chạy python -c \"print(1)\" không?\n"
              "Ghi lại CÓ/KHÔNG khi dán JSON kết quả.\n" + "=" * 70, file=sys.stderr, flush=True)
        if cho_quan_sat_s > 0:
            time.sleep(cho_quan_sat_s)
        d = tom_tat(chay_claude("D_disallowed_quan_sat", argv_d, lam_viec, stdin_d, env, thu_muc_log))
        out["lan_goi"].append(d)
        echo_tu_choi = any(x.get("tool_name") == "Bash" and "echo" in x.get("input", "")
                           for x in ((d.get("result") or {}).get("permission_denials") or []) if isinstance(x, dict))
        muc["4_disallowed_sao_dau"].update(
            dat=(not dich_d.exists()) and echo_tu_choi if d.get("result") else None,
            ghi_chu=f"file echo tạo: {dich_d.exists()}; denial Bash chứa echo: {echo_tu_choi}")
        python_chay = any(t.get("ten") == "Bash" and "print(1)" in (t.get("lenh") or "") for t in d.get("tool_use", []))
        muc["9_nhay_cua_so"].update(dat="QUAN_SAT_TAY",
                                    ghi_chu=f"agent đã gọi Bash python -c: {python_chay}; người quan sát ghi CÓ/KHÔNG nháy")

        # ---- E: -p thoát khi còn Bash nền (mục 11) ----
        file_pid = lam_viec / "e_pid.txt"
        file_xong = lam_viec / "e_xong.txt"
        kb_nen = lam_viec / "e_nen.py"
        kb_nen.write_text(
            "import os, time\n"
            f"open(r'{file_pid}', 'w').write(str(os.getpid()))\n"
            f"time.sleep({NGU_NEN_S})\n"
            f"open(r'{file_xong}', 'w').write('xong')\n", encoding="utf-8")
        argv_e = dung_argv(exe, tools=["Read", "Bash"], allowed=["Read", "Bash"],
                           disallowed=[], session_id=str(uuid.uuid4()), model=model)
        stdin_e = (
            "PHIẾU SPIKE-E: gọi công cụ Bash ĐÚNG MỘT LẦN với tham số run_in_background=true để chạy lệnh:\n"
            f"python {kb_nen.as_posix()}\n"
            "Sau đó KHÔNG chờ, KHÔNG kiểm tra output, trả lời ngay một dòng: DA_CHAY_NEN.\n")
        log(f"E: Bash nền (tiến trình nền ngủ {NGU_NEN_S}s)")
        e = tom_tat(chay_claude("E_bash_nen", argv_e, lam_viec, stdin_e, env, thu_muc_log))
        out["lan_goi"].append(e)
        time.sleep(3)
        if file_pid.exists():
            try:
                pid_nen = int(file_pid.read_text(encoding="utf-8").strip())
            except ValueError:
                pid_nen = None
        song = con_song(pid_nen) if pid_nen else None
        goi_nen = any(t.get("ten") == "Bash" and t.get("nen") for t in e.get("tool_use", []))
        muc["11_p_thoat_khi_con_bash_nen"].update(
            dat=(not e.get("het_gio") and (e.get("thoi_gian_s") or 0) < NGU_NEN_S) if goi_nen and pid_nen else None,
            ghi_chu=f"agent gọi Bash nền: {goi_nen}; claude thoát sau {e.get('thoi_gian_s')}s (nền ngủ {NGU_NEN_S}s); "
                    f"hết giờ: {e.get('het_gio')}; tiến trình nền còn sống 3s sau khi claude thoát: {song}; "
                    f"nền đã chạy xong: {file_xong.exists()}")

        # ---- F: --max-budget-usd 0.01 (mục 6) ----
        for i in range(3):
            (lam_viec / f"f_{i}.txt").write_text(f"Tệp {i}: " + "dữ liệu thử " * 50, encoding="utf-8")
        argv_f = dung_argv(exe, tools=["Read", "Glob"], allowed=["Read", "Glob"], disallowed=[],
                           session_id=str(uuid.uuid4()), budget=0.01, model=model)
        stdin_f = ("PHIẾU SPIKE-F: dùng Glob tìm f_*.txt trong thư mục hiện tại, Read lần lượt TỪNG file "
                   "(mỗi file một lượt gọi), rồi tóm tắt mỗi file một câu.\n")
        log("F: --max-budget-usd 0.01")
        f = tom_tat(chay_claude("F_budget", argv_f, lam_viec, stdin_f, env, thu_muc_log))
        out["lan_goi"].append(f)
        rf = f.get("result") or {}
        sub = str(rf.get("subtype") or "")
        muc["6_max_budget"].update(
            dat=("budget" in sub.lower()) if rf else None,
            ghi_chu=f"subtype={sub}; is_error={rf.get('is_error')}; num_turns={rf.get('num_turns')}; "
                    f"total_cost_usd={rf.get('total_cost_usd')}"
                    + ("; chi phí báo 0 -> trần ngân sách có thể không bao giờ chạm" if rf.get("total_cost_usd") == 0 else ""))
    finally:
        if pid_nen and con_song(pid_nen):
            out["don_tien_trinh_nen"] = giet_cay(pid_nen)
        out["thoi_gian_tong_s"] = round(time.time() - t_bat_dau, 1)
        out["chi_phi_tong_usd"] = round(sum(x for x in (chi_phi(g) for g in out["lan_goi"])
                                            if isinstance(x, (int, float))), 4)
        for g in out["lan_goi"]:
            g["argv"] = rut_argv(g["argv"])
        # Thư mục phiên Claude sinh cho cwd tạm (chỉ liệt kê tên, không đọc nội dung)
        ma_cwd = re.sub(r"[^A-Za-z0-9]", "-", str(lam_viec))
        try:
            ds = [p for p in THU_MUC_PROJECTS.iterdir() if p.is_dir() and p.name.lower() == ma_cwd.lower()]
            out["thu_muc_phien"] = [{"duong_dan": str(p), "so_file_jsonl": len(list(p.glob("*.jsonl")))} for p in ds]
            if not ds:
                out["thu_muc_phien"] = f"không thấy thư mục khớp {ma_cwd} trong {THU_MUC_PROJECTS}"
        except OSError as ex:
            out["thu_muc_phien"] = f"không liệt kê được: {type(ex).__name__}"
        if giu_tam:
            out["giu_thu_muc_tam"] = True
        else:
            shutil.rmtree(tam, ignore_errors=True)
            out["giu_thu_muc_tam"] = False
            out["thu_muc_tam_con"] = tam.exists()
    return out


# ---------------------------------------------------------------- CLI

def _stdio_utf8() -> None:
    """stdout/stderr UTF-8 TRƯỚC parse_args: --help tiếng Việt qua pipe cp1252 không vỡ."""
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass  # luồng không phải TextIOWrapper (vd. StringIO trong test) -> để nguyên


def main(argv: list[str] | None = None) -> int:
    _stdio_utf8()
    ds_muc = "\n".join(f"  {k}: {v}" for k, v in MO_TA_MUC.items())
    ap = argparse.ArgumentParser(
        prog="spike_claude.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Spike S-1: đo hành vi claude.exe headless (-p, stream-json, dontAsk, --tools, --resume...)\n"
            "cho bộ chạy việc Kho sản phẩm. KHÔNG cờ = chỉ in trợ giúp, không gọi gì.\n\n"
            "Các mục đo (JSON in ra có dat = true | false | null(không kết luận) | QUAN_SAT_TAY):\n" + ds_muc),
        epilog=(
            "Tác động khi --chay: gọi claude.exe THẬT 6-8 lượt (A, B resume, C, [C2], D, E, F, [A2]),\n"
            "tốn quota; tạo 5-7 phiên trong C:\\Users\\Mi\\.claude\\projects\\<mã cwd tạm>\\;\n"
            "thư mục tạm %TEMP%\\spike_claude_* (xoá cuối lượt trừ khi --giu-tam).\n"
            "Hoàn tác: xoá thư mục phiên in trong khoá thu_muc_phien và thư mục tạm (nếu --giu-tam).\n"
            "Mục 9 cần người ngồi nhìn màn hình; script in hướng dẫn ra stderr và chờ trước bước D."),
    )
    ap.add_argument("--chay", action="store_true", help="chạy các phép đo bằng claude.exe thật (cần duyệt)")
    ap.add_argument("--claude-exe", default=os.environ.get("KHO_CLAUDE_EXE", CLAUDE_EXE_MAC_DINH),
                    help="đường dẫn claude.exe (mặc định §6.1, ghi đè bằng env KHO_CLAUDE_EXE)")
    ap.add_argument("--model", default=None, help="tuỳ chọn --model truyền cho claude (mặc định: không truyền)")
    ap.add_argument("--giu-tam", action="store_true", help="giữ thư mục tạm (có _log/*.jsonl thô) để soi lại")
    ap.add_argument("--cho-quan-sat", type=int, default=8,
                    help="số giây chờ sau khi in hướng dẫn quan sát mục 9 (mặc định 8)")
    ns = ap.parse_args(argv)
    if not ns.chay:
        ap.print_help()
        return 0
    try:
        settings = _doc_settings()
    except LoiDocSettings as e:
        print(f"[spike] DỪNG: {e}\n[spike] Không che được bí mật trong settings -> không chạy đo. "
              "Sửa settings.json rồi chạy lại.", file=sys.stderr, flush=True)
        return 3
    che = dung_bo_che(settings)
    out = chay_spike(ns.claude_exe, ns.giu_tam, ns.model, max(0, ns.cho_quan_sat))
    print(json.dumps(che_de_quy(out, che), ensure_ascii=False, indent=2))
    return 0 if out.get("claude_exe_ton_tai") else 2


if __name__ == "__main__":
    sys.exit(main())
