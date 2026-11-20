// Poster V2 › Accounts (#/poster/accounts) — port 1:1 E:/tool/tiktok_poster_v2/src/desktop/pages/accounts.py
// (AccountsPage + _AccountCard + _AccountEditDialog), đối chiếu bản Svelte a55d687 Accounts.svelte. Thiết kế: docs/poster-v2-tren-web.md
// §3.3 (login chạy nền DN, khoá nút theo dangChay), §5.3 (Browse cookie đọc file trên máy đang mở web → ô JSON → cookies_from_json;
// dòng nhắc dưới nút login), §6.3–§6.5. Tiền tố pvac / .pvac-. Chỉ gọi pvApi/pvCho; hộp qua pvHop/pvXacNhan/pvThongBao; mọi chuỗi qua esc.
// Không bao giờ tự gửi lại lệnh login; không in cookie / proxy ra console.
"use strict";

// --- pvac-thuan start ---
const PVAC_LOGIN = "🔓 Tạo profile & Login lấy cookies (tự động)";
const PVAC_LOGIN_DANG = "Đang mở Chrome... Hãy đăng nhập TikTok trên trình duyệt";
const PVAC_NHAC = "Cần người ngồi ở máy nhà để đăng nhập trên Chrome vừa mở";
const PVAC_TEP_TOI_DA = 256 * 1024; // = giới hạn body của Worker/video_server (§2.1)
const PVAC_CO_THE = "Thao tác CÓ THỂ đã chạy: xem Logs/Queue trước khi bấm lại.";
// Câu từ chối B1 / B3 của video_server (tools/poster_web.py LOI_B1, LOI_B3; kiem_body → 400 {loi}): chốt chỉ web có, desktop không có.
const PVAC_LOI_CHAN = ["Tên account không hợp lệ",
  "Đường dẫn phải là thư mục/tệp trên ổ đĩa máy nhà (vd E:\\…), không nhận đường mạng"];

// Lỗi lưu account là 400 {loi: B1|B3} (pvChuLoi → "400: <loi>") → câu đó; lỗi khác → null (giữ lỗi gốc: chỉ ghi log).
function pvacLoiChan(e) {
  if (!e || e.status !== 400 || typeof e.message !== "string" || !e.message.startsWith("400: ")) return null;
  const cau = e.message.slice(5);
  return PVAC_LOI_CHAN.includes(cau) ? cau : null;
}

// dict.get(k, macDinh) của Python: chỉ dùng mặc định khi THIẾU khoá (khoá có mà null vẫn là null).
function pvacLay(o, k, macDinh) {
  return o && typeof o === "object" && Object.prototype.hasOwnProperty.call(o, k) ? o[k] : macDinh;
}

// bool() của Python: None/False/0/""/[]/{} → false.
function pvacThat(x) {
  if (Array.isArray(x)) return x.length > 0;
  if (x && typeof x === "object") return Object.keys(x).length > 0;
  return !!x;
}

// int() của Python cho số / chuỗi số nguyên / bool; kiểu khác hoặc chuỗi lạ → ném (như ValueError/TypeError).
function pvacSoNguyen(x) {
  if (typeof x === "boolean") return x ? 1 : 0;
  if (typeof x === "number" && Number.isFinite(x)) return Math.trunc(x);
  if (typeof x === "string" && /^\s*[+-]?\d+\s*$/.test(x)) return parseInt(x, 10);
  throw new Error("int() không hợp lệ");
}

