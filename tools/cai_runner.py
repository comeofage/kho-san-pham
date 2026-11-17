"""Cài bộ chạy việc ra thư mục cố định ngoài repo (D8, docs/bo-chay-viec.md §4.1).

    python tools/cai_runner.py                 # cài vào E:\\kho-runner\\app (hoặc KHO_RUNNER_DIR\\app)
    python tools/cai_runner.py --dich <thư mục app>

Bố cục bản cài (giữ đúng cấu trúc import của repo):
    app\\chay_runner.py
    app\\runner\\*.py           (trừ test_*, spike_*, tao_khoa_ky.py)
    app\\ky_cong_khai.pem       (nếu repo có tools/runner/ky_cong_khai.pem)
    app\\PHIEN_BAN, app\\runner\\PHIEN_BAN
    app\\TONG_KIEM.json         (sha256 từng file, runner so lúc khởi động)

Các bước: giành khoá đơn instance của thư mục dữ liệu (giành không được = runner đang chạy → mã 4) → chép vào
`app.moi` → ghi PHIEN_BAN + TONG_KIEM.json → xoá `app.cu` cũ → `app`→`app.cu` → `app.moi`→`app`. Khoá được
giữ suốt quá trình (runner không thể bật giữa chừng) và luôn được nhả trong `finally`.
Ghi ngoài thư mục dự án → mỗi lần cài thật là NEEDS_APPROVAL (trưởng phòng chạy).
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
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
