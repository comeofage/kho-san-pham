// Test Worker với GitHub giả trong bộ nhớ — chạy: node --test cf/test/
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import worker, { bamMatKhau, kiemMatKhau, taoPhien, tachUid } from "../src/worker.js";

const UID = "1729706628656957720";
let files, env, puts;

// GitHub giả: chỉ đủ /contents (GET json|raw, PUT có sha) và /git/trees.
globalThis.fetch = async (url, opt = {}) => {
  const u = new URL(url);
  const m = u.pathname.match(/^\/repos\/o\/r\/contents\/(.+)$/);
  const raw = (opt.headers || {}).Accept === "application/vnd.github.raw+json";
  if (m) {
    const path = decodeURIComponent(m[1]);
    if ((opt.method || "GET") === "PUT") {
      const b = JSON.parse(opt.body);
      const cu = files[path];
      if (cu && b.sha !== cu.sha) return new Response("{}", { status: 409 });
      if (!cu && b.sha) return new Response("{}", { status: 409 });
      if (cu && !b.sha) return new Response("{}", { status: 422 });
      const text = new TextDecoder().decode(Uint8Array.from(atob(b.content), (c) => c.charCodeAt(0)));
      files[path] = { text, sha: "s" + Math.random() };
      puts.push({ path, message: b.message });
      return new Response("{}", { status: 200 });
    }
    const f = files[path];
    if (!f) return new Response("{}", { status: 404 });
    if (raw) return new Response(f.text);
    const bytes = new TextEncoder().encode(f.text);
    return Response.json({ sha: f.sha, content: btoa(String.fromCharCode(...bytes)) });
  }
  if (u.pathname === "/repos/o/r/git/trees/main") return Response.json({ tree: Object.keys(files).map((path) => ({ path })) });
  throw new Error("fetch lạ: " + url);
};
globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };

