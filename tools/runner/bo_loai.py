"""Đưa thư mục đăng của một sản phẩm về đúng kết quả chấm (việc miễn phí poster_bo_loai, docs/giao-dien-menu-trai.md §4.9).

    python -B -I bo_loai.py --repo-kho <repo kho> --uid <19 số> --goc <GOC> [--goc <GOC>...] [--xem] [--tu-remote]

- `--tu-remote` (runner luôn dùng): đọc duyet.json BẢN MỚI NHẤT trên remote: `git fetch` (có timeout) rồi
  `git cat-file blob <upstream>:data/<uid>/duyet.json`. KHÔNG pull, không đụng cây làm việc/index (web ghi duyet.json
  thẳng lên GitHub; cây làm việc máy nhà có thể cũ). Fetch/đọc lỗi → mã 2, không dời gì. Không có cờ → đọc cây
  làm việc như cũ.

- Video ở cấp trên của `<GOC>/*<UID>/output_poster/` và `…/output/` có mục duyệt CUỐI khớp (goc, ten, sua_luc) là
  `loai` → `os.replace` sang `<thư mục>/_loai/<ten>`.
- Video trong `_loai/` mà mục duyệt cuối KHÔNG còn là `loai` (chấm lại Đạt / Bỏ duyệt) → chuyển về.
- `os.replace` cùng thư mục cha nên nguyên tử và giữ mtime: `sua_luc = int(mtime)` (tools/video_server.py:458) không
  đổi, khoá duyệt vẫn khớp. Poster không quét thư mục con nên `_loai/` không bị đăng.
- Khoá goc giống hệt video_server (`ds_nguon`): output_poster → "<GOC posix>"; output → "<GOC posix>#<dự án>/output".
- Không bao giờ đụng output-adam/, output_daonguoc/ (bản gốc của hardlink), compose_output/.
- Không ghi file trạng thái nào: duyet.json chỉ đọc; hỏng → dừng, mã 2, không dời gì. CHƯA CÓ duyet.json → không dời
  chiều nào (không "trả về" cả _loai/ chỉ vì thiếu dữ liệu chấm).
- Khoá goc so khớp sau khi chuẩn hoá (`chuan_khoa_goc`: hoa/thường, `/` và `\\`) ở CẢ HAI phía: KHO_VIDEO_GOC của
  video_server và --goc của runner có thể viết khác nhau (E:/ và e:\\) mà vẫn là một thư mục trên Windows.

In: `DOI: <ten> -> _loai`, `TRA: <ten>`, `BO_QUA: <ten> (<lý do>)`, dòng cuối `TONG: bo=N tra=M bo_qua=K`.
Mã thoát: 0 = xong; 5 = có file bị bỏ qua (đang bị khoá / trùng tên / đổi giữa chừng — cần kiểm tay); 2 = lỗi dữ liệu.
Lỗi hệ thống khác (đĩa đầy, mất quyền thư mục…) KHÔNG bị nuốt: ném tiếp, tiến trình thoát ≠ 0 kèm traceback.

Thuần stdlib, không import tương đối: chạy được như script trong bản cài (D8) và import được từ danh_muc.
"""
from __future__ import annotations

import argparse
import json
import logging
import ntpath
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

RE_UID = re.compile(r"^\d{19}$", re.ASCII)
DUOI = frozenset({".mp4", ".mov", ".m4v"})          # = DUOI của tools/video_server.py
THU_MUC_DANG = ("output_poster", "output")          # = THU_MUC của tools/video_server.py (chỉ 2 thư mục này)
TEN_LOAI = "_loai"
KET_QUA = frozenset({"dat", "loai", ""})            # = KET_QUA của cf/src/worker.js
MA_XONG, MA_LOI_DU_LIEU, MA_BO_QUA = 0, 2, 5
SO_LAN_THU = 3                                       # os.replace thử lại khi NTFS khoá tạm (Indexer/Antivirus)
CHO_THU_LAI_S = 0.3
HET_GIO_FETCH_S = 60                                 # git fetch (mạng)
HET_GIO_GIT_S = 20                                   # lệnh git cục bộ (rev-parse, ls-tree, cat-file)
CHO_KHOA_GIT_S = 2.0                                 # fetch vướng khoá ref tạm: chờ 2 s, 4 s rồi bỏ (--tu-remote)
SO_LUOT = 3                                          # --tu-remote: fetch + dời lại tới khi khớp, tối đa 3 lượt
LY_DO_KHONG_MUC = ("không có mục chấm khớp (bỏ chấm / video đổi sau khi chấm / gốc đổi) — giữ trong _loai, "
                   "chấm lại Đạt để trả về")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_RE_REF = re.compile(r"^refs/[A-Za-z0-9._/-]+$", re.ASCII)

