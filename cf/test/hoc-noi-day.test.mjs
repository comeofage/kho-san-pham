// HT-T1 — Test nối dây xuyên chặng "Học tự động mỗi ngày" (D15, docs/hoc-tu-dong.md §8.4, §3.8, §3.10, §6.2).
// Chạy: node --test cf/test/hoc-noi-day.test.mjs   (từ gốc repo)
// Đường đi chạy MÃ THẬT cả 4 tầng:
//   web/hoc.js (hcRender/hcTai/hcBam + api() của web/app.js, nạp trong vm) → worker.fetch THẬT (cf/src/worker.js → apiHoc của
//   cf/src/hoc.js + goiMayNha/traVeMayNha/kyRequest thật, ký Ed25519 bằng khoá riêng test) → video_server.H thật (cổng ngẫu nhiên)
//   → runner api.tao_handler thật (KhoHoc trên hoc.db tạm, khoá công khai test) ← runner.hoc_tu_dong.chay() thật chạy từng "ngày"
//   trên fixture §8.2 (DB Poster giả + repo giả, bay_gio giả) — tất cả trong tools/hoc_noi_gia.py (KHO_HOC_TEST=1, thư mục tạm).
// Không mạng ngoài: globalThis.fetch bị thay TRƯỚC khi nạp Worker; chỉ cho http://127.0.0.1:<video>/r/hoc/*; URL khác ném lỗi.
// Không phụ thuộc giờ thật: mọi "ngày" là ngày cố định 2026-12-01..18 (đồng hồ giả của harness); trong vm Date.now = đồng hồ đó.
// Riêng chữ ký D7 dùng giờ thật (runner kiểm lệch ≤ 120 s so với time.time()) — đó là hợp đồng, không giả.
//
// Kịch bản dữ liệu (mỗi ngày một lô video tới tuổi 7 đúng ngày đó, lô cũ bị harness "rút" — xem tools/hoc_noi_gia.py):
//   cap_co_so (bài A): đạt mọi ngày → ứng viên ngày 1, 2 → hiệu lực ngày 3 (đúng 1 bài học sau 3 ngày, ca 1).
//   cap_cau_hoi (bài B): không hiệu ứng ngày 1–3; đều 20/20 SP ngày 4–6 → hiệu lực ngày 6; "pha" (11/20 = 55% < 60%) ngày 7–8.
//   Hợp đồng §8.4 ca 7 ghi "ngày 5 / ngày 6"; ở đây là ngày 7 / ngày 8 vì hoc_bat_ngay = 1/ngày và ca 1 đòi ĐÚNG 1 bài sau 3 ngày
//   (bài B phải bắt đầu từ ngày 4 → đủ 3 ngày liền ở ngày 6). Ý nghĩa ca không đổi.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { performance } from "node:perf_hooks";
import vm from "node:vm";

const fetchGoc = globalThis.fetch;
let CONG = null; // { video, khoa_rieng_pkcs8, video_key, runner_key, dieu_khien, tam } do harness in ra
const chang2 = []; // request Worker → video_server (chặng 2) + phản hồi
globalThis.fetch = async (input, init = {}) => {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  const u = new URL(url);
  const laVideo = CONG && u.protocol === "http:" && u.hostname === "127.0.0.1" && Number(u.port) === CONG.video
    && u.pathname.startsWith("/r/hoc/");
  if (!laVideo) throw new Error(`fetch thật bị cấm trong test: ${url}`);
  const h = new Headers(init.headers || {});
  const rec = { method: init.method || "GET", path: u.pathname, search: u.search,
    headers: Object.fromEntries(h.entries()), body: init.body == null ? null : String(init.body) };
  chang2.push(rec);
  const r = await fetchGoc(url, init);
  rec.status = r.status;
  rec.txt = await r.clone().text();
  return r;
};
globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };
// Nạp Worker SAU khi đã khoá fetch.
const { default: worker, taoPhien, bamMatKhau } = await import("../src/worker.js");

