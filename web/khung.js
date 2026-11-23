// Khung menu trái (đợt 8, W-M1): menu 5 mục của chủ kho (2026-11-19 gỡ Duyệt video + Đăng bài: duyệt lúc tạo video, đăng qua Poster V2; mục Poster V2: web/poster.js, docs/poster-v2-tren-web.md §6.1), trang Cần quay, trang Máy nhà, router cho route mới.
// Thiết kế: docs/giao-dien-menu-trai.md §2, §3, §6, §7. Script thường, chung phạm vi toàn cục với app.js:
// mọi tên cấp đỉnh của file này bắt đầu bằng "mn" (P2-7, test cf/test/menu-web.test.mjs).
// Dùng của app.js (lúc chạy): esc, $, api, state, loadList, route, cardHtml, bindSwitches, quay, soLoaiDaQuay, phienCT, CHI_CHU_HTML,
// sucKhoeHtml; của viec.js: renderViec. Trang Poster V2 (poster.js) và Học tự động (hoc.js, hcRender) gọi qua typeof — chưa có file vẫn chạy.
"use strict";

// --- khung-thuan start ---
const mnMENU = [
  { ma: "hom-nay", href: "#/", ic: "🏠", ten: "Hôm nay", ngan: "Hôm nay" },
  { ma: "kho", href: "#/kho", ic: "📦", ten: "Sản phẩm", ngan: "Sản phẩm" },
  { ma: "can-quay", href: "#/can-quay", ic: "🎥", ten: "Cần quay", ngan: "Cần quay" },
  { ma: "may-nha", href: "#/may-nha", ic: "⚙", ten: "Máy nhà", ngan: "Máy nhà" },
  { ma: "poster", href: "#/poster", ic: "📮", ten: "Poster V2", ngan: "Poster" },
];

