// Test W-P3: Poster V2 › Accounts (web/pv-accounts.js) + Đăng bài (web/pv-post.js).
// Thiết kế: docs/poster-v2-tren-web.md §3.3, §5.1, §5.3, §6.3–§6.5, §9 W-P3. Nguồn: tiktok_poster_v2/src/desktop/pages/{accounts,post}.py.
// Không mạng: globalThis.fetch bị thay bằng hàm ném lỗi TRƯỚC khi nạp mã; các trang nhận fetch giả qua tham số (nạp kèm web/poster.js THẬT).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

globalThis.fetch = async (url) => { throw new Error(`fetch thật bị cấm trong test: ${url}`); };

const doc = (p) => readFileSync(new URL(`../../web/${p}`, import.meta.url), "utf8");
const APP = doc("app.js");
const POSTER = doc("poster.js");
const AC = doc("pv-accounts.js");
const PO = doc("pv-post.js");
const dong = (src, dau) => {
  const l = src.split("\n").find((x) => x.startsWith(dau));
  assert.ok(l, `không thấy dòng bắt đầu bằng "${dau}"`);
  return l;
};
const esc = new Function(`${dong(APP, "const esc = ")}\nreturn esc;`)();
const BAN = `<img src=x onerror=alert(1)>`;
const CHO = "0123456789abcdef0123456789abcdef";
const CHO2 = "fedcba9876543210fedcba9876543210";
const LOGIN = "🔓 Tạo profile & Login lấy cookies (tự động)";
const LOGIN_DANG = "Đang mở Chrome... Hãy đăng nhập TikTok trên trình duyệt";
const NHAC = "Cần người ngồi ở máy nhà để đăng nhập trên Chrome vừa mở";
const re = (x) => esc(x).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); // chuỗi (đã esc như trong HTML) → mẫu regex

const xa = async () => { for (let i = 0; i < 40; i++) await new Promise((r) => setImmediate(r)); };

// Đồng hồ giả (như poster-web.test.mjs): setTimeout/setInterval/Date.now chỉ chạy khi gọi tien(ms).
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

// DOM giả tối thiểu: innerHTML là chuỗi; querySelector('[attr="v"]') trả phần tử con (tạo lười) nếu innerHTML có attr="v".
function phanTu() {
  const el = {
    _html: "", datHtml: false, con: new Map(), nghe: {}, dataset: {}, value: "", checked: false, disabled: false, files: null,
    soClick: 0, open: false, daXoa: false, className: "",
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = String(v); this.datHtml = true; this.con.clear(); },
    addEventListener(ev, f) { (this.nghe[ev] ||= []).push(f); },
    querySelector(sel) {
      const m = /^\[([\w-]+)="([^"]*)"\]$/.exec(sel);
      if (!m || !this._html.includes(`${m[1]}="${m[2]}"`)) return null;
      if (!this.con.has(sel)) this.con.set(sel, phanTu());
      return this.con.get(sel);
    },
    click() { this.soClick++; }, showModal() { this.open = true; }, close() { this.open = false; }, remove() { this.daXoa = true; },
  };
  return el;
}
// Nội dung một vùng: con đã được vẽ lại thì lấy của con, chưa thì lấy của cha.
const vung = (el, sel) => { const c = el.con.get(sel); return c && c.datHtml ? c.innerHTML : el.innerHTML; };
const phat = (el, type, target) => { for (const f of el.nghe[type] || []) f({ type, target, preventDefault() {} }); };
const bam = (el, attr, dataset) => phat(el, "click", { closest: (s) => (s === `[${attr}]` ? { dataset } : null) });
const nhap = (el, type, dataset, extra) => phat(el, type, { dataset, ...extra });
const traLoi = (hop, ma) => phat(hop, "click", { closest: (s) => (s === "[data-pv-nut]" ? { dataset: { pvNut: ma } } : null) });
const tieuDe = (h) => (/<h3 class="pv-hop-tieu-de">([\s\S]*?)<\/h3>/.exec(h.innerHTML) || [])[1];
const cauHop = (h) => (/<p class="pv-cau[^"]*"><span class="pv-ic" aria-hidden="true">[^<]*<\/span> ([\s\S]*?)<\/p>/.exec(h.innerHTML) || [])[1];

// Nạp poster.js THẬT + 2 trang với môi trường giả. xuLy(method, duong, body) → { status, body } | { mang: true } | undefined (ném).
function nap(xuLy) {
  const S = { goi: [], hop: [], log: [], docTep: [] };
  const clock = dongHoGia();
  const auth = { user: "nhan", ten: "nhan", get on() { return !!this.user; } };
  const app = phanTu();
  const $ = (s) => (s === "#app" ? app : app.querySelector(s));
  const document = { hidden: false, body: { append(el) { S.hop.push(el); } }, createElement: () => phanTu() };
  const fetch = async (url, opt = {}) => {
    assert.ok(String(url).startsWith("/api/poster/"), `URL lạ: ${url}`);
    const duong = String(url).slice("/api/poster".length);
    const method = opt.method || "GET";
    const body = opt.body === undefined ? undefined : JSON.parse(opt.body);
    S.goi.push({ method, duong, body });
    const r = xuLy ? await xuLy(method, duong, body) : undefined;
    if (!r) throw new Error(`fetch thật bị cấm trong test: ${url}`);
    if (r.mang) throw new TypeError("Failed to fetch");
    const txt = r.body === undefined ? "" : JSON.stringify(r.body);
    return { status: r.status, ok: r.status >= 200 && r.status < 300, text: async () => txt };
  };
  class FileReader {
    constructor() { this.nghe = {}; this.result = null; }
    addEventListener(ev, f) { this.nghe[ev] = f; }
    readAsText(f) {
      S.docTep.push(f);
      Promise.resolve().then(() => { if (f.loi) this.nghe.error && this.nghe.error(); else { this.result = f.noiDung; this.nghe.load && this.nghe.load(); } });
    }
  }
  const ns = {
    esc, $, document, auth, fetch, FileReader, mnCHUA_CO: "CHUA_CO",
    console: { error: (...a) => S.log.push(a.join(" ")), log: (...a) => S.log.push(a.join(" ")) },
    renderUser: () => {}, openLogin: () => {}, toast: () => {},
    setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout, setInterval: clock.setInterval, clearInterval: clock.clearInterval,
    Date: { now: () => clock.now },
  };
  const ten = Object.keys(ns);
  const P = new Function(...ten, `${POSTER}\n;\n${AC}\n;\n${PO}
return { pvAcVe, pvPoVe, pvDung, pvConSong, pvApi, phien: () => pvPhien,
  pvacVanTay, pvacMauSucKhoe, pvacTenTep, pvacDangCooldown, pvacDuLieu, pvacLenhLogin, pvacTheHtml,
  pvpoMb, pvpoDongVideo, pvpoCauXacNhan, pvpoLenhDang, pvpoLenhKhop, pvpoTenTep, pvpoDsVideo, pvpoTenFolder };`)(...ten.map((k) => ns[k]));
  const goi = (m, d) => S.goi.filter((g) => g.method === m && g.duong === d);
  const hopMo = () => S.hop.filter((h) => !h.daXoa);
  const hopCuoi = () => hopMo()[hopMo().length - 1];
  return { P, S, clock, goi, hopMo, hopCuoi };
}

// ======================= Accounts =======================
const ACC = [
  { id: 1, name: "acc1", cookies_path: "E:\\ck\\acc1.json", proxy: "http://user:pass@1.2.3.4:8080/xyz", active: 1, campaign_hashtags: "#a", chrome_profile_dir: "E:/p/acc1", fingerprint: null },
  { id: 2, name: "acc2", cookies_path: "", proxy: "", active: 0, fingerprint: JSON.stringify({ seed: 7, screen: { width: 1920, height: 1080 }, hardware_concurrency: 8, device_memory: 8, webgl: { vendor: "Google Inc.", renderer: "ANGLE (NVIDIA)" } }) },
];
const HEALTH = { 1: { health_score: 85, posts_today: 3, success_rate: 96.6, in_cooldown: false }, 2: { health_score: 45, posts_today: 0, success_rate: 50, in_cooldown: true } };

// Backend giả mặc định cho Accounts; ghiDe(method, duong, body) trả trước nếu khác undefined.
function mayAc(ghiDe = () => undefined, { acc = ACC, health = HEALTH, dangChay = [] } = {}) {
  return (m, d, b) => {
    const r = ghiDe(m, d, b);
    if (r !== undefined) return r;
    if (m === "GET" && d === "/_kq") return { status: 200, body: { dang_chay: dangChay } };
    if (m === "GET" && d === "/api/v2/system/health") return { status: 200, body: { status: "ok" } };
    if (m === "GET" && d === "/_thong_tin") return { status: 200, body: { backend: "http://127.0.0.1:1" } };
    if (m === "GET" && d === "/api/v2/accounts/") return { status: 200, body: acc };
    const h = /^\/api\/v2\/views\/health\/(\d+)$/.exec(d);
    if (m === "GET" && h) return health[h[1]] ? { status: 200, body: health[h[1]] } : { status: 500, body: { detail: "x" } };
    return undefined;
  };
}
async function moAc(xuLy) {
  const x = nap(xuLy);
  const khung = phanTu();
  const cho = x.P.pvAcVe(khung, x.P.phien());
  await xa();
  return { ...x, khung, cho };
}
const moHopThem = (x) => { bam(x.khung, "data-pvac-nut", { pvacNut: "them" }); return x.hopCuoi(); };
const oHop = (h, ma, gt) => nhap(h, "input", { pvacO: ma }, { value: gt });
const nutHop = (h, nut) => bam(h, "data-pvac-nut", { pvacNut: nut });

