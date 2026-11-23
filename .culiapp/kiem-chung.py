"""Chạy mọi bước kiểm chứng của dự án. Exit 0 = tất cả qua. Đặt tại <dự án>/.culiapp/kiem-chung.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent

# Sửa danh sách này cho từng dự án. Để trống = tự dò.
LENH: list[list[str]] = [["node", "--test", "cf/test/worker.test.mjs", "cf/test/chu-ky-cheo.test.mjs", "cf/test/viec-web.test.mjs", "cf/test/sua-web.test.mjs", "cf/test/homnay-web.test.mjs", "cf/test/menu-web.test.mjs", "cf/test/poster-worker.test.mjs", "cf/test/poster-web.test.mjs", "cf/test/pv-tong-web.test.mjs", "cf/test/pv-tk-dang-web.test.mjs", "cf/test/pv-folders-web.test.mjs", "cf/test/pv-lich-queue-web.test.mjs", "cf/test/poster-noi-3-chang.test.mjs", "cf/test/hoc-worker.test.mjs", "cf/test/hoc-web.test.mjs", "cf/test/hoc-noi-day.test.mjs", "cf/test/radar-worker.test.mjs", "cf/test/radar-uid-web.test.mjs"], ["python", "-B", "-m", "pytest", "tools/test_kho.py", "tools/test_vtk.py", "tools/test_video_server.py", "tools/test_runner_kho_viec.py", "tools/test_runner_danh_muc.py", "tools/test_runner_phieu.py", "tools/test_runner_han_muc.py", "tools/test_runner_radar_xuat.py", "tools/test_runner_chu_ky.py", "tools/test_runner_thuc_thi.py", "tools/test_runner_stream_json.py", "tools/test_runner_api.py", "tools/test_runner_vong_lap.py", "tools/test_runner_chay.py", "tools/test_runner_sua_video.py", "tools/test_runner_theo_doi_phien.py", "tools/test_runner_phien_song.py", "tools/test_runner_bo_loai.py", "tools/test_poster_web.py", "tools/test_runner_hoc_kho.py", "tools/test_runner_quet_view.py", "tools/test_runner_hoc_tu_dong.py", "tools/test_runner_echotik.py", "tools/test_runner_radar_uid_tinh.py", "tools/test_runner_radar_uid_kho.py", "tools/test_runner_radar_uid_script.py", "tools/test_runner_radar_uid_api.py", "tools/test_runner_radar_uid_noi_day.py", "-q", "-p", "no:cacheprovider"], ["F:/auto video oneshot/.venv/Scripts/python.exe", "-B", "-m", "pytest", "tools/test_sua_video_engine.py", "-q", "-p", "no:cacheprovider"]]


def tu_do() -> list[list[str]]:
    co_pytest = any((GOC / f).exists() for f in ("pytest.ini", "tests", "conftest.py"))
    pyproject = GOC / "pyproject.toml"
    if pyproject.exists() and "[tool.pytest" in pyproject.read_text(encoding="utf-8", errors="ignore"):
        co_pytest = True
    if co_pytest:
        return [[sys.executable, "-B", "-m", "pytest", "-q"]]
    return [[sys.executable, "-m", "compileall", "-q",
             "-x", r"[\\/](venv|\.venv|node_modules|\.git)[\\/]", "."]]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    truot = 0
    for lenh in LENH or tu_do():
        print("$", " ".join(lenh), flush=True)
        try:
            r = subprocess.run(lenh, cwd=GOC, timeout=1800)
        except subprocess.TimeoutExpired:
            print("→ QUÁ GIỜ (30 phút)")
            truot += 1
            continue
        print("→ QUA" if r.returncode == 0 else f"→ TRƯỢT (exit {r.returncode})", flush=True)
        truot += r.returncode != 0
    print("KẾT QUẢ:", "QUA HẾT" if not truot else f"{truot} BƯỚC TRƯỢT")
    return 1 if truot else 0


if __name__ == "__main__":
    sys.exit(main())
