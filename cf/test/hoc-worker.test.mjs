// HT-W1 — Test route Worker /api/hoc/* (docs/hoc-tu-dong.md §3.8, §6.2, §6.3, §8.3 HT-W1).
// Chạy: node --test cf/test/hoc-worker.test.mjs
// Máy nhà giả https://may.test như worker.test.mjs. fetch giả đặt TRƯỚC khi nạp mã; URL lạ → ném lỗi.
// Mỗi ca gọi máy nhà khẳng định ĐÚNG request gửi xuống video_server theo §3.8 (path, method, content-type, header ký)
// để không lệch hợp đồng với HT-A1 (video_server RE_R / R_HEADER) — moi:hop-dong-cheo-chang-lech.
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
const H = await import("../src/hoc.js");

const CAP_KHOA = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const KY_RIENG_TEST = Buffer.from(await crypto.subtle.exportKey("pkcs8", CAP_KHOA.privateKey)).toString("base64");
const GOC = "https://kho.test";
const MA = "bh20261123ab12";
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
// origin mặc định đúng cho method khác GET; origin: null → không gửi header Origin.
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

// Kiểm chữ ký D7 của request đã gửi xuống video_server: path ký = path runner (bỏ /r, không query), body đúng byte gửi.
async function kyHopLe(g) {
  const h = g.headers;
  const chuoi = chuoiKyRequest(g.method, g.url.pathname.replace(/^\/r/, ""), Number(h["x-ky-ngay"]), h["x-ky-nonce"], sha256Hex(g.body || ""));
  return crypto.subtle.verify({ name: "Ed25519" }, CAP_KHOA.publicKey, tuB64url(h["x-ky"]), chuoi);
}

// ---------- tuyenHoc (bảng route §3.8) ----------
test("tuyenHoc: 4 route đúng bảng §3.8", () => {
  assert.deepEqual(H.tuyenHoc("/api/hoc/bao-cao"), { GET: { dich: "/hoc/bao-cao", query: ["ngay"], mau: { ngay: H.RE_NGAY_HOC } } });
  const bh = H.tuyenHoc("/api/hoc/bai-hoc");
  assert.equal(bh.GET.dich, "/hoc/bai-hoc");
  assert.deepEqual(bh.GET.query, ["gioi_han"]);
  assert.equal(Object.keys(bh).join(), "GET");
  for (const act of ["hoan-tac", "bat-lai"]) {
    const t = H.tuyenHoc(`/api/hoc/bai-hoc/${MA}/${act}`);
    assert.deepEqual(t, { POST: { dich: `/hoc/bai-hoc/${MA}/${act}`, ma: MA, act } });
  }
});

test("tuyenHoc: ma sai dạng / path lạ → null", () => {
  const sai = [
    "/api/hoc", "/api/hoc/", "/api/hoc/xoa", "/api/hoc/bao-cao/", "/api/hoc/bai-hoc/", "/api/hoc/bai-hoc/bh20261123ab12",
    "/api/hoc/bai-hoc/bh20261123ab12/xoa", "/api/hoc/bai-hoc/bh20261123ab12/hoan-tac/", "/api/hoc/bai-hoc/BH20261123ab12/hoan-tac",
    "/api/hoc/bai-hoc/bh20261123AB12/hoan-tac", "/api/hoc/bai-hoc/bh2026112ab12/hoan-tac", "/api/hoc/bai-hoc/bh20261123ab123/hoan-tac",
    "/api/hoc/bai-hoc/bh20261123ab1/bat-lai", "/api/hoc/bai-hoc/../hoan-tac", "/api/hoc/bai-hoc/bh20261123ab%31/hoan-tac",
    "/api/hoc/bai-hoc/bh20261123ab12/hoan-tac/../bat-lai", "/api/hoc/bai-hoc//hoan-tac", "/api/hoc//bao-cao",
  ];
  for (const p of sai) assert.equal(H.tuyenHoc(p), null, p);
  assert.ok(H.RE_MA_BAI_HOC.test(MA));
  assert.equal(String(H.RE_MA_BAI_HOC), String(/^bh\d{8}[a-z0-9]{4}$/));
});

