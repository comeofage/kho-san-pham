// Kho sản phẩm — web trên Cloudflare Workers; đăng nhập user/pass, đọc/ghi qua /api (Worker giữ token GitHub).
// Dữ liệu vẫn nằm trong repo: data/<id>/{info.json, bo-canh-quay.md, captions.txt, bia.jpg}; data/index.json do Action dựng.
"use strict";

const NHAN = { cho: "Chờ xử lý", da_phan_tich: "Đã phân tích", da_quay: "Đã quay", da_lam_video: "Đã làm video" };
const TOOL = "E:/phantichcanhquay/kho-san-pham/tools/kho.py";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- đăng nhập (cookie HttpOnly do Worker cấp) ----------
const auth = { user: "", ten: "", get on() { return !!this.user; } };

async function api(path, body) {
  const r = await fetch(`/api/${path}`, body === undefined ? { cache: "no-store" }
    : { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  // e.status: phân biệt lỗi vĩnh viễn (401/403) với lỗi tạm (mạng, máy nhà tắt) — homnay.js loaiLoiTai.
  const loi = (msg) => { const e = new Error(msg); e.status = r.status; return e; };
  if (r.status === 401 && path !== "login") { auth.user = ""; renderUser(); openLogin(); throw loi("Hết phiên đăng nhập — đăng nhập lại"); }
  if (!r.ok && r.status !== 409) throw loi(j.loi || `Lỗi ${r.status}`);
  return { status: r.status, ...j };
}

// ---------- tiện ích ----------
const LOAI_QUAY = { oneshot: "Oneshot", review: "Review" };
// Thông tin quay theo loại; dữ liệu cũ chỉ có 1 nút "da_quay" → tính là review.
function quay(i, loai) {
  const q = i[`da_quay_${loai}`];
  if (q) return q;
  if (loai === "review" && i.da_quay && i.da_quay.xong) return i.da_quay;
  return { xong: false, boi: "", luc: "" };
}
function trangThai(i) {
  if (i.da_lam_video && i.da_lam_video.xong) return "da_lam_video";
  if (Object.keys(LOAI_QUAY).some((l) => quay(i, l).xong)) return "da_quay";
  if (i.da_phan_tich) return "da_phan_tich";
  return "cho";
}
function anhBia(i) {
  if (!i.anh_bia) return "";
  return /^https?:/.test(i.anh_bia) ? i.anh_bia
    : `/api/anh/${encodeURIComponent(i.id)}/${encodeURIComponent(i.anh_bia)}?v=${encodeURIComponent(i.cap_nhat_luc || "")}`;
}
const gio = (s) => (s ? s.slice(0, 16).replace("T", " ") : "");
const gioS = (s) => gio(typeof s === "string" ? s : ""); // dữ liệu máy nhà có thể không phải chuỗi
// sua_luc của video là số giây epoch -> "dd/mm HH:MM" giờ VN; không hợp lệ -> "" (không bao giờ ném).
const FMT_SUA = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const gioSua = (s) => {
  const n = typeof s === "number" ? s : typeof s === "string" && /^\d+(\.\d+)?$/.test(s.trim()) ? Number(s) : NaN;
  if (!Number.isFinite(n) || n <= 0 || n > 8.64e9) return ""; // > 8.64e9 giây: Date ngoài khoảng hợp lệ
  const p = Object.fromEntries(FMT_SUA.formatToParts(new Date(n * 1000)).map((x) => [x.type, x.value]));
  return `${p.day}/${p.month} ${p.hour}:${p.minute}`;
};
const laChu = () => auth.user === "nhan" || auth.user === "comeofage";
let toastT;
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("on");
  clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("on"), 2600);
}
async function copy(text, msg = "Đã copy") {
  try { await navigator.clipboard.writeText(text); }
  catch { const a = document.createElement("textarea"); a.value = text; document.body.append(a); a.select(); document.execCommand("copy"); a.remove(); }
  toast(msg);
}
function needLogin() {
  if (auth.on) return true;
  openLogin(); return false;
}

// ---------- dữ liệu danh sách ----------
const state = { list: [], loc: "tat_ca", tim: "" };

async function loadList() {
  state.list = (await api("ds")).san_pham || [];
}

// ---------- giao diện ----------
function renderUser() {
  const u = $("#user");
  u.innerHTML = auth.on
    ? `${laChu() && typeof mnNavHtml !== "function" ? `<a href="#/suc-khoe" class="btn ghost sm" title="Sức khoẻ máy nhà">🩺 Máy nhà</a> ` : ""}<span class="small muted">👤 ${esc(auth.ten)}</span> <button class="btn ghost sm" id="btn-out">Thoát</button>`
    : `<button class="btn sm" id="btn-in">Đăng nhập</button>`;
  // Thanh điều hướng W-7: Hôm nay · Kho sản phẩm · Việc (huy hiệu đếm việc cần bạn giữ id viec-hh).
  // P-33: người không phải chủ kho chỉ có mục Kho sản phẩm.
  const nav = $("#nav");
  if (nav) {
    const chu = laChu(); document.body.dataset.vai = chu ? "chu" : "thuong"; // menu.css chỉ áp cho chủ kho
    nav.innerHTML = !auth.on ? "" : typeof mnNavHtml === "function" ? mnNavHtml(chu) : `${chu ? `<a href="#/" data-nav="hom-nay">Hôm nay</a>` : ""}<a href="#/kho" data-nav="kho">Kho sản phẩm</a>${chu
      ? `<a href="#/viec" data-nav="viec" title="Việc chạy trên máy nhà">Việc<span class="huy-hieu" id="viec-hh" hidden></span></a>` : ""}`;
    danhDauNav();
  }
  $("#btn-out", u)?.addEventListener("click", async () => {
    await api("logout", {}).catch(() => {});
    auth.user = ""; state.list = []; renderUser(); route();
  });
  $("#btn-in", u)?.addEventListener("click", openLogin);
  if (laChu()) capNhatHuyHieuViec(); // viec.js: huy hiệu = can_tra_loi + cho_duyet
}

