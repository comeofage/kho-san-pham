// RU-W1 — Test route Worker /api/radar/* (docs/radar-uid.md §7, §11; D16).
// Chạy: node --test cf/test/radar-worker.test.mjs
// Máy nhà giả https://may.test như hoc-worker.test.mjs. fetch giả đặt TRƯỚC khi nạp mã; URL lạ → ném lỗi.
import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";

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

const W = await import("../src/worker.js");
const { default: worker, taoPhien, bamMatKhau, chuoiKyRequest } = W;
const R = await import("../src/radar.js");

const CAP_KHOA = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const KY_RIENG_TEST = Buffer.from(await crypto.subtle.exportKey("pkcs8", CAP_KHOA.privateKey)).toString("base64");
const GOC = "https://kho.test";
const UID = "1729706628656957720"; // > 2^53
const UID2 = "1737422436677814024";
const ctx = { waitUntil() {} };
let env, nhatKy, logGoc, errGoc;

beforeEach(async () => {
  mayGoi = [];
  mayTraLoi = async () => Response.json({ ok: true });
  env = {
    SESSION_SECRET: "bi-mat-test",
    USERS: JSON.stringify({
      lan: { ten: "Lan", hash: await bamMatKhau("x", undefined, 1000) },
      nhan: { ten: "Nhân", hash: await bamMatKhau("y", undefined, 1000) },
      comeofage: { ten: "Come", hash: await bamMatKhau("z", undefined, 1000) },
    }),
    ASSETS: { fetch: async () => new Response("static") },
    VIDEO_ORIGIN: "https://may.test", VIDEO_KEY: "k-bi-mat", RUNNER_KEY: "rk", KY_RIENG: KY_RIENG_TEST,
  };
  nhatKy = [];
  logGoc = console.log;
  errGoc = console.error;
  console.log = (...a) => nhatKy.push(a.join(" "));
  console.error = () => {};
});
afterEach(() => { console.log = logGoc; console.error = errGoc; });

const cookieCua = async (user) => `kho_s=${await taoPhien(env, user)}`;
async function goi(path, { user = "nhan", method = "GET", origin, body, headers = {} } = {}) {
  const h = { ...headers };
  if (user) h.cookie = await cookieCua(user);
  const o = origin === undefined ? (method === "GET" ? null : GOC) : origin;
  if (o) h.origin = o;
  if (body !== undefined && !h["content-type"]) h["content-type"] = "application/json";
  return worker.fetch(new Request(GOC + path, { method, headers: h, body }), env, ctx);
}
const docJson = async (r) => JSON.parse(await r.text());
const sha256Hex = (t) => createHash("sha256").update(Buffer.from(t, "utf8")).digest("hex");
const tuB64url = (s) => Uint8Array.from(Buffer.from(s, "base64url"));
const depsThat = (laChuKho = () => true) => ({
  goiMayNha: W.goiMayNha, traVeMayNha: W.traVeMayNha, loi: (m, s = 400) => Response.json({ loi: m }, { status: s }), json: Response.json, laChuKho,
});

async function kyHopLe(g, pathRunner) {
  const h = g.headers;
  const chuoi = chuoiKyRequest(g.method, pathRunner || g.url.pathname.replace(/^\/r/, ""), Number(h["x-ky-ngay"]), h["x-ky-nonce"], sha256Hex(g.body || ""));
  return crypto.subtle.verify({ name: "Ed25519" }, CAP_KHOA.publicKey, tuB64url(h["x-ky"]), chuoi);
}