// ---------- quyền ----------
test("chưa đăng nhập → 401 (GET và POST), máy nhà không bị gọi", async () => {
  assert.equal((await goi("/api/hoc/bao-cao", { user: null })).status, 401);
  assert.equal((await goi("/api/hoc/bai-hoc", { user: null })).status, 401);
  for (const act of ["hoan-tac", "bat-lai"]) {
    assert.equal((await goi(`/api/hoc/bai-hoc/${MA}/${act}`, { user: null, method: "POST" })).status, 401, act);
  }
  assert.equal(mayGoi.length, 0);
});

test("người thường → 403 cả đọc lẫn ghi, không gọi máy nhà, không lộ chữ của máy nhà", async () => {
  mayTraLoi = async () => Response.json({ loi: "E:\\kho-runner\\hoc.db hỏng" }, { status: 500 });
  for (const [p, method] of [["/api/hoc/bao-cao", "GET"], ["/api/hoc/bai-hoc", "GET"], [`/api/hoc/bai-hoc/${MA}/hoan-tac`, "POST"], [`/api/hoc/bai-hoc/${MA}/bat-lai`, "POST"]]) {
    const r = await goi(p, { user: "lan", method });
    assert.equal(r.status, 403, p);
    const t = await r.text();
    assert.ok(!t.includes(":\\") && !t.includes("kho-runner"), t);
  }
  // ma sai dạng với người thường: vẫn 403 (quyền kiểm trước tuyến, §3.8)
  assert.equal((await goi("/api/hoc/bai-hoc/xx/hoan-tac", { user: "lan", method: "POST" })).status, 403);
  assert.equal(mayGoi.length, 0);
});

test("apiHoc gọi thẳng: phiên trống/null/user rỗng → 403, không gọi goiMayNha (không gắn tác dụng phụ vào phiên trắng)", async () => {
  let goiMay = 0;
  const deps = {
    goiMayNha: async () => { goiMay++; return Response.json({}); }, traVeMayNha: (r) => r, laChuKho: (u) => u === "nhan",
    loi: (m, s = 400) => Response.json({ loi: m }, { status: s }), json: (d, s = 200) => Response.json(d, { status: s }),
  };
  const url = new URL(`${GOC}/api/hoc/bai-hoc/${MA}/hoan-tac`);
  for (const phien of [null, undefined, {}, { user: "" }, { user: "lan" }]) {
    const req = new Request(url, { method: "POST", headers: { origin: GOC } });
    assert.equal((await H.apiHoc(req, env, url, phien, deps)).status, 403, JSON.stringify(phien));
  }
  assert.equal(goiMay, 0);
});

// ---------- đọc ----------
test("chủ kho GET bao-cao → GET /r/hoc/bao-cao: x-key + x-runner-key, KHÔNG ký, KHÔNG content-type; trả nguyên văn", async () => {
  const than = JSON.stringify({ ngay: "2026-11-23", lan: { trang_thai: "xong" }, hieu_luc: [{ ma: MA, bat_lai_den: null }] });
  mayTraLoi = async () => new Response(than, { status: 200, headers: { "content-type": "application/json; charset=utf-8" } });
  const r = await goi("/api/hoc/bao-cao");
  assert.equal(r.status, 200);
  assert.equal(await r.text(), than);
  assert.match(r.headers.get("content-type"), /^application\/json/);
  assert.equal(r.headers.get("cache-control"), "no-store");
  assert.equal(mayGoi.length, 1);
  const g = mayGoi[0];
  assert.equal(g.method, "GET");
  assert.equal(g.url.href, "https://may.test/r/hoc/bao-cao");
  assert.equal(g.headers["x-key"], "k-bi-mat");
  assert.equal(g.headers["x-runner-key"], "rk");
  for (const k of ["x-ky", "x-ky-ngay", "x-ky-nonce", "content-type"]) assert.equal(g.headers[k], undefined, k);
  assert.equal(g.body, undefined);
  assert.ok(g.signal, "phải có timeout");
});

test("GET bao-cao: chỉ chuyển ngay hợp lệ, bỏ khoá lạ; ngay sai mẫu → 400 không gọi máy nhà", async () => {
  await goi("/api/hoc/bao-cao?ngay=2026-11-23&boi=hacker&x=1");
  assert.equal(mayGoi[0].url.pathname, "/r/hoc/bao-cao");
  assert.equal(mayGoi[0].url.search, "?ngay=2026-11-23");
  mayGoi = [];
  for (const q of ["ngay=2026/11/23", "ngay=", "ngay=2026-11-23x", "ngay=26-11-23", "ngay=..%2F..", "ngay=2026-11-2%0A"]) {
    const r = await goi(`/api/hoc/bao-cao?${q}`);
    assert.equal(r.status, 400, q);
    assert.ok((await docJson(r)).loi);
  }
  assert.equal(mayGoi.length, 0);
});

