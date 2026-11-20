"""Test bộ chuyển đổi sửa video (docs/sua-video.md §6, §11 A-6).

Chạy bằng Python của engine (Python hệ thống thì bị bỏ qua vì không có `modules.render`):
    "/f/auto video oneshot/.venv/Scripts/python.exe" -B -m pytest tools/test_sua_video_engine.py -q -p no:cacheprovider

Mọi dự án là dự án GIẢ trong tmp_path, dựng bằng `ffmpeg -f lavfi` và render THẬT bằng CPU (libx264, khung nhỏ).
Không đụng dự án thật, không đụng E:\\oneshottramcanh (AUTOVIDEO_KHOA_MAY trỏ sang thư mục tạm).
"""
from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOLS = Path(__file__).resolve().parent
ENGINE = Path(os.environ.get("KHO_ENGINE_DIR") or r"F:\auto video oneshot")
for _d in (str(ENGINE), str(TOOLS)):
    if _d not in sys.path:
        sys.path.insert(0, _d)
pytest.importorskip("modules.render")

from runner import sua_video as sv  # noqa: E402
from runner import sua_video_engine as m  # noqa: E402

FFMPEG = shutil.which("ffmpeg") or r"F:\ffmpeg\bin\ffmpeg.exe"
W, H, FPS = 360, 640, 30
VIEC = "j20261117120000ab01"
VIEC2 = "j20261117130000ab02"
UID = "1736818222555104357"
VAI = "benefit"
CLIP = [f"raw-1_00{k}_{VAI}_canh-{c}.mp4" for k, c in enumerate("abc")]
TU = [("Cho", 0.2, 0.5), ("nha", 0.5, 0.9), ("cái", 1.0, 1.4), ("này", 1.4, 1.8), ("đẹp", 1.9, 2.3),
      ("lắm", 2.3, 2.8), ("mua", 3.3, 3.7), ("ngay", 3.7, 4.2), ("kẻo", 4.4, 4.9), ("hết", 4.9, 5.5)]
ME, MA_A = "20261101-ak", "ud1"


def _ff(*args: str) -> None:
    r = subprocess.run([FFMPEG, "-v", "error", "-y", *args], capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-800:]


def _take(f: Path, mau: str, e) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    _ff("-f", "lavfi", "-i", f"color=c={mau}:s={W}x{H}:d=6:r={FPS}", "-f", "lavfi", "-i",
        "sine=frequency=440:duration=6", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(f))
    words = [{"text": t, "start": a, "end": b} for t, a, b in TU]
    f.with_suffix(".words.json").write_text(json.dumps({
        "words": words, "duration": 6.0, "cfg_fp": e.sjb._whisper_fingerprint(m.MODEL_WHISPER, "cuda"),
        "source_sig": list(e.sjb._file_sig(f))}, ensure_ascii=False), encoding="utf-8")
    cau = [{"text": "Cho nha cái này đẹp lắm", "start": 0.2, "end": 2.8, "words": words[:6]},
           {"text": "mua ngay kẻo hết", "start": 3.3, "end": 5.5, "words": words[6:]}]
    f.with_name(f.stem + ".subtitles.json").write_text(json.dumps({
        "take_path": str(f), "duration": 6.0, "words": words, "sentences": cau, "subs_fp": "cu", "take_idx": 0},
        ensure_ascii=False), encoding="utf-8")


def _kho(p: Path) -> None:
    cuts = p / "cuts"
    cuts.mkdir(parents=True, exist_ok=True)
    for ten, mau in zip(CLIP, ("red", "green", "yellow")):
        _ff("-f", "lavfi", "-i", f"color=c={mau}:s={W}x{H}:d=3:r={FPS}", "-c:v", "libx264", "-preset",
            "ultrafast", "-pix_fmt", "yuv420p", str(cuts / ten))
    (cuts / "clip_index.json").write_text(json.dumps({"version": 1, "clips": {
        t: {"role": VAI, "slug": t[11:-4], "dur": 3.0, "desc": "cảnh thử", "tags": []} for t in CLIP}},
        ensure_ascii=False), encoding="utf-8")


def _plan(e, pid: int, take: Path, p: Path, ovl: list[tuple[float, float, int, float]]):
    segs = [e.timeline.Seg(kind="BASE", out_start=0.0, out_end=6.0, src=str(take), src_start=0.0, src_duration=6.0)]
    for a, b, k, ss in ovl:
        segs.append(e.timeline.Seg(kind="OVL", out_start=a, out_end=b, src=str(p / "cuts" / CLIP[k]), src_start=ss,
                                   src_duration=3.0, role=VAI, clip=CLIP[k]))
    return e.timeline.TimelinePlan(plan_id=pid, take_path=str(take), take_idx=0, segments=segs, duration=6.0,
                                   seed=11 + pid, run_seed=1)


@pytest.fixture(scope="module")
def eng():
    return m.nap_engine()


@pytest.fixture(scope="module")
def mau_c(tmp_path_factory, eng):
    """Luồng C: dựng mẻ 2 bản bằng engine thật ở `50oto`, rồi đổi tên thư mục (+ output → output_poster)
    như dữ liệu thật — render_batch.json còn đường dẫn GỐC CŨ."""
    e = eng
    goc = tmp_path_factory.mktemp("mau_c")
    cu = goc / "50oto"
    take = cu / "takes" / "take01.mp4"
    _take(take, "0x3050a0", e)
    _kho(cu)
    out = cu / "output"
    cfg = SimpleNamespace(**vars(e.cfg.load_config()))
    cfg.prefix, cfg.burn_subtitle, cfg.image_options = "50oto2809", True, None
    cfg.bgm_on, cfg.clip_audio_on, cfg.loudnorm, cfg.progress_bar = False, False, False, False
    cfg.sticker, cfg.punch = False, False
    plans = [_plan(e, 0, take, cu, [(0.5, 2.5, 0, 0.0), (3.0, 5.0, 1, 0.0)]),
             _plan(e, 1, take, cu, [(0.5, 2.5, 1, 0.5), (3.0, 5.0, 0, 0.5)])]
    for pl in plans:
        e.hau_ky.dung_hau_ky_cho_plan(pl, subtitle_json_path=str(take.with_name("take01.subtitles.json")),
                                      output_folder=out, burn_subtitle=True, sub_cfg=e.sr.sub_cfg_tu_config(cfg),
                                      width=W, height=H, cart_arrow=True)
    kq = e.render.render_batch_plans(plans, out, workers=2, use_nvenc=False, width=W, height=H, fps=FPS,
                                     dissolve=0.1, pad_or_crop="crop", bgm_on=False, config_snapshot=cfg)
    assert all(ok for ok, _ in kq), kq
    p = goc / f"50oto {UID}"
    cu.rename(p)
    (p / "output").rename(p / "output_poster")
    return p


