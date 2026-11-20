"""Lõi tra cứu + kiểm bản sửa video (docs/sua-video.md §3, §4.2, §5.1–5.2; D10). Chỉ stdlib.

Module THUẦN: không import engine, không ghi đĩa. `sua_video_engine.py` (chạy bằng Python engine) import lại
module này để hai bên dùng chung một luật tra cứu.

Định dạng dữ liệu engine (chỉ đọc, xem §1.2):
- luồng C: `<P>/<output|output_poster>/render_batch.json` = {version:1, plans:[asdict(TimelinePlan)], options, config}
  + `<stem>.done.json` = {key, output:[đường dẫn, size, mtime_ns]};
- luồng A: `<P>/<output_daonguoc|output-adam>/<B>_plan.json` = [TimelinePlan.to_dict()], video `<B>_<ma>.mp4`,
  bản trong `output_poster` là hardlink.

Đường dẫn tuyệt đối trong dữ liệu có thể đã cũ (thư mục dự án bị đổi tên) → `doi_goc` (§3.4).
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

from .du_an import ma_du_an
from .kieu import ThamSoLoi

log = logging.getLogger(__name__)

THU_MUC = ("output_poster", "output")            # cùng thứ tự với tools/video_server.py THU_MUC
OUT_A = ("output_daonguoc", "output-adam")       # nơi mẻ Adam ghi bản gốc (autovideo_audio_take.py)
DUOI = {".mp4", ".mov", ".m4v"}                  # cùng tools/video_server.py DUOI (để liệt kê khớp tab Duyệt)

RE_TEN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z_.()\- ]{0,150}\.mp4$", re.ASCII)
RE_A = re.compile(r"^(\d{8}-[0-9A-Za-z-]+)_([a-z]+\d+)\.mp4$", re.ASCII)
RE_MA_VIDEO = re.compile(r"^[0-9a-f]{16}$", re.ASCII)
RE_SHA = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
RE_VIEC = re.compile(r"^j\d{14}[a-z0-9]{4}$", re.ASCII)
RE_CLIP_ID = re.compile(r"^(.+?_\d{3})_")
RE_GOP_DAU = re.compile(r"\s+([,.!?])")

BODY_TOI_DA = 16 * 1024
PHU_DE_TOI_DA = 30
CHU_TOI_DA = 200
DOI_CLIP_TOI_DA = 10
DOI_CHO_TOI_DA = 3
UNG_VIEN_TOI_DA = 60
_VARIANT_MAX = 8                                 # = ctx_match._VARIANT_MAX của engine
_CAM_KY_TU = set("{}\\<>")
_CAM_BIDI = {chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A), 0x200E, 0x200F, 0x061C)}
_KHOA_BODY = {"sua_luc", "phu_de_sha", "phu_de", "doi_clip", "doi_cho", "boi"}


# ---------------- lỗi + kiểu ----------------

class KhongTraDuoc(Exception):
    """Không lần được video → bản ghi nguồn. `.ly_do` là câu tiếng Việt hiện lên web."""

    def __init__(self, ly_do: str):
        super().__init__(ly_do)
        self.ly_do = ly_do


class BanSuaQuaLon(ThamSoLoi):
    """Body bản sửa quá 16 KB — API trả 413."""
    ma_http = 413


class BanSuaLech(ThamSoLoi):
    """`sua_luc` hoặc `phu_de_sha` lệch dữ liệu hiện tại — API trả 409."""
    ma_http = 409


@dataclass(frozen=True)
class VideoSua:
    ma_video: str
    du_an: str
    goc: str
    thu_muc: str
    ten: str
    duong_dan: Path
    sua_luc: int            # mtime tính bằng mili giây (st_mtime_ns // 1e6)
    luong: str              # "C" | "A" | ""
    sua_duoc: bool
    ly_do: str


@dataclass(frozen=True)
class BanGhi:
    luong: str
    nguon: Path             # render_batch.json | <B>_plan.json
    chi_so: int             # vị trí plan trong danh sách của nguồn
    plan: dict              # đã đổi gốc; luồng C có "take_path"
    goc_cu: str | None
    take: Path
    phu_de: Path            # <take>.subtitles.json
    file_ra: Path           # file video thật sẽ bị thay
    lien_ket: Path | None   # output_poster/<ten> nếu khác file_ra
    tien_to: str | None
    me: str | None
    ma: str | None
    tuy_chon: dict
    cau_hinh: dict
    bien_the: bool
    canh_bao: tuple[str, ...] = field(default=())


# ---------------- tiện ích ----------------

def _la_int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _la_so(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _json_chuan(d: object) -> str:
    """Cùng công thức `danh_muc.tham_so_chuan` (không import danh_muc để module nhẹ)."""
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _doc_json(path: Path, bo_nho: dict | None = None) -> object:
    """Đọc JSON; lỗi đọc/giải mã → KhongTraDuoc. `bo_nho` cache theo (đường dẫn, size, mtime_ns) trong một lượt."""
    try:
        st = path.stat()
        khoa = (str(path), st.st_size, st.st_mtime_ns)
        if bo_nho is not None and khoa in bo_nho:
            return bo_nho[khoa]
        data = json.loads(path.read_bytes().decode("utf-8-sig"))
    except FileNotFoundError as e:
        raise KhongTraDuoc(f"Không có {path.name}") from e
    except OSError as e:
        log.warning("không đọc được %s: %s", path, e)
        raise KhongTraDuoc(f"Không đọc được {path.name}") from e
    except ValueError as e:  # JSONDecodeError, UnicodeDecodeError
        log.warning("JSON hỏng %s: %s", path, e)
        raise KhongTraDuoc(f"{path.name} hỏng (không phải JSON hợp lệ)") from e
    if bo_nho is not None:
        bo_nho[khoa] = data
    return data


def _ten_file(src: str) -> str:
    return PureWindowsPath(src).name


def _goc_du_an(nguon: Path) -> Path:
    """P từ file nguồn: <P>/<thư mục>/render_batch.json hoặc <P>/<out>/<B>_plan.json."""
    return nguon.parent.parent


def _tuong_doi(path: Path, p: Path) -> str:
    try:
        return path.relative_to(p).as_posix()
    except ValueError:
        return path.name


def ma_video(ma_du_an: str, thu_muc: str, ten: str) -> str:
    return hashlib.sha1(f"{ma_du_an}/{thu_muc}/{ten}".encode("utf-8")).hexdigest()[:16]


# ---------------- đổi gốc (§3.4) ----------------

def doi_goc(chuoi: str, goc_cu: str | None, p: Path) -> str:
    """Chuỗi bắt đầu bằng `goc_cu` (không phân biệt hoa thường, chuẩn hoá `\\`, đúng ranh giới thư mục) → thay bằng P."""
    if not chuoi or not goc_cu:
        return chuoi
    n = chuoi.replace("\\", "/")
    g = goc_cu.replace("\\", "/").rstrip("/")
    if not g:
        return chuoi
    if n.lower() == g.lower():
        return str(p)
    if n[:len(g) + 1].lower() != (g + "/").lower():
        return chuoi
    phan = [x for x in n[len(g) + 1:].split("/") if x and x != "."]
    if ".." in phan:
        return chuoi
    return str(Path(p, *phan))


def _goc_cu_tu_take(take: str, luong: str) -> str | None:
    """Thư mục dự án lúc dựng: cha của `takes/` (C) hoặc cha của `voice/_takes/` (A). Không rõ → None (không đổi)."""
    w = PureWindowsPath(take)
    cha = list(w.parents)
    for k, d in enumerate(cha[:-1]):
        if luong == "A":
            if d.name.lower() == "_takes" and k + 1 < len(cha) - 1 and cha[k + 1].name.lower() == "voice":
                return str(cha[k + 2])
        elif d.name.lower() == "takes":
            return str(cha[k + 1])
    return None


def _tim_file(src: str) -> str | None:
    """File có thật? Không thì thử cách `render.py:796-811` (cuts/ phẳng ↔ cuts/<thư mục con>/)."""
    if not src:
        return None
    f = Path(src)
    try:
        if f.is_file():
            return src
        if f.parent.parent.name.lower() == "cuts":
            c = f.parent.parent / f.name
            if c.is_file():
                return str(c)
        if f.parent.name.lower() == "cuts" and f.parent.is_dir():
            for sub in sorted(f.parent.iterdir()):
                if sub.is_dir() and not sub.name.startswith("."):
                    c = sub / f.name
                    if c.is_file():
                        return str(c)
    except OSError as e:
        log.warning("không dò được %s: %s", src, e)
    return None


def _doi_goc_plan(plan: dict, goc_cu: str | None, p: Path, co_take_path: bool) -> dict:
    """Bản sao plan đã đổi gốc take_path / segments[].src / bgm_path; kiểm mọi file nguồn có thật."""
    moi = copy.deepcopy(plan)
    segs = moi.get("segments")
    if not isinstance(segs, list) or not segs:
        raise KhongTraDuoc("Plan không có đoạn nào")
    thieu: list[str] = []
    if co_take_path:
        tp = moi.get("take_path")
        if not isinstance(tp, str) or not tp:
            raise KhongTraDuoc("Plan thiếu take_path")
        moi["take_path"] = doi_goc(tp, goc_cu, p)
        if not Path(moi["take_path"]).is_file():
            thieu.append(_ten_file(tp))
    for k, s in enumerate(segs):
        if not isinstance(s, dict) or not isinstance(s.get("src"), str) or s.get("kind") not in ("BASE", "OVL"):
            raise KhongTraDuoc(f"Đoạn {k} của plan sai định dạng")
        if not _la_so(s.get("out_start")) or not _la_so(s.get("out_end")):
            raise KhongTraDuoc(f"Đoạn {k} của plan thiếu giờ")
        moi_src = doi_goc(s["src"], goc_cu, p)
        thay = _tim_file(moi_src)
        if thay is None:
            if _ten_file(s["src"]) not in thieu:
                thieu.append(_ten_file(s["src"]))
        else:
            s["src"] = thay
    if isinstance(moi.get("bgm_path"), str):
        moi["bgm_path"] = doi_goc(moi["bgm_path"], goc_cu, p)
    if thieu:
        raise KhongTraDuoc(f"Thiếu {len(thieu)} file nguồn: {', '.join(thieu[:5])}")
    return moi


# ---------------- tra cứu (§3.2, §3.3) ----------------

def _tien_to(plan: dict, cau_hinh: dict) -> str | None:
    """Thứ tự `render.py:768`: plan.output_prefix → config.prefix → config.image_options.prefix → 'output'."""
    io = cau_hinh.get("image_options")
    io_prefix = io.get("prefix") if isinstance(io, dict) else None
    t = plan.get("output_prefix") or cau_hinh.get("prefix") or io_prefix or "output"
    return t if isinstance(t, str) else None


def _tra_c(p: Path, v: VideoSua, bo_nho: dict | None) -> BanGhi:
    d = v.duong_dan.parent
    rb = d / "render_batch.json"
    data = _doc_json(rb, bo_nho)
    if not isinstance(data, dict) or not _la_int(data.get("version")) or data["version"] != 1:
        raise KhongTraDuoc("render_batch.json không phải phiên bản 1")
    plans, cfg, opts = data.get("plans"), data.get("config") or {}, data.get("options") or {}
    if not isinstance(plans, list) or not isinstance(cfg, dict) or not isinstance(opts, dict):
        raise KhongTraDuoc("render_batch.json sai định dạng")
    khop: list[tuple[int, str]] = []
    for k, pl in enumerate(plans):
        if not isinstance(pl, dict) or not _la_int(pl.get("plan_id")) or pl["plan_id"] < 0:
            continue
        t = _tien_to(pl, cfg)
        if t is not None and f"{t}_{pl['plan_id']:03d}.mp4" == v.ten:  # so cả chuỗi: "_0061" ≠ plan 61
            khop.append((k, t))
    if not khop:
        raise KhongTraDuoc("Tên video không khớp plan nào trong render_batch.json (có thể thuộc mẻ cũ hơn)")
    if len(khop) > 1:
        raise KhongTraDuoc("Nhiều plan cùng tên video trong render_batch.json")
    chi_so, tien_to = khop[0]
    plan = plans[chi_so]
    if plan.get("status") == "LOI":
        raise KhongTraDuoc("Plan của video này bị cổng chống trùng đánh LOI")
    # Chứng minh nguồn gốc: .done.json khớp size + mtime_ns hiện tại (không so đường dẫn — thư mục có thể đổi tên).
    ly_do_cu = "Không chứng minh được video này sinh từ bản ghi còn lưu (có thể thuộc mẻ cũ hơn)"
    try:
        done = _doc_json(d / f"{Path(v.ten).stem}.done.json", bo_nho)
    except KhongTraDuoc as e:
        raise KhongTraDuoc(ly_do_cu) from e
    st = v.duong_dan.stat()
    out = done.get("output") if isinstance(done, dict) else None
    if (not isinstance(out, list) or len(out) != 3 or not _la_int(out[1]) or not _la_int(out[2])
            or out[1] != st.st_size or out[2] != st.st_mtime_ns):
        raise KhongTraDuoc(ly_do_cu)
    tp = plan.get("take_path")
    if not isinstance(tp, str) or not tp:
        raise KhongTraDuoc("Plan thiếu take_path")
    goc_cu = _goc_cu_tu_take(tp, "C")
    moi = _doi_goc_plan(plan, goc_cu, p, co_take_path=True)
    take = Path(moi["take_path"])
    rc = cfg.get("reuse_count")
    bien_the = bool(cfg.get("variation_enabled")) and _la_so(rc) and rc >= 2
    return BanGhi(luong="C", nguon=rb, chi_so=chi_so, plan=moi, goc_cu=goc_cu, take=take,
                  phu_de=take.with_name(take.stem + ".subtitles.json"), file_ra=v.duong_dan, lien_ket=None,
                  tien_to=tien_to, me=None, ma=None, tuy_chon=dict(opts), cau_hinh=dict(cfg), bien_the=bien_the)


def _tra_a(p: Path, v: VideoSua, bo_nho: dict | None) -> BanGhi:
    m = RE_A.fullmatch(v.ten)
    if not m:
        raise KhongTraDuoc("Tên video không theo mẫu mẻ Adam")
    me, ma = m.group(1), m.group(2)
    st_v = v.duong_dan.stat()
    chon: tuple[str, Path, tuple[str, ...]] | None = None
    ly_do = f"Không thấy bản gốc của video trong {' / '.join(OUT_A)}"
    for out in OUT_A:
        g = p / out / v.ten
        if not g.is_file():
            continue
        if os.path.samefile(g, v.duong_dan):
            chon = (out, g, ())
        elif g.stat().st_size == st_v.st_size:
            chon = (out, g, (f"Bản trong {v.thu_muc} là bản chép, sẽ chép lại",))
        else:
            ly_do = f"Video trong {v.thu_muc} khác bản gốc trong {out}"
            continue
        break
    if chon is None:
        raise KhongTraDuoc(ly_do)
    out, file_ra, canh_bao = chon
    pf = p / out / f"{me}_plan.json"
    data = _doc_json(pf, bo_nho)
    if not isinstance(data, list):
        raise KhongTraDuoc(f"{pf.name} sai định dạng")
    goc_stem = f"{me}_{ma}"
    khop = [k for k, pl in enumerate(data) if isinstance(pl, dict) and isinstance(pl.get("segments"), list)
            and any(isinstance(s, dict) and s.get("kind") == "BASE" and isinstance(s.get("src"), str)
                    and PureWindowsPath(s["src"]).stem == goc_stem for s in pl["segments"])]
    if not khop:
        raise KhongTraDuoc(f"Không thấy plan của {goc_stem} trong {pf.name}")
    if len(khop) > 1:
        raise KhongTraDuoc(f"Nhiều plan cùng {goc_stem} trong {pf.name}")
    if file_ra.stat().st_mtime_ns < pf.stat().st_mtime_ns:
        raise KhongTraDuoc("Plan của mẻ mới hơn video — video có thể thuộc lần dựng cũ")
    plan = data[khop[0]]
    base = next(s for s in plan["segments"] if isinstance(s, dict) and s.get("kind") == "BASE"
                and isinstance(s.get("src"), str) and PureWindowsPath(s["src"]).stem == goc_stem)
    goc_cu = _goc_cu_tu_take(base["src"], "A")
    moi = _doi_goc_plan(plan, goc_cu, p, co_take_path=False)
    take = Path(next(s["src"] for s in moi["segments"]
                     if s.get("kind") == "BASE" and PureWindowsPath(s["src"]).stem == goc_stem))
    return BanGhi(luong="A", nguon=pf, chi_so=khop[0], plan=moi, goc_cu=goc_cu, take=take,
                  phu_de=take.with_name(take.stem + ".subtitles.json"), file_ra=file_ra,
                  lien_ket=v.duong_dan if v.duong_dan != file_ra else None,
                  tien_to=None, me=me, ma=ma, tuy_chon={}, cau_hinh={}, bien_the=False, canh_bao=canh_bao)


def _luong(v_ten: str, d: Path) -> str:
    if RE_A.fullmatch(v_ten):
        return "A"
    return "C" if (d / "render_batch.json").is_file() else ""


def _tra(p: Path, v: VideoSua, bo_nho: dict | None) -> BanGhi:
    if not RE_TEN.fullmatch(v.ten):
        raise KhongTraDuoc("Tên file không hợp lệ để sửa trên web")
    luong = _luong(v.ten, v.duong_dan.parent)
    if luong == "A":
        return _tra_a(p, v, bo_nho)
    if luong == "C":
        return _tra_c(p, v, bo_nho)
    raise KhongTraDuoc("Không có bản ghi dựng (render_batch.json hoặc plan mẻ Adam) cho video này")


def tra_ban_ghi(p: Path, v: VideoSua) -> BanGhi:
    """Video → bản ghi nguồn đã đổi gốc. Không lần được → KhongTraDuoc."""
    return _tra(Path(p), v, None)


def _ds_file(p: Path, goc: Path) -> list[tuple[str, str, Path, os.stat_result]]:
    """[(thu_muc, chuỗi goc như video_server, file, stat)] — không đệ quy, cùng luật liệt kê video_server."""
    kq = []
    for thu_muc in THU_MUC:
        o = p / thu_muc
        g = goc.as_posix() + ("" if thu_muc == "output_poster" else "#" + p.name + "/" + thu_muc)
        try:
            if not o.is_dir():
                continue
            files = sorted((f for f in o.iterdir() if f.is_file() and f.suffix.lower() in DUOI),
                           key=lambda f: f.name.lower())
        except OSError as e:
            log.warning("không liệt kê được %s: %s", o, e)
            continue
        for f in files:
            try:
                kq.append((thu_muc, g, f, f.stat()))
            except OSError as e:  # file vừa bị xoá/đổi tên: bỏ, giống video_server
                log.warning("không stat được %s: %s", f, e)
    return kq


def _lam_video(p: Path, du: str, thu_muc: str, g: str, f: Path, st: os.stat_result,
               bo_nho: dict | None) -> VideoSua:
    v = VideoSua(ma_video=ma_video(du, thu_muc, f.name), du_an=du, goc=g, thu_muc=thu_muc, ten=f.name,
                 duong_dan=f, sua_luc=st.st_mtime_ns // 1_000_000, luong="", sua_duoc=False, ly_do="")
    luong = _luong(f.name, f.parent) if RE_TEN.fullmatch(f.name) else ""
    try:
        _tra(p, v, bo_nho)
        return VideoSua(**{**v.__dict__, "luong": luong, "sua_duoc": True})
    except KhongTraDuoc as e:
        ly_do = e.ly_do
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError) as e:
        # dữ liệu dự án dị dạng ngoài dự kiến: một video hỏng không làm sập cả danh sách
        log.exception("lỗi tra video %s/%s/%s", p, thu_muc, f.name)
        ly_do = f"Lỗi đọc dữ liệu dựng ({type(e).__name__})"
    return VideoSua(**{**v.__dict__, "luong": luong, "ly_do": ly_do})


def ds_video_sua(p: Path, goc: Path) -> list[VideoSua]:
    p, goc = Path(p), Path(goc)
    du = ma_du_an(p)
    bo_nho: dict = {}
    return [_lam_video(p, du, tm, g, f, st, bo_nho) for tm, g, f, st in _ds_file(p, goc)]


def tim_video(p: Path, goc: Path, ma: str) -> VideoSua:
    if not isinstance(ma, str) or not RE_MA_VIDEO.fullmatch(ma):
        raise ThamSoLoi("ma_video phải là 16 ký tự hex")
    p, goc = Path(p), Path(goc)
    du = ma_du_an(p)
    for tm, g, f, st in _ds_file(p, goc):
        if ma_video(du, tm, f.name) == ma:
            return _lam_video(p, du, tm, g, f, st, None)
    raise KhongTraDuoc("Không thấy video này (có thể đã bị xoá hoặc đổi tên)")


# ---------------- phụ đề (§4.1) ----------------

def _gop_dau(text: str) -> str:
    return " ".join(RE_GOP_DAU.sub(r"\1", text).split())


def _take_cua_plan(plan: object, luong: str) -> str | None:
    if not isinstance(plan, dict):
        return None
    if luong == "C":
        tp = plan.get("take_path")
        return tp if isinstance(tp, str) else None
    for s in plan.get("segments") or []:
        if isinstance(s, dict) and s.get("kind") == "BASE" and isinstance(s.get("src"), str):
            return s["src"]
    return None


def _dem_cung_take(b: BanGhi) -> int:
    p = _goc_du_an(b.nguon)
    data = _doc_json(b.nguon)
    plans = data.get("plans") if (b.luong == "C" and isinstance(data, dict)) else data
    if not isinstance(plans, list):
        raise KhongTraDuoc(f"{b.nguon.name} sai định dạng")

    def chuan(s: str) -> str:
        return os.path.normcase(os.path.normpath(doi_goc(s, b.goc_cu, p)))

    cua_minh = chuan(str(b.take))
    dem = 0
    for k, pl in enumerate(plans):
        if k == b.chi_so or not isinstance(pl, dict) or pl.get("status") == "LOI":
            continue
        t = _take_cua_plan(pl, b.luong)
        if t and chuan(t) == cua_minh:
            dem += 1
    return dem


def doc_phu_de(b: BanGhi) -> dict:
    try:
        raw = b.phu_de.read_bytes()
    except FileNotFoundError as e:
        raise KhongTraDuoc("Take chưa có phụ đề (.subtitles.json)") from e
    except OSError as e:
        log.warning("không đọc được %s: %s", b.phu_de, e)
        raise KhongTraDuoc("Không đọc được phụ đề của take") from e
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except ValueError as e:
        raise KhongTraDuoc("Phụ đề của take hỏng (không phải JSON hợp lệ)") from e
    sens = data.get("sentences") if isinstance(data, dict) else None
    if not isinstance(sens, list):
        raise KhongTraDuoc("Phụ đề của take sai định dạng (thiếu sentences)")
    cau = []
    for k, s in enumerate(sens):
        if (not isinstance(s, dict) or not isinstance(s.get("text"), str)
                or not _la_so(s.get("start")) or not _la_so(s.get("end"))):
            raise KhongTraDuoc(f"Phụ đề của take sai định dạng ở câu {k}")
        cau.append({"i": k, "start": s["start"], "end": s["end"], "text": _gop_dau(s["text"])})
    ti = data.get("take_idx")
    if not _la_int(ti):
        ti = b.plan.get("take_idx") if _la_int(b.plan.get("take_idx")) else None
    return {"take": _tuong_doi(b.take, _goc_du_an(b.nguon)), "take_idx": ti,
            "co_words": b.take.with_name(b.take.stem + ".words.json").is_file(),
            "sha": hashlib.sha256(raw).hexdigest(), "bien_the": b.bien_the,
            "so_video_cung_take": _dem_cung_take(b), "cau": cau}


# ---------------- cảnh + kho clip (§5.1) ----------------

def doc_canh(b: BanGhi, p: Path) -> list[dict]:
    kq = []
    for k, s in enumerate(b.plan["segments"]):
        kind = s["kind"]
        role = s.get("role") if isinstance(s.get("role"), str) else ""
        if kind != "OVL":
            doi, ly_do = False, ("Nền đen (Adam) — không đổi được" if b.luong == "A"
                                 else "Nền (người nói) — không đổi được")
        elif not role:
            doi, ly_do = False, "Đoạn chưa gán vai"
        else:
            doi, ly_do = True, ""
        kq.append({"i": k, "kind": kind, "out_start": s["out_start"], "out_end": s["out_end"], "role": role,
                   "clip": _ten_file(s["src"]), "doi_duoc": doi, "ly_do": ly_do})
    return kq


def _doc_kho(p: Path) -> dict[str, dict]:
    """{tên clip: {role, dur, desc, tags, variant_of, file|None}} từ cuts/clip_index.json (chỉ mục hợp lệ)."""
    cuts = p / "cuts"
    ci = cuts / "clip_index.json"
    if not ci.is_file():
        return {}
    data = _doc_json(ci)
    clips = data.get("clips") if isinstance(data, dict) else None
    if not isinstance(clips, dict):
        raise KhongTraDuoc("cuts/clip_index.json sai định dạng")
    try:
        con = [d for d in sorted(cuts.iterdir()) if d.is_dir() and not d.name.startswith(".")]
    except OSError as e:
        log.warning("không liệt kê được %s: %s", cuts, e)
        con = []
    kho: dict[str, dict] = {}
    for ten, m in clips.items():
        if not isinstance(ten, str) or not RE_TEN.fullmatch(ten) or not isinstance(m, dict):
            continue
        if not isinstance(m.get("role"), str) or not _la_so(m.get("dur")):
            continue
        f = next((c for c in [cuts / ten, *(d / ten for d in con)] if c.is_file()), None)
        vo = m.get("variant_of")
        kho[ten] = {"role": m["role"], "dur": float(m["dur"]),
                    "desc": m.get("desc") if isinstance(m.get("desc"), str) else "",
                    "tags": [t for t in (m.get("tags") or []) if isinstance(t, str)][:8]
                    if isinstance(m.get("tags"), list) else [],
                    "variant_of": vo if isinstance(vo, str) else None, "file": f}
    return kho


def _goc_clip(ten: str, kho: dict[str, dict]) -> str:
    """Lần chuỗi variant_of tới clip gốc (tối đa 8 bước, chống vòng)."""
    cur, da = ten, {ten}
    for _ in range(_VARIANT_MAX):
        vo = (kho.get(cur) or {}).get("variant_of")
        if not vo or vo in da:
            break
        da.add(vo)
        cur = vo
    return cur


def _co_anh(p: Path, ten: str) -> bool:
    m = RE_CLIP_ID.match(ten)
    if not m:
        return False
    d = p / "cuts" / ".index_frames" / m.group(1)
    return (d / "f_00.jpg").is_file() or (d / "contact_sheet.jpg").is_file()


def ung_vien(p: Path, b: BanGhi, seg: int, gioi_han: int = UNG_VIEN_TOI_DA) -> list[dict]:
    p = Path(p)
    canh = doc_canh(b, p)
    if not _la_int(seg) or not 0 <= seg < len(canh):
        raise ThamSoLoi("seg không có trong video")
    if not canh[seg]["doi_duoc"]:
        raise ThamSoLoi(f"Đoạn {seg} không đổi được: {canh[seg]['ly_do']}")
    if not _la_int(gioi_han) or gioi_han < 1:
        raise ThamSoLoi("gioi_han phải là số nguyên dương")
    c = canh[seg]
    can = c["out_end"] - c["out_start"]
    kho = _doc_kho(p)
    ctx = b.plan.get("mode") == "ctx"
    khoa = (lambda t: _goc_clip(t, kho)) if ctx else (lambda t: t)
    dang_dung = {khoa(x["clip"]) for x in canh if x["kind"] == "OVL"}
    kq = []
    for ten, m in kho.items():
        if m["role"] != c["role"] or m["file"] is None:
            continue
        if khoa(ten) in dang_dung:
            dung, ly_do = False, "đã có trong video này"
        elif m["dur"] + 1e-9 < can:
            dung, ly_do = False, f"quá ngắn ({m['dur']:.1f}s < {can:.1f}s)"
        else:
            dung, ly_do = True, ""
        kq.append({"clip": ten, "role": m["role"], "dur": m["dur"], "desc": m["desc"], "tags": m["tags"],
                   "co_anh": _co_anh(p, ten), "dung_duoc": dung, "ly_do": ly_do})
    kq.sort(key=lambda u: (not u["dung_duoc"], abs(u["dur"] - can), u["clip"]))
    return kq[:min(gioi_han, UNG_VIEN_TOI_DA)]


def lap_chi_tiet(p: Path, v: VideoSua, b: BanGhi) -> dict:
    """Dữ liệu thật để `kiem_ban_sua` so. Chỉ kiểu JSON (không Path).

    {ma_video, sua_luc, luong, phu_de: doc_phu_de|None, loi_phu_de, canh: doc_canh, che_do,
     kho_clip: {tên: {role, dur, co_file, goc}}, dai_clip: [độ dài clip còn dùng được của từng đoạn | None]}
    """
    p = Path(p)
    try:
        pd, loi = doc_phu_de(b), ""
    except KhongTraDuoc as e:
        pd, loi = None, e.ly_do
    kho = _doc_kho(p)
    dai: list[float | None] = []
    for s in b.plan["segments"]:
        if s["kind"] != "OVL":
            dai.append(None)
            continue
        m = kho.get(_ten_file(s["src"]))
        dur = m["dur"] if m else (s.get("src_duration") if _la_so(s.get("src_duration")) else 0.0)
        bd = s.get("src_start") if _la_so(s.get("src_start")) else 0.0
        dai.append(dur - bd if dur > 0 else None)
    return {"ma_video": v.ma_video, "sua_luc": v.sua_luc, "luong": b.luong, "phu_de": pd, "loi_phu_de": loi,
            "canh": doc_canh(b, p), "che_do": b.plan.get("mode") or "legacy",
            "kho_clip": {t: {"role": m["role"], "dur": m["dur"], "co_file": m["file"] is not None,
                             "goc": _goc_clip(t, kho)} for t, m in kho.items()},
            "dai_clip": dai}


# ---------------- kiểm bản sửa (§4.2, §5.1, §5.2) ----------------

def _kiem_chu(text: object) -> str:
    """Chữ phụ đề: NFC, bỏ trắng đầu/cuối, 1–200 code point, cấm ký tự điều khiển / `{}\\<>` / `-->`."""
    if not isinstance(text, str):
        raise ThamSoLoi("Chữ phụ đề phải là chuỗi")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as e:
        raise ThamSoLoi("Chữ phụ đề có ký tự không hợp lệ") from e
    s = unicodedata.normalize("NFC", text).strip()
    if not 1 <= len(s) <= CHU_TOI_DA:
        raise ThamSoLoi(f"Mỗi câu phụ đề dài 1–{CHU_TOI_DA} ký tự")
    for ch in s:
        if ch in _CAM_KY_TU or ch in _CAM_BIDI or unicodedata.category(ch) in ("Cc", "Zl", "Zp", "Cs"):
            raise ThamSoLoi("Chữ phụ đề có ký tự cấm (xuống dòng, ký tự điều khiển, { } \\ < >)")
    if "-->" in s:
        raise ThamSoLoi("Chữ phụ đề không được chứa '-->'")
    return s


def _ds(body: dict, khoa: str) -> list:
    x = body.get(khoa)
    if x is None:
        return []
    if not isinstance(x, list):
        raise ThamSoLoi(f"{khoa} phải là danh sách")
    return x


def _kiem_phu_de(ds: list, ct: dict, sha_body: object) -> tuple[list[dict], str]:
    if len(ds) > PHU_DE_TOI_DA:
        raise ThamSoLoi(f"Tối đa {PHU_DE_TOI_DA} câu mỗi lần — sửa ít câu hơn")
    if not ds:
        return [], ""
    pd = ct.get("phu_de")
    if pd is None:
        raise ThamSoLoi(ct.get("loi_phu_de") or "Không đọc được phụ đề của take")
    if pd.get("bien_the"):
        raise ThamSoLoi("Video này dùng biến thể phụ đề — chưa sửa được trên web")
    if not pd.get("co_words"):
        raise ThamSoLoi("Take chưa có bản Whisper — không sửa trên web")
    sha = sha_body.strip().lower() if isinstance(sha_body, str) else ""
    if not RE_SHA.fullmatch(sha):
        raise ThamSoLoi("phu_de_sha phải là 64 ký tự hex")
    if sha != pd["sha"]:
        raise BanSuaLech("Phụ đề đã đổi từ lúc bạn mở — tải lại")
    cu = {c["i"]: c["text"] for c in pd["cau"]}
    sua: dict[int, str] = {}
    for x in ds:
        if not isinstance(x, dict) or set(x) != {"i", "text"}:
            raise ThamSoLoi("Mỗi mục phu_de phải là {i, text}")
        i = x["i"]
        if not _la_int(i) or i not in cu:
            raise ThamSoLoi("Chỉ số câu phụ đề không có thật")
        if i in sua:
            raise ThamSoLoi("Trùng chỉ số câu phụ đề")
        sua[i] = _kiem_chu(x["text"])
    ra = [{"i": i, "text": t} for i, t in sorted(sua.items())
          if t != unicodedata.normalize("NFC", cu[i]).strip()]
    return ra, (sha if ra else "")


def _kiem_seg(seg: object, ct: dict) -> dict:
    canh = ct["canh"]
    if not _la_int(seg) or not 0 <= seg < len(canh):
        raise ThamSoLoi("Đoạn không có trong video")
    c = canh[seg]
    if not c["doi_duoc"]:
        raise ThamSoLoi(f"Đoạn {seg} không đổi được: {c['ly_do']}")
    return c


def _kiem_doi_clip(ds: list, ct: dict) -> list[dict]:
    if len(ds) > DOI_CLIP_TOI_DA:
        raise ThamSoLoi(f"Tối đa {DOI_CLIP_TOI_DA} lần đổi clip mỗi lần")
    kho = ct["kho_clip"]
    ctx = ct.get("che_do") == "ctx"
    moi: dict[int, str] = {}
    for x in ds:
        if not isinstance(x, dict) or set(x) != {"seg", "clip"}:
            raise ThamSoLoi("Mỗi mục doi_clip phải là {seg, clip}")
        c = _kiem_seg(x["seg"], ct)
        if c["i"] in moi:
            raise ThamSoLoi("Một đoạn chỉ đổi clip một lần")
        ten = x["clip"]
        if not isinstance(ten, str) or not RE_TEN.fullmatch(ten):
            raise ThamSoLoi("Tên clip không hợp lệ")
        m = kho.get(ten)
        if m is None or not m["co_file"]:
            raise ThamSoLoi(f"Clip {ten} không có trong kho cuts/")
        if m["role"] != c["role"]:
            raise ThamSoLoi(f"Clip {ten} khác vai ({m['role']} ≠ {c['role']})")
        can = c["out_end"] - c["out_start"]
        if m["dur"] + 1e-9 < can:
            raise ThamSoLoi(f"Clip {ten} quá ngắn ({m['dur']:.1f}s < {can:.1f}s)")
        moi[c["i"]] = ten
    moi = {s: t for s, t in moi.items() if t != ct["canh"][s]["clip"]}
    # trùng trong video MỚI (sau khi áp mọi lần đổi)
    clip_sau = {c["i"]: moi.get(c["i"], c["clip"]) for c in ct["canh"] if c["kind"] == "OVL"}

    def khoa(t: str) -> str:
        return (kho.get(t) or {}).get("goc", t) if ctx else t

    for s, t in moi.items():
        if any(khoa(t) == khoa(t2) for s2, t2 in clip_sau.items() if s2 != s):
            raise ThamSoLoi(f"Clip {t} đã có trong video này")
    return [{"seg": s, "clip": t} for s, t in sorted(moi.items())]


def _kiem_doi_cho(ds: list, ct: dict, seg_doi_clip: set[int]) -> list[list[int]]:
    if len(ds) > DOI_CHO_TOI_DA:
        raise ThamSoLoi(f"Tối đa {DOI_CHO_TOI_DA} cặp đổi chỗ mỗi lần")
    da: set[int] = set()
    ra: list[list[int]] = []
    for x in ds:
        if not isinstance(x, list) or len(x) != 2:
            raise ThamSoLoi("Mỗi mục doi_cho phải là [a, b]")
        ca, cb = _kiem_seg(x[0], ct), _kiem_seg(x[1], ct)
        a, b = ca["i"], cb["i"]
        if a == b:
            raise ThamSoLoi("Đổi chỗ phải là hai đoạn khác nhau")
        if a in da or b in da:
            raise ThamSoLoi("Một đoạn chỉ đổi chỗ một lần")
        if a in seg_doi_clip or b in seg_doi_clip:
            raise ThamSoLoi("Một đoạn không vừa đổi clip vừa đổi chỗ trong cùng một lần")
        for nguon, dich in ((a, cb), (b, ca)):
            dai = ct["dai_clip"][nguon]
            can = dich["out_end"] - dich["out_start"]
            if dai is None or dai + 1e-9 < can:
                raise ThamSoLoi(f"Clip của đoạn {nguon} quá ngắn cho khung đoạn {dich['i']}")
        da |= {a, b}
        ra.append(sorted([a, b]))
    return sorted(ra)


def kiem_ban_sua(body: dict, chi_tiet: dict) -> dict:
    """Kiểm đầy đủ bản sửa với dữ liệu thật (`chi_tiet` = `lap_chi_tiet`). Trả bản chuẩn hoá.

    Lỗi: ThamSoLoi (400) · BanSuaLech (409, sua_luc/phu_de_sha lệch) · BanSuaQuaLon (413).
    """
    if not isinstance(body, dict):
        raise ThamSoLoi("Bản sửa phải là object")
    try:
        co = len(_json_chuan(body).encode("utf-8"))
    except (TypeError, ValueError) as e:
        raise ThamSoLoi("Bản sửa không phải JSON hợp lệ") from e
    if co > BODY_TOI_DA:
        raise BanSuaQuaLon("Sửa ít câu hơn mỗi lần")
    la = set(body) - _KHOA_BODY
    if la:
        raise ThamSoLoi(f"Khoá lạ trong bản sửa: {sorted(la)}")
    sl = body.get("sua_luc")
    if not _la_int(sl) or sl < 0:
        raise ThamSoLoi("sua_luc phải là số nguyên không âm")
    if sl != chi_tiet["sua_luc"]:
        raise BanSuaLech("Video đã đổi từ lúc bạn mở — tải lại")
    phu_de, sha = _kiem_phu_de(_ds(body, "phu_de"), chi_tiet, body.get("phu_de_sha"))
    doi_clip = _kiem_doi_clip(_ds(body, "doi_clip"), chi_tiet)
    doi_cho = _kiem_doi_cho(_ds(body, "doi_cho"), chi_tiet, {x["seg"] for x in doi_clip})
    if not (phu_de or doi_clip or doi_cho):
        raise ThamSoLoi("Không có thay đổi nào")
    return {"ma_video": chi_tiet.get("ma_video", ""), "sua_luc": sl, "phu_de_sha": sha,
            "phu_de": phu_de, "doi_clip": doi_clip, "doi_cho": doi_cho}


def ma_ban_sua(ban_chuan: dict) -> str:
    return "b" + hashlib.sha256(_json_chuan(ban_chuan).encode("utf-8")).hexdigest()[:16]


# ---------------- FX-22: sửa chữ cần mật khẩu (§7.2a) + đọc kết thúc mã 2/5 của bộ chuyển đổi (§6.1) ----------------

LOI_SUA_CHU_CAN_MAT_KHAU = "Sửa chữ phụ đề cần lưu lại và nhập mật khẩu — mở màn Sửa video để lưu lại"
LOAI_BUOC_SUA = ("sua_video", "hoan_tac_sua")    # tên loại việc = tên bước (danh_muc._buoc_*)
_RE_DAU_LOI = re.compile(r"\ABước (\w+) thoát mã (\d+):\n", re.ASCII)
_RE_STDERR_SUA = re.compile(r"^\[sua_video\] mã (\d+): (.*)$", re.MULTILINE)
_TIEN_TO_KQ = "KET_QUA_JSON "
# Câu của sua_video_engine.py khi hoàn nguyên/hoàn tác BỎ QUA có chủ đích (hoan_nguyen_bo_qua / hoan_tac_bo_qua):
# "Hoàn nguyên bỏ qua A, B vì việc khác…" · "Lần hoàn nguyên trước đã bỏ qua A (việc khác…)" ·
# "Dựng hỏng (…); hoàn nguyên bỏ qua A — kiểm tay" · "… hoàn tác bỏ qua phụ đề (việc khác…)" ·
# "Lần hoàn tác trước đã bỏ qua phụ đề (việc khác…)".
_RE_BO_QUA = re.compile(r"(?:hoàn nguyên|hoàn tác)(?: trước)?(?: đã)? bỏ qua (.+?)(?: \(việc khác| vì việc khác| — )",
                        re.IGNORECASE)


def co_sua_chu(ban: object) -> bool:
    """Bản sửa (nội dung bảng ban_sua) có đổi CHỮ phụ đề — phần Worker /luu bắt mật khẩu (D10 Q3, §7.2a)."""
    return isinstance(ban, dict) and bool(ban.get("phu_de"))


def _ly_do_tu_duoi(duoi: str, ma: int) -> tuple[str, list[str]]:
    """(ly_do, canh_bao) từ đuôi log: ưu tiên dòng KET_QUA_JSON cuối; dòng bị cắt/hỏng → dòng stderr
    `[sua_video] mã N: …`; không có gì → ("", [])."""
    for dong in reversed(duoi.splitlines()):
        if not dong.startswith(_TIEN_TO_KQ):
            continue
        try:
            kq = json.loads(dong[len(_TIEN_TO_KQ):])
        except ValueError:
            break
        if isinstance(kq, dict) and isinstance(kq.get("ly_do"), str):
            cb = kq.get("canh_bao")
            return kq["ly_do"], [x for x in cb if isinstance(x, str)] if isinstance(cb, list) else []
        break
    ds = [m.group(2).strip() for m in _RE_STDERR_SUA.finditer(duoi) if int(m.group(1)) == ma]
    return (ds[-1] if ds else ""), []


def doc_ket_thuc_loi(loai: str, loi: object) -> dict | None:
    """Lỗi vòng chạy ghi cho bước sửa video (`Bước <loai> thoát mã N:\\n<đuôi log>`) → khoá thêm vào `ket_qua`.

    Chỉ mã 2 và 5 (§6.1); còn lại → None. Mã 5 + câu "bỏ qua" (hoàn nguyên/hoàn tác bỏ qua có chủ đích vì việc khác
    đã đổi) → `kiem_tay: True` + `bo_qua`; mã 5 khác (dừng giữa lúc thay file…) → `do_dang: True`. Mã 2 →
    `chua_doi_gi: True`. Chỉ đọc chuỗi, không đọc đĩa.
    """
    if loai not in LOAI_BUOC_SUA or not isinstance(loi, str):
        return None
    m = _RE_DAU_LOI.match(loi)
    if m is None or m.group(1) != loai or m.group(2) not in ("2", "5"):
        return None
    ma = int(m.group(2))
    ly_do, canh_bao = _ly_do_tu_duoi(loi[m.end():], ma)
    kq: dict = {"ma_thoat": ma, "kiem_tay": False, "do_dang": False, "chua_doi_gi": False, "bo_qua": [],
                "ly_do_sua": ly_do, "canh_bao_sua": canh_bao}
    if ma == 2:
        kq["chua_doi_gi"] = True
        if loai == "hoan_tac_sua" and "bản mới hơn" in ly_do:
            kq["thong_diep"] = ("Không hoàn tác vì video đã có bản mới hơn sau lần sửa này — chưa đổi gì. Muốn đổi "
                                f"tiếp, mở màn Sửa video và tạo bản sửa mới. Chi tiết: {ly_do}")
        else:
            kq["thong_diep"] = f"Chưa đổi gì: {ly_do or 'xem log việc'}"
        return kq
    bq = _RE_BO_QUA.search(ly_do)
    if bq:
        kq["kiem_tay"] = True
        kq["bo_qua"] = [x.strip() for x in bq.group(1).split(", ") if x.strip()]
        kq["thong_diep"] = (f"Cần kiểm tay: đã bỏ qua {', '.join(kq['bo_qua'])} vì việc khác đã đổi (cố ý, để không "
                            "đè bản mới hơn). Chạy tiếp không giúp được — kiểm phụ đề/bản ghi, muốn sửa "
                            "tiếp thì mở màn Sửa video tạo bản sửa mới.")
        return kq
    kq["do_dang"] = True
    kq["thong_diep"] = (f"Dừng giữa chừng: {ly_do}" if ly_do
                        else "Bộ dựng lại dừng mã 5 nhưng không đọc được lý do — xem log việc rồi kiểm tay")
    return kq


# ---------------- SRT (§4.3 bước 2) ----------------

def _gio_srt(t: float) -> str:
    ms = max(0, int(round(t * 1000)))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _lam_sach_cu(text: str) -> str:
    """Chữ cũ (từ engine) chỉ cần giữ cấu trúc SRT: bỏ xuống dòng/điều khiển, `-->` → `->`."""
    s = "".join(" " if unicodedata.category(ch) in ("Cc", "Zl", "Zp") else ch for ch in text)
    while "-->" in s:
        s = s.replace("-->", "->")
    return " ".join(s.split())


def lap_srt(cau: list[dict], sua: dict[int, str]) -> str:
    """Mỗi câu một cue, giờ = start/end của câu; chữ = bản sửa (đã kiểm lại) hoặc chữ cũ. Câu rỗng bị bỏ."""
    co = {c["i"] for c in cau}
    sach = {}
    for i, t in sua.items():
        if not _la_int(i) or i not in co:
            raise ThamSoLoi("Chỉ số câu phụ đề không có thật")
        sach[i] = _kiem_chu(t)
    khoi = []
    for c in cau:
        chu = sach[c["i"]] if c["i"] in sach else _lam_sach_cu(c["text"])
        if not chu:
            continue
        bd = float(c["start"])
        kt = max(bd, float(c["end"]))
        khoi.append(f"{len(khoi) + 1}\n{_gio_srt(bd)} --> {_gio_srt(kt)}\n{chu}\n")
    return "\n".join(khoi) + ("\n" if khoi else "")


# ---------------- nhật ký (§6.3) ----------------

def duong_nhat_ky(b: BanGhi, viec_id: str) -> Path:
    if not isinstance(viec_id, str) or not RE_VIEC.fullmatch(viec_id):
        raise ThamSoLoi("mã việc không hợp lệ")
    return b.file_ra.parent / "_sua" / f"{viec_id}.json"


def doc_nhat_ky(path: Path) -> dict | None:
    """Không có → None. Hỏng → ValueError (không coi là 'chưa chạy': có thể đã thay file giữa chừng)."""
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        return None
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except ValueError as e:
        raise ValueError(f"nhật ký sửa video hỏng: {path}") from e
    if not isinstance(data, dict):
        raise ValueError(f"nhật ký sửa video không phải object: {path}")
    return data
