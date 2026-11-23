# Radar UID: theo dõi UID, tìm sản phẩm tương tự, xếp hạng "đang có đà"

Phiếu A-RU1 + A-RU1b (sửa theo phản biện vòng 1/2, điền số đo RU-0) · Kiến trúc sư Culiapp · 2026-11-23 · nhánh `feat/radar-uid`
Trạng thái: **ĐÃ CHỐT** theo trưởng phòng (được người dùng ủy quyền toàn quyền duyệt thiết kế, 2026-11-23; kiến trúc sư không tự xác minh lời duyệt của người dùng). D16 trong `DECISIONS.md`.
**Hiện thực (2026-11-23, phiếu RU-D2 lượt 3):** lượt 1–2 đã làm xong (code + test pass); chờ tích hợp (deploy Worker, cài runner, khởi động lại: người dùng duyệt, §14). Các mục đánh dấu "đã hiện thực" hoặc §6.3a, §7, §8 phản ánh code thật; nơi code khác thiết kế ban đầu thì tài liệu theo code (danh sách thay đổi: D16, mục "Hiện thực").
Mẫu cấu trúc: `docs/hoc-tu-dong.md`. Liên quan: D1, D2, D3, D7, D8, D12, D13, D15. Hội đồng: `C:/Users/Mi/.claude/hop/Agency-20261123-1336/99-verdict.md`, `h2-claude.md`.

Nguồn số liệu EchoTik: **[Đ]** = ĐÃ ĐO bởi trưởng phòng 2026-11-23, token mới, 7 GET (kiến trúc sư không tự đo; số dán trong phiếu A-RU1b); **[M]** = mẫu cũ trên đĩa 2026-09-28 do kiến trúc sư đọc (`E:/phantichcanhquay/SP_ORICO_2026-09-18/du_lieu_tho/{video,san_pham}.json`, cùng 4 thư mục `SP_*`); **[C]** = CHƯA kiểm chứng.

---

## 0. Tóm tắt một màn hình

- Tab **📡 Radar UID** (`#/theo-doi`, mục menu thứ 6, chỉ chủ kho). Chủ nhập **1 UID gốc**; hệ thống tìm ≤ 10 sản phẩm "tương tự", chụp snapshot mỗi ngày, xếp hạng UID "đang có đà", chủ chọn UID để đưa sang Poster V2 (chỉ sao chép UID, §10).
- **Hai việc runner miễn phí, không Claude, chỉ runner/API tạo:** `radar_uid_hang_ngay` (hẹn giờ 10:00 giờ VN) và `radar_uid_nap`. Chạy `python -m runner.radar_uid`, GET chỉ đọc, ghi **`E:\kho-runner\radar_uid.db`**. **Không chạm `trendradar.db`.**
- **Đường đi:** `web/radar-uid.js` → Worker `/api/radar/*` (chủ kho, ký D7) → `video_server /r/radar/*` → runner `/radar/*`.
- **Chỉ số chính (một):** *trung vị Δview/video/24h trên tập "video đang sống"* (video đổi view trong kỳ **hoặc** đăng ≤ 90 ngày; catalog cũ đứng yên không kéo trung vị về 0), mẫu số giờ là chênh `lay_luc` của chính ta, kèm cỡ mẫu. Hai chỉ số đo đúng hai tiêu chí của chủ: **tăng tốc** (dựa `tong_delta_top5` = tổng Δ dương 5 video lớn nhất, bắt được "vài video bùng nổ") và **view cao ở creator nhỏ**. "Đáng thử" phải đạt **cả hai** và đủ cổng bằng chứng. Không điểm tổng hợp; thiếu = "—" kèm lý do; số tạm hiện xám kèm "chưa đủ bằng chứng".
- **Số đo thật đổi thiết kế** (§2.3): `/videos` có **39 video, 1 trang**, phần lớn đăng 2023–2025; `update_time` của video đổi ở 39/39 sau 3 giây trong khi view đổi 0/39, nên **không dùng làm mốc tươi**; `is_promote` có nhưng chỉ 1/39 và chưa rõ nghĩa, nên **chỉ hiện số thô, không bật nhãn ads**.
- **Hạn mức:** mặc định **60 GET/ngày** (suy diễn: `GHI_CHU_ECHOTIK.md:142` nói ≈ 100 trang chi tiết/ngày nhưng đó là mô tả collector creator-videos khác; **C7 chưa đo**; token dùng chung với `phantichsanpham`); mỗi UID = 2 GET; ngày đầu chỉ nạp 1 UID gốc; tối đa 2 gốc, 24 UID.
- **Nút Poster không ghi vào Poster V2** (§10). Bảng xếp hạng đầu tiên có nghĩa từ **lần chụp thứ 4** (≈ ngày +3).

---

## 1. Mục tiêu, ngoài phạm vi, quyết định đã chốt

**Mục tiêu.** Bảng số thô có cỡ mẫu và cờ để chủ quyết "thử làm video cho UID nào" từ tín hiệu lặp lại nhiều ngày. "Được đẩy" (phiếu): (1) view tăng đột ngột; (2) nhiều creator khác nhau, kể cả ít follower, cùng view cao; (3) ads mạnh. (1) = `tang_toc` (dựa `tong_delta_top5`), (2) = `view_nho`, (3) chỉ có **số thô** `is_promote x/y` (§5.3).

**Tiêu chí thành công của tab:** mỗi nhóm có **ít nhất 1 UID có `xep_loai` khác `chan`**; UID gốc có thể bị `chan` (ví dụ catalog cũ đứng yên) mà nhóm vẫn dùng được nhờ các UID tương tự. Bảng không bao giờ toàn "—": mỗi ô thiếu có lý do hiện kèm (§5.1 Ví dụ 5).

**Ngoài phạm vi:** tự đăng lên TikTok/Poster; deploy Worker; khởi động lại runner/app; sửa `trendradar.db`; kết luận "TikTok đang đẩy" (nhãn đúng: "đáng thử (tín hiệu)"); Telegram/email; chứng minh UID tương tự khớp SKU.

**Đã chốt bởi hội đồng:** không điểm tổng hợp ảo; một chỉ số xếp mặc định; "—" không điền 0; trạng thái "chưa đủ bằng chứng"; cờ chặn `DU_LIEU_CU`, `GAP`, `THIEU_MAU`; cờ cảnh báo `MAU_TOP_VIDEO`, `MOT_CREATOR_CHI_PHOI`, `NGHI_ADS`. **Đã chốt bởi trưởng phòng (A-RU1b):** Q1 nút Poster không tự điền; Q2 trần mặc định 60; Q3 không dùng `is_promote` làm lý do bật nhãn.

---

## 2. Hợp đồng dữ liệu EchoTik

### 2.1 Gọi API

| Mục | Giá trị | Nguồn |
|---|---|---|
| Gốc | `https://echotik.live` | `lay_du_lieu.py:32` |
| Header | `Authorization: Bearer <token>`, `X-User-Id`, `token`, `user_id`, `x-region: VN` (**phải ở header**), `Origin: https://echotik.live`, `Referer`, `User-Agent` Chrome | `lay_du_lieu.py:47-56`, `GHI_CHU_ECHOTIK.md:8-14` |
| Token | `E:\timsanpham\.echotik_token.json` (khoá `token`, `user_id`, `email`, `updated_at`; không đọc giá trị) | đo cục bộ |
| Lỗi | `content-type` chứa `text/html` ("Oops") = token hết hạn **hoặc** tham số bị từ chối; mã ≠ 200 là lỗi | `lay_du_lieu.py:82-88` |
| Nhịp | ≥ 1,2 s giữa hai lần gọi (dùng **1,3 s**) | [P] |
| Thư viện HTTP | `urllib` stdlib được chấp nhận: HTTP 200 JSON, không cần `httpx` | [Đ] C8 |
| Chuyển hướng | **Chặn mọi redirect** (RU-A4, lượt 5): `_ChanRedirect.redirect_request` trả `None` (`echotik.py:73-78`), `_OPENER` (`:81`), `mo_url_khong_theo_redirect` (`:84-86`) là `mo_url` mặc định của `EchoTik` (`:93`), nên mọi 3xx ⇒ `HTTPError` ⇒ `LoiEchoTik("dinh_dang", mã HTTP)` (không theo, không thử lại, không gửi lại `Authorization`/`token` sang host khác). Lý do: `urllib` mặc định theo redirect và gửi lại header sang host mới; chặn để không lộ token cho host lạ. Khuôn cùng loại: `vong_lap.py:367-374` | `echotik.py` |

### 2.2 Endpoint và trường (chỉ GET)

| # | Đường | Trả về | Dùng cho |
|---|---|---|---|
| E1 | `/api/v1/data/products/{pid}` | `data` là **một object**; trường đã thấy [Đ]: `product_id` (chuỗi), `price` (`'$19.37'`), `real_price` (`'499.390₫'`), `sale_cnt` (`'10.17K'`, chuỗi rút gọn), `commission` (`'10%'`), `total_stock_cnt` (số), `update_time` (`'2026-11-22 07:55'`, **cấp sản phẩm, độ phân giải phút**); trường khác [M]: `product_name`, `seller{}`, `categories`, `first_time`. Token cũ trả `"N/A"` cho nhiều trường | giá, tồn, bán, hoa hồng, tên, **mốc EchoTik làm mới SP** |
| E2 | `/api/v1/data/products/{pid}/videos?page&per_page&order&sort` | `data` list + `meta` (`current_page`, `from`, `last_page`, `links`) [Đ]. UID mẫu: **39 phần tử ở trang 1, trang 2 rỗng, `last_page=1`**; `per_page=50` được; `order=publish_time&sort=desc` đổi thứ tự (tham số `order` có tác dụng; **chiều "mới nhất trước" chưa xác nhận [C]**). Trường [Đ]: `video_id`, `views_count` (**số nguyên hoặc chuỗi rút gọn** `'21.81K'`), `play_count`, `publish_time`, `update_time`, `influencer{unique_id, follower_count (`'2.54K'`)}`, `influencer_id`, `influencer_name`, `is_promote`, `is_ai_video`, `digg_count`, `comment_count`, `gmv`, `duration`, `product`... ; `sales` [M] | nguồn số view |
| E4 | `/api/v1/data/products?page&per_page&order=total_sale_7d_cnt&sort=desc&dateRange=7&keyword=` | `data` list; trường **đã thấy** [Đ]: `product_id`, `product_name`, `avg_price` (`'$12.7'`), `total_sale_7d_cnt`; **chưa thấy** trường shop/seller, `category_ids`, ngày lên kệ, `meta` [C]. Với `keyword` 3 từ đầu, `per_page=50`: trả **10 phần tử, 10/10 tên chứa từ khoá** | tìm tương tự |

`order` hợp lệ của E4 chỉ `total_sale_nd_cnt`, `total_sale_7d_cnt` (`GHI_CHU_ECHOTIK.md:19-21`); order khác trả rỗng. Id sản phẩm luôn **chuỗi 19 chữ số** (`^\d{19}$`, D3).

### 2.3 Phát hiện đã đổi thiết kế

1. **View rút gọn hoặc số nguyên.** `'21.81K'`, `'1.79M'`, `'125'`; tối đa 2 chữ số thập phân (`'9.4K'` có thể là 9,40K) nên sai số một lần đọc = ±5 (K), ±5.000 (M), ±5.000.000 (B), 0 (số trần). `follower_count` cùng dạng (`'2.54K'`). Xử lý: `doc_so_rut_gon` (§5.1).
2. **`update_time` của video KHÔNG phải mốc làm mới [Đ].** Hai lần gọi cách 3 s: `update_time` đổi ở 39/39 video, `views_count` đổi 0/39 ⇒ trường này là giờ gọi/giờ gắn khi trả. **Không** dùng cho tuổi, mốc tươi, GAP hay mẫu số Δt. Mốc EchoTik làm mới SP là `update_time` cấp sản phẩm của E1 (`echotik_cap_nhat`). Mẫu số Δt = chênh `lay_luc` (giờ máy ta). Kiểm "EchoTik có làm mới" bằng cổng `KHONG_LAM_MOI` (gần như không video nào đổi view, hoặc `echotik_cap_nhat` SP đứng yên; §5.1); `ti_le_doi` chỉ để hiển thị.
3. **`is_promote` có nhưng yếu [Đ]:** `True` ở 1/39 video (326 view), `False` còn lại trong mẫu in (2,6%). Ý nghĩa chưa rõ ⇒ chỉ hiện `x/y` (§5.3).
4. **Danh sách video ngắn và cũ [Đ]:** UID mẫu có 39 video, mới nhất đăng 2026-07-18 (128 ngày trước), phần lớn 2023–2025. Hệ quả: lọc "tuổi 2–7 ngày" làm mẫu rỗng ⇒ bỏ; tính trên **mọi video** cũng sai vì catalog cũ đứng yên kéo trung vị về 0 và `tang_toc` về 0. Nên chỉ số chính tính trên tập **"video đang sống"** (đổi view trong kỳ hoặc đăng ≤ 90 ngày, §5.1); có chỉ số phụ video ≤ 14 ngày, `view_nho` (≤ 14 ngày, phụ ≤ 30 ngày tách riêng) và "số video mới 30 ngày" (nếu 0 ghi rõ "Không có video mới 30 ngày").
5. **Trang cuối:** `last_page=1` ⇒ `TRANG_VIDEO_TOI_DA = 1` (một GET E2/UID). `last_page > 1` ⇒ chỉ lấy trang 1 (50 video) và bật `MAU_TOP_VIDEO` (`radar_uid.py:183-193` `_lay_video`; cờ ở `radar_uid_tinh.py:433-435`). Cờ chỉ so `meta.last_page` với số trang đã lấy; **không** kiểm thứ tự trả về (xem §5.2).
6. **Múi giờ `publish_time` chưa đo [C3].** Giả định ghi rõ: coi `publish_time` là giờ VN (UTC+7); sai lệch tối đa ≈ 7 giờ chỉ làm dịch ranh giới 14/30 ngày, không đổi chỉ số chính. `tuoi = lay_luc − dang_luc`.

### 2.4 Kết quả RU-0 (C1–C8, ĐÃ ĐO 2026-11-23, 7 GET, trưởng phòng chạy)

| Mã | Câu hỏi | Kết quả | Thiết kế |
|---|---|---|---|
| C1 | `per_page`, `order`, `meta` của `/videos` | `per_page=50` được; 39 phần tử/1 trang; `meta{current_page, from, last_page=1, links}`; `order=publish_time&sort=desc` đổi thứ tự | `moi_trang=50`, đi theo `meta.last_page`; dùng `order=publish_time&sort=desc` |
| C2 | `update_time` video đổi giữa 2 lần cách 3 s? | đổi 39/39; view đổi 0/39 | bỏ `update_time` video khỏi mọi tính toán (§2.3.2) |
| C3 | múi giờ `publish_time` | **chưa đo** | giả định VN, nêu ở §2.3.6 |
| C4 | `is_promote` | `True` 1/39; ý nghĩa chưa rõ | số thô, không bật nhãn (§5.3) |
| C5 | `keyword` có lọc | 10/10 tên chứa từ khoá (3 từ đầu, `per_page=50` trả 10) | cổng `keyword_co_loc` giữ để phát hiện lỗi sau này |
| C6 | `avg_price` vs `price` | cùng ký hiệu USD (`'$12.7'` vs `'$19.37'`); chưa đối chiếu độ lớn | lọc giá `[0,5×; 2×]` giữ, bỏ khi thiếu một bên |
| C7 | rate-limit/ngày | **chưa đo** (không có 429 trong 7 GET) | trần 60, nâng sau khi đo thực tế (§6.4) |
| C8 | `urllib` | HTTP 200 JSON | dùng `urllib`, không thêm package |

### 2.5 Dạng fixture cho phiếu code (giá trị tổng hợp, KHÔNG phải dữ liệu thật)

```jsonc
// E1: {"data": {"product_id": "1729420930611055346", "product_name": "…", "price": "$19.37", "real_price": "499.390₫",
//        "sale_cnt": "10.17K", "commission": "10%", "total_stock_cnt": 562, "update_time": "2026-11-22 07:55", "seller": {"seller_name": "…"}}}
// E2: {"data": [{"video_id": "7…", "views_count": "21.81K"|326, "publish_time": "2026-07-18 10:00:00", "update_time": "<giờ gọi>",
//        "influencer": {"unique_id": "abc", "follower_count": "2.54K"}, "is_promote": false}],
//      "meta": {"current_page": 1, "from": 1, "last_page": 1, "links": []}}
// E4: {"data": [{"product_id": "…", "product_name": "…", "avg_price": "$12.7", "total_sale_7d_cnt": "36"}]}   // chưa có meta/seller trong số đo
```

---

## 3. Tìm sản phẩm tương tự (`radar_uid_tinh.py`, thuần)

