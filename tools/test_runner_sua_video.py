"""Test lõi tra cứu + kiểm bản sửa (docs/sua-video.md §3, §4.2, §5.1–5.2, phiếu B-6).

Chạy: python -B -m pytest tools/test_runner_sua_video.py -q -p no:cacheprovider
Mọi dự án là dự án GIẢ trong tmp_path; không đụng dữ liệu thật.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from runner import sua_video as sv  # noqa: E402
from runner.du_an import ma_du_an  # noqa: E402
from runner.kieu import ThamSoLoi  # noqa: E402

UID = "1736818222555104357"
GOC_CU = r"Z:\cu\50oto"            # gốc cũ (thư mục đã đổi tên) — không tồn tại
GOC_CU_A = r"Z:\cu\aokhoac"
VAI_13 = ("hook", "problem", "product_intro", "benefit", "proof", "detail", "usage",
          "comparison", "social_proof", "broll", "offer", "cta", "outro")
T_VIDEO = 1_790_585_841_123_456_700  # mtime_ns cố định (bội 100 ns: độ phân giải NTFS)
CAU = [
    {"text": "Cái này là sàn trợ giá nè ba mẹ ơi !", "start": 0.0, "end": 2.3},
    {"text": "Xe chạy trớn , cực bền", "start": 2.3, "end": 4.24},
    {"text": "Mua ngay kẻo hết", "start": 4.24, "end": 6.0},
]


def _ghi_json(p: Path, d) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _ghi_bytes(p: Path, n: int = 100, ns: int | None = None) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * n)
    if ns is not None:
        os.utime(p, ns=(ns, ns))
    return p


def _take(p_take: Path, take_idx: int = 1, words: bool = True) -> None:
    _ghi_bytes(p_take, 50)
    stem = p_take.stem
    _ghi_json(p_take.with_name(stem + ".subtitles.json"),
              {"take_path": "cu", "duration": 6.0, "take_idx": take_idx,
               "sentences": [dict(c, words=[]) for c in CAU]})
    if words:
        _ghi_json(p_take.with_name(stem + ".words.json"), {"words": []})


def _kho_clip(p: Path) -> dict:
    """cuts/clip_index.json 13 vai; mỗi vai 3 clip (dài 1.0 / 3.0 / 5.0 s); 1 clip nằm thư mục con."""
    clips = {}
    for k, vai in enumerate(VAI_13):
        for j, dur in enumerate((1.0, 3.0, 5.0)):
            ten = f"raw-{k}_{j:03d}_{vai}_canh-{j}.mp4"
            clips[ten] = {"role": vai, "slug": f"canh-{j}", "dur": dur, "desc": f"mô tả {vai} {j}",
                          "tags": [f"t{n}" for n in range(12)], "is_visual_hook": False}
            thu_muc = p / "cuts" / (vai if (vai == "outro" and j == 2) else "")
            _ghi_bytes(thu_muc / ten, 10)
    # clip có trong index nhưng file mất
    clips["raw-99_000_proof_mat-file.mp4"] = {"role": "proof", "dur": 9.0, "desc": "", "tags": []}
    # ảnh khung cho 1 clip
    _ghi_bytes(p / "cuts" / ".index_frames" / "raw-4_001" / "f_00.jpg", 5)
    _ghi_json(p / "cuts" / "clip_index.json", {"version": 1, "clips": clips})
    return clips


def _seg(kind, a, b, src, role, dur=0.0, src_start=0.0):
    return {"kind": kind, "out_start": a, "out_end": b, "src": src, "src_start": src_start,
            "src_duration": dur, "role": role, "scene": -1, "hflip": False, "zoom": 1.0}


@pytest.fixture
def du_an_c(tmp_path):
    """Luồng C: output_poster/render_batch.json với đường dẫn GỐC CŨ + .done.json khớp."""
    goc = tmp_path / "goc"
    p = goc / f"50oto {UID}"
    _kho_clip(p)
    _take(p / "takes" / "0923 (1)(1)-85.mp4", take_idx=1)
    _take(p / "takes" / "0923 (1)(1)-86.mp4", take_idx=2)
    d = p / "output_poster"
    take_cu = GOC_CU + r"\takes\0923 (1)(1)-85.mp4"
    take_cu2 = GOC_CU + r"\takes\0923 (1)(1)-86.mp4"

    def plan(pid, take, ovl1="raw-4_001_proof_canh-1.mp4"):
        return {"plan_id": pid, "take_path": take, "take_idx": 1, "duration": 6.0,
                "bgm_path": r"F:\auto video oneshot\assets\bgm\a.mp3", "bgm_offset": 1.0, "seed": 7,
                "ass_path": GOC_CU + rf"\output\hau_ky\plan_{pid:03d}.ass",
                "segments": [_seg("BASE", 0.0, 6.0, take, "take"),
                             _seg("OVL", 1.0, 3.0, GOC_CU + "\\cuts\\" + ovl1, "proof", 3.0),
                             _seg("OVL", 3.0, 4.5, GOC_CU + r"\cuts\raw-5_001_detail_canh-1.mp4", "detail", 3.0),
                             # cuts/<vai>/ — engine tự tìm trong thư mục con
                             _seg("OVL", 4.5, 5.5, GOC_CU + r"\cuts\raw-12_002_outro_canh-2.mp4", "outro", 5.0)]}

    rb = {"version": 1,
          "plans": [plan(60, take_cu), plan(61, take_cu), plan(62, take_cu2),
                    dict(plan(63, take_cu), output_prefix="khac")],
          "options": {"workers": 2, "use_nvenc": True, "width": 1080, "height": 1920},
          "config": {"prefix": "50oto2809", "variation_enabled": False, "reuse_count": 0,
                     "image_options": {"prefix": "khongdung"}}}
    _ghi_json(d / "render_batch.json", rb)
    for pid in (60, 61, 62):
        f = _ghi_bytes(d / f"50oto2809_{pid:03d}.mp4", 1000 + pid, T_VIDEO)
        _ghi_json(d / f"50oto2809_{pid:03d}.done.json",
                  {"key": "k", "output": [GOC_CU + rf"\output\{f.name}", f.stat().st_size, f.stat().st_mtime_ns]})
    f = _ghi_bytes(d / "khac_063.mp4", 500, T_VIDEO)
    _ghi_json(d / "khac_063.done.json", {"key": "k", "output": ["x", 500, T_VIDEO]})
    return goc, p


@pytest.fixture
def du_an_a(tmp_path):
    """Luồng A: output_daonguoc/<B>_plan.json + hardlink output_poster."""
    goc = tmp_path / "goc"
    p = goc / f"aokhoac {UID}"
    _kho_clip(p)
    B = "20260930-cq01"
    for ma in ("htd1", "hti1"):
        _take(p / "voice" / "_takes" / B / f"{B}_{ma}.mp4", take_idx=0)
    out = p / "output_daonguoc"

    def plan(k, ma):
        src = GOC_CU_A + rf"\voice\_takes\{B}\{B}_{ma}.mp4"
        return {"plan_id": f"plan_{k:03d}", "take_idx": 0, "duration": 6.0, "bgm_path": "", "bgm_offset": 0.0,
                "seed": 1, "run_seed": 2, "cart_arrow_intervals": [],
                "segments": [_seg("BASE", 0.0, 6.0, src, "take"),
                             _seg("OVL", 0.0, 2.0, GOC_CU_A + r"\cuts\raw-4_001_proof_canh-1.mp4", "proof", 3.0),
                             _seg("OVL", 2.0, 4.0, GOC_CU_A + r"\cuts\raw-5_002_detail_canh-2.mp4", "detail", 5.0)],
                "mode": "legacy", "status": "ok", "warnings": []}

    _ghi_json(out / f"{B}_plan.json", [plan(0, "htd1"), plan(1, "hti1")])
    t_plan = T_VIDEO - 10**9
    os.utime(out / f"{B}_plan.json", ns=(t_plan, t_plan))
    for ma in ("htd1", "hti1"):
        g = _ghi_bytes(out / f"{B}_{ma}.mp4", 2000, T_VIDEO)
        (p / "output_poster").mkdir(parents=True, exist_ok=True)
        os.link(g, p / "output_poster" / g.name)
    return goc, p, B


# ---------------- định danh ----------------

def test_ma_video_on_dinh_va_dung_cong_thuc():
    m = sv.ma_video("abcdef012345", "output_poster", "50oto2809_061.mp4")
    assert m == hashlib.sha1("abcdef012345/output_poster/50oto2809_061.mp4".encode("utf-8")).hexdigest()[:16]
    assert m == sv.ma_video("abcdef012345", "output_poster", "50oto2809_061.mp4")
    assert m != sv.ma_video("abcdef012345", "output", "50oto2809_061.mp4")


def test_ds_video_goc_giong_video_server(du_an_c):
    goc, p = du_an_c
    ds = sv.ds_video_sua(p, goc)
    ten = [v.ten for v in ds]
    assert ten == sorted(ten, key=str.lower)
    assert all(v.goc == goc.as_posix() and v.thu_muc == "output_poster" for v in ds)
    assert all(v.du_an == ma_du_an(p) for v in ds)
    v = next(v for v in ds if v.ten == "50oto2809_061.mp4")
    assert v.sua_luc == T_VIDEO // 1_000_000
    assert v.ma_video == sv.ma_video(ma_du_an(p), "output_poster", v.ten)
    # thư mục output: goc = GOC#<thư mục>/output
    _ghi_bytes(p / "output" / "le.mp4", 10)
    v2 = next(v for v in sv.ds_video_sua(p, goc) if v.thu_muc == "output")
    assert v2.goc == goc.as_posix() + "#" + p.name + "/output"
    assert v2.sua_duoc is False and v2.ly_do


def test_ten_khong_hop_le_khong_sua_duoc(du_an_c):
    goc, p = du_an_c
    _ghi_bytes(p / "output_poster" / "_an.mp4", 10)
    v = next(v for v in sv.ds_video_sua(p, goc) if v.ten == "_an.mp4")
    assert v.sua_duoc is False and "tên" in v.ly_do.lower()


# ---------------- luồng C ----------------

def test_luong_c_anh_xa_va_doi_goc(du_an_c):
    goc, p = du_an_c
    v = next(v for v in sv.ds_video_sua(p, goc) if v.ten == "50oto2809_061.mp4")
    assert v.luong == "C" and v.sua_duoc, v.ly_do
    b = sv.tra_ban_ghi(p, v)
    assert b.luong == "C" and b.chi_so == 1 and b.plan["plan_id"] == 61
    assert b.nguon == p / "output_poster" / "render_batch.json"
    assert b.tien_to == "50oto2809" and b.me is None and b.ma is None
    assert b.take == p / "takes" / "0923 (1)(1)-85.mp4"
    assert b.phu_de == p / "takes" / "0923 (1)(1)-85.subtitles.json"
    assert Path(b.plan["take_path"]) == b.take
    assert b.file_ra == v.duong_dan and b.lien_ket is None
    srcs = [Path(s["src"]) for s in b.plan["segments"]]
    assert srcs[1] == p / "cuts" / "raw-4_001_proof_canh-1.mp4"
    assert srcs[3] == p / "cuts" / "outro" / "raw-12_002_outro_canh-2.mp4"  # tìm trong thư mục con
    assert b.goc_cu and b.goc_cu.replace("\\", "/").lower() == GOC_CU.replace("\\", "/").lower()
    assert b.plan["bgm_path"] == r"F:\auto video oneshot\assets\bgm\a.mp3"   # không dưới gốc cũ → giữ
    assert b.plan["ass_path"].startswith(GOC_CU)                            # ass không đổi gốc
    assert b.tuy_chon["width"] == 1080 and b.cau_hinh["prefix"] == "50oto2809"
    assert b.bien_the is False


def test_luong_c_output_prefix_rieng(du_an_c):
    goc, p = du_an_c
    v = next(v for v in sv.ds_video_sua(p, goc) if v.ten == "khac_063.mp4")
    assert v.sua_duoc, v.ly_do
    assert sv.tra_ban_ghi(p, v).plan["plan_id"] == 63


def test_luong_c_tu_choi_khi_done_lech(du_an_c):
    goc, p = du_an_c
    f = p / "output_poster" / "50oto2809_061.mp4"
    os.utime(f, ns=(T_VIDEO + 100, T_VIDEO + 100))
    v = next(v for v in sv.ds_video_sua(p, goc) if v.ten == f.name)
    assert v.sua_duoc is False and "chứng minh" in v.ly_do
    with pytest.raises(sv.KhongTraDuoc):
        sv.tra_ban_ghi(p, v)


def test_luong_c_tu_choi_khi_thieu_done(du_an_c):
    goc, p = du_an_c
    (p / "output_poster" / "50oto2809_060.done.json").unlink()
    v = next(v for v in sv.ds_video_sua(p, goc) if v.ten == "50oto2809_060.mp4")
    assert v.sua_duoc is False and "chứng minh" in v.ly_do


def test_luong_c_done_size_la_bool_khong_khop(du_an_c):
    goc, p = du_an_c
    f = p / "output_poster" / "50oto2809_060.mp4"
    _ghi_json(p / "output_poster" / "50oto2809_060.done.json", {"output": ["x", True, T_VIDEO]})
    os.utime(f, ns=(T_VIDEO, T_VIDEO))
    v = next(v for v in sv.ds_video_sua(p, goc) if v.ten == f.name)
    assert v.sua_duoc is False


def test_luong_c_khong_khop_nham_so_0061(du_an_c):
    goc, p = du_an_c
    f = _ghi_bytes(p / "output_poster" / "50oto2809_0061.mp4", 5, T_VIDEO)
    _ghi_json(p / "output_poster" / "50oto2809_0061.done.json", {"output": ["x", 5, T_VIDEO]})
    v = next(v for v in sv.ds_video_sua(p, goc) if v.ten == f.name)
    assert v.sua_duoc is False


def test_luong_c_thieu_file_nguon_liet_ke(du_an_c):
    goc, p = du_an_c
    (p / "cuts" / "raw-5_001_detail_canh-1.mp4").unlink()
    v = next(v for v in sv.ds_video_sua(p, goc) if v.ten == "50oto2809_061.mp4")
    assert v.sua_duoc is False and "raw-5_001_detail_canh-1.mp4" in v.ly_do


def test_render_batch_hong_khong_sap_ca_danh_sach(du_an_c):
    goc, p = du_an_c
    (p / "output_poster" / "render_batch.json").write_text("{hỏng", encoding="utf-8")
    ds = sv.ds_video_sua(p, goc)
    assert ds and all(not v.sua_duoc for v in ds)
    _ghi_json(p / "output_poster" / "render_batch.json", {"version": 1, "plans": "sai", "config": {}})
    assert all(not v.sua_duoc for v in sv.ds_video_sua(p, goc))
    _ghi_json(p / "output_poster" / "render_batch.json", {"version": 2, "plans": [], "config": {}})
    assert all(not v.sua_duoc for v in sv.ds_video_sua(p, goc))


def test_bien_the(du_an_c):
    goc, p = du_an_c
    f = p / "output_poster" / "render_batch.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["config"].update(variation_enabled=True, reuse_count=2)
    _ghi_json(f, d)
    v = sv.tim_video(p, goc, sv.ma_video(ma_du_an(p), "output_poster", "50oto2809_061.mp4"))
    b = sv.tra_ban_ghi(p, v)
    assert b.bien_the is True
    ct = sv.lap_chi_tiet(p, v, b)
    with pytest.raises(ThamSoLoi, match="biến thể"):
        sv.kiem_ban_sua(_body(ct, phu_de=[{"i": 0, "text": "Chữ mới"}]), ct)
    # chỉ đổi clip vẫn được
    assert sv.kiem_ban_sua(_body(ct, doi_cho=[[1, 2]]), ct)["doi_cho"] == [[1, 2]]


# ---------------- đổi gốc ----------------

def test_doi_goc_ranh_gioi_va_hoa_thuong(tmp_path):
    p = tmp_path / "moi"
    assert Path(sv.doi_goc(GOC_CU + r"\takes\a.mp4", GOC_CU, p)) == p / "takes" / "a.mp4"
    assert Path(sv.doi_goc("z:/CU/50OTO/cuts/b.mp4", GOC_CU, p)) == p / "cuts" / "b.mp4"
    # cùng tiền tố chuỗi nhưng khác thư mục → giữ nguyên
    assert sv.doi_goc(r"Z:\cu\50oto2\a.mp4", GOC_CU, p) == r"Z:\cu\50oto2\a.mp4"
    assert sv.doi_goc(r"Z:\cu\50oto 1736818222555104357\a.mp4", GOC_CU, p) == r"Z:\cu\50oto 1736818222555104357\a.mp4"
    assert sv.doi_goc("", GOC_CU, p) == ""
    assert sv.doi_goc(r"X:\a.mp4", None, p) == r"X:\a.mp4"


# ---------------- luồng A ----------------

def test_luong_a_anh_xa_hardlink(du_an_a):
    goc, p, B = du_an_a
    v = next(v for v in sv.ds_video_sua(p, goc) if v.ten == f"{B}_hti1.mp4")
    assert v.luong == "A" and v.sua_duoc, v.ly_do
    b = sv.tra_ban_ghi(p, v)
    assert b.chi_so == 1 and b.me == B and b.ma == "hti1" and b.tien_to is None
    assert b.nguon == p / "output_daonguoc" / f"{B}_plan.json"
    assert b.file_ra == p / "output_daonguoc" / f"{B}_hti1.mp4"
    assert b.lien_ket == p / "output_poster" / f"{B}_hti1.mp4"
    assert b.take == p / "voice" / "_takes" / B / f"{B}_hti1.mp4"
    assert b.phu_de == b.take.with_name(f"{B}_hti1.subtitles.json")
    assert Path(b.plan["segments"][1]["src"]) == p / "cuts" / "raw-4_001_proof_canh-1.mp4"
    assert "take_path" not in b.plan
    assert b.tuy_chon == {} and b.cau_hinh == {} and b.bien_the is False
    assert b.goc_cu.replace("\\", "/").lower() == GOC_CU_A.replace("\\", "/").lower()
    assert b.canh_bao == ()


def test_luong_a_ban_chep_cung_size_canh_bao(du_an_a):
    goc, p, B = du_an_a
    f = p / "output_poster" / f"{B}_htd1.mp4"
    f.unlink()
    _ghi_bytes(f, 2000, T_VIDEO)
    v = next(v for v in sv.ds_video_sua(p, goc) if v.ten == f.name)
    assert v.sua_duoc, v.ly_do
    b = sv.tra_ban_ghi(p, v)
    assert b.lien_ket == f and any("bản chép" in c for c in b.canh_bao)


def test_luong_a_khac_size_tu_choi(du_an_a):
    goc, p, B = du_an_a
    f = p / "output_poster" / f"{B}_htd1.mp4"
    f.unlink()
    _ghi_bytes(f, 1999, T_VIDEO)
    v = next(v for v in sv.ds_video_sua(p, goc) if v.ten == f.name)
    assert v.sua_duoc is False


def test_luong_a_plan_moi_hon_video_tu_choi(du_an_a):
    goc, p, B = du_an_a
    pf = p / "output_daonguoc" / f"{B}_plan.json"
    os.utime(pf, ns=(T_VIDEO + 10**9, T_VIDEO + 10**9))
    v = next(v for v in sv.ds_video_sua(p, goc) if v.ten == f"{B}_htd1.mp4")
    assert v.sua_duoc is False


def test_luong_a_khong_co_plan_cua_ma(du_an_a):
    goc, p, B = du_an_a
    g = _ghi_bytes(p / "output_daonguoc" / f"{B}_zz9.mp4", 10, T_VIDEO)
    os.link(g, p / "output_poster" / g.name)
    v = next(v for v in sv.ds_video_sua(p, goc) if v.ten == g.name)
    assert v.luong == "A" and v.sua_duoc is False


def test_tim_video_khong_co(du_an_a):
    goc, p, _B = du_an_a
    with pytest.raises(sv.KhongTraDuoc):
        sv.tim_video(p, goc, "0" * 16)


# ---------------- phụ đề / cảnh / ứng viên ----------------

def _ban_ghi_c(du_an_c, ten="50oto2809_061.mp4"):
    goc, p = du_an_c
    v = sv.tim_video(p, goc, sv.ma_video(ma_du_an(p), "output_poster", ten))
    return p, v, sv.tra_ban_ghi(p, v)


def test_doc_phu_de(du_an_c):
    p, v, b = _ban_ghi_c(du_an_c)
    pd = sv.doc_phu_de(b)
    assert pd["sha"] == hashlib.sha256(b.phu_de.read_bytes()).hexdigest()
    assert pd["take_idx"] == 1 and pd["co_words"] is True and pd["bien_the"] is False
    assert pd["take"] == "takes/0923 (1)(1)-85.mp4"
    assert pd["so_video_cung_take"] == 2       # plan 60 và 63 cùng take; 62 khác take
    assert pd["cau"][0] == {"i": 0, "start": 0.0, "end": 2.3, "text": "Cái này là sàn trợ giá nè ba mẹ ơi!"}
    assert pd["cau"][1]["text"] == "Xe chạy trớn, cực bền"


def test_doc_phu_de_thieu_words(du_an_c):
    p, v, b = _ban_ghi_c(du_an_c)
    b.take.with_name(b.take.stem + ".words.json").unlink()
    assert sv.doc_phu_de(b)["co_words"] is False
    ct = sv.lap_chi_tiet(p, v, b)
    with pytest.raises(ThamSoLoi, match="Whisper"):
        sv.kiem_ban_sua(_body(ct, phu_de=[{"i": 0, "text": "Mới"}]), ct)


def test_doc_canh(du_an_c):
    p, v, b = _ban_ghi_c(du_an_c)
    c = sv.doc_canh(b, p)
    assert [x["kind"] for x in c] == ["BASE", "OVL", "OVL", "OVL"]
    assert c[0]["doi_duoc"] is False and c[0]["ly_do"]
    assert c[1] == {"i": 1, "kind": "OVL", "out_start": 1.0, "out_end": 3.0, "role": "proof",
                    "clip": "raw-4_001_proof_canh-1.mp4", "doi_duoc": True, "ly_do": ""}


def test_ung_vien(du_an_c):
    p, v, b = _ban_ghi_c(du_an_c)
    uv = sv.ung_vien(p, b, 1)
    assert {u["role"] for u in uv} == {"proof"}
    ten = {u["clip"]: u for u in uv}
    assert "raw-99_000_proof_mat-file.mp4" not in ten                 # file mất
    assert ten["raw-4_001_proof_canh-1.mp4"]["dung_duoc"] is False      # đã có trong video
    assert "đã có" in ten["raw-4_001_proof_canh-1.mp4"]["ly_do"]
    assert ten["raw-4_000_proof_canh-0.mp4"]["dung_duoc"] is False      # 1.0 < 2.0
    assert "ngắn" in ten["raw-4_000_proof_canh-0.mp4"]["ly_do"]
    assert ten["raw-4_002_proof_canh-2.mp4"]["dung_duoc"] is True
    assert uv[0]["clip"] == "raw-4_002_proof_canh-2.mp4"                 # dùng được xếp đầu
    assert ten["raw-4_001_proof_canh-1.mp4"]["co_anh"] is True
    assert len(ten["raw-4_002_proof_canh-2.mp4"]["tags"]) == 8
    assert sv.ung_vien(p, b, 1, gioi_han=1) == uv[:1]
    with pytest.raises(ThamSoLoi):
        sv.ung_vien(p, b, 0)        # BASE
    with pytest.raises(ThamSoLoi):
        sv.ung_vien(p, b, 99)


def test_ung_vien_che_do_ctx_so_variant_of(du_an_c):
    p, v, b = _ban_ghi_c(du_an_c)
    ci = p / "cuts" / "clip_index.json"
    d = json.loads(ci.read_text(encoding="utf-8"))
    d["clips"]["raw-4_002_proof_canh-2.mp4"]["variant_of"] = "raw-4_001_proof_canh-1.mp4"
    _ghi_json(ci, d)
    b2 = sv.BanGhi(**{**b.__dict__, "plan": {**b.plan, "mode": "ctx"}})
    ten = {u["clip"]: u for u in sv.ung_vien(p, b2, 1)}
    assert ten["raw-4_002_proof_canh-2.mp4"]["dung_duoc"] is False
    ten = {u["clip"]: u for u in sv.ung_vien(p, b, 1)}    # legacy: chỉ so tên file
    assert ten["raw-4_002_proof_canh-2.mp4"]["dung_duoc"] is True


# ---------------- kiểm bản sửa ----------------

def _body(ct, **kw):
    b = {"sua_luc": ct["sua_luc"], "phu_de_sha": (ct["phu_de"] or {}).get("sha", ""),
         "phu_de": [], "doi_clip": [], "doi_cho": []}
    b.update(kw)
    return b


@pytest.fixture
def ct(du_an_c):
    p, v, b = _ban_ghi_c(du_an_c)
    return sv.lap_chi_tiet(p, v, b)


def test_kiem_hop_le_va_chuan_hoa(ct):
    body = _body(ct, phu_de=[{"i": 2, "text": "  Mu\u0301a ngay  "}, {"i": 0, "text": "Trời ơi, chạy trớn nha!"}],
                 doi_clip=[{"seg": 1, "clip": "raw-4_002_proof_canh-2.mp4"}], doi_cho=[[3, 2]])
    body["phu_de_sha"] = ct["phu_de"]["sha"].upper()          # chuẩn hoá trước khi so
    kq = sv.kiem_ban_sua(body, ct)
    assert [x["i"] for x in kq["phu_de"]] == [0, 2]
    assert kq["phu_de"][1]["text"] == "Múa ngay"              # NFC + bỏ khoảng trắng đầu/cuối
    assert kq["doi_clip"] == [{"seg": 1, "clip": "raw-4_002_proof_canh-2.mp4"}]
    assert kq["doi_cho"] == [[2, 3]]
    assert kq["phu_de_sha"] == ct["phu_de"]["sha"]
    assert kq["ma_video"] == ct["ma_video"]
    # cùng nội dung, thứ tự khác → cùng mã bản sửa
    body2 = dict(body, phu_de=list(reversed(body["phu_de"])), doi_cho=[[2, 3]])
    assert sv.ma_ban_sua(sv.kiem_ban_sua(body2, ct)) == sv.ma_ban_sua(kq)
    assert sv.ma_ban_sua(kq).startswith("b") and len(sv.ma_ban_sua(kq)) == 17


def test_ma_ban_sua_cong_thuc(ct):
    kq = sv.kiem_ban_sua(_body(ct, doi_cho=[[1, 2]]), ct)
    chuan = json.dumps(kq, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert sv.ma_ban_sua(kq) == "b" + hashlib.sha256(chuan.encode("utf-8")).hexdigest()[:16]


@pytest.mark.parametrize("chu", ["a{b", "a}b", "a\\b", "a<b", "a>b", "a-->b", "dòng\nmới", "a\rb", "a\tb",
                                 "a\x00b", "a\u2028b", "a\u202eb", "", "   "])
def test_loc_ky_tu(ct, chu):
    with pytest.raises(ThamSoLoi):
        sv.kiem_ban_sua(_body(ct, phu_de=[{"i": 0, "text": chu}]), ct)


def test_gioi_han_200_ky_tu(ct):
    assert sv.kiem_ban_sua(_body(ct, phu_de=[{"i": 0, "text": "ă" * 200}]), ct)
    with pytest.raises(ThamSoLoi):
        sv.kiem_ban_sua(_body(ct, phu_de=[{"i": 0, "text": "ă" * 201}]), ct)
    # 200 code point SAU NFC: "a" + dấu kết hợp = 1 code point
    assert sv.kiem_ban_sua(_body(ct, phu_de=[{"i": 0, "text": "a\u0301" * 200}]), ct)


def test_gioi_han_30_cau(du_an_c):
    p, v, b = _ban_ghi_c(du_an_c)
    ct = sv.lap_chi_tiet(p, v, b)
    ct["phu_de"]["cau"] = [{"i": k, "start": k, "end": k + 1, "text": "x"} for k in range(40)]
    with pytest.raises(ThamSoLoi):
        sv.kiem_ban_sua(_body(ct, phu_de=[{"i": k, "text": f"c{k}"} for k in range(31)]), ct)
    assert len(sv.kiem_ban_sua(_body(ct, phu_de=[{"i": k, "text": f"c{k}"} for k in range(30)]), ct)["phu_de"]) == 30


def test_gioi_han_16kb_tra_413(ct):
    body = _body(ct, phu_de=[{"i": 0, "text": "a"}], rac="x" * 17000)
    with pytest.raises(sv.BanSuaQuaLon) as e:
        sv.kiem_ban_sua(body, ct)
    assert e.value.ma_http == 413


def test_gioi_han_doi_clip_doi_cho(ct):
    with pytest.raises(ThamSoLoi):
        sv.kiem_ban_sua(_body(ct, doi_clip=[{"seg": 1, "clip": "raw-4_002_proof_canh-2.mp4"}] * 11), ct)
    with pytest.raises(ThamSoLoi):
        sv.kiem_ban_sua(_body(ct, doi_cho=[[1, 2], [1, 3], [2, 3], [1, 2]]), ct)


def test_i_sai_trung_va_khong_doi(ct):
    for pd in ([{"i": 3, "text": "x"}], [{"i": -1, "text": "x"}], [{"i": True, "text": "x"}],
               [{"i": "0", "text": "x"}], [{"i": 0, "text": "x"}, {"i": 0, "text": "y"}],
               [{"i": 0, "text": "x", "la": 1}], ["x"]):
        with pytest.raises(ThamSoLoi):
            sv.kiem_ban_sua(_body(ct, phu_de=pd), ct)
    # chữ giống hệt bản cũ (đã gộp dấu) → bỏ mục → không còn thay đổi nào
    with pytest.raises(ThamSoLoi, match="thay đổi"):
        sv.kiem_ban_sua(_body(ct, phu_de=[{"i": 1, "text": "Xe chạy trớn, cực bền"}]), ct)


def test_lech_sha_va_sua_luc_409(ct):
    with pytest.raises(sv.BanSuaLech) as e:
        sv.kiem_ban_sua(_body(ct, phu_de=[{"i": 0, "text": "x"}], phu_de_sha="0" * 64), ct)
    assert e.value.ma_http == 409
    with pytest.raises(sv.BanSuaLech):
        sv.kiem_ban_sua(_body(ct, doi_cho=[[1, 2]], sua_luc=ct["sua_luc"] + 1), ct)
    with pytest.raises(ThamSoLoi):
        sv.kiem_ban_sua(_body(ct, doi_cho=[[1, 2]], sua_luc=True), ct)


def test_khoa_la_va_hinh_dang(ct):
    with pytest.raises(ThamSoLoi):
        sv.kiem_ban_sua(_body(ct, doi_cho=[[1, 2]], lenh="rm"), ct)
    with pytest.raises(ThamSoLoi):
        sv.kiem_ban_sua("khong-phai-dict", ct)
    # 'boi' được chấp nhận nhưng không vào bản chuẩn
    assert "boi" not in sv.kiem_ban_sua(_body(ct, doi_cho=[[1, 2]], boi="nhan"), ct)


def test_doi_clip_luat(ct):
    def loi(dc):
        with pytest.raises(ThamSoLoi):
            sv.kiem_ban_sua(_body(ct, doi_clip=dc), ct)
    loi([{"seg": 0, "clip": "raw-4_002_proof_canh-2.mp4"}])            # BASE
    loi([{"seg": 1, "clip": "raw-5_002_detail_canh-2.mp4"}])           # khác vai
    loi([{"seg": 1, "clip": "raw-4_000_proof_canh-0.mp4"}])            # quá ngắn
    loi([{"seg": 1, "clip": "raw-99_000_proof_mat-file.mp4"}])         # file mất
    loi([{"seg": 1, "clip": "khong-co.mp4"}])                          # không có trong index
    loi([{"seg": 1, "clip": "../a.mp4"}])                              # tên sai mẫu
    loi([{"seg": 2, "clip": "raw-4_001_proof_canh-1.mp4"}])            # khác vai + đã có
    loi([{"seg": 1, "clip": "raw-4_002_proof_canh-2.mp4"}, {"seg": 1, "clip": "raw-4_002_proof_canh-2.mp4"}])
    # clip giống clip hiện tại → không phải thay đổi
    with pytest.raises(ThamSoLoi):
        sv.kiem_ban_sua(_body(ct, doi_clip=[{"seg": 1, "clip": "raw-4_001_proof_canh-1.mp4"}]), ct)


def test_doi_clip_trung_trong_video_sau_khi_ap(du_an_c):
    """Hai đoạn cùng vai đổi sang cùng một clip → trùng trong video mới."""
    goc, p = du_an_c
    f = p / "output_poster" / "render_batch.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["plans"][1]["segments"][2]["role"] = "proof"
    d["plans"][1]["segments"][2]["src"] = GOC_CU + r"\cuts\raw-4_000_proof_canh-0.mp4"
    _ghi_json(f, d)
    p, v, b = _ban_ghi_c(du_an_c)
    ct = sv.lap_chi_tiet(p, v, b)
    with pytest.raises(ThamSoLoi, match="đã có"):
        sv.kiem_ban_sua(_body(ct, doi_clip=[{"seg": 1, "clip": "raw-4_002_proof_canh-2.mp4"},
                                            {"seg": 2, "clip": "raw-4_002_proof_canh-2.mp4"}]), ct)


def test_doi_cho_luat(ct):
    def loi(dc, **kw):
        with pytest.raises(ThamSoLoi):
            sv.kiem_ban_sua(_body(ct, doi_cho=dc, **kw), ct)
    loi([[0, 1]])           # BASE
    loi([[1, 1]])           # cùng đoạn
    loi([[1, 9]])           # ngoài phạm vi
    loi([[1]])              # sai hình
    loi([[1, 2], [2, 3]])   # đoạn 2 xuất hiện 2 lần
    loi([[1, 2]], doi_clip=[{"seg": 1, "clip": "raw-4_002_proof_canh-2.mp4"}])  # vừa đổi clip vừa đổi chỗ
    # clip đoạn 3 (5.0 s) vào khung đoạn 1 (2.0 s) và clip đoạn 1 (3.0 s) vào khung đoạn 3 (1.0 s) → được
    assert sv.kiem_ban_sua(_body(ct, doi_cho=[[1, 3]]), ct)["doi_cho"] == [[1, 3]]


def test_doi_cho_clip_khong_du_dai(du_an_c):
    goc, p = du_an_c
    f = p / "output_poster" / "render_batch.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["plans"][1]["segments"][3]["src"] = GOC_CU + r"\cuts\raw-12_000_outro_canh-0.mp4"  # 1.0 s
    d["plans"][1]["segments"][3]["src_duration"] = 1.0
    _ghi_json(f, d)
    p, v, b = _ban_ghi_c(du_an_c)
    ct = sv.lap_chi_tiet(p, v, b)
    with pytest.raises(ThamSoLoi, match="ngắn"):
        sv.kiem_ban_sua(_body(ct, doi_cho=[[1, 3]]), ct)   # clip 1.0 s vào khung 2.0 s


# ---------------- SRT, nhật ký ----------------

def test_lap_srt():
    cau = [{"i": 0, "start": 0.0, "end": 2.3, "text": "Câu một"},
           {"i": 1, "start": 2.3, "end": 61.234, "text": "Câu --> hai\nxuống"},
           {"i": 2, "start": 3700.5, "end": 3701.0, "text": ""}]
    s = sv.lap_srt(cau, {0: "Trời ơi, mới!"})
    assert s == ("1\n00:00:00,000 --> 00:00:02,300\nTrời ơi, mới!\n\n"
                 "2\n00:00:02,300 --> 00:01:01,234\nCâu -> hai xuống\n\n")
    with pytest.raises(ThamSoLoi):
        sv.lap_srt(cau, {0: "a{\\b}"})
    with pytest.raises(ThamSoLoi):
        sv.lap_srt(cau, {7: "x"})


def test_nhat_ky(du_an_c, tmp_path):
    p, v, b = _ban_ghi_c(du_an_c)
    nk = sv.duong_nhat_ky(b, "j20261117090000abcd")
    assert nk == b.file_ra.parent / "_sua" / "j20261117090000abcd.json"
    for sai in ("../x", "j1", "J20261117090000abcd", "j20261117090000abcd/.."):
        with pytest.raises(ThamSoLoi):
            sv.duong_nhat_ky(b, sai)
    assert sv.doc_nhat_ky(nk) is None
    _ghi_json(nk, {"buoc": "xong"})
    assert sv.doc_nhat_ky(nk) == {"buoc": "xong"}
    nk.write_text("[1]", encoding="utf-8")
    with pytest.raises(ValueError):
        sv.doc_nhat_ky(nk)
    nk.write_text("{hỏng", encoding="utf-8")
    with pytest.raises(ValueError):
        sv.doc_nhat_ky(nk)


# ---------- FX-22: sửa chữ cần mật khẩu + đọc kết thúc mã 2/5 của bộ chuyển đổi ----------

def test_co_sua_chu():
    assert sv.co_sua_chu({"phu_de": [{"i": 1, "text": "x"}], "doi_clip": []}) is True
    assert sv.co_sua_chu({"phu_de": [], "doi_clip": [{"seg": 1, "clip": "a.mp4"}]}) is False
    assert sv.co_sua_chu({"doi_clip": [{"seg": 1, "clip": "a.mp4"}]}) is False
    assert sv.co_sua_chu(None) is False
    assert sv.co_sua_chu({"phu_de": "lạ"}) is True        # dạng lạ nhưng có giá trị → chặn (an toàn)


def _loi_vong_lap(ten: str, ma: int, ly_do: str, canh_bao=(), json_dong: bool = True,
                  stderr_dong: bool = True) -> str:
    """Đúng dạng vong_lap ghi: 'Bước <ten> thoát mã N:\\n<đuôi log gộp stdout+stderr>' (engine main in stderr rồi
    KET_QUA_JSON)."""
    kq = {"trang_thai": {2: "khong_hop_le", 5: "do_dang"}.get(ma, "loi"), "ly_do": ly_do, "sao_luu": None,
          "canh_bao": list(canh_bao), "video": "50oto2809_061.mp4", "giay": 1.2}
    dong = ["INFO bắt đầu"]
    if stderr_dong:
        dong.append(f"[sua_video] mã {ma}: {ly_do}")
    if json_dong:
        dong.append("KET_QUA_JSON " + json.dumps(kq, ensure_ascii=False))
    return f"Bước {ten} thoát mã {ma}:\n" + "\n".join(dong)


@pytest.mark.parametrize("ten, ly_do, bo", [
    ("sua_video", "Hoàn nguyên bỏ qua 50oto2809_061.done.json, render_batch.json vì việc khác đã đổi — không làm "
                  "lại, kiểm tay", ["50oto2809_061.done.json", "render_batch.json"]),
    ("sua_video", "Lần hoàn nguyên trước đã bỏ qua phụ đề (việc khác đã đổi) — kiểm tay, tạo việc sửa mới nếu cần",
     ["phụ đề"]),
    ("sua_video", "Dựng hỏng (RuntimeError: ffmpeg (mã 1)); hoàn nguyên bỏ qua render_batch.json — kiểm tay",
     ["render_batch.json"]),
    ("hoan_tac_sua", "Video đã về bản cũ nhưng hoàn tác bỏ qua phụ đề (việc khác đã đổi) — kiểm tay", ["phụ đề"]),
    ("hoan_tac_sua", "Lần hoàn tác trước đã bỏ qua phụ đề (việc khác đã đổi) — kiểm tay", ["phụ đề"]),
])
def test_ket_thuc_ma_5_bo_qua_la_kiem_tay(ten, ly_do, bo):
    kq = sv.doc_ket_thuc_loi(ten, _loi_vong_lap(ten, 5, ly_do, canh_bao=["Hoàn nguyên bỏ qua x — kiểm tay"]))
    assert kq["ma_thoat"] == 5 and kq["kiem_tay"] is True and kq["do_dang"] is False
    assert kq["bo_qua"] == bo and kq["ly_do_sua"] == ly_do
    assert kq["canh_bao_sua"] == ["Hoàn nguyên bỏ qua x — kiểm tay"]
    assert "kiểm tay" in kq["thong_diep"].lower() and all(m in kq["thong_diep"] for m in bo)
    assert "không giúp được" in kq["thong_diep"]


@pytest.mark.parametrize("ten, ly_do", [
    ("sua_video", "Video đã đổi giữa lúc sửa (không khớp bản vừa dựng) — kiểm tay"),
    ("hoan_tac_sua", "Hoàn tác hỏng giữa chừng (OSError: khoá) — bấm Chạy lại để làm nốt"),
    ("sua_video", "Dựng hỏng (x) và hoàn nguyên cũng hỏng (y) — xem nhật ký"),
])
def test_ket_thuc_ma_5_do_dang_khac_kiem_tay(ten, ly_do):
    kq = sv.doc_ket_thuc_loi(ten, _loi_vong_lap(ten, 5, ly_do))
    assert kq["ma_thoat"] == 5 and kq["kiem_tay"] is False and kq["do_dang"] is True
    assert kq["bo_qua"] == [] and kq["ly_do_sua"] == ly_do and ly_do in kq["thong_diep"]


def test_ket_thuc_ma_2_hoan_tac_ban_moi_hon_thong_diep_ro():
    ly_do = "Không hoàn tác tự động: đã có bản mới hơn sau lần sửa này ở render_batch.json — chưa đổi gì"
    kq = sv.doc_ket_thuc_loi("hoan_tac_sua", _loi_vong_lap("hoan_tac_sua", 2, ly_do))
    assert kq["ma_thoat"] == 2 and kq["chua_doi_gi"] is True and kq["kiem_tay"] is False
    assert "bản mới hơn" in kq["thong_diep"] and "chưa đổi gì" in kq["thong_diep"]
    assert "render_batch.json" in kq["thong_diep"] and "Sửa video" in kq["thong_diep"]
    kq2 = sv.doc_ket_thuc_loi("sua_video", _loi_vong_lap("sua_video", 2, "Video này không sửa được"))
    assert kq2["ma_thoat"] == 2 and kq2["chua_doi_gi"] is True and "Video này không sửa được" in kq2["thong_diep"]


def test_ket_thuc_doc_du_phong_khi_dong_json_bi_cat():
    ly_do = "Hoàn nguyên bỏ qua render_batch.json vì việc khác đã đổi — không làm lại, kiểm tay"
    chi_stderr = _loi_vong_lap("sua_video", 5, ly_do, json_dong=False)
    assert sv.doc_ket_thuc_loi("sua_video", chi_stderr)["bo_qua"] == ["render_batch.json"]
    cat = _loi_vong_lap("sua_video", 5, ly_do, stderr_dong=False)
    cat = cat.replace("KET_QUA_JSON {", "{")[:-5]                              # vong_lap cắt [-1200:] mất đầu dòng
    kq = sv.doc_ket_thuc_loi("sua_video", "Bước sua_video thoát mã 5:\n" + cat.split("\n", 1)[1])
    assert kq["ma_thoat"] == 5 and kq["kiem_tay"] is False and kq["ly_do_sua"] == ""
    assert "log" in kq["thong_diep"]


@pytest.mark.parametrize("ten, loi", [
    ("sua_video", "quá giờ"),
    ("sua_video", None),
    ("sua_video", "Bước sua_video thoát mã 4:\nKET_QUA_JSON {\"ly_do\": \"x\"}"),
    ("sua_video", "Bước sua_video thoát mã 3:\n[sua_video] mã 3: bận"),
    ("sua_video", "Bước hoan_tac_sua thoát mã 5:\n[sua_video] mã 5: bỏ qua x — kiểm tay"),   # tên bước lệch loại
    ("phan_tich_uid", "Bước sua_video thoát mã 5:\n[sua_video] mã 5: x"),
])
def test_ket_thuc_khong_lien_quan_tra_none(ten, loi):
    assert sv.doc_ket_thuc_loi(ten, loi) is None


def test_chi_stdlib():
    import ast
    src = Path(sv.__file__).read_text(encoding="utf-8")
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0:
            mods.add(n.module.split(".")[0])
    assert mods <= set(sys.stdlib_module_names) | {"__future__"}, mods
