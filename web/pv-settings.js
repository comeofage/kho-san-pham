// Poster V2 trên web — trang Settings (#/poster/settings). Bê nguyên E:/tool/tiktok_poster_v2/src/desktop/pages/settings.py:
// nhóm "Browser Engine" (Default engine + headless, "Save Engine Settings"), "Telegram Notifications" (Bot Token, Chat ID,
// "Save Telegram Settings"), "Architecture Info". Thiết kế: docs/poster-v2-tren-web.md §5.3, §6.3–§6.5, phiếu W-P2. Tiền tố pvse.
// Chỗ khác desktop (§5.3, chốt C1):
// - Ô Bot Token là <input type="password"> LUÔN trống khi tải: máy nhà che secret thành "***" (C1), giá trị đó chỉ dùng để chọn
//   placeholder như settings.py:160-163, KHÔNG BAO GIỜ đổ vào ô (đổ vào rồi bấm lưu sẽ ghi đè token thật bằng "***").
// - "Architecture Info" lấy thư mục / database / profiles từ GET /_thong_tin của video_server (không có get_app_home cục bộ).
// - Không vẽ nhóm "Bản quyền" (desktop chỉ hiện khi licensing.is_enforced(); máy nhà chạy từ mã nguồn nên cũng không hiện).
"use strict";

// --- pvse-thuan start ---
const pvseENGINE = ["selenium", "camoufox", "donut", "cloak"]; // settings.py:47

// _on_loaded (settings.py:152-164) → giá trị cần đặt vào form; null khi config không phải dict (gốc: return, không đổi gì).
// engine = null khi không có trong danh sách (findText < 0 → giữ lựa chọn hiện tại).
function pvseNap(config) {
  if (!config || typeof config !== "object" || Array.isArray(config)) return null;
  const eng = config.default_engine === undefined ? "selenium" : config.default_engine;
  return {
    engine: pvseENGINE.includes(eng) ? eng : null,
    headless: (config.headless === undefined ? "0" : config.headless) === "1",
    placeholder: config.telegram_bot_token ? "*** (đã lưu, nhập mới để thay)" : "Bot Token",
    chat: String(config.telegram_chat_id || ""),
  };
}

// _save_telegram_settings (settings.py:190-231): danh sách [khoá, giá trị] cần PUT theo thứ tự; [] = "Không có gì để lưu".
function pvseTelegram(token, chat) {
  const t = String(token ?? "").trim();
  const c = String(chat ?? "").trim();
  if (t && c) return [["telegram_bot_token", t], ["telegram_chat_id", c]];
  if (t) return [["telegram_bot_token", t]];
  if (c) return [["telegram_chat_id", c]];
  return [];
}

// Khối "Architecture Info" (settings.py:88-93) từ _thong_tin {thu_muc, database, profiles}.
function pvseThongTin(t) {
  const x = t && typeof t === "object" ? t : {};
  const s = (v) => (typeof v === "string" ? v : "");
  return `TikTok Poster V2\nThư mục dữ liệu: ${s(x.thu_muc)}\nDatabase: ${s(x.database)}\nProfiles: ${s(x.profiles)}`;
}

// widgets/common.py _friendly_error: chữ lỗi hiện trong hộp "Lỗi" (giữ nguyên chữ không dấu của bản gốc).
function pvseLoi(e) {
  const msg = String(e && e.message ? e.message : e);
  if (msg.includes("401")) return "Khong co quyen truy cap (401). Kiem tra API token trong .env.";
  if (msg.includes("404")) return "API khong ton tai (404). Kiem tra backend co dang chay khong.";
  if ((e && e.status === 0) || msg.includes("Connection")) return "Khong ket noi duoc backend. Hay kiem tra V2 Backend da chay chua.";
  if (msg.toLowerCase().includes("timeout")) return "Backend phan hoi cham (timeout). Thu lai sau.";
  return `${e && e.status ? "HTTPError" : "Error"}: ${msg.slice(0, 200)}`;
}

