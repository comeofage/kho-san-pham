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
  GET  /suc-khoe                -> {"luc": ISO giờ máy, "apps": [{ma, ten, cong, song}]} (dò cổng TCP 127.0.0.1)
  GET|POST /r/<...>             -> chuyển tiếp sang runner KHO_RUNNER_ORIGIN (mặc định 127.0.0.1:8788), bỏ tiền tố /r;
                                   lọc path/query/body/header theo docs/bo-chay-viec.md §3.2, không chuyển x-key
  (ds: mỗi phần tử nguon[] có thêm "chi_tiet": [{ten, mb, sua_luc}] theo thứ tự ds)
"""
import hmac, os, re, secrets, socket, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, parse_qs

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
                  r"|viec(/j\d{14}[a-z0-9]{4}(/(log|tra-loi|duyet|tu-choi|huy|chay-lai|chay-tiep))?)?)$", re.ASCII)
R_QUERY_KHOA = ("tu", "trang_thai", "uid", "gioi_han", "tom_tat")
RE_R_QUERY_GT = re.compile(r"^[A-Za-z0-9_,-]{0,40}$", re.ASCII)
R_HEADER = ("x-runner-key", "x-ky", "x-ky-ngay", "x-ky-nonce")  # + content-type cho POST; KHÔNG BAO GIỜ x-key
R_BODY_TOI_DA = 16 * 1024
R_TRA_TOI_DA = 1024 * 1024
R_XA_TOI_DA = 1024 * 1024  # body quá cỡ nhưng ≤ mức này thì đọc bỏ để client nhận được 413 (không bị RST)


def _loc_query(query: str) -> str:
    """Chỉ giữ khoá cho phép có giá trị hợp lệ; mỗi khoá lấy lần đầu hợp lệ."""
    from urllib.parse import parse_qsl, urlencode
    giu = {}
    for k, v in parse_qsl(query, keep_blank_values=True):
        if k in R_QUERY_KHOA and k not in giu and RE_R_QUERY_GT.fullmatch(v):
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
    q = _loc_query(u.query)
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
    apps = [{"ma": m, "ten": t, "cong": c, "song": s} for (m, t, c), s in zip(APPS, song)]
    apps.append({"ma": "video_server", "ten": "Máy phát video", "cong": cong_video, "song": True})
    return {"luc": datetime.now().astimezone().isoformat(timespec="seconds"), "apps": apps}


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
        if not hmac.compare_digest(self.headers.get("x-key", ""), self.khoa):
            self._json(401, {"loi": "Sai khoá"}); return None
        u = urlparse(self.path)
        if u.path == "/suc-khoe":
            return "", "suc-khoe", parse_qs(u.query)
        if u.path == "/r" or u.path.startswith("/r/"):
            return "", "runner", {}
        m = re.fullmatch(r"/v/([^/]+)/(ds|file|xoa|dy|dyfile|xem|tien-do)", u.path)
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
        if act == "suc-khoe":
            return self._json(200, suc_khoe(self.cong))
        if act == "tien-do":
            return self._json(200, {"thu_muc": tien_do(id_)})
        if act == "xem":  # chỉ xem, không bao giờ xóa — bỏ qua mọi tham số khác (kể cả xoa)
            f = self._chon(id_, q)
            if not f: return self._json(404, {"loi": "Không thấy video"})
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
        if act != "xoa": return self._json(405, {"loi": "Sai phương thức"})
        f = self._chon(id_, q)
        if not f: return self._json(404, {"loi": "Không thấy video"})
        try:
            xoa_cap(f)
        except OSError as e:
            print("XOA LOI", f, e, flush=True)
            return self._json(500, {"loi": f"Không xóa được: {e}"})
        self._json(200, {"da_xoa": f.name, "con_lai": len(ds_video(id_))})


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    H.khoa = lay_khoa()
    port = int(os.environ.get("KHO_VIDEO_PORT", "8787"))
    H.cong = port
    print(f"Phát video từ {'; '.join(map(str, GOCS))} tại 127.0.0.1:{port} · khoá ở {KEY_FILE}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