// hash → {trang, id}. trang ∈ "goc" | "kho" | "can-quay" | "cu" | "may-nha" | "sua" | "viec-ct" | "poster" | "hoc" | "".
// "hoc" (#/hoc, D15 Q6): trang Học tự động, KHÔNG có mục menu riêng — mở từ khối "📈 Học hôm nay", tô mục Hôm nay.
// id: phần sau "/" của #/poster/<trang>, hoặc của link cũ #/duyet/<id>, #/dang/<id> (trang "cu": chuyển về #/sp/<id> hoặc #/poster)
// (CHƯA giải mã; "" = trang danh sách). Khớp regex của route() trong app.js.
function mnPhanTichHash(hash) {
  const h = typeof hash === "string" ? hash : "";
  if (h === "" || h === "#" || h === "#/") return { trang: "goc", id: "" };
  if (h === "#/kho" || /^#\/sp\/.+$/.test(h)) return { trang: "kho", id: "" };
  if (h === "#/can-quay") return { trang: "can-quay", id: "" };
  if (h === "#/hoc") return { trang: "hoc", id: "" };
  if (h === "#/may-nha" || h === "#/viec" || h === "#/suc-khoe") return { trang: "may-nha", id: "" };
  if (/^#\/viec\/[^/]+$/.test(h)) return { trang: "viec-ct", id: "" };
  if (/^#\/sua\/\d{19}\/[0-9a-f]{16}$/.test(h)) return { trang: "sua", id: "" };
  const p = h.match(/^#\/poster(?:\/([^/]*))?$/);
  if (p) return { trang: "poster", id: p[1] || "" };
  const m = h.match(/^#\/(dang|duyet)(?:\/([^/]*))?$/);
  if (m) return { trang: "cu", id: m[2] || "" };
  return { trang: "", id: "" };
}

// Mục menu đang mở (bảng §2.3). Người thường: trang mặc định là Kho; trang chủ kho → "" (đang xem câu chặn).
function mnMuc(hash, chu) {
  const t = mnPhanTichHash(hash).trang;
  const muc = { goc: chu ? "hom-nay" : "kho", kho: "kho", "can-quay": "can-quay", "may-nha": "may-nha", "viec-ct": "may-nha", poster: "poster", hoc: "hom-nay" }[t] || "";
  if (chu) return muc;
  return t === "" ? "kho" : muc === "kho" ? "kho" : "";
}

// Nội dung #nav. Người thường (P-33): đúng 1 mục, không icon, không huy hiệu — CSS menu chỉ áp khi body[data-vai="chu"].
function mnNavHtml(chu) {
  if (!chu) return `<a href="#/kho" data-nav="kho">Sản phẩm</a>`;
  return mnMENU.map((m) => `<a href="${esc(m.href)}" data-nav="${esc(m.ma)}" aria-label="${esc(m.ten)}">`
    + `<span class="mn-ic" aria-hidden="true">${esc(m.ic)}</span>`
    + `<span class="mn-chu"><span class="mn-du">${esc(m.ten)}</span><span class="mn-ngan" aria-hidden="true">${esc(m.ngan)}</span></span>`
    + `${m.ma === "may-nha" ? `<span class="huy-hieu" id="viec-hh" hidden></span>` : ""}</a>`).join("");
}

// Cần quay: SP đã có bộ cảnh quay mà chưa quay xong (§2.5).
const mnLOC_CQ = { chua_gi: "Chưa quay gì", chua_oneshot: "Chưa quay oneshot", chua_review: "Chưa quay review" };
function mnDsCanQuay(list, loc) {
  const ds = Array.isArray(list) ? list : [];
  const tt = (x) => x.trang_thai || (x.da_phan_tich ? "da_phan_tich" : "");
  const khop = loc === "chua_oneshot" ? (x) => !quay(x, "oneshot").xong
    : loc === "chua_review" ? (x) => !quay(x, "review").xong
    : (x) => tt(x) === "da_phan_tich";
  return ds.filter((x) => x && (tt(x) === "da_phan_tich" || tt(x) === "da_quay") && khop(x))
    .map((x, k) => [x, k]).sort((a, b) => soLoaiDaQuay(a[0]) - soLoaiDaQuay(b[0]) || a[1] - b[1]).map((p) => p[0]);
}
function mnCanQuayHtml(list, loc) {
  const chon = Object.prototype.hasOwnProperty.call(mnLOC_CQ, loc) ? loc : "chua_gi";
  const ds = mnDsCanQuay(list, chon);
  return `<h2 class="sk-tieu-de">🎥 Cần quay</h2>
    <div class="filters">${Object.entries(mnLOC_CQ).map(([k, v]) =>
      `<button class="chip${k === chon ? " on" : ""}" data-mn-loc="${esc(k)}">${esc(v)} (${mnDsCanQuay(list, k).length})</button>`).join("")}</div>
    <div class="list">${ds.length ? ds.map((x, k) => cardHtml(x, k + 1)).join("")
      : `<p class="muted center">Không còn sản phẩm nào ở mục này.</p>`}</div>`;
}
// --- khung-thuan end ---

let mnLocCQ = "chua_gi"; // chip đang chọn ở trang Cần quay (giữ khi vẽ lại sau gạt/gắn thẻ)
const mnCHUA_CO = `<p class="center muted">Trang đang được cập nhật. <a href="#/">← Hôm nay</a></p>`;

// Router cho route mới (+ #/viec, #/suc-khoe). true = đã xử lý hash này; false = để route() cũ của app.js làm.
async function mnRoute(hash, chu) {
  if (typeof pvDung === "function") pvDung(); // Poster V2: xoá hẹn giờ, ngừng hỏi lệnh nền, bỏ kết quả muộn (poster.js)
  const { trang, id } = mnPhanTichHash(hash);
  if (!["can-quay", "may-nha", "cu", "poster", "hoc"].includes(trang)) return false;
  const phien = ++phienCT;
  if (!chu) { $("#app").innerHTML = CHI_CHU_HTML; return true; }
  // Link cũ #/duyet[/<id>], #/dang[/<id>] (2 trang đã gỡ 2026-11-19): có SP → trang SP, không → Poster V2.
  if (trang === "cu") { location.replace(id ? `#/sp/${id}` : "#/poster"); return true; }
  if (trang === "can-quay") await mnRenderCanQuay(phien);
  else if (trang === "may-nha") await mnRenderMayNha(phien);
  else if (trang === "poster") { if (typeof pvRender === "function") await pvRender(id); else $("#app").innerHTML = mnCHUA_CO; }
  else if (trang === "hoc") { if (typeof hcRender === "function") await hcRender(phien); else $("#app").innerHTML = mnCHUA_CO; } // hoc.js (D15)
  return true;
}

// ---------- Cần quay ----------
async function mnRenderCanQuay(phien) {
  if (!state.list.length || route.reload) {
    $("#app").innerHTML = `<p class="muted center">Đang tải…</p>`;
    await loadList();
    route.reload = false;
  }
  if (phien !== phienCT) return; // đã sang trang khác trong lúc tải: không vẽ đè
  mnVeCanQuay();
}
function mnVeCanQuay() {
  $("#app").innerHTML = mnCanQuayHtml(state.list, mnLocCQ);
  document.querySelectorAll("[data-mn-loc]").forEach((b) => b.addEventListener("click", () => { mnLocCQ = b.dataset.mnLoc; mnVeCanQuay(); }));
  // Mở trang SP từ Cần quay → vào thẳng tab bộ cảnh quay.
  document.querySelectorAll("#app .card a.body").forEach((a) => a.addEventListener("click", () => {
    try { sessionStorage.setItem("kho_tab", "canh"); } catch { /* chế độ riêng tư chặn sessionStorage: bỏ qua */ }
  }));
  bindSwitches(); // gạt Đã quay / gắn thẻ xong gọi route() → vẽ lại đúng trang này (P2-5)
}

// ---------- Máy nhà: sức khoẻ (trên) + việc chạy trên máy nhà (dưới) ----------
async function mnRenderMayNha(phien) {
  const viec = renderViec(); // viec.js vẽ khung đồng bộ trước await đầu tiên
  const khung = $("#app .vt-khung");
  if (khung) {
    const dau = khung.firstElementChild;
    (dau || khung).insertAdjacentHTML(dau ? "afterend" : "afterbegin", `<section id="mn-sk" class="sk">
      <div class="row" style="justify-content:space-between"><h3 class="sk-tieu-de">🩺 Sức khoẻ máy nhà</h3><button class="btn sm" id="mn-sk-lai">Kiểm lại</button></div>
      <div id="mn-sk-kq"><p class="muted">Đang kiểm…</p></div>
    </section>`);
    $("#mn-sk-lai")?.addEventListener("click", () => mnKiemSk(phien));
    $("#mn-sk-kq")?.addEventListener("click", (e) => { const b = e.target.closest(".sk-nut"); if (b) mnBatTat(b, phien); });
  }
  await Promise.all([viec, mnKiemSk(phien)]);
}
// Bật/tắt một app trên máy nhà → kiểm lại sức khoẻ. Tắt Bộ chạy việc dừng luôn việc đang chạy → hỏi kỹ.
const MN_CANH_BAO_TAT = { runner: "Việc đang chạy trên máy nhà sẽ bị dừng giữa chừng.", poster: "Lịch đăng tự động sẽ dừng tới khi bật lại." };
async function mnBatTat(btn, phien) {
  const { ma, lam, ten } = btn.dataset;
  if (lam === "tat" && !confirm(`Tắt ${ten}?${MN_CANH_BAO_TAT[ma] ? "\n" + MN_CANH_BAO_TAT[ma] : ""}`)) return;
  document.querySelectorAll("#mn-sk-kq .sk-nut").forEach((b) => { b.disabled = true; });
  btn.textContent = lam === "tat" ? "Đang tắt…" : "Đang bật…";
  let tin = "";
  try { tin = (await api(`may-nha/app/${encodeURIComponent(ma)}/${lam}`, {})).tin || ""; }
  catch (err) { tin = "⚠ " + (err && err.message); }
  if (phien !== phienCT) return;
  if (lam === "bat" && !tin.startsWith("⚠")) await new Promise((r) => setTimeout(r, 4000)); // app cần vài giây để mở cổng
  if (phien !== phienCT) return;
  await mnKiemSk(phien);
  const kq = $("#mn-sk-kq");
  if (kq && tin) kq.insertAdjacentHTML("afterbegin", `<p class="small ${tin.startsWith("⚠") ? "sk-loi" : "muted"}">${esc(ten)}: ${esc(tin)}</p>`);
}
async function mnKiemSk(phien) {
  const btn = $("#mn-sk-lai");
  if (!btn || btn.disabled) return;
  btn.disabled = true; btn.textContent = "Đang kiểm…"; // khoá TRƯỚC await: bấm đúp không gọi 2 lần
  let html;
  try { html = sucKhoeHtml(await api("suc-khoe")); }
  catch (err) { html = `<div class="sk-banner">⚠ Không kiểm được: ${esc(err && err.message)}</div>`; }
  if (phien !== phienCT) return; // đã rời trang: không vẽ đè
  const kq = $("#mn-sk-kq");
  if (kq) kq.innerHTML = html;
  btn.disabled = false; btn.textContent = "Kiểm lại";
}
