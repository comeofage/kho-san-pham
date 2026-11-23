// Học tự động mỗi ngày (D15, docs/hoc-tu-dong.md §3.8, §3.9): khối "📈 Học hôm nay" trong trang Hôm nay + trang #/hoc
// (không có mục menu riêng, Q6), nút Hoàn tác / Bật lại (chỉ chủ kho, đi đường ký D7 ở Worker).
// Script thường, chung phạm vi toàn cục với app.js: mọi tên cấp đỉnh bắt đầu bằng "hc"/"HC_" (P2-7, test cf/test/menu-web.test.mjs).
// Dùng của app.js lúc chạy: $, esc, api, toast, laChu, phienCT. Được gọi từ homnay.js (hcKhoiHomNayHtml) và khung.js (hcRender).
// Web KHÔNG tự tính điều kiện nút: Hoàn tác chỉ khi co_the_hoan_tac === true, Bật lại chỉ khi co_the_bat_lai === true (máy nhà tính).
// CSP script-src 'self': KHÔNG script inline, KHÔNG thuộc tính on…= — sự kiện gắn bằng addEventListener.
"use strict";

// --- hoc-thuan start ---
// Hàm thuần: không đụng DOM/fetch; chỉ dùng `esc` (app.js) lúc gọi. Mọi chuỗi từ API vẽ ra HTML đều qua esc.
const HC_RE_MA = /^bh\d{8}[a-z0-9]{4}$/;
const HC_RE_NGAY = /^(\d{4})-(\d{2})-(\d{2})$/;
const HC_FMT_NGAY = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh", year: "numeric", month: "2-digit", day: "2-digit" });
const HC_FMT_GIO = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Ho_Chi_Minh", hour: "2-digit", hourCycle: "h23" });
const HC_GIO_HOC = 12; // việc học chạy từ 12:00 giờ VN (§0): sau mốc này mà nguồn view cũ 1 ngày → báo vàng
const HC_KY_DIEU_KHIEN = /[\u0000-\u001f\u007f]/g;

const hcCo = (o, k) => !!o && typeof o === "object" && typeof k === "string" && Object.prototype.hasOwnProperty.call(o, k);
const hcObj = (o) => (o && typeof o === "object" && !Array.isArray(o) ? o : {});
const hcMang = (a) => (Array.isArray(a) ? a.filter((x) => x && typeof x === "object" && !Array.isArray(x)) : []);
const hcSo = (n) => (Number.isInteger(n) ? n : null);
const hcN = (n) => (Number.isInteger(n) ? String(n) : "?"); // số để hiện: chỉ số nguyên, còn lại "?"
const hcChu = (s, toiDa = 200) => (typeof s === "string" ? s.slice(0, toiDa) : "");
const hcNhan = (bang, k, macDinh) => (hcCo(bang, k) ? bang[k] : macDinh);
function hcHomNay(nowMs) { return Number.isFinite(nowMs) ? HC_FMT_NGAY.format(new Date(nowMs)) : ""; }
function hcGioVn(nowMs) { return Number.isFinite(nowMs) ? Number(HC_FMT_GIO.format(new Date(nowMs))) : NaN; }

// "YYYY-MM-DD" (giữ nguyên ngày) hoặc ISO có giờ (đổi sang ngày VN) → "dd/mm". Sai → "".
function hcDm(s) {
  if (typeof s !== "string") return "";
  const m = s.match(HC_RE_NGAY);
  if (m) return `${m[3]}/${m[2]}`;
  const t = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s) ? Date.parse(s) : NaN;
  if (!Number.isFinite(t)) return "";
  const n = HC_FMT_NGAY.format(new Date(t));
  return `${n.slice(8, 10)}/${n.slice(5, 7)}`;
}

const HC_TEN_TT = { ung_vien: "Ứng viên", hieu_luc: "Đang dùng", het_han: "Hết hạn", tat_tu_dong: "Tự tắt", hoan_tac: "Đã hoàn tác" };
const HC_TEN_NGUON = { poster_view: "view video", van_hanh: "vận hành", sua_tay: "sửa tay" };
const HC_TEN_HUONG = { tang: "view cao hơn", giam: "view thấp hơn" };
const HC_TT_LAN = { xong: "đã học xong", tu_dung: "tạm dừng", loi: "bị lỗi", dang_chay: "đang chạy", khong_chay: "chưa chạy" };
const HC_TT_POSTER = { ok: "ổn", cu: "cũ", thieu: "thiếu số đo", lech: "lệch nối", loi: "lỗi" };
const HC_TT_QUET = { ok: "ổn", loi: "lỗi", cho: "đang chờ", dang_chay: "đang chạy", chua_tao: "chưa tạo", huy: "đã huỷ" };
// Nhãn ngắn cho mã ly_do của thay_doi: phủ ĐÚNG hoc_danh_muc.LY_DO_CHUYEN trừ LY_DO_THUONG_NGAY (báo cáo đã lọc nhóm đó) —
// test cf/test/hoc-web.test.mjs đọc file .py so bộ mã.
const HC_LY_DO_NGAN = {
  dat_nguong_3_ngay: "đủ 3 ngày liền", cho_suc_chua: "chờ chỗ trống", dut_chuoi: "không còn đạt ngưỡng", het_bang_chung: "hết bằng chứng",
  doi_chieu: "đổi chiều", het_han: "hết hạn", nguoi_hoan_tac: "chủ kho hoàn tác", nguoi_bat_lai: "chủ kho bật lại", dat_lan_dau: "đạt ngưỡng lần đầu",
};
// Mã "thiếu" của một số đo: khớp ĐÚNG bộ khoá hoc_danh_muc.TEN_THIEU (test so bộ mã); nhãn ngắn của web.
const HC_THIEU = {
  so_uid: "chưa đủ SP", so_video: "chưa đủ video", lift: "lệch chưa đủ", nhat_quan: "chưa đủ cùng chiều",
  huong_lech: "hướng ngược dấu độ lệch", so_lan: "chưa đủ số lần", ty_le: "tỉ lệ chưa đủ", chua_co_nguon: "chưa có nguồn",
};
const HC_TEN_BOI = { he_thong: "hệ thống" }; // kho_hoc.BOI_HE_THONG; tên người dùng hiện nguyên

