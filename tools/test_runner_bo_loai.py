"""Test bo_loai.py — việc miễn phí poster_bo_loai (docs/giao-dien-menu-trai.md §4.9).

Chạy: PYTHONIOENCODING=utf-8 python -B -m pytest tools/test_runner_bo_loai.py -q -p no:cacheprovider

Mọi thư mục là fixture trong tmp_path: không đụng thư mục dự án thật, không đụng repo kho thật.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from runner import bo_loai as bl  # noqa: E402

UID = "1729420930611055346"
UID2 = "1729482409825635197"
T0 = 1_763_000_000          # mtime cố định (giây nguyên) để sua_luc dễ đoán


def _video(p: Path, ts: int = T0, noi: bytes = b"mp4") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(noi)
    os.utime(p, (ts, ts))
    return p


@pytest.fixture
def kho(tmp_path):
    """goc/<SP UID>/{output_poster, output, output-adam, output_daonguoc, compose_output} + repo/data/<UID>."""
    goc = tmp_path / "goc"
    du_an = goc / f"Bình nước {UID}"
    op, out = du_an / "output_poster", du_an / "output"
    for ten in ("a.mp4", "b.mp4", "c.mp4"):
        _video(op / ten)
    _video(out / "x.mp4")
    _video(out / "y.mp4")
    (op / "ghi_chu.txt").write_text("không phải video", encoding="utf-8")
    # bản gốc hardlink + thư mục creator: KHÔNG bao giờ bị đụng
    for thu in ("output-adam", "output_daonguoc", "compose_output"):
        _video(du_an / thu / "a.mp4")
    # dự án UID khác và thư mục 20 chữ số (không phải UID này)
    _video(goc / f"SP {UID2}" / "output_poster" / "a.mp4")
    _video(goc / f"Lạ 9{UID}" / "output_poster" / "a.mp4")
    repo = tmp_path / "repo"
    (repo / "data" / UID).mkdir(parents=True)
    (repo / "data" / UID2).mkdir(parents=True)

    class K:
        pass
    k = K()
    k.goc, k.du_an, k.op, k.out, k.repo = goc, du_an, op, out, repo
    k.goc_op = goc.as_posix()                                  # khoá goc của output_poster (video_server.py:118)
    k.goc_out = f"{goc.as_posix()}#{du_an.name}/output"        # khoá goc của output
    return k


def _duyet(k, *muc, uid=UID) -> None:
    ds = [{"goc": g, "ten": t, "sua_luc": s, "mb": 0.1, "ket_qua": kq, "gop_y": "", "boi": "Nhân",
           "luc": "2026-11-18T09:00:00+07:00"} for g, t, s, kq in muc]
    (k.repo / "data" / uid / "duyet.json").write_text(json.dumps({"videos": ds}, ensure_ascii=False),
                                                     encoding="utf-8")


def _chay(k, *them: str) -> int:
    return bl.main(["--repo-kho", str(k.repo), "--uid", UID, "--goc", str(k.goc), *them])


def _ten(thu: Path) -> list[str]:
    return sorted(f.name for f in thu.iterdir() if f.is_file()) if thu.is_dir() else []


# ---------- đọc duyet.json ----------

def test_doc_ket_qua_muc_sau_thang(kho):
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"), (kho.goc_op, "a.mp4", T0, "dat"),
           (kho.goc_op, "b.mp4", T0, "dat"), (kho.goc_op, "b.mp4", T0, "loai"))
    kq = bl.doc_ket_qua_duyet(kho.repo, UID)
    g = bl.chuan_khoa_goc(kho.goc_op)                      # khoá goc đã chuẩn hoá (P2-1)
    assert kq[(g, "a.mp4", T0)] == "dat"
    assert kq[(g, "b.mp4", T0)] == "loai"


def test_doc_ket_qua_chua_co_file_la_none(kho):
    """[P2-1] Thiếu duyet.json ≠ "không có Loại nào": trả None để bên gọi không trả hàng loạt từ _loai/ về."""
    assert bl.doc_ket_qua_duyet(kho.repo, UID) is None


def test_thieu_duyet_json_khong_tra_gi_tu_loai(kho, capsys):
    """[P2-1] _loai/ có file mà chưa có duyet.json (vd đọc nhầm bản kho cũ) → không dời chiều nào."""
    _video(kho.op / "_loai" / "z.mp4")
    _video(kho.out / "_loai" / "w.mp4")
    assert bl.lap_ke_hoach(kho.repo, UID, [kho.goc]) == []
    assert _chay(kho) == 0
    assert _ten(kho.op / "_loai") == ["z.mp4"] and _ten(kho.out / "_loai") == ["w.mp4"]
    assert capsys.readouterr().out.splitlines()[-1] == "TONG: bo=0 tra=0 bo_qua=0"


def _doi_hoa(s: str) -> str:
    return s.swapcase().replace("/", "\\")


def test_goc_khac_hoa_thuong_va_gach_van_khop(kho):
    """[P2-1] KHO_VIDEO_GOC của video_server (E:/…) và --goc của runner (e:\\…) khác chữ hoa/gạch vẫn là một gốc:
    Loại vẫn bị dời, video trong _loai/ còn Loại KHÔNG bị trả về."""
    _video(kho.op / "_loai" / "z.mp4")
    _duyet(kho, (_doi_hoa(kho.goc_op), "a.mp4", T0, "loai"), (kho.goc_op.upper(), "z.mp4", T0, "loai"),
           (_doi_hoa(kho.goc_out), "x.mp4", T0, "loai"))
    assert bl.loai_trong_folder(str(kho.op), kho.repo, [Path(str(kho.goc).swapcase())]) == ["a.mp4"]
    assert bl.loai_trong_folder(str(kho.out), kho.repo, [kho.goc]) == ["x.mp4"]
    assert _chay(kho) == 0
    assert _ten(kho.op / "_loai") == ["a.mp4", "z.mp4"] and _ten(kho.out / "_loai") == ["x.mp4"]
    assert bl.loai_trong_folder(str(kho.op), kho.repo, [Path(str(kho.goc).swapcase())]) == []


def test_chuan_khoa_goc():
    assert bl.chuan_khoa_goc("E:/A/b#Dự Án/output") == bl.chuan_khoa_goc("e:\\a\\B#dự án/OUTPUT")
    assert bl.chuan_khoa_goc("E:/a") != bl.chuan_khoa_goc("E:/a2")


@pytest.mark.parametrize("noi", [
    "{không phải json", "[]", '{"videos": {}}', '{"videos": ["x"]}',
    '{"videos": [{"goc": "g", "ten": "a.mp4", "sua_luc": "1", "ket_qua": "loai"}]}',
    '{"videos": [{"goc": "g", "ten": "a.mp4", "sua_luc": true, "ket_qua": "loai"}]}',
    '{"videos": [{"goc": "g", "ten": "a.mp4", "sua_luc": 1, "ket_qua": "LOAI"}]}',
    '{"videos": [{"goc": 1, "ten": "a.mp4", "sua_luc": 1, "ket_qua": "loai"}]}',
    '{"videos": [{"goc": "g", "ten": "../a.mp4", "sua_luc": 1, "ket_qua": "loai"}]}',
])
def test_doc_ket_qua_hong_la_loi_du_lieu(kho, noi):
    f = kho.repo / "data" / UID / "duyet.json"
    f.write_text(noi, encoding="utf-8")
    with pytest.raises(bl.LoiDuLieu):
        bl.doc_ket_qua_duyet(kho.repo, UID)
    assert f.read_text(encoding="utf-8") == noi          # không đổi tên / không ghi đè file trạng thái hỏng


def test_uid_sai_la_loi_du_lieu(kho):
    for sai in ("123", "../" + UID, UID + "\n", "１" * 19):
        with pytest.raises(bl.LoiDuLieu):
            bl.doc_ket_qua_duyet(kho.repo, sai)


# ---------- chiều 1: Loại → _loai/ ----------

def test_doi_video_loai_sang_loai_giu_mtime(kho, capsys):
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"), (kho.goc_op, "b.mp4", T0, "dat"),
           (kho.goc_out, "x.mp4", T0, "loai"))
    assert _chay(kho) == 0
    assert _ten(kho.op) == ["b.mp4", "c.mp4", "ghi_chu.txt"]
    assert _ten(kho.op / "_loai") == ["a.mp4"]
    assert _ten(kho.out) == ["y.mp4"] and _ten(kho.out / "_loai") == ["x.mp4"]
    for f in (kho.op / "_loai" / "a.mp4", kho.out / "_loai" / "x.mp4"):
        assert int(f.stat().st_mtime) == T0              # giữ mtime → sua_luc vẫn khớp khoá duyệt
    ra = capsys.readouterr().out.splitlines()
    assert any(d.startswith("DOI: a.mp4 -> _loai") for d in ra)
    assert any(d.startswith("DOI: x.mp4 -> _loai") for d in ra)
    assert ra[-1] == "TONG: bo=2 tra=0 bo_qua=0"


def test_sua_luc_lech_thi_khong_doi(kho):
    _duyet(kho, (kho.goc_op, "a.mp4", T0 - 1, "loai"), (kho.goc_op, "b.mp4", T0, "loai"))
    _video(kho.op / "b.mp4", T0 + 5)                     # video đã dựng lại sau khi chấm → khoá không còn khớp
    assert _chay(kho) == 0
    assert _ten(kho.op) == ["a.mp4", "b.mp4", "c.mp4", "ghi_chu.txt"]
    assert not (kho.op / "_loai").exists()


def test_goc_sai_thu_muc_thi_khong_doi(kho):
    """Khoá goc của output_poster và output khác nhau: chấm Loại ở nguồn này không dời file nguồn kia."""
    _duyet(kho, (kho.goc_out, "a.mp4", T0, "loai"), (kho.goc_op, "x.mp4", T0, "loai"))
    assert _chay(kho) == 0
    assert _ten(kho.op / "_loai") == [] and _ten(kho.out / "_loai") == []


def test_khong_dung_ban_goc_va_du_an_khac(kho):
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"))
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"), uid=UID2)
    assert _chay(kho) == 0
    for thu in ("output-adam", "output_daonguoc", "compose_output"):
        assert _ten(kho.du_an / thu) == ["a.mp4"] and not (kho.du_an / thu / "_loai").exists()
    assert _ten(kho.goc / f"SP {UID2}" / "output_poster") == ["a.mp4"]
    assert _ten(kho.goc / f"Lạ 9{UID}" / "output_poster") == ["a.mp4"]


def test_hardlink_ban_goc_con_nguyen(kho):
    goc_adam = kho.du_an / "output-adam" / "h.mp4"
    _video(goc_adam)
    os.link(goc_adam, kho.op / "h.mp4")
    os.utime(goc_adam, (T0, T0))
    _duyet(kho, (kho.goc_op, "h.mp4", T0, "loai"))
    assert _chay(kho) == 0
    assert goc_adam.is_file() and (kho.op / "_loai" / "h.mp4").is_file()


def test_idempotent(kho, capsys):
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"))
    assert _chay(kho) == 0
    capsys.readouterr()
    assert _chay(kho) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "TONG: bo=0 tra=0 bo_qua=0"
    assert _ten(kho.op / "_loai") == ["a.mp4"]


# ---------- chiều 2: hết Loại → trả về ----------

def test_cham_lai_dat_hoac_bo_duyet_thi_tra_ve(kho, capsys):
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"), (kho.goc_op, "b.mp4", T0, "loai"),
           (kho.goc_op, "c.mp4", T0, "loai"))
    assert _chay(kho) == 0
    assert _ten(kho.op / "_loai") == ["a.mp4", "b.mp4", "c.mp4"]
    # a: chấm lại Đạt (mục sau thắng); b: Bỏ chấm còn góp ý (mục ket_qua ""); c: vẫn Loại
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"), (kho.goc_op, "a.mp4", T0, "dat"),
           (kho.goc_op, "b.mp4", T0, ""), (kho.goc_op, "c.mp4", T0, "loai"))
    capsys.readouterr()
    assert _chay(kho) == 0
    assert _ten(kho.op) == ["a.mp4", "b.mp4", "ghi_chu.txt"]
    assert _ten(kho.op / "_loai") == ["c.mp4"]
    assert int((kho.op / "a.mp4").stat().st_mtime) == T0
    ra = capsys.readouterr().out.splitlines()
    assert any(d.startswith("TRA: a.mp4") for d in ra) and any(d.startswith("TRA: b.mp4") for d in ra)
    assert ra[-1] == "TONG: bo=0 tra=2 bo_qua=0"


def test_tra_chi_khi_co_muc_cham_khop(kho, capsys):
    """[FX-B3 P2-2] Chiều trả fail-closed: chỉ trả khi có mục chấm khớp đúng (goc, ten, sua_luc) và mục cuối khác
    "loai". Không có mục (bị xoá, mtime lệch, GOC đổi) → BO_QUA, mã 5, video ở lại _loai/."""
    _video(kho.op / "_loai" / "dat.mp4")
    _video(kho.op / "_loai" / "rong.mp4")
    _video(kho.op / "_loai" / "lech.mp4", T0 + 7)                  # mtime đổi sau khi chấm
    _video(kho.op / "_loai" / "khong_muc.mp4")
    _video(kho.op / "_loai" / "goc_khac.mp4")
    _duyet(kho, (kho.goc_op, "dat.mp4", T0, "dat"), (kho.goc_op, "rong.mp4", T0, ""),
           (kho.goc_op, "lech.mp4", T0, "dat"), ("E:/goc_moi", "goc_khac.mp4", T0, "dat"))
    assert _chay(kho) == 5
    assert _ten(kho.op / "_loai") == ["goc_khac.mp4", "khong_muc.mp4", "lech.mp4"]
    ra = capsys.readouterr().out.splitlines()
    for t in ("lech.mp4", "khong_muc.mp4", "goc_khac.mp4"):
        assert any(d.startswith(f"BO_QUA: {t} (không có mục chấm khớp") for d in ra), t
    assert ra[-1] == "TONG: bo=0 tra=2 bo_qua=3"
    # đếm Loại cho poster_len_lich không đổi: video trong _loai/ không tính
    assert bl.loai_trong_folder(str(kho.op), kho.repo, [kho.goc]) == []


def test_xem_khong_doi_gi(kho, capsys):
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"))
    _video(kho.op / "_loai" / "z.mp4")
    _video(kho.op / "_loai" / "y.mp4")
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"), (kho.goc_op, "y.mp4", T0, "dat"))
    assert _chay(kho, "--xem") == 5                                  # z không có mục → BO_QUA
    assert _ten(kho.op) == ["a.mp4", "b.mp4", "c.mp4", "ghi_chu.txt"]
    assert _ten(kho.op / "_loai") == ["y.mp4", "z.mp4"]
    ra = capsys.readouterr().out
    assert "XEM DOI: a.mp4" in ra and "XEM TRA: y.mp4" in ra and "BO_QUA: z.mp4" in ra
    assert "TONG: bo=1 tra=1 bo_qua=1" in ra


def test_trung_ten_o_dich_bo_qua_ma_5(kho, capsys):
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"))
    _video(kho.op / "_loai" / "a.mp4", T0, b"ban khac")
    assert _chay(kho) == 5
    assert (kho.op / "a.mp4").read_bytes() == b"mp4"          # không ghi đè
    assert (kho.op / "_loai" / "a.mp4").read_bytes() == b"ban khac"
    assert capsys.readouterr().out.splitlines()[-1] == "TONG: bo=0 tra=0 bo_qua=1"


# ---------- file bị khoá (Windows: đang phát / đang tải) ----------

def test_file_bi_khoa_gia_bo_qua_ma_5_va_lam_tiep(kho, monkeypatch, capsys):
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"), (kho.goc_op, "b.mp4", T0, "loai"))
    that = bl._thay_file
    lan = []

    def thay(src: Path, dst: Path) -> None:
        lan.append(src.name)
        if src.name == "a.mp4":
            raise PermissionError(13, "file đang mở", str(src))
        that(src, dst)
    monkeypatch.setattr(bl, "_thay_file", thay)
    monkeypatch.setattr(bl, "_ngu", lambda _s: None)
    assert _chay(kho) == 5
    assert (kho.op / "a.mp4").is_file() and _ten(kho.op / "_loai") == ["b.mp4"]
    assert lan.count("a.mp4") == bl.SO_LAN_THU                # có thử lại (NTFS khoá tạm) rồi mới bỏ qua
    ra = capsys.readouterr().out.splitlines()
    assert any(d.startswith("BO_QUA: a.mp4") for d in ra)
    assert ra[-1] == "TONG: bo=1 tra=0 bo_qua=1"


def test_loi_khac_permissionerror_khong_bi_nuot(kho, monkeypatch):
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"))

    def thay(_src: Path, _dst: Path) -> None:
        raise OSError(28, "hết chỗ")
    monkeypatch.setattr(bl, "_thay_file", thay)
    with pytest.raises(OSError, match="hết chỗ"):
        _chay(kho)


@pytest.mark.skipif(os.name != "nt", reason="khoá file khi đang mở chỉ có trên Windows")
def test_file_dang_mo_that_tren_windows(kho, monkeypatch):
    monkeypatch.setattr(bl, "_ngu", lambda _s: None)
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"))
    with open(kho.op / "a.mp4", "rb"):
        assert _chay(kho) == 5
    assert (kho.op / "a.mp4").is_file()
    assert _chay(kho) == 0                                    # đóng file rồi chạy lại thì dời được
    assert _ten(kho.op / "_loai") == ["a.mp4"]


# ---------- lỗi dữ liệu → mã 2, không dời gì ----------

def test_duyet_hong_ma_2_khong_doi(kho, capsys):
    _video(kho.op / "_loai" / "z.mp4")
    (kho.repo / "data" / UID / "duyet.json").write_text("{hỏng", encoding="utf-8")
    assert _chay(kho) == 2
    assert _ten(kho.op / "_loai") == ["z.mp4"]                # không “trả về” hàng loạt vì đọc hỏng thành rỗng
    assert "[LỖI]" in capsys.readouterr().err


def test_repo_sai_ma_2(kho, tmp_path):
    _video(kho.op / "_loai" / "z.mp4")
    assert bl.main(["--repo-kho", str(tmp_path / "khong_co"), "--uid", UID, "--goc", str(kho.goc)]) == 2
    assert _ten(kho.op / "_loai") == ["z.mp4"]


def test_uid_sai_ma_2(kho):
    assert bl.main(["--repo-kho", str(kho.repo), "--uid", "../x", "--goc", str(kho.goc)]) == 2


# ---------- đếm Loại theo đường dẫn folder Poster (dùng cho _dk_poster_len_lich) ----------

def test_loai_trong_folder(kho):
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"), (kho.goc_op, "b.mp4", T0, "dat"),
           (kho.goc_out, "x.mp4", T0, "loai"))
    assert bl.loai_trong_folder(str(kho.op), kho.repo, [kho.goc]) == ["a.mp4"]
    assert bl.loai_trong_folder(str(kho.op).replace("/", "\\"), kho.repo, [kho.goc]) == ["a.mp4"]
    assert bl.loai_trong_folder(kho.out.as_posix(), kho.repo, [kho.goc]) == ["x.mp4"]
    # không phải thư mục đăng của dự án kho → None (không biết, không chặn)
    for p in (kho.du_an / "compose_output", kho.du_an, kho.goc / "x" / "output_poster",
              kho.goc / f"Lạ 9{UID}" / "output_poster"):
        assert bl.loai_trong_folder(str(p), kho.repo, [kho.goc]) is None, p
    assert bl.loai_trong_folder(str(kho.op), kho.repo, [kho.goc.parent / "goc_khac"]) is None
    _ = _chay(kho)
    assert bl.loai_trong_folder(str(kho.op), kho.repo, [kho.goc]) == []


def test_log_khong_in_duong_dan_o_dia(kho, capsys):
    """[P3] Dòng DOI/TRA/BO_QUA chỉ có tên file (+ tên thư mục đăng), không lộ đường dẫn ổ đĩa."""
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"), (kho.goc_op, "b.mp4", T0, "loai"),
           (kho.goc_op, "z.mp4", T0, "dat"))
    _video(kho.op / "_loai" / "b.mp4", T0, b"ban khac")             # b trùng tên → BO_QUA
    _video(kho.op / "_loai" / "z.mp4")                              # z chấm lại Đạt → TRA
    assert _chay(kho) == 5
    ra = capsys.readouterr().out
    assert "BO_QUA: b.mp4" in ra and "DOI: a.mp4 -> _loai" in ra and "TRA: z.mp4" in ra
    for p in (kho.goc.as_posix(), str(kho.goc), kho.du_an.name):
        assert p not in ra


# ---------- [P1-1] đọc kết quả chấm bản MỚI NHẤT từ remote (git fetch + git show), không đụng cây làm việc ----------

_GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *_GIT_ID, *args], cwd=cwd, capture_output=True, timeout=60, check=False)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return r.stdout.decode("utf-8", "replace")


def _thanh_git(repo: Path, tmp: Path) -> tuple[Path, Path]:
    """repo (máy nhà) có remote bare `origin` + một bản clone `web` mô phỏng Worker ghi thẳng lên GitHub."""
    tu_xa = tmp / "remote.git"
    _git(tmp, "init", "-q", "--bare", "-b", "main", str(tu_xa))
    (repo / "data" / "README").write_text("kho", encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "dau")
    _git(repo, "remote", "add", "origin", str(tu_xa))
    _git(repo, "push", "-q", "-u", "origin", "main")
    web = tmp / "web"
    _git(tmp, "clone", "-q", str(tu_xa), str(web))
    return tu_xa, web


def _web_ghi(web: Path, rel: str, noi: str) -> None:
    f = web / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(noi, encoding="utf-8")
    _git(web, "add", "-A")
    _git(web, "commit", "-q", "-m", f"web {rel}")
    _git(web, "push", "-q", "origin", "main")


def _duyet_json(*muc) -> str:
    return json.dumps({"videos": [{"goc": g, "ten": t, "sua_luc": s, "ket_qua": kq} for g, t, s, kq in muc]})


@pytest.fixture
def kho_git(kho, tmp_path):
    kho.tu_xa, kho.web = _thanh_git(kho.repo, tmp_path)
    kho.head = _git(kho.repo, "rev-parse", "HEAD").strip()
    return kho


def test_tu_remote_doc_ban_moi_khong_dung_cay_lam_viec(kho_git):
    k = kho_git
    _web_ghi(k.web, f"data/{UID}/duyet.json", _duyet_json((k.goc_op, "a.mp4", T0, "loai")))
    assert bl.loai_trong_folder(str(k.op), k.repo, [k.goc]) == []           # cây làm việc cũ: chưa thấy Loại
    assert _chay(k, "--tu-remote") == 0
    assert _ten(k.op / "_loai") == ["a.mp4"]
    # chỉ fetch: HEAD, cây làm việc, index không đổi
    assert _git(k.repo, "rev-parse", "HEAD").strip() == k.head
    assert not (k.repo / "data" / UID / "duyet.json").exists()
    assert _git(k.repo, "status", "--porcelain") == ""


def test_doc_ket_qua_duyet_moi_nhat(kho_git):
    k = kho_git
    assert bl.doc_ket_qua_duyet_moi_nhat(k.repo, UID) is None               # remote chưa có duyet.json
    _web_ghi(k.web, f"data/{UID}/duyet.json", _duyet_json((k.goc_op, "a.mp4", T0, "loai")))
    assert bl.doc_ket_qua_duyet_moi_nhat(k.repo, UID, fetch=False) is None  # chưa fetch → ref cũ
    kq = bl.doc_ket_qua_duyet_moi_nhat(k.repo, UID)
    assert kq == {(bl.chuan_khoa_goc(k.goc_op), "a.mp4", T0): "loai"}
    ref = bl.lay_ban_moi_nhat(k.repo, fetch=False)
    assert ref == "refs/remotes/origin/main"
    assert bl.doc_file_ban_moi(k.repo, ref, f"data/{UID}/info.json") is None
    _web_ghi(k.web, f"data/{UID}/duyet.json", "{hỏng")
    with pytest.raises(bl.LoiDuLieu):
        bl.doc_ket_qua_duyet_moi_nhat(k.repo, UID)


def test_tu_remote_thieu_duyet_json_khong_tra_gi(kho_git):
    k = kho_git
    _video(k.op / "_loai" / "z.mp4")
    assert _chay(k, "--tu-remote") == 0
    assert _ten(k.op / "_loai") == ["z.mp4"]


def test_tu_remote_fetch_loi_ma_2_khong_doi(kho_git, capsys):
    k = kho_git
    _video(k.op / "_loai" / "z.mp4")
    _git(k.repo, "remote", "set-url", "origin", str(k.tu_xa.parent / "khong_co.git"))
    assert _chay(k, "--tu-remote") == 2
    assert _ten(k.op / "_loai") == ["z.mp4"] and _ten(k.op) == ["a.mp4", "b.mp4", "c.mp4", "ghi_chu.txt"]
    assert "[LỖI]" in capsys.readouterr().err


def test_khong_co_upstream_la_loi_git(kho, tmp_path):
    _git(kho.repo, "init", "-q", "-b", "main")
    with pytest.raises(bl.LoiGit):
        bl.lay_ban_moi_nhat(kho.repo, fetch=False)
    with pytest.raises(bl.LoiGit):
        bl.lay_ban_moi_nhat(tmp_path / "khong_phai_repo", fetch=False)


def test_moi_lenh_git_co_timeout_khong_hoi_mat_khau(kho_git, monkeypatch):
    """[FX-B2 P2-1] Mọi lệnh git: có timeout, tắt hộp thoại GCM/terminal, cắt kết nối chậm."""
    that = bl._chay_gioi_han
    goi: list[tuple[list[str], float, dict]] = []

    def gia(argv, het_gio_s, *, env=None):
        goi.append((list(argv), het_gio_s, dict(env or {})))
        return that(argv, het_gio_s, env=env)
    monkeypatch.setattr(bl, "_chay_gioi_han", gia)
    bl.doc_ket_qua_duyet_moi_nhat(kho_git.repo, UID)
    assert goi and any("fetch" in a for a, _t, _e in goi)
    for a, t, e in goi:
        assert a[0] == "git" and isinstance(t, (int, float)) and 0 < t <= bl.HET_GIO_FETCH_S
        for c in ("credential.interactive=false", "http.lowSpeedLimit=1000", "http.lowSpeedTime=30"):
            assert c in a, (c, a)
        assert e.get("GCM_INTERACTIVE") == "never" and e.get("GIT_TERMINAL_PROMPT") == "0"

    def khong_co_git(*_a, **_k):
        raise FileNotFoundError(2, "git")
    monkeypatch.setattr(bl.subprocess, "Popen", khong_co_git)
    with pytest.raises(bl.LoiGit):
        bl.doc_ket_qua_duyet_moi_nhat(kho_git.repo, UID)


_CHAU_GIU_PIPE = """
import subprocess, sys, time
chau = subprocess.Popen([sys.executable, "-c",
    "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(120)", sys.argv[1]])
