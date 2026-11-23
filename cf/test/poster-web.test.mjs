// Test W-P1: khung Poster V2 trên web — web/poster.js (+ móc khung.js, index.html, poster.css).
// Thiết kế: docs/poster-v2-tren-web.md §2.1, §2.2, §3, §6.1–§6.4, §9 W-P1. Chạy: node --test cf/test/
// Không mạng: globalThis.fetch bị thay bằng hàm ném lỗi TRƯỚC khi nạp mã; poster.js nhận fetch giả qua tham số.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

globalThis.fetch = async (url) => { throw new Error(`fetch thật bị cấm trong test: ${url}`); };

const duong = (p) => new URL(`../../web/${p}`, import.meta.url);
const doc = (p) => readFileSync(duong(p), "utf8");
const APP = doc("app.js");
const KHUNG = doc("khung.js");
const POSTER = doc("poster.js");
const CSS = doc("poster.css");
const HTML = doc("index.html");

const dong = (src, dau) => {
  const l = src.split("\n").find((x) => x.startsWith(dau));
  assert.ok(l, `không thấy dòng bắt đầu bằng "${dau}"`);
  return l;
};
const esc = new Function(`${dong(APP, "const esc = ")}\nreturn esc;`)();
const CHI_CHU_HTML = new Function(`${dong(APP, "const CHI_CHU_HTML = ")}\nreturn CHI_CHU_HTML;`)();
const khoi = (src, ten) => {
  const m = src.match(new RegExp(`// --- ${ten} start ---\\n([\\s\\S]*?)// --- ${ten} end ---`));
  assert.ok(m, `thiếu marker ${ten}`);
  return m[1];
};
const BAN = `<img src=x onerror=alert(1)>`;
const CHO = "0123456789abcdef0123456789abcdef";
const CHUA_CO = `<p class="center muted">Trang đang được cập nhật.</p>`;

// Nhường cho các Promise đang chờ chạy xong (timer giả không tự chạy).
const xa = async () => { for (let i = 0; i < 30; i++) await new Promise((r) => setImmediate(r)); };