// _fingerprint_summary = summarize(parse_fingerprint(raw)) (src/browser/fingerprint.py:158-199); lỗi bất kỳ → "lỗi dữ liệu vân tay".
function pvacVanTay(raw) {
  try {
    if (raw === null || raw === undefined || raw === "") return "máy thật";
    const fp = typeof raw === "string" ? JSON.parse(raw) : raw;
    const khoa = (o, k) => {
      if (!o || typeof o !== "object" || Array.isArray(o) || !Object.prototype.hasOwnProperty.call(o, k)) throw new Error(`thiếu ${k}`);
      return o[k];
    };
    const width = pvacSoNguyen(khoa(khoa(fp, "screen"), "width"));
    const height = pvacSoNguyen(khoa(khoa(fp, "screen"), "height"));
    pvacSoNguyen(khoa(fp, "seed"));
    const hc = pvacSoNguyen(khoa(fp, "hardware_concurrency"));
    const dm = pvacSoNguyen(khoa(fp, "device_memory"));
    khoa(khoa(fp, "webgl"), "vendor");
    const r = khoa(khoa(fp, "webgl"), "renderer");
    const renderer = r === null ? "None" : r === true ? "True" : r === false ? "False" : typeof r === "object" ? JSON.stringify(r) : String(r);
    if (width <= 0 || height <= 40 || hc <= 0 || dm <= 0) throw new Error("ngoài phạm vi"); // _TASKBAR_PX = 40
    return `${width}x${height}, ${hc} luồng, ${renderer}`;
  } catch (e) {
    return "lỗi dữ liệu vân tay";
  }
}

// _health_color (accounts.py:33-40).
function pvacMauSucKhoe(score) {
  const s = Number(score);
  if (s >= 80) return "#22c55e";
  if (s >= 60) return "#eab308";
  if (s >= 40) return "#f97316";
  return "#ef4444";
}

// Path(ck_path).name trên Windows: đoạn cuối sau / hoặc \ ("C:" đứng riêng không phải tên).
function pvacTenTep(p) {
  const d = String(p ?? "").split(/[\\/]+/).filter(Boolean);
  if (!d.length) return "";
  const cuoi = d[d.length - 1];
  return d.length === 1 && /^[A-Za-z]:$/.test(cuoi) ? "" : cuoi;
}

// Cooldown: backend trả "in_cooldown" (views.py), giữ cả "cooldown_active" như accounts.py:350.
function pvacDangCooldown(h) {
  return pvacThat(pvacLay(h, "in_cooldown", pvacLay(h, "cooldown_active", false)));
}

// _AccountCard (accounts.py:256-384). Màu chỉ lấy từ bảng cố định, dữ liệu API đều qua esc.
function pvacTheHtml(acc, h) {
  const id = esc(String(pvacLay(acc, "id", "")));
  const ck = pvacLay(acc, "cookies_path", "") || "";
  const score = pvacLay(h, "health_score", 100);
  const succ = Number(pvacLay(h, "success_rate", 100));
  const proxy = pvacLay(acc, "proxy", null);
  const nhan = (mau, chu) => `<span class="pvac-nhan" style="background-color:#2e3440;color:${mau};padding:2px 6px;border-radius:4px;font-size:11px">${chu}</span>`;
  const cd = pvacDangCooldown(h);
  return `<div class="pv-the pvac-the" data-pvac-the="${id}" style="display:flex;flex-wrap:wrap;align-items:center;gap:12px;padding:8px 12px">
  <div class="pvac-thong-tin" style="flex:1;min-width:0;display:flex;flex-direction:column;gap:4px">
    <div class="pvac-dong-ten" style="display:flex;flex-wrap:wrap;align-items:center;gap:8px">
      <b class="pvac-ten" style="font-size:15px;overflow-wrap:anywhere">${pvacThat(pvacLay(acc, "active", true)) ? "🟢" : "🔴"} ${esc(pvacLay(acc, "name", ""))}</b>
      <span class="pv-nho pvac-cookie" style="overflow-wrap:anywhere">🍪 ${esc(ck ? pvacTenTep(ck) : "chưa có cookies")}</span>
    </div>
    <div class="pvac-huy-hieu" style="display:flex;flex-wrap:wrap;gap:8px">
      <span class="pvac-suc-khoe" style="background-color:${pvacMauSucKhoe(score)};color:white;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold">🛡️ Health: ${esc(score)}/100</span>
      ${nhan("#eceff4", `📅 ${esc(pvacLay(h, "posts_today", 0))} bài/ngày`)}
      ${nhan("#a3be8c", `✅ ${esc(succ.toFixed(0))}% thành công`)}
      ${proxy ? nhan("#88c0d0", `🌐 ${esc(Array.from(String(proxy)).slice(0, 20).join(""))}...`) : ""}
    </div>
  </div>
  <div class="pvac-nut" style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
    <button type="button" class="btn sm" style="background-color:#ebcb8b;color:#2e3440;font-weight:bold" data-pvac-nut="cd" data-pvac-id="${id}">${cd ? "🛡️ Bỏ Cooldown" : "🛡️ Cooldown"}</button>
    <button type="button" class="btn ghost sm" data-pvac-nut="check" data-pvac-id="${id}">Check</button>
    <button type="button" class="btn ghost sm" data-pvac-nut="sua" data-pvac-id="${id}">✏️ Edit</button>
    <button type="button" class="btn sm" style="background:#d33a3a;min-width:36px" data-pvac-nut="xoa" data-pvac-id="${id}" aria-label="Xóa">🗑️</button>
  </div>
</div>`;
}

