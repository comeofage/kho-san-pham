// Poster V2 trên web: trang Queue (#/poster/queue), phiếu W-P5, docs/poster-v2-tren-web.md §3.3, §6.3–§6.5.
// Bê nguyên E:/tool/tiktok_poster_v2/src/desktop/pages/queue.py (QueuePage, _PlanDialog) + confirm_destructive (widgets/common.py)
// (đối chiếu bản Svelte a55d687 Queue.svelte). Cùng nút, chữ, 5 tab, bảng 8 cột, phân trang 100/trang, hộp xác nhận, thông báo.
// Script thường, chung phạm vi với app.js/poster.js: mọi tên cấp đỉnh bắt đầu bằng "pvqu" (luật P2-7). Khung gọi pvQuVe / pvQuDung.
// Dùng: pvApi, pvCho, pvConSong, pvHop, pvXacNhan, pvThongBao (poster.js); esc, toast (app.js). CSP script-src 'self': chỉ addEventListener.
// Chỗ khác desktop có chủ ý (§3.3 + kỷ luật phiếu):
// - ▶ "Chạy ngay" (queue/{id}/post, lớp L) trả 202 rồi pvCho hỏi _kq; nút của dòng bị khoá TRƯỚC await tới khi lệnh xong (kể cả khi
//   bảng vẽ lại); mở trang thì pvApi.dangChay() trước, dòng đang chạy bị khoá và theo dõi tiếp.
// - Lỗi TẠM khi gửi ▶ (mạng, 429, 502/503/504/524): hỏi lại dangChay; lệnh còn chạy ở máy nhà thì giữ khoá và chờ, không mở nút.
// - Nút Auto post khoá TRƯỚC await tới khi có trả lời (desktop không khoá → bấm đúp gửi on rồi off). Lỗi TẠM thì đọc lại settings.
// - Nút lệnh ghi khác bỏ qua cú bấm lặp khi lệnh cùng loại đang gửi (không đổi giao diện).
"use strict";

// --- pvqu-thuan start ---
const pvquCO_TRANG = 100; // PAGE_SIZE queue.py:97
const pvquTAB = [["pending", "⏳ Chờ đăng"], ["failed", "❌ Lỗi"], ["done", "✅ Đã đăng"], ["running", "⚡ Đang chạy"], ["all", "📋 Tất cả"]];
const pvquCOT = ["ID", "Video", "Folder", "Tài khoản", "Sản phẩm", "Thời gian", "Trạng thái", "Thao tác"];
const pvquGIO_MAC_DINH = '["08:00","12:00","20:00"]';

const pvquLaDoi = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
// bool(v) của Python.
function pvquThat(v) {
  if (Array.isArray(v)) return v.length > 0;
  if (pvquLaDoi(v)) return Object.keys(v).length > 0;
  return !!v;
}
// str(v) của Python (None → "None"); thiếu khoá → giá trị mặc định của dict.get.
function pvquStr(v, macDinh = "") {
  if (v === undefined) return macDinh;
  if (v === null) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  return String(v);
}
// dict.get(k, mặc định) của Python cho phản hồi API (không phải dict → mặc định).
const pvquLay = (o, k, macDinh) => (pvquLaDoi(o) && Object.prototype.hasOwnProperty.call(o, k) ? o[k] : macDinh);
// f"{n:,}"
const pvquSo = (n) => Math.trunc(Number(n) || 0).toLocaleString("en-US");
const pvquSoNguyen = (v) => { const n = Math.trunc(Number(v)); return Number.isFinite(n) ? n : 0; };
const pvquMaxTrang = (tong) => Math.max(1, Math.floor((pvquSoNguyen(tong) + pvquCO_TRANG - 1) / pvquCO_TRANG));

// Nhãn tab: chưa có số đếm thì chỉ nhãn; có rồi "<nhãn> (n)" (_on_counts_loaded).
const pvquNhanTab = (nhan, so, daDem) => (daDem ? `${nhan} (${pvquSo(so)})` : nhan);

