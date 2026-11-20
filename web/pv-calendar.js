// Poster V2 trên web: trang Calendar (#/poster/calendar), phiếu W-P5, docs/poster-v2-tren-web.md §6.3–§6.5.
// Bê nguyên E:/tool/tiktok_poster_v2/src/desktop/pages/calendar.py (CalendarPage, _PlanDialog, _StatCard) + calendar_utils.py
// (đối chiếu bản Svelte a55d687 Calendar.svelte + calendar-utils.ts). Cùng chữ, nút, cột, hộp thoại; không thêm/bớt tính năng.
// Script thường, chung phạm vi với app.js/poster.js: mọi tên cấp đỉnh bắt đầu bằng "pvca" (luật P2-7). Khung gọi pvCaVe / pvCaDung.
// Dùng: pvApi, pvConSong, pvHop, pvThongBao (poster.js); esc, toast (app.js). CSP script-src 'self': chỉ addEventListener.
// Chỗ khác desktop có chủ ý: kết quả tải tháng về muộn (đã bấm ◀/▶/🔄 lần sau, hoặc đã rời trang) bị bỏ, không vẽ đè (kỷ luật
// tac-dung-phu-gan-phien-trang); desktop vẽ theo thứ tự trả về.
"use strict";

// --- pvca-thuan start ---
const pvcaTHANG = ["", "Tháng 1", "Tháng 2", "Tháng 3", "Tháng 4", "Tháng 5", "Tháng 6",
  "Tháng 7", "Tháng 8", "Tháng 9", "Tháng 10", "Tháng 11", "Tháng 12"]; // MONTH_NAMES calendar.py:55-58
const pvcaTHU = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]; // dow_labels calendar.py:316

const pvcaLaDoi = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
// bool(v) của Python: [] / {} / "" / 0 / None là sai.
function pvcaThat(v) {
  if (Array.isArray(v)) return v.length > 0;
  if (pvcaLaDoi(v)) return Object.keys(v).length > 0;
  return !!v;
}
// str(v) của Python cho giá trị JSON.
function pvcaStr(v) {
  if (v === null || v === undefined) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  return String(v);
}

// calendar_utils.extract_events_by_day
function pvcaSuKienTheoNgay(payload) {
  if (!pvcaLaDoi(payload)) return {};
  const e = payload.events_by_day;
  return pvcaLaDoi(e) ? e : {};
}

// calendar_utils.compute_stat_totals: khác "done"/"failed" đều tính là chờ, nên 4 thẻ cộng lại bằng tổng.
function pvcaTong(eventsByDay) {
  let total = 0, done = 0, failed = 0, pending = 0;
  for (const ds of Object.values(pvcaLaDoi(eventsByDay) ? eventsByDay : {})) {
    if (!Array.isArray(ds)) continue;
    for (const ev of ds) {
      if (!pvcaLaDoi(ev)) continue;
      total += 1;
      const st = (pvcaThat(ev.status) ? pvcaStr(ev.status) : "").trim().toLowerCase();
      if (st === "done") done += 1;
      else if (st === "failed") failed += 1;
      else pending += 1;
    }
  }
  return { total, done, pending, failed };
}

// calendar_utils.extract_time_from_scheduled_at: "YYYY-MM-DD HH:MM:SS" / "YYYY-MM-DDTHH:MM:SS" → "HH:MM".
function pvcaGio(s) {
  if (!s || typeof s !== "string") return "";
  const p = s.replaceAll("T", " ");
  const i = p.indexOf(" ");
  if (i < 0) return "";
  return Array.from(p.slice(i + 1)).slice(0, 5).join("");
}