// Danh sách thẻ hoặc EmptyStateLabel (accounts.py:463-466).
function pvacDsHtml(accounts, health) {
  if (!accounts.length) {
    return `<div class="center pvac-rong" style="padding:40px"><div style="font-size:48px" aria-hidden="true">📭</div><div>${esc("Chưa có account nào. Bấm '+ Add Account' để thêm.")}</div></div>`;
  }
  return `<div class="pvac-ds" style="display:flex;flex-direction:column;gap:8px">${accounts.map((a) =>
    pvacTheHtml(a, pvacLay(health, String(pvacLay(a, "id", "")), {}) || {})).join("")}</div>`;
}

// Vùng nút login (accounts.py:133-147) + dòng nhắc §5.3 / Q3 ngay dưới nút. dang = có lệnh login đang chạy hoặc đang hỏi dangChay.
function pvacLoginHtml(dang, dangChay) {
  return `<button type="button" class="btn pvac-login" style="width:100%;margin-top:12px;background-color:#22c55e;color:white;font-weight:bold;font-size:13px;padding:10px"
    data-pvac-nut="login"${dang ? " disabled" : ""}>${esc(dangChay ? PVAC_LOGIN_DANG : PVAC_LOGIN)}</button>
  <p class="pv-nho pvac-nhac" style="margin:4px 0 0">${esc(PVAC_NHAC)}</p>`;
}

// Nút hộp (QDialogButtonBox Save "Lưu Account" + Cancel "Hủy"); ban = đang gọi cookies_from_json (accounts.py:226).
function pvacNutHopHtml(ban) {
  const d = ban ? " disabled" : "";
  return `<button type="button" class="btn" data-pvac-nut="luu"${d}>Lưu Account</button><button type="button" class="btn ghost" data-pvac-nut="huy"${d}>Hủy</button>`;
}

// Thân hộp _AccountEditDialog (accounts.py:59-159). f = trạng thái ô; coVanTay = account cũ có vân tay.
function pvacHopHtml(f, coVanTay, vanTayChu, loginKhoa, loginDang) {
  const o = (ma, nhan, gt, ph, them = "") => `<label for="pvac-o-${ma}">${esc(nhan)}</label>
    <input id="pvac-o-${ma}" type="text" data-pvac-o="${ma}" value="${esc(gt)}" placeholder="${esc(ph)}" autocomplete="off"${them}>`;
  return `<div class="pv-form pvac-form">
    ${o("name", "Tên Account:", f.name, "Tên account (vd: acc_tiktok_01)", ` maxlength="100"`)}
    <label for="pvac-o-cookies_path">File Cookies (.json):</label>
    <div style="display:flex;gap:8px;min-width:0">
      <input id="pvac-o-cookies_path" type="text" data-pvac-o="cookies_path" value="${esc(f.cookies_path)}" placeholder="Đường dẫn file cookies .json" autocomplete="off" style="flex:1;min-width:0">
      <button type="button" class="btn ghost sm" data-pvac-nut="browse">Browse...</button>
      <input type="file" data-pvac-o="tep" accept=".json,application/json" hidden>
    </div>
    <label for="pvac-o-raw">Paste JSON Cookie:</label>
    <textarea id="pvac-o-raw" data-pvac-o="raw" rows="3" placeholder="${esc("HOẶC Dán trực tiếp nội dung cookies JSON vào đây (từ tiện ích mở rộng Cookie-Editor)...")}">${esc(f.raw)}</textarea>
    ${o("profile", "Chrome Profile Dir:", f.profile, "Thư mục profile riêng (tùy chọn)")}
    ${o("proxy", "Proxy (HTTP/SOCKS5):", f.proxy, "http://user:pass@ip:port")}
    ${o("tags", "Campaign Hashtags:", f.tags, "#campaign #affiliate #shop")}
    <span></span><label><input type="checkbox" data-pvac-o="active"${f.active ? " checked" : ""}> Account đang hoạt động (Active)</label>
    <span></span><label title="${esc("Tạo 1 lần rồi giữ nguyên: màn hình, CPU, GPU, nhiễu canvas/audio.\nBỏ trống cho account chính (dùng thông số máy thật).")}"><input type="checkbox" data-pvac-o="fp"${f.fp ? " checked" : ""}> Dùng vân tay trình duyệt riêng (account phụ, cố định)</label>
    ${coVanTay ? `<span></span><span class="pv-nho pvac-van-tay">${esc(`Vân tay hiện tại: ${vanTayChu}`)}</span>` : ""}
  </div>
  <div data-pvac-vung="login">${pvacLoginHtml(loginKhoa, loginDang)}</div>
  <div class="pv-hop-nut" data-pvac-vung="nut">${pvacNutHopHtml(false)}</div>`;
}

