// Trang "Hôm nay" (#/) — W-7: một màn cho người không chuyên biết hôm nay cần làm gì.
// Dùng chung với app.js/viec.js/loi.js (script thường, cùng phạm vi toàn cục): $, esc, api, loadList, state, laChu, anhBia,
// trangThai, needLogin, phienCT (app.js); nhomViec, demCanBan, nutHanhDong (viec.js); loiLoaiViec, cauViec, changHtml… (loi.js).
// Chỉ gọi 4 nguồn song song: danh sách SP, danh sách việc, sức khoẻ máy nhà, báo cáo học hôm nay (D15, khối từ hoc.js)
// — KHÔNG gọi theo từng SP (tunnel máy nhà).
// CSP script-src 'self': KHÔNG script inline, KHÔNG thuộc tính on…= — sự kiện gắn bằng addEventListener.
"use strict";

// --- homnay-thuan start ---
// Hàm thuần: không đụng DOM/fetch; dùng esc (app.js), nhomViec (viec.js) và hàm lời thường (loi.js) lúc gọi.
const HN_TOI_DA = 5;      // mỗi khối việc hiện 5 mục đầu, còn lại mở bằng "Xem tất cả (N)"
const HN_SP_TOI_DA = 20;  // danh sách SP hiện 20 dòng đầu
// Trần gioi_han của GET /viec: tools/runner/api.py GIOI_HAN_TOI_DA = 500 (Worker chuyển nguyên query gioi_han).
// Giữ khớp chuỗi literal trong renderHomNay: api("viec?gioi_han=500").
const HN_GIOI_HAN_VIEC = 500;
const RE_UID_HN = /^\d{19}$/;
const RE_ID_VIEC_HN = /^j\d{14}[a-z0-9]{4}$/;
const FMT_NGAY_VN = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh", year: "numeric", month: "2-digit", day: "2-digit" });

// Lỗi khi tải: 401 (hết phiên) / 403 (không quyền) là vĩnh viễn; còn lại (mạng, máy nhà tắt, 5xx) là tạm.
function loaiLoiTai(err) {
  const st = err && typeof err === "object" ? err.status : 0;
  return st === 401 ? "dang_nhap" : st === 403 ? "quyen" : "tam";
}
const LOI_TAI_HN = {
  dang_nhap: "Hết phiên đăng nhập — đăng nhập lại để xem",
  quyen: "Tài khoản này không xem được phần này",
};
const cauLoiTai = (loai, tam) => (Object.prototype.hasOwnProperty.call(LOI_TAI_HN, loai) ? LOI_TAI_HN[loai] : tam);

// "YYYY-MM-DD" theo giờ Việt Nam.
function ngayVn(ms) {
  return Number.isFinite(ms) ? FMT_NGAY_VN.format(new Date(ms)) : "";
}
function ngayCuaViec(v) {
  const s = (v && (v.ket_thuc_luc || v.cap_nhat_luc)) || "";
  const t = typeof s === "string" ? Date.parse(s) : NaN;
  return Number.isFinite(t) ? ngayVn(t) : "";
}
function uidCuaViecHn(v) {
  let ts = v && v.tham_so;
  if (typeof ts === "string") { try { ts = JSON.parse(ts); } catch { ts = null; } }
  return ts && typeof ts === "object" && typeof ts.uid === "string" && RE_UID_HN.test(ts.uid) ? ts.uid : "";
}
const linkViecHn = (v) => (v && typeof v.id === "string" && RE_ID_VIEC_HN.test(v.id) ? `#/viec/${v.id}` : "");
const gioPhutHn = (s) => (typeof s === "string" && /^\d{4}-\d\d-\d\dT\d\d:\d\d/.test(s) ? s.slice(11, 16) : "");

