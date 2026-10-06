"""kho.py — cầu nối máy nhà ↔ web Kho sản phẩm (repo GitHub này).

Mỗi sản phẩm = 1 thư mục data/<id>/ (id = UID 19 số, hoặc "tam-..." khi link rút gọn chưa phân giải):
  info.json         link, UID, tên, giá, shop, ảnh bìa, tóm tắt, USP, ghi chú, thư mục máy, trạng thái
  bo-canh-quay.md   file 01-BO-CANH-QUAY-1-BUOI.md (skill phantichcanhquay)
  captions.txt      100 caption Poster (skill tao-video-tu-canh-quay, Bước 8)
  bia.jpg           ảnh bìa thu nhỏ

Lệnh (luôn `export PYTHONIOENCODING=utf-8` trên Windows):
  python kho.py them  <link> [--boi TÊN]                 lưu 1 link mới (báo nếu trùng)
  python kho.py cho                                      liệt kê link chờ phân tích (tự phân giải link rút gọn)
  python kho.py ds    [--trang-thai cho|da_phan_tich|da_quay|da_lam_video]
  python kho.py xem   <id|link>                          in info.json
  python kho.py ghi   <id|link> --tu <thư mục dự án> [--bo-kiem-caption]
                                                         đẩy file 01 + dữ liệu SP + USP + caption + ảnh bìa lên kho
  python kho.py lay   <id|link> --out <thư mục dự án> [--ghi-de]
                                                         kéo captions → kich-ban/poster_captions.txt + du_lieu_tho/kho_info.json
  python kho.py quay  <id|link> --loai oneshot|review [--boi TÊN] [--bo]
                                                         đánh dấu đã quay oneshot / review (--bo = gỡ)
  python kho.py video <id|link> --so N                   đánh dấu đã làm video
  python kho.py index                                    dựng lại data/index.json (GitHub Action dùng)

data/index.json do GitHub Action dựng — script này KHÔNG commit index để tránh xung đột.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
TZ = timezone(timedelta(hours=7))
LOAI_QUAY = ("oneshot", "review")
TRANG_THAI = ("cho", "da_phan_tich", "da_quay", "da_lam_video")
NHAN = {"cho": "Chờ xử lý", "da_phan_tich": "Đã phân tích", "da_quay": "Đã quay", "da_lam_video": "Đã làm video"}

_RE_UID = re.compile(r"(?:/pdp/(?:[^/?#]+/)?|/product/|/products/|product_id=)(\d{15,21})")


# ---------- hàm thuần ----------

def bay_gio() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def tach_uid(link: str) -> str | None:
    """UID (product ID) từ link TikTok Shop / EchoTik; None nếu là link rút gọn / không nhận ra."""
    s = (link or "").strip()
    if re.fullmatch(r"\d{15,21}", s):
        return s
    m = _RE_UID.search(s)
    return m.group(1) if m else None


def link_chuan(uid: str) -> str:
    return f"https://shop.tiktok.com/vn/pdp/{uid}"


def kiem_captions(dong: list[str]) -> list[str]:
    """Luật caption Poster (tao-video-tu-canh-quay Bước 8): ≤150 ký tự, đúng 5 hashtag, không số thứ tự đầu dòng."""
    loi = []
    for i, c in enumerate(dong, 1):
        c = c.strip()
        if len(c) > 150:
            loi.append(f"dòng {i}: dài {len(c)} ký tự (> 150)")
        so_tag = len(re.findall(r"#\w+", c))
        if so_tag != 5:
            loi.append(f"dòng {i}: có {so_tag} hashtag (cần đúng 5)")
        if re.match(r"^\s*\d+\s*[.)\-:]", c):
            loi.append(f"dòng {i}: có số thứ tự đầu dòng")
    # Chặn ghép mẫu đầu×đuôi: 1 vế câu (≥4 chữ) xuất hiện ở > 4 dòng.
    dem: dict[str, int] = {}
    for c in dong:
        for ve in {v.strip().lower() for v in re.split(r"[.!?,]", re.sub(r"#\w+", "", c)) if len(v.split()) >= 4}:
            dem[ve] = dem.get(ve, 0) + 1
    for ve, n in sorted(dem.items(), key=lambda x: -x[1]):
        if n > 4:
            loi.append(f"vế \"{ve}\" lặp ở {n} dòng (tối đa 4) — đang ghép mẫu, viết lại cho khác nhau")
    return loi


def da_quay(info: dict, loai: str) -> bool:
    """Đã quay oneshot/review chưa. Dữ liệu cũ chỉ có 1 nút "da_quay" → tính là review."""
    if (info.get(f"da_quay_{loai}") or {}).get("xong"):
        return True
    return loai == "review" and bool((info.get("da_quay") or {}).get("xong"))


def danh_dau_quay(info: dict, loai: str, xong: bool, boi: str) -> None:
    info[f"da_quay_{loai}"] = {"xong": xong, "boi": boi, "luc": bay_gio()}
    info.pop("da_quay", None)


def nhan_trang_thai(info: dict) -> str:
    if (info.get("da_lam_video") or {}).get("xong"):
        return "da_lam_video"
    if any(da_quay(info, l) for l in LOAI_QUAY):
        return "da_quay"
    if info.get("da_phan_tich"):
        return "da_phan_tich"
    return "cho"


def info_moi(id_: str, uid: str | None, link: str, boi: str = "") -> dict:
    return {
        "id": id_, "uid": uid, "link": link,
        "ten": "", "gia": "", "shop": "", "anh_bia": "",
        "tom_tat": "", "usp": None, "ghi_chu": "", "thu_muc_may": "",
        "them_boi": boi, "them_luc": bay_gio(),
        "da_phan_tich": False,
        "da_quay_oneshot": {"xong": False, "boi": "", "luc": ""},
        "da_quay_review": {"xong": False, "boi": "", "luc": ""},
        "da_lam_video": {"xong": False, "so_video": 0, "luc": ""},
        "cap_nhat_luc": bay_gio(),
    }


def _doc_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _ghi_json(p: Path, d) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def tat_ca(data: Path) -> list[dict]:
    if not data.exists():
        return []
    out = []
    for p in sorted(data.glob("*/info.json")):
        try:
            out.append(_doc_json(p))
        except (OSError, json.JSONDecodeError) as e:
            print(f"[!] bỏ qua {p}: {e}", file=sys.stderr)
    return out


def tim(data: Path, khoa: str) -> dict | None:
    """Tìm theo id, UID, hoặc link."""
    khoa = khoa.strip()
    uid = tach_uid(khoa)
    for i in tat_ca(data):
        if i["id"] == khoa or (uid and i.get("uid") == uid) or i.get("link") == khoa:
            return i
    return None


def luu(data: Path, info: dict) -> None:
    info["cap_nhat_luc"] = bay_gio()
    _ghi_json(data / info["id"] / "info.json", info)


def them_link(data: Path, link: str, boi: str = "") -> tuple[dict, bool]:
    """(info, mới?) — trùng UID hoặc trùng nguyên link thì trả bản cũ, không tạo."""
    link = link.strip()
    cu = tim(data, link)
    if cu:
        return cu, False
    uid = tach_uid(link)
    id_ = uid or "tam-" + datetime.now(TZ).strftime("%Y%m%d%H%M%S%f")
    info = info_moi(id_, uid, link, boi)
    luu(data, info)
    return info, True


def doi_sang_uid(data: Path, id_tam: str, uid: str) -> dict:
    """Đổi thư mục tam-... sang UID. UID đã có → gộp ghi chú vào bản cũ, xoá bản tạm."""
    tam = _doc_json(data / id_tam / "info.json")
    dich = data / uid / "info.json"
    if dich.exists():
        cu = _doc_json(dich)
        if tam.get("ghi_chu") and tam["ghi_chu"] not in cu.get("ghi_chu", ""):
            cu["ghi_chu"] = (cu.get("ghi_chu", "") + "\n" + tam["ghi_chu"]).strip()
        luu(data, cu)
        shutil.rmtree(data / id_tam)
        return cu
    (data / id_tam).rename(data / uid)
    tam.update(id=uid, uid=uid)
    luu(data, tam)
    return tam


def _gia_tri(v):
    """EchoTik hay để dict/list dạng chuỗi repr — chỉ nhận chuỗi thường."""
    return v if isinstance(v, (str, int, float)) else ""


def doc_du_lieu_du_an(P: Path) -> dict:
    """Gom dữ liệu SP từ thư mục dự án: sp_pdp.json (du_lieu_sp.py) ưu tiên, rồi san_pham.json (EchoTik)."""
    P = Path(P)
    d: dict = {"uid": None, "ten": "", "gia": "", "shop": "", "anh_bia_url": "", "usp": None,
               "tom_tat": "", "file01": None, "captions": None, "bia_file": None}
    dl = P / "du_lieu_tho"
    if (dl / "sp_pdp.json").exists():
        s = _doc_json(dl / "sp_pdp.json")
        d.update(uid=s.get("product_id"), ten=s.get("ten", ""), gia=s.get("gia", ""),
                 shop=s.get("seller_name", ""))
        bia = (s.get("anh") or {}).get("bia") or []
        d["anh_bia_url"] = bia[0] if bia else ""
    elif (dl / "san_pham.json").exists():
        s = _doc_json(dl / "san_pham.json")
        s = s.get("data", s) if isinstance(s, dict) else s
        seller = s.get("seller")
        imgs = s.get("images")
        d.update(uid=str(s.get("product_id") or "") or None, ten=_gia_tri(s.get("product_name")),
                 gia=_gia_tri(s.get("real_price") or s.get("price")),
                 shop=seller.get("seller_name", "") if isinstance(seller, dict) else "",
                 anh_bia_url=imgs[0] if isinstance(imgs, list) and imgs else "")
    if (dl / "usp.json").exists():
        u = _doc_json(dl / "usp.json")
        d["usp"] = {"cau": u.get("cau", ""), "tu_khoa": u.get("tu_khoa", [])}
    if (dl / "tom-tat-sp.md").exists():
        d["tom_tat"] = (dl / "tom-tat-sp.md").read_text(encoding="utf-8")
    for ten in ("01-BO-CANH-QUAY-1-BUOI.md",):
        if (P / ten).exists():
            d["file01"] = P / ten
    if (P / "kich-ban" / "poster_captions.txt").exists():
        d["captions"] = P / "kich-ban" / "poster_captions.txt"
    anh_khac = sorted((P / "anh").rglob("*bia*.*")) if (P / "anh").exists() else []
    for c in [P / "anh" / "pdp" / "bia_01.jpg", *anh_khac]:
        if c.exists() and c.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            d["bia_file"] = c
            break
    return d


def tao_index(data: Path) -> dict:
    ds = []
    for i in tat_ca(data):
        cap = data / i["id"] / "captions.txt"
        so_cap = sum(1 for x in cap.read_text(encoding="utf-8").splitlines() if x.strip()) if cap.exists() else 0
        ds.append({
            "id": i["id"], "uid": i.get("uid"), "link": i.get("link"), "ten": i.get("ten", ""),
            "gia": i.get("gia", ""), "shop": i.get("shop", ""), "anh_bia": i.get("anh_bia", ""),
            "trang_thai": nhan_trang_thai(i),
            **{f"da_quay_{l}": i.get(f"da_quay_{l}") or {"xong": da_quay(i, l), "boi": "", "luc": ""} for l in LOAI_QUAY},
            "them_boi": i.get("them_boi", ""), "them_luc": i.get("them_luc", ""),
            "cap_nhat_luc": i.get("cap_nhat_luc", ""), "so_caption": so_cap,
            "co_file01": (data / i["id"] / "bo-canh-quay.md").exists(),
        })
    ds.sort(key=lambda x: x.get("them_luc", ""), reverse=True)
    return {"cap_nhat_luc": bay_gio(), "san_pham": ds}


# ---------- git + mạng ----------

def git(*args: str, kiem=True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    if kiem and r.returncode != 0:
        raise SystemExit(f"[LỖI] git {' '.join(args)}:\n{r.stderr.strip()}")
    return r


def keo() -> None:
    if git("remote", kiem=False).stdout.strip():
        git("pull", "--rebase", "--autostash", "-q")


def day(thong_diep: str) -> None:
    git("add", "-A", "data")
    git("reset", "-q", "data/index.json", kiem=False)  # index do Action dựng
    if not git("diff", "--cached", "--quiet", kiem=False).returncode:
        print("(không có gì thay đổi)")
        return
    git("commit", "-q", "-m", thong_diep)
    if not git("remote", kiem=False).stdout.strip():
        print("[!] repo chưa có remote — mới commit local")
        return
    for _ in range(3):
        if git("push", "-q", kiem=False).returncode == 0:
            print("✓ đã đẩy lên GitHub")
            return
        git("pull", "--rebase", "-q")
    raise SystemExit("[LỖI] push thất bại 3 lần")


def phan_giai_link(link: str) -> str | None:
    """Theo redirect link rút gọn (vt.tiktok.com/...) để lấy UID — dò ở MỌI bước chuyển hướng."""
    da_qua: list[str] = []

    class Ghi(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            da_qua.append(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    try:
        req = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.build_opener(Ghi).open(req, timeout=15) as r:
            da_qua.append(r.geturl())
    except Exception as e:  # mạng/captcha — vẫn xét các bước đã qua
        print(f"[!] lỗi mạng khi mở {link}: {e}", file=sys.stderr)
    for u in da_qua:
        uid = tach_uid(u)
        if uid:
            return uid
    print(f"[!] {link} không dẫn tới trang sản phẩm (hết hạn?) — cần link đầy đủ shop.tiktok.com/vn/pdp/<UID>",
          file=sys.stderr)
    return None


def thu_nho_anh(src: Path, dst: Path, canh=480) -> None:
    try:
        from PIL import Image
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((canh, canh))
            im.save(dst, "JPEG", quality=82)
    except ImportError:
        shutil.copyfile(src, dst)


# ---------- lệnh ----------

def _can(khoa: str) -> dict:
    i = tim(DATA, khoa)
    if not i:
        raise SystemExit(f"[LỖI] không có sản phẩm '{khoa}' trong kho — thêm bằng `kho.py them <link>`")
    return i


def lenh_them(a):
    keo()
    info, moi = them_link(DATA, a.link, a.boi)
    if moi:
        day(f"them {info['id']}")
        print(f"✓ đã lưu: {info['id']}  {info['link']}")
    else:
        print(f"[TRÙNG] đã có: {info['id']} — {NHAN[nhan_trang_thai(info)]} — {info.get('ten') or info['link']}")


def lenh_cho(a):
    keo()
    doi = False
    for i in tat_ca(DATA):
        if i.get("uid") is None:
            uid = phan_giai_link(i["link"])
            if uid:
                doi_sang_uid(DATA, i["id"], uid)
                doi = True
    if doi:
        day("phan giai link rut gon")
    cho = [i for i in tat_ca(DATA) if nhan_trang_thai(i) == "cho"]
    if not cho:
        print("Không có link nào chờ.")
    for i in cho:
        print(f"{i['id']}\t{i['link']}\tthêm bởi {i.get('them_boi') or '?'} lúc {i.get('them_luc', '')[:16]}")


def lenh_ds(a):
    keo()
    for i in tat_ca(DATA):
        t = nhan_trang_thai(i)
        if a.trang_thai and t != a.trang_thai:
            continue
        tick = " ".join(f"{l}:{'✓' if da_quay(i, l) else '-'}" for l in LOAI_QUAY)
        print(f"{i['id']}\t{NHAN[t]}\t{tick}\t{i.get('ten') or i['link']}")


def lenh_xem(a):
    keo()
    print(json.dumps(_can(a.khoa), ensure_ascii=False, indent=1))


def lenh_ghi(a):
    keo()
    P = Path(a.tu)
    d = doc_du_lieu_du_an(P)
    i = tim(DATA, a.khoa) or (d["uid"] and tim(DATA, d["uid"]))
    if not i:
        uid = tach_uid(a.khoa) or d["uid"]
        if not uid:
            raise SystemExit("[LỖI] không xác định được UID — truyền link đầy đủ hoặc chạy du_lieu_sp.py trước")
        i, _ = them_link(DATA, link_chuan(uid))
    if i.get("uid") and d["uid"] and str(d["uid"]) != i["uid"]:
        raise SystemExit(f"[LỖI] thư mục {P} là sản phẩm {d['uid']}, không phải {i['uid']} — kiểm tra lại --tu")
    if i.get("uid") is None and d["uid"]:
        i = doi_sang_uid(DATA, i["id"], d["uid"])
    thu = DATA / i["id"]
    for k in ("ten", "gia", "shop", "tom_tat", "usp"):
        if d[k]:
            i[k] = d[k]
    if d["captions"]:
        dong = [x for x in d["captions"].read_text(encoding="utf-8").splitlines() if x.strip()]
        loi = kiem_captions(dong)
        if loi and not a.bo_kiem_caption:
            raise SystemExit("[LỖI] caption chưa đạt (sửa hoặc --bo-kiem-caption):\n  " + "\n  ".join(loi[:20]))
        (thu / "captions.txt").write_text("\n".join(dong) + "\n", encoding="utf-8")
        print(f"  captions: {len(dong)} dòng" + ("" if len(dong) >= 100 else "  [!] ít hơn 100"))
    if d["file01"]:
        shutil.copyfile(d["file01"], thu / "bo-canh-quay.md")
        i["da_phan_tich"] = True
        print("  file 01: ✓")
    if d["bia_file"]:
        thu_nho_anh(d["bia_file"], thu / "bia.jpg")
        i["anh_bia"] = "bia.jpg"
    elif d["anh_bia_url"] and not i.get("anh_bia"):
        i["anh_bia"] = d["anh_bia_url"]
    i["thu_muc_may"] = str(P.resolve()).replace("\\", "/")
    luu(DATA, i)
    day(f"ghi {i['id']}")
    print(f"✓ {i['id']} — {NHAN[nhan_trang_thai(i)]} — {i.get('ten')}")


def lenh_lay(a):
    keo()
    i = _can(a.khoa)
    P = Path(a.out)
    cap = DATA / i["id"] / "captions.txt"
    dich = P / "kich-ban" / "poster_captions.txt"
    if cap.exists():
        if dich.exists() and not a.ghi_de:
            print(f"[!] {dich} đã có — giữ nguyên (thêm --ghi-de để thay)")
        else:
            dich.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cap, dich)
            print(f"  captions → {dich}")
    else:
        print("[!] kho chưa có caption cho sản phẩm này")
    _ghi_json(P / "du_lieu_tho" / "kho_info.json", i)
    print(f"LINK={link_chuan(i['uid']) if i.get('uid') else i['link']}\nUID={i.get('uid') or '(chưa phân giải)'}\nTRANG_THAI={NHAN[nhan_trang_thai(i)]}")


def lenh_quay(a):
    keo()
    i = _can(a.khoa)
    danh_dau_quay(i, a.loai, not a.bo, a.boi)
    luu(DATA, i)
    day(f"quay {a.loai} {i['id']} {'bo' if a.bo else 'xong'}")


def lenh_video(a):
    keo()
    i = _can(a.khoa)
    i["da_lam_video"] = {"xong": True, "so_video": a.so, "luc": bay_gio()}
    luu(DATA, i)
    day(f"video {i['id']} {a.so}")


def lenh_index(a):
    _ghi_json(DATA / "index.json", tao_index(DATA))
    print(f"✓ index: {len(tat_ca(DATA))} sản phẩm")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kho sản phẩm — cầu nối máy nhà ↔ web")
    sp = ap.add_subparsers(dest="lenh", required=True)
    p = sp.add_parser("them"); p.add_argument("link"); p.add_argument("--boi", default="máy nhà"); p.set_defaults(f=lenh_them)
    p = sp.add_parser("cho"); p.set_defaults(f=lenh_cho)
    p = sp.add_parser("ds"); p.add_argument("--trang-thai", choices=TRANG_THAI); p.set_defaults(f=lenh_ds)
    p = sp.add_parser("xem"); p.add_argument("khoa"); p.set_defaults(f=lenh_xem)
    p = sp.add_parser("ghi"); p.add_argument("khoa"); p.add_argument("--tu", required=True)
    p.add_argument("--bo-kiem-caption", action="store_true"); p.set_defaults(f=lenh_ghi)
    p = sp.add_parser("lay"); p.add_argument("khoa"); p.add_argument("--out", required=True)
    p.add_argument("--ghi-de", action="store_true"); p.set_defaults(f=lenh_lay)
    p = sp.add_parser("quay"); p.add_argument("khoa"); p.add_argument("--loai", choices=LOAI_QUAY, required=True)
    p.add_argument("--boi", default="máy nhà")
    p.add_argument("--bo", action="store_true"); p.set_defaults(f=lenh_quay)
    p = sp.add_parser("video"); p.add_argument("khoa"); p.add_argument("--so", type=int, required=True); p.set_defaults(f=lenh_video)
    p = sp.add_parser("index"); p.set_defaults(f=lenh_index)
    a = ap.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
