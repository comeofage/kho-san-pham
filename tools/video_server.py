"""Server nhỏ trên máy nhà: phát từng video trong output_poster của sản phẩm cho web kho (qua Cloudflare Tunnel).

Chạy:  python tools/video_server.py            (cổng 8787, chỉ nghe 127.0.0.1)
Khoá:  tools/.video_key (tự sinh lần đầu) — đặt cùng giá trị làm secret VIDEO_KEY của Worker.
Thư mục: <GOC>/<tên> <id>/output_poster/*.mp4, GOC mặc định E:/oneshottramcanh , F:/2010, F:/2210, F:/2310/ncm , F:/2610/1026/ncm, F:/2710/1028, F:/3010/3010/ncm và E:/Aff anh nhan/review (đổi bằng biến KHO_VIDEO_GOC, cách nhau bằng ";").

  GET  /v/<id>/ds               -> {"tong": n, "ten": tên video kế tiếp, "mb": dung lượng, nguon[].ds: tên các video kế tiếp}
  GET  /v/<id>/file?ten=<tên>[&xoa=1] -> nội dung video; có xoa=1 thì gửi xong trọn vẹn sẽ xóa file
  POST /v/<id>/xoa?ten=<tên>    -> xóa file đó (web gọi sau khi điện thoại đã nhận đủ)
  GET  /v/<id>/xem?goc=<goc>&ten=<tên> -> xem video inline (Range, không attachment, KHÔNG BAO GIỜ xóa)
  GET  /v/<id>/tien-do          -> {"thu_muc": [{goc, ten, raw, takes, cuts, muse, voice, output_poster, output}]}
                                   đếm file trực tiếp trong từng thư mục con của mọi '<GOC>/*<id>'
  GET  /suc-khoe                -> {"luc": ISO giờ máy, "apps": [{ma, ten, cong, song, bat_tat?}]} (dò cổng TCP 127.0.0.1)
  POST /app/<ma>/bat|tat        -> bật (lệnh cố định LENH_BAT, cửa sổ riêng) / tắt (taskkill /T tiến trình nghe cổng
                                   + cửa sổ cmd bọc nó) app trong LENH_BAT -> {ma, ok, tin, song}; mã lạ 404
  GET|POST /r/<...>             -> chuyển tiếp sang runner KHO_RUNNER_ORIGIN (mặc định 127.0.0.1:8788), bỏ tiền tố /r;
                                   lọc path/query/body/header theo docs/bo-chay-viec.md §3.2, không chuyển x-key
                                   (/r/hoc/*: method + query riêng từng tuyến, docs/hoc-tu-dong.md §3.8 — R_HOC)
  GET  /v/<id>/anh?du_an=<12 hex>&ten=<clip>&k=<0-9|cs> -> image/jpeg cuts/.index_frames/<clip_id>/f_0k.jpg | contact_sheet.jpg
  GET  /v/<id>/clip?du_an=<12 hex>&ten=<clip>  -> clip phủ trong cuts/ (hoặc con một cấp), Range, không attachment
                                   (ten phải là khoá trong cuts/clip_index.json → clips; docs/sua-video.md §8.2)
  (ds: mỗi phần tử nguon[] có thêm "chi_tiet": [{ten, mb, sua_luc}] theo thứ tự ds)
  GET|POST|PUT|PATCH|DELETE /p/<...> -> backend Poster V2 qua tools/poster_web.py (tự kiểm x-key, 401 kèm
                                   x-kho-tu-choi: khoa; docs/poster-v2-tren-web.md; tắt bằng KHO_POSTER_WEB=0)
"""
import hashlib, hmac, os, re, secrets, socket, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # poster_web nằm cạnh file này
import poster_web

# Nhiều thư mục gốc, cách nhau bằng ";" — video nằm ở đâu cũng được miễn là <GOC>/<tên> <id>/output_poster/*.mp4
GOCS = [Path(g) for g in os.environ.get("KHO_VIDEO_GOC", "E:/oneshottramcanh;F:/2010;F:/2210;F:/2310/ncm;F:/2610/1026/ncm;F:/2710/1028;F:/3010/3010/ncm;E:/Aff anh nhan/review").split(";") if g.strip()]
GOC = GOCS[0]
# Video Douyin đã tải sẵn: <DY_GOC>/sp_<id>/douyin/video/*.mp4 (xem trực tiếp trên web, có tua)
DY_GOC = Path(os.environ.get("KHO_DOUYIN_GOC", "E:/phantichcanhquay"))
KEY_FILE = Path(__file__).with_name(".video_key")
RE_ID = re.compile(r"^(\d{15,21}|tam-\d{10,24})$")
DUOI = {".mp4", ".mov", ".m4v"}


