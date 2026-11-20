# Sửa video trên web Kho (đợt 6)

Phiếu A-06 · Kiến trúc sư Culiapp · 2026-11-17
Trạng thái: **ĐỀ XUẤT, chờ người dùng duyệt**. Quyết định mới: **D10** trong `DECISIONS.md` (Đề xuất). Dùng lại khung của `docs/bo-chay-viec.md` §2–§8: đường vào D2, danh mục cố định D3, chữ ký D7, bản cài D8.

Tri thức đã đọc: `DECISIONS.md` D1–D9, `docs/bo-chay-viec.md`. Không có `CLAUDE.md`, `ARCHITECTURE.md`, `KNOWN_BUGS.md` ở gốc repo hay thư mục cha. Engine `F:\auto video oneshot` **không phải repo git** (`git rev-parse` báo "not a git repository").

---

## 0. Tóm tắt một màn hình

- Trong tab ✅ Duyệt, mỗi video có thêm nút **✏ Sửa**. Nút mở màn `#/sua/<uid>/<ma_video>` (dùng được trên điện thoại) với hai thẻ:
  - **Phụ đề**: hiện từng câu kèm giờ, sửa chữ ngay tại chỗ;
  - **Cảnh**: dòng thời gian các đoạn. Bấm một đoạn phủ (OVL) để xem các clip cùng vai trong `cuts/` (ảnh khung + nút ▶ xem thử) rồi chọn. Có thêm "đổi chỗ hai cảnh". **Không** có cắt hay kéo giãn đoạn.
- Bấm **Lưu và dựng lại**:
  1. Worker lưu "bản sửa" lên runner (chỉ dữ liệu, không đường dẫn, không lệnh);
  2. Worker tạo việc `sua_video` (miễn phí, làn `gpu`);
  3. Runner gọi **bộ chuyển đổi** `sua_video_engine.py` bằng Python của engine. Bộ này áp bản sửa, dựng lại **đúng 1 video** (NVENC khoảng 12 s), sao lưu bản cũ, ghi nhật ký, cập nhật bản ghi nguồn để lệnh "chạy tiếp" của engine không ghi đè bản sửa, rồi nối lại liên kết trong `output_poster`.
- **Không sửa engine** (D10, phương án A). Bộ chuyển đổi nằm trong bản cài runner và gọi các hàm engine có sẵn: `render_single_plan`, `dung_hau_ky_cho_plan`, `build_subtitle_json`, `mach_trung_voi_lich_su`. Đây cũng là cách cầu nối Adam đang làm: `autovideo_audio_take.py:4` ghi "Engine không sửa gì". Muốn thêm lệnh vào engine thì là phương án B (§6.8), phải hỏi người dùng.
- **Hoàn tác** là một việc `hoan_tac_sua`: đưa bản cũ trở lại từ `_sua_cu/`. Chỉ đè đúng thứ lần sửa đó ghi; đã có bản mới hơn thì từ chối (mã 2), phụ đề của take đã bị sửa tiếp thì giữ nguyên và báo "kiểm tay" (mã 5). Xem §6.4 (cập nhật 18/11, phiếu A-DOC2).
- Video dựng lại có `sua_luc` mới. Theo khoá duyệt hiện có (`cf/src/worker.js:206`, `web/app.js:540`), video đó tự trở về "Chưa duyệt", người dùng phải duyệt lại.

---

## 1. Hiện trạng đã kiểm (bằng chứng)

### 1.1 Web Kho, Worker, máy nhà

| Điều | Bằng chứng |
|---|---|
| Tab Duyệt chỉ liệt kê `<GOC>/*<id>/output_poster/*.mp4` và `.../output/*.mp4` (không đệ quy). Chuỗi `goc` là `GOC` (với output_poster) hoặc `GOC#<thư mục>/output` | `tools/video_server.py:41`, `:106-116` |
| Web tạo thẻ Duyệt từ `may.ds.nguon[].chi_tiet[]` với khoá `(goc, ten, sua_luc)`; phát video bằng `/api/video/<id>/xem?goc&ten` | `web/app.js:525-538`, `:540`, `:596-601` |
| Duyệt lưu ở `data/<id>/duyet.json`, khoá theo `(goc, ten, sua_luc)`; file dựng lại có `sua_luc` khác nên phải duyệt lại | `cf/src/worker.js:206-219`, `:739-757` |
| Proxy video: act cho phép và query từng act; act `xem`/`file` là stream, không đặt timeout | `cf/src/worker.js:186-191`, `:690-716`; `tools/video_server.py:297` |
| Route `/api/viec*`: bảng `tuyenViec`, Origin bắt buộc với POST, ký mọi POST | `cf/src/worker.js:467-482`, `:636-662` |
| video_server lọc `/r/*` bằng `RE_R`, khoá query `R_QUERY_KHOA` | `tools/video_server.py:128-130` |
| Runner: định tuyến GET/POST, POST kiểm chữ ký | `tools/runner/api.py:629-676` |
| `LoaiViec`, `DANH_MUC`; `dot_bat` hiện là 4 | `tools/runner/danh_muc.py:143-164`, `:745`; `tools/runner/han_muc.py:19` |
| Schema DB hiện là `"2"` | `tools/runner/kho_viec.py:27` |
| `ma_du_an = sha1(posix)[:12]`, `ds_du_an`, `tim_du_an` | `tools/runner/du_an.py:39`, `:73`, `:79` |
| `MoiTruong.ffmpeg_ngoai` (có ffmpeg ngoài cây runner) | `tools/runner/kieu.py:104`; `tools/runner/vong_lap.py:433` |
| `cai_runner.py` chép mọi `tools/runner/*.py` (trừ `test_*`, `spike_*`), nên file mới vào bản cài mà không phải sửa trình cài | `tools/cai_runner.py:8`, `:40`, `:70` |
| Router web, thẻ script | `web/app.js:778-792`; `web/index.html:8-12` |

### 1.2 Engine và hai luồng dựng

| Điều | Bằng chứng | Hệ quả cho thiết kế |
|---|---|---|
| `cli.py render` chỉ chạy tiếp `output\render_batch.json`; không có lệnh dựng 1 video | `F:\auto video oneshot\cli.py:441-458` | Cần đường dựng 1 bản (§6) |
| `cli.py` import `pipeline_runner` ngay đầu file (nặng) | `cli.py:52-60` | Các API đọc không đi qua engine (§3) |
| `render_batch.json` = `{version, plans:[asdict], options, config}`, ghi đè **mỗi lần** `render_batch_plans` chạy trong thư mục đó | `modules/render_checkpoint.py:85-103`; `modules/render.py:1094-1099` | Mỗi thư mục chỉ còn bản ghi của mẻ **cuối** |
| Tên file `<prefix>_<plan_id:03d>.mp4`, với prefix = `plan.output_prefix` → `cfg.prefix` → `image_options.prefix` | `modules/render.py:768-769` | Ánh xạ tên file → plan (luồng C) |
| `.done.json` = `{key, output:[path,size,mtime_ns]}`. Bỏ qua render khi key và chữ ký khớp. Key gồm lệnh ffmpeg và chữ ký file nguồn (`-i`, ass, wm, dcl) | `modules/render.py:911-921`, `:1029-1030`; `modules/render_checkpoint.py:24-49` | Sửa mà không cập nhật `render_batch.json` thì lần `render` (chạy tiếp) sau sẽ **dựng lại bản cũ, đè mất bản sửa** |
| Render ghi vào thư mục tạm, kiểm `verify_video`, rồi `os.replace` vào chỗ thật | `modules/render.py:926-1031` | `os.replace` tạo inode mới, làm gãy hardlink |
| Tự sửa đường dẫn clip lệch chỉ áp cho `cuts/` | `modules/render.py:796-811` | Đường dẫn take/hậu kỳ cũ phải tự đổi gốc |
| **Đường dẫn tuyệt đối đã cũ trong dữ liệu thật**: `E:\oneshottramcanh\50oto 1736818222555104357\output_poster\render_batch.json` có `take_path = E:\oneshottramcanh\50oto\takes\...` và `ass_path = ...\50oto\output\hau_ky\plan_000.ass`. Thư mục đã đổi tên và `output` đã thành `output_poster` | đọc file (chỉ đọc) | Bắt buộc đổi gốc đường dẫn (§3.4) và dựng lại hậu kỳ |
| `TimelinePlan` và `Seg` (các trường) | `modules/timeline.py:308-325`, `:333-370` | |
| `to_dict()` (`plan.json`, `<B>_plan.json`) **không có** `take_path`, `ass_path`, `wm_file` | `modules/timeline.py:372-391` | Luồng A lấy take từ segment BASE; hậu kỳ luôn dựng lại |
| Hậu kỳ: `.ass` riêng mỗi bản tại `<out>/hau_ky/plan_NNN.ass`, rng = `plan.seed` | `modules/hau_ky.py:125-191`, `:169-171` | Dựng lại `.ass` cùng seed thì giữ được độ "rung" chữ như cũ |
| Cách pipeline gọi hậu kỳ: wm/dcl từ `load_wm_from_project`, `sub_cfg`, cờ cart/sticker/punch | `modules/pipeline_runner.py:1348-1362`, `:1405-1442`; `modules/wm_settings.py:176` | Bộ chuyển đổi gọi y như vậy |
| Phụ đề biến thể (`pick_variation_for`) khi `variation_enabled` và `reuse_count ≥ 2` | `modules/pipeline_runner.py:1390-1424`; `modules/subtitle_json_builder.py:1527` | Video dùng biến thể: chưa cho sửa phụ đề |
| Nguồn chữ phụ đề theo thứ tự ưu tiên `.sua.srt` > `.script.txt` > `.agent_proofread.txt` > Whisper thô | `modules/subtitle_json_builder.py:903-957` | Sửa từng câu → ghi `.sua.srt` |
| Dựng phụ đề 1 take: `build_subtitle_json(take_path, take_idx=…)`. `run_subtitle_pipeline` quét **cả thư mục** | `modules/subtitle_json_builder.py:1114-1123`, `:1235` | Chỉ dựng lại đúng take cần, không chạy cả thư mục |
| `words_from_srt` chia đều giờ trong mỗi cue rồi khớp với ASR | `modules/subtitle_align.py:205-217` | Giờ của từ vẫn lấy theo Whisper, chỉ chữ đổi |
| Chống trùng: `ky_hieu_plan`, `mach_trung_voi_lich_su(plan, chu_ky_cu, nguong)` | `modules/anti_trung.py:276-311` | Kiểm khi đổi clip |
| `cuts\clip_index.json` = `{version, clips:{<tên file>: {role, slug, dur, desc, tags, is_visual_hook, raw, abs_start, abs_end…}}}`; ảnh `cuts\.index_frames\<clip_id>\f_NN.jpg` và `contact_sheet.jpg` | đọc `50oto …\cuts` (chỉ đọc) | Danh sách ứng viên và ảnh thu nhỏ |
| Skill: không sửa tay `plan.json`; không chạy thử `render` trên dự án thật | `autovideo-oneshot\SKILL.md:159`, `:165` | Bộ chuyển đổi chỉ sửa một bản ghi, có sao lưu; test chạy trên dự án tạm |

**Luồng A (Adam, `tao-video-tu-canh-quay`)**, file `C:\Users\Mi\.claude\skills\tao-video-tu-canh-quay\scripts\autovideo_audio_take.py`:

