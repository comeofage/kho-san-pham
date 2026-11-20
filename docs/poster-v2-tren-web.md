# Poster V2 trên web Kho (mục menu thứ 7)

Phiếu A-PV1 · Kiến trúc sư Culiapp · 2026-11-18. Sửa theo phiếu A-PV1b (cùng ngày): 3 lựa chọn của người dùng (Q1–Q3 §11) và phản biện P1-1…P3-6.
Trạng thái: **ĐÃ CHỐT** (2026-11-18; người dùng duyệt thiết kế: "Đồng ý, làm đi", phiếu A-PV1c). Quyết định: **D13** trong `DECISIONS.md` (Đã chốt).

Tri thức đã đọc:
- `DECISIONS.md` D1–D12;
- `docs/giao-dien-menu-trai.md`, `docs/bo-chay-viec.md` §3;
- `.culiapp/nhat-ky.md` ca 2026-11-18-e;
- `tools/video_server.py`, `cf/src/worker.js`, `cf/wrangler.toml`, `web/index.html`, `web/_headers`, `web/khung.js`, `web/app.js` (đầu file + router), `web/dang.js` (đầu file);
- mã Poster V2 ở `E:/tool/tiktok_poster_v2` (chỉ đọc);
- bản port Svelte tham khảo `C:/Users/Mi/Agency` commit `a55d687`.

Gốc repo và thư mục cha không có `CLAUDE.md`, `ARCHITECTURE.md` hay `KNOWN_BUGS.md`.

Đã gọi thử backend Poster thật, chỉ GET, token đọc từ `.env` và không in ra:
- `/health` → `{"status":"healthy","version":"2.0.0"}`;
- `/api/v2/system/health` → `{"status":"ok",…,"database":"ok"}`;
- `/api/v2/queue/status` → `{"pending":12,"running":0,"done":6119,"failed":24,…}`;
- cổng `.env` = 8023.

**Hợp đồng (người dùng đã chốt):**
- 9 trang giống hệt app desktop Poster V2: cùng chức năng, nút, cột, bộ lọc, hộp xác nhận và chữ. Lỗi gốc giữ nguyên.
- Chỉ chủ kho dùng được.
- Đường đi: trình duyệt → Worker → video_server → backend :8023. Token Poster không rời máy nhà.
- Bấm thẳng mọi nút ghi: không qua việc/runner, không nhập mật khẩu từng lần.
- Không sửa mã Poster V2. Không đổi trang `#/dang` hay runner.

**Người dùng chốt thêm (A-PV1b):**
- Q1 → **"Mở hết /api/v2/"**: video_server chuyển tiếp mọi path dưới `/api/v2/` (và `/health`); không còn danh sách trắng.
- Q2 → **"Giữ nguyên như app gốc"**: không chặn video Loại, không hạn mức 100 video/ngày trên trang Poster V2.
- Q3 → **"Giữ, thêm dòng nhắc"**: giữ nút login + chữ gốc, thêm một dòng nhỏ dưới nút.

---

## 0. Tóm tắt một màn hình

