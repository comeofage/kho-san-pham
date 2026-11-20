# Giao diện menu trái: mỗi trang một việc (đợt 8)

Phiếu A-UI1 + A-UI1b (sửa sau phản biện R-UI1) · Kiến trúc sư Culiapp · 2026-11-18
Trạng thái: **ĐỀ XUẤT**. Quyết định mới: **D12** trong `DECISIONS.md` (Đề xuất).

Tri thức đã đọc: `DECISIONS.md` D1–D11, `.culiapp/nhat-ky.md` (ca 2026-11-18-b…e). Không có `CLAUDE.md`, `ARCHITECTURE.md`, `KNOWN_BUGS.md` ở gốc repo hay thư mục cha.

Mọi số dòng đọc lại ngày 18/11 sau ca P-33/P-33b:
- `web/app.js` không đổi so với lượt A-UI1;
- `cf/src/worker.js` đã dời dòng, số dòng dưới đây là bản mới;
- mốc JS: 239 pass.

**Người dùng đã chốt:**
- menu 6 mục;
- Đăng bài kiểu Poster V2;
- không bắt chấm hết;
- video Loại không được đăng;
- dọn trang SP;
- **video Loại: dời sang `_loai/` bằng việc miễn phí máy nhà** (cách A);
- **⛔ Ngừng đăng khoá Lên lịch**;
- không làm "folder trong danh sách";
- **linh/thu chỉ thấy Kho sản phẩm** (ca 2026-11-18-d).

---

## 0. Tóm tắt một màn hình

- **Menu mới của chủ kho:** 6 mục, Hôm nay · Sản phẩm · Cần quay · Duyệt video · Đăng bài · Máy nhà.
  - Màn ≥ 900px: cột trái 200px, giống sidebar 220px của Poster V2 (`E:/tool/tiktok_poster_v2/src/desktop/app.py:51-61`, `:125`).
  - Màn hẹp: thanh 6 ô dưới đáy.
- **Người không phải chủ kho:** giữ đúng giao diện P-33 hiện tại, 1 mục "Sản phẩm", không cột trái, không thanh đáy.
- **Đăng chỉ ở trang Đăng bài** (`#/dang`, `#/dang/<id>`).
  - Luồng: chọn SP → folder Poster + số Đạt / Loại / chưa chấm → số video/ngày → **Lên lịch đăng**.
  - Dùng việc có sẵn: `poster_len_lich`, chưa có folder thì `poster_day_folder` trước.
  - Vẫn duyệt bằng mật khẩu ở `#/viec/<id>` (D5, D9).
- **Video Loại.** Runner hiện không lọc video Loại (§1.1). Bịt bằng 2 lớp:
  - **B-L1 (backend, tuỳ chọn, khuyên làm):** việc miễn phí `poster_bo_loai` dời video Loại sang `_loai/`, hoàn tác được. Thêm điều kiện của `poster_len_lich` để chặn ở máy nhà, nên mọi đường duyệt / chạy lại đều bị chặn.
  - **Web (luôn làm):** chặn ở trang Đăng bài và ở **nút Duyệt** của việc `poster_len_lich`.
  - Không làm B-L1 thì còn lỗ hổng, ghi rõ ở §4.8.
- **Trang SP dọn trùng:**
  - bỏ tab ✅ Duyệt;
  - bỏ nút đăng trong khối việc;
  - dời "Tải về" sang Đăng bài; Tải về bỏ qua video Loại, không khoá nút;
  - gộp Rủi ro vào Tóm tắt;
  - "Bước tiếp theo" trỏ sang Duyệt / Đăng.
- **Giảm đụng độ:** phần mới nằm ở file mới (`web/khung.js`, `web/menu.css`, `web/dang.js`, `web/duyet.js`). `app.js` chỉ thêm ≤ 10 dòng móc ở lượt 1.
- **Phần web không đổi Worker.** B-L1 cần thêm **1 dòng** vào danh mục loại việc của Worker (`cf/src/worker.js:304-316`) và **không** đổi D5, D7, D9.

---

## 1. Điều tra

### 1.1 Đăng qua runner có loại video bị chấm "Loại" không? **KHÔNG**

1. **Chấm lưu ở đâu.** Chấm chỉ lưu ở GitHub, trong `data/<id>/duyet.json`.
   - Worker ghi ở `cf/src/worker.js:941-958`, mục `{goc, ten, sua_luc, mb, ket_qua, gop_y, boi, luc}` (`:954`, `KET_QUA` ở `:251`).
   - Chỉ chủ kho đọc được, qua `/api/sp/<id>` (`:965-974`, cờ `xemDuyet` ở `:969`).
2. **Video để chấm = file trong thư mục Poster đăng.**
   - `video_server` liệt kê `<GOC>/*<uid>/output_poster/*.mp4` và `…/output/*.mp4` (`tools/video_server.py:44`, `:109-119`). Khoá `goc`:
     - `output_poster` → `"<GOC posix>"`;
     - `output` → `"<GOC posix>#<tên dự án>/output"` (`:118`).
   - Folder Poster của mẻ Adam có `path = <dự án>/output_poster` (`C:/Users/Mi/.claude/skills/tao-video-tu-canh-quay/scripts/day_len_poster.py:162`).
   - Mẻ giọng creator lấy **`compose_output` nếu có, không thì `output`** (`F:/auto video oneshot/skill/scripts/day_poster.py:45`). Tên folder creator **không chứa UID** (`:6-7`, `:43-44`).
3. **`poster_day_folder` gom hết, không xét chấm.**
   - Runner chạy `day_len_poster.py` (`tools/runner/danh_muc.py:728-735`).
   - Script gom mọi file khớp `VIDEO_CUOI` từ `output-adam/` và `output_daonguoc/` (`day_len_poster.py:32-33`, `:108-111`) bằng hardlink (`:119-133`).
   - Script không đọc chấm.
4. **`poster_len_lich` không biết video nào.**
   - Tham số chỉ là `{folder_id, so_video_ngay}` (`danh_muc.py:389-399`).
   - Phiếu agent chỉ có `plan_folder/batch_schedule` (`danh_muc.py:928-941`, `tools/runner/phieu.py:234-237`).
   - Agent `aff-poster` không có luật về video Loại và bị cấm xoá video (`C:/Users/Mi/.claude/agents/aff-poster.md:41`, `:48-55`).
5. **Không ai đọc dữ liệu chấm.** `grep "duyet.json"` trên `tools/**/*.py` cho kết quả rỗng.

### 1.2 Poster V2 chọn video lúc lên lịch hay lúc đăng? **Lúc lên lịch**

Đọc code `E:/tool/tiktok_poster_v2`:
- `batch_schedule` (`src/backend/routers/folders.py:700-701`) gọi `builder._queue_single_local_video(...)`.
- Hàm đó (`src/backend/scheduler/queue_builder.py:229-271`):
  - liệt kê file trong `folder.path`;
  - bỏ file đã đăng hoặc đang chờ (`posted_video_names`, `:18-32`);
  - lấy file đầu (`:250-252`);
  - **ghi cứng `video_filename` + `video_path` vào bảng `queue`** (`:264-270`).
