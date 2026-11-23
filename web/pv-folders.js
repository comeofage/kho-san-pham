// Poster V2 trên web — trang Folders (#/poster/folders). Port 1:1 E:/tool/tiktok_poster_v2/src/desktop/pages/folders.py
// (FoldersPage + _FolderCard + _FolderEditDialog) và src/core/cadence.py (normalize / is_due / label). Phiếu W-P4,
// docs/poster-v2-tren-web.md §3, §5.2–§5.3, §6.3–§6.5. Đối chiếu bản Svelte a55d687:src/lib/components/poster/pages/Folders.svelte.
// Script thường, chung phạm vi toàn cục: mọi tên cấp đỉnh bắt đầu "pvfo" (P2-7), lớp CSS "pvfo-". Khung gọi pvFoVe(khung, phien).
// Chỉ gọi qua pvApi; hộp thoại qua pvXacNhan / pvThongBao / pvHop (poster.js); mọi chuỗi từ API qua esc; sự kiện qua addEventListener.
// Khác desktop có chủ đích (§5.3, §6.5): không nút "📁 Browse" (gõ đường dẫn), 🔌 Test local gọi route _dem của máy nhà,
// dòng trạng thái đang tải / lỗi tải (desktop chỉ ghi log), hộp Dự báo có nút Đóng, khoá nút ghi trong lúc gửi.
"use strict";

// --- pvfo-thuan start ---
const pvfoSAP_XEP = [["Mới tạo nhất", "created_desc"], ["Cũ nhất", "created_asc"], ["Tên A → Z", "name_asc"],
  ["Tên Z → A", "name_desc"], ["Đã đăng nhiều nhất", "posted_desc"], ["Đã đăng ít nhất", "posted_asc"]]; // _SORT_OPTIONS
const pvfoAI_XEM = [["Mọi người", "everyone"], ["Bạn bè", "friends"], ["Riêng tư", "private"]]; // vis_map
const pvfoMAX_LICH = 31; // cadence.MAX_CADENCE_DAYS

// int(v or d) của Python; chuỗi không phải số nguyên / NaN → d (Python sẽ ném, trang desktop vỡ thẻ: ở web giữ giá trị mặc định).
function pvfoInt(v, d) {
  const x = v || d;
  if (typeof x === "boolean") return x ? 1 : 0;
  if (typeof x === "number") return Number.isFinite(x) ? Math.trunc(x) : d;
  if (typeof x === "string" && /^\s*[+-]?\d+\s*$/.test(x)) return parseInt(x, 10);
  return d;
}
// str() của Python cho giá trị hiển thị trong f-string (None / True / False).
function pvfoPy(v) {
  if (v === undefined || v === null) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  return String(v);
}
const pvfoKep = (n, a, b) => Math.max(a, Math.min(b, n));

// cadence.normalize
function pvfoChuanHoa(n, phase) {
  const nn = pvfoKep(pvfoInt(n, 1), 1, pvfoMAX_LICH);
  return [nn, pvfoKep(pvfoInt(phase, 1), 1, nn)];
}
// Ngày trong tháng theo giờ máy nhà (Asia/Ho_Chi_Minh) — desktop dùng date.today() của máy nhà.
function pvfoNgayNay(d = new Date()) {
  return Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Ho_Chi_Minh", day: "numeric" }).format(d));
}
// cadence.is_due; ngay = ngày trong tháng (1..31), mặc định hôm nay.
function pvfoDenLuot(n, phase, ngay) {
  const [nn, ph] = pvfoChuanHoa(n, phase);
  if (nn === 1) return true;
  const d = ngay === undefined ? pvfoNgayNay() : ngay;
  return (d - 1) % nn === ph - 1;
}
// cadence.label
function pvfoNhanLich(n, phase) {
  const [nn, ph] = pvfoChuanHoa(n, phase);
  if (nn === 1) return "Mỗi ngày";
  if (nn === 2) return ph === 1 ? "Ngày lẻ" : "Ngày chẵn";
  const dau = [];
  for (let d = ph; d < ph + 3 * nn; d += nn) dau.push(d);
  return `${nn} ngày: ${dau.join("-")}…`;
}
// combo_cadence (folders.py:408-419): Mỗi ngày, (n, pha) n=2..5, "Tự cân tải: n ngày"; lịch không có sẵn → thêm cuối.
function pvfoLuaChonLich(n, phase) {
  const ds = [{ chu: pvfoNhanLich(1, 1), tu: false, n: 1, pha: 1 }];
  for (let k = 2; k < 6; k++) for (let p = 1; p <= k; p++) ds.push({ chu: pvfoNhanLich(k, p), tu: false, n: k, pha: p });
  for (let k = 2; k < 6; k++) ds.push({ chu: `Tự cân tải: ${k} ngày`, tu: true, n: k, pha: 0 });
  let chiSo = ds.findIndex((o) => !o.tu && o.n === n && o.pha === phase);
  if (chiSo < 0) { ds.push({ chu: pvfoNhanLich(n, phase), tu: false, n, pha: phase }); chiSo = ds.length - 1; }
  return { ds, chiSo };
}

// _sort_folders (folders.py:879-895). Sắp xếp ổn định; không đổi mảng gốc.
function pvfoSapXep(folders, khoa) {
  const ten = (f) => String((f && f.name) || "").toLowerCase();
  const tao = (f) => String((f && f.created_at) || "");
  const dang = (f) => pvfoInt(f && f.total_posted, 0);
  const ma = (f) => Number((f && f.id) || 0);
  const ss = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const ds = [...(Array.isArray(folders) ? folders : [])];
  switch (khoa) {
    case "name_asc": return ds.sort((a, b) => ss(ten(a), ten(b)));
    case "name_desc": return ds.sort((a, b) => ss(ten(b), ten(a)));
    case "created_asc": return ds.sort((a, b) => ss(tao(a), tao(b)) || ss(ma(a), ma(b)));
    case "posted_desc": return ds.sort((a, b) => ss(dang(b), dang(a)) || ss(ten(a), ten(b)));
    case "posted_asc": return ds.sort((a, b) => ss(dang(a), dang(b)) || ss(ten(a), ten(b)));
    default: return ds.sort((a, b) => ss(tao(b), tao(a)) || ss(ma(b), ma(a)));
  }
}

