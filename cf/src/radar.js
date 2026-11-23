// Kho sản phẩm — route Worker /api/radar/* cho "Radar UID" (docs/radar-uid.md §7, §11; D16).
// Trình duyệt → Worker (file này) → ${VIDEO_ORIGIN}/r/radar/* (video_server, RE_R) → runner /radar/*.
// Đọc và ghi đều CHỈ chủ kho (403 trước mọi gọi máy nhà). Lệnh ghi: Origin bắt buộc, body ≤ 16 KB, Worker tự dựng
// {"boi": phien.user} (+ "uid" nếu route cần, đã kiểm ^\d{19}$), bỏ mọi khoá khác của body trình duyệt, ký Ed25519 D7 qua
// goiMayNha của worker.js. Không tự thử lại. Id 19 số luôn là CHUỖI (không Number/parseInt).
// Lỗi từ máy nhà: chỉ chuyển câu `loi` (chuỗi ngắn, đã lọc) chứ không chuyển thân thô.
// ES module, KHÔNG import worker.js (tránh vòng): mọi hàm dùng chung nhận qua `deps`.
"use strict";

export const RE_UID = /^\d{19}$/;
export const RADAR_BODY_TOI_DA = 16 * 1024; // như BODY_VIEC_TOI_DA (worker.js) và R_BODY_TOI_DA (video_server)
const LOI_TOI_DA = 200;
// Chữ giữ đúng worker.js LOI_MAY_NHA / LOI_CHAM_MAY_NHA.
const LOI_MAY_NHA = "Máy nhà không trả lời (đã bật video_server và tunnel chưa?)";
const LOI_CHAM_MAY_NHA = "Máy nhà phản hồi quá chậm";
const LOI_UID = "UID phải đủ 19 chữ số";

const RE_GOC_LENH = /^\/api\/radar\/goc\/(\d{19})\/(tim-lai|ngung|theo-lai|them-tay)$/;
const RE_GOC_UID_LENH = /^\/api\/radar\/goc\/(\d{19})\/uid\/(\d{19})\/(ghim|bo-ghim|loai|bo-loai)$/;
const RE_GET_UID = /^\/api\/radar\/uid\/(\d{19})$/;

// Bảng route: path web → {METHOD: {dich (path runner, không /r), act?, goc?, uid?}}. Không khớp (gồm uid sai dạng) → null.
// act "goc" và "them-tay" nhận uid trong body (không có `uid` trong bảng); route có uid trên path thì có `uid`.
export function tuyenRadar(p) {
  if (typeof p !== "string") return null;
  if (p === "/api/radar/bang") return { GET: { dich: "/radar/bang" } };
  if (p === "/api/radar/goc") return { POST: { dich: "/radar/goc", act: "goc" } };
  if (p === "/api/radar/chup-lai") return { POST: { dich: "/radar/chup-lai", act: "chup-lai" } };
  let k = p.match(RE_GET_UID);
  if (k) return { GET: { dich: `/radar/uid/${k[1]}` } };
  k = p.match(RE_GOC_LENH);
  if (k) return { POST: { dich: `/radar/goc/${k[1]}/${k[2]}`, act: k[2], goc: k[1] } };
  k = p.match(RE_GOC_UID_LENH);
  if (k) return { POST: { dich: `/radar/goc/${k[1]}/uid/${k[2]}/${k[3]}`, act: k[3], goc: k[1], uid: k[2] } };
  return null;
}

// Đọc body tới `toiDa` byte; vượt → huỷ luồng, trả null. Không body → "".
async function docBodyToiDa(req, toiDa) {
  if (!req.body) return "";
  const reader = req.body.getReader();
  const manh = [];
  let tong = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    tong += value.byteLength;
    if (tong > toiDa) {
      reader.cancel().catch(() => {});
      return null;
    }
    manh.push(value);
  }
  const buf = new Uint8Array(tong);
  let vt = 0;
  for (const m of manh) {
    buf.set(m, vt);
    vt += m.byteLength;
  }
  return new TextDecoder().decode(buf);
}

// Câu lỗi của máy nhà chỉ được qua nếu là chuỗi ngắn, không giống đường dẫn đĩa/traceback.
function cauLoiAnToan(v) {
  if (typeof v !== "string") return "";
  const s = v.trim();
  if (!s || s.length > LOI_TOI_DA) return "";
  if (/[A-Za-z]:\\|Traceback|\.db\b|\.py\b/.test(s)) return "";
  return s;
}

