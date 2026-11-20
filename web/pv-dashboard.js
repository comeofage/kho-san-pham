// Poster V2 trên web — trang Dashboard (#/poster/dashboard). Bê nguyên E:/tool/tiktok_poster_v2/src/desktop/pages/dashboard.py:
// 4 thẻ số (ACCOUNTS / ACTIVE FOLDERS / POSTED TODAY / SUCCESS RATE) + bảng "Hoạt động gần đây" 25 log mới nhất, tự làm mới 10 s.
// Thiết kế: docs/poster-v2-tren-web.md §6.3–§6.5, phiếu W-P2. Tiền tố pvdb. Khung (web/poster.js) gọi pvDbVe(khung, phien).
// Dùng: esc (app.js), pvApi / pvConSong / pvHenGio (poster.js). Chỉ addEventListener (CSP). Mọi chuỗi từ API qua esc.
"use strict";

// --- pvdb-thuan start ---
const pvdbREFRESH_MS = 10_000; // DashboardPage.REFRESH_INTERVAL_MS (dashboard.py:54)

// 4 thẻ y dashboard.py:94-97: [mã, tiêu đề, màu chữ số] (theme.BLUE / GREEN / YELLOW / PINK).
const pvdbTHE = [
  ["accounts", "ACCOUNTS", "#2f6fdb"],
  ["folders", "ACTIVE FOLDERS", "var(--ok)"],
  ["today", "POSTED TODAY", "#d98a00"],
  ["success", "SUCCESS RATE", "#ea76cb"],
];
const pvdbCOT = ["Thời gian", "Video", "Folder", "Trạng thái", "Ghi chú"]; // dashboard.py:116

// _on_data_loaded (dashboard.py:136-142) → giá trị 4 thẻ dạng chữ.
function pvdbSoThe(stats) {
  const s = stats && typeof stats === "object" ? stats : {};
  const success = Number(s.success_rate ?? 0) * 100;
  return {
    accounts: String(s.total_accounts ?? 0),
    folders: String(s.active_folders ?? 0),
    today: String(s.total_videos_today ?? 0),
    success: `${success.toFixed(1)}%`,
  };
}

// Một dòng bảng hoạt động (dashboard.py:149-168): chữ + lớp màu trạng thái (darkGreen / darkRed / darkYellow).
function pvdbDong(log) {
  const l = log && typeof log === "object" ? log : {};
  const st = String(l.status || "").toUpperCase();
  let mau = "";
  if (["DONE", "SUCCESS", "INFO"].includes(st)) mau = "pv-xanh";
  else if (["FAILED", "ERROR"].includes(st)) mau = "pv-do";
  else if (["RUNNING", "WARNING"].includes(st)) mau = "pv-vang";
  return {
    t: String(l.created_at || "").slice(0, 19).replace(/T/g, " "),
    v: String(l.video_filename || "—"),
    f: String(l.folder_id || "—"),
    st,
    mau,
    msg: String(l.message || "").slice(0, 120),
  };
}

// "HH:MM:SS" giờ máy đang mở web (datetime.now().strftime("%H:%M:%S")).
function pvdbGio(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

// Toàn trang. tt = { the: pvdbSoThe(...), luc: "HH:MM:SS" | "", logs: [] }.
function pvdbHtml(tt) {
  const the = tt.the || { accounts: "0", folders: "0", today: "0", success: "0%" }; // giá trị khởi tạo StatCard (dashboard.py:94-97)
  const dong = (Array.isArray(tt.logs) ? tt.logs : []).map(pvdbDong).map((r) => `<tr>
      <td style="white-space:nowrap">${esc(r.t)}</td><td style="white-space:nowrap">${esc(r.v)}</td>
      <td style="white-space:nowrap">${esc(r.f)}</td><td style="white-space:nowrap"${r.mau ? ` class="${r.mau}"` : ""}>${esc(r.st)}</td>
      <td>${esc(r.msg)}</td></tr>`).join("");
  return `<div class="pvdb">
  <div class="pv-cong-cu"><h2 style="margin:0">Dashboard</h2><span class="pv-gian"></span>
    <span class="pv-nho" id="pvdb-luc">${tt.luc ? esc(`Cập nhật lúc: ${tt.luc}`) : ""}</span>
    <button type="button" class="btn ghost" data-pvdb="lammoi">↻ Refresh</button></div>
  <div class="pv-luoi">${pvdbTHE.map(([ma, tieuDe, mau]) => `<div class="pv-the" data-pvdb-the="${ma}">
    <div class="pv-nho" style="font-weight:700;letter-spacing:1px">${esc(tieuDe)}</div>
    <div style="color:${mau};font-size:26px;font-weight:700">${esc(the[ma])}</div></div>`).join("")}</div>
  <div class="pv-cong-cu" style="margin-top:14px"><strong>📋 Hoạt động gần đây (Recent Activity)</strong></div>
  <div class="pv-cuon"><table class="pv-bang"><thead><tr>${pvdbCOT.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${dong}</tbody></table></div>
</div>`;
}
// --- pvdb-thuan end ---

// Khung gọi khi mở tab Dashboard. Như dashboard.py: tải ngay + QTimer 10 s (qua pvHenGio: ngừng khi rời trang / ẩn tab / đăng xuất /
// lượt trước chưa xong). Lỗi tải chỉ ghi console (dashboard.py:170-171 logger.warning) — giữ nguyên, không hộp lỗi.
async function pvDbVe(khung, phien) {
  const tt = { the: null, luc: "", logs: [] };
  khung.innerHTML = pvdbHtml(tt);
  let dang = false; // cờ chặn chạy chồng (nút ↻ Refresh + hẹn giờ) đặt TRƯỚC await
  const tai = async () => {
    if (dang) return;
    dang = true;
    try {
      // worker(): get_stats rồi list_logs(limit=25), tuần tự như dashboard.py:129-132.
      const st = await pvApi.getStats();
      if (!pvConSong(phien)) return;
      const lgs = await pvApi.listLogs(25);
      if (!pvConSong(phien)) return;
      tt.the = pvdbSoThe(st);
      tt.luc = pvdbGio(new Date());
      tt.logs = Array.isArray(lgs) ? lgs : [];
      khung.innerHTML = pvdbHtml(tt);
    } catch (e) {
      if (!pvConSong(phien)) return;
      console.warn(`Dashboard refresh failed: ${e && e.message ? e.message : e}`);
    } finally {
      dang = false;
    }
  };
  khung.addEventListener("click", (ev) => {
    const b = ev.target && typeof ev.target.closest === "function" ? ev.target.closest("[data-pvdb]") : null;
    if (b && b.dataset.pvdb === "lammoi" && pvConSong(phien)) tai();
  });
  pvHenGio(tai, pvdbREFRESH_MS); // đăng ký TRƯỚC await để gắn đúng phiên hiện tại
  await tai();
}