Khoa = tuple[str, str, int]                          # (goc, ten, sua_luc)


class LoiDuLieu(ValueError):
    """Dữ liệu đầu vào sai (uid, repo, duyet.json) → mã 2, không dời gì."""


class LoiGit(LoiDuLieu):
    """Không lấy được bản mới nhất từ remote (fetch lỗi/quá giờ, không có upstream, không chạy được git).
    Là LoiDuLieu: không biết dữ liệu chấm mới nhất → không dời gì, không cho qua.
    `tam_thoi` = CHẮC CHẮN chỉ là khoá git đang bị tiến trình khác giữ (bên gọi nên chờ rồi thử lại)."""

    def __init__(self, thong_diep: str, *, tam_thoi: bool = False) -> None:
        super().__init__(thong_diep)
        self.tam_thoi = tam_thoi


@dataclass(frozen=True)
class Doi:
    huong: str          # "bo" (→ _loai) | "tra" (_loai → về) | "giu" (trong _loai, không có mục chấm khớp)
    nguon: Path
    dich: Path
    sua_luc: int


@dataclass
class KetQua:
    bo: int = 0
    tra: int = 0
    bo_qua: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ma_thoat(self) -> int:
        return MA_BO_QUA if self.bo_qua else MA_XONG


def kiem_uid(uid: object) -> str:
    if not isinstance(uid, str) or not RE_UID.fullmatch(uid):
        raise LoiDuLieu("uid phải là 19 chữ số")
    return uid


def _kiem_muc(m: object, i: int) -> Khoa:
    """Mục duyệt → khoá (goc, ten, sua_luc). Sai hình dạng → LoiDuLieu (không đoán: đọc sai có thể trả video Loại về)."""
    if not isinstance(m, dict):
        raise LoiDuLieu(f"duyet.json: mục {i} không phải object")
    goc, ten, sua_luc, kq = m.get("goc"), m.get("ten"), m.get("sua_luc"), m.get("ket_qua")
    if not isinstance(goc, str) or not goc:
        raise LoiDuLieu(f"duyet.json: mục {i} thiếu goc")
    if not isinstance(ten, str) or not ten or "/" in ten or "\\" in ten:
        raise LoiDuLieu(f"duyet.json: mục {i} có ten sai")
    if isinstance(sua_luc, bool) or not isinstance(sua_luc, int) or sua_luc < 0:
        raise LoiDuLieu(f"duyet.json: mục {i} có sua_luc sai")
    if kq not in KET_QUA:
        raise LoiDuLieu(f"duyet.json: mục {i} có ket_qua lạ")
    return goc, ten, sua_luc


def chuan_khoa_goc(goc: str) -> str:
    """Khoá goc để SO KHỚP: chữ thường + dấu `/`. Đường dẫn Windows không phân biệt hoa thường, và video_server
    (KHO_VIDEO_GOC) với runner (--goc) có thể viết cùng một gốc khác nhau. Dùng ntpath để kết quả như nhau trên
    mọi hệ (dữ liệu là đường dẫn máy nhà Windows)."""
    return ntpath.normcase(goc).replace("\\", "/")