// Danh sách việc → 3 khối: Cần bạn (chờ duyệt trước, rồi câu hỏi), Máy đang làm (chạy rồi chờ), Xong hôm nay (xong/lỗi trong ngày VN).
function duLieuHomNay(ds, nowMs) {
  const g = nhomViec(ds);
  const uu = (v) => (v.trang_thai === "cho_duyet" ? 0 : v.trang_thai === "can_tra_loi" ? 1 : 2);
  const canBan = g.can_ban.map((v, i) => [v, i]).sort((a, b) => uu(a[0]) - uu(b[0]) || a[1] - b[1]).map((x) => x[0]);
  const hn = ngayVn(nowMs);
  const xongHomNay = g.gan_day.filter((v) => (v.trang_thai === "xong" || v.trang_thai === "loi") && ngayCuaViec(v) === hn);
  // Việc lỗi đã có lần chạy MỚI HƠN (tao_luc) cùng loại, cùng uid mà xong → không còn là trục trặc.
  const daChayLai = new Set();
  for (const v of xongHomNay) {
    if (v.trang_thai !== "loi") continue;
    const uid = uidCuaViecHn(v), moc = String(v.tao_luc || "");
    if (g.gan_day.some((w) => w.trang_thai === "xong" && w.loai === v.loai && uidCuaViecHn(w) === uid && String(w.tao_luc || "") > moc)) daChayLai.add(v);
  }
  return { canBan, mayLam: g.dang_chay.concat(g.dang_cho), xongHomNay, daChayLai };
}

// Việc của 1 SP (khớp tham_so.uid). loi = lần chạy MỚI NHẤT của một loại việc bị lỗi (lỗi cũ đã chạy lại thì thôi).
// Việc đã huỷ không tính là "lần chạy mới hơn": lỗi rồi huỷ thì trục trặc vẫn còn.
function viecCuaSp(ds, uid) {
  const rong = { loi: null, canBan: null, dangChay: null, choMay: null };
  if (typeof uid !== "string" || !RE_UID_HN.test(uid)) return rong;
  const cua = (Array.isArray(ds) ? ds : []).filter((v) => v && typeof v === "object" && uidCuaViecHn(v) === uid)
    .sort((a, b) => String(b.tao_luc || "").localeCompare(String(a.tao_luc || "")));
  const daThay = new Set();
  let loi = null;
  for (const v of cua) {
    if (v.trang_thai === "huy" || daThay.has(v.loai)) continue;
    daThay.add(v.loai);
    if (v.trang_thai === "loi" && !loi) loi = v;
  }
  const tim = (tt) => cua.find((v) => v.trang_thai === tt) || null;
  return { loi, canBan: tim("cho_duyet") || tim("can_tra_loi"), dangChay: tim("dang_chay"), choMay: tim("cho") };
}

// P-32: việc tay xử lý được ngay tại Hôm nay (nút "Thử lại" = tra-loi da_lam_xong, "Bỏ việc này" = huy), cùng điều kiện
// nút trả lời không mật khẩu của trang Việc (viec.js ~1214): can_tra_loi, cau_hoi.loai viec_tay, KHÔNG tốn tiền, KHÔNG phiên sống.
function viecTayHn(v) {
  if (!v || typeof v !== "object" || v.trang_thai !== "can_tra_loi" || v.phien_song === true) return false;
  if (typeof v.id !== "string" || !RE_ID_VIEC_HN.test(v.id) || LOAI_TON_TIEN.includes(v.loai)) return false;
  const c = docJsonViec(v.cau_hoi);
  return !!c && typeof c === "object" && c.loai === "viec_tay";
}
// Việc phân tích đang chờ mà SP đã qua chặng Chuẩn bị (đã có bộ cảnh quay) → việc thừa, gợi ý bỏ. ttSp lạ → không đoán.
const viecCuHn = (v, ttSp) => !!v && v.loai === "phan_tich_uid" && ttSp !== "cho" && changTheoTrangThai(ttSp) > 0;
const CAU_VIEC_CU_HN = "Sản phẩm này đã có bộ cảnh quay — việc phân tích đang chờ là việc cũ, có thể bỏ.";
// Nút tại chỗ (đã kiểm viecTayHn). Việc cũ: chỉ "Bỏ việc cũ" — Thử lại sẽ chạy lại phân tích thừa.
function nutViecTayHn(v, cu) {
  const id = esc(v.id);
  return cu
    ? `<button type="button" class="btn sm" data-hn-huy="${id}" data-hn-cu="1">Bỏ việc cũ</button>`
    : `<button type="button" class="btn sm" data-hn-tl="${id}">Thử lại</button><button type="button" class="btn ghost sm" data-hn-huy="${id}">Bỏ việc này</button>`;
}