Chạy trong `radar_uid_nap`. Tối đa **6 GET E4** mỗi lần tìm (3 từ khoá × tối đa 2 trang).

1. `lam_sach_ten(product_name)`: NFC, chữ thường; bỏ `[...]`, `(...)`, `【...】`; bỏ ký tự không phải chữ/số; bỏ token số kèm đơn vị (`\d+(ml|g|kg|cm|mm|m|l|w|v|mah)`) và số trần; bỏ từ quảng cáo `TU_QUANG_CAO` (`freeship, chính hãng, giá rẻ, hot, trend, mới, sale, cao cấp, loại 1, siêu, đẹp, xịn, tặng, combo, set, bộ, cái, chiếc, nhập khẩu, uy tín, tiktok, shop, hàng`).
2. `tu_khoa_tim(ten)`: **ba từ khoá** = 4, 3, 2 âm tiết đầu của tên sạch. (Số đo C5 dùng 3 âm tiết.)
3. Mỗi từ khoá: `GET products?page=1&per_page=50&order=total_sale_7d_cnt&sort=desc&dateRange=7&keyword=…`; **nếu `meta.last_page > 1` thì lấy thêm `page=2`** (E4 chưa thấy `meta`: không có `meta` thì coi 1 trang). **Gộp (union)** kết quả ba từ khoá, khử trùng theo `product_id`.
4. **Cổng `keyword_co_loc(tu_khoa, ten_ung_vien[])`** (bỏ dấu, ≥ 50% tên chứa ≥ 1 âm tiết từ khoá) chạy **từng từ khoá**: từ khoá nào không đạt bị bỏ (nghĩa là EchoTik bỏ qua `keyword`); cả ba không đạt ⇒ nhóm `loi_tim` mã `keyword_khong_loc`, **không chọn ứng viên nào**. Không còn quy tắc suy "token cũ" từ số phần tử (số đo cho thấy 10 phần tử là kết quả thật).
5. Lọc: bỏ UID gốc và UID đã `loai`; `do_giong ≥ 0,35` (Jaccard trên tập âm tiết bỏ dấu, `đ→d`); nếu có giá cả hai bên (`price` E1 vs `avg_price` E4, cùng USD) thì ứng viên trong `[0,5×; 2×]` giá gốc. **Không** lọc theo shop hay danh mục: E4 chưa có trường đó trong số đo.
6. Sắp `do_giong` giảm dần, rồi `total_sale_7d_cnt` giảm dần; lấy 10. `total_sale_7d_cnt` là bán 7 ngày (không phải tích luỹ) nên đã nghiêng về sản phẩm đang bán chứ không phải bán lâu năm. **Đề xuất chưa kiểm chứng:** nếu sau này E4 có ngày lên kệ thì ưu tiên sản phẩm lên kệ ≤ 180 ngày; `order` khác `total_sale_*` bị EchoTik trả rỗng nên không dùng.

**Ví dụ.** Gốc `"[HOT] Kẹp tóc càng cua mini 8cm freeship"` → tên sạch `"kẹp tóc càng cua mini"` → ba từ khoá `"kẹp tóc càng cua"`, `"kẹp tóc càng"`, `"kẹp tóc"`. Ứng viên `"Kẹp tóc càng cua to 12cm"`: `{kep,toc,cang,cua,to}` ∩ `{kep,toc,cang,cua,mini}` = 4, hợp = 6 ⇒ 0,67 giữ; `"Máy sấy tóc mini"`: giao 2, hợp 7 ⇒ 0,29 loại.

UI ghi: "Tương tự theo từ khoá tên + giá. Chưa chứng minh trùng SKU/biến thể." Chủ có thể **thêm tay** UID (§9).

---

## 4. Lưu trữ: `E:\kho-runner\radar_uid.db`

Mô hình `kho_hoc.py`: SQLite WAL, `KhoRadarUid(duong_dan, bay_gio, *, chi_doc=False)`, import không mở file, schema chỉ tạo/nâng trong `mo()` sau mutex runner (`kho_hoc.py:529-560`, `:611`; `isolation_level=None`, `busy_timeout=5000`, `foreign_keys=ON`, kết nối mỗi luồng, đóng cuối request như `api.py:1064-1080`). Script không gọi `mo()`; thiếu file thì thoát `loi`. DB riêng: không nâng `runner.db` (D14 còn Đề xuất), không đụng `trendradar.db`; tên tránh thư mục `radar/` (`danh_muc.py:847`).

```sql
-- meta(k TEXT PRIMARY KEY, v TEXT): schema_ban='1'
CREATE TABLE san_pham (uid TEXT PRIMARY KEY CHECK(length(uid)=19 AND uid NOT GLOB '*[^0-9]*'),
  ten TEXT NOT NULL DEFAULT '', shop TEXT NOT NULL DEFAULT '', cap_nhat_luc TEXT);
CREATE TABLE nhom (goc TEXT PRIMARY KEY REFERENCES san_pham(uid),
  trang_thai TEXT NOT NULL CHECK(trang_thai IN ('cho_tim','dang_tim','da_tim','loi_tim','ngung')),
  ly_do TEXT NOT NULL DEFAULT '', them_luc TEXT NOT NULL, them_boi TEXT NOT NULL, tim_luc TEXT, bat_dau_ngay TEXT NOT NULL);
CREATE TABLE lien_ket (goc TEXT NOT NULL REFERENCES nhom(goc), uid TEXT NOT NULL REFERENCES san_pham(uid),
  vai TEXT NOT NULL CHECK(vai IN ('goc','tuong_tu','them_tay')),
  trang_thai TEXT NOT NULL CHECK(trang_thai IN ('dang_theo','ghim','loai')),
  do_giong REAL, them_luc TEXT NOT NULL, them_boi TEXT NOT NULL, PRIMARY KEY (goc, uid));
CREATE TABLE chup_uid (uid TEXT NOT NULL, ngay TEXT NOT NULL,            -- ngày lịch giờ VN
  trang_thai TEXT NOT NULL CHECK(trang_thai IN ('dang_chup','ok','loi')), ma_loi TEXT NOT NULL DEFAULT '',
  lay_luc TEXT NOT NULL,                     -- giờ máy ta, ISO có múi: MẪU SỐ Δt
  echotik_cap_nhat TEXT,                     -- E1.update_time cấp sản phẩm
  ban_tong TEXT, gia TEXT, hoa_hong TEXT, ton TEXT, tong_creator TEXT,
  so_trang INTEGER NOT NULL DEFAULT 0, tong_trang INTEGER, so_lan_thu INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (uid, ngay));
CREATE TABLE chup_video (uid TEXT NOT NULL, ngay TEXT NOT NULL, video_id TEXT NOT NULL, creator TEXT NOT NULL,
  follower TEXT, view TEXT NOT NULL, ban TEXT, dang_luc TEXT NOT NULL, is_promote INTEGER,   -- KHÔNG lưu update_time video
  PRIMARY KEY (uid, ngay, video_id), FOREIGN KEY (uid, ngay) REFERENCES chup_uid(uid, ngay));
CREATE TABLE lan_chay (ngay TEXT NOT NULL, che_do TEXT NOT NULL, viec_id TEXT NOT NULL, trang_thai TEXT NOT NULL,
  ly_do TEXT NOT NULL DEFAULT '', bat_dau TEXT NOT NULL, ket_thuc TEXT, so_goi INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (ngay, che_do, viec_id));
CREATE TABLE goi_ngay (ngay TEXT PRIMARY KEY, so_goi INTEGER NOT NULL DEFAULT 0);        -- cộng TRƯỚC khi gọi
CREATE TABLE token_tt (id INTEGER PRIMARY KEY CHECK(id=1), trang_thai TEXT NOT NULL, ma TEXT NOT NULL DEFAULT '', luc TEXT NOT NULL);
CREATE TABLE su_kien (id INTEGER PRIMARY KEY, luc TEXT NOT NULL, boi TEXT NOT NULL, hanh_dong TEXT NOT NULL, goc TEXT, uid TEXT);
```

- Chuỗi lưu nguyên văn (`view`, `follower`, `ban`...), số hoá lúc tính. Id luôn TEXT. `ten`, `shop` bỏ ký tự điều khiển C0, cắt 200 ký tự (vẫn escape lúc hiện).
- Một UID có thể ở nhiều nhóm; **chụp một lần/ngày** mỗi UID. Giữ 90 ngày `chup_video`, dọn trong `mo()` (như `kho_hoc.py:38`).
- Chụp mà E2 trả **0 video** ⇒ ghi `trang_thai='loi'`, `ma_loi='khong_co_video'` (không ghi `ok`, không tham gia tính kỳ); UI: "EchoTik chưa có video nào cho UID này".
- Giới hạn cứng (hằng trong `kho_radar_uid.py`, ném `SaiTrangThaiRadar`): `GOC_TOI_DA=2`, `TUONG_TU_TOI_DA=10` (gồm ghim) mỗi nhóm, `THEM_TAY_TOI_DA=3`, `UID_TOI_DA=24` (UID khác nhau toàn DB, trạng thái ≠ `loai`/`ngung`). Lý do: 24 UID × 2 GET = 48 ≤ trần 60 (§6.4).

---

## 5. Công thức, cờ, ngưỡng (`radar_uid_tinh.py`)

### 5.1 Chỉ số

`doc_so_rut_gon(s)` → `(gia_tri, sai_so)`: số nguyên hoặc chuỗi `^\d+$` ⇒ `(n, 0)`; `^\d+(\.\d+)?[KMB]$` ⇒ `(round(x×10^3|6|9), 5 | 5.000 | 5.000.000)`; `"N/A"`, rỗng, lạ ⇒ `None` (hiện "—").

**Kỳ.** Hai snapshot `ok` liên tiếp *a* (cũ), *b* (mới); `gio = b.lay_luc − a.lay_luc`. Kỳ **hợp lệ** nếu `gio ∈ [8, 54]` (Δ đã chuẩn hoá theo giờ nên cho phép lệch); ngoài khoảng ⇒ kỳ `GAP`.

**Video đo được trong kỳ:** có ở cả *a* và *b*, đọc được `view` cả hai lần; `sai_so_tong = sai_so_a + sai_so_b`; nếu `sai_so_tong > 20` (mức M/B) chỉ giữ khi `|Δ| > sai_so_tong`, ngược lại loại (đếm `duoi_do_phan_giai`). **Không lọc theo tuổi video.**

`d24(v) = (view_b − view_a) / (gio / 24)`.
- **`n_doi`** = số video đo được có chuỗi `view` khác snapshot trước; **`ti_le_doi = n_doi / số video đo được`** chỉ **hiển thị** (thông tin), **không** là cổng.
- **Tập "video đang sống"** = video đo được có view đổi trong kỳ **hoặc** `lay_luc − dang_luc ≤ 90 ngày` (`TUOI_SONG_NGAY`). `n_video`, `n_creator` (số `unique_id` khác nhau) đếm trên tập này.
- **Chỉ số chính `trung_vi` = median(d24)** trên tập sống, làm tròn xuống số nguyên. Δ âm vẫn tính.
- **`tong_delta_top5`** = tổng `d24` dương của (tối đa) 5 video lớn nhất trong tập sống (đã chuẩn theo 24 giờ). Bắt được "vài video bùng nổ" mà trung vị không thấy.
- **`KHONG_LAM_MOI` (cổng tươi)** = `n_doi ≤ 1` trong kỳ **hoặc** `echotik_cap_nhat` SP **không đổi qua ≥ 2 kỳ liên tiếp** (3 snapshot liền cùng giá trị). Khi bật: `trung_vi`, `tong_delta_top5` = `null`, hiện số thô ("39 video, view đổi 0, SP cập nhật 07:55"). Không dùng tỉ lệ trên cả catalog cũ làm cổng.
- **`tang_toc` (tiêu chí 1, tăng đột ngột)** = `tong_delta_top5(kỳ này) / max(tong_delta_top5(kỳ trước), SAN_TOP5)`, `SAN_TOP5 = 250`. **Đột ngột** ⇔ `tang_toc ≥ 2,0` **và** `tong_delta_top5(kỳ này) ≥ TOP5_TOI_THIEU = 1.000`. Nếu kỳ trước/kỳ này là `null`, `GAP` hoặc `KHONG_LAM_MOI`, hoặc chưa có kỳ trước ⇒ `tang_toc = null`, hiện "—" kèm lý do ("kỳ trước GAP", "chưa có kỳ trước"). Nhờ top 5, "đột ngột" bật được khi **3 video viral trong 11 video** (Ví dụ 3).
- **`view_nho` (tiêu chí 2, ai đăng cũng cao)** từ **1 snapshot** mới nhất: video `lay_luc − dang_luc ≤ 14 ngày` **và** creator có `follower` **đọc được** và `< 10.000` (follower thiếu/`N/A`/không đọc được **bị loại**, không coi 0; đếm `follower_khong_doc`). `view_nho_trung_vi` = trung vị `view`; `n_creator_nho` = số creator khác nhau. **Cao** ⇔ `view_nho_trung_vi ≥ 5.000` **và** `n_creator_nho ≥ 3`. Nếu **không có video ≤ 14 ngày** ⇒ `view_nho_trung_vi = null`, UI ghi "không có video ≤ 14 ngày" (không "—" trơn), tiêu chí 2 **không đạt**.
- **Phụ tách riêng (không trộn vào cổng):** `view_nho_30_trung_vi`, `n_creator_nho_30` = như `view_nho` nhưng cửa sổ ≤ 30 ngày; `trung_vi_14`, `n_video_14` = như `trung_vi` chỉ trên video ≤ 14 ngày; `n_video_moi_30` = số video đăng ≤ 30 ngày, `= 0` ⇒ UI ghi "Không có video mới 30 ngày".
- `d_ban_ngay` = `(ban_tong_b − ban_tong_a) / (gio/24)` từ `sale_cnt` (E1); `None` nếu một bên `N/A`. `creator_moi_ngay` = số `unique_id` có video với `dang_luc ∈ (a.lay_luc, b.lay_luc]` chia `(gio/24)`, 1 chữ số.
- `spark` = dãy `trung_vi` ≤ 7 kỳ gần nhất, cũ → mới, `null` ở kỳ không hợp lệ/`KHONG_LAM_MOI`; hiện `▁▂▃▄▅▆▇█` với `min(7, floor(8 × max(v,0)/max_v))`, `null` = `·`.
- `so_snapshot`, `phu_gio`: chuỗi snapshot liên tục kết thúc ở snapshot mới nhất, mọi khoảng liền kề ∈ [8, 54] giờ; `phu_gio` = cuối − đầu.

**Ví dụ 1 (trung vị chính)**, kỳ `gio = 24,0`, 11 video, 6 creator, 10/11 video đổi view (`ti_le_doi` = 90,9%, chỉ hiển thị; `n_doi = 10 > 1` nên không `KHONG_LAM_MOI`), đều đăng ≤ 90 ngày nên cả 11 là "đang sống":

| video | creator | view a → b | d24 |
|---|---|---|---|
| v1 | c1 | 12.400 → 15.100 | 2.700 |
| v2 | c1 | 8.000 → 9.500 | 1.500 |
| v3 | c2 | 3.200 → 3.900 | 700 |
| v4 | c2 | 5.600 → 6.100 | 500 |
| v5 | c3 | 20.000 → 20.900 | 900 |
| v6 | c3 | 1.100 → 1.100 | 0 |
| v7 | c4 | 9.000 → 12.300 | 3.300 |
| v8 | c4 | 4.000 → 4.800 | 800 |
| v9 | c5 | 700 → 1.000 | 300 |
| v10 | c5 | 15.000 → 15.400 | 400 |
| v11 | c6 | 6.000 → 6.600 | 600 |

Sắp 0, 300, 400, 500, 600, **700**, 800, 900, 1.500, 2.700, 3.300 ⇒ `trung_vi = 700`, `n_video = 11`, `n_creator = 6`, `tong_delta_top5 = 3.300+2.700+1.500+900+800 = 9.200`. Nếu `gio = 25,2` thì v3 có `d24 = 700/(25,2/24) = 666`. Rút gọn: `'1.79M'→'1.80M'` Δ 10.000 ≤ `sai_so_tong` 10.000 ⇒ loại; `'38.11K'→'38.74K'` `sai_so_tong` 10 ≤ 20 ⇒ giữ, Δ 630.

**Ví dụ 2 (`KHONG_LAM_MOI`)**: 39 video mà `n_doi = 0` (hoặc 1) ⇒ cờ, `trung_vi = null`, hiện số thô. 3 snapshot liền có `echotik_cap_nhat` cùng `2026-11-22 07:55` (2 kỳ liên tiếp đứng yên) ⇒ cũng cờ. Còn `n_doi = 6/39` (15,4%) **không** bật cờ (xem Ví dụ 5).