@pytest.fixture(scope="module")
def mau_a(tmp_path_factory, eng):
    """Luồng A: mẻ Adam 1 bản `<B>_ud1.mp4` trong output_daonguoc + hardlink trong output_poster."""
    e = eng
    p = tmp_path_factory.mktemp("mau_a") / f"aokhoac {UID}"
    take = p / "voice" / "_takes" / ME / f"{ME}_{MA_A}.mp4"
    _take(take, "black", e)
    _kho(p)
    out = p / "output_daonguoc"
    out.mkdir()
    pl = _plan(e, 0, take, p, [(0.5, 2.5, 0, 0.0), (3.0, 5.0, 1, 0.0)])
    (out / f"{ME}_plan.json").write_text(json.dumps([pl.to_dict()], indent=1, ensure_ascii=False), encoding="utf-8")
    cfg = m._phu(e.cfg.load_config(), burn_subtitle=True, cart_arrow_on=True, sticker=False, punch=False)
    snap = e.img.merge_config(cfg, {"prefix": f"_tmp_{ME}", "dissolve": 0.1, "speed_on": False,
                                    "frame_jitter_on": False})
    e.hau_ky.dung_hau_ky_cho_plan(pl, subtitle_json_path=str(take.with_name(take.stem + ".subtitles.json")),
                                  output_folder=out / "_hau_ky" / ME, burn_subtitle=True,
                                  sub_cfg=e.sr.sub_cfg_tu_config(cfg), width=W, height=H, cart_arrow=True)
    ok, msg = e.render.render_single_plan(pl, out, width=W, height=H, fps=FPS, dissolve=0.1, use_nvenc=False,
                                          pad_or_crop="crop", bgm_volume=0.168, config_snapshot=snap)
    assert ok, msg
    tam = out / f"_tmp_{ME}_000.mp4"
    os.replace(tam, out / f"{ME}_{MA_A}.mp4")
    tam.with_suffix(".done.json").unlink()
    shutil.rmtree(out / "_hau_ky")
    return p


def _chep(mau: Path, dich_goc: Path) -> Path:
    p = dich_goc / mau.name
    shutil.copytree(mau, p)                             # copy2: giữ mtime_ns (source_sig, .done.json khớp)
    return p


@pytest.fixture
def moi_truong(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOVIDEO_KHOA_MAY", str(tmp_path / "khoa_may.lock"))
    monkeypatch.setattr(m, "KHUNG_A", (W, H, FPS))
    monkeypatch.setattr(m, "NVENC_A", False)
    monkeypatch.chdir(ENGINE)
    return tmp_path


@pytest.fixture
def du_an_c(mau_c, moi_truong):
    return _chep(mau_c, moi_truong / "du_an")


@pytest.fixture
def du_an_a(mau_a, moi_truong):
    p = _chep(mau_a, moi_truong / "du_an")
    ten = f"{ME}_{MA_A}.mp4"
    (p / "output_poster").mkdir()
    os.link(p / "output_daonguoc" / ten, p / "output_poster" / ten)
    return p


def _ban(p: Path, thu_muc: str, ten: str, data_dir: Path, **sua) -> tuple[Path, dict]:
    """Bản sửa chuẩn hoá đúng như runner ghi DATA/sua/<ban_sua>.json (qua kiem_ban_sua của B-6)."""
    v = sv.tim_video(p, p.parent, sv.ma_video(sv.ma_du_an(p), thu_muc, ten))
    assert v.sua_duoc, v.ly_do
    b = sv.tra_ban_ghi(p, v)
    ct = sv.lap_chi_tiet(p, v, b)
    body = {"sua_luc": v.sua_luc, **sua}
    if "phu_de" in sua:
        body["phu_de_sha"] = ct["phu_de"]["sha"]
    ban = sv.kiem_ban_sua(body, ct)
    f = data_dir / "sua" / f"{sv.ma_ban_sua(ban)}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(ban, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return f, ban


def _argv(p: Path, thu_muc: str, ten: str, ban_f: Path, viec: str = VIEC, xem: bool = False) -> list[str]:
    a = ["ap-dung", "--project", str(p), "--thu-muc", thu_muc, "--video", ten, "--ban-sua", str(ban_f),
         "--viec", viec]
    return a + (["--xem"] if xem else [])


def _mau_tb(f: Path) -> tuple[int, int, int]:
    """Màu trung bình cả khung (thu về 1×1 px) — đọc bằng ffmpeg, không cần thư viện ảnh."""
    r = subprocess.run([FFMPEG, "-v", "error", "-i", str(f), "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt",
                        "rgb24", "-"], capture_output=True, timeout=60)
    assert r.returncode == 0 and len(r.stdout) == 3, r.stderr[-300:]
    return r.stdout[0], r.stdout[1], r.stdout[2]


def _st(f: Path) -> tuple[int, int]:
    st = f.stat()
    return st.st_size, st.st_mtime_ns


def _ket_qua(capsys) -> dict:
    dong = [x for x in capsys.readouterr().out.splitlines() if x.startswith("KET_QUA_JSON ")]
    assert dong, "thiếu dòng KET_QUA_JSON"
    return json.loads(dong[-1][len("KET_QUA_JSON "):])


TEN_C = "50oto2809_000.mp4"


def _gia_render(eng, kq):
    """Render giả GIỮ chữ ký thật (functools.wraps) — bộ chuyển đổi kiểm chữ ký engine trước khi chạy (R-9)."""
    @functools.wraps(eng.render.render_single_plan)
    def gia(*a, **k):
        return kq()
    return gia


# ---------------- (1) sửa 1 câu ----------------

def test_1_sua_cau_phu_de(du_an_c, moi_truong, capsys):
    p = du_an_c
    take = p / "takes" / "take01.mp4"
    wj, sub = take.with_suffix(".words.json"), p / "takes" / "take01.subtitles.json"
    f = p / "output_poster" / TEN_C
    words_ns, cu = wj.stat().st_mtime_ns, _st(f)
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, phu_de=[{"i": 1, "text": "mua liền kẻo hết"}])
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 0, capsys.readouterr()
    kq = _ket_qua(capsys)
    assert kq["trang_thai"] == "xong" and kq["video"] == TEN_C
    d = json.loads(sub.read_text(encoding="utf-8"))
    chu = " ".join(s["text"] for s in d["sentences"])
    assert "liền" in chu and d["take_idx"] == 0
    assert wj.stat().st_mtime_ns == words_ns                     # không chạy Whisper
    rb = json.loads((p / "output_poster" / "render_batch.json").read_text(encoding="utf-8"))
    ass = Path(rb["plans"][0]["ass_path"])
    assert ass.parent == p / "output_poster" / "_sua" / VIEC / "hau_ky"
    assert "liền" in ass.read_text(encoding="utf-8")             # chữ mới đi vào phụ đề burn
    assert take.with_suffix(".sua.srt").is_file()
    assert _st(f) != cu                                          # đã dựng lại
    nk = sv.doc_nhat_ky(p / "output_poster" / "_sua" / f"{VIEC}.json")
    assert nk["buoc"] == "xong" and nk["phu_de"]["sha_sau"] == sv.hashlib.sha256(sub.read_bytes()).hexdigest()
    assert os.path.samefile(p / nk["cu"]["sao_luu"], p / nk["cu"]["sao_luu"])
    assert _st(p / nk["cu"]["sao_luu"]) == cu                    # bản cũ còn nguyên trong _sua_cu/
    assert not (p / ".render.lock").exists() and not (moi_truong / "khoa_may.lock").exists()
    # chạy lại cùng việc (runner khởi động lại sau khi xong) → mã 0, không dựng lại
    moi = _st(f)
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 0
    assert _st(f) == moi


