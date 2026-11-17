"""Cài bộ chạy việc ra thư mục cố định ngoài repo (D8, docs/bo-chay-viec.md §4.1).

    python tools/cai_runner.py                 # cài vào E:\\kho-runner\\app (hoặc KHO_RUNNER_DIR\\app)
    python tools/cai_runner.py --dich <thư mục app>

Bố cục bản cài (giữ đúng cấu trúc import của repo):
    app\\chay_runner.py
    app\\runner\\*.py           (trừ test_*, spike_*, tao_khoa_ky.py)
    app\\ky_cong_khai.pem       (nếu repo có tools/runner/ky_cong_khai.pem)
    app\\PHIEN_BAN, app\\runner\\PHIEN_BAN
    app\\TONG_KIEM.json         (sha256 từng file, runner so lúc khởi động)

Các bước: giành khoá đơn instance của thư mục dữ liệu (giành không được = runner đang chạy → mã 4) → sao lưu
runner.db thành `runner.db.bak-<giờ>` (sqlite3 backup API, giữ 5 bản mới nhất; lỗi → dừng, không cài) → chép vào
`app.moi` → ghi PHIEN_BAN + TONG_KIEM.json → xoá `app.cu` cũ → `app`→`app.cu` → `app.moi`→`app`. Khoá được
giữ suốt quá trình (runner không thể bật giữa chừng) và luôn được nhả trong `finally`.
Ghi ngoài thư mục dự án → mỗi lần cài thật là NEEDS_APPROVAL (trưởng phòng chạy).
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

log = logging.getLogger("kho_runner.cai")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# R-05 P3-6: không chép công cụ dev/test vào bản cài. tao_khoa_ky.py chứa SEED_TEST (khoá ký thử);
# vector_ky.json là vector test (không phải *.py nên vốn không bị glob, vẫn liệt kê cho rõ).
LOAI_TIEN_TO = ("test_", "spike_")
LOAI_TEN = frozenset({"tao_khoa_ky.py", "vector_ky.json"})


def _git(nguon: Path, args: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", "--no-optional-locks", "-C", str(nguon), *args], capture_output=True,
                           timeout=30, creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)
    return r.returncode, (r.stdout if r.returncode == 0 else r.stderr).decode("utf-8", "replace").strip()


def phien_ban(nguon: Path) -> str:
    """`git rev-parse --short HEAD` + `-sua` nếu mã runner có thay đổi chưa commit. Không phải repo → 'khong-git'."""
    rc, ma = _git(nguon, ["rev-parse", "--short", "HEAD"])
    if rc != 0 or not ma:
        return "khong-git"
    rc, thay_doi = _git(nguon, ["status", "--porcelain", "--", "runner", "chay_runner.py"])
    if rc != 0:
        return ma + "-khong-ro"
    return ma + ("-sua" if thay_doi else "")


def _ds_chep(nguon: Path) -> list[tuple[Path, str]]:
    """(file nguồn, đường dẫn tương đối trong bản cài)."""
    runner = nguon / "runner"
    if not (nguon / "chay_runner.py").is_file() or not runner.is_dir():
        raise FileNotFoundError(f"{nguon} không có chay_runner.py và runner/")
    ds = [(nguon / "chay_runner.py", "chay_runner.py")]
    for f in sorted(runner.glob("*.py")):
        if f.name.startswith(LOAI_TIEN_TO) or f.name in LOAI_TEN:
            continue
        ds.append((f, f"runner/{f.name}"))
    pem = runner / "ky_cong_khai.pem"
    if pem.is_file():
        ds.append((pem, "ky_cong_khai.pem"))
    else:
        log.warning("chưa có %s — runner sẽ không mở HTTP cho tới khi có khoá công khai", pem)
    return ds


def _xoa_cay(p: Path) -> None:
    if p.exists():
        shutil.rmtree(p)


TEN_DB = "runner.db"
GIU_BAN_SAO = 5
_RE_BAN_SAO = re.compile(r"^runner\.db\.bak-\d{8}-\d{6}(?:-\d+)?$")


def ten_ban_sao(luc: datetime) -> str:
    """`runner.db.bak-YYYYmmdd-HHMMSS` — sắp theo tên = sắp theo thời gian. Logic thuần."""
    return f"{TEN_DB}.bak-{luc:%Y%m%d-%H%M%S}"


def ban_sao_can_xoa(ten: list[str], giu: int = GIU_BAN_SAO) -> list[str]:
    """Trong các tên file, chọn bản sao runner.db cũ cần xoá để còn `giu` bản mới nhất. Tên khác mẫu → bỏ qua.
    Logic thuần."""
    ds = sorted((t for t in ten if _RE_BAN_SAO.match(t)), key=_khoa_ban_sao)
    return ds[:max(len(ds) - max(giu, 1), 0)]           # luôn giữ ít nhất bản mới nhất


def _khoa_ban_sao(ten: str) -> tuple[str, int]:
    phan = ten.partition(".bak-")[2].split("-")
    return "-".join(phan[:2]), int(phan[2]) if len(phan) > 2 else 0


def sao_luu_db(du_lieu: Path, bay_gio: datetime | None = None, giu: int = GIU_BAN_SAO) -> Path | None:
    """P3-5 (R-15): sao lưu `du_lieu/runner.db` thành `runner.db.bak-<giờ>` bằng sqlite3 backup API (đọc qua WAL →
    một file tự đủ, nhất quán; không cần chép -wal/-shm). Ghi vào `.tmp` rồi đổi tên (không để bản dở dang lọt vào
    danh sách giữ). Giữ tối đa `giu` bản. Không có runner.db → None. Lỗi sao lưu → ném (bên gọi dừng cài).
    Bên gọi phải giữ khoá đơn instance (không ai ghi DB trong lúc sao)."""
    db = du_lieu / TEN_DB
    if not db.is_file():
        return None
    goc = ten_ban_sao(bay_gio or datetime.now())
    dich = du_lieu / goc
    n = 1
    while dich.exists():                                  # 2 lần cài trong cùng một giây
        dich = du_lieu / f"{goc}-{n}"
        n += 1
    tam = dich.with_name(dich.name + ".tmp")
    if tam.exists():
        tam.unlink()
    # mode=rw: không bao giờ tự tạo DB rỗng; đọc được cả DB đang ở chế độ WAL
    nguon = sqlite3.connect(f"file:{db.as_posix()}?mode=rw", uri=True, timeout=30)
    try:
        dong = sqlite3.connect(str(tam))
        try:
            nguon.backup(dong)
            ok = dong.execute("PRAGMA integrity_check").fetchone()
            if not ok or ok[0] != "ok":
                raise sqlite3.DatabaseError(f"bản sao {tam.name} không qua integrity_check: {ok!r}")
        finally:
            dong.close()
    except BaseException:
        if tam.exists():
            try:
                tam.unlink()
            except OSError as e:
                log.error("không xoá được bản sao dở %s: %s", tam, e)
        raise
    finally:
        nguon.close()
    tam.replace(dich)
    log.info("đã sao lưu %s → %s", db, dich.name)
    for ten in ban_sao_can_xoa([p.name for p in du_lieu.iterdir() if p.is_file()], giu):
        try:
            (du_lieu / ten).unlink()
        except OSError as e:                              # không chặn cài, nhưng không im lặng
            log.error("không xoá được bản sao cũ %s: %s", ten, e)
            print(f"[CẢNH BÁO] không xoá được bản sao cũ {ten}: {e}", file=sys.stderr)
    return dich


def cai(nguon: Path, dich: Path) -> str:
    """Cài từ `nguon` (thư mục tools/ của repo) vào `dich` (…\\kho-runner\\app). Trả PHIEN_BAN.
    SystemExit(4) nếu runner của thư mục dữ liệu `dich.parent` đang chạy."""
    from runner import thuc_thi as tt
    from runner.vong_lap import ten_mutex, tinh_tong_kiem
    nguon, dich = Path(nguon).resolve(), Path(dich).resolve()
    du_lieu = dich.parent
    khoa = tt.gianh_don_instance(du_lieu, ten_mutex(du_lieu))
    if khoa is None:
        print("Bộ chạy việc đang chạy — tắt runner rồi cài lại", file=sys.stderr)
        raise SystemExit(4)
    try:
        moi = du_lieu / (dich.name + ".moi")
        cu = du_lieu / (dich.name + ".cu")
        ds = _ds_chep(nguon)
        bak = sao_luu_db(du_lieu)                       # P3-5: lỗi sao lưu → ném, KHÔNG cài
        if bak is not None:
            print(f"Đã sao lưu runner.db → {bak}")
        _xoa_cay(moi)
        moi.mkdir(parents=True)
        for f, tuong_doi in ds:
            d = moi / tuong_doi
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, d)
        pb = phien_ban(nguon)
        (moi / "PHIEN_BAN").write_text(pb + "\n", encoding="utf-8")
        (moi / "runner" / "PHIEN_BAN").write_text(pb + "\n", encoding="utf-8")   # api.py đọc cạnh file của nó
        tong = tinh_tong_kiem(moi)
        (moi / "TONG_KIEM.json").write_text(json.dumps(tong, ensure_ascii=False, indent=1, sort_keys=True),
                                            encoding="utf-8")
        _xoa_cay(cu)
        if dich.exists():
            dich.rename(cu)
        try:
            moi.rename(dich)
        except OSError:
            if cu.exists() and not dich.exists():
                cu.rename(dich)                 # hoàn tác: trả bản cũ về chỗ
            raise
        return pb
    finally:
        try:
            khoa.nha()
        except OSError as e:
            log.error("lỗi nhả khoá đơn instance sau khi cài: %s", e)
            print(f"[LỖI] nhả khoá đơn instance: {e}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    from runner.vong_lap import thu_muc_runner
    ap = argparse.ArgumentParser(
        prog="cai_runner.py",
        description="Cài bộ chạy việc từ tools/ của repo ra thư mục cố định (mặc định KHO_RUNNER_DIR hoặc "
                    "E:\\kho-runner, thư mục con app; không dùng thư mục AppData vì app Claude dạng MSIX "
                    "chuyển hướng nó). Từ chối (mã 4) nếu runner đang chạy.")
    ap.add_argument("--nguon", type=Path, default=TOOLS, help="thư mục tools/ của repo (mặc định: cạnh file này)")
    ap.add_argument("--dich", type=Path, default=None, help="thư mục app đích (mặc định <thư mục runner>\\app)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    dich = a.dich or (thu_muc_runner() / "app")
    pb = cai(a.nguon, dich)
    print(f"Đã cài bộ chạy việc phiên bản {pb} vào {dich}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
