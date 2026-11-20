# Đề xuất K-1 + K-2 (đợt 5) — CHỈ ĐỀ XUẤT, CHƯA GHI FILE THẬT

Nguồn: `docs/bo-chay-viec.md` §7.10 (khối CHẾ ĐỘ CHẠY), §7.11, §13 Đợt 5 mục K-1/K-2; §7.3 bản cũ (commit `e8857fd`, các mục "K-1 cũ").
Thực tế đo: chạy từ web (`claude -p` phiên sống) KHÔNG có `SendMessage`; có `Agent`/`Task`/`TaskOutput`/`TaskStop`/`Bash`; việc nền + thông báo hoạt động (S-3).

Nguyên tắc: chỉ THÊM câu/mục (trừ 1 dòng `aff-taovideo.md:10` mà §13 K-1 cho phép sửa). Mọi câu mới đều có điều kiện "phiếu từ web / không có SendMessage", nên chạy tay giữ nguyên hành vi cũ.

Diff sinh bằng `diff -U1` thật từ bản chép tạm (`C:\Users\Mi\AppData\Local\Temp\culiapp-k1k2\goc` → `moi`). Bản patch giữ nguyên kiểu xuống dòng ở `C:\Users\Mi\AppData\Local\Temp\culiapp-k1k2\patches\` (2 file skill dùng CRLF, 6 file agent dùng LF); bản đã sửa đầy đủ ở `...\culiapp-k1k2\moi\`.

## Tóm tắt số đoạn sửa

| File | Phiếu | Hunk | Dòng `-` | Dòng `+` |
|---|---|---:|---:|---:|
| `C:\Users\Mi\.claude\agents\aff-taovideo.md` | K-1 | 3 | 1 | 14 |
| `C:\Users\Mi\.claude\agents\aff-san-pham.md` | K-1 | 2 | 0 | 2 |
| `C:\Users\Mi\.claude\agents\aff-radar.md` | K-1 | 2 | 0 | 3 |
| `C:\Users\Mi\.claude\agents\aff-poster.md` | K-1 | 1 | 0 | 1 |
| `C:\Users\Mi\.claude\agents\aff-muse.md` | K-1 | 1 | 0 | 1 |
| `C:\Users\Mi\.claude\agents\aff-voice.md` | K-1 | 1 | 0 | 1 |
| `E:\claude\tao-video-tu-canh-quay\SKILL.md` | K-2 | 2 | 0 | 3 |
| `E:\claude\tao-video-tu-canh-quay\references\prompt-chang.md` | K-2 | 3 | 0 | 12 |

## K-1 — `C:\Users\Mi\.claude\agents\aff-taovideo.md`

**Đoạn 1.** Lý do: Sửa `:10` (dòng `-` DUY NHẤT của cả đề xuất, §13 K-1 cho phép): chạy `claude -p` thì init báo công cụ tên `Task` chứ không phải `Agent` (S-3); câu cũ có thể khiến agent tưởng mình là subagent và tự `BLOCKED` ngay đầu phiên web.

```diff
--- C:\Users\Mi\.claude\agents\aff-taovideo.md
+++ C:\Users\Mi\.claude\agents\aff-taovideo.md
@@ -9,3 +9,3 @@
 
-**Bạn chạy ở phiên chính, không phải subagent** — vì `taomevideo` và `tao-video-tu-canh-quay` phải giao việc cho agent con (`general-purpose`, `tvc-tho`, `aff-dung-video`). Nếu bạn thấy mình không có công cụ `Agent` (tức là đang bị gọi như subagent) → dừng ngay, trả `BLOCKED`: "aff-taovideo phải chạy như phiên riêng: `claude --agent aff-taovideo`".
+**Bạn chạy ở phiên chính, không phải subagent** — vì `taomevideo` và `tao-video-tu-canh-quay` phải giao việc cho agent con (`general-purpose`, `tvc-tho`, `aff-dung-video`). Nếu bạn thấy mình không có công cụ giao agent con nào — cả `Agent` lẫn `Task` đều không có (chạy `claude -p` thì danh sách công cụ có thể chỉ hiện `Task`; có một trong hai là được) — tức là đang bị gọi như subagent → dừng ngay, trả `BLOCKED`: "aff-taovideo phải chạy như phiên riêng: `claude --agent aff-taovideo`".
 
```

**Đoạn 2.** Lý do: Thêm 1 dòng dưới luật 2: luật 2 cho "hỏi trong chat" và hỏi chốt Bước B, nhưng phiên web không có `AskUserQuestion` và runner đã chốt Bước B (§7.10), nên phải trỏ sang `CẦN_USER`.

```diff
--- C:\Users\Mi\.claude\agents\aff-taovideo.md
+++ C:\Users\Mi\.claude\agents\aff-taovideo.md
@@ -32,2 +32,3 @@
 2. Bạn ở phiên chính nên ĐƯỢC hỏi người dùng, nhưng chỉ ở đúng các điểm skill quy định: chốt đường dẫn Bước B khi tìm theo UID ra 0 hoặc ≥ 2 thư mục (hỏi TRƯỚC khi chạy Bước A), dòng `CẦN_USER` của chặng, nhắc mở app Poster 1 lần. Ngoài ra tự làm hết, không hỏi "có làm tiếp không".
