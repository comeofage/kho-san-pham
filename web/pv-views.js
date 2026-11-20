// Poster V2 trên web — trang Views (#/poster/views). Bê nguyên E:/tool/tiktok_poster_v2/src/desktop/pages/views.py (ViewsPage):
// tiêu đề "📈 Views Analytics" + nút 🔄 Refresh (chạy scraper), hàng lọc Tất cả/Hot/Warm/Cold/Dead, 4 thẻ đếm, bảng 9 cột có biểu đồ
// 8 ngày, trạng thái rỗng. Thiết kế: docs/poster-v2-tren-web.md §6.3–§6.5, phiếu W-P2. Tiền tố pvvi. Khung gọi pvViVe(khung, phien).
//
// LỖI GỐC GIỮ NGUYÊN (§6.5, có test khoá): views.py:401-413 lọc và đếm theo trường `status`, trong khi API /views/summary trả
// `growth_status` (cột Status của bảng đọc đúng `growth_status`, views.py:428). Hệ quả: chọn Hot/Warm/Cold/Dead → bảng trống, 4 thẻ
// đếm luôn 0. KHÔNG sửa ở đây — sửa phải sửa ở app gốc Poster V2.
"use strict";

// --- pvvi-thuan start ---
// Màu theme.py đổi sang bảng màu web (đỏ / vàng / lam như .pv-do / .pv-vang / .pv-lam của poster.css).
const pvviMAU = { RED: "#d33a3a", YELLOW: "#d98a00", BLUE: "#2f6fdb", GREEN: "var(--ok)", OVERLAY0: "var(--muted)", SURFACE1: "#8c8fa1" };
// GROWTH_STYLE (views.py:212-219): mã → [nhãn, màu].
const pvviGROWTH = {
  hot: ["🔥 Hot", pvviMAU.RED],
  warm: ["📈 Warm", pvviMAU.YELLOW],
  cold: ["❄️ Cold", pvviMAU.BLUE],
  flat: ["➖ Flat", pvviMAU.OVERLAY0],
  dead: ["💀 Dead", pvviMAU.SURFACE1],
  unknown: ["❓ ?", pvviMAU.OVERLAY0],
};
// FILTERS (views.py:255-261).
const pvviLOC = [["all", "Tất cả"], ["hot", "🔥 Hot"], ["warm", "📈 Warm"], ["cold", "❄️ Cold"], ["dead", "💀 Dead"]];
const pvviTHE = ["hot", "warm", "cold", "dead"];
const pvviCOT = ["Product ID", "Folder", "Account", "Status", "Today", "Growth%", "Avg/day", "Total (8d)", "Trend (D-7 → D-0)"];

// str() của Python cho giá trị lấy bằng dict.get(k, ""): thiếu → "", None → "None".
function pvviPy(v) {
  return v === undefined ? "" : v === null ? "None" : String(v);
}
const pvviSo = (v) => Number(v) || 0;
// f"{x:,}"
function pvviPhay(v) {
  return Number.isInteger(v) ? v.toLocaleString("en-US") : v.toLocaleString("en-US", { maximumFractionDigits: 17 });
}
// f"{x:,.1f}"
function pvviPhay1(v) {
  return v.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}
// f"{x:+.1f}%"
function pvviTang(v) {
  return `${v >= 0 ? "+" : "-"}${Math.abs(v).toFixed(1)}%`;
}

// _on_loaded (views.py:391-393): dict → items; còn lại coi là danh sách.
function pvviItems(payload) {
  const ds = payload && typeof payload === "object" && !Array.isArray(payload) ? payload.items : payload;
  return Array.isArray(ds) ? ds : [];
}