// Mọi route POST của bảng §7 (path web, path runner, body gửi xuống, có cần uid trong body của trình duyệt).
const POST_BANG = [
  [`/api/radar/goc`, `/radar/goc`, { uid: UID }, true],
  [`/api/radar/goc/${UID}/tim-lai`, `/radar/goc/${UID}/tim-lai`, {}, false],
  [`/api/radar/goc/${UID}/ngung`, `/radar/goc/${UID}/ngung`, {}, false],
  [`/api/radar/goc/${UID}/theo-lai`, `/radar/goc/${UID}/theo-lai`, {}, false],
  [`/api/radar/goc/${UID}/them-tay`, `/radar/goc/${UID}/them-tay`, { uid: UID2 }, true],
  ...["ghim", "bo-ghim", "loai", "bo-loai"].map((a) => [`/api/radar/goc/${UID}/uid/${UID2}/${a}`, `/radar/goc/${UID}/uid/${UID2}/${a}`, { uid: UID2 }, false]),
  [`/api/radar/chup-lai`, `/radar/chup-lai`, {}, false],
];
const GET_BANG = [["/api/radar/bang", "/radar/bang"], [`/api/radar/uid/${UID}`, `/radar/uid/${UID}`]];

// ---------- tuyenRadar ----------
test("tuyenRadar: 2 route GET + 10 route POST đúng bảng §7", () => {
  assert.deepEqual(R.tuyenRadar("/api/radar/bang"), { GET: { dich: "/radar/bang" } });
  assert.deepEqual(R.tuyenRadar(`/api/radar/uid/${UID}`), { GET: { dich: `/radar/uid/${UID}` } });
  assert.deepEqual(R.tuyenRadar("/api/radar/goc"), { POST: { dich: "/radar/goc", act: "goc" } });
  assert.deepEqual(R.tuyenRadar("/api/radar/chup-lai"), { POST: { dich: "/radar/chup-lai", act: "chup-lai" } });
  assert.deepEqual(R.tuyenRadar(`/api/radar/goc/${UID}/them-tay`), { POST: { dich: `/radar/goc/${UID}/them-tay`, act: "them-tay", goc: UID } });
  for (const a of ["tim-lai", "ngung", "theo-lai"]) {
    assert.deepEqual(R.tuyenRadar(`/api/radar/goc/${UID}/${a}`), { POST: { dich: `/radar/goc/${UID}/${a}`, act: a, goc: UID } });
  }
  for (const a of ["ghim", "bo-ghim", "loai", "bo-loai"]) {
    assert.deepEqual(R.tuyenRadar(`/api/radar/goc/${UID}/uid/${UID2}/${a}`), { POST: { dich: `/radar/goc/${UID}/uid/${UID2}/${a}`, act: a, goc: UID, uid: UID2 } });
  }
  assert.equal(String(R.RE_UID), String(/^\d{19}$/));
  assert.equal(R.RADAR_BODY_TOI_DA, 16 * 1024);
});

test("tuyenRadar: uid/goc sai dạng, path lạ → null", () => {
  const sai = [
    "/api/radar", "/api/radar/", "/api/radar/x", "/api/radar/bang/", "/api/radar/uid/", "/api/radar/uid/12", `/api/radar/uid/${UID}0`,
    `/api/radar/uid/${UID.slice(1)}`, "/api/radar/uid/abcdefghijklmnopqrs", `/api/radar/uid/${UID}/`, "/api/radar/goc/", "/api/radar/goc/12/ngung",
    `/api/radar/goc/${UID}`, `/api/radar/goc/${UID}/xoa`, `/api/radar/goc/${UID}/ngung/`, `/api/radar/goc/${UID}0/ngung`,
    `/api/radar/goc/${UID}/uid/12/ghim`, `/api/radar/goc/12/uid/${UID2}/ghim`, `/api/radar/goc/${UID}/uid/${UID2}/xoa`, `/api/radar/goc/${UID}/uid/${UID2}`,
    `/api/radar/goc/${UID}/uid/${UID2}/ghim/..`, "/api/radar/goc/%31729706628656957720/ngung", "/api/radar//bang", "/api/radar/chup-lai/x", null, undefined,
  ];
  for (const p of sai) assert.equal(R.tuyenRadar(p), null, String(p));
});