- `plan_folder` (`folders.py:417`) dùng cùng `QueueBuilder`.
- Job tự dựng hàng đợi `_build_queue_job` có định nghĩa (`src/backend/scheduler/jobs.py:112-119`). Trong `jobs.py` chỉ thấy chỗ định nghĩa này: không tìm thấy dòng nào đăng ký job này vào bộ hẹn giờ. Kết luận: hàng đợi chỉ dựng khi lên lịch.
- Không tìm thấy chỗ backend kiểm file còn tồn tại trước khi đăng: grep `video_path` + `exists|isfile|is_file` không ra.

**Hệ quả.**
- (a) Phải **dời video Loại khỏi folder TRƯỚC khi lên lịch**. Ghi chú "Poster tự quét lại output_poster" ở `day_len_poster.py:185-187` nói về lúc liệt kê / lên lịch, không phải lúc đăng.
- (b) Video bị chấm Loại **sau** khi đã vào hàng đợi:
  - Nếu vẫn ở chỗ cũ, Poster **vẫn đăng**.
  - Nếu B-L1 đã dời file đi, lượt đó trỏ file không còn. Khả năng cao là đăng **lỗi** thay vì đăng (chưa đo). `_retry_failed_posts` (`jobs.py:121`) có thể thử lại vài lần.
  - Muốn xoá hẳn khỏi hàng đợi phải dùng `delete_queue_item`. Thao tác này cần duyệt (`aff-poster.md:52`), làm tay trong app Poster, ngoài phạm vi.

### 1.3 Dữ liệu cho nhiều SP mà không gọi API từng SP

| Cần biết | Có trong `/api/ds` (index.json)? | Nguồn |
|---|---|---|
| SP đã có video | Có: `trang_thai === "da_lam_video"` | `tools/kho.py:290` |
| Thẻ `can_dang` / `ngung_dang` | Có | `tools/kho.py:292` |
| Folder Poster, số video | **Không**: index không có `da_lam_video` | `tools/kho.py:287-296`. Phải lấy qua `/api/sp/<id>` (`worker.js:965-974`) |
| Đạt / Loại | **Không** | `duyet.json` qua `/api/sp/<id>` |
| Số video còn, chưa chấm | **Không** | `/api/video/<id>/ds` (`worker.js:892-918`, chỉ chủ kho `:893`), có `nguon[].chi_tiet[{ten, mb, sua_luc}]` (`video_server.py:458-460`) |

Danh sách SP chỉ dùng `/api/ds`. Số liệu chỉ tải khi đã chọn 1 SP. Đúng như nhật ký ca 2026-11-18-b (`.culiapp/nhat-ky.md`, dòng "Chưa làm video chờ chấm…").

---

## 2. Bản đồ menu

### 2.1 File và tiền tố tên toàn cục (bắt buộc, P2-7)

| File | Nội dung | Tiền tố JS toàn cục | Tiền tố lớp CSS |
|---|---|---|---|
| `web/khung.js` (mới, W-M1) | `mnMENU`, `mnMuc`, `mnNavHtml`, `mnDsCanQuay`, `mnRoute`, `mnRenderCanQuay`, `mnRenderMayNha` | `mn` | `.mn-` |
| `web/menu.css` (mới, W-M1) | Bố cục cột trái / thanh đáy (§6) | – | `.mn-` + `.nav` |
| `web/dang.js` (mới, W-M2) | Trang Đăng bài | `dg` | `.dg-` |
| `web/duyet.js` (mới, W-M2) | Trang Duyệt video | `dy` | `.dyv-` (`.dy-` đã dùng cho trình phát Douyin, `app.js:819`) |

Mọi hàm thuần nằm trong khối marker `// --- <ten>-thuan start/end ---` để test nạp: `khung-thuan`, `dang-thuan`, `duyet-thuan`. Cách nạp giống `cf/test/homnay-web.test.mjs:18-27`.

### 2.2 Bảng mục

| Mục | Ic | Route (route cũ vẫn vào) | Nội dung | Tái dùng | Ai thấy |
|---|---|---|---|---|---|
| Hôm nay | 🏠 | `#/` | Như hiện tại | `renderHomNay` (`homnay.js:260-308`) | Chủ kho |
| Sản phẩm | 📦 | `#/kho`, `#/sp/<id>` | Danh sách kho + trang SP đã dọn (§5) | `renderList` (`app.js:140-168`), `renderDetail` (`app.js:474`) | **Mọi người** |
| Cần quay | 🎥 | `#/can-quay` | SP có bộ cảnh quay, chưa quay xong | `cardHtml` (`app.js:192-205`), `bindSwitches` (`app.js:233-267`), `quay` (`app.js:28-33`), `loadList` (`app.js:74-76`) | Chủ kho |
| Duyệt video | ✅ | `#/duyet`, `#/duyet/<id>` | Chọn SP → video ▶ Xem / Đạt / Loại / góp ý / ✏ Sửa | Logic tab Duyệt `app.js:576-712` chép sang `duyet.js` | Chủ kho |
| Đăng bài | ⬆ | `#/dang`, `#/dang/<id>` | §4 | `thamSoPoster` (`viec.js:515-521`), `locFolderPoster` (`viec.js:577-585`), `hanMucHtml` (`viec.js:396`), `taoViec` (`viec.js:847-870`), `theViecHtml` (`viec.js:130`), `bindVideo` (`app.js:942-985`) | Chủ kho |
| Máy nhà | ⚙ | `#/may-nha`; `#/viec`, `#/suc-khoe`, `#/viec/<id>` vẫn vào | Sức khoẻ (trên) + danh sách việc (dưới), huy hiệu "cần bạn" | `renderViec` (`viec.js:873-915`), `sucKhoeHtml` (`app.js:435-448`), `capNhatHuyHieuViec` (`viec.js:835-843`) | Chủ kho |

### 2.3 `mnMuc(hash, chu)` → tên mục đang mở

Kết quả ∈ `"hom-nay" | "kho" | "can-quay" | "duyet" | "dang" | "may-nha" | ""`.

| hash | Chủ kho | Người thường |
|---|---|---|
| `""`, `#`, `#/` | `hom-nay` | `kho` |
| `#/kho`, `#/sp/…` | `kho` | `kho` |
| `#/can-quay` | `can-quay` | `""` (trang chặn) |
| `#/duyet…`, `#/sua/…` | `duyet` | `""` |
| `#/dang…` | `dang` | `""` |
| `#/may-nha`, `#/viec…`, `#/suc-khoe` | `may-nha` | `""` |
| lạ | `""` | `kho` |

- Giữ `data-nav="kho"` và id huy hiệu `viec-hh` (`app.js:90`, `viec.js:829-834`). Huy hiệu nay nằm trên mục Máy nhà.
- Nhãn mục kho đổi "Kho sản phẩm" → "Sản phẩm" cho cả hai vai.

### 2.4 Móc vào `app.js` (lượt 1, ≤ 10 dòng, P1-2)

1. `renderUser` (`app.js:86-91`): `nav.innerHTML = auth.on ? mnNavHtml(laChu()) : ""`. Có dự phòng nếu chưa nạp `khung.js`: giữ chuỗi cũ khi `typeof mnNavHtml !== "function"`.
   - Bỏ link 🩺 ở góc phải (`app.js:82`): đã có mục Máy nhà.
   - Gán `document.body.dataset.vai = laChu() ? "chu" : "thuong"`.
2. `danhDauNav` (`app.js:102-111`): `const dang = typeof mnMuc === "function" ? mnMuc(location.hash, laChu()) : <biểu thức cũ>`.
   - Gán `document.body.dataset.trang = /^#\/sua\//.test(location.hash) ? "sua" : dang`.