// _FolderCard: trạng thái 1 thẻ. so = ô "Videos:" ban đầu (folders.py:376-390), homQua = tooltip "Số video đăng hôm qua".
function pvfoTheMoi(f, ngay) {
  const vpd = "videos_per_day" in f ? f.videos_per_day : 1;
  let homQua = f.last_day_count ?? null;
  const [n, ph] = pvfoChuanHoa(f.cadence_days, f.cadence_phase);
  let dau;
  if (n > 1) {
    // Folder đăng theo cadence: hôm nay đến lượt thì mặc định videos_per_day (hôm qua nghỉ là bình thường), không thì 0.
    dau = pvfoDenLuot(n, ph, ngay) ? (vpd || 1) : 0;
    if (dau) homQua = null;
  } else if (homQua === null) dau = vpd || 1;
  else dau = homQua;
  const { ds, chiSo } = pvfoLuaChonLich(n, ph);
  return { f, id: f.id, chon: false, so: pvfoKep(pvfoInt(dau, 0), 0, 100), daSua: false, homQua, ds, chiSo, truoc: null };
}
// wants_force_cadence: người dùng tự nhập số > 0 cho folder hôm nay không đến lượt.
function pvfoMuonEp(c, ngay) {
  const [n, ph] = pvfoChuanHoa(c.f.cadence_days, c.f.cadence_phase);
  return c.daSua && c.so > 0 && !pvfoDenLuot(n, ph, ngay);
}
// lbl_selected_summary
function pvfoTomTat(the, daTai) {
  if (!daTai) return "0 folder được chọn";
  const chon = the.filter((c) => c.chon);
  return `${chon.length} folder được chọn • ${chon.reduce((s, c) => s + c.so, 0)} video`;
}
const pvfoMaAiXem = (chu) => (pvfoAI_XEM.find((x) => x[0] === chu) || [, "everyone"])[1];
// payload _do_add_queue_batch (folders.py:1120-1126)
function pvfoPayloadQueue(chon, gio, aiXem, ngay) {
  const dem = {};
  for (const c of chon) dem[String(c.id)] = c.so;
  return { folder_ids: chon.map((c) => c.id), video_counts: dem, force_folder_ids: chon.filter((c) => pvfoMuonEp(c, ngay)).map((c) => c.id),
    window_hours: gio, visibility: pvfoMaAiXem(aiXem) };
}
// on_done của _do_add_queue_batch (folders.py:1131-1146)
function pvfoChuQueue(res) {
  const r = res && typeof res === "object" ? res : {};
  let cau = `Đã xếp lịch ${pvfoPy("total_queued" in r ? r.total_queued : 0)} video vào hàng chờ Queue!`;
  const bo = Array.isArray(r.skipped_not_due) ? r.skipped_not_due : [];
  if (bo.length) {
    const ten = [...new Set(bo.map((x) => (x && x.folder_name) || pvfoPy(x && x.folder_id)))].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
    cau += `\n\nBỏ ${bo.length} video vì slot rơi vào ngày folder nghỉ theo lịch:\n${ten.slice(0, 10).join(", ")}`;
  }
  const tru = Array.isArray(r.reduced_by_posted) ? r.reduced_by_posted : [];
  if (tru.length) {
    cau += "\n\nĐã trừ số video đã đăng/đã xếp cho hôm nay:\n" + tru.slice(0, 10).map((x) =>
      `- ${pvfoPy((x && x.folder_name) || (x && x.folder_id))}: ${pvfoPy(x && x.requested)} - ${pvfoPy(x && x.posted_today)} có sẵn = xếp ${pvfoPy(x && x.queued)}`).join("\n");
  }
  return cau;
}
// on_done của _do_post_now_batch (folders.py:1094-1102)
function pvfoChuDang(started, errors) {
  if (errors.length && started === 0) return { tieuDe: "Lỗi đăng bài", cau: errors.join("\n"), kieu: "critical" };
  let cau = `Đã bắt đầu tiến trình đăng ${started} video.`;
  if (errors.length) cau += "\nMột số lỗi xảy ra:\n" + errors.join("\n");
  return { tieuDe: "Đang đăng", cau, kieu: "info" };
}

// _FolderEditDialog: giá trị ban đầu các ô (folders.py:57-163).
function pvfoMauSua(folder, accounts) {
  const f = folder && typeof folder === "object" ? folder : {};
  const ds = Array.isArray(accounts) ? accounts : [];
  let pool = String(f.caption_pool || "");
  if (pool.startsWith("[")) {
    try {
      const d = JSON.parse(pool);
      if (Array.isArray(d) && d.every((x) => typeof x === "string")) pool = d.join("\n");
    } catch (e) { /* giữ nguyên chuỗi như desktop */ }
  }
  const src = "source" in f ? f.source : "local";
  const vis = "visibility" in f ? f.visibility : "everyone";
  const coTk = ds.some((a) => a && a.id === f.account_id && f.account_id !== undefined);
  return {
    name: String(f.name ?? ""),
    source: ["local", "drive"].includes(src) ? src : "local",
    account_id: coTk ? f.account_id : null,
    path: String(f.path || ""),
    product_id: String(f.product_id || "").replaceAll(",", "\n"),
    product_id_active: String(f.product_id_active || "").replaceAll(",", "\n"),
    pid_tick: new Map(),
    pid_goc: new Set(pvfoDsPid(f.product_id)),
    pid_dem: f.product_posted_counts && typeof f.product_posted_counts === "object" ? f.product_posted_counts : {},
    product_name: String(f.product_name || ""),
    caption_pool: pool,
    videos_per_day: pvfoKep(pvfoInt(f.videos_per_day, 1), 1, 100),
    post_times: String(("post_times" in f ? f.post_times : '["08:00"]') || '["08:00"]'),
    campaign_hashtags: String(f.campaign_hashtags || ""),
    first_comment: String(f.first_comment || ""),
    visibility: ["everyone", "friends", "private"].includes(vis) ? vis : "everyone",
    active: "active" in f ? Boolean(f.active) : true,
  };
}
// Ô tick từng Product ID (folders.py _sync_product_checkboxes): ID có sẵn lúc mở hộp lấy theo product_id_active (rỗng = tick hết, folder cũ); ID gõ thêm mặc định tick.
function pvfoDsPid(raw) {
  return [...new Set(String(raw ?? "").replaceAll(",", "\n").split(/\r\n|\r|\n/).map((l) => l.trim()).filter(Boolean))];
}
function pvfoPidTick(o, pid) {
  if (o.pid_tick instanceof Map && o.pid_tick.has(pid)) return !!o.pid_tick.get(pid);
  const dau = pvfoDsPid(o.product_id_active);
  return dau.length === 0 || !(o.pid_goc instanceof Set && o.pid_goc.has(pid)) || dau.includes(pid);
}
// "· đã đăng N video" sau UID (số video queue 'done' theo product_id, từ GET /folders/ → product_posted_counts); không có số thì để trống.
function pvfoPidDem(o, pid) {
  const n = o.pid_dem && Object.hasOwn(o.pid_dem, pid) ? Number(o.pid_dem[pid]) : NaN;
  return Number.isFinite(n) ? ` · đã đăng ${n} video` : "";
}
// QR link sản phẩm cạnh mỗi ID (dùng lại thư viện qrcode + lớp .qr của app): nhỏ, rê chuột/chạm mới phóng to.
const pvfoQrCache = new Map();
function pvfoQr(pid) {
  if (typeof window === "undefined" || typeof window.qrcode !== "function" || !/^\d+$/.test(pid)) return "";
  if (!pvfoQrCache.has(pid)) {
    const q = window.qrcode(0, "M"); q.addData(`https://shop.tiktok.com/vn/pdp/${pid}`); q.make();
    pvfoQrCache.set(pid, q.createSvgTag({ cellSize: 4, margin: 4, scalable: true }));
  }
  const svg = pvfoQrCache.get(pid);
  return `<div class="pvfo-qr" tabindex="0" title="Quét/mở link sản phẩm TikTok"><div class="pvfo-qr-mini">${svg}</div><div class="pvfo-qr-pop">${svg}<div class="small">Quét để mở sản phẩm</div></div></div>`;
}
function pvfoPidHtml(o) {
  const ds = pvfoDsPid(o.product_id);
  return `<p class="pv-nho">${esc("Tick ID muốn đăng (bỏ tick để tạm ngưng, không xoá):")}</p>`
    + ds.map((pid) => `<div class="pvfo-pid-hang"><label class="pvfo-hang"><input type="checkbox" class="pvfo-o-chon" data-pvfo-pid="${esc(pid)}"${pvfoPidTick(o, pid) ? " checked" : ""}> ${esc(pid)}${pvfoPidDem(o, pid)}</label>${pvfoQr(pid)}</div>`).join("");
}
// get_data (folders.py:206-223)
function pvfoDuLieuSua(o) {
  const pids = String(o.product_id).replaceAll(",", "\n").split(/\r\n|\r|\n/).map((l) => l.trim()).filter(Boolean);
  return {
    name: String(o.name).trim(), source: o.source, path: String(o.path).trim(), account_id: o.account_id ?? null,
    product_id: pids.join("\n"), product_id_active: pvfoDsPid(pids.join("\n")).filter((p) => pvfoPidTick(o, p)).join("\n"),
    product_name: String(o.product_name).trim(), caption_pool: String(o.caption_pool).trim(),
    videos_per_day: pvfoKep(pvfoInt(o.videos_per_day, 1), 1, 100), post_times: String(o.post_times).trim() || '["08:00"]',
    campaign_hashtags: String(o.campaign_hashtags).trim(), first_comment: String(o.first_comment).trim(), visibility: o.visibility,
    active: !!o.active,
  };
}