def phan_tich_duyet(noi: str, nguon: str) -> dict[Khoa, str]:
    """{(goc đã chuẩn hoá, ten, sua_luc): ket_qua} từ nội dung duyet.json. Mục sau thắng. Hỏng → LoiDuLieu."""
    try:
        d = json.loads(noi)
    except ValueError as e:
        raise LoiDuLieu(f"{nguon} không phải JSON hợp lệ: {e}") from e
    if not isinstance(d, dict):
        raise LoiDuLieu(f"{nguon} không phải object")
    ds = d.get("videos", [])
    if not isinstance(ds, list):
        raise LoiDuLieu(f"{nguon}: videos không phải danh sách")
    kq: dict[Khoa, str] = {}
    for i, m in enumerate(ds):
        goc, ten, sua_luc = _kiem_muc(m, i)          # kiểm TRƯỚC khi đọc ket_qua (m có thể không phải dict)
        kq[(chuan_khoa_goc(goc), ten, sua_luc)] = m["ket_qua"]   # mục sau ghi đè mục trước cùng khoá
    return kq


def _giai_ma(du_lieu: bytes, nguon: str) -> str:
    try:
        return du_lieu.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise LoiDuLieu(f"{nguon} không phải UTF-8: {e}") from e


def doc_ket_qua_duyet(repo_kho: Path, uid: str) -> dict[Khoa, str] | None:
    """Kết quả chấm từ `<repo>/data/<uid>/duyet.json` của CÂY LÀM VIỆC. Chưa có file → None (KHÁC {}: chưa biết)."""
    uid = kiem_uid(uid)
    f = Path(repo_kho) / "data" / uid / "duyet.json"
    ten = f"data/{uid}/duyet.json"                   # tương đối repo: không in đường dẫn ổ đĩa ra log việc
    try:
        du_lieu = f.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise LoiDuLieu(f"không đọc được {ten}: {e.strerror or type(e).__name__}") from e
    return phan_tich_duyet(_giai_ma(du_lieu, ten), ten)


# ---------- đọc bản mới nhất trên remote (không pull, không đụng cây làm việc) ----------

# Đường dẫn tuyệt đối (Windows `X:\` `X:/`, hoặc `/a/…`), CÓ THỂ chứa dấu cách:
# - trong nháy đơn/kép → che trọn tới nháy đóng;
# - không nháy → che tới `: ` / `:` cuối dòng (git: "<đường dẫn>: File exists") hoặc hết dòng. Thà che thừa.
_RE_DUONG_DAN_NHAY = re.compile(r"(['\"])(?:[A-Za-z]:[\\/]|/)[^'\"\r\n]*\1")
_RE_DUONG_DAN = re.compile(r"(?<![\w.])(?:[A-Za-z]:[\\/]|/(?=[^\s'\"/:]+/))[^'\"\r\n]*?(?=:\s|:$|['\"]|$)",
                           re.MULTILINE)
_RE_KHOA_BAN = re.compile(r"\.lock'?: File exists", re.IGNORECASE)   # git: "Unable to create '<…>.lock': File exists"


def _che_duong_dan(s: str) -> str:
    """Bỏ đường dẫn tuyệt đối khỏi thông báo git (stderr gộp vào log việc, có thể lên web)."""
    return _RE_DUONG_DAN.sub("<đường dẫn>", _RE_DUONG_DAN_NHAY.sub(r"\1<đường dẫn>\1", s))


def _giet_cay(p: subprocess.Popen) -> None:
    """Giết cả cây tiến trình (git → git-remote-https → Git Credential Manager…). Có giới hạn giờ, không treo."""
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, timeout=15,
                           check=False, stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning("taskkill cây git pid %d lỗi: %s", p.pid, type(e).__name__)
    else:
        try:
            os.killpg(p.pid, 9)                          # start_new_session=True → pgid = pid
        except ProcessLookupError:
            pass                                         # cả nhóm đã thoát
        except OSError as e:
            log.warning("killpg cây git pid %d lỗi: %s", p.pid, e.strerror)
    p.kill()                                             # Popen.kill bỏ qua tiến trình đã thoát
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        log.error("git pid %d vẫn chưa thoát sau khi giết — bỏ, không chờ thêm", p.pid)


