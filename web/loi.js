// Từ điển lời thường (W-7): đổi mã kỹ thuật (loại việc, trạng thái, chặng) thành câu tiếng Việt cho người không chuyên.
// Dùng chung cho trang Hôm nay (homnay.js) và trang SP (app.js). Script thường, cùng phạm vi toàn cục với app.js/viec.js.
// Không đổi các hằng số cũ (TEN_LOAI_VIEC, TT_VIEC, NHAN, BUOC_DS) — chỉ thêm lớp lời thường bên cạnh.
// CSP script-src 'self': KHÔNG script inline, KHÔNG thuộc tính on…= — sự kiện gắn bằng addEventListener.
"use strict";

// --- loi-thuan start ---
// Hàm thuần: không đụng DOM/fetch; chỉ dùng `esc` (app.js) lúc gọi. Test nạp khối này bằng node.
const coKhoaLoi = (o, k) => !!o && typeof k === "string" && Object.prototype.hasOwnProperty.call(o, k);

// Loại việc → việc máy nhà làm, nói bằng lời thường.
const LOI_LOAI_VIEC = {
  radar_ban_tin: "Làm bản tin sản phẩm đang lên",
  phan_tich_uid: "Phân tích sản phẩm và soạn bộ cảnh quay",
  douyin_uid: "Tìm video mẫu bên Douyin",
  xu_ly_link_moi: "Xử lý các link vừa dán",
  poster_day_folder: "Đưa video sang app đăng",
  voice_pv: "Đọc lời cho video (PerfectVoice)",
  muse_clip: "Làm cảnh minh hoạ bằng AI",
  voice_genmax: "Đọc lời bằng giọng AI",
  poster_len_lich: "Lên lịch đăng video",
  taovideo: "Làm video (2 mẻ)",
  sua_video: "Sửa lại một video",
  hoan_tac_sua: "Hoàn tác bản sửa video",
  poster_bo_loai: "Gỡ video bị Loại khỏi folder đăng",
};
function loiLoaiViec(loai) {
  return coKhoaLoi(LOI_LOAI_VIEC, loai) ? LOI_LOAI_VIEC[loai] : "Việc trên máy nhà";
}

// Trạng thái việc → lời thường.
const LOI_TT_VIEC = {
  cho: "Đang xếp hàng chờ máy", dang_chay: "Máy đang làm", can_tra_loi: "Máy đang hỏi bạn",
  cho_duyet: "Chờ bạn duyệt", xong: "Đã xong", loi: "Có trục trặc", huy: "Đã huỷ",
};
function loiTrangThaiViec(tt) {
  return coKhoaLoi(LOI_TT_VIEC, tt) ? LOI_TT_VIEC[tt] : "Không rõ";
}

// 4 chặng của một sản phẩm (gộp 8 bước chi tiết).
const CHANG_SP = ["Chuẩn bị", "Quay", "Làm video", "Chấm và đăng"];
const CHANG_THEO_TT = { cho: 0, da_phan_tich: 1, da_quay: 2, da_lam_video: 3 };
function changTheoTrangThai(tt) {
  return coKhoaLoi(CHANG_THEO_TT, tt) ? CHANG_THEO_TT[tt] : 0;
}
// Bước hiện tại của tinhBuoc/buocHienTai (1–8, 0 = hoàn tất) → chặng.
function changTheoBuoc(ht) {
  if (ht === 3) return 1;
  if (ht >= 4 && ht <= 6) return 2;
  if (ht === 7 || ht === 8 || ht === 0) return 3;
  return 0;
}
// Dải 4 chặng. Chặng trước chặng hiện tại = "đã qua" (suy từ trang_thai đã ghi), KHÔNG tô "xong" chặng hiện tại/sau.
function changHtml(idx) {
  const k = Number.isInteger(idx) && idx >= 0 && idx < CHANG_SP.length ? idx : 0;
  return `<ol class="chang">${CHANG_SP.map((t, i) => i === k
    ? `<li class="ch ch-hien-tai" aria-current="step">${esc(t)}</li>`
    : `<li class="ch ${i < k ? "ch-qua" : "ch-sau"}">${esc(t)}</li>`).join("")}</ol>`;
}

// Chặng dạng chữ thường cho dòng SP trang Hôm nay: "Bước 2/4 · Quay" (không vẽ ô, để không giống nút bấm).
function changChu(idx) {
  const k = Number.isInteger(idx) && idx >= 0 && idx < CHANG_SP.length ? idx : 0;
  return `Bước ${k + 1}/${CHANG_SP.length} · ${CHANG_SP[k]}`;
}