// Đồng hồ giả: setTimeout/setInterval/Date.now chỉ chạy khi gọi tien(ms).
function dongHoGia() {
  const c = { now: 1_000_000, hen: new Map(), id: 0 };
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
const bam = (el, ma) => el.nghe.click({ target: { closest: () => ({ dataset: { pvNut: ma } }) } });

// Nạp NGUYÊN web/poster.js với môi trường giả. xuLy(url, opt) → { status, body } | undefined (undefined = ném "fetch thật bị cấm").
function napPoster({ xuLy, trang = {}, user = "nhan" } = {}) {
  const S = { goi: [], toasts: [], dangNhap: 0, veUser: 0, hop: [], el: {} };
  const clock = dongHoGia();
  const auth = { user, ten: user, get on() { return !!this.user; } };
  const app = theGia();
  const $ = (s) => {
    if (s === "#app") return app;
    const m = s.match(/^#([\w-]+)$/);
    if (!m || !app.innerHTML.includes(`id="${m[1]}"`)) return null;
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
  const ns = {
    esc, $, document, auth, fetch, globalThis: trang, mnCHUA_CO: CHUA_CO,
    renderUser: () => { S.veUser++; }, openLogin: () => { S.dangNhap++; }, toast: (m) => S.toasts.push(m),
    setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout, setInterval: clock.setInterval, clearInterval: clock.clearInterval,
    Date: { now: () => clock.now },
  };
  const ten = Object.keys(ns);
  const P = new Function(...ten, `${POSTER}
return { pvTRANG, pvTRANG_VE, pvPhanTich, pvTabHtml, pvChuLoi, pvQs, pvGoi, pvCho, pvApi, pvRender, pvDung, pvConSong, pvHenGio,
  pvXacNhan, pvThongBao, pvHop, phien: () => pvPhien };`)(...ten.map((k) => ns[k]));
  return { P, S, clock, auth, app, document };
}
const ok = (body = {}) => () => ({ status: 200, body });

// ---------- khối thuần ----------
test("poster-thuan: khối có marker, nạp riêng được (chỉ cần esc + pvTRANG)", () => {
  const TRANG = POSTER.slice(POSTER.indexOf("const pvTRANG = "), POSTER.indexOf("]];", POSTER.indexOf("const pvTRANG = ")) + 3);
  const F = new Function("esc", `"use strict";\n${TRANG}\n${khoi(POSTER, "poster-thuan")}
return { pvPhanTich, pvTabHtml, pvChuLoi, pvQs };`)(esc);
  assert.equal(F.pvPhanTich("queue"), "queue");
  assert.match(F.pvTabHtml("logs"), /aria-current="page">Logs</);
});

test("pvPhanTich: rỗng / lạ / %E0 / không phải chuỗi → dashboard; 9 mã đúng; mã đã mã hoá giải được", () => {
  const { P } = napPoster();
  for (const x of ["", "la", "%E0", "%E0%A4%A", "Queue", "queue/1", undefined, null, 5]) assert.equal(P.pvPhanTich(x), "dashboard", String(x));
  for (const m of ["dashboard", "accounts", "folders", "calendar", "views", "queue", "post", "logs", "settings"]) assert.equal(P.pvPhanTich(m), m);
  assert.equal(P.pvPhanTich("%71ueue"), "queue");
});

test("pvTabHtml: 9 tab đúng thứ tự + nhãn NAV_ITEMS (app.py:52-62), href #/poster/<ma>, aria-current đúng tab", () => {
  const { P } = napPoster();
  assert.deepEqual(P.pvTRANG, [["Dashboard", "dashboard"], ["Accounts", "accounts"], ["Folders", "folders"], ["Calendar", "calendar"],
    ["Views", "views"], ["Queue", "queue"], ["Đăng bài", "post"], ["Logs", "logs"], ["Settings", "settings"]]);
  assert.deepEqual(P.pvTRANG_VE, { dashboard: "pvDbVe", accounts: "pvAcVe", folders: "pvFoVe", calendar: "pvCaVe",
    views: "pvViVe", queue: "pvQuVe", post: "pvPoVe", logs: "pvLoVe", settings: "pvSeVe" });
  for (const [, ma] of P.pvTRANG) {
    const h = P.pvTabHtml(ma);
    const a = [...h.matchAll(/<a class="pv-tab" href="#\/poster\/([a-z]+)" data-pv-tab="([a-z]+)"( aria-current="page")?>([^<]+)<\/a>/g)];
    assert.deepEqual(a.map((m) => m[4]), P.pvTRANG.map((t) => t[0]));
    assert.deepEqual(a.map((m) => m[1]), P.pvTRANG.map((t) => t[1]));
    assert.deepEqual(a.filter((m) => m[3]).map((m) => m[1]), [ma], `chỉ tab ${ma} có aria-current`);
    assert.equal((h.match(/aria-current/g) || []).length, 1);
  }
  assert.match(P.pvTabHtml("dashboard"), /^<nav class="pv-tabs" aria-label="Poster V2">/);
});

test("pvChuLoi: detail chuỗi / object / mảng / loi / rỗng / chuỗi thô", () => {
  const { P } = napPoster();
  assert.equal(P.pvChuLoi(404, { detail: "Not Found" }), "404: Not Found");
  assert.equal(P.pvChuLoi(422, { detail: [{ loc: ["body", "name"], msg: "field required" }] }), `422: [{"loc":["body","name"],"msg":"field required"}]`);
  assert.equal(P.pvChuLoi(400, { detail: { a: 1 } }), `400: {"a":1}`);
  assert.equal(P.pvChuLoi(502, { loi: "Poster V2 trên máy nhà chưa mở" }), "502: Poster V2 trên máy nhà chưa mở");
  assert.equal(P.pvChuLoi(500, {}), "HTTP 500");
  assert.equal(P.pvChuLoi(500, { detail: "" }), "HTTP 500");
  assert.equal(P.pvChuLoi(500, null), "HTTP 500");
  assert.equal(P.pvChuLoi(500, undefined), "HTTP 500");
  assert.equal(P.pvChuLoi(500, "  Internal Server Error \n"), "500: Internal Server Error");
  assert.equal(P.pvChuLoi(500, "x".repeat(400)), `500: ${"x".repeat(300)}`);
  assert.equal(P.pvChuLoi(403, { detail: "License invalid", loi: "khác" }), "403: License invalid", "detail ưu tiên trước loi");
});

test("pvQs: bỏ undefined/null, giữ 0/false/chuỗi rỗng như api.ts", () => {
  const { P } = napPoster();
  assert.equal(P.pvQs({ limit: 100, offset: 0, status: undefined, x: null }), "?limit=100&offset=0");
  assert.equal(P.pvQs({ archived: 0 }), "?archived=0");
  assert.equal(P.pvQs({}), "");
  assert.equal(P.pvQs(undefined), "");
  assert.equal(P.pvQs({ product_id: "a b&c" }), "?product_id=a+b%26c");
});

// ---------- tên cấp đỉnh (§6.3 luật tránh va, §6.4 danh sách cố định) ----------
const tenDinh = (src) => [...src.matchAll(/^(?:async )?function\*? ?(\w+)|^(?:const|let|var|class) (\w+)/gm)].map((m) => m[1] || m[2]);
test("poster.js: tên cấp đỉnh đúng danh sách §6.4; không tên nào bắt đầu bằng 9 tiền tố con (không phân biệt hoa thường)", () => {
  const DS = ["pvTRANG", "pvTRANG_VE", "pvPhien", "pvPhanTich", "pvTabHtml", "pvChuLoi", "pvQs", "pvGoi", "pvCho", "pvApi", "pvRender",
    "pvDung", "pvConSong", "pvHenGio", "pvXacNhan", "pvThongBao", "pvHop"];
  assert.deepEqual([...tenDinh(POSTER)].sort(), [...DS].sort());
  const CON = ["pvdb", "pvvi", "pvlo", "pvse", "pvac", "pvpo", "pvfo", "pvca", "pvqu"];
  for (const t of tenDinh(POSTER)) {
    assert.ok(t.toLowerCase().startsWith("pv"), t);
    for (const c of CON) assert.ok(!t.toLowerCase().startsWith(c), `"${t}" va tiền tố ${c}`);
  }
  assert.ok(!/\bpvLoiChu\b/.test(POSTER), "tên cũ pvLoiChu đã đổi thành pvChuLoi");
  assert.ok(!/\son[a-z]+="/.test(POSTER) && !/onclick\s*=/i.test(POSTER), "không gắn sự kiện inline (CSP)");
  assert.ok(!/\bfetch\(/.test(POSTER.replace(/async function pvGoi[\s\S]*?\n}\n/, "")), "chỉ pvGoi gọi fetch");
});

// ---------- pvGoi: hợp đồng §2.1 ----------
test("pvGoi: mọi method có x-pv: 1; GET/DELETE không content-type, không body; POST/PUT/PATCH JSON, rỗng → '{}'; URL /api/poster…", async () => {
  const { P, S } = napPoster({ xuLy: ok({ a: 1 }) });
  assert.deepEqual(await P.pvGoi("GET", "/api/v2/stats/"), { a: 1 });
  await P.pvGoi("DELETE", "/api/v2/queue/7");
  await P.pvGoi("POST", "/api/v2/queue/unstick");
  await P.pvGoi("PUT", "/api/v2/settings/headless", { value: true });
  await P.pvGoi("PATCH", "/api/v2/folders/3", { is_archived: 1 });
  await P.pvGoi("post", "/_dem", null);
  const [g, d, p, u, pa, p2] = S.goi;
  for (const r of S.goi) assert.equal(r.headers["x-pv"], "1", `${r.method} có x-pv`);
  for (const r of [g, d]) {
    assert.deepEqual(Object.keys(r.headers), ["x-pv"], `${r.method}: không content-type`);
    assert.equal(r.body, undefined, `${r.method}: không body`);
  }
  for (const r of [p, u, pa, p2]) assert.equal(r.headers["content-type"], "application/json", r.method);
  assert.deepEqual([g.url, d.url, p.url, u.url, pa.url, p2.url], ["/api/poster/api/v2/stats/", "/api/poster/api/v2/queue/7",
    "/api/poster/api/v2/queue/unstick", "/api/poster/api/v2/settings/headless", "/api/poster/api/v2/folders/3", "/api/poster/_dem"]);
  assert.deepEqual([g.method, d.method, p.method, u.method, pa.method, p2.method], ["GET", "DELETE", "POST", "PUT", "PATCH", "POST"]);
  assert.equal(p.body, "{}");
  assert.equal(u.body, `{"value":true}`);
  assert.equal(p2.body, "{}", "body null → {}");
  await assert.rejects(P.pvGoi("HEAD", "/health"), /Method/);
  await assert.rejects(P.pvGoi("GET", "api/v2/x"), /Đường dẫn/);
  assert.equal(S.goi.length, 6, "method/đường sai không fetch");
});

test("pvGoi: 401 → pvDung (xoá hẹn giờ, tăng pvPhien) + auth.user='' + renderUser + openLogin; ném 'Hết phiên…' status 401", async () => {
  const { P, S, clock, auth } = napPoster({ xuLy: () => ({ status: 401, body: { loi: "Chưa đăng nhập" } }) });
  let chay = 0;
  P.pvHenGio(() => { chay++; }, 1000);
  assert.equal(clock.soLap(), 1);
  const p0 = P.phien();
  const e = await P.pvGoi("GET", "/api/v2/stats/").catch((x) => x);
  assert.equal(e.message, "Hết phiên đăng nhập — đăng nhập lại");
  assert.equal(e.status, 401);
  assert.equal(P.phien(), p0 + 1, "pvPhien tăng");
  assert.equal(clock.soLap(), 0, "hẹn giờ bị xoá");
  assert.equal(auth.user, "");
  assert.equal(S.veUser, 1);
  assert.equal(S.dangNhap, 1);
  await clock.tien(5000);
  assert.equal(chay, 0);
  assert.deepEqual(S.toasts, []);
});

test("pvGoi: 4xx/5xx ném đúng chữ + e.status; lỗi mạng status 0 (tạm); 403 bản quyền giữ nguyên; HTML lỗi edge → HTTP <mã>", async () => {
  const BANG = [
    [{ status: 404, body: { detail: "Not Found" } }, "404: Not Found", 404, false],
    [{ status: 502, body: { loi: "Poster V2 trên máy nhà chưa mở" } }, "502: Poster V2 trên máy nhà chưa mở", 502, true],
    [{ status: 403, body: { detail: "License invalid" } }, "403: License invalid", 403, false],
    [{ status: 429, body: { loi: "Poster V2 đang bận" } }, "429: Poster V2 đang bận", 429, true],
    [{ status: 500, body: "Internal Server Error" }, "500: Internal Server Error", 500, false],
    [{ status: 524, body: "<!DOCTYPE html><html>timeout</html>" }, "HTTP 524", 524, true],
    [{ status: 500, body: "" }, "HTTP 500", 500, false],
  ];
  for (const [r, chu, st, tam] of BANG) {
    const { P } = napPoster({ xuLy: () => r });
    const e = await P.pvGoi("POST", "/api/v2/accounts/", { name: "a" }).catch((x) => x);
    assert.equal(e.message, chu);
    assert.equal(e.status, st);
    assert.equal(!!e.tam, tam, `${st} tạm=${tam}`);
  }
  const { P } = napPoster({ xuLy: () => ({ mang: true }) });
  const e = await P.pvGoi("GET", "/api/v2/stats/").catch((x) => x);
  assert.equal(e.status, 0);
  assert.equal(e.tam, true);
  assert.match(e.message, /Failed to fetch/);
});

// ---------- 202 → pvCho ----------
function kichBan(kq, dau = { status: 202, body: { cho: CHO, toi_da_giay: 300 } }) {
  const ds = [...kq];
  return (url) => {
    if (url === `/api/poster/_kq/${CHO}`) return ds.length > 1 ? ds.shift() : ds[0];
    if (url.startsWith("/api/poster/api/v2/")) return dau;
    return undefined;
  };
}

test("pvGoi 202 → hỏi _kq 3 s/lần tới khi xong (đồng hồ giả), trả body; 202 trung:true xử lý y vậy", async () => {
  for (const dau of [{ status: 202, body: { cho: CHO, toi_da_giay: 300 } }, { status: 202, body: { cho: CHO, toi_da_giay: 300, trung: true } }]) {
    const { P, S, clock } = napPoster({ xuLy: kichBan([{ status: 200, body: { xong: false } }, { status: 200, body: { xong: false } },
      { status: 200, body: { xong: true, status: 200, body: { ok: 1 } } }], dau) });
    let kq; let xong = false;
    P.pvGoi("POST", "/api/v2/queue/5/post").then((v) => { kq = v; xong = true; });
    await xa();
    assert.equal(S.goi.length, 1, "chưa hỏi _kq trước 3 s");
    await clock.tien(2999);
    assert.equal(S.goi.length, 1);
    await clock.tien(1);
    assert.equal(S.goi.length, 2);
    assert.equal(S.goi[1].url, `/api/poster/_kq/${CHO}`);
    assert.equal(S.goi[1].method, "GET");
    assert.deepEqual(S.goi[1].headers, { "x-pv": "1" });
    assert.equal(xong, false);
    await clock.tien(6000);
    assert.equal(S.goi.length, 4);
    assert.equal(xong, true);
    assert.deepEqual(kq, { ok: 1 });
    await clock.tien(9000);
    assert.equal(S.goi.length, 4, "xong rồi thì ngừng hỏi");
  }
});

test("pvCho: xong với mã lỗi → ném pvChuLoi(status, body); 504 câu 'CÓ THỂ đã chạy' giữ nguyên", async () => {
  const CAU = "Poster V2 chưa trả lời sau 300 s. Thao tác CÓ THỂ đã chạy: xem Logs/Queue trước khi bấm lại.";
  for (const [x, chu, st] of [[{ status: 400, body: { detail: "Video không tồn tại" } }, "400: Video không tồn tại", 400],
    [{ status: 504, body: { loi: CAU } }, `504: ${CAU}`, 504]]) {
    const { P, clock } = napPoster({ xuLy: kichBan([{ status: 200, body: { xong: true, ...x } }]) });
    const p = P.pvGoi("POST", "/api/v2/post/direct", { folder_id: 1 }).catch((e) => e);
    await clock.tien(3000);
    const e = await p;
    assert.equal(e.message, chu);
    assert.equal(e.status, st);
    assert.ok(!e.roiTrang);
  }
});

test("pvCho: quá (toi_da_giay + 60) s → 'Quá giờ chờ kết quả: xem Logs/Queue.'; ngừng hỏi", async () => {
  const { P, S, clock } = napPoster({ xuLy: kichBan([{ status: 200, body: { xong: false } }], { status: 202, body: { cho: CHO, toi_da_giay: 30 } }) });
  let loi;
  P.pvGoi("GET", "/api/v2/folders/?archived=0").catch((e) => { loi = e; });
  await clock.tien(90_000); // hạn = 30 + 60 s: lượt hỏi ở giây 90 vẫn chạy
  assert.equal(loi, undefined);
  await clock.tien(3000);
  assert.equal(loi.message, "Quá giờ chờ kết quả: xem Logs/Queue.");
  const n = S.goi.length;
  assert.ok(n >= 25 && n <= 32, `số lần hỏi ${n}`);
  await clock.tien(30_000);
  assert.equal(S.goi.length, n);
});

test("pvCho: lỗi tạm (502/mạng) khi hỏi → hỏi tiếp; lỗi vĩnh viễn (404 mất theo dõi) → ném ngay", async () => {
  let { P, clock } = napPoster({ xuLy: kichBan([{ mang: true }, { status: 502, body: { loi: "Máy nhà tắt" } },
    { status: 200, body: { xong: true, status: 200, body: { v: 2 } } }]) });
  let kq;
  P.pvGoi("POST", "/api/v2/queue/5/post").then((v) => { kq = v; });
  await clock.tien(9000);
  assert.deepEqual(kq, { v: 2 });
  ({ P, clock } = napPoster({ xuLy: kichBan([{ status: 404, body: { loi: "Không còn theo dõi được lệnh này (máy phát video vừa khởi động lại). Xem Logs/Queue." } }]) }));
  const p = P.pvGoi("POST", "/api/v2/queue/5/post").catch((e) => e);
  await clock.tien(3000);
  const e = await p;
  assert.match(e.message, /^404: Không còn theo dõi/);
  assert.ok(!e.roiTrang);
});

test("pvCho: đổi trang (pvDung) giữa lúc hỏi → ngừng gọi _kq, lỗi e.roiTrang, không toast / không hộp lỗi", async () => {
  const { P, S, clock } = napPoster({ xuLy: kichBan([{ status: 200, body: { xong: false } }]) });
  const p = P.pvGoi("POST", "/api/v2/queue/5/post").catch((e) => e);
  await clock.tien(3000);
  assert.equal(S.goi.length, 2);
  P.pvDung();
  const e = await p;
  assert.equal(e.roiTrang, true);
  await clock.tien(60_000);
  assert.equal(S.goi.length, 2, "không hỏi _kq nữa");
  assert.deepEqual(S.toasts, []);
  assert.deepEqual(S.hop, []);
  // rời trang trong lúc chờ phản hồi 202 đầu tiên → không bắt đầu hỏi
  let tra;
  const y = napPoster({ xuLy: (url) => (url.includes("/_kq/") ? { status: 200, body: { xong: false } } : new Promise((r) => { tra = r; })) });
  const q = y.P.pvGoi("POST", "/api/v2/queue/5/post").catch((x) => x);
  await xa();
  y.P.pvDung();
  tra({ status: 202, body: { cho: CHO, toi_da_giay: 300 } });
  assert.equal((await q).roiTrang, true);
  await y.clock.tien(10_000);
  assert.equal(y.S.goi.length, 1);
  // pvCho gọi trực tiếp: mã chờ sai → lỗi, không fetch
  await assert.rejects(y.P.pvCho("../x", 10), /không hợp lệ/);
  assert.equal(y.S.goi.length, 1);
});

// ---------- pvHenGio ----------
test("pvHenGio: bỏ lượt khi document.hidden / auth.on===false / lượt trước chưa xong (cờ đặt TRƯỚC await); fn ném thì lượt sau vẫn chạy; pvDung xoá", async () => {
  const { P, clock, auth, document } = napPoster();
  let n = 0;
  let tra = null;
  P.pvHenGio(() => { n++; return new Promise((r) => { tra = r; }); }, 1000);
  await clock.tien(1000);
  assert.equal(n, 1);
  await clock.tien(3000);
  assert.equal(n, 1, "lượt trước chưa xong → bỏ");
  tra();
  await clock.tien(1000);
  assert.equal(n, 2);
  tra();
  document.hidden = true;
  await clock.tien(3000);
  assert.equal(n, 2, "tab ẩn → bỏ");
  document.hidden = false;
  auth.user = "";
  await clock.tien(3000);
  assert.equal(n, 2, "đã đăng xuất → bỏ");
  auth.user = "nhan";
  await clock.tien(1000);
  assert.equal(n, 3);
  tra();
  // fn ném (đồng bộ và Promise bị từ chối) → nuốt lỗi, nhả cờ (hẹn giờ thứ nhất vẫn chạy song song)
  let m = 0;
  P.pvHenGio(() => { m++; if (m === 1) throw new Error("x"); return Promise.reject(new Error("y")); }, 500);
  await clock.tien(1500);
  assert.equal(m, 3);
  assert.equal(clock.soLap(), 2);
  P.pvDung();
  assert.equal(clock.soLap(), 0);
  const n1 = n;
  await clock.tien(5000);
  assert.equal(n, n1, "đã xoá: không chạy nữa");
  assert.equal(m, 3);
});

// ---------- pvApi: bảng §2.2 #1–#45 + route riêng ----------
test("pvApi: mỗi phương thức → đúng (method, path, body) như bảng §2.2 và api_client.py", async () => {
  const { P, S } = napPoster({ xuLy: ok({}) });
  const A = P.pvApi;
  const BANG = [
    // [#, lời gọi, method, path, body (undefined = không body)]
    [1, () => P.pvGoi("GET", "/health"), "GET", "/health"],
    [2, () => A.healthCheck(), "GET", "/api/v2/system/health"],
    [3, () => A.getStats(), "GET", "/api/v2/stats/"],
    [4, () => A.listLogs(), "GET", "/api/v2/logs/?limit=100&offset=0"],
    [4, () => A.listLogs(25), "GET", "/api/v2/logs/?limit=25&offset=0"],
    [4, () => A.listLogs(100, 200, "failed"), "GET", "/api/v2/logs/?limit=100&offset=200&status=failed"],
    [5, () => A.affiliateStats(), "GET", "/api/v2/logs/affiliate-stats"],
    [5, () => A.affiliateStats("1729"), "GET", "/api/v2/logs/affiliate-stats?product_id=1729"],
    [6, () => A.listAccounts(), "GET", "/api/v2/accounts/"],
    [7, () => A.createAccount({ name: "a" }), "POST", "/api/v2/accounts/", { name: "a" }],
    [8, () => A.updateAccount(3, { name: "b" }), "PUT", "/api/v2/accounts/3", { name: "b" }],
    [9, () => A.deleteAccount(3), "DELETE", "/api/v2/accounts/3"],
    [10, () => A.testCookies(3), "POST", "/api/v2/accounts/3/test-cookies", {}],
    [11, () => A.accountCooldown(3), "POST", "/api/v2/accounts/3/cooldown", { hours: 24 }],
    [11, () => A.accountCooldown(3, 6), "POST", "/api/v2/accounts/3/cooldown", { hours: 6 }],
    [12, () => A.accountClearCooldown(3), "DELETE", "/api/v2/accounts/3/cooldown"],
    [13, () => A.cleanAllProfiles(), "POST", "/api/v2/accounts/clean_profiles", {}],
    [14, () => A.loginAndCapture("acc1"), "POST", "/api/v2/accounts/login_and_capture", { name: "acc1", proxy: "", use_fingerprint: false }],
    [14, () => A.loginAndCapture("acc1", "1.2.3.4:80", true), "POST", "/api/v2/accounts/login_and_capture", { name: "acc1", proxy: "1.2.3.4:80", use_fingerprint: true }],
    [15, () => A.cookiesFromJson("acc1", [{ name: "c" }]), "POST", "/api/v2/accounts/cookies_from_json", { name: "acc1", cookies: [{ name: "c" }] }],
    [16, () => A.viewsAccountHealth(3), "GET", "/api/v2/views/health/3"],
    [17, () => A.listFolders(), "GET", "/api/v2/folders/"],
    [17, () => A.getFolders(0), "GET", "/api/v2/folders/?archived=0"],
    [17, () => A.getFolders(1), "GET", "/api/v2/folders/?archived=1"],
    [18, () => A.createFolder({ path: "E:/v" }), "POST", "/api/v2/folders/", { path: "E:/v" }],
    [19, () => A.updateFolder(4, { path: "E:/w" }), "PUT", "/api/v2/folders/4", { path: "E:/w" }],
    [20, () => A.archiveFolder(4), "PATCH", "/api/v2/folders/4", { is_archived: 1 }],
    [20, () => A.archiveFolder(4, false), "PATCH", "/api/v2/folders/4", { is_archived: 0 }],
    [21, () => A.deleteFolder(4), "DELETE", "/api/v2/folders/4"],
    [22, () => A.folderSuggestPhase(4, 10), "GET", "/api/v2/folders/4/suggest_phase?n=10"],
    [23, () => A.cadenceForecast(), "GET", "/api/v2/folders/cadence_forecast?days=14"],
    [23, () => A.cadenceForecast(7), "GET", "/api/v2/folders/cadence_forecast?days=7"],
    [24, () => A.driveTest(4), "GET", "/api/v2/folders/4/drive-test"],
    [25, () => A.postNow(4), "POST", "/api/v2/folders/4/post_now", { visibility: "everyone" }],
    [25, () => A.postNow(4, "friends"), "POST", "/api/v2/folders/4/post_now", { visibility: "friends" }],
    [26, () => A.batchSchedule({ folder_ids: [4] }), "POST", "/api/v2/folders/batch_schedule", { folder_ids: [4] }],
    [27, () => A.listQueue(), "GET", "/api/v2/queue/?limit=100&offset=0"],
    [27, () => A.listQueue("pending", 100, 100), "GET", "/api/v2/queue/?limit=100&offset=100&status=pending"],
    [28, () => A.statusCounts(), "GET", "/api/v2/queue/status"],
    [29, () => A.postQueueItem(9), "POST", "/api/v2/queue/9/post", {}],
    [30, () => A.queueRetry(9), "POST", "/api/v2/queue/9/retry", {}],
    [31, () => A.deleteQueueItem(9), "DELETE", "/api/v2/queue/9"],
    [32, () => A.queueUnstick(), "POST", "/api/v2/queue/unstick", {}],
    [33, () => A.queueClearPending(), "DELETE", "/api/v2/queue/pending/clear"],
    [34, () => A.queueResetAll(), "POST", "/api/v2/queue/reset-all", {}],
    [35, () => A.queueRandomShuffle(), "POST", "/api/v2/queue/random_shuffle", {}],
    [36, () => A.getSettingsAll(), "GET", "/api/v2/settings/"],
    [37, () => A.autopostOn(), "POST", "/api/v2/settings/autopost-on", {}],
    [38, () => A.autopostOff(), "POST", "/api/v2/settings/autopost-off", {}],
    [39, () => A.putSetting("telegram_chat_id", "123"), "PUT", "/api/v2/settings/telegram_chat_id", { value: "123" }],
    [39, () => A.putSetting("headless", false), "PUT", "/api/v2/settings/headless", { value: false }],
    [40, () => A.calendarMonth(2026, 11), "GET", "/api/v2/calendar/month?year=2026&month=11"],
    [40, () => A.calendarMonth(2026, 11, 3), "GET", "/api/v2/calendar/month?year=2026&month=11&account_id=3"],
    [41, () => A.createCalendarPlan({ date: "2026-11-20" }), "POST", "/api/v2/calendar/plans", { date: "2026-11-20" }],
    [42, () => A.deleteCalendarPlan(8), "DELETE", "/api/v2/calendar/plans/8"],
    [43, () => A.viewsSummary(), "GET", "/api/v2/views/summary"],
    [44, () => A.viewsRefresh(), "POST", "/api/v2/views/refresh", {}],
    [45, () => A.postVideoDirect(4, "E:/v/a.mp4", "cap"), "POST", "/api/v2/post/direct",
      { folder_id: 4, video_path: "E:/v/a.mp4", caption: "cap", visibility: "everyone", first_comment: "", draft: false }],
    [45, () => A.postVideoDirect(4, "E:/v/a.mp4", "cap", "friends", "hi", true), "POST", "/api/v2/post/direct",
      { folder_id: 4, video_path: "E:/v/a.mp4", caption: "cap", visibility: "friends", first_comment: "hi", draft: true }],
    ["_video", () => A.dsVideoFolder(4), "GET", "/_video/4"],
    ["_dem", () => A.demVideo("E:\\v"), "POST", "/_dem", { duong_dan: "E:\\v" }],
    ["_thong_tin", () => A.thongTin(), "GET", "/_thong_tin"],
    ["_kq", () => A.dangChay(), "GET", "/_kq"],
  ];
  const so = new Set(BANG.map((b) => b[0]).filter((x) => typeof x === "number"));
  for (let i = 1; i <= 45; i++) assert.ok(so.has(i), `bảng test thiếu dòng #${i}`);
  for (const [stt, f, method, path, body] of BANG) {
    S.goi.length = 0;
    await f();
    assert.equal(S.goi.length, 1, `#${stt}`);
    const r = S.goi[0];
    assert.equal(r.method, method, `#${stt} method`);
    assert.equal(r.url, `/api/poster${path}`, `#${stt} path`);
    if (body === undefined) assert.equal(r.body, undefined, `#${stt} không body`);
    else assert.deepEqual(JSON.parse(r.body), body, `#${stt} body`);
  }
  // Đủ danh sách §6.4 + batBackend (nút "Bật Poster V2"), không thêm (50 phương thức).
  assert.deepEqual(Object.keys(A).sort(), ["listAccounts", "createAccount", "updateAccount", "deleteAccount", "testCookies", "accountCooldown",
    "accountClearCooldown", "cleanAllProfiles", "loginAndCapture", "cookiesFromJson", "viewsAccountHealth", "listFolders", "getFolders",
    "createFolder", "updateFolder", "archiveFolder", "deleteFolder", "folderSuggestPhase", "cadenceForecast", "driveTest", "postNow",
    "batchSchedule", "listQueue", "statusCounts", "postQueueItem", "queueRetry", "deleteQueueItem", "queueUnstick", "queueClearPending",
    "queueResetAll", "queueRandomShuffle", "getSettingsAll", "putSetting", "autopostOn", "autopostOff", "calendarMonth", "createCalendarPlan",
    "deleteCalendarPlan", "viewsSummary", "viewsVideos", "viewsRefresh", "getStats", "healthCheck", "listLogs", "affiliateStats", "postVideoDirect",
    "dsVideoFolder", "demVideo", "thongTin", "dangChay", "batBackend"].sort());
});

test("pvApi: id / khoá Settings lạ (path traversal) → lỗi, không fetch", async () => {
  const { P, S } = napPoster({ xuLy: ok({}) });
  for (const f of [() => P.pvApi.deleteAccount("../x"), () => P.pvApi.deleteQueueItem("1/../../health"), () => P.pvApi.updateFolder(-1, {}),
    () => P.pvApi.postQueueItem(1.5), () => P.pvApi.dsVideoFolder("4?x=1"), () => P.pvApi.putSetting("../x", 1), () => P.pvApi.putSetting("..", 1),
    () => P.pvApi.putSetting("a/b", 1), () => P.pvApi.putSetting("", 1)]) {
    await assert.rejects(f(), /không hợp lệ/);
  }
  assert.equal(S.goi.length, 0);
  await P.pvApi.deleteAccount("12");
  assert.equal(S.goi[0].url, "/api/poster/api/v2/accounts/12", "id dạng chuỗi số vẫn nhận");
});

// ---------- pvRender: thanh trạng thái + tab + #pv-noi ----------
test("pvRender: vẽ thanh trạng thái + 9 tab + #pv-noi, gọi pv<xx>Ve(khung, phien); trang chưa có → mnCHUA_CO; health 30 s qua pvHenGio", async () => {
  const ve = [];
  const trang = { pvQuVe: async (k, ph) => { ve.push([k, ph]); k.innerHTML = "QUEUE"; } };
  const { P, S, app, clock } = napPoster({ trang, xuLy: (url) => (url.endsWith("/api/v2/system/health") ? { status: 200, body: { status: "ok" } }
    : url.endsWith("/_thong_tin") ? { status: 200, body: { backend: "http://127.0.0.1:8023", co_token: true } } : undefined) });
  P.pvDung();
  await P.pvRender("queue");
  assert.match(app.innerHTML, /id="pv-tt-chu"/);
  assert.match(app.innerHTML, /<a class="pv-tab" href="#\/poster\/queue" data-pv-tab="queue" aria-current="page">Queue<\/a>/);
  assert.match(app.innerHTML, /<section id="pv-noi"/);
  assert.equal(ve.length, 1);
  assert.equal(ve[0][0], S.el["pv-noi"]);
  assert.equal(ve[0][1], P.phien());
  assert.equal(S.el["pv-noi"].innerHTML, "QUEUE");
  await xa();
  assert.equal(S.el["pv-tt-chu"].innerHTML, "V2 OK (ok)");
  assert.equal(S.el["pv-tt-chu"].dataset.tt, "ok");
  assert.equal(S.el["pv-tt-url"].innerHTML, "V2 Backend: http://127.0.0.1:8023");
  const dem = () => S.goi.filter((r) => r.url.endsWith("/system/health")).length;
  assert.equal(dem(), 1);
  assert.equal(clock.soLap(), 1, "1 hẹn giờ thanh trạng thái");
  await clock.tien(30_000);
  assert.equal(dem(), 2);
  // trang chưa có file
  for (const id of ["", "la", "logs"]) {
    const x = napPoster({ xuLy: (url) => (url.endsWith("/system/health") ? { status: 200, body: { status: "ok" } } : { status: 200, body: {} }) });
    await x.P.pvRender(id);
    assert.equal(x.S.el["pv-noi"].innerHTML, CHUA_CO, id);
    assert.match(x.app.innerHTML, new RegExp(`data-pv-tab="${id === "logs" ? "logs" : "dashboard"}" aria-current`));
  }
});

test("pvRender: lỗi lạ → 'Poster V2 lỗi: <lỗi ≤120>' đã esc (XSS BAN) + nút bật; _thong_tin có chuỗi độc cũng esc", async () => {
  const { P, S } = napPoster({ xuLy: (url) => (url.endsWith("/system/health") ? { status: 502, body: { loi: `${BAN}${"y".repeat(200)}` } }
    : url.endsWith("/_thong_tin") ? { status: 200, body: { backend: BAN } } : undefined) });
  await P.pvRender("dashboard");
  await xa();
  const chu = S.el["pv-tt-chu"].innerHTML;
  assert.ok(chu.startsWith("Poster V2 lỗi: 502: &lt;img"), chu);
  assert.ok(!chu.includes(BAN));
  assert.equal(S.el["pv-tt-chu"].dataset.tt, "down");
  assert.equal(S.el["pv-tt-chu"].innerHTML, esc(`Poster V2 lỗi: ${`502: ${BAN}${"y".repeat(200)}`.slice(0, 120)}`));
  assert.equal(S.el["pv-tt-nut"].hidden, false);
  assert.ok(!S.el["pv-tt-url"].innerHTML.includes(BAN));
});

// ---------- thanh trạng thái: chặng nào hỏng + nút "Bật Poster V2" ----------
const HEALTH = "/api/poster/api/v2/system/health";
const THONG_TIN = { status: 200, body: { backend: "http://127.0.0.1:8023", co_token: true } };
test("thanh trạng thái: mỗi chặng hỏng một câu riêng; chỉ hiện nút khi bật được", async () => {
  const ca = [
    [{ mang: true }, "Không kết nối được web kho (mất mạng?)", "down", true],
    [{ status: 502, body: { loi: "Poster V2 trên máy nhà chưa mở", ma: "chua_mo" } }, "Poster V2 chưa chạy trên máy nhà", "down", false],
    [{ status: 502, body: { loi: "Poster V2 trên máy nhà chưa mở" } }, "Poster V2 chưa chạy trên máy nhà", "down", false],
    [{ status: 502, body: { loi: "Máy nhà không trả lời (đã bật video_server và tunnel chưa?)" } },
      "Máy nhà không trả lời: video_server hoặc tunnel đang tắt. Trên máy nhà chạy tools/chay_video.bat", "down", true],
    [{ status: 502, body: { loi: "Poster V2 từ chối token (TT_API_BEARER_TOKEN lệch)", ma: "token" } },
      "Poster V2 từ chối token: TT_API_BEARER_TOKEN trong .env của Poster bị lệch", "down", true],
    [{ status: 504, body: { loi: "Máy nhà phản hồi quá chậm" } }, "Máy nhà phản hồi chậm, thử lại sau", "cham", true],
    [{ status: 503, body: { loi: "Poster trên web đang tắt ở máy nhà" } }, "Poster trên web đang tắt ở máy nhà", "down", true],
  ];
  for (const [tra, chu, tt, nutAn] of ca) {
    const { P, S } = napPoster({ xuLy: (url) => (url === HEALTH ? tra : url.endsWith("/_thong_tin") ? THONG_TIN : undefined) });
    await P.pvRender("dashboard");
    await xa();
    assert.equal(S.el["pv-tt-chu"].innerHTML, esc(chu), JSON.stringify(tra));
    assert.equal(S.el["pv-tt-chu"].dataset.tt, tt, chu);
    assert.equal(S.el["pv-tt-nut"].hidden, nutAn, `nút ẩn=${nutAn}: ${chu}`);
  }
});

test("nút Bật Poster V2: POST /_bat_backend {} rồi hỏi health 2 s/lần tới khi OK; nút ẩn khi xong", async () => {
  let len = false;
  const { P, S, clock } = napPoster({ xuLy: (url, opt) => {
    if (url === HEALTH) return len ? { status: 200, body: { status: "ok" } } : { status: 502, body: { loi: "Poster V2 trên máy nhà chưa mở", ma: "chua_mo" } };
    if (url === "/api/poster/_bat_backend") return { status: 200, body: { trang_thai: "dang_bat", pid: 9 } };
    if (url.endsWith("/_thong_tin")) return THONG_TIN;
    return undefined;
  } });
  await P.pvRender("dashboard");
  await xa();
  const nut = S.el["pv-tt-nut"];
  assert.equal(nut.hidden, false);
  nut.nghe.click();
  await xa();
  const bat = S.goi.filter((r) => r.url === "/api/poster/_bat_backend");
  assert.equal(bat.length, 1);
  assert.equal(bat[0].method, "POST");
  assert.equal(bat[0].body, "{}");
  assert.match(S.el["pv-tt-chu"].innerHTML, /^Đang khởi động Poster V2\.\.\. \(45 s\)$/);
  assert.equal(S.el["pv-tt-chu"].dataset.tt, "cham");
  assert.equal(nut.hidden, true, "đang bật thì ẩn nút");
  await clock.tien(2_000);
  assert.match(S.el["pv-tt-chu"].innerHTML, /^Đang khởi động Poster V2\.\.\. \(43 s\)$/);
  len = true;
  const truoc = S.goi.filter((r) => r.url === HEALTH).length;
  await clock.tien(2_000);
  assert.equal(S.goi.filter((r) => r.url === HEALTH).length, truoc + 1);
  assert.equal(S.el["pv-tt-chu"].innerHTML, "V2 OK (ok)");
  assert.equal(nut.hidden, true);
  await clock.tien(10_000);
  assert.equal(S.goi.filter((r) => r.url === HEALTH).length, truoc + 1, "OK rồi thì thôi hỏi 2 s/lần");
});

test("nút Bật Poster V2: không lên sau 45 s → báo xem console, hiện lại nút", async () => {
  const { P, S, clock } = napPoster({ xuLy: (url) => (url === HEALTH ? { status: 502, body: { loi: "x", ma: "chua_mo" } }
    : url === "/api/poster/_bat_backend" ? { status: 200, body: { trang_thai: "dang_bat" } } : url.endsWith("/_thong_tin") ? THONG_TIN : undefined) });
  await P.pvRender("dashboard");
  await xa();
  S.el["pv-tt-nut"].nghe.click();
  await clock.tien(46_000);
  assert.equal(S.el["pv-tt-chu"].innerHTML, esc("Poster V2 không lên sau 45 s: xem cửa sổ console của backend trên máy nhà"));
  assert.equal(S.el["pv-tt-nut"].hidden, false);
});

test("nút Bật Poster V2: cổng bị chương trình khác chiếm (409 cong_la) → hiện tên + PID; bản cũ (404) → bảo deploy", async () => {
  for (const [tra, chu] of [
    [{ status: 409, body: { loi: "Cổng 8023 đang bị relay.exe (PID 7) chiếm, không phải Poster V2: tắt nó trên máy nhà rồi bấm bật lại", ma: "cong_la" } },
      "Cổng 8023 đang bị relay.exe (PID 7) chiếm, không phải Poster V2: tắt nó trên máy nhà rồi bấm bật lại"],
    [{ status: 404, body: { loi: "Đường dẫn Poster không được phép" } },
      "Máy nhà/Worker là bản cũ, chưa có lệnh bật: deploy Worker và khởi động lại video_server"],
  ]) {
    const { P, S } = napPoster({ xuLy: (url) => (url === HEALTH ? { status: 502, body: { loi: "x", ma: "chua_mo" } }
      : url === "/api/poster/_bat_backend" ? tra : url.endsWith("/_thong_tin") ? THONG_TIN : undefined) });
    await P.pvRender("dashboard");
    await xa();
    S.el["pv-tt-nut"].nghe.click();
    await xa();
    assert.equal(S.el["pv-tt-chu"].innerHTML, esc(chu));
    assert.equal(S.el["pv-tt-nut"].disabled, false);
    assert.equal(S.el["pv-tt-nut"].textContent, "Bật Poster V2");
  }
});

test("pvRender: rời trang trong lúc trang con đang tải → trang con nhận phiên cũ (pvConSong=false); lỗi của trang cũ không vẽ", async () => {
  let tra;
  const trang = { pvDbVe: async () => { await new Promise((r) => { tra = r; }); throw new Error(BAN); } };
  const { P, S } = napPoster({ trang, xuLy: () => ({ status: 200, body: { status: "ok" } }) });
  const p = P.pvRender("");
  const ph = P.phien();
  assert.equal(P.pvConSong(ph), true);
  P.pvDung();
  assert.equal(P.pvConSong(ph), false);
  tra();
  await p;
  assert.equal(S.el["pv-noi"].innerHTML, "", "không vẽ lỗi của trang đã rời");
  // trang còn sống mà ném → hiện lỗi đã esc
  const y = napPoster({ trang: { pvDbVe: async () => { throw new Error(BAN); } }, xuLy: () => ({ status: 200, body: {} }) });
  await y.P.pvRender("dashboard");
  assert.match(y.S.el["pv-noi"].innerHTML, /&lt;img/);
  assert.ok(!y.S.el["pv-noi"].innerHTML.includes(BAN));
});

test("pvDung: gọi pv<xx>Dung của các trang đang có (qua globalThis), lỗi của 1 trang không chặn trang khác", () => {
  const goi = [];
  const trang = { pvQuDung: () => { goi.push("qu"); throw new Error("x"); }, pvPoDung: () => goi.push("po") };
  const { P } = napPoster({ trang });
  const loiCu = console.error;
  console.error = () => {};
  try { P.pvDung(); } finally { console.error = loiCu; }
  assert.deepEqual(goi.sort(), ["po", "qu"]);
});

// ---------- hộp thoại ----------
test("pvXacNhan: port confirm_destructive — 2 cách gọi, 'Mục bị ảnh hưởng', chữ nút mặc định, Hủy → false, chuỗi đã esc", async () => {
  const { P, S } = napPoster();
  let p = P.pvXacNhan(`Xóa account ${BAN}?`);
  let h = S.hop[0];
  assert.equal(h.open, true);
  assert.match(h.innerHTML, /<h3 class="pv-hop-tieu-de">Xác nhận<\/h3>/);
  assert.ok(!h.innerHTML.includes(BAN));
  assert.match(h.innerHTML, /data-pv-nut="co">Xóa</);
  assert.match(h.innerHTML, /data-pv-nut="khong">Hủy</);
  bam(h, "khong");
  assert.equal(await p, false);
  assert.equal(h.daXoa, true);
  assert.equal(h.open, false);

  p = P.pvXacNhan(BAN, "Đăng ngay video này?", BAN, undefined, "Thôi");
  h = S.hop[1];
  assert.ok(!h.innerHTML.includes(BAN));
  assert.match(h.innerHTML, /Đăng ngay video này\?\n\nMục bị ảnh hưởng: &lt;img[^]*\n\nBạn có chắc chắn muốn thực hiện\?/);
  assert.match(h.innerHTML, /data-pv-nut="co">Xác nhận</, "câu có 'đăng' → nút Xác nhận");
  assert.match(h.innerHTML, /data-pv-nut="khong">Thôi</);
  bam(h, "co");
  assert.equal(await p, true);

  p = P.pvXacNhan("Reset", "Thêm tất cả vào queue?", "", "Làm luôn");
  h = S.hop[2];
  assert.match(h.innerHTML, /data-pv-nut="co">Làm luôn</);
  assert.ok(!/Mục bị ảnh hưởng/.test(h.innerHTML), "ten rỗng → không thêm dòng");
  h.nghe.cancel({ preventDefault() {} }); // phím Esc
  assert.equal(await p, false);
});

test("pvThongBao / pvHop: tiêu đề + câu đã esc, nút OK; pvHop trả {el, dong, cho}; dong() → null; pvDung đóng hộp đang mở", async () => {
  const { P, S } = napPoster();
  const t = P.pvThongBao(BAN, `Lỗi: ${BAN}`, "critical");
  const h = S.hop[0];
  assert.ok(!h.innerHTML.includes(BAN));
  assert.match(h.innerHTML, /pv-hop-critical/);
  assert.match(h.innerHTML, /data-pv-nut="ok">OK</);
  bam(h, "ok");
  assert.equal(await t, undefined);
  const k = P.pvThongBao("a", "b", `x" onmouseover="1`);
  assert.match(S.hop[1].innerHTML, /pv-hop-info/, "kiểu lạ → info");
  S.hop[1].nghe.close();
  await k;

  const x = P.pvHop({ tieuDe: BAN, html: `<b>ok</b>`, nut: [{ ma: "luu", chu: BAN, chinh: true }, { ma: "huy", chu: "Hủy" }] });
  assert.equal(x.el, S.hop[2]);
  assert.match(x.el.innerHTML, /<b>ok<\/b>/, "html do trang tự esc");
  assert.ok(!x.el.innerHTML.includes(BAN));
  assert.match(x.el.innerHTML, /class="btn" data-pv-nut="luu"/);
  assert.match(x.el.innerHTML, /class="btn ghost" data-pv-nut="huy"/);
  x.dong();
  assert.equal(await x.cho, null);
  bam(x.el, "luu"); // đóng rồi bấm cũng không đổi kết quả
  const y = P.pvHop({ tieuDe: "t", html: "", nut: [{ ma: "a", chu: "A" }] });
  const z = P.pvXacNhan("Xóa?");
  P.pvDung();
  assert.equal(await y.cho, null);
  assert.equal(await z, false);
  assert.ok(S.hop.every((e) => e.daXoa));
});

// ---------- móc khung.js (§6.1) ----------
const K = new Function("esc", `"use strict";\n${khoi(KHUNG, "khung-thuan")}\nreturn { mnMENU, mnMuc, mnNavHtml, mnPhanTichHash };`)(esc);

test("khung.js: mnPhanTichHash/mnMuc nhận #/poster, #/poster/<x>; nav chủ 5 mục (mục 5 Poster V2), người thường 1 mục", () => {
  assert.deepEqual(K.mnPhanTichHash("#/poster"), { trang: "poster", id: "" });
  assert.deepEqual(K.mnPhanTichHash("#/poster/queue"), { trang: "poster", id: "queue" });
  assert.deepEqual(K.mnPhanTichHash("#/poster/"), { trang: "poster", id: "" });
  assert.deepEqual(K.mnPhanTichHash("#/poster/a/b"), { trang: "", id: "" });
  assert.deepEqual(K.mnPhanTichHash("#/posterx"), { trang: "", id: "" });
  assert.equal(K.mnMuc("#/poster/queue", true), "poster");
  assert.equal(K.mnMuc("#/poster", true), "poster");
  assert.equal(K.mnMuc("#/poster", false), "");
  assert.deepEqual(K.mnMENU[4], { ma: "poster", href: "#/poster", ic: "📮", ten: "Poster V2", ngan: "Poster" });
  const h = K.mnNavHtml(true);
  assert.equal((h.match(/<a\b/g) || []).length, 5); // 2026-11-19: gỡ Duyệt video + Đăng bài
  assert.match(h, /<a href="#\/poster" data-nav="poster" aria-label="Poster V2">[^]*Poster V2[^]*<\/a>$/);
  assert.equal(K.mnNavHtml(false), `<a href="#/kho" data-nav="kho">Sản phẩm</a>`);
});

function dungRoute({ pv = true } = {}) {
  const goi = [];
  const app = theGia();
  const ns = { $: (s) => (s === "#app" ? app : null), esc, CHI_CHU_HTML };
  if (pv) Object.assign(ns, { pvDung: () => goi.push("pvDung"), pvRender: async (id) => goi.push(`pvRender:${id}`) });
  const ten = Object.keys(ns);
  const R = new Function(...ten, `"use strict";\nlet phienCT = 0;\n${KHUNG}\nreturn { mnRoute, phien: () => phienCT };`)(...ten.map((k) => ns[k]));
  return { R, goi, app };
}

test("mnRoute: pvDung ở đầu MỌI lần route; chủ #/poster[/x] → pvRender(id chưa giải mã); người thường → CHI_CHU_HTML; chưa có poster.js → mnCHUA_CO", async () => {
  let x = dungRoute();
  assert.equal(await x.R.mnRoute("#/poster", true), true);
  assert.equal(await x.R.mnRoute("#/poster/queue", true), true);
  assert.equal(await x.R.mnRoute("#/poster/%71ueue", true), true);
  assert.deepEqual(x.goi, ["pvDung", "pvRender:", "pvDung", "pvRender:queue", "pvDung", "pvRender:%71ueue"]);
  assert.equal(x.R.phien(), 3);
  x = dungRoute();
  assert.equal(await x.R.mnRoute("#/kho", true), false);
  assert.deepEqual(x.goi, ["pvDung"], "rời Poster sang trang cũ cũng dừng hẹn giờ");
  for (const h of ["#/poster", "#/poster/queue"]) {
    x = dungRoute();
    assert.equal(await x.R.mnRoute(h, false), true);
    assert.equal(x.app.innerHTML, CHI_CHU_HTML);
    assert.deepEqual(x.goi, ["pvDung"], "người thường không vẽ Poster");
  }
  x = dungRoute({ pv: false });
  assert.equal(await x.R.mnRoute("#/poster/queue", true), true);
  assert.match(x.app.innerHTML, /Trang đang được cập nhật/);
});

// ---------- index.html (§6.2) + poster.css ----------
test("index.html: poster.css sau menu.css; poster.js + 9 pv-*.js giữa khung.js và app.js đúng thứ tự §6.2; khung.js?v=4 (2026-11-19 gỡ dang.js, duyet.js)", () => {
  assert.match(HTML, /<link rel="stylesheet" href="menu\.css\?v=1">\s*<link rel="stylesheet" href="poster\.css\?v=2">/);
  const js = [...HTML.matchAll(/<script src="([^"?]+)\?v=\d+" defer><\/script>/g)].map((m) => m[1]).filter((s) => !s.startsWith("vendor/"));
  const i = js.indexOf("khung.js");
  assert.deepEqual(js.slice(i, i + 12), ["khung.js", "poster.js", "pv-dashboard.js", "pv-accounts.js", "pv-folders.js", "pv-calendar.js",
    "pv-views.js", "pv-queue.js", "pv-post.js", "pv-logs.js", "pv-settings.js", "app.js"]);
  assert.match(HTML, /khung\.js\?v=5"/);
  assert.match(HTML, /poster\.js\?v=2" defer/, "2026-11-19 nút Bật Poster V2: nâng ?v");
  for (const f of ["pv-dashboard.js", "pv-settings.js"]) assert.match(HTML, new RegExp(`${f.replace(".", "\\.")}\\?v=1" defer`));
});

test("poster.css: chỉ lớp .pv-*, không position: fixed (không đè .nav), có .pv-cuon { overflow-x: auto; tab xuống dòng, không cuộn ngang", () => {
  const bo = CSS.replace(/\/\*[\s\S]*?\*\//g, "");
  assert.ok(!/position\s*:\s*fixed/.test(bo));
  assert.match(bo, /\.pv-cuon \{ overflow-x: auto/);
  assert.match(bo, /\.pv-tabs \{[^}]*flex-wrap: wrap/);
  assert.ok(!/\.pv-tabs \{[^}]*overflow-x/.test(bo));
  const boMedia = bo.replace(/@media[^{]*\{/g, "");
  const chon = boMedia.split("}").map((r) => r.split("{")[0].trim()).filter(Boolean);
  assert.ok(chon.length >= 10, `đọc được ${chon.length} bộ chọn`);
  for (const sel of chon) for (const s of sel.split(",")) assert.match(s.trim(), /^(dialog)?\.pv-/, `bộ chọn ngoài .pv-: ${s}`);
});