3. `route()` (`app.js:891-918`): **một dòng** ngay sau dòng `const chu = laChu();` (`app.js:900`), trước `try`: `if (!m && typeof mnRoute === "function" && await mnRoute(location.hash, chu)) return;`.
   - `mnRoute` trả `true` khi đã xử lý hash: các route mới + `#/viec`, `#/suc-khoe`, kể cả trang chặn cho người thường.
   - Hash khác đi tiếp nhánh cũ.
   - Nhánh `#/viec`, `#/suc-khoe` cũ (`app.js:905-906`) thành chết; W-M3 xoá.
4. **P2-5:** `bindSwitches` gắn thẻ xong gọi `renderList()` (`app.js:243`). Trên trang Cần quay, việc này vẽ đè trang kho lên. Đổi thành `route()`, giống nhánh gạt quay ở `app.js:262`.

`mnRoute(hash, chu)`:
- Tăng `phienCT` cho mỗi trang (như `app.js:903-909`).
- Gọi `dungDang?.()` qua `typeof dgDung` và `dyDung` trước khi vẽ trang khác. `route()` cũ đã gọi `dungViec()` (`app.js:893`).
- Người thường mở `#/can-quay`, `#/duyet*`, `#/dang*`, `#/may-nha`: `#app` = `CHI_CHU_HTML` (`app.js:449`), trả `true`.
- Gọi `dgRenderDs()`, `dgRender(id)`, `dyRenderDs()`, `dyRender(id)` qua `typeof`. Lượt 1 chưa có thì hiện "Trang đang được cập nhật", nhưng W-M1 và W-M2 cùng lượt nên khi gộp đã có đủ.

### 2.5 Cần quay (`mnRenderCanQuay`, chủ kho)

`mnDsCanQuay(list, loc)`:
- lấy SP có `trang_thai` ∈ {`da_phan_tich`, `da_quay`};
- chip lọc:
  - `chua_gi` (mặc định): `da_phan_tich`;
  - `chua_oneshot`: `!quay(x,"oneshot").xong`;
  - `chua_review`: `!quay(x,"review").xong`;
- sắp xếp theo `soLoaiDaQuay` (`app.js:123`, `:147`).

Thẻ dùng `cardHtml` + `bindSwitches`. Gạt hay gắn thẻ xong gọi `route()` để vẽ lại đúng trang này (nhờ P2-5). Bấm thẻ thì ghi `sessionStorage.kho_tab="canh"` trước khi chuyển (`app.js:845`).

### 2.6 Máy nhà (`mnRenderMayNha`)

- Gọi `renderViec()`. Hàm này vẽ khung đồng bộ trước await đầu (`viec.js:876-885` trước `:914`).
- Ngay sau đó chèn `<section id="mn-sk">` lên đầu `.vt-khung`: nút "Kiểm lại" + `sucKhoeHtml(await api("suc-khoe"))`, viết lại trong `khung.js`, không sửa `renderSucKhoe`.
- `viec.js` (W-M1) chỉ đổi chữ:
  - "← Về kho" (`:876`) → "← Hôm nay" (`#/`);
  - tiêu đề (`:878`) → "⚙ Máy nhà";
  - "← Việc" (`:920`, `:922`) → "← Máy nhà" (`#/may-nha`).

---

## 3. Quyền

| Mục / route | Chủ kho (`nhan`, `comeofage`; `app.js:55`, `worker.js:180`) | Người thường (linh, thu) |
|---|---|---|
| Sản phẩm, `#/sp/<id>` | ✓ | ✓, giao diện P-33 như hiện tại |
| Hôm nay, Cần quay, Duyệt video, Đăng bài, Máy nhà | ✓ | ✗: menu không có. Mở bằng link thì ra `CHI_CHU_HTML`. Worker vẫn 403: `/api/viec*` (`worker.js:839`), `/api/video/*` (`:893`), `/api/duyet` (`:942`), `/api/suc-khoe` (`:921`) |

- Người thường: menu đúng **1 mục** "Sản phẩm". Không cột trái, không thanh đáy: CSS chỉ áp khi `body[data-vai="chu"]`, §6.
- Test P-33 (`cf/test/homnay-web.test.mjs:915-925`) giữ "đúng 1 mục", chỉ đổi nhãn.

---

## 4. Trang Đăng bài

File `web/dang.js`, tiền tố `dg`. Script thường, CSP `script-src 'self'` (`web/_headers`).

### 4.1 `#/dang`: chọn SP

- Chỉ gọi `loadList()` (`app.js:74`), tức `api("ds")`.
- `dgDsSpCoVideo(list, tim)`:
  - lọc `trang_thai === "da_lam_video"`, tìm theo tên / UID / shop;
  - xếp `can_dang` trước, `ngung_dang` cuối.
- Mỗi dòng: ảnh, tên, nhãn ⬆ / ⛔, nút "Chọn" → `#/dang/<id>`.

### 4.2 `#/dang/<id>`: 5 nguồn song song (`Promise.allSettled`)

| Nguồn | Dùng | Lỗi |
|---|---|---|
| `api("sp/<id>")` | `info` + `duyet` | Lỗi cả trang (như `app.js:478-479`) |
| `api("video/<id>/ds")` | Video còn trong `output_poster`/`output` | "Máy nhà tắt: không đếm được video" |
| `api("viec/suc-khoe")` | `dot_bat`, `han_muc`, `chan_ton_tien` (`tools/runner/api.py:601-610`) | "Bộ chạy việc không trả lời" |
| `api("viec/poster/folders")`, **chỉ gọi khi `dot_bat ≥ 4`**, cache theo phiên 60 s trong `dgCache` | Folder Poster `[{id, ten}]` | 502: "Poster V2 trên máy nhà chưa mở…" (câu runner `danh_muc.py:372`). 404 khi `dot_bat < 4` (`api.py:658-664`) |
| `api("viec?gioi_han=50")` | Việc `poster_*` đang mở / gần đây (lọc theo `tham_so.folder_id` hoặc `uid`; `poster_len_lich` không có `uid`, `danh_muc.py:389-399`) | Bỏ qua (runner vẫn trả 409 trùng, `viec.js:855-858`) |

Thêm `visibilitychange`: đăng ký **một lần** lúc nạp file. Chỉ tải lại khi `dgTrang && dgTrang.phien === phienCT`, giống `viec.js:821-823`.

### 4.3 Hàm thuần (interface; `duyet.js` và `viec.js` dùng lại)