// Trạng thái sản phẩm (trang_thai trong danh sách) → câu + nhãn nút việc tiếp theo.
const LOI_TT_SP = {
  cho: { cau: "Máy nhà chưa phân tích — chờ bộ cảnh quay", nut: "Xem sản phẩm" },
  da_phan_tich: { cau: "Đã có bộ cảnh quay — đến lượt bạn quay", nut: "Xem cần quay gì" },
  da_quay: { cau: "Đã quay — có thể làm video", nut: "Làm video" },
  da_lam_video: { cau: "Đã có video — chấm rồi đăng", nut: "Chấm và đăng" },
};
function loiTrangThaiSp(tt) {
  return coKhoaLoi(LOI_TT_SP, tt) ? LOI_TT_SP[tt] : LOI_TT_SP.cho;
}

// Việc tốn tiền đang hỏi mà KHÔNG có phiên sống: web không trả lời được, chỉ xin duyệt lại / huỷ (D9, FX-13).
// Dùng đúng cờ của viec.js: nutHanhDong(v).anTraLoi (cùng điều kiện nutTraLoi(…, laTonTien, phienSong) trả rỗng).
function canDuyetLaiViec(v) {
  if (!v || typeof v !== "object" || v.trang_thai !== "can_tra_loi" || typeof nutHanhDong !== "function") return false;
  return nutHanhDong(v).anTraLoi === true;
}

// Câu "việc tay" kỹ thuật của máy nhà → lời thường + việc cần làm (CHƯA esc). Khớp theo đầu câu runner sinh.
// Không nhận ra → giữ nguyên nội dung gốc (đã trim, cắt 160 ký tự), nhanRa = false để nơi gọi giữ cách nói cũ.
// tools/runner/vong_lap.py (~223-229): runner CHỈ hỏi khi `git status --porcelain -- data` VẪN bẩn (git bận thì tự chờ).
// Mẫu: "Dữ liệu kho có thay đổi chưa đẩy: <f1>, <f2>, … (tối đa 10)[ (+N)]". Kho còn bẩn mà bấm Thử lại → hỏi lại đúng câu này,
// nên câu lời thường KHÔNG hứa tự xong: nói rõ phải lưu/bỏ thay đổi trên máy nhà trước.
const DAU_KHO_BAN = "Dữ liệu kho có thay đổi chưa đẩy";
function cauKhoBan(duoi) {
  let s = String(duoi).replace(/^\s*:\s*/, "");
  let them = 0;
  const m = s.match(/\s*\(\+(\d+)\)$/);
  if (m) { them = Number(m[1]); s = s.slice(0, m.index); }
  const ds = s.split(", ").map((t) => t.trim()).filter(Boolean);
  const khac = Math.max(0, ds.length - 1) + them;
  const dau = ds.length ? ds[0].slice(0, 120) : "";
  const tep = dau ? ` (${dau}${khac ? ` và ${khac} file khác` : ""})` : "";
  return `Máy nhà có dữ liệu kho chưa lưu lên mạng${tep}. Cần lưu hoặc bỏ thay đổi đó trên máy nhà rồi bấm Thử lại.`;
}
function loiViecTay(noiDung) {
  const nd = typeof noiDung === "string" ? noiDung.trim() : "";
  if (nd.startsWith(DAU_KHO_BAN)) return { cau: cauKhoBan(nd.slice(DAU_KHO_BAN.length)), nhanRa: true };
  return { cau: nd.slice(0, 160), nhanRa: false };
}

