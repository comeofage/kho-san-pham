# Nhật ký Phòng Kỹ sư Culiapp — kho-san-pham

## Ca 2026-11-23-a — Tab Radar UID (LỚN) (phiên Agency, worktree E:/phantichcanhquay/kho-san-pham-radar-uid, nhánh feat/radar-uid)
- Yêu cầu: tab "📡 Radar UID" (#/theo-doi): chủ nhập 1 UID → tự tìm SP tương tự (EchoTik keyword) → snapshot hằng ngày → xếp hạng UID "đang được đẩy" (view tăng đột ngột / ai đăng cũng view cao / nghi ads) → sang Poster qua luồng duyệt sẵn có. Hội đồng: C:/Users/Mi/.claude/hop/Agency-20261123-1336/. Bảng chốt yêu cầu: người dùng "Đúng, làm đi". NGOÀI PHẠM VI: tự đăng Poster, deploy Worker, khởi động lại runner/app, sửa trendradar.db. Người dùng ủy quyền TOÀN QUYỀN cho trưởng phòng đến khi hoàn thành (trừ deploy/khởi động lại thật — vẫn để cuối, chờ báo).
- Git: nhánh riêng feat/radar-uid từ main@71489c5; main còn 2 file sửa dở của người khác (nhat-ky.md, web/index.html) — không đụng.
- Mốc ratchet (23/11, chạy ở main): JS 574 test / 571 pass / 3 TRƯỢT CÓ SẴN (homnay-web:337 viec.js onclick=; poster-web:796 main:has(>.pv-khung); pv-folders-web:198 badge captions — P2/P3 của ca 2026-11-22-a, không thuộc việc này); pytest 1987 passed; engine 33 passed.
- RU-0 (trưởng phòng chạy, 7 GET EchoTik, token mới): /videos 39 video/1 trang; update_time video đổi 39/39 giữa 2 lần cách 3 s còn views_count đổi 0/39 → KHÔNG dùng update_time video làm mốc; is_promote 1/39; keyword trả 10 dù per_page=50. Token EchoTik đã thay (user chủ động đăng nhập, bản cũ .bak_20261123 ở E:/timsanpham).
- Thiết kế: A-RU1 (docs/radar-uid.md + D16). Review R-RU1: CHƯA ĐẠT (4 P1: update_time video làm mốc, cửa sổ tuổi 2-7 ngày rỗng, thiếu chỉ số cho tiêu chí 1-2, trần 150>hạn mức Free) → sổ bài học đã ghi (4 dòng, agent culiapp-architect). A-RU1b sửa. Review hẹp R-RU2: còn 1 P1 (trung vị trên catalog cũ mù) → A-RU1c sửa (tập "video đang sống", tong_delta_top5, KHONG_LAM_MOI chỉ khi ≤1 video đổi). Hết vòng review thiết kế (tối đa 1 vòng); A-RU1c không review lại — kiểm lại ở review toàn bộ cuối.
- Quyết: duyệt thiết kế thay người dùng (ủy quyền toàn quyền) — Q1 nút Poster không tự điền UID; Q2 trần mặc định 60 GET/ngày; Q3 is_promote chỉ hiện số thô, không bật nhãn ads (ADS_BAT=False). — Vì: reviewer + số đo. — Nếu sai: sửa hằng NGUONG/ADS_BAT, không đổi cấu trúc.
- Bước kế: lượt 1 (6 phiếu song song: RU-B1, RU-B2, RU-A1, RU-W1, RU-B4, RU-W2), chup snap-luot-1. Lượt 2 (RU-A2, RU-B3), lượt 3 (RU-A3, RU-D1 xong, RU-T1 thêm test vào LENH). Cuối: review toàn bộ, kiem-chung đầy đủ, hỏi người dùng 3 lựa chọn git + tích hợp.
- Lượt 1 (RU-B1 89 test, RU-B2 62, RU-A1 56, RU-W1 169 [kèm worker+hoc-worker], RU-B4 263 [test_video_server], RU-W2 36 test mới + 4 file test cũ 138/140): so SẠCH (mọi file trong phạm vi). kiem_san: noqa E402 ở test_runner_echotik = BÁO OAN (import qua sys.path, tiền lệ ca 11-22); type: ignore[return-value] ở kho_radar_uid.py:163,170 = ép kiểu hẹp sau hàm kiểm (không phải tắt checker lỗi thật, dự án không chạy mypy) → ghi P3, không trả. RU-W2: còn đúng 2 trượt SẴN CÓ (homnay-web:337, poster-web:796) trong 4 file test của nó; RU-W2 tự thêm 1 dòng rduDung() ở mnRoute và nút "Chụp lại hôm nay" (route /api/radar/chup-lai có trong §7). Chưa chạy kiem-chung đầy đủ (làm sau lượt 3). Điểm CẦN CHỐT cho lượt 2 (từ báo cáo B1/B2/A1): che_do lan_chay = 'nap'|'hang-ngay'; ghi_tuong_tu đọc khoá tuỳ chọn do_giong của UngVien; ds_can_chup(ngay, goc=None); chuan_video trả None khi thiếu views_count; creator rỗng gom thành 1; dat_trang_thai_nhom có thể ghi đè 'ngung' → script phải đọc lại trạng thái; mã lỗi echotik: token_het_han|rate_limit|khong_tim_thay|dinh_dang|mang.
- Quyết: không chạy kiem-chung giữa lượt 1 và 2 — các agent lượt 2 sửa file ở runner/test có sẵn, chạy song song dễ đỏ giả — nếu sai thì lỗi hồi quy lộ muộn hơn sau lượt 3, nhưng có mốc 1987/571.
- Bước kế: lượt 2 = RU-A2 + RU-B3 (song song).
- Lượt 2 (RU-A2 42 test [có đột biến], RU-B3 926 test trong 6 file pytest runner): so SẠCH (khai_ma_khong_doi test_runner_api.py = do tôi đưa nhầm vào --agent-khai; B3 báo không sửa). kiem_san: noqa E402 ở test = BÁO OAN; except Exception noqa BLE001 ở radar_uid.py:437/459/464 = đúng khuôn chốt chặn hoc_tu_dong.py:834-844; chay_runner.py:147 log + canh_bao lên /suc-khoe (không nuốt im), :322/vong_lap.py:1466 có sẵn hoặc có lý do ghi rõ → chấp nhận, không trả phiếu.
- Phát hiện lỗi thật giữa các phiếu (A2 báo): radar_uid_tinh._mau_top_video bật cờ khi thứ tự dang_luc tăng, nhưng kho đọc video ORDER BY video_id (id TikTok tăng theo thời gian) → cờ MAU_TOP_VIDEO luôn bật với dữ liệu thật. Đã ghi sổ bài học (P1, RU-B1). Sửa ở lượt 3: RU-B5 (bỏ vế thứ tự, giữ vế last_page).
- B3 báo 3 hành vi ngoài bảng §7 cần ghi vào đặc tả (RU-D2): tim-lai trên nhóm ngung → 409 'Nhóm đã ngừng: bật theo dõi lại trước'; theo-lai nhóm chưa từng tìm xong tự tạo việc nạp; bảng trả cả UID loai ở cuối (nút Bỏ loại) trong khi §5.4 ghi 'loai ẩn'. Quyết: su_kien không ghi cho tim-lai/chup-lai (log + su_kien runner.db đủ) — vì kho_radar_uid thuộc B2 đã xong và việc này chỉ là vết — nếu sai thì chỉ thiếu 1 dòng vết trong radar_uid.db.
- Bước kế: lượt 3 = RU-A3 (test nối đầu-cuối) + RU-B5 (sửa MAU_TOP_VIDEO) + RU-D2 (cập nhật docs/radar-uid.md, bo-chay-viec.md, giao-dien-menu-trai.md, DECISIONS.md). Rồi RU-T1 (LENH kiem-chung), kiem-chung đầy đủ, review toàn bộ.
- Lượt 3 (RU-A3 11 test nối đầu-cuối [đột biến last_page=2 làm đỏ đúng cờ], RU-B5 89 test [đỏ thật rồi xanh], RU-D2 docs): so SẠCH; kiem_san: noqa E402 + N802 (do_GET của http.server) = BÁO OAN. RU-A3: không thấy lỗi nối nào; ngân sách khớp 25 GET nạp (E1×11+E2×11+E4×3), 22 GET/ngày; token giả không rò ở stdout/stderr/log/DB. RU-T1 (trưởng phòng): thêm 8 file test vào LENH .culiapp/kiem-chung.py (cf/test radar-worker + radar-uid-web; tools test_runner_echotik, radar_uid_{tinh,kho,script,api,noi_day}).
- Lượt 4 (RU-W4 nhãn MAU_TOP_VIDEO "50 video đầu trang" + nâng radar-uid.js?v=2; RU-B6 4 câu TEN_LY_DO_RADAR [đỏ 4 rồi xanh 415]): so SẠCH, kiem_san 0 vi phạm.
- Bước kế: kiem-chung đầy đủ (chạy nền /tmp/kc_cuoi.log), review toàn bộ (reviewer 1 lượt nhìn cả thay đổi), báo người dùng + hỏi 3 lựa chọn git + bước tích hợp (deploy Worker, cài runner, khởi động lại runner/video_server — CHƯA làm, chờ duyệt).
- Review toàn bộ R-RU3: CHƯA ĐẠT (0 P0, 1 P1, 3 P2, 8 P3; token/XSS/quyền/SQL/regression sạch). P1: nhóm 'loi_tim' bị bỏ khỏi chụp hằng ngày dù UI dặn thêm tay (sổ bài học đã ghi); P2: ô View đổi sai mẫu số (đã ghi sổ), nhóm kẹt 'dang_tim', lượt hang-ngay 'xong' im lặng khi 0 UID chụp được. Đã sửa ở lượt 5–6: RU-B7 (ds_can_chup lấy da_tim+loi_tim), RU-A4/A4b (khong_chup_duoc; chặn redirect EchoTik; cập nhật test ghim), RU-B8 (gỡ kẹt dang_tim khi không có việc nạp mở; xoá mã chết), RU-W5 (ô View đổi dùng n_doi+ti_le_doi), RU-D3 (đặc tả §6.7 Hạn chế đã biết), RU-B9 (câu khong_chup_duoc). Mọi lượt: so SẠCH, kiem_san: noqa E402/N802/D401 = báo oan; 'mất test' = thay test ghim hành vi sai bằng test chặt hơn (tổng +14).
- Review hẹp R-RU4: ĐẠT (0 P0/P1). Còn treo (P2): (1) lượt hang-ngay vẫn 'xong' khi UID bị khoá số lần thử (so_lan_thu>=2) — cần đếm so_het_luot; (2) hủy việc nạp rồi bấm Tìm lại ngay có thể chồng tiến trình cũ chưa chết (hiếm, không mất dữ liệu); (3) nhóm chỉ gồm UID không có video → lượt 'loi' mỗi ngày (chủ ý, nên ghi §6.3). P3: HTTPError chưa e.close(); tim-lai lỗi sau cho_tim có thể để nhóm cho_tim; docs/radar-uid.md:263 nói 'loi' đi theo tu_chay_lai (sai: chỉ việc bị ngắt lúc khởi động lại); kiem_han_muc gọi 2 lần.
- KIỂM CHỨNG CUỐI (23/11, worktree feat/radar-uid): JS 645 test / 642 pass / 3 TRƯỢT CÓ SẴN (homnay-web:337, poster-web:796, pv-folders-web:198 — đúng 3 mốc đầu); pytest 2504 passed (mốc 1987; chạy bằng LENH bỏ tools/test_vtk.py vì file đó chỉ là untracked ở main, worktree không có — lỗi môi trường có sẵn của LENH, không phải việc này); engine 33 passed. Mức kiểm chứng cả việc: fixture. CHƯA: EchoTik thật với daemon, runner/video_server/Worker thật, trình duyệt thật, đồng thời thật cho cửa sổ hủy/tim-lai.
- CHỜ DUYỆT: tích hợp (deploy Worker `npx wrangler deploy`, chép runner `tools/cai_runner.py`, khởi động lại runner + video_server KHÔNG dùng /T, thêm "radar_uid_bat" nếu muốn tắt lịch) — người dùng cần duyệt riêng; chạy thử nạp 1 UID live (≈35–40 GET EchoTik); merge feat/radar-uid vào main (main còn 2 file sửa dở của người khác).
- TÍCH HỢP (23/11, người dùng duyệt: 'deploy' rồi 'Cài và khởi động lại'): (1) `npx wrangler deploy` từ worktree → Worker kho-san-pham version a2181513 (https://kho-san-pham.kutidak.workers.dev); bản live trước đó (deploy 07:02 UTC) chưa có dòng pv-folders.js?v=9 chưa commit ở main nên không mất gì. (2) Dừng runner PID 55916 (taskkill /PID, không /T; 0 việc dang_chay) → `python tools/cai_runner.py` (từ worktree): sao lưu runner.db.bak-20261123-180726, cài phiên bản 99ec202 vào E:\kho-runner\app. (3) Bật runner bằng Python312 (KHÔNG dùng python của uv: thiếu psutil → thoát ngay, đã gặp) → 8788 lên, radar_uid_hang_ngay tự chạy bù 'xong' (chưa có nhóm → 0 GET), radar_uid.db tạo; 4 việc douyin_uid can_tra_loi giữ nguyên. (4) video_server: chép ĐÚNG 1 file tools/video_server.py từ nhánh vào E:\phantichcanhquay\kho-san-pham\tools (file sạch, == HEAD) vì video_server chạy từ main; dừng PID 36672 (không /T, Poster PID 18564 sống tiếp) rồi bật lại bằng python uv ở cwd main/tools → 8787 lên. Kiểm: /r/radar/bang 200 qua 127.0.0.1:8787 và qua tunnel https://video.kutidak.com, /r/radar/x 404, không khoá 401, runner /suc-khoe phien_ban 99ec202.
- LƯU Ý khi gộp nhánh: main đang có tools/video_server.py SỬA CHƯA COMMIT (== bản trên nhánh feat/radar-uid) nên `git merge feat/radar-uid` sẽ từ chối tới khi người dùng commit hoặc `git checkout -- tools/video_server.py` file đó trước (không mất gì, nội dung giống nhánh). main còn 2 file sửa dở của người khác (nhat-ky.md, web/index.html) cũng cản merge: cần commit/xử lý trước.
- CHƯA làm: chạy thử nạp 1 UID thật (≈25 GET EchoTik, cần người dùng đưa UID gốc); chưa đăng nhập chủ kho để xem tab trên giao diện thật; chưa gộp nhánh vào main.
- CHẠY THỬ LIVE (23/11 18:27, người dùng: 'vào kho-san-pham chọn 1 uid'): chọn UID 1735549089874019878 (Khối Rubik 3D Biến Hình, mới nhất trong kho). them_goc qua KhoRadarUid (boi=truong-phong) rồi `python -B -m runner.radar_uid --che-do nap ... --viec-id tay20261123 --tran-goi 60` (Python312, cwd app) → xong, so_uid=5, so_goi=15/60. Nhóm da_tim: gốc + 5 tương tự (còn <10 vì lọc độ giống/giá). 1 UID tương tự (1732258581196605567) EchoTik chưa có video → ghi 'loi/khong_co_video' (đúng thiết kế). 2 UID bật MAU_TOP_VIDEO (last_page=2, tức >50 video). Mọi UID còn 1 snapshot ⇒ 'chưa đủ bằng chứng', THIEU_MAU: chỉ số đột biến cần ≥2 ngày chụp, đáng thử cần ≥4 snapshot ≥70h; lịch hằng ngày 10:00 sẽ tự chụp tiếp (runner đang chạy). /radar/bang qua video_server trả đúng, token ok, goi_hom_nay 15.

## Ca 2026-11-22-a — Review sức khoẻ web (ad-hoc, không phiếu) (phiên Agency)
- Yêu cầu: "review web Tiniweb" — audit tổng quát, không gắn với ticket/thay đổi nào. culiapp-reviewer (chỉ đọc)
  soi toàn bộ `cf/src/worker.js`, `web/*.js`, `cf/test/*.test.mjs` đối chiếu README/DECISIONS/docs.
- Phát hiện: **P1** `/api/login` không khoá sau nhiều lần sai mật khẩu (khác các luồng khác đều qua
  `kiemMatKhauCoDem`) — mã `moi:login-khong-khoa-sai-mat-khau`. **P2** badge "📄 N captions" thiếu trong
  `web/pv-folders.js` so với test `pv-folders-web.test.mjs` — mã `moi:badge-caption-count-thieu`. **P3** 2 test
  tự false-positive (`viec.js` property `onclick=` JS hợp lệ bị regex CSP bắt nhầm; `poster.css`
  `main:has(>.pv-khung)` hợp lệ nhưng lệch quy ước đặt tên `.pv-*`) — mã `moi:test-qua-chat-false-positive`.
  Nhiễu/cần hỏi: timing side-channel ở login (giá trị thấp, 4 username đã công khai), `ghi_chu` không che đường
  dẫn máy nhà cho user thường (có chủ đích, ghi trong code, đáng hỏi lại), vài route `docBody()` không có trần
  kích thước thân request như `apiViec`/`apiPoster`.
- `so` sau review: `vi_pham_khong_ro` chỉ `data/**` (sản phẩm mới + `data/index.json`) — hệ thống sống (kho.py/
  người dùng) tự ghi trong lúc reviewer chạy, reviewer không có tool Write/Edit, báo cáo tự khai "không sửa file
  nào" → KHÔNG trả phiếu, không vi phạm. Đã xoá snapshot `.culiapp/snap-review-adhoc1.json` sau khi xong.
- Chưa ghi sổ bài học (`bai_hoc.py`) — đây là review code sẵn có trong production, không phải lỗi của một
  kỹ sư culiapp-* vừa viết trong ca này, nên không gán cho agent nào.
- Chưa sửa gì (người dùng chỉ yêu cầu review). Câu hỏi thứ 2 của người dùng ("học tự động mỗi ngày cho web")
  đã hỏi lại qua AskUserQuestion → chọn cả 3: hiệu suất video/sản phẩm thật + sửa tay nhân viên + lỗi vận hành.
  Chưa giao phiếu nào cho hướng này — đang chờ người dùng chốt có muốn làm thiết kế (architect) hay không.

## Ca 2026-11-22-b — Học tự động mỗi ngày (LỚN) (phiên Agency)
- Người dùng chốt thêm: TỰ áp dụng vào gợi ý mặc định (không duyệt từng lần); chạy trên kho-runner; báo cáo +
  hoàn tác trong web Kho. Bảng chốt yêu cầu (3 nguồn: hiệu suất thật, sửa tay nhân viên, lỗi vận hành; cỡ mẫu tối
  thiểu; không nguồn trả phí mới; NGOÀI PHẠM VI: sản phẩm cũ, Telegram/email, API TikTok/EchoTik, /api/login) —
  người dùng "Đúng, làm luôn".
- Sổ bài học: `dem` = [] (không mã nào đạt ngưỡng).
- Bước 3: snap-thietke.json → giao A-HT1 culiapp-architect (docs/hoc-tu-dong.md + D15 Đề xuất).
- A-HT1 DONE_WITH_CONCERNS: docs/hoc-tu-dong.md (1428 dòng) + D15 (DECISIONS.md:655). Khảo sát thật: Radar 0/26.850
  alert khớp UID kho, product_name rỗng 100% → đề xuất dùng view video của mình trong DB Poster V2
  (video_view_snapshots, 1.528 video, 4 ngày dữ liệu); nguồn "sửa tay" không tồn tại (không route sửa caption/USP,
  commit AI và người cùng tác giả); không có dữ liệu giỏ hàng; runner không có cơ chế hẹn giờ; nguồn view phụ thuộc
  script ngoài C:\Users\Mi\view-poster. Câu hỏi mở Q1–Q6 (§11). Lo ngại: cài runner sẽ kéo theo schema 4 của D14.
  8 phiếu / 4 lượt. `so`: đúng 2 file khai; vi_pham_khong_ro chỉ data/** = runner commit `ghi`/`rui-ro` 4 SP
  (16:51–17:11) — người khác sửa, không trả phiếu.
- Bước 3.2: snap-review-thietke.json → giao R-HT1 culiapp-reviewer phản biện (hiện vật + bảng chốt, không kèm
  báo cáo architect).
- R-HT1: CẦN SỬA — P1-1 nguồn view chạy tay không lịch + tiêu chí đếm ngày tự dừng là "chạy xong"; P1-2 thu hẹp
  "mẫu USP/công thức caption" không hỏi; P2 x6 (--chi-doc ghi lan_hoc, hết hạn chỉ xét khi script chạy, luật giữ
  vận hành, test chạm production qua env_toi_thieu/giờ thật, tích hợp kéo theo D14 web/Worker/video_server, tự tắt
  không hoàn tác); P3 x10. Xác nhận: không chuỗi không tin cậy vào phiếu; hoàn tác đúng D7/D12; mô phỏng null
  1,1–1,3%/khoá/ngày. `so` review: chỉ data/** (runner `ghi` 7510f1e) — sạch. Đã ghi sổ bài học 2 P1
  (culiapp-architect, A-HT1, mã moi:nguon-view-chay-tay-khong-lich, moi:thu-hep-hop-dong-khong-hoi).
- Người dùng chốt (AskUserQuestion): nguồn view "Lên lịch tự quét hằng ngày" (nới 'không gọi thêm TikTok' cho
  riêng lượt quét view của mình); "Chỉ đặc trưng caption"; sửa tay "Bỏ đợt này"; "Giữ ngưỡng chặt". Trưởng phòng
  tự quyết: Q2/Q3/Q4/Q6 theo (a); tự tắt có "bật lại" ký D7; chạy lại phan_tich_uid UID cũ do người bấm vẫn nhận gợi ý.
- A-HT1b (vòng sửa 1/1): snap-thietke-2.json → culiapp-architect, ĐƯỢC SỬA docs/hoc-tu-dong.md, D15,
  docs/bo-chay-viec.md (chỉ dòng trỏ).
- A-HT1b DONE_WITH_CONCERNS: sửa đủ P1-1..P3-10 (Phụ lục B đối chiếu). Chuỗi quét view = bao_cao_view.py →
  tiktok_scan.py (yt-dlp --impersonate chrome, không đăng nhập/cookie/Chrome) → ghi_view_poster.py. Chạy thẳng
  KHÔNG an toàn (Apify tốn phí bật được qua channels.json, kênh lỗi vẫn exit 0 và vẫn ghi DB số chép, không giới
  hạn giờ) → thiết kế bọc `quet_view.py` (chặn Apify, timeout giết cây, chỉ ghi khi mọi kênh ổn, ≤3 lần/ngày,
  nhường mutex Radar), lịch trong runner 09:00, học 12:00. Mở lại Q7: con số 5,8% đã báo khi chốt Q5 là một phía —
  thật ra ~9–12%/khoá/ngày, ~27% có ít nhất 1 khoá đạt nhầm; khuyến nghị nâng 70%→80% (1,2%). Q8: bài học người
  hoàn tác có cho bật lại không. Bài học đầu tiên khó có trước giữa 12/2026. 9 phiếu / 4 lượt; §10 có 10 bước cần
  duyệt (bước 0: D14 phải được duyệt vì cài kéo theo D14).
- `so` vòng sửa: sạch, đúng 3 file khai (bo-chay-viec.md chỉ +5 dòng trỏ, đã đọc diff). Agent tự khai vi phạm nhỏ:
  `mkdir -p /tmp/hocpt` (rỗng, ngoài GOC) → trưởng phòng đã rmdir. Đã xoá snap-thietke-2.json.
- Người dùng (AskUserQuestion): Q7 "Nâng lên 80% (Recommended)"; Q8 "Cho trong 7 ngày (Recommended)";
  duyệt thiết kế "Duyệt, giao code".
- A-HT1c (snap-chot): D15 → Đã chốt; ngưỡng 80%; bật lại bài người hoàn tác trong 7 ngày (bài hoàn tác lúc còn
  ứng viên → về ung_vien, không nhảy hiệu lực — architect tự quyết, trưởng phòng chấp nhận vì không đi tắt ngưỡng).
  `so` sạch (2 file). TREO nhỏ: docs/bo-chay-viec.md còn 3 dòng trỏ ghi "D15 (Đề xuất)" — để phiếu tài liệu cuối ca.
- Bước 4: ghi 10 phiếu vào bang-viec.json (A-HT1 xong; HT-B1/A3/A1/W1/W2 lượt 1; HT-B2/B3 lượt 2; HT-A2 lượt 3;
  HT-T1 lượt 4). Git: làm thẳng trên main như các ca trước (kho.py tự pull --rebase --autostash/push main — rủi ro
  đã biết); code dirs sạch trước lượt 1.
- Mốc ratchet (kiem-chung trước lượt 1): JS 495 tests / 492 pass / 3 fail có sẵn (đúng 3 cái R-adhoc: onclick viec.js,
  poster.css :has, badge captions); Python 1519 passed + 1 failed test_poster_web::test_nhat_ky_moi_lenh_ghi_mot_dong
  = CHẬP CHỜN (chạy riêng 3/3 pass; sự kiện nền ket_thuc ghi sớm khi máy bận); engine 33/33.
- Lượt 1 (snap-luot-1): HT-B1 backend ∥ HT-A3 automation ∥ HT-A1 automation ∥ HT-W1 web ∥ HT-W2 web — đang chạy.
  - HT-W1 DONE_WITH_CONCERNS: cf/src/hoc.js mới, worker.js +4/-2 (import, export goiMayNha/traVeMayNha, 1 route),
    151/151 (124 cũ + 27). Tự thêm: 5xx HTML/524 từ edge → JSON 502/504 như poster.js; deps thêm laChuKho — chấp nhận.
  - HT-A1 DONE_WITH_CONCERNS: video_server.py +15/-5, test 123→201. Chặt hơn §3.8: `ngay`/`gioi_han` chỉ nhận ở
    đúng tuyến hoc (không nới R_QUERY_KHOA chung), 405 sai method ngay tại video_server — chấp nhận; TREO: sửa dòng
    §3.2/§3.8 'R_QUERY_KHOA thêm ngay' trong docs (test_hop_dong_hoc_trich_dung_tai_lieu đọc bảng §3.8 — giữ bảng).
  - HT-W2 BLOCKED: khung.js đổi phải tăng ?v= nhưng cf/test/poster-web.test.mjs:782 ghim v=4. Trưởng phòng duyệt (A):
    nới duoc_sua thêm đúng dòng 782 của poster-web.test.mjs + index.html khung.js?v=5; giao lại chính agent.
    Phần còn lại: JS 514/517 (3 đỏ có sẵn), đột biến 13/14 đỏ (M7c tương đương).
  - HT-W2 vòng 2 DONE: poster-web.test.mjs chỉ đổi dòng 782 (v=4→5), index khung.js?v=5; JS 514/517 (3 đỏ có sẵn).
    Trưởng phòng đối chiếu nhãn: web HC_THIEU thiếu 4 mã backend (huong_lech, so_lan, ty_le, chua_co_nguon) → hiện mã
    thô đã esc; HC_LY_DO_NGAN chỉ 4 mã (mã khác không hậu tố) → phiếu nhỏ HT-W2b chạy cùng lượt 2.
  - HT-B1 DONE_WITH_CONCERNS: 58/58, ruff sạch, 16 đột biến đỏ (bỏ riêng lớp lọc SQL hết hạn = tương đương, lớp Python
    vẫn chặn). Thêm 4 mã LY_DO_CHUYEN (dat_lan_dau, dem_chuoi, dat_lai_chuoi, gia_han — 3 mã sau lọc khỏi thay_doi);
    bao_cao/ds_bai_hoc thêm kw bat_ngay/hieu_luc_toi_da; kiểm chặt viec_id/boi/so_lieu; mode=ro tạo -shm/-wal rỗng
    (§10 bước 6 phải loại -shm khi so sha256). Gợi ý HT-B2: nhat_quan_pt chia làm tròn xuống.
  - HT-A3 DONE_WITH_CONCERNS: 56/56 x2, ruff sạch, 23 đột biến S1–S7 đều đỏ (S4 ban đầu 2 lớp che nhau → thêm test
    từng lớp). Thêm: khoá quet_view/.khoa, trần tổng 22 phút, ly_do mọi dòng JSON. Lo ngại: ghi_view_poster.py luôn
    ghi DB thật đường dẫn cứng (--poster-db chỉ để đếm); chạy tay §10 bước 5 không tự hoãn khi Radar chạy → kiểm
    Radar trước khi chạy; tác động §10.5 thêm .khoa và các <ngày>-*.log.
  - `so` lượt 1: sạch — 9 file mới + 11 file sửa, đúng phạm vi, khớp khai; không file ngoài (cả data/** không đổi).
  - `kiem_san` lượt 1 exit 1: video_server.py:324 except OSError = BÁO OAN (có sẵn, số except OSError 12→12, dời dòng);
    quet_view.py:180/403/418/431 except psutil.* khi giết/duyệt cây = CHẤP NHẬN; :196 except Exception → None+log =
    CHẤP NHẬN (hợp đồng §3.4a S6); :468 open không with, đóng trong finally sau khi giết cây = CHẤP NHẬN; :605 pragma
    no cover nhánh fcntl non-Windows = CHẤP NHẬN; noqa DTZ (giờ naive khớp script thật) = CHẤP NHẬN; test: BaseException
    chuyển lỗi luồng, except khi đọc pid file tạm, skipif win32 mutex = CHẤP NHẬN. bo_qua rỗng.
  - Trưởng phòng thêm vào kiem-chung LENH: hoc-worker, hoc-web, test_runner_hoc_kho, test_runner_quet_view. Ratchet đang chạy.
  - Ratchet sau lượt 1: JS 544 tests / 541 pass / 3 fail = đúng 3 đỏ có sẵn (mốc 492 pass); Python 1712 passed 0 failed
    (mốc 1519 + 1 chập chờn); engine 33. Không giảm.
- Bước 6 review lượt 1 (snap-review-1): R-L1a culiapp-reviewer (HT-B1, HT-A3) ∥ R-L1b culiapp-reviewer (HT-A1, HT-W1, HT-W2
  + đối chiếu BaoCao thật của kho_hoc) — đang chạy. Lượt 2 chờ kết quả review.
- R-L1b: CẦN SỬA — P1-1 web không so bc.ngay với hôm nay (api hoc/bao-cao không ngay → runner trả lần học mới nhất)
  → báo cáo cũ hiện như hôm nay, mất báo đỏ khi bộ học ngừng. Xếp loại 1 = HỢP ĐỒNG MƠ HỒ (§3.9 chỉ đặc tả so_ngay_cu,
  kỹ sư làm đúng chữ) → không ghi sổ. Trưởng phòng quyết sửa ở web (so ngày, hiện ngày số liệu, đỏ 'Bộ học chưa chạy từ
  dd/mm'). P3 x7 (nhãn thieu lệch 4+5 mã; bài vận hành gắn 'SP/% cùng chiều'; tóm tắt thiếu hoan_tac/bật lại về ứng
  viên, dut_chuoi đếm thành 'gợi ý'; 'bởi he_thong' thô; 503 KY_RIENG/404 RE_R cũ báo sai nguồn; nút kẹt khoá khi rời
  rồi quay lại #/hoc; 'lúc này' cho bài không bao giờ bật lại) → gộp vào HT-W2b. Ba chặng khớp path/method/mã lỗi;
  bảo mật không thấy lỗi. Ghi cho HT-B3: API runner phải truyền bat_ngay/hieu_luc_toi_da thật vào bao_cao/ds_bai_hoc.
  Reviewer tự khai đã chạy `git stash list` (chỉ đọc) — ghi nhận, không vi phạm thay đổi.
- R-L1a: ĐẠT (0 P0/P1), 114 test xanh, ruff sạch. P2-1 chữ tự do từ hoc.db sửa tay lọt ra BaoCao/BaiHocRa (không lọt vào
  phiếu); P2-2 hạ hoc_hieu_luc_toi_da/hoc_bat_ngay về 0 không chặn bài hiệu lực vào phiếu, còn gia hạn (trái §4.3);
  P2-3 bỏ sót <view_dir>/yt-dlp.conf (yt-dlp đọc config ở cwd) → quét không người canh có thể dùng cookie; P2-4 log
  quét không truy theo lần (CL20). P3 x9 (TOCTOU channels trước ghi, co_the_bat_lai sau hoàn tác dùng hạn mức mặc định,
  tuan_thu không có chỗ lưu → HT-B2/B3 sẽ BLOCKED, mẫu cap_co_so có thể đẩy '100%'/giảm giá, cap_menh_lenh đo một
  khuyên một, vận hành 'giam' không mẫu, trần bật theo ngày học không theo ngày lịch, bang_chung vận hành đóng băng,
  test quét view dùng date.today(), PID tái dùng/ROLLBACK che lỗi/mypy _mot_ra). Không P1 → không ghi sổ bài học.
  Reviewer chạy thử trong %TEMP% để lại tmpqe4nwgbi\hoc.db → trưởng phòng đã xoá.
- `so` review lượt 1 (cả 2 reviewer): sạch, 0 file đổi. Đã xoá snap-review-1.json.
- Trưởng phòng quyết (chỗ hở giữa phiếu): cầu dao áp ở goi_y_hieu_luc(hieu_luc_toi_da) — trần 0 → [] và không gia hạn;
  tuan_thu lưu trong hoc.db (chỉ số nguyên) qua hàm ghi mới, bao_cao/ds_bai_hoc đọc; hoan_tac/bat_lai nhận hạn mức thật.
  P1-1 R-L1b sửa ở web. Lượt 2 = vòng sửa: HT-B1b ∥ HT-A3b ∥ HT-W2b. HT-B2/B3 → lượt 3, HT-A2 → lượt 4, HT-T1 → lượt 5.
- Lượt 2 (snap-luot-2):
  - HT-W2b DONE_WITH_CONCERNS: hoc.js + index hoc.js?v=2 + hoc-web test (36). So bc.ngay với hôm nay VN, đỏ 'Bộ học chưa
    chạy từ dd/mm'; HC_THIEU/HC_LY_DO_NGAN khớp đúng hoc_danh_muc (test đọc thẳng .py); hcLoaiLoi phân biệt nguồn lỗi;
    vẽ lại phiên hiện hành sau POST. JS LENH[0] 559/556/3 (3 đỏ có sẵn). Ghi cho HT-B3: runner trả đúng
    {"loi":"Học tự động chưa bật"} 503. TREO P3: POST xong đúng lúc trang Hôm nay đang tải → khối có thể còn số cũ.
  - HT-B1b DONE_WITH_CONCERNS: 84 test (58+26), 16 đột biến đỏ, ruff sạch. Interface mới: goi_y_hieu_luc(hieu_luc_toi_da);
    hoan_tac(ma, boi, *, bat_ngay, hieu_luc_toi_da); bao_cao(ngay, *, bat_ngay, hieu_luc_toi_da); ds_bai_hoc(gioi_han=50, *,
    bat_ngay, hieu_luc_toi_da); ghi_tuan_thu(ngay, ds); KHOA_TUAN_THU; mã cap_nhat_so_do; thay_doi[].boi có thể null;
    bai_hoc thêm cột tuan_thu/tuan_thu_ngay (schema vẫn '1', chưa cài máy thật). Trưởng phòng quyết: hoc_bat_ngay=0 tắt
    HẲN gợi ý vào phiếu (HT-B3 gọi goi_y_hieu_luc(0 if bat_ngay==0 else toi_da)); trần hạ >0 vẫn gia hạn mọi bài = TREO P3.
  - HT-A3b DONE_WITH_CONCERNS: 83 test x2, đột biến đỏ, ruff sạch. Chặn {cwd}/yt-dlp.conf, {python dir}/yt-dlp.conf,
    config-location/-P; log theo lượt (--nguon tay|runner, mặc định tay), log con <ngày>-l<lan>-*.log không ghi đè;
    kiểm hash channels trước báo cáo và trước ghi; la_con_minh (create_time); DONG_HO_NGAY. Ghi cho HT-B3: lap_buoc thêm
    '--nguon','runner'. Tài liệu §3.4a/§10.5 cần tên log mới. TREO: khe TOCTOU vài ms trong ghi_view_poster (mã ngoài).
  - `so` lượt 2: sạch, 8 file đúng phạm vi, khớp khai. `kiem_san`: exit 0 (sạch).
  - Ratchet sau lượt 2: JS 559/556/3 (3 đỏ có sẵn); Python 1765 passed 0 failed; engine 33. Không giảm.
- Lượt 3 (snap-luot-3): HT-B2 backend (hoc_tu_dong.py) ∥ HT-B3 backend (danh_muc/phieu/kieu/han_muc/api) — đang chạy.
  Phiếu kèm interface HT-B1b nguyên văn + quyết định: cầu dao bat_ngay=0; hạn mức thật vào API; 503 nguyên văn;
  --nguon runner; chặn ở _tao_viec; không lộ su_kien thô.
  - HT-B2 DONE: hoc_tu_dong.py (CLI --ngay --hoc-db --poster-db --runner-db --repo (--viec-id|--chi-doc) --bat-ngay
    --hieu-luc-toi-da; stdout 1 dòng JSON) + test_runner_hoc_tu_dong.py (125 cùng hoc_kho).
  - HT-B3 DONE: 2 loại việc hệ thống, argv khớp cả 2 CLI (trưởng phòng soát danh_muc ~1000-1016); lay_goi_y_hoc có
    cầu dao; ma_goi_y_trong_phieu; /hoc/* + 503 nguyên văn; chặn loại hệ thống ở _tao_viec kể cả chay-lai. Runner test 556→691.
  - `so` lượt 3: exit 0, 2 file mới + 9 file sửa đúng phạm vi, data 0.
  - `kiem_san` exit 1, 4 mục — đều không trả phiếu: hoc_tu_dong.py:290/:493 `type: ignore` (dict dựng động gán TypedDict —
    chấp nhận); :430/:512 `except (ValueError, RecursionError)` bỏ dòng JSON hỏng từ dữ liệu không tin cậy, trả None/bỏ
    dòng đúng thiết kế (chấp nhận); test_runner_han_muc.py:15 `noqa: E402` sau sys.path (báo oan, như các ca trước).
  - Trưởng phòng thêm tools/test_runner_hoc_tu_dong.py vào LENH kiem-chung.
  - Ratchet sau lượt 3: JS 556 pass / 3 đỏ có sẵn (không đổi); Python 1941 passed (mốc 1765); engine 33. Không giảm.
- Review R-L3 (reviewer, snap-review-3): ĐẠT, 0 P0/P1. `so` review: chỉ 5 file data/ đổi = runner tự ghi kho
  (commit db9b0d3 "ghi 1738083993239520429") → người khác sửa, không vi phạm. Xếp loại:
  - P2 CL14 trần SO_VIEC_TOI_DA ORDER BY tăng dần cắt việc mới nhất mà báo ok → lỗi thật (P2, không vào sổ) → HT-B2c.
  - P3 UTF-8 hỏng dừng cả nguồn poster_view với lý do sai; P3 --chi-doc có đường thoát không in JSON; P3 mypy 7 lỗi → HT-B2c.
  - P3 het_gio 25 phút quet_view < ca xấu nhất: NHIỄU — quet_view.py tự giới hạn tổng 22 phút (HT-A3b).
  - Ghi chú cầu dao hoc_bat_ngay=0 quay về 1 khi cau_hinh.json hỏng / cần khởi động lại runner: theo luật hạn mức
    chung có sẵn → đánh đổi chấp nhận, báo người dùng.
- Lượt 4 (snap-luot-4): HT-A2 automation (vong_lap/chay_runner + 2 test) ∥ HT-B2c backend (hoc_tu_dong + test).
  - HT-B2c DONE_WITH_CONCERNS: 136 test hoc_tu_dong+hoc_kho, ruff sạch, mypy 0 lỗi ở hoc_tu_dong. khoang_can_doc + lọc SQL
    DESC + bi_cat; text_factory → CHU_HONG đếm bo_dong_hong; chay() in đúng 1 lần, chốt chặn loi_bat_ngo. TREO P3: web
    chưa hiện bi_cat (bao_cao lọc khoá cố định, cần sửa kho_hoc.py).
  - HT-A2 DONE_WITH_CONCERNS: 546 + 971 test qua. HEN_GIO_MAC_DINH, _hen_gio (chặn trùng theo khoá ngày + dem_trong_ngay
    gồm việc ẩn), _ghi_ap_dung ngay sau lap_buoc_hieu_luc (theo §3.7 — ghi kể cả khi lượt Claude sau đó lỗi: chấp nhận,
    đúng tài liệu), _mo_kho_hoc lỗi → canh_bao + None. TREO: kết nối hoc.db của luồng làn daemon không đóng chủ động.
  - `so` lượt 4: 6 file đúng phạm vi, khớp khai. vi_pham_khong_ro: data/* (runner push 3529597) + web/pv-folders.js,
    cf/test/pv-folders-web.test.mjs (12:02-12:03, tính năng tick Product ID trang Poster — PHIÊN KHÁC đang sửa cùng repo)
    → người khác sửa, không trả phiếu. KHÔNG gộp 2 file pv-folders vào commit của việc này.
  - `kiem_san` exit 1: 8 `except Exception  # noqa: BLE001` — 7 mới đúng yêu cầu phiếu (ghi vết không chặn việc, chốt
    chặn JSON, hẹn giờ không giết làn, đóng hoc.db vẫn nhả khoá), đều có log → chấp nhận; vong_lap.py:1453 có sẵn → báo oan.
- Review R-L4: ĐẠT, 0 P0/P1/P2. `so` review: chỉ file của phiên Poster khác (pv-folders.js + test, docs/poster-v2-tren-web.md,
  web/index.html) → người khác sửa. LƯU Ý COMMIT: web/index.html chứa cả thẻ hoc.js của D15 lẫn sửa của phiên kia.
  P3 treo (không kéo vòng): P3-1 bi_cat báo nhầm khi khoảng phụ rỗng (hoc_tu_dong:509-512); P3-2 dòng queue hỏng che
  tình trạng mơ hồ (:402-424); P3-3 _in ngoài chốt chặn (:801); P3-4 lỗi hẹn giờ kéo dài log traceback mỗi 2 s
  (vong_lap:1363); P3-5 ghi ap_dung trước khi Claude được sinh (đúng chữ §3.7, đếm dư khi huỷ trước bước).
  Lo ngại §10 bước 7: bật lịch cần khởi động lại runner (hm đọc lúc khởi động) → đưa vào bước duyệt.
- Ratchet sau lượt 4: JS 557 pass / 3 đỏ (index.html loi.js+homnay.js; poster.css; pv-folders "(a) chữ nguyên văn" —
  cùng 3 đỏ có sẵn, +1 pass do phiên Poster); Python 1972 passed (mốc 1941); engine 33. Không giảm.
- Lượt 5 (snap-luot-5): HT-T1 culiapp-web DONE_WITH_CONCERNS — 10/10 test x2 lần, ruff sạch, không lệch hợp đồng chặng.
  Ca 7 dùng ngày 7/8 thay ngày 5/6 của §8.4 (do hoc_bat_ngay=1/ngày) → chấp nhận, ghi cho phiếu sửa tài liệu. Harness
  thêm 2 trường dieu_khien/tam → chấp nhận. TREO (ngoài phạm vi): luồng HTTP runner mở kết nối runner.db (dung_nonce)
  không đóng tường minh → giữ khoá file tới gc trên Windows, runner chạy lâu có thể tích kết nối mồ côi.
  - `so`: 2 file mới đúng phạm vi; vi_pham_khong_ro data/* + web/index.html + web/pv-folders.js = phiên Poster khác.
  - `kiem_san`: 4 mục trong harness test hoc_noi_gia.py (except OSError khi client ngắt / shutdown, 500 cho test đọc)
    → chấp nhận (dọn dẹp harness, không phải code chạy thật).
  - Trưởng phòng thêm cf/test/hoc-noi-day.test.mjs vào LENH.
- Bước 7: R-CUOI (reviewer toàn bộ, snap-review-cuoi): CHƯA ĐẠT — 1 P1, 4 P2, 7 P3. Xếp loại (đã đối chiếu code):
  - P1-1 `moi:bai-chi-bao-cao-chiem-cho` (kho_hoc.py:465-491 không lọc ap_phieu=False) → LỖI THẬT, đã ghi sổ bài học
    (phiếu HT-B1). Trưởng phòng chọn hướng (a): khoá ap_phieu=False KHÔNG tạo dòng bai_hoc, chỉ đo + canh_bao_van_hanh
    (web đã có khối "Lỗi vận hành lặp lại").
  - P2-2 báo cáo "Đang dùng" khi cầu dao tắt → lỗi thật (backend + web).
  - P2-3 mẫu gợi ý va kho.py kiem_captions (số đầu dòng, vế ≥4 chữ lặp >4 dòng, quota cứng dễ bịa số) → lỗi thật.
  - P2-4 đọc toàn bảng snapshot không WHERE → lỗi thật (CL16).
  - P2-1 hạn mức chỉ đọc lúc khởi động, §10 không nhắc khởi động lại → hợp đồng thiếu: sửa tài liệu + đưa vào bước duyệt.
  - P3-1 tài liệu lệch hoc_bat_ngay=0 → sửa tài liệu. P3-2 cap_menh_lenh tự mâu thuẫn → sửa cùng P2-3.
  - P3-3 CAS theo trạng thái đã ghi, P3-4 ghi vết sớm, P3-5 hoãn 'ban' ghi sai lý do mỗi 60 s, P3-6 quet_view/ không dọn
    log, P3-7 ruff I001 hoc_noi_gia → TREO, báo người dùng.
  - Kết luận rò kết nối runner.db (HT-T1 lo ngại 6): reviewer đọc api.py thấy _goi_kho_hoc đóng sau request; phần
    dung_nonce chưa soi riêng → vẫn TREO.
  - `so` review cuối: sạch (reviewer không sửa gì).
- Ratchet cuối (trước lượt 6): JS 567 pass / 3 đỏ có sẵn; Python 1 failed / 1971 passed — test_video_server
  ::test_pid_nghe_cong_doc_netstat_that, chạy riêng 3/3 qua, pid_nghe_cong không bị đụng → CHẬP CHỜN (netstat lúc máy
  tải nặng, nhiều agent chạy server); engine 33.
- Lượt 6 (snap-luot-6): HT-B4 backend ∥ HT-W3 web (hợp đồng trường han_muc/vao_phieu do trưởng phòng chốt trong cả 2
  phiếu) ∥ HT-D1 architect (tài liệu).
  - HT-B4 DONE_WITH_CONCERNS: 537 Python + 50 node xanh, ruff sạch. la_ap_phieu; _chon_goi_y dùng chung cho goi_y_hieu_luc
    và vao_phieu; mẫu "Nếu … thì ưu tiên khoảng N/100"; 14 caption mẫu qua kho.kiem_captions; lọc collected_at
    [ngay−74, ngay]; bi_cat SELECT 1; _in có dự phòng. TREO P3: mẫu cap_menh_lenh còn "đừng" ("đừng bỏ lỡ" hơi hối thúc);
    409 bật lại dòng chỉ báo cáo dùng câu chung khong_the_bat_lai; tuân thủ đếm SP không có số là "không làm theo".
  - HT-W3 DONE_WITH_CONCERNS: hoc-web 40/40; hoc.js?v=3. 2 đỏ trong lệnh gộp = 2 trong 3 đỏ có sẵn. TREO P3: câu xác
    nhận "Bật lại" vẫn ghi "sẽ vào phiếu" khi cầu dao tắt.
  - HT-D1 DONE_WITH_CONCERNS: tài liệu A1–A10 + B, §12a việc treo T1–T10, Phụ lục C; sửa ví dụ 15/21 → 17/21 (không
    qua được 80%). BÁO NGƯỜI DÙNG: hoc_bat_ngay=0 nay tắt hẳn gợi ý (rộng hơn câu đã duyệt "tắt tự áp dụng").
  - `so` lượt 6: 11 file đúng phạm vi, khớp khai; data/* = runner push. `kiem_san`: 2 except dự phòng in JSON (phiếu
    yêu cầu) → chấp nhận. Tài liệu đã có vao_phieu/han_muc/lưu(?! ý).
- R-L6 (review vòng sửa 1): CẦN SỬA nhẹ, 0 P0/P1. `so` review sạch. Ratchet sau lượt 6: JS 571/3 đỏ có sẵn; Python 1983;
  engine 33 — không giảm.
  - P2-1 mẫu cap_menh_lenh còn gợi "săm" (=sắm/mua) và "đừng" (FOMO) → lỗi thật (P2, không vào sổ). Trưởng phòng quyết:
    gợi ý chỉ còn thử/xem/lưu + "không dùng 'ngay', 'kẻo hết', 'đừng bỏ lỡ'".
  - P3-3/4/5 tài liệu lệch code; P3-7 vao_phieu lệch khi bang_chung hỏng; P3-2 mất "nguồn cũ N ngày" khi biên rỗng → sửa.
  - P3-1 SQLite vẫn SCAN toàn bảng (DB chỉ đọc, không index) → chấp nhận, ghi §12a. P3-6 nghi vấn 2 dòng JSON khi flush
    lỗi → TREO.
- Lượt 7 (snap-luot-7, vòng sửa 2 — cuối): HT-B4b backend ∥ HT-D1b architect.
  - HT-B4b DONE_WITH_CONCERNS: 245 Python + 50 node xanh, ruff sạch. DONG_TU_GOI_Y_MENH_LENH = thử/xem/lưu; mẫu tăng
    rút còn 298 ký tự (test khoá ≤300); _chon_goi_y bỏ bài ghep_goi_y None; _ngay_snap_moi_nhat khi biên rỗng.
    TREO P3: MAX(collected_at) có thể trả ngày trong biên khi mọi dòng trong biên hỏng.
  - HT-D1b DONE_WITH_CONCERNS: §3.6/§3.7/§3.8/§12a T11–T14/D15. Câu mẫu cap_menh_lenh tài liệu viết trước khi backend
    chốt → TRƯỞNG PHÒNG tự chép đúng hằng thật vào docs/hoc-tu-dong.md:498 (việc NHỎ 1 dòng, chép nguyên văn hằng).
  - `so` lượt 7: 7 file đúng phạm vi; `kiem_san` sạch.
- R-L7 (review vòng sửa 2): ĐẠT, 0 P0/P1/P2; `so` review sạch. P3 treo: trần hieu_luc_toi_da và SO_DONG_GOI_Y_TOI_DA
  chưa khoá bằng test (khớp vì cùng 5); MAX(collected_at) bị chuỗi ngày sai dạng che; §3.6 chép SQL MAX thiếu WHERE,
  "hai"→"ba" truy vấn; §3.8 vao_phieu có ở mọi BaiHocRa + câu "đang sửa song song" cũ.
- Ratchet cuối: JS 571 pass / 3 đỏ có sẵn; Python 1987 passed (mốc đầu ca 1765); engine 33. Không giảm.
- GIAO CA: 19 phiếu xong. Mức kiểm chứng cả việc = unit (HT-W3 web), phần runner/backend fixture + test nối dây 3 chặng.
  CHƯA chạy thật: cài runner, khởi động lại video_server, deploy Worker, quét view thật, bật lịch (§10 bước 0–9, hỏi
  người dùng từng bước). Đã xoá snap-*.json. Commit: chờ người dùng; LƯU Ý tách web/index.html (phiên Poster cũng sửa)
  và loại web/pv-folders.js, cf/test/pv-folders-web.test.mjs, docs/poster-v2-tren-web.md, data/*.

## Ca 2026-11-21-dp — Trang ⚙ Việc: dừng/ẩn/phân trang (phiên Agency)
- Yêu cầu người dùng (qua ảnh chụp trang ⚙ Việc): cho dừng việc đang chạy, cho "xoá" (chốt = chỉ ẩn/lưu trữ,
  KHÔNG xoá cứng vì D7/D9 ký theo id việc), phân trang cố định 10 dòng/trang. Khảo sát trước thấy `/huy` đã dừng
  được việc đang chạy từ lâu (chỉ thiếu nút trên thẻ danh sách) nên KHÔNG viết cơ chế dừng mới.
- Lượt 1: DP-1 backend (cột `luu_tru`, `dat_luu_tru`, `dem_loc`, `offset`, act `luu-tru`/`bo-luu-tru`,
  `tools/runner/kho_viec.py` + `api.py`), DP-2 web (nút Dừng/Ẩn trên thẻ + phân trang mỗi nhóm, `cf/src/worker.js`
  + `web/viec.js`), DP-4 web (phát hiện giữa chừng: tunnel `tools/video_server.py` có allowlist path/query riêng
  theo D2, chưa mở cho act/tham số mới — vá luôn, cùng lượt), DP-3 architect (docs/bo-chay-viec.md §3.2/§7.7/§8/§12
  + DECISIONS.md D14). so/kiem_san sau lượt: sạch (1 cảnh báo `# type: ignore` ở `kho_viec.py:520` là báo oan — idiom
  cũ có sẵn từ `chuyen()`, không phải DP-1 thêm). kiem-chung cuối lượt 1: JS vẫn đúng 3 lỗi có sẵn từ trước (không
  liên quan — một trong số là `nt.onclick=` property JS hợp lệ, không phải inline HTML, bị regex kiểm CSP bắt
  nhầm); Python 1496→1514 pass; engine 33/33 không đổi. Trưởng phòng tự bump `web/index.html` viec.js?v=15→16
  (việc nhỏ).
- Review R-DP1 (culiapp-reviewer, chỉ đọc): **CHƯA ĐẠT**. P1 `moi:an-viec-roi-chay-lai-an-tang-hinh` — `chuyen()`
  không xoá `luu_tru=1` khi việc đổi `trang_thai` ra khỏi `TRANG_THAI_DONG` (qua `chay-tiep`/`xin-duyet-lai` sẵn
  có) → việc đã ẩn có thể chạy lại (kể cả việc tốn tiền) mà biến mất khỏi mọi danh sách, vi phạm đúng ràng buộc đã
  chốt trong phiếu. Đã ghi sổ bài học (`bai_hoc.py them`, mã trên, phiếu DP-1). P3: `boi` của `luu-tru`/`bo-luu-tru`
  không ghi `su_kien` (mất dấu ai đã ẩn); docs nói nút Dừng cũng hiện ở `can_tra_loi` nhưng code/test chỉ hiện ở
  `dang_chay`. D7/D9/D2/CSP/schema migration: reviewer xác nhận ổn, không cần sửa DP-2/DP-4.
- Vòng sửa 1/2: DP-1 vá `chuyen()` (luôn `luu_tru=0` khi `den not in TRANG_THAI_DONG`, một chỗ duy nhất, có bằng
  chứng RED→GREEN) + ghi `su_kien` cho `luu-tru`/`bo-luu-tru` (289 pass, +6 test); DP-3 sửa đúng 1 câu §12. `so`
  sau vòng sửa: sạch cho 5 file của 2 phiếu; có 1 file ngoài phạm vi `data/1737981550082229795/info.json` đổi —
  đã kiểm là commit thật (`1fac632c`, 21/11 09:17) của hệ thống sống (kho.py/người dùng), không liên quan tới
  phiếu nào ở đây, không ai trong phòng khai sửa — không trả phiếu. `kiem_san` sạch.
- Review vòng 2 (chỉ soi phần vá): **ĐẠT**, 0 lỗi. Xác nhận bất biến `luu_tru=1 ⇒ trang_thai ∈ TRANG_THAI_DONG`
  đúng ở MỌI nơi ghi `trang_thai` (rà cả `vong_lap.py` — 10 lời gọi `chuyen()`, ngoài phạm vi phiếu nhưng reviewer
  tự soi thêm cho chắc), `su_kien` ghi đúng `boi` thật, test không giả, docs khớp code.
- KIỂM CHỨNG CUỐI (lượt 1 + vòng sửa): JS vẫn đúng 3 lỗi có sẵn từ trước khi bắt đầu việc này (không liên quan —
  đã đối chiếu từng cái, không file mới); Python 1496→1520 passed (+24 test); engine 33/33. `so` từ snapshot GỐC
  (trước lượt 1) tới giờ: sạch, đúng 13 file dự kiến (`tools/runner/kho_viec.py`, `tools/runner/api.py`,
  `tools/test_runner_kho_viec.py`, `tools/test_runner_api.py`, `tools/video_server.py`,
  `tools/test_video_server.py`, `cf/src/worker.js`, `web/viec.js`, `web/index.html`, `cf/test/worker.test.mjs`,
  `cf/test/viec-web.test.mjs`, `docs/bo-chay-viec.md`, `DECISIONS.md`) + 2 file dữ liệu sống không liên quan
  (`data/1737981550082229795/info.json`, `data/index.json` — hệ thống/kho.py tự commit, không phải phòng kỹ sư).
- Mức kiểm chứng cả việc: **unit** (thấp nhất trong các phiếu kỹ sư cấp 3 — DP-1/DP-2/DP-4 đều `unit`; DP-3
  `khong-ap-dung`, bỏ qua theo quy định). CHƯA chạy thật: chưa bấm thử trên trình duyệt thật (cần đăng nhập Worker
  + runner sống); chưa nâng `runner.db` thật trên máy nhà (ALTER schema "3"→"4" sẽ tự chạy ở lần khởi động kế tiếp
  của runner — không mất dữ liệu theo test, nhưng chưa kiểm trên file production); chưa deploy Worker
  (`npx wrangler deploy`); chưa cài lại bản runner (`tools/cai_runner.py`) + khởi động lại runner/video_server
  trên máy thật — các bước này đều là TÍCH HỢP cần người dùng duyệt riêng, không tự làm.
- Treo nhẹ (không chặn): §4.2 `docs/bo-chay-viec.md` (bảng schema) vẫn ghi "phiên bản 1", lạc hậu từ TRƯỚC việc
  này (schema thật đã ở '3' rồi '4') — kiến trúc sư nêu ở DP-3 nhưng ngoài phạm vi phiếu, để dành cho phiếu dọn
  tài liệu riêng sau này nếu cần.
- GIAO CA: 4 phiếu (DP-1 backend, DP-2 web, DP-3 architect, DP-4 web) + 1 vòng sửa (DP-1, DP-3) đều `xong`. Đã xoá
  `.culiapp/snap-*.json`. Đề xuất một commit gộp (code + `.culiapp/` trừ snap); CHƯA commit, chờ người dùng.

## Ca 2026-11-19-a — Gỡ trang Duyệt video + Đăng bài khỏi web Kho (phiên Agency)
- Yêu cầu: "Bỏ Duyệt Video luôn, Bỏ Đăng Bài luôn. Duyệt từ lúc tạo Video rồi" (đã có tab Poster V2). Làm trực tiếp, không qua phòng kỹ sư (chỉ gỡ web).
- Web: menu 7 → 5 mục; index.html bỏ dang.js, duyet.js (khung v4, loi v6, homnay v6, viec v13, app v24, sua v3); link cũ #/dang[/id], #/duyet[/id] → #/sp/<id> hoặc #/poster (chủ kho); bước 7 "Kiểm duyệt" luôn bo_qua ("duyệt lúc tạo video"); bước 8 → nút "Mở Poster V2" (trang:poster); Hôm nay SP da_lam_video → #/sp/<id>; màn sửa "← Về sản phẩm".
- File gỡ chuyển vào _da-go-20261119/ (web/dang.js, web/duyet.js, cf-test/dang-web, duyet-web — chưa từng commit nên không xoá). kiem-chung.py bỏ 2 test đó.
- Giữ nguyên: Worker (route duyet.json, poster_*), runner, dữ liệu duyet.json. Hệ quả: nút ✏ Sửa video chỉ có ở trang Duyệt → màn #/sua chỉ còn mở qua link việc; poster_bo_loai/poster_len_lich không còn chỗ tạo từ web; app.js còn hàm Tải về/laLoai dùng cho dang.js (chết, chưa dọn).
- Kiểm: JS 480 pass (13 file); kiem-chung Python 1483 + engine 33 QUA; web tĩnh 8797 + fetch giả: menu 5 mục, chuyển hướng đúng. Người dùng "Deploy đi" → `npx wrangler deploy` version 892f66cb-0ce7-4696-b423-125ed8705af1; web thật nạp khung v4, app v24, không còn dang.js/duyet.js (chưa kiểm sau đăng nhập).

## Ca 2026-11-18-f — Trang "Poster V2" trên web Kho (phiên Agency funny-hermann)
- Yêu cầu: "poster phải là 1 tab trên web" (sanpham.kutidak.com), bê nguyên 9 trang Poster V2, không sửa mã Poster. Người dùng chốt: mở công khai Internet; chủ kho bấm thẳng mọi nút ghi (không mật khẩu từng lần) → D13. Trước đó đã làm nhầm thành tab trong app Agency (commit a55d687, đã revert khỏi main Agency = 07106da) — bản Svelte đó dùng làm tham khảo.
- Phân loại: LỚN (3 tầng máy nhà/Worker/web + quyết định bảo mật mới).
- Mốc ratchet: kiem-chung QUA HẾT — JS (8 file) đạt hết, Python 1246 passed, engine 33 passed.
- A-PV1 (architect): docs/poster-v2-tren-web.md (752 dòng) + D13 Đề xuất. so sạch (chỉ 2 file đó).
- R-PV1 (reviewer phản biện): CHƯA ĐẠT — P1-1 hợp đồng content-type lệch 3 chặng (DELETE 415), P1-2 mất trạng thái lệnh đăng nền → đăng trùng, P1-3 test có thể chạm backend 8023 thật; P2 x5 (secret settings ra trình duyệt, homnay-web:325, thăm dò sau 401, UNC/NTLM ở _dem, sát trần 90 s); P3 x6. so review sạch. Ghi sổ bài học 3 P1 (agent culiapp-architect, phiếu A-PV1).
- Người dùng chốt thêm: API "Mở hết /api/v2/"; video Loại/hạn mức "Giữ nguyên như app gốc"; nút Login "Giữ, thêm dòng nhắc".
- A-PV1b (architect, vòng sửa 1): sửa đủ 3 lựa chọn + 16 phát hiện (bảng TÌM–SỬA trong báo cáo); thêm T-P1 test nối 3 chặng; tự thêm x-pv bắt buộc, cấm %, lệnh ghi S >80 s chuyển nền. so sạch.
- Duyệt thiết kế: người dùng "Đồng ý, làm đi" (gồm 3 chỗ tự thêm). A-PV1c: D13 Đã chốt; D3/D9/D12 ghi "Bị thay một phần bởi D13". so sạch.
- Lượt 1 (song song): B-P1 culiapp-backend (tools/poster_web.py, video_server.py ≤20 dòng, tools/test_poster_web.py) ∥ W-P0 culiapp-web (cf/src/poster.js, worker.js 2 dòng, cf/test/poster-worker.test.mjs) ∥ W-P1 culiapp-web (web/poster.js, poster.css, khung.js, index.html, cf/test/poster-web + menu-web + homnay-web). Mức cần: fixture.
- Lượt 1 xong: B-P1 DONE_WITH_CONCERNS (336 pytest qua: 222 mới + 114 test_video_server cũ; video_server.py +14 dòng); W-P0 DONE_WITH_CONCERNS (154 JS qua, worker.js +2 dòng); W-P1 DONE_WITH_CONCERNS (412 JS, 0 fail, 9 skip chờ pv-*.js). so: chỉ 13 file trong phạm vi, khớp khai. kiem_san exit 1: video_server.py 172/311/336 = BÁO OAN (số except không đổi so với snapshot, chỉ dời dòng; diff chỉ 14 dòng móc); poster_web.py:621 FileNotFoundError khi xoay nhật ký, :726 settimeout trên socket đã đóng = CHẤP NHẬN; test noqa E402 = BÁO OAN; test except OSError backend giả = CHẤP NHẬN. Trưởng phòng quyết: dòng nhắc nút Login dùng lớp .pv-nho (không sửa poster.css).
- CHỜ DUYỆT: B-P1 — khởi động lại video_server thật (taskkill pid :8787 → khởi động lại như cũ, không đặt KHO_POSTER_DIR/TT_API_*) để nạp /p/*. Trình cùng deploy Worker sau lượt 3.
- Lượt 2 (song song): W-P2 (pv-dashboard/views/logs/settings) ∥ W-P3 (pv-accounts/post) ∥ W-P4 (pv-folders) ∥ W-P5 (pv-calendar/queue) ∥ T-P1 automation (tools/poster_noi_gia.py, cf/test/poster-noi-3-chang.test.mjs).
- T-P1 DONE: 16/16 ca nối 3 chặng bằng mã thật, chạy 2 lần liền xanh, không sót tiến trình, không lệch hợp đồng.
- W-P2 DONE_WITH_CONCERNS: 4 trang + 31 test (đột biến 5 ca đều đỏ). SỰ CỐ: agent chạy `taskkill //F //IM node.exe` khi gỡ test treo → tắt MỌI node trên máy, gồm vite dev 1430 (C:\Users\Mi\Agency), 1431 (phiên khác), 1432 (bản thử của trưởng phòng), vite E:\shopee\frontend. Python (Poster 8023, video_server 8787) không bị. Đã báo người dùng.
- W-P3 DONE_WITH_CONCERNS: Accounts + Đăng bài, 25 test, đột biến 5 ca đều đỏ; lỗi tạm khi đăng → hỏi dangChay 1 lần, không tự gửi lại.
- W-P4 DONE_WITH_CONCERNS: Folders 34 test (81/81 lệnh phiếu), đột biến 5 ca đỏ. W-P5 DONE_WITH_CONCERNS: Calendar + Queue 23 test (70/70), đột biến 6/7 đỏ (M7 chốt thừa).
- so lượt 2: 15 file mới đúng phạm vi. vi_pham_khong_ro 9 file (cf/src/worker.js, web/app.js, index.html, khung.js, style.css, tools/video_server.py, test_video_server.py, cf/test/worker.test.mjs, poster-web.test.mjs) = NGƯỜI KHÁC SỬA: phiên "Bật tắt từng công cụ" (local_13150535…, cwd C:\Users\Mi\Agency) thêm POST /app/<ma>/bat|tat lúc 20:18–20:19; móc Poster còn nguyên (grep). Không trả phiếu. kiem_san: poster_noi_gia noqa E402 = BÁO OAN; except RuntimeError (tự kiểm chot_test) + except OSError khi chờ stdin = CHẤP NHẬN; video_server 174/313 = dời dòng do phiên khác (BÁO OAN).
- Lượt 3 (trưởng phòng): thêm 7 file JS poster + tools/test_poster_web.py vào kiem-chung.py. R-PV2 (review toàn bộ) đang chạy.
- kiem-chung (lượt 3): QUA HẾT — JS 533/533 (mốc 336), Python 1474 (mốc 1246; gồm 222 test_poster_web + phần phiên khác), engine 33.
- R-PV2: ĐẠT (0 P0/P1). P2-1 nhật ký mất khi đổi tên file bị khoá (tái hiện được; ghi sổ CL6 culiapp-backend B-P1). P3-1 ket_thuc thiếu status; P3-2 bảng lệnh đầy sớm do GET; P3-3 B1/B3 chặn lưu account không báo; P3-4 lỗi tạm Đăng bài gắn nhầm lệnh; P3-5 mypy/ruff/test signal (bỏ qua). so review sạch (reviewer tạo .ruff_cache — cache công cụ, git bỏ qua, chấp nhận).
- Lượt 3 sửa: FX-PB1 backend (poster_web.py + test: P2-1, P3-1, P3-2) ∥ FX-PW1 web (pv-accounts.js, pv-post.js + test: P3-3, P3-4).
- Cả 2 agent FX bị ngắt giữa chừng bởi lỗi API (billing) trước khi báo cáo; trưởng phòng kiểm tay: so chỉ 5 file trong phạm vi; code + test đủ cho P2-1/P3-1/P3-2 (pytest 222→231) và P3-3/P3-4 (JS 25→30). kiem_san: chỉ skipif win32 test khoá file = CHẤP NHẬN. kiem-chung: JS 538/538, engine 33, Python 1482 passed + 1 failed test_r_put_van_405 (WinError 10053, PUT có body tới /r/viec bị 405 không đọc body) → chạy riêng 5/5 qua, CHẬP CHỜN có sẵn, không liên quan Poster. Chưa chạy lại reviewer cho vòng sửa này (P2/P3, chấp nhận).
- Mức kiểm chứng cả việc: fixture (backend giả + test nối 3 chặng bằng mã thật). CHƯA: chạy trên trình duyệt thật, deploy, video_server thật, backend Poster thật, 9 trang với dữ liệu thật.
- ĐÃ XỬ LÝ DUYỆT: người dùng "Cả hai bước". (1) video_server: KHÔNG cần khởi động lại — pid 4144 chạy từ 19/11 08:09 (sau lần sửa poster_web.py cuối 18/11 20:49, do phiên khác khởi động lại); /p/health → 401 + x-kho-tu-choi: khoa. (2) `npx wrangler deploy` → version 43622a2b-7786-4a30-b3f4-2eb901c79780 (kho-san-pham.kutidak.workers.dev / sanpham.kutidak.com). Deploy kéo theo cả phần chưa commit của phiên "Bật tắt từng công cụ" (nút bật/tắt app).
- Kiểm live (chỉ GET, không đăng nhập, không chạm backend Poster): index có 11 thẻ poster/pv-*; 6 file mẫu 200; /api/poster/... chưa đăng nhập → 401; DELETE Origin lạ → 403 "Sai nguồn gọi"; video.kutidak.com/p/health không khoá → 401.
- GIAO CA: mức kiểm chứng = fixture + kiểm live đọc-không-đăng-nhập. CHƯA: đăng nhập chủ kho thật và mở #/poster xem 9 trang với dữ liệu thật; bấm thử một nút ghi; điện thoại 375px; lần quét folders đầu ~84 s qua Tunnel (~100 s). TREO: P3-5 (mypy/ruff, test signal 95 s); lệnh đăng khi video_server khởi động lại giữa chừng mất bảng theo dõi (D13 đã chấp nhận); test_r_put_van_405 chập chờn WinError 10053 trên Windows. Commit: chưa (kho.py day() tự push main công khai; code đợt 5–8 + Poster đều chưa commit).

## Ca 2026-11-18-e — Menu trái kiểu Poster V2 + trang Đăng bài (phiên Agency)
- Phản ánh: "quá rối rắm, chồng chéo, muốn đăng bài không biết làm sao" → muốn gọn như TikTok Poster V2. Phân loại: LỚN (đổi điều hướng cả web).
- Chốt với người dùng: menu trái 6 mục (Hôm nay · Sản phẩm · Cần quay · Duyệt video · Đăng bài · Máy nhà), thanh đáy trên điện thoại; trang Đăng bài không bắt chấm hết; video Loại không đăng; ⛔ Ngừng đăng khoá Lên lịch; dọn trang SP. Video Loại: chọn "dời sang _loai/ bằng việc miễn phí máy nhà" — đợt SAU (backend).
- Mốc ratchet: JS 236/239 (3 trượt P-33b = phiên khác đang làm dở), Python 1170/1172 (test_dieu_kien_truoc_hong_luc_nhan..., test_p1_1_instance_thu_hai...), engine 33.
- Đồng thời: một phiên khác (VideoBatchLocal) đang sửa cf/src/worker.js + test (P-33/P-33b). Người dùng chọn "Làm song song luôn".
- A-UI1 (architect): docs/giao-dien-menu-trai.md + D12 Đề xuất. Phát hiện: runner KHÔNG lọc video Loại khi poster_day_folder/poster_len_lich. so: chỉ docs + DECISIONS do architect; cf/src/worker.js, cf/test/worker.test.mjs, cf/.wrangler/tmp = phiên khác; data/** = kho tự commit.
- R-UI1 (reviewer phản biện thiết kế): CẦN SỬA — P1-1 khoá Loại chỉ lúc tạo việc (lọt qua duyệt/xin duyệt lại/chạy lại), P1-2 đụng độ phiên song song; P2-1..8, P3 x7. so review: snapshot snap-review-thietke.json bị phiên khác xoá (Bước 8 của họ) → soát tay: reviewer khai 'File đã sửa: không', git diff web/cf chỉ có phần P-33 của phiên kia. Phiên kia đã xong P-33/P-33b (ca 2026-11-18-d) → JS 239/239. Đổi tên ca này thành -e.
- Duyệt thiết kế: người dùng "Đồng ý, làm đi"; B-L1 "Làm luôn đợt này". A-UI1b/c sửa theo R-UI1, D12 Đã chốt, D10 ghi bị thay một phần.
- Lượt 40 (W-M1 ∥ W-M2 ∥ B-L1): W-M1 BLOCKED vì regex CSP viec-web:315 bắt viec.js sát app.js → cho sửa 1 dòng (A). B-L1 BLOCKED vì test_runner_vong_lap:1447 so khớp tuyệt đối poster_ds_folder → cho sửa 1 dòng (A). so: vi_pham_khong_ro chỉ cf/.wrangler/tmp/* (wrangler dev tự nạp lại) + data/** (kho tự commit) — không trả phiếu. kiem_san: poster_ds_folder.py:56 except khi reconfigure stdout = CHẤP NHẬN (mẫu cũ); noqa E402 trong test = BÁO OAN; skipif Windows-only test khoá file = CHẤP NHẬN. Trưởng phòng thêm menu/dang/duyet-web + test_runner_bo_loai vào kiem-chung.py.
- R-40: CẦN SỬA — P1 dk đọc duyet.json cũ (moi:dk-doc-du-lieu-cu), P1 _loai/ không hoàn tác trên web (moi:loai-khong-hoan-tac-tren-web) → ghi sổ bài học; P2 trả hàng loạt khi thiếu duyet.json, autostash, Ngừng đăng chỉ chặn ở nút; P3 x6.
- Lượt 41 (FX-B1 ∥ FX-W2 ∥ W-M3+W-M4 gộp): so sạch; kiem_san: bot-test test_doc_ket_qua_chua_co_file = đổi tên _la_none (BÁO OAN), bot-assert lap_buoc 7→6 = bỏ bước kho_xem theo phiếu (CHẤP NHẬN). kiem-chung QUA HẾT: JS 318, Python 1227, engine 33. Trưởng phòng thử web tĩnh 8797 + fetch giả: trang Đăng bài, Gỡ Loại tạo poster_bo_loai đúng, Duyệt có khối đã gỡ, 375px không cuộn ngang, trang SP 7 tab không vd-btns.
- R-41: CẦN SỬA — P1 Bỏ Loại không kích hoạt trả về (ghi sổ, cùng mã/phiếu W-M2), P2 git fetch treo (GCM, cháu giữ pipe), P2 fetch ngoài mutex kho, P2 Ngừng đăng hở compose_output; P3 x3.
- Lượt 42 (vòng sửa 2): FX-W3 (Bỏ Loại tự tạo poster_bo_loai, Kiểm lại đánh số lượt) ∥ FX-B2 (_chay_gioi_han file tạm + taskkill /T, GCM_INTERACTIVE=never, uid_cua_folder, che đường dẫn) + FX-W4 (nút Đồng bộ folder luôn hiện khi có poster_bo_loai). Trưởng phòng chốt: poster_len_lich KHÔNG giữ mutex kho (tránh chặn 30 phút), đụng .lock → ban. so sạch; kiem_san: except ProcessLookupError khi killpg = CHẤP NHẬN; test đổi tên = BÁO OAN.
- Lượt 43–45: FX-B3 (3 lượt fetch, trả fail-closed, _dk_bo_loai, che dấu cách) ∥ FX-W5; FX-W6 Worker giữ mục "" khi bỏ chấm; R-43 P1 Đạt/Bỏ duyệt sau Loại không đồng bộ → FX-W7; R-44 P1 tác dụng phụ gắn phiên trang (ghi sổ) → FX-W8 Worker TỰ tạo poster_bo_loai trong POST /api/duyet (dong_bo tao/trung/chua/null) + FX-W9 nhóm chờ về 3 ngày, gập. so/kiem_san sạch mọi lượt. kiem-chung cuối QUA HẾT: JS 336, Python 1246, engine 33.
- R-45: P1 409 "trung" khi việc bo_loai đang chạy đã fetch xong → lần chấm cuối không áp (moi:trung-viec-bo-lan-cham-cuoi); P2 không tự thử lại khi "chua" + nhóm chờ về ẩn sau 3 ngày; P3 x4 (timeout 20s, Origin /api/duyet, test quyền chấm Loại, gh() không timeout). Người dùng chọn "Deploy ngay, làm triệt để sau" (đồng bộ folder ngay trước mỗi lần lên lịch). Video Loại vẫn không lên lịch được (_dk_poster_len_lich chặn).
- CHỜ DUYỆT: deploy Worker + cài runner. ĐÃ XỬ LÝ DUYỆT: "Chạy cả hai"; lệnh cài sửa lại: "Chạy lệnh cài đúng".
- TÍCH HỢP (18/11 ~15:45): deploy Worker c6ed93ac (web loi v5, homnay v5, viec v12, khung v1, dang v3, duyet v6, app v22, sua v2). Cài runner: LẦN ĐẦU trưởng phòng truyền SAI `--dich E:/kho-runner` (phải là thư mục app) → script đổi tên cả E:/kho-runner thành kho-runner.cu và cài code vào E:/kho-runner; runner đang tắt, dữ liệu nguyên. Hoàn tác bằng đổi tên (bản cài sai để ở E:/kho-runner.sai-20261118, CHƯA xoá). Xin duyệt lại → `python tools/cai_runner.py` (mặc định) → sao lưu runner.db.bak-20261118-154526, app 6ac662e-sua → bật runner pid 41680 (Start-Process, WorkingDirectory E:\kho-runner\app), log khởi động sạch, 2 làn. Kiểm web thật #/dang/1731703798106392955: menu 6 mục, folder #322 còn 14, nút ↻ Đồng bộ hiện (runner có poster_bo_loai).
- GIAO CA: Mức kiểm chứng cả việc = fixture + xem bản thật (đọc, không tạo việc). CHƯA: chạy thật poster_bo_loai/poster_len_lich trên folder thật; GCM/HTTPS fetch thật; điện thoại thật. TREO: (P1 R-45) 409 khi bo_loai đang chạy làm lần chấm cuối không áp → đợt sau "đồng bộ folder ngay trước mỗi lần lên lịch" (người dùng chọn làm sau); P2 không tự thử lại khi dong_bo "chua", nhóm chờ về ẩn sau 3 ngày; P3: timeout 20 s khi chấm Loại lúc máy nhà chậm, Origin cho /api/duyet, test quyền chấm Loại, gh() không timeout, Lưu góp ý trên video Loại báo câu "Đã Loại", "Chưa duyệt" kèm boi/luc, Bỏ duyệt vẫn hỏi lại với mục "". Commit: chưa (main tự bị đẩy công khai bởi kho.py).
- COMMIT b67a707 trên nhánh LOCAL dot-8-menu-trai (cha dot-5-7 fd3e9f0), tạo bằng index tạm + commit-tree, không đụng main/worktree, không push (người dùng: "Nhánh riêng, không đẩy"). main vẫn 6ac662e, code đợt 8 vẫn nằm chưa commit trên main như cũ.

## Ca 2026-11-18-d — Phân quyền: chỉ nhan/comeofage thấy toàn bộ (P-33, P-33b)
- Yêu cầu: "chỉ có nhan và comeofage được thấy toàn bộ dữ liệu, tài khoản linh và thu chỉ nhìn thấy kho sản phẩm".
- P-33: người không phải chủ (ngoài USER_MAY_NHA) nav chỉ Kho; #/ → Kho; #/viec*, #/suc-khoe, #/sua → "chỉ dành cho chủ kho"; trang SP ẩn Bước tiếp theo + tab Làm video. Worker anTruongNoiBo bỏ thu_muc_may, da_lam_video.duong_dan/poster_folder, poster[].duong_dan ở ds/sp/them/quay/tag/ghichu.
- R-33 ĐẠT; P2-1 đường dẫn ổ đĩa trong tom_tat/md/douyin → P-33b cheDuongDan (quét data thật: 403 chỗ che, 0 URL bị đổi, 0 sót). Trưởng phòng: ghi_chu không che (tránh người thường Lưu đè bản đã che).
- P3 treo: danh sách chủ lặp ở web/app.js (nên lấy cờ từ /api/me); #/sua sai định dạng → Kho thay vì câu chặn.
- SỰ CỐ: kho.py chạy git pull --rebase --autostash vào thư mục làm việc (12:01, 12:16); lần 12:01 worker.js về HEAD, đã khôi phục từ stash@{0}. Stash autostash cũ còn 3 cái — chưa xoá. Rủi ro còn tới khi code đợt 5–7 được commit.
- Verify: kiem-chung QUA HẾT (JS 239, Py 1172, engine 33). Deploy 8c071e0c, app.js v20.
- CHƯA kiểm: đăng nhập thật bằng linh/thu.

## Ca 2026-11-18-c — Hôm nay dễ bắt đầu (P-32, P-32b)
- Phản ánh: "không nhấn được gì, không biết bắt đầu". Gốc: 2 việc phan_tich_uid kẹt viec_tay "Dữ liệu kho có thay đổi chưa đẩy" (kho đã sạch, 2 SP đã có bộ cảnh quay); Hôm nay không có ô dán link; chặng trông như nút.
- P-32 (culiapp-web): ô "Bắt đầu sản phẩm mới" + Cách làm 4 bước; việc tay không tốn tiền có nút Thử lại/Bỏ việc này tại chỗ; phan_tich_uid thừa → "Bỏ việc cũ"; chặng thành chữ "Bước k/4"; tên/ảnh SP là link.
- R-32: ĐẠT, P2-1 (lời thường hứa tự xong — sai), P2-2 (mất link khi 401) + P3-1..4 → P-32b sửa hết.
- so: data/** đổi = kho tự commit (người khác), không trả phiếu. kiem_san sạch.
- Verify: kiem-chung QUA HẾT (JS 229, Python 1172, engine 33). Xem local 8799 desktop + mobile (ô Bắt đầu, dòng SP).
- Deploy 7adeb1f9; sanpham.kutidak.com phục vụ loi v4, homnay v4, app v19.
- CHƯA kiểm: bấm Thử lại/Bỏ việc trên bản thật (cần đăng nhập người dùng).

## Ca 2026-11-18-b — Giao diện dễ dùng "Hôm nay" (đợt 7, /loop 'triển khai từng bước đến khi hoàn thành')
- Nguồn: biên bản hội đồng C:\Users\Mi\.claude\hop\VideoBatchLocal-20261118-0709\99-verdict.md (phương án lai). Phân loại: VỪA (thiết kế đã chốt ở hội đồng, bỏ architect). Chỉ làm Lượt 1 (bước 1–4); bước 5 (đề xuất/lý do cho câu hỏi AI, nút "Để AI tự chọn") NGOÀI PHẠM VI.
- Mốc ratchet: JS 191 pass; Python 1172 passed; sua_video_engine 33 passed.
- Git: main còn code đợt 5–6 chưa commit (bản commit ở nhánh local dot-5-6). Không commit lên main (kho.py tự push).
- Lượt 30 (W-7 culiapp-web): so: vi_pham_khong_ro data/index.json = người khác sửa (git pull của kho, HEAD 399487d "index" trong lúc agent chạy) — không trả phiếu. kiem_san sạch. JS 207 pass (191 cũ + 16 mới); test cũ sửa: viec-web linkLuuLaiSua 2 assert "#/"→"#/kho" (chấp nhận). Trưởng phòng tự sửa web/sua.js:340-341 link "Về kho" → #/kho (việc NHỎ). Chưa làm "video chờ chấm" trong Cần bạn (không có dữ liệu mà không gọi API từng SP) — chấp nhận.
- Trưởng phòng thử trên wrangler dev cục bộ bằng fetch giả (không đăng nhập thật): 3 khối + 4 chặng hiện đúng, XSS tên SP bị esc, điện thoại 375px không cuộn ngang. Thấy: SP chờ trả lời mà nút chính vẫn "Làm video" → gộp vào FX-30. (so review: cf/.wrangler/... = do trưởng phòng chạy wrangler dev, không phải reviewer.)
- R-30: ĐẠT (0 P0/P1). P2-1 đếm cắt ở 50 việc, P2-2 nút chính không tác dụng bước 4–5, P2-3 trang SP vẽ đè sau await; 6 P3. Vòng sửa 1: FX-30 (P2-1..3 + P3 nút duy nhất, câu hỏi tốn tiền không phiên sống, lỗi đã chạy lại). Treo: P3 overflow-x clip, .tagbtn 20px, nghi vấn A==B qua tu_tim.
- Lượt 31 FX-30: so sạch, kiem_san sạch, JS 213 pass. Trưởng phòng thử lại bằng fetch giả: 1 nút/SP đúng ưu tiên, "Xem và duyệt lại" khi phiên ngắt, lỗi đã chạy lại hiện xám.
- R-31: ĐẠT (0 P0/P1). P2 nghi vấn tải 500 việc đầy đủ — ĐO THẬT: runner hiện 8 việc = 13,9 KB (~1,7 KB/việc → ~870 KB khi đủ 500) → treo, đề xuất chế độ trả gọn ở runner. P3 treo: ưu tiên duyệt lại trước Trả lời trong cùng SP; gom "đã chạy lại" chỉ theo loại+uid; nhánh dem chết (runner chỉ trả dem khi tom_tat=1); nút chính trỏ nút đang khoá. Dừng vòng review (đạt, chỉ còn P2 nghi vấn/P3).
- Verify cuối (kiem-chung.py): JS 191 → thiếu homnay-web trong LENH → trưởng phòng thêm cf/test/homnay-web.test.mjs vào kiem-chung.py; chạy lại 5 file JS: 213 pass. Python 1171 passed + 1 failed test_runner_thuc_thi (cháu kế thừa stdout, nhạy thời gian khi máy bận) → chạy lại file đó 3 lần: 25/25 passed cả 3 (CHẬP CHỜN, không liên quan — đợt này không đụng tools/). sua_video_engine 33 passed.
- Mức kiểm chứng cả việc: unit + thử giao diện bằng dữ liệu giả trên wrangler dev cục bộ. CHƯA: deploy Worker; chưa thử với dữ liệu thật sau đăng nhập; chưa thử 15 phút trên điện thoại với người dùng.
- CHỜ DUYỆT: deploy Worker (web/ mới) lên kho-san-pham.kutidak.workers.dev / muse.kutidak.com.
- ĐÃ XỬ LÝ DUYỆT: deploy — đồng ý ("Deploy lên thật"). npx wrangler deploy → version 8cd8bf6c-b518-4326-a62b-2159bd4ebc11. Kiểm: kho-san-pham.kutidak.workers.dev phục vụ loi.js?v=2, homnay.js?v=2, viec.js?v=9, app.js?v=17; /api/viec chưa đăng nhập → 401. muse.kutidak.com đứng sau Cloudflare Access (302 về trang đăng nhập Access) — không kiểm được bằng curl. CHƯA kiểm giao diện thật sau đăng nhập.
- Người dùng: không dùng workers.dev nữa, dùng tên miền kutidak.com. Dò ra sanpham.kutidak.com là tên miền riêng của Worker này: phục vụ loi.js?v=2, homnay.js?v=2, viec.js?v=9, app.js?v=17; /api/viec chưa đăng nhập → 401. (muse.kutidak.com là app khác sau Cloudflare Access — ghi nhầm ở dòng trên.)

## Ca 2026-11-17-a — Bảng điều khiển (Bước 0 + 1a)
- Phân loại: VỪA (bỏ architect). Nhánh `bang-dieu-khien`. Biên bản hội đồng: C:\Users\Mi\.claude\hop\VideoBatchLocal-20261117-1504\99-verdict.md
- Mốc ratchet: worker.test.mjs 12 pass; pytest test_kho+test_vtk 18 pass.
- Quyết định: GIỮ luồng tải-rồi-xoá `file?xoa=1` (web/app.js:546 dùng); chỉ chuyển tiếp xoa khi `sec-fetch-site: same-origin` (khác biên bản "video_server bỏ xoá trên GET" — vì bỏ sẽ hỏng nút tải).
- Lượt 1 (song song): P-01 video_server (tools/video_server.py, tools/test_video_server.py) · P-02 Worker (cf/src/worker.js, cf/test/worker.test.mjs) · P-03 giao diện (web/app.js, web/style.css, web/index.html).
- Lượt 2 (sửa sau review R-01: P2-1 401 máy nhà, P2-2 tinhBuoc, P3-2/3/4/5/6/7): so sạch; kiem_san nuot-loi video_server.py:224 except OSError = CHẤP NHẬN (phiếu P-02b yêu cầu bỏ qua file vừa bị xoá). Worker 25 pass, pytest 35 pass.
- Review R-02: ĐẠT (0 P0/P1). Lượt 3 P-03c (app.js: khoá bấm đúp theo Set, chặn vẽ nhầm SP, gộp mục duyệt, gioSua an toàn): so sạch, node --check + 12 tình huống tinhBuoc qua. CHƯA review lại vòng 3.
- Đã bật video_server (Start-Process, PID 64304) — trước đó cổng 8787 không chạy. Deploy Worker version 6399c02c. Kiểm thật: video.kutidak.com/suc-khoe trả 4 app (muse tắt, perfectvoice/poster/video_server bật); /api/* chưa đăng nhập → 401.
- CHƯA kiểm: giao diện thật sau đăng nhập (cần người dùng đăng nhập); hành vi sec-fetch-site trên iPhone.
- Treo P3: video_server unquote 2 lần (tên file có %), iterdir thư mục bị xoá giữa chừng, nhánh dy stat không bắt lỗi; mục chỉ có góp ý không tính là đã duyệt; máy nhà tắt thì bước 7 không ra Hoàn tất.
- Ca 2026-11-17-b (đợt 3–5): architect A-01 viết docs/bo-chay-viec.md + DECISIONS.md (D1–D6 Đề xuất). PHÁT HIỆN: kho.py tự git pull/commit/push trong repo → đã chuyển repo về main (nhánh bang-dieu-khien chưa có commit, xoá); code đợt 1–2 vẫn là thay đổi chưa commit trên main. so thiết kế: vi phạm cf/.wrangler/... = do trưởng phòng chạy wrangler dev, không phải agent.
- Thiết kế ĐÃ CHỐT (AskUserQuestion 17/11: 'Duyệt, làm luôn'; hạn mức 'Giữ mức đề xuất'; người duyệt 'Cả nhan và comeofage'). Trưởng phòng tự đổi dòng Trạng thái D1–D8 (thao tác cơ học).
- CHỜ DUYỆT: W-0 — npm pack marked@12.0.2 dompurify@3.4.18 qrcode-generator@1.4.4 trong /tmp/w0-vendor, chép 3 file vào web/vendor/. Ghi chú: onclick nội tuyến app.js:459 → giao W-2 đổi sang addEventListener.
- Lượt 4 (đợt 3 L1: B-1,B-1b,B-1c,A-1,S-1,W-0,W-1,W-3): so sạch. kiem_san: noqa E402/type:ignore trong test = BÁO OAN (import qua sys.path); nuot-loi psutil.NoSuchProcess/Error khi giết cây, OSError probe cổng, BrokenPipe = hợp lệ; thuc_thi.py:742/748 except Exception → chuyển reviewer. ĐÃ XỬ LÝ DUYỆT: W-0 — đồng ý ('Cho tải'); S-1 — đồng ý ('Cho chạy').
- S-1 đã chạy (duyệt 'Cho chạy'): 7/7 lượt claude.exe exit 1 'Invalid API key · Fix external API key' (apiKeySource ANTHROPIC_API_KEY từ settings.json + ANTHROPIC_BASE_URL proxy). Mục 1 (tên trường init/result, session_id) ĐẠT; mục 3 --tools giới hạn công cụ lõi nhưng MCP (engram, boardroom) vẫn lọt → cần --strict-mcp-config; các mục khác không kết luận do lỗi khoá. Đã xoá thư mục phiên spike. CHẶN: runner cần claude headless đăng nhập được — chờ người dùng sửa xác thực CLI.
- R-04 lượt 4: ĐẠT (0 P0/P1; 1 P2 csp onclick → W-2; 9 P3 → phiếu lượt 2/F-1). Chữ ký Python↔JS khớp byte.
- Lượt 5 (đợt 3 L2: B-2, A-2, W-1b, W-2, F-1): so sạch; kiem_san: except Exception có log/ném lại ở vòng phục vụ, SaiTrangThai khi việc đã huỷ (B-2 ghi chú), noqa N802 do_GET = chấp nhận, chuyển reviewer xét. Toàn bộ: JS 59 pass +1 todo, Python 443 passed.
- R-05 lượt 5: CHƯA ĐẠT (P1 thiếu --strict-mcp-config; P2 lưới soát công cụ, che bí mật dữ liệu ra web, giet_cay bị bỏ kết quả). Vòng sửa 1: FX-1 backend, FX-2 automation, FX-3 web.
- Lượt 6 (sửa R-05: FX-1/2/3): so sạch; kiem_san bot-test test_claude_co_cong_cu_mcp_lot_thi_dung_ngay = CHẤP NHẬN (phiếu FX-2 mục 8 cho thay bằng test tham số 6 ca). JS 67 pass, Python 469 passed. Trưởng phòng tăng viec.js?v=2.
- R-06: ĐẠT (0 P0/P1; P2-1 log mất đuôi khi huỷ; 7 P3, P3-1 cắt trước khi che lộ một phần bí mật). Treo cho phiếu FX-4 cùng lượt 3.
- Lượt 7 FX-4 (P2-1 log đuôi, P3-1..7 che trước cắt, tool_use lạ, pem hỏng, không giết được, không Job Object): JS 67, Python 491 passed. CHƯA review lại.
- R-07 FX-4: ĐẠT (P2: PID tái dùng không Job Object, log cắt trước che, web mất đuôi log khi huỷ, nhả tài nguyên khi không giết được). Vòng sửa cuối FX-5/FX-6 rồi dừng review, chuyển sang kiểm live.
- Lượt 8 FX-5/FX-6: JS 69 pass, Python 507 passed. Dừng vòng review (đã 4 vòng, chỉ còn ca biên); kiểm tiếp bằng chạy thật. Treo: cờ khong_giet_duoc không tự gỡ; _con_song chỉ trong bộ nhớ; cong_cu_ngoai cắt 80/60 trước che.
- 17/11 tối: người dùng đăng nhập Claude (claude.ai, Max) qua cửa sổ trợ giúp. S-1 chạy lại: 11/11 mục đo ĐẠT (dontAsk ghi đè bypass, --tools, disallowed *, cost>0, max-budget, resume, env tối thiểu, Bash nền bị dừng khi -p thoát, stdin tiếng Việt). ~0,75 USD. Đã xoá thư mục phiên.
- PHÁT HIỆN: app Claude desktop là MSIX → ghi %LOCALAPPDATA% từ trong app bị chuyển vào Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local. Đã xoá bản cài kho-runner ở đó. Đổi thư mục runner sang E:\kho-runner (phiếu FX-7). KY_RIENG đã đưa lên Cloudflare (bước 1 xong).
- LƯỢT 3 TÍCH HỢP THẬT XONG (17/11 19:48): KY_RIENG + RUNNER_KEY lên Cloudflare; runner cài E:\kho-runner (bật bằng Start-Process, cổng 8788); video_server khởi động lại (có /r/*); deploy Worker 1d033b68; CSP có trên bản thật. Bấm 'Bản tin radar' trên web thật (tài khoản nhan) → việc j20261117194047be5f XONG sau 7m44s, 9 lượt Claude, ~1,67 USD ước tính; file E:\quet-kenh-anti\de-xuat\2026-11-17-de-xuat-san-pham.md; kiểm chéo 3/3 khớp. Lưu ý: ket_qua.file_ra rỗng (runner chưa ghi nhận file ra).
- Ca 2026-11-17-c (đợt 4–6, /loop 'làm tiếp đến khi hoàn thành'). Commit 278c7db đợt 1–3. Lượt 10: B-3 + S-2.
- Lượt 10: B-3 xong (590 passed), S-2 xong (NEEDS_APPROVAL → người dùng 'Cho chạy'). KHÔNG cài B-3 trước A-3.
- S-2 chạy thật (~0,20 USD): subagent (Agent) chạy được trong -p; init.tools có Task/TaskOutput/TaskStop; Bash nền CHẾT khi -p thoát (nen_xong.txt không xuất hiện), resume KHÔNG nhận thông báo nền; SendMessage KHÔNG có trong -p. → D4 (theo lượt + resume) KHÔNG đủ cho taovideo (skill dựa vào việc nền + thông báo). Hướng mới: 1 tiến trình claude sống suốt việc với --input-format stream-json, trả lời qua stdin. Cần spike S-3 xác nhận.
- Lượt 11 (đợt 4: A-3, W-4, P-4, W-5): so sạch. JS 96, Python 625. A-3 NEEDS_APPROVAL chạy poster_ds_folder.py thật (GET chỉ đọc). Hạn chế W-4: bộ đếm sai mật khẩu trên workers.dev không bền (cần KV).
- Người dùng chọn 'Sổ trên Cloudflare' cho P1-1 (R-11). Đã tạo KV SO_DUYET id 31283948f3834148ad49c7181c92f452, thêm binding vào cf/wrangler.toml. Hạn mức poster: chọn tổng cả ngày ≤5 video (người dùng 'ko hiểu' → trưởng phòng chọn mức an toàn).
- NGƯỜI DÙNG đổi hạn mức poster: 'nới tổng video/tài khoản là 100' → so_video_ngay 1–100/việc, tổng ≤100 video/tài khoản/ngày (gom theo folder nếu chưa có trường tài khoản), giữ ≤2 việc/ngày. Đã báo FX-11, FX-9, FX-12.
- Lượt 12 (D9: FX-9, FX-11, FX-12, A-D9): so sạch. Chấp nhận FX-11 #1 (genmax chưa ước tính → về uoc_tinh).
- Lượt 13 (FX-10, FX-13, A-D9b + trưởng phòng sửa tên trường test chéo tieu): so sạch; JS 125, Python 747. Chấp nhận FX-10 #1 (tiêu ngay trước sinh tiến trình).
- Lượt 14 (FX-14 api tra-loi/suc-khoe, FX-15 lý do duyệt lại): so sạch; Python 758, JS 125.
- R-15: KHÔNG ĐẠT — P1 base64 không chuẩn (16 biến thể chữ ký) lách sổ tiêu; P2 hạn mức theo tieu_luc_dau sai khi chạy lại khác ngày; P2 KV đọc lỗi vẫn cho thử mật khẩu. Vòng sửa FX-16/17/18.
- Lượt 16 (FX-16/17/18): so sạch; JS 128, Python 794. Treo P3: video poster chạy lại khác ngày chưa cộng vào hôm nay.
- ĐỢT 4 LÊN THẬT (17/11 ~22:00, người dùng 'Làm hết'): commit c7bf184; runner c7bf184 cài E:\kho-runner (sao lưu runner.db.bak-20261117-215720, schema 2, dot_bat 4); deploy Worker 43fa7231 (KV SO_DUYET). Thử thật: tạo muse_clip j20261117215853hx12 → cho_duyet; khung duyệt hiện đúng; Từ chối (qua API vì pane chặn confirm) → huy; không tiêu, KV rỗng, không chạy gì.
- S-3 chạy thật (~0,18 USD): chế độ 1 tiến trình claude -p --input-format stream-json sống suốt việc: n1 sống qua lượt ✓; n2 Bash nền chạy qua ranh giới lượt, xong ✓; n3 system/task_notification tới agent ✓; n4 agent TỰ THỨC (assistant+result mới lúc 78s không cần tin user) ✓; n5 SendMessage KHÔNG có (Agent/Task có) ✗; n6 CẦN_USER + trả lời qua stdin ✓; n7 đóng stdin thoát gọn 0,73s ✓; n8 total_cost_usd CỘNG DỒN trong phiên (runner phải lấy chênh lệch). init.tools: Task, Bash, TaskOutput, TaskStop. → Đợt 5 thiết kế lại theo D11: tiến trình sống.
- Trưởng phòng sửa video_server RE_R thêm xin-duyet-lai (59 test qua), khởi động lại video_server.
- Đợt 6: người dùng chốt (AskUserQuestion): chỉ dựng lại video đang sửa; code dựng trong bộ chạy việc (không sửa engine); lưu phụ đề cần mật khẩu mỗi lần. Kiến trúc sư A-05 đang thiết kế lại đợt 5 (D11).
- D10, D11 ĐÃ CHỐT (trưởng phòng đổi dòng Trạng thái theo câu trả lời người dùng). WM_CHO_PHEP = nha.cua.mit (quét dữ liệu: chỉ watermark này từng dùng).
- K-1/K-2: bản đề xuất ở .culiapp/de-xuat-K1-K2.md (patch áp thử OK, file thật chưa đụng). Chờ người dùng xem duyệt.
- Lượt 19 (B-7, A-6, W-9, S-4 viết, B-5, K-1/K-2 đề xuất): so sạch. K-1/K-2 ĐÃ GHI (người dùng 'Ghi hết'): sao lưu C:\Users\Mi\.claude\backups\truoc-K1-K2-20261118 (10 file), 6 agent + catalog, skill nguồn E:\claude + bản cài; test_tu_canh OK, test_scripts OK. S-4 đang chạy thật (duyệt 'Cho chạy').
- 18/11 00:29: B-4, W-6, R-20 dừng vì Claude hết hạn mức 5 giờ → cho chạy tiếp sau 00:20. R-20 (đợt 6): CHƯA ĐẠT — P1-1 chạy tiếp việc sửa lỗi hoàn nguyên lại đè bản sửa mới (ghi sổ bài học); P2-1 render_batch.json bị mẻ khác ghi giữa chừng; P2-2 kiem-chung thiếu test đợt 6 (trưởng phòng đã thêm sua-web, test_runner_sua_video, test_runner_theo_doi_phien, test_sua_video_engine bằng venv F:); P2-3 TOCTOU khoá; P3-1 chạy lại/tiếp việc sửa chữ không hỏi lại mật khẩu → trưởng phòng chốt theo D10 'mật khẩu mỗi lần': chặn chạy lại/chạy tiếp sua_video có ban_sua (giao sau B-4 vì đụng api.py); P3-2 hằng NGON_NGU_MAC_DINH; P3-3 ruff style. Giao FX-20 (automation, sua_video_engine.py + test) vào lượt 20.
- W-6 xong (DONE_WITH_CONCERNS, unit/fixture, 179 JS pass). Trưởng phòng tăng style.css?v=17. Chuyển cho B-4/A-5: runner nhận da_xac_nhan_mat_khau; lỗi tu_tim có chữ 'takes'/'dự án B'; WM khớp 3 nơi; so mã câu hỏi khi trả lời phiên sống.
- FX-20 xong (22+54 pass, fixture): hoan_nguyen đối chiếu trạng thái trước khi khôi phục, P2-1/P2-3/P3-2. Giao FX-21 (cùng file): luồng hoàn tác _khoi_phuc_nguon cũng đè .done.json không điều kiện.
- S-4 xong (~0,69 USD, 33 phút): (1) --tools nhận 'Agent' nhưng init.tools hiện 'Task'; Skill gọi được. (2) tool_use subagent có trên stdout (parent_tool_use_id); WebFetch ngoài --tools không gọi được. (3) subagent KHÔNG gọi được Agent lồng → fan-out C2 phải do agent chính (tiến trình) gọi. (4) tin gửi vào stdin giữa lượt (Bash đang chạy) KHÔNG chen vào lượt đó; nó chỉ được thấy ở lượt sau (lượt cuối nhắc CHEN-S4-55) → runner phải XẾP HÀNG câu trả lời, chỉ gửi stdin sau result. (5) --max-budget-usd CỘNG DỒN CẢ PHIÊN: chạm trần thì mọi lượt sau bị error_max_budget_usd ngay → đặt bằng trần phiên (60), runner tự tính chênh lệch. (6) im lặng 30 phút với stdin mở: tiến trình sống, nhớ ngữ cảnh. (7) total_cost_usd gồm cả subagent, cộng dồn. (8) có task_started/task_notification(completed). Đã xoá thư mục phiên spike (thư mục tạm script tự xoá).
- FX-21 xong (33+54 pass, fixture): hoàn tác xếp loại goc/minh/khac/mat từng mục, có bản mới hơn → mã 2 không đổi gì; phụ đề take bị đổi → video vẫn về, phụ đề giữ, mã 5. Trưởng phòng CHỐT giữ mã 5 (an toàn), giao architect cập nhật docs/sua-video.md §6.4 cùng lúc ghi kết luận S-4 vào docs/bo-chay-viec.md. Cần web/api hiện rõ 'kiểm tay' cho mã 5.
- B-4 xong (DONE_WITH_CONCERNS, fixture; kiem-chung QUA HẾT: JS 179, pytest 1049, engine 33). so lượt 20: vi_pham_khong_ro chỉ cf/.wrangler/tmp/* = do trưởng phòng chạy wrangler dev. kiem_san: bot-test test_taovideo_chua_mo, test_dot_bat_van_4_sua_video_khong_mo_taovideo = CHẤP NHẬN (dot_bat 5 làm test lỗi thời); test_lap_phieu_dot_5_co_cau_hoi đổi theo luật cau_hoi chỉ ở phiên sống = CHẤP NHẬN; noqa E402/type: ignore trong test = BÁO OAN. KHÔNG cài runner trước A-5. Douyin tự tạo việc → giao A-5 (vong_lap).
- Lượt 21: A-5 (automation: phien_song mới, vong_lap, chay_runner + test) ∥ FX-22 (backend: api.py, sua_video.py + test — chạy lại/tiếp sua_video có ban_sua cần lưu lại với mật khẩu; mã 5 'kiểm tay').
- A-DOC2 xong: sua-video.md §0/6.1–6.4/7.2a, bo-chay-viec.md §7.0a (S-4) + FX-24/25/26 (mã câu hỏi 'ma' qua web→Worker→runner, Đ5-L3) + K-3 (skill tao-video-tu-canh-quay: fan-out C2 phải do agent chính gọi — CẦN NGƯỜI DÙNG DUYỆT). Trưởng phòng xác nhận: chặn chạy lại chỉ khi người bấm; runner tự làm nốt sau khởi động lại không chặn. CHỜ DUYỆT: K-3 — sửa SKILL.md tao-video-tu-canh-quay (sẽ hỏi cùng bước tích hợp).
- FX-22 xong (272 pass, fixture): co_the_chay_lai, can_luu_lai_mat_khau, ket_qua.kiem_tay/do_dang/chua_doi_gi/thong_diep suy ra trong viec_ra (không lưu DB). Gộp vào Đ5-L3: FX-24 backend thêm co_the_chay_tiep=false khi kiem_tay; FX-26 automation ghi ket_qua bền trong vong_lap; FX-25 web dùng co_the_chay_lai, link màn sửa khi can_luu_lai_mat_khau, nhãn 'Cần kiểm tay' + thong_diep. Tài liệu §6.1/§7.2a lệch câu chữ → architect sửa sau.
- Lượt 21b (song song A-5, không trùng file): FX-24 backend (kieu, phieu, api + test: mã câu hỏi, khối CHẾ ĐỘ CHẠY, chặn chạy tiếp khi kiem_tay) ∥ FX-25 web (worker.js, viec.js, index.html + test: ma_cau_hoi, nút theo co_the_chay_lai/tiep, link lưu lại, nhãn Cần kiểm tay). Mốc so vẫn snap-luot-21.
- FX-25 xong (191 JS pass, fixture; viec.js?v=8). Đã nhắn FX-24 dùng fullmatch cho mã câu hỏi. Treo P3: class vj-kiem-tay chưa có CSS.
- FX-24 xong (407+392 pass, fixture). PHẢI ghép FX-24/25/26 cùng lúc (vong_lap.tra_loi_song còn 3 tham số, chưa sinh ma). Trưởng phòng chốt: chạy lại khi kiem_tay vẫn cho (tạo bản sửa mới); P3 sửa câu thong_diep 'Chạy lại/Chạy tiếp không giúp được' → chỉ 'Chạy tiếp'.
- A-5 xong (DONE_WITH_CONCERNS, fixture; 160 pass; kiem-chung QUA HẾT 1091+33+JS). so lượt 21 (A-5, FX-22, FX-24, FX-25, A-DOC2): chỉ cf/.wrangler/tmp/* (trưởng phòng). kiem_san: except Exception có log ở dọn phiên/ghi trạng thái (phien_song.py:334-341, vong_lap.py:1212/1314/2171), psutil.NoSuchProcess/Error trong test, noqa E402 trong test = CHẤP NHẬN/BÁO OAN. Đã thêm test_runner_phien_song.py vào kiem-chung.
- Lượt 22: FX-26 (automation, tiếp tục agent A-5): tra_loi_song 4 tham số, sinh ma câu hỏi, PhienSong.gui kèm ma, che_truong_ket_thuc chép ma, chay_runner in UTF-8.
- Trưởng phòng (việc NHỎ): sửa câu thong_diep kiem_tay sua_video.py:877 + test_runner_api.py:2122 thành 'Chạy tiếp không giúp được'; 285 pass.
- FX-26 xong (DONE; 381 pass; kiem-chung QUA HẾT 1126+33+JS; test đầu–cuối HTTP thật + Claude giả). so lượt 22 sạch; kiem_san chay_runner.py:117 except khi reconfigure stdout = CHẤP NHẬN. Bước 7: review toàn bộ đợt 5 + phần sửa đợt 6 (R-22).
- R-22 (đợt 5 + sửa đợt 6): ĐẠT để cài (0 P0/P1). P2-1 tin TIN_TRAN_CODEX bị bo_hang_doi huỷ; P2-2 xin duyệt lại lọt khi phiên đang đóng (mất loi/đối soát, pid cũ); P2-3 trần Codex lách qua Bash; P2-4 đối soát taovideo báo xong khi Bước B chưa làm (dòng kho không mốc thời gian); P3-1 phiếu/web in trần code; P3-2 mất cảnh báo lệch bản CLI. Quyết định: sửa hết P2 trước khi cài. Lượt 23: FX-27 automation (P2-1, P2-2, P3-2: phien_song, vong_lap) ∥ FX-28 backend (P2-3, P2-4, P3-1: danh_muc, stream_json, phieu). Đã xoá 2 thư mục tạm reviewer để lại.
- FX-27 xong (DONE; 383 pass, fixture): bo_hang_doi chỉ huỷ tin có mã; co_phien_song giữ tới khi chốt trạng thái cuối; cảnh báo bản CLI vào ket_qua.canh_bao. P3 treo: web chưa hiện ket_qua.canh_bao.
- FX-28 xong (486+343 pass, fixture): đếm Codex qua Bash (lenh_goi_codex), đối soát taovideo đòi mp4 mới Bước B + 0 partial + ảnh chụp kho (anh_chup_kho_taovideo), tran_taovideo hiệu lực. so lượt 23 sạch; kiem_san type: ignore trong test = BÁO OAN. Dữ liệu cũ có dòng B nhan=None/'Creator (autovideo)' nhưng skill autovideo-oneshot đã vá 17/11 luôn --nhan nha.cua.mit → chấp nhận.
- Lượt 24: FX-29 backend nhỏ: ghi ket_qua.kho_luc_tao lúc tạo việc taovideo (api.py), giữ qua xin duyệt lại; truyền hm=self.hm vào lap_phieu_tiep_taovideo (vong_lap.py:1971) và _buoc_taovideo (danh_muc). Architect cập nhật §7.8/§7.5/§7.9 theo đề xuất FX-28.
- A-DOC3 xong: §7.2–7.9 bo-chay-viec.md, §6.1/§7.2/§7.2a sua-video.md khớp code. Chạy lại việc kiem_tay tạo việc mới cùng tham số; engine sẽ chặn mã 2 nếu video đã đổi → an toàn, chấp nhận.
- FX-29 xong (api 216 pass; kiem-chung 1 trượt: test_15_hai_tin chập chờn — so time.time() chặt, bằng nhau trên Windows). Trưởng phòng (việc NHỎ) đổi test so theo thứ tự dòng nhật ký Claude giả; 5/5 qua. Ghi chú: test này chỉ chứng minh thứ tự, phần 'mỗi result một tin' do test_tin_gui_luc_dang_lam_chi_ghi_sau_ket_luot chứng minh. so lượt 24 sạch, kiem_san sạch.
- KIỂM CHỨNG CUỐI (lượt 24, 02:2x 18/11): JS 191 pass, pytest 1172 passed, engine 33 passed → QUA HẾT. Mức cả việc: fixture. CHƯA: claude.exe thật phiên sống, Worker/web thật đợt 5–6, sửa video thật. CHỜ DUYỆT: tích hợp (deploy Worker, cài runner, khởi động lại runner + video_server), K-3, commit.
- ĐÃ XỬ LÝ DUYỆT (AskUserQuestion 18/11 ~02:30): tích hợp — 'Cài + deploy luôn'; K-3 — 'Cho sửa'; commit — 'Commit' (không push, chỉ file dự án).
- TÍCH HỢP ĐỢT 5–6 (18/11 ~06:57): deploy Worker 8413f87f (KV SO_DUYET, web viec.js?v=8, style v17, sua.js v1); tắt runner pid 49628 → cai_runner (sao lưu runner.db.bak-20261118-065708; lần chạy đầu vỡ ở print cp1252 sau khi đã sao lưu — chạy lại với PYTHONIOENCODING=utf-8 OK) → bật runner pid 18536 (Start-Process với đường dẫn python đầy đủ; 'python' trần không lên) → /suc-khoe: dot_bat 5, chan_ton_tien false, phien_ban 8b1c17c-sua; video_server khởi động lại pid 57712; video.kutidak.com/suc-khoe 5 app (muse tắt). Không tạo việc tốn tiền.
- PHÁT HIỆN QUAN TRỌNG: kho.py day() làm git push mọi commit local của main → commit đợt 4 (c7bf184 → rebase thành e8857fd) ĐÃ LÊN origin/main công khai (comeofage/kho-san-pham). Không thấy bí mật trong file đã track (chỉ ky_cong_khai.pem + vector_ky.json khoá TEST). → TẠM HOÃN commit đợt 5–6, hỏi người dùng (commit trên main sẽ tự bị đẩy công khai).
- K-3 xong (skill sửa bản nguồn, test_tu_canh 101 OK, test_scripts 119 OK); trưởng phòng chép sang bản cài theo duyệt 'Cho sửa', sao lưu C:\Users\Mi\.claude\backups\truoc-K3-20261118, diff rỗng. Commit: người dùng chọn 'Nhánh riêng, không lên mạng' → worktree nhánh dot-5-6.
- COMMIT 273a30d trên nhánh LOCAL dot-5-6 (qua worktree tạm, đã gỡ); main vẫn 8b1c17c, code đợt 5–6 nằm chưa commit trên main như cũ (kho.py chỉ add data/ nên không đẩy code). Đã xoá snap-*.json.
- GIAO CA: Đợt 5–6 lên thật, mức kiểm chứng cả việc = fixture. CHƯA chạy thật: phiên taovideo với claude.exe + GenMax (cần người dùng ngồi máy, chọn sản phẩm, duyệt), sửa 1 video thật, bấm thử web trên điện thoại. Treo P3: vj-kiem-tay chưa CSS; web chưa hiện ket_qua.canh_bao; video poster chạy lại khác ngày; fixture WorkerGia/SoGia khoá chuỗi; lap_tin_chay_tiep cắt 500 ký tự; han_muc._gia_tri private dùng ở vong_lap; cai_runner.py print chết khi console cp1252; lách Codex bằng che giấu cố ý.
- WEB POSTER: trang Folders có ô tick từng Product ID (pv-folders.js?v=5, gửi product_id_active, huy hiệu đang/tổng) khớp app desktop Poster V2; cf/test/pv-folders-web.test.mjs thêm 1 test + cập nhật payload (34 pass). Còn 3 test trượt có từ trước, không liên quan: index.html loi/homnay, poster.css, thẻ folder thiếu '📄 captions'. CHƯA deploy Worker/web (wrangler deploy), chưa commit.
- WEB POSTER: ô tick Product ID hiện '· đã đăng N video' sau UID (backend GET /folders/ trả product_posted_counts; pv-folders.js?v=6), cả desktop lẫn web. Đã deploy Worker.
