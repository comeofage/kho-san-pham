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
const soLoaiDaQuay = (x) => Object.keys(LOAI_QUAY).filter((l) => quay(x, l).xong).length;
const LOC_THEM = { yeu_thich: "★ Yêu thích", can_dang: "⬆ Cần đăng", chua_oneshot: "Chưa quay oneshot", chua_review: "Chưa quay review" };
const TAG_RIENG = { yeu_thich: ["★", "Yêu thích"], can_dang: ["⬆", "Cần đăng"] };
function tagHtml(x) {
  return `<div class="tagbtns">${Object.entries(TAG_RIENG).map(([t, [ic, ten]]) =>
    `<button type="button" class="tagbtn ${x[t] ? "on" : ""}" data-tag="${t}" data-id="${esc(x.id)}" title="${x[t] ? "Bỏ thẻ" : "Gắn thẻ"} ${ten}" aria-pressed="${!!x[t]}">${ic}</button>`).join("")}</div>`;
}
const theCua = (x) => Array.isArray(x.the) ? x.the : [];
function khopLoc(x, loc) {
  if (loc === "tat_ca") return true;
  if (loc.startsWith("the:")) return theCua(x).includes(loc.slice(4));
  if (loc === "yeu_thich" || loc === "can_dang") return !!x[loc];
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

function cardHtml(x, stt) {
  const tt = x.trang_thai || trangThai(x);
  const img = anhBia(x);
  return `<div class="card">
    ${img ? `<img class="thumb" src="${esc(img)}" referrerpolicy="no-referrer" loading="lazy" alt="">` : `<div class="thumb"></div>`}
    <a class="body" href="#/sp/${encodeURIComponent(x.id)}">
      <div class="ten"><span class="stt">#${stt}</span> ${esc(x.ten || x.link)}</div>
      <div class="small muted"><span class="badge b-${tt}">${NHAN[tt]}</span>${x.gia ? " <b>" + esc(x.gia) + "</b> ·" : ""} ${x.uid ? `<span class="uid-copy" role="button" title="Bấm để copy UID" data-copy="${esc(x.uid)}" data-copy-msg="Đã copy UID ${esc(x.uid)}">${esc(x.uid)} ⧉</span>` : "link rút gọn"}${theCua(x).map((t) => ` <span class="the-rieng">#${esc(t)}</span>`).join("")}</div>
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

function bindSwitches() {
  document.querySelectorAll("[data-tag]").forEach((b) => b.addEventListener("click", async () => {
    if (!needLogin()) return;
    const id = b.dataset.id, tag = b.dataset.tag, bat = !b.classList.contains("on");
    b.disabled = true;
    try {
      const { info } = await api("tag", { id, tag, bat });
      const k = state.list.findIndex((x) => x.id === id);
      if (k >= 0) state.list[k] = { ...state.list[k], [tag]: !!info[tag], cap_nhat_luc: info.cap_nhat_luc };
      toast(`${bat ? "✓ Đã gắn" : "Đã bỏ"} thẻ ${TAG_RIENG[tag][1]}`);
      renderList();
    } catch (err) { b.disabled = false; toast("⚠ " + err.message); }
  }));
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

// Đợt sale 11/11: trong khoảng này caption giữ 2 hashtag sản phẩm đầu + 3 tag chiến dịch = 5 tag (file captions.txt giữ nguyên).
const TAG_DOT = { tu: new Date("2026-10-31T00:00:00+07:00"), den: new Date("2026-11-12T00:00:00+07:00"),
  tag: "#TikTokShop1111 #SaleToVoDoi #Zocoby" };
function doiTag(c) {
  const now = new Date();
  if (!c || now < TAG_DOT.tu || now >= TAG_DOT.den) return c;
  const giu = (c.match(/#\S+/g) || []).slice(0, 2);
  return [c.replace(/#\S+/g, "").replace(/\s+/g, " ").trim(), ...giu, TAG_DOT.tag].join(" ");
}

// ---------- trang chi tiết ----------
async function renderDetail(id) {
  $("#app").innerHTML = `<p class="muted center">Đang tải…</p>`;
  let d;
  try { d = await api(`sp/${encodeURIComponent(id)}`); }
  catch (err) { $("#app").innerHTML = `<p class="center">${esc(err.message)}. <a href="#/">← Về kho</a></p>`; return; }
  const { info: i, md, caps, douyin } = d;
  let vtk = d.vtk || [];
  const tt = trangThai(i);
  const capList = (caps || "").split(/\r?\n/).map((s) => doiTag(s.trim())).filter(Boolean);
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
            ${auth.user === "nhan" || auth.user === "comeofage" ? `<dt>Tải về</dt><dd><span id="vd-btns"></span> <span class="small muted" id="vd-st">đang kiểm…</span></dd>` : ""}
            <dt>Link</dt><dd><a href="${esc(i.link)}" target="_blank" rel="noopener">${esc(i.link)}</a></dd>
            ${i.gia ? `<dt>Giá</dt><dd>${esc(i.gia)}</dd>` : ""}
            ${i.shop ? `<dt>Shop</dt><dd>${esc(i.shop)}</dd>` : ""}
            <dt>Thêm</dt><dd>${esc(i.them_boi || "?")} · ${gio(i.them_luc)}</dd>
            ${i.da_lam_video && i.da_lam_video.xong ? `<dt>Video</dt><dd>${i.da_lam_video.so_video} video · ${gio(i.da_lam_video.luc)}</dd>` : ""}
            ${i.da_lam_video && i.da_lam_video.xong ? ((i.da_lam_video.poster && i.da_lam_video.poster.length ? i.da_lam_video.poster : (i.da_lam_video.poster_folder != null || i.da_lam_video.duong_dan ? [{ folder: i.da_lam_video.poster_folder, duong_dan: i.da_lam_video.duong_dan }] : [])).map((p) => `<dt>Poster</dt><dd>${p.nhan ? esc(p.nhan) + " · " : ""}${p.folder != null ? "folder " + esc(String(p.folder)) : ""}${p.so_video ? " · " + esc(String(p.so_video)) + " video" : ""}${p.duong_dan ? ` · <code>${esc(p.duong_dan)}</code>` : ""}</dd>`).join("")) : ""}
          </dl>
        </div>
      </div>
      ${Object.keys(LOAI_QUAY).map((l) => { const q = quay(i, l); return `<div class="quaybox">
        <div class="small">${q.xong ? `🎬 <b>${esc(q.boi)}</b> đã quay ${LOAI_QUAY[l]} lúc ${gio(q.luc)}` : `Chưa quay ${LOAI_QUAY[l]} — gạt khi quay xong để lần sau không làm trùng`}</div>
        ${switchHtml(i, l, `Đã quay ${LOAI_QUAY[l]}`)}
      </div>`; }).join("")}
      <div class="tabs">
        <button class="tab" data-tab="canh">🎥 Bộ cảnh quay</button>
        <button class="tab" data-tab="douyin">🎵 Douyin</button>
        <button class="tab" data-tab="cap">💬 Caption (${capList.length})</button>
        <button class="tab" data-tab="tt">📋 Tóm tắt & USP</button>
        <button class="tab" data-tab="vtk">🎬 Video tham khảo (<span id="vtk-dem">${vtk.length}</span>)</button>
        <button class="tab" data-tab="video">🎞 Làm video</button>
        <button class="tab" data-tab="note">📝 Ghi chú</button>
      </div>
      <div class="panel" id="panel"></div>
    </div>`;
  bindVideo(i.id);

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
       ${i.tom_tat ? `<h3>Tóm tắt sản phẩm</h3><div class="md">${window.DOMPurify && window.marked ? DOMPurify.sanitize(marked.parse(i.tom_tat)) : `<pre>${esc(i.tom_tat)}</pre>`}</div>` : ""}`,
    video: () => `<p class="small">Thông tin đưa sang <b>/tao-video-tu-canh-quay</b>:</p>
       <pre class="cmd">${esc(prompt)}</pre>
       <div class="row"><button class="btn sm" data-copy="${esc(prompt)}">Copy cho Claude</button>
       ${i.uid ? `<button class="btn ghost sm" data-copy="${esc(lenh)}">Copy lệnh kéo caption</button>` : ""}</div>
       <p class="small muted">Thư mục máy nhà: ${esc(i.thu_muc_may || "chưa có")}</p>`,
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
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === k));
    $("#panel").innerHTML = panels[k]();
    sessionStorage.setItem("kho_tab", k);
    $("#panel [data-copy-random]")?.addEventListener("click", () => {
      const k = Math.floor(Math.random() * capList.length);
      copy(capList[k], `Đã copy caption #${k + 1}`);
    });
    $("#panel [data-copy-all]")?.addEventListener("click", () => copy(capList.join("\n"), `Đã copy ${capList.length} caption`));
    bindVtk();
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
  if (!b) return;
  e.preventDefault(); // nút copy nằm trong link thẻ sản phẩm → không mở trang chi tiết
  copy(b.dataset.copy, b.dataset.copyMsg);
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

// Tải video trong output_poster của máy nhà về điện thoại: nút "video kế tiếp" tải 1 file rồi xóa file gốc.
// (iPhone Safari không cho tải nhiều file cùng lúc từ 1 lượt chạm nên chỉ còn nút tải từng video.)
function bindVideo(id) {
  const box = $("#vd-btns"), st = $("#vd-st");
  if (!box) return;
  const api = (act, q = "", method = "GET") => fetch(`/api/video/${encodeURIComponent(id)}/${act}${q}`, { method });
  const kiem = async () => {
    try {
      const r = await api("ds");
      const d = await r.json();
      if (!r.ok) throw new Error(d.loi || "Lỗi");
      const nhieu = d.nguon.length > 1;
      box.innerHTML = d.nguon.map((n) => {
        const tienTo = nhieu ? esc(n.goc) + " — " : "";
        return `<button class="btn sm" data-goc="${esc(n.goc)}" title="Tải 1 video kế tiếp về máy${nhieu ? " từ " + esc(n.goc) : ""}, xong xóa khỏi máy nhà">⬇ ${tienTo}video kế tiếp</button>`;
      }).join(" ");
      box.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => tai(b.dataset.goc)));
      st.textContent = !d.co_folder ? "máy nhà chưa có folder output_poster cho sản phẩm này"
        : !d.tong ? "hết video"
        : d.nguon.map((n) => `${nhieu ? n.goc + ": " : ""}còn ${n.tong} · kế tiếp ${n.ten} (${n.mb} MB)`).join(" — ");
      return d;
    } catch (e) { box.innerHTML = ""; st.textContent = e.message; }
  };
  const tai = async (goc) => {
    const d = await kiem();
    const n = d && d.nguon.find((x) => x.goc === goc);
    if (!n) return;
    box.querySelectorAll("button").forEach((b) => (b.disabled = true));
    st.textContent = `đang tải ${n.ten}…`;
    const a = document.createElement("a");
    a.href = `/api/video/${encodeURIComponent(id)}/file?goc=${encodeURIComponent(goc)}&ten=${encodeURIComponent(n.ten)}&xoa=1`;
    a.download = n.ten;
    document.body.append(a); a.click(); a.remove();
    toast(`Đang tải ${n.ten} — xong máy nhà sẽ tự xóa file này`);
    // Chờ máy nhà gửi xong (video biến mất khỏi danh sách) rồi mới mở nút lại.
    for (let k = 0; k < 60; k++) {
      await new Promise((r) => setTimeout(r, 3000));
      const t = await kiem();
      const m = t && t.nguon.find((x) => x.goc === goc);
      if (t && (!m || m.ten !== n.ten)) { toast(`Đã tải ${n.ten} và xóa ở máy nhà`); return; }
      box.querySelectorAll("button").forEach((b) => (b.disabled = true));
    }
    kiem();
  };
  kiem();
}
