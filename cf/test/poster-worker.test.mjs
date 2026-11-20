// W-P0 — Test route Worker /api/poster/* (docs/poster-v2-tren-web.md §7, §2.1, §4.2, §9 W-P0).
// Chạy: node --test cf/test/poster-worker.test.mjs
// Máy nhà giả https://may.test như worker.test.mjs:15-20. fetch giả đặt TRƯỚC khi nạp mã; URL lạ → ném lỗi.
import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";

let mayGoi, mayTraLoi;
globalThis.fetch = async (url, opt = {}) => {
  const u = new URL(url);
  if (u.origin === "https://may.test") {
    mayGoi.push({ url: u, method: opt.method || "GET", headers: opt.headers || {}, signal: opt.signal, body: opt.body });
    return mayTraLoi(u, opt);
  }
  throw new Error("fetch thật bị cấm trong test: " + url);
};
globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };

const { default: worker, taoPhien, bamMatKhau } = await import("../src/worker.js");
const P = await import("../src/poster.js");

const GOC = "https://kho.test";
const HEX32 = "0123456789abcdef0123456789abcdef";
let env, nhatKy, logGoc;
const ctx = { waitUntil() {} };

beforeEach(async () => {
  mayGoi = [];
  mayTraLoi = async () => Response.json({ ok: true });
  env = {
    SESSION_SECRET: "bi-mat-test",
    USERS: JSON.stringify({
      lan: { ten: "Lan", hash: await bamMatKhau("x", undefined, 1000) },
      nhan: { ten: "Nhân", hash: await bamMatKhau("y", undefined, 1000) },
    }),
    ASSETS: { fetch: async () => new Response("static") },
    VIDEO_ORIGIN: "https://may.test", VIDEO_KEY: "k-bi-mat",
  };
  nhatKy = [];
  logGoc = console.log;
  console.log = (...a) => nhatKy.push(a.join(" "));
});
afterEach(() => { console.log = logGoc; });

const cookieCua = async (user) => `kho_s=${await taoPhien(env, user)}`;

// Gọi Worker. pv mặc định có; origin mặc định đúng cho method khác GET.
async function goi(path, { user = "nhan", method = "GET", pv = true, origin, body, ct, headers = {} } = {}) {
  const h = { ...headers };
  if (user) h.cookie = await cookieCua(user);
  if (pv) h["x-pv"] = "1";
  const o = origin === undefined ? (method === "GET" ? null : GOC) : origin;
  if (o) h.origin = o;
  if (ct) h["content-type"] = ct;
  return worker.fetch(new Request(GOC + path, { method, headers: h, body }), env, ctx);
}
const docJson = async (r) => JSON.parse(await r.text());

// ---------- quyền ----------
test("chưa đăng nhập → 401, máy nhà không bị gọi", async () => {
  const r = await goi("/api/poster/api/v2/stats/", { user: null });
  assert.equal(r.status, 401);
  assert.equal(mayGoi.length, 0);
});

test("người thường → 403 và máy nhà không bị gọi (cả GET lẫn POST)", async () => {
  assert.equal((await goi("/api/poster/api/v2/stats/", { user: "lan" })).status, 403);
  assert.equal((await goi("/api/poster/api/v2/queue/unstick", { user: "lan", method: "POST", ct: "application/json", body: "{}" })).status, 403);
  assert.equal(mayGoi.length, 0);
});

test("thiếu x-pv → 403 với cả GET; máy nhà không bị gọi", async () => {
  const r = await goi("/api/poster/api/v2/stats/", { pv: false });
  assert.equal(r.status, 403);
  assert.equal((await docJson(r)).loi, "Thiếu x-pv");
  const r2 = await goi("/api/poster/api/v2/queue/7", { pv: false, method: "DELETE" });
  assert.equal(r2.status, 403);
  const r3 = await goi("/api/poster/api/v2/stats/", { headers: { "x-pv": "2" }, pv: false });
  assert.equal(r3.status, 403);
  assert.equal(mayGoi.length, 0);
});

test("có x-pv + chủ kho → GET không cần Origin, chuyển tới /p/<rest>", async () => {
  const r = await goi("/api/poster/api/v2/stats/");
  assert.equal(r.status, 200);
  assert.deepEqual(await docJson(r), { ok: true });
  assert.equal(mayGoi.length, 1);
  assert.equal(mayGoi[0].url.href, "https://may.test/p/api/v2/stats/");
  assert.equal(mayGoi[0].method, "GET");
});

