// Bộ chạy việc trên web Kho (docs/bo-chay-viec.md §12, đợt 3: trả lời CHỈ bằng nút).
// Dùng chung với app.js (script thường, cùng phạm vi toàn cục): $, esc, api, toast, laChu, gioS, phienCT, buocHienTai.
// CSP script-src 'self': KHÔNG script inline, KHÔNG thuộc tính on…= — mọi sự kiện gắn bằng addEventListener.
"use strict";

// --- viec-thuan start ---
// Hàm thuần: không đụng DOM, fetch hay biến toàn cục nào ngoài `esc` (test nạp khối này bằng node, tiêm esc của app.js).
const TEN_LOAI_VIEC = {
  radar_ban_tin: "📡 Bản tin radar", phan_tich_uid: "Phân tích SP (bộ cảnh quay)", douyin_uid: "Tìm video Douyin",
  xu_ly_link_moi: "📥 Xử lý link mới", poster_day_folder: "Đẩy folder lên Poster", voice_pv: "Voice PerfectVoice",
  muse_clip: "B-roll AI (Muse)", voice_genmax: "Voice GenMax", poster_len_lich: "Lên lịch Poster", taovideo: "Dựng 2 mẻ video",
  poster_bo_loai: "Gỡ video bị Loại khỏi folder đăng",
};
// Đợt mở của từng loại + tham số web phải chọn (uid lấy từ SP; du_an/me chọn từ /api/viec/du-an/<uid>).
const LOAI_VIEC_SP = {
  phan_tich_uid: { dot: 3, can: ["uid"] }, douyin_uid: { dot: 3, can: ["uid"] },
  voice_pv: { dot: 3, can: ["uid", "du_an", "me"] }, poster_day_folder: { dot: 3, can: ["uid", "du_an"] },
  muse_clip: { dot: 4, can: ["uid", "du_an"] }, voice_genmax: { dot: 4, can: ["uid", "du_an", "me"] },
  poster_len_lich: { dot: 4, can: [] }, taovideo: { dot: 5, can: ["uid", "du_an_a", "du_an_b", "wm"] },
  poster_bo_loai: { dot: 3, can: ["uid"] }, // B-L1: từng bấm ở trang Đăng bài (đã gỡ 2026-11-19); goiYViec không tự thêm
};
const TT_VIEC = {
  cho: "Đang chờ", dang_chay: "Đang chạy", can_tra_loi: "Cần bạn", cho_duyet: "Chờ duyệt",
  xong: "Xong", loi: "Lỗi", huy: "Đã huỷ",
};
const TT_MO = ["cho", "dang_chay", "can_tra_loi", "cho_duyet"];
// Phân trang #/viec (FX-28): mỗi nhóm tự gọi API riêng theo trang_thai, cố định 10 dòng/trang (§12).
const TRANG_VIEC_SO_DONG = 10;
const NHOM_VIEC = [
  { k: "can_ban", ten: "👉 Cần bạn", tt: "can_tra_loi,cho_duyet" },
  { k: "dang_chay", ten: "⏳ Đang chạy", tt: "dang_chay" },
  { k: "dang_cho", ten: "🕒 Đang chờ", tt: "cho" },
  { k: "gan_day", ten: "🗂 Gần đây", tt: "xong,loi,huy" },
];
// Trạng thái ở nhóm "Gần đây" (đã kết thúc) — chỉ các việc này mới có nút "🗃 Ẩn" (luu-tru).
const TT_DA_KET_THUC = ["xong", "loi", "huy"];
const RE_ID_VIEC = /^j\d{14}[a-z0-9]{4}$/;
const RE_UID_VIEC = /^\d{19}$/;
const RE_DIEU_KHIEN = /[\u0000-\u001f\u007f]/;
const TRA_LOI_TOI_DA_WEB = 120; // khớp Worker (TRA_LOI_TOI_DA)

const laIdViec = (id) => typeof id === "string" && RE_ID_VIEC.test(id);
const tenLoaiViec = (loai) => TEN_LOAI_VIEC[loai] || String(loai ?? "?");
const gioViec = (s) => (typeof s === "string" ? s.slice(0, 16).replace("T", " ") : "");
const docJsonViec = (x) => {
  if (typeof x !== "string") return x ?? null;
  try { return JSON.parse(x); } catch { return null; }
};

// Trạng thái → {nhan, lop} (lop dùng làm class CSS, luôn nằm trong tập cố định).
function nhanTrangThai(tt) {
  return Object.prototype.hasOwnProperty.call(TT_VIEC, tt) ? { nhan: TT_VIEC[tt], lop: `tt-${tt}` } : { nhan: String(tt ?? "?"), lop: "tt-khac" };
}

// Chia danh sách việc thành 4 nhóm màn hình #/viec. can_ban = nhóm "Cần bạn" (không phải trường can_ban của việc).
function nhomViec(ds) {
  const g = { can_ban: [], dang_chay: [], dang_cho: [], gan_day: [] };
  for (const v of Array.isArray(ds) ? ds : []) {
    if (!v || typeof v !== "object") continue;
    const tt = v.trang_thai;
    if (tt === "can_tra_loi" || tt === "cho_duyet") g.can_ban.push(v);
    else if (tt === "dang_chay") g.dang_chay.push(v);
    else if (tt === "cho") g.dang_cho.push(v);
    else g.gan_day.push(v);
  }
  const tang = (k) => (a, b) => String(a[k] || "").localeCompare(String(b[k] || ""));
  g.can_ban.sort(tang("cap_nhat_luc")); g.dang_chay.sort(tang("bat_dau_luc")); g.dang_cho.sort(tang("tao_luc"));
  g.gan_day.sort((a, b) => tang("cap_nhat_luc")(b, a));
  return g;
}

// Cách trả lời câu hỏi đang chờ → {nut:[{nhan, gia_tri}], o_chu, can_mat_khau} (W-6, §7.6).
// - Việc tốn tiền KHÔNG có phiên sống: không trả lời trên web (FX-12/13 — chỉ Xin duyệt lại / Huỷ).
// - Phiên sống (phienSong === true): chon + cau_hoi (ô chữ) cần mật khẩu; viec_tay/khong_ro chỉ nút.
// - Việc thường: nút như đợt 3, không mật khẩu; cau_hoi chỉ trả lời được khi có phiên sống.
// dotBat giữ trong chữ ký: phien_song chỉ có từ đợt 5 nên cờ đó đủ để mở ô chữ.
function nutTraLoi(cauHoi, dotBat, laTonTien = false, phienSong = false) {
  const rong = { nut: [], o_chu: false, can_mat_khau: false };
  const song = phienSong === true;
  void dotBat;
  const c = docJsonViec(cauHoi);
  if (!c || typeof c !== "object" || Array.isArray(c)) return rong;
  if (laTonTien && !song) return rong;
  if (c.loai === "chon") {
    const da = new Set();
    const nut = (Array.isArray(c.lua_chon) ? c.lua_chon : [])
      .filter((x) => typeof x === "string" && x.trim() && x.length <= TRA_LOI_TOI_DA_WEB && !RE_DIEU_KHIEN.test(x) && !da.has(x) && da.add(x))
      .slice(0, 6).map((x) => ({ nhan: x, gia_tri: x }));
    return { nut, o_chu: false, can_mat_khau: song && nut.length > 0 };
  }
  if (c.loai === "viec_tay") return { nut: [{ nhan: "✓ Tôi đã làm xong", gia_tri: "da_lam_xong" }], o_chu: false, can_mat_khau: false };
  if (c.loai === "khong_ro") return { nut: [{ nhan: "▶ Tiếp tục", gia_tri: "tiep_tuc" }], o_chu: false, can_mat_khau: false };
  if (c.loai === "cau_hoi" && song) return { nut: [], o_chu: true, can_mat_khau: true };
  return rong;
}

// Agent đang chờ việc nền (render/voice) — runner đặt can_ban (§7.3 hành động cho_nen). Không phải cảnh báo.
function dangChoNen(viec) {
  return !!viec && typeof viec === "object" && viec.trang_thai === "dang_chay" && typeof viec.can_ban === "string" && viec.can_ban.includes("việc nền");
}
// Log còn chạy: đang chạy, hoặc phiên sống đang hỏi (việc nền vẫn ghi log).
function logDangSong(viec) {
  return !!viec && typeof viec === "object"
    && (viec.trang_thai === "dang_chay" || (viec.trang_thai === "can_tra_loi" && viec.phien_song === true));
}

// Gợi ý nút "▶ Chạy" theo bước hiện tại (§12). info: SP + co_douyin (đã có tab Douyin hay chưa).
// Trả {nut:[{loai, nhan, can}], ghi_chu}.
function goiYViec(ht, info, dotBat) {
  const i = info || {};
  const dot = Number.isInteger(dotBat) ? dotBat : 3;
  if (!RE_UID_VIEC.test(String(i.uid || ""))) return { nut: [], ghi_chu: "Chưa có UID — chờ máy nhà tìm UID (nút 📥 Xử lý link mới ở trang ⚙ Việc)." };
  const coDouyin = !!(i.co_douyin || i.douyin);
  const ds = [];
  const them = (loai) => {
    const m = LOAI_VIEC_SP[loai];
    if (m && m.dot <= dot && !ds.some((x) => x.loai === loai)) ds.push({ loai, nhan: tenLoaiViec(loai), can: m.can.slice() });
  };
  const GHI_CHU = {
    0: "✓ Hoàn tất", 3: "👉 Việc của bạn: quay raw/takes (không chạy từ web được).",
    8: "👉 Lên lịch đăng ở Poster V2 (video đã duyệt lúc tạo).",
  };
  if (ht === 2) { them("phan_tich_uid"); if (i.da_phan_tich && !coDouyin) them("douyin_uid"); }
  // Đã quay (4–6): "Làm video" (taovideo tự làm voice + 2 mẻ + đẩy Poster) luôn đứng đầu; clip AI/voice lẻ chỉ là nút phụ tuỳ chọn.
  else if (ht >= 4 && ht <= 6) { them("taovideo"); if (ht === 4) them("muse_clip"); if (ht === 5) { them("voice_pv"); them("voice_genmax"); } }
  // ht 8: video duyệt lúc tạo, đăng ở Poster V2 (2026-11-19 gỡ trang Duyệt video + Đăng bài) — khối việc không còn nút poster_*.
  // Nút phụ: đã qua bước 2 mà chưa có Douyin.
  if ((ht === 0 || ht > 2) && !coDouyin) them("douyin_uid");
  let ghi_chu = GHI_CHU[ht] || "";
  if (!ghi_chu && ([4, 6].includes(ht)) && !ds.some((x) => x.loai !== "douyin_uid")) ghi_chu = "Bước này chưa có việc chạy được từ web ở đợt hiện tại.";
  return { nut: ds, ghi_chu };
}

// "uid 123… · du_an abc · me 20261117-a"
function dongThamSo(ts) {
  const t = docJsonViec(ts);
  if (!t || typeof t !== "object") return "";
  return Object.keys(t).sort().map((k) => `${k} ${Array.isArray(t[k]) ? t[k].join(",") : String(t[k])}`).join(" · ");
}

// Nút hành động trên thẻ (FX-28, §12): dang_chay → "⏹ Dừng" (gọi act huy, có sẵn); đã kết thúc (nhóm Gần đây) →
// "🗃 Ẩn" (gọi act luu-tru, mới). Nằm TRONG thẻ <a class="vt"> (giữ CSS/layout cũ) — handler ở renderViec() chặn
// nổi bọt (preventDefault + stopPropagation) trước khi click chạy tới <a>, nên không điều hướng khi bấm nút.
function theVtActHtml(id, tt) {
  if (!id) return "";
  const act = tt === "dang_chay" ? "huy" : TT_DA_KET_THUC.includes(tt) ? "luu-tru" : "";
  if (!act) return "";
  const nhan = act === "huy" ? "⏹ Dừng" : "🗃 Ẩn";
  return `<div class="row vt-act"><button type="button" class="btn ghost sm" data-vt-act="${act}" data-vt-id="${esc(id)}">${nhan}</button></div>`;
}
function theViecHtml(v) {
  const x = v || {};
  const tt = nhanTrangThai(x.trang_thai);
  const id = laIdViec(x.id) ? x.id : "";
  const ts = dongThamSo(x.tham_so);
  const ch = docJsonViec(x.cau_hoi);
  const goiY = x.trang_thai === "can_tra_loi" && ch && ch.noi_dung ? `<div class="small vt-hoi">❓ ${esc(String(ch.noi_dung).slice(0, 160))}</div>` : "";
  const banner = !x.can_ban ? "" : dangChoNen(x) ? `<div class="small vt-cho-nen">⏳ ${esc(x.can_ban)}</div>` : `<div class="small vt-can-ban">⚠ ${esc(x.can_ban)}</div>`;
  const inner = `<div class="vt-dong1"><span class="tt ${tt.lop}">${esc(tt.nhan)}</span> <b>${esc(tenLoaiViec(x.loai))}</b></div>
      ${ts ? `<div class="small muted vt-ts">${esc(ts)}</div>` : ""}${goiY}${banner}
      <div class="small muted">${esc(x.tao_boi || "?")} · ${esc(gioViec(x.tao_luc))}${x.lan_thu > 1 ? ` · lần ${esc(x.lan_thu)}` : ""}</div>${theVtActHtml(id, x.trang_thai)}`;
  return id ? `<a class="vt" href="#/viec/${esc(id)}">${inner}</a>` : `<div class="vt">${inner}</div>`;
}

// Số trang (cố định 10 dòng/trang, FX-28); tong không hợp lệ/≤0 → luôn ít nhất 1 trang.
function soTrangViec(tong) {
  const n = Number(tong);
  return Number.isFinite(n) && n > TRANG_VIEC_SO_DONG ? Math.ceil(n / TRANG_VIEC_SO_DONG) : 1;
}
// Nút chuyển trang dưới mỗi nhóm — khoá "‹ Trước"/"Sau ›" đúng dataset.vtTrang để handler cộng/trừ 1 trang.
function trangNhomHtml(k, trang, soTrang) {
  const t = Number.isInteger(trang) && trang > 0 ? trang : 1;
  const s = Number.isInteger(soTrang) && soTrang > 0 ? soTrang : 1;
  return `<div class="row small vt-trang">
      <button type="button" class="btn ghost sm" data-vt-trang="${k}:-1"${t <= 1 ? " disabled" : ""}>‹ Trước</button>
      <span class="muted">Trang ${t}/${s}</span>
      <button type="button" class="btn ghost sm" data-vt-trang="${k}:1"${t >= s ? " disabled" : ""}>Sau ›</button>
    </div>`;
}
// g: {can_ban:[...], ...} (mỗi nhóm là việc của ĐÚNG trang hiện tại, đã lọc trang_thai từ API riêng).
// trangs (tuỳ chọn): {can_ban: {trang, tong}, ...} — tong = tổng số việc khớp bộ lọc (không phải list.length);
// thiếu trangs[k] → coi tong = g[k].length (không có điều hướng trang, giữ hành vi cũ khi gọi F.dsNhomHtml(g)).
function dsNhomHtml(g, trangs = {}) {
  const html = NHOM_VIEC.filter(({ k }) => (g[k] && g[k].length) || (trangs[k] && trangs[k].tong > 0))
    .map(({ k, ten }) => {
      const tr = trangs[k] || {};
      const tong = Number.isInteger(tr.tong) ? tr.tong : (g[k] ? g[k].length : 0);
      const trang = Number.isInteger(tr.trang) && tr.trang > 0 ? tr.trang : 1;
      const nav = tong > TRANG_VIEC_SO_DONG ? trangNhomHtml(k, trang, soTrangViec(tong)) : "";
      return `<h3 class="vt-nhom">${ten} <span class="small muted">(${tong})</span></h3><div class="vt-ds">${(g[k] || []).map(theViecHtml).join("")}</div>${nav}`;
    }).join("");
  return html || `<p class="muted center">Chưa có việc nào.</p>`;
}

// Làn: chuỗi id việc, hoặc object {id, loai} (runner mới); object không có id lẫn loai = rảnh.
const moTaLan = (x) => {
  if (!x) return "rảnh";
  const laObj = typeof x === "object";
  if (laObj && !x.id && !x.loai) return "rảnh";
  const id = typeof x === "string" ? x : laObj ? x.id : "";
  const loai = laObj && x.loai ? " · " + esc(tenLoaiViec(x.loai)) : "";
  return laIdViec(id) ? `<a href="#/viec/${esc(id)}">bận${loai}</a>` : `bận${loai}`;
};
const soViec = (x, le = 0) => { const n = Number(x); return Number.isFinite(n) ? n.toFixed(le) : "?"; };

