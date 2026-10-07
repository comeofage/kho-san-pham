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
  if (r.status === 401 && path !== "login") { auth.user = ""; renderUser(); openLogin(); throw new Error("Hết phiên đăng nhập — đăng nhập lại"); }
  if (!r.ok && r.status !== 409) throw new Error(j.loi || `Lỗi ${r.status}`);
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
    ? `<span class="small muted">👤 ${esc(auth.ten)}</span> <button class="btn ghost sm" id="btn-out">Thoát</button>`
    : `<button class="btn sm" id="btn-in">Đăng nhập</button>`;
  $("#btn-out", u)?.addEventListener("click", async () => {
    await api("logout", {}).catch(() => {});
    auth.user = ""; state.list = []; renderUser(); route();
  });
  $("#btn-in", u)?.addEventListener("click", openLogin);
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
const LOC_THEM = { chua_oneshot: "Chưa quay oneshot", chua_review: "Chưa quay review" };
function khopLoc(x, loc) {
  if (loc === "tat_ca") return true;
  if (loc === "chua_oneshot") return !quay(x, "oneshot").xong;
  if (loc === "chua_review") return !quay(x, "review").xong;
  return (x.trang_thai || trangThai(x)) === loc;
}

function renderList() {
  const dem = {};
  for (const k of ["tat_ca", ...Object.keys(NHAN), ...Object.keys(LOC_THEM)]) dem[k] = state.list.filter((x) => khopLoc(x, k)).length;
  const q = state.tim.toLowerCase();
  const ds = state.list.filter((x) => khopLoc(x, state.loc)
    && (!q || [x.ten, x.uid, x.link, x.shop, x.them_boi].join(" ").toLowerCase().includes(q)));

  $("#app").innerHTML = `
    <form class="add" id="form-add">
      <input id="in-link" placeholder="Dán link sản phẩm TikTok Shop…" autocomplete="off">
      <button class="btn">Lưu</button>
    </form>
    <p id="add-msg" class="add-msg ${state.msg ? esc(state.msg.loai) : ""}">${state.msg ? esc(state.msg.text) : ""}</p>
    <div class="filters">
      ${[["tat_ca", "Tất cả"], ...Object.entries(LOC_THEM), ...Object.entries(NHAN)].map(([k, v]) => `<button class="chip ${state.loc === k ? "on" : ""}" data-loc="${k}">${v} (${dem[k]})</button>`).join("")}
    </div>
    <input class="search" id="in-tim" placeholder="Tìm theo tên, UID, shop…" value="${esc(state.tim)}">
    <div class="list">
      ${ds.length ? ds.map(cardHtml).join("") : `<p class="muted center">${state.list.length ? "Không có sản phẩm khớp." : "Kho trống — dán link đầu tiên ở trên."}</p>`}
    </div>`;

  $("#form-add").addEventListener("submit", onAdd);
  document.querySelectorAll("[data-loc]").forEach((b) => b.addEventListener("click", () => { state.loc = b.dataset.loc; renderList(); }));
  const tim = $("#in-tim");
  tim.addEventListener("input", () => { state.tim = tim.value; renderList(); const t = $("#in-tim"); t.focus(); t.setSelectionRange(t.value.length, t.value.length); });
  bindSwitches();
}

function cardHtml(x) {
  const tt = x.trang_thai || trangThai(x);
  const img = anhBia(x);
  return `<div class="card">
    ${img ? `<img class="thumb" src="${esc(img)}" referrerpolicy="no-referrer" loading="lazy" alt="">` : `<div class="thumb"></div>`}
    <a class="body" href="#/sp/${encodeURIComponent(x.id)}">
      <div class="ten">${esc(x.ten || x.link)}</div>
      <div class="small muted"><span class="badge b-${tt}">${NHAN[tt]}</span> ${esc(x.uid || "link rút gọn")}${x.gia ? " · " + esc(x.gia) : ""}</div>
      <div class="small muted">${daQuayText(x) || `Thêm bởi ${esc(x.them_boi || "?")} ${gio(x.them_luc)}`}</div>
    </a>
    <div class="switches">${switchHtml(x, "oneshot")}${switchHtml(x, "review")}</div>
  </div>`;
}

// "🎬 Oneshot: Lan 06/10 · Review: Minh 07/10" — rỗng nếu chưa quay gì.
function daQuayText(x) {
  return Object.keys(LOAI_QUAY).map((l) => { const q = quay(x, l); return q.xong ? `${LOAI_QUAY[l]}: ${esc(q.boi)} ${gio(q.luc).slice(5)}` : ""; })
    .filter(Boolean).map((s, k) => (k ? "" : "🎬 ") + s).join(" · ");
}

