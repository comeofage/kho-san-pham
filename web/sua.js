// Màn sửa video #/sua/<uid>/<ma_video> (docs/sua-video.md §9, phiếu W-9). Dùng $, esc, api, toast, laChu (app.js)
// và taoViec, buocLog (viec.js) lúc chạy. Mọi chuỗi từ runner qua esc(); chữ trong textarea gán bằng .value.
"use strict";

// --- sua-thuan start ---
// Hàm thuần (không DOM, không biến ngoài trừ esc) để kiểm bằng node: cf/test/sua-web.test.mjs.
const RE_UID_SUA = /^\d{19}$/;
const RE_MA_VIDEO_SUA = /^[0-9a-f]{16}$/;
const RE_SHA_SUA = /^[0-9a-f]{64}$/;
const RE_DU_AN_SUA = /^[0-9a-f]{12}$/;
const RE_ID_VIEC_SUA = /^j\d{14}[a-z0-9]{4}$/;
const RE_TEN_CLIP_SUA = /^[0-9A-Za-z][0-9A-Za-z_.()\- ]{0,150}\.mp4$/; // §3.1, khớp Worker RE_TEN_CLIP
// Khớp Worker RE_CHU_PHU_DE_CAM: điều khiển C0/C1, xuống dòng (cả U+2028/2029), thẻ ASS { } \, < > và "-->".
const RE_CHU_CAM_SUA = /[\u0000-\u001f\u007f-\u009f\u2028\u2029{}\\<>]|-->/;
const RE_SURROGATE_SUA = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/;
const GIOI_HAN_SUA = { cau: 30, chu: 200, clip: 10, cho: 3, body: 16 * 1024, matKhau: 200 }; // §4.2, Worker
const LOG_SUA_TOI_DA = 1500; // ký tự log rút gọn trong khung tiến trình
const TEN_VAI_SUA = {
  hook: "Mở đầu", problem: "Vấn đề", pain_point: "Nỗi đau", painpoint: "Nỗi đau", benefit: "Lợi ích", proof: "Chứng minh",
  detail: "Chi tiết", demo: "Dùng thử", social_proof: "Khách dùng", socialproof: "Khách dùng", unboxing: "Mở hộp",
  broll: "Cảnh phụ", cta: "Chốt đơn",
};
const TT_SUA = { cho: "Chờ chạy", dang_chay: "Đang dựng", can_tra_loi: "Cần trả lời", cho_duyet: "Chờ duyệt", xong: "Xong", loi: "Lỗi", huy: "Đã huỷ" };
const TEN_LOAI_SUA = { sua_video: "Sửa video", hoan_tac_sua: "Dùng lại bản cũ" };
const coKhoaSua = (o, k) => !!o && typeof k === "string" && Object.prototype.hasOwnProperty.call(o, k);
const objSua = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : {});
const chuoiSua = (x) => (typeof x === "string" ? x : "");
const soSua = (x) => (typeof x === "number" && Number.isFinite(x) ? x : 0);
const lopTtSua = (tt) => (coKhoaSua(TT_SUA, tt) ? `tt-${tt}` : "tt-khac");
const nhanTtSua = (tt) => (coKhoaSua(TT_SUA, tt) ? TT_SUA[tt] : String(tt || "?"));

// Chữ hiển thị: gộp khoảng trắng, bỏ khoảng trắng trước dấu câu (§4.1).
function gopDau(s) {
  return chuoiSua(s).replace(/\s+/g, " ").replace(/ ([,.!?;:…])/g, "$1").trim();
}
// [mm:ss.s] cho câu phụ đề; mm:ss cho đoạn cảnh.
function gioCau(giay) {
  const t = Math.max(0, Math.round(soSua(giay) * 10) / 10);
  const p = Math.floor(t / 60), g = t - p * 60;
  return `${String(p).padStart(2, "0")}:${g.toFixed(1).padStart(4, "0")}`;
}
function gioCanh(giay) {
  const t = Math.max(0, Math.floor(soSua(giay)));
  return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
}

// "" nếu hợp lệ, ngược lại câu báo lỗi (cùng luật Worker kiemBanSua).
function kiemCauPhuDe(text) {
  if (typeof text !== "string" || RE_SURROGATE_SUA.test(text)) return "chữ không hợp lệ";
  const t = text.normalize("NFC");
  if (!t.trim()) return "không được để trống";
  if ([...t].length > GIOI_HAN_SUA.chu) return `tối đa ${GIOI_HAN_SUA.chu} ký tự`;
  if (RE_CHU_CAM_SUA.test(t)) return "không dùng xuống dòng, ký tự điều khiển, { } \\ < > hay -->";
  return "";
}

// nguon = may.ds.nguon của tab Duyệt ({goc, chi_tiet:[{ten}]}); ds = videos của GET /api/viec/sua-video/<uid>.
// Trả Map JSON[goc, ten] → mục của runner. Ghép theo (goc, ten), KHÔNG theo sua_luc (runner dùng mili giây).
function ghepVideoSua(nguon, ds) {
  const ra = new Map();
  if (!Array.isArray(nguon) || !Array.isArray(ds)) return ra;
  const co = new Set();
  for (const n of nguon) {
    if (!n || typeof n.goc !== "string" || !Array.isArray(n.chi_tiet)) continue;
    for (const c of n.chi_tiet) if (c && typeof c.ten === "string") co.add(JSON.stringify([n.goc, c.ten]));
  }
  for (const x of ds) {
    if (!x || typeof x !== "object" || typeof x.goc !== "string" || typeof x.ten !== "string") continue;
    if (typeof x.ma_video !== "string" || !RE_MA_VIDEO_SUA.test(x.ma_video)) continue;
    const k = JSON.stringify([x.goc, x.ten]);
    if (co.has(k) && !ra.has(k)) ra.set(k, x);
  }
  return ra;
}