// ----- HTML (mọi chuỗi qua esc) -----
const pvfoMa = (c) => esc(String(c.id));
// Màu pastel riêng cho mỗi account: góc vàng 137.5° theo account_id (id kề nhau vẫn cách xa màu); không có id thì băm tên.
function pvfoHue(f) {
  const id = Number(f && f.account_id);
  if (Number.isFinite(id) && id > 0) return Math.round((id * 137.508) % 360);
  let h = 0; for (const ch of String((f && f.account_name) || "")) h = (h * 31 + ch.codePointAt(0)) % 360;
  return h;
}
// Huy hiệu products: "đang đăng/tổng" khi có ID bị bỏ tick (desktop folders.py _FolderCard).
function pvfoSoPid(f) {
  const tong = "product_id_count" in f ? f.product_id_count : 0;
  const dang = "product_id_active_count" in f ? f.product_id_active_count : tong;
  return dang === tong ? tong : `${dang}/${tong}`;
}
function pvfoTheHtml(c) {
  const f = c.f;
  const ten = "name" in f ? pvfoPy(f.name) : "Unnamed";
  const tk = f.account_name || `Account #${f.account_id || "—"}`;
  const con = "available_videos" in f ? f.available_videos : 0;
  const daDang = pvfoPy("total_posted" in f ? f.total_posted : 0);
  const xem = f.product_name || f.caption || "";
  const vpd = pvfoPy("videos_per_day" in f ? f.videos_per_day : 1);
  const hq = pvfoInt(f.last_day_count, 0), hn = pvfoInt(f.today_count, 0);
  const ma = pvfoMa(c);
  const laLuuTru = Boolean(f.is_archived || 0);
  return `<div class="pvfo-the${c.chon ? " pvfo-the-chon" : ""}" data-pvfo-the="${ma}" style="--tk-h:${pvfoHue(f)}">`
    + `<input type="checkbox" class="pvfo-o-chon" data-pvfo-chon="${ma}"${c.chon ? " checked" : ""} aria-label="Chọn folder ${esc(ten)}">`
    + `<b class="pvfo-ten">${esc(ten)}</b>`
    + `<span class="pvfo-bd pvfo-bd-lam">👤 ${esc(tk)}</span>`
    + `<span class="pvfo-bd ${Number(con) > 0 ? "pvfo-bd-xanh" : "pvfo-bd-do"}">🎬 Còn ${esc(pvfoPy(con))} video</span>`
    + `<span class="pvfo-bd pvfo-bd-ngoc" title="Tổng số video đã đăng từ folder này: ${esc(daDang)}">✅ Đã đăng ${esc(daDang)}</span>`
    + `<span class="pvfo-bd pvfo-bd-vang">🏷️ ${esc(pvfoPy(pvfoSoPid(f)))} products</span>`
    + `<span class="pvfo-bd ${hq > 0 ? "pvfo-bd-xanh" : "pvfo-bd-mo"}" title="Số video đăng thành công hôm qua của folder này.">🕘 Hôm qua: ${hq}</span>`
    + `<span class="pvfo-bd ${hn > 0 ? "pvfo-bd-xanh" : "pvfo-bd-mo"}" title="Số video đã đăng thành công hôm nay của folder này.">📆 Hôm nay: ${hn}</span>`
    + `<span class="pvfo-dk"><label class="pvfo-nho">Videos: <input type="number" class="pvfo-o-so" min="0" max="100" step="1" inputmode="numeric" value="${c.so}" data-pvfo-so="${ma}"`
    + `${c.homQua !== null ? ` title="Số video đăng hôm qua: ${esc(pvfoPy(c.homQua))}"` : ""}></label>`
    + `<select class="pvfo-o-lich" data-pvfo-lich="${ma}" title="Chỉ đăng vào các ngày trong tháng theo chu kỳ này" aria-label="Lịch đăng">`
    + c.ds.map((o, i) => `<option value="${i}"${i === c.chiSo ? " selected" : ""}>${esc(o.chu)}</option>`).join("") + `</select>`
    + `<button type="button" class="btn ghost sm" data-pvfo-luu-tru="${ma}" data-pvfo-ve="${laLuuTru ? "0" : "1"}">${laLuuTru ? "Khôi phục" : "Lưu trữ"}</button>`
    + `<button type="button" class="btn ghost sm" data-pvfo-sua="${ma}">Edit</button>`
    + `<button type="button" class="btn sm pvfo-nut-xoa" data-pvfo-xoa="${ma}">Delete</button></span></div>`;
}
// _render_chips: "Tất cả (n)" + "<tên> (n)" theo account_id; data-pvfo-chip = chỉ số trong accounts (-1 = Tất cả).
function pvfoChipHtml(folders, accounts, locTk) {
  const dem = new Map();
  for (const f of folders) dem.set(f && f.account_id, (dem.get(f && f.account_id) || 0) + 1);
  return `<button type="button" class="chip pvfo-dam${locTk === null ? " on" : ""}" data-pvfo-chip="-1" aria-pressed="${locTk === null}">Tất cả (${folders.length})</button>`
    + accounts.map((a, i) => {
      const id = a ? a.id : undefined;
      const on = locTk !== null && locTk === id;
      return `<button type="button" class="chip${on ? " on" : ""}" data-pvfo-chip="${i}" aria-pressed="${on}">${esc(pvfoPy(a && a.name))} (${dem.get(id) || 0})</button>`;
    }).join("");
}
function pvfoTabsHtml(tab) {
  return [["Hoạt động", 0], ["Lưu trữ", 1]].map(([chu, i]) =>
    `<button type="button" class="pvfo-tab" role="tab" data-pvfo-tab="${i}" aria-selected="${tab === i}">${esc(chu)}</button>`).join("");
}
function pvfoKhungHtml(S) {
  const chon = (ds, gt) => ds.map(([chu, v]) => `<option value="${esc(v)}"${v === gt ? " selected" : ""}>${esc(chu)}</option>`).join("");
  return `<div class="pvfo-trang">
  <div class="pvfo-dau"><h2 class="pvfo-tieu-de">${esc("📁 Folders & Batch Scheduler")}</h2><span class="pvfo-gian"></span>
    <label class="pvfo-nho">Sắp xếp: <select id="pvfo-sap-xep">${chon(pvfoSAP_XEP, S.sapXep)}</select></label>
    <button type="button" class="btn sm" data-pvfo-hd="them">+ Add Folder</button>
    <button type="button" class="btn ghost sm" data-pvfo-hd="du-bao">📊 Dự báo lịch</button>
    <button type="button" class="btn ghost sm" data-pvfo-hd="lam-moi">Refresh</button></div>
  <div class="pvfo-tabs" id="pvfo-tabs" role="tablist">${pvfoTabsHtml(S.tab)}</div>
  <div id="pvfo-tt" role="status"></div>
  <div class="pvfo-chips" id="pvfo-chip"></div>
  <div class="pvfo-ds" id="pvfo-ds"></div>
  <div class="pvfo-lo" role="group" aria-label="Xếp lịch hàng loạt">
    <b id="pvfo-tom-tat">${esc(pvfoTomTat([], false))}</b>
    <button type="button" class="btn sm${S.chonHet ? "" : " ghost"}" data-pvfo-hd="chon-het" aria-pressed="${!!S.chonHet}">Chọn hết tab</button>
    <button type="button" class="btn ghost sm" data-pvfo-hd="hom-qua" title="Chỉ tick các folder (đang hiện) hôm qua đã được đưa vào Queue, bỏ tick các folder khác.">↺ Giống hôm qua</button>
    <label class="pvfo-nho">Đăng trong vòng <input type="number" id="pvfo-gio" class="pvfo-o-so" min="1" max="48" step="1" inputmode="numeric" value="${esc(String(S.gio))}" title="Mỗi video cách nhau ngẫu nhiên 2-10 phút, đăng xong trong khung giờ này"> tiếng</label>
    <label class="pvfo-nho">Ai xem: <select id="pvfo-ai-xem">${chon(pvfoAI_XEM.map(([c]) => [c, c]), S.aiXem)}</select></label>
    <span class="pvfo-gian"></span>
    <button type="button" class="btn sm pvfo-nut-dang" data-pvfo-hd="dang-ngay">⚡ Đăng ngay</button>
    <button type="button" class="btn sm pvfo-nut-queue" data-pvfo-hd="queue">➕ Thêm vào Queue</button>
  </div>
</div>`;
}
// Thân hộp "Thêm folder" / "Sửa folder". Không có nút Browse (§5.3); textarea bắt đầu bằng "\n" vì trình duyệt bỏ 1 dòng trống đầu.
function pvfoHopSuaHtml(o, accounts) {
  const ds = Array.isArray(accounts) ? accounts : [];
  let chonTk = -1;
  ds.forEach((a, i) => { if (o.account_id !== null && a && a.id === o.account_id) chonTk = i; });
  const opt = (v, chu, on) => `<option value="${esc(v)}"${on ? " selected" : ""}>${esc(chu)}</option>`;
  const o1 = (ten, ph, gt) => `<input type="text" name="${ten}" value="${esc(gt)}"${ph ? ` placeholder="${esc(ph)}"` : ""}>`;
  return `<div class="pv-form pvfo-form">
  <span>Tên folder:</span>${o1("name", "Tên folder (bắt buộc)", o.name)}
  <span>Nguồn + Account:</span><div class="pvfo-hang"><select name="source">${["local", "drive"].map((s) => opt(s, s, s === o.source)).join("")}</select>
    <span>Account:</span><select name="account">${opt("-1", "— Không chọn —", chonTk < 0)}${ds.map((a, i) =>
      opt(String(i), `${pvfoPy(a && a.name)} (ID: ${pvfoPy(a && a.id)})`, i === chonTk)).join("")}</select></div>
  <span>Đường dẫn / Drive ID:</span><div><div class="pvfo-hang">${o1("path", "Đường dẫn thư mục hoặc Google Drive ID", o.path)}<button type="button" class="btn ghost sm" data-pvfo-test="">🔌 Test</button></div>
    <p class="pv-nho">Gõ đường dẫn thư mục trên máy nhà, rồi bấm 🔌 Test</p></div>
  <span>TikTok Shop Product IDs:</span><div><textarea name="product_id" rows="3" placeholder="${esc("Nhập các Product ID TikTok Shop (mỗi dòng 1 mã)")}">\n${esc(o.product_id)}</textarea>
    <div data-pvfo-pid-ds="">${pvfoPidHtml(o)}</div></div>
  <span>Tên sản phẩm:</span>${o1("product_name", "Tên sản phẩm hiển thị trên giỏ hàng (tùy chọn)", o.product_name)}
  <span>Caption Pool:</span><textarea name="caption_pool" rows="4" placeholder="${esc("Danh sách caption (mỗi dòng 1 caption hoặc phân cách bởi ---)")}">\n${esc(o.caption_pool)}</textarea>
  <span>${esc("Tần suất & Giờ đăng:")}</span><div class="pvfo-hang"><input type="number" class="pvfo-o-so" name="videos_per_day" min="1" max="100" step="1" inputmode="numeric" value="${esc(String(o.videos_per_day))}">
    <span>video/ngày</span><span>Giờ đăng:</span>${o1("post_times", '["08:00", "12:00", "20:00"]', o.post_times)}</div>
  <span>Campaign Hashtags:</span>${o1("campaign_hashtags", "#campaign #affiliate", o.campaign_hashtags)}
  <span>First Comment:</span>${o1("first_comment", "", o.first_comment)}
  <span>Quyền riêng tư:</span><select name="visibility">${["everyone", "friends", "private"].map((s) => opt(s, s, s === o.visibility)).join("")}</select>
  <span></span><label class="pvfo-hang"><input type="checkbox" class="pvfo-o-chon" name="active"${o.active ? " checked" : ""}> Folder đang hoạt động (Active)</label>
</div>`;
}
// Bảng "Dự báo số video mỗi ngày theo lịch" (folders.py:950-969): cột dd/mm, hàng account_name, ô loads.
function pvfoDuBaoHtml(res) {
  const r = res && typeof res === "object" ? res : {};
  const ngay = Array.isArray(r.dates) ? r.dates : [];
  const tk = Array.isArray(r.accounts) ? r.accounts : [];
  const dau = ngay.map((d) => { const s = String(d); return `<th class="pvfo-giua">${esc(s.slice(8, 10) + "/" + s.slice(5, 7))}</th>`; }).join("");
  const than = tk.map((a) => `<tr><th scope="row">${esc(pvfoPy(a && a.account_name))}</th>${(a && Array.isArray(a.loads) ? a.loads : [])
    .slice(0, ngay.length).map((v) => `<td class="pvfo-giua">${esc(pvfoPy(v))}</td>`).join("")}</tr>`).join("");
  return `<div class="pv-cuon"><table class="pv-bang pvfo-du-bao"><thead><tr><th></th>${dau}</tr></thead><tbody>${than}</tbody></table></div>`;
}
// --- pvfo-thuan end ---

