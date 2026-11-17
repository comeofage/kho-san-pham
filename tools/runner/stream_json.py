"""Đọc sự kiện stream-json của `claude -p --output-format stream-json --verbose` (§6.2).

MỌI chỗ đọc tên trường của stream-json nằm trong file này. Phần còn lại của runner
chỉ gọi các hàm dưới đây, nên khi spike S-01 cho thấy tên trường khác thì chỉ sửa ở đây
(và fixture trong tools/test_runner_stream_json.py).

Tên trường ĐÃ được spike S-1 xác nhận (chạy thật, A-2 cập nhật):
- type=="system" and subtype=="init"  -> session_id, tools, permissionMode, model, apiKeySource,
                                         agents, mcp_servers. init.session_id == --session-id.
- type=="assistant"                   -> message (message.id, message.content[] gồm text /
                                         tool_use{name,input}), parent_tool_use_id, error
- type=="result"                      -> subtype, is_error, session_id (== init), total_cost_usd,
                                         num_turns, duration_ms, result, permission_denials;
                                         subtype "error_*" cũng coi là lỗi.
Chưa xác nhận: type=="user" -> message.content[] gồm tool_result{content,is_error} (chỉ dùng cho log).
total_cost_usd = 0 ở lần S-1 lỗi đăng nhập — chưa kết luận có đúng khi đi qua proxy (§6.3 chốt 1).

S-1 cũng cho thấy `--tools` KHÔNG loại công cụ MCP của người dùng (mcp__*): runner soát MỌI sự kiện
bằng `SoatCongCu` (init.tools/mcp_servers, tool_use của mọi assistant, assistant trước init) và dừng
phiên nếu có vi phạm (R-05 P2-1).

Lưu ý đếm lượt: Claude Code có thể phát NHIỀU sự kiện assistant cho cùng một message
(mỗi khối content một sự kiện, cùng message.id). `dem_luot` không giữ trạng thái; bên gọi
khử trùng theo `ma_message`.
"""
from __future__ import annotations

import json
from typing import Callable

_CAT_INPUT = 300      # ký tự tối đa khi in input công cụ
_CAT_VAN_BAN = 2000   # ký tự tối đa khi in văn bản agent
_CAT_KET_QUA = 300    # ký tự tối đa khi in kết quả công cụ


def doc_su_kien(dong: str) -> dict | None:
    """json.loads an toàn. None nếu dòng rỗng, không phải JSON, hoặc JSON không phải object."""
    if not isinstance(dong, str):
        return None
    s = dong.strip()
    if not s or s[0] != "{":
        return None
    try:
        sk = json.loads(s)
    except ValueError:
        return None
    return sk if isinstance(sk, dict) else None


def _chuoi(x) -> str | None:
    return x if isinstance(x, str) and x else None


def _noi_dung(sk: dict) -> list:
    """message.content dạng list các dict; mọi dạng khác → []."""
    msg = sk.get("message")
    if not isinstance(msg, dict):
        return []
    c = msg.get("content")
    if not isinstance(c, list):
        return []
    return [k for k in c if isinstance(k, dict)]


def la_khoi_tao(sk: dict) -> str | None:
    """session_id nếu là sự kiện init."""
    if sk.get("type") == "system" and sk.get("subtype") == "init":
        return _chuoi(sk.get("session_id"))
    return None


def _ds_chuoi(x) -> list[str]:
    return [v for v in x if isinstance(v, str) and v] if isinstance(x, list) else []


def _ten_mcp(x) -> list[str]:
    """mcp_servers: list các {name, status} (hoặc chuỗi) → tên server."""
    if not isinstance(x, list):
        return []
    ra = []
    for v in x:
        if isinstance(v, dict) and _chuoi(v.get("name")):
            ra.append(v["name"])
        elif _chuoi(v):
            ra.append(v)
    return ra


def thong_tin_khoi_tao(sk: dict) -> dict | None:
    """{session_id, cong_cu, che_do_quyen, model, nguon_khoa, mcp} nếu là sự kiện init."""
    sid = la_khoi_tao(sk)
    if sid is None:
        return None
    return {"session_id": sid, "cong_cu": _ds_chuoi(sk.get("tools")),
            "che_do_quyen": _chuoi(sk.get("permissionMode")), "model": _chuoi(sk.get("model")),
            "nguon_khoa": _chuoi(sk.get("apiKeySource")), "mcp": _ten_mcp(sk.get("mcp_servers"))}


