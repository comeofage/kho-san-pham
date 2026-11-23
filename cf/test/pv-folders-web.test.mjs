// Test W-P4: trang Folders của Poster V2 trên web — web/pv-folders.js (port E:/tool/tiktok_poster_v2/src/desktop/pages/folders.py).
// Thiết kế: docs/poster-v2-tren-web.md §3 (202/_kq), §5.2–§5.3, §6.3–§6.5, §9 W-P4. Chạy: node --test cf/test/pv-folders-web.test.mjs
// Không mạng: globalThis.fetch bị thay bằng hàm ném lỗi TRƯỚC khi nạp mã; mã trang nhận fetch giả qua tham số (nạp NGUYÊN poster.js thật).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

globalThis.fetch = async (url) => { throw new Error(`fetch thật bị cấm trong test: ${url}`); };

const duong = (p) => new URL(`../../web/${p}`, import.meta.url);
const doc = (p) => readFileSync(duong(p), "utf8");
const APP = doc("app.js");
const POSTER = doc("poster.js");
const FO = doc("pv-folders.js");

const dong = (src, dau) => {
  const l = src.split("\n").find((x) => x.startsWith(dau));
  assert.ok(l, `không thấy dòng bắt đầu bằng "${dau}"`);
  return l;
};
const esc = new Function(`${dong(APP, "const esc = ")}\nreturn esc;`)();
const khoi = (src, ten) => {
  const m = src.match(new RegExp(`// --- ${ten} start ---\\n([\\s\\S]*?)// --- ${ten} end ---`));
  assert.ok(m, `thiếu marker ${ten}`);
  return m[1];
};
const BAN = `<img src=x onerror=alert(1)>`;
const CHO = "0123456789abcdef0123456789abcdef";
const NGAY_VN = Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Ho_Chi_Minh", day: "numeric" }).format(new Date()));

// ---------- khối thuần ----------
const T = new Function("esc", `"use strict";\n${khoi(FO, "pvfo-thuan")}
return { pvfoSAP_XEP, pvfoAI_XEM, pvfoInt, pvfoPy, pvfoChuanHoa, pvfoDenLuot, pvfoNhanLich, pvfoLuaChonLich, pvfoSapXep, pvfoTheMoi,
  pvfoMuonEp, pvfoTomTat, pvfoPayloadQueue, pvfoChuQueue, pvfoChuDang, pvfoMauSua, pvfoDuLieuSua, pvfoTheHtml, pvfoChipHtml,
  pvfoKhungHtml, pvfoHopSuaHtml, pvfoDuBaoHtml };`)(esc);

const F = (id, them = {}) => ({ id, name: `F${id}`, account_id: 1, account_name: "acc1", available_videos: 5, total_posted: 3,
  product_id_count: 2, caption_count: 4, product_name: "", caption: "", videos_per_day: 2, last_day_count: 1, today_count: 0,
  cadence_days: 1, cadence_phase: 1, is_archived: 0, created_at: `2026-01-0${id}`, yesterday_queued_count: 0, ...them });
const ACC = [{ id: 1, name: "acc1" }, { id: 2, name: "acc2" }];

test("cadence.py: normalize / is_due / label giống bản Python (bảng)", () => {
  const BANG_CHUAN = [[null, null, [1, 1]], [0, 0, [1, 1]], ["3", "2", [3, 2]], [2.7, 9, [2, 2]], ["x", "y", [1, 1]], [99, 40, [31, 31]],
    [-4, 1, [1, 1]], [5, -1, [5, 1]], [true, true, [1, 1]]];
  for (const [n, p, kq] of BANG_CHUAN) assert.deepEqual(T.pvfoChuanHoa(n, p), kq, `${n},${p}`);
  // is_due: (day - 1) % n == phase - 1; n=1 luôn đúng
  assert.equal(T.pvfoDenLuot(1, 1, 17), true);
  assert.equal(T.pvfoDenLuot(2, 1, 1), true);
  assert.equal(T.pvfoDenLuot(2, 1, 2), false);
  assert.equal(T.pvfoDenLuot(2, 2, 2), true);
  assert.equal(T.pvfoDenLuot(3, 3, 9), true);
  assert.equal(T.pvfoDenLuot(3, 1, 31), true, "31 và 1 tháng sau có thể liền nhau");
  assert.equal(T.pvfoDenLuot(3, 2, 31), false);
  // label
  assert.equal(T.pvfoNhanLich(1, 1), "Mỗi ngày");
  assert.equal(T.pvfoNhanLich(2, 1), "Ngày lẻ");
  assert.equal(T.pvfoNhanLich(2, 2), "Ngày chẵn");
  assert.equal(T.pvfoNhanLich(3, 1), "3 ngày: 1-4-7…");
  assert.equal(T.pvfoNhanLich(5, 4), "5 ngày: 4-9-14…");
  assert.equal(T.pvfoNhanLich(7, 3), "7 ngày: 3-10-17…");
});

test("combobox lịch: Mỗi ngày + (n, pha) n=2..5 + 'Tự cân tải: n ngày'; lịch lạ thêm cuối danh sách", () => {
  const { ds, chiSo } = T.pvfoLuaChonLich(1, 1);
  assert.equal(ds.length, 1 + 2 + 3 + 4 + 5 + 4);
  assert.deepEqual(ds.map((o) => o.chu), ["Mỗi ngày", "Ngày lẻ", "Ngày chẵn", "3 ngày: 1-4-7…", "3 ngày: 2-5-8…", "3 ngày: 3-6-9…",
    "4 ngày: 1-5-9…", "4 ngày: 2-6-10…", "4 ngày: 3-7-11…", "4 ngày: 4-8-12…", "5 ngày: 1-6-11…", "5 ngày: 2-7-12…", "5 ngày: 3-8-13…",
    "5 ngày: 4-9-14…", "5 ngày: 5-10-15…", "Tự cân tải: 2 ngày", "Tự cân tải: 3 ngày", "Tự cân tải: 4 ngày", "Tự cân tải: 5 ngày"]);
  assert.equal(chiSo, 0);
  assert.equal(T.pvfoLuaChonLich(3, 2).chiSo, 4);
  const la = T.pvfoLuaChonLich(7, 3);
  assert.equal(la.ds.length, 20);
  assert.equal(la.chiSo, 19);
  assert.equal(la.ds[19].chu, "7 ngày: 3-10-17…");
  assert.equal(la.ds[19].tu, false);
});

test("_sort_folders: 6 kiểu sắp xếp (khoá phụ tên / id) đúng như folders.py:879-895", () => {
  const ds = [F(1, { name: "b", created_at: "2026-01-02", total_posted: 5 }), F(2, { name: "A", created_at: "2026-01-02", total_posted: 5 }),
    F(3, { name: "c", created_at: "2026-01-01", total_posted: 9 }), F(4, { name: "a2", created_at: null, total_posted: null })];
  const ids = (k) => T.pvfoSapXep(ds, k).map((f) => f.id);
  assert.deepEqual(T.pvfoSAP_XEP, [["Mới tạo nhất", "created_desc"], ["Cũ nhất", "created_asc"], ["Tên A → Z", "name_asc"],
    ["Tên Z → A", "name_desc"], ["Đã đăng nhiều nhất", "posted_desc"], ["Đã đăng ít nhất", "posted_asc"]]);
  assert.deepEqual(ids("created_desc"), [2, 1, 3, 4]);
  assert.deepEqual(ids("created_asc"), [4, 3, 1, 2]);
  assert.deepEqual(ids("name_asc"), [2, 4, 1, 3]);
  assert.deepEqual(ids("name_desc"), [3, 1, 4, 2]);
  assert.deepEqual(ids("posted_desc"), [3, 2, 1, 4]);
  assert.deepEqual(ids("posted_asc"), [4, 2, 1, 3]);
  assert.deepEqual(ids("la"), [2, 1, 3, 4], "khoá lạ → Mới tạo nhất");
  assert.deepEqual(ds.map((f) => f.id), [1, 2, 3, 4], "không đổi mảng gốc");
});

test("_FolderCard: số Videos ban đầu theo lịch + hôm qua (folders.py:376-390)", () => {
  const ngay = 4; // n=2: pha 2 đến lượt, pha 1 nghỉ
  let c = T.pvfoTheMoi(F(1, { last_day_count: null, videos_per_day: 3 }), ngay);
  assert.equal(c.so, 3); assert.equal(c.homQua, null);
  c = T.pvfoTheMoi(F(1, { last_day_count: 0 }), ngay);
  assert.equal(c.so, 0, "hôm qua không đăng → 0"); assert.equal(c.homQua, 0);
  c = T.pvfoTheMoi(F(1, { last_day_count: 250 }), ngay);
  assert.equal(c.so, 100, "QSpinBox kẹp 0..100");
  c = T.pvfoTheMoi(F(1, { cadence_days: 2, cadence_phase: 2, videos_per_day: 4, last_day_count: 0 }), ngay);
  assert.equal(c.so, 4, "đến lượt → videos_per_day"); assert.equal(c.homQua, null, "đến lượt thì bỏ tooltip hôm qua");
  c = T.pvfoTheMoi(F(1, { cadence_days: 2, cadence_phase: 1, videos_per_day: 4, last_day_count: 2 }), ngay);
  assert.equal(c.so, 0, "nghỉ → 0"); assert.equal(c.homQua, 2);
  c = T.pvfoTheMoi(F(1, { cadence_days: 2, cadence_phase: 2, videos_per_day: 0 }), ngay);
  assert.equal(c.so, 1, "vpd or 1");
  assert.equal(c.chon, false); assert.equal(c.daSua, false);
});