// _on_counts_loaded: {} / không phải dict → null (giữ nguyên); còn lại → số đếm 5 tab, "all" = tổng 4 trạng thái.
function pvquDem(counts) {
  if (!pvquLaDoi(counts) || !Object.keys(counts).length) return null;
  const g = (k) => pvquSoNguyen(pvquLay(counts, k, 0));
  const d = { pending: g("pending"), running: g("running"), done: g("done"), failed: g("failed") };
  return { ...d, all: d.pending + d.running + d.done + d.failed };
}

// "Trang x / y (Tổng: n mục - 100/trang)" (_update_pagination_ui).
function pvquPhanTrang(trang, tong) {
  const max = pvquMaxTrang(tong);
  const cur = Math.min(Math.max(1, pvquSoNguyen(trang) || 1), max);
  return { trang: cur, max, chu: `Trang ${pvquSo(cur)} / ${pvquSo(max)} (Tổng: ${pvquSo(tong)} mục - 100/trang)`, truoc: cur > 1, sau: cur < max };
}

// Một dòng bảng (_populate_row) → các ô chữ.
function pvquDong(it) {
  const o = pvquLaDoi(it) ? it : {};
  const status = pvquLay(o, "status", "");
  const video = pvquThat(o.video_filename) ? o.video_filename : pvquThat(o.video_path) ? o.video_path : "";
  const raw = status === "done"
    ? [o.posted_at, o.scheduled_at, o.created_at].find(pvquThat) ?? ""
    : [o.scheduled_at, o.created_at].find(pvquThat) ?? "";
  const tt = status === "done" ? ["✅ Đã đăng", "pv-xanh"] : status === "failed" ? ["❌ Lỗi", "pv-do"]
    : status === "running" ? ["⚡ Đang đăng", "pv-lam"] : ["⏳ Chờ đăng", "pv-vang"];
  return {
    id: pvquStr(pvquLay(o, "id", "")),
    qid: pvquSoNguyen(pvquLay(o, "id", 0)), // int(item.get("id", 0))
    video: Array.from(pvquStr(video)).slice(0, 50).join(""),
    folder: pvquThat(o.folder_name) ? pvquStr(o.folder_name) : `#${pvquStr(pvquLay(o, "folder_id", ""))}`,
    account: pvquThat(o.account_name) ? pvquStr(o.account_name) : `#${pvquStr(pvquLay(o, "account_id", ""))}`,
    product: pvquThat(o.product_id) ? pvquStr(o.product_id) : "",
    time: pvquStr(raw).replaceAll("T", " ").split(".")[0],
    status: tt[0], lop: tt[1],
  };
}

function pvquDongHtml(it, dangChay) {
  const r = pvquDong(it);
  const khoa = dangChay && dangChay.has(r.qid);
  return `<tr><td>${esc(r.id)}</td><td>${esc(r.video)}</td><td>${esc(r.folder)}</td><td>${esc(r.account)}</td>`
    + `<td title="${esc(r.product)}">${esc(r.product)}</td><td>${esc(r.time)}</td><td class="${r.lop}">${esc(r.status)}</td>`
    + `<td class="pvqu-nut"><button type="button" class="btn sm" data-pvqu-chay="${esc(r.qid)}" title="Chạy ngay" aria-label="Chạy ngay"${khoa ? " disabled" : ""}>${khoa ? "…" : "▶"}</button>`
    + `<button type="button" class="btn ghost sm" data-pvqu-thu="${esc(r.qid)}" title="Retry" aria-label="Retry">↻</button>`
    + `<button type="button" class="btn ghost sm pv-do" data-pvqu-xoa="${esc(r.qid)}" title="Xóa" aria-label="Xóa">✕</button></td></tr>`;
}

// _PlanDialog.get_data: QSpinBox 1–200 / 0–120; khung giờ là JSON mảng, sai → [].
function pvquKeHoach(soVideo, gio, jitter) {
  const kep = (v, lo, hi, md) => { const n = Math.trunc(Number(v)); return Number.isFinite(n) && String(v ?? "").trim() !== "" ? Math.min(hi, Math.max(lo, n)) : md; };
  const raw = String(gio ?? "").trim();
  let post = [];
  try { const v = raw ? JSON.parse(raw) : []; post = Array.isArray(v) ? v : []; } catch (e) { post = []; }
  return { count: kep(soVideo, 1, 200, 5), post_times: post, jitter_minutes: kep(jitter, 0, 120, 20) };
}