def lay_khoa() -> str:
    if not KEY_FILE.exists():
        KEY_FILE.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    return KEY_FILE.read_text(encoding="utf-8").strip()


THU_MUC = [("output_poster", ""), ("output", "")]  # output = mẻ autovideo-oneshot (nút tải riêng)  # folder được liệt kê để tải; bản cùng tên ở output_daonguoc bị xóa theo (xem xoa_cap)
FOLDER_DAO = "output_daonguoc"


def xoa_cap(f: Path) -> None:
    """Xóa file đã tải và bản cùng tên trong output_daonguoc (nếu có)."""
    f.unlink(); print("DA XOA", f, flush=True)
    b = f.parent.parent / FOLDER_DAO / f.name
    if b.is_file():
        try:
            b.unlink(); print("DA XOA", b, flush=True)
        except OSError as e:
            print("XOA LOI", b, e, flush=True)


def ds_douyin(id_: str) -> list[Path]:
    d = DY_GOC / f"sp_{id_}" / "douyin" / "video"
    return sorted((f for f in d.iterdir() if f.is_file() and f.suffix.lower() in DUOI), key=lambda f: f.name.lower()) if d.is_dir() else []


def gui_file_range(h, f: Path, attachment: bool = False) -> None:
    """Gửi file có hỗ trợ Range (để <video> tua được và bắt đầu phát ngay)."""
    size = f.stat().st_size
    a, b, code = 0, size - 1, 200
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", h.headers.get("range", "").strip())
    if m and (m[1] or m[2]):
        if m[1]:
            a = int(m[1]); b = int(m[2]) if m[2] else size - 1
        else:
            a = max(0, size - int(m[2]))
        b = min(b, size - 1)
        if a > b:
            h.send_response(416); h.send_header("content-range", f"bytes */{size}"); h.send_header("content-length", "0"); h.end_headers(); return
        code = 206
    h.send_response(code)
    h.send_header("content-type", "video/mp4")
    h.send_header("accept-ranges", "bytes")
    h.send_header("content-length", str(b - a + 1))
    if code == 206:
        h.send_header("content-range", f"bytes {a}-{b}/{size}")
    h.end_headers()
    try:
        with open(f, "rb") as fh:
            fh.seek(a); left = b - a + 1
            while left > 0 and (chunk := fh.read(min(1 << 20, left))):
                h.wfile.write(chunk); left -= len(chunk)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        pass


def thu_muc_outputs(id_: str) -> list[Path]:
    """Mọi thư mục '<tên> <id>' (ở mọi GOC) có output_poster."""
    return [d for g in GOCS if g.is_dir() for d in sorted(g.glob(f"*{id_}")) if any((d / t).is_dir() for t, _ in THU_MUC)]


def thu_muc_output(id_: str) -> Path | None:
    ds = thu_muc_outputs(id_)
    return ds[0] if ds else None


def ds_video(id_: str, goc: str | None = None) -> list[tuple[str, Path]]:
    """[(tên hiển thị, đường dẫn)] của output_poster; goc (nếu có) chỉ lấy thư mục gốc đó."""
    return [(t, f) for g, t, f in ds_nguon(id_) if goc is None or g == goc]


def ds_nguon(id_: str) -> list[tuple[str, str, Path]]:
    """[(thư mục gốc, tên hiển thị, đường dẫn)] — mỗi thư mục gốc giữ riêng, không gộp."""
    kq = []
    for g in GOCS:
        if not g.is_dir(): continue
        for d in sorted(g.glob(f"*{id_}")):
            for t, tien_to in THU_MUC:
                o = d / t
                if o.is_dir():
                    kq += [(g.as_posix() + ("" if t == "output_poster" else "#" + d.name + "/" + t), tien_to + f.name, f) for f in sorted((f for f in o.iterdir() if f.is_file() and f.suffix.lower() in DUOI), key=lambda f: f.name.lower())]
    return kq


