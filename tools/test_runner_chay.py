"""Test điểm vào runner + cài đặt (§4.1, D8, P1-1) — chạy:
PYTHONIOENCODING=utf-8 python -B -m pytest tools/test_runner_chay.py -q

- KHO_RUNNER_DIR, KHO_REPO trỏ vào tmp_path; mutex có tên riêng suy từ thư mục tạm (không đụng `Local\\kho-runner`).
- Runner chạy `--khong-http`; kho.py giả (ngủ) trong repo git tạm. Không gọi claude.exe/agy.exe.
- cai() chép vào tmp_path; không ghi E:\\kho-runner hay %LOCALAPPDATA%\\kho-runner.
"""
import json
import os
import sqlite3
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import psutil
import pytest

TOOLS = Path(__file__).parent
sys.path.insert(0, str(TOOLS))
import cai_runner  # noqa: E402
from runner import thuc_thi as tt  # noqa: E402
from runner import vong_lap as vl  # noqa: E402
from runner.kho_viec import KhoViec  # noqa: E402
from runner.kieu import MUI_GIO_VN  # noqa: E402

PY = sys.executable
CHAY_RUNNER = TOOLS / "chay_runner.py"


def env_runner(du_lieu: Path, repo: Path) -> dict:
    e = dict(os.environ)
    e.update({"KHO_RUNNER_DIR": str(du_lieu), "KHO_REPO": str(repo), "PYTHONIOENCODING": "utf-8",
              "PYTHONDONTWRITEBYTECODE": "1"})
    return e


def chup_db(db: Path) -> list:
    c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=10)
    try:
        return [list(map(tuple, c.execute(f"SELECT * FROM {b} ORDER BY 1"))) for b in ("viec", "su_kien", "tra_loi")]
    finally:
        c.close()


def giet_cay_test(p: subprocess.Popen) -> None:
    try:
        ds = psutil.Process(p.pid).children(recursive=True)
    except psutil.NoSuchProcess:
        ds = []
    p.kill()
    for c in ds:
        try:
            c.kill()
        except psutil.NoSuchProcess:
            pass
    p.wait(timeout=15)
    psutil.wait_procs(ds, timeout=15)


@pytest.fixture
def repo_git(tmp_path):
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    (repo / "tools" / "kho.py").write_text(textwrap.dedent("""
        import time
        print("đang chờ", flush=True)
        time.sleep(120)
    """), encoding="utf-8")
    r = subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return repo