# ---------------- (2) đổi clip + (6) hoàn tác ----------------

def test_2_doi_clip_resume_va_6_hoan_tac(du_an_c, moi_truong, capsys, eng):
    p = du_an_c
    d = p / "output_poster"
    f = d / TEN_C
    rb = d / "render_batch.json"
    truoc = json.loads(rb.read_text(encoding="utf-8"))
    done_truoc = (d / "50oto2809_000.done.json").read_bytes()
    cu = _st(f)
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 0, capsys.readouterr()
    sau = json.loads(rb.read_text(encoding="utf-8"))
    assert sau["plans"][1] == truoc["plans"][1]                  # chỉ đổi đúng 1 mục
    assert sau["plans"][0] != truoc["plans"][0]
    assert sau["plans"][0]["segments"][2]["clip"] == CLIP[2]
    assert {k: v for k, v in sau.items() if k != "plans"} == {k: v for k, v in truoc.items() if k != "plans"}
    done = json.loads((d / "50oto2809_000.done.json").read_text(encoding="utf-8"))
    assert done["output"] == eng.rc.file_sig(f)                  # .done.json khớp bản mới
    assert (d / "_sua" / VIEC / "khung_2.jpg").is_file()         # §6.7 khung kiểm bằng mắt
    r, g, bl = _mau_tb(d / "_sua" / VIEC / "khung_2.jpg")
    assert r > 150 and g > 150 and bl < 110, (r, g, bl)          # khung giữa đoạn 2 là clip vàng (clip c) thật
    moi = _st(f)
    # "chạy tiếp" của engine: bản đã sửa KHÔNG bị dựng lại (key + chữ ký khớp)
    eng.rc.resume_batch(d)
    assert _st(f) == moi
    # (6) hoàn tác → đúng size/mtime cũ, bản ghi + .done.json cũ trở lại
    rb_moi = json.loads(rb.read_text(encoding="utf-8"))          # resume_batch vừa ghi lại render_batch.json
    capsys.readouterr()
    argv = ["hoan-tac", "--project", str(p), "--thu-muc", "output_poster", "--video", TEN_C,
            "--viec-goc", VIEC, "--viec", VIEC2]
    assert m.main(argv) == 0, capsys.readouterr()
    assert _ket_qua(capsys)["trang_thai"] == "xong"
    assert _st(f) == cu
    sau_ht = json.loads(rb.read_text(encoding="utf-8"))
    assert sau_ht["plans"][0] == truoc["plans"][0]
    assert sau_ht["plans"][1] == rb_moi["plans"][1]
    assert (d / "50oto2809_000.done.json").read_bytes() == done_truoc
    v = sv.tim_video(p, p.parent, sv.ma_video(sv.ma_du_an(p), "output_poster", TEN_C))
    assert v.sua_duoc, v.ly_do                                   # tra cứu lại được như trước khi sửa
    assert _st(d / "_sua_cu" / f"50oto2809_000.{VIEC2}.mp4") == moi   # bản đã sửa được giữ lại


# ---------------- (3) luồng A: link output_poster trỏ inode mới ----------------

def test_3_luong_a_lien_ket(du_an_a, moi_truong, capsys):
    p = du_an_a
    ten = f"{ME}_{MA_A}.mp4"
    goc, lk = p / "output_daonguoc" / ten, p / "output_poster" / ten
    pf = p / "output_daonguoc" / f"{ME}_plan.json"
    pf_ns, cu = pf.stat().st_mtime_ns, _st(goc)
    ban_f, _ = _ban(p, "output_poster", ten, moi_truong, doi_clip=[{"seg": 1, "clip": CLIP[2]}])
    assert m.main(_argv(p, "output_poster", ten, ban_f)) == 0, capsys.readouterr()
    assert _st(goc) != cu
    assert os.path.samefile(goc, lk)
    assert pf.stat().st_mtime_ns == pf_ns                        # giữ luật tra §3.3 bước 3 cho cả mẻ
    plans = json.loads(pf.read_text(encoding="utf-8"))
    assert plans[0]["segments"][1]["clip"] == CLIP[2] and plans[0]["plan_id"] == "plan_000"
    assert not (p / "output_daonguoc" / "_sua" / VIEC / "ra").exists()
    v = sv.tim_video(p, p.parent, sv.ma_video(sv.ma_du_an(p), "output_poster", ten))
    assert v.sua_duoc, v.ly_do


# ---------------- (4) render hỏng → mã 4, mọi thứ y nguyên ----------------

def test_4_render_hong_hoan_nguyen(du_an_c, moi_truong, capsys, eng, monkeypatch):
    p = du_an_c
    d = p / "output_poster"
    f = d / TEN_C
    sub = p / "takes" / "take01.subtitles.json"
    sub_truoc, done_truoc, rb_truoc = sub.read_bytes(), (d / "50oto2809_000.done.json").read_bytes(), \
        (d / "render_batch.json").read_bytes()
    cu = _st(f)
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, phu_de=[{"i": 0, "text": "Cho nha cái này xịn lắm"}],
                    doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    monkeypatch.setattr(eng.render, "render_single_plan", _gia_render(eng, lambda: (False, "giả lỗi NVENC + CPU")))
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 4
    kq = _ket_qua(capsys)
    assert kq["trang_thai"] == "dung_hong" and "giả lỗi" in kq["ly_do"]
    assert _st(f) == cu
    assert sub.read_bytes() == sub_truoc
    assert not (p / "takes" / "take01.sua.srt").exists()
    assert (d / "50oto2809_000.done.json").read_bytes() == done_truoc
    assert (d / "render_batch.json").read_bytes() == rb_truoc
    assert not (d / "_sua_cu" / f"50oto2809_000.{VIEC}.mp4").exists()
    assert sv.doc_nhat_ky(d / "_sua" / f"{VIEC}.json")["buoc"] == "hoan_nguyen"
    assert not (p / ".render.lock").exists()