// "YYYY-MM-DD" đã kiểm → số ngày kể từ mốc (UTC, chỉ để trừ 2 ngày lịch).
function hcSoNgay(s) { const m = s.match(HC_RE_NGAY); return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) / 86400000; }

// Ngày của số liệu so với hôm nay giờ VN (P1-1: GET hoc/bao-cao không kèm ngay → lần học MỚI NHẤT, có thể là ngày cũ).
// {laHomNay, dm: "dd/mm"|"", cu: số ngày cũ hơn hôm nay (0 = cùng ngày/không rõ), nhan: "hôm nay"|"ngày dd/mm", Nhan: viết hoa đầu câu}.
function hcNgaySoLieu(bc, nowMs) {
  const ngay = hcObj(bc).ngay;
  const ok = typeof ngay === "string" && HC_RE_NGAY.test(ngay);
  const homNay = hcHomNay(nowMs);
  const laHomNay = ok && homNay !== "" && ngay === homNay;
  const cu = ok && homNay !== "" && ngay < homNay ? Math.round(hcSoNgay(homNay) - hcSoNgay(ngay)) : 0;
  const dm = ok ? hcDm(ngay) : "";
  const nhan = laHomNay ? "hôm nay" : `ngày ${dm || "?"}`;
  return { laHomNay, dm, cu, nhan, Nhan: nhan[0].toUpperCase() + nhan.slice(1) };
}
const hcCauNgaySoLieu = (n) => `Số liệu ngày ${n.dm || "?"}${n.laHomNay ? " (hôm nay)" : ""}`;

// Cầu dao §4.3 (HT-W3): bc.han_muc = {bat_ngay, hieu_luc_toi_da} (runner HT-B4). Vắng/rác → coi như không biết (hành vi cũ).
const HC_CAU_TAT = "Gợi ý học đang TẮT (cau_hinh.json: hoc_bat_ngay = 0) — không bài nào vào phiếu.";
const hcHanMuc = (bc) => hcObj(hcObj(bc).han_muc);
const hcHocTat = (bc) => hcHanMuc(bc).bat_ngay === 0;
// Bài hieu_luc mà runner báo vao_phieu === false (bị cầu dao cắt) — chỉ boolean false mới tính; vắng → như cũ "Đang dùng".
const hcKhongVaoPhieu = (b) => hcObj(b).trang_thai === "hieu_luc" && hcObj(b).vao_phieu === false;
function hcNhanKhongVao(hm) {
  const x = hcObj(hm);
  if (x.bat_ngay === 0) return "Hiệu lực nhưng KHÔNG vào phiếu (gợi ý học đang tắt: hoc_bat_ngay = 0)";
  const tran = hcSo(x.hieu_luc_toi_da);
  return tran !== null ? `Hiệu lực nhưng KHÔNG vào phiếu (vượt trần hieu_luc_toi_da = ${tran})` : "Hiệu lực nhưng KHÔNG vào phiếu";
}

// Cảnh báo (§3.9 + P1-1): [{muc: "do"|"vang", cau}] (CHƯA esc).
// Báo cáo cũ hơn hôm nay: sau 12:00 (giờ học chạy) hoặc cũ ≥ 2 ngày → ĐỎ "Bộ học chưa chạy từ dd/mm"; trước 12:00 mà cũ đúng
// 1 ngày là bình thường (học hôm nay chưa tới giờ) → không đỏ, ngày số liệu hiện ở dòng "Số liệu ngày dd/mm".
function hcCanhBao(bc, nowMs) {
  const n = hcNgaySoLieu(bc, nowMs);
  const pv = hcObj(hcObj(hcObj(bc).nguon).poster_view);
  const q = hcObj(pv.quet_hom_nay);
  const cu = hcSo(pv.so_ngay_cu);
  const ra = [];
  if (hcHocTat(bc)) ra.push({ muc: "vang", cau: HC_CAU_TAT });
  if (n.cu >= 2 || (n.cu === 1 && hcGioVn(nowMs) >= HC_GIO_HOC)) ra.push({ muc: "do", cau: `Bộ học chưa chạy từ ${n.dm}` });
  if (cu !== null && cu >= 2) {
    const dm = hcDm(pv.ngay_moi_nhat);
    const moi = dm ? ` (lần có số mới nhất ${dm})` : "";
    ra.push({ muc: "do", cau: n.laHomNay ? `Nguồn view đã cũ ${cu} ngày${moi} — bộ học đang tạm dừng`
      : `${n.Nhan}: nguồn view đã cũ ${cu} ngày${moi} — bộ học tạm dừng` });
  }
  if (q.trang_thai === "loi") ra.push({ muc: "vang", cau: `Quét view ${n.nhan} lỗi: ${hcChu(q.ten_ly_do, 160) || "chưa rõ lý do"}` });
  else if (cu === 1 && n.laHomNay && hcGioVn(nowMs) >= HC_GIO_HOC) ra.push({ muc: "vang", cau: "Hôm nay chưa có view mới" });
  else if (cu === 1 && !n.laHomNay) ra.push({ muc: "vang", cau: `${n.Nhan} chưa có view mới` });
  return ra;
}