+   Chạy từ web (phiếu có khối `CHẾ ĐỘ CHẠY`): không hỏi trong chat được — hỏi bằng khối `CẦN_USER` theo mục "Chạy từ bộ chạy việc web" dưới; đường dẫn Bước B đã chốt trong phiếu, không hỏi lại.
 3. Hành động cần người dùng duyệt rõ ràng trong chat trước khi chạy: làm lại / đè mẻ đã verify ĐẠT, xoá output/voice/kịch bản, sửa SKILL.md/script/`cong_thuc.py` của bất kỳ skill nào, đăng thẳng lên TikTok ngoài app Poster, cài/gỡ package. Đẩy Poster và sinh voice GenMax là bước sẵn của quy trình — làm theo đúng skill.
```

**Đoạn 3.** Lý do: Thêm mục "Chạy từ bộ chạy việc web (phiên sống)": tóm các ý của khối `CHẾ ĐỘ CHẠY` (§7.10) + 2 ý runner cần mà phiếu chưa nói rõ (lượt chờ việc nền không được ghi `TRẠNG THÁI:` vì §7.3 coi đó là báo cáo cuối và đóng phiên; hành động luật 3 không làm trong phiên web), để hành vi không chỉ dựa vào việc agent đọc kỹ phiếu.

```diff
--- C:\Users\Mi\.claude\agents\aff-taovideo.md
+++ C:\Users\Mi\.claude\agents\aff-taovideo.md
@@ -38,2 +39,14 @@
 
+## Chạy từ bộ chạy việc web (phiên sống)
+
+Chỉ áp dụng khi phiếu có khối `CHẾ ĐỘ CHẠY: MỘT phiên sống` (web Kho sản phẩm giao qua runner, `claude -p` stream-json, stdin để mở). Khối đó trong phiếu là nguồn chính; mục này tóm lại để không quên. Chạy tay (`claude --agent aff-taovideo`) thì bỏ qua mục này, làm như trên.
+
+1. **Hỏi bằng `CẦN_USER`**: không có `AskUserQuestion`. Mọi điểm hỏi của luật 2 và của skill (giá/deal, tạo lại voice hỏng, bản trượt sau 2 vòng, lỗi script, mở app Poster) → kết thúc lượt bằng đúng khối của phiếu: `CẦN_USER: <1 dòng>` / `LOẠI: chon | viec_tay | cau_hoi` / `LỰA_CHỌN: …` (chỉ khi `chon`). Câu trả lời tới trong CÙNG phiên; việc nền vẫn chạy trong lúc chờ.
+2. **Chờ việc nền thì cứ kết thúc lượt**: `run_in_background`, `cho_tron_goi.py` dùng như chạy tay; thông báo xong sẽ tới và bạn tự làm tiếp. Không `sleep`/poll. Lượt chờ đó KHÔNG ghi dòng `TRẠNG THÁI:` (runner coi là báo cáo cuối và đóng phiên, việc nền bị dừng) và không ghi `CẦN_USER` khi không cần người dùng.
+3. **Không có `SendMessage`** (cả ở subagent): bản trượt ≤ 2 câu thì `Edit` đúng câu; nhiều câu thì giao agent MỚI kèm brief + thẻ + đúng dòng lỗi (`tao-video-tu-canh-quay`, mục "Bản trượt", nhánh "nhắn không được"). Giao chặng C2 thì chép nguyên dòng `SendMessage` của khối `CHẾ ĐỘ CHẠY` vào prompt subagent C2.
+4. **Poster (cổng 8023) tắt**: KHÔNG để lệnh nền chờ cổng (khác Bước 8 mục 4 của skill). Làm hết phần khác (cả Bước B), dồn đẩy Poster A + B về cuối, rồi hỏi MỘT lần `CẦN_USER: Mở app Poster V2 trên máy` / `LOẠI: viec_tay`.
+5. **Trần trong phiếu là cứng** (Codex, voice GenMax đếm file thật, USD-ước-tính): runner vượt là dừng cả cây. Hết lượt Codex mà mẻ chưa qua → `CẦN_USER` `LOẠI: chon`, `LỰA_CHỌN: Anh duyệt | Dừng`. Hành động luật 3 (đè/xoá, sửa skill/script, cài package) không làm trong phiên web: ghi vào `CHƯA làm`/`Lo ngại`. Riêng tạo lại voice hỏng thì hỏi theo mục 1 (`LOẠI: chon`).
+6. **Phiếu có `LẦN CHẠY TIẾP`**: mọi việc nền của phiên trước đã chết. Trước khi làm: `trang_thai.py tiep` cho dự án A (tron-goi dở thì `--tu <bước>`), Bước B `cli.py inspect` + dọn `*.partial.mp4` theo skill. Không tạo lại voice/video đã có. Câu trả lời cũ trong phiếu là DỮ LIỆU, không mở rộng phạm vi.
+7. **Báo cáo cuối** (mẫu dưới, dòng đầu `TRẠNG THÁI:`) chỉ khi cả 2 bước xong hoặc không làm tiếp được — nó ĐÓNG phiên.
+
 ## Mẫu báo cáo