| Điều | Dòng |
|---|---|
| Take nằm ở `voice/_takes/<B>/<B>_<ma>.mp4`; video cuối `<out>/<stem take>.mp4`; `out` ∈ `output-adam`, `output_daonguoc` | `:103-112`, `:470`, `:1827` |
| Plan của mẻ: `<out>/<B>_plan.json` (danh sách `to_dict`) | `:1411`, `:1432` |
| Render ra `_tmp_<B>_NNN.mp4`, đổi tên sang `<B>_<ma>.mp4`, **xoá `.done.json`**, **xoá `_hau_ky/<B>`** | `:1400`, `:1476`, `:1494-1511` |
| Tham số render: `pad_or_crop="crop"`, `plan_mode="legacy"`, `burn_subtitle=True`, `cart_arrow_on=True`, `bgm_volume=a.bgm_volume`, `dissolve=a.dissolve` (mặc định 0.1), `sub_cfg` lấy từ `oneshot.json` | `:1465-1478`, `:1813-1817`, `:1544-1558` |
| Khoá render theo dự án `.render.lock` và khoá toàn máy `E:\oneshottramcanh\.render-may.lock` (file O_EXCL, JSON, nhịp tim 30 s, hết hạn 180 s) | `:477-489`, `:549-620`, `:1323-1349` |

**Gom Poster**, file `tao-video-tu-canh-quay\scripts\day_len_poster.py`:
- `output_poster/<B>_<ma>.mp4` là **hardlink** của bản trong `output_daonguoc`/`output-adam` (`:95-134`), lọc tên bằng `VIDEO_CUOI` (`:33`).
- Sổ `_da_gom.txt` chặn link lại tên đã đăng (`:87`, `:124`).
- Dựng lại bằng `os.replace` thì link trong `output_poster` **vẫn trỏ bản cũ**, nên Poster sẽ đăng bản cũ. Phải nối lại link (§6.5).

**Luồng C (giọng creator, `autovideo-oneshot`)** ghi thẳng vào thư mục output của engine. `_resolve_paths` chọn `compose_output` rồi tới `output` (`cli.py:156-158`). Dữ liệu thật cho thấy thư mục này có thể đã bị đổi tên thành `output_poster`.

---

## 2. Kiến trúc

```
Điện thoại: web/sua.js (màn #/sua/<uid>/<ma_video>) ← nút ✏ trong tab Duyệt (web/app.js)
   │ GET đọc / POST "luu" (+ mật khẩu nếu có sửa chữ, Q3)
   ▼
Worker cf/src/worker.js
   │ /api/viec/sua-video/*  → ký Ed25519 (D7) → video.kutidak.com/r/sua-video/*
   │ /api/video/<uid>/(anh|clip) → video.kutidak.com/v/<uid>/(anh|clip)  (ảnh khung, xem thử clip)
   ▼
tools/video_server.py  (/r/* chuyển tiếp theo D2; /v/* phục vụ file)
   ▼
Runner (bản cài D8) 127.0.0.1:8788
   ├─ sua_video.py         (MỚI, stdlib) tra cứu video→bản ghi, phụ đề, cảnh, ứng viên, kiểm bản sửa
   ├─ api.py               route /sua-video/*, bảng ban_sua (kho_viec.py)
   ├─ danh_muc.py          loại sua_video, hoan_tac_sua (làn gpu, miễn phí)
   └─ sua_video_engine.py  (MỚI) chạy bằng F:\auto video oneshot\.venv\Scripts\python.exe,
                           cwd = thư mục engine; import modules.* của engine; ghi file dự án
```

Ranh giới:
- **Core logic** (`sua_video.py`): thuần, không import engine, test bằng fixture JSON. `sua_video_engine.py` import lại module này để hai bên dùng chung một luật tra cứu.
- **Automation** (`sua_video_engine.py`): mọi việc ghi đĩa, khoá, render, thay file.
- **Giao diện**: `api.py`, Worker, `web/sua.js`.

Vì sao chia hai file: runner chạy bằng Python hệ thống (3.12, stdlib + psutil + cryptography) và phải trả lời GET dưới 10 s (`tools/video_server.py:127`). Import engine thì kéo theo faster-whisper và các thư viện khác, chậm và có thể lỗi DLL. Chỉ bước ghi mới cần engine.

---

## 3. Tra cứu: video trong tab Duyệt → dự án / mẻ / plan / đoạn

### 3.1 Định danh không có đường dẫn từ web

- Runner liệt kê video sửa được theo UID, dùng cùng `GOCS` và cùng định dạng chuỗi `goc` với video_server (`tools/video_server.py:115`, bản sao trong `du_an.py`). Web ghép với thẻ Duyệt theo `(goc, ten)` và nhận về `ma_video`.
- `ma_video = sha1(f"{ma_du_an}/{thu_muc}/{ten}")[:16]` (hex), với `thu_muc` ∈ {`output_poster`, `output`}. Mọi API sau đó chỉ nhận `uid` + `ma_video` (+ `du_an` khi tạo việc). Runner tự dò lại đường dẫn.
- Ràng buộc tên: `ten` khớp `^[0-9A-Za-z][0-9A-Za-z_.()\- ]{0,150}\.mp4$`, không có `/` hay `\`. Tên clip cũng dùng cùng mẫu này.

### 3.2 Luồng C: `render_batch.json` + `.done.json`

Video `D/<ten>` với `D` = `P/output` hoặc `P/output_poster`:
1. Có `D/render_batch.json`, `version == 1`.
2. Tính prefix theo đúng thứ tự `render.py:768`: `plan.output_prefix` → `config.prefix` → `config.image_options.prefix` → `"output"`. Tên phải khớp `^<prefix>_(\d{3})\.mp4$`. Tìm plan có `plan_id` bằng số đó.
3. **Chứng minh nguồn gốc**: có `D/<stem>.done.json`, và `output[1:] == [size, mtime_ns]` của file video hiện tại. Không so `output[0]` (đường dẫn), vì thư mục có thể đã đổi tên. Lệch hoặc thiếu → `sua_duoc=False`, lý do "Không chứng minh được video này sinh từ bản ghi còn lưu (có thể thuộc mẻ cũ hơn)".
4. Take = `plan.take_path` sau khi đổi gốc (§3.4). Phụ đề = `<take>.subtitles.json`.

### 3.3 Luồng A: `<B>_plan.json`

Video `P/output_poster/<ten>` hoặc `P/output/<ten>` mà tên khớp `^(\d{8}-[0-9A-Za-z-]+)_([a-z]+\d+)\.mp4$` (`day_len_poster.py:33`). Khi đó `B = nhóm 1`, `ma = nhóm 2`:
1. Tìm bản gốc `P/<out>/<ten>` với `out` ∈ (`output_daonguoc`, `output-adam`):
   - `os.path.samefile(video, bản gốc)` → `lien_ket` = video trong `output_poster`;
   - không cùng inode nhưng cùng `size` → vẫn nhận, kèm cảnh báo "bản trong output_poster là bản chép, sẽ chép lại".
2. Có `P/<out>/<B>_plan.json`. Lấy plan có segment `kind=="BASE"` với `Path(src).stem == f"{B}_{ma}"`.
3. `mtime(bản gốc) ≥ mtime(<B>_plan.json)` (video dựng sau khi chốt plan), sai thì từ chối.
4. Take = `src` của BASE (đổi gốc). Phụ đề = `<take>.subtitles.json` trong `voice/_takes/<B>/`.

### 3.4 Đổi gốc đường dẫn tuyệt đối

- `goc_cu` = `Path(take_path).parent.parent` (thư mục dự án lúc dựng; take nằm ở `takes/` hoặc `voice/_takes/<B>/`, với luồng A thì lấy cha cấp 3).
- Mọi chuỗi bắt đầu bằng `goc_cu` (so không phân biệt hoa thường, chuẩn hoá `\`) thì thay bằng `P`. Áp cho `take_path`, `segments[].src`, `bgm_path` (chỉ khi nằm dưới `goc_cu`).
- Sau khi đổi, `src` vẫn thiếu thì thử cách tìm của `render.py:796-811` (theo tên trong `cuts/` và thư mục con). Vẫn thiếu → `sua_duoc=False`, liệt kê tối đa 5 file thiếu.
- `ass_path`, `wm_file`, `disclaimer_file` **không** đổi gốc. Hậu kỳ luôn dựng lại (§6.3).

### 3.5 Chữ ký hàm (`tools/runner/sua_video.py`, phiếu B-6)

```python
class KhongTraDuoc(Exception): ...          # .ly_do: str (tiếng Việt, hiện lên web)

@dataclass(frozen=True)
class VideoSua:
    ma_video: str; du_an: str; goc: str; thu_muc: str; ten: str
    duong_dan: Path; sua_luc: int           # mtime ms, như video_server trả
    luong: str                               # "C" | "A" | ""
    sua_duoc: bool; ly_do: str

@dataclass(frozen=True)
class BanGhi:
    luong: str; nguon: Path; chi_so: int    # render_batch.json | <B>_plan.json; vị trí plan trong danh sách
    plan: dict                               # đã đổi gốc; luồng C có thêm "take_path"
    goc_cu: str | None
    take: Path; phu_de: Path                 # <take>.subtitles.json
    file_ra: Path                            # file video thật sẽ bị thay
    lien_ket: Path | None                    # output_poster/<ten> nếu khác file_ra
    tien_to: str | None; me: str | None; ma: str | None
    tuy_chon: dict; cau_hinh: dict           # C: options/config của render_batch; A: {} (bộ chuyển đổi tự điền)
    bien_the: bool                           # C: config.variation_enabled và reuse_count >= 2

def ma_video(ma_du_an: str, thu_muc: str, ten: str) -> str
def ds_video_sua(p: Path, goc: Path) -> list[VideoSua]
def tim_video(p: Path, goc: Path, ma: str) -> VideoSua                  # KhongTraDuoc
def tra_ban_ghi(p: Path, v: VideoSua) -> BanGhi                         # KhongTraDuoc
def doi_goc(chuoi: str, goc_cu: str | None, p: Path) -> str
def doc_phu_de(b: BanGhi) -> dict   # {take, take_idx, co_words, sha (sha256 hex bytes .subtitles.json), bien_the,
                                    #  so_video_cung_take, cau:[{i, start, end, text}]}
def doc_canh(b: BanGhi, p: Path) -> list[dict]  # [{i, kind, out_start, out_end, role, clip, doi_duoc, ly_do}]
def ung_vien(p: Path, b: BanGhi, seg: int, gioi_han: int = 60) -> list[dict]
    # [{clip, role, dur, desc, tags[:8], co_anh, dung_duoc, ly_do}]
def kiem_ban_sua(body: dict, chi_tiet: dict) -> dict                    # ThamSoLoi; trả bản sửa chuẩn hoá
def lap_srt(cau: list[dict], sua: dict[int, str]) -> str
def ma_ban_sua(ban_chuan: dict) -> str                                  # "b" + sha256(tham_so_chuan)[:16]
def duong_nhat_ky(b: BanGhi, viec_id: str) -> Path                      # <thư mục file_ra>/_sua/<viec_id>.json
def doc_nhat_ky(path: Path) -> dict | None
```

`so_video_cung_take` đếm các plan khác trong cùng nguồn có cùng take. Web dùng số này để báo "N video khác cùng lời này" (Q1).

---

## 4. Sửa phụ đề

### 4.1 Hiển thị

`doc_phu_de` trả `sentences[]` của `.subtitles.json` (đã kiểm có `text`, `start`, `end`). Dữ liệu thật: 26 câu/take, dạng `{"text": "Cho nha , cái này …", "start": 0.0, "end": 4.24, "words": [...]}`. Web hiện `[mm:ss.s–mm:ss.s]` và chữ đã gộp dấu câu (bỏ khoảng trắng trước `, . ! ?`).

### 4.2 Bản sửa (dữ liệu, không phải lệnh)

```json
{"sua_luc": 1790585841123, "phu_de_sha": "<64 hex>",
 "phu_de": [{"i": 3, "text": "Trời ơi, chạy trớn nha!"}],
 "doi_clip": [{"seg": 5, "clip": "raw-12_000_proof_xe-chay-qua-hang-xe.mp4"}],
 "doi_cho": [[4, 7]]}
