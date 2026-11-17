# Bộ chạy việc cho web Kho sản phẩm (đợt 3–5)

Phiếu A-01, sửa lại theo phiếu A-01b (phản biện) · Kiến trúc sư Culiapp · 2026-11-17
Trạng thái: **ĐỀ XUẤT, chờ người dùng duyệt**. Quyết định D1–D9 ghi trong `DECISIONS.md` (D9: sổ lời duyệt đã tiêu trên Cloudflare KV, sửa review R-11; phiếu A-D9).

Trước tài liệu này, dự án chưa có `CLAUDE.md`, `ARCHITECTURE.md`, `DECISIONS.md` hay `KNOWN_BUGS.md` (đã dò ở gốc repo và thư mục cha). Thiết kế dựa trên ba nguồn:
- code thật, dẫn `file:dòng`;
- biên bản hội đồng `C:\Users\Mi\.claude\hop\VideoBatchLocal-20261117-1504\99-verdict.md`;
- nhật ký `.culiapp/nhat-ky.md`.

Người dùng đã chốt sau hội đồng: **mọi thứ nằm trong CÙNG MỘT web (web Kho)**, kể cả `aff-taovideo` (câu hỏi giữa chừng hiện trên web, trả lời trên web).

Mục §16 đối chiếu từng lỗi phản biện A-01b với chỗ đã sửa.

---

## 0. Tóm tắt một màn hình

