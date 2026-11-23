// Test RU-W2 (D16, docs/radar-uid.md §8–§10): tab "📡 Radar UID" (#/theo-doi, web/radar-uid.js) + nhãn 2 loại việc + ?v.
// Không mạng: api/DOM giả. Chạy: node --test cf/test/radar-uid-web.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const doc = (p) => readFileSync(new URL(`../../web/${p}`, import.meta.url), "utf8");
const APP = doc("app.js");
const RDU = doc("radar-uid.js");
const HTML = doc("index.html");
const CSS = doc("style.css");
const LOI = doc("loi.js");
const VIEC = doc("viec.js");

const esc = new Function(`${APP.split("\n").find((l) => l.startsWith("const esc = "))}\nreturn esc;`)();
const khoi = (src, ten) => {
  const m = src.match(new RegExp(`// --- ${ten} start ---\\n([\\s\\S]*?)// --- ${ten} end ---`));
  assert.ok(m, `thiếu marker ${ten}`);
  return m[1];
};
const F = new Function("esc", `"use strict";\n${khoi(RDU, "radar-uid-thuan")}
return { rduLayUid, rduSo, rduSpark, rduNhanCo, rduHangHtml, rduNhomHtml, rduBangHtml, rduPosterHtml, rduCauLoiTai, rduCauLoiGhi,
  rduChoPhep, rduChoPhepNhom, RDU_NHAC };`)(esc);