// Tô mục điều hướng đang mở theo hash.
function danhDauNav() {
  const h = location.hash;
  const dang = typeof mnMuc === "function" ? mnMuc(h, laChu()) : !laChu() ? (/^#\/(sp|viec|suc-khoe|sua)(\/|$)/.test(h) ? "" : "kho") // P-33: trang mặc định của người thường là Kho
    : h === "" || h === "#" || h === "#/" ? "hom-nay" : h === "#/kho" ? "kho" : h.startsWith("#/viec") ? "viec" : "";
  document.body.dataset.trang = /^#\/sua\//.test(h) ? "sua" : dang; // menu.css ẩn thanh đáy ở màn sửa
  document.querySelectorAll("#nav [data-nav]").forEach((a) => {
    const on = a.dataset.nav === dang;
    a.classList.toggle("on", on);
    if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
}

function openLogin() {
  $("#login-err").textContent = "";
  if (!$("#dlg-login").open) $("#dlg-login").showModal();
}

function switchHtml(i, loai, label = LOAI_QUAY[loai]) {
  const q = quay(i, loai);
  return `<label class="switch" data-quay="${esc(i.id)}" data-loai="${loai}" title="${q.xong ? `Đã quay ${LOAI_QUAY[loai]} — ${esc(q.boi)} ${gio(q.luc)}` : `Gạt khi đã quay ${LOAI_QUAY[loai]} xong`}">
    <input type="checkbox" ${q.xong ? "checked" : ""}><span class="tr"></span><span>${label}</span></label>`;
}
const soLoaiDaQuay = (x) => Object.keys(LOAI_QUAY).filter((l) => quay(x, l).xong).length;
const LOC_THEM = { yeu_thich: "★ Yêu thích", can_dang: "⬆ Cần đăng", ngung_dang: "⛔ Ngừng đăng", chua_oneshot: "Chưa quay oneshot", chua_review: "Chưa quay review" };
const TAG_RIENG = { yeu_thich: ["★", "Yêu thích"], can_dang: ["⬆", "Cần đăng"], ngung_dang: ["⛔", "Ngừng đăng (có phản hồi tiêu cực)"] };
function tagHtml(x) {
  return `<div class="tagbtns">${Object.entries(TAG_RIENG).map(([t, [ic, ten]]) =>
    `<button type="button" class="tagbtn ${x[t] ? "on" : ""}" data-tag="${t}" data-id="${esc(x.id)}" title="${x[t] ? "Bỏ thẻ" : "Gắn thẻ"} ${ten}" aria-pressed="${!!x[t]}">${ic}</button>`).join("")}</div>`;
}
const theCua = (x) => Array.isArray(x.the) ? x.the : [];
function khopLoc(x, loc) {
  if (loc === "tat_ca") return true;
  if (loc.startsWith("the:")) return theCua(x).includes(loc.slice(4));
  if (loc === "yeu_thich" || loc === "can_dang" || loc === "ngung_dang") return !!x[loc];
  if (loc === "chua_oneshot") return !quay(x, "oneshot").xong;
  if (loc === "chua_review") return !quay(x, "review").xong;
  return (x.trang_thai || trangThai(x)) === loc;
}

function renderList() {
  const dem = {};
  const locThe = Object.fromEntries([...new Set(state.list.flatMap(theCua))].sort().map((t) => ["the:" + t, "#" + t]));
  for (const k of ["tat_ca", ...Object.keys(NHAN), ...Object.keys(LOC_THEM), ...Object.keys(locThe)]) dem[k] = state.list.filter((x) => khopLoc(x, k)).length;
  const q = state.tim.toLowerCase();
  const ds = state.list.filter((x) => khopLoc(x, state.loc)
    && (!q || [x.ten, x.uid, x.link, x.shop, x.them_boi, ...theCua(x).map((t) => "#" + t)].join(" ").toLowerCase().includes(q)))
    .sort((a, b) => soLoaiDaQuay(a) - soLoaiDaQuay(b)); // chưa quay gì lên đầu; cùng nhóm giữ thứ tự mới thêm trước

  $("#app").innerHTML = `
    <form class="add" id="form-add">
      <input id="in-link" placeholder="Dán link sản phẩm TikTok Shop…" autocomplete="off">
      <button class="btn">Lưu</button>
    </form>
    <p id="add-msg" class="add-msg ${state.msg ? esc(state.msg.loai) : ""}">${state.msg ? esc(state.msg.text) : ""}</p>
    <div class="filters">
      ${[["tat_ca", "Tất cả"], ...Object.entries(LOC_THEM), ...Object.entries(locThe), ...Object.entries(NHAN)].map(([k, v]) => `<button class="chip ${state.loc === k ? "on" : ""}" data-loc="${k}">${v} (${dem[k]})</button>`).join("")}
    </div>
    <input class="search" id="in-tim" placeholder="Tìm theo tên, UID, shop…" value="${esc(state.tim)}">
    <div class="list">
      ${ds.length ? ds.map((x, k) => cardHtml(x, k + 1)).join("") : `<p class="muted center">${state.list.length ? "Không có sản phẩm khớp." : "Kho trống — dán link đầu tiên ở trên."}</p>`}
    </div>`;

  $("#form-add").addEventListener("submit", onAdd);
  document.querySelectorAll("[data-loc]").forEach((b) => b.addEventListener("click", () => { state.loc = b.dataset.loc; renderList(); }));
  const tim = $("#in-tim");
  tim.addEventListener("input", () => { state.tim = tim.value; renderList(); const t = $("#in-tim"); t.focus(); t.setSelectionRange(t.value.length, t.value.length); });
  bindSwitches();
}

const RR_TEN = { "🟢": "Thấp", "🟡": "Trung bình", "🟠": "Khá cao", "🔴": "Cao" };
const NL_TEN = { "✅": "Có thể làm Affiliate", "⚠️": "Làm được nhưng cần chỉnh nội dung", "❌": "Không nên làm Affiliate" };
function ruiRoIcon(x) {
  const r = x.rui_ro && (x.rui_ro.ket_luan || x.rui_ro);
  if (!r || !r.muc_do) return `<span class="rr rr-none" title="Chưa đánh giá rủi ro">⚪</span>`;
  return `<span class="rr" title="Rủi ro ${RR_TEN[r.muc_do] || ""} — ${NL_TEN[r.nen_lam] || ""}">${r.muc_do}</span>`;
}
function ruiRoPanel(r) {
  if (!r || !r.ket_luan) return `<p class="muted">Chưa đánh giá rủi ro. Chạy <code>/phantichcanhquay</code> (hoặc <code>/phantichsanpham</code>) cho sản phẩm này, bước đánh giá rủi ro sẽ đẩy kết quả lên đây.</p>`;
  const k = r.ket_luan;
  const bang = (heads, rows) => `<div class="tbl-wrap"><table class="rr-tbl"><thead><tr>${heads.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.map((c) => `<tr>${c.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  return `<h3>1. Kết luận</h3>
    ${bang(["Hạng mục", "Kết quả"], [["Có nên làm Affiliate", `${k.nen_lam} ${NL_TEN[k.nen_lam] || ""}`], ["Mức độ rủi ro", `${k.muc_do} ${RR_TEN[k.muc_do] || ""}`], ["Nguy cơ lớn nhất", k.nguy_co], ["Khuyến nghị", k.khuyen_nghi]])}
    <h3>2. Tổng hợp rủi ro</h3>
    ${bang(["Hạng mục", "Mức độ", "Nhận xét"], (r.tong_hop || []).map((t) => [t.hang_muc, t.muc_do, t.nhan_xet || ""]))}
    ${(r.luu_y || []).length ? `<h3>3. Các rủi ro cần lưu ý</h3>${bang(["Vấn đề", "Rủi ro", "Cách xử lý"], r.luu_y.map((t) => [t.van_de, t.rui_ro, t.xu_ly]))}` : ""}
    ${(r.claim_cam || []).length ? `<h3>4. Claim không nên dùng</h3>${bang(["Không nên nói", "Gợi ý thay thế"], r.claim_cam.map((t) => [t.khong_nen, t.goi_y]))}` : ""}
    <h3>5. Kết luận cuối</h3><p><b>${esc(r.ket_luan_cuoi)}</b></p>
    ${r.thieu_thong_tin ? `<p class="small muted">Cần bổ sung: ${esc(r.thieu_thong_tin)}</p>` : ""}
    <p class="small muted">Đánh giá lúc ${gio(r.danh_gia_luc)} theo chính sách TikTok Shop VN — chỉ mang tính tham khảo, cần người duyệt lại.</p>`;
}

function cardHtml(x, stt) {
  const tt = x.trang_thai || trangThai(x);
  const img = anhBia(x);
  return `<div class="card${x.ngung_dang ? " ngung" : ""}">
    ${img ? `<img class="thumb" src="${esc(img)}" referrerpolicy="no-referrer" loading="lazy" alt="">` : `<div class="thumb"></div>`}
    <a class="body" href="#/sp/${encodeURIComponent(x.id)}">
      <div class="ten"><span class="stt">#${stt}</span> ${ruiRoIcon(x)} ${x.ngung_dang ? `<span class="ngung-tag" title="Có phản hồi tiêu cực — ngừng đăng video">⛔ NGỪNG ĐĂNG</span> ` : ""}${esc(x.ten || x.link)}</div>
      <div class="small muted"><span class="badge b-${tt}">${NHAN[tt]}</span> <span class="buoc-nho bn-${tt}" title="Chặng hiện tại (ước tính theo trạng thái)">${esc(changChu(changTheoTrangThai(tt)))}</span>${x.gia ? " <b>" + esc(x.gia) + "</b> ·" : ""} ${x.uid ? `<span class="uid-copy" role="button" title="Bấm để copy UID" data-copy="${esc(x.uid)}" data-copy-msg="Đã copy UID ${esc(x.uid)}">${esc(x.uid)} ⧉</span>` : "link rút gọn"}${theCua(x).map((t) => ` <span class="the-rieng">#${esc(t)}</span>`).join("")}</div>
    </a>
    ${tagHtml(x)}
    ${qrHtml(x)}
    <div class="switches">${switchHtml(x, "oneshot")}${switchHtml(x, "review")}</div>
  </div>`;
}

// QR link sản phẩm: ô nhỏ trên thẻ, rê chuột (hoặc chạm) mới hiện to để điện thoại quét → mở TikTok thêm vào trưng bày.
const qrCache = new Map();
function qrSvg(text) {
  if (!window.qrcode) return "";
  if (!qrCache.has(text)) {
    const q = qrcode(0, "M"); q.addData(text); q.make();
    qrCache.set(text, q.createSvgTag({ cellSize: 4, margin: 4, scalable: true }));
  }
  return qrCache.get(text);
}
function qrHtml(x) {
  const link = x.uid ? `https://shop.tiktok.com/vn/pdp/${x.uid}` : x.link;
  const svg = link ? qrSvg(link) : "";
  if (!svg) return "";
  return `<div class="qr" tabindex="0" title="Quét bằng điện thoại để mở sản phẩm">
    <div class="qr-mini">${svg}</div>
    <div class="qr-pop">${svg}<div class="small">Quét để mở sản phẩm</div></div>
  </div>`;
}

// "🎬 Oneshot: Lan 06/10 · Review: Minh 07/10" — rỗng nếu chưa quay gì.
function daQuayText(x) {
  return Object.keys(LOAI_QUAY).map((l) => { const q = quay(x, l); return q.xong ? `${LOAI_QUAY[l]}: ${esc(q.boi)} ${gio(q.luc).slice(5)}` : ""; })
    .filter(Boolean).map((s, k) => (k ? "" : "🎬 ") + s).join(" · ");
}

// Phản hồi gắn thẻ / gạt Đã quay về muộn: chỉ vẽ lại khi vẫn đúng trang lúc bấm (cùng hash + cùng phienCT), không vẽ đè trang mới.
function bindSwitches() {
  document.querySelectorAll("[data-tag]").forEach((b) => b.addEventListener("click", async () => {
    if (!needLogin()) return;
    const id = b.dataset.id, tag = b.dataset.tag, bat = !b.classList.contains("on");
    const h = location.hash, p = phienCT; // chụp trang TRƯỚC await
    b.disabled = true;
    try {
      const { info } = await api("tag", { id, tag, bat });
      const k = state.list.findIndex((x) => x.id === id);
      if (k >= 0) state.list[k] = { ...state.list[k], [tag]: !!info[tag], cap_nhat_luc: info.cap_nhat_luc };
      toast(`${bat ? "✓ Đã gắn" : "Đã bỏ"} thẻ ${TAG_RIENG[tag][1]}`);
      if (location.hash === h && phienCT === p) await route(); // P2-5: vẽ lại đúng trang đang mở (Kho hoặc Cần quay)
    } catch (err) { b.disabled = false; toast("⚠ " + err.message); }
  }));
  document.querySelectorAll("[data-quay]").forEach((sw) => {
    const cb = $("input", sw);
    cb.addEventListener("change", async (e) => {
      const id = sw.dataset.quay, loai = sw.dataset.loai, ten = LOAI_QUAY[loai], val = cb.checked;
      if (!needLogin()) { cb.checked = !val; return; }
      if (!val && !confirm(`Gỡ đánh dấu 'đã quay ${ten}' cho sản phẩm này?`)) { cb.checked = true; return; }
      const h = location.hash, p = phienCT; // chụp trang TRƯỚC await
      sw.classList.add("busy");
      try {
        const { info } = await api("quay", { id, loai, xong: val });
        const k = state.list.findIndex((x) => x.id === id);
        if (k >= 0) {
          const x = { ...state.list[k], da_quay_oneshot: info.da_quay_oneshot, da_quay_review: info.da_quay_review };
          delete x.da_quay;
          state.list[k] = { ...x, cap_nhat_luc: info.cap_nhat_luc, trang_thai: trangThai(info) };
        }
        toast(val ? `✓ Đã quay ${ten}` : `Đã gỡ ${ten}`);
        if (location.hash === h && phienCT === p) await route();
      } catch (err) { cb.checked = !val; toast("⚠ " + err.message); }
      finally { sw.classList.remove("busy"); }
    });
  });
}

// Lấy link từ đoạn chữ dán vào (app TikTok hay copy kèm tên sản phẩm).
function tachLink(text) {
  const t = (text || "").trim();
  const m = t.match(/https?:\/\/[^\s"'<>]+/i);
  if (m) return m[0].replace(/[),.;!?]+$/, "");
  const so = t.match(/\b\d{15,21}\b/);
  return so ? so[0] : null;
}

// Ô thêm link có ở 2 nơi: trang Kho (#form-add, "kho") và ô "Bắt đầu sản phẩm mới" của trang Hôm nay (#form-hn-add, "hn", homnay.js).
const O_THEM = {
  kho: { input: "#in-link", nut: "#form-add button", msg: "#add-msg", nhan: "Lưu" },
  hn: { input: "#in-hn-link", nut: "#form-hn-add button", msg: "#hn-add-msg", nhan: "Bắt đầu" },
};
let linkCho = ""; // link dán lúc chưa đăng nhập — lưu tiếp sau khi đăng nhập
let linkChoO = "kho"; // ô đã dán linkCho
function baoAdd(text, loai = "", o = "kho") {
  if (o !== "hn") state.msg = { text, loai }; // state.msg chỉ để renderList vẽ lại thông báo của trang Kho
  const el = $(O_THEM[o === "hn" ? "hn" : "kho"].msg);
  if (el) { el.textContent = text; el.className = `add-msg ${loai}`; }
  else toast(text); // lưu tự động sau đăng nhập khi đang ở trang không có ô báo (vd trang SP)
}

// Worker lưu link xong tự giao máy nhà phân tích (worker.js giaoPhanTichLinkMoi) → may: "tao" | "trung" | "chua".
function cauMayThem(may) {
  if (may === "tao") return "✓ Đã lưu — máy nhà đã nhận, đang làm bộ cảnh quay.";
  if (may === "trung") return "✓ Đã lưu — máy nhà đang có việc phân tích này rồi.";
  return "✓ Đã lưu — máy nhà chưa nhận (đang tắt?). Bật máy rồi bấm 📥 Xử lý link mới ở trang Việc.";
}

async function onAdd(e) {
  e?.preventDefault();
  const o = e ? (e.currentTarget && e.currentTarget.id === "form-hn-add" ? "hn" : "kho") : linkChoO;
  const raw = e ? ($(O_THEM[o].input)?.value || "") : linkCho;
  if (!raw.trim()) return;
  const link = tachLink(raw);
  if (!link) { baoAdd("⚠ Không thấy link trong nội dung vừa dán — copy lại link sản phẩm.", "loi", o); return; }
  if (!auth.on) { linkCho = raw; linkChoO = o; baoAdd("Đăng nhập xong sẽ tự lưu link này.", "", o); openLogin(); return; }
  linkCho = "";
  const btn = $(O_THEM[o].nut);
  if (btn) { btn.disabled = true; btn.textContent = "Đang lưu…"; }
  try {
    const r = await api("them", { link });
    if (r.trung) {
      baoAdd(`Đã có trong kho${r.trang_thai ? " — " + NHAN[r.trang_thai] : ""}. Không lưu trùng.`, "loi", o);
      location.hash = `#/sp/${encodeURIComponent(r.id)}`;
      return;
    }
    state.list.unshift(r.info);
    const cau = cauMayThem(r.may);
    if (o === "hn") {
      // Hôm nay: mở thẳng trang sản phẩm vừa lưu (không vẽ trang Kho) — câu máy nhà hiện bằng toast vì trang đổi ngay
      if (r.info && r.info.id != null) { toast(cau); location.hash = `#/sp/${encodeURIComponent(r.info.id)}`; return; }
      if (btn) { btn.disabled = false; btn.textContent = O_THEM.hn.nhan; }
      baoAdd(cau, "ok", "hn");
      return;
    }
    state.loc = "tat_ca"; state.tim = "";
    renderList();
    baoAdd(cau, "ok");
  } catch (err) {
    // Hết phiên ngầm (auth.on còn true lúc bấm, API trả 401 và đã mở hộp đăng nhập): giữ lại link để đăng nhập xong tự lưu.
    const hetPhien = !!err && err.status === 401;
    if (hetPhien) { linkCho = raw; linkChoO = o; }
    const cau = hetPhien ? "Hết phiên — đăng nhập lại, link sẽ tự lưu." : "⚠ Lưu không được: " + err.message;
    if (o === "hn") { if (btn) { btn.disabled = false; btn.textContent = O_THEM.hn.nhan; } }
    else renderList();
    const oNhap = $(O_THEM[o].input);
    if (oNhap) oNhap.value = raw; // lưu lỗi: giữ link trong ô để bấm lại
    baoAdd(cau, "loi", o);
  }
}

// Đợt sale 11/11: trong khoảng này caption giữ 2 hashtag sản phẩm đầu + 3 tag chiến dịch = 5 tag (file captions.txt giữ nguyên).
const TAG_DOT = { tu: new Date("2026-10-31T00:00:00+07:00"), den: new Date("2026-11-12T00:00:00+07:00"),
  tag: "#TikTokShop1111 #SaleToVoDoi #Zocoby" };
function doiTag(c) {
  const now = new Date();
  if (!c || now < TAG_DOT.tu || now >= TAG_DOT.den) return c;
  const giu = (c.match(/#\S+/g) || []).slice(0, 2);
  return [c.replace(/#\S+/g, "").replace(/\s+/g, " ").trim(), ...giu, TAG_DOT.tag].join(" ");
}

// ---------- tiến độ 8 bước ----------
// Thẻ kho hiện chặng "Bước k/4" (changChu, loi.js) — chỉ ước tính từ trang_thai (không hỏi máy nhà cho từng SP).

// --- tinhBuoc start ---
// Hàm thuần (không đụng DOM/biến ngoài) để kiểm được bằng node.
// info: /api/sp; tienDo: /api/video/<id>/tien-do hoặc null (máy nhà tắt); duyet: mảng duyệt; dsVideo: /api/video/<id>/ds hoặc null.
function tinhBuoc(info, tienDo, duyet, dsVideo) {
  const i = info || {};
  const TAT = "máy nhà tắt";
  const num = (x) => { const n = Number(x); return Number.isFinite(n) && n > 0 ? n : 0; };
  const mk = (so, ten, trang_thai, ghi_chu = "") => ({ so, ten, trang_thai, ghi_chu });
  const may = !!(tienDo && Array.isArray(tienDo.thu_muc));
  const t = { raw: 0, takes: 0, muse: 0, voice: 0, output_poster: 0, output: 0 };
  if (may) for (const th of tienDo.thu_muc) for (const k of Object.keys(t)) t[k] += num(th && th[k]);
  const dlv = i.da_lam_video || {};
  const posterKho = Array.isArray(dlv.poster) ? dlv.poster.filter((p) => p && typeof p === "object") : [];
  // "xong" trong kho chưa đủ: phải có video thật (so_video > 0 hoặc có dòng Poster), nếu không là dòng ghi 0 video.
  const daVideo = !!dlv.xong && (posterKho.length > 0 || num(dlv.so_video) > 0);
  // Dựng 2 mẻ = Adam (nhan ≠ nha.cua.mit) + creator (nha.cua.mit). Kho có dòng Poster mà thiếu 1 bên → mới 1/2 mẻ.
  const coMeAdam = posterKho.some((p) => p.nhan !== "nha.cua.mit");
  const coMeCreator = posterKho.some((p) => p.nhan === "nha.cua.mit");
  const du2Me = posterKho.length === 0 || (coMeAdam && coMeCreator);
  const daQuay = ["oneshot", "review"].some((l) => i[`da_quay_${l}`] && i[`da_quay_${l}`].xong) || !!(i.da_quay && i.da_quay.xong);

  const b1 = mk(1, "Săn SP", "xong");
  const b2 = mk(2, "Bộ cảnh quay", i.da_phan_tich ? "xong" : "chua");

  let b3;
  if (may && t.raw + t.takes > 0) b3 = mk(3, "Quay", "xong", `raw ${t.raw} · takes ${t.takes}`);
  else if (daQuay) b3 = mk(3, "Quay", "xong", "đã gạt đã quay");
  else if (daVideo) b3 = mk(3, "Quay", "xong", "đã làm video");
  else b3 = mk(3, "Quay", "chua", may ? "" : TAT);

  let b6;
  const soVideo = dlv.so_video ? `${dlv.so_video} video` : "đã làm video";
  if (may && t.output_poster > 0 && t.output > 0) b6 = mk(6, "Dựng 2 mẻ", "xong", `poster ${t.output_poster} · output ${t.output}`);
  else if (daVideo && du2Me) b6 = mk(6, "Dựng 2 mẻ", "xong", soVideo);
  else if (daVideo) b6 = mk(6, "Dựng 2 mẻ", "dang", `1/2 mẻ (thiếu ${coMeAdam ? "creator nha.cua.mit" : "Adam"})`);
  else if (may && (t.output_poster > 0 || t.output > 0)) b6 = mk(6, "Dựng 2 mẻ", "dang", "1/2 mẻ");
  else b6 = mk(6, "Dựng 2 mẻ", "chua", may ? "" : TAT);

  // Voice: mẻ autovideo dùng giọng creator trong takes (không có voice/) -> đã có video mà không voice thì bỏ qua.
  let b5;
  const coOutput = (may && (t.output_poster > 0 || t.output > 0)) || daVideo;
  if (may && t.voice > 0) b5 = mk(5, "Voice", "xong", `${t.voice} file`);
  else if (coOutput) b5 = mk(5, "Voice", "bo_qua", may ? "dùng giọng có sẵn trong takes" : `dùng giọng có sẵn trong takes · ${TAT}`);
  else b5 = mk(5, "Voice", "chua", may ? "" : TAT);

  let b4;
  if (may && t.muse > 0) b4 = mk(4, "B-roll AI", "xong", `${t.muse} file`);
  else if (b5.trang_thai === "xong" || b6.trang_thai !== "chua") b4 = mk(4, "B-roll AI", "bo_qua", may ? "không bắt buộc" : `không bắt buộc · ${TAT}`);
  else b4 = mk(4, "B-roll AI", "chua", may ? "không bắt buộc" : TAT);

  let b8;
  const poster = Array.isArray(dlv.poster) ? dlv.poster : [];
  if (poster.length) {
    const fd = poster.map((p) => p && p.folder).filter((f) => f != null);
    b8 = mk(8, "Đăng", "xong", fd.length ? `folder ${fd.join(", ")}` : `${poster.length} lượt`);
  } else if (dlv.poster_folder != null) b8 = mk(8, "Đăng", "xong", `folder ${dlv.poster_folder}`);
  else b8 = mk(8, "Đăng", "chua");

  // Kiểm duyệt: 2026-11-19 bỏ trang Duyệt video — video được duyệt ngay lúc tạo, bước 7 luôn "bo_qua" (tham số duyet giữ để không đổi chữ ký).
  const b7 = mk(7, "Kiểm duyệt", "bo_qua", "duyệt lúc tạo video");

  return [b1, b2, b3, b4, b5, b6, b7, b8];
}
// Bước hiện tại = số của bước đầu tiên "chua"/"dang" (bỏ qua "xong" và "bo_qua"); 0 = Hoàn tất.
function buocHienTai(buoc) {
  const b = buoc.find((x) => x.trang_thai !== "xong" && x.trang_thai !== "bo_qua");
  return b ? b.so : 0;
}
// --- tinhBuoc end ---

// ---------- trang sức khoẻ máy nhà (đọc + nút Bật/Tắt app có bat_tat, xử lý ở khung.js mnBatTat) ----------
const GOI_Y_APP = { muse: "Mở E:\\viết bài wp\\VideoBatchLocal\\Start.cmd", perfectvoice: "Mở E:\\PerfectVoice\\Run.cmd", poster: "Mở app TikTok Poster V2" };
function sucKhoeHtml(d) {
  const apps = Array.isArray(d.apps) ? d.apps : [];
  return `${d.may_nha ? `<div class="sk-banner ok">🟢 Máy nhà đang trả lời</div>` : `<div class="sk-banner">🔴 Máy nhà không trả lời${d.loi ? ": " + esc(d.loi) : ""}</div>`}
    <p class="small muted">Giờ kiểm: ${esc(gioS(d.luc) || "—")}</p>
    <div class="sk-ds">${apps.map((a) => {
      const goiY = !a.song && GOI_Y_APP[String(a.ma || "").toLowerCase()];
      return `<div class="sk-app ${a.song ? "song" : "chet"}">
        <span class="cham" aria-hidden="true"></span>
        <div class="sk-body"><b>${esc(a.ten || a.ma)}</b> <span class="small muted">cổng ${esc(a.cong ?? "?")}${a.luc ? " · " + esc(gioS(a.luc)) : ""}</span>
          ${goiY ? `<div class="small sk-goi-y">👉 ${esc(goiY)}</div>` : ""}</div>
        <span class="small sk-tt">${a.song ? "Sống" : "Tắt"}</span>
        ${a.bat_tat ? `<button class="btn sm ${a.song ? "ghost" : ""} sk-nut" data-ma="${esc(a.ma)}" data-lam="${a.song ? "tat" : "bat"}" data-ten="${esc(a.ten || a.ma)}">${a.song ? "Tắt" : "Bật"}</button>` : ""}
      </div>`;
    }).join("") || `<p class="muted">Không có thông tin app.</p>`}</div>`;
}
const CHI_CHU_HTML = `<p class="center muted">Trang này chỉ dành cho chủ kho. <a href="#/kho">← Về kho</a></p>`;

// ---------- trang chi tiết ----------
let phienCT = 0; // đánh số mỗi lần mở trang chi tiết: kết quả máy nhà về muộn của trang cũ thì bỏ
async function renderDetail(id) {
  const phien = ++phienCT;
  $("#app").innerHTML = `<p class="muted center">Đang tải…</p>`;
  let d;
  try { d = await api(`sp/${encodeURIComponent(id)}`); }
  catch (err) { if (phien !== phienCT) return; $("#app").innerHTML = `<p class="center">${esc(err.message)}. <a href="#/kho">← Về kho</a></p>`; return; }
  if (phien !== phienCT) return; // đã sang trang khác trong lúc tải: không vẽ đè
  const { info: i, md, caps, douyin } = d;
  let vtk = d.vtk || [];
  // Dữ liệu chấm chỉ để tính 8 bước / Bước tiếp theo. Duyệt video lúc tạo (không còn trang Duyệt/Đăng bài), đăng ở Poster V2.
  const duyet = Array.isArray(d.duyet) ? d.duyet : [];
  const chu = laChu();
  const may = { tai: chu, tienDo: null, ds: null }; // dữ liệu máy nhà, tải sau khi render
  const tt = trangThai(i);
  const capList = (caps || "").split(/\r?\n/).map((s) => doiTag(s.trim())).filter(Boolean);
  const img = anhBia(i);
  const lenh = i.uid
    ? `python ${TOOL} lay ${i.uid} --out "${i.thu_muc_may || "<thư mục dự án>"}"`
    : "(link rút gọn — máy nhà chạy `kho.py cho` để tìm UID trước)";
  const linkChuan = i.uid ? `https://shop.tiktok.com/vn/pdp/${i.uid}` : i.link;
  const prompt = `/tao-video-tu-canh-quay\nLink: ${linkChuan}\nUID: ${i.uid || "?"}\nThư mục: ${i.thu_muc_may || "?"}\nCaption: ${lenh}`;

  $("#app").innerHTML = `
    <p><a href="#/kho" class="small">← Về kho</a></p>
    <div class="detail">
      <div class="head">
        ${img ? `<img src="${esc(img)}" referrerpolicy="no-referrer" alt="">` : ""}
        <div style="min-width:0">
          <h1 title="Bấm để xem đủ tên" id="sp-ten">${esc(i.ten || "(chưa có tên — chờ máy nhà phân tích)")}</h1>
          <span class="badge b-${tt}">${NHAN[tt]}</span>
          <dl class="kv">
            <dt>UID</dt><dd>${i.uid ? `${esc(i.uid)} <button class="btn ghost sm" data-copy="${esc(i.uid)}">Copy</button>` : "chưa có"}</dd>
            <dt>Link</dt><dd><a href="${esc(i.link)}" target="_blank" rel="noopener">${esc(i.link)}</a></dd>
            ${i.gia ? `<dt>Giá</dt><dd>${esc(i.gia)}</dd>` : ""}
            ${i.shop ? `<dt>Shop</dt><dd>${esc(i.shop)}</dd>` : ""}
            <dt>Thêm</dt><dd>${esc(i.them_boi || "?")} · ${gio(i.them_luc)}</dd>
            ${i.da_lam_video && i.da_lam_video.xong ? `<dt>Video</dt><dd>${esc(i.da_lam_video.so_video)} video · ${gio(i.da_lam_video.luc)}${chu ? ` · <a href="#/poster">Poster V2 →</a>` : ""}</dd>` : ""}
            ${i.da_lam_video && i.da_lam_video.xong ? ((i.da_lam_video.poster && i.da_lam_video.poster.length ? i.da_lam_video.poster : (i.da_lam_video.poster_folder != null || i.da_lam_video.duong_dan ? [{ folder: i.da_lam_video.poster_folder, duong_dan: i.da_lam_video.duong_dan }] : [])).map((p) => `<dt>Poster</dt><dd>${p.nhan ? esc(p.nhan) + " · " : ""}${p.folder != null ? "folder " + esc(String(p.folder)) : ""}${p.so_video ? " · " + esc(String(p.so_video)) + " video" : ""}${p.duong_dan ? ` · <code>${esc(p.duong_dan)}</code>` : ""}</dd>`).join("")) : ""}
          </dl>
        </div>
      </div>
      ${chu ? `<div class="bt" id="buoc-tiep"></div>` : ""}
      ${chu ? `<details class="buoc8-gom"><summary>Chi tiết 8 bước nhỏ</summary>
        <p class="small muted">4 chặng: Chuẩn bị (1–2) · Quay (3) · Làm video (4–6) · Chấm và đăng (7–8)</p>
        <div class="buoc8" id="buoc8"></div></details><div class="viec-sp" id="viec-sp"></div>` : ""}
      ${Object.keys(LOAI_QUAY).map((l) => { const q = quay(i, l); return `<div class="quaybox">
        <div class="small">${q.xong ? `🎬 <b>${esc(q.boi)}</b> đã quay ${LOAI_QUAY[l]} lúc ${gio(q.luc)}` : `Chưa quay ${LOAI_QUAY[l]} — gạt khi quay xong để lần sau không làm trùng`}</div>
        ${switchHtml(i, l, `Đã quay ${LOAI_QUAY[l]}`)}
      </div>`; }).join("")}
      <div class="tabs">
        <button class="tab" data-tab="canh">🎥 Bộ cảnh quay</button>
        <button class="tab" data-tab="douyin">🎵 Douyin</button>
        <button class="tab" data-tab="cap">💬 Caption (${capList.length})</button>
        <button class="tab" data-tab="tt">📋 Tóm tắt & rủi ro ${i.rui_ro && i.rui_ro.ket_luan ? esc(i.rui_ro.ket_luan.muc_do) : "⚪"}</button>
        <button class="tab" data-tab="vtk">🎬 Video tham khảo (<span id="vtk-dem">${vtk.length}</span>)</button>
        ${chu ? `<button class="tab" data-tab="video">🎞 Làm video</button>` : ""}
        <button class="tab" data-tab="note">📝 Ghi chú</button>
      </div>
      <div class="panel" id="panel"></div>
    </div>`;
  // CSP script-src 'self' chặn onclick inline → gắn bằng addEventListener (bấm tên để xem đủ).
  $("#sp-ten").addEventListener("click", (e) => e.currentTarget.classList.toggle("full"));

  const panels = {
    canh: () => md
      ? `<div class="md">${window.DOMPurify && window.marked ? DOMPurify.sanitize(marked.parse(md)) : `<pre>${esc(md)}</pre>`}</div>`
      : `<p class="muted">Chưa có file bộ cảnh quay. Máy nhà chạy <code>/phantichcanhquay</code> cho link này rồi <code>kho.py ghi</code>.</p>`,
    douyin: () => douyin
      ? `<div class="md">${window.DOMPurify && window.marked ? DOMPurify.sanitize(marked.parse(douyin)) : `<pre>${esc(douyin)}</pre>`}</div>`
      : `<p class="muted">Chưa có dữ liệu Douyin cho sản phẩm này.<br>Chạy <code>timvideodouyin</code> để tải video và trích xuất cảnh quay ăn tiền.</p>`,
    cap: () => capList.length
      ? `<div class="row" style="justify-content:space-between"><span class="small muted">${capList.length} caption · ≤150 ký tự · 5 hashtag</span>
           <span><button class="btn sm" data-copy-random>🎲 Copy ngẫu nhiên</button> <button class="btn ghost sm" data-copy-all>Copy tất cả</button></span></div>
         <ul class="caps">${capList.map((c, k) => `<li><span class="n">${k + 1}</span><span>${esc(c)}</span><button class="btn ghost sm" data-copy="${esc(c)}">Copy</button></li>`).join("")}</ul>`
      : `<p class="muted">Chưa có caption.</p>`,
    tt: () => `${i.usp && i.usp.cau ? `<h3>USP</h3><p><b>${esc(i.usp.cau)}</b></p><p class="small muted">Từ khoá: ${esc((i.usp.tu_khoa || []).join(", "))}</p>` : `<p class="muted">Chưa có USP.</p>`}
       ${i.tom_tat ? `<h3>Tóm tắt sản phẩm</h3><div class="md">${window.DOMPurify && window.marked ? DOMPurify.sanitize(marked.parse(i.tom_tat)) : `<pre>${esc(i.tom_tat)}</pre>`}</div>` : ""}
       <h2 class="sk-tieu-de">Rủi ro ${i.rui_ro && i.rui_ro.ket_luan ? esc(i.rui_ro.ket_luan.muc_do) : "⚪"}</h2>${ruiRoPanel(i.rui_ro)}`,
    note: () => `<textarea id="in-note" placeholder="Ghi chú cho sản phẩm này…">${esc(i.ghi_chu)}</textarea>
       <div class="row end" style="margin-top:8px"><button class="btn" id="btn-note">Lưu ghi chú</button></div>`,
    vtk: () => `<form class="vtk-add" id="form-vtk">
         <input id="in-vtk-link" placeholder="Dán link video muốn quay giống (TikTok, Douyin, YouTube…)" autocomplete="off">
         <input id="in-vtk-note" placeholder="Ghi chú: muốn học cảnh nào, đoạn nào… (không bắt buộc)" maxlength="2000" autocomplete="off">
         <div class="row end"><button class="btn">Thêm video</button></div>
       </form>
       <p class="small muted">Máy nhà sẽ tải video, tách từng cảnh theo giây kèm ảnh chụp, góc máy, cỡ cảnh, chuyển động máy.</p>
       ${vtk.length ? `<div class="vtk-list">${vtk.slice().reverse().map(vtkHtml).join("")}</div>` : `<p class="muted center">Chưa có video tham khảo.</p>`}`,
  };
  // P-33: tab Làm video (prompt + thư mục máy nhà) chỉ cho chủ kho; tab đã nhớ "video" của người thường rơi về tab mặc định (show).
  if (chu) panels.video = () => `<p class="small">Thông tin đưa sang <b>/tao-video-tu-canh-quay</b>:</p>
       <pre class="cmd">${esc(prompt)}</pre>
       <div class="row"><button class="btn sm" data-copy="${esc(prompt)}">Copy cho Claude</button>
       ${i.uid ? `<button class="btn ghost sm" data-copy="${esc(lenh)}">Copy lệnh kéo caption</button>` : ""}</div>
       <p class="small muted">Thư mục máy nhà: ${esc(i.thu_muc_may || "chưa có")}</p>`;
  // Dải 8 bước đầu trang (chỉ chủ kho).
  const veBuoc = () => {
    if (phien !== phienCT) return; // trang này đã bị thay: #buoc8 hiện tại là của SP khác
    const box = $("#buoc8");
    if (!box) return;
    const ds = tinhBuoc(i, may.tienDo, duyet, may.ds), ht = buocHienTai(ds);
    const tat = !may.tai && (!may.tienDo || !may.ds);
    const gc = (s) => (may.tai ? s.replace("máy nhà tắt", "đang tải…") : s);
    box.innerHTML = `<div class="buoc8-dau"><b>Tiến độ 8 bước</b> <span class="small muted">${may.tai ? "đang hỏi máy nhà…" : tat ? "⚠ máy nhà tắt" : ht ? `đang ở bước ${ht}` : "✓ Hoàn tất"}</span></div>
      <ol class="buoc8-ds">${ds.map((b) => `<li class="bc s-${b.trang_thai}${b.so === ht ? " hien-tai" : ""}" title="${esc(b.ten + (b.ghi_chu ? " — " + gc(b.ghi_chu) : ""))}">
        <span class="bc-so">${b.trang_thai === "xong" ? "✓" : b.trang_thai === "bo_qua" ? "–" : b.so}</span><span class="bc-ten">${esc(b.ten)}</span><span class="bc-gc">${esc(gc(b.ghi_chu))}</span></li>`).join("")}</ol>`;
    if (!may.tai) veViecSp({ ...i, co_douyin: !!douyin }, ds, phien); // viec.js: nút ▶ Chạy theo bước hiện tại
    veBuocTiep();
  };
  // Khối "Bước tiếp theo" (W-7, loi.js): chủ kho dùng tinhBuoc/buocHienTai khi máy nhà đã trả lời; còn lại theo trang_thai.
  const veBuocTiep = () => {
    if (phien !== phienCT) return;
    const box = $("#buoc-tiep");
    if (!box) return;
    let ht = null, ghiChu = "", coSan;
    if (chu && may.tai) ghiChu = "Đang hỏi máy nhà để biết chính xác bước tiếp theo…";
    else if (chu) {
      ht = buocHienTai(tinhBuoc(i, may.tienDo, duyet, may.ds));
      if (!may.tienDo || !may.ds) ghiChu = "⚠ Máy nhà đang tắt — bước tiếp theo có thể chưa chính xác.";
      // Nút chính "viec:<loai>" chỉ khi khối việc (goiYViec, cùng đợt bật) thật sự có nút loại đó (viec.js).
      coSan = typeof goiYViec === "function"
        ? goiYViec(ht, { ...i, co_douyin: !!douyin }, typeof dotBatViec === "number" ? dotBatViec : undefined).nut.map((n) => n.loai) : [];
    }
    box.innerHTML = buocTiepHtml(buocTiepTheo(ht, tt, chu, coSan), ghiChu);
  };
  const vtkHtml = (v) => `<div class="vtk" data-vid="${esc(v.vid)}">
      <div class="vtk-head">
        <div style="min-width:0">
          <a href="${esc(v.link)}" target="_blank" rel="noopener" class="vtk-link">${esc(v.link)}</a>
          ${v.ghi_chu ? `<div class="small">📝 ${esc(v.ghi_chu)}</div>` : ""}
          <div class="small muted"><span class="badge ${v.trang_thai === "da_phan_tich" ? "b-da_phan_tich" : "b-cho"}">${v.trang_thai === "da_phan_tich" ? `Đã phân tích · ${v.so_canh || "?"} cảnh · ${v.thoi_luong ? Math.round(v.thoi_luong) + "s" : ""}` : "Chờ phân tích"}</span>
            ${esc(v.them_boi || "?")} · ${gio(v.them_luc)}</div>
        </div>
        <div class="row" style="flex:none">
          ${v.trang_thai === "da_phan_tich" ? `<button class="btn sm" data-vtk-xem>Xem cảnh</button>` : ""}
          <button class="btn ghost sm" data-vtk-xoa title="Xoá khỏi danh sách">✕</button>
        </div>
      </div>
      <div class="vtk-canh"></div>
    </div>`;
  const giay = (x) => (Number(x) || 0).toFixed(1).replace(/\.0$/, "") + "s";
  const canhHtml = (v, c) => `<div class="canh">
      ${c.anh ? `<img src="/api/anh/${encodeURIComponent(i.id)}/video_tk/${encodeURIComponent(v.vid)}/${encodeURIComponent(c.anh)}" loading="lazy" alt="">` : `<div class="img"></div>`}
      <div class="canh-body">
        <div><b>#${esc(c.so)}</b> <span class="badge b-cho">${giay(c.bat_dau)} – ${giay(c.ket_thuc)}</span> <span class="small muted">${giay(c.ket_thuc - c.bat_dau)}</span>
          ${c.noi_tiep ? `<span class="small muted" title="Cùng cú máy với đoạn trước, không có nhát cắt">↳ nối tiếp, không cắt</span>` : ""}</div>
        <div>${esc(c.noi_dung)}</div>
        <div class="small muted">🎥 ${esc(c.goc_may)} · 🔍 ${esc(c.co_canh)} · ↔ ${esc(c.chuyen_dong)}</div>
      </div>
    </div>`;
  const bindVtk = () => {
    $("#form-vtk")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const link = $("#in-vtk-link").value.trim(), ghi_chu = $("#in-vtk-note").value.trim();
      if (!link) return;
      const btn = $("#form-vtk button"); btn.disabled = true; btn.textContent = "Đang lưu…";
      try { vtk = (await api("vtk", { id: i.id, link, ghi_chu })).vtk; $("#vtk-dem").textContent = vtk.length; show("vtk"); toast("✓ Đã thêm — chờ máy nhà phân tích"); }
      catch (err) { toast("⚠ " + err.message); btn.disabled = false; btn.textContent = "Thêm video"; }
    });
    document.querySelectorAll("[data-vtk-xoa]").forEach((b) => b.addEventListener("click", async () => {
      const vid = b.closest(".vtk").dataset.vid;
      if (!confirm("Xoá video này khỏi danh sách tham khảo?")) return;
      try { vtk = (await api("vtk-xoa", { id: i.id, vid })).vtk; $("#vtk-dem").textContent = vtk.length; show("vtk"); toast("Đã xoá"); }
      catch (err) { toast("⚠ " + err.message); }
    }));
    document.querySelectorAll("[data-vtk-xem]").forEach((b) => b.addEventListener("click", async () => {
      const box = $(".vtk-canh", b.closest(".vtk"));
      if (box.innerHTML) { box.innerHTML = ""; b.textContent = "Xem cảnh"; return; }
      box.innerHTML = `<p class="muted small">Đang tải…</p>`;
      try {
        const pt = await api(`vtk/${encodeURIComponent(i.id)}/${encodeURIComponent(b.closest(".vtk").dataset.vid)}`);
        box.innerHTML = (pt.canh || []).map((c) => canhHtml(pt, c)).join("") || `<p class="muted small">Không có cảnh nào.</p>`;
        b.textContent = "Ẩn cảnh";
      } catch (err) { box.innerHTML = `<p class="err">${esc(err.message)}</p>`; }
    }));
  };
  const show = (k) => {
    if (k === "ruiro") k = "tt"; // W-M3: tab Rủi ro gộp vào Tóm tắt
    if (!panels[k]) k = md ? "canh" : "cap"; // tab đã nhớ không còn (vd tab Duyệt đã dời sang trang Duyệt video)
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === k));
    $("#panel").innerHTML = panels[k]();
    sessionStorage.setItem("kho_tab", k);
    $("#panel [data-copy-random]")?.addEventListener("click", () => {
      const k = Math.floor(Math.random() * capList.length);
      copy(capList[k], `Đã copy caption #${k + 1}`);
    });
    $("#panel [data-copy-all]")?.addEventListener("click", () => copy(capList.join("\n"), `Đã copy ${capList.length} caption`));
    bindVtk();
    if (k === "douyin") bindDouyin();
    $("#btn-note")?.addEventListener("click", async () => {
      if (!needLogin()) return;
      const v = $("#in-note").value;
      try { await api("ghichu", { id: i.id, ghi_chu: v }); i.ghi_chu = v; toast("✓ Đã lưu ghi chú"); }
      catch (err) { toast("⚠ " + err.message); }
    });
  };
  // Tab Douyin: mỗi dòng bảng có tên file .mp4 → thêm nút ▶ phát thẳng (stream từ máy nhà, tua được).
  const bindDouyin = () => {
    if (auth.user !== "nhan" && auth.user !== "comeofage") return;
    const codes = [...document.querySelectorAll("#panel .md code")].filter((c) => /\.mp4$/i.test(c.textContent.trim()));
    if (!codes.length) return;
    $("#panel").insertAdjacentHTML("afterbegin", `<div id="dy-player" class="dy-player" hidden><div class="small"><b id="dy-ten"></b> <button class="btn ghost sm" id="dy-dong">✕ Đóng</button></div><video id="dy-video" controls playsinline preload="metadata"></video></div>`);
    const vd = $("#dy-video"), box = $("#dy-player");
    $("#dy-dong").addEventListener("click", () => { vd.pause(); vd.removeAttribute("src"); vd.load(); box.hidden = true; });
    codes.forEach((c) => {
      const ten = c.textContent.trim();
      const b = document.createElement("button");
      b.className = "btn sm"; b.textContent = "▶"; b.title = "Xem video này ngay trên web";
      b.addEventListener("click", () => {
        vd.src = `/api/video/${encodeURIComponent(i.id)}/dyfile?ten=${encodeURIComponent(ten)}`;
        $("#dy-ten").textContent = ten; box.hidden = false;
        box.scrollIntoView({ block: "nearest", behavior: "smooth" });
        vd.play().catch(() => {});
      });
      c.after(" ", b);
    });
    vd.addEventListener("error", async () => {
      if (!vd.getAttribute("src")) return; // vừa bấm Đóng
      const url = vd.getAttribute("src"), mc = vd.error ? vd.error.code : "?";
      let http = "?", ct = "", loi = "";
      try { const r = await fetch(url, { headers: { range: "bytes=0-1" } }); http = r.status; ct = r.headers.get("content-type") || ""; if (!r.ok) loi = (await r.json().catch(() => ({}))).loi || ""; }
      catch (e) { http = "mạng: " + e.message; }
      $("#dy-ten").insertAdjacentHTML("afterend", ` <span class="small">⚠ HTTP ${esc(String(http))} · lỗi player ${mc} · ${esc(ct)} ${esc(loi)} · <a href="${esc(url)}" target="_blank">mở tab riêng</a></span>`);
      toast(`⚠ Không phát được (HTTP ${http}, player ${mc}) ${loi}`);
    });
  };
  document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
  show(sessionStorage.getItem("kho_tab") || (md ? "canh" : "cap"));
  bindSwitches();
  // Nút của "Bước tiếp theo": sang trang Poster V2, mở tab có sẵn, hoặc bấm đúng nút việc có sẵn trong khối việc.
  $("#buoc-tiep")?.addEventListener("click", (e) => { // chỉ chủ kho có khối này (P-33)
    const b = e.target.closest("button[data-bt-lam], button[data-bt-phu]");
    if (!b || phien !== phienCT) return;
    const lam = b.dataset.btLam || b.dataset.btPhu || "", cuon = (el) => el && el.scrollIntoView({ block: "start", behavior: "smooth" });
    if (lam.startsWith("trang:")) {
      const trang = lam.slice(6);
      if (trang === "poster") location.hash = "#/poster";
      return;
    }
    if (lam.startsWith("tab:")) { show(lam.slice(4)); cuon($(".tabs")); return; }
    const khoi = $("#viec-sp");
    const loai = lam.startsWith("viec:") ? lam.slice(5) : "";
    const nut = /^[a-z_]+$/.test(loai) && khoi ? $(`[data-vs-loai="${loai}"]`, khoi) : null;
    if (nut && !nut.disabled) nut.click();
    cuon(khoi);
  });
  veBuocTiep();
  // Khối việc (viec.js) vẽ lại khi biết đợt bật / danh sách việc → tính lại nút chính cho khớp nút có thật trong khối.
  const khoiViecSp = $("#viec-sp");
  if (chu && khoiViecSp && typeof MutationObserver === "function") {
    const theoDoi = new MutationObserver(() => {
      if (phien !== phienCT) { theoDoi.disconnect(); return; }
      if (!may.tai) veBuocTiep();
    });
    theoDoi.observe(khoiViecSp, { childList: true });
  }
  if (chu) {
    veBuoc();
    // Hỏi máy nhà song song; lỗi nào thì phần đó coi như máy nhà tắt, không làm vỡ trang.
    Promise.allSettled([api(`video/${encodeURIComponent(i.id)}/tien-do`), api(`video/${encodeURIComponent(i.id)}/ds`)]).then(([a, b]) => {
      if (phien !== phienCT || !$("#buoc8")) return; // đã rời trang này
      may.tai = false;
      may.tienDo = a.status === "fulfilled" ? { thu_muc: Array.isArray(a.value.thu_muc) ? a.value.thu_muc : [] } : null;
      may.ds = b.status === "fulfilled" ? b.value : null;
      veBuoc();
    });
  }
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-copy]");
  if (!b) return;
  e.preventDefault(); // nút copy nằm trong link thẻ sản phẩm → không mở trang chi tiết
  copy(b.dataset.copy, b.dataset.copyMsg);
});

// ---------- router ----------
async function route() {
  if (typeof dungSua === "function") dungSua(); // sua.js: dừng thăm dò + bỏ phản hồi muộn của màn sửa cũ
  dungViec(); // viec.js: dừng polling + bỏ phản hồi muộn của trang việc cũ (kể cả khi vừa đăng xuất)
  danhDauNav();
  if (!auth.on) { $("#app").innerHTML = `<p class="muted center">Đăng nhập để xem kho.</p>`; openLogin(); return; }
  const m = location.hash.match(/^#\/sp\/(.+)$/);
  const mv = location.hash.match(/^#\/viec\/([^/]+)$/);
  const ms = location.hash.match(/^#\/sua\/(\d{19})\/([0-9a-f]{16})$/);
  // P-33: người không phải chủ kho chỉ xem Kho (+ trang SP): #/ và hash lạ → Kho; trang máy nhà → CHI_CHU_HTML.
  const chu = laChu();
  try {
    if (typeof mnRoute === "function" && await mnRoute(location.hash, chu)) return; // khung.js: Cần quay, Máy nhà, Poster V2, link cũ #/duyet|#/dang (+ #/viec, #/suc-khoe)
    if (m) await renderDetail(decodeURIComponent(m[1]));
    else if (!chu && (ms || mv || location.hash === "#/viec" || location.hash === "#/suc-khoe")) { phienCT++; $("#app").innerHTML = CHI_CHU_HTML; }
    else if (ms) { phienCT++; await renderSua(ms[1], ms[2]); }
    else if (mv) { phienCT++; await renderViecChiTiet(decodeURIComponent(mv[1])); }
    else if (location.hash === "#/kho" || !chu) {
      const p = ++phienCT;
      if (!state.list.length || route.reload) await loadList();
      route.reload = false;
      if (p === phienCT) renderList(); // đã sang trang khác trong lúc tải: không vẽ đè
    }
    else { route.reload = false; await renderHomNay(); } // #/ (mặc định): homnay.js — luôn tải mới 3 nguồn
  } catch (err) {
    $("#app").innerHTML = `<p class="err">⚠ ${esc(err.message)}</p>`;
  }
}

window.addEventListener("hashchange", () => { if (!location.hash.startsWith("#/sp/")) route.reload = false; route(); });
window.addEventListener("DOMContentLoaded", async () => {
  $("#form-login").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#login-err").textContent = "Đang kiểm tra…";
    try {
      const r = await api("login", { user: $("#in-user").value.trim(), pass: $("#in-pass").value });
      auth.user = r.user; auth.ten = r.ten;
      $("#in-pass").value = "";
      $("#dlg-login").close();
      renderUser(); route.reload = true; await route();
      if (linkCho) onAdd();
      toast(`Xin chào ${auth.ten}`);
    } catch (err) { $("#login-err").textContent = err.message; }
  });
  try { const me = await api("me"); auth.user = me.user; auth.ten = me.ten; } catch { /* chưa đăng nhập */ }
  renderUser();
  route();
});

// Tải video trong output_poster của máy nhà về điện thoại: nút "video kế tiếp" tải 1 file rồi xóa file gốc.
// (iPhone Safari không cho tải nhiều file cùng lúc từ 1 lượt chạm nên chỉ còn nút tải từng video.)
// Chỉ còn ở trang Đăng bài (dang.js, W-M3). opt.laLoai(goc, ten, sua_luc): mỗi nguồn chọn file ĐẦU TIÊN trong chi_tiet không bị
// Loại rồi tải bằng /file?goc&ten (Worker nhận ten); hết file hợp lệ → câu báo, bấm không tải gì. KHÔNG khoá nút (P2-2):
// chấm lại xong bấm là tải được ngay. Không có opt.laLoai → như cũ (file kế tiếp máy nhà đưa).
function bindVideo(id, opt = {}) {
  const box = $("#vd-btns"), st = $("#vd-st");
  if (!box) return;
  const laLoai = opt && typeof opt.laLoai === "function" ? opt.laLoai : null;
  const HET = "Không còn video nào chưa bị Loại";
  const api = (act, q = "", method = "GET") => fetch(`/api/video/${encodeURIComponent(id)}/${act}${q}`, { method });
  // File sẽ tải của 1 nguồn → {ten, mb} | null. Có laLoai mà không có chi_tiet: không biết video nào bị Loại → không tải (thiên về chặt).
  const chon = (n) => {
    if (!n || typeof n !== "object") return null;
    if (!laLoai) return n.ten ? { ten: n.ten, mb: n.mb } : null;
    const c = (Array.isArray(n.chi_tiet) ? n.chi_tiet : []).find((x) => x && typeof x.ten === "string" && x.ten && !laLoai(n.goc, x.ten, x.sua_luc));
    return c ? { ten: c.ten, mb: c.mb } : null;
  };
  const dsNguon = (d) => (d && Array.isArray(d.nguon) ? d.nguon : []);
  const kiem = async () => {
    try {
      const r = await api("ds");
      const d = await r.json();
      if (!r.ok) throw new Error(d.loi || "Lỗi");
      const nguon = dsNguon(d);
      const nhieu = nguon.length > 1;
      box.innerHTML = nguon.map((n) => {
        const tienTo = nhieu ? esc(n.goc) + " — " : "";
        return `<button class="btn sm" data-goc="${esc(n.goc)}" title="Tải 1 video kế tiếp về máy${nhieu ? " từ " + esc(n.goc) : ""}, xong xóa khỏi máy nhà">⬇ ${tienTo}video kế tiếp</button>`;
      }).join(" ");
      box.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => tai(b.dataset.goc)));
      st.textContent = !d.co_folder ? "máy nhà chưa có folder output_poster cho sản phẩm này"
        : !d.tong ? "hết video"
        : nguon.map((n) => { const c = chon(n); return `${nhieu ? n.goc + ": " : ""}còn ${n.tong} · ${c ? `kế tiếp ${c.ten} (${c.mb} MB)` : HET}`; }).join(" — ");
      return d;
    } catch (e) { box.innerHTML = ""; st.textContent = e.message; }
  };
  const tai = async (goc) => {
    const d = await kiem();
    const n = dsNguon(d).find((x) => x.goc === goc);
    if (!n) return;
    const c = chon(n);
    if (!c) { toast(`${HET}${dsNguon(d).length > 1 ? " ở " + goc : ""}: kiểm lại video lúc tạo nếu chấm nhầm.`); return; }
    box.querySelectorAll("button").forEach((b) => (b.disabled = true));
    st.textContent = `đang tải ${c.ten}…`;
    const a = document.createElement("a");
    a.href = `/api/video/${encodeURIComponent(id)}/file?goc=${encodeURIComponent(goc)}&ten=${encodeURIComponent(c.ten)}&xoa=1`;
    a.download = c.ten;
    document.body.append(a); a.click(); a.remove();
    toast(`Đang tải ${c.ten} — xong máy nhà sẽ tự xóa file này`);
    // Chờ máy nhà gửi xong (file biến mất khỏi danh sách) rồi mới mở nút lại.
    for (let k = 0; k < 60; k++) {
      await new Promise((r) => setTimeout(r, 3000));
      const t = await kiem();
      const m = dsNguon(t).find((x) => x.goc === goc);
      const con = !!m && (Array.isArray(m.chi_tiet) ? m.chi_tiet.some((x) => x && x.ten === c.ten) : m.ten === c.ten);
      if (t && !con) { toast(`Đã tải ${c.ten} và xóa ở máy nhà`); return; }
      box.querySelectorAll("button").forEach((b) => (b.disabled = true));
    }
    kiem();
  };
  kiem();
}