print("con chay", flush=True)
time.sleep(float(sys.argv[2]))
"""


def _con_song(pid: int) -> bool:
    if os.name == "nt":
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"], capture_output=True,
                           timeout=30, check=False)
        return f'"{pid}"' in r.stdout.decode("utf-8", "replace")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _doi_pid(f: Path) -> int:
    import time
    for _ in range(100):
        if f.is_file() and f.read_text(encoding="utf-8").strip():
            return int(f.read_text(encoding="utf-8"))
        time.sleep(0.1)
    raise AssertionError("tiến trình cháu không ghi pid")


def _giet(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=30, check=False)
    else:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass


def test_qua_gio_giet_ca_cay_khong_treo_vi_chau_giu_pipe(tmp_path):
    """[FX-B2 P2-1] THẬT: con quá giờ, cháu (như git-remote-https/GCM) giữ stdout ngủ lâu → trả LoiGit trong
    ≤ timeout + vài giây (không chờ cháu), và cháu bị giết theo cây."""
    import time
    f = tmp_path / "pid_chau.txt"
    bat_dau = time.monotonic()
    with pytest.raises(bl.LoiGit, match="quá"):
        bl._chay_gioi_han([sys.executable, "-c", _CHAU_GIU_PIPE, str(f), "120"], 2)
    tre = time.monotonic() - bat_dau
    pid = _doi_pid(f)
    try:
        assert tre < 2 + 10, tre
        for _ in range(50):
            if not _con_song(pid):
                break
            time.sleep(0.2)
        assert not _con_song(pid), "cháu còn sống sau khi giết cây"
    finally:
        _giet(pid)


def test_con_xong_som_chau_con_giu_pipe_khong_treo(tmp_path):
    """[FX-B2 P2-1] Con thoát ngay nhưng cháu còn giữ stdout: không chờ cháu (bẫy communicate()), trả output con."""
    import time
    f = tmp_path / "pid_chau.txt"
    bat_dau = time.monotonic()
    rc, out, _err = bl._chay_gioi_han([sys.executable, "-c", _CHAU_GIU_PIPE, str(f), "0"], 30)
    tre = time.monotonic() - bat_dau
    pid = _doi_pid(f)
    try:
        assert rc == 0 and b"con chay" in out
        assert tre < 15, tre
    finally:
        _giet(pid)


def test_fetch_vuong_khoa_ref_la_tam_thoi(kho_git):
    """[FX-B2 P2-2] fetch đụng khoá ref (kho.py đang pull/push) → LoiGit.tam_thoi (bên gọi chờ, không việc tay);
    lỗi khác (remote mất) → không tạm thời. Thông báo không lộ đường dẫn ổ đĩa."""
    k = kho_git
    _web_ghi(k.web, f"data/{UID}/duyet.json", _duyet_json((k.goc_op, "a.mp4", T0, "loai")))
    khoa = k.repo / ".git" / "refs" / "remotes" / "origin" / "main.lock"
    khoa.write_text("", encoding="utf-8")
    try:
        with pytest.raises(bl.LoiGit) as e:
            bl.lay_ban_moi_nhat(k.repo)
        assert e.value.tam_thoi
        assert str(k.repo) not in str(e.value) and k.repo.as_posix() not in str(e.value)
        assert str(k.repo.parent) not in str(e.value) and k.repo.parent.as_posix() not in str(e.value)
    finally:
        khoa.unlink()
    _git(k.repo, "remote", "set-url", "origin", str(k.tu_xa.parent / "khong_co.git"))
    with pytest.raises(bl.LoiGit) as e:
        bl.lay_ban_moi_nhat(k.repo)
    assert not e.value.tam_thoi
    assert k.tu_xa.parent.as_posix() not in str(e.value) and str(k.tu_xa.parent) not in str(e.value)


def test_che_duong_dan():
    s = ("fatal: '/c/Users/Mi/x.git' does not appear; Unable to create 'E:/phan tich/kho/.git/a.lock': File "
         "exists. at C:\\Users\\Mi\\kho\\data and E:/kho/data/x")
    ra = bl._che_duong_dan(s)
    for la in ("Users", "phan tich", "kho"):
        assert la not in ra, ra
    assert "File exists" in ra and "fatal:" in ra


def test_stderr_va_log_khong_lo_duong_dan(kho, tmp_path, monkeypatch, caplog):
    """[FX-B2 P3-1] Lỗi dữ liệu và cảnh báo (gộp vào log việc qua stderr) chỉ có tên, không có đường dẫn."""
    bi_mat = kho.goc.parent.as_posix()
    lenh = [sys.executable, "-B", "-I", str(Path(bl.__file__)), "--repo-kho", str(kho.repo), "--uid", UID,
            "--goc", str(kho.goc), "--goc", str(tmp_path / "o_chua_cam")]
    moi_truong = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    # gốc không đọc được (ổ chưa cắm), chạy như script thật (stderr thật)
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "dat"))
    r = subprocess.run(lenh, capture_output=True, timeout=60, check=False, env=moi_truong)
    err = r.stderr.decode("utf-8", "replace")
    assert r.returncode == 0 and "o_chua_cam" in err, err
    for p in (bi_mat, str(kho.goc.parent), str(tmp_path)):
        assert p not in err, err
    # duyet.json hỏng
    (kho.repo / "data" / UID / "duyet.json").write_text("{hỏng", encoding="utf-8")
    r = subprocess.run(lenh, capture_output=True, timeout=60, check=False, env=moi_truong)
    err = r.stderr.decode("utf-8", "replace")
    assert r.returncode == 2 and "[LỖI]" in err and "duyet.json" in err
    for p in (bi_mat, str(kho.goc.parent), str(tmp_path)):
        assert p not in err, err
    # thiếu data/ trong --repo-kho
    r = subprocess.run([sys.executable, "-B", "-I", str(Path(bl.__file__)), "--repo-kho", str(tmp_path / "x"),
                        "--uid", UID, "--goc", str(kho.goc)], capture_output=True, timeout=60, check=False,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    err = r.stderr.decode("utf-8", "replace")
    assert r.returncode == 2 and str(tmp_path) not in err and tmp_path.as_posix() not in err
    # file bị khoá: cảnh báo chỉ có tên file
    (kho.repo / "data" / UID / "duyet.json").unlink()
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"))

    def thay(src: Path, _dst: Path) -> None:
        raise PermissionError(13, "file đang mở", str(src))
    monkeypatch.setattr(bl, "_thay_file", thay)
    monkeypatch.setattr(bl, "_ngu", lambda _s: None)
    with caplog.at_level("WARNING", logger=bl.__name__):
        assert _chay(kho) == 5
    assert "a.mp4" in caplog.text and bi_mat not in caplog.text and str(kho.goc.parent) not in caplog.text


# ---------- FX-B3 ----------

def test_tu_remote_lap_lai_khi_web_ghi_giua_chung(kho_git, monkeypatch, capsys):
    """[FX-B3 P2-1] Bỏ Loại liên tiếp: lần Bỏ Loại thứ hai ghi lên web SAU khi lượt 1 đã fetch → lượt 2 fetch lại và
    trả nốt (việc mới cùng uid bị 409 nên chính việc đang chạy phải bắt kịp)."""
    k = kho_git
    _web_ghi(k.web, f"data/{UID}/duyet.json", _duyet_json((k.goc_op, "a.mp4", T0, "loai"),
                                                          (k.goc_op, "b.mp4", T0, "loai")))
    assert _chay(k, "--tu-remote") == 0
    assert _ten(k.op / "_loai") == ["a.mp4", "b.mp4"]
    _web_ghi(k.web, f"data/{UID}/duyet.json", _duyet_json((k.goc_op, "a.mp4", T0, "dat"),
                                                          (k.goc_op, "b.mp4", T0, "loai")))
    that = bl.thuc_hien
    lan: list[int] = []

    def thuc_hien(ke, *, xem=False):
        kq = that(ke, xem=xem)
        if not lan:                                   # web ghi lần Bỏ Loại thứ hai trong lúc lượt 1 đang dời
            _web_ghi(k.web, f"data/{UID}/duyet.json", _duyet_json((k.goc_op, "a.mp4", T0, "dat"),
                                                                  (k.goc_op, "b.mp4", T0, "dat")))
        lan.append(1)
        return kq
    monkeypatch.setattr(bl, "thuc_hien", thuc_hien)
    capsys.readouterr()
    assert _chay(k, "--tu-remote") == 0
    assert _ten(k.op / "_loai") == [] and "a.mp4" in _ten(k.op) and "b.mp4" in _ten(k.op)
    ra = capsys.readouterr().out.splitlines()
    assert "LUOT: 1" in ra and "LUOT: 2" in ra and "LUOT: 3" not in ra
    assert any(d.startswith("TRA: a.mp4") for d in ra) and any(d.startswith("TRA: b.mp4") for d in ra)


def test_tu_remote_toi_da_3_luot_con_viec_ma_5(kho_git, monkeypatch, capsys):
    k = kho_git
    _web_ghi(k.web, f"data/{UID}/duyet.json", _duyet_json((k.goc_op, "a.mp4", T0, "loai")))

    def khoa(src: Path, _dst: Path) -> None:
        raise PermissionError(13, "file đang mở", str(src))
    monkeypatch.setattr(bl, "_thay_file", khoa)
    monkeypatch.setattr(bl, "_ngu", lambda _s: None)
    assert _chay(k, "--tu-remote") == 5
    ra = capsys.readouterr().out.splitlines()
    assert [d for d in ra if d.startswith("LUOT:")] == ["LUOT: 1", "LUOT: 2", "LUOT: 3"]
    assert any(d.startswith("CON_VIEC: 1") for d in ra), ra
    assert (k.op / "a.mp4").is_file()


def test_tu_remote_khong_co_gi_mot_luot(kho_git, capsys):
    assert _chay(kho_git, "--tu-remote") == 0
    ra = capsys.readouterr().out.splitlines()
    assert [d for d in ra if d.startswith("LUOT:")] == ["LUOT: 1"] and ra[-1] == "TONG: bo=0 tra=0 bo_qua=0"


def test_tu_remote_khoa_ref_tam_thoi_thu_lai(kho_git, monkeypatch):
    """[FX-B3 P3-6] Bước chạy không còn _dk_kho: fetch vướng khoá ref tạm (kho.py) → thử lại vài lần rồi mới lỗi."""
    k = kho_git
    _web_ghi(k.web, f"data/{UID}/duyet.json", _duyet_json((k.goc_op, "a.mp4", T0, "loai")))
    khoa = k.repo / ".git" / "refs" / "remotes" / "origin" / "main.lock"
    khoa.write_text("", encoding="utf-8")
    ngu: list[float] = []

    def ngu_va_mo_khoa(s: float) -> None:
        ngu.append(s)
        if len(ngu) == 2:
            khoa.unlink()                              # kho.py tay xong
    monkeypatch.setattr(bl, "_ngu", ngu_va_mo_khoa)
    assert _chay(k, "--tu-remote") == 0
    assert len(ngu) == 2 and _ten(k.op / "_loai") == ["a.mp4"]
    khoa.write_text("", encoding="utf-8")
    _web_ghi(k.web, f"data/{UID}/duyet.json", _duyet_json((k.goc_op, "a.mp4", T0, "dat")))
    monkeypatch.setattr(bl, "_ngu", lambda _s: None)
    try:
        assert _chay(k, "--tu-remote") == 2                # khoá không nhả → lỗi, không dời gì
    finally:
        khoa.unlink()
    assert _ten(k.op / "_loai") == ["a.mp4"]


def test_fetch_khong_ghi_fetch_head_tat_gc(kho_git, monkeypatch):
    """[FX-B3 P3-4] fetch: --no-write-fetch-head, gc.auto=0, maintenance.auto=false (bớt đụng khoá với kho.py pull)."""
    that = bl._chay_gioi_han
    goi: list[list[str]] = []

    def gia(argv, het_gio_s, *, env=None):
        goi.append(list(argv))
        return that(argv, het_gio_s, env=env)
    monkeypatch.setattr(bl, "_chay_gioi_han", gia)
    bl.lay_ban_moi_nhat(kho_git.repo)
    f = next(a for a in goi if "fetch" in a)
    assert "--no-write-fetch-head" in f[f.index("fetch"):]
    for c in ("gc.auto=0", "maintenance.auto=false"):
        assert c in f[:f.index("fetch")], f
    assert not (kho_git.repo / ".git" / "FETCH_HEAD").exists()


@pytest.mark.parametrize("s", [
    "fatal: not a git repository: E:/Aff anh nhan/review/.git",
    "error: Unable to create E:/Aff anh nhan/review/.git/refs/x.lock: File exists.",
    "fatal: cannot change to 'E:/Aff anh nhan/review/.git': No such file",
    'fatal: "E:\\Aff anh nhan\\review\\.git" lỗi',
    "warning: /c/Users/Mi/Aff anh nhan/review/.git: bad",
])
def test_che_duong_dan_co_dau_cach(s):
    """[FX-B3 P3-2] Đường dẫn có dấu cách bị che trọn (trong nháy, hoặc tới ':' / hết dòng)."""
    ra = bl._che_duong_dan(s)
    for la in ("Aff", "anh nhan", "review", "Users"):
        assert la not in ra, ra
    assert ra.split(" ")[0] in ("fatal:", "error:", "warning:")
    if "File exists" in s:
        assert "File exists" in ra


# ---------- chạy như script thật (bản cài chỉ có stdlib, python -I) ----------

def test_chay_script_doc_lap(kho):
    _duyet(kho, (kho.goc_op, "a.mp4", T0, "loai"))
    r = subprocess.run([sys.executable, "-B", "-I", str(Path(bl.__file__)), "--repo-kho", str(kho.repo),
                        "--uid", UID, "--goc", str(kho.goc)], capture_output=True, timeout=60,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    out = r.stdout.decode("utf-8")
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert "DOI: a.mp4 -> _loai" in out and out.splitlines()[-1] == "TONG: bo=1 tra=0 bo_qua=0"
    assert _ten(kho.op / "_loai") == ["a.mp4"]