**Ví dụ 3 (`tang_toc` theo top 5)**: Ví dụ 1 có top5 = 9.200; kỳ trước top5 = 1.600 ⇒ 9.200/max(1.600, 250) = **5,75** và 9.200 ≥ 1.000 ⇒ **đột ngột**. **Vài video bùng nổ:** 11 video có `d24` = 0, 0, 20, 40, 60, 100, 120, 150, 2.000, 2.500, 3.000 ⇒ `trung_vi = 100` (nhìn như phẳng) nhưng `tong_delta_top5 = 3.000+2.500+2.000+150+120 = 7.770`; kỳ trước top5 = 540 ⇒ 7.770/max(540, 250) = **14,39** ⇒ **đột ngột** (3 video viral trong 11). Không đột ngột: trước 100, nay 400 ⇒ 400/max(100, 250) = 1,6 (< 2); trước 0, nay 900 ⇒ 900/250 = 3,6 nhưng 900 < 1.000 (sàn tuyệt đối). Kỳ trước `GAP` ⇒ `tang_toc = null`, "—" kèm "kỳ trước GAP".

**Ví dụ 4 (`view_nho`)**, video ≤ 14 ngày: c1 (2,54K) 9.800; c2 (8,1K) 6.400; c3 (450) 12.000; c4 (9,99K) 3.100; c5 (15K) 40.000 **loại (≥ 10K)**; c6 (1,2K) 7.200. Còn 5 video: 3.100, 6.400, 7.200, 9.800, 12.000 ⇒ `view_nho_trung_vi = 7.200`, `n_creator_nho = 5` ⇒ cao (≥ 5.000, ≥ 3). Creator c7 có `follower = "N/A"` ⇒ **loại**, `follower_khong_doc = 1`. Không video nào ≤ 14 ngày ⇒ "không có video ≤ 14 ngày"; cửa sổ phụ ≤ 30 ngày tính riêng.

**Ví dụ 5 (UID mẫu: 39 video, mới nhất đăng 128 ngày trước)**. Số đo thật chỉ nói `views_count` đổi **0/39 sau 3 giây** (C2); con số **6/39 dưới đây là giả định minh hoạ** cho kỳ cách 24 giờ. Giả sử 6 video đổi view với `d24` = 4, 6, 9, 15, 30, 120 (4 creator). Tất cả đăng > 90 ngày nên tập sống = đúng 6 video đó. Kết quả (chỉ 1 snapshot ⇒ chưa có kỳ trước; giả sử đã 2 snapshot):
- `n_doi = 6 > 1`, `echotik_cap_nhat` đổi ⇒ **không** `KHONG_LAM_MOI`; `ti_le_doi = 6/39 = 15,4%` hiện như thông tin.
- `n_video = 6`, `n_creator = 4`; `trung_vi = (9+15)/2 = 12`; `tong_delta_top5 = 120+30+15+9+6 = 180`.
- `n_video = 6 < 8` ⇒ `THIEU_MAU` ⇒ `xep_loai = chua_du`, `tam = true`: ô hiện **"12 (xám) · chưa đủ bằng chứng (n=6 < 8, 2/4 snapshot)"**, không phải "—".
- `tang_toc`: "—" kèm "chưa có kỳ trước" (hoặc số nếu có); `view_nho`: "không có video ≤ 14 ngày"; "Không có video mới 30 ngày"; `is_promote 1/39`. Cả bảng **không** toàn "—": mỗi ô thiếu có lý do. UID gốc này có thể `chan`/`chua_du` mà nhóm vẫn có UID tương tự dùng được (tiêu chí §1).

### 5.2 Cờ

| Cờ | Loại | Điều kiện | Ví dụ |
|---|---|---|---|
| `DU_LIEU_CU` | chặn | snapshot `ok` mới nhất có `lay_luc` cách bây giờ > 36 giờ (chỉ điều kiện này) | 21/11 08:00 → 23/11 10:00 = 50 giờ ⇒ cờ |
| `GAP` | chặn | kỳ gần nhất `gio > 54` hoặc `< 8` | 20/11 08:00 → 22/11 15:00 = 55 giờ ⇒ GAP; 48 giờ ⇒ không |
| `THIEU_MAU` | chặn (cổng "đáng thử") | **không** `DU_MAU(kỳ gần nhất)` (định nghĩa §5.4: kỳ hợp lệ, `n_video ≥ 8`, `n_creator ≥ 3`, không `KHONG_LAM_MOI`), **hoặc** `so_snapshot < 4`, **hoặc** `phu_gio < 70` (72 giờ, dung sai 2) | n=7, c=2 ⇒ cờ, số hiện xám |
| `KHONG_LAM_MOI` | chặn | `n_doi ≤ 1` trong kỳ, **hoặc** `echotik_cap_nhat` không đổi qua ≥ 2 kỳ liên tiếp (§5.1). **Không** dựa tỉ lệ trên cả catalog | 39 video, `n_doi = 0` ⇒ cờ; `n_doi = 6/39` ⇒ không |
| `MAU_TOP_VIDEO` | cảnh báo | **chỉ** `meta.last_page > số trang đã lấy` (snapshot mới nhất: `tong_trang > so_trang`; chỉ lấy một trang 50 video trong tổng nhiều hơn). `last_page` thiếu (`None`) ⇒ không cờ. Code: `radar_uid_tinh.py:433-435` (`_mau_top_video`), gắn cờ `:559-560` | `last_page = 2`, đã lấy 1 trang ⇒ cờ; UID mẫu `last_page = 1` ⇒ không |

**Vì sao không kiểm thứ tự trả về (đã bỏ vế "không giảm theo `dang_luc`"):** kho đọc video bằng `ORDER BY video_id` (`kho_radar_uid.py:688`) nên thứ tự EchoTik trả về **không được lưu**; id video TikTok lại tăng theo thời gian đăng, nên thứ tự đọc lại luôn "không giảm" và vế đó làm cờ **luôn bật**. Chiều `sort=desc` của E2 vẫn chưa đo (§2.2, Phụ lục A); hệ quả được chấp nhận: nếu EchoTik bỏ qua `order`, trang 1 có thể không phải 50 video mới nhất mà cờ không báo (chỉ báo khi `last_page > 1`).
| `MOT_CREATOR_CHI_PHOI` | cảnh báo | `n_creator ≥ 3` và một creator ≥ 50% tổng Δ dương | c1 9.000/12.000 = 75% ⇒ cờ; Ví dụ 1: 4.200/11.700 = 35,9% ⇒ không |
| `NGHI_ADS` | cảnh báo | **không có luật bật nào được chấp nhận đợt này** (§5.3) | – |

`DU_LIEU_CU`, `GAP`, `KHONG_LAM_MOI` ⇒ `xep_loai="chan"` (số chính "—"/số thô). `THIEU_MAU` ⇒ `"chua_du"`.

### 5.3 `is_promote` và `NGHI_ADS`

EchoTik không có trường chi tiêu/doanh số ads. Mỗi UID luôn hiện **số thô "is_promote x/y"** (x video có `is_promote=1`, y video đo được) kèm câu cố định "is_promote chưa rõ nghĩa". **Bỏ luật R2** (follower nhỏ + tăng mạnh: trùng với tiêu chí 2, không phân biệt được với đà thật). Luật R1 (`x ≥ 3` và `x/y ≥ 30%`) chỉ nằm trong code sau công tắc `NGUONG.ADS_BAT = False` (mặc định tắt; ngưỡng 30% chưa kiểm). Cờ `NGHI_ADS` do đó **không bao giờ bật** cho tới khi một phiếu sau đo nghĩa của `is_promote` (đóng Q3 theo (b)).

### 5.4 Xếp loại và ngưỡng

`radar_uid_tinh.NGUONG` (một chỗ; đổi = đổi code, review, cài lại D8). **Tất cả là đề xuất chưa kiểm chứng**, xem lại sau 14 ngày dữ liệu:

| Hằng | Giá trị | Hằng | Giá trị |
|---|---|---|---|
| `KY_GIO` | (8, 54) | `TUOI_SONG_NGAY` | 90 |
| `DU_LIEU_CU_GIO` | 36 | `TANG_TOC_MIN` | 2,0 |
| `SNAPSHOT_TOI_THIEU` | 4 | `SAN_TOP5` | 250 |
| `PHU_GIO_TOI_THIEU` | 70 | `TOP5_TOI_THIEU` | 1.000 |
| `VIDEO_TOI_THIEU` | 8 | `FOLLOWER_NHO` | 10.000 |
| `CREATOR_TOI_THIEU` | 3 | `VIEW_CAO_NHO` | 5.000 |
| `KHONG_LAM_MOI_DOI_TOI_DA` | 1 | `CREATOR_NHO_TOI_THIEU` | 3 |
| `CAP_NHAT_KHONG_DOI_KY` | 2 | `TUOI_MOI_NGAY`, `TUOI_NHO_PHU_NGAY`, `VIDEO_MOI_NGAY` | 14, 30, 30 |
| `CREATOR_CHI_PHOI_PT` | 50 | `TOP_N` | 5 |
| `ADS_BAT`, `ADS_PROMOTE_PT` | False, 30 | `NGAY_HA_UU_TIEN`, `TRANG_VIDEO_TOI_DA` | 7, 1 |

**`DU_MAU(kỳ)` (một định nghĩa duy nhất, dùng cho cả `THIEU_MAU` ở §5.2 lẫn `dang_co_da`):** kỳ hợp lệ (`gio ∈ [8, 54]`), **không** `KHONG_LAM_MOI`, `n_video ≥ 8` và `n_creator ≥ 3` (đếm trên tập "đang sống").

`xep_loai`:
1. `chan`: có `DU_LIEU_CU`, `GAP` hoặc `KHONG_LAM_MOI`.
2. `chua_du`: có `THIEU_MAU`. **Số tạm hiện xám** kèm "chưa đủ bằng chứng (n=7, 2/4 snapshot)" ngay khi tính được từ ≥ 2 snapshot (`tam=true`); chỉ "—" khi không tính được (chưa có kỳ hợp lệ), luôn kèm lý do.
3. `dang_co_da` ("đáng thử (tín hiệu)"): không cờ chặn, `so_snapshot ≥ 4`, `phu_gio ≥ 70`, `DU_MAU` ở **cả hai kỳ gần nhất**, **và** tiêu chí 1 (`tang_toc` đột ngột, §5.1) **và** tiêu chí 2 (`view_nho` cao). Cần **cả hai tiêu chí**, không chỉ `trung_vi > 0`.
4. `chua_co_da`: đủ cổng như (3) nhưng chưa đạt đủ hai tiêu chí; UI nêu tiêu chí nào thiếu (kể cả `tang_toc = null`: "kỳ trước GAP").

Sắp mặc định: `dang_co_da` → `chua_co_da` → `chua_du` → `chan`; trong mỗi lớp theo `trung_vi` giảm (null cuối), rồi `n_video`, rồi `uid`; UID `loai` **xuống cuối `ds`** (khoá đầu của sắp xếp là `trang_thai == "loai"`, `api.py:194-203`). API **vẫn trả** UID loại để web có nút "Bỏ loại"; ẩn là việc của web (gom khối "Đã loại" thu gọn, hàng làm mờ, §8). `uu_tien="ha"` khi `chua_du` do `THIEU_MAU` và `hôm nay − bat_dau_ngay ≥ 7` (khối thu gọn "Ít dữ liệu"). Không tự bỏ UID.

---

## 6. Luồng định kỳ và xử lý lỗi

### 6.1 Hai loại việc (`danh_muc.py:1739-1751`, theo `hoc_hang_ngay`)

| Trường | `radar_uid_hang_ngay` | `radar_uid_nap` |
|---|---|---|
| Ai tạo | `BoChay._hen_gio` từ **10:00** giờ VN (`vong_lap.py:1394-1430`; mốc `HEN_GIO_MAC_DINH` `:118-119`) | API: nhập UID gốc, "Tìm lại", "Chụp lại" |
| `dot`, `lan_chay`, `ton_tien`, `agent` | 3, `nhe`, False, None | giống |
| `tu_chay_lai`, `het_gio_s` | True, 1200 | True, 900 |
| `tham_so`, `tinh_khoa` | `{"ngay"}` hôm nay/hôm qua; `ngay` | `{"goc"}` 19 số; `goc` |
| Bước | `python -B -m runner.radar_uid --che-do hang-ngay --ngay … --db <du_lieu>/radar_uid.db --token-file … --viec-id <id> --tran-goi 60`, cwd `THU_MUC_CAI` | `--che-do nap --goc <uid> …` |
| `kiem_dau_ra` | `lan_chay(ngay, che_do, viec_id).trang_thai ∈ {xong, tu_dung}` ⇒ `xong`, còn lại `chua` (đọc `radar_uid.db` `mode=ro`, `_dau_ra_radar_uid`, `danh_muc.py:1624-1641`); **không** đòi mọi UID có `chup_uid`. Từ lượt 5, lượt `loi`/`khong_chup_duoc` (thử ≥ 1 UID, chụp `ok` = 0) rơi vào "còn lại" ⇒ `chua`: `_dau_ra_radar_uid` **không đổi code**; việc không đạt đầu ra đi theo đường `tu_chay_lai`/D6 như mọi việc khác, và chạy lại an toàn vì UID `ok` hôm nay bị bỏ, UID `loi` chụp lại ≤ 2 lần/ngày, ngân sách đếm trước mỗi GET (§6.5). Mã thoát của script ở nhánh này do RU-A4 quyết; số lần chạy lại thực tế chưa kiểm bằng test ở mức đặc tả này | như trái (`che_do='nap'`) |

Cả hai trong `LOAI_CHI_HE_THONG` và `LOAI_KHONG_CHAY_LAI` (`danh_muc.py:163-167`): web không tạo/"Chạy lại" qua `/api/viec`; nút trong tab gọi route riêng (§7), API tạo nội bộ bằng `_tao_viec_da_khoa` (khoá `(loai, khoa)`, bỏ cổng `LOAI_CHI_HE_THONG`, vẫn qua `kiem_han_muc`). Hàm `_tao_viec_he_thong` bản đầu là **mã chết và đã xoá** (RU-B8, lượt 5); không còn tham chiếu nào tới nó. Bỏ lịch nếu `KhoRadarUid` không mở được hoặc cầu dao `radar_uid_bat=0` (`vong_lap.py:1408-1413`).

**Làn:** dùng làn `nhe` có sẵn, **không thêm làn riêng** (D1 chốt hai làn; thêm làn đổi `vong_lap` nhiều). Hệ quả chấp nhận: `phan_tich_uid` dài (≤ 90 phút) làm Radar chạy trễ; kỳ hợp lệ rộng tới 54 giờ nên trễ vài giờ không gây GAP; việc nạp do chủ bấm có thể chờ, UI hiện `cho_tim` kèm "đang chờ máy nhà".

### 6.2 Việc script làm (`radar_uid.py`)

`hang-ngay`: (1) `bat_dau_lan`; kiểm file token. (2) Mỗi UID `dang_theo`/`ghim` của nhóm **`da_tim` hoặc `loi_tim`** (khử trùng; `ds_can_chup(ngay)`; bảng nhóm dưới đoạn này), theo thứ tự **xoay: UID có lần chụp `ok` gần nhất cũ nhất đi trước** (chưa từng chụp đứng đầu; không cố định thứ tự, để UID cuối không bị đói khi gặp trần ngân sách): `bat_dau_chup` ghi **`dang_chup` TRƯỚC khi gọi mạng**; `tinh_goi` cộng ngân sách **trước** mỗi GET; **E1 rồi E2 trang 1** (`order=publish_time&sort=desc`, `per_page=50`; thêm trang nếu `meta.last_page` > 1 **và** `TRANG_VIDEO_TOI_DA` cho phép; mặc định 1 trang); `ghi_chup_ok` một giao dịch. UID đã `ok` hôm nay thì bỏ qua. (3) Nhóm `cho_tim`/`dang_tim` **thuộc luồng nạp** (`radar_uid_nap`, do chủ bấm), **không** thuộc `hang-ngay`: `hang-ngay` bỏ qua chúng; nhóm `ngung` cũng bỏ. Nhóm `loi_tim` **được chụp** (RU-B7, lượt 5): UI khi tìm tương tự lỗi dặn chủ "thêm tay UID" (§6.3 `keyword_khong_loc`), nên gốc và UID thêm tay/ghim của nhóm đó phải có chuỗi snapshot hằng ngày; nếu bỏ qua thì các UID đó không bao giờ đủ 4 snapshot. (4) `ket_thuc_lan`: **lượt đã THỬ ≥ 1 UID mà chụp `ok` = 0 kết thúc `loi` với `ly_do="khong_chup_duoc"`** (RU-A4, lượt 5; `_chay_hang_ngay`, `radar_uid.py:254-263`: `lan.so_thu > 0 and lan.so_uid == 0` ⇒ `_LoiViec("khong_chup_duoc")`, thoát 1 theo docstring `:16`; trước đây có thể kết thúc `xong` im lặng khi mọi UID hỏng từng cái); nhánh dừng có chủ đích (`rate_limit`, `token_het_han`, `token_thieu`, `het_han_muc_goi`, `mang_lien_tiep`, `dinh_dang`) vẫn là `tu_dung` với `ly_do` của nó. Lượt không có UID nào cần chụp (mọi UID đã `ok` hôm nay, hoặc danh sách rỗng) vẫn `xong`. stdout đúng **một dòng JSON ASCII** `{"trang_thai","ly_do","so_uid","so_goi"}`; lỗi bất ngờ log chỉ tên kiểu ngoại lệ.

