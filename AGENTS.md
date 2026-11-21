# AGENTS.md

Web "Kho sản phẩm" (Cloudflare Worker) + bộ chạy việc trên máy nhà, phục vụ quy trình affiliate TikTok Shop
(`/phantichcanhquay`, `/tao-video-tu-canh-quay`). Đọc `README.md` trước: cài đặt, lệnh, cấu trúc dữ liệu `data/`.

## Đi tìm đúng chỗ trước khi sửa

- **Đặc tả sống** (nguồn sự thật cho hành vi — không phải chỉ comment code): `docs/bo-chay-viec.md` (bộ chạy việc,
  trang ⚙ Việc ↔ `web/viec.js`), `docs/giao-dien-menu-trai.md`, `docs/poster-v2-tren-web.md`, `docs/sua-video.md`.
  Đổi hành vi mà không cập nhật đặc tả tương ứng = chưa xong việc.
- `web/` — giao diện tĩnh. CSP `script-src 'self'`: **không** inline `<script>`/`on…=`, gắn sự kiện bằng
  `addEventListener`.
- `cf/src/worker.js` — API đăng nhập + đọc/ghi repo qua GitHub API (chạy trên Cloudflare Workers).
- `tools/` — script máy nhà (`kho.py`, `video_server.py`...); `tools/runner/` — bộ chạy việc (phiên Claude sống,
  duyệt việc tốn tiền, hạn mức, hàng đợi).
- `.culiapp/` — nhật ký & bảng phiếu của Phòng Kỹ sư Culiapp (`bang-viec.json`, `nhat-ky.md`, `de-xuat-K1-K2.md`).
  Đây LÀ state tracking thật của dự án — đọc trước khi bắt tay, nối tiếp vào đó, không tạo bảng/nhật ký song song.

## Làm việc code

- Việc vừa/lớn (đụng nhiều hệ: web + Worker + runner, hoặc nhiều file): giao cho skill `/culiapp` (Phòng Kỹ sư
  Culiapp) — chia phiếu, review có bằng chứng, ghi vào `.culiapp/`.
- Việc nhỏ (1 file, ≤2 chỗ sửa): sửa trực tiếp; nếu đổi hành vi người dùng thấy được thì vẫn thêm 1 dòng vào
  `.culiapp/nhat-ky.md`.

## Kiểm chứng trước khi báo xong

- Lệnh gốc: `python .culiapp/kiem-chung.py` (= `init.sh`) — chạy cả 3 bước: JS (`node --test cf/test/*.test.mjs`),
  Python chính (pytest nhiều file `tools/test_runner_*.py`...), và engine sửa video (venv riêng ở
  `F:/auto video oneshot/.venv`). Đổi/thêm file test thì cũng thêm tên file vào mảng `LENH` trong
  `.culiapp/kiem-chung.py`, không chỉ chạy lẻ rồi báo xong.
- Sửa riêng `web/viec.js` → có thể chạy nhanh `node --test cf/test/viec-web.test.mjs` trước, nhưng vẫn phải
  chạy `kiem-chung.py` đầy đủ trước khi báo xong.
- Không tự ý `npx wrangler deploy` hay khởi động lại runner trên máy thật — đó là bước **tích hợp** cần người
  dùng duyệt riêng (xem `.culiapp/nhat-ky.md`, mục "TÍCH HỢP").

## Bất biến quan trọng

- Việc tốn tiền (`muse_clip`, `voice_genmax`, `poster_len_lich`, `taovideo` — xem `LOAI_TON_TIEN` trong
  `web/viec.js` và `tools/runner/danh_muc.py`) phải qua duyệt lại mật khẩu; không tự chạy hay bỏ qua bước duyệt.
- Không đoán/tự chọn ngầm tham số nhạy cảm (watermark, giá, tài khoản đăng...) — thiếu thì báo lỗi rõ, không
  mặc định âm thầm.
- Tiếng Việt là ngôn ngữ chính của tên biến/hàm/tài liệu trong repo này — giữ nguyên quy ước khi sửa.