// Chuẩn hoá chi tiết GET /api/viec/sua-video/<uid>/<ma> (§8.1) thành dạng web dùng.
function chuanSua(d) {
  const o = objSua(d), v = objSua(o.video), pd = objSua(o.phu_de);
  const luong = chuoiSua(o.luong) || chuoiSua(v.luong);
  const cau = (Array.isArray(pd.cau) ? pd.cau : [])
    .filter((c) => c && Number.isInteger(c.i) && c.i >= 0 && typeof c.text === "string")
    .map((c) => ({ i: c.i, start: soSua(c.start), end: soSua(c.end), text: c.text }));
  const n = pd.so_video_cung_take;
  return {
    video: { ma_video: chuoiSua(v.ma_video), du_an: chuoiSua(v.du_an), goc: chuoiSua(v.goc), ten: chuoiSua(v.ten),
      sua_luc: v.sua_luc, sua_duoc: v.sua_duoc !== false, ly_do: chuoiSua(v.ly_do) },
    luong, me: chuoiSua(o.me),
    phu_de: { sha: chuoiSua(pd.sha), co_words: pd.co_words === true, bien_the: pd.bien_the === true,
      so_video_cung_take: Number.isInteger(n) && n > 0 ? n : 0, cau },
    canh: Array.isArray(o.canh) ? o.canh : [],
    ghi_chu_luong_a: o.ghi_chu_luong_a === true || luong === "A",
    viec_mo: typeof o.viec_mo === "string" && RE_ID_VIEC_SUA.test(o.viec_mo) ? o.viec_mo : "",
    lich_su: Array.isArray(o.lich_su) ? o.lich_su : [],
  };
}

// canh của runner → {ds: mọi đoạn theo giờ, phu: đoạn phủ đổi được}.
function nhomCanh(canh) {
  const ds = (Array.isArray(canh) ? canh : [])
    .filter((c) => c && Number.isInteger(c.i) && c.i >= 0)
    .map((c) => {
      const role = chuoiSua(c.role), kind = chuoiSua(c.kind);
      return { i: c.i, kind, tu: soSua(c.out_start), den: soSua(c.out_end), role,
        vai: coKhoaSua(TEN_VAI_SUA, role) ? TEN_VAI_SUA[role] : role || "?",
        clip: chuoiSua(c.clip), doi_duoc: kind === "OVL" && c.doi_duoc === true, ly_do: chuoiSua(c.ly_do), laNen: kind === "BASE" };
    })
    .sort((a, b) => a.tu - b.tu || a.i - b.i);
  return { ds, phu: ds.filter((x) => x.doi_duoc) };
}

// Bản đang sửa trong bộ nhớ: phu_de Map<i, chữ>, doi_clip Map<seg, clip>, doi_cho [[a, b]].
const nhapRong = () => ({ phu_de: new Map(), doi_clip: new Map(), doi_cho: [] });

// "" nếu đổi chỗ a↔b được; ngược lại lý do.
function kiemDoiCho(d, nhap, a, b) {
  const phu = new Set(nhomCanh(d && d.canh).phu.map((x) => x.i));
  if (!phu.has(a) || !phu.has(b)) return "Chỉ đổi chỗ được hai đoạn phủ đổi được";
  if (a === b) return "Chọn một đoạn khác";
  if (nhap.doi_clip.has(a) || nhap.doi_clip.has(b)) return "Đoạn này đã đổi clip — bấm ↺ để bỏ trước";
  if (nhap.doi_cho.some((p) => p.includes(a) || p.includes(b))) return "Đoạn này đã nằm trong một cặp đổi chỗ";
  if (nhap.doi_cho.length >= GIOI_HAN_SUA.cho) return `Đổi chỗ tối đa ${GIOI_HAN_SUA.cho} cặp mỗi lần`;
  return "";
}

// Gom bản sửa gửi Worker (§4.2). Trả {so, coChu, body, loi}; body KHÔNG bao giờ chứa mật khẩu.
function dongThayDoi(d, nhap) {
  const pd = d.phu_de, cauTheoI = new Map(pd.cau.map((c) => [c.i, c]));
  const nhom = nhomCanh(d.canh), phu = new Map(nhom.phu.map((x) => [x.i, x]));
  let loi = "";
  const phu_de = [];
  for (const i of [...nhap.phu_de.keys()].sort((a, b) => a - b)) {
    const c = cauTheoI.get(i);
    if (!c) continue;
    const text = String(nhap.phu_de.get(i));
    const t = typeof text.normalize === "function" && !RE_SURROGATE_SUA.test(text) ? text.normalize("NFC") : text;
    if (t === gopDau(c.text).normalize("NFC")) continue;
    const l = kiemCauPhuDe(t);
    if (l && !loi) loi = `Câu ${i + 1}: ${l}`;
    phu_de.push({ i, text: t });
  }
  const doi_clip = [];
  for (const seg of [...nhap.doi_clip.keys()].sort((a, b) => a - b)) {
    const x = phu.get(seg), clip = nhap.doi_clip.get(seg);
    if (!x || typeof clip !== "string" || !RE_TEN_CLIP_SUA.test(clip) || clip === x.clip) continue;
    doi_clip.push({ seg, clip });
  }
  const doi_cho = nhap.doi_cho.filter((p) => Array.isArray(p) && p.length === 2 && phu.has(p[0]) && phu.has(p[1]) && p[0] !== p[1]).map((p) => [p[0], p[1]]);
  const coChu = phu_de.length > 0;
  const so = phu_de.length + doi_clip.length + doi_cho.length;
  const sua_luc = d.video.sua_luc;
  const body = { sua_luc, ...(coChu && RE_SHA_SUA.test(pd.sha) ? { phu_de_sha: pd.sha } : {}), phu_de, doi_clip, doi_cho };
  if (!loi && (!Number.isSafeInteger(sua_luc) || sua_luc < 0)) loi = "Thiếu thời điểm sửa của video — tải lại trang";
  if (!loi && phu_de.length > GIOI_HAN_SUA.cau) loi = `Sửa tối đa ${GIOI_HAN_SUA.cau} câu mỗi lần`;
  if (!loi && doi_clip.length > GIOI_HAN_SUA.clip) loi = `Đổi tối đa ${GIOI_HAN_SUA.clip} clip mỗi lần`;
  if (!loi && doi_cho.length > GIOI_HAN_SUA.cho) loi = `Đổi chỗ tối đa ${GIOI_HAN_SUA.cho} cặp mỗi lần`;
  if (!loi && coChu && pd.bien_the) loi = "Video này dùng biến thể phụ đề — chưa sửa được trên web";
  if (!loi && coChu && !pd.co_words) loi = "Take chưa có bản Whisper — không sửa trên web";
  if (!loi && coChu && !RE_SHA_SUA.test(pd.sha)) loi = "Thiếu mã phụ đề — tải lại trang";
  if (!loi && new TextEncoder().encode(JSON.stringify({ ...body, mat_khau: "x".repeat(GIOI_HAN_SUA.matKhau) })).length > GIOI_HAN_SUA.body) {
    loi = "Bản sửa quá lớn — sửa ít câu hơn mỗi lần";
  }
  return { so, coChu, body, loi };
}