test("wants_force_cadence + payload batch_schedule y folders.py:1120-1126", () => {
  const ngay = 4;
  const a = T.pvfoTheMoi(F(7, { cadence_days: 2, cadence_phase: 1 }), ngay); // nghỉ hôm nay
  const b = T.pvfoTheMoi(F(8), ngay);
  a.so = 2; a.daSua = true; b.so = 1;
  assert.equal(T.pvfoMuonEp(a, ngay), true);
  assert.equal(T.pvfoMuonEp(b, ngay), false);
  assert.deepEqual(T.pvfoPayloadQueue([a, b], 6, "Bạn bè", ngay), {
    folder_ids: [7, 8], video_counts: { 7: 2, 8: 1 }, force_folder_ids: [7], window_hours: 6, visibility: "friends" });
  assert.deepEqual(T.pvfoPayloadQueue([b], 4, "???", ngay).visibility, "everyone");
  a.daSua = false;
  assert.equal(T.pvfoMuonEp(a, ngay), false, "không tự gõ thì không ép");
  assert.deepEqual(T.pvfoAI_XEM, [["Mọi người", "everyone"], ["Bạn bè", "friends"], ["Riêng tư", "private"]]);
});

test("chữ kết quả Thêm vào Queue / Đăng ngay nguyên văn folders.py:1094-1146", () => {
  assert.equal(T.pvfoChuQueue({ total_queued: 5 }), "Đã xếp lịch 5 video vào hàng chờ Queue!");
  assert.equal(T.pvfoChuQueue({}), "Đã xếp lịch 0 video vào hàng chờ Queue!");
  assert.equal(T.pvfoChuQueue({ total_queued: 3, skipped_not_due: [{ folder_name: "b" }, { folder_name: "a" }, { folder_id: 9 }, { folder_name: "a" }],
    reduced_by_posted: [{ folder_name: "X", requested: 4, posted_today: 1, queued: 3 }, { folder_id: 2, requested: 2, posted_today: 2, queued: 0 }] }),
  "Đã xếp lịch 3 video vào hàng chờ Queue!\n\nBỏ 4 video vì slot rơi vào ngày folder nghỉ theo lịch:\n9, a, b"
    + "\n\nĐã trừ số video đã đăng/đã xếp cho hôm nay:\n- X: 4 - 1 có sẵn = xếp 3\n- 2: 2 - 2 có sẵn = xếp 0");
  assert.deepEqual(T.pvfoChuDang(3, []), { tieuDe: "Đang đăng", cau: "Đã bắt đầu tiến trình đăng 3 video.", kieu: "info" });
  assert.deepEqual(T.pvfoChuDang(1, ["Folder #2 (b): 500: x"]),
    { tieuDe: "Đang đăng", cau: "Đã bắt đầu tiến trình đăng 1 video.\nMột số lỗi xảy ra:\nFolder #2 (b): 500: x", kieu: "info" });
  assert.deepEqual(T.pvfoChuDang(0, ["e1", "e2"]), { tieuDe: "Lỗi đăng bài", cau: "e1\ne2", kieu: "critical" });
  assert.equal(T.pvfoTomTat([], false), "0 folder được chọn");
  const c = [T.pvfoTheMoi(F(1), 1), T.pvfoTheMoi(F(2), 1)];
  c[0].chon = true; c[0].so = 4;
  assert.equal(T.pvfoTomTat(c, true), "1 folder được chọn • 4 video");
});

test("_FolderEditDialog: giá trị ban đầu + get_data y folders.py:57-223", () => {
  const m = T.pvfoMauSua(null, ACC);
  assert.deepEqual(m, { name: "", source: "local", account_id: null, path: "", product_id: "", product_id_active: "", pid_tick: new Map(), pid_goc: new Set(), pid_dem: {}, product_name: "", caption_pool: "",
    videos_per_day: 1, post_times: '["08:00"]', campaign_hashtags: "", first_comment: "", visibility: "everyone", active: true });
  const s = T.pvfoMauSua(F(3, { source: "drive", account_id: 2, path: "E:\\v", product_id: "11,22", caption_pool: '["a","b"]',
    videos_per_day: 300, post_times: "", visibility: "private", active: 0, campaign_hashtags: null }), ACC);
  assert.equal(s.source, "drive"); assert.equal(s.account_id, 2); assert.equal(s.product_id, "11\n22");
  assert.equal(s.caption_pool, "a\nb"); assert.equal(s.videos_per_day, 100); assert.equal(s.post_times, '["08:00"]');
  assert.equal(s.visibility, "private"); assert.equal(s.active, false); assert.equal(s.campaign_hashtags, "");
  assert.equal(T.pvfoMauSua(F(3, { account_id: 99, source: "ftp", visibility: "x" }), ACC).account_id, null, "account lạ → Không chọn");
  assert.equal(T.pvfoMauSua(F(3, { source: "ftp" }), ACC).source, "local");
  assert.equal(T.pvfoMauSua(F(3, { caption_pool: "[hỏng" }), ACC).caption_pool, "[hỏng");
  assert.equal(T.pvfoMauSua(F(3, { caption_pool: "[1,2]" }), ACC).caption_pool, "[1,2]", "list không phải chuỗi: giữ nguyên (join lỗi)");
  assert.deepEqual(T.pvfoDuLieuSua({ ...m, name: "  Tên  ", path: " E:\\x ", product_id: " 1, 2\n\n3 ", caption_pool: "\n c \n",
    post_times: "  ", account_id: 2, active: false }), {
    name: "Tên", source: "local", path: "E:\\x", account_id: 2, product_id: "1\n2\n3", product_id_active: "1\n2\n3", product_name: "", caption_pool: "c",
    videos_per_day: 1, post_times: '["08:00"]', campaign_hashtags: "", first_comment: "", visibility: "everyone", active: false });
});

test("tick từng Product ID: mặc định tick hết (folder cũ), theo product_id_active, bấm tick ghi đè; chỉ ID tick vào product_id_active", () => {
  const cu = T.pvfoMauSua(F(3, { product_id: "11,22,33" }), ACC);
  assert.equal(T.pvfoDuLieuSua(cu).product_id_active, "11\n22\n33", "product_id_active rỗng = tick hết");
  const m = T.pvfoMauSua(F(3, { product_id: "11\n22\n33", product_id_active: "22" }), ACC);
  assert.equal(T.pvfoDuLieuSua(m).product_id_active, "22");
  assert.deepEqual([...T.pvfoHopSuaHtml(m, ACC).matchAll(/data-pvfo-pid="(\d+)"( checked)?/g)].map((x) => [x[1], !!x[2]]),
    [["11", false], ["22", true], ["33", false]]);
  m.pid_tick.set("11", true); m.pid_tick.set("22", false);
  assert.equal(T.pvfoDuLieuSua(m).product_id_active, "11");
  m.product_id = "11\n11\n44";
  assert.equal(T.pvfoDuLieuSua(m).product_id, "11\n11\n44");
  assert.equal(T.pvfoDuLieuSua(m).product_id_active, "11\n44", "trùng ID chỉ tính 1; ID gõ thêm mặc định tick");
  const dem = T.pvfoMauSua(F(3, { product_id: "11\n22", product_posted_counts: { 11: 5, 22: 0 } }), ACC);
  const hd = T.pvfoHopSuaHtml(dem, ACC);
  assert.ok(hd.includes("11 · đã đăng 5 video</label>") && hd.includes("22 · đã đăng 0 video</label>"), "số video đã đăng sau UID");
  assert.ok(T.pvfoHopSuaHtml(T.pvfoMauSua(F(3, { product_id: "11" }), ACC), ACC).includes("> 11</label>"), "không có số thì không hiện");
  const huyHieu = (f) => T.pvfoTheHtml(T.pvfoTheMoi(F(5, f), 1));
  assert.ok(huyHieu({ product_id_count: 3, product_id_active_count: 1 }).includes("🏷️ 1/3 products"));
  assert.ok(huyHieu({ product_id_count: 3, product_id_active_count: 3 }).includes("🏷️ 3 products"));
  assert.ok(huyHieu({ product_id_count: 2 }).includes("🏷️ 2 products"));
});

