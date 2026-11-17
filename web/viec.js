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
};
// Đợt mở của từng loại + tham số web phải chọn (uid lấy từ SP; du_an/me chọn từ /api/viec/du-an/<uid>).
const LOAI_VIEC_SP = {
  phan_tich_uid: { dot: 3, can: ["uid"] }, douyin_uid: { dot: 3, can: ["uid"] },
  voice_pv: { dot: 3, can: ["uid", "du_an", "me"] }, poster_day_folder: { dot: 3, can: ["uid", "du_an"] },
  muse_clip: { dot: 4, can: ["uid", "du_an"] }, voice_genmax: { dot: 4, can: ["uid", "du_an", "me"] },
  poster_len_lich: { dot: 4, can: [] }, taovideo: { dot: 5, can: ["uid"] },
};
const TT_VIEC = {
  cho: "Đang chờ", dang_chay: "Đang chạy", can_tra_loi: "Cần bạn", cho_duyet: "Chờ duyệt",
  xong: "Xong", loi: "Lỗi", huy: "Đã huỷ",
};
const TT_MO = ["cho", "dang_chay", "can_tra_loi", "cho_duyet"];
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

// Nút trả lời cho câu hỏi đang chờ → [{nhan, gia_tri}]. Đợt 3 chỉ có nút: cau_hoi (chữ tự do) → [] ở MỌI đợt
// vì đợt 5 dùng khung chữ + mật khẩu, không phải nút.
function nutTraLoi(cauHoi, dotBat) {
  const c = docJsonViec(cauHoi);
  if (!c || typeof c !== "object" || Array.isArray(c)) return [];
  if (c.loai === "chon") {
    const da = new Set();
    return (Array.isArray(c.lua_chon) ? c.lua_chon : [])
      .filter((x) => typeof x === "string" && x.trim() && x.length <= TRA_LOI_TOI_DA_WEB && !RE_DIEU_KHIEN.test(x) && !da.has(x) && da.add(x))
      .slice(0, 6).map((x) => ({ nhan: x, gia_tri: x }));
  }
  if (c.loai === "viec_tay") return [{ nhan: "✓ Tôi đã làm xong", gia_tri: "da_lam_xong" }];
  if (c.loai === "khong_ro") return [{ nhan: "▶ Tiếp tục", gia_tri: "tiep_tuc" }];
  void dotBat; // cau_hoi: đợt < 5 không có ô chữ; đợt 5 (W-6) thêm khung chữ riêng
  return [];
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
    7: "👉 Kiểm video ở tab ✅ Duyệt.",
  };
  if (ht === 2) { them("phan_tich_uid"); if (i.da_phan_tich && !coDouyin) them("douyin_uid"); }
  else if (ht === 4) them("muse_clip");
  else if (ht === 5) { them("voice_pv"); them("voice_genmax"); }
  else if (ht === 6) them("taovideo");
  else if (ht === 8) { them("poster_day_folder"); them("poster_len_lich"); }
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

function theViecHtml(v) {
  const x = v || {};
  const tt = nhanTrangThai(x.trang_thai);
  const id = laIdViec(x.id) ? x.id : "";
  const ts = dongThamSo(x.tham_so);
  const ch = docJsonViec(x.cau_hoi);
  const goiY = x.trang_thai === "can_tra_loi" && ch && ch.noi_dung ? `<div class="small vt-hoi">❓ ${esc(String(ch.noi_dung).slice(0, 160))}</div>` : "";
  const banner = x.can_ban ? `<div class="small vt-can-ban">⚠ ${esc(x.can_ban)}</div>` : "";
  const inner = `<div class="vt-dong1"><span class="tt ${tt.lop}">${esc(tt.nhan)}</span> <b>${esc(tenLoaiViec(x.loai))}</b></div>
      ${ts ? `<div class="small muted vt-ts">${esc(ts)}</div>` : ""}${goiY}${banner}
      <div class="small muted">${esc(x.tao_boi || "?")} · ${esc(gioViec(x.tao_luc))}${x.lan_thu > 1 ? ` · lần ${esc(x.lan_thu)}` : ""}</div>`;
  return id ? `<a class="vt" href="#/viec/${esc(id)}">${inner}</a>` : `<div class="vt">${inner}</div>`;
}