test("GET bai-hoc: gioi_han ^\\d{1,3}$ chuyển xuống; sai → 400", async () => {
  await goi("/api/hoc/bai-hoc?gioi_han=50&ngay=2026-11-23");
  assert.equal(mayGoi[0].url.href, "https://may.test/r/hoc/bai-hoc?gioi_han=50");
  mayGoi = [];
  await goi("/api/hoc/bai-hoc");
  assert.equal(mayGoi[0].url.href, "https://may.test/r/hoc/bai-hoc");
  mayGoi = [];
  for (const q of ["gioi_han=abc", "gioi_han=1000", "gioi_han=-1", "gioi_han="]) assert.equal((await goi(`/api/hoc/bai-hoc?${q}`)).status, 400, q);
  assert.equal(mayGoi.length, 0);
});

// ---------- ghi ----------
for (const act of ["hoan-tac", "bat-lai"]) {
  test(`chủ kho POST ${act} → POST /r/hoc/bai-hoc/<ma>/${act}, JSON, ký D7 đúng path, body Worker tự dựng {"boi":"nhan"}`, async () => {
    mayTraLoi = async () => Response.json({ bai_hoc: { ma: MA, trang_thai: act === "hoan-tac" ? "hoan_tac" : "hieu_luc" } });
    const r = await goi(`/api/hoc/bai-hoc/${MA}/${act}`, { method: "POST", body: JSON.stringify({ boi: "ke-mao-danh", ma: "khac", x: 1 }) });
    assert.equal(r.status, 200);
    assert.equal((await docJson(r)).bai_hoc.ma, MA);
    assert.equal(mayGoi.length, 1, "không thử lại");
    const g = mayGoi[0];
    assert.equal(g.method, "POST");
    assert.equal(g.url.href, `https://may.test/r/hoc/bai-hoc/${MA}/${act}`);
    assert.equal(g.headers["content-type"], "application/json");
    assert.equal(g.headers["x-key"], "k-bi-mat");
    assert.equal(g.headers["x-runner-key"], "rk");
    assert.equal(g.body, '{"boi":"nhan"}');
    assert.match(g.headers["x-ky"], /^[A-Za-z0-9_-]{86}$/);
    assert.match(g.headers["x-ky-nonce"], /^[0-9a-f]{32}$/);
    assert.match(g.headers["x-ky-ngay"], /^\d{13}$/);
    assert.ok(await kyHopLe(g), "chữ ký D7 phải kiểm được bằng khoá công khai");
    // ký đúng path runner /hoc/bai-hoc/<ma>/<act> — đổi path thì chữ ký không khớp
    const saiPath = chuoiKyRequest("POST", `/hoc/bai-hoc/${MA}/${act === "hoan-tac" ? "bat-lai" : "hoan-tac"}`, Number(g.headers["x-ky-ngay"]), g.headers["x-ky-nonce"], sha256Hex(g.body));
    assert.ok(!(await crypto.subtle.verify({ name: "Ed25519" }, CAP_KHOA.publicKey, tuB64url(g.headers["x-ky"]), saiPath)));
    assert.ok(nhatKy.includes(`hoc ${act} ${MA} boi nhan → 200`), nhatKy.join("|"));
  });

  test(`POST ${act}: chủ kho thứ hai (comeofage) → boi lấy từ phiên; không body cũng được`, async () => {
    const r = await goi(`/api/hoc/bai-hoc/${MA}/${act}`, { user: "comeofage", method: "POST" });
    assert.equal(r.status, 200);
    assert.equal(mayGoi[0].body, '{"boi":"comeofage"}');
    assert.ok(await kyHopLe(mayGoi[0]));
  });

  test(`POST ${act}: thiếu Origin → 403, Origin lạ → 403, không gọi máy nhà`, async () => {
    assert.equal((await goi(`/api/hoc/bai-hoc/${MA}/${act}`, { method: "POST", origin: null })).status, 403);
    assert.equal((await goi(`/api/hoc/bai-hoc/${MA}/${act}`, { method: "POST", origin: "https://evil.test" })).status, 403);
    // gọi thẳng apiHoc với Origin lạ (không qua chặn chung ở fetch()) cũng 403
    const url = new URL(`${GOC}/api/hoc/bai-hoc/${MA}/${act}`);
    const req = new Request(url, { method: "POST", headers: { origin: "https://evil.test" } });
    const deps = { goiMayNha: W.goiMayNha, traVeMayNha: W.traVeMayNha, loi: (m, s = 400) => Response.json({ loi: m }, { status: s }), json: Response.json, laChuKho: () => true };
    assert.equal((await H.apiHoc(req, env, url, { user: "nhan" }, deps)).status, 403);
    assert.equal(mayGoi.length, 0);
  });

  test(`POST ${act}: ma sai dạng → 404 trước khi gọi máy nhà`, async () => {
    for (const ma of ["bh2026112ab12", "BH20261123ab12", "bh20261123AB12", "bh20261123ab123", "x", "..", "bh20261123ab%31", "j20261117150000ab12"]) {
      const r = await goi(`/api/hoc/bai-hoc/${ma}/${act}`, { method: "POST" });
      assert.equal(r.status, 404, ma);
    }
    assert.equal(mayGoi.length, 0);
  });

  test(`POST ${act}: 409 từ máy nhà về NGUYÊN VĂN (status + body), không đổi thành 500`, async () => {
    const cau = act === "hoan-tac" ? "bài học không còn hiệu lực" : "đã quá 7 ngày kể từ lúc hoàn tác, không bật lại được nữa";
    const than = JSON.stringify({ loi: cau });
    mayTraLoi = async () => new Response(than, { status: 409, headers: { "content-type": "application/json; charset=utf-8" } });
    const r = await goi(`/api/hoc/bai-hoc/${MA}/${act}`, { method: "POST" });
    assert.equal(r.status, 409);
    assert.equal(await r.text(), than);
    assert.ok(nhatKy.includes(`hoc ${act} ${MA} boi nhan → 409`));
    assert.equal(mayGoi.length, 1);
  });
}

