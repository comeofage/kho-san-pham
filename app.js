// Kho sản phẩm — web tĩnh trên GitHub Pages, đọc/ghi thẳng repo qua GitHub API.
// Dữ liệu: data/<id>/{info.json, bo-canh-quay.md, captions.txt, bia.jpg}; data/index.json do Action dựng.
"use strict";

const BRANCH = "main";
const NHAN = { cho: "Chờ xử lý", da_phan_tich: "Đã phân tích", da_quay: "Đã quay", da_lam_video: "Đã làm video" };
const TOOL = "E:/phantichcanhquay/kho-san-pham/tools/kho.py";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- cấu hình repo + đăng nhập ----------
function repoInfo() {
  const q = new URLSearchParams(location.search).get("repo") || localStorage.getItem("kho_repo");
  if (q && q.includes("/")) { const [owner, repo] = q.split("/"); return { owner, repo }; }
  const m = location.hostname.match(/^([^.]+)\.github\.io$/i);
  if (m) {
    const seg = location.pathname.split("/").filter(Boolean)[0];
    return { owner: m[1], repo: seg || `${m[1]}.github.io` };
  }
  if (/^(localhost|127\.0\.0\.1)$/.test(location.hostname)) return { owner: "local", repo: "local", local: true }; // xem thử, chỉ đọc
  return null;
}
// Khách đọc file tĩnh cùng nguồn (Pages / local); còn lại đọc raw GitHub.
const CUNG_NGUON = () => location.hostname.endsWith("github.io") || (REPO && REPO.local);
const REPO = repoInfo();
if (new URLSearchParams(location.search).get("repo")) localStorage.setItem("kho_repo", new URLSearchParams(location.search).get("repo"));

const auth = {
  get token() { return localStorage.getItem("kho_token") || ""; },
  get ten() { return localStorage.getItem("kho_ten") || ""; },
  get on() { return !!this.token; },
  set(token, ten) { localStorage.setItem("kho_token", token); localStorage.setItem("kho_ten", ten); },
  out() { localStorage.removeItem("kho_token"); },
};

// ---------- GitHub API ----------
const b64dec = (b) => new TextDecoder().decode(Uint8Array.from(atob(b.replace(/\n/g, "")), (c) => c.charCodeAt(0)));
function b64enc(text) {
  const bytes = new TextEncoder().encode(text);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

async function gh(path, opt = {}) {
  const r = await fetch(`https://api.github.com/repos/${REPO.owner}/${REPO.repo}${path}`, {
    ...opt,
    headers: { Accept: "application/vnd.github+json", ...(auth.on ? { Authorization: `Bearer ${auth.token}` } : {}), ...(opt.headers || {}) },
    cache: "no-store",
  });
  if (r.status === 401) { auth.out(); renderUser(); throw new Error("Token sai hoặc đã hết hạn — đăng nhập lại"); }
  return r;
}

async function getFile(path) {
  const r = await gh(`/contents/${path}?ref=${BRANCH}`);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`Đọc ${path} lỗi ${r.status}`);
  const j = await r.json();
  return { text: b64dec(j.content || ""), sha: j.sha };
}

async function putFile(path, text, sha, message) {
  const r = await gh(`/contents/${path}`, {
    method: "PUT",
    body: JSON.stringify({ message, content: b64enc(text), branch: BRANCH, ...(sha ? { sha } : {}) }),
  });
  if (r.status === 409 || r.status === 422) return { conflict: true, status: r.status };
  if (r.status === 403 || r.status === 404) throw new Error("Token không có quyền ghi repo này");
  if (!r.ok) throw new Error(`Ghi ${path} lỗi ${r.status}`);
  return { ok: true };
}

// Đọc file: đăng nhập → API (mới nhất); khách → file tĩnh trên Pages.
async function readText(path) {
  if (auth.on) { const f = await getFile(path); return f ? f.text : null; }
  const base = CUNG_NGUON() ? "" : `https://raw.githubusercontent.com/${REPO.owner}/${REPO.repo}/${BRANCH}/`;
  const r = await fetch(`${base}${path}?t=${Date.now()}`, { cache: "no-store" });
  return r.ok ? r.text() : null;
}

// Sửa info.json an toàn khi nhiều người ghi cùng lúc (sha khác → đọc lại, thử lại).
async function updateInfo(id, mutate, message) {
  for (let lan = 0; lan < 3; lan++) {
    const f = await getFile(`data/${id}/info.json`);
    if (!f) throw new Error("Sản phẩm không còn trong kho");
    const info = JSON.parse(f.text);
    mutate(info);
    info.cap_nhat_luc = nowIso();
    const r = await putFile(`data/${id}/info.json`, JSON.stringify(info, null, 1) + "\n", f.sha, message);
    if (r.ok) return info;
  }
  throw new Error("Có người vừa sửa cùng lúc — thử lại");
}