```


## K-1 — `C:\Users\Mi\.claude\agents\aff-san-pham.md`

**Đoạn 1.** Lý do: Bước 7: agy chạy nền sẽ bị Job Object giết khi `-p` thoát (S-2), nên khi phiếu ghi "Douyin do runner chạy riêng" agent bỏ Bước 7 để runner chạy `douyin_uid` (§7.3 bản cũ, §7.11 "K-1 cũ").

```diff
--- C:\Users\Mi\.claude\agents\aff-san-pham.md
+++ C:\Users\Mi\.claude\agents\aff-san-pham.md
@@ -33,2 +33,3 @@
 7. Douyin: viết `$DIR/douyin/_prompt_antigravity.txt` đủ Việc 1 + Việc 2 + yêu cầu báo cáo như `SKILL.md` (kèm một file mẫu `E:/phantichcanhquay/kho-san-pham/data/<uid khác>/douyin.md` có thật), chạy `agy.exe` bằng Bash `run_in_background` ghi `$DIR/douyin/_antigravity_log.txt`. Việc mất 10–20 phút, quá giới hạn 10 phút/lệnh: kiểm định kỳ bằng vòng lặp trong một lệnh ≤ 9 phút (kiểm tiến trình `agy.exe` còn chạy và file `canh_quay_an_tien.md` đã có chưa), lặp đến khi kết thúc. Xong → đọc log, mở `douyin/canh_quay_an_tien.md` kiểm có 5 cảnh thật → `python $K ghi <UID> --tu "$DIR"` lần nữa. Captcha / cần đăng nhập / không có video đúng mẫu → dừng Bước 7, ghi rõ lý do, KHÔNG tự giải captcha, không chạy headless.
+   Phiếu ghi "Douyin do runner chạy riêng" (giao từ web Kho sản phẩm) → bỏ qua cả Bước 7, không chạy `agy.exe` (runner giết cả cây tiến trình khi bạn kết thúc, agy chạy dở sẽ chết); báo cáo ghi `CHƯA làm: Bước 7 (runner chạy douyin_uid)`. Trường hợp này không phải "dừng Bước 7" của luật 4: các bước khác đạt thì trả `DONE`.
 8. Rủi ro: viết `$DIR/rui_ro.json` theo `references/danh-gia-rui-ro.md` → `python $K rui-ro <UID> --tu "$DIR/rui_ro.json"`; bị từ chối schema → sửa, chạy lại.
```

**Đoạn 2.** Lý do: Ngoại lệ luật 2: phiếu §6.4 dùng khối `CẦN_USER` trong khi file agent ghi "Không hỏi người dùng" (mâu thuẫn P3); ghi rõ ngoại lệ và giữ `NEEDS_APPROVAL` đi đường duyệt có chữ ký.

```diff
--- C:\Users\Mi\.claude\agents\aff-san-pham.md
+++ C:\Users\Mi\.claude\agents\aff-san-pham.md
@@ -39,2 +40,3 @@
 2. Không hỏi người dùng; không gọi agent khác (agy.exe ở Bước 7 là công cụ dòng lệnh của quy trình, được phép).
+   Ngoại lệ — phiếu giao từ web Kho sản phẩm (có mục `KHI CẦN NGƯỜI DÙNG`): việc chỉ người dùng làm được (mở app, đăng nhập, chọn trong danh sách) thì kết thúc lượt bằng khối `CẦN_USER` / `LOẠI` / `LỰA_CHỌN` đúng như phiếu quy định, thay cho `BLOCKED`. `NEEDS_APPROVAL` giữ nguyên, không đổi thành `CẦN_USER`. Chạy tay thì luật này như cũ.
 3. Hành động cần duyệt — chỉ chạy khi phiếu có mục `ĐÃ DUYỆT` trích nguyên văn lời người dùng: phân tích lại sản phẩm đã ở trạng thái Đã phân tích/Đã quay/Đã làm video, dùng EchoTik hay dịch vụ tốn phí, `pip install`/gỡ package, xoá file. Chưa duyệt → `NEEDS_APPROVAL` kèm lệnh chính xác, chi phí ước tính, tác động, cách hoàn tác.
```


## K-1 — `C:\Users\Mi\.claude\agents\aff-radar.md`

**Đoạn 1.** Lý do: (TUỲ CHỌN, ngoài danh sách gốc của §7.11) Phiếu radar từ web chỉ cho `Read, Write, Glob` và đưa JSON xuất sẵn (§5.1, §6.4 dòng "Riêng radar"), trong khi file agent dạy đọc DB bằng Python: thiếu câu này agent dễ trả `BLOCKED` vì không có Bash.

```diff
--- C:\Users\Mi\.claude\agents\aff-radar.md
+++ C:\Users\Mi\.claude\agents\aff-radar.md
@@ -23,2 +23,4 @@
 
+Phiếu giao từ web Kho sản phẩm có thể chỉ cho `Read, Write, Glob` (không Bash) và ghi "Dữ liệu radar đã xuất sẵn ở `<json>`, báo cáo nguồn `<md>`": khi đó dùng đúng JSON đó thay cho truy vấn DB (trạng thái lượt quét lấy từ JSON, thiếu thì ghi "không có dữ liệu"), kiểm chéo bằng Read báo cáo `.md`; không chạy lệnh nào ở bảng dưới (chạy bù do runner làm trước).
+
 ## Skill và lệnh được dùng