// Câu mô tả 1 việc (CHƯA esc — nơi gọi esc).
function cauViec(v) {
  const x = v && typeof v === "object" ? v : {};
  const ten = loiLoaiViec(x.loai);
  let ch = x.cau_hoi;
  if (typeof ch === "string") { try { ch = JSON.parse(ch); } catch { ch = null; } }
  const nd = ch && typeof ch === "object" && typeof ch.noi_dung === "string" ? ch.noi_dung.trim().slice(0, 160) : "";
  if (x.trang_thai === "can_tra_loi") {
    if (canDuyetLaiViec(x)) return `Cần duyệt lại để chạy tiếp: ${ten}`;
    if (ch && ch.loai === "viec_tay") {
      const l = loiViecTay(ch.noi_dung);
      if (l.nhanRa) return l.cau;
      // Hôm nay có nút "Thử lại" tại chỗ (viecTayHn, homnay.js) → câu runner "…bấm Đã làm xong" đổi cho khớp nhãn nút.
      const coNutThuLai = typeof viecTayHn === "function" && viecTayHn(x);
      const ndHien = coNutThuLai ? nd.replace(/Đã làm xong/g, "Thử lại") : nd;
      return ndHien ? `Cần bạn làm tay: ${ndHien}` : `Cần bạn làm tay một bước của "${ten}"`;
    }
    return nd ? `Máy hỏi: ${nd}` : `Máy đang chờ bạn trả lời ("${ten}")`;
  }
  if (x.trang_thai === "cho_duyet") return `Cần bạn duyệt trước khi chạy (tốn tiền): ${ten}`;
  if (x.trang_thai === "dang_chay") return ten;
  if (x.trang_thai === "cho") return `${ten} — đang xếp hàng`;
  if (x.trang_thai === "loi") return `${ten} — có trục trặc`;
  if (x.trang_thai === "xong") return `${ten} — xong`;
  return `${ten} — ${loiTrangThaiViec(x.trang_thai).toLowerCase()}`;
}
function nutViec(v) {
  const tt = v && v.trang_thai;
  if (tt === "can_tra_loi") return canDuyetLaiViec(v) ? "Xem và duyệt lại" : "Trả lời";
  return tt === "cho_duyet" ? "Xem và duyệt" : "Xem";
}

// Thời gian đã chạy từ mốc ISO (có múi giờ) tới nowMs → "đã chạy 25 phút". Sai → "".
function thoiGianChay(batDau, nowMs) {
  const t = typeof batDau === "string" ? Date.parse(batDau) : NaN;
  if (!Number.isFinite(t) || !Number.isFinite(nowMs)) return "";
  const phut = Math.floor(Math.max(0, nowMs - t) / 60000);
  if (phut < 1) return "vừa bắt đầu";
  if (phut < 60) return `đã chạy ${phut} phút`;
  const g = Math.floor(phut / 60), p = phut % 60;
  return `đã chạy ${g} giờ${p ? ` ${p} phút` : ""}`;
}

// /api/suc-khoe → {cau, tat}. Không trả lời / lỗi → "đang tắt".
function loiSucKhoe(d) {
  if (!d || typeof d !== "object" || !d.may_nha) return { cau: "Máy nhà đang tắt — việc sẽ chờ", tat: true };
  const apps = Array.isArray(d.apps) ? d.apps : [];
  const tat = apps.filter((a) => a && typeof a === "object" && !a.song).map((a) => String(a.ten || a.ma || "?").slice(0, 40));
  return { cau: ["Máy nhà: đang chạy", ...tat.map((t) => `${t} đang tắt`)].join(" · "), tat: false };
}