// _render (views.py:401-413) — LỖI GỐC: lọc + đếm theo `status`, không theo `growth_status`.
function pvviLoc(items, loc) {
  return loc === "all" ? [...items] : items.filter((it) => ((it && it.status) || "unknown") === loc);
}
function pvviDem(items) {
  const c = { hot: 0, warm: 0, cold: 0, dead: 0 };
  for (const it of items) {
    const st = (it && it.status) || "unknown";
    if (Object.prototype.hasOwnProperty.call(c, st)) c[st] += 1;
  }
  return c;
}

// _populate_row (views.py:424-471).
function pvviDong(item) {
  const it = item && typeof item === "object" ? item : {};
  const status = it.growth_status || "unknown";
  const [nhan, mau] = Object.prototype.hasOwnProperty.call(pvviGROWTH, status) ? pvviGROWTH[status] : pvviGROWTH.unknown;
  const growth = pvviSo(it.growth_rate);
  return {
    fid: pvviPy(it.folder_id),
    productId: pvviPy(it.product_id),
    folder: String(it.folder_name || `#${pvviPy(it.folder_id)}`),
    account: String(it.account_name || `#${pvviPy(it.account_id)}`),
    nhan,
    mau,
    today: pvviPhay(pvviSo(it.views_d0)),
    growth: pvviTang(growth),
    mauGrowth: growth > 0 ? pvviMAU.GREEN : growth < 0 ? pvviMAU.RED : "",
    avg: pvviPhay1(pvviSo(it.avg_daily_views)),
    total: pvviPhay(pvviSo(it.total_views)),
    // views_d7 cũ nhất → views_d0 mới nhất
    lichSu: [7, 6, 5, 4, 3, 2, 1, 0].map((d) => pvviSo(it[`views_d${d}`])),
  };
}

// _GrowthBars (views.py:222-249): 8 cột, cao ∝ giá trị/max (tối thiểu 2), độ đậm 0.4 → 1.0 từ cũ tới mới, màu theme.BLUE.
function pvviCot(values) {
  const H = 40;
  const maxV = Math.max(...values) || 1;
  const n = values.length;
  const rect = values.map((v, i) => {
    const h = Math.max(2, Math.trunc((v / maxV) * (H - 4)));
    return `<rect x="${i + 0.06}" y="${H - h - 2}" width="0.8" height="${h}" fill="${pvviMAU.BLUE}" fill-opacity="${(0.4 + 0.6 * ((i + 1) / n)).toFixed(3)}"/>`;
  }).join("");
  return `<svg viewBox="0 0 ${n} ${H}" preserveAspectRatio="none" height="${H}" style="display:block;width:100%;min-width:120px" aria-hidden="true">${rect}</svg>`;
}

// widgets/common.py _friendly_error: chữ lỗi hiện trong hộp "Lỗi" (giữ nguyên chữ không dấu của bản gốc).
function pvviLoi(e) {
  const msg = String(e && e.message ? e.message : e);
  if (msg.includes("401")) return "Khong co quyen truy cap (401). Kiem tra API token trong .env.";
  if (msg.includes("404")) return "API khong ton tai (404). Kiem tra backend co dang chay khong.";
  if ((e && e.status === 0) || msg.includes("Connection")) return "Khong ket noi duoc backend. Hay kiem tra V2 Backend da chay chua.";
  if (msg.toLowerCase().includes("timeout")) return "Backend phan hoi cham (timeout). Thu lai sau.";
  return `${e && e.status ? "HTTPError" : "Error"}: ${msg.slice(0, 200)}`;
}