`nap --goc <uid>`: E1 gốc → `san_pham`, nhóm `dang_tim`; tìm tương tự (§3, ≤ 6 GET E4) → `ghi_tuong_tu` (giữ `ghim`, `them_tay`, `loai`); `da_tim`; rồi chụp E1+E2 cho gốc và tương tự chưa chụp hôm nay.

**Bảng trạng thái nhóm → ai chụp** (`ds_can_chup`, `kho_radar_uid.py:562-584`; UID `loai` luôn bị bỏ):

| Trạng thái nhóm | `hang-ngay` (`goc=None`) | `nap` (`goc=<uid>`) | Ghi chú |
|---|---|---|---|
| `cho_tim` | không | có | chờ việc nạp |
| `dang_tim` | không | có | việc nạp đang chạy; kẹt thì `tim-lai` gỡ (§7) |
| `da_tim` | **có** | có | bình thường |
| `loi_tim` | **có** (lượt 5) | có | gốc, tương tự đang theo dõi, thêm tay, ghim đều chụp; chủ bấm "Tìm lại" hoặc thêm tay để sửa |
| `ngung` | không | không | `nap` kết thúc `xong/nhom_ngung` |

**Ngân sách:** mỗi UID = **2 GET**; ngân sách = `2×N + (GET tìm)`. Nạp 1 nhóm đủ 11 UID ≈ 22 + 3–6 = 25–28 GET; chụp hằng ngày 1 nhóm = 22; 2 nhóm = 44. Trần 60.

### 6.3 Bảng dừng và lỗi

| Mã (`ly_do`) | Gặp khi | Việc | UI |
|---|---|---|---|
| `token_thieu` | không có file token | `tu_dung` | "Chưa có token EchoTik: đăng nhập EchoTik trên Chrome để tạo lại file token." |
| `token_het_han` | `text/html`, 401, 403 | `tu_dung`, ghi `token_tt` | "EchoTik trả trang lỗi: token hết hạn hoặc EchoTik từ chối tham số. Đăng nhập lại EchoTik trên máy nhà." |
| `rate_limit` | 429 | `tu_dung`, dừng ngay, không thử lại | "EchoTik giới hạn lượt gọi: thử lại ngày mai." |
| `het_han_muc_goi` | `goi_ngay.so_goi ≥ tran` | `tu_dung`; UID còn lại để mai | "Hết ngân sách gọi EchoTik hôm nay (n/60)." |
| `mang_lien_tiep` | 5 lỗi mạng liên tiếp sau thử lại | `tu_dung` | "Mất mạng tới EchoTik." |
| `keyword_khong_loc` | cổng §3.4 | nhóm `loi_tim` | "EchoTik không lọc theo từ khoá nên không tìm được tương tự: thêm tay UID." |
| `khong_tim_thay` | E1 404 hoặc `data` rỗng | UID `chup_uid.loi`, việc tiếp tục | "EchoTik không có UID này." |
| `khong_co_video` | E2 0 video | UID `loi`, tiếp tục | "EchoTik chưa có video nào cho UID này." |
| `dinh_dang` | JSON thiếu khoá bắt buộc | UID `loi`; ≥ 3 UID liên tiếp ⇒ `tu_dung` | "EchoTik trả dữ liệu lạ." |
| `khong_chup_duoc` | lượt `hang-ngay` đã **thử ≥ 1 UID** nhưng chụp `ok` = 0 (mọi UID hỏng từng cái: `khong_tim_thay`, `khong_co_video`, `dinh_dang` < 3 liên tiếp, `mang` < 5 liên tiếp). Không áp cho nhánh dừng có chủ đích ở các dòng trên (`rate_limit`, `token_*`, `het_han_muc_goi`, `mang_lien_tiep`, `dinh_dang` ≥ 3: vẫn `tu_dung`) và không áp khi không có UID nào cần chụp | lượt **`loi`** (không còn `xong` im lặng) | "Hôm nay không chụp được UID nào (EchoTik lỗi từng UID): xem lý do của từng UID hoặc bấm 'Chụp lại hôm nay'." (**việc còn lại:** câu này CHƯA có trong `TEN_LY_DO_RADAR`, `api.py:172-186`; phiếu code cần thêm khoá `khong_chup_duoc`; tới lúc đó UI dùng câu dự phòng) |
| `nhom_ngung` | chủ bấm "Ngừng theo dõi" giữa lúc `nap` đang chạy (hoặc nhóm đã `ngung` ngay lúc nhận việc) | việc `xong`, `ly_do="nhom_ngung"`; không ghi đè trạng thái nhóm; UID gốc đang `dang_chup` chốt `loi` `ma_loi="nhom_ngung"` | không có câu riêng (UI dùng câu dự phòng) |
| `khong_co_nhom` | `nap --goc` mà `goc` không có trong bảng `nhom` | lượt `loi`, **exit 1** | không có câu riêng |
| `loi_bat_ngo`, `tham_so_sai` | ngoại lệ không lường trước (log chỉ tên kiểu) / tham số dòng lệnh hoặc `viec_id`/`che_do` bị kho từ chối | lượt `loi`, **exit 1** (`tham_so_sai` không ghi `lan_chay` nếu chưa mở được lượt) | không có câu riêng |

Đã bỏ mã `ha_cap` (số đo cho thấy `per_page=50` đủ dùng; số phần tử ít không còn là bằng chứng hạ cấp). `tu_dung` ≠ `loi`: việc `xong`; ngày thiếu snapshot thành `GAP` nếu > 54 giờ. Lượt `loi` (`khong_chup_duoc`, `khong_co_nhom`, `loi_bat_ngo`, `tham_so_sai`) thì `kiem_dau_ra` = `chua` (§6.1).

**Ghi chú `TEN_LY_DO_RADAR` (`api.py:172-186`).** Bảng hiện có 12 khoá: `token_thieu`, `token_het_han`, `rate_limit`, `mang_lien_tiep`, `keyword_khong_loc`, `khong_tim_thay`, `khong_co_video`, `dinh_dang`, `nhom_ngung`, `khong_co_nhom`, `loi_bat_ngo`, `tham_so_sai`; `het_han_muc_goi` dựng riêng trong `ten_ly_do_radar` (`:191-195`) vì có số. **Việc còn lại (chưa làm ở thời điểm viết, `grep khong_chup_duoc tools/runner/*.py` không có kết quả):** thêm khoá `"khong_chup_duoc": "Hôm nay không chụp được UID nào (EchoTik lỗi từng UID): xem lý do của từng UID hoặc bấm 'Chụp lại hôm nay'."`. `api.py` thuộc phiếu RU-B8; phiếu đó hoặc phiếu sau phải thêm, và test `test_runner_radar_uid_api.py` nên có một ca `ten_ly_do_radar("khong_chup_duoc", 0, 60) != ""`.

### 6.3a Hành vi đã hiện thực ngoài đặc tả ban đầu (RU-B2, đọc từ code)

- **Mã lỗi của client EchoTik** (`echotik.py:32`, `LoiEchoTik.ma`): `token_thieu`, `token_het_han` (HTTP 401/403, hoặc `text/html`/thân bắt đầu bằng `<`), `rate_limit` (429), `khong_tim_thay` (404, hoặc E1 `data` rỗng), `dinh_dang` (HTTP khác 200 **kể cả 3xx: client không theo chuyển hướng**, §2.1; JSON hỏng, thiếu khoá `data`, UID sai dạng), `mang` (timeout/5xx/ngắt kết nối sau 2 lần thử lại, `_get` `:149-176`; mã HTTP → mã lỗi `_xu_ly` `:177-192`). `token_het_han|rate_limit` dừng cả lượt; `mang` cộng bộ đếm liên tiếp (5 ⇒ `mang_lien_tiep`); `dinh_dang` cộng bộ đếm (3 ⇒ `dinh_dang`); `khong_tim_thay` chỉ hỏng UID đó (`radar_uid.py:151-172`). Lỗi E1 hoặc E4 của lần nạp, và mọi lần dừng cả lượt (`_Dung`) giữa `nap`, chuyển nhóm sang `loi_tim` với `ly_do` = mã đó (`radar_uid.py:313`, `:337`, `:353`).
- **`ds_can_chup(ngay, goc=None)`** (`kho_radar_uid.py:562-584`): mặc định (`hang-ngay`) chỉ UID của nhóm `da_tim` **hoặc `loi_tim`** (`dk = "n.trang_thai IN ('da_tim','loi_tim')"` `:575`; RU-B7 lượt 5; nhóm `cho_tim/dang_tim/ngung` không chụp; vẫn bỏ UID `loai`); với `goc=<uid>` (luồng `nap`) lấy UID của riêng nhóm đó ở **mọi trạng thái trừ `ngung`**, để nạp chụp ngay sau khi tìm xong. Cả hai đều xoay (chụp `ok` cũ nhất trước) và bỏ UID đã `ok` hôm nay.
- **`ghi_tuong_tu` đọc khoá tuỳ chọn `do_giong`** của từng ứng viên (`kho_radar_uid.py:548-549`): số (không phải bool) được lưu vào `lien_ket.do_giong` (`float`), thiếu hoặc kiểu khác ⇒ `NULL`. `radar_uid.py:304` luôn thêm `do_giong` (làm tròn 4 chữ số) trước khi ghi; `UngVien` §7.2 không có khoá này nên kiểu vẫn nguyên.
- **`nap` khi nhóm `ngung`:** `_chay_nap` chỉ vào `dang_tim` nếu nhóm đang `cho_tim|dang_tim|da_tim|loi_tim`; nếu nhóm `ngung` thì lượt kết thúc `xong` với `ly_do="nhom_ngung"`, **không gọi EchoTik** (`radar_uid.py:329-333`). Chủ ngừng nhóm giữa chừng (sau E1 hoặc sau tìm) cũng ra `xong/nhom_ngung`, không ghi `tuong_tu` và không ghi đè `ngung` bằng `da_tim` (`:307-326`, test `test_runner_radar_uid_script.py:508-528`). `nap` cho `goc` không có nhóm: `khong_co_nhom`, exit 1 (bảng §6.3).
- **`so_goi` trong dòng JSON stdout** là **số GET của lượt này** (`_Lan.so_goi`, `radar_uid.py:100,112-117`), **không phải** tổng trong ngày; tổng ngày là `goi_hom_nay` của kho (`GET /radar/bang`: `han_muc.goi_hom_nay`). Chạy lại cùng `(ngay, che_do, viec_id)` đã `xong/tu_dung` thì in lại `ly_do` cũ với `so_uid=0` và `so_goi` đã lưu của lượt đó, không gọi mạng (`:424-426`).
- **Hạn chế đã biết (cũng ở §6.7 mục 6): khe hở compare-and-set.** `_chuyen_nhom` đọc trạng thái nhóm rồi mới ghi, không phải một giao dịch SQL (`radar_uid.py:268-275`). Nếu chủ bấm "Ngừng theo dõi" đúng vào khe vài mili-giây giữa đọc và ghi thì lần ghi đó có thể đè `ngung` bằng `da_tim`/`loi_tim`. Chấp nhận vì khe cỡ mili-giây (như ghi chú trong docstring `_chuyen_nhom`); hậu quả: nhóm quay lại `da_tim`, hôm sau vẫn bị chụp (tốn GET EchoTik, không tốn tiền) cho tới khi chủ bấm ngừng lần nữa; không mất dữ liệu. Muốn chữa phải để `dat_trang_thai_nhom` nhận tập trạng thái cho phép và `UPDATE … WHERE trang_thai IN (…)` trong một giao dịch (`kho_radar_uid.py:495`; phiếu sau, không làm ở đợt này).


### 6.4 Hạn mức (`han_muc.py:43-46`, `han_muc_radar` `:136-140`, `_kiem_radar_uid` `:403-415`; `cau_hinh.json` chỉ hạ, đọc một lần lúc khởi động như D15)

- `radar_uid_bat` (1; **0 = cầu dao**: tắt lịch + tắt tạo việc, API ghi trả 409 "Radar UID đang tắt").
- `radar_uid_goi_ngay` = **60** (trần là **hằng trong code**; `cau_hinh.json` chỉ hạ, như D5/D15).
- `radar_uid_chay_ngay` = **6**: đếm **mọi** việc `radar_uid_*` do API tạo (nạp, tìm lại, chụp lại); việc hẹn giờ (`boi="he_thong"`) không đếm. Vượt ⇒ `VuotHanMuc` ⇒ 429.
- **Lý do 60 (suy diễn, C7 chưa đo):** `GHI_CHU_ECHOTIK.md:142` nói gói Free ≈ 100 trang chi tiết/ngày, nhưng đó là mô tả collector creator-videos khác, **không** phải số đo của endpoint này; token dùng chung với `phantichsanpham` (≈ 4 GET/lần phân tích). Các GET của RU-0/Phụ lục A chạy tay, **không đi qua `goi_ngay`** nên không tính vào 60. **Ngày đầu chỉ nạp 1 UID gốc.** **Cách nâng:** sau ≥ 3 ngày chạy, nếu không gặp 429 và `goi_hom_nay` max < 40, trưởng phòng đề xuất phiếu đổi hằng code lên 100 và `GOC_TOI_DA` lên 3, `UID_TOI_DA` lên 36 (cần review + cài lại D8); C7 chỉ đóng khi có số đo nhiều ngày.

### 6.5 Idempotent, khởi động lại, mọi lớp thử lại

- `chup_uid(uid, ngay)`: chạy lại cùng ngày bỏ qua UID `ok`; `dang_chup`/`loi` chụp lại tối đa `so_lan_thu = 2`/ngày. Đọc không hoàn tác: chỉ tốn ngân sách (đã đếm trước). Kết quả lấy từ `chup_uid`/`lan_chay`, không từ stdout; không tự đưa việc "về chờ" chỉ vì không thấy kết quả.
- D6: sau khởi động lại runner, `kiem_dau_ra` (`quyet_dinh_sau_khoi_dong`, tối đa 3 lần): `xong` hoặc chạy lại (idempotent).
- **Mọi lớp thử lại:** (1) `EchoTik._get` (`echotik.py:149-175`) ≤ 2 lần cho timeout/5xx/ngắt kết nối, chờ 3 s rồi 6 s, mỗi lần tính ngân sách; 4xx, 429, HTML và **3xx (chặn redirect, `dinh_dang`)** **không** thử lại. (2) D6 ≤ 3 lần. (3) `_hen_gio` không thử lại trong ngày sau `TrungViec/VuotHanMuc/ThamSoLoi` (`vong_lap.py:1423-1427`). (4) Worker, video_server, `goiMayNha` (`worker.js:491-511`): không thử lại; web không tự gửi lại POST.
- Máy tắt cả ngày: không bù; ngày sau hiện `GAP` nếu > 54 giờ.
- **Nhóm kẹt `dang_tim` (RU-B8, lượt 5).** Việc `radar_uid_nap` có thể chết giữa chừng (huỷ, hết lần thử, runner sập) làm nhóm kẹt `dang_tim` mãi mà không việc nào sẽ đổi nó. `POST tim-lai` (§7 dòng 4) xử lý: nhóm `dang_tim` **mà không có việc `radar_uid_nap` mở cùng khoá** ⇒ coi là kẹt, gỡ (kho cấm `dang_tim → cho_tim` trực tiếp nên đi `dang_tim → loi_tim → cho_tim`, hai bước trong cùng `khoa_ghi` và cùng lần kiểm "không có việc mở", `api.py:1340-1352` (hàm `p_radar_tim_lai` từ `:1328`)), ghi `log.warning` rồi tạo việc nạp mới bình thường; nhóm `dang_tim` **mà có việc nạp mở** ⇒ 409 "Nhóm đang được tìm: chờ xong" như cũ. Khởi động lại runner không tự gỡ kẹt: chỉ chủ bấm "Tìm lại" hoặc việc nạp chạy lại theo D6 mới đổi nhóm. Lưu ý: gỡ kẹt không phải bước có tác dụng ngoài không hoàn tác (chỉ đổi trạng thái nhóm + tạo việc đọc EchoTik, có kiểm hạn mức trước khi đổi).

### 6.6 Token