function pvseHtml() {
  return `<div class="pvse">
  <h2 style="margin:0">Settings</h2>
  <p class="muted" style="margin:4px 0 12px">Cấu hình engine, thông báo và thông tin hệ thống.</p>
  <div class="pv-nhom"><h4>Browser Engine</h4><div class="pv-form">
    <label for="pvse-engine">Default engine:</label>
    <select id="pvse-engine">${pvseENGINE.map((e, i) => `<option value="${e}"${i === 0 ? " selected" : ""}>${e}</option>`).join("")}</select>
    <span></span><label style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="pvse-headless" style="width:auto"> Chạy headless (không hiển thị cửa sổ)</label>
    <span></span><div><button type="button" class="btn" data-pvse="engine">Save Engine Settings</button></div>
  </div></div>
  <div class="pv-nhom"><h4>Telegram Notifications</h4><div class="pv-form">
    <label for="pvse-token">Bot Token:</label>
    <input id="pvse-token" type="password" autocomplete="new-password" placeholder="Bot Token (ẩn khi đã lưu)" value="">
    <label for="pvse-chat">Chat ID:</label>
    <input id="pvse-chat" type="text" autocomplete="off" placeholder="Chat ID" value="">
    <span></span><div><button type="button" class="btn" data-pvse="telegram">Save Telegram Settings</button></div>
  </div></div>
  <div class="pv-nhom"><h4>Architecture Info</h4>
    <div id="pvse-info" class="muted" style="white-space:pre-line;font-size:12px;line-height:1.6;user-select:text;overflow-wrap:anywhere">${esc(pvseThongTin({}))}</div>
  </div>
</div>`;
}
// --- pvse-thuan end ---

// Khung gọi khi mở tab Settings. Tải get_settings_all (lỗi chỉ ghi console như settings.py:149) + _thong_tin cho Architecture Info.
async function pvSeVe(khung, phien) {
  khung.innerHTML = pvseHtml();
  const o = (id) => khung.querySelector(`#${id}`);
  const ok = () => pvConSong(phien);

  const dangLuu = { engine: false, telegram: false }; // cờ chặn bấm cùng nút Save chồng (đặt TRƯỚC await)
  // Gốc: _put lần lượt; lỗi bất kỳ lần nào → hộp "Lỗi" và dừng chuỗi.
  const luu = async (nut, cap, sauKhiXong) => {
    if (dangLuu[nut]) return;
    dangLuu[nut] = true;
    try {
      for (const [k, v] of cap) {
        try { await pvApi.putSetting(k, v); }
        catch (e) {
          if (!ok()) return;
          await pvThongBao("Lỗi", pvseLoi(e), "critical");
          return;
        }
        if (!ok()) return;
      }
      await sauKhiXong();
    } finally {
      dangLuu[nut] = false;
    }
  };

  const luuEngine = () => {
    // _save_engine_settings (settings.py:166-188): default_engine rồi headless ("1"/"0") → "Đã lưu" / "Engine settings saved."
    const sel = o("pvse-engine"), chk = o("pvse-headless");
    const engine = sel ? String(sel.value) : "";
    const headless = chk && chk.checked ? "1" : "0";
    return luu("engine", [["default_engine", engine], ["headless", headless]], () => pvThongBao("Đã lưu", "Engine settings saved.", "info"));
  };

  const luuTelegram = async () => {
    const tk = o("pvse-token"), ch = o("pvse-chat");
    const cap = pvseTelegram(tk ? tk.value : "", ch ? ch.value : "");
    if (!cap.length) {
      await pvThongBao("Không có gì để lưu", "Chưa nhập token hoặc chat ID.", "info");
      return;
    }
    // _after_tg: hộp "Đã lưu" rồi xoá ô token, placeholder "*** (đã lưu)" (ô Chat ID giữ nguyên).
    return luu("telegram", cap, async () => {
      await pvThongBao("Đã lưu", "Telegram settings saved.", "info");
      if (!ok()) return;
      const t = o("pvse-token");
      if (t) { t.value = ""; t.placeholder = "*** (đã lưu)"; }
    });
  };

  khung.addEventListener("click", (ev) => {
    const b = ev.target && typeof ev.target.closest === "function" ? ev.target.closest("[data-pvse]") : null;
    if (!b || !ok()) return;
    if (b.dataset.pvse === "engine") luuEngine();
    else if (b.dataset.pvse === "telegram") luuTelegram();
  });

  const thongTin = pvApi.thongTin().then((t) => {
    if (!ok()) return;
    const el = o("pvse-info");
    if (el) el.innerHTML = esc(pvseThongTin(t));
  }).catch((e) => {
    if (!ok()) return;
    console.warn(`Architecture Info: ${e && e.message ? e.message : e}`);
  });

  try {
    const cfg = await pvApi.getSettingsAll();
    if (!ok()) return;
    const n = pvseNap(cfg);
    if (n) {
      const sel = o("pvse-engine"), chk = o("pvse-headless"), tk = o("pvse-token"), ch = o("pvse-chat");
      if (sel && n.engine) sel.value = n.engine;
      if (chk) chk.checked = n.headless;
      if (tk) tk.placeholder = n.placeholder; // KHÔNG đặt tk.value (C1: giá trị là "***")
      if (ch) ch.value = n.chat;
    }
  } catch (e) {
    if (!ok()) return;
    console.warn(`Settings load failed: ${e && e.message ? e.message : e}`);
  }
  await thongTin;
}