test("(a) chữ nguyên văn: khung trang, thẻ folder, hộp Thêm/Sửa (không Browse, có dòng gợi ý), Dự báo", () => {
  const k = T.pvfoKhungHtml({ tab: 0, sapXep: "created_desc", gio: 4, aiXem: "Mọi người", chonHet: false });
  for (const chu of ["📁 Folders &amp; Batch Scheduler", "Sắp xếp:", ">Mới tạo nhất<", ">Cũ nhất<", ">Tên A → Z<", ">Tên Z → A<",
    ">Đã đăng nhiều nhất<", ">Đã đăng ít nhất<", ">+ Add Folder<", ">📊 Dự báo lịch<", ">Refresh<", ">Hoạt động<", ">Lưu trữ<",
    ">0 folder được chọn<", ">Chọn hết tab<", ">↺ Giống hôm qua<", "Đăng trong vòng", "tiếng", "Ai xem:", ">Mọi người<", ">Bạn bè<",
    ">Riêng tư<", ">⚡ Đăng ngay<", ">➕ Thêm vào Queue<",
    `title="Chỉ tick các folder (đang hiện) hôm qua đã được đưa vào Queue, bỏ tick các folder khác."`,
    `title="Mỗi video cách nhau ngẫu nhiên 2-10 phút, đăng xong trong khung giờ này"`]) assert.ok(k.includes(chu), chu);
  assert.match(k, /id="pvfo-gio"[^>]*value="4"/);
  const c = T.pvfoTheMoi(F(5, { product_name: "Sản phẩm rất dài hơn hai mươi ký tự", last_day_count: 2, today_count: 1 }), 1);
  const h = T.pvfoTheHtml(c);
  for (const chu of [">F5<", "👤 acc1", "🎬 Còn 5 video", "✅ Đã đăng 3", `title="Tổng số video đã đăng từ folder này: 3"`, "🏷️ 2 products",
    "📄 4 captions", "📦 Sản phẩm rất dài hơn...", "📅 2/day", "🕘 Hôm qua: 2", `title="Số video đăng thành công hôm qua của folder này."`,
    "📆 Hôm nay: 1", `title="Số video đã đăng thành công hôm nay của folder này."`, "Videos:", `title="Số video đăng hôm qua: 2"`,
    `title="Chỉ đăng vào các ngày trong tháng theo chu kỳ này"`, ">Lưu trữ<", ">Edit<", ">Delete<"]) assert.ok(h.includes(chu), chu);
  assert.ok(T.pvfoTheHtml(T.pvfoTheMoi(F(5, { is_archived: 1 }), 1)).includes(">Khôi phục<"));
  assert.ok(T.pvfoTheHtml(T.pvfoTheMoi(F(5, { account_name: "", account_id: null }), 1)).includes("👤 Account #—"));
  assert.ok(!T.pvfoTheHtml(T.pvfoTheMoi(F(5), 1)).includes("📦"), "không preview thì không hiện");
  assert.ok(T.pvfoTheHtml(T.pvfoTheMoi(F(5, { name: undefined }), 1)).includes(">F5<") === false);
  const sua = T.pvfoHopSuaHtml(T.pvfoMauSua(null, ACC), ACC);
  for (const chu of ["Tên folder:", `placeholder="Tên folder (bắt buộc)"`, "Nguồn + Account:", ">local<", ">drive<", "Account:",
    ">— Không chọn —<", ">acc1 (ID: 1)<", ">acc2 (ID: 2)<", "Đường dẫn / Drive ID:", `placeholder="Đường dẫn thư mục hoặc Google Drive ID"`,
    ">🔌 Test<", "Gõ đường dẫn thư mục trên máy nhà, rồi bấm 🔌 Test", "TikTok Shop Product IDs:",
    `placeholder="Nhập các Product ID TikTok Shop (mỗi dòng 1 mã)"`, "Tick ID muốn đăng (bỏ tick để tạm ngưng, không xoá):", "Tên sản phẩm:",
    `placeholder="Tên sản phẩm hiển thị trên giỏ hàng (tùy chọn)"`, "Caption Pool:",
    `placeholder="Danh sách caption (mỗi dòng 1 caption hoặc phân cách bởi ---)"`, "Tần suất &amp; Giờ đăng:", "video/ngày", "Giờ đăng:",
    `placeholder="[&quot;08:00&quot;, &quot;12:00&quot;, &quot;20:00&quot;]"`, "Campaign Hashtags:", `placeholder="#campaign #affiliate"`,
    "First Comment:", "Quyền riêng tư:", ">everyone<", ">friends<", ">private<", "Folder đang hoạt động (Active)"]) assert.ok(sua.includes(chu), chu);
  assert.ok(!/Browse/.test(sua), "không có nút Browse (§5.3)");
  const db = T.pvfoDuBaoHtml({ dates: ["2026-11-18", "2026-11-19"], accounts: [{ account_name: "acc1", loads: [3, 0] }] });
  assert.ok(db.includes(">18/11<") && db.includes(">19/11<") && db.includes(">acc1<") && db.includes(">3<") && db.includes(">0<"));
});

test("(d) XSS: tên folder / account / preview / dự báo / tên account trong hộp sửa đều qua esc", () => {
  const c = T.pvfoTheMoi(F(1, { name: BAN, account_name: BAN, product_name: BAN, available_videos: BAN, id: 1 }), 1);
  const h = T.pvfoTheHtml(c);
  assert.ok(!h.includes("<img"), h);
  assert.ok(!T.pvfoChipHtml([F(1)], [{ id: 1, name: BAN }], null).includes("<img"));
  assert.ok(!T.pvfoHopSuaHtml(T.pvfoMauSua(F(1, { name: BAN, path: BAN, caption_pool: `</textarea>${BAN}` }), [{ id: 1, name: BAN }]),
    [{ id: 1, name: BAN }]).includes("<img"));
  assert.ok(!T.pvfoDuBaoHtml({ dates: [BAN], accounts: [{ account_name: BAN, loads: [BAN] }] }).includes("<img"));
});