// Ô "Bắt đầu sản phẩm mới" + dải "Cách làm" 4 bước (tĩnh, không dữ liệu động). Form gắn onAdd (app.js) trong renderHomNay.
// Nhãn khớp nút thật: gạt "Đã quay …" (trang SP), nút khối "Bước tiếp theo" (vd "Làm video"), "Duyệt & chạy (tối đa …)",
// bước 4: video duyệt lúc tạo, lên lịch ở Poster V2 (2026-11-19 gỡ trang Duyệt video + Đăng bài).
function batDauHnHtml() {
  return `<section class="hn-bat-dau">
      <p class="hn-bd-cau"><b>Bắt đầu sản phẩm mới:</b> dán link sản phẩm TikTok Shop vào ô dưới rồi bấm Bắt đầu.</p>
      <form class="add hn-add" id="form-hn-add">
        <input id="in-hn-link" placeholder="Dán link sản phẩm TikTok Shop…" autocomplete="off" aria-label="Link sản phẩm TikTok Shop">
        <button class="btn" type="submit">Bắt đầu</button>
      </form>
      <p id="hn-add-msg" class="add-msg" role="status"></p>
      <div class="small muted hn-cach"><b>Cách làm:</b>
        <ol>
          <li>Dán link → máy nhà tự làm bộ cảnh quay (danh sách cảnh cần quay).</li>
          <li>Bạn quay theo danh sách, xong gạt "Đã quay" trong trang sản phẩm.</li>
          <li>Mở sản phẩm, bấm nút ở khối "Bước tiếp theo" (vd Làm video), xem chi phí tối đa rồi duyệt.</li>
          <li>Video được duyệt ngay lúc tạo; lên lịch đăng ở Poster V2.</li>
        </ol>
      </div>
    </section>`;
}

// 1 dòng SP: chặng (chữ thường) + câu trạng thái (chỉ từ dữ liệu chắc chắn) + ĐÚNG 1 chỗ hành động.
// Nút theo ưu tiên: chờ duyệt / cần duyệt lại → câu hỏi trả lời được → trục trặc → máy đang làm → nút theo chặng (#/sp/<uid>).
// Câu trạng thái đi cùng nút để dòng không nói một đằng, nút làm một nẻo. Việc không có id hợp lệ → về trang Việc.
// P-32: việc tay xử lý được tại chỗ → `tay: {v, cu}` (spHomNayHtml vẽ nút Thử lại / Bỏ việc thay cho link).
function dongSpHomNay(sp, vs) {
  const x = sp && typeof sp === "object" ? sp : {};
  const v = vs && typeof vs === "object" ? vs : {};
  const tt = x.trang_thai;
  const l = loiTrangThaiSp(tt);
  const chang = changTheoTrangThai(tt);
  const toiViec = (w, nhan) => ({ nhan, href: linkViecHn(w) || "#/viec" });
  if (v.canBan && viecTayHn(v.canBan)) {
    const cu = viecCuHn(v.canBan, tt);
    return { chang, lop: "hn-cho-ban", cau: cu ? CAU_VIEC_CU_HN : `Đang chờ bạn: ${cauViec(v.canBan)}`,
      nut: toiViec(v.canBan, nutViec(v.canBan)), tay: { v: v.canBan, cu } };
  }
  if (v.canBan) return { chang, lop: "hn-cho-ban", cau: `Đang chờ bạn: ${cauViec(v.canBan)}`, nut: toiViec(v.canBan, nutViec(v.canBan)) };
  if (v.loi) return { chang, lop: "hn-loi", cau: "Có trục trặc — bấm để xem", nut: toiViec(v.loi, "Xem trục trặc") };
  if (v.dangChay) return { chang, lop: "hn-dang", cau: `Máy đang làm: ${loiLoaiViec(v.dangChay.loai)}`, nut: toiViec(v.dangChay, "Xem máy đang làm") };
  const nut = { nhan: l.nut, href: `#/sp/${encodeURIComponent(String(x.id ?? ""))}` };
  if (v.choMay) return { chang, lop: "hn-dang", cau: `Máy sẽ làm: ${loiLoaiViec(v.choMay.loai)} (đang xếp hàng)`, nut };
  return { chang, lop: "", cau: l.cau, nut };
}
const UU_SP_HN = { "hn-loi": 0, "hn-cho-ban": 1, "hn-dang": 2 };

