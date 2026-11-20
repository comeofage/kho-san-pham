// Poster V2 trên web — trang Logs (#/poster/logs). Bê nguyên E:/tool/tiktok_poster_v2/src/desktop/pages/logs.py (LogsPage):
// bảng 7 cột, phân trang 100 dòng ("◀ Trang trước" / "Trang sau ▶"), bấm một dòng → hộp "Chi tiết log #<id>" (dòng thời gian từng
// bước), nút "📊 Thống kê đổi sản phẩm" → hộp thống kê (affiliate_stats), nút 🔄 Refresh.
// Thiết kế: docs/poster-v2-tren-web.md §6.3–§6.5, phiếu W-P2. Tiền tố pvlo. Khung gọi pvLoVe(khung, phien). Hộp thoại qua pvHop /
// pvThongBao (poster.js); mọi chuỗi từ API qua esc (gồm message, error_details, caption, JSON timeline).
// Giữ nguyên như gốc: tổng số log để phân trang = pending + running + done + failed của /queue/status (đếm QUEUE, không đếm logs —
// logs.py:282-287), nên số trang có thể lệch số log thật.
"use strict";

// --- pvlo-thuan start ---
const pvloPAGE_SIZE = 100; // LogsPage.PAGE_SIZE
const pvloCOT = ["ID", "Thời gian", "Folder", "Tài khoản", "Video", "Sản phẩm", "Trạng thái"]; // logs.py:216-218
const pvloMAU = { GREEN: "var(--ok)", RED: "#d33a3a", YELLOW: "#d98a00", BLUE: "#2f6fdb" }; // theme.GREEN / RED / YELLOW / BLUE

// str() của Python cho dict.get(k, mặc_định): thiếu → mặc định, None → "None".
function pvloPy(v, macDinh = "") {
  return v === undefined ? macDinh : v === null ? "None" : String(v);
}
const pvloSo = (n) => n.toLocaleString("en-US"); // f"{n:,}"
const pvloGio = (v) => String(v ?? "").replace(/T/g, " ").split(".")[0]; // .replace("T", " ").split(".")[0]

// _on_counts_loaded: {} / null → bỏ qua (null); còn lại → tổng 4 trạng thái.
function pvloTong(counts) {
  if (!counts || typeof counts !== "object" || Object.keys(counts).length === 0) return null;
  return ["pending", "running", "done", "failed"].reduce((t, k) => t + (Number(counts[k] ?? 0) || 0), 0);
}
const pvloSoTrang = (tong) => Math.max(1, Math.floor((tong + pvloPAGE_SIZE - 1) / pvloPAGE_SIZE));
// _update_pagination_ui: kẹp trang về số trang tối đa → { trang, chu, truoc, sau }.
function pvloPhanTrang(trang, tong) {
  const mp = pvloSoTrang(tong);
  const t = trang > mp ? mp : trang;
  return { trang: t, chu: `Trang ${pvloSo(t)} / ${pvloSo(mp)} (Tổng: ${pvloSo(tong)} logs - 100/trang)`, truoc: t > 1, sau: t < mp };
}

// _render (logs.py:301-345): một dòng bảng.
function pvloDong(log) {
  const l = log && typeof log === "object" ? log : {};
  const status = pvloPy(l.status).toLowerCase();
  const message = String(l.message || "");
  const err = String(l.error_details || "");
  let st;
  if (["done", "success", "posted"].includes(status)) st = { chu: "✅ Thành công", mau: pvloMAU.GREEN, tip: message || "Đăng video thành công" };
  else if (["failed", "error"].includes(status)) st = { chu: "❌ Thất bại", mau: pvloMAU.RED, tip: err ? `${message}\n${err}` : message };
  else if (status === "running") st = { chu: "⚡ Đang chạy", mau: pvloMAU.BLUE, tip: "" };
  else st = { chu: status, mau: "", tip: "" };
  const video = String(l.video_filename || "");
  return {
    id: pvloPy(l.id),
    gio: pvloGio(l.created_at || l.timestamp || ""),
    folder: String(l.folder_name || (l.folder_id ? `#${l.folder_id}` : "")),
    account: String(l.account_name || (l.account_id ? `#${l.account_id}` : "")),
    video,
    video50: video.slice(0, 50),
    product: String(l.product_id || ""),
    st,
  };
}

// core/post_timeline.py parse_timeline: chuỗi JSON → các phần tử là dict; rỗng / hỏng / không phải mảng → [].
function pvloTimeline(raw) {
  if (!raw || typeof raw !== "string") return [];
  let d;
  try { d = JSON.parse(raw); } catch (e) { return []; }
  return Array.isArray(d) ? d.filter((x) => x && typeof x === "object" && !Array.isArray(x)) : [];
}