def _la_init(sk: dict) -> bool:
    """Sự kiện init, KHÔNG đòi session_id (soát công cụ phải bắt cả init thiếu session_id)."""
    return sk.get("type") == "system" and sk.get("subtype") == "init"


def cong_cu_ngoai(sk: dict, cho_phep) -> list[str]:
    """Vi phạm bộ công cụ trong MỘT sự kiện (không giữ trạng thái; thứ tự init xem `SoatCongCu`).

    - init (có hay không session_id): `tools` thiếu / không phải list / có phần tử không phải chuỗi khác rỗng
      → một mục mô tả lỗi (không biết bộ công cụ thật = không an toàn). Ngược lại: công cụ ngoài `cho_phep`;
      MCP server được báo kết nối cũng tính (dạng 'mcp:<tên>') khi `tools` không liệt kê công cụ mcp__ nào.
    - assistant: tên mọi tool_use ngoài `cho_phep`.
    """
    cp = set(cho_phep)
    if _la_init(sk):
        tools = sk.get("tools")
        if not isinstance(tools, list) or not all(isinstance(t, str) and t for t in tools):
            return [f"init: trường tools thiếu hoặc sai dạng ({_cat(repr(tools), 80)})"]
        ra = [t for t in tools if t not in cp]
        if not any(t.startswith("mcp__") for t in tools):
            ra += [f"mcp:{m}" for m in _ten_mcp(sk.get("mcp_servers"))]
        return ra
    return _khoi_cong_cu_ngoai(sk, cp)


def _khoi_cong_cu_ngoai(sk: dict, cp: set) -> list[str]:
    """FX-4 P3-3/R-06 P3-2: MỌI khối có `type` kết thúc bằng "tool_use" (tool_use, server_tool_use, mcp_tool_use…)
    trong sự kiện assistant. Tên không phải chuỗi khác rỗng, hoặc ngoài `cp` → vi phạm."""
    if sk.get("type") != "assistant":
        return []
    ra = []
    for k in _noi_dung(sk):
        loai = k.get("type")
        if not (isinstance(loai, str) and loai.endswith("tool_use")):
            continue
        ten = k.get("name")
        if not _chuoi(ten):
            ra.append(f"{_cat(loai, 40)}: tên công cụ không hợp lệ ({_cat(repr(ten), 60)})")
        elif ten not in cp:
            ra.append(ten if loai == "tool_use" else f"{_cat(loai, 40)}:{ten}")
    return ra


class SoatCongCu:
    """Soát bộ công cụ suốt một lượt chạy Claude (P2-1, R-05). Mỗi lượt tạo một đối tượng mới.

    `xet(sk)` trả danh sách vi phạm (rỗng = ổn); bên gọi thấy vi phạm thì giết phiên:
    (a) init thiếu/sai dạng `tools`, hoặc có công cụ ngoài danh sách (kể cả init không có session_id);
    (b) tool_use của MỌI sự kiện assistant (kể cả của subagent) ngoài danh sách;
    (c) sự kiện assistant xuất hiện trước khi thấy init (không biết phiên đang có công cụ gì).
    """

    def __init__(self, cho_phep):
        self.cho_phep = frozenset(cho_phep)
        self.da_thay_init = False

    def xet(self, sk: dict) -> list[str]:
        if not isinstance(sk, dict):
            return []
        if _la_init(sk):
            self.da_thay_init = True
        elif sk.get("type") == "assistant" and not self.da_thay_init:
            return ["sự kiện assistant xuất hiện trước sự kiện init (không biết bộ công cụ của phiên)"]
        return cong_cu_ngoai(sk, self.cho_phep)