- Đọc từ `--token-file` (mặc định `E:\timsanpham\.echotik_token.json`, env `KHO_ECHOTIK_TOKEN_FILE`; `vong_lap.py:113`, `:471`, `kieu.py:143` `MoiTruong.echotik_token_file`. Biến môi trường được ưu tiên; không đặt thì dùng đường dẫn mặc định **chỉ khi thư mục runner là mặc định** (`vong_lap.py:455-459`, như `KHO_THU_MUC_VIEW`); thư mục runner tạm không đặt biến thì `echotik_token_file=None` và `_buoc_radar_uid` báo `ThamSoLoi` (không tự đoán đường dẫn, `danh_muc.py:1041-1042`)) **mỗi lần gọi**, cache theo `(đường dẫn, mtime)`. Token **không** vào argv (chỉ đường dẫn), env, DB, `ket_qua`, log, stdout, thông báo lỗi, `su_kien`; ngoại lệ chỉ tên kiểu + mã HTTP; không log thân phản hồi lỗi.
- Thêm `Read(//E:/timsanpham/.echotik_token.json)` vào `_CONG_CU_CAM_CO_DINH` (`danh_muc.py:143`): chỉ **giảm chạm nhầm** của phiên Claude cùng user (như D7), **không phải bảo vệ**.

### 6.7 Hạn chế đã biết (R-RU3, review toàn bộ; ghi thẳng, KHÔNG sửa ở lượt 5)

Reviewer R-RU3 còn các mục mức P3 dưới đây; chủ kho cần biết để không đọc quá mức bảng xếp hạng:

1. **Tiêu chí 3 (ads) không có suy luận.** `NGUONG["ADS_BAT"] = False` (`radar_uid_tinh.py:49`, D16): cờ `NGHI_ADS` không bao giờ bật; UI chỉ hiện số thô `is_promote x/y (chưa rõ nghĩa)`. Chủ không nhận được nhãn "nghi ads" nào, dù thiết kế ban đầu của hội đồng có tiêu chí này (§5.3).
2. **Log hạ nguồn thiếu ngữ cảnh.** Các dòng `log` của runner/API cho Radar thiếu `viec_id` và `boi` ở một số nhánh; bảng `su_kien` **không ghi** hành động `tim-lai` và `chup-lai` (chỉ các lệnh còn lại, §4 `su_kien`). Muốn truy "ai bấm Tìm lại/Chụp lại lúc nào" phải tra log Worker/runner, không tra được ở `radar_uid.db`.
3. **`them-tay` API không kiểm trạng thái nhóm.** `KhoRadarUid.them_tay` (`kho_radar_uid.py:392-415`) chỉ kiểm nhóm có tồn tại (`_can_nhom`), không kiểm `ngung`: thêm tay vào nhóm đã ngừng được chấp nhận (UID nằm đó, không bị chụp tới khi bật theo dõi lại). Không mất tiền, không sai dữ liệu; chỉ gây bất ngờ UI.
4. **Sai số rút gọn "K" cố định ±5.** `doc_so_rut_gon` (§5.1) giả định hai chữ số thập phân (`'21.81K'` ⇒ ±5). Nếu EchoTik trả `'1.2K'` (một chữ số thập phân) thì sai số thật là **±50**, hai lần đọc K có `sai_so_tong` = 10 ≤ 20 nên §5.1 (dòng "Video đo được trong kỳ") giữ Δ mà **không kiểm `|Δ|`**, và không bắt được Δ giả cỡ vài chục view (thật là ±100). Chưa đo EchoTik có trả dạng một chữ số hay không; chỉ số chính là trung vị nên ảnh hưởng nhỏ, nhưng Δ nhỏ của video nhỏ có thể sai.
5. **Ngân sách thời gian có thể vượt `het_gio_s`.** Một lượt 60 GET, mỗi GET timeout 30 s (`TIMEOUT_S`, `echotik.py:25`) × 3 lần thử (1 + 2 thử lại, chờ 3 s + 6 s, `:27`) ⇒ ≈ 60 × (90 + 9) s ≈ 5.940 s ≫ `het_gio_s` 1200 s khi mạng hỏng liên tục. Thực tế bộ đếm `mang_lien_tiep` (5 lỗi liên tiếp) dừng lượt sớm hơn nhiều, nhưng nếu lỗi mạng xen kẽ với GET thành công thì lượt có thể hết giờ. Việc có `tu_chay_lai=True` nên được chạy lại (idempotent, §6.5); chưa có số đo thực.
6. **Khe hở compare-and-set chuyển trạng thái nhóm** (`radar_uid.py:268-275`, chi tiết ở §6.3a): đọc rồi ghi không cùng một giao dịch SQL; hậu quả cỡ mili-giây đã nêu; chữa bằng `UPDATE … WHERE trang_thai IN (…)` ở phiếu sau.
7. **Trần 100/ngày của EchoTik Free là suy diễn.** Con số từ `GHI_CHU_ECHOTIK.md:142` mô tả collector khác; **C7 chưa đo** (không có 429 trong 7 GET của RU-0). Trần 60 GET/ngày của Radar (§6.4) và việc "nâng lên 100" đều dựa vào suy diễn đó; chỉ coi là đo được sau nhiều ngày `goi_hom_nay` thật.

---

## 7. API

Đường: `api("radar/...")` → Worker `/api/radar/*` (`cf/src/radar.js`, móc ở `worker.js:958`, import `:9`) → `/r/radar/*` → runner `/radar/*`. Mọi gọi qua `goiMayNha` (`worker.js:491`), POST ký D7, `boi` Worker dựng từ phiên (bỏ mọi khoá khác của body, chỉ nhận `uid` đúng `^\d{19}$`).

| # | Web | PT | Runner | Body | Phản hồi OK | Lỗi |
|---|---|---|---|---|---|---|
| 1 | `/api/radar/bang` | GET | `/radar/bang` | – | 200 `Bang`; `ds` của mỗi nhóm **gồm cả UID `trang_thai="loai"`, xếp cuối** (`api.py:194-203`, `:1249-1252`; test `test_runner_radar_uid_api.py:291-309`) | 401 · 403 "Không có quyền" · 502 "Máy nhà không trả lời…" · 503 "Chưa cấu hình bộ chạy việc" / "Radar UID chưa bật" · 504 |
| 2 | `/api/radar/uid/<uid>` | GET | `/radar/uid/<uid>` | – | 200 `ChiTiet` | như 1 + 404 "Không có UID này trong Radar" (uid sai dạng cũng 404 ở 3 chặng) |
| 3 | `/api/radar/goc` | POST | `/radar/goc` | `{uid}` | 202 `{da_co, goc, viec_id}` | 400 "UID phải đủ 19 chữ số" · 409 "Đã đủ 2 UID gốc: ngừng bớt" · 409 "Đã đủ 24 UID theo dõi" · 409 "Radar UID đang tắt" · 429 "Vượt hạn mức" · 413/415 |
| 4 | `/api/radar/goc/<goc>/tim-lai` | POST | cùng | – | 202 `{viec_id}` | 404 · 409 "Nhóm đang được tìm: chờ xong" (**có việc `radar_uid_nap` mở cùng khoá**, kiểm đầu tiên; nhóm `dang_tim` mà **không** có việc mở là kẹt ⇒ **không 409**: đặt lại `cho_tim` rồi tạo việc mới, §6.5, `api.py:1340-1352` (hàm `p_radar_tim_lai` từ `:1328`); test: phiếu RU-B8) · **409 "Nhóm đã ngừng: bật theo dõi lại trước"** (nhóm `ngung`; kiểm sau kiểm "có việc mở", trước hạn mức; `api.py:163`, `:1342-1343`; test `:505-510`) · 429 |
| 5 | `/api/radar/goc/<goc>/ngung` · `/theo-lai` | POST | cùng | – | 200 `{goc, trang_thai}` | 404 · 409 (theo-lai vượt 2 gốc) |
| 6 | `/api/radar/goc/<goc>/them-tay` | POST | cùng | `{uid}` | 200 | 400 · 404 · 409 "Đã đủ 3 UID thêm tay" · 409 "Đã đủ 24 UID theo dõi" · 409 "UID này đang bị loại: bỏ loại trước" |
| 7 | `/api/radar/goc/<goc>/uid/<uid>/(ghim\|bo-ghim\|loai\|bo-loai)` | POST | cùng | – | 200 `{uid, trang_thai}` | 404 · 409 "Không đổi được UID gốc" · 409 "Đã đủ 10 UID tương tự" |
| 8 | `/api/radar/chup-lai` | POST | `/radar/chup-lai` | – | 202 `{viec_id}` | 409 "Đang có lượt chụp chạy" (có việc `radar_uid_hang_ngay` mở cho hôm nay, kể cả lượt hẹn giờ; hoặc `TrungViec`) · 409 "Radar UID đang tắt" · 429 "Vượt hạn mức (6 việc/ngày)" (`api.py:1392-1408`) |

**Hành vi của `theo-lai` ngoài bảng (`api.py:1368-1382`, test `test_runner_radar_uid_api.py:554-570`).** `theo-lai` đưa nhóm về `da_tim` nếu nhóm từng tìm xong (`tim_luc` có), về `cho_tim` nếu chưa (`kho_radar_uid.py:489`). Chỉ khi nhóm **vừa từ `ngung` sang `cho_tim`** (chưa từng tìm xong: không ai sẽ nạp nó), API **tự tạo việc `radar_uid_nap`** (khoá = `goc`, qua `_tao_viec_da_khoa`, tính vào `radar_uid_chay_ngay`). Nếu hết hạn mức hoặc đã có việc nạp mở (`VuotHanMuc`, `TrungViec`, `ThamSoLoi`) thì **không lỗi**: ghi `log.warning("radar: theo-lai … không tạo được việc nạp …")`, vẫn trả 200 `{goc, trang_thai: "cho_tim"}`, nhóm giữ `cho_tim` và chủ bấm "Tìm lại" sau. Không tạo việc trùng.

- **Quyền:** `laChuKho(phien.user)` (`worker.js:183`) trước mọi gọi máy nhà (403 trước, như `hoc.js:61`). POST: `Origin === url.origin` (như `hoc.js:88`), body ≤ 16 KB (`video_server.py:151`), `content-type: application/json` khi có body.
- **video_server (`RE_R`, `:139-143`)** thêm `|radar/(bang|chup-lai|uid/\d{19}|goc|goc/\d{19}/(tim-lai|ngung|theo-lai|them-tay)|goc/\d{19}/uid/\d{19}/(ghim|bo-ghim|loai|bo-loai))`; GET cho `bang` và `uid/<uid>`, POST cho phần còn lại (sai ⇒ 405); không nới `R_QUERY_KHOA`. `RUNNER_TIMEOUT = 10` s (`:138`): `GET bang` chỉ đọc SQLite (< 1 s), **không** gọi EchoTik trong request.
- **Runner (`api.py`):** 8 nhánh cạnh `/hoc/*`: hằng + hàm sắp/dựng `UidRa` `:158-222`; handler `g_radar_bang` `:1254`, `g_radar_uid` `:1278`, `p_radar_goc` `:1309`, `p_radar_tim_lai` `:1331`, `p_radar_nhom` `:1357`, `p_radar_uid` `:1385`, `p_radar_chup_lai` `:1392`; điều phối GET `:1509-1512`, POST `:1542-1551`; `kho_radar=None` ⇒ 503 `LOI_RADAR_CHUA_BAT`; mọi lệnh ghi vào `su_kien`.
- **Id 19 số:** chuỗi ở mọi chặng; cấm `Number(uid)`, `parseInt`. Test web dùng `"1729706628656957720"` (> 2^53).

### 7.1 Dạng dữ liệu (cố định)

```jsonc
// GET /radar/bang
{ "luc": "2026-11-23T10:12:00+07:00", "ngay": "2026-11-23",
  "token": {"trang_thai": "ok|thieu|het_han|chua_kiem", "cau": ""},
  "han_muc": {"bat": 1, "goi_ngay_toi_da": 60, "goi_hom_nay": 22, "goc_toi_da": 2},
  "lan": {"trang_thai": "xong|tu_dung|loi|dang_chay|chua_chay", "ly_do": "", "ngay": "2026-11-23", "ten_ly_do": ""},
  "nhom": [ { "goc": "1737422436677814024", "ten": "…", "trang_thai": "cho_tim|dang_tim|da_tim|loi_tim|ngung",
              "ly_do": "", "ten_ly_do": "", "tim_luc": "…", "bat_dau_ngay": "2026-11-20", "ds": [ /* UidRa, sắp §5.4 */ ] } ] }

// UidRa (số: number|null; id: chuỗi)
{ "uid": "…", "vai": "goc|tuong_tu|them_tay", "trang_thai": "dang_theo|ghim|loai", "ten": "…", "shop": "…", "do_giong": 0.67,
  "xep_loai": "dang_co_da|chua_co_da|chua_du|chan", "uu_tien": "thuong|ha", "tam": false,
  "trung_vi": 700, "trung_vi_truoc": 520,                          // null khi KHONG_LAM_MOI/GAP/không tính được
  "tong_delta_top5": 9200, "tong_delta_top5_truoc": 1600,
  "tang_toc": 5.75, "tang_dot_ngot": true, "ly_do_tang_toc": "",   // tang_toc null ⇒ ly_do_tang_toc ("kỳ trước GAP", "chưa có kỳ trước")
  "n_video": 11, "n_creator": 6, "n_doi": 10, "ti_le_doi": 90.9,    // n_video/n_creator: tập "đang sống"; ti_le_doi chỉ để hiển thị
  "view_nho_trung_vi": 7200, "n_creator_nho": 5, "cau_view_nho": "", // không có video ≤ 14 ngày ⇒ view_nho_trung_vi null, "không có video ≤ 14 ngày"
  "view_nho_30_trung_vi": 6800, "n_creator_nho_30": 7, "follower_khong_doc": 1,
  "trung_vi_14": 640, "n_video_14": 9,
  "n_video_moi_30": 4, "cau_video_moi": "",                       // = 0 ⇒ "Không có video mới 30 ngày"
  "promote_x": 1, "promote_y": 39,
  "spark": [null, 320, 520, 700], "d_ban_ngay": 14.2, "creator_moi_ngay": 1.5,
  "gia": "499.390₫", "hoa_hong": "10%", "ton": "562",
  "du_lieu_luc": "2026-11-23T10:01:00+07:00", "echotik_cap_nhat": "2026-11-22 07:55", "so_snapshot": 4, "phu_gio": 72.2,
  "co": ["GAP"], "co_canh_bao": ["MOT_CREATOR_CHI_PHOI"], "ly_do_thieu": ["so_snapshot 2/4"], "duoi_do_phan_giai": 1 }
```

`ChiTiet` = `UidRa` + `chuoi` (mỗi kỳ gần nhất ≤ 14: `{ngay, gio, hop_le, trung_vi, tong_delta_top5, n_video, n_creator, n_doi, ti_le_doi}`) + `video` (≤ 50 của snapshot mới nhất: `{video_id, creator, follower, view, d24|null, dang_luc, is_promote|null}`).

### 7.2 Kiểu dùng chung (nguyên văn; mỗi module khai báo bản của mình, TypedDict là cấu trúc nên không cần import chéo; RU-B3 có test so khoá)

```python
class HangVideo(TypedDict):      # sau echotik.chuan_video()
    video_id: str; creator: str; follower: str | None; view: str; ban: str | None; dang_luc: str; is_promote: int | None
class Snapshot(TypedDict):       # sau kho.doc_snapshots()
    uid: str; ngay: str; lay_luc: str; echotik_cap_nhat: str | None; ban_tong: str | None
    gia: str | None; hoa_hong: str | None; ton: str | None; tong_creator: str | None
    so_trang: int; tong_trang: int | None; videos: dict[str, HangVideo]
class MetaTrang(TypedDict):      # từ khoá "meta" của EchoTik; thiếu = None
    current_page: int | None; last_page: int | None
class UngVien(TypedDict):        # sau echotik.chuan_ung_vien()
    uid: str; ten: str; gia: str | None; ban_7d: str | None      # gia = avg_price nguyên văn
class KetQuaTimKiem(TypedDict):
    ds: list[UngVien]; meta: MetaTrang
```

---

## 8. Giao diện tab

**Menu (đã hiện thực).** `web/khung.js`: `mnMENU` (`:9-16`) có cuối mảng `{ ma: "theo-doi", href: "#/theo-doi", ic: "📡", ten: "Radar UID", ngan: "Radar" }`; `mnPhanTichHash` (`:22`) có `#/theo-doi` ⇒ `{trang:"theo-doi", id:""}` (`:28`); `mnMuc` (`:40-42`) có `"theo-doi": "theo-doi"`; `mnRoute` (`:82-95`): **dòng đầu gọi `rduDung()` qua `typeof` (`:84`) ở MỌI lần đổi route**, danh sách trang có `"theo-doi"` (`:86`), nhánh `rduRender(phien)` qua `typeof` (`:95`). Menu chủ kho nay đúng **6 mục**: Hôm nay · Sản phẩm · Cần quay · Máy nhà · Poster V2 · Radar UID. Người thường: `CHI_CHU_HTML` (`:85`); menu người thường đúng 1 mục (`:47`). Thanh đáy 6 ô (`menu.css` `minmax(0, 1fr)`), không sửa `menu.css`.