// Câu "bình thường" của ngày số liệu (CHƯA esc): trạng thái lần học, hoặc tóm tắt thay đổi, hoặc "không đổi gì — chưa đủ mẫu".
// "Hôm nay" chỉ khi bc.ngay là hôm nay giờ VN; còn lại "Ngày dd/mm".
function hcCauHomNay(bc, nowMs) {
  const x = hcObj(bc);
  const n = hcNgaySoLieu(x, nowMs);
  const lan = hcObj(x.lan);
  const ld = hcChu(lan.ten_ly_do, 160);
  if (lan.trang_thai === "loi") return `Lần học ${n.nhan} bị lỗi${ld ? `: ${ld}` : ""}`;
  if (lan.trang_thai === "tu_dung") return `${n.Nhan} bộ học tạm dừng${ld ? `: ${ld}` : ""}`;
  if (lan.trang_thai === "dang_chay") return n.laHomNay ? "Bộ học đang chạy — xem lại sau ít phút" : `Lần học ${n.nhan} chưa kết thúc`;
  if (lan.trang_thai === "khong_chay") return `${n.Nhan} bộ học chưa chạy`;
  const td = hcMang(x.thay_doi);
  const dem = (f) => td.filter(f).length;
  const batMoi = dem((t) => t.den === "hieu_luc" && t.tu === "ung_vien");
  const batLai = dem((t) => t.den === "hieu_luc" && !!t.tu && t.tu !== "ung_vien");
  const khoiPhuc = dem((t) => t.den === "ung_vien" && t.tu === "hoan_tac");
  const hoanTac = dem((t) => t.den === "hoan_tac");
  // tat_tu_dong từ ứng viên (dut_chuoi) là ứng viên dừng, KHÔNG phải tắt gợi ý đang dùng (P3-3)
  const tat = td.filter((t) => t.den === "tat_tu_dong" && t.tu !== "ung_vien");
  const uvDung = dem((t) => t.den === "tat_tu_dong" && t.tu === "ung_vien");
  const hetHan = dem((t) => t.den === "het_han");
  const choCho = dem((t) => t.den === "ung_vien" && t.tu === "ung_vien" && t.ly_do === "cho_suc_chua");
  const uvMoi = dem((t) => t.den === "ung_vien" && !t.tu);
  const phan = [];
  if (batMoi) phan.push(`Đã bật ${batMoi} gợi ý mới`);
  if (batLai) phan.push(`Đã bật lại ${batLai} gợi ý`);
  if (khoiPhuc) phan.push(`Đã khôi phục ${khoiPhuc} gợi ý về ứng viên`);
  if (hoanTac) phan.push(`Đã hoàn tác ${hoanTac} gợi ý`);
  if (tat.length) {
    const lyDo = [...new Set(tat.map((t) => hcNhan(HC_LY_DO_NGAN, t.ly_do, "")).filter(Boolean))];
    phan.push(`Đã tự tắt ${tat.length} gợi ý${lyDo.length ? ` (${lyDo.join(", ")})` : ""}`);
  }
  if (uvDung) phan.push(`${uvDung} ứng viên dừng (không còn đạt ngưỡng)`);
  if (hetHan) phan.push(`${hetHan} gợi ý hết hạn`);
  if (choCho) phan.push(`${choCho} ứng viên đủ ngày, chờ chỗ trống`);
  if (uvMoi) phan.push(`${uvMoi} ứng viên mới`);
  if (phan.length) return `${n.laHomNay ? "" : `${n.Nhan}: `}${phan.join(" · ")}`;
  const can = hcSo(hcObj(x.nguong).so_uid_toi_thieu) ?? 20;
  const co = Math.max(0, ...hcMang(x.do_luong).filter((d) => d.nguon === "poster_view").map((d) => hcSo(d.so_uid) ?? 0));
  return co < can ? `${n.Nhan}: không đổi gì — chưa đủ mẫu (cần ${can} SP, đang có ${co})` : `${n.Nhan}: không đổi gì`;
}

const hcDongHtml = (muc, cau) => `<div class="hn-tt${muc === "do" ? " hn-loi" : muc === "vang" ? " hn-cho-ban" : ""}" data-hc-muc="${muc}">${esc(cau)}</div>`;
function hcDongNgayHtml(bc, nowMs) {
  return hcCanhBao(bc, nowMs).map((c) => hcDongHtml(c.muc, c.cau)).join("") + hcDongHtml("thuong", hcCauHomNay(bc, nowMs));
}

// Khối "📈 Học hôm nay" trong trang Hôm nay (chỉ chủ kho — homNayHtml chỉ gọi khi t.chu). Báo cáo hỏng → "" (không vẽ).
function hcKhoiHomNayHtml(bc, nowMs) {
  if (!bc || typeof bc !== "object" || Array.isArray(bc)) return "";
  return `<section class="hn-khoi hn-hoc"><h2 class="hn-tieu-de">📈 Học hôm nay</h2>`
    + `<p class="small muted">${esc(hcCauNgaySoLieu(hcNgaySoLieu(bc, nowMs)))}</p>${hcDongNgayHtml(bc, nowMs)}`
    + `<a class="small" href="#/hoc">Xem chi tiết học tự động →</a></section>`;
}