// Ô tìm sản phẩm ở trang Hôm nay: cùng trường với ô tìm trang Kho (app.js renderList), thêm bỏ dấu tiếng Việt
// để gõ "vi da" vẫn ra "Ví da". Chuỗi tìm rỗng/chỉ khoảng trắng → khớp mọi SP.
const boDauHn = (x) => String(x == null ? "" : x).normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[đĐ]/g, "d").toLowerCase();
function khopTimHn(sp, tim) {
  const q = boDauHn(tim).trim();
  if (!q) return true;
  const x = sp && typeof sp === "object" ? sp : {};
  return boDauHn([x.ten, x.uid, x.id, x.link, x.shop, x.them_boi].join(" ")).includes(q);
}

function spHomNayHtml(sp, vs, anh) {
  const x = sp && typeof sp === "object" ? sp : {};
  const d = dongSpHomNay(x, vs);
  const ten = x.ten || x.link || "(chưa có tên — chờ máy nhà phân tích)";
  const tt = `<div class="hn-tt ${d.lop}">${esc(d.cau)}</div>`;
  // P-32: tên + ảnh là link mở trang SP (ảnh bỏ khỏi thứ tự Tab để không đọc trùng); chặng là chữ thường, không phải ô.
  const id = x.id == null ? "" : String(x.id);
  const lk = id ? esc(`#/sp/${encodeURIComponent(id)}`) : "";
  const anhHtml = anh ? `<img class="hn-anh" src="${esc(anh)}" referrerpolicy="no-referrer" loading="lazy" alt="">` : `<div class="hn-anh"></div>`;
  const tenHtml = lk ? `<a class="hn-sp-ten" href="${lk}">${esc(ten)}</a>` : `<div class="hn-sp-ten">${esc(ten)}</div>`;
  const hanhDong = d.tay
    ? `<div class="row hn-sp-nut hn-tay">${nutViecTayHn(d.tay.v, d.tay.cu)}</div>`
    : `<a class="btn sm hn-sp-nut" href="${esc(d.nut.href)}">${esc(d.nut.nhan)}</a>`;
  return `<div class="hn-sp">
      ${lk ? `<a class="hn-anh-lk" href="${lk}" tabindex="-1" aria-hidden="true">${anhHtml}</a>` : anhHtml}
      <div class="hn-sp-than">${tenHtml}<div class="small muted hn-chang">${esc(changChu(d.chang))}</div>${tt}</div>
      ${hanhDong}
    </div>`;
}

// Khối có tiêu đề "Tên (N)"; quá `toiDa` mục → phần còn lại ẩn tại chỗ + nút "Xem tất cả (N)" (không mất mục nào).
// ghiChu: câu lời thường (chưa esc) hiện ngay dưới tiêu đề, kèm link trang Việc.
function khoiHn(ma, tieuDe, muc, toiDa, rong, ghiChu) {
  const n = muc.length;
  const ds = muc.map((h, i) => (i < toiDa ? `<div class="hn-muc">${h}</div>` : `<div class="hn-muc hn-an" hidden>${h}</div>`)).join("");
  return `<section class="hn-khoi hn-${ma}"><h2 class="hn-tieu-de">${esc(tieuDe)} (${n})</h2>
      ${ghiChu ? ghiChuHn(ghiChu) : ""}
      ${n ? `<div class="hn-ds">${ds}</div>` : `<p class="small muted">${esc(rong)}</p>`}
      ${n > toiDa ? `<button type="button" class="btn ghost sm hn-mo" data-hn-mo="${esc(ma)}">Xem tất cả (${n})</button>` : ""}
    </section>`;
}
const ghiChuHn = (cau) => `<p class="small muted hn-ghi-chu"><a href="#/viec">${esc(cau)}</a></p>`;
// Số việc cần bạn (can_tra_loi + cho_duyet) toàn kho từ `dem` (nếu phản hồi có) trừ số đang hiện; sai mẫu → 0.
function soCanBanChuaHien(dem, dangHien) {
  if (typeof demCanBan !== "function") return 0;
  const n = demCanBan(dem) - (Number.isInteger(dangHien) ? dangHien : 0);
  return n > 0 ? n : 0;
}
function khoiLoiHn(ma, tieuDe, cau) {
  return `<section class="hn-khoi hn-${ma}"><h2 class="hn-tieu-de">${esc(tieuDe)}</h2><p class="hn-bao">${esc(cau)}</p></section>`;
}

