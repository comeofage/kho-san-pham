// Poster V2 › Đăng bài (#/poster/post) — port 1:1 E:/tool/tiktok_poster_v2/src/desktop/pages/post.py (PostPage), đối chiếu bản Svelte
// a55d687 Post.svelte. Thiết kế: docs/poster-v2-tren-web.md §3.3 (post/direct lớp L chạy nền, khoá "ĐĂNG NGAY" theo dangChay),
// §5.1 (danh sách video qua route _video/<folder_id> của máy nhà), §6.3–§6.5. Tiền tố pvpo / .pvpo-. Chỉ gọi pvApi/pvCho; hộp qua
// pvHop/pvThongBao; mọi chuỗi qua esc. KHÔNG BAO GIỜ tự gửi lại lệnh đăng (lỗi hay hết giờ đều chỉ báo + hỏi dangChay).
"use strict";

// --- pvpo-thuan start ---
const PVPO_HIEN = ["everyone", "private", "friends"]; // visibility_combo (post.py:130)
const PVPO_CO_THE = "Thao tác CÓ THỂ đã chạy: xem Logs/Queue trước khi bấm lại.";

// f"{size / (1024*1024):.1f}" của Python: làm tròn nửa-về-chẵn khi đúng giữa (size nguyên → so bằng số nguyên, không sai số).
function pvpoMb(size) {
  const n = Number(size);
  if (!Number.isFinite(n)) return "nan";
  const MB = 1048576;
  if (Number.isSafeInteger(n) && n >= 0 && Number.isSafeInteger(n * 10) && (n * 10) % MB === MB / 2) {
    const duoi = Math.floor((n * 10) / MB);
    return ((duoi % 2 === 0 ? duoi : duoi + 1) / 10).toFixed(1);
  }
  return (n / MB).toFixed(1);
}

// Dòng của video_list (post.py:254-257).
function pvpoDongVideo(v) {
  return `${v.name} (${pvpoMb(v.size)} MB)`;
}

// Câu hộp "Xác nhận đăng" (post.py:300-306). Cắt 50 ký tự theo code point như Python.
function pvpoCauXacNhan(ten, caption, hien, nhap) {
  const kt = Array.from(caption);
  return `Đăng video '${ten}'?\n\nCaption: ${kt.slice(0, 50).join("")}${kt.length > 50 ? "..." : ""}\nVisibility: ${hien}\nDraft: ${nhap ? "Có" : "Không"}`;
}

// Tên folder trong combo (post.py:209): f.get("name", f"Folder #{id}").
function pvpoTenFolder(f) {
  return f && Object.prototype.hasOwnProperty.call(f, "name") && f.name !== null && f.name !== undefined ? String(f.name) : `Folder #${f ? f.id : ""}`;
}

// Danh sách video hợp lệ từ _video/<id> (§5.1) → [{name, path, size}]; ho_tro=false → null.
function pvpoDsVideo(r) {
  if (!r || typeof r !== "object" || r.ho_tro !== true) return null;
  return (Array.isArray(r.video) ? r.video : []).filter((v) => v && typeof v.name === "string" && typeof v.path === "string")
    .map((v) => ({ name: v.name, path: v.path, size: Number(v.size) || 0 }));
}

// Mọi lệnh đăng đang chạy trong GET /_kq (§3.3) → [{ cho, toiDa, folderId, video }].
function pvpoDsLenhDang(dc) {
  const ds = dc && Array.isArray(dc.dang_chay) ? dc.dang_chay : [];
  return ds.filter((x) => x && x.method === "POST" && typeof x.path === "string"
    && x.path.split("?")[0] === "/api/v2/post/direct" && typeof x.cho === "string").map((l) => {
    const t = l.tom_tat && typeof l.tom_tat === "object" ? l.tom_tat : {};
    return { cho: l.cho, toiDa: l.toi_da_giay, folderId: Number.isInteger(t.folder_id) ? t.folder_id : null,
      video: typeof t.video === "string" ? t.video : "" };
  });
}

// Lệnh đăng đang chạy đầu tiên (khoá nút khi mở trang) → { cho, toiDa, folderId, video } | null.
function pvpoLenhDang(dc) {
  return pvpoDsLenhDang(dc)[0] || null;
}