// Dải tóm tắt từ /api/viec/suc-khoe.
function tomTatHtml(sk) {
  const s = sk || {};
  const hm = s.han_muc && typeof s.han_muc === "object" ? s.han_muc : {};
  const lan = s.lan && typeof s.lan === "object" ? s.lan : {};
  const tn = s.tai_nguyen && typeof s.tai_nguyen === "object" ? s.tai_nguyen : {};
  const canhBao = Array.isArray(s.canh_bao) ? s.canh_bao : [];
  return `<div class="sk-banner ok">🟢 Bộ chạy việc: Sống${s.phien_ban ? ` <span class="small">· bản ${esc(s.phien_ban)}</span>` : ""}</div>
    <div class="vt-tom small">
      <span>GPU: ${moTaLan(lan.gpu)}</span><span>Nhẹ: ${moTaLan(lan.nhe)}</span><span>Kho: ${tn.kho ? "bận" : "rảnh"}</span>
      <span>Claude hôm nay: $${esc(soViec(s.chi_phi_hom_nay_usd, 2))}${hm.claude_usd_ngay != null ? ` / $${esc(soViec(hm.claude_usd_ngay))}` : ""}</span>
      <span>Việc Claude: ${esc(soViec(s.viec_claude_hom_nay))}${hm.claude_viec_ngay != null ? ` / ${esc(soViec(hm.claude_viec_ngay))}` : ""}</span>
    </div>
    ${s.tam_dung_claude_den ? `<div class="vj-can-ban">⏸ Tạm dừng Claude đến ${esc(gioViec(String(s.tam_dung_claude_den)))}</div>` : ""}
    ${canhBao.map((c) => `<div class="small vt-can-ban">⚠ ${esc(c)}</div>`).join("")}`;
}

// Huy hiệu ⚙ Việc = can_tra_loi + cho_duyet, lấy từ `dem` của GET /viec?tom_tat=1 (đếm toàn kho, không phải 50 việc).
function demCanBan(dem) {
  if (!dem || typeof dem !== "object" || Array.isArray(dem)) return 0;
  const so = (k) => { const n = Number(dem[k]); return Number.isInteger(n) && n > 0 ? n : 0; };
  return so("can_tra_loi") + so("cho_duyet");
}

// Id việc trùng trong phản hồi 409 (runner trả `trung` = việc đầy đủ; bản cũ có thể là chuỗi id). Sai mẫu → "".
function idTrungViec(r) {
  const t = r && r.trung;
  const id = typeof t === "string" ? t : t && typeof t === "object" ? t.id : "";
  return laIdViec(id) ? id : "";
}

const NHAN_XONG = { huy: "Đã huỷ", "tu-choi": "Đã từ chối", "chay-tiep": "▶ Đã cho chạy tiếp", "chay-lai": "↻ Đã tạo việc chạy lại", "tra-loi": "✓ Đã gửi trả lời", duyet: "✓ Đã duyệt — việc sẽ chạy trên máy nhà",
  "xin-duyet-lai": "↻ Đã xin duyệt lại — kiểm tham số rồi duyệt bằng mật khẩu",
  "nhan-tin": "✓ Đã gửi chỉ đạo — agent nhận khi xong bước đang làm",
  "luu-tru": "✓ Đã ẩn", "bo-luu-tru": "✓ Đã bỏ ẩn" };
// Phản hồi của POST /viec/<id>/<act> → {toast, chuyen (id việc cần mở, "" = ở lại), canhBao (giữ trên trang)}.
function ketQuaHanhDong(act, r, id) {
  const x = r || {};
  if (x.status === 409) {
    const trung = act === "chay-lai" ? idTrungViec(x) : "";
    if (trung && trung !== id) return { toast: "Đã có việc cùng loại đang mở — chuyển sang việc đó", chuyen: trung, canhBao: "" };
    return { toast: "⚠ " + (x.loi || "Việc đã đổi trạng thái — tải lại"), chuyen: "", canhBao: "" };
  }
  const canhBao = typeof x.canh_bao === "string" && x.canh_bao.trim() ? x.canh_bao.slice(0, 300) : "";
  const moi = x.viec && x.viec.id;
  return {
    toast: canhBao ? "⚠ " + canhBao : NHAN_XONG[act] || "✓ Đã gửi",
    chuyen: act === "chay-lai" && laIdViec(moi) && moi !== id ? moi : "",
    canhBao,
  };
}

// ---------- đợt 4 (§5.2, §9 mục 4): duyệt việc tốn tiền + form tạo ----------
const USER_DUYET = ["nhan", "comeofage"];
const LOAI_TON_TIEN = ["muse_clip", "voice_genmax", "poster_len_lich", "taovideo"]; // ton_tien=True ở tools/runner/danh_muc.py
const LOAI_CO_CLAUDE = ["muse_clip", "poster_len_lich", "taovideo"];                 // loại chạy bằng agent Claude
const LOI_DUYET_TOI_DA_WEB = 2000; // code point — khớp Worker LOI_DUYET_TOI_DA
// Mã mẫu Muse → nhãn. Mã + thứ tự phải trùng MA_MAU_MUSE (cf/src/worker.js) và TEN_MAU_MUSE (tools/runner/danh_muc.py).
const TEN_MAU_MUSE = {
  xoay_360: "Xoay 360° nền trơn", cam_tay: "Cầm tay xoay", can_canh: "Cận cảnh chất liệu",
  dung_that: "Dùng thật tại nhà", dat_ban: "Đặt lên bàn", mo_hop: "Mở hộp", truoc_sau: "Trước / sau",
};
const MUSE_THOI_LUONG_WEB = [10, 15];
const RE_DU_AN_VIEC = /^[0-9a-f]{12}$/;
// Surrogate lẻ (Worker từ chối). Không dùng regex lookbehind: Safari iOS < 16.4 không parse được → cả file chết.
const coSurrogateLe = (s) => {
  for (let k = 0; k < s.length; k++) {
    const c = s.charCodeAt(k);
    if (c >= 0xd800 && c <= 0xdbff) { const n = s.charCodeAt(k + 1); if (n >= 0xdc00 && n <= 0xdfff) { k++; continue; } return true; }
    if (c >= 0xdc00 && c <= 0xdfff) return true;
  }
  return false;
};
const coKhoa = (o, k) => !!o && typeof k === "string" && Object.prototype.hasOwnProperty.call(o, k);
const catKyTu = (s, n) => [...String(s)].slice(0, n).join("");
const thamSoObj = (x) => { const t = docJsonViec(x); return t && typeof t === "object" && !Array.isArray(t) ? t : {}; };
const tenMau = (m) => (coKhoa(TEN_MAU_MUSE, m) ? TEN_MAU_MUSE[m] : String(m));
const soNguyenWeb = (x) => (typeof x === "number" ? x : typeof x === "string" && /^\d{1,10}$/.test(x) ? Number(x) : NaN);

// Người này có được duyệt việc này trên web không: chỉ chủ kho, việc đang cho_duyet, loại tốn tiền.
function duocDuyet(viec, user) {
  return !!viec && typeof viec === "object" && USER_DUYET.includes(user)
    && viec.trang_thai === "cho_duyet" && LOAI_TON_TIEN.includes(viec.loai);
}

// D9: lời duyệt việc tốn tiền chỉ dùng 1 lần — việc đã chạy rồi lỗi/hỏi giữa chừng không "Chạy tiếp"/"Tiếp tục" được
// (runner trả 409 "cần duyệt lại") → ẩn 2 nút đó, hiện "Xin duyệt lại" (POST xin-duyet-lai → về cho_duyet).
// FX-13: đang can_tra_loi thì ẩn MỌI nút trả lời (anTraLoi) — mỗi lần chạy phải tiêu một lời duyệt mới.
// W-6 (§7.4, §7.6): phiên sống (phien_song === true) đang hỏi → trả lời trực tiếp, KHÔNG Xin duyệt lại
// (runner: co_the_xin_duyet_lai = False khi còn phiên). laTonTien bỏ trống → suy theo loại.
function nutHanhDong(viec, laTonTien) {
  const ok = !!viec && typeof viec === "object";
  const tonTien = ok && (typeof laTonTien === "boolean" ? laTonTien : LOAI_TON_TIEN.includes(viec.loai));
  if (tonTien && viec.phien_song === true && viec.trang_thai === "can_tra_loi") return { xinDuyetLai: false, anChayTiep: true, anTraLoi: false };
  const co = tonTien && (viec.trang_thai === "loi" || viec.trang_thai === "can_tra_loi");
  return { xinDuyetLai: co, anChayTiep: co, anTraLoi: tonTien && viec.trang_thai === "can_tra_loi" };
}
function nutChoViecTonTien(viec) {
  return nutHanhDong(viec, !!viec && typeof viec === "object" && LOAI_TON_TIEN.includes(viec.loai));
}

// ---------- W-6 (§7.6): khung trả lời trong phiên sống ----------
const TRA_LOI_CHU_TOI_DA_WEB = 1000; // code point — khớp Worker TRA_LOI_CHU_TOI_DA
const RE_DIEU_KHIEN_TRU_XD = /[\u0000-\u0009\u000b-\u001f\u007f]/;
// "" = hợp lệ; ngược lại câu báo lỗi (khớp Worker: cho xuống dòng, cấm điều khiển khác + surrogate lẻ).
function kiemChuTraLoi(s) {
  if (typeof s !== "string" || !s.trim()) return "Câu trả lời không được để trống";
  if ([...s].length > TRA_LOI_CHU_TOI_DA_WEB) return `Câu trả lời tối đa ${TRA_LOI_CHU_TOI_DA_WEB} ký tự`;
  if (RE_DIEU_KHIEN_TRU_XD.test(s) || coSurrogateLe(s)) return "Câu trả lời có ký tự lỗi";
  return "";
}
// FX-25 (§7.6): mã câu hỏi runner sinh cho mỗi câu hỏi phiên sống; web gửi lại khi trả lời để runner không trả nhầm câu mới.
const RE_MA_CAU_HOI_WEB = /^q[0-9a-f]{12}$/; // khớp Worker RE_MA_CAU_HOI + runner kieu.RE_MA_CAU_HOI
function maCauHoi(viec) {
  if (!viec || typeof viec !== "object") return "";
  const c = docJsonViec(viec.cau_hoi);
  const ma = c && typeof c === "object" ? c.ma : "";
  return typeof ma === "string" && RE_MA_CAU_HOI_WEB.test(ma) ? ma : "";
}
// Khoá nhận diện câu hỏi đang treo: đổi câu hỏi (agent hỏi lại/rút câu) hoặc đổi mã câu hỏi → vẽ lại khung, không gửi câu trả lời cũ.
function khoaCauHoi(viec) {
  if (!viec || typeof viec !== "object") return "";
  const c = docJsonViec(viec.cau_hoi);
  return `${laIdViec(viec.id) ? viec.id : ""}|${maCauHoi(viec)}|${c && typeof c === "object" ? JSON.stringify(c) : ""}`;
}
// Khung trả lời (vẽ MỘT lần vào #vj-tra-loi theo khoaCauHoi; polling không vẽ lại để giữ chữ đang gõ).
// Ô mật khẩu KHÔNG BAO GIỜ có value. opt: {khoa}. Không phải phiên sống đang hỏi → "".
function khungTraLoiHtml(viec, opt = {}) {
  const v = viec && typeof viec === "object" ? viec : null;
  if (!v || v.trang_thai !== "can_tra_loi" || v.phien_song !== true) return "";
  const k = nutTraLoi(v.cau_hoi, 5, LOAI_TON_TIEN.includes(v.loai), true);
  if (!k.nut.length && !k.o_chu) return "";
  const dis = opt && opt.khoa ? " disabled" : "";
  return `<form class="vtl" id="vtl-form">
      <div class="small muted">Trả lời thẳng vào phiên đang chạy — không cần duyệt lại${k.can_mat_khau ? "; nhập lại mật khẩu mỗi lần gửi" : ""}.</div>
      ${k.o_chu ? `<label for="vtl-chu">Câu trả lời <span class="small muted">(1–${TRA_LOI_CHU_TOI_DA_WEB} ký tự)</span>
        <textarea id="vtl-chu" class="vtl-chu" rows="4" maxlength="${TRA_LOI_CHU_TOI_DA_WEB}"${dis}></textarea></label>` : ""}
      ${k.can_mat_khau ? `<label for="vtl-mk">Mật khẩu đăng nhập
        <input type="password" id="vtl-mk" class="vtl-mk" autocomplete="current-password" maxlength="256"${dis}></label>` : ""}
      <div class="row vtl-nut">${k.nut.map((n, i) => `<button type="button" class="btn sm" data-vtl-nut="${i}"${dis}>${esc(n.nhan)}</button>`).join("")}
        ${k.o_chu ? `<button type="button" class="btn sm" data-vtl-act="gui"${dis}>➤ Gửi trả lời</button>` : ""}</div>
    </form>`;
}

// Khung chỉ đạo agent (#vj-chi-dao): việc phiên sống đang chạy/đang hỏi. "Nhắn" xếp hàng (agent nhận khi xong bước đang
// làm; khoá khi agent đang hỏi — trả lời ở khung trên); "Ngắt & nhắn" giết phiên ngay, chỉ đạo đi vào phiếu lần chạy
// tiếp sau Xin duyệt lại. Ô mật khẩu KHÔNG BAO GIỜ có value. opt: {khoa}.
// Việc taovideo KHÔNG còn phiên ở loi/cho_duyet: chỉ "Ghi chỉ đạo" (lưu cho lần chạy tiếp sau Xin duyệt lại → Duyệt).
function khungChiDaoHtml(viec, opt = {}) {
  const v = viec && typeof viec === "object" ? viec : null;
  if (!v) return "";
  const song = v.phien_song === true && ["dang_chay", "can_tra_loi"].includes(v.trang_thai);
  const ghi = !song && v.loai === "taovideo" && ["loi", "cho_duyet"].includes(v.trang_thai);
  if (!song && !ghi) return "";
  const dis = opt && opt.khoa ? " disabled" : "";
  const dangHoi = v.trang_thai === "can_tra_loi";
  const huongDan = song
    ? `Nhắn: agent nhận khi xong bước đang làm (đang chờ render/voice nền thì nhận ngay).
        Ngắt &amp; nhắn: dừng ngay cả render/voice, rồi bấm Xin duyệt lại → Duyệt để chạy lại theo chỉ đạo.`
    : `Việc không còn chạy: chỉ đạo được lưu và đưa vào phiếu lần chạy tiếp${v.trang_thai === "loi" ? " — sau đó bấm ↻ Xin duyệt lại rồi Duyệt" : " — sau đó Duyệt"}.`;
  const nut = song
    ? `<button type="button" class="btn sm" data-vcd-act="nhan"${dangHoi ? " disabled title=\"Agent đang hỏi — trả lời ở khung trên, hoặc Ngắt & nhắn\"" : dis}>➤ Nhắn</button>
        <button type="button" class="btn ghost sm" data-vcd-act="ngat"${dis}>⏹ Ngắt &amp; nhắn</button>`
    : `<button type="button" class="btn sm" data-vcd-act="ghi"${dis}>💾 Ghi chỉ đạo</button>`;
  return `<form class="vtl vcd" id="vcd-form">
      <h3>💬 Chỉ đạo agent</h3>
      <div class="small muted">${huongDan}</div>
      <label for="vcd-chu">Chỉ đạo <span class="small muted">(1–${TRA_LOI_CHU_TOI_DA_WEB} ký tự)</span>
        <textarea id="vcd-chu" class="vtl-chu" rows="3" maxlength="${TRA_LOI_CHU_TOI_DA_WEB}" placeholder="vd: Kịch bản không được nói giá, làm lại voice"${dis}></textarea></label>
      <label for="vcd-mk">Mật khẩu đăng nhập
        <input type="password" id="vcd-mk" class="vtl-mk" autocomplete="current-password" maxlength="256"${dis}></label>
      <div class="row vtl-nut">
        ${nut}</div>
    </form>`;
}

// tham_so_chuan (GET /api/viec/<id>) — NGUYÊN chuỗi runner trả, phải là JSON object; sai/thiếu → "" (không cho duyệt).
function thamSoChuanDuyet(d) {
  const s = d && typeof d === "object" ? d.tham_so_chuan : null;
  if (typeof s !== "string" || !s || s.length > 100000) return "";
  try { const o = JSON.parse(s); return o && typeof o === "object" && !Array.isArray(o) ? s : ""; } catch { return ""; }
}