test("lệnh ghi thiếu Origin / Origin lạ → 403, không gọi máy nhà", async () => {
  for (const m of ["POST", "PUT", "PATCH", "DELETE"]) {
    const coBody = m !== "DELETE";
    const opt = { method: m, ...(coBody ? { ct: "application/json", body: "{}" } : {}) };
    const thieu = await goi("/api/poster/api/v2/folders/3", { ...opt, origin: null });
    assert.equal(thieu.status, 403, `${m} thiếu Origin`);
    assert.equal((await docJson(thieu)).loi, "Sai nguồn gọi");
    assert.equal((await goi("/api/poster/api/v2/folders/3", { ...opt, origin: "https://la.test" })).status, 403, `${m} Origin lạ`);
  }
  assert.equal(mayGoi.length, 0);
});

test("thiếu VIDEO_ORIGIN/VIDEO_KEY → 503", async () => {
  delete env.VIDEO_KEY;
  assert.equal((await goi("/api/poster/health")).status, 503);
  env.VIDEO_KEY = "k"; delete env.VIDEO_ORIGIN;
  assert.equal((await goi("/api/poster/health")).status, 503);
  assert.equal(mayGoi.length, 0);
});

// ---------- path / method / query ----------
test("kiemDuongPoster: rest hợp lệ → dich /p<rest><query>", () => {
  assert.deepEqual(P.kiemDuongPoster("/health", "GET", ""), { dich: "/p/health" });
  assert.deepEqual(P.kiemDuongPoster("/api/v2/logs/", "GET", "?limit=50&offset=0"), { dich: "/p/api/v2/logs/?limit=50&offset=0" });
  assert.deepEqual(P.kiemDuongPoster("/_kq", "GET", ""), { dich: "/p/_kq" });
  assert.deepEqual(P.kiemDuongPoster(`/_kq/${HEX32}`, "GET", ""), { dich: `/p/_kq/${HEX32}` });
  assert.deepEqual(P.kiemDuongPoster("/_video/12", "GET", ""), { dich: "/p/_video/12" });
  assert.deepEqual(P.kiemDuongPoster("/_dem", "POST", ""), { dich: "/p/_dem" });
  assert.deepEqual(P.kiemDuongPoster("/_thong_tin", "GET", ""), { dich: "/p/_thong_tin" });
  assert.deepEqual(P.kiemDuongPoster("/_bat_backend", "POST", ""), { dich: "/p/_bat_backend" });
  assert.equal(P.kiemDuongPoster("/_bat_backend/x", "POST", "").status, 404);
  assert.deepEqual(P.kiemDuongPoster("/api/v2/accounts/a..b", "PUT", ""), { dich: "/p/api/v2/accounts/a..b" });
});

test("kiemDuongPoster: rest lạ, '..', '.', '//', '%', '\\', method lạ, query dài → lỗi 4xx", () => {
  const xau = [
    "", "/", "/api/v2/", "/api/v1/x", "/admin", "/api/v2/../x", "/api/v2/a/../../x", "/api/v2/./x", "/api/v2/a/.",
    "/api/v2//x", "/api/v2/%2e%2e/x", "/api/v2/a%2fb", "/api/v2/a\\b", "/api/v2/a\x01b", "/_kq/123", `/_kq/${HEX32}0`,
    `/_kq/${HEX32.toUpperCase()}`, "/_video/abc", "/_video/1234567890", "/_dem/x", "/health/", "/api/v2/" + "a".repeat(201),
  ];
  for (const rest of xau) {
    const k = P.kiemDuongPoster(rest, "GET", "");
    assert.ok(k.status >= 400 && k.status < 500 && !k.dich, `phải chặn ${JSON.stringify(rest)}`);
  }
  for (const m of ["HEAD", "OPTIONS", "TRACE", "CONNECT", "get"]) {
    assert.equal(P.kiemDuongPoster("/health", m, "").status, 405, m);
  }
  assert.equal(P.kiemDuongPoster("/health", "GET", "?" + "a".repeat(513)).status, 400);
  assert.deepEqual(P.kiemDuongPoster("/health", "GET", "?" + "a".repeat(512)), { dich: "/p/health?" + "a".repeat(512) });
});

