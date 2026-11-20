// Test W-P5: trang Calendar (web/pv-calendar.js) + Queue (web/pv-queue.js) của Poster V2 trên web.
// Thiết kế: docs/poster-v2-tren-web.md §3.3, §6.3–§6.5, §9 W-P5. Nguồn bê: E:/tool/tiktok_poster_v2/src/desktop/pages/{calendar,
// calendar_utils,queue}.py + widgets/common.py confirm_destructive. Chạy: node --test cf/test/pv-lich-queue-web.test.mjs
// Không mạng: globalThis.fetch bị thay bằng hàm ném lỗi TRƯỚC khi nạp mã; mã trang nhận fetch giả qua tham số (đi qua pvGoi THẬT).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

globalThis.fetch = async (url) => { throw new Error(`fetch thật bị cấm trong test: ${url}`); };

const duong = (p) => new URL(`../../web/${p}`, import.meta.url);
const doc = (p) => readFileSync(duong(p), "utf8");
const APP = doc("app.js");
const POSTER = doc("poster.js");
const CAL = doc("pv-calendar.js");
const QU = doc("pv-queue.js");

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
const CHO2 = "fedcba9876543210fedcba9876543210";

const xa = async () => { for (let i = 0; i < 40; i++) await new Promise((r) => setImmediate(r)); };

// Đồng hồ giả: setTimeout/setInterval/Date.now chỉ chạy khi gọi tien(ms).
function dongHoGia() {
  const c = { now: 1_000_000, hen: new Map(), id: 0 };
  c.setTimeout = (fn, ms) => { const id = ++c.id; c.hen.set(id, { at: c.now + (ms || 0), fn, lap: 0, ms }); return id; };
  c.setInterval = (fn, ms) => { const id = ++c.id; c.hen.set(id, { at: c.now + ms, fn, lap: ms, ms }); return id; };
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

const vang = (s) => String(s).replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const theGia = (extra = {}) => ({ innerHTML: "", textContent: "", dataset: {}, disabled: false, hidden: false, nghe: {},
  addEventListener(ev, f) { this.nghe[ev] = f; }, ...extra });
// <dialog> giả: querySelector('[name="x"]') trả ô nhập có value mặc định đọc từ HTML (test sửa .value để "gõ").
const hopGia = () => theGia({ open: false, daXoa: false, className: "", o: {},
  showModal() { this.open = true; }, close() { this.open = false; }, remove() { this.daXoa = true; },
  querySelector(sel) {
    const m = sel.match(/^\[name="(\w+)"\]$/);
    if (!m) return { focus() {} };
    if (!this.o[m[1]]) {
      const i = this.innerHTML.match(new RegExp(`name="${m[1]}"[^>]*value="([^"]*)"`));
      const t = this.innerHTML.match(new RegExp(`name="${m[1]}"[^>]*>([^<]*)</textarea>`));
      this.o[m[1]] = { value: vang(i ? i[1] : t ? t[1] : "") };
    }
    return this.o[m[1]];
  } });
const bamHop = (el, ma) => el.nghe.click({ target: { closest: () => ({ dataset: { pvNut: ma } }) } });
const tieuDeHop = (el) => vang((el.innerHTML.match(/<h3 class="pv-hop-tieu-de">([^]*?)<\/h3>/) || [])[1] || "");
const nutHop = (el) => [...el.innerHTML.matchAll(/data-pv-nut="(\w+)">([^<]*)</g)].map((m) => [m[1], vang(m[2])]);

// Bấm một nút trong khung trang (uỷ quyền sự kiện): tìm thẻ <button … attr="val" …> trong HTML, dựng dataset từ data-*.
function bam(khung, attr, val) {
  const the = khung.innerHTML.match(new RegExp(`<button[^>]*\\b${attr}="${val}"[^>]*>`));
  assert.ok(the, `không thấy nút ${attr}="${val}"`);
  const dataset = {};
  for (const [, k, v] of the[0].matchAll(/data-([\w-]+)="([^"]*)"/g)) dataset[k.replace(/-(\w)/g, (_, c) => c.toUpperCase())] = vang(v);
  const disabled = /\sdisabled[\s>]/.test(the[0]);
  khung.nghe.click({ target: { closest: () => ({ dataset, disabled }) } });
  return disabled;
}
const nutTag = (khung, attr, val) => (khung.innerHTML.match(new RegExp(`<button[^>]*\\b${attr}="${val}"[^>]*>[^<]*</button>`)) || [""])[0];
// Các dòng của bảng chính (tbody đầu tiên trong khung) → mảng ô đã bỏ thẻ + giải esc.
const dongBang = (html) => {
  const tb = (html.match(/<tbody>([^]*?)<\/tbody>/) || [])[1] || "";
  return [...tb.matchAll(/<tr>([^]*?)<\/tr>/g)].map((r) => [...r[1].matchAll(/<td[^>]*>([^]*?)<\/td>/g)].map((c) => c[1]));
};
// Kết quả _kq đã xong (bọc trong HTTP 200 để fetch giả không nhầm "status" của lệnh với mã HTTP).
const KQ = (status, body) => ({ status: 200, body: { xong: true, status, body } });
const hoan = () => { let xong; const p = new Promise((r) => { xong = r; }); return { p, xong }; };

// Nạp NGUYÊN web/poster.js + pv-calendar.js + pv-queue.js với môi trường giả.
// tuyen: { "GET /api/v2/…": body | (rec) => ({status, body}) | Promise }; thiếu tuyến → ném "fetch thật bị cấm".
function nap({ tuyen = {}, homNay = "2026-11-18T10:00:00" } = {}) {
  const S = { goi: [], toasts: [], hop: [] };
  const clock = dongHoGia();
  const auth = { user: "nhan", ten: "nhan", get on() { return !!this.user; } };
  const trang = {};
  const document = { hidden: false, body: { append(el) { S.hop.push(el); } }, createElement: () => hopGia() };
  class DateGia extends Date {
    constructor(...a) { super(...(a.length ? a : [homNay])); }
    static now() { return clock.now; }
  }
  const fetch = async (url, opt = {}) => {
    const method = opt.method || "GET";
    const rec = { url, method, body: opt.body, khoa: method + " " + url.replace(/^\/api\/poster/, "") };
    S.goi.push(rec);
    let h = Object.prototype.hasOwnProperty.call(tuyen, rec.khoa) ? tuyen[rec.khoa] : undefined;
    if (typeof h === "function") h = h(rec);
    h = await h;
    if (h === undefined) throw new Error(`fetch thật bị cấm trong test: ${url}`);
    const r = h && typeof h === "object" && "status" in h ? h : { status: 200, body: h };
    if (r.mang) throw new TypeError("Failed to fetch");
    const txt = typeof r.body === "string" ? r.body : r.body === undefined ? "" : JSON.stringify(r.body);
    return { status: r.status, ok: r.status >= 200 && r.status < 300, text: async () => txt };
  };
  const ns = {
    esc, $: () => null, document, auth, fetch, globalThis: trang, mnCHUA_CO: "",
    renderUser() {}, openLogin() {}, toast: (m) => S.toasts.push(m),
    setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout, setInterval: clock.setInterval, clearInterval: clock.clearInterval,
    Date: DateGia,
  };
  const ten = Object.keys(ns);
  const P = new Function(...ten, `${POSTER}\n;${CAL}\n;${QU}
return { pvApi, pvDung, pvHop, pvCaVe, pvCaDung, pvQuVe, pvQuDung, phien: () => pvPhien };`)(...ten.map((k) => ns[k]));
  trang.pvCaDung = P.pvCaDung;
  trang.pvQuDung = P.pvQuDung;
  const khung = theGia();
  return { P, S, clock, khung, tuyen };
}
const urls = (S) => S.goi.map((g) => g.khoa);

// =====================================================================================================================
// CALENDAR
// =====================================================================================================================
const CA = new Function("esc", `"use strict";\n${khoi(CAL, "pvca-thuan")}
return { pvcaTHANG, pvcaTHU, pvcaSuKienTheoNgay, pvcaTong, pvcaGio, pvcaTieuDe, pvcaTaiKhoan, pvcaChuO, pvcaTuan, pvcaIdKeHoach,
  pvcaDuLieuKeHoach, pvcaNgayMacDinh, pvcaLuoiHtml, pvcaChiTietHtml, pvcaTheHtml };`)(esc);

test("pvca-thuan: monthdayscalendar (tuần bắt đầu T2) khớp Python calendar.Calendar(0) — tháng nhuận, tháng bắt đầu CN", () => {
  // Kỳ vọng in từ Python thật: calendar.Calendar(firstweekday=0).monthdayscalendar(y, m).
  const PY = {
    "2024-2": [[0, 0, 0, 1, 2, 3, 4], [5, 6, 7, 8, 9, 10, 11], [12, 13, 14, 15, 16, 17, 18], [19, 20, 21, 22, 23, 24, 25], [26, 27, 28, 29, 0, 0, 0]],
    "2023-2": [[0, 0, 1, 2, 3, 4, 5], [6, 7, 8, 9, 10, 11, 12], [13, 14, 15, 16, 17, 18, 19], [20, 21, 22, 23, 24, 25, 26], [27, 28, 0, 0, 0, 0, 0]],
    "2015-2": [[0, 0, 0, 0, 0, 0, 1], [2, 3, 4, 5, 6, 7, 8], [9, 10, 11, 12, 13, 14, 15], [16, 17, 18, 19, 20, 21, 22], [23, 24, 25, 26, 27, 28, 0]],
    "2024-9": [[0, 0, 0, 0, 0, 0, 1], [2, 3, 4, 5, 6, 7, 8], [9, 10, 11, 12, 13, 14, 15], [16, 17, 18, 19, 20, 21, 22], [23, 24, 25, 26, 27, 28, 29], [30, 0, 0, 0, 0, 0, 0]],
    "2026-11": [[0, 0, 0, 0, 0, 0, 1], [2, 3, 4, 5, 6, 7, 8], [9, 10, 11, 12, 13, 14, 15], [16, 17, 18, 19, 20, 21, 22], [23, 24, 25, 26, 27, 28, 29], [30, 0, 0, 0, 0, 0, 0]],
    "2026-3": [[0, 0, 0, 0, 0, 0, 1], [2, 3, 4, 5, 6, 7, 8], [9, 10, 11, 12, 13, 14, 15], [16, 17, 18, 19, 20, 21, 22], [23, 24, 25, 26, 27, 28, 29], [30, 31, 0, 0, 0, 0, 0]],
  };
  for (const [k, v] of Object.entries(PY)) {
    const [y, m] = k.split("-").map(Number);
    assert.deepEqual(CA.pvcaTuan(y, m), v, k);
  }
  assert.deepEqual(CA.pvcaTHU, ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]);
  assert.equal(CA.pvcaTHANG[11], "Tháng 11");
  assert.equal(CA.pvcaNgayMacDinh(2024, 2, 29), "2024-02-29", "ngày 29 tháng nhuận hợp lệ");
  assert.equal(CA.pvcaNgayMacDinh(2023, 2, 29), "2023-02-01", "date() lỗi → giữ ngày 1 (except: pass)");
  assert.equal(CA.pvcaNgayMacDinh(2026, 11, null), "2026-11-01");
});