// ---------- quyền ----------
test("chưa đăng nhập → 401 (mọi route), máy nhà không bị gọi", async () => {
  for (const [p] of GET_BANG) assert.equal((await goi(p, { user: null })).status, 401, p);
  for (const [p] of POST_BANG) assert.equal((await goi(p, { user: null, method: "POST" })).status, 401, p);
  assert.equal(mayGoi.length, 0);
});

test("người thường → 403 TRƯỚC mọi fetch (cả route lạ/sai method/sai Origin), không lộ chữ của máy nhà", async () => {
  mayTraLoi = async () => Response.json({ loi: "E:\\kho-runner\\radar_uid.db hỏng" }, { status: 500 });
  for (const [p] of GET_BANG) assert.equal((await goi(p, { user: "lan" })).status, 403, p);
  for (const [p, , body] of POST_BANG) {
    const r = await goi(p, { user: "lan", method: "POST", body: JSON.stringify(body) });
    assert.equal(r.status, 403, p);
    const t = await r.text();
    assert.ok(!t.includes(":\\") && !t.includes("kho-runner") && !t.includes("radar_uid"), t);
  }
  for (const p of ["/api/radar/x", "/api/radar/uid/12", "/api/radar/goc/12/ngung"]) assert.equal((await goi(p, { user: "lan", method: "POST" })).status, 403, p);
  assert.equal((await goi("/api/radar/bang", { user: "lan", method: "DELETE" })).status, 403);
  assert.equal((await goi("/api/radar/goc", { user: "lan", method: "POST", origin: "https://evil.test", body: "{}" })).status, 403);
  assert.equal((await goi("/api/radar/goc", { user: "lan", method: "POST", body: "x".repeat(20000) })).status, 403);
  assert.equal(mayGoi.length, 0);
});

test("apiRadar gọi thẳng: phiên trống/null/user rỗng/người thường → 403, không gọi goiMayNha", async () => {
  let goiMay = 0;
  const deps = { ...depsThat((u) => u === "nhan"), goiMayNha: async () => { goiMay++; return Response.json({}); } };
  const url = new URL(`${GOC}/api/radar/chup-lai`);
  for (const phien of [null, undefined, {}, { user: "" }, { user: "lan" }, { user: 5 }]) {
    const req = new Request(url, { method: "POST", headers: { origin: GOC } });
    assert.equal((await R.apiRadar(req, env, url, phien, deps)).status, 403, JSON.stringify(phien));
  }
  assert.equal(goiMay, 0);
});

// ---------- đọc ----------
test("chủ kho GET bang/uid → GET /r/radar/...: x-key + x-runner-key, KHÔNG ký, KHÔNG content-type, có timeout; trả nguyên văn; id giữ chuỗi", async () => {
  for (const [p, dich] of GET_BANG) {
    mayGoi = [];
    const than = `{"nhom":[{"goc":"${UID}","ds":[{"uid":"${UID2}","trung_vi":700}]}]}`;
    mayTraLoi = async () => new Response(than, { status: 200, headers: { "content-type": "application/json; charset=utf-8" } });
    const r = await goi(p);
    assert.equal(r.status, 200, p);
    assert.equal(await r.text(), than);
    assert.equal(r.headers.get("cache-control"), "no-store");
    assert.equal(mayGoi.length, 1);
    const g = mayGoi[0];
    assert.equal(g.method, "GET");
    assert.equal(g.url.href, `https://may.test/r${dich}`);
    assert.equal(g.headers["x-key"], "k-bi-mat");
    assert.equal(g.headers["x-runner-key"], "rk");
    for (const k of ["x-ky", "x-ky-ngay", "x-ky-nonce", "content-type"]) assert.equal(g.headers[k], undefined, k);
    assert.equal(g.body, undefined);
    assert.ok(g.signal, "phải có timeout");
  }
});

test("GET: query của trình duyệt không chuyển xuống máy nhà", async () => {
  await goi("/api/radar/bang?boi=hacker&x=1&uid=2");
  assert.equal(mayGoi[0].url.href, "https://may.test/r/radar/bang");
});