# ---------------- (5) ngắt sau `thay` → chạy lại làm nốt ----------------

def test_5_ngat_sau_thay_chay_lai_lam_not(du_an_a, moi_truong, capsys, monkeypatch):
    p = du_an_a
    ten = f"{ME}_{MA_A}.mp4"
    goc, lk = p / "output_daonguoc" / ten, p / "output_poster" / ten
    ban_f, _ = _ban(p, "output_poster", ten, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    that = m.PhienSua.buoc_nguon

    def ngat(self):
        self.ghi("nguon")
        raise OSError("giả mất điện giữa bước nguon")
    monkeypatch.setattr(m.PhienSua, "buoc_nguon", ngat)
    assert m.main(_argv(p, "output_poster", ten, ban_f)) == 5
    assert _ket_qua(capsys)["trang_thai"] == "do_dang"
    nk_f = p / "output_daonguoc" / "_sua" / f"{VIEC}.json"
    assert sv.doc_nhat_ky(nk_f)["buoc"] == "nguon"
    assert not os.path.samefile(goc, lk)                          # link chưa nối
    assert not (p / ".render.lock").exists() and not (moi_truong / "khoa_may.lock").exists()
    moi = _st(goc)
    monkeypatch.setattr(m.PhienSua, "buoc_nguon", that)
    assert m.main(_argv(p, "output_poster", ten, ban_f)) == 0, capsys.readouterr()
    assert _st(goc) == moi                                        # không dựng lại
    assert os.path.samefile(goc, lk)
    plans = json.loads((p / "output_daonguoc" / f"{ME}_plan.json").read_text(encoding="utf-8"))
    assert plans[0]["segments"][2]["clip"] == CLIP[2]
    assert sv.doc_nhat_ky(nk_f)["buoc"] == "xong"


# ---------------- (7) khoá bận → mã 3 ----------------

def test_7_khoa_du_an_ban_ma_3_qua_dong_lenh(du_an_c, moi_truong):
    """Chạy đúng dòng lệnh §6.1 (subprocess dạng list, cwd = engine) để kiểm cả mã thoát + KET_QUA_JSON."""
    p = du_an_c
    f = p / "output_poster" / TEN_C
    cu = _st(f)
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    khoa = p / ".render.lock"
    khoa.write_text(json.dumps({"batch": "20261117-x", "pid": 1, "viec": "render", "luc": 0, "het_han": 180,
                                "du_an": str(p)}), encoding="utf-8")
    env = dict(os.environ, KHO_SUA_CHO_KHOA="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
               AUTOVIDEO_KHOA_MAY=str(moi_truong / "khoa_may.lock"))
    r = subprocess.run([sys.executable, "-B", str(TOOLS / "runner" / "sua_video_engine.py"),
                        *_argv(p, "output_poster", TEN_C, ban_f)], cwd=str(ENGINE), env=env,
                       capture_output=True, timeout=120)
    out = r.stdout.decode("utf-8")
    assert r.returncode == 3, (out, r.stderr.decode("utf-8", "replace"))
    kq = json.loads(out.strip().splitlines()[-1][len("KET_QUA_JSON "):])
    assert kq["trang_thai"] == "ban" and kq["video"] == TEN_C
    assert _st(f) == cu
    assert khoa.exists()                                          # không xoá khoá của người khác
    assert not (p / "output_poster" / "_sua").exists()


def test_7b_khoa_may_ban_nha_khoa_du_an(du_an_c, moi_truong, capsys, monkeypatch):
    p = du_an_c
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    (moi_truong / "khoa_may.lock").write_text(json.dumps({"batch": "x", "pid": 1, "het_han": 180}), encoding="utf-8")
    monkeypatch.setenv("KHO_SUA_CHO_KHOA", "0.3")
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 3
    assert not (p / ".render.lock").exists()                     # khoá dự án đã lấy thì phải nhả


def test_khoa_cu_bi_go(tmp_path):
    f = tmp_path / ".render.lock"
    f.write_text(json.dumps({"batch": "x", "pid": 1, "het_han": 180}), encoding="utf-8")
    os.utime(f, (1, 1))                                           # mtime năm 1970 → cũ
    k = m.Khoa(f, "sua-j", "P").lay(1)
    tt = json.loads(f.read_text(encoding="utf-8"))
    assert tt["pid"] == os.getpid() and tt["het_han"] == 180 and tt["viec"] == "sửa video"
    k.tha()
    assert not f.exists()


def test_nha_khoa_khong_nuot_loi(tmp_path):
    """Khoá bị người khác thay (mất nhịp tim → hết hạn) → không xoá, báo lỗi + cảnh báo, không im lặng."""
    f = tmp_path / ".render.lock"
    k = m.Khoa(f, "sua-j", "P").lay(1)
    f.write_text(json.dumps({"batch": "khac", "pid": 99999}), encoding="utf-8")
    cb: list[str] = []
    m.tha_khoa([k], cb)
    assert f.exists() and cb and "tiến trình khác" in cb[0]
    k2 = m.Khoa(tmp_path / "b.lock", "sua-j", "P").lay(1)
    (tmp_path / "b.lock").unlink()
    with pytest.raises(RuntimeError):
        k2.tha()


# ---------------- (8) file đang mở → mã 3 trước khi render ----------------

def test_8_file_dang_mo_ma_3_truoc_render(du_an_c, moi_truong, capsys, eng, monkeypatch):
    p = du_an_c
    f = p / "output_poster" / TEN_C
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    goi: list = []
    monkeypatch.setattr(eng.render, "render_single_plan", _gia_render(eng, lambda: goi.append(1) or (False, "x")))
    with open(f, "rb"):
        rc = m.main(_argv(p, "output_poster", TEN_C, ban_f))
    assert rc == 3 and not goi
    assert "đang được mở" in _ket_qua(capsys)["ly_do"]
    assert f.is_file() and not f.with_name(f.name + ".thu-khoa").exists()
    assert not (p / "output_poster" / "_sua").exists()


# ---------------- phụ: chạy khô, engine đổi, video đã đổi ----------------

def test_xem_khong_ghi_gi(du_an_c, moi_truong, capsys):
    p = du_an_c
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, phu_de=[{"i": 1, "text": "mua liền kẻo hết"}],
                    doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    truoc = sorted((x.relative_to(p).as_posix(), x.stat().st_mtime_ns) for x in p.rglob("*"))
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f, xem=True)) == 0
    kq = _ket_qua(capsys)
    assert kq["trang_thai"] == "xem" and kq["tom_tat"] == {"so_cau": 1, "so_clip": 1, "so_doi_cho": 0}
    assert sorted((x.relative_to(p).as_posix(), x.stat().st_mtime_ns) for x in p.rglob("*")) == truoc