// sha256 hex chữ thường của chuỗi UTF-8 (crypto.subtle — chỉ có ở HTTPS/localhost; thiếu thì ném lỗi).
async function sha256HexWeb(s) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(String(s)));
  return [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

// 409 của Worker khi sha_tham_so không khớp tham_so_chuan hiện tại → phải tải lại việc rồi duyệt lại.
const duLieuViecDoi = (r) => !!r && r.status === 409 && typeof r.loi === "string" && r.loi.includes("Dữ liệu việc đã đổi");

// Câu "Lời duyệt" gợi ý sẵn theo loại (người dùng sửa được).
function loiDuyetMau(viec) {
  const v = viec && typeof viec === "object" ? viec : {};
  const ts = thamSoObj(v.tham_so);
  const g = (k) => (ts[k] == null ? "?" : String(ts[k]));
  let s;
  if (v.loai === "muse_clip") {
    const n = Array.isArray(ts.mau) ? ts.mau.length : 0;
    s = `Đồng ý sinh ${n} clip B-roll AI (Muse) ${ts.thoi_luong == null ? 10 : g("thoi_luong")} giây, tỉ lệ ${ts.ti_le == null ? "9:16" : g("ti_le")}, cho dự án ${g("du_an")}.`;
  } else if (v.loai === "voice_genmax") s = `Đồng ý sinh voice GenMax mẻ ${g("me")} của dự án ${g("du_an")} theo đúng ước tính ở trên.`;
  else if (v.loai === "poster_len_lich") s = `Đồng ý lên lịch đăng Poster cho folder ${g("folder_id")}, ${g("so_video_ngay")} video/ngày.`;
  else if (v.loai === "taovideo") s = `Đồng ý dựng 2 mẻ video cho dự án A ${g("du_an_a")}, B ${ts.du_an_b === "tu_tim" ? "tự tìm" : g("du_an_b")}, watermark ${tenWm(ts.wm)} — 1 lời duyệt cho cả phiên, trong trần ở trên.`;
  else s = `Đồng ý chạy ${tenLoaiViec(v.loai)} với tham số ở trên.`;
  return catKyTu(s, LOI_DUYET_TOI_DA_WEB);
}

// "" = hợp lệ; ngược lại là câu báo lỗi (khớp kiểm của Worker).
function kiemLoiDuyet(s) {
  if (typeof s !== "string" || !s.trim()) return "Lời duyệt không được để trống";
  if ([...s].length > LOI_DUYET_TOI_DA_WEB) return `Lời duyệt tối đa ${LOI_DUYET_TOI_DA_WEB} ký tự`;
  if (coSurrogateLe(s)) return "Lời duyệt có ký tự lỗi";
  return "";
}

// Ước tính/chi phí từ ket_qua.uoc_tinh, viec.uoc_tinh, xem_truoc (object hoặc chuỗi/JSON) → dòng chữ (chưa esc).
const NHAN_UOC_TINH = { so_ban: "Số bản", ky_tu: "Ký tự", credit: "Credit", so_clip: "Số clip", chi_phi_usd: "Chi phí (USD)", ghi_chu: "Ghi chú" };
function dongUocTinh(d) {
  const x = d && typeof d === "object" ? d : {};
  const v = x.viec && typeof x.viec === "object" ? x.viec : {};
  const kq = docJsonViec(v.ket_qua);
  const ra = [];
  const them = (s) => { const t = String(s).slice(0, 500); if (t.trim() && !ra.includes(t)) ra.push(t); };
  for (const n of [kq && typeof kq === "object" ? kq.uoc_tinh : null, v.uoc_tinh, x.xem_truoc]) {
    if (n == null || n === "") continue;
    let o = n;
    if (typeof n === "string") { try { o = JSON.parse(n); } catch { o = n; } }
    if (o && typeof o === "object" && !Array.isArray(o)) {
      for (const [k, val] of Object.entries(o)) {
        if (val == null || (typeof val === "object" && !Array.isArray(val))) continue;
        them(`${coKhoa(NHAN_UOC_TINH, k) ? NHAN_UOC_TINH[k] : k}: ${Array.isArray(val) ? val.join(", ") : val}`);
      }
    } else if (Array.isArray(o)) them(o.join(", "));
    else them(o);
  }
  return ra.slice(0, 20);
}

// Tham số dễ hiểu cho người duyệt → [[nhãn, giá trị]] (chưa esc).
function moTaThamSoDuyet(loai, tsTho) {
  const ts = thamSoObj(tsTho);
  const NHAN = { uid: "Sản phẩm (UID)", du_an: "Dự án", me: "Mẻ", mau: "Mẫu clip", thoi_luong: "Thời lượng", ti_le: "Tỉ lệ", folder_id: "Folder Poster", so_video_ngay: "Số video/ngày",
    du_an_a: "Dự án A (raw, giọng Adam)", du_an_b: "Dự án B (takes, giọng creator)", wm: "Watermark", gia: "Giá (đ)" };
  const ra = Object.keys(ts).map((k) => {
    const val = ts[k];
    if (k === "du_an_b" && val === "tu_tim") return [NHAN.du_an_b, "Tự tìm (dự án duy nhất có takes/)"];
    if (k === "wm") return [NHAN.wm, tenWm(val)];
    if (k === "mau") return [NHAN.mau, (Array.isArray(val) ? val : [val]).map(tenMau).join(", ")];
    if (k === "thoi_luong") return [NHAN.thoi_luong, `${val} giây`];
    if (k === "folder_id") return [NHAN.folder_id, `#${val}`];
    if (k === "so_video_ngay") return [NHAN.so_video_ngay, `${val} video/ngày`];
    return [coKhoa(NHAN, k) ? NHAN[k] : k, Array.isArray(val) ? val.join(", ") : String(val)];
  });
  if (loai === "muse_clip" && Array.isArray(ts.mau)) ra.push(["Tổng", `${ts.mau.length} clip × ${ts.thoi_luong == null ? 10 : ts.thoi_luong} giây`]);
  return ra;
}

// Hạn mức liên quan tới loại, từ /api/viec/suc-khoe (trần trong han_muc; "còn lại" chỉ tính được cho Claude).
const HAN_MUC_LOAI = {
  muse_clip: [["muse_clip_moi_viec", "clip/việc"], ["muse_clip_ngay", "clip/ngày"]],
  voice_genmax: [["genmax_ban_moi_viec", "bản/việc"], ["genmax_viec_ngay", "việc GenMax/ngày"]],
  poster_len_lich: [["poster_len_lich_ngay", "việc/ngày"], ["poster_video_ngay_toi_da", "video/tài khoản/ngày"]],
  taovideo: [["taovideo_usd_viec", "USD/phiên"], ["taovideo_mp3_viec", "voice/phiên"], ["codex_luot_viec", "Codex/phiên"],
    ["taovideo_ngay", "việc/ngày"], ["taovideo_lan_ngay", "lần duyệt/ngày"]],
};
// §7.5: một lời duyệt = một phiên sống; hiện khi máy nhà chưa gửi uoc_tinh có câu này.
const TRAN_PHIEN_TAOVIDEO = "1 lời duyệt = 1 phiên chạy. Trong phiên: ≤25 voice GenMax (đếm file thật), ≤6 lượt Codex, ≤60 USD-ước-tính Claude, ≤8 giờ làm, mỗi câu hỏi chờ ≤3 giờ. Phiên bị ngắt (máy tắt, quá giờ, chạm trần) → phải duyệt lại. Trả lời câu hỏi trong phiên không cần duyệt lại.";
function hanMucHtml(loai, sk) {
  if (!sk || typeof sk !== "object") return `<span class="muted">Đang hỏi hạn mức…</span>`;
  const hm = sk.han_muc && typeof sk.han_muc === "object" ? sk.han_muc : {};
  const tran = (coKhoa(HAN_MUC_LOAI, loai) ? HAN_MUC_LOAI[loai] : []).filter(([k]) => hm[k] != null).map(([k, dv]) => `${esc(hm[k])} ${esc(dv)}`);
  const phan = [];
  if (tran.length) phan.push(`Trần: ${tran.join(" · ")}`);
  if (LOAI_CO_CLAUDE.includes(loai)) {
    const conUsd = Number(hm.claude_usd_ngay) - Number(sk.chi_phi_hom_nay_usd);
    const conViec = Number(hm.claude_viec_ngay) - Number(sk.viec_claude_hom_nay);
    const c = [];
    if (Number.isFinite(conUsd)) c.push(`$${esc(Math.max(0, conUsd).toFixed(2))}`);
    if (Number.isFinite(conViec)) c.push(`${esc(Math.max(0, conViec))} việc`);
    if (c.length) phan.push(`Claude hôm nay còn: ${c.join(" · ")}`);
  }
  return phan.length ? phan.join("<br>") : `<span class="muted">Không có số hạn mức.</span>`;
}

// ---------- W-7: phần đầu dễ hiểu của khung duyệt (Dự kiến / Tối đa / Sẽ làm ra). Chuỗi trả về CHƯA esc. ----------
const soKhongAm = (x) => (typeof x === "number" && Number.isFinite(x) && x >= 0 ? x : null);
const soGon = (n) => String(Math.round(n * 100) / 100);
const soTrongTranPhien = (re) => { const m = TRAN_PHIEN_TAOVIDEO.match(re); return m ? Number(m[1]) : null; };
// "Dự kiến": chi phí USD nếu máy nhà gửi; không thì vài dòng ước tính; câu trần phiên (§7.5) không phải dự kiến.
function duKienDuyet(ut) {
  const ds = (Array.isArray(ut) ? ut : []).filter((s) => typeof s === "string" && !s.includes("1 lời duyệt = 1 phiên"));
  const tien = `${NHAN_UOC_TINH.chi_phi_usd}: `;
  const usd = ds.find((s) => s.startsWith(tien));
  if (usd) return `~${usd.slice(tien.length)} USD`;
  return ds.length ? `~${ds.slice(0, 3).join(" · ")}` : "Chưa có ước tính";
}
// "Tối đa" từ sk.han_muc (như hanMucHtml). taovideo thiếu số → lấy từ TRAN_PHIEN_TAOVIDEO (trần code; cấu hình chỉ được hạ).
// → {chu: câu hiển thị, nut: trần ngắn cho nút Duyệt ("" = không ghi)}.
const TRAN_LOAI_DUYET = { muse_clip: ["muse_clip_moi_viec", "clip/việc", "clip"], voice_genmax: ["genmax_ban_moi_viec", "bản/việc", "bản"],
  poster_len_lich: ["poster_video_ngay_toi_da", "video/tài khoản/ngày", ""] };
function toiDaDuyet(loai, sk) {
  const hm = sk && typeof sk === "object" && sk.han_muc && typeof sk.han_muc === "object" ? sk.han_muc : null;
  const lay = (k) => (hm ? soKhongAm(hm[k]) : null);
  if (loai === "taovideo") {
    const usd = lay("taovideo_usd_viec") ?? soTrongTranPhien(/≤(\d+(?:\.\d+)?) USD/);
    const voice = lay("taovideo_mp3_viec") ?? soTrongTranPhien(/≤(\d+) voice/);
    const lamS = lay("taovideo_lam_s");
    const gio = lamS ? lamS / 3600 : soTrongTranPhien(/≤(\d+(?:\.\d+)?) giờ làm/);
    const p = [];
    if (usd != null) p.push(`${soGon(usd)} USD Claude`);
    if (voice != null) p.push(`${soGon(voice)} voice`);
    if (gio != null) p.push(`${soGon(gio)} giờ làm`);
    return { chu: p.length ? p.join(" · ") : TRAN_PHIEN_TAOVIDEO, nut: usd != null ? `${soGon(usd)} USD` : "" };
  }
  if (!coKhoa(TRAN_LOAI_DUYET, loai)) return { chu: "Chưa có số trần", nut: "" };
  if (!hm) return { chu: sk ? "Chưa có số trần" : "Đang hỏi hạn mức…", nut: "" };
  const [k, dv, dvNut] = TRAN_LOAI_DUYET[loai];
  const n = lay(k);
  return n == null ? { chu: "Chưa có số trần", nut: "" } : { chu: `${soGon(n)} ${dv}`, nut: dvNut ? `${soGon(n)} ${dvNut}` : "" };
}
function nhanNutDuyet(loai, sk) {
  const t = toiDaDuyet(loai, sk);
  return `✓ Duyệt & chạy${t.nut ? ` (tối đa ${t.nut})` : ""}`;
}
// "Sẽ làm ra": chỉ từ tham số có thật — không tự chọn/đoán watermark hay kênh.
function seLamRaDuyet(loai, tsTho) {
  const ts = thamSoObj(tsTho);
  const so = (k) => (Number.isInteger(ts[k]) && ts[k] > 0 ? ts[k] : null);
  const ra = [];
  if (so("so_video") != null) ra.push(`${so("so_video")} video`);
  if (loai === "muse_clip" && Array.isArray(ts.mau)) ra.push(`${ts.mau.length} clip × ${ts.thoi_luong == null ? 10 : ts.thoi_luong} giây`);
  if (loai === "voice_genmax" && ts.me != null) ra.push(`Voice cho mẻ ${String(ts.me)}`);
  if (loai === "taovideo") ra.push("2 mẻ video: mẻ giọng Adam + mẻ giọng creator");
  if (coKhoa(ts, "wm")) ra.push(`Gắn logo: ${tenWm(ts.wm)}`);
  else if (loai === "taovideo") ra.push("Gắn logo: tham số chưa ghi — đừng duyệt, tạo lại việc");
  if (ts.folder_id != null) ra.push(`Đăng vào folder Poster #${String(ts.folder_id)}${so("so_video_ngay") != null ? `, ${so("so_video_ngay")} video/ngày` : ""}`);
  if (typeof ts.kenh === "string" && ts.kenh) ra.push(`Kênh đăng: ${ts.kenh}`);
  return ra;
}

// Chốt Loại / Ngừng đăng ở nút Duyệt của việc poster_len_lich (§4.8). loai: {kq, cau} (dgKetLuanDuyet, dang.js) hoặc
// {kq:"dang_kiem"}. Khoá: co_loai, ngung_dang, dang_kiem và mọi kq lạ (thiên về chặt); khong_biet chỉ cảnh báo; sach / không có → bật.
function khoaLoaiDuyet(loai) {
  if (!loai || typeof loai !== "object") return false;
  return loai.kq !== "sach" && loai.kq !== "khong_biet";
}
// Khối câu dưới phần tham số (không có gì khi sach / không có). dis: thuộc tính disabled của nút "↻ Kiểm lại".
function loaiDuyetHtml(loai, dis = "") {
  if (!loai || typeof loai !== "object" || loai.kq === "sach") return "";
  if (loai.kq === "dang_kiem") return `<div class="small muted" id="vd-loai">Đang kiểm video bị Loại của folder…</div>`;
  const cau = typeof loai.cau === "string" && loai.cau ? loai.cau : "Chưa kiểm được video bị Loại của folder này.";
  const nut = ` <button type="button" class="btn ghost sm" data-vd-act="kiem-loai"${dis}>↻ Kiểm lại</button>`;
  return loai.kq === "khong_biet"
    ? `<div class="vj-can-ban" id="vd-loai">⚠ ${esc(cau)}${nut}</div>`
    : `<div class="vj-loi" id="vd-loai">⛔ ${esc(cau)}${nut}</div>`;
}

// Khung duyệt (vẽ MỘT lần vào #vj-duyet, không vẽ lại khi polling để giữ chữ đang gõ). opt: {sk, khoa, loai}.
// Ô mật khẩu KHÔNG BAO GIỜ có value. Tham số hiện từ tham_so_chuan (đúng chuỗi được băm gửi kèm sha_tham_so);
// thiếu tham_so_chuan → nút Duyệt luôn khoá, báo tải lại.
function khungDuyetHtml(d, opt = {}) {
  const v = (d && d.viec) || {};
  const dis = opt.khoa ? " disabled" : "";
  const tsc = thamSoChuanDuyet(d);
  const disDuyet = opt.khoa || !tsc || khoaLoaiDuyet(opt.loai) ? " disabled" : "";
  const ts = moTaThamSoDuyet(v.loai, tsc || v.tham_so);
  const ut = dongUocTinh(d);
  const td = toiDaDuyet(v.loai, opt.sk);
  const lamRa = seLamRaDuyet(v.loai, tsc || v.tham_so);
  return `<form class="vd" id="vd-form">
      <div class="vd-dau"><b>💳 Duyệt việc tốn tiền: ${esc(tenLoaiViec(v.loai))}</b></div>
      <div class="vd-tom">
        <div><b>Dự kiến:</b> ${esc(duKienDuyet(ut))}</div>
        <div><b>Tối đa:</b> <span id="vd-toi-da">${esc(td.chu)}</span></div>
        ${lamRa.length ? `<div><b>Sẽ làm ra:</b> ${lamRa.map((s) => esc(s)).join(" · ")}</div>` : ""}
      </div>
      ${ts.length ? `<dl class="kv vd-ts">${ts.map(([k, x]) => `<dt>${esc(k)}</dt><dd>${esc(x)}</dd>`).join("")}</dl>` : ""}
      ${tsc ? "" : `<div class="vj-can-ban">⚠ Chưa nhận được tham số chuẩn của việc — tải lại rồi mới duyệt được. <button type="button" class="btn ghost sm" data-vd-act="tai-lai"${dis}>↻ Tải lại</button></div>`}
      ${loaiDuyetHtml(opt.loai, dis)}
      <div class="vd-uoc"><b>Ước tính / chi phí</b>${ut.length ? `<ul class="small">${ut.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>` : `<div class="small muted">Máy nhà chưa gửi ước tính.</div>`}</div>
      ${v.loai === "taovideo" && !ut.some((s) => s.includes("1 lời duyệt = 1 phiên")) ? `<div class="small vd-tran"><b>Trần mỗi phiên:</b> ${esc(TRAN_PHIEN_TAOVIDEO)}</div>` : ""}
      <div class="small vd-hm" id="vd-hm">${hanMucHtml(v.loai, opt.sk)}</div>
      <label for="vd-loi">Lời duyệt <span class="small muted">(sửa được — lưu cùng chữ ký duyệt)</span>
        <textarea id="vd-loi" class="vd-loi" rows="3" maxlength="${LOI_DUYET_TOI_DA_WEB}">${esc(loiDuyetMau(tsc ? { ...v, tham_so: tsc } : v))}</textarea></label>
      <label for="vd-mk">Mật khẩu đăng nhập <span class="small muted">(nhập lại mỗi lần duyệt)</span>
        <input type="password" id="vd-mk" class="vd-mk" autocomplete="current-password" maxlength="256"></label>
      <div class="row vd-nut"><button type="button" class="btn sm" data-vd-act="duyet"${disDuyet}>${esc(nhanNutDuyet(v.loai, opt.sk))}</button>
        <button type="button" class="btn ghost sm" data-vd-act="tu-choi"${dis}>Từ chối</button></div>
    </form>`;
}

// Tham số tạo muse_clip → {tham_so} | {loi}. mau giữ thứ tự danh mục.
function thamSoMuse(uid, duAn, mau, thoiLuong) {
  if (typeof uid !== "string" || !RE_UID_VIEC.test(uid)) return { loi: "UID sản phẩm không hợp lệ" };
  if (typeof duAn !== "string" || !RE_DU_AN_VIEC.test(duAn)) return { loi: "Chưa chọn dự án" };
  const ds = Array.isArray(mau) ? mau : [];
  if (!ds.length) return { loi: "Chọn ít nhất 1 mẫu clip" };
  if (new Set(ds).size !== ds.length || ds.some((m) => !coKhoa(TEN_MAU_MUSE, m))) return { loi: "Mẫu clip không hợp lệ" };
  if (!MUSE_THOI_LUONG_WEB.includes(thoiLuong)) return { loi: "Thời lượng phải là 10 hoặc 15 giây" };
  return { tham_so: { uid, du_an: duAn, mau: Object.keys(TEN_MAU_MUSE).filter((k) => ds.includes(k)), thoi_luong: thoiLuong, ti_le: "9:16" } };
}

const POSTER_VIDEO_NGAY_WEB = [1, 100]; // số video/ngày cho phép (phiếu FX-12 bổ sung)
// Tham số tạo poster_len_lich (giá trị dropdown/ô số là chuỗi) → {tham_so} | {loi}.
function thamSoPoster(folderId, soVideo) {
  const f = soNguyenWeb(folderId), n = soNguyenWeb(soVideo);
  const [nMin, nMax] = POSTER_VIDEO_NGAY_WEB;
  if (!Number.isInteger(f) || f <= 0 || f >= 1e9) return { loi: "Chọn folder Poster" };
  if (!Number.isInteger(n) || n < nMin || n > nMax) return { loi: `Số video/ngày phải từ ${nMin} đến ${nMax}` };
  return { tham_so: { folder_id: f, so_video_ngay: n } };
}

// ---------- W-6: form taovideo (§7.10) ----------
const WM_TAOVIDEO_WEB = ["khong", "nha.cua.mit"]; // khớp Worker WM_TAOVIDEO
const TEN_WM = { khong: "Không watermark", "nha.cua.mit": "nha.cua.mit" };
const GIA_TAOVIDEO_WEB = [1000, 10000000];
function tenWm(w) { return coKhoa(TEN_WM, w) ? TEN_WM[w] : String(w ?? "?"); }
// W-7: nhắc rõ logo sẽ in lên video; chưa chọn thì nói chưa chọn (không tự chọn ngầm).
function wmNhacHtml(w) {
  return WM_TAOVIDEO_WEB.includes(w) ? `Logo này sẽ in lên video: <b>${esc(tenWm(w))}</b>`
    : `<span class="err">Chưa chọn logo.</span> Logo này sẽ in lên video — chọn "Không watermark" nếu không muốn in logo.`;
}
// Watermark được chọn: lua_chon của tham số wm trong /api/viec/danh-muc ∩ danh sách cho phép; thiếu/rỗng → cả danh sách.
function wmTaovideo(danhMuc) {
  const ds = danhMuc && Array.isArray(danhMuc.loai) ? danhMuc.loai : [];
  const l = ds.find((x) => x && x.ma === "taovideo");
  const ts = l && Array.isArray(l.tham_so) ? l.tham_so.find((t) => t && t.ten === "wm") : null;
  const lc = ts && Array.isArray(ts.lua_chon) ? ts.lua_chon : [];
  const ra = WM_TAOVIDEO_WEB.filter((w) => lc.includes(w));
  return ra.length ? ra : WM_TAOVIDEO_WEB.slice();
}
// Giá trị form (chuỗi từ select/ô số) → {tham_so} | {loi}. gia rỗng = không gửi.
function thamSoTaovideo(uid, duAnA, duAnB, wm, gia) {
  if (typeof uid !== "string" || !RE_UID_VIEC.test(uid)) return { loi: "UID sản phẩm không hợp lệ" };
  if (typeof duAnA !== "string" || !RE_DU_AN_VIEC.test(duAnA)) return { loi: "Chọn dự án A (có raw/)" };
  if (typeof duAnB !== "string" || !(duAnB === "tu_tim" || RE_DU_AN_VIEC.test(duAnB))) return { loi: "Chọn dự án B (có takes/) hoặc Tự tìm" };
  if (duAnB === duAnA) return { loi: "Dự án A và B phải khác nhau" };
  if (!WM_TAOVIDEO_WEB.includes(wm)) return { loi: "Chọn watermark" };
  const tham_so = { uid, du_an_a: duAnA, du_an_b: duAnB, wm };
  const g = typeof gia === "number" ? String(gia) : typeof gia === "string" ? gia.trim() : "";
  if (g) {
    const n = /^\d{1,9}$/.test(g) ? Number(g) : NaN;
    const [gMin, gMax] = GIA_TAOVIDEO_WEB;
    if (!Number.isInteger(n) || n < gMin || n > gMax) return { loi: `Giá phải là số nguyên ${gMin}–${gMax} đồng (hoặc để trống)` };
    tham_so.gia = n;
  }
  return { tham_so };
}

// W-7: tự điền form taovideo. Dự án A: tự chọn khi máy nhà chỉ có ĐÚNG 1 dự án (đã chọn rồi thì giữ).
function duAnATuDong(duAn, hienTai) {
  if (typeof hienTai === "string" && hienTai) return hienTai;
  const ds = Array.isArray(duAn) ? duAn.filter((p) => p && RE_DU_AN_VIEC.test(String(p.ma))) : [];
  return ds.length === 1 ? String(ds[0].ma) : "";
}
// Giá từ info SP ("112.389₫") → chuỗi số nguyên đồng nếu CHẮC (1 con số, dấu chấm ngăn nghìn, trong khoảng Worker nhận); không → "".
function giaTuInfoSp(info) {
  const g = info && typeof info.gia === "string" ? info.gia.trim() : "";
  const m = g.match(/^(\d{1,3}(?:\.\d{3})*|\d+)\s*(?:₫|đ|vnđ|vnd)?$/i);
  if (!m) return "";
  const n = Number(m[1].replace(/\./g, ""));
  const [gMin, gMax] = GIA_TAOVIDEO_WEB;
  return Number.isInteger(n) && n >= gMin && n <= gMax ? String(n) : "";
}

// GET /api/viec/poster/folders → [{id, ten}] sạch (id nguyên dương < 1e9, không trùng).
function locFolderPoster(r) {
  const ds = r && Array.isArray(r.folders) ? r.folders : [];
  const ra = [];
  for (const x of ds) {
    if (!x || typeof x !== "object" || !Number.isInteger(x.id) || x.id <= 0 || x.id >= 1e9 || ra.some((y) => y.id === x.id)) continue;
    ra.push({ id: x.id, ten: typeof x.ten === "string" && x.ten.trim() ? x.ten.slice(0, 80) : `#${x.id}` });
  }
  return ra;
}

// Form tạo việc đợt 4 trong khối việc SP. form: {loai, ...giá trị đang chọn}; opt: {folders, loi, khoa}.
function formViecSpHtml(form, opt = {}) {
  if (!form || typeof form !== "object") return "";
  const o = opt || {};
  const dis = o.khoa ? " disabled" : "";
  const dong = `<button type="button" class="btn ghost sm" data-vs-an="1">Đóng</button>`;
  const luuY = `<p class="small muted">Việc tốn tiền: tạo xong sẽ chờ bạn duyệt (nhập lại mật khẩu) mới chạy.</p>`;
  if (form.loai === "muse_clip") {
    const chon = Array.isArray(form.mau) ? form.mau : [];
    const tl = MUSE_THOI_LUONG_WEB.includes(form.thoi_luong) ? form.thoi_luong : MUSE_THOI_LUONG_WEB[0];
    return `<div class="vs-form">
      <div class="small"><b>${esc(tenLoaiViec("muse_clip"))}</b> · ${esc(form.nhan || "")}</div>
      <fieldset class="vs-mau"><legend class="small muted">Chọn mẫu clip (mỗi mẫu 1 clip)</legend>
        ${Object.keys(TEN_MAU_MUSE).map((k) => `<label class="vs-ck"><input type="checkbox" data-vs-mau="${k}"${chon.includes(k) ? " checked" : ""}> ${esc(TEN_MAU_MUSE[k])}</label>`).join("")}
      </fieldset>
      <div class="vs-tl small">Thời lượng: ${MUSE_THOI_LUONG_WEB.map((s) => `<label class="vs-ck"><input type="radio" name="vs-tl" data-vs-tl="${s}"${s === tl ? " checked" : ""}> ${s} giây</label>`).join("")}
        <span class="muted">· tỉ lệ 9:16</span></div>
      ${luuY}
      <div class="row vs-nut"><button type="button" class="btn sm" data-vs-gui="muse_clip"${dis}>▶ Tạo việc</button>${dong}</div>
    </div>`;
  }
  if (form.loai === "poster_len_lich") {
    const dau = `<div class="small"><b>${esc(tenLoaiViec("poster_len_lich"))}</b></div>`;
    if (o.loi) return `<div class="vs-form">${dau}<p class="small err">⚠ ${esc(o.loi)}</p><div class="row vs-nut"><button type="button" class="btn ghost sm" data-vs-folder-lai="1">↻ Thử lại</button>${dong}</div></div>`;
    if (!Array.isArray(o.folders)) return `<div class="vs-form">${dau}<p class="small muted">Đang hỏi máy nhà danh sách folder Poster…</p></div>`;
    if (!o.folders.length) return `<div class="vs-form">${dau}<p class="small muted">Poster chưa có folder nào.</p><div class="row vs-nut">${dong}</div></div>`;
    const fId = soNguyenWeb(form.folder_id);
    const nRaw = soNguyenWeb(form.so_video_ngay);
    const [nMin, nMax] = POSTER_VIDEO_NGAY_WEB;
    const n = Number.isInteger(nRaw) && nRaw >= nMin && nRaw <= nMax ? nRaw : nMin;
    return `<div class="vs-form">${dau}
      <label class="small">Folder Poster
        <select class="vs-sel" data-vs-folder><option value="">— chọn folder —</option>${o.folders.map((f) => `<option value="${esc(f.id)}"${f.id === fId ? " selected" : ""}>${esc(f.ten)}</option>`).join("")}</select></label>
      <label class="small">Số video/ngày (${nMin}–${nMax})
        <input type="number" class="vs-sel" data-vs-so min="${nMin}" max="${nMax}" step="1" inputmode="numeric" value="${n}"></label>
      ${luuY}
      <div class="row vs-nut"><button type="button" class="btn sm" data-vs-gui="poster_len_lich"${dis}>▶ Tạo việc</button>${dong}</div>
    </div>`;
  }
  if (form.loai === "taovideo") {
    // opt.duAn: [{ma, ten}] từ /api/viec/du-an/<uid> (null = đang tải); opt.duAnLoi; opt.wm: danh sách watermark.
    // W-7: nhãn lời thường (giá trị gửi đi giữ nguyên); hộp chọn đợt quay chỉ hiện khi ≥2 dự án hoặc máy nhà báo lỗi chốt B.
    const dau = `<div class="small"><b>Làm video</b> <span class="muted">· 2 mẻ: 1 mẻ giọng Adam + 1 mẻ giọng creator</span></div>`;
    if (o.duAnLoi) return `<div class="vs-form">${dau}<p class="small err">⚠ ${esc(o.duAnLoi)}</p><div class="row vs-nut">${dong}</div></div>`;
    if (!Array.isArray(o.duAn)) return `<div class="vs-form">${dau}<p class="small muted">Đang hỏi máy nhà danh sách đợt quay…</p></div>`;
    if (!o.duAn.length) return `<div class="vs-form">${dau}<p class="small muted">Máy nhà chưa có dự án nào cho SP này (chưa có đợt quay).</p><div class="row vs-nut">${dong}</div></div>`;
    const wmDs = Array.isArray(o.wm) && o.wm.length ? o.wm : WM_TAOVIDEO_WEB;
    const opt1 = (ma, ten, chon) => `<option value="${esc(ma)}"${ma === chon ? " selected" : ""}>${esc(ten)}</option>`;
    const tenDa = (p) => String(p.ten || `Thư mục ${String(p.ma).slice(0, 6)}`); // tên thư mục (thường có ngày) thay mã hash
    const b = typeof form.du_an_b === "string" ? form.du_an_b : "tu_tim";
    const nhieu = o.duAn.length >= 2;
    const aChon = o.duAn.find((p) => p.ma === form.du_an_a);
    const hopA = nhieu || !aChon
      ? `<label class="small">Đợt quay dùng cho video giọng Adam
        <select class="vs-sel" data-vs-a><option value="">— chọn đợt quay —</option>${o.duAn.map((p) => opt1(p.ma, tenDa(p), form.du_an_a)).join("")}</select></label>`
      : `<div class="small">Đợt quay dùng cho video giọng Adam: <b>${esc(tenDa(aChon))}</b></div>`;
    const hopB = nhieu || form.loi_b || b !== "tu_tim"
      ? `<label class="small">Đợt quay có giọng creator
        <select class="vs-sel" data-vs-b>${b === "" ? `<option value="" selected>— chọn đợt quay —</option>` : ""}${opt1("tu_tim", "Tự tìm", b)}${o.duAn.map((p) => opt1(p.ma, tenDa(p), b)).join("")}</select></label>`
      : `<div class="small">Đợt quay có giọng creator: <b>Tự tìm</b> <span class="muted">(máy nhà tự lấy đợt có giọng creator)</span></div>`;
    const wmChon = wmDs.includes(form.wm) ? form.wm : "";
    return `<div class="vs-form">${dau}
      ${hopA}
      ${hopB}
      ${form.loi_b ? `<p class="small err">⚠ ${esc(form.loi_b)} — chọn đợt quay có giọng creator trong danh sách rồi tạo lại.</p>` : ""}
      <label class="small">Logo (watermark)
        <select class="vs-sel" data-vs-wm>${wmChon ? "" : `<option value="" selected>— chọn logo —</option>`}${wmDs.map((w) => opt1(w, tenWm(w), wmChon)).join("")}</select></label>
      <p class="small vs-wm-nhac">${wmNhacHtml(wmChon)}</p>
      <label class="small">Giá bán (đồng, tuỳ chọn)
        <input type="number" class="vs-sel" data-vs-gia min="${GIA_TAOVIDEO_WEB[0]}" max="${GIA_TAOVIDEO_WEB[1]}" step="1000" inputmode="numeric" value="${esc(form.gia == null ? "" : String(form.gia))}"></label>
      ${luuY.replace("mới chạy.", "mới chạy — 1 lần duyệt cho cả phiên.")}
      <div class="row vs-nut"><button type="button" class="btn sm" data-vs-gui="taovideo"${dis}>▶ Tạo việc</button>${dong}</div>
    </div>`;
  }
  return "";
}

// Một trang log {tu, den, noi_dung, het} → {tu mới, them, het, con (đọc tiếp ngay được)}. Không tiến → dừng.
function buocLog(r, tu) {
  const x = r || {};
  const them = typeof x.noi_dung === "string" ? x.noi_dung : "";
  const den = Number(x.den);
  const tuMoi = Number.isFinite(den) && den > tu ? den : tu;
  const het = x.het !== false;
  return { tu: tuMoi, them, het, con: !het && !!them && tuMoi > tu };
}

// Việc đã dừng (không dang_chay) mà lượt đọc log cuối còn het === false (runner chưa ghi xong đuôi log:
// "giết cả cây…", "kết thúc: mã …") → hẹn đọc lại sau ~2,5 s, tối đa LOG_DOC_LAI_TOI_DA lần.
// cuoi = buocLog của trang cuối (null khi lượt đọc lỗi); con = true thì nút "Tải thêm" lo, không tự đọc.
const LOG_DOC_LAI_TOI_DA = 20;
function canDocLaiLog(tt, cuoi, lanDaDoc) {
  return typeof tt === "string" && tt !== "dang_chay" && !!cuoi && cuoi.het === false && !cuoi.con
    && Number.isInteger(lanDaDoc) && lanDaDoc < LOG_DOC_LAI_TOI_DA;
}

// FX-25 (hợp đồng runner FX-22 §7.2a): nút Chạy lại / Chạy tiếp theo cờ co_the_chay_lai / co_the_chay_tiep của runner.
// Thiếu cờ (máy nhà bản cũ) → hành vi cũ (chạy lại khi loi/huy; chạy tiếp khi loi + co_the_chay_tiep).
// can_luu_lai_mat_khau (bản sửa có đổi chữ phụ đề) → ẩn cả hai, phải lưu lại ở màn Sửa video kèm mật khẩu.
// Việc tốn tiền (D9, nutHanhDong.anChayTiep) không bao giờ có Chạy tiếp.
function nutChayLaiTiep(viec) {
  if (!viec || typeof viec !== "object") return { chayLai: false, chayTiep: false, luuLai: false };
  if (viec.can_luu_lai_mat_khau === true) return { chayLai: false, chayTiep: false, luuLai: true };
  const tt = viec.trang_thai;
  const chayLai = typeof viec.co_the_chay_lai === "boolean" ? viec.co_the_chay_lai : tt === "loi" || tt === "huy";
  const chayTiep = viec.co_the_chay_tiep === true && !nutHanhDong(viec).anChayTiep; // runner chỉ bật ở loi; thiếu cờ = false (như cũ)
  return { chayLai, chayTiep, luuLai: false };
}
const RE_MA_VIDEO_VIEC = /^[0-9a-f]{16}$/; // khớp RE_MA_VIDEO_SUA (web/sua.js)
// Link để lưu lại bản sửa: #/sua/<uid>/<ma_video> từ tham_so; thiếu ma_video → trang SP; thiếu uid → về kho.
function linkLuuLaiSua(viec) {
  const ts = viec && typeof viec === "object" ? thamSoObj(viec.tham_so) : {};
  const uid = typeof ts.uid === "string" && RE_UID_VIEC.test(ts.uid) ? ts.uid : "";
  const ma = typeof ts.ma_video === "string" && RE_MA_VIDEO_VIEC.test(ts.ma_video) ? ts.ma_video : "";
  if (uid && ma) return { href: `#/sua/${uid}/${ma}`, nhan: "Mở màn Sửa video để lưu lại" };
  if (uid) return { href: `#/sp/${uid}`, nhan: "Mở trang sản phẩm → Sửa video để lưu lại" };
  return { href: "#/kho", nhan: "Về kho → mở sản phẩm → Sửa video để lưu lại" };
}

// Nội dung trang #/viec/<id>. opt: {dotBat, khoa (đang gửi lệnh → nút tắt), md (text → html đã làm sạch, hoặc bỏ),
// canhBao (chuỗi cảnh báo của lệnh vừa gửi, vd. huỷ mà chưa dừng được tiến trình)}.
function chiTietViecHtml(d, opt = {}) {
  const v = (d && d.viec) || {};
  const tt = nhanTrangThai(v.trang_thai);
  const dis = opt.khoa ? " disabled" : "";
  const mo = TT_MO.includes(v.trang_thai);
  const ch = docJsonViec(v.cau_hoi);
  const kq = docJsonViec(v.ket_qua);
  const ts = dongThamSo(v.tham_so);
  const pre = (s) => `<pre class="vj-pre">${esc(s)}</pre>`;
  const dong = [];
  dong.push(`<div class="vj-dau"><span class="tt ${tt.lop}">${esc(tt.nhan)}</span> <b>${esc(tenLoaiViec(v.loai))}</b> <span class="small muted">${esc(v.id || "")}</span></div>`);
  dong.push(`<dl class="kv">
      ${ts ? `<dt>Tham số</dt><dd>${esc(ts)}</dd>` : ""}
      <dt>Tạo</dt><dd>${esc(v.tao_boi || "?")} · ${esc(gioViec(v.tao_luc))}</dd>
      ${v.bat_dau_luc ? `<dt>Bắt đầu</dt><dd>${esc(gioViec(v.bat_dau_luc))}</dd>` : ""}
      ${v.ket_thuc_luc ? `<dt>Kết thúc</dt><dd>${esc(gioViec(v.ket_thuc_luc))}</dd>` : ""}
      ${v.lan_thu > 1 ? `<dt>Lần thử</dt><dd>${esc(v.lan_thu)}</dd>` : ""}
      ${v.so_lan_claude ? `<dt>Claude</dt><dd>${esc(v.so_lan_claude)} lần · ${esc(v.so_luot_claude || 0)} lượt · $${esc(soViec(v.chi_phi_usd, 2))}</dd>` : ""}
      ${laIdViec(v.chay_lai_tu) ? `<dt>Chạy lại từ</dt><dd><a href="#/viec/${esc(v.chay_lai_tu)}">${esc(v.chay_lai_tu)}</a></dd>` : ""}
      ${laIdViec(v.cha_id) ? `<dt>Việc cha</dt><dd><a href="#/viec/${esc(v.cha_id)}">${esc(v.cha_id)}</a></dd>` : ""}
    </dl>`);
  if (opt.canhBao) dong.push(`<div class="vj-can-ban">⚠ ${esc(opt.canhBao)}</div>`);
  if (v.can_ban) dong.push(dangChoNen(v) ? `<div class="vj-cho-nen">⏳ ${esc(v.can_ban)}</div>` : `<div class="vj-can-ban">⚠ ${esc(v.can_ban)}</div>`);
  if (v.ghi_chu) dong.push(`<p class="small muted">📝 ${esc(v.ghi_chu)}</p>`);
  // FX-25: ket_qua.thong_diep (runner dịch mã thoát 2/5 của bước sửa video) thay loi thô; chi tiết thô ở log.
  const kqObj = kq && typeof kq === "object" && !Array.isArray(kq) ? kq : {};
  const thongDiep = typeof kqObj.thong_diep === "string" && kqObj.thong_diep.trim() ? kqObj.thong_diep : "";
  if (kqObj.kiem_tay === true) {
    const boQua = (Array.isArray(kqObj.bo_qua) ? kqObj.bo_qua : []).filter((x) => typeof x === "string" && x);
    dong.push(`<div class="vj-can-ban vj-kiem-tay"><b>🔎 Cần kiểm tay</b>${thongDiep ? `<div>${esc(thongDiep)}</div>` : ""}
      ${boQua.length ? `<div class="small">Đã bỏ qua:</div><ul class="small">${boQua.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}</div>`);
  } else if (thongDiep) dong.push(`<div class="vj-loi">⚠ ${esc(thongDiep)}</div>`);
  else if (v.loi) dong.push(`<div class="vj-loi">⚠ ${esc(v.loi)}</div>`);
  if (thongDiep || kqObj.kiem_tay === true) dong.push(`<div class="row"><button type="button" class="btn ghost sm" data-vj-xem-log="1">📜 Xem log chi tiết</button></div>`);

  // Khung trả lời bằng nút. Phiên sống (W-6): nút/ô chữ/mật khẩu nằm ở khung riêng #vj-tra-loi (khungTraLoiHtml).
  const laTonTien = LOAI_TON_TIEN.includes(v.loai);
  const tonTien = nutHanhDong(v, laTonTien);
  if (v.trang_thai === "can_tra_loi") {
    const song = v.phien_song === true;
    // giữ chỉ số gốc của nutTraLoi (handler tra lại theo chỉ số); việc tốn tiền không phiên: không nút nào (D9, FX-13)
    const nut = tonTien.anTraLoi || song ? [] : nutTraLoi(ch, opt.dotBat, laTonTien, false).nut.map((n, k) => ({ ...n, k }));
    const loai = ch && ch.loai;
    const tieuDe = loai === "viec_tay" ? "👉 Việc của bạn" : loai === "khong_ro" ? "❓ Agent dừng mà không rõ lý do" : "❓ Cần bạn trả lời";
    const huongDan = song
      ? `<p class="small muted">Phiên đang chạy chờ bạn trả lời (việc nền vẫn chạy) — trả lời ở khung bên dưới, không cần duyệt lại.</p>`
      : tonTien.anTraLoi
        ? `<p class="small muted">Việc tốn tiền: trả lời xong phải duyệt lại bằng mật khẩu — bấm "↻ Xin duyệt lại" rồi duyệt, hoặc Huỷ.</p>`
        : `<p class="small muted">Câu hỏi này cần trả lời bằng chữ — đợt 3 chỉ trả lời bằng nút, hãy làm trên máy nhà hoặc Huỷ.</p>`;
    dong.push(`<div class="vj-hoi">
        <div class="vj-hoi-dau"><b>${tieuDe}</b></div>
        ${ch && ch.noi_dung ? `<div class="vj-hoi-nd">${esc(ch.noi_dung)}</div>` : ""}
        ${nut.length ? "" : huongDan}
        <div class="row vj-hoi-nut">${nut.map((n) => `<button class="btn sm" data-vj-tl="${n.k}"${dis}>${esc(n.nhan)}</button>`).join("")}
          <button class="btn ghost sm" data-vj-act="huy"${dis}>Huỷ việc</button></div>
      </div>`);
  }
  // opt.khungDuyet: trang đang có khung duyệt riêng (#vj-duyet, khungDuyetHtml) → không vẽ khối cũ ở đây.
  if (v.trang_thai === "cho_duyet" && !opt.khungDuyet) {
    dong.push(`<div class="vj-hoi"><b>⏳ Việc chờ duyệt</b>${v.uoc_tinh ? `<div class="vj-hoi-nd">${esc(v.uoc_tinh)}</div>` : ""}
      <p class="small muted">Việc này không duyệt được trên web — duyệt trên máy nhà hoặc Từ chối.</p>
      <div class="row"><button class="btn ghost sm" data-vj-act="tu-choi"${dis}>Từ chối</button></div></div>`);
  }

  // Kết quả.
  if (kq && typeof kq === "object") {
    const fileRa = Array.isArray(kq.file_ra) ? kq.file_ra : [];
    const goiY = (Array.isArray(kq.goi_y_viec) ? kq.goi_y_viec : []).filter((l) => l === "douyin_uid");
    const tom = typeof kq.tom_tat === "string" ? kq.tom_tat : "";
    const mdHtml = tom && v.loai === "radar_ban_tin" && typeof opt.md === "function" ? opt.md(tom) : null;
    dong.push(`<h3>Kết quả${kq.trang_thai_agent ? ` <span class="small muted">${esc(kq.trang_thai_agent)}</span>` : ""}</h3>
      ${kq.co_lo_ngai ? `<div class="vj-can-ban">⚠ Có lo ngại — đọc tóm tắt bên dưới</div>` : ""}
      ${tom ? (mdHtml != null ? `<div class="md">${mdHtml}</div>` : pre(tom)) : ""}
      ${fileRa.length ? `<ul class="small vj-file">${fileRa.map((f) => `<li><code>${esc(f)}</code></li>`).join("")}</ul>` : ""}
      ${goiY.length && RE_UID_VIEC.test(String((docJsonViec(v.tham_so) || {}).uid || "")) ? `<div class="row">${goiY.map((l) => `<button class="btn sm" data-vj-goi-y="${esc(l)}"${dis}>▶ Chạy ${esc(tenLoaiViec(l))}</button>`).join("")}</div>` : ""}`);
  }
  if (typeof d.xem_truoc === "string" && d.xem_truoc) dong.push(`<h3>Xem trước</h3>${pre(d.xem_truoc)}`);

  // Nút điều khiển.
  const nut = [];
  if (mo && v.trang_thai !== "can_tra_loi") nut.push(`<button class="btn ghost sm" data-vj-act="huy"${dis}>Huỷ việc</button>`);
  if (tonTien.xinDuyetLai) nut.push(`<button class="btn sm" data-vj-act="xin-duyet-lai"${dis}>↻ Xin duyệt lại</button>`);
  const lt = nutChayLaiTiep(v);
  if (lt.chayTiep) nut.push(`<button class="btn sm" data-vj-act="chay-tiep"${dis}>▶ Chạy tiếp</button>`);
  if (lt.chayLai) nut.push(`<button class="btn ghost sm" data-vj-act="chay-lai"${dis}>↻ Chạy lại</button>`);
  if (lt.luuLai) {
    const lk = linkLuuLaiSua(v);
    nut.push(`<a class="btn sm" href="${esc(lk.href)}">✏ ${esc(lk.nhan)}</a>`);
    dong.push(`<p class="small muted">Bản sửa này có đổi chữ phụ đề — không chạy lại bằng nút được; mở màn Sửa video, lưu lại kèm mật khẩu.</p>`);
  }
  if (nut.length) dong.push(`<div class="row vj-nut">${nut.join("")}${opt.khoa ? `<span class="small muted">đang gửi…</span>` : ""}</div>`);
  if (v.loai === "taovideo" && mo) dong.push(`<p class="small muted">Huỷ dừng ngay render/voice; video đã xong vẫn giữ. Đừng chạy tay quy trình cùng SP khi việc đang chạy.</p>`);
  if (v.loai === "voice_pv") dong.push(`<p class="small muted">Huỷ không dừng ngay GPU của PerfectVoice (app còn xử lý nốt vài phút). Việc này chưa kiểm Whisper.</p>`);

  const traLoi = Array.isArray(d.tra_loi) ? d.tra_loi : [];
  if (traLoi.length) dong.push(`<h3>Đã trả lời</h3><ul class="small vj-su-kien">${traLoi.map((t) => `<li>${esc(gioViec(t && t.luc))} · ${esc(t && t.boi)}: ${esc(t && t.noi_dung)}</li>`).join("")}</ul>`);
  const suKien = Array.isArray(d.su_kien) ? d.su_kien : [];
  if (suKien.length) dong.push(`<h3>Sự kiện</h3><ul class="small vj-su-kien">${suKien.map((s) => `<li>${esc(gioViec(s && s.luc))} · ${esc(s && s.tu ? nhanTrangThai(s.tu).nhan : "mới")} → ${esc(nhanTrangThai(s && s.den).nhan)} · ${esc(s && s.boi)}${s && s.ghi_chu ? " · " + esc(s.ghi_chu) : ""}</li>`).join("")}</ul>`);
  return dong.join("\n");
}
// --- viec-thuan end ---

// ---------- phần có DOM ----------
let phienViec = 0;              // tăng mỗi lần rời/vào trang việc: phản hồi về muộn của trang cũ bị bỏ
let viecTrang = null;           // {lamMoi, timers} của trang việc đang mở
let dotBatViec = 3;             // cập nhật từ /api/viec/suc-khoe
const dangGuiViec = new Set();  // khoá chống bấm đúp: id việc đang gửi lệnh / "tao:<loai>|<tham_so>"

function dungViec() {
  phienViec++;
  if (viecTrang) viecTrang.timers.forEach((t) => clearInterval(t));
  viecTrang = null;
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && viecTrang) viecTrang.lamMoi();
});
const tabHien = () => document.visibilityState === "visible";
const mdSach = (s) => (window.DOMPurify && window.marked ? DOMPurify.sanitize(marked.parse(s)) : null);

// Báo khi có việc MỚI cần bạn (can_tra_loi/cho_duyet): tiêu đề tab, popup hệ thống, tiếng "ting".
const TIEU_DE_GOC = document.title;
let canBanTruoc = null, nhapNhayT = 0;
function tingViec() {
  try {
    const Ac = window.AudioContext || window.webkitAudioContext;
    if (!Ac) return;
    const ac = new Ac(), o = ac.createOscillator(), g = ac.createGain();
    o.frequency.value = 880; g.gain.setValueAtTime(0.15, ac.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.6);
    o.connect(g); g.connect(ac.destination); o.start(); o.stop(ac.currentTime + 0.6);
  } catch { /* trình duyệt chặn âm thanh khi chưa chạm trang */ }
}
function baoCanBan(n) {
  const moi = canBanTruoc !== null && n > canBanTruoc;
  canBanTruoc = n;
  clearInterval(nhapNhayT); nhapNhayT = 0;
  if (n <= 0) { document.title = TIEU_DE_GOC; return; }
  const a = `(${n}) 👉 Cần bạn – ${TIEU_DE_GOC}`;
  if (tabHien()) document.title = a;
  else { let b = false; document.title = a; nhapNhayT = setInterval(() => { b = !b; document.title = b ? TIEU_DE_GOC : a; }, 1000); }
  if (!moi) return;
  tingViec();
  if ("Notification" in window && Notification.permission === "granted") {
    try {
      const nt = new Notification("👉 Có việc cần bạn", { body: `${n} việc đang chờ bạn trả lời/duyệt`, tag: "viec-can-ban" });
      nt.onclick = () => { window.focus(); location.hash = "#/viec"; nt.close(); };
    } catch { /* bỏ qua */ }
  }
}
document.addEventListener("visibilitychange", () => { if (tabHien() && canBanTruoc > 0) { clearInterval(nhapNhayT); nhapNhayT = 0; document.title = `(${canBanTruoc}) 👉 Cần bạn – ${TIEU_DE_GOC}`; } });
// Xin quyền popup ở lần chạm đầu (trình duyệt đòi cử chỉ người dùng); poll nền 15s để báo cả khi không mở #/viec.
document.addEventListener("click", () => {
  if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
}, { once: true });
setInterval(() => { if (typeof laChu === "function" && laChu()) capNhatHuyHieuViec(); }, 15000);

// Huy hiệu ⚙ Việc = can_tra_loi + cho_duyet.
let huyHieuDangTai = false;
function datHuyHieuViec(n) {
  const el = $("#viec-hh");
  if (!el) return;
  el.textContent = n > 0 ? String(n) : "";
  el.hidden = !(n > 0);
}
async function capNhatHuyHieuViec() {
  if (!laChu() || huyHieuDangTai) return;
  huyHieuDangTai = true;
  try {
    const r = await api("viec?tom_tat=1");
    const n = demCanBan(r && r.dem);
    datHuyHieuViec(n);
    baoCanBan(n);
  } catch { /* bộ chạy việc tắt: không hiện huy hiệu */ }
  finally { huyHieuDangTai = false; }
}

// Tạo việc. Khoá theo (loai, tham_so) TRƯỚC await. Trả id việc (mới hoặc trùng) hoặc "".
// opt.khiLoi(err): gọi thêm khi lỗi (vd. taovideo "tu_tim" mà máy nhà không chốt được dự án B).
async function taoViec(loai, tham_so, nut, opt = {}) {
  const khoa = `tao:${loai}|${JSON.stringify(tham_so)}`;
  if (dangGuiViec.has(khoa)) return "";
  dangGuiViec.add(khoa);
  const nhanCu = nut ? nut.textContent : "";
  if (nut) { nut.disabled = true; nut.textContent = "Đang gửi…"; }
  try {
    const r = await api("viec", { loai, tham_so });
    if (r.status === 409) {
      toast(`Đã có việc ${tenLoaiViec(loai)} đang mở`);
      return idTrungViec(r);
    }
    const id = r.viec && r.viec.id;
    toast(`✓ Đã giao: ${tenLoaiViec(loai)}`);
    return laIdViec(id) ? id : "";
  } catch (err) {
    toast("⚠ " + err.message);
    if (opt && typeof opt.khiLoi === "function") opt.khiLoi(err);
    return "";
  } finally {
    dangGuiViec.delete(khoa);
    if (nut && nut.isConnected) { nut.disabled = false; nut.textContent = nhanCu; }
  }
}

// ---------- #/viec ----------
async function renderViec() {
  if (!laChu()) { $("#app").innerHTML = `<p class="center muted">Trang này chỉ dành cho chủ kho. <a href="#/kho">← Về kho</a></p>`; return; }
  const tk = phienViec;
  $("#app").innerHTML = `<p><a href="#/" class="small">← Hôm nay</a></p>
    <div class="vt-khung">
      <div class="row" style="justify-content:space-between"><h2 class="sk-tieu-de">⚙ Máy nhà</h2></div>
      <div id="vt-tom-tat"><p class="muted small">Đang hỏi bộ chạy việc…</p></div>
      <div class="row vt-giao">
        <button class="btn sm" id="vt-radar">📡 Bản tin radar</button>
        <button class="btn sm" id="vt-link">📥 Xử lý link mới</button>
      </div>
      <div id="vt-ds"></div>
    </div>`;
  const giao = (loai) => async (e) => {
    const id = await taoViec(loai, {}, e.currentTarget);
    if (tk !== phienViec) return; // đã rời trang
    if (id) location.hash = `#/viec/${id}`;
  };
  $("#vt-radar").addEventListener("click", giao("radar_ban_tin"));
  $("#vt-link").addEventListener("click", giao("xu_ly_link_moi"));

  // FX-28: mỗi nhóm giữ số trang riêng (không reset khi lamMoi() tự polling mỗi 5 s — chỉ đổi khi người dùng bấm
  // nút chuyển trang, hoặc khi trang hiện tại vượt quá tổng số trang mới thì kẹp về trang cuối còn hợp lệ).
  const trangNhom = { can_ban: 1, dang_chay: 1, dang_cho: 1, gan_day: 1 };
  let dangLamMoi = false;
  // Tải đúng 1 trang của 1 nhóm; trang hiện tại vượt quá tổng số trang mới (vd. tong giảm) → kẹp về trang cuối rồi tải lại.
  const taiTrangNhom = async (dinh) => {
    const goi = (trang) => api(`viec?trang_thai=${dinh.tt}&gioi_han=${TRANG_VIEC_SO_DONG}&offset=${(trang - 1) * TRANG_VIEC_SO_DONG}`);
    const docKq = (r) => {
      const ds = Array.isArray(r.viec) ? r.viec : [];
      return { ds, tong: Number.isInteger(r.tong) ? r.tong : ds.length };
    };
    let trang = trangNhom[dinh.k] || 1;
    let { ds, tong } = docKq(await goi(trang));
    const soTrang = soTrangViec(tong);
    if (trang > soTrang) {
      trang = soTrang;
      trangNhom[dinh.k] = trang;
      ({ ds, tong } = docKq(await goi(trang)));
    }
    return { ds, tong, trang };
  };
  const lamMoi = async () => {
    if (dangLamMoi || tk !== phienViec) return;
    dangLamMoi = true;
    try {
      const [sk, ...nhomKq] = await Promise.allSettled([api("viec/suc-khoe"), ...NHOM_VIEC.map(taiTrangNhom)]);
      if (tk !== phienViec) return;
      const tt = $("#vt-tom-tat"), dsEl = $("#vt-ds");
      if (sk.status === "fulfilled") {
        if (Number.isInteger(sk.value.dot_bat)) dotBatViec = sk.value.dot_bat;
        if (tt) tt.innerHTML = tomTatHtml(sk.value);
      } else if (tt) tt.innerHTML = `<div class="sk-banner">🔴 Bộ chạy việc không trả lời: ${esc(sk.reason && sk.reason.message)}</div>`;
      const g = {}, trangs = {};
      let coViec = false, coLoi = false;
      NHOM_VIEC.forEach((dinh, i) => {
        const kq = nhomKq[i];
        if (kq.status === "fulfilled") {
          g[dinh.k] = kq.value.ds; trangs[dinh.k] = { trang: kq.value.trang, tong: kq.value.tong };
          if (kq.value.tong > 0) coViec = true;
        } else { g[dinh.k] = []; coLoi = true; }
      });
      if (dsEl) {
        dsEl.innerHTML = coLoi && !coViec ? `<p class="err">⚠ Không lấy được danh sách việc</p>` : dsNhomHtml(g, trangs);
        capNhatHuyHieuViec(); // đếm toàn kho qua tom_tat=1, không đếm từ danh sách từng nhóm trên trang
      }
    } finally { dangLamMoi = false; }
  };

  // Nút chuyển trang (data-vt-trang="<nhóm>:<-1|1>") + nút "⏹ Dừng"/"🗃 Ẩn" trên thẻ (data-vt-act, data-vt-id):
  // chặn nổi bọt/điều hướng của <a class="vt"> bọc thẻ TRƯỚC khi xử lý (nút nằm trong thẻ, không đổi cấu trúc/CSS cũ).
  $("#vt-ds").addEventListener("click", (e) => {
    const bt = e.target.closest("button[data-vt-trang]");
    if (bt) {
      if (bt.disabled) return;
      const [k, d] = bt.dataset.vtTrang.split(":");
      trangNhom[k] = Math.max(1, (trangNhom[k] || 1) + Number(d));
      lamMoi();
      return;
    }
    const ba = e.target.closest("button[data-vt-act]");
    if (!ba || ba.disabled) return;
    e.preventDefault(); e.stopPropagation(); // nút nằm trong <a class="vt"> — không điều hướng khi bấm
    const act = ba.dataset.vtAct, idA = ba.dataset.vtId;
    if (!laIdViec(idA) || dangGuiViec.has(idA)) return;
    if (act === "huy" && !confirm("Dừng việc này?")) return;
    dangGuiViec.add(idA); // khoá TRƯỚC await
    ba.disabled = true;
    const nhanCu = ba.textContent;
    ba.textContent = "Đang gửi…";
    api(`viec/${idA}/${act}`, {}).then((r) => { if (tk === phienViec) toast(ketQuaHanhDong(act, r, idA).toast); })
      .catch((err) => { if (tk === phienViec) toast("⚠ " + err.message); })
      .finally(() => {
        dangGuiViec.delete(idA);
        if (tk === phienViec) lamMoi();
        else if (ba.isConnected) { ba.disabled = false; ba.textContent = nhanCu; }
      });
  });

  viecTrang = { lamMoi, timers: [setInterval(() => { if (tabHien()) lamMoi(); }, 5000)] };
  await lamMoi();
}

// ---------- #/viec/<id> ----------
async function renderViecChiTiet(id) {
  if (!laChu()) { $("#app").innerHTML = `<p class="center muted">Trang này chỉ dành cho chủ kho. <a href="#/kho">← Về kho</a></p>`; return; }
  if (!laIdViec(id)) { $("#app").innerHTML = `<p class="center">Mã việc không hợp lệ. <a href="#/may-nha">← Máy nhà</a></p>`; return; }
  const tk = phienViec;
  $("#app").innerHTML = `<p><a href="#/may-nha" class="small">← Máy nhà</a></p>
    <div class="vj">
      <div id="vj-nd"><p class="muted">Đang tải…</p></div>
      <div id="vj-tra-loi"></div>
      <div id="vj-chi-dao"></div>
      <div id="vj-duyet"></div>
      <h3>Log <span class="small muted" id="vj-log-tt"></span></h3>
      <pre class="vj-log" id="vj-log"></pre>
      <div class="row"><button class="btn ghost sm" id="vj-log-them" hidden>⬇ Tải thêm log</button></div>
    </div>`;
  let d = null, logTu = 0, logText = "", logDangTai = false, viecDangTai = false;
  let logXepHang = false;  // có lời gọi taiLog() trong lúc đang tải → chạy thêm đúng 1 lần sau khi xong
  let canhBaoViec = "";    // cảnh báo của lệnh vừa gửi (vd. huỷ mà runner chưa dừng được tiến trình)
  let logDocLai = 0;       // số lần đã hẹn đọc lại đuôi log sau khi việc dừng (canDocLaiLog)
  let henLog = false;      // đang có một lần hẹn đọc lại chờ chạy
  const LOG_TRANG_CHAY = 5;  // trang 64 KB mỗi lượt khi việc đang chạy (polling lấy tiếp)
  const LOG_TRANG_XONG = 8;  // việc đã dừng: đọc đến het, tối đa 8 trang/lượt; còn nữa → nút "Tải thêm"

  // Khung duyệt (#vj-duyet): vẽ MỘT lần khi việc vào cho_duyet, không vẽ lại theo polling (giữ chữ đang gõ);
  // mật khẩu chỉ nằm trong ô input và body của đúng lần gửi — không lưu ở đâu khác.
  let khungDuyetMo = false, skDuyet = null, skDangTai = false;
  // khungTsc: tham_so_chuan chụp lúc vẽ khung = chuỗi người duyệt đang thấy → băm gửi sha_tham_so (không lấy d mới về sau).
  // lanTaiViec/dLan/khungChoLan: sau 409 "Dữ liệu việc đã đổi" chỉ vẽ lại khung bằng dữ liệu của lần tải BẮT ĐẦU sau đó.
  let khungTsc = "", lanTaiViec = 0, dLan = 0, khungChoLan = 0;
  // §4.8 (W-M3): việc poster_len_lich → kiểm video Loại / ⛔ Ngừng đăng của folder TRƯỚC khi vẽ khung; nút Duyệt khoá theo kết quả.
  // loaiDuyet: {fid, kq, cau} của lần kiểm gần nhất (null = chưa kiểm); khungLoai: kết quả đang dùng trong khung đang hiện.
  let loaiDuyet = null, loaiDangKiem = false, choLoai = false, khungLoai = null;
  const khoaKhungDuyet = (khoa) => {
    if (tk !== phienViec) return; // phản hồi muộn của trang cũ: không đụng DOM trang mới
    const box = $("#vj-duyet");
    if (!box || !khungDuyetMo) return;
    box.querySelectorAll("button, textarea, input").forEach((el) => {
      el.disabled = khoa || (el.dataset.vdAct === "duyet" && (!khungTsc || khoaLoaiDuyet(khungLoai)));
    });
  };
  const boKhungDuyet = () => {
    const box = $("#vj-duyet");
    if (box) box.innerHTML = ""; // bỏ cả ô mật khẩu
    khungDuyetMo = false; khungTsc = ""; khungLoai = null; choLoai = false;
  };
  // Folder của việc poster_len_lich (chuỗi, lấy từ tham_so_chuan = đúng cái sẽ ký); null = không phải việc lên lịch.
  const folderDuyet = (tsc) => {
    if (!d || !d.viec || d.viec.loai !== "poster_len_lich") return null;
    const ts = docJsonViec(tsc || d.viec.tham_so);
    return String((ts && typeof ts === "object" ? ts.folder_id : "") ?? "");
  };
  // FX-W3: mỗi lượt kiểm có số; "↻ Kiểm lại" tăng số (bỏ lượt đang chạy) → chỉ lượt mới nhất được ghi loaiDuyet.
  let luotKiem = 0;
  const kiemLoaiDuyet = async (fid) => {
    if (loaiDangKiem || tk !== phienViec) return;
    loaiDangKiem = true; // khoá TRƯỚC await: polling không kiểm chồng
    const luot = ++luotKiem;
    let kq = null;
    try { kq = typeof dgKiemLoaiFolder === "function" ? await dgKiemLoaiFolder(fid) : null; }
    catch { kq = null; }
    finally { if (luot === luotKiem) loaiDangKiem = false; } // lượt cũ bị bỏ: khoá đã thuộc lượt mới, không mở
    if (luot !== luotKiem) return; // đã có lượt kiểm mới hơn
    if (tk !== phienViec) return; // đã rời trang
    if (!kq || typeof kq !== "object" || typeof kq.kq !== "string") kq = { kq: "khong_biet", cau: "Không kiểm được video Loại của folder này: kiểm folder ở Poster V2" };
    loaiDuyet = { kq: kq.kq, cau: typeof kq.cau === "string" ? kq.cau : "", fid };
    veDuyet();
  };
  const taiSkDuyet = async () => {
    if (skDangTai || skDuyet || tk !== phienViec) return;
    skDangTai = true; // khoá TRƯỚC await
    try {
      const sk = await api("viec/suc-khoe");
      if (tk !== phienViec) return;
      if (Number.isInteger(sk.dot_bat)) dotBatViec = sk.dot_bat;
      skDuyet = sk;
      const el = $("#vd-hm");
      if (el && d && d.viec) el.innerHTML = hanMucHtml(d.viec.loai, sk);
      // W-7: cập nhật "Tối đa" + chữ nút Duyệt theo hạn mức vừa về (chỉ đổi chữ, không đổi trạng thái khoá/cơ chế duyệt)
      const td = $("#vd-toi-da"), nut = $('#vj-duyet button[data-vd-act="duyet"]');
      if (d && d.viec) {
        if (td) td.textContent = toiDaDuyet(d.viec.loai, sk).chu;
        if (nut) nut.textContent = nhanNutDuyet(d.viec.loai, sk);
      }
    } catch {
      if (tk !== phienViec) return;
      const el = $("#vd-hm");
      if (el) el.innerHTML = `<span class="muted">Không lấy được hạn mức — máy nhà vẫn kiểm khi duyệt.</span>`;
    } finally { skDangTai = false; }
  };
  const veDuyet = () => {
    if (tk !== phienViec) return;
    const box = $("#vj-duyet");
    if (!box) return;
    if (!d || !duocDuyet(d.viec, auth.user)) {
      if (khungDuyetMo || choLoai) boKhungDuyet(); // rời cho_duyet: bỏ khung (cả ô mật khẩu)
      return;
    }
    const tsc = thamSoChuanDuyet(d);
    if (khungDuyetMo && tsc !== khungTsc && !dangGuiViec.has(id)) boKhungDuyet(); // tham số đổi → vẽ lại cho đúng cái sẽ ký
    if (!khungDuyetMo) {
      if (dLan <= khungChoLan) return; // chờ dữ liệu mới sau 409 "Dữ liệu việc đã đổi"
      const fid = folderDuyet(tsc);
      if (fid !== null && (!loaiDuyet || loaiDuyet.fid !== fid)) { // chưa kiểm folder này: chờ kết quả rồi mới vẽ khung
        if (!choLoai) { box.innerHTML = loaiDuyetHtml({ kq: "dang_kiem" }); choLoai = true; }
        kiemLoaiDuyet(fid);
        return;
      }
      choLoai = false;
      khungLoai = fid !== null ? loaiDuyet : null;
      box.innerHTML = khungDuyetHtml(d, { sk: skDuyet, khoa: dangGuiViec.has(id), loai: khungLoai || undefined });
      khungDuyetMo = true;
      khungTsc = tsc;
      taiSkDuyet();
    }
    khoaKhungDuyet(dangGuiViec.has(id));
  };
  // Khung trả lời phiên sống (#vj-tra-loi, W-6): vẽ MỘT lần cho mỗi câu hỏi (khoaCauHoi), polling không vẽ lại
  // để giữ chữ đang gõ; câu hỏi đổi/hết → bỏ khung (cả ô mật khẩu). Mật khẩu chỉ nằm trong ô input + body lần gửi.
  // khungTlChoLan (FX-25): sau 409 của tra-loi (câu hỏi đã đổi) chỉ vẽ lại khung bằng dữ liệu của lần tải BẮT ĐẦU sau đó.
  let khungTlMo = false, khungTlKhoa = "", khungTlChoLan = 0;
  const khoaKhungTraLoi = (khoa) => {
    if (tk !== phienViec) return; // phản hồi muộn của trang cũ: không đụng DOM trang mới
    const box = $("#vj-tra-loi");
    if (!box || !khungTlMo) return;
    box.querySelectorAll("button, textarea, input").forEach((el) => { el.disabled = khoa; });
  };
  const boKhungTraLoi = () => {
    const box = $("#vj-tra-loi");
    if (box) box.innerHTML = "";
    khungTlMo = false; khungTlKhoa = "";
  };
  const veTraLoi = () => {
    if (tk !== phienViec) return;
    const v = d && d.viec;
    const html = v ? khungTraLoiHtml(v, { khoa: dangGuiViec.has(id) }) : "";
    const khoa = html ? khoaCauHoi(v) : "";
    if (khungTlMo && khoa !== khungTlKhoa && !dangGuiViec.has(id)) boKhungTraLoi(); // câu hỏi đổi/hết
    if (!khungTlMo && html) {
      if (dLan <= khungTlChoLan) return; // chờ dữ liệu mới sau 409 "Câu hỏi đã đổi"
      const box = $("#vj-tra-loi");
      if (!box) return;
      box.innerHTML = html;
      khungTlMo = true; khungTlKhoa = khoa;
    }
    khoaKhungTraLoi(dangGuiViec.has(id));
  };
  // Khung chỉ đạo (#vj-chi-dao): vẽ lại chỉ khi đổi trạng thái (dang_chay ↔ can_tra_loi) để giữ chữ đang gõ.
  let khungCdKhoa = "";
  const veChiDao = () => {
    if (tk !== phienViec) return;
    const box = $("#vj-chi-dao");
    if (!box) return;
    const v = d && d.viec;
    const html = v ? khungChiDaoHtml(v) : "";
    const khoa = html ? `${v.id}|${v.trang_thai}` : "";
    if (khoa !== khungCdKhoa && !dangGuiViec.has(id)) {
      const chu = $("#vcd-chu");
      const giu = chu ? chu.value : "";
      box.innerHTML = html;
      khungCdKhoa = khoa;
      const moi = $("#vcd-chu");
      if (moi && giu) moi.value = giu;
    }
    if (khungCdKhoa) box.querySelectorAll("button, textarea, input").forEach((el) => {
      el.disabled = dangGuiViec.has(id) || (el.dataset.vcdAct === "nhan" && v && v.trang_thai === "can_tra_loi");
    });
  };
  const ve = () => {
    if (tk !== phienViec) return;
    const nd = $("#vj-nd");
    if (!nd || !d) return;
    nd.innerHTML = chiTietViecHtml(d, { dotBat: dotBatViec, khoa: dangGuiViec.has(id), md: mdSach, canhBao: canhBaoViec, khungDuyet: duocDuyet(d.viec, auth.user) });
    veTraLoi();
    veChiDao();
    veDuyet();
  };
  const taiViec = async () => {
    if (viecDangTai || tk !== phienViec) return;
    viecDangTai = true;
    const lan = ++lanTaiViec;
    try {
      const r = await api(`viec/${id}`);
      if (tk !== phienViec) return;
      const songCu = logDangSong(d && d.viec);
      d = r;
      dLan = lan;
      ve();
      if (songCu && !logDangSong(r.viec)) taiLog(); // lấy nốt log cuối
    } catch (err) {
      if (tk !== phienViec) return;
      if (!d) { const nd = $("#vj-nd"); if (nd) nd.innerHTML = `<p class="err">⚠ ${esc(err.message)}</p>`; }
      else toast("⚠ " + err.message);
    } finally { viecDangTai = false; }
  };
  const taiLog = async () => {
    if (tk !== phienViec) return;
    if (logDangTai) { logXepHang = true; return; } // không bỏ lượt: vd. lấy đuôi log ngay khi việc vừa dừng
    logDangTai = true; // khoá TRƯỚC await
    logXepHang = false;
    const tt = $("#vj-log-tt"), nutThem = $("#vj-log-them");
    if (nutThem) nutThem.disabled = true;
    const chay = !d || !d.viec || logDangSong(d.viec); // phiên sống đang hỏi: việc nền vẫn ghi log
    if (d && d.viec && logDangSong(d.viec)) logDocLai = 0; // chạy lại/chạy tiếp rồi dừng → được hẹn lại từ đầu
    let conThem = false;
    let cuoi = null; // buocLog của trang cuối lượt này (null nếu lỗi)
    try {
      const toiDa = chay ? LOG_TRANG_CHAY : LOG_TRANG_XONG;
      for (let k = 0; k < toiDa; k++) {
        const r = await api(`viec/${id}/log?tu=${logTu}`);
        if (tk !== phienViec) return;
        const b = buocLog(r, logTu);
        cuoi = b;
        if (b.them) {
          const el = $("#vj-log");
          const cuoi = el && el.scrollHeight - el.scrollTop - el.clientHeight < 40;
          logText += b.them;
          if (logText.length > 200000) logText = "…(đã cắt bớt phần đầu)\n" + logText.slice(-150000);
          if (el) { el.textContent = logText; if (cuoi) el.scrollTop = el.scrollHeight; }
        }
        logTu = b.tu;
        conThem = !chay && b.con; // việc đã dừng mà hết lượt vẫn còn log
        if (!b.con) break;         // hết dữ liệu hiện có
      }
      if (tt) tt.textContent = conThem ? "(còn nữa)" : "";
    } catch (err) {
      if (tk === phienViec && tt) tt.textContent = "⚠ " + err.message;
      conThem = !chay; // cho bấm thử lại
    } finally {
      logDangTai = false;
      if (tk === phienViec) {
        if (nutThem && nutThem.isConnected) { nutThem.hidden = !conThem; nutThem.disabled = false; }
        if (logXepHang) { logXepHang = false; taiLog(); }
        else if (!henLog && !logDangSong(d && d.viec) && canDocLaiLog(d && d.viec && d.viec.trang_thai, cuoi, logDocLai)) {
          henLog = true; logDocLai++; // đặt cờ + đếm TRƯỚC khi hẹn
          const h = setTimeout(() => {
            henLog = false;
            if (tk !== phienViec) return; // đã rời trang/đổi việc
            taiLog();
          }, 2500);
          if (viecTrang) viecTrang.timers.push(h); // dungViec() huỷ cùng các timer khác
        }
      }
    }
  };
  $("#vj-log-them").addEventListener("click", () => taiLog());

  // body: object, hoặc hàm async trả object (gọi SAU khi đã khoá — vd. băm sha_tham_so khi duyệt).
  // Trả phản hồi của runner (kể cả 409) hoặc null khi không gửi được / lỗi.
  const hanhDong = async (act, body) => {
    if (dangGuiViec.has(id)) return null;
    dangGuiViec.add(id); // khoá TRƯỚC await
    ve();
    let chuyen = false, r = null;
    try {
      const b = typeof body === "function" ? await body() : body;
      if (tk !== phienViec) return null; // đã rời trang trong lúc chuẩn bị body: không gửi
      r = await api(`viec/${id}/${act}`, b || {});
      if (tk !== phienViec) return;
      const k = ketQuaHanhDong(act, r, id);
      if (r.status !== 409) canhBaoViec = k.canhBao;
      if (act === "duyet" && duLieuViecDoi(r)) {
        // tham số trên máy nhà khác chuỗi đã hiển thị: bỏ khung, chỉ vẽ lại bằng dữ liệu tải SAU lúc này
        khungChoLan = lanTaiViec;
        boKhungDuyet();
        toast("⚠ Dữ liệu việc đã đổi — đang tải lại, kiểm tham số rồi duyệt lại");
      } else if (act === "tra-loi" && r.status === 409) {
        // FX-25: runner báo câu hỏi đã đổi (mã lệch) / việc không còn chờ → hiện lý do, bỏ khung, vẽ lại bằng dữ liệu tải sau
        khungTlChoLan = lanTaiViec;
        boKhungTraLoi();
        toast("⚠ " + (typeof r.loi === "string" && r.loi ? r.loi : "Câu hỏi đã đổi — tải lại để xem câu mới"));
      } else toast(k.toast);
      if (k.chuyen) { chuyen = true; location.hash = `#/viec/${k.chuyen}`; }
    } catch (err) { r = null; if (tk === phienViec) toast("⚠ " + err.message); }
    finally {
      dangGuiViec.delete(id);
      if (tk === phienViec && !chuyen) { ve(); taiViec(); }
    }
    return r;
  };

  // Duyệt & chạy: kiểm lời duyệt + tham số chuẩn → lấy mật khẩu ra rồi xoá ô NGAY (thành công hay lỗi đều không còn) →
  // khoá nút → gửi (hanhDong đặt dangGuiViec trước await, rồi mới băm sha_tham_so). Không await nào trước khi khoá.
  // sha_tham_so băm khungTsc = đúng chuỗi tham_so_chuan đang hiển thị trong khung.
  const guiDuyet = () => {
    if (dangGuiViec.has(id) || tk !== phienViec || !d || !duocDuyet(d.viec, auth.user)) return;
    const oLoi = $("#vd-loi"), oMk = $("#vd-mk");
    if (!oLoi || !oMk) return;
    const tsc = khungTsc;
    if (!tsc) { toast("⚠ Chưa có tham số chuẩn của việc — tải lại rồi duyệt"); return; }
    if (khoaLoaiDuyet(khungLoai)) { toast("⚠ " + (khungLoai.cau || "Chưa duyệt được việc lên lịch này")); return; } // §4.8: chặn cả khi nút bị bật lại

    const loi_duyet = oLoi.value;
    const sai = kiemLoiDuyet(loi_duyet);
    if (sai) { toast("⚠ " + sai); oLoi.focus(); return; }
    if (!oMk.value) { toast("⚠ Nhập mật khẩu để duyệt"); oMk.focus(); return; }
    const mat_khau = oMk.value;
    oMk.value = "";
    khoaKhungDuyet(true);
    hanhDong("duyet", async () => ({ loi_duyet, mat_khau, sha_tham_so: await sha256HexWeb(tsc) }));
  };
  $("#vj-duyet").addEventListener("submit", (e) => e.preventDefault()); // Enter trong form không tự gửi
  $("#vj-duyet").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-vd-act]");
    if (!b || b.disabled || !d || !d.viec) return;
    if (b.dataset.vdAct === "duyet") guiDuyet();
    else if (b.dataset.vdAct === "tai-lai") taiViec(); // tham_so_chuan mới về → veDuyet tự vẽ lại khung
    else if (b.dataset.vdAct === "kiem-loai") { // §4.8: chấm lại / gỡ Loại xong → kiểm lại rồi vẽ lại khung
      if (dangGuiViec.has(id)) return;
      luotKiem++; loaiDangKiem = false; // bỏ lượt đang chạy (nếu có) để lượt mới chạy ngay; kết quả lượt cũ bị bỏ
      loaiDuyet = null; boKhungDuyet(); veDuyet();
    }
    else if (b.dataset.vdAct === "tu-choi" && confirm("Từ chối việc này?")) hanhDong("tu-choi");
  });

  // Trả lời phiên sống (W-6): kiểm câu hỏi chưa đổi + chữ + mật khẩu → lấy mật khẩu ra rồi xoá ô NGAY → khoá khung →
  // gửi (hanhDong đặt dangGuiViec trước await). Không await nào trước khi khoá. Chữ giữ lại trong ô (sai mật khẩu gõ lại được).
  // idx: chỉ số nút (number) hoặc null = gửi ô chữ.
  const guiTraLoi = (idx) => {
    if (dangGuiViec.has(id) || tk !== phienViec || !d || !d.viec || !khungTlMo) return;
    const v = d.viec;
    if (khoaCauHoi(v) !== khungTlKhoa) { boKhungTraLoi(); veTraLoi(); toast("⚠ Câu hỏi vừa đổi — đọc lại rồi trả lời"); return; }
    const k = nutTraLoi(v.cau_hoi, dotBatViec, LOAI_TON_TIEN.includes(v.loai), v.phien_song === true);
    let tra_loi;
    if (idx === null) {
      const oChu = $("#vtl-chu");
      if (!k.o_chu || !oChu) return;
      tra_loi = oChu.value;
      const sai = kiemChuTraLoi(tra_loi);
      if (sai) { toast("⚠ " + sai); oChu.focus(); return; }
    } else {
      const n = k.nut[idx];
      if (!n) return;
      tra_loi = n.gia_tri;
    }
    const body = { tra_loi };
    const ma = maCauHoi(v); // đã kiểm khoaCauHoi (gồm ma) khớp khung đang hiện ở trên → đúng mã câu hỏi người dùng đang đọc
    if (ma) body.ma_cau_hoi = ma;
    if (k.can_mat_khau) {
      const oMk = $("#vtl-mk");
      if (!oMk || !oMk.value) { toast("⚠ Nhập mật khẩu để gửi trả lời"); if (oMk) oMk.focus(); return; }
      body.mat_khau = oMk.value;
      oMk.value = "";
    }
    khoaKhungTraLoi(true);
    hanhDong("tra-loi", body);
  };
  $("#vj-tra-loi").addEventListener("submit", (e) => e.preventDefault()); // Enter trong form không tự gửi
  $("#vj-tra-loi").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b || b.disabled) return;
    if (b.dataset.vtlNut !== undefined) guiTraLoi(Number(b.dataset.vtlNut));
    else if (b.dataset.vtlAct === "gui") guiTraLoi(null);
  });

  // Chỉ đạo: kiểm chữ + mật khẩu → lấy mật khẩu ra rồi xoá ô NGAY → gửi. Chữ chỉ xoá khi gửi thành công.
  const guiChiDao = (ngat) => {
    if (dangGuiViec.has(id) || tk !== phienViec || !d || !d.viec) return;
    const oChu = $("#vcd-chu"), oMk = $("#vcd-mk");
    if (!oChu || !oMk) return;
    const noi_dung = oChu.value;
    const sai = kiemChuTraLoi(noi_dung);
    if (sai) { toast("⚠ " + sai.replace("Câu trả lời", "Chỉ đạo")); oChu.focus(); return; }
    if (!oMk.value) { toast("⚠ Nhập mật khẩu để gửi chỉ đạo"); oMk.focus(); return; }
    if (ngat && !confirm("Ngắt ngay phiên đang chạy (dừng cả render/voice)? Sau đó bấm Xin duyệt lại → Duyệt để chạy lại theo chỉ đạo.")) return;
    const mat_khau = oMk.value;
    oMk.value = "";
    hanhDong("nhan-tin", { noi_dung, ngat, mat_khau }).then((r) => {
      if (tk !== phienViec || !r || r.status === 409) return;
      const o = $("#vcd-chu");
      if (o) o.value = "";
      if (ngat) toast("⏹ Đã ngắt — bấm ↻ Xin duyệt lại rồi duyệt để chạy lại theo chỉ đạo");
      else if (r.luu_cho_lan_sau) toast("💾 Đã ghi chỉ đạo — lần chạy tiếp sẽ làm theo");
    });
  };
  $("#vj-chi-dao").addEventListener("submit", (e) => e.preventDefault());
  $("#vj-chi-dao").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-vcd-act]");
    if (!b || b.disabled) return;
    guiChiDao(b.dataset.vcdAct === "ngat");
  });

  // Một listener ủy quyền cho cả khung (nội dung vẽ lại liên tục, không gắn lại mỗi lần).
  $("#vj-nd").addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b || b.disabled || !d || !d.viec) return;
    if (b.dataset.vjAct) {
      const act = b.dataset.vjAct;
      if (act === "huy" && !confirm("Huỷ việc này?")) return;
      if (act === "tu-choi" && !confirm("Từ chối việc này?")) return;
      hanhDong(act);
    } else if (b.dataset.vjTl !== undefined) {
      // nút trong #vj-nd chỉ dành cho việc KHÔNG phiên sống, không tốn tiền (phiên sống dùng khung #vj-tra-loi có mật khẩu)
      const laTt = LOAI_TON_TIEN.includes(d.viec.loai);
      const n = nutTraLoi(d.viec.cau_hoi, dotBatViec, laTt, false).nut[Number(b.dataset.vjTl)];
      if (n && !nutChoViecTonTien(d.viec).anTraLoi && d.viec.phien_song !== true) {
        const ma = maCauHoi(d.viec);
        hanhDong("tra-loi", ma ? { tra_loi: n.gia_tri, ma_cau_hoi: ma } : { tra_loi: n.gia_tri });
      }
    } else if (b.dataset.vjXemLog) {
      const el = $("#vj-log");
      if (el) el.scrollIntoView({ block: "start", behavior: "smooth" }); // không dùng <a href="#…">: đổi hash sẽ chạy router
    } else if (b.dataset.vjGoiY === "douyin_uid") {
      const uid = String((docJsonViec(d.viec.tham_so) || {}).uid || "");
      if (!RE_UID_VIEC.test(uid)) return;
      const moi = await taoViec("douyin_uid", { uid }, b);
      if (tk === phienViec && moi) location.hash = `#/viec/${moi}`;
    }
  });

  let nhip = 0;
  const lamMoi = () => {
    const tt = d && d.viec && d.viec.trang_thai;
    if (logDangSong(d && d.viec)) taiLog();
    if (!d || TT_MO.includes(tt)) taiViec();
  };
  viecTrang = {
    lamMoi,
    timers: [setInterval(() => {
      if (!tabHien()) return;
      nhip++;
      const tt = d && d.viec && d.viec.trang_thai;
      if (logDangSong(d && d.viec)) taiLog();                   // log 3 s khi đang chạy / phiên sống đang hỏi
      if (nhip % 2 === 0 && (!d || TT_MO.includes(tt))) taiViec(); // trạng thái ~6 s khi việc còn mở
    }, 3000)],
  };
  await taiViec();
  await taiLog();
}

