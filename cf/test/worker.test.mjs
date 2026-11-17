// Test Worker với GitHub giả trong bộ nhớ — chạy: node --test cf/test/
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import worker, { bamMatKhau, kiemMatKhau, taoPhien, tachUid, chuoiKyRequest, kiemThamSoViec, kyRequest, chuoiKyDuyet, datLaiDemSaiMatKhau, chuoiTieuDuyet, datLaiSoTieuBoNho } from "../src/worker.js";

const UID = "1729706628656957720";
// Cặp khoá Ed25519 chỉ dùng cho test (Web Crypto của Node 24): KY_RIENG = PKCS8 DER base64 như tao_khoa_ky.py in ra.
const CAP_KHOA = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const KY_RIENG_TEST = Buffer.from(await crypto.subtle.exportKey("pkcs8", CAP_KHOA.privateKey)).toString("base64");
let files, env, puts, mayGoi, mayTraLoi;

// GitHub giả: chỉ đủ /contents (GET json|raw, PUT có sha) và /git/trees.
// Máy nhà giả (https://may.test): ghi lại URL + header, trả lời theo mayTraLoi.
globalThis.fetch = async (url, opt = {}) => {
  const u = new URL(url);
  if (u.origin === "https://may.test") {
    mayGoi.push({ url: u, method: opt.method || "GET", headers: opt.headers || {}, signal: opt.signal, body: opt.body });
    return mayTraLoi(u, opt);
  }
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
const CACHE_RONG = { match: async () => undefined, put: async () => {} };
globalThis.caches = { default: CACHE_RONG };

const ctx = { waitUntil() {} };
const call = (path, { body, cookie, method, origin, headers = {} } = {}) =>
  worker.fetch(new Request(`https://kho.test${path}`, {
    method: method || (body ? "POST" : "GET"),
    headers: { ...(cookie ? { cookie } : {}), ...(origin ? { origin } : {}), "content-type": "application/json", ...headers },
    body: body ? JSON.stringify(body) : undefined,
  }), env, ctx);

async function dangNhap(user = "lan", pass = "matkhau-lan") {
  const r = await call("/api/login", { body: { user, pass } });
  return { r, cookie: (r.headers.get("set-cookie") || "").split(";")[0] };
}

beforeEach(async () => {
  datLaiDemSaiMatKhau();
  datLaiSoTieuBoNho();
  globalThis.caches.default = CACHE_RONG;
  puts = [];
  mayGoi = [];
  mayTraLoi = async () => new Response("ok", { headers: { "content-type": "video/mp4" } });
  files = {
    "data/index.json": { text: JSON.stringify({ san_pham: [{ id: UID, uid: UID, link: `https://shop.tiktok.com/vn/pdp/${UID}`, ten: "Gel", trang_thai: "da_phan_tich" }] }), sha: "i1" },
    [`data/${UID}/info.json`]: { text: JSON.stringify({ id: UID, uid: UID, ten: "Gel", da_phan_tich: true, ghi_chu: "", da_quay: { xong: true, boi: "Cũ", luc: "x" } }), sha: "a1" },
    [`data/${UID}/bo-canh-quay.md`]: { text: "# Bộ cảnh", sha: "m1" },
  };
  env = {
    GH_REPO: "o/r", GH_BRANCH: "main", GITHUB_TOKEN: "t", SESSION_SECRET: "bi-mat-test",
    USERS: JSON.stringify({
      lan: { ten: "Lan", hash: await bamMatKhau("matkhau-lan", undefined, 1000) },
      nhan: { ten: "Nhân", hash: await bamMatKhau("matkhau-nhan", undefined, 1000) },
      comeofage: { ten: "Come", hash: await bamMatKhau("matkhau-come", undefined, 1000) },
    }),
    ASSETS: { fetch: async () => new Response("static") },
    VIDEO_ORIGIN: "https://may.test", VIDEO_KEY: "k",
    RUNNER_KEY: "rk", KY_RIENG: KY_RIENG_TEST,
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

// ---------- proxy video: allowlist query + chặn xoá liên trang ----------
const dangNhapNhan = () => dangNhap("nhan", "matkhau-nhan");
const goiCuoi = () => mayGoi[mayGoi.length - 1];

test("video file: same-origin giữ xoa=1, bỏ khoá lạ, gửi x-key", async () => {
  const { cookie } = await dangNhapNhan();
  const r = await call(`/api/video/${UID}/file?ten=a&goc=b&xoa=1&la=x`, { cookie, headers: { "sec-fetch-site": "same-origin" } });
  assert.equal(r.status, 200);
  const u = goiCuoi().url;
  assert.equal(u.pathname, `/v/${UID}/file`);
  assert.equal(u.searchParams.get("xoa"), "1");
  assert.equal(u.searchParams.get("ten"), "a");
  assert.equal(u.searchParams.get("goc"), "b");
  assert.equal(u.searchParams.has("la"), false);
  assert.equal(goiCuoi().headers["x-key"], "k");
});

test("video file: cross-site / thiếu sec-fetch-site / xoa khác 1 → không chuyển xoa", async () => {
  const { cookie } = await dangNhapNhan();
  for (const headers of [{ "sec-fetch-site": "cross-site" }, { "sec-fetch-site": "same-site" }, { "sec-fetch-site": "none" }, {}]) {
    const r = await call(`/api/video/${UID}/file?ten=a&goc=b&xoa=1&la=x`, { cookie, headers });
    assert.equal(r.status, 200);
    const u = goiCuoi().url;
    assert.equal(u.searchParams.has("xoa"), false, JSON.stringify(headers));
    assert.equal(u.searchParams.get("ten"), "a");
    assert.equal(u.searchParams.has("la"), false);
  }
  await call(`/api/video/${UID}/file?ten=a&xoa=true`, { cookie, headers: { "sec-fetch-site": "same-origin" } });
  assert.equal(goiCuoi().url.searchParams.has("xoa"), false);
});

test("video xem/ds/tien-do/dy/dyfile: chỉ khoá được phép", async () => {
  const { cookie } = await dangNhapNhan();
  const so = { cookie, headers: { "sec-fetch-site": "same-origin" } };
  await call(`/api/video/${UID}/xem?ten=a&goc=g&xoa=1&z=2`, so);
  assert.equal(goiCuoi().url.pathname, `/v/${UID}/xem`);
  assert.equal(goiCuoi().url.search, "?ten=a&goc=g");
  for (const act of ["ds", "dy", "tien-do"]) {
    await call(`/api/video/${UID}/${act}?x=1&xoa=1`, so);
    assert.equal(goiCuoi().url.pathname, `/v/${UID}/${act}`);
    assert.equal(goiCuoi().url.search, "", act);
  }
  await call(`/api/video/${UID}/dyfile?ten=c.mp4&goc=g&xoa=1`, so);
  assert.equal(goiCuoi().url.search, "?ten=c.mp4");
});

test("video xoa: chỉ POST, chuyển ten+goc; GET xoa / POST file → 405", async () => {
  const { cookie } = await dangNhapNhan();
  const r = await call(`/api/video/${UID}/xoa?ten=a&goc=b&xoa=1&q=1`, { cookie, method: "POST" });
  assert.equal(r.status, 200);
  assert.equal(goiCuoi().method, "POST");
  assert.equal(goiCuoi().url.search, "?ten=a&goc=b");
  const truoc = mayGoi.length;
  assert.equal((await call(`/api/video/${UID}/xoa?ten=a`, { cookie })).status, 405);
  assert.equal((await call(`/api/video/${UID}/file?ten=a`, { cookie, method: "POST" })).status, 405);
  assert.equal(mayGoi.length, truoc);
});

test("user không phải nhan/comeofage → 403 cho video, suc-khoe, duyet", async () => {
  const { cookie } = await dangNhap();
  for (const p of [`/api/video/${UID}/file?ten=a&xoa=1`, `/api/video/${UID}/xem?ten=a`, "/api/suc-khoe"]) {
    const r = await call(p, { cookie, headers: { "sec-fetch-site": "same-origin" } });
    assert.equal(r.status, 403, p);
    assert.deepEqual(await r.json(), { loi: "Không có quyền" });
  }
  const r = await call("/api/duyet", { cookie, body: { id: UID, goc: "g", ten: "a.mp4", sua_luc: 1, ket_qua: "dat" } });
  assert.equal(r.status, 403);
  assert.equal(mayGoi.length, 0);
  assert.equal(puts.length, 0);
  assert.equal((await call("/api/suc-khoe")).status, 401);
});

// ---------- sức khoẻ máy nhà ----------
test("suc-khoe: máy nhà OK → JSON gốc + may_nha true", async () => {
  const { cookie } = await dangNhapNhan();
  mayTraLoi = async () => Response.json({ apps: [{ ten: "video_server", chay: true }], ok: true });
  const r = await call("/api/suc-khoe", { cookie });
  assert.equal(r.status, 200);
  const d = await r.json();
  assert.equal(d.may_nha, true);
  assert.deepEqual(d.apps, [{ ten: "video_server", chay: true }]);
  assert.equal(goiCuoi().url.href, "https://may.test/suc-khoe");
  assert.equal(goiCuoi().headers["x-key"], "k");
});

test("suc-khoe: máy nhà lỗi / không ok → 200 may_nha false; thiếu cấu hình → 503", async () => {
  const { cookie } = await dangNhapNhan();
  const mong = (loi) => ({ may_nha: false, loi, apps: [] });
  const ghiLoi = [];
  const goc = console.error;
  console.error = (...a) => ghiLoi.push(a.join(" "));
  try {
    mayTraLoi = async () => { throw new Error("tunnel tắt"); };
    let r = await call("/api/suc-khoe", { cookie });
    assert.equal(r.status, 200);
    assert.deepEqual(await r.json(), mong("Máy nhà không trả lời (đã bật video_server và tunnel chưa?)"));
    mayTraLoi = async () => new Response("bad gateway", { status: 502 });
    r = await call("/api/suc-khoe", { cookie });
    assert.equal(r.status, 200);
    assert.deepEqual(await r.json(), mong("Máy nhà trả mã 502 (đã bật video_server và tunnel chưa?)"));
    mayTraLoi = async () => new Response("nope", { status: 404 });
    assert.deepEqual(await (await call("/api/suc-khoe", { cookie })).json(), mong("Máy nhà trả mã 404"));
    for (const st of [401, 403]) {
      mayTraLoi = async () => Response.json({ loi: "Sai khoá" }, { status: st });
      r = await call("/api/suc-khoe", { cookie });
      assert.equal(r.status, 200);
      assert.deepEqual(await r.json(), mong("Máy nhà từ chối khoá (VIDEO_KEY lệch với tools/.video_key)"), String(st));
    }
    mayTraLoi = async () => { throw new DOMException("hết giờ", "TimeoutError"); };
    assert.deepEqual(await (await call("/api/suc-khoe", { cookie })).json(), mong("Hết thời gian chờ máy nhà"));
    mayTraLoi = async () => Response.json([1, 2]);
    assert.deepEqual(await (await call("/api/suc-khoe", { cookie })).json(), mong("Máy nhà trả dữ liệu lạ"));
  } finally {
    console.error = goc;
  }
  assert.equal(ghiLoi.length, 7);
  assert.ok(ghiLoi.every((s) => s.includes("suc-khoe")), ghiLoi.join("\n"));
  delete env.VIDEO_KEY;
  assert.equal((await call("/api/suc-khoe", { cookie })).status, 503);
});

// ---------- proxy video: khoá lệch + timeout ----------
test("video: máy nhà 401/403 → 502 (không đẩy ra màn đăng nhập) + console.error", async () => {
  const { cookie } = await dangNhapNhan();
  const ghiLoi = [];
  const goc = console.error;
  console.error = (...a) => ghiLoi.push(a.join(" "));
  try {
    for (const st of [401, 403]) {
      mayTraLoi = async () => Response.json({ loi: "Sai khoá" }, { status: st });
      for (const act of ["ds", "file?ten=a"]) {
        const r = await call(`/api/video/${UID}/${act}`, { cookie });
        assert.equal(r.status, 502, `${st} ${act}`);
        assert.deepEqual(await r.json(), { loi: "Máy nhà từ chối khoá (VIDEO_KEY lệch với tools/.video_key)" });
      }
    }
  } finally {
    console.error = goc;
  }
  assert.equal(ghiLoi.length, 4);
  // mã khác vẫn chuyển nguyên
  mayTraLoi = async () => Response.json({ loi: "Không thấy video" }, { status: 404 });
  assert.equal((await call(`/api/video/${UID}/xem?ten=a`, { cookie })).status, 404);
});

test("video: ds/dy/tien-do có timeout, hết giờ → 504; file/xem/dyfile/xoa không đặt timeout", async () => {
  const { cookie } = await dangNhapNhan();
  for (const act of ["ds", "dy", "tien-do"]) {
    await call(`/api/video/${UID}/${act}`, { cookie });
    assert.ok(goiCuoi().signal instanceof AbortSignal, act);
  }
  for (const [act, method] of [["file?ten=a", "GET"], ["xem?ten=a", "GET"], ["dyfile?ten=a", "GET"], ["xoa?ten=a", "POST"]]) {
    await call(`/api/video/${UID}/${act}`, { cookie, method });
    assert.equal(goiCuoi().signal, undefined, act);
  }
  const goc = console.error;
  console.error = () => {};
  try {
    for (const ten of ["TimeoutError", "AbortError"]) {
      mayTraLoi = async () => { throw new DOMException("hết giờ", ten); };
      const r = await call(`/api/video/${UID}/ds`, { cookie });
      assert.equal(r.status, 504, ten);
      assert.deepEqual(await r.json(), { loi: "Máy nhà phản hồi quá chậm" });
    }
    // lỗi mạng khác vẫn 502 như cũ
    mayTraLoi = async () => { throw new Error("tunnel tắt"); };
    assert.equal((await call(`/api/video/${UID}/ds`, { cookie })).status, 502);
  } finally {
    console.error = goc;
  }
});

// ---------- duyệt video ----------
const PATH_DUYET = `data/${UID}/duyet.json`;
const docDuyet = () => JSON.parse(files[PATH_DUYET].text).videos;

test("duyet: thêm, cập nhật cùng khoá không nhân đôi, xoá bằng ket_qua+gop_y rỗng", async () => {
  const { cookie } = await dangNhapNhan();
  let r = await call("/api/duyet", { cookie, body: { id: UID, goc: "output_poster", ten: "a.mp4", sua_luc: 100, mb: 3.2, ket_qua: "dat", gop_y: "đẹp" } });
  assert.equal(r.status, 200);
  let d = (await r.json()).duyet;
  assert.equal(d.length, 1);
  assert.deepEqual({ ...d[0], luc: undefined }, { goc: "output_poster", ten: "a.mp4", sua_luc: 100, mb: 3.2, ket_qua: "dat", gop_y: "đẹp", boi: "Nhân", luc: undefined });
  assert.match(d[0].luc, /\+07:00$/);
  assert.equal(puts[0].path, PATH_DUYET);
  assert.equal(puts[0].message, `Duyệt video a.mp4 ${UID} — Nhân`);

  // khác sua_luc → mục riêng; mb/gop_y thiếu → 0/""
  r = await call("/api/duyet", { cookie, body: { id: UID, goc: "output_poster", ten: "a.mp4", sua_luc: 200, ket_qua: "loai" } });
  d = (await r.json()).duyet;
  assert.equal(d.length, 2);
  assert.equal(d[1].mb, 0);
  assert.equal(d[1].gop_y, "");

  // cùng khoá → cập nhật
  r = await call("/api/duyet", { cookie, body: { id: UID, goc: "output_poster", ten: "a.mp4", sua_luc: 100, mb: 3.2, ket_qua: "loai", gop_y: "mờ" } });
  d = (await r.json()).duyet;
  assert.equal(d.length, 2);
  assert.equal(d.find((x) => x.sua_luc === 100).ket_qua, "loai");
  assert.equal(docDuyet().length, 2);

  // chỉ góp ý, chưa chấm → vẫn giữ
  r = await call("/api/duyet", { cookie, body: { id: UID, goc: "output_poster", ten: "a.mp4", sua_luc: 100, ket_qua: "", gop_y: "xem lại" } });
  assert.equal((await r.json()).duyet.length, 2);

  // xoá
  r = await call("/api/duyet", { cookie, body: { id: UID, goc: "output_poster", ten: "a.mp4", sua_luc: 100, ket_qua: "", gop_y: "" } });
  d = (await r.json()).duyet;
  assert.deepEqual(d.map((x) => x.sua_luc), [200]);
  assert.deepEqual(docDuyet().map((x) => x.sua_luc), [200]);
});

test("duyet: validate → 400, SP không tồn tại → 404", async () => {
  const { cookie } = await dangNhapNhan();
  const tot = { id: UID, goc: "g", ten: "a.mp4", sua_luc: 1, mb: 1, ket_qua: "dat", gop_y: "" };
  for (const sai of [
    { ten: "x/a.mp4" }, { ten: "x\\a.mp4" }, { ten: "" }, { ten: "a".repeat(201) }, { ten: 5 },
    { ket_qua: "tot" }, { ket_qua: undefined },
    { sua_luc: -1 }, { sua_luc: 1.5 }, { sua_luc: "1" },
    { mb: -1 }, { mb: "3" },
    { goc: "" }, { goc: "g".repeat(301) },
    { gop_y: "x".repeat(2001) }, { gop_y: 3 },
    { id: "../x" },
  ]) {
    const r = await call("/api/duyet", { cookie, body: { ...tot, ...sai } });
    assert.equal(r.status, 400, JSON.stringify(sai));
  }
  assert.equal(puts.length, 0);
  const r = await call("/api/duyet", { cookie, body: { ...tot, id: "1730000000000000009" } });
  assert.equal(r.status, 404);
  assert.equal(puts.length, 0);
  // POST từ origin khác vẫn bị chặn
  assert.equal((await call("/api/duyet", { cookie, origin: "https://evil.test", body: tot })).status, 403);
});

test("/api/sp trả duyet ([] khi chưa có file)", async () => {
  const { cookie } = await dangNhapNhan();
  let d = await (await call(`/api/sp/${UID}`, { cookie })).json();
  assert.deepEqual(d.duyet, []);
  assert.deepEqual(d.vtk, []);
  files[PATH_DUYET] = { text: JSON.stringify({ videos: [{ goc: "g", ten: "a.mp4", sua_luc: 1, ket_qua: "dat" }] }), sha: "d1" };
  d = await (await call(`/api/sp/${UID}`, { cookie })).json();
  assert.deepEqual(d.duyet, [{ goc: "g", ten: "a.mp4", sua_luc: 1, ket_qua: "dat" }]);
});

test("/api/sp: user không phải nhan/comeofage nhận duyet rỗng (không lộ đường dẫn máy nhà)", async () => {
  files[PATH_DUYET] = { text: JSON.stringify({ videos: [{ goc: "E:/oneshottramcanh", ten: "a.mp4", sua_luc: 1, ket_qua: "dat" }] }), sha: "d1" };
  const { cookie } = await dangNhap();
  const r = await call(`/api/sp/${UID}`, { cookie });
  assert.equal(r.status, 200);
  const t = await r.text();
  assert.deepEqual(JSON.parse(t).duyet, []);
  assert.equal(t.includes("oneshottramcanh"), false);
  assert.equal(JSON.parse(t).info.ten, "Gel");
});

// ---------- bộ chạy việc: /api/viec* (W-1, §3.3, §8.2, §8.3) ----------
const JOB = "j20261117150000ab12";
const ORIGIN = "https://kho.test";
const hex = (buf) => [...new Uint8Array(buf)].map((x) => x.toString(16).padStart(2, "0")).join("");
const sha256Hex = async (s) => hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)));
const tuB64url = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
async function kiemChuKy(goi) {
  const h = goi.headers;
  const chuoi = chuoiKyRequest(goi.method, goi.url.pathname.replace(/^\/r/, ""), Number(h["x-ky-ngay"]), h["x-ky-nonce"], await sha256Hex(goi.body || ""));
  return crypto.subtle.verify({ name: "Ed25519" }, CAP_KHOA.publicKey, tuB64url(h["x-ky"]), chuoi);
}
const postViec = (cookie, path, body, extra = {}) => call(path, { cookie, body, origin: ORIGIN, ...extra });

test("viec: chuoiKyRequest đúng định dạng §8.3 từng byte", () => {
  const b = chuoiKyRequest("POST", "/viec/j20261117150000ab12/tra-loi", 1763366400123, "0123456789abcdef0123456789abcdef", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  assert.ok(b instanceof Uint8Array);
  assert.equal(new TextDecoder().decode(b),
    "kho-runner-v1\nPOST\n/viec/j20261117150000ab12/tra-loi\n1763366400123\n0123456789abcdef0123456789abcdef\ne3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
});

test("viec: kyRequest sinh header x-ky* kiểm được bằng khoá công khai; nonce không lặp", async () => {
  const body = JSON.stringify({ loai: "phan_tich_uid", tham_so: { uid: UID }, boi: "nhan", ghi: "tiếng Việt" });
  const h1 = await kyRequest(env, "POST", "/viec", body);
  const h2 = await kyRequest(env, "POST", "/viec", body);
  assert.match(h1["x-ky-nonce"], /^[0-9a-f]{32}$/);
  assert.notEqual(h1["x-ky-nonce"], h2["x-ky-nonce"]);
  assert.ok(Math.abs(Number(h1["x-ky-ngay"]) - Date.now()) < 5000);
  assert.match(h1["x-ky"], /^[A-Za-z0-9_-]+$/);
  const chuoi = chuoiKyRequest("POST", "/viec", Number(h1["x-ky-ngay"]), h1["x-ky-nonce"], await sha256Hex(body));
  assert.ok(await crypto.subtle.verify({ name: "Ed25519" }, CAP_KHOA.publicKey, tuB64url(h1["x-ky"]), chuoi));
  // đổi path → chữ ký không còn đúng
  const sai = chuoiKyRequest("POST", "/viec/x", Number(h1["x-ky-ngay"]), h1["x-ky-nonce"], await sha256Hex(body));
  assert.ok(!(await crypto.subtle.verify({ name: "Ed25519" }, CAP_KHOA.publicKey, tuB64url(h1["x-ky"]), sai)));
});

test("viec: KY_RIENG nhận cả JWK và PKCS8 base64url", async () => {
  const jwk = JSON.stringify(await crypto.subtle.exportKey("jwk", CAP_KHOA.privateKey));
  const b64u = KY_RIENG_TEST.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  for (const nguon of [jwk, b64u]) {
    const h = await kyRequest({ KY_RIENG: nguon }, "POST", "/viec/j20261117150000ab12/huy", "{}");
    const chuoi = chuoiKyRequest("POST", "/viec/j20261117150000ab12/huy", Number(h["x-ky-ngay"]), h["x-ky-nonce"], await sha256Hex("{}"));
    assert.ok(await crypto.subtle.verify({ name: "Ed25519" }, CAP_KHOA.publicKey, tuB64url(h["x-ky"]), chuoi), nguon.slice(0, 5));
  }
});

test("viec: chưa đăng nhập 401; user không phải nhan/comeofage 403; không gọi máy nhà", async () => {
  assert.equal((await call("/api/viec")).status, 401);
  const { cookie } = await dangNhap();
  for (const [p, body] of [["/api/viec"], ["/api/viec/danh-muc"], [`/api/viec/${JOB}`], ["/api/viec", { loai: "xu_ly_link_moi", tham_so: {} }], [`/api/viec/${JOB}/huy`, {}]]) {
    const r = body ? await postViec(cookie, p, body) : await call(p, { cookie });
    assert.equal(r.status, 403, p);
    assert.deepEqual(await r.json(), { loi: "Không có quyền" });
  }
  assert.equal(mayGoi.length, 0);
});

test("viec: thiếu RUNNER_KEY / KY_RIENG / VIDEO_ORIGIN / VIDEO_KEY → 503, không gọi máy nhà", async () => {
  const { cookie } = await dangNhapNhan();
  for (const k of ["RUNNER_KEY", "KY_RIENG", "VIDEO_ORIGIN", "VIDEO_KEY"]) {
    const giu = env[k];
    delete env[k];
    assert.equal((await call("/api/viec/suc-khoe", { cookie })).status, 503, k);
    assert.equal((await postViec(cookie, "/api/viec", { loai: "xu_ly_link_moi" })).status, 503, k);
    env[k] = giu;
  }
  assert.equal(mayGoi.length, 0);
});

test("viec: POST thiếu Origin hoặc Origin lạ → 403, không gọi máy nhà", async () => {
  const { cookie } = await dangNhapNhan();
  assert.equal((await call("/api/viec", { cookie, body: { loai: "xu_ly_link_moi" } })).status, 403);
  assert.equal((await call(`/api/viec/${JOB}/huy`, { cookie, body: {} })).status, 403);
  assert.equal((await postViec(cookie, "/api/viec", { loai: "xu_ly_link_moi" }, { origin: "https://evil.test" })).status, 403);
  assert.equal(mayGoi.length, 0);
});

test("viec: POST /api/viec dựng lại body, gắn boi từ phiên, đủ header, chữ ký đúng", async () => {
  const { cookie } = await dangNhapNhan();
  mayTraLoi = async () => Response.json({ viec: { id: JOB } }, { status: 201 });
  const r = await postViec(cookie, "/api/viec", { loai: "voice_pv", tham_so: { uid: UID, du_an: "0123456789ab", me: "20261117-a1" }, boi: "comeofage", la: 1 });
  assert.equal(r.status, 201);
  assert.deepEqual(await r.json(), { viec: { id: JOB } });
  const g = goiCuoi();
  assert.equal(g.url.href, "https://may.test/r/viec");
  assert.equal(g.method, "POST");
  assert.deepEqual(JSON.parse(g.body), { loai: "voice_pv", tham_so: { uid: UID, du_an: "0123456789ab", me: "20261117-a1" }, boi: "nhan" });
  assert.equal(g.headers["x-key"], "k");
  assert.equal(g.headers["x-runner-key"], "rk");
  assert.equal(g.headers["content-type"], "application/json");
  for (const k of ["x-ky", "x-ky-ngay", "x-ky-nonce"]) assert.ok(g.headers[k], k);
  assert.ok(await kiemChuKy(g));
  assert.ok(g.signal instanceof AbortSignal);
});

test("viec: kiemThamSoViec theo danh mục đợt 3 (§5.1)", () => {
  const D = "0123456789ab", ME = "20261117-a1";
  for (const [b, mong] of [
    [{ loai: "radar_ban_tin" }, { loai: "radar_ban_tin", tham_so: {} }],
    [{ loai: "radar_ban_tin", tham_so: { top_n: 5, chay_bu: true } }, { loai: "radar_ban_tin", tham_so: { top_n: 5, chay_bu: true } }],
    [{ loai: "radar_ban_tin", tham_so: { top_n: 30, chay_bu: false } }, { loai: "radar_ban_tin", tham_so: { top_n: 30, chay_bu: false } }],
    [{ loai: "phan_tich_uid", tham_so: { uid: UID } }, { loai: "phan_tich_uid", tham_so: { uid: UID } }],
    [{ loai: "douyin_uid", tham_so: { uid: UID } }, { loai: "douyin_uid", tham_so: { uid: UID } }],
    [{ loai: "xu_ly_link_moi", tham_so: {} }, { loai: "xu_ly_link_moi", tham_so: {} }],
    [{ loai: "poster_day_folder", tham_so: { uid: UID, du_an: D } }, { loai: "poster_day_folder", tham_so: { uid: UID, du_an: D } }],
    [{ loai: "voice_pv", tham_so: { uid: UID, du_an: D, me: ME } }, { loai: "voice_pv", tham_so: { uid: UID, du_an: D, me: ME } }],
  ]) assert.deepEqual(kiemThamSoViec(b), mong, JSON.stringify(b));
  for (const b of [
    null, [], "x", {}, { loai: "" }, { loai: "Radar_ban_tin" }, { loai: "rm -rf" }, { loai: "x".repeat(31) }, { loai: "__proto__" }, { loai: "constructor" },
    { loai: "muse_clip", tham_so: { uid: UID } }, { loai: "taovideo", tham_so: { uid: UID } }, { loai: "voice_genmax", tham_so: { uid: UID, du_an: D } },
    { loai: "radar_ban_tin", tham_so: [] }, { loai: "radar_ban_tin", tham_so: "x" }, { loai: "radar_ban_tin", tham_so: null },
    { loai: "radar_ban_tin", tham_so: { top_n: 4 } }, { loai: "radar_ban_tin", tham_so: { top_n: 31 } }, { loai: "radar_ban_tin", tham_so: { top_n: 10.5 } },
    { loai: "radar_ban_tin", tham_so: { top_n: "10" } }, { loai: "radar_ban_tin", tham_so: { chay_bu: "true" } }, { loai: "radar_ban_tin", tham_so: { chay_bu: 1 } },
    { loai: "radar_ban_tin", tham_so: { lenh: "x" } },
    { loai: "phan_tich_uid" }, { loai: "phan_tich_uid", tham_so: { uid: "123" } }, { loai: "phan_tich_uid", tham_so: { uid: Number(UID) } },
    { loai: "phan_tich_uid", tham_so: { uid: `${UID}\n` } }, { loai: "phan_tich_uid", tham_so: { uid: UID, them: "../x" } },
    { loai: "douyin_uid", tham_so: { uid: "tam-12345678901" } },
    { loai: "xu_ly_link_moi", tham_so: { uid: UID } },
    { loai: "poster_day_folder", tham_so: { uid: UID } }, { loai: "poster_day_folder", tham_so: { uid: UID, du_an: "0123456789AB" } },
    { loai: "poster_day_folder", tham_so: { uid: UID, du_an: "E:/x" } }, { loai: "poster_day_folder", tham_so: { uid: UID, du_an: { a: 1 } } },
    { loai: "voice_pv", tham_so: { uid: UID, du_an: D } }, { loai: "voice_pv", tham_so: { uid: UID, du_an: D, me: "2026-11-17" } },
    { loai: "voice_pv", tham_so: { uid: UID, du_an: D, me: "20261117-" } }, { loai: "voice_pv", tham_so: { uid: UID, du_an: D, me: "20261117-abcdefghijklm" } },
    { loai: "voice_pv", tham_so: { uid: UID, du_an: D, me: ["20261117-a"] } },
    { loai: "phan_tich_uid", tham_so: Object.fromEntries(Array.from({ length: 11 }, (_, i) => [`k${i}`, "a"])) },
  ]) assert.equal(typeof kiemThamSoViec(b), "string", JSON.stringify(b));
});

test("viec: POST /api/viec mẫu sai → 400, body hỏng → 400, quá lớn → 413, không gọi máy nhà", async () => {
  const { cookie } = await dangNhapNhan();
  for (const b of [{ loai: "muse_clip", tham_so: { uid: UID } }, { loai: "phan_tich_uid", tham_so: { uid: "1" } }, { loai: "xu_ly_link_moi", tham_so: { lenh: "x" } }]) {
    assert.equal((await postViec(cookie, "/api/viec", b)).status, 400, JSON.stringify(b));
  }
  const tho = (body) => worker.fetch(new Request(`${ORIGIN}/api/viec`, { method: "POST", headers: { cookie, origin: ORIGIN, "content-type": "application/json" }, body }), env, ctx);
  assert.equal((await tho("{không phải json")).status, 400);
  assert.equal((await tho(JSON.stringify({ loai: "xu_ly_link_moi", rac: "x".repeat(17000) }))).status, 413);
  assert.equal(mayGoi.length, 0);
});

test("viec: GET chuyển đúng path runner, lọc query; không ký GET", async () => {
  const { cookie } = await dangNhapNhan();
  mayTraLoi = async () => Response.json({ ok: 1 });
  for (const [vao, ra] of [
    [`/api/viec?trang_thai=cho,dang_chay&uid=${UID}&gioi_han=20&tom_tat=1&la=x&tu=5`, `/r/viec?trang_thai=cho%2Cdang_chay&uid=${UID}&gioi_han=20&tom_tat=1`],
    ["/api/viec/danh-muc?x=1", "/r/danh-muc"],
    ["/api/viec/suc-khoe", "/r/suc-khoe"],
    ["/api/viec/poster-folders", "/r/poster/folders"],
    ["/api/viec/poster/folders?x=1", "/r/poster/folders"],
    [`/api/viec/du-an/${UID}`, `/r/du-an/${UID}`],
    [`/api/viec/${JOB}?tu=1`, `/r/viec/${JOB}`],
    [`/api/viec/${JOB}/log?tu=4096&trang_thai=x`, `/r/viec/${JOB}/log?tu=4096`],
  ]) {
    const r = await call(vao, { cookie });
    assert.equal(r.status, 200, vao);
    const g = goiCuoi();
    assert.equal(g.url.pathname + g.url.search, ra, vao);
    assert.equal(g.method, "GET");
    assert.equal(g.headers["x-key"], "k");
    assert.equal(g.headers["x-runner-key"], "rk");
    assert.equal(g.headers["x-ky"], undefined);
    assert.ok(g.signal instanceof AbortSignal);
  }
});

test("viec: id/uid/query sai, route lạ, sai phương thức, duyet đợt 3 → không gọi máy nhà", async () => {
  const { cookie } = await dangNhapNhan();
  for (const [p, st] of [
    ["/api/viec/..%2F..%2Fsuc-khoe", 404], ["/api/viec/j123", 404], [`/api/viec/${JOB.toUpperCase()}`, 404],
    ["/api/viec/du-an/123", 404], ["/api/viec/du-an/..%2Fx", 404],
    ["/api/viec?trang_thai=cho%20x", 400], [`/api/viec?uid=${"1".repeat(41)}`, 400], [`/api/viec/${JOB}/log?tu=-1;x`, 400],
    [`/api/viec/${JOB}/xoa`, 404], ["/api/viec/poster/folders/1", 404], ["/api/viec/poster", 404],
    [`/api/viec/${JOB}/huy`, 405], [`/api/viec/${JOB}/tra-loi`, 405],
  ]) assert.equal((await call(p, { cookie })).status, st, p);
  assert.equal((await postViec(cookie, "/api/viec/danh-muc", {})).status, 405);
  assert.equal((await postViec(cookie, `/api/viec/${JOB}`, {})).status, 405);
  assert.equal((await postViec(cookie, `/api/viec/${JOB}/log`, {})).status, 405);
  assert.equal((await call(`/api/viec/${JOB}/duyet`, { cookie })).status, 405);
  assert.equal((await postViec(cookie, `/api/viec/${JOB.toUpperCase()}/duyet`, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" })).status, 404);
  assert.equal(mayGoi.length, 0);
});

test("viec: huy/chay-tiep/chay-lai/tu-choi → POST body {boi} có ký đúng path", async () => {
  const { cookie } = await dangNhapNhan();
  mayTraLoi = async () => Response.json({ viec: { id: JOB } });
  for (const act of ["huy", "chay-tiep", "chay-lai", "tu-choi"]) {
    const r = await postViec(cookie, `/api/viec/${JOB}/${act}`, { boi: "lan", ly_do: "x" });
    assert.equal(r.status, 200, act);
    const g = goiCuoi();
    assert.equal(g.url.pathname, `/r/viec/${JOB}/${act}`);
    assert.equal(g.url.search, "");
    assert.equal(g.method, "POST");
    assert.deepEqual(JSON.parse(g.body), { boi: "nhan" });
    assert.ok(await kiemChuKy(g), act);
  }
});

// Runner giả cho tra-loi: GET /r/viec/<id> trả câu hỏi đang chờ; POST ghi nhận.
function runnerCauHoi(cauHoi, trangThai = "can_tra_loi", dangChuoi = false) {
  mayTraLoi = async (u, opt) => {
    if ((opt.method || "GET") === "GET") return Response.json({ viec: { id: JOB, trang_thai: trangThai, cau_hoi: dangChuoi ? JSON.stringify(cauHoi) : cauHoi }, tra_loi: [] });
    return Response.json({ viec: { id: JOB, trang_thai: "cho" } });
  };
}
const soPost = () => mayGoi.filter((g) => g.method === "POST").length;

test("viec tra-loi: chỉ nhận giá trị nút đúng câu hỏi; ký và gửi {tra_loi, boi}", async () => {
  const { cookie } = await dangNhapNhan();
  const duong = `/api/viec/${JOB}/tra-loi`;
  runnerCauHoi({ loai: "chon", noi_dung: "Chọn thư mục", lua_chon: ["E:/a/sp_1", "Bỏ qua"] }, "can_tra_loi", true);
  const r = await postViec(cookie, duong, { tra_loi: "Bỏ qua", boi: "lan", mat_khau: "x" });
  assert.equal(r.status, 200);
  const g = goiCuoi();
  assert.equal(g.url.pathname, `/r/viec/${JOB}/tra-loi`);
  assert.deepEqual(JSON.parse(g.body), { tra_loi: "Bỏ qua", boi: "nhan" });
  assert.ok(await kiemChuKy(g));
  assert.equal(mayGoi[mayGoi.length - 2].url.pathname, `/r/viec/${JOB}`);

  runnerCauHoi({ loai: "viec_tay", noi_dung: "Mở Poster" });
  assert.equal((await postViec(cookie, duong, { tra_loi: "da_lam_xong" })).status, 200);
  runnerCauHoi({ loai: "khong_ro", noi_dung: "?" });
  assert.equal((await postViec(cookie, duong, { tra_loi: "tiep_tuc" })).status, 200);
  assert.equal(soPost(), 3);
});

test("viec tra-loi: chữ tự do / sai nút / cau_hoi đợt 3 / sai trạng thái → bị từ chối, không POST", async () => {
  const { cookie } = await dangNhapNhan();
  const duong = `/api/viec/${JOB}/tra-loi`;
  runnerCauHoi({ loai: "chon", noi_dung: "Chọn", lua_chon: ["A", "B"] });
  for (const tl of ["C", "a", "A ", "xoá hết dữ liệu đi", "", 1, null, ["A"], "x".repeat(121), "A\nB"]) {
    assert.equal((await postViec(cookie, duong, { tra_loi: tl })).status, 400, JSON.stringify(tl));
  }
  runnerCauHoi({ loai: "viec_tay", noi_dung: "Mở Poster" });
  assert.equal((await postViec(cookie, duong, { tra_loi: "tiep_tuc" })).status, 400);
  assert.equal((await postViec(cookie, duong, { tra_loi: "Tôi đã làm xong rồi nhé" })).status, 400);
  runnerCauHoi({ loai: "khong_ro", noi_dung: "?" });
  assert.equal((await postViec(cookie, duong, { tra_loi: "da_lam_xong" })).status, 400);
  runnerCauHoi({ loai: "cau_hoi", noi_dung: "Viết gì?" });
  assert.equal((await postViec(cookie, duong, { tra_loi: "ok" })).status, 400);
  runnerCauHoi({ loai: "chon", noi_dung: "Chọn", lua_chon: ["A"] }, "dang_chay");
  assert.equal((await postViec(cookie, duong, { tra_loi: "A" })).status, 409);
  runnerCauHoi(null);
  assert.equal((await postViec(cookie, duong, { tra_loi: "A" })).status, 409);
  assert.equal(soPost(), 0);
});

test("viec: máy nhà 401/403 → 502; hết giờ → 504; lỗi mạng → 502; 4xx khác trả nguyên", async () => {
  const { cookie } = await dangNhapNhan();
  const goc = console.error;
  const ghiLoi = [];
  console.error = (...a) => ghiLoi.push(a.join(" "));
  try {
    for (const st of [401, 403]) {
      mayTraLoi = async () => Response.json({ loi: "sai chữ ký" }, { status: st });
      for (const r of [await call("/api/viec/suc-khoe", { cookie }), await postViec(cookie, "/api/viec", { loai: "xu_ly_link_moi" })]) {
        assert.equal(r.status, 502, String(st));
        assert.deepEqual(await r.json(), { loi: "Máy nhà từ chối khoá/chữ ký bộ chạy việc" });
      }
    }
    for (const ten of ["TimeoutError", "AbortError"]) {
      mayTraLoi = async () => { throw new DOMException("hết giờ", ten); };
      assert.equal((await call("/api/viec", { cookie })).status, 504, ten);
    }
    mayTraLoi = async () => { throw new Error("tunnel tắt"); };
    assert.equal((await postViec(cookie, `/api/viec/${JOB}/huy`, {})).status, 502);
  } finally {
    console.error = goc;
  }
  assert.ok(ghiLoi.length >= 7);
  mayTraLoi = async () => Response.json({ trung: { id: JOB } }, { status: 409 });
  const r = await postViec(cookie, "/api/viec", { loai: "phan_tich_uid", tham_so: { uid: UID } });
  assert.equal(r.status, 409);
  assert.deepEqual(await r.json(), { trung: { id: JOB } });
  mayTraLoi = async () => Response.json({ loi: "Tham số sai" }, { status: 400 });
  assert.equal((await postViec(cookie, "/api/viec", { loai: "phan_tich_uid", tham_so: { uid: UID } })).status, 400);
});

test("viec: KY_RIENG hỏng → 503, không gửi request chưa ký", async () => {
  const { cookie } = await dangNhapNhan();
  env.KY_RIENG = "không-phải-khoá";
  const goc = console.error;
  console.error = () => {};
  try {
    assert.equal((await postViec(cookie, "/api/viec", { loai: "xu_ly_link_moi" })).status, 503);
  } finally {
    console.error = goc;
  }
  assert.equal(mayGoi.length, 0);
});

// ---------- đợt 4 (W-4): danh mục tốn tiền, poster/folders, duyệt có mật khẩu + chữ ký kho-duyet-v1 ----------
test("viec: kiemThamSoViec nhận 3 loại đợt 4 (§5.2), validate chặt", () => {
  const D = "0123456789ab", ME = "20261117-a1";
  const BAY_MAU = ["xoay_360", "cam_tay", "can_canh", "dung_that", "dat_ban", "mo_hop", "truoc_sau"];
  for (const [b, mong] of [
    [{ loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: ["xoay_360"] } }, { loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: ["xoay_360"] } }],
    [{ loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: BAY_MAU, thoi_luong: 15, ti_le: "9:16" } },
      { loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: BAY_MAU, thoi_luong: 15, ti_le: "9:16" } }],
    [{ loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: ["mo_hop"], thoi_luong: 10 } }, { loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: ["mo_hop"], thoi_luong: 10 } }],
    [{ loai: "voice_genmax", tham_so: { uid: UID, du_an: D, me: ME } }, { loai: "voice_genmax", tham_so: { uid: UID, du_an: D, me: ME } }],
    [{ loai: "poster_len_lich", tham_so: { folder_id: 12, so_video_ngay: 1 } }, { loai: "poster_len_lich", tham_so: { folder_id: 12, so_video_ngay: 1 } }],
    [{ loai: "poster_len_lich", tham_so: { folder_id: 999999999, so_video_ngay: 5 } }, { loai: "poster_len_lich", tham_so: { folder_id: 999999999, so_video_ngay: 5 } }],
    [{ loai: "poster_len_lich", tham_so: { folder_id: 3, so_video_ngay: 6 } }, { loai: "poster_len_lich", tham_so: { folder_id: 3, so_video_ngay: 6 } }],
    [{ loai: "poster_len_lich", tham_so: { folder_id: 3, so_video_ngay: 100 } }, { loai: "poster_len_lich", tham_so: { folder_id: 3, so_video_ngay: 100 } }],
  ]) assert.deepEqual(kiemThamSoViec(b), mong, JSON.stringify(b));
  for (const b of [
    { loai: "muse_clip", tham_so: { uid: UID, du_an: D } }, { loai: "muse_clip", tham_so: { du_an: D, mau: ["xoay_360"] } },
    { loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: [] } }, { loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: "xoay_360" } },
    { loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: ["xoay_360", "xoay_360"] } }, { loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: ["la_lam"] } },
    { loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: ["__proto__"] } }, { loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: [1] } },
    { loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: ["Xoay_360"] } }, { loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: [...BAY_MAU, "xoay_360"] } },
    { loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: ["xoay_360"], thoi_luong: 12 } }, { loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: ["xoay_360"], thoi_luong: "10" } },
    { loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: ["xoay_360"], ti_le: "16:9" } }, { loai: "muse_clip", tham_so: { uid: UID, du_an: D, mau: ["xoay_360"], prompt: "x" } },
    { loai: "voice_genmax", tham_so: { uid: UID, du_an: D, me: ME, ma_ban: ["a"] } }, { loai: "voice_genmax", tham_so: { uid: UID, du_an: D, me: "20261117" } },
    { loai: "voice_genmax", tham_so: { uid: UID, du_an: D, me: ME, dong_y: true } },
    { loai: "poster_len_lich", tham_so: { folder_id: 12 } }, { loai: "poster_len_lich", tham_so: { so_video_ngay: 2 } },
    { loai: "poster_len_lich", tham_so: { folder_id: "12", so_video_ngay: 2 } }, { loai: "poster_len_lich", tham_so: { folder_id: 0, so_video_ngay: 2 } },
    { loai: "poster_len_lich", tham_so: { folder_id: -3, so_video_ngay: 2 } }, { loai: "poster_len_lich", tham_so: { folder_id: 1.5, so_video_ngay: 2 } },
    { loai: "poster_len_lich", tham_so: { folder_id: 1e9, so_video_ngay: 2 } }, { loai: "poster_len_lich", tham_so: { folder_id: 3, so_video_ngay: 0 } },
    { loai: "poster_len_lich", tham_so: { folder_id: 3, so_video_ngay: 101 } }, { loai: "poster_len_lich", tham_so: { folder_id: 3, so_video_ngay: true } },
    { loai: "poster_len_lich", tham_so: { folder_id: 3, so_video_ngay: 2.5 } }, { loai: "poster_len_lich", tham_so: { folder_id: 3, so_video_ngay: "50" } },
    { loai: "poster_len_lich", tham_so: { folder_id: 3, so_video_ngay: 2, uid: UID } },
    { loai: "taovideo", tham_so: {} },
  ]) assert.equal(typeof kiemThamSoViec(b), "string", JSON.stringify(b));
});