```js
// dlv = info.da_lam_video → [{folder:number|null, nhan, so_video:number|null, duong_dan}]  (kiểu mới poster[] + kiểu cũ poster_folder/duong_dan; như app.js:517, :392-397)
function dgPosterCuaSp(dlv)

// Quy tắc ghép duong_dan (kho) ↔ nguon.goc (video_server.py:118); "\"→"/", bỏ "/" cuối, so không phân biệt hoa thường:
//   ".../<dự án>/output_poster" → goc = "<GOC>"              (GOC = cha của <dự án>)
//   ".../<dự án>/output"        → goc = "<GOC>#<dự án>/output"
//   ".../<dự án>/compose_output" → {chua_ho_tro: "compose_output"}  (video_server KHÔNG liệt kê, video_server.py:44)
//   khác / không thấy            → null
function dgNguonCuaPoster(duongDan, nguon)   // → nguon item | null | {chua_ho_tro}

// Đếm theo (goc, ten, sua_luc), mục duyệt SAU CÙNG thắng (như timDuyet app.js:591, tinhBuoc app.js:406-413); chỉ file còn trong chi_tiet.
// loaiCu: số file cùng (goc, ten) có mục "loai" ở sua_luc KHÁC (video đã sửa sau khi bị Loại → giờ là "chưa chấm", D10).
function dgDem(n, duyet)   // → {tong, dat, loai, chua, tenLoai:string[], loaiCu}
// Như trên nhưng gộp mọi nguồn (dùng khi không ghép được — thiên về chặt).
function dgDemTatCa(nguonDs, duyet)

// Folder lên lịch được: dòng dgPosterCuaSp có folder ∈ folders. Kho không ghi folder → folder runner có ten chứa đúng UID
// (folder Adam = tên thư mục dự án "<tên> <uid>", day_len_poster.py:162; folder creator KHÔNG chứa UID, day_poster.py:43-44
// → chỉ tìm được qua kho poster[]). → [{id, ten, nhan, duong_dan, tu_tim:boolean}]
function dgFolder(info, folders)

// Khoá nút Lên lịch: "" = được bấm; còn lại là câu lời thường (CHƯA esc). Thứ tự §4.5.
function dgLyDoKhoa(t)

// Kiểm Loại cho 1 folder khi KHÔNG ở trang Đăng bài (nút Duyệt của việc poster_len_lich, §4.8).
// → {kq: "sach"|"co_loai"|"khong_biet", so, cau}
function dgKetLuanLoai(folderId, folders, spTheoFolder, info, nguonDs, duyet)

function dgHtml(t)   // toàn trang, mọi chuỗi dữ liệu qua esc
```

### 4.4 Bố cục `#/dang/<id>`

1. "← Chọn sản phẩm khác", ảnh + tên, link `#/sp/<id>`.
2. **Mỗi folder** (`dgFolder`) có các dòng:
   - `#id · tên · nhãn`;
   - **Còn N · Đạt a · Loại b · Chưa chấm c**;
   - `chua_ho_tro`: "Folder lấy video từ compose_output, web chưa xem / chấm được thư mục này";
   - không ghép được: tổng mọi nguồn + "không ghép được folder với video trên máy nhà";
   - kho ghi mà Poster không có: "⚠ không thấy folder này trên Poster";
   - `b > 0`: tên video Loại (≤ 10) + link "Chấm lại ở Duyệt video";
   - `loaiCu > 0`: "N video đã sửa sau khi bị Loại, cần chấm lại".
3. **Form Lên lịch:**
   - chọn folder (radio, tự chọn khi chỉ có 1);
   - Số video/ngày 1–100 (`viec.js:513`, mặc định 1 như `viec.js:616`);
   - nhắc cạn: số/ngày > `dat + chua` → "đủ ~Y ngày";
   - `hanMucHtml("poster_len_lich", sk)`;
   - câu tốn tiền (`viec.js:593`);
   - nút **"Lên lịch đăng"**, kèm lý do khoá ngay dưới.
4. **Nút "Gỡ N video Loại khỏi folder"**: chỉ khi B-L1 đã có, tức `dot_bat` đủ và danh mục có `poster_bo_loai` (§4.9).
5. **"Đưa video sang Poster"** (`poster_day_folder`, miễn phí):
   - nổi bật khi chưa có folder;
   - có folder rồi thì là nút phụ "Gom thêm video mới vào folder" (`day_len_poster.py:188-195`);
   - danh sách dự án `api("viec/du-an/<uid>")` chỉ tải khi bấm (như `viec.js:1352-1381`);
   - `co_captions === false` thì khoá, kèm câu "Dự án chưa có 100 caption Poster" (`danh_muc.py:559-560`; `du_an.py:75`).
6. **Việc đăng đang mở / gần đây:** dùng `theViecHtml`. Dòng nhắc: "Video bị chấm Loại sau khi đã lên lịch vẫn nằm trong hàng đợi Poster; xoá khỏi hàng đợi phải làm trong app Poster" (§1.2 b).
7. `<details>` **"Tải video về điện thoại để đăng tay"**:
   - chỉ gọi `bindVideo` **khi mở** `<details>` (sự kiện `toggle`), lần đầu;
   - cảnh báo: tải xong, máy nhà xoá file (cả bản gốc) (`app.js:970`, `video_server.py:48-56`);
   - lượt 1 gọi `bindVideo(id)` như cũ;
   - lượt 2 gọi `bindVideo(id, { laLoai })`: nút tải **chọn video đầu tiên không bị Loại** (P2-2, §5).

### 4.5 `dgLyDoKhoa`: thứ tự

| # | Điều kiện | Câu |
|---|---|---|
| 1 | `viec/suc-khoe` lỗi | "Máy nhà đang tắt: bật máy rồi bấm Tải lại." |
| 2 | `sk.dot_bat < 4` | "Lên lịch đăng chưa được bật trên máy nhà (cần đợt 4). Vẫn đưa video sang Poster được." |
| 3 | `poster/folders` lỗi | "Poster V2 trên máy nhà chưa mở: mở app rồi bấm Thử lại." |
| 4 | `sk.chan_ton_tien` | "Máy nhà đang chặn việc tốn tiền (bản cài lệch), cần cài lại trên máy." (D9, `api.py:610`) |
| 5 | `info.ngung_dang` | "Sản phẩm đang gắn ⛔ Ngừng đăng: bỏ thẻ ở trang Sản phẩm nếu muốn đăng lại." (người dùng chốt) |
| 6 | Không có folder | "Chưa có folder Poster: bấm Đưa video sang Poster trước." |
| 7 | `video/<id>/ds` lỗi | "Không đếm được video trên máy nhà nên chưa biết còn video bị Loại hay không." |
| 8 | **`loai > 0`** (nguồn của folder đang chọn; không ghép được thì đếm mọi nguồn) | Có B-L1: "Folder còn N video bị Loại: bấm Gỡ video Loại trước." Không có B-L1: "Folder còn N video bị Loại, Poster sẽ đăng cả chúng. Chấm lại (Đạt hoặc Bỏ duyệt) hoặc dời video khỏi folder trên máy rồi Tải lại." |
| 9 | `dat + chua === 0` | "Folder không còn video nào để đăng." |
| 10 | Đã có `poster_len_lich` mở cho folder | "Đã có việc lên lịch đang chờ: xem và duyệt" (link `#/viec/<id>`) |

- Không có nhánh "chưa chấm hết".
- Nguồn `chua_ho_tro` (compose_output) không chấm được trên web nên không có Loại để chặn. Khi đó hiện câu riêng, không khoá.

### 4.6 Bấm "Lên lịch đăng"

1. `thamSoPoster` (`viec.js:515`).
2. `taoViec("poster_len_lich", …)` (`viec.js:847`; xử lý 409 ở `:855-858`).
3. Ghi `sessionStorage.dg_folder_sp[folder_id] = id SP`, dùng cho §4.8.
4. `location.hash = "#/viec/<id>"`. Việc ở `cho_duyet` (`danh_muc.py:1408`). Khung duyệt sẵn có (`viec.js:472-499`) cùng chốt Loại §4.8.

`poster_day_folder`: `taoViec("poster_day_folder", {uid, du_an})` → `#/viec/<id>`. Việc này miễn phí, tự chạy (`danh_muc.py:1370-1374`).

### 4.7 Máy nhà tắt