**Nạp script.** `web/radar-uid.js` đặt **sau `sua.js`** trong `index.html`: `app.js` khởi động ở `DOMContentLoaded` (`app.js:755`), khi mọi script `defer` đã chạy; vị trí cuối không làm vỡ regex liền kề (`homnay-web:327`, `hoc-web:460`, `sua-web:293`, `poster-web:780`).

**Tên cấp đỉnh:** tiền tố `rdu` (đã dò: không tên nào trong `web/*.js` bắt đầu `rdu`). Khối thuần `// --- radar-uid-thuan start/end ---`. CSP `script-src 'self'`: không inline, sự kiện bằng `addEventListener`. CSS: khối `.rdu-*` nối cuối `web/style.css` (không thêm file CSS: `menu-web.test.mjs:410` đòi đúng 3 CSS), không `style="…"`, không `<table>` (375px không cuộn ngang): hàng là thẻ lưới.

**Khung trang:** tiêu đề, "↻ Tải lại", ô nhập UID + "Theo dõi", dòng nhắc cố định *"Sản phẩm 'tương tự' chọn theo từ khoá tên + giá, chưa chứng minh trùng SKU. Bảng cho thấy tín hiệu, không phải kết luận TikTok đang đẩy."*, banner token/lỗi (§6.3), mỗi nhóm một khối.

**Hàng UID** (mỗi chỉ số một cột/ô riêng): `uid` + shop + nhãn vai · **trung vị Δview/video/24h** (chính, lớn nhất; xám + "chưa đủ bằng chứng (n=…, k/4 snapshot)" khi `tam`; số thô khi `KHONG_LAM_MOI`) · sparkline · **tăng tốc** "×5,75 (đột ngột / không) · top 5 = 9.200" (hoặc "—" kèm `ly_do_tang_toc`) · **view creator nhỏ** "trung vị 7.200 · 5 creator < 10K follower (≤ 14 ngày)" (hoặc "không có video ≤ 14 ngày"; kèm dòng phụ ≤ 30 ngày) · "n video đang sống · n creator" · ô **"View đổi"** `"view đổi {n_doi} video ({ti_le_doi}%)"` (`rduODoi`, `web/radar-uid.js:179-185`; RU-W5, lượt 5; bản trước ghi "n_doi/promote_y", **không còn**: `n_doi` và `ti_le_doi` cùng đo trên video có mặt ở cả hai snapshot, còn `promote_y` đếm video của snapshot mới nhất nên khác mẫu số; thiếu một trong hai ⇒ "view đổi — (chưa đo được ở cả hai snapshot)") · video mới 30 ngày (hoặc "Không có video mới 30 ngày") · Δ bán/ngày · creator mới/ngày · giá / hoa hồng / tồn · ô **riêng** "is_promote x/y (chưa rõ nghĩa)" (`radar-uid.js:254`, `promote_x`/`promote_y`, không trộn với ô "View đổi") · "dữ liệu lúc … · phủ … giờ · k snapshot" · cờ (chặn đỏ, cảnh báo vàng) · "📮 Poster" · "Ghim / Loại". Thiếu = `—`. Khối "Ít dữ liệu" và "Đã loại" thu gọn.

**UID đã loại trên web (`web/radar-uid.js:228-254`, `:262-285`, `web/style.css:380`).** `GET /radar/bang` trả cả UID `loai` (§7); web tách chúng khỏi danh sách chính, gom vào `<details>` "Đã loại (n)" thu gọn mặc định; hàng có lớp `rdu-loai` (làm mờ `opacity: .6`), nhãn " · đã loại", **chỉ còn nút "Bỏ loại"** (không "📮 Poster", không "Ghim/Loại"). UID gốc không bao giờ có nút loại (`rduChoPhep`, `:130-138`).

**Nút "Chụp lại hôm nay" (`radar-uid.js:399`, `:511-514`).** Ở đầu trang, cạnh "↻ Tải lại". Bấm → hộp xác nhận `confirm("Chụp lại tất cả UID hôm nay? Việc này tốn ngân sách gọi EchoTik (khoảng 2 lượt mỗi UID).")`; huỷ thì không gọi gì; đồng ý thì `POST radar/chup-lai` (§7 dòng 8) qua `rduGui` (khoá nút trước `await`). Tạo một lượt `radar_uid_hang_ngay` cho hôm nay: UID đã `ok` hôm nay bị bỏ qua, chỉ chụp phần lỗi/chưa chụp (idempotent, §6.5).

**`rduDung()` (`radar-uid.js:387-391`).** Huỷ hẹn giờ hỏi lại 10 s (`rduHen`) và tăng `rduLuot` để bỏ kết quả muộn của lần tải đang chờ. `mnRoute` gọi ở đầu mọi lần đổi route (`khung.js:84`), nên rời `#/theo-doi` thì không còn timer chạy ngầm; `rduRender` cũng gọi lại ở đầu (`:395`).

**Trạng thái:** rỗng (giới thiệu + ô nhập); đang tải; lỗi API (một dòng `hn-bao`, câu §6.3/§7, không hiện HTML); nhóm `cho_tim`/`dang_tim` "Đang tìm/Đang chờ máy nhà…" (hỏi lại 10 s khi còn ở trang, bỏ kết quả muộn bằng `phienCT` như `hoc.js:377`); `loi_tim`: lý do + "Tìm lại" + ô thêm tay.

**Chống lỗi bấm:** khoá nút TRƯỚC `await` (như `hoc.js:374`, `:405`); `Set` hành động đang gửi; 409/429 hiện đúng câu §7; mạng đứt giữa POST ⇒ giữ khoá tới lần tải thành công kế.

**XSS:** mọi chuỗi từ API qua `esc` (`app.js:9`); `uid` vào `data-rdu-uid`/URL chỉ sau `^\d{19}$`; số qua `Number.isFinite`; test chèn `"><img src=x onerror=1>` vào mọi trường.

**Nhãn việc:** `web/viec.js:13` (`TEN_LOAI_VIEC`), `web/loi.js:26-27` (`LOI_LOAI_VIEC`) thêm `radar_uid_hang_ngay: "Chụp Radar UID mỗi ngày"`, `radar_uid_nap: "Nạp UID vào Radar"`.

**Test hiện hành phải sửa (đã đọc) và `?v` phải nâng:**

| File | Dòng | Sửa |
|---|---|---|
| `cf/test/menu-web.test.mjs` | `:60`, `:63-66` | mảng thêm `["#/theo-doi","theo-doi","Radar UID"]`; `5` → `6` (hai chỗ); tiêu đề |
| | `:164-166`, `:283` | `5` → `6` |
| | `:408-413` | danh sách script thêm `"radar-uid.js"` sau `"sua.js"` |
| | `:431` | `TIEN_TO` thêm `"radar-uid.js": "rdu"` |
| `cf/test/poster-web.test.mjs` | `:728`, `:739`, `:740` | tiêu đề; `5` → `6`; regex `…<\/a>$` bỏ neo `$` |
| | **`:782`** | ghim `khung\.js\?v=5"` ⇒ đổi `v=6` (khung.js đổi nên phải nâng) |
| `cf/test/homnay-web.test.mjs` | `:956`, `:971` | tiêu đề; `5` → `6` |
| `.culiapp/kiem-chung.py` | mảng `LENH` | thêm test mới (trưởng phòng, RU-T1) |

`?v` phải nâng: `style.css` 20 → 21, `khung.js` 5 → 6, `viec.js` 17 → 18, `loi.js` 7 → 8; thêm `radar-uid.js?v=1` và dòng `<script>` ở `index.html`. Test ghim `?v` đã tìm: chỉ `poster-web:782`; RU-W2 chỉ chạy 4 file test nêu ở phiếu, còn chạy toàn bộ `cf/test/*.test.mjs` để bắt ghim còn sót là việc của RU-T1 (sau khi RU-W1 xong). Không vỡ (đã đối chiếu): `homnay-web:327`, `hoc-web:460`, `sua-web:293`, `poster-web:780`.

---

## 9. Luồng nhập UID và quản lý danh sách

1. Chủ dán UID (cả link chứa `/product/<19 số>`, `/pdp/<19 số>`, ý như `lay_du_lieu.py:59-66`, không đi theo link rút gọn). Sai dạng: báo ngay, không gọi API.
2. `POST /api/radar/goc {uid}` ⇒ runner ghi `san_pham`, `nhom(cho_tim)`, `lien_ket(goc,goc,'goc','dang_theo')`, tạo việc `radar_uid_nap` (khoá = `goc`), trả 202. UID đã có: `da_co:true`, không tạo việc.
3. Việc nạp tìm tương tự và chụp snapshot đầu (§6.2). Trang tự hỏi lại.
4. `them-tay` (≤ 3, UID chưa bị loại); `ghim` (giữ qua "Tìm lại"); `loai` (ngừng chụp, không bị "Tìm lại" chọn lại; web gom vào khối "Đã loại" thu gọn, hàng làm mờ, chỉ còn nút "Bỏ loại"; `bo-loai` hoàn tác; `GET /radar/bang` vẫn trả UID loại ở cuối `ds`, §7); `ngung` cả nhóm (giữ dữ liệu; `theo-lai` bật lại, trong giới hạn 2 gốc). Không xoá cứng (như D14).
5. "Tìm lại": thay các `tuong_tu` không ghim bằng danh sách mới; UID bị thay thôi chụp (dữ liệu cũ giữ). UID gốc không `loai` được (409), chỉ `ngung` cả nhóm.

---

## 10. Nút Poster: làm gì và vì sao

**Đã đọc trực tiếp:**
- `PATCH /api/v2/folders/{id}` nhận cột trong `ALLOWED_FOLDER_COLUMNS` (gồm `product_id`, `product_id_active`; `folders.py:20-42`), **ghi đè nguyên chuỗi** (`:316-326`).
- `pick_product` (`product_pool.py:39-87`): ≥ 2 ID đang tick ⇒ chọn **ngẫu nhiên trong nhóm ít dùng nhất 7 ngày** (`:68-84`). Thêm UID vào folder của sản phẩm khác sẽ **gắn sai sản phẩm vào video**.
- Trang Folders web đã có ô "TikTok Shop Product IDs" và ô tick (`web/pv-folders.js:318`, `docs/poster-v2-tren-web.md:382-385`).
- Không có luồng "UID → folder" trong `/api/viec`: `poster_day_folder` tạo folder từ **dự án đã có video** (`giao-dien-menu-trai.md` §4.4); UID mới chưa có video thì chưa có gì để đưa sang.

**Quyết định (Q1 = a, đã chốt trưởng phòng): không có đường ghi tự động.** Nút "📮 Poster" mở khung nhỏ:
- **Sao chép UID** (`navigator.clipboard.writeText`, dự phòng `textarea` + `execCommand("copy")`).
- **Mở Poster V2 › Folders** (`#/poster/folders`; `pvTRANG` có `["Folders","folders"]`, `web/poster.js:11`).
- Hướng dẫn: "Chỉ dán vào folder có video **của đúng sản phẩm này** (ô Product IDs, mỗi dòng một mã). Đừng thêm vào folder đang đăng sản phẩm khác: Poster sẽ chia đều video giữa các ID đang tick."
- UID `vai ≠ goc`: **ô tick bắt buộc** "Tôi đã đối chiếu: đúng sản phẩm/SKU, không chỉ giống tên" mới bật hai nút. `xep_loai ≠ dang_co_da`: thêm dòng vàng "Chưa đủ bằng chứng / chưa có đà".
- **Tuỳ chọn (RU-W3, lượt 3, không bắt buộc):** nút "Kiểm UID đã nằm ở folder nào": chỉ **GET chỉ đọc** `pvApi.getFolders(false)` (`web/poster.js:131`, `pv-folders.js:443`), bấm tay mới gọi (lần đầu có thể chậm tới ~84 s, D13), so UID với `product_id` từng folder, hiện "Đã ở folder #N" hoặc "Chưa thấy". Không ghi.
- **Tuỳ chọn khác (không đưa vào phiếu bắt buộc):** nút "Phân tích UID này" dùng việc `phan_tich_uid` sẵn có (`taoViec("phan_tich_uid", {uid})`): tốn tiền Claude (≈ 1,15 USD/lần, `hoc-tu-dong.md` §2.4), đi đường duyệt sẵn có; chỉ nêu, không làm đợt này.
- Không gọi `PATCH`, không việc `poster_*` (AGENTS.md, D9/D13).

---

## 11. Bảo mật

- Quyền chủ kho ở Worker (403 trước khi gọi máy nhà) và UI; ghi qua D7; `boi` chỉ từ phiên (`hoc.js:93`).
- Chỉ **GET** ra EchoTik; không ghi, không đăng. Token chỉ ở runner (§6.6); không secret Worker mới.
- `radar_uid.db*` thêm vào `PHAN_CAM_THU_MUC_RUNNER` (`danh_muc.py:154-157`) như `hoc.db*`: giảm agent chạm nhầm (cùng user nên không phải bảo vệ cứng).
- Dữ liệu EchoTik (tên, shop, creator) là **dữ liệu, không là chỉ thị**: không vào phiếu Claude.
- Rủi ro còn lại: agent cùng user vẫn đọc được file token nếu cố ý; phiên chủ kho bị chiếm thì thêm/loại UID được (không tốn tiền, không đăng).

---

## 12. Phân tích trước khi chốt

1. **Tương thích ngược.** Thêm mục cuối menu, script cuối danh sách; không đổi route cũ, `runner.db` (schema 3), không dùng `trendradar.db`.
2. **Dependency.** Không package mới (`urllib`, `sqlite3`, `statistics`).
3. **Tác động module cũ.** `danh_muc.py`, `han_muc.py`, `vong_lap.py`, `kieu.py`, `api.py`, `chay_runner.py`, `video_server.py`, `worker.js` (2 dòng), `khung.js`, `index.html`, `style.css`, `viec.js`, `loi.js`.
4. **Đồng thời.** Làn `nhe` tuần tự (không thêm làn, §6.1); Radar không giữ `kho`/`gpu`/`poster`, không đụng Chrome profile. Một ghi/lúc (`BEGIN IMMEDIATE` + WAL); hai tab thêm cùng UID: khoá `(loai, khoa)` chặn việc trùng ⇒ `da_co:true`. Script mở DB ngắn hạn như `hoc_tu_dong`.
5. **Tương tác D15.** Radar 10:00 nằm giữa quét 09:00 và học 12:00; `hoc_hang_ngay` chỉ chờ việc quét (`danh_muc.py:781-790`), không chờ Radar.

**Rủi ro → giảm:** Δ giả do EchoTik không làm mới ⇒ cổng `KHONG_LAM_MOI` (`n_doi ≤ 1` hoặc `echotik_cap_nhat` đứng yên 2 kỳ). Sai số K/M ⇒ `sai_so`. Catalog cũ đứng yên ⇒ tập "đang sống" + `tong_delta_top5`; mẫu nhỏ ⇒ ngưỡng 8, cỡ mẫu và lý do hiện kèm. Đọc nhầm tín hiệu thành kết luận ⇒ nhãn "đáng thử (tín hiệu)", dòng nhắc, cần đạt hai tiêu chí. Tương tự sai SKU ⇒ nhãn, ô tick, không ghi Poster. Hết hạn mức EchoTik ⇒ ngân sách trước-khi-gọi, trần 60, `tu_dung`. Ngưỡng sai ⇒ một bảng `NGUONG`, xem lại sau 14 ngày.

---

## 13. Kế hoạch chia phiếu

Các phiếu trong cùng một lượt (lượt 1: 6 phiếu; lượt 2: 2; lượt 3: 3) **không trùng file**. Lệnh chạy ở Git Bash tại `E:/phantichcanhquay/kho-san-pham-radar-uid`. Phụ thuộc ⇒ lượt sau. Mức: compile < unit < fixture < live (không phiếu nào ghi `live`). Mọi phiếu code **dùng dữ liệu đo ở §2.2–§2.5** (trích, không đoán).

### Lượt 0: RU-D1 · culiapp-architect · Điền số đo RU-0 — **ĐÃ LÀM** trong phiếu A-RU1b (§2.2, §2.3, §2.4, §2.5, Phụ lục A). Lượt 1 chỉ bắt đầu sau lượt này.

### Lượt 1 (6 phiếu song song)