test("qua Worker: rest lạ, '//', '%2f', '%2e%2e', method lạ → 4xx, không gọi máy nhà", async () => {
  for (const p of ["/api/poster", "/api/poster/", "/api/poster/admin", "/api/poster/api/v2//x", "/api/poster/api/v2/a%2fb",
    "/api/poster/api/v2/%2e%2e/%2e%2e/x", "/api/poster/api/v2/../../api/me", "/api/poster/_kq/123", "/api/poster/_video/x"]) {
    const r = await goi(p);
    assert.ok(r.status >= 400 && r.status < 500, `${p} → ${r.status}`);
  }
  for (const m of ["HEAD", "OPTIONS"]) {
    const r = await goi("/api/poster/health", { method: m });
    assert.equal(r.status, 405, m);
  }
  assert.equal(mayGoi.length, 0);
});

test("/_kq (không id) và /_kq/<32 hex> qua", async () => {
  mayTraLoi = async () => Response.json({ dang_chay: [] });
  assert.equal((await goi("/api/poster/_kq")).status, 200);
  mayTraLoi = async () => Response.json({ xong: false });
  assert.equal((await goi(`/api/poster/_kq/${HEX32}`)).status, 200);
  assert.deepEqual(mayGoi.map((g) => g.url.pathname), ["/p/_kq", `/p/_kq/${HEX32}`]);
});

test("query chuyển nguyên (≤ 512); dài hơn → 400, không gọi máy nhà", async () => {
  await goi("/api/poster/api/v2/calendar/month?year=2026&month=11&account_id=3");
  assert.equal(mayGoi[0].url.href, "https://may.test/p/api/v2/calendar/month?year=2026&month=11&account_id=3");
  const q = "?status=" + "x".repeat(505);
  assert.equal(q.length - 1, 512);
  assert.equal((await goi("/api/poster/api/v2/logs/" + q)).status, 200);
  assert.equal(mayGoi[1].url.search, q);
  assert.equal((await goi("/api/poster/api/v2/logs/" + q + "y")).status, 400);
  assert.equal(mayGoi.length, 2);
});

// ---------- hợp đồng body §2.1 ----------
const tenHeader = (h) => Object.keys(h).map((k) => k.toLowerCase()).sort();

test("DELETE không content-type, không body → máy nhà nhận DELETE không content-type, không body", async () => {
  const r = await goi("/api/poster/api/v2/queue/7", { method: "DELETE" });
  assert.equal(r.status, 200);
  const g = mayGoi[0];
  assert.equal(g.method, "DELETE");
  assert.equal(g.url.pathname, "/p/api/v2/queue/7");
  assert.equal(g.body, undefined);
  assert.deepEqual(tenHeader(g.headers), ["x-key", "x-poster-boi"]);
});

test("DELETE có content-type JSON nhưng không body vẫn qua (không kiểm content-type), không gửi content-type", async () => {
  const r = await goi("/api/poster/api/v2/queue/7", { method: "DELETE", ct: "application/json" });
  assert.equal(r.status, 200);
  assert.deepEqual(tenHeader(mayGoi[0].headers), ["x-key", "x-poster-boi"]);
});

test("DELETE có body → 400, không gọi máy nhà", async () => {
  const r = await goi("/api/poster/api/v2/queue/7", { method: "DELETE", ct: "application/json", body: "{}" });
  assert.equal(r.status, 400);
  assert.equal(mayGoi.length, 0);
});

test("GET có body → 400 (kiemBodyPoster với request giả; Request chuẩn không cho GET có body)", async () => {
  const gia = (headers, bytes) => ({
    headers: new Headers(headers),
    body: bytes ? new Response(bytes).body : null,
    arrayBuffer: async () => (bytes ? bytes.buffer : new ArrayBuffer(0)),
  });
  assert.equal((await P.kiemBodyPoster(gia({}, new TextEncoder().encode("{}")), "GET")).status, 400);
  assert.equal((await P.kiemBodyPoster(gia({ "content-length": "2" }, null), "GET")).status, 400);
  assert.deepEqual(await P.kiemBodyPoster(gia({}, null), "GET"), { body: null, ct: null });
  assert.deepEqual(await P.kiemBodyPoster(gia({}, null), "DELETE"), { body: null, ct: null });
  // Qua Worker: content-length > 0 trên GET cũng bị chặn.
  const r = await goi("/api/poster/api/v2/stats/", { headers: { "content-length": "5" } });
  assert.equal(r.status, 400);
  assert.equal(mayGoi.length, 0);
});