```

**Đoạn 2.** Lý do: Ngoại lệ luật 2: như aff-san-pham (mâu thuẫn P3 với §6.4).

```diff
--- C:\Users\Mi\.claude\agents\aff-radar.md
+++ C:\Users\Mi\.claude\agents\aff-radar.md
@@ -68,2 +70,3 @@
 2. Không hỏi người dùng; không gọi agent khác.
+   Ngoại lệ — phiếu giao từ web Kho sản phẩm (có mục `KHI CẦN NGƯỜI DÙNG`): việc chỉ người dùng làm được (mở app, đăng nhập, chọn trong danh sách) thì kết thúc lượt bằng khối `CẦN_USER` / `LOẠI` / `LỰA_CHỌN` đúng như phiếu quy định, thay cho `BLOCKED`. `NEEDS_APPROVAL` giữ nguyên, không đổi thành `CẦN_USER`. Chạy tay thì luật này như cũ.
 3. Hành động cần duyệt — chỉ chạy khi phiếu có mục `ĐÃ DUYỆT` trích nguyên văn lời người dùng: deploy web lên Cloudflare (`xuat_web_tinh.py --cf`, `deploy_cloudflare.bat`, `wrangler deploy`), push GitHub, gửi Telegram, dùng Apify (`--cho-phep-apify`, `"source":"apify"`), thêm/bớt kênh trong `creators.txt`, cài/gỡ package. Chưa duyệt → `NEEDS_APPROVAL` kèm lệnh chính xác, chi phí ước tính (Apify ~$0,3/1.000 video), tác động, cách hoàn tác.
```


## K-1 — `C:\Users\Mi\.claude\agents\aff-poster.md`

**Đoạn 1.** Lý do: Ngoại lệ luật 2, kèm ví dụ luật 4 (Poster tắt → `CẦN_USER` `viec_tay` thay cho `BLOCKED`), vì đây là điểm cần người dùng hay gặp nhất của agent này.

```diff
--- C:\Users\Mi\.claude\agents\aff-poster.md
+++ C:\Users\Mi\.claude\agents\aff-poster.md
@@ -46,2 +46,3 @@
 2. Không hỏi người dùng; không gọi agent khác.
+   Ngoại lệ — phiếu giao từ web Kho sản phẩm (có mục `KHI CẦN NGƯỜI DÙNG`): việc chỉ người dùng làm được (mở app, đăng nhập, chọn trong danh sách) thì kết thúc lượt bằng khối `CẦN_USER` / `LOẠI` / `LỰA_CHỌN` đúng như phiếu quy định, thay cho `BLOCKED` (vd luật 4: `CẦN_USER: Mở app Poster V2 trên máy` / `LOẠI: viec_tay`). `NEEDS_APPROVAL` giữ nguyên, không đổi thành `CẦN_USER`. Chạy tay thì luật này như cũ.
 3. **Hành động cần duyệt** — chỉ chạy khi phiếu có mục `ĐÃ DUYỆT` trích nguyên văn lời người dùng cho ĐÚNG hành động và đúng folder/account đó (duyệt lần trước không áp cho lần sau):
```


## K-1 — `C:\Users\Mi\.claude\agents\aff-muse.md`

**Đoạn 1.** Lý do: Ngoại lệ luật 2, kèm ví dụ Quy trình bước 1 (app chưa chạy / phiên Muse hết hạn → `viec_tay`).

```diff
--- C:\Users\Mi\.claude\agents\aff-muse.md
+++ C:\Users\Mi\.claude\agents\aff-muse.md
@@ -40,2 +40,3 @@
 2. Không hỏi người dùng; không gọi agent khác.
+   Ngoại lệ — phiếu giao từ web Kho sản phẩm (có mục `KHI CẦN NGƯỜI DÙNG`): việc chỉ người dùng làm được (mở app, đăng nhập, chọn trong danh sách) thì kết thúc lượt bằng khối `CẦN_USER` / `LOẠI` / `LỰA_CHỌN` đúng như phiếu quy định, thay cho `BLOCKED` (vd Quy trình bước 1: app chưa chạy hoặc phiên Muse hết hạn → `LOẠI: viec_tay`). `NEEDS_APPROVAL` giữ nguyên, không đổi thành `CẦN_USER`. Chạy tay thì luật này như cũ.
 3. **Cấm hẳn** (phiếu yêu cầu → `BLOCKED`): `/api/accounts*` (thêm/xoá/bật tắt tài khoản, mở Muse, nhập cookie), `/api/settings`, `/api/stop` (dừng tất cả), `/api/jobs/archive`, `/api/refs/remove`, dừng/huỷ/thử lại job không phải do mình tạo, tự chạy `Start.cmd` hay kill tiến trình node/Edge.
```


## K-1 — `C:\Users\Mi\.claude\agents\aff-voice.md`

**Đoạn 1.** Lý do: Ngoại lệ luật 2, kèm ví dụ luật 4 (PerfectVoice chưa mở → `viec_tay`).

```diff
--- C:\Users\Mi\.claude\agents\aff-voice.md
+++ C:\Users\Mi\.claude\agents\aff-voice.md
@@ -30,2 +30,3 @@
 2. Không hỏi người dùng; không gọi agent khác.