def test_engine_doi_chu_ky_ma_2(du_an_c, moi_truong, capsys, monkeypatch):
    p = du_an_c
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    can = dict(m.CHU_KY_CAN)
    can[("render", "render_single_plan")] = can[("render", "render_single_plan")] | {"tham_so_khong_co"}
    monkeypatch.setattr(m, "CHU_KY_CAN", can)
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 2
    assert "Engine đổi phiên bản" in _ket_qua(capsys)["ly_do"]


def test_video_doi_sau_khi_sua_ma_2(du_an_c, moi_truong, capsys):
    p = du_an_c
    f = p / "output_poster" / TEN_C
    ban_f, ban = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    ban["sua_luc"] -= 1000
    ban_f.write_text(json.dumps(ban), encoding="utf-8")
    cu = _st(f)
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 2
    assert "đã đổi" in _ket_qua(capsys)["ly_do"]
    assert _st(f) == cu


def test_doi_clip_trung_ledger_ma_2(du_an_c, moi_truong, capsys):
    """§5.4: bản mới trùng ≥ 4 s với bản trong ledger (đường dẫn cũ, so theo TÊN file) → mã 2, không đổi gì."""
    p = du_an_c
    d = p / "output_poster"
    # bản cũ trong ledger (đường dẫn gốc khác): cùng take, đúng dàn cảnh mà bản sửa sẽ tạo ra → trùng 6 s
    (d / "ledger.json").write_text(json.dumps({"plans": [{
        "plan_id": 7, "take_path": r"Z:\khac\takes\take01.mp4", "duration": 6.0,
        "ovls": [[0.5, 2.5, rf"Z:\khac\cuts\{CLIP[2]}", 0.0], [3.0, 5.0, rf"Z:\khac\cuts\{CLIP[1]}", 0.0]]}]}),
        encoding="utf-8")
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 1, "clip": CLIP[2]}])
    cu = _st(d / TEN_C)
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 2
    assert "trùng" in _ket_qua(capsys)["ly_do"]
    assert _st(d / TEN_C) == cu


# ---------------- R-20 P1-1: chạy tiếp việc hỏng KHÔNG hoàn nguyên đè lên việc sau ----------------

def _anh_chup(p: Path) -> dict:
    """Trạng thái các thứ hoan_nguyen có thể đụng: phụ đề, .sua.srt, .done.json, video."""
    d = p / "output_poster"
    take = p / "takes" / "take01.mp4"
    srt = take.with_suffix(".sua.srt")
    return {"sub": (p / "takes" / "take01.subtitles.json").read_bytes(),
            "srt": srt.read_bytes() if srt.exists() else None,
            "done": (d / "50oto2809_000.done.json").read_bytes() if (d / "50oto2809_000.done.json").exists() else None,
            "video": _st(d / TEN_C)}


def test_p1_1_viec_hong_chay_tiep_khong_de_viec_sau(du_an_c, moi_truong, capsys, eng, monkeypatch):
    """J1 dựng hỏng (buoc=hoan_nguyen) → J2 cùng video xong → chạy tiếp J1: dữ liệu của J2 còn nguyên."""
    p = du_an_c
    d = p / "output_poster"
    that = eng.render.render_single_plan
    ban1, _ = _ban(p, "output_poster", TEN_C, moi_truong, phu_de=[{"i": 0, "text": "Cho nha cái này xịn lắm"}])
    monkeypatch.setattr(eng.render, "render_single_plan", _gia_render(eng, lambda: (False, "giả lỗi")))
    assert m.main(_argv(p, "output_poster", TEN_C, ban1)) == 4
    assert sv.doc_nhat_ky(d / "_sua" / f"{VIEC}.json")["buoc"] == "hoan_nguyen"
    monkeypatch.setattr(eng.render, "render_single_plan", that)
    ban2, _ = _ban(p, "output_poster", TEN_C, moi_truong, phu_de=[{"i": 1, "text": "mua liền kẻo hết"}])
    assert m.main(_argv(p, "output_poster", TEN_C, ban2, viec=VIEC2)) == 0, capsys.readouterr()
    j2 = _anh_chup(p)
    assert j2["srt"] is not None and j2["done"] is not None
    capsys.readouterr()
    rc = m.main(_argv(p, "output_poster", TEN_C, ban1))          # "Chạy tiếp" J1
    assert rc != 0
    assert _anh_chup(p) == j2                                    # phụ đề / .sua.srt / .done.json / video của J2


def test_p1_1_chay_tiep_sau_hoan_nguyen_khong_ai_doi_thi_lam_lai(du_an_c, moi_truong, capsys, eng, monkeypatch):
    """Nhật ký đã hoan_nguyen, không ai đổi gì → chạy tiếp dựng lại từ đầu, xong mã 0."""
    p = du_an_c
    that = eng.render.render_single_plan
    ban1, _ = _ban(p, "output_poster", TEN_C, moi_truong, phu_de=[{"i": 1, "text": "mua liền kẻo hết"}])
    monkeypatch.setattr(eng.render, "render_single_plan", _gia_render(eng, lambda: (False, "giả lỗi")))
    assert m.main(_argv(p, "output_poster", TEN_C, ban1)) == 4
    monkeypatch.setattr(eng.render, "render_single_plan", that)
    assert m.main(_argv(p, "output_poster", TEN_C, ban1)) == 0, capsys.readouterr()
    sub = json.loads((p / "takes" / "take01.subtitles.json").read_text(encoding="utf-8"))
    assert "liền" in " ".join(s["text"] for s in sub["sentences"])


def test_p1_1_chet_sau_khi_thay_video_chay_tiep_khong_de_video_moi(du_an_c, moi_truong, capsys, eng, monkeypatch):
    """J1 chết ở bước render SAU khi engine đã thay video (nhật ký còn 'render') → J2 xong → chạy tiếp J1:
    không đưa bản V0 đè video của J2, không chép .done.json cũ đè; trả mã lỗi + cảnh báo."""
    p = du_an_c
    d = p / "output_poster"
    ban1, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    ghi_that, hn_that = m.PhienSua.ghi, m.PhienSua.hoan_nguyen

    def ghi(self, buoc=None):
        if buoc == "thay":
            raise OSError("giả mất điện sau khi thay video")
        return ghi_that(self, buoc)

    def chet(self):
        raise OSError("tiến trình đã chết")
    monkeypatch.setattr(m.PhienSua, "ghi", ghi)
    monkeypatch.setattr(m.PhienSua, "hoan_nguyen", chet)
    assert m.main(_argv(p, "output_poster", TEN_C, ban1)) == 5
    assert sv.doc_nhat_ky(d / "_sua" / f"{VIEC}.json")["buoc"] == "render"
    monkeypatch.setattr(m.PhienSua, "ghi", ghi_that)
    monkeypatch.setattr(m.PhienSua, "hoan_nguyen", hn_that)
    ban2, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 1, "clip": CLIP[2]}])
    assert m.main(_argv(p, "output_poster", TEN_C, ban2, viec=VIEC2)) == 0, capsys.readouterr()
    j2 = _anh_chup(p)
    capsys.readouterr()
    rc = m.main(_argv(p, "output_poster", TEN_C, ban1))
    kq = _ket_qua(capsys)
    assert _anh_chup(p) == j2
    assert rc == 5, kq
    assert any("bỏ qua" in x for x in kq["canh_bao"]), kq
    nk = sv.doc_nhat_ky(d / "_sua" / f"{VIEC}.json")
    assert nk["hoan_nguyen_bo_qua"]
    assert m.main(_argv(p, "output_poster", TEN_C, ban1)) == 5   # chạy tiếp lần nữa: vẫn dừng, không làm lại
    assert _anh_chup(p) == j2