const GOC_REPO = fileURLToPath(new URL("../../", import.meta.url));
const APP = readFileSync(new URL("../../web/app.js", import.meta.url), "utf8");
const HOC = readFileSync(new URL("../../web/hoc.js", import.meta.url), "utf8");
const ESC_DONG = APP.split("\n").find((l) => l.startsWith("const esc = "));
const API_SRC = (APP.match(/async function api\(path, body\) \{[\s\S]*?\n\}\n/) || [])[0];
assert.ok(ESC_DONG && API_SRC, "không thấy esc/api trong web/app.js");
const esc = new Function(`${ESC_DONG}\nreturn esc;`)();
const KHO = "https://kho.test";

const D = (n) => `2026-12-${String(n).padStart(2, "0")}`;
const MS = (n, gio = 12) => Date.parse(`${D(n)}T${String(gio).padStart(2, "0")}:00:00+07:00`);
const KHOA_A = "cap_co_so";
const KHOA_B = "cap_cau_hoi";
const TEN_A = "Caption có con số cụ thể";
const TEN_B = "Caption có câu hỏi";
const CAU_QUA_HAN = "đã quá 7 ngày kể từ lúc hoàn tác, không bật lại được nữa";
const CAU_KHONG_CON = "bài học không còn hiệu lực";
const LOI_KHOA_RUNNER = "Máy nhà từ chối khoá/chữ ký bộ chạy việc"; // worker.js LOI_KHOA_RUNNER

// ---------- harness Python ----------
let con = null;
let raPy = "";

function chayHarness() {
  return new Promise((ok, loi) => {
    con = spawn("python", ["-B", "tools/hoc_noi_gia.py"], { cwd: GOC_REPO, stdio: ["pipe", "pipe", "pipe"], windowsHide: true,
      env: { ...process.env, KHO_HOC_TEST: "1" } });
    let buf = "";
    let xong = false;
    const het = setTimeout(() => { if (!xong) { xong = true; loi(new Error(`harness không in dòng JSON sau 30 s:\n${raPy}`)); } }, 30_000);
    con.stdout.setEncoding("utf8");
    con.stderr.setEncoding("utf8");
    con.stderr.on("data", (d) => { raPy += d; });
    con.stdout.on("data", (d) => { // luôn rút stdout để tiến trình con không nghẽn ống
      raPy += d;
      if (xong) return;
      buf += d;
      const i = buf.indexOf("\n");
      if (i < 0) return;
      xong = true;
      clearTimeout(het);
      try { ok(JSON.parse(buf.slice(0, i))); } catch { loi(new Error(`dòng đầu không phải JSON: ${buf.slice(0, i)}`)); }
    });
    con.on("error", (e) => { if (!xong) { xong = true; clearTimeout(het); loi(e); } });
    con.on("exit", (c) => { if (!xong) { xong = true; clearTimeout(het); loi(new Error(`harness thoát sớm (${c}):\n${raPy}`)); } });
  });
}

async function tatHarness() {
  if (!con || con.exitCode !== null || con.signalCode !== null) return;
  const thoat = new Promise((r) => con.once("exit", r));
  con.stdin.end(); // hoc_noi_gia.py: stdin đóng → tắt server, xoá thư mục tạm, thoát
  let hen;
  const kip = await Promise.race([thoat.then(() => true), new Promise((r) => { hen = setTimeout(() => r(false), 15_000); })]);
  clearTimeout(hen);
  if (!kip) { con.kill(); await thoat; } // chỉ giết đúng PID mình sinh
}
process.on("exit", () => { try { if (con && con.exitCode === null) con.kill(); } catch { /* đã tắt */ } });