const ctx = { waitUntil() {} };
const call = (path, { body, cookie, method, origin } = {}) =>
  worker.fetch(new Request(`https://kho.test${path}`, {
    method: method || (body ? "POST" : "GET"),
    headers: { ...(cookie ? { cookie } : {}), ...(origin ? { origin } : {}), "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  }), env, ctx);

async function dangNhap(user = "lan", pass = "matkhau-lan") {
  const r = await call("/api/login", { body: { user, pass } });
  return { r, cookie: (r.headers.get("set-cookie") || "").split(";")[0] };
}

beforeEach(async () => {
  puts = [];
  files = {
    "data/index.json": { text: JSON.stringify({ san_pham: [{ id: UID, uid: UID, link: `https://shop.tiktok.com/vn/pdp/${UID}`, ten: "Gel", trang_thai: "da_phan_tich" }] }), sha: "i1" },
    [`data/${UID}/info.json`]: { text: JSON.stringify({ id: UID, uid: UID, ten: "Gel", da_phan_tich: true, ghi_chu: "", da_quay: { xong: true, boi: "Cũ", luc: "x" } }), sha: "a1" },
    [`data/${UID}/bo-canh-quay.md`]: { text: "# Bộ cảnh", sha: "m1" },
  };
  env = {
    GH_REPO: "o/r", GH_BRANCH: "main", GITHUB_TOKEN: "t", SESSION_SECRET: "bi-mat-test",
    USERS: JSON.stringify({ lan: { ten: "Lan", hash: await bamMatKhau("matkhau-lan", undefined, 1000) } }),
    ASSETS: { fetch: async () => new Response("static") },
  };
});

test("băm và kiểm mật khẩu", async () => {
  const h = await bamMatKhau("abc", undefined, 1000);
  assert.ok(await kiemMatKhau("abc", h));
  assert.ok(!(await kiemMatKhau("abd", h)));
  assert.ok(!(await kiemMatKhau("abc", "rác")));
});

test("tách UID", () => {
  assert.equal(tachUid(`https://shop.tiktok.com/vn/pdp/${UID}?x=1`), UID);
  assert.equal(tachUid("https://vt.tiktok.com/ZS9AR1U4aqHLh/"), null);
});

test("chưa đăng nhập thì mọi API dữ liệu trả 401", async () => {
  for (const p of ["/api/ds", `/api/sp/${UID}`, "/api/me", `/api/anh/${UID}/bia.jpg`]) assert.equal((await call(p)).status, 401, p);
  assert.equal((await call("/api/them", { body: { link: UID } })).status, 401);
});

test("sai mật khẩu / user lạ bị từ chối, không cấp cookie", async () => {
  for (const [u, p] of [["lan", "sai"], ["ai", "matkhau-lan"]]) {
    const { r } = await dangNhap(u, p);
    assert.equal(r.status, 401);
    assert.equal(r.headers.get("set-cookie"), null);
  }
});

test("đăng nhập đúng → cookie HttpOnly, /api/me trả tên hiển thị", async () => {
  const { r, cookie } = await dangNhap("LAN ", "matkhau-lan");
  assert.equal(r.status, 200);
  assert.match(r.headers.get("set-cookie"), /HttpOnly; Secure; SameSite=Lax/);
  assert.deepEqual(await (await call("/api/me", { cookie })).json(), { user: "lan", ten: "Lan" });
});

test("cookie bị sửa, hết hạn, hoặc user đã bị xoá → 401", async () => {
  const { cookie } = await dangNhap();
  assert.equal((await call("/api/me", { cookie: cookie.slice(0, -2) + "xx" })).status, 401);
  const cu = await taoPhien(env, "lan", Date.now() - 31 * 24 * 3600e3);
  assert.equal((await call("/api/me", { cookie: `kho_s=${cu}` })).status, 401);
  env.USERS = "{}";
  assert.equal((await call("/api/me", { cookie })).status, 401);
});

test("danh sách gộp sản phẩm mới chưa vào index", async () => {
  const { cookie } = await dangNhap();
  files["data/1730000000000000001/info.json"] = { text: JSON.stringify({ id: "1730000000000000001", uid: "1730000000000000001", tom_tat: "dài" }), sha: "n" };
  const ds = (await (await call("/api/ds", { cookie })).json()).san_pham;
  assert.deepEqual(ds.map((x) => x.id), ["1730000000000000001", UID]);
  assert.equal(ds[0].trang_thai, "cho");
  assert.equal(ds[0].tom_tat, undefined);
});

test("chi tiết sản phẩm + chặn ID lạ (path traversal)", async () => {
  const { cookie } = await dangNhap();
  const d = await (await call(`/api/sp/${UID}`, { cookie })).json();
  assert.equal(d.info.ten, "Gel");
  assert.equal(d.md, "# Bộ cảnh");
  assert.equal(d.caps, null);
  assert.equal((await call(`/api/sp/..%2F..%2Fx`, { cookie })).status, 400);
  assert.equal((await call(`/api/anh/${UID}/..%2Finfo.json`, { cookie })).status, 400);
});

test("thêm link: tên người thêm lấy từ phiên, trùng thì 409", async () => {
  const { cookie } = await dangNhap();
  const r = await call("/api/them", { cookie, body: { link: "https://shop.tiktok.com/vn/pdp/1731111111111111111?a=b" } });
  assert.equal(r.status, 200);
  const info = JSON.parse(files["data/1731111111111111111/info.json"].text);
  assert.equal(info.them_boi, "Lan");
  assert.match(puts[0].message, /— Lan$/);
  const t = await call("/api/them", { cookie, body: { link: UID } });
  assert.equal(t.status, 409);
  assert.equal((await t.json()).id, UID);
});

test("gạt đã quay: ghi người + chuyển dữ liệu cũ da_quay sang review", async () => {
  const { cookie } = await dangNhap();
  const r = await call("/api/quay", { cookie, body: { id: UID, loai: "oneshot", xong: true } });
  assert.equal(r.status, 200);
  const info = JSON.parse(files[`data/${UID}/info.json`].text);
  assert.equal(info.da_quay_oneshot.boi, "Lan");
  assert.equal(info.da_quay_review.boi, "Cũ");
  assert.equal(info.da_quay, undefined);
  assert.equal((await r.json()).info.trang_thai, "da_quay");
  assert.equal((await call("/api/quay", { cookie, body: { id: UID, loai: "xoa", xong: true } })).status, 400);
});

test("ghi chú lưu được; POST từ origin khác bị chặn", async () => {
  const { cookie } = await dangNhap();
  assert.equal((await call("/api/ghichu", { cookie, body: { id: UID, ghi_chu: "mai quay" } })).status, 200);
  assert.equal(JSON.parse(files[`data/${UID}/info.json`].text).ghi_chu, "mai quay");
  assert.equal((await call("/api/ghichu", { cookie, origin: "https://evil.test", body: { id: UID, ghi_chu: "x" } })).status, 403);
});

test("trang tĩnh đi qua ASSETS", async () => {
  assert.equal(await (await call("/")).text(), "static");
});