test("pvca-thuan: bảng calendar_utils khớp đầu ra Python thật (stat / giờ / tiêu đề / account / chữ ô / events_by_day)", () => {
  const evs = { "2026-11-01": [{ status: "done" }, { status: " DONE " }, { status: "failed" }, { status: "running" }, { status: null }, {}, "x", 5],
    "2026-11-02": "khong-phai-list", "2026-11-03": [{ status: 0 }, { status: "Failed" }] };
  assert.deepEqual(CA.pvcaTong(evs), { total: 8, done: 2, pending: 4, failed: 2 });
  const gio = [["2026-11-18 09:30:00", "09:30"], ["2026-11-18T21:05:59", "21:05"], ["2026-11-18", ""], ["", ""], [null, ""], [5, ""],
    ["aTb 12:34", "b 12:"], ["2026-11-18  09:30", " 09:3"], ["x y", "y"]];
  for (const [vao, ra] of gio) assert.equal(CA.pvcaGio(vao), ra, String(vao));
  const td = [[{ caption: "  Cap  " }, "Cap"], [{ caption: "   ", video_filename: "v.mp4" }, "v.mp4"], [{ caption: null, video_filename: "", folder_name: "F" }, "F"],
    [{ folder_id: 7 }, "Folder #7"], [{ folder_id: 0 }, "(không có tên)"], [{}, "(không có tên)"], ["x", ""], [{ caption: 5 }, "5"],
    [{ caption: [], folder_id: 3 }, "Folder #3"], [{ caption: true }, "True"]];
  for (const [vao, ra] of td) assert.equal(CA.pvcaTieuDe(vao), ra, JSON.stringify(vao));
  const tk = [[{ account_name: "acc" }, "acc"], [{}, ""], [{ account_name: null }, ""], ["x", ""], [{ account_name: 5 }, "5"]];
  for (const [vao, ra] of tk) assert.equal(CA.pvcaTaiKhoan(vao), ra, JSON.stringify(vao));
  const nhieu = [...Array(110).fill({ status: "done" }), ...Array(3).fill({ status: "pending" }), { status: "failed" }];
  assert.equal(CA.pvcaChuO(24, nhieu), "24\n🟢110 🟡3 🔴1");
  assert.equal(CA.pvcaChuO(5, []), "5");
  assert.equal(CA.pvcaChuO(5, null), "5");
  assert.equal(CA.pvcaChuO(6, [{ status: "failed" }]), "6\n🔴1");
  assert.deepEqual(CA.pvcaSuKienTheoNgay({ events_by_day: { a: [] } }), { a: [] });
  for (const x of [[], { events_by_day: [1] }, null, "x"]) assert.deepEqual(CA.pvcaSuKienTheoNgay(x), {});
  assert.deepEqual(CA.pvcaIdKeHoach([{ kind: "plan", plan_id: 7 }, { kind: "plan", plan_id: null }, { kind: "plan" }, { kind: "queue", queue_id: 1 }, "x"]), [7]);
  assert.deepEqual(CA.pvcaDuLieuKeHoach({ title: " A ", scheduled_date: " 2026-11-05 ", scheduled_time: "12:00", folder_id: "12", account_id: "", notes: " n " }),
    { title: "A", scheduled_date: "2026-11-05", scheduled_time: "12:00", folder_id: 12, account_id: null, notes: "n" });
  assert.deepEqual(CA.pvcaDuLieuKeHoach({ title: "", folder_id: "9999999", account_id: "-5" }),
    { title: "", scheduled_date: "", scheduled_time: "", folder_id: 999999, account_id: null, notes: "" }, "QSpinBox kẹp 0–999999");
});

const THANG11 = {
  year: 2026, month: 11,
  events_by_day: {
    "2026-11-01": [
      { id: "q_1", kind: "queue", queue_id: 1, status: "done", scheduled_at: "2026-11-01 09:30:00", account_name: "acc1", caption: "Cap 1" },
      { id: "p_7", kind: "plan", plan_id: 7, status: "planned", scheduled_at: "2026-11-01T12:00:00", account_name: null, folder_name: "F" },
    ],
    "2026-11-05": [{ id: "q_2", kind: "queue", queue_id: 2, status: "failed", scheduled_at: "2026-11-05 08:00:00", video_filename: BAN, account_name: BAN }],
  },
};
const T_THANG = (y, m) => `GET /api/v2/calendar/month?year=${y}&month=${m}`;

test("Calendar: mở trang → calendarMonth(năm, tháng) không account_id; chữ nguyên văn header / 4 thẻ / 2 khung / bảng; lưới T2–CN; hôm nay", async () => {
  const { P, S, khung } = nap({ tuyen: { [T_THANG(2026, 11)]: THANG11 } });
  await P.pvCaVe(khung, P.phien());
  await xa();
  assert.deepEqual(urls(S), [T_THANG(2026, 11)]);
  const h = khung.innerHTML;
  for (const chu of ["<h2>📅 Content Calendar</h2>", ">◀</button>", ">▶</button>", ">Hôm nay</button>", ">+ Thêm kế hoạch</button>", ">🔄</button>",
    "📊 TỔNG KẾ HOẠCH", "✔️ ĐÃ ĐĂNG", "⏳ CHỜ ĐĂNG", "❌ THẤT BẠI", "<h4>Lịch tháng</h4>", "<h4>Chi tiết ngày</h4>",
    "Bấm vào một ngày để xem chi tiết", "<th>Giờ</th><th>Account</th><th>Video/Folder</th><th>Trạng thái</th>", ">Tháng 11 2026<"]) {
    assert.ok(h.includes(chu), `thiếu "${chu}"`);
  }
  assert.deepEqual([...h.matchAll(/<div class="pvca-thu">([^<]+)<\/div>/g)].map((m) => m[1]), ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]);
  assert.deepEqual([...h.matchAll(/<div class="pvca-so">([^<]+)<\/div>/g)].map((m) => m[1]), ["3", "1", "1", "1"], "Tổng / Đã đăng / Chờ / Thất bại");
  // Tháng 11/2026 bắt đầu Chủ nhật → 6 ô đệm trước ngày 1.
  const o = [...h.matchAll(/<(?:div|button) [^>]*class="pvca-o([^"]*)"[^>]*>([^<]*)</g)];
  assert.equal(o.length, 42);
  assert.equal(o.slice(0, 6).every((m) => m[1].includes("pvca-dem")), true);
  assert.equal(o[6][2], "1\n🟢1 🟡1");
  assert.match(nutTag(khung, "data-pvca-ngay", "1"), /title="2 video"/);
  assert.equal(o[10][2], "5\n🔴1");
  assert.match(nutTag(khung, "data-pvca-ngay", "18"), /pvca-hom-nay/);
  assert.doesNotMatch(nutTag(khung, "data-pvca-ngay", "2"), /title=/, "ngày không có video: không tooltip");
  assert.ok(!h.includes('data-pvca="xoa"'), "chưa chọn ngày: ẩn nút xoá");
});