// calendar_utils.event_display_title: caption → video_filename → folder_name → "Folder #id" → "(không có tên)".
function pvcaTieuDe(ev) {
  if (!pvcaLaDoi(ev)) return "";
  const cap = typeof ev.caption === "string" ? ev.caption.trim() : ev.caption;
  if (pvcaThat(cap)) return pvcaStr(cap);
  if (pvcaThat(ev.video_filename)) return pvcaStr(ev.video_filename);
  if (pvcaThat(ev.folder_name)) return pvcaStr(ev.folder_name);
  if (pvcaThat(ev.folder_id)) return `Folder #${pvcaStr(ev.folder_id)}`;
  return "(không có tên)";
}

// calendar_utils.event_display_account
function pvcaTaiKhoan(ev) {
  if (!pvcaLaDoi(ev)) return "";
  return pvcaThat(ev.account_name) ? pvcaStr(ev.account_name) : "";
}

// calendar_utils.format_day_cell_text: "24\n🟢110 🟡3 🔴1"; số 0 bỏ; không có sự kiện thì chỉ số ngày.
function pvcaChuO(day, events) {
  const t = pvcaTong({ _: pvcaThat(events) ? events : [] });
  const phan = [["🟢", "done"], ["🟡", "pending"], ["🔴", "failed"]].filter(([, k]) => t[k]).map(([d, k]) => `${d}${t[k]}`);
  return phan.length ? `${day}\n${phan.join(" ")}` : String(day);
}

const pvcaHai = (n) => String(n).padStart(2, "0");
const pvcaNgay = (y, m, d) => `${y}-${pvcaHai(m)}-${pvcaHai(d)}`; // f"{y}-{m:02d}-{d:02d}"
const pvcaSoNgay = (y, m) => new Date(y, m, 0).getDate();

// calendar.Calendar(firstweekday=0).monthdayscalendar(y, m): tuần bắt đầu thứ Hai, 0 = ô đệm.
function pvcaTuan(y, m) {
  const dau = (new Date(y, m - 1, 1).getDay() + 6) % 7; // T2 = 0 … CN = 6
  const o = Array(dau).fill(0);
  for (let d = 1; d <= pvcaSoNgay(y, m); d++) o.push(d);
  while (o.length % 7) o.push(0);
  const tuan = [];
  for (let i = 0; i < o.length; i += 7) tuan.push(o.slice(i, i + 7));
  return tuan;
}

// Danh sách sự kiện của 1 ngày như self._events_by_day.get(day_str, []) (không phải mảng → rỗng).
function pvcaDsNgay(eventsByDay, ngay) {
  const ds = pvcaLaDoi(eventsByDay) ? eventsByDay[ngay] : undefined;
  return Array.isArray(ds) ? ds : [];
}

// _render_day_detail: chỉ sự kiện "plan" có plan_id mới xoá được (DELETE /calendar/plans/{id}); "queue" quản ở trang Queue.
function pvcaIdKeHoach(items) {
  return (Array.isArray(items) ? items : []).filter((ev) => pvcaLaDoi(ev) && ev.kind === "plan" && ev.plan_id !== null && ev.plan_id !== undefined)
    .map((ev) => ev.plan_id);
}

// QSpinBox 0–999999: chữ không phải số → 0.
function pvcaSpin(v) {
  const n = Math.trunc(Number(v));
  return Number.isFinite(n) ? Math.min(999999, Math.max(0, n)) : 0;
}

// _PlanDialog.get_data
function pvcaDuLieuKeHoach(f) {
  const s = (x) => String(x ?? "").trim();
  return {
    title: s(f.title),
    scheduled_date: s(f.scheduled_date),
    scheduled_time: s(f.scheduled_time),
    folder_id: pvcaSpin(f.folder_id) || null,
    account_id: pvcaSpin(f.account_id) || null,
    notes: s(f.notes),
  };
}

// Ngày mặc định của hộp "+ Thêm kế hoạch" (_add_plan): ngày 1 của tháng đang xem, hoặc ngày đang chọn nếu hợp lệ trong tháng đó.
function pvcaNgayMacDinh(y, m, chon) {
  if (chon && chon >= 1 && chon <= pvcaSoNgay(y, m)) return pvcaNgay(y, m, chon);
  return pvcaNgay(y, m, 1);
}