def _chay_gioi_han(argv: list[str], het_gio_s: float, *, env: dict[str, str] | None = None
                   ) -> tuple[int, bytes, bytes]:
    """Chạy argv, quá `het_gio_s` → giết cả cây rồi LoiGit. stdout/stderr ghi vào FILE tạm, không qua pipe: tiến
    trình cháu (git-remote-https, GCM) còn giữ handle cũng không làm treo (bẫy communicate() sau kill() của
    subprocess.run trên Windows). Không chạy được → LoiGit."""
    with tempfile.TemporaryFile() as ra, tempfile.TemporaryFile() as loi:
        try:
            p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=ra, stderr=loi, env=env,
                                 creationflags=_NO_WINDOW, start_new_session=os.name != "nt")
        except OSError as e:
            raise LoiGit(f"không chạy được {Path(argv[0]).name}: {e.strerror or type(e).__name__}") from e
        try:
            rc = p.wait(timeout=het_gio_s)
        except subprocess.TimeoutExpired as e:
            _giet_cay(p)
            raise LoiGit(f"{Path(argv[0]).name} quá {het_gio_s:g} giây (mạng treo / chờ đăng nhập?)") from e
        finally:
            if p.poll() is None:                         # lỗi bất ngờ (KeyboardInterrupt…) → không bỏ rơi cây
                _giet_cay(p)
        ra.seek(0)
        loi.seek(0)
        return rc, ra.read(), loi.read()


_GIT_KHONG_HOI = ("-c", "credential.interactive=false", "-c", "http.lowSpeedLimit=1000",
                  "-c", "http.lowSpeedTime=30")


# fetch: không tự gc/maintenance (tự chạy sẽ giữ khoá lâu, đụng kho.py pull).
_GIT_KHONG_DON = ("-c", "gc.auto=0", "-c", "maintenance.auto=false")


def _chay_git(repo: Path, args: list[str], het_gio_s: float, *, cau_hinh: tuple[str, ...] = ()
              ) -> tuple[int, bytes, str]:
    """git [cau_hinh] -C <repo> <args>, có timeout, KHÔNG hỏi mật khẩu (terminal lẫn hộp thoại GCM), cắt kết nối
    chậm. Trả (mã, stdout, stderr THÔ — che bằng _tom trước khi đưa vào thông báo). Không chạy được / quá giờ →
    LoiGit."""
    argv = ["git", "--no-optional-locks", "-c", "core.quotepath=false", *_GIT_KHONG_HOI, *cau_hinh, "-C", str(repo),
            *args]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    rc, out, err = _chay_gioi_han(argv, het_gio_s, env=env)
    return rc, out, err.decode("utf-8", "replace").strip()


def _tom(err: str) -> str:
    return _che_duong_dan(err)[:300]


def lay_ban_moi_nhat(repo_kho: Path, *, fetch: bool = True) -> str:
    """Ref upstream của nhánh hiện tại (vd `refs/remotes/origin/main`), sau `git fetch` nếu `fetch`.
    fetch chỉ cập nhật ref remote trong .git: không merge/rebase, cây làm việc và index giữ nguyên.
    fetch vướng khoá ref (`<…>.lock': File exists` — kho.py/git khác đang ghi) → LoiGit(tam_thoi=True)."""
    repo = Path(repo_kho)
    rc, out, err = _chay_git(repo, ["rev-parse", "--symbolic-full-name", "@{u}"], HET_GIO_GIT_S)
    ref = out.decode("utf-8", "replace").strip()
    if rc != 0 or not _RE_REF.fullmatch(ref):
        raise LoiGit(f"nhánh hiện tại của kho không có nhánh theo dõi trên remote: {_tom(err) or _tom(ref)!r}")
    if fetch:
        rc, _out, err = _chay_git(repo, ["fetch", "--quiet", "--no-tags", "--no-write-fetch-head"], HET_GIO_FETCH_S,
                                  cau_hinh=_GIT_KHONG_DON)
        if rc != 0:
            raise LoiGit(f"git fetch lỗi (mã {rc}): {_tom(err)}", tam_thoi=bool(_RE_KHOA_BAN.search(err)))
    return ref