// Khối "Bước tiếp theo" của trang SP. ht: buocHienTai (null = chưa biết, dùng trang_thai); chu: chủ kho (có việc máy nhà).
// nut.lam: "tab:<tab>" (mở tab trên trang), "viec:<loai>" (bấm nút việc có sẵn trong khối việc), "khoi:viec" (cuộn tới khối việc),
// "trang:poster" (sang trang Poster V2). phu: nút phụ (cùng dạng nut), có thể không có.
const BUOC_TIEP_TT = {
  cho: { cau: "Máy nhà đang chuẩn bị bộ cảnh quay — chờ một chút rồi quay lại.", nut: { nhan: "Xem tóm tắt sản phẩm", lam: "tab:tt" } },
  da_phan_tich: { cau: "Đến lượt quay theo bộ cảnh quay. Quay xong gạt \"Đã quay\".", nut: { nhan: "Xem cần quay gì", lam: "tab:canh" } },
  da_quay: { cau: "Đã quay — bước tiếp theo là làm video.", nut: { nhan: "Xem thông tin làm video", lam: "tab:video" } },
  da_lam_video: { cau: "Đã có video (duyệt lúc tạo) — đăng qua Poster V2.", nut: { nhan: "Xem caption", lam: "tab:cap" } },
};
// Nút "viec:<loai>" khi chính loại đó KHÔNG có trong khối việc (goiYViec): đổi sang loại khác có sẵn với câu/nhãn khớp.
const BUOC_TIEP_VIEC = {
  phan_tich_uid: { cau: "Cần bộ cảnh quay: giao máy nhà phân tích sản phẩm.", nhan: "Giao máy phân tích" },
  muse_clip: { cau: "Tạo clip minh hoạ bằng AI (tuỳ chọn).", nhan: "Tạo clip minh hoạ" },
  voice_pv: { cau: "Đọc lời bằng giọng AI (PerfectVoice).", nhan: "Đọc lời bằng giọng AI" },
  voice_genmax: { cau: "Đọc lời bằng giọng AI (GenMax).", nhan: "Đọc lời bằng giọng AI" },
  taovideo: { cau: "Đã quay — cho máy nhà làm video.", nhan: "Làm video" },
  poster_day_folder: { cau: "Đưa video sang app đăng.", nhan: "Đưa sang app đăng" },
  poster_len_lich: { cau: "Lên lịch đăng video.", nhan: "Lên lịch đăng" },
};
const VIEC_PHU_BT = ["douyin_uid"]; // goiYViec thêm làm nút phụ — không dùng làm nút chính
// coSan: danh sách loại goiYViec(ht, …) đang trả (undefined = không kiểm, giữ như cũ).
function chinhNutViecBt(b, coSan) {
  if (!Array.isArray(coSan) || !b.nut || !b.nut.lam.startsWith("viec:")) return b;
  if (coSan.includes(b.nut.lam.slice(5))) return b;
  const loai = coSan.find((l) => typeof l === "string" && !VIEC_PHU_BT.includes(l) && coKhoaLoi(BUOC_TIEP_VIEC, l));
  if (!loai) return { ...b, cau: "Máy nhà chưa sẵn sàng cho bước này — xem khối việc bên dưới.", nut: { nhan: "Xem việc máy nhà", lam: "khoi:viec" } };
  return { ...b, cau: BUOC_TIEP_VIEC[loai].cau, nut: { nhan: BUOC_TIEP_VIEC[loai].nhan, lam: `viec:${loai}` } };
}
function buocTiepTheo(ht, tt, chu, coSan) {
  if (!chu || !Number.isInteger(ht) || ht < 0 || ht > 8) {
    const b = coKhoaLoi(BUOC_TIEP_TT, tt) ? BUOC_TIEP_TT[tt] : BUOC_TIEP_TT.cho;
    return { chang: changTheoTrangThai(tt), cau: b.cau, nut: { ...b.nut } };
  }
  return chinhNutViecBt(buocTiepChu(ht), coSan);
}
function buocTiepChu(ht) {
  const chang = changTheoBuoc(ht);
  if (ht === 0) return { chang, cau: "Đã xong các bước. Có thể xem lại caption.", nut: { nhan: "Xem caption", lam: "tab:cap" } };
  if (ht <= 2) return { chang, cau: "Cần bộ cảnh quay: giao máy nhà phân tích sản phẩm.", nut: { nhan: "Giao máy phân tích", lam: "viec:phan_tich_uid" } };
  if (ht === 3) return { chang, cau: "Đến lượt bạn quay theo bộ cảnh quay. Quay xong gạt \"Đã quay\".", nut: { nhan: "Xem cần quay gì", lam: "tab:canh" } };
  if (ht <= 6) return { chang, cau: "Đã quay — cho máy nhà làm video.", nut: { nhan: "Làm video", lam: "viec:taovideo" } };
  // 2026-11-19: bỏ trang Duyệt video + Đăng bài — video duyệt lúc tạo, đăng/lên lịch ở Poster V2.
  return { chang, cau: "Video đã duyệt lúc tạo, đến lượt lên lịch đăng ở Poster V2.", nut: { nhan: "Mở Poster V2", lam: "trang:poster" } };
}
function buocTiepHtml(b, ghiChu) {
  const x = b && typeof b === "object" ? b : buocTiepTheo(null, "cho", false);
  return `<div class="bt-dau"><b>Bước tiếp theo</b></div>
    ${changHtml(x.chang)}
    <p class="bt-cau"><b>Việc nên làm bây giờ:</b> ${esc(x.cau)}</p>
    ${ghiChu ? `<p class="small muted">${esc(ghiChu)}</p>` : ""}
    <div class="row bt-nut">${x.nut ? `<button type="button" class="btn" data-bt-lam="${esc(x.nut.lam)}">${esc(x.nut.nhan)}</button>` : ""}${x.phu && x.phu.lam
      ? `<button type="button" class="btn ghost" data-bt-phu="${esc(x.phu.lam)}">${esc(x.phu.nhan)}</button>` : ""}<a class="btn ghost" href="#/">Để sau</a></div>`;
}
// --- loi-thuan end ---