const LOI_DUYET = "Duyệt, làm luôn — tối đa 20 video\nđã xem ước tính";
// tham_so_chuan cố ý có khoảng trắng: Worker phải ký NGUYÊN CHUỖI runner trả, không stringify lại.
const TS_CHUAN = "{\"du_an\":\"0123456789ab\", \"me\":\"20261117-a1\",\"uid\":\"1729706628656957720\"}";
// [P2-2] sha256hex của tham_so_chuan người dùng đã xem (tính đồng bộ, không top-level await).
const SHA_TS = createHash("sha256").update(Buffer.from(TS_CHUAN, "utf8")).digest("hex");
function runnerDuyet({ trangThai = "cho_duyet", loai = "voice_genmax", thamSoChuan = TS_CHUAN, getStatus = 200, post = () => Response.json({ viec: { id: JOB, trang_thai: "cho" } }) } = {}) {
  mayTraLoi = async (u, opt) => {
    if ((opt.method || "GET") === "GET") {
      if (getStatus !== 200) return Response.json({ loi: "x" }, { status: getStatus });
      return Response.json({ viec: { id: JOB, loai, trang_thai: trangThai }, tra_loi: [], xem_truoc: null, ...(thamSoChuan === "THIEU" ? {} : { tham_so_chuan: thamSoChuan }) });
    }
    return post(u, opt);
  };
}
const duongDuyet = `/api/viec/${JOB}/duyet`;
const RE_ISO_TZ = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;