test("404/400/503 JSON từ máy nhà → chuyển nguyên status + body", async () => {
  for (const [s, than] of [[404, '{"loi":"không có bài học"}'], [400, '{"loi":"ngày sai"}'], [503, '{"loi":"Học tự động chưa bật"}']]) {
    mayTraLoi = async () => new Response(than, { status: s, headers: { "content-type": "application/json" } });
    const r1 = await goi(`/api/hoc/bai-hoc/${MA}/hoan-tac`, { method: "POST" });
    assert.equal(r1.status, s);
    assert.equal(await r1.text(), than);
    const r2 = await goi("/api/hoc/bao-cao");
    assert.equal(r2.status, s);
    assert.equal(await r2.text(), than);
  }
});

test("máy nhà trả 401/403 (khoá/chữ ký lệch) → 502, KHÔNG chuyển 401 cho trình duyệt", async () => {
  for (const s of [401, 403]) {
    mayTraLoi = async () => Response.json({ loi: "sai chữ ký" }, { status: s });
    for (const [p, method] of [[`/api/hoc/bai-hoc/${MA}/hoan-tac`, "POST"], [`/api/hoc/bai-hoc/${MA}/bat-lai`, "POST"], ["/api/hoc/bao-cao", "GET"]]) {
      const r = await goi(p, { method });
      assert.equal(r.status, 502, `${s} ${p}`);
      assert.ok((await docJson(r)).loi);
    }
  }
});

test("lỗi tạm: mạng lỗi → 502, hết giờ → 504, edge HTML 5xx → 502 JSON, 524 → 504; không thử lại", async () => {
  const ca = [
    [async () => { throw new TypeError("fetch failed"); }, 502],
    [async () => { throw Object.assign(new Error("t"), { name: "TimeoutError" }); }, 504],
    [async () => new Response("<html>Bad gateway</html>", { status: 502, headers: { "content-type": "text/html" } }), 502],
    [async () => new Response("<html>timeout</html>", { status: 524, headers: { "content-type": "text/html" } }), 504],
    [async () => new Response("<html>origin down</html>", { status: 530 }), 502],
  ];
  for (const [i, [f, s]] of ca.entries()) {
    mayGoi = [];
    mayTraLoi = f;
    const r = await goi(`/api/hoc/bai-hoc/${MA}/hoan-tac`, { method: "POST" });
    assert.equal(r.status, s, `ca ${i}`);
    assert.match(r.headers.get("content-type"), /^application\/json/, `ca ${i}`);
    assert.ok((await docJson(r)).loi, `ca ${i}`);
    assert.equal(mayGoi.length, 1, `ca ${i}: không thử lại`);
  }
});

