// Kho sản phẩm — Cloudflare Worker: đăng nhập user/pass + API đọc/ghi repo GitHub (dữ liệu vẫn ở data/<id>/).
// Token GitHub chỉ nằm trong secret GITHUB_TOKEN của Worker; trình duyệt chỉ cầm cookie phiên.
// Secret: GITHUB_TOKEN, SESSION_SECRET, USERS (JSON do cf/tools/tao-users.mjs sinh). Biến: GH_REPO, GH_BRANCH.
// Máy nhà: VIDEO_ORIGIN, VIDEO_KEY; bộ chạy việc thêm RUNNER_KEY, KY_RIENG (xem docs/bo-chay-viec.md §8.3).
// KV SO_DUYET (D9): sổ lời duyệt đã tiêu (tieu:<sha256hex 64 byte chu_ky_duyet dạng chuẩn>, không TTL) + đếm sai mật khẩu duyệt (sai:<user>).
"use strict";
import { apiPoster } from "./poster.js";

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

const TAG_RIENG = ["yeu_thich", "can_dang", "ngung_dang"];

// ---------- máy nhà (video_server qua tunnel) ----------
const USER_MAY_NHA = ["nhan", "comeofage"];
const laChuKho = (user) => USER_MAY_NHA.includes(user);
// P-33: người không phải chủ kho không thấy trường nội bộ máy nhà (đường dẫn ổ đĩa) trong info trả về.
// Hàm thuần: không sửa đối tượng gốc; chủ kho nhận nguyên đối tượng. Giữ xong/so_video/luc/nhan/folder để web hiện trạng thái.
export function anTruongNoiBo(info, laChu) {
  if (laChu || !laObjectThuong(info)) return info;
  const { thu_muc_may, ...ra } = info; // eslint-disable-line no-unused-vars
  const dlv = info.da_lam_video;
  if (laObjectThuong(dlv)) {
    const { duong_dan, poster_folder, ...gon } = dlv; // eslint-disable-line no-unused-vars
    if (Array.isArray(dlv.poster)) {
      gon.poster = dlv.poster.map((p) => {
        if (!laObjectThuong(p)) return p;
        const { duong_dan: _bo, ...q } = p; // eslint-disable-line no-unused-vars
        return q;
      });
    }
    ra.da_lam_video = gon;
  }
  // ghi_chu giữ nguyên: người thường sửa được ghi chú — che ở đây thì bấm Lưu sẽ ghi bản đã che đè lên bản gốc.
  const daChe = cheSau(ra);
  if (Object.prototype.hasOwnProperty.call(ra, "ghi_chu")) daChe.ghi_chu = ra.ghi_chu;
  return daChe;
}
// P-33b: che đường dẫn tuyệt đối máy nhà trong chữ cho người thường. Ổ đĩa Windows "X:\…"/"X:/…" (chữ ổ không đứng sau
// chữ/số/"/" → không bắt "https://", "…/c:d") và UNC "\\máy\…"; dừng ở khoảng trắng, ngoặc, backtick, nháy, "|" (bảng markdown
// không vỡ); dấu câu cuối (.,;:!?) trả lại sau chỗ che. Chỉ thay đoạn đường dẫn, giữ phần chữ còn lại của dòng.
const CHE_DUONG_DAN = "[đường dẫn máy nhà]";
// "file:///X:/…" (link markdown trong douyin.md) che cả tiền tố.
const RE_DUONG_DAN = /(?:\bfile:\/{2,3}|(?<![A-Za-z0-9/\\]))[A-Za-z]:[\\/][^\s()[\]{}<>`"'|]*|(?<![\\\w])\\\\[^\s\\()[\]{}<>`"'|]+\\[^\s()[\]{}<>`"'|]*/g;
export function cheDuongDan(text) {
  if (typeof text !== "string" || !text) return text;
  return text.replace(RE_DUONG_DAN, (m) => CHE_DUONG_DAN + (m.match(/[.,;:!?]+$/) || [""])[0]);
}
// Che trong mọi chuỗi của giá trị JSON (lồng nhau); trả bản mới, không sửa gốc.
function cheSau(o) {
  if (typeof o === "string") return cheDuongDan(o);
  if (Array.isArray(o)) return o.map(cheSau);
  if (laObjectThuong(o)) return Object.fromEntries(Object.entries(o).map(([k, v]) => [k, cheSau(v)]));
  return o;
}
const GOI_Y_MAY_NHA = "(đã bật video_server và tunnel chưa?)";
const LOI_MAY_NHA = `Máy nhà không trả lời ${GOI_Y_MAY_NHA}`;
// Máy nhà trả 401/403 khi x-key lệch: KHÔNG chuyển nguyên về trình duyệt (web hiểu 401 = hết phiên đăng nhập).
const LOI_KHOA_MAY_NHA = "Máy nhà từ chối khoá (VIDEO_KEY lệch với tools/.video_key)";
const LOI_CHAM_MAY_NHA = "Máy nhà phản hồi quá chậm";
// act trả JSON/ảnh nhỏ → có timeout; file/xem/dyfile/xoa/clip là stream dài → không đặt.
const ACT_CO_TIMEOUT = ["ds", "dy", "tien-do", "anh"];
const TIMEOUT_VIDEO_MS = 15000;
const laHetGio = (e) => !!e && (e.name === "TimeoutError" || e.name === "AbortError");
// Khoá query được chuyển sang máy nhà theo act; mọi khoá khác bị bỏ. anh/clip: ảnh khung + xem thử clip (docs/sua-video.md §8.2–§8.3).
const QUERY_VIDEO = {
  ds: [], dy: [], "tien-do": [], file: ["ten", "goc", "xoa"], xem: ["ten", "goc"], dyfile: ["ten"], xoa: ["ten", "goc"],
  anh: ["du_an", "ten", "k"], clip: ["du_an", "ten"],
};
// xoa=1 (tải xong thì xoá ở máy nhà) chỉ nhận khi trình duyệt báo request đến từ chính trang này:
// cookie SameSite=Lax vẫn đi theo điều hướng GET từ trang khác, nên không có header này → chỉ tải, không xoá.
function queryVideo(act, src, secFetchSite) {
  const q = new URLSearchParams();
  for (const k of QUERY_VIDEO[act] || []) {
    if (!src.has(k)) continue;
    const val = src.get(k);
    if (k === "xoa" && !(val === "1" && secFetchSite === "same-origin")) continue;
    q.set(k, val);
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

// Duyệt video: data/<id>/duyet.json, mỗi mục khoá theo (goc, ten, sua_luc).
const DUYET_RONG = { videos: [] };
const KET_QUA = ["dat", "loai", ""];
function kiemDuyet(b) {
  const { id, goc, ten, sua_luc, mb = 0, ket_qua, gop_y = "" } = b || {};
  if (!RE_ID.test(String(id))) return "ID không hợp lệ";
  if (typeof goc !== "string" || goc.length < 1 || goc.length > 300) return "Thư mục gốc không hợp lệ";
  if (typeof ten !== "string" || ten.length < 1 || ten.length > 200 || /[/\\]/.test(ten)) return "Tên video không hợp lệ";
  if (!Number.isInteger(sua_luc) || sua_luc < 0) return "Thời điểm sửa không hợp lệ";
  if (typeof mb !== "number" || !Number.isFinite(mb) || mb < 0) return "Dung lượng không hợp lệ";
  if (!KET_QUA.includes(ket_qua)) return "Kết quả duyệt không hợp lệ";
  if (typeof gop_y !== "string" || gop_y.length > 2000) return "Góp ý không hợp lệ hoặc quá dài";
  return { id, goc, ten, sua_luc, mb, ket_qua, gop_y: gop_y.trim() };
}

// ---------- bộ chạy việc: Worker → video_server /r/* → runner (docs/bo-chay-viec.md §3.3, §8.2, §8.3) ----------
// Secret thêm: RUNNER_KEY (x-runner-key), KY_RIENG (khoá riêng Ed25519, PKCS8 DER base64 hoặc JWK).
const LOI_KHOA_RUNNER = "Máy nhà từ chối khoá/chữ ký bộ chạy việc";
const TIMEOUT_VIEC_MS = 20000; // video_server chờ runner 10 s
const BODY_VIEC_TOI_DA = 16 * 1024; // khớp giới hạn của video_server (§3.2)
const TRA_LOI_TOI_DA = 120;
const RE_LOAI = /^[a-z_]{3,30}$/;
const RE_GIA_TRI_QUERY = /^[A-Za-z0-9_,-]{0,40}$/;
const RE_KY_TU_DIEU_KHIEN = /[\u0000-\u001f\u007f]/;
const THAM_SO_TOI_DA = 10;
const KIEM_THAM_SO = {
  uid: (v) => typeof v === "string" && /^\d{19}$/.test(v),
  du_an: (v) => typeof v === "string" && /^[0-9a-f]{12}$/.test(v),
  me: (v) => typeof v === "string" && /^\d{8}-[a-z0-9]{1,12}$/.test(v),
  top_n: (v) => Number.isInteger(v) && v >= 5 && v <= 30,
  chay_bu: (v) => typeof v === "boolean",
  // đợt 4 (§5.2) — khớp tools/runner/danh_muc.py: MAU_PROMPT_MUSE, MUSE_THOI_LUONG, MUSE_TI_LE, POSTER_VIDEO_NGAY
  mau: (v) => Array.isArray(v) && v.length >= 1 && v.length <= MA_MAU_MUSE.length && new Set(v).size === v.length
    && v.every((x) => typeof x === "string" && MA_MAU_MUSE.includes(x)),
  thoi_luong: (v) => v === 10 || v === 15,
  ti_le: (v) => v === "9:16",
  folder_id: (v) => Number.isInteger(v) && v > 0 && v < 1e9,
  so_video_ngay: (v) => Number.isInteger(v) && v >= 1 && v <= 100, // FX-9: người dùng nới 1–5 → 1–100
  // đợt 6 (docs/sua-video.md §7.1): hoan_tac_sua
  ma_video: (v) => typeof v === "string" && RE_MA_VIDEO.test(v),
  viec_goc: (v) => typeof v === "string" && RE_ID_VIEC.test(v),
  // đợt 5 (§7.10): taovideo — runner kiểm lại đầy đủ (raw/, takes/, chốt B khi tu_tim)
  du_an_a: (v) => typeof v === "string" && /^[0-9a-f]{12}$/.test(v),
  du_an_b: (v) => typeof v === "string" && (v === "tu_tim" || /^[0-9a-f]{12}$/.test(v)),
  wm: (v) => typeof v === "string" && WM_TAOVIDEO.includes(v),
  gia: (v) => Number.isInteger(v) && v >= 1000 && v <= 10_000_000,
};
// Watermark cho phép (phiếu W-6; khớp ("khong", *WM_CHO_PHEP) của tools/runner/han_muc.py).
const WM_TAOVIDEO = ["khong", "nha.cua.mit"];
const RE_MA_VIDEO = /^[0-9a-f]{16}$/;
// Mã mẫu prompt Muse cố định (web chỉ gửi MÃ). Phải trùng khoá MAU_PROMPT_MUSE trong tools/runner/danh_muc.py.
const MA_MAU_MUSE = ["xoay_360", "cam_tay", "can_canh", "dung_that", "dat_ban", "mo_hop", "truoc_sau"];
// Danh mục đợt 3 (§5.1) + đợt 4 (§5.2) + đợt 5 taovideo (§7.10): loại → [khoá bắt buộc, khoá tuỳ chọn].
// Runner vẫn chặn theo dot_bat — Worker chỉ kiểm hình dạng.
// voice_genmax: web KHÔNG gửi được ma_ban (runner tự gắn); thoi_luong/ti_le của muse_clip tuỳ chọn (runner có mặc định).
const DANH_MUC_VIEC = new Map([
  ["radar_ban_tin", [[], ["top_n", "chay_bu"]]],
  ["phan_tich_uid", [["uid"], []]],
  ["douyin_uid", [["uid"], []]],
  ["xu_ly_link_moi", [[], []]],
  ["poster_day_folder", [["uid", "du_an"], []]],
  ["poster_bo_loai", [["uid"], []]],
  ["voice_pv", [["uid", "du_an", "me"], []]],
  ["muse_clip", [["uid", "du_an", "mau"], ["thoi_luong", "ti_le"]]],
  ["voice_genmax", [["uid", "du_an", "me"], []]],
  ["poster_len_lich", [["folder_id", "so_video_ngay"], []]],
  // sua_video KHÔNG có ở đây: chỉ tạo qua POST /api/viec/sua-video/<uid>/<ma>/luu (kiểm bản sửa + mật khẩu Q3).
  ["hoan_tac_sua", [["uid", "du_an", "ma_video", "viec_goc"], []]],
  ["taovideo", [["uid", "du_an_a", "du_an_b", "wm"], ["gia"]]],
]);
// Đợt 3: trả lời chỉ bằng nút — giá trị hợp lệ theo loại câu hỏi (cau_hoi chữ tự do là đợt 5).
const NUT_CO_DINH = { viec_tay: ["da_lam_xong"], khong_ro: ["tiep_tuc"] };
const laObjectThuong = (o) => !!o && typeof o === "object" && !Array.isArray(o);
const hexOf = (buf) => [...new Uint8Array(buf)].map((x) => x.toString(16).padStart(2, "0")).join("");

// Trả {loai, tham_so} đã dựng lại (chỉ khoá cho phép) hoặc chuỗi lỗi.
export function kiemThamSoViec(b) {
  if (!laObjectThuong(b)) return "Dữ liệu không hợp lệ";
  const { loai } = b;
  if (typeof loai !== "string" || !RE_LOAI.test(loai) || !DANH_MUC_VIEC.has(loai)) return "Loại việc không có trong danh mục";
  const ts = b.tham_so === undefined ? {} : b.tham_so;
  if (!laObjectThuong(ts)) return "Tham số không hợp lệ";
  const khoa = Object.keys(ts);
  if (khoa.length > THAM_SO_TOI_DA) return "Quá nhiều tham số";
  const [batBuoc, tuyChon] = DANH_MUC_VIEC.get(loai);
  const tham_so = {};
  for (const k of khoa) {
    if (!batBuoc.includes(k) && !tuyChon.includes(k)) return "Tham số không thuộc loại việc này";
    if (!KIEM_THAM_SO[k](ts[k])) return `Tham số ${k} không hợp lệ`;
    tham_so[k] = ts[k];
  }
  for (const k of batBuoc) if (!(k in tham_so)) return `Thiếu tham số ${k}`;
  return { loai, tham_so };
}

// Chuỗi ký request §8.3 — phải khớp byte với tools/runner/chu_ky.py:chuoi_ky_request.
export function chuoiKyRequest(method, path, ngayMs, nonce, shaHex) {
  return te.encode(`kho-runner-v1\n${method}\n${path}\n${ngayMs}\n${nonce}\n${shaHex}`);
}

// Workers không nhận khoá Ed25519 raw → PKCS8 (base64/base64url) hoặc JWK. Cache promise ngay (trước await) theo giá trị secret.
let khoaKyCache = null;
function khoaKy(env) {
  const nguon = String(env.KY_RIENG || "").trim();
  if (khoaKyCache && khoaKyCache.nguon === nguon) return khoaKyCache.hua;
  const hua = (async () => {
    if (nguon.startsWith("{")) return crypto.subtle.importKey("jwk", JSON.parse(nguon), { name: "Ed25519" }, false, ["sign"]);
    const der = unb64url(nguon.replace(/\s+/g, "").replace(/=+$/, ""));
    return crypto.subtle.importKey("pkcs8", der, { name: "Ed25519" }, false, ["sign"]);
  })();
  khoaKyCache = { nguon, hua };
  hua.catch(() => { if (khoaKyCache && khoaKyCache.hua === hua) khoaKyCache = null; });
  return hua;
}

// Header ký cho request ghi: x-ky-ngay, x-ky-nonce, x-ky. path = path runner (không tiền tố /r, không query).
export async function kyRequest(env, method, path, bodyText = "") {
  let khoa;
  try {
    khoa = await khoaKy(env);
  } catch (e) {
    console.error("viec: không nạp được KY_RIENG", e && e.name);
    throw Object.assign(new Error("Khoá ký bộ chạy việc không hợp lệ (KY_RIENG)"), { status: 503 });
  }
  const ngay = Date.now();
  const nonce = hexOf(crypto.getRandomValues(new Uint8Array(16)));
  const sha = hexOf(await crypto.subtle.digest("SHA-256", te.encode(bodyText)));
  const ky = await crypto.subtle.sign({ name: "Ed25519" }, khoa, chuoiKyRequest(method, path, ngay, nonce, sha));
  return { "x-ky-ngay": String(ngay), "x-ky-nonce": nonce, "x-ky": b64url(ky) };
}

// Chuỗi ký lời duyệt §8.3 — phải khớp byte với tools/runner/chu_ky.py:chuoi_ky_duyet.
// thamSoChuan là NGUYÊN CHUỖI runner trả ở GET /viec/<id> (không stringify lại); thamSoChuan + loiDuyet chỉ vào chuỗi
// dưới dạng sha256 nên được chứa xuống dòng; các trường còn lại thì không.
const truongKy = (ten, v) => {
  if (typeof v !== "string") throw new TypeError(`${ten} phải là chuỗi`);
  if (/[\r\n]/.test(v)) throw new TypeError(`${ten} chứa ký tự xuống dòng`);
  return v;
};
const sha256HexText = async (s) => hexOf(await crypto.subtle.digest("SHA-256", te.encode(s)));
export async function chuoiKyDuyet(id, loai, thamSoChuan, loiDuyet, duyetLuc, boi) {
  for (const [ten, v] of [["tham_so_chuan", thamSoChuan], ["loi_duyet", loiDuyet]]) if (typeof v !== "string") throw new TypeError(`${ten} phải là chuỗi`);
  const phan = [truongKy("id", id), truongKy("loai", loai), await sha256HexText(thamSoChuan), await sha256HexText(loiDuyet), truongKy("duyet_luc", duyetLuc), truongKy("boi", boi)];
  return te.encode(["kho-duyet-v1", ...phan].join("\n"));
}
// chu_ky_duyet (base64url không padding, 86 ký tự) bằng KY_RIENG.
export async function kyDuyet(env, id, loai, thamSoChuan, loiDuyet, duyetLuc, boi) {
  const chuoi = await chuoiKyDuyet(id, loai, thamSoChuan, loiDuyet, duyetLuc, boi);
  let khoa;
  try {
    khoa = await khoaKy(env);
  } catch (e) {
    console.error("viec: không nạp được KY_RIENG", e && e.name);
    throw Object.assign(new Error("Khoá ký bộ chạy việc không hợp lệ (KY_RIENG)"), { status: 503 });
  }
  return b64url(await crypto.subtle.sign({ name: "Ed25519" }, khoa, chuoi));
}

// ---------- sổ "lời duyệt đã tiêu" (D9): runner → POST /api/runner/tieu-duyet, KV SO_DUYET ----------
// Mỗi chu_ky_duyet chỉ tiêu được 1 lần; Worker ký xác nhận kho-tieu-v1 để runner biết lời duyệt chưa bị dùng.
const RE_ID_VIEC = /^j\d{14}[a-z0-9]{4}$/; // cùng mẫu id việc ở tuyenViec
const RE_CHU_KY_DUYET = /^[A-Za-z0-9_-]{86}$/;
const RE_NONCE_TIEU = /^[0-9a-f]{32}$/;
const TIEU_BO_NHO_TOI_DA = 5000;
// Khoá tieu: đã/đang tiêu trong isolate này → luc — giữ chỗ ĐỒNG BỘ trước await KV (request song song cùng isolate không lọt).
const soTieuBoNho = new Map();
export function datLaiSoTieuBoNho() { soTieuBoNho.clear(); } // test: giả lập isolate mới
// [FX-17 P1-1] chu_ky_duyet phải ở DẠNG CHUẨN: giải ra đúng 64 byte, mã hoá lại phải đúng chuỗi gốc
// (86 ký tự chứa 4 bit thừa ở ký tự cuối → 16 chuỗi cùng 64 byte). Không chuẩn → null.
function giaiChuKyChuan(s) {
  if (typeof s !== "string" || !RE_CHU_KY_DUYET.test(s)) return null;
  let byte;
  try { byte = unb64url(s); } catch { return null; }
  return byte.length === 64 && b64url(byte) === s ? byte : null;
}
function lucTrongSo(v) {
  try {
    const d = JSON.parse(v);
    return laObjectThuong(d) && typeof d.luc === "string" ? d.luc : null;
  } catch { return null; }
}
const loiDaDung = (luc) => json({ loi: "Lời duyệt đã dùng", luc: luc ?? null }, 409);

// Chuỗi ký tiêu duyệt — UTF-8 "kho-tieu-v1\n"+id+"\n"+sha256hex(chu_ky_duyet)+"\n"+nonce.
export async function chuoiTieuDuyet(id, chuKyDuyet, nonce) {
  if (typeof chuKyDuyet !== "string") throw new TypeError("chu_ky_duyet phải là chuỗi");
  return te.encode(`kho-tieu-v1\n${truongKy("id", id)}\n${await sha256HexText(chuKyDuyet)}\n${truongKy("nonce", nonce)}`);
}
export async function kyTieuDuyet(env, id, chuKyDuyet, nonce) {
  const chuoi = await chuoiTieuDuyet(id, chuKyDuyet, nonce);
  let khoa;
  try {
    khoa = await khoaKy(env);
  } catch (e) {
    console.error("tieu-duyet: không nạp được KY_RIENG", e && e.name);
    throw Object.assign(new Error("Khoá ký bộ chạy việc không hợp lệ (KY_RIENG)"), { status: 503 });
  }
  return b64url(await crypto.subtle.sign({ name: "Ed25519" }, khoa, chuoi));
}
// So khoá hằng thời gian kể cả khi độ dài khác: so sha256 (cùng 64 ký tự).
async function khoaKhop(a, b) {
  const [x, y] = await Promise.all([sha256HexText(a), sha256HexText(b)]);
  return bangNhau(x, y);
}

async function tieuDuyet(req, env) {
  if (!env.RUNNER_KEY || !env.KY_RIENG || !env.SO_DUYET) return loi("Chưa cấu hình sổ duyệt", 503);
  const khoaGui = req.headers.get("x-runner-key");
  if (!khoaGui || !(await khoaKhop(khoaGui, String(env.RUNNER_KEY)))) return loi("Sai khoá bộ chạy việc", 401);
  const b = await docBodyViec(req);
  const { id, chu_ky_duyet, nonce } = laObjectThuong(b) ? b : {};
  const byteKy = giaiChuKyChuan(chu_ky_duyet);
  if (typeof id !== "string" || !RE_ID_VIEC.test(id) || !byteKy || typeof nonce !== "string" || !RE_NONCE_TIEU.test(nonce)) {
    return loi("Dữ liệu tiêu duyệt không hợp lệ");
  }
  const khoa = `tieu:${hexOf(await crypto.subtle.digest("SHA-256", byteKy))}`; // băm 64 BYTE, không băm chuỗi
  const ky = await kyTieuDuyet(env, id, chu_ky_duyet, nonce); // KY_RIENG hỏng → 503 TRƯỚC khi tiêu
  // --- đoạn đồng bộ: kiểm + giữ chỗ trong isolate (không await ở giữa) ---
  if (soTieuBoNho.has(khoa)) return loiDaDung(soTieuBoNho.get(khoa));
  const luc = nowIso();
  soTieuBoNho.set(khoa, luc);
  if (soTieuBoNho.size > TIEU_BO_NHO_TOI_DA) soTieuBoNho.delete(soTieuBoNho.keys().next().value);
  // --- hết đoạn đồng bộ ---
  try {
    const cu = await env.SO_DUYET.get(khoa);
    if (cu !== null) {
      const lucDau = lucTrongSo(cu);
      if (soTieuBoNho.has(khoa)) soTieuBoNho.set(khoa, lucDau); // vẫn giữ chỗ, chỉ cập nhật luc thật từ sổ
      return loiDaDung(lucDau);
    }
    await env.SO_DUYET.put(khoa, JSON.stringify({ id, luc })); // §8.3: sổ tiêu KHÔNG đặt TTL
  } catch (e) {
    soTieuBoNho.delete(khoa); // chưa tiêu được → nhả chỗ cho lần thử lại
    console.error("tieu-duyet: KV SO_DUYET lỗi", e && e.name);
    return loi("Sổ duyệt tạm lỗi — thử lại", 503);
  }
  return json({ ky });
}

// Gọi runner qua video_server. Luôn trả Response: của máy nhà, hoặc lỗi 502/504 đã đổi (401/403 → 502).
async function goiMayNha(env, path, { method = "GET", body, timeoutMs = TIMEOUT_VIEC_MS } = {}) {
  const headers = { "x-key": env.VIDEO_KEY, "x-runner-key": env.RUNNER_KEY };
  let bodyText;
  if (method === "POST") {
    bodyText = JSON.stringify(body === undefined ? {} : body);
    Object.assign(headers, { "content-type": "application/json" }, await kyRequest(env, method, path.split("?")[0], bodyText));
  }
  let r;
  try {
    r = await fetch(`${env.VIDEO_ORIGIN}/r${path}`, { method, headers, body: bodyText, signal: AbortSignal.timeout(timeoutMs) });
  } catch (e) {
    console.error(`viec ${method} ${path}: máy nhà lỗi`, e);
    return laHetGio(e) ? loi(LOI_CHAM_MAY_NHA, 504) : loi(LOI_MAY_NHA, 502);
  }
  if (r.status === 401 || r.status === 403) {
    console.error(`viec ${method} ${path}: máy nhà trả ${r.status} — RUNNER_KEY/VIDEO_KEY/khoá ký lệch`);
    if (r.body) r.body.cancel().catch(() => {});
    return loi(LOI_KHOA_RUNNER, 502);
  }
  return r;
}
const traVeMayNha = (r) =>
  new Response(r.body, { status: r.status, headers: { "content-type": r.headers.get("content-type") || "application/json; charset=utf-8", "cache-control": "no-store" } });

function queryViec(src, khoaChoPhep, mauRieng = {}) {
  const q = new URLSearchParams();
  for (const k of khoaChoPhep) {
    if (!src.has(k)) continue;
    const v = src.get(k);
    if (!(mauRieng[k] || RE_GIA_TRI_QUERY).test(v)) return null;
    q.set(k, v);
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

// Bảng route: path web → {METHOD: {dich (path runner), query?, lam?}}. Không khớp → null (404).
function tuyenViec(p) {
  const s = p.slice("/api/viec".length);
  let k;
  if (s === "") return { GET: { dich: "/viec", query: ["trang_thai", "uid", "gioi_han", "tom_tat"] }, POST: { dich: "/viec", lam: "tao" } };
  if (s === "/danh-muc") return { GET: { dich: "/danh-muc" } };
  if (s === "/suc-khoe") return { GET: { dich: "/suc-khoe" } };
  if (s === "/poster-folders" || s === "/poster/folders") return { GET: { dich: "/poster/folders" } };
  if ((k = s.match(/^\/du-an\/(\d{19})$/))) return { GET: { dich: `/du-an/${k[1]}` } };
  // Sửa video (docs/sua-video.md §8.3): đọc qua GET; ghi chỉ qua /luu (ban-sua của runner không mở thẳng ra web).
  if ((k = s.match(/^\/sua-video\/(\d{19})(?:\/([0-9a-f]{16})(?:\/(ung-vien|luu))?)?$/))) {
    const [, uid, ma, act] = k;
    if (!ma) return { GET: { dich: `/sua-video/${uid}` } };
    if (!act) return { GET: { dich: `/sua-video/${uid}/${ma}` } };
    if (act === "ung-vien") return { GET: { dich: `/sua-video/${uid}/${ma}/ung-vien`, query: ["seg"], mau: { seg: /^\d{1,3}$/ } } };
    return { POST: { dich: `/sua-video/${uid}/${ma}/ban-sua`, lam: "sua_video", uid, ma } };
  }
  if ((k = s.match(/^\/(j\d{14}[a-z0-9]{4})(?:\/(log|tra-loi|duyet|tu-choi|huy|chay-tiep|chay-lai|xin-duyet-lai))?$/))) {
    const [, id, act] = k;
    if (!act) return { GET: { dich: `/viec/${id}` } };
    if (act === "log") return { GET: { dich: `/viec/${id}/log`, query: ["tu"] } };
    return { POST: { dich: `/viec/${id}/${act}`, lam: act === "tra-loi" ? "tra_loi" : act === "duyet" ? "duyet" : "boi", id } };
  }
  return null;
}

async function docBodyViec(req) {
  if (Number(req.headers.get("content-length") || 0) > BODY_VIEC_TOI_DA) throw Object.assign(new Error("Dữ liệu quá lớn"), { status: 413 });
  const t = await req.text();
  if (te.encode(t).length > BODY_VIEC_TOI_DA) throw Object.assign(new Error("Dữ liệu quá lớn"), { status: 413 });
  if (!t.trim()) return {};
  try { return JSON.parse(t); } catch { throw Object.assign(new Error("Dữ liệu không phải JSON"), { status: 400 }); }
}

// Giá trị nút hợp lệ cho câu hỏi đang chờ; null = không trả lời bằng nút được (đợt 3).
function giaTriNut(cauHoi) {
  if (!laObjectThuong(cauHoi)) return null;
  if (cauHoi.loai === "chon") return Array.isArray(cauHoi.lua_chon) ? cauHoi.lua_chon.filter((x) => typeof x === "string") : null;
  return NUT_CO_DINH[cauHoi.loai] || null;
}

// Trả lời câu hỏi đang chờ (§7.6, §8.2, §9 mục 4). Body web {tra_loi, ma_cau_hoi?, mat_khau?}; body tới runner {tra_loi, boi, da_xac_nhan_mat_khau, ma_cau_hoi?}.
// - ma_cau_hoi (FX-25): tuỳ chọn; có thì phải khớp RE_MA_CAU_HOI (sai → 400 trước mọi bước khác, không gọi máy nhà), chuyển nguyên sang runner (runner so với cau_hoi.ma, lệch → 409).
// - Không mật khẩu: chỉ giá trị nút (≤120 ký tự, không ký tự điều khiển).
// - Có mật khẩu: kiểm + đếm sai (KV sai:<user>) TRƯỚC khi gọi máy nhà; chữ 1–1000 code point (cho phép xuống dòng).
// - Phiên sống (viec.phien_song === true): chon/cau_hoi bắt buộc mật khẩu; viec_tay/khong_ro chỉ nút.
// - cau_hoi (chữ tự do) chỉ khi có phiên sống. Cờ da_xac_nhan_mat_khau do Worker đặt, không lấy từ client.
const TRA_LOI_CHU_TOI_DA = 1000; // code point — khớp runner kiem_tra_loi_dot5 (§7.6)
const RE_DIEU_KHIEN_TRU_XUONG_DONG = /[\u0000-\u0009\u000b-\u001f\u007f]/;
const RE_MA_CAU_HOI = /^q[0-9a-f]{12}$/; // khớp runner kieu.RE_MA_CAU_HOI (§7.6)
async function traLoiViec(req, env, tuyen, phien) {
  const b = await docBodyViec(req);
  const { tra_loi, mat_khau, ma_cau_hoi } = laObjectThuong(b) ? b : {};
  const coMa = ma_cau_hoi !== undefined;
  if (coMa && (typeof ma_cau_hoi !== "string" || !RE_MA_CAU_HOI.test(ma_cau_hoi))) return loi("Mã câu hỏi không hợp lệ");
  const coMk = mat_khau !== undefined;
  if (coMk && (typeof mat_khau !== "string" || !mat_khau || mat_khau.length > MAT_KHAU_TOI_DA)) return loi("Mật khẩu không hợp lệ");
  if (typeof tra_loi !== "string" || !tra_loi.trim() || RE_SURROGATE_LE.test(tra_loi)) return loi("Câu trả lời không hợp lệ");
  if (coMk) {
    if ([...tra_loi].length > TRA_LOI_CHU_TOI_DA || RE_DIEU_KHIEN_TRU_XUONG_DONG.test(tra_loi)) return loi(`Câu trả lời phải dài 1–${TRA_LOI_CHU_TOI_DA} ký tự, không có ký tự điều khiển`);
  } else if (tra_loi.length > TRA_LOI_TOI_DA || RE_KY_TU_DIEU_KHIEN.test(tra_loi)) {
    return loi("Câu trả lời không hợp lệ");
  }
  let daXacNhan = false;
  if (coMk) {
    const loiMk = await kiemMatKhauCoDem(env, phien.user, mat_khau);
    if (loiMk) return loiMk;
    daXacNhan = true;
  }
  const r = await goiMayNha(env, `/viec/${tuyen.id}`);
  if (!r.ok) return traVeMayNha(r);
  let d;
  try { d = await r.json(); } catch { return loi("Máy nhà trả dữ liệu lạ", 502); }
  const viec = laObjectThuong(d) ? d.viec : null;
  if (!laObjectThuong(viec) || viec.trang_thai !== "can_tra_loi") return loi("Việc không còn chờ trả lời", 409);
  let cauHoi = viec.cau_hoi;
  if (typeof cauHoi === "string") { try { cauHoi = JSON.parse(cauHoi); } catch { cauHoi = null; } }
  if (!laObjectThuong(cauHoi)) return loi("Việc không còn chờ trả lời", 409);
  const phienSong = viec.phien_song === true;
  if (cauHoi.loai === "cau_hoi") {
    if (!phienSong) return loi("Câu hỏi này chưa trả lời được trên web (chỉ trả lời chữ khi việc có phiên sống)");
    if (!daXacNhan) return loi("Trả lời bằng chữ cần nhập mật khẩu", 403);
  } else {
    const nut = giaTriNut(cauHoi);
    if (!nut) return loi("Câu hỏi này chưa trả lời được trên web");
    if (!nut.includes(tra_loi)) return loi("Câu trả lời không khớp nút nào của câu hỏi");
    if (phienSong && cauHoi.loai === "chon" && !daXacNhan) return loi("Chọn trong phiên đang chạy cần nhập mật khẩu", 403);
  }
  return traVeMayNha(await goiMayNha(env, tuyen.dich, { method: "POST", body: { tra_loi, boi: phien.user, da_xac_nhan_mat_khau: daXacNhan, ...(coMa ? { ma_cau_hoi } : {}) } }));
}

// ---------- duyệt việc tốn tiền (đợt 4, §8.2, §8.3, §9 mục 4) ----------
const LOI_DUYET_TOI_DA = 2000; // ký tự (code point, như len() Python) — khớp runner api.LOI_DUYET_TOI_DA
const MAT_KHAU_TOI_DA = 256;
const SAI_MK_TOI_DA = 5;
const SAI_MK_CUA_SO_MS = 10 * 60e3;
const RE_SURROGATE_LE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/;
// Đếm sai mật khẩu theo user: bộ nhớ isolate (lớp đầu, chặn song song trong isolate) + lớp bền:
// KV SO_DUYET khoá `sai:<user>` (D9, giữ qua isolate/colo) khi có binding; không có binding → Cache API (cùng colo) như cũ.
// sai = mốc ms các lần sai đã xác nhận; dang_kiem = số lần đang kiểm (giữ chỗ ĐỒNG BỘ trước await); khoa_den = ms.
const demSaiBoNho = new Map();
export function datLaiDemSaiMatKhau() { demSaiBoNho.clear(); } // test: giả lập isolate mới
const khoaCacheSai = (user) => `https://dem-sai-mat-khau.kho.invalid/${encodeURIComponent(user)}`;
const khoaKvSai = (user) => `sai:${user}`;
function chuanHoaDemSai(d) {
  if (!laObjectThuong(d) || !Array.isArray(d.sai)) return null;
  return { sai: d.sai.filter((x) => Number.isFinite(x)).slice(-50), khoa_den: Number.isFinite(d.khoa_den) ? d.khoa_den : 0 };
}
async function docDemSaiCache(user) {
  try {
    const r = await caches.default.match(khoaCacheSai(user));
    if (!r) return null;
    return chuanHoaDemSai(await r.json());
  } catch (e) {
    console.error("dem-sai-mat-khau: đọc Cache API lỗi", e && e.name);
    return null;
  }
}
async function ghiDemSaiCache(user, dem) {
  try {
    await caches.default.put(khoaCacheSai(user), new Response(JSON.stringify({ sai: dem.sai, khoa_den: dem.khoa_den }), {
      headers: { "content-type": "application/json", "cache-control": `max-age=${SAI_MK_CUA_SO_MS / 1000}` },
    }));
  } catch (e) {
    console.error("dem-sai-mat-khau: ghi Cache API lỗi", e && e.name);
  }
}
// Có SO_DUYET mà KV đọc lỗi → NÉM (người gọi trả 503, không kiểm mật khẩu — §9.4).
async function docDemSai(env, user) {
  if (!env.SO_DUYET) return docDemSaiCache(user);
  try {
    return chuanHoaDemSai(await env.SO_DUYET.get(khoaKvSai(user), { type: "json" }));
  } catch (e) {
    console.error("dem-sai-mat-khau: đọc KV lỗi", e && e.name);
    throw e;
  }
}
async function ghiDemSai(env, user, dem) {
  if (!env.SO_DUYET) return ghiDemSaiCache(user, dem);
  try {
    await env.SO_DUYET.put(khoaKvSai(user), JSON.stringify({ sai: dem.sai, khoa_den: dem.khoa_den }), { expirationTtl: SAI_MK_CUA_SO_MS / 1000 });
  } catch (e) {
    console.error("dem-sai-mat-khau: ghi KV lỗi", e && e.name);
  }
}

const RE_SHA256_HEX = /^[0-9a-f]{64}$/;

// Kiểm mật khẩu của user đang đăng nhập, có đếm sai (dùng chung cho duyệt việc tốn tiền và lưu bản sửa có chữ, Q3).
// Trả null khi đúng; sai/khoá/KV lỗi → Response lỗi (403/429/503).
async function kiemMatKhauCoDem(env, user, mat_khau) {
  let cache;
  try {
    cache = await docDemSai(env, user);
  } catch {
    return loi("Không kiểm được số lần sai — thử lại sau", 503); // §9.4: coi như đang khoá, KHÔNG kiểm mật khẩu
  }
  // --- đoạn đồng bộ: hợp nhất + kiểm + giữ chỗ (không await ở giữa → request song song không lọt quá 5 lần) ---
  let dem = demSaiBoNho.get(user);
  if (!dem) demSaiBoNho.set(user, (dem = { sai: [], dang_kiem: 0, khoa_den: 0 }));
  if (cache) {
    if (cache.sai.length > dem.sai.length) dem.sai = cache.sai;
    dem.khoa_den = Math.max(dem.khoa_den, cache.khoa_den);
  }
  const bayGio = Date.now();
  dem.sai = dem.sai.filter((t) => bayGio - t < SAI_MK_CUA_SO_MS);
  if (bayGio < dem.khoa_den || dem.sai.length + dem.dang_kiem >= SAI_MK_TOI_DA) {
    return loi(`Sai mật khẩu ${SAI_MK_TOI_DA} lần — tạm khoá duyệt 10 phút`, 429);
  }
  dem.dang_kiem++;
  // --- hết đoạn đồng bộ ---
  let dung = false;
  try {
    const u = dsUser(env)[user];
    dung = !!u && (await kiemMatKhau(mat_khau, u.hash));
  } finally {
    dem.dang_kiem--;
  }
  if (!dung) {
    const luc = Date.now();
    dem.sai.push(luc);
    if (dem.sai.filter((t) => luc - t < SAI_MK_CUA_SO_MS).length >= SAI_MK_TOI_DA) dem.khoa_den = Math.max(dem.khoa_den, luc + SAI_MK_CUA_SO_MS);
    await ghiDemSai(env, user, dem);
    return loi("Sai mật khẩu", 403);
  }
  return null;
}

async function duyetViec(req, env, tuyen, phien) {
  const b = await docBodyViec(req);
  const { loi_duyet, mat_khau, sha_tham_so } = laObjectThuong(b) ? b : {};
  if (typeof loi_duyet !== "string" || !loi_duyet.trim() || [...loi_duyet].length > LOI_DUYET_TOI_DA || RE_SURROGATE_LE.test(loi_duyet)) {
    return loi(`Lời duyệt phải là chữ 1–${LOI_DUYET_TOI_DA} ký tự`);
  }
  // [P2-2] sha256hex của tham_so_chuan người dùng đã xem — kiểm dạng TRƯỚC mật khẩu (thiếu không tính lần sai).
  if (typeof sha_tham_so !== "string" || !RE_SHA256_HEX.test(sha_tham_so)) return loi("Thiếu sha_tham_so — tải lại việc rồi duyệt");
  if (typeof mat_khau !== "string" || !mat_khau || mat_khau.length > MAT_KHAU_TOI_DA) return loi("Thiếu mật khẩu");
  const user = phien.user;
  const loiMk = await kiemMatKhauCoDem(env, user, mat_khau);
  if (loiMk) return loiMk;

  const r = await goiMayNha(env, `/viec/${tuyen.id}`);
  if (!r.ok) return traVeMayNha(r);
  let d;
  try { d = await r.json(); } catch { return loi("Máy nhà trả dữ liệu lạ", 502); }
  const viec = laObjectThuong(d) ? d.viec : null;
  // tham_so_chuan: NGUYÊN CHUỖI runner trả (không stringify lại) — runner băm đúng chuỗi này khi kiểm chữ ký.
  if (!laObjectThuong(viec) || typeof d.tham_so_chuan !== "string" || typeof viec.loai !== "string" || !RE_LOAI.test(viec.loai)
    || (viec.id !== undefined && viec.id !== tuyen.id)) {
    return loi("Máy nhà trả dữ liệu lạ", 502);
  }
  if (viec.trang_thai !== "cho_duyet") return loi("Việc không còn chờ duyệt", 409);
  if (!bangNhau(await sha256HexText(d.tham_so_chuan), sha_tham_so)) return loi("Dữ liệu việc đã đổi — tải lại rồi duyệt", 409);
  const duyet_luc = nowIso();
  const chu_ky_duyet = await kyDuyet(env, tuyen.id, viec.loai, d.tham_so_chuan, loi_duyet, duyet_luc, user);
  return traVeMayNha(await goiMayNha(env, tuyen.dich, { method: "POST", body: { loi_duyet, duyet_luc, boi: user, chu_ky_duyet } }));
}

// ---------- sửa video (đợt 6, docs/sua-video.md §4.2, §8.3) ----------
// Worker chỉ kiểm HÌNH DẠNG; runner (kiem_ban_sua) kiểm đầy đủ với dữ liệu thật (chỉ số câu, vai clip, chữ trùng bản cũ…).
const SUA_PHU_DE_TOI_DA = 30;
const SUA_CHU_TOI_DA = 200; // code point, sau NFC
const SUA_DOI_CLIP_TOI_DA = 10;
const SUA_DOI_CHO_TOI_DA = 3;
const SUA_SEG_TOI_DA = 199; // khớp seg 0–199 của runner (§8.1)
const SUA_CAU_TOI_DA = 9999;
// Chữ phụ đề đi vào .sua.srt rồi .ass: cấm điều khiển C0/C1, xuống dòng (kể cả U+2028/2029), thẻ ASS { } \, < > và "-->" (phá SRT).
const RE_CHU_PHU_DE_CAM = /[\u0000-\u001f\u007f-\u009f\u2028\u2029{}\\<>]|-->/;
const RE_TEN_CLIP = /^[0-9A-Za-z][0-9A-Za-z_.()\- ]{0,150}\.mp4$/; // §3.1
const RE_BAN_SUA = /^b[0-9a-f]{16}$/;
const RE_DU_AN = /^[0-9a-f]{12}$/;
const laSoNguyenTrong = (v, max) => Number.isInteger(v) && v >= 0 && v <= max;
const laObjectDungKhoa = (o, khoa) => laObjectThuong(o) && Object.keys(o).length === khoa.length && khoa.every((k) => k in o);

// Trả bản sửa đã dựng lại (chỉ khoá cho phép, chữ đã NFC) hoặc chuỗi lỗi. Không đụng mat_khau.
export function kiemBanSua(b) {
  if (!laObjectThuong(b)) return "Dữ liệu không hợp lệ";
  const { sua_luc, phu_de_sha, phu_de = [], doi_clip = [], doi_cho = [] } = b;
  if (!Number.isSafeInteger(sua_luc) || sua_luc < 0) return "Thời điểm sửa không hợp lệ — tải lại video";
  if (phu_de_sha !== undefined && (typeof phu_de_sha !== "string" || !RE_SHA256_HEX.test(phu_de_sha))) return "Mã phụ đề không hợp lệ — tải lại video";
  if (!Array.isArray(phu_de) || phu_de.length > SUA_PHU_DE_TOI_DA) return `Sửa tối đa ${SUA_PHU_DE_TOI_DA} câu mỗi lần`;
  if (!Array.isArray(doi_clip) || doi_clip.length > SUA_DOI_CLIP_TOI_DA) return `Đổi tối đa ${SUA_DOI_CLIP_TOI_DA} clip mỗi lần`;
  if (!Array.isArray(doi_cho) || doi_cho.length > SUA_DOI_CHO_TOI_DA) return `Đổi chỗ tối đa ${SUA_DOI_CHO_TOI_DA} cặp mỗi lần`;
  if (phu_de.length + doi_clip.length + doi_cho.length === 0) return "Chưa có thay đổi nào";
  if (phu_de.length && phu_de_sha === undefined) return "Thiếu mã phụ đề — tải lại video";
  const ra = { sua_luc, ...(phu_de_sha === undefined ? {} : { phu_de_sha }), phu_de: [], doi_clip: [], doi_cho: [] };
  const daCau = new Set();
  for (const c of phu_de) {
    if (!laObjectDungKhoa(c, ["i", "text"]) || !laSoNguyenTrong(c.i, SUA_CAU_TOI_DA)) return "Câu phụ đề không hợp lệ";
    if (daCau.has(c.i)) return "Một câu bị sửa hai lần";
    daCau.add(c.i);
    if (typeof c.text !== "string" || RE_SURROGATE_LE.test(c.text)) return `Câu ${c.i}: chữ không hợp lệ`;
    const text = c.text.normalize("NFC");
    const dai = [...text].length;
    if (!text.trim() || dai > SUA_CHU_TOI_DA) return `Câu ${c.i}: chữ phải dài 1–${SUA_CHU_TOI_DA} ký tự`;
    if (RE_CHU_PHU_DE_CAM.test(text)) return `Câu ${c.i}: không dùng xuống dòng, ký tự điều khiển, { } \\ < > hay -->`;
    ra.phu_de.push({ i: c.i, text });
  }
  const daSeg = new Set();
  for (const c of doi_clip) {
    if (!laObjectDungKhoa(c, ["seg", "clip"]) || !laSoNguyenTrong(c.seg, SUA_SEG_TOI_DA)) return "Đoạn cần đổi clip không hợp lệ";
    if (daSeg.has(c.seg)) return "Một đoạn bị đổi clip hai lần";
    daSeg.add(c.seg);
    if (typeof c.clip !== "string" || !RE_TEN_CLIP.test(c.clip)) return "Tên clip không hợp lệ";
    ra.doi_clip.push({ seg: c.seg, clip: c.clip });
  }
  for (const c of doi_cho) {
    if (!Array.isArray(c) || c.length !== 2 || !c.every((x) => laSoNguyenTrong(x, SUA_SEG_TOI_DA)) || c[0] === c[1]) return "Cặp đổi chỗ không hợp lệ";
    ra.doi_cho.push([c[0], c[1]]);
  }
  return ra;
}

// POST /api/viec/sua-video/<uid>/<ma>/luu → (1) POST /r/sua-video/<uid>/<ma>/ban-sua → (2) POST /r/viec {loai:"sua_video"}.
// Có sửa chữ phụ đề → bắt mật khẩu (Q3=A), đếm sai chung bộ đếm với duyệt; chỉ đổi clip/đổi chỗ → không cần.
async function luuSuaVideo(req, env, tuyen, phien) {
  const b = await docBodyViec(req);
  const ban = kiemBanSua(b);
  if (typeof ban === "string") return loi(ban);
  const user = phien.user;
  if (ban.phu_de.length) {
    const { mat_khau } = b;
    if (typeof mat_khau !== "string" || !mat_khau) return loi("Sửa chữ phụ đề cần nhập mật khẩu", 403);
    if (mat_khau.length > MAT_KHAU_TOI_DA) return loi("Sai mật khẩu", 403); // không băm chuỗi dài bất thường; không tính lượt
    const loiMk = await kiemMatKhauCoDem(env, user, mat_khau);
    if (loiMk) return loiMk;
  }
  const r1 = await goiMayNha(env, tuyen.dich, { method: "POST", body: { ...ban, boi: user } });
  if (!r1.ok) return traVeMayNha(r1); // lỗi ở (1) → KHÔNG tạo việc
  let d1;
  try { d1 = await r1.json(); } catch { return loi("Máy nhà trả dữ liệu lạ", 502); }
  const ban_sua = laObjectThuong(d1) ? d1.ban_sua : null;
  const du_an = laObjectThuong(d1) ? d1.du_an : null;
  if (typeof ban_sua !== "string" || !RE_BAN_SUA.test(ban_sua) || typeof du_an !== "string" || !RE_DU_AN.test(du_an)) {
    return loi("Máy nhà trả dữ liệu lạ", 502);
  }
  const tham_so = { uid: tuyen.uid, du_an, ma_video: tuyen.ma, ban_sua };
  const r2 = await goiMayNha(env, "/viec", { method: "POST", body: { loai: "sua_video", tham_so, boi: user } });
  if (r2.status === 409) {
    let d2 = null;
    try { d2 = await r2.json(); } catch { /* giữ null */ }
    const t = laObjectThuong(d2) ? d2.trung : null;
    const id = typeof t === "string" ? t : laObjectThuong(t) ? t.id : null;
    if (typeof id === "string" && RE_ID_VIEC.test(id)) return json({ loi: "Video này đang được dựng lại", trung: id, ban_sua }, 409);
    return json({ loi: (laObjectThuong(d2) && typeof d2.loi === "string" && d2.loi) || "Không tạo được việc", ban_sua }, 409);
  }
  if (!r2.ok) return traVeMayNha(r2);
  let d2;
  try { d2 = await r2.json(); } catch { return loi("Máy nhà trả dữ liệu lạ", 502); }
  if (!laObjectThuong(d2) || !laObjectThuong(d2.viec)) return loi("Máy nhà trả dữ liệu lạ", 502);
  return json({ viec: d2.viec, ban_sua }, r2.status);
}

async function apiViec(req, env, url, phien) {
  const m = req.method;
  if (!USER_MAY_NHA.includes(phien.user)) return loi("Không có quyền", 403);
  // POST bắt buộc có Origin đúng (chặn chung ở fetch() cho qua khi thiếu Origin).
  if (m !== "GET" && req.headers.get("origin") !== url.origin) return loi("Sai nguồn gọi", 403);
  if (!env.VIDEO_ORIGIN || !env.VIDEO_KEY || !env.RUNNER_KEY || !env.KY_RIENG) return loi("Chưa cấu hình bộ chạy việc", 503);
  const bang = tuyenViec(url.pathname);
  if (!bang) return loi("Không có API này", 404);
  const tuyen = bang[m];
  if (!tuyen) return loi("Sai phương thức", 405);
  if (m === "GET") {
    const q = queryViec(url.searchParams, tuyen.query || [], tuyen.mau);
    if (q === null) return loi("Tham số truy vấn không hợp lệ");
    return traVeMayNha(await goiMayNha(env, tuyen.dich + q));
  }
  if (tuyen.lam === "tra_loi") return traLoiViec(req, env, tuyen, phien);
  if (tuyen.lam === "duyet") return duyetViec(req, env, tuyen, phien);
  if (tuyen.lam === "sua_video") return luuSuaVideo(req, env, tuyen, phien);
  let body;
  if (tuyen.lam === "tao") {
    const b = kiemThamSoViec(await docBodyViec(req));
    if (typeof b === "string") return loi(b);
    body = { loai: b.loai, tham_so: b.tham_so, boi: phien.user };
  } else {
    body = { boi: phien.user };
  }
  return traVeMayNha(await goiMayNha(env, tuyen.dich, { method: "POST", body }));
}

// Dán link xong tự giao máy nhà phân tích (không phải bấm "📥 Xử lý link mới"). Ai dán cũng được: Worker tự ký như
// giaoDongBoLoai, chạy dưới tên người dán. Link có UID → phan_tich_uid {uid} (khoá theo UID, không đụng việc khác).
// Link rút gọn (chưa có UID) → xu_ly_link_moi (kho.py cho tự tìm UID rồi tạo việc con).
// Không bao giờ ném: máy nhà tắt/lỗi thì link vẫn đã lưu, vẫn bấm tay được.
// → "tao" (máy nhà nhận) | "trung" (409: đã có việc cùng khoá đang mở) | "chua" (thiếu cấu hình / máy nhà tắt, lỗi, từ chối).
export async function giaoPhanTichLinkMoi(env, uid, phien) {
  try {
    if (!env.VIDEO_ORIGIN || !env.VIDEO_KEY || !env.RUNNER_KEY || !env.KY_RIENG) return "chua";
    const v = kiemThamSoViec(/^\d{19}$/.test(String(uid || ""))
      ? { loai: "phan_tich_uid", tham_so: { uid: String(uid) } }
      : { loai: "xu_ly_link_moi", tham_so: {} });
    if (typeof v === "string") return "chua";
    const r = await goiMayNha(env, "/viec", { method: "POST", body: { loai: v.loai, tham_so: v.tham_so, boi: phien.user } });
    if (r.body) r.body.cancel().catch(() => {});
    if (r.status === 409) return "trung";
    if (!r.ok) console.error(`them: máy nhà trả ${r.status} khi giao ${v.loai}`);
    return r.ok ? "tao" : "chua";
  } catch (e) {
    console.error("them: không giao được việc phân tích", e && e.name);
    return "chua";
  }
}

// FX-W8: giao việc miễn phí poster_bo_loai {uid} sau khi lưu chấm dính Loại — cùng đường POST /api/viec (kiemThamSoViec +
// goiMayNha: ký Ed25519 §8.3, timeout TIMEOUT_VIEC_MS). Không bao giờ ném: lỗi máy nhà không làm hỏng việc lưu chấm.
// → "tao" (máy nhà nhận) | "trung" (409: việc cùng uid đang mở) | "chua" (thiếu cấu hình / UID sai / máy nhà tắt, lỗi, từ chối).
async function giaoDongBoLoai(env, infoT, phien) {
  try {
    if (!env.VIDEO_ORIGIN || !env.VIDEO_KEY || !env.RUNNER_KEY || !env.KY_RIENG) return "chua";
    let uid = "";
    try { uid = String(JSON.parse(infoT).uid || ""); } catch { uid = ""; }
    const v = kiemThamSoViec({ loai: "poster_bo_loai", tham_so: { uid } });
    if (typeof v === "string") return "chua";
    const r = await goiMayNha(env, "/viec", { method: "POST", body: { loai: v.loai, tham_so: v.tham_so, boi: phien.user } });
    if (r.body) r.body.cancel().catch(() => {});
    if (r.status === 409) return "trung";
    if (!r.ok) console.error(`duyet: máy nhà trả ${r.status} khi giao poster_bo_loai`);
    return r.ok ? "tao" : "chua";
  } catch (e) {
    console.error("duyet: không giao được poster_bo_loai", e && e.name);
    return "chua";
  }
}

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
  // Runner gọi (không có phiên, không có Origin) — xác thực bằng x-runner-key; đặt TRƯỚC kiểm phiên.
  if (p === "/api/runner/tieu-duyet") return m === "POST" ? tieuDuyet(req, env) : loi("Sai phương thức", 405);

  const phien = await docPhien(env, req);
  if (!phien) return loi("Chưa đăng nhập", 401);
  if (p === "/api/me") return json(phien);
  if (p === "/api/viec" || p.startsWith("/api/viec/")) return apiViec(req, env, url, phien);
  if (p === "/api/poster" || p.startsWith("/api/poster/")) return apiPoster(req, env, url, { user: phien.user, chu: laChuKho(phien.user) });

  let v;
  if ((v = p.match(/^\/api\/video\/([^/]+)\/(ds|file|xoa|dy|dyfile|xem|tien-do|anh|clip)$/))) {
    if (!USER_MAY_NHA.includes(phien.user)) return loi("Không có quyền", 403);
    const id = decodeURIComponent(v[1]), act = v[2];
    if (!RE_ID.test(id)) return loi("ID không hợp lệ");
    if (!env.VIDEO_ORIGIN || !env.VIDEO_KEY) return loi("Chưa cấu hình máy phát video", 503);
    if ((act === "xoa") !== (m === "POST")) return loi("Sai phương thức", 405);
    const q = queryVideo(act, url.searchParams, req.headers.get("sec-fetch-site"));
    let r;
    try {
      r = await fetch(`${env.VIDEO_ORIGIN}/v/${id}/${act}${q}`, {
        method: m,
        headers: { "x-key": env.VIDEO_KEY, ...(req.headers.get("range") ? { range: req.headers.get("range") } : {}) },
        ...(ACT_CO_TIMEOUT.includes(act) ? { signal: AbortSignal.timeout(TIMEOUT_VIDEO_MS) } : {}),
      });
    } catch (e) {
      console.error(`video ${act} ${id}: máy nhà lỗi`, e);
      return laHetGio(e) ? loi(LOI_CHAM_MAY_NHA, 504) : loi(LOI_MAY_NHA, 502);
    }
    if (r.status === 401 || r.status === 403) {
      console.error(`video ${act} ${id}: máy nhà trả ${r.status} — VIDEO_KEY lệch với tools/.video_key`);
      if (r.body) r.body.cancel().catch(() => {});
      return loi(LOI_KHOA_MAY_NHA, 502);
    }
    const h = new Headers({ "content-type": r.headers.get("content-type") || "application/octet-stream", "cache-control": "no-store" });
    for (const k of ["content-length", "content-disposition", "content-range", "accept-ranges"]) if (r.headers.get(k)) h.set(k, r.headers.get(k));
    return new Response(r.body, { status: r.status, headers: h });
  }

  if (p === "/api/suc-khoe" && m === "GET") {
    if (!USER_MAY_NHA.includes(phien.user)) return loi("Không có quyền", 403);
    if (!env.VIDEO_ORIGIN || !env.VIDEO_KEY) return loi("Chưa cấu hình máy phát video", 503);
    const hong = (loiND, chiTiet) => {
      console.error(`suc-khoe: ${loiND}`, chiTiet);
      return json({ may_nha: false, loi: loiND, apps: [] });
    };
    let r;
    try {
      r = await fetch(`${env.VIDEO_ORIGIN}/suc-khoe`, { headers: { "x-key": env.VIDEO_KEY }, signal: AbortSignal.timeout(10000) });
    } catch (e) {
      return hong(laHetGio(e) ? "Hết thời gian chờ máy nhà" : LOI_MAY_NHA, e);
    }
    if (r.status === 401 || r.status === 403) return hong(LOI_KHOA_MAY_NHA, r.status);
    if (!r.ok) return hong(`Máy nhà trả mã ${r.status}${r.status >= 500 ? ` ${GOI_Y_MAY_NHA}` : ""}`, r.status);
    let d;
    try { d = await r.json(); } catch (e) { return hong(laHetGio(e) ? "Hết thời gian chờ máy nhà" : "Máy nhà trả dữ liệu lạ", e); }
    if (!d || typeof d !== "object" || Array.isArray(d)) return hong("Máy nhà trả dữ liệu lạ", d);
    return json({ ...d, may_nha: true });
  }

  // Bật/tắt từng app trên máy nhà (video_server.py LENH_BAT — mã cố định, không gửi lệnh).
  const mApp = p.match(/^\/api\/may-nha\/app\/(muse|perfectvoice|poster|runner)\/(bat|tat)$/);
  if (mApp && m === "POST") {
    if (!USER_MAY_NHA.includes(phien.user)) return loi("Không có quyền", 403);
    if (!env.VIDEO_ORIGIN || !env.VIDEO_KEY) return loi("Chưa cấu hình máy phát video", 503);
    let r;
    try {
      r = await fetch(`${env.VIDEO_ORIGIN}/app/${mApp[1]}/${mApp[2]}`, { method: "POST", headers: { "x-key": env.VIDEO_KEY }, signal: AbortSignal.timeout(30000) });
    } catch (e) {
      return loi(laHetGio(e) ? "Hết thời gian chờ máy nhà" : LOI_MAY_NHA, 502);
    }
    if (r.status === 401 || r.status === 403) return loi(LOI_KHOA_MAY_NHA, 502);
    const d = await r.json().catch(() => null);
    if (!d || typeof d !== "object") return loi(`Máy nhà trả mã ${r.status}`, 502);
    console.log(`may-nha ${phien.user} ${mApp[2]} ${mApp[1]}: ${r.status} ${d.tin || d.loi || ""}`);
    return r.ok ? json(d) : loi(d.tin || d.loi || `Máy nhà trả mã ${r.status}`, r.status === 404 ? 404 : 502);
  }

  if (p === "/api/duyet" && m === "POST") {
    if (!USER_MAY_NHA.includes(phien.user)) return loi("Không có quyền", 403);
    const b = kiemDuyet(await docBody(req));
    if (typeof b === "string") return loi(b);
    const infoT = await getText(env, `data/${b.id}/info.json`);
    if (!infoT) return loi("Không tìm thấy sản phẩm", 404);
    const cungKhoa = (o) => o.goc === b.goc && o.ten === b.ten && o.sua_luc === b.sua_luc;
    let cu = ""; // ket_qua cũ của mục cùng khoá (lượt mutate cuối = lượt đã ghi)
    const d = await suaJson(env, `data/${b.id}/duyet.json`, (x) => {
      x.videos = x.videos || [];
      const vt = x.videos.findIndex(cungKhoa);
      cu = vt >= 0 && x.videos[vt] ? x.videos[vt].ket_qua : "";
      // FX-W6: bỏ chấm + bỏ góp ý → GIỮ mục cũ (ket_qua "", gop_y ""): runner bo_loai.py chỉ trả video từ _loai/ khi có mục
      // khớp đúng (goc, ten, sua_luc) mà mục cuối khác "loai". Chưa có mục cùng khoá → không thêm gì (không tạo rác).
      if (b.ket_qua === "" && b.gop_y === "" && vt < 0) return;
      const muc = { goc: b.goc, ten: b.ten, sua_luc: b.sua_luc, mb: b.mb, ket_qua: b.ket_qua, gop_y: b.gop_y, boi: phien.ten, luc: nowIso() };
      if (vt >= 0) x.videos[vt] = muc; // cập nhật tại chỗ, giữ thứ tự
      else x.videos.push(muc);
    }, `Duyệt video ${b.ten} ${b.id} — ${phien.ten}`, DUYET_RONG);
    // FX-W8: chấm dính Loại (cũ hoặc mới là "loai") → Worker tự giao poster_bo_loai, không phụ thuộc trang web còn mở.
    const dong_bo = cu === "loai" || b.ket_qua === "loai" ? await giaoDongBoLoai(env, infoT, phien) : null;
    return json({ duyet: d.videos, dong_bo });
  }

  const chu = laChuKho(phien.user);
  if (p === "/api/ds" && m === "GET") return json({ san_pham: (await danhSach(env)).map((x) => anTruongNoiBo(x, chu)) });

  let k;
  if ((k = p.match(/^\/api\/sp\/([^/]+)$/)) && m === "GET") {
    const id = decodeURIComponent(k[1]);
    if (!RE_ID.test(id)) return loi("ID không hợp lệ");
    // duyet.json chứa đường dẫn ổ máy nhà (goc) → chỉ đọc/trả cho user máy nhà; user khác nhận [].
    const xemDuyet = chu;
    const [infoT, md, caps, vtkT, douyin, duyetT] = await Promise.all(["info.json", "bo-canh-quay.md", "captions.txt", "video_tk.json", "douyin.md", ...(xemDuyet ? ["duyet.json"] : [])].map((f) => getText(env, `data/${id}/${f}`)));
    if (!infoT) return loi("Không tìm thấy sản phẩm", 404);
    const che = (t) => (chu ? t : cheDuongDan(t)); // P-33b: md/caps/douyin của người thường không lộ đường dẫn máy nhà
    return json({ info: anTruongNoiBo(JSON.parse(infoT), chu), md: che(md), caps: che(caps), douyin: che(douyin), vtk: vtkT ? JSON.parse(vtkT).videos || [] : [], duyet: duyetT ? JSON.parse(duyetT).videos || [] : [] });
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
    const may = await giaoPhanTichLinkMoi(env, uid, phien);
    return json({ info: anTruongNoiBo({ ...info, trang_thai: "cho" }, chu), may });
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
    return json({ info: anTruongNoiBo({ ...info, trang_thai: trangThai(info) }, chu) });
  }

  if (p === "/api/tag" && m === "POST") { // thẻ riêng: yêu thích / cần đăng
    const { id, tag, bat } = await docBody(req);
    if (!RE_ID.test(String(id)) || !TAG_RIENG.includes(tag)) return loi("Dữ liệu không hợp lệ");
    const info = await updateInfo(env, id, (i) => { if (bat) i[tag] = true; else delete i[tag]; }, `${bat ? "Gắn" : "Bỏ"} thẻ ${tag} ${id} — ${phien.ten}`);
    return json({ info: anTruongNoiBo({ ...info, trang_thai: trangThai(info) }, chu) });
  }

  if (p === "/api/ghichu" && m === "POST") {
    const { id, ghi_chu = "" } = await docBody(req);
    if (!RE_ID.test(String(id))) return loi("ID không hợp lệ");
    if (String(ghi_chu).length > 20000) return loi("Ghi chú quá dài");
    const info = await updateInfo(env, id, (i) => { i.ghi_chu = String(ghi_chu); }, `Ghi chú ${id} — ${phien.ten}`);
    return json({ info: anTruongNoiBo(info, chu) });
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