// GET /_kq → lệnh đăng queue đang chạy: [{qid, cho, toi}] (§3.3: POST /api/v2/queue/{id}/post|run).
function pvquViecChay(r) {
  const ds = pvquLaDoi(r) && Array.isArray(r.dang_chay) ? r.dang_chay : [];
  const kq = [];
  for (const v of ds) {
    if (!pvquLaDoi(v) || String(v.method || "").toUpperCase() !== "POST" || typeof v.cho !== "string") continue;
    const m = String(v.path || "").split("?")[0].match(/^\/api\/v2\/queue\/(\d{1,9})\/(?:post|run)$/);
    if (!m) continue;
    const tq = pvquLay(v.tom_tat, "queue_id", undefined);
    const qid = Number.isInteger(tq) ? tq : Number(m[1]);
    kq.push({ qid, cho: v.cho, toi: v.toi_da_giay });
  }
  return kq;
}
// widgets/common.py _friendly_error: run_async đưa MỌI lỗi qua hàm này trước on_error (giữ chữ không dấu của bản gốc;
// cùng cách port với pv-settings.js/pv-logs.js/pv-views.js). Lỗi HTTP (có e.status) mang tên lớp "HTTPError" như requests.
function pvquLoi(e) {
  const msg = String(e && e.message ? e.message : e);
  if (msg.includes("401")) return "Khong co quyen truy cap (401). Kiem tra API token trong .env.";
  if (msg.includes("404")) return "API khong ton tai (404). Kiem tra backend co dang chay khong.";
  if ((e && e.status === 0) || msg.includes("Connection")) return "Khong ket noi duoc backend. Hay kiem tra V2 Backend da chay chua.";
  if (msg.toLowerCase().includes("timeout")) return "Backend phan hoi cham (timeout). Thu lai sau.";
  return `${e && e.status ? "HTTPError" : "Error"}: ${msg.slice(0, 200)}`;
}
// --- pvqu-thuan end ---

const pvquCSS = `<style>
.pvqu-dau h2 { margin: 0; font-size: 20px; }
.pvqu-auto { min-width: 64px; border-radius: 14px; }
.pvqu-auto[aria-pressed="false"] { background: var(--line); color: var(--text); }
.pvqu-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.pvqu-nut { white-space: nowrap; }
.pvqu-nut .btn { min-width: 36px; margin-right: 4px; }
.pvqu-trang { justify-content: center; margin-top: 8px; }
.pvqu-trang .pvqu-tt { font-weight: 700; padding: 0 10px; }
</style>`;

// Trạng thái của lần mở trang hiện tại (mỗi lần vào trang tạo mới; pvQuDung bỏ).
let pvquTT = null;

const pvquSong = (tt) => pvquTT === tt && pvConSong(tt.phien);