```

Luật kiểm (Worker kiểm hình dạng; runner `kiem_ban_sua` kiểm đầy đủ, so với dữ liệu thật):
- `phu_de` ≤ 30 mục; `i` phải là chỉ số câu có thật; không trùng `i`.
- `text` sau NFC dài 1–200 code point. Cấm ký tự điều khiển, xuống dòng, `{ } \ < >`, chuỗi `-->`. `{\…}` là thẻ điều khiển của ASS và `-->` phá cấu trúc SRT.
- Chữ giống hệt bản cũ thì bỏ mục đó.
- `phu_de_sha` phải bằng sha hiện tại, lệch → 409 "Phụ đề đã đổi từ lúc bạn mở — tải lại".
- `doi_clip` ≤ 10 mục, `doi_cho` ≤ 3 cặp; luật ở §5.
- Phải có ít nhất 1 thay đổi. Body ≤ 16 KB (giới hạn `BODY_VIEC_TOI_DA`, `cf/src/worker.js:225`; video_server §3.2). Vượt → 413 "Sửa ít câu hơn mỗi lần".
- Video dùng phụ đề biến thể (`bien_the`) → 400 "Video này dùng biến thể phụ đề — chưa sửa được trên web".
- Take chưa có `.words.json` → 400 "Take chưa có bản Whisper — không sửa trên web". Lý do: dựng lại sẽ chạy Whisper.

**Chữ phụ đề là chữ tự do thứ ba** (bổ sung D3, ghi trong D10):
- chỉ đi vào file `.sua.srt` qua script, **không bao giờ** vào phiếu agent hay dòng lệnh;
- `--ban-sua` là đường dẫn tới file JSON do runner tự ghi.

### 4.3 Áp dụng (trong `sua_video_engine.py`, §6)

1. Sao lưu `<take>.subtitles.json` và `<take>.sua.srt` (nếu có) vào `<thư mục take>/_sua_cu/<viec>/`.
2. `lap_srt(sentences_hien_tai, sua)`: mỗi câu một cue, giờ là `start`/`end` của câu, chữ là bản sửa hoặc bản cũ (đã gộp dấu). Ghi `<take>.sua.srt` (UTF-8, tạm rồi `os.replace`).
   - Hệ quả: từ đây `.sua.srt` được ưu tiên hơn `.script.txt` cho take này (`subtitle_json_builder.py:919-927`). Ghi rõ trong nhật ký và trên web.
3. Ghi lại `mtime_ns` của `<take>.words.json`. Gọi `build_subtitle_json(take, take_idx=<take_idx cũ>, force=False)`.
4. Hậu kiểm:
   - `.words.json` không đổi `mtime_ns` (không chạy Whisper);
   - mọi câu đã sửa có chữ mới trong `sentences[].text` (so sau khi bỏ dấu câu và khoảng trắng thừa);
   - `take_idx` giữ nguyên.

   Sai một điều → khôi phục bản sao lưu, mã thoát 4.

### 4.4 Phạm vi (câu hỏi Q1)

Một take dùng cho nhiều video (luồng C: khoảng 100 video từ khoảng 14 take). `.subtitles.json` là của take, nên đề xuất (A):
- chỉ dựng lại **video đang sửa**;
- các video khác cùng take giữ phụ đề đã in cho tới khi được sửa hoặc dựng lại;
- web báo "Lời này dùng chung cho N video khác chưa đăng — chúng giữ chữ cũ".

---

## 5. Đổi clip, đổi chỗ hai cảnh

### 5.1 Đổi clip của một đoạn phủ

- Chỉ đoạn `kind == "OVL"`. BASE là take (người nói hoặc nền đen Adam), không đổi được.
- Ứng viên (`ung_vien`):
  - mục trong `cuts/clip_index.json` → `clips`, file có thật trong `cuts/` (cùng cách tìm `render.py:796-811`);
  - **cùng `role`** với đoạn;
  - `dur ≥ out_end − out_start`.
- Đánh dấu không dùng được, kèm lý do:
  - "đã có trong video này" (trùng tên file với một OVL khác của plan; với plan `mode=="ctx"` còn so gốc `variant_of`);
  - "quá ngắn".
- Sắp xếp: chưa dùng trong video trước, rồi theo `dur` gần độ dài đoạn. Tối đa 60.
- Áp: `src` = đường dẫn clip, `clip` = tên, `src_start = 0.0`, `src_duration = dur`, `zoom = 1.0`, `hflip = False`, `evidence = []`, `filler = False`, `src_key = ""`, `key_start = -1.0`. **Giữ** `out_start`, `out_end`, `role`. Thêm `"sua tay tu web <viec>"` vào `plan.warnings`.

### 5.2 Đổi chỗ hai cảnh (mức tối thiểu cho "đổi thứ tự")

`doi_cho: [[a, b]]`: đổi `src/clip/src_start/src_duration/zoom/variant` giữa hai đoạn OVL. Giữ khung thời gian của từng đoạn, nên clip của mỗi bên phải đủ dài cho khung mới (kiểm như §5.1).

### 5.3 Không làm (và lý do)

- Cắt, kéo giãn, xoá đoạn: phá luật nhịp (nền lộ ≤ 4.5 s, phủ 1.5–4.0 s) và luật vùng mở/chốt mà máy thi hành (`autovideo-oneshot\SKILL.md:159`). Với Adam, xoá phủ là để lộ nền đen.
- Đổi sang clip **khác vai**: để sau, cần đo lại `audit_ctx`.

### 5.4 Chống trùng khi đổi clip

- Bản mới: `ky_hieu_plan(plan_moi)` (`anti_trung.py:293`).
- Các bản khác:
  - luồng C: các plan còn lại trong `render_batch.json` và `ledger.json` → `plans` của thư mục đó;
  - luồng A: `ledger.json` của `output-adam` và `output_daonguoc`, cộng các `*_plan.json` khác (đúng tập `_nap_ledger` + `_ke_hoach_cho`, `autovideo_audio_take.py:500-546`).
- **Trước khi so**, đổi mọi `src` của cả hai phía thành `Path(src).name`, vì đường dẫn cũ có thể đã sai (§1.2). Bỏ bản ghi của chính video này.
- `mach_trung_voi_lich_su(ban_moi, ds_khac, nguong=4.0)` (`anti_trung.py:276`) khác `None` → mã thoát 2, kèm lý do "Đổi clip làm video trùng {mach:.1f}s với bản {plan_b}". Ngưỡng 4.0 s theo trần của skill (`autovideo-oneshot\SKILL.md:151`).
- **Giới hạn đã biết:** ledger không được cập nhật, nên mẻ dựng **sau** có thể dùng lại clip vừa đổi vào. Ghi trong §10 R-6.

---

## 6. Dựng lại đúng 1 video: `sua_video_engine.py`

### 6.1 Dòng lệnh (runner lập, subprocess dạng list)

```python
[PYTHON_ENGINE, str(APP / "sua_video_engine.py"), "ap-dung",
 "--project", str(P), "--thu-muc", thu_muc, "--video", ten,
 "--ban-sua", str(DATA / "sua" / f"{ban_sua}.json"), "--viec", viec_id]          # cwd = THU_MUC_ENGINE
[PYTHON_ENGINE, str(APP / "sua_video_engine.py"), "hoan-tac",
 "--project", str(P), "--thu-muc", thu_muc, "--video", ten, "--viec-goc", viec_goc, "--viec", viec_id]
[PYTHON_ENGINE, str(APP / "sua_video_engine.py"), "ap-dung", ..., "--xem"]   # chạy khô: kiểm hết, không ghi dự án, không render
```

- `PYTHON_ENGINE` = `KHO_PYTHON_ENGINE` hoặc `F:\auto video oneshot\.venv\Scripts\python.exe`.
- `THU_MUC_ENGINE` = `KHO_ENGINE_DIR` hoặc `F:\auto video oneshot`.
- Đầu script: `sys.path.insert(0, THU_MUC_ENGINE)`.

**Mã thoát:**

| Mã | Nghĩa |
|---|---|
| 0 | xong |
| 2 | bản sửa không hợp lệ, video đã đổi, engine đổi phiên bản; `hoan-tac` thấy đã có bản mới hơn hoặc mất sao lưu (§6.4). **Không đổi gì** |
| 3 | bận (khoá render của engine, hoặc file video đang bị mở); không đổi gì |
| 4 | dựng hỏng; đã hoàn nguyên đủ mọi mục, không đổi gì |
| 5 | **kiểm tay**. Một trong ba trường hợp: (a) hỏng giữa lúc thay file, nhật ký giữ trạng thái, bấm Chạy tiếp (cùng mã việc) để làm nốt → runner gắn `do_dang`; (b) hoàn nguyên phải bỏ qua mục đã bị việc khác đổi (`hoan_nguyen_bo_qua`, §6.3a); (c) hoàn tác đã đưa video về nhưng bỏ qua phụ đề của take (`hoan_tac_bo_qua`, §6.4). (b) và (c) là bỏ qua có chủ đích → runner gắn `kiem_tay`; chạy tiếp cùng mã việc vẫn trả mã 5, không làm lại gì |

**Runner đọc kết thúc mã 2/5** (FX-22/FX-24; `sua_video.doc_ket_thuc_loi(loai, loi) -> dict | None`, `tools/runner/sua_video.py:848-883`). Hàm chỉ đọc chuỗi `loi` của vòng chạy (`Bước <loai> thoát mã N:\n<đuôi log>`), không đọc đĩa, không lưu DB. `api.viec_ra` (`tools/runner/api.py:312-316`) gộp kết quả vào `ket_qua` của việc `loi` trả ra web. Các khoá thêm vào: `ma_thoat`, `kiem_tay`, `do_dang`, `chua_doi_gi`, `bo_qua`, `ly_do_sua`, `canh_bao_sua`, `thong_diep`.

| Trường hợp | Cờ | Nhãn / thông điệp |
|---|---|---|
| Mã 5, lý do là câu "bỏ qua" có chủ đích: hoàn nguyên/hoàn tác bỏ qua mục mà việc khác đã đổi, tức (b), (c) ở trên (`_RE_BO_QUA`, `sua_video.py:821`) | `kiem_tay: true`, `bo_qua: [mục…]` | **"Cần kiểm tay"**: "Cần kiểm tay: đã bỏ qua … vì việc khác đã đổi (cố ý, để không đè bản mới hơn). Chạy tiếp không giúp được …" |
| Mã 5 khác: dừng giữa chừng, tức (a) | `do_dang: true` | "Dừng giữa chừng: <lý do>" (không đọc được lý do → "… xem log việc rồi kiểm tay") |
| Mã 2 | `chua_doi_gi: true` | "Chưa đổi gì: <lý do>"; `hoan_tac_sua` gặp "bản mới hơn" → thông điệp riêng "Không hoàn tác vì video đã có bản mới hơn …" |

Chỉ trường hợp đầu là `kiem_tay: true`. Web hiện nhãn "Cần kiểm tay" theo cờ này kèm lý do nguyên văn, không gộp chung với lỗi thường; `do_dang` và `chua_doi_gi` có nhãn riêng (nhật ký `.culiapp/nhat-ky.md`, FX-21).

Dòng stdout cuối: `KET_QUA_JSON {"trang_thai": …, "video": ten, "sao_luu": rel, "canh_bao": [...], "giay": n}`.

### 6.2 Khoá và an toàn với mẻ đang chạy

1. Lấy khoá `P/.render.lock` rồi `E:\oneshottramcanh\.render-may.lock` (đổi được bằng `AUTOVIDEO_KHOA_MAY`). Định dạng **tương thích `KhoaPlan`** (`autovideo_audio_take.py:549-620`):
   - tạo bằng O_EXCL, nội dung JSON `{batch: "sua-<viec>", pid, viec: "sửa video", luc, het_han: 180, du_an}`;
   - nhịp tim `os.utime` mỗi 30 s;
   - chờ tối đa 10 phút, quá thì mã 3.

   Cùng thứ tự "dự án → máy" như Adam, nên không deadlock.

   **Gỡ khoá cũ** (mtime quá `het_han`, `Khoa._cu`, `tools/runner/sua_video_engine.py:264-281`): không `unlink` thẳng, vì giữa lúc thấy cũ và lúc xoá thì tiến trình khác có thể đã gỡ và lấy khoá mới. Cách làm (`Khoa._go_cu`, `:283-314`):
   - chụp (nội dung, `mtime_ns`) của khoá lúc thấy cũ;
   - `os.replace(khoá → <tên>.go.<pid>.<ns>)` (nguyên tử);
   - đọc lại bản đã dời: đúng ảnh chụp → xoá; khác → trả về tên cũ bằng `os.link` (không đè nếu đã có khoá khác chiếm chỗ; không link được thì `os.rename`, cũng không đè);
   - `PermissionError` lúc dời → để lượt chờ sau thử lại.

   Nhả khoá (`Khoa.tha`, `:353-369`) chỉ xoá khi `pid` và `batch` trong file là của mình; lỗi nhả được ghi vào cảnh báo, không nuốt.
2. Luồng C (`cli.py run`) **không** dùng khoá. Lưới chặn là `dieu_kien_truoc` của runner (§7.2): có `ffmpeg.exe` ngoài cây runner → đứng `cho`.
3. Thư mục của `file_ra` có `*.partial.mp4` mới hơn 10 phút → mã 3 "Mẻ đang dựng trong thư mục này".
4. **Thử khoá file** trước khi tốn GPU: `os.replace(file_ra, file_ra + ".thu-khoa")` rồi đổi ngược ngay. `PermissionError` (video_server đang phát, Poster đang tải) → mã 3 "Video đang được mở (đang xem hoặc đang đăng) — đóng trình phát rồi bấm Chạy lại".

### 6.3 Các bước của `ap-dung` (mỗi bước ghi nhật ký trước khi làm)

Nhật ký `<thư mục file_ra>/_sua/<viec>.json` lưu **đường dẫn tương đối với P** (đổi tên thư mục vẫn dùng được):

```json
{"viec":"j…","ban_sua":"b…","luong":"C","video":"output_poster/50oto2809_061.mp4",
 "buoc":"tra|phu_de|hau_ky|render|thay|nguon|lien_ket|xong|hoan_nguyen",
 "cu":{"size":…,"mtime_ns":…,"sao_luu":"output_poster/_sua_cu/50oto2809_061.j….mp4"},
 "moi":{"size":…,"mtime_ns":…},
 "phu_de":{"take":"takes/…mp4","sao_luu":"takes/_sua_cu/j…/","sha_sau":"…"},
 "nguon":{"file":"output_poster/render_batch.json","sao_luu":"output_poster/_sua/j…/render_batch.json"}}