// ---------- khối việc trong trang chi tiết SP (#viec-sp, dưới #buoc8) ----------
// form: form tạo việc đợt 4 đang mở ({loai:"muse_clip", du_an, nhan, mau, thoi_luong} | {loai:"poster_len_lich", folder_id, so_video_ngay});
// folders: danh sách folder Poster (null = chưa tải), foldersLoi, dangTaiFolder: khoá tải.
const SP_VIEC_MOI = () => ({ ds: null, loi: "", duAn: null, duAnLoi: "", chon: "", luaChon: [], dangTaiDuAn: false,
  form: null, folders: null, foldersLoi: "", dangTaiFolder: false, wmDs: null, dangTaiDm: false });
const spViec = { phien: -1, i: null, ht: -1, ...SP_VIEC_MOI() };

async function taiViecSp(phien, uid) {
  try {
    const [ds, sk] = await Promise.allSettled([api(`viec?uid=${encodeURIComponent(uid)}&gioi_han=10`), api("viec/suc-khoe")]);
    if (phien !== phienCT || spViec.phien !== phien) return;
    if (sk.status === "fulfilled" && Number.isInteger(sk.value.dot_bat)) dotBatViec = sk.value.dot_bat;
    if (ds.status === "fulfilled") { spViec.ds = Array.isArray(ds.value.viec) ? ds.value.viec : []; spViec.loi = ""; }
    else { spViec.ds = []; spViec.loi = (ds.reason && ds.reason.message) || "lỗi"; }
  } catch (err) { spViec.ds = []; spViec.loi = err.message; }
  veKhoiViecSp();
}