test("Accounts (a): chữ nguyên văn accounts.py — thanh trên, thẻ account, huy hiệu, nút, trang rỗng", async () => {
  const x = await moAc(mayAc());
  const t = x.khung.innerHTML;
  assert.match(t, />TikTok Accounts</);
  assert.match(t, /data-pvac-nut="don">🧹 Dọn cache profile</);
  assert.match(t, /data-pvac-nut="lammoi">↻ Refresh</);
  assert.match(t, /data-pvac-nut="them">\+ Add Account</);
  assert.deepEqual(x.S.goi.map((g) => `${g.method} ${g.duong}`).filter((s) => !/health$|thong_tin/.test(s)),
    ["GET /_kq", "GET /api/v2/accounts/", "GET /api/v2/views/health/1", "GET /api/v2/views/health/2"]);
  const ds = vung(x.khung, '[data-pvac-vung="ds"]');
  assert.match(ds, />🟢 acc1</);
  assert.match(ds, />🔴 acc2</);
  assert.match(ds, />🍪 acc1\.json</);
  assert.match(ds, />🍪 chưa có cookies</);
  assert.match(ds, /background-color:#22c55e;[^>]*>🛡️ Health: 85\/100</);
  assert.match(ds, /background-color:#f97316;[^>]*>🛡️ Health: 45\/100</);
  assert.match(ds, />📅 3 bài\/ngày</);
  assert.match(ds, />✅ 97% thành công</);
  assert.match(ds, />🌐 http:\/\/user:pass@1\.2\.\.\.</,"proxy cắt 20 ký tự + '...'");
  assert.equal((ds.match(/🌐/g) || []).length, 1, "proxy rỗng không có huy hiệu");
  assert.match(ds, /data-pvac-nut="cd" data-pvac-id="1">🛡️ Cooldown</);
  assert.match(ds, /data-pvac-nut="cd" data-pvac-id="2">🛡️ Bỏ Cooldown</);
  assert.match(ds, /data-pvac-nut="check" data-pvac-id="1">Check</);
  assert.match(ds, /data-pvac-nut="sua" data-pvac-id="1">✏️ Edit</);
  assert.match(ds, /data-pvac-nut="xoa" data-pvac-id="1" aria-label="Xóa">🗑️</);
  const y = await moAc(mayAc(undefined, { acc: [] }));
  assert.match(vung(y.khung, '[data-pvac-vung="ds"]'), /📭[\s\S]*Chưa có account nào\. Bấm &#39;\+ Add Account&#39; để thêm\./);
});

test("Accounts thuần: vân tay (parse_fingerprint+summarize), màu health, tên file cookie, cooldown, get_data, lệnh login", () => {
  const { P } = nap();
  const fp = { seed: 1, screen: { width: "1366", height: 768 }, hardware_concurrency: 4, device_memory: 8, webgl: { vendor: "v", renderer: "R" } };
  assert.equal(P.pvacVanTay(JSON.stringify(fp)), "1366x768, 4 luồng, R");
  assert.equal(P.pvacVanTay(fp), "1366x768, 4 luồng, R");
  assert.equal(P.pvacVanTay(null), "máy thật");
  assert.equal(P.pvacVanTay("{hỏng"), "lỗi dữ liệu vân tay");
  assert.equal(P.pvacVanTay({ ...fp, screen: { width: 1366, height: 40 } }), "lỗi dữ liệu vân tay", "height <= _TASKBAR_PX");
  assert.equal(P.pvacVanTay({ ...fp, webgl: { renderer: "R" } }), "lỗi dữ liệu vân tay", "thiếu vendor = KeyError");
  assert.equal(P.pvacVanTay({ ...fp, seed: "x" }), "lỗi dữ liệu vân tay");
  assert.equal(P.pvacVanTay([1]), "lỗi dữ liệu vân tay");
  assert.deepEqual([80, 79, 60, 59, 40, 39].map(P.pvacMauSucKhoe), ["#22c55e", "#eab308", "#eab308", "#f97316", "#f97316", "#ef4444"]);
  assert.equal(P.pvacTenTep("E:\\a\\b\\c.json"), "c.json");
  assert.equal(P.pvacTenTep("E:/a/b/"), "b");
  assert.equal(P.pvacTenTep("C:"), "");
  assert.equal(P.pvacDangCooldown({ in_cooldown: false, cooldown_active: true }), false, "in_cooldown có mặt thì dùng in_cooldown");
  assert.equal(P.pvacDangCooldown({ cooldown_active: true }), true);
  assert.equal(P.pvacDangCooldown({}), false);
  assert.deepEqual(P.pvacDuLieu({ name: " a ", cookies_path: " c ", profile: " p ", proxy: " x ", tags: " #t ", active: true, fp: false }),
    { name: "a", cookies_path: "c", chrome_profile_dir: "p", proxy: "x", campaign_hashtags: "#t", active: true, use_fingerprint: false });
  assert.deepEqual(P.pvacLenhLogin({ dang_chay: [{ cho: CHO2, method: "POST", path: "/api/v2/post/direct" },
    { cho: CHO, method: "POST", path: "/api/v2/accounts/login_and_capture", toi_da_giay: 360, tom_tat: { name: "acc9" } }] }),
  { cho: CHO, toiDa: 360, ten: "acc9" });
  assert.equal(P.pvacLenhLogin({ dang_chay: [] }), null);
  assert.equal(P.pvacLenhLogin(null), null);
});

test("Accounts (b): Cooldown / Bỏ Cooldown / Check / 🧹 / ↻ → đúng lời gọi pvApi rồi làm mới; hộp đúng chữ", async () => {
  const x = await moAc(mayAc((m, d) => {
    if (m === "POST" && d === "/api/v2/accounts/1/cooldown") return { status: 200, body: { status: "ok" } };
    if (m === "DELETE" && d === "/api/v2/accounts/2/cooldown") return { status: 200, body: { status: "ok" } };
    if (m === "POST" && d === "/api/v2/accounts/1/test-cookies") return { status: 200, body: { status: "ok", message: "Found 9 cookies, 3 essential" } };
    if (m === "POST" && d === "/api/v2/accounts/2/test-cookies") return { status: 200, body: { status: "invalid", message: "No cookies file found" } };
    if (m === "POST" && d === "/api/v2/accounts/clean_profiles") return { status: 200, body: { status: "ok", cleaned_caches: 4, freed_mb: 12.5 } };
    return undefined;
  }));
  const soTai = () => x.goi("GET", "/api/v2/accounts/").length;
  bam(x.khung, "data-pvac-nut", { pvacNut: "cd", pvacId: "1" });
  await xa();
  assert.deepEqual(x.goi("POST", "/api/v2/accounts/1/cooldown")[0].body, { hours: 24 });
  assert.equal(soTai(), 2, "làm mới sau cooldown");
  bam(x.khung, "data-pvac-nut", { pvacNut: "cd", pvacId: "2" });
  await xa();
  assert.equal(x.goi("DELETE", "/api/v2/accounts/2/cooldown").length, 1);
  assert.equal(soTai(), 3);

  bam(x.khung, "data-pvac-nut", { pvacNut: "check", pvacId: "1" });
  await xa();
  let h = x.hopCuoi();
  assert.equal(tieuDe(h), "Kiểm tra cookies");
  assert.equal(cauHop(h), esc("✅ Cookies hợp lệ!\nFound 9 cookies, 3 essential"));
  assert.equal(soTai(), 3, "desktop làm mới SAU khi đóng hộp");
  traLoi(h, "ok");
  await xa();
  assert.equal(soTai(), 4);
  bam(x.khung, "data-pvac-nut", { pvacNut: "check", pvacId: "2" });
  await xa();
  h = x.hopCuoi();
  assert.match(h.innerHTML, /pv-hop-warning/);
  assert.equal(cauHop(h), esc("⚠️ Cookies cảnh báo: No cookies file found"));
  traLoi(h, "ok");
  await xa();

  bam(x.khung, "data-pvac-nut", { pvacNut: "don" });
  await xa();
  h = x.hopCuoi();
  assert.equal(tieuDe(h), "Dọn dẹp");
  assert.equal(cauHop(h), "Đã dọn dẹp 4 thư mục cache rác, giải phóng 12.5 MB.");
  traLoi(h, "ok");
  const truoc = soTai();
  bam(x.khung, "data-pvac-nut", { pvacNut: "lammoi" });
  await xa();
  assert.equal(soTai(), truoc + 1);
});

test("Accounts (b): 🗑️ hỏi confirm_destructive 'Xóa tài khoản '<tên>'?' — Hủy không gọi gì; Xóa → DELETE rồi làm mới", async () => {
  const x = await moAc(mayAc((m, d) => (m === "DELETE" && d === "/api/v2/accounts/1" ? { status: 200, body: { status: "ok" } } : undefined)));
  bam(x.khung, "data-pvac-nut", { pvacNut: "xoa", pvacId: "1" });
  await xa();
  let h = x.hopCuoi();
  assert.equal(tieuDe(h), "Xác nhận");
  assert.equal(cauHop(h), esc("Xóa tài khoản 'acc1'?"));
  assert.match(h.innerHTML, /data-pv-nut="co">Xóa</);
  assert.match(h.innerHTML, /data-pv-nut="khong">Hủy</);
  traLoi(h, "khong");
  await xa();
  assert.equal(x.goi("DELETE", "/api/v2/accounts/1").length, 0);
  bam(x.khung, "data-pvac-nut", { pvacNut: "xoa", pvacId: "1" });
  await xa();
  traLoi(x.hopCuoi(), "co");
  await xa();
  assert.equal(x.goi("DELETE", "/api/v2/accounts/1").length, 1);
  assert.equal(x.goi("GET", "/api/v2/accounts/").length, 2);
  bam(x.khung, "data-pvac-nut", { pvacNut: "xoa", pvacId: "../9" });
  await xa();
  assert.equal(x.hopMo().length, 0, "id lạ không khớp account nào → không làm gì");
});

test("Accounts (a)(b): hộp Thêm Account đủ ô + chữ nguyên văn; dòng nhắc NGAY dưới nút login; Lưu → createAccount(get_data) rồi làm mới", async () => {
  const x = await moAc(mayAc((m, d) => (m === "POST" && d === "/api/v2/accounts/" ? { status: 200, body: { id: 3 } } : undefined)));
  const h = moHopThem(x);
  const t = h.innerHTML;
  assert.equal(tieuDe(h), "Thêm Account");
  for (const [nhan, ph] of [["Tên Account:", "Tên account (vd: acc_tiktok_01)"], ["File Cookies (.json):", "Đường dẫn file cookies .json"],
    ["Chrome Profile Dir:", "Thư mục profile riêng (tùy chọn)"], ["Proxy (HTTP/SOCKS5):", "http://user:pass@ip:port"],
    ["Campaign Hashtags:", "#campaign #affiliate #shop"]]) {
    assert.ok(t.includes(`>${nhan}</label>`), nhan);
    assert.ok(t.includes(`placeholder="${esc(ph)}"`), ph);
  }
  assert.ok(t.includes(">Paste JSON Cookie:</label>"));
  assert.ok(t.includes(`placeholder="${esc("HOẶC Dán trực tiếp nội dung cookies JSON vào đây (từ tiện ích mở rộng Cookie-Editor)...")}"`));
  assert.match(t, /data-pvac-nut="browse">Browse\.\.\.</);
  assert.match(t, /<input type="file" data-pvac-o="tep" accept="\.json,application\/json" hidden>/);
  assert.match(t, /data-pvac-o="active" checked> Account đang hoạt động \(Active\)</);
  assert.match(t, /data-pvac-o="fp"> Dùng vân tay trình duyệt riêng \(account phụ, cố định\)</);
  assert.ok(t.includes(`title="${esc("Tạo 1 lần rồi giữ nguyên: màn hình, CPU, GPU, nhiễu canvas/audio.\nBỏ trống cho account chính (dùng thông số máy thật).")}"`));
  assert.ok(!t.includes("Vân tay hiện tại"));
  assert.match(t, new RegExp(`data-pvac-nut="login">${re(LOGIN)}</button>\\s*<p class="pv-nho pvac-nhac"[^>]*>${re(NHAC)}</p>`),
    "nút login giữ chữ gốc; dòng nhắc nguyên văn ngay dưới nút");
  assert.match(t, /data-pvac-nut="luu">Lưu Account<\/button><button type="button" class="btn ghost" data-pvac-nut="huy">Hủy</);
  nutHop(h, "huy");
  assert.ok(h.daXoa, "Hủy đóng hộp");
  const h2 = moHopThem(x);
  oHop(h2, "name", "  acc_moi ");
  oHop(h2, "cookies_path", "E:/ck/m.json");
  oHop(h2, "profile", "E:/p/m");
  oHop(h2, "proxy", "socks5://1.1.1.1:1");
  oHop(h2, "tags", "#x");
  nhap(h2, "change", { pvacO: "active" }, { checked: false });
  nhap(h2, "change", { pvacO: "fp" }, { checked: true });
  nutHop(h2, "luu");
  await xa();
  assert.ok(h2.daXoa, "đóng hộp");
  assert.deepEqual(x.goi("POST", "/api/v2/accounts/")[0].body, { name: "acc_moi", cookies_path: "E:/ck/m.json", chrome_profile_dir: "E:/p/m",
    proxy: "socks5://1.1.1.1:1", campaign_hashtags: "#x", active: false, use_fingerprint: true });
  assert.equal(x.goi("GET", "/api/v2/accounts/").length, 2);
  // Tên trống → "Lỗi" / "Tên account không được để trống.", không gọi gì, hộp vẫn mở.
  const h3 = moHopThem(x);
  nutHop(h3, "luu");
  await xa();
  const loi = x.hopCuoi();
  assert.equal(tieuDe(loi), "Lỗi");
  assert.equal(cauHop(loi), "Tên account không được để trống.");
  assert.match(loi.innerHTML, /pv-hop-warning/);
  traLoi(loi, "ok");
  await xa();
  assert.ok(!h3.daXoa);
  assert.equal(x.goi("POST", "/api/v2/accounts/").length, 1);
  nutHop(h3, "huy");
  assert.ok(h3.daXoa, "Hủy đóng hộp");
});

test("Accounts (b): Edit điền sẵn; có vân tay → 'Vân tay hiện tại'; bỏ tick → hỏi 'Bỏ vân tay riêng?' No = không gọi, Yes = updateAccount", async () => {
  const x = await moAc(mayAc((m, d) => (m === "PUT" && d === "/api/v2/accounts/2" ? { status: 200, body: { id: 2 } } : undefined)));
  bam(x.khung, "data-pvac-nut", { pvacNut: "sua", pvacId: "2" });
  const h = x.hopCuoi();
  assert.equal(tieuDe(h), "Sửa Account");
  assert.match(h.innerHTML, /data-pvac-o="name" value="acc2"/);
  assert.match(h.innerHTML, /data-pvac-o="active"> Account/, "active=0 → không tick");
  assert.match(h.innerHTML, /data-pvac-o="fp" checked>/);
  assert.match(h.innerHTML, />Vân tay hiện tại: 1920x1080, 8 luồng, ANGLE \(NVIDIA\)</);
  nhap(h, "change", { pvacO: "fp" }, { checked: false });
  nutHop(h, "luu");
  await xa();
  let q = x.hopCuoi();
  assert.equal(tieuDe(q), "Bỏ vân tay riêng?");
  assert.equal(cauHop(q), esc("Account này sẽ chuyển sang thông số máy thật - với TikTok là đổi sang thiết bị khác.\n"
    + "Bật lại sau sẽ ra bộ vân tay MỚI, không lấy lại được bộ cũ.\n\nTiếp tục?"));
  assert.match(q.innerHTML, /data-pv-nut="yes">Yes<\/button><button type="button" class="btn ghost" data-pv-nut="no">No</);
  traLoi(q, "no");
  await xa();
  assert.equal(x.goi("PUT", "/api/v2/accounts/2").length, 0);
  assert.ok(!h.daXoa);
  nutHop(h, "luu");
  await xa();
  q = x.hopCuoi();
  traLoi(q, "yes");
  await xa();
  assert.deepEqual(x.goi("PUT", "/api/v2/accounts/2")[0].body, { name: "acc2", cookies_path: "", chrome_profile_dir: "", proxy: "",
    campaign_hashtags: "", active: false, use_fingerprint: false });
  assert.ok(h.daXoa);
});

test("Accounts (b)(c): JSON hỏng → 'Lỗi cú pháp JSON'; mảng → cookiesFromJson TRƯỚC rồi mới đóng hộp + lưu cookies_path; lỗi → 'Không thể lưu cookies'", async () => {
  let ckLoi = true;
  let mo;
  const x = await moAc(mayAc((m, d) => {
    if (m === "POST" && d === "/api/v2/accounts/cookies_from_json") {
      if (ckLoi) return { status: 400, body: { detail: "Danh sách cookies trống" } };
      return new Promise((r) => { mo = () => r({ status: 200, body: { status: "ok", cookies_path: "E:/tool/ck/acc1.json", count: 1 } }); });
    }
    if (m === "PUT" && d === "/api/v2/accounts/1") return { status: 200, body: {} };
    return undefined;
  }));
  bam(x.khung, "data-pvac-nut", { pvacNut: "sua", pvacId: "1" });
  const h = x.hopCuoi();
  oHop(h, "raw", "[{hỏng");
  nutHop(h, "luu");
  await xa();
  let b = x.hopCuoi();
  assert.equal(tieuDe(b), "Lỗi cú pháp JSON");
  assert.match(cauHop(b), /^Nội dung cookies JSON không hợp lệ: /);
  assert.match(b.innerHTML, /pv-hop-critical/);
  traLoi(b, "ok");
  await xa();
  assert.equal(x.goi("POST", "/api/v2/accounts/cookies_from_json").length, 0);
  assert.ok(!h.daXoa);
  const ck = [{ name: "sessionid", value: "S", domain: ".tiktok.com" }];
  oHop(h, "raw", JSON.stringify(ck));
  nutHop(h, "luu");
  await xa();
  b = x.hopCuoi();
  assert.equal(tieuDe(b), "Lỗi");
  assert.equal(cauHop(b), "Không thể lưu cookies: 400: Danh sách cookies trống");
  traLoi(b, "ok");
  await xa();
  assert.ok(!h.daXoa, "lỗi thì hộp vẫn mở");
  assert.equal(x.goi("PUT", "/api/v2/accounts/1").length, 0);
  ckLoi = false;
  nutHop(h, "luu");
  await xa();
  assert.match(vung(h, '[data-pvac-vung="nut"]'), /data-pvac-nut="luu" disabled>Lưu Account<\/button><button[^>]*data-pvac-nut="huy" disabled>/, "đang lưu cookies: khoá nút hộp");
  nutHop(h, "luu");
  nutHop(h, "huy");
  await xa();
  assert.equal(x.goi("POST", "/api/v2/accounts/cookies_from_json").length, 2, "bấm Lưu lần 2 khi đang chờ không gửi thêm");
  assert.ok(!h.daXoa, "chưa đóng hộp khi cookies_from_json chưa xong");
  assert.deepEqual(x.goi("POST", "/api/v2/accounts/cookies_from_json")[1].body, { name: "acc1", cookies: ck });
  mo();
  await xa();
  assert.ok(h.daXoa);
  assert.equal(x.goi("PUT", "/api/v2/accounts/1")[0].body.cookies_path, "E:/tool/ck/acc1.json");
  assert.ok(!x.S.log.some((l) => l.includes("sessionid") || l.includes("user:pass")), "không in cookie / proxy ra console");
});

test("Accounts (f) lỗi gốc giữ: JSON là object (không phải mảng) → không gọi cookies_from_json, lưu luôn; lỗi create/update chỉ ghi log", async () => {
  const x = await moAc(mayAc((m, d) => (m === "POST" && d === "/api/v2/accounts/" ? { status: 400, body: { detail: "Invalid account payload" } } : undefined)));
  const h = moHopThem(x);
  oHop(h, "name", "a");
  oHop(h, "raw", `{"cookies": []}`);
  nutHop(h, "luu");
  await xa();
  assert.equal(x.goi("POST", "/api/v2/accounts/cookies_from_json").length, 0);
  assert.equal(x.goi("POST", "/api/v2/accounts/").length, 1);
  assert.ok(h.daXoa);
  assert.equal(x.hopMo().length, 0, "desktop không có on_error cho create_account → không hộp");
  assert.ok(x.S.log.some((l) => l.includes("Invalid account payload")));
});

// P3-3: chốt B1/B3 chỉ web có (video_server kiem_body → 400 {loi}) → mở lại hộp với dữ liệu đã nhập + báo câu từ chối.
const LOI_B1 = "Tên account không hợp lệ";
const LOI_B3 = "Đường dẫn phải là thư mục/tệp trên ổ đĩa máy nhà (vd E:\\…), không nhận đường mạng";

test("Accounts P3-3: Thêm bị B1 (400 {loi}) → mở lại hộp Thêm giữ dữ liệu + 'Không thể lưu account' / câu B1; sửa tên rồi Lưu → tạo", async () => {
  let lan = 0;
  const x = await moAc(mayAc((m, d) => {
    if (m === "POST" && d === "/api/v2/accounts/") return ++lan === 1 ? { status: 400, body: { loi: LOI_B1 } } : { status: 200, body: { id: 3 } };
    return undefined;
  }));
  const h = moHopThem(x);
  oHop(h, "name", "a/b");
  oHop(h, "proxy", "http://1.1.1.1:1");
  nhap(h, "change", { pvacO: "active" }, { checked: false });
  nutHop(h, "luu");
  await xa();
  assert.ok(h.daXoa, "desktop đóng hộp trước khi gọi API");
  const mo = x.hopMo();
  assert.equal(mo.length, 2, "hộp Thêm mở lại + hộp báo lỗi");
  const h2 = mo[0];
  assert.equal(tieuDe(h2), "Thêm Account");
  assert.match(h2.innerHTML, /data-pvac-o="name" value="a\/b"/);
  assert.match(h2.innerHTML, /data-pvac-o="proxy" value="http:\/\/1\.1\.1\.1:1"/);
  assert.match(h2.innerHTML, /data-pvac-o="active"> Account/, "giữ trạng thái active đã bỏ tick");
  const b = mo[1];
  assert.equal(tieuDe(b), "Không thể lưu account");
  assert.equal(cauHop(b), esc(LOI_B1));
  assert.match(b.innerHTML, /pv-hop-warning/);
  traLoi(b, "ok");
  await xa();
  assert.ok(!h2.daXoa);
  bam(x.khung, "data-pvac-nut", { pvacNut: "them" });
  assert.equal(x.hopMo().length, 1, "hộp mở lại là hộp hiện hành: không mở hộp thứ hai");
  oHop(h2, "name", "ab");
  nutHop(h2, "luu");
  await xa();
  assert.ok(h2.daXoa);
  const gui = x.goi("POST", "/api/v2/accounts/").map((g) => g.body);
  assert.equal(gui.length, 2, "không tự gửi lại: lần 2 do người dùng bấm Lưu");
  assert.deepEqual(gui[1], { name: "ab", cookies_path: "", chrome_profile_dir: "", proxy: "http://1.1.1.1:1", campaign_hashtags: "", active: false, use_fingerprint: false });
  assert.equal(x.hopMo().length, 0);
});

test("Accounts P3-3: Sửa bị B3 (cookies_path UNC) → mở lại hộp Sửa cùng account; lỗi 400 khác / 500 vẫn chỉ ghi log", async () => {
  let tra = { status: 400, body: { loi: LOI_B3 } };
  const x = await moAc(mayAc((m, d) => (m === "PUT" && d === "/api/v2/accounts/1" ? tra : undefined)));
  bam(x.khung, "data-pvac-nut", { pvacNut: "sua", pvacId: "1" });
  const h = x.hopCuoi();
  oHop(h, "cookies_path", "\\\\nas\\ck.json");
  nutHop(h, "luu");
  await xa();
  assert.ok(h.daXoa);
  const [h2, b] = x.hopMo();
  assert.equal(tieuDe(h2), "Sửa Account");
  assert.ok(h2.innerHTML.includes(`data-pvac-o="cookies_path" value="${esc("\\\\nas\\ck.json")}"`));
  assert.equal(tieuDe(b), "Không thể lưu account");
  assert.equal(cauHop(b), esc(LOI_B3));
  traLoi(b, "ok");
  await xa();
  // 400 không phải câu B1/B3 (detail của backend) → giữ lỗi gốc: chỉ console.error, không hộp.
  tra = { status: 400, body: { detail: "Account name already exists" } };
  nutHop(h2, "luu");
  await xa();
  assert.ok(h2.daXoa);
  assert.equal(x.hopMo().length, 0);
  assert.ok(x.S.log.some((l) => l.includes("Account name already exists")));
  // 400 {loi} khác B1/B3 và 500 mang câu B1 cũng chỉ ghi log.
  for (const t of [{ status: 400, body: { loi: "Query không hợp lệ" } }, { status: 500, body: { loi: LOI_B1 } }]) {
    tra = t;
    bam(x.khung, "data-pvac-nut", { pvacNut: "sua", pvacId: "1" });
    nutHop(x.hopCuoi(), "luu");
    await xa();
    assert.equal(x.hopMo().length, 0, JSON.stringify(t));
  }
  assert.equal(x.goi("PUT", "/api/v2/accounts/1").length, 4);
});

test("Accounts P3-3: lỗi B1 về khi người dùng đã mở hộp khác / đã rời trang → không mở hộp chồng; rời trang thì không báo", async () => {
  const cho = [];
  const x = await moAc(mayAc((m, d) => (m === "POST" && d === "/api/v2/accounts/" ? new Promise((r) => cho.push(r)) : undefined)));
  const h = moHopThem(x);
  oHop(h, "name", "x:y");
  nutHop(h, "luu");
  await xa();
  assert.ok(h.daXoa);
  const h2 = moHopThem(x);
  cho[0]({ status: 400, body: { loi: LOI_B1 } });
  await xa();
  const mo = x.hopMo();
  assert.equal(mo.length, 2, "hộp người dùng vừa mở + hộp báo lỗi; không mở lại hộp cũ");
  assert.equal(mo[0], h2);
  assert.equal(cauHop(mo[1]), esc(LOI_B1));
  traLoi(mo[1], "ok");
  nutHop(h2, "huy");
  await xa();
  const h3 = moHopThem(x);
  oHop(h3, "name", "..");
  nutHop(h3, "luu");
  await xa();
  x.P.pvDung();
  cho[1]({ status: 400, body: { loi: LOI_B1 } });
  await xa();
  assert.equal(x.hopMo().length, 0, "đã rời trang: không hộp");
});

test("Accounts: Browse... mở <input type=file>; FileReader đọc file → ô JSON; Lưu → cookiesFromJson; file > 256 KB → cảnh báo, không đọc", async () => {
  const x = await moAc(mayAc((m, d) => {
    if (m === "POST" && d === "/api/v2/accounts/cookies_from_json") return { status: 200, body: { cookies_path: "E:/ck/b.json" } };
    if (m === "POST" && d === "/api/v2/accounts/") return { status: 200, body: {} };
    return undefined;
  }));
  const h = moHopThem(x);
  oHop(h, "name", "b");
  nutHop(h, "browse");
  const tep = h.querySelector('[data-pvac-o="tep"]');
  assert.equal(tep.soClick, 1);
  nhap(h, "change", { pvacO: "tep" }, { files: [{ size: 300 * 1024, noiDung: "[]" }], value: "x" });
  await xa();
  assert.equal(x.S.docTep.length, 0);
  let b = x.hopCuoi();
  assert.equal(cauHop(b), "File cookies quá lớn (tối đa 256 KB).");
  traLoi(b, "ok");
  const noi = `[{"name":"sid","value":"1"}]`;
  nhap(h, "change", { pvacO: "tep" }, { files: [{ size: noi.length, noiDung: noi }], value: "x" });
  await xa();
  assert.equal(x.S.docTep.length, 1);
  assert.equal(h.querySelector('[data-pvac-o="raw"]').value, noi, "nội dung đổ vào ô Paste JSON Cookie");
  nhap(h, "change", { pvacO: "tep" }, { files: [{ size: 1, loi: true }] });
  await xa();
  b = x.hopCuoi();
  assert.equal(cauHop(b), "Không đọc được file cookies.");
  traLoi(b, "ok");
  nutHop(h, "luu");
  await xa();
  assert.deepEqual(x.goi("POST", "/api/v2/accounts/cookies_from_json")[0].body, { name: "b", cookies: [{ name: "sid", value: "1" }] });
  assert.equal(x.goi("POST", "/api/v2/accounts/")[0].body.cookies_path, "E:/ck/b.json");
});

test("Accounts login: tên trống → cảnh báo; bấm → loginAndCapture (202) khoá nút TRƯỚC await, bấm lại không gửi; xong → điền ô + 'Thành công'", async () => {
  let kq = { xong: false };
  const x = await moAc(mayAc((m, d) => {
    if (m === "POST" && d === "/api/v2/accounts/login_and_capture") return { status: 202, body: { cho: CHO, toi_da_giay: 360 } };
    if (m === "GET" && d === `/_kq/${CHO}`) return { status: 200, body: kq };
    return undefined;
  }));
  const h = moHopThem(x);
  nutHop(h, "login");
  await xa();
  let b = x.hopCuoi();
  assert.equal(tieuDe(b), "Lỗi");
  assert.equal(cauHop(b), "Vui lòng nhập Tên Account trước khi tạo profile và login.");
  traLoi(b, "ok");
  oHop(h, "name", " acc7 ");
  oHop(h, "proxy", " http://p:1 ");
  nhap(h, "change", { pvacO: "fp" }, { checked: true });
  nutHop(h, "login");
  assert.match(vung(h, '[data-pvac-vung="login"]'), new RegExp(`data-pvac-nut="login" disabled>${re(LOGIN_DANG)}</button>\\s*<p class="pv-nho pvac-nhac"[^>]*>${re(NHAC)}</p>`),
    "khoá + chữ 'Đang mở Chrome...' ngay khi bấm (đồng bộ)");
  nutHop(h, "login");
  await xa();
  assert.equal(x.goi("POST", "/api/v2/accounts/login_and_capture").length, 1);
  assert.deepEqual(x.goi("POST", "/api/v2/accounts/login_and_capture")[0].body, { name: "acc7", proxy: "http://p:1", use_fingerprint: true });
  await x.clock.tien(3000);
  assert.equal(x.goi("GET", `/_kq/${CHO}`).length, 1);
  kq = { xong: true, status: 200, body: { status: "ok", cookies_path: "E:/tool/ck/acc7.json", chrome_profile_dir: "E:/tool/profiles_v2/acc7", cookies_count: 12 } };
  await x.clock.tien(3000);
  b = x.hopCuoi();
  assert.equal(tieuDe(b), "Thành công");
  assert.equal(cauHop(b), esc("Đã đăng nhập thành công!\nĐã trích xuất 12 cookies."));
  assert.equal(h.querySelector('[data-pvac-o="cookies_path"]').value, "E:/tool/ck/acc7.json");
  assert.equal(h.querySelector('[data-pvac-o="profile"]').value, "E:/tool/profiles_v2/acc7");
  assert.match(vung(h, '[data-pvac-vung="login"]'), new RegExp(`data-pvac-nut="login">${re(LOGIN)}</button>`), "mở khoá, chữ gốc");
  traLoi(b, "ok");
  // Kết quả khác "ok" → "Thông báo" + nguyên dict.
  kq = { xong: true, status: 200, body: { status: "pending" } };
  nutHop(h, "login");
  await x.clock.tien(3000);
  b = x.hopCuoi();
  assert.equal(tieuDe(b), "Thông báo");
  assert.equal(cauHop(b), esc(`{"status":"pending"}`));
});

test("Accounts login (c): lỗi vĩnh viễn → 'Lỗi đăng nhập' / 'Không thể lấy cookies: <lỗi>'; lỗi tạm → hỏi dangChay, còn chạy thì gắn lại, KHÔNG gửi lại", async () => {
  let kieu = "408";
  let dc = [];
  const x = await moAc(mayAc((m, d) => {
    if (m === "POST" && d === "/api/v2/accounts/login_and_capture") {
      if (kieu === "408") return { status: 202, body: { cho: CHO, toi_da_giay: 360 } };
      if (kieu === "mang") return { mang: true };
      return { status: 524, body: "" };
    }
    if (m === "GET" && d === `/_kq/${CHO}`) return { status: 200, body: { xong: true, status: 408, body: { detail: "Hết 5 phút chưa thấy login. Thử lại." } } };
    if (m === "GET" && d === `/_kq/${CHO2}`) return { status: 200, body: { xong: true, status: 200, body: { status: "ok", cookies_count: 3 } } };
    if (m === "GET" && d === "/_kq") return { status: 200, body: { dang_chay: dc } };
    return undefined;
  }));
  const h = moHopThem(x);
  oHop(h, "name", "acc8");
  nutHop(h, "login");
  await x.clock.tien(3000);
  let b = x.hopCuoi();
  assert.equal(tieuDe(b), "Lỗi đăng nhập");
  assert.equal(cauHop(b), "Không thể lấy cookies: 408: Hết 5 phút chưa thấy login. Thử lại.");
  assert.match(b.innerHTML, /pv-hop-critical/);
  traLoi(b, "ok");
  // Lỗi mạng, máy nhà không còn lệnh → báo lỗi kèm câu CÓ THỂ đã chạy; chỉ 1 POST.
  kieu = "mang";
  nutHop(h, "login");
  await xa();
  b = x.hopCuoi();
  assert.match(cauHop(b), /^Không thể lấy cookies: Không kết nối được máy chủ: Failed to fetch\nThao tác CÓ THỂ đã chạy: xem Logs\/Queue trước khi bấm lại\.$/);
  traLoi(b, "ok");
  // 524 nhưng máy nhà còn lệnh login → gắn lại (khoá tiếp), hỏi _kq của lệnh đó, không POST lần 2.
  kieu = "524";
  dc = [{ cho: CHO2, method: "POST", path: "/api/v2/accounts/login_and_capture", toi_da_giay: 360, tom_tat: { name: "acc8" } }];
  const truoc = x.goi("POST", "/api/v2/accounts/login_and_capture").length;
  nutHop(h, "login");
  await xa();
  assert.equal(x.goi("POST", "/api/v2/accounts/login_and_capture").length, truoc + 1);
  assert.match(vung(h, '[data-pvac-vung="login"]'), /data-pvac-nut="login" disabled>/);
  await x.clock.tien(3000);
  assert.equal(x.goi("POST", "/api/v2/accounts/login_and_capture").length, truoc + 1, "không tự gửi lại lệnh login");
  b = x.hopCuoi();
  assert.equal(tieuDe(b), "Thành công");
  assert.equal(cauHop(b), esc("Đã đăng nhập thành công!\nĐã trích xuất 3 cookies."));
});

test("Accounts §3.3: mở trang khi dangChay có login_and_capture → nút login khoá, pvCho đúng 'cho', xong thì mở khoá + hiện kết quả", async () => {
  let xong = false;
  const dc = [{ cho: CHO, method: "POST", path: "/api/v2/accounts/login_and_capture", lop: "DN", toi_da_giay: 360, tom_tat: { name: "acc1" } }];
  const x = await moAc(mayAc((m, d) => {
    if (m === "GET" && d === `/_kq/${CHO}`) return { status: 200, body: xong ? { xong: true, status: 200, body: { status: "ok", cookies_path: "E:/c.json", chrome_profile_dir: "E:/p", cookies_count: 5 } } : { xong: false } };
    return undefined;
  }, { dangChay: dc }));
  assert.equal(x.S.goi[0].duong, "/_kq", "hỏi dangChay khi mở trang");
  bam(x.khung, "data-pvac-nut", { pvacNut: "sua", pvacId: "1" });
  const h = x.hopCuoi();
  assert.match(h.innerHTML, new RegExp(`data-pvac-nut="login" disabled>${re(LOGIN_DANG)}</button>`));
  nutHop(h, "login");
  await x.clock.tien(3000);
  assert.equal(x.goi("POST", "/api/v2/accounts/login_and_capture").length, 0);
  assert.equal(x.goi("GET", `/_kq/${CHO}`).length, 1);
  xong = true;
  await x.clock.tien(3000);
  assert.match(vung(h, '[data-pvac-vung="login"]'), new RegExp(`data-pvac-nut="login">${re(LOGIN)}</button>`));
  assert.equal(h.querySelector('[data-pvac-o="cookies_path"]').value, "E:/c.json", "hộp cùng tên account → điền ô");
  assert.equal(tieuDe(x.hopCuoi()), "Thành công");
});

test("Accounts §3.3: trong lúc còn đang hỏi dangChay, nút login trong hộp bị khoá (không mở được Chrome thứ hai)", async () => {
  let moKq;
  const x = await moAc(mayAc((m, d) => (m === "GET" && d === "/_kq" ? new Promise((r) => { moKq = () => r({ status: 200, body: { dang_chay: [] } }); }) : undefined)));
  const h = moHopThem(x);
  assert.match(h.innerHTML, new RegExp(`data-pvac-nut="login" disabled>${re(LOGIN)}</button>`));
  oHop(h, "name", "a");
  nutHop(h, "login");
  await xa();
  assert.equal(x.goi("POST", "/api/v2/accounts/login_and_capture").length, 0);
  moKq();
  await xa();
  assert.match(vung(h, '[data-pvac-vung="login"]'), new RegExp(`data-pvac-nut="login">${re(LOGIN)}</button>`));
});

test("Accounts (d) XSS: tên / cookie / proxy / vân tay / lỗi API đều esc", async () => {
  const acc = [{ id: 1, name: BAN, cookies_path: `E:/x/${BAN}`, proxy: BAN, active: 1,
    fingerprint: { seed: 1, screen: { width: 10, height: 100 }, hardware_concurrency: 1, device_memory: 1, webgl: { vendor: "v", renderer: BAN } } }];
  const x = await moAc(mayAc((m, d) => (m === "POST" && d === "/api/v2/accounts/1/test-cookies" ? { status: 500, body: { detail: BAN } } : undefined),
    { acc, health: { 1: { health_score: BAN, posts_today: BAN, success_rate: 1 } } }));
  const ds = vung(x.khung, '[data-pvac-vung="ds"]');
  assert.ok(!ds.includes("<img"), ds);
  assert.match(ds, /&lt;img/);
  bam(x.khung, "data-pvac-nut", { pvacNut: "sua", pvacId: "1" });
  assert.ok(!x.hopCuoi().innerHTML.includes("<img"));
  nutHop(x.hopCuoi(), "huy");
  bam(x.khung, "data-pvac-nut", { pvacNut: "check", pvacId: "1" });
  await xa();
  const b = x.hopCuoi();
  assert.equal(tieuDe(b), "Lỗi");
  assert.ok(!b.innerHTML.includes("<img") && b.innerHTML.includes("500: &lt;img"));
});

test("Accounts (e): rời trang giữa lúc tải / login → không vẽ đè, không hộp lỗi roiTrang, ngừng hỏi _kq", async () => {
  let mo;
  const x = await moAc(mayAc((m, d) => {
    if (m === "GET" && d === "/api/v2/accounts/") return new Promise((r) => { mo = () => r({ status: 200, body: ACC }); });
    if (m === "POST" && d === "/api/v2/accounts/login_and_capture") return { status: 202, body: { cho: CHO, toi_da_giay: 360 } };
    if (m === "GET" && d === `/_kq/${CHO}`) return { status: 200, body: { xong: false } };
    return undefined;
  }));
  const h = moHopThem(x);
  oHop(h, "name", "z");
  nutHop(h, "login");
  await x.clock.tien(3000);
  x.P.pvDung();
  mo();
  await x.clock.tien(9000);
  assert.ok(!vung(x.khung, '[data-pvac-vung="ds"]').includes("acc1"), "không vẽ danh sách của phiên cũ");
  assert.equal(x.goi("GET", `/_kq/${CHO}`).length, 1, "ngừng hỏi sau khi rời trang");
  assert.equal(x.hopMo().length, 0, "hộp đóng, không hộp lỗi");
  assert.equal(x.goi("GET", "/api/v2/views/health/1").length, 0);
});

// ======================= Đăng bài =======================
const FOLDERS = [
  { id: 3, name: "Máy hút bụi", path: "E:/v/hut", source: "local", caption: "Caption mặc định #ad" },
  { id: 4, name: "Drive", path: "x", source: "drive" },
  { id: 5, path: "\\\\host\\share", source: "local" },
];
const VIDEO = [{ name: "a.mp4", path: "E:/v/hut/a.mp4", size: 1572864 }, { name: "b.mov", path: "E:/v/hut/b.mov", size: 262144 }];

function mayPo(ghiDe = () => undefined, { dangChay = [], folders = FOLDERS } = {}) {
  return (m, d, b) => {
    const r = ghiDe(m, d, b);
    if (r !== undefined) return r;
    if (m === "GET" && d === "/_kq") return { status: 200, body: { dang_chay: dangChay } };
    if (m === "GET" && d === "/api/v2/folders/") return { status: 200, body: folders };
    if (m === "GET" && d === "/_video/3") return { status: 200, body: { ho_tro: true, video: VIDEO } };
    if (m === "GET" && d === "/_video/5") return { status: 200, body: { ho_tro: false, video: [] } };
    return undefined;
  };
}
async function moPo(xuLy) {
  const x = nap(xuLy);
  const khung = phanTu();
  const cho = x.P.pvPoVe(khung, x.P.phien());
  await xa();
  return { ...x, khung, cho };
}
const V = (x, ten) => vung(x.khung, `[data-pvpo-vung="${ten}"]`);
const chonFolder = (x, i) => nhap(x.khung, "change", { pvpoO: "folder" }, { value: String(i) });
const nutPo = (x, nut, extra = {}) => bam(x.khung, "data-pvpo-nut", { pvpoNut: nut, ...extra });
const nutDang = (x) => /<button[^>]*data-pvpo-nut="dang"([^>]*)>ĐĂNG NGAY<\/button>/.exec(V(x, "nut"));

test("Đăng bài (a): chữ nguyên văn post.py — nhãn, placeholder, combo visibility, nút; ĐĂNG NGAY khoá khi chưa chọn video", async () => {
  const x = await moPo(mayPo());
  const t = x.khung.innerHTML;
  for (const s of [">Chọn Folder:<", ">Videos trong folder:<", ">Chọn một video để xem thông tin<", ">Đăng Video<",
    ">Chọn video và nhấn Đăng để đăng ngay lập tức.<", ">Chưa chọn video<", ">Caption:<", `placeholder="Nhập caption cho video..."`,
    ">Visibility:<", ">First Comment:<", `placeholder="Bình luận đầu tiên (tùy chọn)..."`, ">Lưu nháp (Draft)<"]) assert.ok(t.includes(s), s);
  assert.match(t, /<option value="everyone">everyone<\/option><option value="private">private<\/option><option value="friends">friends<\/option>/);
  assert.match(V(x, "nut"), /data-pvpo-nut="lammoi">Làm mới</);
  assert.match(nutDang(x)[1], /disabled/);
  assert.deepEqual(x.S.goi.map((g) => `${g.method} ${g.duong}`), ["GET /_kq", "GET /api/v2/folders/"], "dangChay TRƯỚC, rồi list_folders");
  assert.equal(V(x, "folder"), `<option value="0" selected>-- Chọn Folder --</option><option value="1">Máy hút bụi</option><option value="2">Drive</option><option value="3">Folder #5</option>`);
});

test("Đăng bài thuần: MB 1 chữ số (nửa-về-chẵn như Python), câu xác nhận cắt 50 ký tự, lệnh đang chạy, danh sách _video", () => {
  const { P } = nap();
  assert.equal(P.pvpoMb(1572864), "1.5");
  assert.equal(P.pvpoMb(262144), "0.2", "0.25 → 0.2 (Python)");
  assert.equal(P.pvpoMb(786432), "0.8", "0.75 → 0.8");
  assert.equal(P.pvpoMb(0), "0.0");
  assert.equal(P.pvpoDongVideo({ name: "a.mp4", size: 5 * 1048576 }), "a.mp4 (5.0 MB)");
  const dai = "🙂".repeat(51);
  assert.equal(P.pvpoCauXacNhan("v.mp4", dai, "private", true), `Đăng video 'v.mp4'?\n\nCaption: ${"🙂".repeat(50)}...\nVisibility: private\nDraft: Có`);
  assert.equal(P.pvpoCauXacNhan("v.mp4", "ngắn", "everyone", false), "Đăng video 'v.mp4'?\n\nCaption: ngắn\nVisibility: everyone\nDraft: Không");
  assert.deepEqual(P.pvpoLenhDang({ dang_chay: [{ cho: CHO, method: "POST", path: "/api/v2/post/direct", toi_da_giay: 300, tom_tat: { folder_id: 3, video: "a.mp4" } }] }),
    { cho: CHO, toiDa: 300, folderId: 3, video: "a.mp4" });
  assert.equal(P.pvpoLenhDang({ dang_chay: [{ cho: CHO, method: "POST", path: "/api/v2/queue/1/post" }] }), null);
  assert.equal(P.pvpoDsVideo({ ho_tro: false, video: [] }), null);
  assert.deepEqual(P.pvpoDsVideo({ ho_tro: true, video: [{ name: "a", path: "p", size: "7" }, { name: 1 }] }), [{ name: "a", path: "p", size: 7 }]);
  assert.equal(P.pvpoTenFolder({ id: 9 }), "Folder #9");
});

test("Đăng bài (b): chọn folder local → dsVideoFolder → '<tên> (x.x MB)', 'Tìm thấy N video', 'Folder: <path>'; drive / ho_tro:false → 'Folder rỗng…'", async () => {
  const x = await moPo(mayPo());
  chonFolder(x, 1);
  assert.equal(V(x, "tt"), "Đang tải videos...");
  await xa();
  assert.equal(x.goi("GET", "/_video/3").length, 1);
  const ds = V(x, "ds");
  assert.match(ds, />a\.mp4 \(1\.5 MB\)</);
  assert.match(ds, />b\.mov \(0\.2 MB\)</);
  assert.equal(V(x, "tt"), "Tìm thấy 2 video");
  assert.equal(V(x, "info"), "Folder: E:/v/hut");
  chonFolder(x, 2);
  await xa();
  assert.equal(x.goi("GET", "/_video/4").length, 0, "nguồn drive: desktop không liệt kê");
  assert.equal(V(x, "info"), "Folder rỗng hoặc nguồn không hỗ trợ");
  assert.equal(V(x, "ds"), "");
  chonFolder(x, 3);
  await xa();
  assert.equal(x.goi("GET", "/_video/5").length, 1);
  assert.equal(V(x, "info"), "Folder rỗng hoặc nguồn không hỗ trợ");
  chonFolder(x, 0);
  await xa();
  assert.equal(V(x, "xem"), "Chưa chọn video");
  // Làm mới: chỉ khi đang có folder.
  const truoc = x.S.goi.length;
  nutPo(x, "lammoi");
  await xa();
  assert.equal(x.S.goi.length, truoc);
  chonFolder(x, 1);
  await xa();
  nutPo(x, "lammoi");
  await xa();
  assert.equal(x.goi("GET", "/_video/3").length, 3);
});

test("Đăng bài (b): chọn video → '🎬 <tên>', tự điền caption của folder khi ô trống, mở ĐĂNG NGAY; thiếu caption → 'Thiếu caption'", async () => {
  const x = await moPo(mayPo(undefined, { folders: [{ id: 3, name: "F", path: "E:/v/hut", source: "local" }] }));
  chonFolder(x, 1);
  await xa();
  nutPo(x, "video", { pvpoI: "1" });
  assert.equal(V(x, "xem"), "🎬 b.mov");
  assert.match(V(x, "ds"), /data-pvpo-i="1" aria-selected="true"/);
  assert.ok(!/disabled/.test(nutDang(x)[1]));
  nutPo(x, "dang");
  await xa();
  const b = x.hopCuoi();
  assert.equal(tieuDe(b), "Thiếu caption");
  assert.equal(cauHop(b), "Vui lòng nhập caption.");
  traLoi(b, "ok");
  const y = await moPo(mayPo());
  chonFolder(y, 1);
  await xa();
  nutPo(y, "video", { pvpoI: "0" });
  assert.equal(y.khung.querySelector('[data-pvpo-o="caption"]').value, "Caption mặc định #ad");
});

test("Đăng bài (b): ĐĂNG NGAY → hộp 'Xác nhận đăng' (No = không gửi); Yes → postVideoDirect đủ tham số; 202 khoá nút, bấm lại không gửi; xong như desktop", async () => {
  let kq = { xong: false };
  const x = await moPo(mayPo((m, d) => {
    if (m === "POST" && d === "/api/v2/post/direct") return { status: 202, body: { cho: CHO, toi_da_giay: 300 } };
    if (m === "GET" && d === `/_kq/${CHO}`) return { status: 200, body: kq };
    return undefined;
  }));
  chonFolder(x, 1);
  await xa();
  nutPo(x, "video", { pvpoI: "0" });
  nhap(x.khung, "input", { pvpoO: "caption" }, { value: "  Hút sạch #ad  " });
  nhap(x.khung, "change", { pvpoO: "hien" }, { value: "private" });
  nhap(x.khung, "input", { pvpoO: "fc" }, { value: " link ở bio " });
  nutPo(x, "nhap");
  assert.match(V(x, "nhap"), /aria-pressed="true">Lưu nháp \(Draft\)/);
  nutPo(x, "dang");
  assert.match(nutDang(x)[1], /disabled/, "khoá ngay khi bấm (trước await hộp xác nhận)");
  nutPo(x, "dang");
  await xa();
  assert.equal(x.hopMo().length, 1, "bấm 2 lần chỉ 1 hộp");
  let b = x.hopCuoi();
  assert.equal(tieuDe(b), "Xác nhận đăng");
  assert.equal(cauHop(b), esc("Đăng video 'a.mp4'?\n\nCaption: Hút sạch #ad\nVisibility: private\nDraft: Có"));
  assert.match(b.innerHTML, /data-pv-nut="yes">Yes<\/button><button type="button" class="btn ghost" data-pv-nut="no">No</);
  traLoi(b, "no");
  await xa();
  assert.equal(x.goi("POST", "/api/v2/post/direct").length, 0);
  assert.ok(!/disabled/.test(nutDang(x)[1]), "No → mở lại nút");
  nutPo(x, "dang");
  await xa();
  traLoi(x.hopCuoi(), "yes");
  await xa();
  assert.deepEqual(x.goi("POST", "/api/v2/post/direct").map((g) => g.body), [{ folder_id: 3, video_path: "E:/v/hut/a.mp4", caption: "Hút sạch #ad",
    visibility: "private", first_comment: "link ở bio", draft: true }]);
  assert.equal(V(x, "tt"), "⏳ Đang đăng video...");
  assert.match(nutDang(x)[1], /disabled/);
  assert.match(V(x, "nut"), /Đang đăng a\.mp4…/);
  nutPo(x, "dang");
  nutPo(x, "video", { pvpoI: "1" });
  assert.match(nutDang(x)[1], /disabled/, "chọn video khác trong lúc đăng vẫn khoá");
  await x.clock.tien(3000);
  assert.equal(x.goi("POST", "/api/v2/post/direct").length, 1, "không gửi lần 2");
  kq = { xong: true, status: 200, body: { success: true, message: "Đã đăng 1 video" } };
  await x.clock.tien(3000);
  assert.equal(V(x, "tt"), "✅ Đã đăng 1 video");
  b = x.hopCuoi();
  assert.equal(tieuDe(b), "Thành công");
  assert.equal(cauHop(b), "Đã đăng 1 video");
  assert.ok(!/disabled/.test(nutDang(x)[1]));
  assert.ok(!/Đang đăng/.test(V(x, "nut")));
  assert.equal(x.khung.querySelector('[data-pvpo-o="caption"]').value, "");
  assert.equal(x.khung.querySelector('[data-pvpo-o="fc"]').value, "");
  assert.match(V(x, "nhap"), /aria-pressed="false"/);
});

test("Đăng bài (c): lỗi → '❌ Lỗi: <lỗi>' + 'Lỗi' / 'Không thể đăng video:\\n<lỗi>'; lỗi tạm → hỏi dangChay: còn chạy thì gắn lại, không còn thì kèm 'CÓ THỂ đã chạy'", async () => {
  let kieu = "500";
  let dc = [];
  const x = await moPo(mayPo((m, d) => {
    if (m === "POST" && d === "/api/v2/post/direct") {
      if (kieu === "500") return { status: 202, body: { cho: CHO, toi_da_giay: 300 } };
      if (kieu === "429") return { status: 429, body: { loi: "Đang có lệnh đăng/login khác chạy, chờ xong rồi thử lại" } };
      return { status: 524, body: "" };
    }
    if (m === "GET" && d === `/_kq/${CHO}`) return { status: 200, body: { xong: true, status: 500, body: { detail: "Upload failed" } } };
    if (m === "GET" && d === `/_kq/${CHO2}`) return { status: 200, body: { xong: true, status: 200, body: { message: "OK rồi" } } };
    if (m === "GET" && d === "/_kq") return { status: 200, body: { dang_chay: dc } };
    return undefined;
  }));
  chonFolder(x, 1);
  await xa();
  nutPo(x, "video", { pvpoI: "0" });
  const dang = async () => { nutPo(x, "dang"); await xa(); traLoi(x.hopCuoi(), "yes"); await xa(); };
  await dang();
  await x.clock.tien(3000);
  assert.equal(V(x, "tt"), "❌ Lỗi: 500: Upload failed");
  let b = x.hopCuoi();
  assert.equal(tieuDe(b), "Lỗi");
  assert.equal(cauHop(b), esc("Không thể đăng video:\n500: Upload failed"));
  assert.match(b.innerHTML, /pv-hop-critical/);
  traLoi(b, "ok");
  assert.ok(!/disabled/.test(nutDang(x)[1]));
  kieu = "429";
  await dang();
  b = x.hopCuoi();
  assert.equal(cauHop(b), esc("Không thể đăng video:\n429: Đang có lệnh đăng/login khác chạy, chờ xong rồi thử lại"), "429 không gọi backend → không thêm câu CÓ THỂ");
  traLoi(b, "ok");
  kieu = "524";
  await dang();
  b = x.hopCuoi();
  assert.equal(cauHop(b), esc("Không thể đăng video:\nHTTP 524\nThao tác CÓ THỂ đã chạy: xem Logs/Queue trước khi bấm lại."));
  traLoi(b, "ok");
  dc = [{ cho: CHO2, method: "POST", path: "/api/v2/post/direct", toi_da_giay: 300, tom_tat: { folder_id: 3, video: "a.mp4" } }];
  const truoc = x.goi("POST", "/api/v2/post/direct").length;
  await dang();
  assert.equal(x.goi("POST", "/api/v2/post/direct").length, truoc + 1);
  assert.match(nutDang(x)[1], /disabled/, "máy nhà còn lệnh → vẫn khoá");
  assert.match(V(x, "nut"), /Đang đăng a\.mp4…/);
  await x.clock.tien(3000);
  assert.equal(x.goi("POST", "/api/v2/post/direct").length, truoc + 1, "không tự gửi lại lệnh đăng");
  assert.equal(V(x, "tt"), "✅ OK rồi");
});

test("Đăng bài thuần P3-4: tên tệp như PureWindowsPath(...).name; chỉ lấy lệnh post/direct khớp CẢ folder_id lẫn tên video", () => {
  const { P } = nap();
  assert.equal(P.pvpoTenTep("E:/v/hut/a.mp4"), "a.mp4");
  assert.equal(P.pvpoTenTep("E:\\v\\hut\\b.mov"), "b.mov");
  assert.equal(P.pvpoTenTep("E:a.mp4"), "a.mp4");
  assert.equal(P.pvpoTenTep(""), "");
  const l = (cho, folder_id, video, path = "/api/v2/post/direct") => ({ cho, method: "POST", path, toi_da_giay: 300, tom_tat: { folder_id, video } });
  const dc = { dang_chay: [l(CHO, 3, "b.mov"), l("1".repeat(32), 4, "a.mp4"), l("2".repeat(32), 3, "a.mp4", "/api/v2/queue/1/post"), l(CHO2, 3, "a.mp4")] };
  assert.deepEqual(P.pvpoLenhKhop(dc, 3, "a.mp4"), { cho: CHO2, toiDa: 300, folderId: 3, video: "a.mp4" });
  assert.equal(P.pvpoLenhKhop(dc, 3, "c.mp4"), null);
  assert.equal(P.pvpoLenhKhop(dc, 5, "a.mp4"), null);
  assert.equal(P.pvpoLenhKhop({ dang_chay: [l(CHO, null, "")] }, null, ""), null, "thiếu folder/tên → không khớp");
  assert.equal(P.pvpoLenhKhop(null, 3, "a.mp4"), null);
});

test("Đăng bài (c) P3-4: lỗi tạm mà máy nhà đang chạy lệnh đăng KHÁC (khác video / khác folder) → báo lỗi kèm 'CÓ THỂ đã chạy', không gắn, không gửi lại", async () => {
  let dc = [];
  const x = await moPo(mayPo((m, d) => {
    if (m === "POST" && d === "/api/v2/post/direct") return { status: 524, body: "" };
    if (m === "GET" && d === `/_kq/${CHO}`) return { status: 200, body: { xong: true, status: 200, body: { message: "của tab khác" } } };
    if (m === "GET" && d === `/_kq/${CHO2}`) return { status: 200, body: { xong: true, status: 200, body: { message: "OK của mình" } } };
    if (m === "GET" && d === "/_kq") return { status: 200, body: { dang_chay: dc } };
    return undefined;
  }));
  chonFolder(x, 1);
  await xa();
  nutPo(x, "video", { pvpoI: "0" });
  nhap(x.khung, "input", { pvpoO: "caption" }, { value: "cap" });
  const dang = async () => { nutPo(x, "dang"); await xa(); traLoi(x.hopCuoi(), "yes"); await xa(); };
  dc = [{ cho: CHO, method: "POST", path: "/api/v2/post/direct", toi_da_giay: 300, tom_tat: { folder_id: 3, video: "b.mov" } },
    { cho: CHO, method: "POST", path: "/api/v2/post/direct", toi_da_giay: 300, tom_tat: { folder_id: 4, video: "a.mp4" } }];
  await dang();
  const loi = "HTTP 524\nThao tác CÓ THỂ đã chạy: xem Logs/Queue trước khi bấm lại.";
  assert.equal(V(x, "tt"), esc(`❌ Lỗi: ${loi}`));
  let b = x.hopCuoi();
  assert.equal(tieuDe(b), "Lỗi");
  assert.equal(cauHop(b), esc(`Không thể đăng video:\n${loi}`));
  traLoi(b, "ok");
  assert.ok(!/disabled/.test(nutDang(x)[1]), "không gắn lệnh của tab khác → mở nút");
  assert.ok(!/Đang đăng/.test(V(x, "nut")));
  await x.clock.tien(6000);
  assert.equal(x.goi("GET", `/_kq/${CHO}`).length, 0, "không hỏi kết quả lệnh của tab khác");
  assert.equal(x.goi("POST", "/api/v2/post/direct").length, 1, "không tự gửi lại");
  // Lệnh khớp nằm SAU lệnh của tab khác → gắn đúng lệnh khớp (không lấy lệnh đầu).
  dc = [dc[0], { cho: CHO2, method: "POST", path: "/api/v2/post/direct", toi_da_giay: 300, tom_tat: { folder_id: 3, video: "a.mp4" } }];
  await dang();
  assert.match(nutDang(x)[1], /disabled/);
  assert.match(V(x, "nut"), /Đang đăng a\.mp4…/);
  await x.clock.tien(3000);
  assert.equal(x.goi("GET", `/_kq/${CHO}`).length, 0);
  assert.equal(V(x, "tt"), "✅ OK của mình");
  b = x.hopCuoi();
  assert.equal(tieuDe(b), "Thành công");
  assert.equal(x.goi("POST", "/api/v2/post/direct").length, 2, "lần 2 do người dùng bấm, không tự gửi lại");
});

test("Đăng bài §3.3: mở trang khi dangChay có post/direct → chọn sẵn folder, khoá ĐĂNG NGAY, 'Đang đăng <video>…', pvCho; rời rồi quay lại vẫn khoá", async () => {
  let xong = false;
  const dc = [{ cho: CHO, method: "POST", path: "/api/v2/post/direct", lop: "L", toi_da_giay: 300, tom_tat: { folder_id: 3, video: "a.mp4" } }];
  const xuLy = mayPo((m, d) => {
    if (m === "GET" && d === `/_kq/${CHO}`) return { status: 200, body: xong ? { xong: true, status: 200, body: { message: "Xong" } } : { xong: false } };
    return undefined;
  }, { dangChay: dc });
  const x = await moPo(xuLy);
  assert.match(V(x, "folder"), /<option value="1" selected>Máy hút bụi<\/option>/);
  assert.equal(x.goi("GET", "/_video/3").length, 1);
  nutPo(x, "video", { pvpoI: "0" });
  assert.match(nutDang(x)[1], /disabled/);
  assert.match(V(x, "nut"), /Đang đăng a\.mp4…/);
  nutPo(x, "dang");
  await x.clock.tien(3000);
  assert.equal(x.goi("POST", "/api/v2/post/direct").length, 0);
  assert.equal(x.goi("GET", `/_kq/${CHO}`).length, 1);
  // Rời trang rồi quay lại (trang mới, cùng môi trường): gọi lại dangChay, vẫn khoá.
  x.P.pvDung();
  const khung2 = phanTu();
  x.P.pvPoVe(khung2, x.P.phien());
  await xa();
  assert.equal(x.goi("GET", "/_kq").length, 2);
  assert.match(vung(khung2, '[data-pvpo-vung="nut"]'), /data-pvpo-nut="dang" disabled>ĐĂNG NGAY/);
  assert.match(vung(khung2, '[data-pvpo-vung="nut"]'), /Đang đăng a\.mp4…/);
  xong = true;
  await x.clock.tien(3000);
  assert.equal(vung(khung2, '[data-pvpo-vung="tt"]'), "✅ Xong");
  assert.equal(tieuDe(x.hopCuoi()), "Thành công");
  assert.equal(x.hopMo().length, 1, "trang cũ đã rời không hiện thêm hộp");
  assert.match(V(x, "nut"), /Đang đăng a\.mp4…/, "trang cũ đã rời: không vẽ đè");
  assert.doesNotMatch(vung(khung2, '[data-pvpo-vung="nut"]'), /Đang đăng/, "trang mới mở khoá");
});

test("Đăng bài: trong lúc hỏi dangChay nút khoá; folder đổi trong lúc liệt kê → bỏ kết quả cũ", async () => {
  let moKq, mo3;
  const x = await moPo(mayPo((m, d) => {
    if (m === "GET" && d === "/_kq") return new Promise((r) => { moKq = () => r({ status: 200, body: { dang_chay: [] } }); });
    if (m === "GET" && d === "/_video/3") return new Promise((r) => { mo3 = () => r({ status: 200, body: { ho_tro: true, video: VIDEO } }); });
    return undefined;
  }));
  assert.match(nutDang(x)[1], /disabled/);
  assert.equal(x.goi("GET", "/api/v2/folders/").length, 0, "chưa tải folder trước khi biết lệnh đang chạy");
  moKq();
  await xa();
  chonFolder(x, 1);
  await xa();
  chonFolder(x, 2);
  mo3();
  await xa();
  assert.equal(V(x, "ds"), "");
  assert.equal(V(x, "info"), "Folder rỗng hoặc nguồn không hỗ trợ");
});

test("Đăng bài (d) XSS + (e) rời trang: tên folder/video/đường dẫn/lỗi esc; rời giữa lúc đăng → không vẽ, không hộp, ngừng hỏi", async () => {
  const x = await moPo(mayPo((m, d) => {
    if (m === "GET" && d === "/_video/3") return { status: 200, body: { ho_tro: true, video: [{ name: BAN, path: `E:/v/${BAN}`, size: 1 }] } };
    if (m === "POST" && d === "/api/v2/post/direct") return { status: 202, body: { cho: CHO, toi_da_giay: 300 } };
    if (m === "GET" && d === `/_kq/${CHO}`) return { status: 200, body: { xong: false } };
    return undefined;
  }, { folders: [{ id: 3, name: BAN, path: `E:/v/${BAN}`, source: "local", caption: BAN }] }));
  chonFolder(x, 1);
  await xa();
  nutPo(x, "video", { pvpoI: "0" });
  for (const v of ["folder", "ds", "info", "xem"]) assert.ok(!V(x, v).includes("<img"), v);
  nutPo(x, "dang");
  await xa();
  const b = x.hopCuoi();
  assert.ok(!b.innerHTML.includes("<img"));
  traLoi(b, "yes");
  await x.clock.tien(3000);
  const nut = V(x, "nut");
  assert.ok(!nut.includes("<img") && nut.includes("&lt;img"));
  x.P.pvDung();
  await x.clock.tien(9000);
  assert.equal(x.goi("GET", `/_kq/${CHO}`).length, 1, "ngừng hỏi");
  assert.equal(x.hopMo().length, 0);
  assert.equal(V(x, "tt"), "⏳ Đang đăng video...", "không vẽ đè sau khi rời");
  // Lỗi tải video có chuỗi độc.
  const y = await moPo(mayPo((m, d) => (m === "GET" && d === "/_video/3" ? { status: 404, body: { detail: BAN } } : undefined)));
  chonFolder(y, 1);
  await xa();
  assert.ok(!V(y, "tt").includes("<img") && V(y, "tt").startsWith("❌ Lỗi: 404: &lt;img"));
});

// ---------- tên cấp đỉnh + CSP ----------
const tenDinh = (src) => [...src.matchAll(/^(?:async )?function\*? ?(\w+)|^(?:const|let|var|class) (\w+)/gm)].map((m) => m[1] || m[2]);
test("pv-accounts.js / pv-post.js: tên cấp đỉnh đúng tiền tố pvac / pvpo; có pvAcVe / pvPoVe; không sự kiện inline; không fetch trực tiếp; có khối thuần", () => {
  for (const [src, tt, ve] of [[AC, "pvac", "pvAcVe"], [PO, "pvpo", "pvPoVe"]]) {
    const ds = tenDinh(src);
    assert.ok(ds.includes(ve));
    for (const t of ds) assert.ok(t.toLowerCase().startsWith(tt), `"${t}" phải bắt đầu bằng ${tt}`);
    assert.ok(!/\son[a-z]+="/.test(src) && !/onclick\s*=/i.test(src), "không gắn sự kiện inline (CSP)");
    assert.ok(!/\bfetch\(/.test(src), "chỉ gọi qua pvApi");
    assert.match(src, new RegExp(`// --- ${tt}-thuan start ---[\\s\\S]+// --- ${tt}-thuan end ---`));
    assert.ok(!/console\.(log|error)\([^)]*(proxy|cookies\b)/.test(src), "không in proxy / cookie ra console");
  }
});
