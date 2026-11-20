// Kho sản phẩm — route Worker /api/poster/* cho trang "Poster V2" (docs/poster-v2-tren-web.md §7, §2.1, §4.2; D13).
// Trình duyệt → Worker (file này) → ${VIDEO_ORIGIN}/p/<rest> (video_server máy nhà, tools/poster_web.py) → backend Poster.
// Worker chỉ kiểm việc của chặng mình: chủ kho, x-pv, Origin cho lệnh ghi, lọc path thô, hợp đồng body §2.1.
// Không tự thử lại lệnh ghi khi lỗi/hết giờ. Không chuyển 401 cho trình duyệt (web hiểu 401 = hết phiên).
// ES module, KHÔNG import worker.js (tránh vòng): tự có json/loi nhỏ.
"use strict";

export const POSTER_BODY_TOI_DA = 256 * 1024;
export const POSTER_TIMEOUT_MS = 95_000;
export const POSTER_QUERY_TOI_DA = 512;
export const RE_REST_POSTER = /^\/(api\/v2\/[A-Za-z0-9_.~\-\/]{1,200}|health|_kq(\/[0-9a-f]{32})?|_video\/\d{1,9}|_dem|_thong_tin|_bat_backend)$/;

const METHOD_POSTER = ["GET", "POST", "PUT", "PATCH", "DELETE"];
const METHOD_CO_BODY = ["POST", "PUT", "PATCH"];
// Câu lỗi giữ đúng chữ của worker.js:221-225 (LOI_MAY_NHA / LOI_KHOA_MAY_NHA / LOI_CHAM_MAY_NHA).
const LOI_MAY_NHA = "Máy nhà không trả lời (đã bật video_server và tunnel chưa?)";
const LOI_KHOA_MAY_NHA = "Máy nhà từ chối khoá (VIDEO_KEY lệch với tools/.video_key)";
const LOI_401_LA = "Máy nhà trả 401 không rõ nguồn";
const LOI_CHAM_MAY_NHA = "Máy nhà phản hồi quá chậm";
const CO_THE_DA_CHAY = "Thao tác CÓ THỂ đã chạy: bấm Refresh để kiểm trước khi bấm lại";

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });
const loi = (msg, status = 400) => json({ loi: msg }, status);
const laHetGio = (e) => !!e && (e.name === "TimeoutError" || e.name === "AbortError");
// Lệnh ghi: lỗi sau khi đã gửi thì không biết máy nhà đã làm chưa → nói rõ, để người dùng kiểm trước khi bấm lại.
const cauGhi = (cau, method) => (method === "GET" ? cau : `${cau}. ${CO_THE_DA_CHAY}`);

// rest = url.pathname bỏ "/api/poster"; search = url.search ("" hoặc "?…").
// → {dich: "/p" + rest + search} | {status, loi}
export function kiemDuongPoster(rest, method, search) {
  if (!METHOD_POSTER.includes(method)) return { status: 405, loi: "Sai phương thức" };
  const r = typeof rest === "string" ? rest : "";
  const sai = { status: 404, loi: "Đường dẫn Poster không được phép" };
  if (!RE_REST_POSTER.test(r)) return sai;
  if (r.includes("//") || r.includes("%") || r.includes("\\") || /[\x00-\x1f\x7f]/.test(r)) return sai;
  if (r.split("/").some((d) => d === "." || d === "..")) return sai;
  const s = typeof search === "string" ? search : "";
  const q = s.startsWith("?") ? s.slice(1) : s;
  if (q.length > POSTER_QUERY_TOI_DA || q.includes("#") || /[\x00-\x1f\x7f]/.test(q)) return { status: 400, loi: "Tham số truy vấn không hợp lệ" };
  return { dich: "/p" + r + (q ? "?" + q : "") };
}

// Đọc body tối đa `toiDa` byte; quá thì huỷ luồng và trả null. Không body → Uint8Array rỗng.
async function docToiDa(req, toiDa) {
  if (!req.body) return new Uint8Array(0);
  const reader = req.body.getReader();
  const phan = [];
  let tong = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    tong += value.byteLength;
    if (tong > toiDa) {
      reader.cancel().catch(() => {});
      return null;
    }
    phan.push(value);
  }
  const ra = new Uint8Array(tong);
  let o = 0;
  for (const p of phan) { ra.set(p, o); o += p.byteLength; }
  return ra;
}