test("GET uid sai dạng → 404 trước khi gọi máy nhà; sai method → 405", async () => {
  for (const u of ["12", `${UID}0`, "abc", "%31729706628656957720"]) assert.equal((await goi(`/api/radar/uid/${u}`)).status, 404, u);
  assert.equal((await goi("/api/radar/bang", { method: "POST" })).status, 405);
  assert.equal((await goi(`/api/radar/uid/${UID}`, { method: "POST" })).status, 405);
  assert.equal((await goi("/api/radar/goc")).status, 405);
  assert.equal((await goi("/api/radar/chup-lai")).status, 405);
  assert.equal((await goi(`/api/radar/goc/${UID}/ngung`)).status, 405);
  assert.equal((await goi(`/api/radar/goc/${UID}/uid/${UID2}/ghim`, { method: "PUT" })).status, 405);
  assert.equal((await goi("/api/radar/bang", { method: "DELETE" })).status, 405);
  assert.equal(mayGoi.length, 0);
});

test("path /api/radar lạ → 404 (không rơi xuống route khác)", async () => {
  for (const p of ["/api/radar", "/api/radar/", "/api/radar/xoa", `/api/radar/goc/${UID}/xoa`]) assert.equal((await goi(p)).status, 404, p);
  assert.equal(mayGoi.length, 0);
});

// ---------- ghi ----------
for (const [pWeb, pRunner, body, can] of POST_BANG) {
  test(`chủ kho POST ${pWeb.replace(UID2, "<uid>").replace(UID, "<goc>")} → POST /r${pRunner.replace(UID2, "<uid>").replace(UID, "<goc>")}, ký D7, body chỉ {boi[,uid]}`, async () => {
    mayTraLoi = async () => Response.json({ viec_id: "j1" }, { status: 202 });
    // body trình duyệt có khoá giả mạo: chỉ uid (nếu route cần) được giữ
    const r = await goi(pWeb, { method: "POST", body: JSON.stringify({ ...body, boi: "ke-mao-danh", goc: "x", hanh_dong: "xoa", x: 1 }) });
    assert.equal(r.status, 202);
    assert.equal(mayGoi.length, 1, "không thử lại");
    const g = mayGoi[0];
    assert.equal(g.method, "POST");
    assert.equal(g.url.href, `https://may.test/r${pRunner}`);
    assert.equal(g.headers["content-type"], "application/json");
    assert.equal(g.headers["x-key"], "k-bi-mat");
    assert.equal(g.headers["x-runner-key"], "rk");
    assert.equal(g.body, can ? JSON.stringify({ boi: "nhan", uid: body.uid }) : '{"boi":"nhan"}');
    assert.match(g.headers["x-ky"], /^[A-Za-z0-9_-]{86}$/);
    assert.match(g.headers["x-ky-nonce"], /^[0-9a-f]{32}$/);
    assert.match(g.headers["x-ky-ngay"], /^\d{13}$/);
    assert.ok(await kyHopLe(g, pRunner), "chữ ký D7 phải kiểm được bằng khoá công khai, đúng path runner");
    assert.ok(!(await kyHopLe(g, "/radar/chup-lai/khac")), "đổi path thì chữ ký không khớp");
    assert.ok(nhatKy.some((d) => d.startsWith("radar ") && d.endsWith("boi nhan → 202")), nhatKy.join("|"));
  });
}

test("POST route không cần body: không body, hoặc body rỗng, đều được; chủ kho thứ hai → boi lấy từ phiên", async () => {
  const r = await goi("/api/radar/chup-lai", { user: "comeofage", method: "POST" });
  assert.equal(r.status, 200);
  assert.equal(mayGoi[0].body, '{"boi":"comeofage"}');
  assert.ok(await kyHopLe(mayGoi[0]));
  const r2 = await goi(`/api/radar/goc/${UID}/ngung`, { method: "POST", body: "" });
  assert.equal(r2.status, 200);
  assert.equal(mayGoi[1].body, '{"boi":"nhan"}');
});