// ---------- method, cấu hình, body ----------
test("sai method → 405, không gọi máy nhà", async () => {
  assert.equal((await goi(`/api/hoc/bai-hoc/${MA}/hoan-tac`)).status, 405);
  assert.equal((await goi("/api/hoc/bao-cao", { method: "POST" })).status, 405);
  assert.equal((await goi("/api/hoc/bai-hoc", { method: "DELETE" })).status, 405);
  assert.equal((await goi(`/api/hoc/bai-hoc/${MA}/bat-lai`, { method: "PUT" })).status, 405);
  assert.equal(mayGoi.length, 0);
});

test("path /api/hoc lạ → 404 (không rơi xuống route khác)", async () => {
  for (const p of ["/api/hoc/xoa", "/api/hoc", "/api/hoc/bai-hoc/../bao-cao-x"]) {
    const r = await goi(p);
    assert.equal(r.status, 404, p);
  }
  assert.equal(mayGoi.length, 0);
});

test("thiếu VIDEO_ORIGIN/VIDEO_KEY/RUNNER_KEY/KY_RIENG → 503, không gọi máy nhà", async () => {
  const goc = { ...env };
  for (const k of ["VIDEO_ORIGIN", "VIDEO_KEY", "RUNNER_KEY", "KY_RIENG"]) {
    env = { ...goc };
    delete env[k];
    assert.equal((await goi("/api/hoc/bao-cao")).status, 503, k);
    assert.equal((await goi(`/api/hoc/bai-hoc/${MA}/hoan-tac`, { method: "POST" })).status, 503, k);
  }
  assert.equal(mayGoi.length, 0);
});

test("KY_RIENG hỏng → 503, không gửi request chưa ký", async () => {
  env.KY_RIENG = "không-phải-khoá";
  const r = await goi(`/api/hoc/bai-hoc/${MA}/bat-lai`, { method: "POST" });
  assert.equal(r.status, 503);
  assert.equal(mayGoi.length, 0);
});

test("body POST quá 16 KB (content-length) → 413, không gọi máy nhà", async () => {
  const lon = JSON.stringify({ x: "a".repeat(17 * 1024) });
  const r = await goi(`/api/hoc/bai-hoc/${MA}/hoan-tac`, { method: "POST", body: lon });
  assert.equal(r.status, 413, "độ dài thật (không có content-length, như chunked)");
  // header content-length khai lớn (Workers thật luôn có header này) → 413 ngay, không đọc body
  const url = new URL(`${GOC}/api/hoc/bai-hoc/${MA}/bat-lai`);
  const req = new Request(url, { method: "POST", headers: { origin: GOC, "content-length": String(17 * 1024) }, body: "{}" });
  const deps = { goiMayNha: W.goiMayNha, traVeMayNha: W.traVeMayNha, loi: (m, s = 400) => Response.json({ loi: m }, { status: s }), json: Response.json, laChuKho: () => true };
  assert.equal((await H.apiHoc(req, env, url, { user: "nhan" }, deps)).status, 413);
  assert.equal(mayGoi.length, 0);
  // đúng 16 KB vẫn qua, và body đó vẫn bị bỏ (Worker tự dựng boi)
  const vua = JSON.stringify({ boi: "x", d: "a".repeat(16 * 1024 - 18) });
  assert.equal(Buffer.byteLength(vua), 16 * 1024);
  const r2 = await goi(`/api/hoc/bai-hoc/${MA}/hoan-tac`, { method: "POST", body: vua });
  assert.equal(r2.status, 200);
  assert.equal(mayGoi[0].body, '{"boi":"nhan"}');
});

test("worker.js export goiMayNha, traVeMayNha (cho HT-T1 dùng hàm thật)", () => {
  assert.equal(typeof W.goiMayNha, "function");
  assert.equal(typeof W.traVeMayNha, "function");
});
