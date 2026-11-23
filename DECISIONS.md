# Quyết định kiến trúc — Kho sản phẩm

Quy ước:
- Mỗi quyết định khó đảo ngược là một mục D<số>, đánh số nối tiếp. Không xoá mục cũ.
- Quyết định mới để "Đề xuất". Chỉ chuyển sang "Đã chốt" khi người dùng duyệt.
- Thiết kế chi tiết nằm ở `docs/bo-chay-viec.md`.

D1–D6 được sửa ngay tại chỗ theo phản biện A-01b, vì đều còn ở trạng thái Đề xuất và chưa ai duyệt.

## D1: Bộ chạy việc là tiến trình riêng, trạng thái lưu SQLite ngoài repo  (2026-11-17)
Trạng thái: Đã chốt (người dùng duyệt 17/11/2026: "Duyệt, làm luôn"; hạn mức "Giữ mức đề xuất"; người duyệt "Cả nhan và comeofage")

**Bối cảnh.** Web Kho sản phẩm cần chạy các việc của Phòng Affiliate trên máy nhà Windows, gồm agent Claude và script. Việc dài từ vài phút đến nhiều giờ. Yêu cầu:
- sống qua reboot;
- không chạy trùng;
- không tranh GPU.

`tools/video_server.py` là ThreadingHTTPServer đang phục vụ stream video (`tools/video_server.py:59-86`, `:281`). Người dùng đã chốt: mọi thứ nằm trong cùng web Kho.

**Quyết định.**
- Runner là tiến trình riêng: user Mi, nghe `127.0.0.1:8788`, bật khi đăng nhập Windows qua `tools/chay_video.bat`.
- Code nằm ở thư mục cài theo D8.
- Trạng thái lưu SQLite WAL ở `%LOCALAPPDATA%\kho-runner\runner.db`.
- **Đơn instance:** giành named mutex `Local\kho-runner` + `msvcrt.locking` trên `runner.lock` ở dòng đầu `main()`, trước mọi thao tác với job hay tiến trình.
- Hai làn tuần tự `gpu` và `nhe`.
- Mutex tài nguyên `kho` dùng chung mọi làn cho việc gọi `kho.py`.
- Khoá chống trùng (loại, khoá) bằng unique index một phần.
- Giao diện việc nằm trong web Kho, file `web/viec.js`.

**Phương án đã loại.**
- Nhồi queue + `jobs.json` vào `video_server.py`: lỗi bộ chạy làm sập luôn nút tải video, và khoá phát video trở thành khoá chạy agent.
- Lưu job trong repo GitHub: chậm, mỗi lần đổi trạng thái thành một commit.
- Kiểm đơn instance bằng việc bind cổng: bước dọn mồ côi chạy trước khi bind, nên instance thứ hai sẽ giết job của instance đang chạy.
- Service LocalSystem: sai profile người dùng.
- App hoặc web riêng: người dùng đã bác.

**Hệ quả.**
- Không ai đăng nhập Windows thì bộ chạy tắt; trang 🩺 báo điều này.
- Dữ liệu chạy nằm ngoài git.
- Khi `taovideo` chạy (giữ `kho` hàng giờ), các việc đụng kho ở làn `nhe` phải đợi.

## D2: Đường vào bộ chạy qua video_server chuyển tiếp `/r/*`, khoá thứ hai `RUNNER_KEY`  (2026-11-17)
Trạng thái: Đã chốt (người dùng duyệt 17/11/2026: "Duyệt, làm luôn"; hạn mức "Giữ mức đề xuất"; người duyệt "Cả nhan và comeofage")

**Bối cảnh.** Runner chỉ nghe 127.0.0.1. Thêm hostname tunnel mới phải sửa config của service LocalSystem, tức cần UAC. Người dùng không rành kỹ thuật. Yêu cầu: lộ `VIDEO_KEY` không được đủ để chạy việc.

**Quyết định.**
- Worker gọi `https://video.kutidak.com/r/...` kèm `x-key=VIDEO_KEY` và `x-runner-key=RUNNER_KEY`; các request ghi kèm thêm `x-ky*` (D7).
- `video_server.py` kiểm `x-key`, lọc path/query/body theo allowlist, và chỉ chuyển sang `127.0.0.1:8788` các header `x-runner-key`, `x-ky*`, `content-type`.
- Runner kiểm `x-runner-key` cho mọi request, kiểm chữ ký cho request ghi.

**Phương án đã loại.**
- Hostname tunnel mới: cần UAC và dashboard; không có Cloudflare Access thì chỉ cần một khoá là gọi thẳng được runner.
- Dùng chung `VIDEO_KEY`: lộ khoá xem video là chạy được agent.

**Hệ quả.**
- Runner phụ thuộc video_server còn sống.
- Thêm khoảng 50 dòng chuyển tiếp trong video_server.
- Trưởng phòng phải đặt các secret Worker `RUNNER_KEY` và `KY_RIENG`.

## D3: Danh mục việc cố định; web không gửi đường dẫn hay lệnh; đợt 3 chỉ trả lời bằng nút  (2026-11-17)
Trạng thái: Đã chốt (người dùng duyệt 17/11/2026: "Duyệt, làm luôn"; hạn mức "Giữ mức đề xuất"; người duyệt "Cả nhan và comeofage")
Bị thay một phần bởi D13 (đường dẫn/chữ tự do tới backend Poster qua `/api/poster/*`)

**Bối cảnh.** Web công khai điều khiển máy nhà, có agent dùng Bash. Thư viện JS nạp từ CDN không ghim phiên bản (`web/index.html:8-10`) và chưa có CSP, nên XSS có thể biến thành chạy lệnh trên máy nhà.

**Quyết định.**
- Runner chỉ nhận các loại việc trong `danh_muc.py`:
  - đợt 3: `radar_ban_tin`, `phan_tich_uid`, `douyin_uid`, `xu_ly_link_moi`, `poster_day_folder`, `voice_pv`;
  - đợt 4: `muse_clip`, `voice_genmax`, `poster_len_lich`;
  - đợt 5: `taovideo`.
- Tham số validate chặt:
  - UID khớp `^\d{19}$`;
  - dự án là mã băm do runner tự dò;
  - mẻ lấy từ tên file có thật.
- **Đợt 3 chỉ trả lời bằng nút:** chọn, đã làm xong, tiếp tục.
- Chữ tự do chỉ có ở 2 chỗ: lời duyệt (đợt 4) và trả lời câu hỏi (đợt 5). Cả hai bắt nhập lại mật khẩu mỗi lần gửi và được đặt trong khối `<<< >>>` của phiếu.
- Tự host `marked@12.0.2`, `dompurify@3.4.18`, `qrcode-generator@1.4.4` trong `web/vendor/`, đặt CSP `script-src 'self'` qua `web/_headers`.
- Việc miễn phí mà agent trả `NEEDS_APPROVAL` bị chuyển `loi`, web không có nút duyệt cho trường hợp này.

**Phương án đã loại.**
- Ô lệnh hoặc ô prompt tự do: mở đường chạy lệnh tuỳ ý.
- Cho trả lời chữ tự do ngay ở đợt 3: XSS có thể đưa chữ thẳng vào agent có Bash.
- Giữ CDN nhưng gắn SRI: vẫn phải để `script-src` mở cho bên ngoài.

**Hệ quả.**
- Mỗi việc mới phải thêm code vào danh mục.
- Ở đợt 3, câu hỏi cần chữ tự do sẽ thành "việc của bạn" (làm trên máy).
- Mỗi lần nâng thư viện JS phải tải lại thủ công, có duyệt.

## D4: Gọi Claude headless theo lượt; phát hiện câu hỏi bằng khối `CẦN_USER` / dòng `TRẠNG THÁI`; trả lời bằng `--resume`  (2026-11-17)
Trạng thái: Đã chốt (người dùng duyệt 17/11/2026: "Duyệt, làm luôn"; hạn mức "Giữ mức đề xuất"; người duyệt "Cả nhan và comeofage")

**Bối cảnh.**
- Agent `aff-*` cần chạy khi không có người ngồi máy.
- `aff-taovideo` có điểm phải hỏi người dùng (`aff-taovideo.md:32`).
- Claude CLI 2.1.169 có `-p`, `--agent`, `--tools`, `--session-id`, `--resume`, `--output-format stream-json`, `--permission-mode dontAsk`, `--allowedTools`/`--disallowedTools`, `--max-budget-usd`; **không có `--max-turns`**.
- `settings.json` của người dùng đặt `defaultMode=bypassPermissions` và đi qua proxy `ANTHROPIC_BASE_URL`.

**Quyết định.**
- Gọi thẳng `claude.exe` với `-p --agent <aff-…> --tools <bộ theo loại> --permission-mode dontAsk --allowedTools … --disallowedTools … --output-format stream-json --verbose`.
- Lần đầu dùng `--session-id`; chỉ dùng `--resume` khi đã thấy sự kiện init (`phien_da_tao`).
- Phiếu đưa qua stdin; tiến trình chạy trong console ẩn dùng chung, env tối thiểu.
- Mọi chỗ đọc trường stream-json gom vào `stream_json.py` để sửa được sau khi spike S-01 xác nhận tên trường.
- Bốn chốt chi phí:
  - USD/ngày;
  - số việc Claude/ngày;
  - trần số lượt mỗi việc (đếm từ luồng sự kiện);
  - `--max-budget-usd`.
- Radar chạy Claude chỉ với `--tools Read,Write,Glob`, dữ liệu do script xuất sẵn.
- Coi `--disallowedTools` là lớp chặn nhầm lẫn, không phải chốt chặn.

**Phương án đã loại.**
- stream-json hai chiều giữ tiến trình sống: treo hàng giờ, mất phiên khi reboot.
- `bypassPermissions`: không có danh sách công cụ cho phép.
- Chỉ dựa vào USD: có thể sai khi đi qua proxy.

**Hệ quả.**
- Spike S-01 bắt buộc kiểm `dontAsk` có ghi đè được `defaultMode` không; không được thì dùng `--settings` tối thiểu.
- Đợt 5 phụ thuộc spike S-02 (việc nền khi `-p` thoát). Nếu S-02 không đạt, đợt 5 dừng ở mức "chạy tay, theo dõi trên web".

## D5: Việc tốn tiền luôn qua `cho_duyet`; trần hạn mức là hằng số trong code; lời duyệt nguyên văn  (2026-11-17)
Trạng thái: Đã chốt (người dùng duyệt 17/11/2026: "Duyệt, làm luôn"; hạn mức "Giữ mức đề xuất"; người duyệt "Cả nhan và comeofage")

**Bối cảnh.**
- Muse, GenMax, lên lịch Poster và taovideo tốn tiền hoặc có rủi ro.
- Agent chạy cùng user Mi đọc và sửa được `cau_hinh.json`.

**Quyết định.**
- Các loại `ton_tien` khi tạo vào thẳng `cho_duyet`.
- GenMax chạy 2 pha: `tao_voice.py` không có `--dong-y` để lấy ước tính, duyệt xong mới chạy với `--dong-y`.
- Lời duyệt nguyên văn và tên người duyệt được ký theo D7, rồi chèn vào mục `ĐÃ DUYỆT:` của phiếu.
- Trần hạn mức là hằng số trong `han_muc.py`. `cau_hinh.json` chỉ được hạ: `min(trần, file)`.
- Hạn mức được kiểm ở 3 lúc: tạo, duyệt, nhận việc (kể cả "chạy tiếp").
- Việc tốn tiền không bao giờ tự chạy lại.

**Phương án đã loại.**
- Chỉ dựa vào luật trong file agent.
- Đặt hạn mức trong file cấu hình mà file được nới: agent tự nới được.

**Hệ quả.**
- Muốn nới trần phải sửa code và cài lại (có duyệt).
- Mỗi việc tốn tiền thêm một bước gõ lời duyệt và mật khẩu.

## D6: Runner tự gắn vào Windows Job Object; khởi động lại thì dọn mồ côi và đối soát đầu ra thật  (2026-11-17)
Trạng thái: Đã chốt (người dùng duyệt 17/11/2026: "Duyệt, làm luôn"; hạn mức "Giữ mức đề xuất"; người duyệt "Cả nhan và comeofage")

**Bối cảnh.** Tiến trình con (Claude, agy, ffmpeg) có thể mồ côi khi runner crash hoặc máy reboot. Gắn từng con vào job sau `Popen` để hở một khoảng thời gian.

**Quyết định.**
- Ngay sau khi giành mutex, runner tự gắn mình vào Job Object có `KILL_ON_JOB_CLOSE`. Con cháu sinh ra đã nằm sẵn trong job.
- DB lưu `pid` + `create_time`.
- Khi khởi động lại:
  1. giết cây tiến trình cũ nếu create_time khớp;
  2. gọi `kiem_dau_ra`;
  3. đầu ra đã có → `xong`; loại idempotent → `cho` (resume nếu có phiên); còn lại → `loi` kèm nút "Chạy tiếp" hoặc "Chạy lại".
- Đối soát dùng đầu ra thật:
  - `phan_tich_uid`: kiểm `rui_ro` và `douyin.md`;
  - `voice_pv`: kiểm bằng ffprobe; file dở bị đổi tên thành `.hong-<id>`.