- Hiện folder theo kho, không có số liệu.
- Nút Lên lịch / Đưa sang Poster khoá theo §4.5 #1. Có "↻ Tải lại".
- Không tạo việc "chờ máy bật": POST `/viec` cần runner trả lời (`worker.js:528`).

### 4.8 Chốt Loại ở nút Duyệt (P1-1): mọi đường dẫn tới chạy `poster_len_lich`

Các đường có thể dẫn tới chạy việc:
- duyệt ở `#/viec/<id>`: tới từ Đăng bài, từ trang Việc, hay từ Hôm nay (`homnay.js:132-138` dẫn link `#/viec/<id>`);
- "↻ Xin duyệt lại" (`viec.js:789`) chỉ đưa việc về `cho_duyet`, nên vẫn phải qua nút Duyệt;
- "↻ Chạy lại" (`viec.js:791`) tạo việc mới, việc tốn tiền vào thẳng `cho_duyet` (D5).

→ **Chỉ cần chốt ở nút Duyệt** là chặn hết các đường phía web. Phía máy nhà do B-L1 lo (§4.9).

Thiết kế (W-M3):
- `khungDuyetHtml(d, opt)` (`viec.js:472-499`) thêm `opt.loai = {kq, cau}`:
  - `kq === "co_loai"` → nút Duyệt `disabled` + câu đỏ;
  - `"khong_biet"` → câu vàng "Không kiểm được video Loại của folder này: mở Đăng bài của sản phẩm để kiểm", **không khoá**;
  - `"sach"` → không thêm gì.
- `renderViecChiTiet` (`viec.js:918`): khi `loai === "poster_len_lich"` và `cho_duyet`, gọi `dgKetLuanLoai`. Ánh xạ folder → SP theo thứ tự:
  1. `sessionStorage.dg_folder_sp`;
  2. tên folder chứa đúng một chuỗi 19 số;
  3. không tìm được → `khong_biet`.

  Tìm được SP thì tải `sp/<id>` + `video/<id>/ds`.

**Còn hở khi KHÔNG làm B-L1:**
- (a) Folder creator lên lịch từ trang Việc, không qua Đăng bài: tên không chứa UID, nên ra `khong_biet` và chỉ cảnh báo.
- (b) Video bị chấm Loại sau khi đã lên lịch (§1.2 b).
- (c) Bất kỳ ai gọi thẳng runner. D7 chặn phần lớn trường hợp này.

### 4.9 B-L1: việc miễn phí `poster_bo_loai` (backend, tuỳ chọn, khuyên làm)

**Hành vi.**
- `poster_bo_loai {uid}` đưa folder về đúng kết quả chấm, theo hai chiều:
  - file ở cấp trên của `<GOC>/*<uid>/output_poster/` và `…/output/` có mục duyệt cuối khớp `(goc, ten, sua_luc)` là `loai` → `os.replace` sang `<thư mục>/_loai/<ten>`;
  - file trong `_loai/` mà mục duyệt cuối **không còn** là `loai` (người dùng bấm Đạt hoặc Bỏ duyệt) → chuyển về.
- **Hoàn tác** = chấm lại rồi chạy lại việc. Việc idempotent.
- `os.replace` cùng ổ nên nguyên tử và **giữ mtime**: `sua_luc = int(mtime)` (`video_server.py:458`) không đổi, khoá duyệt vẫn khớp.
- Poster không quét thư mục con (`day_len_poster.py:9`, `:99`).
- `day_len_poster` không gom lại tên đã có trong `_da_gom.txt` (`:124-125`), và chỉ gỡ link ở cấp trên (`:113-117`). `_loai/` an toàn.
- Không đụng `output-adam/`, `output_daonguoc/` (bản gốc của hardlink) và `compose_output/`.

**Dữ liệu chấm mới nhất.** Web ghi `duyet.json` thẳng lên GitHub. Repo máy nhà chỉ có bản mới sau `git pull`. Vì vậy:
- bước 1 chạy `kho.py xem <uid>`: hàm này gọi `keo()` = `git pull --rebase --autostash` (`tools/kho.py:311-313`, `:432-434`);
- việc giữ tài nguyên `kho` (mutex D1);
- bước 2 chạy `bo_loai.py`.

**Chặn ở máy nhà.**
- `poster_ds_folder.py` trả thêm `duong_dan` (`path` của folder; `list_folders` có trường này, `day_len_poster.py:192`).
- `g_poster_folders` **bỏ** `duong_dan` trước khi trả ra web (`api.py:662-668`).
- `_dk_poster_len_lich` (`danh_muc.py:583-586`) lấy `duong_dan` của `folder_id`:
  - thư mục dự án có tên kết thúc bằng UID và thư mục con là `output_poster`/`output` → đếm Loại bằng `duyet.json` trong repo;
  - còn Loại → `_viec_tay("Folder còn N video bị Loại: chạy 'Gỡ video Loại' ở trang Đăng bài, xong rồi Xin duyệt lại")`.
- Kiểm điều kiện chạy **trước** khi tiêu lời duyệt (`vong_lap.py:1462-1464`: tiêu ngay trước khi sinh tiến trình). Vì vậy không mất tiền, chỉ phải xin duyệt lại (D9).

**Phiếu B-L1 (culiapp-backend).**
- **ĐƯỢC SỬA:**
  - `tools/runner/danh_muc.py` (loại mới, `_dk_poster_len_lich`, `ds_folder_poster` giữ `duong_dan` nội bộ);
  - `tools/runner/bo_loai.py` (mới, thuần stdlib);
  - `tools/runner/poster_ds_folder.py`;
  - `tools/runner/api.py` (bỏ `duong_dan` khi trả ra);
  - `tools/test_runner_bo_loai.py` (mới), `tools/test_runner_danh_muc.py`, `tools/test_runner_api.py`;
  - `cf/src/worker.js`: **1 dòng** `["poster_bo_loai", [["uid"], []]]` trong `DANH_MUC_VIEC` (`:304-316`). Bắt buộc, vì Worker từ chối loại việc lạ;
  - `cf/test/worker.test.mjs`.
- **Chữ ký:**
  - `bo_loai.py --repo-kho <p> --uid <19 số> --goc <g>... [--xem]`;
  - in `DOI: <ten> -> _loai` / `TRA: <ten>` / `TONG: bo=N tra=M bo_qua=K`;
  - mã thoát: 0 = xong, 5 = có file bị khoá (bỏ qua, cần kiểm tay), 2 = lỗi dữ liệu.
- **Thuộc tính `LoaiViec`:** `dot=3`, `lan_chay="nhe"`, `ton_tien=False`, `tu_chay_lai=True`, `tai_nguyen={"poster","kho"}`, `tinh_khoa=uid`, `kiem_dau_ra` = quét lại, hết Loại thì `xong`.
- **Tiêu chí xong:**
  - pytest fixture thư mục tạm cho cả 2 chiều;
  - `sua_luc` lệch thì không dời;
  - mục sau thắng;
  - giữ mtime;
  - file khoá (giả `PermissionError`) thì mã 5;
  - không đụng `output_daonguoc`/`compose_output`;
  - `_dk_poster_len_lich` có Loại thì ra việc tay, không có thì `None`;
  - `/poster/folders` không lộ `duong_dan`.
- **Lệnh kiểm chứng:** `python -B -m pytest tools/test_runner_bo_loai.py tools/test_runner_danh_muc.py tools/test_runner_api.py -q -p no:cacheprovider` và `node --test cf/test/worker.test.mjs`.
- **Cần duyệt (trưởng phòng chạy):** cài lại runner (D8), deploy Worker.