# ---------------- R-20 P2-1: mẻ mới ghi lại render_batch.json (plan_id trùng) → không cấy plan sửa ----------------

def test_p2_1_nguon_doi_mtime_khong_cay_plan(du_an_c, moi_truong, capsys, monkeypatch):
    p = du_an_c
    rb = p / "output_poster" / "render_batch.json"
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    that = m.PhienSua.buoc_nguon

    def ngat(self):
        self.ghi("nguon")
        raise OSError("giả mất điện trước khi ghi nguồn")
    monkeypatch.setattr(m.PhienSua, "buoc_nguon", ngat)
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 5
    # mẻ `cli.py run` mới (không lấy khoá) ghi lại render_batch.json, plan_id trùng
    data = json.loads(rb.read_text(encoding="utf-8"))
    data["plans"][0]["seed"] = 999
    rb.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.utime(rb, ns=(rb.stat().st_atime_ns, rb.stat().st_mtime_ns + 5_000_000_000))
    me_moi = rb.read_bytes()
    monkeypatch.setattr(m.PhienSua, "buoc_nguon", that)
    capsys.readouterr()
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 0
    kq = _ket_qua(capsys)
    assert rb.read_bytes() == me_moi                             # không cấy plan sửa vào mẻ mới
    assert any("render_batch.json đã đổi" in x for x in kq["canh_bao"]), kq


def test_p2_1_luong_c_chay_lai_nguon_da_ghi(du_an_c, moi_truong, capsys, monkeypatch):
    p = du_an_c
    rb = p / "output_poster" / "render_batch.json"
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    that = m.PhienSua.buoc_lien_ket

    def ngat(self):
        raise OSError("giả mất điện sau khi ghi nguồn")
    monkeypatch.setattr(m.PhienSua, "buoc_lien_ket", ngat)
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 5
    nk_f = p / "output_poster" / "_sua" / f"{VIEC}.json"
    nk = json.loads(nk_f.read_text(encoding="utf-8"))
    nk["buoc"] = "nguon"                                         # giả chết ngay sau write_json, trước khi ghi nhật ký
    nk["nguon"].pop("mtime_ns_sau", None)
    nk_f.write_text(json.dumps(nk, ensure_ascii=False), encoding="utf-8")
    sau = rb.read_bytes()
    monkeypatch.setattr(m.PhienSua, "buoc_lien_ket", that)
    capsys.readouterr()
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 0
    kq = _ket_qua(capsys)
    assert not any("đã đổi" in x for x in kq["canh_bao"]), kq
    assert json.loads(rb.read_bytes())["plans"][0]["segments"][2]["clip"] == CLIP[2]
    assert json.loads(rb.read_bytes()) == json.loads(sau)


# ---------------- R-20 P2-3: gỡ khoá cũ không xoá nhầm khoá mới ----------------

def test_p2_3_go_khoa_cu_khong_xoa_khoa_moi(tmp_path, monkeypatch):
    f = tmp_path / ".render.lock"
    f.write_text(json.dumps({"batch": "cu", "pid": 1, "het_han": 180}), encoding="utf-8")
    os.utime(f, (1, 1))
    moi = json.dumps({"batch": "moi", "pid": 4242, "het_han": 180}).encode()
    cu_that = m.Khoa._cu
    lan = []

    def cu(self):
        kq = cu_that(self)
        if not lan:                                               # đúng giữa lúc thấy cũ và lúc gỡ: tiến trình khác
            lan.append(1)                                         # gỡ khoá cũ và lấy khoá mới
            f.unlink()
            f.write_bytes(moi)
        return kq
    monkeypatch.setattr(m.Khoa, "_cu", cu)
    with pytest.raises(m.Thoat) as ex:
        m.Khoa(f, "sua-j", "P").lay(0.3)
    assert ex.value.ma == 3
    assert f.read_bytes() == moi                                  # khoá mới còn nguyên
    assert sorted(x.name for x in tmp_path.iterdir()) == [".render.lock"]


# ---------------- R-20 P3-2: hằng engine thiếu → mã 2 ----------------

def test_p3_2_thieu_ngon_ngu_mac_dinh_ma_2(du_an_c, moi_truong, capsys, eng, monkeypatch):
    p = du_an_c
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, phu_de=[{"i": 1, "text": "mua liền kẻo hết"}])
    monkeypatch.delattr(eng.sjb, "NGON_NGU_MAC_DINH")
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 2
    assert "Engine đổi phiên bản" in _ket_qua(capsys)["ly_do"]


# ---------------- FX-21: hoàn tác chỉ áp lên đúng bản lần sửa đó tạo ra ----------------

def _argv_ht(p: Path, ten: str = TEN_C, viec_goc: str = VIEC, viec: str = VIEC2, thu_muc: str = "output_poster"):
    return ["hoan-tac", "--project", str(p), "--thu-muc", thu_muc, "--video", ten, "--viec-goc", viec_goc,
            "--viec", viec]


def _anh_chup_ht(p: Path) -> dict:
    """Mọi thứ hoàn tác có thể đụng (luồng C): video, .done.json, render_batch.json, plan.json, phụ đề, .sua.srt."""
    d = p / "output_poster"
    pj = d / "plan.json"
    return {**_anh_chup(p), "rb": (d / "render_batch.json").read_bytes(),
            "pj": pj.read_bytes() if pj.exists() else None}