// Câu hộp xác nhận (confirm hiện chữ thô, không phải HTML: chỉ bỏ ký tự điều khiển + cắt ngắn).
function hcCauXacNhan(act, b) {
  const x = hcObj(b);
  const ten = hcChu(x.ten, 80).replace(HC_KY_DIEU_KHIEN, " ").trim() || "(không tên)";
  if (act === "hoan-tac") {
    return `Hoàn tác gợi ý '${ten}'? Gợi ý sẽ thôi vào phiếu phân tích mới và bộ học không tự học lại gợi ý này trong 30 ngày. Bấm nhầm thì Bật lại được trong 7 ngày.`;
  }
  if (x.trang_thai === "hoan_tac" && !x.bat_luc) return `Khôi phục '${ten}' về ứng viên? Gợi ý chưa vào phiếu, vẫn phải đạt đủ ngày liên tiếp như thường.`;
  // Bài vận hành sống cố định 28 ngày, không tự tắt vì hết bằng chứng (§4.1b) → không hứa "tự tắt lại".
  if (x.nguon === "van_hanh") return `Bật lại gợi ý '${ten}'? Gợi ý sẽ vào phiếu phân tích mới trong 28 ngày.`;
  return `Bật lại gợi ý '${ten}'? Gợi ý sẽ vào phiếu phân tích mới trong 14 ngày, và tự tắt lại nếu lần học kế tiếp không còn đủ bằng chứng giữ (≥ 20 SP, ≥ 60% cùng chiều).`;
}

// Nút ghi theo trạng thái + cờ máy nhà (§3.9). chu !== true → không nút ghi nào.
function hcNutHtml(b, nowMs, chu) {
  const x = hcObj(b);
  if (chu !== true || typeof x.ma !== "string" || !HC_RE_MA.test(x.ma)) return "";
  const nut = (act, nhan) => `<button type="button" class="btn ghost sm" data-hc-act="${act}" data-hc-ma="${esc(x.ma)}">${esc(nhan)}</button>`;
  const ghi = (cau) => `<span class="small muted">${esc(cau)}</span>`;
  const tt = x.trang_thai;
  if (tt === "ung_vien" || tt === "hieu_luc") return x.co_the_hoan_tac === true ? nut("hoan-tac", "Hoàn tác") : "";
  if (tt === "hoan_tac") {
    const den = typeof x.bat_lai_den === "string" && HC_RE_NGAY.test(x.bat_lai_den) ? x.bat_lai_den : "";
    if (x.co_the_bat_lai === true) return nut("bat-lai", "Bật lại") + (den ? ghi(`Bật lại được tới hết ${hcDm(den)}`) : "");
    const homNay = hcHomNay(nowMs);
    if (!den || (homNay && den < homNay)) return ghi("Đã quá 7 ngày, chờ bộ học tự học lại sau 30 ngày cấm");
    return ghi(`Chưa bật lại được lúc này (hạn bật lại tới hết ${hcDm(den)}) — có thể đang có gợi ý cùng loại hoặc đã đủ số gợi ý đang dùng`);
  }
  if (tt === "tat_tu_dong" || tt === "het_han") {
    if (x.co_the_bat_lai === true) return nut("bat-lai", "Bật lại");
    // Ứng viên đứt chuỗi (chưa từng hiệu lực, bat_luc rỗng): máy nhà KHÔNG BAO GIỜ cho bật lại (§4.2 điều kiện 1) — câu vĩnh viễn.
    if (!(typeof x.bat_luc === "string" && x.bat_luc)) return ghi("Ứng viên dừng trước khi được dùng — không bật lại được; bộ học tự xét lại khi khoá này đạt ngưỡng lần nữa");
    return ghi("Chưa bật lại được lúc này — có thể đang có gợi ý cùng loại, đã đủ số gợi ý đang dùng hoặc đang tắt tự áp dụng");
  }
  return "";
}

