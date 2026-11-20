"""Chuyển tiếp /p/* của video_server sang backend TikTok Poster V2 (FastAPI 127.0.0.1:<TT_API_PORT|8023>).

Hợp đồng: docs/poster-v2-tren-web.md (§2 lọc path + hợp đồng body, §3 bảng lệnh/hạn giờ, §4.3–§4.4 header/token/
nhật ký, §5.1–§5.2 _video/_dem), quyết định D13. Chỉ dùng stdlib.

  /p/api/v2/<...>, /p/health   GET|POST|PUT|PATCH|DELETE → backend (gắn Bearer token đọc LÚC GỌI)
  GET  /p/_kq                  lệnh đang chạy     GET /p/_kq/<32 hex>  kết quả một lệnh
  GET  /p/_video/<folder_id>   video của folder   POST /p/_dem {"duong_dan"}  đếm video
  GET  /p/_thong_tin           backend/thư mục Poster (không bao giờ có token)
  POST /p/_bat_backend {}      bật backend Poster nếu cổng trống (cửa sổ console riêng ở máy nhà)

Luật an toàn (CL21): lệnh ghi KHÔNG BAO GIỜ tự gửi lại; khoá chống trùng giữ tới khi lệnh nền kết thúc;
backend 401 chỉ gọi lại với GET. Công tắc: env KHO_POSTER_WEB=0 → mọi /p/* trả 503.
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Callable

# ---------------------------------------------------------------- hằng (đọc qua module lúc gọi để test monkeypatch được)
HAN_CHO_DONG_BO = 80.0                          # giây chờ trong handler trước khi chuyển nền
HAN_NEN = {"S": 300.0, "L": 300.0, "DN": 360.0}  # hạn tổng của luồng nền
HAN_QUET_DIA = 30.0
HAN_KET_NOI = 5.0
HAN_DOC_BODY = 15.0                             # timeout socket khi đọc body từ Worker
CHO_CHAY = {"S": 6, "L": 1, "DN": 1}
BANG_TOI_DA = 50
GIU_KET_QUA = 15 * 60
BODY_TOI_DA = 256 * 1024
XA_TOI_DA = 1024 * 1024                         # body bị từ chối nhưng ≤ mức này thì đọc bỏ (client nhận được mã lỗi)
TRA_TOI_DA = 4 * 1024 * 1024
NHAT_KY_TOI_DA = 5 * 1024 * 1024
XOAY_CHO = (0.05, 0.1, 0.2)                     # giây chờ trước mỗi lần thử lại đổi tên nhật ký (NTFS khoá)
XOAY_NGHI = 60.0                                # đổi tên hỏng hẳn → không thử lại trong chừng này giây
QUERY_TOI_DA = 512
DUONG_DAN_TOI_DA = 400

POSTER_THAT = Path("E:/tool/tiktok_poster_v2")
# Python có đủ fastapi/selenium của Poster (start.bat dùng đúng bản này, không dùng "python" trong PATH).
PYTHON_POSTER = Path("C:/Users/Mi/AppData/Local/Programs/Python/Python312/python.exe")
HAN_BAT_LAI = 60.0                              # giây: vừa bật xong mà bấm nữa thì không mở thêm tiến trình
CONG_THAT = 8023
CONG_MAC_DINH = 8023

BANG_LOP: tuple[tuple[str, re.Pattern, str], ...] = (
    ("POST", re.compile(r"/api/v2/accounts/login_and_capture", re.ASCII), "DN"),   # §2.2 #14
    ("POST", re.compile(r"/api/v2/queue/\d{1,9}/post", re.ASCII), "L"),            # #29
    ("POST", re.compile(r"/api/v2/post/direct", re.ASCII), "L"),                   # #45
    ("POST", re.compile(r"/api/v2/queue/\d{1,9}/run", re.ASCII), "L"),             # #46
)

METHOD_CO_BODY = ("POST", "PUT", "PATCH")
METHODS = ("GET", "DELETE") + METHOD_CO_BODY
KHOA_DUONG_DAN = ("path", "video_path", "cookies_path", "chrome_profile_dir")
TU_BI_MAT = ("token", "api_key", "secret", "password")
DUOI_DS_VIDEO = ("*.mp4", "*.mov", "*.avi", "*.mkv", "*.webm")      # post.py:241
DUOI_DEM = (".mp4", ".mov", ".avi", ".webm")                        # folders.py:192
DUOI_DANG = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm"})    # B2

RE_PATH = re.compile(r"/api/v2/[A-Za-z0-9_.~\-/]{1,200}", re.ASCII)
RE_KQ = re.compile(r"/_kq/([0-9a-f]{32})", re.ASCII)
RE_VIDEO = re.compile(r"/_video/(\d{1,9})", re.ASCII)
RE_DIEU_KHIEN = re.compile(r"[\x00-\x1f\x7f]")
RE_O_DIA = re.compile(r"[A-Za-z]:[\\/]")
RE_BOI = re.compile(r"[^\w.@\-]", re.ASCII)

LOI_PATH = "Đường dẫn Poster không được phép"
LOI_TAT = "Poster trên web đang tắt ở máy nhà"
LOI_B1 = "Tên account không hợp lệ"
LOI_B2 = "Video không nằm trong thư mục của folder"
LOI_B3 = "Đường dẫn phải là thư mục/tệp trên ổ đĩa máy nhà (vd E:\\…), không nhận đường mạng"
LOI_CHUA_MO = "Poster V2 trên máy nhà chưa mở"
LOI_TOKEN = "Poster V2 từ chối token (TT_API_BEARER_TOKEN lệch)"
LOI_CONG_LA = "Cổng {port} đang bị {ai} chiếm, không phải Poster V2: tắt nó trên máy nhà rồi bấm bật lại"
LOI_KQ_MAT = "Không còn theo dõi được lệnh này (máy phát video vừa khởi động lại). Xem Logs/Queue."
LOI_BAN_DANG = "Đang có lệnh đăng/login khác chạy, chờ xong rồi thử lại"
LOI_BAN_S = "Poster V2 đang bận"
LOI_QUET = "Quét thư mục quá 30 s"
CO_THE_DA_CHAY = "Thao tác CÓ THỂ đã chạy: xem Logs/Queue trước khi bấm lại."


# ---------------------------------------------------------------- cấu hình (đọc MỖI lần gọi, chống đọc dữ liệu cũ)
def poster_dir() -> Path:
    return Path(os.environ.get("KHO_POSTER_DIR") or POSTER_THAT)


def _dang_test() -> bool:
    return "pytest" in sys.modules or os.environ.get("KHO_POSTER_TEST") == "1"


def chot_test(port: int, thu_muc: Path) -> None:
    """Đang chạy test mà trỏ vào cổng/thư mục Poster thật → ném lỗi, không mở kết nối."""
    if not _dang_test():
        return
    try:
        trung_thu_muc = Path(thu_muc).resolve() == POSTER_THAT.resolve()
    except OSError:
        trung_thu_muc = True  # không xác định được → coi như trùng (an toàn)
    if port == CONG_THAT or trung_thu_muc:
        raise RuntimeError("Test đang trỏ vào Poster V2 thật")


_CACHE_ENV: dict[tuple[str, int], dict[str, str]] = {}
_KHOA_CACHE = threading.Lock()


def _doc_env(f: Path, doc_lai: bool = False) -> dict[str, str]:
    """Đọc .env như _load_api_token (api_client.py:15-32): bỏ dòng trống/#, cắt nháy. Cache theo (đường dẫn, mtime)."""
    try:
        mtime = f.stat().st_mtime_ns
    except OSError:
        return {}
    khoa = (str(f), mtime)
    with _KHOA_CACHE:
        if not doc_lai and khoa in _CACHE_ENV:
            return _CACHE_ENV[khoa]
    kq: dict[str, str] = {}
    try:
        for dong in f.read_text(encoding="utf-8").splitlines():
            dong = dong.strip()
            if not dong or dong.startswith("#") or "=" not in dong:
                continue
            k, v = dong.split("=", 1)
            kq[k.strip()] = v.strip().strip('"').strip("'")
    except (OSError, UnicodeDecodeError) as e:
        print("POSTER ENV LOI", f, type(e).__name__, flush=True)
        return {}
    with _KHOA_CACHE:
        _CACHE_ENV.clear()
        _CACHE_ENV[khoa] = kq
    return kq