test("Calendar: ◀ / ▶ qua năm, Hôm nay; nhãn tháng đổi ngay; ngày đang chọn giữ nguyên khi đổi tháng (như desktop)", async () => {
  const t = {};
  for (const [y, m] of [[2026, 1], [2025, 12], [2026, 2], [2026, 12], [2027, 1]]) t[T_THANG(y, m)] = { events_by_day: {} };
  const { P, S, khung } = nap({ tuyen: t, homNay: "2026-01-15T10:00:00" });
  await P.pvCaVe(khung, P.phien());
  await xa();
  bam(khung, "data-pvca-ngay", "15");
  bam(khung, "data-pvca", "truoc");
  assert.match(khung.innerHTML, />Tháng 12 2025</);
  await xa();
  bam(khung, "data-pvca", "sau");
  await xa();
  bam(khung, "data-pvca", "sau");
  await xa();
  assert.match(khung.innerHTML, />Tháng 2 2026</);
  assert.match(khung.innerHTML, /Chi tiết ngày 2026-02-15/, "_selected_day không bị xoá khi đổi tháng");
  bam(khung, "data-pvca", "hom-nay");
  await xa();
  assert.deepEqual(urls(S), [T_THANG(2026, 1), T_THANG(2025, 12), T_THANG(2026, 1), T_THANG(2026, 2), T_THANG(2026, 1)]);
  bam(khung, "data-pvca", "lam-moi");
  await xa();
  assert.equal(urls(S).at(-1), T_THANG(2026, 1), "🔄 gọi lại đúng tháng");

  const b = nap({ tuyen: t, homNay: "2026-12-03T10:00:00" });
  await b.P.pvCaVe(b.khung, b.P.phien());
  bam(b.khung, "data-pvca", "sau");
  await xa();
  assert.deepEqual(urls(b.S), [T_THANG(2026, 12), T_THANG(2027, 1)]);
  assert.match(b.khung.innerHTML, />Tháng 1 2027</);
});

test("Calendar: bấm ngày → 'Chi tiết ngày …' + bảng 4 cột; nút 🗑️ chỉ hiện khi ngày có kế hoạch (plan); chuỗi API đã esc", async () => {
  const { P, khung } = nap({ tuyen: { [T_THANG(2026, 11)]: THANG11 } });
  await P.pvCaVe(khung, P.phien());
  await xa();
  bam(khung, "data-pvca-ngay", "1");
  assert.match(khung.innerHTML, /Chi tiết ngày 2026-11-01/);
  assert.deepEqual(dongBang(khung.innerHTML), [["09:30", "acc1", "Cap 1", "done"], ["12:00", "", "F", "planned"]]);
  assert.match(nutTag(khung, "data-pvca-ngay", "1"), /pvca-chon/);
  assert.match(khung.innerHTML, /data-pvca="xoa">🗑️ Xóa kế hoạch đã chọn<\/button>/);
  bam(khung, "data-pvca-ngay", "5");
  assert.ok(!khung.innerHTML.includes('data-pvca="xoa"'), "ngày chỉ có queue: ẩn nút xoá");
  assert.ok(!khung.innerHTML.includes(BAN), "XSS");
  assert.deepEqual(dongBang(khung.innerHTML), [["08:00", esc(BAN), esc(BAN), "failed"]]);
  bam(khung, "data-pvca-ngay", "2");
  assert.deepEqual(dongBang(khung.innerHTML), []);
});

test("Calendar: + Thêm kế hoạch — hộp _PlanDialog đủ ô; Hủy không gọi; thiếu tiêu đề → 'Thiếu thông tin'; Lưu → createCalendarPlan đúng payload, toast, tải lại", async () => {
  let tao = 0;
  const { P, S, khung } = nap({ tuyen: {
    [T_THANG(2026, 11)]: THANG11,
    "POST /api/v2/calendar/plans": () => { tao++; return { id: 9 }; },
  } });
  await P.pvCaVe(khung, P.phien());
  await xa();
  bam(khung, "data-pvca", "them");
  let h = S.hop.at(-1);
  assert.equal(tieuDeHop(h), "+ Thêm kế hoạch");
  for (const nhan of ["Tiêu đề:", "Ngày:", "Giờ:", "Folder ID:", "Account ID:", "Ghi chú:"]) assert.ok(h.innerHTML.includes(`>${nhan}</label>`), nhan);
  assert.deepEqual(nutHop(h), [["luu", "Lưu"], ["huy", "Hủy"]]);
  assert.equal(h.querySelector('[name="scheduled_date"]').value, "2026-11-01", "chưa chọn ngày → ngày 1");
  assert.equal(h.querySelector('[name="scheduled_time"]').value, "12:00");
  assert.equal(h.querySelector('[name="folder_id"]').value, "0");
  assert.match(h.innerHTML, /placeholder="YYYY-MM-DD"/);
  bamHop(h, "huy");
  await xa();
  assert.equal(tao, 0);

  bam(khung, "data-pvca-ngay", "5");
  bam(khung, "data-pvca", "them");
  h = S.hop.at(-1);
  assert.equal(h.querySelector('[name="scheduled_date"]').value, "2026-11-05", "ngày đang chọn");
  h.querySelector('[name="title"]').value = "   ";
  bamHop(h, "luu");
  await xa();
  assert.equal(tao, 0);
  const canh = S.hop.at(-1);
  assert.equal(tieuDeHop(canh), "Thiếu thông tin");
  assert.match(canh.innerHTML, /pv-hop-warning/);
  assert.ok(canh.innerHTML.includes("Tiêu đề là bắt buộc."));
  bamHop(canh, "ok");

  bam(khung, "data-pvca", "them");
  h = S.hop.at(-1);
  h.querySelector('[name="title"]').value = ` Bài ${BAN} `;
  h.querySelector('[name="folder_id"]').value = "12";
  h.querySelector('[name="account_id"]').value = "";
  h.querySelector('[name="notes"]').value = " ghi chú ";
  const truoc = S.goi.length;
  bamHop(h, "luu");
  await xa();
  const p = S.goi.find((g) => g.khoa === "POST /api/v2/calendar/plans");
  assert.deepEqual(JSON.parse(p.body), { title: `Bài ${BAN}`, scheduled_date: "2026-11-05", scheduled_time: "12:00", folder_id: 12, account_id: null, notes: "ghi chú" });
  assert.deepEqual(S.toasts, [`Đã thêm 'Bài ${BAN}'`], "toast dùng textContent (app.js) nên không cần esc");
  assert.deepEqual(urls(S).slice(truoc), ["POST /api/v2/calendar/plans", T_THANG(2026, 11)]);
});