+   Ngoại lệ — phiếu giao từ web Kho sản phẩm (có mục `KHI CẦN NGƯỜI DÙNG`): việc chỉ người dùng làm được (mở app, đăng nhập, chọn trong danh sách) thì kết thúc lượt bằng khối `CẦN_USER` / `LOẠI` / `LỰA_CHỌN` đúng như phiếu quy định, thay cho `BLOCKED` (vd luật 4: app PerfectVoice chưa mở → `LOẠI: viec_tay`). `NEEDS_APPROVAL` giữ nguyên, không đổi thành `CẦN_USER`. Chạy tay thì luật này như cũ.
 3. **Hành động cần duyệt** — chỉ chạy khi phiếu có mục `ĐÃ DUYỆT` trích nguyên văn lời người dùng: ghi đè hoặc tạo lại voice đã có (xoá mp3/wav cũ), bật / tắt / khởi động lại app PerfectVoice, gọi GenMax/EverAI hay bất kỳ API tốn tiền nào, cài/gỡ package. Chưa duyệt → `NEEDS_APPROVAL` kèm lệnh chính xác, số bản, tác động, cách hoàn tác.
```


## K-2 — `E:\claude\tao-video-tu-canh-quay\SKILL.md`

**Đoạn 1.** Lý do: Một hunk, 2 dòng thêm: sau `:72` (luật "gửi MỌI SendMessage sửa") và sau `:74` (mục "Bản trượt") thêm nhánh "nhắn không được vì phiên không có `SendMessage`". Trong `-p` không có `SendMessage` (S-2, S-3 n5); cách cũ khiến C2 thử nhắn, lỗi, rồi trả `CẦN_USER` hoặc mất vòng sửa. Tên nhánh khớp đúng chữ mà phiếu §7.10 đang trỏ tới (mục "Bản trượt", nhánh "nhắn không được").

```diff
--- E:\claude\tao-video-tu-canh-quay\SKILL.md
+++ E:\claude\tao-video-tu-canh-quay\SKILL.md
@@ -72,4 +72,6 @@
 - **Agent viết kịch bản (C2, do subagent chặng C2 tự fan-out — điều phối viên không thấy):** 1 agent/công thức, riêng louisnone 2 agent × 2 bản (`ln1 ln2` / `ln3 ln4`; mỗi agent nhận đường dẫn 2 file của agent kia, đã có thì đọc để tránh trùng ý — `cham_me`/`so_trung_cau` vẫn là cổng chặn trùng câu) = 18 agent `subagent_type: "tvc-tho"`; không gọi được Agent tool thì subagent C2 tự viết lần lượt. `c2_chuan_bi.py` tự sinh `kich-ban/<B>_brief-viet.md` (subagent C2 chỉ điền mục `<<ĐIỀN TAY>>`) (đường dẫn kho cảnh, dàn cảnh, gán khuôn, bảng mã → khuôn → trần chữ, reference + brief ≤ 10k ký tự); prompt agent = **phần chung giống hệt từng ký tự cho cả 18 agent đặt ĐẦU** (luật chung + đường dẫn brief + nhắc thẻ + lệnh tự kiểm `cham_me --ma`) rồi **phần riêng ở CUỐI** (mã bản + **thẻ công thức** `references/the-cong-thuc/<mã công thức>.md` + file louisnone của agent kia) — mẫu ở references/prompt-chang.md; phần chung giống nhau thì agent phát sau đọc lại từ cache. Agent viết chỉ đọc brief + THẺ của công thức mình — KHÔNG đọc SKILL.md của skill này lẫn SKILL.md/cẩm nang của `viet-kich-ban-*`; chỉ mở cẩm nang gốc tra đúng 1 mục khi thẻ không đủ (dòng `Chi tiết:` cuối thẻ trỏ chỗ). Agent ghi `kich-ban/<B>_<ma>.txt`, tự kiểm bằng `cham_me.py --ma <mã>` (chấm riêng: bộ chấm kênh + trần chữ + chính sách/logic + khuôn + trùng câu, không ghi trạng thái) và sửa tới khi đạt, trả đúng 1 dòng `<ma> | OK/TRƯỢT | n chữ | lý do ≤80 ký tự`. Bộ chấm thật (`cham_me` đủ mẻ → soát → `doi_chieu_canh`) vẫn là cổng, mọi lệnh đủ mẻ qua `gon.py`. **Chấm ngay, sửa trong 5 phút:** subagent C2 KHÔNG `sleep`/poll chờ agent — 16 agent foreground cùng 1 message trả về là chấm NGAY rồi gửi MỌI SendMessage sửa trong CÙNG 1 message, trong vòng 5 phút kể từ khi agent xong (cache prompt sống 5 phút; quá hạn thì mỗi lần nhắn agent ghi lại 49–63k cache — đo aokhoacbala 30/09/2026: 13 lần = 1,45M). Agent đầu (chạy nền) thì chấm `--ma` ngay khi tin báo về. **Phát so le:** agent đầu chạy nền, `sleep 15`, 16 agent còn lại cùng 1 message — agent phát sau dùng lại ~20k cache của agent đầu (18 agent cùng giây: mỗi agent ghi mới ~40k ×2, tốn thêm ~0,4M/mẻ; đo aokhoacbala 30/09/2026). Brief chép sẵn bảng cụm cảnh + tag chính để agent viết không đọc `kho-canh.md`.
