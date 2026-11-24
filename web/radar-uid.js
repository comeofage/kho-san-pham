// Radar UID (D16, docs/radar-uid.md §8–§10): tab "📡 Radar UID" (#/theo-doi, mục menu thứ 6, CHỈ chủ kho).
// RU-W6: trang chính chỉ liệt kê UID CHÍNH (thẻ có ảnh, bấm vào #/theo-doi/<goc>); UID tương tự + chỉ số nằm ở trang chi tiết (chỉ số trong <details>).
// Ảnh: chỉ <img> khi URL thuộc cdn.echotik.live (CSP img-src đúng host này); thiếu/hết hạn → ô xám, không báo lỗi.
// Chủ nhập 1 UID gốc → máy nhà tìm ≤ 10 SP "tương tự", chụp snapshot mỗi ngày; bảng xếp hạng UID "đang có đà".
// Script thường, chung phạm vi toàn cục với app.js: mọi tên cấp đỉnh bắt đầu bằng "rdu"/"RDU_" (P2-7, test cf/test/menu-web.test.mjs).
// Dùng của app.js lúc chạy: $, esc, api, toast, copy, phienCT. Được gọi từ khung.js (rduRender, rduDung) qua typeof.
// KHÔNG điểm tổng hợp ảo: số chính là trung vị Δview/video/24h; thiếu = "—" kèm lý do; chưa đủ bằng chứng = số xám + câu cố định.
// Nút "📮 Poster" KHÔNG ghi vào Poster V2 (§10): chỉ Sao chép UID + mở Poster V2 › Folders, ô tick đối chiếu SKU với UID không phải gốc.
// CSP script-src 'self': KHÔNG script inline, KHÔNG thuộc tính on…= — sự kiện gắn bằng addEventListener.
// ID 19 chữ số luôn là CHUỖI (> 2^53): cấm ép sang số; chỉ vào thuộc tính/URL sau khi khớp ^\d{19}$.
"use strict";