function bindSwitches() {
  document.querySelectorAll("[data-quay]").forEach((sw) => {
    const cb = $("input", sw);
    cb.addEventListener("change", async (e) => {
      const id = sw.dataset.quay, loai = sw.dataset.loai, ten = LOAI_QUAY[loai], val = cb.checked;
      if (!needLogin()) { cb.checked = !val; return; }
      if (!val && !confirm(`Gỡ đánh dấu 'đã quay ${ten}' cho sản phẩm này?`)) { cb.checked = true; return; }
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
        route();
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

let linkCho = ""; // link dán lúc chưa đăng nhập — lưu tiếp sau khi đăng nhập
function baoAdd(text, loai = "") {
  state.msg = { text, loai };
  const el = $("#add-msg");
  if (el) { el.textContent = text; el.className = `add-msg ${loai}`; }
}

async function onAdd(e) {
  e?.preventDefault();
  const raw = e ? $("#in-link").value : linkCho;
  if (!raw.trim()) return;
  const link = tachLink(raw);
  if (!link) { baoAdd("⚠ Không thấy link trong nội dung vừa dán — copy lại link sản phẩm.", "loi"); return; }
  if (!auth.on) { linkCho = raw; baoAdd("Đăng nhập xong sẽ tự lưu link này."); openLogin(); return; }
  linkCho = "";
  const btn = $("#form-add button");
  if (btn) { btn.disabled = true; btn.textContent = "Đang lưu…"; }
  try {
    const r = await api("them", { link });
    if (r.trung) {
      baoAdd(`Đã có trong kho${r.trang_thai ? " — " + NHAN[r.trang_thai] : ""}. Không lưu trùng.`, "loi");
      location.hash = `#/sp/${encodeURIComponent(r.id)}`;
      return;
    }
    state.list.unshift(r.info);
    state.loc = "tat_ca"; state.tim = "";
    renderList();
    baoAdd(r.info.uid ? `✓ Đã lưu ${r.info.uid} — chờ máy nhà phân tích.` : "✓ Đã lưu link rút gọn — máy nhà sẽ tìm UID.", "ok");
  } catch (err) {
    renderList();
    baoAdd("⚠ Lưu không được: " + err.message, "loi");
  }
}

// ---------- trang chi tiết ----------
async function renderDetail(id) {
  $("#app").innerHTML = `<p class="muted center">Đang tải…</p>`;
  let d;
  try { d = await api(`sp/${encodeURIComponent(id)}`); }
  catch (err) { $("#app").innerHTML = `<p class="center">${esc(err.message)}. <a href="#/">← Về kho</a></p>`; return; }
  const { info: i, md, caps } = d;
  const tt = trangThai(i);
  const capList = (caps || "").split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  const img = anhBia(i);
  const lenh = i.uid
    ? `python ${TOOL} lay ${i.uid} --out "${i.thu_muc_may || "<thư mục dự án>"}"`
    : "(link rút gọn — máy nhà chạy `kho.py cho` để tìm UID trước)";
  const linkChuan = i.uid ? `https://shop.tiktok.com/vn/pdp/${i.uid}` : i.link;
  const prompt = `/tao-video-tu-canh-quay\nLink: ${linkChuan}\nUID: ${i.uid || "?"}\nThư mục: ${i.thu_muc_may || "?"}\nCaption: ${lenh}`;

  $("#app").innerHTML = `
    <p><a href="#/" class="small">← Về kho</a></p>
    <div class="detail">
      <div class="head">
        ${img ? `<img src="${esc(img)}" referrerpolicy="no-referrer" alt="">` : ""}
        <div style="min-width:0">
          <h1 title="Bấm để xem đủ tên" onclick="this.classList.toggle('full')">${esc(i.ten || "(chưa có tên — chờ máy nhà phân tích)")}</h1>
          <span class="badge b-${tt}">${NHAN[tt]}</span>
          <dl class="kv">
            <dt>UID</dt><dd>${i.uid ? `${esc(i.uid)} <button class="btn ghost sm" data-copy="${esc(i.uid)}">Copy</button>` : "chưa có"}</dd>
            <dt>Link</dt><dd><a href="${esc(i.link)}" target="_blank" rel="noopener">${esc(i.link)}</a></dd>
            ${i.gia ? `<dt>Giá</dt><dd>${esc(i.gia)}</dd>` : ""}
            ${i.shop ? `<dt>Shop</dt><dd>${esc(i.shop)}</dd>` : ""}
            <dt>Thêm</dt><dd>${esc(i.them_boi || "?")} · ${gio(i.them_luc)}</dd>
            ${i.da_lam_video && i.da_lam_video.xong ? `<dt>Video</dt><dd>${i.da_lam_video.so_video} video · ${gio(i.da_lam_video.luc)}</dd>` : ""}
          </dl>
        </div>
      </div>
      ${Object.keys(LOAI_QUAY).map((l) => { const q = quay(i, l); return `<div class="quaybox">
        <div class="small">${q.xong ? `🎬 <b>${esc(q.boi)}</b> đã quay ${LOAI_QUAY[l]} lúc ${gio(q.luc)}` : `Chưa quay ${LOAI_QUAY[l]} — gạt khi quay xong để lần sau không làm trùng`}</div>
        ${switchHtml(i, l, `Đã quay ${LOAI_QUAY[l]}`)}
      </div>`; }).join("")}
      <div class="tabs">
        <button class="tab" data-tab="canh">🎥 Bộ cảnh quay</button>
        <button class="tab" data-tab="cap">💬 Caption (${capList.length})</button>
        <button class="tab" data-tab="tt">📋 Tóm tắt & USP</button>
        <button class="tab" data-tab="video">🎞 Làm video</button>
        <button class="tab" data-tab="note">📝 Ghi chú</button>
      </div>
      <div class="panel" id="panel"></div>
    </div>`;

  const panels = {
    canh: () => md
      ? `<div class="md">${window.DOMPurify && window.marked ? DOMPurify.sanitize(marked.parse(md)) : `<pre>${esc(md)}</pre>`}</div>`
      : `<p class="muted">Chưa có file bộ cảnh quay. Máy nhà chạy <code>/phantichcanhquay</code> cho link này rồi <code>kho.py ghi</code>.</p>`,
    cap: () => capList.length
      ? `<div class="row" style="justify-content:space-between"><span class="small muted">${capList.length} caption · ≤150 ký tự · 5 hashtag</span>
           <button class="btn sm" data-copy-all>Copy tất cả</button></div>
         <ul class="caps">${capList.map((c, k) => `<li><span class="n">${k + 1}</span><span>${esc(c)}</span><button class="btn ghost sm" data-copy="${esc(c)}">Copy</button></li>`).join("")}</ul>`
      : `<p class="muted">Chưa có caption.</p>`,
    tt: () => `${i.usp && i.usp.cau ? `<h3>USP</h3><p><b>${esc(i.usp.cau)}</b></p><p class="small muted">Từ khoá: ${esc((i.usp.tu_khoa || []).join(", "))}</p>` : `<p class="muted">Chưa có USP.</p>`}
       ${i.tom_tat ? `<h3>Tóm tắt sản phẩm</h3><div class="md">${window.DOMPurify && window.marked ? DOMPurify.sanitize(marked.parse(i.tom_tat)) : `<pre>${esc(i.tom_tat)}</pre>`}</div>` : ""}`,
    video: () => `<p class="small">Thông tin đưa sang <b>/tao-video-tu-canh-quay</b>:</p>
       <pre class="cmd">${esc(prompt)}</pre>
       <div class="row"><button class="btn sm" data-copy="${esc(prompt)}">Copy cho Claude</button>
       ${i.uid ? `<button class="btn ghost sm" data-copy="${esc(lenh)}">Copy lệnh kéo caption</button>` : ""}</div>
       <p class="small muted">Thư mục máy nhà: ${esc(i.thu_muc_may || "chưa có")}</p>`,
    note: () => `<textarea id="in-note" placeholder="Ghi chú cho sản phẩm này…">${esc(i.ghi_chu)}</textarea>
       <div class="row end" style="margin-top:8px"><button class="btn" id="btn-note">Lưu ghi chú</button></div>`,
  };
  const show = (k) => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === k));
    $("#panel").innerHTML = panels[k]();
    sessionStorage.setItem("kho_tab", k);
    $("#panel [data-copy-all]")?.addEventListener("click", () => copy(capList.join("\n"), `Đã copy ${capList.length} caption`));
    $("#btn-note")?.addEventListener("click", async () => {
      if (!needLogin()) return;
      const v = $("#in-note").value;
      try { await api("ghichu", { id: i.id, ghi_chu: v }); i.ghi_chu = v; toast("✓ Đã lưu ghi chú"); }
      catch (err) { toast("⚠ " + err.message); }
    });
  };
  document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
  show(sessionStorage.getItem("kho_tab") || (md ? "canh" : "cap"));
  bindSwitches();
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-copy]");
  if (b) copy(b.dataset.copy);
});

// ---------- router ----------
async function route() {
  if (!auth.on) { $("#app").innerHTML = `<p class="muted center">Đăng nhập để xem kho.</p>`; openLogin(); return; }
  const m = location.hash.match(/^#\/sp\/(.+)$/);
  try {
    if (m) await renderDetail(decodeURIComponent(m[1]));
    else { if (!state.list.length || route.reload) await loadList(); route.reload = false; renderList(); }
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