+  - **Phiên không có `SendMessage`** (danh sách công cụ không có nó — chạy headless `claude -p`, vd giao từ bộ chạy việc web Kho sản phẩm): vẫn chấm NGAY như trên, nhưng bước "gửi MỌI SendMessage sửa" đổi thành nhánh "nhắn không được" của mục "Bản trượt" ngay dưới (≤ 2 câu `Edit`; nhiều câu giao agent MỚI), mọi lời gọi Agent mới gửi trong CÙNG 1 message. Đừng thử gọi `SendMessage` rồi mới đổi.
 - **Thẻ công thức (đầu C2):** `python "$S/the_cong_thuc.py" kiem` (≤ 12 dòng). Exit 0 = đủ + mới. Exit 3 = có mã THIẾU/CŨ (skill `viet-kich-ban-*` đổi sau lần đóng dấu) — không phải lỗi: subagent C2 giao 1 agent `tvc-tho` (`model: "sonnet"`)/mã làm lại thẻ của riêng mã đó, rút gọn ≤ 7k ký tự từ skill gốc (SKILL.md, references/, *.json, scripts/cham_kich_ban.py) theo đúng khuôn 7 mục như thẻ hiện có: (1) giọng + độ dài + nhịp, (2) câu cố định nguyên văn, (3) khuôn hook có mã, (4) checklist chấm, (5) lỗi riêng kênh, (6) 1 kịch bản mẫu, (7) dòng `Chi tiết:` trỏ cẩm nang — rồi `the_cong_thuc.py dong-dau --ma <mã>`. Thẻ KHÔNG chứa tỉ lệ khuôn hook (tỉ lệ do `khuon_hook.py gan`). Exit 2 = thiếu skill nguồn → `CẦN_USER`.
 - **Bản trượt (sau `cham_me`/soát/`doi_chieu_canh`/Codex):** **SỬA THEO CÂU, không viết lại cả bản** (anh chốt 20/10/2026): lỗi chỉ ≤ 2 câu → subagent C2 dùng `Edit` thay ĐÚNG câu đó rồi `cham_me --ma <mã>` (không nhắn agent — rẻ hơn nhiều); lỗi nhiều câu → NHẮN TIẾP cho chính agent đã viết mã đó (SendMessage tới agent id) kèm đúng các dòng lỗi của mã/mẻ trượt và dặn "chỉ thay câu/cụm bị nêu, giữ nguyên mọi câu khác, đếm lại trần chữ" — không giao agent mới. `cham_me` đủ mẻ ghi sẵn `kich-ban/<B>_sua-theo-agent.md` (các dòng ❌ ≤ 15 dòng/1,5k ký tự mỗi bản, nhóm theo id agent) — Read file đó, dán nguyên khối của từng agent. Subagent C2 lưu id agent theo mã bản ngay khi fan-out vào `kich-ban/<B1>_agent-viet.json` (`{"ud1": "<id>", "ln1": "<id A>", "ln2": "<id A>", …}`; nhóm: file của mẻ đầu, dùng cho cả nhóm). Tối đa 2 vòng rồi `CẦN_USER`. Nhắn không được (agent đã hết) mới mở agent mới với brief + thẻ + dòng lỗi, rồi cập nhật id trong file.
+  - **Nhắn không được vì phiên không có `SendMessage`** (headless `claude -p`; Bash/Agent vẫn có): coi như mọi agent viết "đã hết" ngay từ đầu. Lỗi ≤ 2 câu → `Edit` như trên. Lỗi nhiều câu → 1 agent `tvc-tho` MỚI (foreground) cho mỗi mã trượt, prompt = phần chung C2 y nguyên + phần riêng của mã (thẻ) + đoạn "SỬA (không viết mới)" kèm nguyên khối dòng lỗi của mã trong `<B>_sua-theo-agent.md` — mẫu ở references/prompt-chang.md mục C2. Các mã trượt gửi trong CÙNG 1 message; ghi id mới vào `<B1>_agent-viet.json`. Vẫn tối đa 2 vòng rồi `CẦN_USER`.
 - **Nhóm N mẻ (khi anh bảo "chạy/làm N mẻ"; 1 mẻ thì như cũ — anh chốt 30/09/2026):** `python "$S/trang_thai.py" nhom "$P" --so N` tạo N mã mẻ liên tiếp (khoá `"nhom"` trong file trạng thái). Mỗi mẻ vẫn ĐỦ 21 kịch bản / 20 voice / 20 video riêng. `tiep` tự xử lý: **C0–C2 theo NHÓM** (in cả nhóm; ghi tay 1 lệnh `--batch B1,B2,…`), **từ C3 các mẻ SONG SONG**. C1: `khuon_hook.py gan --batch B1,…,BN` (gán 1 lần, giữ tỉ lệ xoay vòng theo kênh gốc, trần lặp khuôn tính trên cả nhóm) → **1 subagent dàn N×21 bản trong 1 file chung** `kich-ban/<B1>_dan-canh-chung.md` (Bước 3) → `dan_canh.py kiem --ghi` tách `<B>_dan-canh.md` từng mẻ + ghi `dan_canh` cả nhóm — không mẻ nào phải chờ đọc dàn cảnh mẻ trước. C2: 1 brief chung `kich-ban/<B1>_brief-viet.md` → **18 agent cho CẢ nhóm** (1 agent/công thức viết bản đó cho mọi mẻ, tự làm khác hook/góc/câu; louisnone A = `ln1 ln2` × N, B = `ln3 ln4` × N) — 17 lần khởi động + đọc brief thay vì 17 × N. Chấm/soát/đối chiếu vẫn TỪNG MẺ; bản trượt → nhắn tiếp agent đã viết mã đó (id trong `<B1>_agent-viet.json`) kèm dòng lỗi của mẻ trượt. **C3→C5:** mẻ nào qua C2 là giao ngay (`tiep` in dòng `song song: …`); khi mọi mẻ đã qua C2, `tiep` in "C3→C5 SONG SONG" → điều phối viên gửi N lời gọi Agent trong CÙNG 1 tin nhắn (mỗi mẻ 1 subagent, prompt điền từ `tiep "$P" --batch <B>`). Voice N mẻ chạy cùng lúc; `run` tự xếp hàng bằng `.render.lock` (1 mẻ/dự án, mẻ sau chờ tối đa 3 giờ) nên render vẫn nối tiếp liền; mẻ nào `verify` ĐẠT là C5 đẩy Poster ngay.
