// Kho sản phẩm — route Worker /api/hoc/* cho "Học tự động mỗi ngày" (docs/hoc-tu-dong.md §3.8, §6.2, §6.3; D15).
// Trình duyệt → Worker (file này) → ${VIDEO_ORIGIN}/r/hoc/* (video_server, RE_R) → runner /hoc/* (api.py, KhoHoc).
// Đọc (báo cáo, danh sách bài học) và ghi (Hoàn tác / Bật lại) đều CHỈ chủ kho. Lệnh ghi: Origin bắt buộc, Worker tự dựng
// {"boi": phien.user} (bỏ body trình duyệt), ký Ed25519 D7 qua goiMayNha của worker.js. Không tự thử lại.
// ES module, KHÔNG import worker.js (tránh vòng): mọi hàm dùng chung nhận qua `deps`.
"use strict";

export const RE_MA_BAI_HOC = /^bh\d{8}[a-z0-9]{4}$/;
export const RE_NGAY_HOC = /^\d{4}-\d{2}-\d{2}$/;
const RE_GIOI_HAN_HOC = /^\d{1,3}$/;
export const HOC_BODY_TOI_DA = 16 * 1024; // như BODY_VIEC_TOI_DA (worker.js) và R_BODY_TOI_DA (video_server)
// Chữ giữ đúng worker.js LOI_MAY_NHA / LOI_CHAM_MAY_NHA.
const LOI_MAY_NHA = "Máy nhà không trả lời (đã bật video_server và tunnel chưa?)";
const LOI_CHAM_MAY_NHA = "Máy nhà phản hồi quá chậm";

const RE_TUYEN_GHI = /^\/api\/hoc\/bai-hoc\/([^/]+)\/(hoan-tac|bat-lai)$/;

// Bảng route: path web → {METHOD: {dich (path runner, không /r), query?, mau?, ma?, act?}}. Không khớp (gồm ma sai dạng) → null.
export function tuyenHoc(p) {
  if (p === "/api/hoc/bao-cao") return { GET: { dich: "/hoc/bao-cao", query: ["ngay"], mau: { ngay: RE_NGAY_HOC } } };
  if (p === "/api/hoc/bai-hoc") return { GET: { dich: "/hoc/bai-hoc", query: ["gioi_han"], mau: { gioi_han: RE_GIOI_HAN_HOC } } };
  const k = typeof p === "string" ? p.match(RE_TUYEN_GHI) : null;
  if (!k || !RE_MA_BAI_HOC.test(k[1])) return null;
  const [, ma, act] = k;
  return { POST: { dich: `/hoc/bai-hoc/${ma}/${act}`, ma, act } };
}

// Chỉ giữ khoá cho phép; giá trị sai mẫu → null (400). Khoá lặp lấy giá trị đầu.
function queryHoc(src, khoa, mau) {
  const q = new URLSearchParams();
  for (const k of khoa) {
    if (!src.has(k)) continue;
    const v = src.get(k);
    if (!mau[k].test(v)) return null;
    q.set(k, v);
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

// Đọc bỏ body, không giữ nội dung; quá `toiDa` byte thì huỷ luồng và trả false.
async function boBodyToiDa(req, toiDa) {
  if (!req.body) return true;
  const reader = req.body.getReader();
  let tong = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return true;
    tong += value.byteLength;
    if (tong > toiDa) {
      reader.cancel().catch(() => {});
      return false;
    }
  }
}

// deps = { goiMayNha, traVeMayNha, loi, json, laChuKho } — từ worker.js. Luôn trả Response.
export async function apiHoc(req, env, url, phien, deps) {
  const { goiMayNha, traVeMayNha, loi, laChuKho } = deps;
  const user = phien && typeof phien.user === "string" ? phien.user : "";
  if (!user || !laChuKho(user)) return loi("Không có quyền", 403);
  const bang = tuyenHoc(url.pathname);
  if (!bang) return loi("Không có API này", 404);
  const m = req.method;
  const tuyen = bang[m];
  if (!tuyen) return loi("Sai phương thức", 405);
  if (!env.VIDEO_ORIGIN || !env.VIDEO_KEY || !env.RUNNER_KEY || !env.KY_RIENG) return loi("Chưa cấu hình bộ chạy việc", 503);

  // Lỗi từ edge Cloudflare (524, trang HTML 5xx khi tunnel tắt) không phải JSON của video_server → đổi thành lỗi JSON tạm.
  // Mọi phản hồi JSON của máy nhà (200/400/404/409/503…) chuyển nguyên status + body.
  const traVe = (r) => {
    const ct = r.headers.get("content-type") || "";
    if (r.status === 524 || (r.status >= 500 && !/^application\/json/i.test(ct))) {
      console.error(`hoc ${m} ${tuyen.dich}: edge/máy nhà trả ${r.status} (${ct || "không content-type"})`);
      if (r.body) r.body.cancel().catch(() => {});
      return r.status === 524 ? loi(LOI_CHAM_MAY_NHA, 504) : loi(LOI_MAY_NHA, 502);
    }
    return traVeMayNha(r);
  };

  if (m === "GET") {
    const q = queryHoc(url.searchParams, tuyen.query, tuyen.mau);
    if (q === null) return loi("Tham số truy vấn không hợp lệ");
    return traVe(await goiMayNha(env, tuyen.dich + q));
  }

  // POST: Origin bắt buộc và đúng (chặn chung ở fetch() cho qua khi thiếu Origin).
  if (req.headers.get("origin") !== url.origin) return loi("Sai nguồn gọi", 403);
  // Trần body như apiViec (header + độ dài thật, kể cả chunked); body trình duyệt bị bỏ: boi chỉ lấy từ phiên.
  if (Number(req.headers.get("content-length") || 0) > HOC_BODY_TOI_DA || !(await boBodyToiDa(req, HOC_BODY_TOI_DA))) {
    return loi("Dữ liệu quá lớn", 413);
  }
  const res = traVe(await goiMayNha(env, tuyen.dich, { method: "POST", body: { boi: user } }));
  console.log(`hoc ${tuyen.act} ${tuyen.ma} boi ${user} → ${res.status}`);
  return res;
}
