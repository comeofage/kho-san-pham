"""Bộ chuyển đổi sửa video: áp bản sửa rồi dựng lại ĐÚNG 1 video bằng hàm có sẵn của engine (docs/sua-video.md §6, D10).

Chạy bằng Python của engine (runner lập argv dạng list, cwd = thư mục engine):

    PY sua_video_engine.py ap-dung  --project P --thu-muc output_poster --video <ten> --ban-sua <json> --viec <id> [--xem]
    PY sua_video_engine.py hoan-tac --project P --thu-muc output_poster --video <ten> --viec-goc <id> --viec <id>

Không sửa engine (D10 phương án A): chỉ import `modules.*` và gọi `render_single_plan`, `dung_hau_ky_cho_plan`,
`build_subtitle_json`, `mach_trung_voi_lich_su`, `load_wm_from_project`. Chữ ký các hàm được kiểm lúc chạy (R-9).
Tra cứu video → bản ghi dùng chung `sua_video.py` (B-6).

Mã thoát: 0 xong · 2 bản sửa sai / video đã đổi / engine đổi (không đổi gì) · 3 bận (không đổi gì) ·
4 dựng hỏng (đã hoàn nguyên) · 5 hỏng giữa lúc thay file (nhật ký giữ trạng thái, chạy lại để làm nốt), hoặc
hoàn nguyên phải BỎ QUA mục đã bị việc khác đổi (`hoan_nguyen_bo_qua` trong nhật ký — kiểm tay, không tự làm lại).
`hoan-tac` (FX-21): đã có bản mới hơn ở video / .done.json / mục nguồn / plan.json → mã 2, chưa đổi gì; phụ đề của
take đã bị video khác sửa tiếp → video vẫn về bản cũ, bỏ qua phụ đề (`hoan_tac_bo_qua`), mã 5 kiểm tay.
Dòng stdout cuối: `KET_QUA_JSON {...}`.
"""
from __future__ import annotations

import argparse
import copy
import dataclasses
import filecmp
import hashlib
import importlib.util
import inspect
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

_DAY = Path(__file__).resolve().parent
# Chạy dạng script thì Python tự chèn thư mục runner/ vào sys.path[0]: các file api.py, kieu.py… của runner có thể
# che module cùng tên mà thư viện của engine import. Bỏ đi, chỉ dùng dạng gói `runner.*`.
if sys.path and sys.path[0] and Path(sys.path[0]).resolve() == _DAY:
    sys.path.pop(0)
THU_MUC_ENGINE = Path(os.environ.get("KHO_ENGINE_DIR") or r"F:\auto video oneshot")
for _d in (str(THU_MUC_ENGINE), str(_DAY.parent)):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from runner import sua_video as sv  # noqa: E402
from runner.kieu import ThamSoLoi  # noqa: E402

log = logging.getLogger("kho_runner.sua_video_engine")

SCRIPT_ADAM = Path(os.environ.get("KHO_SCRIPT_ADAM")
                   or r"C:\Users\Mi\.claude\skills\tao-video-tu-canh-quay\scripts\autovideo_audio_take.py")
KHOA_DU_AN = ".render.lock"                                   # = autovideo_audio_take.KHOA_RENDER
KHOA_MAY_MAC_DINH = Path(r"E:\oneshottramcanh\.render-may.lock")
KHOA_HET_HAN, KHOA_NHIP, KHOA_CU_GIAY = 180, 30, 1800          # = KHOA_RENDER_HET_HAN, KHOA_RENDER_NHIP, KHOA_CU_GIAY
CHO_KHOA_GIAY = 600                                            # chờ khoá tối đa 10 phút rồi mã 3
PARTIAL_MOI_GIAY = 600                                         # *.partial.mp4 mới hơn 10 phút = mẻ đang dựng
GIU_SAO_LUU = 3
NGUONG_TRUNG = 4.0                                             # trần mạch trùng của skill (autovideo-oneshot)
THU_LAI = 10                                                   # os.replace thử lại 10 lần × 1 s (= _thay_the)
# Luồng A: tham số mặc định của `autovideo_audio_take.py run` (§6.3 bước 5). Test được hạ để chạy bằng CPU.
KHUNG_A = (1080, 1920, 30)
DISSOLVE_A = 0.1
NVENC_A = True
MODEL_WHISPER = "large-v3-turbo"                               # = mặc định build_subtitle_json
RE_BAN_SUA = re.compile(r"^b[0-9a-f]{16}$", re.ASCII)
BAN_SUA_TOI_DA = 64 * 1024


class Thoat(Exception):
    def __init__(self, ma: int, ly_do: str):
        super().__init__(ly_do)
        self.ma, self.ly_do = ma, ly_do


# ---------------- engine (R-9) ----------------

# hàm engine → tham số bắt buộc phải có (chữ ký đổi = engine đổi phiên bản → từ chối, không hỏng ngầm)
CHU_KY_CAN = {
    ("render", "render_single_plan"): {"plan", "output_folder", "width", "height", "fps", "dissolve", "use_nvenc",
                                       "pad_or_crop", "bgm_volume", "config_snapshot"},
    ("hau_ky", "dung_hau_ky_cho_plan"): {"plan", "subtitle_json_path", "output_folder", "burn_subtitle", "sub_cfg",
                                         "wm_config", "disclaimer_config", "width", "height", "sticker", "punch",
                                         "cart_arrow", "cart_arrow_mode", "project_dir"},
    ("sjb", "build_subtitle_json"): {"take_path", "force", "take_idx"},
    ("sjb", "_words_cache_reason"): {"data", "video_path", "output_json", "model_size", "language"},
    ("anti_trung", "mach_trung_voi_lich_su"): {"plan", "chu_ky_cu", "nguong"},
    ("wm", "load_wm_from_project"): {"project_dir"},
    ("wm", "tim_thu_muc_cau_hinh"): set(),
    ("wm", "co_tu_project"): {"project_dir"},
    ("rc", "write_json"): {"path", "data"},
    ("sr", "sub_cfg_tu_config"): {"config"},
    ("img", "merge_config"): {"cfg", "options"},
    ("cfg", "load_config"): set(),
}
# hằng engine bộ sửa dùng trực tiếp (R-20 P3-2): thiếu = engine đổi phiên bản → mã 2, không AttributeError mã 5
HANG_CAN = {("sjb", "NGON_NGU_MAC_DINH")}
TRUONG_CAN = {"TimelinePlan": {"plan_id", "take_path", "take_idx", "segments", "duration", "seed", "ass_path",
                               "wm_file", "disclaimer_file", "stickers", "punch_times", "cart_arrow_intervals",
                               "warnings"},
              "Seg": {"kind", "out_start", "out_end", "src", "src_start", "src_duration", "role", "zoom", "hflip",
                      "clip", "src_key", "key_start", "evidence", "filler"}}


def nap_engine() -> SimpleNamespace:
    try:
        import modules.anti_trung as anti_trung
        import modules.config as cfg
        import modules.hau_ky as hau_ky
        import modules.image_settings as img
        import modules.render as render
        import modules.render_checkpoint as rc
        import modules.sticker_cta as sticker
        import modules.subtitle_json_builder as sjb
        import modules.subtitle_renderer as sr
        import modules.timeline as timeline
        import modules.wm_settings as wm
    except Exception as e:  # ImportError, lỗi DLL…: báo nguyên văn loại lỗi
        log.exception("không nạp được engine ở %s", THU_MUC_ENGINE)
        raise Thoat(2, f"Không nạp được engine ở {THU_MUC_ENGINE} ({type(e).__name__}: {e})") from e
    return SimpleNamespace(anti_trung=anti_trung, cfg=cfg, hau_ky=hau_ky, img=img, render=render, rc=rc,
                           sticker=sticker, sjb=sjb, sr=sr, timeline=timeline, wm=wm)


def kiem_engine(e: SimpleNamespace) -> None:
    """R-9: đủ hàm + đủ tham số + đủ trường dataclass; thiếu → mã 2 'engine đổi phiên bản'."""
    thieu = []
    for (mod, ten), can in CHU_KY_CAN.items():
        fn = getattr(getattr(e, mod), ten, None)
        if not callable(fn):
            thieu.append(f"{mod}.{ten}")
            continue
        try:
            co = set(inspect.signature(fn).parameters)
        except (TypeError, ValueError):
            thieu.append(f"{mod}.{ten}(chữ ký)")
            continue
        if can - co:
            thieu.append(f"{mod}.{ten}({', '.join(sorted(can - co))})")
    for mod, ten in sorted(HANG_CAN):
        if not hasattr(getattr(e, mod), ten):
            thieu.append(f"{mod}.{ten}")
    for ten, can in TRUONG_CAN.items():
        lop = getattr(e.timeline, ten, None)
        co = {f.name for f in dataclasses.fields(lop)} if dataclasses.is_dataclass(lop) else set()
        if can - co:
            thieu.append(f"timeline.{ten}({', '.join(sorted(can - co))})")
    if thieu:
        raise Thoat(2, "Engine đổi phiên bản — bộ sửa video cần cập nhật: " + "; ".join(thieu[:6]))


# ---------------- tiện ích file ----------------

def _rel(p: Path, f: Path) -> str:
    try:
        return Path(f).relative_to(p).as_posix()
    except ValueError:
        return str(f)                     # ngoài dự án (hiếm): giữ tuyệt đối


def _abs(p: Path, s: str) -> Path:
    return Path(s) if Path(s).is_absolute() else p / s