test("Calendar: 🗑️ Xóa kế hoạch đã chọn — hộp question 'Xóa kế hoạch' Yes/No; No không gọi; Yes → DELETE từng plan_id rồi tải lại; bấm đúp chỉ 1 hộp", async () => {
  const hai = { events_by_day: { "2026-11-01": [{ kind: "plan", plan_id: 7 }, { kind: "plan", plan_id: 8 }, { kind: "queue", queue_id: 3 }] } };
  const { P, S, khung } = nap({ tuyen: { [T_THANG(2026, 11)]: hai, "DELETE /api/v2/calendar/plans/7": {}, "DELETE /api/v2/calendar/plans/8": {} } });
  await P.pvCaVe(khung, P.phien());
  await xa();
  bam(khung, "data-pvca-ngay", "1");
  bam(khung, "data-pvca", "xoa");
  bam(khung, "data-pvca", "xoa");
  assert.equal(S.hop.length, 1, "bấm đúp: 1 hộp");
  const h = S.hop[0];
  assert.equal(tieuDeHop(h), "Xóa kế hoạch");
  assert.ok(h.innerHTML.includes("Xóa 2 kế hoạch đang chọn?"));
  assert.deepEqual(nutHop(h), [["co", "Yes"], ["khong", "No"]]);
  bamHop(h, "khong");
  await xa();
  assert.ok(!urls(S).some((u) => u.startsWith("DELETE")));
  bam(khung, "data-pvca", "xoa");
  bamHop(S.hop.at(-1), "co");
  await xa();
  const sau = urls(S).slice(1);
  assert.deepEqual(sau.filter((u) => u.startsWith("DELETE")), ["DELETE /api/v2/calendar/plans/7", "DELETE /api/v2/calendar/plans/8"]);
  assert.equal(sau.filter((u) => u === T_THANG(2026, 11)).length, 2, "mỗi lần xoá xong refresh 1 lần");
});

test("Calendar: lỗi API → QMessageBox.critical 'Lỗi' với chữ lỗi gốc (tải tháng / thêm / xoá)", async () => {
  const { P, S, khung } = nap({ tuyen: {
    [T_THANG(2026, 11)]: { status: 500, body: { detail: `boom ${BAN}` } },
  } });
  await P.pvCaVe(khung, P.phien());
  await xa();
  const h = S.hop[0];
  assert.equal(tieuDeHop(h), "Lỗi");
  assert.match(h.innerHTML, /pv-hop-critical/);
  assert.ok(h.innerHTML.includes(esc(`HTTPError: 500: boom ${BAN}`)) && !h.innerHTML.includes(BAN));
  assert.match(khung.innerHTML, />Tháng 11 2026</, "khung vẫn vẽ");

  const b = nap({ tuyen: {
    [T_THANG(2026, 11)]: THANG11,
    "POST /api/v2/calendar/plans": { status: 422, body: { detail: [{ msg: "bad date" }] } },
    "DELETE /api/v2/calendar/plans/7": { status: 404, body: { detail: "Plan not found" } },
  } });
  await b.P.pvCaVe(b.khung, b.P.phien());
  await xa();
  bam(b.khung, "data-pvca", "them");
  b.S.hop.at(-1).querySelector('[name="title"]').value = "x";
  bamHop(b.S.hop.at(-1), "luu");
  await xa();
  assert.ok(b.S.hop.at(-1).innerHTML.includes(esc(`HTTPError: 422: [{"msg":"bad date"}]`)));
  assert.deepEqual(b.S.toasts, []);
  bam(b.khung, "data-pvca-ngay", "1");
  bam(b.khung, "data-pvca", "xoa");
  bamHop(b.S.hop.at(-1), "co");
  await xa();
  assert.equal(tieuDeHop(b.S.hop.at(-1)), "Lỗi");
  assert.ok(b.S.hop.at(-1).innerHTML.includes("API khong ton tai (404). Kiem tra backend co dang chay khong."));
});

test("Calendar: rời trang giữa chừng không vẽ đè / không hiện lỗi; bấm ◀▶ nhanh: kết quả cũ về muộn không đè tháng mới", async () => {
  const cho = hoan();
  const { P, S, khung } = nap({ tuyen: { [T_THANG(2026, 11)]: () => cho.p } });
  const ve = P.pvCaVe(khung, P.phien());
  await xa();
  const truoc = khung.innerHTML;
  P.pvDung();
  cho.xong({ status: 500, body: { detail: "x" } });
  await ve;
  await xa();
  assert.equal(khung.innerHTML, truoc);
  assert.equal(S.hop.length, 0, "không hiện lỗi của trang đã rời");

  // Hộp thêm đang mở khi rời trang → đóng, không gửi.
  const c = nap({ tuyen: { [T_THANG(2026, 11)]: THANG11 } });
  await c.P.pvCaVe(c.khung, c.P.phien());
  bam(c.khung, "data-pvca", "them");
  c.S.hop.at(-1).querySelector('[name="title"]').value = "x";
  c.P.pvDung();
  await xa();
  assert.ok(!urls(c.S).some((u) => u.startsWith("POST")));

  const cu = hoan(), moi = hoan();
  const d = nap({ tuyen: { [T_THANG(2026, 11)]: (r) => (d.S.goi.filter((g) => g.khoa === r.khoa).length === 1 ? THANG11 : moi.p),
    [T_THANG(2026, 10)]: () => cu.p } });
  await d.P.pvCaVe(d.khung, d.P.phien());
  bam(d.khung, "data-pvca", "truoc");
  bam(d.khung, "data-pvca", "sau");
  moi.xong({ events_by_day: { "2026-11-09": [{ status: "done" }] } });
  await xa();
  cu.xong({ events_by_day: { "2026-10-09": [{ status: "failed" }, { status: "failed" }] } });
  await xa();
  assert.match(d.khung.innerHTML, />Tháng 11 2026</);
  assert.deepEqual([...d.khung.innerHTML.matchAll(/<div class="pvca-so">([^<]+)<\/div>/g)].map((m) => m[1]), ["1", "1", "0", "0"]);
  assert.equal(d.S.hop.length, 0);
});

// =====================================================================================================================
// QUEUE
// =====================================================================================================================
const QQ = new Function("esc", `"use strict";\n${khoi(QU, "pvqu-thuan")}
return { pvquTAB, pvquCOT, pvquDem, pvquPhanTrang, pvquDong, pvquDongHtml, pvquKeHoach, pvquViecChay, pvquNhanTab, pvquMaxTrang };`)(esc);

const T_DS = (status, offset = 0) => `GET /api/v2/queue/?limit=100&offset=${offset}${status ? `&status=${status}` : ""}`;
const DEM = { pending: 12, running: 0, done: 6119, failed: 24 };
const DONG = [{ id: 5, video_filename: "v5.mp4", folder_name: "F", account_name: "acc", product_id: "1729", status: "pending", scheduled_at: "2026-11-18T09:30:00.5" },
  { id: 6, video_filename: "v6.mp4", folder_name: "F", account_name: "acc", status: "pending", scheduled_at: "2026-11-18 10:00:00" }];
// Tuyến mặc định của trang Queue (mở trang: _kq → status → list pending → settings).
const tuyenQ = (them = {}) => ({
  "GET /_kq": { dang_chay: [] },
  "GET /api/v2/queue/status": DEM,
  [T_DS("pending")]: DONG,
  "GET /api/v2/settings/": { autopost_enabled: "0", telegram_bot_token: "***" },
  ...them,
});
async function moQ(them = {}) {
  const x = nap({ tuyen: tuyenQ(them) });
  await x.P.pvQuVe(x.khung, x.P.phien());
  await xa();
  return x;
}