test("id 19 số giữ nguyên chuỗi xuống máy nhà (không qua Number)", async () => {
  await goi("/api/radar/goc", { method: "POST", body: `{"uid":"${UID}"}` });
  assert.equal(mayGoi[0].body, `{"boi":"nhan","uid":"${UID}"}`);
  assert.ok(Number.isSafeInteger(Number(UID)) === false, "UID mẫu phải > 2^53");
});

test("POST goc / them-tay: uid thiếu/sai dạng/không phải chuỗi/JSON hỏng → 400, không gọi máy nhà", async () => {
  const xau = [
    undefined, "", "{}", "[]", "null", "không phải json", `{"uid":${UID}}`, '{"uid":1729706628656957720}', '{"uid":"12"}', `{"uid":"${UID}0"}`,
    `{"uid":" ${UID}"}`, `{"uid":"${UID}\\n"}`, '{"uid":["1729706628656957720"]}', '{"uid":null}', `{"UID":"${UID}"}`, `{"goc":"${UID}"}`,
  ];
  for (const p of ["/api/radar/goc", `/api/radar/goc/${UID}/them-tay`]) {
    for (const b of xau) {
      const r = await goi(p, { method: "POST", body: b });
      assert.equal(r.status, 400, `${p} ${b}`);
      assert.equal((await docJson(r)).loi, "UID phải đủ 19 chữ số");
    }
  }
  assert.equal(mayGoi.length, 0);
});

test("POST: thiếu Origin → 403, Origin lạ → 403 (kể cả gọi thẳng apiRadar), không gọi máy nhà", async () => {
  for (const [p, , body] of POST_BANG) {
    assert.equal((await goi(p, { method: "POST", origin: null, body: JSON.stringify(body) })).status, 403, p);
    assert.equal((await goi(p, { method: "POST", origin: "https://evil.test", body: JSON.stringify(body) })).status, 403, p);
  }
  const url = new URL(`${GOC}/api/radar/chup-lai`);
  for (const headers of [{ origin: "https://evil.test" }, {}]) {
    const req = new Request(url, { method: "POST", headers });
    assert.equal((await R.apiRadar(req, env, url, { user: "nhan" }, depsThat())).status, 403);
  }
  assert.equal(mayGoi.length, 0);
});

test("POST: id trên path sai dạng → 404 trước khi gọi máy nhà", async () => {
  for (const p of ["/api/radar/goc/12/ngung", `/api/radar/goc/${UID}0/tim-lai`, `/api/radar/goc/${UID}/uid/12/ghim`, `/api/radar/goc/abc/uid/${UID2}/loai`]) {
    assert.equal((await goi(p, { method: "POST" })).status, 404, p);
  }
  assert.equal(mayGoi.length, 0);
});

test("POST: body > 16 KB → 413 (content-length, và độ dài thật không có header); đúng 16 KB qua", async () => {
  const lon = JSON.stringify({ uid: UID, x: "a".repeat(17 * 1024) });
  assert.equal((await goi("/api/radar/goc", { method: "POST", body: lon })).status, 413);
  assert.equal((await goi("/api/radar/chup-lai", { method: "POST", body: lon })).status, 413);
  const url = new URL(`${GOC}/api/radar/goc`);
  const req = new Request(url, { method: "POST", headers: { origin: GOC, "content-length": String(17 * 1024), "content-type": "application/json" }, body: "{}" });
  assert.equal((await R.apiRadar(req, env, url, { user: "nhan" }, depsThat())).status, 413);
  // luồng chunked không có content-length
  const luong = new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(lon)); c.close(); } });
  const req2 = new Request(url, { method: "POST", headers: { origin: GOC, "content-type": "application/json" }, body: luong, duplex: "half" });
  assert.equal((await R.apiRadar(req2, env, url, { user: "nhan" }, depsThat())).status, 413);
  assert.equal(mayGoi.length, 0);
  const dem = JSON.stringify({ uid: UID, d: "" });
  const vua = JSON.stringify({ uid: UID, d: "a".repeat(16 * 1024 - Buffer.byteLength(dem)) });
  assert.equal(Buffer.byteLength(vua), 16 * 1024);
  const r2 = await goi("/api/radar/goc", { method: "POST", body: vua });
  assert.equal(r2.status, 200);
  assert.equal(mayGoi[0].body, `{"boi":"nhan","uid":"${UID}"}`);
});

