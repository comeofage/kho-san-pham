# Kho sản phẩm

Web lưu link sản phẩm TikTok Shop, dùng chung cho `/phantichcanhquay` và `/tao-video-tu-canh-quay`.
Chạy trên **Cloudflare Workers** (`cf/`), mở được từ bất kỳ đâu (điện thoại, máy khác).
Phải **đăng nhập bằng tài khoản riêng** (user/pass) mới xem và sửa được. Worker giữ token GitHub, nhân viên không cầm token.
Dữ liệu vẫn nằm trong repo này (`data/`), nên `tools/kho.py` trên máy nhà dùng như cũ.

## Luồng làm việc

1. **Dán link** lên web (hoặc gửi link cho Claude trên máy nhà) → sản phẩm vào trạng thái **Chờ xử lý**.
   UID đã có trong kho thì web báo trùng.
2. Trên máy nhà, nói với Claude **"xử lý link mới trong kho"** → Claude chạy `kho.py cho`, rồi với từng link:
   `/phantichcanhquay` → file 01 + dữ liệu SP + USP + 100 caption → `kho.py ghi` → **Đã phân tích**.
3. Nhân viên mở web, đọc **Bộ cảnh quay** để quay. Quay xong thì gạt **"Oneshot"** hoặc **"Review"** (web ghi tên + giờ) → **Đã quay**.
4. Làm video: tab **🎞 Làm video** → bấm **Copy cho Claude** và dán vào Claude trên máy nhà. `/tao-video-tu-canh-quay`
   tự kéo caption từ kho, xong thì chạy `kho.py video` → **Đã làm video**.

## Cài đặt / vận hành web (thư mục `cf/`)

```
web/            giao diện (index.html, app.js, style.css) — Worker phục vụ dưới dạng file tĩnh
cf/src/worker.js  đăng nhập + API /api/* đọc/ghi repo qua GitHub API
cf/wrangler.toml  cấu hình Worker (tên repo GH_REPO, nhánh GH_BRANCH)
```

Secret của Worker (đặt bằng `npx wrangler secret put <TÊN>` trong `cf/`, không ghi vào file):

| Secret | Là gì |
|---|---|
| `GITHUB_TOKEN` | Fine-grained token: chỉ repo `kho-san-pham`, **Contents: Read and write** |
| `SESSION_SECRET` | Chuỗi ngẫu nhiên dài. Đổi giá trị → mọi người bị đăng xuất |
| `USERS` | Danh sách tài khoản, mật khẩu đã băm (sinh bằng lệnh dưới) |

```bash
cd E:/phantichcanhquay/kho-san-pham/cf
npx wrangler login                                   # lần đầu: tự đăng nhập Cloudflare trên trình duyệt
npx wrangler deploy                                  # đưa web lên (sửa web/ hay cf/src/ xong thì chạy lại)
# Thêm / đổi / xoá tài khoản: liệt kê ĐỦ mọi tài khoản mỗi lần (lệnh ghi đè cả danh sách)
node tools/tao-users.mjs "nhan:<mật khẩu>:Nhân" "thu:<mật khẩu>:Thu" "linh:<mật khẩu>:Linh" | npx wrangler secret put USERS
```
Xoá một người khỏi `USERS` → phiên đăng nhập của người đó hết hiệu lực ngay.

Test Worker: `node --test cf/test/worker.test.mjs` · chạy thử local: tạo `cf/.dev.vars` (USERS=…, SESSION_SECRET=…) rồi `npx wrangler dev` trong `cf/`.

## Lệnh máy nhà

```bash
export PYTHONIOENCODING=utf-8
K=E:/phantichcanhquay/kho-san-pham/tools/kho.py
python $K them "<link>"                       # lưu link
python $K cho                                 # link đang chờ phân tích
python $K ds --trang-thai da_quay             # sản phẩm đã quay, chưa làm video
python $K ghi <UID> --tu <thư mục dự án>      # đẩy file 01 / caption / USP / ảnh lên kho
python $K lay <UID> --out <thư mục dự án>     # kéo caption về kich-ban/poster_captions.txt
python $K quay <UID> --loai oneshot --boi Tên  # đánh dấu đã quay oneshot (hoặc --loai review)
python $K video <UID> --so 18                 # đánh dấu đã làm video
```

Test: `python -m pytest tools/test_kho.py -q`

## Cấu trúc dữ liệu

```
data/<UID>/info.json        link, UID, tên, giá, shop, tóm tắt, USP, ghi chú, thư mục máy, trạng thái
data/<UID>/bo-canh-quay.md  01-BO-CANH-QUAY-1-BUOI.md
data/<UID>/captions.txt     100 caption (≤150 ký tự, đúng 5 hashtag)
data/<UID>/bia.jpg          ảnh bìa thu nhỏ
data/index.json             do GitHub Action dựng lại sau mỗi lần push — không sửa tay
```
Link rút gọn (`vt.tiktok.com/...`) được lưu tạm dưới `data/tam-.../`. `kho.py cho` sẽ tìm UID rồi đổi tên thư mục.