// Chi tiết từng video của một dòng (folder + UID). Dữ liệu: GET /api/v2/views/videos. View mỗi ngày = chênh lệch 2 snapshot liên tiếp.
function pvviChiTiet(ds) {
  if (ds === undefined || ds === "tai") return `<tr><td colspan="9" class="muted" style="padding:10px 16px">Đang tải video…</td></tr>`;
  if (typeof ds === "string") return `<tr><td colspan="9" style="padding:10px 16px;color:${pvviMAU.RED}">${esc(ds)}</td></tr>`;
  if (!ds.length) return `<tr><td colspan="9" class="muted" style="padding:10px 16px">Chưa có snapshot video nào cho dòng này.</td></tr>`;
  const ngay = (d) => (d === 0 ? "Hôm nay" : `D-${d}`);
  const hang = ds.map((v) => {
    const cap = String(v.caption || v.video_filename || v.video_id || "");
    const ten = v.url ? `<a href="${esc(v.url)}" target="_blank" rel="noopener noreferrer">${esc(cap.slice(0, 60))}</a>` : esc(cap.slice(0, 60));
    const cells = [0, 1, 2, 3, 4, 5, 6, 7].map((d) => `<td>${esc(pvviPhay(pvviSo(v[`views_d${d}`])))}</td>`).join("");
    return `<tr><td>${ten}</td><td>${esc(pvviPy(v.posted_at))}</td><td>${esc(pvviPhay(pvviSo(v.total_views)))}</td>${cells}<td>${esc(pvviPhay(pvviSo(v.gain_8d)))}</td></tr>`;
  }).join("");
  return `<tr><td colspan="9" style="padding:6px 16px 14px;background:rgba(0,0,0,.03)"><div class="pv-cuon"><table class="pv-bang">
    <thead><tr><th>Video (${ds.length})</th><th>Đăng lúc</th><th>Tổng view</th>${[0, 1, 2, 3, 4, 5, 6, 7].map((d) => `<th>${ngay(d)}</th>`).join("")}<th>Tăng 8 ngày</th></tr></thead>
    <tbody>${hang}</tbody></table></div></td></tr>`;
}

// Toàn trang. tt = { items, loc, daTai }. Trạng thái rỗng chỉ hiện sau lần tải đầu (views.py: empty_state.hide() lúc dựng).
function pvviHtml(tt) {
  const items = Array.isArray(tt.items) ? tt.items : [];
  const dem = pvviDem(items);
  const rong = tt.daTai && items.length === 0;
  const loc = pvviLoc(items, tt.loc);
  const bang = rong
    ? `<div class="center muted" style="padding:40px" data-pvvi-rong><div style="font-size:48px">📭</div>
      <div style="font-size:16px;color:var(--text)">Chưa có dữ liệu view</div><div>Bấm 'Refresh' để chạy scraper một lần.</div></div>`
    : `<div class="pv-cuon"><table class="pv-bang"><thead><tr>${pvviCOT.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${
      loc.map(pvviDong).map((r) => `<tr>
      <td data-pvvi="chitiet" data-pvvi-fid="${esc(r.fid)}" data-pvvi-pid="${esc(r.productId)}" style="white-space:nowrap;cursor:pointer;text-decoration:underline dotted" title="Bấm để xem từng video">${esc(r.productId)}</td><td>${esc(r.folder)}</td><td>${esc(r.account)}</td>
      <td style="color:${r.mau}">${esc(r.nhan)}</td><td>${esc(r.today)}</td>
      <td${r.mauGrowth ? ` style="color:${r.mauGrowth}"` : ""}>${esc(r.growth)}</td><td>${esc(r.avg)}</td><td>${esc(r.total)}</td>
      <td style="min-width:120px;width:18%">${pvviCot(r.lichSu)}</td></tr>${tt.mo === r.fid + "|" + r.productId ? pvviChiTiet(tt.ct && tt.ct[tt.mo]) : ""}`).join("")}</tbody></table></div>`;
  return `<div class="pvvi">
  <div class="pv-cong-cu"><h2 style="margin:0">📈 Views Analytics</h2><span class="pv-gian"></span>
    <button type="button" class="btn ghost" data-pvvi="lammoi">🔄 Refresh</button></div>
  <div class="pv-cong-cu"><span class="muted">Lọc:</span>${pvviLOC.map(([ma, nhan]) =>
    `<button type="button" class="btn${tt.loc === ma ? "" : " ghost"}" data-pvvi="loc" data-pvvi-loc="${ma}" aria-pressed="${tt.loc === ma}">${esc(nhan)}</button>`).join("")}</div>
  <div class="pv-luoi" style="margin-bottom:10px">${pvviTHE.map((k) => `<div class="pv-the" data-pvvi-the="${k}" style="border-left:4px solid ${pvviGROWTH[k][1]}">
    <div style="color:${pvviGROWTH[k][1]};font-weight:700">${esc(pvviGROWTH[k][0])}</div>
    <div style="font-size:20px;font-weight:700">${dem[k]}</div></div>`).join("")}</div>
  ${bang}
</div>`;
}
// --- pvvi-thuan end ---

