// T-P1 — Test nối 3 chặng Poster V2 (docs/poster-v2-tren-web.md §9 T-P1, §2.1, §3, §4, §7).
// Chạy: node --test cf/test/poster-noi-3-chang.test.mjs   (từ gốc repo)
// Đường đi chạy MÃ THẬT cả 3 tầng (chỉ đọc):
//   web/poster.js (pvApi/pvGoi/pvCho, nạp trong vm) → cf/src/poster.js (apiPoster) → video_server.H + poster_web.xu_ly
//   (tools/poster_noi_gia.py, cổng ngẫu nhiên) → backend Poster GIẢ (cùng tiến trình Python, cổng ngẫu nhiên, ghi lại mọi request).
// Không mạng ngoài: globalThis.fetch bị thay TRƯỚC khi nạp mã; chỉ cho đúng http://127.0.0.1:<video> và
// http://127.0.0.1:<backend>/__ghi|__xoa|__tra; mọi URL khác (kể cả :8023) ném lỗi.
// Ngoại lệ môi trường duy nhất: setTimeout trong vm bị rút còn ≤ 100 ms (nhịp hỏi _kq 3 s của pvCho), logic không đổi.
import { test, before, after, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const fetchGoc = globalThis.fetch;
let CONG = null; // { backend, video, khoa } do máy chạy giả in ra
const chang2 = []; // request Worker → video_server (chặng 2) + phản hồi
globalThis.fetch = async (input, init = {}) => {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  const u = new URL(url);
  const laVideo = CONG && u.protocol === "http:" && u.hostname === "127.0.0.1" && Number(u.port) === CONG.video;
  const laBackend = CONG && u.protocol === "http:" && u.hostname === "127.0.0.1" && Number(u.port) === CONG.backend
    && ["/__ghi", "/__xoa", "/__tra"].includes(u.pathname) && u.search === "";
  if (!laVideo && !laBackend) throw new Error(`fetch thật bị cấm trong test: ${url}`);
  if (laBackend) return fetchGoc(url, init);
  const h = new Headers(init.headers || {});
  const rec = { method: init.method || "GET", path: u.pathname, search: u.search,
    headers: Object.fromEntries(h.entries()), body: init.body == null ? null : Buffer.from(init.body).toString("utf8") };
  chang2.push(rec);
  const r = await fetchGoc(url, init);
  rec.status = r.status;
  rec.txt = await r.clone().text();
  return r;
};
// Nạp Worker SAU khi đã khoá fetch.
const { apiPoster } = await import("../src/poster.js");

const GOC_REPO = fileURLToPath(new URL("../../", import.meta.url));
const POSTER = readFileSync(new URL("../../web/poster.js", import.meta.url), "utf8");
const APP = readFileSync(new URL("../../web/app.js", import.meta.url), "utf8");
const escDong = APP.split("\n").find((l) => l.startsWith("const esc = "));
assert.ok(escDong, "không thấy esc trong web/app.js");
const esc = new Function(`${escDong}\nreturn esc;`)();
const KHO = "https://kho.test";

// ---------- máy chạy giả (Python) ----------
let con = null;
let raPy = "";

function chayMayGia() {
  return new Promise((ok, loi) => {
    con = spawn("python", ["-B", "tools/poster_noi_gia.py"], { cwd: GOC_REPO, stdio: ["pipe", "pipe", "pipe"], windowsHide: true });
    let buf = "";
    let xong = false;
    const het = setTimeout(() => { if (!xong) { xong = true; loi(new Error(`máy chạy giả không in cổng sau 15 s:\n${raPy}`)); } }, 15_000);
    con.stdout.setEncoding("utf8");
    con.stderr.setEncoding("utf8");
    con.stderr.on("data", (d) => { raPy += d; });
    // Luôn rút stdout (log của video_server) để tiến trình con không bị nghẽn ống.
    con.stdout.on("data", (d) => {
      raPy += d;
      if (xong) return;
      buf += d;
      const i = buf.indexOf("\n");
      if (i < 0) return;
      xong = true;
      clearTimeout(het);
      try { ok(JSON.parse(buf.slice(0, i))); } catch (e) { loi(new Error(`dòng đầu không phải JSON: ${buf.slice(0, i)}`)); }
    });
    con.on("error", (e) => { if (!xong) { xong = true; clearTimeout(het); loi(e); } });
    con.on("exit", (c) => { if (!xong) { xong = true; clearTimeout(het); loi(new Error(`máy chạy giả thoát sớm (${c}):\n${raPy}`)); } });
  });
}

async function tatMayGia() {
  if (!con || con.exitCode !== null || con.signalCode !== null) return;
  const thoat = new Promise((r) => con.once("exit", r));
  con.stdin.end(); // poster_noi_gia.py: stdin đóng → tắt server, xoá thư mục tạm
  let hen;
  const kip = await Promise.race([thoat.then(() => true), new Promise((r) => { hen = setTimeout(() => r(false), 8_000); })]);
  clearTimeout(hen); // không giữ vòng sự kiện thêm 8 s
  if (!kip) { con.kill(); await thoat; }
}
process.on("exit", () => { try { if (con && con.exitCode === null) con.kill(); } catch { /* đã tắt */ } });

before(async () => {
  try {
    CONG = await chayMayGia();
  } catch (e) {
    await tatMayGia();
    throw e;
  }
  assert.ok(Number.isInteger(CONG.backend) && Number.isInteger(CONG.video));
  assert.notEqual(CONG.backend, 8023);
  assert.notEqual(CONG.video, 8023);
  assert.notEqual(CONG.video, 8787);
});
after(tatMayGia);

const be = async (p, body) => {
  const r = await fetchGoc(`http://127.0.0.1:${CONG.backend}${p}`,
    body === undefined ? {} : { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  assert.equal(r.status, 200, `${p} → ${r.status}`);
  return r.json();
};
const ghiBackend = async () => (await be("/__ghi")).ghi;
const traBackend = (method, path, status, body, cham) => be("/__tra", { method, path, status, body, ...(cham ? { cham } : {}) });

// ---------- trình duyệt giả: web/poster.js thật trong vm ----------
// chang1: request trình duyệt → Worker; mỗi lần đi qua apiPoster thật với env máy nhà = video_server giả.
function napTrang({ videoKey } = {}) {
  const S = { chang1: [], dangNhap: 0, veUser: 0 };
  const auth = { user: "nhan", get on() { return !!this.user; } };
  const env = { VIDEO_ORIGIN: `http://127.0.0.1:${CONG.video}`, VIDEO_KEY: videoKey || CONG.khoa };
  const fetchTrang = async (duong, opt = {}) => {
    assert.ok(typeof duong === "string" && duong.startsWith("/api/poster"), `trang gọi URL lạ: ${duong}`);
    // Trình duyệt thật gửi kèm cookie + Origin; thêm vài header lạ để kiểm không lọt qua chặng 2/3.
    const headers = { ...(opt.headers || {}), origin: KHO, cookie: "kho_s=phien-gia", "x-runner-key": "lo", "x-ky": "lo",
      authorization: "Bearer trinh-duyet-lo" };
    S.chang1.push({ method: opt.method || "GET", duong, headers: { ...(opt.headers || {}) }, body: opt.body });
    const req = new Request(KHO + duong, { ...opt, headers });
    return apiPoster(req, env, new URL(req.url), { user: "nhan", chu: true });
  };
  const ctx = vm.createContext({
    esc, auth, fetch: fetchTrang, console, URLSearchParams,
    $: () => null, mnCHUA_CO: "",
    document: { hidden: false, body: { append() {} }, createElement: () => ({}) },
    renderUser: () => { S.veUser++; }, openLogin: () => { S.dangNhap++; }, toast: () => {},
    setTimeout: (fn, ms) => setTimeout(fn, Math.min(Number(ms) || 0, 100)),
    clearTimeout, setInterval, clearInterval,
  });
  vm.runInContext(`${POSTER}\n;globalThis.__pv = { pvGoi, pvCho, pvApi, pvDung, phien: () => pvPhien };`, ctx, { filename: "web/poster.js" });
  return { pv: ctx.__pv, S, fetchTrang };
}

const loiCua = async (p) => { try { await p; } catch (e) { return e; } assert.fail("phải ném lỗi"); };
const CAM_TOI_BACKEND = ["x-key", "x-pv", "x-poster-boi", "cookie", "x-runner-key", "x-ky", "origin"];

// Kiểm chung 1 request backend nhận: chỉ token giả ở chặng cuối, không header lạ.
function kiemBackend(g, method, path, { ct, body }) {
  assert.equal(g.method, method);
  assert.equal(g.path, path);
  assert.equal(g.headers.authorization, "Bearer tok-gia");
  for (const k of CAM_TOI_BACKEND) assert.equal(g.headers[k], undefined, `header ${k} lọt tới backend`);
  if (ct) assert.equal(g.headers["content-type"], "application/json");
  else assert.equal(g.headers["content-type"], undefined, `${method} không được có Content-Type tới backend`);
  assert.equal(g.body, body);
}
// Chặng 2 (Worker → video_server): x-key + x-poster-boi, content-type chỉ khi POST/PUT/PATCH, không token/cookie/x-pv.
function kiemChang2(r, method, { ct, body }) {
  assert.equal(r.method, method);
  assert.equal(r.headers["x-key"], CONG.khoa);
  assert.equal(r.headers["x-poster-boi"], "nhan");
  for (const k of ["cookie", "x-pv", "authorization", "x-runner-key", "x-ky", "origin"]) assert.equal(r.headers[k], undefined, `header ${k} lọt sang chặng 2`);
  if (ct) assert.equal(r.headers["content-type"], "application/json");
  else assert.equal(r.headers["content-type"], undefined);
  assert.equal(r.body, body);
  assert.ok(!JSON.stringify(r).includes("tok-gia"), "token lộ ở chặng 2");
}
// Chặng 1 (trình duyệt → Worker): x-pv: 1; content-type + body chỉ khi POST/PUT/PATCH; không token.
function kiemChang1(r, method, { ct, body }) {
  assert.equal(r.method, method);
  assert.equal(r.headers["x-pv"], "1");
  if (ct) assert.equal(r.headers["content-type"], "application/json");
  else assert.equal(r.headers["content-type"], undefined);
  assert.equal(r.body, body);
  assert.ok(!JSON.stringify(r).includes("tok-gia"));
}

beforeEach(async () => {
  chang2.length = 0;
  await be("/__xoa", {});
});

// ---------- rào fetch ----------
test("rào fetch: chỉ 127.0.0.1:<video> và <backend>/__ghi|__xoa|__tra; :8023, host khác, backend /api/v2 → ném", async () => {
  for (const u of ["http://127.0.0.1:8023/health", "http://127.0.0.1:8023/api/v2/queue/status", "https://video.kutidak.com/p/health",
    `http://localhost:${CONG.video}/p/health`, `http://127.0.0.1:${CONG.backend}/api/v2/stats/`, `http://127.0.0.1:${CONG.backend}/__ghi?x=1`,
    "http://127.0.0.1:8787/suc-khoe"]) {
    await assert.rejects(globalThis.fetch(u), /fetch thật bị cấm/, u);
  }
  assert.equal((await ghiBackend()).length, 0);
});

// ---------- mỗi method một ca (§2.1) ----------
test("GET pvApi.listAccounts → backend GET /api/v2/accounts/, không Content-Type, body rỗng, Bearer tok-gia", async () => {
  const { pv, S } = napTrang();
  const kq = await pv.pvApi.listAccounts();
  assert.deepEqual({ ...kq }, { ok: true, method: "GET", path: "/api/v2/accounts/" });
  kiemChang1(S.chang1[0], "GET", { ct: false, body: undefined });
  assert.equal(chang2.length, 1);
  assert.equal(chang2[0].path, "/p/api/v2/accounts/");
  kiemChang2(chang2[0], "GET", { ct: false, body: null });
  const g = await ghiBackend();
  assert.equal(g.length, 1);
  kiemBackend(g[0], "GET", "/api/v2/accounts/", { ct: false, body: "" });
});

test("GET có query: pvApi.listQueue('pending', 100, 0) → query chuyển nguyên qua 3 chặng", async () => {
  const { pv } = napTrang();
  await pv.pvApi.listQueue("pending", 100, 0);
  assert.equal(chang2[0].search, "?limit=100&offset=0&status=pending");
  const g = await ghiBackend();
  assert.equal(g.length, 1);
  assert.equal(g[0].query, "limit=100&offset=0&status=pending");
  kiemBackend(g[0], "GET", "/api/v2/queue/", { ct: false, body: "" });
});

test("DELETE pvApi.deleteQueueItem(5) → backend DELETE /api/v2/queue/5 không Content-Type, không body; không 415 ở chặng nào", async () => {
  const { pv, S } = napTrang();
  const kq = await pv.pvApi.deleteQueueItem(5);
  assert.deepEqual({ ...kq }, { ok: true, method: "DELETE", path: "/api/v2/queue/5" });
  kiemChang1(S.chang1[0], "DELETE", { ct: false, body: undefined });
  kiemChang2(chang2[0], "DELETE", { ct: false, body: null });
  assert.equal(chang2[0].status, 200);
  const g = await ghiBackend();
  assert.equal(g.length, 1);
  kiemBackend(g[0], "DELETE", "/api/v2/queue/5", { ct: false, body: "" });
  assert.ok(!g[0].headers["content-length"] || g[0].headers["content-length"] === "0", "DELETE không được mang body tới backend");
});

test("POST rỗng pvApi.queueUnstick → body {} xuyên 3 chặng, Content-Type JSON tới backend", async () => {
  const { pv, S } = napTrang();
  const kq = await pv.pvApi.queueUnstick();
  assert.equal(kq.path, "/api/v2/queue/unstick");
  kiemChang1(S.chang1[0], "POST", { ct: true, body: "{}" });
  kiemChang2(chang2[0], "POST", { ct: true, body: "{}" });
  const g = await ghiBackend();
  assert.equal(g.length, 1);
  kiemBackend(g[0], "POST", "/api/v2/queue/unstick", { ct: true, body: "{}" });
});

test("POST có body pvApi.accountCooldown(3) → backend nhận {\"hours\":24}", async () => {
  const { pv } = napTrang();
  await pv.pvApi.accountCooldown(3);
  kiemChang2(chang2[0], "POST", { ct: true, body: '{"hours":24}' });
  const g = await ghiBackend();
  kiemBackend(g[0], "POST", "/api/v2/accounts/3/cooldown", { ct: true, body: '{"hours":24}' });
});

test("PUT pvApi.putSetting('headless','1') → PUT /api/v2/settings/headless body {\"value\":\"1\"}", async () => {
  const { pv, S } = napTrang();
  await pv.pvApi.putSetting("headless", "1");
  kiemChang1(S.chang1[0], "PUT", { ct: true, body: '{"value":"1"}' });
  kiemChang2(chang2[0], "PUT", { ct: true, body: '{"value":"1"}' });
  const g = await ghiBackend();
  kiemBackend(g[0], "PUT", "/api/v2/settings/headless", { ct: true, body: '{"value":"1"}' });
});

test("PATCH pvApi.archiveFolder(9, true) → PATCH /api/v2/folders/9 body {\"is_archived\":1} (api_client.py archive_folder)", async () => {
  const { pv } = napTrang();
  await pv.pvApi.archiveFolder(9, true);
  kiemChang2(chang2[0], "PATCH", { ct: true, body: '{"is_archived":1}' });
  const g = await ghiBackend();
  kiemBackend(g[0], "PATCH", "/api/v2/folders/9", { ct: true, body: '{"is_archived":1}' });
});

// ---------- lệnh nền + chống trùng (§3.3) ----------
test("nền: postQueueItem(7) → 202 {cho} → pvGoi hỏi _kq → kết quả; gọi lại khi đang chạy → cùng cho, trung, backend nhận đúng 1 lần", async () => {
  const { pv } = napTrang();
  const p1 = pv.pvApi.postQueueItem(7);
  // chờ chặng 2 có 202 của lệnh đầu
  const t0 = Date.now();
  while (!chang2.some((r) => r.path === "/p/api/v2/queue/7/post" && r.status === 202)) {
    assert.ok(Date.now() - t0 < 5000, "không thấy 202 của lệnh đăng");
    await new Promise((r) => setTimeout(r, 20));
  }
  const dau = JSON.parse(chang2.find((r) => r.path === "/p/api/v2/queue/7/post").txt);
  assert.match(dau.cho, /^[0-9a-f]{32}$/);
  assert.equal(dau.trung, false);
  assert.equal(dau.toi_da_giay, 300);
  // _kq liệt kê lệnh đang chạy, tóm tắt chỉ có queue_id
  const ds = await pv.pvApi.dangChay();
  const muc = ds.dang_chay.find((x) => x.cho === dau.cho);
  assert.ok(muc, "GET /_kq phải liệt kê lệnh nền");
  assert.equal(muc.method, "POST");
  assert.equal(muc.path, "/api/v2/queue/7/post");
  assert.equal(muc.lop, "L");
  assert.deepEqual({ ...muc.tom_tat }, { queue_id: 7 });

  const p2 = pv.pvApi.postQueueItem(7);
  const [k1, k2] = await Promise.all([p1, p2]);
  for (const k of [k1, k2]) assert.deepEqual({ ...k }, { ok: true, method: "POST", path: "/api/v2/queue/7/post" });

  const lenhDang = chang2.filter((r) => r.path === "/p/api/v2/queue/7/post");
  assert.equal(lenhDang.length, 2);
  const sau = JSON.parse(lenhDang[1].txt);
  assert.equal(lenhDang[1].status, 202);
  assert.equal(sau.cho, dau.cho, "lệnh trùng phải trả lại cho cũ");
  assert.equal(sau.trung, true);
  assert.ok(chang2.some((r) => r.path === `/p/_kq/${dau.cho}` && r.method === "GET"), "pvGoi phải hỏi _kq/<cho>");
  for (const r of chang2.filter((x) => x.path.startsWith("/p/_kq"))) kiemChang2(r, "GET", { ct: false, body: null });

  const g = await ghiBackend();
  const dang = g.filter((x) => x.path === "/api/v2/queue/7/post");
  assert.equal(dang.length, 1, "backend phải nhận đúng 1 lệnh đăng");
  kiemBackend(dang[0], "POST", "/api/v2/queue/7/post", { ct: true, body: "{}" });
  // xong rồi thì không còn trong danh sách
  const ds2 = await pv.pvApi.dangChay();
  assert.ok(!ds2.dang_chay.some((x) => x.cho === dau.cho));
});

// ---------- an ninh / đường lỗi ----------
test("x-pv bắt buộc: request tới Worker thiếu x-pv → 403, video_server và backend không nhận gì", async () => {
  const { fetchTrang } = napTrang();
  const r = await fetchTrang("/api/poster/api/v2/stats/", { method: "GET", headers: {} });
  assert.equal(r.status, 403);
  assert.deepEqual(await r.json(), { loi: "Thiếu x-pv" });
  const r2 = await fetchTrang("/api/poster/api/v2/queue/unstick", { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
  assert.equal(r2.status, 403);
  assert.equal(chang2.length, 0);
  assert.equal((await ghiBackend()).length, 0);
});

test("_thong_tin: trả backend giả, co_token true, không có token ở phản hồi trình duyệt", async () => {
  const { pv } = napTrang();
  const t = await pv.pvApi.thongTin();
  assert.equal(t.backend, `http://127.0.0.1:${CONG.backend}`);
  assert.equal(t.co_token, true);
  assert.ok(!JSON.stringify(t).includes("tok-gia"));
  assert.ok(!chang2[0].txt.includes("tok-gia"));
  assert.equal((await ghiBackend()).length, 0, "_thong_tin không gọi backend");
});

test("backend 401 (GET) → video_server đọc lại .env, gọi lại đúng 1 lần, đổi 502 câu token; trình duyệt KHÔNG bị đăng xuất", async () => {
  await traBackend("GET", "/api/v2/stats/", 401, { detail: "Invalid token" });
  const { pv, S } = napTrang();
  const e = await loiCua(pv.pvApi.getStats());
  assert.equal(e.status, 502);
  assert.equal(e.message, "502: Poster V2 từ chối token (TT_API_BEARER_TOKEN lệch)");
  assert.equal(S.dangNhap, 0);
  assert.equal(S.veUser, 0);
  assert.equal(chang2[0].status, 502);
  const g = await ghiBackend();
  assert.equal(g.filter((x) => x.path === "/api/v2/stats/").length, 2, "GET 401 gọi lại đúng 1 lần");
});

test("backend 401 (POST) → 502 câu token, KHÔNG gọi lại lệnh ghi", async () => {
  await traBackend("POST", "/api/v2/views/refresh", 401, { detail: "Invalid token" });
  const { pv, S } = napTrang();
  const e = await loiCua(pv.pvApi.viewsRefresh());
  assert.equal(e.message, "502: Poster V2 từ chối token (TT_API_BEARER_TOKEN lệch)");
  assert.equal(S.dangNhap, 0);
  assert.equal((await ghiBackend()).filter((x) => x.path === "/api/v2/views/refresh").length, 1);
});

test("backend 403 → chuyển nguyên qua 3 chặng: '403: <detail>', không đăng xuất", async () => {
  await traBackend("GET", "/api/v2/settings/", 403, { detail: "Bản quyền không hợp lệ" });
  const { pv, S } = napTrang();
  const e = await loiCua(pv.pvApi.getSettingsAll());
  assert.equal(e.status, 403);
  assert.equal(e.message, "403: Bản quyền không hợp lệ");
  assert.equal(chang2[0].status, 403);
  assert.equal(S.dangNhap, 0);
});

test("backend 500 / 503 → chuyển nguyên status + detail tới trình duyệt", async () => {
  await traBackend("GET", "/api/v2/queue/status", 500, { detail: "boom" });
  await traBackend("DELETE", "/api/v2/calendar/plans/4", 503, { detail: { ly_do: "db khoá" } });
  const { pv, S } = napTrang();
  const e = await loiCua(pv.pvApi.statusCounts());
  assert.equal(e.status, 500);
  assert.equal(e.message, "500: boom");
  const e2 = await loiCua(pv.pvApi.deleteCalendarPlan(4));
  assert.equal(e2.status, 503);
  assert.equal(e2.message, '503: {"ly_do":"db khoá"}');
  assert.equal(S.dangNhap, 0);
  const g = await ghiBackend();
  kiemBackend(g.find((x) => x.method === "DELETE"), "DELETE", "/api/v2/calendar/plans/4", { ct: false, body: "" });
});

test("Worker gửi sai VIDEO_KEY → video_server 401 + x-kho-tu-choi → Worker 502 câu VIDEO_KEY; không đăng xuất, backend không nhận", async () => {
  const { pv, S } = napTrang({ videoKey: "khoa-sai" });
  const e = await loiCua(pv.pvApi.listAccounts());
  assert.equal(e.status, 502);
  assert.equal(e.message, "502: Máy nhà từ chối khoá (VIDEO_KEY lệch với tools/.video_key)");
  assert.equal(chang2[0].status, 401);
  assert.equal(S.dangNhap, 0);
  assert.equal((await ghiBackend()).length, 0);
});