// CSS riêng của trang (CSP style-src có 'unsafe-inline'; không sửa poster.css). Lớp có tiền tố pvfo- (bản Svelte từng vỡ vì lớp "spin").
const pvfoCSS = `
.pvfo-trang { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.pvfo-dau { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.pvfo-tieu-de { margin: 0; font-size: 18px; }
.pvfo-gian { flex: 1; }
.pvfo-nho { display: inline-flex; align-items: center; gap: 4px; color: var(--muted); font-size: 12px; white-space: nowrap; }
.pvfo-trang select, .pvfo-hop select { padding: 4px 6px; border: 1px solid var(--line); border-radius: 6px; background: var(--card); color: var(--text); font: inherit; font-size: 13px; max-width: 100%; }
.pvfo-tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); }
.pvfo-tab { border: 0; border-bottom: 2px solid transparent; background: none; padding: 6px 14px; color: var(--muted); font: inherit; font-weight: 600; cursor: pointer; }
.pvfo-tab[aria-selected="true"] { color: var(--text); border-bottom-color: #2f6fdb; }
.pvfo-tai { margin: 0; color: var(--muted); font-size: 13px; }
.pvfo-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.pvfo-dam { font-weight: 700; }
.pvfo-ds { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.pvfo-the { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; padding: 8px 10px; min-width: 0; border: 1px solid var(--line); border-left: 4px solid hsl(var(--tk-h, 0) 55% 70%); border-radius: 8px; background: color-mix(in srgb, hsl(var(--tk-h, 0) 80% 75%) 22%, var(--card)); cursor: pointer; }
.pvfo-the:hover { border-color: #2f6fdb; }
.pvfo-the-chon { border: 1.5px solid #2f6fdb; border-left: 4px solid #2f6fdb; background: color-mix(in srgb, #2f6fdb 10%, var(--card)); }
.pvfo-o-chon { width: 20px; height: 20px; flex: none; margin: 0; padding: 0; cursor: pointer; }
.pvfo-ten { min-width: 120px; font-size: 14px; overflow-wrap: anywhere; }
.pvfo-bd { padding: 2px 8px; border-radius: 6px; background: color-mix(in srgb, var(--muted) 14%, transparent); font-size: 12px; white-space: nowrap; }
.pvfo-bd-lam { color: var(--text); background: hsl(var(--tk-h, 0) 70% 82% / .8); font-weight: 600; } .pvfo-bd-xanh { color: var(--ok); } .pvfo-bd-do { color: #d33a3a; } .pvfo-bd-ngoc { color: #179299; }
.pvfo-bd-vang { color: #b37400; } .pvfo-bd-tim { color: #8839ef; } .pvfo-bd-mo { color: var(--muted); }
.pvfo-xem { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
.pvfo-dk { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-left: auto; }
.pvfo-o-so { width: 64px; padding: 4px 6px; border-radius: 6px; }
.pvfo-o-lich { width: 150px; }
.pvfo-nut-xoa { background: #f38ba8; color: #11111b; }
.pvfo-nut-dang { background: #89b4fa; color: #11111b; }
.pvfo-nut-queue { background: #a6e3a1; color: #11111b; }
.pvfo-lo { position: sticky; bottom: 0; z-index: 5; display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--card); }
.pvfo-rong { margin: 0; padding: 32px 10px; text-align: center; color: var(--muted); }
.pvfo-rong-ic { display: block; font-size: 40px; }
.pvfo-pid-hang { display: flex; align-items: center; gap: 8px; margin: 2px 0; }
.pvfo-qr { position: relative; flex: none; cursor: zoom-in; outline: none; }
.pvfo-qr svg { display: block; width: 100%; height: auto; }
.pvfo-qr-mini { width: 30px; padding: 2px; background: #fff; border-radius: 6px; border: 1px solid #ccc; }
.pvfo-qr-pop { display: none; position: absolute; right: calc(100% + 8px); left: auto; top: 0; z-index: 20; width: 200px; padding: 10px; background: #fff; color: #333; border-radius: 12px; box-shadow: 0 8px 28px #0005; text-align: center; font-size: 12px; }
.pvfo-qr:hover .pvfo-qr-pop, .pvfo-qr:focus .pvfo-qr-pop { display: block; }
.pvfo-hang { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; min-width: 0; }
.pvfo-hang > input[type="text"] { flex: 1; min-width: 160px; width: auto; }
.pvfo-form textarea { min-height: 60px; }
.pvfo-giua { text-align: center; }
.pv-hop.pvfo-hop-rong { width: min(980px, 96vw); }
/* Desktop: mỗi folder đúng 1 hàng, gọn */
@media (min-width: 900px) {
  .pvfo-ds { gap: 1px; }
  .pvfo-the { flex-wrap: nowrap; padding: 0 8px; gap: 5px; line-height: 1.2; border-radius: 6px; }
  .pvfo-o-chon { width: 16px; height: 16px; }
  .pvfo-ten { flex: 1 1 90px; min-width: 60px; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pvfo-bd { padding: 0 6px; font-size: 11px; flex: none; }
  .pvfo-xem { flex: 0 1 110px; min-width: 0; font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pvfo-dk { flex-wrap: nowrap; flex: none; gap: 4px; }
  .pvfo-nho { font-size: 11px; white-space: nowrap; }
  .pvfo-o-so { width: 48px; padding: 0 4px; height: 22px; line-height: 1.2; font-size: 12px; border-radius: 4px; box-sizing: border-box; }
  .pvfo-o-lich { width: 105px; padding: 2px 4px; height: auto; line-height: 1.3; font-size: 12px; box-sizing: border-box; }
  .pvfo-the .btn.sm { padding: 0 8px; height: 22px; font-size: 12px; line-height: 1; border-radius: 5px; }
}
@media (min-width: 900px) and (max-width: 1399.98px) { .pvfo-xem { display: none; } }
@media (max-width: 899.98px) {
  body[data-vai="chu"] .pvfo-lo { bottom: calc(var(--mn-day) + env(safe-area-inset-bottom)); }
  .pvfo-dk { margin-left: 0; }
}
`;
function pvfoNapCss() {
  if (document.getElementById("pvfo-css")) return;
  const st = document.createElement("style");
  st.id = "pvfo-css";
  st.textContent = pvfoCSS;
  document.head.append(st);
}