function veKhoiViecSp() {
  if (spViec.phien !== phienCT) return;
  const box = $("#viec-sp");
  if (!box || !spViec.i) return;
  const i = spViec.i;
  const g = goiYViec(spViec.ht, i, dotBatViec);
  const mo = (spViec.ds || []).filter((v) => v && TT_MO.includes(v.trang_thai));
  const ganDay = (spViec.ds || []).filter((v) => v && !TT_MO.includes(v.trang_thai)).slice(0, 3);
  const dangTao = (loai) => [...dangGuiViec].some((k) => k.startsWith(`tao:${loai}|`));
  // W-7: form taovideo — tự chọn đợt quay A khi máy nhà chỉ có đúng 1 dự án (làm 1 lần, người dùng đổi được nếu có hộp chọn).
  const f = spViec.form;
  if (f && f.loai === "taovideo" && !f.daTuChonA && Array.isArray(spViec.duAn)) {
    f.daTuChonA = true;
    f.du_an_a = duAnATuDong(spViec.duAn, f.du_an_a);
  }
  let chon = "";
  if (spViec.chon) {
    if (spViec.duAnLoi) chon = `<p class="err">⚠ ${esc(spViec.duAnLoi)}</p>`;
    else if (!spViec.duAn) chon = `<p class="small muted">Đang hỏi máy nhà danh sách dự án…</p>`;
    else {
      chon = spViec.luaChon.length
        ? `<div class="small muted">Chọn cho ${esc(tenLoaiViec(spViec.chon))}:</div><div class="row vs-chon">${spViec.luaChon.map((x, k) =>
          `<button class="btn ghost sm" data-vs-tao="${k}"${x.tat ? " disabled" : ""}${dangTao(x.loai) ? " disabled" : ""}>${esc(x.nhan)}</button>`).join("")}</div>`
        : `<p class="small muted">Máy nhà chưa có dự án phù hợp cho ${esc(tenLoaiViec(spViec.chon))}.</p>`;
    }
  }
  box.innerHTML = `<div class="vs-dau"><b>⚙ Việc trên máy nhà</b> <a href="#/viec" class="small">Tất cả việc →</a></div>
    ${spViec.ds === null ? `<p class="small muted">Đang hỏi bộ chạy việc…</p>`
      : spViec.loi ? `<p class="small err">⚠ Bộ chạy việc: ${esc(spViec.loi)}</p>`
      : mo.length || ganDay.length ? `<div class="vt-ds">${mo.concat(ganDay).map(theViecHtml).join("")}</div>` : ""}
    ${g.nut.length ? `<div class="row vs-nut">${g.nut.map((n) => `<button class="btn sm" data-vs-loai="${esc(n.loai)}"${dangTao(n.loai) || mo.some((v) => v.loai === n.loai) ? " disabled" : ""}>▶ ${esc(n.nhan)}</button>`).join("")}</div>` : ""}
    ${g.ghi_chu ? `<p class="small muted">${esc(g.ghi_chu)}</p>` : ""}
    ${spViec.form ? formViecSpHtml(spViec.form, { folders: spViec.folders, loi: spViec.foldersLoi, khoa: dangTao(spViec.form.loai),
      duAn: spViec.duAn, duAnLoi: spViec.duAnLoi, wm: spViec.wmDs }) : chon}`;
}