// deps = { goiMayNha, traVeMayNha, loi, json, laChuKho } — từ worker.js. Luôn trả Response.
export async function apiRadar(req, env, url, phien, deps) {
  const { goiMayNha, traVeMayNha, loi, laChuKho } = deps;
  const user = phien && typeof phien.user === "string" ? phien.user : "";
  if (!user || !laChuKho(user)) return loi("Không có quyền", 403);
  const bang = tuyenRadar(url.pathname);
  if (!bang) return loi("Không có API này", 404);
  const m = req.method;
  const tuyen = bang[m];
  if (!tuyen) return loi("Sai phương thức", 405);
  if (!env.VIDEO_ORIGIN || !env.VIDEO_KEY || !env.RUNNER_KEY || !env.KY_RIENG) return loi("Chưa cấu hình bộ chạy việc", 503);

  // Lỗi từ máy nhà: giữ status 4xx và câu `loi` đã lọc; 524/HTML/5xx lạ → lỗi JSON của Worker. Không chuyển thân thô.
  const traVe = async (r) => {
    const ct = r.headers.get("content-type") || "";
    const laJson = /^application\/json/i.test(ct);
    if (r.status < 400) return traVeMayNha(r);
    if (r.status === 524) {
      console.error(`radar ${m} ${tuyen.dich}: edge trả 524`);
      if (r.body) r.body.cancel().catch(() => {});
      return loi(LOI_CHAM_MAY_NHA, 504);
    }
    let cau = "";
    if (laJson) {
      try {
        const o = JSON.parse(await r.text());
        cau = cauLoiAnToan(o && o.loi);
      } catch (e) {
        cau = "";
      }
    } else if (r.body) {
      r.body.cancel().catch(() => {});
    }
    if (r.status >= 500 && ![502, 503, 504].includes(r.status)) {
      console.error(`radar ${m} ${tuyen.dich}: máy nhà trả ${r.status}`);
      return loi(LOI_MAY_NHA, 502);
    }
    if (!cau) {
      console.error(`radar ${m} ${tuyen.dich}: máy nhà trả ${r.status} (${ct || "không content-type"}) không có câu lỗi`);
      return r.status >= 500 ? loi(r.status === 504 ? LOI_CHAM_MAY_NHA : LOI_MAY_NHA, r.status === 504 ? 504 : 502) : loi("Máy nhà từ chối yêu cầu", r.status);
    }
    return loi(cau, r.status);
  };

  // GET: không chuyển query nào xuống máy nhà.
  if (m === "GET") return traVe(await goiMayNha(env, tuyen.dich));

  // POST: Origin bắt buộc và đúng (chặn chung ở fetch() cho qua khi thiếu Origin).
  if (req.headers.get("origin") !== url.origin) return loi("Sai nguồn gọi", 403);
  // Trần body (header + độ dài thật, kể cả chunked).
  if (Number(req.headers.get("content-length") || 0) > RADAR_BODY_TOI_DA) return loi("Dữ liệu quá lớn", 413);
  const text = await docBodyToiDa(req, RADAR_BODY_TOI_DA);
  if (text === null) return loi("Dữ liệu quá lớn", 413);
  if (text !== "" && !/^application\/json\s*(;|$)/i.test(req.headers.get("content-type") || "")) {
    return loi("Cần content-type application/json", 415);
  }

  const gui = { boi: user };
  // Route có uid/goc trên path: runner lấy từ path, body chỉ {boi}.
  if (tuyen.act === "goc" || tuyen.act === "them-tay") {
    // uid lấy từ body, phải là CHUỖI đúng 19 số (số JSON sẽ mất chính xác > 2^53 nên không nhận). Khoá khác bị bỏ.
    let o = null;
    try {
      o = text === "" ? null : JSON.parse(text);
    } catch (e) {
      o = null;
    }
    const uid = o && typeof o === "object" && !Array.isArray(o) ? o.uid : undefined;
    if (typeof uid !== "string" || !RE_UID.test(uid)) return loi(LOI_UID, 400);
    gui.uid = uid;
  }

  const res = await traVe(await goiMayNha(env, tuyen.dich, { method: "POST", body: gui }));
  console.log(`radar ${tuyen.act}${tuyen.goc ? " " + tuyen.goc : ""}${tuyen.uid ? " " + tuyen.uid : ""} boi ${user} → ${res.status}`);
  return res;
}