test("POST có body mà content-type không phải application/json → 415, không gọi máy nhà", async () => {
  for (const ct of ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", "application/jsonx"]) {
    assert.equal((await goi("/api/radar/goc", { method: "POST", body: `{"uid":"${UID}"}`, headers: { "content-type": ct } })).status, 415, ct);
    assert.equal((await goi("/api/radar/chup-lai", { method: "POST", body: "{}", headers: { "content-type": ct } })).status, 415, ct);
  }
  assert.equal(mayGoi.length, 0);
  assert.equal((await goi("/api/radar/goc", { method: "POST", body: `{"uid":"${UID}"}`, headers: { "content-type": "application/json; charset=utf-8" } })).status, 200);
});

// ---------- lỗi từ máy nhà ----------
test("lỗi JSON của runner (404/409/429/503...) → giữ status + câu `loi`, bỏ khoá khác", async () => {
  const ca = [[404, "Không có UID này trong Radar"], [409, "Đã đủ 2 UID gốc: ngừng bớt"], [429, "Vượt hạn mức"], [503, "Radar UID chưa bật"], [400, "UID phải đủ 19 chữ số"], [413, "Dữ liệu quá lớn"], [415, "Cần JSON"]];
  for (const [s, cau] of ca) {
    mayTraLoi = async () => new Response(JSON.stringify({ loi: cau, chi_tiet: "E:\\kho-runner\\x", token: "secret" }), { status: s, headers: { "content-type": "application/json" } });
    for (const [p, method] of [["/api/radar/bang", "GET"], [`/api/radar/goc/${UID}/ngung`, "POST"]]) {
      const r = await goi(p, { method });
      assert.equal(r.status, s, `${s} ${p}`);
      assert.deepEqual(await docJson(r), { loi: cau });
    }
  }
});

test("không chuyển thân lỗi thô: đường dẫn đĩa/traceback/quá dài/không phải chuỗi/văn bản thô/500 → lỗi chung của Worker", async () => {
  const ca = [
    [new Response(JSON.stringify({ loi: "E:\\kho-runner\\radar_uid.db hỏng" }), { status: 409, headers: { "content-type": "application/json" } }), 409],
    [new Response(JSON.stringify({ loi: "Traceback (most recent call last)" }), { status: 409, headers: { "content-type": "application/json" } }), 409],
    [new Response(JSON.stringify({ loi: "a".repeat(500) }), { status: 429, headers: { "content-type": "application/json" } }), 429],
    [new Response(JSON.stringify({ loi: { x: 1 } }), { status: 404, headers: { "content-type": "application/json" } }), 404],
    [new Response("Traceback: boom at E:\\kho-runner\\api.py", { status: 400, headers: { "content-type": "text/plain" } }), 400],
    [new Response(JSON.stringify({ loi: "sqlite3.OperationalError ở E:\\kho-runner\\radar_uid.db" }), { status: 500, headers: { "content-type": "application/json" } }), 502],
    [new Response("<html>Bad gateway</html>", { status: 502, headers: { "content-type": "text/html" } }), 502],
    [new Response("<html>timeout</html>", { status: 524, headers: { "content-type": "text/html" } }), 504],
    [new Response("<html>origin down</html>", { status: 530 }), 502],
  ];
  for (const [i, [resp, s]] of ca.entries()) {
    mayTraLoi = async () => resp;
    const r = await goi("/api/radar/bang");
    assert.equal(r.status, s, `ca ${i}`);
    assert.match(r.headers.get("content-type"), /^application\/json/, `ca ${i}`);
    const t = await r.text();
    assert.ok(JSON.parse(t).loi, `ca ${i}`);
    assert.ok(!/E:\\|Traceback|kho-runner|\.db|\.py|sqlite|Bad gateway|aaaaaaaaaa|secret/.test(t), `ca ${i}: ${t}`);
  }
});

