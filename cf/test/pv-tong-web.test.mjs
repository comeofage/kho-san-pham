// Test W-P2: 4 trang Poster V2 trên web — Dashboard (web/pv-dashboard.js), Views (pv-views.js), Logs (pv-logs.js), Settings (pv-settings.js).
// Thiết kế: docs/poster-v2-tren-web.md §5.3, §6.3–§6.5, §9 W-P2. Nguồn bê nguyên: E:/tool/tiktok_poster_v2/src/desktop/pages/*.py.
// Không mạng: globalThis.fetch bị thay bằng hàm ném lỗi TRƯỚC khi nạp mã; mã nạp nhận fetch giả qua tham số, URL lạ → ném lỗi.
// Nạp NGUYÊN web/poster.js thật + 4 file trang trong cùng một phạm vi (như trình duyệt), DOM giả tối thiểu.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

globalThis.fetch = async (url) => { throw new Error(`fetch thật bị cấm trong test: ${url}`); };

const duong = (p) => new URL(`../../web/${p}`, import.meta.url);
const doc = (p) => readFileSync(duong(p), "utf8");
const APP = doc("app.js");
const POSTER = doc("poster.js");
const FILE = { db: doc("pv-dashboard.js"), vi: doc("pv-views.js"), lo: doc("pv-logs.js"), se: doc("pv-settings.js") };

const dongBatDau = (src, dau) => {
  const l = src.split("\n").find((x) => x.startsWith(dau));
  assert.ok(l, `không thấy dòng bắt đầu bằng "${dau}"`);
  return l;
};
const esc = new Function(`${dongBatDau(APP, "const esc = ")}\nreturn esc;`)();
const khoi = (src, ten) => {
  const m = src.match(new RegExp(`// --- ${ten} start ---\\n([\\s\\S]*?)// --- ${ten} end ---`));
  assert.ok(m, `thiếu marker ${ten}`);
  return m[1];
};
const BAN = `<img src=x onerror=alert(1)>`;
const xa = async () => { for (let i = 0; i < 40; i++) await new Promise((r) => setImmediate(r)); };