def test_fx21_done_json_moi_hon_tu_choi(du_an_c, moi_truong, capsys):
    """Sửa lần 1 xong → mẻ engine ghi lại .done.json của V (video giữ nguyên) → hoàn tác lần 1: mã 2, không đè gì."""
    p = du_an_c
    done = p / "output_poster" / "50oto2809_000.done.json"
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 0, capsys.readouterr()
    d = json.loads(done.read_text(encoding="utf-8"))
    d["key"] = "khoa-cua-me-moi"
    done.write_text(json.dumps(d), encoding="utf-8")
    truoc = _anh_chup_ht(p)
    capsys.readouterr()
    assert m.main(_argv_ht(p)) == 2
    kq = _ket_qua(capsys)
    assert ".done.json" in kq["ly_do"] and "mới hơn" in kq["ly_do"], kq
    assert _anh_chup_ht(p) == truoc


def test_fx21_sua_lan_2_xong_hoan_tac_lan_1_tu_choi(du_an_c, moi_truong, capsys):
    """Kịch bản phiếu: V sửa lần 1, rồi sửa lần 2 xong → hoàn tác lần 1: mã 2, bản của lần 2 còn nguyên."""
    p = du_an_c
    ban1, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    assert m.main(_argv(p, "output_poster", TEN_C, ban1)) == 0, capsys.readouterr()
    ban2, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[1]}])
    assert m.main(_argv(p, "output_poster", TEN_C, ban2, viec=VIEC2)) == 0, capsys.readouterr()
    truoc = _anh_chup_ht(p)
    capsys.readouterr()
    assert m.main(_argv_ht(p, viec="j20261117140000ab03")) == 2
    assert _anh_chup_ht(p) == truoc


def test_fx21_render_batch_me_moi_tu_choi(du_an_c, moi_truong, capsys):
    """Mẻ mới ghi lại render_batch.json (plan_id trùng, video chưa dựng lại) → hoàn tác: mã 2, không cấy plan cũ."""
    p = du_an_c
    rb = p / "output_poster" / "render_batch.json"
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 0, capsys.readouterr()
    data = json.loads(rb.read_text(encoding="utf-8"))
    data["plans"][0]["seed"] = 999
    rb.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    truoc = _anh_chup_ht(p)
    capsys.readouterr()
    assert m.main(_argv_ht(p)) == 2
    assert "render_batch.json" in _ket_qua(capsys)["ly_do"]
    assert _anh_chup_ht(p) == truoc


def test_fx21_plan_json_doi_tu_choi(du_an_c, moi_truong, capsys):
    p = du_an_c
    d = p / "output_poster"
    rb = json.loads((d / "render_batch.json").read_text(encoding="utf-8"))
    pj = d / "plan.json"
    pj.write_text(json.dumps([{"plan_id": f"plan_{x['plan_id']:03d}", "segments": x["segments"]}
                              for x in rb["plans"]], indent=2), encoding="utf-8")
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 0, capsys.readouterr()
    ds = json.loads(pj.read_text(encoding="utf-8"))
    assert ds[0]["segments"][2]["clip"] == CLIP[2]
    ds[0]["segments"] = ds[0]["segments"][:1]                    # pipeline lập plan mới cho plan_000
    pj.write_text(json.dumps(ds, indent=2), encoding="utf-8")
    truoc = _anh_chup_ht(p)
    capsys.readouterr()
    assert m.main(_argv_ht(p)) == 2
    assert "plan.json" in _ket_qua(capsys)["ly_do"]
    assert _anh_chup_ht(p) == truoc


def test_fx21_plan_json_khop_thi_khoi_phuc(du_an_c, moi_truong, capsys):
    p = du_an_c
    d = p / "output_poster"
    rb = json.loads((d / "render_batch.json").read_text(encoding="utf-8"))
    pj = d / "plan.json"
    pj.write_text(json.dumps([{"plan_id": f"plan_{x['plan_id']:03d}", "segments": x["segments"]}
                              for x in rb["plans"]], indent=2), encoding="utf-8")
    goc = json.loads(pj.read_text(encoding="utf-8"))
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 0, capsys.readouterr()
    capsys.readouterr()
    assert m.main(_argv_ht(p)) == 0, capsys.readouterr()
    assert json.loads(pj.read_text(encoding="utf-8")) == goc


def test_fx21_phu_de_take_sua_tiep_bo_qua_ma_5(du_an_c, moi_truong, capsys):
    """V sửa chữ (J1) → video khác cùng take sửa chữ tiếp (J2) → hoàn tác J1: video V về bản cũ, phụ đề + .sua.srt
    của J2 giữ nguyên, ghi hoan_tac_bo_qua, mã 5; chạy lại vẫn mã 5, không làm lại."""
    p = du_an_c
    d = p / "output_poster"
    ten2 = "50oto2809_001.mp4"
    cu = _st(d / TEN_C)
    ban1, _ = _ban(p, "output_poster", TEN_C, moi_truong, phu_de=[{"i": 0, "text": "Cho nha cái này xịn lắm"}])
    assert m.main(_argv(p, "output_poster", TEN_C, ban1)) == 0, capsys.readouterr()
    ban2, _ = _ban(p, "output_poster", ten2, moi_truong, phu_de=[{"i": 1, "text": "mua liền kẻo hết"}])
    assert m.main(_argv(p, "output_poster", ten2, ban2, viec=VIEC2)) == 0, capsys.readouterr()
    sau_j2 = _anh_chup(p)
    rb_j2 = json.loads((d / "render_batch.json").read_text(encoding="utf-8"))
    capsys.readouterr()
    viec3 = "j20261117140000ab03"
    assert m.main(_argv_ht(p, viec=viec3)) == 5
    kq = _ket_qua(capsys)
    assert any("bỏ qua" in x for x in kq["canh_bao"]), kq
    now = _anh_chup(p)
    assert now["sub"] == sau_j2["sub"] and now["srt"] == sau_j2["srt"]
    assert _st(d / TEN_C) == cu
    assert json.loads((d / "render_batch.json").read_text(encoding="utf-8"))["plans"][1] == rb_j2["plans"][1]
    nk = sv.doc_nhat_ky(d / "_sua" / f"{viec3}.json")
    assert nk["hoan_tac_bo_qua"]
    lan1 = _anh_chup_ht(p)
    assert m.main(_argv_ht(p, viec=viec3)) == 5
    assert _anh_chup_ht(p) == lan1