```

**Đoạn 2.** Lý do: Thêm 1 dòng bảng "Lỗi hay mắc" sau `:239`: dòng cũ chỉ dạy "mọi SendMessage trong 1 message"; thêm cặp sai/đúng cho phiên headless.

```diff
--- E:\claude\tao-video-tu-canh-quay\SKILL.md
+++ E:\claude\tao-video-tu-canh-quay\SKILL.md
@@ -239,2 +241,3 @@
 | C2 `sleep` 4–7 phút chờ agent viết rồi mới chấm cả mẻ, nhắn sửa lẻ từng tin | Agent trả về là chấm NGAY; mọi SendMessage sửa trong 1 message, ≤ 5 phút (cache) — dán khối `<B>_sua-theo-agent.md` |
+| Phiên headless không có `SendMessage` mà vẫn cố nhắn agent cũ, hoặc trả `CẦN_USER` vì "không nhắn được" | ≤ 2 câu `Edit`; nhiều câu giao agent `tvc-tho` MỚI: phần chung C2 + thẻ + đoạn SỬA kèm khối lỗi của mã (mục "Bản trượt", nhánh "nhắn không được") |
 | Mẻ không nói giá mà vẫn gán khuôn hô giá (ud H10, htd H13, sql H11…) | Mặc định đã loại (cần `"noi_gia": true` mới mở khuôn giá); kiểm `du_lieu` có lỡ ghi `noi_gia` không; không gán lại tay |
```


## K-2 — `E:\claude\tao-video-tu-canh-quay\references\prompt-chang.md`

**Đoạn 1.** Lý do: Sau `:96-97`: câu cũ "dán thẳng vào SendMessage"; thêm chỗ dán thay thế khi không có `SendMessage`.

```diff
--- E:\claude\tao-video-tu-canh-quay\references\prompt-chang.md
+++ E:\claude\tao-video-tu-canh-quay\references\prompt-chang.md
@@ -97,2 +97,3 @@
   đầy đủ — cần chi tiết thì grep đúng mã. KHÔNG Read 11-cong-thuc.md (agent viết dùng thẻ); viet-tu-canh.md chỉ mục brief nếu cần.
+  Phiên không có `SendMessage` (headless `claude -p`): khối của mã trượt trong file đó dán vào đoạn SỬA của agent MỚI (nhánh "Không có SendMessage" dưới), không nhắn.
   **Phát theo 2 đợt (có Codex xem sớm):** đợt 1 = 3 agent `ud1`, `nn1`, `tr1` (công thức khác giọng nhau, cùng 1 message, foreground);
```

**Đoạn 2.** Lý do: Sau `:129` (khối "Chấm ngay, sửa trong 5 phút", gồm `:126`): đây là phần điều phối viên DÁN vào prompt subagent C2. Subagent C2 không đọc mục "Chạy theo chặng" của SKILL.md (`trang_thai.py dong_skill` chỉ cho đọc Luật, Thư mục, Bước 4), nên nhánh thay thế bắt buộc phải nằm ở đây, kèm mẫu đoạn "SỬA (không viết mới)" cho agent `tvc-tho` mới.

```diff
--- E:\claude\tao-video-tu-canh-quay\references\prompt-chang.md
+++ E:\claude\tao-video-tu-canh-quay\references\prompt-chang.md
@@ -129,2 +130,11 @@
   không đợi cả mẻ. Nhắn không được (agent đã hết) mới mở agent mới (brief + thẻ + dòng lỗi), cập nhật id. Tối đa 2 vòng -> CẦN_USER.
+  **Không có `SendMessage`** (danh sách công cụ của bạn không có nó — chạy headless `claude -p`, vd phiếu có khối `CHẾ ĐỘ CHẠY`
+  của bộ chạy việc web): không nhắn, không thử gọi. Lỗi ≤ 2 câu -> `Edit` như trên. Nhiều câu -> mỗi mã trượt 1 agent `tvc-tho`
+  MỚI (foreground), mọi mã trong CÙNG 1 message, prompt = PHẦN CHUNG y nguyên + phần riêng của mã + đoạn:
+  ```
+  SỬA (không viết mới): bản hiện có <P>/kich-ban/<B>_<ma>.txt. Lỗi cần sửa (nguyên khối của mã này trong <B>_sua-theo-agent.md):
+  <khối dòng ❌ của mã>
+  Chỉ thay đúng câu/cụm bị nêu bằng Edit, giữ nguyên mọi câu khác, đếm lại trần chữ. Không viết lại cả bản. Rồi tự kiểm cham_me --ma như trên.
+  ```
+  Ghi id mới vào `<B1>_agent-viet.json`. Vẫn tối đa 2 vòng -> CẦN_USER.
   **Codex duyệt kịch bản (anh yêu cầu 20/10/2026; sau khi cả mẻ qua `cham_me` + `soat_chinh_sach` + `doi_chieu_canh`, TRƯỚC voice):**