test("pvqu-thuan: dòng bảng như _populate_row (8 cột, cắt video 50, '#None', giờ, nhãn trạng thái); đếm tab; phân trang; get_data; dangChay", () => {
  const r = QQ.pvquDong({ id: 5, video_filename: "a".repeat(60), folder_name: null, folder_id: 3, account_name: "", account_id: null, product_id: "1729",
    status: "done", posted_at: "2026-11-18T09:30:00.123", scheduled_at: "x" });
  assert.deepEqual([r.id, r.video, r.folder, r.account, r.product, r.time, r.status, r.qid],
    ["5", "a".repeat(50), "#3", "#None", "1729", "2026-11-18 09:30:00", "✅ Đã đăng", 5]);
  const r2 = QQ.pvquDong({ id: "7", status: "running", created_at: "2026-11-17T08:00:00", video_path: "E:/v/b.mp4" });
  assert.deepEqual([r2.video, r2.folder, r2.account, r2.time, r2.status, r2.qid], ["E:/v/b.mp4", "#", "#", "2026-11-17 08:00:00", "⚡ Đang đăng", 7]);
  assert.equal(QQ.pvquDong({ status: "failed" }).status, "❌ Lỗi");
  assert.equal(QQ.pvquDong({ status: "weird" }).status, "⏳ Chờ đăng");
  assert.equal(QQ.pvquDong({ status: "pending", scheduled_at: "", created_at: "2026-01-02T03:04:05" }).time, "2026-01-02 03:04:05");
  assert.deepEqual(QQ.pvquCOT, ["ID", "Video", "Folder", "Tài khoản", "Sản phẩm", "Thời gian", "Trạng thái", "Thao tác"]);
  assert.deepEqual(QQ.pvquTAB, [["pending", "⏳ Chờ đăng"], ["failed", "❌ Lỗi"], ["done", "✅ Đã đăng"], ["running", "⚡ Đang chạy"], ["all", "📋 Tất cả"]]);
  assert.deepEqual(QQ.pvquDem(DEM), { pending: 12, running: 0, done: 6119, failed: 24, all: 6155 });
  assert.equal(QQ.pvquDem({}), null, "if not counts: return");
  assert.equal(QQ.pvquDem(null), null);
  assert.equal(QQ.pvquNhanTab("✅ Đã đăng", 6119, true), "✅ Đã đăng (6,119)");
  assert.equal(QQ.pvquNhanTab("✅ Đã đăng", 6119, false), "✅ Đã đăng");
  assert.deepEqual(QQ.pvquPhanTrang(1, 6119), { trang: 1, max: 62, chu: "Trang 1 / 62 (Tổng: 6,119 mục - 100/trang)", truoc: false, sau: true });
  assert.deepEqual(QQ.pvquPhanTrang(5, 0), { trang: 1, max: 1, chu: "Trang 1 / 1 (Tổng: 0 mục - 100/trang)", truoc: false, sau: false });
  assert.deepEqual(QQ.pvquKeHoach("5", '["08:00","12:00","20:00"]', "20"), { count: 5, post_times: ["08:00", "12:00", "20:00"], jitter_minutes: 20 });
  assert.deepEqual(QQ.pvquKeHoach("999", "{bad", "-3"), { count: 200, post_times: [], jitter_minutes: 0 });
  assert.deepEqual(QQ.pvquKeHoach("", '{"a":1}', "abc"), { count: 5, post_times: [], jitter_minutes: 20 });
  assert.deepEqual(QQ.pvquViecChay({ dang_chay: [
    { cho: CHO, method: "POST", path: "/api/v2/queue/7/run", lop: "L", toi_da_giay: 300, tom_tat: { queue_id: 7 } },
    { cho: CHO2, method: "POST", path: "/api/v2/queue/8/post?x=1", toi_da_giay: 300, tom_tat: {} },
    { cho: CHO, method: "POST", path: "/api/v2/post/direct", tom_tat: { folder_id: 1 } },
    { cho: CHO, method: "POST", path: "/api/v2/queue/9/retry" },
    { cho: CHO, method: "GET", path: "/api/v2/queue/10/post" },
  ] }), [{ qid: 7, cho: CHO, toi: 300 }, { qid: 8, cho: CHO2, toi: 300 }]);
  assert.deepEqual(QQ.pvquViecChay(null), []);
});

test("Queue: mở trang gọi dangChay TRƯỚC, rồi status + list(pending,100,0) + settings; chữ nguyên văn header/toolbar/5 tab/8 cột/phân trang", async () => {
  const cho = hoan();
  const x = nap({ tuyen: tuyenQ({ "GET /api/v2/queue/status": () => cho.p }) });
  const ve = x.P.pvQuVe(x.khung, x.P.phien());
  let h = x.khung.innerHTML;
  for (const chu of ["<h2>📋 Queue (Hàng đợi)</h2>", "<span>Auto post:</span>", ">TẮT</button>", ">🔄 Refresh</button>", ">📅 Lên lịch</button>",
    ">🔓 Gỡ kẹt</button>", ">🔀 Random</button>", ">🗑️ Xóa hết chờ</button>", ">🧹 Reset toàn bộ</button>",
    ">◀ Trang trước</button>", ">Trang 1 / 1 (Tổng: 0 mục)</span>", ">Trang sau ▶</button>"]) {
    assert.ok(h.includes(chu), `thiếu "${chu}"`);
  }
  assert.deepEqual([...h.matchAll(/data-pvqu-tab="\w+">([^<]+)</g)].map((m) => m[1]), ["⏳ Chờ đăng", "❌ Lỗi", "✅ Đã đăng", "⚡ Đang chạy", "📋 Tất cả"]);
  assert.deepEqual([...h.matchAll(/<th>([^<]+)<\/th>/g)].map((m) => m[1]), ["ID", "Video", "Folder", "Tài khoản", "Sản phẩm", "Thời gian", "Trạng thái", "Thao tác"]);
  await ve;
  await xa();
  assert.deepEqual(urls(x.S), ["GET /_kq", "GET /api/v2/queue/status", T_DS("pending"), "GET /api/v2/settings/"]);
  assert.match(x.khung.innerHTML, /Trang 1 \/ 1 \(Tổng: 0 mục - 100\/trang\)/, "list về trước counts");
  cho.xong(DEM);
  await xa();
  h = x.khung.innerHTML;
  assert.deepEqual([...h.matchAll(/data-pvqu-tab="\w+">([^<]+)</g)].map((m) => m[1]),
    ["⏳ Chờ đăng (12)", "❌ Lỗi (24)", "✅ Đã đăng (6,119)", "⚡ Đang chạy (0)", "📋 Tất cả (6,155)"]);
  assert.match(h, />Trang 1 \/ 1 \(Tổng: 12 mục - 100\/trang\)</);
  assert.match(h, /data-pvqu-tab="pending" [^>]*|aria-selected="true" data-pvqu-tab="pending"/);
  assert.deepEqual(dongBang(h).map((r) => r.slice(0, 7)), [["5", "v5.mp4", "F", "acc", "1729", "2026-11-18 09:30:00", "⏳ Chờ đăng"],
    ["6", "v6.mp4", "F", "acc", "", "2026-11-18 10:00:00", "⏳ Chờ đăng"]]);
  assert.match(h, /data-pvqu-chay="5" title="Chạy ngay" aria-label="Chạy ngay">▶</);
  assert.match(h, /data-pvqu-thu="5" title="Retry" aria-label="Retry">↻</);
  assert.match(h, /data-pvqu-xoa="5" title="Xóa" aria-label="Xóa">✕</);
  assert.ok(!h.includes("***"), "không hiện settings khác");
});

test("Queue: Auto post — đọc autopost_enabled; bấm khoá nút TRƯỚC await, bấm đúp chỉ 1 lệnh; BẬT/TẮT + toast; lỗi → trả lại + 'Lỗi'; lỗi tạm → đọc lại settings", async () => {
  const on = hoan();
  let khoaKhiGui = null;
  const x = await moQ({
    "GET /api/v2/settings/": { autopost_enabled: "1" },
    "POST /api/v2/settings/autopost-off": () => { khoaKhiGui = /data-pvqu="auto"[^>]*disabled/.test(x.khung.innerHTML); return on.p; },
    "POST /api/v2/settings/autopost-on": { status: 500, body: { detail: "db locked" } },
  });
  assert.match(nutTag(x.khung, "data-pvqu", "auto"), /aria-pressed="true"[^>]*>BẬT</);
  bam(x.khung, "data-pvqu", "auto");
  assert.equal(bam(x.khung, "data-pvqu", "auto"), true, "lần 2: nút đã khoá");
  await xa();
  assert.equal(khoaKhiGui, true, "khoá TRƯỚC khi gửi");
  assert.equal(urls(x.S).filter((u) => u.includes("autopost")).length, 1);
  on.xong({ ok: true });
  await xa();
  assert.match(nutTag(x.khung, "data-pvqu", "auto"), /aria-pressed="false">TẮT</);
  assert.deepEqual(x.S.toasts, ["Auto post đã TẮT"]);
  assert.equal(x.S.goi.find((g) => g.khoa === "POST /api/v2/settings/autopost-off").body, "{}");

  bam(x.khung, "data-pvqu", "auto");
  await xa();
  assert.match(nutTag(x.khung, "data-pvqu", "auto"), /aria-pressed="false">TẮT</, "lỗi khi bật → về TẮT");
  assert.equal(tieuDeHop(x.S.hop.at(-1)), "Lỗi");
  assert.ok(x.S.hop.at(-1).innerHTML.includes("HTTPError: 500: db locked"));
  assert.equal(urls(x.S).filter((u) => u === "GET /api/v2/settings/").length, 1, "lỗi vĩnh viễn: không đọc lại");

  const y = await moQ({ "POST /api/v2/settings/autopost-on": { status: 502, body: { loi: "Không với tới máy nhà" } } });
  y.tuyen["GET /api/v2/settings/"] = { autopost_enabled: "1" }; // lệnh thật ra đã tới máy nhà
  bam(y.khung, "data-pvqu", "auto");
  await xa();
  assert.equal(urls(y.S).filter((u) => u === "GET /api/v2/settings/").length, 2, "lỗi tạm: đọc lại trạng thái thật");
  assert.match(nutTag(y.khung, "data-pvqu", "auto"), />BẬT</);
  assert.ok(y.S.hop.at(-1).innerHTML.includes("HTTPError: 502: Không với tới máy nhà"));
});