def _ghi_nguyen_tu(path: Path, noi_dung: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tam = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tam.write_text(noi_dung, encoding="utf-8")
        _thay_the(tam, path)
    finally:
        if tam.exists():
            tam.unlink()


def _ghi_json(path: Path, data: object, indent: int = 1) -> None:
    _ghi_nguyen_tu(path, json.dumps(data, ensure_ascii=False, indent=indent, default=str))


def _doc_json(path: Path) -> object:
    return json.loads(Path(path).read_bytes().decode("utf-8-sig"))


def _thay_the(src: Path, dst: Path, lan: int = THU_LAI) -> None:
    """os.replace thử lại (Windows khoá file khi trình phát / Poster / antivirus đang mở) — như `_thay_the` Adam."""
    for i in range(lan):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == lan - 1:
                raise
            time.sleep(1.0)


def _chep_qua_tam(src: Path, dst: Path) -> None:
    """Chép giữ mtime (copy2) qua file tạm cùng thư mục rồi os.replace — dst không bao giờ dở dang."""
    tam = dst.with_name(f".{dst.name}.{os.getpid()}.tmp")
    try:
        shutil.copy2(src, tam)
        _thay_the(tam, dst)
    finally:
        if tam.exists():
            tam.unlink()


def _sig(f: Path) -> dict:
    st = f.stat()
    return {"size": st.st_size, "mtime_ns": st.st_mtime_ns}


def _khop(f: Path, d: dict | None) -> bool:
    try:
        st = f.stat()
    except FileNotFoundError:
        return False
    return bool(d) and st.st_size == d.get("size") and st.st_mtime_ns == d.get("mtime_ns")


def _sha(f: Path) -> str:
    return hashlib.sha256(f.read_bytes()).hexdigest()


def _dau(f: Path) -> dict | None:
    """Dấu vết file nhỏ (phụ đề, .sua.srt, .done.json): size + mtime_ns + sha. Không có file → None."""
    try:
        st = f.stat()
        sha = _sha(f)
    except FileNotFoundError:
        return None
    return {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha": sha}


def _cung_dau(f: Path, d: dict | None) -> bool:
    """f hiện tại đúng là trạng thái đã ghi lại `d` (None = không có file)."""
    return _dau(f) == d


# ---------------- khoá tương thích KhoaPlan (§6.2) ----------------

def duong_khoa_may() -> Path:
    v = os.environ.get("AUTOVIDEO_KHOA_MAY", "").strip()
    if not v:
        return KHOA_MAY_MAC_DINH
    p = Path(v)
    return p / KHOA_MAY_MAC_DINH.name if p.is_dir() else p


class Khoa:
    """File O_EXCL, JSON {batch, pid, viec, luc, het_han, du_an}, nhịp tim os.utime — cùng định dạng `KhoaPlan`
    (autovideo_audio_take.py), nên mẻ Adam và bộ sửa chờ nhau đúng luật. Khoá cũ = mtime quá `het_han` giây."""

    def __init__(self, f: Path, batch: str, du_an: str):
        self.f, self.batch, self.du_an = Path(f), batch, du_an
        self.giu = False
        self._dung = threading.Event()
        self._luong: threading.Thread | None = None

    def _cu(self) -> tuple[bytes | None, int] | None:
        """Khoá cũ → ảnh chụp (nội dung, mtime_ns) để lúc gỡ đối chiếu đúng là khoá đó; còn hạn / không có → None."""
        try:
            raw: bytes | None = self.f.read_bytes()
        except FileNotFoundError:
            return None
        except OSError:
            raw = None
        try:
            tt = json.loads(raw.decode("utf-8")) if raw is not None else {}
            het = float(tt.get("het_han") or KHOA_CU_GIAY)
        except (ValueError, AttributeError, TypeError):
            het = KHOA_CU_GIAY
        try:
            st = self.f.stat()
        except FileNotFoundError:
            return None
        return (raw, st.st_mtime_ns) if time.time() - st.st_mtime > het else None

    def _go_cu(self, anh: tuple[bytes | None, int]) -> None:
        """R-20 P2-3: không `unlink` thẳng (TOCTOU — giữa lúc thấy cũ và lúc xoá, tiến trình khác có thể đã gỡ và lấy
        khoá mới). Đổi tên khoá sang tên tạm (nguyên tử) rồi đọc lại: đúng khoá cũ đã thấy → xoá; khác → trả về chỗ."""
        tam = self.f.with_name(f"{self.f.name}.go.{os.getpid()}.{time.time_ns()}")
        try:
            os.replace(self.f, tam)
        except FileNotFoundError:
            return                                  # người khác đã gỡ
        except PermissionError as ex:               # đang bị mở: lượt sau thử lại
            log.warning("chưa gỡ được khoá cũ %s: %s", self.f, ex)
            return
        try:
            nay: tuple[bytes | None, int] | None = (tam.read_bytes(), tam.stat().st_mtime_ns)
        except OSError:
            nay = None
        if nay is not None and anh[0] is not None and nay == anh:
            log.warning("gỡ khoá cũ %s", self.f)
            tam.unlink(missing_ok=True)
            return
        log.warning("khoá %s đã đổi từ lúc thấy cũ — trả lại, không gỡ", self.f)
        try:
            os.link(tam, self.f)                    # tạo lại đúng tên, KHÔNG đè nếu đã có khoá khác
        except FileExistsError:
            log.error("không trả lại được khoá %s: đã có khoá khác chiếm chỗ (bản dời ở %s bị bỏ)", self.f, tam)
        except OSError:
            try:
                os.rename(tam, self.f)              # Windows: rename không đè file có sẵn
                return
            except OSError as ex:
                log.error("không trả lại được khoá %s: %s (bản dời giữ ở %s)", self.f, ex, tam)
                return
        tam.unlink(missing_ok=True)

    def _tim(self) -> None:
        while not self._dung.wait(KHOA_NHIP):
            try:
                os.utime(self.f)
            except OSError as e:          # không im lặng: mất nhịp tim → khoá có thể bị coi là cũ
                log.error("không chạm được khoá %s: %s", self.f, e)

    def lay(self, cho_toi_da: float) -> "Khoa":
        t0 = time.time()
        while True:
            try:
                fd = os.open(self.f, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                anh = self._cu()
                if anh is not None:
                    self._go_cu(anh)
                    if not self.f.exists():
                        continue
                if time.time() - t0 >= cho_toi_da:
                    raise Thoat(3, f"Đang có mẻ dựng video ({self.f.name}) — chờ xong rồi bấm Chạy lại") from None
                time.sleep(min(2.0, max(0.05, cho_toi_da / 10)))
                continue
            try:
                os.write(fd, json.dumps({"batch": self.batch, "pid": os.getpid(), "viec": "sửa video",
                                         "luc": time.time(), "het_han": KHOA_HET_HAN,
                                         "du_an": self.du_an}).encode())
            except BaseException:
                os.close(fd)
                self.f.unlink(missing_ok=True)       # không để lại khoá rỗng chặn người khác 30 phút
                raise
            os.close(fd)
            self.giu = True
            self._dung.clear()
            self._luong = threading.Thread(target=self._tim, daemon=True)
            self._luong.start()
            return self

    def tha(self) -> None:
        """Nhả khoá. Lỗi KHÔNG bị nuốt: ném OSError/RuntimeError để bên gọi ghi log + cảnh báo."""
        self._dung.set()
        if self._luong is not None:
            self._luong.join(timeout=5)
        if not self.giu:
            return
        self.giu = False
        try:
            tt = json.loads(self.f.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise RuntimeError(f"khoá {self.f} đã mất trước khi nhả (bị gỡ vì hết hạn?)") from None
        except ValueError as e:
            raise RuntimeError(f"khoá {self.f} không đọc được, không xoá: {e}") from e
        if tt.get("pid") != os.getpid() or tt.get("batch") != self.batch:
            raise RuntimeError(f"khoá {self.f} đang thuộc tiến trình khác (pid {tt.get('pid')}), không xoá")
        self.f.unlink()


def lay_khoa(p: Path, viec: str, cho_toi_da: float) -> list[Khoa]:
    """Dự án → máy (cùng thứ tự với Adam, không deadlock). Lấy hỏng giữa chừng thì nhả cái đã lấy."""
    du_an = str(p)
    k1 = Khoa(p / KHOA_DU_AN, f"sua-{viec}", du_an).lay(cho_toi_da)
    try:
        f2 = duong_khoa_may()
        f2.parent.mkdir(parents=True, exist_ok=True)
        k2 = Khoa(f2, f"sua-{viec}", du_an).lay(cho_toi_da)
    except BaseException:
        tha_khoa([k1], [])
        raise
    return [k1, k2]


def tha_khoa(ds: list[Khoa], canh_bao: list[str]) -> None:
    for k in reversed(ds):
        try:
            k.tha()
        except (OSError, RuntimeError) as e:
            log.error("LỖI nhả khoá %s: %s", k.f, e)
            print(f"[LỖI] nhả khoá {k.f}: {e}", file=sys.stderr, flush=True)
            canh_bao.append(f"Không nhả được khoá {k.f.name}: {e}")


def cho_khoa_giay() -> float:
    v = os.environ.get("KHO_SUA_CHO_KHOA", "").strip()
    try:
        return float(v) if v else float(CHO_KHOA_GIAY)
    except ValueError:
        return float(CHO_KHOA_GIAY)


# ---------------- kiểm bận (§6.2 bước 3, 4) ----------------

def kiem_partial(thu_muc: Path) -> None:
    gio = time.time()
    try:
        ds = list(thu_muc.iterdir())
    except OSError as e:
        raise Thoat(3, f"Không đọc được thư mục video: {e}") from e
    for f in ds:
        if f.name.endswith(".partial.mp4"):
            try:
                if gio - f.stat().st_mtime < PARTIAL_MOI_GIAY:
                    raise Thoat(3, "Mẻ đang dựng trong thư mục này — chờ xong rồi bấm Chạy lại")
            except FileNotFoundError:
                continue


def thu_khoa_file(f: Path) -> None:
    """Đổi tên đi rồi đổi về ngay: Windows từ chối khi file đang mở (đang xem / Poster đang tải) → mã 3."""
    tam = f.with_name(f.name + ".thu-khoa")
    if tam.exists() and not f.exists():             # lần trước chết giữa hai lần đổi tên
        _thay_the(tam, f)
    try:
        os.replace(f, tam)
    except PermissionError as e:
        raise Thoat(3, "Video đang được mở (đang xem hoặc đang đăng) — đóng trình phát rồi bấm Chạy lại") from e
    try:
        _thay_the(tam, f)
    except OSError as e:
        log.error("KHÔNG đổi tên lại được %s → %s: %s", tam, f, e)
        raise Thoat(5, f"Không đổi tên lại được {tam.name} → {f.name} ({e}) — đổi tay rồi chạy lại") from e


# ---------------- bản sửa → plan (§5) ----------------

def _plan_obj(d: dict, e: SimpleNamespace):
    """dict (asdict hoặc to_dict) → TimelinePlan. Khoá lạ / thiếu → mã 2 (engine hoặc dữ liệu đổi định dạng)."""
    d = copy.deepcopy(d)
    pid = d.get("plan_id")
    if isinstance(pid, str):
        d["plan_id"] = int(pid.rsplit("_", 1)[-1])
    if not d.get("take_path"):
        d["take_path"] = next((s["src"] for s in d["segments"] if s.get("kind") == "BASE"), "")
    try:
        d["segments"] = [e.timeline.Seg(**s) for s in d["segments"]]
        d["stickers"] = [e.sticker.StickerEvent(**s) if isinstance(s, dict) else s for s in d.get("stickers") or []]
        return e.timeline.TimelinePlan(**d)
    except TypeError as ex:
        raise Thoat(2, f"Plan không khớp định dạng của engine ({ex})") from ex


def ap_ban_sua(b: sv.BanGhi, p: Path, ban: dict, viec: str) -> tuple[dict, list[int]]:
    """Áp doi_clip / doi_cho vào bản sao plan (chỉ trong bộ nhớ). Trả (plan mới, các đoạn đã đổi)."""
    plan = copy.deepcopy(b.plan)
    segs = plan["segments"]
    doi: list[int] = []
    if ban["doi_clip"]:
        kho = sv._doc_kho(p)                       # cùng luật tìm file với kiem_ban_sua (dùng chung, §2)
        for x in ban["doi_clip"]:
            m = kho.get(x["clip"])
            if m is None or m["file"] is None:
                raise Thoat(2, f"Clip {x['clip']} không còn trong cuts/")
            s = segs[x["seg"]]
            s.update(src=str(m["file"]), clip=x["clip"], src_start=0.0, src_duration=float(m["dur"]), zoom=1.0,
                     hflip=False, evidence=[], filler=False, src_key="", key_start=-1.0)
            doi.append(x["seg"])
    for a_, b_ in ban["doi_cho"]:
        sa, sb = segs[a_], segs[b_]
        for k in ("src", "clip", "src_start", "src_duration", "zoom", "hflip", "variant"):
            if k in sa or k in sb:
                va, vb = sa.get(k), sb.get(k)
                if k == "clip":                      # plan legacy để clip rỗng: lấy tên từ src
                    va = va or sv._ten_file(sa["src"])
                    vb = vb or sv._ten_file(sb["src"])
                sa[k], sb[k] = vb, va
        doi += [a_, b_]
    if doi:
        plan.setdefault("warnings", [])
        plan["warnings"] = list(plan["warnings"] or []) + [f"sua tay tu web {viec}"]
    return plan, sorted(set(doi))


def _ky_hieu_ten(d: dict) -> dict:
    """Ký hiệu chống trùng với đường dẫn chỉ còn TÊN file (đường dẫn cũ có thể đã sai, §5.4)."""
    pid = d.get("plan_id", -1)
    if isinstance(pid, str):
        try:
            pid = int(pid.rsplit("_", 1)[-1])
        except ValueError:
            pid = -1
    if "ovls" in d:                                 # bản ghi ledger
        ovls = [[float(o[0]), float(o[1]), PureWindowsPath(str(o[2])).name, float(o[3])] for o in d["ovls"]]
        take = str(d.get("take_path") or "")
    else:
        segs = d.get("segments") or []
        ovls = [[float(s["out_start"]), float(s["out_end"]), PureWindowsPath(str(s["src"])).name,
                 float(s.get("src_start") or 0.0)] for s in segs if s.get("kind") == "OVL"]
        take = str(d.get("take_path") or next((s["src"] for s in segs if s.get("kind") == "BASE"), ""))
    return {"plan_id": pid, "take_path": PureWindowsPath(take).name, "duration": float(d.get("duration") or 0.0),
            "ovls": ovls}


def _cung_ban(a: dict, b: dict) -> bool:
    if a["take_path"] != b["take_path"] or len(a["ovls"]) != len(b["ovls"]):
        return False
    return all(x[2] == y[2] and all(abs(x[i] - y[i]) < 1e-3 for i in (0, 1, 3)) for x, y in zip(a["ovls"], b["ovls"]))


def _ds_ledger(d: Path) -> list[dict]:
    f = d / "ledger.json"
    if not f.is_file():
        return []
    try:
        data = _doc_json(f)
    except (OSError, ValueError) as ex:
        raise Thoat(2, f"{_rel(d.parent, f)} hỏng — không soát trùng được ({ex})") from ex
    return [m for m in (data.get("plans") or []) if isinstance(m, dict)] if isinstance(data, dict) else []


def kiem_trung(e: SimpleNamespace, p: Path, b: sv.BanGhi, plan_moi: dict) -> None:
    """§5.4: so bản mới với các bản khác (cùng nguồn + ledger; luồng A thêm *_plan.json của 2 thư mục Adam)."""
    cu = _ky_hieu_ten(b.plan)
    khac: list[dict] = []
    if b.luong == "C":
        data = _doc_json(b.nguon)
        khac += [pl for k, pl in enumerate(data.get("plans") or [])
                 if k != b.chi_so and isinstance(pl, dict) and pl.get("status") != "LOI"]
        khac += _ds_ledger(b.nguon.parent)
    else:
        for out in sv.OUT_A:
            d = p / out
            if not d.is_dir():
                continue
            khac += _ds_ledger(d)
            for f in sorted(d.glob("*_plan.json")):
                try:
                    ds = _doc_json(f)
                except (OSError, ValueError) as ex:
                    raise Thoat(2, f"{out}/{f.name} hỏng — không soát trùng được ({ex})") from ex
                for k, pl in enumerate(ds if isinstance(ds, list) else []):
                    if isinstance(pl, dict) and not (f == b.nguon and k == b.chi_so):
                        khac.append(pl)
    ds_kh = []
    for m in khac:
        try:
            kh = _ky_hieu_ten(m)
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if not _cung_ban(kh, cu):                   # bỏ bản ghi của chính video này
            ds_kh.append(kh)
    moi = _ky_hieu_ten(plan_moi)
    moi_plan = {"plan_id": moi["plan_id"], "take_path": moi["take_path"], "duration": moi["duration"],
                "segments": [{"kind": "OVL", "out_start": o[0], "out_end": o[1], "src": o[2], "src_start": o[3]}
                             for o in moi["ovls"]]}
    vp = e.anti_trung.mach_trung_voi_lich_su(moi_plan, ds_kh, nguong=NGUONG_TRUNG)
    if vp is not None:
        raise Thoat(2, f"Đổi clip làm video trùng {vp.mach:.1f}s với bản {vp.plan_b}")


# ---------------- cấu hình dựng ----------------

def _phu(cfg, **ghi_de):
    """= pipeline_runner._phu_cau_hinh: bản sao dataclass với khoá khác None được ghi đè."""
    co = {f.name for f in dataclasses.fields(cfg)}
    thay = {k: v for k, v in ghi_de.items() if v is not None and k in co}
    return dataclasses.replace(cfg, **thay) if thay else cfg


def _nap_adam():
    if not SCRIPT_ADAM.is_file():
        raise Thoat(2, "Không đọc được cấu hình phụ đề Adam (thiếu script cầu nối)")
    try:
        spec = importlib.util.spec_from_file_location("_cau_noi_adam_sua", SCRIPT_ADAM)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _ = mod.sub_cfg_du_an, mod.BGM_VOLUME
        return mod
    except (Exception, SystemExit) as ex:
        log.exception("không nạp được %s", SCRIPT_ADAM)
        raise Thoat(2, f"Không đọc được cấu hình phụ đề Adam ({type(ex).__name__}: {ex})") from ex


def cau_hinh_dung(e: SimpleNamespace, p: Path, b: sv.BanGhi, viec: str) -> SimpleNamespace:
    """Tham số hậu kỳ + render cho đúng luồng (§6.3 bước 4–5). Không ghi đĩa."""
    tm = e.wm.tim_thu_muc_cau_hinh(p) or p
    wm, dcl = e.wm.load_wm_from_project(tm)          # lọc enabled như pipeline_runner.py:1357-1362
    wm = wm if wm.enabled and wm.text_lines else None
    dcl = dcl if dcl.enabled and dcl.text else None
    if b.luong == "C":
        snap = SimpleNamespace(**b.cau_hinh)
        w = int(b.tuy_chon.get("width") or 1080)
        h = int(b.tuy_chon.get("height") or 1920)
        tham_so = set(inspect.signature(e.render.render_single_plan).parameters)
        bo = {"plan", "output_folder", "config_snapshot", "progress_callback", "stop_flag"}
        render_kw = {k: v for k, v in b.tuy_chon.items() if k in tham_so and k not in bo}
        bo_qua = sorted(set(b.tuy_chon) - set(render_kw) - {"workers"})
        if bo_qua:
            log.warning("bỏ tuỳ chọn render engine không nhận: %s", bo_qua)
        try:
            sub_cfg = e.sr.sub_cfg_tu_config(snap)
        except Exception as ex:
            raise Thoat(2, f"Không dựng được cấu hình phụ đề từ render_batch.json ({ex})") from ex
        return SimpleNamespace(tm=tm, wm=wm, dcl=dcl, sub_cfg=sub_cfg, w=w, h=h,
                               burn=bool(b.cau_hinh.get("burn_subtitle")) or bool(b.plan.get("ass_path")),
                               cart_mode=str(b.cau_hinh.get("cart_arrow_mode") or "keyword"),
                               snap=snap, render_kw=render_kw, thu_muc_ra=b.file_ra.parent)
    adam = _nap_adam()
    try:
        cfg = e.cfg.load_config()
        cfg = _phu(cfg, **e.wm.co_tu_project(tm))
        cfg = _phu(cfg, burn_subtitle=True, cart_arrow_on=True, sticker=False, punch=False)
        sub_cfg, _phu_de = adam.sub_cfg_du_an(p)
        w, h, fps = KHUNG_A
        snap = e.img.merge_config(cfg, {"prefix": f"_sua_{viec}", "dissolve": DISSOLVE_A,
                                        "speed_on": False, "frame_jitter_on": False})
        if sub_cfg is None:
            sub_cfg = e.sr.sub_cfg_tu_config(cfg)
    except Thoat:
        raise
    except (Exception, SystemExit) as ex:
        log.exception("cấu hình Adam")
        raise Thoat(2, f"Không đọc được cấu hình phụ đề Adam ({type(ex).__name__}: {ex})") from ex
    render_kw = dict(width=w, height=h, fps=fps, dissolve=DISSOLVE_A, use_nvenc=NVENC_A, pad_or_crop="crop",
                     bgm_volume=float(adam.BGM_VOLUME))
    return SimpleNamespace(tm=tm, wm=wm, dcl=dcl, sub_cfg=sub_cfg, w=w, h=h, burn=True,
                           cart_mode=str(getattr(cfg, "cart_arrow_mode", "keyword") or "keyword"),
                           snap=snap, render_kw=render_kw, thu_muc_ra=None)


def kiem_words(e: SimpleNamespace, take: Path) -> None:
    """Chặn TRƯỚC khi gọi build_subtitle_json: cache .words.json phải dùng được, không thì engine chạy Whisper."""
    wj = take.with_suffix(".words.json")
    try:
        data = _doc_json(wj)
    except FileNotFoundError as ex:
        raise Thoat(2, "Take chưa có bản Whisper — không sửa trên web") from ex
    except (OSError, ValueError) as ex:
        raise Thoat(2, f"Bản Whisper của take hỏng ({ex})") from ex
    ly_do = e.sjb._words_cache_reason(data, take, wj, MODEL_WHISPER, e.sjb.NGON_NGU_MAC_DINH)
    if ly_do:
        raise Thoat(2, f"Bản Whisper của take không dùng lại được ({ly_do}) — dựng lại sẽ chạy Whisper, không sửa trên web")


def _chuan_chu(s: str) -> str:
    s = unicodedata.normalize("NFC", s).lower()
    s = "".join(" " if unicodedata.category(c).startswith("P") else c for c in s)
    return " ".join(s.split())


# ---------------- phiên ap-dung ----------------

def doc_ban_sua(path: Path) -> tuple[str, dict]:
    try:
        raw = Path(path).read_bytes()
    except OSError as ex:
        raise Thoat(2, f"Không đọc được bản sửa ({ex})") from ex
    if len(raw) > BAN_SUA_TOI_DA:
        raise Thoat(2, "Bản sửa quá lớn")
    try:
        ban = json.loads(raw.decode("utf-8-sig"))
    except ValueError as ex:
        raise Thoat(2, "Bản sửa không phải JSON hợp lệ") from ex
    if not isinstance(ban, dict):
        raise Thoat(2, "Bản sửa phải là object")
    stem = Path(path).stem
    return (stem if RE_BAN_SUA.fullmatch(stem) else sv.ma_ban_sua(ban)), ban


def tim_nhat_ky(p: Path, thu_muc: str, ten: str, viec: str) -> Path | None:
    """Nhật ký nằm cạnh file_ra: thư mục video, hoặc (luồng A) thư mục bản gốc của Adam."""
    ung = [p / thu_muc / "_sua" / f"{viec}.json"]
    if sv.RE_A.fullmatch(ten):
        ung += [p / out / "_sua" / f"{viec}.json" for out in sv.OUT_A]
    return next((f for f in ung if f.is_file()), None)


def _doc_nk(f: Path) -> dict:
    try:
        nk = sv.doc_nhat_ky(f)
    except ValueError as ex:
        raise Thoat(5, f"Nhật ký sửa video hỏng ({f.name}) — kiểm tay") from ex
    if nk is None:
        raise Thoat(5, f"Mất nhật ký {f.name}")
    return nk


class PhienSua:
    def __init__(self, a: argparse.Namespace, e: SimpleNamespace, canh_bao: list[str]):
        self.a, self.e, self.cb = a, e, canh_bao
        self.p = Path(a.project)
        self.viec = a.viec
        self.nk: dict = {}
        self.nk_f: Path | None = None

    # ---- nhật ký ----
    def ghi(self, buoc: str | None = None) -> None:
        if buoc:
            self.nk["buoc"] = buoc
        self.nk["canh_bao"] = list(dict.fromkeys(self.cb))
        _ghi_json(self.nk_f, self.nk)

    # ---- chuẩn bị (không ghi đĩa) ----
    def chuan_bi(self) -> SimpleNamespace:
        p, a, e = self.p, self.a, self.e
        ma = sv.ma_video(sv.ma_du_an(p), a.thu_muc, a.video)
        v = sv.tim_video(p, p.parent, ma)
        if not v.sua_duoc:
            raise Thoat(2, v.ly_do or "Video này không sửa được")
        b = sv.tra_ban_ghi(p, v)
        ma_ban, ban = doc_ban_sua(Path(a.ban_sua))
        ma_trong = ban.pop("ma_video", "")
        if ma_trong and ma_trong != v.ma_video:
            raise Thoat(2, "Bản sửa không thuộc video này")
        if ban.get("sua_luc") != v.sua_luc:
            raise Thoat(2, "Video đã đổi từ lúc bạn sửa — mở lại và sửa")
        ban = sv.kiem_ban_sua(ban, sv.lap_chi_tiet(p, v, b))
        pd = None
        if ban["phu_de"]:
            pd = sv.doc_phu_de(b)
            if pd["take_idx"] is None:
                raise Thoat(2, "Phụ đề của take không có take_idx — không sửa trên web")
            kiem_words(e, b.take)
        plan_moi, doi = ap_ban_sua(b, p, ban, self.viec)
        if doi:
            kiem_trung(e, p, b, plan_moi)
        ch = cau_hinh_dung(e, p, b, self.viec)
        _plan_obj(plan_moi, e)                       # dựng thử: định dạng sai thì mã 2 ngay, chưa ghi gì
        self.cb.extend(b.canh_bao)
        if ban["phu_de"]:
            self.cb.append("Từ nay take này lấy chữ từ .sua.srt (ưu tiên hơn .script.txt)")
        return SimpleNamespace(v=v, b=b, ma_ban=ma_ban, ban=ban, pd=pd, plan_moi=plan_moi, doi=doi, ch=ch)

    # ---- chạy ----
    def chay(self) -> dict:
        a = self.a
        nk_f = tim_nhat_ky(self.p, a.thu_muc, a.video, self.viec)
        if nk_f is not None:
            self.nk_f, self.nk = nk_f, _doc_nk(nk_f)
            if self.nk.get("loai") != "ap_dung" or self.nk.get("viec") != self.viec:
                raise Thoat(2, "Nhật ký của mã việc này không phải việc sửa")
            buoc = self.nk.get("buoc")
            self.cb.extend(self.nk.get("canh_bao") or [])
            if buoc == "xong":
                return dict(self.nk.get("ket_qua") or {"trang_thai": "xong"})
            if buoc in ("thay", "nguon", "lien_ket"):
                return self.lam_tiep()
            if buoc == "hoan_nguyen":
                # R-20 P1-1: đã hoàn nguyên xong — KHÔNG làm lại (có thể việc khác đã sửa video từ đó). Lần trước có
                # mục bỏ qua → trạng thái không chắc, dừng cho người kiểm; không thì làm lại từ đầu (chuan_bi chặn
                # bằng sua_luc nếu video đã đổi).
                bo = self.nk.get("hoan_nguyen_bo_qua") or []
                if bo:
                    raise Thoat(5, f"Lần hoàn nguyên trước đã bỏ qua {', '.join(bo)} (việc khác đã đổi) — kiểm tay,"
                                   " tạo việc sửa mới nếu cần")
            else:                                  # tra | phu_de | hau_ky | render → hoàn nguyên rồi làm lại từ đầu
                bo = self.hoan_nguyen()
                if bo:
                    raise Thoat(5, f"Hoàn nguyên bỏ qua {', '.join(bo)} vì việc khác đã đổi — không làm lại, kiểm tay")
            self.cb.clear()
        cb = self.chuan_bi()
        b = cb.b
        kiem_partial(b.file_ra.parent)
        thu_khoa_file(b.file_ra)
        if b.lien_ket is not None and b.lien_ket.exists():
            thu_khoa_file(b.lien_ket)
        return self.lam_moi(cb)

    def lam_moi(self, cb: SimpleNamespace) -> dict:
        p, e, b = self.p, self.e, cb.b
        stem = b.file_ra.stem
        sua_dir = b.file_ra.parent / "_sua" / self.viec
        self.nk_f = sv.duong_nhat_ky(b, self.viec)
        lien_kieu = None
        if b.lien_ket is not None:
            try:
                lien_kieu = "link" if os.path.samefile(b.lien_ket, b.file_ra) else "chep"
            except OSError:
                lien_kieu = "link"
        self.nk = {"viec": self.viec, "loai": "ap_dung", "ban_sua": cb.ma_ban, "luong": b.luong,
                   "video": _rel(p, b.file_ra), "thu_muc": self.a.thu_muc, "ten": self.a.video,
                   "lien_ket": _rel(p, b.lien_ket) if b.lien_ket is not None else None, "lien_ket_kieu": lien_kieu,
                   "plan_id": int(_plan_obj(cb.plan_moi, e).plan_id), "chi_so": b.chi_so,
                   "me": b.me, "ma": b.ma, "doi_seg": cb.doi, "sua_dir": _rel(p, sua_dir),
                   "nguon": {"file": _rel(p, b.nguon), "sao_luu": _rel(p, sua_dir / b.nguon.name),
                             "mtime_ns": b.nguon.stat().st_mtime_ns},
                   "cu": None, "moi": None, "phu_de": None}
        self.ghi("tra")
        try:
            if cb.ban["phu_de"]:
                self.buoc_phu_de(b, cb)
            plan = self.buoc_hau_ky(b, cb, sua_dir)
            self.buoc_render(b, cb, plan, sua_dir, stem)
        except BaseException as ex:
            ma, ly_do = (ex.ma, ex.ly_do) if isinstance(ex, Thoat) else (4, f"{type(ex).__name__}: {ex}")
            if not isinstance(ex, Thoat):
                log.exception("dựng hỏng")
            try:
                bo = self.hoan_nguyen()
            except BaseException as ex2:
                log.exception("HOÀN NGUYÊN HỎNG")
                raise Thoat(5, f"Dựng hỏng ({ly_do}) và hoàn nguyên cũng hỏng ({ex2}) — xem nhật ký") from ex2
            if isinstance(ex, KeyboardInterrupt):
                raise
            if bo:
                raise Thoat(5, f"Dựng hỏng ({ly_do}); hoàn nguyên bỏ qua {', '.join(bo)} — kiểm tay") from ex
            raise Thoat(4 if ma not in (2, 3) else ma, ly_do) from ex
        return self.lam_tiep()

    def buoc_phu_de(self, b: sv.BanGhi, cb: SimpleNamespace) -> None:
        p, e = self.p, self.e
        take = b.take
        sub, srt, wj = b.phu_de, take.with_suffix(".sua.srt"), take.with_suffix(".words.json")
        bk = take.parent / "_sua_cu" / self.viec
        sua = {x["i"]: x["text"] for x in cb.ban["phu_de"]}
        noi_dung_srt = sv.lap_srt(cb.pd["cau"], sua)
        # Dấu vết để hoàn nguyên chỉ đụng thứ CHÍNH việc này đã ghi (R-20 P1-1): *_truoc = bản gốc, *_sau = bản mình
        # ghi (ghi NGAY sau khi ghi); srt_sha_ghi ghi TRƯỚC khi ghi .sua.srt để phủ cả lúc chết giữa ghi và ghi nhật ký.
        self.nk["phu_de"] = {"take": _rel(p, take), "sao_luu": _rel(p, bk), "co_srt_cu": srt.exists(),
                             "sha_truoc": cb.pd["sha"], "sha_sau": None,
                             "sub_truoc": _dau(sub), "sub_sau": None, "srt_truoc": _dau(srt), "srt_sau": None,
                             "srt_sha_ghi": hashlib.sha256(noi_dung_srt.encode("utf-8")).hexdigest()}
        self.ghi("phu_de")
        bk.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sub, bk / sub.name)
        if srt.exists():
            shutil.copy2(srt, bk / srt.name)
        _ghi_nguyen_tu(srt, noi_dung_srt)
        self.nk["phu_de"]["srt_sau"] = _dau(srt)
        self.ghi()
        words_ns = wj.stat().st_mtime_ns
        try:
            kq = e.sjb.build_subtitle_json(take, take_idx=int(cb.pd["take_idx"]), force=False)
        finally:                                   # ghi cả khi engine ném lỗi / trước mọi phép kiểm bên dưới
            self.nk["phu_de"]["sub_sau"] = _dau(sub)
            self.nk["phu_de"]["sha_sau"] = (self.nk["phu_de"]["sub_sau"] or {}).get("sha")
            self.ghi()
        if kq is None:
            raise Thoat(4, "Dựng lại phụ đề hỏng")
        if wj.stat().st_mtime_ns != words_ns:
            raise Thoat(4, "Dựng lại phụ đề đã chạy Whisper (ghi đè .words.json) — đã hoàn nguyên")
        moi = _doc_json(sub)
        if moi.get("take_idx") != cb.pd["take_idx"]:
            raise Thoat(4, "Dựng lại phụ đề làm đổi take_idx — đã hoàn nguyên")
        toan = _chuan_chu(" ".join(str(s.get("text", "")) for s in moi.get("sentences") or []))
        thieu = [i for i, t in sua.items() if _chuan_chu(t) not in toan]
        if thieu:
            raise Thoat(4, f"Phụ đề dựng lại không có chữ mới ở câu {thieu[:5]} — đã hoàn nguyên")

    def buoc_hau_ky(self, b: sv.BanGhi, cb: SimpleNamespace, sua_dir: Path):
        e, ch = self.e, cb.ch
        self.ghi("hau_ky")
        plan = _plan_obj(cb.plan_moi, e)
        giu = copy.deepcopy((plan.cart_arrow_intervals, plan.stickers, plan.punch_times))
        plan.ass_path = plan.wm_file = plan.disclaimer_file = ""     # hậu kỳ cũ (đường dẫn cũ) luôn dựng lại
        e.hau_ky.dung_hau_ky_cho_plan(
            plan, subtitle_json_path=str(b.phu_de), output_folder=sua_dir, burn_subtitle=ch.burn,
            sub_cfg=ch.sub_cfg, wm_config=ch.wm, disclaimer_config=ch.dcl, width=ch.w, height=ch.h,
            sticker=False, punch=False, cart_arrow=True, cart_arrow_mode=ch.cart_mode, project_dir=ch.tm)
        plan.cart_arrow_intervals, plan.stickers, plan.punch_times = giu
        if ch.burn and not plan.ass_path:
            raise Thoat(4, "Không dựng được phụ đề (.ass) cho bản này")
        return plan

    def buoc_render(self, b: sv.BanGhi, cb: SimpleNamespace, plan, sua_dir: Path, stem: str) -> None:
        p, e, ch = self.p, self.e, cb.ch
        f = b.file_ra
        sl = f.parent / "_sua_cu" / f"{stem}.{self.viec}.mp4"
        done = f.parent / f"{stem}.done.json"
        done_bk = sua_dir / done.name
        self.nk["cu"] = dict(_sig(f), sao_luu=_rel(p, sl))
        self.nk["done_sao_luu"] = _rel(p, done_bk) if b.luong == "C" else None
        # R-20 P1-1: done_truoc = .done.json gốc; done_sau / moi = thứ engine ghi cho CHÍNH việc này (ghi ngay khi
        # render trả về, kể cả khi hỏng) — hoàn nguyên chỉ đè khi hiện tại vẫn đúng là chúng.
        self.nk["done_truoc"] = _dau(done) if b.luong == "C" else None
        self.ghi("render")
        sl.parent.mkdir(parents=True, exist_ok=True)
        if sl.exists() and not os.path.samefile(sl, f):
            sl.unlink()
        if not sl.exists():
            os.link(f, sl)                           # chép cứng: tức thì, giữ inode + mtime cũ
        if b.luong == "C":
            sua_dir.mkdir(parents=True, exist_ok=True)
            if done.exists():
                shutil.copy2(done, done_bk)
                done.unlink()
            try:
                ok, msg = e.render.render_single_plan(plan, output_folder=f.parent, config_snapshot=ch.snap,
                                                      **ch.render_kw)
            finally:
                self.nk["moi"] = _sig(f) if f.exists() else None
                self.nk["done_sau"] = {"dau": _dau(done)}
                self.ghi()
            if not ok:
                raise Thoat(4, f"Dựng hỏng: {str(msg)[-400:]}")
            if _khop(f, self.nk["cu"]):
                raise Thoat(4, "Engine không dựng lại file (vẫn là bản cũ)")
        else:
            ra = sua_dir / "ra"
            ok, msg = e.render.render_single_plan(plan, output_folder=ra, config_snapshot=ch.snap, **ch.render_kw)
            out = ra / f"_sua_{self.viec}_{plan.plan_id:03d}.mp4"
            if not ok or not out.is_file():
                raise Thoat(4, f"Dựng hỏng: {str(msg)[-400:]}")
            self.nk["moi"] = _sig(out)               # os.replace giữ size + mtime → ghi TRƯỚC khi thay
            self.ghi()
            _thay_the(out, f)
            out.with_suffix(".done.json").unlink(missing_ok=True)
        _ghi_json(sua_dir / "plan_moi.json", dataclasses.asdict(plan))
        self.nk["moi"] = _sig(f)
        self.ghi("thay")

    # ---- sau khi thay (mã 5 nếu hỏng) ----
    def lam_tiep(self) -> dict:
        try:
            return self._lam_tiep()
        except Thoat:
            raise
        except BaseException as ex:
            log.exception("hỏng sau khi thay file")
            if isinstance(ex, KeyboardInterrupt):
                raise
            raise Thoat(5, f"Hỏng giữa lúc thay file ({type(ex).__name__}: {ex}) — bấm Chạy lại để làm nốt") from ex

    def _lam_tiep(self) -> dict:
        p, nk = self.p, self.nk
        f = _abs(p, nk["video"])
        if not _khop(f, nk.get("moi")):
            raise Thoat(5, "Video đã đổi giữa lúc sửa (không khớp bản vừa dựng) — kiểm tay")
        if nk["buoc"] in ("thay", "nguon"):
            self.buoc_nguon()
        self.buoc_lien_ket()
        self.trich_khung()
        self.don_sao_luu(f)
        sua_dir = _abs(p, nk["sua_dir"])
        if nk["luong"] == "A":
            shutil.rmtree(sua_dir / "ra", ignore_errors=True)
        kq = {"trang_thai": "xong", "sao_luu": (nk.get("cu") or {}).get("sao_luu"),
              "canh_bao": list(dict.fromkeys(self.cb))}
        nk["ket_qua"] = kq
        self.ghi("xong")
        return dict(kq)

    def buoc_nguon(self) -> None:
        p, nk, e = self.p, self.nk, self.e
        self.ghi("nguon")
        src, bk = _abs(p, nk["nguon"]["file"]), _abs(p, nk["nguon"]["sao_luu"])
        sua_dir = _abs(p, nk["sua_dir"])
        plan_moi = _doc_json(sua_dir / "plan_moi.json")
        k, pid = nk["chi_so"], nk["plan_id"]
        if nk["luong"] == "C":
            # R-20 P2-1: `cli.py run` không lấy khoá — mẻ mới ghi lại render_batch.json (plan_id trùng) thì so plan_id
            # vẫn khớp. So thêm mtime_ns với lúc tra (hoặc lúc chính việc này đã ghi); lệch → không ghi, cảnh báo.
            mt = src.stat().st_mtime_ns
            data = _doc_json(src)
            plans = data.get("plans") if isinstance(data, dict) else None
            dung_muc = isinstance(plans, list) and k < len(plans) and isinstance(plans[k], dict) \
                and plans[k].get("plan_id") == pid
            da_ghi = nk["nguon"].get("mtime_ns_sau")
            if mt == da_ghi or (da_ghi is None and dung_muc and plans[k] == plan_moi):
                ok = True                            # đã ghi (chạy lại sau khi ghi; chết trước khi kịp ghi nhật ký)
            elif mt == nk["nguon"]["mtime_ns"] and dung_muc:
                if not bk.exists():                  # chạy lại: bản sao lưu đầu tiên là bản TRƯỚC khi sửa
                    bk.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, bk)
                plans[k] = plan_moi
                e.rc.write_json(src, data)
                ok = True
            else:
                ok = False
                self.cb.append("render_batch.json đã đổi (mẻ khác?) — không cập nhật bản ghi")
            if ok and nk["nguon"].get("mtime_ns_sau") != src.stat().st_mtime_ns:
                nk["nguon"]["mtime_ns_sau"] = src.stat().st_mtime_ns
                self.ghi()
            pj = src.parent / "plan.json"
            if not ok:
                return                               # plan.json đi cùng mẻ: mẻ mới thì cũng không cấy vào
            if pj.is_file():
                if not (sua_dir / "plan.json").exists():
                    shutil.copy2(pj, sua_dir / "plan.json")
                ds = _doc_json(pj)
                muc = next((m for m in ds if isinstance(m, dict) and m.get("plan_id") == f"plan_{pid:03d}"), None) \
                    if isinstance(ds, list) else None
                if muc is not None:
                    muc["segments"] = plan_moi["segments"]
                    _ghi_json(pj, ds, indent=2)
        else:
            if not bk.exists():                      # chạy lại: bản sao lưu đầu tiên là bản TRƯỚC khi sửa
                bk.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, bk)
            data = _doc_json(src)
            goc = f"{nk['me']}_{nk['ma']}"
            if isinstance(data, list) and k < len(data) and isinstance(data[k], dict) and any(
                    s.get("kind") == "BASE" and PureWindowsPath(str(s.get("src"))).stem == goc
                    for s in data[k].get("segments") or []):
                data[k] = _plan_obj(plan_moi, e).to_dict()
                _ghi_json(src, data, indent=1)
                # Giữ mtime cũ: luật tra luồng A (§3.3 bước 3) đòi video ≥ mtime <B>_plan.json — đổi mtime là mọi
                # video khác của mẻ thành "không sửa được".
                os.utime(src, ns=(time.time_ns(), int(nk["nguon"]["mtime_ns"])))
            else:
                self.cb.append(f"{src.name} đã đổi — không cập nhật bản ghi")

    def buoc_lien_ket(self) -> None:
        p, nk = self.p, self.nk
        self.ghi("lien_ket")
        if not nk.get("lien_ket"):
            return
        lk, f = _abs(p, nk["lien_ket"]), _abs(p, nk["video"])
        sl = _abs(p, nk["cu"]["sao_luu"])
        noi_lien_ket(lk, f, sl, nk.get("lien_ket_kieu"), self.viec, self.cb)

    def trich_khung(self) -> None:
        """§6.7: 1 khung giữa mỗi đoạn đã đổi → _sua/<viec>/khung_<seg>.jpg (để người xem bằng mắt)."""
        p, nk = self.p, self.nk
        if not nk.get("doi_seg"):
            return
        f, sua_dir = _abs(p, nk["video"]), _abs(p, nk["sua_dir"])
        try:
            segs = _doc_json(sua_dir / "plan_moi.json")["segments"]
        except (OSError, ValueError, KeyError) as ex:
            self.cb.append(f"Không trích được khung kiểm ({ex})")
            return
        for i in nk["doi_seg"]:
            ra = sua_dir / f"khung_{i}.jpg"
            if ra.exists():
                continue
            giua = (float(segs[i]["out_start"]) + float(segs[i]["out_end"])) / 2
            cmd = [shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-ss", f"{giua:.3f}", "-i", str(f),
                   "-frames:v", "1", "-q:v", "3", str(ra)]
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=60,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (OSError, subprocess.TimeoutExpired) as ex:
                self.cb.append(f"Không trích được khung đoạn {i} ({ex})")
                continue
            if r.returncode != 0 or not ra.is_file():
                loi = r.stderr.decode("utf-8", "replace")[-300:]
                log.warning("ffmpeg trích khung đoạn %s lỗi %s: %s", i, r.returncode, loi)
                self.cb.append(f"Không trích được khung đoạn {i}")

    def don_sao_luu(self, f: Path) -> None:
        """Giữ tối đa GIU_SAO_LUU bản trong _sua_cu/ cho video này (mã việc tăng theo thời gian → sắp theo tên)."""
        d = f.parent / "_sua_cu"
        if not d.is_dir():
            return
        mau = re.compile(re.escape(f.stem) + r"\.j\d{14}[a-z0-9]{4}\.mp4$")
        ds = sorted(x for x in d.iterdir() if x.is_file() and mau.fullmatch(x.name))
        for x in ds[:max(0, len(ds) - GIU_SAO_LUU)]:
            try:
                x.unlink()
            except OSError as ex:
                log.error("không xoá được bản sao lưu cũ %s: %s", x, ex)
                self.cb.append(f"Không xoá được bản sao lưu cũ {x.name}")

    # ---- hoàn nguyên (trước khi thay xong) ----
    def hoan_nguyen(self) -> list[str]:
        """Trả về như trước khi sửa — CHỈ những gì hiện tại vẫn đúng là thứ việc này đã ghi (R-20 P1-1). Mục nào đã
        bị việc khác / người khác đổi thì BỎ QUA (không đè), ghi cảnh báo + `hoan_nguyen_bo_qua` vào nhật ký.
        Gọi lại nhiều lần an toàn: mục đã về bản gốc thì không làm gì. Trả danh sách mục bỏ qua."""
        p, nk = self.p, self.nk
        if not nk or self.nk_f is None:
            return []
        bo: list[str] = []
        pd = nk.get("phu_de")
        if pd and pd.get("sao_luu"):
            take = _abs(p, pd["take"])
            bk = _abs(p, pd["sao_luu"])
            sub, srt = take.with_name(take.stem + ".subtitles.json"), take.with_suffix(".sua.srt")
            # nhật ký cũ (trước R-20) chỉ có sha_truoc / sha_sau: dùng làm dấu dự phòng
            self._hn_file(sub, pd.get("sub_truoc"), pd.get("sub_sau"), pd.get("sha_sau"), bk / sub.name, "phụ đề", bo,
                          sha_truoc=None if "sub_truoc" in pd else pd.get("sha_truoc"))
            self._hn_file(srt, pd.get("srt_truoc"), pd.get("srt_sau"), pd.get("srt_sha_ghi"),
                          bk / srt.name if pd.get("co_srt_cu") else None, ".sua.srt", bo)
        cu = nk.get("cu")
        f = _abs(p, nk["video"])
        if cu and cu.get("sao_luu"):
            sl = _abs(p, cu["sao_luu"])
            if sl.exists() and f.exists() and os.path.samefile(f, sl):
                sl.unlink()                          # chưa thay: chỉ bỏ link sao lưu
            elif _khop(f, cu):
                pass                                 # đã là bản gốc (hoàn nguyên lần trước đã trả về)
            elif sl.exists() and nk.get("moi") and _khop(f, nk["moi"]):
                _thay_the(sl, f)                     # đúng bản việc này dựng: trả inode cũ (giữ mtime) về chỗ
            else:
                bo.append("video")
                self.cb.append(f"Hoàn nguyên bỏ qua video: {f.name} không còn là bản việc này dựng (việc khác đã đổi"
                               f" hoặc không đủ dấu vết) — giữ nguyên; bản cũ"
                               f"{' ở ' + cu['sao_luu'] if sl.exists() else ' không còn'} — kiểm tay")
        if nk.get("done_sao_luu"):
            dbk = _abs(p, nk["done_sao_luu"])
            done = f.parent / dbk.name
            if "done_truoc" not in nk:               # nhật ký cũ (trước R-20): không có dấu vết → không đè mù
                if not done.exists() and dbk.is_file():
                    _chep_qua_tam(dbk, done)
                elif done.exists():
                    bo.append(".done.json")
                    self.cb.append(f"Hoàn nguyên bỏ qua {done.name}: nhật ký cũ không có dấu vết — kiểm tay")
            else:
                ds = nk.get("done_sau")
                self._hn_file(done, nk.get("done_truoc"), ds.get("dau") if ds else None, None,
                              dbk if nk.get("done_truoc") else None, done.name, bo,
                              mat_la_cua_minh=ds is None or ds.get("dau") is None)
        nk["hoan_nguyen_bo_qua"] = bo
        self.ghi("hoan_nguyen")
        return bo

    def _hn_file(self, f: Path, truoc: dict | None, sau: dict | None, sha_ghi: str | None, bk: Path | None,
                 ten: str, bo: list[str], mat_la_cua_minh: bool = False, sha_truoc: str | None = None) -> None:
        """Hoàn nguyên 1 file nhỏ. truoc = dấu bản gốc (None = gốc không có file); sau = dấu bản việc này ghi
        (None = chưa kịp ghi nhật ký); sha_ghi = sha nội dung định ghi (phủ lúc chết giữa ghi và ghi nhật ký);
        bk = bản sao lưu để chép về (None = gốc không có → xoá); mat_la_cua_minh = file mất là do chính việc này xoá."""
        nay = _dau(f)
        if nay == truoc or (sha_truoc and nay is not None and nay["sha"] == sha_truoc):
            return                                   # đã là bản gốc
        if nay is None and not mat_la_cua_minh:
            khop = False
        elif nay is None:
            khop = True                              # chính việc này đã xoá (vd .done.json trước khi render)
        elif sau is not None:
            khop = nay == sau
        else:
            khop = sha_ghi is not None and nay["sha"] == sha_ghi
        if not khop:
            bo.append(ten)
            self.cb.append(f"Hoàn nguyên bỏ qua {ten} ({f.name}): hiện tại không còn là bản việc này ghi (việc khác đã"
                           " sửa tiếp?) — giữ nguyên, kiểm tay")
            return
        if bk is None:
            f.unlink(missing_ok=True)
        elif bk.is_file():
            _chep_qua_tam(bk, f)
        else:
            bo.append(ten)
            self.cb.append(f"Hoàn nguyên bỏ qua {ten} ({f.name}): mất bản sao lưu {bk.name} — kiểm tay")


def noi_lien_ket(lk: Path, f: Path, sl: Path | None, kieu: str | None, viec: str, cb: list[str]) -> None:
    """Bước 8 §6.3: output_poster/<ten> trỏ inode mới. Đã đăng (mất file) → chỉ cảnh báo."""
    if not lk.exists():
        cb.append("Video đã được đăng trước khi sửa xong (không còn trong output_poster)")
        return
    if os.path.samefile(lk, f):
        return
    tam = lk.with_name(f".{lk.name}.{viec}.lnk")
    tam.unlink(missing_ok=True)
    if kieu == "chep":
        # FX-21: chỉ chép đè khi bản trong output_poster vẫn đúng nội dung bản bị thay (sl); đã giống f → xong rồi
        if filecmp.cmp(lk, f, shallow=False):
            return
        if sl is None or not sl.exists() or not filecmp.cmp(lk, sl, shallow=False):
            cb.append(f"Bản chép trong {lk.parent.name} không còn là bản cũ — không nối lại, kiểm tay")
            return
        try:
            shutil.copy2(f, tam)
            _thay_the(tam, lk)
        finally:
            tam.unlink(missing_ok=True)
        return
    if sl is None or not sl.exists() or not os.path.samefile(lk, sl):
        cb.append(f"Bản trong {lk.parent.name} không còn trỏ bản cũ — không nối lại")
        return
    try:
        os.link(f, tam)
        _thay_the(tam, lk)
    finally:
        tam.unlink(missing_ok=True)


# ---------------- hoan-tac (§6.4) ----------------
# FX-21: hoàn tác chỉ áp lên ĐÚNG bản lần sửa đó tạo ra. Mỗi mục được xếp loại TRƯỚC khi đè (và xếp lại ngay trước
# lúc đè): GOC = đã là bản trước khi sửa (không làm gì) · MINH = đúng thứ lần sửa đó ghi (được đè) · KHAC = đã có bản
# mới hơn / việc khác đổi (không đè) · MAT = đúng của lần sửa nhưng mất bản sao lưu (không đè).
# Mục gắn với video (video, .done.json, mục nguồn, plan.json) KHAC/MAT → từ chối mã 2, chưa đổi gì.
# Phụ đề + .sua.srt là của TAKE (video khác cùng take có thể đã sửa tiếp) → bỏ qua như hoan_nguyen: cảnh báo +
# `hoan_tac_bo_qua` trong nhật ký, mã 5 "kiểm tay"; chạy lại không làm lại.
GOC, MINH, KHAC, MAT = "goc", "minh", "khac", "mat"


def _sha_neu_co(f: Path) -> str | None:
    try:
        return _sha(f)
    except FileNotFoundError:
        return None


def _chuan_json(x: object) -> object:
    """Dạng sau khi ghi JSON rồi đọc lại (tuple → list…) — để so với thứ đã ghi ra đĩa."""
    return json.loads(json.dumps(x, ensure_ascii=False, default=str))


def _done_tro_video(done: Path, moi: dict) -> bool:
    """Nhật ký cũ (không có done_sau): .done.json ghi `output` = [đường dẫn, size, mtime_ns] của video nó mô tả."""
    try:
        out = _doc_json(done).get("output")
    except (OSError, ValueError, AttributeError):
        return False
    return isinstance(out, list) and len(out) == 3 and out[1] == moi.get("size") and out[2] == moi.get("mtime_ns")


def _xet_done(p: Path, g: dict) -> tuple[str, Path, Path | None]:
    """.done.json (luồng C) → (loại, file, nguồn chép về | None = trước khi sửa không có file → xoá)."""
    dbk = _abs(p, g["done_sao_luu"])
    done = _abs(p, g["video"]).parent / dbk.name
    if "done_truoc" in g:
        co_goc = g["done_truoc"] is not None
        sha_goc = (g["done_truoc"] or {}).get("sha")
    else:                                        # nhật ký cũ: bản trước khi sửa = bản sao lưu (nếu có)
        co_goc = dbk.is_file()
        sha_goc = _sha_neu_co(dbk)
    nguon = dbk if co_goc else None
    sha_nay = _sha_neu_co(done)
    if (sha_nay is None and not co_goc) or (sha_nay is not None and co_goc and sha_nay == sha_goc):
        return GOC, done, nguon
    if isinstance(g.get("done_sau"), dict):
        sau = g["done_sau"].get("dau")
        minh = sha_nay is None if sau is None else sha_nay == sau.get("sha")
    else:
        minh = sha_nay is not None and _done_tro_video(done, g["moi"])
    if not minh:
        return KHAC, done, nguon
    if co_goc and (not dbk.is_file() or ("done_truoc" in g and _sha(dbk) != sha_goc)):
        return MAT, done, nguon
    return MINH, done, nguon


def _xet_nguon(p: Path, g: dict, e: SimpleNamespace) -> tuple[str, object, object]:
    """Mục chi_so trong render_batch.json (C) / <B>_plan.json (A) → (loại, data hiện tại, mục cũ để đặt lại)."""
    src, bk = _abs(p, g["nguon"]["file"]), _abs(p, g["nguon"]["sao_luu"])
    sua_dir = _abs(p, g["sua_dir"])
    k, pid = g["chi_so"], g["plan_id"]
    try:
        data = _doc_json(src)
    except (OSError, ValueError):
        return KHAC, None, None
    try:
        cu_data = _doc_json(bk)
    except (OSError, ValueError):
        cu_data = None
    if g["luong"] == "C":
        ds = data.get("plans") if isinstance(data, dict) else None
        ds_cu = cu_data.get("plans") if isinstance(cu_data, dict) else None
        if not (isinstance(ds, list) and k < len(ds) and isinstance(ds[k], dict) and ds[k].get("plan_id") == pid):
            return KHAC, data, None
    else:
        ds, ds_cu = data, cu_data
        if not (isinstance(ds, list) and k < len(ds)):
            return KHAC, data, None
    muc_cu = ds_cu[k] if isinstance(ds_cu, list) and k < len(ds_cu) else None
    if muc_cu is not None and ds[k] == muc_cu:
        return GOC, data, muc_cu
    try:
        plan_moi = _doc_json(sua_dir / "plan_moi.json")
        da_ghi = plan_moi if g["luong"] == "C" else _chuan_json(_plan_obj(plan_moi, e).to_dict())
    except (OSError, ValueError, KeyError, TypeError):
        return KHAC, data, muc_cu                # không còn plan lần sửa đó ghi → không chứng minh được là của mình
    if ds[k] != da_ghi:
        return KHAC, data, muc_cu
    return (MAT if muc_cu is None else MINH), data, muc_cu


def _xet_plan_json(p: Path, g: dict) -> tuple[str, object, dict | None]:
    """Mục plan_<pid> trong plan.json cạnh render_batch.json (luồng C) → (loại, ds hiện tại, segments cũ)."""
    src, sua_dir = _abs(p, g["nguon"]["file"]), _abs(p, g["sua_dir"])
    pj, pj_bk = src.parent / "plan.json", sua_dir / "plan.json"
    if g["luong"] != "C" or not pj_bk.is_file():
        return GOC, None, None                   # lần sửa đó không đụng plan.json
    ten = f"plan_{g['plan_id']:03d}"

    def tim(ds: object) -> dict | None:
        return next((m for m in ds if isinstance(m, dict) and m.get("plan_id") == ten), None) \
            if isinstance(ds, list) else None
    try:
        muc_cu = tim(_doc_json(pj_bk))
    except (OSError, ValueError):
        return MAT, None, None
    if muc_cu is None:
        return GOC, None, None                   # lúc sửa không có mục này → đã không ghi gì
    try:
        ds = _doc_json(pj)
        seg_moi = _doc_json(sua_dir / "plan_moi.json")["segments"]
    except (OSError, ValueError, KeyError, TypeError):
        return KHAC, None, None
    muc = tim(ds)
    if muc is None:
        return KHAC, ds, None
    if muc.get("segments") == muc_cu.get("segments"):
        return GOC, ds, muc_cu
    return (MINH if muc.get("segments") == seg_moi else KHAC), ds, muc_cu


def _xet_phu_de(p: Path, g: dict) -> tuple[str, dict]:
    """Phụ đề + .sua.srt của take, xét CHUNG (.sua.srt là nguồn chữ của .subtitles.json — không tách đôi)."""
    pd = g["phu_de"]
    take, bk = _abs(p, pd["take"]), _abs(p, pd["sao_luu"])
    sub, srt = take.with_name(take.stem + ".subtitles.json"), take.with_suffix(".sua.srt")
    co_srt_cu = bool(pd.get("co_srt_cu"))
    sub_truoc = (pd.get("sub_truoc") or {}).get("sha") if "sub_truoc" in pd else pd.get("sha_truoc")
    sub_sau = (pd.get("sub_sau") or {}).get("sha") or pd.get("sha_sau")
    if "srt_truoc" in pd:
        srt_truoc = (pd.get("srt_truoc") or {}).get("sha")
    else:                                        # nhật ký cũ: bản trước khi sửa = bản sao lưu
        srt_truoc = _sha_neu_co(bk / srt.name) if co_srt_cu else None
    srt_sau = (pd.get("srt_sau") or {}).get("sha") or pd.get("srt_sha_ghi")
    sub_nay, srt_nay = _sha_neu_co(sub), _sha_neu_co(srt)
    sub_goc = sub_nay is not None and sub_nay == sub_truoc
    srt_goc = srt_nay is None if not co_srt_cu else (srt_nay is not None and srt_nay == srt_truoc)
    ct = {"sub": sub, "srt": srt, "bk": bk, "co_srt_cu": co_srt_cu, "sub_goc": sub_goc, "srt_goc": srt_goc}
    if sub_goc and srt_goc:
        return GOC, ct
    sub_minh = sub_goc or (sub_nay is not None and sub_nay == sub_sau)
    # nhật ký rất cũ không có dấu .sua.srt: theo kết luận của .subtitles.json (sinh ra từ chính .sua.srt đó)
    srt_minh = srt_goc or (srt_nay is not None and (srt_sau is None or srt_nay == srt_sau))
    if not (sub_minh and srt_minh):
        return KHAC, ct
    if (not sub_goc and not (bk / sub.name).is_file()) or (not srt_goc and co_srt_cu and not (bk / srt.name).is_file()):
        return MAT, ct
    return MINH, ct


def _xet_hoan_tac(p: Path, g: dict, e: SimpleNamespace) -> dict[str, str]:
    """Xếp loại mọi mục gắn với VIDEO (chỉ đọc). Trả {tên file: loại}."""
    kq: dict[str, str] = {}
    if g["luong"] == "C" and g.get("done_sao_luu"):
        loai, done, _ = _xet_done(p, g)
        kq[done.name] = loai
    kq[_abs(p, g["nguon"]["file"]).name] = _xet_nguon(p, g, e)[0]
    kq["plan.json"] = _xet_plan_json(p, g)[0]
    return kq


def _tu_choi_neu_moi_hon(p: Path, g: dict, e: SimpleNamespace, da_doi: bool) -> None:
    xet = _xet_hoan_tac(p, g, e)
    khac = [t for t, l in xet.items() if l == KHAC]
    mat = [t for t, l in xet.items() if l == MAT]
    if not khac and not mat:
        return
    ly_do = "; ".join(
        ([f"đã có bản mới hơn sau lần sửa này ở {', '.join(khac)}"] if khac else [])
        + ([f"mất bản sao lưu của {', '.join(mat)}"] if mat else []))
    if da_doi:                                   # chạy lại sau khi đã đưa video về: không đè thêm gì, kiểm tay
        raise Thoat(5, f"Hoàn tác dừng giữa chừng: {ly_do} — video đã về bản cũ, phần còn lại giữ nguyên, kiểm tay")
    raise Thoat(2, f"Không hoàn tác tự động: {ly_do} — chưa đổi gì")


def hoan_tac(a: argparse.Namespace, e: SimpleNamespace, cb: list[str]) -> dict:
    p = Path(a.project)
    goc_f = tim_nhat_ky(p, a.thu_muc, a.video, a.viec_goc)
    if goc_f is None:
        raise Thoat(2, "Không thấy nhật ký của lần sửa cần hoàn tác")
    g = _doc_nk(goc_f)
    if g.get("loai") != "ap_dung" or g.get("buoc") != "xong":
        raise Thoat(2, "Lần sửa đó chưa xong — không hoàn tác được")
    if g.get("ten") != a.video:
        raise Thoat(2, "Nhật ký không thuộc video này")
    nk_f = goc_f.parent / f"{a.viec}.json"
    nk = _doc_nk(nk_f) if nk_f.exists() else None
    if nk is not None:
        if nk.get("loai") != "hoan_tac" or nk.get("viec_goc") != a.viec_goc:
            raise Thoat(2, "Nhật ký của mã việc này không phải việc hoàn tác lần sửa đó")
        cb.extend(nk.get("canh_bao") or [])
        if nk.get("buoc") == "xong":
            bo = nk.get("hoan_tac_bo_qua") or []
            if bo:                               # lần trước đã bỏ qua mục bị việc khác đổi: KHÔNG làm lại
                raise Thoat(5, f"Lần hoàn tác trước đã bỏ qua {', '.join(bo)} (việc khác đã đổi) — kiểm tay")
            return dict(nk.get("ket_qua") or {"trang_thai": "xong"})
    f = _abs(p, g["video"])
    cu, moi = g["cu"], g["moi"]
    sl = _abs(p, cu["sao_luu"])
    da_thay = _khop(f, cu) and nk is not None
    if not da_thay and not _khop(f, moi):
        raise Thoat(2, "Video đã đổi sau lần sửa — không hoàn tác tự động")
    if not da_thay and not sl.is_file():
        raise Thoat(2, "Không còn bản sao lưu của lần sửa này (đã bị dọn)")
    _tu_choi_neu_moi_hon(p, g, e, da_thay)       # FX-21: đối chiếu MỌI mục trước khi đè bất cứ thứ gì
    bo: list[str] = []
    if g.get("phu_de"):
        loai, ct = _xet_phu_de(p, g)
        if loai in (KHAC, MAT):
            bo.append("phụ đề")
            cb.append(f"Hoàn tác bỏ qua phụ đề ({ct['sub'].name}, {ct['srt'].name}): "
                      + ("video khác cùng take đã sửa tiếp sau lần này" if loai == KHAC else "mất bản sao lưu")
                      + " — giữ nguyên, kiểm tay")
    kiem_partial(f.parent)
    thu_khoa_file(f)
    lk = _abs(p, g["lien_ket"]) if g.get("lien_ket") else None
    if lk is not None and lk.exists():
        thu_khoa_file(lk)
    sl_moi = f.parent / "_sua_cu" / f"{f.stem}.{a.viec}.mp4"
    if nk is None:
        nk = {"viec": a.viec, "loai": "hoan_tac", "viec_goc": a.viec_goc, "luong": g["luong"], "video": g["video"],
              "thu_muc": a.thu_muc, "ten": a.video, "cu": dict(moi, sao_luu=_rel(p, sl_moi)),
              "moi": {"size": cu["size"], "mtime_ns": cu["mtime_ns"]}, "buoc": "thay"}
    nk["canh_bao"] = cb
    _ghi_json(nk_f, nk)
    try:
        if not da_thay:
            sl_moi.parent.mkdir(parents=True, exist_ok=True)
            if not sl_moi.exists():
                os.link(f, sl_moi)
            _thay_the(sl, f)                         # giữ mtime cũ → .done.json cũ khớp lại
        if not _khop(f, cu):
            raise Thoat(5, "Sau khi đưa bản cũ về, video không khớp kích thước/giờ cũ — kiểm tay")
        nk["buoc"] = "nguon"
        _ghi_json(nk_f, nk)
        _khoi_phuc_nguon(p, g, e, cb)
        nk["buoc"] = "phu_de"
        _ghi_json(nk_f, nk)
        if "phụ đề" not in bo:
            bo.extend(_khoi_phuc_phu_de(p, g, cb))
        nk["buoc"] = "lien_ket"
        _ghi_json(nk_f, nk)
        if lk is not None:
            noi_lien_ket(lk, f, sl_moi, g.get("lien_ket_kieu"), a.viec, cb)
    except Thoat:
        raise
    except BaseException as ex:
        log.exception("hoàn tác hỏng")
        if isinstance(ex, KeyboardInterrupt):
            raise
        raise Thoat(5, f"Hoàn tác hỏng giữa chừng ({type(ex).__name__}: {ex}) — bấm Chạy lại để làm nốt") from ex
    kq = {"trang_thai": "xong", "sao_luu": _rel(p, sl_moi), "canh_bao": list(dict.fromkeys(cb))}
    nk.update(buoc="xong", ket_qua=kq, canh_bao=kq["canh_bao"], hoan_tac_bo_qua=bo)
    _ghi_json(nk_f, nk)
    if bo:
        raise Thoat(5, f"Video đã về bản cũ nhưng hoàn tác bỏ qua {', '.join(bo)} (việc khác đã đổi) — kiểm tay")
    return dict(kq)


def _khoi_phuc_nguon(p: Path, g: dict, e: SimpleNamespace, cb: list[str]) -> None:
    """Đặt lại đúng mục chi_so (các mục khác có thể đã đổi), .done.json và mục plan.json — mỗi thứ xếp loại lại ngay
    trước khi đè (FX-21); thấy KHAC/MAT ở đây = có người đổi giữa lúc hoàn tác → dừng mã 5, không đè."""
    src = _abs(p, g["nguon"]["file"])
    loai, data, muc_cu = _xet_nguon(p, g, e)
    if loai not in (GOC, MINH):
        raise Thoat(5, f"{src.name} đổi giữa lúc hoàn tác — video đã về bản cũ, bản ghi giữ nguyên, kiểm tay")
    if loai == MINH:
        k = g["chi_so"]
        if g["luong"] == "C":
            data["plans"][k] = muc_cu
            e.rc.write_json(src, data)
        else:
            mt = src.stat().st_mtime_ns              # giữ mtime: luật tra luồng A (§3.3 bước 3)
            data[k] = muc_cu
            _ghi_json(src, data, indent=1)
            os.utime(src, ns=(time.time_ns(), mt))
    if g["luong"] != "C":
        return
    if g.get("done_sao_luu"):
        loai, done, nguon = _xet_done(p, g)
        if loai not in (GOC, MINH):
            raise Thoat(5, f"{done.name} đổi giữa lúc hoàn tác — giữ nguyên, kiểm tay")
        if loai == MINH:
            if nguon is None:
                done.unlink(missing_ok=True)         # trước khi sửa không có .done.json
            else:
                _chep_qua_tam(nguon, done)
    loai, ds, muc_cu = _xet_plan_json(p, g)
    if loai not in (GOC, MINH):
        raise Thoat(5, "plan.json đổi giữa lúc hoàn tác — giữ nguyên, kiểm tay")
    if loai == MINH:
        ten = f"plan_{g['plan_id']:03d}"
        muc = next(m for m in ds if isinstance(m, dict) and m.get("plan_id") == ten)
        muc["segments"] = muc_cu["segments"]
        _ghi_json(src.parent / "plan.json", ds, indent=2)


def _khoi_phuc_phu_de(p: Path, g: dict, cb: list[str]) -> list[str]:
    """Phụ đề + .sua.srt: chỉ đè khi hiện tại vẫn đúng là thứ lần sửa đó ghi. Trả danh sách mục bỏ qua."""
    if not g.get("phu_de"):
        return []
    loai, ct = _xet_phu_de(p, g)
    if loai == GOC:
        return []
    if loai != MINH:
        cb.append(f"Hoàn tác bỏ qua phụ đề ({ct['sub'].name}): đổi giữa lúc hoàn tác — giữ nguyên, kiểm tay")
        return ["phụ đề"]
    sub, srt, bk = ct["sub"], ct["srt"], ct["bk"]
    if not ct["sub_goc"]:
        _chep_qua_tam(bk / sub.name, sub)
    if not ct["srt_goc"]:
        if ct["co_srt_cu"]:
            _chep_qua_tam(bk / srt.name, srt)
        else:
            srt.unlink(missing_ok=True)
    return []


# ---------------- dòng lệnh ----------------

def _kiem_tham_so(a: argparse.Namespace) -> None:
    if a.thu_muc not in sv.THU_MUC:
        raise Thoat(2, f"--thu-muc phải là một trong {list(sv.THU_MUC)}")
    if not sv.RE_TEN.fullmatch(a.video):
        raise Thoat(2, "Tên video không hợp lệ")
    for ten in ("viec", "viec_goc"):
        x = getattr(a, ten, None)
        if x is not None and not sv.RE_VIEC.fullmatch(x):
            raise Thoat(2, f"--{ten.replace('_', '-')} không hợp lệ")
    if not Path(a.project).is_dir():
        raise Thoat(2, "Không thấy thư mục dự án")
    if not (Path(a.project) / a.thu_muc / a.video).is_file() and a.lenh == "ap-dung" \
            and tim_nhat_ky(Path(a.project), a.thu_muc, a.video, a.viec) is None:
        raise Thoat(2, "Không thấy video này (có thể đã bị xoá hoặc đổi tên)")


def chay(a: argparse.Namespace, cb: list[str]) -> dict:
    _kiem_tham_so(a)
    e = nap_engine()
    kiem_engine(e)
    p = Path(a.project)
    if a.lenh == "ap-dung" and a.xem:
        ph = PhienSua(a, e, cb)
        c = ph.chuan_bi()
        return {"trang_thai": "xem", "sao_luu": None, "luong": c.b.luong,
                "tom_tat": {"so_cau": len(c.ban["phu_de"]), "so_clip": len(c.ban["doi_clip"]),
                            "so_doi_cho": len(c.ban["doi_cho"])}, "canh_bao": list(dict.fromkeys(cb))}
    khoa = lay_khoa(p, a.viec, cho_khoa_giay())
    try:
        if a.lenh == "ap-dung":
            return PhienSua(a, e, cb).chay()
        return hoan_tac(a, e, cb)
    finally:
        tha_khoa(khoa, cb)


def tao_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sua_video_engine.py", description="Sửa và dựng lại 1 video (docs/sua-video.md §6)")
    sub = ap.add_subparsers(dest="lenh", required=True)
    for ten in ("ap-dung", "hoan-tac"):
        s = sub.add_parser(ten)
        s.add_argument("--project", required=True)
        s.add_argument("--thu-muc", required=True)
        s.add_argument("--video", required=True)
        s.add_argument("--viec", required=True)
        if ten == "ap-dung":
            s.add_argument("--ban-sua", required=True)
            s.add_argument("--xem", action="store_true", help="chạy khô: kiểm hết, không ghi dự án, không render")
        else:
            s.add_argument("--viec-goc", required=True)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = tao_parser().parse_args(argv)
    t0 = time.time()
    cb: list[str] = []
    try:
        kq, ma = chay(a, cb), 0
    except Thoat as t:
        ma, kq = t.ma, {"trang_thai": {2: "khong_hop_le", 3: "ban", 4: "dung_hong", 5: "do_dang"}.get(t.ma, "loi"),
                        "ly_do": t.ly_do}
    except sv.KhongTraDuoc as t:
        ma, kq = 2, {"trang_thai": "khong_hop_le", "ly_do": t.ly_do}
    except ThamSoLoi as t:
        ma, kq = 2, {"trang_thai": "khong_hop_le", "ly_do": str(t)}
    except Exception as t:  # lỗi ngoài dự kiến: không đoán trạng thái — để người kiểm nhật ký
        log.exception("lỗi ngoài dự kiến")
        ma, kq = 5, {"trang_thai": "loi", "ly_do": f"Lỗi ngoài dự kiến ({type(t).__name__}: {t}) — xem log"}
    kq.setdefault("sao_luu", None)
    kq["canh_bao"] = list(dict.fromkeys([*(kq.get("canh_bao") or []), *cb]))
    kq.update(video=a.video, giay=round(time.time() - t0, 1))
    if ma:
        print(f"[sua_video] mã {ma}: {kq.get('ly_do')}", file=sys.stderr, flush=True)
    print("KET_QUA_JSON " + json.dumps(kq, ensure_ascii=False), flush=True)
    return ma


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
        sys.stderr.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main())
