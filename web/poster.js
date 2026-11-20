// Poster V2 trên web Kho (mục menu thứ 7, #/poster/<trang>) — docs/poster-v2-tren-web.md §6.4 (khung + client API, phiếu W-P1).
// 9 trang con nằm ở web/pv-*.js (pvdb pvac pvfo pvca pvvi pvqu pvpo pvlo pvse), mỗi trang khai báo pv<xx>Ve(khung, phien) và
// tuỳ chọn pv<xx>Dung(); khung tra qua globalThis nên thiếu file trang vẫn chạy (hiện mnCHUA_CO).
// Script thường, chung phạm vi toàn cục với app.js/khung.js: tên cấp đỉnh CỐ ĐỊNH theo §6.4, bắt đầu bằng "pv" và KHÔNG bắt đầu bằng
// 9 tiền tố con (luật tránh va §6.3, test cf/test/poster-web.test.mjs). Biến nội bộ đặt trong closure hoặc làm thuộc tính hàm.
// Dùng của app.js (lúc chạy): esc, $, auth, renderUser, openLogin; của khung.js: mnCHUA_CO. CSP script-src 'self': chỉ addEventListener.
// Đường đi: trình duyệt → Worker /api/poster/<rest> → video_server /p/<rest> → backend Poster :8023 (token không tới trình duyệt).
"use strict";

// Thứ tự + nhãn y NAV_ITEMS (E:/tool/tiktok_poster_v2/src/desktop/app.py:52-62).
const pvTRANG = [["Dashboard", "dashboard"], ["Accounts", "accounts"], ["Folders", "folders"], ["Calendar", "calendar"],
  ["Views", "views"], ["Queue", "queue"], ["Đăng bài", "post"], ["Logs", "logs"], ["Settings", "settings"]];
const pvTRANG_VE = { dashboard: "pvDbVe", accounts: "pvAcVe", folders: "pvFoVe", calendar: "pvCaVe",
  views: "pvViVe", queue: "pvQuVe", post: "pvPoVe", logs: "pvLoVe", settings: "pvSeVe" };
// Phiên trang Poster: pvDung tăng khi rời trang / đổi tab / đăng xuất; kết quả về muộn của phiên cũ bị bỏ (pvConSong).
let pvPhien = 0;

// --- poster-thuan start ---
// id = phần sau #/poster/ CHƯA giải mã → mã trang trong pvTRANG; rỗng / lạ / giải mã lỗi → "dashboard".
function pvPhanTich(id) {
  let s = "";
  if (typeof id === "string") {
    try { s = decodeURIComponent(id); } catch (e) { s = ""; } // %E0… hỏng: về Dashboard, không ném
  }
  return pvTRANG.some((t) => t[1] === s) ? s : "dashboard";
}

// Thanh 9 tab (link hash, router của khung.js lo việc đổi trang). CSS: flex-wrap, không cuộn ngang.
function pvTabHtml(ma) {
  return `<nav class="pv-tabs" aria-label="Poster V2">${pvTRANG.map(([nhan, m]) =>
    `<a class="pv-tab" href="#/poster/${esc(m)}" data-pv-tab="${esc(m)}"${m === ma ? ` aria-current="page"` : ""}>${esc(nhan)}</a>`).join("")}</nav>`;
}

// Chữ lỗi giống _raise_for_status (api_client.py:46-64) / errorText của api.ts:
// detail chuỗi → "<status>: <detail>"; detail khác → "<status>: <JSON>"; loi (Worker/video_server) → "<status>: <loi>";
// thân là chuỗi thô → "<status>: <300 ký tự đầu>"; còn lại → "HTTP <status>".
function pvChuLoi(status, j) {
  if (j && typeof j === "object" && !Array.isArray(j)) {
    const d = j.detail;
    if (typeof d === "string") { if (d) return `${status}: ${d}`; }
    else if (d !== undefined && d !== null) return `${status}: ${JSON.stringify(d)}`;
    if (typeof j.loi === "string" && j.loi) return `${status}: ${j.loi}`;
  } else if (typeof j === "string") {
    const t = j.trim().slice(0, 300);
    if (t) return `${status}: ${t}`;
  }
  return `HTTP ${status}`;
}