```

**Đoạn 3.** Lý do: Sau `:202` (C2 nhóm, gồm `:201`): áp cùng nhánh cho nhóm N mẻ (khối lỗi theo từng mẻ).

```diff
--- E:\claude\tao-video-tu-canh-quay\references\prompt-chang.md
+++ E:\claude\tao-video-tu-canh-quay\references\prompt-chang.md
@@ -202,2 +212,4 @@
   1 message trong 5 phút (như C2 1 mẻ; không sleep chờ).
+  Không có `SendMessage` -> nhánh "Không có SendMessage" của C2 1 mẻ: agent MỚI cho từng mã trượt của từng mẻ (đoạn SỬA ghi đúng
+  mẻ `<B>` và khối lỗi của mẻ đó), mọi lời gọi trong CÙNG 1 message.
   Thẻ: `the_cong_thuc.py kiem` 1 lần cho cả nhóm trước khi fan-out. Id agent lưu ở `kich-ban/<B1>_agent-viet.json` (dùng cho cả nhóm).
```


## Bước chép K-2 sang bản cài (bước RIÊNG, cần duyệt; trưởng phòng chạy)

`SKILL.md:215`: sửa ở nguồn `E:\claude\tao-video-tu-canh-quay\`, chạy 2 bộ test, rồi chép sang `C:\Users\Mi\.claude\skills\tao-video-tu-canh-quay\`. Lúc soạn đề xuất, nguồn và bản cài của 2 file này GIỐNG HỆT (`diff -q` rỗng).

1. Sao lưu bản cài (đặt ngoài `skills/` để không bị nạp trùng):
   `mkdir -p /c/Users/Mi/.claude/backups/tao-video-tu-canh-quay-truoc-K2/references && cp /c/Users/Mi/.claude/skills/tao-video-tu-canh-quay/SKILL.md /c/Users/Mi/.claude/backups/tao-video-tu-canh-quay-truoc-K2/ && cp /c/Users/Mi/.claude/skills/tao-video-tu-canh-quay/references/prompt-chang.md /c/Users/Mi/.claude/backups/tao-video-tu-canh-quay-truoc-K2/references/`
2. Test (đúng `SKILL.md:208-209`; `S` trỏ bản cài như `SKILL.md:97` — K-2 chỉ sửa .md nên script không đổi):
   `PY="F:/auto video oneshot/.venv/Scripts/python.exe"; S="C:/Users/Mi/.claude/skills/tao-video-tu-canh-quay/scripts"; python "$S/gon.py" --buoc test_tu_canh -- "$PY" "$S/test_tu_canh.py"; python "$S/gon.py" --buoc test_scripts -- "$PY" "$S/test_scripts.py"`
   Ghi chú: `trang_thai.py dong_skill` (`:472`) và test ở `test_tu_canh.py:1304` tính khoảng dòng SKILL.md theo tiêu đề mục, K-2 không thêm/đổi tiêu đề nào. Test đọc `HERE.parent/SKILL.md` của bản cài, nên chạy test SAU bước 3 mới kiểm được bản mới (chạy cả trước và sau để so).
3. Chép:
   `cp /e/claude/tao-video-tu-canh-quay/SKILL.md /c/Users/Mi/.claude/skills/tao-video-tu-canh-quay/SKILL.md && cp /e/claude/tao-video-tu-canh-quay/references/prompt-chang.md /c/Users/Mi/.claude/skills/tao-video-tu-canh-quay/references/prompt-chang.md`
4. Kiểm: `diff -q /e/claude/tao-video-tu-canh-quay/SKILL.md /c/Users/Mi/.claude/skills/tao-video-tu-canh-quay/SKILL.md; diff -q /e/claude/tao-video-tu-canh-quay/references/prompt-chang.md /c/Users/Mi/.claude/skills/tao-video-tu-canh-quay/references/prompt-chang.md` → rỗng.

Tác động: ghi đè 2 file của bản cài (mọi phiên `tao-video-tu-canh-quay` sau đó đọc bản mới); `gon.py` ghi log test vào thư mục log của nó. Hoàn tác: chép ngược 2 file từ `C:\Users\Mi\.claude\backups\tao-video-tu-canh-quay-truoc-K2\`.

## Kiểm sau khi ghi thật (lệnh của §13)

- K-1: `grep -n "phiên sống\|SendMessage\|CẦN_USER" /c/Users/Mi/.claude/agents/aff-taovideo.md`
- K-2: `grep -n "không có .SendMessage." /e/claude/tao-video-tu-canh-quay/SKILL.md /e/claude/tao-video-tu-canh-quay/references/prompt-chang.md`
- Frontmatter 6 agent không đổi (không hunk nào chạm dòng 1–5).