**Phương án đã loại.**
- Gắn job sau `Popen`: có khoảng hở.
- Chỉ quét PID: dễ giết nhầm khi PID bị tái dùng.
- Luôn chạy lại job dở: chạy trùng, tốn tiền hai lần.

**Hệ quả.**
- Runner chết thì mọi việc đang chạy bị ngắt.
- Riêng `douyin_uid` (agy cần cửa sổ để giải captcha) là việc riêng, có console hiện, không chạy bên trong phiên Claude.

## D7: Mọi lệnh ghi tới runner và mọi lời duyệt được Worker ký bằng Ed25519  (2026-11-17)
Trạng thái: Đã chốt (người dùng duyệt 17/11/2026: "Duyệt, làm luôn"; hạn mức "Giữ mức đề xuất"; người duyệt "Cả nhan và comeofage")

**Bối cảnh.** Agent Claude chạy dưới cùng user Mi với runner, nên đọc được `.runner_key`, `runner.db`, `cau_hinh.json`. Khi đó agent có thể:
- gọi API localhost để tạo, trả lời hoặc duyệt việc, vì runner tin trường `boi` trong body;
- sửa DB để biến một việc thành "đã duyệt".

Đã kiểm khả năng thực hiện:
- Workers Web Crypto hỗ trợ `Ed25519` (sign/verify, import PKCS8);
- máy có `cryptography` 45.0.5 với Ed25519.

**Quyết định.**
- Khoá riêng Ed25519 chỉ nằm trong secret Worker `KY_RIENG`. Khoá được sinh bằng `tools/runner/tao_khoa_ky.py`, đi thẳng qua pipe vào `wrangler secret put`, không ghi đĩa.
- Khoá công khai nằm trong bản cài runner: `app\ky_cong_khai.pem`.
- **Ký mọi POST** trên chuỗi `kho-runner-v1\nMETHOD\npath\nngay_ms\nnonce\nsha256(body)`. Runner kiểm:
  - lệch thời gian ≤ 120 s;
  - nonce chưa dùng (bảng `nonce`);
  - chữ ký đúng.

  `boi` chỉ được tin khi chữ ký đúng.
- **Ký lời duyệt** trên `kho-duyet-v1\nid\nloai\nsha256(tham_so_chuan)\nsha256(loi_duyet)\nduyet_luc\nboi` và lưu vào `chu_ky_duyet`. Runner kiểm khi nhận duyệt **và mỗi lần nhận việc hoặc chạy tiếp**, nên sửa DB không qua được.
- Chữ tự do (lời duyệt, trả lời đợt 5) chỉ được Worker ký sau khi kiểm lại mật khẩu đăng nhập.
- Có vector test chéo `tools/runner/vector_ky.json` để kiểm Worker và runner ký giống nhau từng byte.

**Phương án đã loại.**
- HMAC dùng chung khoá: runner phải giữ khoá ký, agent đọc trộm là ký được.
- Chạy runner dưới một user Windows riêng: chặn được cả việc agent sửa code runner, nhưng cần admin/UAC và phải chuyển profile Claude, Poster, agy. Quá nặng với người dùng hiện tại.
- Chỉ dựa vào `RUNNER_KEY`: agent cùng user đọc được khoá này.

**Hệ quả.**
- Thêm secret `KY_RIENG` và một bước sinh khoá do trưởng phòng chạy.
- **Rủi ro còn lại:** agent có Bash cố ý sửa code hoặc khoá công khai trong bản cài rồi chờ runner khởi động lại thì D7 không chặn được. Chỉ giảm nhẹ bằng hai cách: cấm thư mục `kho-runner` trong danh sách cấm của Claude, và kiểm tổng `TONG_KIEM.json`. Cả hai đều phát hiện được nhầm lẫn, không chặn được cố ý.

## D8: Code runner chạy từ bản cài cố định ngoài repo; dữ liệu sản phẩm vẫn ở repo  (2026-11-17)
Trạng thái: Đã chốt (người dùng duyệt 17/11/2026: "Duyệt, làm luôn"; hạn mức "Giữ mức đề xuất"; người duyệt "Cả nhan và comeofage")

**Bối cảnh.**
- `kho.py` chạy `git pull --rebase --autostash`, commit và push ngay trong cây làm việc `E:\phantichcanhquay\kho-san-pham` (`tools/kho.py:304-331`).
- Cây làm việc này đồng thời chứa code đang phát triển: repo đang ở `main`, code đợt 1–2 chưa commit.
- Nếu runner chạy code từ chính cây này, mỗi lần `kho.py` pull hay autostash có thể làm đổi code runner giữa chừng.
- Agent (`aff-san-pham`, `aff-taovideo`) gọi `kho.py` theo đường dẫn cố định trong repo.