def doc_file_ban_moi(repo_kho: Path, ref: str, duong: str) -> bytes | None:
    """Nội dung `<ref>:<duong>` (đường dẫn trong repo, dấu `/`). Không có trên ref → None. Lỗi git → LoiGit."""
    repo = Path(repo_kho)
    rc, out, err = _chay_git(repo, ["ls-tree", "-z", ref, "--", duong], HET_GIO_GIT_S)
    if rc != 0:
        raise LoiGit(f"git ls-tree {duong} lỗi (mã {rc}): {_tom(err)}")
    if not out:
        return None
    phan = out.split(b" ", 2)                        # "<mode> <type> <sha>\t<path>\0"
    if len(phan) < 3 or phan[1] != b"blob":
        raise LoiDuLieu(f"{ref}:{duong} không phải file")
    rc, du_lieu, err = _chay_git(repo, ["cat-file", "blob", f"{ref}:{duong}"], HET_GIO_GIT_S)
    if rc != 0:
        raise LoiGit(f"git cat-file {duong} lỗi (mã {rc}): {_tom(err)}")
    return du_lieu


def doc_ket_qua_duyet_ref(repo_kho: Path, ref: str, uid: str) -> dict[Khoa, str] | None:
    """Kết quả chấm ở `<ref>:data/<uid>/duyet.json`. Chưa có file → None. Hỏng → LoiDuLieu."""
    duong = f"data/{kiem_uid(uid)}/duyet.json"
    du_lieu = doc_file_ban_moi(repo_kho, ref, duong)
    if du_lieu is None:
        return None
    nguon = f"{ref}:{duong}"
    return phan_tich_duyet(_giai_ma(du_lieu, nguon), nguon)


def doc_ket_qua_duyet_moi_nhat(repo_kho: Path, uid: str, *, fetch: bool = True) -> dict[Khoa, str] | None:
    """Như doc_ket_qua_duyet nhưng đọc bản trên remote (fetch rồi đọc ref upstream). Lỗi git → LoiGit."""
    kiem_uid(uid)
    return doc_ket_qua_duyet_ref(repo_kho, lay_ban_moi_nhat(repo_kho, fetch=fetch), uid)


def khoa_goc(goc: Path, du_an: Path, thu: str) -> str:
    """Khoá goc y như video_server.ds_nguon (tools/video_server.py:118). So khớp qua chuan_khoa_goc."""
    g = Path(goc).as_posix()
    return g if thu == "output_poster" else f"{g}#{du_an.name}/{thu}"


def _la_thu_muc_uid(ten: str, uid: str) -> bool:
    """Tên kết thúc bằng UID và ký tự ngay trước UID không phải chữ số (giống du_an._thu_muc_cua_uid)."""
    return ten.endswith(uid) and not (len(ten) > len(uid) and ten[-len(uid) - 1] in "0123456789")


def du_an_cua_uid(uid: str, gocs: list[Path]) -> list[tuple[Path, Path]]:
    kiem_uid(uid)
    kq: list[tuple[Path, Path]] = []
    for g in gocs:
        g = Path(g)
        if not g.is_dir():          # ổ chưa cắm: bỏ gốc này (không đụng gì ở đó)
            log.warning("bỏ qua gốc không đọc được: %s", _sach(g.name))   # chỉ tên: stderr vào log việc
            continue
        kq += [(g, d) for d in sorted(g.glob(f"*{uid}")) if d.is_dir() and _la_thu_muc_uid(d.name, uid)]
    return kq


def _video_trong(thu: Path) -> list[Path]:
    if not thu.is_dir():
        return []
    return sorted((f for f in thu.iterdir() if f.is_file() and f.suffix.lower() in DUOI), key=lambda f: f.name.lower())


def _sua_luc(f: Path) -> int:
    return int(f.stat().st_mtime)