// PureWindowsPath(video_path).name (tom_tat.video của video_server _tom_tat): bỏ ổ đĩa, tách theo \ và /, lấy phần cuối khác rỗng.
function pvpoTenTep(p) {
  const ds = String(p ?? "").replace(/^[A-Za-z]:/, "").split(/[\\/]+/).filter((x) => x);
  return ds.length ? ds[ds.length - 1] : "";
}

// Lệnh đăng đang chạy KHỚP lệnh vừa gửi (cùng folder_id và cùng tên tệp video) → { cho, toiDa, folderId, video } | null.
// Không khớp = lệnh của tab / máy khác: không được gắn kết quả của nó vào lệnh này (P3-4).
function pvpoLenhKhop(dc, folderId, tep) {
  if (!Number.isInteger(folderId) || typeof tep !== "string" || !tep) return null;
  return pvpoDsLenhDang(dc).find((l) => l.folderId === folderId && l.video === tep) || null;
}

// Khung trang (post.py:31-190): trái = folder + danh sách video; phải = form đăng.
function pvpoKhungHtml() {
  return `<div class="pvpo" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;align-items:start">
  <div class="pvpo-trai" style="display:flex;flex-direction:column;gap:6px;min-width:0">
    <label class="muted" for="pvpo-folder">Chọn Folder:</label>
    <select id="pvpo-folder" data-pvpo-o="folder" data-pvpo-vung="folder"><option value="0">-- Chọn Folder --</option></select>
    <span class="muted">Videos trong folder:</span>
    <div class="pv-the pvpo-ds" data-pvpo-vung="ds" role="listbox" aria-label="Videos trong folder" style="padding:0;min-height:120px;max-height:50vh;overflow:auto"></div>
    <span class="pv-nho" data-pvpo-vung="info" style="overflow-wrap:anywhere">Chọn một video để xem thông tin</span>
  </div>
  <div class="pvpo-phai" style="display:flex;flex-direction:column;gap:8px;min-width:0">
    <h2 style="margin:0">Đăng Video</h2>
    <span class="muted">Chọn video và nhấn Đăng để đăng ngay lập tức.</span>
    <div class="pvpo-xem" data-pvpo-vung="xem" style="border:2px dashed var(--line);border-radius:8px;padding:40px 12px;text-align:center;color:var(--muted);overflow-wrap:anywhere">Chưa chọn video</div>
    <label for="pvpo-caption" style="font-weight:bold">Caption:</label>
    <textarea id="pvpo-caption" data-pvpo-o="caption" rows="4" placeholder="Nhập caption cho video..."></textarea>
    <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px"><label for="pvpo-hien">Visibility:</label>
      <select id="pvpo-hien" data-pvpo-o="hien">${PVPO_HIEN.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("")}</select></div>
    <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px"><label for="pvpo-fc">First Comment:</label>
      <input id="pvpo-fc" type="text" data-pvpo-o="fc" placeholder="Bình luận đầu tiên (tùy chọn)..." style="flex:1;min-width:0"></div>
    <div data-pvpo-vung="nhap">${pvpoNhapHtml(false)}</div>
    <div class="pv-cong-cu" data-pvpo-vung="nut" style="margin:0">${pvpoNutHtml(false, null)}</div>
    <span class="pv-nho pv-vang" data-pvpo-vung="tt" style="white-space:pre-wrap;overflow-wrap:anywhere"></span>
  </div>
</div>`;
}

// Nút bật/tắt "Lưu nháp (Draft)" (post.py:149-165, QPushButton checkable).
function pvpoNhapHtml(bat) {
  return `<button type="button" class="btn${bat ? "" : " ghost"}" data-pvpo-nut="nhap" aria-pressed="${bat ? "true" : "false"}">Lưu nháp (Draft)</button>`;
}

// "Làm mới" + "ĐĂNG NGAY". Đăng bị khoá khi chưa chọn video (desktop setEnabled(False)) HOẶC có lệnh đăng đang chạy / đang hỏi (§3.3).
function pvpoNutHtml(choPhep, dang) {
  const khoa = !choPhep || !!dang;
  const phu = dang && dang.video !== undefined ? `<span class="pv-nho pvpo-dang">${esc(`Đang đăng ${dang.video}…`)}</span>` : "";
  return `<button type="button" class="btn ghost" data-pvpo-nut="lammoi">Làm mới</button>
    <button type="button" class="btn" data-pvpo-nut="dang"${khoa ? " disabled" : ""}>ĐĂNG NGAY</button>${phu}`;
}