def test_fx21_hoan_tac_ngat_giua_chay_lai_lam_not(du_an_c, moi_truong, capsys, monkeypatch):
    """Hoàn tác chết sau khi đã khôi phục bản ghi nguồn → chạy lại: nhận ra mục đã về bản cũ, làm nốt, mã 0."""
    p = du_an_c
    d = p / "output_poster"
    sub = p / "takes" / "take01.subtitles.json"
    sub_goc, done_goc, rb_goc = sub.read_bytes(), (d / "50oto2809_000.done.json").read_bytes(), \
        json.loads((d / "render_batch.json").read_text(encoding="utf-8"))
    cu = _st(d / TEN_C)
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, phu_de=[{"i": 0, "text": "Cho nha cái này xịn lắm"}],
                    doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 0, capsys.readouterr()
    that = m._khoi_phuc_phu_de

    def chet(*a, **k):
        raise OSError("giả mất điện giữa hoàn tác")
    monkeypatch.setattr(m, "_khoi_phuc_phu_de", chet)
    assert m.main(_argv_ht(p)) == 5
    monkeypatch.setattr(m, "_khoi_phuc_phu_de", that)
    capsys.readouterr()
    assert m.main(_argv_ht(p)) == 0, capsys.readouterr()
    assert _st(d / TEN_C) == cu and sub.read_bytes() == sub_goc
    assert not (p / "takes" / "take01.sua.srt").exists()
    assert (d / "50oto2809_000.done.json").read_bytes() == done_goc
    assert json.loads((d / "render_batch.json").read_text(encoding="utf-8"))["plans"][0] == rb_goc["plans"][0]


def test_fx21_luong_a_plan_doi_tu_choi(du_an_a, moi_truong, capsys):
    p = du_an_a
    ten = f"{ME}_{MA_A}.mp4"
    pf = p / "output_daonguoc" / f"{ME}_plan.json"
    ban_f, _ = _ban(p, "output_poster", ten, moi_truong, doi_clip=[{"seg": 1, "clip": CLIP[2]}])
    assert m.main(_argv(p, "output_poster", ten, ban_f)) == 0, capsys.readouterr()
    data = json.loads(pf.read_text(encoding="utf-8"))
    data[0]["seed"] = 999                                         # mẻ Adam lập lại plan cho mã này
    ns = pf.stat().st_mtime_ns
    pf.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.utime(pf, ns=(ns, ns))
    truoc = (pf.read_bytes(), _st(p / "output_daonguoc" / ten), _st(p / "output_poster" / ten))
    capsys.readouterr()
    assert m.main(_argv_ht(p, ten=ten)) == 2
    assert pf.name in _ket_qua(capsys)["ly_do"]
    assert (pf.read_bytes(), _st(p / "output_daonguoc" / ten), _st(p / "output_poster" / ten)) == truoc


def test_fx21_luong_a_hoan_tac_xong(du_an_a, moi_truong, capsys):
    p = du_an_a
    ten = f"{ME}_{MA_A}.mp4"
    goc, lk = p / "output_daonguoc" / ten, p / "output_poster" / ten
    pf = p / "output_daonguoc" / f"{ME}_plan.json"
    pf_goc, cu = json.loads(pf.read_text(encoding="utf-8")), _st(goc)
    ban_f, _ = _ban(p, "output_poster", ten, moi_truong, doi_clip=[{"seg": 1, "clip": CLIP[2]}])
    assert m.main(_argv(p, "output_poster", ten, ban_f)) == 0, capsys.readouterr()
    capsys.readouterr()
    assert m.main(_argv_ht(p, ten=ten)) == 0, capsys.readouterr()
    assert _st(goc) == cu and os.path.samefile(goc, lk)
    assert json.loads(pf.read_text(encoding="utf-8")) == pf_goc


def test_fx21_nhat_ky_cu_khong_dau_done(du_an_c, moi_truong, capsys):
    """Nhật ký lần sửa kiểu cũ (không done_truoc/done_sau): .done.json nhận bằng trường `output` = video lần sửa dựng.
    Bị ghi lại (output khác) → mã 2; đúng của lần sửa → hoàn tác xong, .done.json cũ trở lại."""
    p = du_an_c
    d = p / "output_poster"
    done = d / "50oto2809_000.done.json"
    done_goc = done.read_bytes()
    ban_f, _ = _ban(p, "output_poster", TEN_C, moi_truong, doi_clip=[{"seg": 2, "clip": CLIP[2]}])
    assert m.main(_argv(p, "output_poster", TEN_C, ban_f)) == 0, capsys.readouterr()
    nk_f = d / "_sua" / f"{VIEC}.json"
    nk = json.loads(nk_f.read_text(encoding="utf-8"))
    nk.pop("done_truoc"), nk.pop("done_sau")
    nk_f.write_text(json.dumps(nk, ensure_ascii=False), encoding="utf-8")
    cua_j1 = done.read_bytes()
    dd = json.loads(cua_j1)
    dd["output"] = [dd["output"][0], dd["output"][1] + 1, dd["output"][2]]
    done.write_text(json.dumps(dd), encoding="utf-8")
    truoc = _anh_chup_ht(p)
    capsys.readouterr()
    assert m.main(_argv_ht(p)) == 2
    assert _anh_chup_ht(p) == truoc
    done.write_bytes(cua_j1)
    assert m.main(_argv_ht(p, viec="j20261117140000ab03")) == 0, capsys.readouterr()
    assert done.read_bytes() == done_goc


def test_fx21_lien_ket_ban_chep_da_thay_khong_de(mau_a, moi_truong, capsys):
    """output_poster giữ BẢN CHÉP (không phải hardlink). Sau lần sửa, bản chép bị thay bằng file khác → hoàn tác
    đưa video gốc về nhưng KHÔNG chép đè bản trong output_poster, có cảnh báo."""
    p = _chep(mau_a, moi_truong / "du_an")
    ten = f"{ME}_{MA_A}.mp4"
    goc, lk = p / "output_daonguoc" / ten, p / "output_poster" / ten
    lk.parent.mkdir()
    shutil.copy2(goc, lk)
    ban_f, _ = _ban(p, "output_poster", ten, moi_truong, doi_clip=[{"seg": 1, "clip": CLIP[2]}])
    assert m.main(_argv(p, "output_poster", ten, ban_f)) == 0, capsys.readouterr()
    assert lk.read_bytes() == goc.read_bytes() and not os.path.samefile(goc, lk)
    lk.write_bytes(b"ban khac do nguoi dung dat vao")
    capsys.readouterr()
    rc = m.main(_argv_ht(p, ten=ten))
    kq = _ket_qua(capsys)
    assert lk.read_bytes() == b"ban khac do nguoi dung dat vao"
    assert any("không nối lại" in x for x in kq["canh_bao"]), kq
    assert rc == 0, kq


def test_ky_hieu_ten_bo_duong_dan():
    kh = m._ky_hieu_ten({"plan_id": "plan_003", "duration": 6, "segments": [
        {"kind": "BASE", "out_start": 0, "out_end": 6, "src": r"E:\cu\takes\t.mp4", "src_start": 0},
        {"kind": "OVL", "out_start": 1, "out_end": 3, "src": r"E:\cu\cuts\a.mp4", "src_start": 0.5}]})
    assert kh == {"plan_id": 3, "take_path": "t.mp4", "duration": 6.0, "ovls": [[1.0, 3.0, "a.mp4", 0.5]]}