THU_MUC_TIEN_DO = ("raw", "takes", "cuts", "muse", "voice", "output_poster", "output")
DUOI_VOICE = {".mp3", ".wav"}
# (mã, tên, cổng) các app trên máy nhà cần dò sống/chết
APPS = [("muse", "Video Batch Local (Muse)", 3786), ("perfectvoice", "PerfectVoice", 7890),
        ("poster", "TikTok Poster V2", 8023), ("runner", "Bộ chạy việc", 8788)]

# ---------- chuyển tiếp /r/* sang runner (docs/bo-chay-viec.md §3.2) ----------
RUNNER_ORIGIN = os.environ.get("KHO_RUNNER_ORIGIN", "http://127.0.0.1:8788")
RUNNER_TIMEOUT = 10
RE_R = re.compile(r"^/r/(suc-khoe|danh-muc|poster/folders|du-an/\d{19}"
                  r"|viec(/j\d{14}[a-z0-9]{4}(/(log|tra-loi|duyet|tu-choi|huy|chay-lai|chay-tiep|xin-duyet-lai|nhan-tin"
                  r"|luu-tru|bo-luu-tru))?)?"
                  r"|sua-video/\d{19}(/[0-9a-f]{16}(/(ung-vien|ban-sua))?)?"
                  r"|hoc/(bao-cao|bai-hoc(/bh\d{8}[a-z0-9]{4}/(hoan-tac|bat-lai))?))$", re.ASCII)
R_QUERY_KHOA = ("tu", "trang_thai", "uid", "gioi_han", "tom_tat", "seg", "offset")
# /r/hoc/* (docs/hoc-tu-dong.md §3.8): mỗi tuyến đúng 1 method + khoá query riêng, không nới R_QUERY_KHOA chung.
# Path đã khớp RE_R mà không có ở đây = /r/hoc/bai-hoc/<ma>/(hoan-tac|bat-lai): chỉ POST, không query.
R_HOC = {"/r/hoc/bao-cao": ("GET", ("ngay",)), "/r/hoc/bai-hoc": ("GET", ("gioi_han",))}
R_HOC_GHI = ("POST", ())
RE_R_QUERY_GT = re.compile(r"^[A-Za-z0-9_,-]{0,40}$", re.ASCII)
R_HEADER = ("x-runner-key", "x-ky", "x-ky-ngay", "x-ky-nonce")  # + content-type cho POST; KHÔNG BAO GIỜ x-key
R_BODY_TOI_DA = 16 * 1024
R_TRA_TOI_DA = 1024 * 1024
R_XA_TOI_DA = 1024 * 1024  # body quá cỡ nhưng ≤ mức này thì đọc bỏ để client nhận được 413 (không bị RST)


def _loc_query(query: str, khoa: tuple | None = None) -> str:
    """Chỉ giữ khoá cho phép (mặc định R_QUERY_KHOA) có giá trị hợp lệ; mỗi khoá lấy lần đầu hợp lệ."""
    from urllib.parse import parse_qsl, urlencode
    khoa = R_QUERY_KHOA if khoa is None else khoa
    giu = {}
    for k, v in parse_qsl(query, keep_blank_values=True):
        if k in khoa and k not in giu and RE_R_QUERY_GT.fullmatch(v):
            giu[k] = v
    return urlencode(list(giu.items()), safe=",")


def _do_dai_body(h) -> int | None:
    """content-length hợp lệ (chỉ chữ số ASCII, không chunked) -> số byte; ngược lại None."""
    cl = h.headers.get("content-length")
    if h.headers.get("transfer-encoding") or cl is None or not re.fullmatch(r"\d{1,12}", cl.strip(), re.ASCII):
        return None
    return int(cl)


def _tu_choi(h, code: int, loi: str) -> None:
    """Từ chối request; body còn treo (≤1 MB) thì đọc bỏ để client nhận được mã lỗi thay vì bị RST."""
    h.close_connection = True
    n = _do_dai_body(h) if h.command == "POST" else None
    if n and n <= R_XA_TOI_DA:
        try:
            h.rfile.read(n)
        except OSError:
            pass
    h._json(code, {"loi": loi})