**Quyết định.**
- `tools/runner/` trong repo chỉ là mã nguồn.
- `tools/cai_runner.py` chép bản phát hành vào `%LOCALAPPDATA%\kho-runner\app\`:
  - kèm `PHIEN_BAN` (commit, có dấu `-sua` nếu cây làm việc bẩn) và `TONG_KIEM.json`;
  - thay thư mục cũ theo kiểu nguyên tử (`app.moi` → `app`, giữ một bản `app.cu`);
  - từ chối cài khi runner đang chạy.
- Startup chạy bản cài.
- Dữ liệu sản phẩm và `kho.py` giữ nguyên trong repo, không phải sửa đường dẫn trong agent.
- `du_an.py` giữ một bản sao `GOCS` (không import video_server từ repo). Có test trong repo kiểm bản sao khớp `tools/video_server.py:24`.
- Việc đụng kho có chẩn đoán riêng cho từng trường hợp:
  - `index.lock` đang bận;
  - `index.lock` cũ;
  - nhánh khác `main`;
  - `data/` bẩn.

**Phương án đã loại.**
- Chạy runner thẳng từ repo: code có thể đổi giữa chừng.
- Tạo bản clone riêng cho dữ liệu: phải sửa đường dẫn trong agent và giữ 2 bản repo.
- Đóng gói thành exe: thừa.

**Hệ quả.**
- Mỗi lần nâng runner cần một bước cài (ghi ngoài thư mục dự án, có duyệt).
- `PHIEN_BAN` hiện trên `/suc-khoe` để biết đang chạy bản nào.
- Bản sao `GOCS` có thể lệch với video_server; test phát hiện được.

## D9: Sổ "lời duyệt đã tiêu" trên Cloudflare KV; mỗi lời duyệt chỉ chạy được một lần pha tốn tiền  (2026-11-17)
Trạng thái: Đã chốt (người dùng chọn "Sổ trên Cloudflare" ngày 17/11/2026, sửa lỗi review R-11 P1-1). Bổ sung D5 và D7, không thay hai quyết định này.
Bị thay một phần bởi D13 (trang Poster V2 không qua hạn mức `poster_len_lich`)

**Bối cảnh.**
- Review R-11 P1-1: chữ ký duyệt D7 chỉ chứng minh "việc này đã được duyệt", không chứng minh "lời duyệt này chưa dùng". Ai sửa được `runner.db` (đưa việc `xong`/`loi` về `cho`, giữ nguyên tham số và chữ ký) thì runner chạy lại pha tốn tiền: chữ ký vẫn khớp, nên Muse/GenMax/Poster bị gọi thêm lần nữa. Agent chạy cùng user Mi sửa được `runner.db` (D7 Bối cảnh).
- Mọi thứ nằm trên máy nhà đều sửa được bởi user Mi. Muốn có "sổ tiêu một lần" thì sổ phải nằm ngoài máy, ở chỗ chỉ Worker ghi được.
- Review R-11 còn nêu: P2-1 lệch `TONG_KIEM.json` mới chỉ cảnh báo, chưa chặn; P2-2 người duyệt có thể ký lên tham số khác với bản đã xem (tham số đổi giữa lúc xem và lúc bấm duyệt).
- Đếm sai mật khẩu đang dùng Cache API (`cf/src/worker.js:441-465`): cache theo colo, không bền.

**Quyết định.**
- **KV `SO_DUYET`** (id `31283948f3834148ad49c7181c92f452`, binding đã có trong `cf/wrangler.toml`).
- **Route Worker `POST /api/runner/tieu-duyet`.** Chỉ cần header `x-runner-key` (không cần phiên, không kiểm Origin). Body `{id, chu_ky_duyet, nonce}`.
  - Khoá KV: `tieu:<sha256_hex(chu_ky_duyet)>`.
  - Lần đầu: ghi KV rồi trả 200 `{ky}`, với `ky` = Ed25519(`KY_RIENG`) trên `"kho-tieu-v1\n" + id + "\n" + sha256_hex(chu_ky_duyet) + "\n" + nonce`.
  - Các lần sau: 409.
- **Runner gọi route này NGAY TRƯỚC mỗi lần chạy pha tốn tiền**, mỗi lần một nonce mới, rồi kiểm `ky` bằng khoá công khai trong bản cài.
  - 200 và chữ ký đúng → chạy.
  - 409 → `loi` "lời duyệt đã dùng".
  - Lỗi mạng, hết giờ, 5xx, 401, chữ ký sai → đứng `cho` (hoãn), không chạy.
- **Bỏ "Chạy tiếp" và "Tiếp tục" cho việc tốn tiền.** Thay bằng nút **"Xin duyệt lại"** (từ `loi` hoặc `can_tra_loi`): việc về `cho_duyet`, xoá 4 trường duyệt cũ, rồi duyệt lại bằng mật khẩu (sinh chữ ký duyệt mới, nên có khoá KV mới).
- **Đếm sai mật khẩu chuyển sang KV** (`sai:<user>`), bỏ Cache API.
- **`/duyet` kèm `sha_tham_so`** = sha256 của `tham_so_chuan` mà người duyệt đã xem. Worker so với bản lấy mới từ runner; lệch → 409 (R-11 P2-2).
- **Lệch `TONG_KIEM` bản cài → chặn việc tốn tiền** (đứng `cho`, không tiêu lời duyệt) cho tới khi cài lại (R-11 P2-1).
- **Hạn mức Poster** (người dùng đổi sau bản D9 đầu, phiếu A-D9b):
  - mỗi việc `poster_len_lich` 1–100 video/ngày;
  - tổng `so_video_ngay` ≤ 100 video **mỗi tài khoản** mỗi ngày;
  - vẫn ≤ 2 việc/ngày.

  Dữ liệu folder Poster chưa có trường tài khoản, nên tạm gom theo `folder_id` (`han_muc.khoa_tai_khoan_poster`).
- **Việc tốn tiền đang ở `can_tra_loi`: trên web chỉ có nút "Xin duyệt lại"**, không trả lời trực tiếp.
- **`voice_genmax` xin duyệt lại khi chưa có ước tính** → về `cho` với `buoc='uoc_tinh'` (pha miễn phí), chạy xong mới sang `cho_duyet`.

**Phương án đã loại.**
- Sổ tiêu trong `runner.db` hoặc file trên máy: user Mi sửa được, không chặn được đúng lỗi P1-1.
- Durable Object làm sổ (đếm nguyên tử, nhất quán mạnh): đúng hơn về lý thuyết nhưng phải thêm class, migration và cấu hình. Runner chạy một instance và gọi tuần tự, nên KV đủ. Người dùng đã chọn KV.
- Ghi sổ vào repo GitHub qua Worker: chậm, mỗi lần chạy thành một commit, và không có so-sánh-rồi-ghi.
- Giữ "Chạy tiếp" bằng cách cho một lời duyệt tiêu N lần: lại mở đường chạy thêm mà không có người bấm duyệt.
- Runner tự ký "đã tiêu": runner không giữ khoá riêng (D7).

**Hệ quả.**
- Một lời duyệt = đúng một lần chạy pha tốn tiền. Sửa `runner.db` để chạy lại sẽ nhận 409, không tốn tiền.
- Việc tốn tiền phụ thuộc mạng tới Cloudflare lúc bắt đầu chạy. Mất mạng thì việc đứng chờ, không chạy.
- Worker ghi KV xong mà runner không nhận được phản hồi (mạng đứt giữa chừng): lần thử sau nhận 409 và việc vào `loi`, phải xin duyệt lại. Kết quả là phải bấm thêm một lần chứ không tốn tiền.
- Mỗi lần việc tốn tiền dừng lại (lỗi hoặc có câu hỏi) phải xin duyệt lại, thêm một bước nhập mật khẩu. Câu hỏi của agent không được trả lời trên web: người duyệt đọc câu hỏi và log rồi quyết định duyệt lại hay huỷ. Đợt 5 (`taovideo` hỏi nhiều lượt) sẽ thiết kế lại khi làm B-4/W-6.
- Hạn mức ngày phải đếm theo số lần đã tiêu, không theo số việc (cột mới `so_lan_tieu`).
- Thêm route Worker, KV, 4 phiếu sửa FX-9..FX-12 (`docs/bo-chay-viec.md` §13).
- **Rủi ro còn lại:**
  - KV chỉ nhất quán cuối cùng (eventual consistency), và đọc-rồi-ghi không nguyên tử. Hai lần gọi gần nhau ở hai colo khác nhau có thể cùng nhận 200. Runner luôn ở cùng một máy nên thường vào cùng colo và đọc thấy bản ghi vừa ghi. Runner gọi tuần tự.
  - Ai có `.runner_key` (agent cùng user) gọi được route này để "tiêu" trước một lời duyệt. Như vậy chỉ chặn được việc (DoS), không chạy được gì tốn tiền: chữ ký trả về gắn nonce của người gọi, runner không dùng được. Spam khoá rác có thể làm cạn hạn mức ghi KV trong ngày.
  - Agent có Bash cùng user vẫn có thể sửa code runner trong bản cài rồi chờ runner khởi động lại (đã ghi ở D7). D9 không đổi điều này. `TONG_KIEM` chỉ phát hiện nhầm lẫn.

## D10: Sửa video từ web bằng bộ chuyển đổi trong bản cài runner, không sửa engine; dựng lại tại chỗ có sao lưu và cập nhật bản ghi nguồn  (2026-11-17)
Trạng thái: Đã chốt (người dùng 17/11/2026: Q1 "Chỉ video đang sửa", Q2 "Trong bộ chạy việc", Q3 "Có, mỗi lần lưu")
Bị thay một phần bởi D12 (vị trí nút ✏ Sửa)

**Bối cảnh.**
- Người dùng muốn sửa phụ đề và đổi clip của một video ngay trong tab ✅ Duyệt, trên điện thoại, rồi dựng lại đúng video đó.
- Engine `F:\auto video oneshot` là app khác và không có git. Engine chưa có lệnh dựng 1 video: `cli.py render` chỉ chạy tiếp `render_batch.json` (`cli.py:441-458`).
- `render_batch.json` bị ghi đè mỗi lần dựng trong cùng thư mục (`render.py:1094`). Bỏ qua render dựa vào `.done.json` có key gồm chữ ký file nguồn (`render.py:911-921`, `render_checkpoint.py:33-49`).
- Dữ liệu thật có đường dẫn tuyệt đối đã cũ: `50oto 1736818222555104357\output_poster\render_batch.json` trỏ `...\50oto\takes`, `...\50oto\output\hau_ky`.
- Mẻ Adam xoá `.done.json` và `_hau_ky/<B>` sau khi đổi tên (`autovideo_audio_take.py:1494-1511`). `output_poster` là hardlink (`day_len_poster.py:95-134`), nên `os.replace` để link trỏ bản cũ.

**Quyết định.**
- **Không sửa engine.** Thêm bộ chuyển đổi `tools/runner/sua_video_engine.py`, chạy bằng Python của engine, cwd là thư mục engine. Bộ này gọi hàm engine có sẵn: `render_single_plan`, `dung_hau_ky_cho_plan`, `build_subtitle_json`, `mach_trung_voi_lich_su`, `load_wm_from_project`. Được cài theo D8 cùng runner. Phần tra cứu thuần stdlib nằm ở `tools/runner/sua_video.py`. Lúc chạy, bộ chuyển đổi kiểm chữ ký các hàm engine; lệch thì từ chối.
- **Tra cứu video → bản ghi:**
  - luồng C (giọng creator): `render_batch.json` + tên `<prefix>_<NNN>.mp4` + `.done.json` khớp size và mtime;
  - luồng A (Adam): `<out>/<B>_plan.json` + segment BASE `<B>_<ma>`;
  - mọi đường dẫn được đổi gốc sang thư mục dự án hiện tại; hậu kỳ luôn dựng lại.
- **Dựng lại tại chỗ:**
  - chép cứng bản cũ vào `_sua_cu/`;
  - dựng 1 bản (luồng C ghi thẳng tên cũ để `.done.json` khớp lần chạy tiếp);
  - **cập nhật đúng một mục** trong `render_batch.json` / `<B>_plan.json` (có sao lưu);
  - nối lại hardlink trong `output_poster`;
  - nhật ký từng bước với đường dẫn tương đối, nên chạy lại được và hoàn tác được.
- Giữ khoá render `.render.lock` và khoá máy `.render-may.lock` theo đúng định dạng `KhoaPlan` của cầu nối Adam.
- **Loại việc mới** `sua_video` và `hoan_tac_sua`: miễn phí, làn `gpu`, gắn `dot=4`. Gắn đợt 6 thì phải nâng `dot_bat`, như vậy mở luôn `taovideo` đợt 5. Trần `sua_video_ngay = 60`.
- **Bản sửa** lưu trong bảng `ban_sua` của runner (schema 3). Việc chỉ mang mã `ban_sua`. Web không gửi đường dẫn; video định danh bằng `ma_video = sha1(ma_du_an/thu_muc/ten)[:16]`.
- **Bổ sung D3: chữ phụ đề là chỗ chữ tự do thứ ba.**
  - Chữ chỉ vào `<take>.sua.srt` qua script, không bao giờ vào phiếu agent hay dòng lệnh.
  - Lọc ký tự: cấm điều khiển, xuống dòng, `{ } \ < >`, `-->`; tối đa 200 ký tự mỗi câu, 30 câu mỗi lần.
  - Bắt nhập mật khẩu khi lưu nếu có sửa chữ (chờ người dùng chốt, Q3 trong `docs/sua-video.md` §12).
- **Phạm vi tối thiểu:** sửa chữ từng câu, đổi clip cùng vai, đổi chỗ hai cảnh phủ. Không cắt, kéo giãn hay xoá đoạn.

**Phương án đã loại.**
- Thêm lệnh `render-mot` vào `cli.py` của engine: sửa app khác không có git; `cli.py` import nặng; skill phải đổi theo. Giữ làm phương án B nếu người dùng muốn (`docs/sua-video.md` §6.8).
- Vá `render_batch.json` rồi xoá `.done.json` và gọi `cli.py render`: chạy lại cả mẻ (ffprobe mọi bản), không dùng được cho mẻ Adam (render_batch là của mẻ cuối, `.done.json` đã bị xoá), và đường dẫn cũ làm key lệch.
- Sửa tay `plan.json` rồi `cli.py timeline`: timeline sinh lại toàn bộ, mất bản đang có, trái luật skill.
- Dựng ra file tên mới (`_v2`) thay vì thay tại chỗ: Poster và sổ `_da_gom.txt` coi là video mới, dễ đăng cả hai bản.
- Chạy `run_subtitle_pipeline` cho cả thư mục take: có thể kích Whisper ở take chưa có `.words.json`.
- Cho chữ phụ đề đi qua tham số việc: vượt giới hạn tham số của Worker (chuỗi ≤ 40), và lẫn dữ liệu với lệnh.

**Hệ quả.**
- Bộ chuyển đổi phụ thuộc hàm nội bộ engine. Engine đổi chữ ký hàm thì việc sửa bị từ chối (không hỏng ngầm); phải sửa bộ chuyển đổi và cài lại runner.
- Ledger chống trùng không biết clip vừa đổi, nên mẻ dựng sau có thể trùng với video đã sửa. Lúc đổi chỉ kiểm trùng với các bản đã có.
- Luồng A dựng lại bằng tham số mặc định của `run` (mẻ không lưu tham số). Nếu mẻ đã chạy với tham số khác thì chuyển cảnh và âm lượng nhạc có thể khác nhẹ. Phiếu tuỳ chọn B-9 sửa skill để lưu tham số (cần duyệt).
- `.sua.srt` được ưu tiên hơn `.script.txt` cho take đã sửa.
- Video dựng lại có `sua_luc` mới, nên phải duyệt lại.
- Mỗi lần sửa giữ tối đa 3 bản cũ trong `_sua_cu/` (tốn đĩa bằng dung lượng video).
- Thêm 6 phiếu (B-6, B-7, A-6, W-7, W-8, W-9) và một bước cài runner, deploy Worker có duyệt.

**Ghi chú 18/11/2026 (A-DOC2, trưởng phòng chốt sau R-20, FX-20, FX-21; không đổi trạng thái).** Chi tiết: `docs/sua-video.md` §6.1, §6.2, §6.3, §6.3a, §6.4, §7.2a.
- **Xếp loại trước khi đè.** Trước khi đè bất kỳ mục nào (video, `.done.json`, mục `chi_so` trong `render_batch.json` / `<B>_plan.json`, `plan_<pid>` trong `plan.json`, phụ đề take + `.sua.srt`), xếp vào `goc` (đã là bản cũ, không làm), `minh` (đúng thứ lần sửa này ghi, được đè), `khac` (đã có bản mới hơn hoặc việc khác đổi, không đè), `mat` (của lần sửa nhưng mất sao lưu, không đè).
- **Hoàn tác:**
  - mục gắn với video ở `khac`/`mat` → mã 2 "đã có bản mới hơn… chưa đổi gì", không chạm gì;
  - mất sao lưu nguồn → từ chối (bỏ cách cũ "giữ bản sửa, cảnh báo");
  - phụ đề take + `.sua.srt` (dùng chung nhiều video) ở `khac`/`mat` → video vẫn về bản cũ, phụ đề giữ nguyên, cảnh báo + `hoan_tac_bo_qua`, **mã 5 "kiểm tay"** (thay cho "để nguyên, cảnh báo, mã 0"). Chạy lại vẫn mã 5.
- **Hoàn nguyên khi dựng hỏng:** đã ở bước `hoan_nguyen` thì không hoàn nguyên lại. Mỗi mục đối chiếu dấu size + `mtime_ns` + sha với dấu việc này ghi (video: size + `mtime_ns`); không khớp → bỏ qua, ghi `hoan_nguyen_bo_qua`, mã 5.
- **Luồng C:** bước `nguon` so `st_mtime_ns` của `render_batch.json` với lúc tra (hoặc với dấu chính việc này đã ghi); lệch → không ghi, cảnh báo.
- **Khoá dự án / máy:** gỡ khoá cũ bằng `os.replace` sang tên tạm rồi so lại, sai thì trả lại.
- **Mật khẩu khi chạy lại (Q3 = "mật khẩu mỗi lần").** Chạy lại / chạy tiếp việc `sua_video` có sửa chữ phụ đề (`ban_sua.phu_de` khác rỗng) phải lưu lại qua `/luu` kèm mật khẩu; nút "Chạy lại"/"Chạy tiếp" trả 409. Runner tự làm nốt sau khi khởi động lại (D6) không bị chặn. Code `api.py` làm ở FX-22.

## D11: `taovideo` chạy bằng một phiên Claude sống suốt việc (stream-json hai chiều); một lời duyệt cho một phiên, kèm trần đo từ dữ liệu thật  (2026-11-17)
Trạng thái: Đã chốt (người dùng 17/11/2026: "1 lần cho cả phiên", "Cho sửa + mở đợt 5"; watermark cho phép: nha.cua.mit hoặc không)

**Bối cảnh.**
- D4 chọn gọi Claude theo lượt và nối bằng `--resume`, và đã loại phương án stream-json hai chiều vì "treo hàng giờ, mất phiên khi reboot". D4 ghi rõ đợt 5 phụ thuộc spike S-02.
- S-2 (đo thật): Bash nền chết khi `-p` thoát; lượt resume không nhận thông báo việc nền; không có `SendMessage` (`.culiapp/nhat-ky.md:31`).
- Quy trình `taomevideo` / `tao-video-tu-canh-quay` dựa vào việc nền ở phiên chính và thông báo hoàn tất (`SKILL.md:48`, `:172`), cấm `sleep` (`:65`), và chờ Poster bằng lệnh nền (`:202`). Theo lượt thì quy trình đứng.
- S-3 (đo thật, `.culiapp/test-spike-s3.json`), với một tiến trình `claude -p --input-format stream-json --output-format stream-json --verbose --strict-mcp-config` giữ stdin mở:
  - tiến trình sống qua nhiều lượt;
  - Bash nền chạy qua ranh giới lượt; thông báo việc nền tới; agent tự thức;
  - khối `CẦN_USER` phát hiện được ở result cuối lượt + im lặng, trả lời qua stdin thì agent nhớ ngữ cảnh;
  - đóng stdin thì thoát gọn mã 0;
  - `total_cost_usd` cộng dồn trong phiên;
  - init báo công cụ `Agent` dưới tên `Task`; không có `SendMessage`.
- `taovideo` là loại tốn tiền (GenMax). D9 hiện bắt mỗi lần sinh tiến trình tốn tiền phải tiêu một lời duyệt mới, và việc tốn tiền ở `can_tra_loi` không được trả lời trên web (A-D9b).
- Key GenMax nằm ở biến môi trường tài khoản Windows, script tự đọc (`tao-video-tu-canh-quay\SKILL.md:40`). Runner không chặn cứng được từng lần gọi GenMax bên trong phiên.

**Quyết định.**
- **Phiên sống.** Mỗi lần chạy `taovideo` là MỘT tiến trình `claude.exe -p --input-format stream-json --output-format stream-json --verbose --agent aff-taovideo --strict-mcp-config --permission-mode dontAsk …`:
  - stdin giữ mở; mỗi tin là một dòng JSON `{"type":"user",…}`; chỉ luồng làn ghi stdin, và chỉ khi agent đang rảnh;
  - làn `gpu`, giữ tài nguyên `kho` suốt phiên;
  - module mới `tools/runner/phien_song.py`; phân loại sự kiện thuần trong `tools/runner/theo_doi_phien.py`.
- **Phát hiện tình trạng** từ sự kiện cấp cao (`parent_tool_use_id` rỗng):
  - `result` + im lặng ≥ 10 s → kết luận lượt;
  - tập việc nền từ `system/task_started` / `task_notification` / `task_updated`;
  - `CẦN_USER` → hỏi; `TRẠNG THÁI: DONE…` → đóng stdin rồi đối soát; không rõ mà còn việc nền → chờ; không rõ mà không còn việc nền → nhắc 1 lần rồi hỏi.
- **Không dùng `--resume` cho `taovideo`.** Mỗi lần sinh tiến trình dùng một session id mới. Chạy tiếp sau khi bị ngắt dùng phiếu "LẦN CHẠY TIẾP", vì trạng thái thật đã nằm ở file (`trang_thai.py tiep`, `trang-thai.json`, kho).
- **Một lời duyệt = một phiên sống** (D9 tiêu đúng một lần, ngay trước khi sinh tiến trình). Trong phiên, trả lời câu hỏi trên web đi thẳng vào stdin, không tiêu lời duyệt. `chon` và `cau_hoi` bắt nhập lại mật khẩu; `viec_tay` và `khong_ro` chỉ cần nút. Phiên kết thúc vì bất kỳ lý do gì → muốn chạy tiếp phải "Xin duyệt lại".
- **Trần cứng trong một phiên** (hằng số trong `han_muc.py`, chỉ được hạ):
  - ≤ 60 USD-ước-tính, tính bằng chênh lệch `total_cost_usd`;
  - ≤ 25 file voice `*_adam.mp3` mới, đếm file thật;
  - ≤ 6 lượt Codex, đặt lại khi có lời duyệt mới;
  - ≤ 1500 message;
  - 8 giờ làm, 3 giờ cho mỗi lần chờ trả lời, 4 giờ chờ việc nền liên tục, 24 giờ tuyệt đối.

  Vượt trần → giết cả cây → `loi`. `taovideo_ngay` đếm việc (1/ngày); thêm `taovideo_lan_ngay = 3` lần tiêu/ngày.
- **Bị ngắt** (reboot, runner chết, tiến trình chết):
  - không cố nối lại việc nền;
  - `doi_soat_taovideo` **chỉ đọc file**: `<B>_trang-thai.json`, `_log/<B>_tron_goi.xong.json`, `data/<UID>/info.json` → `da_lam_video.poster`, `output/*.mp4`;
  - đổi tên mp3 hỏng `.hong-<id>`;
  - `xong` hoặc `loi` kèm tóm tắt + "Xin duyệt lại".
- **Công cụ** `Read, Write, Edit, Glob, Grep, Bash, Skill, Agent, Task, TaskOutput, TaskStop, TodoWrite`. Bỏ `SendMessage`. Danh sách soát được bổ sung công cụ chỉ đọc mà subagent phát ra, theo kết quả S-4.
- **Bước B** chốt thư mục lúc tạo việc (runner tìm dự án của UID có `takes/*.mp4`), không hỏi giữa chừng.

**Phương án đã loại.**
- Giữ D4 (theo lượt + `--resume`) cho `taovideo`: S-2 cho thấy việc nền chết và thông báo mất, nên quy trình đứng ở render/voice/chờ Poster.
- Bắt skill chạy mọi thứ foreground để hợp với theo lượt: phải viết lại `taomevideo` / `tao-video-tu-canh-quay` (vốn chốt việc nền ở phiên chính sau sự cố "mẻ bigcup đứng 3 giờ", `SKILL.md:47-48`); lượt dài hàng giờ thì quá giờ / trần lượt khó đặt.
- Nối phiên bằng `--resume` sau khi bị ngắt: việc nền không sống sót; đọc lại ngữ cảnh hàng trăm nghìn token rất đắt; chưa đo `--resume` với stream-json vào.
- Duyệt từng pha GenMax qua `CẦN_USER`: không phải chốt chặn (agent tự quyết khi nào hỏi, key đọc từ tài khoản Windows); trái luật "voice tự chạy" đã chốt (`SKILL.md:36`); người dùng phải trả lời đúng lúc voice, việc giữ GPU lâu hơn.
- Một lời duyệt tiêu N lần cho cả việc (kể cả sau khi bị ngắt): D9 đã loại vì mở đường chạy lại mà không có người bấm.
- Nhả tiến trình khi chờ lâu rồi sinh lại: phải tiêu lời duyệt mới hoặc phá D9, và việc nền đang chạy (render, chờ Poster) chết.

**Hệ quả.**
- Quy trình `taovideo` chạy được từ web mà không phải sửa skill. Phiếu có khối "CHẾ ĐỘ CHẠY" thay cho `SendMessage` và chờ Poster nền. K-1/K-2 (sửa agent/skill) làm hành vi ổn định hơn, cần người dùng duyệt.
- Trong lúc chờ trả lời (≤ 3 giờ mỗi câu), làn `gpu` và tài nguyên `kho` bị giữ: `voice_pv`, `voice_genmax`, `sua_video` và các việc đụng kho phải đợi.
- Reboot giữa chừng mất toàn bộ việc nền. Chạy tiếp cần duyệt lại; agent làm tiếp từ file trạng thái.
- Trần GenMax chỉ phát hiện sau khi xảy ra (có thể vượt tối đa 1 file).
- Phụ thuộc vào `--input-format stream-json` của Claude CLI 2.1.169 (ít tài liệu). CLI báo phiên bản khác thì có cảnh báo; nâng bản thì chạy lại S-3/S-4.
- Ngày có `taovideo`, mức chung 40 USD/ngày có thể bị vượt (trần riêng 60). Việc Claude khác đợi tới hôm sau.
- Thêm phiếu S-4, B-5, B-4 (thay bản cũ), W-6 (thay bản cũ), K-1, K-2, A-5 (thay A-4). Không đổi schema DB: phiên sống nhận biết bằng `pid` khác rỗng ở `dang_chay`/`can_tra_loi`.
- Khi D11 được chốt: D4 ghi thêm "Bị thay một phần bởi D11 (loại `taovideo`)"; D9 ghi thêm ngoại lệ trả lời trong phiên sống của `taovideo`.

**Ghi chú 18/11/2026 (A-DOC2): kết luận spike S-4** (đo thật trên Claude CLI 2.1.169, `.culiapp/test-spike-s4.json`; không đổi trạng thái). Chi tiết: `docs/bo-chay-viec.md` §7.0a, §7.2, §7.6, §7.9–§7.11.
- `--tools` nhận `Agent` nhưng `init.tools` báo `Task`; `Skill` gọi được. Giữ cả `Agent` và `Task`.
- `tool_use` của subagent có trên stdout kèm `parent_tool_use_id`. Công cụ ngoài `--tools` (`WebFetch`) subagent không gọi được, nên danh sách soát **không nới thêm** công cụ nào (thay câu "bổ sung công cụ chỉ đọc mà subagent phát ra" ở mục Công cụ).
- Subagent **không** gọi được `Agent` lồng. Mọi fan-out (vd C2 viết kịch bản bằng `tvc-tho`) phải do agent chính của tiến trình gọi: thêm dòng vào khối CHẾ ĐỘ CHẠY, và đề xuất K-3 sửa skill (cần duyệt).
- Tin user ghi vào stdin giữa lượt (agent đang chạy công cụ) không chen vào lượt đó, chỉ được thấy ở lượt sau. Runner xếp hàng mọi tin và chỉ ghi stdin sau sự kiện `result` cấp cao, mỗi `result` tối đa một tin. Mỗi câu hỏi có **mã câu hỏi**; câu trả lời mang mã đó, lệch thì bỏ, để không trả nhầm câu hỏi mới.
- `--max-budget-usd` cộng dồn cả phiên; chạm trần thì mọi lượt sau trả `error_max_budget_usd` ngay. Đặt bằng trần phiên (60 USD, hoặc mức đã hạ); runner vẫn tự giám sát theo chênh lệch `total_cost_usd`.
- Im lặng 30 phút với stdin mở: tiến trình sống, nhớ ngữ cảnh.
- `total_cost_usd` gồm cả subagent, cộng dồn trong phiên.
- Có `system/task_started` (cả `Agent` foreground) và `task_notification` `status = "completed"`.
- Phiếu phát sinh: FX-24, FX-25, FX-26, K-3 (`docs/bo-chay-viec.md` §13, Đ5-L3).

## D12: Web Kho dùng menu trái 6 mục, mỗi trang một việc; đăng bài chỉ ở trang Đăng bài, dựng trên việc có sẵn  (2026-11-18)
Trạng thái: Đã chốt (2026-11-18; người dùng duyệt thiết kế: "Đồng ý, làm đi"; B-L1 `poster_bo_loai` làm trong đợt này: "Làm luôn đợt này")
Bị thay một phần bởi D13 (menu 7 mục; gọi thẳng Poster V2 và không chặn video Loại trong mục Poster V2)

**Bối cảnh.**
- Người dùng nói web "quá rối rắm, chồng chéo, muốn đăng bài cũng không biết làm thế nào".
- Hiện tại chuyện đăng nằm rải ở 3 chỗ trên trang SP:
  - khối "Bước tiếp theo" (`web/loi.js:192-200`);
  - nút `poster_day_folder` / `poster_len_lich` của khối việc, chỉ hiện ở bước 8 (`web/viec.js:115`);
  - dòng "Tải về", tải rồi xoá file (`web/app.js:511`, `:942-985`).
- Nút đăng chỉ hiện khi đã chấm hết video (`web/app.js:415-418` + `buocHienTai`). Trang SP có 9 tab.
- Người dùng đã chốt:
  - menu 6 mục (Hôm nay · Sản phẩm · Cần quay · Duyệt video · Đăng bài · Máy nhà), trên điện thoại thành thanh đáy;
  - trang Đăng bài kiểu Poster V2;
  - không bắt chấm hết; video Loại không được đăng;
  - video Loại dời sang `_loai/` bằng việc miễn phí ở máy nhà;
  - ⛔ Ngừng đăng khoá Lên lịch;
  - linh/thu chỉ thấy Kho sản phẩm (ca 2026-11-18-d).
- Điều tra:
  - runner **không** lọc video Loại khi đẩy folder hay lên lịch. Dữ liệu chấm chỉ nằm ở `data/<id>/duyet.json`, không script máy nhà nào đọc (`docs/giao-dien-menu-trai.md` §1.1);
  - Poster V2 ghim tên + đường dẫn file vào hàng đợi **lúc lên lịch** (`E:/tool/tiktok_poster_v2/src/backend/scheduler/queue_builder.py:229-271`), nên phải dời video Loại trước khi lên lịch.
- `data/index.json` không có `da_lam_video`, Đạt/Loại hay số video (`tools/kho.py:287-296`).

**Quyết định.** Thay một phần D10: nút ✏ Sửa rời tab ✅ Duyệt của trang SP sang trang Duyệt video. Phần còn lại của D10 giữ nguyên.
- Chủ kho có menu 6 mục:
  - cột trái 200px khi màn ≥ 900px, thanh đáy khi hẹp hơn.
- Người không phải chủ kho giữ giao diện P-33: 1 mục "Sản phẩm", không cột trái, không thanh đáy.
- Route mới: `#/can-quay`, `#/duyet[/<id>]`, `#/dang[/<id>]`, `#/may-nha`. Route cũ (`#/`, `#/kho`, `#/sp/<id>`, `#/viec[/<id>]`, `#/suc-khoe`, `#/sua/…`) vẫn vào được, không redirect.
- **Đăng chỉ ở trang Đăng bài.**
  - Dùng đúng việc có sẵn: `poster_day_folder` (miễn phí), `poster_len_lich` (tốn tiền, qua `cho_duyet` và duyệt mật khẩu ở `#/viec/<id>`).
  - Không đổi D3, D5, D7, D9.
  - Bỏ nút đăng khỏi khối việc trang SP; dời "Tải về" sang Đăng bài, bỏ qua video Loại.
- Không bắt chấm hết. Chặn video Loại ở 2 lớp:
  - web: trang Đăng bài + nút Duyệt của mọi việc `poster_len_lich`;
  - máy nhà (B-L1, làm trong đợt này): việc miễn phí `poster_bo_loai {uid}` dời file Loại ở cấp trên `output_poster/`, `output/` sang `_loai/` và chuyển ngược khi hết Loại. `poster_len_lich` không qua được điều kiện chạy khi folder còn Loại. B-L1 thêm 1 dòng vào danh mục loại việc của Worker.
- Danh sách SP ở các trang chỉ dùng `/api/ds`. Số Đạt/Loại/chưa chấm và folder Poster chỉ tải khi đã chọn 1 SP.
- Phần mới nằm ở file mới (`web/khung.js`, `web/menu.css`, `web/dang.js`, `web/duyet.js`), có tiền tố tên toàn cục `mn`/`dg`/`dy`. `app.js` chỉ có móc ở lượt đầu. Không thêm thư viện.
- Thiết kế chi tiết: `docs/giao-dien-menu-trai.md`.

**Phương án đã loại.**
- Giữ 3 tab, chỉ dọn trang SP: không trả lời được "đăng ở đâu", vẫn phải vào từng SP.
- Viết lại bằng framework SPA (React/Vue): phải đổi cách nạp script dưới CSP `script-src 'self'` và vendor tự host (D3), viết lại cả 5 file JS và bộ test JS hiện có (229 pass, `.culiapp/nhat-ky.md:8`).
- Trang Đăng bài gọi thẳng API Poster V2 / có nút "Đăng ngay" (`post_now`): phá danh mục cố định (D3) và luật việc tốn tiền phải duyệt (D5, D9).
- Thêm endpoint Worker trả tóm tắt video của mọi SP: phải gọi máy nhà theo từng SP qua tunnel, hoặc đổi API runner (ngoài phạm vi). Danh sách không cần số liệu này mới chọn được SP.
- Giữ luật "chấm hết mới đăng": người dùng đã bác.
- Web tự xoá video Loại bằng `/api/video/<id>/xoa`: xoá luôn bản gốc trong `output_daonguoc` (`tools/video_server.py:48-56`), không hoàn tác được.
- Chỉ cảnh báo, không chặn: trái chốt "video Loại không được đăng".
- Gắn bước dời Loại vào chính `poster_len_lich`: lời duyệt bị tiêu trước khi sinh tiến trình đầu (`tools/runner/vong_lap.py:1462-1464`), nên bước miễn phí hỏng cũng làm mất lời duyệt.
- Dồn phần mới vào `app.js`: đụng độ với phiên song song và với các phiếu cùng lượt.

**Hệ quả.**
- Mỗi việc có đúng một trang; link cũ vẫn chạy.
- Trang SP còn 7 tab.
- "Bước tiếp theo" trỏ sang Duyệt / Đăng.
- Thẻ kho dùng chung hệ 4 chặng.
- Không làm B-L1 thì còn hở 2 chỗ:
  - folder creator lên lịch không qua trang Đăng bài (tên folder không chứa UID, web chỉ cảnh báo);
  - video bị chấm Loại sau khi đã vào hàng đợi Poster.
- Có B-L1 thì lượt đã vào hàng đợi trỏ file đã dời, có thể đăng lỗi và được thử lại (chưa đo). Xoá khỏi hàng đợi phải làm tay trong app Poster.
- Thanh đáy phải nhường màn sửa video (`.sua-thanh`) và toast; trên Android có thể bị bàn phím ảo đẩy lên.
- Không deploy giữa lượt 1 và lượt 2.
- Phiếu: W-M1, W-M2, B-L1 (lượt 1), W-M3 (lượt 2), W-M4 (sau B-L1). Thêm 3 file test JS, trưởng phòng đưa vào `kiem-chung.py`.
- Khi D12 chốt: D10 ghi thêm "Bị thay một phần bởi D12 (vị trí nút ✏ Sửa)".

## D13: Trang "Poster V2" trên web Kho gọi thẳng backend Poster qua video_server; chủ kho bấm mọi nút ghi không qua việc, không mật khẩu  (2026-11-18)
Trạng thái: Đã chốt (2026-11-18; người dùng duyệt thiết kế: "Đồng ý, làm đi")

**Bối cảnh.**
- Người dùng chốt (phiếu A-PV1): thêm mục menu thứ 7 "Poster V2" (chỉ chủ kho), trong đó có 9 trang giống hệt app desktop TikTok Poster V2 (`E:/tool/tiktok_poster_v2/src/desktop/app.py:52-62`, `pages/*.py`). Cùng nút, cùng chữ, cùng lỗi gốc. Mở công khai qua đăng nhập web sẵn có.
- Chủ kho bấm thẳng các nút ghi như app gốc: Đăng ngay, Thêm vào Queue, bật/tắt Auto post, xoá, sửa account, Settings. Không qua việc/runner, không nhập mật khẩu từng lần.
- Người dùng chốt thêm (A-PV1b):
  - phạm vi API: "Mở hết /api/v2/";
  - video Loại / hạn mức 100: "Giữ nguyên như app gốc";
  - nút "🔓 Tạo profile & Login lấy cookies": "Giữ, thêm dòng nhắc".
- Điều này đi ngược bốn chỗ đã chốt:
  - D12 đã loại "Trang Đăng bài gọi thẳng API Poster V2 / có nút Đăng ngay", và chốt "video Loại không được đăng";
  - D3 cấm web gửi đường dẫn;
  - D5/D9 bắt việc đăng tốn tiền phải duyệt bằng mật khẩu và giới hạn hạn mức `poster_len_lich` (100 video/ngày/tài khoản);
  - D1 đã loại việc nhồi hàng đợi việc vào `video_server.py`.
- Backend Poster (`127.0.0.1:8023`) là production, có account TikTok thật. Backend chỉ nghe localhost, bắt Bearer token trong `.env`, CORS chỉ cho `:8022`.
- Máy nhà đã có đường vào qua Tunnel `video.kutidak.com` → `tools/video_server.py` (D2). Tunnel cắt request ở khoảng 100 s, trong khi desktop chờ tới 300 s khi đăng và 360 s khi login lấy cookie (`src/desktop/api_client.py:38-43`). Lần đầu `GET /api/v2/folders/` mất khoảng 84 s.
- Backend `post/direct` INSERT dòng `pending` trước khi lấy semaphore rồi trả 429 (`src/core/poster_api.py:73-87`); `queue/{id}/post|run` đưa dòng về `pending` trước semaphore (`src/backend/routers/queue.py:260-275`). Hai lệnh đăng song song để lại dòng `pending` mà scheduler đăng sau.

**Quyết định.**
- **Thay một phần D12:**
  - menu 6 mục → 7 mục;
  - phương án đã loại "gọi thẳng API Poster V2 / Đăng ngay" nay được làm, chỉ trong mục Poster V2;
  - **luật "video Loại không được đăng" không áp cho trang Poster V2** (người dùng chọn "Giữ nguyên như app gốc"). Trang `#/dang` vẫn giữ luật này.
- **Thay một phần D9:** trang Poster V2 là **đường vòng có chủ ý** quanh hạn mức `poster_len_lich` (100 video/ngày/tài khoản, duyệt mật khẩu). Lên lịch / đăng từ trang này không qua hạn mức, không đếm vào sổ của D9. D9 vẫn nguyên với runner/việc.
- **Thay một phần D3:** web gửi đường dẫn và chữ tự do tới backend Poster (không tới runner hay agent).
- Không đổi D5, D7 với runner/việc.

- **Đường đi 3 chặng:**
  1. Trình duyệt → Worker `/api/poster/<rest>`. Worker kiểm phiên, kiểm chủ kho (403 trước mọi lần gọi máy nhà), header `x-pv`, lọc path thô, rồi gọi `${VIDEO_ORIGIN}/p/<rest>` với `x-key` và `x-poster-boi`.
  2. `video_server` tự kiểm `x-key` (sai thì 401 kèm `x-kho-tu-choi: khoa`), lọc path chung, kiểm hợp đồng body, áp chốt riêng, gắn `Authorization: Bearer <TT_API_BEARER_TOKEN>`.
  3. Backend `127.0.0.1:<TT_API_PORT|8023>`.
- **Mở hết `/api/v2/`** (người dùng chọn "Mở hết /api/v2/"): chuyển tiếp mọi path `/api/v2/<…>` và `/health`, method GET/POST/PUT/PATCH/DELETE. Không danh sách trắng. Vẫn giữ:
  - lọc path chung: ký tự `[A-Za-z0-9_.~\-/]`, không `%` (chặn `%2e%2e` và mọi dạng mã hoá), không `\`, không ký tự điều khiển, không `//`, không đoạn `.`/`..`;
  - lọc header: chỉ `Authorization`, `Accept`, `Content-Type` tới backend;
  - body ≤ 256 KB; phản hồi ≤ 4 MB.
  - Bảng "tuyến 9 trang dùng" chỉ để phân lớp timeout S/L/DN và gắn chốt riêng; path ngoài bảng mặc định lớp S.
- **Hợp đồng content-type chung cho 3 chặng:** GET và DELETE không content-type, không body; POST/PUT/PATCH luôn `application/json` với body JSON, rỗng = `{}`. Có test nối 3 chặng cho từng method.
- **Token** đọc ở máy nhà, **mỗi lần gọi**: env trước, sau đó `<KHO_POSTER_DIR>/.env`. Token không bao giờ rời máy nhà và không có secret Worker mới. Dưới test (`pytest` hoặc `KHO_POSTER_TEST=1`), gặp cổng 8023 hay thư mục `E:/tool/tiktok_poster_v2` thì ném lỗi trước khi kết nối.
- **Chốt riêng** (áp theo method + mẫu path, cả path ngoài bảng):
  - B1, tên account: không chứa `/`, `\`, `:`, ký tự điều khiển; khác `.` và `..`. Lý do: `POST /api/v2/accounts/{id}/clean-profile` ghép tên vào đường dẫn rồi `rmtree` (`src/backend/routers/accounts.py:481-505`), tuyến này nay đi qua được;
  - B2, `post/direct` chỉ nhận video nằm trực tiếp trong thư mục của folder;
  - B3, các khoá `path`, `video_path`, `cookies_path`, `chrome_profile_dir`, `duong_dan` phải là đường dẫn có ổ đĩa, không UNC (`\\…`, `//…`, `\\?\…`). Lý do: Windows mở UNC sẽ gửi hash NetNTLM của user tới máy lạ;
  - C1, phản hồi `/api/v2/settings*`: giá trị khác rỗng của khoá chứa `token`/`api_key`/`secret`/`password` đổi thành `"***"`. Desktop cũng không hiện token (ô Password, placeholder "ẩn khi đã lưu").
- **Chống CSRF:**
  - mọi request (cả GET) bắt buộc header `x-pv: 1`, vì có GET ghi dữ liệu (`GET /api/v2/views/health/{id}` ghi `account_health`, `src/backend/routers/views.py:440-447`) và cookie `SameSite=Lax` đi theo điều hướng GET cấp cao;
  - mọi method khác GET bắt buộc `Origin` đúng (thiếu cũng 403); POST/PUT/PATCH bắt buộc `content-type: application/json`.
- **Bảng lệnh chống trùng trong video_server:** mọi lời gọi backend chạy trong luồng có khoá `(method, path?query, sha256(body))`.
  - Trùng khoá đang chạy → gắn vào lệnh cũ (L/DN trả lại đúng `cho` cũ, 202), không gọi backend lần hai.
  - Lớp S chờ 80 s rồi tự chuyển nền (202 `{cho}`); L/DN (đăng, login) nền ngay. Hạn tổng theo đồng hồ monotonic (S 300 s, L 300 s, DN 360 s); video_server luôn trả lời Worker ≤ 85 s.
  - Chỗ chạy: 6 luồng S, **1 lệnh đăng**, 1 lệnh login; bảng tối đa 50 mục, chỉ trong RAM.
  - `GET /_kq` liệt kê lệnh đang chạy; trang Đăng bài/Queue/Accounts gọi khi mở để khoá nút và hỏi tiếp; rời trang chỉ ngừng hỏi.
  - `_video`/`_dem` quét đĩa trong cùng giới hạn luồng S, tối đa 30 s.
- **Mã lỗi:** backend 401 → 502 "token lệch" (không để 401 tới trình duyệt); backend 403 (câu bản quyền, `src/backend/license_guard.py:11-14`) chuyển nguyên. Worker chỉ đổi 401 của máy nhà thành "VIDEO_KEY lệch" khi có header `x-kho-tu-choi: khoa`; 403 chuyển nguyên.
- **Không bước xác nhận thứ hai.** Hộp xác nhận của app gốc là lớp xác nhận duy nhất. Nút login lấy cookie giữ chữ gốc, thêm dòng nhắc "Cần người ngồi ở máy nhà để đăng nhập trên Chrome vừa mở".
- **Nhật ký ai bấm gì:**
  - video_server ghi JSONL cho mọi lệnh ghi vào `%LOCALAPPDATA%\kho-poster-web\nhat-ky.jsonl`, ngoài repo. Mỗi dòng gồm người bấm, method, path, status, thời gian, sha256 body, tên khoá body, cờ trùng; không ghi giá trị body;
  - Worker `console.log` một dòng cho mỗi lệnh ghi.
- Công tắc tắt ở máy nhà: `KHO_POSTER_WEB=0` (đọc mỗi lần gọi).

**Phương án đã loại.**
- Mỗi nút thành một loại việc của runner, có ký Ed25519, duyệt và hạn mức (giữ D3/D5/D9): khoảng 30 loại việc mới, mỗi lần bấm phải chờ runner. Người dùng đã bác ("không qua việc/runner").
- Nhập mật khẩu cho mỗi lệnh ghi: người dùng đã bác.
- Hostname tunnel riêng trỏ thẳng :8023 kèm Cloudflare Access: cần UAC và dashboard (lý do như D2). Ngoài ra token Poster phải đi kèm request từ ngoài vào.
- Worker giữ token Poster: token rời máy nhà, trái hợp đồng.
- Bảng tuyến hẹp 45 tuyến (đề xuất A ở bản A-PV1): người dùng chọn "Mở hết /api/v2/".
- Chặn `batch_schedule`/`post_now` khi folder còn video Loại (đọc `duyet.json`): người dùng chọn "Giữ nguyên như app gốc".
- Chờ đồng bộ tới 300–360 s: Tunnel cắt ở khoảng 100 s (524). Người dùng không thấy kết quả và dễ bấm Đăng lại thành đăng 2 lần.
- Lớp S quá giờ trả 504 "CÓ THỂ đã chạy" (bản A-PV1): người dùng bấm Refresh/bấm lại, chồng lần quét đĩa hoặc ghi lần hai.
- Cho 3 lệnh nền song song (bản A-PV1): hai lệnh đăng cùng lúc để lại dòng `pending` mồ côi ở backend → đăng trùng.
- Đặt bảng lệnh nền trong runner (đúng tinh thần D1): phải qua việc/runner, người dùng đã bác.
- Duyệt thư mục máy nhà từ web cho nút Browse: mặt tấn công mới. Thay bằng gõ đường dẫn + nút Test (`_dem`).

**Hệ quả.**
- Ai chiếm được phiên chủ kho (cookie 30 ngày) là thao tác được account TikTok thật: đăng, xoá, sửa cookie, đổi folder trỏ sang thư mục bất kỳ trên ổ đĩa máy nhà. Chỉ còn `x-pv`/Origin/SameSite, quyền chủ kho, chốt B1–B3 và nhật ký để tra sau.
- **Do mở hết `/api/v2/`**, phiên bị chiếm còn gọi được các tuyến app không dùng:
  - `PUT /api/v2/settings/<khoá bất kỳ>`: đổi giờ ngủ, autopost, `anthropic_api_key`… (C1 chỉ che khi đọc, không chặn ghi);
  - `POST /api/v2/settings/backup-now`, `/settings/drive-reauth`, `/settings/clean-profile-cache`;
  - `POST /api/v2/queue/{id}/run` (đăng ngay 1 item; xếp lớp L nên vẫn chỉ 1 lệnh đăng mỗi lúc);
  - `POST /api/v2/folders/{id}/autogen-captions`, có thể gọi API sinh caption tốn phí nếu `caption_autogen` bật (chưa đọc sâu);
  - `POST /api/v2/accounts/{id}/clean-profile` (có B1).

  Poster V2 thêm tuyến mới thì tuyến đó đi qua ngay, không cần sửa video_server.
- `POST/PUT accounts` nhận `cookies_path` và `chrome_profile_dir` tuỳ ý trên ổ đĩa máy nhà: backend có thể mở Chrome bằng profile Chrome thật của user, hoặc đọc file khác làm cookie. B3 chỉ chặn đường mạng. Desktop cũng vậy.
- **Video Loại và hạn mức (theo lựa chọn "Giữ nguyên như app gốc"):** trang Poster V2 không chặn video Loại và không có hạn mức 100 video/ngày/tài khoản. Video Loại vẫn được `poster_bo_loai` tự dời khỏi folder sau mỗi lần chấm (FX-W8). Lần dời trượt (P1 R-45 còn treo) thì video Loại có thể bị lên lịch hoặc đăng từ trang này. Số video đăng mỗi ngày qua trang này chỉ bị giới hạn bởi chính Poster V2.
- Cùng một việc "lên lịch" giờ có 2 đường với 2 mức kiểm khác nhau: `#/dang` (duyệt, hạn mức, chặn Loại) và Poster V2 (bấm thẳng).
- Autopost/scheduler của Poster và lệnh đăng từ web dùng chung semaphore backend. Khi scheduler đang đăng, `post/direct` từ web vẫn có thể nhận 429 sau khi backend đã INSERT dòng `pending` (hành vi gốc, desktop gặp y vậy). video_server chỉ ngăn được 2 lệnh đăng cùng lúc từ web.
- **video_server giữ bảng lệnh nền trong RAM, đi gần phương án D1 đã loại** ("nhồi queue vào `video_server.py`: lỗi bộ chạy làm sập luôn nút tải video"). Chấp nhận vì: không lưu đĩa; không chạy agent/script/GPU, việc thật do backend Poster làm, video_server chỉ đợi HTTP; tối đa 8 luồng, 50 mục, mỗi mục ≤ 6 phút + 15 phút giữ kết quả; khoá bảng không giữ trong lúc gọi backend; có công tắc `KHO_POSTER_WEB=0`. Rủi ro còn lại: lỗi ở phần này có thể giữ luồng của handler `/p`; video_server khởi động lại thì mất bảng, web nhận 404 ở `_kq` và câu "Xem Logs/Queue".
- Mở tab Accounts gọi `GET views/health/{id}`, GET này ghi `account_health` như khi mở desktop. Kiểm live "chỉ GET" vì vậy vẫn có ghi phụ này.
- Thêm 2 file Python (`poster_web.py`, `poster_noi_gia.py`), 1 module Worker, 11 file web, 7 file test. Móc vào file cũ: `video_server.py` ≤ 20 dòng (nhánh `/p` đặt trước dòng kiểm khoá của `_vao`), `worker.js` 2 dòng, `khung.js` khoảng 8 dòng, `index.html` 11 dòng. 2 test cũ đổi số mục 6 → 7 và regex thứ tự script (`menu-web.test.mjs:403-409`, `homnay-web.test.mjs:325`).
- Khi D13 chốt:
  - D12 ghi thêm "Bị thay một phần bởi D13 (menu 7 mục; gọi thẳng Poster V2 và không chặn video Loại trong mục Poster V2)";
  - D9 ghi thêm "Bị thay một phần bởi D13 (trang Poster V2 không qua hạn mức `poster_len_lich`)";
  - D3 ghi thêm "Bị thay một phần bởi D13 (đường dẫn/chữ tự do tới backend Poster qua `/api/poster/*`)".
- Thiết kế chi tiết và phiếu: `docs/poster-v2-tren-web.md`.

## D14: Ẩn/lưu trữ việc đã kết thúc bằng cờ `luu_tru`, không xoá cứng; phân trang thật cho trang ⚙ Việc  (2026-11-21)
Trạng thái: Đề xuất

**Bối cảnh.**
- Trang ⚙ Việc (`#/viec`) chỉ tải `gioi_han` việc mới nhất mỗi lượt (mặc định 50, tối đa 500, `api.py:82-83`,
  `:659-662`) và không có số trang hay tổng số thật — việc `xong`/`loi`/`huy` dồn lại theo thời gian làm danh sách
  ngày càng dài, không dọn được.
- Người dùng muốn dọn danh sách nhưng **không được xoá cứng khỏi `runner.db`**, vì hai lý do khó đảo ngược đã
  chốt ở D7 và D9:
  - D7: chữ ký duyệt (`chu_ky_duyet`) và sự kiện (`su_kien`) gắn theo `viec.id`; xoá dòng `viec` làm đứt liên kết
    `su_kien.viec_id REFERENCES viec(id)` và `tra_loi.viec_id REFERENCES viec(id)` (khoá ngoại, §4.2), mất cả
    lịch sử "ai duyệt gì, khi nào" mà D7 dựng ra để kiểm tra sau;
  - D9: sổ "lời duyệt đã tiêu" (`SO_DUYET` trên Cloudflare KV) khoá theo `sha256(chu_ky_duyet)`, còn hạn mức ngày
    (`so_lan_tieu`, `tieu_luc_dau`) đếm theo đúng dòng `viec`. Xoá dòng `viec` xong rồi lỡ tạo lại job tình cờ
    trùng `id` (khó nhưng không phải không thể — `id` chỉ là giờ + 4 ký tự ngẫu nhiên, `kho_viec.py:_id_moi`) sẽ
    làm hạn mức/sổ tiêu tính sai hoặc lạc khỏi dữ liệu thật — đúng kiểu lỗi D9 vừa mới vá (R-11 P1-1).
  - Vì vậy "xoá cứng" bị loại ngay từ đầu, không bàn lại.
- Cần phân biệt "ẩn khỏi danh sách cho đỡ rối" với "xoá dữ liệu" — hai nhu cầu khác nhau, không cần đánh đổi an
  toàn của D7/D9 để giải quyết nhu cầu đầu.

**Quyết định.**
- **Cột mới `luu_tru INTEGER NOT NULL DEFAULT 0`** trong bảng `viec` (`runner.db`), nâng schema tại chỗ
  `'3' → '4'` theo đúng khuôn các lần nâng trước (`ALTER TABLE … ADD COLUMN`, không xoá/tạo lại DB, D1/D9 §schema;
  code đã làm ở `tools/runner/kho_viec.py:34-45`, `:236`).
- **`KhoViec.dat_luu_tru(id, luu_tru: bool)`** (`tools/runner/kho_viec.py:414-425`): chỉ cho ẩn/bỏ ẩn khi
  `trang_thai ∈ TRANG_THAI_DONG` (`xong`, `loi`, `huy`); việc còn mở (`cho`/`dang_chay`/`can_tra_loi`/`cho_duyet`)
  bị từ chối (`ThamSoLoi`) — phải huỷ hoặc chạy xong trước. `luu_tru` là **cờ độc lập**, không đi qua CAS của
  `chuyen()` và không đổi `trang_thai`.
- Việc có `luu_tru=1` bị loại khỏi **mọi** kết quả `ds()`/`dem_loc()` (nền của `GET /viec` danh sách), nhưng vẫn
  xem đủ qua `GET /viec/<id>` (tra theo id không lọc `luu_tru`) — ẩn khỏi danh sách, không mất dữ liệu, không mất
  khả năng tra lại khi cần (vd kiểm toán lại một lời duyệt cũ).
- **2 act mới `luu-tru` / `bo-luu-tru`** qua đúng endpoint sẵn có `POST /viec/<id>/<act>`, đi qua **CÙNG** đường
  ký Ed25519 request ghi (§8.3, D7) như `huy`/`chay-tiep`/…, không thêm cơ chế ký riêng — vì đây chỉ là đổi một
  cờ hiển thị, không phải hành động tốn tiền hay ảnh hưởng tiến trình, không cần mức bảo vệ riêng của D9.
- **`GET /viec` (và `GET /api/viec` phía Worker) nhận thêm `offset`** bên cạnh `gioi_han` đã có, trả thêm
  `"tong"` = tổng số việc khớp bộ lọc `trang_thai` hiện tại (đã loại `luu_tru=1`, cùng điều kiện với
  `ds()`/`dem_loc()`), để web tính số trang thật.
- Web (trang ⚙ Việc): phân trang **CỐ ĐỊNH 10 dòng/trang**; mỗi nhóm trạng thái (Cần bạn / Đang chạy / Đang chờ /
  Gần đây) có số trang riêng; trang hiện tại của mỗi nhóm giữ nguyên qua các lần tự làm mới 5 giây.
- **Dừng việc đang chạy KHÔNG phải cơ chế mới.** Vẫn là `POST /huy` đã có từ trước (D6: giết cây tiến trình qua
  Job Object riêng, chuyển `huy`). Thay đổi duy nhất là web thêm nút gọi `huy` ngay trên thẻ việc ở trang danh
  sách (trước đây phải mở trang chi tiết mới thấy nút này).

**Phương án đã loại.**
- **Xoá cứng dòng `viec` (và dọn `su_kien`/`tra_loi` theo)**: phá khoá ngoại và lịch sử duyệt mà D7 dựng ra; có
  thể làm hạn mức/sổ tiêu của D9 tính sai nếu `id` bị tái dùng sau này. Người dùng đã chốt không làm theo hướng
  này.
- **Xoá mềm bằng cách gài `trang_thai` riêng (vd `'an'`) thay vì cột cờ**: phá `CHECK` constraint hiện có của
  `trang_thai` và mọi chỗ coi `trang_thai ∈ TRANG_THAI_DONG` là "đã kết thúc" (đối soát D6, hạn mức D9); phải sửa
  rất nhiều nơi để phân biệt "đã kết thúc" với "đã kết thúc và bị ẩn". Cờ độc lập (`luu_tru`) không đụng gì trong
  số đó.
- **Tự động ẩn theo tuổi (vd ẩn mọi việc đã xong quá N ngày) thay vì người dùng bấm**: người dùng có thể còn cần
  nhìn lại việc cũ (vd đang tra một lời duyệt tháng trước); ẩn tự động xoá mất lựa chọn đó. Giữ hành động bấm tay,
  bỏ-ẩn-được bất cứ lúc nào.
- **Phân trang kiểu "tải thêm" dựa vào con trỏ `id`/`tao_luc` cuối trang trước** (không cần `tong`): đơn giản hơn
  cho API, nhưng không cho web biết "còn bao nhiêu trang" để vẽ số trang theo đúng yêu cầu (phân trang CỐ ĐỊNH 10
  dòng, có số trang riêng từng nhóm) — người dùng đã chốt kiểu có số trang, không phải "tải thêm".

**Hệ quả.**
- `runner.db` không giảm dung lượng theo thời gian (dữ liệu vẫn còn, chỉ ẩn) — đây là đánh đổi có chủ ý để giữ
  được bằng chứng ký/duyệt của D7/D9; dọn dung lượng thật (nếu cần sau này) phải là một quyết định khác, riêng.
- Mọi nơi đang gọi `kho.ds()`/`dem_loc()` tự động loại việc đã ẩn mà không cần sửa logic gọi (lọc nằm trong
  `_dieu_kien_ds`, dùng chung cho cả hai hàm) — rủi ro quên lọc ở một đường gọi mới trong tương lai nếu có người
  viết thêm hàm đọc danh sách riêng không đi qua `_dieu_kien_ds`.
- Thêm 2 act vào mọi nơi đang liệt kê "các act ghi tới `/viec/<id>`" (regex allowlist của `video_server.py`,
  route Worker, bảng API) — bỏ sót một chỗ thì act mới bị 404 ở đúng chỗ đó, không chạy được, không có rủi ro bảo
  mật (an toàn hơn so với sót ngược — không lọt được việc không nên làm).
- Web cần giữ "trang hiện tại" riêng cho từng nhóm trạng thái qua các lần tự làm mới 5 giây; nếu không giữ, người
  dùng đang đọc trang 2 của nhóm Gần đây sẽ bị bật về trang 1 mỗi 5 giây — khó dùng. Đây là ràng buộc UI cần nhớ,
  không phải vấn đề của API.
- Không đổi D1, D3 (phần còn hiệu lực), D5, D6, D7, D9 (phần còn hiệu lực) — D14 chỉ thêm một cờ và hai act đi
  qua đúng cơ chế đã có, không mở đường chạy lại việc tốn tiền và không đổi cách ký/duyệt.

## D15: Học tự động mỗi ngày bằng 2 việc runner tự hẹn giờ (`quet_view_hang_ngay` 09:00, `hoc_hang_ngay` 12:00); nguồn hiệu suất là view video của mình trong DB Poster V2; chỉ học đặc trưng caption + mẫu lỗi vận hành; bài học là khoá danh mục cố định, tự áp vào phiếu `phan_tich_uid`, hoàn tác/bật lại qua đường ký D7  (2026-11-22)
Trạng thái: Đã chốt (2026-11-22, người dùng: 'Duyệt, giao code')
(Lịch sử: Đề xuất, sửa theo phản biện A-HT1b ngày 2026-11-22; người dùng chốt Q-nguồn view, Q-học cái gì, Q1–Q6 rồi Q7, Q8 cùng ngày, xem dưới; chuyển "Đã chốt" ở phiếu A-HT1c. Phiếu HT-D1 ngày 2026-11-23 đồng bộ tài liệu với code và ghi các bổ sung kỹ thuật của trưởng phòng sau review R-CUOI, xem cuối mục Quyết định. Phiếu HT-D1b ngày 2026-11-23 sửa các câu chưa khớp code: biên snapshot 74 ngày, hai tập động từ `cap_menh_lenh`, điều kiện `vao_phieu`.)

**Bối cảnh.**
- Hợp đồng người dùng (phiếu A-HT1):
  - một việc tự động mỗi ngày trong runner, học từ 3 nguồn (hiệu suất qua Breakout Radar, sửa tay của nhân viên, lỗi vận hành lặp);
  - **tự** cập nhật gợi ý mặc định ("mẫu USP + công thức caption ưu tiên") cho lần phân tích sản phẩm mới, không duyệt từng lần;
  - có cỡ mẫu tối thiểu, lịch sử, nút hoàn tác trên web, báo cáo hằng ngày;
  - không thêm nguồn trả phí, không lộ dữ liệu nhạy cảm, không dựng hệ thống chạy ngầm riêng.
- **Người dùng chốt ngày 2026-11-22:**
  - **Q-nguồn view:** lên lịch tự quét view hằng ngày. Nới ràng buộc "không gọi thêm API TikTok" **riêng** cho lượt quét view video của chính mình (trước đây chạy tay bằng `C:\Users\Mi\view-poster\bao_cao_view.py`);
  - **Q-học cái gì:** chỉ học đặc trưng caption (7 khoá); USP chỉ ở mức `cap_nhac_usp`; không sửa skill. Đây là **phần thu hẹp** của hợp đồng "mẫu USP + công thức caption ưu tiên", người dùng đã đồng ý;
  - **Q1:** bỏ nguồn sửa tay đợt này;
  - **Q5:** giữ ngưỡng 20 SP / 70% / 15% / 3 ngày (câu trả lời lúc đó; ngưỡng cùng chiều sau đó đổi bởi Q7);
  - **Q2, Q3, Q4, Q6:** theo khuyến nghị (a): view video của mình thay Radar, chỉ học theo view, chấp nhận lần phân tích chạy tay không nhận gợi ý, khối trong Hôm nay + trang `#/hoc`;
  - **Q7** (mở lại vì con số 5,8% lúc chốt Q5 sai, đúng là 9–12% mỗi khoá mỗi ngày): "Nâng lên 80% (Recommended)" → `nhat_quan_toi_thieu_pt` 70 → **80** (≥ 16/20 cùng chiều; ngẫu nhiên hai phía khoảng 1,2%);
  - **Q8:** "Cho trong 7 ngày (Recommended)" → bài học do người Hoàn tác được Bật lại trong 7 ngày sau khi hoàn tác, cùng đường ký D7, chỉ chủ kho, bỏ lệnh cấm 30 ngày của dòng đó; quá 7 ngày thì không;
  - **Duyệt thiết kế:** "Duyệt, giao code".
- **Trưởng phòng quyết** cùng ngày: (i) bài học tự tắt hoặc hết hạn có nút "Bật lại", đi đường ký D7, chỉ chủ kho, vẫn tôn trọng hạn dùng và ngưỡng giữ; (ii) người dùng chủ động chạy lại `phan_tich_uid` cho UID cũ thì vẫn nhận gợi ý.
- Đo trên dữ liệu thật ngày 2026-11-22 (`docs/hoc-tu-dong.md` §2, Phụ lục A):
  - Radar không nối được về UID kho (0/26.850 alert);
  - `video_view_snapshots` của Poster có 1.528 video từ 19/11, do `ghi_view_poster.py` ghi. Script này **chép số cũ** cho video không được quét lại (video 7–14 ngày tuổi: 50–100% dòng giống hôm trước); `queue` có 50 `video_id` lặp; view trung vị theo tài khoản chênh tới 13 lần;
  - chuỗi quét (`tiktok_scan.py` → yt-dlp `--impersonate chrome`) **không đăng nhập, không cookie, không Chrome**; 4 kênh quét dưới 2 phút. Nhưng chuỗi này thoát mã 0 khi kênh lỗi, vẫn ghi DB khi kênh lỗi, không có giới hạn giờ, và gọi Apify tốn phí chỉ cần một dòng cấu hình (token có sẵn trên máy);
  - runner không có cơ chế hẹn giờ; Task Scheduler đã có pipeline Radar 08:00 (`CapNhatTuanTikTokDaily`, mutex `Global\QuetKenhAntiPipeline`);
  - nguồn "sửa tay" không tồn tại; 76% lần phân tích đi qua runner.
- Rủi ro riêng: chữ không tin cậy (caption, tiêu đề TikTok, tên kênh, log) chảy vào phiên `claude -p` có Bash; tự áp dụng không duyệt; lệnh ghi từ web; test chạm DB thật.

**Quyết định.**
- **Hẹn giờ trong runner, không Task Scheduler:** `BoChay(hen_gio=...)` kiểm trong vòng làn `nhe` có sẵn, tạo việc `quet_view_hang_ngay` từ 09:00 và `hoc_hang_ngay` từ 12:00 giờ VN, mỗi loại 1 việc/ngày, khoá = ngày. Hẹn giờ **chỉ bật khi thư mục runner là `E:\kho-runner`** (test với thư mục tạm không bao giờ tạo việc hẹn giờ). Cả hai việc chỉ runner tự tạo; `api._tao_viec` từ chối khi web tạo mới. Riêng `quet_view_hang_ngay` cho phép chủ kho Chạy lại lượt **của hôm nay**.
- **Việc quét view `quet_view_hang_ngay`** (làn `nhe`, miễn phí, không Claude): một bước `python -m runner.quet_view` bọc chuỗi quét sẵn có, **không sửa** script ngoài:
  - từ chối nếu `channels.json` có `source` khác `yt-dlp` hoặc có `maxItems` (chặn Apify), hoặc file cấu hình yt-dlp có cookie;
  - mỗi kênh có giới hạn giờ, giết cả cây khi quá giờ; kênh chỉ tính là ổn khi có dấu hiệu quét thật (dòng "✓", `raw` mới ghi, `fetched_at`, `last_seen`);
  - **tất cả kênh ổn mới chạy `ghi_view_poster.py`**; `bao_cao_view.py` chỉ chạy với `--khong-quet --khong-ghi` để giữ báo cáo md;
  - ghi trạng thái trước khi gọi mạng; tối đa 3 lần/ngày; đã quét ổn thì không quét lại;
  - hoãn khi pipeline Radar giữ mutex hoặc đang có lần chạy tay;
  - stdout của việc chỉ có 1 dòng JSON mã + số.
- **Việc học `hoc_hang_ngay`** (làn `nhe`, không mạng): `python -m runner.hoc_tu_dong`, chờ việc quét cùng ngày đóng (tới 18:00).
- **Nguồn:**
  - hiệu suất = view video của mình, đọc `mode=ro` từ `v2_data.db`, **chỉ dùng lần đo thật** (bỏ bản chép), view chuẩn ở tuổi [3, 7] ngày, video ≥ 7 ngày tuổi, đăng trong 60 ngày;
  - nối theo cặp (video_id, product_id); caption chuẩn hoá (NFC, bỏ số thứ tự, bỏ hashtag) rồi chỉ dùng caption khớp `captions.txt` của chính UID;
  - vận hành = `runner.db` `mode=ro`, chuỗi cố định do runner sinh;
  - sửa tay: bỏ đợt này (Q1), báo "chưa có nguồn sửa tay".
- **Phương pháp:** chỉ 7 khoá đặc trưng caption + 5 khoá vận hành, danh mục cố định trong code. So trong nhóm (UID, tài khoản), đếm theo **caption khác nhau**, trung vị log, gộp về UID; `nhat_quan` = % UID cùng chiều.
- **Lưu trữ:** SQLite riêng `E:\kho-runner\hoc.db`; `KhoHoc` theo mô hình luồng của `KhoViec`; nâng schema chỉ ở `mo()` sau mutex. Chế độ `--chi-doc` mở `mode=ro`, không gọi `mo()`, không ghi gì.
- **Luật tự áp dụng (caption):** bật khi ≥ 20 SP, ≥ 200 video, |lệch| ≥ 15%, **≥ 80% SP cùng chiều** (Q7), đạt **3 ngày lịch liên tiếp có dữ liệu mới**; giữ khi ≥ 60%; hạn 14 ngày gia hạn khi còn giữ.
- **Luật vận hành:** bật khi ≥ 3 lần và ≥ 20% trong 14 ngày, 3 ngày liên tiếp; hạn **cố định 28 ngày**, không tự tắt vì hết bằng chứng (cắt vòng phản hồi nhắc → lỗi giảm → tắt).
- **Chung:** ≤ 1 lần tự bật/ngày, ≤ 5 bài hiệu lực; tự dừng **theo từng nguồn** (nguồn view chưa có số mới hôm nay, lượt quét thiếu, nối lệch); ngày tự dừng không tính vào chuỗi. **Hết hạn xét cả lúc đọc**: bài quá `het_han_luc` không vào phiếu dù bộ học lỗi nhiều ngày. Hoàn tác cấm học lại cùng khoá + hướng 30 ngày; cấm tính từ dòng đang ở `hoan_tac`, nên dòng được chủ kho Bật lại (Q8) thì hết gây cấm.
- **Trần trong `HAN_MUC_TRAN`** (`cau_hinh.json` chỉ hạ): `hoc_bat_ngay` 1 (0 = **cầu dao**: tắt tự bật **và tắt hẳn gợi ý vào phiếu**, kể cả bài đang hiệu lực; vẫn đo, vẫn báo cáo, không Bật lại được), `hoc_hieu_luc_toi_da` 5 (0 = không bài nào vào phiếu), `quet_view_ngay` 3 (0 = tắt lịch quét). Runner đọc `cau_hinh.json` **một lần lúc khởi động**: sửa xong phải khởi động lại runner; file hỏng thì quay về trần code (cầu dao và lịch quét bật lại), là giới hạn đã biết của luật hạn mức chung.
- **Đưa vào phiên phân tích:** khối ≤ 6 dòng trong `them` của phiếu `phan_tich_uid`, ghép từ mẫu câu cố định + số nguyên đã kiểm. Không sửa `SKILL.md`. Bộ học không tự đụng SP cũ; phân tích do người chủ động chạy lại thì vẫn nhận gợi ý. Ghi vết `ap_dung` bọc lỗi, không làm hỏng phân tích.
- **API:** runner `GET /hoc/bao-cao`, `GET /hoc/bai-hoc`, `POST /hoc/bai-hoc/<ma>/hoan-tac`, `POST /hoc/bai-hoc/<ma>/bat-lai`. Qua video_server `RE_R` và Worker `/api/hoc/*` (chủ kho, Origin bắt buộc, Worker tự dựng `{boi}`, **ký Ed25519 D7**). `ma` sai dạng = 404 ở cả 3 chặng. Bật lại chỉ cho (a) bài đã từng hiệu lực rồi tự tắt/hết hạn, hoặc (b) bài do người hoàn tác khi hôm nay (giờ VN) ≤ ngày hoàn tác + 7 (Q8; ngày thứ 8 trở đi → 409 câu cố định); và phải còn chỗ, không có dòng mở cùng khoá, tự áp dụng đang bật. Bài hoàn tác lúc đang/đã từng hiệu lực trở về `hieu_luc` với hạn mới; bài hoàn tác lúc còn ứng viên trở về `ung_vien`, không đi tắt qua luật 3 ngày.
- **Web:** khối "📈 Học hôm nay" (cảnh báo đỏ khi nguồn view cũ > 1 ngày, vàng khi quét hôm nay lỗi) + trang `#/hoc`; nhãn 2 loại việc mới trong `web/loi.js`, `web/viec.js`. Không thêm menu.
- Thiết kế chi tiết, phiếu HT-B1…HT-T1 (gồm HT-A3 cho lượt quét), hành động cần duyệt: `docs/hoc-tu-dong.md`.
- Không thay quyết định nào. Mở rộng nguyên tắc D3: phiếu chỉ nhận thêm chữ từ danh mục cố định.
- **Bổ sung kỹ thuật sau review R-CUOI** (trưởng phòng quyết, 2026-11-23; không đổi quyết định nào của người dùng; chi tiết `docs/hoc-tu-dong.md` Phụ lục C):
  - Khoá vận hành `ap_phieu=False` (`voice_pv_ma_2`, `douyin_qua_gio`, `taovideo_tu_thoat`) **không bao giờ tạo dòng `bai_hoc`**; chỉ đo và hiện trong `canh_bao_van_hanh`. Không tính vào lượt tự bật/ngày hay trần 5 bài hiệu lực.
  - Báo cáo `/hoc/bao-cao` thêm `"han_muc": {"bat_ngay", "hieu_luc_toi_da"}` (hạn mức hiệu lực runner đang giữ); mỗi bài `hieu_luc` có `"vao_phieu": bool`, true chỉ khi bài thuộc đúng danh sách phiếu sẽ nhận **và** còn ghép được câu gợi ý (`hoc_danh_muc.ghep_goi_y` không `None`; cùng điều kiện chọn bài với `goi_y_hieu_luc`, bổ sung phiếu HT-D1b). Web hiện "Gợi ý học đang TẮT" khi `bat_ngay = 0` và không ghi "Đang dùng" cho bài `vao_phieu = false` (`hoc.js?v=3`).
  - Mẫu câu gợi ý caption: không còn quota cứng "ít nhất N" (dạng "nếu sản phẩm có … thì ưu tiên khoảng N/100"); `cap_co_so` thêm "không mở đầu dòng bằng con số"; `cap_nhac_usp` lồng cụm USP vào câu, không lặp nguyên vế (tránh va `tools/kho.py` `kiem_captions`). `cap_menh_lenh` có hai tập động từ (bổ sung phiếu HT-D1b): tập **ĐO** `hoc_danh_muc.DONG_TU_MENH_LENH` (`mua, đừng, thử, xem, săm, chốt, lưu, tậu`) giữ nguyên để số đo cũ so được với số mới, đặc trưng dùng regex `lưu(?! ý)`; tập **GỢI Ý** `hoc_danh_muc.DONG_TU_GOI_Y_MENH_LENH` chỉ `thử, xem, lưu` (bỏ nhóm hối thúc mua và "đừng"), mẫu chiều tăng thêm "không dùng 'ngay', 'kẻo hết', 'đừng bỏ lỡ'". Đánh đổi đã chấp nhận: lift đo trên cả nhóm động từ (gồm động từ mua) nhưng chỉ khuyên tập con; lift mất thì bài tự tắt theo ngưỡng giữ.
  - `hoc_tu_dong` lọc `video_view_snapshots` theo `collected_at` ngay trong SQL, biên `[ngay − SNAP_LUI_NGAY, ngay]`, `SNAP_LUI_NGAY` = 74 = 60 (cửa sổ đăng) + 7 (tuổi đo tối đa) + 7 (cửa sổ trung vị `poster_thieu`); bảng `queue` chỉ đọc dòng có `video_id` còn snapshot trong biên (truy vấn con `IN (SELECT … collected_at …)`). Biên rỗng thì chạy thêm `SELECT MAX(collected_at)` để vẫn báo `ngay_moi_nhat`/`so_ngay_cu`. SQLite vẫn SCAN toàn bảng (không index `collected_at`; DB Poster mở chỉ đọc nên không tạo index), chỉ dòng trong biên lên Python: P3 chấp nhận. Đọc `runner.db` theo khoảng ngày trong SQL, trần 200.000 dòng, chạm trần thì bỏ phần cũ nhất và báo `bi_cat`.
  - video_server không nới `R_QUERY_KHOA` chung; mỗi tuyến `/r/hoc/*` có method + khoá query riêng (`R_HOC`, `R_HOC_GHI`).

**Phương án đã loại.**
- Dùng Breakout Radar làm nguồn hiệu suất: không nối được alert về sản phẩm của kho (đo 0/26.850). Học từ đó là học hiệu suất video của người khác.
- Dùng `post_metrics_snapshots` của Poster: chụp ngay lúc đăng, view = 0 ở 4.158/4.608 video.
- Cho Claude đọc dữ liệu rồi viết "bài học" bằng chữ tự do vào phiếu sau: đường prompt injection từ caption hoặc tiêu đề tới agent có Bash; tốn tiền mỗi ngày; không kiểm được ngưỡng.
- Lưu bài học trong repo (`data/_hoc/…`) và hoàn tác bằng Worker commit GitHub: lệnh ghi không qua runner/D7; thêm commit mỗi ngày và xung đột với `kho.py` pull/autostash; runner phải tin dữ liệu repo mà mọi phiên web có quyền ghi.
- Thêm bảng vào `runner.db`: buộc nâng schema `runner.db`, trong khi bản cài đang ở 3 và D14 (schema 4) còn Đề xuất; lỗi bộ học có thể đụng hàng đợi việc.
- Cron Worker hoặc **Task Scheduler** riêng để kích bộ học hay lượt quét: trái ràng buộc "không dựng hệ thống chạy ngầm riêng"; chạy ngoài mutex runner nên không xếp hàng được với việc khác của làn `nhe`, không có đối soát khởi động lại D6, không hiện trên trang Việc. Runner đã có vòng làn chạy liên tục nên không cần.
- **Lên lịch thẳng `bao_cao_view.py`** (Task Scheduler hoặc bước script runner): kênh lỗi vẫn ghi số cũ với ngày hôm nay, không giới hạn giờ, Apify tốn phí bật được bằng một dòng `channels.json`. Không an toàn khi không người canh.
- **Sửa `tiktok_scan.py` / `ghi_view_poster.py`** để thêm các kiểm: mã ngoài repo, thuộc skill và thư mục cá nhân của người dùng, ngoài phạm vi; bọc bên ngoài đủ chặn mà không đụng chúng.
- Dùng mọi snapshot (kể cả bản chép) với view gần tuổi 7 trong [3, 21] (bản đầu của D15): lẫn số cũ mang ngày mới, đo sai tuổi.
- Ghi bài học từ một lần chạy `--chi-doc` (bản đầu): làm việc thật cùng ngày ra `da_hoc` và mất ngày học.
- Sửa `SKILL.md` của `phantichcanhquay` để đọc gợi ý: phải sửa skill và mở đường "file trên đĩa → agent" (Q4 đã chốt không làm).
- Học "mẫu USP" ở mức sản phẩm: chỉ 30 SP đủ dữ liệu, lẫn khác biệt ngành hàng; người dùng đã chốt chỉ học caption.
- Luật "giữ theo bằng chứng" cho bài học vận hành: tạo vòng bật/tắt vì nhắc có tác dụng thì lỗi giảm.
- Ngưỡng nhỏ hơn (12 SP, 65%, 2 ngày): xác suất ngẫu nhiên vượt điều kiện cùng chiều hai phía khoảng 39% (≥ 8/12) so với 11,5% (≥ 14/20).
- Giữ cùng chiều 70% như lúc chốt Q5 (Q7 a): khoảng 9–12% mỗi khoá mỗi đợt dữ liệu đạt nhầm, 3 ngày liên tiếp gần như không giảm; người dùng chọn nâng 80%.
- Giữ 70% nhưng đòi khẳng định lại trên dữ liệu không chồng (Q7 c): phức tạp hơn, chậm thêm 1–2 tuần.
- Không cho Bật lại bài đã hoàn tác (Q8 a): bấm nhầm Hoàn tác phải chờ 30 ngày cấm; người dùng chọn cho bật lại trong 7 ngày.
- Cho khoá vận hành "chỉ báo cáo" thành bài học như khoá khác (bản code đầu, R-CUOI P1-1): bài không bao giờ vào phiếu nhưng chiếm lượt tự bật và chỗ trong trần 5 bài, chặn bài thật.
- `hoc_bat_ngay = 0` chỉ tắt tự bật, bài đang hiệu lực vẫn vào phiếu (bản tài liệu đầu): không có cách tắt nhanh mọi gợi ý khi nghi học sai; chọn cầu dao tắt hẳn.
- Mẫu gợi ý dạng quota cứng "viết ít nhất N caption …" (bản đầu): ép agent bịa số khi sản phẩm không có, và lặp nguyên vế va luật `kiem_captions` của `kho.py`.
- Nới `R_QUERY_KHOA` chung thêm `ngay` (bản tài liệu đầu): khoá mới đi qua mọi tuyến `/r/*`; khoá riêng từng tuyến hẹp hơn (D2).
- Đọc lại `cau_hinh.json` mỗi lần dùng thay vì lúc khởi động: phải đổi luật hạn mức chung của mọi loại việc, ngoài phạm vi D15; giữ luật chung, ghi rõ phải khởi động lại.

**Hệ quả.**
- Lượt quét gọi trang công khai TikTok mỗi ngày một lần (4 kênh, không đăng nhập), ghi `v2_data.db` và thư mục `C:\Users\Mi\view-poster` như lần chạy tay. Bộ học không gọi mạng, không tốn tiền, không Claude.
- Một kênh lỗi kéo dài làm cả 4 kênh mất số hằng ngày cho tới khi người sửa (đổi lại: không bao giờ ghi số chép). Web báo đỏ khi nguồn view cũ > 1 ngày.
- Chạy mã ngoài repo (`tiktok_scan.py`, script `view-poster`) ngoài kiểm soát D8, như tiền lệ `radar_ban_tin`. Đổi định dạng output thì lượt quét báo lỗi (an toàn), không ghi sai.
- Luật lấy số chặt làm dữ liệu dùng được hôm nay chỉ còn 247 video / 47 SP. Bài học caption đầu tiên khó có trước **giữa tháng 12/2026**, có thể không có nếu hiệu ứng không đều (độ cùng chiều hiện 50–67%).
- **Xác suất học nhầm** với ngưỡng 80% (Q7): cận trên nhị thức hai phía khoảng 1,2% mỗi khoá đủ cỡ mẫu mỗi đợt dữ liệu (khoảng 3,6% khi 3 khoá cùng đủ cỡ mẫu); chưa mô phỏng hoán vị lại ở 80%. 3 ngày liên tiếp gần như không giảm thêm, vì dữ liệu các ngày chồng nhau > 90%. (Ở ngưỡng 70% cũ là 9–12%; con số 5,8% của bản đầu là một phía, sai.) Đổi lại bài học caption tới chậm hơn hoặc không tới. Lưới an toàn: gợi ý mềm, hạn dùng, ngưỡng giữ, Hoàn tác, Bật lại trong 7 ngày nếu bấm nhầm.
- Bật lại sau hoàn tác (Q8) thêm 1 câu 409 cố định (tổng 5), trường `bat_lai_den` trong `BaiHocRa`, hằng `bat_lai_sau_hoan_tac_ngay = 7`; chữ ký `KhoHoc.bat_lai` không đổi.
- Khoảng 24% lần phân tích chạy tay ngoài runner không nhận gợi ý (Q4).
- Agent cùng user Mi có thể sửa `hoc.db` (như rủi ro D7): chỉ bật/tắt được câu soát sẵn. `hoc.db*` và `quet_view/**` thêm vào phần cấm của thư mục runner.
- Thêm 4 module runner, 1 module Worker, 1 file web, 7 file test; móc vào 10 file cũ. Cần: tắt lịch quét tạm thời, cài runner, chạy thử lượt quét 1 lần, chạy thử bộ học `--chi-doc`, bật lịch, khởi động lại video_server, deploy Worker. Mọi bước đều cần duyệt.
- **Cài D15 kéo theo D14 ở cả 3 tầng** (runner schema 3 → 4 + act mới, video_server, Worker/web). Lần deploy Worker cuối ghi nhận là trước D14. D14 phải được duyệt trước.
- Mỗi lần đổi mẫu câu, ngưỡng hay giờ hẹn là đổi code, review và cài lại (D8).
- Tắt/bật cầu dao gợi ý hoặc lịch quét bằng `cau_hinh.json` chỉ có tác dụng sau khi khởi động lại runner; khởi động lại sau 09:00 với lịch quét đang bật thì việc quét của hôm nay được tạo ngay. `cau_hinh.json` hỏng thì runner dùng trần code (cầu dao và lịch quét bật lại) kèm cảnh báo `/suc-khoe`; người tắt phải kiểm cảnh báo này.
- Còn 10 việc P3 treo (báo cáo/log kém chính xác, không làm sai bài học vào phiếu): `docs/hoc-tu-dong.md` §12a.