// --- radar-uid-thuan start ---
// Hàm thuần: không đụng DOM/fetch; chỉ dùng `esc` (app.js) lúc gọi. Mọi chuỗi từ API vẽ ra HTML đều qua esc.
const RDU_RE_UID = /^\d{19}$/;
const RDU_RE_LINK = /\/(?:product|pdp)\/(?:[^/?#\s]+\/)?(\d{19})(?!\d)/;
const RDU_RE_NGAY = /^(\d{4})-(\d{2})-(\d{2})$/;
const RDU_RE_ANH = /^https:\/\/cdn\.echotik\.live\/[A-Za-z0-9._\/-]{1,300}$/; // đúng 1 host (khớp CSP img-src trong web/_headers)
const RDU_RE_LOI_CAU_HINH = /^(Chưa cấu hình bộ chạy việc|Khoá ký bộ chạy việc không hợp lệ \(KY_RIENG\))$/;
const RDU_KY_DIEU_KHIEN = /[\u0000-\u001f\u007f]/g;
const RDU_SNAPSHOT_CAN = 4; // SNAPSHOT_TOI_THIEU (§5.4): chỉ để hiện "k/4 snapshot"
const RDU_SPARK = "▁▂▃▄▅▆▇█";
const RDU_FMT_GIO = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const RDU_FMT_NGAY = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh", year: "numeric", month: "2-digit", day: "2-digit" });

const RDU_NHAC = "Sản phẩm 'tương tự' chọn theo từ khoá tên + giá, chưa chứng minh trùng SKU. Bảng cho thấy tín hiệu, không phải kết luận TikTok đang đẩy.";
const RDU_CAU_KHONG_VIDEO_14 = "không có video ≤ 14 ngày";
const RDU_CAU_KHONG_VIDEO_MOI = "Không có video mới 30 ngày";
const RDU_CAU_POSTER_HUONG_DAN = "Chỉ dán vào folder có video của đúng sản phẩm này (ô Product IDs, mỗi dòng một mã). Đừng thêm vào folder đang đăng sản phẩm khác: Poster sẽ chia đều video giữa các ID đang tick.";
const RDU_CAU_TICK = "Tôi đã đối chiếu: đúng sản phẩm/SKU, không chỉ giống tên";
const RDU_CAU_CHUA_DA = "Chưa đủ bằng chứng / chưa có đà";

const RDU_XEP = { dang_co_da: "Đáng thử (tín hiệu)", chua_co_da: "Chưa có đà", chua_du: "Chưa đủ bằng chứng", chan: "Bị chặn" };
const RDU_VAI = { goc: "UID gốc", tuong_tu: "Tương tự", them_tay: "Thêm tay" };
const RDU_TT_NHOM = { cho_tim: "Đang chờ máy nhà…", dang_tim: "Đang tìm sản phẩm tương tự…", da_tim: "", loi_tim: "Tìm sản phẩm tương tự bị lỗi", ngung: "Đã ngừng theo dõi (giữ dữ liệu)" };
// Huy hiệu nhóm trên thẻ UID chính: [lớp CSS, chữ].
const RDU_TT_HUY_HIEU = { cho_tim: ["tim", "Đang tìm"], dang_tim: ["tim", "Đang tìm"], da_tim: ["xong", "Đã tìm"], loi_tim: ["loi", "Lỗi tìm"], ngung: ["ngung", "Ngừng"] };
const RDU_TT_LAN = { xong: "đã xong", tu_dung: "tạm dừng", loi: "bị lỗi", dang_chay: "đang chạy", chua_chay: "chưa chạy" };
const RDU_CAU_TOKEN = {
  thieu: "Chưa có token EchoTik: đăng nhập EchoTik trên Chrome để tạo lại file token.",
  het_han: "EchoTik trả trang lỗi: token hết hạn hoặc EchoTik từ chối tham số. Đăng nhập lại EchoTik trên máy nhà.",
};
// Mã ly_do của lần chạy (§6.3) → câu lời thường; dùng khi API không kèm ten_ly_do.
const RDU_CAU_LY_DO = {
  token_thieu: RDU_CAU_TOKEN.thieu, token_het_han: RDU_CAU_TOKEN.het_han,
  rate_limit: "EchoTik giới hạn lượt gọi: thử lại ngày mai.", mang_lien_tiep: "Mất mạng tới EchoTik.",
  keyword_khong_loc: "EchoTik không lọc theo từ khoá nên không tìm được tương tự: thêm tay UID.",
  khong_tim_thay: "EchoTik không có UID này.", khong_co_video: "EchoTik chưa có video nào cho UID này.", dinh_dang: "EchoTik trả dữ liệu lạ.",
};
const RDU_CO = {
  DU_LIEU_CU: { ten: "Dữ liệu cũ (> 36 giờ)", muc: "chan" },
  GAP: { ten: "Hở dữ liệu (kỳ < 8 hoặc > 54 giờ)", muc: "chan" },
  THIEU_MAU: { ten: "Thiếu mẫu (cần ≥ 8 video, ≥ 3 creator, ≥ 4 snapshot trong 72 giờ)", muc: "chan" },
  KHONG_LAM_MOI: { ten: "Số liệu không làm mới", muc: "chan" },
  MAU_TOP_VIDEO: { ten: "Chỉ lấy 50 video đầu trang trong tổng nhiều hơn", muc: "canh-bao" },
  MOT_CREATOR_CHI_PHOI: { ten: "Một creator chiếm ≥ 50% lượt tăng", muc: "canh-bao" },
  NGHI_ADS: { ten: "Nghi chạy ads", muc: "canh-bao" },
};

const rduCo = (o, k) => !!o && typeof o === "object" && Object.prototype.hasOwnProperty.call(o, k);
const rduObj = (o) => (o && typeof o === "object" && !Array.isArray(o) ? o : {});
const rduMang = (a) => (Array.isArray(a) ? a : []);
const rduOk = (n) => typeof n === "number" && Number.isFinite(n); // số hiện được; chuỗi số / null / NaN → không
const rduChu = (s, toiDa = 200) => (typeof s === "string" ? s.replace(RDU_KY_DIEU_KHIEN, " ").slice(0, toiDa).trim() : "");
const rduNhan = (b, k, md) => (rduCo(b, k) ? b[k] : md);
const rduId = (s) => (typeof s === "string" && RDU_RE_UID.test(s) ? s : ""); // id 19 số hợp lệ hoặc ""

// Ô nhập (UID thô hoặc link chứa /product/<19 số>, /pdp/<19 số>) → "19 số" | "". Không đi theo link rút gọn.
function rduLayUid(s) {
  if (typeof s !== "string") return "";
  const t = s.trim();
  if (RDU_RE_UID.test(t)) return t;
  const m = t.match(RDU_RE_LINK);
  return m ? m[1] : "";
}

// number|null → "—" | chuỗi có dấu chấm nghìn, dấu phẩy thập phân (le = số chữ số thập phân, 0–3). Không bao giờ in 0 giả cho null.
function rduSo(n, le = 0) {
  if (!rduOk(n) || Math.abs(n) >= 1e15) return "—";
  const d = Number.isInteger(le) && le > 0 && le <= 3 ? le : 0;
  const t = Math.abs(n).toFixed(d);
  const [ng, tp] = t.split(".");
  const dau = n < 0 && Number(t) !== 0 ? "-" : "";
  return `${dau}${ng.replace(/\B(?=(\d{3})+(?!\d))/g, ".")}${tp ? `,${tp}` : ""}`;
}

// (number|null)[] → "▁▃▅▇" (≤ 7 kỳ gần nhất, cũ → mới); null = "·". Mức = min(7, floor(8 × max(v,0) / max_v)).
function rduSpark(a) {
  if (!Array.isArray(a)) return "";
  const v = a.slice(-7).map((x) => (rduOk(x) ? x : null));
  const lonNhat = Math.max(0, ...v.filter((x) => x !== null));
  return v.map((x) => (x === null ? "·" : RDU_SPARK[lonNhat > 0 ? Math.min(7, Math.floor((8 * Math.max(x, 0)) / lonNhat)) : 0])).join("");
}

// Mã cờ → {ten, muc: "chan"|"canh-bao"}. Mã lạ: tên cắt ngắn, mức theo nơi API đặt (macDinh).
function rduNhanCo(ma, macDinh = "canh-bao") {
  if (typeof ma === "string" && rduCo(RDU_CO, ma)) return { ...RDU_CO[ma] };
  return { ten: rduChu(typeof ma === "string" ? ma : "", 40) || "Cờ lạ", muc: macDinh === "chan" ? "chan" : "canh-bao" };
}

function rduGio(s) { // ISO có giờ → "dd/mm HH:MM" giờ VN; sai → ""
  const t = typeof s === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s) ? Date.parse(s) : NaN;
  if (!Number.isFinite(t)) return "";
  const p = Object.fromEntries(RDU_FMT_GIO.formatToParts(new Date(t)).map((x) => [x.type, x.value]));
  return `${p.day}/${p.month} ${p.hour}:${p.minute}`;
}
function rduDm(s) { // "YYYY-MM-DD" → "dd/mm"; sai → ""
  const m = typeof s === "string" ? s.match(RDU_RE_NGAY) : null;
  return m ? `${m[3]}/${m[2]}` : "";
}
const rduHomNay = (nowMs) => (Number.isFinite(nowMs) ? RDU_FMT_NGAY.format(new Date(nowMs)) : "");

// Một ô số liệu: gt/phu là HTML ĐÃ esc bởi người gọi; nhan là chữ thường (esc ở đây).
const rduO = (cls, nhan, gt, phu = "") => `<div class="rdu-o ${cls}"><span class="rdu-nhan">${esc(nhan)}</span><div class="rdu-gt">${gt}</div>`
  + `${phu ? `<div class="rdu-phu small muted">${phu}</div>` : ""}</div>`;

// Lý do không có trung vị (CHƯA esc). Luôn có câu — không "—" trơn.
function rduLyDoThieu(u) {
  const x = rduObj(u);
  const co = rduMang(x.co);
  const ra = [];
  if (co.includes("KHONG_LAM_MOI")) {
    ra.push(`số liệu không làm mới: ${rduSo(x.n_video)} video, view đổi ${rduSo(x.n_doi)}${rduChu(x.echotik_cap_nhat, 40) ? `, SP cập nhật ${rduChu(x.echotik_cap_nhat, 40)}` : ""}`);
  }
  if (co.includes("GAP")) ra.push("kỳ gần nhất bị hở dữ liệu (GAP)");
  if (co.includes("DU_LIEU_CU")) ra.push("dữ liệu cũ hơn 36 giờ");
  if (!ra.length) {
    const lt = rduMang(x.ly_do_thieu).filter((k) => typeof k === "string").slice(0, 3).map((k) => rduChu(k, 60)).filter(Boolean);
    ra.push(lt.length ? `chưa tính được: ${lt.join(", ")}` : "chưa tính được (cần ít nhất 2 snapshot hợp lệ)");
  }
  return ra.join(" · ");
}

// Hành động ghim/loại có được phép với dòng này không (web KHÔNG tự tính từ dữ liệu cũ: dùng dữ liệu đang hiện).
function rduChoPhep(u, act) {
  const x = rduObj(u), tt = x.trang_thai;
  if (x.vai === "goc") return false; // 409 "Không đổi được UID gốc"
  if (act === "ghim") return tt === "dang_theo";
  if (act === "bo-ghim") return tt === "ghim";
  if (act === "loai") return tt === "dang_theo" || tt === "ghim";
  if (act === "bo-loai") return tt === "loai";
  return false;
}
function rduChoPhepNhom(nhom, act) {
  const tt = rduObj(nhom).trang_thai;
  if (act === "tim-lai" || act === "them-tay") return tt === "da_tim" || tt === "loi_tim";
  if (act === "ngung") return tt !== "ngung";
  if (act === "theo-lai") return tt === "ngung";
  return false;
}

// ---- ô số liệu của một hàng ----
function rduOTrungVi(u) {
  const xam = u.tam === true || u.xep_loai === "chua_du" || u.xep_loai === "chan";
  if (rduOk(u.trung_vi)) {
    const phu = [];
    if (u.tam === true || u.xep_loai === "chua_du") phu.push(`chưa đủ bằng chứng (n=${rduSo(u.n_video)}, ${rduSo(u.so_snapshot)}/${RDU_SNAPSHOT_CAN} snapshot)`);
    else if (u.xep_loai === "chan") phu.push("bị chặn: xem cờ trên thẻ");
    if (rduOk(u.trung_vi_truoc)) phu.push(`kỳ trước ${rduSo(u.trung_vi_truoc)}`);
    return rduO("rdu-o-chinh", "Trung vị Δview/video/24h", `<span class="rdu-so-lon${xam ? " rdu-xam" : ""}">${esc(rduSo(u.trung_vi))}</span>`, esc(phu.join(" · ")));
  }
  return rduO("rdu-o-chinh", "Trung vị Δview/video/24h", `<span class="rdu-so-lon rdu-xam">—</span>`, esc(rduLyDoThieu(u)));
}
function rduOTangToc(u) {
  if (rduOk(u.tang_toc)) {
    const cau = `×${rduSo(u.tang_toc, 2)} (${u.tang_dot_ngot === true ? "đột ngột" : "không"}) · top 5 = ${rduSo(u.tong_delta_top5)}`;
    return rduO(u.tang_dot_ngot === true ? "rdu-dot" : "", "Tăng tốc", esc(cau));
  }
  return rduO("", "Tăng tốc", "—", esc(rduChu(u.ly_do_tang_toc, 80) || "chưa có kỳ trước"));
}
function rduOViewNho(u) {
  const phu = [];
  if (rduOk(u.view_nho_30_trung_vi)) phu.push(`≤ 30 ngày: trung vị ${rduSo(u.view_nho_30_trung_vi)} · ${rduSo(u.n_creator_nho_30)} creator`);
  if (rduOk(u.follower_khong_doc) && u.follower_khong_doc > 0) phu.push(`${rduSo(u.follower_khong_doc)} creator không đọc được follower (đã loại)`);
  const gt = rduOk(u.view_nho_trung_vi)
    ? `trung vị ${rduSo(u.view_nho_trung_vi)} · ${rduSo(u.n_creator_nho)} creator < 10K follower (≤ 14 ngày)`
    : (rduChu(u.cau_view_nho, 120) || RDU_CAU_KHONG_VIDEO_14);
  return rduO("", "View ở creator nhỏ", esc(gt), esc(phu.join(" · ")));
}
function rduOSong(u) {
  const phu = rduOk(u.trung_vi_14) ? `≤ 14 ngày: trung vị ${rduSo(u.trung_vi_14)} (${rduSo(u.n_video_14)} video)` : "";
  return rduO("", "Video đang sống", esc(`${rduSo(u.n_video)} video đang sống · ${rduSo(u.n_creator)} creator`), esc(phu));
}
function rduODoi(u) {
  // n_doi và ti_le_doi cùng đo trên số video có mặt ở cả hai snapshot; KHÔNG dùng promote_y làm mẫu số.
  if (rduOk(u.n_doi) && rduOk(u.ti_le_doi)) {
    return rduO("", "View đổi", esc(`view đổi ${rduSo(u.n_doi)} video (${rduSo(u.ti_le_doi, 1)}%)`));
  }
  return rduO("", "View đổi", esc("view đổi — (chưa đo được ở cả hai snapshot)"));
}
function rduOMoi(u) {
  const gt = rduOk(u.n_video_moi_30) ? (u.n_video_moi_30 > 0 ? `${rduSo(u.n_video_moi_30)} video mới ≤ 30 ngày` : RDU_CAU_KHONG_VIDEO_MOI) : "—";
  return rduO("", "Video mới", esc(gt));
}
function rduOGia(u) {
  const t = (s) => esc(rduChu(s, 40) || "—");
  return rduO("", "Giá / hoa hồng / tồn", `${t(u.gia)} · ${t(u.hoa_hong)} · tồn ${t(u.ton)}`);
}
function rduOCo(u) {
  const chip = (ma, muc) => {
    const c = rduNhanCo(ma, muc);
    return `<span class="rdu-co rdu-co-${c.muc}">${esc(c.ten)}</span>`;
  };
  const chan = rduMang(u.co).filter((m) => typeof m === "string").map((m) => chip(m, "chan"));
  const bao = rduMang(u.co_canh_bao).filter((m) => typeof m === "string").map((m) => chip(m, "canh-bao"));
  const thieu = rduMang(u.ly_do_thieu).filter((k) => typeof k === "string").slice(0, 4).map((k) => rduChu(k, 60)).filter(Boolean);
  if (!chan.length && !bao.length && !thieu.length) return "";
  return `<div class="rdu-cos">${chan.join("")}${bao.join("")}${thieu.length ? `<span class="small muted">Thiếu: ${esc(thieu.join(", "))}</span>` : ""}</div>`;
}

// Khung nhỏ "📮 Poster" (§10): KHÔNG ghi vào Poster V2. goc: id nhóm (gắn vào nút để dò lại dữ liệu đang hiện).
function rduPosterHtml(u, goc) {
  const x = rduObj(u);
  const uid = rduId(x.uid);
  if (!uid) return "";
  const g = rduId(goc);
  const gAttr = g ? ` data-rdu-goc="${g}"` : "";
  const canTick = x.vai !== "goc";
  const nut = (act, nhan) => `<button type="button" class="btn ghost sm" data-rdu-act="${act}" data-rdu-uid="${uid}"${gAttr}${canTick ? " disabled" : ""}>${esc(nhan)}</button>`;
  return `<div class="rdu-poster" data-rdu-poster="${uid}" hidden>`
    + `<p class="small">${esc(RDU_CAU_POSTER_HUONG_DAN)}</p>`
    + (canTick ? `<label class="rdu-tick"><input type="checkbox" data-rdu-tick="${uid}"> ${esc(RDU_CAU_TICK)}</label>` : "")
    + (x.xep_loai !== "dang_co_da" ? `<p class="small rdu-vang">${esc(RDU_CAU_CHUA_DA)}</p>` : "")
    + `<div class="row">${nut("chep", "Sao chép UID")}${nut("mo-folders", "Mở Poster V2 › Folders")}</div></div>`;
}

// ---- ảnh (RU-W6 D): chỉ <img> khi URL đúng host CDN EchoTik (CSP img-src chỉ mở đúng host này); còn lại ô xám ----
const rduAnhHopLe = (u) => typeof u === "string" && RDU_RE_ANH.test(u);
// kich: "nho" (~96px, mặc định) | "lon". Ảnh lỗi tải (URL EchoTik sống ~24 giờ) → rduAnhLoi (phần DOM) thay bằng RDU_ANH_HET.
function rduAnhHtml(url, kich) {
  const cl = kich === "lon" ? "lon" : "nho";
  const trong = rduAnhHopLe(url)
    ? `<img src="${esc(url)}" loading="lazy" referrerpolicy="no-referrer" alt="">`
    : `<span class="rdu-anh-ph">chưa có ảnh</span>`;
  return `<span class="rdu-anh rdu-anh-${cl}">${trong}</span>`;
}
// Giá từ API: chuỗi đã định dạng ("499.390₫") hoặc số; thiếu → "" (không vẽ dòng, không điền 0).
function rduGiaChu(g) {
  if (typeof g === "string") return rduChu(g, 40);
  return rduOk(g) ? `${rduSo(g)}₫` : "";
}
// 2 liên kết ngoài; uid chỉ vào URL sau khi khớp ^\d{19}$.
function rduLienKetHtml(uid) {
  const u = rduId(uid);
  if (!u) return "";
  const a = (href, nhan) => `<a class="rdu-lk" href="${href}" target="_blank" rel="noopener noreferrer">${nhan}</a>`;
  return `<span class="rdu-lks">${a(`https://shop.tiktok.com/view/product/${u}?region=VN`, "Mở TikTok")}${a(`https://echotik.live/products/${u}`, "Mở EchoTik")}</span>`;
}
function rduSaoChepHtml(uid, goc) {
  const u = rduId(uid), g = rduId(goc);
  if (!u || !g) return "";
  return `<button type="button" class="btn ghost sm rdu-chep" data-rdu-act="sao-chep-uid" data-rdu-uid="${u}" data-rdu-goc="${g}" aria-label="Sao chép UID">Sao chép</button>`;
}
function rduHuyHieuHtml(tt) {
  const h = rduCo(RDU_TT_HUY_HIEU, tt) ? RDU_TT_HUY_HIEU[tt] : ["khac", "Không rõ"];
  return `<span class="rdu-tt rdu-tt-${h[0]}">${esc(h[1])}</span>`;
}

// Gom thông tin hiển thị của một nhóm (UID chính); thiếu ảnh/tên/shop/giá của nhóm → lấy từ dòng UID gốc trong ds. goc sai → null.
function rduThongTinNhom(nhom) {
  const n = rduObj(nhom);
  const goc = rduId(n.goc);
  if (!goc) return null;
  const ds = rduMang(n.ds).filter((u) => u && typeof u === "object");
  const gocU = ds.find((u) => u.vai === "goc" || u.uid === goc) || {};
  const tt = rduCo(RDU_TT_NHOM, n.trang_thai) ? n.trang_thai : "";
  const tuongTu = ds.filter((u) => u.vai !== "goc" && u.uid !== goc);
  return {
    n, goc, ds, tt, tuongTu,
    anh: rduAnhHopLe(n.anh) ? n.anh : (rduAnhHopLe(gocU.anh) ? gocU.anh : ""),
    ten: rduChu(n.ten, 160) || rduChu(gocU.ten, 160),
    shop: rduChu(n.shop, 80) || rduChu(gocU.shop, 80),
    gia: rduGiaChu(n.gia) || rduGiaChu(gocU.gia),
    dem: rduOk(n.n_tuong_tu) ? n.n_tuong_tu : tuongTu.filter((u) => u.trang_thai !== "loai").length,
    lyDo: n.trang_thai === "loi_tim" ? rduChu(n.ten_ly_do, 200) || rduChu(n.ly_do, 80) : "",
    gocU,
  };
}
// Nút của nhóm (Tìm lại / Ngừng / Theo dõi lại): nằm NGOÀI thẻ liên kết.
function rduNutNhomHtml(n, goc) {
  const nut = (act, nhan) => `<button type="button" class="btn ghost sm" data-rdu-act="${act}" data-rdu-goc="${goc}">${esc(nhan)}</button>`;
  const nuts = [];
  if (rduChoPhepNhom(n, "tim-lai")) nuts.push(nut("tim-lai", "Tìm lại"));
  if (rduChoPhepNhom(n, "ngung")) nuts.push(nut("ngung", "Ngừng theo dõi"));
  if (rduChoPhepNhom(n, "theo-lai")) nuts.push(nut("theo-lai", "Theo dõi lại"));
  return nuts.join("");
}

// Trang chính: THẺ một UID chính (chỉ nhóm, không liệt kê UID tương tự). Thẻ = <article> chứa <a href="#/theo-doi/<goc>"> + hàng nút bên ngoài <a>.
function rduTheChinhHtml(nhom) {
  const t = rduThongTinNhom(nhom);
  if (!t) return "";
  const batDau = rduDm(t.n.bat_dau_ngay);
  const ghim = rduOk(t.n.n_ghim) && t.n.n_ghim > 0 ? ` · ${rduSo(t.n.n_ghim)} đã ghim` : "";
  return `<article class="rdu-the" data-rdu-goc="${t.goc}">`
    + `<a class="rdu-the-lk" href="#/theo-doi/${t.goc}">${rduAnhHtml(t.anh, "nho")}<div class="rdu-thong-tin">`
    + `<div class="rdu-the-ten">${esc(t.ten || "(chưa có tên)")}</div>`
    + (t.shop ? `<div class="small muted">Shop: ${esc(t.shop)}</div>` : "")
    + (t.gia ? `<div class="small rdu-gia">${esc(t.gia)}</div>` : "")
    + `<div>${rduHuyHieuHtml(t.n.trang_thai)}${t.lyDo ? ` <span class="small rdu-vang">${esc(t.lyDo)}</span>` : ""}</div>`
    + `<div class="small">${esc(`${rduSo(t.dem)} UID tương tự đang theo dõi${ghim}`)}</div>`
    + (batDau ? `<div class="small muted">Bắt đầu theo dõi ${esc(batDau)}</div>` : "")
    + `</div></a><div class="row rdu-the-nut">${rduNutNhomHtml(t.n, t.goc)}</div></article>`;
}

// Khung "Chỉ số" thu gọn (<details>): xếp loại + mọi ô số liệu + dòng dữ liệu. Cờ chặn/cảnh báo KHÔNG nằm trong đây.
function rduChiSoHtml(x) {
  const xep = rduCo(RDU_XEP, x.xep_loai) ? x.xep_loai : "khac";
  const dl = rduGio(x.du_lieu_luc);
  const cuoi = `dữ liệu lúc ${dl || "—"} · phủ ${rduSo(x.phu_gio)} giờ · ${rduSo(x.so_snapshot)} snapshot`;
  return `<details class="rdu-chi-so"><summary>Chỉ số</summary>`
    + `<div><span class="rdu-xl rdu-xl-${xep}">${esc(rduNhan(RDU_XEP, x.xep_loai, "Chưa phân loại"))}</span></div>`
    + `<div class="rdu-luoi">${rduOTrungVi(x)}`
    + rduO("", "Xu hướng", `<span class="rdu-spark">${esc(rduSpark(x.spark))}</span>`, "7 kỳ gần nhất, cũ → mới")
    + `${rduOTangToc(x)}${rduOViewNho(x)}${rduOSong(x)}${rduODoi(x)}${rduOMoi(x)}`
    + rduO("", "Δ bán/ngày", esc(rduSo(x.d_ban_ngay, 1)))
    + rduO("", "Creator mới/ngày", esc(rduSo(x.creator_moi_ngay, 1)))
    + `${rduOGia(x)}`
    + rduO("", "is_promote", esc(`is_promote ${rduSo(x.promote_x)}/${rduSo(x.promote_y)} (chưa rõ nghĩa)`))
    + `</div><div class="small muted rdu-cuoi">${esc(cuoi)}</div></details>`;
}

// 1 UID tương tự (UidRa §7.1) → thẻ ngang: ảnh, tên, shop, giá, đã bán, UID + sao chép, liên kết, nhãn ghim/loại, cờ, nút; chỉ số trong <details>.
// goc: id nhóm chứa hàng này.
function rduHangHtml(u, goc) {
  const x = rduObj(u);
  const uid = rduId(x.uid);
  if (!uid) return `<article class="rdu-hang rdu-khac"><p class="small muted">Một dòng có UID không hợp lệ — đã bỏ qua.</p></article>`;
  const g = rduId(goc);
  const gAttr = g ? ` data-rdu-goc="${g}"` : "";
  const xep = rduCo(RDU_XEP, x.xep_loai) ? x.xep_loai : "khac";
  const loai = x.trang_thai === "loai";
  const vai = rduNhan(RDU_VAI, x.vai, "UID");
  const giong = x.vai === "tuong_tu" && rduOk(x.do_giong) ? ` · tên giống ${rduSo(Math.round(x.do_giong * 100))}%` : "";
  const chip = x.trang_thai === "ghim" ? ` <span class="rdu-chip rdu-chip-ghim">📌 ghim</span>` : loai ? ` <span class="rdu-chip rdu-chip-loai">loại</span>` : "";
  const nut = (act, nhan, cls = "ghost") => `<button type="button" class="btn ${cls} sm" data-rdu-act="${act}" data-rdu-uid="${uid}"${gAttr}>${esc(nhan)}</button>`;
  const nuts = [];
  if (g && rduChoPhep(x, "ghim")) nuts.push(nut("ghim", "Ghim"));
  if (g && rduChoPhep(x, "bo-ghim")) nuts.push(nut("bo-ghim", "Bỏ ghim"));
  if (g && rduChoPhep(x, "loai")) nuts.push(nut("loai", "Loại"));
  if (g && rduChoPhep(x, "bo-loai")) nuts.push(nut("bo-loai", "Bỏ loại"));
  if (!loai) nuts.unshift(nut("poster", "📮 Poster"));
  const gia = rduGiaChu(x.gia);
  const ban = rduOk(x.ban_tong) ? `Đã bán ${rduSo(x.ban_tong)}` : "";
  const dong = [gia, ban].filter(Boolean).join(" · ");
  return `<article class="rdu-hang rdu-${xep}${loai ? " rdu-loai" : ""}" data-rdu-uid="${uid}"${gAttr}>`
    + `<div class="rdu-the-ngang">${rduAnhHtml(x.anh, "nho")}<div class="rdu-thong-tin">`
    + `<div class="rdu-sp">${esc(rduChu(x.ten, 160) || "(chưa có tên)")}</div>`
    + `<div class="small muted">Shop: ${esc(rduChu(x.shop, 80) || "—")}</div>`
    + (dong ? `<div class="small rdu-gia">${esc(dong)}</div>` : "")
    + `<div class="rdu-uid-dong"><span class="rdu-uid">${uid}</span>${loai ? "" : rduSaoChepHtml(uid, g)}</div>`
    + `<div class="small muted">${esc(vai + giong)}${chip}</div>`
    + `${rduLienKetHtml(uid)}</div></div>`
    + `${rduOCo(x)}`
    + `<div class="row rdu-tay">${nuts.join("")}</div>${rduChiSoHtml(x)}${loai ? "" : rduPosterHtml(x, g)}</article>`;
}

// Trang chi tiết một UID chính: khối UID chính, rồi danh sách UID TƯƠNG TỰ (API đã sắp §5.4; "Ít dữ liệu" và "Đã loại" thu gọn).
function rduChiTietHtml(nhom) {
  const t = rduThongTinNhom(nhom);
  if (!t) return "";
  const { n, goc } = t;
  const loai = t.tuongTu.filter((u) => u.trang_thai === "loai");
  const ha = t.tuongTu.filter((u) => u.trang_thai !== "loai" && u.uu_tien === "ha");
  const chinh = t.tuongTu.filter((u) => u.trang_thai !== "loai" && u.uu_tien !== "ha");
  const hang = (a) => a.map((u) => rduHangHtml(u, goc)).join("");
  const cauTt = t.tt ? RDU_TT_NHOM[t.tt] : "Trạng thái nhóm không rõ";
  const batDau = rduDm(n.bat_dau_ngay);
  const them = rduChoPhepNhom(n, "them-tay")
    ? `<div class="rdu-them row"><input type="text" class="rdu-them-in" data-rdu-vao="them-tay" maxlength="300" placeholder="Thêm tay 1 UID tương tự (≤ 3)" aria-label="Thêm tay UID">`
      + `<button type="button" class="btn ghost sm" data-rdu-act="them-tay" data-rdu-goc="${goc}">Thêm tay</button></div>` : "";
  const soTuongTu = chinh.length + ha.length;
  return `<p><a class="rdu-quay" href="#/theo-doi">← Tất cả UID chính</a></p>`
    + `<section class="rdu-nhom rdu-chinh hn-khoi" data-rdu-goc="${goc}" data-rdu-tt="${esc(t.tt)}">`
    + `<div class="rdu-the-ngang">${rduAnhHtml(t.anh, "lon")}<div class="rdu-thong-tin">`
    + `<h2 class="hn-tieu-de">${esc(t.ten || "(chưa có tên)")}</h2>`
    + (t.shop ? `<div class="small muted">Shop: ${esc(t.shop)}</div>` : "")
    + (t.gia ? `<div class="rdu-gia">${esc(t.gia)}</div>` : "")
    + `<div>${rduHuyHieuHtml(n.trang_thai)}</div>`
    + `<div class="rdu-uid-dong"><span class="rdu-uid">${goc}</span>${rduSaoChepHtml(goc, goc)}</div>`
    + `${rduLienKetHtml(goc)}`
    + (batDau ? `<div class="small muted">Bắt đầu theo dõi ${esc(batDau)}</div>` : "")
    + `</div></div>`
    + (cauTt ? `<p class="small ${t.tt === "loi_tim" ? "hn-bao" : "muted"}">${esc(cauTt)}${t.lyDo ? `: ${esc(t.lyDo)}` : ""}</p>` : "")
    + `<div class="row rdu-nhom-nut">${rduNutNhomHtml(n, goc)}</div>`
    + (rduCo(t.gocU, "uid") ? rduChiSoHtml(rduObj(t.gocU)) : "")
    + `</section>`
    + `<h3 class="hn-tieu-de rdu-muc">UID tương tự đang theo dõi (${soTuongTu})</h3>`
    + (soTuongTu ? "" : `<p class="small muted">Chưa có UID tương tự nào đang theo dõi.</p>`)
    + (chinh.length ? `<div class="rdu-ds">${hang(chinh)}</div>` : "")
    + (ha.length ? `<details class="rdu-gom"><summary>Ít dữ liệu (${ha.length})</summary><div class="rdu-ds">${hang(ha)}</div></details>` : "")
    + (loai.length ? `<details class="rdu-gom"><summary>Đã loại (${loai.length})</summary><div class="rdu-ds">${hang(loai)}</div></details>` : "")
    + them;
}

// Câu lý do của lần chạy gần nhất (CHƯA esc): ưu tiên ten_ly_do của máy nhà, rồi bảng §6.3.
function rduCauLan(lan, hanMuc) {
  const l = rduObj(lan);
  if (l.trang_thai !== "tu_dung" && l.trang_thai !== "loi") return "";
  const ten = rduChu(l.ten_ly_do, 200);
  if (ten) return ten;
  if (l.ly_do === "het_han_muc_goi") {
    const h = rduObj(hanMuc);
    return `Hết ngân sách gọi EchoTik hôm nay (${rduSo(h.goi_hom_nay)}/${rduSo(h.goi_ngay_toi_da)}).`;
  }
  return rduNhan(RDU_CAU_LY_DO, l.ly_do, `Lần chạy gần nhất ${RDU_TT_LAN[l.trang_thai]}${rduChu(l.ly_do, 60) ? ` (${rduChu(l.ly_do, 60)})` : ""}.`);
}

const RDU_KHONG_CO_HTML = `<section class="hn-khoi rdu-rong"><h2 class="hn-tieu-de">Không có UID chính này.</h2>`
  + `<p class="small">UID này không còn trong Radar hoặc chưa được nạp.</p><p><a class="rdu-quay" href="#/theo-doi">← Tất cả UID chính</a></p></section>`;
const RDU_RONG_HTML = `<section class="hn-khoi rdu-rong"><h2 class="hn-tieu-de">Chưa theo dõi UID nào</h2>`
  + `<p class="small">Dán 1 UID gốc (19 chữ số, hoặc link TikTok Shop có /product/… hay /pdp/…) vào ô phía trên. Máy nhà tìm ≤ 10 sản phẩm tương tự theo tên + giá, `
  + `chụp số liệu EchoTik mỗi ngày (10:00), rồi xếp hạng UID đang có đà.</p>`
  + `<p class="small muted">Bảng xếp hạng đầu tiên có nghĩa từ lần chụp thứ 4 (khoảng ngày thứ 4). Trước đó số chỉ là tạm, hiện xám kèm "chưa đủ bằng chứng".</p></section>`;

// Phần thân dưới ô nhập: banner token/lỗi, hạn mức, rồi (id rỗng) danh sách THẺ UID chính / (id = 19 số) chi tiết một UID chính.
// id có mà sai dạng hoặc không có trong dữ liệu → "Không có UID chính này."
function rduBangHtml(bang, nowMs, id) {
  const b = rduObj(bang);
  const bao = (ma, cau) => `<p class="hn-bao" data-rdu-bao="${ma}">${esc(cau)}</p>`;
  const ra = [];
  const hm = rduObj(b.han_muc);
  const cauToken = rduNhan(RDU_CAU_TOKEN, rduObj(b.token).trang_thai, "");
  if (cauToken) ra.push(bao("token", cauToken));
  const cauLan = rduCauLan(b.lan, hm);
  if (cauLan && cauLan !== cauToken) ra.push(bao("lan", cauLan));
  if (hm.bat === 0) ra.push(bao("tat", "Radar UID đang tắt (cầu dao): không chụp và không nhận UID mới."));
  const lan = rduObj(b.lan);
  const ngayLan = rduDm(lan.ngay);
  const homNay = rduHomNay(nowMs);
  const cu = typeof lan.ngay === "string" && homNay && lan.ngay !== homNay;
  const thongTin = [];
  if (rduOk(hm.goi_hom_nay) || rduOk(hm.goi_ngay_toi_da)) thongTin.push(`Hôm nay đã gọi EchoTik ${rduSo(hm.goi_hom_nay)}/${rduSo(hm.goi_ngay_toi_da)} lượt`);
  if (rduOk(hm.goc_toi_da)) thongTin.push(`tối đa ${rduSo(hm.goc_toi_da)} UID gốc`);
  if (RDU_TT_LAN[lan.trang_thai]) thongTin.push(`lần chụp gần nhất ${RDU_TT_LAN[lan.trang_thai]}${ngayLan ? ` (ngày ${ngayLan}${cu ? ", không phải hôm nay" : ""})` : ""}`);
  if (thongTin.length) ra.push(`<p class="small muted rdu-tin">${esc(thongTin.join(" · "))}</p>`);
  if (typeof id === "string" && id !== "") {
    const idOk = rduId(id);
    const n = idOk ? rduMang(b.nhom).find((x) => rduObj(x).goc === idOk) : null;
    ra.push((n && rduChiTietHtml(n)) || RDU_KHONG_CO_HTML);
    return ra.join("");
  }
  const the = rduMang(b.nhom).map((n) => rduTheChinhHtml(n)).filter(Boolean);
  ra.push(the.length ? `<div class="rdu-the-ds">${the.join("")}</div>` : RDU_RONG_HTML);
  return ra.join("");
}

// Lỗi tải bảng → câu lời thường (CHƯA esc). Không bao giờ đưa thân lỗi máy chủ / HTML ra.
function rduCauLoiTai(err) {
  const st = err && typeof err === "object" ? err.status : 0;
  const msg = err && typeof err.message === "string" ? err.message.trim() : "";
  if (st === 401) return "Hết phiên đăng nhập — đăng nhập lại để xem.";
  if (st === 403) return "Tài khoản này không xem được Radar UID.";
  if (st === 404) return "Máy nhà chưa hỗ trợ Radar UID — cần cập nhật máy nhà.";
  if (st === 503 && msg === "Radar UID chưa bật") return "Radar UID chưa bật trên máy nhà.";
  if (st === 503 && RDU_RE_LOI_CAU_HINH.test(msg)) return "Máy chủ web chưa cấu hình đúng kết nối tới máy nhà — báo người quản trị.";
  if (Number.isInteger(st) && st >= 400 && st < 500) return "Máy chủ không nhận yêu cầu này — bấm Tải lại.";
  return "Chưa tải được Radar UID — mạng chập chờn hoặc máy nhà đang tắt. Bấm Tải lại.";
}

// Lỗi khi ghi (POST) → {cau, ketCuc}. ketCuc: "mo" (chắc chắn chưa làm gì → mở khoá), "lai" (tải lại bảng, mở khoá),
// "chua_ro" (mạng/5xx: không biết đã tới máy nhà chưa → GIỮ khoá tới lần tải thành công kế).
function rduCauLoiGhi(err) {
  const st = err && typeof err === "object" ? err.status : 0;
  const cau = rduChu(err && typeof err.message === "string" ? err.message : "", 160);
  if (st === 401) return { cau: "Hết phiên đăng nhập — đăng nhập lại rồi bấm lại.", ketCuc: "mo" };
  if (st === 403) return { cau: "Tài khoản này không làm được thao tác này.", ketCuc: "mo" };
  if (st === 404) return { cau: `⚠ ${cau || "Không tìm thấy"} — đã tải lại để bạn xem.`, ketCuc: "lai" };
  if (st === 400 || st === 413 || st === 415 || st === 429) return { cau: `⚠ ${cau || "Máy chủ không nhận thao tác này"}`, ketCuc: "mo" };
  return { cau: "Chưa chắc đã xong — bấm Tải lại để xem trạng thái thật.", ketCuc: "chua_ro" };
}
// --- radar-uid-thuan end ---

// ---------- phần có DOM ----------
const RDU_ACT_GHI = new Set(["goc", "chup-lai", "tim-lai", "ngung", "theo-lai", "them-tay", "ghim", "bo-ghim", "loai", "bo-loai"]);
const RDU_TOAST_XONG = {
  "chup-lai": "✓ Đã nhận: máy nhà sẽ chụp lại các UID hôm nay.", "tim-lai": "✓ Đã nhận: máy nhà đang tìm lại sản phẩm tương tự.",
  ngung: "✓ Đã ngừng theo dõi nhóm (giữ dữ liệu).", "theo-lai": "✓ Đã theo dõi lại nhóm.", "them-tay": "✓ Đã thêm UID.",
  ghim: "✓ Đã ghim UID.", "bo-ghim": "✓ Đã bỏ ghim.", loai: "✓ Đã loại UID (ngừng chụp).", "bo-loai": "✓ Đã bỏ loại.",
};
const RDU_HEN_MS = 10000; // nhóm còn cho_tim/dang_tim: hỏi lại mỗi 10 giây khi còn ở trang

let rduLuot = 0; // số lượt tải bảng: kết quả của lượt cũ về muộn thì bỏ (đặt TRƯỚC await)
let rduPhienTrang = -1; // phienCT của trang đang hiện (rduRender đặt)
let rduBang = null; // bảng đang hiện — mọi nút kiểm lại trạng thái từ đây, không tin data-* của nút
let rduHtmlCuoi = ""; // HTML đã vẽ: giống hệt thì không vẽ lại (giữ khung Poster / ô tick đang mở khi hỏi lại)
let rduHen = 0;
let rduIdTrang = ""; // id UID chính của trang chi tiết đang hiện ("" = trang danh sách)
const rduDangGui = new Set(); // khoá hành động đang gửi (chống bấm đúp, kể cả sau khi vẽ lại)
const rduChuaRo = new Set(); // khoá đã gửi mà chưa chắc kết quả (mạng/5xx) — giữ tới lần tải bảng thành công kế

const rduKhoa = (d) => `${(d && d.rduAct) || ""}|${(d && d.rduGoc) || ""}|${(d && d.rduUid) || ""}`;
function rduKhoaNut(khoa, khoaLai) {
  document.querySelectorAll("#rdu [data-rdu-act]").forEach((n) => { if (rduKhoa(n.dataset) === khoa) n.disabled = khoaLai; });
}
function rduMsg(cau, loi) {
  const o = $("#rdu-msg");
  if (o) { o.textContent = cau; o.className = loi ? "small rdu-loi" : "small muted"; }
}
const rduTimNhom = (goc) => rduMang(rduObj(rduBang).nhom).find((n) => rduObj(n).goc === goc) || null;
const rduTimUid = (goc, uid) => { const n = rduTimNhom(goc); return n ? rduMang(n.ds).find((u) => rduObj(u).uid === uid) || null : null; };

// Dừng hẹn giờ hỏi lại + bỏ kết quả đang chờ (khung.js mnRoute gọi ở đầu MỌI lần đổi route).
function rduDung() {
  if (rduHen) clearTimeout(rduHen);
  rduHen = 0;
  rduLuot++;
}

// Ảnh lỗi tải (URL EchoTik hết hạn ~24 giờ): thay <img> bằng ô "ảnh hết hạn". CSP cấm onerror inline; sự kiện error không nổi bọt
// → nghe ở pha capture trên khung #rdu.
const RDU_ANH_HET = `<span class="rdu-anh-ph">ảnh hết hạn</span>`;
function rduAnhLoi(e) {
  const t = e && e.target;
  if (!t || t.tagName !== "IMG" || typeof t.closest !== "function") return;
  const k = t.closest(".rdu-anh");
  if (!k) return;
  k.innerHTML = RDU_ANH_HET;
  k.classList.add("rdu-anh-het");
}

// Trang #/theo-doi (id rỗng: danh sách UID chính) hoặc #/theo-doi/<19 số> (chi tiết) — khung.js mnRoute gọi, đã kiểm chủ kho + đánh số phiên.
async function rduRender(phien, id) {
  rduDung();
  rduIdTrang = rduId(id); // sai dạng → trang danh sách
  rduPhienTrang = phien; rduBang = null; rduHtmlCuoi = "";
  $("#app").innerHTML = `<div class="hn rdu" id="rdu">
      <div class="row hn-dau"><h1 class="hn-h1">📡 Radar UID</h1>
        <div class="row"><button type="button" class="btn ghost sm" id="rdu-chup-lai" data-rdu-act="chup-lai">Chụp lại hôm nay</button>
        <button type="button" class="btn ghost sm" id="rdu-tai-lai" data-rdu-act="tai-lai">↻ Tải lại</button></div></div>
      <p class="small muted rdu-nhac">${esc(RDU_NHAC)}</p>
      ${rduIdTrang ? "" : `<div class="rdu-them row"><input type="text" id="rdu-in" data-rdu-vao="goc" maxlength="300" autocomplete="off" placeholder="Dán UID gốc (19 chữ số) hoặc link sản phẩm TikTok Shop" aria-label="UID gốc">
        <button type="button" class="btn" id="rdu-them" data-rdu-act="goc">Theo dõi</button></div>`}
      <p class="small muted" id="rdu-msg" role="status"></p>
      <div id="rdu-nd"><p class="muted">Đang tải…</p></div>
    </div>`;
  const goc = $("#rdu");
  goc.addEventListener("click", (e) => {
    const b = e.target && e.target.closest ? e.target.closest("[data-rdu-act]") : null;
    if (!b) return undefined;
    if (typeof e.preventDefault === "function") e.preventDefault(); // nút không kích hoạt điều hướng của thẻ / liên kết bao ngoài
    if (typeof e.stopPropagation === "function") e.stopPropagation();
    return rduBam(b);
  });
  goc.addEventListener("error", rduAnhLoi, true);
  goc.addEventListener("change", (e) => { const t = e.target && e.target.closest ? e.target.closest("[data-rdu-tick]") : null; if (t) rduDoiTick(t); });
  goc.addEventListener("keydown", (e) => { // Enter trong ô nhập = bấm nút cùng hàng
    if (e.key !== "Enter" || !e.target || !e.target.closest) return;
    const vao = e.target.closest("[data-rdu-vao]");
    const hang = vao ? vao.closest(".rdu-them") : null;
    const nut = hang ? hang.querySelector("[data-rdu-act]") : null;
    if (!nut) return undefined;
    e.preventDefault();
    return rduBam(nut);
  });
  await rduTai(phien, false);
}

// Tải bảng rồi vẽ #rdu-nd. tuTay: bấm "Tải lại" (nút đang khoá thì bỏ).
async function rduTai(phien, tuTay) {
  const nut = $("#rdu-tai-lai");
  if (tuTay && nut && nut.disabled) return;
  const luot = ++rduLuot;
  if (rduHen) { clearTimeout(rduHen); rduHen = 0; }
  if (nut) nut.disabled = true; // khoá TRƯỚC await
  let bang = null, loi = null;
  try { bang = await api("radar/bang"); } catch (err) { loi = err; }
  if (phien !== phienCT || luot !== rduLuot) return; // đã sang trang khác / có lượt tải mới hơn: không vẽ đè
  const nd = $("#rdu-nd");
  let hoiLai = false;
  if (nd) {
    if (loi || !bang || !Array.isArray(bang.nhom)) {
      rduBang = null; rduHtmlCuoi = "";
      nd.innerHTML = `<p class="hn-bao" data-rdu-bao="loi">${esc(loi ? rduCauLoiTai(loi) : "Máy nhà trả dữ liệu lạ — bấm Tải lại.")}</p>`;
    } else {
      rduChuaRo.clear(); // đã có trạng thái thật từ máy nhà
      rduBang = bang;
      const html = rduBangHtml(bang, Date.now(), rduIdTrang);
      if (html !== rduHtmlCuoi) { nd.innerHTML = html; rduHtmlCuoi = html; }
      // nút ghi: khoá nếu đang gửi / chưa chắc kết quả, ngược lại mở
      document.querySelectorAll("#rdu [data-rdu-act]").forEach((n) => {
        if (RDU_ACT_GHI.has(n.dataset.rduAct)) { const k = rduKhoa(n.dataset); n.disabled = rduDangGui.has(k) || rduChuaRo.has(k); }
      });
      hoiLai = bang.nhom.some((n) => n && (!rduIdTrang || n.goc === rduIdTrang) && (n.trang_thai === "cho_tim" || n.trang_thai === "dang_tim"));
    }
  }
  const n2 = $("#rdu-tai-lai");
  if (n2) n2.disabled = false;
  if (hoiLai) {
    rduHen = setTimeout(() => {
      rduHen = 0;
      if (phien === phienCT && $("#rdu")) rduTai(phien, false);
    }, RDU_HEN_MS);
  }
}

function rduDoiTick(t) {
  const khung = t.closest("[data-rdu-poster]");
  if (!khung) return;
  khung.querySelectorAll("[data-rdu-act]").forEach((n) => { n.disabled = !t.checked; });
}

// Gửi 1 POST ghi: khoá TRƯỚC await; 409 → câu §7; mạng đứt → giữ khoá tới lần tải thành công kế. Trả r (thành công) hoặc null.
async function rduGui(khoa, path, body, cauXong) {
  if (rduDangGui.has(khoa) || rduChuaRo.has(khoa)) return null;
  rduDangGui.add(khoa);
  rduKhoaNut(khoa, true);
  let r = null, veLai = false, moKhoa = true;
  try {
    const kq = await api(path, body);
    veLai = true;
    if (kq.status === 409) toast(`⚠ ${rduChu(kq.loi, 160) || "Trạng thái vừa đổi"} — đã tải lại để bạn xem.`);
    else { r = kq; toast(typeof cauXong === "function" ? cauXong(kq) : cauXong); }
  } catch (err) {
    const l = rduCauLoiGhi(err);
    toast(l.cau);
    veLai = l.ketCuc === "lai";
    if (l.ketCuc === "chua_ro") { moKhoa = false; rduChuaRo.add(khoa); }
  }
  try { if (veLai) await rduVeLaiSauGhi(); } finally { rduDangGui.delete(khoa); }
  if (moKhoa) rduKhoaNut(khoa, false);
  return r;
}
// Sau ghi: tải lại trang ĐANG hiện (phiên hiện hành) nếu vẫn là trang Radar.
async function rduVeLaiSauGhi() {
  const p = phienCT;
  if (rduPhienTrang === p && $("#rdu")) await rduTai(p, false);
}

async function rduThemGoc() {
  const o = $("#rdu-in");
  const uid = rduLayUid(o ? o.value : "");
  if (!uid) { rduMsg("UID phải đủ 19 chữ số (hoặc dán link TikTok Shop có /product/<19 số>).", true); return; } // sai dạng: không gọi API
  rduMsg("", false);
  if (o) o.disabled = true;
  const r = await rduGui("goc||", "radar/goc", { uid }, (k) => (k.da_co ? "UID này đã có trong Radar." : "✓ Đã nhận UID: máy nhà sẽ tìm sản phẩm tương tự (vài phút), bảng tự cập nhật."));
  if (o) { o.disabled = false; if (r) o.value = ""; }
  if (r) rduMsg(r.da_co ? "UID này đã có trong Radar." : "Đã nhận UID, máy nhà đang tìm sản phẩm tương tự…", false);
}

// Mọi nút trong #rdu. Kiểm lại id 19 số + cờ cho phép từ dữ liệu đang hiện (rduBang) trước khi gửi.
async function rduBam(b) {
  const d = b && b.dataset ? b.dataset : {};
  const act = d.rduAct;
  if (!b || b.disabled || typeof act !== "string") return;
  if (act === "tai-lai") { await rduTai(rduPhienTrang, true); return; }
  if (act === "goc") { await rduThemGoc(); return; }
  if (act === "chup-lai") {
    if (!confirm("Chụp lại tất cả UID hôm nay? Việc này tốn ngân sách gọi EchoTik (khoảng 2 lượt mỗi UID).")) return;
    await rduGui("chup-lai||", "radar/chup-lai", {}, RDU_TOAST_XONG["chup-lai"]);
    return;
  }
  const goc = rduId(d.rduGoc), uid = rduId(d.rduUid);
  const loiCu = () => toast("Mục này vừa đổi trạng thái — bấm Tải lại để xem.");
  if (act === "sao-chep-uid") { // chép UID của thẻ (không cần tick: chỉ chép, không đụng Poster); id phải có trong dữ liệu đang hiện
    if (!goc || !uid || !rduTimNhom(goc) || (uid !== goc && !rduTimUid(goc, uid))) { loiCu(); return; }
    await copy(uid, "Đã sao chép UID");
    return;
  }
  if (act === "poster" || act === "chep" || act === "mo-folders") {
    const u = goc && uid ? rduTimUid(goc, uid) : null;
    if (!u) { loiCu(); return; }
    if (act === "poster") {
      const p = b.closest(".rdu-hang") ? b.closest(".rdu-hang").querySelector("[data-rdu-poster]") : null;
      if (p) p.hidden = !p.hidden;
      return;
    }
    if (u.vai !== "goc") { // UID không phải gốc: ô tick đối chiếu SKU bắt buộc (kiểm lại ở đây, không chỉ nút disabled)
      const k = b.closest("[data-rdu-poster]") ? b.closest("[data-rdu-poster]").querySelector("[data-rdu-tick]") : null;
      if (!k || k.checked !== true) { toast("Hãy tick ô đối chiếu SP/SKU trước."); return; }
    }
    if (act === "chep") await copy(uid, "Đã sao chép UID");
    else location.hash = "#/poster/folders";
    return;
  }
  if (!RDU_ACT_GHI.has(act) || !goc) return;
  const nhom = rduTimNhom(goc);
  if (!nhom) { loiCu(); return; }
  if (act === "ghim" || act === "bo-ghim" || act === "loai" || act === "bo-loai") {
    if (!uid || !rduChoPhep(rduTimUid(goc, uid), act)) { loiCu(); return; }
    await rduGui(rduKhoa(d), `radar/goc/${goc}/uid/${uid}/${act}`, {}, RDU_TOAST_XONG[act]);
    return;
  }
  if (!rduChoPhepNhom(nhom, act)) { loiCu(); return; }
  if (act === "them-tay") {
    const grp = b.closest(".rdu-nhom");
    const o = grp ? grp.querySelector(".rdu-them-in") : null;
    const moi = rduLayUid(o ? o.value : "");
    if (!moi) { toast("UID phải đủ 19 chữ số."); return; } // sai dạng: không gọi API
    if (o) o.disabled = true;
    const r = await rduGui(rduKhoa(d), `radar/goc/${goc}/them-tay`, { uid: moi }, RDU_TOAST_XONG[act]);
    if (o) { o.disabled = false; if (r) o.value = ""; }
    return;
  }
  await rduGui(rduKhoa(d), `radar/goc/${goc}/${act}`, {}, RDU_TOAST_XONG[act]);
}