def chuyen_tiep_runner(h, method: str) -> None:
    """Chuyển request /r/* (đã qua kiểm x-key) sang runner; tự trả lời client trong mọi trường hợp."""
    import http.client
    # Đặt timeout TRƯỚC mọi lần đọc body (kể cả _tu_choi đọc bỏ ≤1 MB): client khai
    # content-length rồi im không giữ được luồng mãi.
    h.connection.settimeout(RUNNER_TIMEOUT)
    u = urlparse(h.path)
    if not RE_R.fullmatch(u.path):
        return _tu_choi(h, 404, "Đường dẫn không hợp lệ")
    hoc = R_HOC.get(u.path, R_HOC_GHI) if u.path.startswith("/r/hoc/") else None
    if hoc and method != hoc[0]:
        return _tu_choi(h, 405, "Sai phương thức")
    body = None
    if method == "POST":
        ct = h.headers.get("content-type", "")
        if ct.split(";", 1)[0].strip().lower() != "application/json":
            return _tu_choi(h, 415, "Chỉ nhận application/json")
        if h.headers.get("transfer-encoding") or h.headers.get("content-length") is None:
            return _tu_choi(h, 411, "Cần content-length")
        n = _do_dai_body(h)
        if n is None:
            return _tu_choi(h, 400, "content-length không hợp lệ")
        if n > R_BODY_TOI_DA:
            return _tu_choi(h, 413, "Body quá 16 KB")
        try:
            body = h.rfile.read(n) if n else b""  # timeout đã đặt ở đầu hàm
        except OSError:
            h.close_connection = True
            return h._json(408, {"loi": "Hết giờ đọc body"})
        if len(body) != n:
            h.close_connection = True
            return h._json(400, {"loi": "Body bị cắt"})
    elif method != "GET":
        return h._json(405, {"loi": "Sai phương thức"})

    hd = {k: h.headers[k] for k in R_HEADER if h.headers.get(k) is not None}
    if method == "POST":
        hd["content-type"] = h.headers["content-type"]
    q = _loc_query(u.query, hoc[1] if hoc else None)
    dich = u.path[2:] + ("?" + q if q else "")
    goc = urlparse(RUNNER_ORIGIN)
    conn = http.client.HTTPConnection(goc.hostname or "127.0.0.1", goc.port or 80, timeout=RUNNER_TIMEOUT)
    try:
        try:
            conn.request(method, dich, body=body, headers=hd)
            r = conn.getresponse()
            noi_dung = r.read(R_TRA_TOI_DA + 1)
        except (TimeoutError, socket.timeout):
            return h._json(504, {"loi": "Bộ chạy việc không trả lời kịp"})
        except (ConnectionError, http.client.HTTPException, OSError, ValueError) as e:
            print("RUNNER LOI", type(e).__name__, flush=True)
            return h._json(502, {"loi": "Bộ chạy việc chưa bật"})
    finally:
        conn.close()
    if len(noi_dung) > R_TRA_TOI_DA:
        return h._json(502, {"loi": "Phản hồi bộ chạy việc quá 1 MB"})
    h.send_response(r.status)
    h.send_header("content-type", r.getheader("content-type") or "application/json; charset=utf-8")
    h.send_header("content-length", str(len(noi_dung)))
    h.end_headers()
    try:
        h.wfile.write(noi_dung)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        pass


# ---------- ảnh khung / clip phủ cho trang sửa video (docs/sua-video.md §8.2, §3.1) ----------
RE_DU_AN = re.compile(r"^[0-9a-f]{12}$", re.ASCII)
RE_TEN_CLIP = re.compile(r"^[0-9A-Za-z][0-9A-Za-z_.()\- ]{0,150}\.mp4$", re.ASCII)
RE_CLIP_ID = re.compile(r"^(.+?_\d{3})_", re.ASCII)
RE_K_ANH = re.compile(r"^([0-9]|cs)$", re.ASCII)


def ma_du_an(p: Path) -> str:
    """Bản sao y tools/runner/du_an.py:39 (test chéo trong test_video_server.py)."""
    return hashlib.sha1(Path(p).as_posix().encode("utf-8")).hexdigest()[:12]