def cau_hinh(doc_lai: bool = False) -> tuple[str, int]:
    """(token, port). Env TT_API_* ưu tiên, rồi <poster_dir()>/.env. Gọi chot_test trước khi trả."""
    thu_muc = poster_dir()
    env = _doc_env(thu_muc / ".env", doc_lai)
    token = os.environ.get("TT_API_BEARER_TOKEN") or env.get("TT_API_BEARER_TOKEN", "")
    cong_chu = (os.environ.get("TT_API_PORT") or env.get("TT_API_PORT") or "").strip()
    port = int(cong_chu) if re.fullmatch(r"\d{1,5}", cong_chu, re.ASCII) and 0 < int(cong_chu) < 65536 else CONG_MAC_DINH
    chot_test(port, thu_muc)
    return token, port


# ---------------------------------------------------------------- lọc path / query / lớp
def kiem_path(path: str) -> bool:
    if path == "/health":
        return True
    if not RE_PATH.fullmatch(path) or "//" in path:
        return False
    return not any(d in (".", "..") for d in path.split("/"))


def kiem_query(query: str) -> bool:
    return len(query) <= QUERY_TOI_DA and "#" not in query and not RE_DIEU_KHIEN.search(query)


def lop_cua(method: str, path: str) -> str:
    for m, mau, lop in BANG_LOP:
        if m == method and mau.fullmatch(path):
            return lop
    return "S"


# ---------------------------------------------------------------- body (§2.1)
def _do_dai(h) -> int | None:
    cl = h.headers.get("content-length")
    if cl is None:
        return 0
    return int(cl) if re.fullmatch(r"\d{1,12}", cl.strip(), re.ASCII) else None


def _xa_body(h) -> None:
    """Body chưa đọc (≤ 1 MB) thì đọc bỏ, để client nhận được mã lỗi thay vì bị RST."""
    if getattr(h, "_pv_da_doc", False):
        return
    h._pv_da_doc = True
    n = _do_dai(h)
    if n and n <= XA_TOI_DA and not h.headers.get("transfer-encoding"):
        try:
            h.rfile.read(n)
        except OSError:
            pass