function pvpoFolderHtml(folders, idx) {
  return `<option value="0"${idx === 0 ? " selected" : ""}>-- Chọn Folder --</option>${folders.map((f, i) =>
    `<option value="${i + 1}"${idx === i + 1 ? " selected" : ""}>${esc(pvpoTenFolder(f))}</option>`).join("")}`;
}

function pvpoDsHtml(videos, row) {
  return videos.map((v, i) => `<button type="button" class="pvpo-video" role="option" data-pvpo-nut="video" data-pvpo-i="${i}" aria-selected="${i === row ? "true" : "false"}"
    style="display:block;width:100%;text-align:left;padding:8px;border:0;border-bottom:1px solid var(--line);background:${i === row ? "color-mix(in srgb, var(--accent) 12%, transparent)" : "transparent"};color:inherit;cursor:pointer;overflow-wrap:anywhere">${esc(pvpoDongVideo(v))}</button>`).join("");
}
// --- pvpo-thuan end ---

// Trang Đăng bài. Trạng thái trong closure tt gắn phiên; sau MỖI await kiểm pvConSong trước khi vẽ / hiện hộp.
async function pvPoVe(khung, phien) {
  const tt = { phien, khung, folders: [], idx: 0, folderId: null, videos: [], row: -1, caption: "", hien: "everyone", fc: "", nhap: false,
    choPhep: false, dang: { kiem: true }, lanTai: 0 };
  khung.innerHTML = pvpoKhungHtml();
  pvpoVe(tt, "nut");
  khung.addEventListener("click", (ev) => {
    const b = ev.target && typeof ev.target.closest === "function" ? ev.target.closest("[data-pvpo-nut]") : null;
    if (!b) return;
    const nut = b.dataset.pvpoNut;
    if (nut === "video") pvpoChonVideo(tt, Number(b.dataset.pvpoI));
    else if (nut === "nhap") { tt.nhap = !tt.nhap; pvpoVe(tt, "nhap"); }
    else if (nut === "lammoi") { if (tt.folderId) pvpoDoiFolder(tt); }
    else if (nut === "dang") pvpoDang(tt);
  });
  const nhap = (ev) => {
    const t = ev.target;
    const ma = t && t.dataset ? t.dataset.pvpoO : undefined;
    if (ma === "folder") {
      if (ev.type !== "change") return;
      const i = Number(t.value);
      tt.idx = Number.isInteger(i) && i >= 0 && i <= tt.folders.length ? i : 0;
      pvpoDoiFolder(tt);
    } else if (ma === "caption") tt.caption = String(t.value ?? "");
    else if (ma === "fc") tt.fc = String(t.value ?? "");
    else if (ma === "hien") tt.hien = PVPO_HIEN.includes(t.value) ? t.value : "everyone";
  };
  khung.addEventListener("input", nhap);
  khung.addEventListener("change", nhap);

  // §3.3: hỏi lệnh đăng đang chạy TRƯỚC khi mở khoá "ĐĂNG NGAY".
  let lenh = null;
  try { lenh = pvpoLenhDang(await pvApi.dangChay()); }
  catch (e) { if (!pvConSong(phien)) return; /* không hỏi được: video_server vẫn chặn trùng ở máy nhà */ }
  if (!pvConSong(phien)) return;
  tt.dang = null;
  if (lenh) pvpoGan(tt, lenh);
  else pvpoVe(tt, "nut");
  await pvpoTaiFolder(tt, lenh ? lenh.folderId : null);
}

// Vẽ lại một vùng theo trạng thái.
function pvpoVe(tt, vung) {
  const v = tt.khung.querySelector(`[data-pvpo-vung="${vung}"]`);
  if (!v) return;
  if (vung === "nut") v.innerHTML = pvpoNutHtml(tt.choPhep, tt.dang);
  else if (vung === "nhap") v.innerHTML = pvpoNhapHtml(tt.nhap);
  else if (vung === "ds") v.innerHTML = pvpoDsHtml(tt.videos, tt.row);
  else if (vung === "folder") v.innerHTML = pvpoFolderHtml(tt.folders, tt.idx);
}

function pvpoChu(tt, vung, chu) {
  const v = tt.khung.querySelector(`[data-pvpo-vung="${vung}"]`);
  if (v) v.innerHTML = esc(chu);
}

function pvpoDatO(tt, ma, gt) {
  const v = tt.khung.querySelector(`[data-pvpo-o="${ma}"]`);
  if (v) v.value = gt;
}