const GOC = "1737422436677814024"; // > 2^53: phải giữ nguyên là chuỗi
const UID = "1729706628656957720";
const UID2 = "1729706628656957721";
const UID3 = "1729706628656957722";
const BAN = `"><img src=x onerror=1>`;
const KHONG_LOT = (h, ten) => {
  assert.ok(!h.includes("<img"), `${ten}: lọt thẻ <img`);
  assert.ok(!h.includes(BAN), `${ten}: lọt chuỗi độc thô`);
  assert.ok(!/\son[a-z]+\s*=/i.test(h.replaceAll(esc(BAN), "")), `${ten}: lọt thuộc tính on…=`);
  assert.ok(!/<table|style="/i.test(h), `${ten}: có bảng/style cứng`);
};

// UidRa §7.1 (giá trị tổng hợp, không phải dữ liệu thật)
const U = (x = {}) => ({
  uid: UID, vai: "tuong_tu", trang_thai: "dang_theo", ten: "Máy xay mini", shop: "Shop A", do_giong: 0.67,
  xep_loai: "dang_co_da", uu_tien: "thuong", tam: false,
  trung_vi: 700, trung_vi_truoc: 520, tong_delta_top5: 9200, tong_delta_top5_truoc: 1600,
  tang_toc: 5.75, tang_dot_ngot: true, ly_do_tang_toc: "",
  n_video: 11, n_creator: 6, n_doi: 10, ti_le_doi: 90.9,
  view_nho_trung_vi: 7200, n_creator_nho: 5, cau_view_nho: "", view_nho_30_trung_vi: 6800, n_creator_nho_30: 7, follower_khong_doc: 1,
  trung_vi_14: 640, n_video_14: 9, n_video_moi_30: 4, cau_video_moi: "", promote_x: 1, promote_y: 39,
  spark: [null, 320, 520, 700], d_ban_ngay: 14.2, creator_moi_ngay: 1.5, gia: "499.390₫", hoa_hong: "10%", ton: "562",
  du_lieu_luc: "2026-11-23T10:01:00+07:00", echotik_cap_nhat: "2026-11-22 07:55", so_snapshot: 4, phu_gio: 72.2,
  co: [], co_canh_bao: ["MOT_CREATOR_CHI_PHOI"], ly_do_thieu: [], duoi_do_phan_giai: 1, ...x,
});
const NHOM = (x = {}) => ({
  goc: GOC, ten: "Máy xay thực phẩm", trang_thai: "da_tim", ly_do: "", ten_ly_do: "", tim_luc: "2026-11-20T10:00:00+07:00", bat_dau_ngay: "2026-11-20",
  ds: [U({ uid: GOC, vai: "goc", do_giong: null }), U({ uid: UID }), U({ uid: UID2, vai: "them_tay", trang_thai: "ghim" })], ...x,
});
const BANG = (x = {}) => ({
  luc: "2026-11-23T10:12:00+07:00", ngay: "2026-11-23", token: { trang_thai: "ok", cau: "" },
  han_muc: { bat: 1, goi_ngay_toi_da: 60, goi_hom_nay: 22, goc_toi_da: 2 },
  lan: { trang_thai: "xong", ly_do: "", ngay: "2026-11-23", ten_ly_do: "" }, nhom: [NHOM()], ...x,
});
const HOM_NAY = Date.parse("2026-11-23T11:00:00+07:00");

// ---------- 1. hàm thuần nhỏ ----------
test("rduLayUid: 19 số thô hoặc link /product/<19> /pdp/<19>; sai dạng → ''; id > 2^53 giữ nguyên chuỗi", () => {
  assert.equal(F.rduLayUid(UID), UID);
  assert.equal(F.rduLayUid(`  ${GOC}\n`), GOC);
  assert.equal(F.rduLayUid(`https://shop.tiktok.com/vn/pdp/${UID}`), UID);
  assert.equal(F.rduLayUid(`https://shop.tiktok.com/view/product/${UID}?x=1`), UID);
  assert.equal(F.rduLayUid(`https://shop.tiktok.com/vn/pdp/may-xay-mini/${UID}?utm=1`), UID);
  for (const x of ["", "123", UID.slice(1), `${UID}9`, `abc${UID}`, `https://x.vn/product/${UID}9`, "https://vt.tiktok.com/ZSabc/", BAN, null, undefined, 1729706628656957720, {}]) {
    assert.equal(F.rduLayUid(x), "", String(x));
  }
});

test("rduSo: null/NaN/chuỗi → '—' (không 0 giả); chấm nghìn, phẩy thập phân; số âm", () => {
  for (const x of [null, undefined, NaN, Infinity, "700", "", {}, [], true]) assert.equal(F.rduSo(x), "—", String(x));
  assert.equal(F.rduSo(0), "0");
  assert.equal(F.rduSo(700), "700");
  assert.equal(F.rduSo(9200), "9.200");
  assert.equal(F.rduSo(1234567), "1.234.567");
  assert.equal(F.rduSo(-1500), "-1.500");
  assert.equal(F.rduSo(5.75, 2), "5,75");
  assert.equal(F.rduSo(14.2, 1), "14,2");
  assert.equal(F.rduSo(90.94, 1), "90,9");
  assert.equal(F.rduSo(-0.04, 1), "0,0", "không in -0");
  assert.equal(F.rduSo(1e16), "—");
});

test("rduSpark: ≤ 7 kỳ cũ → mới, null = '·', mức min(7, floor(8×v/max)), âm = thấp nhất", () => {
  assert.equal(F.rduSpark([null, 320, 520, 700]), "·▄▆█");
  assert.equal(F.rduSpark([0, 0, 0]), "▁▁▁");
  assert.equal(F.rduSpark([null, null]), "··");
  assert.equal(F.rduSpark([-5, 10]), "▁█");
  assert.equal(F.rduSpark([1, 2, 3, 4, 5, 6, 7, 8, 9]).length, 7);
  assert.equal(F.rduSpark([1, 2, 3, 4, 5, 6, 7, 8, 9]).at(-1), "█");
  for (const x of [null, undefined, "x", {}, 5]) assert.equal(F.rduSpark(x), "");
  assert.equal(F.rduSpark(["700", NaN, 5]), "··█", "chuỗi/NaN coi như không có số");
});

test("rduNhanCo: 7 cờ §5.2 đúng mức chặn/cảnh báo; mã lạ không ném; không lấy khoá prototype", () => {
  for (const ma of ["DU_LIEU_CU", "GAP", "THIEU_MAU", "KHONG_LAM_MOI"]) assert.equal(F.rduNhanCo(ma).muc, "chan", ma);
  for (const ma of ["MAU_TOP_VIDEO", "MOT_CREATOR_CHI_PHOI", "NGHI_ADS"]) assert.equal(F.rduNhanCo(ma).muc, "canh-bao", ma);
  assert.equal(F.rduNhanCo("MAU_TOP_VIDEO").ten, "Chỉ lấy 50 video đầu trang trong tổng nhiều hơn", "không khẳng định 'mới nhất' (chiều sắp xếp chưa đo)");
  assert.ok(F.rduNhanCo("GAP").ten.length > 3);
  assert.deepEqual(F.rduNhanCo("LA_HOAC", "chan"), { ten: "LA_HOAC", muc: "chan" });
  assert.equal(F.rduNhanCo("LA").muc, "canh-bao");
  assert.equal(F.rduNhanCo("__proto__").ten, "__proto__");
  assert.equal(F.rduNhanCo(null).ten, "Cờ lạ");
  assert.equal(F.rduNhanCo("x".repeat(100)).ten.length, 40);
});

test("rduChoPhep / rduChoPhepNhom: UID gốc không ghim/loại; trạng thái đúng chiều; nhóm theo trạng thái", () => {
  assert.equal(F.rduChoPhep({ vai: "goc", trang_thai: "dang_theo" }, "loai"), false);
  assert.equal(F.rduChoPhep({ vai: "tuong_tu", trang_thai: "dang_theo" }, "ghim"), true);
  assert.equal(F.rduChoPhep({ vai: "tuong_tu", trang_thai: "ghim" }, "ghim"), false);
  assert.equal(F.rduChoPhep({ vai: "tuong_tu", trang_thai: "ghim" }, "bo-ghim"), true);
  assert.equal(F.rduChoPhep({ vai: "them_tay", trang_thai: "ghim" }, "loai"), true);
  assert.equal(F.rduChoPhep({ vai: "tuong_tu", trang_thai: "loai" }, "bo-loai"), true);
  assert.equal(F.rduChoPhep({ vai: "tuong_tu", trang_thai: "loai" }, "ghim"), false);
  assert.equal(F.rduChoPhep(null, "ghim"), false);
  assert.equal(F.rduChoPhep({ vai: "tuong_tu", trang_thai: "dang_theo" }, "xoa"), false);
  const c = (tt, a) => F.rduChoPhepNhom({ trang_thai: tt }, a);
  assert.deepEqual(["cho_tim", "dang_tim", "da_tim", "loi_tim", "ngung"].map((t) => c(t, "tim-lai")), [false, false, true, true, false]);
  assert.deepEqual(["cho_tim", "da_tim", "ngung"].map((t) => c(t, "ngung")), [true, true, false]);
  assert.deepEqual(["da_tim", "ngung"].map((t) => c(t, "theo-lai")), [false, true]);
  assert.deepEqual(["cho_tim", "da_tim", "loi_tim", "ngung"].map((t) => c(t, "them-tay")), [false, true, true, false]);
});

// ---------- 2. hàng UID ----------
test("rduHangHtml: mỗi chỉ số một ô riêng, đủ cột §8 (số chính, spark, tăng tốc, view nhỏ, sống, đổi, mới, bán, creator mới, giá, is_promote, dữ liệu)", () => {
  const h = F.rduHangHtml(U(), GOC);
  assert.match(h, new RegExp(`data-rdu-uid="${UID}" data-rdu-goc="${GOC}"`));
  assert.match(h, /Trung vị Δview\/video\/24h/);
  assert.match(h, /class="rdu-so-lon">700</, "số chính, không xám khi đủ bằng chứng");
  assert.ok(!/rdu-so-lon rdu-xam">700/.test(h));
  assert.match(h, /kỳ trước 520/);
  assert.match(h, /<span class="rdu-spark">·▄▆█<\/span>/);
  assert.match(h, /×5,75 \(đột ngột\) · top 5 = 9\.200/);
  assert.match(h, /trung vị 7\.200 · 5 creator &lt; 10K follower \(≤ 14 ngày\)/);
  assert.match(h, /≤ 30 ngày: trung vị 6\.800 · 7 creator/);
  assert.match(h, /1 creator không đọc được follower/);
  assert.match(h, /11 video đang sống · 6 creator/);
  assert.match(h, /view đổi 10 video \(90,9%\)/);
  assert.ok(!/view đổi 10\/39|view đổi \d+\//.test(h), "mẫu số không được lấy từ promote_y");
  assert.match(h, /is_promote 1\/39/, "is_promote nằm ở ô riêng");
  assert.match(h, /4 video mới ≤ 30 ngày/);
  assert.match(h, /Δ bán\/ngày[\s\S]*?14,2/);
  assert.match(h, /Creator mới\/ngày[\s\S]*?1,5/);
  assert.match(h, /499\.390₫ · 10% · tồn 562/);
  assert.match(h, /is_promote 1\/39 \(chưa rõ nghĩa\)/);
  assert.match(h, /dữ liệu lúc 23\/11 10:01 · phủ 72 giờ · 4 snapshot/);
  assert.match(h, /tên giống 67%/);
  assert.match(h, /rdu-co rdu-co-canh-bao/);
  assert.ok(!/NGHI_ADS|Nghi chạy ads/.test(h), "NGHI_ADS mặc định tắt: chỉ hiện khi API trả về");
  assert.ok(!/điểm tổng|điểm số|score/i.test(h), "không điểm tổng hợp ảo");
  assert.match(h, /Shop A/);
  KHONG_LOT(h, "hàng đủ");
});

test("rduHangHtml: tam=true / chưa đủ → số XÁM + câu 'chưa đủ bằng chứng (n=…, k/4 snapshot)' (không phải '—')", () => {
  const h = F.rduHangHtml(U({ tam: true, xep_loai: "chua_du", trung_vi: 12, n_video: 6, n_creator: 4, so_snapshot: 2, tang_toc: null, tang_dot_ngot: false, ly_do_tang_toc: "chưa có kỳ trước", co: ["THIEU_MAU"], ly_do_thieu: ["n_video 6/8", "so_snapshot 2/4"] }), GOC);
  assert.match(h, /class="rdu-so-lon rdu-xam">12</);
  assert.match(h, /chưa đủ bằng chứng \(n=6, 2\/4 snapshot\)/);
  assert.match(h, /rdu-co rdu-co-chan/);
  assert.match(h, /Thiếu: n_video 6\/8, so_snapshot 2\/4/);
  assert.match(h, /Tăng tốc[\s\S]*?—[\s\S]*?chưa có kỳ trước/);
  assert.match(h, /rdu-xl-chua_du/);
  // chua_du nhưng API quên tam → vẫn xám (không đưa số tạm như số tin cậy)
  assert.match(F.rduHangHtml(U({ tam: false, xep_loai: "chua_du", trung_vi: 12 }), GOC), /rdu-so-lon rdu-xam">12</);
});

test("rduHangHtml: KHONG_LAM_MOI → '—' + số thô (video, view đổi, SP cập nhật), cờ chặn; không in 0 giả", () => {
  const h = F.rduHangHtml(U({ xep_loai: "chan", trung_vi: null, trung_vi_truoc: null, tong_delta_top5: null, tang_toc: null, tang_dot_ngot: false,
    ly_do_tang_toc: "kỳ trước GAP", n_video: 39, n_doi: 0, ti_le_doi: 0, co: ["KHONG_LAM_MOI"], spark: [null, null, null] }), GOC);
  assert.match(h, /class="rdu-so-lon rdu-xam">—</);
  assert.match(h, /số liệu không làm mới: 39 video, view đổi 0, SP cập nhật 2026-11-22 07:55/);
  assert.match(h, /rdu-co rdu-co-chan/);
  assert.match(h, /kỳ trước GAP/);
  assert.match(h, /<span class="rdu-spark">···<\/span>/);
  assert.ok(!/class="rdu-so-lon[^"]*">0</.test(h));
  // GAP / không lý do → vẫn có câu, không '—' trơn
  assert.match(F.rduHangHtml(U({ trung_vi: null, co: ["GAP"] }), GOC), /kỳ gần nhất bị hở dữ liệu \(GAP\)/);
  assert.match(F.rduHangHtml(U({ trung_vi: null, co: [], ly_do_thieu: [] }), GOC), /chưa tính được \(cần ít nhất 2 snapshot hợp lệ\)/);
  assert.match(F.rduHangHtml(U({ trung_vi: null, co: [], ly_do_thieu: ["so_snapshot 1/4"] }), GOC), /chưa tính được: so_snapshot 1\/4/);
});

test("rduHangHtml: thiếu = '—' kèm lý do: không video ≤ 14 ngày, Không có video mới 30 ngày, tăng tốc null có lý do", () => {
  const h = F.rduHangHtml(U({ view_nho_trung_vi: null, n_creator_nho: 0, cau_view_nho: "", n_video_moi_30: 0, tang_toc: null, tang_dot_ngot: false, ly_do_tang_toc: "",
    d_ban_ngay: null, creator_moi_ngay: null, gia: "", hoa_hong: null, ton: undefined, promote_x: null, promote_y: null, phu_gio: null, du_lieu_luc: "", so_snapshot: null }), GOC);
  assert.match(h, /không có video ≤ 14 ngày/);
  assert.match(h, /≤ 30 ngày: trung vị 6\.800/, "dòng phụ 30 ngày vẫn hiện");
  assert.match(h, /Không có video mới 30 ngày/);
  assert.match(h, /chưa có kỳ trước/);
  assert.match(h, /— · — · tồn —/);
  assert.match(h, /is_promote —\/— \(chưa rõ nghĩa\)/);
  assert.match(h, /dữ liệu lúc — · phủ — giờ · — snapshot/);
  assert.ok(!/class="rdu-gt">0</.test(h));
  // câu của máy nhà được dùng khi có (đã esc)
  assert.match(F.rduHangHtml(U({ view_nho_trung_vi: null, cau_view_nho: "không có video ≤ 14 ngày (follower N/A)" }), GOC), /follower N\/A/);
});

test("rduHangHtml: ô View đổi thiếu n_doi hoặc ti_le_doi → '—' kèm lý do, không điền 0", () => {
  for (const t of [{ n_doi: null }, { ti_le_doi: null }, { n_doi: undefined, ti_le_doi: undefined }]) {
    const h = F.rduHangHtml(U(t), GOC);
    assert.match(h, /view đổi — \(chưa đo được ở cả hai snapshot\)/, JSON.stringify(t));
    assert.ok(!/view đổi 0/.test(h), JSON.stringify(t));
  }
});

test("rduHangHtml: NGHI_ADS chỉ hiện khi API trả về trong co_canh_bao; cờ chặn đỏ / cảnh báo vàng", () => {
  const h = F.rduHangHtml(U({ co: ["DU_LIEU_CU"], co_canh_bao: ["NGHI_ADS", "MAU_TOP_VIDEO"], xep_loai: "chan" }), GOC);
  assert.match(h, /rdu-co rdu-co-chan">Dữ liệu cũ/);
  assert.match(h, /rdu-co rdu-co-canh-bao">Nghi chạy ads/);
  assert.match(h, /rdu-co rdu-co-canh-bao">Chỉ lấy 50 video/);
  assert.match(h, /bị chặn: xem cờ bên dưới/);
});

test("rduHangHtml: nút theo vai/trạng thái; UID gốc không có Ghim/Loại; loại chỉ có Bỏ loại; goc rác → không nút ghi", () => {
  const nut = (h) => [...h.matchAll(/data-rdu-act="([\w-]+)"/g)].map((m) => m[1]);
  assert.deepEqual(nut(F.rduHangHtml(U({ uid: GOC, vai: "goc" }), GOC)), ["poster", "chep", "mo-folders"]);
  assert.deepEqual(nut(F.rduHangHtml(U(), GOC)), ["poster", "ghim", "loai", "chep", "mo-folders"]);
  assert.deepEqual(nut(F.rduHangHtml(U({ trang_thai: "ghim" }), GOC)), ["poster", "bo-ghim", "loai", "chep", "mo-folders"]);
  const loai = F.rduHangHtml(U({ trang_thai: "loai" }), GOC);
  assert.deepEqual(nut(loai), ["bo-loai"]);
  assert.match(loai, /rdu-hang rdu-dang_co_da rdu-loai/);
  assert.ok(!/data-rdu-poster/.test(loai), "UID đã loại: không khung Poster");
  assert.deepEqual(nut(F.rduHangHtml(U(), BAN)), ["poster", "chep", "mo-folders"], "không có goc hợp lệ → không ghim/loại");
  assert.ok(!/data-rdu-goc/.test(F.rduHangHtml(U(), BAN)));
});

test("rduHangHtml: UID không phải chuỗi 19 số (rác, số JS, ngắn) → câu cố định, không thuộc tính, không nút", () => {
  for (const uid of [BAN, "123", 1729706628656957720, null, undefined, `${UID}9`, " " + UID]) {
    const h = F.rduHangHtml(U({ uid, ten: "Tên" }), GOC);
    assert.match(h, /UID không hợp lệ — đã bỏ qua/, String(uid));
    assert.ok(!/data-rdu|<button/.test(h), String(uid));
    KHONG_LOT(h, String(uid));
  }
  for (const x of [null, undefined, "x", 5, []]) assert.doesNotThrow(() => F.rduHangHtml(x, GOC));
});

test("XSS: chèn chuỗi độc vào MỌI trường chuỗi của UidRa → không lọt <img / on…= / chuỗi thô", () => {
  const xau = U({
    ten: BAN, shop: BAN, vai: BAN, trang_thai: BAN, xep_loai: BAN, uu_tien: BAN, ly_do_tang_toc: BAN, cau_view_nho: BAN, cau_video_moi: BAN,
    gia: BAN, hoa_hong: BAN, ton: BAN, du_lieu_luc: BAN, echotik_cap_nhat: BAN, co: [BAN, "GAP"], co_canh_bao: [BAN], ly_do_thieu: [BAN],
    trung_vi: null, view_nho_trung_vi: null, tang_toc: null,
  });
  KHONG_LOT(F.rduHangHtml(xau, GOC), "hàng");
  // số mà API trả chuỗi → không vẽ ra (chỉ number hữu hạn mới hiện)
  const so = U({ trung_vi: BAN, n_video: BAN, n_creator: BAN, n_doi: BAN, ti_le_doi: BAN, tang_toc: BAN, view_nho_trung_vi: BAN, so_snapshot: BAN, phu_gio: BAN, promote_x: BAN, promote_y: BAN, d_ban_ngay: BAN, spark: [BAN, 5] });
  const h = F.rduHangHtml(so, GOC);
  KHONG_LOT(h, "số là chuỗi");
  KHONG_LOT(F.rduPosterHtml(xau, GOC), "poster");
});

// ---------- 3. khung Poster ----------
test("rduPosterHtml: CHỈ Sao chép UID + Mở Folders; hướng dẫn; ô tick bắt buộc với UID không phải gốc (2 nút disabled); dòng vàng khi chưa có đà", () => {
  const h = F.rduPosterHtml(U({ xep_loai: "chua_co_da" }), GOC);
  assert.match(h, /hidden>/);
  assert.match(h, /data-rdu-act="chep"[^>]*disabled>Sao chép UID</);
  assert.match(h, /data-rdu-act="mo-folders"[^>]*disabled>Mở Poster V2 › Folders</);
  assert.match(h, /type="checkbox" data-rdu-tick="1729706628656957720"> Tôi đã đối chiếu: đúng sản phẩm\/SKU, không chỉ giống tên/);
  assert.match(h, /Chưa đủ bằng chứng \/ chưa có đà/);
  assert.match(h, /Đừng thêm vào folder đang đăng sản phẩm khác/);
  assert.equal((h.match(/<button/g) || []).length, 2, "không nút nào ngoài 2 nút này (không PATCH/đẩy tự động)");
  const g = F.rduPosterHtml(U({ uid: GOC, vai: "goc", xep_loai: "dang_co_da" }), GOC);
  assert.ok(!/data-rdu-tick/.test(g), "UID gốc không cần tick");
  assert.ok(!/disabled/.test(g));
  assert.ok(!/chưa có đà/.test(g), "đang có đà: không dòng vàng");
  assert.equal(F.rduPosterHtml(U({ uid: BAN }), GOC), "");
});

// ---------- 4. nhóm ----------
test("rduNhomHtml: cho_tim/dang_tim 'đang chờ/tìm…', loi_tim có lý do + Tìm lại + ô thêm tay, da_tim đủ nút, ngung chỉ Theo dõi lại", () => {
  const nut = (h) => [...h.matchAll(/data-rdu-act="([\w-]+)" data-rdu-goc/g)].map((m) => m[1]);
  let h = F.rduNhomHtml(NHOM({ trang_thai: "cho_tim", ds: [U({ uid: GOC, vai: "goc" })] }));
  assert.match(h, /Đang chờ máy nhà…/);
  assert.ok(!/Tìm lại|rdu-them-in/.test(h));
  assert.deepEqual(nut(h), ["ngung"]);
  assert.match(F.rduNhomHtml(NHOM({ trang_thai: "dang_tim", ds: [] })), /Đang tìm sản phẩm tương tự…/);
  h = F.rduNhomHtml(NHOM({ trang_thai: "loi_tim", ly_do: "keyword_khong_loc", ten_ly_do: "EchoTik không lọc theo từ khoá nên không tìm được tương tự: thêm tay UID." }));
  assert.match(h, /Tìm sản phẩm tương tự bị lỗi: EchoTik không lọc theo từ khoá/);
  assert.match(h, /data-rdu-act="tim-lai"/);
  assert.match(h, /class="rdu-them-in"/);
  assert.match(h, /data-rdu-act="them-tay" data-rdu-goc="1737422436677814024"/);
  h = F.rduNhomHtml(NHOM());
  assert.deepEqual(nut(h).filter((a) => a !== "ghim" && a !== "loai" && a !== "bo-ghim" && a !== "bo-loai" && a !== "poster" && a !== "chep" && a !== "mo-folders"), ["tim-lai", "ngung", "them-tay"]);
  assert.match(h, /gốc 1737422436677814024/);
  assert.match(h, /Bắt đầu theo dõi 20\/11/);
  h = F.rduNhomHtml(NHOM({ trang_thai: "ngung" }));
  assert.match(h, /Đã ngừng theo dõi \(giữ dữ liệu\)/);
  assert.match(h, /data-rdu-act="theo-lai"/);
  assert.ok(!/data-rdu-act="tim-lai"|rdu-them-in/.test(h));
  assert.match(F.rduNhomHtml(NHOM({ trang_thai: "la" })), /Trạng thái nhóm không rõ/);
  assert.equal(F.rduNhomHtml(NHOM({ goc: BAN })), "");
  assert.equal(F.rduNhomHtml(null), "");
});

test("rduNhomHtml: 'Ít dữ liệu' (uu_tien=ha) và 'Đã loại' thu gọn bằng <details>; hàng chính không lẫn", () => {
  const h = F.rduNhomHtml(NHOM({ ds: [U({ uid: GOC, vai: "goc" }), U({ uid: UID, uu_tien: "ha", ten: "AAA-ha" }), U({ uid: UID2, trang_thai: "loai", ten: "BBB-loai" }), U({ uid: UID3, ten: "CCC-chinh" })] }));
  assert.match(h, /<details class="rdu-gom"><summary>Ít dữ liệu \(1\)<\/summary>[\s\S]*?AAA-ha[\s\S]*?<\/details>/);
  assert.match(h, /<details class="rdu-gom"><summary>Đã loại \(1\)<\/summary>[\s\S]*?BBB-loai[\s\S]*?<\/details>/);
  const chinh = h.slice(0, h.indexOf("<details"));
  assert.match(chinh, /CCC-chinh/);
  assert.ok(!/AAA-ha|BBB-loai/.test(chinh));
  assert.ok(!/<details/.test(F.rduNhomHtml(NHOM())), "không có gì để gom thì không vẽ");
});

test("XSS nhóm: tên/lý do/trạng thái/ds rác → an toàn", () => {
  const h = F.rduNhomHtml(NHOM({ ten: BAN, trang_thai: "loi_tim", ly_do: BAN, ten_ly_do: BAN, bat_dau_ngay: BAN, tim_luc: BAN, ds: [U({ uid: BAN, ten: BAN }), U({ ten: BAN, shop: BAN }), null, "x", 5] }));
  KHONG_LOT(h, "nhóm");
  KHONG_LOT(F.rduNhomHtml(NHOM({ trang_thai: BAN })), "trạng thái nhóm rác");
});

// ---------- 5. cả bảng ----------
test("rduBangHtml: rỗng → giới thiệu (không bảng trống); có thông tin hạn mức + lần chụp; nhắc 'chưa chứng minh trùng SKU' là hằng", () => {
  const rong = F.rduBangHtml(BANG({ nhom: [] }), HOM_NAY);
  assert.match(rong, /Chưa theo dõi UID nào/);
  assert.match(rong, /lần chụp thứ 4/);
  assert.match(F.rduBangHtml(BANG(), HOM_NAY), /Hôm nay đã gọi EchoTik 22\/60 lượt · tối đa 2 UID gốc · lần chụp gần nhất đã xong \(ngày 23\/11\)/);
  assert.match(F.rduBangHtml(BANG({ lan: { trang_thai: "xong", ngay: "2026-11-21" } }), HOM_NAY), /ngày 21\/11, không phải hôm nay/);
  assert.equal(F.RDU_NHAC, "Sản phẩm 'tương tự' chọn theo từ khoá tên + giá, chưa chứng minh trùng SKU. Bảng cho thấy tín hiệu, không phải kết luận TikTok đang đẩy.");
  for (const x of [null, undefined, "x", [], { nhom: "x", token: 5, lan: [], han_muc: "x" }]) assert.doesNotThrow(() => F.rduBangHtml(x, HOM_NAY));
  assert.match(F.rduBangHtml(null, HOM_NAY), /Chưa theo dõi UID nào/);
});

test("rduBangHtml: banner token (§6.3), lần chạy tạm dừng/lỗi, hết ngân sách, cầu dao tắt; không lặp banner trùng", () => {
  let h = F.rduBangHtml(BANG({ token: { trang_thai: "thieu" } }), HOM_NAY);
  assert.match(h, /data-rdu-bao="token">Chưa có token EchoTik: đăng nhập EchoTik trên Chrome để tạo lại file token\./);
  h = F.rduBangHtml(BANG({ token: { trang_thai: "het_han" }, lan: { trang_thai: "tu_dung", ly_do: "token_het_han", ngay: "2026-11-23" } }), HOM_NAY);
  assert.match(h, /EchoTik trả trang lỗi: token hết hạn/);
  assert.equal((h.match(/EchoTik trả trang lỗi/g) || []).length, 1, "token + lần chạy cùng câu → một banner");
  h = F.rduBangHtml(BANG({ lan: { trang_thai: "tu_dung", ly_do: "het_han_muc_goi", ngay: "2026-11-23" } }), HOM_NAY);
  assert.match(h, /Hết ngân sách gọi EchoTik hôm nay \(22\/60\)\./);
  h = F.rduBangHtml(BANG({ lan: { trang_thai: "tu_dung", ly_do: "rate_limit", ten_ly_do: "EchoTik giới hạn lượt gọi: thử lại ngày mai." } }), HOM_NAY);
  assert.match(h, /data-rdu-bao="lan">EchoTik giới hạn lượt gọi: thử lại ngày mai\./);
  assert.match(F.rduBangHtml(BANG({ lan: { trang_thai: "loi", ly_do: "ma_la" } }), HOM_NAY), /Lần chạy gần nhất bị lỗi \(ma_la\)\./);
  assert.match(F.rduBangHtml(BANG({ han_muc: { bat: 0 } }), HOM_NAY), /Radar UID đang tắt/);
  assert.ok(!/data-rdu-bao/.test(F.rduBangHtml(BANG(), HOM_NAY)), "mọi thứ ổn: không banner");
});

test("XSS bảng: token/lần chạy/hạn mức/nhóm rác → an toàn", () => {
  const h = F.rduBangHtml(BANG({ token: { trang_thai: BAN, cau: BAN }, lan: { trang_thai: "loi", ly_do: BAN, ten_ly_do: BAN, ngay: BAN }, han_muc: { bat: BAN, goi_hom_nay: BAN, goi_ngay_toi_da: BAN, goc_toi_da: BAN },
    nhom: [NHOM({ ten: BAN }), NHOM({ goc: BAN })] }), HOM_NAY);
  KHONG_LOT(h, "bảng");
});

test("rduCauLoiTai: câu lời thường theo mã, không đưa thân lỗi/HTML ra; rduCauLoiGhi: 400/413/415/429 mở khoá, 404 tải lại, mạng/5xx giữ khoá", () => {
  const L = (st, msg = BAN) => F.rduCauLoiTai(Object.assign(new Error(msg), { status: st }));
  assert.match(L(401), /đăng nhập lại/);
  assert.match(L(403), /không xem được Radar UID/);
  assert.match(L(404), /chưa hỗ trợ Radar UID/);
  assert.match(L(503, "Radar UID chưa bật"), /chưa bật trên máy nhà/);
  assert.match(L(503, "Chưa cấu hình bộ chạy việc"), /chưa cấu hình đúng/);
  assert.match(L(503, "Khoá ký bộ chạy việc không hợp lệ (KY_RIENG)"), /chưa cấu hình đúng/);
  assert.match(L(503, "Lỗi 503"), /Bấm Tải lại/);
  assert.match(L(400), /không nhận yêu cầu/);
  for (const st of [0, 500, 502, 504, undefined]) assert.match(L(st), /mạng chập chờn[\s\S]*Bấm Tải lại/, `status ${st}`);
  for (const st of [401, 403, 404, 400, 503, 502]) assert.ok(!L(st).includes("img") && !L(st).includes(BAN), `status ${st}`);
  assert.match(F.rduCauLoiTai(new TypeError("Failed to fetch")), /Bấm Tải lại/);
  assert.match(F.rduCauLoiTai(null), /Bấm Tải lại/);
  const G = (st, msg = "Vượt hạn mức (6 việc/ngày)") => F.rduCauLoiGhi(Object.assign(new Error(msg), { status: st }));
  for (const st of [400, 413, 415, 429]) assert.deepEqual([G(st).ketCuc, G(st).cau], ["mo", "⚠ Vượt hạn mức (6 việc/ngày)"], String(st));
  assert.equal(G(404, "Không có UID này trong Radar").ketCuc, "lai");
  assert.equal(G(401).ketCuc, "mo");
  assert.equal(G(403).ketCuc, "mo");
  for (const st of [0, 500, 502, 503, 504, undefined]) assert.equal(G(st).ketCuc, "chua_ro", String(st));
  assert.equal(F.rduCauLoiGhi(new TypeError("Failed to fetch")).ketCuc, "chua_ro");
  assert.ok(F.rduCauLoiGhi(Object.assign(new Error("a\u0000b".repeat(200)), { status: 429 })).cau.length <= 165, "cắt ngắn + bỏ ký tự điều khiển");
});

// ---------- 6. phần có DOM ----------
function phanTichNut(html) {
  return [...html.matchAll(/<button\b([^>]*)>/g)].map((m) => {
    const a = m[1];
    const t = Object.fromEntries([...a.matchAll(/([\w-]+)="([^"]*)"/g)].map((x) => [x[1], x[2]]));
    const dataset = {};
    for (const [k, v] of Object.entries(t)) if (k.startsWith("data-")) dataset[k.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = v;
    return { id: t.id || "", dataset, disabled: /\sdisabled(\s|$)/.test(a) };
  }).filter((b) => b.dataset.rduAct);
}

function dungRdu({ bang = BANG(), apiGia, confirmTra = true } = {}) {
  const S = { goi: [], toast: [], chep: [], timers: [], daXoaTimer: [], viTri: { hash: "" }, xacNhan: 0, gan: 0, appHtml: "", ndHtml: "" };
  const khung = { nut: [] }, nd = { nut: [] };
  const o = { in: { value: "", disabled: false }, msg: { textContent: "", className: "" }, tick: {}, panel: {}, them: {} };
  const lay = (m, k, mk) => (m[k] ||= mk());
  const tatCa = () => [...khung.nut, ...nd.nut];
  const gan = (n) => {
    n.closest = (s) => {
      const u = n.dataset.rduUid, g = n.dataset.rduGoc;
      if (s === ".rdu-hang") return { querySelector: () => lay(o.panel, u, () => ({ hidden: true })) };
      if (s === "[data-rdu-poster]") return { querySelector: () => lay(o.tick, u, () => ({ checked: false })), querySelectorAll: () => nd.nut.filter((x) => x.dataset.rduUid === u && /^(chep|mo-folders)$/.test(x.dataset.rduAct)) };
      if (s === ".rdu-nhom") return { querySelector: () => lay(o.them, g, () => ({ value: "", disabled: false })) };
      return null;
    };
    return n;
  };
  const app = { get innerHTML() { return S.appHtml; }, set innerHTML(v) { S.appHtml = v; khung.nut = phanTichNut(v).map(gan); nd.nut = []; S.ndHtml = ""; } };
  const ndEl = { get innerHTML() { return S.ndHtml; }, set innerHTML(v) { S.ndHtml = v; S.gan++; nd.nut = phanTichNut(v).map(gan); } };
  const goc = { nghe: {}, addEventListener(ev, f) { this.nghe[ev] = f; } };
  const co = (id) => S.appHtml.includes(`id="${id}"`);
  const $ = (s) => {
    if (s === "#app") return app;
    if (s === "#rdu") return co("rdu") ? goc : null;
    if (s === "#rdu-nd") return co("rdu-nd") ? ndEl : null;
    if (s === "#rdu-in") return co("rdu-in") ? o.in : null;
    if (s === "#rdu-msg") return co("rdu-msg") ? o.msg : null;
    if (s === "#rdu-tai-lai") return co("rdu-tai-lai") ? khung.nut.find((b) => b.id === "rdu-tai-lai") : null;
    return null;
  };
  const api = async (path, body) => {
    S.goi.push([path, body]);
    if (apiGia) return apiGia(path, body, S);
    if (path === "radar/bang") return { status: 200, ...bang };
    return { status: 202, da_co: false, goc: GOC, viec_id: "j20261123101200abcd" };
  };
  const ns = {
    $, esc, api, toast: (m) => S.toast.push(m), copy: async (t, m) => { S.chep.push([t, m]); }, confirm: () => { S.xacNhan++; return confirmTra; },
    document: { querySelectorAll: (s) => (s === "#rdu [data-rdu-act]" ? tatCa() : []) }, location: S.viTri,
    setTimeout: (f, ms) => { S.timers.push({ f, ms }); return S.timers.length; }, clearTimeout: (i) => S.daXoaTimer.push(i),
  };
  const ten = Object.keys(ns);
  const K = new Function(...ten, `"use strict";\nlet phienCT = 0;\n${RDU}\nreturn { rduRender, rduDung, rduTai, sang: () => ++phienCT, phien: () => phienCT };`)(...ten.map((k) => ns[k]));
  const nutDe = (act, uid = "", g = "") => tatCa().find((b) => b.dataset.rduAct === act && (b.dataset.rduUid || "") === uid && (b.dataset.rduGoc || "") === g);
  const bam = (b) => goc.nghe.click({ target: { closest: (s) => (s === "[data-rdu-act]" ? b : null) } });
  const so = (p) => S.goi.filter((x) => x[0] === p).length;
  return { K, S, o, goc, nd, ndEl, khung, nutDe, bam, so, tatCa };
}
const batDau = async (x) => { const p = x.K.sang(); await x.K.rduRender(p); return p; };

test("rduRender: khung (tiêu đề, Tải lại, ô nhập + Theo dõi, dòng nhắc cố định, trạng thái), GET bang 1 lần, vẽ nhóm; gắn click/change/keydown bằng addEventListener", async () => {
  const x = dungRdu();
  await batDau(x);
  assert.deepEqual(x.S.goi, [["radar/bang", undefined]]);
  assert.match(x.S.appHtml, /📡 Radar UID/);
  assert.ok(x.S.appHtml.includes(esc(F.RDU_NHAC)), "dòng nhắc cố định (đã esc)");
  assert.match(x.S.appHtml, /id="rdu-in"/);
  assert.match(x.S.appHtml, /id="rdu-them" data-rdu-act="goc">Theo dõi</);
  assert.match(x.S.appHtml, /id="rdu-tai-lai"[^>]*>↻ Tải lại/);
  assert.match(x.S.appHtml, /Đang tải…/);
  assert.match(x.S.ndHtml, /Máy xay thực phẩm/);
  assert.deepEqual(Object.keys(x.goc.nghe).sort(), ["change", "click", "keydown"]);
  assert.equal(x.nutDe("tai-lai").disabled, false, "mở lại nút Tải lại sau khi tải xong");
  KHONG_LOT(x.S.appHtml + x.S.ndHtml, "trang");
});

test("lỗi tải: một dòng hn-bao lời thường, KHÔNG hiện thân lỗi/HTML; không hẹn giờ; nút Tải lại mở lại", async () => {
  for (const [st, msg, mong] of [[503, "Radar UID chưa bật", /chưa bật trên máy nhà/], [500, `<html>${BAN}</html>`, /Bấm Tải lại/], [403, "Không có quyền", /không xem được/]]) {
    const x = dungRdu({ apiGia: async () => { throw Object.assign(new Error(msg), { status: st }); } });
    await batDau(x);
    assert.match(x.S.ndHtml, /^<p class="hn-bao" data-rdu-bao="loi">/);
    assert.match(x.S.ndHtml, mong);
    assert.ok(!x.S.ndHtml.includes("html") && !x.S.ndHtml.includes("img"));
    assert.equal(x.S.timers.length, 0);
    assert.equal(x.nutDe("tai-lai").disabled, false);
  }
  const y = dungRdu({ apiGia: async () => ({ status: 200, nhom: "x" }) });
  await batDau(y);
  assert.match(y.S.ndHtml, /dữ liệu lạ/);
});

test("trang cũ về muộn: đổi phiên / rduDung trong lúc chờ → không vẽ đè; lượt tải cũ bị lượt mới thay", async () => {
  let mo;
  const cho = new Promise((r) => { mo = r; });
  let x = dungRdu({ apiGia: async (p) => { await cho; return { status: 200, ...BANG() }; } });
  const p = x.K.sang();
  const t = x.K.rduRender(p);
  x.K.sang(); // sang trang khác
  mo(); await t;
  assert.equal(x.S.ndHtml, "", "không vẽ đè");
  x = dungRdu({ apiGia: async () => { await cho; return { status: 200, ...BANG() }; } });
  const t2 = x.K.rduRender(x.K.sang());
  x.K.rduDung(); // mnRoute gọi ở đầu mọi lần đổi route
  await t2;
  assert.equal(x.S.ndHtml, "");
  assert.equal(x.nutDe("tai-lai").disabled, true, "trang đã bỏ: không đụng DOM mới");
});

test("hẹn giờ: còn nhóm cho_tim/dang_tim → hỏi lại sau 10 s (1 hẹn), hết thì thôi; rduDung xoá hẹn; HTML y hệt thì không vẽ lại", async () => {
  const dangTim = BANG({ nhom: [NHOM({ trang_thai: "cho_tim", ds: [U({ uid: GOC, vai: "goc" })] })] });
  const x = dungRdu({ bang: dangTim });
  const p = await batDau(x);
  assert.equal(x.S.timers.length, 1);
  assert.equal(x.S.timers[0].ms, 10000);
  assert.equal(x.S.gan, 1);
  await x.S.timers[0].f(); // đến hạn, bảng không đổi
  await new Promise((r) => setImmediate(r));
  assert.equal(x.so("radar/bang"), 2);
  assert.equal(x.S.gan, 1, "bảng không đổi → không vẽ lại (giữ khung Poster/ô tick đang mở)");
  assert.equal(x.S.timers.length, 2, "vẫn còn đang tìm → hẹn tiếp");
  x.K.rduDung();
  assert.ok(x.S.daXoaTimer.length >= 1, "rduDung xoá hẹn");
  // hết đang tìm → không hẹn
  const y = dungRdu();
  await batDau(y);
  assert.equal(y.S.timers.length, 0);
  // hẹn chạy khi đã rời trang → không gọi API
  const z = dungRdu({ bang: dangTim });
  await batDau(z);
  z.K.sang();
  await z.S.timers[0].f();
  assert.equal(z.so("radar/bang"), 1);
  void p;
});

test("nhập UID gốc: sai dạng → báo ngay, KHÔNG gọi API; link đủ → POST radar/goc {uid} (chuỗi 19 số), xoá ô, tải lại", async () => {
  const x = dungRdu();
  await batDau(x);
  for (const sai of ["", "12345", `${UID}0`, "https://vt.tiktok.com/ZS1/", BAN]) {
    x.o.in.value = sai;
    await x.bam(x.nutDe("goc"));
    assert.match(x.o.msg.textContent, /UID phải đủ 19 chữ số/, sai);
    assert.equal(x.o.msg.className, "small rdu-loi");
  }
  assert.equal(x.so("radar/goc"), 0);
  assert.equal(x.so("radar/bang"), 1);
  x.o.in.value = `https://shop.tiktok.com/vn/pdp/${GOC}?x=1`;
  await x.bam(x.nutDe("goc"));
  const post = x.S.goi.filter((g) => g[0] === "radar/goc");
  assert.equal(post.length, 1);
  assert.deepEqual(post[0][1], { uid: GOC });
  assert.equal(typeof post[0][1].uid, "string");
  assert.equal(x.o.in.value, "");
  assert.equal(x.o.in.disabled, false);
  assert.match(x.o.msg.textContent, /Đã nhận UID/);
  assert.ok(x.S.toast.some((t) => /Đã nhận UID/.test(t)));
  assert.equal(x.so("radar/bang"), 2, "tải lại sau khi ghi");
  assert.equal(x.nutDe("goc").disabled, false);
  // da_co
  const y = dungRdu({ apiGia: async (p) => (p === "radar/bang" ? { status: 200, ...BANG() } : { status: 202, da_co: true, goc: GOC }) });
  await batDau(y);
  y.o.in.value = GOC;
  await y.bam(y.nutDe("goc"));
  assert.match(y.o.msg.textContent, /đã có trong Radar/);
});

test("khoá bấm đúp: khoá nút TRƯỚC await → bấm lần 2 trong lúc chờ không gửi lần 2; mở khoá sau khi xong", async () => {
  let mo;
  const cho = new Promise((r) => { mo = r; });
  const x = dungRdu({ apiGia: async (p) => { if (p === "radar/bang") return { status: 200, ...BANG() }; await cho; return { status: 202, da_co: false, goc: GOC }; } });
  await batDau(x);
  x.o.in.value = GOC;
  const nut = x.nutDe("goc");
  const a = x.bam(nut);
  assert.equal(nut.disabled, true, "khoá ngay, trước khi API trả lời");
  assert.equal(x.o.in.disabled, true);
  const b = x.bam(nut); // bấm đúp
  x.o.in.value = GOC;
  await b;
  assert.equal(x.so("radar/goc"), 1);
  mo(); await a;
  assert.equal(x.so("radar/goc"), 1);
  assert.equal(x.nutDe("goc").disabled, false);
  // cả khi nút bị bấm qua Enter
  const y = dungRdu();
  await batDau(y);
  y.o.in.value = GOC;
  let chan = 0;
  await y.goc.nghe.keydown({ key: "Enter", preventDefault: () => { chan++; }, target: { closest: (s) => (s === "[data-rdu-vao]" ? { closest: (s2) => (s2 === ".rdu-them" ? { querySelector: () => y.nutDe("goc") } : null) } : null) } });
  assert.equal(chan, 1);
  assert.equal(y.so("radar/goc"), 1, "Enter = bấm Theo dõi");
  await y.goc.nghe.keydown({ key: "a", preventDefault: () => { chan++; }, target: {} });
  assert.equal(chan, 1);
});

test("409/429 hiện đúng câu §7 và tải lại; 400 mở khoá không tải lại; mạng đứt giữa POST → GIỮ khoá tới lần tải thành công kế", async () => {
  // 409: api() trả r.status === 409 (không ném)
  let x = dungRdu({ apiGia: async (p) => (p === "radar/bang" ? { status: 200, ...BANG() } : { status: 409, loi: "Đã đủ 2 UID gốc: ngừng bớt" }) });
  await batDau(x);
  x.o.in.value = GOC;
  await x.bam(x.nutDe("goc"));
  assert.ok(x.S.toast.some((t) => t.includes("Đã đủ 2 UID gốc: ngừng bớt")), x.S.toast.join("|"));
  assert.equal(x.o.in.value, GOC, "409: giữ nội dung ô nhập");
  assert.equal(x.so("radar/bang"), 2);
  assert.equal(x.nutDe("goc").disabled, false);
  // 429 (ném)
  x = dungRdu({ apiGia: async (p) => { if (p === "radar/bang") return { status: 200, ...BANG() }; throw Object.assign(new Error("Vượt hạn mức (6 việc/ngày)"), { status: 429 }); } });
  await batDau(x);
  await x.bam(x.nutDe("chup-lai"));
  assert.ok(x.S.toast.some((t) => t.includes("Vượt hạn mức (6 việc/ngày)")));
  assert.equal(x.so("radar/bang"), 1, "429 chắc chắn chưa làm gì: không tải lại");
  assert.equal(x.nutDe("chup-lai").disabled, false);
  // mạng đứt
  let hong = true;
  x = dungRdu({ apiGia: async (p) => { if (p === "radar/bang") return { status: 200, ...BANG() }; if (hong) throw new TypeError("Failed to fetch"); return { status: 202, goc: GOC }; } });
  await batDau(x);
  x.o.in.value = GOC;
  await x.bam(x.nutDe("goc"));
  assert.ok(x.S.toast.some((t) => /Chưa chắc đã xong/.test(t)));
  assert.equal(x.nutDe("goc").disabled, true, "giữ khoá: không biết đã tới máy nhà chưa");
  hong = false;
  await x.bam(x.nutDe("goc")); // nút đang khoá → bỏ
  assert.equal(x.so("radar/goc"), 1, "không tự gửi lại");
  await x.K.rduTai(x.K.phien(), true); // tải thành công kế tiếp → mở khoá
  assert.equal(x.nutDe("goc").disabled, false);
  // 401: mở khoá, không tải lại
  x = dungRdu({ apiGia: async (p) => { if (p === "radar/bang") return { status: 200, ...BANG() }; throw Object.assign(new Error("Hết phiên đăng nhập — đăng nhập lại"), { status: 401 }); } });
  await batDau(x);
  x.o.in.value = GOC;
  await x.bam(x.nutDe("goc"));
  assert.ok(x.S.toast.some((t) => /Hết phiên đăng nhập/.test(t)));
  assert.equal(x.nutDe("goc").disabled, false);
});

test("Chụp lại hôm nay: hỏi xác nhận (huỷ → không gọi), đồng ý → POST radar/chup-lai {}", async () => {
  let x = dungRdu({ confirmTra: false });
  await batDau(x);
  await x.bam(x.nutDe("chup-lai"));
  assert.equal(x.S.xacNhan, 1);
  assert.equal(x.so("radar/chup-lai"), 0);
  x = dungRdu();
  await batDau(x);
  await x.bam(x.nutDe("chup-lai"));
  assert.deepEqual(x.S.goi.filter((g) => g[0] === "radar/chup-lai"), [["radar/chup-lai", {}]]);
  assert.ok(x.S.toast.some((t) => /chụp lại/.test(t)));
});

test("ghim/loại: POST đúng đường dẫn id 19 số (chuỗi) body {}; kiểm lại cờ từ dữ liệu đang hiện; id rác/giả mạo/UID gốc không gửi", async () => {
  const x = dungRdu();
  await batDau(x);
  await x.bam(x.nutDe("ghim", UID, GOC));
  assert.deepEqual(x.S.goi.filter((g) => g[0].includes("/ghim")), [[`radar/goc/${GOC}/uid/${UID}/ghim`, {}]]);
  assert.ok(x.S.toast.some((t) => /Đã ghim/.test(t)));
  assert.equal(x.so("radar/bang"), 2);
  await x.bam(x.nutDe("loai", UID, GOC));
  assert.ok(x.S.goi.some((g) => g[0] === `radar/goc/${GOC}/uid/${UID}/loai`));
  await x.bam(x.nutDe("bo-ghim", UID2, GOC));
  assert.ok(x.S.goi.some((g) => g[0] === `radar/goc/${GOC}/uid/${UID2}/bo-ghim`));
  const truoc = x.S.goi.length;
  const gia = (act, uid, g) => ({ disabled: false, dataset: { rduAct: act, rduUid: uid, rduGoc: g }, closest: () => null });
  for (const b of [gia("loai", GOC, GOC), gia("ghim", UID2, GOC), gia("ghim", "abc", GOC), gia("ghim", UID, "../x"), gia("ghim", UID, ""), gia("ghim", "1".repeat(19), GOC), gia("tim-lai", "", UID), gia("ngung", "", BAN), gia("xoa-het", UID, GOC)]) {
    await x.bam(b);
  }
  assert.equal(x.S.goi.length, truoc, "không gửi gì");
  assert.ok(x.S.toast.some((t) => /vừa đổi trạng thái/.test(t)));
});

test("nút nhóm + thêm tay: Tìm lại/Ngừng/Theo dõi lại đúng đường dẫn; nhóm đang tìm không Tìm lại; thêm tay sai dạng không gọi API, đúng → body {uid}", async () => {
  const x = dungRdu();
  await batDau(x);
  await x.bam(x.nutDe("tim-lai", "", GOC));
  assert.ok(x.S.goi.some((g) => g[0] === `radar/goc/${GOC}/tim-lai` && JSON.stringify(g[1]) === "{}"));
  await x.bam(x.nutDe("ngung", "", GOC));
  assert.ok(x.S.goi.some((g) => g[0] === `radar/goc/${GOC}/ngung`));
  const o = x.o.them[GOC] = { value: "abc", disabled: false };
  await x.bam(x.nutDe("them-tay", "", GOC));
  assert.equal(x.so(`radar/goc/${GOC}/them-tay`), 0);
  assert.ok(x.S.toast.some((t) => /UID phải đủ 19 chữ số/.test(t)));
  o.value = `https://shop.tiktok.com/view/product/${UID3}`;
  await x.bam(x.nutDe("them-tay", "", GOC));
  assert.deepEqual(x.S.goi.filter((g) => g[0].endsWith("/them-tay")), [[`radar/goc/${GOC}/them-tay`, { uid: UID3 }]]);
  assert.equal(o.value, "");
  assert.equal(o.disabled, false);
  // nhóm đã ngừng: theo-lai
  const y = dungRdu({ bang: BANG({ nhom: [NHOM({ trang_thai: "ngung" })] }) });
  await batDau(y);
  assert.equal(y.nutDe("tim-lai", "", GOC), undefined);
  await y.bam(y.nutDe("theo-lai", "", GOC));
  assert.ok(y.S.goi.some((g) => g[0] === `radar/goc/${GOC}/theo-lai`));
  // nút giả mạo tim-lai trên nhóm đang tìm → không gửi
  const z = dungRdu({ bang: BANG({ nhom: [NHOM({ trang_thai: "dang_tim", ds: [] })] }) });
  await batDau(z);
  await z.bam({ disabled: false, dataset: { rduAct: "tim-lai", rduGoc: GOC }, closest: () => null });
  assert.equal(z.so(`radar/goc/${GOC}/tim-lai`), 0);
});

test("📮 Poster: mở/đóng khung; Sao chép / Mở Folders chỉ chạy khi đã tick (UID ≠ gốc); KHÔNG gọi API nào ngoài GET bang; id sao chép là chuỗi 19 số", async () => {
  const x = dungRdu();
  await batDau(x);
  const p = x.o.panel;
  await x.bam(x.nutDe("poster", UID, GOC));
  assert.equal(p[UID].hidden, false, "mở khung");
  await x.bam(x.nutDe("poster", UID, GOC));
  assert.equal(p[UID].hidden, true, "đóng khung");
  // chưa tick: nút disabled → bấm bị bỏ
  assert.equal(x.nutDe("chep", UID, GOC).disabled, true);
  await x.bam(x.nutDe("chep", UID, GOC));
  await x.bam(x.nutDe("mo-folders", UID, GOC));
  assert.deepEqual(x.S.chep, []);
  assert.equal(x.S.viTri.hash, "");
  // kể cả khi nút bị gỡ disabled bằng devtools: JS kiểm lại ô tick → chặn
  for (const a of ["chep", "mo-folders"]) { const n = x.nutDe(a, UID, GOC); n.disabled = false; await x.bam(n); n.disabled = true; }
  assert.deepEqual(x.S.chep, []);
  assert.equal(x.S.viTri.hash, "");
  assert.equal(x.S.toast.filter((t) => /tick ô đối chiếu/.test(t)).length, 2);
  // tick → bật hai nút
  const tick = (x.o.tick[UID] ||= { checked: false });
  tick.checked = true;
  const hai = [x.nutDe("chep", UID, GOC), x.nutDe("mo-folders", UID, GOC)];
  await x.goc.nghe.change({ target: { closest: (s) => (s === "[data-rdu-tick]" ? { checked: true, closest: (s2) => (s2 === "[data-rdu-poster]" ? { querySelectorAll: () => hai } : null) } : null) } });
  assert.deepEqual(hai.map((b) => b.disabled), [false, false]);
  await x.bam(x.nutDe("chep", UID, GOC));
  assert.deepEqual(x.S.chep, [[UID, "Đã sao chép UID"]]);
  assert.equal(typeof x.S.chep[0][0], "string");
  await x.bam(x.nutDe("mo-folders", UID, GOC));
  assert.equal(x.S.viTri.hash, "#/poster/folders");
  // UID gốc: không cần tick
  await x.bam(x.nutDe("chep", GOC, GOC));
  assert.deepEqual(x.S.chep.at(-1), [GOC, "Đã sao chép UID"]);
  // không có gì ghi vào Poster / máy nhà
  assert.deepEqual([...new Set(x.S.goi.map((g) => g[0]))], ["radar/bang"]);
  // ô tick bỏ → hai nút khoá lại
  await x.goc.nghe.change({ target: { closest: (s) => (s === "[data-rdu-tick]" ? { checked: false, closest: (s2) => (s2 === "[data-rdu-poster]" ? { querySelectorAll: () => hai } : null) } : null) } });
  assert.deepEqual(hai.map((b) => b.disabled), [true, true]);
});

// ---------- 7. nguồn: CSP, tên, id, đường API, index.html, CSS, nhãn việc ----------
test("radar-uid.js: không inline/on…=, không bảng/style cứng/độ rộng cứng, không fetch/URL máy nhà, không ép id sang số, mọi tên cấp đỉnh bắt đầu 'rdu'", () => {
  assert.ok(!/\son[a-z]+\s*=/i.test(RDU.replace(/on…=/g, "")), "on…=");
  assert.ok(!/<table|style="|white-space:\s*nowrap|width:\s*\d/.test(RDU), "bảng/style cứng");
  assert.ok(!/\bfetch\s*\(|XMLHttpRequest|localhost|127\.0\.0\.1|\/r\/radar|\/radar\//.test(RDU), "gọi trực tiếp máy nhà");
  assert.ok(!/parseInt|parseFloat|Number\s*\(\s*(?:u|x|d|n|b)?\.?\s*(?:uid|goc)\b|\+\s*(?:uid|goc)\b/.test(RDU), "ép id sang số");
  assert.ok(!/<script/i.test(RDU));
  assert.match(RDU, /addEventListener\("click"/);
  const ten = [...RDU.matchAll(/^(?:async )?function\*? ?(\w+)|^(?:const|let|var|class) (\w+)/gm)].map((m) => m[1] || m[2]);
  assert.ok(ten.length >= 40, `đọc được ${ten.length} tên`);
  for (const t of ten) assert.ok(t.toLowerCase().startsWith("rdu"), `radar-uid.js: "${t}" phải bắt đầu bằng rdu`);
  for (const h of ["rduLayUid", "rduSo", "rduSpark", "rduNhanCo", "rduHangHtml", "rduNhomHtml", "rduBangHtml", "rduPosterHtml", "rduRender"]) assert.ok(ten.includes(h), h);
  // chỉ gọi qua api() của app.js: mọi đường dẫn bắt đầu "radar/"
  const duong = [...RDU.matchAll(/api\(\s*[`"]([^`"$]*)/g), ...RDU.matchAll(/rduGui\([^,]+,\s*[`"]([^`"$]*)/g)].map((m) => m[1]);
  assert.ok(duong.length >= 6 && duong.every((d) => d.startsWith("radar/")), duong.join(","));
  assert.ok(RDU.includes("`radar/goc/${goc}/uid/${uid}/${act}`"));
  // không có đường ghi vào Poster
  assert.ok(!/poster\/|pvApi|PATCH|\/api\/v2/.test(RDU.replace(/#\/poster\/folders/g, "").replace(/Poster V2/g, "")), "nút Poster không được ghi vào Poster V2");
});

test("index.html: radar-uid.js ngay SAU sua.js, ?v=3; ?v của style.css/khung.js/viec.js/loi.js đã nâng; không script inline", () => {
  assert.match(HTML, /<script src="sua\.js\?v=\d+" defer><\/script>\s*<script src="radar-uid\.js\?v=3" defer><\/script>\s*<\/head>/);
  const v = (f) => Number((HTML.match(new RegExp(`${f.replace(".", "\\.")}\\?v=(\\d+)`)) || [])[1]);
  assert.ok(v("style.css") >= 21, "style.css");
  assert.ok(v("khung.js") >= 6, "khung.js");
  assert.ok(v("viec.js") >= 18, "viec.js");
  assert.ok(v("loi.js") >= 8, "loi.js");
  assert.ok(!/<script(?![^>]*\ssrc=)[^>]*>/i.test(HTML));
  assert.equal((HTML.match(/radar-uid\.js/g) || []).length, 1);
  assert.deepEqual([...HTML.matchAll(/<link rel="stylesheet" href="([^"?]+)/g)].map((m) => m[1]), ["style.css", "menu.css", "poster.css"], "không thêm file CSS");
});

test("style.css: khối .rdu-* nối cuối, chỉ lớp .rdu-*, không cuộn ngang, hàng là lưới (không bảng), mục chính chiếm cả hàng", () => {
  const i = CSS.indexOf("/* Radar UID (D16");
  assert.ok(i > 0, "thiếu khối Radar UID");
  const khoi = CSS.slice(i).replace(/\/\*[\s\S]*?\*\//g, "");
  assert.ok(!/overflow-x:\s*(auto|scroll)|position:\s*fixed|<table/.test(khoi));
  const chon = khoi.replace(/@media[^{]*\{/g, "").split("}").map((r) => r.split("{")[0].trim()).filter(Boolean);
  assert.ok(chon.length >= 30, `đọc được ${chon.length} bộ chọn`);
  for (const sel of chon) for (const s of sel.split(",")) assert.match(s.trim(), /^\.rdu/, `bộ chọn ngoài .rdu: ${s}`);
  assert.match(khoi, /\.rdu-luoi \{[^}]*display: grid/);
  assert.match(khoi, /\.rdu-o-chinh \{[^}]*grid-column: 1 \/ -1/);
  assert.match(khoi, /\.rdu-poster\[hidden\] \{ display: none; \}/);
  assert.ok(CSS.indexOf("/* W-7 điện thoại */") < i, "khối W-7 (homnay-web) không bị chen");
  assert.ok(!/<table/i.test(RDU));
});

test("nhãn việc: viec.js TEN_LOAI_VIEC + loi.js LOI_LOAI_VIEC có radar_uid_hang_ngay, radar_uid_nap; LOAI_VIEC_SP (web tạo được) KHÔNG có; nhãn cũ giữ nguyên", () => {
  const N = new Function("esc", `"use strict";\n${khoi(LOI, "loi-thuan")}\n${khoi(VIEC, "viec-thuan")}\nreturn { LOI_LOAI_VIEC, loiLoaiViec, TEN_LOAI_VIEC, LOAI_VIEC_SP };`)(esc);
  for (const m of [N.TEN_LOAI_VIEC, N.LOI_LOAI_VIEC]) {
    assert.equal(m.radar_uid_hang_ngay, "Chụp Radar UID mỗi ngày");
    assert.equal(m.radar_uid_nap, "Nạp UID vào Radar");
  }
  assert.equal(N.loiLoaiViec("radar_uid_nap"), "Nạp UID vào Radar");
  for (const l of ["radar_uid_hang_ngay", "radar_uid_nap"]) assert.ok(!Object.prototype.hasOwnProperty.call(N.LOAI_VIEC_SP, l), l);
  assert.equal(N.TEN_LOAI_VIEC.hoc_hang_ngay, "Học mỗi ngày");
  assert.equal(N.LOI_LOAI_VIEC.quet_view_hang_ngay, "Quét view video của mình");
});