function pvquVeLai(tt) {
  if (!pvquSong(tt)) return;
  const nutCC = [["lam-moi", "🔄 Refresh", "btn sm"], ["len-lich", "📅 Lên lịch", "btn ghost sm"], ["go-ket", "🔓 Gỡ kẹt", "btn ghost sm"],
    ["random", "🔀 Random", "btn ghost sm"], ["xoa-cho", "🗑️ Xóa hết chờ", "btn ghost sm"], ["reset", "🧹 Reset toàn bộ", "btn ghost sm pv-do"]];
  const rows = tt.rows[tt.tab] || [];
  tt.khung.innerHTML = `${pvquCSS}
    <div class="pv-cong-cu pvqu-dau"><h2>📋 Queue (Hàng đợi)</h2><span class="pv-gian"></span><span>Auto post:</span>
      <button type="button" class="btn sm pvqu-auto" data-pvqu="auto" aria-pressed="${tt.apBat ? "true" : "false"}"${tt.apBan ? " disabled" : ""}>${esc(tt.apChu)}</button></div>
    <div class="pv-cong-cu">${nutCC.map(([ma, chu, lop]) => `<button type="button" class="${lop}" data-pvqu="${ma}">${esc(chu)}</button>`).join("")}</div>
    <div class="pvqu-tabs" role="tablist">${pvquTAB.map(([k, nhan]) =>
      `<button type="button" role="tab" class="chip${k === tt.tab ? " on" : ""}" aria-selected="${k === tt.tab ? "true" : "false"}" data-pvqu-tab="${k}">${
        esc(pvquNhanTab(nhan, tt.dem[k], tt.daDem))}</button>`).join("")}</div>
    <div class="pv-cuon"><table class="pv-bang"><thead><tr>${pvquCOT.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((it) => pvquDongHtml(it, tt.dangChay)).join("")}</tbody></table></div>
    <div class="pv-cong-cu pvqu-trang">
      <button type="button" class="btn ghost sm" data-pvqu="truoc"${tt.trangTruoc ? "" : " disabled"}>◀ Trang trước</button>
      <span class="pvqu-tt" id="pvqu-tt">${esc(tt.trangChu)}</span>
      <button type="button" class="btn ghost sm" data-pvqu="sau"${tt.trangSau ? "" : " disabled"}>Trang sau ▶</button>
    </div>`;
}

// _update_pagination_ui
function pvquCapNhatTrang(tt) {
  const p = pvquPhanTrang(tt.trang[tt.tab] || 1, tt.dem[tt.tab] || 0);
  tt.trang[tt.tab] = p.trang;
  tt.trangChu = p.chu; tt.trangTruoc = p.truoc; tt.trangSau = p.sau;
}

// refresh_async: chặn làm mới chồng (cờ + lưới an toàn 35 s, queue.py:284-333), gọi status_counts + list_queue song song.
function pvquLamMoi(tt) {
  if (!pvquSong(tt) || tt.dangTai) return;
  tt.dangTai = true;
  tt.conGoi = 2;
  const hen = setTimeout(() => { tt.henAnToan.delete(hen); tt.dangTai = false; }, 35_000);
  tt.henAnToan.add(hen);
  const xong = () => { tt.conGoi -= 1; if (tt.conGoi <= 0) tt.dangTai = false; };

  pvApi.statusCounts().then((c) => {
    if (!pvquSong(tt)) return;
    const d = pvquDem(c);
    if (!d) return;
    tt.dem = d; tt.daDem = true;
    pvquCapNhatTrang(tt);
    pvquVeLai(tt);
  }).catch(() => { /* desktop chỉ logger.debug */ }).finally(xong);

  const tab = tt.tab;
  const status = tab === "all" ? null : tab;
  // Kẹp trang theo tổng đã biết (tab bỏ ở trang 2+ khi số đếm co lại).
  const max = pvquMaxTrang(tt.dem[tab] || 0);
  if ((tt.trang[tab] || 1) > max) tt.trang[tab] = max;
  const offset = ((tt.trang[tab] || 1) - 1) * pvquCO_TRANG;
  pvApi.listQueue(status, pvquCO_TRANG, offset).then((items) => {
    if (!pvquSong(tt)) return;
    tt.items = Array.isArray(items) ? items : []; // self._items: trang vừa tải (📅 Lên lịch dùng)
    tt.rows[tab] = tt.items;
    pvquCapNhatTrang(tt);
    pvquVeLai(tt);
  }).catch(async (e) => {
    if (!pvquSong(tt)) return;
    await pvThongBao("Lỗi tải queue", pvquLoi(e), "critical"); // hộp modal: desktop nhả cờ sau khi đóng hộp
  }).finally(xong);
}

// _refresh_autopost: settings.autopost_enabled == "1". Lỗi chỉ ghi log.
async function pvquTaiAuto(tt) {
  let s;
  try { s = await pvApi.getSettingsAll(); } catch (e) { return; }
  if (!pvquSong(tt) || tt.apBan || !pvquLaDoi(s)) return;
  pvquDatAuto(tt, pvquLay(s, "autopost_enabled", "0") === "1");
  pvquVeLai(tt);
}
function pvquDatAuto(tt, bat) { // _apply_autopost_state
  tt.apBat = bat;
  tt.apChu = bat ? "BẬT" : "TẮT";
}