```

1. **tra**:
   - `tra_ban_ghi` (dùng chung `sua_video.py`);
   - `sua_luc` hiện tại phải bằng `ban_sua.sua_luc`, khác → mã 2 "Video đã đổi từ lúc bạn sửa";
   - đổi gốc đường dẫn;
   - kiểm mọi file nguồn có thật;
   - kiểm `bien_the` / `.words.json` (§4.2).
2. **áp bản sửa vào plan** (trong bộ nhớ): `doi_clip`, `doi_cho` (§5) → kiểm chống trùng (§5.4).
3. **phu_de**: §4.3 (chỉ khi có sửa chữ).
4. **hau_ky**: dựng vào `<thư mục file_ra>/_sua/<viec>/hau_ky/`.
   - `wm`, `dcl` = `load_wm_from_project(P)` (`wm_settings.py:176`), lọc `enabled` như `pipeline_runner.py:1357-1362`.
   - `sub_cfg`:
     - luồng C: `sub_cfg_tu_config(SimpleNamespace(**cau_hinh))`;
     - luồng A: áp khoá `sub_*` của `P/oneshot.json` đúng như `sub_cfg_du_an` (`autovideo_audio_take.py:1544-1558`). Nạp hàm đó bằng `importlib.util.spec_from_file_location` từ đường dẫn skill cố định. Không nạp được → mã 2 "Không đọc được cấu hình phụ đề Adam".
   - `burn_subtitle`:
     - luồng C: `cau_hinh.burn_subtitle` hoặc bản ghi cũ có `ass_path`;
     - luồng A: `True`.
   - Gọi `dung_hau_ky_cho_plan(plan, subtitle_json_path=<take>.subtitles.json, output_folder=<thư mục hậu kỳ>, burn_subtitle=…, sub_cfg=…, wm_config=…, disclaimer_config=…, width, height, cart_arrow=True, …)`, giống `pipeline_runner.py:1425-1442`.
   - Sau đó **gán lại** `cart_arrow_intervals`, `stickers`, `punch_times` bằng giá trị của bản ghi cũ, để video mới chỉ khác đúng chỗ đã sửa.
5. **render**: chép cứng `os.link(file_ra, sao_luu)` vào `_sua_cu/` trước (cùng ổ, tức thì, giữ inode cũ). Rồi tuỳ luồng:
   - **Luồng C**:
     - xoá `<stem>.done.json` (đã chép vào `_sua/<viec>/`);
     - gọi `render_single_plan(plan, output_folder=thư mục file_ra, config_snapshot=SimpleNamespace(**cau_hinh), **tuy_chon_render)`, với `tuy_chon_render` là `options` của `render_batch.json`, bỏ `workers`;
     - engine ghi đè **đúng tên** đó theo kiểu nguyên tử và tự ghi `.done.json` có key khớp với lần "chạy tiếp" sau (`render.py:1029-1030`).
   - **Luồng A**:
     - `output_prefix` = `f"_sua_{viec}"`, `output_folder` = `_sua/<viec>/ra/`;
     - tham số `width=1080, height=1920, fps=30, dissolve=0.1, pad_or_crop="crop", bgm_volume=BGM_VOLUME (đọc từ script Adam như trên), use_nvenc=True`;
     - xong thì `os.replace` vào `file_ra`, thử lại 10 lần × 1 s (giống `_thay_the`, `autovideo_audio_take.py:119-128`).
   - Render hỏng: hoàn nguyên theo §6.3a (bỏ link sao lưu, trả `.done.json` và phụ đề), mã 4. File gốc chưa bị động tới. Hoàn nguyên phải bỏ qua mục nào → mã 5.
6. **thay**: ghi `moi` (size, mtime_ns) vào nhật ký.
7. **nguon**:
   - sao lưu cả file nguồn vào `_sua/<viec>/`;
   - thay **đúng một mục** (`chi_so`) bằng plan mới:
     - luồng C ghi `asdict`-tương thích vào `render_batch.json` bằng `write_json` (`render_checkpoint.py:13-21`), và cập nhật segment của mục cùng `plan_id` trong `plan.json` nếu có;
     - luồng A ghi `to_dict` vào `<B>_plan.json`.
   - Lý do: không làm bước này thì lần `cli.py render` sau dựng lại bản cũ (§1.2).
   - **Luồng C, chống ghi đè mẻ mới** (`PhienSua.buoc_nguon`, `sua_video_engine.py:945-987`). `cli.py run` không lấy khoá, nên một mẻ mới có thể đã ghi lại `render_batch.json` với `plan_id` trùng; so `plan_id` thôi là chưa đủ. Bước `tra` ghi `nguon.mtime_ns` (`st_mtime_ns` của `render_batch.json` lúc tra). Lúc ghi:
     - `st_mtime_ns` hiện tại bằng `nguon.mtime_ns_sau` (dấu chính việc này đã ghi), hoặc chưa có dấu nhưng mục `chi_so` đã đúng là `plan_moi` → coi là đã ghi (chạy lại sau khi ghi);
     - bằng `nguon.mtime_ns` **và** mục `chi_so` có đúng `plan_id` → sao lưu (chỉ lần đầu) rồi ghi, sau đó lưu `mtime_ns_sau`;
     - còn lại → **không ghi** cả `render_batch.json` lẫn `plan.json`, cảnh báo "render_batch.json đã đổi (mẻ khác?) — không cập nhật bản ghi".
   - **Luồng A**: chỉ ghi khi mục `chi_so` vẫn có BASE `<B>_<ma>`; ghi xong đặt lại `mtime` cũ của `<B>_plan.json` (giữ luật tra §3.3 bước 3 cho các video khác của mẻ). Lệch → không ghi, cảnh báo.
8. **lien_ket**: luồng A, hoặc khi `lien_ket` khác `None` (`noi_lien_ket`, `:1139-1168`):
   - nếu `output_poster/<ten>` còn tồn tại **và** `samefile(output_poster/<ten>, sao_luu)` (vẫn trỏ inode cũ): `os.link(file_ra, output_poster/.<ten>.<viec>.lnk)` rồi `os.replace` đè lên, thử lại 10 lần. Không còn trỏ inode cũ → không nối, cảnh báo;
   - không còn tồn tại (Poster đã đăng và xoá) thì bỏ qua, ghi cảnh báo "video đã được đăng trước khi sửa xong";
   - nếu là bản chép: chỉ chép lại (file tạm + `os.replace`) khi nội dung bản trong `output_poster` vẫn giống hệt bản sao lưu cũ; đã giống bản mới → xong; khác cả hai → không chép, cảnh báo "kiểm tay".
9. **xong**: nhả khoá, in `KET_QUA_JSON`.

Chạy lại sau khi bị ngắt (runner khởi động lại, D6): đọc nhật ký (`PhienSua.chay`, `sua_video_engine.py:737-769`).
- `buoc ∈ {tra, phu_de, hau_ky, render}` → hoàn nguyên theo §6.3a. Không bỏ qua mục nào → làm lại từ đầu (bước `tra` chặn bằng `sua_luc` nếu video đã đổi). Có mục bị bỏ qua → mã 5, **không làm lại**.
- `buoc == hoan_nguyen` (lần trước đã hoàn nguyên xong) → **không hoàn nguyên lại**, vì từ lúc đó việc khác có thể đã sửa video. Lần trước có `hoan_nguyen_bo_qua` → mã 5; không có → làm lại từ đầu như trên.
- `buoc ∈ {thay, nguon, lien_ket}` → làm tiếp từ bước kế. Trước đó video phải còn khớp `moi` (size, `mtime_ns`); lệch → mã 5 "Video đã đổi giữa lúc sửa — kiểm tay".
- `xong` → in kết quả cũ, mã 0.

### 6.3a Xếp loại trước khi đè, và hoàn nguyên khi dựng hỏng

**Luật chung** (áp cho cả hoàn nguyên §6.3a lẫn hoàn tác §6.4; trưởng phòng chốt 18/11, FX-21 + R-20 P1-1). Trước khi đè **bất kỳ** mục nào, xếp mục đó vào một trong bốn loại:

| Loại | Nghĩa | Làm gì |
|---|---|---|
| `goc` | hiện tại đã là bản trước khi sửa | không làm gì |
| `minh` | hiện tại đúng là thứ lần sửa này ghi | được đè (trả bản cũ về) |
| `khac` | đã có bản mới hơn, hoặc việc / người khác đã đổi | **không đè** |
| `mat` | đúng là của lần sửa này nhưng mất bản sao lưu | **không đè** |

Các mục: video; `<stem>.done.json` (luồng C); mục `chi_so` trong `render_batch.json` / `<B>_plan.json`; mục `plan_<pid>` trong `plan.json` (luồng C); `<take>.subtitles.json` + `<take>.sua.srt`. Hằng số `GOC, MINH, KHAC, MAT` ở `sua_video_engine.py:1178`.

**Dấu vết nhật ký ghi để xếp loại** (`buoc_phu_de` `:812-850`, `buoc_render` `:867-912`):
- file nhỏ: dấu `{size, mtime_ns, sha}` (`_dau`, `:229-236`) của bản trước (`sub_truoc`, `srt_truoc`, `done_truoc`) và bản việc này ghi (`sub_sau`, `srt_sau`, `done_sau`). Dấu "sau" ghi **ngay** khi engine trả về, kể cả khi engine ném lỗi. Riêng `.sua.srt` còn có `srt_sha_ghi`, ghi **trước** khi ghi file, để phủ trường hợp chết giữa lúc ghi file và lúc ghi nhật ký;
- video: `cu` / `moi` = `{size, mtime_ns}` (không băm video cho nhanh). `moi` được ghi trước `os.replace` (luồng A) hoặc ngay khi render trả về (luồng C);
- nhật ký cũ (trước R-20) không có dấu "trước/sau" thì dùng `sha_truoc` / `sha_sau` làm dấu dự phòng; không đủ dấu → coi là `khac`, không đè mù.

**Hoàn nguyên** (`PhienSua.hoan_nguyen`, `:1058-1107`; mỗi file nhỏ qua `_hn_file`, `:1109-1136`), gọi khi dựng hỏng hoặc khi chạy lại từ bước trước `thay`:
- mỗi mục đối chiếu dấu hiện tại với dấu việc này ghi (file nhỏ: size + `mtime_ns` + sha; video: `samefile` với link sao lưu, hoặc size + `mtime_ns`);
  - đã là bản gốc → bỏ qua, không làm gì;
  - đúng của việc này → trả bản sao lưu về (file nhỏ chép qua file tạm + `os.replace`; video `os.replace` inode cũ về chỗ, giữ `mtime`); gốc không có file → xoá; `.done.json` mà chính việc này đã xoá trước khi render → chép lại;
  - không khớp, hoặc mất bản sao lưu → **bỏ qua**, thêm tên mục vào `hoan_nguyen_bo_qua` trong nhật ký, cảnh báo "kiểm tay";
- ghi `buoc = hoan_nguyen`. Có mục bỏ qua → mã 5 (thay cho mã 4);
- hoàn nguyên không đụng `render_batch.json` / `<B>_plan.json`, vì hai file này chỉ được ghi sau bước `thay`.

### 6.4 `hoan-tac`

Cập nhật 18/11 theo code đã sửa (FX-21, `hoan_tac`, `tools/runner/sua_video_engine.py:1347-1428`) và luật xếp loại §6.3a. Hoàn tác chỉ áp lên **đúng** bản mà lần sửa đó tạo ra.

1. Lấy khoá như §6.2 (`chay`, `:1519`). Đọc nhật ký của `viec_goc`: phải là `ap_dung`, ở `xong`, đúng tên video. Sai → mã 2.
2. Video: phải đúng `moi` (size, `mtime_ns`); khác → mã 2 "Video đã đổi sau lần sửa — không hoàn tác tự động". Bản sao lưu video `cu.sao_luu` phải còn; mất → mã 2 "Không còn bản sao lưu của lần sửa này".
3. **Xếp loại mọi mục gắn với video, trước khi đè bất cứ thứ gì** (`_xet_hoan_tac`, `:1322-1330`; `_tu_choi_neu_moi_hon`, `:1333-1344`):
   - `.done.json` (luồng C, `_xet_done`, `:1202-1225`);
   - mục `chi_so` trong `render_batch.json` / `<B>_plan.json` (`_xet_nguon`, `:1228-1260`): mục hiện tại phải bằng đúng `plan_moi` của lần sửa đó mới là `minh`; mất bản sao lưu nguồn → `mat`;
   - mục `plan_<pid>` trong `plan.json` (`_xet_plan_json`, `:1263-1290`).

   Có mục `khac` hoặc `mat` → **mã 2 "Không hoàn tác tự động: đã có bản mới hơn sau lần sửa này ở … / mất bản sao lưu của … — chưa đổi gì"**, không chạm gì.
   - **Mất sao lưu nguồn → từ chối.** Bỏ hẳn cách cũ "giữ bản sửa trong nguồn, chỉ cảnh báo": như vậy video về bản cũ mà bản ghi vẫn là bản sửa, nên lần "chạy tiếp" của engine sẽ dựng lại bản sửa.
4. **Phụ đề take** (`.subtitles.json` + `.sua.srt`, xét chung vì `.sua.srt` là nguồn chữ của `.subtitles.json`; `_xet_phu_de`, `:1293-1319`). Hai file này thuộc take và dùng chung cho nhiều video, nên video khác cùng take có thể đã sửa tiếp. Loại `khac` hoặc `mat`:
   - video **vẫn** được đưa về bản cũ;
   - phụ đề và `.sua.srt` giữ nguyên, ghi cảnh báo, thêm `"phụ đề"` vào `hoan_tac_bo_qua` của nhật ký hoàn tác;
   - trả **mã 5 "kiểm tay"**. Thay cho mô tả cũ "để nguyên, cảnh báo, mã 0".
5. Thử khoá file video (và bản trong `output_poster`) như §6.2 bước 4. Ghi nhật ký hoàn tác `<thư mục video>/_sua/<viec>.json` với `buoc = thay`.
6. Chép cứng bản hiện tại sang `_sua_cu/<stem>.<viec>.mp4`, rồi `os.replace(sao_luu_cu → file_ra)`. Thao tác này giữ `mtime`, nên `.done.json` cũ khớp lại. Sau đó video phải khớp `cu`; lệch → mã 5.
7. `buoc = nguon`: **xếp loại lại ngay trước khi đè** từng mục (`_khoi_phuc_nguon`, `:1431-1466`), vì có thể có người đổi giữa bước 3 và lúc này:
   - `minh` → đặt lại đúng mục `chi_so` từ bản sao lưu (không chép đè cả file, vì các mục khác có thể đã đổi). Luồng A giữ `mtime` cũ của `<B>_plan.json`;
   - `.done.json` `minh` → chép bản cũ về, hoặc xoá nếu trước khi sửa không có;
   - `plan.json` `minh` → đặt lại `segments` của `plan_<pid>`;
   - `goc` → bỏ qua; `khac`/`mat` lúc này → mã 5 "đổi giữa lúc hoàn tác — video đã về bản cũ, bản ghi giữ nguyên, kiểm tay".
8. `buoc = phu_de`: nếu bước 4 không bỏ qua, xếp loại lại rồi trả `.subtitles.json` và `.sua.srt` về bản cũ (gốc không có `.sua.srt` → xoá) (`_khoi_phuc_phu_de`, `:1469-1487`). Lúc này thành `khac`/`mat` → bỏ qua như bước 4.
9. `buoc = lien_ket`: nối lại link `output_poster` như bước 8 ở §6.3.
10. `buoc = xong`, lưu `ket_qua` và `hoan_tac_bo_qua`. Có mục bỏ qua → mã 5; không có → mã 0.

**Chạy lại cùng việc hoàn tác:**
- nhật ký ở `xong` có `hoan_tac_bo_qua` → **vẫn mã 5**, không làm lại gì; không có → in kết quả cũ, mã 0;
- video đã về bản cũ (lần trước dừng giữa chừng) mà nay có mục `khac`/`mat` → mã 5 "Hoàn tác dừng giữa chừng … video đã về bản cũ, phần còn lại giữ nguyên, kiểm tay", không đè thêm gì;
- chưa đổi gì → làm lại từ bước 2.

Người dùng thấy mã 5 thì tự kiểm phụ đề / bản ghi. Muốn sửa tiếp thì mở màn sửa và tạo một bản sửa mới; không có nút tự sửa cho trường hợp này.

### 6.5 Sao lưu, dung lượng, dọn

- `_sua_cu/` và `_sua/` nằm **trong thư mục của video**:
  - video_server chỉ liệt kê file ngay trong thư mục (`tools/video_server.py:115`), nên tab Duyệt không thấy chúng;
  - Poster quét `output_poster` không đệ quy (`day_len_poster.py:8-9`), nên không đăng nhầm.
- Mỗi video giữ tối đa 3 bản sao lưu (xoá bản cũ nhất khi `ap-dung` xong). Không tự xoá theo ngày.

### 6.6 Độ trung thực của bản dựng lại

- **Luồng C** dùng đúng `options` và `config` đã lưu, cùng `seed`, `bgm_offset`, `cart_arrow_intervals`, nên khác bản cũ đúng ở chỗ đã sửa. Riêng khi mẻ dùng `bgm_vol_min/max`, âm lượng nhạc được bốc ngẫu nhiên lại (`render.py:776-780`).
- **Luồng A** không lưu `options` theo mẻ (`render_batch.json` của thư mục đó là của mẻ cuối). Dùng mặc định của `run` (§6.3 bước 5). Nếu mẻ đã chạy với `--dissolve` hoặc `--bgm-volume` khác thì chuyển cảnh hoặc âm lượng nhạc khác nhẹ. Web ghi rõ điều này.
- Phiếu tuỳ chọn B-9 (§11) giúp mẻ sau lưu được ảnh chụp tham số.

### 6.7 Kiểm sau dựng

`render_single_plan` đã gọi `verify_video` (đủ hình và tiếng, đúng thời lượng ± 0.15 s, đúng 1080×1920, đúng fps; `render_checkpoint.py:52-82`). Bộ chuyển đổi cũng trích 1 khung giữa mỗi đoạn đã đổi vào `_sua/<viec>/khung_<seg>.jpg` để người làm hoặc reviewer xem được bằng mắt. Web chưa hiện ảnh này ở đợt 6.

### 6.8 Phương án B: thêm lệnh vào engine (để người dùng chọn, Q2)

Nếu muốn lệnh nằm trong engine:
- thêm file mới `F:\auto video oneshot\modules\sua_mot.py`, chứa phần lõi của §6.3 (không có phần runner);
- thêm `@app.command("render-mot")` vào `cli.py`, sau `cmd_render` (`cli.py:441-458`), với tham số `--project P --video <ten> --ban-sua <json> [--xem]`;
- thêm test vào `tests/`.

**Rủi ro:**
- engine không có git, nên trước khi sửa phải chép `cli.py` ra bản sao lưu;
- import đầu `cli.py` nặng, nên lệnh chậm hơn khoảng vài giây;
- skill `autovideo-oneshot` phải ghi thêm lệnh mới;
- sửa app khác cần người dùng duyệt;
- người chạy `cli.py run` từ app GUI không bị ảnh hưởng, vì đây chỉ là file mới cộng thêm một lệnh.

**Lợi:** người dùng dùng được lệnh này trong terminal mà không cần runner.

Đề xuất vẫn là **A**: không đụng engine, bộ chuyển đổi được kiểm thử trong repo kho và cài theo D8.

---

## 7. Danh mục việc runner mới

### 7.1 Bảng loại

| Mã | Tên | `dot` | Làn / tài nguyên | Tiền | Tham số | Khoá trùng | Quá giờ | Tự chạy lại |
|---|---|---|---|---|---|---|---|---|
| `sua_video` | Sửa và dựng lại 1 video | **4** (*) | gpu / – | miễn phí | `uid` `^\d{19}$`; `du_an` 12 hex (`tim_du_an`); `ma_video` `^[0-9a-f]{16}$` (phải có trong `ds_video_sua`); `ban_sua` `^b[0-9a-f]{16}$` (có trong bảng `ban_sua`, cùng `uid`, `ma_video`) | `ma_video` | 20 phút | có (nhật ký, §6.3) |
| `hoan_tac_sua` | Dùng lại bản cũ | 4 (*) | gpu / – | miễn phí | `uid`, `du_an`, `ma_video`, `viec_goc` `^j\d{14}[a-z0-9]{4}$` (việc `sua_video` đã `xong` của cùng `ma_video`) | `ma_video` | 10 phút | có |

(*) `dot_bat` hiện là 4 (`han_muc.py:19`). Đặt `dot=6` thì phải nâng `dot_bat` lên 6, và như vậy **mở luôn `taovideo` đợt 5**. Vì vậy hai loại này gắn `dot=4`, coi như phụ lục đợt 4 (miễn phí, không cần duyệt). Ghi trong D10.

### 7.2 Điều kiện trước, lập bước, đối soát

- **`dieu_kien_truoc`** (cả hai loại):
  - không có việc mở của loại kia trên cùng `ma_video` → nếu có thì `"ban"`;
  - `mt.ffmpeg_ngoai()` → `"ban"`;
  - `P/.render.lock` hoặc khoá máy có mtime < 180 s → `"ban"` (ghi chú "Đang có mẻ dựng video — chờ");
  - `PYTHON_ENGINE` không có → `viec_tay` "Không thấy Python của app dựng video `F:\auto video oneshot\.venv` — kiểm ổ F rồi bấm Đã làm xong".
- **`lap_buoc`**:
  - runner ghi `DATA/sua/<ban_sua>.json` (nội dung bảng `ban_sua`, JSON chuẩn) rồi trả 1 `BuocChay`. Lệnh như §6.1, `env_them={"PYTHONUTF8":"1","PYTHONIOENCODING":"utf-8"}`, console ẩn dùng chung (§6.1 của `bo-chay-viec.md`);
  - mã thoát 3 → việc về `loi` với lý do nguyên văn, nút "Chạy lại". Không đổi `vong_lap.py`.
- **`kiem_dau_ra`**: đọc nhật ký `duong_nhat_ky(b, viec_id)`.
  - `buoc == "xong"` **và** `file_ra` khớp `moi` → `xong`;
  - có nhật ký nhưng chưa `xong` → `chua`, nên lần chạy lại tự làm nốt;
  - không có → `chua`.
- **Kết quả** hiện trên web: tên video, "đã sao lưu bản cũ", cảnh báo.
- **Mã thoát 2/5** (§6.1): việc về `loi`; `ket_qua` trả web mang `kiem_tay` / `do_dang` / `chua_doi_gi` + `thong_diep` theo bảng ở §6.1.
  - `kiem_tay: true` (mã 5 bỏ qua có chủ đích): **không cho "Chạy tiếp"**. `co_the_chay_tiep` = false (`api.co_the_chay_tiep`, `tools/runner/api.py:363-374`); `POST /viec/<id>/chay-tiep` trả 409 `{loi: thong_diep, kiem_tay: true}` (`api.thong_diep_kiem_tay` `:347`, `p_chay_tiep` `:842-844`). Lý do: chạy tiếp cùng mã việc thì bộ chuyển đổi đọc lại nhật ký và lại trả mã 5.
  - `kiem_tay: true` **vẫn cho "Chạy lại"** (`co_the_chay_lai` không xét `kiem_tay`, `api.py:328`). Chạy lại tạo việc mới từ cùng tham số (`p_chay_lai`, `api.py:855-866`, `chay_lai_tu`), không dùng nhật ký của việc cũ.
  - `do_dang: true` (mã 5 dừng giữa chừng): "Chạy tiếp" cùng mã việc để bộ chuyển đổi làm nốt/hoàn nguyên theo nhật ký.
  - Việc có sửa chữ phụ đề: cả hai nút bị chặn theo §7.2a, bất kể cờ nào ở trên.

### 7.2a Chạy lại / chạy tiếp việc có sửa chữ phụ đề: phải lưu lại bằng mật khẩu

**Quyết định** (trưởng phòng chốt 18/11; áp D10 Q3 "Có, mỗi lần lưu" theo nghĩa **mật khẩu mỗi lần**). Việc `sua_video` mà `ban_sua` có `phu_de` khác rỗng:
- **không** được tạo lại qua nút "Chạy lại" / "Chạy tiếp" (`POST /viec/<id>/chay-lai`, `/chay-tiep`). Runner trả 409 với thông điệp `sua_video.LOI_SUA_CHU_CAN_MAT_KHAU` = "Sửa chữ phụ đề cần lưu lại và nhập mật khẩu — mở màn Sửa video để lưu lại" (`tools/runner/sua_video.py:812`; chặn ở `api.py:840-841` và `:860-863`; "có sửa chữ" = `sua_video.co_sua_chu(ban)`, `sua_video.py:825`, tức `ban_sua.phu_de` khác rỗng);
- người dùng phải đi lại đường `POST /api/viec/sua-video/<uid>/<ma>/luu` (§8.3) kèm `mat_khau`. Đường này sinh `ban_sua` + việc mới;
- việc chỉ đổi clip / đổi chỗ (không có `phu_de`) vẫn dùng "Chạy lại" như cũ.

Lý do: chữ phụ đề là chữ tự do (D3 bổ sung trong D10). Nếu cho chạy lại bằng nút không mật khẩu, một phiên web bị chiếm (XSS) có thể bấm chạy lại một bản sửa chữ cũ vào lúc khác ý người dùng.

Phạm vi: chỉ chặn lần tạo lại do **người bấm** (hai endpoint API trên). Runner tự làm nốt cùng việc sau khi khởi động lại (D6, §6.3 "Chạy lại sau khi bị ngắt") **không** bị chặn, vì đó vẫn là việc cũ và `ban_sua` đã được xác nhận mật khẩu lúc lưu. Chặn chỉ nằm ở `api.py`, vòng chạy không kiểm.

**Cờ trả web** (`api.viec_ra`, `tools/runner/api.py:327-329`):
- `co_the_chay_lai` = trạng thái thuộc `TRANG_THAI_CHAY_LAI` **và** không sửa chữ;
- `can_luu_lai_mat_khau` = có sửa chữ;
- `co_the_chay_tiep` = `api.co_the_chay_tiep(v, sua_chu)`: false khi có sửa chữ hoặc `kiem_tay` (§7.2).

Web hiện nút theo các cờ này và hiện nguyên văn lý do 409. Trạng thái code: đã có (FX-22, FX-24). Ghi ở D10.

### 7.3 Hạn mức và trạng thái DB

- Thêm vào `HAN_MUC_TRAN`: `"sua_video_ngay": 60` (đếm việc `sua_video` + `hoan_tac_sua` tạo trong ngày). Chặn bấm lặp vô hạn làm bận GPU.
- Bảng mới, schema `"3"` (`kho_viec.py`, thêm `CREATE TABLE IF NOT EXISTS`, không đụng bảng cũ):

```sql
CREATE TABLE IF NOT EXISTS ban_sua(
  id TEXT PRIMARY KEY,               -- 'b' + sha256(tham_so_chuan(noi_dung))[:16]
  uid TEXT NOT NULL, du_an TEXT NOT NULL, ma_video TEXT NOT NULL,
  noi_dung TEXT NOT NULL,            -- JSON chuẩn đã qua kiem_ban_sua
  tao_boi TEXT NOT NULL, tao_luc TEXT NOT NULL);