let ENV = null;
let COOKIE = "";
before(async () => {
  try {
    CONG = await chayHarness();
  } catch (e) {
    await tatHarness();
    throw e;
  }
  for (const k of ["video", "dieu_khien"]) {
    assert.ok(Number.isInteger(CONG[k]) && CONG[k] > 0, k);
    for (const cam of [8787, 8788, 8023]) assert.notEqual(CONG[k], cam, `${k} trùng cổng thật ${cam}`);
  }
  assert.match(CONG.khoa_rieng_pkcs8, /^[A-Za-z0-9+/]+=*$/);
  assert.ok(typeof CONG.tam === "string" && existsSync(CONG.tam));
  ENV = {
    SESSION_SECRET: "bi-mat-hoc-noi-day",
    USERS: JSON.stringify({ nhan: { ten: "Nhân", hash: await bamMatKhau("y", undefined, 1000) } }),
    ASSETS: { fetch: async () => new Response("static") },
    VIDEO_ORIGIN: `http://127.0.0.1:${CONG.video}`, VIDEO_KEY: CONG.video_key, RUNNER_KEY: CONG.runner_key,
    KY_RIENG: CONG.khoa_rieng_pkcs8,
  };
  COOKIE = await taoPhien(ENV, "nhan");
}, { timeout: 60_000 });

after(async () => {
  await tatHarness();
  if (CONG && CONG.tam) assert.equal(existsSync(CONG.tam), false, `thư mục tạm còn sau khi harness tắt: ${CONG.tam}\n${raPy}`);
}, { timeout: 30_000 });