**RU-B1 · culiapp-backend · Công thức thuần**
- ĐƯỢC SỬA: `tools/runner/radar_uid_tinh.py` (mới), `tools/test_runner_radar_uid_tinh.py` (mới). CẤM: mọi file khác; không I/O, không mạng, không `sqlite3`.
- Dữ liệu đo dùng: views số nguyên/`'21.81K'`; `follower_count '2.54K'` (có thể thiếu); `n_doi` 0/39 sau 3 giây; mẫu số = `lay_luc`; không có `update_time` video.
- Interface (kiểu §7.2 nguyên văn):
```python
RE_UID: re.Pattern                                   # ^\d{19}$
NGUONG: dict[str, Any]                               # §5.4 đủ khoá (gồm ADS_BAT=False)
class SoRutGon(NamedTuple): gia_tri: int; sai_so: int
def doc_so_rut_gon(s: object) -> SoRutGon | None
def bo_dau(s: str) -> str
def lam_sach_ten(ten: str) -> list[str]
def tu_khoa_tim(ten: str) -> list[str]                     # 3 chuỗi: 4, 3, 2 âm tiết đầu
def do_giong(ten_goc: str, ten_ung: str) -> float
def keyword_co_loc(tu_khoa: str, ten_ung_vien: list[str]) -> bool
def chon_tuong_tu(goc_ten: str, goc_gia: str | None, ung_vien: list[UngVien], da_loai: frozenset[str], so_luong: int = 10) -> list[UngVien]
class KyDo(TypedDict): gio: float; hop_le: bool; n_video: int; n_creator: int; n_doi: int; ti_le_doi: float | None   # n_video/n_creator: tập "đang sống"
                       trung_vi: int | None; tong_delta_top5: int | None; khong_lam_moi: bool
                       ds_d24: list[tuple[str, str, int]]; loai: dict[str, int]
def tinh_ky(truoc: Snapshot, sau: Snapshot, cap_nhat_dung_yen: bool = False) -> KyDo   # cap_nhat_dung_yen: echotik_cap_nhat không đổi ở kỳ liền trước
def view_nho(sau: Snapshot, tuoi_ngay: int = 14) -> tuple[int | None, int, int]   # (trung vị view | None, số creator, follower_khong_doc); follower đọc được và < 10K
def du_mau(ky: KyDo) -> bool                                # DU_MAU §5.4, dùng chung cho THIEU_MAU và dang_co_da
def xep_hang_uid(snaps: list[Snapshot], hom_nay: datetime, bat_dau_ngay: str) -> dict   # đúng khoá UidRa §7.1 (trừ uid/vai/ten/shop/do_giong/trang_thai)
```
- Tiêu chí xong: test mọi ví dụ §3, §5.1 (Ví dụ 1–5), §5.2: trung vị 700 (n=11, c=6), `tong_delta_top5` 9.200; 666 ở 25,2 giờ; `'1.79M'→'1.80M'` loại; `'38.11K'→'38.74K'` giữ; `n_doi = 0` ⇒ `KHONG_LAM_MOI`, `trung_vi is None`; `echotik_cap_nhat` đứng yên 2 kỳ ⇒ `KHONG_LAM_MOI`; **`n_doi = 6/39` ⇒ KHÔNG cờ**, `trung_vi = 12`, `tong_delta_top5 = 180`, `THIEU_MAU` (n=6 < 8), `tam=True`; `tang_toc` 5,75 (9.200/1.600), 14,39 (7.770/540, trung vị chỉ 100), 1,6, 3,6 nhưng 900 < 1.000 ⇒ không đột ngột; kỳ trước GAP ⇒ `tang_toc is None` + `ly_do_tang_toc`; `view_nho` 7.200, 5 creator, follower `N/A` bị loại; không video ≤ 14 ngày ⇒ `view_nho_trung_vi is None` + câu "không có video ≤ 14 ngày"; `du_mau` dùng chung; GAP 55 giờ có, 48 giờ không; `DU_LIEU_CU` 50 giờ; `THIEU_MAU` n=7/c=2 ⇒ `tam=True`, số vẫn trả; `dang_co_da` đòi cả hai tiêu chí; `n_video_moi_30 == 0` ⇒ `cau_video_moi == "Không có video mới 30 ngày"`; `NGHI_ADS` không bao giờ bật khi `ADS_BAT=False`; id 19 số là chuỗi; không 0 giả.
- LỆNH: `python -B -m pytest tools/test_runner_radar_uid_tinh.py -q -p no:cacheprovider`. MỨC: `unit`. DUYỆT: không.

**RU-B2 · culiapp-backend · Kho `radar_uid.db`**
- ĐƯỢC SỬA: `tools/runner/kho_radar_uid.py` (mới), `tools/test_runner_radar_uid_kho.py` (mới). CẤM: `kho_hoc.py`, mọi file khác. File tự đủ (không import `radar_uid_tinh`), có `RE_UID` riêng.
- Interface:
```python
GOC_TOI_DA = 2; TUONG_TU_TOI_DA = 10; THEM_TAY_TOI_DA = 3; UID_TOI_DA = 24
class KhongCoRadar(LookupError): ...                 # 404, .loi cố định
class SaiTrangThaiRadar(RuntimeError): ...           # 409, .loi cố định §7
class KhoRadarUid:
    def __init__(self, duong_dan: Path, bay_gio: Callable[[], datetime], *, chi_doc: bool = False) -> None   # không mở file
    def mo(self) -> None;  def dong(self) -> None
    def them_goc(self, uid: str, boi: str) -> dict                                # {"da_co": bool, "goc": str}
    def them_tay(self, goc: str, uid: str, boi: str) -> None
    def dat_uid(self, goc: str, uid: str, hanh_dong: str, boi: str) -> dict       # ghim|bo-ghim|loai|bo-loai
    def dat_goc(self, goc: str, hanh_dong: str, boi: str) -> dict                 # ngung|theo-lai
    def dat_trang_thai_nhom(self, goc: str, trang_thai: str, ly_do: str = "") -> None
    def ghi_san_pham(self, uid: str, ten: str, shop: str) -> None
    def ghi_tuong_tu(self, goc: str, ds: list[UngVien], tim_luc: str) -> int
    def ds_can_chup(self, ngay: str, goc: str | None = None) -> list[str]         # chưa `ok` hôm nay (goc=None: nhóm da_tim hoặc loi_tim; goc=<uid>: UID của nhóm đó, mọi trạng thái trừ ngung; §6.3a); xoay: lần `ok` gần nhất cũ nhất trước, chưa từng chụp đứng đầu
    def bat_dau_chup(self, uid: str, ngay: str, lay_luc: str) -> bool             # ghi 'dang_chup' TRƯỚC khi gọi mạng; False nếu đã ok / hết 2 lần thử
    def ghi_chup_ok(self, snap: Snapshot) -> None                                 # 1 giao dịch; snap.videos rỗng ⇒ ghi 'loi' ma_loi='khong_co_video', KHÔNG 'ok'
    def ghi_chup_loi(self, uid: str, ngay: str, ma_loi: str) -> None
    def tinh_goi(self, ngay: str, so: int, tran: int) -> bool                     # cộng trước khi gọi; False nếu vượt
    def doc_snapshots(self, uid: str, tu_ngay: str) -> list[Snapshot]
    def ds_nhom(self) -> list[dict];  def uid_cua_nhom(self, goc: str) -> list[dict]
    def bat_dau_lan(self, ngay: str, che_do: str, viec_id: str) -> bool
    def ket_thuc_lan(self, ngay: str, che_do: str, viec_id: str, trang_thai: str, ly_do: str, so_goi: int) -> None
    def ghi_token(self, trang_thai: str, ma: str) -> None;  def doc_token(self) -> dict
    def lan_gan_nhat(self) -> dict | None;  def lan_cua_viec(self, ngay: str, che_do: str, viec_id: str) -> dict | None
    def goi_hom_nay(self, ngay: str) -> int
```
- Tiêu chí xong: schema §4 đúng (không cột `update_time` video); `ds_can_chup` xoay đúng thứ tự (UID chụp cũ nhất trước, không cố định); giới hạn §4 trả `SaiTrangThaiRadar` đúng câu §7; `bat_dau_chup` idempotent, `so_lan_thu ≤ 2`; `ghi_chup_ok` hoàn tác hết khi lỗi giữa chừng; video rỗng ⇒ `loi`; id 19 số không đổi kiểu; `chi_doc=True` không tạo file; `mo()` lặp lại an toàn.
- LỆNH: `python -B -m pytest tools/test_runner_radar_uid_kho.py -q -p no:cacheprovider`. MỨC: `fixture`. DUYỆT: không.

**RU-A1 · culiapp-automation · Client EchoTik**
- ĐƯỢC SỬA: `tools/runner/echotik.py` (mới), `tools/test_runner_echotik.py` (mới). CẤM: mọi file khác, mọi gọi mạng thật.
- Dữ liệu đo dùng: §2.5 (E1/E2/E4 + `meta`), `urllib` đủ, HTML = lỗi token/tham số.
- Interface:
```python
class LoiEchoTik(Exception):
    ma: str   # 'token_thieu'|'token_het_han'|'rate_limit'|'mang'|'dinh_dang'|'khong_tim_thay'
class HetNganSach(Exception): ...                       # tinh_goi trả False
class EchoTik:
    def __init__(self, token_file: Path, *, mo_url: Callable = urllib.request.urlopen, ngu: Callable[[float], None] = time.sleep,
                 dong_ho: Callable[[], float] = time.monotonic, cach_toi_thieu_s: float = 1.3,
                 tinh_goi: Callable[[int], bool] | None = None) -> None
    def chi_tiet(self, uid: str) -> dict                                            # object E1 thô
    def video(self, uid: str, trang: int = 1, moi_trang: int = 50) -> tuple[list[dict], MetaTrang]   # order=publish_time&sort=desc
    def tim(self, tu_khoa: str, trang: int = 1, moi_trang: int = 50) -> tuple[list[dict], MetaTrang]
    so_goi: int
def chuan_video(raw: dict) -> HangVideo | None          # thiếu video_id/publish_time ⇒ None; view nhận int hoặc str ⇒ luôn str; BỎ update_time
def chuan_ung_vien(raw: dict) -> UngVien | None         # product_id, product_name, avg_price, total_sale_7d_cnt
def chuan_meta(raw: object) -> MetaTrang                # thiếu ⇒ {None, None}
```
- Tiêu chí xong (mock `mo_url`): header đúng §2.1 và **token không xuất hiện** trong `str(LoiEchoTik)`, log, `repr`; HTML ⇒ `token_het_han`; 401/403 ⇒ `token_het_han`; 429 ⇒ `rate_limit` không thử lại; 5xx/timeout thử lại ≤ 2 lần (3 s, 6 s qua `ngu` giả), mỗi lần `tinh_goi(1)`; `tinh_goi` False ⇒ `HetNganSach`; cách ≥ 1,3 s (kiểm bằng `dong_ho` giả); `meta` có/không có; `chuan_video` nhận `views_count` 326 (int) và `'21.81K'`; `data` thiếu ⇒ `dinh_dang`; đọc file token mỗi lần (đổi mtime nhận token mới); không `print`.
- LỆNH: `python -B -m pytest tools/test_runner_echotik.py -q -p no:cacheprovider`. MỨC: `fixture`. DUYỆT: không.

**RU-W1 · culiapp-web · Worker `/api/radar/*`**
- ĐƯỢC SỬA: `cf/src/radar.js` (mới), `cf/src/worker.js` (đúng 2 dòng: `import { apiRadar } from "./radar.js";` cạnh `:8`; `if (p === "/api/radar" || p.startsWith("/api/radar/")) return apiRadar(req, env, url, phien, { goiMayNha, traVeMayNha, loi, json, laChuKho });` sau `:956`), `cf/test/radar-worker.test.mjs` (mới). CẤM: phần khác của `worker.js`.
- Interface: `export function tuyenRadar(p: string): {GET?: {dich}, POST?: {dich, act, goc?, uid?}} | null`; `export async function apiRadar(req, env, url, phien, deps): Promise<Response>`; `RE_UID = /^\d{19}$/`, `RADAR_BODY_TOI_DA = 16 * 1024`. Chữ ký như `apiHoc` (`hoc.js:58`).
- Tiêu chí xong: bảng §7 (từng route, phương thức, 403 người thường **trước** mọi `fetch`, 405, 404 uid sai dạng, Origin sai 403, 413, 415); body gửi máy nhà chỉ `{boi}` hoặc `{boi, uid}`; ký D7 (verify Ed25519 như `hoc-worker.test.mjs`); 524/HTML 5xx ⇒ lỗi JSON; id 19 số giữ chuỗi.
- LỆNH: `node --check cf/src/radar.js && node --check cf/src/worker.js && node --test cf/test/radar-worker.test.mjs cf/test/worker.test.mjs cf/test/hoc-worker.test.mjs`. MỨC: `fixture`. DUYỆT: không.

**RU-B4 · culiapp-backend · Chuyển tiếp video_server**
- ĐƯỢC SỬA: `tools/video_server.py` (chỉ `RE_R` `:139-143`, bảng phương thức mới cạnh `R_HOC` `:147-148`, nhánh `hoc = …` `:196`), `tools/test_video_server.py`. CẤM: phần khác; không nới `R_QUERY_KHOA`.
- Interface: `R_RADAR_GET = re.compile(r"^/r/radar/(bang|uid/\d{19})$")`; các đường `/r/radar/*` còn lại khớp `RE_R` chỉ POST; GET không query.
- Tiêu chí xong: đường đúng regex §7 qua; lạ (`/r/radar/x`, `/r/radar/uid/12`) 404; GET trên route POST và ngược lại 405; body > 16 KB 413; header chuyển tiếp chỉ `x-runner-key, x-ky*, content-type`.
- LỆNH: `python -B -m pytest tools/test_video_server.py -q -p no:cacheprovider`. MỨC: `fixture`. DUYỆT: không.

**RU-W2 · culiapp-web · Giao diện tab**
- ĐƯỢC SỬA: `web/radar-uid.js` (mới), `web/khung.js`, `web/index.html`, `web/style.css` (nối khối `.rdu-*` + nâng `?v`), `web/viec.js` (dòng `:13` + `?v`), `web/loi.js` (`:26-27` + `?v`), `cf/test/radar-uid-web.test.mjs` (mới), `cf/test/menu-web.test.mjs`, `cf/test/poster-web.test.mjs`, `cf/test/homnay-web.test.mjs`. CẤM: `app.js`, `hoc.js`, `poster.js`, `pv-*.js`.
- Interface (khối `radar-uid-thuan`):
```js
function rduLayUid(s)          // → "19 số" | ""
function rduSo(n)              // number|null → "—" | chuỗi có dấu chấm nghìn
function rduSpark(a)           // (number|null)[] → "▁▃▅▇" · "·"
function rduNhanCo(ma)         // mã cờ → {ten, muc: "chan"|"canh-bao"}
function rduHangHtml(u)        // UidRa §7.1 → html (đã esc); đủ cột §8
function rduNhomHtml(nhom)
function rduBangHtml(bang, nowMs)
function rduPosterHtml(u)      // Sao chép / Mở Folders + ô tick SKU (vai ≠ goc)
async function rduRender(phien)
```
- Tiêu chí xong: §8 đủ (cột riêng cho từng chỉ số, `tam` xám + câu "chưa đủ bằng chứng (n=…, k/4 snapshot)", "Không có video mới 30 ngày", `is_promote x/y`, rỗng/tải/lỗi, XSS mọi trường, `uid` kiểm trước thuộc tính, không `<table>`/`style="`/`on…=`), khoá bấm đúp, không `Number(uid)`, sửa đủ test §8 (kể cả `poster-web:782` và `?v`); P2-7 xanh; `mnNavHtml(false)` đúng 1 mục.
- LỆNH: `node --check web/radar-uid.js && node --check web/khung.js && node --test cf/test/radar-uid-web.test.mjs cf/test/menu-web.test.mjs cf/test/poster-web.test.mjs cf/test/homnay-web.test.mjs` (chỉ test của chính phiếu + 3 test menu/poster/homnay; **không** chạy toàn bộ `cf/test/*.test.mjs` vì RU-W1 cùng lượt có thể còn dở; chạy toàn bộ là việc của RU-T1). MỨC: `fixture`. DUYỆT: không.

### Lượt 2 (sau lượt 1; 2 phiếu song song)

