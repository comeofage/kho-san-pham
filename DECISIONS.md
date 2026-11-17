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