**Rủi ro.**
- Windows khoá file đang phát hoặc đang tải (`video_server` stream, Poster upload): `os.replace` lỗi → bỏ qua file đó, mã 5.
- `git pull --autostash` của `kho.py` từng kéo lùi file đang sửa (sự cố ca 2026-11-18-d). Việc này giữ mutex `kho` như các việc đụng kho khác.
- Lượt đã vào hàng đợi Poster trỏ file đã dời: có thể đăng lỗi và thử lại (§1.2 b).
- `cf/src/worker.js` đang bị phiên khác sửa. Trưởng phòng xếp lượt.

**Nếu người dùng KHÔNG làm B-L1 đợt này:**
- Web vẫn chặn theo §4.5 #8 và §4.8. Lỗ hổng còn lại như cuối §4.8.
- Cách gỡ tạm cho người dùng:
  - chấm lại video đó (Đạt hoặc Bỏ duyệt) nếu chấm nhầm;
  - hoặc tự dời file khỏi `output_poster` trên máy (thư mục con bất kỳ). Trang Đăng bài hiện tên file cần dời.
- **Không** dùng `/api/video/<id>/xoa`: lệnh này xoá cả bản gốc (`video_server.py:48-56`).

---

## 5. Trang sản phẩm sau khi dọn (W-M3, lượt 2)

| Khối | Sau khi dọn |
|---|---|
| "Tải về" (`app.js:511`, gọi `bindVideo` ở `:543`) | Dời sang Đăng bài. `bindVideo(id, opt)` thêm `opt.laLoai(goc, ten, sua_luc)`: mỗi nguồn chọn **file đầu tiên trong `chi_tiet` không bị Loại**, rồi tải bằng `/file?goc&ten&xoa=1`. Worker nhận `ten` (`worker.js:232`). Hết video hợp lệ → "Không còn video nào chưa bị Loại". **Không khoá nút** (P2-2). |
| Dòng Video/Poster (`app.js:516-517`) | Giữ, thêm link "Đăng bài →" |
| "Bước tiếp theo" (`app.js:521`, `loi.js:185-208`) | Giữ, đổi bước 7–8 (bảng dưới) |
| "Xem đủ 8 bước" (`app.js:522-523`) | Đổi thành "Chi tiết 8 bước nhỏ" + dòng ánh xạ Chuẩn bị (1–2) · Quay (3) · Làm video (4–6) · Chấm và đăng (7–8), theo `loi.js:46-51` |
| Khối việc (`viec.js:1270-1304`) | `goiYViec(8)` (`viec.js:115`) bỏ `poster_*`, ghi chú "👉 Đăng ở trang Đăng bài". `goiYViec` ghi chú bước 7 "tab ✅ Duyệt" (`viec.js:109`) đổi thành "👉 Chấm ở trang Duyệt video". Giữ nút Douyin (`:117`). Giữ code form poster (`viec.js:608-625`, `:1335-1350`) |
| Gạt Oneshot/Review | Giữ |
| Tab ✅ Duyệt (`app.js:536`, `:576-712`) | Bỏ. `kho_tab="duyet"` cũ rơi về tab mặc định nhờ `show()` (`app.js:795`) |
| Tab Rủi ro (`app.js:533`) | Gộp vào "📋 Tóm tắt & rủi ro" (`app.js:557-559`); ánh xạ `kho_tab="ruiro"` → `"tt"` |
| Nhãn `BUOC_DS` "B7–8 Duyệt/Đăng" (`app.js:199`, `:346`) | Đổi sang `changChu(changTheoTrangThai(tt))` (`loi.js:42-44`, `:61-64`) |
| Nhánh `#/viec`, `#/suc-khoe` chết trong `route()` (`app.js:905-906`) + `renderSucKhoe` (`app.js:450-470`) | Xoá (giữ `sucKhoeHtml`) |

**Bước tiếp theo** (`buocTiepChu` ở `loi.js:192-200`; `buocTiepHtml` ở `loi.js:201-208` thêm `x.phu`):

| ht | Câu | Nút chính | Nút phụ |
|---|---|---|---|
| 7 | "Có video chưa chấm. Chấm thêm hoặc đăng luôn (video bị Loại không được đăng)." | "Chấm video" `trang:duyet` | "Đăng bài" `trang:dang` |
| 8 | "Video đã chấm, đến lượt lên lịch đăng." | "Đăng bài" `trang:dang` | – |

- Bộ nghe ở `app.js:848-858` xử lý `trang:duyet|dang` → `#/duyet/<id>` | `#/dang/<id>`.

**Hôm nay** (`homnay.js`):
- "Cách làm" dòng 4 (`:116`) → "Chấm video ở Duyệt video, rồi lên lịch ở Đăng bài.";
- SP `da_lam_video` không có việc chờ: nút trỏ `#/dang/<id>` (`homnay.js:141`).

**Màn sửa** (`sua.js`, P2-3): link "← Về sản phẩm" ở `sua.js:351` và `:382` → "← Về Duyệt video" (`#/duyet/<uid>`). SP có UID thì `id === uid`: Worker tạo `id = uid || "tam-…"`. `renderSua` chỉ nhận UID 19 số (`app.js:898`).

**Duyệt video** (`duyet.js`):
- `dyRenderDs()` dùng `dgDsSpCoVideo`.
- `dyRender(id)` tải `sp/<id>` + `video/<id>/ds`, vẽ thẻ + ✏ Sửa (`taiDsSua`/`veNutSua`, `app.js:642-659`) như tab cũ.
- Giữ khoá chống bấm đúp (`app.js:484-487`, `:679-697`) và luật "chỉ gộp mục của video vừa gửi" (`app.js:686-688`).
- Thêm thanh "Đạt · Loại · Chưa chấm" (`dgDem`) + nút "Đăng bài →".

---

## 6. CSS (`web/menu.css`, nạp sau `style.css`)

```css
:root { --mn-dau: 52px; --mn-rong: 200px; --mn-day: 58px; }
body[data-vai="chu"] .top { min-height: var(--mn-dau); box-sizing: border-box; }
body[data-vai="chu"] .nav a { position: relative; min-width: 0; }
body[data-vai="chu"] .nav .mn-chu { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

@media (min-width: 900px) {
  body[data-vai="chu"] { padding-left: var(--mn-rong); }
  body[data-vai="chu"] .nav { position: fixed; top: 0; left: 0; bottom: 0; z-index: 6; width: var(--mn-rong); max-width: none; margin: 0;
    flex-direction: column; gap: 2px; padding: calc(var(--mn-dau) + 8px) 8px 10px; overflow-y: auto; overflow-x: hidden;
    border-right: 1px solid var(--line); background: var(--card); box-sizing: border-box; }
  body[data-vai="chu"] .nav a { border: 0; border-radius: 8px; padding: 10px 12px; gap: 10px; justify-content: flex-start; }
  body[data-vai="chu"] .sua-thanh { left: var(--mn-rong); }      /* P3: .sua-thanh left:0 (style.css:275) đè cột menu */
}
@media (max-width: 899.98px) {
  body[data-vai="chu"] .nav { position: fixed; left: 0; right: 0; bottom: 0; z-index: 9; max-width: none; margin: 0;
    display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr);
    padding: 4px 2px calc(4px + env(safe-area-inset-bottom)); gap: 0; overflow: hidden;
    background: var(--card); border-top: 1px solid var(--line); }
  body[data-vai="chu"] .nav a { flex-direction: column; justify-content: center; gap: 2px; border: 0; border-radius: 8px;
    padding: 4px 0; font-size: 11px; min-height: 48px; }
  body[data-vai="chu"] .nav .huy-hieu { position: absolute; top: 2px; left: 55%; }
  body[data-vai="chu"] main { padding-bottom: calc(var(--mn-day) + 24px + env(safe-area-inset-bottom)); }
  body[data-vai="chu"] #toast { bottom: calc(var(--mn-day) + 16px + env(safe-area-inset-bottom)); }
  body[data-trang="sua"] .nav { display: none; }   /* màn sửa có .sua-thanh cố định đáy (style.css:275) */
}
```

