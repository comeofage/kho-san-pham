# Kho sản phẩm

Web lưu link sản phẩm TikTok Shop, dùng chung cho `/phantichcanhquay` và `/tao-video-tu-canh-quay`.
Mở được từ bất kỳ đâu (điện thoại, máy khác). Ai cũng xem được; muốn thêm link, gạt "đã quay" hay sửa ghi chú thì phải đăng nhập bằng token.

## Luồng làm việc

1. **Dán link** lên web (hoặc gửi link cho Claude trên máy nhà) → sản phẩm vào trạng thái **Chờ xử lý**.
   UID đã có trong kho thì web báo trùng.
2. Trên máy nhà, nói với Claude **"xử lý link mới trong kho"** → Claude chạy `kho.py cho`, rồi với từng link:
   `/phantichcanhquay` → file 01 + dữ liệu SP + USP + 100 caption → `kho.py ghi` → **Đã phân tích**.
3. Nhân viên mở web, đọc **Bộ cảnh quay** để quay. Quay xong thì **gạt "Đã quay"** (web ghi tên + giờ) → **Đã quay**.
4. Làm video: tab **🎞 Làm video** → bấm **Copy cho Claude** và dán vào Claude trên máy nhà. `/tao-video-tu-canh-quay`
   tự kéo caption từ kho, xong thì chạy `kho.py video` → **Đã làm video**.

## Cài đặt lần đầu (làm 1 lần)

1. **Tạo repo:** github.com → New repository → tên `kho-san-pham`, **Public**, không tick thêm README.
2. **Đẩy code** (chạy trên máy nhà, thay `<tai-khoan>`):
   ```bash
   cd E:/phantichcanhquay/kho-san-pham
   git remote add origin https://github.com/<tai-khoan>/kho-san-pham.git
   git push -u origin main
   ```
3. **Bật web:** repo → Settings → Pages → Source: **GitHub Actions**.
   Sau khoảng 1 phút web sẽ có ở `https://<tai-khoan>.github.io/kho-san-pham/`.
4. **Tạo token dùng chung:** github.com → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate:
   - Repository access: **Only select repositories** → `kho-san-pham`
   - Permissions → Repository → **Contents: Read and write** (không cấp gì thêm)
   - Expiration: tuỳ ý (hết hạn thì tạo lại và gửi lại cho nhân viên)
5. Mở web → **Đăng nhập** → dán token và gõ tên. Đưa token này cho nhân viên, mỗi người tự gõ tên mình.

> Token bị lộ: vào lại trang token → **Delete** → tạo cái mới. Token cũ hết tác dụng ngay.

## Lệnh máy nhà

```bash
export PYTHONIOENCODING=utf-8
K=E:/phantichcanhquay/kho-san-pham/tools/kho.py
python $K them "<link>"                       # lưu link
python $K cho                                 # link đang chờ phân tích
python $K ds --trang-thai da_quay             # sản phẩm đã quay, chưa làm video
python $K ghi <UID> --tu <thư mục dự án>      # đẩy file 01 / caption / USP / ảnh lên kho
python $K lay <UID> --out <thư mục dự án>     # kéo caption về kich-ban/poster_captions.txt
python $K quay <UID> --boi Tên                # đánh dấu đã quay
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