// _load_folders / _on_folders_loaded (post.py:196-210): combo xoá → về "-- Chọn Folder --". chon = folder của lệnh đăng đang chạy.
async function pvpoTaiFolder(tt, chon) {
  let fs;
  try { fs = await pvApi.listFolders(); }
  catch (e) {
    if (pvConSong(tt.phien) && !(e && e.roiTrang)) console.error(`Failed to load folders: ${e && e.message ? e.message : e}`);
    return;
  }
  if (!pvConSong(tt.phien)) return;
  tt.folders = Array.isArray(fs) ? fs.filter((f) => f && typeof f === "object") : [];
  const i = chon === null ? -1 : tt.folders.findIndex((f) => f.id === chon);
  tt.idx = i >= 0 ? i + 1 : 0;
  pvpoVe(tt, "folder");
  pvpoDoiFolder(tt);
}

// _on_folder_changed (post.py:212-232) + _load_local_videos (post.py:234-260) qua _video/<id> (§5.1).
async function pvpoDoiFolder(tt) {
  const f = tt.idx > 0 ? tt.folders[tt.idx - 1] : null;
  const folderId = f && f.id !== undefined ? f.id : null;
  tt.folderId = folderId;
  tt.videos = [];
  tt.row = -1;
  tt.choPhep = false;
  const lan = ++tt.lanTai;
  pvpoVe(tt, "ds");
  pvpoChu(tt, "xem", "Chưa chọn video");
  pvpoVe(tt, "nut");
  if (folderId === null) return;
  const path = Object.prototype.hasOwnProperty.call(f, "path") ? f.path : "";
  const source = Object.prototype.hasOwnProperty.call(f, "source") ? f.source : "local";
  if (!(source === "local" && path)) { pvpoChu(tt, "info", "Folder rỗng hoặc nguồn không hỗ trợ"); return; }
  pvpoChu(tt, "tt", "Đang tải videos...");
  let r;
  try { r = await pvApi.dsVideoFolder(folderId); }
  catch (e) {
    if (!pvConSong(tt.phien) || (e && e.roiTrang) || lan !== tt.lanTai) return;
    pvpoChu(tt, "tt", `❌ Lỗi: ${e && e.message ? e.message : e}`);
    pvpoChu(tt, "info", `Folder: ${path}`);
    return;
  }
  if (!pvConSong(tt.phien) || lan !== tt.lanTai) return; // folder đã đổi trong lúc liệt kê
  const ds = pvpoDsVideo(r);
  if (ds === null) {
    pvpoChu(tt, "tt", "");
    pvpoChu(tt, "info", "Folder rỗng hoặc nguồn không hỗ trợ");
    return;
  }
  tt.videos = ds;
  pvpoVe(tt, "ds");
  pvpoChu(tt, "tt", `Tìm thấy ${ds.length} video`);
  pvpoChu(tt, "info", `Folder: ${path}`);
}

// _on_video_selected (post.py:266-277).
function pvpoChonVideo(tt, i) {
  if (!Number.isInteger(i) || i < 0 || i >= tt.videos.length) return;
  tt.row = i;
  pvpoVe(tt, "ds");
  pvpoChu(tt, "xem", `🎬 ${tt.videos[i].name}`);
  tt.choPhep = true;
  pvpoVe(tt, "nut");
  if (tt.folderId) {
    const f = tt.folders.find((x) => x.id === tt.folderId);
    if (f && f.caption && !tt.caption) {
      tt.caption = String(f.caption);
      pvpoDatO(tt, "caption", tt.caption);
    }
  }
}

// QMessageBox.question (Yes / No) → Promise<boolean>.
function pvpoHoi(tieuDe, cau) {
  const h = pvHop({ tieuDe, html: `<p class="pv-cau"><span class="pv-ic" aria-hidden="true">❓</span> ${esc(cau)}</p>`,
    nut: [{ ma: "yes", chu: "Yes", chinh: true }, { ma: "no", chu: "No" }] });
  return h.cho.then((v) => v === "yes");
}