// _on_toggle_autopost: nút checkable đổi trạng thái ngay khi bấm; khoá nút TRƯỚC await.
async function pvquBamAuto(tt) {
  if (tt.apBan) return;
  const bat = !tt.apBat;
  tt.apBat = bat;
  tt.apBan = true;
  pvquVeLai(tt);
  try { await (bat ? pvApi.autopostOn() : pvApi.autopostOff()); }
  catch (e) {
    if (!pvquSong(tt)) return;
    tt.apBan = false;
    pvquDatAuto(tt, !bat);
    pvquVeLai(tt);
    if (e && e.tam) pvquTaiAuto(tt); // lệnh có thể đã tới máy nhà: đọc lại trạng thái thật
    pvThongBao("Lỗi", pvquLoi(e), "critical");
    return;
  }
  if (!pvquSong(tt)) return;
  tt.apBan = false;
  pvquDatAuto(tt, bat);
  pvquVeLai(tt);
  toast(bat ? "Auto post đã BẬT" : "Auto post đã TẮT");
}

// ▶ xong (thành công / lỗi), dùng chung cho bấm ▶ và lệnh đang chạy lúc mở trang.
function pvquXongChay(tt, qid, loi) {
  if (!pvquSong(tt)) return;
  tt.dangChay.delete(qid);
  pvquVeLai(tt);
  if (loi) { pvThongBao("Lỗi", pvquLoi(loi), "critical"); return; }
  toast(`Đã chạy #${qid}`);
  pvquLamMoi(tt);
}

// Theo dõi lệnh đăng đang chạy ở máy nhà (dòng qid đã khoá).
async function pvquTheoDoi(tt, qid, cho, toi) {
  try { await pvCho(cho, toi); }
  catch (e) { if (!pvquSong(tt) || (e && e.roiTrang)) return; pvquXongChay(tt, qid, e); return; }
  pvquXongChay(tt, qid, null);
}

// ▶ Chạy ngay (_run): khoá nút + "…" TRƯỚC await, toast "Đang đăng…", POST queue/{id}/post (202 → pvCho trong pvGoi).
async function pvquChay(tt, qid) {
  if (tt.dangChay.has(qid)) return;
  tt.dangChay.add(qid);
  pvquVeLai(tt);
  toast(`Đang đăng video #${qid}, vui lòng đợi...`);
  try { await pvApi.postQueueItem(qid); }
  catch (e) {
    if (!pvquSong(tt) || (e && e.roiTrang)) return;
    if (e && e.tam) {
      // Lỗi tạm (mạng / hết chỗ / cổng quá giờ): lệnh có thể đã chạy ở máy nhà. Còn chạy → giữ khoá, chờ tiếp; không gửi lại.
      let viec = [];
      try { viec = pvquViecChay(await pvApi.dangChay()); } catch (e2) { viec = []; }
      if (!pvquSong(tt)) return;
      const v = viec.find((x) => x.qid === qid);
      if (v) { pvquTheoDoi(tt, qid, v.cho, v.toi); return; }
    }
    pvquXongChay(tt, qid, e);
    return;
  }
  pvquXongChay(tt, qid, null);
}

// Lệnh ghi ngắn: (xác nhận) → gọi → toast + làm mới; lỗi → QMessageBox.critical "Lỗi". Bấm lặp khi cùng lệnh đang gửi thì bỏ qua.
async function pvquLenh(tt, ma, xacNhan, goi, chuToast) {
  if (tt.dangGui.has(ma)) return;
  if (xacNhan && !(await xacNhan())) return;
  if (!pvquSong(tt) || tt.dangGui.has(ma)) return;
  tt.dangGui.add(ma);
  let r;
  try { r = await goi(); }
  catch (e) {
    tt.dangGui.delete(ma);
    if (!pvquSong(tt)) return;
    pvThongBao("Lỗi", pvquLoi(e), "critical");
    return;
  }
  tt.dangGui.delete(ma);
  if (!pvquSong(tt)) return;
  toast(chuToast(r));
  pvquLamMoi(tt);
}