// Nội dung hộp _LogDetailDialog (logs.py:113-172).
function pvloChiTietHtml(log) {
  const l = log && typeof log === "object" ? log : {};
  const dau = `<div style="font-weight:700;overflow-wrap:anywhere;margin-bottom:8px">${esc(l.video_filename || "")}<br>Tài khoản: ${
    esc(l.account_name || "")}&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;Folder: ${esc(l.folder_name || "")}</div>`;
  const ev = pvloTimeline(l.timeline);
  let than;
  if (!ev.length) {
    const extra = String(l.error_details || "");
    than = `<p>Log này được ghi trước khi có dòng thời gian chi tiết.</p><p>[${esc(pvloGio(l.created_at || ""))}] ${esc(l.message || "")}</p>${
      extra ? `<p style="color:${pvloMAU.RED}">${esc(extra)}</p>` : ""}`;
  } else {
    than = ev.map((e) => {
      const mau = e.step === "error" ? pvloMAU.RED : e.step === "done" ? pvloMAU.GREEN : "";
      const ct = e.step === "caption" && e.caption
        ? `<div class="muted" style="margin:2px 0 0 12px">${esc(String(e.caption)).replace(/\n/g, "<br>")}</div>` : "";
      return `<p style="margin:6px 0"><span class="muted">${esc(pvloPy(e.at))}</span> &nbsp;<span${mau ? ` style="color:${mau}"` : ""}>${
        esc(pvloPy(e.text))}</span>${ct}</p>`;
    }).join("");
  }
  return `${dau}<div class="pv-the" style="max-height:60vh;overflow:auto;overflow-wrap:anywhere">${than}</div>`;
}

// Nội dung hộp _AffiliateStatsDialog (logs.py:31-110).
function pvloThongKeHtml(stats) {
  const s = stats && typeof stats === "object" && !Array.isArray(stats) ? stats : {};
  const by = s.by_action && typeof s.by_action === "object" ? s.by_action : {};
  const recent = Array.isArray(s.recent) ? s.recent : [];
  const the = [["primary", pvloMAU.GREEN], ["fallback", pvloMAU.YELLOW], ["fallback_exhausted", pvloMAU.RED]].map(([a, mau]) =>
    `<div class="pv-the" data-pvlo-hanh-dong="${a}" style="border-left:4px solid ${mau};padding:8px">
      <div class="muted" style="font-size:11px">${a}</div><div style="color:${mau};font-size:20px;font-weight:700">${esc(pvloPy(by[a], "0"))}</div></div>`).join("");
  const dong = recent.map((r) => {
    const x = r && typeof r === "object" ? r : {};
    const a = x.action || "primary";
    const mau = a === "fallback" ? pvloMAU.YELLOW : a === "fallback_exhausted" ? pvloMAU.RED : pvloMAU.GREEN;
    return `<tr><td>${esc(pvloPy(x.posted_at))}</td><td>${esc(pvloPy(x.product_id))}</td><td style="color:${mau}">${esc(pvloPy(x.action))}</td><td>${
      esc(String(x.fallback_from || ""))}</td></tr>`;
  }).join("");
  return `<div style="font-size:16px;font-weight:700">${esc(`Tổng cộng: ${pvloPy(s.total, "0")} lượt gắn sản phẩm`)}</div>
  <div class="pv-luoi" style="margin-top:8px">${the}</div>
  <div class="muted" style="margin-top:8px">Lịch sử gần đây (50 mục)</div>
  <div class="pv-cuon"><table class="pv-bang"><thead><tr><th>Thời gian</th><th>Product ID</th><th>Action</th><th>Fallback từ</th></tr></thead>
  <tbody>${dong}</tbody></table></div>`;
}

// widgets/common.py _friendly_error: chữ lỗi hiện trong hộp "Lỗi" (giữ nguyên chữ không dấu của bản gốc).
function pvloLoi(e) {
  const msg = String(e && e.message ? e.message : e);
  if (msg.includes("401")) return "Khong co quyen truy cap (401). Kiem tra API token trong .env.";
  if (msg.includes("404")) return "API khong ton tai (404). Kiem tra backend co dang chay khong.";
  if ((e && e.status === 0) || msg.includes("Connection")) return "Khong ket noi duoc backend. Hay kiem tra V2 Backend da chay chua.";
  if (msg.toLowerCase().includes("timeout")) return "Backend phan hoi cham (timeout). Thu lai sau.";
  return `${e && e.status ? "HTTPError" : "Error"}: ${msg.slice(0, 200)}`;
}