// 1 bài học (BaiHocRa) → 1 mục. ngayCan: số ngày liên tiếp cần để bật (ngưỡng). hm: bc.han_muc (có thể vắng).
function hcBaiHtml(b, nowMs, chu, ngayCan, hm) {
  const x = hcObj(b);
  const tt = x.trang_thai;
  const bcg = hcObj(x.bang_chung);
  const khongVao = hcKhongVaoPhieu(x);
  const meta = [khongVao ? hcNhanKhongVao(hm) : hcNhan(HC_TEN_TT, tt, "Không rõ"), `nguồn ${hcNhan(HC_TEN_NGUON, x.nguon, "khác")}`];
  if (x.nguon === "poster_view" && hcCo(HC_TEN_HUONG, x.huong)) meta.push(HC_TEN_HUONG[x.huong]);
  if (x.nguon === "van_hanh") {
    // §4.1b: nguồn vận hành dùng so_uid = số LẦN khớp, so_video = số VIỆC cùng loại, nhat_quan_pt = tỉ lệ (kho_hoc.py canh_bao_van_hanh)
    if (Number.isInteger(bcg.so_uid)) meta.push(`${bcg.so_uid} lần / ${hcN(bcg.so_video)} việc${Number.isInteger(bcg.nhat_quan_pt) ? ` (${bcg.nhat_quan_pt}%)` : ""}`);
  } else {
    if (Number.isInteger(bcg.so_uid)) meta.push(`${bcg.so_uid} SP`);
    if (Number.isInteger(bcg.nhat_quan_pt)) meta.push(`${bcg.nhat_quan_pt}% cùng chiều`);
    if (Number.isInteger(bcg.lift_pt)) meta.push(`lệch ${bcg.lift_pt}%`);
  }
  if (tt === "ung_vien") meta.push(`đạt ${hcN(x.ngay_dat_lien_tiep)}/${ngayCan} ngày liền`);
  if (tt === "hieu_luc") {
    if (hcDm(x.het_han_luc)) meta.push(`${khongVao ? "hiệu lực" : "dùng"} tới hết ${hcDm(x.het_han_luc)}`);
    if (Number.isInteger(x.so_sp_da_ap)) meta.push(`đã vào ${x.so_sp_da_ap} phiếu`);
  }
  if (tt === "tat_tu_dong" || tt === "het_han" || tt === "hoan_tac") {
    const luc = hcDm(x.tat_luc), boi = hcNhan(HC_TEN_BOI, x.tat_boi, hcChu(x.tat_boi, 40)), lyDo = hcChu(x.ten_ly_do_tat, 160);
    if (luc) meta.push(`ngày ${luc}${boi ? ` bởi ${boi}` : ""}`);
    if (lyDo) meta.push(lyDo);
  }
  const ma = typeof x.ma === "string" && HC_RE_MA.test(x.ma) ? x.ma : "";
  const nut = hcNutHtml(x, nowMs, chu);
  return `<div class="hn-muc-sp">${esc(hcChu(x.ten, 120) || "(gợi ý không tên)")}</div>`
    + (x.goi_y ? `<div class="hn-muc-cau small">${esc(hcChu(x.goi_y, 400))}</div>` : "")
    + `<div class="hn-muc-cau small muted">${esc(meta.join(" · "))}${ma ? ` · <span>${esc(ma)}</span>` : ""}</div>`
    + (nut ? `<div class="row hn-tay">${nut}</div>` : "");
}

const hcKhoiHtml = (ma, tieuDe, muc, rong) => `<section class="hn-khoi hc-${ma}"><h2 class="hn-tieu-de">${esc(tieuDe)} (${muc.length})</h2>`
  + (muc.length ? `<div class="hn-ds">${muc.map((h) => `<div class="hn-muc">${h}</div>`).join("")}</div>` : `<p class="small muted">${esc(rong)}</p>`)
  + `</section>`;