test("POST {} → gửi content-type: application/json + body {} nguyên byte, header chỉ x-key/x-poster-boi/content-type", async () => {
  const r = await goi("/api/poster/api/v2/queue/unstick", {
    method: "POST", ct: "application/json", body: "{}",
    headers: { "x-runner-key": "rk", authorization: "Bearer lo", "x-ky": "z" },
  });
  assert.equal(r.status, 200);
  const g = mayGoi[0];
  assert.equal(g.method, "POST");
  assert.deepEqual(tenHeader(g.headers), ["content-type", "x-key", "x-poster-boi"]);
  assert.equal(g.headers["content-type"], "application/json");
  assert.equal(g.headers["x-key"], "k-bi-mat");
  assert.equal(g.headers["x-poster-boi"], "nhan");
  assert.equal(new TextDecoder().decode(g.body), "{}");
  assert.ok(g.signal, "phải có signal timeout");
});

test("PUT/PATCH JSON UTF-8 có charset → chuyển nguyên byte", async () => {
  const body = JSON.stringify({ name: "Tài khoản ✓", nested: [1, 2] });
  for (const m of ["PUT", "PATCH"]) {
    const r = await goi("/api/poster/api/v2/folders/3", { method: m, ct: "application/json; charset=utf-8", body });
    assert.equal(r.status, 200, m);
  }
  for (const g of mayGoi) {
    assert.equal(new TextDecoder().decode(g.body), body);
    assert.equal(g.headers["content-type"], "application/json");
  }
});

test("POST rỗng → 400 'Thiếu body JSON'; POST không body → 400", async () => {
  const r = await goi("/api/poster/api/v2/queue/unstick", { method: "POST", ct: "application/json", body: "" });
  assert.equal(r.status, 400);
  assert.equal((await docJson(r)).loi, "Thiếu body JSON");
  assert.equal((await goi("/api/poster/api/v2/queue/unstick", { method: "POST", ct: "application/json" })).status, 400);
  assert.equal(mayGoi.length, 0);
});

test("POST/PUT/PATCH sai hoặc thiếu content-type → 415", async () => {
  for (const m of ["POST", "PUT", "PATCH"]) {
    assert.equal((await goi("/api/poster/api/v2/folders/3", { method: m, ct: "text/plain", body: "{}" })).status, 415, m);
    assert.equal((await goi("/api/poster/api/v2/folders/3", { method: m, ct: "application/x-www-form-urlencoded", body: "a=b" })).status, 415, m);
    assert.equal((await goi("/api/poster/api/v2/folders/3", { method: m, body: new Uint8Array([123, 125]) })).status, 415, m);
  }
  assert.equal(mayGoi.length, 0);
});

test("> 256 KB (đo byte) → 413; đúng 256 KB → qua", async () => {
  // Chuỗi chữ có dấu: số ký tự < 256K nhưng số byte > 256K → phải 413.
  const nhieuByte = JSON.stringify({ s: "ạ".repeat(100_000) });
  assert.ok(nhieuByte.length < P.POSTER_BODY_TOI_DA && new TextEncoder().encode(nhieuByte).length > P.POSTER_BODY_TOI_DA);
  assert.equal((await goi("/api/poster/api/v2/accounts/cookies_from_json", { method: "POST", ct: "application/json", body: nhieuByte })).status, 413);
  // content-length khai lớn → 413 trước khi đọc
  assert.equal((await goi("/api/poster/api/v2/accounts/", {
    method: "POST", ct: "application/json", body: "{}", headers: { "content-length": String(P.POSTER_BODY_TOI_DA + 1) },
  })).status, 413);
  assert.equal(mayGoi.length, 0);
  const vua = JSON.stringify({ s: "a".repeat(P.POSTER_BODY_TOI_DA - 8) });
  assert.equal(new TextEncoder().encode(vua).length, P.POSTER_BODY_TOI_DA);
  assert.equal((await goi("/api/poster/api/v2/accounts/", { method: "POST", ct: "application/json", body: vua })).status, 200);
  assert.equal(mayGoi.length, 1);
});

test("JSON hỏng → 400, không gọi máy nhà", async () => {
  for (const b of ["{", "abc", "{'a':1}", "\uFEFF{}x"]) {
    assert.equal((await goi("/api/poster/api/v2/folders/", { method: "POST", ct: "application/json", body: b })).status, 400, b);
  }
  assert.equal((await goi("/api/poster/api/v2/folders/", { method: "POST", ct: "application/json", body: new Uint8Array([0x7b, 0xff, 0x7d]) })).status, 400);
  assert.equal(mayGoi.length, 0);
});