// ---------- môi trường giả: nạp NGUYÊN poster.js + pv-folders.js ----------
const xa = async () => { for (let i = 0; i < 40; i++) await new Promise((r) => setImmediate(r)); };
function dongHoGia() {
  const c = { now: 1_000_000, hen: new Map(), id: 0 };
  c.setTimeout = (fn, ms) => { const id = ++c.id; c.hen.set(id, { at: c.now + (ms || 0), fn, lap: 0 }); return id; };
  c.setInterval = (fn, ms) => { const id = ++c.id; c.hen.set(id, { at: c.now + ms, fn, lap: ms }); return id; };
  c.clearTimeout = (id) => { c.hen.delete(id); };
  c.clearInterval = c.clearTimeout;
  c.tien = async (ms) => {
    const dich = c.now + ms;
    await xa();
    for (;;) {
      let best = null;
      for (const [id, h] of c.hen) if (h.at <= dich && (!best || h.at < best[1].at)) best = [id, h];
      if (!best) break;
      const [id, h] = best;
      c.now = h.at;
      if (h.lap) h.at += h.lap; else c.hen.delete(id);
      h.fn();
      await xa();
    }
    c.now = dich;
  };
  return c;
}
function elGia(ten = "") {
  return { ten, innerHTML: "", textContent: "", value: "", checked: false, disabled: false, className: "", id: "", dataset: {}, attrs: {},
    nghe: {}, con: new Map(), open: false, daXoa: false,
    addEventListener(ev, f) { (this.nghe[ev] ||= []).push(f); },
    querySelector(sel) { if (!this.con.has(sel)) this.con.set(sel, elGia(sel)); return this.con.get(sel); },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    showModal() { this.open = true; }, close() { this.open = false; }, remove() { this.daXoa = true; }, focus() {}, append() {} };
}
// Phần tử đích giả cho sự kiện: attrs (data-*, id) + closest(sel) theo chuỗi cha (hỗ trợ "[attr]" và tên thẻ, phân tách bằng dấu phẩy).
function muc(attrs = {}, them = {}) {
  const dataset = {};
  for (const [k, v] of Object.entries(attrs)) if (k.startsWith("data-")) dataset[k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = v;
  return { attrs, dataset, tag: them.tag || "div", cha: them.cha || null, value: them.value ?? "", checked: !!them.checked, name: them.name || "",
    id: attrs.id || "", disabled: false,
    closest(sel) {
      for (let x = this; x; x = x.cha) {
        for (const p of sel.split(",").map((s) => s.trim())) {
          const m = p.match(/^\[([\w-]+)\]$/);
          if (m ? Object.prototype.hasOwnProperty.call(x.attrs, m[1]) : p === x.tag) return x;
        }
      }
      return null;
    } };
}
const phat = async (el, ev, target) => { for (const f of el.nghe[ev] || []) f({ target, preventDefault() {} }); await xa(); };

function napFo(xuLy) {
  const S = { goi: [], hop: [], toasts: [], css: null };
  const clock = dongHoGia();
  const auth = { user: "nhan", ten: "nhan", get on() { return !!this.user; } };
  const app = elGia("#app");
  const $ = (s) => (s === "#app" ? app : null);
  const document = { hidden: false, body: { append(el) { S.hop.push(el); } }, head: { append(el) { S.css = el; } },
    getElementById: (id) => (S.css && S.css.id === id ? S.css : null), createElement: (t) => elGia(t) };
  const fetch = async (url, opt = {}) => {
    const rec = { url, method: opt.method || "GET", body: opt.body === undefined ? undefined : JSON.parse(opt.body) };
    S.goi.push(rec);
    const r = xuLy ? await xuLy(rec) : undefined;
    if (!r) throw new Error(`fetch thật bị cấm trong test: ${url}`);
    const txt = typeof r.body === "string" ? r.body : r.body === undefined ? "" : JSON.stringify(r.body);
    return { status: r.status, ok: r.status >= 200 && r.status < 300, text: async () => txt };
  };
  class DateGia extends Date { static now() { return clock.now; } }
  const ns = {
    esc, $, document, auth, fetch, globalThis: {}, mnCHUA_CO: "", renderUser() {}, openLogin() {}, toast: (m) => S.toasts.push(m),
    setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout, setInterval: clock.setInterval, clearInterval: clock.clearInterval, Date: DateGia,
  };
  const ten = Object.keys(ns);
  const P = new Function(...ten, `${POSTER}\n;\n${FO}
return { pvApi, pvDung, phien: () => pvPhien, pvFoVe };`)(...ten.map((k) => ns[k]));
  return { P, S, clock };
}
const ok = (body) => ({ status: 200, body });
const URL_TK = "/api/poster/api/v2/accounts/";
const URL_FO0 = "/api/poster/api/v2/folders/?archived=0";
const URL_FO1 = "/api/poster/api/v2/folders/?archived=1";
// Máy giả: bảng "METHOD url" → hàm/giá trị; mặc định accounts + folders.
function may(bang = {}, folders = [F(1), F(2, { account_id: 2, account_name: "acc2" }), F(3)]) {
  return async (rec) => {
    const k = `${rec.method} ${rec.url}`;
    if (k in bang) { const v = bang[k]; return typeof v === "function" ? v(rec) : v; }
    if (k === `GET ${URL_TK}`) return ok(ACC);
    if (k === `GET ${URL_FO0}` || k === `GET ${URL_FO1}`) return ok(folders);
    return undefined;
  };
}
async function moTrang(xuLy) {
  const m = napFo(xuLy);
  const khung = elGia("#pv-noi");
  const ve = m.P.pvFoVe(khung, m.P.phien());
  await xa();
  const q = (s) => khung.querySelector(s);
  const hopCuoi = () => m.S.hop[m.S.hop.length - 1];
  const bamHop = async (ma) => { await phat(hopCuoi(), "click", muc({ "data-pv-nut": ma })); };
  const bam = async (attrs, them) => phat(khung, "click", muc(attrs, them));
  const doi = async (attrs, them) => phat(khung, "change", muc(attrs, them));
  const go = async (attrs, them) => phat(khung, "input", muc(attrs, them));
  return { ...m, khung, ve, q, hopCuoi, bamHop, bam, doi, go, goiGhi: () => m.S.goi.filter((r) => r.method !== "GET") };
}
const theNut = (attr, id) => muc({ [attr]: String(id) }, { tag: "button", cha: muc({ "data-pvfo-the": String(id) }) });

// ---------- tên cấp đỉnh / CSP ----------
const tenDinh = (src) => [...src.matchAll(/^(?:async )?function\*? ?(\w+)|^(?:const|let|var|class) (\w+)/gm)].map((m) => m[1] || m[2]);
test("pv-folders.js: mọi tên cấp đỉnh bắt đầu 'pvfo' (P2-7); có pvFoVe; không sự kiện inline; không fetch trực tiếp; lớp CSS có tiền tố", () => {
  const ds = tenDinh(FO);
  assert.ok(ds.includes("pvFoVe"));
  for (const t of ds) assert.ok(t.toLowerCase().startsWith("pvfo"), t);
  assert.ok(!/\son[a-z]+=["']/.test(FO) && !/onclick\s*=/i.test(FO), "không gắn sự kiện inline (CSP)");
  assert.ok(!/\bfetch\(/.test(FO), "chỉ gọi qua pvApi");
  assert.ok(!/\bconfirm\(|\balert\(/.test(FO), "hộp thoại qua pvXacNhan / pvThongBao");
  const lop = [...FO.matchAll(/\.([a-z][\w-]*)\s*[{,:]/g)].map((m) => m[1]).filter((c) => /^[a-z]/.test(c));
  const css = FO.slice(FO.indexOf("const pvfoCSS"), FO.indexOf("`;", FO.indexOf("const pvfoCSS")));
  for (const c of [...css.matchAll(/\.([a-z][\w-]*)/g)].map((m) => m[1])) {
    assert.ok(c.startsWith("pvfo-") || ["btn", "chip", "on", "pv-hop", "ghost", "sm"].includes(c), `lớp CSS "${c}" thiếu tiền tố`);
  }
  assert.ok(!/class="[^"]*\bspin\b/.test(FO), "không dùng lớp 'spin' (va CSS toàn cục, bug bản Svelte)");
  assert.ok(lop.length > 0);
});

// ---------- tải trang ----------
test("tải: listAccounts rồi getFolders(archived=0) (y refresh_async); vẽ chip 'Tất cả (n)' / '<tên> (n)' + thẻ + tóm tắt", async () => {
  const t = await moTrang(may());
  await t.ve;
  assert.deepEqual(t.S.goi.map((r) => `${r.method} ${r.url}`), [`GET ${URL_TK}`, `GET ${URL_FO0}`]);
  const chip = t.q("#pvfo-chip").innerHTML;
  assert.ok(chip.includes(">Tất cả (3)<") && chip.includes(">acc1 (2)<") && chip.includes(">acc2 (1)<"), chip);
  const ds = t.q("#pvfo-ds").innerHTML;
  assert.deepEqual([...ds.matchAll(/data-pvfo-the="(\d+)"/g)].map((m) => m[1]), ["3", "2", "1"], "Mới tạo nhất trước");
  assert.equal(t.q("#pvfo-tom-tat").textContent, "0 folder được chọn • 0 video");
  assert.equal(t.q("#pvfo-tt").innerHTML, "", "hết trạng thái đang tải");
  assert.ok(t.S.css && t.S.css.id === "pvfo-css", "nạp CSS riêng một lần");
});

test("tải: danh sách rỗng → 'Không có folder nào trong danh sách này.'", async () => {
  const t = await moTrang(may({}, []));
  await t.ve;
  assert.match(t.q("#pvfo-ds").innerHTML, /📭[\s\S]*Không có folder nào trong danh sách này\./);
});

test("§3: getFolders trả 202 → hiện 'đang tải' rõ ràng; pvCho xong thì vẽ; bấm Refresh lúc đang chờ gọi lại bình thường (cùng URL)", async () => {
  let lanFo = 0;
  const t = await moTrang(may({
    [`GET ${URL_FO0}`]: () => { lanFo++; return { status: 202, body: { cho: CHO, toi_da_giay: 300, ...(lanFo > 1 ? { trung: true } : {}) } }; },
    [`GET /api/poster/_kq/${CHO}`]: () => (t.clock.now >= 1_006_000 ? ok({ xong: true, status: 200, body: [F(1), F(9)] }) : ok({ xong: false })),
  }));
  assert.match(t.q("#pvfo-tt").innerHTML, /Đang tải danh sách folder…[\s\S]*1–2 phút/);
  assert.equal(t.q("#pvfo-ds").innerHTML, "");
  await t.clock.tien(3000);
  assert.match(t.q("#pvfo-tt").innerHTML, /Đang tải/, "chưa xong vẫn hiện đang tải");
  await t.bam({ "data-pvfo-hd": "lam-moi" }, { tag: "button" });
  assert.equal(lanFo, 2, "Refresh gửi lại đúng GET folders (video_server tự gắn vào lần quét cũ)");
  assert.deepEqual(t.S.goi.filter((r) => r.url === URL_FO0).length, 2);
  await t.clock.tien(6000);
  await t.ve;
  assert.equal(t.q("#pvfo-tt").innerHTML, "");
  assert.deepEqual([...t.q("#pvfo-ds").innerHTML.matchAll(/data-pvfo-the="(\d+)"/g)].map((m) => m[1]).sort(), ["1", "9"]);
  assert.equal(t.S.hop.length, 0, "không hộp lỗi");
});

test("(e) đổi tab Hoạt động → Lưu trữ nhanh: kết quả cũ về muộn KHÔNG đè; gửi archived=1", async () => {
  let traCu;
  const t = await moTrang(may({
    [`GET ${URL_FO0}`]: () => new Promise((r) => { traCu = () => r(ok([F(1, { name: "CU" })])); }),
    [`GET ${URL_FO1}`]: ok([F(5, { name: "LUU", is_archived: 1 })]),
  }));
  await t.bam({ "data-pvfo-tab": "1" }, { tag: "button" });
  assert.ok(t.S.goi.some((r) => r.url === URL_FO1));
  assert.match(t.q("#pvfo-tabs").innerHTML, /data-pvfo-tab="1"[^>]*aria-selected="true"/);
  assert.match(t.q("#pvfo-ds").innerHTML, /LUU/);
  traCu();
  await xa();
  assert.match(t.q("#pvfo-ds").innerHTML, /LUU/);
  assert.ok(!/CU/.test(t.q("#pvfo-ds").innerHTML), "kết quả tab cũ bị bỏ");
  assert.match(t.q("#pvfo-ds").innerHTML, />Khôi phục</);
  const n = t.S.goi.length;
  await t.bam({ "data-pvfo-tab": "1" }, { tag: "button" });
  assert.equal(t.S.goi.length, n, "bấm lại đúng tab đang mở không tải lại (currentChanged)");
});

test("(e) rời trang (pvDung) lúc đang chờ 202 → không vẽ, không hộp lỗi roiTrang", async () => {
  const t = await moTrang(may({ [`GET ${URL_FO0}`]: { status: 202, body: { cho: CHO, toi_da_giay: 300 } }, [`GET /api/poster/_kq/${CHO}`]: ok({ xong: false }) }));
  t.P.pvDung();
  await t.clock.tien(9000);
  await t.ve;
  assert.equal(t.q("#pvfo-ds").innerHTML, "");
  assert.equal(t.S.hop.length, 0);
  assert.ok(!t.S.goi.some((r) => r.url.startsWith("/api/poster/_kq/")), "không hỏi _kq sau khi rời");
});

test("(c) lỗi tải: lỗi tạm (502) có gợi ý Refresh; lỗi vĩnh viễn (403) chỉ hiện chữ lỗi; chữ lỗi qua esc", async () => {
  let t = await moTrang(may({ [`GET ${URL_FO0}`]: { status: 502, body: { loi: `Poster V2 trên máy nhà chưa mở ${BAN}` } } }));
  await t.ve;
  let tt = t.q("#pvfo-tt").innerHTML;
  assert.match(tt, /502: Poster V2 trên máy nhà chưa mở/);
  assert.match(tt, /Bấm Refresh để thử lại/);
  assert.ok(!tt.includes("<img"));
  t = await moTrang(may({ [`GET ${URL_FO0}`]: { status: 403, body: { detail: "License invalid" } } }));
  await t.ve;
  tt = t.q("#pvfo-tt").innerHTML;
  assert.match(tt, /403: License invalid/);
  assert.ok(!/Bấm Refresh/.test(tt));
});

// ---------- lọc / chọn / sắp xếp ----------
test("chip account lọc thẻ; Chọn hết tab; card click chọn; ↺ Giống hôm qua (0 folder → hộp info nguyên văn)", async () => {
  const t = await moTrang(may({}, [F(1, { yesterday_queued_count: 2 }), F(2, { account_id: 2, account_name: "acc2" }), F(3)]));
  await t.ve;
  await t.bam({ "data-pvfo-chip": "1" }, { tag: "button" }); // account thứ 2 (id 2)
  assert.deepEqual([...t.q("#pvfo-ds").innerHTML.matchAll(/data-pvfo-the="(\d+)"/g)].map((m) => m[1]), ["2"]);
  assert.match(t.q("#pvfo-chip").innerHTML, /class="chip on"[^>]*>acc2 \(1\)</);
  await t.bam({ "data-pvfo-chip": "-1" }, { tag: "button" });
  assert.equal([...t.q("#pvfo-ds").innerHTML.matchAll(/data-pvfo-the=/g)].length, 3);
  await t.bam({ "data-pvfo-hd": "chon-het" }, { tag: "button" });
  assert.equal(t.q("#pvfo-tom-tat").textContent, "3 folder được chọn • 3 video");
  assert.equal(t.q('[data-pvfo-hd="chon-het"]').attrs["aria-pressed"], "true");
  await t.bam({ "data-pvfo-hd": "chon-het" }, { tag: "button" });
  assert.equal(t.q("#pvfo-tom-tat").textContent, "0 folder được chọn • 0 video");
  // bấm vùng trống của thẻ → chọn; bấm nút trong thẻ thì không
  await t.bam({ "data-pvfo-the": "3" });
  assert.equal(t.q("#pvfo-tom-tat").textContent, "1 folder được chọn • 1 video");
  await t.bam({}, { tag: "label", cha: muc({ "data-pvfo-the": "3" }) });
  assert.equal(t.q("#pvfo-tom-tat").textContent, "1 folder được chọn • 1 video", "bấm nhãn/ô trong thẻ không đổi chọn");
  await t.doi({ "data-pvfo-chon": "1" }, { tag: "input", checked: true });
  assert.equal(t.q("#pvfo-tom-tat").textContent, "2 folder được chọn • 2 video");
  assert.match(t.q("#pvfo-ds").innerHTML, /pvfo-the pvfo-the-chon" data-pvfo-the="1"/);
  // Giống hôm qua: chỉ folder 1 có yesterday_queued_count > 0
  await t.bam({ "data-pvfo-hd": "hom-qua" }, { tag: "button" });
  assert.equal(t.q("#pvfo-tom-tat").textContent, "1 folder được chọn • 1 video");
  assert.equal(t.S.hop.length, 0);
  // chỉ còn thẻ acc2 (không folder nào hôm qua có queue) → hộp info
  await t.bam({ "data-pvfo-chip": "1" }, { tag: "button" });
  await t.bam({ "data-pvfo-hd": "hom-qua" }, { tag: "button" });
  assert.match(t.hopCuoi().innerHTML, /Giống hôm qua[\s\S]*Hôm qua không có folder nào \(trong danh sách đang hiện\) được đưa vào Queue\./);
});

test("(f) lỗi gốc giữ nguyên: đổi Sắp xếp dựng lại thẻ (bỏ chọn) nhưng KHÔNG cập nhật tóm tắt; Refresh xong 'Chọn hết tab' vẫn bật dù thẻ bỏ chọn", async () => {
  const t = await moTrang(may());
  await t.ve;
  await t.bam({ "data-pvfo-hd": "chon-het" }, { tag: "button" });
  assert.equal(t.q("#pvfo-tom-tat").textContent, "3 folder được chọn • 3 video");
  await t.doi({ id: "pvfo-sap-xep" }, { tag: "select", value: "name_desc" });
  assert.deepEqual([...t.q("#pvfo-ds").innerHTML.matchAll(/data-pvfo-the="(\d+)"/g)].map((m) => m[1]), ["3", "2", "1"]);
  assert.ok(!/pvfo-the-chon/.test(t.q("#pvfo-ds").innerHTML), "thẻ dựng lại = bỏ chọn");
  assert.equal(t.q("#pvfo-tom-tat").textContent, "3 folder được chọn • 3 video", "tóm tắt cũ (folders.py:604 chỉ gọi _render_cards)");
  await t.bam({ "data-pvfo-hd": "lam-moi" }, { tag: "button" });
  assert.equal(t.q("#pvfo-tom-tat").textContent, "0 folder được chọn • 0 video");
  assert.equal(t.q('[data-pvfo-hd="chon-het"]').attrs["aria-pressed"], "true", "nút Chọn hết tab vẫn bật như desktop");
});

test("ô Videos: gõ số → tóm tắt đổi + đánh dấu người dùng sửa; kẹp 0..100; ô 'Đăng trong vòng' kẹp 1..48", async () => {
  const t = await moTrang(may());
  await t.ve;
  await t.doi({ "data-pvfo-chon": "1" }, { tag: "input", checked: true });
  await t.go({ "data-pvfo-so": "1" }, { tag: "input", value: "7" });
  assert.equal(t.q("#pvfo-tom-tat").textContent, "1 folder được chọn • 7 video");
  const o = muc({ "data-pvfo-so": "1" }, { tag: "input", value: "500" });
  await phat(t.khung, "change", o);
  assert.equal(o.value, "100");
  assert.equal(t.q("#pvfo-tom-tat").textContent, "1 folder được chọn • 100 video");
  const g = muc({ id: "pvfo-gio" }, { tag: "input", value: "99" });
  await phat(t.khung, "change", g);
  assert.equal(g.value, "48");
  const g0 = muc({ id: "pvfo-gio" }, { tag: "input", value: "0" });
  await phat(t.khung, "change", g0);
  assert.equal(g0.value, "1");
});

// ---------- lịch đăng (cadence) ----------
test("cadence: chọn lịch → updateFolder {cadence_days, cadence_phase}, ô Videos theo đến lượt; lỗi → trả combobox + hộp 'Lỗi lưu lịch đăng'", async () => {
  const phaDen = ((NGAY_VN - 1) % 2) + 1; // n=2: pha đến lượt hôm nay
  const phaNghi = phaDen === 1 ? 2 : 1;
  let loi = false;
  const t = await moTrang(may({ "PUT /api/poster/api/v2/folders/1": () => (loi ? { status: 500, body: { detail: `hỏng ${BAN}` } } : ok({ ok: true })) },
    [F(1, { videos_per_day: 3, last_day_count: 2 })]));
  await t.ve;
  await t.doi({ "data-pvfo-chon": "1" }, { tag: "input", checked: true });
  const idxNghi = 1 + (phaNghi - 1); // ["Mỗi ngày", "Ngày lẻ", "Ngày chẵn", …]
  await t.doi({ "data-pvfo-lich": "1" }, { tag: "select", value: String(idxNghi) });
  assert.deepEqual(t.goiGhi().map((r) => [r.method, r.url, r.body]), [["PUT", "/api/poster/api/v2/folders/1", { cadence_days: 2, cadence_phase: phaNghi }]]);
  assert.equal(t.q("#pvfo-tom-tat").textContent, "1 folder được chọn • 0 video", "ngày nghỉ → 0");
  const idxDen = 1 + (phaDen - 1);
  await t.doi({ "data-pvfo-lich": "1" }, { tag: "select", value: String(idxDen) });
  assert.equal(t.q("#pvfo-tom-tat").textContent, "1 folder được chọn • 3 video", "đến lượt → videos_per_day");
  assert.equal(t.S.goi.filter((r) => r.url === URL_FO0).length, 1, "không refresh sau khi lưu lịch");
  // người dùng đã gõ số → giữ nguyên số
  await t.go({ "data-pvfo-so": "1" }, { tag: "input", value: "5" });
  loi = true;
  await t.doi({ "data-pvfo-lich": "1" }, { tag: "select", value: "3" });
  assert.equal(t.q("#pvfo-tom-tat").textContent, "1 folder được chọn • 5 video");
  assert.match(t.hopCuoi().innerHTML, /Lỗi lưu lịch đăng[\s\S]*500: hỏng/);
  assert.ok(!t.hopCuoi().innerHTML.includes("<img"));
  assert.match(t.q("#pvfo-ds").innerHTML, new RegExp(`<option value="${idxDen}" selected>`), "combobox trả về lựa chọn trước");
});

test("cadence 'Tự cân tải: 3 ngày' → trả combobox, gọi suggest_phase?n=3, áp pha trả về (lưu updateFolder); lỗi → 'Lỗi chọn pha tự động'", async () => {
  let loi = false;
  const t = await moTrang(may({
    "GET /api/poster/api/v2/folders/1/suggest_phase?n=3": () => (loi ? { status: 404, body: { detail: "Folder not found" } } : ok({ cadence_days: 3, cadence_phase: 2 })),
    "PUT /api/poster/api/v2/folders/1": ok({}),
  }, [F(1)]));
  await t.ve;
  const sel = muc({ "data-pvfo-lich": "1" }, { tag: "select", value: "16" }); // Tự cân tải: 3 ngày
  await phat(t.khung, "change", sel);
  assert.equal(sel.value, "0", "quay về lựa chọn cũ trước khi hỏi backend");
  assert.ok(t.S.goi.some((r) => r.url === "/api/poster/api/v2/folders/1/suggest_phase?n=3"));
  assert.deepEqual(t.goiGhi().map((r) => r.body), [{ cadence_days: 3, cadence_phase: 2 }]);
  assert.match(t.q("#pvfo-ds").innerHTML, /<option value="4" selected>3 ngày: 2-5-8…/);
  loi = true;
  await phat(t.khung, "change", muc({ "data-pvfo-lich": "1" }, { tag: "select", value: "16" }));
  assert.match(t.hopCuoi().innerHTML, /Lỗi chọn pha tự động[\s\S]*404: Folder not found/);
  // pha đề xuất trùng pha hiện tại → không lưu lại (setCurrentIndex cùng chỉ số không phát tín hiệu)
  loi = false;
  const n = t.goiGhi().length;
  await phat(t.khung, "change", muc({ "data-pvfo-lich": "1" }, { tag: "select", value: "16" }));
  assert.equal(t.goiGhi().length, n);
});

// ---------- Lưu trữ / Khôi phục / Delete / Edit ----------
test("(b) Lưu trữ → PATCH {is_archived:1} rồi tải lại; Khôi phục → 0; lỗi → hộp 'Lỗi'", async () => {
  let loi = false;
  const t = await moTrang(may({ "PATCH /api/poster/api/v2/folders/2": () => (loi ? { status: 500, body: { detail: "x" } } : ok({})) }));
  await t.ve;
  await t.bam({ "data-pvfo-luu-tru": "2", "data-pvfo-ve": "1" }, { tag: "button" });
  assert.deepEqual(t.goiGhi().map((r) => [r.method, r.url, r.body]), [["PATCH", "/api/poster/api/v2/folders/2", { is_archived: 1 }]]);
  assert.equal(t.S.goi.filter((r) => r.url === URL_FO0).length, 2, "tải lại sau khi lưu trữ");
  await t.bam({ "data-pvfo-luu-tru": "2", "data-pvfo-ve": "0" }, { tag: "button" });
  assert.deepEqual(t.goiGhi()[1].body, { is_archived: 0 });
  loi = true;
  await t.bam({ "data-pvfo-luu-tru": "2", "data-pvfo-ve": "1" }, { tag: "button" });
  assert.match(t.hopCuoi().innerHTML, /<h3 class="pv-hop-tieu-de">Lỗi<\/h3>[\s\S]*500: x/);
});

test("(b) Delete: hộp xác nhận nguyên văn; Hủy → không gọi; Xóa → DELETE rồi tải lại; lỗi → 'Lỗi xóa folder'", async () => {
  let loi = false;
  const t = await moTrang(may({ "DELETE /api/poster/api/v2/folders/1": () => (loi ? { status: 500, body: { detail: "khoá" } } : ok({})) },
    [F(1, { name: `Tên ${BAN}` })]));
  await t.ve;
  await t.bam({ "data-pvfo-xoa": "1" }, { tag: "button" });
  const h = t.hopCuoi().innerHTML;
  assert.match(h, /Xác nhận/);
  assert.ok(h.includes("Xóa folder &#39;Tên &lt;img src=x onerror=alert(1)&gt;&#39;?\nCác video trong hàng đợi sẽ không bị xóa."), h);
  await t.bamHop("khong");
  assert.equal(t.goiGhi().length, 0, "Hủy không gọi");
  await t.bam({ "data-pvfo-xoa": "1" }, { tag: "button" });
  await t.bamHop("co");
  assert.deepEqual(t.goiGhi().map((r) => [r.method, r.url]), [["DELETE", "/api/poster/api/v2/folders/1"]]);
  assert.equal(t.S.goi.filter((r) => r.url === URL_FO0).length, 2);
  loi = true;
  await t.bam({ "data-pvfo-xoa": "1" }, { tag: "button" });
  await t.bamHop("co");
  assert.match(t.hopCuoi().innerHTML, /Lỗi xóa folder[\s\S]*500: khoá/);
});

test("(b) + Add Folder: hộp 'Thêm folder' → gõ ô → Lưu Folder → createFolder đúng payload → tải lại; Hủy → không gọi; lỗi 'Lỗi thêm folder'", async () => {
  let loi = false;
  const t = await moTrang(may({ "POST /api/poster/api/v2/folders/": () => (loi ? { status: 422, body: { detail: "name required" } } : ok({ id: 9 })) }));
  await t.ve;
  await t.bam({ "data-pvfo-hd": "them" }, { tag: "button" });
  let hop = t.hopCuoi();
  assert.match(hop.innerHTML, /<h3 class="pv-hop-tieu-de">Thêm folder<\/h3>/);
  assert.match(hop.innerHTML, />Lưu Folder</);
  assert.match(hop.innerHTML, />Hủy</);
  await t.bamHop("huy");
  assert.equal(t.goiGhi().length, 0);
  await t.bam({ "data-pvfo-hd": "them" }, { tag: "button" });
  hop = t.hopCuoi();
  await phat(hop, "input", muc({}, { name: "name", value: " Mới " }));
  await phat(hop, "change", muc({}, { name: "account", value: "1" }));
  await phat(hop, "input", muc({}, { name: "path", value: "E:\\vid" }));
  await phat(hop, "input", muc({}, { name: "product_id", value: "1,2" }));
  await phat(hop, "input", muc({}, { name: "videos_per_day", value: "3" }));
  await phat(hop, "change", muc({}, { name: "visibility", value: "friends" }));
  await phat(hop, "change", muc({}, { name: "active", checked: false }));
  await t.bamHop("luu");
  assert.deepEqual(t.goiGhi().map((r) => [r.method, r.url, r.body]), [["POST", "/api/poster/api/v2/folders/", {
    name: "Mới", source: "local", path: "E:\\vid", account_id: 2, product_id: "1\n2", product_id_active: "1\n2", product_name: "", caption_pool: "", videos_per_day: 3,
    post_times: '["08:00"]', campaign_hashtags: "", first_comment: "", visibility: "friends", active: false }]]);
  assert.equal(t.S.goi.filter((r) => r.url === URL_FO0).length, 2);
  loi = true;
  await t.bam({ "data-pvfo-hd": "them" }, { tag: "button" });
  await t.bamHop("luu");
  assert.match(t.hopCuoi().innerHTML, /Lỗi thêm folder[\s\S]*422: name required/);
});

test("(b) Edit: hộp 'Sửa folder' điền sẵn → updateFolder(id, get_data) → tải lại; lỗi 'Lỗi sửa folder'", async () => {
  const t = await moTrang(may({ "PUT /api/poster/api/v2/folders/2": { status: 400, body: { detail: "bad" } } },
    [F(2, { account_id: 2, path: "E:\\a", caption_pool: '["x","y"]' })]));
  await t.ve;
  await t.bam({ "data-pvfo-sua": "2" }, { tag: "button" });
  const hop = t.hopCuoi();
  assert.match(hop.innerHTML, /<h3 class="pv-hop-tieu-de">Sửa folder<\/h3>/);
  assert.match(hop.innerHTML, /value="E:\\a"/);
  assert.match(hop.innerHTML, /<option value="1" selected>acc2 \(ID: 2\)/);
  await t.bamHop("luu");
  const g = t.goiGhi()[0];
  assert.equal(g.method, "PUT");
  assert.equal(g.url, "/api/poster/api/v2/folders/2");
  assert.equal(g.body.caption_pool, "x\ny");
  assert.equal(g.body.account_id, 2);
  assert.match(t.hopCuoi().innerHTML, /Lỗi sửa folder[\s\S]*400: bad/);
});

test("🔌 Test: trống → cảnh báo; local → POST /_dem {duong_dan} + 2 hộp gốc; 400 B3 → hộp warning câu máy nhà; drive → driveTest / chưa lưu", async () => {
  const B3 = "Đường dẫn phải là thư mục/tệp trên ổ đĩa máy nhà (vd E:\\…), không nhận đường mạng";
  const dem = { "E:\\co": ok({ ton_tai: true, so_video: 7 }), "E:\\khong": ok({ ton_tai: false, so_video: 0 }), "\\\\h\\s": { status: 400, body: { loi: B3 } } };
  const t = await moTrang(may({
    "POST /api/poster/_dem": (rec) => dem[rec.body.duong_dan],
    "GET /api/poster/api/v2/folders/2/drive-test": ok({ video_count: 12 }),
  }, [F(2)]));
  await t.ve;
  await t.bam({ "data-pvfo-hd": "them" }, { tag: "button" });
  const hop = t.hopCuoi();
  const test1 = async () => { await phat(hop, "click", muc({ "data-pvfo-test": "" }, { tag: "button" })); };
  await test1();
  assert.match(t.hopCuoi().innerHTML, /pv-hop-warning[\s\S]*Vui lòng nhập đường dẫn trước khi test\./);
  assert.match(t.hopCuoi().innerHTML, /<h3 class="pv-hop-tieu-de">Lỗi<\/h3>/);
  await phat(hop, "input", muc({}, { name: "path", value: " E:\\co " }));
  await test1();
  assert.deepEqual(t.goiGhi().map((r) => [r.url, r.body]), [["/api/poster/_dem", { duong_dan: "E:\\co" }]]);
  assert.match(t.hopCuoi().innerHTML, /Thành công[\s\S]*Thư mục Local hợp lệ!\nTìm thấy 7 video\./);
  await phat(hop, "input", muc({}, { name: "path", value: "E:\\khong" }));
  await test1();
  assert.match(t.hopCuoi().innerHTML, /pv-hop-critical[\s\S]*Thư mục local không tồn tại\./);
  await phat(hop, "input", muc({}, { name: "path", value: "\\\\h\\s" }));
  await test1();
  assert.match(t.hopCuoi().innerHTML, /pv-hop-warning/);
  assert.ok(t.hopCuoi().innerHTML.includes("400: Đường dẫn phải là thư mục/tệp trên ổ đĩa máy nhà"));
  // drive, folder chưa lưu
  await phat(hop, "change", muc({}, { name: "source", value: "drive" }));
  await test1();
  assert.match(t.hopCuoi().innerHTML, /Google Drive[\s\S]*Vui lòng lưu folder trước để test kết nối Drive qua API\./);
  assert.ok(!t.S.goi.some((r) => /drive-test/.test(r.url)));
  // drive, folder đã có id
  await t.bam({ "data-pvfo-sua": "2" }, { tag: "button" });
  const hop2 = t.hopCuoi();
  await phat(hop2, "change", muc({}, { name: "source", value: "drive" }));
  await phat(hop2, "input", muc({}, { name: "path", value: "1AbC" }));
  await phat(hop2, "click", muc({ "data-pvfo-test": "" }, { tag: "button" }));
  assert.ok(t.S.goi.some((r) => r.url === "/api/poster/api/v2/folders/2/drive-test"));
  assert.match(t.hopCuoi().innerHTML, /Google Drive[\s\S]*Kết nối Drive thành công!\nSố video: 12/);
});

test("📊 Dự báo lịch → cadence_forecast?days=14; hộp bảng tiêu đề nguyên văn; lỗi → 'Lỗi dự báo lịch'", async () => {
  let loi = false;
  const t = await moTrang(may({ "GET /api/poster/api/v2/folders/cadence_forecast?days=14": () => (loi ? { status: 500, body: { detail: "x" } }
    : ok({ dates: ["2026-11-18", "2026-11-19"], accounts: [{ account_name: "acc1", loads: [2, 4] }] })) }));
  await t.ve;
  await t.bam({ "data-pvfo-hd": "du-bao" }, { tag: "button" });
  const h = t.hopCuoi().innerHTML;
  assert.match(h, /Dự báo số video mỗi ngày theo lịch \(folder đang bật\)/);
  assert.match(h, />18\/11<[\s\S]*>19\/11<[\s\S]*>acc1<[\s\S]*>2<[\s\S]*>4</);
  loi = true;
  await t.bam({ "data-pvfo-hd": "du-bao" }, { tag: "button" });
  assert.match(t.hopCuoi().innerHTML, /Lỗi dự báo lịch[\s\S]*500: x/);
});

// ---------- ⚡ Đăng ngay ----------
test("⚡ Đăng ngay: chưa chọn / tổng 0 → cảnh báo nguyên văn, không gọi", async () => {
  const t = await moTrang(may());
  await t.ve;
  await t.bam({ "data-pvfo-hd": "dang-ngay" }, { tag: "button" });
  assert.match(t.hopCuoi().innerHTML, /Cảnh báo[\s\S]*Vui lòng chọn ít nhất 1 folder để đăng ngay\./);
  await t.doi({ "data-pvfo-chon": "1" }, { tag: "input", checked: true });
  await t.go({ "data-pvfo-so": "1" }, { tag: "input", value: "0" });
  await t.bam({ "data-pvfo-hd": "dang-ngay" }, { tag: "button" });
  assert.match(t.hopCuoi().innerHTML, /Cảnh báo[\s\S]*Tất cả folder đã chọn đang để số video = 0\./);
  await t.bam({ "data-pvfo-hd": "queue" }, { tag: "button" });
  assert.match(t.hopCuoi().innerHTML, /Tất cả folder đã chọn đang để số video = 0\./);
  await t.doi({ "data-pvfo-chon": "1" }, { tag: "input", checked: false });
  await t.bam({ "data-pvfo-hd": "queue" }, { tag: "button" });
  assert.match(t.hopCuoi().innerHTML, /Vui lòng chọn ít nhất 1 folder để thêm vào Queue\./);
  assert.equal(t.goiGhi().length, 0);
});

test("⚡ Đăng ngay: khoá nút TRƯỚC await (cả lúc hộp xác nhận); bấm đúp không gửi 2 lần; Hủy → không gọi, mở khoá", async () => {
  const t = await moTrang(may({ "POST /api/poster/api/v2/folders/1/post_now": ok({ status: "started" }) }));
  await t.ve;
  await t.doi({ "data-pvfo-chon": "1" }, { tag: "input", checked: true });
  await t.bam({ "data-pvfo-hd": "dang-ngay" }, { tag: "button" });
  assert.equal(t.q('[data-pvfo-hd="dang-ngay"]').disabled, true, "khoá ngay khi hộp xác nhận mở");
  assert.equal(t.q('[data-pvfo-hd="queue"]').disabled, true);
  const soHop = t.S.hop.length;
  await t.bam({ "data-pvfo-hd": "dang-ngay" }, { tag: "button" });
  assert.equal(t.S.hop.length, soHop, "bấm lần 2 khi đang khoá: không mở hộp mới");
  assert.match(t.hopCuoi().innerHTML, /Bắt đầu đăng ngay video từ 1 folder đã chọn\?/);
  assert.match(t.hopCuoi().innerHTML, />Xác nhận</);
  await t.bamHop("khong");
  assert.equal(t.goiGhi().length, 0);
  assert.equal(t.q('[data-pvfo-hd="dang-ngay"]').disabled, false, "Hủy → mở khoá");
});

test("⚡ Đăng ngay: gọi postNow count lần/folder với visibility đã chọn; nút khoá suốt lúc gửi; xong → hộp 'Đang đăng' + tải lại", async () => {
  let t;
  const khoa = [];
  t = await moTrang(may({
    "POST /api/poster/api/v2/folders/1/post_now": () => { khoa.push(t.q('[data-pvfo-hd="dang-ngay"]').disabled); return ok({ status: "started" }); },
    "POST /api/poster/api/v2/folders/3/post_now": () => { khoa.push(t.q('[data-pvfo-hd="queue"]').disabled); return ok({ status: "started" }); },
  }));
  await t.ve;
  await t.doi({ "data-pvfo-chon": "1" }, { tag: "input", checked: true });
  await t.doi({ "data-pvfo-chon": "3" }, { tag: "input", checked: true });
  await t.go({ "data-pvfo-so": "1" }, { tag: "input", value: "2" });
  await t.doi({ id: "pvfo-ai-xem" }, { tag: "select", value: "Riêng tư" });
  await t.bam({ "data-pvfo-hd": "dang-ngay" }, { tag: "button" });
  assert.match(t.hopCuoi().innerHTML, /Bắt đầu đăng ngay video từ 2 folder đã chọn\?/);
  await t.bamHop("co");
  const ghi = t.goiGhi();
  assert.deepEqual(ghi.map((r) => r.url), ["/api/poster/api/v2/folders/3/post_now", "/api/poster/api/v2/folders/1/post_now",
    "/api/poster/api/v2/folders/1/post_now"], "theo thứ tự thẻ (Mới tạo nhất), mỗi folder count lần");
  for (const r of ghi) assert.deepEqual(r.body, { visibility: "private" });
  assert.deepEqual(khoa, [true, true, true]);
  assert.match(t.hopCuoi().innerHTML, /Đang đăng[\s\S]*Đã bắt đầu tiến trình đăng 3 video\./);
  assert.equal(t.q('[data-pvfo-hd="dang-ngay"]').disabled, false);
  assert.equal(t.S.goi.filter((r) => r.url === URL_FO0).length, 2, "tải lại");
});

test("⚡ Đăng ngay: lỗi 1 folder → dừng folder đó, folder khác vẫn chạy; tất cả lỗi → 'Lỗi đăng bài'; KHÔNG tự gửi lại", async () => {
  let t = await moTrang(may({
    "POST /api/poster/api/v2/folders/1/post_now": { status: 409, body: { detail: "Folder hết video" } },
    "POST /api/poster/api/v2/folders/3/post_now": ok({}),
  }));
  await t.ve;
  await t.doi({ "data-pvfo-chon": "1" }, { tag: "input", checked: true });
  await t.doi({ "data-pvfo-chon": "3" }, { tag: "input", checked: true });
  await t.go({ "data-pvfo-so": "1" }, { tag: "input", value: "3" });
  await t.bam({ "data-pvfo-hd": "dang-ngay" }, { tag: "button" });
  await t.bamHop("co");
  assert.equal(t.goiGhi().filter((r) => r.url.endsWith("/1/post_now")).length, 1, "lỗi → break, không gửi tiếp/không gửi lại");
  assert.match(t.hopCuoi().innerHTML, /Đang đăng[\s\S]*Đã bắt đầu tiến trình đăng 1 video\.\nMột số lỗi xảy ra:\nFolder #1 \(F1\): 409: Folder hết video/);
  t = await moTrang(may({ "POST /api/poster/api/v2/folders/1/post_now": { status: 502, body: { loi: "Poster V2 trên máy nhà chưa mở" } } }));
  await t.ve;
  await t.doi({ "data-pvfo-chon": "1" }, { tag: "input", checked: true });
  await t.bam({ "data-pvfo-hd": "dang-ngay" }, { tag: "button" });
  await t.bamHop("co");
  assert.equal(t.goiGhi().length, 1);
  assert.match(t.hopCuoi().innerHTML, /pv-hop-critical[\s\S]*Folder #1 \(F1\): 502: Poster V2 trên máy nhà chưa mở/);
  assert.match(t.hopCuoi().innerHTML, /Lỗi đăng bài/);
});

test("⚡ Đăng ngay: lệnh trả 202 rồi rời trang → không gửi tiếp (kể cả folder sau), không hộp kết quả (roiTrang)", async () => {
  const t = await moTrang(may({
    "POST /api/poster/api/v2/folders/3/post_now": { status: 202, body: { cho: CHO, toi_da_giay: 300 } },
    "POST /api/poster/api/v2/folders/1/post_now": ok({}),
    [`GET /api/poster/_kq/${CHO}`]: ok({ xong: false }),
  }));
  await t.ve;
  await t.doi({ "data-pvfo-chon": "3" }, { tag: "input", checked: true }); // thẻ 3 đứng trước thẻ 1 (Mới tạo nhất)
  await t.doi({ "data-pvfo-chon": "1" }, { tag: "input", checked: true });
  await t.go({ "data-pvfo-so": "3" }, { tag: "input", value: "3" });
  await t.bam({ "data-pvfo-hd": "dang-ngay" }, { tag: "button" });
  await t.bamHop("co");
  const soHop = t.S.hop.length;
  t.P.pvDung();
  await t.clock.tien(10_000);
  assert.equal(t.goiGhi().length, 1, "không gửi lần 2 khi chưa biết lần 1 ra sao");
  assert.equal(t.S.hop.filter((h) => !h.daXoa).length, 0);
  assert.equal(t.S.hop.length, soHop, "không mở hộp kết quả/lỗi");
});

// ---------- ➕ Thêm vào Queue ----------
test("➕ Thêm vào Queue: payload y folders.py; khoá TRƯỚC await, bấm đúp → 1 lệnh; hộp 'Thành công' + tải lại", async () => {
  let t; let tra;
  const khoa = [];
  t = await moTrang(may({ "POST /api/poster/api/v2/folders/batch_schedule": () => {
    khoa.push(t.q('[data-pvfo-hd="queue"]').disabled, t.q('[data-pvfo-hd="dang-ngay"]').disabled);
    return new Promise((r) => { tra = () => r(ok({ total_queued: 4, skipped_not_due: [], reduced_by_posted: [] })); });
  } }));
  await t.ve;
  await t.doi({ "data-pvfo-chon": "2" }, { tag: "input", checked: true });
  await t.doi({ "data-pvfo-chon": "1" }, { tag: "input", checked: true });
  await t.go({ "data-pvfo-so": "2" }, { tag: "input", value: "3" });
  await t.doi({ id: "pvfo-gio" }, { tag: "input", value: "6" });
  await t.doi({ id: "pvfo-ai-xem" }, { tag: "select", value: "Bạn bè" });
  await t.bam({ "data-pvfo-hd": "queue" }, { tag: "button" });
  await t.bam({ "data-pvfo-hd": "queue" }, { tag: "button" });
  assert.equal(t.goiGhi().length, 1, "bấm đúp chỉ gửi 1 lần");
  assert.deepEqual(khoa, [true, true]);
  assert.deepEqual(t.goiGhi()[0].body, { folder_ids: [2, 1], video_counts: { 2: 3, 1: 1 }, force_folder_ids: [], window_hours: 6, visibility: "friends" });
  tra();
  await xa();
  assert.match(t.hopCuoi().innerHTML, /Thành công[\s\S]*Đã xếp lịch 4 video vào hàng chờ Queue!/);
  assert.equal(t.q('[data-pvfo-hd="queue"]').disabled, false);
  assert.equal(t.S.goi.filter((r) => r.url === URL_FO0).length, 2);
});

test("➕ Thêm vào Queue: lỗi → hộp 'Lỗi' (câu 'CÓ THỂ đã chạy' giữ nguyên), không gửi lại, mở khoá", async () => {
  const CAU = "Poster V2 chưa trả lời sau 300 s. Thao tác CÓ THỂ đã chạy: xem Logs/Queue trước khi bấm lại.";
  const t = await moTrang(may({ "POST /api/poster/api/v2/folders/batch_schedule": { status: 504, body: { loi: CAU } } }));
  await t.ve;
  await t.doi({ "data-pvfo-chon": "1" }, { tag: "input", checked: true });
  await t.bam({ "data-pvfo-hd": "queue" }, { tag: "button" });
  assert.equal(t.goiGhi().length, 1);
  assert.match(t.hopCuoi().innerHTML, /<h3 class="pv-hop-tieu-de">Lỗi<\/h3>[\s\S]*pv-hop-critical/);
  assert.ok(t.hopCuoi().innerHTML.includes(`504: ${CAU}`));
  assert.equal(t.q('[data-pvfo-hd="queue"]').disabled, false);
  assert.equal(t.S.goi.filter((r) => r.url === URL_FO0).length, 1, "lỗi thì không tải lại (y desktop)");
});