// Hợp đồng §2.1 phía Worker. → {body: Uint8Array|null, ct: "application/json"|null} | {status, loi}
export async function kiemBodyPoster(req, method) {
  const cl = req.headers.get("content-length");
  const soCl = cl === null ? 0 : Number(cl);
  if (!METHOD_CO_BODY.includes(method)) {
    // GET / DELETE: không body, không kiểm content-type, không gửi content-type.
    if (soCl > 0) return { status: 400, loi: `${method} không được có body` };
    const b = await docToiDa(req, POSTER_BODY_TOI_DA);
    if (b === null || b.byteLength > 0) return { status: 400, loi: `${method} không được có body` };
    return { body: null, ct: null };
  }
  const ct = (req.headers.get("content-type") || "").trim().toLowerCase();
  if (!ct.startsWith("application/json")) return { status: 415, loi: "Chỉ nhận content-type: application/json" };
  if (soCl > POSTER_BODY_TOI_DA) return { status: 413, loi: "Body quá lớn (tối đa 256 KB)" };
  const b = await docToiDa(req, POSTER_BODY_TOI_DA);
  if (b === null) return { status: 413, loi: "Body quá lớn (tối đa 256 KB)" };
  if (b.byteLength === 0) return { status: 400, loi: "Thiếu body JSON" };
  try {
    JSON.parse(new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(b));
  } catch {
    return { status: 400, loi: "Body không phải JSON hợp lệ" };
  }
  return { body: b, ct: "application/json" };
}

// nguoi = { user, chu } (worker.js tính chu = laChuKho(user)). Luôn trả Response.
export async function apiPoster(req, env, url, nguoi) {
  const method = req.method;
  if (!nguoi || !nguoi.chu) return loi("Không có quyền", 403);
  if (req.headers.get("x-pv") !== "1") return loi("Thiếu x-pv", 403);
  if (method !== "GET" && req.headers.get("origin") !== url.origin) return loi("Sai nguồn gọi", 403);
  if (!env.VIDEO_ORIGIN || !env.VIDEO_KEY) return loi("Chưa cấu hình máy phát video", 503);
  const rest = url.pathname.slice("/api/poster".length);
  const d = kiemDuongPoster(rest, method, url.search);
  if (!d.dich) return loi(d.loi, d.status);
  const b = await kiemBodyPoster(req, method);
  if (b.status) return loi(b.loi, b.status);

  const headers = { "x-key": env.VIDEO_KEY, "x-poster-boi": nguoi.user };
  if (b.ct) headers["content-type"] = b.ct;
  const ghiNhatKy = (status) => {
    if (method !== "GET") console.log(JSON.stringify({ poster: true, method, path: rest, user: nguoi.user, status }));
  };
  const traLoi = (res) => { ghiNhatKy(res.status); return res; };

  let r;
  try {
    r = await fetch(env.VIDEO_ORIGIN + d.dich, {
      method,
      headers,
      ...(b.body ? { body: b.body } : {}),
      signal: AbortSignal.timeout(POSTER_TIMEOUT_MS),
    });
  } catch (e) {
    console.error(`poster ${method} ${rest}: máy nhà lỗi`, e && e.name);
    return traLoi(laHetGio(e) ? loi(cauGhi(LOI_CHAM_MAY_NHA, method), 504) : loi(cauGhi(LOI_MAY_NHA, method), 502));
  }
  const ctMay = r.headers.get("content-type") || "";
  if (r.status === 401) {
    const khoa = r.headers.get("x-kho-tu-choi") === "khoa";
    console.error(`poster ${method} ${rest}: máy nhà trả 401${khoa ? " (sai x-key)" : " không rõ nguồn"}`);
    if (r.body) r.body.cancel().catch(() => {});
    return traLoi(loi(khoa ? LOI_KHOA_MAY_NHA : LOI_401_LA, 502));
  }
  // Edge Cloudflare cắt ~100 s (524) hoặc không với tới tunnel (5xx trang HTML): không phải JSON của video_server.
  if (r.status === 524 || (r.status >= 500 && !/^application\/json/i.test(ctMay))) {
    console.error(`poster ${method} ${rest}: edge/máy nhà trả ${r.status} (${ctMay || "không content-type"})`);
    if (r.body) r.body.cancel().catch(() => {});
    return traLoi(r.status === 524 ? loi(cauGhi(LOI_CHAM_MAY_NHA, method), 504) : loi(cauGhi(LOI_MAY_NHA, method), 502));
  }
  // 403 (bản quyền backend), 202 {cho, trung}, 2xx/4xx/5xx JSON khác: chuyển nguyên status + body.
  const h = new Headers({ "content-type": ctMay || "application/json; charset=utf-8", "cache-control": "no-store" });
  return traLoi(new Response(r.body, { status: r.status, headers: h }));
}