function skHn(sk) {
  if (!sk || !sk.ok) {
    const cau = cauLoiTai(sk && sk.loai, "Chưa kiểm được máy nhà — mạng chập chờn hoặc máy nhà đang tắt");
    return `<a class="hn-sk tat" href="#/suc-khoe">${esc(cau)}</a>`;
  }
  const l = loiSucKhoe(sk.d);
  return `<a class="hn-sk ${l.tat ? "tat" : "ok"}" href="#/suc-khoe">${esc(l.cau)}</a>`;
}

// t: {chu, nowMs, sk:{ok,d}|{ok:false,loai}, viec:{ok,ds}|{ok:false,loai}, sp:{ok,ds}|{ok:false,loai}, anh: sp → url ảnh bìa}
function homNayHtml(t) {
  const x = t && typeof t === "object" ? t : {};
  const anh = typeof x.anh === "function" ? x.anh : () => "";
  const dsSp = x.sp && x.sp.ok && Array.isArray(x.sp.ds) ? x.sp.ds : [];
  const coUid = dsSp.filter((s) => s && RE_UID_HN.test(String(s.uid || "")));
  const tenTheoUid = new Map(coUid.map((s) => [String(s.uid), String(s.ten || s.link || "")]));
  const ttTheoUid = new Map(coUid.map((s) => [String(s.uid), s.trang_thai]));
  const dsViec = x.chu && x.viec && x.viec.ok && Array.isArray(x.viec.ds) ? x.viec.ds : [];
  const ra = [];
  if (x.chu) {
    ra.push(skHn(x.sk));
    if (x.viec && x.viec.ok) {
      const g = duLieuHomNay(dsViec, x.nowMs);
      const tenSp = (v) => { const ten = tenTheoUid.get(uidCuaViecHn(v)); return ten ? `<div class="hn-muc-sp">${esc(ten)}</div>` : ""; };
      const nutMo = (v, nhan) => { const l = linkViecHn(v); return `<a class="btn sm" href="${esc(l || "#/viec")}">${esc(nhan)}</a>`; };
      // Runner trả tối đa HN_GIOI_HAN_VIEC việc mới nhất: đủ trần → có thể còn việc cũ hơn không hiện ở đây.
      if (dsViec.length >= HN_GIOI_HAN_VIEC) ra.push(ghiChuHn("Có thể còn việc cũ hơn — xem trang Việc"));
      const conLai = soCanBanChuaHien(x.viec.dem, g.canBan.length);
      ra.push(khoiHn("can-ban", "Cần bạn", g.canBan.map((v) => {
        if (!viecTayHn(v)) return `${tenSp(v)}<div class="hn-muc-cau">${esc(cauViec(v))}</div>${nutMo(v, nutViec(v))}`;
        const cu = viecCuHn(v, ttTheoUid.get(uidCuaViecHn(v))); // P-32: việc tay bấm được tại chỗ
        return `${tenSp(v)}<div class="hn-muc-cau">${esc(cu ? CAU_VIEC_CU_HN : cauViec(v))}</div>${nutViecTayHn(v, cu)}`;
      }), HN_TOI_DA, "Không có gì cần bạn lúc này.",
        conLai ? `Còn ${conLai} việc cần bạn chưa hiện — xem trang Việc` : ""));
      ra.push(khoiHn("may-lam", "Máy đang làm", g.mayLam.map((v) => {
        const tg = v.trang_thai === "dang_chay" ? thoiGianChay(v.bat_dau_luc, x.nowMs) : "đang xếp hàng";
        return `${tenSp(v)}<a class="hn-muc-cau" href="${esc(linkViecHn(v) || "#/viec")}">${esc(loiLoaiViec(v.loai))}${tg ? ` · <span class="muted">${esc(tg)}</span>` : ""}</a>`;
      }), HN_TOI_DA, "Máy nhà đang rảnh."));
      ra.push(khoiHn("xong", "Xong hôm nay", g.xongHomNay.map((v) => {
        const l = esc(linkViecHn(v) || "#/viec");
        if (v.trang_thai === "loi" && g.daChayLai.has(v)) return `${tenSp(v)}<a class="hn-muc-cau muted" href="${l}">Lỗi, đã chạy lại xong · ${esc(loiLoaiViec(v.loai))}</a>`;
        if (v.trang_thai === "loi") return `${tenSp(v)}<a class="hn-muc-cau" href="${l}"><span class="hn-loi">Có trục trặc — bấm để xem</span> · ${esc(loiLoaiViec(v.loai))}</a>`;
        const gp = gioPhutHn(v.ket_thuc_luc);
        return `${tenSp(v)}<a class="hn-muc-cau" href="${l}">✓ ${esc(loiLoaiViec(v.loai))}${gp ? ` <span class="muted">lúc ${esc(gp)}</span>` : ""}</a>`;
      }), HN_TOI_DA, "Hôm nay chưa có việc nào xong."));
    } else {
      ra.push(khoiLoiHn("viec", "Việc máy nhà", cauLoiTai(x.viec && x.viec.loai, "Chưa tải được việc — máy nhà có thể đang tắt")));
    }
    // D15 §3.9: khối "📈 Học hôm nay" (hoc.js, chỉ chủ kho). Thiếu t.hoc / nguồn lỗi / chưa nạp hoc.js → không vẽ gì.
    if (x.hoc && x.hoc.ok && typeof hcKhoiHomNayHtml === "function") {
      const k = hcKhoiHomNayHtml(x.hoc.d, x.nowMs);
      if (k) ra.push(k);
    }
  }
  if (x.sp && x.sp.ok) {
    const viecOk = !x.chu || (x.viec && x.viec.ok);
    const tim = typeof x.tim === "string" ? x.tim.trim() : "";
    const dong = dsSp.filter((s) => s && typeof s === "object" && khopTimHn(s, tim)).map((s, i) => {
      const vs = viecCuaSp(dsViec, String(s.uid || ""));
      const lop = dongSpHomNay(s, vs).lop;
      return { s, vs, i, uu: Object.prototype.hasOwnProperty.call(UU_SP_HN, lop) ? UU_SP_HN[lop] : 3 };
    }).sort((a, b) => a.uu - b.uu || a.i - b.i);
    // Đang tìm → hiện hết kết quả khớp (không cắt 20 dòng), câu rỗng nói rõ là không khớp chứ không phải kho trống.
    ra.push(khoiHn("ds-sp", tim ? "Sản phẩm khớp tìm kiếm" : "Sản phẩm", dong.map((d) => spHomNayHtml(d.s, d.vs, anh(d.s))),
      tim ? dong.length : HN_SP_TOI_DA,
      tim ? `Không thấy sản phẩm nào khớp "${tim}" — thử tên khác, UID 19 số hoặc tên shop.` : "Kho trống — dán link đầu tiên ở ô Bắt đầu phía trên.")
      .replace("</h2>", `</h2>${x.chu && !viecOk ? `<p class="small muted">Chưa tải được việc máy nhà — trạng thái dưới đây chỉ theo kho.</p>` : ""}`));
  } else {
    ra.push(khoiLoiHn("ds-sp", "Sản phẩm", cauLoiTai(x.sp && x.sp.loai, "Chưa tải được danh sách sản phẩm — kiểm mạng rồi bấm Tải lại")));
  }
  return ra.join("\n");
}
// --- homnay-thuan end ---