def loi_assistant(sk: dict) -> str | None:
    """Trường `error` của sự kiện assistant (vd lỗi đăng nhập/quota); None nếu không có."""
    if sk.get("type") != "assistant":
        return None
    e = sk.get("error")
    if e is None or e == "" or e is False:
        return None
    if isinstance(e, str):
        return e
    try:
        return json.dumps(e, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(e)


def la_ket_qua(sk: dict) -> dict | None:
    """{session_id, chi_phi_usd, so_luot, loi: bool, van_ban, bi_tu_choi: list} nếu là sự kiện result."""
    if sk.get("type") != "result":
        return None
    chi_phi = sk.get("total_cost_usd")
    so_luot = sk.get("num_turns")
    tu_choi = sk.get("permission_denials")
    subtype = sk.get("subtype")
    return {
        "session_id": _chuoi(sk.get("session_id")),
        "chi_phi_usd": float(chi_phi) if isinstance(chi_phi, (int, float)) and not isinstance(chi_phi, bool) else 0.0,
        "so_luot": int(so_luot) if isinstance(so_luot, int) and not isinstance(so_luot, bool) else 0,
        "loi": bool(sk.get("is_error") is True or (isinstance(subtype, str) and subtype.startswith("error"))),
        "van_ban": sk.get("result") if isinstance(sk.get("result"), str) else "",
        "bi_tu_choi": list(tu_choi) if isinstance(tu_choi, list) else [],
    }


def ma_message(sk: dict) -> str | None:
    """message.id của sự kiện assistant (để khử trùng khi đếm lượt)."""
    if sk.get("type") != "assistant":
        return None
    msg = sk.get("message")
    return _chuoi(msg.get("id")) if isinstance(msg, dict) else None


def dem_luot(sk: dict) -> int:
    """1 nếu là sự kiện message assistant, ngược lại 0. Bên gọi khử trùng theo ma_message."""
    return 1 if sk.get("type") == "assistant" and isinstance(sk.get("message"), dict) else 0


def ten_cong_cu(sk: dict) -> list[tuple[str, dict]]:
    """Các tool_use (tên, input) trong sự kiện assistant."""
    if sk.get("type") != "assistant":
        return []
    ra = []
    for k in _noi_dung(sk):
        if k.get("type") == "tool_use" and _chuoi(k.get("name")):
            inp = k.get("input")
            ra.append((k["name"], inp if isinstance(inp, dict) else {}))
    return ra


def van_ban_assistant(sk: dict) -> str | None:
    """Các khối text của sự kiện assistant nối lại; None nếu không có."""
    if sk.get("type") != "assistant":
        return None
    phan = [k["text"] for k in _noi_dung(sk) if k.get("type") == "text" and isinstance(k.get("text"), str)]
    s = "\n".join(phan).strip()
    return s or None


def _cat(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + f"… (+{len(s) - n} ký tự)"


def _khong_che(s: str) -> str:
    return s


def _tom_input(inp: dict, che: Callable[[str], str] = _khong_che) -> str:
    try:
        s = json.dumps(inp, ensure_ascii=False)
    except (TypeError, ValueError):
        s = repr(inp)
    return _cat(che(s), _CAT_INPUT)


def _chu_ket_qua_cong_cu(c) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(k["text"] for k in c if isinstance(k, dict) and isinstance(k.get("text"), str))
    return ""


def dich_dong(sk: dict, che: Callable[[str], str] | None = None) -> str | None:
    """Dòng log cho người đọc; None nếu sự kiện không đáng ghi.

    `che` (R-07 P2-2): hàm che bí mật áp lên văn bản ĐẦY ĐỦ trước khi cắt (input công cụ 300, văn bản agent 2000,
    kết quả/lỗi 300). Che sau khi cắt không cứu được bí mật đã bị cắt dở. None = không che."""
    che = che or _khong_che
    t = sk.get("type")
    sid = la_khoi_tao(sk)
    if sid:
        model = _chuoi(sk.get("model")) or "?"
        return f"[khởi tạo] phiên {sid} · model {model}"
    if t == "assistant":
        dong = []
        loi = loi_assistant(sk)
        if loi:
            dong.append("[lỗi agent] " + _cat(che(loi), _CAT_KET_QUA))
        for k in _noi_dung(sk):
            if k.get("type") == "text" and isinstance(k.get("text"), str) and k["text"].strip():
                dong.append("[agent] " + _cat(che(k["text"].strip()), _CAT_VAN_BAN))
            elif k.get("type") == "tool_use" and _chuoi(k.get("name")):
                inp = k.get("input") if isinstance(k.get("input"), dict) else {}
                dong.append(f"[công cụ] {che(k['name'])} {_tom_input(inp, che)}")
        return "\n".join(dong) or None
    if t == "user":
        dong = []
        for k in _noi_dung(sk):
            if k.get("type") == "tool_result":
                nhan = "[lỗi công cụ]" if k.get("is_error") is True else "[kết quả công cụ]"
                dong.append(f"{nhan} {_cat(che(_chu_ket_qua_cong_cu(k.get('content')).strip()), _CAT_KET_QUA)}")
        return "\n".join(dong) or None
    kq = la_ket_qua(sk)
    if kq:
        tt = "LỖI" if kq["loi"] else "xong"
        them = f" · bị từ chối {len(kq['bi_tu_choi'])}" if kq["bi_tu_choi"] else ""
        return f"[kết thúc] {tt} · {kq['so_luot']} lượt · {kq['chi_phi_usd']:.4f} USD{them}"
    return None