// Đồng hồ giả (như poster-web.test.mjs): setTimeout/setInterval/Date.now chỉ chạy khi gọi tien(ms).
function dongHoGia() {
  const c = { now: Date.UTC(2026, 10, 18, 3, 4, 5), hen: new Map(), id: 0 };
  c.setTimeout = (fn, ms) => { const id = ++c.id; c.hen.set(id, { at: c.now + (ms || 0), fn, lap: 0 }); return id; };
  c.setInterval = (fn, ms) => { const id = ++c.id; c.hen.set(id, { at: c.now + ms, fn, lap: ms }); return id; };
  c.clearTimeout = (id) => { c.hen.delete(id); };
  c.clearInterval = c.clearTimeout;
  c.soLap = () => [...c.hen.values()].filter((h) => h.lap).length;
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

const theGia = (extra = {}) => ({ innerHTML: "", textContent: "", dataset: {}, disabled: false, hidden: false, nghe: {},
  addEventListener(ev, f) { this.nghe[ev] = f; }, ...extra });
const hopGia = () => theGia({ open: false, daXoa: false, className: "",
  showModal() { this.open = true; }, close() { this.open = false; }, remove() { this.daXoa = true; }, querySelector() { return null; } });

const camel = (s) => s.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
// Mọi thẻ mở trong html có thuộc tính data-*: { tag, dataset, disabled, chu (chữ ngay sau thẻ) }.
function cacThe(html) {
  return [...html.matchAll(/<(\w+)((?:\s+[\w-]+(?:="[^"]*")?)*)\s*>([^<]*)/g)].map((m) => {
    const ds = {};
    for (const a of m[2].matchAll(/\sdata-([\w-]+)(?:="([^"]*)")?/g)) ds[camel(a[1])] = a[2] ?? "";
    return { tag: m[1], attrs: m[2], dataset: ds, disabled: /\sdisabled(\s|$|=)/.test(m[2]), chu: m[3] };
  }).filter((t) => Object.keys(t.dataset).length);
}

// Phần tử khung #pv-noi giả: innerHTML đặt lại → bỏ phần tử con cũ; querySelector("#id") dựng phần tử từ thẻ trong HTML hiện tại.
function khungGia() {
  const k = { nghe: {}, con: {}, _html: "", addEventListener(ev, f) { this.nghe[ev] = f; } };
  Object.defineProperty(k, "innerHTML", { get() { return this._html; }, set(v) { this._html = String(v); this.con = {}; } });
  k.querySelector = (s) => {
    const m = s.match(/^#([\w-]+)$/);
    if (!m) return null;
    const id = m[1];
    if (k.con[id]) return k.con[id];
    const t = k._html.match(new RegExp(`<(\\w+)([^>]*\\sid="${id}"[^>]*)>`));
    if (!t) return null;
    const at = (n) => { const x = t[2].match(new RegExp(`\\s${n}="([^"]*)"`)); return x ? x[1] : undefined; };
    const el = { id, tag: t[1], type: at("type"), placeholder: at("placeholder") ?? "", value: at("value") ?? "",
      checked: /\schecked(\s|$)/.test(t[2]), innerHTML: "" };
    const sau = k._html.slice(t.index + t[0].length);
    if (t[1] === "select") {
      const ds = sau.slice(0, sau.indexOf("</select>"));
      el.options = [...ds.matchAll(/<option value="([^"]*)"/g)].map((x) => x[1]);
      const chon = ds.match(/<option value="([^"]*)" selected>/);
      el.value = chon ? chon[1] : el.options[0] || "";
    }
    if (t[1] === "div") el.innerHTML = sau.slice(0, sau.indexOf("</div>"));
    return (k.con[id] = el);
  };
  return k;
}
// Bấm phần tử có data-* khớp mọi cặp trong `khop` (như trình duyệt: phần tử disabled không phát click).
function bamKhung(k, khop) {
  const t = cacThe(k.innerHTML).find((x) => Object.entries(khop).every(([a, v]) => x.dataset[a] === v));
  assert.ok(t, `không thấy phần tử ${JSON.stringify(khop)}`);
  if (t.disabled) return false;
  const tien = Object.keys(khop)[0];
  k.nghe.click({ target: { closest: (sel) => (sel === `[data-${tien}]` ? { dataset: t.dataset, disabled: t.disabled } : null) } });
  return true;
}
const bamHop = (el, ma) => el.nghe.click({ target: { closest: () => ({ dataset: { pvNut: ma } }) } });
const chuHop = (el) => el.innerHTML;
const tieuDeHop = (el) => (el.innerHTML.match(/<h3 class="pv-hop-tieu-de">([^<]*)<\/h3>/) || [])[1];

// Nạp poster.js thật + 4 trang. xuLy(url, opt) → { status, body } | Promise<…> | undefined (undefined = ném "fetch thật bị cấm").
function nap({ xuLy, user = "nhan" } = {}) {
  const S = { goi: [], toasts: [], hop: [], canhBao: [], el: {} };
  const clock = dongHoGia();
  const auth = { user, ten: user, get on() { return !!this.user; } };
  const app = theGia();
  const noi = khungGia();
  const $ = (s) => {
    if (s === "#app") return app;
    const m = s.match(/^#([\w-]+)$/);
    if (!m || !app.innerHTML.includes(`id="${m[1]}"`)) return null;
    if (m[1] === "pv-noi") return noi;
    return (S.el[m[1]] ||= theGia());
  };
  const document = { hidden: false, body: { append(el) { S.hop.push(el); } }, createElement: () => hopGia() };
  const fetch = async (url, opt = {}) => {
    const rec = { url, method: opt.method || "GET", headers: { ...(opt.headers || {}) }, body: opt.body };
    S.goi.push(rec);
    const r = xuLy ? await xuLy(url, opt, rec) : undefined;
    if (!r) throw new Error(`fetch thật bị cấm trong test: ${url}`);
    if (r.mang) throw new TypeError("Failed to fetch");
    const txt = typeof r.body === "string" ? r.body : r.body === undefined ? "" : JSON.stringify(r.body);
    return { status: r.status, ok: r.status >= 200 && r.status < 300, text: async () => txt };
  };
  class DateGia extends Date {
    constructor(...a) { if (a.length) super(...a); else super(clock.now); }
    static now() { return clock.now; }
  }
  const trang = {};
  const ns = {
    esc, $, document, auth, fetch, globalThis: trang, mnCHUA_CO: "<p>chưa có</p>",
    renderUser: () => {}, openLogin: () => {}, toast: (m) => S.toasts.push(m),
    setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout, setInterval: clock.setInterval, clearInterval: clock.clearInterval,
    Date: DateGia, console: { warn: (m) => S.canhBao.push(String(m)), debug: (m) => S.canhBao.push(String(m)), error: () => {}, log: () => {} },
  };
  const ten = Object.keys(ns);
  const P = new Function(...ten, `${POSTER}\n;\n${FILE.db}\n;\n${FILE.vi}\n;\n${FILE.lo}\n;\n${FILE.se}
return { pvApi, pvRender, pvDung, pvHenGio, phien: () => pvPhien, pvDbVe, pvViVe, pvLoVe, pvSeVe };`)(...ten.map((k) => ns[k]));
  Object.assign(trang, { pvDbVe: P.pvDbVe, pvViVe: P.pvViVe, pvLoVe: P.pvLoVe, pvSeVe: P.pvSeVe });
  return { P, S, clock, auth, app, noi, khung: noi, document };
}
// Bảng định tuyến fetch giả: khoá "METHOD /đường" (sau /api/poster). Giá trị: { status, body } | hàm (rec) → … ; thiếu → ném lỗi.
const API = "/api/poster";
function bang(ds) {
  return (url, opt, rec) => {
    const k = `${(opt.method || "GET").toUpperCase()} ${url.startsWith(API) ? url.slice(API.length) : url}`;
    if (!Object.prototype.hasOwnProperty.call(ds, k)) return undefined;
    const v = ds[k];
    return typeof v === "function" ? v(rec) : v;
  };
}
const ok = (body) => ({ status: 200, body });
const hoan = () => { let tra; const p = new Promise((r) => { tra = r; }); return { p, tra }; };
const goiApi = (S) => S.goi.map((r) => `${r.method} ${r.url.slice(API.length)}`);
const khongCoBan = (html, chu) => {
  assert.ok(!html.includes(BAN), `${chu}: chuỗi BAN thô lọt vào DOM`);
  assert.ok(!/<img/i.test(html), `${chu}: có thẻ <img>`);
};

// ================= chung =================
const TIEN_TO = { db: "pvdb", vi: "pvvi", lo: "pvlo", se: "pvse" };
const VE = { db: "pvDbVe", vi: "pvViVe", lo: "pvLoVe", se: "pvSeVe" };
const tenDinh = (src) => [...src.matchAll(/^(?:async )?function\*? ?(\w+)|^(?:const|let|var|class) (\w+)/gm)].map((m) => m[1] || m[2]);

test("4 file: tên cấp đỉnh đúng tiền tố §6.3 (không phân biệt hoa thường), có pv<xx>Ve, không gắn sự kiện inline, không fetch/setInterval/setTimeout riêng", () => {
  for (const [k, src] of Object.entries(FILE)) {
    const ds = tenDinh(src);
    assert.ok(ds.includes(VE[k]), `${k}: thiếu ${VE[k]}`);
    for (const t of ds) assert.ok(t.toLowerCase().startsWith(TIEN_TO[k]), `${k}: "${t}" phải bắt đầu bằng ${TIEN_TO[k]}`);
    assert.ok(!/\son[a-z]+="/.test(src) && !/onclick\s*=/i.test(src), `${k}: không gắn sự kiện inline (CSP)`);
    assert.ok(!/\bfetch\(/.test(src), `${k}: chỉ gọi qua pvApi`);
    assert.ok(!/\bset(Interval|Timeout)\(/.test(src), `${k}: hẹn giờ chỉ qua pvHenGio`);
    assert.ok(!/\bfunction toast\b|id="toast"/.test(src), `${k}: không tự viết toast`);
  }
});

test("khối thuần (pvdb/pvvi/pvlo/pvse-thuan) có marker, nạp riêng được chỉ với esc", () => {
  for (const [k, src] of Object.entries(FILE)) {
    const t = TIEN_TO[k];
    const F = new Function("esc", `"use strict";\n${khoi(src, `${t}-thuan`)}\nreturn true;`);
    assert.equal(F(esc), true, k);
  }
});

test("pvRender('logs' / 'views' / 'settings' / 'dashboard') giao #pv-noi cho đúng hàm trang", async () => {
  for (const [ma, chu] of [["dashboard", "ACTIVE FOLDERS"], ["views", "📈 Views Analytics"], ["logs", "📜 Logs"], ["settings", "Telegram Notifications"]]) {
    const { P, noi } = nap({ xuLy: () => ({ status: 503, body: { loi: "tắt" } }) });
    await P.pvRender(ma);
    await xa();
    assert.ok(noi.innerHTML.includes(chu), `${ma}: thấy "${chu}"`);
    P.pvDung();
  }
});

// ================= Dashboard =================
const STATS = { total_accounts: 7, active_folders: 3, total_videos_today: 12, success_rate: 0.8734 };
const LOGS25 = [
  { created_at: "2026-11-18T10:11:12.345678", video_filename: "a.mp4", folder_id: 4, status: "done", message: "ok" },
  { created_at: "2026-11-18T09:00:00", video_filename: "", folder_id: 0, status: "failed", message: "x".repeat(200) },
  { created_at: null, status: "running" },
  { status: "warning" },
  { status: "info" },
  { status: "pending" },
];
const dbApi = (extra = {}) => bang({ "GET /api/v2/stats/": ok(STATS), "GET /api/v2/logs/?limit=25&offset=0": ok(LOGS25), ...extra });

test("Dashboard (a): chữ nguyên văn dashboard.py — tiêu đề, nút, 4 thẻ (giá trị khởi tạo 0 / 0%), tiêu đề bảng, 5 cột", async () => {
  const d = hoan();
  const { P, khung } = nap({ xuLy: bang({ "GET /api/v2/stats/": () => d.p }) });
  P.pvDbVe(khung, P.phien());
  const h = khung.innerHTML;
  assert.match(h, /<h2[^>]*>Dashboard<\/h2>/);
  assert.match(h, /data-pvdb="lammoi">↻ Refresh</);
  const the = [...h.matchAll(/data-pvdb-the="(\w+)">\s*<div[^>]*>([^<]+)<\/div>\s*<div[^>]*>([^<]*)<\/div>/g)].map((m) => [m[2], m[3]]);
  assert.deepEqual(the, [["ACCOUNTS", "0"], ["ACTIVE FOLDERS", "0"], ["POSTED TODAY", "0"], ["SUCCESS RATE", "0%"]]);
  assert.match(h, /<strong>📋 Hoạt động gần đây \(Recent Activity\)<\/strong>/);
  assert.deepEqual([...h.matchAll(/<th>([^<]+)<\/th>/g)].map((m) => m[1]), ["Thời gian", "Video", "Folder", "Trạng thái", "Ghi chú"]);
  P.pvDung();
});

test("Dashboard (b): mở trang → get_stats rồi list_logs(limit=25) tuần tự; số thẻ, 'Cập nhật lúc', dòng bảng + màu trạng thái như .py", async () => {
  const { P, S, khung } = nap({ xuLy: dbApi() });
  await P.pvDbVe(khung, P.phien());
  assert.deepEqual(goiApi(S), ["GET /api/v2/stats/", "GET /api/v2/logs/?limit=25&offset=0"]);
  const h = khung.innerHTML;
  const so = [...h.matchAll(/data-pvdb-the="(\w+)">\s*<div[^>]*>[^<]+<\/div>\s*<div[^>]*>([^<]*)<\/div>/g)].map((m) => m[2]);
  assert.deepEqual(so, ["7", "3", "12", "87.3%"]);
  const gio = new Date(Date.UTC(2026, 10, 18, 3, 4, 5));
  const p2 = (n) => String(n).padStart(2, "0");
  assert.ok(h.includes(`Cập nhật lúc: ${p2(gio.getHours())}:${p2(gio.getMinutes())}:${p2(gio.getSeconds())}`));
  const dong = [...h.matchAll(/<tr>\s*<td[^>]*>([^<]*)<\/td><td[^>]*>([^<]*)<\/td>\s*<td[^>]*>([^<]*)<\/td><td[^>]*?(?: class="([\w-]+)")?>([^<]*)<\/td>\s*<td>([^<]*)<\/td><\/tr>/g)]
    .map((m) => [m[1], m[2], m[3], m[4] || "", m[5], m[6]]);
  assert.deepEqual(dong, [
    ["2026-11-18 10:11:12", "a.mp4", "4", "pv-xanh", "DONE", "ok"],
    ["2026-11-18 09:00:00", "—", "—", "pv-do", "FAILED", "x".repeat(120)],
    ["", "—", "—", "pv-vang", "RUNNING", ""],
    ["", "—", "—", "pv-vang", "WARNING", ""],
    ["", "—", "—", "pv-xanh", "INFO", ""],
    ["", "—", "—", "", "PENDING", ""],
  ]);
});

test("Dashboard: tự làm mới 10 s qua pvHenGio; ↻ Refresh gọi lại; bấm chồng khi đang tải chỉ 1 lượt; rời trang (pvDung) thì ngừng", async () => {
  let cho = null;
  const { P, S, clock, khung } = nap({ xuLy: dbApi({ "GET /api/v2/stats/": () => (cho ? cho.p : ok(STATS)) }) });
  await P.pvDbVe(khung, P.phien());
  assert.equal(S.goi.length, 2);
  assert.equal(clock.soLap(), 1, "1 hẹn giờ của pvHenGio");
  await clock.tien(10_000);
  assert.equal(S.goi.length, 4, "sau 10 s gọi lại stats + logs");
  cho = hoan();
  bamKhung(khung, { pvdb: "lammoi" });
  bamKhung(khung, { pvdb: "lammoi" });
  await xa();
  assert.equal(S.goi.length, 5, "bấm 2 lần khi đang tải → chỉ 1 lời gọi stats");
  cho.tra(ok(STATS));
  await xa();
  assert.equal(S.goi.length, 6);
  cho = null;
  P.pvDung();
  assert.equal(clock.soLap(), 0, "pvDung xoá hẹn giờ");
  await clock.tien(60_000);
  assert.equal(S.goi.length, 6, "rời trang: không gọi nữa");
});

test("Dashboard (c): lỗi tải → chỉ ghi console 'Dashboard refresh failed: …' (logger.warning), không hộp, không toast, giữ trang", async () => {
  const { P, S, khung } = nap({ xuLy: bang({ "GET /api/v2/stats/": { status: 500, body: { detail: "boom" } } }) });
  await P.pvDbVe(khung, P.phien());
  assert.deepEqual(S.canhBao, ["Dashboard refresh failed: 500: boom"]);
  assert.equal(S.hop.length, 0);
  assert.deepEqual(S.toasts, []);
  assert.match(khung.innerHTML, /ACCOUNTS/);
  assert.deepEqual(goiApi(S), ["GET /api/v2/stats/"], "stats lỗi → không gọi logs (cùng worker)");
  P.pvDung();
});

test("Dashboard (d): XSS — mọi chuỗi từ API qua esc", async () => {
  const { P, khung } = nap({ xuLy: dbApi({
    "GET /api/v2/stats/": ok({ total_accounts: BAN, active_folders: BAN, total_videos_today: BAN, success_rate: 0 }),
    "GET /api/v2/logs/?limit=25&offset=0": ok([{ created_at: BAN, video_filename: BAN, folder_id: BAN, status: BAN, message: BAN }]),
  }) });
  await P.pvDbVe(khung, P.phien());
  khongCoBan(khung.innerHTML, "dashboard");
  assert.ok(khung.innerHTML.includes(esc(BAN)));
  P.pvDung();
});

test("Dashboard (e): rời trang giữa chừng → kết quả muộn không vẽ đè, không gọi tiếp logs, không cảnh báo", async () => {
  const d = hoan();
  const { P, S, khung } = nap({ xuLy: bang({ "GET /api/v2/stats/": () => d.p }) });
  const xong = P.pvDbVe(khung, P.phien());
  await xa();
  const truoc = khung.innerHTML;
  P.pvDung();
  khung.innerHTML = "TRANG KHAC";
  d.tra(ok(STATS));
  await xong;
  assert.equal(khung.innerHTML, "TRANG KHAC");
  assert.deepEqual(goiApi(S), ["GET /api/v2/stats/"]);
  assert.deepEqual(S.canhBao, []);
  assert.ok(truoc.includes("Dashboard"));
});

// ================= Views =================
const VI_ITEMS = [
  { product_id: "P1", folder_name: "Folder A", account_name: "acc1", growth_status: "hot", views_d0: 1234567, growth_rate: 12.345,
    avg_daily_views: 1234.56, total_views: 9876543, views_d7: 1, views_d6: 2, views_d5: 3, views_d4: 4, views_d3: 5, views_d2: 6, views_d1: 7 },
  { product_id: "P2", folder_id: 7, account_id: null, growth_status: "warm", views_d0: 0, growth_rate: -5, avg_daily_views: 0, total_views: 0 },
  { product_id: "P3", growth_status: "dead" },
  { product_id: "P4", growth_status: "la-lam" },
];
const viApi = (extra = {}) => bang({ "GET /api/v2/views/summary": ok({ items: VI_ITEMS }), ...extra });
const viDong = (h) => [...h.matchAll(/<tr>\s*<td[^>]*>([^<]*)<\/td><td>([^<]*)<\/td><td>([^<]*)<\/td>\s*<td style="color:[^"]*">([^<]*)<\/td><td>([^<]*)<\/td>\s*<td[^>]*>([^<]*)<\/td><td>([^<]*)<\/td><td>([^<]*)<\/td>/g)]
  .map((m) => m.slice(1, 9));
const viThe = (h) => Object.fromEntries([...h.matchAll(/data-pvvi-the="(\w+)"[^>]*>\s*<div[^>]*>([^<]+)<\/div>\s*<div[^>]*>(\d+)<\/div>/g)].map((m) => [m[1], [m[2], Number(m[3])]]));

test("Views (a): chữ nguyên văn views.py — tiêu đề, 🔄 Refresh, 'Lọc:' + 5 nút lọc, 4 thẻ, 9 cột, trạng thái rỗng", async () => {
  const { P, khung } = nap({ xuLy: viApi({ "GET /api/v2/views/summary": ok({ items: [] }) }) });
  await P.pvViVe(khung, P.phien());
  const h = khung.innerHTML;
  assert.match(h, /<h2[^>]*>📈 Views Analytics<\/h2>/);
  assert.match(h, /data-pvvi="lammoi">🔄 Refresh</);
  assert.match(h, /<span class="muted">Lọc:<\/span>/);
  assert.deepEqual(cacThe(h).filter((t) => t.dataset.pvvi === "loc").map((t) => [t.dataset.pvviLoc, t.chu]),
    [["all", "Tất cả"], ["hot", "🔥 Hot"], ["warm", "📈 Warm"], ["cold", "❄️ Cold"], ["dead", "💀 Dead"]]);
  assert.deepEqual(viThe(h), { hot: ["🔥 Hot", 0], warm: ["📈 Warm", 0], cold: ["❄️ Cold", 0], dead: ["💀 Dead", 0] });
  assert.ok(h.includes("Chưa có dữ liệu view") && h.includes("Bấm 'Refresh' để chạy scraper một lần.") && h.includes("📭"));
  assert.ok(!h.includes("<table"), "rỗng → ẩn bảng");
  const { P: P2, khung: k2 } = nap({ xuLy: viApi() });
  await P2.pvViVe(k2, P2.phien());
  assert.deepEqual([...k2.innerHTML.matchAll(/<th>([^<]+)<\/th>/g)].map((m) => m[1]),
    ["Product ID", "Folder", "Account", "Status", "Today", "Growth%", "Avg/day", "Total (8d)", "Trend (D-7 → D-0)"]);
  assert.ok(!k2.innerHTML.includes("Chưa có dữ liệu view"));
});

test("Views (b): views_summary → dòng bảng định dạng như _populate_row (growth_status, f'{x:,}', '{x:+.1f}%', '{x:,.1f}', #id / #None), biểu đồ 8 cột", async () => {
  const { P, S, khung } = nap({ xuLy: viApi() });
  await P.pvViVe(khung, P.phien());
  assert.deepEqual(goiApi(S), ["GET /api/v2/views/summary"]);
  const h = khung.innerHTML;
  assert.deepEqual(viDong(h), [
    ["P1", "Folder A", "acc1", "🔥 Hot", "1,234,567", "+12.3%", "1,234.6", "9,876,543"],
    ["P2", "#7", "#None", "📈 Warm", "0", "-5.0%", "0.0", "0"],
    ["P3", "#", "#", "💀 Dead", "0", "+0.0%", "0.0", "0"],
    ["P4", "#", "#", "❓ ?", "0", "+0.0%", "0.0", "0"],
  ]);
  assert.equal((h.match(/<svg /g) || []).length, 4);
  const rect1 = [...h.slice(0, h.indexOf("</svg>")).matchAll(/<rect [^>]*height="(\d+)"/g)].map((m) => Number(m[1]));
  assert.deepEqual(rect1, [2, 2, 2, 2, 2, 2, 2, 36], "cao ∝ giá trị/max, tối thiểu 2 (d7…d0)");
  assert.match(h, /fill-opacity="0\.475"/);
  assert.match(h, /fill-opacity="1\.000"/);
  // payload là danh sách (không phải dict) cũng nhận
  const { P: P2, khung: k2 } = nap({ xuLy: viApi({ "GET /api/v2/views/summary": ok(VI_ITEMS.slice(0, 1)) }) });
  await P2.pvViVe(k2, P2.phien());
  assert.equal(viDong(k2.innerHTML).length, 1);
});

test("Views (f) LỖI GỐC giữ nguyên: lọc + 4 thẻ đếm theo `status`, không theo `growth_status` → Hot/Warm… trống, thẻ = 0; lọc không gọi API", async () => {
  const { P, S, khung } = nap({ xuLy: viApi() });
  await P.pvViVe(khung, P.phien());
  assert.deepEqual(viThe(khung.innerHTML), { hot: ["🔥 Hot", 0], warm: ["📈 Warm", 0], cold: ["❄️ Cold", 0], dead: ["💀 Dead", 0] },
    "growth_status hot/warm/dead nhưng thẻ đếm vẫn 0");
  for (const k of ["hot", "warm", "dead"]) {
    bamKhung(khung, { pvvi: "loc", pvviLoc: k });
    assert.equal(viDong(khung.innerHTML).length, 0, `lọc ${k}: bảng trống dù có dòng growth_status=${k}`);
    assert.match(khung.innerHTML, new RegExp(`data-pvvi-loc="${k}" aria-pressed="true"`));
    assert.ok(!khung.innerHTML.includes("Chưa có dữ liệu view"), "không hiện trạng thái rỗng (_items khác rỗng)");
  }
  bamKhung(khung, { pvvi: "loc", pvviLoc: "all" });
  assert.equal(viDong(khung.innerHTML).length, 4);
  assert.equal(S.goi.length, 1, "đổi bộ lọc không gọi API");
  // Bằng chứng đọc `status`: dòng có status (không có growth_status) mới được đếm/lọc.
  const { P: P2, khung: k2 } = nap({ xuLy: viApi({ "GET /api/v2/views/summary": ok({ items: [
    { product_id: "S1", status: "hot", growth_status: "cold" }, { product_id: "S2", status: "hot" }, { product_id: "S3", status: "dead" }] }) }) });
  await P2.pvViVe(k2, P2.phien());
  assert.deepEqual(viThe(k2.innerHTML), { hot: ["🔥 Hot", 2], warm: ["📈 Warm", 0], cold: ["❄️ Cold", 0], dead: ["💀 Dead", 1] });
  bamKhung(k2, { pvvi: "loc", pvviLoc: "hot" });
  assert.deepEqual(viDong(k2.innerHTML).map((r) => [r[0], r[3]]), [["S1", "❄️ Cold"], ["S2", "❓ ?"]], "cột Status vẫn đọc growth_status");
});

test("Views (b): 🔄 Refresh → toast 'Đang fetch view counts...' → POST views/refresh → toast 'Đã scrape N dòng' → tải lại; bấm chồng chỉ 1 POST", async () => {
  const d = hoan();
  const { P, S, khung } = nap({ xuLy: viApi({ "POST /api/v2/views/refresh": () => d.p }) });
  await P.pvViVe(khung, P.phien());
  bamKhung(khung, { pvvi: "lammoi" });
  bamKhung(khung, { pvvi: "lammoi" });
  await xa();
  assert.deepEqual(S.toasts, ["Đang fetch view counts..."]);
  assert.deepEqual(goiApi(S), ["GET /api/v2/views/summary", "POST /api/v2/views/refresh"]);
  assert.equal(S.goi[1].body, "{}");
  d.tra(ok({ rows: 5 }));
  await xa();
  assert.deepEqual(S.toasts, ["Đang fetch view counts...", "Đã scrape 5 dòng"]);
  assert.deepEqual(goiApi(S), ["GET /api/v2/views/summary", "POST /api/v2/views/refresh", "GET /api/v2/views/summary"]);
  // không có rows → 0
  const { P: P2, S: S2, khung: k2 } = nap({ xuLy: viApi({ "POST /api/v2/views/refresh": ok({}) }) });
  await P2.pvViVe(k2, P2.phien());
  bamKhung(k2, { pvvi: "lammoi" });
  await xa();
  assert.deepEqual(S2.toasts, ["Đang fetch view counts...", "Đã scrape 0 dòng"]);
});

test("Views (c): lỗi → hộp 'Lỗi' (critical) với chữ _friendly_error: 404 / HTTPError / mất kết nối; refresh lỗi không tải lại", async () => {
  const BANG = [
    [{ status: 404, body: { detail: "Not Found" } }, "API khong ton tai (404). Kiem tra backend co dang chay khong."],
    [{ status: 500, body: { detail: "boom" } }, "HTTPError: 500: boom"],
    [{ mang: true }, "Khong ket noi duoc backend. Hay kiem tra V2 Backend da chay chua."],
    [{ status: 502, body: { loi: "Poster V2 trên máy nhà chưa mở" } }, "HTTPError: 502: Poster V2 trên máy nhà chưa mở"],
  ];
  for (const [r, chu] of BANG) {
    const { P, S, khung } = nap({ xuLy: bang({ "GET /api/v2/views/summary": r }) });
    const xong = P.pvViVe(khung, P.phien());
    await xa();
    assert.equal(S.hop.length, 1);
    assert.equal(tieuDeHop(S.hop[0]), "Lỗi");
    assert.ok(chuHop(S.hop[0]).includes("pv-hop-critical"));
    assert.ok(chuHop(S.hop[0]).includes(esc(chu)), chu);
    bamHop(S.hop[0], "ok");
    await xong;
  }
  const { P, S, khung } = nap({ xuLy: viApi({ "POST /api/v2/views/refresh": { status: 500, body: { detail: "scraper hỏng" } } }) });
  await P.pvViVe(khung, P.phien());
  bamKhung(khung, { pvvi: "lammoi" });
  await xa();
  assert.equal(S.hop.length, 1);
  assert.ok(chuHop(S.hop[0]).includes("HTTPError: 500: scraper hỏng"));
  assert.deepEqual(S.toasts, ["Đang fetch view counts..."]);
  assert.equal(goiApi(S).filter((g) => g === "GET /api/v2/views/summary").length, 1);
});

test("Views (d): XSS — product/folder/account/status/số từ API qua esc", async () => {
  const { P, khung } = nap({ xuLy: viApi({ "GET /api/v2/views/summary": ok({ items: [
    { product_id: BAN, folder_name: BAN, account_name: BAN, growth_status: BAN, status: BAN },
    { product_id: "x", folder_id: BAN, account_id: BAN }] }) }) });
  await P.pvViVe(khung, P.phien());
  khongCoBan(khung.innerHTML, "views");
  const { P: P2, S: S2, khung: k2 } = nap({ xuLy: viApi({ "POST /api/v2/views/refresh": ok({ rows: BAN }), "GET /api/v2/views/summary": { status: 500, body: { detail: BAN } } }) });
  const x = P2.pvViVe(k2, P2.phien());
  await xa();
  khongCoBan(chuHop(S2.hop[0]), "hộp lỗi views");
  bamHop(S2.hop[0], "ok");
  await x;
});

test("Views (e): rời trang giữa chừng → không vẽ đè, không hộp lỗi (kể cả khi lời gọi lỗi về muộn)", async () => {
  const d = hoan();
  const { P, S, khung } = nap({ xuLy: bang({ "GET /api/v2/views/summary": () => d.p }) });
  const xong = P.pvViVe(khung, P.phien());
  await xa();
  P.pvDung();
  khung.innerHTML = "TRANG KHAC";
  d.tra({ status: 500, body: { detail: "muộn" } });
  await xong;
  assert.equal(khung.innerHTML, "TRANG KHAC");
  assert.equal(S.hop.length, 0);
  // refresh đang chạy rồi rời trang → không toast kết quả, không tải lại
  const d2 = hoan();
  const { P: P2, S: S2, khung: k2 } = nap({ xuLy: viApi({ "POST /api/v2/views/refresh": () => d2.p }) });
  await P2.pvViVe(k2, P2.phien());
  bamKhung(k2, { pvvi: "lammoi" });
  await xa();
  P2.pvDung();
  d2.tra(ok({ rows: 3 }));
  await xa();
  assert.deepEqual(S2.toasts, ["Đang fetch view counts..."]);
  assert.equal(S2.goi.length, 2);
});

// ================= Logs =================
const LO_LOGS = [
  { id: 5, created_at: "2026-11-18T10:11:12.5", folder_name: "F1", account_name: "acc", video_filename: "v".repeat(60), product_id: "PROD1",
    status: "DONE", message: "" },
  { id: 6, timestamp: "2026-11-18T08:00:00", folder_id: 3, account_id: 9, status: "failed", message: "lỗi", error_details: "chi tiết" },
  { id: 7, status: "running" },
  { id: 8, status: null },
  { id: 9, status: "posted", message: "đã đăng" },
];
const loApi = (extra = {}) => bang({
  "GET /api/v2/queue/status": ok({ pending: 1, running: 0, done: 250, failed: 0 }),
  "GET /api/v2/logs/?limit=100&offset=0": ok(LO_LOGS),
  "GET /api/v2/logs/?limit=100&offset=100": ok(LO_LOGS.slice(0, 1)),
  "GET /api/v2/logs/?limit=100&offset=200": ok([]),
  ...extra,
});
const loDong = (h) => [...h.matchAll(/<tr data-pvlo="dong" data-pvlo-i="(\d+)"[^>]*>\s*<td>([^<]*)<\/td><td>([^<]*)<\/td><td>([^<]*)<\/td><td>([^<]*)<\/td>\s*<td title="([^"]*)">([^<]*)<\/td><td title="([^"]*)"[^>]*>([^<]*)<\/td>\s*<td([^>]*)>([^<]*)<\/td>/g)]
  .map((m) => ({ i: m[1], id: m[2], gio: m[3], folder: m[4], account: m[5], videoTip: m[6], video: m[7], product: m[9], stAttr: m[10], st: m[11] }));
const loTrang = (h) => (h.match(/<span style="font-weight:700;padding:0 14px">([^<]*)<\/span>/) || [])[1];

test("Logs (a): chữ nguyên văn logs.py — tiêu đề, 2 nút, 7 cột, phân trang + chữ trang khởi tạo; rỗng 'Chưa có log nào'", async () => {
  const d = hoan();
  const { P, khung } = nap({ xuLy: bang({ "GET /api/v2/queue/status": () => d.p, "GET /api/v2/logs/?limit=100&offset=0": () => d.p }) });
  P.pvLoVe(khung, P.phien());
  const h = khung.innerHTML;
  assert.match(h, /<h2[^>]*>📜 Logs<\/h2>/);
  assert.match(h, /class="btn" data-pvlo="thongke">📊 Thống kê đổi sản phẩm</);
  assert.match(h, /data-pvlo="lammoi">🔄 Refresh</);
  assert.deepEqual([...h.matchAll(/<th>([^<]+)<\/th>/g)].map((m) => m[1]), ["ID", "Thời gian", "Folder", "Tài khoản", "Video", "Sản phẩm", "Trạng thái"]);
  assert.match(h, /data-pvlo="truoc">◀ Trang trước</);
  assert.match(h, /data-pvlo="sau">Trang sau ▶</);
  assert.equal(loTrang(h), "Trang 1 / 1 (Tổng: 0 logs - 100/trang)");
  P.pvDung();
  const { P: P2, khung: k2 } = nap({ xuLy: loApi({ "GET /api/v2/logs/?limit=100&offset=0": ok([]) }) });
  await P2.pvLoVe(k2, P2.phien());
  assert.ok(k2.innerHTML.includes("Chưa có log nào") && k2.innerHTML.includes("📭"));
  assert.ok(!k2.innerHTML.includes("<table"));
});

test("Logs (b): status_counts + list_logs(100, 0); dòng bảng như _render (giờ, #id, video 50 ký tự, trạng thái + tooltip + màu)", async () => {
  const { P, S, khung } = nap({ xuLy: loApi() });
  await P.pvLoVe(khung, P.phien());
  assert.deepEqual(goiApi(S).sort(), ["GET /api/v2/logs/?limit=100&offset=0", "GET /api/v2/queue/status"]);
  const r = loDong(khung.innerHTML);
  assert.deepEqual(r.map((x) => [x.id, x.gio, x.folder, x.account, x.video, x.product, x.st]), [
    ["5", "2026-11-18 10:11:12", "F1", "acc", "v".repeat(50), "PROD1", "✅ Thành công"],
    ["6", "2026-11-18 08:00:00", "#3", "#9", "", "", "❌ Thất bại"],
    ["7", "", "", "", "", "", "⚡ Đang chạy"],
    ["8", "", "", "", "", "", "none"],
    ["9", "", "", "", "", "", "✅ Thành công"],
  ]);
  assert.equal(r[0].videoTip, "v".repeat(60));
  assert.match(r[0].stAttr, /title="Đăng video thành công"/);
  assert.match(r[1].stAttr, /title="lỗi\nchi tiết"/);
  assert.match(r[4].stAttr, /title="đã đăng"/);
  assert.match(r[0].stAttr, /color:var\(--ok\)/);
  assert.match(r[1].stAttr, /color:#d33a3a/);
  assert.match(r[2].stAttr, /color:#2f6fdb/);
  assert.equal(r[3].stAttr, "");
});

test("Logs (b): phân trang 100 — Tổng = pending+running+done+failed của queue/status (giữ như gốc), ◀/▶ đổi offset, nút tắt đúng chỗ", async () => {
  const { P, S, khung } = nap({ xuLy: loApi() });
  await P.pvLoVe(khung, P.phien());
  assert.equal(loTrang(khung.innerHTML), "Trang 1 / 3 (Tổng: 251 logs - 100/trang)");
  assert.match(khung.innerHTML, /data-pvlo="truoc" disabled>/);
  assert.equal(bamKhung(khung, { pvlo: "truoc" }), false, "◀ tắt ở trang 1");
  bamKhung(khung, { pvlo: "sau" });
  await xa();
  assert.ok(goiApi(S).includes("GET /api/v2/logs/?limit=100&offset=100"));
  assert.equal(loTrang(khung.innerHTML), "Trang 2 / 3 (Tổng: 251 logs - 100/trang)");
  bamKhung(khung, { pvlo: "sau" });
  await xa();
  assert.ok(goiApi(S).includes("GET /api/v2/logs/?limit=100&offset=200"));
  assert.equal(loTrang(khung.innerHTML), "Trang 3 / 3 (Tổng: 251 logs - 100/trang)");
  assert.match(khung.innerHTML, /data-pvlo="sau" disabled>/);
  bamKhung(khung, { pvlo: "truoc" });
  await xa();
  assert.equal(S.goi.filter((g) => g.url.endsWith("offset=100")).length, 2);
  // số lớn có dấu phẩy; queue/status rỗng → giữ nguyên
  const { P: P2, khung: k2 } = nap({ xuLy: loApi({ "GET /api/v2/queue/status": ok({ pending: 123000, running: 6, done: 450, failed: 0 }) }) });
  await P2.pvLoVe(k2, P2.phien());
  assert.equal(loTrang(k2.innerHTML), "Trang 1 / 1,235 (Tổng: 123,456 logs - 100/trang)");
  const { P: P3, khung: k3 } = nap({ xuLy: loApi({ "GET /api/v2/queue/status": ok({}) }) });
  await P3.pvLoVe(k3, P3.phien());
  assert.equal(loTrang(k3.innerHTML), "Trang 1 / 1 (Tổng: 0 logs - 100/trang)");
  assert.ok(!/data-pvlo="sau" disabled/.test(k3.innerHTML), "chưa có số đếm → nút giữ trạng thái mặc định (bật)");
});

test("Logs (b): bấm dòng → hộp 'Chi tiết log #<id>' — dòng thời gian (giờ, màu error/done, caption xuống dòng) hoặc câu log cũ; nút 'Đóng'", async () => {
  const TL = JSON.stringify([
    { at: "2026-11-18 10:00:01", step: "login", text: "Đăng nhập" },
    { at: "2026-11-18 10:00:05", step: "caption", text: "Caption", caption: "dòng 1\ndòng 2" },
    { at: "2026-11-18 10:00:09", step: "error", text: "Hỏng" },
    { at: "2026-11-18 10:00:10", step: "done", text: "Xong" },
    "rác", [1],
  ]);
  const ds = [{ id: 11, video_filename: "a.mp4", account_name: "acc", folder_name: "F", timeline: TL },
    { id: 12, created_at: "2026-11-18T07:00:00.123", message: "cũ", error_details: "trace" },
    { id: 13, timeline: "{hỏng" }];
  const { P, S, khung } = nap({ xuLy: loApi({ "GET /api/v2/logs/?limit=100&offset=0": ok(ds) }) });
  await P.pvLoVe(khung, P.phien());
  bamKhung(khung, { pvlo: "dong", pvloI: "0" });
  assert.equal(S.hop.length, 1);
  const h0 = chuHop(S.hop[0]);
  assert.equal(tieuDeHop(S.hop[0]), "Chi tiết log #11");
  assert.match(h0, /a\.mp4<br>Tài khoản: acc&nbsp;&nbsp;&nbsp;\|&nbsp;&nbsp;&nbsp;Folder: F/);
  assert.match(h0, /<span class="muted">2026-11-18 10:00:01<\/span> &nbsp;<span>Đăng nhập<\/span>/);
  assert.match(h0, /dòng 1<br>dòng 2/);
  assert.match(h0, /<span style="color:#d33a3a">Hỏng<\/span>/);
  assert.match(h0, /<span style="color:var\(--ok\)">Xong<\/span>/);
  assert.equal((h0.match(/<p style="margin:6px 0">/g) || []).length, 4, "chỉ phần tử dict của timeline");
  assert.match(h0, /data-pv-nut="dong">Đóng</);
  bamHop(S.hop[0], "dong");
  assert.equal(S.hop[0].daXoa, true);
  bamKhung(khung, { pvlo: "dong", pvloI: "1" });
  const h1 = chuHop(S.hop[1]);
  assert.equal(tieuDeHop(S.hop[1]), "Chi tiết log #12");
  assert.ok(h1.includes("<p>Log này được ghi trước khi có dòng thời gian chi tiết.</p><p>[2026-11-18 07:00:00] cũ</p>"));
  assert.match(h1, /<p style="color:#d33a3a">trace<\/p>/);
  bamKhung(khung, { pvlo: "dong", pvloI: "2" });
  assert.ok(chuHop(S.hop[2]).includes("Log này được ghi trước khi có dòng thời gian chi tiết."), "timeline hỏng → câu log cũ");
  assert.equal(S.goi.length, 2, "mở chi tiết không gọi API");
});

test("Logs (b): '📊 Thống kê đổi sản phẩm' → affiliate_stats (không tham số) → hộp đúng chữ: tổng, 3 thẻ hành động, bảng 4 cột, Đóng", async () => {
  const ST = { total: 12, by_action: { primary: 9, fallback: 2 }, recent: [
    { posted_at: "2026-11-18 10:00", product_id: "P1", action: "primary", fallback_from: null },
    { posted_at: "2026-11-18 11:00", product_id: "P2", action: "fallback", fallback_from: "P1" },
    { posted_at: "2026-11-18 12:00", product_id: "P3", action: "fallback_exhausted" },
    { product_id: "P4", action: null }] };
  const { P, S, khung } = nap({ xuLy: loApi({ "GET /api/v2/logs/affiliate-stats": ok(ST) }) });
  await P.pvLoVe(khung, P.phien());
  bamKhung(khung, { pvlo: "thongke" });
  bamKhung(khung, { pvlo: "thongke" });
  await xa();
  assert.equal(goiApi(S).filter((g) => g.includes("affiliate-stats")).length, 1, "bấm chồng → 1 lời gọi, 1 hộp");
  assert.equal(S.hop.length, 1);
  const h = chuHop(S.hop[0]);
  assert.equal(tieuDeHop(S.hop[0]), "📊 Thống kê đổi sản phẩm");
  assert.ok(h.includes("Tổng cộng: 12 lượt gắn sản phẩm"));
  const the = [...h.matchAll(/data-pvlo-hanh-dong="(\w+)"[^>]*>\s*<div[^>]*>([^<]+)<\/div><div style="color:([^;]+);[^"]*">([^<]*)<\/div>/g)].map((m) => [m[2], m[3], m[4]]);
  assert.deepEqual(the, [["primary", "var(--ok)", "9"], ["fallback", "#d98a00", "2"], ["fallback_exhausted", "#d33a3a", "0"]]);
  assert.ok(h.includes("Lịch sử gần đây (50 mục)"));
  assert.deepEqual([...h.matchAll(/<th>([^<]+)<\/th>/g)].map((m) => m[1]), ["Thời gian", "Product ID", "Action", "Fallback từ"]);
  const dong = [...h.matchAll(/<tr><td>([^<]*)<\/td><td>([^<]*)<\/td><td style="color:([^"]+)">([^<]*)<\/td><td>([^<]*)<\/td><\/tr>/g)].map((m) => m.slice(1));
  assert.deepEqual(dong, [
    ["2026-11-18 10:00", "P1", "var(--ok)", "primary", ""],
    ["2026-11-18 11:00", "P2", "#d98a00", "fallback", "P1"],
    ["2026-11-18 12:00", "P3", "#d33a3a", "fallback_exhausted", ""],
    ["", "P4", "var(--ok)", "None", ""],
  ]);
  assert.match(h, /data-pv-nut="dong">Đóng</);
  bamHop(S.hop[0], "dong");
  await xa();
  bamKhung(khung, { pvlo: "thongke" });
  await xa();
  assert.equal(S.hop.length, 2, "đóng hộp rồi bấm lại → mở hộp mới");
});

test("Logs (c): list_logs lỗi → hộp 'Lỗi' critical; status_counts lỗi → chỉ console; affiliate_stats lỗi → hộp 'Lỗi', không mở hộp thống kê", async () => {
  const { P, S, khung } = nap({ xuLy: loApi({ "GET /api/v2/logs/?limit=100&offset=0": { status: 500, body: { detail: "db khoá" } },
    "GET /api/v2/queue/status": { status: 404, body: { detail: "Not Found" } } }) });
  const xong = P.pvLoVe(khung, P.phien());
  await xa();
  assert.equal(S.hop.length, 1);
  assert.equal(tieuDeHop(S.hop[0]), "Lỗi");
  assert.ok(chuHop(S.hop[0]).includes("HTTPError: 500: db khoá") && chuHop(S.hop[0]).includes("pv-hop-critical"));
  assert.deepEqual(S.canhBao, ["status_counts error: API khong ton tai (404). Kiem tra backend co dang chay khong."]);
  bamHop(S.hop[0], "ok");
  await xong;
  const { P: P2, S: S2, khung: k2 } = nap({ xuLy: loApi({ "GET /api/v2/logs/affiliate-stats": { mang: true } }) });
  await P2.pvLoVe(k2, P2.phien());
  bamKhung(k2, { pvlo: "thongke" });
  await xa();
  assert.equal(S2.hop.length, 1);
  assert.equal(tieuDeHop(S2.hop[0]), "Lỗi");
  assert.ok(chuHop(S2.hop[0]).includes("Khong ket noi duoc backend. Hay kiem tra V2 Backend da chay chua."));
});

test("Logs (d): XSS — cột bảng, tooltip, hộp chi tiết (timeline JSON, caption, error_details), hộp thống kê", async () => {
  const TL = JSON.stringify([{ at: BAN, step: "caption", text: BAN, caption: BAN }, { at: "x", step: BAN, text: BAN }]);
  const ds = [{ id: BAN, created_at: BAN, folder_name: BAN, account_name: BAN, video_filename: BAN, product_id: BAN, status: BAN, message: BAN,
    error_details: BAN, timeline: TL },
  { id: 2, status: "failed", message: `"${BAN}`, error_details: BAN, video_filename: `"><b>`, created_at: BAN }];
  const ST = { total: BAN, by_action: { primary: BAN }, recent: [{ posted_at: BAN, product_id: BAN, action: BAN, fallback_from: BAN }] };
  const { P, S, khung } = nap({ xuLy: loApi({ "GET /api/v2/logs/?limit=100&offset=0": ok(ds), "GET /api/v2/logs/affiliate-stats": ok(ST) }) });
  await P.pvLoVe(khung, P.phien());
  khongCoBan(khung.innerHTML, "bảng logs");
  assert.ok(!khung.innerHTML.includes(`"><b>`), "thuộc tính title không bị phá");
  bamKhung(khung, { pvlo: "dong", pvloI: "0" });
  bamKhung(khung, { pvlo: "dong", pvloI: "1" });
  bamKhung(khung, { pvlo: "thongke" });
  await xa();
  assert.equal(S.hop.length, 3);
  for (const h of S.hop) khongCoBan(chuHop(h), "hộp logs");
});

test("Logs (e): rời trang giữa chừng → không vẽ đè, không hộp lỗi, không mở hộp thống kê muộn", async () => {
  const d = hoan(), d2 = hoan();
  const { P, S, khung } = nap({ xuLy: bang({ "GET /api/v2/queue/status": () => d2.p, "GET /api/v2/logs/?limit=100&offset=0": () => d.p }) });
  const xong = P.pvLoVe(khung, P.phien());
  await xa();
  P.pvDung();
  khung.innerHTML = "TRANG KHAC";
  d.tra({ status: 500, body: { detail: "muộn" } });
  d2.tra(ok({ done: 999 }));
  await xong;
  assert.equal(khung.innerHTML, "TRANG KHAC");
  assert.equal(S.hop.length, 0);
  const d3 = hoan();
  const { P: P2, S: S2, khung: k2 } = nap({ xuLy: loApi({ "GET /api/v2/logs/affiliate-stats": () => d3.p }) });
  await P2.pvLoVe(k2, P2.phien());
  bamKhung(k2, { pvlo: "thongke" });
  await xa();
  P2.pvDung();
  d3.tra(ok({ total: 1 }));
  await xa();
  assert.equal(S2.hop.length, 0);
});

// ================= Settings =================
const CFG = { default_engine: "camoufox", headless: "1", telegram_bot_token: "***", telegram_chat_id: "-100123", anthropic_api_key: "***" };
const TT = { backend: "http://127.0.0.1:8023", co_token: true, thu_muc: "E:\\tool\\tiktok_poster_v2", database: "E:\\tool\\tiktok_poster_v2\\v2_data.db",
  profiles: "E:\\tool\\tiktok_poster_v2\\profiles_v2" };
const seApi = (extra = {}) => bang({ "GET /api/v2/settings/": ok(CFG), "GET /_thong_tin": ok(TT),
  "PUT /api/v2/settings/default_engine": (r) => ok({ key: "default_engine", value: JSON.parse(r.body).value }),
  "PUT /api/v2/settings/headless": (r) => ok({ key: "headless", value: JSON.parse(r.body).value }),
  "PUT /api/v2/settings/telegram_bot_token": ok({ key: "telegram_bot_token", value: "***" }),
  "PUT /api/v2/settings/telegram_chat_id": (r) => ok({ key: "telegram_chat_id", value: JSON.parse(r.body).value }),
  ...extra });
const puts = (S) => S.goi.filter((g) => g.method === "PUT").map((g) => [g.url.slice(API.length), JSON.parse(g.body)]);

test("Settings (a): chữ nguyên văn settings.py — tiêu đề, phụ đề, 3 nhóm, nhãn, 4 engine, checkbox, 2 nút; ô token password; không có 'Bản quyền'", async () => {
  const { P, khung } = nap({ xuLy: seApi() });
  await P.pvSeVe(khung, P.phien());
  const h = khung.innerHTML;
  assert.match(h, /<h2[^>]*>Settings<\/h2>/);
  assert.ok(h.includes("Cấu hình engine, thông báo và thông tin hệ thống."));
  assert.deepEqual([...h.matchAll(/<h4>([^<]+)<\/h4>/g)].map((m) => m[1]), ["Browser Engine", "Telegram Notifications", "Architecture Info"]);
  assert.deepEqual([...h.matchAll(/<label for="[\w-]+">([^<]+)<\/label>/g)].map((m) => m[1]), ["Default engine:", "Bot Token:", "Chat ID:"]);
  assert.deepEqual(khung.querySelector("#pvse-engine").options, ["selenium", "camoufox", "donut", "cloak"]);
  assert.ok(h.includes("> Chạy headless (không hiển thị cửa sổ)</label>"));
  assert.match(h, /data-pvse="engine">Save Engine Settings</);
  assert.match(h, /data-pvse="telegram">Save Telegram Settings</);
  assert.match(h, /<input id="pvse-token" type="password"[^>]*placeholder="Bot Token \(ẩn khi đã lưu\)" value="">/);
  assert.match(h, /<input id="pvse-chat"[^>]*placeholder="Chat ID"/);
  assert.ok(!h.includes("Bản quyền") && !h.includes("Nhập key / Gia hạn"), "không vẽ nhóm Bản quyền");
});

test("Settings: tải → engine/headless/chat đổ vào form; token '***' (C1) KHÔNG vào ô, chỉ đổi placeholder; Architecture Info từ _thong_tin", async () => {
  const { P, S, khung } = nap({ xuLy: seApi() });
  await P.pvSeVe(khung, P.phien());
  assert.deepEqual(goiApi(S).sort(), ["GET /_thong_tin", "GET /api/v2/settings/"]);
  assert.equal(khung.querySelector("#pvse-engine").value, "camoufox");
  assert.equal(khung.querySelector("#pvse-headless").checked, true);
  const tk = khung.querySelector("#pvse-token");
  assert.equal(tk.value, "", "ô token luôn trống");
  assert.equal(tk.type, "password");
  assert.equal(tk.placeholder, "*** (đã lưu, nhập mới để thay)");
  assert.equal(khung.querySelector("#pvse-chat").value, "-100123");
  assert.equal(khung.querySelector("#pvse-info").innerHTML,
    esc("TikTok Poster V2\nThư mục dữ liệu: E:\\tool\\tiktok_poster_v2\nDatabase: E:\\tool\\tiktok_poster_v2\\v2_data.db\nProfiles: E:\\tool\\tiktok_poster_v2\\profiles_v2"));
  // Không có token / engine lạ / headless "0"
  const { P: P2, khung: k2 } = nap({ xuLy: seApi({ "GET /api/v2/settings/": ok({ default_engine: "chrome", headless: "0", telegram_bot_token: "" }) }) });
  await P2.pvSeVe(k2, P2.phien());
  assert.equal(k2.querySelector("#pvse-engine").value, "selenium", "findText < 0 → giữ lựa chọn");
  assert.equal(k2.querySelector("#pvse-headless").checked, false);
  assert.equal(k2.querySelector("#pvse-token").placeholder, "Bot Token");
  assert.equal(k2.querySelector("#pvse-chat").value, "");
  // headless phải đúng chuỗi "1" như gốc (config.get("headless","0") == "1")
  const { P: P3, khung: k3 } = nap({ xuLy: seApi({ "GET /api/v2/settings/": ok({ headless: true }) }) });
  await P3.pvSeVe(k3, P3.phien());
  assert.equal(k3.querySelector("#pvse-headless").checked, false);
});

test("Settings: Save Engine → PUT default_engine rồi PUT headless ('1'/'0') → hộp 'Đã lưu' / 'Engine settings saved.'; lỗi → hộp 'Lỗi', dừng chuỗi", async () => {
  const { P, S, khung } = nap({ xuLy: seApi() });
  await P.pvSeVe(khung, P.phien());
  khung.querySelector("#pvse-engine").value = "donut";
  khung.querySelector("#pvse-headless").checked = false;
  bamKhung(khung, { pvse: "engine" });
  bamKhung(khung, { pvse: "engine" });
  await xa();
  assert.deepEqual(puts(S), [["/api/v2/settings/default_engine", { value: "donut" }], ["/api/v2/settings/headless", { value: "0" }]]);
  assert.equal(S.hop.length, 1);
  assert.equal(tieuDeHop(S.hop[0]), "Đã lưu");
  assert.ok(chuHop(S.hop[0]).includes("Engine settings saved.") && chuHop(S.hop[0]).includes("pv-hop-info"));
  bamHop(S.hop[0], "ok");
  await xa();
  const { P: P2, S: S2, khung: k2 } = nap({ xuLy: seApi({ "PUT /api/v2/settings/default_engine": { status: 500, body: { detail: "db" } } }) });
  await P2.pvSeVe(k2, P2.phien());
  bamKhung(k2, { pvse: "engine" });
  await xa();
  assert.deepEqual(puts(S2), [["/api/v2/settings/default_engine", { value: "camoufox" }]], "lỗi bước 1 → không PUT headless");
  assert.equal(tieuDeHop(S2.hop[0]), "Lỗi");
  assert.ok(chuHop(S2.hop[0]).includes("HTTPError: 500: db") && chuHop(S2.hop[0]).includes("pv-hop-critical"));
});

test("Settings: Save Telegram — trống cả hai → 'Không có gì để lưu'; chỉ gửi khoá có chữ (strip); token+chat theo thứ tự; lưu xong xoá ô token, placeholder '*** (đã lưu)'", async () => {
  // dữ liệu tải có telegram_bot_token "***" → bấm lưu với ô token trống KHÔNG BAO GIỜ gửi "***"
  const { P, S, khung } = nap({ xuLy: seApi({ "GET /api/v2/settings/": ok({ ...CFG, telegram_chat_id: "" }) }) });
  await P.pvSeVe(khung, P.phien());
  khung.querySelector("#pvse-token").value = "   ";
  bamKhung(khung, { pvse: "telegram" });
  await xa();
  assert.deepEqual(puts(S), []);
  assert.equal(tieuDeHop(S.hop[0]), "Không có gì để lưu");
  assert.ok(chuHop(S.hop[0]).includes("Chưa nhập token hoặc chat ID."));
  bamHop(S.hop[0], "ok");
  await xa();

  const BANG = [
    [" 123:abc ", " -99 ", [["/api/v2/settings/telegram_bot_token", { value: "123:abc" }], ["/api/v2/settings/telegram_chat_id", { value: "-99" }]]],
    ["tok", "", [["/api/v2/settings/telegram_bot_token", { value: "tok" }]]],
    ["", "-55", [["/api/v2/settings/telegram_chat_id", { value: "-55" }]]],
  ];
  for (const [tok, chat, mong] of BANG) {
    const { P: Px, S: Sx, khung: kx } = nap({ xuLy: seApi() });
    await Px.pvSeVe(kx, Px.phien());
    kx.querySelector("#pvse-token").value = tok;
    kx.querySelector("#pvse-chat").value = chat;
    bamKhung(kx, { pvse: "telegram" });
    await xa();
    assert.deepEqual(puts(Sx), mong, `${tok}|${chat}`);
    assert.ok(!Sx.goi.some((g) => g.body && g.body.includes("***")), "không bao giờ gửi '***'");
    assert.equal(tieuDeHop(Sx.hop[0]), "Đã lưu");
    assert.ok(chuHop(Sx.hop[0]).includes("Telegram settings saved."));
    assert.equal(kx.querySelector("#pvse-token").value, tok, "ô token xoá SAU khi đóng hộp (như QMessageBox chặn)");
    bamHop(Sx.hop[0], "ok");
    await xa();
    assert.equal(kx.querySelector("#pvse-token").value, "");
    assert.equal(kx.querySelector("#pvse-token").placeholder, "*** (đã lưu)");
    assert.equal(kx.querySelector("#pvse-chat").value, chat, "ô Chat ID giữ nguyên");
  }
  // lỗi PUT token → hộp Lỗi, không PUT chat, ô token giữ
  const { P: P2, S: S2, khung: k2 } = nap({ xuLy: seApi({ "PUT /api/v2/settings/telegram_bot_token": { status: 422, body: { detail: [{ msg: "x" }] } } }) });
  await P2.pvSeVe(k2, P2.phien());
  k2.querySelector("#pvse-token").value = "t";
  k2.querySelector("#pvse-chat").value = "c";
  bamKhung(k2, { pvse: "telegram" });
  await xa();
  assert.deepEqual(puts(S2), [["/api/v2/settings/telegram_bot_token", { value: "t" }]]);
  assert.equal(tieuDeHop(S2.hop[0]), "Lỗi");
  assert.ok(chuHop(S2.hop[0]).includes(esc(`HTTPError: 422: [{"msg":"x"}]`)));
  assert.equal(k2.querySelector("#pvse-token").value, "t");
});

test("Settings (c): tải lỗi → chỉ console 'Settings load failed: …' (logger.warning), không hộp; _thong_tin lỗi → Architecture Info để trống", async () => {
  const { P, S, khung } = nap({ xuLy: seApi({ "GET /api/v2/settings/": { status: 502, body: { loi: "Poster V2 trên máy nhà chưa mở" } },
    "GET /_thong_tin": { status: 502, body: { loi: "tắt" } } }) });
  await P.pvSeVe(khung, P.phien());
  assert.equal(S.hop.length, 0);
  assert.ok(S.canhBao.includes("Settings load failed: 502: Poster V2 trên máy nhà chưa mở"));
  assert.equal(khung.querySelector("#pvse-token").placeholder, "Bot Token (ẩn khi đã lưu)");
  assert.ok(khung.innerHTML.includes(esc("TikTok Poster V2\nThư mục dữ liệu: \nDatabase: \nProfiles: ")));
});

test("Settings (d): XSS — _thong_tin và lỗi trong hộp qua esc", async () => {
  const { P, S, khung } = nap({ xuLy: seApi({ "GET /_thong_tin": ok({ thu_muc: BAN, database: BAN, profiles: BAN }),
    "PUT /api/v2/settings/default_engine": { status: 400, body: { detail: BAN } } }) });
  await P.pvSeVe(khung, P.phien());
  khongCoBan(khung.querySelector("#pvse-info").innerHTML, "Architecture Info");
  bamKhung(khung, { pvse: "engine" });
  await xa();
  khongCoBan(chuHop(S.hop[0]), "hộp lỗi settings");
});

test("Settings (e): rời trang giữa chừng → không đổ dữ liệu vào form, không hộp lỗi/hộp đã lưu", async () => {
  const d = hoan();
  const { P, S, khung } = nap({ xuLy: seApi({ "GET /api/v2/settings/": () => d.p }) });
  const xong = P.pvSeVe(khung, P.phien());
  await xa();
  const chat = khung.querySelector("#pvse-chat");
  P.pvDung();
  d.tra(ok(CFG));
  await xong;
  assert.equal(chat.value, "");
  assert.equal(S.hop.length, 0);
  const d2 = hoan();
  const { P: P2, S: S2, khung: k2 } = nap({ xuLy: seApi({ "PUT /api/v2/settings/headless": () => d2.p }) });
  await P2.pvSeVe(k2, P2.phien());
  bamKhung(k2, { pvse: "engine" });
  await xa();
  P2.pvDung();
  d2.tra({ status: 500, body: { detail: "muộn" } });
  await xa();
  assert.equal(S2.hop.length, 0);
});