```

Dòng cũ hơn 30 ngày bị xoá ở bước dọn khởi động (§4.6 của `bo-chay-viec.md`).

---

## 8. API

### 8.1 Runner (thêm vào `api.py`)

| Method + path | Vào | Ra |
|---|---|---|
| `GET /sua-video/<uid>` | – | `{videos:[VideoSua (bỏ duong_dan)]}` |
| `GET /sua-video/<uid>/<ma_video>` | – | `{video, luong, me, tien_to, plan_id, phu_de: doc_phu_de, canh: doc_canh, ghi_chu_luong_a: bool, viec_mo: id\|null, lich_su:[{viec, loai, trang_thai, luc, boi, hoan_tac_duoc}]}` |
| `GET /sua-video/<uid>/<ma_video>/ung-vien?seg=<n>` | `seg` 0–199 | `{ung_vien:[…]}` |
| `POST /sua-video/<uid>/<ma_video>/ban-sua` (ký) | bản sửa §4.2 + `boi` | 201 `{ban_sua, du_an, tom_tat:{so_cau, so_clip, so_doi_cho}}` · 400 · 409 (`sua_luc` hoặc `phu_de_sha` lệch) · 413 |

Việc được tạo qua `POST /viec` có sẵn.

### 8.2 video_server (`tools/video_server.py`)

- `RE_R` thêm nhánh `sua-video/\d{19}(/[0-9a-f]{16}(/(ung-vien|ban-sua))?)?`, `R_QUERY_KHOA` thêm `seg`.
  - Quan sát thêm: `RE_R` hiện **chưa** có `xin-duyet-lai` (`tools/video_server.py:128-129`), dù §3.2 của `bo-chay-viec.md` đã thêm. Phiếu W-7 không sửa chỗ này; trưởng phòng đối chiếu FX-12.
- Act mới trên `/v/<id>/…`:
  - `anh?du_an=<12 hex>&ten=<clip>&k=<0-9|cs>` → `image/jpeg` từ `cuts/.index_frames/<clip_id>/f_0k.jpg` (`k=cs` → `contact_sheet.jpg`);
  - `clip?du_an=<12 hex>&ten=<clip>` → stream mp4 có Range (dùng `gui_file_range`, `tools/video_server.py:61`), không bao giờ là attachment.
- Kiểm:
  - `du_an` phải là `ma_du_an` của một thư mục `<GOC>/*<id>` (cùng công thức `du_an.py:39`, có test chéo);
  - `ten` khớp mẫu §3.1 **và** là khoá trong `clip_index.json` → `clips`;
  - file nằm ngay trong `cuts/` hoặc thư mục con một cấp;
  - `clip_id` = nhóm 1 của `^(.+?_\d{3})_`, không khớp → 404.

### 8.3 Worker (`cf/src/worker.js`)

| Web gọi | Chuyển tới | Ghi chú |
|---|---|---|
| `GET /api/viec/sua-video/<uid>` · `/<ma>` · `/<ma>/ung-vien?seg=` | `/r/sua-video/…` | thêm vào `tuyenViec`; query `seg` `^\d{1,3}$` |
| `POST /api/viec/sua-video/<uid>/<ma>/luu` | (1) `POST /r/sua-video/<uid>/<ma>/ban-sua` → (2) `POST /r/viec {loai:"sua_video", tham_so:{uid, du_an, ma_video, ban_sua}}` | Web gửi `{sua_luc, phu_de_sha, phu_de, doi_clip, doi_cho, mat_khau?}`. Worker kiểm hình dạng §4.2. Có `phu_de` khác rỗng thì kiểm `mat_khau` (Q3), đếm sai bằng KV `sai:<user>` như `duyetViec`. Ký cả hai POST. Trả `{viec, ban_sua}`; (2) trả 409 trùng → `{trung: id}` |
| `POST /api/viec` `{loai:"hoan_tac_sua", tham_so:{uid, du_an, ma_video, viec_goc}}` | có sẵn | `kiemThamSoViec` đã nhận chuỗi ≤ 40 |
| `GET /api/video/<id>/(anh\|clip)` | `/v/<id>/(anh\|clip)` | thêm vào regex (`cf/src/worker.js:690`) và `QUERY_VIDEO`: `anh:["du_an","ten","k"]`, `clip:["du_an","ten"]`; `anh` có timeout, `clip` là stream |

Chỉ `USER_MAY_NHA` dùng được. POST bắt buộc Origin như cũ.

---

## 9. Màn hình web (điện thoại)

- **Tab Duyệt** (`web/app.js:547-564`):
  - thêm nút `✏ Sửa` vào `.dv-nut`. Chỉ hiện khi danh sách `GET /api/viec/sua-video/<uid>` (gọi 1 lần lúc mở tab) có video cùng `(goc, ten)` với `sua_duoc`;
  - video không sửa được thì nút mờ, chạm vào hiện `ly_do`;
  - video đang có việc sửa mở thì hiện nhãn "đang dựng lại…".
- **`#/sua/<uid>/<ma_video>`** (file mới `web/sua.js`, router `web/app.js:778-792`):
  - Đầu trang: tên video, "Giọng thật" hoặc "Adam · mẻ B", trình phát nhỏ dính trên cùng (dùng `/api/video/<id>/xem`). Luồng A có dòng "Dựng lại bằng tham số mặc định — chuyển cảnh/nhạc có thể khác nhẹ".
  - **Thẻ Phụ đề**:
    - mỗi câu một khối `[00:03.2]` (chạm vào thì tua tới giây đó) + `textarea` tự giãn, `maxlength=200`;
    - câu đã sửa có viền vàng và nút ↺ để trả về chữ cũ;
    - đầu thẻ báo "Lời này dùng chung cho N video khác — chúng giữ chữ cũ" (Q1).
  - **Thẻ Cảnh**:
    - danh sách đoạn theo thời gian: `00:04–00:07 · Lợi ích · [ảnh f_0k]` + nút `Đổi`;
    - BASE hiện "Nền (người nói)" hoặc "Nền đen (Adam)", không có nút.
  - **Ngăn kéo "Đổi"** (bottom sheet):
    - lưới 2 cột ứng viên: ảnh khung, `desc` 2 dòng, thời lượng;
    - nút `▶ Xem thử` (thẻ `video` với `/api/video/<id>/clip?…`, `preload="none"`) và `Chọn`;
    - ứng viên không dùng được thì mờ, kèm lý do;
    - cuối danh sách có nút "Đổi chỗ với cảnh khác…" (chọn đoạn thứ hai).
  - **Thanh dưới** (cố định):
    - `N thay đổi · [Huỷ] [Lưu và dựng lại]`;
    - có sửa chữ thì hiện hộp nhập mật khẩu trước khi gửi (Q3);
    - gửi xong chuyển sang khung tiến trình: trạng thái việc (thăm dò 3 s qua `GET /api/viec/<id>`), log rút gọn;
    - xong thì hiện "▶ Xem bản mới" và "↩ Dùng lại bản cũ" (tạo `hoan_tac_sua`);
    - 409 trùng việc → "Video này đang được dựng lại" + liên kết sang `#/viec/<id>`.
  - **Lịch sử sửa** (cuối trang): các lần sửa, ai, lúc nào, nút hoàn tác ở lần gần nhất có `hoan_tac_duoc`.
- Mọi chuỗi từ runner đi qua `esc()`. Không chèn HTML thô. Chữ trong `textarea` gán bằng `.value`.
- Lưu nháp cục bộ trong `sessionStorage` theo `ma_video` để mất sóng không mất chữ đã gõ.

---

## 10. Rủi ro

| # | Rủi ro | Cách giảm |
|---|---|---|
| R-1 | Lần "chạy tiếp" render của engine ghi đè bản sửa | Cập nhật mục plan trong `render_batch.json`; engine tự ghi `.done.json` có key khớp (§6.3 bước 5, 7) |
| R-2 | Đường dẫn tuyệt đối cũ (đã thấy trong dữ liệu thật) | Đổi gốc (§3.4), dựng lại hậu kỳ; thiếu file thì từ chối và liệt kê |
| R-3 | Hardlink `output_poster` vẫn trỏ bản cũ, Poster đăng bản cũ | Bước `lien_ket` (§6.3 bước 8), kiểm `samefile` |
| R-4 | Tranh GPU, tranh với mẻ đang dựng | Làn `gpu` 1 việc; khoá `.render.lock` và khoá máy tương thích Adam; `ffmpeg_ngoai`; kiểm `*.partial.mp4` |
| R-5 | Windows khoá file (đang phát hoặc đang đăng) | Thử khoá trước khi render; `os.replace` thử lại 10 lần; mã 3 "đóng trình phát" |
| R-6 | Ledger không biết clip mới, nên mẻ sau có thể trùng với video đã sửa | Kiểm trùng lúc đổi (§5.4); ghi trong D10. Phiếu sau có thể ghi ledger |
| R-7 | `.sua.srt` được ưu tiên hơn `.script.txt` vĩnh viễn cho take đó | Ghi nhật ký và báo trên web; hoàn tác khôi phục `.sua.srt` cũ hoặc xoá |
| R-8 | Lỡ chạy Whisper (tốn GPU, ghi đè `.words.json`) | Chỉ `build_subtitle_json` 1 take, `force=False`; bắt buộc có `.words.json`; hậu kiểm `mtime_ns` |
| R-9 | Bộ chuyển đổi phụ thuộc hàm nội bộ engine (A) | Lúc chạy kiểm có đủ `render_single_plan`, `dung_hau_ky_cho_plan`, `build_subtitle_json`, `mach_trung_voi_lich_su`, `load_wm_from_project` và chữ ký tham số (`inspect.signature`); thiếu → mã 2 "engine đổi phiên bản". Test fixture chạy với engine thật |
| R-10 | Chữ tự do (XSS chèn chữ vào video rồi Poster đăng) | Mật khẩu khi có sửa chữ (Q3); lọc ký tự; chữ chỉ vào `.sua.srt`; video dựng lại phải duyệt lại (khoá `sua_luc`) |
| R-11 | Luồng A dựng lại không đúng `--dissolve`/`--bgm-volume` của mẻ | Báo trên web; phiếu tuỳ chọn B-9 |
| R-12 | Agent cùng user sửa `ban_sua` trong DB | Việc miễn phí, chỉ đổi video trong dự án, có sao lưu, phải duyệt lại. Không cần sổ D9 |
| R-13 | Video đã đăng trong lúc đang sửa | Bước `lien_ket` thấy link mất → cảnh báo "đã đăng trước khi sửa xong" |
| R-14 | Hai việc sửa hai video cùng take | Làn `gpu` chạy tuần tự; `phu_de_sha` của việc sau lệch → mã 2 "phụ đề đã đổi — mở lại và sửa" |
| R-15 | Hoàn tác / hoàn nguyên đè mất bản mới hơn của việc khác (video, bản ghi, phụ đề take dùng chung) | Xếp loại `goc/minh/khac/mat` trước mỗi lần đè (§6.3a); mục gắn video có bản mới hơn → mã 2 không đổi gì; phụ đề take → giữ nguyên, mã 5 kiểm tay (§6.4) |
| R-16 | `cli.py run` (không khoá) ghi lại `render_batch.json` giữa lúc sửa | So `st_mtime_ns` với lúc tra / dấu chính việc này ghi; lệch → không ghi, cảnh báo (§6.3 bước 7) |
| R-17 | Gỡ nhầm khoá vừa được tiến trình khác lấy (TOCTOU) | Gỡ bằng `os.replace` sang tên tạm rồi so lại, sai thì trả về (§6.2) |
| R-18 | Chạy lại bản sửa chữ phụ đề mà không xác nhận lại | Bắt lưu lại qua `/luu` kèm mật khẩu (§7.2a; code chưa làm) |

---

## 11. Kế hoạch phiếu

Gốc `E:\phantichcanhquay\kho-san-pham`. Lệnh chạy trong Git Bash từ `cd /e/phantichcanhquay/kho-san-pham`. Test không chạm dự án thật hay `%LOCALAPPDATA%\kho-runner` (dùng `tmp_path`, `KHO_RUNNER_DIR`, `KHO_VIDEO_GOC`, `AUTOVIDEO_KHOA_MAY` trỏ sang thư mục tạm).

### Lượt 1 (song song, không trùng file)

**B-6 · culiapp-backend · Lõi tra cứu và kiểm bản sửa**
- ĐƯỢC SỬA: `tools/runner/sua_video.py` (mới), `tools/test_runner_sua_video.py` (mới).
- Việc: toàn bộ chữ ký §3.5; luật §3.1–§3.4, §4.2, §5.1–§5.2 (phần kiểm, không ghi). Chỉ dùng stdlib.
- Fixture tự dựng trong `tmp_path`:
  - (a) luồng C có `output_poster/render_batch.json` chứa đường dẫn **gốc cũ** + `.done.json` khớp/lệch;
  - (b) luồng A có `output_daonguoc/<B>_plan.json` + hardlink `output_poster`;
  - (c) `clip_index.json` 13 vai.
- Kiểm chứng: `python -B -m pytest tools/test_runner_sua_video.py -q -p no:cacheprovider`.
- Xong khi: test phủ ánh xạ C và A, đổi gốc, từ chối khi `.done.json` lệch, từ chối biến thể, lọc ký tự (`{`, `\`, `-->`, xuống dòng), giới hạn 30/200/16 KB, `ma_video` ổn định.

**W-7 · culiapp-web · video_server: chuyển tiếp `/r/sua-video/*`, act `anh` và `clip`**
- ĐƯỢC SỬA: `tools/video_server.py`, `tools/test_video_server.py`.
- Việc: §8.2. Thêm test chéo công thức `ma_du_an` khớp `tools/runner/du_an.py:39`.
- Kiểm chứng: `python -B -m pytest tools/test_video_server.py -q -p no:cacheprovider`.
- Xong khi:
  - `ten` có `..`, `/`, `\`, hoặc không có trong `clip_index` → 404;
  - Range hoạt động với `clip`;
  - `RE_R` nhận đúng 4 dạng path mới, từ chối dạng khác.

**W-8 · culiapp-web · Worker: route sửa video**
- ĐƯỢC SỬA: `cf/src/worker.js`, `cf/test/worker.test.mjs`.
- Việc: §8.3. Kiểm hình dạng bản sửa như §4.2. Gọi tuần tự hai POST đã ký; lỗi ở (1) thì không gọi (2).
- Kiểm chứng: `node --test cf/test/worker.test.mjs cf/test/chu-ky-cheo.test.mjs`.
- Xong khi:
  - có `phu_de` mà thiếu hoặc sai mật khẩu → 403, có đếm sai;
  - body > 16 KB → 413;
  - `anh`/`clip` chỉ chuyển đúng khoá query;
  - user khác `nhan`/`comeofage` → 403.

### Lượt 2 (sau B-6; ba phiếu song song, không trùng file)

**B-7 · culiapp-backend · Loại việc, bảng `ban_sua`, API runner**
- ĐƯỢC SỬA: `tools/runner/danh_muc.py`, `tools/runner/han_muc.py`, `tools/runner/api.py`, `tools/runner/kho_viec.py`, `tools/test_runner_danh_muc.py`, `tools/test_runner_han_muc.py`, `tools/test_runner_api.py`, `tools/test_runner_kho_viec.py`.
- Phụ thuộc: B-6.
- Việc: §7, §8.1. Schema `"3"` (bảng mới, nâng `PHIEN_BAN_SCHEMA`, giữ nâng cấp từ `"2"`). `lap_buoc` ghi `DATA/sua/<ban_sua>.json` và dựng argv §6.1. `kiem_dau_ra` đọc nhật ký qua `sua_video.doc_nhat_ky`.
- Kiểm chứng: `python -B -m pytest tools/test_runner_danh_muc.py tools/test_runner_han_muc.py tools/test_runner_api.py tools/test_runner_kho_viec.py -q -p no:cacheprovider`.
- Xong khi:
  - `dot=4` không mở `taovideo`;
  - trùng `ma_video` → 409;
  - DB schema 2 cũ mở lên được;
  - argv không chứa chữ từ web;
  - `hoan_tac_sua` từ chối khi `viec_goc` không `xong`.

**A-6 · culiapp-automation · Bộ chuyển đổi `sua_video_engine.py`**
- ĐƯỢC SỬA: `tools/runner/sua_video_engine.py` (mới), `tools/test_sua_video_engine.py` (mới).
- Phụ thuộc: B-6 (import `sua_video`).
- Việc: §6.1–§6.7: khoá tương thích `KhoaPlan`, nhật ký, `ap-dung`, `--xem`, `hoan-tac`, mã thoát, kiểm chữ ký hàm engine (R-9).
- Test chạy bằng Python của engine. Đầu file test có `pytest.importorskip("modules.render")`, nên chạy bằng Python hệ thống thì bị bỏ qua. Test dựng dự án tạm bằng `ffmpeg -f lavfi` (take 6 s màu + sine, 3 clip 3 s), `.words.json`/`.subtitles.json` giả, `render_batch.json` với **đường dẫn gốc cũ**, rồi chạy render thật bằng CPU (`use_nvenc=False` qua tham số test) trong `tmp_path`. Đây là mức fixture, không đụng dự án thật.
- Kiểm chứng: `"/f/auto video oneshot/.venv/Scripts/python.exe" -B -m pytest tools/test_sua_video_engine.py -q -p no:cacheprovider`.
- Xong khi:
  - (1) sửa 1 câu → `.subtitles.json` có chữ mới, `.words.json` giữ nguyên mtime;
  - (2) đổi clip → `render_batch.json` chỉ đổi đúng 1 mục, `.done.json` khớp, gọi lại `resume_batch` không dựng lại bản đó;
  - (3) luồng A → link `output_poster` trỏ inode mới;
  - (4) giả lỗi render → mã 4, file gốc và phụ đề y nguyên;
  - (5) giả ngắt sau `thay` → chạy lại làm nốt `nguon`/`lien_ket`;
  - (6) `hoan-tac` trả đúng size/mtime cũ;
  - (7) khoá bận → mã 3;
  - (8) file đang mở (giữ handle) → mã 3 trước khi render.

**W-9 · culiapp-web · Màn sửa video**
- ĐƯỢC SỬA: `web/sua.js` (mới), `web/app.js`, `web/index.html` (thêm `<script src="sua.js?v=1" defer>`, tăng `v` của `app.js`), `web/style.css`, `cf/test/sua-web.test.mjs` (mới).
- Phụ thuộc: interface W-8 (§8.3). Không cần W-8 xong mới làm, vì test dùng `fetch` giả.
- Việc: §9.
- Kiểm chứng: `node --test cf/test/sua-web.test.mjs cf/test/viec-web.test.mjs`.
- Xong khi:
  - hàm thuần (`dongThayDoi`, `kiemCauPhuDe`, `nhomCanh`, `ghepVideoSua(nguon, ds)`) có test;
  - chữ có `<script>` hiển thị như chữ thường;
  - không gửi `mat_khau` khi chỉ đổi clip;
  - bản nháp `sessionStorage` khôi phục được.

### Lượt 3: tích hợp thật (trưởng phòng chạy; mỗi bước NEEDS_APPROVAL)

1. Cài runner bản mới (`python tools/cai_runner.py`, ghi `%LOCALAPPDATA%\kho-runner\app\`), khởi động lại runner và video_server; deploy Worker.
2. Chỉ đọc: `GET /api/viec/sua-video/1736818222555104357` trên web. Kiểm `50oto2809_061.mp4` ra luồng C, có 26 câu và các đoạn.
3. Chạy khô: tạo một bản sửa thử, rồi trưởng phòng chạy tay lệnh §6.1 có `--xem` (không ghi dự án, không render).
4. Sửa thật **1 video chưa đăng** do người dùng chọn. Xem lại trên web, rồi thử hoàn tác.

### Phiếu tuỳ chọn (không chặn đợt 6)

**B-9 · culiapp-backend · Mẻ Adam lưu ảnh chụp tham số dựng**
- ĐƯỢC SỬA: `C:\Users\Mi\.claude\skills\tao-video-tu-canh-quay\scripts\autovideo_audio_take.py` (+ test của skill).
- Việc: ghi thêm `<out>/<B>_render.json` = `{bgm_volume, dissolve, ovl_max, sub_phu, am_goc}` cạnh `<B>_plan.json`. A-6 đọc file này nếu có.
- **Sửa skill nằm ngoài repo, cần người dùng duyệt.**

### Bảng chồng file theo lượt

| Lượt | Phiếu và file |
|---|---|
| Đ6-L1 | B-6 (`sua_video.py` + test) · W-7 (`video_server.py` + test) · W-8 (`worker.js`, `worker.test.mjs`) |
| Đ6-L2 | B-7 (`danh_muc, han_muc, api, kho_viec` + 4 test) · A-6 (`sua_video_engine.py` + test) · W-9 (`sua.js, app.js, index.html, style.css, sua-web.test.mjs`) |
| Đ6-L3 | tích hợp thật (trưởng phòng) |

Không có hai phiếu cùng lượt trùng file. Gợi ý cho trưởng phòng: thêm `tools/test_runner_sua_video.py` và `cf/test/sua-web.test.mjs` vào `LENH` của `.culiapp/kiem-chung.py`. Riêng `tools/test_sua_video_engine.py` chạy bằng Python engine nên đặt thành một lệnh riêng.

---

## 12. Câu hỏi mở cho người dùng

- **Q1. Sửa lời của một take thì dựng lại video nào?**
  - (A, đề xuất) Chỉ video đang sửa; video khác cùng lời giữ chữ cũ, web báo số lượng.
  - (B) Mọi video chưa đăng cùng take (N × khoảng 12 s GPU, và phải duyệt lại cả N).
- **Q2. Đặt code dựng lại ở đâu?**
  - (A, đề xuất) Bộ chuyển đổi trong bản cài runner, gọi hàm engine; **không sửa engine**.
  - (B) Thêm lệnh `render-mot` vào `F:\auto video oneshot\cli.py`. Đây là sửa app khác; engine không có git nên phải sao lưu tay.
- **Q3. Có bắt nhập mật khẩu khi lưu phụ đề không?**
  - (A, đề xuất) Có, một lần mỗi lần bấm "Lưu và dựng lại" nếu có sửa chữ; chỉ đổi clip thì không cần.
  - (B) Không cần. Nhanh hơn, nhưng XSS có thể chèn chữ vào video. Video vẫn phải duyệt lại trước khi đăng.

---

## 13. Tự soát

| Mục được nhắc | Có thật |
|---|---|
| `cli.py` `subtitles`, `render`, `_resolve_paths`, import đầu file | `F:\auto video oneshot\cli.py:379-410`, `:441-458`, `:121-160`, `:52-60` |
| `render_single_plan`, đặt tên, tìm lại cuts, `_chay_ffmpeg` (done/publish), `render_batch_plans` + `save_batch` | `modules/render.py:732`, `:768-769`, `:796-811`, `:890-1061` (`:911-921`, `:1022-1030`), `:1064`, `:1094-1099` |
| `write_json`, `file_sig`, `render_key`, `verify_video`, `save_batch`, `load_batch`, `resume_batch` | `modules/render_checkpoint.py:13`, `:24`, `:33`, `:52`, `:85`, `:92`, `:106` |
| `resume_render_ui` | `modules/pipeline_runner.py:699` |
| Hậu kỳ trong pipeline, wm/dcl, biến thể | `modules/pipeline_runner.py:1348-1362`, `:1390-1442` |
| `dung_hau_ky_cho_plan`, tên `.ass` | `modules/hau_ky.py:125`, `:169` |
| `Seg`, `TimelinePlan`, `to_dict`, `resolve_overlay_for_clip` | `modules/timeline.py:308`, `:333`, `:372`, `:400` |
| `soat_me`, `mach_trung_voi_lich_su`, `ky_hieu_plan` | `modules/anti_trung.py:256`, `:276`, `:293` |
| `chu_cuoi`, `build_subtitle_json`, `run_subtitle_pipeline`, `pick_variation_for` | `modules/subtitle_json_builder.py:903`, `:1114`, `:1235`, `:1527` |
| `words_from_srt` | `modules/subtitle_align.py:205` |
| `load_wm_from_project` | `modules/wm_settings.py:176` |
| Cầu nối Adam: thư mục, khoá, `KhoaPlan`, `cmd_run`, đổi tên/xoá `.done.json`/`_hau_ky`, `sub_cfg_du_an` | `autovideo_audio_take.py:103-128`, `:470-489`, `:549-620`, `:1323-1349`, `:1494-1511`, `:1544` |
| Gom Poster bằng hardlink, `VIDEO_CUOI`, `_da_gom.txt` | `day_len_poster.py:33`, `:87`, `:95-134` |
| Worker: proxy video, duyệt, `tuyenViec`, `apiViec`, `BODY_VIEC_TOI_DA` | `cf/src/worker.js:186-191`, `:206-219`, `:225`, `:467-482`, `:636-662`, `:690-716`, `:739-757` |
| video_server: `THU_MUC`, `ds_nguon`, `RE_R`, act, `gui_file_range` | `tools/video_server.py:41`, `:106-116`, `:128-130`, `:297`, `:61` |
| Runner: `LoaiViec`, `DANH_MUC`, `dot_bat`, schema, route, `ma_du_an`/`ds_du_an`/`tim_du_an`, `BuocChay`, `MoiTruong.ffmpeg_ngoai`, chép bản cài | `danh_muc.py:143`, `:745`; `han_muc.py:19`; `kho_viec.py:27`; `api.py:629-676`; `du_an.py:39`, `:73`, `:79`; `kieu.py:49`, `:92-104`; `cai_runner.py:70` |
| Web: thẻ Duyệt, router, script | `web/app.js:525-564`, `:589-602`, `:778-792`; `web/index.html:8-12` |
| Python engine 3.12.11 + pytest 9.1.1; ffmpeg/ffprobe ở `F:\ffmpeg\bin` | đã chạy `--version` |
| (A-DOC2, 18/11) Bộ chuyển đổi đã sửa: `Khoa._cu/_go_cu/tha`, `PhienSua.chay`, `buoc_phu_de`, `buoc_render`, `buoc_nguon`, `hoan_nguyen`, `_hn_file`, `noi_lien_ket`, `GOC/MINH/KHAC/MAT`, `_xet_done`, `_xet_nguon`, `_xet_plan_json`, `_xet_phu_de`, `_xet_hoan_tac`, `_tu_choi_neu_moi_hon`, `hoan_tac`, `_khoi_phuc_nguon`, `_khoi_phuc_phu_de`, `chay` | `tools/runner/sua_video_engine.py:264`, `:283`, `:353`, `:737`, `:812`, `:867`, `:945`, `:1058`, `:1109`, `:1139`, `:1178`, `:1202`, `:1228`, `:1263`, `:1293`, `:1322`, `:1333`, `:1347`, `:1431`, `:1469`, `:1508` |
| Route chạy lại / chạy tiếp của runner (để chặn ở §7.2a) | `tools/runner/api.py:94`, `:845-846` |