// Body POST /luu: chỉ kèm mat_khau khi có sửa chữ (Q3); không sửa object gốc.
function thanLuu(body, matKhau) {
  const ra = { ...body };
  delete ra.mat_khau;
  if (Array.isArray(body.phu_de) && body.phu_de.length) ra.mat_khau = String(matKhau || "");
  return ra;
}

// Bản nháp (sessionStorage, theo ma_video). Gắn sua_luc + sha: video đã dựng lại hoặc phụ đề đổi → bỏ nháp.
const khoaNhapSua = (ma) => `kho_sua_nhap:${ma}`;
function nhapLuu(nhap, d) {
  return JSON.stringify({ v: 1, sua_luc: d.video.sua_luc, sha: d.phu_de.sha,
    phu_de: [...nhap.phu_de].map(([i, text]) => ({ i, text })), doi_clip: [...nhap.doi_clip].map(([seg, clip]) => ({ seg, clip })), doi_cho: nhap.doi_cho });
}
function nhapDoc(chuoi, d) {
  let o;
  try { o = JSON.parse(chuoi); } catch { return null; }
  if (!o || o.v !== 1 || o.sua_luc !== d.video.sua_luc || !Array.isArray(o.phu_de) || !Array.isArray(o.doi_clip) || !Array.isArray(o.doi_cho)) return null;
  if (o.phu_de.length && o.sha !== d.phu_de.sha) return null;
  const cau = new Set(d.phu_de.cau.map((c) => c.i));
  const phu = new Set(nhomCanh(d.canh).phu.map((x) => x.i));
  const nh = nhapRong();
  for (const x of o.phu_de) if (x && cau.has(x.i) && typeof x.text === "string" && x.text.length <= 1000) nh.phu_de.set(x.i, x.text);
  for (const x of o.doi_clip) if (x && phu.has(x.seg) && typeof x.clip === "string" && RE_TEN_CLIP_SUA.test(x.clip)) nh.doi_clip.set(x.seg, x.clip);
  for (const p of o.doi_cho) if (Array.isArray(p) && p.length === 2 && !kiemDoiCho(d, nh, p[0], p[1])) nh.doi_cho.push([p[0], p[1]]);
  return nh;
}
const nhapCoGi = (nh) => nh.phu_de.size + nh.doi_clip.size + nh.doi_cho.length > 0;
function luuNhapSua(store, ma, nhap, d) {
  try {
    if (!store) return;
    if (nhapCoGi(nhap)) store.setItem(khoaNhapSua(ma), nhapLuu(nhap, d));
    else store.removeItem(khoaNhapSua(ma));
  } catch { /* hết chỗ / chế độ riêng tư: bỏ qua */ }
}
// {trang_thai: "ok" | "khong" | "bo", nhap}
function docNhapSua(store, ma, d) {
  let s = null;
  try { s = store ? store.getItem(khoaNhapSua(ma)) : null; } catch { s = null; }
  if (typeof s !== "string") return { trang_thai: "khong", nhap: nhapRong() };
  const nh = nhapDoc(s, d);
  if (nh && nhapCoGi(nh)) return { trang_thai: "ok", nhap: nh };
  try { store.removeItem(khoaNhapSua(ma)); } catch { /* bỏ qua */ }
  return { trang_thai: "bo", nhap: nhapRong() };
}

// Kết quả POST /luu (Worker §8.3): {viec, trung, loi}.
function ketQuaLuu(r) {
  const x = objSua(r);
  if (x.status === 409) {
    const t = x.trung, id = typeof t === "string" ? t : objSua(t).id;
    return { viec: "", trung: typeof id === "string" && RE_ID_VIEC_SUA.test(id) ? id : "", loi: chuoiSua(x.loi) || "Không tạo được việc" };
  }
  const id = objSua(x.viec).id;
  if (typeof id === "string" && RE_ID_VIEC_SUA.test(id)) return { viec: id, trung: "", loi: "" };
  return { viec: "", trung: "", loi: chuoiSua(x.loi) || "Máy nhà trả dữ liệu lạ" };
}

const urlAnhSua = (uid, duAn, clip, k) => `/api/video/${uid}/anh?du_an=${encodeURIComponent(duAn)}&ten=${encodeURIComponent(clip)}&k=${k}`;
const urlClipSua = (uid, duAn, clip) => `/api/video/${uid}/clip?du_an=${encodeURIComponent(duAn)}&ten=${encodeURIComponent(clip)}`;
const anhCoSua = (uid, duAn, clip) => RE_UID_SUA.test(uid) && RE_DU_AN_SUA.test(duAn) && RE_TEN_CLIP_SUA.test(clip);

// Một câu phụ đề. textarea để trống: chữ gán bằng .value sau khi vẽ.
function cauHtml(c, o = {}) {
  return `<div class="sua-cau${o.daSua ? " da-sua" : ""}" data-cau="${c.i}">
    <div class="row sua-cau-dau"><button type="button" class="sua-gio" data-tua="${c.i}" title="Tua tới câu này">[${gioCau(c.start)}]</button>
      <button type="button" class="btn ghost sm" data-cau-hoan="${c.i}" title="Trả về chữ cũ"${o.daSua ? "" : " hidden"}>↺</button>
      <span class="small err" data-cau-loi></span></div>
    <textarea class="sua-o" rows="1" maxlength="${GIOI_HAN_SUA.chu}" data-cau-o="${c.i}"${o.khoa ? " readonly" : ""}></textarea>
    <div class="small muted sua-cu"${o.daSua ? "" : " hidden"}>Cũ: ${esc(gopDau(c.text))}</div>
  </div>`;
}

