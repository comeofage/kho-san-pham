"""vtk.py — chuẩn bị phân tích VIDEO THAM KHẢO (tab "Video tham khảo" trên web kho).

Luồng (kho.py gọi):
  chuan_bi(link, out)   tải video (yt-dlp) → tách cảnh (PySceneDetect) → ảnh giữa mỗi cảnh anh/cNN.jpg
                        → tấm soát soat/soat_K.jpg (mỗi hàng 1 cảnh: đầu | giữa | cuối, để nhìn chuyển động máy)
                        → nhap.json (giờ cảnh đã điền, mô tả để trống)
  Agent Read từng tấm soát, chép nhap.json → phan_tich.json, điền noi_dung / goc_may / co_canh / chuyen_dong
  (được gộp/tách cảnh nếu máy cắt sai — nhớ đánh số lại và giữ ảnh khớp).
  kiem_phan_tich(...)   kho.py vtk-ghi gọi trước khi đẩy lên kho.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

TRUONG_MO_TA = ("noi_dung", "goc_may", "co_canh", "chuyen_dong")
ANH_RONG = 360          # ảnh lên web: rộng 360px
CANH_NGAN_NHAT = 0.4    # cảnh ngắn hơn (giây) gộp vào cảnh trước — thường là chớp hiệu ứng
HANG_MOI_TAM = 6        # số cảnh mỗi tấm soát
DOAN_DAI_NHAT = 5.0     # cảnh liền dài hơn (giây) chia thành đoạn nối tiếp


def _chay(*args: str) -> subprocess.CompletedProcess:
    r = subprocess.run(list(args), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"[LỖI] {args[0]}: {(r.stderr or r.stdout).strip()[-800:]}")
    return r


def co_hinh(video: Path) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=codec_type",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    return "video" in r.stdout


def tai_tikwm(link: str, dich: Path) -> str:
    """Dự phòng cho TikTok: video gắn giỏ hàng yt-dlp chỉ thấy track nhạc (07/10/2026) — tikwm.com trả link
    video thật. Chỉ gửi link video công khai. Gói miễn phí giới hạn 1 lượt/giây. Trả "" nếu được, còn lại là lý do lỗi."""
    import json as _json
    import time
    import urllib.parse
    import urllib.request
    ua = {"User-Agent": "Mozilla/5.0"}
    for lan in range(3):
        try:
            req = urllib.request.Request("https://www.tikwm.com/api/?hd=1&url=" + urllib.parse.quote(link, safe=""), headers=ua)
            with urllib.request.urlopen(req, timeout=30) as r:
                j = _json.load(r)
        except Exception as e:  # mạng
            loi = f"tikwm: {e}"
            time.sleep(2)
            continue
        d = j.get("data") or {}
        if j.get("code") != 0:
            loi = f"tikwm: {j.get('msg')}"
            time.sleep(1.5)
            continue
        if d.get("images"):
            return "bài ảnh trượt (slideshow), không có video"
        url = d.get("hdplay") or d.get("play")
        if not url:
            return "tikwm không trả link video"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=ua), timeout=120) as r:
                dich.write_bytes(r.read())
        except Exception as e:
            return f"tải file từ tikwm lỗi: {e}"
        return ""
    return loi


def tai_video(link: str, out: Path) -> Path:
    """Tải video về out/video.mp4: yt-dlp trước, TikTok không ra hình thì thử tikwm. Có sẵn video.mp4 thì dùng luôn."""
    out.mkdir(parents=True, exist_ok=True)
    dich = out / "video.mp4"
    if dich.exists() and dich.stat().st_size > 0:
        return dich
    r = subprocess.run(
        ["yt-dlp", "-f", "bv*[height<=1080]+ba/b[height<=1080][vcodec!=none]/b[vcodec!=none]", "--merge-output-format", "mp4",
         "--no-playlist", "-o", str(out / "video.%(ext)s"), link],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode == 0 and dich.exists() and co_hinh(dich):
        return dich
    for f in out.glob("video.*"):
        f.unlink()
    loi = (r.stderr or r.stdout).strip()[-400:]
    if re.search(r"tiktok\.com", link, re.I):
        ly_do = tai_tikwm(link, dich)
        if not ly_do and co_hinh(dich):
            return dich
        dich.unlink(missing_ok=True)
        loi = f"yt-dlp: {loi.splitlines()[-1] if loi else '?'}\ntikwm: {ly_do or 'file tải về không có hình'}"
    raise SystemExit(f"[LỖI] không tải được video {link}:\n{loi}\n"
                     f"→ Tải tay video về {dich} rồi chạy lại lệnh (đã có file thì bỏ qua bước tải).")


def thoi_luong(video: Path) -> float:
    r = _chay("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video))
    return round(float(r.stdout.strip()), 3)


def gop_canh_ngan(canh: list[tuple[float, float]], toi_thieu: float = CANH_NGAN_NHAT) -> list[tuple[float, float]]:
    """Gộp cảnh ngắn hơn `toi_thieu` giây vào cảnh trước (cảnh đầu ngắn thì gộp vào cảnh sau)."""
    out: list[list[float]] = []
    for a, b in canh:
        if out and b - a < toi_thieu:
            out[-1][1] = b
        else:
            out.append([a, b])
    if len(out) > 1 and out[0][1] - out[0][0] < toi_thieu:
        out[1][0] = out[0][0]
        out.pop(0)
    return [(round(a, 3), round(b, 3)) for a, b in out]


def chia_doan_dai(canh: list[tuple[float, float]], toi_da: float = DOAN_DAI_NHAT) -> list[tuple[float, float, bool]]:
    """Cảnh liền dài hơn `toi_da` giây (oneshot, tự quay nói chuyện) chia đều thành đoạn ≤ toi_da để vẫn có
    bảng theo giây. Phần tử thứ 3 = True: đoạn NỐI TIẾP cú máy trước, không có nhát cắt."""
    out = []
    for a, b in canh:
        n = max(1, math.ceil((b - a) / toi_da - 1e-9))
        buoc = (b - a) / n
        for j in range(n):
            out.append((round(a + j * buoc, 3), round(b if j == n - 1 else a + (j + 1) * buoc, 3), j > 0))
    return out


def tach_canh(video: Path, tong: float, nguong: float = 27.0) -> list[tuple[float, float, bool]]:
    from scenedetect import ContentDetector, detect
    giay = lambda t: t.seconds if isinstance(getattr(type(t), "seconds", None), property) else t.get_seconds()
    ds = [(giay(s), giay(e)) for s, e in detect(str(video), ContentDetector(threshold=nguong))]
    return chia_doan_dai(gop_canh_ngan(ds) if ds else [(0.0, tong)])


def chup(video: Path, t: float, dst: Path, rong: int = ANH_RONG) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    _chay("ffmpeg", "-y", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(video), "-frames:v", "1",
          "-vf", f"scale={rong}:-2", "-q:v", "4", str(dst))


def dung_tam_soat(hang: list[tuple[str, list[Path]]], dst: Path) -> None:
    """Mỗi hàng: nhãn + 3 ảnh (đầu/giữa/cuối cảnh) xếp ngang."""
    from PIL import Image, ImageDraw
    anh = [[Image.open(p).convert("RGB") for p in ps] for _, ps in hang]
    w, h = anh[0][0].size
    nhan_cao = 28
    tam = Image.new("RGB", (w * 3, (h + nhan_cao) * len(hang)), "white")
    ve = ImageDraw.Draw(tam)
    for k, ((nhan, _), ba) in enumerate(zip(hang, anh)):
        y = k * (h + nhan_cao)
        ve.text((6, y + 6), nhan, fill="black")
        for j, im in enumerate(ba):
            tam.paste(im.resize((w, h)), (j * w, y + nhan_cao))
    dst.parent.mkdir(parents=True, exist_ok=True)
    tam.save(dst, "JPEG", quality=85)


def chuan_bi(link: str, out: Path, vid: str = "") -> dict:
    out = Path(out)
    video = tai_video(link, out)
    tong = thoi_luong(video)
    canh = tach_canh(video, tong)
    nhap = {"vid": vid, "link": link, "thoi_luong": tong, "canh": []}
    hang: list[tuple[str, list[Path]]] = []
    for k, (a, b, noi_tiep) in enumerate(canh, 1):
        ten = f"c{k:02d}.jpg"
        chup(video, (a + b) / 2, out / "anh" / ten)
        ba = []
        for nhan, t in (("dau", a + 0.05), ("giua", (a + b) / 2), ("cuoi", max(a, b - 0.1))):
            p = out / "soat" / "khung" / f"c{k:02d}_{nhan}.jpg"
            chup(video, t, p, rong=240)
            ba.append(p)
        hang.append((f"#{k}  {a:.1f}s - {b:.1f}s  ({b - a:.1f}s){'  NOI TIEP (khong cat)' if noi_tiep else ''}"
                     "   dau | giua | cuoi", ba))
        nhap["canh"].append({"so": k, "bat_dau": a, "ket_thuc": b, "noi_tiep": noi_tiep, "anh": ten,
                             **{t: "" for t in TRUONG_MO_TA}})
    tam = []
    for i in range(0, len(hang), HANG_MOI_TAM):
        p = out / "soat" / f"soat_{i // HANG_MOI_TAM + 1}.jpg"
        dung_tam_soat(hang[i:i + HANG_MOI_TAM], p)
        tam.append(p)
    (out / "nhap.json").write_text(json.dumps(nhap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"video": video, "thoi_luong": tong, "so_canh": len(canh), "tam_soat": tam, "nhap": out / "nhap.json"}


def kiem_phan_tich(d: dict, thu_anh: Path) -> list[str]:
    """Lỗi của phan_tich.json — rỗng là đạt."""
    loi = []
    canh = d.get("canh") or []
    if not canh:
        return ["không có cảnh nào"]
    tong = float(d.get("thoi_luong") or 0)
    truoc = -1.0
    for k, c in enumerate(canh, 1):
        if c.get("so") != k:
            loi.append(f"cảnh thứ {k}: 'so' = {c.get('so')} (phải đánh số liền 1..n)")
        try:
            a, b = float(c["bat_dau"]), float(c["ket_thuc"])
        except (KeyError, TypeError, ValueError):
            loi.append(f"cảnh {k}: thiếu/sai bat_dau, ket_thuc")
            continue
        if not (b > a >= truoc - 0.05):
            loi.append(f"cảnh {k}: thời gian {a}–{b} không tăng dần")
        if tong and b > tong + 0.5:
            loi.append(f"cảnh {k}: ket_thuc {b} vượt độ dài video {tong}")
        truoc = b
        for t in TRUONG_MO_TA:
            if not str(c.get(t) or "").strip():
                loi.append(f"cảnh {k}: chưa điền {t}")
        if not c.get("anh") or not (Path(thu_anh) / c["anh"]).exists():
            loi.append(f"cảnh {k}: không thấy ảnh {c.get('anh')!r} trong {thu_anh}")
    return loi


def chep_anh(d: dict, tu: Path, den: Path) -> None:
    if den.exists():
        shutil.rmtree(den)
    den.mkdir(parents=True)
    for c in d["canh"]:
        shutil.copyfile(Path(tu) / c["anh"], den / c["anh"])