- **Menu chủ kho có 7 mục.** Thêm "📮 Poster V2" (`#/poster`) vào cuối. Người thường vẫn chỉ có 1 mục "Sản phẩm" (P-33).
- **Bên trong `#/poster/<trang>`** là thanh 9 tab theo đúng thứ tự `NAV_ITEMS` (`E:/tool/tiktok_poster_v2/src/desktop/app.py:52-62`): Dashboard · Accounts · Folders · Calendar · Views · Queue · Đăng bài · Logs · Settings. Trên cùng có thanh trạng thái backend, tự kiểm 30 s một lần như `app.py:203-237`.
- **3 chặng mạng, mỗi chặng chỉ kiểm việc của chặng mình:**
  1. Worker `/api/poster/<rest>`: phiên đăng nhập, chủ kho, header `x-pv`, Origin, kích thước, lọc path thô.
  2. video_server `/p/<rest>`: `x-key`, **lọc path chung** (mọi `/api/v2/*`, chặn `..`/`%`/`//`/`\`/ký tự điều khiển), hợp đồng body §2.1, chốt riêng B1–B3/C1, gắn token, nhật ký.
  3. Backend `http://127.0.0.1:<TT_API_PORT|8023>`.
- **Mọi lời gọi tới backend chạy trong một luồng có khoá chống trùng** `(method, path?query, sha256(body))`. Lệnh trùng khoá đang chạy được gắn vào lệnh cũ, không gọi backend lần hai (§3.3).
  - Lớp L/DN (đăng video, login lấy cookie) trả `202 {cho}` ngay.
  - Lớp S chờ tối đa 80 s; quá thì tự chuyển nền và trả `202 {cho}`. Web hỏi `_kq`, rời trang thì chỉ ngừng hỏi.
  - `GET /_kq` liệt kê lệnh đang chạy; Đăng bài, Queue, Accounts gọi khi mở trang để khoá nút và hỏi tiếp.
- **Chỗ cần ổ đĩa máy nhà** có 2 route chỉ đọc của video_server: `_video/<folder_id>` (trang Đăng bài) và `_dem` (nút Test của Folders). Đường dẫn UNC / không có ổ đĩa bị từ chối. Browse thư mục không làm được trên web, phải gõ đường dẫn. Browse cookie đọc file trên chính máy đang mở web rồi đi qua `cookies_from_json`, đây là luồng sẵn có của app (§5).
- **Phần mới đặt ở file mới:**
  - `tools/poster_web.py`, `tools/poster_noi_gia.py` (máy chạy giả cho test nối 3 chặng);
  - `cf/src/poster.js`;
  - `web/poster.js`, `web/poster.css`;
  - 9 file `web/pv-*.js`;
  - 7 file test mới.

  Móc vào file cũ: `tools/video_server.py` ≤ 20 dòng, `cf/src/worker.js` 2 dòng, `web/khung.js` ≈ 8 dòng, `web/index.html` 11 dòng, cộng 2 file test cũ (`menu-web`, `homnay-web`) sửa số mục 6 → 7 và regex thứ tự script.
- **Không đổi:** D1–D12 về runner/việc, trang `#/dang`, `wrangler.toml`. Không thêm secret.

---

## 1. Kiến trúc 3 chặng

```
Trình duyệt (chủ kho, cookie kho_s)
  │  fetch /api/poster/<rest>   header x-pv: 1   (web/poster.js: pvGoi)
  ▼
Worker (cf/src/worker.js → cf/src/poster.js: apiPoster)
  │  phiên + chủ kho (403) · x-pv bắt buộc · Origin bắt buộc cho ghi · hợp đồng body §2.1 · lọc path thô
  │  fetch ${VIDEO_ORIGIN}/p/<rest>  header: x-key, x-poster-boi, content-type (chỉ POST/PUT/PATCH)   (timeout 95 s)
  ▼
Cloudflare Tunnel video.kutidak.com  (edge cắt ở ~100 s → 524)
  ▼
video_server 127.0.0.1:8787 (tools/video_server.py → tools/poster_web.py: xu_ly)
  │  x-key · lọc path chung · hợp đồng body · chốt B1–B3 · khoá chống trùng · trả lời Worker ≤ 85 s · nhật ký JSONL
  │  http.client → 127.0.0.1:<port>  header: Authorization: Bearer <token>, Accept, Content-Type (chỉ POST/PUT/PATCH)
  ▼
Poster V2 backend (FastAPI, production, account TikTok thật)
```

**Ranh giới:**
- **Core logic, thuần, test không cần mạng:**
  - `tools/poster_web.py`: lọc path, bảng lớp, hợp đồng body, chốt B1/B3, che secret C1, đọc `.env`, chốt chống chạm production, liệt kê/đếm video;
  - `cf/src/poster.js`: `kiemDuongPoster`, `kiemBodyPoster`;
  - khối `poster-thuan` trong `web/poster.js` và khối `pv<xx>-thuan` của từng trang.
- **Automation service:** `poster_web.xu_ly` + `BangLenh` (luồng gọi backend, khoá chống trùng, chuyển nền, nhật ký).
- **Giao diện:** `web/poster.js` (khung + client API) và `web/pv-*.js` (9 trang).

**Dùng chung logic:** `pvApi` trong `web/poster.js` là bản port 1:1 của `src/desktop/api_client.py`, dùng chung tên phương thức với `src/lib/poster/api.ts` của bản tham khảo. 9 trang chỉ gọi qua `pvApi`, không tự `fetch`.

---

## 2. Đường dẫn được chuyển tiếp và bảng tuyến 9 trang dùng

**Phạm vi (Q1 "Mở hết /api/v2/").** video_server chuyển tiếp **mọi** path dạng `/api/v2/<phần còn lại>` và đúng `/health`, với method GET/POST/PUT/PATCH/DELETE. Không có danh sách trắng. Path backend không tồn tại thì FastAPI trả 404/405 và video_server chuyển nguyên.

**Lọc path chung** (`poster_web.kiem_path`, chạy **trước** mọi việc khác; sai → 404 `{"loi":"Đường dẫn Poster không được phép"}`, không gọi backend):
- là `/health`, hoặc khớp `^/api/v2/[A-Za-z0-9_.~\-/]{1,200}$`;
- không có `%` (chặn `%2e%2e`, `%2f`, `%5c` và mọi dạng mã hoá), không có `\`, không có ký tự điều khiển (`\x00-\x1f`, `\x7f`);
- không có `//`, không có đoạn `.` hay `..` (tách theo `/`).

Method ngoài 5 method trên → 405 tại video_server (`do_HEAD`/`do_OPTIONS` mặc định của `BaseHTTPRequestHandler` trả 501, cũng không chuyển).

**Query:** chuyển nguyên sau khi kiểm chung: ≤ 512 ký tự, không ký tự điều khiển, không `#`. Không lọc theo khoá (không còn bảng khoá cho phép).

**Header:** như §4.3, không đổi.

Path viết đúng dấu `/` cuối như `api_client.py`. FastAPI redirect 307 khi lệch dấu `/`, và video_server không theo redirect.

### 2.1 Hợp đồng body và content-type chung cho cả 3 chặng (P1-1)

Một bảng duy nhất; `pvGoi` (web), `apiPoster` (Worker) và `poster_web.xu_ly` (video_server) cài đúng bảng này. Desktop luôn gửi `json=data or {}` cho POST (`src/desktop/api_client.py:91-96`), nên POST rỗng phải thành `{}` ngay từ trình duyệt.

| Method | Trình duyệt → Worker (`pvGoi`) | Worker kiểm và gửi → video_server | video_server kiểm và gửi → backend |
|---|---|---|---|
| GET | Không body, **không** `content-type` | Body khác rỗng → 400. Không gửi `content-type`. | `content-length > 0` → 400. Gửi không body, không `Content-Type`. |
| DELETE | Không body, **không** `content-type` | Body khác rỗng → 400. **Không** kiểm `content-type`, không gửi `content-type`. | `content-length > 0` → 400. Gửi không body, không `Content-Type`. |
| POST / PUT / PATCH | **Luôn** `content-type: application/json` và body `JSON.stringify(body ?? {})`; body rỗng = `{}` | `content-type` không bắt đầu bằng `application/json` → 415. Body rỗng → 400 `"Thiếu body JSON"`. > 256 KB (đo byte) → 413. `JSON.parse` lỗi → 400. Gửi nguyên byte body + `content-type: application/json`. | Như Worker (415 / 400 / 413 / 400). Gửi nguyên byte body + `Content-Type: application/json`. |

Bảng áp cho cả route riêng: `POST /_dem` theo dòng POST; `GET /_kq`, `/_video`, `/_thong_tin` theo dòng GET.

Kiểm chứng hợp đồng: unit ở từng phiếu (W-P1 cho `pvGoi`, W-P0 cho Worker, B-P1 cho video_server) **và** test nối 3 chặng T-P1 (§9) chạy thật `pvGoi → apiPoster → poster_web.xu_ly → backend giả HTTP cục bộ` cho từng method.

### 2.2 Bảng tuyến 9 trang dùng (chỉ để phân lớp và gắn chốt riêng)

Bảng này **không** còn là danh sách cho phép. Nó dùng để:
- phân lớp timeout S/L/DN (`poster_web.lop_cua`); path không có trong bảng **mặc định lớp S**;
- liệt kê lời gọi của 9 trang cho test `pvApi` (W-P1) và test nối 3 chặng (T-P1);
- ghi chỗ áp chốt riêng B1/B2/B3/C1.

Danh sách lấy từ mọi lời gọi `self.api.*` / `self._api.*` trong `src/desktop/pages/*.py` và `app.py`, cộng 2 dòng ngoài 9 trang nhưng cần lớp/chốt riêng (đánh dấu ✱).

**Ký hiệu:**
- `{id}` = `\d{1,9}`, `{key}` = `[A-Za-z0-9_.\-]{1,64}`.
- Lớp: **S** = chạy luồng, chờ đồng bộ tối đa 80 s rồi chuyển nền, hạn tổng 300 s; **L** = nền ngay, 300 s; **DN** = nền ngay, 360 s (§3).

| # | Method | Path backend | Lớp | Query 9 trang gửi | Chốt riêng | Trang dùng (`api_client.py`) |
|---|---|---|---|---|---|---|
| 1 | GET | `/health` | S | – | – | (dự phòng kiểm sống) |
| 2 | GET | `/api/v2/system/health` | S | – | – | thanh trạng thái (`health_check`) |
| 3 | GET | `/api/v2/stats/` | S | – | – | Dashboard |
| 4 | GET | `/api/v2/logs/` | S | `limit, offset, status` | – | Dashboard, Logs |
| 5 | GET | `/api/v2/logs/affiliate-stats` | S | `product_id` | – | Logs |
| 6 | GET | `/api/v2/accounts/` | S | – | – | Accounts, Folders |
| 7 | POST | `/api/v2/accounts/` | S | – | B1, B3 | Accounts |
| 8 | PUT | `/api/v2/accounts/{id}` | S | – | B1, B3 | Accounts |
| 9 | DELETE | `/api/v2/accounts/{id}` | S | – | – | Accounts |
| 10 | POST | `/api/v2/accounts/{id}/test-cookies` | S | – | – | Accounts |
| 11 | POST | `/api/v2/accounts/{id}/cooldown` | S | – | – | Accounts |
| 12 | DELETE | `/api/v2/accounts/{id}/cooldown` | S | – | – | Accounts |
| 13 | POST | `/api/v2/accounts/clean_profiles` | S | – | – | Accounts |
| 14 | POST | `/api/v2/accounts/login_and_capture` | **DN** | – | B1, B3 | Accounts |
| 15 | POST | `/api/v2/accounts/cookies_from_json` | S | – | B1, B3; `cookies` là mảng | Accounts |
| 16 | GET | `/api/v2/views/health/{id}` | S | – | – (GET này **có ghi** `account_health`, `views.py:440-447`) | Accounts |
| 17 | GET | `/api/v2/folders/` | S | `archived` | – (lần đầu ~84 s, §3.1) | Folders, Đăng bài |
| 18 | POST | `/api/v2/folders/` | S | – | B3 | Folders |
| 19 | PUT | `/api/v2/folders/{id}` | S | – | B3 | Folders |
| 20 | PATCH | `/api/v2/folders/{id}` | S | – | B3 | Folders (Lưu trữ / Khôi phục) |
| 21 | DELETE | `/api/v2/folders/{id}` | S | – | – | Folders |
| 22 | GET | `/api/v2/folders/{id}/suggest_phase` | S | `n` | – | Folders |
| 23 | GET | `/api/v2/folders/cadence_forecast` | S | `days` | – | Folders |
| 24 | GET | `/api/v2/folders/{id}/drive-test` | S | – | – | Folders (Test, nguồn drive) |
| 25 | POST | `/api/v2/folders/{id}/post_now` | S | – | – (backend trả ngay `started`, đăng trong luồng riêng, `folders.py:663-670`) | Folders (⚡ Đăng ngay) |
| 26 | POST | `/api/v2/folders/batch_schedule` | S | – | B3 | Folders (➕ Thêm vào Queue) |
| 27 | GET | `/api/v2/queue/` | S | `limit, offset, status` | – | Queue |
| 28 | GET | `/api/v2/queue/status` | S | – | – | Queue, Logs |
| 29 | POST | `/api/v2/queue/{id}/post` | **L** | – | – | Queue |
| 30 | POST | `/api/v2/queue/{id}/retry` | S | – | – | Queue |
| 31 | DELETE | `/api/v2/queue/{id}` | S | – | – | Queue |
| 32 | POST | `/api/v2/queue/unstick` | S | – | – | Queue (Gỡ kẹt, 📅 Lên lịch) |
| 33 | DELETE | `/api/v2/queue/pending/clear` | S | – | – | Queue |
| 34 | POST | `/api/v2/queue/reset-all` | S | – | – | Queue |
| 35 | POST | `/api/v2/queue/random_shuffle` | S | – | – | Queue |
| 36 | GET | `/api/v2/settings/` | S | – | **C1** | Queue, Settings |
| 37 | POST | `/api/v2/settings/autopost-on` | S | – | – | Queue |
| 38 | POST | `/api/v2/settings/autopost-off` | S | – | – | Queue |
| 39 | PUT | `/api/v2/settings/{key}` | S | – | C1 (phản hồi) | Settings: 4 khoá `headless`, `default_engine`, `telegram_bot_token`, `telegram_chat_id` (`settings.py:166-231`). Khoá khác cũng qua (Q1). |
| 40 | GET | `/api/v2/calendar/month` | S | `year, month, account_id` | – | Calendar |
| 41 | POST | `/api/v2/calendar/plans` | S | – | – | Calendar |
| 42 | DELETE | `/api/v2/calendar/plans/{id}` | S | – | – | Calendar |
| 43 | GET | `/api/v2/views/summary` | S | – | – | Views |
| 44 | POST | `/api/v2/views/refresh` | S | – | – | Views |
| 45 | POST | `/api/v2/post/direct` | **L** | – | B2, B3 | Đăng bài |
| 46 ✱ | POST | `/api/v2/queue/{id}/run` | **L** | – | – | Không trang nào gọi; cùng hàm với #29 (`queue.py:249-308`), xếp L để không chiếm luồng S 300 s |
| 47 ✱ | GET | `/api/v2/settings/{key}` | S | – | **C1** | Không trang nào gọi; che secret như #36 |

**Route riêng của video_server** (không chuyển sang backend; tiền tố `_` không trùng path backend nào vì backend chỉ có `/api/v2/*` và `/health`):

| Method | Path | Lớp | Việc |
|---|---|---|---|
| GET | `/_kq` | – | Liệt kê lệnh đang chạy (§3.3) |
| GET | `/_kq/<32 hex>` | – | Kết quả một lệnh (§3.3) |
| GET | `/_video/{id}` | S + quét đĩa ≤ 30 s | Liệt kê video của folder Poster (§5.1) |
| POST | `/_dem` | quét đĩa ≤ 30 s | Đếm video trong 1 thư mục, body `{"duong_dan": str ≤ 400}` (§5.2) |
| GET | `/_thong_tin` | – | `{backend: "http://127.0.0.1:<port>", co_token: bool, thu_muc, database, profiles}`, dùng cho thanh trạng thái và khối "Architecture Info" của Settings (`settings.py:84-97`). Không bao giờ trả token. |

### 2.3 Chốt riêng

Các chốt áp theo method + mẫu path, **kể cả path ngoài bảng §2.2**. Sai thì 400 `{"loi": …}`, không gọi backend.

- **B1, tên account.** Áp cho mọi POST/PUT/PATCH có path bắt đầu `/api/v2/accounts`. Nếu body có khoá cấp đỉnh `name` thì `name` phải là chuỗi 1–100 ký tự, **không chứa** `/`, `\`, `:` hay ký tự điều khiển, và **khác** `.` và `..`. Câu lỗi: `"Tên account không hợp lệ"`.
  - Lý do: backend ghép `get_profiles_dir() / account["name"]` rồi `rmtree` thư mục cache con, ở `POST /api/v2/accounts/{id}/clean-profile` (`src/backend/routers/accounts.py:481-505`). Tuyến này không có trong bảng §2.2 nhưng nay đi qua được (Q1). Tên `..` trỏ ra thư mục cha; tên có `:` (vd `C:x`) làm `Path / name` nhảy sang ổ khác trên Windows.
  - Vì đã cấm `/` và `\`, chuỗi chứa `..` ở giữa (vd `a..b`) vô hại và được nhận. Tên account TikTok thật không chứa các ký tự bị cấm, nên luật này không bớt tính năng.
- **B2, `post/direct`.**
  - `folder_id` nguyên dương, `video_path` là chuỗi;
  - video_server gọi `GET /api/v2/folders/{folder_id}` (`folders.py:300`, cùng luồng của lệnh) rồi kiểm `source == "local"`;
  - `folder.path` và `video_path` qua `la_duong_dan_o_dia` (B3);
  - `Path(video_path).resolve().parent == Path(folder.path).resolve()`;
  - file tồn tại, đuôi thuộc `.mp4 .mov .avi .mkv .webm`.

  Sai thì 400 `{"loi":"Video không nằm trong thư mục của folder"}`. Desktop chỉ chọn được video trong danh sách `Path(folder.path).glob` (`post.py:239-247`), nên luật này trùng đúng thứ UI tạo ra. Nó chặn trường hợp có phiên bị chiếm rồi đăng một file bất kỳ trên máy nhà. Q2 không đổi B2: B2 chặn đường dẫn, không chặn video Loại.
- **B3, đường dẫn trong body không phải UNC (P2-4).** Với mọi request có body: các khoá `path`, `video_path`, `cookies_path`, `chrome_profile_dir` **ở mọi cấp lồng** (duyệt dict/list) và `duong_dan` của `_dem`, nếu là chuỗi khác rỗng thì phải qua `la_duong_dan_o_dia`:
  - khớp `^[A-Za-z]:[\\/]`;
  - không bắt đầu bằng `\\`, `//` (gồm cả `\\?\`, `\\.\`);
  - không có ký tự điều khiển.

  Câu lỗi: `"Đường dẫn phải là thư mục/tệp trên ổ đĩa máy nhà (vd E:\\…), không nhận đường mạng"`. Lý do: Windows truy cập `\\host\share` sẽ tự gửi hash NetNTLM của user Mi tới máy lạ. Desktop chỉ tạo đường dẫn bằng hộp chọn tệp cục bộ nên không mất tính năng.
- **C1, che secret trong phản hồi Settings (P2-1).** Mọi phản hồi 2xx của path bắt đầu `/api/v2/settings` (GET `/settings/`, GET/PUT `/settings/{key}`), kể cả khi trả qua `_kq`: với mỗi cặp khoá–giá trị mà tên khoá (chữ thường) chứa `token`, `api_key`, `secret` hoặc `password` và giá trị khác rỗng, video_server thay giá trị bằng `"***"`.
  - Dạng `{key: value}` của `GET /settings/` (`settings.py:18-23`): xét từng khoá.
  - Dạng `{"key": k, "value": v}` của `GET/PUT /settings/{key}` (`settings.py:26-46`): xét `k`.
  - Desktop không hiện token: ô Bot Token là `QLineEdit.Password`, placeholder "Bot Token (ẩn khi đã lưu)", và xoá ô sau khi lưu (`pages/settings.py`, ô token `:67-69` và `_save_telegram_settings` `:190-231`). Web làm y vậy: ô token luôn trống, không dùng giá trị trả về.

**Path lạ:** không còn 404 "không có trong bảng". Path qua lọc chung thì chuyển backend; backend không có route thì trả 404 `{"detail":"Not Found"}`, web hiện "404: Not Found" theo `pvChuLoi`.

---

## 3. Timeout ở 3 chặng

### 3.1 Bảng

| Lớp | Trình duyệt | Worker → máy nhà | Edge/Tunnel | video_server | Desktop gốc |
|---|---|---|---|---|---|
| S (đọc + ghi ngắn, và mọi path ngoài bảng) | không đặt; nhận 202 thì hỏi `_kq` | `AbortSignal.timeout(95_000)` | ~100 s (524) | chờ đồng bộ tối đa **80 s** (monotonic); xong thì trả kết quả, chưa xong thì trả `202 {cho, toi_da_giay: 300}` và luồng chạy tiếp tới hạn tổng **300 s** | 30 s (`api_client.py:38`) |
| L (`queue/{id}/post`, `queue/{id}/run`, `post/direct`) | 202 ngay, rồi hỏi `_kq` 3 s/lần, tối đa 300 + 60 s | 95 s cho lệnh bắt đầu và cho mỗi lần hỏi | – | 202 ngay; luồng hạn tổng 300 s | 300 s (`_LONG`, `:39`) |
| DN (`login_and_capture`) | 202 ngay, rồi hỏi tối đa 360 + 60 s | như trên | – | 202 ngay; luồng hạn tổng 360 s | 360 s (`_LOGIN`, `:43`) |
| `_video`, `_dem` | – | 95 s | – | phần gọi backend như S; phần quét đĩa chờ tối đa 30 s, quá thì 504 | – |
| `_kq`, `_thong_tin` | – | 95 s | – | không gọi backend, trả ngay | – |

**Hạn tổng theo monotonic (P3-2).** `http.client` chỉ có timeout cho từng lần đọc socket, nên một backend nhả byte chậm có thể giữ kết nối quá 90 s. video_server đặt `deadline = time.monotonic() + han`; trước mỗi lần đọc đặt `sock.settimeout(max(0.1, deadline - time.monotonic()))`; hết hạn thì đóng kết nối và ghi kết quả 504. Handler trả lời Worker chậm nhất sau **80 s + thời gian ghi phản hồi (< 5 s) ≤ 85 s**, nên chặng trong luôn hết giờ trước Worker (95 s) và edge (~100 s). Kết nối: 5 s.

**Vì sao S chờ 80 s rồi chuyển nền thay vì 504 (P2-5):**
- Lần gọi đầu `/api/v2/folders/?archived=0` mất khoảng 84 s mới có byte đầu (bài học đã gặp). `folders.py` của backend khai báo `async` nhưng làm I/O đồng bộ, nên các lời gọi khác cũng chậm theo.
- Với 504, người dùng thấy lỗi rồi bấm Refresh, mở thêm một lần quét đĩa chồng lên lần đang chạy. Với chuyển nền + khoá chống trùng (§3.3), lần bấm sau gắn vào đúng lần quét đang chạy.
- Lệnh ghi S quá 80 s cũng chuyển nền, không trả 504 "CÓ THỂ đã chạy": người dùng thấy kết quả thật, và bấm lại trong lúc chờ không gây ghi lần hai.

### 3.2 Hành vi khi quá giờ (không bao giờ tự thử lại lệnh ghi)

| Trường hợp | Mã / chữ trả về | Web làm gì |
|---|---|---|
| S chưa xong sau 80 s | video_server `202 {"cho": ma, "toi_da_giay": 300}` | `pvGoi` tự hỏi `_kq`; mã trang không cần biết. |
| Luồng nền (S/L/DN) hết hạn tổng 300/300/360 s | `_kq` → `{"xong":true,"status":504,"body":{"loi":"Poster V2 chưa trả lời sau <n> s. Thao tác CÓ THỂ đã chạy: xem Logs/Queue trước khi bấm lại."}}` (GET: "Poster V2 trả lời quá chậm (> <n> s). Bấm Refresh/Làm mới.") | Hiện như lỗi gốc của lệnh. |
| Quét đĩa `_video`/`_dem` quá 30 s | 504 `{"loi":"Quét thư mục quá 30 s"}` | Hiện lỗi. |
| Worker > 95 s, hoặc edge 524 / không với tới máy nhà | Worker 504 / 502 `{"loi":…}` (câu như `LOI_CHAM_MAY_NHA` / `LOI_MAY_NHA`, `worker.js:221-225`). Lệnh ghi thì thêm "Thao tác CÓ THỂ đã chạy…". Không xảy ra khi video_server khoẻ vì nó trả lời ≤ 85 s. | Hiện lỗi, không gọi lại. |
| Web hỏi `_kq` quá hạn (`toi_da_giay` + 60 s) | – | Error "Quá giờ chờ kết quả: xem Logs/Queue." |
| `_kq/<ma>` 404 (video_server vừa khởi động lại) | 404 `{"loi":"Không còn theo dõi được lệnh này (máy phát video vừa khởi động lại). Xem Logs/Queue."}` | Hiện lỗi. |
| Hết chỗ chạy (§3.3) | 429 `{"loi": …}` | Hiện lỗi. |
| Backend tắt | 502 `{"loi":"Poster V2 trên máy nhà chưa mở"}` | Thanh trạng thái đỏ + lỗi của trang. Web không có nút "Mở app gốc" (§5.4). |
| Backend **401** (token lệch) | video_server đọc lại `.env` 1 lần, gọi lại **chỉ với GET**; vẫn 401 thì **đổi** thành 502 `{"loi":"Poster V2 từ chối token (TT_API_BEARER_TOKEN lệch)"}` | Không để 401 đi tới trình duyệt: `api()`/`pvGoi` hiểu 401 là hết phiên đăng nhập (`web/app.js:20`). |
| Backend **403** | **Chuyển nguyên** (P3-1). Backend dùng 403 cho câu bản quyền (`src/backend/license_guard.py:11-14`). | Hiện "403: <detail>" như desktop. |

### 3.3 Bảng lệnh và khoá chống trùng (`tools/poster_web.py: BangLenh`) (P1-2, P2-5)

- **Mọi** lời gọi backend (S, L, DN, và phần gọi backend của `_video`) chạy trong `threading.Thread(daemon=True)` do `BangLenh` quản lý. Mỗi lệnh có:
  - `ma = secrets.token_hex(16)`;
  - `khoa = (method, path_kem_query, sha256(body_bytes).hexdigest())` (GET/DELETE: sha256 của chuỗi rỗng);
  - `lop`, `bat_dau` (monotonic), `toi_da_giay`, `tom_tat` (§ dưới), `ket_qua` khi xong.
- **Trùng khoá đang chạy** → không gọi backend lần hai:
  - L/DN: trả lại `202 {"cho": <ma cũ>, "toi_da_giay": …, "trung": true}`;
  - S: handler mới cũng chờ trên lệnh cũ (chung hạn 80 s), rồi trả kết quả hoặc 202 với `ma` cũ.
  - Ví dụ: bấm "ĐĂNG NGAY" 2 lần, mở lại trang Đăng bài rồi bấm lại cùng video, 2 tab cùng Refresh Folders.
  - Lệnh đã xong thì khoá được nhả: bấm lại sau khi đã thấy kết quả là một lệnh mới, giống desktop.
- **Chỗ chạy:**
  - S: tối đa **6** luồng (gồm cả luồng S đã chuyển nền);
  - L: tối đa **1** luồng. Backend `post/direct` INSERT dòng `pending` **trước** khi lấy semaphore rồi 429 (`src/core/poster_api.py:73-87`); `queue/{id}/post` đưa dòng về `pending` trước semaphore (`src/backend/routers/queue.py:260-275`). Hai lệnh đăng song song từ web sẽ để lại dòng `pending` mồ côi mà scheduler đăng sau → đăng trùng. Vì vậy video_server chỉ cho 1 lệnh đăng mỗi lúc;
  - DN: tối đa **1** luồng (một Chrome login mỗi lúc);
  - hết chỗ → 429 `{"loi":"Đang có lệnh đăng/login khác chạy, chờ xong rồi thử lại"}` (L/DN) hoặc `{"loi":"Poster V2 đang bận"}` (S), **không** gọi backend. Kiểm trùng khoá trước, kiểm chỗ sau.
- **Bảng giữ tối đa 50 mục**; mục đã xong giữ 15 phút, đọc nhiều lần được. Đầy mà toàn mục đang chạy → 429 như trên.
- **Hỏi kết quả** `GET /p/_kq/<ma>`:
  - đang chạy → `200 {"xong": false}`;
  - xong → `200 {"xong": true, "status": <mã backend>, "body": <JSON backend đã qua C1 | {"loi": …}>}`;
  - mã lạ → 404 (câu §3.2).
- **Liệt kê** `GET /p/_kq` → `200 {"dang_chay": [{"cho", "method", "path", "lop", "giay_da_chay", "toi_da_giay", "tom_tat"}]}`, chỉ các lệnh `xong == false`. `path` gồm query. `tom_tat` chỉ chứa:
  - `post/direct`: `{"folder_id": int, "video": <tên file, không đường dẫn>}`;
  - `login_and_capture`: `{"name": str}`;
  - `queue/{id}/post|run`: `{"queue_id": int}`;
  - còn lại: `{}`.

  Không bao giờ chứa cookie, token hay giá trị body khác.
- **Phía web:**
  - `pvGoi` thấy `202` có `cho` thì gọi `pvCho(cho, toi_da_giay)` (hỏi 3 s/lần), rồi trả `body` hoặc ném lỗi như request đồng bộ. Mã trang không cần biết lệnh chạy nền.
  - **Rời trang** (đổi tab Poster, đổi mục menu, đăng xuất): `pvCho` chỉ ngừng hỏi và ném lỗi có `e.roiTrang = true`. Trang con đã theo quy ước "sau await: `if (!pvConSong(phien)) return;`" nên không vẽ, không hiện lỗi. Lệnh nền vẫn chạy ở máy nhà.
  - **Mở trang** Đăng bài, Queue, Accounts: gọi `pvApi.dangChay()` (`GET /_kq`) trước khi vẽ nút. Lệnh đang chạy khớp với nút nào thì nút đó bị khoá (disabled, chữ phụ "Đang chạy…"), rồi gọi `pvCho(cho, toi_da_giay)`; xong thì hiện kết quả như khi bấm và mở khoá. Ánh xạ:
    - Đăng bài: `POST /api/v2/post/direct` → khoá nút "ĐĂNG NGAY"; chọn sẵn folder `tom_tat.folder_id`;
    - Queue: `POST /api/v2/queue/{id}/post|run` → khoá nút đăng của dòng `queue_id`;
    - Accounts: `POST /api/v2/accounts/login_and_capture` → khoá nút "🔓 Tạo profile & Login lấy cookies".
  - **Folders** không cần gọi `dangChay()`: `getFolders` gửi đúng khoá của lần quét đang chạy, nên video_server tự gắn vào lần quét đó (không chồng lần quét mới).
- **video_server chết giữa chừng:** luồng chết, bảng lệnh mất (chỉ ở RAM). Backend nhiều khả năng vẫn làm tiếp; uvicorn không huỷ handler khi client ngắt, điều này **chưa đo**. Web nhận 404 ở `_kq` và câu "Xem Logs/Queue".

---

## 4. Bảo mật

### 4.1 Quyền

| Lớp | Kiểm |
|---|---|
| Web | Menu chỉ có mục Poster V2 khi `laChu()` (`web/app.js:55`). Người thường mở `#/poster*` thì `mnRoute` vẽ `CHI_CHU_HTML` (`web/khung.js:82`, `web/app.js:460`). |
| Worker | Phiên hợp lệ (`docPhien`, `worker.js:81`), nếu không thì 401. `laChuKho(user)` (`worker.js:180-181`), nếu không thì **403 trước mọi lần gọi máy nhà**. |
| video_server | `x-key` do `poster_web.xu_ly` tự kiểm (§7, P3-1). Không có khái niệm người dùng: tin `x-poster-boi` chỉ để ghi nhật ký, và chỉ sau khi `x-key` đúng. |

### 4.2 CSRF / Origin
- **Mọi** request tới `/api/poster/*`, kể cả GET, bắt buộc header `x-pv: 1`; thiếu thì 403 `"Thiếu x-pv"`. Trang khác không đặt được header tuỳ ý mà không qua preflight (Worker không trả CORS), và điều hướng cấp cao (link, form) không đặt được header. Lý do: có GET ghi dữ liệu (`GET views/health/{id}` ghi `account_health`, `src/backend/routers/views.py:440-447`; `GET folders/{id}/drive-test` gọi Google Drive), và cookie `SameSite=Lax` (`worker.js:92`) **có** đi theo điều hướng GET cấp cao từ trang khác.
- Mọi method khác GET trên `/api/poster/*` **bắt buộc** `Origin === url.origin`. Thiếu Origin cũng 403, như `apiViec` (`worker.js:842`). Chặn chung ở `fetch()` (`worker.js:1134-1137`) cho qua khi thiếu Origin, nên phải kiểm riêng.
- POST/PUT/PATCH bắt buộc `content-type: application/json` (§2.1). DELETE không có body nên không kiểm content-type; DELETE không phải method "simple" nên trang khác cũng phải preflight.
- Không còn câu "GET không có tác dụng phụ ghi" (sai, xem trên). GET có ghi được bảo vệ bằng `x-pv` + chủ kho.

### 4.3 Giới hạn path / header / kích thước

| Chặng | Luật |
|---|---|
| Worker (thô) | `rest` khớp `RE_REST_POSTER` (§7): `/api/v2/…` ký tự `[A-Za-z0-9_.~\-/]`, `/health`, `/_kq`, `/_kq/<32 hex>`, `/_video/<id>`, `/_dem`, `/_thong_tin`; không `//`, không đoạn `.`/`..`, không `%`. Method ∈ GET/POST/PUT/PATCH/DELETE. Query ≤ 512 ký tự. Body theo §2.1, ≤ 256 KB đo bằng byte. Chỉ gửi `x-key`, `x-poster-boi = phien.user`, `content-type` (chỉ POST/PUT/PATCH). **Không** chuyển cookie hay header nào của trình duyệt. |
| video_server (chặt) | Lọc path chung §2 + hợp đồng body §2.1 + chốt B1–B3. Gọi backend bằng request **mới**, chỉ có header `Authorization: Bearer <token>`, `Accept: application/json`, `Content-Type: application/json` (chỉ POST/PUT/PATCH). Không chuyển `x-key`, `x-runner-key`, `x-ky*`, `cookie`, `x-poster-boi`, `x-pv`. Phản hồi ≤ 4 MB (quá thì 502), qua C1, chỉ trả `content-type` JSON. |
| Token | Đọc **mỗi lần gọi** (P1-3), không giữ hằng lúc import: ưu tiên env `TT_API_BEARER_TOKEN` và `TT_API_PORT`; không có thì đọc `<poster_dir()>/.env`, với `poster_dir()` = env `KHO_POSTER_DIR`, mặc định `E:/tool/tiktok_poster_v2`. Cách đọc giống `_load_api_token` (`src/desktop/api_client.py:15-32`): bỏ dòng trống/`#`, cắt nháy. Cache theo `(đường dẫn .env, mtime)`. Token không vào log, không vào phản hồi, không vào nhật ký. |
| Chốt chống chạm production khi test (P1-3) | `cau_hinh()` gọi `chot_test(port, thu_muc)` trước khi trả. Đang chạy test (`"pytest" in sys.modules` hoặc env `KHO_POSTER_TEST=1`) mà `port == 8023` hoặc `thu_muc` resolve trùng `E:/tool/tiktok_poster_v2` → `raise RuntimeError("Test đang trỏ vào Poster V2 thật")`, không mở kết nối. |

### 4.4 Nhật ký ai bấm gì
- **Máy nhà:** video_server ghi 1 dòng JSONL cho **mỗi request khác GET** (gồm cả `_dem`), 1 dòng khi một lệnh chuyển nền, và 1 dòng khi lệnh nền kết thúc.
  - File: `%LOCALAPPDATA%\kho-poster-web\nhat-ky.jsonl`, đổi được bằng env `KHO_POSTER_NHAT_KY`. Quá 5 MB thì đổi tên sang `.1`, giữ 1 bản.
  - Ngoài repo, vì `kho.py` tự commit/pull trong repo (D8).
  - Mẫu:

    ```json
    {"luc":"2026-11-18T20:01:02+07:00","boi":"nhan","method":"POST","path":"/api/v2/folders/12/post_now","query":"","status":200,"ms":812,"body_sha256":"…","khoa_body":["visibility"],"cho":null,"trung":false}
    ```
  - **Không ghi giá trị body.** Cookie, `telegram_bot_token` và khoá Settings bất kỳ đi qua body.
  - Ghi lỗi thì in ra console, không làm hỏng request.
- **Worker:** `console.log` một dòng `{poster, method, path, user, status}` cho mỗi lệnh ghi (xem bằng `wrangler tail`). Không ghi body.

### 4.5 XSS
Mọi chuỗi từ backend qua `esc` (`web/app.js:9`), kể cả tên account/folder, caption, `error_message` của log, JSON chi tiết log. CSP `script-src 'self'` (`web/_headers`) nên sự kiện gắn bằng `addEventListener`, không dùng `onclick=`. Test mỗi trang chèn chuỗi `BAN` như `homnay-web.test.mjs`.

### 4.6 Rủi ro còn lại (ghi vào D13)
- Ai chiếm được phiên chủ kho (cookie 30 ngày, `worker.js:9`) thì thao tác được trên account TikTok thật: Đăng ngay, xoá, sửa cookie. Không còn lớp xác nhận thứ hai.
- **Mở hết `/api/v2/` (Q1)** nên phiên bị chiếm còn gọi được các tuyến app không dùng, ví dụ:
  - `PUT /api/v2/settings/<khoá bất kỳ>` (`settings.py:36-46`): đổi giờ ngủ, autopost, `anthropic_api_key`… (C1 chỉ che giá trị khi **đọc**);
  - `POST /api/v2/settings/backup-now`, `/settings/drive-reauth`, `/settings/clean-profile-cache`;
  - `POST /api/v2/queue/{id}/run` (đăng ngay 1 item, xếp lớp L);
  - `POST /api/v2/folders/{id}/autogen-captions` (`folders.py:387-413`), có thể gọi API sinh caption tốn phí nếu `caption_autogen` bật (chưa đọc sâu `QueueBuilder.autogen_captions_for_folder`);
  - `POST /api/v2/accounts/{id}/clean-profile` (đã có B1 bảo vệ tên).
- `PUT folders/{id}` nhận `path` tuỳ ý trên ổ đĩa máy nhà. Folder trỏ vào thư mục bất kỳ có video thì Đăng ngay / Thêm vào Queue sẽ đăng video ở đó. Desktop cũng vậy. B2 chỉ chặn `post/direct`; B3 chỉ chặn đường mạng.
- `POST/PUT accounts` nhận `cookies_path` và `chrome_profile_dir` tuỳ ý trên ổ đĩa máy nhà (B3 chặn UNC). Trỏ `chrome_profile_dir` vào profile Chrome thật của user thì backend mở Chrome bằng profile đó; trỏ `cookies_path` vào file khác thì backend đọc file đó làm cookie. Desktop cũng vậy.
- `_dem` cho biết một thư mục trên ổ đĩa máy nhà có tồn tại không và có bao nhiêu video (lộ thông tin nhẹ). Desktop cũng làm vậy cục bộ. UNC bị B3 từ chối.
- **Settings:** secret (`telegram_bot_token`, `anthropic_api_key`, mọi khoá chứa `token`/`api_key`/`secret`/`password`) **không** tới trình duyệt nhờ C1; giao diện chỉ biết có/không. Ghi đè thì vẫn được (như desktop).
- **Video Loại và hạn mức (Q2 "Giữ nguyên như app gốc").** Trang Poster V2 **không** chặn video Loại (D12) và **không** có hạn mức `poster_len_lich` 100 video/ngày/tài khoản cần duyệt (D9). Video Loại vẫn được `poster_bo_loai` tự dời khỏi folder sau mỗi lần chấm (`worker.js:1005-1006`). Nếu lần dời đó trượt (409 khi việc đang chạy, P1 R-45 còn treo) mà chủ kho bấm "Thêm vào Queue" / "⚡ Đăng ngay" ở trang Poster V2, video Loại có thể được lên lịch hoặc đăng. Số video đăng mỗi ngày qua trang này chỉ bị giới hạn bởi chính Poster V2.
- Lệnh đăng từ web và autopost/scheduler của Poster dùng chung semaphore của backend. Khi scheduler đang đăng, `post/direct` nhận 429 sau khi đã INSERT dòng `pending` (`poster_api.py:73-87`), để lại dòng mà scheduler sẽ đăng sau. Đây là hành vi gốc (desktop gặp y vậy); video_server chỉ ngăn được trường hợp 2 lệnh từ web.

---

## 5. Chỗ cần ổ đĩa máy nhà

### 5.1 Đăng bài: danh sách video của folder (`post.py:225-260`)
- Route `GET /p/_video/{folder_id}`. video_server gọi `GET /api/v2/folders/{id}` (lớp S, trong `BangLenh`) để lấy `{path, source}` **từ backend**. Web không gửi đường dẫn nào.
  - `source != "local"`, `path` rỗng, hoặc `path` không qua `la_duong_dan_o_dia` (UNC) → `{"ho_tro": false, "video": []}`. Web hiện đúng câu gốc "Folder rỗng hoặc nguồn không hỗ trợ".
  - Ngược lại → liệt kê y `post.py:239-247` (chờ tối đa 30 s, quá thì 504):
    - với từng đuôi theo thứ tự `*.mp4, *.mov, *.avi, *.mkv, *.webm`, gọi `Path(path).glob(ext)` (không đệ quy);
    - bỏ tên chứa `_posted` hoặc `okkkk`;
    - trả `{"ho_tro": true, "video": [{"name", "path", "size"}]}`.

    `path` cần cho `post/direct`; B2 kiểm lại lúc đăng.
- Thư mục không tồn tại → `{"ho_tro": true, "video": []}`. Desktop cũng ra danh sách rỗng.
- Folder 404 → chuyển nguyên 404 của backend.
- Quét đĩa chạy trong luồng chiếm 1 chỗ S (§3.3), không chạy ngoài giới hạn.

### 5.2 Folders: nút 🔌 Test với nguồn local (`folders.py:182-198`)
- Route `POST /p/_dem` với body `{"duong_dan": "<chuỗi trong ô Path>"}`:
  - `duong_dan` không qua `la_duong_dan_o_dia` (B3) → 400 câu B3;
  - thư mục tồn tại → `{"ton_tai": true, "so_video": n}`, đếm `iterdir()` có đuôi `.mp4 .mov .avi .webm` (đúng bộ đuôi của `folders.py:192`);
  - không tồn tại → `{"ton_tai": false, "so_video": 0}`.
  - Chạy trong luồng chiếm 1 chỗ S, chờ tối đa 30 s, quá thì 504.
- Web hiện đúng 2 hộp gốc: "Thư mục Local hợp lệ!\nTìm thấy {n} video." / "Thư mục local không tồn tại.". Lỗi 400 B3 hiện qua `pvThongBao` kiểu warning.
- Nguồn drive giữ nguyên lời gọi `drive-test` (tuyến 24).

### 5.3 Không bê 1:1 được, kèm phương án

| Chỗ | Desktop | Web | Lý do |
|---|---|---|---|
| Folders "📁 Browse" (`folders.py:178-180`) | Hộp chọn thư mục của Windows | **Bỏ nút.** Ô Path vẫn gõ/dán được (desktop cũng cho gõ). Dưới ô có chữ "Gõ đường dẫn thư mục trên máy nhà, rồi bấm 🔌 Test". | Trình duyệt không duyệt được ổ máy nhà. Một trình duyệt thư mục từ xa qua Internet là mặt tấn công mới, không làm. |
| Accounts "Browse..." cookie (`accounts.py:161-164`) | Chọn file JSON trên máy nhà, ghi **đường dẫn** vào `cookies_path` | Nút "Browse..." mở `<input type="file" accept=".json,application/json">`. File được đọc **trên máy đang mở web**, nội dung đổ vào ô JSON cookies (`raw_cookies_input`). Bấm Save → `cookies_from_json` (`accounts.py:216-239`), backend tự lưu file và trả `cookies_path`. Ô `cookies_path` vẫn gõ tay được (B3 chặn UNC). | Đây là luồng dán JSON sẵn có của app. Kết quả như nhau: account có file cookie trên máy nhà. |
| Settings "Architecture Info" (`settings.py:84-97`) | Đọc `get_app_home()` cục bộ | Lấy từ `_thong_tin`: `thu_muc = poster_dir()`, `database = <thu_muc>/v2_data.db`, `profiles = <thu_muc>/profiles_v2` (`src/core/paths.py:54-59`) | Không chạy mã Poster trong video_server. Nếu Poster chạy bản đóng gói (dữ liệu ở `%APPDATA%`), đặt `KHO_POSTER_DIR` cho đúng. |
| Settings "Bản quyền" (`settings.py:100-113`) | Chỉ hiện khi `licensing.is_enforced()` = bản đóng gói hoặc `TT_LICENSE_ENFORCE=1` (`src/licensing/runtime.py:82-83`) | **Không vẽ.** Máy nhà đang chạy từ mã nguồn nên desktop hiện tại cũng không hiện khối này. | Cần module Python cục bộ. |
| Settings ô "Bot Token" | `QLineEdit.Password`, placeholder "Bot Token (ẩn khi đã lưu)", lưu xong xoá ô, placeholder "*** (đã lưu)" | Y vậy: `<input type="password">` luôn trống khi tải, cùng placeholder. Giá trị `"***"` từ C1 không được đổ vào ô. Lưu theo đúng nhánh `_save_telegram_settings` (`settings.py:190-231`): ô trống thì không gửi khoá đó. | Không đổi hành vi; chỉ ghi rõ để không ai đổ `"***"` vào ô rồi lưu đè token thật. |
| "🔓 Tạo profile & Login lấy cookies" (`accounts.py:166-198`) | Mở Chrome **trên máy nhà** để đăng nhập | Giữ nút và chữ y nguyên, chạy lớp DN (§3.3). **Thêm một dòng nhỏ ngay dưới nút** (Q3): `Cần người ngồi ở máy nhà để đăng nhập trên Chrome vừa mở` (lớp `.pvac-nhac`, cỡ chữ nhỏ, màu phụ). | Chrome vẫn mở trên màn hình máy nhà; người ở xa không đăng nhập được trong cửa sổ đó. Người dùng chọn "Giữ, thêm dòng nhắc". |
| Thanh trạng thái `V2 Backend: <url>` (`app.py:189`) | URL cục bộ | Hiện `backend` từ `_thong_tin` (`http://127.0.0.1:8023`) | – |
| Thông báo ngắn trên thanh trạng thái (`status_bar.showMessage`) | Chữ ở thanh trạng thái cửa sổ | Gọi `toast(msg)` sẵn có (`web/app.js:57-60`), không tự viết bản riêng (P3-3). | Web đã có một vùng `#toast` dùng chung (`web/index.html:46`). |

### 5.4 Không làm trên web
- Mở **app desktop** Poster, hoặc chạy `start.bat` / `backend_only.bat`. (Đổi 2026-11-19 theo yêu cầu người dùng: web **được** bật riêng backend, xem dưới.)

### 5.5 Thanh trạng thái + nút "Bật Poster V2" (2026-11-19)
- Thanh trạng thái không nhại nguyên câu lỗi mà nói chặng nào hỏng: mất mạng / Worker không với tới máy nhà (video_server hoặc tunnel tắt → chạy `tools/chay_video.bat`) / sai `VIDEO_KEY` / Poster chưa chạy (`ma: "chua_mo"`) / sai token (`ma: "token"`) / chậm (504) / Poster web đang tắt (503).
- Poster chưa chạy hoặc lỗi lạ → nút **Bật Poster V2** → `POST /api/poster/_bat_backend {}` → video_server `POST /p/_bat_backend` (`tools/poster_web.py: bat_backend`):
  - cổng đang là Poster (`/health` = `{"status":"healthy","version":"2.x"}`) → 200 `{"trang_thai":"da_chay"}`, không mở gì;
  - cổng bị chương trình khác chiếm → 409 `{"ma":"cong_la","loi":"Cổng … đang bị <tên.exe> (PID n) chiếm…"}`, không mở gì;
  - cổng trống → mở `python -B -m src.backend.main` (Python312 như `start.bat`, đổi bằng env `KHO_POSTER_PYTHON`) trong cửa sổ console riêng, cwd = thư mục Poster, env `API_PORT`/`TT_API_PORT` = cổng đang hỏi → 200 `{"trang_thai":"dang_bat","pid"}`; bấm lại trong 60 s khi tiến trình còn sống không mở thêm.
- Web hỏi health 2 s/lần, tối đa 45 s ("Đang khởi động Poster V2... (n s)"); quá hạn thì bảo xem console trên máy nhà. Mỗi lần bấm ghi một dòng `su_kien: "bat_backend"` vào nhật ký Poster web.
- `running_count_quick` (`app.py:99`): desktop chỉ dùng khi đóng cửa sổ.
- Phím tắt Ctrl+1..9 và Ctrl+R làm mới trang (`app.py:191-199`): không thêm. Ctrl+R trên trình duyệt là tải lại cả trang.

---

## 6. Web: khung, file, quy ước tên

### 6.1 Route và móc vào `web/khung.js` (≈ 8 dòng, W-P1)
1. `mnMENU` (`khung.js:9-16`) thêm dòng thứ 7: `{ ma: "poster", href: "#/poster", ic: "📮", ten: "Poster V2", ngan: "Poster" }`.
2. `mnPhanTichHash` (`khung.js:20-31`) thêm, trước dòng `dang|duyet`: `#/poster` hoặc `#/poster/<x>` → `{ trang: "poster", id: x || "" }`.
3. `mnMuc` (`khung.js:36`): thêm `poster: "poster"` vào bảng ánh xạ.
4. `mnRoute` (`khung.js:76-96`):
   - đầu hàm thêm `if (typeof pvDung === "function") pvDung();`;
   - danh sách trang thêm `"poster"`;
   - nhánh `poster` gọi `pvRender(id)` qua `typeof`, chưa có thì vẽ `mnCHUA_CO`.
   - Người thường đã được nhánh `!chu` (`:82`) lo.

**Hệ quả kèm theo:**
- Thanh đáy điện thoại có 7 ô (`grid-auto-columns: minmax(0, 1fr)` trong `web/menu.css`); không sửa `menu.css`.
- Hash `#/poster/<x>` lạ hoặc rỗng → Dashboard. Giải mã `x` bằng `decodeURIComponent` trong `try`.
- **Đăng xuất / 401 không đi qua `mnRoute`** (P2-3): `route()` trả về ở `if (!auth.on) {… return; }` (`web/app.js:744`) **trước** khi gọi `mnRoute` (`:751`), nên `pvDung()` ở đầu `mnRoute` không chạy. Vì vậy `pvGoi` tự gọi `pvDung()` khi gặp 401, và `pvHenGio` tự bỏ lượt khi `!auth.on` (§6.4).

### 6.2 `web/index.html` (W-P1)
- Sau `menu.css?v=1` thêm `<link rel="stylesheet" href="poster.css?v=1">`.
- Sau `duyet.js` và **trước** `app.js` thêm 10 script `defer`:
  - `poster.js?v=1`;
  - `pv-dashboard.js?v=1`, `pv-accounts.js?v=1`, `pv-folders.js?v=1`, `pv-calendar.js?v=1`, `pv-views.js?v=1`, `pv-queue.js?v=1`, `pv-post.js?v=1`, `pv-logs.js?v=1`, `pv-settings.js?v=1`.
- Nâng `khung.js?v=2`.
- File trang chưa có ở lượt 1 thì trình duyệt chỉ báo 404 cho script đó; test P2-7 tự bỏ qua file thiếu (`cf/test/menu-web.test.mjs:421-428`). **Không deploy trước khi đủ 9 file.**

**Test cũ có kiểm thứ tự script/CSS (P2-2), đã rà hết `cf/test/*.mjs`:**

| Test | Kiểm gì | Sau khi chèn 10 script + `poster.css` | Ai sửa |
|---|---|---|---|
| `cf/test/homnay-web.test.mjs:323-325` | Regex `duyet.js` **liền trước** `app.js` | **Vỡ** | W-P1: thêm `poster.js` + 9 `pv-*.js` vào regex, đúng thứ tự §6.2 |
| `cf/test/menu-web.test.mjs:403-409` | `deepEqual` danh sách CSS `["style.css","menu.css"]` và danh sách script | **Vỡ** | W-P1: thêm `poster.css` và 10 script |
| `cf/test/menu-web.test.mjs:421-444` | P2-7 bảng tiền tố | Thiếu 10 file mới | W-P1: thêm `poster.js: "pv"` và 9 tiền tố §6.3 |
| `cf/test/viec-web.test.mjs:369` | `viec.js` … `app.js` với `[\s\S]*?` | Không vỡ | – |
| `cf/test/sua-web.test.mjs:293` | `app.js` liền trước `sua.js` | Không vỡ (chèn trước `app.js`) | – |
| `cf/test/viec-web.test.mjs:1049-1052`, `:725`, `:885`, `:1003` | Chỉ số `?v=` | Không vỡ | – |
| `cf/test/homnay-web.test.mjs:332`, `viec-web.test.mjs:368`, `sua-web.test.mjs:296` | Không script inline | Không vỡ | – |

### 6.3 File và tiền tố (P2-7: mọi tên cấp đỉnh bắt đầu bằng tiền tố của file, so không phân biệt hoa thường)

| File | Tiền tố JS | Lớp CSS | Nguồn desktop (dòng) | Bản tham khảo Svelte (dòng) | Phiếu |
|---|---|---|---|---|---|
| `web/poster.js` | `pv` (xem luật tránh va dưới bảng) | `.pv-` | `app.py` (323), `api_client.py` (358), `widgets/common.py` (`confirm_destructive` `:262`) | `PosterV2.svelte` (233), `api.ts` (202) | W-P1 |
| `web/poster.css` | – | `.pv-` | `theme.py` (tham khảo màu) | style trong các `.svelte` | W-P1 |
| `web/pv-dashboard.js` | `pvdb` | `.pvdb-` | `pages/dashboard.py` (171) | `Dashboard.svelte` (137) | W-P2 |
| `web/pv-views.js` | `pvvi` | `.pvvi-` | `pages/views.py` (304) | `Views.svelte` (233) | W-P2 |
| `web/pv-logs.js` | `pvlo` | `.pvlo-` | `pages/logs.py` (371) | `Logs.svelte` (353) | W-P2 |
| `web/pv-settings.js` | `pvse` | `.pvse-` | `pages/settings.py` (231) | `Settings.svelte` (161) | W-P2 |
| `web/pv-accounts.js` | `pvac` | `.pvac-` | `pages/accounts.py` (536) | `Accounts.svelte` (469) | W-P3 |
| `web/pv-post.js` | `pvpo` | `.pvpo-` | `pages/post.py` (332) | `Post.svelte` (337) | W-P3 |
| `web/pv-folders.js` | `pvfo` | `.pvfo-` | `pages/folders.py` (1149) | `Folders.svelte` (932) | W-P4 |
| `web/pv-calendar.js` | `pvca` | `.pvca-` | `pages/calendar.py` (439) + `calendar_utils.py` (152) | `Calendar.svelte` (356) + `calendar-utils.ts` (88) | W-P5 |
| `web/pv-queue.js` | `pvqu` | `.pvqu-` | `pages/queue.py` (641) | `Queue.svelte` (622) | W-P5 |

**Luật tránh va tiền tố (P3-4):** tên cấp đỉnh của `web/poster.js` **không được** bắt đầu (không phân biệt hoa thường) bằng 9 tiền tố con `pvdb pvvi pvlo pvse pvac pvpo pvfo pvca pvqu`. Bản cũ có `pvLoiChu` (bắt đầu `pvlo`, va `pv-logs.js`), nay đổi thành **`pvChuLoi`**. Không đặt hằng như `pvPOLL…` (va `pvpo`), `pvSe…` (va `pvse`), `pvCa…` (va `pvca`). Danh sách tên cấp đỉnh của `poster.js` cố định ở §6.4; W-P1 thêm test so danh sách này với 9 tiền tố con.

Đường dẫn nguồn desktop: `E:/tool/tiktok_poster_v2/src/desktop/`. Bản tham khảo đọc bằng:

```
git -C C:/Users/Mi/Agency show a55d687:src/lib/components/poster/pages/<Ten>.svelte
```

Mỗi file có khối hàm thuần `// --- <tiền tố>-thuan start/end ---` để test nạp (như `menu-web.test.mjs:24-28`). Riêng `poster.js` dùng `poster-thuan`.

### 6.4 Interface `web/poster.js` (W-P1 làm; W-P2..W-P5 chỉ dùng)

Tên cấp đỉnh của `poster.js` (đủ, không thêm): `pvTRANG`, `pvTRANG_VE`, `pvPhien`, `pvPhanTich`, `pvTabHtml`, `pvChuLoi`, `pvQs`, `pvGoi`, `pvCho`, `pvApi`, `pvRender`, `pvDung`, `pvConSong`, `pvHenGio`, `pvXacNhan`, `pvThongBao`, `pvHop`. Biến nội bộ khác đặt trong closure hoặc trong `pvApi`.

```js
// Thứ tự + nhãn y NAV_ITEMS (app.py:52-62).
const pvTRANG = [["Dashboard","dashboard"],["Accounts","accounts"],["Folders","folders"],["Calendar","calendar"],
  ["Views","views"],["Queue","queue"],["Đăng bài","post"],["Logs","logs"],["Settings","settings"]];
const pvTRANG_VE = { dashboard: "pvDbVe", accounts: "pvAcVe", folders: "pvFoVe", calendar: "pvCaVe",
  views: "pvViVe", queue: "pvQuVe", post: "pvPoVe", logs: "pvLoVe", settings: "pvSeVe" };
let pvPhien = 0;

// --- poster-thuan start ---
function pvPhanTich(id)            // string chưa giải mã → mã trang trong pvTRANG; "" / lạ / giải mã lỗi → "dashboard"
function pvTabHtml(ma)             // thanh 9 tab: <a href="#/poster/<ma>" data-pv-tab aria-current>, flex-wrap, không cuộn ngang
function pvChuLoi(status, j)       // (đổi tên từ pvLoiChu, P3-4) chữ lỗi giống _raise_for_status / api.ts errorText:
                                   //   j.detail chuỗi → "<status>: <detail>"; detail khác → "<status>: <JSON.stringify(detail)>";
                                   //   j.loi (Worker/video_server) → "<status>: <loi>"; còn lại → "HTTP <status>"
function pvQs(params)              // như qs() của api.ts: bỏ undefined/null → "?a=1&b=2" | ""
// --- poster-thuan end ---

// Gọi API. duong = path backend ("/api/v2/…", có thể kèm query) hoặc route riêng ("/_video/12", "/_dem", "/_thong_tin", "/_kq").
// Hợp đồng §2.1:
//   headers luôn có "x-pv": "1";
//   GET/DELETE: không body, không content-type;
//   POST/PUT/PATCH: content-type "application/json", body JSON.stringify(body ?? {}).
// 401 → pvDung(); auth.user = ""; renderUser(); openLogin(); ném Error("Hết phiên đăng nhập — đăng nhập lại") (P2-3).
// !ok (khác 202) → ném Error(pvChuLoi(status, j)) có e.status.
// 202 có j.cho → return pvCho(j.cho, j.toi_da_giay).
async function pvGoi(method, duong, body)            // → any

// Hỏi GET /_kq/<cho> 3 s/lần, tối đa (toiDaGiay + 60) s, gắn với pvPhien lúc gọi.
// pvPhien đổi (rời trang / đăng xuất) → ngừng hỏi, ném Error có e.roiTrang = true (trang con không hiện lỗi này).
// xong: status 2xx → trả body; khác → ném Error(pvChuLoi(status, body)). Quá hạn → ném Error("Quá giờ chờ kết quả: xem Logs/Queue.").
async function pvCho(cho, toiDaGiay)                  // → any

// 1:1 api_client.py, tên camelCase giống src/lib/poster/api.ts. CHỈ các phương thức 9 trang dùng (bảng §2.2 #1–#45) + 4 tiện ích cuối:
const pvApi = {
  listAccounts, createAccount(data), updateAccount(id, data), deleteAccount(id),
  testCookies(id), accountCooldown(id, hours=24 → body {hours}), accountClearCooldown(id), cleanAllProfiles(),
  loginAndCapture(name, proxy="", useFingerprint=false), cookiesFromJson(name, cookies), viewsAccountHealth(id),
  listFolders(), getFolders(archived) /* = _get("/api/v2/folders/", {archived}) folders.py:797 */,
  createFolder(data), updateFolder(id, data), archiveFolder(id, archived=true), deleteFolder(id),
  folderSuggestPhase(id, n), cadenceForecast(days=14), driveTest(id), postNow(id, visibility="everyone"), batchSchedule(data),
  listQueue(status, limit=100, offset=0), statusCounts(), postQueueItem(id), queueRetry(id), deleteQueueItem(id),
  queueUnstick(), queueClearPending(), queueResetAll(), queueRandomShuffle(),
  getSettingsAll(), putSetting(key, value) /* = _put("/api/v2/settings/<key>", {value}) */, autopostOn(), autopostOff(),
  calendarMonth(year, month, accountId), createCalendarPlan(payload), deleteCalendarPlan(id),
  viewsSummary(), viewsRefresh(), getStats(), healthCheck(),
  listLogs(limit=100, offset=0, status), affiliateStats(productId),
  postVideoDirect(folderId, videoPath, caption, visibility="everyone", firstComment="", draft=false),
  dsVideoFolder(folderId) /* GET /_video/<id> → {ho_tro, video:[{name,path,size}]} */,
  demVideo(duongDan)      /* POST /_dem → {ton_tai, so_video} */,
  thongTin()              /* GET /_thong_tin */,
  dangChay()              /* GET /_kq → {dang_chay:[{cho, method, path, lop, giay_da_chay, toi_da_giay, tom_tat}]} */,
};

// Khung trang
async function pvRender(id)        // khung.js gọi; vẽ thanh trạng thái + tab + <section id="pv-noi">, rồi gọi globalThis[pvTRANG_VE[ma]]
function pvDung()                  // xoá mọi hẹn giờ của pvHenGio, tăng pvPhien (bỏ kết quả muộn, dừng pvCho), gọi pv<xx>Dung nếu có
function pvConSong(phien)          // true khi phien === pvPhien (trang con dùng sau MỖI await trước khi vẽ)
// setInterval gắn phiên hiện tại. Mỗi lượt BỎ QUA khi: !auth.on, document.hidden, hoặc lượt trước (fn trả Promise) chưa xong (P2-3).
// pvDung xoá. fn ném lỗi thì nuốt lỗi (trang tự hiện lỗi trong fn) và vẫn nhả cờ "đang chạy".
function pvHenGio(fn, ms)

// Hộp thoại dùng chung (thẻ <dialog>, mọi chuỗi qua esc; gắn sự kiện bằng addEventListener)
function pvXacNhan(tieuDeHoacCau, cau, ten, chuCo, chuKhong = "Hủy")  // port confirm_destructive (widgets/common.py:262-268) → Promise<boolean>
function pvThongBao(tieuDe, cau, kieu = "info")                       // QMessageBox information|warning|critical → Promise<void>
function pvHop({ tieuDe, html, nut: [{ ma, chu, chinh }] })           // hộp tuỳ biến → { el, dong(), cho: Promise<string|null> }
```

**Dùng chung với `app.js` (không viết lại):** `esc` (`web/app.js:9`), `toast(msg)` (`web/app.js:57-60`, cho thông báo ngắn kiểu `status_bar.showMessage`), `auth`, `renderUser`, `openLogin`, `laChu`. Các trang `pv-*.js` gọi thẳng `toast(msg)`; không trang nào tự tạo vùng toast hay hàm toast riêng (P3-3).

**Trang con** (mỗi file `pv-*.js`) khai báo **đúng 2 tên** để khung gọi qua `typeof`, cộng các tên nội bộ cùng tiền tố:

```js
async function pv<xx>Ve(khung /* HTMLElement #pv-noi */, phien /* number */)   // vẽ + tải dữ liệu; sau await: if (!pvConSong(phien)) return;
function pv<xx>Dung()                                                       // tuỳ chọn: huỷ việc riêng của trang
```

`<xx>` lần lượt là `Db, Ac, Fo, Ca, Vi, Qu, Po, Lo, Se`. Khung tra `globalThis[pvTRANG_VE[ma]]`. Script thường khai báo `function` cấp đỉnh nên tên có trên `globalThis`.

**Quy ước bắt lỗi trong trang con:** `try { … await pvApi.x() … } catch (e) { if (!pvConSong(phien)) return; /* hiện lỗi như .py */ }`. Lỗi `e.roiTrang` luôn rơi vào nhánh `return` vì `pvPhien` đã đổi.

**Thăm dò:**
- thanh trạng thái gọi `healthCheck` 30 s/lần (`app.py:203-205`);
- Dashboard gọi lại sau mỗi `REFRESH_INTERVAL_MS = 10_000` (`dashboard.py:54`);
- mọi hẹn giờ phải qua `pvHenGio`, nên rời trang, ẩn tab, đăng xuất, hoặc lượt trước chưa xong là không gọi.

Đây là chỗ khác desktop duy nhất về nhịp gọi, lý do ở §8 (tải).

**Bảng rộng** (Queue, Logs, Folders): bọc trong `<div class="pv-cuon">` có `overflow-x:auto`. Chỉ khối bảng cuộn ngang; trang không cuộn ngang ở 375px. `menu.css` và `style.css` không đổi.

### 6.5 Tiêu chí "giống hệt" cho mỗi trang (dùng cho W-P2..W-P5)
- Cùng nút, cùng chữ trên nút, tiêu đề, cột bảng, ô lọc, tab lọc, phân trang (Queue/Logs 100 dòng), tiêu đề và câu của mọi hộp xác nhận/thông báo. Lấy **nguyên văn** từ `.py`.
- Cùng lời gọi API, cùng tham số và payload như `.py`. Đối chiếu với bản Svelte, nơi đã ghi "Same as source".
- **Lỗi gốc giữ nguyên**, có test khoá lại. Ví dụ đã biết: `views.py` lọc và đếm theo `status` trong khi API trả `growth_status`, nên bộ lọc luôn trống (`Views.svelte:40-48`).
- Kỹ sư thấy chỗ khác tương tự thì giữ nguyên và ghi vào "Lo ngại", không sửa.
- Không thêm tính năng. Chỗ khác desktop chỉ được là các mục §5.3, nhịp thăm dò §6.4 và khoá nút theo lệnh đang chạy §3.3.

---

## 7. Worker: `cf/src/poster.js` (mới) + móc 2 dòng `worker.js`

```js
// cf/src/poster.js — ES module, không import worker.js (tránh vòng); tự có json/loi nhỏ.
export const POSTER_BODY_TOI_DA = 256 * 1024;
export const POSTER_TIMEOUT_MS = 95_000;
export const RE_REST_POSTER = /^\/(api\/v2\/[A-Za-z0-9_.~\-\/]{1,200}|health|_kq(\/[0-9a-f]{32})?|_video\/\d{1,9}|_dem|_thong_tin)$/;
// rest = url.pathname bỏ "/api/poster". Kiểm thêm: không "//", không đoạn "." / "..", không "%"; method ∈ 5 method; query ≤ 512.
// → {dich:"/p"+rest+query} | {status, loi}
export function kiemDuongPoster(rest, method, search)
// Hợp đồng §2.1 cho phía Worker. → {body: Uint8Array|null, ct: "application/json"|null} | {status, loi}
export async function kiemBodyPoster(req, method)
// nguoi = { user, chu } (worker.js tính chu = laChuKho(user)). Luôn trả Response.
export async function apiPoster(req, env, url, nguoi)
```

**Thứ tự trong `apiPoster`:**
1. `!nguoi.chu` → 403.
2. Header `x-pv` khác `"1"` → 403 "Thiếu x-pv" (mọi method, §4.2).
3. Method khác GET mà `origin !== url.origin` → 403 "Sai nguồn gọi".
4. Thiếu `VIDEO_ORIGIN`/`VIDEO_KEY` → 503 "Chưa cấu hình máy phát video".
5. `kiemDuongPoster` lỗi → 404/405/400.
6. `kiemBodyPoster` theo §2.1: GET/DELETE có body → 400; POST/PUT/PATCH sai content-type → 415, rỗng → 400, `content-length` hoặc byte thật > 256 KB → 413, JSON hỏng → 400.
7. `fetch(VIDEO_ORIGIN + dich, {method, headers: {x-key, x-poster-boi: nguoi.user, content-type (chỉ POST/PUT/PATCH)}, body (chỉ POST/PUT/PATCH), signal: AbortSignal.timeout(95_000)})`.
8. Lỗi mạng → 502 `LOI_MAY_NHA`. Hết giờ → 504. Method khác GET thì câu thêm "Thao tác CÓ THỂ đã chạy: bấm Refresh để kiểm trước khi bấm lại".
9. Máy nhà trả **401** (P3-1):
   - có header `x-kho-tu-choi: khoa` (video_server tự đặt khi `x-key` sai, §9 B-P1) → 502 "Máy nhà từ chối khoá (VIDEO_KEY lệch với tools/.video_key)" (như `worker.js:955-958`);
   - không có header đó → 502 "Máy nhà trả 401 không rõ nguồn". **Không bao giờ** chuyển 401 cho trình duyệt (trình duyệt hiểu 401 là hết phiên).
10. Máy nhà trả **403** → **chuyển nguyên** status + body (403 bản quyền của backend). Không đổi thành "VIDEO_KEY lệch".
11. Còn lại: trả nguyên status + body, `content-type` của máy nhà (mặc định JSON), `cache-control: no-store`.
12. Method khác GET thì `console.log` nhật ký §4.4.

**Móc `worker.js` (2 dòng):**
- đầu file, sau `"use strict";`: `import { apiPoster } from "./poster.js";`;
- trong `api()` ngay sau dòng `/api/viec` (`worker.js:934`): `if (p === "/api/poster" || p.startsWith("/api/poster/")) return apiPoster(req, env, url, { user: phien.user, chu: laChuKho(phien.user) });`.

Không đổi `wrangler.toml` (`[assets] run_worker_first = ["/api/*"]` đã bao `/api/poster/*`). Không thêm secret.

---

## 8. Phân tích trước khi chốt

1. **Kiến trúc hiện tại, tương thích ngược.**
   - Giữ mô hình script thường + biến toàn cục + `phienCT` + router `mnRoute` của D12. Route cũ không đổi.
   - Worker thêm một nhánh `/api/poster/*`, không đụng `/api/viec`, `/api/video`, `/api/duyet`.
   - video_server thêm tiền tố `/p` cạnh `/v`, `/r`; `/r/*` vẫn chỉ GET/POST. Thêm `do_PUT/do_PATCH/do_DELETE`: path khác `/p/*` thì 405, nên test `test_r_method_khac_khong_chuyen` (`tools/test_video_server.py:475-479`, chấp nhận 405|501) vẫn qua.
   - `_vao` (`tools/video_server.py:392-404`) hiện kiểm `x-key` trước mọi path và trả 401 `{"loi":"Sai khoá"}` không header riêng. Móc mới: nhánh `/p` và `/p/*` đặt **trước** dòng kiểm khoá và trả act `"poster"`; `poster_web.xu_ly` tự kiểm `x-key` bằng `hmac.compare_digest` với `h.khoa`, sai thì 401 kèm header `x-kho-tu-choi: khoa`. Path `/v`, `/r`, `/suc-khoe` giữ nguyên hành vi cũ.
2. **Dependency.** Không thêm. Python stdlib (`http.client`, `threading`, `secrets`, `hashlib`, `json`, `time`). JS thuần. Worker là module ES nội bộ. Test nối 3 chặng dùng `node:child_process` để chạy `python -B tools/poster_noi_gia.py`.
3. **Tác động module hiện có:**
   - `khung.js` ≈ 8 dòng; `index.html` 11 dòng; `worker.js` 2 dòng; `video_server.py` ≤ 20 dòng (import, nhánh `/p` trong `_vao`, 2 dòng trong `do_GET`/`do_POST`, 3 handler mới, docstring).
   - Test cũ phải sửa: số mục 6 → 7 ở `cf/test/menu-web.test.mjs:57-68`, `:278`, `cf/test/homnay-web.test.mjs:953-968`; thứ tự script/CSS ở `cf/test/menu-web.test.mjs:403-409` và `cf/test/homnay-web.test.mjs:325`; bảng tiền tố P2-7 `cf/test/menu-web.test.mjs:424` thêm 10 file. Rà đủ ở §6.2.
4. **Đồng thời và tài nguyên:**
   - `ThreadingHTTPServer` mỗi request một luồng. Handler `/p` giữ luồng tối đa ~85 s; luồng gọi backend do `BangLenh` quản lý.
   - Giới hạn: **6 luồng S + 1 luồng L + 1 luồng DN** = tối đa 8 luồng gọi backend, bảng 50 mục. Mục đích: một tab treo hay người dùng bấm liên tục không làm cạn luồng phát video, và không có 2 lệnh đăng song song từ web (§3.3).
   - Backend :8023 dùng chung với app desktop đang mở; backend tự xử lý đồng thời như khi desktop gọi. Semaphore đăng của backend là chung (§4.6).
   - **Windows khoá file:** `post/direct` đọc video trong khi `/v/<id>/file?xoa=1` có thể đang xoá file đó (`video_server.py:480-484`), hoặc `poster_bo_loai` đang dời file sang `_loai/`. B2 kiểm `is_file()` lúc đăng, file mất sau đó thì backend báo lỗi đăng. Không cần khoá chung.
   - **Đường dẫn mạng:** B3 từ chối UNC ở body và `_video` bỏ qua folder có `path` UNC, nên video_server không mở kết nối SMB. Ổ mạng đã map (vd `Z:`) vẫn qua B3; Windows dùng thông tin đăng nhập đã lưu cho ổ đó, không gửi hash tới máy do người gọi chọn.
   - **Không có Chrome profile hay GPU** ở phía video_server; Chrome do backend mở như desktop.
   - **Tải Worker:** Dashboard mở liên tục = 2 lời gọi / 10 s ≈ 17 nghìn request/ngày mỗi tab, cộng thanh trạng thái ≈ 2,9 nghìn. Nếu gói Workers là Free (100 nghìn/ngày, **chưa kiểm gói**) thì 4–5 tab mở cả ngày có thể chạm trần. `pvHenGio` ngừng khi ẩn tab, rời trang, đăng xuất. Mỗi lệnh chuyển nền thêm tối đa (300 + 60) / 3 = 120 lời gọi `_kq`.
   - **Bảng lệnh nền trong video_server đi gần phương án D1 đã loại** ("nhồi queue + `jobs.json` vào `video_server.py`: lỗi bộ chạy làm sập luôn nút tải video", `DECISIONS.md:31`). Chấp nhận vì khác ở chỗ quan trọng:
     - không lưu đĩa, không sống qua khởi động lại, mỗi mục tối đa 6 phút + 15 phút giữ kết quả;
     - không chạy agent, script hay GPU; công việc thật do tiến trình backend Poster làm, video_server chỉ đợi HTTP;
     - có trần cứng 8 luồng / 50 mục và công tắc `KHO_POSTER_WEB=0`;
     - lối thay là đưa vào runner (D1) thì phải qua việc/runner, người dùng đã bác.

     Rủi ro còn lại: lỗi trong `BangLenh` (vd deadlock khoá bảng) có thể giữ luồng của handler `/p`; nút tải video vẫn chạy vì mỗi request một luồng riêng. B-P1 phải có test khoá bảng không bị giữ khi gọi backend (khoá chỉ bao thao tác trên dict).
5. **Rủi ro tóm tắt:**

| Rủi ro | Giảm |
|---|---|
| Phiên chủ kho bị chiếm → thao tác account thật, kể cả tuyến app không dùng (Q1) | `x-pv`, Origin bắt buộc, JSON-only, chủ kho, nhật ký máy nhà, B1/B3; chấp nhận theo D13 |
| Lệnh dài / chậm bị 524, người dùng bấm lại → đăng 2 lần | Chuyển nền + khoá chống trùng (trùng trả lại `cho` cũ); 1 lệnh đăng mỗi lúc; `GET /_kq` khoá nút khi mở lại trang; không tự thử lại lệnh ghi |
| Lệch content-type giữa 3 chặng → mọi DELETE / POST rỗng bị 415 | Bảng hợp đồng §2.1 + test nối 3 chặng T-P1 |
| 401 backend làm web đăng xuất | video_server đổi 401 → 502; Worker không bao giờ chuyển 401 |
| Test chạm Poster thật | Cấu hình đọc lúc gọi, fixture `delenv`, `chot_test` ném lỗi khi gặp :8023 / thư mục thật, `fetch` giả bắt buộc ở test JS |
| Secret Settings lộ ra trình duyệt | C1 che `"***"` ở video_server |
| Đường dẫn UNC → lộ hash NetNTLM | B3 + `_video` bỏ qua UNC |
| Thăm dò chạy sau đăng xuất | `pvGoi` gọi `pvDung` khi 401; `pvHenGio` bỏ lượt khi `!auth.on` |
| Trùng tên toàn cục giữa 10 file mới | Tiền tố riêng mỗi file + luật tránh va §6.3 + test P2-7 |
| Gọi nhầm endpoint ghi khi kiểm chứng | Kiểm chứng ghi chỉ với backend giả; live chỉ GET (§10) |
| `.env` Poster đổi token khi app khởi động lại | Đọc lúc gọi, cache theo `mtime`; backend 401 thì đọc lại 1 lần rồi gọi lại **chỉ với GET** |
| Bỏ qua chốt Loại D12 / hạn mức D9 | Người dùng chọn giữ như app gốc (Q2); ghi ở D13 |

---

## 9. Kế hoạch phiếu

**Gốc chạy lệnh:** `E:/phantichcanhquay/kho-san-pham`.
- **Mốc** (nhật ký ca 2026-11-18-e): JS 336, Python 1246, engine 33. Không được giảm. Trưởng phòng đo lại trước lượt 1.
- **Kỹ sư được đọc** (chỉ đọc): `E:/tool/tiktok_poster_v2/**` và `git -C C:/Users/Mi/Agency show a55d687:<path>`.
- **Cấm** mọi lệnh tới `127.0.0.1:8023`, kể cả GET; mọi test dùng backend giả.
- **Luật test chung (P1-3):**
  - Python: fixture `autouse` `monkeypatch.delenv(…, raising=False)` cho `KHO_POSTER_DIR`, `TT_API_BEARER_TOKEN`, `TT_API_PORT`, `KHO_POSTER_NHAT_KY`, `KHO_POSTER_WEB`, rồi đặt `KHO_POSTER_DIR` / `KHO_POSTER_NHAT_KY` vào `tmp_path`. Backend giả nghe cổng ngẫu nhiên (`0`), không bao giờ 8023.
  - JS: mỗi file test đặt `globalThis.fetch` bằng hàm giả **trước** khi nạp mã; hàm giả ném `Error("fetch thật bị cấm trong test")` với URL nó không xử lý. Riêng T-P1 cho phép đúng `http://127.0.0.1:<2 cổng do máy chạy giả in ra>`, ném lỗi với host/cổng khác (kể cả 8023).

### Lượt 1 (song song, không trùng file)

**B-P1 · culiapp-backend · Chuyển tiếp Poster trong video_server**
- **ĐƯỢC SỬA:**
  - `tools/poster_web.py` (mới);
  - `tools/video_server.py` (chỉ móc ≤ 20 dòng: import; trong `_vao`, nhánh `/p` và `/p/*` → act `"poster"` đặt **trước** dòng kiểm `x-key`; `do_GET`/`do_POST` gọi `poster_web.xu_ly`; thêm `do_PUT`/`do_PATCH`/`do_DELETE` dùng chung một hàm; docstring);
  - `tools/test_poster_web.py` (mới).
- **Phụ thuộc:** không.
- **Việc:** §2 (lọc path chung, hợp đồng §2.1, bảng lớp §2.2, chốt B1/B2/B3/C1, route riêng), §3 (hạn chờ 80 s, hạn tổng monotonic, `BangLenh`, khoá chống trùng, `GET /_kq`, mã lỗi), §4.3–§4.4 (header, token đọc lúc gọi, `chot_test`, nhật ký), §5.1–§5.2, giới hạn đồng thời §8.4. Thêm công tắc tắt: env `KHO_POSTER_WEB=0` (đọc lúc gọi) → mọi `/p/*` trả 503 `{"loi":"Poster trên web đang tắt ở máy nhà"}`.
- **Interface:**

  ```python
  HAN_CHO_DONG_BO = 80.0                   # giây chờ trong handler trước khi chuyển nền
  HAN_NEN = {"S": 300.0, "L": 300.0, "DN": 360.0}
  HAN_QUET_DIA = 30.0
  HAN_KET_NOI = 5.0
  CHO_CHAY = {"S": 6, "L": 1, "DN": 1}
  BANG_LOP: tuple[tuple[str, re.Pattern, str], ...]   # (method, mẫu path, lớp) — chỉ các dòng L/DN của §2.2 (#14, #29, #45, #46)

  def poster_dir() -> Path                 # env KHO_POSTER_DIR đọc MỖI lần gọi; mặc định Path("E:/tool/tiktok_poster_v2")
  def chot_test(port: int, thu_muc: Path) -> None
      # ("pytest" in sys.modules or os.environ.get("KHO_POSTER_TEST") == "1")
      # and (port == 8023 or thu_muc.resolve() == Path("E:/tool/tiktok_poster_v2").resolve())
      # → raise RuntimeError("Test đang trỏ vào Poster V2 thật")
  def cau_hinh() -> tuple[str, int]        # (token, port); env TT_API_* đọc mỗi lần gọi, rồi <poster_dir()>/.env;
                                           # cache theo (đường dẫn, mtime); gọi chot_test trước khi trả
  def kiem_path(path: str) -> bool         # lọc chung §2
  def kiem_query(query: str) -> bool       # ≤ 512, không ký tự điều khiển, không "#"
  def lop_cua(method: str, path: str) -> str            # "S" | "L" | "DN"; không khớp BANG_LOP → "S"
  def doc_body(h, method: str) -> tuple[bytes | None, object | None] | tuple[int, str]
                                           # hợp đồng §2.1 → (byte, obj) hoặc (status, câu lỗi)
  def la_duong_dan_o_dia(s: str) -> bool   # B3
  def kiem_body(method: str, path: str, obj: object) -> str | None   # B1 + B3 (+ "cookies là mảng" cho cookies_from_json); None = hợp lệ
  def kiem_post_direct(obj: dict, folder: dict) -> str | None        # B2, nhận folder đã lấy từ backend
  def che_bi_mat(path: str, obj: object) -> object                    # C1
  def ds_video(folder: dict) -> dict       # {"ho_tro": bool, "video": [{"name","path","size"}]}  (post.py:239-247)
  def dem_video(duong_dan: str) -> dict    # {"ton_tai": bool, "so_video": int}               (folders.py:190-192)
  def goi_backend(method: str, path_kem_query: str, body: bytes | None, han: float) -> tuple[int, object]
                                           # http.client, hạn tổng monotonic; 401 → đọc lại .env 1 lần, gọi lại chỉ khi GET
  class BangLenh:
      def nhan(self, khoa: tuple[str, str, str], lop: str, viec: Callable[[], tuple[int, object]],
               tom_tat: dict, toi_da_giay: float) -> tuple[str, bool]
          # → (ma, trung). Trùng khoá đang chạy → (ma cũ, True). Hết chỗ lớp / bảng đầy → raise DayCho(lop)
      def cho(self, ma: str, giay: float) -> tuple[int, object] | None   # None = chưa xong sau `giay`
      def ket_qua(self, ma: str) -> dict | None                           # {"xong": False} | {"xong": True, "status", "body"} | None
      def dang_chay(self) -> list[dict]                                   # cho GET /_kq
  class DayCho(Exception): lop: str
  def ghi_nhat_ky(muc: dict) -> None
  def xu_ly(h, method: str) -> None        # luôn tự trả lời client; tự kiểm x-key (401 + header x-kho-tu-choi: khoa)
  ```
- **Tiêu chí xong** (pytest; backend giả = `ThreadingHTTPServer` cổng ngẫu nhiên ghi lại method/path/query/header/body, có chế độ chậm và chế độ nhả byte nhỏ giọt; `.env` giả trong `tmp_path` qua `KHO_POSTER_DIR`; nhật ký trong `tmp_path` qua `KHO_POSTER_NHAT_KY`; luật test chung ở đầu §9):
  - **chống chạm production:** `chot_test(8023, tmp)` và `chot_test(<cổng giả>, Path("E:/tool/tiktok_poster_v2"))` ném `RuntimeError` và không mở socket (monkeypatch `http.client.HTTPConnection` đếm lần tạo = 0); `poster_dir()`/`cau_hinh()` phản ánh env đặt **sau** khi import module;
  - mỗi dòng #1–#47 của bảng §2.2 được chuyển đúng method + path + query; path ngoài bảng (vd `POST /api/v2/settings/backup-now`, `GET /api/v2/system/config`) cũng được chuyển, lớp S;
  - lọc path: `..`, `/./`, `//`, `%2e%2e`, `%2f`, `\`, `\x01`, path không bắt đầu `/api/v2/` (khác `/health`) → 404, backend giả **không nhận gì**; method `HEAD`/`OPTIONS` không chuyển;
  - thiếu/sai `x-key` → 401 có header `x-kho-tu-choi: khoa`; `/v/...` sai khoá vẫn 401 như cũ;
  - hợp đồng §2.1 cho từng method: DELETE không body → backend nhận DELETE không `Content-Type`, không body; DELETE có body → 400; POST `{}` → backend nhận `Content-Type: application/json` và body `{}`; POST rỗng → 400; POST sai content-type → 415; > 256 KB → 413; JSON hỏng → 400; GET có body → 400;
  - header tới backend chỉ gồm `Authorization: Bearer <token giả>`, `Accept`, `Content-Type` (chỉ POST/PUT/PATCH), cùng header bắt buộc của `http.client`; không có `x-key`, `cookie`, `x-poster-boi`, `x-runner-key`, `x-pv`;
  - env token ghi đè `.env`; token **không** xuất hiện trong stdout, phản hồi hay nhật ký;
  - B1: `name` = `"a/b"`, `"a\\b"`, `"C:x"`, `"."`, `".."`, chuỗi 101 ký tự → 400, kể cả với path accounts ngoài bảng (vd `PATCH /api/v2/accounts/3`); `"a..b"` được nhận;
  - B2: video ngoài thư mục folder / sai đuôi / folder drive / folder path UNC → 400; đúng → chuyển;
  - B3: `\\host\share\x`, `//host/x`, `\\?\C:\x`, `relative\x` ở `path` lồng trong list/dict, `cookies_path`, `chrome_profile_dir`, `video_path`, `duong_dan` → 400; `E:\x` và `E:/x` qua;
  - C1: `GET /settings/` có `telegram_bot_token`, `anthropic_api_key`, `x_password`, `y_secret` khác rỗng → `"***"`; giá trị rỗng giữ rỗng; khoá thường giữ nguyên; `GET/PUT /settings/{key}` dạng `{key,value}` che theo `key`; kết quả qua `_kq` cũng đã che;
  - backend tắt → 502; backend 401 → 502 (câu token), GET được gọi lại đúng 1 lần, POST không gọi lại; backend 403 → 403 nguyên body;
  - hạn: monkeypatch `HAN_CHO_DONG_BO = 0.5`, `HAN_NEN["S"] = 1.5`: GET chậm 1 s → 202 `{cho}` rồi `_kq` → `{xong:true, status:200}`; GET chậm 3 s → `_kq` `status 504` câu GET; POST chậm 3 s → câu "CÓ THỂ đã chạy"; backend nhả từng byte mỗi 0,3 s (mỗi lần đọc không quá timeout) vẫn bị cắt đúng hạn tổng (đo monotonic);
  - lệnh L: 202 `{cho}` → `_kq` `{xong:false}` → `{xong:true,status,body}`; gửi lại **cùng** method/path/body khi đang chạy → 202 cùng `cho`, `trung: true`, backend giả nhận **đúng 1** lần; khác body → 429 (L chỉ 1 chỗ), backend không nhận;
  - lệnh S trùng khoá (2 request song song cùng GET `/api/v2/folders/?archived=0`) → backend giả nhận **1** lần, cả 2 nhận cùng kết quả;
  - `GET /_kq` liệt kê lệnh đang chạy, `tom_tat` của `post/direct` chỉ có `folder_id` + tên file, của `login_and_capture` chỉ có `name`; không có `cookies`, token; lệnh đã xong không còn trong danh sách; `_kq` mã lạ → 404;
  - khoá bảng không bị giữ khi gọi backend: trong lúc 1 lệnh L treo, `GET /_kq` trả lời < 0,5 s;
  - `_video`: đúng thứ tự đuôi, bỏ `_posted`/`okkkk`, không đệ quy, nguồn drive / path UNC → `ho_tro:false`; quét quá `HAN_QUET_DIA` (monkeypatch) → 504;
  - `_dem`: đếm `.mp4 .mov .avi .webm`; thư mục không có → `ton_tai:false`; UNC → 400;
  - `_thong_tin` không có token;
  - nhật ký: 1 dòng mỗi lệnh ghi, có `boi`, `trung`, không có giá trị body; lỗi ghi file không làm hỏng request;
  - `KHO_POSTER_WEB=0` đặt sau import → 503;
  - `/r/viec` với PUT vẫn 405;
  - toàn bộ `tools/test_video_server.py` vẫn xanh.
- **Lệnh kiểm chứng:**

  ```
  python -B -m py_compile tools/poster_web.py tools/video_server.py
  python -B -m pytest tools/test_poster_web.py tools/test_video_server.py -q -p no:cacheprovider
  ```
- **Mức cần đạt:** `fixture`.

**W-P0 · culiapp-web · Worker `/api/poster/*`**
- **ĐƯỢC SỬA:** `cf/src/poster.js` (mới), `cf/src/worker.js` (chỉ 2 dòng §7), `cf/test/poster-worker.test.mjs` (mới).
- **Phụ thuộc:** không. Hợp đồng với B-P1 là path `/p/<rest>`, header `x-key` / `x-poster-boi` / `content-type` theo §2.1, mã 202/`_kq`, header `x-kho-tu-choi: khoa` khi 401.
- **Việc:** §7, phía Worker của §2.1.
- **Tiêu chí xong** (máy nhà giả `https://may.test` như `cf/test/worker.test.mjs:15-20`; `fetch` giả bắt buộc theo luật test chung):
  - chưa đăng nhập → 401;
  - người thường → 403 và máy nhà **không** được gọi;
  - thiếu `x-pv` → 403 với cả GET; có `x-pv` + chủ kho → GET không cần Origin;
  - lệnh ghi thiếu Origin / Origin lạ → 403;
  - `rest` lạ, `..`, `//`, `%2e%2e`, method lạ → 4xx, không gọi máy nhà; `/_kq` (không id) và `/_kq/<32 hex>` qua;
  - hợp đồng §2.1 từng method: DELETE không content-type, không body → gọi máy nhà **không** có `content-type`, không body; DELETE có body → 400; POST `{}` → gửi `content-type: application/json` + `{}`; POST rỗng → 400; POST/PUT/PATCH sai content-type → 415; > 256 KB → 413; JSON hỏng → 400; GET có body → 400;
  - header gửi đi chỉ gồm `x-key`, `x-poster-boi`, và `content-type` khi POST/PUT/PATCH; không có `cookie`, `x-pv` của trình duyệt;
  - query chuyển nguyên (≤ 512);
  - máy nhà 401 có `x-kho-tu-choi: khoa` → 502 câu VIDEO_KEY; 401 không header → 502 câu "không rõ nguồn"; **403 → 403 nguyên body**; lỗi mạng → 502; hết giờ (giả `AbortSignal`) → 504, lệnh ghi có câu "CÓ THỂ đã chạy";
  - 202 `{cho, trung}` được chuyển nguyên;
  - `worker.test.mjs` không đổi và vẫn xanh.
- **Lệnh kiểm chứng:**

  ```
  node --check cf/src/poster.js
  node --check cf/src/worker.js
  node --test cf/test/poster-worker.test.mjs cf/test/worker.test.mjs cf/test/chu-ky-cheo.test.mjs
  ```
- **Mức cần đạt:** `fixture`.

**W-P1 · culiapp-web · Khung Poster V2 trên web**
- **ĐƯỢC SỬA:**
  - `web/poster.js` (mới), `web/poster.css` (mới);
  - `web/khung.js` (chỉ §6.1);
  - `web/index.html` (§6.2);
  - `cf/test/poster-web.test.mjs` (mới);
  - `cf/test/menu-web.test.mjs` (chỉ số mục 6 → 7 ở `:57-68`, `:278`; danh sách CSS + script ở `:403-409`; bảng tiền tố P2-7 ở `:421-444` thêm `poster.js: "pv"` và 9 file `pv-*.js` với tiền tố §6.3);
  - `cf/test/homnay-web.test.mjs` (chỉ số mục 6 → 7 ở `:953-968` và **regex thứ tự script ở `:325`**, thêm `poster.js` + 9 `pv-*.js` giữa `duyet.js` và `app.js` theo đúng thứ tự §6.2).
- **Phụ thuộc:** không. Gọi `/api/poster/*` theo hợp đồng §2.1 và §7; test dùng `fetch` giả.
- **Việc:** §6.1, §6.2, §6.4 toàn bộ: `pvApi` đủ danh sách (gồm `dangChay`), `pvGoi` theo hợp đồng §2.1, `pvCho`, thanh trạng thái, thanh 9 tab, `pvXacNhan`/`pvThongBao`/`pvHop`, `pvHenGio`. Chưa có file trang thì nội dung tab là `mnCHUA_CO`.
- **Tiêu chí xong:**
  - `pvPhanTich`: rỗng/lạ/`%E0` → `dashboard`, 9 mã đúng;
  - `pvTabHtml`: 9 tab đúng thứ tự và nhãn `NAV_ITEMS`, `aria-current` đúng tab;
  - `pvChuLoi`: `detail` chuỗi / object / `loi` / rỗng;
  - tên cấp đỉnh của `poster.js` đúng danh sách §6.4, không tên nào bắt đầu (không phân biệt hoa thường) bằng 9 tiền tố con;
  - `pvGoi` (fetch giả):
    - mọi method có header `x-pv: 1`;
    - GET và DELETE: **không** có `content-type`, không body;
    - POST/PUT/PATCH: `content-type: application/json`; `pvGoi("POST", p)` gửi body `"{}"`;
    - đúng URL `/api/poster…`;
    - 401 gọi luồng đăng nhập **và** `pvDung()` (hẹn giờ bị xoá, `pvPhien` tăng);
    - 4xx/5xx ném đúng chữ;
    - 202 → hỏi `_kq` tới khi xong (đồng hồ giả); 202 `trung:true` xử lý như 202;
    - đổi trang giữa lúc hỏi → ngừng gọi `_kq`, lỗi có `e.roiTrang === true`, không gọi `toast`/hộp lỗi;
  - `pvHenGio`: không chạy khi `document.hidden`; không chạy khi `auth.on === false`; không chạy lượt mới khi Promise lượt trước chưa xong; fn ném lỗi thì lượt sau vẫn chạy; `pvDung` xoá;
  - `pvApi`: mỗi phương thức → đúng (method, path, body) như bảng §2.2 (bảng test liệt kê đủ #1–#45 + `_video`, `_dem`, `_thong_tin`, `_kq`);
  - `mnMuc("#/poster/queue", true) === "poster"`;
  - nav chủ 7 mục (mục 7 `#/poster` "Poster V2"); người thường vẫn 1 mục;
  - người thường mở `#/poster` → `CHI_CHU_HTML`;
  - XSS chuỗi `BAN` trong thanh trạng thái / hộp thoại;
  - test P2-7 xanh với file `pv-*.js` chưa có (skip);
  - CSS tĩnh: `poster.css` không có `position: fixed` đè `.nav`, có `.pv-cuon { overflow-x: auto`;
  - mọi test cũ xanh (gồm `homnay-web.test.mjs:325` đã cập nhật), tổng ≥ mốc.
- **Lệnh kiểm chứng:**

  ```
  node --check web/poster.js
  node --check web/khung.js
  node --test cf/test/poster-web.test.mjs cf/test/menu-web.test.mjs cf/test/homnay-web.test.mjs cf/test/dang-web.test.mjs cf/test/duyet-web.test.mjs cf/test/viec-web.test.mjs cf/test/sua-web.test.mjs
  ```
- **Mức cần đạt:** `fixture`.

### Lượt 2 (sau lượt 1; 5 phiếu song song, mỗi phiếu chỉ file của mình)

**Chung cho W-P2..W-P5:**
- Theo §6.3–§6.5.
- Mỗi trang = 1 file `web/pv-<trang>.js`, chỉ gọi `pvApi`/`pvGoi`/`pvCho`, hộp thoại qua `pvXacNhan`/`pvThongBao`/`pvHop`, thông báo ngắn qua `toast`, thăm dò qua `pvHenGio`.
- Test nạp khối thuần + `web/poster.js` thật, DOM/`fetch` giả như `cf/test/homnay-web.test.mjs:769-798`; `fetch` giả bắt buộc theo luật test chung.
- **Không** sửa `web/index.html`, `web/poster.js`, `web/khung.js` hay test của phiếu khác. Thiếu gì ở core thì trả `BLOCKED`.
- **Mỗi trang phải có test:**
  - (a) bảng "chữ nguyên văn": mọi nút, cột, tiêu đề hộp lấy từ `.py`, so chuỗi;
  - (b) mỗi nút → đúng lời gọi `pvApi` với đúng tham số; nút có xác nhận thì bấm "Hủy" không gọi gì;
  - (c) lỗi API hiện đúng chữ/hộp như `.py`;
  - (d) XSS;
  - (e) rời trang giữa chừng không vẽ đè, không hiện lỗi `roiTrang`;
  - (f) lỗi gốc đã biết được giữ.

**W-P2 · culiapp-web · Dashboard, Views, Logs, Settings**
- **ĐƯỢC SỬA:** `web/pv-dashboard.js`, `web/pv-views.js`, `web/pv-logs.js`, `web/pv-settings.js`, `cf/test/pv-tong-web.test.mjs` (mới).
- **Tiêu chí riêng:**
  - Dashboard làm mới 10 s qua `pvHenGio`, gọi `getStats` + `listLogs(25)`;
  - Views: test khoá lỗi gốc (lọc/đếm theo `status`, không theo `growth_status`), nút refresh → `viewsRefresh`;
  - Logs: phân trang 100, hộp "Chi tiết log", hộp "📊 Thống kê đổi sản phẩm" → `affiliateStats`;
  - Settings:
    - lưu theo đúng `settings.py:166-231`: Engine lưu `default_engine` rồi `headless`; Telegram ô trống cả hai → hộp "Không có gì để lưu"; chỉ gửi khoá có chữ; lưu xong xoá ô token, placeholder "*** (đã lưu)";
    - ô Bot Token `type=password` luôn trống khi tải; dữ liệu giả `getSettingsAll` trả `telegram_bot_token: "***"` thì ô vẫn trống và không có lời gọi `putSetting("telegram_bot_token", "***")` nào;
    - khối Architecture Info từ `thongTin()`, không có khối Bản quyền.
- **Lệnh kiểm chứng:**

  ```
  node --check web/pv-dashboard.js
  node --check web/pv-views.js
  node --check web/pv-logs.js
  node --check web/pv-settings.js
  node --test cf/test/pv-tong-web.test.mjs cf/test/menu-web.test.mjs cf/test/poster-web.test.mjs
  ```

**W-P3 · culiapp-web · Accounts, Đăng bài**
- **ĐƯỢC SỬA:** `web/pv-accounts.js`, `web/pv-post.js`, `cf/test/pv-tk-dang-web.test.mjs` (mới).
- **Tiêu chí riêng:**
  - Accounts:
    - thẻ account, Cooldown / Bỏ Cooldown, Check (`testCookies`), Edit, 🗑️ có xác nhận, 🧹 Dọn cache profile, ↻ Refresh, + Add Account;
    - hộp Add/Edit đủ ô như `accounts.py:60-160`, gồm hỏi "Bỏ vân tay riêng?" (`:206-213`);
    - "Browse..." đọc file bằng `<input type=file>` vào ô JSON (§5.3), có test `FileReader` giả;
    - JSON hỏng → hộp "Lỗi cú pháp JSON";
    - JSON là mảng → `cookiesFromJson` rồi mới đóng hộp;
    - nút "🔓 Tạo profile & Login lấy cookies" giữ chữ gốc, **ngay dưới nút** có dòng `Cần người ngồi ở máy nhà để đăng nhập trên Chrome vừa mở` (so chuỗi nguyên văn); bấm gọi `loginAndCapture` (chạy nền, có test 202);
    - mở trang khi `dangChay()` có `login_and_capture` → nút login bị khoá, gọi `pvCho` với `cho` đó, xong thì mở khoá;
  - Đăng bài:
    - danh sách folder → `dsVideoFolder` → danh sách "<tên> (x.x MB)", "Tìm thấy N video", `ho_tro:false` → "Folder rỗng hoặc nguồn không hỗ trợ";
    - nút "ĐĂNG NGAY" có hộp xác nhận như `post.py`, gọi `postVideoDirect(folderId, video.path, …)`, kết quả nền hiện như desktop; trong lúc chờ nút bị khoá;
    - mở trang khi `dangChay()` có `post/direct` → chọn sẵn folder `tom_tat.folder_id`, nút "ĐĂNG NGAY" khoá, hiện "Đang đăng <video>…", gọi `pvCho`; rời trang rồi quay lại thì vẫn khoá (gọi lại `dangChay`).
- **Lệnh kiểm chứng:**

  ```
  node --check web/pv-accounts.js
  node --check web/pv-post.js
  node --test cf/test/pv-tk-dang-web.test.mjs cf/test/menu-web.test.mjs cf/test/poster-web.test.mjs
  ```

**W-P4 · culiapp-web · Folders**
- **ĐƯỢC SỬA:** `web/pv-folders.js`, `cf/test/pv-folders-web.test.mjs` (mới).
- **Tiêu chí riêng:**
  - tab lọc theo account "Tất cả (n)" / "<tên> (n)" (`folders.py:824-845`);
  - `getFolders(archived)`; thẻ folder với Lưu trữ/Khôi phục (`archiveFolder`), Edit, Delete (xác nhận);
  - `getFolders` trả qua 202 (fetch giả) → trang vẫn vẽ đúng khi `pvCho` xong; đang chờ mà bấm ↻ thì gọi lại bình thường (video_server tự gắn vào lần quét cũ, §3.3);
  - cadence: `updateFolder` + `folderSuggestPhase`;
  - "📊 Dự báo lịch" → `cadenceForecast(14)`;
  - "Chọn hết tab", "↺ Giống hôm qua", "⚡ Đăng ngay" (`postNow` + chọn visibility), "➕ Thêm vào Queue" (`batchSchedule`, payload y `folders.py`);
  - hộp Add/Edit: không có nút Browse (§5.3), có dòng gợi ý; 🔌 Test local → `demVideo` + 2 hộp gốc; 400 B3 → hộp warning với câu từ máy nhà; drive → `driveTest`.
- **Lệnh kiểm chứng:**

  ```
  node --check web/pv-folders.js
  node --test cf/test/pv-folders-web.test.mjs cf/test/menu-web.test.mjs cf/test/poster-web.test.mjs
  ```

**W-P5 · culiapp-web · Calendar, Queue**
- **ĐƯỢC SỬA:** `web/pv-calendar.js`, `web/pv-queue.js`, `cf/test/pv-lich-queue-web.test.mjs` (mới).
- **Tiêu chí riêng:**
  - Calendar:
    - lưới tháng T2–CN;
    - ◀ ▶, "Hôm nay", "+ Thêm kế hoạch" (hộp, `createCalendarPlan`), 🔄, "🗑️ Xóa kế hoạch đã chọn" (xác nhận, `deleteCalendarPlan`);
    - hàm thuần port `calendar_utils.py` có test bảng (tháng nhuận, ngày đầu tháng CN);
  - Queue:
    - `statusCounts` + `listQueue(status, 100, offset)`, khoá 35 s chống làm mới chồng (`queue.py:300`);
    - bật/tắt Auto post (`getSettingsAll` → `autopostOn`/`autopostOff`);
    - đăng 1 item (`postQueueItem`, nền), retry, xoá (xác nhận "Xóa queue item");
    - mở trang khi `dangChay()` có `queue/{id}/post` hoặc `queue/{id}/run` → nút đăng của dòng `tom_tat.queue_id` khoá, gọi `pvCho`, xong thì làm mới bảng;
    - Gỡ kẹt / Xóa hết chờ / Reset toàn bộ / xáo trộn với đúng câu xác nhận;
    - "📅 Lên lịch" → hộp `_PlanDialog` rồi `queueUnstick` (`queue.py:600-630`).
- **Lệnh kiểm chứng:**

  ```
  node --check web/pv-calendar.js
  node --check web/pv-queue.js
  node --test cf/test/pv-lich-queue-web.test.mjs cf/test/menu-web.test.mjs cf/test/poster-web.test.mjs
  ```

**T-P1 · culiapp-automation · Test nối 3 chặng (P1-1)**
- **ĐƯỢC SỬA:** `tools/poster_noi_gia.py` (mới), `cf/test/poster-noi-3-chang.test.mjs` (mới).
- **Phụ thuộc:** B-P1, W-P0, W-P1 (dùng mã thật của cả 3, chỉ đọc).
- **Việc:**
  - `tools/poster_noi_gia.py` — máy chạy giả, chạy bằng `python -B tools/poster_noi_gia.py`:
    - đặt `os.environ["KHO_POSTER_TEST"] = "1"` và xoá `TT_API_BEARER_TOKEN`, `TT_API_PORT`, `KHO_POSTER_WEB` **trước** khi import `poster_web`/`video_server`;
    - tạo thư mục tạm (`tempfile.mkdtemp`) chứa `.env` giả (`TT_API_BEARER_TOKEN=tok-gia`, `TT_API_PORT=<cổng backend giả>`), đặt `KHO_POSTER_DIR` và `KHO_POSTER_NHAT_KY` vào đó;
    - khởi động backend giả (`ThreadingHTTPServer` cổng 0) ghi lại mọi request; route phụ `GET /__ghi` trả danh sách đã ghi, `POST /__xoa` xoá danh sách; `/api/v2/...` trả `{"ok": true, "method", "path"}` ngay, riêng `POST /api/v2/queue/7/post` chờ 1,5 s;
    - khởi động `video_server.H` (cổng 0, khoá `khoa-gia`);
    - in đúng 1 dòng JSON `{"backend": <cổng>, "video": <cổng>, "khoa": "khoa-gia"}` ra stdout; thoát khi stdin đóng, xoá thư mục tạm.
  - `cf/test/poster-noi-3-chang.test.mjs`:
    - `spawn("python", ["-B", "tools/poster_noi_gia.py"])` từ gốc repo, đọc dòng JSON;
    - `globalThis.fetch` gốc chỉ được gọi với `http://127.0.0.1:<video>` hoặc `http://127.0.0.1:<backend>/__ghi|__xoa`; URL khác (kể cả `:8023`) ném lỗi;
    - nạp `web/poster.js` thật trong `vm` với DOM giả tối thiểu (`auth.on = true`, `document.hidden = false`); `fetch` của trang chuyển `/api/poster/<rest>` thành `apiPoster(new Request("https://kho.test/api/poster/<rest>", init + Origin "https://kho.test"), {VIDEO_ORIGIN: "http://127.0.0.1:<video>", VIDEO_KEY: "khoa-gia"}, url, {user: "nhan", chu: true})` import từ `cf/src/poster.js` thật;
    - mỗi ca gọi qua `pvApi`/`pvGoi` thật, rồi đọc `__ghi` của backend giả.
- **Tiêu chí xong** (mỗi method một ca, cộng ca nền):
  - GET `pvApi.listAccounts()` → backend nhận GET `/api/v2/accounts/`, không `Content-Type`, body rỗng, `Authorization: Bearer tok-gia`;
  - DELETE `pvApi.deleteQueueItem(5)` → backend nhận DELETE `/api/v2/queue/5`, **không** `Content-Type`, body rỗng; không có 415 ở chặng nào;
  - POST rỗng `pvApi.queueUnstick()` → backend nhận `Content-Type: application/json`, body `{}`;
  - POST có body `pvApi.accountCooldown(3)` → body `{"hours":24}`;
  - PUT `pvApi.putSetting("headless", "1")` → PUT `/api/v2/settings/headless` body `{"value":"1"}`;
  - PATCH `pvApi.archiveFolder(9, true)` → PATCH `/api/v2/folders/9` đúng body như `api_client.py`;
  - nền: `pvApi.postQueueItem(7)` → `202` → `pvGoi` hỏi `_kq` → trả `{"ok": true,…}`; gọi lại cùng lệnh trong lúc chờ → backend giả nhận **1** lần;
  - header tới backend không có `x-key`, `x-pv`, `x-poster-boi`, `cookie`;
  - tiến trình Python được kết thúc trong `after()` kể cả khi test lỗi.
- **Lệnh kiểm chứng:**

  ```
  python -B -m py_compile tools/poster_noi_gia.py
  node --test cf/test/poster-noi-3-chang.test.mjs
  ```
- **Mức cần đạt:** `fixture` (HTTP cục bộ cổng ngẫu nhiên, không dịch vụ ngoài).

**Mức cần đạt của W-P2..W-P5:** `fixture`.

### Lượt 3: trưởng phòng
1. Thêm vào `LENH` của `.culiapp/kiem-chung.py`:
   - JS: `cf/test/poster-worker.test.mjs cf/test/poster-web.test.mjs cf/test/pv-tong-web.test.mjs cf/test/pv-tk-dang-web.test.mjs cf/test/pv-folders-web.test.mjs cf/test/pv-lich-queue-web.test.mjs cf/test/poster-noi-3-chang.test.mjs`;
   - Python: `tools/test_poster_web.py`.

   Chạy `python .culiapp/kiem-chung.py`, tổng ≥ mốc.
2. Thử web tĩnh với `fetch` giả, như ca 2026-11-18-e: 9 trang ở 375px và 1280px, không cuộn ngang trang, thanh đáy 7 ô không che nút cuối, hộp thoại đóng/mở, dòng nhắc dưới nút login. Mức: `fixture`.
3. Hành động cần duyệt (§10), rồi kiểm live chỉ GET.

### Bảng file theo lượt (không trùng trong cùng lượt)

| Lượt | Phiếu | File |
|---|---|---|
| 1 | B-P1 | `tools/poster_web.py`, `tools/video_server.py`, `tools/test_poster_web.py` |
| 1 | W-P0 | `cf/src/poster.js`, `cf/src/worker.js`, `cf/test/poster-worker.test.mjs` |
| 1 | W-P1 | `web/poster.js`, `web/poster.css`, `web/khung.js`, `web/index.html`, `cf/test/poster-web.test.mjs`, `cf/test/menu-web.test.mjs`, `cf/test/homnay-web.test.mjs` |
| 2 | W-P2 | `web/pv-dashboard.js`, `web/pv-views.js`, `web/pv-logs.js`, `web/pv-settings.js`, `cf/test/pv-tong-web.test.mjs` |
| 2 | W-P3 | `web/pv-accounts.js`, `web/pv-post.js`, `cf/test/pv-tk-dang-web.test.mjs` |
| 2 | W-P4 | `web/pv-folders.js`, `cf/test/pv-folders-web.test.mjs` |
| 2 | W-P5 | `web/pv-calendar.js`, `web/pv-queue.js`, `cf/test/pv-lich-queue-web.test.mjs` |
| 2 | T-P1 | `tools/poster_noi_gia.py`, `cf/test/poster-noi-3-chang.test.mjs` |

`cf/src/worker.js`, `tools/video_server.py`, `web/index.html` đang có thay đổi chưa commit của đợt 5–8. Mỗi phiếu chỉ thêm đúng các dòng móc đã nêu. Trưởng phòng soát diff số dòng.

T-P1 phát hiện lệch hợp đồng ở phiếu nào thì trưởng phòng mở phiếu sửa riêng cho chủ file đó (B-P1 / W-P0 / W-P1) ở lượt sau; T-P1 không sửa file của phiếu khác.

---

## 10. Hành động cần duyệt (trưởng phòng chạy sau khi người dùng duyệt D13 và kết quả lượt 3)

| # | Lệnh (cwd) | Tác động | Hoàn tác |
|---|---|---|---|
| 1 | Dừng tiến trình `python video_server.py` của cửa sổ "kho-video-server", rồi `start "kho-video-server" python video_server.py` (cwd `E:/phantichcanhquay/kho-san-pham/tools`; env tuỳ chọn `KHO_POSTER_DIR`, `KHO_POSTER_NHAT_KY`) | Nút tải/xem video và `/r/*` gián đoạn vài giây. Tạo `%LOCALAPPDATA%\kho-poster-web\nhat-ky.jsonl` khi có lệnh ghi đầu tiên. Đọc `E:/tool/tiktok_poster_v2/.env`. | Bật lại với `KHO_POSTER_WEB=0` (tắt `/p/*` ngay, không cần sửa code), hoặc chạy bản `tools/video_server.py` trước phiếu. |
| 2 | `npx wrangler deploy` (cwd `E:/phantichcanhquay/kho-san-pham/cf`) | Worker mới + web tĩnh mới (menu 7 mục, 11 file JS/CSS mới) | `npx wrangler rollback <id bản trước>`. Ghi id bản trước, hiện là `c6ed93ac` theo nhật ký ca e, trưởng phòng kiểm lại bằng `npx wrangler deployments list`. |
| 3 | Kiểm live **chỉ đọc**: đăng nhập `nhan`, mở lần lượt 9 tab `#/poster/<trang>`, xem dữ liệu thật. **Không bấm nút ghi nào** (Đăng ngay, Thêm vào Queue, Auto post, Save, Delete, Cooldown, Check, Test, Refresh của Views, Gỡ kẹt…). Tab Đăng bài chỉ chọn folder để xem danh sách video (`_video`, chỉ đọc). Tab Accounts có gọi `GET views/health/{id}`, GET này **ghi** `account_health` (`views.py:440-447`), như khi mở desktop. Mở DevTools xem phản hồi `GET /api/poster/api/v2/settings/`: các khoá secret là `"***"`. Thử thêm 1 tài khoản người thường: không thấy mục, `GET /api/poster/api/v2/stats/` (kèm `x-pv: 1`) → 403. | Chỉ GET tới backend production (kèm ghi phụ `account_health` như desktop). Lần đầu Folders có thể mất ~84 s, web nhận 202 rồi tự hỏi `_kq`. | Không cần. |

Mức kiểm chứng sau bước 3: `live` (chỉ GET), do trưởng phòng chạy. Các nút ghi chỉ đạt `fixture` cho tới khi người dùng tự bấm thật.

---

## 11. Câu hỏi cho người dùng (trưởng phòng hỏi)

Đã trả lời (A-PV1b):
- **Q1. Phạm vi API** → "Mở hết /api/v2/". Đã sửa §2, §4.6, D13.
- **Q2. Video Loại và hạn mức** → "Giữ nguyên như app gốc". Không chặn; rủi ro ở §4.6, D13.
- **Q3. Nút "🔓 Tạo profile & Login lấy cookies"** → "Giữ, thêm dòng nhắc". Dòng nhắc ở §5.3, W-P3.

Đã trả lời (A-PV1c, 2026-11-18):
- **Q4. Duyệt D13 (bản sửa A-PV1b)?** → "Đồng ý, làm đi". D13 chuyển "Đã chốt"; D3, D9, D12 đã ghi "Bị thay một phần bởi D13". Phạm vi được duyệt: bấm thẳng mọi nút ghi, không runner, không mật khẩu; mở hết `/api/v2/`; `x-pv` + Origin + JSON-only + nhật ký máy nhà; chốt B1/B2/B3, che secret C1; bảng lệnh chống trùng trong video_server (1 lệnh đăng mỗi lúc); không chặn video Loại, không hạn mức.
- **3 điểm kiến trúc sư tự thêm** (người dùng chọn "Đồng ý, làm đi" thay vì bỏ 3 chỗ này) → **chấp nhận**:
  - header `x-pv: 1` bắt buộc với mọi request, kể cả GET (§4.2);
  - cấm ký tự `%` trong path (§4.3, lọc path chung ở §2);
  - lệnh lớp S quá 80 s tự chuyển nền, trả 202 `{cho}` (§3.2, §3.3).

Không còn câu hỏi mở.