// Form taovideo (W-6): danh sách dự án (dùng chung cache spViec.duAn) + watermark từ /api/viec/danh-muc.
async function taiDuAnTaovideo(phien) {
  if (spViec.duAn || spViec.dangTaiDuAn || spViec.phien !== phien) return;
  spViec.dangTaiDuAn = true; // khoá TRƯỚC await
  spViec.duAnLoi = "";
  try {
    const r = await api(`viec/du-an/${encodeURIComponent(spViec.i.uid)}`);
    if (phien !== phienCT || spViec.phien !== phien) return;
    spViec.duAn = (Array.isArray(r.du_an) ? r.du_an : []).filter((p) => p && RE_DU_AN_VIEC.test(String(p.ma)));
  } catch (err) {
    if (phien !== phienCT || spViec.phien !== phien) return;
    spViec.duAnLoi = (err && err.message) || "lỗi";
  } finally {
    if (spViec.phien === phien) spViec.dangTaiDuAn = false;
  }
  veKhoiViecSp();
}
async function taiWmTaovideo(phien) {
  if (spViec.wmDs || spViec.dangTaiDm || spViec.phien !== phien) return;
  spViec.dangTaiDm = true; // khoá TRƯỚC await
  let dm = null;
  try { dm = await api("viec/danh-muc"); } catch { /* lỗi → dùng danh sách mặc định */ }
  if (phien !== phienCT || spViec.phien !== phien) return;
  spViec.dangTaiDm = false;
  spViec.wmDs = wmTaovideo(dm);
  veKhoiViecSp();
}