const pvfoChuE = (e) => String(e && e.message ? e.message : e);
const pvfoQ = (S, sel) => S.khung.querySelector(sel);
const pvfoTimThe = (S, id) => S.the.find((c) => String(c.id) === String(id));

// Khung gọi khi mở tab Folders. Trạng thái trang nằm trong S (đóng gói theo phiên, không biến toàn cục).
async function pvFoVe(khung, phien) {
  pvfoNapCss();
  const S = { phien, khung, tab: 0, sapXep: "created_desc", locTk: null, folders: [], accounts: [], the: [], daTai: false,
    chonHet: false, gio: 4, aiXem: "Mọi người", lanTai: 0, dangTai: false, loiTai: null, dangGui: false };
  khung.innerHTML = pvfoKhungHtml(S);
  khung.addEventListener("click", (ev) => pvfoBam(S, ev));
  khung.addEventListener("change", (ev) => pvfoDoi(S, ev));
  khung.addEventListener("input", (ev) => pvfoGo(S, ev));
  await pvfoTai(S);
}

// refresh_async: list_accounts rồi GET /api/v2/folders/?archived=0|1. Lần đầu có thể ~84 s: pvGoi tự chờ 202/_kq; bấm Refresh lúc đang
// chờ gửi lại đúng request đó → video_server gắn vào lần quét đang chạy (§3.3). Mỗi lần tải có số thứ tự: kết quả của lần cũ (vd tab
// trước) về muộn thì bỏ, không đè.
async function pvfoTai(S) {
  const lan = ++S.lanTai;
  const archived = S.tab === 1 ? "1" : "0";
  const conDung = () => pvConSong(S.phien) && lan === S.lanTai;
  S.dangTai = true; S.loiTai = null;
  pvfoVeTrangThai(S);
  let tk, fo;
  try {
    tk = await pvApi.listAccounts();
    if (!conDung()) return;
    fo = await pvApi.getFolders(archived);
  } catch (e) {
    if (!conDung() || (e && e.roiTrang)) return;
    S.dangTai = false; S.loiTai = e;
    pvfoVeTrangThai(S);
    return;
  }
  if (!conDung()) return;
  S.accounts = Array.isArray(tk) ? tk : [];
  S.folders = Array.isArray(fo) ? fo : [];
  S.dangTai = false; S.daTai = true;
  pvfoVeTrangThai(S);
  pvfoDungThe(S);
  pvfoVeDs(S);
}
function pvfoVeTrangThai(S) {
  const el = pvfoQ(S, "#pvfo-tt");
  if (!el) return;
  if (S.dangTai) {
    el.innerHTML = `<p class="pvfo-tai">⏳ Đang tải danh sách folder… Lần đầu máy nhà phải quét thư mục, có thể mất 1–2 phút.</p>`;
  } else if (S.loiTai) {
    // Lỗi tạm (mạng, máy nhà tắt, bận, quá giờ) → gợi ý thử lại; lỗi vĩnh viễn (403 bản quyền, 404…) chỉ hiện chữ lỗi.
    el.innerHTML = `<p class="err">Không tải được danh sách folder: ${esc(pvfoChuE(S.loiTai))}${S.loiTai.tam ? " Bấm Refresh để thử lại." : ""}</p>`;
  } else el.innerHTML = "";
}
// _render_cards: lọc theo account, sắp xếp, dựng thẻ mới (bỏ chọn, ô Videos về mặc định).
function pvfoDungThe(S) {
  const loc = S.folders.filter((f) => f && typeof f === "object" && (S.locTk === null || f.account_id === S.locTk));
  const ngay = pvfoNgayNay();
  S.the = pvfoSapXep(loc, S.sapXep).map((f) => pvfoTheMoi(f, ngay));
}
function pvfoVeDs(S) {
  const chip = pvfoQ(S, "#pvfo-chip");
  if (chip) chip.innerHTML = S.daTai ? pvfoChipHtml(S.folders, S.accounts, S.locTk) : "";
  pvfoVeThe(S, true);
  pvfoVeChonHet(S);
}
function pvfoVeThe(S, tomTat) {
  const ds = pvfoQ(S, "#pvfo-ds");
  if (ds) {
    ds.innerHTML = !S.daTai ? "" : S.the.length ? S.the.map(pvfoTheHtml).join("")
      : `<p class="pvfo-rong"><span class="pvfo-rong-ic" aria-hidden="true">📭</span>Không có folder nào trong danh sách này.</p>`;
  }
  if (tomTat) pvfoVeTomTat(S);
}
function pvfoVeTomTat(S) {
  const el = pvfoQ(S, "#pvfo-tom-tat");
  if (el) el.textContent = pvfoTomTat(S.the, S.daTai);
}
function pvfoVeChonHet(S) {
  const b = pvfoQ(S, '[data-pvfo-hd="chon-het"]');
  if (!b) return;
  b.setAttribute("aria-pressed", String(S.chonHet));
  b.className = `btn sm${S.chonHet ? "" : " ghost"}`;
}
function pvfoKhoaLo(S, khoa) {
  for (const sel of ['[data-pvfo-hd="dang-ngay"]', '[data-pvfo-hd="queue"]']) {
    const b = pvfoQ(S, sel);
    if (b) b.disabled = khoa;
  }
}