// 📅 Lên lịch (_plan): hộp _PlanDialog → kiểm self._items → xác nhận → queue_unstick (lỗi gốc giữ nguyên: chỉ dùng jitter cho câu chữ).
async function pvquLenLich(tt) {
  if (tt.dangGui.has("len-lich")) return;
  const hop = pvHop({
    tieuDe: "📅 Lên lịch đăng video",
    html: `<div class="pv-form">
      <label for="pvqu-f-count">Số video:</label><input id="pvqu-f-count" name="count" type="number" min="1" max="200" step="1" value="5">
      <label for="pvqu-f-times">Khung giờ vàng:</label><input id="pvqu-f-times" name="times" type="text" placeholder="${esc(pvquGIO_MAC_DINH)}" value="${esc(pvquGIO_MAC_DINH)}">
      <label for="pvqu-f-jitter">Jitter (phút):</label><input id="pvqu-f-jitter" name="jitter" type="number" min="0" max="120" step="1" value="20">
    </div>`,
    nut: [{ ma: "luu", chu: "Lên lịch", chinh: true }, { ma: "huy", chu: "Hủy" }],
  });
  const doc = (ten) => { const el = hop.el.querySelector(`[name="${ten}"]`); return el ? el.value : ""; };
  if ((await hop.cho) !== "luu" || !pvquSong(tt)) return;
  const data = pvquKeHoach(doc("count"), doc("times"), doc("jitter"));
  if (!tt.items.length) { pvThongBao("Trống", "Không có item nào để lên lịch.", "info"); return; }
  const pending = tt.items.filter((it) => pvquLaDoi(it) && it.status === "pending");
  if (!pending.length) { pvThongBao("Trống", "Không có pending item nào để lên lịch.", "info"); return; }
  await pvquLenh(tt, "len-lich",
    () => pvXacNhan("Lên lịch lại", `Sẽ re-schedule ${pending.length} pending item với jitter ${data.jitter_minutes} phút.`),
    () => pvApi.queueUnstick(), () => `Đã re-schedule ${pending.length} item`);
}