// Như qs() của api.ts: bỏ undefined/null → "?a=1&b=2" | "".
function pvQs(params) {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params && typeof params === "object" ? params : {})) {
    if (v === undefined || v === null) continue;
    sp.append(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}
// --- poster-thuan end ---

// Gọi /api/poster<duong>. duong = path backend ("/api/v2/…", có thể kèm query) hoặc route riêng ("/_video/12", "/_dem", "/_kq"…).
// Hợp đồng §2.1: luôn có header x-pv: 1; GET/DELETE không body, không content-type; POST/PUT/PATCH content-type JSON, body
// JSON.stringify(body ?? {}). 401 = hết phiên đăng nhập kho (Worker không bao giờ chuyển 401 của máy nhà, §3.2) → dừng trang + mở
// đăng nhập. 202 {cho} = lệnh chạy nền ở máy nhà → pvCho. Lỗi khác ném Error(pvChuLoi) có e.status và e.tam (lỗi tạm: mạng, 429, 5xx
// cổng) để trang phân biệt "thử lại sau" với lỗi vĩnh viễn. KHÔNG tự gọi lại lệnh ghi.
async function pvGoi(method, duong, body) {
  const m = String(method || "").toUpperCase();
  const coBody = m === "POST" || m === "PUT" || m === "PATCH";
  if (!coBody && m !== "GET" && m !== "DELETE") throw new Error(`Method không hỗ trợ: ${m}`);
  if (typeof duong !== "string" || !duong.startsWith("/")) throw new Error("Đường dẫn Poster không hợp lệ");
  const phien = pvPhien;
  const loi = (msg, status) => Object.assign(new Error(msg), { status, tam: [0, 429, 502, 503, 504, 524].includes(status) });
  const tuyChon = { method: m, cache: "no-store", headers: coBody ? { "x-pv": "1", "content-type": "application/json" } : { "x-pv": "1" } };
  if (coBody) tuyChon.body = JSON.stringify(body ?? {});
  let r;
  try { r = await fetch(`/api/poster${duong}`, tuyChon); }
  catch (err) { throw loi(`Không kết nối được máy chủ: ${err && err.message ? err.message : err}`, 0); }
  const txt = await r.text().catch(() => "");
  let j = {};
  if (txt) {
    try { j = JSON.parse(txt); } catch (e) { j = txt.trim().startsWith("<") ? {} : txt; } // trang HTML lỗi của edge: bỏ, chỉ giữ mã
  }
  if (r.status === 401) {
    pvDung(); // đăng xuất không đi qua mnRoute (P2-3): tự dừng hẹn giờ + bỏ kết quả muộn
    auth.user = ""; renderUser(); openLogin();
    throw loi("Hết phiên đăng nhập — đăng nhập lại", 401);
  }
  if (r.status === 202 && j && typeof j === "object" && typeof j.cho === "string") return pvCho(j.cho, j.toi_da_giay, phien);
  // ma (video_server): "chua_mo" | "token" | "cong_la" → thanh trạng thái biết chặng nào hỏng mà không phải dò chữ.
  if (!r.ok) throw Object.assign(loi(pvChuLoi(r.status, j), r.status), { ma: j && typeof j === "object" && typeof j.ma === "string" ? j.ma : "" });
  return j;
}

// Hỏi GET /_kq/<cho> 3 s/lần, tối đa (toiDaGiay + 60) s, gắn với phiên lúc gọi (mặc định pvPhien hiện tại; pvGoi truyền phiên lúc
// BẮT ĐẦU request để lệnh trả 202 sau khi đã rời trang không bắt đầu hỏi). Phiên đổi → ngừng hỏi, ném lỗi e.roiTrang (trang con không
// hiện). Lỗi tạm khi hỏi (mạng chập chờn) → hỏi tiếp; lỗi vĩnh viễn (404 mất theo dõi) → ném. Lệnh nền vẫn chạy ở máy nhà.
async function pvCho(cho, toiDaGiay, phien = pvPhien) {
  const roi = () => Object.assign(new Error("Đã rời trang Poster"), { roiTrang: true });
  if (!pvConSong(phien)) throw roi();
  if (typeof cho !== "string" || !/^[0-9a-f]{32}$/.test(cho)) throw new Error("Mã lệnh chờ không hợp lệ");
  const giay = Number(toiDaGiay);
  const han = Date.now() + ((Number.isFinite(giay) && giay > 0 ? Math.min(giay, 3600) : 300) + 60) * 1000;
  for (;;) {
    // Ngủ 3 s; pvDung đánh thức sớm (pvCho.ngu) để lỗi roiTrang ra ngay, không giữ trang cũ thêm 3 s.
    await new Promise((xong) => {
      const day = () => { clearTimeout(t); pvCho.ngu.delete(day); xong(); };
      const t = setTimeout(day, 3000);
      pvCho.ngu.add(day);
    });
    if (!pvConSong(phien)) throw roi();
    if (Date.now() > han) throw Object.assign(new Error("Quá giờ chờ kết quả: xem Logs/Queue."), { status: 504 });
    let kq;
    try { kq = await pvGoi("GET", `/_kq/${cho}`); }
    catch (e) {
      if (!pvConSong(phien)) throw roi();
      if (e && e.tam) continue;
      throw e;
    }
    if (!pvConSong(phien)) throw roi();
    if (kq && kq.xong === true) {
      const st = Number(kq.status);
      if (st >= 200 && st < 300) return kq.body;
      throw Object.assign(new Error(pvChuLoi(st, kq.body)), { status: st });
    }
  }
}

// 1:1 api_client.py (tên camelCase như src/lib/poster/api.ts): CHỈ phương thức 9 trang dùng (bảng §2.2 #2–#45) + 4 tiện ích route riêng.
// id phải là số nguyên ≤ 9 chữ số, khoá Settings theo {key} của §2.2: chặn ghép path lạ ("../x") ngay ở trình duyệt.
const pvApi = (() => {
  const so = (x) => {
    const n = typeof x === "number" ? x : typeof x === "string" && /^\d{1,9}$/.test(x) ? Number(x) : NaN;
    if (!Number.isInteger(n) || n < 0 || n > 999999999) throw new Error(`Mã không hợp lệ: ${String(x).slice(0, 40)}`);
    return n;
  };
  const khoa = (k) => {
    if (typeof k !== "string" || !/^[A-Za-z0-9_.-]{1,64}$/.test(k) || k === "." || k === "..") throw new Error("Khoá Settings không hợp lệ");
    return k;
  };
  const get = async (ep, params) => pvGoi("GET", ep + pvQs(params));
  const post = async (ep, data) => pvGoi("POST", ep, data ?? {});
  const put = async (ep, data) => pvGoi("PUT", ep, data ?? {});
  const patch = async (ep, data) => pvGoi("PATCH", ep, data ?? {});
  const del = async (ep) => pvGoi("DELETE", ep);
  return Object.freeze({
    // === Accounts ===
    listAccounts: async () => get("/api/v2/accounts/"),
    createAccount: async (data) => post("/api/v2/accounts/", data),
    updateAccount: async (id, data) => put(`/api/v2/accounts/${so(id)}`, data),
    deleteAccount: async (id) => del(`/api/v2/accounts/${so(id)}`),
    testCookies: async (id) => post(`/api/v2/accounts/${so(id)}/test-cookies`),
    accountCooldown: async (id, hours = 24) => post(`/api/v2/accounts/${so(id)}/cooldown`, { hours }),
    accountClearCooldown: async (id) => del(`/api/v2/accounts/${so(id)}/cooldown`),
    cleanAllProfiles: async () => post("/api/v2/accounts/clean_profiles"),
    loginAndCapture: async (name, proxy = "", useFingerprint = false) =>
      post("/api/v2/accounts/login_and_capture", { name, proxy, use_fingerprint: useFingerprint }),
    cookiesFromJson: async (name, cookies) => post("/api/v2/accounts/cookies_from_json", { name, cookies }),
    viewsAccountHealth: async (id) => get(`/api/v2/views/health/${so(id)}`),
    // === Folders ===
    listFolders: async () => get("/api/v2/folders/"),
    getFolders: async (archived) => get("/api/v2/folders/", { archived }), // = self.api._get("/api/v2/folders/", archived=…) folders.py:797
    createFolder: async (data) => post("/api/v2/folders/", data),
    updateFolder: async (id, data) => put(`/api/v2/folders/${so(id)}`, data),
    archiveFolder: async (id, archived = true) => patch(`/api/v2/folders/${so(id)}`, { is_archived: archived ? 1 : 0 }),
    deleteFolder: async (id) => del(`/api/v2/folders/${so(id)}`),
    folderSuggestPhase: async (id, n) => get(`/api/v2/folders/${so(id)}/suggest_phase`, { n }),
    cadenceForecast: async (days = 14) => get("/api/v2/folders/cadence_forecast", { days }),
    driveTest: async (id) => get(`/api/v2/folders/${so(id)}/drive-test`),
    postNow: async (id, visibility = "everyone") => post(`/api/v2/folders/${so(id)}/post_now`, { visibility }),
    batchSchedule: async (data) => post("/api/v2/folders/batch_schedule", data),
    // === Queue ===
    listQueue: async (status, limit = 100, offset = 0) => get("/api/v2/queue/", { limit, offset, ...(status ? { status } : {}) }),
    statusCounts: async () => get("/api/v2/queue/status"),
    postQueueItem: async (id) => post(`/api/v2/queue/${so(id)}/post`),
    queueRetry: async (id) => post(`/api/v2/queue/${so(id)}/retry`),
    deleteQueueItem: async (id) => del(`/api/v2/queue/${so(id)}`),
    queueUnstick: async () => post("/api/v2/queue/unstick"),
    queueClearPending: async () => del("/api/v2/queue/pending/clear"),
    queueResetAll: async () => post("/api/v2/queue/reset-all"),
    queueRandomShuffle: async () => post("/api/v2/queue/random_shuffle"),
    // === Settings ===
    getSettingsAll: async () => get("/api/v2/settings/"),
    putSetting: async (key, value) => put(`/api/v2/settings/${khoa(key)}`, { value }), // = update_setting
    autopostOn: async () => post("/api/v2/settings/autopost-on"),
    autopostOff: async () => post("/api/v2/settings/autopost-off"),
    // === Calendar ===
    calendarMonth: async (year, month, accountId) => get("/api/v2/calendar/month", { year, month, ...(accountId ? { account_id: accountId } : {}) }),
    createCalendarPlan: async (payload) => post("/api/v2/calendar/plans", payload),
    deleteCalendarPlan: async (id) => del(`/api/v2/calendar/plans/${so(id)}`),
    // === Views / Stats / System / Logs ===
    viewsSummary: async (params) => get("/api/v2/views/summary", params),
    viewsVideos: async (params) => get("/api/v2/views/videos", params),
    viewsRefresh: async () => post("/api/v2/views/refresh"),
    getStats: async () => get("/api/v2/stats/"),
    healthCheck: async () => get("/api/v2/system/health"),
    listLogs: async (limit = 100, offset = 0, status) => get("/api/v2/logs/", { limit, offset, ...(status ? { status } : {}) }),
    affiliateStats: async (productId) => get("/api/v2/logs/affiliate-stats", productId ? { product_id: productId } : {}),
    // === Post (Direct upload) ===
    postVideoDirect: async (folderId, videoPath, caption, visibility = "everyone", firstComment = "", draft = false) =>
      post("/api/v2/post/direct", { folder_id: folderId, video_path: videoPath, caption, visibility, first_comment: firstComment, draft }),
    // === Route riêng của video_server (§2.2) ===
    dsVideoFolder: async (folderId) => get(`/_video/${so(folderId)}`), // → {ho_tro, video:[{name,path,size}]}
    demVideo: async (duongDan) => post("/_dem", { duong_dan: duongDan }), // → {ton_tai, so_video}
    thongTin: async () => get("/_thong_tin"), // → {backend, co_token, thu_muc, database, profiles}
    batBackend: async () => post("/_bat_backend", {}), // → {trang_thai: "da_chay"|"dang_bat", pid?} | 409 {ma:"cong_la"}
    dangChay: async () => get("/_kq"), // → {dang_chay:[{cho, method, path, lop, giay_da_chay, toi_da_giay, tom_tat}]}
  });
})();

// khung.js gọi (sau pvDung). Vẽ thanh trạng thái (healthCheck 30 s/lần như app.py:203-205) + 9 tab + <section id="pv-noi">,
// rồi giao #pv-noi cho trang con globalThis[pvTRANG_VE[ma]](khung, phien).
async function pvRender(id) {
  const phien = pvPhien;
  const ma = pvPhanTich(id);
  $("#app").innerHTML = `<div class="pv-khung">
    <div class="pv-tt" role="status"><span class="pv-cham" id="pv-cham" aria-hidden="true">●</span><span class="pv-tt-chu" id="pv-tt-chu">Khoi tao...</span><span class="pv-tt-url" id="pv-tt-url"></span><button type="button" class="btn ghost pv-tt-nut" id="pv-tt-nut" hidden>Bật Poster V2</button></div>
    ${pvTabHtml(ma)}
    <section id="pv-noi" class="pv-noi"></section>
  </div>`;
  // Thanh trạng thái: nói rõ chặng nào hỏng (trình duyệt → Worker → tunnel/video_server → Poster :8023), không nhại nguyên câu lỗi.
  // Poster chưa chạy (hoặc lỗi lạ) → hiện nút "Bật Poster V2": POST /_bat_backend, video_server mở src.backend.main trong cửa sổ
  // console riêng ở máy nhà; cổng bị chương trình khác chiếm thì video_server trả 409 kèm tên + PID. Cờ chặn chạy chồng đặt TRƯỚC await.
  const phanLoai = (e) => {
    const msg = String(e && e.message ? e.message : e);
    const st = e && e.status, ma = e && e.ma;
    if (st === 0) return { tt: "down", chu: "Không kết nối được web kho (mất mạng?)" };
    if (ma === "chua_mo" || msg.includes("Poster V2 trên máy nhà chưa mở")) return { tt: "down", chu: "Poster V2 chưa chạy trên máy nhà", nut: true };
    if (ma === "token") return { tt: "down", chu: "Poster V2 từ chối token: TT_API_BEARER_TOKEN trong .env của Poster bị lệch" };
    if (ma === "cong_la") return { tt: "down", chu: msg.replace(/^\d+: /, ""), nut: true };
    if (msg.includes("Máy nhà không trả lời")) {
      return { tt: "down", chu: "Máy nhà không trả lời: video_server hoặc tunnel đang tắt. Trên máy nhà chạy tools/chay_video.bat" };
    }
    if (msg.includes("VIDEO_KEY")) return { tt: "down", chu: "Máy nhà từ chối khoá của web (VIDEO_KEY lệch với tools/.video_key)" };
    if (st === 504 || msg.includes("quá chậm")) return { tt: "cham", chu: "Máy nhà phản hồi chậm, thử lại sau" };
    if (st === 503) return { tt: "down", chu: msg.replace(/^\d+: /, "") };
    return { tt: "down", chu: `Poster V2 lỗi: ${msg.slice(0, 120)}`, nut: true };
  };
  const veTT = ({ tt, chu, nut }) => {
    const cham = $("#pv-cham"), nhan = $("#pv-tt-chu"), b = $("#pv-tt-nut");
    if (cham) cham.dataset.tt = tt;
    if (nhan) { nhan.dataset.tt = tt; nhan.innerHTML = esc(chu); }
    if (b) b.hidden = !nut;
  };
  const CHO_BAT_MS = 45_000;
  let batDen = 0; // Date.now() hạn chờ Poster lên sau khi bấm bật; 0 = không đang bật
  let dangKiem = false;
  const kiem = async () => {
    if (dangKiem) return undefined;
    dangKiem = true;
    let kq;
    try {
      const h = await pvApi.healthCheck();
      kq = { tt: "ok", chu: `V2 OK (${h && h.status != null ? h.status : "unknown"})` };
    } catch (e) {
      kq = phanLoai(e);
    } finally {
      dangKiem = false;
    }
    if (!pvConSong(phien)) return kq;
    if (batDen && kq.tt !== "ok") {
      const con = batDen - Date.now();
      kq = con > 0 ? { tt: "cham", chu: `Đang khởi động Poster V2... (${Math.ceil(con / 1000)} s)` }
        : { tt: "down", chu: "Poster V2 không lên sau 45 s: xem cửa sổ console của backend trên máy nhà", nut: true };
      if (con <= 0) batDen = 0;
    } else if (kq.tt === "ok") {
      batDen = 0;
    }
    veTT(kq);
    return kq;
  };
  const choLen = () => {
    if (!batDen || !pvConSong(phien)) return;
    setTimeout(async () => {
      if (!pvConSong(phien)) return;
      await kiem();
      choLen();
    }, 2_000);
  };
  const nut = $("#pv-tt-nut");
  if (nut) {
    nut.addEventListener("click", async () => {
      if (nut.disabled) return;
      nut.disabled = true;
      nut.textContent = "Đang bật...";
      try {
        const r = await pvApi.batBackend();
        if (!pvConSong(phien)) return;
        batDen = r && r.trang_thai === "da_chay" ? 0 : Date.now() + CHO_BAT_MS;
        if (batDen) veTT({ tt: "cham", chu: "Đang khởi động Poster V2..." });
        await kiem();
        choLen();
      } catch (e) {
        if (!pvConSong(phien)) return;
        const cu = e && e.status === 404 && String(e.message).includes("không được phép");
        veTT(cu ? { tt: "down", chu: "Máy nhà/Worker là bản cũ, chưa có lệnh bật: deploy Worker và khởi động lại video_server" } : phanLoai(e));
      } finally {
        nut.disabled = false;
        nut.textContent = "Bật Poster V2";
      }
    });
  }
  kiem();
  pvHenGio(kiem, 30_000);
  // "V2 Backend: <url>" (status_bar.showMessage, app.py:189) lấy từ _thong_tin; lỗi thì để trống (thanh trạng thái đã báo down).
  pvApi.thongTin().then((t) => {
    if (!pvConSong(phien)) return;
    const u = $("#pv-tt-url");
    if (u && t && typeof t.backend === "string") u.innerHTML = esc(`V2 Backend: ${t.backend}`);
  }).catch(() => { /* thanh trạng thái đã hiện lỗi của healthCheck */ });

  const noi = $("#pv-noi");
  const ve = globalThis[pvTRANG_VE[ma]];
  if (typeof ve !== "function") {
    noi.innerHTML = typeof mnCHUA_CO === "string" ? mnCHUA_CO : `<p class="center muted">Trang đang được cập nhật.</p>`;
    return;
  }
  try { await ve(noi, phien); }
  catch (e) {
    if (!pvConSong(phien) || (e && e.roiTrang)) return;
    noi.innerHTML = `<p class="err">${esc(e && e.message ? e.message : e)}</p>`;
  }
}

// Rời trang Poster / đổi tab / đăng xuất: xoá mọi hẹn giờ pvHenGio, tăng pvPhien + đánh thức pvCho (ngừng hỏi, ném roiTrang),
// đóng hộp thoại đang mở (trả null/false), gọi pv<xx>Dung của trang con nếu có.
function pvDung() {
  for (const id of pvHenGio.ds) clearInterval(id);
  pvHenGio.ds.clear();
  pvPhien++;
  for (const day of [...pvCho.ngu]) day();
  for (const h of [...pvHop.mo]) h.dong();
  for (const ten of Object.values(pvTRANG_VE)) {
    const f = globalThis[ten.replace(/Ve$/, "Dung")];
    if (typeof f !== "function") continue;
    try { f(); } catch (e) { console.error("Poster: lỗi khi dừng trang", ten, e); }
  }
}

// true khi phiên còn là phiên hiện tại (trang con kiểm sau MỖI await trước khi vẽ).
function pvConSong(phien) {
  return phien === pvPhien;
}

// setInterval gắn phiên hiện tại. Mỗi lượt BỎ QUA khi: đã đăng xuất (!auth.on), tab ẩn (document.hidden), hoặc lượt trước (fn trả
// Promise) chưa xong (P2-3). Cờ "đang chạy" đặt TRƯỚC await. fn ném thì nuốt lỗi (trang tự hiện lỗi trong fn) và vẫn nhả cờ. pvDung xoá.
function pvHenGio(fn, ms) {
  const phien = pvPhien;
  let dang = false;
  const id = setInterval(async () => {
    if (!pvConSong(phien)) { clearInterval(id); pvHenGio.ds.delete(id); return; }
    if (dang || !auth.on || document.hidden) return;
    dang = true;
    try { await fn(); } catch (e) { /* trang tự hiện lỗi trong fn; hẹn giờ không được chết vì một lượt lỗi */ } finally { dang = false; }
  }, ms);
  pvHenGio.ds.add(id);
  return id;
}

// Port confirm_destructive (widgets/common.py:262-300) → Promise<boolean>. Gọi 1 tham số = (câu); 2+ tham số = (tiêu đề, câu, …).
// ten khác rỗng → thêm "Mục bị ảnh hưởng: …". Câu có "đăng"/"thêm" là hành động (nút "Xác nhận", mặc định Có);
// còn lại là xoá (nút "Xóa", mặc định Không).
function pvXacNhan(tieuDeHoacCau, cau, ten, chuCo, chuKhong = "Hủy") {
  const coTieuDe = cau !== undefined && cau !== null;
  const tieuDe = coTieuDe ? String(tieuDeHoacCau ?? "") : "Xác nhận";
  const chinh = String((coTieuDe ? cau : tieuDeHoacCau) ?? "");
  const day = ten ? `${chinh}\n\nMục bị ảnh hưởng: ${ten}\n\nBạn có chắc chắn muốn thực hiện?` : chinh;
  const hanhDong = chinh.toLowerCase().includes("đăng") || chinh.toLowerCase().includes("thêm");
  const hop = pvHop({
    tieuDe,
    html: `<p class="pv-cau"><span class="pv-ic" aria-hidden="true">${hanhDong ? "❓" : "⚠️"}</span> ${esc(day)}</p>`,
    nut: [{ ma: "co", chu: chuCo || (hanhDong ? "Xác nhận" : "Xóa"), chinh: hanhDong }, { ma: "khong", chu: chuKhong, chinh: !hanhDong }],
  });
  return hop.cho.then((v) => v === "co");
}

// QMessageBox.information | warning | critical → Promise<void> (đóng bằng OK / Esc).
function pvThongBao(tieuDe, cau, kieu = "info") {
  const IC = { info: "ℹ️", warning: "⚠️", critical: "⛔" };
  const k = Object.prototype.hasOwnProperty.call(IC, kieu) ? kieu : "info";
  const hop = pvHop({
    tieuDe: String(tieuDe ?? ""),
    html: `<p class="pv-cau pv-hop-${k}"><span class="pv-ic" aria-hidden="true">${IC[k]}</span> ${esc(cau)}</p>`,
    nut: [{ ma: "ok", chu: "OK", chinh: true }],
  });
  return hop.cho.then(() => undefined);
}

// Hộp tuỳ biến (thẻ <dialog> gắn vào body). tieuDe và chữ nút được esc ở đây; html do trang gọi TỰ esc dữ liệu API.
// → { el, dong(), cho: Promise<mã nút | null> } (null = Esc / đóng / rời trang).
function pvHop({ tieuDe = "", html = "", nut = [] } = {}) {
  const el = document.createElement("dialog");
  el.className = "pv-hop";
  el.innerHTML = `<h3 class="pv-hop-tieu-de">${esc(tieuDe)}</h3><div class="pv-hop-noi">${html}</div><div class="pv-hop-nut">${
    (Array.isArray(nut) ? nut : []).map((n) => `<button type="button" class="btn${n && n.chinh ? "" : " ghost"}" data-pv-nut="${esc(n && n.ma)}">${esc(n && n.chu)}</button>`).join("")}</div>`;
  let traLoi;
  const cho = new Promise((r) => { traLoi = r; });
  let xong = false;
  const hop = { el, cho, dong: () => {} };
  const ket = (v) => {
    if (xong) return;
    xong = true;
    pvHop.mo.delete(hop);
    try { if (el.open) el.close(); } catch (e) { /* hộp đã bị gỡ khỏi DOM */ }
    el.remove();
    traLoi(v);
  };
  hop.dong = () => ket(null);
  el.addEventListener("click", (ev) => {
    const b = ev.target && typeof ev.target.closest === "function" ? ev.target.closest("[data-pv-nut]") : null;
    if (b) ket(b.dataset.pvNut);
  });
  el.addEventListener("cancel", (ev) => { ev.preventDefault(); ket(null); });
  el.addEventListener("close", () => ket(null));
  document.body.append(el);
  pvHop.mo.add(hop);
  el.showModal();
  const macDinh = el.querySelector(".pv-hop-nut .btn:not(.ghost)");
  if (macDinh) macDinh.focus();
  return hop;
}

// Trạng thái nội bộ gắn vào hàm (không thêm tên cấp đỉnh, §6.4).
pvHenGio.ds = new Set(); // id setInterval đang chạy
pvCho.ngu = new Set(); // hàm đánh thức các lượt ngủ 3 s của pvCho
pvHop.mo = new Set(); // hộp thoại đang mở