**Ràng buộc:**
- Không cuộn ngang ở 375px.
- `.nav` của chủ kho không còn `overflow-x: auto` (`style.css:299`). Giữ `html, body { overflow-x: clip }` (`style.css:298`).
- Nhãn đáy ngắn (`ngan`): Hôm nay · Sản phẩm · Cần quay · Duyệt · Đăng bài · Máy nhà. Nhãn đủ dùng cho `aria-label` + cột trái.
- `.nav a.on` (`style.css:301`) + `aria-current` (`app.js:109`).
- Người thường: không có quy tắc nào áp (không có `data-vai="chu"`), nên giữ giao diện P-33.
- **Không sửa** `style.css`: mọi thứ mới nằm ở `menu.css`.

Mỗi ô menu là `<a href data-nav aria-label><span class="mn-ic" aria-hidden="true">…</span><span class="mn-chu">…</span>[huy hiệu]</a>`.

---

## 7. Tương thích link cũ

| Link | Sau đợt này |
|---|---|
| `#/` | Hôm nay (chủ) / Kho (người thường) |
| `#/kho`, `#/sp/<id>` | Như cũ (trang SP đã dọn; tab `duyet` → mặc định, `ruiro` → `tt`) |
| `#/viec`, `#/suc-khoe` | Trang Máy nhà, giữ nguyên hash |
| `#/viec/<id>`, `#/sua/<uid>/<ma>` | Như cũ |

Không redirect, không `replaceState` (tránh vòng `hashchange`, `app.js:920`).

---

## 8. Phân tích + rủi ro

1. **Tương thích.** Giữ mô hình script thường, biến toàn cục và `phienCT`. Thêm 4 file mới. `app.js` lượt 1 chỉ có móc (§2.4). API web, Worker, dữ liệu không đổi; B-L1 thêm 1 dòng Worker.
2. **Dependency.** Không thêm. CSP giữ nguyên.
3. **Tác động.**
   - `app.js`, `viec.js`, `loi.js`, `homnay.js`, `sua.js` (lượt 2).
   - Test cũ phải sửa:
     - `homnay-web.test.mjs:58-62` (chuỗi nav trong `renderUser`) và `:898-925` (fixture nav, nhãn "Sản phẩm");
     - `viec-web.test.mjs:38`, `:46`, `:65` (`goiYViec(8)`);
     - các test `buocTiepTheo` ở `homnay-web.test.mjs:388-412`.
4. **Đồng thời.**
   - Trang Đăng bài gọi ≤ 5 nguồn, 3 nguồn qua tunnel. Mức này ngang trang SP hiện tại (`app.js:872`, `viec.js:1261`).
   - Hai người cùng lên lịch: runner khoá `folder:<id>` (`danh_muc.py:1407`), web nhận 409 và đưa tới việc đang mở.
   - B-L1 giữ `poster` + `kho`.

| Rủi ro | Giảm |
|---|---|
| Video Loại vẫn bị đăng | §4.5, §4.8 (web) + B-L1 (máy nhà). Phần còn hở ghi ở cuối §4.8. |
| Ghép `duong_dan` ↔ `goc` sai; 2 dự án cùng UID trong 1 GOC gộp chung một `goc` (`video_server.py:114`) | Không ghép được thì đếm mọi nguồn (thiên về chặt) + câu báo. |
| Folder creator `compose_output` không chấm được | Câu riêng "chưa hỗ trợ", không giả là "sạch". Có test fixture. |
| **Trùng tên toàn cục giữa các script** (cùng phạm vi; `const` trùng là SyntaxError, cả trang chết) | Tiền tố `mn`/`dg`/`dy` + test §9 (P2-7). |
| Lượt 1 có cả tab Duyệt cũ lẫn trang Duyệt mới; Tải về chưa lọc Loại | **Không deploy giữa lượt 1 và lượt 2** (P2-2). Hai bản cùng ghi `/api/duyet` với cùng khoá, không lệch dữ liệu. |
| Thanh đáy che `.sua-thanh`, toast; bàn phím ảo Android | Ẩn ở màn sửa, dời toast, `padding-bottom`. Bàn phím: chấp nhận đợt này. |
| XSS qua tên SP / folder / video | `esc` (`app.js:9`) + test chèn `BAN` (`homnay-web.test.mjs:35`). |

---

## 9. Kế hoạch phiếu

**Lệnh kiểm chứng chung (P2-6), chạy ở gốc `E:/phantichcanhquay/kho-san-pham`:**

```
node --check web/app.js
node --check web/viec.js
node --check web/loi.js
node --check web/homnay.js
node --check web/sua.js
node --check web/khung.js
node --check web/dang.js
node --check web/duyet.js
node --test cf/test/worker.test.mjs cf/test/chu-ky-cheo.test.mjs cf/test/viec-web.test.mjs cf/test/sua-web.test.mjs cf/test/homnay-web.test.mjs cf/test/menu-web.test.mjs cf/test/dang-web.test.mjs cf/test/duyet-web.test.mjs
```

- Mốc: JS 239 pass, không được giảm.
- Trưởng phòng thêm 3 file test mới vào `LENH` của `.culiapp/kiem-chung.py`.

**Test bắt buộc chống trùng khai báo (P2-7)**, nằm trong `menu-web.test.mjs`:
1. Đọc `web/index.html`, lấy các `<script src>` theo đúng thứ tự (bỏ `vendor/`).
2. Nối nội dung các file đó.
3. `new vm.Script(noi)` phải không ném lỗi.
4. Thêm một kiểm tra: dùng regex lấy tên khai báo cấp đỉnh (`^(?:async )?function (\w+)`, `^(?:const|let|class) (\w+)`) của từng file. Không tên nào được xuất hiện ở 2 file. Mọi tên trong `khung.js`/`dang.js`/`duyet.js` phải bắt đầu bằng `mn`/`dg`/`dy`.

### Lượt 1 (song song, không trùng file)

**W-M1 · culiapp-web · Khung menu, Cần quay, Máy nhà**
- **ĐƯỢC SỬA:** `web/khung.js` (mới), `web/menu.css` (mới), `web/app.js` (chỉ móc §2.4, ≤ 10 dòng, gồm P2-5), `web/index.html`, `web/viec.js` (chỉ chữ / link ở `:874-878`, `:919-922`), `cf/test/menu-web.test.mjs` (mới), `cf/test/homnay-web.test.mjs`.
- **`index.html`:**
  - thêm `<link rel="stylesheet" href="menu.css?v=1">` sau `style.css`;
  - thêm script `khung.js?v=1`, `dang.js?v=1`, `duyet.js?v=1` theo thứ tự `loi` → `homnay` → `viec` → `khung` → `dang` → `duyet` → `app` → `sua`;
  - nâng `?v` của `app.js`, `viec.js`.