// 4 thẻ thống kê (_StatCard).
function pvcaTheHtml(t) {
  const the = [["📊 TỔNG KẾ HOẠCH", t.total, "pv-lam"], ["✔️ ĐÃ ĐĂNG", t.done, "pv-xanh"], ["⏳ CHỜ ĐĂNG", t.pending, "pv-vang"], ["❌ THẤT BẠI", t.failed, "pv-do"]];
  return `<div class="pvca-the">${the.map(([nhan, so, mau]) =>
    `<div class="pv-the pvca-the-o ${mau}"><div class="pv-nho">${esc(nhan)}</div><div class="pvca-so">${esc(so)}</div></div>`).join("")}</div>`;
}

// Lưới tháng (_render_calendar): hàng T2–CN rồi các tuần; ô hôm nay viền xanh lá, ô đang chọn viền xanh dương.
function pvcaLuoiHtml(y, m, eventsByDay, chon, homNay) {
  const dau = pvcaTHU.map((t) => `<div class="pvca-thu">${esc(t)}</div>`).join("");
  const o = pvcaTuan(y, m).flat().map((d) => {
    if (d === 0) return `<div class="pvca-o pvca-dem"></div>`;
    const ds = pvcaDsNgay(eventsByDay, pvcaNgay(y, m, d));
    const lop = `${homNay && homNay.y === y && homNay.m === m && homNay.d === d ? " pvca-hom-nay" : ""}${chon === d ? " pvca-chon" : ""}`;
    return `<button type="button" class="pvca-o pvca-ngay${lop}" data-pvca-ngay="${esc(d)}"${ds.length ? ` title="${esc(`${ds.length} video`)}"` : ""}${
      chon === d ? ` aria-pressed="true"` : ""}>${esc(pvcaChuO(d, ds))}</button>`;
  }).join("");
  return `<div class="pvca-luoi">${dau}${o}</div>`;
}

// Khối "Chi tiết ngày" (_render_day_detail): bảng 4 cột Giờ / Account / Video/Folder / Trạng thái.
function pvcaChiTietHtml(y, m, eventsByDay, chon) {
  const ngay = chon ? pvcaNgay(y, m, chon) : "";
  const ds = chon ? pvcaDsNgay(eventsByDay, ngay) : [];
  const nhan = chon ? `Chi tiết ngày ${ngay}` : "Bấm vào một ngày để xem chi tiết";
  const dong = ds.map((ev) => {
    const e = pvcaLaDoi(ev) ? ev : {};
    return `<tr><td>${esc(pvcaGio(e.scheduled_at))}</td><td>${esc(pvcaTaiKhoan(e))}</td><td>${esc(pvcaTieuDe(e))}</td><td>${
      esc(pvcaThat(e.status) ? pvcaStr(e.status) : "")}</td></tr>`;
  }).join("");
  const coXoa = chon ? pvcaIdKeHoach(ds).length > 0 : false;
  return `<p class="pv-nho" id="pvca-nhan-ngay">${esc(nhan)}</p>
    <div class="pv-cuon"><table class="pv-bang"><thead><tr><th>Giờ</th><th>Account</th><th>Video/Folder</th><th>Trạng thái</th></tr></thead>
    <tbody>${dong}</tbody></table></div>
    ${coXoa ? `<button type="button" class="btn pvca-xoa" data-pvca="xoa">🗑️ Xóa kế hoạch đã chọn</button>` : ""}`;
}
// widgets/common.py _friendly_error: run_async đưa MỌI lỗi qua hàm này trước on_error (giữ chữ không dấu của bản gốc;
// cùng cách port với pv-settings.js/pv-logs.js/pv-views.js). Lỗi HTTP (có e.status) mang tên lớp "HTTPError" như requests.
function pvcaLoi(e) {
  const msg = String(e && e.message ? e.message : e);
  if (msg.includes("401")) return "Khong co quyen truy cap (401). Kiem tra API token trong .env.";
  if (msg.includes("404")) return "API khong ton tai (404). Kiem tra backend co dang chay khong.";
  if ((e && e.status === 0) || msg.includes("Connection")) return "Khong ket noi duoc backend. Hay kiem tra V2 Backend da chay chua.";
  if (msg.toLowerCase().includes("timeout")) return "Backend phan hoi cham (timeout). Thu lai sau.";
  return `${e && e.status ? "HTTPError" : "Error"}: ${msg.slice(0, 200)}`;
}
// --- pvca-thuan end ---