// get_data (accounts.py:244-253).
function pvacDuLieu(f) {
  return {
    name: String(f.name).trim(),
    cookies_path: String(f.cookies_path).trim(),
    chrome_profile_dir: String(f.profile).trim(),
    proxy: String(f.proxy).trim(),
    campaign_hashtags: String(f.tags).trim(),
    active: !!f.active,
    use_fingerprint: !!f.fp,
  };
}

// Lệnh login đang chạy trong GET /_kq (§3.3) → { cho, toiDa, ten } | null.
function pvacLenhLogin(dc) {
  const ds = dc && Array.isArray(dc.dang_chay) ? dc.dang_chay : [];
  const l = ds.find((x) => x && x.method === "POST" && typeof x.path === "string"
    && x.path.split("?")[0] === "/api/v2/accounts/login_and_capture" && typeof x.cho === "string");
  if (!l) return null;
  const ten = l.tom_tat && typeof l.tom_tat.name === "string" ? l.tom_tat.name : "";
  return { cho: l.cho, toiDa: l.toi_da_giay, ten };
}
// --- pvac-thuan end ---

// Trang Accounts. Trạng thái nằm trong closure tt gắn phiên; sau MỖI await kiểm pvConSong trước khi vẽ / hiện hộp.
async function pvAcVe(khung, phien) {
  const tt = { phien, khung, accounts: [], health: {}, lanTai: 0, login: { kiem: true }, hop: null, soHop: 0 };
  khung.innerHTML = `<div class="pvac">
  <div class="pv-cong-cu"><h2 style="margin:0;font-size:20px">TikTok Accounts</h2><span class="pv-gian"></span>
    <button type="button" class="btn ghost" data-pvac-nut="don">🧹 Dọn cache profile</button>
    <button type="button" class="btn ghost" data-pvac-nut="lammoi">↻ Refresh</button>
    <button type="button" class="btn" data-pvac-nut="them">+ Add Account</button>
  </div>
  <div data-pvac-vung="ds"></div>
</div>`;
  khung.addEventListener("click", (ev) => {
    const b = ev.target && typeof ev.target.closest === "function" ? ev.target.closest("[data-pvac-nut]") : null;
    if (b) pvacBamTrang(tt, b.dataset.pvacNut, b.dataset.pvacId);
  });
  // §3.3: hỏi lệnh login đang chạy (song song với tải danh sách); trong lúc hỏi nút login khoá.
  const kiemLogin = async () => {
    let lenh = null;
    try { lenh = pvacLenhLogin(await pvApi.dangChay()); }
    catch (e) { /* không hỏi được: video_server vẫn chặn trùng ở máy nhà (§3.3) */ }
    if (!pvConSong(phien)) return;
    tt.login = null;
    if (lenh) pvacGanLogin(tt, lenh);
    else pvacVeLogin(tt);
  };
  await Promise.all([kiemLogin(), pvacTai(tt)]);
}