function dsNhomHtml(g) {
  const muc = [["can_ban", "👉 Cần bạn"], ["dang_chay", "⏳ Đang chạy"], ["dang_cho", "🕒 Đang chờ"], ["gan_day", "🗂 Gần đây"]];
  const html = muc.filter(([k]) => g[k] && g[k].length)
    .map(([k, ten]) => `<h3 class="vt-nhom">${ten} <span class="small muted">(${g[k].length})</span></h3><div class="vt-ds">${g[k].map(theViecHtml).join("")}</div>`).join("");
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

const NHAN_XONG = { huy: "Đã huỷ", "tu-choi": "Đã từ chối", "chay-tiep": "▶ Đã cho chạy tiếp", "chay-lai": "↻ Đã tạo việc chạy lại", "tra-loi": "✓ Đã gửi trả lời" };
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
  if (v.can_ban) dong.push(`<div class="vj-can-ban">⚠ ${esc(v.can_ban)}</div>`);
  if (v.ghi_chu) dong.push(`<p class="small muted">📝 ${esc(v.ghi_chu)}</p>`);
  if (v.loi) dong.push(`<div class="vj-loi">⚠ ${esc(v.loi)}</div>`);

  // Khung trả lời bằng nút.
  if (v.trang_thai === "can_tra_loi") {
    const nut = nutTraLoi(ch, opt.dotBat);
    const loai = ch && ch.loai;
    const tieuDe = loai === "viec_tay" ? "👉 Việc của bạn" : loai === "khong_ro" ? "❓ Agent dừng mà không rõ lý do" : "❓ Cần bạn trả lời";
    dong.push(`<div class="vj-hoi">
        <div class="vj-hoi-dau"><b>${tieuDe}</b></div>
        ${ch && ch.noi_dung ? `<div class="vj-hoi-nd">${esc(ch.noi_dung)}</div>` : ""}
        ${nut.length ? "" : `<p class="small muted">Câu hỏi này cần trả lời bằng chữ — đợt 3 chỉ trả lời bằng nút, hãy làm trên máy nhà hoặc Huỷ.</p>`}
        <div class="row vj-hoi-nut">${nut.map((n, k) => `<button class="btn sm" data-vj-tl="${k}"${dis}>${esc(n.nhan)}</button>`).join("")}
          <button class="btn ghost sm" data-vj-act="huy"${dis}>Huỷ việc</button></div>
      </div>`);
  }
  if (v.trang_thai === "cho_duyet") {
    dong.push(`<div class="vj-hoi"><b>⏳ Việc chờ duyệt</b>${v.uoc_tinh ? `<div class="vj-hoi-nd">${esc(v.uoc_tinh)}</div>` : ""}
      <p class="small muted">Duyệt trên web mở ở đợt 4.</p>
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
  if (v.trang_thai === "loi" && v.co_the_chay_tiep) nut.push(`<button class="btn sm" data-vj-act="chay-tiep"${dis}>▶ Chạy tiếp</button>`);
  if (v.trang_thai === "loi" || v.trang_thai === "huy") nut.push(`<button class="btn ghost sm" data-vj-act="chay-lai"${dis}>↻ Chạy lại</button>`);
  if (nut.length) dong.push(`<div class="row vj-nut">${nut.join("")}${opt.khoa ? `<span class="small muted">đang gửi…</span>` : ""}</div>`);
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
    datHuyHieuViec(demCanBan(r && r.dem));
  } catch { /* bộ chạy việc tắt: không hiện huy hiệu */ }
  finally { huyHieuDangTai = false; }
}

// Tạo việc. Khoá theo (loai, tham_so) TRƯỚC await. Trả id việc (mới hoặc trùng) hoặc "".
async function taoViec(loai, tham_so, nut) {
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
  } catch (err) { toast("⚠ " + err.message); return ""; }
  finally {
    dangGuiViec.delete(khoa);
    if (nut && nut.isConnected) { nut.disabled = false; nut.textContent = nhanCu; }
  }
}

// ---------- #/viec ----------
async function renderViec() {
  if (!laChu()) { $("#app").innerHTML = `<p class="center muted">Trang này chỉ dành cho chủ kho. <a href="#/">← Về kho</a></p>`; return; }
  const tk = phienViec;
  $("#app").innerHTML = `<p><a href="#/" class="small">← Về kho</a></p>
    <div class="vt-khung">
      <div class="row" style="justify-content:space-between"><h2 class="sk-tieu-de">⚙ Việc chạy trên máy nhà</h2></div>
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

  let dangLamMoi = false;
  const lamMoi = async () => {
    if (dangLamMoi || tk !== phienViec) return;
    dangLamMoi = true;
    try {
      const [sk, ds] = await Promise.allSettled([api("viec/suc-khoe"), api("viec?gioi_han=50")]);
      if (tk !== phienViec) return;
      const tt = $("#vt-tom-tat"), dsEl = $("#vt-ds");
      if (sk.status === "fulfilled") {
        if (Number.isInteger(sk.value.dot_bat)) dotBatViec = sk.value.dot_bat;
        if (tt) tt.innerHTML = tomTatHtml(sk.value);
      } else if (tt) tt.innerHTML = `<div class="sk-banner">🔴 Bộ chạy việc không trả lời: ${esc(sk.reason && sk.reason.message)}</div>`;
      if (ds.status === "fulfilled") {
        const list = Array.isArray(ds.value.viec) ? ds.value.viec : [];
        if (dsEl) dsEl.innerHTML = dsNhomHtml(nhomViec(list));
        capNhatHuyHieuViec(); // đếm toàn kho qua tom_tat=1, không đếm từ 50 việc trên trang
      } else if (dsEl) dsEl.innerHTML = `<p class="err">⚠ Không lấy được danh sách việc: ${esc(ds.reason && ds.reason.message)}</p>`;
    } finally { dangLamMoi = false; }
  };
  viecTrang = { lamMoi, timers: [setInterval(() => { if (tabHien()) lamMoi(); }, 5000)] };
  await lamMoi();
}

// ---------- #/viec/<id> ----------
async function renderViecChiTiet(id) {
  if (!laChu()) { $("#app").innerHTML = `<p class="center muted">Trang này chỉ dành cho chủ kho. <a href="#/">← Về kho</a></p>`; return; }
  if (!laIdViec(id)) { $("#app").innerHTML = `<p class="center">Mã việc không hợp lệ. <a href="#/viec">← Việc</a></p>`; return; }
  const tk = phienViec;
  $("#app").innerHTML = `<p><a href="#/viec" class="small">← Việc</a></p>
    <div class="vj">
      <div id="vj-nd"><p class="muted">Đang tải…</p></div>
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

  const ve = () => {
    const nd = $("#vj-nd");
    if (!nd || !d) return;
    nd.innerHTML = chiTietViecHtml(d, { dotBat: dotBatViec, khoa: dangGuiViec.has(id), md: mdSach, canhBao: canhBaoViec });
  };
  const taiViec = async () => {
    if (viecDangTai || tk !== phienViec) return;
    viecDangTai = true;
    try {
      const r = await api(`viec/${id}`);
      if (tk !== phienViec) return;
      const ttCu = d && d.viec && d.viec.trang_thai;
      d = r;
      ve();
      if (ttCu === "dang_chay" && r.viec && r.viec.trang_thai !== "dang_chay") taiLog(); // lấy nốt log cuối
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
    const chay = !d || !d.viec || d.viec.trang_thai === "dang_chay";
    if (d && d.viec && d.viec.trang_thai === "dang_chay") logDocLai = 0; // chạy lại/chạy tiếp rồi dừng → được hẹn lại từ đầu
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
        else if (!henLog && canDocLaiLog(d && d.viec && d.viec.trang_thai, cuoi, logDocLai)) {
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

  const hanhDong = async (act, body) => {
    if (dangGuiViec.has(id)) return;
    dangGuiViec.add(id); // khoá TRƯỚC await
    ve();
    let chuyen = false;
    try {
      const r = await api(`viec/${id}/${act}`, body || {});
      if (tk !== phienViec) return;
      const k = ketQuaHanhDong(act, r, id);
      if (r.status !== 409) canhBaoViec = k.canhBao;
      toast(k.toast);
      if (k.chuyen) { chuyen = true; location.hash = `#/viec/${k.chuyen}`; }
    } catch (err) { if (tk === phienViec) toast("⚠ " + err.message); }
    finally {
      dangGuiViec.delete(id);
      if (tk === phienViec && !chuyen) { ve(); taiViec(); }
    }
  };

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
      const n = nutTraLoi(d.viec.cau_hoi, dotBatViec)[Number(b.dataset.vjTl)];
      if (n) hanhDong("tra-loi", { tra_loi: n.gia_tri });
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
    if (tt === "dang_chay") taiLog();
    if (!d || TT_MO.includes(tt)) taiViec();
  };
  viecTrang = {
    lamMoi,
    timers: [setInterval(() => {
      if (!tabHien()) return;
      nhip++;
      const tt = d && d.viec && d.viec.trang_thai;
      if (tt === "dang_chay") taiLog();                         // log 3 s khi đang chạy
      if (nhip % 2 === 0 && (!d || TT_MO.includes(tt))) taiViec(); // trạng thái ~6 s khi việc còn mở
    }, 3000)],
  };
  await taiViec();
  await taiLog();
}