// CSS riêng của trang (poster.css chỉ có lớp .pv- dùng chung; CSP style-src cho phép 'unsafe-inline').
const pvcaCSS = `<style>
.pvca-dau h2 { margin: 0; font-size: 20px; }
.pvca-thang { font-size: 18px; font-weight: 700; white-space: nowrap; }
.pvca-the { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; margin-bottom: 10px; }
.pvca-the-o { border-left-width: 4px; border-left-style: solid; }
.pvca-so { font-size: 24px; font-weight: 700; }
.pvca-chia { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; }
.pvca-chia > .pv-nhom { min-width: 0; margin: 0; }
.pvca-trai { flex: 3 1 320px; }
.pvca-phai { flex: 2 1 260px; display: flex; flex-direction: column; gap: 8px; }
.pvca-luoi { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 4px; }
.pvca-thu { text-align: center; color: var(--muted); font-weight: 700; padding: 4px; font-size: 13px; }
.pvca-o { min-height: 60px; min-width: 0; }
.pvca-ngay { font: inherit; font-size: 12px; text-align: left; padding: 4px; white-space: pre-line; overflow-wrap: anywhere; color: var(--text);
  background: var(--bg); border: 1px solid var(--line); border-radius: 4px; cursor: pointer; }
.pvca-ngay.pvca-hom-nay { border-color: var(--ok); }
.pvca-ngay.pvca-chon { border-color: #2f6fdb; background: var(--card); }
.pvca-xoa { align-self: flex-start; }
</style>`;

// Trạng thái của lần mở trang hiện tại (mỗi lần vào trang tạo mới; pvCaDung bỏ).
let pvcaTT = null;

function pvcaVeLai(tt) {
  if (pvcaTT !== tt || !pvConSong(tt.phien)) return;
  const hn = new Date();
  const homNay = { y: hn.getFullYear(), m: hn.getMonth() + 1, d: hn.getDate() };
  const { nam, thang } = tt.luoi; // lưới + chi tiết vẽ theo tháng lúc tải xong / lúc bấm ngày (như _render_calendar)
  tt.idKeHoach = tt.chon ? pvcaIdKeHoach(pvcaDsNgay(tt.suKien, pvcaNgay(nam, thang, tt.chon))) : [];
  tt.khung.innerHTML = `${pvcaCSS}
    <div class="pv-cong-cu pvca-dau"><h2>📅 Content Calendar</h2><span class="pv-gian"></span>
      <button type="button" class="btn ghost sm" data-pvca="truoc" aria-label="Tháng trước">◀</button>
      <span class="pvca-thang" id="pvca-thang">${esc(`${pvcaTHANG[tt.thang]} ${tt.nam}`)}</span>
      <button type="button" class="btn ghost sm" data-pvca="sau" aria-label="Tháng sau">▶</button>
      <button type="button" class="btn ghost sm" data-pvca="hom-nay">Hôm nay</button>
      <button type="button" class="btn sm" data-pvca="them">+ Thêm kế hoạch</button>
      <button type="button" class="btn ghost sm" data-pvca="lam-moi" aria-label="Làm mới">🔄</button>
    </div>
    ${pvcaTheHtml(tt.tong)}
    <div class="pvca-chia">
      <section class="pv-nhom pvca-trai"><h4>Lịch tháng</h4>${pvcaLuoiHtml(nam, thang, tt.suKien, tt.chon, homNay)}</section>
      <section class="pv-nhom pvca-phai"><h4>Chi tiết ngày</h4>${pvcaChiTietHtml(nam, thang, tt.suKien, tt.chon)}</section>
    </div>`;
}