test("không chuyển cookie, x-pv, origin hay header nào của trình duyệt; GET không có content-type", async () => {
  await goi("/api/poster/api/v2/settings/", { headers: { "x-runner-key": "rk", range: "bytes=0-1", "user-agent": "ua" } });
  const g = mayGoi[0];
  assert.deepEqual(tenHeader(g.headers), ["x-key", "x-poster-boi"]);
  assert.equal(g.body, undefined);
});

// ---------- phản hồi máy nhà ----------
test("máy nhà 401 có x-kho-tu-choi: khoa → 502 câu VIDEO_KEY", async () => {
  mayTraLoi = async () => new Response('{"loi":"Sai khoá"}', { status: 401, headers: { "x-kho-tu-choi": "khoa", "content-type": "application/json" } });
  const r = await goi("/api/poster/api/v2/stats/");
  assert.equal(r.status, 502);
  assert.equal((await docJson(r)).loi, "Máy nhà từ chối khoá (VIDEO_KEY lệch với tools/.video_key)");
});

test("máy nhà 401 không header → 502 câu 'không rõ nguồn'; không bao giờ chuyển 401", async () => {
  mayTraLoi = async () => new Response('{"detail":"x"}', { status: 401, headers: { "content-type": "application/json" } });
  const r = await goi("/api/poster/api/v2/stats/");
  assert.equal(r.status, 502);
  assert.equal((await docJson(r)).loi, "Máy nhà trả 401 không rõ nguồn");
  mayTraLoi = async () => new Response("", { status: 401, headers: { "x-kho-tu-choi": "khac" } });
  assert.equal((await goi("/api/poster/api/v2/stats/")).status, 502);
});

test("máy nhà 403 → 403 nguyên body (câu bản quyền backend)", async () => {
  const body = '{"detail":"License invalid — liên hệ"}';
  mayTraLoi = async () => new Response(body, { status: 403, headers: { "content-type": "application/json" } });
  const r = await goi("/api/poster/api/v2/queue/unstick", { method: "POST", ct: "application/json", body: "{}" });
  assert.equal(r.status, 403);
  assert.equal(await r.text(), body);
  assert.match(r.headers.get("content-type"), /^application\/json/);
});

test("lỗi mạng → 502 (lệnh ghi thêm câu CÓ THỂ đã chạy)", async () => {
  mayTraLoi = async () => { throw new TypeError("fetch failed"); };
  const r = await goi("/api/poster/api/v2/stats/");
  assert.equal(r.status, 502);
  const l = (await docJson(r)).loi;
  assert.match(l, /^Máy nhà không trả lời/);
  assert.doesNotMatch(l, /CÓ THỂ/);
  const w = await goi("/api/poster/api/v2/queue/7/retry", { method: "POST", ct: "application/json", body: "{}" });
  assert.equal(w.status, 502);
  assert.match((await docJson(w)).loi, /CÓ THỂ đã chạy/);
  assert.equal(mayGoi.length, 2, "không tự thử lại");
});

test("hết giờ (giả AbortSignal) → 504; GET không có câu CÓ THỂ, lệnh ghi có; không tự thử lại", async () => {
  mayTraLoi = async () => { throw new DOMException("The operation was aborted due to timeout", "TimeoutError"); };
  const r = await goi("/api/poster/api/v2/folders/?archived=0");
  assert.equal(r.status, 504);
  assert.doesNotMatch((await docJson(r)).loi, /CÓ THỂ/);
  for (const m of ["POST", "PUT", "PATCH", "DELETE"]) {
    const opt = m === "DELETE" ? { method: m } : { method: m, ct: "application/json", body: "{}" };
    const w = await goi("/api/poster/api/v2/queue/7", opt);
    assert.equal(w.status, 504, m);
    assert.match((await docJson(w)).loi, /Thao tác CÓ THỂ đã chạy: bấm Refresh để kiểm trước khi bấm lại/, m);
  }
  mayTraLoi = async () => { throw new DOMException("aborted", "AbortError"); };
  assert.equal((await goi("/api/poster/api/v2/stats/")).status, 504);
  assert.equal(mayGoi.length, 6, "mỗi request đúng 1 lần gọi máy nhà");
});