def lap_ke_hoach(repo_kho: Path, uid: str, gocs: list[Path]) -> list[Doi]:
    """Các lần dời cần làm theo duyet.json của CÂY LÀM VIỆC (chưa làm gì). Rỗng = đã khớp kết quả chấm."""
    return lap_ke_hoach_tu(doc_ket_qua_duyet(repo_kho, uid), uid, gocs)


def lap_ke_hoach_tu(kq: dict[Khoa, str] | None, uid: str, gocs: list[Path]) -> list[Doi]:
    """Các lần dời cần làm theo kết quả chấm `kq` (khoá đã chuẩn hoá). `kq` None (chưa có duyet.json) → []:
    KHÔNG coi là "không có Loại" để trả hàng loạt từ _loai/ về.
    Chiều trả fail-closed (FX-B3): chỉ trả khi có mục chấm khớp ĐÚNG (goc chuẩn hoá, ten, sua_luc) và mục cuối khác
    "loai" (Đạt, hoặc "" = bỏ chấm còn góp ý). Không có mục → "giu" (BO_QUA khi thực hiện, mã 5)."""
    kiem_uid(uid)
    if kq is None:
        return []
    ke: list[Doi] = []
    for g, d in du_an_cua_uid(uid, gocs):
        for thu in THU_MUC_DANG:
            o = d / thu
            if not o.is_dir():
                continue
            kg = chuan_khoa_goc(khoa_goc(g, d, thu))
            loai = o / TEN_LOAI
            for f in _video_trong(o):
                s = _sua_luc(f)
                if kq.get((kg, f.name, s)) == "loai":
                    ke.append(Doi("bo", f, loai / f.name, s))
            for f in _video_trong(loai):
                s = _sua_luc(f)
                muc = kq.get((kg, f.name, s))
                if muc is None:
                    ke.append(Doi("giu", f, o / f.name, s))
                elif muc != "loai":
                    ke.append(Doi("tra", f, o / f.name, s))
    return ke


def viec_con(ke: list[Doi]) -> list[Doi]:
    """Các lần dời thật (bo/tra) — bỏ "giu" (không tự xử được, cần người chấm lại)."""
    return [d for d in ke if d.huong in ("bo", "tra")]


@dataclass(frozen=True)
class FolderKho:
    """Folder Poster là `<GOC>/*<UID>/output_poster|output` của kho."""
    uid: str
    goc: Path
    du_an: Path
    thu: str
    duong_dan: Path


def loai_trong_folder_tu(fk: FolderKho, kq: dict[Khoa, str] | None) -> list[str]:
    """Tên video bị Loại còn ở cấp trên của folder `fk` theo kết quả chấm `kq` (None = chưa chấm → [])."""
    if kq is None:
        return []
    kg = chuan_khoa_goc(khoa_goc(fk.goc, fk.du_an, fk.thu))
    return [f.name for f in _video_trong(fk.duong_dan) if kq.get((kg, f.name, _sua_luc(f))) == "loai"]


def loai_trong_folder(duong_dan: str, repo_kho: Path, gocs: list[Path]) -> list[str] | None:
    """Như loai_trong_folder_tu, đọc duyet.json của CÂY LÀM VIỆC. None = folder không phải của kho (không biết →
    không chặn). duyet.json hỏng → LoiDuLieu. (Runner đọc bản remote mới nhất: danh_muc._dk_poster_len_lich.)"""
    fk = folder_cua_kho(duong_dan, gocs)
    if fk is None:
        return None
    return loai_trong_folder_tu(fk, doc_ket_qua_duyet(repo_kho, fk.uid))


def uid_cua_folder(duong_dan: object) -> str | None:
    """UID của sản phẩm sở hữu folder Poster: thư mục CHA kết thúc bằng 19 chữ số (ký tự trước không phải số).
    Áp cho MỌI thư mục con (output_poster, output, compose_output của creator…), không cần khớp gốc. None = không
    nhận ra."""
    if not isinstance(duong_dan, str) or not duong_dan.strip():
        return None
    d = Path(duong_dan.strip()).parent
    m = re.search(r"(\d{19})$", d.name, re.ASCII)
    if not m or not _la_thu_muc_uid(d.name, m.group(1)):
        return None
    return m.group(1)