// refresh(): GET /calendar/month?year&month (không account_id, như calendar.py:262-265). Lỗi → QMessageBox.critical "Lỗi".
// Chỉ lần gọi MỚI NHẤT của phiên này được vẽ (bấm ◀▶ nhanh hoặc xoá nhiều kế hoạch không để kết quả cũ đè).
async function pvcaTai(tt) {
  const luot = ++tt.luot;
  const nam = tt.nam, thang = tt.thang;
  let payload;
  try { payload = await pvApi.calendarMonth(nam, thang); }
  catch (e) {
    if (pvcaTT !== tt || !pvConSong(tt.phien) || luot !== tt.luot) return;
    pvThongBao("Lỗi", pvcaLoi(e), "critical");
    return;
  }
  if (pvcaTT !== tt || !pvConSong(tt.phien) || luot !== tt.luot) return;
  tt.suKien = pvcaSuKienTheoNgay(payload); // _on_loaded
  tt.tong = pvcaTong(tt.suKien);
  tt.luoi = { nam, thang };
  pvcaVeLai(tt);
}

// Đổi tháng: nhãn đổi ngay (_update_month_label), lưới vẽ lại khi tải xong.
function pvcaDoiThang(tt, buoc) {
  if (buoc === 0) {
    const hn = new Date();
    tt.nam = hn.getFullYear(); tt.thang = hn.getMonth() + 1;
  } else if (buoc < 0) {
    if (tt.thang === 1) { tt.thang = 12; tt.nam -= 1; } else tt.thang -= 1;
  } else if (tt.thang === 12) { tt.thang = 1; tt.nam += 1; } else tt.thang += 1;
  pvcaVeLai(tt);
  pvcaTai(tt);
}

// + Thêm kế hoạch (_add_plan + _PlanDialog).
async function pvcaThem(tt) {
  const macDinh = pvcaNgayMacDinh(tt.nam, tt.thang, tt.chon);
  const o = (ten, nhan, the) => `<label for="pvca-f-${ten}">${esc(nhan)}</label>${the}`;
  const hop = pvHop({
    tieuDe: "+ Thêm kế hoạch",
    html: `<div class="pv-form">
      ${o("title", "Tiêu đề:", `<input id="pvca-f-title" name="title" type="text" maxlength="500" value="">`)}
      ${o("scheduled_date", "Ngày:", `<input id="pvca-f-scheduled_date" name="scheduled_date" type="text" placeholder="YYYY-MM-DD" value="${esc(macDinh)}">`)}
      ${o("scheduled_time", "Giờ:", `<input id="pvca-f-scheduled_time" name="scheduled_time" type="text" value="12:00">`)}
      ${o("folder_id", "Folder ID:", `<input id="pvca-f-folder_id" name="folder_id" type="number" min="0" max="999999" step="1" value="0">`)}
      ${o("account_id", "Account ID:", `<input id="pvca-f-account_id" name="account_id" type="number" min="0" max="999999" step="1" value="0">`)}
      ${o("notes", "Ghi chú:", `<textarea id="pvca-f-notes" name="notes" rows="3"></textarea>`)}
    </div>`,
    nut: [{ ma: "luu", chu: "Lưu", chinh: true }, { ma: "huy", chu: "Hủy" }],
  });
  const doc = (ten) => { const el = hop.el.querySelector(`[name="${ten}"]`); return el ? el.value : ""; };
  const kq = await hop.cho;
  if (kq !== "luu" || pvcaTT !== tt || !pvConSong(tt.phien)) return;
  const data = pvcaDuLieuKeHoach({ title: doc("title"), scheduled_date: doc("scheduled_date"), scheduled_time: doc("scheduled_time"),
    folder_id: doc("folder_id"), account_id: doc("account_id"), notes: doc("notes") });
  if (!data.title) { pvThongBao("Thiếu thông tin", "Tiêu đề là bắt buộc.", "warning"); return; }
  try { await pvApi.createCalendarPlan(data); }
  catch (e) {
    if (pvcaTT !== tt || !pvConSong(tt.phien)) return;
    pvThongBao("Lỗi", pvcaLoi(e), "critical");
    return;
  }
  if (pvcaTT !== tt || !pvConSong(tt.phien)) return;
  toast(`Đã thêm '${data.title}'`);
  pvcaTai(tt);
}