// Khung gọi khi mở tab Views. refresh() = views_summary; lỗi → hộp "Lỗi" (critical). 🔄 Refresh = _refresh_now (views.py:379-389):
// toast "Đang fetch view counts..." → views_refresh → toast "Đã scrape N dòng" + tải lại; lỗi → hộp "Lỗi".
async function pvViVe(khung, phien) {
  const tt = { items: [], loc: "all", daTai: false, mo: "", ct: {} };
  const ve = () => { khung.innerHTML = pvviHtml(tt); };
  ve();
  const taiLai = async () => {
    try {
      const p = await pvApi.viewsSummary();
      if (!pvConSong(phien)) return;
      tt.items = pvviItems(p);
      tt.daTai = true;
      ve();
    } catch (e) {
      if (!pvConSong(phien)) return;
      pvThongBao("Lỗi", pvviLoi(e), "critical"); // không chờ đóng hộp: pvViVe xong ngay, hộp tự đóng khi rời trang
    }
  };
  let dangScrape = false; // cờ chặn bấm 🔄 Refresh chồng (đặt TRƯỚC await): views_refresh chạy scraper, không gửi 2 lần
  const scrape = async () => {
    if (dangScrape) return;
    dangScrape = true;
    try {
      toast("Đang fetch view counts...");
      let r;
      try { r = await pvApi.viewsRefresh(); }
      catch (e) {
        if (!pvConSong(phien)) return;
        await pvThongBao("Lỗi", pvviLoi(e), "critical");
        return;
      }
      if (!pvConSong(phien)) return;
      const rows = r && typeof r === "object" && !Array.isArray(r) && "rows" in r ? pvviPy(r.rows) : "0";
      toast(`Đã scrape ${rows} dòng`);
      await taiLai();
    } finally {
      dangScrape = false;
    }
  };
  khung.addEventListener("click", (ev) => {
    const b = ev.target && typeof ev.target.closest === "function" ? ev.target.closest("[data-pvvi]") : null;
    if (!b || !pvConSong(phien)) return;
    if (b.dataset.pvvi === "lammoi") scrape();
    else if (b.dataset.pvvi === "chitiet") {
      if (ev.target.closest("a")) return;
      const khoa = `${b.dataset.pvviFid}|${b.dataset.pvviPid}`;
      if (tt.mo === khoa) { tt.mo = ""; ve(); return; }
      tt.mo = khoa;
      if (!Array.isArray(tt.ct[khoa])) {
        tt.ct[khoa] = "tai";
        ve();
        pvApi.viewsVideos({ folder_id: b.dataset.pvviFid, product_id: b.dataset.pvviPid }).then((r) => {
          tt.ct[khoa] = r && Array.isArray(r.items) ? r.items : [];
        }).catch((e) => { tt.ct[khoa] = pvviLoi(e); }).finally(() => { if (pvConSong(phien)) ve(); });
      } else ve();
    }
    else if (b.dataset.pvvi === "loc" && pvviLOC.some(([ma]) => ma === b.dataset.pvviLoc)) {
      tt.loc = b.dataset.pvviLoc; // _on_filter_changed: chỉ vẽ lại, không gọi API
      ve();
    }
  });
  await taiLai();
}