// ---------- khối việc trong trang chi tiết SP (#viec-sp, dưới #buoc8) ----------
const spViec = { phien: -1, i: null, ht: -1, ds: null, loi: "", duAn: null, duAnLoi: "", chon: "", luaChon: [], dangTaiDuAn: false };

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
    ${chon}`;
}

async function chonDuAnSp(loai, phien) {
  spViec.chon = loai;
  spViec.luaChon = [];
  const dung = () => {
    const ds = spViec.duAn || [];
    spViec.luaChon = loai === "voice_pv"
      ? ds.flatMap((p) => (Array.isArray(p.me) ? p.me : []).map((me) => ({ loai, nhan: `${p.ten || p.ma} · mẻ ${me}`, tham_so: { uid: spViec.i.uid, du_an: p.ma, me } })))
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
    Object.assign(spViec, { phien, ds: null, loi: "", duAn: null, duAnLoi: "", chon: "", luaChon: [], dangTaiDuAn: false });
    box.addEventListener("click", async (e) => {
      const b = e.target.closest("button");
      if (!b || b.disabled || spViec.phien !== phien) return;
      if (b.dataset.vsLoai) {
        const loai = b.dataset.vsLoai;
        const m = LOAI_VIEC_SP[loai];
        if (!m) return;
        if (m.can.includes("du_an")) { chonDuAnSp(loai, phien); return; }
        const id = await taoViec(loai, { uid: spViec.i.uid }, b);
        if (phien !== phienCT) return;
        if (id) location.hash = `#/viec/${id}`; else veKhoiViecSp(); // lỗi: vẽ lại để mở khoá nút
      } else if (b.dataset.vsTao !== undefined) {
        const x = spViec.luaChon[Number(b.dataset.vsTao)];
        if (!x || x.tat) return;
        const id = await taoViec(x.loai, x.tham_so, b);
        if (phien !== phienCT) return;
        if (id) location.hash = `#/viec/${id}`; else veKhoiViecSp();
      }
    });
  }
  spViec.i = i;
  spViec.ht = buocHienTai(ds);
  veKhoiViecSp();
  if (moi && RE_UID_VIEC.test(String(i.uid || ""))) taiViecSp(phien, i.uid);
  else if (moi) { spViec.ds = []; veKhoiViecSp(); }
}