// Trang #/hoc (BaoCao §3.8). chu: chỉ true mới có nút ghi.
function hcTrangHtml(bc, nowMs, chu) {
  const x = hcObj(bc);
  const lan = hcObj(x.lan);
  const ng = hcObj(x.nguong);
  const pv = hcObj(hcObj(x.nguon).poster_view);
  const vh = hcObj(hcObj(x.nguon).van_hanh);
  const q = hcObj(pv.quet_hom_nay);
  const c7 = hcObj(x.chi_so_7_ngay);
  const ngayCan = hcSo(ng.ngay_lien_tiep) ?? 3;
  const ra = [];
  const n = hcNgaySoLieu(x, nowMs); // P1-1: "hôm nay" chỉ khi bc.ngay là hôm nay giờ VN
  const ld = hcChu(lan.ten_ly_do, 160);
  ra.push(`<section class="hn-khoi hc-hom-nay"><h2 class="hn-tieu-de">${esc(hcCauNgaySoLieu(n))}</h2>${hcDongNgayHtml(x, nowMs)}`
    + `<p class="small muted">${esc(`Lần học: ${hcNhan(HC_TT_LAN, lan.trang_thai, "không rõ")}${ld ? ` (${ld})` : ""}${lan.du_lieu_moi === true ? " · có dữ liệu mới" : ""}`)}</p>`
    + `<p class="small">${esc(`7 ngày qua: máy bật ${hcN(c7.ngay_may_bat)} · quét view ổn ${hcN(c7.ngay_quet_ok)} · học chạy ${hcN(c7.ngay_hoc_chay)} · `)}`
    + `<b>${esc(`có dữ liệu mới ${hcN(c7.ngay_du_lieu_moi)}`)}</b></p></section>`);
  // Nguồn
  const qld = hcChu(q.ten_ly_do, 160);
  ra.push(hcKhoiHtml("nguon", "Nguồn dữ liệu", [
    esc(`View video (Poster): ${hcNhan(HC_TT_POSTER, pv.trang_thai, "không rõ")}`
      + `${hcDm(pv.ngay_moi_nhat) ? ` · số mới nhất ${hcDm(pv.ngay_moi_nhat)}` : ""} · ${hcN(pv.so_video_hop_le)} video dùng được · ${hcN(pv.so_uid)} SP`
      + ` · ${hcN(pv.so_lan_do_ngay)} lần đo ${n.nhan} (trung vị 7 ngày ${hcN(pv.trung_vi_lan_do_7_ngay)})`
      + ` · bỏ ${hcN(pv.bo_caption_ngoai_kho)} caption ngoài kho, ${hcN(pv.bo_mo_ho)} mơ hồ`),
    esc(`Quét view ${n.nhan}: ${hcNhan(HC_TT_QUET, q.trang_thai, "không rõ")}${qld ? ` (${qld})` : ""}`),
    esc(`Vận hành máy nhà: ${hcNhan(HC_TT_POSTER, vh.trang_thai, "không rõ")} · ${hcN(vh.so_viec)} việc, ${hcN(vh.so_loi)} lỗi`),
    esc("Sửa tay của nhân viên: chưa có nguồn sửa tay"),
  ], ""));
  // Thay đổi trong ngày
  ra.push(hcKhoiHtml("thay-doi", `Thay đổi ${n.nhan}`, hcMang(x.thay_doi).map((t) => esc(`${hcChu(t.ten, 120) || "(không tên)"}: `
    + `${hcNhan(HC_TEN_TT, t.tu, "mới")} → ${hcNhan(HC_TEN_TT, t.den, "không rõ")}${hcNhan(HC_LY_DO_NGAN, t.ly_do, "") ? ` (${HC_LY_DO_NGAN[t.ly_do]})` : ""}`)),
  `${n.Nhan} không có gợi ý nào đổi trạng thái.`));
  // HT-W3: bài hieu_luc bị cầu dao cắt (vao_phieu === false) tách khỏi "Đang dùng" sang khối riêng (chỉ vẽ khi có).
  const hm = x.han_muc;
  const hl = hcMang(x.hieu_luc);
  const hlKhong = hl.filter(hcKhongVaoPhieu);
  ra.push(hcKhoiHtml("hieu-luc", "Đang dùng", hl.filter((b) => !hcKhongVaoPhieu(b)).map((b) => hcBaiHtml(b, nowMs, chu, ngayCan, hm)),
    hcHocTat(x) ? HC_CAU_TAT : "Chưa có gợi ý nào đang vào phiếu phân tích."));
  if (hlKhong.length) {
    ra.push(hcKhoiHtml("khong-vao-phieu", "Hiệu lực nhưng KHÔNG vào phiếu", hlKhong.map((b) => hcBaiHtml(b, nowMs, chu, ngayCan, hm)), ""));
  }
  ra.push(hcKhoiHtml("ung-vien", "Ứng viên", hcMang(x.ung_vien).map((b) => hcBaiHtml(b, nowMs, chu, ngayCan, hm)),
    `Chưa có ứng viên — cần đạt ngưỡng ${ngayCan} ngày liền mới thành gợi ý.`));
  ra.push(hcKhoiHtml("da-tat", "Đã tự tắt / hết hạn / đã hoàn tác", hcMang(x.da_tat).map((b) => hcBaiHtml(b, nowMs, chu, ngayCan, hm)),
    "Chưa có gợi ý nào bị tắt."));
  // Đo lường hôm nay
  ra.push(hcKhoiHtml("do-luong", `Đo lường ${n.nhan}`, hcMang(x.do_luong).map((d) => {
    const thieu = Array.isArray(d.thieu) ? d.thieu.filter((k) => typeof k === "string").map((k) => hcNhan(HC_THIEU, k, hcChu(k, 40))) : [];
    const so = d.nguon === "van_hanh"
      ? `${hcN(d.so_uid)} lần / ${hcN(d.so_video)} việc (${hcN(d.nhat_quan_pt)}%)`
      : `${hcN(d.so_uid)} SP · ${hcN(d.so_video)} video · ${hcN(d.so_caption)} caption · lệch ${hcN(d.lift_pt)}% · ${hcN(d.nhat_quan_pt)}% cùng chiều`;
    return `<div class="hn-muc-sp">${esc(hcChu(d.ten, 120) || "(không tên)")}</div>`
      + `<div class="hn-muc-cau small${d.dat === true ? "" : " muted"}">${esc(`${d.dat === true ? "✓ đạt" : "chưa đạt"} · ${so}${thieu.length ? ` · ${thieu.join(", ")}` : ""}`)}</div>`;
  }), `${n.Nhan} chưa đo được khoá nào.`));
  ra.push(hcKhoiHtml("van-hanh", "Lỗi vận hành lặp lại", hcMang(x.canh_bao_van_hanh).map((c) =>
    esc(`${hcChu(c.ten, 120) || "(không tên)"}: ${hcN(c.so_lan)} lần / ${hcN(c.so_viec)} việc trong ${hcN(c.cua_so_ngay)} ngày`)),
  "Không có lỗi vận hành lặp lại."));
  ra.push(`<p class="small muted">${esc(`Ngưỡng bật gợi ý caption: ≥ ${hcN(ng.so_uid_toi_thieu)} SP, ≥ ${hcN(ng.so_video_toi_thieu)} video, `
    + `lệch ≥ ${hcN(ng.lift_toi_thieu_pt)}%, ≥ ${hcN(ng.nhat_quan_toi_thieu_pt)}% cùng chiều, ${hcN(ng.ngay_lien_tiep)} ngày liền có dữ liệu mới.`)}</p>`);
  return ra.join("\n");
}

// Thân lỗi ({"loi"} → err.message của api() trong app.js) theo từng chặng (P3-5) — CHỈ những câu sau mới được hiểu riêng:
//  runner (kho_hoc / hoc_danh_muc.TEN_LY_DO): 404 "chưa có lần học nào" (bao-cao), 404 "không có bài học" (bai-hoc/<ma>);
//  runner chưa nối kho_hoc (§3.8): 503 "Học tự động chưa bật";
//  Worker: 503 "Chưa cấu hình bộ chạy việc" (cf/src/hoc.js), 503 "Khoá ký bộ chạy việc không hợp lệ (KY_RIENG)" (worker.js, chỉ POST).
// 404 khác ("Đường dẫn không hợp lệ" của video_server chưa khởi động lại, "không có API này" của runner/Worker cũ…) = máy nhà
// chưa có tuyến học → câu trung tính. 503 lạ (không phải JSON của 2 chặng trên) = lỗi tạm.
const HC_LOI_CHUA_CO_LAN = "chưa có lần học nào";
const HC_LOI_KHONG_BAI = "không có bài học";
const HC_LOI_CHUA_BAT = "Học tự động chưa bật";
const HC_RE_LOI_CAU_HINH = /^(Chưa cấu hình bộ chạy việc|Khoá ký bộ chạy việc không hợp lệ \(KY_RIENG\))$/;