test("Queue: ▶ Chạy ngay — khoá dòng + '…' TRƯỚC await, toast chờ, 202 → hỏi _kq → 'Đã chạy #5' + làm mới; bấm đúp chỉ 1 POST", async () => {
  let khoaKhiGui = null, kq = 0;
  const x = await moQ({
    "POST /api/v2/queue/5/post": () => { khoaKhiGui = /data-pvqu-chay="5"[^>]*disabled>…</.test(x.khung.innerHTML); return { status: 202, body: { cho: CHO, toi_da_giay: 300 } }; },
    [`GET /_kq/${CHO}`]: () => (++kq < 2 ? { xong: false } : KQ(200, { status: "done" })),
  });
  const truoc = x.S.goi.length;
  bam(x.khung, "data-pvqu-chay", "5");
  assert.equal(bam(x.khung, "data-pvqu-chay", "5"), true, "lần 2 bấm vào nút đã khoá");
  assert.deepEqual(x.S.toasts, ["Đang đăng video #5, vui lòng đợi..."]);
  await xa();
  assert.equal(khoaKhiGui, true);
  assert.match(nutTag(x.khung, "data-pvqu-chay", "6"), />▶</, "dòng khác không khoá");
  await x.clock.tien(3000);
  assert.match(nutTag(x.khung, "data-pvqu-chay", "5"), /disabled>…</, "đang chờ _kq: vẫn khoá");
  await x.clock.tien(3000);
  assert.deepEqual(x.S.toasts, ["Đang đăng video #5, vui lòng đợi...", "Đã chạy #5"]);
  assert.deepEqual(urls(x.S).slice(truoc), ["POST /api/v2/queue/5/post", `GET /_kq/${CHO}`, `GET /_kq/${CHO}`, "GET /api/v2/queue/status", T_DS("pending")]);
  assert.match(nutTag(x.khung, "data-pvqu-chay", "5"), /aria-label="Chạy ngay">▶</, "xong: mở khoá");
});

test("Queue: ▶ lỗi vĩnh viễn → mở khoá + 'Lỗi'; lỗi tạm mà máy nhà còn chạy lệnh → giữ khoá, theo dõi tiếp (không gửi lại); lỗi tạm không còn lệnh → mở khoá", async () => {
  const x = await moQ({ "POST /api/v2/queue/5/post": { status: 409, body: { detail: "Item đang chạy" } } });
  bam(x.khung, "data-pvqu-chay", "5");
  await xa();
  assert.match(nutTag(x.khung, "data-pvqu-chay", "5"), />▶</);
  assert.equal(tieuDeHop(x.S.hop.at(-1)), "Lỗi");
  assert.ok(x.S.hop.at(-1).innerHTML.includes("HTTPError: 409: Item đang chạy"));
  assert.equal(urls(x.S).filter((u) => u === "GET /_kq").length, 1, "lỗi vĩnh viễn: không hỏi dangChay");

  const y = await moQ({ "POST /api/v2/queue/5/post": { status: 504, body: { loi: "Máy nhà trả lời quá chậm. Thao tác CÓ THỂ đã chạy" } },
    [`GET /_kq/${CHO}`]: KQ(200, {}) });
  y.tuyen["GET /_kq"] = { dang_chay: [{ cho: CHO, method: "POST", path: "/api/v2/queue/5/post", lop: "L", toi_da_giay: 300, tom_tat: { queue_id: 5 } }] };
  bam(y.khung, "data-pvqu-chay", "5");
  await xa();
  assert.match(nutTag(y.khung, "data-pvqu-chay", "5"), /disabled>…</, "lỗi tạm + còn chạy: giữ khoá");
  assert.equal(y.S.hop.length, 0);
  await y.clock.tien(3000);
  assert.equal(urls(y.S).filter((u) => u === "POST /api/v2/queue/5/post").length, 1, "không tự gửi lại lệnh ghi");
  assert.deepEqual(y.S.toasts.at(-1), "Đã chạy #5");
  assert.match(nutTag(y.khung, "data-pvqu-chay", "5"), />▶</);

  const z = await moQ({ "POST /api/v2/queue/5/post": { status: 429, body: { loi: "Đang có lệnh đăng/login khác chạy, chờ xong rồi thử lại" } } });
  bam(z.khung, "data-pvqu-chay", "5");
  await xa();
  assert.equal(urls(z.S).filter((u) => u === "GET /_kq").length, 2, "lỗi tạm: hỏi lại dangChay");
  assert.match(nutTag(z.khung, "data-pvqu-chay", "5"), />▶</);
  assert.ok(z.S.hop.at(-1).innerHTML.includes("HTTPError: 429: Đang có lệnh đăng/login khác chạy, chờ xong rồi thử lại"));
});

test("Queue: mở trang khi dangChay có queue/{id}/post|run → dòng đó khoá, pvCho; xong → toast + làm mới bảng; lỗi nền → mở khoá + 'Lỗi'", async () => {
  let kq = 0;
  const x = await moQ({
    "GET /_kq": { dang_chay: [
      { cho: CHO, method: "POST", path: "/api/v2/queue/5/run", lop: "L", giay_da_chay: 12, toi_da_giay: 300, tom_tat: { queue_id: 5 } },
      { cho: CHO2, method: "POST", path: "/api/v2/post/direct", lop: "L", toi_da_giay: 300, tom_tat: { folder_id: 2, video: "a.mp4" } },
    ] },
    [`GET /_kq/${CHO}`]: () => (++kq < 2 ? { xong: false } : KQ(200, {})),
  });
  assert.match(nutTag(x.khung, "data-pvqu-chay", "5"), /disabled>…</);
  assert.match(nutTag(x.khung, "data-pvqu-chay", "6"), />▶</);
  bam(x.khung, "data-pvqu", "lam-moi"); // vẽ lại bảng vẫn giữ khoá (đang tải: bị bỏ, như desktop)
  await x.clock.tien(3000);
  assert.match(nutTag(x.khung, "data-pvqu-chay", "5"), /disabled>…</);
  const truoc = x.S.goi.length;
  await x.clock.tien(3000);
  assert.deepEqual(x.S.toasts, ["Đã chạy #5"]);
  assert.deepEqual(urls(x.S).slice(truoc), [`GET /_kq/${CHO}`, "GET /api/v2/queue/status", T_DS("pending")]);
  assert.match(nutTag(x.khung, "data-pvqu-chay", "5"), />▶</);
  assert.ok(!urls(x.S).includes(`GET /_kq/${CHO2}`), "lệnh post/direct không thuộc trang Queue");

  const y = await moQ({
    "GET /_kq": { dang_chay: [{ cho: CHO, method: "POST", path: "/api/v2/queue/6/post", toi_da_giay: 300, tom_tat: { queue_id: 6 } }] },
    [`GET /_kq/${CHO}`]: KQ(500, { detail: `Upload lỗi ${BAN}` }),
  });
  await y.clock.tien(3000);
  assert.match(nutTag(y.khung, "data-pvqu-chay", "6"), />▶</);
  assert.equal(tieuDeHop(y.S.hop.at(-1)), "Lỗi");
  assert.ok(y.S.hop.at(-1).innerHTML.includes(esc(`HTTPError: 500: Upload lỗi ${BAN}`)) && !y.S.hop.at(-1).innerHTML.includes(BAN));
});