// Danh sách folder Poster cho form poster_len_lich (tải 1 lần mỗi trang SP; lỗi → nút Thử lại).
async function taiFolderPoster(phien) {
  if (spViec.dangTaiFolder || spViec.folders || spViec.phien !== phien) return;
  spViec.dangTaiFolder = true; // khoá TRƯỚC await
  spViec.foldersLoi = "";
  try {
    const r = await api("viec/poster/folders");
    if (phien !== phienCT || spViec.phien !== phien) return;
    spViec.folders = locFolderPoster(r);
  } catch (err) {
    if (phien !== phienCT || spViec.phien !== phien) return;
    spViec.foldersLoi = (err && err.message) || "lỗi";
  } finally {
    if (spViec.phien === phien) spViec.dangTaiFolder = false;
  }
  veKhoiViecSp();
}

async function chonDuAnSp(loai, phien) {
  spViec.chon = loai;
  spViec.luaChon = [];
  spViec.form = null;
  const dung = () => {
    const ds = spViec.duAn || [];
    spViec.luaChon = loai === "voice_pv" || loai === "voice_genmax"
      ? ds.flatMap((p) => (Array.isArray(p.me) ? p.me : []).map((me) => ({ loai, nhan: `${p.ten || p.ma} · mẻ ${me}`, tham_so: { uid: spViec.i.uid, du_an: p.ma, me } })))
      : loai === "muse_clip" // chọn dự án → mở form chọn mẫu/thời lượng
        ? ds.map((p) => ({ loai, nhan: String(p.ten || p.ma), mo_form: true, tham_so: { uid: spViec.i.uid, du_an: p.ma } }))
        : ds.map((p) => ({ loai, nhan: `${p.ten || p.ma}${p.co_captions === false ? " (chưa có captions)" : ""}`, tat: p.co_captions === false, tham_so: { uid: spViec.i.uid, du_an: p.ma } }));
  };
  if (spViec.duAn) { dung(); veKhoiViecSp(); return; }
  veKhoiViecSp();
  if (spViec.dangTaiDuAn) return;
  spViec.dangTaiDuAn = true; // khoá TRƯỚC await
  try {
    const r = await api(`viec/du-an/${encodeURIComponent(spViec.i.uid)}`);
    if (phien !== phienCT || spViec.phien !== phien) return;
    spViec.duAn = (Array.isArray(r.du_an) ? r.du_an : []).filter((p) => p && /^[0-9a-f]{12}$/.test(String(p.ma)));
    spViec.duAnLoi = "";
    dung();
  } catch (err) {
    if (phien !== phienCT || spViec.phien !== phien) return;
    spViec.duAnLoi = err.message;
  } finally {
    if (spViec.phien === phien) spViec.dangTaiDuAn = false;
  }
  veKhoiViecSp();
}