// err → "dang_nhap" | "quyen" | "chua_co_lan" | "khong_bai" | "chua_ho_tro" | "chua_bat" | "cau_hinh" | "tu_choi" | "tam".
function hcLoaiLoi(err) {
  const st = err && typeof err === "object" ? err.status : 0;
  const msg = err && typeof err.message === "string" ? err.message.trim() : "";
  if (st === 401) return "dang_nhap";
  if (st === 403) return "quyen";
  if (st === 404) return msg === HC_LOI_CHUA_CO_LAN ? "chua_co_lan" : msg === HC_LOI_KHONG_BAI ? "khong_bai" : "chua_ho_tro";
  if (st === 503) return msg === HC_LOI_CHUA_BAT ? "chua_bat" : HC_RE_LOI_CAU_HINH.test(msg) ? "cau_hinh" : "tam";
  if (Number.isInteger(st) && st >= 400 && st < 500) return "tu_choi";
  return "tam"; // mạng, 5xx (502/504 của Worker), không rõ
}
const HC_CAU_CHUA_HO_TRO = "Máy nhà chưa hỗ trợ học tự động — cần cập nhật máy nhà";
const HC_CAU_CAU_HINH = "Máy chủ web chưa cấu hình đúng kết nối tới máy nhà — báo người quản trị";

// Lỗi tải báo cáo → câu lời thường (CHƯA esc). Không bao giờ đưa thân lỗi máy chủ ra.
function hcCauLoiTai(err) {
  const l = hcLoaiLoi(err);
  if (l === "dang_nhap") return "Hết phiên đăng nhập — đăng nhập lại để xem.";
  if (l === "quyen") return "Tài khoản này không xem được phần này.";
  if (l === "chua_co_lan") return "Bộ học chưa chạy lần nào — báo cáo đầu tiên có sau 12:00 hằng ngày.";
  if (l === "chua_ho_tro" || l === "khong_bai") return `${HC_CAU_CHUA_HO_TRO}.`;
  if (l === "chua_bat") return "Học tự động chưa bật trên máy nhà.";
  if (l === "cau_hinh") return `${HC_CAU_CAU_HINH}.`;
  if (l === "tu_choi") return "Máy chủ không nhận yêu cầu này — bấm Tải lại.";
  return "Chưa tải được báo cáo học — mạng chập chờn hoặc máy nhà đang tắt. Bấm Tải lại.";
}
// --- hoc-thuan end ---

// ---------- phần có DOM ----------
let hcLuot = 0; // số lượt tải báo cáo: kết quả của lượt cũ về muộn thì bỏ (đặt TRƯỚC await)
let hcBai = new Map(); // ma → bài học đang hiện (hcBam kiểm lại cờ co_the_* từ đây, không tin data-* của nút)
const hcDangGui = new Set(); // ma đang gửi hoàn tác/bật lại — chống bấm đúp, kể cả sau khi vẽ lại
const hcChuaRo = new Set(); // ma đã gửi mà chưa chắc kết quả (mạng/502/504) — giữ khoá tới lần tải báo cáo thành công
let hcPhienTrang = -1; // phienCT của trang #/hoc đang hiện (hcRender đặt) — POST xong thì vẽ lại ĐÚNG trang này nếu nó còn hiện

function hcKhoaNut(ma, khoa) {
  document.querySelectorAll("#hc [data-hc-ma]").forEach((n) => { if (n.dataset.hcMa === ma) n.disabled = khoa; });
}

// Trang #/hoc (khung.js mnRoute gọi, đã kiểm chủ kho + đánh số phiên).
async function hcRender(phien) {
  hcPhienTrang = phien;
  $("#app").innerHTML = `<div class="hn" id="hc">
      <div class="row hn-dau"><h1 class="hn-h1">📈 Học tự động</h1><button type="button" class="btn ghost sm" id="hc-tai-lai">↻ Tải lại</button></div>
      <p class="small"><a href="#/">← Hôm nay</a></p>
      <div id="hc-nd"><p class="muted">Đang tải…</p></div>
    </div>`;
  $("#hc").addEventListener("click", (e) => {
    const b = e.target.closest("[data-hc-act]");
    if (b) { hcBam(b); return; }
    if (e.target.closest("#hc-tai-lai")) hcTai(phien, true);
  });
  await hcTai(phien, false);
}

// Tải báo cáo rồi vẽ #hc-nd. tuTay: bấm "Tải lại" (nút đang khoá thì bỏ).
async function hcTai(phien, tuTay) {
  const nut = $("#hc-tai-lai");
  if (tuTay && nut && nut.disabled) return;
  const luot = ++hcLuot;
  if (nut) nut.disabled = true; // khoá TRƯỚC await
  let bc = null, loi = null;
  try { bc = await api("hoc/bao-cao"); } catch (err) { loi = err; }
  if (phien !== phienCT || luot !== hcLuot) return; // đã sang trang khác / có lượt tải mới hơn: không vẽ đè
  const nd = $("#hc-nd");
  if (nd) {
    if (loi) nd.innerHTML = `<p class="hn-bao">${esc(hcCauLoiTai(loi))}</p>`;
    else {
      hcChuaRo.clear(); // đã có trạng thái thật từ máy nhà
      hcBai = new Map([...hcMang(bc.hieu_luc), ...hcMang(bc.ung_vien), ...hcMang(bc.da_tat)]
        .filter((b) => typeof b.ma === "string" && HC_RE_MA.test(b.ma)).map((b) => [b.ma, b]));
      nd.innerHTML = hcTrangHtml(bc, Date.now(), laChu());
      // bài đang gửi (bấm trước lúc vẽ lại) → nút mới vẽ vẫn khoá
      nd.querySelectorAll("[data-hc-ma]").forEach((n) => { if (hcDangGui.has(n.dataset.hcMa)) n.disabled = true; });
    }
  }
  const n2 = $("#hc-tai-lai");
  if (n2) n2.disabled = false;
}