test("viec duyet: đúng mật khẩu → GET tham_so_chuan, ký duyệt + ký request, boi từ phiên, không chuyển mật khẩu", async () => {
  const { cookie } = await dangNhapNhan();
  runnerDuyet();
  const r = await postViec(cookie, duongDuyet, { loi_duyet: LOI_DUYET, sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan", boi: "comeofage", duyet_luc: "2000-01-01T00:00:00+07:00", chu_ky_duyet: "x" });
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { viec: { id: JOB, trang_thai: "cho" } });
  assert.equal(mayGoi.length, 2);
  const [g1, g2] = mayGoi;
  assert.equal(g1.method, "GET");
  assert.equal(g1.url.pathname + g1.url.search, `/r/viec/${JOB}`);
  assert.equal(g2.method, "POST");
  assert.equal(g2.url.pathname + g2.url.search, `/r/viec/${JOB}/duyet`);
  assert.ok(await kiemChuKy(g2));
  const b = JSON.parse(g2.body);
  assert.deepEqual(Object.keys(b).sort(), ["boi", "chu_ky_duyet", "duyet_luc", "loi_duyet"]);
  assert.equal(b.boi, "nhan");
  assert.equal(b.loi_duyet, LOI_DUYET);
  assert.match(b.duyet_luc, RE_ISO_TZ);
  assert.ok(b.duyet_luc.length <= 40);
  assert.ok(Math.abs(Date.parse(b.duyet_luc) - Date.now()) < 60000);
  assert.match(b.chu_ky_duyet, /^[A-Za-z0-9_-]{86}$/);
  const chuoi = await chuoiKyDuyet(JOB, "voice_genmax", TS_CHUAN, LOI_DUYET, b.duyet_luc, "nhan");
  assert.ok(await crypto.subtle.verify({ name: "Ed25519" }, CAP_KHOA.publicKey, tuB64url(b.chu_ky_duyet), chuoi));
  // stringify lại tham_so_chuan sẽ ra chuỗi khác → chữ ký không khớp (chứng minh ký nguyên chuỗi)
  const chuoiLai = await chuoiKyDuyet(JOB, "voice_genmax", JSON.stringify(JSON.parse(TS_CHUAN)), LOI_DUYET, b.duyet_luc, "nhan");
  assert.ok(!(await crypto.subtle.verify({ name: "Ed25519" }, CAP_KHOA.publicKey, tuB64url(b.chu_ky_duyet), chuoiLai)));
  for (const g of mayGoi) {
    const lo = JSON.stringify([g.url.href, g.headers, g.body || ""]);
    assert.equal(lo.includes("matkhau-nhan"), false);
    assert.equal(lo.includes("mat_khau"), false);
  }
});

test("viec duyet: sai mật khẩu → 403 không gọi máy nhà; lần sai thứ 6 → 429 (kể cả mật khẩu đúng); hết 10 phút mở lại", async (t) => {
  const { cookie } = await dangNhapNhan();
  runnerDuyet();
  const goc = Date.now();
  let bayGio = goc;
  t.mock.method(Date, "now", () => bayGio);
  for (let i = 1; i <= 5; i++) {
    const r = await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: `sai-${i}` });
    assert.equal(r.status, 403, `lần ${i}`);
    assert.deepEqual(await r.json(), { loi: "Sai mật khẩu" });
  }
  const r6 = await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "sai-6" });
  assert.equal(r6.status, 429);
  assert.match((await r6.json()).loi, /10 phút/);
  assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" })).status, 429);
  assert.equal(mayGoi.length, 0);
  // người duyệt khác không bị khoá theo
  const come = await dangNhap("comeofage", "matkhau-come");
  assert.equal((await postViec(come.cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-come" })).status, 200);
  assert.equal(JSON.parse(goiCuoi().body).boi, "comeofage");
  mayGoi = [];
  bayGio = goc + 9 * 60e3;
  assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" })).status, 429);
  bayGio = goc + 10 * 60e3 + 1000;
  assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" })).status, 200);
});

test("viec duyet: mật khẩu đúng không xoá lần sai cũ; sai cũ quá 10 phút thì không tính", async (t) => {
  const { cookie } = await dangNhapNhan();
  runnerDuyet();
  const goc = Date.now();
  let bayGio = goc;
  t.mock.method(Date, "now", () => bayGio);
  for (let i = 0; i < 4; i++) assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "sai" })).status, 403);
  assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" })).status, 200);
  assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "sai" })).status, 403); // lần sai thứ 5
  assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" })).status, 429);
  datLaiDemSaiMatKhau();
  bayGio = goc + 20 * 60e3;
  for (let i = 0; i < 4; i++) assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "sai" })).status, 403);
  bayGio += 10 * 60e3 + 1000; // 4 lần cũ trôi khỏi cửa sổ
  for (let i = 0; i < 5; i++) assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "sai" })).status, 403, `lần ${i}`);
  assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "sai" })).status, 429);
});