// Gọi sau veBuoc() (app.js). i: info SP + co_douyin; ds: kết quả tinhBuoc; phien: phienCT của trang.
function veViecSp(i, ds, phien) {
  if (phien !== phienCT || !laChu()) return;
  const box = $("#viec-sp");
  if (!box) return;
  const moi = spViec.phien !== phien;
  if (moi) {
    Object.assign(spViec, { phien, ...SP_VIEC_MOI() });
    // Giá trị form đổi → lưu vào spViec.form (khối vẽ lại khi danh sách việc về, không mất lựa chọn).
    // Nghe cả "input": ô số video/ngày chỉ bắn "change" khi rời ô — vẽ lại giữa chừng sẽ mất số đang gõ.
    const doiForm = (e) => {
      const t = e.target, f = spViec.form;
      if (!f || !t || !t.dataset || spViec.phien !== phien) return;
      if (t.dataset.vsMau) {
        const s = new Set(Array.isArray(f.mau) ? f.mau : []);
        if (t.checked) s.add(t.dataset.vsMau); else s.delete(t.dataset.vsMau);
        f.mau = [...s];
      } else if (t.dataset.vsTl) { if (t.checked) f.thoi_luong = Number(t.dataset.vsTl); }
      else if ("vsFolder" in t.dataset) f.folder_id = t.value;
      else if ("vsSo" in t.dataset) f.so_video_ngay = t.value;
      else if ("vsA" in t.dataset) f.du_an_a = t.value;
      else if ("vsB" in t.dataset) { f.du_an_b = t.value; f.loi_b = ""; }
      else if ("vsWm" in t.dataset) {
        f.wm = t.value;
        const nhac = $(".vs-wm-nhac", box); // nhắc logo đang chọn ngay, không chờ vẽ lại
        if (nhac) nhac.innerHTML = wmNhacHtml(f.wm);
      }
      else if ("vsGia" in t.dataset) f.gia = t.value;
    };
    box.addEventListener("change", doiForm);
    box.addEventListener("input", doiForm);
    box.addEventListener("click", async (e) => {
      const b = e.target.closest("button");
      if (!b || b.disabled || spViec.phien !== phien) return;
      if (b.dataset.vsLoai) {
        const loai = b.dataset.vsLoai;
        const m = LOAI_VIEC_SP[loai];
        if (!m) return;
        spViec.form = null;
        if (loai === "poster_len_lich") { // không cần dự án: mở form folder + số video/ngày
          spViec.chon = "";
          spViec.form = { loai, folder_id: "", so_video_ngay: 1 };
          veKhoiViecSp();
          taiFolderPoster(phien);
          return;
        }
        if (loai === "taovideo") { // form chọn A/B/watermark/giá; tạo xong chờ duyệt 1 lần cho cả phiên
          spViec.chon = "";
          // W-7 mặc định: B "tu_tim", giá lấy từ SP nếu chắc chắn hợp lệ; watermark để trống — người dùng tự chọn.
          spViec.form = { loai, du_an_a: "", du_an_b: "tu_tim", wm: "", gia: giaTuInfoSp(spViec.i), loi_b: "" };
          veKhoiViecSp();
          taiDuAnTaovideo(phien);
          taiWmTaovideo(phien);
          return;
        }
        if (m.can.includes("du_an")) { chonDuAnSp(loai, phien); return; }
        const id = await taoViec(loai, { uid: spViec.i.uid }, b);
        if (phien !== phienCT) return;
        if (id) location.hash = `#/viec/${id}`; else veKhoiViecSp(); // lỗi: vẽ lại để mở khoá nút
      } else if (b.dataset.vsTao !== undefined) {
        const x = spViec.luaChon[Number(b.dataset.vsTao)];
        if (!x || x.tat) return;
        if (x.mo_form) {
          spViec.form = { loai: x.loai, du_an: x.tham_so.du_an, nhan: x.nhan, mau: [], thoi_luong: 10 };
          veKhoiViecSp();
          return;
        }
        const id = await taoViec(x.loai, x.tham_so, b);
        if (phien !== phienCT) return;
        if (id) location.hash = `#/viec/${id}`; else veKhoiViecSp();
      } else if (b.dataset.vsGui) {
        const f = spViec.form;
        if (!f || f.loai !== b.dataset.vsGui) return;
        const wmDs = spViec.wmDs || WM_TAOVIDEO_WEB;
        // W-7: gửi đúng logo người dùng chọn; chưa chọn / không còn trong danh sách → thamSoTaovideo báo "Chọn watermark".
        const r = f.loai === "muse_clip" ? thamSoMuse(String(spViec.i.uid || ""), f.du_an, f.mau, f.thoi_luong)
          : f.loai === "taovideo" ? thamSoTaovideo(String(spViec.i.uid || ""), f.du_an_a, f.du_an_b, wmDs.includes(f.wm) ? f.wm : "", f.gia)
          : thamSoPoster(f.folder_id, f.so_video_ngay);
        if (r.loi) { toast("⚠ " + r.loi); return; }
        // taovideo "tu_tim": máy nhà trả 400 khi 0 hoặc ≥2 dự án có takes/ (§7.10) → bắt chọn B trong danh sách.
        const khiLoi = (err) => {
          if (f.loai !== "taovideo" || f.du_an_b !== "tu_tim" || spViec.form !== f || spViec.phien !== phien) return;
          const msg = String((err && err.message) || "");
          if (!/takes|du_an_b|dự án B/i.test(msg)) return;
          f.loi_b = msg.slice(0, 300);
          f.du_an_b = "";
        };
        const id = await taoViec(f.loai, r.tham_so, b, { khiLoi });
        if (phien !== phienCT) return;
        if (id) location.hash = `#/viec/${id}`; else veKhoiViecSp();
      } else if (b.dataset.vsAn) {
        spViec.form = null;
        veKhoiViecSp();
      } else if (b.dataset.vsFolderLai) {
        spViec.folders = null;
        spViec.foldersLoi = "";
        veKhoiViecSp();
        taiFolderPoster(phien);
      }
    });
  }
  spViec.i = i;
  spViec.ht = buocHienTai(ds);
  veKhoiViecSp();
  if (moi && RE_UID_VIEC.test(String(i.uid || ""))) taiViecSp(phien, i.uid);
  else if (moi) { spViec.ds = []; veKhoiViecSp(); }
}