test("timeout 95 s: signal truyền vào fetch là AbortSignal chưa huỷ", async () => {
  assert.equal(P.POSTER_TIMEOUT_MS, 95_000);
  await goi("/api/poster/health");
  assert.ok(mayGoi[0].signal instanceof AbortSignal);
  assert.equal(mayGoi[0].signal.aborted, false);
});

test("edge 524 → 504; lỗi edge HTML 5xx → 502; 502 JSON của video_server chuyển nguyên", async () => {
  mayTraLoi = async () => new Response("<html>524</html>", { status: 524, headers: { "content-type": "text/html" } });
  const r = await goi("/api/poster/api/v2/queue/7/post", { method: "POST", ct: "application/json", body: "{}" });
  assert.equal(r.status, 504);
  assert.match((await docJson(r)).loi, /CÓ THỂ đã chạy/);
  mayTraLoi = async () => new Response("<html>bad gateway</html>", { status: 530, headers: { "content-type": "text/html" } });
  const r2 = await goi("/api/poster/health");
  assert.equal(r2.status, 502);
  assert.match((await docJson(r2)).loi, /^Máy nhà không trả lời/);
  mayTraLoi = async () => Response.json({ loi: "Poster V2 trên máy nhà chưa mở" }, { status: 502 });
  const r3 = await goi("/api/poster/health");
  assert.equal(r3.status, 502);
  assert.deepEqual(await docJson(r3), { loi: "Poster V2 trên máy nhà chưa mở" });
});

test("202 {cho, trung} chuyển nguyên", async () => {
  const body = { cho: HEX32, toi_da_giay: 300, trung: true };
  mayTraLoi = async () => Response.json(body, { status: 202 });
  const r = await goi("/api/poster/api/v2/post/direct", { method: "POST", ct: "application/json", body: JSON.stringify({ folder_id: 1, video_path: "E:\\v\\a.mp4" }) });
  assert.equal(r.status, 202);
  assert.deepEqual(await docJson(r), body);
  assert.equal(r.headers.get("cache-control"), "no-store");
});

test("các mã khác chuyển nguyên status + body + content-type (mặc định JSON), cache-control no-store", async () => {
  mayTraLoi = async () => new Response('{"detail":"Not Found"}', { status: 404, headers: { "content-type": "application/json" } });
  const r = await goi("/api/poster/api/v2/khong-co");
  assert.equal(r.status, 404);
  assert.equal(await r.text(), '{"detail":"Not Found"}');
  assert.equal(r.headers.get("cache-control"), "no-store");
  // body byte → Response không tự gắn content-type (chuỗi thì tự thành text/plain)
  mayTraLoi = async () => new Response(new TextEncoder().encode('{"a":1}'), { status: 200 });
  const r2 = await goi("/api/poster/health");
  assert.equal(await r2.clone().text(), '{"a":1}');
  assert.match(r2.headers.get("content-type"), /^application\/json/);
  mayTraLoi = async () => new Response('{"detail":"x"}', { status: 429, headers: { "content-type": "application/json", "set-cookie": "a=b", "x-noi-bo": "1" } });
  const r3 = await goi("/api/poster/api/v2/queue/7/post", { method: "POST", ct: "application/json", body: "{}" });
  assert.equal(r3.status, 429);
  assert.equal(r3.headers.get("set-cookie"), null);
  assert.equal(r3.headers.get("x-noi-bo"), null);
});

// ---------- nhật ký ----------
test("lệnh ghi ghi 1 dòng console.log {poster, method, path, user, status}, không có body; GET không ghi", async () => {
  await goi("/api/poster/api/v2/stats/");
  assert.equal(nhatKy.length, 0);
  await goi("/api/poster/api/v2/settings/telegram_bot_token", { method: "PUT", ct: "application/json", body: JSON.stringify({ value: "BI-MAT-123" }) });
  assert.equal(nhatKy.length, 1);
  assert.doesNotMatch(nhatKy[0], /BI-MAT-123/);
  assert.doesNotMatch(nhatKy[0], /k-bi-mat/);
  const d = JSON.parse(nhatKy[0]);
  assert.deepEqual(d, { poster: true, method: "PUT", path: "/api/v2/settings/telegram_bot_token", user: "nhan", status: 200 });
});

// ---------- không ảnh hưởng route khác ----------
test("route cũ không bị nhánh poster nuốt: /api/posterx → 404 chung", async () => {
  const r = await goi("/api/posterx");
  assert.equal(r.status, 404);
  assert.equal((await docJson(r)).loi, "Không có API này");
  assert.equal(mayGoi.length, 0);
});