// ----- sự kiện (uỷ quyền trên khung) -----
function pvfoBam(S, ev) {
  const t = ev && ev.target;
  if (!t || typeof t.closest !== "function") return;
  const tab = t.closest("[data-pvfo-tab]");
  if (tab) { pvfoDoiTab(S, Number(tab.dataset.pvfoTab)); return; }
  const chip = t.closest("[data-pvfo-chip]");
  if (chip) {
    // _select_account_filter
    const i = Number(chip.dataset.pvfoChip);
    S.locTk = Number.isInteger(i) && i >= 0 && i < S.accounts.length ? (S.accounts[i] && S.accounts[i].id) ?? null : null;
    pvfoDungThe(S);
    pvfoVeDs(S);
    return;
  }
  const hd = t.closest("[data-pvfo-hd]");
  if (hd) { pvfoHanhDong(S, hd.dataset.pvfoHd, hd); return; }
  const lt = t.closest("[data-pvfo-luu-tru]");
  if (lt) { pvfoLuuTru(S, lt.dataset.pvfoLuuTru, lt.dataset.pvfoVe === "1", lt); return; }
  const sua = t.closest("[data-pvfo-sua]");
  if (sua) { const c = pvfoTimThe(S, sua.dataset.pvfoSua); if (c) pvfoMoHopSua(S, c.f); return; }
  const xoa = t.closest("[data-pvfo-xoa]");
  if (xoa) { pvfoXoa(S, xoa.dataset.pvfoXoa, xoa); return; }
  // mousePressEvent: bấm vùng trống của thẻ = đổi ô chọn
  const the = t.closest("[data-pvfo-the]");
  if (the && !t.closest("button, input, select, label, textarea, a")) {
    const c = pvfoTimThe(S, the.dataset.pvfoThe);
    if (c) { c.chon = !c.chon; pvfoVeThe(S, true); }
  }
}
function pvfoHanhDong(S, ma, nut) {
  if (ma === "them") pvfoMoHopSua(S, null);
  else if (ma === "du-bao") pvfoDuBao(S, nut);
  else if (ma === "lam-moi") pvfoTai(S);
  else if (ma === "chon-het") {
    // check_all.toggled → set_selected cho mọi thẻ đang hiện
    S.chonHet = !S.chonHet;
    for (const c of S.the) c.chon = S.chonHet;
    pvfoVeThe(S, true);
    pvfoVeChonHet(S);
  } else if (ma === "hom-qua") pvfoGiongHomQua(S);
  else if (ma === "dang-ngay") pvfoDangNgay(S);
  else if (ma === "queue") pvfoThemQueue(S);
}
function pvfoDoi(S, ev) {
  const t = ev && ev.target;
  if (!t) return;
  const d = t.dataset || {};
  if (t.id === "pvfo-sap-xep") {
    if (!pvfoSAP_XEP.some((x) => x[1] === t.value)) return;
    S.sapXep = t.value;
    pvfoDungThe(S);
    pvfoVeThe(S, false); // y folders.py:604: chỉ _render_cards, không _update_selected_summary (lỗi gốc giữ nguyên)
    return;
  }
  if (t.id === "pvfo-gio") { pvfoGoGio(S, t.value); t.value = String(S.gio); return; }
  if (t.id === "pvfo-ai-xem") { if (pvfoAI_XEM.some((x) => x[0] === t.value)) S.aiXem = t.value; return; }
  if (d.pvfoChon !== undefined) {
    const c = pvfoTimThe(S, d.pvfoChon);
    if (c) { c.chon = !!t.checked; pvfoVeThe(S, true); }
    return;
  }
  if (d.pvfoSo !== undefined) {
    const c = pvfoTimThe(S, d.pvfoSo);
    if (c) { pvfoGoSo(S, c, t.value); t.value = String(c.so); }
    return;
  }
  if (d.pvfoLich !== undefined) {
    const c = pvfoTimThe(S, d.pvfoLich);
    if (c) pvfoChonLich(S, c, Number(t.value), t);
  }
}
function pvfoGo(S, ev) {
  const t = ev && ev.target;
  if (!t) return;
  const d = t.dataset || {};
  if (d.pvfoSo !== undefined) { const c = pvfoTimThe(S, d.pvfoSo); if (c) pvfoGoSo(S, c, t.value); }
  else if (t.id === "pvfo-gio") pvfoGoGio(S, t.value);
}
// QSpinBox 0..100: số người dùng gõ (khác số đang có) = _count_user_edited; ô trống / không phải số thì giữ số cũ.
function pvfoGoSo(S, c, v) {
  const n = parseInt(String(v), 10);
  if (!Number.isFinite(n)) return;
  const so = pvfoKep(n, 0, 100);
  if (so !== c.so) { c.so = so; c.daSua = true; }
  pvfoVeTomTat(S);
}
function pvfoGoGio(S, v) {
  const n = parseInt(String(v), 10);
  if (Number.isFinite(n)) S.gio = pvfoKep(n, 1, 48);
}
// _on_tab_changed
function pvfoDoiTab(S, i) {
  if ((i !== 0 && i !== 1) || i === S.tab) return;
  S.tab = i;
  const tabs = pvfoQ(S, "#pvfo-tabs");
  if (tabs) tabs.innerHTML = pvfoTabsHtml(i);
  // Lần tải có thể lâu (quét thư mục): xoá thẻ của tab cũ để không thao tác nhầm trên danh sách khác tab đang chọn.
  S.daTai = false; S.folders = []; S.the = [];
  pvfoVeDs(S);
  pvfoTai(S);
}
// _select_same_as_yesterday
function pvfoGiongHomQua(S) {
  let chon = 0;
  S.chonHet = false;
  for (const c of S.the) {
    const trung = pvfoInt(c.f.yesterday_queued_count, 0) > 0;
    c.chon = trung;
    if (trung) chon++;
  }
  pvfoVeThe(S, true);
  pvfoVeChonHet(S);
  if (chon === 0) pvThongBao("Giống hôm qua", "Hôm qua không có folder nào (trong danh sách đang hiện) được đưa vào Queue.", "info");
}