// Nút Hoàn tác / Bật lại: kiểm mã + quyền + cờ của dữ liệu đang hiện → confirm → khoá TRƯỚC await → gửi → toast → vẽ lại.
async function hcBam(b) {
  const act = b && b.dataset ? b.dataset.hcAct : "";
  const ma = b && b.dataset ? b.dataset.hcMa : "";
  if (!b || b.disabled || (act !== "hoan-tac" && act !== "bat-lai") || typeof ma !== "string" || !HC_RE_MA.test(ma)) return;
  if (!laChu() || hcDangGui.has(ma) || hcChuaRo.has(ma)) return;
  const bh = hcBai.get(ma);
  if (!bh || (act === "hoan-tac" ? bh.co_the_hoan_tac !== true : bh.co_the_bat_lai !== true)) {
    toast("Gợi ý này vừa đổi trạng thái — bấm Tải lại để xem."); return;
  }
  if (!confirm(hcCauXacNhan(act, bh))) return;
  hcDangGui.add(ma); // khoá TRƯỚC await
  hcKhoaNut(ma, true);
  let veLai = true, moKhoa = false;
  try {
    const r = await api(`hoc/bai-hoc/${ma}/${act}`, {}); // Worker tự dựng body {"boi": <user>}, bỏ body trình duyệt
    if (r.status === 409) {
      // 409: câu cố định của máy nhà (hoc_danh_muc) — toast dùng textContent
      const cau = hcChu(r.loi, 160).replace(HC_KY_DIEU_KHIEN, " ");
      toast(`⚠ Chưa ${act === "hoan-tac" ? "hoàn tác" : "bật lại"} được: ${cau || "gợi ý vừa đổi trạng thái"} — đã tải lại để bạn xem.`);
    } else toast(act === "hoan-tac" ? "✓ Đã hoàn tác gợi ý." : "✓ Đã bật lại gợi ý.");
  } catch (err) {
    // P3-5: phân biệt theo chặng trả lỗi (hcLoaiLoi). "chưa làm gì" chỉ khi chắc request không tới kho_hoc.
    const l = hcLoaiLoi(err);
    if (l === "dang_nhap") { veLai = false; moKhoa = true; toast("Hết phiên đăng nhập — đăng nhập lại rồi bấm lại."); } // app.js đã mở hộp đăng nhập
    else if (l === "khong_bai") toast("Không còn gợi ý này trên máy nhà — đã tải lại.");
    else if (l === "quyen") { veLai = false; toast("Tài khoản này không làm được thao tác này."); }
    else if (l === "chua_ho_tro" || l === "chua_co_lan") { veLai = false; moKhoa = true; toast(`${HC_CAU_CHUA_HO_TRO} — chưa làm gì.`); }
    else if (l === "chua_bat") { veLai = false; moKhoa = true; toast("Học tự động chưa bật trên máy nhà — chưa làm gì."); }
    else if (l === "cau_hinh") { veLai = false; moKhoa = true; toast(`${HC_CAU_CAU_HINH} — chưa làm gì.`); }
    else if (l === "tu_choi") { veLai = false; moKhoa = true; toast("⚠ Máy chủ không nhận thao tác này — bấm Tải lại rồi thử lại."); }
    else { veLai = false; hcChuaRo.add(ma); toast("Chưa chắc đã xong — bấm Tải lại để xem trạng thái thật."); } // mạng / 502 / 504 / 503 lạ
  } finally {
    hcDangGui.delete(ma); // luôn dọn, kể cả khi đã sang trang khác
  }
  if (moKhoa) hcKhoaNut(ma, false); // nút của trang #/hoc ĐANG hiện (kể cả trang mở lại sau khi bấm)
  if (veLai) await hcVeLaiSauGhi();
}

// Sau Hoàn tác/Bật lại (P3-6): vẽ lại trang ĐANG hiện ở phiên HIỆN HÀNH (không phải phiên lúc bấm):
//  - trang #/hoc (kể cả vừa rời rồi quay lại) → tải lại báo cáo, vẽ lại (nút mở khoá);
//  - trang Hôm nay có khối "📈 Học hôm nay" → chỉ thay khối đó, không đụng phần còn lại của trang;
//  - trang khác → không làm gì. Kiểm lại phiên + khối còn trong DOM SAU await.
async function hcVeLaiSauGhi() {
  const p = phienCT;
  if (hcPhienTrang === p && $("#hc")) { await hcTai(p, false); return; }
  const k = $("#hn .hn-hoc");
  if (!k) return;
  let bc;
  try { bc = await api("hoc/bao-cao"); } catch (err) { return; } // khối giữ số cũ; lần mở trang Hôm nay sau sẽ tải mới
  if (p !== phienCT || !k.isConnected) return;
  const h = hcKhoiHomNayHtml(bc, Date.now());
  if (h) k.outerHTML = h;
}
