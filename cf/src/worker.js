// Kho sản phẩm — Cloudflare Worker: đăng nhập user/pass + API đọc/ghi repo GitHub (dữ liệu vẫn ở data/<id>/).
// Token GitHub chỉ nằm trong secret GITHUB_TOKEN của Worker; trình duyệt chỉ cầm cookie phiên.
// Secret: GITHUB_TOKEN, SESSION_SECRET, USERS (JSON do cf/tools/tao-users.mjs sinh). Biến: GH_REPO, GH_BRANCH.
"use strict";

const COOKIE = "kho_s";
const PHIEN_GIAY = 30 * 24 * 3600;
const LOAI_QUAY = ["oneshot", "review"];
const RE_ID = /^(\d{15,21}|tam-\d{10,24})$/;
const RE_ANH = /^[\w.-]+\.(jpe?g|png|webp)$/i;

// ---------- tiện ích ----------
const te = new TextEncoder();
const b64url = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64url = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
function b64encUtf8(text) {
  const bytes = te.encode(text);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}
const b64decUtf8 = (b) => new TextDecoder().decode(Uint8Array.from(atob(b.replace(/\n/g, "")), (c) => c.charCodeAt(0)));

export function nowIso(ms = Date.now()) {
  return new Date(ms + 7 * 3600e3).toISOString().slice(0, 19) + "+07:00";
}
export function tachUid(link) {
  const s = (link || "").trim();
  if (/^\d{15,21}$/.test(s)) return s;
  const m = s.match(/(?:\/pdp\/(?:[^/?#]+\/)?|\/product\/|\/products\/|product_id=)(\d{15,21})/);
  return m ? m[1] : null;
}
function quay(i, loai) {
  const q = i[`da_quay_${loai}`];
  if (q) return q;
  if (loai === "review" && i.da_quay && i.da_quay.xong) return i.da_quay;
  return { xong: false, boi: "", luc: "" };
}
export function trangThai(i) {
  if (i.da_lam_video && i.da_lam_video.xong) return "da_lam_video";
  if (LOAI_QUAY.some((l) => quay(i, l).xong)) return "da_quay";
  if (i.da_phan_tich) return "da_phan_tich";
  return "cho";
}

const json = (data, status = 200, headers = {}) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers } });
const loi = (msg, status = 400) => json({ loi: msg }, status);

// ---------- mật khẩu + phiên ----------
async function hmac(secret, data) {
  const k = await crypto.subtle.importKey("raw", te.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64url(await crypto.subtle.sign("HMAC", k, te.encode(data)));
}
function bangNhau(a, b) {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}
// "pbkdf2$<vòng>$<salt b64url>$<hash b64url>"
export async function bamMatKhau(pass, saltBytes = crypto.getRandomValues(new Uint8Array(16)), vong = 100000) {
  const k = await crypto.subtle.importKey("raw", te.encode(pass), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: saltBytes, iterations: vong }, k, 256);
  return `pbkdf2$${vong}$${b64url(saltBytes)}$${b64url(bits)}`;
}
export async function kiemMatKhau(pass, chuoi) {
  const [loai, vong, salt] = String(chuoi || "").split("$");
  if (loai !== "pbkdf2") return false;
  return bangNhau(await bamMatKhau(pass, unb64url(salt), Number(vong)), chuoi);
}
function dsUser(env) {
  try { return JSON.parse(env.USERS || "{}"); } catch { return {}; }
}
export async function taoPhien(env, user, ms = Date.now()) {
  const body = b64url(te.encode(JSON.stringify({ u: user, h: Math.floor(ms / 1000) + PHIEN_GIAY })));
  return `${body}.${await hmac(env.SESSION_SECRET, body)}`;
}
export async function docPhien(env, req) {
  const m = (req.headers.get("cookie") || "").match(new RegExp(`(?:^|;\\s*)${COOKIE}=([^;]+)`));
  if (!m || !env.SESSION_SECRET) return null;
  const [body, sig] = m[1].split(".");
  if (!body || !sig || !bangNhau(sig, await hmac(env.SESSION_SECRET, body))) return null;
  let p;
  try { p = JSON.parse(new TextDecoder().decode(unb64url(body))); } catch { return null; }
  if (!p || p.h * 1000 < Date.now()) return null;
  const u = dsUser(env)[p.u];
  return u ? { user: p.u, ten: u.ten || p.u } : null; // xoá user khỏi USERS → phiên cũ hết hiệu lực
}
const cookiePhien = (val, tuoi) => `${COOKIE}=${val}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${tuoi}`;

// ---------- GitHub ----------
function gh(env, path, opt = {}) {
  return fetch(`https://api.github.com/repos/${env.GH_REPO}${path}`, {
    ...opt,
    headers: {
      Accept: "application/vnd.github+json",
      "User-Agent": "kho-san-pham-worker",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(env.GITHUB_TOKEN ? { Authorization: `Bearer ${env.GITHUB_TOKEN}` } : {}),
      ...(opt.headers || {}),
    },
  });
}
const nhanh = (env) => env.GH_BRANCH || "main";
async function loiGh(r, viec) {
  let chiTiet = "";
  const t = await r.text().catch(() => "");
  try { chiTiet = JSON.parse(t).message || ""; } catch { chiTiet = t.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 160); }
  return new Error(`${viec} lỗi GitHub ${r.status}${chiTiet ? ` (${chiTiet})` : ""}`);
}