// ----- lịch đăng (cadence) -----
// _on_cadence_picked
function pvfoChonLich(S, c, i, sel) {
  const o = c.ds[i];
  if (!o) return;
  if (o.tu) {
    // Quay về lựa chọn cũ rồi nhờ backend chọn pha cân tải nhất.
    sel.value = String(c.chiSo);
    pvfoTuCan(S, c.id, o.n);
    return;
  }
  pvfoApLich(S, c, i);
}
function pvfoApLich(S, c, i) {
  const o = c.ds[i];
  c.truoc = [c.f.cadence_days, c.f.cadence_phase, c.chiSo];
  c.chiSo = i;
  c.f.cadence_days = o.n; c.f.cadence_phase = o.pha;
  // Số người dùng đã gõ tay thì giữ nguyên; chỉ đổi mặc định chưa ai chỉnh.
  if (!c.daSua) c.so = pvfoDenLuot(o.n, o.pha) ? pvfoKep(pvfoInt(c.f.videos_per_day, 1), 0, 100) : 0;
  pvfoVeThe(S, true);
  pvfoLuuLich(S, c.id, o.n, o.pha);
}
// _save_cadence: không refresh (refresh dựng lại thẻ, mất các ô Videos đang chỉnh). Lỗi → revert_cadence + hộp lỗi.
async function pvfoLuuLich(S, id, n, pha) {
  try {
    await pvApi.updateFolder(id, { cadence_days: n, cadence_phase: pha });
  } catch (e) {
    if (!pvConSong(S.phien) || (e && e.roiTrang)) return;
    const c = pvfoTimThe(S, id);
    if (c && c.truoc) {
      [c.f.cadence_days, c.f.cadence_phase, c.chiSo] = c.truoc;
      pvfoVeThe(S, true);
    }
    pvThongBao("Lỗi lưu lịch đăng", pvfoChuE(e), "critical");
  }
}
// _auto_cadence → folder_suggest_phase(id, n) → apply_cadence (chỉ lưu khi chỉ số đổi, như setCurrentIndex).
async function pvfoTuCan(S, id, n) {
  let res;
  try {
    res = await pvApi.folderSuggestPhase(id, n);
  } catch (e) {
    if (!pvConSong(S.phien) || (e && e.roiTrang)) return;
    pvThongBao("Lỗi chọn pha tự động", pvfoChuE(e), "critical");
    return;
  }
  if (!pvConSong(S.phien)) return;
  const c = pvfoTimThe(S, id);
  if (!c || !res || typeof res !== "object") return;
  const nn = pvfoInt(res.cadence_days, NaN), ph = pvfoInt(res.cadence_phase, NaN);
  const i = c.ds.findIndex((o) => !o.tu && o.n === nn && o.pha === ph);
  if (i >= 0 && i !== c.chiSo) pvfoApLich(S, c, i);
}

// 📊 Dự báo lịch → cadence_forecast(14)
async function pvfoDuBao(S, nut) {
  if (nut.disabled) return;
  nut.disabled = true; // khoá TRƯỚC await: bấm đúp không mở 2 hộp
  let res;
  try {
    res = await pvApi.cadenceForecast(14);
  } catch (e) {
    if (!pvConSong(S.phien) || (e && e.roiTrang)) return;
    nut.disabled = false;
    pvThongBao("Lỗi dự báo lịch", pvfoChuE(e), "critical");
    return;
  }
  if (!pvConSong(S.phien)) return;
  nut.disabled = false;
  const hop = pvHop({ tieuDe: "Dự báo số video mỗi ngày theo lịch (folder đang bật)", html: pvfoDuBaoHtml(res), nut: [{ ma: "dong", chu: "Đóng", chinh: true }] });
  hop.el.className += " pvfo-hop-rong";
}

// ----- Lưu trữ / Khôi phục / Delete -----
async function pvfoLuuTru(S, id, luuTru, nut) {
  if (nut.disabled) return;
  nut.disabled = true;
  try {
    await pvApi.archiveFolder(id, luuTru);
  } catch (e) {
    if (!pvConSong(S.phien) || (e && e.roiTrang)) return;
    nut.disabled = false;
    pvThongBao("Lỗi", pvfoChuE(e), "critical");
    return;
  }
  if (!pvConSong(S.phien)) return;
  nut.disabled = false;
  pvfoTai(S);
}
async function pvfoXoa(S, id, nut) {
  const c = pvfoTimThe(S, id);
  if (!c || nut.disabled) return;
  const ten = "name" in c.f ? pvfoPy(c.f.name) : "";
  nut.disabled = true;
  let dongY = false;
  try { dongY = await pvXacNhan(`Xóa folder '${ten}'?\nCác video trong hàng đợi sẽ không bị xóa.`); }
  finally { nut.disabled = false; }
  if (!dongY || !pvConSong(S.phien)) return;
  nut.disabled = true;
  try {
    await pvApi.deleteFolder(c.id);
  } catch (e) {
    if (!pvConSong(S.phien) || (e && e.roiTrang)) return;
    nut.disabled = false;
    pvThongBao("Lỗi xóa folder", pvfoChuE(e), "critical");
    return;
  }
  if (!pvConSong(S.phien)) return;
  nut.disabled = false;
  pvfoTai(S);
}