// _post_video (post.py:279-318). Khoá nút TRƯỚC mọi await (chống đăng trùng lên TikTok thật); lớp L: pvGoi nhận 202 rồi pvCho.
async function pvpoDang(tt) {
  if (tt.dang) return;
  if (!tt.folderId) { pvThongBao("Chưa chọn", "Vui lòng chọn folder trước.", "warning"); return; }
  const idx = tt.row;
  if (idx < 0 || idx >= tt.videos.length) { pvThongBao("Chưa chọn", "Vui lòng chọn video.", "warning"); return; }
  const video = tt.videos[idx];
  const caption = tt.caption.trim();
  if (!caption) { pvThongBao("Thiếu caption", "Vui lòng nhập caption.", "warning"); return; }
  const hien = tt.hien, fc = tt.fc.trim(), nhap = tt.nhap, folderId = tt.folderId;
  tt.dang = { hoi: true };
  pvpoVe(tt, "nut");
  const co = await pvpoHoi("Xác nhận đăng", pvpoCauXacNhan(video.name, caption, hien, nhap));
  if (!pvConSong(tt.phien)) return;
  if (!co) { tt.dang = null; pvpoVe(tt, "nut"); return; }
  const lenh = { video: video.name, folderId, tep: pvpoTenTep(video.path), daGan: false };
  tt.dang = lenh;
  tt.choPhep = false;
  pvpoChu(tt, "tt", "⏳ Đang đăng video...");
  pvpoVe(tt, "nut");
  let res;
  try { res = await pvApi.postVideoDirect(folderId, video.path, caption, hien, fc, nhap); }
  catch (e) { await pvpoLoi(tt, lenh, e); return; }
  pvpoXong(tt, lenh, res);
}

// Mở trang khi máy nhà còn lệnh đăng (§3.3): khoá nút, hiện "Đang đăng <video>…", hỏi tiếp; xong hiện kết quả như khi bấm.
function pvpoGan(tt, l, daGan = true) {
  const lenh = { video: l.video, daGan };
  tt.dang = lenh;
  pvpoVe(tt, "nut");
  pvCho(l.cho, l.toiDa, tt.phien).then((res) => pvpoXong(tt, lenh, res), (e) => pvpoLoi(tt, lenh, e));
}

// _on_post_success (post.py:320-327).
function pvpoXong(tt, lenh, res) {
  if (!pvConSong(tt.phien) || tt.dang !== lenh) return;
  const msg = (k) => { const m = res && typeof res === "object" ? res.message : undefined; return m === undefined || m === null ? k : String(m); };
  tt.dang = null;
  tt.choPhep = true;
  pvpoChu(tt, "tt", `✅ ${msg("Đăng thành công!")}`);
  pvpoVe(tt, "nut");
  tt.caption = ""; tt.fc = ""; tt.nhap = false;
  pvpoDatO(tt, "caption", "");
  pvpoDatO(tt, "fc", "");
  pvpoVe(tt, "nhap");
  pvThongBao("Thành công", msg("Video đã được đăng!"), "info");
}

// _on_post_error (post.py:329-332). Lỗi tạm (mạng / 5xx cổng) có thể là lệnh vẫn chạy ở máy nhà → hỏi dangChay 1 lần: còn chạy thì
// gắn lại và tiếp tục khoá; KHÔNG gửi lại. Chỉ gắn lệnh cùng folder_id + tên video với lệnh vừa gửi (lệnh của tab khác không phải
// của mình). Không còn chạy / không khớp thì báo lỗi kèm câu "CÓ THỂ đã chạy".
async function pvpoLoi(tt, lenh, e) {
  if (!pvConSong(tt.phien) || (e && e.roiTrang) || tt.dang !== lenh) return;
  const tam = !!(e && e.tam) && e.status !== 429;
  if (tam && !lenh.daGan) {
    lenh.daGan = true;
    let l = null;
    try { l = pvpoLenhKhop(await pvApi.dangChay(), lenh.folderId, lenh.tep); } catch (e2) { /* không hỏi được: báo lỗi bên dưới */ }
    if (!pvConSong(tt.phien) || tt.dang !== lenh) return;
    if (l) { pvpoGan(tt, { ...l, video: l.video || lenh.video }, true); return; }
  }
  let msg = e && e.message ? e.message : String(e);
  if (tam && !/CÓ THỂ/.test(msg)) msg += `\n${PVPO_CO_THE}`;
  tt.dang = null;
  tt.choPhep = true;
  pvpoChu(tt, "tt", `❌ Lỗi: ${msg}`);
  pvpoVe(tt, "nut");
  pvThongBao("Lỗi", `Không thể đăng video:\n${msg}`, "critical");
}