// ---------- phần có DOM ----------
let hnDangTai = false; // chặn bấm "Tải lại" liên tiếp (đặt TRƯỚC await)
let hnViecDs = new Map(); // id → việc của lần tải đang hiện (bamViecHn kiểm lại điều kiện + lấy ma_cau_hoi từ đây)
const hnDangGui = new Set(); // id việc đang gửi tra-loi/huy từ trang Hôm nay (chống bấm đúp)
let hnTim = ""; // chữ đang gõ ở ô tìm SP — giữ qua "Tải lại" / quay lại trang
let hnT = null; // dữ liệu lần tải gần nhất: gõ tìm chỉ vẽ lại #hn-nd từ đây, KHÔNG gọi lại máy nhà

function veNdHn() {
  const nd = $("#hn-nd");
  if (!nd || !hnT) return;
  nd.innerHTML = homNayHtml({ ...hnT, tim: hnTim });
  // Việc đang gửi tra-loi/huy (bấm trước lúc vẽ lại) → nút mới vẽ của việc đó vẫn khoá, chống gửi đúp.
  if (hnDangGui.size) nd.querySelectorAll("[data-hn-tl], [data-hn-huy]").forEach((n) => {
    if (hnDangGui.has(n.dataset.hnTl || n.dataset.hnHuy)) n.disabled = true;
  });
}