// refresh_async (accounts.py:439-455): list_accounts rồi health từng account; lỗi health → giá trị mặc định; lỗi chung chỉ ghi log.
async function pvacTai(tt) {
  const lan = ++tt.lanTai;
  try {
    const ds = await pvApi.listAccounts();
    if (!pvConSong(tt.phien)) return;
    const accs = Array.isArray(ds) ? ds.filter((a) => a && typeof a === "object") : [];
    const hMap = {};
    for (const a of accs) {
      try { hMap[String(a.id)] = await pvApi.viewsAccountHealth(a.id); }
      catch (e) { hMap[String(a.id)] = { health_score: 100, posts_today: 0, success_rate: 100 }; }
      if (!pvConSong(tt.phien)) return;
    }
    if (lan !== tt.lanTai) return; // lần Refresh mới hơn sẽ vẽ
    tt.accounts = accs;
    tt.health = hMap;
    const v = tt.khung.querySelector('[data-pvac-vung="ds"]');
    if (v) v.innerHTML = pvacDsHtml(accs, hMap);
  } catch (e) {
    if (!pvConSong(tt.phien) || (e && e.roiTrang)) return;
    console.error(`Error loading accounts: ${e && e.message ? e.message : e}`);
  }
}

function pvacBamTrang(tt, nut, idChu) {
  if (nut === "lammoi") { pvacTai(tt); return; }
  if (nut === "them") { pvacMoHop(tt, null); return; }
  if (nut === "don") { pvacDonCache(tt); return; }
  const acc = tt.accounts.find((a) => String(a.id) === String(idChu));
  if (!acc) return;
  if (nut === "cd") pvacCooldown(tt, acc.id, pvacDangCooldown(pvacLay(tt.health, String(acc.id), {}) || {}));
  else if (nut === "check") pvacKiemCookie(tt, acc.id);
  else if (nut === "sua") pvacMoHop(tt, acc);
  else if (nut === "xoa") pvacXoa(tt, acc.id, String(pvacLay(acc, "name", "") ?? ""));
}

// _toggle_cooldown (accounts.py:504-508): không có on_error ở desktop → chỉ ghi log.
async function pvacCooldown(tt, id, dangCd) {
  try {
    if (dangCd) await pvApi.accountClearCooldown(id);
    else await pvApi.accountCooldown(id);
  } catch (e) {
    if (pvConSong(tt.phien) && !(e && e.roiTrang)) console.error(`Cooldown lỗi: ${e && e.message ? e.message : e}`);
    return;
  }
  if (pvConSong(tt.phien)) pvacTai(tt);
}

// _check_cookies (accounts.py:510-521).
async function pvacKiemCookie(tt, id) {
  let res;
  try { res = await pvApi.testCookies(id); }
  catch (e) {
    if (!pvConSong(tt.phien) || (e && e.roiTrang)) return;
    pvThongBao("Lỗi", e && e.message ? e.message : String(e), "critical");
    return;
  }
  if (!pvConSong(tt.phien)) return;
  const msg = pvacLay(res, "message", "");
  if (pvacLay(res, "status", undefined) === "ok") await pvThongBao("Kiểm tra cookies", `✅ Cookies hợp lệ!\n${msg ?? ""}`, "info");
  else await pvThongBao("Kiểm tra cookies", `⚠️ Cookies cảnh báo: ${msg ?? ""}`, "warning");
  if (pvConSong(tt.phien)) pvacTai(tt);
}

// _clean_profile_cache (accounts.py:523-532): không có on_error ở desktop → chỉ ghi log.
async function pvacDonCache(tt) {
  let res;
  try { res = await pvApi.cleanAllProfiles(); }
  catch (e) {
    if (pvConSong(tt.phien) && !(e && e.roiTrang)) console.error(`Dọn cache lỗi: ${e && e.message ? e.message : e}`);
    return;
  }
  if (!pvConSong(tt.phien)) return;
  pvThongBao("Dọn dẹp", `Đã dọn dẹp ${pvacLay(res, "cleaned_caches", 0)} thư mục cache rác, giải phóng ${pvacLay(res, "freed_mb", 0)} MB.`, "info");
}