def folder_cua_kho(duong_dan: object, gocs: list[Path]) -> FolderKho | None:
    """Nhận diện folder Poster. None = không phải thư mục đăng `<GOC>/*<UID>/output_poster|output` của kho."""
    if not isinstance(duong_dan, str) or not duong_dan.strip():
        return None
    p = Path(duong_dan.strip())
    thu, d = p.name, p.parent
    if thu not in THU_MUC_DANG:
        return None
    m = re.search(r"(\d{19})$", d.name, re.ASCII)
    if not m or not _la_thu_muc_uid(d.name, m.group(1)):
        return None
    chuan = os.path.normcase(os.path.normpath(str(d.parent)))
    g = next((Path(x) for x in gocs if os.path.normcase(os.path.normpath(str(x))) == chuan), None)
    if g is None:
        return None
    return FolderKho(uid=m.group(1), goc=g, du_an=d, thu=thu, duong_dan=p)


def _thay_file(nguon: Path, dich: Path) -> None:
    os.replace(nguon, dich)


def _ngu(giay: float) -> None:
    time.sleep(giay)


def _sach(s: str) -> str:
    """Tên file là dữ liệu người dùng: bỏ ký tự điều khiển để một tên không chèn được dòng giả vào log."""
    return "".join(c if c.isprintable() else "?" for c in s)


def _dong(d: Doi) -> str:
    return f"DOI: {_sach(d.nguon.name)} -> {TEN_LOAI}" if d.huong == "bo" else f"TRA: {_sach(d.nguon.name)}"


def _thu_dang(d: Doi) -> str:
    """Tên thư mục đăng (output_poster|output) của lần dời: không in đường dẫn ổ đĩa ra log."""
    return (d.nguon.parent if d.huong == "bo" else d.dich.parent).name


def _thu_doi(d: Doi) -> str | None:
    """Dời một file. Trả lý do bỏ qua, hoặc None nếu đã dời. Chỉ PermissionError (file đang mở) được bỏ qua."""
    if d.dich.exists():
        return "trùng tên ở nơi đến, không ghi đè"
    try:
        if _sua_luc(d.nguon) != d.sua_luc:
            return "file vừa đổi (sua_luc khác lúc quét)"
    except FileNotFoundError:
        return "file vừa biến mất"
    if d.huong == "bo":
        d.dich.parent.mkdir(exist_ok=True)
    for lan in range(SO_LAN_THU):
        try:
            _thay_file(d.nguon, d.dich)
            return None
        except PermissionError as e:
            log.warning("đang bị khoá %s (lần %d/%d): %s", _sach(d.nguon.name), lan + 1, SO_LAN_THU,
                        e.strerror or type(e).__name__)
            if lan + 1 < SO_LAN_THU:
                _ngu(CHO_THU_LAI_S * (2 ** lan))
    return "đang bị khoá (đang phát / đang tải?)"


def thuc_hien(ke: list[Doi], *, xem: bool = False) -> KetQua:
    kq = KetQua()
    for d in ke:
        ly_do = LY_DO_KHONG_MUC if d.huong == "giu" else None if xem else _thu_doi(d)
        if ly_do is not None:
            kq.bo_qua.append((d.nguon.name, ly_do))
            print(f"BO_QUA: {_sach(d.nguon.name)} ({ly_do}) [{_sach(_thu_dang(d))}]", flush=True)
            continue
        print(("XEM " if xem else "") + _dong(d) + f" [{_sach(_thu_dang(d))}]", flush=True)
        if d.huong == "bo":
            kq.bo += 1
        else:
            kq.tra += 1
    print(f"TONG: bo={kq.bo} tra={kq.tra} bo_qua={len(kq.bo_qua)}", flush=True)
    return kq