// ---------- điều khiển harness (cổng riêng, chỉ test gọi) ----------
async function dk(p, body) {
  const r = await fetchGoc(`http://127.0.0.1:${CONG.dieu_khien}${p}`,
    body === undefined ? {} : { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json();
  assert.equal(r.status, 200, `${p} → ${r.status} ${JSON.stringify(j)}\n${raPy.slice(-2000)}`);
  return j;
}
// Chạy runner.hoc_tu_dong.chay() thật cho ngày n (đồng hồ giả = ngày n 12:00 VN).
async function hocNgay(n, cauHoi) {
  const k = await dk("/__ngay", { ngay: D(n), cau_hoi: cauHoi });
  assert.equal(k.ma, 0, JSON.stringify(k));
  assert.deepEqual(Object.keys(k.ra).sort(), ["ly_do", "so_thay_doi", "trang_thai"]);
  assert.equal(k.ra.trang_thai, "xong", `ngày ${D(n)}: ${JSON.stringify(k.ra)}`);
  return k;
}
const datGio = (n, gio = 12) => dk("/__gio", { ngay: D(n), gio });
const baiHoc = async () => (await dk("/__bai")).bai; // dòng bai_hoc thô đọc mode=ro
const motBai = async (ma) => { const b = (await baiHoc()).filter((x) => x.ma === ma); assert.equal(b.length, 1, ma); return b[0]; };

// ---------- trình duyệt giả: web/hoc.js thật + api() của web/app.js trong vm ----------
function napWeb({ env = ENV, nowN = 3 } = {}) {
  const S = { toast: [], xacNhan: [], chang1: [], dangNhap: 0 };
  const el = () => ({ innerHTML: "", disabled: false, isConnected: true, addEventListener() {}, querySelectorAll: () => [] });
  const dom = { "#app": el(), "#hc": el(), "#hc-nd": el(), "#hc-tai-lai": el() };
  const fetchTrang = async (duong, opt = {}) => {
    assert.ok(typeof duong === "string" && duong.startsWith("/api/hoc/"), `trang gọi URL lạ: ${duong}`);
    const { cache, ...o } = opt; // eslint-disable-line no-unused-vars — Request của Node không cần cache mode
    const method = o.method || "GET";
    // Trình duyệt thật gửi cookie phiên; POST cùng nguồn kèm Origin.
    const headers = { ...(o.headers || {}), cookie: `kho_s=${COOKIE}`, ...(method === "GET" ? {} : { origin: KHO }) };
    S.chang1.push({ method, duong, body: o.body });
    return worker.fetch(new Request(KHO + duong, { ...o, headers }), env, { waitUntil() {} });
  };
  const ctx = vm.createContext({
    fetch: fetchTrang, console, URLSearchParams, Intl,
    auth: { user: "nhan", ten: "Nhân", get on() { return !!this.user; } },
    renderUser() {}, openLogin() { S.dangNhap++; },
    $: (s) => dom[s] ?? null, document: { querySelectorAll: () => [] },
    toast: (m) => { S.toast.push(m); }, confirm: (m) => { S.xacNhan.push(m); return true; }, laChu: () => true,
    __nowMs: MS(nowN),
  });
  vm.runInContext(`${ESC_DONG}\n${API_SRC}\nlet phienCT = 1;\nDate.now = () => globalThis.__nowMs;\n${HOC}\n`
    + ";globalThis.__hc = { hcRender, hcTai, hcBam, api, bai: (ma) => hcBai.get(ma) };", ctx, { filename: "web/hoc.js" });
  const hc = ctx.__hc;
  return {
    hc, S, dom, fetchTrang,
    gio(n) { ctx.__nowMs = MS(n); },
    html: () => dom["#hc-nd"].innerHTML,
    async moTrang(n) { ctx.__nowMs = MS(n); await hc.hcRender(1); return dom["#hc-nd"].innerHTML; },
    async taiLai() { await hc.hcTai(1, false); return dom["#hc-nd"].innerHTML; },
    bam: (act, ma) => hc.hcBam({ dataset: { hcAct: act, hcMa: ma }, disabled: false }),
  };
}
const nutCua = (h, act) => [...h.matchAll(new RegExp(`data-hc-act="${act}" data-hc-ma="(bh\\d{8}[a-z0-9]{4})"`, "g"))].map((m) => m[1]);
const cuoi = (a) => a[a.length - 1];
const chang2Cuoi = (path) => { const r = chang2.filter((x) => x.path === path); assert.ok(r.length, `chặng 2 không có ${path}`); return cuoi(r); };

let A = ""; // mã bài học cap_co_so (hiệu lực sau 3 ngày)
let B = ""; // mã bài học cap_cau_hoi (hiệu lực ngày 6)

// ---------- rào ----------
test("rào fetch: chỉ 127.0.0.1:<video>/r/hoc/*; :8787, :8788, :8023, host khác, /r/viec → ném", async () => {
  for (const u of ["http://127.0.0.1:8787/r/hoc/bao-cao", "http://127.0.0.1:8788/hoc/bao-cao", "http://127.0.0.1:8023/health",
    "https://video.kutidak.com/r/hoc/bao-cao", `http://localhost:${CONG.video}/r/hoc/bao-cao`, `http://127.0.0.1:${CONG.video}/r/viec`,
    `http://127.0.0.1:${CONG.dieu_khien}/__bai`]) {
    await assert.rejects(globalThis.fetch(u), /fetch thật bị cấm/, u);
  }
  assert.equal(chang2.length, 0);
});

// ---------- ca 1 ----------
test("ca 1: hoc_tu_dong.chay() thật 3 ngày → đúng 1 bài hiệu lực; web/hoc.js vẽ đúng 1 bài học qua đủ 3 chặng", async () => {
  const ngay1 = await hocNgay(1, "khong");
  assert.equal(ngay1.ra.so_thay_doi, 1); // cap_co_so: (mới) → ứng viên
  await hocNgay(2, "khong");
  await hocNgay(3, "khong");
  const bai = await baiHoc();
  assert.equal(bai.length, 1, JSON.stringify(bai));
  assert.equal(bai[0].khoa, KHOA_A);
  assert.equal(bai[0].trang_thai, "hieu_luc");
  assert.equal(bai[0].het_han_luc, D(17));
  A = bai[0].ma;
  assert.match(A, /^bh20261201[a-z0-9]{4}$/);

  const web = napWeb({ nowN: 3 });
  const h = await web.moTrang(3);
  assert.match(h, /Đang dùng \(1\)/);
  assert.match(h, /Ứng viên \(0\)/);
  assert.match(h, /Đã tự tắt \/ hết hạn \/ đã hoàn tác \(0\)/);
  assert.deepEqual(nutCua(h, "hoan-tac"), [A]);
  assert.deepEqual(nutCua(h, "bat-lai"), []);
  assert.ok(h.includes(esc(TEN_A)));
  // view ×2 → lệch = e^(log1p(400)−log1p(200))−1 ≈ 99% (hoc_tu_dong dùng log1p) — số tất định
  assert.match(h, /20 SP · 100% cùng chiều · lệch 99%/);
  assert.match(h, /dùng tới hết 17\/12/);
  // chặng 1 → 2: GET không query lạ, không chữ ký; chặng 2 trả 200 JSON của runner
  assert.deepEqual(web.S.chang1.map((x) => `${x.method} ${x.duong}`), ["GET /api/hoc/bao-cao"]);
  const g = chang2Cuoi("/r/hoc/bao-cao");
  assert.equal(g.method, "GET");
  assert.equal(g.status, 200);
  assert.equal(g.headers["x-key"], CONG.video_key);
  assert.equal(g.headers["x-runner-key"], CONG.runner_key);
  assert.equal(g.headers["x-ky"], undefined);
  assert.equal(JSON.parse(g.txt).ngay, D(3));
});

// ---------- ca 2 ----------
test("ca 2: bấm Hoàn tác trên web < 2 s → hoc.db hoan_tac, tat_boi='nhan'; Worker tự dựng body {boi} + ký D7", async () => {
  const web = napWeb({ nowN: 3 });
  await web.moTrang(3);
  const n0 = chang2.length;
  const t0 = performance.now();
  await web.bam("hoan-tac", A);
  const ms = performance.now() - t0;
  assert.ok(ms < 2000, `hoàn tác mất ${ms.toFixed(0)} ms`);
  assert.equal(cuoi(web.S.toast), "✓ Đã hoàn tác gợi ý.");
  assert.match(web.S.xacNhan[0], new RegExp(`^Hoàn tác gợi ý '${TEN_A}'\\?`));
  // chặng 1: body trình duyệt "{}"; chặng 2: Worker bỏ body đó, gửi {"boi":"nhan"} kèm 3 header ký
  const post = web.S.chang1.find((x) => x.method === "POST");
  assert.equal(post.duong, `/api/hoc/bai-hoc/${A}/hoan-tac`);
  assert.equal(post.body, "{}");
  const p = chang2.slice(n0).find((x) => x.method === "POST");
  assert.equal(p.path, `/r/hoc/bai-hoc/${A}/hoan-tac`);
  assert.equal(p.search, "");
  assert.equal(p.body, '{"boi":"nhan"}');
  assert.equal(p.headers["content-type"], "application/json");
  assert.match(p.headers["x-ky"], /^[A-Za-z0-9_-]{86}$/);
  assert.match(p.headers["x-ky-nonce"], /^[0-9a-f]{32}$/);
  assert.match(p.headers["x-ky-ngay"], /^\d+$/);
  assert.equal(p.status, 200);
  assert.equal(JSON.parse(p.txt).bai_hoc.trang_thai, "hoan_tac");
  const r = await motBai(A);
  assert.equal(r.trang_thai, "hoan_tac");
  assert.equal(r.tat_boi, "nhan");
  assert.equal(r.ly_do_tat, "nguoi_hoan_tac");
  assert.ok(r.tat_luc.startsWith(D(3)), r.tat_luc);
  // web vẽ lại sau khi ghi: bài chuyển xuống mục đã tắt, có nút Bật lại tới hết D+7
  const h = web.html();
  assert.match(h, /Đang dùng \(0\)/);
  assert.match(h, /Đã tự tắt \/ hết hạn \/ đã hoàn tác \(1\)/);
  assert.deepEqual(nutCua(h, "hoan-tac"), []);
  assert.deepEqual(nutCua(h, "bat-lai"), [A]);
  assert.match(h, /Bật lại được tới hết 10\/12/);
  assert.match(h, /ngày 03\/12 bởi nhan/);
});

// ---------- ca 3 ----------
test("ca 3: Hoàn tác lần 2 → 409 câu cố định tới web (không 500); một bản lớp SaiTrangThaiHoc trong tiến trình runner", async () => {
  const web = napWeb({ nowN: 3 });
  const truoc = await motBai(A);
  const r = await web.hc.api(`hoc/bai-hoc/${A}/hoan-tac`, {});
  assert.equal(r.status, 409);
  assert.equal(r.loi, CAU_KHONG_CON);
  const p = chang2Cuoi(`/r/hoc/bai-hoc/${A}/hoan-tac`);
  assert.equal(p.status, 409);
  assert.deepEqual(JSON.parse(p.txt), { loi: CAU_KHONG_CON });
  assert.deepEqual(await motBai(A), truoc);
  const mb = await dk("/__mot_ban");
  assert.equal(mb.cung_lop, true, JSON.stringify(mb)); // api.SaiTrangThaiHoc is runner.kho_hoc.SaiTrangThaiHoc
  assert.deepEqual(mb.module_kho_hoc, ["runner.kho_hoc"]);
  // nút trên web cũng không gửi lần 2: dữ liệu đang hiện có co_the_hoan_tac=false
  await web.moTrang(3);
  const n0 = chang2.length;
  await web.bam("hoan-tac", A);
  assert.equal(chang2.length - n0, 0);
  assert.equal(cuoi(web.S.toast), "Gợi ý này vừa đổi trạng thái — bấm Tải lại để xem.");
});

// ---------- ca 4 ----------
test("ca 4: POST thẳng vào video_server (đúng x-key + x-runner-key) mà không chữ ký → runner 401, hoc.db không đổi", async () => {
  const truoc = await motBai(A);
  for (const them of [{}, { "x-ky": "A".repeat(86), "x-ky-ngay": String(Date.now()), "x-ky-nonce": "0".repeat(32) }]) {
    const r = await fetchGoc(`http://127.0.0.1:${CONG.video}/r/hoc/bai-hoc/${A}/bat-lai`, {
      method: "POST", body: '{"boi":"nhan"}',
      headers: { "content-type": "application/json", "x-key": CONG.video_key, "x-runner-key": CONG.runner_key, ...them },
    });
    assert.equal(r.status, 401);
    assert.deepEqual(await r.json(), { loi: "chữ ký request không hợp lệ" });
  }
  assert.deepEqual(await motBai(A), truoc);
  assert.equal(truoc.trang_thai, "hoan_tac");
});

// ---------- ca 5 ----------
test("ca 5: Worker ký bằng khoá riêng khác → runner 401 → Worker 502; web báo 'Chưa chắc đã xong', hoc.db không đổi", async () => {
  const cap = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
  const kySai = Buffer.from(await crypto.subtle.exportKey("pkcs8", cap.privateKey)).toString("base64");
  const web = napWeb({ env: { ...ENV, KY_RIENG: kySai }, nowN: 3 });
  const truoc = await motBai(A);
  let loi = null;
  try { await web.hc.api(`hoc/bai-hoc/${A}/bat-lai`, {}); } catch (e) { loi = e; }
  assert.ok(loi, "phải ném lỗi");
  assert.equal(loi.status, 502);
  assert.equal(loi.message, LOI_KHOA_RUNNER);
  const p = chang2Cuoi(`/r/hoc/bai-hoc/${A}/bat-lai`);
  assert.equal(p.status, 401);
  assert.deepEqual(JSON.parse(p.txt), { loi: "chữ ký request không hợp lệ" });
  // qua nút web (GET không ký nên vẫn tải được trang; POST ký sai)
  const h = await web.moTrang(3);
  assert.deepEqual(nutCua(h, "bat-lai"), [A]);
  await web.bam("bat-lai", A);
  assert.equal(cuoi(web.S.toast), "Chưa chắc đã xong — bấm Tải lại để xem trạng thái thật.");
  assert.equal(web.S.dangNhap, 0, "502 của máy nhà không được đăng xuất người dùng");
  assert.deepEqual(await motBai(A), truoc);
});

// ---------- ca 6 ----------
test("ca 6: ngày 4 khoá của bài đã hoàn tác vẫn đạt nhưng bộ học KHÔNG tự học lại (đang bị cấm)", async () => {
  await hocNgay(4, "deu");
  const web = napWeb({ nowN: 4 });
  const bc = await web.hc.api(`hoc/bao-cao?ngay=${D(4)}`);
  assert.equal(bc.status, 200);
  const dlA = bc.do_luong.find((x) => x.khoa === KHOA_A);
  assert.equal(dlA.dat, true, JSON.stringify(dlA));
  assert.equal(dlA.so_uid, 20);
  assert.equal(bc.thay_doi.filter((t) => t.khoa === KHOA_A).length, 0, JSON.stringify(bc.thay_doi));
  const moiB = bc.thay_doi.filter((t) => t.khoa === KHOA_B);
  assert.deepEqual(moiB.map((t) => [t.tu, t.den, t.ly_do]), [[null, "ung_vien", "dat_lan_dau"]]);
  const dongA = (await baiHoc()).filter((b) => b.khoa === KHOA_A);
  assert.equal(dongA.length, 1);
  assert.equal(dongA[0].ma, A);
  assert.equal(dongA[0].trang_thai, "hoan_tac");
  B = moiB[0].ma;
  assert.match(B, /^bh20261204[a-z0-9]{4}$/);
});

// ---------- ca 7 ----------
test("ca 7: bài khác hết bằng chứng → Bật lại trên web → hieu_luc, het_han_luc mới; ngày sau vẫn không đủ → tự tắt lại", async () => {
  await hocNgay(5, "deu");
  await hocNgay(6, "deu");
  let b = await motBai(B);
  assert.equal(b.trang_thai, "hieu_luc");
  assert.equal(b.het_han_luc, D(20));
  await hocNgay(7, "pha");
  b = await motBai(B);
  assert.equal(b.trang_thai, "tat_tu_dong");
  assert.equal(b.ly_do_tat, "het_bang_chung");
  assert.equal(b.tat_boi, "he_thong");
  const web = napWeb({ nowN: 7 });
  const bc7 = await web.hc.api(`hoc/bao-cao?ngay=${D(7)}`);
  const dlB = bc7.do_luong.find((x) => x.khoa === KHOA_B);
  assert.equal(dlB.nhat_quan_pt, 55);
  assert.equal(dlB.dat, false);
  const h = await web.moTrang(7);
  assert.ok(nutCua(h, "bat-lai").includes(B), h);
  const t0 = performance.now();
  await web.bam("bat-lai", B);
  assert.ok(performance.now() - t0 < 2000);
  assert.equal(cuoi(web.S.toast), "✓ Đã bật lại gợi ý.");
  assert.equal(cuoi(web.S.xacNhan), `Bật lại gợi ý '${TEN_B}'? Gợi ý sẽ vào phiếu phân tích mới trong 14 ngày, và tự tắt lại nếu lần học kế tiếp không còn đủ bằng chứng giữ (≥ 20 SP, ≥ 60% cùng chiều).`);
  b = await motBai(B);
  assert.equal(b.trang_thai, "hieu_luc");
  assert.equal(b.het_han_luc, D(21)); // mới: hôm nay + 14 (trước là D(20))
  assert.equal(b.tat_luc, null);
  assert.equal(b.tat_boi, null);
  assert.deepEqual(nutCua(web.html(), "hoan-tac"), [B]);
  await hocNgay(8, "pha");
  b = await motBai(B);
  assert.equal(b.trang_thai, "tat_tu_dong");
  assert.equal(b.ly_do_tat, "het_bang_chung");
  const bc8 = await web.hc.api(`hoc/bao-cao?ngay=${D(8)}`);
  assert.deepEqual(bc8.thay_doi.filter((t) => t.ma === B).map((t) => [t.tu, t.den, t.ly_do, t.boi]),
    [["hieu_luc", "tat_tu_dong", "het_bang_chung", "he_thong"]]);
});

// ---------- ca 8 ----------
test("ca 8: GET bao-cao / bai-hoc tới trình duyệt không chứa đường dẫn máy (:\\, /Users/, E:/, thư mục tạm)", async () => {
  const web = napWeb({ nowN: 8 });
  const tamThuong = CONG.tam.toLowerCase();
  const tamXuoi = tamThuong.replace(/\\/g, "/");
  for (const duong of ["/api/hoc/bao-cao", `/api/hoc/bao-cao?ngay=${D(8)}`, "/api/hoc/bai-hoc", "/api/hoc/bai-hoc?gioi_han=200"]) {
    const r = await web.fetchTrang(duong);
    assert.equal(r.status, 200, duong);
    const t = await r.text();
    assert.ok(t.length > 50, duong);
    for (const cam of [":\\", "/Users/", "E:/", "e:/", "kho-runner", "hoc.db", "v2_data"]) assert.ok(!t.includes(cam), `${duong} chứa ${cam}`);
    const thuong = t.toLowerCase();
    assert.ok(!thuong.includes(tamThuong) && !thuong.includes(tamXuoi) && !thuong.includes(JSON.stringify(CONG.tam).slice(1, -1).toLowerCase()),
      `${duong} lộ thư mục tạm`);
  }
});

// ---------- ca 9 ----------
test("ca 9 (Q8): bài hoàn tác ở ca 2, bay_gio = D+7 → Bật lại qua 3 chặng 200 hieu_luc; hoàn tác lại, D'+8 → 409 tới web, hoc.db không đổi", async () => {
  await datGio(10); // ngày hoàn tác ở ca 2 = 03/12 → hạn bật lại tới hết 10/12
  const web = napWeb({ nowN: 10 });
  let h = await web.moTrang(10);
  assert.ok(nutCua(h, "bat-lai").includes(A));
  assert.match(h, /Bật lại được tới hết 10\/12/);
  await web.bam("bat-lai", A);
  assert.equal(cuoi(web.S.toast), "✓ Đã bật lại gợi ý.");
  const p = chang2Cuoi(`/r/hoc/bai-hoc/${A}/bat-lai`);
  assert.equal(p.status, 200);
  assert.equal(p.body, '{"boi":"nhan"}');
  assert.equal(JSON.parse(p.txt).bai_hoc.trang_thai, "hieu_luc");
  let a = await motBai(A);
  assert.equal(a.trang_thai, "hieu_luc");
  assert.equal(a.het_han_luc, D(24));
  assert.equal(a.tat_luc, null);
  // hoàn tác lại (ngày D' = 10/12) qua web
  h = web.html();
  assert.ok(nutCua(h, "hoan-tac").includes(A));
  await web.bam("hoan-tac", A);
  assert.equal(cuoi(web.S.toast), "✓ Đã hoàn tác gợi ý.");
  a = await motBai(A);
  assert.equal(a.trang_thai, "hoan_tac");
  assert.ok(a.tat_luc.startsWith(D(10)), a.tat_luc);
  // D'+7: còn bật lại được — web tải trang lúc này (nút Bật lại hiện)
  await datGio(17);
  h = await web.moTrang(17);
  assert.ok(nutCua(h, "bat-lai").includes(A));
  assert.match(h, /Bật lại được tới hết 17\/12/);
  const truoc = await motBai(A);
  // D'+8: người dùng bấm nút đang hiện (dữ liệu cũ) → máy nhà 409 câu cố định → web toast đúng câu
  await datGio(18);
  web.gio(18);
  await web.bam("bat-lai", A);
  assert.equal(cuoi(web.S.toast), `⚠ Chưa bật lại được: ${CAU_QUA_HAN} — đã tải lại để bạn xem.`);
  const p409 = chang2Cuoi(`/r/hoc/bai-hoc/${A}/bat-lai`);
  assert.equal(p409.status, 409);
  assert.deepEqual(JSON.parse(p409.txt), { loi: CAU_QUA_HAN });
  assert.deepEqual(await motBai(A), truoc, "hoc.db đổi dòng bài sau 409");
  // gọi thẳng api() của web: 409 trả về (không ném), đúng câu
  const r = await web.hc.api(`hoc/bai-hoc/${A}/bat-lai`, {});
  assert.equal(r.status, 409);
  assert.equal(r.loi, CAU_QUA_HAN);
  assert.deepEqual(await motBai(A), truoc);
  // web vẽ lại sau 409: hết nút, câu "Đã quá 7 ngày…"
  h = web.html();
  assert.ok(!nutCua(h, "bat-lai").includes(A));
  assert.match(h, /Đã quá 7 ngày, chờ bộ học tự học lại sau 30 ngày cấm/);
});