// Một đoạn trong thẻ Cảnh. o: {uid, duAn, luong, clipMoi, choVoi, clipCho, chonCho, khoa}.
function canhDongHtml(r, o = {}) {
  const gio = `<b>${gioCanh(r.tu)}–${gioCanh(r.den)}</b>`;
  const anh = (clip) => (anhCoSua(o.uid, o.duAn, clip)
    ? `<img class="sua-anh" src="${esc(urlAnhSua(o.uid, o.duAn, clip, "0"))}" loading="lazy" alt="">` : `<div class="sua-anh"></div>`);
  if (r.laNen) {
    return `<div class="sua-canh nen" data-seg="${r.i}"><div class="sua-anh"></div>
      <div class="sua-canh-body">${gio} · ${o.luong === "A" ? "Nền đen (Adam)" : "Nền (người nói)"}</div></div>`;
  }
  const moi = typeof o.clipMoi === "string" ? o.clipMoi : "";
  const cho = Number.isInteger(o.choVoi) ? o.choVoi : null;
  const thay = !!moi || cho !== null;
  const hien = moi || (cho !== null && typeof o.clipCho === "string" ? o.clipCho : r.clip);
  let nut = "";
  if (!o.khoa) {
    if (Number.isInteger(o.chonCho)) nut = r.i !== o.chonCho && r.doi_duoc && !thay ? `<button type="button" class="btn sm" data-canh-cho="${r.i}">Chọn</button>` : "";
    else if (thay) nut = `<button type="button" class="btn ghost sm" data-canh-hoan="${r.i}" title="Trả về như cũ">↺</button>`;
    else if (r.doi_duoc) nut = `<button type="button" class="btn sm" data-canh-doi="${r.i}">Đổi</button>`;
  }
  return `<div class="sua-canh${thay ? " da-sua" : ""}${!r.doi_duoc ? " khoa" : ""}" data-seg="${r.i}">
    ${anh(hien)}
    <div class="sua-canh-body"><span class="small muted">#${r.i}</span> ${gio} · ${esc(r.vai)}
      <div class="small muted sua-ten-clip">${esc(r.clip)}</div>
      ${moi ? `<div class="small">→ ${esc(moi)}</div>` : ""}
      ${cho !== null ? `<div class="small">⇄ đổi chỗ với #${cho}${o.clipCho ? ": " + esc(o.clipCho) : ""}</div>` : ""}
      ${!r.doi_duoc && r.ly_do ? `<div class="small muted">${esc(r.ly_do)}</div>` : ""}
    </div>
    <div class="sua-canh-nut">${nut}</div>
  </div>`;
}

// Một ứng viên trong ngăn kéo "Đổi".
function ungVienHtml(u, k, o = {}) {
  const dung = u.dung_duoc !== false;
  const dur = typeof u.dur === "number" && Number.isFinite(u.dur) ? `${u.dur.toFixed(1)} s` : "";
  return `<div class="sua-uv${dung ? "" : " mo"}" data-uv="${k}">
    <div class="sua-uv-xem">${u.co_anh === true && anhCoSua(o.uid, o.duAn, u.clip)
      ? `<img class="sua-anh" src="${esc(urlAnhSua(o.uid, o.duAn, u.clip, "0"))}" loading="lazy" alt="">` : `<div class="sua-anh"></div>`}</div>
    <div class="small sua-uv-desc">${esc(chuoiSua(u.desc) || u.clip)}</div>
    <div class="small muted">${esc(dur)}${dung ? "" : ` · ${esc(chuoiSua(u.ly_do) || "không dùng được")}`}</div>
    <div class="row"><button type="button" class="btn ghost sm" data-uv-xem="${k}">▶ Xem thử</button>
      <button type="button" class="btn sm" data-uv-chon="${k}"${dung ? "" : " disabled"}>Chọn</button></div>
  </div>`;
}

// Lịch sử sửa: mới nhất trước; nút hoàn tác chỉ ở lần gần nhất có hoan_tac_duoc.
function lichSuHtml(ls, o = {}) {
  const ds = (Array.isArray(ls) ? ls : []).filter((x) => x && typeof x === "object")
    .slice().sort((a, b) => chuoiSua(b.luc).localeCompare(chuoiSua(a.luc)));
  if (!ds.length) return `<p class="small muted">Chưa sửa lần nào.</p>`;
  const kHoan = ds.findIndex((x) => x.hoan_tac_duoc === true && x.loai === "sua_video" && typeof x.viec === "string" && RE_ID_VIEC_SUA.test(x.viec));
  return `<ul class="sua-ls">${ds.map((x, k) => {
    const id = typeof x.viec === "string" && RE_ID_VIEC_SUA.test(x.viec) ? x.viec : "";
    const loai = coKhoaSua(TEN_LOAI_SUA, x.loai) ? TEN_LOAI_SUA[x.loai] : chuoiSua(x.loai);
    return `<li><span class="small muted">${esc(chuoiSua(x.luc).slice(0, 16).replace("T", " "))} · ${esc(chuoiSua(x.boi))}</span>
      ${esc(loai)} <span class="badge ${lopTtSua(x.trang_thai)}">${esc(nhanTtSua(x.trang_thai))}</span>
      ${id ? `<a class="small" href="#/viec/${id}">việc</a>` : ""}
      ${k === kHoan ? `<button type="button" class="btn ghost sm" data-ls-hoan="${id}"${o.khoa ? " disabled" : ""}>↩ Dùng lại bản cũ</button>` : ""}</li>`;
  }).join("")}</ul>`;
}

// Nút ✏ Sửa trong thẻ tab Duyệt (x = mục của ghepVideoSua).
function nutSuaHtml(x, uid) {
  if (!x || typeof x.ma_video !== "string" || !RE_MA_VIDEO_SUA.test(x.ma_video) || typeof uid !== "string" || !RE_UID_SUA.test(uid)) return "";
  if (typeof x.viec_mo === "string" && RE_ID_VIEC_SUA.test(x.viec_mo)) return `<a class="btn ghost sm dv-sua-dang" href="#/viec/${x.viec_mo}">⏳ đang dựng lại…</a>`;
  if (x.sua_duoc === true) return `<a class="btn ghost sm" href="#/sua/${uid}/${x.ma_video}">✏ Sửa</a>`;
  return `<button type="button" class="btn ghost sm mo" data-dv-sua-ly-do="${esc(chuoiSua(x.ly_do) || "Video này chưa sửa được trên web")}">✏ Sửa</button>`;
}

// Khung tiến trình của việc sửa/hoàn tác. v: {id, loai, tt, log, loi}.
function tienHtml(v) {
  const id = typeof v.id === "string" && RE_ID_VIEC_SUA.test(v.id) ? v.id : "";
  const ht = v.loai === "hoan_tac_sua";
  return `<div class="sua-tien">
    <div class="row"><b>${ht ? "↩ Dùng lại bản cũ" : "🔁 Dựng lại video"}</b>
      <span class="badge ${lopTtSua(v.tt)}">${esc(v.tt ? nhanTtSua(v.tt) : "Đang hỏi…")}</span>
      ${id ? `<a class="small" href="#/viec/${id}">mở việc</a>` : ""}</div>
    ${v.tt === "xong" ? `<p class="small">✓ Xong. Video đã được thay — phải duyệt lại trước khi đăng.</p>
      <div class="row"><button type="button" class="btn sm" data-tien-xem>▶ Xem bản mới</button>${ht ? "" : `<button type="button" class="btn ghost sm" data-tien-hoan>↩ Dùng lại bản cũ</button>`}</div>` : ""}
    ${v.tt === "loi" || v.tt === "huy" ? `<div class="vj-loi">${esc(chuoiSua(v.loi) || (v.tt === "huy" ? "Việc đã huỷ" : "Dựng lại không thành công"))}</div>
      ${id ? `<p class="small"><a href="#/viec/${id}">Mở việc để Chạy lại →</a></p>` : ""}` : ""}
    ${v.log ? `<pre class="vj-log sua-log">${esc(v.log)}</pre>` : ""}
  </div>`;
}
// --- sua-thuan end ---

// ---------- phần có DOM ----------
let phienSua = 0;   // tăng mỗi lần rời/vào màn sửa: phản hồi về muộn của màn cũ bị bỏ
let suaTrang = null; // {timers, lamMoi} của màn sửa đang mở

function dungSua() {
  phienSua++;
  if (suaTrang) suaTrang.timers.forEach((t) => clearInterval(t));
  suaTrang = null;
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && suaTrang) suaTrang.lamMoi();
});
const khoPhienSua = () => { try { return window.sessionStorage; } catch { return null; } };

async function renderSua(uid, ma) {
  const app = $("#app");
  if (!laChu()) { app.innerHTML = `<p class="center muted">Trang này chỉ dành cho chủ kho. <a href="#/kho">← Về kho</a></p>`; return; }
  if (!RE_UID_SUA.test(uid) || !RE_MA_VIDEO_SUA.test(ma)) { app.innerHTML = `<p class="center">Mã video không hợp lệ. <a href="#/kho">← Về kho</a></p>`; return; }
  const tk = phienSua;
  const s = { d: null, nhom: null, nhap: nhapRong(), tab: "phu_de", dangTai: false, dangLuu: false, viec: null, ngan: 0, chonCho: null, uv: [], timers: [] };
  suaTrang = { timers: s.timers, lamMoi: () => { if (s.viec && !s.viec.het) hoiViec(); } };
  const ve1 = (sel) => (tk === phienSua ? $(sel) : null);
  const dangKhoa = () => !s.d || !s.d.video.sua_duoc || s.dangLuu || !!(s.viec && !s.viec.het);
  const luuNhap = () => luuNhapSua(khoPhienSua(), ma, s.nhap, s.d);
  const choCua = (i) => { const p = s.nhap.doi_cho.find((x) => x.includes(i)); return p ? (p[0] === i ? p[1] : p[0]) : null; };

  const veLoi = (msg) => {
    app.innerHTML = `<p><a href="#/sp/${uid}" class="small">← Về sản phẩm</a></p><p class="err">⚠ ${esc(msg)}</p>
      <p><button class="btn sm" id="sua-tai-lai">Tải lại</button></p>`;
    $("#sua-tai-lai").addEventListener("click", () => tai());
  };

  const tai = async (phat = false) => {
    if (s.dangTai || tk !== phienSua) return;
    s.dangTai = true; // chặn tải chồng TRƯỚC await
    if (!s.d) app.innerHTML = `<p class="muted center">Đang hỏi máy nhà video này…</p>`;
    let r;
    try { r = await api(`viec/sua-video/${uid}/${ma}`); }
    catch (err) { if (tk === phienSua) veLoi(err.message); return; }
    finally { s.dangTai = false; }
    if (tk !== phienSua) return;
    s.d = chuanSua(r);
    s.nhom = nhomCanh(s.d.canh);
    s.chonCho = null;
    const nh = docNhapSua(khoPhienSua(), ma, s.d);
    s.nhap = nh.nhap;
    if (nh.trang_thai === "ok") toast("Đã khôi phục phần đang sửa dở");
    else if (nh.trang_thai === "bo") toast("Bản nháp cũ không còn khớp (video đã dựng lại hoặc phụ đề đổi) — đã bỏ");
    ve();
    if (phat) { const vd = $("#sua-vd"); if (vd) { vd.scrollIntoView({ block: "nearest" }); vd.play().catch(() => {}); } }
    // việc đang mở của video (mở lại trang giữa chừng); bỏ qua việc vừa theo dõi xong để không lặp tải
    if (s.d.viec_mo && (!s.viec || (s.viec.het && s.viec.id !== s.d.viec_mo))) theoDoi(s.d.viec_mo, "");
  };

  const ve = () => {
    const v = s.d.video;
    const nhanLuong = s.d.luong === "A" ? `Adam${s.d.me ? " · mẻ " + s.d.me : ""}` : "Giọng thật";
    const src = `/api/video/${uid}/xem?goc=${encodeURIComponent(v.goc)}&ten=${encodeURIComponent(v.ten)}&v=${encodeURIComponent(String(v.sua_luc))}`;
    app.innerHTML = `<p><a href="#/sp/${uid}" class="small">← Về sản phẩm</a></p>
      <div class="sua">
        <div class="sua-dau">
          <div class="sua-ten"><b>${esc(v.ten)}</b> <span class="badge b-da_phan_tich">${esc(nhanLuong)}</span></div>
          ${s.d.ghi_chu_luong_a ? `<div class="small muted">Dựng lại bằng tham số mặc định — chuyển cảnh/nhạc có thể khác nhẹ.</div>` : ""}
          <video id="sua-vd" controls playsinline preload="metadata" src="${esc(src)}"></video>
        </div>
        ${v.sua_duoc ? "" : `<div class="vj-loi">Video này chưa sửa được trên web: ${esc(v.ly_do || "không rõ lý do")}</div>`}
        <div id="sua-tien"></div>
        <div class="tabs"><button class="tab" data-sua-tab="phu_de">💬 Phụ đề (${s.d.phu_de.cau.length})</button>
          <button class="tab" data-sua-tab="canh">🎞 Cảnh (${s.nhom.ds.length})</button></div>
        <div class="panel" id="sua-the"></div>
        <h3>Lịch sử sửa</h3><div id="sua-ls"></div>
      </div>
      <div class="sua-thanh" id="sua-thanh">
        <div class="row"><b id="sua-dem"></b> <span class="small err" id="sua-loi"></span></div>
        <input type="password" id="sua-mk" autocomplete="current-password" maxlength="${GIOI_HAN_SUA.matKhau}" placeholder="Mật khẩu (bắt buộc khi sửa chữ phụ đề)" hidden>
        <div class="row end"><button type="button" class="btn ghost sm" id="sua-huy">Huỷ</button>
          <button type="button" class="btn" id="sua-luu">Lưu và dựng lại</button></div>
      </div>
      <div class="sua-ngan" id="sua-ngan" hidden></div>`;
    const vd = $("#sua-vd");
    vd.addEventListener("error", () => { if (vd.getAttribute("src")) toast("⚠ Không phát được — máy nhà tắt hoặc file đã bị chuyển"); });
    document.querySelectorAll("[data-sua-tab]").forEach((b) => b.addEventListener("click", () => { s.tab = b.dataset.suaTab; s.chonCho = null; veThe(); }));
    $("#sua-huy").addEventListener("click", () => {
      if (s.dangLuu || !confirm("Bỏ hết thay đổi chưa lưu?")) return;
      s.nhap = nhapRong(); s.chonCho = null; luuNhap(); veThe(); capNhatThanh();
    });
    $("#sua-luu").addEventListener("click", luu);
    $("#sua-ngan").addEventListener("click", (e) => { if (e.target === e.currentTarget) dongNgan(); });
    veTien(); veThe(); veLs(); capNhatThanh();
  };

  const capNhatThanh = () => {
    const thanh = ve1("#sua-thanh");
    if (!thanh || !s.d) return;
    const t = dongThayDoi(s.d, s.nhap);
    thanh.hidden = !s.d.video.sua_duoc || !!(s.viec && !s.viec.het);
    $("#sua-dem").textContent = t.so ? `${t.so} thay đổi` : "Chưa có thay đổi";
    $("#sua-loi").textContent = t.loi;
    const mk = $("#sua-mk");
    mk.hidden = !t.coChu;
    if (!t.coChu) mk.value = "";
    $("#sua-huy").disabled = !t.so || s.dangLuu;
    const nut = $("#sua-luu");
    nut.disabled = !t.so || !!t.loi || s.dangLuu;
    nut.textContent = s.dangLuu ? "Đang gửi…" : "Lưu và dựng lại";
  };

  const gian = (o) => { o.style.height = "auto"; o.style.height = `${o.scrollHeight + 2}px`; };
  const capNhatCau = (el, c) => {
    const o = $("[data-cau-o]", el);
    const daSua = s.nhap.phu_de.has(c.i);
    el.classList.toggle("da-sua", daSua);
    $("[data-cau-hoan]", el).hidden = !daSua;
    $(".sua-cu", el).hidden = !daSua;
    $("[data-cau-loi]", el).textContent = daSua ? kiemCauPhuDe(o.value) : "";
  };

  const veThe = () => {
    const the = ve1("#sua-the");
    if (!the || !s.d) return;
    document.querySelectorAll("[data-sua-tab]").forEach((b) => b.classList.toggle("on", b.dataset.suaTab === s.tab));
    const khoa = dangKhoa();
    if (s.tab === "phu_de") {
      const pd = s.d.phu_de;
      const khoaChu = khoa || pd.bien_the || !pd.co_words;
      const bao = [];
      if (pd.so_video_cung_take > 0) bao.push(`Lời này dùng chung cho ${pd.so_video_cung_take} video khác — chúng giữ chữ cũ.`);
      if (pd.bien_the) bao.push("Video này dùng biến thể phụ đề — chưa sửa chữ được trên web.");
      else if (!pd.co_words) bao.push("Take chưa có bản Whisper — không sửa chữ trên web.");
      the.innerHTML = bao.map((x) => `<div class="vj-can-ban">${esc(x)}</div>`).join("")
        + (pd.cau.length ? pd.cau.map((c) => cauHtml(c, { daSua: s.nhap.phu_de.has(c.i), khoa: khoaChu })).join("") : `<p class="muted">Không có câu phụ đề.</p>`)
        + `<p class="small muted">Lưu chữ sẽ ghi bản phụ đề sửa tay cho take này (từ đó ưu tiên hơn kịch bản gốc) và cần mật khẩu.</p>`;
      const theoI = new Map(pd.cau.map((c) => [c.i, c]));
      the.querySelectorAll(".sua-cau").forEach((el) => {
        const c = theoI.get(Number(el.dataset.cau));
        if (!c) return;
        const o = $("[data-cau-o]", el);
        o.value = s.nhap.phu_de.has(c.i) ? s.nhap.phu_de.get(c.i) : gopDau(c.text);
        gian(o); capNhatCau(el, c);
        o.addEventListener("input", () => {
          if (o.readOnly) return;
          if (o.value.normalize("NFC") === gopDau(c.text).normalize("NFC")) s.nhap.phu_de.delete(c.i);
          else s.nhap.phu_de.set(c.i, o.value);
          gian(o); capNhatCau(el, c); luuNhap(); capNhatThanh();
        });
        $("[data-cau-hoan]", el).addEventListener("click", () => {
          if (dangKhoa()) return;
          s.nhap.phu_de.delete(c.i); o.value = gopDau(c.text);
          gian(o); capNhatCau(el, c); luuNhap(); capNhatThanh();
        });
        $("[data-tua]", el).addEventListener("click", () => {
          const vd = $("#sua-vd");
          if (!vd) return;
          try { vd.currentTime = c.start; } catch { /* chưa có metadata */ }
          vd.play().catch(() => {});
        });
      });
      return;
    }
    const duAn = s.d.video.du_an;
    const theoSeg = new Map(s.nhom.ds.map((x) => [x.i, x]));
    the.innerHTML = (Number.isInteger(s.chonCho) ? `<div class="vj-can-ban">Chọn đoạn thứ hai để đổi chỗ với #${s.chonCho}
        <button type="button" class="btn ghost sm" data-cho-thoi>Thôi</button></div>` : "")
      + (s.nhom.ds.length ? s.nhom.ds.map((x) => {
        const cho = choCua(x.i);
        return canhDongHtml(x, { uid, duAn, luong: s.d.luong, clipMoi: s.nhap.doi_clip.get(x.i) || "", choVoi: cho,
          clipCho: cho !== null && theoSeg.get(cho) ? theoSeg.get(cho).clip : "", chonCho: s.chonCho, khoa });
      }).join("") : `<p class="muted">Không có đoạn nào.</p>`);
    the.querySelectorAll("img.sua-anh").forEach((im) => im.addEventListener("error", () => im.replaceWith(Object.assign(document.createElement("div"), { className: "sua-anh" }))));
    $("[data-cho-thoi]", the)?.addEventListener("click", () => { s.chonCho = null; veThe(); });
    the.querySelectorAll("[data-canh-doi]").forEach((b) => b.addEventListener("click", () => moNgan(Number(b.dataset.canhDoi))));
    the.querySelectorAll("[data-canh-hoan]").forEach((b) => b.addEventListener("click", () => {
      if (dangKhoa()) return;
      const i = Number(b.dataset.canhHoan);
      s.nhap.doi_clip.delete(i);
      s.nhap.doi_cho = s.nhap.doi_cho.filter((p) => !p.includes(i));
      luuNhap(); veThe(); capNhatThanh();
    }));
    the.querySelectorAll("[data-canh-cho]").forEach((b) => b.addEventListener("click", () => {
      if (dangKhoa() || !Number.isInteger(s.chonCho)) return;
      const a = s.chonCho, c = Number(b.dataset.canhCho);
      const l = kiemDoiCho(s.d, s.nhap, a, c);
      if (l) { toast("⚠ " + l); return; }
      s.nhap.doi_cho.push([a, c]); s.chonCho = null;
      luuNhap(); veThe(); capNhatThanh(); toast(`⇄ Đổi chỗ #${a} với #${c}`);
    }));
  };

  const veLs = () => {
    const el = ve1("#sua-ls");
    if (!el || !s.d) return;
    el.innerHTML = lichSuHtml(s.d.lich_su, { khoa: dangKhoa() });
    el.querySelectorAll("[data-ls-hoan]").forEach((b) => b.addEventListener("click", () => hoanTac(b.dataset.lsHoan, b)));
  };

  // ----- ngăn kéo "Đổi" -----
  const dungVideoNgan = () => document.querySelectorAll("#sua-ngan video").forEach((v) => { v.pause(); v.removeAttribute("src"); v.load(); });
  const dongNgan = () => {
    s.ngan++; // phản hồi ứng viên đang chờ bị bỏ
    const ngan = ve1("#sua-ngan");
    if (!ngan) return;
    dungVideoNgan();
    ngan.hidden = true; ngan.innerHTML = "";
  };
  const moNgan = async (seg) => {
    const x = s.nhom && s.nhom.ds.find((r) => r.i === seg);
    if (!x || !x.doi_duoc || dangKhoa()) return;
    if (choCua(seg) !== null) { toast("Đoạn này đang đổi chỗ — bấm ↺ để bỏ trước"); return; }
    const lan = ++s.ngan; // đánh số lần mở TRƯỚC await
    const ngan = $("#sua-ngan");
    const coCho = s.nhom.phu.some((p) => p.i !== seg && !s.nhap.doi_clip.has(p.i) && choCua(p.i) === null) && s.nhap.doi_cho.length < GIOI_HAN_SUA.cho;
    ngan.hidden = false;
    ngan.innerHTML = `<div class="sua-ngan-hop" role="dialog" aria-label="Đổi cảnh">
      <div class="row sua-ngan-dau"><b>Đổi #${x.i} · ${gioCanh(x.tu)}–${gioCanh(x.den)} · ${esc(x.vai)}</b>
        <button type="button" class="btn ghost sm" data-ngan-dong>✕</button></div>
      <div class="sua-ngan-than" id="sua-ngan-than"><p class="muted">Đang tải clip cùng vai…</p></div>
      <div class="row sua-ngan-cuoi">${coCho ? `<button type="button" class="btn ghost sm" data-ngan-cho>⇄ Đổi chỗ với cảnh khác…</button>` : ""}</div>
    </div>`;
    $("[data-ngan-dong]", ngan).addEventListener("click", dongNgan);
    $("[data-ngan-cho]", ngan)?.addEventListener("click", () => { dongNgan(); s.chonCho = seg; veThe(); toast("Chọn đoạn thứ hai"); });
    let r;
    try { r = await api(`viec/sua-video/${uid}/${ma}/ung-vien?seg=${seg}`); }
    catch (err) {
      const t = tk === phienSua && lan === s.ngan ? $("#sua-ngan-than") : null;
      if (t) t.innerHTML = `<p class="err">⚠ ${esc(err.message)}</p>`;
      return;
    }
    if (tk !== phienSua || lan !== s.ngan) return; // đã đóng/mở đoạn khác: bỏ phản hồi muộn
    const than = $("#sua-ngan-than");
    if (!than) return; // trang vừa vẽ lại: ngăn kéo cũ không còn
    s.uv = (Array.isArray(r.ung_vien) ? r.ung_vien : []).filter((u) => u && typeof u.clip === "string" && RE_TEN_CLIP_SUA.test(u.clip)).slice(0, 60);
    than.innerHTML = s.uv.length ? `<div class="sua-uv-luoi">${s.uv.map((u, k) => ungVienHtml(u, k, { uid, duAn: s.d.video.du_an })).join("")}</div>`
      : `<p class="muted">Không có clip cùng vai trong kho cắt.</p>`;
    than.querySelectorAll("img.sua-anh").forEach((im) => im.addEventListener("error", () => im.replaceWith(Object.assign(document.createElement("div"), { className: "sua-anh" }))));
    than.querySelectorAll("[data-uv-xem]").forEach((b) => b.addEventListener("click", () => {
      const u = s.uv[Number(b.dataset.uvXem)];
      const o = b.closest(".sua-uv") && $(".sua-uv-xem", b.closest(".sua-uv"));
      if (!u || !o) return;
      dungVideoNgan(); // chỉ phát 1 clip một lúc
      o.innerHTML = `<video class="sua-anh" controls playsinline preload="none"></video>`;
      const vd = $("video", o);
      vd.addEventListener("error", () => { if (vd.getAttribute("src")) toast("⚠ Không phát được clip này"); });
      vd.src = urlClipSua(uid, s.d.video.du_an, u.clip);
      vd.play().catch(() => {});
    }));
    than.querySelectorAll("[data-uv-chon]").forEach((b) => b.addEventListener("click", () => {
      const u = s.uv[Number(b.dataset.uvChon)];
      if (!u || u.dung_duoc === false || dangKhoa()) return;
      if (u.clip === x.clip) s.nhap.doi_clip.delete(seg); else s.nhap.doi_clip.set(seg, u.clip);
      dongNgan(); luuNhap(); veThe(); capNhatThanh();
      toast(`✓ #${seg} → ${u.clip}`);
    }));
  };

  // ----- lưu -----
  const luu = async () => {
    if (s.dangLuu || tk !== phienSua || !s.d || dangKhoa()) return;
    const t = dongThayDoi(s.d, s.nhap);
    if (!t.so) { toast("Chưa có thay đổi nào"); return; }
    if (t.loi) { toast("⚠ " + t.loi); return; }
    const o = $("#sua-mk");
    const mk = t.coChu && o ? o.value : "";
    if (o) o.value = ""; // mật khẩu chỉ sống trong biến cục bộ của lượt gửi này
    if (t.coChu && !mk) { toast("Sửa chữ phụ đề cần nhập mật khẩu"); if (o) o.focus(); return; }
    s.dangLuu = true; // khoá trước khi gửi: chặn bấm đúp
    dongNgan(); capNhatThanh(); veThe();
    try {
      const r = await api(`viec/sua-video/${uid}/${ma}/luu`, thanLuu(t.body, mk));
      if (tk !== phienSua) return; // đã rời màn: không đụng DOM trang mới
      const k = ketQuaLuu(r);
      if (k.viec) {
        s.nhap = nhapRong(); luuNhap();
        toast("✓ Đã gửi — máy nhà đang dựng lại");
        theoDoi(k.viec, "sua_video");
      } else if (k.trung) {
        toast("Video này đang được dựng lại");
        theoDoi(k.trung, "");
      } else toast("⚠ " + k.loi);
    } catch (err) { if (tk === phienSua) toast("⚠ " + err.message); }
    finally {
      s.dangLuu = false;
      if (tk === phienSua) { capNhatThanh(); veThe(); veLs(); }
    }
  };
  // --- het luu ---

  // ----- tiến trình việc (thăm dò 3 s) -----
  const veTien = () => {
    const el = ve1("#sua-tien");
    if (!el) return;
    el.innerHTML = s.viec ? tienHtml(s.viec) : "";
    $("[data-tien-xem]", el)?.addEventListener("click", () => tai(true));
    const h = $("[data-tien-hoan]", el);
    if (h) h.addEventListener("click", () => hoanTac(s.viec.id, h));
  };
  const theoDoi = (id, loai) => {
    if (!RE_ID_VIEC_SUA.test(id) || tk !== phienSua) return;
    s.timers.splice(0).forEach((t) => clearInterval(t));
    s.viec = { id, loai, tt: "", log: "", logTu: 0, loi: "", het: false, dangTai: false };
    veTien(); capNhatThanh(); veThe(); veLs();
    s.timers.push(setInterval(() => { if (document.visibilityState === "visible") hoiViec(); }, 3000));
    hoiViec();
  };
  const hoiViec = async () => {
    const v = s.viec;
    if (!v || v.dangTai || v.het || tk !== phienSua) return;
    v.dangTai = true; // chặn hỏi chồng TRƯỚC await
    try {
      const r = await api(`viec/${v.id}`);
      if (tk !== phienSua || s.viec !== v) return;
      const x = objSua(r && r.viec);
      if (typeof x.trang_thai === "string") v.tt = x.trang_thai;
      if (typeof x.loai === "string") v.loai = x.loai;
      v.loi = chuoiSua(x.loi);
      try {
        const l = await api(`viec/${v.id}/log?tu=${v.logTu}`);
        if (tk !== phienSua || s.viec !== v) return;
        const b = buocLog(l, v.logTu);
        v.logTu = b.tu; v.log = (v.log + b.them).slice(-LOG_SUA_TOI_DA);
      } catch { /* log không bắt buộc */ }
      if (["xong", "loi", "huy"].includes(v.tt)) {
        v.het = true;
        s.timers.splice(0).forEach((t) => clearInterval(t));
      }
      veTien();
      if (v.het) {
        capNhatThanh(); veThe(); veLs();
        if (v.tt === "xong") tai(); // video đã thay: lấy sua_luc/lịch sử mới, lần lưu sau không gửi sua_luc cũ
      }
    } catch (err) {
      if (tk === phienSua && s.viec === v) { v.loi = err.message; veTien(); }
    } finally { v.dangTai = false; }
  };
  const hoanTac = async (viecGoc, nut) => {
    if (tk !== phienSua || !s.d || !RE_ID_VIEC_SUA.test(viecGoc)) return;
    if (!RE_DU_AN_SUA.test(s.d.video.du_an)) { toast("⚠ Thiếu mã dự án — tải lại trang"); return; }
    if (!confirm("Dùng lại bản cũ của video này? Bản hiện tại sẽ được sao lưu.")) return;
    const id = await taoViec("hoan_tac_sua", { uid, du_an: s.d.video.du_an, ma_video: ma, viec_goc: viecGoc }, nut); // taoViec khoá chống bấm đúp
    if (tk !== phienSua) return;
    if (id) theoDoi(id, "hoan_tac_sua");
  };

  await tai();
}