async function getFile(env, path) {
  const r = await gh(env, `/contents/${path}?ref=${nhanh(env)}`);
  if (r.status === 404) return null;
  if (!r.ok) throw await loiGh(r, `Đọc ${path}`);
  const j = await r.json();
  return { text: b64decUtf8(j.content || ""), sha: j.sha };
}
async function getText(env, path) {
  const r = await gh(env, `/contents/${path}?ref=${nhanh(env)}`, { headers: { Accept: "application/vnd.github.raw+json" } });
  if (r.status === 404) return null;
  if (!r.ok) throw await loiGh(r, `Đọc ${path}`);
  return r.text();
}
async function putFile(env, path, text, sha, message) {
  const r = await gh(env, `/contents/${path}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ message, content: b64encUtf8(text), branch: nhanh(env), ...(sha ? { sha } : {}) }),
  });
  if (r.status === 409 || r.status === 422) return { conflict: true };
  if (!r.ok) throw await loiGh(r, `Ghi ${path}`);
  return { ok: true };
}
// Sửa 1 file JSON an toàn khi nhiều người ghi cùng lúc (sha lệch → đọc lại, thử lại).
// macDinh: giá trị khi file chưa có (null → báo không tìm thấy). mutate trả chuỗi = lỗi người dùng.
async function suaJson(env, path, mutate, message, macDinh = null) {
  for (let lan = 0; lan < 3; lan++) {
    const f = await getFile(env, path);
    if (!f && !macDinh) throw Object.assign(new Error("Sản phẩm không còn trong kho"), { status: 404 });
    const d = f ? JSON.parse(f.text) : structuredClone(macDinh);
    const loiND = mutate(d);
    if (typeof loiND === "string") throw Object.assign(new Error(loiND), { status: 400 });
    if ((await putFile(env, path, JSON.stringify(d, null, 1) + "\n", f && f.sha, message)).ok) return d;
  }
  throw Object.assign(new Error("Có người vừa sửa cùng lúc — thử lại"), { status: 409 });
}
const updateInfo = (env, id, mutate, message) =>
  suaJson(env, `data/${id}/info.json`, (i) => { mutate(i); i.cap_nhat_luc = nowIso(); }, message);

// Video tham khảo: data/<id>/video_tk.json (danh sách) + data/<id>/video_tk/<vid>.json (bảng cảnh) + video_tk/<vid>/cNN.jpg
const RE_VID = /^v\d{8,20}$/;
const VTK_RONG = { videos: [] };
export function taoVid(ms = Date.now()) {
  return "v" + nowIso(ms).replace(/\D/g, "").slice(0, 14) + String(ms % 1000).padStart(3, "0");
}

// index.json (Action dựng) + sản phẩm mới có info.json mà index chưa kịp có.
async function danhSach(env) {
  const [t, tree] = await Promise.all([
    getText(env, "data/index.json"),
    gh(env, `/git/trees/${nhanh(env)}?recursive=1`).then((r) => (r.ok ? r.json() : { tree: [] })),
  ]);
  const ds = t ? JSON.parse(t).san_pham || [] : [];
  const coFile = new Set((tree.tree || []).map((x) => x.path));
  const ids = new Set(ds.map((x) => x.id));
  const moi = [...coFile].map((p) => p.match(/^data\/([^/]+)\/info\.json$/)).filter(Boolean).map((m) => m[1]).filter((id) => !ids.has(id));
  const them = await Promise.all(moi.map(async (id) => { const s = await getText(env, `data/${id}/info.json`); return s && JSON.parse(s); }));
  for (const i of them.filter(Boolean)) ds.unshift({ ...i, tom_tat: undefined, trang_thai: trangThai(i) });
  // bỏ sản phẩm đã bị xoá/đổi tên (tam-… → UID) nhưng index còn giữ
  return tree.tree ? ds.filter((x) => coFile.has(`data/${x.id}/info.json`)) : ds;
}

const TAG_RIENG = ["yeu_thich", "can_dang"];

// ---------- API ----------
async function docBody(req) {
  try { return await req.json(); } catch { return {}; }
}

async function api(req, env, ctx, url) {
  const p = url.pathname;
  const m = req.method;

  if (p === "/api/login" && m === "POST") {
    const { user = "", pass = "" } = await docBody(req);
    const u = dsUser(env)[String(user).trim().toLowerCase()];
    if (!u || !(await kiemMatKhau(String(pass), u.hash))) return loi("Sai tên đăng nhập hoặc mật khẩu", 401);
    const key = String(user).trim().toLowerCase();
    return json({ user: key, ten: u.ten || key }, 200, { "set-cookie": cookiePhien(await taoPhien(env, key), PHIEN_GIAY) });
  }
  if (p === "/api/logout" && m === "POST") return json({ ok: true }, 200, { "set-cookie": cookiePhien("", 0) });

  const phien = await docPhien(env, req);
  if (!phien) return loi("Chưa đăng nhập", 401);
  if (p === "/api/me") return json(phien);

  let v;
  if ((v = p.match(/^\/api\/video\/([^/]+)\/(ds|file|xoa|dy|dyfile)$/))) {
    if (phien.user !== "nhan" && phien.user !== "comeofage") return loi("Không có quyền", 403);
    const id = decodeURIComponent(v[1]), act = v[2];
    if (!RE_ID.test(id)) return loi("ID không hợp lệ");
    if (!env.VIDEO_ORIGIN || !env.VIDEO_KEY) return loi("Chưa cấu hình máy phát video", 503);
    if ((act === "xoa") !== (m === "POST")) return loi("Sai phương thức", 405);
    let r;
    try {
      r = await fetch(`${env.VIDEO_ORIGIN}/v/${id}/${act}${url.search}`, { method: m, headers: { "x-key": env.VIDEO_KEY, ...(req.headers.get("range") ? { range: req.headers.get("range") } : {}) } });
    } catch { return loi("Máy nhà không trả lời (đã bật video_server và tunnel chưa?)", 502); }
    const h = new Headers({ "content-type": r.headers.get("content-type") || "application/octet-stream", "cache-control": "no-store" });
    for (const k of ["content-length", "content-disposition", "content-range", "accept-ranges"]) if (r.headers.get(k)) h.set(k, r.headers.get(k));
    return new Response(r.body, { status: r.status, headers: h });
  }

  if (p === "/api/ds" && m === "GET") return json({ san_pham: await danhSach(env) });

  let k;
  if ((k = p.match(/^\/api\/sp\/([^/]+)$/)) && m === "GET") {
    const id = decodeURIComponent(k[1]);
    if (!RE_ID.test(id)) return loi("ID không hợp lệ");
    const [infoT, md, caps, vtkT, douyin] = await Promise.all(["info.json", "bo-canh-quay.md", "captions.txt", "video_tk.json", "douyin.md"].map((f) => getText(env, `data/${id}/${f}`)));
    if (!infoT) return loi("Không tìm thấy sản phẩm", 404);
    return json({ info: JSON.parse(infoT), md, caps, douyin, vtk: vtkT ? JSON.parse(vtkT).videos || [] : [] });
  }

  if ((k = p.match(/^\/api\/vtk\/([^/]+)\/([^/]+)$/)) && m === "GET") {
    const id = decodeURIComponent(k[1]), vid = decodeURIComponent(k[2]);
    if (!RE_ID.test(id) || !RE_VID.test(vid)) return loi("ID không hợp lệ");
    const t = await getText(env, `data/${id}/video_tk/${vid}.json`);
    return t ? json(JSON.parse(t)) : loi("Video này chưa được phân tích", 404);
  }

  if (p === "/api/vtk" && m === "POST") {
    const { id, link: linkVao = "", ghi_chu = "" } = await docBody(req);
    const link = String(linkVao).trim();
    if (!RE_ID.test(String(id))) return loi("ID không hợp lệ");
    if (!/^https?:\/\/\S+$/i.test(link) || link.length > 1000) return loi("Không thấy link video hợp lệ");
    if (String(ghi_chu).length > 2000) return loi("Ghi chú quá dài");
    if (!(await getText(env, `data/${id}/info.json`))) return loi("Không tìm thấy sản phẩm", 404);
    const v = { vid: taoVid(), link, ghi_chu: String(ghi_chu).trim(), them_boi: phien.ten, them_luc: nowIso(), trang_thai: "cho" };
    const d = await suaJson(env, `data/${id}/video_tk.json`, (x) => {
      x.videos = x.videos || [];
      if (x.videos.some((o) => o.link === link)) return "Video này đã có trong danh sách";
      x.videos.push(v);
    }, `Video tham khảo ${id} — ${phien.ten}`, VTK_RONG);
    return json({ vtk: d.videos });
  }

  if (p === "/api/vtk-xoa" && m === "POST") {
    const { id, vid } = await docBody(req);
    if (!RE_ID.test(String(id)) || !RE_VID.test(String(vid))) return loi("ID không hợp lệ");
    const d = await suaJson(env, `data/${id}/video_tk.json`, (x) => {
      const truoc = (x.videos || []).length;
      x.videos = (x.videos || []).filter((o) => o.vid !== vid);
      if (x.videos.length === truoc) return "Video không còn trong danh sách";
    }, `Xoá video tham khảo ${vid} ${id} — ${phien.ten}`);
    return json({ vtk: d.videos });
  }

  // /api/anh/<id>/<file> hoặc /api/anh/<id>/video_tk/<vid>/<file>
  if ((k = p.match(/^\/api\/anh\/([^/]+)\/(?:video_tk\/([^/]+)\/)?([^/]+)$/)) && m === "GET") {
    const id = decodeURIComponent(k[1]), vid = k[2] && decodeURIComponent(k[2]), ten = decodeURIComponent(k[3]);
    if (!RE_ID.test(id) || !RE_ANH.test(ten) || (vid !== undefined && !RE_VID.test(vid))) return loi("Đường dẫn ảnh không hợp lệ");
    const file = vid ? `video_tk/${vid}/${ten}` : ten;
    const cache = caches.default;
    const key = new Request(url.toString(), { method: "GET" }); // ?v=cap_nhat_luc → ảnh đổi thì khoá đổi
    let r = await cache.match(key);
    if (!r) {
      const g = await gh(env, `/contents/data/${id}/${file}?ref=${nhanh(env)}`, { headers: { Accept: "application/vnd.github.raw+json" } });
      if (!g.ok) return new Response("", { status: g.status === 404 ? 404 : 502 });
      const loaiAnh = /\.png$/i.test(file) ? "image/png" : /\.webp$/i.test(file) ? "image/webp" : "image/jpeg";
      r = new Response(g.body, { headers: { "content-type": loaiAnh, "cache-control": "private, max-age=86400" } });
      ctx.waitUntil(cache.put(key, r.clone()));
    }
    return r;
  }

  if (p === "/api/them" && m === "POST") {
    const link = String((await docBody(req)).link || "").trim();
    if (!/^https?:\/\/\S+$/i.test(link) && !/^\d{15,21}$/.test(link)) return loi("Không thấy link hợp lệ");
    const uid = tachUid(link);
    const ds = await danhSach(env);
    const trung = ds.find((x) => (uid && x.uid === uid) || x.link === link);
    if (trung) return json({ trung: true, id: trung.id, trang_thai: trung.trang_thai || trangThai(trung) }, 409);
    const t = nowIso();
    const id = uid || "tam-" + t.replace(/\D/g, "").slice(0, 14) + String(Date.now() % 1000).padStart(3, "0");
    const info = {
      id, uid, link, ten: "", gia: "", shop: "", anh_bia: "", tom_tat: "", usp: null, ghi_chu: "", thu_muc_may: "",
      them_boi: phien.ten, them_luc: t, da_phan_tich: false,
      da_quay_oneshot: { xong: false, boi: "", luc: "" }, da_quay_review: { xong: false, boi: "", luc: "" },
      da_lam_video: { xong: false, so_video: 0, luc: "" }, cap_nhat_luc: t,
    };
    const r = await putFile(env, `data/${id}/info.json`, JSON.stringify(info, null, 1) + "\n", null, `Thêm ${id} — ${phien.ten}`);
    if (r.conflict) return json({ trung: true, id }, 409);
    return json({ info: { ...info, trang_thai: "cho" } });
  }

  if (p === "/api/quay" && m === "POST") {
    const { id, loai, xong } = await docBody(req);
    if (!RE_ID.test(String(id)) || !LOAI_QUAY.includes(loai)) return loi("Dữ liệu không hợp lệ");
    const info = await updateInfo(env, id, (i) => {
      i[`da_quay_${loai}`] = { xong: !!xong, boi: phien.ten, luc: nowIso() };
      if (i.da_quay) { // chuyển dữ liệu cũ 1 nút sang review rồi bỏ
        if (!i.da_quay_review) i.da_quay_review = i.da_quay;
        delete i.da_quay;
      }
    }, `${xong ? "Đã quay" : "Bỏ đã quay"} ${loai} ${id} — ${phien.ten}`);
    return json({ info: { ...info, trang_thai: trangThai(info) } });
  }

  if (p === "/api/tag" && m === "POST") { // thẻ riêng: yêu thích / cần đăng
    const { id, tag, bat } = await docBody(req);
    if (!RE_ID.test(String(id)) || !TAG_RIENG.includes(tag)) return loi("Dữ liệu không hợp lệ");
    const info = await updateInfo(env, id, (i) => { if (bat) i[tag] = true; else delete i[tag]; }, `${bat ? "Gắn" : "Bỏ"} thẻ ${tag} ${id} — ${phien.ten}`);
    return json({ info: { ...info, trang_thai: trangThai(info) } });
  }

  if (p === "/api/ghichu" && m === "POST") {
    const { id, ghi_chu = "" } = await docBody(req);
    if (!RE_ID.test(String(id))) return loi("ID không hợp lệ");
    if (String(ghi_chu).length > 20000) return loi("Ghi chú quá dài");
    const info = await updateInfo(env, id, (i) => { i.ghi_chu = String(ghi_chu); }, `Ghi chú ${id} — ${phien.ten}`);
    return json({ info });
  }

  return loi("Không có API này", 404);
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(req);
    // Chặn POST từ trang khác (ngoài SameSite=Lax của cookie).
    if (req.method !== "GET") {
      const o = req.headers.get("origin");
      if (o && o !== url.origin) return loi("Sai nguồn gọi", 403);
    }
    try {
      return await api(req, env, ctx, url);
    } catch (e) {
      if (!e.status || e.status >= 500) console.error(e);
      return loi(e.message || "Lỗi máy chủ", e.status || 500);
    }
  },
};