// _delete_account (accounts.py:534-536) qua confirm_destructive.
async function pvacXoa(tt, id, ten) {
  const co = await pvXacNhan(`Xóa tài khoản '${ten}'?`);
  if (!co || !pvConSong(tt.phien)) return;
  try { await pvApi.deleteAccount(id); }
  catch (e) {
    if (pvConSong(tt.phien) && !(e && e.roiTrang)) console.error(`Xóa account lỗi: ${e && e.message ? e.message : e}`);
    return;
  }
  if (pvConSong(tt.phien)) pvacTai(tt);
}

// QMessageBox.question (Yes / No) → Promise<boolean>.
function pvacHoi(tieuDe, cau) {
  const h = pvHop({ tieuDe, html: `<p class="pv-cau"><span class="pv-ic" aria-hidden="true">❓</span> ${esc(cau)}</p>`,
    nut: [{ ma: "yes", chu: "Yes", chinh: true }, { ma: "no", chu: "No" }] });
  return h.cho.then((v) => v === "yes");
}

// Mở _AccountEditDialog; account = null → Thêm. fSan = dữ liệu ô đã nhập (mở lại hộp sau lỗi B1/B3) thay cho giá trị của account.
function pvacMoHop(tt, account, fSan = null) {
  if (tt.hop) return;
  const a = account || {};
  const coVanTay = pvacThat(pvacLay(a, "fingerprint", null));
  const f = fSan ? { ...fSan } : {
    name: String(pvacLay(a, "name", "") ?? ""),
    cookies_path: String(pvacLay(a, "cookies_path", "") || ""),
    raw: "",
    profile: String(pvacLay(a, "chrome_profile_dir", "") || ""),
    proxy: String(pvacLay(a, "proxy", "") || ""),
    tags: String(pvacLay(a, "campaign_hashtags", "") || ""),
    active: pvacThat(pvacLay(a, "active", true)),
    fp: coVanTay,
  };
  const p = pvHop({ tieuDe: account ? "Sửa Account" : "Thêm Account",
    html: pvacHopHtml(f, coVanTay, coVanTay ? pvacVanTay(a.fingerprint) : "", !!tt.login, !!(tt.login && tt.login.dang)), nut: [] });
  const h = { ma: ++tt.soHop, el: p.el, dong: p.dong, f, account, coVanTay, ban: false };
  tt.hop = h;
  p.cho.then(() => { if (tt.hop === h) tt.hop = null; });
  const o = (ma) => h.el.querySelector(`[data-pvac-o="${ma}"]`);
  h.dat = (ma, gt) => { const x = o(ma); if (x) x.value = gt; };
  h.el.addEventListener("click", (ev) => {
    const b = ev.target && typeof ev.target.closest === "function" ? ev.target.closest("[data-pvac-nut]") : null;
    if (!b) return;
    const nut = b.dataset.pvacNut;
    if (nut === "browse") { const t = o("tep"); if (t && typeof t.click === "function") t.click(); }
    else if (nut === "login") pvacBatLogin(tt, h);
    else if (nut === "luu") pvacLuu(tt, h);
    else if (nut === "huy") { if (!h.ban) { if (tt.hop === h) tt.hop = null; h.dong(); } }
  });
  const nhap = (ev) => {
    const t = ev.target;
    const ma = t && t.dataset ? t.dataset.pvacO : undefined;
    if (ma === "tep") { if (ev.type === "change") pvacDocTep(tt, h, t); return; }
    if (ma === "active" || ma === "fp") f[ma] = !!t.checked;
    else if (ma && Object.prototype.hasOwnProperty.call(f, ma)) f[ma] = String(t.value ?? "");
  };
  h.el.addEventListener("input", nhap);
  h.el.addEventListener("change", nhap);
}

// "Browse..." (§5.3): đọc file JSON trên máy đang mở web, đổ nội dung vào ô "Paste JSON Cookie" (Save → cookies_from_json).
function pvacDocTep(tt, h, input) {
  const tep = input && input.files && input.files[0];
  if (!tep) return;
  try { input.value = ""; } catch (e) { /* trình duyệt cũ không cho xoá */ }
  if (Number(tep.size) > PVAC_TEP_TOI_DA) {
    pvThongBao("Lỗi", "File cookies quá lớn (tối đa 256 KB).", "warning");
    return;
  }
  const r = new FileReader();
  r.addEventListener("load", () => {
    if (!pvConSong(tt.phien) || tt.hop !== h) return;
    h.f.raw = typeof r.result === "string" ? r.result : "";
    h.dat("raw", h.f.raw);
  });
  r.addEventListener("error", () => {
    if (!pvConSong(tt.phien) || tt.hop !== h) return;
    pvThongBao("Lỗi", "Không đọc được file cookies.", "critical");
  });
  r.readAsText(tep);
}