// Toàn trang. tt = { logs, rong, chu, truoc, sau }.
function pvloHtml(tt) {
  const bang = tt.rong
    ? `<div class="center muted" style="padding:40px" data-pvlo-rong><div style="font-size:48px">📭</div><div style="font-size:16px;color:var(--text)">Chưa có log nào</div></div>`
    : `<div class="pv-cuon"><table class="pv-bang"><thead><tr>${pvloCOT.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${
      tt.logs.map(pvloDong).map((r, i) => `<tr data-pvlo="dong" data-pvlo-i="${i}" style="cursor:pointer">
      <td>${esc(r.id)}</td><td>${esc(r.gio)}</td><td>${esc(r.folder)}</td><td>${esc(r.account)}</td>
      <td title="${esc(r.video)}">${esc(r.video50)}</td><td title="${esc(r.product)}" style="color:${pvloMAU.YELLOW}">${esc(r.product)}</td>
      <td${r.st.mau ? ` style="color:${r.st.mau}"` : ""}${r.st.tip ? ` title="${esc(r.st.tip)}"` : ""}>${esc(r.st.chu)}</td></tr>`).join("")}</tbody></table></div>`;
  return `<div class="pvlo">
  <div class="pv-cong-cu"><h2 style="margin:0">📜 Logs</h2><span class="pv-gian"></span>
    <button type="button" class="btn" data-pvlo="thongke">📊 Thống kê đổi sản phẩm</button>
    <button type="button" class="btn ghost" data-pvlo="lammoi">🔄 Refresh</button></div>
  ${bang}
  <div class="pv-cong-cu" style="justify-content:center;margin-top:6px">
    <button type="button" class="btn ghost" data-pvlo="truoc"${tt.truoc ? "" : " disabled"}>◀ Trang trước</button>
    <span style="font-weight:700;padding:0 14px">${esc(tt.chu)}</span>
    <button type="button" class="btn ghost" data-pvlo="sau"${tt.sau ? "" : " disabled"}>Trang sau ▶</button></div>
</div>`;
}
// --- pvlo-thuan end ---

// Khung gọi khi mở tab Logs. refresh() (logs.py:256-269): status_counts (lỗi chỉ ghi console) và list_logs(100, offset) chạy song song;
// lỗi list_logs → hộp "Lỗi". Không tự làm mới theo giờ (gốc không có timer).
async function pvLoVe(khung, phien) {
  // Nút phân trang mặc định bật cho tới khi có số đếm (QPushButton mặc định enabled; _update_pagination_ui mới đặt lại).
  const tt = { logs: [], rong: false, trang: 1, tong: 0, chu: "Trang 1 / 1 (Tổng: 0 logs - 100/trang)", truoc: true, sau: true };
  const ve = () => { khung.innerHTML = pvloHtml(tt); };
  ve();
  const capNhatTrang = () => {
    const p = pvloPhanTrang(tt.trang, tt.tong);
    Object.assign(tt, p);
  };
  const lamMoi = () => {
    const dem = pvApi.statusCounts().then((c) => {
      if (!pvConSong(phien)) return;
      const tong = pvloTong(c);
      if (tong === null) return;
      tt.tong = tong;
      capNhatTrang();
      ve();
    }).catch((e) => {
      if (!pvConSong(phien)) return;
      console.debug(`status_counts error: ${pvloLoi(e)}`);
    });
    const offset = (tt.trang - 1) * pvloPAGE_SIZE;
    const ds = pvApi.listLogs(pvloPAGE_SIZE, offset).then((rows) => {
      if (!pvConSong(phien)) return;
      tt.logs = Array.isArray(rows) ? rows : [];
      tt.rong = tt.logs.length === 0;
      ve();
    }).catch((e) => {
      if (!pvConSong(phien)) return;
      pvThongBao("Lỗi", pvloLoi(e), "critical"); // không chờ đóng hộp: pvLoVe xong ngay, hộp tự đóng khi rời trang
    });
    return Promise.all([dem, ds]);
  };
  let dangThongKe = false; // cờ chặn bấm chồng (đặt TRƯỚC await): mỗi lần bấm chỉ mở 1 hộp
  const thongKe = async () => {
    if (dangThongKe) return;
    dangThongKe = true;
    try {
      let s;
      try { s = await pvApi.affiliateStats(); }
      catch (e) {
        if (!pvConSong(phien)) return;
        await pvThongBao("Lỗi", pvloLoi(e), "critical");
        return;
      }
      if (!pvConSong(phien)) return;
      const hop = pvHop({ tieuDe: "📊 Thống kê đổi sản phẩm", html: pvloThongKeHtml(s || {}), nut: [{ ma: "dong", chu: "Đóng", chinh: false }] });
      await hop.cho;
    } finally {
      dangThongKe = false;
    }
  };
  const chiTiet = (i) => {
    if (!(i >= 0 && i < tt.logs.length)) return;
    const l = tt.logs[i] && typeof tt.logs[i] === "object" ? tt.logs[i] : {};
    pvHop({ tieuDe: `Chi tiết log #${pvloPy(l.id)}`, html: pvloChiTietHtml(l), nut: [{ ma: "dong", chu: "Đóng", chinh: false }] });
  };
  khung.addEventListener("click", (ev) => {
    const b = ev.target && typeof ev.target.closest === "function" ? ev.target.closest("[data-pvlo]") : null;
    if (!b || b.disabled || !pvConSong(phien)) return;
    const viec = b.dataset.pvlo;
    if (viec === "lammoi") lamMoi();
    else if (viec === "thongke") thongKe();
    else if (viec === "truoc") {
      if (tt.trang > 1) { tt.trang -= 1; lamMoi(); }
    } else if (viec === "sau") {
      if (tt.trang < pvloSoTrang(tt.tong)) { tt.trang += 1; lamMoi(); }
    } else if (viec === "dong") chiTiet(Number(b.dataset.pvloI));
  });
  await lamMoi();
}