test("máy nhà trả 401/403 (khoá/chữ ký lệch) → 502, KHÔNG chuyển 401 cho trình duyệt", async () => {
  for (const s of [401, 403]) {
    mayTraLoi = async () => Response.json({ loi: "sai chữ ký" }, { status: s });
    for (const [p, method] of [["/api/radar/chup-lai", "POST"], ["/api/radar/bang", "GET"]]) {
      const r = await goi(p, { method });
      assert.equal(r.status, 502, `${s} ${p}`);
      assert.ok((await docJson(r)).loi);
    }
  }
});

test("lỗi tạm: mạng lỗi → 502, hết giờ → 504; không thử lại", async () => {
  const ca = [
    [async () => { throw new TypeError("fetch failed"); }, 502],
    [async () => { throw Object.assign(new Error("t"), { name: "TimeoutError" }); }, 504],
  ];
  for (const [i, [f, s]] of ca.entries()) {
    mayGoi = [];
    mayTraLoi = f;
    const r = await goi("/api/radar/chup-lai", { method: "POST" });
    assert.equal(r.status, s, `ca ${i}`);
    assert.match(r.headers.get("content-type"), /^application\/json/, `ca ${i}`);
    assert.ok((await docJson(r)).loi, `ca ${i}`);
    assert.equal(mayGoi.length, 1, `ca ${i}: không thử lại`);
  }
});

// ---------- cấu hình, nhật ký ----------
test("thiếu VIDEO_ORIGIN/VIDEO_KEY/RUNNER_KEY/KY_RIENG → 503, không gọi máy nhà; KY_RIENG hỏng → 503 không gửi request chưa ký", async () => {
  const goc = { ...env };
  for (const k of ["VIDEO_ORIGIN", "VIDEO_KEY", "RUNNER_KEY", "KY_RIENG"]) {
    env = { ...goc };
    delete env[k];
    assert.equal((await goi("/api/radar/bang")).status, 503, k);
    assert.equal((await goi("/api/radar/chup-lai", { method: "POST" })).status, 503, k);
  }
  env = { ...goc, KY_RIENG: "không-phải-khoá" };
  assert.equal((await goi("/api/radar/chup-lai", { method: "POST" })).status, 503);
  assert.equal(mayGoi.length, 0);
});

test("nhật ký không chứa token/khoá/cookie/chữ ký", async () => {
  await goi("/api/radar/goc", { method: "POST", body: `{"uid":"${UID}"}` });
  await goi("/api/radar/bang");
  const log = nhatKy.join("\n");
  for (const bimat of ["k-bi-mat", "rk", KY_RIENG_TEST, "kho_s=", mayGoi[0].headers["x-ky"]]) {
    if (bimat === "rk") continue; // quá ngắn để tìm tin cậy ("rk" nằm trong từ thường)
    assert.ok(!log.includes(bimat), bimat);
  }
  assert.ok(log.includes("radar goc boi nhan → 200"), log);
});

test("worker.js export goiMayNha, traVeMayNha; radar.js export tuyenRadar, apiRadar", () => {
  assert.equal(typeof W.goiMayNha, "function");
  assert.equal(typeof W.traVeMayNha, "function");
  assert.equal(typeof R.tuyenRadar, "function");
  assert.equal(typeof R.apiRadar, "function");
});