// ---------- tiện ích ----------
function nowIso() {
  const d = new Date(Date.now() + 7 * 3600e3);
  return d.toISOString().slice(0, 19) + "+07:00";
}
function tachUid(link) {
  const s = (link || "").trim();
  if (/^\d{15,21}$/.test(s)) return s;
  const m = s.match(/(?:\/pdp\/(?:[^/?#]+\/)?|\/product\/|\/products\/|product_id=)(\d{15,21})/);
  return m ? m[1] : null;
}
function trangThai(i) {
  if (i.da_lam_video && i.da_lam_video.xong) return "da_lam_video";
  if (i.da_quay && i.da_quay.xong) return "da_quay";
  if (i.da_phan_tich) return "da_phan_tich";
  return "cho";
}
function anhBia(i) {
  if (!i.anh_bia) return "";
  return /^https?:/.test(i.anh_bia) ? i.anh_bia
    : (CUNG_NGUON() ? "" : `https://raw.githubusercontent.com/${REPO.owner}/${REPO.repo}/${BRANCH}/`) + `data/${i.id}/${i.anh_bia}`;
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
  const t = await readText("data/index.json");
  const ds = t ? (JSON.parse(t).san_pham || []) : [];
  if (auth.on) {
    // Bổ sung sản phẩm vừa thêm mà Action chưa kịp dựng index.
    try {
      const r = await gh(`/git/trees/${BRANCH}?recursive=1`);
      if (r.ok) {
        const ids = new Set(ds.map((x) => x.id));
        const moi = (await r.json()).tree
          .map((x) => x.path.match(/^data\/([^/]+)\/info\.json$/)).filter(Boolean).map((m) => m[1])
          .filter((id) => !ids.has(id));
        const them = await Promise.all(moi.map(async (id) => { const f = await getFile(`data/${id}/info.json`); return f && JSON.parse(f.text); }));
        for (const i of them.filter(Boolean)) ds.unshift({ ...i, trang_thai: trangThai(i) });
      }
    } catch (e) { console.warn(e); }
  }
  state.list = ds;
}

// ---------- giao diện ----------
function renderUser() {
  const u = $("#user");
  u.innerHTML = auth.on
    ? `<span class="small muted">👤 ${esc(auth.ten)}</span> <button class="btn ghost sm" id="btn-out">Thoát</button>`
    : `<button class="btn sm" id="btn-in">Đăng nhập</button>`;
  $("#btn-out", u)?.addEventListener("click", () => { auth.out(); renderUser(); route(); });
  $("#btn-in", u)?.addEventListener("click", openLogin);
}

function openLogin() {
  $("#in-ten").value = auth.ten;
  $("#login-err").textContent = "";
  $("#dlg-login").showModal();
}

function switchHtml(i, label = "Đã quay") {
  const on = i.da_quay && i.da_quay.xong;
  return `<label class="switch" data-quay="${esc(i.id)}" title="${on ? `Đã quay — ${esc(i.da_quay.boi)} ${gio(i.da_quay.luc)}` : "Gạt khi đã quay xong"}">
    <input type="checkbox" ${on ? "checked" : ""}><span class="tr"></span><span>${label}</span></label>`;
}

function renderList() {
  const dem = { tat_ca: state.list.length };
  for (const k of Object.keys(NHAN)) dem[k] = state.list.filter((x) => (x.trang_thai || trangThai(x)) === k).length;
  const q = state.tim.toLowerCase();
  const ds = state.list.filter((x) => (state.loc === "tat_ca" || (x.trang_thai || trangThai(x)) === state.loc)
    && (!q || [x.ten, x.uid, x.link, x.shop, x.them_boi].join(" ").toLowerCase().includes(q)));

  $("#app").innerHTML = `
    <form class="add" id="form-add">
      <input id="in-link" placeholder="Dán link sản phẩm TikTok Shop…" inputmode="url" autocomplete="off">
      <button class="btn">Lưu</button>
    </form>
    <div class="filters">
      ${[["tat_ca", "Tất cả"], ...Object.entries(NHAN)].map(([k, v]) => `<button class="chip ${state.loc === k ? "on" : ""}" data-loc="${k}">${v} (${dem[k]})</button>`).join("")}
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
      <div class="small muted">${x.da_quay && x.da_quay.xong ? `🎬 ${esc(x.da_quay.boi)} quay ${gio(x.da_quay.luc)}` : `Thêm bởi ${esc(x.them_boi || "?")} ${gio(x.them_luc)}`}</div>
    </a>
    ${switchHtml(x)}
  </div>`;
}

function bindSwitches() {
  document.querySelectorAll("[data-quay]").forEach((sw) => {
    const cb = $("input", sw);
    cb.addEventListener("change", async (e) => {
      const id = sw.dataset.quay, val = cb.checked;
      if (!needLogin()) { cb.checked = !val; return; }
      if (!val && !confirm("Gỡ đánh dấu 'đã quay' cho sản phẩm này?")) { cb.checked = true; return; }
      sw.classList.add("busy");
      try {
        const info = await updateInfo(id, (i) => { i.da_quay = { xong: val, boi: auth.ten, luc: nowIso() }; },
          `${val ? "Đã quay" : "Bỏ đã quay"} ${id} — ${auth.ten}`);
        const k = state.list.findIndex((x) => x.id === id);
        if (k >= 0) state.list[k] = { ...state.list[k], da_quay: info.da_quay, trang_thai: trangThai(info) };
        toast(val ? "✓ Đã đánh dấu quay xong" : "Đã gỡ đánh dấu");
        route();
      } catch (err) { cb.checked = !val; toast("⚠ " + err.message); }
      finally { sw.classList.remove("busy"); }
    });
  });
}

async function onAdd(e) {
  e.preventDefault();
  const link = $("#in-link").value.trim();
  if (!link) return;
  if (!/^https?:\/\//.test(link) && !/^\d{15,21}$/.test(link)) { toast("Link không hợp lệ"); return; }
  if (!needLogin()) return;
  const uid = tachUid(link);
  const trung = state.list.find((x) => (uid && x.uid === uid) || x.link === link);
  if (trung) { toast(`Đã có trong kho — ${NHAN[trung.trang_thai || trangThai(trung)]}`); location.hash = `#/sp/${encodeURIComponent(trung.id)}`; return; }
  const id = uid || "tam-" + nowIso().replace(/\D/g, "").slice(0, 14) + String(Date.now() % 1000).padStart(3, "0");
  const t = nowIso();
  const info = {
    id, uid, link, ten: "", gia: "", shop: "", anh_bia: "", tom_tat: "", usp: null, ghi_chu: "", thu_muc_may: "",
    them_boi: auth.ten, them_luc: t, da_phan_tich: false,
    da_quay: { xong: false, boi: "", luc: "" }, da_lam_video: { xong: false, so_video: 0, luc: "" }, cap_nhat_luc: t,
  };
  try {
    const r = await putFile(`data/${id}/info.json`, JSON.stringify(info, null, 1) + "\n", null, `Thêm ${id} — ${auth.ten}`);
    if (r.conflict) { toast("Sản phẩm này đã có trong kho"); await loadList(); location.hash = `#/sp/${encodeURIComponent(id)}`; route(); return; }
    state.list.unshift({ ...info, trang_thai: "cho" });
    toast(uid ? "✓ Đã lưu — chờ máy nhà phân tích" : "✓ Đã lưu link rút gọn — máy nhà sẽ tìm UID");
    renderList();
  } catch (err) { toast("⚠ " + err.message); }
}

// ---------- trang chi tiết ----------
async function renderDetail(id) {
  $("#app").innerHTML = `<p class="muted center">Đang tải…</p>`;
  const [infoT, md, caps] = await Promise.all([
    readText(`data/${id}/info.json`), readText(`data/${id}/bo-canh-quay.md`), readText(`data/${id}/captions.txt`),
  ]);
  if (!infoT) { $("#app").innerHTML = `<p class="center">Không tìm thấy sản phẩm. <a href="#/">← Về kho</a></p>`; return; }
  const i = JSON.parse(infoT);
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
      <div class="quaybox">
        <div class="small">${i.da_quay && i.da_quay.xong ? `🎬 <b>${esc(i.da_quay.boi)}</b> đã quay lúc ${gio(i.da_quay.luc)}` : "Chưa quay — gạt khi quay xong để lần sau không làm trùng"}</div>
        ${switchHtml(i, "Đã quay xong")}
      </div>
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
      try { await updateInfo(i.id, (x) => { x.ghi_chu = v; }, `Ghi chú ${i.id} — ${auth.ten}`); i.ghi_chu = v; toast("✓ Đã lưu ghi chú"); }
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
  if (!REPO) {
    $("#app").innerHTML = `<p>Mở trang qua GitHub Pages (<code>&lt;tài-khoản&gt;.github.io/&lt;repo&gt;</code>) hoặc thêm <code>?repo=tài-khoản/repo</code> vào địa chỉ.</p>`;
    return;
  }
  const m = location.hash.match(/^#\/sp\/(.+)$/);
  try {
    if (m) await renderDetail(decodeURIComponent(m[1]));
    else { if (!state.list.length || route.reload) await loadList(); route.reload = false; renderList(); }
  } catch (err) {
    $("#app").innerHTML = `<p class="err">⚠ ${esc(err.message)}</p>`;
  }
}

window.addEventListener("hashchange", () => { if (!location.hash.startsWith("#/sp/")) route.reload = false; route(); });
window.addEventListener("DOMContentLoaded", () => {
  $("#btn-login-huy").addEventListener("click", () => $("#dlg-login").close());
  $("#form-login").addEventListener("submit", async (e) => {
    e.preventDefault();
    const token = $("#in-token").value.trim(), ten = $("#in-ten").value.trim();
    $("#login-err").textContent = "Đang kiểm tra…";
    try {
      const r = await fetch(`https://api.github.com/repos/${REPO.owner}/${REPO.repo}`, { headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" } });
      if (!r.ok) throw new Error("Token sai hoặc không có quyền với kho này");
      const j = await r.json();
      if (!j.permissions || !j.permissions.push) throw new Error("Token chỉ có quyền đọc — cần quyền ghi (Contents: Read and write)");
      auth.set(token, ten);
      $("#dlg-login").close();
      renderUser(); route.reload = true; route();
      toast(`Xin chào ${ten}`);
    } catch (err) { $("#login-err").textContent = err.message; }
  });
  renderUser();
  route();
});