test("viec duyet: 8 request sai mật khẩu song song → đúng 5 lần 403, còn lại 429", async () => {
  const { cookie } = await dangNhapNhan();
  runnerDuyet();
  const ds = await Promise.all(Array.from({ length: 8 }, (_, i) => postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: `sai-${i}` })));
  assert.deepEqual(ds.map((r) => r.status).sort(), [403, 403, 403, 403, 403, 429, 429, 429]);
  assert.equal(mayGoi.length, 0);
});

test("viec duyet: đếm sai lưu qua Cache API → isolate mới (mất bộ nhớ) vẫn khoá; cache hỏng không 500", async () => {
  const kho = new Map();
  const daPut = [];
  const khoa = (req) => (typeof req === "string" ? req : req.url);
  globalThis.caches.default = {
    match: async (req) => { const r = kho.get(khoa(req)); return r ? r.clone() : undefined; },
    put: async (req, res) => { daPut.push({ k: khoa(req), cc: res.headers.get("cache-control"), noiDung: await res.clone().text() }); kho.set(khoa(req), res.clone()); },
  };
  const { cookie } = await dangNhapNhan();
  runnerDuyet();
  for (let i = 0; i < 5; i++) assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "sai-bi-mat" })).status, 403);
  assert.ok(daPut.length >= 5);
  assert.match(daPut[0].cc, /max-age=\d+/);
  for (const p of daPut) assert.equal((p.k + p.noiDung).includes("sai-bi-mat"), false);
  datLaiDemSaiMatKhau(); // như isolate mới
  assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" })).status, 429);
  globalThis.caches.default = { match: async () => { throw new Error("cache hỏng"); }, put: async () => { throw new Error("cache hỏng"); } };
  datLaiDemSaiMatKhau();
  const goc = console.error;
  console.error = () => {};
  try {
    assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "sai" })).status, 403);
    assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" })).status, 200);
  } finally {
    console.error = goc;
  }
});