def test_help_khong_can_khoa():
    r = subprocess.run([PY, "-B", str(CHAY_RUNNER), "--help"], capture_output=True, timeout=60,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    out = r.stdout.decode("utf-8")
    assert r.returncode == 0 and "--khong-http" in out
    assert "E:\\kho-runner" in out and "LOCALAPPDATA" not in out          # FX-7


def test_cai_runner_help_va_dich_mac_dinh(tmp_path, monkeypatch, capsys):
    """FX-7: --help nói E:\\kho-runner; đích mặc định = thu_muc_runner()/app (KHO_RUNNER_DIR → tmp_path)."""
    with pytest.raises(SystemExit) as e:
        cai_runner.main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "E:\\kho-runner" in out and "LOCALAPPDATA" not in out
    n = nguon_gia(tmp_path)
    monkeypatch.setenv("KHO_RUNNER_DIR", str(tmp_path / "du_lieu"))
    assert cai_runner.main(["--nguon", str(n)]) == 0
    assert (tmp_path / "du_lieu" / "app" / "chay_runner.py").is_file()
    assert "du_lieu" in capsys.readouterr().out


def test_p1_1_instance_thu_hai_khong_dung_viec_cua_instance_dau(tmp_path, repo_git):
    du_lieu = tmp_path / "du_lieu"
    kho = KhoViec(du_lieu / "runner.db", lambda: __import__("datetime").datetime.now(MUI_GIO_VN))
    v = kho.tao("xu_ly_link_moi", "kho", {}, "nhe", "cho", "nhan")
    del kho
    env = env_runner(du_lieu, repo_git)
    a = subprocess.Popen([PY, "-B", str(CHAY_RUNNER), "--khong-http"], env=env, cwd=str(tmp_path),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        db = du_lieu / "runner.db"
        han = time.monotonic() + 60
        pid = None
        while time.monotonic() < han:
            assert a.poll() is None, a.stdout.read().decode("utf-8", "replace")
            if db.exists():
                dong = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=10).execute(
                    "SELECT trang_thai, pid FROM viec WHERE id=?", (v["id"],)).fetchone()
                if dong and dong[0] == "dang_chay" and dong[1]:
                    pid = dong[1]
                    break
            time.sleep(0.2)
        assert pid, "instance A không nhận việc"
        time.sleep(1.0)                                   # để A ghi xong mọi thứ của lần nhận
        truoc = chup_db(db)
        assert psutil.pid_exists(pid)

        b = subprocess.run([PY, "-B", str(CHAY_RUNNER), "--khong-http"], env=env, cwd=str(tmp_path),
                           capture_output=True, timeout=60)
        assert b.returncode == 3, b.stdout + b.stderr
        assert "Bộ chạy việc đã chạy" in b.stdout.decode("utf-8")
        assert psutil.pid_exists(pid) and psutil.Process(pid).is_running()   # việc của A vẫn sống
        assert chup_db(db) == truoc                                          # B không đổi DB
        assert a.poll() is None
    finally:
        giet_cay_test(a)
    # A chết → Job Object giết luôn kho.py giả
    han = time.monotonic() + 15
    while time.monotonic() < han and psutil.pid_exists(pid):
        time.sleep(0.2)
    assert not psutil.pid_exists(pid)


def test_p1_1_lock_file_la_luoi_thu_hai(tmp_path):
    """Giữ runner.lock (mutex khác tên) → runner vẫn thoát 3, không tạo DB."""
    du_lieu = tmp_path / "du_lieu"
    giu = subprocess.Popen([PY, "-c", textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(TOOLS)!r})
        from runner import thuc_thi as tt
        k = tt.gianh_don_instance(__import__('pathlib').Path({str(du_lieu)!r}), 'Local\\\\kho-runner-test-khac')
        print('giu' if k else 'khong', flush=True)
        time.sleep(60)
    """)], stdout=subprocess.PIPE)
    try:
        assert giu.stdout.readline().strip() == b"giu"
        r = subprocess.run([PY, "-B", str(CHAY_RUNNER), "--khong-http"], env=env_runner(du_lieu, tmp_path),
                           capture_output=True, timeout=60)
        assert r.returncode == 3
        assert not (du_lieu / "runner.db").exists()
    finally:
        giet_cay_test(giu)


def ban_sao_khong_pem(tmp_path: Path) -> Path:
    """Bản sao chay_runner.py + runner/*.py (KHÔNG có ky_cong_khai.pem) để test không phụ thuộc repo có pem hay không."""
    import shutil
    app = tmp_path / "app_sao"
    (app / "runner").mkdir(parents=True)
    shutil.copy2(TOOLS / "chay_runner.py", app / "chay_runner.py")
    for f in (TOOLS / "runner").glob("*.py"):
        shutil.copy2(f, app / "runner" / f.name)
    return app


def test_thieu_pem_thoat_6_truoc_khi_dung_db(tmp_path):
    """R-05 P3-8: thiếu ky_cong_khai.pem → mã 6 TRƯỚC khoi_dong (không mở DB, không đối soát việc nào)."""
    app = ban_sao_khong_pem(tmp_path)
    du_lieu = tmp_path / "du_lieu"
    r = subprocess.run([PY, "-B", str(app / "chay_runner.py"), "--cong", "1"],
                       env=env_runner(du_lieu, tmp_path / "repo_khong_co"), cwd=str(tmp_path),
                       capture_output=True, timeout=60)
    assert r.returncode == 6, r.stdout + r.stderr
    assert "ky_cong_khai.pem" in r.stderr.decode("utf-8", "replace")
    assert not (du_lieu / "runner.db").exists()
    k = tt.gianh_don_instance(du_lieu, vl.ten_mutex(du_lieu))          # đã nhả khoá đơn instance
    assert k is not None
    k.nha()


def test_pem_hong_thoat_6_truoc_khi_dung_db(tmp_path):
    """R-06 P3-4: ky_cong_khai.pem có mà hỏng → mã 6 (không traceback mã 1), chưa mở DB, đã nhả khoá."""
    app = ban_sao_khong_pem(tmp_path)
    (app / "runner" / "ky_cong_khai.pem").write_bytes(b"-----BEGIN PUBLIC KEY-----\nkhong-phai-base64\n")
    du_lieu = tmp_path / "du_lieu"
    r = subprocess.run([PY, "-B", str(app / "chay_runner.py"), "--cong", "1"],
                       env=env_runner(du_lieu, tmp_path / "repo_khong_co"), cwd=str(tmp_path),
                       capture_output=True, timeout=60)
    err = r.stderr.decode("utf-8", "replace")
    assert r.returncode == 6, r.stdout + r.stderr
    assert "ky_cong_khai.pem hỏng" in err and "Traceback" not in err
    assert not (du_lieu / "runner.db").exists()
    k = tt.gianh_don_instance(du_lieu, vl.ten_mutex(du_lieu))
    assert k is not None
    k.nha()


def test_khong_gan_duoc_job_object_dua_canh_bao_ra_suc_khoe(tmp_path, monkeypatch):
    """R-05 P2-3: gắn Job Object thất bại → cảnh báo nằm trong `canh_bao` mà api.tao_handler nhận (/suc-khoe)."""
    import chay_runner
    from runner import api
    du_lieu = tmp_path / "du_lieu"
    monkeypatch.setenv("KHO_RUNNER_DIR", str(du_lieu))
    for k in ("KHO_REPO", "KHO_THU_MUC_RADAR", "KHO_THU_MUC_SP", "KHO_THU_MUC_SCRIPTS"):
        monkeypatch.setenv(k, str(tmp_path / k.lower()))
    monkeypatch.setattr(tt, "tu_gan_job_object", lambda: False)        # KHÔNG gắn pytest vào Job Object thật
    monkeypatch.setattr(chay_runner, "_cai_log", lambda thu_muc: None)
    monkeypatch.setattr(chay_runner, "_khoa_cong_khai", lambda: (object(), tmp_path / "gia.pem"))
    bat = {}

    def tao_handler(kho, mt, khoa, kcc, hm, canh_bao, *a, **kw):
        bat["canh_bao"] = canh_bao
        bat["che"] = kw.get("che")
        raise KeyboardInterrupt                                         # thoát main() trước khi bind/bật làn
    monkeypatch.setattr(api, "tao_handler", tao_handler)
    assert chay_runner.main(["--cong", "1"]) == 0
    assert any("Job Object" in c for c in bat["canh_bao"]), bat
    assert callable(bat["che"])                                         # R-06 P3-3: api nhận bộ che
    k = tt.gianh_don_instance(du_lieu, vl.ten_mutex(du_lieu))
    assert k is not None
    k.nha()


def test_khoa_runner_hong_thoat_6_truoc_khi_doi_viec(tmp_path, monkeypatch, caplog):
    """R-07 P3-7: .runner_key có mà quá ngắn → mã 6 + log, TRƯỚC khoi_dong (chưa mở DB, chưa đổi việc nào),
    không tự ghi đè file khoá, đã nhả khoá đơn instance."""
    import chay_runner
    du_lieu = tmp_path / "du_lieu"
    du_lieu.mkdir()
    (du_lieu / ".runner_key").write_text("ngan", encoding="utf-8")
    monkeypatch.setenv("KHO_RUNNER_DIR", str(du_lieu))
    for k in ("KHO_REPO", "KHO_THU_MUC_RADAR", "KHO_THU_MUC_SP", "KHO_THU_MUC_SCRIPTS"):
        monkeypatch.setenv(k, str(tmp_path / k.lower()))
    monkeypatch.setattr(tt, "tu_gan_job_object", lambda: False)
    monkeypatch.setattr(chay_runner, "_cai_log", lambda thu_muc: None)
    monkeypatch.setattr(chay_runner, "_khoa_cong_khai", lambda: (object(), tmp_path / "gia.pem"))
    goi_khoi_dong = []
    monkeypatch.setattr(vl.BoChay, "khoi_dong", lambda self: goi_khoi_dong.append(1) or {})
    with caplog.at_level("ERROR", logger="kho_runner"):
        assert chay_runner.main(["--cong", "1"]) == 6
    assert goi_khoi_dong == [] and not (du_lieu / "runner.db").exists()
    assert (du_lieu / ".runner_key").read_text(encoding="utf-8") == "ngan"
    assert any(".runner_key" in r.getMessage() for r in caplog.records), caplog.records
    k = tt.gianh_don_instance(du_lieu, vl.ten_mutex(du_lieu))
    assert k is not None
    k.nha()


def test_doc_khoa_runner_ngan_nem_khong_kem_ngu_canh_except(tmp_path):
    """B904: lỗi khoá ngắn ném `from None` (không dính FileExistsError vào __context__ hiển thị)."""
    import chay_runner
    (tmp_path / ".runner_key").write_text("ngan", encoding="utf-8")
    with pytest.raises(RuntimeError) as e:
        chay_runner.doc_hoac_tao_khoa_runner(tmp_path)
    assert e.value.__suppress_context__ is True and e.value.__cause__ is None


# ---------------- cai_runner ----------------

def nguon_gia(tmp_path: Path) -> Path:
    n = tmp_path / "nguon"
    (n / "runner").mkdir(parents=True)
    (n / "chay_runner.py").write_text("# điểm vào\n", encoding="utf-8")
    for ten in ("__init__.py", "vong_lap.py", "test_x.py", "spike_claude.py", "tao_khoa_ky.py"):
        (n / "runner" / ten).write_text(f"# {ten}\n", encoding="utf-8")
    (n / "runner" / "ky_cong_khai.pem").write_text("-----BEGIN PUBLIC KEY-----\n", encoding="utf-8")
    (n / "runner" / "vector_ky.json").write_text("{}", encoding="utf-8")
    return n


def test_cai_chep_dung_bo_cuc_va_ghi_tong_kiem(tmp_path):
    n = nguon_gia(tmp_path)
    dich = tmp_path / "kho-runner" / "app"
    pb = cai_runner.cai(n, dich)
    assert pb == "khong-git"
    ten = sorted(p.relative_to(dich).as_posix() for p in dich.rglob("*") if p.is_file())
    assert ten == ["PHIEN_BAN", "TONG_KIEM.json", "chay_runner.py", "ky_cong_khai.pem", "runner/PHIEN_BAN",
                   "runner/__init__.py", "runner/vong_lap.py"]
    tong = json.loads((dich / "TONG_KIEM.json").read_text(encoding="utf-8"))
    assert set(tong) == set(ten) - {"TONG_KIEM.json"}
    assert vl.kiem_tong(dich) == []
    # cài lần 2: bản cũ thành app.cu, app.moi không còn
    (n / "runner" / "vong_lap.py").write_text("# bản mới\n", encoding="utf-8")
    cai_runner.cai(n, dich)
    assert (dich / "runner" / "vong_lap.py").read_text(encoding="utf-8") == "# bản mới\n"
    assert (dich.parent / "app.cu" / "runner" / "vong_lap.py").read_text(encoding="utf-8") == "# vong_lap.py\n"
    assert not (dich.parent / "app.moi").exists()
    # khoá đã được nhả: giành lại được
    k = tt.gianh_don_instance(dich.parent, vl.ten_mutex(dich.parent))
    assert k is not None
    k.nha()


def test_cai_tu_choi_khi_runner_dang_chay(tmp_path):
    n = nguon_gia(tmp_path)
    dich = tmp_path / "kho-runner" / "app"
    du_lieu = dich.parent
    giu = subprocess.Popen([PY, "-c", textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(TOOLS)!r})
        from pathlib import Path
        from runner import thuc_thi as tt
        from runner.vong_lap import ten_mutex
        d = Path({str(du_lieu)!r})
        k = tt.gianh_don_instance(d, ten_mutex(d))
        print('giu' if k else 'khong', flush=True)
        time.sleep(60)
    """)], stdout=subprocess.PIPE)
    try:
        assert giu.stdout.readline().strip() == b"giu"
        with pytest.raises(SystemExit) as e:
            cai_runner.cai(n, dich)
        assert e.value.code == 4
        assert not dich.exists() and not (du_lieu / "app.moi").exists()
    finally:
        giet_cay_test(giu)


def test_cai_ban_cai_chay_duoc_help(tmp_path):
    """Bản cài thật từ tools/ của repo: import đúng bố cục app/runner, `--help` chạy."""
    dich = tmp_path / "kho-runner" / "app"
    nguon = tmp_path / "tools_sao"
    (nguon / "runner").mkdir(parents=True)
    import shutil
    shutil.copy2(TOOLS / "chay_runner.py", nguon / "chay_runner.py")
    for f in (TOOLS / "runner").glob("*.py"):
        shutil.copy2(f, nguon / "runner" / f.name)
    shutil.copy2(TOOLS / "runner" / "vector_ky.json", nguon / "runner" / "vector_ky.json")
    cai_runner.cai(nguon, dich)
    assert not list((dich / "runner").glob("spike_*"))
    # R-05 P3-6: công cụ sinh khoá (có SEED_TEST) và vector test không được vào bản cài
    assert not (dich / "runner" / "tao_khoa_ky.py").exists()
    assert not list(dich.rglob("vector_ky.json")) and not list(dich.rglob("test_*"))
    assert all(b"SEED_TEST" not in f.read_bytes() for f in dich.rglob("*") if f.is_file())
    r = subprocess.run([PY, "-B", str(dich / "chay_runner.py"), "--help"], capture_output=True, timeout=60,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert r.returncode == 0, r.stderr
    r = subprocess.run([PY, "-B", "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
                        "import runner.vong_lap, runner.api, runner.danh_muc; print('ok')", str(dich)],
                       capture_output=True, timeout=60)
    assert r.stdout.strip() == b"ok", r.stderr