test("Queue: ↻ Retry → queueRetry + toast + làm mới; ✕ → confirm_destructive 'Xóa queue item' (Hủy không gọi) → deleteQueueItem + toast", async () => {
  const x = await moQ({ "POST /api/v2/queue/6/retry": { ok: true }, "DELETE /api/v2/queue/5": { ok: true } });
  let truoc = x.S.goi.length;
  bam(x.khung, "data-pvqu-thu", "6");
  await xa();
  assert.deepEqual(urls(x.S).slice(truoc), ["POST /api/v2/queue/6/retry", "GET /api/v2/queue/status", T_DS("pending")]);
  assert.equal(x.S.goi[truoc].body, "{}");
  assert.deepEqual(x.S.toasts, ["Đã retry #6"]);

  bam(x.khung, "data-pvqu-xoa", "5");
  const h = x.S.hop.at(-1);
  assert.equal(tieuDeHop(h), "Xóa queue item");
  assert.ok(h.innerHTML.includes("Bạn sắp xóa:\n\nMục bị ảnh hưởng: #5\n\nBạn có chắc chắn muốn thực hiện?"));
  assert.match(h.innerHTML, /⚠️/);
  assert.deepEqual(nutHop(h), [["co", "Xóa"], ["khong", "Hủy"]]);
  bamHop(h, "khong");
  await xa();
  assert.ok(!urls(x.S).includes("DELETE /api/v2/queue/5"));
  bam(x.khung, "data-pvqu-xoa", "5");
  bamHop(x.S.hop.at(-1), "co");
  await xa();
  truoc = urls(x.S).indexOf("DELETE /api/v2/queue/5");
  assert.ok(truoc > 0);
  assert.equal(x.S.goi[truoc].body, undefined, "DELETE không body");
  assert.deepEqual(x.S.toasts.at(-1), "Đã xóa thành công #5");
});

test("Queue: Gỡ kẹt / Xóa hết chờ / Reset toàn bộ / Random — đúng tiêu đề + câu xác nhận; Hủy không gọi; xong → toast số từ API + làm mới", async () => {
  const CA4 = [
    ["go-ket", "Gỡ kẹt video", "Reset tất cả video đang chạy quá 15 phút về pending.", "POST /api/v2/queue/unstick", { reset_count: 3 }, "Đã gỡ 3 video"],
    ["xoa-cho", "Xóa hết chờ", "Xóa tất cả video đang pending. Đã đăng/lỗi giữ nguyên.", "DELETE /api/v2/queue/pending/clear", { deleted: 4 }, "Đã xóa 4 pending"],
    ["reset", "Reset toàn bộ", "Reset toàn bộ video failed/stuck về pending để thử lại.", "POST /api/v2/queue/reset-all", {}, "Đã reset 0 video"],
    ["random", "Random hàng chờ", "Xáo trộn thứ tự tất cả video đang pending, giãn cách lại 3-5 phút mỗi video.", "POST /api/v2/queue/random_shuffle",
      { shuffled: null }, "Đã random None video"],
  ];
  for (const [ma, tieu, cau, lenh, tra, chuToast] of CA4) {
    const x = await moQ({ [lenh]: tra });
    bam(x.khung, "data-pvqu", ma);
    let h = x.S.hop.at(-1);
    assert.equal(tieuDeHop(h), tieu, ma);
    assert.ok(h.innerHTML.includes(cau), `${ma}: câu`);
    assert.ok(!h.innerHTML.includes("Mục bị ảnh hưởng"), ma);
    // confirm_destructive: câu chứa "đăng"/"thêm" (kể cả "Đã đăng" của Xóa hết chờ — lỗi gốc giữ nguyên) → nút "Xác nhận" + ❓.
    const hanhDong = cau.toLowerCase().includes("đăng") || cau.toLowerCase().includes("thêm");
    assert.equal(hanhDong, ma === "xoa-cho", ma);
    assert.deepEqual(nutHop(h), [["co", hanhDong ? "Xác nhận" : "Xóa"], ["khong", "Hủy"]], ma);
    assert.ok(h.innerHTML.includes(hanhDong ? "❓" : "⚠️"), ma);
    bamHop(h, "khong");
    await xa();
    assert.ok(!urls(x.S).includes(lenh), `${ma}: Hủy không gọi`);
    bam(x.khung, "data-pvqu", ma);
    h = x.S.hop.at(-1);
    const truoc = x.S.goi.length;
    bamHop(h, "co");
    await xa();
    assert.deepEqual(urls(x.S).slice(truoc), [lenh, "GET /api/v2/queue/status", T_DS("pending")], ma);
    if (lenh.startsWith("POST")) assert.equal(x.S.goi[truoc].body, "{}");
    assert.deepEqual(x.S.toasts, [chuToast], ma);
  }
  const e = await moQ({ "POST /api/v2/queue/unstick": { status: 500, body: { detail: "x" } } });
  bam(e.khung, "data-pvqu", "go-ket");
  bamHop(e.S.hop.at(-1), "co");
  await xa();
  assert.equal(tieuDeHop(e.S.hop.at(-1)), "Lỗi");
  assert.ok(e.S.hop.at(-1).innerHTML.includes("HTTPError: 500: x"));
  assert.deepEqual(e.S.toasts, []);
});

test("Queue: 📅 Lên lịch — hộp _PlanDialog; Hủy không gì; 'Trống' khi không có item / không có pending; xác nhận 'Lên lịch lại' (jitter) → queue_unstick (lỗi gốc giữ)", async () => {
  const x = await moQ({ "POST /api/v2/queue/unstick": { reset_count: 0 } });
  bam(x.khung, "data-pvqu", "len-lich");
  let h = x.S.hop.at(-1);
  assert.equal(tieuDeHop(h), "📅 Lên lịch đăng video");
  for (const nhan of ["Số video:", "Khung giờ vàng:", "Jitter (phút):"]) assert.ok(h.innerHTML.includes(`>${nhan}</label>`), nhan);
  assert.deepEqual(nutHop(h), [["luu", "Lên lịch"], ["huy", "Hủy"]]);
  assert.equal(h.querySelector('[name="count"]').value, "5");
  assert.equal(h.querySelector('[name="times"]').value, '["08:00","12:00","20:00"]');
  assert.equal(h.querySelector('[name="jitter"]').value, "20");
  bamHop(h, "huy");
  await xa();
  assert.equal(x.S.hop.length, 1);

  bam(x.khung, "data-pvqu", "len-lich");
  h = x.S.hop.at(-1);
  h.querySelector('[name="jitter"]').value = "35";
  h.querySelector('[name="count"]').value = "9";
  bamHop(h, "luu");
  await xa();
  h = x.S.hop.at(-1);
  assert.equal(tieuDeHop(h), "Lên lịch lại");
  assert.ok(h.innerHTML.includes("Sẽ re-schedule 2 pending item với jitter 35 phút."), "đếm pending của trang vừa tải, không dùng 'Số video'");
  assert.deepEqual(nutHop(h), [["co", "Xóa"], ["khong", "Hủy"]], "lỗi gốc: confirm_destructive coi đây là xoá");
  const truoc = x.S.goi.length;
  bamHop(h, "co");
  await xa();
  assert.deepEqual(urls(x.S).slice(truoc), ["POST /api/v2/queue/unstick", "GET /api/v2/queue/status", T_DS("pending")]);
  assert.equal(x.S.goi[truoc].body, "{}", "không gửi count/post_times/jitter (như desktop)");
  assert.deepEqual(x.S.toasts, ["Đã re-schedule 2 item"]);

  const y = await moQ({ [T_DS("pending")]: [] });
  bam(y.khung, "data-pvqu", "len-lich");
  bamHop(y.S.hop.at(-1), "luu");
  await xa();
  assert.equal(tieuDeHop(y.S.hop.at(-1)), "Trống");
  assert.ok(y.S.hop.at(-1).innerHTML.includes("Không có item nào để lên lịch."));
  assert.match(y.S.hop.at(-1).innerHTML, /pv-hop-info/);

  const z = await moQ({ [T_DS("failed")]: [{ id: 9, status: "failed" }] });
  bam(z.khung, "data-pvqu-tab", "failed");
  await xa();
  bam(z.khung, "data-pvqu", "len-lich");
  bamHop(z.S.hop.at(-1), "luu");
  await xa();
  assert.ok(z.S.hop.at(-1).innerHTML.includes("Không có pending item nào để lên lịch."), "self._items = trang vừa tải (tab Lỗi)");
});