async function renderHomNay() {
  const phien = ++phienCT; // mở trang khác sau đó sẽ tăng tiếp → kết quả về muộn của lượt này bị bỏ, không vẽ đè
  const chu = laChu();
  hnDangTai = true;
  $("#app").innerHTML = `<div class="hn" id="hn">
      <div class="row hn-dau"><h1 class="hn-h1">Hôm nay</h1><button type="button" class="btn ghost sm" id="hn-tai-lai" disabled>↻ Tải lại</button></div>
      ${batDauHnHtml()}
      <input class="search hn-tim" id="hn-tim" type="search" placeholder="Tìm sản phẩm theo tên, UID, shop…" value="${esc(hnTim)}" autocomplete="off" aria-label="Tìm sản phẩm theo tên, UID, shop">
      <div id="hn-nd"><p class="muted">Đang tải…</p></div>
    </div>`;
  $("#form-hn-add").addEventListener("submit", onAdd); // app.js: lưu xong / trùng → #/sp/<id>
  // Ô tìm nằm NGOÀI #hn-nd nên vẽ lại danh sách không làm mất con trỏ đang gõ.
  $("#hn-tim").addEventListener("input", (e) => { hnTim = e.target.value; veNdHn(); });
  $("#hn").addEventListener("click", (e) => {
    const nv = e.target.closest("[data-hn-tl], [data-hn-huy]");
    if (nv) { bamViecHn(nv); return; }
    const b = e.target.closest("[data-hn-mo]");
    if (b) {
      const k = b.closest(".hn-khoi");
      if (k) k.querySelectorAll(".hn-an").forEach((el) => { el.hidden = false; el.classList.remove("hn-an"); });
      b.remove();
    } else if (e.target.closest("#hn-tai-lai") && !hnDangTai) renderHomNay();
  });
  let ra;
  try {
    // 4 nguồn song song; nguồn nào lỗi thì chỉ khối đó báo (nguồn học lỗi: không vẽ khối học), khối khác vẫn hiện.
    ra = await Promise.allSettled([loadList(), chu ? api("viec?gioi_han=500") : null, chu ? api("suc-khoe") : null,
      chu ? api("hoc/bao-cao") : null]);
  } finally { if (phien === phienCT) hnDangTai = false; }
  if (phien !== phienCT) return; // đã sang trang khác
  const [a, b, c, d] = ra;
  const loai = (r) => loaiLoiTai(r.reason);
  if ([a, b, c, d].some((r) => r.status === "rejected" && loai(r) === "dang_nhap")) needLogin(); // 401: mở lại hộp đăng nhập
  const t = {
    chu, nowMs: Date.now(), anh: anhBia,
    sp: a.status === "fulfilled" ? { ok: true, ds: state.list.map((x) => ({ ...x, trang_thai: x.trang_thai || trangThai(x) })) } : { ok: false, loai: loai(a) },
    viec: b.status === "fulfilled"
      ? { ok: true, ds: b.value && Array.isArray(b.value.viec) ? b.value.viec : [], dem: b.value && b.value.dem } // dem: bộ đếm toàn kho nếu runner trả kèm
      : { ok: false, loai: loai(b) },
    sk: c.status === "fulfilled" ? { ok: true, d: c.value } : { ok: false, loai: loai(c) },
    // D15: báo cáo học hôm nay (404 "chưa có lần học nào", 503 chưa bật, lỗi mạng → ok:false → không vẽ khối)
    hoc: chu && d.status === "fulfilled" && d.value && typeof d.value === "object" ? { ok: true, d: d.value } : { ok: false, loai: loai(d) },
  };
  hnViecDs = new Map(t.viec.ok ? t.viec.ds.filter((v) => v && typeof v === "object" && typeof v.id === "string").map((v) => [v.id, v]) : []);
  hnT = t;
  veNdHn();
  const nut = $("#hn-tai-lai");
  if (nut) nut.disabled = false;
}