function pvquBam(tt, ev) {
  const b = ev && ev.target && typeof ev.target.closest === "function"
    ? ev.target.closest("[data-pvqu], [data-pvqu-tab], [data-pvqu-chay], [data-pvqu-thu], [data-pvqu-xoa]") : null;
  if (!b || b.disabled || !pvquSong(tt)) return;
  const d = b.dataset || {};
  const id = (v) => (typeof v === "string" && /^\d{1,9}$/.test(v) ? Number(v) : null);
  if (d.pvquTab !== undefined) {
    if (!pvquTAB.some(([k]) => k === d.pvquTab) || d.pvquTab === tt.tab) return;
    tt.tab = d.pvquTab; // currentChanged → refresh_async (bị bỏ nếu đang tải: giữ như desktop)
    pvquVeLai(tt);
    pvquLamMoi(tt);
    return;
  }
  if (d.pvquChay !== undefined) { const q = id(d.pvquChay); if (q !== null) pvquChay(tt, q); return; }
  if (d.pvquThu !== undefined) {
    const q = id(d.pvquThu);
    if (q !== null) pvquLenh(tt, `thu-${q}`, null, () => pvApi.queueRetry(q), () => `Đã retry #${q}`);
    return;
  }
  if (d.pvquXoa !== undefined) {
    const q = id(d.pvquXoa);
    if (q !== null) {
      pvquLenh(tt, `xoa-${q}`, () => pvXacNhan("Xóa queue item", "Bạn sắp xóa:", `#${q}`),
        () => pvApi.deleteQueueItem(q), () => `Đã xóa thành công #${q}`);
    }
    return;
  }
  switch (d.pvqu) {
    case "auto": pvquBamAuto(tt); break;
    case "lam-moi": pvquLamMoi(tt); break;
    case "len-lich": pvquLenLich(tt); break;
    case "go-ket":
      pvquLenh(tt, "go-ket", () => pvXacNhan("Gỡ kẹt video", "Reset tất cả video đang chạy quá 15 phút về pending."),
        () => pvApi.queueUnstick(), (r) => `Đã gỡ ${pvquStr(pvquLay(r, "reset_count", 0))} video`);
      break;
    case "xoa-cho":
      pvquLenh(tt, "xoa-cho", () => pvXacNhan("Xóa hết chờ", "Xóa tất cả video đang pending. Đã đăng/lỗi giữ nguyên."),
        () => pvApi.queueClearPending(), (r) => `Đã xóa ${pvquStr(pvquLay(r, "deleted", 0))} pending`);
      break;
    case "reset":
      pvquLenh(tt, "reset", () => pvXacNhan("Reset toàn bộ", "Reset toàn bộ video failed/stuck về pending để thử lại."),
        () => pvApi.queueResetAll(), (r) => `Đã reset ${pvquStr(pvquLay(r, "reset_count", 0))} video`);
      break;
    case "random":
      pvquLenh(tt, "random", () => pvXacNhan("Random hàng chờ", "Xáo trộn thứ tự tất cả video đang pending, giãn cách lại 3-5 phút mỗi video."),
        () => pvApi.queueRandomShuffle(), (r) => `Đã random ${pvquStr(pvquLay(r, "shuffled", 0))} video`);
      break;
    case "truoc": { // _prev_page
      const cur = tt.trang[tt.tab] || 1;
      if (cur > 1) { tt.trang[tt.tab] = cur - 1; pvquLamMoi(tt); }
      break;
    }
    case "sau": { // _next_page
      const cur = tt.trang[tt.tab] || 1;
      if (cur < pvquMaxTrang(tt.dem[tt.tab] || 0)) { tt.trang[tt.tab] = cur + 1; pvquLamMoi(tt); }
      break;
    }
    default: break;
  }
}

// Khung gọi khi mở #/poster/queue. §3.3: hỏi dangChay TRƯỚC khi vẽ nút từng dòng (bảng chỉ có dòng sau khi list_queue về).
async function pvQuVe(khung, phien) {
  const tt = {
    khung, phien, tab: "pending", items: [],
    rows: { pending: [], failed: [], done: [], running: [], all: [] },
    trang: { pending: 1, failed: 1, done: 1, running: 1, all: 1 },
    dem: { pending: 0, failed: 0, done: 0, running: 0, all: 0 }, daDem: false,
    trangChu: "Trang 1 / 1 (Tổng: 0 mục)", trangTruoc: true, trangSau: true, // nhãn + nút lúc dựng (queue.py:236-248)
    apBat: false, apChu: "TẮT", apBan: false,
    dangTai: false, conGoi: 0, henAnToan: new Set(),
    dangChay: new Set(), dangGui: new Set(),
  };
  pvquTT = tt;
  pvquVeLai(tt);
  khung.addEventListener("click", (ev) => pvquBam(tt, ev));
  let viec = [];
  try { viec = pvquViecChay(await pvApi.dangChay()); }
  catch (e) { if (!pvquSong(tt)) return; viec = []; } // không đọc được thì vẫn mở trang như desktop
  if (!pvquSong(tt)) return;
  for (const v of viec) {
    if (tt.dangChay.has(v.qid)) continue;
    tt.dangChay.add(v.qid);
    pvquTheoDoi(tt, v.qid, v.cho, v.toi);
  }
  pvquLamMoi(tt); // __init__: refresh() rồi _refresh_autopost()
  pvquTaiAuto(tt);
}

// pvDung gọi khi rời trang / đổi tab / đăng xuất: huỷ lưới an toàn 35 s, bỏ trạng thái để kết quả muộn không vẽ.
function pvQuDung() {
  const tt = pvquTT;
  pvquTT = null;
  if (!tt) return;
  for (const h of tt.henAnToan) clearTimeout(h);
  tt.henAnToan.clear();
}
