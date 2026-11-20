"""Spike S-1..S-4: đo hành vi claude.exe headless cho bộ chạy việc (docs/bo-chay-viec.md §6, §7, §13).

Kịch bản 'cu' (S-1, mặc định) chỉ dùng thư viện chuẩn; kịch bản 'nen' (S-2) dùng thêm psutil
nếu có (import lười, thiếu thì các mục đo tiến trình ghi null). Mặc định (không cờ) chỉ in trợ giúp. `--chay` mới gọi
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

PHIEN_BAN = 3

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
        _dong_goi(out, tam, lam_viec, giu_tam, t_bat_dau)
    return out


def _dong_goi(out: dict, tam: Path, lam_viec: Path, giu_tam: bool, t_bat_dau: float) -> None:
    """Phần cuối chung của mọi kịch bản: tổng thời gian/chi phí, rút argv, liệt kê phiên, dọn tạm."""
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


# ---------------------------------------------------------------- kịch bản nền (S-2)

TEN_AGENT_NEN = "thu-runner-nen"
CONG_CU_NEN = ["Agent", "SendMessage", "Bash"]  # --allowedTools đúng 3 công cụ này
# Tên thăm dò thêm vào --tools (KHÔNG vào --allowedTools): cái nào có thật sẽ hiện trong init.tools;
# agent gọi tới sẽ bị dontAsk từ chối và ghi vào permission_denials -> biết đợt 5 cần cho phép gì.
CONG_CU_THAM_DO = ["Task", "TaskOutput", "TaskStop", "BashOutput", "KillShell", "KillBash"]
NGU_NEN_S2 = 60
FILE_NEN_XONG = "nen_xong.txt"
LENH_NEN = ("python -c \"import time; time.sleep(%d); open('%s','w').write('x')\""
            % (NGU_NEN_S2, FILE_NEN_XONG))
DAU_CON_1 = "CON-S2-OK"
DAU_CON_2 = "CON-S2-LAI"
RE_ID_NEN = re.compile(r"(?i)\b(?:shell|bash|task|background)[ _-]*id\W{0,3}\s*([A-Za-z0-9_-]{4,})|with ID:\s*([A-Za-z0-9_-]{4,})")
RE_ID_AGENT = re.compile(r"(?i)agent[ _-]?id\W{0,3}\s*([A-Za-z0-9_-]{4,})")
# Dấu hiệu thông báo hoàn tất việc nền trong luồng sự kiện (không xuất hiện trong prompt của script)
RE_THONG_BAO_NEN = re.compile(r"(?i)task[-_]notification|background (?:command|task|shell)[^\"]{0,80}(?:completed|finished|exited)|exit code")

MO_TA_MUC_NEN = {
    "n1_p_thoat_truoc_viec_nen": "lượt 1 (-p) thoát TRƯỚC khi Bash nền ngủ xong 60s (true) hay chờ xong mới thoát (false)",
    "n2_nen_con_song_sau_p_thoat": "tiến trình Bash nền còn sống ~3s sau khi -p thoát (psutil, khớp cmdline chứa nen_xong.txt)",
    "n3_file_nen_xong_xuat_hien": "file nen_xong.txt có xuất hiện (chờ tới mốc gọi Bash nền + 60s + 20s)",
    "n4_luot2_nhan_thong_bao_nen": "lượt 2 (--resume) có nhận thông báo hoàn tất việc nền (sự kiện stream + agent tự khai)",
    "n5_sendmessage_subagent_cu": "SendMessage tới subagent của lượt 1 sau --resume có chạy (tool_use + tool_result không lỗi, không bị từ chối)",
    "n6_ten_cong_cu_init": "tên công cụ thật trong init.tools (Agent/Task? SendMessage? BashOutput/KillShell/TaskOutput/TaskStop?)",
    "n7_subagent_luot1": "lượt 1 gọi được subagent general-purpose và nhận đúng dấu CON-S2-OK",
    "n8_chi_phi": "total_cost_usd từng lượt và tổng",
}


def agents_json_nen() -> str:
    return json.dumps({TEN_AGENT_NEN: {
        "description": "Agent thử việc nền cho spike S-2; làm đúng chỉ dẫn, trả lời ngắn.",
        "prompt": (f"Bạn là {TEN_AGENT_NEN}, agent kiểm thử việc nền. Làm đúng và chỉ đúng các bước được yêu cầu. "
                   "Nếu một công cụ bị từ chối hoặc không có, KHÔNG tìm cách khác, chỉ báo lại."),
    }}, ensure_ascii=False)


def dung_argv_nen(exe: str, *, tools: list[str], session_id: str | None = None,
                  resume: str | None = None, model: str | None = None) -> list[str]:
    """argv kịch bản nen: --strict-mcp-config, dontAsk, --allowedTools đúng CONG_CU_NEN, cấm chung."""
    a = [exe, "-p", "--strict-mcp-config", "--agents", agents_json_nen(), "--agent", TEN_AGENT_NEN,
         "--tools", ",".join(tools),
         "--permission-mode", "dontAsk",
         "--allowedTools", *CONG_CU_NEN,
         "--disallowedTools", *CONG_CU_CAM_CHUNG,
         "--output-format", "stream-json", "--verbose"]
    if model:
        a += ["--model", model]
    a += ["--resume", resume] if resume else ["--session-id", session_id or str(uuid.uuid4())]
    return a


def _chu_trong(x) -> str:
    """Gom mọi chuỗi trong content tool_result (str hoặc list khối text) thành một chuỗi."""
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return "\n".join(_chu_trong(v) for v in x)
    if isinstance(x, dict):
        return _chu_trong(x.get("text") if "text" in x else x.get("content", ""))
    return ""


def cong_cu_chi_tiet(su_kien: list[dict]) -> list[dict]:
    """Ghép tool_use với tool_result theo id (cả của subagent: parent_tool_use_id). Hàm thuần."""
    ds: list[dict] = []
    theo_id: dict[str, dict] = {}
    for e in su_kien:
        msg = e.get("message") if isinstance(e.get("message"), dict) else {}
        for c in msg.get("content") or []:
            if not isinstance(c, dict):
                continue
            if e.get("type") == "assistant" and c.get("type") == "tool_use":
                inp = c.get("input") if isinstance(c.get("input"), dict) else {}
                m = {"id": c.get("id"), "ten": c.get("name"), "t_s": e.get("__t"),
                     "cha": e.get("parent_tool_use_id"),
                     "khoa_input": sorted(inp.keys()),
                     "input_dau": json.dumps(inp, ensure_ascii=False)[:300],
                     "nen": inp.get("run_in_background"),
                     "ket_qua_dau": None, "loi": None, "t_ket_qua_s": None}
                ds.append(m)
                if c.get("id"):
                    theo_id[c["id"]] = m
            elif e.get("type") == "user" and c.get("type") == "tool_result":
                m = theo_id.get(c.get("tool_use_id"))
                if m is not None:
                    m["ket_qua_dau"] = _chu_trong(c.get("content"))[:600]
                    m["loi"] = bool(c.get("is_error"))
                    m["t_ket_qua_s"] = e.get("__t")
    return ds


def tim_thong_bao_nen(su_kien: list[dict], bo_qua: list[str] | None = None) -> list[dict]:
    """Sự kiện có dấu hiệu thông báo hoàn tất việc nền (trừ tool_result của chính lệnh gọi). Hàm thuần."""
    bo = set(bo_qua or [])
    ra = []
    for e in su_kien:
        if e.get("type") == "assistant":
            continue  # lời agent tự khai đo riêng
        s = json.dumps({k: v for k, v in e.items() if k != "__t"}, ensure_ascii=False)
        if any(b and b in s for b in bo) and e.get("type") == "user" and '"tool_result"' in s:
            continue
        m = RE_THONG_BAO_NEN.search(s)
        if m:
            ra.append({"t_s": e.get("__t"), "loai": f"{e.get('type')}/{e.get('subtype')}",
                       "khop": m.group(0)[:120], "doan": s[max(0, m.start() - 150):m.end() + 150]})
    return ra


TEN_UNG_VIEN_NEN = re.compile(r"^(python\d*(\.\d+)*w?|py|bash|sh|cmd|pwsh|powershell)(\.exe)?$")


def _cmd_khop_nen(cmd: list[str] | None) -> bool:
    s = " ".join(cmd or [])
    return FILE_NEN_XONG in s and "sleep" in s


class TheoDoiNen:
    """Thread quét psutil mỗi giây, ghi lại các tiến trình có cmdline chứa lệnh nền."""

    def __init__(self, t0: float):
        self.t0 = t0
        self.thay: dict[int, dict] = {}
        self.loi: str | None = None
        self._dung = threading.Event()
        self._th = threading.Thread(target=self._chay, daemon=True)
        self.bo_qua: set[int] = set()
        try:
            import psutil  # noqa: F401
            self.psutil = psutil
            # Không tính chính script này và tổ tiên (cmdline người gọi có thể chứa chuỗi lệnh nền)
            self.bo_qua = {os.getpid()} | {p.pid for p in psutil.Process().parents()}
        except ImportError:
            self.psutil = None
            self.loi = "không import được psutil"

    def bat_dau(self) -> None:
        if self.psutil:
            self._th.start()

    def dung(self) -> None:
        self._dung.set()
        if self._th.is_alive():
            self._th.join(timeout=10)

    def quet(self) -> None:
        ps = self.psutil
        # Lọc theo tên trước (rẻ); chỉ đọc cmdline của ứng viên: đọc cmdline mọi tiến trình
        # trên Windows mất ~20s/lần quét (đã đo), làm hỏng mốc thời gian.
        for p in ps.process_iter(["pid", "name"]):
            try:
                pid, ten = p.info["pid"], (p.info.get("name") or "").lower()
                if pid in self.thay or pid in self.bo_qua or not TEN_UNG_VIEN_NEN.search(ten):
                    continue
                cmd = p.cmdline()
                if not _cmd_khop_nen(cmd):
                    continue
                self.thay[pid] = {
                    "pid": pid, "ppid": p.ppid(), "ten": ten, "create_time": p.create_time(),
                    "cmd_dau": " ".join(cmd)[:200],
                    "t_thay_s": round(time.monotonic() - self.t0, 1)}
            except (ps.NoSuchProcess, ps.AccessDenied, ps.ZombieProcess):
                continue

    def _chay(self) -> None:
        while not self._dung.is_set():
            try:
                self.quet()
            except Exception as e:  # noqa: BLE001
                self.loi = f"{type(e).__name__}: {e}"[:200]
            self._dung.wait(1.0)

    def con_song(self) -> list[int]:
        """PID đã thấy mà vẫn sống và đúng là tiến trình đó (create_time khớp, chống tái dùng PID)."""
        if not self.psutil:
            return []
        ps = self.psutil
        song = []
        for pid, tt in self.thay.items():
            try:
                p = ps.Process(pid)
                if abs(p.create_time() - tt["create_time"]) < 1 and p.status() != ps.STATUS_ZOMBIE:
                    song.append(pid)
            except (ps.NoSuchProcess, ps.AccessDenied):
                continue
        return song


def chay_spike_nen(exe: str, giu_tam: bool, model: str | None) -> dict:
    """S-2: việc nền (subagent + Bash nền) qua ranh giới -p và --resume."""
    out: dict = {
        "phien_ban_script": PHIEN_BAN,
        "kich_ban": "nen",
        "claude_exe": exe,
        "claude_exe_ton_tai": Path(exe).is_file(),
        "lenh_nen": LENH_NEN,
        "cong_cu_allowed": CONG_CU_NEN,
        "cong_cu_tham_do_trong_tools": CONG_CU_THAM_DO,
        "muc": {k: {"mo_ta": v, "dat": None, "ghi_chu": ""} for k, v in MO_TA_MUC_NEN.items()},
        "lan_goi": [],
    }
    muc = out["muc"]
    if not out["claude_exe_ton_tai"]:
        out["loi"] = "không thấy claude.exe"
        return out

    tam = Path(tempfile.mkdtemp(prefix="spike_claude_nen_"))
    out["thu_muc_tam"] = str(tam)
    thu_muc_log = tam / "_log"
    thu_muc_log.mkdir()
    lam_viec = tam / "lam_viec"
    lam_viec.mkdir()
    file_xong = lam_viec / FILE_NEN_XONG
    env = env_toi_thieu()
    t_bat_dau = time.time()
    t0 = time.monotonic()
    theo_doi = TheoDoiNen(t0)  # khởi tạo TRƯỚC try: finally luôn dùng được
    try:
        theo_doi.bat_dau()
        out["psutil"] = theo_doi.loi or "có"

        # ---- lượt 1: subagent + Bash nền, rồi kết thúc lượt ----
        sid = str(uuid.uuid4())
        stdin_1 = (
            "PHIẾU SPIKE-NEN lượt 1. Làm đúng hai việc sau, mỗi việc gọi công cụ ĐÚNG MỘT LẦN, rồi KẾT THÚC lượt ngay:\n"
            "1) Gọi công cụ Agent (công cụ giao việc cho subagent) với subagent_type general-purpose, "
            f"description \"S2 con\", prompt: \"Trả lời đúng một dòng: {DAU_CON_1}. Không dùng công cụ nào.\"\n"
            "2) Gọi công cụ Bash với tham số run_in_background=true để chạy đúng lệnh:\n"
            f"{LENH_NEN}\n"
            "Sau đó KHÔNG chờ, KHÔNG kiểm output, KHÔNG gọi thêm công cụ nào. Trả lời ngắn: DA_GIAO_VIEC_NEN, "
            "kèm id của subagent và id việc nền nếu công cụ có trả về.\n")
        tools_1 = CONG_CU_NEN + CONG_CU_THAM_DO
        argv_1 = dung_argv_nen(exe, tools=tools_1, session_id=sid, model=model)
        log(f"NEN lượt 1: subagent + Bash nền ngủ {NGU_NEN_S2}s (--tools có thêm tên thăm dò)")
        t_bd_1 = time.monotonic() - t0
        k1 = chay_claude("N1_giao_viec_nen", argv_1, lam_viec, stdin_1, env, thu_muc_log)
        if not any(e.get("type") == "system" and e.get("subtype") == "init" for e in k1.get("su_kien", [])):
            # Có thể tên thăm dò không hợp lệ làm claude từ chối khởi động -> chạy lại đúng 3 công cụ
            out["luot1_lan_dau_khong_init"] = {"ma_thoat": k1.get("ma_thoat"), "stderr_cuoi": k1.get("stderr_cuoi")}
            out["lan_goi"].append(tom_tat(k1))
            log("NEN lượt 1 không có init -> chạy lại với --tools đúng Agent,SendMessage,Bash")
            sid = str(uuid.uuid4())
            argv_1 = dung_argv_nen(exe, tools=CONG_CU_NEN, session_id=sid, model=model)
            t_bd_1 = time.monotonic() - t0
            k1 = chay_claude("N1b_giao_viec_nen", argv_1, lam_viec, stdin_1, env, thu_muc_log)
        t_thoat_1 = t_bd_1 + (k1.get("thoi_gian_s") or 0)
        file_luc_thoat = file_xong.exists()
        cc1 = cong_cu_chi_tiet(k1.get("su_kien", []))
        tb1 = tim_thong_bao_nen(k1.get("su_kien", []))
        t1 = tom_tat(k1)
        t1["cong_cu_chi_tiet"] = cc1
        t1["thong_bao_nen_trong_luot"] = tb1
        out["lan_goi"].append(t1)

        time.sleep(3)
        if theo_doi.psutil:
            theo_doi.quet()
        song_sau_3s = theo_doi.con_song()

        bash_nen = next((c for c in cc1 if c["ten"] == "Bash" and c.get("nen")), None)
        agent_goi = next((c for c in cc1 if c["ten"] in ("Agent", "Task") and not c.get("cha")), None)
        t_goi_nen = (t_bd_1 + bash_nen["t_s"]) if bash_nen and bash_nen.get("t_s") is not None else None
        id_nen = None
        if bash_nen and bash_nen.get("ket_qua_dau"):
            m = RE_ID_NEN.search(bash_nen["ket_qua_dau"])
            id_nen = (m.group(1) or m.group(2)) if m else None
        id_agent = None
        if agent_goi and agent_goi.get("ket_qua_dau"):
            m = RE_ID_AGENT.search(agent_goi["ket_qua_dau"])
            id_agent = m.group(1) if m else None
        out["id_tu_luot1"] = {"id_viec_nen": id_nen, "id_subagent": id_agent}

        init1 = t1.get("init") or {}
        tools_init = init1.get("tools")
        muc["n6_ten_cong_cu_init"].update(
            dat=True if isinstance(tools_init, list) else None,
            ghi_chu=f"init.tools={tools_init}; tên thăm dò CÓ trong init: "
                    f"{[x for x in CONG_CU_THAM_DO if isinstance(tools_init, list) and x in tools_init]}; "
                    f"--tools lượt 1={argv_1[argv_1.index('--tools') + 1]}")
        muc["n7_subagent_luot1"].update(
            dat=(bool(agent_goi) and not agent_goi.get("loi") and DAU_CON_1 in (agent_goi.get("ket_qua_dau") or ""))
            if t1.get("result") else None,
            ghi_chu=f"tool_use Agent/Task: {agent_goi['ten'] if agent_goi else None}; "
                    f"lỗi: {agent_goi.get('loi') if agent_goi else None}; id_subagent={id_agent}; "
                    f"bị từ chối: {[d for d in ((t1.get('result') or {}).get('permission_denials') or [])]}")

        # ---- chờ tới mốc việc nền đáng lẽ xong ----
        moc = (t_goi_nen if t_goi_nen is not None else t_bd_1) + NGU_NEN_S2 + 20
        t_file = (time.monotonic() - t0) if file_luc_thoat else None
        log(f"NEN: chờ tới mốc gọi nền + {NGU_NEN_S2 + 20}s để xem {FILE_NEN_XONG}")
        while t_file is None and time.monotonic() - t0 < moc:
            time.sleep(2)
            if file_xong.exists():
                t_file = time.monotonic() - t0
        song_sau_moc = theo_doi.con_song()

        p_truoc = None
        if bash_nen and t_goi_nen is not None and not k1.get("het_gio"):
            p_truoc = (t_thoat_1 < t_goi_nen + NGU_NEN_S2) and not file_luc_thoat
        muc["n1_p_thoat_truoc_viec_nen"].update(
            dat=p_truoc,
            ghi_chu=f"agent gọi Bash nền: {bool(bash_nen)}; gọi nền lúc {t_goi_nen and round(t_goi_nen, 1)}s, "
                    f"-p thoát lúc {round(t_thoat_1, 1)}s (mã {k1.get('ma_thoat')}, hết giờ {k1.get('het_gio')}); "
                    f"file có lúc thoát: {file_luc_thoat}")
        muc["n2_nen_con_song_sau_p_thoat"].update(
            dat=(bool(song_sau_3s) if theo_doi.thay else None) if theo_doi.psutil else None,
            ghi_chu=f"psutil: {out['psutil']}; tiến trình nền thấy được: {list(theo_doi.thay.values())}; "
                    f"còn sống 3s sau thoát: {song_sau_3s}; còn sống ở mốc +{NGU_NEN_S2 + 20}s: {song_sau_moc}"
                    + ("" if theo_doi.thay else "; KHÔNG bắt được tiến trình nền nào (có thể chết trước lần quét đầu)"))
        muc["n3_file_nen_xong_xuat_hien"].update(
            dat=t_file is not None if bash_nen else None,
            ghi_chu=f"xuất hiện lúc {t_file and round(t_file, 1)}s (mốc chờ {round(moc, 1)}s)")

        # ---- lượt 2: --resume hỏi trạng thái + SendMessage tới subagent cũ ----
        res1 = t1.get("result") or {}
        sid_ok = init1.get("session_id") or sid
        if res1:
            goi_y_id = f" (id subagent lượt trước: {id_agent})" if id_agent else " (dùng id/tên subagent bạn nhớ từ lượt trước)"
            stdin_2 = (
                "PHIẾU SPIKE-NEN lượt 2 (tiếp phiên). Không chạy lệnh Bash nào.\n"
                "1) Cho biết trạng thái việc Bash nền ở lượt trước: từ lượt trước tới giờ bạn có nhận được "
                "thông báo hệ thống nào báo việc nền đã xong không? Nếu có, chép nguyên văn.\n"
                f"2) Dùng công cụ SendMessage ĐÚNG MỘT LẦN gửi tới subagent ở lượt trước{goi_y_id} nội dung: "
                f"\"Trả lời đúng một dòng: {DAU_CON_2}\". Nếu không có công cụ SendMessage hoặc bị từ chối, "
                "KHÔNG thử cách khác.\n"
                "3) Kết thúc bằng đúng hai dòng:\n"
                "NHAN_THONG_BAO_NEN: co | khong\n"
                "SENDMESSAGE: chay | loi | khong_co\n")
            argv_2 = dung_argv_nen(exe, tools=argv_1[argv_1.index("--tools") + 1].split(","),
                                   resume=sid_ok, model=model)
            log("NEN lượt 2: --resume, hỏi trạng thái nền + SendMessage")
            k2 = chay_claude("N2_resume_hoi_nen", argv_2, lam_viec, stdin_2, env, thu_muc_log)
            cc2 = cong_cu_chi_tiet(k2.get("su_kien", []))
            bo_qua = [x for x in (bash_nen.get("id") if bash_nen else None,) if x]
            tb2 = tim_thong_bao_nen(k2.get("su_kien", []), bo_qua)
            t2 = tom_tat(k2)
            t2["cong_cu_chi_tiet"] = cc2
            t2["thong_bao_nen_trong_luot"] = tb2
            out["lan_goi"].append(t2)
            txt2 = van_ban(t2)
            m_tb = re.search(r"NHAN_THONG_BAO_NEN:\s*(\w+)", txt2)
            m_sm = re.search(r"SENDMESSAGE:\s*(\w+)", txt2)
            muc["n4_luot2_nhan_thong_bao_nen"].update(
                dat=(bool(tb2) or bool(m_tb and m_tb.group(1).lower() == "co")) if t2.get("result") else None,
                ghi_chu=f"sự kiện stream có dấu hiệu: {len(tb2)}; agent tự khai: {m_tb.group(1) if m_tb else None}; "
                        f"lượt 1 cũng có dấu hiệu: {len(tb1)}")
            sm = [c for c in cc2 if c["ten"] == "SendMessage"]
            sm_tu_choi = bi_tu_choi(t2, "SendMessage")
            muc["n5_sendmessage_subagent_cu"].update(
                dat=(bool(sm) and not sm_tu_choi and not any(c.get("loi") for c in sm)) if t2.get("result") else None,
                ghi_chu=f"số tool_use SendMessage: {len(sm)}; bị từ chối: {sm_tu_choi}; "
                        f"kết quả: {[c.get('ket_qua_dau') for c in sm]}; có dấu {DAU_CON_2}: "
                        f"{any(DAU_CON_2 in (c.get('ket_qua_dau') or '') for c in cc2) or DAU_CON_2 in txt2}; "
                        f"agent tự khai: {m_sm.group(1) if m_sm else None}; "
                        f"SendMessage trong init lượt 2: {'SendMessage' in ((t2.get('init') or {}).get('tools') or [])}")
        else:
            for k in ("n4_luot2_nhan_thong_bao_nen", "n5_sendmessage_subagent_cu"):
                muc[k]["ghi_chu"] = "bỏ qua: lượt 1 không có result"
        out["file_nen_xong_cuoi"] = file_xong.exists()
        out["nen_con_song_cuoi"] = theo_doi.con_song()
    finally:
        theo_doi.dung()
        con = theo_doi.con_song()
        if con:
            out["don_tien_trinh_nen"] = {pid: giet_cay(pid) for pid in con}
        out["tien_trinh_nen_da_thay"] = list(theo_doi.thay.values())
        _dong_goi(out, tam, lam_viec, giu_tam, t_bat_dau)
        muc["n8_chi_phi"].update(
            dat=(out["chi_phi_tong_usd"] > 0) if out["lan_goi"] else None,
            ghi_chu=f"từng lượt: {[(g['ten'], chi_phi(g)) for g in out['lan_goi']]}")
    return out


# ---------------------------------------------------------------- kịch bản sống (S-3)
# MỘT tiến trình `claude -p --input-format stream-json --output-format stream-json --verbose`
# sống suốt việc; tin user gửi qua stdin dạng JSON lines, KHÔNG đóng stdin giữa các lượt.
# Định dạng tin (docs: code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode, SDKUserMessage):
#   {"type":"user","message":{"role":"user","content":"<chữ>"},"parent_tool_use_id":null}
# Mỗi lượt kết thúc bằng một sự kiện `result`.

TEN_AGENT_SONG = "thu-runner-song"
CONG_CU_SONG = ["Agent", "Task", "TaskOutput", "TaskStop", "SendMessage", "Bash"]  # --allowedTools
CONG_CU_THAM_DO_SONG = ["BashOutput", "KillShell"]  # chỉ thêm vào --tools để xem init có không
DAU_CON_S3 = "CON-S3-OK"
DAU_CON_S3_LAI = "CON-S3-LAI"
TU_KHOA_SONG = "CHIM-SAO-77"
MAU_CHON = "xanh"
CHO_QUAN_SAT_SONG_S = NGU_NEN_S2 + 20   # mốc quan sát tính từ lúc gọi Bash nền
HET_GIO_LUOT_SONG_S = 300               # chờ result của một lượt
CHO_RANH_TOI_DA_S = 150                 # chờ lượt tự thức (nếu có) xong trước khi gửi tin mới
YEN_LANG_RANH_S = 5                     # coi là rảnh khi sau result im lặng ngần này giây
CHO_THOAT_SAU_DONG_STDIN_S = 90
TONG_HET_GIO_SONG_S = 1200              # trần cứng cả kịch bản: quá thì taskkill cây tiến trình

MO_TA_MUC_SONG = {
    "n1_tien_trinh_khong_thoat_giua_luot": "tiến trình claude còn sống ở mốc quan sát, trước lượt 2 và trước lượt 3",
    "n2_nen_chay_qua_ranh_gioi_luot": "Bash nền chạy tiếp sau result lượt 1 và xong (nen_xong.txt xuất hiện)",
    "n3_thong_bao_nen_toi_agent": "thông báo hoàn tất việc nền tới agent (sự kiện stream có dấu hiệu, hoặc agent tự khai ở lượt 2)",
    "n4_agent_tu_thuc_day": "có sự kiện assistant/result MỚI trong cửa sổ quan sát khi runner chưa gửi gì",
    "n5_subagent_sendmessage": "init.tools có Agent/Task, SendMessage; subagent lượt 1 trả đúng dấu; SendMessage lượt 2 gọi được",
    "n6_phat_hien_cho_user": "result cuối lượt 2 có khối CẦN_USER (LOẠI: chon) đọc được; lượt 3 nhận câu trả lời và nhớ ngữ cảnh",
    "n7_dong_stdin_thoat_gon": "đóng stdin -> tiến trình thoát trong thời hạn, mã thoát 0",
    "n8_chi_phi": "total_cost_usd từng result (cộng dồn theo phiên hay theo lượt?) và tổng",
}


def tin_user_stream_json(noi_dung: str) -> str:
    """Một dòng JSON (kết thúc \\n) cho stdin --input-format stream-json. Hàm thuần."""
    return json.dumps({"type": "user", "message": {"role": "user", "content": noi_dung},
                       "parent_tool_use_id": None}, ensure_ascii=False) + "\n"


def doc_khoi_can_user(van_ban_kq: str) -> dict | None:
    """Đọc khối CẦN_USER CUỐI cùng: {cau_hoi, loai, lua_chon[]}. Không có -> None. Hàm thuần."""
    ds = list(RE_CAN_USER.finditer(van_ban_kq or ""))
    if not ds:
        return None
    m = ds[-1]
    sau = van_ban_kq[m.end():]
    loai = re.search(r"^LOẠI:\s*(\S+)", sau, re.M)
    lc = re.search(r"^LỰA_CHỌN:\s*(.+)$", sau, re.M)
    return {"cau_hoi": m.group(1).strip(),
            "loai": loai.group(1).strip() if loai else None,
            "lua_chon": [x.strip() for x in lc.group(1).split("|") if x.strip()] if lc else []}


def _khong_phai_he_thong(e: dict) -> bool:
    return e.get("type") != "system"


def dang_ranh(su_kien: list[dict], bay_gio_s: float, yen_s: float = YEN_LANG_RANH_S) -> bool:
    """Agent đang chờ người dùng: sự kiện không-phải-system cuối là `result` và đã im lặng >= yen_s.

    Sự kiện system lẻ sau result (vd. thông báo) không tính là bận; nếu nó kéo theo lượt mới thì
    sẽ có assistant/user sau đó -> bận. Hàm thuần.
    """
    cuoi = next((e for e in reversed(su_kien) if _khong_phai_he_thong(e)), None)
    if not cuoi or cuoi.get("type") != "result":
        return False
    moi_nhat = su_kien[-1].get("__t", 0) if su_kien else 0
    return bay_gio_s - moi_nhat >= yen_s


def vi_tri_sau_result_dau(su_kien: list[dict]) -> int:
    """Chỉ số ngay SAU sự kiện `result` đầu tiên; không có result -> 0. Hàm thuần."""
    return next((i + 1 for i, e in enumerate(su_kien) if e.get("type") == "result"), 0)


def chia_theo_result(su_kien: list[dict]) -> list[list[dict]]:
    """Chia luồng sự kiện thành các lượt, mỗi lượt kết thúc ở một `result` (phần dư cuối nếu có). Hàm thuần."""
    luot, cur = [], []
    for e in su_kien:
        cur.append(e)
        if e.get("type") == "result":
            luot.append(cur)
            cur = []
    if cur:
        luot.append(cur)
    return luot


def tom_tat_result(e: dict) -> dict:
    return {"t_s": e.get("__t"), "subtype": e.get("subtype"), "is_error": e.get("is_error"),
            "total_cost_usd": e.get("total_cost_usd"), "num_turns": e.get("num_turns"),
            "duration_ms": e.get("duration_ms"), "session_id": e.get("session_id"),
            "result_dau": str(e.get("result") or "")[:1500]}


def danh_gia_chi_phi(chi_phi_ds: list) -> dict:
    """Từ total_cost_usd của các result: đoán cộng dồn (không giảm) hay theo lượt. Hàm thuần."""
    so = [x for x in chi_phi_ds if isinstance(x, (int, float))]
    if not so:
        return {"kieu": None, "tong_usd": None}
    cong_don = all(b >= a for a, b in zip(so, so[1:])) and len(so) > 1
    return {"kieu": "cong_don_khong_giam" if cong_don else ("mot_result" if len(so) == 1 else "theo_luot"),
            "tong_usd": round(so[-1] if cong_don or len(so) == 1 else sum(so), 4),
            "tong_neu_cong": round(sum(so), 4), "lon_nhat": round(max(so), 4)}


class PhienSong:
    """Một tiến trình claude stream-json sống; đọc stdout theo dòng có mốc thời gian, ghi stdin không đóng."""

    def __init__(self, argv: list[str], cwd: Path, env: dict[str, str], t0: float):
        self.argv, self.cwd, self.env, self.t0 = argv, cwd, env, t0
        self.p: subprocess.Popen | None = None
        self.dong_tho: list[str] = []
        self.su_kien: list[dict] = []
        self.loi_ra: list[str] = []
        self.khong_json = 0
        self.tin_da_gui: list[dict] = []
        self._cv = threading.Condition()
        self._th: list[threading.Thread] = []
        self.loi_ghi: str | None = None

    def t(self) -> float:
        return time.monotonic() - self.t0

    def bat_dau(self) -> str | None:
        kw: dict = {}
        if os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= STARTF_USESHOWWINDOW
            si.wShowWindow = SW_HIDE
            kw["startupinfo"] = si
            kw["creationflags"] = CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP
        try:
            self.p = subprocess.Popen(self.argv, cwd=str(self.cwd), env=self.env, stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
        except OSError as e:
            return f"{type(e).__name__}: {e}"
        self._th = [threading.Thread(target=self._doc_out, daemon=True),
                    threading.Thread(target=self._doc_err, daemon=True)]
        for th in self._th:
            th.start()
        return None

    def _doc_out(self) -> None:
        for b in iter(self.p.stdout.readline, b""):
            s = b.decode("utf-8", errors="replace").rstrip("\r\n")
            t = round(self.t(), 2)
            with self._cv:
                self.dong_tho.append(s)
                try:
                    sk = json.loads(s)
                except ValueError:
                    self.khong_json += 1
                    sk = None
                if isinstance(sk, dict):
                    sk["__t"] = t
                    self.su_kien.append(sk)
                self._cv.notify_all()
        with self._cv:
            self._cv.notify_all()

    def _doc_err(self) -> None:
        for b in iter(self.p.stderr.readline, b""):
            self.loi_ra.append(b.decode("utf-8", errors="replace").rstrip("\r\n"))

    def song(self) -> bool:
        return self.p is not None and self.p.poll() is None

    def chup(self) -> list[dict]:
        with self._cv:
            return list(self.su_kien)

    def gui(self, ten: str, noi_dung: str) -> bool:
        """Ghi một tin user (JSON line) rồi flush, KHÔNG đóng stdin."""
        ghi = {"ten": ten, "t_s": round(self.t(), 2), "song_truoc_khi_gui": self.song(), "ok": False}
        try:
            self.p.stdin.write(tin_user_stream_json(noi_dung).encode("utf-8"))
            self.p.stdin.flush()
            ghi["ok"] = True
        except (OSError, ValueError) as e:
            ghi["loi"] = type(e).__name__
            self.loi_ghi = ghi["loi"]
        self.tin_da_gui.append(ghi)
        return ghi["ok"]

    def so_result(self) -> int:
        with self._cv:
            return sum(1 for e in self.su_kien if e.get("type") == "result")

    def cho_result_moi(self, so_truoc: int, het_gio_s: float) -> bool:
        """Chờ tới khi có result thứ so_truoc+1, tiến trình thoát, hoặc hết giờ."""
        han = time.monotonic() + het_gio_s
        with self._cv:
            while True:
                if sum(1 for e in self.su_kien if e.get("type") == "result") > so_truoc:
                    return True
                con = han - time.monotonic()
                if con <= 0 or not self.song():
                    return False
                self._cv.wait(timeout=min(con, 2.0))

    def cho_ranh(self, het_gio_s: float) -> bool:
        han = time.monotonic() + het_gio_s
        while time.monotonic() < han and self.song():
            if dang_ranh(self.chup(), self.t()):
                return True
            time.sleep(1.0)
        return dang_ranh(self.chup(), self.t())

    def dong_stdin(self) -> None:
        try:
            if self.p and self.p.stdin and not self.p.stdin.closed:
                self.p.stdin.close()
        except OSError as e:
            self.loi_ghi = f"dong_stdin: {type(e).__name__}"

    def cho_thoat(self, het_gio_s: float) -> tuple[bool, float | None]:
        """(thoát trong hạn?, giây từ lúc gọi tới lúc thoát)."""
        if self.p is None:
            return False, None
        bd = time.monotonic()
        try:
            self.p.wait(timeout=het_gio_s)
            return True, round(time.monotonic() - bd, 2)
        except subprocess.TimeoutExpired:
            return False, None

    def ket_thuc(self) -> str | None:
        """Dọn: còn sống thì taskkill cây; join thread đọc."""
        ghi = None
        if self.p is not None and self.p.poll() is None:
            ghi = giet_cay(self.p.pid)
            try:
                self.p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                ghi += "; van con song"
        for th in self._th:
            th.join(timeout=10)
        return ghi


def agents_json_song() -> str:
    return json.dumps({TEN_AGENT_SONG: {
        "description": "Agent thử phiên sống cho spike S-3; làm đúng chỉ dẫn, trả lời ngắn.",
        "prompt": (f"Bạn là {TEN_AGENT_SONG}, agent kiểm thử phiên sống nhiều lượt. Làm đúng và chỉ đúng các bước "
                   "được yêu cầu trong tin mới nhất. Nếu một công cụ bị từ chối hoặc không có, KHÔNG tìm cách khác, "
                   "chỉ báo lại. Khi nhận thông báo hệ thống về việc nền, chỉ ghi nhận ngắn gọn, không tự làm thêm việc."),
    }}, ensure_ascii=False)


def dung_argv_song(exe: str, *, tools: list[str], session_id: str, model: str | None = None) -> list[str]:
    """argv kịch bản song: -p, stream-json vào/ra, --strict-mcp-config, dontAsk, KHÔNG có prompt trên argv."""
    a = [exe, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
         "--strict-mcp-config", "--agents", agents_json_song(), "--agent", TEN_AGENT_SONG,
         "--tools", ",".join(tools),
         "--permission-mode", "dontAsk",
         "--allowedTools", *CONG_CU_SONG,
         "--disallowedTools", *CONG_CU_CAM_CHUNG,
         "--session-id", session_id]
    if model:
        a += ["--model", model]
    return a


def _van_ban_result(luot: list[dict]) -> str:
    r = next((e for e in reversed(luot) if e.get("type") == "result"), None)
    return str((r or {}).get("result") or "")


def chay_spike_song(exe: str, giu_tam: bool, model: str | None) -> dict:
    """S-3: một tiến trình stream-json sống qua 3 lượt + cửa sổ quan sát việc nền."""
    out: dict = {
        "phien_ban_script": PHIEN_BAN,
        "kich_ban": "song",
        "claude_exe": exe,
        "claude_exe_ton_tai": Path(exe).is_file(),
        "lenh_nen": LENH_NEN,
        "cong_cu_allowed": CONG_CU_SONG,
        "cong_cu_tham_do_trong_tools": CONG_CU_THAM_DO_SONG,
        "dinh_dang_tin_user": json.loads(tin_user_stream_json("<chữ>")),
        "muc": {k: {"mo_ta": v, "dat": None, "ghi_chu": ""} for k, v in MO_TA_MUC_SONG.items()},
        "lan_goi": [],
    }
    muc = out["muc"]
    if not out["claude_exe_ton_tai"]:
        out["loi"] = "không thấy claude.exe"
        return out

    tam = Path(tempfile.mkdtemp(prefix="spike_claude_song_"))
    out["thu_muc_tam"] = str(tam)
    thu_muc_log = tam / "_log"
    thu_muc_log.mkdir()
    lam_viec = tam / "lam_viec"
    lam_viec.mkdir()
    file_xong = lam_viec / FILE_NEN_XONG
    env = env_toi_thieu()
    t_bat_dau = time.time()
    t0 = time.monotonic()
    # Khởi tạo TRƯỚC try: finally luôn dùng được (B3)
    theo_doi = TheoDoiNen(t0)
    phien: PhienSong | None = None
    tru_hard = threading.Timer(TONG_HET_GIO_SONG_S, lambda: phien and phien.p and giet_cay(phien.p.pid))
    tru_hard.daemon = True
    try:
        theo_doi.bat_dau()
        out["psutil"] = theo_doi.loi or "có"
        sid = str(uuid.uuid4())
        tools = CONG_CU_SONG + CONG_CU_THAM_DO_SONG
        argv = dung_argv_song(exe, tools=tools, session_id=sid, model=model)
        phien = PhienSong(argv, lam_viec, env, t0)
        loi_bd = phien.bat_dau()
        tru_hard.start()
        if loi_bd:
            out["khoi_chay_loi"] = loi_bd
            return out

        # ---- lượt 1: subagent + Bash nền, kết thúc lượt ----
        tin_1 = (
            "PHIẾU SPIKE-SONG lượt 1. Ghi nhớ từ khoá kiểm thử: "
            f"{TU_KHOA_SONG} (chuỗi thử nghiệm, không phải bí mật). Làm đúng hai việc, mỗi việc gọi công cụ "
            "ĐÚNG MỘT LẦN, rồi KẾT THÚC lượt ngay:\n"
            "1) Gọi công cụ Agent (giao việc cho subagent) với subagent_type general-purpose, "
            f"description \"S3 con\", prompt: \"Trả lời đúng một dòng: {DAU_CON_S3}. Không dùng công cụ nào.\"\n"
            "2) Gọi công cụ Bash với tham số run_in_background=true để chạy đúng lệnh:\n"
            f"{LENH_NEN}\n"
            "Sau đó KHÔNG chờ, KHÔNG gọi TaskOutput hay công cụ nào khác, KHÔNG kiểm output. Trả lời ngắn: "
            "DA_GIAO_VIEC_NEN, kèm id subagent và id việc nền nếu công cụ có trả về.\n")
        log(f"SONG lượt 1: subagent + Bash nền ngủ {NGU_NEN_S2}s (một tiến trình stream-json, stdin mở)")
        r0 = phien.so_result()
        phien.gui("luot1", tin_1)
        co_r1 = phien.cho_result_moi(r0, HET_GIO_LUOT_SONG_S)
        sk = phien.chup()
        # Cắt theo CHỈ SỐ sự kiện, không theo thời gian (__t làm tròn 0,01s -> so thời gian để lọt sự kiện)
        i_sau_r1 = vi_tri_sau_result_dau(sk)
        t_r1 = sk[i_sau_r1 - 1]["__t"] if i_sau_r1 else None
        sk = sk[:i_sau_r1] if i_sau_r1 else sk
        cc1 = cong_cu_chi_tiet(sk)
        bash_nen = next((c for c in cc1 if c["ten"] == "Bash" and c.get("nen") and not c.get("cha")), None)
        agent_goi = next((c for c in cc1 if c["ten"] in ("Agent", "Task") and not c.get("cha")), None)
        t_goi_nen = bash_nen.get("t_s") if bash_nen else None
        file_luc_r1 = file_xong.exists()
        id_agent = None
        if agent_goi and agent_goi.get("ket_qua_dau"):
            m = RE_ID_AGENT.search(agent_goi["ket_qua_dau"])
            id_agent = m.group(1) if m else None
        out["id_tu_luot1"] = {"id_subagent": id_agent, "tool_use_id_bash_nen": bash_nen.get("id") if bash_nen else None}

        # ---- cửa sổ quan sát: KHÔNG gửi gì tới mốc gọi nền + 80s ----
        moc = (t_goi_nen if t_goi_nen is not None else (t_r1 or phien.t())) + CHO_QUAN_SAT_SONG_S
        bd_cua_so = t_r1 if t_r1 is not None else phien.t()
        log(f"SONG: im lặng quan sát tới mốc {round(moc, 1)}s (không gửi tin)")
        t_file = phien.t() if file_luc_r1 else None
        while phien.t() < moc and phien.song():
            time.sleep(1.0)
            if t_file is None and file_xong.exists():
                t_file = phien.t()
        if t_file is None and file_xong.exists():
            t_file = phien.t()
        song_o_moc = phien.song()
        if theo_doi.psutil:
            theo_doi.quet()
        nen_song_o_moc = theo_doi.con_song()
        i_bd_cua_so = i_sau_r1 if i_sau_r1 else len(phien.chup())
        sk_cua_so = phien.chup()[i_bd_cua_so:]
        # Nếu agent tự thức và còn đang chạy lượt đó: chờ rảnh trước khi gửi lượt 2
        ranh_truoc_l2 = phien.cho_ranh(CHO_RANH_TOI_DA_S)
        t_gui_2 = phien.t()
        i_gui_2 = len(phien.chup())
        sk_tu_thuc = phien.chup()[i_bd_cua_so:i_gui_2]
        tu_thuc_assistant = [e for e in sk_tu_thuc if e.get("type") == "assistant" and not e.get("parent_tool_use_id")]
        tu_thuc_result = [e for e in sk_tu_thuc if e.get("type") == "result"]

        # ---- lượt 2: hỏi trạng thái + SendMessage + kết thúc bằng CẦN_USER ----
        song_truoc_l2 = phien.song()
        txt2 = ""
        cc2: list[dict] = []
        sk_l2: list[dict] = []
        if song_truoc_l2:
            goi_y_id = f" (id subagent lượt 1: {id_agent})" if id_agent else " (dùng id/tên subagent bạn nhớ từ lượt 1)"
            tin_2 = (
                "PHIẾU SPIKE-SONG lượt 2 (cùng phiên, cùng tiến trình). Không chạy Bash, không gọi TaskOutput.\n"
                "1) Trạng thái việc Bash nền ở lượt 1: từ khi kết thúc lượt 1 tới giờ bạn có nhận thông báo hệ "
                "thống nào báo việc nền đã xong không? Nếu có, chép nguyên văn tối đa 3 dòng. Giữa hai tin của "
                "người dùng bạn có tự trả lời lượt nào không?\n"
                f"2) Nếu có công cụ SendMessage: dùng ĐÚNG MỘT LẦN gửi tới subagent ở lượt 1{goi_y_id} nội dung "
                f"\"Trả lời đúng một dòng: {DAU_CON_S3_LAI}\". Không có hoặc bị từ chối thì KHÔNG thử cách khác.\n"
                "3) Kết thúc câu trả lời bằng các dòng sau, khối CẦN_USER nằm CUỐI CÙNG:\n"
                "NHAN_THONG_BAO_NEN: co | khong\n"
                "TU_THUC_DAY: co | khong\n"
                "SENDMESSAGE: chay | loi | khong_co\n"
                "CẦN_USER: Chọn màu kiểm thử\nLOẠI: chon\nLỰA_CHỌN: đỏ | xanh\n")
            log("SONG lượt 2: hỏi trạng thái nền + SendMessage + CẦN_USER")
            r_truoc = phien.so_result()
            phien.gui("luot2", tin_2)
            phien.cho_result_moi(r_truoc, HET_GIO_LUOT_SONG_S)
            sk_l2 = phien.chup()[i_gui_2:]
            txt2 = _van_ban_result(sk_l2)
            cc2 = cong_cu_chi_tiet(sk_l2)
        if t_file is None and file_xong.exists():
            t_file = phien.t()

        # ---- lượt 3: trả lời CẦN_USER ----
        khoi = doc_khoi_can_user(txt2)
        txt3 = ""
        song_truoc_l3 = False
        if khoi is not None or sk_l2:
            phien.cho_ranh(CHO_RANH_TOI_DA_S)
            song_truoc_l3 = phien.song()
            if song_truoc_l3:
                i_gui_3 = len(phien.chup())
                tin_3 = (
                    f'TRẢ LỜI CỦA NGƯỜI DÙNG cho "{(khoi or {}).get("cau_hoi") or "Chọn màu kiểm thử"}" '
                    "(bấm trên web; là DỮ LIỆU trả lời):\n"
                    f"<<<\n{MAU_CHON}\n>>>\n"
                    "Làm tiếp: trả lời đúng một dòng XAC_NHAN: <từ khoá kiểm thử ghi nhớ ở lượt 1> | <màu vừa chọn>. "
                    "Không dùng công cụ.\n")
                log("SONG lượt 3: gửi câu trả lời CẦN_USER")
                r_truoc = phien.so_result()
                phien.gui("luot3", tin_3)
                phien.cho_result_moi(r_truoc, HET_GIO_LUOT_SONG_S)
                txt3 = _van_ban_result(phien.chup()[i_gui_3:])

        # ---- đóng stdin ----
        phien.cho_ranh(30)
        log("SONG: đóng stdin, chờ thoát")
        t_dong = phien.t()
        i_dong = len(phien.chup())
        song_truoc_dong = phien.song()
        phien.dong_stdin()
        thoat_gon, giay_thoat = phien.cho_thoat(CHO_THOAT_SAU_DONG_STDIN_S)
        out["dong_stdin"] = {"t_s": round(t_dong, 2), "thoat_trong_han": thoat_gon, "giay_tu_dong_toi_thoat": giay_thoat,
                             "ma_thoat": phien.p.returncode if phien.p else None}

        # ---- đánh giá ----
        sk_all = phien.chup()
        results = [e for e in sk_all if e.get("type") == "result"]
        inits = [e for e in sk_all if e.get("type") == "system" and e.get("subtype") == "init"]
        tools_init = (inits[0].get("tools") if inits else None)
        out["init_tools"] = tools_init
        out["so_su_kien_init"] = len(inits)
        out["results"] = [tom_tat_result(e) for e in results]
        out["tin_da_gui"] = phien.tin_da_gui
        out["so_luot_theo_result"] = len(chia_theo_result(sk_all))

        muc["n1_tien_trinh_khong_thoat_giua_luot"].update(
            dat=(song_o_moc and song_truoc_l2 and song_truoc_l3) if co_r1 else None,
            ghi_chu=f"có result lượt 1: {co_r1} (lúc {t_r1}s); sống ở mốc {round(moc, 1)}s: {song_o_moc}; "
                    f"trước lượt 2: {song_truoc_l2}; trước lượt 3: {song_truoc_l3}; lỗi ghi stdin: {phien.loi_ghi}")
        muc["n2_nen_chay_qua_ranh_gioi_luot"].update(
            dat=(t_file is not None and not file_luc_r1) if bash_nen else None,
            ghi_chu=f"agent gọi Bash nền: {bool(bash_nen)} lúc {t_goi_nen}s; file có ngay lúc result lượt 1: {file_luc_r1}; "
                    f"file xuất hiện lúc {t_file and round(t_file, 1)}s; psutil: {out['psutil']}; "
                    f"tiến trình nền thấy: {len(theo_doi.thay)}; còn sống ở mốc: {nen_song_o_moc}")
        bo_qua = [bash_nen.get("id")] if bash_nen and bash_nen.get("id") else []
        tb_sau_r1 = tim_thong_bao_nen(sk_all[i_sau_r1:] if i_sau_r1 else [], bo_qua)
        out["thong_bao_nen_sau_luot1"] = tb_sau_r1[:10]
        m_tb = re.search(r"NHAN_THONG_BAO_NEN:\s*(\w+)", txt2)
        muc["n3_thong_bao_nen_toi_agent"].update(
            dat=(bool(tb_sau_r1) or bool(m_tb and m_tb.group(1).lower() == "co")) if bash_nen and txt2 else None,
            ghi_chu=f"sự kiện stream có dấu hiệu sau lượt 1: {len(tb_sau_r1)} "
                    f"(loại: {sorted({x['loai'] for x in tb_sau_r1})}); agent tự khai: {m_tb.group(1) if m_tb else None}")
        m_tt = re.search(r"TU_THUC_DAY:\s*(\w+)", txt2)
        loai_cua_so = sorted({f"{e.get('type')}/{e.get('subtype')}" for e in sk_cua_so})
        muc["n4_agent_tu_thuc_day"].update(
            dat=bool(tu_thuc_assistant or tu_thuc_result) if co_r1 else None,
            ghi_chu=f"cửa sổ {bd_cua_so}s -> mốc {round(moc, 1)}s (không gửi gì): {len(sk_cua_so)} sự kiện; "
                    f"tới lúc gửi lượt 2 ({round(t_gui_2, 1)}s): "
                    f"assistant chính: {len(tu_thuc_assistant)}, result: {len(tu_thuc_result)} "
                    f"(t={[e.get('__t') for e in tu_thuc_result]}); loại sự kiện: {loai_cua_so}; "
                    f"rảnh trước lượt 2: {ranh_truoc_l2}; agent tự khai: {m_tt.group(1) if m_tt else None}")
        sm = [c for c in cc2 if c["ten"] == "SendMessage"]
        den = [d.get("tool_name") for r in results for d in (r.get("permission_denials") or []) if isinstance(d, dict)]
        co_sm_init = isinstance(tools_init, list) and "SendMessage" in tools_init
        co_agent_init = isinstance(tools_init, list) and any(x in tools_init for x in ("Agent", "Task"))
        sub_ok = bool(agent_goi) and not agent_goi.get("loi") and DAU_CON_S3 in (agent_goi.get("ket_qua_dau") or "")
        muc["n5_subagent_sendmessage"].update(
            dat=(co_agent_init and sub_ok and co_sm_init and bool(sm) and not any(c.get("loi") for c in sm)
                 and "SendMessage" not in den) if co_r1 else None,
            ghi_chu=f"init có Agent/Task: {co_agent_init}; init có SendMessage: {co_sm_init}; subagent lượt 1 "
                    f"({agent_goi['ten'] if agent_goi else None}) đúng dấu: {sub_ok}; id={id_agent}; "
                    f"SendMessage gọi: {len(sm)}, kết quả: {[c.get('ket_qua_dau') for c in sm]}; "
                    f"có {DAU_CON_S3_LAI}: {DAU_CON_S3_LAI in txt2 or any(DAU_CON_S3_LAI in (c.get('ket_qua_dau') or '') for c in cc2)}; "
                    f"permission_denials (mọi result): {den}")
        xac_nhan_ok = TU_KHOA_SONG in txt3 and MAU_CHON in txt3
        muc["n6_phat_hien_cho_user"].update(
            dat=(khoi is not None and (khoi.get("loai") or "").lower() == "chon" and xac_nhan_ok) if txt2 else None,
            ghi_chu=f"khối CẦN_USER lượt 2: {khoi}; lượt 3 nhắc đúng từ khoá + màu: {xac_nhan_ok}; "
                    f"dấu hiệu chờ user = sự kiện result cuối lượt rồi im lặng >= {YEN_LANG_RANH_S}s")
        muc["n7_dong_stdin_thoat_gon"].update(
            dat=(thoat_gon and phien.p.returncode == 0) if song_truoc_dong else None,
            ghi_chu=f"còn sống lúc đóng stdin: {song_truoc_dong}; thoát sau {giay_thoat}s (hạn {CHO_THOAT_SAU_DONG_STDIN_S}s), mã {phien.p.returncode}; "
                    f"sự kiện sau khi đóng stdin: {len(sk_all[i_dong:])}")
        dg = danh_gia_chi_phi([e.get("total_cost_usd") for e in results])
        out["chi_phi_danh_gia"] = dg
        muc["n8_chi_phi"].update(
            dat=(dg["tong_usd"] or 0) > 0 if dg["kieu"] else None,
            ghi_chu=f"từng result: {[e.get('total_cost_usd') for e in results]}; đánh giá: {dg}")
        out["van_ban_luot2_dau"] = txt2[:1500]
        out["van_ban_luot3_dau"] = txt3[:600]
        out["file_nen_xong_cuoi"] = file_xong.exists()
    finally:
        tru_hard.cancel()
        theo_doi.dung()
        con = theo_doi.con_song()
        if con:
            out["don_tien_trinh_nen"] = {pid: giet_cay(pid) for pid in con}
        out["tien_trinh_nen_da_thay"] = list(theo_doi.thay.values())
        if phien is not None:
            don = phien.ket_thuc()
            if don:
                out["don_tien_trinh_claude"] = don
            with open(thu_muc_log / "S_song.jsonl", "w", encoding="utf-8") as f:
                for s in phien.dong_tho:
                    f.write(s + "\n")
            # Một mục lan_goi cho cả tiến trình: tom_tat lấy result CUỐI -> chi phí không đếm trùng
            tt = tom_tat({"ten": "S_song", "argv": phien.argv, "su_kien": phien.chup(),
                          "ma_thoat": phien.p.returncode if phien.p else None, "het_gio": False,
                          "thoi_gian_s": round(phien.t(), 2), "so_dong_khong_json": phien.khong_json,
                          "stderr_cuoi": "\n".join(phien.loi_ra)[-800:]})
            tt["cong_cu_chi_tiet"] = cong_cu_chi_tiet(phien.chup())
            out["lan_goi"].append(tt)
        _dong_goi(out, tam, lam_viec, giu_tam, t_bat_dau)
        dg = out.get("chi_phi_danh_gia")
        if dg and dg.get("tong_usd") is not None:
            out["chi_phi_tong_usd"] = dg["tong_usd"]
    return out


# ---------------------------------------------------------------- kịch bản sống 2 (S-4)
# Cùng dạng lệnh §7.2 (stream-json vào/ra, --strict-mcp-config, dontAsk, --tools = --allowedTools,
# --max-budget-usd, --session-id mới) với agent nội tuyến; cwd = thư mục tạm có skill tạm
# .claude/skills/thu-s4/SKILL.md. Hai tiến trình: CHÍNH (mục 1-4, 6-8) và NGÂN SÁCH (mục 5, trần 0,05).

TEN_AGENT_S4 = "thu-runner-s4"
CONG_CU_S4 = ["Read", "Bash", "Skill", "Agent", "Task", "TaskOutput", "TaskStop"]  # --tools = --allowedTools
CONG_CU_NGAN_SACH = ["Read"]
TEN_SKILL_S4 = "thu-s4"
MA_SKILL_S4 = "MA-SKILL-S4-9137"        # chỉ có trong SKILL.md tạm: thấy trong trả lời = skill đã được đọc
MA_DOC_S4 = "MA-DOC-S4-2468"            # chỉ có trong doc_s4.txt: subagent Read được
TU_KHOA_S4 = "CHIM-CU-31"
DAU_CON_S4 = "CON-S4-OK"
DAU_CON2_S4 = "CON2-S4-OK"
DAU_CHAU_S4 = "CHAU-S4-OK"
DAU_CON_BASH_S4 = "CON-BASH-S4"
DAU_BASH_20 = "XONG-20-S4"
DAU_CHEN = "CHEN-S4-55"
DAU_B2 = "B2-S4-OK"
URL_WEBFETCH_S4 = "https://example.com"
NGU_FOREGROUND_S = 20
TRAN_NGAN_SACH_S4 = 0.05
TRAN_USD_CHINH_S4 = 2.0                 # chốt phụ cho tiến trình chính (như §7.2), đủ cao để không cắt phép đo
CHO_DAI_MAC_DINH_S = 1800
HET_GIO_LUOT_S4 = 420                   # chờ result một lượt (lượt 2 có 3 subagent)
CHO_RESULT_THEM_S = 90                  # sau result đầu của lượt chèn: chờ thêm result của tin chèn
TRAN_CUNG_THEM_S4 = 1500                # trần cứng = --cho-dai + ngần này giây rồi taskkill

MO_TA_MUC_S4 = {
    "s1_tools_skill": "--tools Read,Bash,Skill,Agent,Task,TaskOutput,TaskStop: tên trong init.tools (Agent hay chỉ Task; có Skill); "
                      "gọi được Skill thu-s4 (trả lời có mã chỉ nằm trong SKILL.md tạm)",
    "s2_subagent_cong_cu": "subagent general-purpose: tool_use của subagent có trên stdout (parent_tool_use_id); WebFetch (ngoài --tools) "
                           "bị chặn hay chạy; danh sách mọi tên công cụ subagent phát. dat=true khi thấy được VÀ WebFetch không chạy được",
    "s3_agent_long": "subagent gọi được Agent lồng một cấp (mô phỏng C2 fan-out): tool_use Agent/Task có parent_tool_use_id, có dấu CHAU-S4-OK",
    "s4_tin_giua_luot": f"tin user gửi khi agent đang chạy Bash foreground {NGU_FOREGROUND_S}s: xếp hàng sau lượt hay chen giữa; lượt có hỏng không",
    "s5_max_budget_phien_song": f"--max-budget-usd {TRAN_NGAN_SACH_S4} trong phiên sống (tiến trình riêng): dừng lượt, dừng tiến trình, "
                                "hay tính cộng dồn cả phiên (lượt sau bị từ chối ngay)",
    "s6_im_lang_dai": "im lặng --cho-dai giây với stdin mở: tiến trình còn sống, lượt kế trả lời bình thường và nhớ từ khoá lượt 1",
    "s7_chi_phi_gom_subagent": "total_cost_usd có gồm chi phí subagent không (so token modelUsage với usage assistant cấp cao/subagent)",
    "s8_su_kien_task": "giá trị task_notification.status và task_updated.patch thấy được; Agent chạy foreground có sinh task_started không",
}


def noi_dung_skill_s4() -> str:
    return (f"---\nname: {TEN_SKILL_S4}\n"
            "description: Skill tạm của spike S-4 bộ chạy việc. Chỉ dùng khi được yêu cầu gọi đúng tên thu-s4.\n"
            "---\n\n"
            "# thu-s4\n\n"
            f"Khi skill này được gọi: trả lời đúng một dòng `SKILL_S4: {MA_SKILL_S4}` rồi làm tiếp phần còn lại "
            "của tin người dùng. Không dùng công cụ nào vì skill này.\n")


def agents_json_s4() -> str:
    return json.dumps({TEN_AGENT_S4: {
        "description": "Agent thử phiên sống cho spike S-4; làm đúng chỉ dẫn, trả lời ngắn.",
        "prompt": (f"Bạn là {TEN_AGENT_S4}, agent kiểm thử phiên sống nhiều lượt. Làm đúng và chỉ đúng các bước "
                   "được yêu cầu. Nếu một công cụ bị từ chối hoặc không có, KHÔNG tìm cách khác, chỉ báo lại. "
                   "Khi nhận thông báo hệ thống về việc nền, chỉ ghi nhận ngắn gọn, không tự làm thêm việc."),
    }}, ensure_ascii=False)


def dung_argv_s4(exe: str, *, tools: list[str], session_id: str, budget: float,
                 model: str | None = None) -> list[str]:
    """argv dạng §7.2: stream-json vào/ra, --strict-mcp-config, agent nội tuyến, --tools = --allowedTools,
    dontAsk, cấm chung, --max-budget-usd, --session-id mới. Hàm thuần."""
    a = [exe, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
         "--agents", agents_json_s4(), "--agent", TEN_AGENT_S4,
         "--strict-mcp-config",
         "--tools", ",".join(tools),
         "--permission-mode", "dontAsk",
         "--allowedTools", *tools,
         "--disallowedTools", *CONG_CU_CAM_CHUNG,
         "--max-budget-usd", str(budget),
         "--session-id", session_id]
    if model:
        a += ["--model", model]
    return a


def tong_token(u) -> int:
    """Tổng token của một usage (message.usage hoặc một mục modelUsage, chịu cả hai kiểu tên). Hàm thuần."""
    if not isinstance(u, dict):
        return 0
    khoa = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
            "inputTokens", "outputTokens", "cacheCreationInputTokens", "cacheReadInputTokens")
    return sum(int(u[k]) for k in khoa if isinstance(u.get(k), (int, float)))


def usage_theo_cap(su_kien: list[dict]) -> dict:
    """Token của message assistant, khử trùng theo message.id (lấy bản cuối), tách cấp cao / subagent. Hàm thuần."""
    theo_id: dict[str, tuple[bool, int]] = {}
    khong_id = {"cap_cao": 0, "subagent": 0}
    for e in su_kien:
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") if isinstance(e.get("message"), dict) else {}
        cap_cao = not e.get("parent_tool_use_id")
        n = tong_token(msg.get("usage"))
        if msg.get("id"):
            theo_id[msg["id"]] = (cap_cao, n)
        else:
            khong_id["cap_cao" if cap_cao else "subagent"] += n
    ra = dict(khong_id)
    for cap_cao, n in theo_id.values():
        ra["cap_cao" if cap_cao else "subagent"] += n
    ra["so_message_subagent"] = sum(1 for c, _ in theo_id.values() if not c)
    return ra


def tom_model_usage(res: dict) -> dict:
    """Tóm modelUsage của một result: Σ costUSD, Σ token, theo model. Hàm thuần."""
    mu = res.get("modelUsage") if isinstance(res.get("modelUsage"), dict) else {}
    theo = {k: {"token": tong_token(v), "costUSD": (v or {}).get("costUSD")} for k, v in mu.items()}
    cost = [x["costUSD"] for x in theo.values() if isinstance(x["costUSD"], (int, float))]
    return {"co_modelUsage": bool(mu), "theo_model": theo,
            "tong_cost": round(sum(cost), 6) if cost else None,
            "tong_token": sum(x["token"] for x in theo.values())}


def danh_gia_chi_phi_subagent(token_mu_truoc: int | None, token_mu_sau: int, usage_luot: dict) -> dict:
    """Mục 7: chênh token modelUsage của lượt có subagent so với token assistant cấp cao/subagent của lượt.

    modelUsage cộng dồn (trước có số) -> lấy chênh; không thì dùng nguyên số sau. Gồm subagent ⇔ chênh
    ≥ cấp cao + 50% subagent; chỉ ≈ cấp cao (< cấp cao + 10% subagent) -> không gồm. Hàm thuần.
    """
    chenh = token_mu_sau - token_mu_truoc if token_mu_truoc is not None and token_mu_sau >= token_mu_truoc else token_mu_sau
    cc, sub = usage_luot.get("cap_cao", 0), usage_luot.get("subagent", 0)
    if sub <= 0:
        gom = None  # stdout không có usage subagent -> không so được
    elif chenh >= cc + 0.5 * sub:
        gom = True
    elif chenh < cc + 0.1 * sub:
        gom = False
    else:
        gom = None
    return {"chenh_token_modelUsage": chenh, "token_cap_cao": cc, "token_subagent": sub, "gom_subagent": gom}


def tom_su_kien_task(su_kien: list[dict], id_agent_foreground: list[str]) -> dict:
    """Mục 8: tập status của task_notification, patch của task_updated, task_started theo tool_use_id. Hàm thuần."""
    status, patch_khoa, patch_mau, bd = set(), set(), [], []
    for e in su_kien:
        if e.get("type") != "system":
            continue
        st = e.get("subtype")
        if st == "task_notification":
            status.add(str(e.get("status")))
        elif st == "task_updated":
            p = e.get("patch") if isinstance(e.get("patch"), dict) else {}
            patch_khoa.update(p.keys())
            if len(patch_mau) < 12:
                patch_mau.append({k: (v if isinstance(v, (str, int, float, bool)) or v is None else type(v).__name__)
                                  for k, v in p.items()})
        elif st == "task_started":
            bd.append({"task_id": e.get("task_id"), "tool_use_id": e.get("tool_use_id"),
                       "task_type": e.get("task_type"), "subagent_type": e.get("subagent_type")})
    fg = set(id_agent_foreground)
    return {"task_notification_status": sorted(status), "task_updated_patch_khoa": sorted(patch_khoa),
            "task_updated_patch_mau": patch_mau, "task_started": bd,
            "agent_foreground_co_task_started": (any(x["tool_use_id"] in fg for x in bd) if fg else None)}


def phan_loai_chen(su_kien: list[dict], id_bash: str | None, dau_chen: str, dau_bash: str) -> dict:
    """Mục 4: su_kien = mọi sự kiện từ lúc gửi tin lượt Bash foreground (đã có tin chèn ở giữa). Hàm thuần.

    - chen_giua_luot: chỉ MỘT result chứa cả dấu bash và dấu chèn (tin được nạp vào chính lượt đó);
    - xep_hang_sau_luot: result đầu không có dấu chèn, một result SAU có;
    - bi_bo_qua: không result nào có dấu chèn.
    Lượt hỏng ⇔ result đầu is_error, hoặc tool_result Bash lỗi/thiếu dấu bash.
    """
    results = [e for e in su_kien if e.get("type") == "result"]
    cc = cong_cu_chi_tiet(su_kien)
    bash = next((c for c in cc if c["id"] == id_bash), None) if id_bash else None
    co_chen = [dau_chen in str(r.get("result") or "") for r in results]
    if not results:
        kieu = None
    elif co_chen[0] and dau_bash in str(results[0].get("result") or ""):
        kieu = "chen_giua_luot"
    elif co_chen[0]:
        kieu = "chen_giua_luot_thay_ket_qua"  # result đầu có dấu chèn nhưng mất dấu bash
    elif any(co_chen[1:]):
        kieu = "xep_hang_sau_luot"
    else:
        kieu = "bi_bo_qua"
    # assistant cấp cao nhắc dấu chèn TRƯỚC khi có tool_result Bash -> tin được đọc ngay giữa lúc tool chạy
    t_bash_xong = bash.get("t_ket_qua_s") if bash else None
    nhac_som = any(
        e.get("type") == "assistant" and not e.get("parent_tool_use_id") and t_bash_xong is not None
        and (e.get("__t") or 0) < t_bash_xong and dau_chen in json.dumps(e.get("message"), ensure_ascii=False)
        for e in su_kien)
    hong = bool(results and results[0].get("is_error")) or bash is None or bool(bash.get("loi")) \
        or dau_bash not in (bash.get("ket_qua_dau") or "")
    return {"kieu": kieu, "so_result": len(results), "result_co_dau_chen": co_chen,
            "result_dau_co_dau_bash": bool(results) and dau_bash in str(results[0].get("result") or ""),
            "subtype_result": [r.get("subtype") for r in results],
            "nhac_chen_truoc_khi_bash_xong": nhac_som, "t_bash_xong_s": t_bash_xong,
            "luot_hong": hong if results else None}


def phan_loai_ngan_sach(ds: list[dict]) -> dict:
    """Mục 5: ds = các lượt của tiến trình có --max-budget-usd, mỗi phần tử
    {co_result, subtype, is_error, total_cost_usd, song_sau}. Hàm thuần.

    Lượt k đầu tiên có subtype chứa 'budget':
    - tiến trình chết sau lượt k -> dung_tien_trinh;
    - lượt k+1 cũng 'budget' -> cong_don_ca_phien (mọi lượt sau bị từ chối);
    - lượt k+1 thành công -> theo_luot;
    - không có lượt k+1 -> chi_dung_luot (chưa biết lượt sau).
    Không lượt nào chạm -> khong_cham (kèm chi phí cuối).
    """
    k = next((i for i, x in enumerate(ds) if "budget" in str(x.get("subtype") or "").lower()), None)
    if k is None:
        return {"kieu": "khong_cham", "luot_cham": None,
                "chi_phi_cuoi": next((x.get("total_cost_usd") for x in reversed(ds) if x.get("co_result")), None)}
    if not ds[k].get("song_sau"):
        kieu = "dung_tien_trinh"
    elif k + 1 >= len(ds) or not ds[k + 1].get("co_result"):
        kieu = "chi_dung_luot" if k + 1 >= len(ds) else "luot_sau_khong_result"
    elif "budget" in str(ds[k + 1].get("subtype") or "").lower():
        kieu = "cong_don_ca_phien"
    else:
        kieu = "theo_luot"
    return {"kieu": kieu, "luot_cham": k + 1, "subtype_luot_cham": ds[k].get("subtype"),
            "chi_phi_luc_cham": ds[k].get("total_cost_usd")}


def tom_tat_result_s4(e: dict) -> dict:
    tt = tom_tat_result(e)
    tt["modelUsage"] = tom_model_usage(e)
    tt["permission_denials"] = [
        {"tool_name": d.get("tool_name"),
         "input": json.dumps(d.get("tool_input"), ensure_ascii=False)[:200]}
        for d in (e.get("permission_denials") or []) if isinstance(d, dict)]
    return tt


def _gui_va_cho(phien: PhienSong, ten: str, noi_dung: str, het_gio_s: float) -> tuple[int, bool]:
    """Gửi một tin, chờ result mới. Trả (chỉ số sự kiện lúc gửi, có result mới)."""
    i = len(phien.chup())
    r = phien.so_result()
    phien.gui(ten, noi_dung)
    return i, phien.cho_result_moi(r, het_gio_s)


def _ghi_phien(out: dict, phien: PhienSong, ten: str, thu_muc_log: Path) -> None:
    don = phien.ket_thuc()
    if don:
        out.setdefault("don_tien_trinh_claude", {})[ten] = don
    with open(thu_muc_log / f"{ten}.jsonl", "w", encoding="utf-8") as f:
        for s in phien.dong_tho:
            f.write(s + "\n")
    sk = phien.chup()
    tt = tom_tat({"ten": ten, "argv": phien.argv, "su_kien": sk,
                  "ma_thoat": phien.p.returncode if phien.p else None, "het_gio": False,
                  "thoi_gian_s": round(phien.t(), 2), "so_dong_khong_json": phien.khong_json,
                  "stderr_cuoi": "\n".join(phien.loi_ra)[-800:]})
    tt["cong_cu_chi_tiet"] = cong_cu_chi_tiet(sk)
    tt["results"] = [tom_tat_result_s4(e) for e in sk if e.get("type") == "result"]
    tt["tin_da_gui"] = phien.tin_da_gui
    out["lan_goi"].append(tt)


def _do_ngan_sach(exe: str, lam_viec: Path, env: dict, t0: float, model: str | None,
                  dat_phien) -> dict:
    """Mục 5: tiến trình riêng --max-budget-usd 0.05, tối đa 3 lượt. dat_phien(p) đăng ký để finally dọn."""
    for i in range(3):
        (lam_viec / f"b_{i}.txt").write_text(f"Tệp ngân sách {i}: " + "dữ liệu thử ngân sách " * 60, encoding="utf-8")
    phien = PhienSong(dung_argv_s4(exe, tools=CONG_CU_NGAN_SACH, session_id=str(uuid.uuid4()),
                                   budget=TRAN_NGAN_SACH_S4, model=model), lam_viec, env, t0)
    dat_phien(phien)
    ra: dict = {"argv_tools": CONG_CU_NGAN_SACH, "tran_usd": TRAN_NGAN_SACH_S4, "luot": []}
    loi = phien.bat_dau()
    if loi:
        ra["khoi_chay_loi"] = loi
        return ra
    tin = [
        ("B1", "PHIẾU S4-NGÂN-SÁCH lượt 1: dùng Read đọc lần lượt b_0.txt, b_1.txt, b_2.txt trong thư mục hiện tại "
               "(mỗi file một lần gọi), rồi tóm tắt mỗi file một câu.\n"),
        ("B2", f"PHIẾU S4-NGÂN-SÁCH lượt 2: trả lời đúng một dòng: {DAU_B2}. Không dùng công cụ.\n"),
        ("B3", "PHIẾU S4-NGÂN-SÁCH lượt 3: đọc lại b_0.txt bằng Read rồi trả lời một câu.\n"),
    ]
    da_cham = False
    for ten, noi_dung in tin:
        if not phien.song():
            break
        i, co = _gui_va_cho(phien, ten, noi_dung, HET_GIO_LUOT_S4)
        time.sleep(5)
        sk = phien.chup()[i:]
        r = next((e for e in reversed(sk) if e.get("type") == "result"), None)
        ra["luot"].append({"ten": ten, "co_result": co and r is not None,
                           "subtype": (r or {}).get("subtype"), "is_error": (r or {}).get("is_error"),
                           "total_cost_usd": (r or {}).get("total_cost_usd"), "num_turns": (r or {}).get("num_turns"),
                           "result_dau": str((r or {}).get("result") or "")[:300],
                           "so_tool_use": len(cong_cu_chi_tiet(sk)),
                           "song_sau": phien.song()})
        cham = "budget" in str((r or {}).get("subtype") or "").lower()
        if da_cham:
            break  # đã có lượt sau lượt chạm -> đủ để phân loại
        da_cham = cham
    ra["phan_loai"] = phan_loai_ngan_sach(ra["luot"])
    song_truoc_dong = phien.song()
    phien.dong_stdin()
    thoat, giay = phien.cho_thoat(CHO_THOAT_SAU_DONG_STDIN_S)
    ra["dong_stdin"] = {"song_truoc_dong": song_truoc_dong, "thoat_trong_han": thoat, "giay": giay,
                        "ma_thoat": phien.p.returncode if phien.p else None}
    return ra


def chay_spike_song2(exe: str, giu_tam: bool, model: str | None, cho_dai_s: int) -> dict:
    """S-4: phiên sống, phần còn thiếu (8 mục §13 Đợt 5)."""
    out: dict = {
        "phien_ban_script": PHIEN_BAN,
        "kich_ban": "song2",
        "claude_exe": exe,
        "claude_exe_ton_tai": Path(exe).is_file(),
        "cong_cu_tools_va_allowed": CONG_CU_S4,
        "tran_usd_tien_trinh_chinh": TRAN_USD_CHINH_S4,
        "cho_dai_s": cho_dai_s,
        "muc": {k: {"mo_ta": v, "dat": None, "ghi_chu": ""} for k, v in MO_TA_MUC_S4.items()},
        "lan_goi": [],
    }
    muc = out["muc"]
    if not out["claude_exe_ton_tai"]:
        out["loi"] = "không thấy claude.exe"
        return out

    tam = Path(tempfile.mkdtemp(prefix="spike_claude_s4_"))
    out["thu_muc_tam"] = str(tam)
    thu_muc_log = tam / "_log"
    thu_muc_log.mkdir()
    lam_viec = tam / "lam_viec"
    thu_skill = lam_viec / ".claude" / "skills" / TEN_SKILL_S4
    thu_skill.mkdir(parents=True)
    (thu_skill / "SKILL.md").write_text(noi_dung_skill_s4(), encoding="utf-8")
    file_doc = lam_viec / "doc_s4.txt"
    file_doc.write_text(f"Tệp cho subagent đọc. Mã: {MA_DOC_S4}\n", encoding="utf-8")
    env = env_toi_thieu()
    t_bat_dau = time.time()
    t0 = time.monotonic()
    # Khởi tạo TRƯỚC try: finally luôn dùng được (B3)
    ds_phien: dict[str, PhienSong] = {}

    def _giet_het() -> None:
        for p in list(ds_phien.values()):
            if p.p is not None and p.p.poll() is None:
                giet_cay(p.p.pid)

    tru_hard = threading.Timer(cho_dai_s + TRAN_CUNG_THEM_S4, _giet_het)
    tru_hard.daemon = True
    try:
        tru_hard.start()

        # ======== tiến trình NGÂN SÁCH (mục 5) ========
        log(f"S4 mục 5: tiến trình riêng --max-budget-usd {TRAN_NGAN_SACH_S4}, tối đa 3 lượt")
        ns = _do_ngan_sach(exe, lam_viec, env, t0, model, lambda p: ds_phien.__setitem__("S4_ngan_sach", p))
        out["ngan_sach"] = ns
        pl = ns.get("phan_loai") or {}
        muc["s5_max_budget_phien_song"].update(
            dat=True if pl.get("kieu") in ("dung_tien_trinh", "cong_don_ca_phien", "theo_luot", "chi_dung_luot") else None,
            ket_luan=pl.get("kieu"),
            ghi_chu=f"phân loại: {pl}; các lượt: {[(x['ten'], x['subtype'], x['total_cost_usd'], x['song_sau']) for x in ns.get('luot', [])]}; "
                    f"đóng stdin: {ns.get('dong_stdin')}")

        # ======== tiến trình CHÍNH ========
        sid = str(uuid.uuid4())
        phien = PhienSong(dung_argv_s4(exe, tools=CONG_CU_S4, session_id=sid, budget=TRAN_USD_CHINH_S4, model=model),
                          lam_viec, env, t0)
        ds_phien["S4_chinh"] = phien
        loi_bd = phien.bat_dau()
        if loi_bd:
            out["khoi_chay_loi"] = loi_bd
            return out

        # ---- lượt 1: Skill (mục 1) ----
        tin_1 = (
            f"PHIẾU S4 lượt 1. Ghi nhớ từ khoá kiểm thử: {TU_KHOA_S4} (chuỗi thử nghiệm, không phải bí mật). "
            f"Gọi công cụ Skill ĐÚNG MỘT LẦN với skill \"{TEN_SKILL_S4}\" và làm theo nội dung skill. "
            "Không gọi công cụ nào khác. Kết thúc bằng dòng: SKILL: chay | loi | khong_co\n")
        log("S4 lượt 1: Skill thu-s4")
        i1, co_r1 = _gui_va_cho(phien, "luot1", tin_1, HET_GIO_LUOT_S4)
        phien.cho_ranh(60)
        sk1 = phien.chup()[i1:]
        txt1 = _van_ban_result(sk1)
        cc1 = cong_cu_chi_tiet(sk1)
        inits = [e for e in phien.chup() if e.get("type") == "system" and e.get("subtype") == "init"]
        init0 = inits[0] if inits else {}
        tools_init = init0.get("tools")
        skills_init = init0.get("skills")
        ds_skill_init = [s if isinstance(s, str) else (s or {}).get("name") for s in (skills_init or [])]
        out["init"] = {"tools": tools_init, "claude_code_version": init0.get("claude_code_version"),
                       "so_skills": len(ds_skill_init), "co_skill_thu_s4": TEN_SKILL_S4 in ds_skill_init,
                       "permissionMode": init0.get("permissionMode"), "agents": init0.get("agents"),
                       "so_su_kien_init": len(inits)}
        goi_skill = [c for c in cc1 if c["ten"] == "Skill" and not c.get("cha")]
        skill_ok = bool(goi_skill) and not any(c.get("loi") for c in goi_skill) and MA_SKILL_S4 in txt1
        muc["s1_tools_skill"].update(
            dat=(isinstance(tools_init, list) and "Skill" in tools_init and skill_ok) if co_r1 else None,
            ghi_chu=f"init.tools={tools_init}; có Agent: {isinstance(tools_init, list) and 'Agent' in tools_init}; "
                    f"có Task: {isinstance(tools_init, list) and 'Task' in tools_init}; có Skill: "
                    f"{isinstance(tools_init, list) and 'Skill' in tools_init}; init.skills có thu-s4: "
                    f"{out['init']['co_skill_thu_s4']} ({len(ds_skill_init)} skill); tool_use Skill: "
                    f"{[(c['input_dau'], c['loi'], (c['ket_qua_dau'] or '')[:150]) for c in goi_skill]}; "
                    f"trả lời có {MA_SKILL_S4}: {MA_SKILL_S4 in txt1}")
        out["van_ban_luot1_dau"] = txt1[:800]

        # ---- lượt 2: subagent công cụ + Agent lồng (mục 2, 3, 7, 8) ----
        tin_2 = (
            "PHIẾU S4 lượt 2. Gọi công cụ Agent ĐÚNG HAI LẦN, LẦN LƯỢT (chờ lần 1 xong mới gọi lần 2), đều chạy "
            "foreground (KHÔNG đặt run_in_background), subagent_type general-purpose:\n"
            f"Lần 1: description \"S4 con cong cu\", prompt: \"Làm đúng 3 bước, mỗi bước gọi công cụ ĐÚNG MỘT LẦN: "
            f"(a) Read file {file_doc.as_posix()}; (b) WebFetch url {URL_WEBFETCH_S4} với prompt 'tiêu đề trang'; "
            f"(c) Bash lệnh: python -c \\\"print('{DAU_CON_BASH_S4}')\\\". Bước nào bị từ chối hoặc không có công cụ thì "
            "ghi nguyên văn lỗi, KHÔNG thử cách khác. Trả lời: dòng đầu " + DAU_CON_S4 + "; rồi kết quả từng bước; "
            "rồi dòng CONG_CU_CUA_TOI: <tên chính xác mọi công cụ bạn có, cách nhau dấu phẩy>.\"\n"
            f"Lần 2: description \"S4 con long\", prompt: \"Gọi công cụ Agent ĐÚNG MỘT LẦN (foreground) với "
            f"subagent_type general-purpose, prompt 'Trả lời đúng một dòng: {DAU_CHAU_S4}. Không dùng công cụ nào.' "
            f"Rồi trả lời: dòng đầu {DAU_CON2_S4}; dòng hai là nguyên văn kết quả agent đó trả về, hoặc lỗi nguyên "
            "văn nếu không gọi được Agent. Không thử cách khác.\"\n"
            "Xong hai lần thì trả lời ngắn: nguyên văn hai kết quả. Không gọi công cụ nào khác.\n")
        log("S4 lượt 2: subagent (Read, WebFetch, Bash) + subagent gọi Agent lồng")
        mu_truoc = tom_model_usage(next((e for e in reversed(sk1) if e.get("type") == "result"), {}) or {})
        i2, co_r2 = _gui_va_cho(phien, "luot2", tin_2, HET_GIO_LUOT_S4)
        phien.cho_ranh(120)
        sk2 = phien.chup()[i2:]
        txt2 = _van_ban_result(sk2)
        cc2 = cong_cu_chi_tiet(sk2)
        agent_cap_cao = [c for c in cc2 if c["ten"] in ("Agent", "Task") and not c.get("cha")]
        id_cap_cao = [c["id"] for c in agent_cap_cao if c.get("id")]
        cong_cu_con = [c for c in cc2 if c.get("cha")]
        ten_con = sorted({str(c["ten"]) for c in cong_cu_con})
        out["luot2"] = {"agent_cap_cao": [{"id": c["id"], "ten": c["ten"], "nen": c.get("nen"), "loi": c.get("loi"),
                                           "ket_qua_dau": (c.get("ket_qua_dau") or "")[:400]} for c in agent_cap_cao],
                        "cong_cu_subagent": [{"ten": c["ten"], "cha": c["cha"], "loi": c.get("loi"),
                                              "input_dau": c["input_dau"][:200],
                                              "ket_qua_dau": (c.get("ket_qua_dau") or "")[:300]} for c in cong_cu_con],
                        "van_ban_dau": txt2[:1500]}
        wf = [c for c in cong_cu_con if c["ten"] == "WebFetch"]
        den2 = [d.get("tool_name") for e in sk2 if e.get("type") == "result"
                for d in (e.get("permission_denials") or []) if isinstance(d, dict)]
        if not wf:
            trang_thai_wf = "khong_goi"
        elif any(c.get("loi") is False for c in wf) and "WebFetch" not in den2:
            trang_thai_wf = "chay_duoc"
        else:
            trang_thai_wf = "bi_chan"
        read_con = [c for c in cong_cu_con if c["ten"] == "Read"]
        bash_con = [c for c in cong_cu_con if c["ten"] == "Bash"]
        m_cc = re.search(r"CONG_CU_CUA_TOI:\s*(.+)", "\n".join([txt2] + [c.get("ket_qua_dau") or "" for c in agent_cap_cao]))
        thay_con = bool(cong_cu_con)
        muc["s2_subagent_cong_cu"].update(
            dat=(thay_con and trang_thai_wf != "chay_duoc") if co_r2 else None,
            ket_luan={"tool_use_subagent_tren_stdout": thay_con, "webfetch": trang_thai_wf,
                      "ten_cong_cu_subagent_phat": ten_con},
            ghi_chu=f"số tool_use có parent_tool_use_id: {len(cong_cu_con)}; WebFetch: "
                    f"{[(c['loi'], (c.get('ket_qua_dau') or '')[:200]) for c in wf]}; permission_denials lượt 2: {den2}; "
                    f"Read con: {[(c['loi'], MA_DOC_S4 in (c.get('ket_qua_dau') or '')) for c in read_con]}; "
                    f"Bash con: {[(c['loi'], DAU_CON_BASH_S4 in (c.get('ket_qua_dau') or '')) for c in bash_con]}; "
                    f"subagent tự khai công cụ: {m_cc.group(1)[:400] if m_cc else None}")
        long = [c for c in cong_cu_con if c["ten"] in ("Agent", "Task")]
        chau_ok = any(not c.get("loi") and DAU_CHAU_S4 in (c.get("ket_qua_dau") or "") for c in long)
        muc["s3_agent_long"].update(
            dat=chau_ok if co_r2 else None,
            ghi_chu=f"tool_use Agent/Task cấp con: {[(c['ten'], c['cha'], c['loi'], (c.get('ket_qua_dau') or '')[:200]) for c in long]}; "
                    f"có {DAU_CHAU_S4} trong kết quả: {chau_ok}; trong văn bản cuối: {DAU_CHAU_S4 in txt2}")
        r2 = next((e for e in reversed(sk2) if e.get("type") == "result"), None)
        mu_sau = tom_model_usage(r2 or {})
        u2 = usage_theo_cap(sk2)
        dg7 = danh_gia_chi_phi_subagent(mu_truoc["tong_token"] if mu_truoc["co_modelUsage"] else None,
                                         mu_sau["tong_token"], u2)
        r1 = next((e for e in reversed(sk1) if e.get("type") == "result"), None)
        c1, c2 = (r1 or {}).get("total_cost_usd"), (r2 or {}).get("total_cost_usd")
        muc["s7_chi_phi_gom_subagent"].update(
            dat=dg7["gom_subagent"] if co_r2 else None,
            ghi_chu=f"{dg7}; modelUsage trước: {mu_truoc}; sau: {mu_sau}; total_cost_usd lượt 1={c1}, lượt 2={c2}; "
                    f"total_cost_usd lượt 2 ≈ Σ costUSD modelUsage: "
                    f"{isinstance(c2, (int, float)) and mu_sau['tong_cost'] is not None and abs(c2 - mu_sau['tong_cost']) < 1e-6}")

        # ---- lượt 3: tin chen giữa Bash foreground (mục 4) ----
        phien.cho_ranh(60)
        tin_3 = (
            f"PHIẾU S4 lượt 3. Gọi công cụ Bash ĐÚNG MỘT LẦN, foreground (KHÔNG run_in_background), lệnh:\n"
            f"python -c \"import time; time.sleep({NGU_FOREGROUND_S}); print('{DAU_BASH_20}')\"\n"
            "Rồi trả lời một dòng BASH: <output lệnh>. Nếu trong lúc đó có tin mới của người dùng thì làm theo tin đó luôn.\n")
        tin_chen = (f"TIN CHÈN (gửi khi bạn đang chạy Bash): trong câu trả lời kế tiếp của bạn hãy có thêm dòng "
                    f"DA_THAY_TIN_CHEN: {DAU_CHEN}. Không dùng công cụ vì tin này.\n")
        log(f"S4 lượt 3: Bash foreground {NGU_FOREGROUND_S}s, chen tin giữa lúc chạy")
        i3 = len(phien.chup())
        r_truoc = phien.so_result()
        phien.gui("luot3", tin_3)
        id_bash = None
        han = time.monotonic() + 180
        while time.monotonic() < han and phien.song() and id_bash is None:
            cc3 = cong_cu_chi_tiet(phien.chup()[i3:])
            b = next((c for c in cc3 if c["ten"] == "Bash" and not c.get("cha")), None)
            if b:
                id_bash = b["id"]
                break
            if phien.so_result() > r_truoc:
                break
            time.sleep(0.5)
        chen: dict = {"id_bash": id_bash, "da_gui": False}
        if id_bash:
            time.sleep(3)
            b = next((c for c in cong_cu_chi_tiet(phien.chup()[i3:]) if c["id"] == id_bash), {})
            chen["bash_xong_truoc_khi_chen"] = b.get("t_ket_qua_s") is not None
            chen["t_gui_s"] = round(phien.t(), 2)
            chen["da_gui"] = phien.gui("chen", tin_chen)
        phien.cho_result_moi(r_truoc, HET_GIO_LUOT_S4)
        if chen["da_gui"]:
            phien.cho_result_moi(r_truoc + 1, CHO_RESULT_THEM_S)
        phien.cho_ranh(60)
        sk3 = phien.chup()[i3:]
        pl4 = phan_loai_chen(sk3, id_bash, DAU_CHEN, DAU_BASH_20)
        chen.update(pl4)
        chen["su_kien_user_sau_khi_chen"] = [
            {"t_s": e.get("__t"), "noi_dung_dau": json.dumps((e.get("message") or {}).get("content"), ensure_ascii=False)[:200]}
            for e in sk3 if e.get("type") == "user" and chen.get("t_gui_s") is not None
            and (e.get("__t") or 0) >= chen["t_gui_s"]
            and not any(isinstance(c, dict) and c.get("type") == "tool_result"
                        for c in ((e.get("message") or {}).get("content") or []) if isinstance(c, dict))][:5]
        chen["results"] = [tom_tat_result(e) for e in sk3 if e.get("type") == "result"]
        out["chen_giua_luot"] = chen
        muc["s4_tin_giua_luot"].update(
            dat=(pl4["kieu"] is not None and pl4["luot_hong"] is False) if chen["da_gui"] else None,
            ket_luan=pl4["kieu"],
            ghi_chu=f"gửi chèn lúc {chen.get('t_gui_s')}s; Bash xong trước khi chèn: {chen.get('bash_xong_truoc_khi_chen')}; "
                    f"Bash xong lúc {pl4['t_bash_xong_s']}s; số result: {pl4['so_result']}; result có dấu chèn: "
                    f"{pl4['result_co_dau_chen']}; result đầu có dấu bash: {pl4['result_dau_co_dau_bash']}; "
                    f"nhắc chèn trước khi Bash xong: {pl4['nhac_chen_truoc_khi_bash_xong']}; lượt hỏng: {pl4['luot_hong']}"
                    + ("" if id_bash else "; KHÔNG thấy tool_use Bash cấp cao -> không chèn"))

        # ---- im lặng dài (mục 6) ----
        phien.cho_ranh(60)
        i_im = len(phien.chup())
        t_bd_im = phien.t()
        log(f"S4: im lặng {cho_dai_s}s với stdin mở (mục 6)")
        han = time.monotonic() + cho_dai_s
        mau_song: list[tuple[float, bool]] = []
        while time.monotonic() < han and phien.song():
            time.sleep(min(30.0, max(0.0, han - time.monotonic())))
            mau_song.append((round(phien.t(), 1), phien.song()))
        song_sau_im = phien.song()
        sk_im = phien.chup()[i_im:]
        tin_5 = (f"PHIẾU S4 lượt cuối (sau {cho_dai_s}s im lặng). Không dùng công cụ. Trả lời đúng một dòng: "
                 "XAC_NHAN_S4: <từ khoá kiểm thử ghi nhớ ở lượt 1>\n")
        txt5, co_r5, r5 = "", False, None
        if song_sau_im:
            log("S4 lượt cuối: hỏi lại từ khoá")
            i5, co_r5 = _gui_va_cho(phien, "luot_cuoi", tin_5, HET_GIO_LUOT_S4)
            sk5 = phien.chup()[i5:]
            txt5 = _van_ban_result(sk5)
            r5 = next((e for e in reversed(sk5) if e.get("type") == "result"), None)
        loai_im = sorted({f"{e.get('type')}/{e.get('subtype')}" for e in sk_im})
        muc["s6_im_lang_dai"].update(
            dat=(song_sau_im and co_r5 and not (r5 or {}).get("is_error") and TU_KHOA_S4 in txt5),
            ghi_chu=f"im lặng {t_bd_im:.1f}s -> {phien.t():.1f}s; sống sau im lặng: {song_sau_im}; mã thoát nếu chết: "
                    f"{phien.p.returncode if phien.p else None}; sự kiện trong lúc im lặng ({len(sk_im)}): {loai_im}; "
                    f"lượt cuối có result: {co_r5}, is_error: {(r5 or {}).get('is_error')}, subtype: {(r5 or {}).get('subtype')}, "
                    f"duration_ms: {(r5 or {}).get('duration_ms')}; nhắc đúng từ khoá: {TU_KHOA_S4 in txt5}; "
                    f"mẫu sống (mỗi 30s, 3 mẫu cuối): {mau_song[-3:]}")
        out["van_ban_luot_cuoi_dau"] = txt5[:400]

        # ---- đóng stdin ----
        phien.cho_ranh(30)
        song_truoc_dong = phien.song()
        phien.dong_stdin()
        thoat, giay = phien.cho_thoat(CHO_THOAT_SAU_DONG_STDIN_S)
        out["dong_stdin"] = {"song_truoc_dong": song_truoc_dong, "thoat_trong_han": thoat, "giay": giay,
                             "ma_thoat": phien.p.returncode if phien.p else None}

        # ---- mục 8 trên cả luồng ----
        sk_all = phien.chup()
        bg = [c["id"] for c in cong_cu_chi_tiet(sk_all) if c["ten"] in ("Agent", "Task") and c.get("id") and not c.get("nen")]
        tk = tom_su_kien_task(sk_all, bg)
        out["su_kien_task"] = tk
        muc["s8_su_kien_task"].update(
            dat=True if (tk["task_notification_status"] or tk["task_updated_patch_khoa"] or tk["task_started"]) else None,
            ket_luan={"agent_foreground_co_task_started": tk["agent_foreground_co_task_started"]},
            ghi_chu=f"task_notification.status: {tk['task_notification_status']}; task_updated.patch khoá: "
                    f"{tk['task_updated_patch_khoa']}; số task_started: {len(tk['task_started'])}; "
                    f"Agent foreground (id) có task_started: {tk['agent_foreground_co_task_started']}")
        dg = danh_gia_chi_phi([e.get("total_cost_usd") for e in sk_all if e.get("type") == "result"])
        out["chi_phi_danh_gia_chinh"] = dg
    finally:
        tru_hard.cancel()
        _giet_het()  # giết mọi tiến trình còn sống TRƯỚC khi ghi log (ghi log lỗi cũng không để sót tiến trình)
        for ten, p in ds_phien.items():
            try:
                _ghi_phien(out, p, ten, thu_muc_log)
            except Exception as ex:  # noqa: BLE001
                out.setdefault("loi_ghi_phien", {})[ten] = f"{type(ex).__name__}: {ex}"[:300]
        _dong_goi(out, tam, lam_viec, giu_tam, t_bat_dau)
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
    ds_muc_nen = "\n".join(f"  {k}: {v}" for k, v in MO_TA_MUC_NEN.items())
    ds_muc_song = "\n".join(f"  {k}: {v}" for k, v in MO_TA_MUC_SONG.items())
    ds_muc_s4 = "\n".join(f"  {k}: {v}" for k, v in MO_TA_MUC_S4.items())
    ap = argparse.ArgumentParser(
        prog="spike_claude.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Spike S-1..S-4: đo hành vi claude.exe headless (-p, stream-json, dontAsk, --tools, --resume,\n"
            "việc nền) cho bộ chạy việc Kho sản phẩm. KHÔNG cờ = chỉ in trợ giúp, không gọi gì.\n\n"
            "Kịch bản 'cu' (mặc định, S-1). Các mục đo (dat = true | false | null(không kết luận) | QUAN_SAT_TAY):\n"
            + ds_muc + "\n\n"
            "Kịch bản 'nen' (S-2): agent nội tuyến có Agent, SendMessage, Bash (--strict-mcp-config,\n"
            "dontAsk, --allowedTools đúng 3 công cụ; --tools thêm tên thăm dò "
            + ",".join(CONG_CU_THAM_DO) + ").\n"
            "Lượt 1 gọi 1 subagent general-purpose + 1 Bash nền ngủ 60s rồi kết thúc; lượt 2 --resume hỏi\n"
            "trạng thái việc nền và thử SendMessage tới subagent cũ. Các mục đo:\n" + ds_muc_nen + "\n\n"
            "Kịch bản 'song' (S-3): MỘT tiến trình claude -p --input-format stream-json --output-format\n"
            "stream-json --verbose sống suốt việc; tin user gửi qua stdin dạng JSON lines\n"
            '  {"type":"user","message":{"role":"user","content":"..."},"parent_tool_use_id":null}\n'
            "không đóng stdin giữa các lượt. Agent nội tuyến có " + ",".join(CONG_CU_SONG) + "\n"
            "(--strict-mcp-config, dontAsk, env tối thiểu, thư mục tạm; --tools thêm tên thăm dò "
            + ",".join(CONG_CU_THAM_DO_SONG) + ").\n"
            f"Lượt 1: 1 subagent + 1 Bash nền ngủ {NGU_NEN_S2}s rồi kết thúc lượt; runner im lặng tới mốc gọi nền\n"
            f"+{CHO_QUAN_SAT_SONG_S}s; lượt 2 hỏi trạng thái + SendMessage + kết thúc bằng khối CẦN_USER (LOẠI: chon);\n"
            "lượt 3 gửi câu trả lời; rồi đóng stdin. Các mục đo:\n" + ds_muc_song + "\n\n"
            "Kịch bản 'song2' (S-4): cùng dạng lệnh §7.2 (stream-json vào/ra, --strict-mcp-config, dontAsk,\n"
            "--tools = --allowedTools = " + ",".join(CONG_CU_S4) + ",\n"
            f"--max-budget-usd {TRAN_USD_CHINH_S4}, --session-id mới), agent nội tuyến, cwd tạm có skill tạm\n"
            f".claude/skills/{TEN_SKILL_S4}/SKILL.md. Tiến trình NGÂN SÁCH (--max-budget-usd {TRAN_NGAN_SACH_S4}, "
            "--tools Read, tối đa 3 lượt)\n"
            "chạy trước; rồi tiến trình CHÍNH: lượt 1 Skill; lượt 2 hai subagent foreground (Read+WebFetch+Bash;\n"
            f"Agent lồng); lượt 3 Bash foreground {NGU_FOREGROUND_S}s + chèn tin giữa lúc chạy; im lặng --cho-dai giây;\n"
            "lượt cuối hỏi lại từ khoá; đóng stdin. Các mục đo:\n" + ds_muc_s4),
        epilog=(
            "Tác động khi --chay (cu): gọi claude.exe THẬT 6-8 lượt (A, B resume, C, [C2], D, E, F, [A2]),\n"
            "tốn quota; tạo 5-7 phiên trong C:\\Users\\Mi\\.claude\\projects\\<mã cwd tạm>\\;\n"
            "thư mục tạm %TEMP%\\spike_claude_* (xoá cuối lượt trừ khi --giu-tam).\n"
            "Mục 9 cần người ngồi nhìn màn hình; script in hướng dẫn ra stderr và chờ trước bước D.\n"
            "Tác động khi --chay --kich-ban nen: 2 lượt claude.exe THẬT (+1 nếu lượt 1 không khởi động\n"
            "được với tên thăm dò), 1 subagent, ~0,5 USD; chạy ~3-5 phút (chờ việc nền 60s + 20s);\n"
            "1 phiên (kèm file subagent) trong C:\\Users\\Mi\\.claude\\projects\\<mã cwd tạm>\\;\n"
            "thư mục tạm %TEMP%\\spike_claude_nen_*; tiến trình nền còn sót bị taskkill cuối lượt.\n"
            "Tác động khi --chay --kich-ban song: 1 tiến trình claude.exe THẬT, 3 tin user (+ lượt tự thức\n"
            "nếu có), 1 subagent (+1 SendMessage nếu có), ước ~0,3-0,8 USD; chạy ~3-6 phút (trần cứng\n"
            f"{TONG_HET_GIO_SONG_S}s rồi taskkill); 1 phiên trong C:\\Users\\Mi\\.claude\\projects\\<mã cwd tạm>\\;\n"
            "thư mục tạm %TEMP%\\spike_claude_song_* (có _log/S_song.jsonl nếu --giu-tam).\n"
            "Tác động khi --chay --kich-ban song2: 2 tiến trình claude.exe THẬT (ngân sách tối đa 3 lượt; chính 4 lượt\n"
            "+ 1 tin chèn), 3 subagent (1 gọi WebFetch tới https://example.com nếu không bị chặn), ước ~0,6-1,0 USD;\n"
            f"chạy ~--cho-dai + 5 phút (mặc định ~35 phút; trần cứng --cho-dai + {TRAN_CUNG_THEM_S4}s rồi taskkill);\n"
            "2 phiên (kèm file subagent) trong C:\\Users\\Mi\\.claude\\projects\\<mã cwd tạm>\\;\n"
            "thư mục tạm %TEMP%\\spike_claude_s4_* (có _log/S4_*.jsonl nếu --giu-tam).\n"
            "Hoàn tác: xoá thư mục phiên in trong khoá thu_muc_phien và thư mục tạm (nếu --giu-tam)."),
    )
    ap.add_argument("--chay", action="store_true", help="chạy các phép đo bằng claude.exe thật (cần duyệt)")
    ap.add_argument("--kich-ban", choices=["cu", "nen", "song", "song2"], default="cu",
                    help="cu = 12 mục S-1 (mặc định, hành vi cũ); nen = việc nền S-2; "
                         "song = một tiến trình stream-json sống nhiều lượt S-3; "
                         "song2 = phiên sống, phần còn thiếu S-4 (8 mục)")
    ap.add_argument("--claude-exe", default=os.environ.get("KHO_CLAUDE_EXE", CLAUDE_EXE_MAC_DINH),
                    help="đường dẫn claude.exe (mặc định §6.1, ghi đè bằng env KHO_CLAUDE_EXE)")
    ap.add_argument("--model", default=None, help="tuỳ chọn --model truyền cho claude (mặc định: không truyền)")
    ap.add_argument("--giu-tam", action="store_true", help="giữ thư mục tạm (có _log/*.jsonl thô) để soi lại")
    ap.add_argument("--cho-quan-sat", type=int, default=8,
                    help="số giây chờ sau khi in hướng dẫn quan sát mục 9 (mặc định 8)")
    ap.add_argument("--cho-dai", type=int, default=CHO_DAI_MAC_DINH_S,
                    help=f"song2: số giây im lặng với stdin mở trước lượt cuối (mục s6; mặc định {CHO_DAI_MAC_DINH_S})")
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
    if ns.kich_ban == "nen":
        out = chay_spike_nen(ns.claude_exe, ns.giu_tam, ns.model)
    elif ns.kich_ban == "song":
        out = chay_spike_song(ns.claude_exe, ns.giu_tam, ns.model)
    elif ns.kich_ban == "song2":
        out = chay_spike_song2(ns.claude_exe, ns.giu_tam, ns.model, max(0, ns.cho_dai))
    else:
        out = chay_spike(ns.claude_exe, ns.giu_tam, ns.model, max(0, ns.cho_quan_sat))
    print(json.dumps(che_de_quy(out, che), ensure_ascii=False, indent=2))
    return 0 if out.get("claude_exe_ton_tai") else 2


if __name__ == "__main__":
    sys.exit(main())