function pvacVeLogin(tt) {
  const h = tt.hop;
  if (!h) return;
  const v = h.el.querySelector('[data-pvac-vung="login"]');
  if (v) v.innerHTML = pvacLoginHtml(!!tt.login, !!(tt.login && tt.login.dang));
}

function pvacVeNutHop(h) {
  const v = h.el.querySelector('[data-pvac-vung="nut"]');
  if (v) v.innerHTML = pvacNutHopHtml(h.ban);
}

// _do_auto_login (accounts.py:166-198). Lớp DN: pvGoi nhận 202 rồi pvCho tối đa 360 + 60 s. Khoá TRƯỚC await (chống mở 2 Chrome).
async function pvacBatLogin(tt, h) {
  if (tt.login) return;
  const name = String(h.f.name).trim();
  const proxy = String(h.f.proxy).trim();
  const useFp = !!h.f.fp;
  if (!name) { pvThongBao("Lỗi", "Vui lòng nhập Tên Account trước khi tạo profile và login.", "warning"); return; }
  tt.login = { dang: true, ten: name, hopMa: h.ma, daGan: false };
  pvacVeLogin(tt);
  const lenh = tt.login;
  let res;
  try { res = await pvApi.loginAndCapture(name, proxy, useFp); }
  catch (e) { await pvacLoginLoi(tt, lenh, e); return; }
  pvacLoginXong(tt, lenh, res);
}

// Mở trang khi máy nhà còn lệnh login (§3.3): khoá nút, hỏi tiếp; xong hiện kết quả như khi bấm.
function pvacGanLogin(tt, l, daGan = true) {
  const lenh = { dang: true, ten: l.ten, hopMa: null, daGan };
  tt.login = lenh;
  pvacVeLogin(tt);
  pvCho(l.cho, l.toiDa, tt.phien).then((res) => pvacLoginXong(tt, lenh, res), (e) => pvacLoginLoi(tt, lenh, e));
}

// Hộp đang mở có phải hộp của lệnh này: bấm từ hộp nào thì đúng hộp đó; lệnh gắn lại thì hộp cùng tên account.
function pvacHopCuaLenh(tt, lenh) {
  const h = tt.hop;
  if (!h) return null;
  if (lenh.hopMa !== null) return h.ma === lenh.hopMa ? h : null;
  return lenh.ten && String(h.f.name).trim() === lenh.ten ? h : null;
}

function pvacLoginXong(tt, lenh, res) {
  if (!pvConSong(tt.phien) || tt.login !== lenh) return;
  tt.login = null;
  pvacVeLogin(tt);
  if (pvacLay(res, "status", undefined) === "ok") {
    const h = pvacHopCuaLenh(tt, lenh);
    if (h) {
      h.f.cookies_path = String(pvacLay(res, "cookies_path", "") ?? "");
      h.f.profile = String(pvacLay(res, "chrome_profile_dir", "") ?? "");
      h.dat("cookies_path", h.f.cookies_path);
      h.dat("profile", h.f.profile);
    }
    pvThongBao("Thành công", `Đã đăng nhập thành công!\nĐã trích xuất ${pvacLay(res, "cookies_count", 0)} cookies.`, "info");
  } else {
    pvThongBao("Thông báo", typeof res === "string" ? res : JSON.stringify(res), "warning");
  }
}