def _doc_moi_nhat_thu_lai(repo: Path, uid: str) -> dict[Khoa, str] | None:
    """doc_ket_qua_duyet_moi_nhat; fetch vướng khoá ref TẠM (kho.py đang pull/push) → chờ rồi thử lại, tối đa
    SO_LAN_THU lần. Lỗi khác hoặc hết lượt → ném LoiGit."""
    lan = 0
    while True:
        try:
            return doc_ket_qua_duyet_moi_nhat(repo, uid)
        except LoiGit as e:
            lan += 1
            if not e.tam_thoi or lan >= SO_LAN_THU:
                raise
            log.warning("git kho đang bận (khoá ref) — thử lại (%d/%d)", lan, SO_LAN_THU)
            _ngu(CHO_KHOA_GIT_S * (2 ** (lan - 1)))


def chay_tu_remote(repo: Path, uid: str, gocs: list[Path], *, xem: bool = False) -> int:
    """--tu-remote (FX-B3): fetch → lập kế hoạch → dời; rồi fetch + lập LẠI, tới khi không còn việc hoặc SO_LUOT lượt
    (việc mới cùng uid bị chặn trùng khi việc này đang chạy, nên chính nó phải bắt kịp lần chấm ghi giữa chừng).
    Vẫn còn việc sau SO_LUOT lượt → dòng CON_VIEC, mã 5."""
    ma = MA_XONG
    for luot in range(1, SO_LUOT + 1):
        ke = lap_ke_hoach_tu(_doc_moi_nhat_thu_lai(repo, uid), uid, gocs)
        con = viec_con(ke)
        if luot > 1 and not con:
            return ma
        print(f"LUOT: {luot}", flush=True)
        ma = thuc_hien(ke, xem=xem).ma_thoat
        if xem or not con:
            return ma
    con = viec_con(lap_ke_hoach_tu(_doc_moi_nhat_thu_lai(repo, uid), uid, gocs))
    if con:
        print(f"CON_VIEC: {len(con)} video chưa khớp kết quả chấm sau {SO_LUOT} lượt (đang bị khoá hoặc vừa chấm "
              "lại) — chạy lại 'Gỡ video Loại'", flush=True)
        return MA_BO_QUA
    return ma


def main(argv: list[str] | None = None) -> int:
    for luong in (sys.stdout, sys.stderr):
        cau_hinh = getattr(luong, "reconfigure", None)      # TextIO không khai báo reconfigure (mypy)
        if callable(cau_hinh):
            try:
                cau_hinh(encoding="utf-8", errors="replace")
            except ValueError as e:                          # luồng đã ghi dở: giữ mã hoá cũ, vẫn chạy
                log.debug("không đổi được mã hoá luồng: %s", e)
    ap = argparse.ArgumentParser(description="Dời video bị chấm Loại khỏi thư mục đăng (hoàn tác được)")
    ap.add_argument("--repo-kho", required=True)
    ap.add_argument("--uid", required=True)
    ap.add_argument("--goc", action="append", required=True)
    ap.add_argument("--xem", action="store_true", help="chỉ in việc sẽ làm, không dời gì")
    ap.add_argument("--tu-remote", action="store_true",
                    help="đọc duyet.json bản mới nhất trên remote (git fetch + đọc ref upstream, không pull)")
    a = ap.parse_args(argv)
    repo = Path(a.repo_kho)
    try:
        if not (repo / "data").is_dir():
            raise LoiDuLieu("không thấy thư mục data/ trong --repo-kho (sai --repo-kho?)")
        gocs = [Path(g) for g in a.goc]
        if a.tu_remote:
            return chay_tu_remote(repo, a.uid, gocs, xem=a.xem)
        ke = lap_ke_hoach(repo, a.uid, gocs)
    except LoiDuLieu as e:
        print(f"[LỖI] {e}", file=sys.stderr, flush=True)
        return MA_LOI_DU_LIEU
    return thuc_hien(ke, xem=a.xem).ma_thoat


if __name__ == "__main__":
    sys.exit(main())