test("Queue: tab → list_queue(status); 'Tất cả' không status; phân trang 100/trang ◀/▶; chặn làm mới chồng + lưới an toàn 35 s; đổi tab khi đang tải bị bỏ (lỗi gốc)", async () => {
  const cho = hoan();
  const x = await moQ({ "GET /api/v2/queue/status": { pending: 250, running: 0, done: 0, failed: 1 },
    [T_DS("failed")]: [{ id: 9, status: "failed" }], [T_DS(null)]: DONG, [T_DS("pending", 100)]: () => cho.p });
  assert.match(x.khung.innerHTML, />Trang 1 \/ 3 \(Tổng: 250 mục - 100\/trang\)</);
  assert.match(nutTag(x.khung, "data-pvqu", "truoc"), /disabled/);
  bam(x.khung, "data-pvqu", "sau");
  await xa();
  assert.equal(urls(x.S).at(-1), T_DS("pending", 100));
  // đang tải: Refresh / đổi tab bị bỏ (refresh_async debounce)
  const n = x.S.goi.length;
  bam(x.khung, "data-pvqu", "lam-moi");
  bam(x.khung, "data-pvqu-tab", "failed");
  await xa();
  assert.equal(x.S.goi.length, n, "không gọi chồng");
  assert.match(x.khung.innerHTML, /aria-selected="true" data-pvqu-tab="failed"/, "tab đã đổi nhưng bảng chưa tải (như desktop)");
  assert.deepEqual(dongBang(x.khung.innerHTML), []);
  cho.xong(DONG);
  await xa();
  assert.deepEqual(dongBang(x.khung.innerHTML), [], "kết quả của tab pending không đổ vào tab failed");
  bam(x.khung, "data-pvqu", "lam-moi");
  await xa();
  assert.equal(urls(x.S).at(-1), T_DS("failed"));
  assert.deepEqual(dongBang(x.khung.innerHTML).map((r) => r[0]), ["9"]);
  bam(x.khung, "data-pvqu-tab", "all");
  await xa();
  assert.equal(urls(x.S).at(-1), T_DS(null));
  bam(x.khung, "data-pvqu-tab", "pending");
  await xa();
  assert.equal(urls(x.S).at(-1), T_DS("pending", 100), "mỗi tab nhớ trang riêng");

  const treo = await moQ({ [T_DS("pending")]: () => new Promise(() => {}) });
  const m = treo.S.goi.length;
  bam(treo.khung, "data-pvqu", "lam-moi");
  await xa();
  assert.equal(treo.S.goi.length, m);
  await treo.clock.tien(35_000);
  bam(treo.khung, "data-pvqu", "lam-moi");
  await xa();
  assert.equal(treo.S.goi.length, m + 2, "sau 35 s cho làm mới lại");
});

test("Queue: lỗi tải → 'Lỗi tải queue' (cờ chặn giữ tới khi đóng hộp, như desktop); lỗi status_counts im lặng; XSS trong bảng", async () => {
  const x = await moQ({ [T_DS("pending")]: { status: 500, body: { detail: "db" } }, "GET /api/v2/queue/status": { status: 500, body: {} } });
  const h = x.S.hop.at(-1);
  assert.equal(tieuDeHop(h), "Lỗi tải queue");
  assert.match(h.innerHTML, /pv-hop-critical/);
  assert.ok(h.innerHTML.includes("HTTPError: 500: db"));
  assert.equal(x.S.hop.length, 1, "lỗi status_counts chỉ ghi log");
  const n = x.S.goi.length;
  bam(x.khung, "data-pvqu", "lam-moi");
  await xa();
  assert.equal(x.S.goi.length, n, "hộp lỗi còn mở: refresh vẫn đang chạy");
  bamHop(h, "ok");
  await xa();
  bam(x.khung, "data-pvqu", "lam-moi");
  await xa();
  assert.equal(x.S.goi.length, n + 2);

  const y = await moQ({ [T_DS("pending")]: [{ id: 5, video_filename: BAN, folder_name: BAN, account_name: BAN, product_id: BAN, status: BAN, scheduled_at: BAN }] });
  assert.ok(!y.khung.innerHTML.includes(BAN));
  assert.deepEqual(dongBang(y.khung.innerHTML)[0].slice(0, 6), [ "5", esc(BAN), esc(BAN), esc(BAN), esc(BAN), esc(BAN)]);
  assert.match(y.khung.innerHTML, new RegExp(`title="${esc(BAN).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`), "tooltip sản phẩm đã esc");
});

test("Queue: rời trang giữa chừng — không vẽ đè, không hộp lỗi, không toast 'Đã chạy'; pvQuDung huỷ lưới 35 s; id lạ trong data-* bị bỏ", async () => {
  const cho = hoan();
  const x = nap({ tuyen: tuyenQ({ [T_DS("pending")]: () => cho.p }) });
  await x.P.pvQuVe(x.khung, x.P.phien());
  await xa();
  const truoc = x.khung.innerHTML;
  assert.ok([...x.clock.hen.values()].some((h) => h.ms === 35_000));
  x.P.pvDung();
  assert.ok(![...x.clock.hen.values()].some((h) => h.ms === 35_000), "pvQuDung xoá hẹn 35 s");
  cho.xong({ status: 500, body: { detail: "x" } });
  await xa();
  assert.equal(x.khung.innerHTML, truoc);
  assert.equal(x.S.hop.length, 0);

  const y = await moQ({ "POST /api/v2/queue/5/post": { status: 202, body: { cho: CHO, toi_da_giay: 300 } }, [`GET /_kq/${CHO}`]: { xong: false } });
  bam(y.khung, "data-pvqu-chay", "5");
  await xa();
  const v = y.khung.innerHTML;
  y.P.pvDung();
  await y.clock.tien(10_000);
  assert.deepEqual(y.S.toasts, ["Đang đăng video #5, vui lòng đợi..."]);
  assert.equal(y.S.hop.length, 0, "lỗi roiTrang không hiện");
  assert.equal(y.khung.innerHTML, v);
  assert.equal(urls(y.S).filter((u) => u.startsWith("GET /_kq/")).length, 0, "ngừng hỏi _kq ngay khi rời trang");

  const z = await moQ();
  const n = z.S.goi.length;
  z.khung.nghe.click({ target: { closest: () => ({ dataset: { pvquChay: "../1" }, disabled: false }) } });
  z.khung.nghe.click({ target: { closest: () => ({ dataset: { pvquTab: "x" }, disabled: false }) } });
  z.khung.nghe.click({ target: { closest: () => null } });
  await xa();
  assert.equal(z.S.goi.length, n);
});

test("_friendly_error (widgets/common.py:166-178): 401 / 404 / mất kết nối / timeout / còn lại 'HTTPError: …' cắt 200 — giống nhau ở 2 trang", () => {
  const CA2 = new Function("esc", `"use strict";
${khoi(CAL, "pvca-thuan")}
return pvcaLoi;`)(esc);
  const QU2 = new Function("esc", `"use strict";
${khoi(QU, "pvqu-thuan")}
return pvquLoi;`)(esc);
  const loi = (msg, status) => Object.assign(new Error(msg), status === undefined ? {} : { status });
  const BANG = [
    [loi("401: x", 401), "Khong co quyen truy cap (401). Kiem tra API token trong .env."],
    [loi("404: Queue item not found", 404), "API khong ton tai (404). Kiem tra backend co dang chay khong."],
    [loi("Không kết nối được máy chủ: Failed to fetch", 0), "Khong ket noi duoc backend. Hay kiem tra V2 Backend da chay chua."],
    [loi("504: Read Timeout", 504), "Backend phan hoi cham (timeout). Thu lai sau."],
    [loi(`500: ${"y".repeat(300)}`, 500), `HTTPError: 500: ${"y".repeat(195)}`],
    [loi("Mã không hợp lệ: x"), "Error: Mã không hợp lệ: x"],
  ];
  for (const [e, ra] of BANG) {
    assert.equal(CA2(e), ra, e.message.slice(0, 30));
    assert.equal(QU2(e), ra, e.message.slice(0, 30));
  }
});

test("pv-calendar.js / pv-queue.js: không gắn sự kiện inline, không tự gọi fetch, chỉ gọi pvApi; mọi tên cấp đỉnh đúng tiền tố", () => {
  const tenDinh = (src) => [...src.matchAll(/^(?:async )?function\*? ?(\w+)|^(?:const|let|var|class) (\w+)/gm)].map((m) => m[1] || m[2]);
  for (const [src, tt] of [[CAL, "pvca"], [QU, "pvqu"]]) {
    for (const t of tenDinh(src)) assert.ok(t.toLowerCase().startsWith(tt), `${tt}: ${t}`);
    assert.ok(!/\son[a-z]+="/.test(src) && !/onclick\s*=/i.test(src), "CSP: không inline handler");
    assert.ok(!/\bfetch\(/.test(src) && !/pvGoi\(/.test(src), "chỉ qua pvApi");
    assert.ok(!/innerHTML\s*\+=/.test(src));
  }
  assert.ok(/function pvCaVe\(khung, phien\)/.test(CAL) && /function pvCaDung\(\)/.test(CAL));
  assert.ok(/function pvQuVe\(khung, phien\)/.test(QU) && /function pvQuDung\(\)/.test(QU));
});