test("viec duyet: body sai → 400, không gọi máy nhà, không tính lần sai", async () => {
  const { cookie } = await dangNhapNhan();
  runnerDuyet();
  for (const b of [
    {}, { mat_khau: "matkhau-nhan" }, { loi_duyet: "", mat_khau: "matkhau-nhan" }, { loi_duyet: "   \n ", mat_khau: "matkhau-nhan" },
    { loi_duyet: 1, mat_khau: "matkhau-nhan" }, { loi_duyet: ["ok"], mat_khau: "matkhau-nhan" }, { loi_duyet: "đ".repeat(2001), mat_khau: "matkhau-nhan" },
    { loi_duyet: "ok" }, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "" }, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: 123 }, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "x".repeat(257) },
  ]) assert.equal((await postViec(cookie, duongDuyet, b)).status, 400, JSON.stringify(b).slice(0, 60));
  assert.equal(mayGoi.length, 0);
  // 2000 ký tự (ký tự ngoài BMP đếm 1 như Python len) vẫn nhận; chưa bị khoá
  const dai = "😀".repeat(2000);
  assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: dai, sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" })).status, 200);
  assert.equal(JSON.parse(goiCuoi().body).loi_duyet, dai);
});

test("viec duyet: user không phải nhan/comeofage → 403; thiếu Origin → 403; không gọi máy nhà", async () => {
  const { cookie } = await dangNhap();
  runnerDuyet();
  assert.deepEqual(await (await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-lan" })).json(), { loi: "Không có quyền" });
  const nhan = await dangNhapNhan();
  assert.equal((await call(duongDuyet, { cookie: nhan.cookie, body: { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" } })).status, 403);
  assert.equal(mayGoi.length, 0);
});

test("viec duyet: runner không ở cho_duyet → 409; 404 trả nguyên; dữ liệu lạ → 502; POST 429/400 trả nguyên; 401 → 502", async () => {
  const { cookie } = await dangNhapNhan();
  const gui = () => postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" });
  for (const tt of ["cho", "dang_chay", "xong", "huy"]) {
    runnerDuyet({ trangThai: tt });
    assert.equal((await gui()).status, 409, tt);
  }
  runnerDuyet({ getStatus: 404 });
  assert.equal((await gui()).status, 404);
  for (const ts of ["THIEU", null, 5, { a: 1 }]) {
    runnerDuyet({ thamSoChuan: ts });
    assert.equal((await gui()).status, 502, JSON.stringify(ts));
  }
  runnerDuyet({ loai: "Loai la\nx" });
  assert.equal((await gui()).status, 502);
  assert.equal(mayGoi.filter((g) => g.method === "POST").length, 0);
  runnerDuyet({ post: () => Response.json({ loi: "Vượt hạn mức" }, { status: 429 }) });
  const r = await gui();
  assert.equal(r.status, 429);
  assert.deepEqual(await r.json(), { loi: "Vượt hạn mức" });
  runnerDuyet({ post: () => Response.json({ loi: "duyet_luc lệch" }, { status: 400 }) });
  assert.equal((await gui()).status, 400);
  const goc = console.error;
  console.error = () => {};
  try {
    runnerDuyet({ post: () => Response.json({ loi: "chữ ký sai" }, { status: 401 }) });
    assert.equal((await gui()).status, 502);
  } finally {
    console.error = goc;
  }
});

test("viec duyet: chuoiKyDuyet từ chối xuống dòng ở trường không băm", async () => {
  const LUC = "2026-11-17T21:05:00+07:00";
  await assert.rejects(chuoiKyDuyet(`${JOB}\n`, "voice_genmax", "{}", "ok", LUC, "nhan"));
  await assert.rejects(chuoiKyDuyet(JOB, "voice_genmax", "{}", "ok", `${LUC}\r`, "nhan"));
  await assert.rejects(chuoiKyDuyet(JOB, "voice_genmax", "{}", "ok", LUC, "nhan\nx"));
  await assert.rejects(chuoiKyDuyet(JOB, "voice_genmax", 5, "ok", LUC, "nhan"));
  const ok = await chuoiKyDuyet(JOB, "voice_genmax", "{}", "a\nb", LUC, "nhan");
  assert.equal(new TextDecoder().decode(ok).split("\n").length, 7);
});

// ---------- [P2-2] sha_tham_so: dữ liệu việc đổi giữa lúc xem và lúc duyệt ----------
test("viec duyet: thiếu/sai dạng sha_tham_so → 400, không gọi máy nhà, không tính lần sai", async () => {
  const { cookie } = await dangNhapNhan();
  runnerDuyet();
  for (const sha of [undefined, "", 5, SHA_TS.toUpperCase(), SHA_TS.slice(1), `${SHA_TS}0`, "g".repeat(64)]) {
    const r = await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: sha, mat_khau: "sai" });
    assert.equal(r.status, 400, String(sha));
  }
  assert.equal(mayGoi.length, 0);
  assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" })).status, 200);
});

test("viec duyet: sha_tham_so lệch tham_so_chuan runner → 409, KHÔNG ký, KHÔNG POST runner", async () => {
  const { cookie } = await dangNhapNhan();
  runnerDuyet({ thamSoChuan: TS_CHUAN.replace("20261117-a1", "20261117-b2") });
  const r = await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" });
  assert.equal(r.status, 409);
  assert.deepEqual(await r.json(), { loi: "Dữ liệu việc đã đổi — tải lại rồi duyệt" });
  assert.equal(soPost(), 0);
  assert.equal(mayGoi.length, 1);
  assert.equal(mayGoi[0].method, "GET");
});

test("viec: POST /api/viec poster_len_lich so_video_ngay 1–100 qua, 101 → 400 không gọi máy nhà", async () => {
  const { cookie } = await dangNhapNhan();
  mayTraLoi = async () => Response.json({ viec: { id: JOB } }, { status: 201 });
  const r = await postViec(cookie, "/api/viec", { loai: "poster_len_lich", tham_so: { folder_id: 12, so_video_ngay: 100 } });
  assert.equal(r.status, 201);
  assert.deepEqual(JSON.parse(goiCuoi().body), { loai: "poster_len_lich", tham_so: { folder_id: 12, so_video_ngay: 100 }, boi: "nhan" });
  mayGoi = [];
  for (const n of [0, 101, 1000]) assert.equal((await postViec(cookie, "/api/viec", { loai: "poster_len_lich", tham_so: { folder_id: 12, so_video_ngay: n } })).status, 400, String(n));
  assert.equal(mayGoi.length, 0);
});

// ---------- xin duyệt lại ----------
test("viec xin-duyet-lai: POST {boi} ký đúng path, không cần mật khẩu; user lạ 403; GET 405", async () => {
  const { cookie } = await dangNhapNhan();
  mayTraLoi = async () => Response.json({ viec: { id: JOB, trang_thai: "cho_duyet" } });
  const r = await postViec(cookie, `/api/viec/${JOB}/xin-duyet-lai`, { boi: "lan", mat_khau: "x" });
  assert.equal(r.status, 200);
  const g = goiCuoi();
  assert.equal(g.url.pathname + g.url.search, `/r/viec/${JOB}/xin-duyet-lai`);
  assert.equal(g.method, "POST");
  assert.deepEqual(JSON.parse(g.body), { boi: "nhan" });
  assert.ok(await kiemChuKy(g));
  assert.equal(mayGoi.length, 1);
  assert.equal((await call(`/api/viec/${JOB}/xin-duyet-lai`, { cookie })).status, 405);
  const lan = await dangNhap();
  assert.equal((await postViec(lan.cookie, `/api/viec/${JOB}/xin-duyet-lai`, {})).status, 403);
  assert.equal((await call(`/api/viec/${JOB}/xin-duyet-lai`, { cookie, body: {} })).status, 403); // thiếu Origin
  assert.equal(mayGoi.length, 1);
});

// ---------- D9: sổ duyệt KV ----------
function taoKvGia() {
  const kho = new Map();
  const goi = [];
  return {
    kho, goi, hong: false,
    async get(k, opt) {
      goi.push(["get", k]);
      if (this.hong) throw new Error("kv hỏng");
      const v = kho.get(k);
      if (v === undefined) return null;
      const loai = typeof opt === "string" ? opt : opt && opt.type;
      return loai === "json" ? JSON.parse(v.value) : v.value;
    },
    async put(k, value, opt = {}) {
      goi.push(["put", k, opt]);
      if (this.hong) throw new Error("kv hỏng");
      assert.equal(typeof value, "string");
      kho.set(k, { value, opt });
    },
  };
}
const CK_DUYET = "A".repeat(43) + "_-" + "b".repeat(40) + "Q"; // 86 ký tự base64url DẠNG CHUẨN (4 bit thừa cuối = 0)
const B64URL_BANG = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
// Khoá sổ tiêu = "tieu:" + sha256hex(64 byte chữ ký đã giải) — không băm chuỗi.
const khoaTieu = async (ck) => `tieu:${hex(await crypto.subtle.digest("SHA-256", tuB64url(ck)))}`;
const NONCE = "0123456789abcdef0123456789abcdef";
const tieu = (body, { key = "rk", headers = {}, method = "POST" } = {}) =>
  worker.fetch(new Request(`${ORIGIN}/api/runner/tieu-duyet`, {
    method,
    headers: { "content-type": "application/json", ...(key === null ? {} : { "x-runner-key": key }), ...headers },
    body: method === "GET" ? undefined : typeof body === "string" ? body : JSON.stringify(body),
  }), env, ctx);

test("chuoiTieuDuyet: đúng định dạng kho-tieu-v1 từng byte; từ chối xuống dòng", async () => {
  const out = await chuoiTieuDuyet(JOB, CK_DUYET, NONCE);
  assert.ok(out instanceof Uint8Array);
  assert.equal(new TextDecoder().decode(out), `kho-tieu-v1\n${JOB}\n${await sha256Hex(CK_DUYET)}\n${NONCE}`);
  await assert.rejects(chuoiTieuDuyet(`${JOB}\n`, CK_DUYET, NONCE));
  await assert.rejects(chuoiTieuDuyet(JOB, CK_DUYET, `${NONCE}\n`));
  await assert.rejects(chuoiTieuDuyet(JOB, 5, NONCE));
});

test("tieu-duyet: lần 1 → 200 + chữ ký kiểm được bằng khoá công khai; lần 2 → 409; không cần phiên/Origin", async () => {
  env.SO_DUYET = taoKvGia();
  const r = await tieu({ id: JOB, chu_ky_duyet: CK_DUYET, nonce: NONCE });
  assert.equal(r.status, 200);
  const d = await r.json();
  assert.deepEqual(Object.keys(d), ["ky"]);
  assert.match(d.ky, /^[A-Za-z0-9_-]{86}$/);
  assert.ok(await crypto.subtle.verify({ name: "Ed25519" }, CAP_KHOA.publicKey, tuB64url(d.ky), await chuoiTieuDuyet(JOB, CK_DUYET, NONCE)));
  // nonce khác → chữ ký không khớp
  assert.ok(!(await crypto.subtle.verify({ name: "Ed25519" }, CAP_KHOA.publicKey, tuB64url(d.ky), await chuoiTieuDuyet(JOB, CK_DUYET, "f".repeat(32)))));
  const khoa = await khoaTieu(CK_DUYET);
  assert.notEqual(khoa, `tieu:${await sha256Hex(CK_DUYET)}`);
  assert.equal(env.SO_DUYET.kho.has(`tieu:${await sha256Hex(CK_DUYET)}`), false, "không được băm chuỗi base64url");
  const muc = env.SO_DUYET.kho.get(khoa);
  assert.ok(muc, "phải ghi khoá tieu:<sha256hex 64 byte>");
  const giaTri = JSON.parse(muc.value);
  assert.deepEqual(Object.keys(giaTri).sort(), ["id", "luc"]);
  assert.equal(giaTri.id, JOB);
  // §8.3: sổ tiêu KHÔNG đặt TTL
  assert.equal(muc.opt.expirationTtl, undefined);
  assert.equal(muc.opt.expiration, undefined);
  // lần 2 (nonce khác) → 409 kèm luc = thời điểm tiêu đầu
  const r2 = await tieu({ id: JOB, chu_ky_duyet: CK_DUYET, nonce: "f".repeat(32) });
  assert.equal(r2.status, 409);
  assert.deepEqual(await r2.json(), { loi: "Lời duyệt đã dùng", luc: giaTri.luc });
  // isolate mới (mất bộ nhớ) → KV vẫn chặn, luc lấy từ sổ KV
  datLaiSoTieuBoNho();
  const r3 = await tieu({ id: JOB, chu_ky_duyet: CK_DUYET, nonce: NONCE });
  assert.equal(r3.status, 409);
  assert.deepEqual(await r3.json(), { loi: "Lời duyệt đã dùng", luc: giaTri.luc });
  assert.equal(mayGoi.length, 0);
});

test("tieu-duyet [FX-17 P1-1]: 16 biến thể ký tự cuối (cùng 64 byte) → 400 trừ dạng chuẩn; dạng chuẩn tiêu 2 lần → 409", async () => {
  env.SO_DUYET = taoKvGia();
  const dau = CK_DUYET.slice(0, 85);
  const viTri = B64URL_BANG.indexOf(CK_DUYET[85]);
  assert.equal(viTri % 16, 0);
  const bienThe = Array.from({ length: 16 }, (_, i) => dau + B64URL_BANG[viTri + i]);
  // cùng 64 byte sau khi giải
  for (const ck of bienThe) assert.deepEqual(tuB64url(ck), tuB64url(CK_DUYET));
  for (const ck of bienThe) {
    if (ck === CK_DUYET) continue;
    const r = await tieu({ id: JOB, chu_ky_duyet: ck, nonce: NONCE });
    assert.equal(r.status, 400, ck);
    assert.equal((await r.json()).ky, undefined);
  }
  assert.equal(env.SO_DUYET.goi.length, 0, "dạng không chuẩn không được đụng KV");
  assert.equal((await tieu({ id: JOB, chu_ky_duyet: CK_DUYET, nonce: NONCE })).status, 200);
  const r2 = await tieu({ id: JOB, chu_ky_duyet: CK_DUYET, nonce: "f".repeat(32) });
  assert.equal(r2.status, 409);
  assert.equal(typeof (await r2.json()).luc, "string");
  // isolate mới: các biến thể vẫn 400 (không lọt sang khoá KV mới)
  datLaiSoTieuBoNho();
  for (const ck of bienThe) if (ck !== CK_DUYET) assert.equal((await tieu({ id: JOB, chu_ky_duyet: ck, nonce: NONCE })).status, 400, ck);
  assert.equal(env.SO_DUYET.goi.filter((g) => g[0] === "put").length, 1);
});

test("tieu-duyet: 5 request song song cùng chu_ky_duyet → đúng 1 lần 200", async () => {
  env.SO_DUYET = taoKvGia();
  const ds = await Promise.all(Array.from({ length: 5 }, () => tieu({ id: JOB, chu_ky_duyet: CK_DUYET, nonce: NONCE })));
  assert.deepEqual(ds.map((r) => r.status).sort(), [200, 409, 409, 409, 409]);
});

test("tieu-duyet: runner key thiếu/sai → 401; thiếu cấu hình → 503; không đụng KV", async () => {
  env.SO_DUYET = taoKvGia();
  const b = { id: JOB, chu_ky_duyet: CK_DUYET, nonce: NONCE };
  for (const key of [null, "", "rk2", "r", "RK"]) assert.equal((await tieu(b, { key })).status, 401, String(key));
  // cookie phiên hợp lệ không thay được runner key
  const { cookie } = await dangNhapNhan();
  assert.equal((await tieu(b, { key: null, headers: { cookie } })).status, 401);
  for (const k of ["RUNNER_KEY", "KY_RIENG", "SO_DUYET"]) {
    const giu = env[k];
    delete env[k];
    assert.equal((await tieu(b)).status, 503, k);
    env[k] = giu;
  }
  assert.equal(env.SO_DUYET.goi.length, 0);
  // Origin lạ vẫn bị chặn chung
  assert.equal((await tieu(b, { headers: { origin: "https://evil.test" } })).status, 403);
  assert.equal((await tieu(b, { method: "GET" })).status, 405);
});

test("tieu-duyet: body sai → 400, không ghi KV", async () => {
  env.SO_DUYET = taoKvGia();
  const tot = { id: JOB, chu_ky_duyet: CK_DUYET, nonce: NONCE };
  for (const sai of [
    { id: undefined }, { id: JOB.toUpperCase() }, { id: "j123" }, { id: `${JOB}\n` }, { id: 5 }, { id: "1729706628656957720" },
    { chu_ky_duyet: undefined }, { chu_ky_duyet: CK_DUYET.slice(1) }, { chu_ky_duyet: `${CK_DUYET}A` }, { chu_ky_duyet: CK_DUYET.slice(1) + "=" }, { chu_ky_duyet: CK_DUYET.slice(1) + "+" },
    { nonce: undefined }, { nonce: NONCE.toUpperCase() }, { nonce: NONCE.slice(1) }, { nonce: `${NONCE}0` }, { nonce: 1 },
  ]) assert.equal((await tieu({ ...tot, ...sai })).status, 400, JSON.stringify(sai));
  for (const tho of ["{không phải json", "[]", "null", "\"x\""]) assert.equal((await tieu(tho)).status, 400, tho);
  assert.equal(env.SO_DUYET.goi.filter((g) => g[0] === "put").length, 0);
});

test("tieu-duyet: KV lỗi → 503 (không trả chữ ký), lần sau KV lành vẫn tiêu được", async () => {
  env.SO_DUYET = taoKvGia();
  env.SO_DUYET.hong = true;
  const goc = console.error;
  console.error = () => {};
  try {
    const r = await tieu({ id: JOB, chu_ky_duyet: CK_DUYET, nonce: NONCE });
    assert.equal(r.status, 503);
    assert.equal((await r.json()).ky, undefined);
  } finally {
    console.error = goc;
  }
  env.SO_DUYET.hong = false;
  assert.equal((await tieu({ id: JOB, chu_ky_duyet: CK_DUYET, nonce: NONCE })).status, 200);
});

test("viec duyet: có SO_DUYET → đếm sai lưu KV sai:<user> TTL 10 phút, isolate mới vẫn khoá; không dùng Cache API", async () => {
  env.SO_DUYET = taoKvGia();
  let dungCache = 0;
  globalThis.caches.default = { match: async () => { dungCache++; }, put: async () => { dungCache++; } };
  const { cookie } = await dangNhapNhan();
  runnerDuyet();
  for (let i = 0; i < 5; i++) assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "sai-bi-mat" })).status, 403);
  const muc = env.SO_DUYET.kho.get("sai:nhan");
  assert.ok(muc, "phải ghi khoá sai:nhan");
  assert.equal(muc.opt.expirationTtl, 600);
  assert.equal(muc.value.includes("sai-bi-mat"), false);
  assert.equal(dungCache, 0);
  datLaiDemSaiMatKhau(); // như isolate mới
  assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" })).status, 429);
  // user khác không bị khoá
  const come = await dangNhap("comeofage", "matkhau-come");
  assert.equal((await postViec(come.cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-come" })).status, 200);
});

test("viec duyet: có SO_DUYET → 8 request sai song song vẫn đúng 5 lần 403", async () => {
  env.SO_DUYET = taoKvGia();
  const { cookie } = await dangNhapNhan();
  runnerDuyet();
  const ds = await Promise.all(Array.from({ length: 8 }, (_, i) => postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: `sai-${i}` })));
  assert.deepEqual(ds.map((r) => r.status).sort(), [403, 403, 403, 403, 403, 429, 429, 429]);
});

test("viec duyet [FX-17 P2-2]: KV đọc lỗi → 503, KHÔNG kiểm mật khẩu (kể cả isolate mới, mật khẩu đúng/sai), không gọi runner", async () => {
  env.SO_DUYET = taoKvGia();
  const { cookie } = await dangNhapNhan();
  runnerDuyet();
  datLaiDemSaiMatKhau(); // isolate mới: bộ đếm bộ nhớ trống — trước đây lọt qua dò mật khẩu
  env.SO_DUYET.hong = true;
  const goc = console.error;
  console.error = () => {};
  try {
    for (let i = 0; i < 8; i++) {
      const r = await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: `sai-${i}` });
      assert.equal(r.status, 503, `lần ${i}`);
      assert.deepEqual(await r.json(), { loi: "Không kiểm được số lần sai — thử lại sau" });
    }
    const dung = await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" });
    assert.equal(dung.status, 503, "mật khẩu đúng cũng không được kiểm khi KV đọc lỗi");
  } finally {
    console.error = goc;
  }
  assert.equal(mayGoi.length, 0);
  assert.equal(env.SO_DUYET.goi.filter((g) => g[0] === "put").length, 0, "không kiểm mật khẩu → không ghi lần sai");
  // KV lành lại → duyệt bình thường, các lần 503 không bị tính là sai
  env.SO_DUYET.hong = false;
  assert.equal((await postViec(cookie, duongDuyet, { loi_duyet: "ok", sha_tham_so: SHA_TS, mat_khau: "matkhau-nhan" })).status, 200);
});