// P-32: nút "Thử lại" (data-hn-tl) / "Bỏ việc này"/"Bỏ việc cũ" (data-hn-huy) — CHỈ gọi khi người dùng bấm.
// Kiểm id + điều kiện viecTayHn trên dữ liệu đang hiện → (huỷ: confirm) → khoá nút TRƯỚC await → gửi → toast → vẽ lại trang.
async function bamViecHn(b) {
  const huy = b.hasAttribute("data-hn-huy");
  const id = huy ? b.dataset.hnHuy : b.dataset.hnTl;
  if (b.disabled || typeof id !== "string" || !RE_ID_VIEC_HN.test(id) || hnDangGui.has(id)) return;
  const v = hnViecDs.get(id);
  if (!viecTayHn(v)) { toast("Việc này không còn chờ bạn — đang tải lại trang."); if (!hnDangTai) renderHomNay(); return; }
  if (huy && !confirm(b.dataset.hnCu
    ? "Bỏ việc phân tích cũ này? Bộ cảnh quay đã có vẫn giữ nguyên."
    : "Bỏ việc này? Máy nhà sẽ không làm tiếp việc này.")) return;
  const phien = phienCT;
  hnDangGui.add(id); // khoá TRƯỚC await: mọi nút của việc này (dòng SP + khối Cần bạn)
  document.querySelectorAll("#hn [data-hn-tl], #hn [data-hn-huy]").forEach((n) => {
    if (n.dataset.hnTl === id || n.dataset.hnHuy === id) n.disabled = true;
  });
  const act = huy ? "huy" : "tra-loi";
  const ma = huy ? "" : maCauHoi(v);
  const body = huy ? {} : ma ? { tra_loi: "da_lam_xong", ma_cau_hoi: ma } : { tra_loi: "da_lam_xong" };
  try {
    const r = await api(`viec/${id}/${act}`, body);
    if (r.status === 409) toast(huy ? "⚠ Việc này vừa đổi trạng thái nên chưa bỏ được — đã tải lại để bạn xem."
      : "⚠ Việc này vừa thay đổi trên máy nhà — đã tải lại để bạn xem tình trạng mới.");
    else toast(huy ? "Đã bỏ việc này." : "✓ Đã báo máy nhà thử lại — việc sẽ chạy tiếp.");
  } catch (err) {
    // 401: hàm gọi API của app.js đã mở hộp đăng nhập; không đưa chuỗi lỗi kỹ thuật lên toast
    toast(err && err.status === 401 ? "Hết phiên đăng nhập — đăng nhập lại rồi bấm lại."
      : "⚠ Chưa gửi được — mạng chập chờn hoặc máy nhà đang tắt. Thử lại sau ít phút.");
  } finally {
    hnDangGui.delete(id);
  }
  if (phien === phienCT && !hnDangTai && auth.on) renderHomNay(); // vẫn đang ở trang Hôm nay (cùng lượt vẽ) → tải lại 3 nguồn
}