// 🗑️ Xóa kế hoạch đã chọn (_delete_selected_plan): QMessageBox.question (Yes/No), rồi xoá từng id, mỗi lần xong thì refresh.
async function pvcaXoa(tt) {
  const ids = [...(tt.idKeHoach || [])];
  if (!ids.length || tt.dangXoa) return;
  tt.dangXoa = true; // chặn bấm lần 2 trong lúc hộp đang mở / đang gửi (đặt TRƯỚC await)
  try {
    const hop = pvHop({
      tieuDe: "Xóa kế hoạch",
      html: `<p class="pv-cau"><span class="pv-ic" aria-hidden="true">❓</span> ${esc(`Xóa ${ids.length} kế hoạch đang chọn?`)}</p>`,
      nut: [{ ma: "co", chu: "Yes", chinh: true }, { ma: "khong", chu: "No" }],
    });
    if ((await hop.cho) !== "co" || pvcaTT !== tt || !pvConSong(tt.phien)) return;
    await Promise.all(ids.map(async (id) => {
      try { await pvApi.deleteCalendarPlan(id); }
      catch (e) {
        if (pvcaTT !== tt || !pvConSong(tt.phien)) return;
        pvThongBao("Lỗi", pvcaLoi(e), "critical");
        return;
      }
      if (pvcaTT !== tt || !pvConSong(tt.phien)) return;
      pvcaTai(tt);
    }));
  } finally {
    tt.dangXoa = false;
  }
}

function pvcaBam(tt, ev) {
  const b = ev && ev.target && typeof ev.target.closest === "function" ? ev.target.closest("[data-pvca], [data-pvca-ngay]") : null;
  if (!b || b.disabled || pvcaTT !== tt || !pvConSong(tt.phien)) return;
  const d = b.dataset || {};
  if (d.pvcaNgay !== undefined) {
    const n = Number(d.pvcaNgay);
    if (!Number.isInteger(n) || n < 1 || n > 31) return;
    tt.chon = n; // _on_day_clicked: vẽ lại lưới + chi tiết theo tháng đang xem
    tt.luoi = { nam: tt.nam, thang: tt.thang };
    pvcaVeLai(tt);
    return;
  }
  if (d.pvca === "truoc") pvcaDoiThang(tt, -1);
  else if (d.pvca === "sau") pvcaDoiThang(tt, 1);
  else if (d.pvca === "hom-nay") pvcaDoiThang(tt, 0);
  else if (d.pvca === "lam-moi") pvcaTai(tt);
  else if (d.pvca === "them") pvcaThem(tt);
  else if (d.pvca === "xoa") pvcaXoa(tt);
}

// Khung gọi khi mở #/poster/calendar.
async function pvCaVe(khung, phien) {
  const hn = new Date();
  const tt = { khung, phien, nam: hn.getFullYear(), thang: hn.getMonth() + 1, suKien: {}, tong: pvcaTong({}), chon: null,
    luoi: null, idKeHoach: [], luot: 0, dangXoa: false };
  tt.luoi = { nam: tt.nam, thang: tt.thang };
  pvcaTT = tt;
  pvcaVeLai(tt);
  khung.addEventListener("click", (ev) => pvcaBam(tt, ev));
  await pvcaTai(tt);
}

// pvDung gọi khi rời trang / đổi tab / đăng xuất: bỏ trạng thái để kết quả muộn không vẽ.
function pvCaDung() {
  pvcaTT = null;
}