// Lỗi login. Lỗi tạm (mạng / 5xx cổng) có thể là lệnh vẫn chạy ở máy nhà → hỏi dangChay 1 lần: còn chạy thì gắn lại, KHÔNG gửi lại.
async function pvacLoginLoi(tt, lenh, e) {
  if (!pvConSong(tt.phien) || (e && e.roiTrang) || tt.login !== lenh) return;
  const tam = !!(e && e.tam) && e.status !== 429;
  if (tam && !lenh.daGan) {
    lenh.daGan = true;
    let l = null;
    try { l = pvacLenhLogin(await pvApi.dangChay()); } catch (e2) { /* không hỏi được: báo lỗi bên dưới */ }
    if (!pvConSong(tt.phien) || tt.login !== lenh) return;
    if (l) { pvacGanLogin(tt, { ...l, ten: l.ten || lenh.ten }, true); return; }
  }
  tt.login = null;
  pvacVeLogin(tt);
  let msg = e && e.message ? e.message : String(e);
  if (tam && !/CÓ THỂ/.test(msg)) msg += `\n${PVAC_CO_THE}`;
  pvThongBao("Lỗi đăng nhập", `Không thể lấy cookies: ${msg}`, "critical");
}

// _validate_and_accept (accounts.py:200-242) rồi create/update (accounts.py:483-502).
async function pvacLuu(tt, h) {
  if (h.ban) return;
  h.ban = true; // chặn bấm Lưu 2 lần trong lúc hỏi / gọi API (đặt TRƯỚC await)
  try {
    const raw = String(h.f.raw).trim();
    const name = String(h.f.name).trim();
    if (!name) { await pvThongBao("Lỗi", "Tên account không được để trống.", "warning"); return; }
    if (h.coVanTay && !h.f.fp) {
      const co = await pvacHoi("Bỏ vân tay riêng?",
        "Account này sẽ chuyển sang thông số máy thật - với TikTok là đổi sang thiết bị khác.\n"
        + "Bật lại sau sẽ ra bộ vân tay MỚI, không lấy lại được bộ cũ.\n\nTiếp tục?");
      if (!co || !pvConSong(tt.phien) || tt.hop !== h) return;
    }
    if (raw) {
      let parsed;
      try { parsed = JSON.parse(raw); }
      catch (e) {
        await pvThongBao("Lỗi cú pháp JSON", `Nội dung cookies JSON không hợp lệ: ${e && e.message ? e.message : e}`, "critical");
        return;
      }
      if (Array.isArray(parsed)) {
        pvacVeNutHop(h);
        let res;
        try { res = await pvApi.cookiesFromJson(name, parsed); }
        catch (e) {
          if (!pvConSong(tt.phien) || (e && e.roiTrang) || tt.hop !== h) return;
          h.ban = false;
          pvacVeNutHop(h);
          pvThongBao("Lỗi", `Không thể lưu cookies: ${e && e.message ? e.message : e}`, "critical");
          return;
        }
        if (!pvConSong(tt.phien) || tt.hop !== h) return; // hộp đã đóng trong lúc chờ: desktop exec() đã trả Rejected
        const cp = pvacLay(res, "cookies_path", "");
        if (cp) { h.f.cookies_path = String(cp); h.dat("cookies_path", h.f.cookies_path); }
      }
    }
    pvacChapNhan(tt, h);
  } finally {
    if (tt.hop === h && h.ban) { h.ban = false; pvacVeNutHop(h); }
  }
}

// accept() → get_data → create_account / update_account → refresh. Desktop không có on_error → chỉ ghi log.
// Riêng chốt B1/B3 của web (400 {loi}): mở lại hộp với dữ liệu đã nhập (nếu chưa có hộp khác) + báo câu từ chối; KHÔNG tự gửi lại.
async function pvacChapNhan(tt, h) {
  const data = pvacDuLieu(h.f);
  tt.hop = null;
  h.ban = false;
  h.dong();
  try {
    if (h.account) await pvApi.updateAccount(h.account.id, data);
    else await pvApi.createAccount(data);
  } catch (e) {
    if (!pvConSong(tt.phien) || (e && e.roiTrang)) return;
    const chan = pvacLoiChan(e);
    if (!chan) { console.error(`Lưu account lỗi: ${e && e.message ? e.message : e}`); return; }
    if (!tt.hop) pvacMoHop(tt, h.account, h.f); // người dùng đã mở hộp khác trong lúc chờ → không mở chồng
    pvThongBao("Không thể lưu account", chan, "warning");
    return;
  }
  if (pvConSong(tt.phien)) pvacTai(tt);
}