**RU-A2 · culiapp-automation · Script chạy việc** (phụ thuộc RU-B1, B2, A1)
- ĐƯỢC SỬA: `tools/runner/radar_uid.py` (mới), `tools/test_runner_radar_uid_script.py` (mới).
- Interface: `python -B -m runner.radar_uid --che-do {nap,hang-ngay} --ngay YYYY-MM-DD --db P --token-file P --viec-id ID --tran-goi N [--goc UID]`; `def chay(argv: list[str], *, echotik_factory: Callable[..., EchoTik] = EchoTik, bay_gio: Callable[[], datetime] = ...) -> int` (0 = `xong`/`tu_dung`, 1 = lỗi); stdout đúng 1 dòng `{"trang_thai","ly_do","so_uid","so_goi"}`.
- Tiêu chí xong (EchoTik giả, DB tạm): §6.2–6.5: ghi `dang_chup` trước gọi; chạy hai lần idempotent; dừng đúng từng mã §6.3; ngân sách `2×N + tìm`; thứ tự chụp xoay (UID chụp cũ nhất trước, UID cuối không đói khi gặp trần); `hang-ngay` bỏ qua nhóm `cho_tim`/`dang_tim`/`ngung` nhưng chụp nhóm `da_tim` và `loi_tim`; thử ≥ 1 UID mà `ok` = 0 ⇒ `loi`/`khong_chup_duoc`; E2 0 video ⇒ `loi`; `last_page=2` ⇒ `MAU_TOP_VIDEO`; ba từ khoá union, cổng `keyword_co_loc` từng từ khoá; UID trùng gốc/đã loại bị bỏ; không token trong stdout/stderr/DB/log.
- LỆNH: `python -B -m pytest tools/test_runner_radar_uid_script.py -q -p no:cacheprovider`. MỨC: `fixture`. DUYỆT: không.

**RU-B3 · culiapp-backend · Nối vào runner** (phụ thuộc RU-B1, B2 về hàm; với RU-A2 **chỉ phụ thuộc tên CLI** đã khai ở interface của A2 ⇒ **làm song song với A2 được**)
- ĐƯỢC SỬA: `tools/runner/danh_muc.py`, `han_muc.py`, `vong_lap.py`, `kieu.py`, `api.py`, `tools/chay_runner.py`, `tools/test_runner_radar_uid_api.py` (mới), `tools/test_runner_danh_muc.py`, `test_runner_han_muc.py`, `test_runner_vong_lap.py`, `test_runner_api.py`, `test_runner_chay.py`.
- Việc: 2 `LoaiViec` (§6.1) + `LOAI_CHI_HE_THONG`, `LOAI_KHONG_CHAY_LAI`, `PHAN_CAM_THU_MUC_RUNNER += "radar_uid.db*"`, `_CONG_CU_CAM_CO_DINH += "Read(//E:/timsanpham/.echotik_token.json)"`; `HAN_MUC_TRAN` 3 khoá §6.4 (`radar_uid_bat=1`, `radar_uid_goi_ngay=60`, `radar_uid_chay_ngay=6`; đếm lúc tạo theo khuôn `han_muc.py:418-423`, chỉ việc `boi != "he_thong"`); `HEN_GIO_MAC_DINH = (("quet_view_hang_ngay", 9), ("radar_uid_hang_ngay", 10), ("hoc_hang_ngay", 12))` + `BoChay(kho_radar=None)`; `MoiTruong.echotik_token_file`; `chay_runner.py` mở `KhoRadarUid` sau mutex (khuôn `:116-122`, `:226-229`); `api.py` 8 route §7 (bản thiết kế đầu còn `_tao_viec_he_thong`; hàm này là mã chết, đã xoá ở lượt 5, API dùng `_tao_viec_da_khoa`); `kiem_dau_ra` đọc `lan_chay` (§6.1).
- Tiêu chí xong: §7 từng route (404/409/429/503); `GET /radar/bang` dùng `xep_hang_uid`, đúng §7.1, id là chuỗi; `hen_gio_cho` thư mục tạm không tạo việc radar; cầu dao `radar_uid_bat=0`; **sửa test cũ đúng chỗ ghim** (không giữ nguyên văn): `test_runner_danh_muc.py:1995-1997` (`LOAI_CHI_HE_THONG`, `LOAI_KHONG_CHAY_LAI`) và `test_runner_han_muc.py:27-29` (`HAN_MUC_TRAN == {…}`) cập nhật theo bộ giá trị mới; thêm `test_runner_vong_lap.py`/`test_runner_chay.py` cho `HEN_GIO_MAC_DINH`; test so khoá TypedDict §7.2 giữa `radar_uid_tinh`, `kho_radar_uid`, `echotik`.
- LỆNH: `python -B -m pytest tools/test_runner_radar_uid_api.py tools/test_runner_danh_muc.py tools/test_runner_han_muc.py tools/test_runner_vong_lap.py tools/test_runner_api.py tools/test_runner_chay.py -q -p no:cacheprovider`. MỨC: `fixture`. DUYỆT: không.

### Lượt 3

**RU-A3 · culiapp-automation · Test nối đầu-cuối bằng máy chủ EchoTik giả** (phụ thuộc lượt 1–2)
- ĐƯỢC SỬA: `tools/test_runner_radar_uid_noi_day.py` (mới). `http.server` cổng ngẫu nhiên phát JSON dạng §2.5 (view `326` và `'21.81K'`, `update_time` video luôn đổi, 39 video, `last_page=1`, E4 10 phần tử), chạy script thật trong thư mục tạm, rồi `GET /radar/bang` qua `tao_handler`; `KHO_RUNNER_DIR` tạm, **không** chạm `E:\kho-runner` hay `E:\timsanpham`.
- LỆNH: `python -B -m pytest tools/test_runner_radar_uid_noi_day.py -q -p no:cacheprovider`. MỨC: `fixture`. DUYỆT: không.

**RU-W3 · culiapp-web · (TUỲ CHỌN) Kiểm UID đã ở folder Poster nào** (phụ thuộc RU-W2)
- ĐƯỢC SỬA: `web/radar-uid.js`, `cf/test/radar-uid-web.test.mjs`, `web/index.html` (chỉ nâng `?v`). Hàm thuần `rduFolderChuaUid(folders, uid) → {id, ten}[]`; chỉ `pvApi.getFolders(false)` (GET), gọi khi bấm tay. Tiêu chí: không có lời gọi ghi; test thuần + fixture. LỆNH: `node --check web/radar-uid.js && node --test cf/test/radar-uid-web.test.mjs cf/test/menu-web.test.mjs`. MỨC: `fixture`. Không bắt buộc cho tích hợp.

**RU-T1 · trưởng phòng**: thêm 8 file test mới (`tools/test_runner_radar_uid_{tinh,kho,script,api,noi_day}.py`, `tools/test_runner_echotik.py`, `cf/test/radar-worker.test.mjs`, `cf/test/radar-uid-web.test.mjs`) vào `LENH` của `.culiapp/kiem-chung.py`; chạy `python .culiapp/kiem-chung.py`; ghi `.culiapp/nhat-ky.md`; xếp lượt với phiên khác đang sửa `cf/src/worker.js`.

---

## 14. Hành động cần duyệt (trưởng phòng chạy)

| # | Lệnh | Tác động | Hoàn tác |
|---|---|---|---|
| 0 | RU-0 (Phụ lục A) | **ĐÃ CHẠY 2026-11-23** (7 GET, đọc token, không ghi file) | – |
| 1 | Thêm `"radar_uid_bat": 0` vào `E:\kho-runner\cau_hinh.json` | ghi cấu hình runner thật (lịch tắt lúc kiểm; đọc lúc khởi động) | xoá khoá, khởi động lại |
| 2 | Tắt runner, `["python", "tools/cai_runner.py"]`, bật runner | ghi `E:\kho-runner\app\`, tạo `radar_uid.db*` | `app.cu` → `app`; xoá `radar_uid.db*` |
| 3 | Khởi động lại video_server (**không** `taskkill /T`) | `/r/*` gián đoạn vài giây | khởi động bản cũ |
| 4 | `["npx", "wrangler", "deploy"]` tại `cf` | Worker + web mới | `["npx", "wrangler", "rollback"]` |
| 5 | **Nạp thử 1 UID gốc (live, ≈ 25–28 GET):** `["python","-B","-m","runner.radar_uid","--che-do","nap","--goc","<UID>","--ngay","<hôm nay>","--db","E:/kho-runner/radar_uid.db","--token-file","E:/timsanpham/.echotik_token.json","--viec-id","tay","--tran-goi","60"]` tại `E:\kho-runner\app` | ghi `radar_uid.db`, tiêu hạn mức EchoTik | `ngung` nhóm trên web; xoá DB nếu cần |
| 6 | Bật lịch: bỏ khoá `radar_uid_bat`, khởi động lại runner, kiểm `/suc-khoe` không cảnh báo "cau_hinh.json hỏng". **Ngày đầu chỉ 1 UID gốc** | từ 10:00 hằng ngày ≈ 22 GET (1 nhóm) | đặt lại `0` |
| 7 | Sau 4 ngày: mở `#/theo-doi`, kiểm tiêu chí thành công §1 (nhóm có ≥ 1 UID `xep_loai ≠ chan`), đối chiếu một UID bằng tay; theo dõi `goi_hom_nay` và 429 để quyết nâng trần (§6.4) | không | – |

---

## 15. Câu hỏi còn mở

**Không còn câu hỏi mở.** Ba câu của bản đầu đã đóng ("Đã chốt trưởng phòng", được người dùng ủy quyền toàn quyền; kiến trúc sư không tự xác minh):
- **Q1 (nút Poster tự điền UID):** **(a)** chỉ Sao chép UID + mở Folders; kèm GET chỉ-đọc tuỳ chọn RU-W3 (§10). (b) PATCH `product_id` bị loại vì ghi đè nguyên chuỗi và `pick_product` trộn sản phẩm.
- **Q2 (trần gọi EchoTik):** **mặc định 60/ngày**, ngày đầu 1 UID gốc, nâng sau khi đo (§6.4).
- **Q3 (`is_promote`):** **(b)** chỉ hiện số thô `x/y`, không dùng làm lý do bật `NGHI_ADS` (§5.3).

---

## 16. Tự soát: file/hàm hiện có được nhắc tới đều có thật

- Web: `web/khung.js:9-16,22,28,40-42,82-95` (đã đo lại lượt 3), cũ: `:21,38,46,47,80,83,85,90-91`; `web/hoc.js:346,354,374,377,405`; `web/poster.js:11,131`; `web/pv-folders.js:318,443`; `web/viec.js:13`; `web/loi.js:26-27`; `web/index.html:15-29`; `web/app.js:9,755`.
- Worker: `cf/src/hoc.js:11,19,58,61,88,93`; `cf/src/worker.js:8,9,183,491,512,958`.
- video_server: `tools/video_server.py:138,139-143,147-148,151,194-198`.
- Runner (đã đo lại lượt 3): `api.py:158-222,724-760,1254-1408,1509-1551`; `danh_muc.py:158,163-174,1037-1076,1624-1641,1739-1751`; `vong_lap.py:118-119,1394-1430`; `han_muc.py:43-53,136-140,403-415`; `kho_radar_uid.py:31-64,467-493,495,548-549,562-584,688`; `radar_uid.py:100-117,140-175,183-193,251-276,307-366,409-452`; `radar_uid_tinh.py:433-435,559-560`; `echotik.py:32,149-193`; cũ (lượt 0): `api.py:638-643,1064-1080`; `danh_muc.py:143,154,781-790,847`; `chay_runner.py:109-122,226-229`; `kho_hoc.py:38,529-560,611`.
- Ngoài repo: `lay_du_lieu.py:32,47-56,59-66,82-88`; `GHI_CHU_ECHOTIK.md:8-14,19-21,142`; `folders.py:20-42,305-328`; `product_pool.py:39-87`; `docs/poster-v2-tren-web.md:382-385`; mẫu `[M]` `SP_ORICO_2026-09-18/du_lieu_tho`.
- Test: `menu-web.test.mjs:60-66,164-166,283,408-413,431`; `poster-web.test.mjs:728-740,782`; `homnay-web.test.mjs:956,971`; `test_runner_danh_muc.py:1995-1997`; `test_runner_han_muc.py:27-29`. Không vỡ: `homnay-web:327`, `hoc-web:460`, `sua-web:293`.
- Số ví dụ đã tính bằng máy (`python -I -c`, báo cáo A-RU1c): trung vị 700; Σ Δ dương 11.700; top5 = 9.200; 4.200/11.700 = 35,9%; 700/(25,2/24) = 666,67; `tang_toc` 9.200/max(1.600,250) = 5,75; viral `d24` {0,0,20,40,60,100,120,150,2.000,2.500,3.000} ⇒ trung vị 100, top5 7.770, 7.770/540 = 14,39; 400/250 = 1,6; 900/250 = 3,6; UID mẫu minh hoạ `d24` {4,6,9,15,30,120} ⇒ trung vị 12, top5 180, 6/39 = 15,4%; `view_nho` 7.200.

Đã có sau lượt 1–2 (đối chiếu bằng `ls` 2026-11-23): `tools/runner/{radar_uid_tinh,kho_radar_uid,radar_uid,echotik}.py`, `cf/src/radar.js`, `web/radar-uid.js`, `tools/test_runner_{echotik,radar_uid_tinh,radar_uid_kho,radar_uid_script,radar_uid_api}.py`, `cf/test/radar-worker.test.mjs`, `cf/test/radar-uid-web.test.mjs`. **Chưa có:** `tools/test_runner_radar_uid_noi_day.py` (RU-A3, đang làm song song).

Số dòng ở §6–§8 (phiếu RU-D2 lượt 3) lấy từ cây làm việc ngày 2026-11-23 và sẽ dời khi code đổi; khi lệch thì tìm theo tên hàm/hằng.

---

## Phụ lục A: RU-0 (ĐÃ CHẠY 2026-11-23 bởi trưởng phòng, 7 GET) và lệnh để đo lại

Kết quả đã điền ở §2.2–§2.4. Output nguyên văn do trưởng phòng giữ; tài liệu này chỉ ghi số đã phiếu A-RU1b chuyển lại. Còn **CHƯA đo:** C3 (múi giờ `publish_time`), C7 (rate-limit), chiều `sort=desc` của E2 (mới nhất trước?), `meta` của E4, trường shop/danh mục của E4.

Lệnh đo lại (chỉ đọc, không ghi file, không in token, ≤ 12 GET cách 1,3 s; dừng khi gặp HTML/401/403/429), chạy ở Git Bash. **Các GET này chạy tay, không đi qua `goi_ngay`** nên không tính vào trần 60 của Radar nhưng vẫn tốn hạn mức tài khoản EchoTik chung:

```
python -I - <<'PY'
import json, re, sys, time, urllib.parse, urllib.request, urllib.error
BASE = "https://echotik.live"
UID_MAU = "1729420930611055346"
d = json.load(open(r"E:\timsanpham\.echotik_token.json", encoding="utf-8"))
tok, usr = str(d.get("token", "")), str(d.get("user_id", ""))
H = {"Authorization": "Bearer " + tok, "X-User-Id": usr, "token": tok, "user_id": usr, "x-region": "VN",
     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
     "Accept": "application/json, text/plain, */*", "Origin": BASE, "Referer": BASE + "/"}
n = 0
def goi(path):
    global n
    n += 1
    if n > 12: sys.exit("vuot tran 12 lan goi")
    time.sleep(1.3)
    try:
        r = urllib.request.urlopen(urllib.request.Request(BASE + path, headers=H), timeout=30)
        st, ct, body = r.status, r.headers.get("content-type", ""), r.read()
    except urllib.error.HTTPError as e:
        st, ct, body = e.code, e.headers.get("content-type", ""), e.read()
    print(f"#{n} {path.split('?')[0]} {path.split('?')[1] if '?' in path else ''} -> HTTP {st} {ct.split(';')[0]}")
    if not ("json" in ct and st == 200):
        print("   DUNG: khong phai JSON 200. Khong in than phan hoi."); sys.exit(1)
    return json.loads(body)
sp = goi(f"/api/v1/data/products/{UID_MAU}"); dt = sp.get("data") or {}
print("   E1 khoa:", sorted(dt.keys())[:60])
v = goi(f"/api/v1/data/products/{UID_MAU}/videos?page=1&per_page=50&order=publish_time&sort=desc")
ds = v.get("data") or []
print("   E2 so phan tu:", len(ds), "| meta:", json.dumps(v.get("meta"))[:200])
print("   C3/sort: dang dau:", [x.get("publish_time") for x in ds[:3]], "dang cuoi:", [x.get("publish_time") for x in ds[-2:]])
ten = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", str(dt.get("product_name", "")))
kw = " ".join(re.findall(r"[^\W\d_]+", ten)[:3])
s = goi("/api/v1/data/products?" + urllib.parse.urlencode({"page": 1, "per_page": 50, "order": "total_sale_7d_cnt", "sort": "desc", "dateRange": 7, "keyword": kw}))
print("   E4 so phan tu:", len(s.get("data") or []), "| khoa:", sorted(((s.get("data") or [{}])[0]).keys())[:40], "| meta:", json.dumps(s.get("meta"))[:200])
PY
```