- **Tiến trình riêng trên máy nhà** (D1, D8). Code runner được **cài ra thư mục cố định ngoài repo** `%LOCALAPPDATA%\kho-runner\app\`, chép từ `tools/runner/` của repo. Lý do: `kho.py` pull/commit trong repo sẽ không làm đổi code runner đang chạy. Dữ liệu chạy (SQLite, log) cũng nằm ở `%LOCALAPPDATA%\kho-runner\`. Runner nghe `127.0.0.1:8788`.
- **Một instance duy nhất.** Ngay dòng đầu `main()`, runner phải giành named mutex `Local\kho-runner` **và** khoá file `runner.lock`. Chỉ sau đó mới đụng tới job hay tiến trình.
- **Đường vào** (D2): Worker → `video.kutidak.com/r/*` (tunnel có sẵn) → `video_server.py` chuyển tiếp sang runner. Runner kiểm 2 lớp:
  - `x-runner-key` cho mọi request;
  - **chữ ký Ed25519 của Worker** cho mọi request ghi (D7).

  Agent chạy cùng user Mi có đọc được `.runner_key` hay `runner.db` cũng **không tự tạo, trả lời hay duyệt việc được**.
- **Danh mục việc cố định** (D3). Web không gửi đường dẫn hay lệnh. **Đợt 3 chỉ trả lời bằng nút** (chọn / đã làm xong / tiếp tục). Chữ tự do (trả lời ở đợt 5, lời duyệt ở đợt 4) bắt nhập lại mật khẩu mỗi lần gửi và được Worker ký.
- **Web cứng hơn trước khi mở quyền ghi:**
  - tự host `marked@12.0.2`, `dompurify@3.4.18`, `qrcode-generator@1.4.4` trong `web/vendor/`;
  - đặt CSP `script-src 'self'` qua `web/_headers`.
- **Hai làn** `gpu` / `nhe`, mỗi làn 1 việc. Có thêm **mutex tài nguyên `kho`** dùng chung mọi làn cho việc gọi `kho.py`.
- **Claude headless theo lượt** (D4): `claude.exe -p --agent … --tools … --permission-mode dontAsk --output-format stream-json`, phiếu đưa qua stdin, `--resume` khi người dùng trả lời. Chốt chi phí:
  - hạn mức USD/ngày;
  - **dự phòng** số job Claude/ngày và trần số lượt mỗi job (đếm từ luồng sự kiện), vì USD có thể sai khi đi qua proxy.
- **Việc tốn tiền** (D5): luôn vào `cho_duyet`. Hạn mức là **hằng số trong code**; `cau_hinh.json` chỉ được hạ. Chữ ký duyệt được kiểm lại lúc nhận việc.
- **Bền qua reboot** (D6): runner tự gắn mình vào Windows Job Object (con cháu sinh ra đã nằm sẵn trong job, không có khoảng hở). Khi khởi động lại: dọn mồ côi, đối soát đầu ra, chỉ tự chạy lại việc idempotent.
- **Đợt 3 dùng được độc lập** (6 việc miễn phí, gồm `douyin_uid` mới) trước đợt 4 (tốn tiền) và đợt 5 (`aff-taovideo`).

---

## 1. Hiện trạng đã kiểm (bằng chứng)

| Điều | Bằng chứng |
|---|---|
| Repo đang ở `main`; code đợt 1–2 là thay đổi chưa commit | `git branch --show-current` → `main` (phiếu A-01b) |
| `.gitignore` đã có `tools/.video_key` | `.gitignore` (đã đọc) |
| Cookie phiên `SameSite=Lax`, HttpOnly | `cf/src/worker.js:90` |
| Chặn POST khác Origin, nhưng cho qua khi **thiếu** Origin | `cf/src/worker.js:432-435` |
| Chỉ `nhan`/`comeofage` được dùng máy nhà | `cf/src/worker.js:178`; kiểm ở `:243`, `:271`, `:292` |
| Kiểm mật khẩu PBKDF2 (dùng lại được để xác nhận lại mật khẩu) | `cf/src/worker.js:62-71` (`bamMatKhau`, `kiemMatKhau`), `:72-74` (`dsUser`) |
| Proxy `/api/video` → `${VIDEO_ORIGIN}/v/...` kèm `x-key`, timeout 15 s; 401/403 đổi thành 502 | `cf/src/worker.js:184-186`, `:242-268`, `:260-264` |
| Tài sản tĩnh KHÔNG đi qua Worker (chỉ `/api/*` đi qua), nên Worker không thể gắn CSP vào HTML | `cf/wrangler.toml` mục `[assets]`: `run_worker_first = ["/api/*"]`; `cf/src/worker.js:430` |
| Thư viện JS nạp từ jsdelivr, không ghim bản, không SRI | `web/index.html:8-10` |
| video_server chỉ nghe 127.0.0.1; khoá `x-key`; danh sách app dò cổng; `GOCS` | `tools/video_server.py:281`, `:28`, `:33-36`, `:183`, `:120-121`, `:24` |
| Web: `laChu`, `tinhBuoc`/`buocHienTai`, trang 🩺, `veBuoc`, router | `web/app.js:53`, `:305-384`, `:403-423`, `:635-645`, `:772-782` |
| `kho.py` pull/commit/push trong repo, không có khoá liên tiến trình | `tools/kho.py:43`, `:304-331` |
| `kho.py cho` in mỗi link chờ thành 1 dòng `id\tlink\t…` | `tools/kho.py:404-419` |
| `kho.py ghi` đặt `da_phan_tich=True` ngay khi có file 01 (Bước 6), **trước** Douyin và rủi ro | `tools/kho.py:462-465`; Douyin `:466-468`; rủi ro `:625-641` (`i["rui_ro"]` ở `:631`) |
| `kho.py ghi` nhận Douyin từ `douyin/canh_quay_an_tien.md` → `data/<id>/douyin.md` | `tools/kho.py:231-235`, `:466-467` |
| Lệnh agy chuẩn cho Douyin | `C:\Users\Mi\.claude\skills\phantichcanhquay\SKILL.md:145-150` |
| Tự khởi động: Startup `chay_video_autostart.bat` → `tools/chay_video.bat` (video_server + một connector cloudflared thứ hai) | `tools/chay_video.bat:4-5` |
| Service cloudflared chạy dưới LocalSystem | `sc qc cloudflared` (chỉ đọc) |
| Claude CLI 2.1.169 có `-p`, `--agent`, `--agents`, `--tools`, `--session-id`, `--resume`, `--output-format stream-json`, `--permission-mode … dontAsk`, `--allowedTools`, `--disallowedTools`, `--max-budget-usd`, `--add-dir`. **Không có `--max-turns`** | `claude --help` |
| File thực thi thật của Claude | `C:\Users\Mi\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe` (theo `claude.cmd`) |
| `~/.claude/settings.json`: `permissions.defaultMode = bypassPermissions`; `env` có `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL` (proxy), `ANTHROPIC_*_MODEL` | đọc tên khoá, không in giá trị |
| Python 3.12.3, `psutil` 7.0.0, `cryptography` 45.0.5 (có Ed25519), SQLite 3.45.1, Node 24.16 | đã chạy |
| Workers Web Crypto hỗ trợ `Ed25519` sign/verify, import khoá riêng dạng PKCS8/JWK (không nhận raw) | https://developers.cloudflare.com/workers/runtime-apis/web-crypto/ |
| Phiên bản thư viện hiện hành | `npm view`: marked 12.0.2, dompurify 3.4.18, qrcode-generator 1.4.4 |
| Agent và điểm hỏi | `aff-taovideo.md:10`, `:32`, `:34`, `:36`; `aff-poster.md:11`, `:28-30`, `:41`, `:47-59`; `aff-muse.md:29-30`, `:43`; `aff-san-pham.md:26`, `:33`, `:41`; `aff-voice.md:23`, `:32`; `aff-radar.md:22`, `:30`, `:48`, `:69`, `:73` |
| GenMax không có `--dong-y` thì không gọi API | `tao-video-tu-canh-quay\scripts\tao_voice.py:7-12`, `:599-601` |
| PerfectVoice script | `tao_voice_pv.py:6`, `:122`, `:189` |
| Quy ước `CẦN_USER` | `tao-video-tu-canh-quay\SKILL.md:67`; `scripts\do_token.py:21` |

---

## 2. Kiến trúc tổng thể

```
Điện thoại: web/app.js + web/viec.js (+ web/vendor/*, CSP qua web/_headers)
   │ cookie phiên; chỉ nhan/comeofage; đợt 3: trả lời bằng nút; đợt 4–5: chữ tự do + nhập lại mật khẩu
   ▼
Cloudflare Worker cf/src/worker.js
   │ /api/viec/*: kiểm phiên + quyền + Origin bắt buộc + hình dạng tham số
   │ ký Ed25519 mọi request ghi (KY_RIENG); ký riêng lời duyệt (D7)
   │ fetch https://video.kutidak.com/r/...  (x-key, x-runner-key, x-ky-*)
   ▼
Cloudflare Tunnel (service LocalSystem, KHÔNG đổi)
   ▼
tools/video_server.py (repo) 127.0.0.1:8787
   │ /r/*: kiểm x-key → lọc path/query/body → chuyển x-runner-key + x-ky-* + content-type
   ▼
%LOCALAPPDATA%\kho-runner\app\  (bản cài, chép từ tools/runner) 127.0.0.1:8788, user Mi
   ├─ chay_runner.py  main(): mutex đơn instance → Job Object tự gắn → dọn/đối soát → HTTP + 2 làn
   ├─ api.py          x-runner-key; chu_ky.py kiểm chữ ký ghi + chữ ký duyệt; nonce chống phát lại
   ├─ kho_viec.py     SQLite (CAS), nonce, sự kiện, đếm hạn mức
   ├─ danh_muc.py     allowlist + tham số + điều kiện trước + tài nguyên + lập bước + đối soát
   ├─ han_muc.py      trần hằng số trong code; cau_hinh.json chỉ được hạ
   ├─ du_an.py        dò dự án theo UID (GOCS sao từ video_server, có test đối chiếu)
   ├─ phieu.py        dựng phiếu, đọc TRẠNG THÁI / CẦN_USER
   ├─ radar_xuat.py   xuất dữ liệu radar từ SQLite chỉ đọc ra JSON (cho Claude không cần Bash)
   ├─ stream_json.py  đọc trường sự kiện của Claude (cô lập để sửa sau spike)
   ├─ thuc_thi.py     tiến trình con: console ẩn, quá giờ, log, che bí mật, env tối thiểu, giết cây
   └─ vong_lap.py     2 làn, mutex tài nguyên, khởi động lại
        ├─ script: kho.py (repo), day_len_poster.py (venv Poster), tao_voice_pv.py, tao_voice.py, agy.exe, quet_dot_bien_7ngay.py
        └─ claude.exe -p --agent aff-radar | aff-san-pham | aff-muse | aff-poster | aff-taovideo
```

Ranh giới:
- **Core logic** (thuần, test không cần tiến trình): `kho_viec`, `danh_muc`, `han_muc`, `du_an`, `phieu`, `chu_ky`, `stream_json`, `radar_xuat`.
- **Automation service**: `thuc_thi`, `vong_lap`, `chay_runner`, `tools/cai_runner.py`.
- **Giao diện**: `api.py`, Worker, `web/viec.js`.

---

## 3. Đường vào từ Internet

### 3.1 Hai phương án (giữ phân tích gốc)

| | (a) Hostname tunnel mới `runner.kutidak.com` | (b) video_server chuyển tiếp `/r/*` (CHỌN) |
|---|---|---|
| Thao tác | Sửa `C:\Users\Mi\.cloudflared\config.yml` + khởi động lại service = **UAC**; muốn chặt cần Cloudflare Access (dashboard) | Không UAC. Trưởng phòng đặt 2 secret Worker |
| Lộ `VIDEO_KEY` | Không liên quan | Tới được `/r/*`, nhưng thiếu `RUNNER_KEY` + chữ ký thì không làm được gì |
| Lộ `RUNNER_KEY` | Đủ để gọi thẳng runner nếu không có Access | Không đủ: còn phải qua video_server, runner chỉ nghe 127.0.0.1, và request ghi cần chữ ký Worker |
| Phụ thuộc | Độc lập | Phụ thuộc video_server còn sống (bật cùng nhau) |

**Chọn (b):** không UAC; bảo mật bằng hoặc hơn (a) khi không có Access. Lý do chi tiết ở D2.

### 3.2 Quy tắc chuyển tiếp trong video_server

- Path phải khớp `^/r/(suc-khoe|danh-muc|poster/folders|du-an/\d{19}|viec(/j\d{14}[a-z0-9]{4}(/(log|tra-loi|duyet|tu-choi|huy|chay-lai|chay-tiep|xin-duyet-lai))?)?)$` (`xin-duyet-lai` thêm theo D9, phiếu FX-12). Không khớp thì 404, không gọi runner.
- Query: chỉ giữ khoá `tu`, `trang_thai`, `uid`, `gioi_han`, `tom_tat`; giá trị phải khớp `^[A-Za-z0-9_,-]{0,40}$`.
- Method: GET, hoặc POST với `content-type: application/json` và body ≤ 16 KB (lớn hơn → 413).
- Kiểm `x-key` trước mọi thứ (dùng `_vao`, `tools/video_server.py:181-191`).
- Chỉ chuyển các header: `x-runner-key`, `x-ky`, `x-ky-ngay`, `x-ky-nonce`, `content-type`. **Không** chuyển `x-key`.
- Gọi `http://127.0.0.1:8788` (bỏ tiền tố `/r`), timeout 10 s. Runner tắt → 502 `{"loi":"Bộ chạy việc chưa bật"}`. Status và body ≤ 1 MB trả nguyên.
- Thêm `("runner", "Bộ chạy việc", 8788)` vào `APPS` (`tools/video_server.py:120-121`).

### 3.3 Quy tắc ở Worker

- `/api/viec*` chỉ cho `USER_MAY_NHA`. Thiếu `RUNNER_KEY` hoặc `KY_RIENG` → 503.
- POST **bắt buộc** có `Origin` đúng origin của web.
- Body được dựng lại từ các khoá cho phép, gắn `boi = phien.user`.
- **Ký mọi request ghi** theo §8.3. Từ đợt 4, ký thêm lời duyệt. Request có chữ tự do bắt `mat_khau` và kiểm bằng `kiemMatKhau`; mật khẩu không bao giờ chuyển đi.
- 401/403 từ phía máy nhà → 502 "Máy nhà từ chối khoá/chữ ký bộ chạy việc".

---

## 4. Runner

### 4.1 Cài đặt, đơn instance, khoá (D8, P1-1)

**Thư mục cài và dữ liệu:**
- Repo `tools/runner/` là **mã nguồn**. Muốn đưa vào dùng thì chạy `python tools/cai_runner.py`:
  - kiểm runner đang tắt (thử giành mutex; giành không được thì dừng, mã 4);
  - chép `tools/runner/*.py` (trừ `test_*`, `spike_*`), `tools/runner/ky_cong_khai.pem` và `tools/chay_runner.py` vào `%LOCALAPPDATA%\kho-runner\app.moi\`;
  - ghi `PHIEN_BAN` = `git rev-parse --short HEAD` + `-sua` nếu `git status --porcelain tools/runner` không rỗng;
  - đổi tên `app` → `app.cu` (xoá `app.cu` cũ trước), rồi `app.moi` → `app`.

  Việc cài là ghi ngoài thư mục dự án, nên mỗi lần là **NEEDS_APPROVAL**, trưởng phòng chạy.
- Startup chạy bản cài: `tools/chay_video.bat` thêm dòng `start "kho-runner" /min python "%LOCALAPPDATA%\kho-runner\app\chay_runner.py"`.
- Dữ liệu: `%LOCALAPPDATA%\kho-runner\`, gồm:
  - `runner.db` (WAL);
  - `runner.lock`;
  - `log\`;
  - `radar\` (JSON xuất từ DB radar);
  - `.runner_key` (tự sinh lần đầu);
  - `cau_hinh.json` (tuỳ chọn, chỉ được **hạ** hạn mức, xem §10).

  Biến `KHO_RUNNER_DIR` đổi được thư mục này; test luôn dùng thư mục tạm.
- Dữ liệu sản phẩm vẫn ở repo (`kho.py` giữ nguyên đường dẫn, agent không phải sửa).

**Đơn instance — `main()` làm đúng thứ tự, bước 1 trước mọi việc khác:**
1. `CreateMutexW(None, True, "Local\\kho-runner")` qua ctypes. `GetLastError() == ERROR_ALREADY_EXISTS (183)` → in "Bộ chạy việc đã chạy", thoát mã 3. **Không** mở DB, **không** dọn mồ côi.
2. Mở `runner.lock` và `msvcrt.locking(fd, LK_NBLCK, 1)`. Thất bại → thoát mã 3 (lưới thứ hai, phòng session khác).
3. Tự gắn tiến trình runner vào Job Object (§4.6).
4. Mở DB, dọn mồ côi, đối soát (§4.6).
5. Bind `127.0.0.1:8788` (thất bại → ghi log, thoát mã 5).
6. Bật 2 làn.

Chạy dưới **user Mi** (Startup folder) chứ không phải LocalSystem, vì đăng nhập Claude, agy, Edge và venv Poster đều nằm trong profile Mi.

### 4.2 SQLite schema (phiên bản 1)

```sql
PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS meta(khoa TEXT PRIMARY KEY, gia_tri TEXT NOT NULL);       -- ('schema','1')
CREATE TABLE IF NOT EXISTS viec(
  id TEXT PRIMARY KEY,                       -- 'j' + YYYYMMDDHHMMSS (giờ VN) + 4 ký tự [a-z0-9]
  loai TEXT NOT NULL, khoa TEXT NOT NULL,
  tham_so TEXT NOT NULL,                     -- JSON CHUẨN: json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=False)
  lan_chay TEXT NOT NULL CHECK(lan_chay IN ('gpu','nhe')),
  trang_thai TEXT NOT NULL CHECK(trang_thai IN ('cho','dang_chay','can_tra_loi','cho_duyet','xong','loi','huy')),
  buoc TEXT NOT NULL DEFAULT 'chay',         -- 'uoc_tinh' | 'chay'
  tao_boi TEXT NOT NULL, tao_luc TEXT NOT NULL, cap_nhat_luc TEXT NOT NULL,
  bat_dau_luc TEXT, ket_thuc_luc TEXT,
  lan_thu INTEGER NOT NULL DEFAULT 1, cha_id TEXT REFERENCES viec(id), chay_lai_tu TEXT REFERENCES viec(id),
  pid INTEGER, pid_tao_luc REAL,
  session_id TEXT,                           -- UUID phiên Claude
  phien_da_tao INTEGER NOT NULL DEFAULT 0,   -- 1 khi đã thấy sự kiện init có session_id → mới được --resume
  cau_hoi TEXT,                              -- JSON {loai:'chon'|'viec_tay'|'khong_ro'|'cau_hoi', noi_dung, lua_chon:[...]}
  can_ban TEXT,                              -- thông báo KHÔNG chặn khi đang chạy (vd "Douyin đòi captcha, giải trong cửa sổ Chrome")
  uoc_tinh TEXT,
  loi_duyet TEXT, duyet_boi TEXT, duyet_luc TEXT, chu_ky_duyet TEXT,   -- D7
  ket_qua TEXT,                              -- JSON {trang_thai_agent, co_lo_ngai, tom_tat, file_ra:[...]}
  loi TEXT, ghi_chu TEXT,
  chi_phi_usd REAL NOT NULL DEFAULT 0, so_luot_claude INTEGER NOT NULL DEFAULT 0, so_lan_claude INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS viec_dang_mo ON viec(loai, khoa)
  WHERE trang_thai IN ('cho','dang_chay','can_tra_loi','cho_duyet');
CREATE INDEX IF NOT EXISTS viec_tt ON viec(trang_thai, lan_chay, tao_luc);
CREATE TABLE IF NOT EXISTS su_kien(id INTEGER PRIMARY KEY AUTOINCREMENT, viec_id TEXT NOT NULL REFERENCES viec(id),
  luc TEXT NOT NULL, tu TEXT, den TEXT NOT NULL, boi TEXT NOT NULL, ghi_chu TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS tra_loi(id INTEGER PRIMARY KEY AUTOINCREMENT, viec_id TEXT NOT NULL REFERENCES viec(id),
  luc TEXT NOT NULL, boi TEXT NOT NULL, cau_hoi TEXT NOT NULL, noi_dung TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS nonce(gia_tri TEXT PRIMARY KEY, luc REAL NOT NULL);       -- chống phát lại chữ ký, xoá dòng > 1 ngày
```

- `so_luot_claude`: số lượt (turn) cộng dồn qua mọi lần chạy, đếm từ luồng sự kiện.
- `so_lan_claude`: số lần gọi `claude.exe`.
- Mỗi luồng mở một kết nối riêng. Mọi chuyển trạng thái là **CAS**: `UPDATE … WHERE id=? AND trang_thai IN (…)`; `rowcount = 0` → `SaiTrangThai`.

### 4.3 Máy trạng thái

| Từ | Đến | Khi nào |
|---|---|---|
| (mới) | `cho` | `POST /viec`, loại miễn phí, điều kiện trước đạt |
| (mới) | `can_tra_loi` (`viec_tay`) | điều kiện trước hỏng lúc tạo (vd Poster tắt) |
| (mới) | `cho_duyet`, hoặc `cho` + `buoc='uoc_tinh'` | loại `ton_tien` (đợt 4–5) |
| `cho` | `dang_chay` | làn rảnh, tài nguyên rảnh, hạn mức còn, chữ ký duyệt hợp lệ (nếu là loại tốn tiền) |
| `dang_chay` | `cho` | **điều kiện trước hỏng hoặc tài nguyên bận ngay sau khi nhận** (vd git kho đang bận, GPU có ffmpeg ngoài); ghi chú lý do, thử lại sau 60 s |
| `dang_chay` | `xong` / `loi` / `can_tra_loi` / `cho_duyet` | runner đọc kết quả (§6.5) |
| `can_tra_loi` | `cho` | `POST /tra-loi` (đợt 3: chỉ giá trị nút), loại **miễn phí** |
| `loi` / `can_tra_loi` | `cho_duyet` | **`POST /xin-duyet-lai`** (D9), chỉ loại tốn tiền: xoá 4 trường duyệt, giữ `session_id`/`phien_da_tao`/`loi`/`cau_hoi` để lần chạy sau resume. Loại tốn tiền **không** nhận `POST /tra-loi` (409 "việc tốn tiền: dùng Xin duyệt lại") |
| `loi` / `can_tra_loi` | `cho` + `buoc='uoc_tinh'` | **`POST /xin-duyet-lai`** của `voice_genmax` khi **chưa có ước tính** (`uoc_tinh` rỗng): chạy lại pha ước tính miễn phí, xong mới sang `cho_duyet` (A-D9b) |
| `cho_duyet` | `cho` | `POST /duyet` có chữ ký duyệt hợp lệ, hạn mức còn |
| `cho_duyet` | `huy` | `POST /tu-choi` |
| trạng thái mở | `huy` | `POST /huy` (đang chạy → giết cây trước) |
| `loi` | `cho` | **`POST /chay-tiep`**: chỉ loại **miễn phí**, khi `phien_da_tao=1` và `so_lan_claude>0`. Loại tốn tiền → 409, dùng "Xin duyệt lại" (D9). Lần chạy kế là `--resume` với tin "Phiên trước dừng vì: <loi>. Kiểm trạng thái thật rồi làm tiếp" |
| `loi` / `huy` | (job mới) | `POST /chay-lai`: tạo job mới có `chay_lai_tu`; loại tốn tiền vào `cho_duyet` lại |

### 4.4 Làn và tài nguyên

- **Làn `gpu`** (1 việc): `voice_pv`, `voice_genmax`, `taovideo`. Điều kiện trước: không có `ffmpeg.exe` nào nằm ngoài cây tiến trình của runner.
- **Làn `nhe`** (1 việc): `radar_ban_tin`, `phan_tich_uid`, `douyin_uid`, `xu_ly_link_moi`, `poster_day_folder`, `muse_clip`, `poster_len_lich`.
- **Mutex tài nguyên** (P2-8): `LoaiViec.tai_nguyen: frozenset[str]`. Runner giữ một `threading.Lock` cho mỗi tên tài nguyên, **dùng chung cho mọi làn**. Khi nhận việc, `nhan_viec_ke` chỉ chọn job FIFO đầu tiên trong làn mà mọi tài nguyên của nó đang rảnh. Tài nguyên được giữ suốt job.
  - `kho`: `phan_tich_uid`, `douyin_uid`, `xu_ly_link_moi`, `taovideo`. Hệ quả: khi `taovideo` chạy (hàng giờ), các việc đụng kho ở làn `nhe` phải đợi. Radar, poster và muse vẫn chạy. Chấp nhận được vì taovideo ≤ 1 lần/ngày.
  - `poster`: `poster_day_folder`, `poster_len_lich`.
- **Chẩn đoán kho** trước khi chạy việc có tài nguyên `kho`. Mỗi lỗi có thông điệp riêng:
  1. Có `.git/index.lock` và một tiến trình `git.exe` đang chạy (psutil), hoặc file khoá mới hơn 10 phút → `dang_chay→cho`, ghi chú "git kho đang bận (có thể bạn đang chạy kho.py tay)".
  2. Có `.git/index.lock` cũ hơn 10 phút và không có `git.exe` → `can_tra_loi/viec_tay`: "Có khoá git cũ `E:\phantichcanhquay\kho-san-pham\.git\index.lock` (lần chạy trước bị ngắt). Kiểm không có cửa sổ git nào rồi xoá file này, bấm Đã làm xong".
  3. Nhánh khác `main` → `viec_tay`: "Thư mục kho đang ở nhánh `<x>`; chuyển về main".
  4. `git status --porcelain -- data` không rỗng → `viec_tay` kèm tối đa 10 đường dẫn bẩn: "Dữ liệu kho có thay đổi chưa đẩy".

  Code chưa commit **ngoài** `data/` (đợt 1–2 trên `main`) không chặn: `kho.py` dùng `pull --rebase --autostash` (`tools/kho.py:313`). Xung đột autostash → `kho.py` in `[LỖI] git …`, job vào `loi` với nguyên văn.

### 4.5 Khoá chống trùng

Unique index một phần `viec_dang_mo(loai, khoa)`. `tao()` ném `TrungViec(viec_dang_mo)`; API trả 409.

| Loại | Khoá |
|---|---|
| `radar_ban_tin` | ngày giờ VN lúc tạo `YYYY-MM-DD` |
| `phan_tich_uid`, `douyin_uid`, `taovideo` | UID |
| `xu_ly_link_moi` | `kho` |
| `poster_day_folder`, `muse_clip` | `ma_du_an` |
| `voice_pv`, `voice_genmax` | `ma_du_an:me` |
| `poster_len_lich` | `folder:<id>` |

### 4.6 Job Object, khởi động lại, mồ côi

**Job Object toàn runner (P3: không có khoảng hở sau Popen).** Ở bước 3 của `main()`:
- `CreateJobObjectW` + `SetInformationJobObject(JobObjectExtendedLimitInformation, LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)`;
- `AssignProcessToJobObject(job, GetCurrentProcess())`.

Mọi tiến trình con cháu sinh sau đó **đã nằm trong job ngay lúc tạo**. Runner chết thì cả cây chết theo. Windows 8 trở lên hỗ trợ job lồng nhau, nên runner được bật từ cửa sổ đã nằm trong job khác vẫn chạy được. Gắn thất bại → ghi log "Không gắn được Job Object — tiến trình con có thể mồ côi khi runner chết" và chạy tiếp (lưới dự phòng là bước dọn dưới đây).

**Giết một job** (quá giờ hoặc Huỷ): `psutil.Process(pid).children(recursive=True)` + tiến trình gốc → `kill()`, chờ 10 s, rồi `taskkill /T /F /PID <pid>` dự phòng.

**Khởi động lại** (bước 4 của `main()`, chỉ chạy khi đã giành được mutex):
1. Mỗi job `dang_chay`: nếu `pid` sống **và** `create_time` khớp `pid_tao_luc` (±1 s) thì giết cây; PID đã bị tái dùng thì không đụng.
2. Gọi `kiem_dau_ra` → `quyet_dinh_sau_khoi_dong`:

| Đối soát | `tu_chay_lai=True` và `lan_thu < 3` | Ngược lại |
|---|---|---|
| `xong` | `xong` ("đối soát sau khởi động lại") | như bên trái |
| `chua` | `cho`, `lan_thu+1`; có `phien_da_tao=1` thì lần kế là resume | `loi` "Bị ngắt khi máy tắt — kiểm rồi bấm Chạy tiếp/Chạy lại" |
| `khong_ro` | như ô Ngược lại | `loi` như trên |

   Việc tốn tiền không bao giờ tự chạy lại. Lời báo của việc tốn tiền là "Bị ngắt khi máy tắt — kiểm log rồi bấm Xin duyệt lại/Chạy lại" (không có Chạy tiếp, D9).
3. Xoá log và JSON radar cũ hơn 30 ngày; xoá dòng `nonce` cũ hơn 1 ngày.

### 4.7 Log, che bí mật, môi trường tối thiểu (P2-1)

- Log:
  - việc script ghi `log\<id>.log`;
  - việc Claude ghi stream-json thô vào `log\<id>.jsonl`, kèm bản người đọc ở `log\<id>.log`.
- API trả log theo offset byte, ≤ 64 KB mỗi lần, **đã che bí mật**.
- **Che theo GIÁ TRỊ.** Danh sách giá trị cần che được dựng lại mỗi lần phục vụ log, có cache 60 s theo mtime của file nguồn. Chỉ che giá trị dài từ 12 ký tự trở lên:
  - mọi giá trị trong `C:\Users\Mi\.claude\settings.json` → `env` (gồm `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`);
  - `os.environ["GENMAX_API_KEY"]` nếu có;
  - nội dung `tools/.video_key` và `%LOCALAPPDATA%\kho-runner\.runner_key`;
  - mọi giá trị chuỗi có tên khoá khớp `(?i)token|key|secret|pass` trong `E:\quet-kenh-anti\cau-hinh.json` (token Telegram).
- **Che theo MẪU:** `sk-[A-Za-z0-9_-]{20,}`, `(ghp_|github_pat_)[A-Za-z0-9_]{10,}`, `\d{8,10}:[A-Za-z0-9_-]{30,}` (token bot Telegram). Tất cả thay bằng `***`.
- **Môi trường tối thiểu cho tiến trình con.** Không kế thừa toàn bộ `os.environ`; chỉ chép `SYSTEMROOT, SYSTEMDRIVE, WINDIR, COMSPEC, PATH, PATHEXT, USERPROFILE, USERNAME, USERDOMAIN, HOMEDRIVE, HOMEPATH, APPDATA, LOCALAPPDATA, PROGRAMDATA, PROGRAMFILES, PROGRAMFILES(X86), TEMP, TMP, COMPUTERNAME, NUMBER_OF_PROCESSORS, PROCESSOR_ARCHITECTURE`, cộng `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`.
  - `GENMAX_API_KEY` chỉ thêm cho `voice_genmax` pha `chay`.
  - Claude tự đọc `ANTHROPIC_*` từ `settings.json` nên không truyền. Spike S-01 kiểm Claude vẫn đăng nhập được với env tối thiểu.

---

## 5. Danh mục việc (allowlist)

Quy tắc chung:
- **UID** `^\d{19}$`.
- **Dự án** là `ma` 12 hex (`sha1(duong_dan.as_posix())[:12]`), tra lại trong `ds_du_an(uid)` do runner tự dò `<GOC>/*<UID>`. `GOCS` mặc định **sao y** `tools/video_server.py:24`, đổi bằng cùng biến `KHO_VIDEO_GOC`. Một test trong repo kiểm hai danh sách giống nhau.
- **Mẻ** `^\d{8}-[a-z0-9]{1,12}$`, phải nằm trong `ds_me(P)` (từ `P/kich-ban/<me>_kich-ban-da-cham.md`).
- **Không loại nào nhận chữ tự do vào lệnh.** Chữ tự do chỉ có ở `tra_loi` (đợt 5) và `loi_duyet` (đợt 4), xem §9.
- `dot_bat` = min(`DOT_TOI_DA` trong code, `cau_hinh.json`). Loại có `dot > dot_bat` → 400.

### 5.1 Đợt 3: miễn phí

| Mã | Các bước | Tham số | Làn / tài nguyên | Quá giờ | Điều kiện trước | Đối soát (`kiem_dau_ra`) | Tự chạy lại |
|---|---|---|---|---|---|---|---|
| `radar_ban_tin` | (1) chỉ khi `chay_bu=true` **và** `scan_runs` của hôm nay không `ok`: script `python quet_dot_bien_7ngay.py --workers 6`, cwd `E:\quet-kenh-anti` (miễn phí, `aff-radar.md:30`), quá giờ 30 phút. (2) script `python radar_xuat.py --ngay <YYYY-MM-DD hoặc rỗng> --ra <data>\radar\<id>.json` (mở DB **chỉ đọc**, `aff-radar.md:22`). (3) Claude `aff-radar`, **`--tools Read,Write,Glob`** (không Bash), cwd `E:\quet-kenh-anti`, `--add-dir <data>\radar` | `top_n` 5–30 (mặc định 10), `chay_bu` bool | nhe / – | 45 phút | không | `E:\quet-kenh-anti\de-xuat\<scan_date>-de-xuat-san-pham.md`, với **`scan_date` lấy từ JSON xuất** (ngày dữ liệu, không phải ngày chạy), có mtime ≥ `bat_dau_luc` | có |
| `phan_tich_uid` | Claude `aff-san-pham`, cwd `E:\phantichcanhquay` | `uid` | nhe / `kho` | 90 phút | chẩn đoán kho (§4.4) | Đọc `data/<UID>/info.json` (P2-4): `rui_ro` có **và** `data/<UID>/douyin.md` có → `xong`. `da_phan_tich` + `rui_ro` có nhưng thiếu `douyin.md` → `xong` + `co_lo_ngai` + gợi ý nút `douyin_uid`. Còn lại → `chua` | có (Bước 0 tự dừng nếu đã phân tích, `aff-san-pham.md:26`) |
| `douyin_uid` (mới, P2-3) | (1) runner ghi `sp_<UID>/douyin/_prompt_antigravity.txt` từ mẫu cố định `phieu.lap_prompt_douyin(uid, thu_muc, file_mau)`: Việc 1 + Việc 2 + báo cáo, như `phantichcanhquay\SKILL.md:153-156`; `file_mau` = `data/<uid khác>/douyin.md` đầu tiên tồn tại. (2) script `agy.exe --dangerously-skip-permissions --add-dir E:/phantichcanhquay --add-dir C:/Users/Mi/.gemini/config/skills/timvideodouyin -p <nội dung prompt> --output-format text --print-timeout 0` (đúng `SKILL.md:145-150`), stdout ghi `_antigravity_log.txt` **và** log job; **console hiện** (`hien_cua_so=True`) để Chrome hay cửa sổ giải captcha hiện được. Khi chạy, cứ 15 s đọc log: khớp `(?i)captcha|验证|滑块|đăng nhập|login` → đặt `can_ban` "Douyin đòi captcha/đăng nhập — giải trong cửa sổ trên máy nếu đang ngồi máy" (không chặn). (3) agy thoát: có `douyin/canh_quay_an_tien.md` mtime ≥ `bat_dau_luc` → script `python E:/phantichcanhquay/kho-san-pham/tools/kho.py ghi <UID> --tu E:/phantichcanhquay/sp_<UID>`; không có → `can_tra_loi/viec_tay` "Douyin bị captcha hoặc cần đăng nhập. Mở Chrome profile Douyin trên máy, giải xong bấm Đã làm xong để chạy lại tìm video" (trả lời → `cho`, chạy lại từ bước 1) | `uid` | nhe / `kho` | 40 phút | thư mục `E:/phantichcanhquay/sp_<UID>` tồn tại; chẩn đoán kho | `data/<UID>/douyin.md` mtime ≥ `bat_dau_luc` → `xong` | có |
| `xu_ly_link_moi` | script `python tools/kho.py cho`, cwd repo | không | nhe / `kho` | 5 phút | chẩn đoán kho | Dòng `^(\d{19})\t` (`tools/kho.py:419`) → tạo job con `phan_tich_uid` (tối đa 5, trùng thì bỏ qua); id `tam-…` báo "link rút gọn chưa phân giải". Exit 0 → `xong` | có |
| `poster_day_folder` | script 2 bước: `E:/tool/tiktok_poster_v2/.venv/Scripts/python.exe C:/Users/Mi/.claude/skills/tao-video-tu-canh-quay/scripts/day_len_poster.py --project <P> --link https://shop.tiktok.com/vn/pdp/<UID> --captions <P>/kich-ban/poster_captions.txt --xem`, rồi cùng lệnh bỏ `--xem` | `uid`, `du_an` | nhe / `poster` | 15 phút | cổng 8023 sống; có file captions | Bước xem: exit 0, không `[LỖI]`. Bước thật: exit 0 + có `soát lại:` + không `[LỖI]`; có `[CẢNH BÁO]` → `xong` + `co_lo_ngai` (`aff-poster.md:57-59`) | có (`aff-poster.md:41`) |
| `voice_pv` | script `python C:/Users/Mi/.claude/skills/tao-video-tu-canh-quay/scripts/tao_voice_pv.py --project <P> --batch <me>` | `uid`, `du_an`, `me` | gpu / – | 4 giờ | cổng 7890 sống; không ffmpeg ngoài | Xem P2-7 bên dưới | có |

**`voice_pv` đối soát (P2-7):**
- Danh sách mã lấy bằng `python …/trang_thai.py --project <P> --batch <me> ma`.
- Mỗi mã cần `P/voice/<me>_<ma>_adam.mp3` đạt **ffprobe** `format=duration > 0` (lệnh `ffprobe -v error -show_entries format=duration -of csv=p=0`).
- File có mtime ≥ `bat_dau_luc` của job bị ngắt mà ffprobe lỗi hoặc thời lượng 0 → **đổi tên** thành `<tên>.hong-<job_id>` (giữ lại, hoàn tác được). Nhờ vậy lần chạy lại script sẽ sinh lại bản đó; script vốn không ghi đè bản đã có.
- Đủ hết → `xong`; thiếu → `chua`.
- **Huỷ không dừng GPU của PerfectVoice:** app server vẫn hoàn tất request đang xử lý, vài phút. Web ghi rõ điều này cạnh nút Huỷ.
- Script không có bước Whisper của `aff-voice`; web ghi "chưa kiểm Whisper".

**Ánh xạ captcha (P2-3)** cho `phan_tich_uid`: agent trả `DONE_WITH_CONCERNS` mà báo cáo khớp `(?i)captcha|đăng nhập douyin|验证` → job `xong` + `co_lo_ngai` (phần bộ cảnh quay đã xong), **kèm nút "Chạy Douyin"** tạo `douyin_uid`. Không ánh xạ sang `can_tra_loi` + resume, vì Job Object đã giết agy khi `-p` thoát, và chạy lại `phan_tich_uid` sẽ bị Bước 0 chặn.

Mẻ giọng creator (`day_poster.py`) **không** có trong đợt 3.

### 5.2 Đợt 4: tốn tiền hoặc rủi ro (luôn cần duyệt có chữ ký)

| Mã | Ai chạy | Tham số | Làn / tài nguyên | Duyệt / hạn mức (trần code) | Đối soát |
|---|---|---|---|---|---|
| `muse_clip` | Claude `aff-muse`, `--tools Read,Write,Edit,Glob,Grep,Bash`, cwd `<P>` | `uid`, `du_an`, `mau` (1–10 mã trong `MAU_PROMPT_MUSE` cố định), `thoi_luong` ∈ {10,15}, `ti_le` ∈ {`9:16`} | nhe / – | luôn `cho_duyet`; ≤10 clip/việc, ≤15 clip/ngày | `khong_ro` |
| `voice_genmax` | script 2 pha: `tao_voice.py --project <P> --batch <me>` (ước tính, KHÔNG gọi API) → `cho_duyet` → cùng lệnh **thêm `--dong-y`** | `uid`, `du_an`, `me` | gpu / – | ≤25 bản/việc, ≤2 việc/ngày; không đường nào sinh `--gui-lai-ma` | `khong_ro` |
| `poster_len_lich` | Claude `aff-poster`, `--tools Read,Write,Edit,Glob,Grep,Bash` | `folder_id` (từ `GET /poster/folders`), `so_video_ngay` 1–100 | nhe / `poster` | luôn `cho_duyet`; ≤2 việc/ngày; ≤100 video/ngày mỗi việc; **tổng `so_video_ngay` ≤100 video mỗi tài khoản mỗi ngày** (D9/A-D9b; tạm gom tài khoản theo `folder_id`, `han_muc.khoa_tai_khoan_poster`); duyệt chỉ áp cho đúng job | `khong_ro` |

**Cổng chạy pha tốn tiền** (`BoChay._cong_ton_tien`, `tools/runner/vong_lap.py:1055`). Chạy đúng thứ tự, ngay trước MỖI lần sinh tiến trình của pha tốn tiền, gồm: lượt đầu sau duyệt, lượt sau khi xin duyệt lại rồi duyệt lại, và từng bước kế của cùng một lần chạy (`_con_khop_duyet`, `:1074`, giữ kiểm như hiện có, không tiêu lại):
1. Bản cài lệch `TONG_KIEM` (`BoChay.chan_ton_tien`) → hoãn, đứng `cho`, ghi chú "bản cài runner lệch tổng kiểm — cài lại runner" (R-11 P2-1).
2. Chữ ký duyệt trên dữ liệu đang lưu (`chu_ky.kiem_duyet`), sai → `loi` (giữ như hiện có, `:1039-1053`).
3. `kiem_han_muc(…, luc='nhan', viec_id=id)`.
4. **Tiêu lời duyệt** (D9, §8.3): `so_duyet.tieu_duyet(...)`.
   - `"da_tieu"` → `kho.ghi_tieu(id)`, rồi chạy.
   - `"da_dung"` → `loi` "lời duyệt đã dùng — bấm Xin duyệt lại".
   - `"chua_ro"` → hoãn, đứng `cho` với lý do, thử lại sau `cho_lai_han_muc_s`.

Pha không tốn tiền (`voice_genmax` `buoc='uoc_tinh'`) bỏ qua cổng (giữ `can_kiem_duyet`, `:488`).

**Không có "Chạy tiếp" và "Tiếp tục" cho loại tốn tiền** (D9):
- `co_the_chay_tiep` (`tools/runner/api.py:224`) trả False cho loại tốn tiền.
- Câu hỏi `khong_ro` của việc tốn tiền không có nút "Tiếp tục".
- Runner không tự "Tiếp tục" việc tốn tiền.
- Thay vào đó là `POST /xin-duyet-lai` (§4.3, §8.1).
- Việc tốn tiền ở `can_tra_loi` **không được trả lời trực tiếp** (A-D9b). Web chỉ hiện câu hỏi (để đọc) và các nút "Xin duyệt lại" / "Huỷ"; `POST /tra-loi` của loại tốn tiền → 409.
- Lần chạy sau khi duyệt lại dùng `--resume` (nếu `phien_da_tao=1`). Stdin là `lap_tin_chay_tiep(viec, ly_do)` nối thêm `lap_tin_duyet(viec)`, với `ly_do`:
  - xin duyệt lại từ `loi` → `loi` cũ;
  - xin duyệt lại từ `can_tra_loi` → "Người dùng không trả lời câu hỏi trước (<noi_dung câu hỏi, cắt 500 ký tự>) mà duyệt lại để làm tiếp. Không hỏi lại câu đó; chỗ nào cần quyết định thì chọn phương án an toàn nhất (không tốn thêm tiền), không làm được thì dừng và báo".
- `voice_genmax` xin duyệt lại khi chưa có ước tính → `cho` + `buoc='uoc_tinh'` (pha miễn phí, không qua cổng, không tiêu), xong pha này mới sang `cho_duyet` như lần đầu.

Việc miễn phí mà agent trả `NEEDS_APPROVAL` → `loi` "Agent xin làm việc ngoài danh mục: <trích> — làm tay trên máy". Không có nút Duyệt.

### 5.3 Đợt 5: `taovideo`

| Mã | Ai chạy | Tham số | Làn / tài nguyên | Duyệt / hạn mức | Đối soát |
|---|---|---|---|---|---|
| `taovideo` | Claude `--agent aff-taovideo`, `--tools Read,Write,Edit,Glob,Grep,Bash,Skill,Agent,SendMessage,TodoWrite` (P2-9), cwd dự án A, `--add-dir` dự án B, `F:\auto video oneshot`, `C:\Users\Mi\.claude\skills` | `uid`, `du_an_a`, `du_an_b` (mã hoặc `"tu_tim"`), `wm` (chỉ giá trị trong `WM_CHO_PHEP` hằng số code), `gia` int 1.000–10.000.000 hoặc null | gpu / `kho` | `cho_duyet`; ≤1/ngày; ≤ `CODEX_LUOT_VIEC` (mặc định 6) lần gọi subagent `codex:*` mỗi job: runner đếm `tool_use` tên `Agent` có `subagent_type` bắt đầu bằng `codex`, vượt thì giết cây → `can_tra_loi/khong_ro` "Đã chạm trần lượt Codex" | `khong_ro` → `loi` + "Chạy tiếp" |

---

## 6. Gọi Claude headless an toàn

### 6.1 Lệnh (subprocess dạng list, KHÔNG qua cmd.exe)

```python
argv = [CLAUDE_EXE, "-p",
        "--agent", loai.agent,
        "--tools", ",".join(loai.bo_cong_cu),          # GIỚI HẠN CỨNG bộ công cụ có mặt (P2-5)
        "--permission-mode", "dontAsk",                # quyền: công cụ ngoài --allowedTools bị từ chối, không treo
        "--allowedTools", *loai.bo_cong_cu,
        "--disallowedTools", *CONG_CU_CAM_CHUNG, *loai.cong_cu_cam,
        "--output-format", "stream-json", "--verbose",
        "--max-budget-usd", str(loai.tran_usd_moi_luot),
        *(["--resume", viec.session_id] if viec.phien_da_tao else ["--session-id", viec.session_id]),
        *sum((["--add-dir", d] for d in loai.them_thu_muc(tham_so)), [])]
# phiếu / tin tiếp → STDIN UTF-8, rồi đóng stdin.
```

- `CLAUDE_EXE` = `C:\Users\Mi\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe` (ghi đè bằng `KHO_CLAUDE_EXE`). Gọi thẳng, không qua `claude.cmd`.
- **Console ẩn dùng chung** (P3): `creationflags = CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP`, `startupinfo.dwFlags = STARTF_USESHOWWINDOW`, `wShowWindow = SW_HIDE`. Con cháu (python, ffmpeg, agy) dùng chung console ẩn này, nên không nháy cửa sổ. **Không** dùng `CREATE_NO_WINDOW`: tiến trình không console sẽ khiến con cháu console tự cấp console mới và hiện cửa sổ. Riêng `douyin_uid` dùng `SW_SHOWMINNOACTIVE`. Spike S-01 kiểm có nháy cửa sổ không.
- `CONG_CU_CAM_CHUNG = ["AskUserQuestion", "Bash(git push*)", "Bash(*wrangler*)", "Bash(*deploy_cloudflare*)", "Bash(*gui_telegram*)", "Bash(pip *)", "Bash(*--gui-lai-ma*)", "Bash(*kho-runner*)", "Edit(//C:/Users/Mi/AppData/Local/kho-runner/**)", "Write(//C:/Users/Mi/AppData/Local/kho-runner/**)", "Read(//C:/Users/Mi/AppData/Local/kho-runner/**)"]`.
  - **Nói thẳng:** `--disallowedTools` với mẫu `Bash(...)` chỉ khớp chuỗi lệnh. Đó **không phải chốt chặn** (lách được bằng `bash -c`, biến, đường dẫn tương đối). Nó chỉ chặn nhầm lẫn.
  - Chốt thật nằm ở: `--tools` (công cụ không có mặt thì không dùng được), D3, D5, D7, quá giờ, trần lượt, log.
  - Spike S-01 kiểm mẫu có `*` ở đầu có hoạt động không.
- **`dontAsk` so với `settings.json` `defaultMode = bypassPermissions`:** cờ dòng lệnh phải ghi đè setting. S-01 **bắt buộc** kiểm. Nếu không ghi đè được → chạy Claude với `--settings <file JSON tối thiểu do runner sinh trong data dir>` đặt `permissions.defaultMode = "dontAsk"`; vẫn không được → báo trưởng phòng, chưa mở việc Claude.
- `--tools` theo loại:
  - `radar_ban_tin`: `Read,Write,Glob`;
  - `phan_tich_uid`: `Read,Write,Edit,Glob,Grep,Bash,Skill`;
  - `muse_clip`, `poster_len_lich`: `Read,Write,Edit,Glob,Grep,Bash`;
  - `taovideo`: như §5.3.
- `session_id = uuid4()` sinh khi tạo job. `phien_da_tao` đổi thành 1 khi thấy sự kiện đầu (`type=system`, `subtype=init`) mang `session_id` đó. Chưa thấy thì lần sau vẫn dùng `--session-id` cùng UUID.

### 6.2 Đọc sự kiện (cô lập, P2-5)

Mọi chỗ đọc tên trường của stream-json nằm trong `tools/runner/stream_json.py`, có test fixture. A-1 viết theo giả định dưới đây; A-2 chỉnh sau khi có kết quả spike S-01.

```python
def doc_su_kien(dong: str) -> dict | None                  # json.loads an toàn; None nếu không phải JSON
def la_khoi_tao(sk: dict) -> str | None                    # session_id nếu là sự kiện init
def la_ket_qua(sk: dict) -> dict | None                    # {session_id, chi_phi_usd, so_luot, loi: bool, van_ban, bi_tu_choi: list}
def dem_luot(sk: dict) -> int                              # 1 nếu là message assistant mới, ngược lại 0
def ten_cong_cu(sk: dict) -> list[tuple[str, dict]]        # các tool_use (tên, input) trong sự kiện
def dich_dong(sk: dict) -> str | None                      # dòng log người đọc
```

Giả định (S-01 xác nhận):
- `type=="system" and subtype=="init"` → `session_id`;
- `type=="assistant"` → `message.content[]` gồm `text` / `tool_use{name,input}`;
- `type=="result"` → `session_id`, `total_cost_usd`, `num_turns`, `is_error`, `result`, `permission_denials`.

### 6.3 Quota và chi phí (P2-6)

Bốn chốt, độc lập nhau:
1. **USD/ngày**: tổng `chi_phi_usd` hôm nay ≥ `claude_usd_ngay` → job Claude đứng `cho`. Có thể không đúng khi đi qua `ANTHROPIC_BASE_URL` proxy (S-01 đo `total_cost_usd > 0`).
2. **Số job Claude/ngày** (dự phòng): đếm job có `so_lan_claude > 0` và `bat_dau_luc` hôm nay ≥ `claude_viec_ngay` (mặc định 12) → đứng `cho`.
3. **Trần lượt mỗi job**: runner cộng `dem_luot` theo thời gian thực. Vượt `tran_luot` của loại thì giết cây → `can_tra_loi/khong_ro` "Đã chạm trần N lượt". Trần: radar 40, phan_tich 250, muse 120, poster_len_lich 60, taovideo 1500/lượt chạy. Đây cũng là thay thế cho `--max-turns` mà CLI không có.
4. `--max-budget-usd` mỗi lượt (nếu có hiệu lực): radar 3, phan_tich 8, muse 3, poster 2, taovideo 40.

Khác:
- **Hết quota hoặc quá tải**: `loi=True` hoặc văn bản khớp `(?i)usage limit|rate limit|\b429\b|overloaded` → `loi`; tạm dừng mọi việc Claude 30 phút (`tam_dung_claude_den`).
- `permission_denials`/`bi_tu_choi` khác rỗng → ghi vào kết quả để chỉnh allowlist.
- Quá giờ → giết cây, `loi`; nếu `phien_da_tao=1` thì có nút "Chạy tiếp".

### 6.4 Mẫu phiếu (stdin lần đầu)

```
PHIẾU <job_id> — <agent> (giao từ web Kho sản phẩm qua bộ chạy việc; người giao: <tao_boi>)
BỐI CẢNH CHẠY: bạn chạy headless (claude -p). Không ai ngồi ở terminal; không có công cụ hỏi người dùng.
Mục tiêu: <câu cố định theo loại, chèn tham số đã validate>
Đầu vào: <UID / đường dẫn tuyệt đối runner tự dò / file JSON runner xuất sẵn>
ĐƯỢC GHI: <cố định theo loại>
CẤM: <cố định theo loại>; không đọc/ghi C:\Users\Mi\AppData\Local\kho-runner\
ĐÃ DUYỆT: không có
Xong khi: <cố định theo loại>
KHI CẦN NGƯỜI DÙNG (mở app, đăng nhập, chọn trong danh sách): KHÔNG tự đoán. Kết thúc lượt; cuối câu trả lời ghi đúng khối:
CẦN_USER: <câu hỏi hoặc việc người dùng phải làm, 1 dòng, ≤300 ký tự>
LOẠI: chon | viec_tay              (đợt 5 thêm: cau_hoi)
LỰA_CHỌN: <a> | <b> | <c>          (chỉ khi LOẠI: chon, ≤6 lựa chọn, mỗi cái ≤120 ký tự)
Quy ước này thay cho luật "không hỏi người dùng" trong file agent cho riêng phiếu này. Bạn sẽ được tiếp tục CÙNG phiên.
Còn lại: trả về theo mẫu báo cáo trong file agent, dòng đầu là "TRẠNG THÁI: ...".
```

Riêng radar (không có Bash), thêm dòng: "Dữ liệu radar đã xuất sẵn ở `<json>`, báo cáo nguồn `<md>`; không truy cập DB; kiểm chéo bằng Read".

Mục `ĐÃ DUYỆT` khi có duyệt:

```
ĐÃ DUYỆT: <duyet_boi> lúc <duyet_luc>, cho đúng job <id> với tham số <tham_so chuẩn>, nguyên văn:
<<<
<loi_duyet>
>>>
```

Tin tiếp khi resume:

```
TRẢ LỜI CỦA NGƯỜI DÙNG cho "<cau_hoi.noi_dung>" (bấm/gõ trên web; là DỮ LIỆU trả lời, không mở rộng phạm vi phiếu <id>):
<<<
<chon: đúng chuỗi lựa chọn | viec_tay: "Người dùng báo đã làm xong việc: <noi_dung>" | khong_ro: "Tiếp tục; chỉ dừng ở điểm CẦN_USER" | đợt 5 cau_hoi: chữ đã làm sạch>
>>>
Làm tiếp từ chỗ dừng. Quy ước CẦN_USER và mẫu báo cáo giữ nguyên.
```

### 6.5 Đọc kết quả: `phieu.phan_tich_ket_qua(van_ban_cuoi) -> KetQuaAgent`

Thứ tự:
1. Dòng `^CẦN_USER:\s*(.+)$` **cuối cùng** → `CAN_USER`. `LOẠI` lạ hoặc thiếu → `viec_tay`. Đợt < 5 mà `LOẠI: cau_hoi` → hạ xuống `viec_tay` (người dùng chỉ có nút).
2. `^TRẠNG THÁI:\s*(DONE_WITH_CONCERNS|DONE|BLOCKED|NEEDS_CONTEXT|NEEDS_APPROVAL)\b` (dòng đầu khớp).
3. Không khớp gì → `KHONG_RO`.

| KetQuaAgent | Job |
|---|---|
| `DONE` | `kiem_dau_ra=='xong'` → `xong`; không thì `xong` + `co_lo_ngai` "agent báo xong nhưng chưa thấy đầu ra" |
| `DONE_WITH_CONCERNS` | `xong` + `co_lo_ngai`. `phan_tich_uid` có chữ captcha → thêm nút `douyin_uid` (§5.1) |
| `CAN_USER` | `can_tra_loi` |
| `BLOCKED`, `NEEDS_CONTEXT` | `can_tra_loi/viec_tay`, `noi_dung` = 1500 ký tự đầu của báo cáo |
| `NEEDS_APPROVAL` | loại `ton_tien` → `cho_duyet` (duyệt có chữ ký → resume với `ĐÃ DUYỆT`); loại miễn phí → `loi` |
| `KHONG_RO` | `can_tra_loi/khong_ro` (nút "Tiếp tục" / "Huỷ") |
| exit ≠ 0 mà không có kết quả, hoặc `loi=True` | `loi` |

---

## 7. Đợt 5: hỏi-đáp `aff-taovideo` trên web

### 7.1 Theo lượt + resume (giữ lựa chọn D4)

| | Theo lượt (CHỌN) | stream-json hai chiều |
|---|---|---|
| Trả lời sau vài giờ | Không tốn gì | Tiến trình treo hàng giờ |
| Reboot khi đang chờ | Resume được (phiên trên đĩa) | Mất phiên |
| Phát hiện "đang hỏi" | Rõ ràng: lượt kết thúc + khối `CẦN_USER` | Phải đoán |
| Rủi ro | `-p` thoát khi việc nền (subagent / Bash nền) còn chạy; Job Object giết việc nền; thông báo hoàn tất việc nền bị mất (P2-9) → spike S-02 đo | Phức tạp |

### 7.2 Luồng

1. Tạo `taovideo` → `cho_duyet` (ước tính "~21 voice GenMax + render 2 mẻ GPU ~N giờ").
2. Người dùng gõ lời duyệt + mật khẩu; Worker ký → `cho` → làn gpu nhận (giữ `kho`) → lượt 1.
3. Gặp điểm hỏi (`aff-taovideo.md:32`; `tao-video-tu-canh-quay\SKILL.md:67`) → khối `CẦN_USER` → `can_tra_loi`.
   - `chon` (vd chốt thư mục Bước B) và `viec_tay` (mở Poster): trả lời bằng nút.
   - `cau_hoi`: chữ tự do + mật khẩu (§9).
4. Trả lời → `cho` → `--resume`.
5. `TRẠNG THÁI: DONE…` → `kiem_dau_ra`: `kho.py xem <UID>` có 2 dòng Poster (`aff-taovideo.md:36`).
6. `KHONG_RO`: tự "Tiếp tục" tối đa 1 lần mỗi job, chỉ khi không còn tiến trình con của job. Lần hai thì hỏi người dùng.
7. Nếu S-02 cho thấy `-p` thoát trước khi việc nền xong: K-1 bắt buộc dòng "không kết thúc lượt khi còn việc nền; chờ bằng vòng kiểm ≤9 phút/lệnh" (như `aff-san-pham.md:33`). Nếu điều đó vẫn không đủ, đợt 5 dừng ở mức "chạy tay trên máy, theo dõi trên web" và tôi báo lại người dùng.

### 7.3 Đề xuất cập nhật agent (phiếu K-1, culiapp-skill; chỉ đề xuất)

- Sửa mâu thuẫn luật **"Không hỏi người dùng"** (`aff-radar.md`, `aff-san-pham.md`, `aff-poster.md`, `aff-muse.md`, `aff-voice.md`, luật 2) với quy ước `CẦN_USER`: thêm câu "Ngoại lệ: phiếu có mục KHI CẦN NGƯỜI DÙNG thì dùng khối CẦN_USER như phiếu quy định, thay cho BLOCKED". Phiếu §6.4 đã tự ghi ngoại lệ này, nên đợt 3 chạy được kể cả trước K-1.
- `aff-taovideo.md`: thêm mục "Chạy từ bộ chạy việc web":
  1. khối `CẦN_USER/LOẠI/LỰA_CHỌN`;
  2. chốt Bước B dùng `LOẠI: chon`;
  3. không kết thúc lượt khi còn việc nền;
  4. được resume với "Phiên trước bị ngắt" → `trang_thai.py tiep` trước khi làm tiếp;
  5. dùng Codex không quá trần phiếu ghi.
- `aff-san-pham.md` Bước 7: khi phiếu ghi "Douyin do runner chạy riêng" thì bỏ qua Bước 7 và ghi `CHƯA làm: Bước 7 (runner chạy douyin_uid)`. Việc này tránh agy bị Job Object giết. Thay đổi đi kèm ở `danh_muc`: phiếu `phan_tich_uid` ghi dòng đó, và runner tự tạo `douyin_uid` khi `phan_tich_uid` xong. Trước K-1, giữ nguyên ánh xạ captcha ở §5.1.

---

## 8. API

### 8.1 API runner (127.0.0.1:8788)

Mọi route đòi `x-runner-key`. Mọi **POST** còn đòi chữ ký request §8.3.

| Method + path | Body / query | Trả |
|---|---|---|
| `GET /suc-khoe` | – | `{luc, phien_ban, lan:{gpu,nhe}, tai_nguyen:{kho,poster}, dem:{…}, chi_phi_hom_nay_usd, viec_claude_hom_nay, han_muc, tam_dung_claude_den, dot_bat}` |
| `GET /danh-muc` | – | `{loai:[{ma, ten, dot, ton_tien, lan_chay, tham_so:[…]}]}` (chỉ `dot ≤ dot_bat`) |
| `GET /du-an/<uid>` | – | `{du_an:[{ma, ten, goc, me:[…], co_captions}]}` |
| `GET /poster/folders` | – | đợt 4; trước đó 404 |
| `POST /viec` | `{loai, tham_so, boi}` | 201 `{viec}` · 409 `{trung}` · 400 · 429 (≤30 job/ngày/người) |
| `GET /viec` | `?trang_thai=&uid=&gioi_han=&tom_tat=1` | `{viec:[…]}` hoặc `{dem}` |
| `GET /viec/<id>` | – | `{viec, tra_loi:[…], xem_truoc, tham_so_chuan}` (`tham_so_chuan` để Worker ký duyệt) |
| `GET /viec/<id>/log` | `?tu=` | `{tu, den, noi_dung, het}` |
| `POST /viec/<id>/tra-loi` | `{tra_loi, boi}` | Chỉ khi `can_tra_loi`. `chon`: đúng một lựa chọn; `viec_tay`: `"da_lam_xong"`; `khong_ro`: `"tiep_tuc"`; `cau_hoi`: chỉ đợt 5, 1–1000 ký tự |
| `POST /viec/<id>/duyet` | `{loi_duyet, duyet_luc, boi, chu_ky_duyet}` | Chỉ khi `cho_duyet`; kiểm chữ ký duyệt + hạn mức |
| `POST /viec/<id>/tu-choi` · `/huy` | `{boi}` | `{viec}` |
| `POST /viec/<id>/chay-tiep` | `{boi}` | `loi→cho` theo §4.3; 409 nếu không đủ điều kiện hoặc là loại tốn tiền (D9) |
| `POST /viec/<id>/xin-duyet-lai` (D9) | `{boi}` | Chỉ loại tốn tiền ở `loi` hoặc `can_tra_loi`, tiến trình cũ không còn sống: xoá `loi_duyet, duyet_boi, duyet_luc, chu_ky_duyet` → `cho_duyet`. Riêng `voice_genmax` chưa có `uoc_tinh` → `cho` + `buoc='uoc_tinh'`. 409 nếu sai điều kiện hoặc trùng việc đang mở |
| `POST /viec/<id>/chay-lai` | `{boi}` | 201 job mới |

`viec` trả ra có các trường của §4.2, trừ `pid`, `pid_tao_luc`, `session_id`, `chu_ky_duyet`; thêm `co_session`, `co_the_chay_tiep` và `co_the_xin_duyet_lai` (bool). `/suc-khoe` thêm `chan_ton_tien` (bool, D9).

### 8.2 API Worker (chỉ `nhan`/`comeofage`)

| Web gọi | Chuyển tới | Body Worker dựng lại |
|---|---|---|
| `GET /api/viec?…` | `/r/viec?…` | – |
| `POST /api/viec` | `/r/viec` | `{loai, tham_so, boi}` (`loai` `^[a-z_]{3,30}$`; `tham_so` object phẳng ≤10 khoá; giá trị string ≤40 / số / bool / mảng ≤10 string ≤20) |
| `GET /api/viec/danh-muc`, `/api/viec/suc-khoe`, `/api/viec/poster-folders` | `/r/danh-muc`, `/r/suc-khoe`, `/r/poster/folders` | – |
| `GET /api/viec/du-an/<uid>` | `/r/du-an/<uid>` | – |
| `GET /api/viec/<id>`, `/api/viec/<id>/log?tu=` | tương ứng | – |
| `POST /api/viec/<id>/tra-loi` | tương ứng | Đợt 3: `{tra_loi}` chỉ nhận chuỗi ≤120 ký tự (giá trị nút). Đợt 5: chữ tự do chỉ khi có `mat_khau` đúng (§9) |
| `POST /api/viec/<id>/duyet` (đợt 4) | Web gửi `{loi_duyet, mat_khau, sha_tham_so}`. Worker kiểm `mat_khau` (đếm sai bằng KV, §9) → GET `/r/viec/<id>` lấy `tham_so_chuan` + `loai` → `sha256_hex(tham_so_chuan) ≠ sha_tham_so` → 409 "Tham số việc đã đổi sau khi bạn mở trang — tải lại rồi duyệt" (D9, R-11 P2-2) → ký duyệt (§8.3) → POST | `{loi_duyet, duyet_luc, boi, chu_ky_duyet}` |
| `POST /api/viec/<id>/(tu-choi\|huy\|chay-tiep\|chay-lai\|xin-duyet-lai)` | tương ứng | `{boi}` |
| `POST /api/runner/tieu-duyet` (D9) | **không chuyển tiếp**; runner gọi thẳng Worker | §8.3 "Tiêu lời duyệt" |

`sha_tham_so` do web tính bằng `crypto.subtle.digest("SHA-256", UTF-8(tham_so_chuan))` trên đúng `tham_so_chuan` của response `GET /api/viec/<id>` dùng để vẽ khung duyệt (hex thường, 64 ký tự).

Lỗi: mạng → 502; hết giờ → 504; 401/403 → 502 "khoá/chữ ký lệch"; 4xx khác trả nguyên. Hàm chung `goiMayNha(env, path, {method, body, timeoutMs})`. W-1 không refactor route `/api/video` cũ.

### 8.3 Chữ ký Worker (D7)

- **Khoá.** `tools/runner/tao_khoa_ky.py` (một lần, trưởng phòng chạy) sinh cặp Ed25519 bằng `cryptography`:
  - in khoá riêng dạng **PKCS8 DER base64** ra stdout, không ghi đĩa;
  - ghi khoá công khai PEM vào `tools/runner/ky_cong_khai.pem` (khoá công khai, commit được);
  - lệnh: `python tools/runner/tao_khoa_ky.py --ghi-cong-khai tools/runner/ky_cong_khai.pem | npx wrangler secret put KY_RIENG`.

  Worker import bằng `crypto.subtle.importKey("pkcs8", der, {name:"Ed25519"}, false, ["sign"])`. Runner đọc khoá công khai từ **bản cài** `app\ky_cong_khai.pem`.
- **Ký request ghi** (mọi POST tới runner). Header:
  - `x-ky-ngay: <unix ms>`;
  - `x-ky-nonce: <32 hex ngẫu nhiên>`;
  - `x-ky: <base64url chữ ký>` trên chuỗi
    `"kho-runner-v1\n" + METHOD + "\n" + path_khong_tien_to_r + "\n" + ngay + "\n" + nonce + "\n" + sha256_hex(body_bytes)`.

  Runner kiểm theo thứ tự: `|bây giờ − ngay| ≤ 120 s`; nonce chưa có trong bảng `nonce` (chèn vào trong cùng transaction); chữ ký đúng. Sai → 401. Vì vậy `boi` trong body chỉ được tin khi chữ ký đúng.
- **Ký lời duyệt** (lưu bền, kiểm lại lúc nhận việc). `chu_ky_duyet` = chữ ký trên
  `"kho-duyet-v1\n" + id + "\n" + loai + "\n" + sha256_hex(tham_so_chuan) + "\n" + sha256_hex(loi_duyet) + "\n" + duyet_luc + "\n" + boi`.

  Runner kiểm khi nhận `/duyet` (so với `tham_so` đang lưu) và **mỗi lần nhận việc** cho loại `ton_tien`. Chữ ký duyệt chặn được việc sửa **nội dung** (tham số, lời duyệt, người duyệt, thời điểm), nhưng **không** chặn được việc chạy lại: sửa `runner.db` để đưa một việc đã duyệt về `cho` thì chữ ký vẫn khớp (review R-11 P1-1). Chặn chạy lại do sổ tiêu một lần dưới đây đảm nhận (D9).
- **Tiêu lời duyệt (D9).** Một lời duyệt chỉ cho chạy pha tốn tiền đúng một lần. Sổ nằm trên Cloudflare KV `SO_DUYET`, chỉ Worker ghi được.
  - **Route Worker** `POST /api/runner/tieu-duyet`:
    - đầu vào: header `x-runner-key` so khớp `env.RUNNER_KEY` bằng so sánh hằng thời gian. Không cần phiên, không kiểm Origin (runner không phải trình duyệt). Body JSON ≤ 1 KB, đúng 3 khoá `{id, chu_ky_duyet, nonce}`: `id` khớp `^j\d{14}[a-z0-9]{4}$`; `chu_ky_duyet` khớp `^[A-Za-z0-9_-]{86}$`; `nonce` khớp `^[0-9a-f]{32}$`;
    - sai khoá → 401; sai hình dạng → 400; thiếu `RUNNER_KEY`, `KY_RIENG` hoặc binding `SO_DUYET` → 503;
    - `k = "tieu:" + sha256_hex(chu_ky_duyet)` (sha256 trên byte UTF-8 của chuỗi base64url);
    - `await env.SO_DUYET.get(k)` khác null → 409 `{loi:"lời duyệt đã dùng", luc}`;
    - ngược lại `await env.SO_DUYET.put(k, JSON.stringify({id, luc: ISO, nonce}))`, **không đặt TTL**. Ghi xong mới ký, rồi trả 200 `{ky}`;
    - `ky` = base64url Ed25519(`KY_RIENG`) trên `"kho-tieu-v1\n" + id + "\n" + sha256_hex(chu_ky_duyet) + "\n" + nonce`;
    - `put` lỗi → 503 và không ký.
  - **Phía runner** (`tools/runner/so_duyet.py`, phiếu FX-10):
    - mỗi lần gọi sinh `nonce = secrets.token_hex(16)`;
    - `POST <WORKER_ORIGIN>/api/runner/tieu-duyet`, timeout 15 s, header `x-runner-key` lấy từ `.runner_key`;
    - 200 → kiểm `ky` bằng `chu_ky.kiem_tieu(kcc, id, chu_ky_duyet, nonce, ky)` (khoá công khai trong bản cài) → `"da_tieu"`;
    - 409 → `"da_dung"`;
    - mọi trường hợp khác (mạng, hết giờ, 5xx, 401, 400, JSON hỏng, chữ ký sai) → `"chua_ro"`: không chạy, việc đứng `cho`, cảnh báo trên `/suc-khoe`.

    Nonce do runner tự sinh và chỉ nằm trong bộ nhớ, nên chữ ký mà kẻ khác lấy được (với nonce của họ) không dùng được cho runner.
  - **Ai sửa `runner.db` để chạy lại một việc đã duyệt** (đổi `xong`/`loi` → `cho`, chép chữ ký sang việc khác cùng id, …) nhận 409 ở bước tiêu, nên không tốn tiền. Muốn chạy lại phải "Xin duyệt lại" rồi nhập mật khẩu. Duyệt mới có `duyet_luc` mới, nên chữ ký mới và khoá KV mới.
  - **Giới hạn của sổ:**
    - KV chỉ nhất quán cuối cùng (eventual consistency), và get-rồi-put không nguyên tử. Hai lần gọi sát nhau ở hai colo khác nhau có thể cùng nhận 200. Runner chạy một instance, gọi tuần tự, luôn từ cùng một máy (thường cùng colo, đọc thấy bản ghi vừa ghi).
    - Ai có `.runner_key` có thể tiêu trước một lời duyệt. Kết quả chỉ là việc bị chặn (DoS), không gây tốn tiền.
    - Runner đã tiêu thành công mà tiến trình chết trước khi gọi API ngoài: lời duyệt vẫn mất, phải xin duyệt lại. Lệch về phía an toàn.
    - `WORKER_ORIGIN` là hằng số trong `so_duyet.py`. Đổi sang máy chủ giả cũng không có tác dụng, vì máy chủ giả không ký được.
- **Chặn khi lệch tổng kiểm (D9, R-11 P2-1).** Lúc khởi động, `kiem_tong(THU_MUC_APP)` (`tools/runner/vong_lap.py:146`, gọi ở `tools/chay_runner.py:156`) trả danh sách không rỗng → `BoChay(..., chan_ton_tien=True)`. Khi đó cổng §5.2 bước 1 hoãn mọi việc tốn tiền, và `/suc-khoe` trả `chan_ton_tien: true`. Hết chặn bằng cách cài lại runner (`cai_runner.py` ghi `TONG_KIEM.json` mới) rồi khởi động lại. Thiếu `TONG_KIEM.json` (chạy từ mã nguồn) cũng bị chặn.
- **Vector test chéo:** B-1c sinh `tools/runner/vector_ky.json` từ khoá có seed cố định (chỉ dùng cho test). W-1b dùng vector đó kiểm chữ ký phía Worker khớp từng byte.
- **Giới hạn còn lại (nói thẳng):** agent có Bash chạy dưới user Mi vẫn có thể **sửa chính code hoặc khoá công khai trong bản cài** rồi chờ runner khởi động lại. D7 chặn được kiểu lạm dụng thực tế (gọi API localhost bằng khoá đọc trộm, sửa DB, sửa `cau_hinh.json`), nhưng không chặn được một agent cố ý viết lại runner. Chặn hẳn cần tách user Windows riêng cho runner (cần admin/UAC, đã loại ở D7). Giảm nhẹ:
  - `CONG_CU_CAM_CHUNG` có thư mục `kho-runner` (không phải chốt chặn);
  - lúc khởi động, runner so sha256 các file trong `app\` với `app\TONG_KIEM.json` do `cai_runner.py` ghi, lệch thì từ chối chạy việc tốn tiền (`chan_ton_tien`, D9) và hiện cảnh báo trên `/suc-khoe`. Agent sửa được cả file tổng kiểm, nên đây chỉ là phát hiện nhầm lẫn;
  - sổ tiêu D9 vẫn đứng vững khi chỉ `runner.db` bị sửa, nhưng code runner bị viết lại thì có thể bỏ qua bước tiêu. Giới hạn này giữ nguyên như đã ghi ở D7.

---

## 9. Bảo mật phía web (P1-2)

1. **Tự host thư viện**: `web/vendor/marked-12.0.2.min.js`, `web/vendor/purify-3.4.18.min.js`, `web/vendor/qrcode-generator-1.4.4.min.js`.
   - Lấy từ tarball npm đúng phiên bản (`npm pack marked@12.0.2 dompurify@3.4.18 qrcode-generator@1.4.4` trong thư mục tạm, chép đúng file `marked.min.js`, `dist/purify.min.js`, `qrcode.min.js`).
   - Ghi sha256 vào `web/vendor/NGUON.md`.
   - Tải mạng là **NEEDS_APPROVAL**, trưởng phòng chạy.
   - `web/index.html` trỏ sang `vendor/…`, bỏ jsdelivr.
2. **CSP** qua file `web/_headers` (Workers Static Assets đọc file này; tài sản tĩnh không đi qua Worker vì `run_worker_first = ["/api/*"]`):
   ```
   /*
     Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'
     X-Content-Type-Options: nosniff
     Referrer-Policy: same-origin
   ```
   `style-src 'unsafe-inline'` cần cho 6 thuộc tính `style="…"` có trong `web/app.js`; không có script inline (`web/index.html:8-11` đều là `src`). Kỹ sư phải kiểm bằng `wrangler dev` + `curl -sI http://127.0.0.1:8787/` thấy header. Nếu `_headers` không được áp dụng → phương án dự phòng: đổi `run_worker_first = true` và Worker gắn header cho `env.ASSETS.fetch` (sửa `cf/wrangler.toml` + `cf/src/worker.js:430`). Kỹ sư báo lại trước khi làm phương án này.
3. **Đợt 3 chỉ có nút**: API runner và Worker chỉ nhận `tra_loi` là giá trị nút (§8.1–8.2). Phiếu đợt 3 không cho agent dùng `LOẠI: cau_hoi`.
4. **Chữ tự do (đợt 4 lời duyệt, đợt 5 trả lời) bắt nhập lại mật khẩu mỗi lần gửi**: Worker kiểm `kiemMatKhau(mat_khau, dsUser(env)[phien.user].hash)` (`cf/src/worker.js:67-74`). Sai → 403 "Sai mật khẩu". Sai 5 lần trong 10 phút → khoá thao tác này 10 phút. Đếm theo user bằng **KV `SO_DUYET`**, khoá `sai:<user>` (D9, thay Cache API ở `cf/src/worker.js:441-465`):
   - giá trị `{"sai":[ms,...],"khoa_den":ms}`, `put` với `expirationTtl: 900`;
   - giữ lớp đếm trong bộ nhớ isolate (`demSaiBoNho`) làm lớp chặn song song trong cùng isolate;
   - KV đọc lỗi → coi như đang bị khoá (503 "Không kiểm được số lần sai — thử lại sau"), không kiểm mật khẩu. XSS không biết mật khẩu nên không duyệt được và không đưa được chữ vào agent.
5. Mọi chuỗi từ runner hoặc agent (câu hỏi, lựa chọn, log, kết quả) đều qua `esc()` trước khi chèn HTML. Bản tin radar render bằng marked + DOMPurify (như tab hiện có).

---

## 10. Hạn mức (D5, P1-3)

Trần là **hằng số trong `tools/runner/han_muc.py`**. `cau_hinh.json` (nếu có) chỉ được **hạ**: `hieu_luc = min(tran_code, gia_tri_file)`. Giá trị lớn hơn trần bị bỏ qua và ghi cảnh báo trên `/suc-khoe`.

```python
HAN_MUC_TRAN = {
  "dot_bat": 3,                       # đợt cao nhất được mở; tăng = sửa code + cài lại (có duyệt)
  "claude_usd_ngay": 40, "claude_viec_ngay": 12,
  "viec_tao_ngay_moi_nguoi": 30, "con_toi_da_xu_ly_link": 5,
  "muse_clip_moi_viec": 10, "muse_clip_ngay": 15,
  "genmax_ban_moi_viec": 25, "genmax_viec_ngay": 2,
  "poster_len_lich_ngay": 2, "poster_video_ngay_toi_da": 100,   # A-D9b: trần mỗi việc VÀ tổng mỗi tài khoản/ngày
  "taovideo_ngay": 1, "codex_luot_viec": 6,
}
TRAN_LUOT = {"radar_ban_tin": 40, "phan_tich_uid": 250, "muse_clip": 120, "poster_len_lich": 60, "taovideo": 1500}
WM_CHO_PHEP: tuple[str, ...] = ()     # đợt 5 điền theo người dùng
```

Kiểm ở 3 thời điểm: **tạo**, **duyệt** (cả duyệt lại), **nhận**. Từ D9, loại tốn tiền không còn `chay-tiep`; loại miễn phí vẫn kiểm hạn mức ở `chay-tiep`.

**Đếm hạn mức ngày theo số lần tiêu (D9).** Một việc tốn tiền có thể chạy nhiều lần (mỗi lần xin duyệt lại), nên hạn mức ngày đếm theo số lần đã tiêu lời duyệt, không theo số việc:
- Bảng `viec` thêm 2 cột (schema `'2'`, `ALTER TABLE … ADD COLUMN` khi mở DB phiên bản 1):
  - `so_lan_tieu INTEGER NOT NULL DEFAULT 0`;
  - `tieu_luc_dau TEXT`.

  `KhoViec.ghi_tieu(id)` tăng `so_lan_tieu` và đặt `tieu_luc_dau` nếu đang rỗng.
- `ngay_tinh_han_muc(viec)` (`tools/runner/han_muc.py:122`):
  - ngày = `tieu_luc_dau` → `duyet_luc` → `tao_luc` (lấy giá trị đầu tiên có);
  - được tính khi `so_lan_tieu > 0`, hoặc có `duyet_luc`, hoặc việc đang mở.
- `so_luong_ngay` (`:103`) nhân với `max(1, so_lan_tieu)` khi đếm việc khác.
- Việc đang xét, lúc `duyet` và `nhan`: cộng `so_luong_ngay × (so_lan_tieu + 1)`. Lúc `tao`: cộng `so_luong_ngay`.
- **Poster (D9, A-D9b).** `poster_video_ngay_toi_da` = 100, dùng cho hai kiểm:
  - **mỗi việc**: `so_video_ngay` 1–100;
  - **mỗi tài khoản mỗi ngày**: Σ `so_video_ngay` của các việc `poster_len_lich` cùng tài khoản được tính trong ngày (`video_poster_tai_khoan_ngay`, `tools/runner/han_muc.py:169`; cùng tập `ngay_tinh_han_muc`; mỗi việc tính một lần dù tiêu nhiều lần, vì chạy lại cùng lịch không tăng số video/ngày), cộng việc đang xét, ≤ 100.

  Khoá tài khoản là `khoa_tai_khoan_poster(tham_so)` (`:147`). Hàm này **tạm** trả `folder:<folder_id>`, vì danh sách folder Poster chưa có trường tài khoản. Khi có trường đó thì chỉ sửa hàm này. Khoá `None` (tham số hỏng) bị tính vào mọi tài khoản (thiên về chặt). `poster_len_lich_ngay` (2 việc/ngày, toàn bộ) vẫn giữ và đếm theo lần tiêu.

  Giới hạn: kiểm này chỉ tính các việc lên lịch trong cùng ngày. Lịch đặt từ hôm trước vẫn chạy trên Poster V2 mà runner không thấy.

---

## 11. Rủi ro, cách giảm, phần KHÔNG làm được

| # | Rủi ro | Cách giảm |
|---|---|---|
| R-A | `kho.py` pull/commit trong repo vừa là chỗ sửa code (nay ở `main`, code đợt 1–2 chưa commit) | D8: code runner chạy từ bản cài nên pull không đổi code đang chạy; mutex `kho`; chẩn đoán kho 4 nhánh (§4.4); autostash xung đột → `loi` nguyên văn |
| R-B | ~~`.video_key` không ignore~~ | Đã có trong `.gitignore`. Bỏ khỏi A-2 |
| R-C | `chay_video.bat` bật connector cloudflared thứ hai, ingress thiếu muse/troly | Không sửa trong kế hoạch này; báo người dùng |
| R-D | `-p` thoát khi việc nền còn chạy; mất thông báo hoàn tất | S-2; K-1; tự "Tiếp tục" 1 lần; đợt 5 có điểm dừng §7.2 bước 7 |
| R-E | Tên trường stream-json, `--max-budget-usd`, `dontAsk` so với `bypassPermissions`, mẫu cấm có `*` đầu | S-01; `stream_json.py` cô lập; 4 chốt chi phí §6.3 |
| R-F | Người dùng chạy tay cùng lúc | Kiểm ffmpeg ngoài; chẩn đoán `index.lock` + `git.exe`; web ghi "đừng chạy tay cùng SP" |
| R-G | Máy ngủ hoặc tắt | Đối soát §4.6; khuyên power plan "không ngủ khi cắm điện" |
| R-H | Không ai đăng nhập Windows sau reboot | Trang 🩺 hiện runner tắt |
| R-I | Prompt injection từ dữ liệu web/TikTok | Radar không có Bash (P2-11); `--tools` theo loại; chữ tự do cần mật khẩu; NEEDS_APPROVAL ở việc miễn phí bị chặn |
| R-J | Lộ bí mật trong log | Che theo giá trị + mẫu; env tối thiểu (§4.7) |
| R-K | XSS điều khiển máy nhà | Tự host + CSP; đợt 3 chỉ nút; chữ tự do cần mật khẩu; ghi cần chữ ký Worker (§8.3, §9) |
| R-L | Agent cùng user tự duyệt hoặc nới hạn mức | D7 chữ ký + kiểm lại lúc nhận; trần trong code; còn lại: agent cố ý sửa code bản cài (§8.3) |
| R-Q | Sửa `runner.db` để chạy lại việc tốn tiền đã duyệt (R-11 P1-1) | D9: sổ tiêu một lần trên KV `SO_DUYET`, runner tiêu ngay trước mỗi lần chạy; còn lại: KV nhất quán cuối cùng, DoS bằng `.runner_key` (§8.3) |
| R-M | Instance thứ hai giết job của instance đang chạy | Mutex + lock ở dòng đầu `main()` (§4.1); test trong A-2 |
| R-N | Huỷ `voice_pv` để lại mp3 hỏng; PerfectVoice vẫn dùng GPU vài phút | Đối soát ffprobe + đổi tên `.hong-<id>`; web ghi rõ |
| R-O | Workers Static Assets không áp `_headers` | Kiểm bằng `wrangler dev`; dự phòng `run_worker_first=true` (§9) |
| R-P | SQLite khoá ghi | WAL + busy_timeout + kết nối riêng + CAS |

**Không làm được từ web**, hiển thị là hộp "👉 Việc của bạn" (`can_tra_loi/viec_tay`, nút "Tôi đã làm xong") hoặc thông báo không chặn `can_ban`:

| Việc | Hiển thị |
|---|---|
| Captcha / đăng nhập Douyin | Đang chạy `douyin_uid`: `can_ban` "Douyin đòi captcha — nếu đang ngồi máy, giải trong cửa sổ Chrome". agy thoát mà chưa có file: `viec_tay` "Mở Chrome profile Douyin trên máy, giải captcha/đăng nhập, rồi bấm Đã làm xong để chạy lại tìm video". Từ `phan_tich_uid` bị captcha: `xong` (có lo ngại) + nút "Chạy Douyin" |
| Đăng nhập lại Muse | `viec_tay` theo `aff-muse.md:29` |
| Mở Poster V2 / PerfectVoice / Video Batch Local | `viec_tay` "Mở <app>" (lệnh mở lấy từ `GOI_Y_APP`, `web/app.js:388`) |
| Gắn account folder Poster | `viec_tay` |
| Khoá git cũ / nhánh / dữ liệu kho bẩn | `viec_tay` theo §4.4 |
| Quay raw/takes | gợi ý ở bước 3, không có nút |
| UAC, cài package, sửa skill, cài bản runner mới | không đưa lên web |

---

## 12. Màn hình web

- **Đầu trang** (`renderUser`, `web/app.js:77-87`): thêm `⚙ Việc` cạnh 🩺; huy hiệu = `can_tra_loi + cho_duyet`.
- **`#/viec`**:
  - dải tóm tắt: runner, làn, tài nguyên `kho`, chi phí và số việc Claude hôm nay so với hạn mức, tạm dừng;
  - nút "📡 Bản tin radar", "📥 Xử lý link mới";
  - nhóm Cần bạn / Đang chạy / Đang chờ / Gần đây;
  - tự làm mới 5 s khi tab hiện.
- **`#/viec/<id>`**:
  - thông tin, sự kiện, `can_ban` (dải vàng, không chặn);
  - **khung trả lời bằng nút**: `chon` (mỗi lựa chọn một nút), `viec_tay` ("Tôi đã làm xong" / "Huỷ"), `khong_ro` ("Tiếp tục" / "Huỷ"); đợt 5 thêm `cau_hoi` (textarea + ô mật khẩu);
  - khung duyệt (đợt 4): ước tính + lời duyệt + mật khẩu;
  - log (offset, 3 s khi đang chạy);
  - kết quả (radar render markdown);
  - nút Huỷ / Chạy tiếp (khi `co_the_chay_tiep`) / Chạy lại.
- **Chi tiết SP**: `<div id="viec-sp">` dưới `#buoc8`, gọi `veViecSp(i, ds, phien)` sau `veBuoc()`. Nút "▶ Chạy" theo `goiYViec(ht, info, dotBat)`:

| Bước hiện tại | Gợi ý |
|---|---|
| 2 Bộ cảnh quay | `phan_tich_uid`; nếu `da_phan_tich` mà chưa có tab Douyin → thêm `douyin_uid` |
| 3 Quay | không nút; "👉 Việc của bạn: quay raw/takes" |
| 4 B-roll AI | `muse_clip` (đợt 4) |
| 5 Voice | `voice_pv`; `voice_genmax` (đợt 4) |
| 6 Dựng 2 mẻ | `taovideo` (đợt 5) |
| 7 Kiểm duyệt | không nút; trỏ tab ✅ Duyệt |
| 8 Đăng | `poster_day_folder`; `poster_len_lich` (đợt 4) |
| 0 Hoàn tất | không |

  Ngoài bảng: SP đã qua bước 2 mà `douyin` rỗng thì luôn có nút phụ `douyin_uid`.
- Không đổi `tinhBuoc`/`buocHienTai`.

---

## 13. Kế hoạch phiếu

Gốc: `E:\phantichcanhquay\kho-san-pham`. Lệnh chạy trong Git Bash từ `cd /e/phantichcanhquay/kho-san-pham`. Test Python đặt ở `tools/test_runner_*.py` (pytest chế độ prepend thêm `tools/` vào `sys.path`).

Ràng buộc chung:
- Chỉ stdlib + `psutil` + `cryptography` (đều đã cài).
- Test không chạm `%LOCALAPPDATA%\kho-runner` thật (đặt `KHO_RUNNER_DIR` sang `tmp_path`).
- Test không gọi `claude.exe` hay `agy.exe` thật (dùng chương trình giả `python -c` / script giả).

### Đợt 3, lượt 1 (song song, không trùng file)

**B-1 · culiapp-backend · Lõi: kiểu, kho việc, danh mục đợt 3, dò dự án, phiếu, hạn mức**
- ĐƯỢC SỬA: `tools/runner/__init__.py`, `tools/runner/kieu.py`, `tools/runner/kho_viec.py`, `tools/runner/danh_muc.py`, `tools/runner/du_an.py`, `tools/runner/phieu.py`, `tools/runner/han_muc.py`, `tools/test_runner_kho_viec.py`, `tools/test_runner_danh_muc.py`, `tools/test_runner_phieu.py`, `tools/test_runner_han_muc.py`
- Phụ thuộc: không.
- Interface (đúng chữ ký):

```python
# kieu.py
TRANG_THAI = ("cho","dang_chay","can_tra_loi","cho_duyet","xong","loi","huy")
DANG_MO = ("cho","dang_chay","can_tra_loi","cho_duyet")
class ThamSoLoi(ValueError): ...
class TrungViec(Exception):
    def __init__(self, viec: dict): self.viec = viec
class SaiTrangThai(Exception): ...
class VuotHanMuc(Exception): ...
@dataclass(frozen=True)
class BuocChay:
    ten: str; argv: list[str]; cwd: str; stdin: str | None; env_them: dict[str, str]
    la_claude: bool; het_gio_s: int; hien_cua_so: bool = False; file_log_phu: str | None = None
@dataclass(frozen=True)
class CanNguoiDung:
    loai: str                     # 'viec_tay' | 'chon' | 'khong_ro' | 'cau_hoi'
    noi_dung: str
    lua_chon: tuple[str, ...] = ()
@dataclass(frozen=True)
class KetQuaAgent:
    trang_thai: str               # DONE|DONE_WITH_CONCERNS|BLOCKED|NEEDS_CONTEXT|NEEDS_APPROVAL|CAN_USER|KHONG_RO
    cau_hoi: CanNguoiDung | None
    tom_tat: str
@dataclass
class MoiTruong:
    gocs: list[Path]; repo_kho: Path; thu_muc_scripts: Path; python_poster: Path; claude_exe: Path
    agy_exe: Path; thu_muc_radar: Path; thu_muc_sp: Path; thu_muc_du_lieu: Path
    cong_song: Callable[[int], bool]
    chan_doan_kho: Callable[[Path], CanNguoiDung | str | None]   # None = sạch; 'ban' = đợi; CanNguoiDung = việc tay
    ffmpeg_ngoai: Callable[[], bool]
    thoi_luong_media: Callable[[Path], float | None]             # ffprobe
    bay_gio: Callable[[], datetime]
    doc_folder_poster: Callable[[], list[dict]] = lambda: []

# kho_viec.py
class KhoViec:
    def __init__(self, duong_dan_db: Path, bay_gio: Callable[[], datetime]): ...
    def tao(self, loai: str, khoa: str, tham_so: dict, lan_chay: str, trang_thai_dau: str, boi: str, *,
            buoc: str = "chay", uoc_tinh: str | None = None, cau_hoi: CanNguoiDung | None = None,
            session_id: str | None = None, cha_id: str | None = None, chay_lai_tu: str | None = None) -> dict
    def lay(self, id: str) -> dict | None
    def ds(self, trang_thai: Sequence[str] | None = None, khoa: str | None = None, gioi_han: int = 50) -> list[dict]
    def chuyen(self, id: str, tu: Sequence[str], den: str, boi: str, ghi_chu: str = "", **truong) -> dict
    def nhan_viec_ke(self, lan_chay: str, tai_nguyen_ban: set[str], tai_nguyen_cua: Callable[[str], frozenset[str]]) -> dict | None
    def ghi_tien_trinh(self, id: str, pid: int | None, pid_tao_luc: float | None) -> None
    def danh_dau_phien(self, id: str) -> None                                   # phien_da_tao = 1
    def cong_chi_phi(self, id: str, usd: float, so_luot: int, them_lan: bool) -> None
    def them_tra_loi(self, id: str, boi: str, cau_hoi: str, noi_dung: str) -> None
    def dung_nonce(self, nonce: str, luc: float) -> bool                       # False nếu đã dùng
    def su_kien(self, id: str) -> list[dict]
    def tra_loi_cua(self, id: str) -> list[dict]
    def dem(self) -> dict[str, int]
    def chi_phi_ngay(self, ngay: date) -> float
    def dem_trong_ngay(self, loai: str | None, ngay: date, boi: str | None = None, chi_claude: bool = False) -> int
    def don_cu(self, truoc: datetime) -> None                                   # nonce cũ

# du_an.py
GOCS_MAC_DINH: list[str]                      # sao y tools/video_server.py:24
def gocs_tu_moi_truong() -> list[Path]        # KHO_VIDEO_GOC hoặc mặc định
def ma_du_an(p: Path) -> str
def ds_du_an(uid: str, gocs: list[Path]) -> list[dict]
def tim_du_an(ma: str, uid: str, gocs: list[Path]) -> Path | None
def ds_me(p: Path) -> list[str]

# han_muc.py
HAN_MUC_TRAN: dict[str, int | float]; TRAN_LUOT: dict[str, int]; WM_CHO_PHEP: tuple[str, ...]
def han_muc_hieu_luc(cau_hinh_file: dict) -> tuple[dict, list[str]]          # (giá trị, cảnh báo khoá bị bỏ vì vượt trần)
def kiem_han_muc(kho: KhoViec, ma_loai: str, tham_so: dict, hm: dict, luc: str, boi: str) -> None   # raise VuotHanMuc; luc ∈ tao|duyet|nhan

# danh_muc.py
@dataclass(frozen=True)
class LoaiViec:
    ma: str; ten: str; dot: int; lan_chay: str; ton_tien: bool; agent: str | None
    tu_chay_lai: bool; het_gio_s: int; tai_nguyen: frozenset[str]
    tham_so: tuple[dict, ...]
    kiem_tham_so: Callable[[dict, MoiTruong], dict]
    tinh_khoa: Callable[[dict], str]
    trang_thai_dau: Callable[[dict], tuple[str, str]]
    dieu_kien_truoc: Callable[[dict, MoiTruong], CanNguoiDung | str | None]  # 'ban' = đợi
    lap_buoc: Callable[[dict, dict, MoiTruong], list[BuocChay]]
    kiem_dau_ra: Callable[[dict, dict, MoiTruong], str]
    bo_cong_cu: tuple[str, ...] = (); cong_cu_cam: tuple[str, ...] = (); tran_usd_moi_luot: float = 0
DANH_MUC: dict[str, LoaiViec]     # đợt 3: radar_ban_tin, phan_tich_uid, douyin_uid, xu_ly_link_moi, poster_day_folder, voice_pv
CONG_CU_CAM_CHUNG: tuple[str, ...]
def lay_loai(ma: str, dot_bat: int) -> LoaiViec
def tham_so_chuan(tham_so: dict) -> str
def lenh_claude(loai: LoaiViec, viec: dict, mt: MoiTruong) -> list[str]         # §6.1, dựa vào viec['phien_da_tao']
def quyet_dinh_sau_khoi_dong(viec: dict, ket_qua_kiem: str, loai: LoaiViec) -> tuple[str, str]
def con_tu_xu_ly_link(stdout: str, gioi_han: int) -> tuple[list[str], list[str]]
def mp3_hong(p: Path, me: str, bat_dau: datetime, mt: MoiTruong) -> list[Path]  # P2-7

# phieu.py
def lap_phieu(loai: LoaiViec, viec: dict, mt: MoiTruong, dot_bat: int) -> str
def lap_tin_tiep(viec: dict, cau_hoi: CanNguoiDung, tra_loi: str) -> str
def lap_tin_duyet(viec: dict) -> str
def lap_tin_chay_tiep(viec: dict, ly_do: str) -> str
def lap_prompt_douyin(uid: str, thu_muc: Path, file_mau: Path) -> str
def lam_sach_chu(s: str, toi_da: int) -> str
def phan_tich_ket_qua(van_ban_cuoi: str, dot_bat: int) -> KetQuaAgent
def anh_xa_ket_qua(loai: LoaiViec, kq: KetQuaAgent, dau_ra: str) -> tuple[str, dict]
```

- Lệnh kiểm chứng: `python -B -m pytest tools/test_runner_kho_viec.py tools/test_runner_danh_muc.py tools/test_runner_phieu.py tools/test_runner_han_muc.py -q`
- Xong khi (mỗi mục ≥1 test):
  - trùng → `TrungViec`; CAS sai → `SaiTrangThai`;
  - `nhan_viec_ke` FIFO, bỏ qua job có tài nguyên bận, 2 thread không lấy trùng;
  - mọi tham số sai bị từ chối;
  - argv `lap_buoc` khớp §5.1 từng phần tử (radar 3 bước có hoặc không có chạy bù; douyin 3 bước, bước agy `hien_cua_so=True`);
  - `kiem_dau_ra` của `phan_tich_uid` đủ 3 nhánh P2-4 trên cây `data/` giả;
  - `voice_pv` đánh dấu mp3 hỏng chỉ khi mtime ≥ bắt đầu và thời lượng ≤ 0 hoặc None;
  - `phan_tich_ket_qua` với 9 mẫu (thêm: `cau_hoi` ở đợt 3 hạ xuống `viec_tay`);
  - `quyet_dinh_sau_khoi_dong` đủ 6 ô;
  - `han_muc_hieu_luc` không cho nới quá trần;
  - `kiem_han_muc` chặn `claude_viec_ngay`;
  - `GOCS_MAC_DINH` bằng đúng danh sách tách từ `tools/video_server.py:24` (test đọc file nguồn bằng regex, không import);
  - `lenh_claude` có `--tools`, có `--resume` chỉ khi `phien_da_tao=1`.

**B-1b · culiapp-backend · Xuất dữ liệu radar**
- ĐƯỢC SỬA: `tools/runner/radar_xuat.py`, `tools/test_runner_radar_xuat.py`
- Phụ thuộc: không.
- Interface: `def xuat(db: Path, ngay: str | None, ra: Path) -> dict` trả `{scan_date, status, channels_ok, channels_total, alerts_shop, so_dong, bao_cao_md}`. CLI `--db` (mặc định `E:/quet-kenh-anti/tiktok_7ngay.db`), `--ngay`, `--ra`.
  - Mở DB `file:…?mode=ro`.
  - Chọn `scan_date` = `--ngay` hoặc lượt `ok` mới nhất.
  - Ghi `scan_runs` của ngày đó + `breakout_alerts` có `has_shop=1` (các cột ở `aff-radar.md:17`) ra JSON UTF-8.
  - `bao_cao_md` = `E:\quet-kenh-anti\data_dot_bien_7ngay\Bao-Cao-Dot-Bien-7-Ngay-<scan_date>.md` nếu tồn tại.
- Lệnh kiểm chứng: `python -B -m pytest tools/test_runner_radar_xuat.py -q`
- Xong khi: test với DB SQLite giả trong `tmp_path` (đúng tên bảng và cột) qua; mở DB thật bị cấm trong test.

**B-1c · culiapp-backend · Chữ ký (D7)**
- ĐƯỢC SỬA: `tools/runner/chu_ky.py`, `tools/runner/tao_khoa_ky.py`, `tools/runner/vector_ky.json`, `tools/test_runner_chu_ky.py`
- Phụ thuộc: không.
- Interface:

```python
def chuoi_ky_request(method: str, path: str, ngay_ms: int, nonce: str, body: bytes) -> bytes
def chuoi_ky_duyet(id: str, loai: str, tham_so_chuan: str, loi_duyet: str, duyet_luc: str, boi: str) -> bytes
def nap_khoa_cong_khai(pem: bytes) -> Ed25519PublicKey
def kiem_request(kcc, headers: Mapping[str, str], method: str, path: str, body: bytes, bay_gio_ms: int,
                 dung_nonce: Callable[[str, float], bool]) -> str | None          # None = hợp lệ, ngược lại lý do
def kiem_duyet(kcc, viec: dict) -> bool                                            # dùng các trường đang lưu
```

  `tao_khoa_ky.py --ghi-cong-khai <pem>` in PKCS8 DER base64 ra stdout. `vector_ky.json` gồm: seed test cố định (32 byte hex, chỉ dùng cho test), khoá công khai, 2 request mẫu và 1 lời duyệt mẫu (có tiếng Việt) kèm chữ ký đúng.
- Lệnh kiểm chứng: `python -B -m pytest tools/test_runner_chu_ky.py -q`
- Xong khi: đúng → None; sai chữ ký / lệch 121 s / nonce lặp / body đổi 1 byte → lý do; `kiem_duyet` sai khi `tham_so` hoặc `loi_duyet` trong viec bị sửa; vector tái tạo được.

**A-1 · culiapp-automation · Thực thi tiến trình + đọc stream-json**
- ĐƯỢC SỬA: `tools/runner/thuc_thi.py`, `tools/runner/stream_json.py`, `tools/test_runner_thuc_thi.py`, `tools/test_runner_stream_json.py`
- Phụ thuộc: không.
- Interface:

```python
# stream_json.py — đúng các hàm ở §6.2
# thuc_thi.py
@dataclass
class KetQuaTienTrinh:
    ma_thoat: int | None; het_gio: bool; bi_huy: bool; vuot_luot: bool
    ket_qua: dict | None          # stream_json.la_ket_qua(...)
    van_ban_cuoi: str; session_id: str | None; so_luot: int; cong_cu_da_goi: list[str]
def tu_gan_job_object() -> bool                       # gắn tiến trình hiện tại; KILL_ON_JOB_CLOSE
def gianh_don_instance(thu_muc: Path) -> object | None  # mutex Local\kho-runner + msvcrt.locking runner.lock; None nếu đã có instance
def env_toi_thieu(them: dict[str, str]) -> dict[str, str]  # §4.7
def chay_tien_trinh(argv: list[str], cwd: str, stdin_text: str | None, env: dict[str, str],
                    file_log: Path, file_jsonl: Path | None, het_gio_s: int, la_claude: bool, hien_cua_so: bool,
                    tran_luot: int | None, khi_bat_dau: Callable[[int, float], None],
                    khi_co_session: Callable[[str], None], khi_doc_dong: Callable[[str], None],
                    huy: threading.Event) -> KetQuaTienTrinh
def giet_cay(pid: int, tao_luc: float | None) -> bool
def ffmpeg_ngoai(pid_goc_cua_runner: set[int]) -> bool
def bo_che(nguon: "NguonBiMat") -> Callable[[str], str]   # §4.7: che theo giá trị (đọc lại theo mtime) + mẫu
@dataclass
class NguonBiMat:
    settings_json: Path; file_khoa: list[Path]; cau_hinh_radar: Path; ten_bien_moi_truong: list[str]
```

- Lệnh kiểm chứng: `python -B -m pytest tools/test_runner_thuc_thi.py tools/test_runner_stream_json.py -q`
- Xong khi:
  - fixture stream-json (init / assistant text / tool_use / result) cho đúng các trường giả định;
  - chương trình giả → `session_id`, `so_luot`;
  - `tran_luot=2` với 3 message → `vuot_luot` và tiến trình đã chết;
  - quá giờ → chết cả cây (cha + con `sleep`);
  - stdin tiếng Việt nguyên vẹn;
  - `env_toi_thieu` không chứa biến lạ đặt trong test (vd `ANTHROPIC_API_KEY=x`);
  - che bí mật theo giá trị đọc từ `settings.json` giả và mẫu `sk-…`;
  - `gianh_don_instance` lần 2 trong cùng thư mục trả None (gọi trong tiến trình con riêng);
  - sau `tu_gan_job_object`, tiến trình con được sinh ra chết khi tiến trình cha giả bị kill (test qua tiến trình trung gian).

**W-0 · culiapp-web · Tự host thư viện + CSP**
- ĐƯỢC SỬA: `web/vendor/*` (mới), `web/vendor/NGUON.md`, `web/_headers` (mới), `web/index.html`
- Phụ thuộc: không.
- Việc: §9 mục 1–2. Tải gói là NEEDS_APPROVAL. Lệnh chính xác: chạy `npm pack marked@12.0.2 dompurify@3.4.18 qrcode-generator@1.4.4` trong thư mục tạm do kỹ sư nêu, sau đó chép file.
- Lệnh kiểm chứng: `grep -c "cdn.jsdelivr" web/index.html` → `0`; `sha256sum web/vendor/*.js` khớp `NGUON.md`; `cd cf && npx wrangler dev --port 8790` rồi `curl -sI http://127.0.0.1:8790/ | grep -i content-security-policy` (bản dev cục bộ, không deploy).
- Xong khi: header CSP xuất hiện ở `wrangler dev`; mở trang dev trên trình duyệt không có lỗi CSP trong console (trưởng phòng hoặc reviewer kiểm tay); hoặc báo lại nếu `_headers` không áp dụng (§9).

**W-1 · culiapp-web · Worker `/api/viec*` + ký request**
- ĐƯỢC SỬA: `cf/src/worker.js`, `cf/test/worker.test.mjs`
- Phụ thuộc: không.
- Interface:
  - `goiMayNha(env, path, {method, body, timeoutMs})`;
  - `export function kiemThamSoViec(b)`;
  - `export async function kyRequest(env, method, path, bodyText) -> headers`;
  - `export function chuoiKyRequest(method, path, ngayMs, nonce, shaHex) -> Uint8Array` (cùng định dạng §8.3).
- Việc: §3.3, §8.2 (đợt 3: không có duyệt, `tra-loi` chỉ nhận chuỗi ≤120 ký tự); route `chay-tiep`, `poster-folders`; ký mọi POST.
- Lệnh kiểm chứng: `node --test cf/test/`
- Xong khi:
  - quyền 403; thiếu `RUNNER_KEY`/`KY_RIENG` → 503; POST thiếu Origin → 403;
  - header gửi đi có `x-key`, `x-runner-key`, `x-ky*`;
  - chữ ký kiểm được bằng khoá công khai sinh trong test (Web Crypto Ed25519 trong Node 24);
  - body dựng lại; mẫu sai → 400 và không gọi máy nhà;
  - 401 → 502; hết giờ → 504;
  - test cũ vẫn qua.

**W-3 · culiapp-web · video_server chuyển tiếp `/r/*`**
- ĐƯỢC SỬA: `tools/video_server.py`, `tools/test_video_server.py`
- Phụ thuộc: không.
- Việc: §3.2. Thêm `RUNNER_ORIGIN` (env `KHO_RUNNER_ORIGIN`, mặc định `http://127.0.0.1:8788`), `chuyen_tiep_runner(h, method) -> None`; thêm runner vào `APPS`.
- Lệnh kiểm chứng: `python -B -m pytest tools/test_video_server.py -q`
- Xong khi:
  - runner giả xác nhận: path ngoài regex 404; thiếu `x-key` 401; query lạ bị bỏ; body > 16 KB → 413;
  - chỉ các header cho phép được chuyển (gồm `x-ky*`, không có `x-key`);
  - runner tắt → 502; `chay-tiep` qua được;
  - test cũ vẫn qua.

**S-1 · culiapp-automation · Spike Claude headless (chuẩn bị, KHÔNG tự chạy)**
- ĐƯỢC SỬA: `tools/runner/spike_claude.py`
- Phụ thuộc: không.
- Việc: script tạo thư mục tạm, chạy `claude.exe` (đường dẫn §6.1) với agent nội tuyến `--agents '{"thu-runner":{…}}' --agent thu-runner`, env tối thiểu (§4.7), console ẩn (§6.1). Đo và in JSON ĐẠT/KHÔNG cho từng mục:
  1. sự kiện init và result cùng các trường §6.2;
  2. **`--permission-mode dontAsk` có ghi đè `defaultMode=bypassPermissions` trong settings không** (yêu cầu agent `Write` một file khi `--allowedTools Read` → phải bị từ chối, file không được tạo); nếu không → thử lại với `--settings` tối thiểu;
  3. `--tools Read,Glob` làm `Bash` biến mất;
  4. mẫu `--disallowedTools "Bash(*echo*)"` (có `*` đầu) có chặn `echo hi` không;
  5. `total_cost_usd > 0` khi đi qua `ANTHROPIC_BASE_URL` hiện tại;
  6. `--max-budget-usd 0.01` có dừng lượt không;
  7. khối `CẦN_USER` → `--resume` với stdin → lượt 2 nhớ ngữ cảnh lượt 1;
  8. đăng nhập chạy được với env tối thiểu;
  9. có nháy cửa sổ console khi agent gọi Bash `python -c "print(1)"` (ghi nhận bằng người quan sát; script in hướng dẫn);
  10. thời gian khởi động.
- Lệnh kiểm chứng: `python -m py_compile tools/runner/spike_claude.py && python tools/runner/spike_claude.py --help`
- Xong khi: trả `NEEDS_APPROVAL` với lệnh `python tools/runner/spike_claude.py --chay`, thư mục chạy là repo, tác động (quota ~0,2–0,8 USD; 3–4 phiên trong `C:\Users\Mi\.claude\projects\`; thư mục tạm), hoàn tác (xoá thư mục tạm). Trưởng phòng chạy, dán JSON kết quả cho A-2.

### Đợt 3, lượt 2 (sau lượt 1)

**B-2 · culiapp-backend · HTTP API runner**
- ĐƯỢC SỬA: `tools/runner/api.py`, `tools/test_runner_api.py`
- Phụ thuộc: B-1, B-1c.
- Interface: `def tao_handler(kho: KhoViec, mt: MoiTruong, khoa: str, khoa_cong_khai, hm: dict, canh_bao: list[str], bao_huy: Callable[[str], None], doc_log: Callable[[str, int], dict], trang_thai_lan: Callable[[], dict]) -> type[BaseHTTPRequestHandler]`
- Việc: §8.1 (trừ `/poster/folders` → 404, duyệt → 404 ở đợt 3); mọi POST kiểm `chu_ky.kiem_request`; `tra-loi` đợt 3 chỉ nhận giá trị nút; `chay-tiep` §4.3; hạn mức tạo.
- Lệnh kiểm chứng: `python -B -m pytest tools/test_runner_api.py -q`
- Xong khi:
  - mọi route trong §8.1 có test;
  - POST không chữ ký / sai chữ ký / nonce lặp → 401;
  - `boi` lấy từ body đã ký;
  - `tra-loi` chữ tự do ở đợt 3 → 400;
  - `chay-tiep` khi `phien_da_tao=0` → 409;
  - `/danh-muc` ẩn đợt > `dot_bat`.

**A-2 · culiapp-automation · Vòng chạy, điểm vào, cài đặt, tự bật**
- ĐƯỢC SỬA: `tools/runner/vong_lap.py`, `tools/chay_runner.py`, `tools/cai_runner.py`, `tools/test_runner_vong_lap.py`, `tools/test_runner_chay.py`, `tools/chay_video.bat`, `tools/runner/stream_json.py` (chỉnh theo kết quả S-1), `tools/test_runner_stream_json.py`
- Phụ thuộc: B-1, B-1b, B-1c, A-1, S-1 (đã chạy).
- Interface:

```python
class BoChay:
    def __init__(self, kho: KhoViec, mt: MoiTruong, hm: dict, thu_muc_log: Path, che: Callable[[str], str]): ...
    def khoi_dong(self) -> dict                 # §4.6 bước 1–3
    def bat_lan(self) -> None
    def chay_mot(self, viec: dict) -> None
    def bao_huy(self, id: str) -> None
    def doc_log(self, id: str, tu: int) -> dict
    def trang_thai_lan(self) -> dict
def tao_moi_truong() -> MoiTruong
def main(argv: list[str] | None = None) -> int  # tools/chay_runner.py: ĐÚNG thứ tự §4.1 (mutex trước mọi thứ)
# tools/cai_runner.py
def cai(nguon: Path, dich: Path) -> str          # trả PHIEN_BAN; dừng (SystemExit 4) nếu runner đang chạy
```

- Việc:
  - §4.1–4.7; §5.1 (radar 3 bước, douyin, poster 2 bước, voice đối soát + đổi tên `.hong-<id>`, xu_ly_link_moi sinh con);
  - §6.1–6.3 (resume theo `phien_da_tao`, trần lượt, 4 chốt chi phí, tạm dừng Claude);
  - `chay_video.bat`: thêm **trước** dòng cloudflared: `start "kho-runner" /min python "%LOCALAPPDATA%\kho-runner\app\chay_runner.py"` (giữ nguyên các dòng khác);
  - **Không** sửa `.gitignore` (đã có `tools/.video_key`).
- Lệnh kiểm chứng: `python -B -m pytest tools/test_runner_vong_lap.py tools/test_runner_chay.py tools/test_runner_stream_json.py -q && python -B tools/chay_runner.py --help && python -B tools/cai_runner.py --help`
- Xong khi:
  - **P1-1:** instance A đang chạy (tiến trình con, `KHO_RUNNER_DIR` tạm) có job `dang_chay` với PID sống; khởi động instance B → B thoát mã 3, PID của A vẫn sống, DB không đổi;
  - kịch bản Claude giả: xong; CAN_USER chon → trả lời → lượt 2 có `--resume` và stdin đúng; `phien_da_tao=0` → lượt 2 dùng `--session-id`;
  - quá giờ; vượt trần lượt → `can_tra_loi/khong_ro`;
  - khởi động lại → `cho` `lan_thu=2`;
  - điều kiện trước hỏng lúc nhận → `dang_chay→cho`;
  - mutex `kho`: 2 job `kho` ở 2 làn không chạy cùng lúc;
  - `voice_pv` đổi tên mp3 hỏng;
  - chạm `claude_viec_ngay` → đứng `cho`;
  - `cai()` từ chối khi mutex đang bị giữ, và ghi `TONG_KIEM.json`.

**W-1b · culiapp-web · Test chéo chữ ký**
- ĐƯỢC SỬA: `cf/test/chu-ky-cheo.test.mjs`
- Phụ thuộc: W-1, B-1c.
- Lệnh kiểm chứng: `node --test cf/test/`
- Xong khi: `chuoiKyRequest` của Worker với dữ liệu trong `tools/runner/vector_ky.json` cho đúng byte; chữ ký Worker tạo từ seed test khớp vector.

**W-2 · culiapp-web · Giao diện việc (đợt 3: chỉ nút)**
- ĐƯỢC SỬA: `web/viec.js` (mới), `web/app.js`, `web/index.html`, `web/style.css`, `cf/test/viec-web.test.mjs` (mới)
- Phụ thuộc: W-0 (index.html), W-1.
- Việc: §12. `app.js` chỉ thêm 3 móc (link + huy hiệu; route `#/viec`, `#/viec/<id>`; `#viec-sp` + `veViecSp`). Hàm thuần nằm giữa marker `// --- viec-thuan start/end ---`: `goiYViec(ht, info, dotBat)`, `nhomViec(ds)`, `nhanTrangThai(tt)`, `nutTraLoi(cauHoi, dotBat) -> [{nhan, gia_tri}]`. `index.html`: thêm `<script src="viec.js?v=1" defer>`, tăng `app.js?v=`.
- Lệnh kiểm chứng: `node --check web/viec.js && node --check web/app.js && node --test cf/test/`
- Xong khi:
  - test thuần qua (bảng `goiYViec`; `nutTraLoi` cho `cau_hoi` ở đợt 3 trả mảng rỗng; `nhomViec`);
  - mọi chuỗi qua `esc()`; nút khoá bấm đúp; polling dừng khi rời trang;
  - không có `<script>` inline và không có `on…=` (để CSP qua): `grep -nE "on[a-z]+=\"" web/viec.js` → 0.

### Đợt 3, lượt 3: tích hợp thật (trưởng phòng chạy, NEEDS_APPROVAL từng bước)

1. `python tools/runner/tao_khoa_ky.py --ghi-cong-khai tools/runner/ky_cong_khai.pem | (cd cf && npx wrangler secret put KY_RIENG)`
2. `python tools/cai_runner.py`, rồi chạy `python "%LOCALAPPDATA%\kho-runner\app\chay_runner.py"` một lần để sinh `.runner_key`, rồi tắt → `cd cf && npx wrangler secret put RUNNER_KEY`.
3. `cd cf && npx wrangler deploy` (W-0, W-1, W-2).
4. Khởi động lại video_server (W-3) và bật runner.
5. Điện thoại:
   - trang 🩺 thấy "Bộ chạy việc: Sống";
   - chạy `radar_ban_tin` (`chay_bu=false`);
   - xem log, bản tin, chi phí;
   - sau đó thử `poster_day_folder` cho một dự án có `output_poster/`.

Đợt 3 dùng được độc lập. Theo biên bản hội đồng, nên dùng 7 ngày trước khi mở đợt 4.

### Đợt 4

**B-3 · culiapp-backend** · ĐƯỢC SỬA: `tools/runner/danh_muc.py`, `tools/runner/han_muc.py`, `tools/runner/api.py`, `tools/test_runner_danh_muc.py`, `tools/test_runner_han_muc.py`, `tools/test_runner_api.py`
- Phụ thuộc: B-2.
- Việc:
  - 3 loại §5.2 + khung `taovideo` (`dot=5`); `MAU_PROMPT_MUSE: dict[str,str]` (6–8 mẫu cố định);
  - route `/viec/<id>/duyet` kiểm `chu_ky.kiem_duyet` + `kiem_han_muc(luc='duyet')`; `GET /poster/folders` gọi `mt.doc_folder_poster()`;
  - `/chay-tiep` cho loại tốn tiền kiểm chữ ký duyệt + hạn mức;
  - trần `dot_bat` trong code nâng lên 4 (chỉ khi người dùng đồng ý mở đợt 4).
- Lệnh kiểm chứng: `python -B -m pytest tools/test_runner_danh_muc.py tools/test_runner_han_muc.py tools/test_runner_api.py -q`
- Xong khi:
  - tạo → `cho_duyet` (genmax → `cho`/`uoc_tinh`);
  - duyệt có chữ ký sai → 401; sửa `tham_so` trong DB sau duyệt → nhận việc bị từ chối;
  - không đường nào sinh `--gui-lai-ma`;
  - vượt hạn mức ở 3 thời điểm bị chặn.

**A-3 · culiapp-automation** · ĐƯỢC SỬA: `tools/runner/vong_lap.py`, `tools/test_runner_vong_lap.py`, `tools/runner/poster_ds_folder.py` (mới)
- Phụ thuộc: B-3.
- Việc:
  - pha `uoc_tinh` → `cho_duyet`;
  - **gọi `kiem_han_muc(…, luc='nhan')` và `chu_ky.kiem_duyet` ngay trước khi chạy loại tốn tiền** (P2-10); sai → `loi` "chữ ký duyệt không hợp lệ" hoặc đứng `cho`;
  - `poster_ds_folder.py` (venv Poster, chỉ `ApiClient().list_folders()`, in JSON);
  - đếm subagent `codex*` cho trần Codex.
- Lệnh kiểm chứng: `python -B -m pytest tools/test_runner_vong_lap.py -q && python -m py_compile tools/runner/poster_ds_folder.py`
- Xong khi: test 2 pha; test DB bị sửa trạng thái → bị chặn lúc nhận; chạy thật `poster_ds_folder.py` → NEEDS_APPROVAL.

**W-4 · culiapp-web** · ĐƯỢC SỬA: `cf/src/worker.js`, `cf/test/worker.test.mjs`
- Phụ thuộc: W-1, B-3.
- Việc:
  - route `duyet`: GET `tham_so_chuan` → kiểm `mat_khau` (§9 mục 4, giới hạn sai 5 lần/10 phút) → ký duyệt → POST;
  - export `chuoiKyDuyet(...)`.
- Lệnh kiểm chứng: `node --test cf/test/`
- Xong khi: sai mật khẩu → 403 và không gọi máy nhà; lần sai thứ 6 → 429; chữ ký duyệt khớp `vector_ky.json`.

**W-5 · culiapp-web** · ĐƯỢC SỬA: `web/viec.js`, `web/style.css`, `cf/test/viec-web.test.mjs`
- Phụ thuộc: W-2, W-4.
- Việc: khung duyệt (ước tính, lời duyệt, ô mật khẩu `autocomplete="current-password"`), form `muse_clip` / `voice_genmax` / `poster_len_lich`; hàm thuần `duocDuyet(loi)`.
- Lệnh kiểm chứng: `node --check web/viec.js && node --test cf/test/`
- Xong khi: test thuần qua; mật khẩu không bao giờ lưu vào `localStorage`/`sessionStorage` (grep).

### Đợt 5

**S-2 · culiapp-automation** · ĐƯỢC SỬA: `tools/runner/spike_claude.py`
- Phụ thuộc: S-1.
- Việc: thêm `--kich-ban nen`: agent nội tuyến có `Agent`, `SendMessage`, `Bash`; gọi 1 subagent + 1 Bash nền `sleep 60`. Đo:
  - `-p` thoát trước hay sau việc nền;
  - việc nền có bị Job Object giết không;
  - thông báo hoàn tất có tới lượt sau (`--resume`) không;
  - `SendMessage` tới subagent cũ sau resume có chạy không.
- Xong khi: NEEDS_APPROVAL `python tools/runner/spike_claude.py --chay --kich-ban nen` (~0,5 USD).

**K-1 · culiapp-skill** · ĐƯỢC SỬA: `C:\Users\Mi\.claude\agents\aff-taovideo.md`, `aff-san-pham.md`, `aff-radar.md`, `aff-poster.md`, `aff-muse.md`, `aff-voice.md`
- Phụ thuộc: S-2.
- Việc: §7.3 (ngoại lệ luật "không hỏi người dùng"; mục chạy từ web cho taovideo; Bước 7 do runner chạy).
- Xong khi: diff chỉ thêm câu hoặc mục; người dùng duyệt.

**B-4 · culiapp-backend** · ĐƯỢC SỬA: `tools/runner/danh_muc.py`, `tools/runner/phieu.py`, `tools/runner/api.py`, `tools/runner/han_muc.py`, các test tương ứng
- Phụ thuộc: S-2, B-3.
- Việc:
  - `taovideo` hoàn chỉnh (§5.3);
  - `tra-loi` loại `cau_hoi` cho phép chữ tự do 1–1000 ký tự **chỉ khi request có cờ `da_xac_nhan_mat_khau: true` trong body đã ký**;
  - `WM_CHO_PHEP` theo người dùng; trần `dot_bat` = 5;
  - sau K-1: `phan_tich_uid` ghi "Douyin do runner chạy riêng" và tự tạo `douyin_uid`.
- Xong khi: test argv và phiếu khớp; `cau_hoi` không có cờ → 400.

**A-4 · culiapp-automation** · ĐƯỢC SỬA: `tools/runner/vong_lap.py`, `tools/test_runner_vong_lap.py`
- Phụ thuộc: B-4.
- Việc: quá giờ theo lượt; tự Tiếp tục 1 lần; trần Codex; resume sau bị ngắt.
- Xong khi: kịch bản giả 3 lượt qua.

**W-6 · culiapp-web** · ĐƯỢC SỬA: `cf/src/worker.js`, `cf/test/worker.test.mjs`, `web/viec.js`, `web/style.css`, `cf/test/viec-web.test.mjs`
- Phụ thuộc: W-5, B-4.
- Việc: `tra-loi` chữ tự do cần `mat_khau` (Worker kiểm, thêm `da_xac_nhan_mat_khau: true` vào body đã ký); form `taovideo`; câu hỏi `cau_hoi` có ô mật khẩu.
- Xong khi: test Worker (thiếu hoặc sai mật khẩu → 403) và test thuần qua.

### Sửa theo review R-11 (D9): FX-9..FX-12

Chạy sau đợt 4 (B-3, A-3, W-4, W-5 đã có code), trước khi mở đợt 4 cho người dùng. Thứ tự: FX-9 → (FX-10 ∥ FX-11 ∥ FX-12) → tích hợp.

**FX-9 · culiapp-backend · Chữ ký tiêu, schema 2, hạn mức theo lần tiêu, API xin duyệt lại**
- ĐƯỢC SỬA: `tools/runner/chu_ky.py`, `tools/runner/vector_ky.json`, `tools/runner/kho_viec.py`, `tools/runner/han_muc.py`, `tools/runner/api.py`, `tools/test_runner_chu_ky.py`, `tools/test_runner_kho_viec.py`, `tools/test_runner_han_muc.py`, `tools/test_runner_api.py`
- Phụ thuộc: không (B-3 đã xong).
- Hiện trạng lúc viết phiếu: `tools/test_runner_chu_ky.py:368-405`, `:556-558` đã gọi `chu_ky.kiem_tieu`, nhưng `chu_ky.py` chưa có hàm này. Kỹ sư giữ tên và chữ ký mà test đang dùng.
- Interface (đúng chữ ký):

```python
# chu_ky.py
def chuoi_ky_tieu(id: str, chu_ky_duyet: str, nonce: str) -> bytes
    # UTF-8 của "kho-tieu-v1\n" + id + "\n" + sha256_hex(chu_ky_duyet.encode()) + "\n" + nonce
def kiem_tieu(kcc: Ed25519PublicKey, id: str, chu_ky_duyet: str, nonce: str, ky: str) -> bool
    # ky: base64url không padding; sai định dạng → False, không ném

# kho_viec.py
SCHEMA = "2"   # mở DB '1' → ALTER TABLE viec ADD COLUMN so_lan_tieu INTEGER NOT NULL DEFAULT 0;
               #               ALTER TABLE viec ADD COLUMN tieu_luc_dau TEXT; meta schema='2' (một transaction)
class KhoViec:
    def ghi_tieu(self, id: str) -> dict                 # so_lan_tieu += 1; tieu_luc_dau = bay_gio nếu rỗng; trả việc mới
    def xin_duyet_lai(self, id: str, boi: str, ve_uoc_tinh: bool = False) -> dict
        # CAS (loi|can_tra_loi) → cho_duyet; ve_uoc_tinh=True → cho + buoc='uoc_tinh' (genmax chưa có uoc_tinh);
        # loi_duyet, duyet_boi, duyet_luc, chu_ky_duyet = NULL; giữ session_id, phien_da_tao, loi, cau_hoi;
        # raise SaiTrangThai / TrungViec

# han_muc.py — §10 "Đếm hạn mức ngày theo số lần tiêu" + poster theo tài khoản (đã có trong cây làm việc)
def so_luong_ngay(ma_loai: str, tham_so: object, so_lan_tieu: int = 0) -> int   # × max(1, so_lan_tieu)
def khoa_tai_khoan_poster(tham_so: object) -> str | None                        # đã có, han_muc.py:147
def video_poster_tai_khoan_ngay(kho: KhoViec, khoa_tk: str | None, ngay: date, tru_id: str | None = None) -> int  # đã có, :169

# api.py
def co_the_chay_tiep(v: dict) -> bool        # thêm: loại tốn tiền (tra DANH_MUC theo v['loai']) → False
def co_the_xin_duyet_lai(v: dict) -> bool    # loại tốn tiền, trang_thai ∈ {'loi','can_tra_loi'},
                                             # không tien_trinh_cu_con_song
```

- Việc:
  - route `POST /viec/<id>/xin-duyet-lai` (§8.1), thêm vào `_RE_ROUTE_HANH_DONG` (`tools/runner/api.py:67`) và `HANH_DONG` (`:480`);
  - `p_chay_tiep` (`:431`): loại tốn tiền → 409 "việc tốn tiền không chạy tiếp được — dùng Xin duyệt lại";
  - `p_tra_loi`: loại tốn tiền → 409 "việc tốn tiền: dùng Xin duyệt lại" (A-D9b);
  - `p_xin_duyet_lai`: `voice_genmax` có `uoc_tinh` rỗng → `xin_duyet_lai(..., ve_uoc_tinh=True)`, còn lại → `cho_duyet`;
  - `danh_muc.py` không nằm trong phiếu này: giới hạn `so_video_ngay` 1–100 đã có ở `tools/runner/danh_muc.py:63`;
  - `_ra` thêm `co_the_xin_duyet_lai`;
  - `/suc-khoe` thêm `chan_ton_tien = bool(trang_thai_lan().get("chan_ton_tien"))`;
  - `vector_ky.json` thêm mục `tieu` (id, chu_ky_duyet của lời duyệt mẫu, nonce cố định, `chuoi_hex`, `ky`) sinh từ seed test sẵn có.
- Lệnh kiểm chứng: `python -B -m pytest tools/test_runner_chu_ky.py tools/test_runner_kho_viec.py tools/test_runner_han_muc.py tools/test_runner_api.py -q`
- Xong khi (mỗi mục ≥1 test):
  - `kiem_tieu` đúng với vector; sai khi đổi 1 ký tự nonce, id hoặc chu_ky_duyet;
  - DB schema 1 mở ra lên 2, dữ liệu cũ giữ nguyên;
  - `ghi_tieu` hai lần → `so_lan_tieu=2`, `tieu_luc_dau` không đổi;
  - `xin_duyet_lai` xoá đúng 4 trường; việc trùng đang mở → `TrungViec`;
  - API: `chay-tiep` loại tốn tiền → 409; `xin-duyet-lai` loại miễn phí → 409; `tra-loi` loại tốn tiền → 409;
  - `xin-duyet-lai` từ `can_tra_loi` → `cho_duyet`;
  - genmax `loi` chưa có `uoc_tinh` → `cho` + `buoc='uoc_tinh'`; genmax có `uoc_tinh` → `cho_duyet`;
  - muse 10 clip đã tiêu 1 lần + duyệt lại 10 clip → vượt `muse_clip_ngay` 15;
  - poster cùng folder 60 + 50 video/ngày cùng ngày → việc thứ hai bị chặn ở `tao`, `duyet` và `nhan`; khác folder 60 + 50 → qua; một việc 101 → 400;
  - test cũ vẫn qua.

**FX-10 · culiapp-automation · Tiêu lời duyệt trước mỗi lần chạy, chặn khi lệch tổng kiểm**
- ĐƯỢC SỬA: `tools/runner/so_duyet.py` (mới), `tools/runner/vong_lap.py`, `tools/chay_runner.py`, `tools/test_runner_so_duyet.py` (mới), `tools/test_runner_vong_lap.py`, `tools/test_runner_chay.py`
- Phụ thuộc: FX-9.
- Đầu vào trưởng phòng ghi vào phiếu: giá trị `WORKER_ORIGIN` (origin https của Worker `kho-san-pham` đang phục vụ web Kho). Phiếu không có giá trị này → kỹ sư trả `BLOCKED`.
- Interface:

```python
# so_duyet.py
WORKER_ORIGIN: str                       # hằng số, giá trị theo phiếu
def tieu_duyet(origin: str, khoa_runner: str, kcc, id: str, chu_ky_duyet: str, *,
               goi_http: Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]] | None = None,
               sinh_nonce: Callable[[], str] = lambda: secrets.token_hex(16),
               timeout_s: float = 15.0) -> tuple[str, str]
    # → ("da_tieu" | "da_dung" | "chua_ro", mô tả ngắn không chứa khoá). goi_http mặc định: urllib POST JSON.

# vong_lap.py
class BoChay:
    def __init__(..., chan_ton_tien: bool = False,
                 tieu: Callable[[str, str], tuple[str, str]] | None = None): ...
    # tieu(id, chu_ky_duyet); None → mọi việc tốn tiền "chua_ro" (đứng cho, cảnh báo)
LOI_DA_DUNG = "lời duyệt đã dùng"
```

- Việc:
  - cổng §5.2 bước 1–4 trong `_cong_ton_tien` (`tools/runner/vong_lap.py:1055`). Bước tiêu chỉ chạy một lần mỗi lần chạy; các bước kế dùng `_con_khop_duyet` (`:1074`) như cũ, không tiêu lại;
  - `"da_tieu"` → `kho.ghi_tieu(id)` trước khi sinh tiến trình;
  - `ly_do_tiep_tuc` (`:328`) phân biệt duyệt lại sau trả lời và duyệt lại sau lỗi; stdin theo §5.2;
  - `trang_thai_lan()` (`:756`) thêm `"chan_ton_tien"`;
  - không bao giờ tự "Tiếp tục" loại tốn tiền;
  - lời báo khởi động lại theo §4.6;
  - `chay_runner.py` (`:153-160`): `chan_ton_tien = bool(kiem_tong(THU_MUC_APP))`; dựng `tieu` từ `so_duyet.tieu_duyet(WORKER_ORIGIN, <nội dung .runner_key>, <khoá công khai bản cài>, …)`.
- Lệnh kiểm chứng: `python -B -m pytest tools/test_runner_so_duyet.py tools/test_runner_vong_lap.py tools/test_runner_chay.py -q && python -B tools/chay_runner.py --help`
- Xong khi (mọi test dùng `goi_http`/`tieu` giả, **không gọi mạng thật**):
  - `tieu_duyet`: 200 + chữ ký đúng (khoá từ seed vector) → `da_tieu`; 200 + chữ ký trên nonce khác → `chua_ro`; 409 → `da_dung`; 401/500/timeout/JSON hỏng → `chua_ro`;
  - mỗi lần chạy gọi `tieu` đúng 1 lần, trước khi sinh tiến trình;
  - **kịch bản R-11:** việc đã chạy xong, sửa DB `xong→cho` → sổ giả trả `da_dung` → `loi` `LOI_DA_DUNG`, chương trình giả không được sinh;
  - `chua_ro` → `cho`, không sinh tiến trình;
  - `chan_ton_tien=True` → không gọi `tieu`, việc đứng `cho`; việc miễn phí vẫn chạy;
  - việc ở `can_tra_loi` → xin duyệt lại → duyệt lại → lượt 2 có `--resume`, stdin có lý do "không trả lời câu hỏi trước" (§5.2) và mục `ĐÃ DUYỆT`;
  - genmax pha ước tính (cả khi về từ xin duyệt lại) không gọi `tieu`, xong thì sang `cho_duyet`;
  - test cũ vẫn qua.

**FX-11 · culiapp-web · Worker: route tiêu, sổ KV, sai mật khẩu bằng KV, `sha_tham_so`**
- ĐƯỢC SỬA: `cf/src/worker.js`, `cf/test/worker.test.mjs`, `cf/test/chu-ky-cheo.test.mjs`
- Phụ thuộc: FX-9 (mục `tieu` trong `vector_ky.json`).
- **Hiện trạng lúc viết phiếu (A-D9 đã đọc):** cây làm việc đã có một phần FX-11, gồm:
  - `chuoiTieuDuyet` / `kyTieuDuyet` (`cf/src/worker.js:360`, `:364`);
  - `tieuDuyet` (`:381`), route ở `:655-656`;
  - `sha_tham_so` trong `duyetViec` (`:553-604`);
  - `xin-duyet-lai` trong regex `tuyenViec` (`:455`).

  Đếm sai mật khẩu vẫn dùng Cache API (`:506-530`). Kỹ sư **đối chiếu và hoàn thiện** theo phiếu này, không viết lại phần đã khớp.
- Interface (giữ tên đã có):
  - `export async function chuoiTieuDuyet(id, chuKyDuyet, nonce) -> Uint8Array` (đúng byte §8.3);
  - `export async function kyTieuDuyet(env, id, chuKyDuyet, nonce) -> string`;
  - `async function tieuDuyet(req, env) -> Response`;
  - `export async function demSaiDoc(env, user)` và `export async function demSaiGhi(env, user, dem)` (KV `sai:<user>`, TTL 900).
- Việc:
  - route `POST /api/runner/tieu-duyet` đứng **trước** kiểm phiên. Kiểm Origin chung (`:853-857`) chỉ chặn khi có Origin mà lệch, nên runner (không gửi Origin) đi qua được. Route khác dưới `/api/runner/` → 404;
  - §8.3 "Tiêu lời duyệt" đúng từng nhánh;
  - `duyetViec` kiểm `sha_tham_so` theo §8.2;
  - thay Cache API bằng KV theo §9 mục 4;
  - regex `tuyenViec` có `xin-duyet-lai` (lam `boi`).
- Lệnh kiểm chứng: `node --test cf/test/`
- Xong khi (KV giả bằng `Map`, có cờ để `put` ném lỗi):
  - sai/thiếu `x-runner-key` → 401 và không đụng KV; body sai hình dạng → 400;
  - lần 1 → 200, `ky` kiểm được bằng khoá công khai test; lần 2 cùng `chu_ky_duyet` (nonce khác) → 409;
  - `put` ném → 503, không có `ky`; thiếu binding `SO_DUYET` → 503;
  - `chuoiTieuDuyet` khớp vector `tieu`;
  - `/duyet` thiếu hoặc lệch `sha_tham_so` → 409 và không POST máy nhà;
  - sai mật khẩu lần 6 → 429 kể cả sau `datLaiDemSaiMatKhau()` (đọc lại từ KV giả);
  - test cũ vẫn qua.

**FX-12 · culiapp-web · Giao diện xin duyệt lại, `sha_tham_so`; video_server cho qua `xin-duyet-lai`**
- ĐƯỢC SỬA: `web/viec.js`, `web/style.css`, `web/index.html` (chỉ tăng `viec.js?v=`), `cf/test/viec-web.test.mjs`, `tools/video_server.py`, `tools/test_video_server.py`
- Phụ thuộc: FX-9 (tên trường `co_the_xin_duyet_lai`, `chan_ton_tien`). Chạy song song với FX-11 vì không trùng file.
- Hiện trạng lúc viết phiếu: `web/viec.js:176`, `:228` đã có một phần nút "Xin duyệt lại". Kỹ sư đối chiếu và hoàn thiện, không viết lại.
- Interface (hàm thuần giữa marker `viec-thuan`):
  - `async function shaThamSo(thamSoChuan) -> string` (hex 64);
  - `function nutHanhDong(viec, laTonTien) -> [{nhan, hanh_dong}]`, với `hanh_dong ∈ huy|chay-tiep|chay-lai|xin-duyet-lai`.
- Việc:
  - khung duyệt gửi `sha_tham_so` tính từ đúng `tham_so_chuan` đã vẽ;
  - nút "Xin duyệt lại" khi `co_the_xin_duyet_lai`, kèm dòng "Lần chạy trước có thể đã tốn tiền — xem log trước khi duyệt lại";
  - việc tốn tiền ở `can_tra_loi` (mọi loại câu hỏi): chỉ hiện nội dung câu hỏi để đọc, **không có nút trả lời**, chỉ có "Xin duyệt lại" (POST `xin-duyet-lai`) và "Huỷ" (A-D9b);
  - form `poster_len_lich`: `so_video_ngay` 1–100, ghi chú "tối đa 100 video/ngày mỗi tài khoản (tạm tính theo folder)";
  - dải đỏ khi `/suc-khoe.chan_ton_tien`: "Bản cài runner lệch tổng kiểm — việc tốn tiền đang bị chặn";
  - video_server: regex §3.2 thêm `xin-duyet-lai`.
- Lệnh kiểm chứng: `node --check web/viec.js && node --test cf/test/ && python -B -m pytest tools/test_video_server.py -q`
- Xong khi:
  - `nutHanhDong` của việc tốn tiền ở `loi` không có `chay-tiep`, có `xin-duyet-lai`; ở `can_tra_loi` chỉ có `xin-duyet-lai` và `huy`;
  - `shaThamSo` khớp sha256 của Python với chuỗi tiếng Việt mẫu;
  - video_server chuyển `/r/viec/<id>/xin-duyet-lai`;
  - `grep -nE "on[a-z]+=\"" web/viec.js` → 0;
  - test cũ vẫn qua.

**Tích hợp FX (trưởng phòng chạy, NEEDS_APPROVAL từng bước):**
1. `cd cf && npx wrangler deploy` (FX-11, FX-12 web). Worker phải lên **trước** runner. Nếu runner mới chạy trước, `tieu` trả `chua_ro` và việc tốn tiền chỉ đứng chờ (an toàn).
2. Khởi động lại video_server (FX-12).
3. Tắt runner → `python tools/cai_runner.py` → bật runner (FX-9, FX-10).
4. Kiểm trên web: `/suc-khoe` có `chan_ton_tien: false`; một việc `poster_len_lich` 1 video được duyệt và chạy; `GET /api/viec/<id>` của việc đó có `so_lan_tieu=1`; bấm thử "Xin duyệt lại" trên một việc `loi` (nếu có).

### Bảng chồng file theo lượt

| Lượt | Phiếu và file |
|---|---|
| Đ3-L1 | B-1 (`kieu, kho_viec, danh_muc, du_an, phieu, han_muc` + 4 test) · B-1b (`radar_xuat` + test) · B-1c (`chu_ky, tao_khoa_ky, vector_ky.json` + test) · A-1 (`thuc_thi, stream_json` + 2 test) · W-0 (`web/vendor/*, web/_headers, web/index.html`) · W-1 (`cf/src/worker.js, cf/test/worker.test.mjs`) · W-3 (`tools/video_server.py` + test) · S-1 (`spike_claude.py`) |
| Đ3-L2 | B-2 (`api.py` + test) · A-2 (`vong_lap, chay_runner, cai_runner, chay_video.bat, stream_json.py` + test) · W-1b (`cf/test/chu-ky-cheo.test.mjs`) · W-2 (`web/viec.js, app.js, index.html, style.css, cf/test/viec-web.test.mjs`) |
| Đ4-L1 | B-3 |
| Đ4-L2 | A-3 (`vong_lap`) · W-4 (`worker.js`) |
| Đ4-L3 | W-5 (`viec.js`) |
| FX-L1 | FX-9 (`chu_ky, vector_ky.json, kho_viec, han_muc, api` + 4 test) |
| FX-L2 | FX-10 (`so_duyet, vong_lap, chay_runner` + 3 test) · FX-11 (`worker.js, worker.test.mjs, chu-ky-cheo.test.mjs`) · FX-12 (`viec.js, style.css, index.html, viec-web.test.mjs, video_server.py` + test) |
| Đ5 | S-2 → K-1 ∥ B-4 → A-4 ∥ W-6 |

`stream_json.py` thuộc A-1 ở L1 rồi A-2 ở L2 (cùng vị trí, tuần tự). `web/index.html` thuộc W-0 ở L1 rồi W-2 ở L2 (tuần tự).

Gợi ý cho trưởng phòng: thêm các `tools/test_runner_*.py` và `cf/test/` vào `LENH` của `.culiapp/kiem-chung.py`.

---

## 14. Câu hỏi mở cần người dùng chốt

- **Q1. Hạn mức trần** (§10). Claude 40 USD-ước-tính và 12 việc mỗi ngày; Muse ≤10 clip/việc, 15 clip/ngày; GenMax ≤25 bản/việc, 2 việc/ngày; lên lịch Poster 2 lần/ngày, ≤100 video/ngày mỗi tài khoản (A-D9b; bản đầu là ≤5); taovideo 1/ngày; Codex 6 lượt/việc. Vì là trần trong code, muốn **nới** phải sửa code và cài lại; muốn **hạ** thì sửa `cau_hinh.json`. Đề xuất: giữ các số này.
- **Q2. Ai được duyệt việc tốn tiền?**
  - (A, đề xuất) Cả `nhan` và `comeofage`; mỗi lần nhập lại mật khẩu của chính mình; tên người duyệt được ký vào phiếu.
  - (B) Chỉ `comeofage`.
- **Q3. Cách xác nhận lại khi gõ chữ tự do** (lời duyệt đợt 4, trả lời đợt 5).
  - (A, đề xuất) Nhập lại mật khẩu đăng nhập mỗi lần.
  - (B) Mã PIN riêng 6 số (thêm secret và một bước cài).

  Câu hỏi này không ảnh hưởng đợt 3, vì đợt 3 chỉ có nút.

Câu Q1 cũ (repo dùng chung) đã khép bằng D8 và tình trạng mới (repo ở `main`).

---

## 15. Tự soát

- File và hàm hiện có được dẫn đều đã kiểm:
  - `cf/src/worker.js:62-74,90,178,184-186,242-268,430,432-435`;
  - `cf/wrangler.toml` (`run_worker_first`);
  - `web/index.html:8-11`;
  - `web/app.js:53,77,305,381,388,403,635,772` (6 `style="`);
  - `tools/video_server.py:24,28,33-36,120-121,181-191,281`;
  - `tools/kho.py:43,231-235,304-331,404-419,462-468,625-641`;
  - `tools/chay_video.bat:4-5`; `.gitignore`;
  - `phantichcanhquay\SKILL.md:145-156`;
  - các file agent và script ở §1;
  - `claude.exe`, `agy.exe`, Poster venv;
  - `cryptography` 45.0.5 có Ed25519.
- File mới đều nằm trong ĐƯỢC SỬA của đúng một phiếu ở mỗi lượt (bảng §13).
- Giả định chưa kiểm (để spike hoặc kỹ sư xác nhận):
  - các trường stream-json;
  - `dontAsk` có ghi đè được `bypassPermissions`;
  - mẫu `*` đầu;
  - chi phí qua proxy;
  - console ẩn;
  - `_headers` của Workers Static Assets;
  - hành vi việc nền (S-2).

---

## 16. Đối chiếu phản biện A-01b

| Mục | Đã sửa ở |
|---|---|
| P1-1 instance thứ hai giết job | §4.1 (mutex + lock đầu `main()`), §4.6, A-1 `gianh_don_instance`, test A-2 |
| P1-2 XSS → RCE | §9 (tự host, CSP `_headers`, đợt 3 chỉ nút, mật khẩu cho chữ tự do), W-0 ở Đ3-L1, §8.1–8.2, W-2, W-4/W-6 |
| P1-3 tự duyệt / nới hạn mức | D7, §8.3 (ký request + ký duyệt, kiểm lại lúc nhận, giới hạn còn lại), §10 (trần trong code, file chỉ hạ), B-1c, B-3, A-3 |
| P2-1 che bí mật | §4.7 (theo giá trị + mẫu `sk-…`, env tối thiểu), A-1 |
| P2-2 `chay-tiep` | §4.3, §3.2 regex, §8.1–8.2, W-1, B-2 |
| P2-3 captcha Douyin | §5.1 `douyin_uid` + ánh xạ captcha, §11, §7.3 (K-1) |
| P2-4 đối soát phan_tich_uid | §5.1 (`rui_ro` + `douyin.md`) |
| P2-5 phụ thuộc spike | §6.2 `stream_json.py` cô lập; A-1 viết theo giả định, A-2 chỉnh; S-1 mở rộng 10 mục; `--tools` |
| P2-6 USD không hiệu lực | §6.3 4 chốt (việc/ngày, trần lượt) |
| P2-7 voice_pv dở | §5.1 (ffprobe + mtime + đổi tên), §11 R-N |
| P2-8 kho.py không khoá | §4.4 mutex `kho` mọi làn + chẩn đoán 4 nhánh; D8 code cài ngoài repo |
| P2-9 taovideo | §5.3 (`SendMessage`, trần Codex), S-2, §7.1 |
| P2-10 hạn mức lúc nhận | §5.2, A-3 |
| P2-11 radar không Bash | §5.1 (`radar_xuat.py` + `--tools Read,Write,Glob`, chạy bù là bước script), B-1b |
| P3 console | §6.1 (console ẩn dùng chung, không `CREATE_NO_WINDOW`) |
| P3 Job Object sau Popen | §4.6 (runner tự gắn, con sinh ra đã trong job) |
| P3 `dang_chay→cho` | §4.3 |
| P3 cờ phiên | §4.2 `phien_da_tao`, §6.1 |
| P3 tên bản tin theo ngày dữ liệu | §5.1 radar |
| P3 disallowedTools không phải chốt | §6.1 |
| P3 mâu thuẫn "không hỏi người dùng" | §6.4 ngoại lệ trong phiếu, §7.3 K-1 |
| `.gitignore` đã có khoá | bỏ khỏi A-2; R-B |