- **Interface:** `mnRoute(hash, chu) → Promise<boolean>`, gọi `dgRenderDs()`, `dgRender(id)`, `dgDung()`, `dyRenderDs()`, `dyRender(id)`, `dyDung()` nếu có.
- **Tiêu chí xong:**
  - `mnMuc` đủ bảng §2.3 cho cả 2 vai;
  - nav chủ 6 mục; người thường đúng 1 mục `#/kho` "Sản phẩm", không gọi huy hiệu;
  - `mnRoute`: người thường mở 4 route chủ kho thì ra `CHI_CHU_HTML`; `#/viec`/`#/suc-khoe` → Máy nhà; hash khác trả `false`;
  - `mnDsCanQuay` 3 chip;
  - gắn thẻ trên Cần quay không vẽ trang kho;
  - CSS tĩnh: `menu.css` có quy tắc `body[data-vai="chu"]`, `minmax(0, 1fr)`, `env(safe-area-inset-bottom)`, `body[data-trang="sua"] .nav`, `.sua-thanh { left: var(--mn-rong)`;
  - test P2-7;
  - `app.js` diff ≤ 10 dòng thêm/sửa (trưởng phòng soát);
  - mọi test cũ xanh.

**W-M2 · culiapp-web · Đăng bài + Duyệt video**
- **ĐƯỢC SỬA:** `web/dang.js` (mới), `web/duyet.js` (mới), `cf/test/dang-web.test.mjs` (mới), `cf/test/duyet-web.test.mjs` (mới).
- **Việc:**
  - §4.1–§4.7; §4.4 mục 4 (nút Gỡ Loại) chỉ hiện khi danh mục runner có `poster_bo_loai` (`api("viec/danh-muc")`, `viec.js:1327`);
  - `dgKetLuanLoai` (để W-M3 dùng);
  - `duyet.js` theo §5 phần "Duyệt video".
- **Tiêu chí xong:**
  - test thuần:
    - `dgPosterCuaSp`;
    - `dgNguonCuaPoster`: `output_poster`, `#…/output`, `compose_output` → `chua_ho_tro`, gạch ngược, hoa/thường, lệch → null;
    - `dgDem`: mục sau thắng, bỏ duyệt, `sua_luc` lệch → chưa chấm + `loaiCu`, file đã mất bị bỏ;
    - `dgFolder`: kho ∩ runner, dự phòng UID, folder creator không UID chỉ qua kho;
    - `dgLyDoKhoa`: đủ 10 nhánh đúng thứ tự, không có "chưa chấm hết", `ngung_dang` khoá, `dot_bat < 4`;
    - `dgKetLuanLoai`: 3 kết quả;
  - XSS;
  - fixture DOM giả `api` (như `homnay-web.test.mjs:769-798`):
    - `dgRenderDs` chỉ gọi `ds`;
    - `dgRender` gọi đúng 5 nguồn (`dot_bat < 4` thì không gọi `poster/folders`), không gọi `viec/du-an` trước khi bấm;
    - `bindVideo` chỉ chạy khi mở `<details>`;
    - Lên lịch gửi `{loai:"poster_len_lich", tham_so:{folder_id, so_video_ngay}}` → hash `#/viec/<id>`; 409 → việc trùng;
  - `duyet-web`: Đạt gửi đủ khoá và chỉ gộp mục video đó; bấm đúp không gửi 2 lần; đổi trang giữa chừng không vẽ đè.

**B-L1 · culiapp-backend · `poster_bo_loai`** (tuỳ chọn; chạy song song lượt 1 nếu người dùng duyệt; §4.9)

### Lượt 2 (sau W-M1, W-M2; deploy chỉ sau lượt này)

**W-M3 · culiapp-web · Dọn trang SP, chốt Loại ở nút Duyệt, nối Bước tiếp theo**
- **ĐƯỢC SỬA:** `web/app.js`, `web/loi.js`, `web/viec.js`, `web/homnay.js`, `web/sua.js`, `web/dang.js`, `web/index.html`, `cf/test/viec-web.test.mjs`, `cf/test/homnay-web.test.mjs`, `cf/test/menu-web.test.mjs`, `cf/test/dang-web.test.mjs`, `cf/test/sua-web.test.mjs`.
- **Việc:**
  - §5 toàn bộ;
  - §4.8: `khungDuyetHtml` nhận `opt.loai`, `renderViecChiTiet` gọi `dgKetLuanLoai`;
  - `dang.js` truyền `laLoai` cho `bindVideo`;
  - nâng `?v` các file đã đổi.
- **Tiêu chí xong:**
  - `goiYViec(8, …, 3|4)` không còn `poster_*`, còn `douyin_uid` khi chưa có Douyin;
  - ghi chú bước 7 không còn "tab ✅ Duyệt";
  - `buocTiepTheo(7)` → chính `trang:duyet` + phụ `trang:dang`; `(8)` → `trang:dang`;
  - trang SP không còn `data-tab="duyet"`, `data-tab="ruiro"`, `id="vd-btns"`;
  - thẻ kho hiện "Bước k/4";
  - `bindVideo` bỏ qua video Loại, chọn video kế (fixture: video 1 Loại → tải video 2; tất cả Loại → câu báo, không request);
  - `khungDuyetHtml` với `co_loai` thì nút Duyệt `disabled`, với `khong_biet` thì có câu cảnh báo, nút bật;
  - `sua.js` link `#/duyet/<uid>`;
  - mọi test xanh, tổng ≥ mốc.

### Lượt 3 (chỉ khi B-L1 xong)

**W-M4 · culiapp-web · Nối nút "Gỡ video Loại"**
- **ĐƯỢC SỬA:** `web/dang.js`, `web/viec.js` (`TEN_LOAI_VIEC`, `LOAI_VIEC_SP`), `web/loi.js` (`LOI_LOAI_VIEC`), `web/index.html`, `cf/test/dang-web.test.mjs`.
- **Tiêu chí xong:**
  - bấm "Gỡ N video Loại" thì `taoViec("poster_bo_loai", {uid})`;
  - câu khoá #8 đổi sang bản "có B-L1";
  - tên việc lời thường "Gỡ video bị Loại khỏi folder đăng".

### Trưởng phòng
- Thêm test mới vào `kiem-chung.py`.
- Thử `wrangler dev` cục bộ bằng dữ liệu giả ở 375px / 1280px: không cuộn ngang, thanh đáy không che nút cuối, màn sửa không có menu, trang Đăng bài đủ các trạng thái §4.5. Mức kiểm: `fixture`.
- Deploy (cần duyệt) chỉ sau lượt 2.
- B-L1: cài lại runner + deploy Worker (cần duyệt), xếp lượt với phiên đang sửa `worker.js`.

---

## 10. Câu hỏi cho người dùng: đã trả lời hết

- **Q1. Đã trả lời 18/11/2026: "Làm luôn đợt này".** Người dùng duyệt thiết kế: "Đồng ý, làm đi".
  - B-L1 (`poster_bo_loai`) chạy song song lượt 1, cùng W-M1 và W-M2. W-M4 làm sau khi B-L1 xong.
  - Cần duyệt riêng: cài lại runner (D8) và deploy Worker.
  - Trưởng phòng xếp lượt sửa `cf/src/worker.js` với phiên song song.
- D12 chuyển sang "Đã chốt (2026-11-18)".