// ----- hộp Thêm / Sửa folder -----
async function pvfoMoHopSua(S, folder) {
  const laSua = !!folder;
  const ds = S.accounts.slice();
  const o = pvfoMauSua(folder, ds);
  const hop = pvHop({ tieuDe: laSua ? "Sửa folder" : "Thêm folder", html: pvfoHopSuaHtml(o, ds),
    nut: [{ ma: "luu", chu: "Lưu Folder", chinh: true }, { ma: "huy", chu: "Hủy" }] });
  hop.el.className += " pvfo-hop";
  const ghi = (ev) => {
    const t = ev && ev.target;
    const pid = t && t.dataset ? t.dataset.pvfoPid : undefined;
    if (pid !== undefined) { o.pid_tick.set(pid, !!t.checked); return; }
    pvfoGhiO(o, t, ds);
    if (t && t.name === "product_id" && typeof hop.el.querySelector === "function") {
      const kv = hop.el.querySelector("[data-pvfo-pid-ds]");
      if (kv) kv.innerHTML = pvfoPidHtml(o);
    }
  };
  hop.el.addEventListener("input", ghi);
  hop.el.addEventListener("change", ghi);
  hop.el.addEventListener("click", (ev) => {
    const b = ev && ev.target && typeof ev.target.closest === "function" ? ev.target.closest("[data-pvfo-test]") : null;
    if (b) pvfoThuNguon(S, o, folder, b);
  });
  const kq = await hop.cho;
  if (kq !== "luu" || !pvConSong(S.phien)) return;
  const data = pvfoDuLieuSua(o);
  try {
    if (laSua) await pvApi.updateFolder(folder.id, data);
    else await pvApi.createFolder(data);
  } catch (e) {
    if (!pvConSong(S.phien) || (e && e.roiTrang)) return;
    pvThongBao(laSua ? "Lỗi sửa folder" : "Lỗi thêm folder", pvfoChuE(e), "critical");
    return;
  }
  if (!pvConSong(S.phien)) return;
  pvfoTai(S);
}
// Ghi giá trị một ô của hộp sửa vào trạng thái form (ô nào lạ / giá trị lạ thì bỏ qua).
function pvfoGhiO(o, t, ds) {
  if (!t || typeof t.name !== "string") return;
  const v = String(t.value ?? "");
  switch (t.name) {
    case "name": case "path": case "product_id": case "product_name": case "caption_pool": case "post_times":
    case "campaign_hashtags": case "first_comment":
      o[t.name] = v; break;
    case "source": if (v === "local" || v === "drive") o.source = v; break;
    case "visibility": if (["everyone", "friends", "private"].includes(v)) o.visibility = v; break;
    case "account": {
      const i = Number(v);
      o.account_id = Number.isInteger(i) && i >= 0 && i < ds.length ? (ds[i] && ds[i].id) ?? null : null;
      break;
    }
    case "videos_per_day": { const n = parseInt(v, 10); if (Number.isFinite(n)) o.videos_per_day = pvfoKep(n, 1, 100); break; }
    case "active": o.active = !!t.checked; break;
    default: break;
  }
}
// _test_connection (folders.py:182-204). Local: máy nhà đếm video qua POST /_dem (§5.2); drive: drive-test (cần folder đã lưu).
async function pvfoThuNguon(S, o, folder, nut) {
  if (nut.disabled) return;
  const duong = String(o.path).trim();
  if (!duong) { pvThongBao("Lỗi", "Vui lòng nhập đường dẫn trước khi test.", "warning"); return; }
  nut.disabled = true;
  try {
    if (o.source === "local") {
      let r;
      try { r = await pvApi.demVideo(duong); }
      catch (e) {
        if (!pvConSong(S.phien) || (e && e.roiTrang)) return;
        pvThongBao("Lỗi", pvfoChuE(e), "warning"); // 400 B3 (đường mạng) / lỗi máy nhà: câu từ máy nhà
        return;
      }
      if (!pvConSong(S.phien)) return;
      if (r && r.ton_tai === true) pvThongBao("Thành công", `Thư mục Local hợp lệ!\nTìm thấy ${pvfoPy(r.so_video)} video.`, "info");
      else pvThongBao("Lỗi", "Thư mục local không tồn tại.", "critical");
    } else if (folder && folder.id) {
      let r;
      try { r = await pvApi.driveTest(folder.id); }
      catch (e) {
        if (!pvConSong(S.phien) || (e && e.roiTrang)) return;
        pvThongBao("Lỗi", `Kết nối Drive thất bại: ${pvfoChuE(e)}`, "critical");
        return;
      }
      if (!pvConSong(S.phien)) return;
      pvThongBao("Google Drive", `Kết nối Drive thành công!\nSố video: ${pvfoPy(r && typeof r === "object" && "video_count" in r ? r.video_count : 0)}`, "info");
    } else {
      pvThongBao("Google Drive", "Vui lòng lưu folder trước để test kết nối Drive qua API.", "info");
    }
  } finally {
    nut.disabled = false;
  }
}

// ----- thanh batch: ⚡ Đăng ngay / ➕ Thêm vào Queue -----
// Khoá CẢ HAI nút (S.dangGui + disabled) TRƯỚC await đầu tiên (kể cả hộp xác nhận): bấm đúp / bấm nút kia không gửi lệnh ghi thứ hai.
// Không bao giờ tự gửi lại lệnh ghi; lệnh nền (202) bị bỏ dở vì rời trang / hết phiên thì dừng, không gửi tiếp.
async function pvfoDangNgay(S) {
  if (S.dangGui) return;
  const chon = S.the.filter((c) => c.chon);
  if (!chon.length) { pvThongBao("Cảnh báo", "Vui lòng chọn ít nhất 1 folder để đăng ngay.", "warning"); return; }
  if (chon.reduce((s, c) => s + c.so, 0) === 0) { pvThongBao("Cảnh báo", "Tất cả folder đã chọn đang để số video = 0.", "warning"); return; }
  const vis = pvfoMaAiXem(S.aiXem);
  // Snapshot trước khi chạy (desktop: items_snapshot trên GUI thread).
  const muc = chon.map((c) => [c.id, c.so, "name" in c.f ? pvfoPy(c.f.name) : ""]);
  S.dangGui = true;
  pvfoKhoaLo(S, true);
  let kq = null;
  try {
    if (!(await pvXacNhan(`Bắt đầu đăng ngay video từ ${chon.length} folder đã chọn?`))) return;
    let started = 0, dung = false;
    const errors = [];
    for (const [id, so, ten] of muc) {
      for (let i = 0; i < so; i++) {
        try {
          await pvApi.postNow(id, vis);
          started++;
        } catch (e) {
          if (e && (e.roiTrang || e.status === 401)) dung = true; // không biết lệnh đã chạy chưa → dừng hẳn
          else errors.push(`Folder #${pvfoPy(id)} (${ten}): ${pvfoChuE(e)}`);
          break;
        }
      }
      if (dung) break;
    }
    kq = { started, errors, dung };
  } finally {
    S.dangGui = false;
    pvfoKhoaLo(S, false);
  }
  if (!kq || kq.dung || !pvConSong(S.phien)) return;
  const m = pvfoChuDang(kq.started, kq.errors);
  pvThongBao(m.tieuDe, m.cau, m.kieu);
  pvfoTai(S);
}
async function pvfoThemQueue(S) {
  if (S.dangGui) return;
  const chon = S.the.filter((c) => c.chon);
  if (!chon.length) { pvThongBao("Cảnh báo", "Vui lòng chọn ít nhất 1 folder để thêm vào Queue.", "warning"); return; }
  if (chon.reduce((s, c) => s + c.so, 0) === 0) { pvThongBao("Cảnh báo", "Tất cả folder đã chọn đang để số video = 0.", "warning"); return; }
  const payload = pvfoPayloadQueue(chon, S.gio, S.aiXem);
  S.dangGui = true;
  pvfoKhoaLo(S, true);
  let res, loi = null;
  try { res = await pvApi.batchSchedule(payload); }
  catch (e) { loi = e || new Error("Lỗi"); }
  finally {
    S.dangGui = false;
    pvfoKhoaLo(S, false);
  }
  if (!pvConSong(S.phien) || (loi && loi.roiTrang)) return;
  if (loi) { pvThongBao("Lỗi", pvfoChuE(loi), "critical"); return; }
  pvThongBao("Thành công", pvfoChuQueue(res), "info");
  pvfoTai(S);
}