def tim_du_an(id_: str, ma: str) -> Path | None:
    """Thư mục '<GOC>/*<id>' có ma_du_an == ma (ký tự ngay trước id không là chữ số, như du_an.py)."""
    if not RE_DU_AN.fullmatch(ma or ""):
        return None
    for g in GOCS:
        try:
            if not g.is_dir():
                continue
            for d in sorted(g.glob(f"*{id_}")):
                ten = d.name
                if not d.is_dir() or not ten.endswith(id_):
                    continue
                if len(ten) > len(id_) and ten[-len(id_) - 1] in "0123456789":
                    continue
                if ma_du_an(d) == ma:
                    return d
        except OSError:
            continue
    return None


def _mot(q: dict, k: str) -> str:
    return (q.get(k) or [""])[0]


def _nam_trong(f: Path, goc: Path, cap_toi_da: int) -> bool:
    """f (sau khi resolve) nằm dưới goc, sâu không quá cap_toi_da cấp thư mục."""
    try:
        rel = f.resolve().relative_to(goc.resolve())
    except (OSError, ValueError):
        return False
    return 1 <= len(rel.parts) <= cap_toi_da + 1


def tim_clip(id_: str, q: dict) -> tuple[Path, str] | None:
    """(thư mục cuts, tên clip) nếu du_an hợp lệ thuộc id và ten là khoá trong clip_index.json → clips."""
    import json
    ten = _mot(q, "ten")
    if not RE_TEN_CLIP.fullmatch(ten) or ".." in ten:
        return None
    d = tim_du_an(id_, _mot(q, "du_an"))
    if d is None:
        return None
    cuts = d / "cuts"
    try:
        idx = json.loads((cuts / "clip_index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    clips = idx.get("clips") if isinstance(idx, dict) else None
    if not isinstance(clips, dict) or ten not in clips:
        return None
    return cuts, ten


def file_clip(cuts: Path, ten: str) -> Path | None:
    """File clip ngay trong cuts/ hoặc thư mục con một cấp (không theo liên kết ra ngoài)."""
    ung = [cuts / ten]
    try:
        ung += [x / ten for x in sorted(cuts.iterdir()) if x.is_dir()]
    except OSError:
        pass
    return next((f for f in ung if f.is_file() and _nam_trong(f, cuts, 1)), None)


def file_anh(cuts: Path, ten: str, k: str) -> Path | None:
    m = RE_CLIP_ID.match(ten)
    if not m:
        return None
    goc_anh = cuts / ".index_frames"
    f = goc_anh / m[1] / ("contact_sheet.jpg" if k == "cs" else f"f_0{k}.jpg")
    return f if f.is_file() and _nam_trong(f, goc_anh, 1) else None


def gui_anh(h, f: Path) -> None:
    try:
        b = f.read_bytes()
    except OSError:
        return h._json(404, {"loi": "Không thấy ảnh"})
    h.send_response(200)
    h.send_header("content-type", "image/jpeg")
    h.send_header("content-length", str(len(b)))
    h.end_headers()
    try:
        h.wfile.write(b)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        pass


def dem_file(d: Path, duoi: set[str]) -> int:
    """Số file (không đệ quy) có đuôi trong `duoi`; thư mục không tồn tại -> 0."""
    if not d.is_dir():
        return 0
    try:
        return sum(1 for f in d.iterdir() if f.is_file() and f.suffix.lower() in duoi)
    except OSError:
        return 0


def tien_do(id_: str) -> list[dict]:
    """Mọi thư mục '<GOC>/*<id>' (không đòi output_poster) kèm số file từng khâu."""
    kq = []
    for g in GOCS:
        if not g.is_dir(): continue
        for d in sorted(g.glob(f"*{id_}")):
            if not d.is_dir(): continue
            muc = {"goc": g.as_posix(), "ten": d.name}
            for t in THU_MUC_TIEN_DO:
                muc[t] = dem_file(d / t, DUOI_VOICE if t == "voice" else DUOI)
            kq.append(muc)
    return kq


def cong_song(cong: int, cho: float = 1.0) -> bool:
    """Mở được kết nối TCP tới 127.0.0.1:<cổng> trong `cho` giây (không gửi dữ liệu)."""
    try:
        with socket.create_connection(("127.0.0.1", cong), timeout=cho):
            return True
    except OSError:
        return False


def suc_khoe(cong_video: int) -> dict:
    with ThreadPoolExecutor(max_workers=len(APPS) or 1) as ex:
        song = list(ex.map(lambda a: cong_song(a[2]), APPS))
    apps = [{"ma": m, "ten": t, "cong": c, "song": s, **({"bat_tat": True} if m in LENH_BAT else {})}
            for (m, t, c), s in zip(APPS, song)]
    apps.append({"ma": "video_server", "ten": "Máy phát video", "cong": cong_video, "song": True})
    return {"luc": datetime.now().astimezone().isoformat(timespec="seconds"), "apps": apps}


# ---------- bật/tắt từng app từ trang Máy nhà ----------
# Lệnh bật CỐ ĐỊNH theo mã (web chỉ gửi mã, không gửi lệnh). Máy phát video không nằm đây: nó là đường điều khiển.
PY312 = r"C:\Users\Mi\AppData\Local\Programs\Python\Python312\python.exe"
LENH_BAT = {
    "muse": ["cmd", "/c", r"E:\viết bài wp\VideoBatchLocal\Start.cmd"],
    "perfectvoice": ["cmd", "/c", r"E:\PerfectVoice\Run.cmd"],
    "poster": ["cmd", "/c", r"E:\tool\tiktok_poster_v2\backend_only.bat"],
    "runner": ["cmd", "/c", PY312, r"E:\kho-runner\app\chay_runner.py"],
}
CHO_TAT = 8.0  # giây chờ cổng đóng sau taskkill


def pid_nghe_cong(cong: int) -> set[int]:
    """PID đang LISTENING trên <cổng> (netstat -ano, không cần psutil)."""
    import subprocess
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    kq = set()
    for d in out.splitlines():
        p = d.split()
        if len(p) >= 5 and p[3].upper() == "LISTENING" and p[1].rsplit(":", 1)[-1] == str(cong) and p[4].isdigit():
            kq.add(int(p[4]))
    kq.discard(0)
    return kq


def bang_tien_trinh() -> dict[int, tuple[int, str]]:
    """{pid: (pid cha, tên exe thường)} cho mọi tiến trình."""
    import subprocess
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Get-CimInstance Win32_Process | ForEach-Object { \"$($_.ProcessId) $($_.ParentProcessId) $($_.Name)\" }"],
                             capture_output=True, text=True, timeout=20,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    kq = {}
    for d in out.splitlines():
        p = d.strip().split(" ", 2)
        if len(p) == 3 and p[0].isdigit() and p[1].isdigit():
            kq[int(p[0])] = (int(p[1]), p[2].lower())
    return kq


def goc_can_giet(pid: int, bang: dict[int, tuple[int, str]], cam: set[int]) -> int:
    """Leo lên các cmd.exe cha (cửa sổ .cmd/.bat bọc app) để tắt luôn cửa sổ đó;
    dừng khi cha không phải cmd.exe hoặc là tổ tiên của chính video_server (cam)."""
    cur, da = pid, {pid}
    while True:
        cha = bang.get(cur, (0, ""))[0]
        if not cha or cha in cam or cha in da or bang.get(cha, (0, ""))[1] != "cmd.exe":
            return cur
        cur = cha; da.add(cur)


def to_tien(pid: int, bang: dict[int, tuple[int, str]]) -> set[int]:
    kq, cur = {pid}, pid
    while (cha := bang.get(cur, (0, ""))[0]) and cha not in kq:
        kq.add(cha); cur = cha
    return kq


def tat_app(cong: int) -> tuple[bool, str]:
    import subprocess
    pids = pid_nghe_cong(cong)
    if not pids:
        return True, "Đã tắt sẵn"
    bang = bang_tien_trinh()
    cam = to_tien(os.getpid(), bang)
    goc = {goc_can_giet(p, bang, cam) for p in pids} - cam
    if not goc:
        return False, "Không tắt được: app chạy chung tiến trình với máy phát video"
    for p in goc:
        subprocess.run(["taskkill", "/PID", str(p), "/T", "/F"], capture_output=True, timeout=15,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print("TAT APP cong", cong, "pid", p, flush=True)
    han = time.monotonic() + CHO_TAT
    while time.monotonic() < han:
        if not cong_song(cong, 0.5):
            return True, "Đã tắt"
        time.sleep(0.3)
    return False, "Đã gửi lệnh tắt nhưng cổng vẫn mở"


def bat_app(ma: str, cong: int) -> tuple[bool, str]:
    import subprocess
    if cong_song(cong):
        return True, "Đang chạy sẵn"
    lenh = LENH_BAT[ma]
    file_chay = Path(lenh[-1])
    if not file_chay.exists():
        return False, f"Không thấy {file_chay}"
    # Cửa sổ riêng, nhóm tiến trình riêng: tắt/khởi động lại video_server không kéo app chết theo.
    co = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        subprocess.Popen(lenh, cwd=str(file_chay.parent), creationflags=co, close_fds=True)
    except OSError as e:
        return False, f"Không chạy được: {e}"
    print("BAT APP", ma, flush=True)
    return True, "Đang bật — bấm Kiểm lại sau vài giây"


def bat_tat(ma: str, hanh_dong: str) -> tuple[int, dict]:
    app = next((a for a in APPS if a[0] == ma), None)
    if not app or ma not in LENH_BAT:
        return 404, {"loi": "App không bật/tắt được từ web"}
    ok, tin = bat_app(ma, app[2]) if hanh_dong == "bat" else tat_app(app[2])
    return (200 if ok else 500), {"ma": ma, "ok": ok, "tin": tin, "song": cong_song(app[2])}


class H(BaseHTTPRequestHandler):
    khoa = ""
    cong = int(os.environ.get("KHO_VIDEO_PORT", "8787"))

    def log_message(self, fmt, *a):
        print(self.log_date_time_string(), self.address_string(), fmt % a, flush=True)

    def _json(self, code, obj):
        import json
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _vao(self):
        """Trả (id, hành động, query) nếu hợp lệ, ngược lại đã trả lỗi và trả None."""
        if re.match(r"/p(/|$)", urlparse(self.path).path):  # poster_web.xu_ly tự kiểm x-key
            return "", "poster", {}
        if not hmac.compare_digest(self.headers.get("x-key", ""), self.khoa):
            self._json(401, {"loi": "Sai khoá"}); return None
        u = urlparse(self.path)
        if u.path == "/suc-khoe":
            return "", "suc-khoe", parse_qs(u.query)
        m = re.fullmatch(r"/app/([a-z_]{1,20})/(bat|tat)", u.path)
        if m:
            return m[1], "app-" + m[2], {}
        if u.path == "/r" or u.path.startswith("/r/"):
            return "", "runner", {}
        m = re.fullmatch(r"/v/([^/]+)/(ds|file|xoa|dy|dyfile|xem|tien-do|anh|clip)", u.path)
        if not m or not RE_ID.match(m[1]):
            self._json(404, {"loi": "Đường dẫn không hợp lệ"}); return None
        return m[1], m[2], parse_qs(u.query)

    def _chon(self, id_, q):
        ten = unquote((q.get("ten") or [""])[0])
        goc = (q.get("goc") or [None])[0]
        return next((f for ten_hien, f in ds_video(id_, goc) if ten_hien == ten), None)

    def do_GET(self):
        r = self._vao()
        if not r: return
        id_, act, q = r
        if act == "runner":
            return chuyen_tiep_runner(self, "GET")
        if act == "poster": return poster_web.xu_ly(self, "GET")
        if act == "suc-khoe":
            return self._json(200, suc_khoe(self.cong))
        if act == "tien-do":
            return self._json(200, {"thu_muc": tien_do(id_)})
        if act == "xem":  # chỉ xem, không bao giờ xóa — bỏ qua mọi tham số khác (kể cả xoa)
            f = self._chon(id_, q)
            if not f: return self._json(404, {"loi": "Không thấy video"})
            return gui_file_range(self, f)
        if act == "anh":  # ảnh khung của clip phủ (chỉ đọc)
            k = _mot(q, "k")
            if not RE_K_ANH.fullmatch(k):
                return self._json(400, {"loi": "k phải là 0-9 hoặc cs"})
            c = tim_clip(id_, q)
            f = file_anh(*c, k) if c else None
            if not f: return self._json(404, {"loi": "Không thấy ảnh"})
            return gui_anh(self, f)
        if act == "clip":  # xem thử clip phủ: Range, không attachment, không bao giờ xoá
            c = tim_clip(id_, q)
            f = file_clip(*c) if c else None
            if not f: return self._json(404, {"loi": "Không thấy clip"})
            return gui_file_range(self, f)
        if act == "dy":
            return self._json(200, {"video": [{"ten": f.name, "mb": round(f.stat().st_size / 1e6, 1)} for f in ds_douyin(id_)]})
        if act == "dyfile":
            ten = unquote((q.get("ten") or [""])[0])
            f = next((f for f in ds_douyin(id_) if f.name == ten), None)
            if not f: return self._json(404, {"loi": "Không thấy video Douyin"})
            return gui_file_range(self, f)
        if act == "ds":
            # stat một lần; file vừa bị request khác xoá (giữa lúc liệt kê và stat) thì bỏ qua,
            # để ds / chi_tiet / tong cùng dựa trên đúng danh sách file còn sống.
            ds = []
            for g, t, f in ds_nguon(id_):
                try:
                    st = f.stat()
                except OSError:
                    continue
                ds.append((g, t, st))
            nguon = []
            for g in dict.fromkeys(x[0] for x in ds):
                ng = [x for x in ds if x[0] == g]
                chi_tiet = [{"ten": t, "mb": round(st.st_size / 1e6, 1), "sua_luc": int(st.st_mtime)} for _, t, st in ng]
                nguon.append({"goc": g, "tong": len(ng), "ten": ng[0][1], "mb": chi_tiet[0]["mb"],
                              "ds": [c["ten"] for c in chi_tiet], "chi_tiet": chi_tiet})
            return self._json(200, {"tong": len(ds), "ten": ds[0][1] if ds else None,
                                    "mb": nguon[0]["mb"] if ds else 0, "nguon": nguon,
                                    "co_folder": thu_muc_output(id_) is not None})
        if act == "file":
            f = self._chon(id_, q)
            if not f: return self._json(404, {"loi": "Không thấy video"})
            self.send_response(200)
            self.send_header("content-type", "video/mp4")
            self.send_header("content-length", str(f.stat().st_size))
            self.send_header("content-disposition", f"attachment; filename*=UTF-8''{quote(next(t for g, t, p in ds_nguon(id_) if p == f))}")
            self.end_headers()
            try:
                with open(f, "rb") as fh:
                    while chunk := fh.read(1 << 20):
                        self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                print("NGAT GIUA CHUNG, giu lai", f.name, flush=True)
                return
            if (q.get("xoa") or [""])[0] == "1":  # gửi trọn vẹn rồi mới xóa; bị ngắt thì giữ file
                try:
                    xoa_cap(f)
                except OSError as e:
                    print("XOA LOI", f, e, flush=True)
            return
        self._json(405, {"loi": "Sai phương thức"})

    def do_POST(self):
        r = self._vao()
        if not r: return
        id_, act, q = r
        if act == "runner":
            return chuyen_tiep_runner(self, "POST")
        if act == "poster": return poster_web.xu_ly(self, "POST")
        if act in ("app-bat", "app-tat"):
            return self._json(*bat_tat(id_, act[4:]))
        if act != "xoa": return self._json(405, {"loi": "Sai phương thức"})
        f = self._chon(id_, q)
        if not f: return self._json(404, {"loi": "Không thấy video"})
        try:
            xoa_cap(f)
        except OSError as e:
            print("XOA LOI", f, e, flush=True)
            return self._json(500, {"loi": f"Không xóa được: {e}"})
        self._json(200, {"da_xoa": f.name, "con_lai": len(ds_video(id_))})

    def _ghi_khac(self):  # PUT/PATCH/DELETE: chỉ /p/*, path khác 405
        r = self._vao()
        if r: return poster_web.xu_ly(self, self.command) if r[1] == "poster" else self._json(405, {"loi": "Sai phương thức"})
    do_PUT = do_PATCH = do_DELETE = _ghi_khac


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    H.khoa = lay_khoa()
    port = int(os.environ.get("KHO_VIDEO_PORT", "8787"))
    H.cong = port
    print(f"Phát video từ {'; '.join(map(str, GOCS))} tại 127.0.0.1:{port} · khoá ở {KEY_FILE}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