def doc_body(h, method: str) -> tuple[bytes | None, object | None] | tuple[int, str]:
    """Hợp đồng §2.1 → (byte, obj) hoặc (status, câu lỗi)."""
    if method not in METHOD_CO_BODY:
        n = _do_dai(h)
        if h.headers.get("transfer-encoding") or n is None or n > 0:
            return 400, "GET/DELETE không nhận body"
        h._pv_da_doc = True
        return None, None
    ct = (h.headers.get("content-type") or "").strip().lower()
    if not ct.startswith("application/json"):
        return 415, "Chỉ nhận application/json"
    if h.headers.get("transfer-encoding"):
        return 411, "Cần content-length"
    n = _do_dai(h)
    if n is None:
        return 400, "content-length không hợp lệ"
    if n == 0:
        return 400, "Thiếu body JSON"
    if n > BODY_TOI_DA:
        return 413, "Body quá 256 KB"
    try:
        b = h.rfile.read(n)
    except OSError:
        h._pv_da_doc = True
        return 408, "Hết giờ đọc body"
    h._pv_da_doc = True
    if len(b) != n:
        return 400, "Body bị cắt"
    try:
        return b, json.loads(b.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return 400, "Body không phải JSON hợp lệ"


# ---------------------------------------------------------------- chốt B1/B2/B3, che C1
def la_duong_dan_o_dia(s: object) -> bool:
    """B3: 'X:\\…' hoặc 'X:/…'; không UNC (\\\\, //, \\\\?\\), không ký tự điều khiển."""
    if not isinstance(s, str) or RE_DIEU_KHIEN.search(s):
        return False
    if s.startswith(("\\\\", "//", "\\/", "/\\")):
        return False
    return RE_O_DIA.match(s) is not None


def _duyet_duong_dan(obj: object):
    """Sinh mọi giá trị của khoá đường dẫn (ở mọi cấp lồng dict/list)."""
    ngan = [obj]
    while ngan:
        x = ngan.pop()
        if isinstance(x, dict):
            for k, v in x.items():
                if k in KHOA_DUONG_DAN and isinstance(v, str) and v:
                    yield v
                if isinstance(v, (dict, list)):
                    ngan.append(v)
        elif isinstance(x, list):
            ngan.extend(v for v in x if isinstance(v, (dict, list)))


def _ten_hop_le(ten: object) -> bool:
    return (isinstance(ten, str) and 1 <= len(ten) <= 100 and ten not in (".", "..")
            and not any(c in ten for c in "/\\:") and not RE_DIEU_KHIEN.search(ten))


def kiem_body(method: str, path: str, obj: object) -> str | None:
    """B1 + B3 (+ cookies là mảng cho cookies_from_json). None = hợp lệ."""
    if method in METHOD_CO_BODY and path.startswith("/api/v2/accounts") and isinstance(obj, dict) \
            and "name" in obj and not _ten_hop_le(obj["name"]):
        return LOI_B1
    if any(not la_duong_dan_o_dia(v) for v in _duyet_duong_dan(obj)):
        return LOI_B3
    if method == "POST" and path == "/api/v2/accounts/cookies_from_json" \
            and not (isinstance(obj, dict) and isinstance(obj.get("cookies"), list)):
        return "cookies phải là mảng"
    return None


def _kiem_dang_post_direct(obj: object) -> str | None:
    if not isinstance(obj, dict):
        return LOI_B2
    fid, vp = obj.get("folder_id"), obj.get("video_path")
    if type(fid) is not int or fid <= 0 or not isinstance(vp, str) or not vp:
        return LOI_B2
    return None


def kiem_post_direct(obj: dict, folder: dict) -> str | None:
    """B2: video phải nằm ngay trong thư mục local của folder (giống danh sách post.py:239-247)."""
    loi = _kiem_dang_post_direct(obj)
    if loi:
        return loi
    if not isinstance(folder, dict) or folder.get("source", "local") != "local":
        return LOI_B2
    fp, vp = folder.get("path"), obj["video_path"]
    if not la_duong_dan_o_dia(fp) or not la_duong_dan_o_dia(vp):
        return LOI_B2
    try:
        v = Path(vp).resolve()
        if v.parent != Path(fp).resolve() or v.suffix.lower() not in DUOI_DANG or not v.is_file():
            return LOI_B2
    except OSError:
        return LOI_B2
    return None


def _la_bi_mat(k: object) -> bool:
    return isinstance(k, str) and any(t in k.lower() for t in TU_BI_MAT)


def _co_gia_tri(v: object) -> bool:
    return v not in (None, "")


def che_bi_mat(path: str, obj: object) -> object:
    """C1: path /api/v2/settings* → giá trị của khoá bí mật thành "***" (dạng {k: v} và {"key","value"})."""
    if not path.startswith("/api/v2/settings"):
        return obj
    if isinstance(obj, list):
        return [che_bi_mat(path, x) for x in obj]
    if not isinstance(obj, dict):
        return obj
    kq = {k: ("***" if _la_bi_mat(k) and _co_gia_tri(v) else che_bi_mat(path, v)) for k, v in obj.items()}
    if "key" in kq and "value" in kq and _la_bi_mat(kq["key"]) and _co_gia_tri(kq["value"]):
        kq["value"] = "***"
    return kq


# ---------------------------------------------------------------- ổ đĩa máy nhà (§5.1, §5.2)
def ds_video(folder: dict) -> dict:
    """{"ho_tro", "video": [{name, path, size}]} — bê nguyên post.py:225-247."""
    path = folder.get("path") if isinstance(folder, dict) else None
    source = folder.get("source", "local") if isinstance(folder, dict) else None
    if source != "local" or not path or not la_duong_dan_o_dia(path):
        return {"ho_tro": False, "video": []}
    video = []
    try:
        p = Path(path)
        if p.exists() and p.is_dir():
            for ext in DUOI_DS_VIDEO:
                for f in p.glob(ext):
                    if "_posted" not in f.name and "okkkk" not in f.name:
                        video.append({"name": f.name, "path": str(f), "size": f.stat().st_size})
    except OSError as e:  # desktop log lỗi rồi giữ phần đã thấy (post.py:248-249)
        print("POSTER _video LOI", type(e).__name__, e, flush=True)
    return {"ho_tro": True, "video": video}


def dem_video(duong_dan: str) -> dict:
    """{"ton_tai", "so_video"} — bê nguyên folders.py:189-192."""
    p = Path(duong_dan)
    if p.exists() and p.is_dir():
        return {"ton_tai": True, "so_video": len([f for f in p.iterdir() if f.suffix.lower() in DUOI_DEM])}
    return {"ton_tai": False, "so_video": 0}


_SEM_QUET = threading.BoundedSemaphore(2)  # lần quét quá hạn vẫn giữ chỗ tới khi thật sự xong


def _quet(ten: str, *a) -> tuple[int, object]:
    """Chạy globals()[ten](*a) trong luồng riêng, chờ tối đa HAN_QUET_DIA; quá thì 504."""
    han = HAN_QUET_DIA
    t0 = time.monotonic()
    if not _SEM_QUET.acquire(timeout=han):
        return 504, {"loi": LOI_QUET}
    kq: list = []

    def chay() -> None:
        try:
            kq.append((200, globals()[ten](*a)))
        except OSError as e:
            print("POSTER QUET LOI", ten, type(e).__name__, e, flush=True)
            kq.append((500, {"loi": f"Không đọc được thư mục ({type(e).__name__})"}))
        finally:
            _SEM_QUET.release()

    t = threading.Thread(target=chay, daemon=True, name="poster-quet")
    t.start()
    t.join(max(0.0, han - (time.monotonic() - t0)))
    return kq[0] if kq else (504, {"loi": LOI_QUET})


# ---------------------------------------------------------------- gọi backend
def _cau_qua_gio(method: str, han: float) -> str:
    if method == "GET":
        return f"Poster V2 trả lời quá chậm (> {han:g} s). Bấm Refresh/Làm mới."
    return f"Poster V2 chưa trả lời sau {han:g} s. {CO_THE_DA_CHAY}"


def _goi_mot_lan(method: str, pq: str, body: bytes | None, token: str, port: int,
                 deadline: float, han: float) -> tuple[int, object]:
    hd = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if method in METHOD_CO_BODY:
        hd["Content-Type"] = "application/json"
    con = deadline - time.monotonic()
    if con <= 0:
        return 504, {"loi": _cau_qua_gio(method, han)}
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=min(HAN_KET_NOI, con))
    het_han = threading.Event()

    def cat() -> None:  # đồng hồ chặn: backend nhả byte nhỏ giọt (kể cả ở header) vẫn bị cắt đúng hạn tổng
        het_han.set()
        s = conn.sock
        if s is not None:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    dong_ho = threading.Timer(con, cat)
    dong_ho.daemon = True
    da_ket_noi = False
    try:
        try:
            conn.connect()
            da_ket_noi = True
            dong_ho.start()
            conn.sock.settimeout(max(0.1, deadline - time.monotonic()))
            conn.request(method, pq, body=body, headers=hd)
            conn.sock.settimeout(max(0.1, deadline - time.monotonic()))
            r = conn.getresponse()
            phan: list[bytes] = []
            tong = 0
            while True:
                con = deadline - time.monotonic()
                if con <= 0 or het_han.is_set():
                    return 504, {"loi": _cau_qua_gio(method, han)}
                if conn.sock is not None:
                    conn.sock.settimeout(max(0.1, con))
                c = r.read1(65536)
                if not c:
                    break
                phan.append(c)
                tong += len(c)
                if tong > TRA_TOI_DA:
                    return 502, {"loi": "Phản hồi Poster V2 quá 4 MB"}
            if het_han.is_set():  # bị cắt giữa chừng mà read1 trả rỗng (EOF giả)
                return 504, {"loi": _cau_qua_gio(method, han)}
        except (TimeoutError, socket.timeout):
            return 504, {"loi": _cau_qua_gio(method, han)}
        except (ConnectionError, http.client.HTTPException, OSError) as e:
            if het_han.is_set():
                return 504, {"loi": _cau_qua_gio(method, han)}
            if not da_ket_noi:
                return 502, {"loi": LOI_CHUA_MO, "ma": "chua_mo"}
            print("POSTER BACKEND LOI", method, pq.split("?", 1)[0], type(e).__name__, flush=True)
            loi = "Mất kết nối với Poster V2 giữa chừng."
            return 502, {"loi": loi if method == "GET" else f"{loi} {CO_THE_DA_CHAY}"}
    finally:
        dong_ho.cancel()
        conn.close()
    noi_dung = b"".join(phan)
    st = r.status
    if 300 <= st < 400:
        return 502, {"loi": f"Poster V2 chuyển hướng ({st}); kiểm dấu / cuối đường dẫn"}
    if not noi_dung:
        return st, None
    try:
        return st, json.loads(noi_dung.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return st, {"detail": noi_dung[:500].decode("utf-8", "replace")}


def goi_backend(method: str, path_kem_query: str, body: bytes | None, han: float) -> tuple[int, object]:
    """Gọi backend với hạn tổng monotonic `han`. 401 → đọc lại .env 1 lần; chỉ GET mới gọi lại.

    Không bao giờ tự gửi lại lệnh ghi (CL21)."""
    deadline = time.monotonic() + han
    token, port = cau_hinh()
    st, obj = _goi_mot_lan(method, path_kem_query, body, token, port, deadline, han)
    if st != 401:
        return st, obj
    token, port = cau_hinh(doc_lai=True)
    if method == "GET":
        st, obj = _goi_mot_lan(method, path_kem_query, body, token, port, deadline, han)
    if st == 401:
        return 502, {"loi": LOI_TOKEN, "ma": "token"}
    return st, obj


# ---------------------------------------------------------------- bật backend từ web
_KHOA_BAT = threading.Lock()
_DA_BAT: dict[str, object] = {"proc": None, "luc": 0.0}


def _cong_dang_nghe(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


def _la_poster(port: int) -> bool:
    """/health công khai của Poster V2 trả {"status": "healthy", "version": "2.x"} (main.py:189-192)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3.0)
    try:
        conn.request("GET", "/health")
        r = conn.getresponse()
        obj = json.loads(r.read(65536).decode("utf-8"))
    except (OSError, http.client.HTTPException, ValueError, UnicodeDecodeError):
        return False
    finally:
        conn.close()
    return isinstance(obj, dict) and obj.get("status") == "healthy" and str(obj.get("version", "")).startswith("2.")


def ai_giu_cong(port: int) -> str:
    """'tên.exe (PID n)' của tiến trình đang nghe cổng; không rõ thì 'một chương trình khác'."""
    an = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        ra = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=10,
                            creationflags=an).stdout
        for dong in ra.splitlines():
            cot = dong.split()
            if len(cot) >= 5 and cot[1].endswith(f":{port}") and cot[3].upper() == "LISTENING":
                pid = cot[4]
                ten = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True,
                                     text=True, timeout=10, creationflags=an).stdout.strip()
                ten = ten.split(",")[0].strip('"') if ten.startswith('"') else "?"
                return f"{ten} (PID {pid})"
    except (OSError, subprocess.SubprocessError):
        pass
    return "một chương trình khác"


def _python_poster() -> str:
    tu_env = os.environ.get("KHO_POSTER_PYTHON")
    if tu_env:
        return tu_env
    return str(PYTHON_POSTER) if PYTHON_POSTER.exists() else sys.executable


def _mo_tien_trinh(lenh: list[str], cwd: Path, env: dict[str, str]):  # tách riêng để test thay
    return subprocess.Popen(lenh, cwd=str(cwd), env=env, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


def bat_backend() -> tuple[int, dict]:
    """Bật `python -m src.backend.main` của Poster nếu cổng trống. Không bao giờ mở 2 backend chồng nhau."""
    _token, port = cau_hinh()
    with _KHOA_BAT:
        if _cong_dang_nghe(port):
            if _la_poster(port):
                return 200, {"trang_thai": "da_chay"}
            return 409, {"loi": LOI_CONG_LA.format(port=port, ai=ai_giu_cong(port)), "ma": "cong_la"}
        p = _DA_BAT["proc"]
        if p is not None and p.poll() is None and time.monotonic() - float(_DA_BAT["luc"]) < HAN_BAT_LAI:
            return 200, {"trang_thai": "dang_bat"}
        env = dict(os.environ)
        # Backend đọc API_PORT (settings không có tiền tố); client đọc TT_API_PORT. Ghim cả hai về cổng đang hỏi.
        env.update({"API_PORT": str(port), "TT_API_PORT": str(port), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        try:
            p = _mo_tien_trinh([_python_poster(), "-B", "-m", "src.backend.main"], poster_dir(), env)
        except OSError as e:
            return 500, {"loi": f"Không chạy được Poster V2: {e}"}
        _DA_BAT.update(proc=p, luc=time.monotonic())
        print("POSTER BAT BACKEND pid", p.pid, "cong", port, flush=True)
        return 200, {"trang_thai": "dang_bat", "pid": p.pid}


# ---------------------------------------------------------------- bảng lệnh nền (§3.3)
class DayCho(Exception):
    def __init__(self, lop: str):
        super().__init__(lop)
        self.lop = lop


@dataclass
class _Lenh:
    ma: str
    khoa: tuple[str, str, str]
    lop: str
    bat_dau: float
    toi_da_giay: float
    tom_tat: dict
    xong: threading.Event = field(default_factory=threading.Event)
    ket_qua: tuple[int, object] | None = None
    xong_luc: float | None = None
    nen: bool = False
    doi: int = 0  # số handler lớp S đã nhận mã nhưng chưa gọi cho() — mục này không được dọn khi bảng đầy


class BangLenh:
    """Lệnh gọi backend chạy trong luồng daemon. Khoá bảng CHỈ bao thao tác trên dict, không bao giờ giữ khi gọi backend."""

    def __init__(self, khi_su_kien: Callable[[str, dict], None] | None = None):
        self._khoa = threading.Lock()
        self._lenh: dict[str, _Lenh] = {}
        self._theo_khoa: dict[tuple[str, str, str], str] = {}
        self._khi_su_kien = khi_su_kien

    @staticmethod
    def _mo_ta(l: _Lenh) -> dict:
        return {"cho": l.ma, "method": l.khoa[0], "path": l.khoa[1], "lop": l.lop,
                "giay_da_chay": round(time.monotonic() - l.bat_dau, 1), "toi_da_giay": l.toi_da_giay,
                "tom_tat": dict(l.tom_tat)}

    def _don(self) -> None:  # gọi khi đang giữ khoá
        bay_gio = time.monotonic()
        for ma in [m for m, l in self._lenh.items() if l.xong_luc is not None and bay_gio - l.xong_luc > GIU_KET_QUA]:
            del self._lenh[ma]

    @staticmethod
    def _thu_tu_don(l: _Lenh) -> tuple[int, float]:
        """Thứ tự xoá khi bảng đầy (P3-2): (0) lệnh xong đồng bộ — client đã nhận kết quả, không ai hỏi _kq;
        (1) GET đã chuyển nền; (2) lệnh ghi đã chuyển nền — giữ lâu nhất. Cùng hạng: xong sớm xoá trước."""
        hang = 0 if not l.nen else (1 if l.khoa[0] == "GET" else 2)
        return hang, l.xong_luc or 0.0

    def _bao(self, ten: str, l: _Lenh, status: int | None = None) -> None:
        if self._khi_su_kien is None:
            return
        try:
            mo_ta = self._mo_ta(l)
            if status is not None:  # chỉ mã kết quả, KHÔNG BAO GIỜ body
                mo_ta["status"] = status
            self._khi_su_kien(ten, mo_ta)
        except Exception as e:  # nhật ký hỏng không được làm hỏng lệnh; in ra console
            print("POSTER SU KIEN LOI", ten, type(e).__name__, e, flush=True)

    def nhan(self, khoa: tuple[str, str, str], lop: str, viec: Callable[[], tuple[int, object]],
             tom_tat: dict, toi_da_giay: float) -> tuple[str, bool]:
        """→ (ma, trung). Trùng khoá đang chạy → (ma cũ, True). Hết chỗ lớp / bảng đầy → DayCho(lop)."""
        with self._khoa:
            self._don()
            cu = self._theo_khoa.get(khoa)
            if cu is not None:
                if lop == "S":
                    self._lenh[cu].doi += 1
                return cu, True
            dang = sum(1 for l in self._lenh.values() if l.lop == lop and l.xong_luc is None)
            if dang >= CHO_CHAY[lop]:
                raise DayCho(lop)
            if len(self._lenh) >= BANG_TOI_DA:
                xong = sorted((l for l in self._lenh.values() if l.xong_luc is not None and l.doi == 0),
                              key=self._thu_tu_don)
                for l in xong[:len(self._lenh) - BANG_TOI_DA + 1]:
                    del self._lenh[l.ma]
                if len(self._lenh) >= BANG_TOI_DA:
                    raise DayCho(lop)
            l = _Lenh(ma=secrets.token_hex(16), khoa=khoa, lop=lop, bat_dau=time.monotonic(),
                      toi_da_giay=toi_da_giay, tom_tat=dict(tom_tat), nen=lop != "S", doi=int(lop == "S"))
            self._lenh[l.ma] = l
            self._theo_khoa[khoa] = l.ma
        t = threading.Thread(target=self._chay, args=(l, viec), daemon=True, name=f"poster-{lop}")
        try:
            t.start()
        except RuntimeError:
            with self._khoa:
                self._lenh.pop(l.ma, None)
                self._theo_khoa.pop(khoa, None)
            raise DayCho(lop) from None
        return l.ma, False

    def _chay(self, l: _Lenh, viec: Callable[[], tuple[int, object]]) -> None:
        try:
            kq = viec()
        except Exception as e:  # mọi lỗi của việc → kết quả 500, luồng không chết im lặng
            print("POSTER VIEC LOI", l.khoa[0], l.khoa[1].split("?", 1)[0], flush=True)
            traceback.print_exc()
            kq = (500, {"loi": f"Lỗi nội bộ video_server ({type(e).__name__})"})
        with self._khoa:
            l.ket_qua = kq
            l.xong_luc = time.monotonic()
            if self._theo_khoa.get(l.khoa) == l.ma:
                del self._theo_khoa[l.khoa]
            nen = l.nen
        l.xong.set()
        if nen:
            self._bao("ket_thuc", l, kq[0])

    def cho(self, ma: str, giay: float) -> tuple[int, object] | None:
        """Chờ tối đa `giay`; None = chưa xong (lệnh được đánh dấu chạy nền)."""
        with self._khoa:
            l = self._lenh.get(ma)
            if l is not None:
                l.doi = max(0, l.doi - 1)  # đã cầm tham chiếu: từ đây mục bị dọn cũng không sao
        if l is None:
            raise KeyError(ma)
        l.xong.wait(max(0.0, giay))
        with self._khoa:
            if l.ket_qua is not None:
                return l.ket_qua
            moi = not l.nen
            l.nen = True
        if moi:
            self._bao("chuyen_nen", l)
        return None

    def ket_qua(self, ma: str) -> dict | None:
        with self._khoa:
            self._don()
            l = self._lenh.get(ma)
            if l is None:
                return None
            if l.ket_qua is None:
                return {"xong": False}
            return {"xong": True, "status": l.ket_qua[0], "body": l.ket_qua[1]}

    def dang_chay(self) -> list[dict]:
        with self._khoa:
            return [self._mo_ta(l) for l in self._lenh.values() if l.xong_luc is None]


# ---------------------------------------------------------------- nhật ký JSONL (§4.4) — không bao giờ ghi giá trị body
_KHOA_NHAT_KY = threading.Lock()
_xoay_nghi_den = 0.0  # monotonic; giữ _KHOA_NHAT_KY khi đọc/ghi


def _file_nhat_ky() -> Path:
    f = os.environ.get("KHO_POSTER_NHAT_KY")
    if f:
        return Path(f)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "kho-poster-web" / "nhat-ky.jsonl"


def _xoay_vong(f: Path) -> None:
    """Quá 5 MB thì đổi tên sang .1, thử lại theo XOAY_CHO. Hỏng hẳn → in lỗi, nghỉ XOAY_NGHI giây rồi mới thử lại;
    KHÔNG ném: dòng nhật ký vẫn phải được ghi vào file hiện tại (chấp nhận vượt 5 MB). Gọi khi giữ _KHOA_NHAT_KY."""
    global _xoay_nghi_den
    if time.monotonic() < _xoay_nghi_den:
        return
    try:
        if f.stat().st_size <= NHAT_KY_TOI_DA:
            return
    except FileNotFoundError:
        return
    dich = f.with_name(f.name + ".1")
    for cho in (*XOAY_CHO, None):
        try:
            os.replace(f, dich)
            return
        except FileNotFoundError:
            return
        except OSError as e:  # Windows: file đang mở ở trình xem log/antivirus/indexer
            if cho is None:
                _xoay_nghi_den = time.monotonic() + XOAY_NGHI
                print("NHAT KY LOI xoay vong (van ghi tiep vao file hien tai)", type(e).__name__, e, flush=True)
                return
            time.sleep(cho)


def ghi_nhat_ky(muc: dict) -> None:
    """Ghi 1 dòng JSONL; quá 5 MB thì đổi sang .1 (giữ 1 bản). Đổi tên lỗi không làm mất dòng. Lỗi chỉ in ra console."""
    try:
        f = _file_nhat_ky()
        dong = json.dumps(muc, ensure_ascii=False) + "\n"
        with _KHOA_NHAT_KY:
            f.parent.mkdir(parents=True, exist_ok=True)
            _xoay_vong(f)
            with open(f, "a", encoding="utf-8") as fh:
                fh.write(dong)
    except (OSError, TypeError, ValueError) as e:
        print("NHAT KY LOI", type(e).__name__, e, flush=True)


def _luc() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _su_kien_bang(ten: str, mo_ta: dict) -> None:
    path, _, query = mo_ta["path"].partition("?")
    muc = {"luc": _luc(), "su_kien": ten, "method": mo_ta["method"], "path": path, "query": query,
           "lop": mo_ta["lop"], "giay": mo_ta["giay_da_chay"], "cho": mo_ta["cho"]}
    if "status" in mo_ta:  # ket_thuc: mã kết quả cuối (P3-1); không ghi body
        muc["status"] = mo_ta["status"]
    ghi_nhat_ky(muc)


BANG = BangLenh(_su_kien_bang)


# ---------------------------------------------------------------- handler
def _tra(h, code: int, obj: object, header: dict[str, str] | None = None) -> None:
    _xa_body(h)
    b = b"" if code in (204, 304) else json.dumps(obj, ensure_ascii=False).encode("utf-8")
    try:
        h.send_response(code)
        if code not in (204, 304):
            h.send_header("content-type", "application/json; charset=utf-8")
        h.send_header("content-length", str(len(b)))
        h.send_header("cache-control", "no-store")
        for k, v in (header or {}).items():
            h.send_header(k, v)
        h.end_headers()
        if b:
            h.wfile.write(b)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        pass


def _khoa_dung(h) -> bool:
    mong = getattr(h, "khoa", "") or ""
    if not mong:
        return False
    nhan = h.headers.get("x-key", "")
    return hmac.compare_digest(nhan.encode("utf-8", "surrogateescape"), mong.encode("utf-8", "surrogateescape"))


def _tom_tat(method: str, path: str, obj: object) -> dict:
    """Tóm tắt cho GET /_kq — không bao giờ chứa cookie, token hay giá trị body khác (§3.3)."""
    if method != "POST":
        return {}
    m = re.fullmatch(r"/api/v2/queue/(\d{1,9})/(post|run)", path, re.ASCII)
    if m:
        return {"queue_id": int(m[1])}
    o = obj if isinstance(obj, dict) else {}
    if path == "/api/v2/post/direct":
        fid, vp = o.get("folder_id"), o.get("video_path")
        return {"folder_id": fid if type(fid) is int else None,
                "video": PureWindowsPath(vp).name if isinstance(vp, str) else ""}
    if path == "/api/v2/accounts/login_and_capture":
        ten = o.get("name")
        return {"name": ten[:100] if isinstance(ten, str) else ""}
    return {}


def _viec_backend(method: str, pq: str, path: str, body: bytes | None, obj: object, lop: str) -> Callable:
    def viec() -> tuple[int, object]:
        han = HAN_NEN[lop]
        deadline = time.monotonic() + han
        if path == "/api/v2/post/direct":  # B2: lấy folder từ backend trong cùng luồng của lệnh
            st, folder = goi_backend("GET", f"/api/v2/folders/{obj['folder_id']}", None, han)
            if st != 200:
                return st, folder
            loi = kiem_post_direct(obj, folder)
            if loi:
                return 400, {"loi": loi}
            han = max(0.0, deadline - time.monotonic())
        st, kq = goi_backend(method, pq, body, han)
        if 200 <= st < 300:
            kq = che_bi_mat(path, kq)
        return st, kq
    return viec


def _viec_video(folder_id: str) -> Callable:
    def viec() -> tuple[int, object]:
        st, folder = goi_backend("GET", f"/api/v2/folders/{folder_id}", None, HAN_NEN["S"])
        if st != 200:
            return st, folder
        return _quet("ds_video", folder)
    return viec


def _boi(h) -> str | None:
    b = h.headers.get("x-poster-boi")
    return RE_BOI.sub("", b)[:64] if b else None


def xu_ly(h, method: str) -> None:
    """Xử lý một request /p/*; luôn tự trả lời client."""
    t0 = time.monotonic()
    h._pv_da_doc = False
    try:
        h.connection.settimeout(HAN_DOC_BODY)
    except OSError:
        pass
    h.close_connection = True
    if not _khoa_dung(h):
        return _tra(h, 401, {"loi": "Sai khoá"}, {"x-kho-tu-choi": "khoa"})
    if os.environ.get("KHO_POSTER_WEB") == "0":
        return _tra(h, 503, {"loi": LOI_TAT})

    tho = h.path
    duong, _, query = tho.partition("?")
    rest = duong[2:] if duong.startswith("/p") else ""
    if "#" in tho:
        return _tra(h, 400, {"loi": "Query không hợp lệ"})

    # route riêng của video_server
    if rest == "/_kq" or RE_KQ.fullmatch(rest) or rest == "/_thong_tin" or RE_VIDEO.fullmatch(rest):
        if method != "GET":
            return _tra(h, 405, {"loi": "Sai phương thức"})
        loi = doc_body(h, method)
        if isinstance(loi[0], int):
            return _tra(h, loi[0], {"loi": loi[1]})
        if rest == "/_kq":
            return _tra(h, 200, {"dang_chay": BANG.dang_chay()})
        m = RE_KQ.fullmatch(rest)
        if m:
            kq = BANG.ket_qua(m[1])
            return _tra(h, 200, kq) if kq is not None else _tra(h, 404, {"loi": LOI_KQ_MAT})
        if rest == "/_thong_tin":
            try:
                token, port = cau_hinh()
            except RuntimeError as e:  # chot_test khi đang test
                return _tra(h, 500, {"loi": str(e)})
            td = poster_dir()
            return _tra(h, 200, {"backend": f"http://127.0.0.1:{port}", "co_token": bool(token), "thu_muc": str(td),
                                 "database": str(td / "v2_data.db"), "profiles": str(td / "profiles_v2")})
        fid = RE_VIDEO.fullmatch(rest)[1]
        return _chay_lenh(h, method, t0, ("GET", rest, hashlib.sha256(b"").hexdigest()), "S",
                          _viec_video(fid), {}, None, None, rest, "", ghi=False)
    if rest == "/_bat_backend":
        if method != "POST":
            return _tra(h, 405, {"loi": "Sai phương thức"})
        r = doc_body(h, method)
        if isinstance(r[0], int):
            return _tra(h, r[0], {"loi": r[1]})
        try:
            code, tra = bat_backend()
        except RuntimeError as e:  # chot_test khi đang test
            code, tra = 500, {"loi": str(e)}
        ghi_nhat_ky({"luc": _luc(), "su_kien": "bat_backend", "boi": _boi(h), "method": method, "path": rest,
                     "status": code, "ms": int((time.monotonic() - t0) * 1000)})
        return _tra(h, code, tra)
    if rest == "/_dem":
        if method != "POST":
            return _tra(h, 405, {"loi": "Sai phương thức"})
        r = doc_body(h, method)
        if isinstance(r[0], int):
            return _tra(h, r[0], {"loi": r[1]})
        body, obj = r
        dd = obj.get("duong_dan") if isinstance(obj, dict) else None
        if not isinstance(dd, str) or not dd or len(dd) > DUONG_DAN_TOI_DA:
            return _tra(h, 400, {"loi": "Thiếu duong_dan (chuỗi ≤ 400 ký tự)"})
        if not la_duong_dan_o_dia(dd):
            return _tra(h, 400, {"loi": LOI_B3})
        return _chay_lenh(h, method, t0, ("POST", rest, hashlib.sha256(body).hexdigest()), "S",
                          lambda: _quet("dem_video", dd), {}, body, obj, rest, "", ghi=True)

    # chuyển tiếp backend
    if not kiem_path(rest):
        return _tra(h, 404, {"loi": LOI_PATH})
    if method not in METHODS:
        return _tra(h, 405, {"loi": "Sai phương thức"})
    if not kiem_query(query):
        return _tra(h, 400, {"loi": "Query không hợp lệ"})
    r = doc_body(h, method)
    if isinstance(r[0], int):
        return _tra(h, r[0], {"loi": r[1]})
    body, obj = r
    loi = kiem_body(method, rest, obj)
    if loi is None and method == "POST" and rest == "/api/v2/post/direct":
        loi = _kiem_dang_post_direct(obj)
    if loi:
        return _tra(h, 400, {"loi": loi})
    pq = rest + ("?" + query if query else "")
    lop = lop_cua(method, rest)
    khoa = (method, pq, hashlib.sha256(body or b"").hexdigest())
    return _chay_lenh(h, method, t0, khoa, lop, _viec_backend(method, pq, rest, body, obj, lop),
                      _tom_tat(method, rest, obj), body, obj, rest, query, ghi=method != "GET")


def _chay_lenh(h, method: str, t0: float, khoa: tuple[str, str, str], lop: str, viec: Callable, tom_tat: dict,
               body: bytes | None, obj: object, path: str, query: str, ghi: bool) -> None:
    ma, trung = None, False
    try:
        ma, trung = BANG.nhan(khoa, lop, viec, tom_tat, HAN_NEN[lop])
    except DayCho:
        code, tra = 429, {"loi": LOI_BAN_S if lop == "S" else LOI_BAN_DANG}
    else:
        if lop != "S":
            code, tra = 202, {"cho": ma, "toi_da_giay": HAN_NEN[lop], "trung": trung}
        else:
            kq = BANG.cho(ma, HAN_CHO_DONG_BO - (time.monotonic() - t0))
            if kq is None:
                code, tra = 202, {"cho": ma, "toi_da_giay": HAN_NEN[lop], "trung": trung}
            else:
                code, tra = kq
    if ghi:  # ghi TRƯỚC khi trả lời: client thấy phản hồi thì dòng nhật ký đã có
        ghi_nhat_ky({"luc": _luc(), "su_kien": "yeu_cau", "boi": _boi(h), "method": method, "path": path,
                     "query": query, "status": code, "ms": int((time.monotonic() - t0) * 1000),
                     "body_sha256": hashlib.sha256(body or b"").hexdigest(),
                     "khoa_body": [str(k)[:64] for k in list(obj)[:50]] if isinstance(obj, dict) else [],
                     "cho": ma, "trung": trung})
    _tra(h, code, tra)
