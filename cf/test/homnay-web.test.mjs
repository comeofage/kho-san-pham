// Test W-7 (lượt 30): trang "Hôm nay" (web/homnay.js), từ điển lời thường (web/loi.js), router #/ ↔ #/kho,
// màn duyệt có "Dự kiến/Tối đa", form taovideo tự điền mặc định, trang SP có "Bước tiếp theo". Chạy: node --test cf/test/
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const doc = (p) => readFileSync(new URL(`../../web/${p}`, import.meta.url), "utf8");
const APP = doc("app.js");
const VIEC = doc("viec.js");
const SUA = doc("sua.js");
const LOI = doc("loi.js");
const HN = doc("homnay.js");
const HTML = doc("index.html");
const CSS = doc("style.css");

const dongEsc = APP.split("\n").find((l) => l.startsWith("const esc = "));
assert.ok(dongEsc, "không thấy const esc trong app.js");
const esc = new Function(`${dongEsc}\nreturn esc;`)();
const khoi = (src, ten) => {
  const m = src.match(new RegExp(`// --- ${ten} start ---\\n([\\s\\S]*?)// --- ${ten} end ---`));
  assert.ok(m, `thiếu marker ${ten}`);
  return m[1];
};
// Nạp 3 khối thuần chung một phạm vi (như trình duyệt: cùng phạm vi toàn cục), tiêm esc thật của app.js.
const F = new Function("esc", `"use strict";\n${khoi(LOI, "loi-thuan")}\n${khoi(VIEC, "viec-thuan")}\n${khoi(HN, "homnay-thuan")}
return { CHANG_SP, changTheoTrangThai, changTheoBuoc, changHtml, loiLoaiViec, loiTrangThaiViec, loiTrangThaiSp, cauViec, nutViec, thoiGianChay,
  loiSucKhoe, buocTiepTheo, buocTiepHtml, TEN_LOAI_VIEC, TT_VIEC, nhomViec, khungDuyetHtml, duKienDuyet, toiDaDuyet, seLamRaDuyet, nhanNutDuyet,
  TRAN_PHIEN_TAOVIDEO, formViecSpHtml, duAnATuDong, giaTuInfoSp, thamSoTaovideo, linkLuuLaiSua,
  loaiLoiTai, ngayVn, viecCuaSp, dongSpHomNay, duLieuHomNay, homNayHtml, spHomNayHtml, HN_TOI_DA,
  goiYViec, canDuyetLaiViec, HN_GIOI_HAN_VIEC, loiViecTay, changChu, viecTayHn, batDauHnHtml, LOAI_TON_TIEN, khopTimHn };`)(esc);

const UID = "1729706628656957720";
const UID2 = "1729706628656957721";
const ID = (n) => `j2026111810000${n}abcd`;
const BAN = `<img src=x onerror=alert(1)>`;
const NOW = Date.parse("2026-11-18T15:00:00+07:00");
const V = (x = {}) => ({ id: ID(1), loai: "phan_tich_uid", trang_thai: "xong", tham_so: { uid: UID }, tao_luc: "2026-11-18T09:00:00+07:00", ...x });

// ---------- 1. router + điều hướng ----------
test("router: #/ → Hôm nay, #/kho → danh sách kho (renderList giữ nguyên)", () => {
  const r = APP.slice(APP.indexOf("async function route()"), APP.indexOf("window.addEventListener(\"hashchange\""));
  assert.match(r, /location\.hash === "#\/kho"[\s\S]{0,200}renderList\(\)/);
  assert.match(r, /renderHomNay\(\)/);
  // nhánh mặc định (else cuối) là Hôm nay, không phải renderList
  const cuoi = r.slice(r.lastIndexOf("else"));
  assert.match(cuoi, /renderHomNay/);
  assert.ok(!/renderList/.test(cuoi));
  assert.match(APP, /function renderList\(\)/);
});

test("link 'về kho' trỏ #/kho; logo + 'Để sau' trỏ #/; thanh điều hướng 3 mục giữ huy hiệu", () => {
  for (const [ten, src] of [["app.js", APP], ["viec.js", VIEC]]) {
    for (const m of src.matchAll(/<a[^>]*href="#\/"[^>]*>([^<]*)</g)) assert.ok(!/kho/i.test(m[1]), `${ten}: "${m[1]}" còn trỏ #/`);
    assert.ok(!/href: "#\/", nhan: "Về kho/.test(src), `${ten}: linkLuuLaiSua còn #/`);
  }
  assert.match(APP, /href="#\/kho"[^>]*>← Về kho/);
  assert.match(HTML, /<a href="#\/" class="logo">/);
  const ru = APP.slice(APP.indexOf("function renderUser()"), APP.indexOf("function openLogin()"));
  assert.match(ru, /href="#\/"[^>]*>[^<]*Hôm nay/);
  assert.match(ru, /href="#\/kho"[^>]*>[^<]*Kho sản phẩm/);
  assert.match(ru, /href="#\/viec"[^>]*>[^<]*Việc<span class="huy-hieu" id="viec-hh"/);
  assert.equal((APP.match(/id="viec-hh"/g) || []).length, 1, "huy hiệu chỉ 1 chỗ");
  assert.match(HTML, /<nav[^>]*id="nav"/);
  assert.equal(F.linkLuuLaiSua(null).href, "#/kho");
});

// ---------- 3. từ điển lời thường ----------
test("4 chặng: map đúng trang_thai và bước 8 bước", () => {
  assert.deepEqual(F.CHANG_SP, ["Chuẩn bị", "Quay", "Làm video", "Chấm và đăng"]);
  assert.equal(F.changTheoTrangThai("cho"), 0);
  assert.equal(F.changTheoTrangThai("da_phan_tich"), 1);
  assert.equal(F.changTheoTrangThai("da_quay"), 2);
  assert.equal(F.changTheoTrangThai("da_lam_video"), 3);
  assert.equal(F.changTheoTrangThai("__proto__"), 0);
  assert.equal(F.changTheoTrangThai(undefined), 0);
  for (const [ht, c] of [[1, 0], [2, 0], [3, 1], [4, 2], [5, 2], [6, 2], [7, 3], [8, 3], [0, 3]]) assert.equal(F.changTheoBuoc(ht), c, `bước ${ht}`);
  const h = F.changHtml(2);
  for (const t of F.CHANG_SP) assert.ok(h.includes(t), t);
  assert.match(h, /class="ch ch-hien-tai"[^>]*aria-current="step"[^>]*>[^<]*Làm video/);
  assert.ok(!/xong/i.test(h), "không tô 'xong'");
  assert.ok(!/%/.test(h), "không phần trăm");
});

test("lời thường: loại việc, trạng thái, sức khoẻ — không đổi hằng số cũ", () => {
  assert.equal(F.TEN_LOAI_VIEC.taovideo, "Dựng 2 mẻ video");
  assert.equal(F.TT_VIEC.can_tra_loi, "Cần bạn");
  assert.ok(!/_/.test(F.loiLoaiViec("phan_tich_uid")));
  assert.ok(!/taovideo|uid/i.test(F.loiLoaiViec("taovideo")));
  assert.ok(F.loiLoaiViec("loai_la") && !F.loiLoaiViec("loai_la").includes("<"));
  assert.equal(F.loiLoaiViec("__proto__"), F.loiLoaiViec("loai_la"));
  assert.match(F.loiTrangThaiViec("loi"), /trục trặc/);
  assert.deepEqual(F.loiSucKhoe({ may_nha: false, loi: "x" }), { cau: "Máy nhà đang tắt — việc sẽ chờ", tat: true });
  assert.equal(F.loiSucKhoe(null).tat, true);
  const s = F.loiSucKhoe({ may_nha: true, apps: [{ ma: "muse", ten: "Muse", song: false }, { ma: "poster", ten: "Poster", song: true }] });
  assert.equal(s.tat, false);
  assert.equal(s.cau, "Máy nhà: đang chạy · Muse đang tắt");
  assert.equal(F.thoiGianChay("2026-11-18T14:35:00+07:00", NOW), "đã chạy 25 phút");
  assert.equal(F.thoiGianChay("2026-11-18T12:50:00+07:00", NOW), "đã chạy 2 giờ 10 phút");
  assert.equal(F.thoiGianChay("rác", NOW), "");
  assert.equal(F.nutViec({ trang_thai: "cho_duyet" }), "Xem và duyệt");
  assert.equal(F.nutViec({ trang_thai: "can_tra_loi" }), "Trả lời");
});

// ---------- 2. trang Hôm nay ----------
test("viecCuaSp + dongSpHomNay: có việc lỗi → 'Có trục trặc'; đang chạy → 'Máy đang làm'; không đoán phần trăm", () => {
  const sp = { id: UID, uid: UID, ten: "SP", trang_thai: "da_quay" };
  // lỗi mới nhất của loại đó → trục trặc
  let vs = F.viecCuaSp([V({ id: ID(1), loai: "taovideo", trang_thai: "loi" })], UID);
  let d = F.dongSpHomNay(sp, vs);
  assert.equal(d.lop, "hn-loi");
  assert.equal(d.cau, "Có trục trặc — bấm để xem");
  assert.equal(d.nut.href, `#/viec/${ID(1)}`); // FX-30: dòng trạng thái không còn link — nút duy nhất tới việc lỗi
  // lỗi cũ đã có lần chạy mới hơn cùng loại xong → không còn trục trặc
  vs = F.viecCuaSp([V({ id: ID(1), loai: "taovideo", trang_thai: "loi", tao_luc: "2026-11-17T09:00:00+07:00" }),
    V({ id: ID(2), loai: "taovideo", trang_thai: "xong", tao_luc: "2026-11-18T09:00:00+07:00" })], UID);
  assert.notEqual(F.dongSpHomNay(sp, vs).lop, "hn-loi");
  // đang chạy
  vs = F.viecCuaSp([V({ id: ID(3), loai: "taovideo", trang_thai: "dang_chay" })], UID);
  d = F.dongSpHomNay(sp, vs);
  assert.match(d.cau, /^Máy đang làm: /);
  assert.ok(!/taovideo/.test(d.cau));
  // việc của SP khác không tính
  vs = F.viecCuaSp([V({ id: ID(4), trang_thai: "loi", tham_so: { uid: UID2 } })], UID);
  assert.notEqual(F.dongSpHomNay(sp, vs).lop, "hn-loi");
  // không việc → câu theo trang_thai; 1 nút tới #/sp/<id>
  d = F.dongSpHomNay(sp, F.viecCuaSp([], UID));
  assert.equal(d.chang, 2);
  assert.equal(d.nut.href, `#/sp/${UID}`);
  const h = F.spHomNayHtml(sp, F.viecCuaSp([V({ trang_thai: "loi" })], UID), "");
  assert.ok(!/\d\s*%/.test(h), "không phần trăm");
  assert.equal((h.match(/class="btn[^"]*hn-sp-nut/g) || []).length, 1, "đúng 1 nút việc tiếp theo");
  assert.ok(!/8 ô/.test(h));
  assert.match(h, /class="[^"]*hn-loi[^"]*"[^>]*>[^<]*Có trục trặc — bấm để xem/);
});

test("duLieuHomNay: Cần bạn (duyệt trước, rồi câu hỏi), Máy đang làm, Xong hôm nay theo ngày VN", () => {
  const ds = [
    V({ id: ID(1), trang_thai: "can_tra_loi", cap_nhat_luc: "2026-11-18T08:00:00+07:00", cau_hoi: { loai: "chon", noi_dung: "Chọn?" } }),
    V({ id: ID(2), loai: "taovideo", trang_thai: "cho_duyet", cap_nhat_luc: "2026-11-18T09:00:00+07:00" }),
    V({ id: ID(3), trang_thai: "dang_chay", bat_dau_luc: "2026-11-18T14:00:00+07:00" }),
    V({ id: ID(4), trang_thai: "cho" }),
    V({ id: ID(5), trang_thai: "xong", ket_thuc_luc: "2026-11-18T10:00:00+07:00" }),
    V({ id: ID(6), trang_thai: "loi", ket_thuc_luc: "2026-11-18T00:30:00+07:00" }),
    V({ id: ID(7), trang_thai: "xong", ket_thuc_luc: "2026-11-17T23:59:00+07:00" }), // hôm qua giờ VN
    V({ id: ID(8), trang_thai: "xong", ket_thuc_luc: "2026-11-17T17:30:00Z" }),         // = 00:30 18/11 giờ VN
    V({ id: ID(9), trang_thai: "huy", ket_thuc_luc: "2026-11-18T10:00:00+07:00" }),
  ];
  const g = F.duLieuHomNay(ds, NOW);
  assert.deepEqual(g.canBan.map((v) => v.id), [ID(2), ID(1)]);
  assert.deepEqual(g.mayLam.map((v) => v.id), [ID(3), ID(4)]);
  assert.deepEqual(g.xongHomNay.map((v) => v.id).sort(), [ID(5), ID(6), ID(8)].sort());
  assert.equal(F.ngayVn(Date.parse("2026-11-17T17:30:00Z")), "2026-11-18");
});

test("homNayHtml: khối đủ thứ tự, quá 5 mục có 'Xem tất cả (N)', lỗi từng API riêng, mọi dữ liệu qua esc", () => {
  const canBan = Array.from({ length: 7 }, (_, k) => V({ id: ID(k), trang_thai: "can_tra_loi", cau_hoi: { loai: "chon", noi_dung: BAN } }));
  const sp = [{ id: UID, uid: UID, ten: BAN, trang_thai: "cho" }];
  let h = F.homNayHtml({ chu: true, nowMs: NOW, sk: { ok: true, d: { may_nha: true, apps: [] } }, viec: { ok: true, ds: canBan }, sp: { ok: true, ds: sp }, anh: () => "" });
  const iSk = h.indexOf("hn-sk"), iCan = h.indexOf("Cần bạn (7)"), iLam = h.indexOf("Máy đang làm (0)"), iXong = h.indexOf("Xong hôm nay (0)"), iSp = h.indexOf("hn-ds-sp");
  assert.ok(iSk >= 0 && iSk < iCan && iCan < iLam && iLam < iXong && iXong < iSp, [iSk, iCan, iLam, iXong, iSp].join(","));
  assert.match(h, /Xem tất cả \(7\)/);
  assert.equal((h.match(/class="hn-muc[^"]*hn-an"/g) || []).length, 2, "2 mục ẩn sau 5 mục đầu (không mất mục nào)");
  assert.equal((h.match(/href="#\/viec\/j/g) || []).length >= 7, true);
  assert.match(h, />Trả lời</);
  assert.match(h, /href="#\/suc-khoe"/);
  assert.ok(!h.includes("<img src=x"), "lọt thẻ img");
  assert.ok(h.includes(esc(BAN)));
  assert.ok(!/\son[a-z]+=/i.test(h.replace(/&lt;img src=x onerror=alert\(1\)&gt;/g, "")), "có on…=");
  // API việc lỗi tạm → khối việc báo lời thường, khối SP vẫn hiện
  h = F.homNayHtml({ chu: true, nowMs: NOW, sk: { ok: false, loai: "tam" }, viec: { ok: false, loai: "tam" }, sp: { ok: true, ds: sp }, anh: () => "" });
  assert.match(h, /Chưa tải được việc — máy nhà có thể đang tắt/);
  assert.match(h, /hn-ds-sp/);
  // 401/403 khác lỗi tạm
  h = F.homNayHtml({ chu: true, nowMs: NOW, sk: { ok: true, d: { may_nha: true } }, viec: { ok: false, loai: "quyen" }, sp: { ok: false, loai: "dang_nhap" }, anh: () => "" });
  assert.ok(!/máy nhà có thể đang tắt/.test(h));
  assert.match(h, /đăng nhập/i);
  // không phải chủ kho: chỉ danh sách SP
  h = F.homNayHtml({ chu: false, nowMs: NOW, sp: { ok: true, ds: sp }, anh: () => "" });
  assert.ok(!/Cần bạn/.test(h) && /hn-ds-sp/.test(h));
});

test("loaiLoiTai: 401 → dang_nhap, 403 → quyen, còn lại (mạng, 5xx) → tam", () => {
  assert.equal(F.loaiLoiTai(Object.assign(new Error("x"), { status: 401 })), "dang_nhap");
  assert.equal(F.loaiLoiTai(Object.assign(new Error("x"), { status: 403 })), "quyen");
  assert.equal(F.loaiLoiTai(Object.assign(new Error("x"), { status: 502 })), "tam");
  assert.equal(F.loaiLoiTai(new TypeError("Failed to fetch")), "tam");
  assert.equal(F.loaiLoiTai(null), "tam");
  assert.match(APP, /\.status = r\.status/);
});

test("Hôm nay CHỈ gọi 4 API song song (D15 thêm hoc/bao-cao), không gọi theo từng SP; chặn vẽ đè bằng phienCT trước await", () => {
  const dom = HN.slice(HN.indexOf("// --- homnay-thuan end ---"));
  // P-32: phần tải trang (renderHomNay) chỉ 4 nguồn; API tra-loi/huy chỉ nằm trong bamViecHn (gọi từ listener click)
  const tai = dom.slice(dom.indexOf("async function renderHomNay"), dom.indexOf("async function bamViecHn"));
  assert.ok(tai.length > 0 && dom.indexOf("async function bamViecHn") > dom.indexOf("async function renderHomNay"));
  const goi = tai.match(/\bapi\(/g) || [];
  assert.equal(goi.length, 3, "chỉ api(\"suc-khoe\") + api(\"viec?gioi_han=500\") + api(\"hoc/bao-cao\") (+ loadList)");
  assert.match(tai, /api\("suc-khoe"\)/);
  assert.match(tai, /api\("viec\?gioi_han=500"\)/);
  assert.match(tai, /chu \? api\("hoc\/bao-cao"\) : null/, "D15: báo cáo học chỉ gọi cho chủ kho");
  assert.match(tai, /loadList\(\)/);
  assert.match(tai, /Promise\.allSettled\(/);
  const bam = dom.slice(dom.indexOf("async function bamViecHn"));
  const goiBam = [...bam.matchAll(/\bapi\(([^,)]*)/g)].map((m) => m[1]);
  assert.deepEqual(goiBam, ["`viec/${id}/${act}`"], "bamViecHn: đúng 1 lời gọi api");
  assert.match(bam, /const act = huy \? "huy" : "tra-loi"/);
  assert.equal((HN.match(/\bbamViecHn\(/g) || []).length, 2, "khai báo + 1 lời gọi (trong listener click)");
  assert.match(tai, /addEventListener\("click"[\s\S]*bamViecHn\(/);
  const khuonApi = [...HN.matchAll(/api\(`[^`]*`/g)].map((m) => m[0]);
  assert.deepEqual(khuonApi, ["api(`viec/${id}/${act}`"], "không gọi api với đường dẫn ghép theo SP");
  assert.ok(!/\.(map|forEach)\([^)]*api\(/.test(HN));
  const f = dom.slice(dom.indexOf("async function renderHomNay"));
  const iPhien = f.indexOf("++phienCT"), iAwait = f.indexOf("await");
  assert.ok(iPhien > 0 && iPhien < iAwait, "đánh số phiên trước await");
  assert.match(f.slice(iAwait), /phien !== phienCT/);
  assert.match(f, /needLogin\(\)/);
});

// ---------- 4. màn duyệt ----------
const VS = (x = {}) => ({ id: ID(1), loai: "taovideo", trang_thai: "cho_duyet", tham_so: { uid: UID, du_an_a: "abcdef012345", du_an_b: "tu_tim", wm: "nha.cua.mit" }, ...x });
test("khung duyệt: Dự kiến / Tối đa / Sẽ làm ra + nút ghi trần; giữ mật khẩu + sha256", () => {
  const d = { viec: VS(), tham_so_chuan: JSON.stringify(VS().tham_so) };
  const sk = { han_muc: { taovideo_usd_viec: 40, taovideo_mp3_viec: 20, taovideo_lam_s: 7200 } };
  let h = F.khungDuyetHtml(d, { sk });
  assert.match(h, /Dự kiến:<\/b> Chưa có ước tính/);
  assert.match(h, /Tối đa:<\/b> <span id="vd-toi-da">40 USD Claude · 20 voice · 2 giờ làm<\/span>/);
  assert.match(h, /Gắn logo: nha\.cua\.mit/);
  assert.match(h, /data-vd-act="duyet"[^>]*>[^<]*Duyệt &amp; chạy \(tối đa 40 USD\)/);
  assert.match(h, /type="password"/);
  // thiếu hạn mức → lấy từ TRAN_PHIEN_TAOVIDEO
  h = F.khungDuyetHtml(d, {});
  assert.match(h, /Tối đa:<\/b> <span id="vd-toi-da">60 USD Claude · 25 voice · 8 giờ làm<\/span>/);
  assert.match(h, /tối đa 60 USD/);
  // có ước tính
  h = F.khungDuyetHtml({ ...d, viec: VS({ ket_qua: { uoc_tinh: { chi_phi_usd: 12.5 } } }) }, { sk });
  assert.match(h, /Dự kiến:<\/b> ~12\.5 USD/);
  // muse: số clip + trần clip
  const dm = { viec: { id: ID(1), loai: "muse_clip", trang_thai: "cho_duyet", tham_so: { uid: UID, du_an: "abcdef012345", mau: ["xoay_360", "mo_hop"], thoi_luong: 15 } } };
  h = F.khungDuyetHtml({ ...dm, tham_so_chuan: JSON.stringify(dm.viec.tham_so) }, { sk: { han_muc: { muse_clip_moi_viec: 7 } } });
  assert.match(h, /2 clip × 15 giây/);
  assert.match(h, /Duyệt &amp; chạy \(tối đa 7 clip\)/);
  // không tự đoán watermark khi tham số thiếu
  assert.equal(F.seLamRaDuyet("taovideo", { uid: UID }).some((s) => /nha\.cua\.mit|Không watermark/.test(s)), false);
  // dữ liệu xấu
  h = F.khungDuyetHtml({ viec: VS({ tham_so: { wm: BAN, so_video: BAN } }), tham_so_chuan: JSON.stringify({ wm: BAN }) }, { sk: { han_muc: { taovideo_usd_viec: BAN } } });
  assert.ok(!h.includes("<img"));
  // DOM: cập nhật trần khi hạn mức về, cơ chế băm giữ nguyên
  const r = VIEC.slice(VIEC.indexOf("const taiSkDuyet"), VIEC.indexOf("const veDuyet"));
  assert.match(r, /vd-toi-da/);
  assert.match(r, /nhanNutDuyet\(/);
  assert.match(VIEC, /sha_tham_so: await sha256HexWeb\(tsc\)/);
});

// ---------- 5. form taovideo ----------
test("form taovideo: tự chọn dự án A khi chỉ có 1, B mặc định tu_tim, giá từ SP; watermark không tự chọn ngầm; lời thường", () => {
  assert.equal(F.duAnATuDong([{ ma: "abcdef012345", ten: "x" }], ""), "abcdef012345");
  assert.equal(F.duAnATuDong([{ ma: "abcdef012345" }, { ma: "0123456789ab" }], ""), "");
  assert.equal(F.duAnATuDong([{ ma: "abcdef012345" }], "0123456789ab"), "0123456789ab");
  assert.equal(F.duAnATuDong(null, ""), "");
  assert.equal(F.giaTuInfoSp({ gia: "112.389₫" }), "112389");
  assert.equal(F.giaTuInfoSp({ gia: "99₫" }), "");               // dưới mức Worker nhận
  assert.equal(F.giaTuInfoSp({ gia: "100.000₫ - 200.000₫" }), ""); // khoảng giá: không đoán
  assert.equal(F.giaTuInfoSp({ gia: "1,5tr" }), "");
  assert.equal(F.giaTuInfoSp({}), "");
  const mot = [{ ma: "abcdef012345", ten: "20261117-ban-chai" }];
  let h = F.formViecSpHtml({ loai: "taovideo", du_an_a: "abcdef012345", du_an_b: "tu_tim", wm: "", gia: "112389" }, { duAn: mot, wm: ["khong", "nha.cua.mit"] });
  assert.ok(!/<select[^>]*data-vs-a/.test(h), "1 dự án: không hiện hộp chọn A");
  assert.ok(!/<select[^>]*data-vs-b/.test(h), "1 dự án: không hiện hộp chọn B");
  assert.match(h, /Đợt quay dùng cho video giọng Adam/);
  assert.match(h, /20261117-ban-chai/);
  assert.match(h, /Đợt quay có giọng creator/);
  assert.match(h, /Tự tìm/);
  assert.ok(!/raw\/|takes\/|tu_tim<|Dự án A \(|Dự án B \(/.test(h.replace(/value="tu_tim"/g, "")), "còn nhãn kỹ thuật");
  assert.match(h, /<option value="" selected>— chọn logo —<\/option>/);
  assert.match(h, /Logo này sẽ in lên video/);
  assert.match(h, /value="112389"/);
  // runner trả lỗi thiếu/thừa takes → hiện hộp chọn B dù chỉ 1 dự án
  h = F.formViecSpHtml({ loai: "taovideo", du_an_a: "abcdef012345", du_an_b: "", wm: "khong", loi_b: "Có 2 dự án có takes" }, { duAn: mot, wm: ["khong"] });
  assert.match(h, /<select[^>]*data-vs-b/);
  assert.match(h, /Logo này sẽ in lên video: <b>Không watermark<\/b>/);
  // DOM: gửi đúng wm người chọn (không thay ngầm bằng wmDs[0]); tự điền A + giá
  const r = VIEC.slice(VIEC.indexOf("function veViecSp("));
  assert.ok(!/wmDs\.includes\(f\.wm\) \? f\.wm : wmDs\[0\]/.test(r), "còn chọn ngầm watermark");
  assert.match(r, /giaTuInfoSp\(/);
  assert.match(VIEC, /duAnATuDong\(/);
  // thamSoTaovideo vẫn chặn khi chưa chọn watermark
  assert.ok(F.thamSoTaovideo(UID, "abcdef012345", "tu_tim", "", "").loi);
});

// ---------- 6. trang SP dạng trợ lý ----------
test("trang SP: khối 'Bước tiếp theo' sau tên/ảnh, 8 bước gom vào <details>, nút 'Để sau' về #/", () => {
  const r = APP.slice(APP.indexOf("async function renderDetail("), APP.indexOf("document.addEventListener(\"click\""));
  const iHead = r.indexOf('<div class="head">'), iBt = r.indexOf('id="buoc-tiep"'), iDet = r.indexOf("<details");
  assert.ok(iHead > 0 && iHead < iBt && iBt < iDet, "thứ tự head → bước tiếp theo → details");
  // W-M3 §5: "Xem đủ 8 bước" → "Chi tiết 8 bước nhỏ" + dòng ánh xạ 4 chặng; tab Duyệt + Rủi ro bỏ (Rủi ro gộp vào Tóm tắt)
  assert.match(r, /<details[^>]*>\s*<summary>Chi tiết 8 bước nhỏ<\/summary>\s*<p class="small muted">[^<]*Chuẩn bị \(1–2\) · Quay \(3\) · Làm video \(4–6\) · Chấm và đăng \(7–8\)<\/p>\s*<div class="buoc8" id="buoc8"><\/div>/);
  assert.match(r, /buocTiepTheo\(/);
  assert.match(r, /buocHienTai\(/);
  for (const tab of ["canh", "douyin", "cap", "tt", "vtk", "video", "note"]) assert.match(r, new RegExp(`data-tab="${tab}"`), tab);
  for (const tab of ["ruiro", "duyet"]) assert.ok(!r.includes(`data-tab="${tab}"`), tab);
  let b = F.buocTiepTheo(6, "da_quay", true);
  assert.equal(b.chang, 2);
  assert.equal(b.nut.lam, "viec:taovideo");
  b = F.buocTiepTheo(null, "da_phan_tich", false);
  assert.equal(b.chang, 1);
  assert.equal(b.nut.lam, "tab:canh");
  const h = F.buocTiepHtml(F.buocTiepTheo(7, "da_lam_video", true), "");
  assert.match(h, /Việc nên làm bây giờ/);
  assert.match(h, /<a class="btn ghost[^"]*" href="#\/">Để sau<\/a>/);
  assert.equal((h.match(/data-bt-lam=/g) || []).length, 1, "1 nút chính");
  assert.ok(!/8 ô/.test(h));
});

// ---------- 7, 8. điện thoại, index.html, CSP ----------
test("CSS điện thoại: nút ≥44px, ô nhập 16px, 1 cột dưới 640px, không cuộn ngang", () => {
  const m = CSS.match(/\/\* W-7 điện thoại \*\/\s*@media \(max-width: 640px\) \{([\s\S]*?)\n\}/);
  assert.ok(m, "thiếu khối @media W-7");
  assert.match(m[1], /\.btn[^{]*\{[^}]*min-height: 44px/);
  assert.match(m[1], /input, textarea, select[^{]*\{[^}]*font-size: 16px/);
  assert.match(m[1], /grid-template-columns: 1fr|flex-direction: column/);
  assert.match(CSS, /overflow-x: clip/);
});

test("index.html: loi.js + homnay.js nạp trước viec.js/app.js, tăng phiên bản; không script inline", () => {
  // Đợt 8 (W-M1): khung.js nằm giữa viec.js và app.js (docs/giao-dien-menu-trai.md §9); dang.js, duyet.js gỡ 2026-11-19.
  // D15 (HT-W2): hoc.js ngay sau homnay.js.
  assert.match(HTML, /<script src="loi\.js\?v=\d+" defer><\/script>\s*<script src="homnay\.js\?v=\d+" defer><\/script>\s*<script src="hoc\.js\?v=\d+" defer><\/script>\s*<script src="viec\.js\?v=\d+" defer><\/script>\s*<script src="khung\.js\?v=\d+" defer><\/script>\s*<script src="poster\.js\?v=\d+" defer><\/script>\s*<script src="pv-dashboard\.js\?v=\d+" defer><\/script>\s*<script src="pv-accounts\.js\?v=\d+" defer><\/script>\s*<script src="pv-folders\.js\?v=\d+" defer><\/script>\s*<script src="pv-calendar\.js\?v=\d+" defer><\/script>\s*<script src="pv-views\.js\?v=\d+" defer><\/script>\s*<script src="pv-queue\.js\?v=\d+" defer><\/script>\s*<script src="pv-post\.js\?v=\d+" defer><\/script>\s*<script src="pv-logs\.js\?v=\d+" defer><\/script>\s*<script src="pv-settings\.js\?v=\d+" defer><\/script>\s*<script src="app\.js\?v=\d+" defer><\/script>\s*<script src="sua\.js\?v=\d+" defer>/);
  assert.ok(Number(HTML.match(/style\.css\?v=(\d+)/)[1]) >= 18);
  // FX-30: loi.js, homnay.js, app.js đã sửa → tăng phiên bản
  assert.ok(Number(HTML.match(/loi\.js\?v=(\d+)/)[1]) >= 2);
  assert.ok(Number(HTML.match(/homnay\.js\?v=(\d+)/)[1]) >= 2);
  assert.ok(Number(HTML.match(/app\.js\?v=(\d+)/)[1]) >= 17);
  assert.ok(Number(HTML.match(/viec\.js\?v=(\d+)/)[1]) >= 9);
  assert.ok(!/<script(?![^>]*\ssrc=)[^>]*>/i.test(HTML));
  for (const [ten, src] of [["loi.js", LOI], ["homnay.js", HN], ["app.js", APP], ["viec.js", VIEC]]) {
    assert.ok(!/\son[a-z]+="/.test(src), `${ten} có on…="`);
    assert.ok(!/onclick\s*=/i.test(src), `${ten} có onclick=`);
  }
});

const khaiBao = (src) => [...src.matchAll(/^(?:const|let|var|function|async function|class)\s+([A-Za-z_$][\w$]*)/gm)].map((x) => x[1]);
test("không trùng tên khai báo cấp cao giữa loi.js, homnay.js, hoc.js, viec.js, app.js, sua.js", () => {
  const thay = new Map();
  for (const [ten, src] of [["loi.js", LOI], ["homnay.js", HN], ["hoc.js", doc("hoc.js")], ["viec.js", VIEC], ["app.js", APP], ["sua.js", SUA]]) {
    for (const k of khaiBao(src)) {
      assert.ok(!thay.has(k), `${k} khai báo ở cả ${thay.get(k)} và ${ten}`);
      thay.set(k, ten);
    }
  }
});

test("chèn dữ liệu vào HTML qua esc: tên SP, câu hỏi AI, tên thư mục", () => {
  const sp = { id: UID, uid: UID, ten: BAN, trang_thai: "cho" };
  const vs = F.viecCuaSp([V({ trang_thai: "can_tra_loi", cau_hoi: { loai: "chon", noi_dung: BAN } })], UID);
  const h = F.spHomNayHtml(sp, vs, `x" onerror="alert(1)`);
  assert.ok(!h.includes("<img src=x"));
  assert.ok(!/onerror="alert/.test(h), "lọt thuộc tính qua src ảnh");
  const f = F.formViecSpHtml({ loai: "taovideo", du_an_a: "", du_an_b: "tu_tim", wm: "" }, { duAn: [{ ma: "abcdef012345", ten: BAN }, { ma: "0123456789ab", ten: BAN }] });
  assert.ok(!f.includes("<img src=x"));
  // không chèn chuỗi thô (template ${x.ten} không qua esc) trong homnay.js / loi.js
  for (const [ten, src] of [["homnay.js", HN], ["loi.js", LOI]]) {
    for (const m of src.matchAll(/\$\{([^}]*\.(ten|noi_dung|loi|message)[^}]*)\}/g)) assert.match(m[1], /esc\(/, `${ten}: \${${m[1]}} không qua esc`);
  }
});

// ---------- FX-30: sửa sau review lượt 31 ----------
test("FX-30 P2-1: Hôm nay gọi giới hạn tối đa runner (500), báo khi có thể còn việc cũ hơn / còn việc cần bạn chưa hiện", () => {
  assert.equal(F.HN_GIOI_HAN_VIEC, 500);
  const sp = { ok: true, ds: [] };
  const sk = { ok: true, d: { may_nha: true } };
  // đủ 500 dòng → ghi chú "Có thể còn việc cũ hơn"
  const day = Array.from({ length: 500 }, (_, k) => V({ id: `j2026111810${String(k).padStart(4, "0")}abcd`, trang_thai: "xong", ket_thuc_luc: "2026-11-10T10:00:00+07:00" }));
  let h = F.homNayHtml({ chu: true, nowMs: NOW, sk, viec: { ok: true, ds: day }, sp, anh: () => "" });
  assert.match(h, /Có thể còn việc cũ hơn — xem trang Việc/);
  h = F.homNayHtml({ chu: true, nowMs: NOW, sk, viec: { ok: true, ds: day.slice(0, 499) }, sp, anh: () => "" });
  assert.ok(!/Có thể còn việc cũ hơn/.test(h));
  // dem toàn kho nhiều hơn số đang hiện → "Còn N việc cần bạn chưa hiện"
  const ds = [V({ id: ID(1), loai: "taovideo", trang_thai: "cho_duyet" })];
  h = F.homNayHtml({ chu: true, nowMs: NOW, sk, viec: { ok: true, ds, dem: { cho_duyet: 2, can_tra_loi: 1 } }, sp, anh: () => "" });
  assert.match(h, /Cần bạn \(1\)/);
  assert.match(h, /Còn 2 việc cần bạn chưa hiện — xem trang Việc/);
  h = F.homNayHtml({ chu: true, nowMs: NOW, sk, viec: { ok: true, ds, dem: { cho_duyet: 1 } }, sp, anh: () => "" });
  assert.ok(!/chưa hiện/.test(h));
  h = F.homNayHtml({ chu: true, nowMs: NOW, sk, viec: { ok: true, ds, dem: { cho_duyet: "<b>9</b>" } }, sp, anh: () => "" });
  assert.ok(!/chưa hiện/.test(h) && !h.includes("<b>9"));
  // DOM: chuyển dem (nếu phản hồi có) vào homNayHtml
  const dom = HN.slice(HN.indexOf("// --- homnay-thuan end ---"));
  assert.match(dom, /dem: /);
});

test("FX-30 P2-2: nút chính trang SP chỉ trỏ viec:<loai> khi goiYViec có loại đó; không có thì đổi câu/nhãn hoặc báo máy nhà chưa sẵn sàng", () => {
  const i = { uid: UID, co_douyin: true };
  const coSan = (ht, dot) => F.goiYViec(ht, i, dot).nut.map((n) => n.loai);
  // bước 6, đợt 5: có taovideo → giữ "Làm video"
  let b = F.buocTiepTheo(6, "da_quay", true, coSan(6, 5));
  assert.equal(b.nut.lam, "viec:taovideo");
  assert.equal(b.nut.nhan, "Làm video");
  // bước 4/5 đợt 5: đã quay → nút chính vẫn là "Làm video" (clip AI, voice lẻ chỉ là nút phụ trong khối việc)
  for (const ht of [4, 5]) {
    b = F.buocTiepTheo(ht, "da_quay", true, coSan(ht, 5));
    assert.equal(b.nut.lam, "viec:taovideo");
    assert.equal(b.nut.nhan, "Làm video");
  }
  // bước 5 đợt 4 (chưa mở taovideo): rơi về voice
  b = F.buocTiepTheo(5, "da_quay", true, coSan(5, 4));
  assert.equal(b.nut.lam, "viec:voice_pv");
  assert.match(b.cau + b.nut.nhan, /Đọc lời bằng giọng AI/);
  // bước 4 đợt 3: goiYViec rỗng → máy nhà chưa sẵn sàng, nút về khối việc
  assert.deepEqual(coSan(4, 3), []);
  b = F.buocTiepTheo(4, "da_quay", true, coSan(4, 3));
  assert.match(b.cau, /Máy nhà chưa sẵn sàng cho bước này/);
  assert.equal(b.nut.lam, "khoi:viec");
  // chỉ còn nút phụ Douyin → vẫn coi là chưa sẵn sàng (không đưa Douyin làm nút chính)
  b = F.buocTiepTheo(6, "da_quay", true, F.goiYViec(6, { uid: UID }, 3).nut.map((n) => n.loai));
  assert.equal(b.nut.lam, "khoi:viec");
  // mọi nút viec: đều nằm trong danh sách goiYViec
  for (let ht = 0; ht <= 8; ht++) for (const dot of [3, 4, 5]) for (const info of [i, { uid: UID }, {}]) {
    const ds = F.goiYViec(ht, info, dot).nut.map((n) => n.loai);
    const x = F.buocTiepTheo(ht, "da_quay", true, ds);
    if (x.nut.lam.startsWith("viec:")) assert.ok(ds.includes(x.nut.lam.slice(5)), `ht ${ht} đợt ${dot}: ${x.nut.lam}`);
  }
  // app.js: tính danh sách loại bằng goiYViec rồi truyền vào buocTiepTheo; vẽ lại khi khối việc đổi
  const r = APP.slice(APP.indexOf("const veBuocTiep"), APP.indexOf("const vtkHtml"));
  assert.match(r, /goiYViec\(/);
  assert.match(r, /buocTiepTheo\(ht, tt, chu, [a-zA-Z]+\)/);
  assert.match(APP, /MutationObserver/);
});

test("FX-30 P2-3: renderDetail kiểm phienCT sau await ở cả nhánh lỗi lẫn thành công, trước khi ghi #app", () => {
  const f = APP.slice(APP.indexOf("async function renderDetail("));
  const iAwait = f.indexOf("await api(");
  const iCatch = f.indexOf("catch (err)", iAwait);
  const iTc = f.indexOf("const { info: i, md, caps, douyin } = d;");
  assert.ok(iAwait > 0 && iCatch > iAwait && iTc > iCatch);
  const catchK = f.slice(iCatch, f.indexOf("\n", iCatch));
  assert.ok(catchK.includes("phien !== phienCT") && catchK.indexOf("phien !== phienCT") < catchK.indexOf('$("#app").innerHTML'), "nhánh lỗi");
  assert.match(f.slice(f.indexOf("\n", iCatch), iTc), /if \(phien !== phienCT\) return;/, "nhánh thành công");
});

test("FX-30 P3-a: dòng SP đúng 1 chỗ bấm; nút theo ưu tiên duyệt → trả lời → trục trặc → đang chạy → chặng", () => {
  const sp = { id: UID, uid: UID, ten: "SP", trang_thai: "da_quay" };
  const nut = (ds) => F.dongSpHomNay(sp, F.viecCuaSp(ds, UID)).nut;
  const loi = V({ id: ID(1), loai: "douyin_uid", trang_thai: "loi", tao_luc: "2026-11-18T08:00:00+07:00" });
  const dangChay = V({ id: ID(2), loai: "phan_tich_uid", trang_thai: "dang_chay", tao_luc: "2026-11-18T08:30:00+07:00" });
  const hoi = V({ id: ID(3), loai: "voice_pv", trang_thai: "can_tra_loi", cau_hoi: { loai: "chon", noi_dung: "?" }, tao_luc: "2026-11-18T09:00:00+07:00" });
  const duyet = V({ id: ID(4), loai: "taovideo", trang_thai: "cho_duyet", tao_luc: "2026-11-18T09:30:00+07:00" });
  assert.deepEqual(nut([loi, dangChay, hoi, duyet]), { nhan: "Xem và duyệt", href: `#/viec/${ID(4)}` });
  assert.deepEqual(nut([loi, dangChay, hoi]), { nhan: "Trả lời", href: `#/viec/${ID(3)}` });
  assert.deepEqual(nut([loi, dangChay]), { nhan: "Xem trục trặc", href: `#/viec/${ID(1)}` });
  assert.deepEqual(nut([dangChay]), { nhan: "Xem máy đang làm", href: `#/viec/${ID(2)}` });
  assert.deepEqual(nut([]), { nhan: "Làm video", href: `#/sp/${UID}` });
  // dòng trạng thái khớp nút (đang chờ bạn → không ghi trục trặc lên cùng dòng)
  assert.equal(F.dongSpHomNay(sp, F.viecCuaSp([loi, duyet], UID)).lop, "hn-cho-ban");
  // HTML: dòng trạng thái là chữ thường, đúng 1 NÚT (.btn) trong dòng SP; P-32: tên + ảnh SP là link #/sp/<id> (không phải nút)
  for (const ds of [[loi], [duyet], [hoi], [dangChay], []]) {
    const h = F.spHomNayHtml(sp, F.viecCuaSp(ds, UID), "");
    assert.equal((h.match(/class="btn\b/g) || []).length, 1, JSON.stringify(ds.map((v) => v.trang_thai)));
    assert.ok(!/<button\b/.test(h));
    const khongPhaiNut = [...h.matchAll(/<a\b([^>]*)>/g)].map((m) => m[1]).filter((a) => !/class="btn\b/.test(a));
    assert.ok(khongPhaiNut.length >= 1 && khongPhaiNut.every((a) => a.includes(`href="#/sp/${UID}"`)), "link ngoài nút chỉ tới #/sp/<id>");
    assert.ok(!/<a[^>]*hn-tt/.test(h));
    assert.match(h, /<div class="hn-tt/);
  }
});

test("FX-30 P3-b: việc tốn tiền can_tra_loi không phiên sống → 'Cần duyệt lại để chạy tiếp' + 'Xem và duyệt lại'", () => {
  const ch = { loai: "chon", noi_dung: "Chọn mẫu?", lua_chon: ["a"] };
  const tt = V({ loai: "taovideo", trang_thai: "can_tra_loi", cau_hoi: ch });
  assert.equal(F.canDuyetLaiViec(tt), true);
  assert.match(F.cauViec(tt), /^Cần duyệt lại để chạy tiếp/);
  assert.ok(!/Máy hỏi/.test(F.cauViec(tt)));
  assert.equal(F.nutViec(tt), "Xem và duyệt lại");
  // phiên sống: trả lời trực tiếp được
  const song = { ...tt, phien_song: true };
  assert.equal(F.canDuyetLaiViec(song), false);
  assert.match(F.cauViec(song), /^Máy hỏi: /);
  assert.equal(F.nutViec(song), "Trả lời");
  // việc thường (không tốn tiền) không phiên: vẫn "Trả lời"
  const thuong = V({ loai: "voice_pv", trang_thai: "can_tra_loi", cau_hoi: ch });
  assert.equal(F.canDuyetLaiViec(thuong), false);
  assert.equal(F.nutViec(thuong), "Trả lời");
  // viec_tay của việc tốn tiền không phiên cũng phải duyệt lại
  assert.match(F.cauViec(V({ loai: "muse_clip", trang_thai: "can_tra_loi", cau_hoi: { loai: "viec_tay", noi_dung: "x" } })), /^Cần duyệt lại/);
  assert.equal(F.canDuyetLaiViec(V({ loai: "taovideo", trang_thai: "cho_duyet" })), false);
  // dùng đúng cờ của viec.js (nutHanhDong(...).anTraLoi — cùng điều kiện nutTraLoi trả rỗng)
  assert.match(LOI, /nutHanhDong\(/);
  // trên trang Hôm nay: dòng SP và khối Cần bạn
  const sp = { id: UID, uid: UID, ten: "SP", trang_thai: "da_quay" };
  assert.deepEqual(F.dongSpHomNay(sp, F.viecCuaSp([tt], UID)).nut, { nhan: "Xem và duyệt lại", href: `#/viec/${ID(1)}` });
  const h = F.homNayHtml({ chu: true, nowMs: NOW, sk: { ok: true, d: { may_nha: true } }, viec: { ok: true, ds: [tt] }, sp: { ok: true, ds: [sp] }, anh: () => "" });
  assert.match(h, /Cần duyệt lại để chạy tiếp/);
  assert.ok(!/>Trả lời</.test(h));
});

test("FX-30 P3-c: lỗi đã chạy lại xong → xám 'Lỗi, đã chạy lại xong'; lỗi rồi huỷ → vẫn trục trặc ở dòng SP", () => {
  const loi = V({ id: ID(1), loai: "taovideo", trang_thai: "loi", tao_luc: "2026-11-18T08:00:00+07:00", ket_thuc_luc: "2026-11-18T08:30:00+07:00" });
  const xong = V({ id: ID(2), loai: "taovideo", trang_thai: "xong", tao_luc: "2026-11-18T09:00:00+07:00", ket_thuc_luc: "2026-11-18T10:00:00+07:00" });
  const sk = { ok: true, d: { may_nha: true } };
  const khoiXong = (ds) => { const h = F.homNayHtml({ chu: true, nowMs: NOW, sk, viec: { ok: true, ds }, sp: { ok: true, ds: [] }, anh: () => "" }); return h.slice(h.indexOf("hn-xong")); };
  let k = khoiXong([loi, xong]);
  assert.match(k, /Lỗi, đã chạy lại xong/);
  assert.ok(!/class="hn-loi"/.test(k), "không còn đỏ");
  // lần chạy lại xong là của SP khác → vẫn đỏ
  assert.match(khoiXong([loi, { ...xong, tham_so: { uid: UID2 } }]), /class="hn-loi">Có trục trặc/);
  // lần xong CŨ hơn lần lỗi → vẫn đỏ
  assert.match(khoiXong([loi, { ...xong, tao_luc: "2026-11-18T07:00:00+07:00" }]), /class="hn-loi">Có trục trặc/);
  // lần xong là loại khác → vẫn đỏ
  assert.match(khoiXong([loi, { ...xong, loai: "muse_clip" }]), /class="hn-loi">Có trục trặc/);
  // lỗi rồi lần sau bị huỷ → dòng SP vẫn trục trặc
  const huy = V({ id: ID(3), loai: "taovideo", trang_thai: "huy", tao_luc: "2026-11-18T09:00:00+07:00" });
  const vs = F.viecCuaSp([loi, huy], UID);
  assert.equal(vs.loi && vs.loi.id, ID(1));
  const sp = { id: UID, uid: UID, ten: "SP", trang_thai: "da_quay" };
  assert.equal(F.dongSpHomNay(sp, vs).lop, "hn-loi");
  assert.equal(F.dongSpHomNay(sp, vs).nut.nhan, "Xem trục trặc");
});

// ---------- P-32: bắt đầu dùng luồng ngay từ trang Hôm nay ----------
const CAU_KHO = "Dữ liệu kho có thay đổi chưa đẩy: data/1731898847922259456/douyin.md";
const TAY = (x = {}) => V({ id: ID(5), loai: "phan_tich_uid", trang_thai: "can_tra_loi",
  cau_hoi: { loai: "viec_tay", lua_chon: [], noi_dung: CAU_KHO }, ...x });
const SK_OK = { ok: true, d: { may_nha: true } };
const khoiCanBan = (h) => h.slice(h.indexOf("hn-can-ban"), h.indexOf("hn-may-lam"));
const reEsc = (s) => s.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");

const CAU_KHO_LT = "Máy nhà có dữ liệu kho chưa lưu lên mạng (data/1731898847922259456/douyin.md). Cần lưu hoặc bỏ thay đổi đó trên máy nhà rồi bấm Thử lại.";
test("P-32 loiViecTay: câu kho chưa đẩy → lời thường + việc cần làm; câu lạ giữ nguyên (cắt 160); cauViec dùng nó", () => {
  let l = F.loiViecTay(CAU_KHO);
  assert.equal(l.nhanRa, true);
  assert.equal(l.cau, CAU_KHO_LT);
  // P-32b P2-1: không hứa "tự xong" (runner chỉ hỏi khi kho VẪN bẩn — Thử lại lúc còn bẩn sẽ bị hỏi lại)
  assert.ok(!/tự xong|vài phút/.test(l.cau));
  l = F.loiViecTay("  Mở app Poster rồi bấm đăng nhập  ");
  assert.deepEqual(l, { cau: "Mở app Poster rồi bấm đăng nhập", nhanRa: false });
  assert.equal(F.loiViecTay("x".repeat(300)).cau.length, 160);
  assert.deepEqual(F.loiViecTay(null), { cau: "", nhanRa: false });
  assert.deepEqual(F.loiViecTay(42), { cau: "", nhanRa: false });
  // cauViec: câu nhận ra → lời thường; câu lạ → như cũ
  assert.equal(F.cauViec(TAY()), CAU_KHO_LT);
  assert.equal(F.cauViec(TAY({ cau_hoi: { loai: "viec_tay", noi_dung: "Cắm ổ cứng" } })), "Cần bạn làm tay: Cắm ổ cứng");
  assert.equal(F.cauViec(TAY({ cau_hoi: JSON.stringify({ loai: "viec_tay", noi_dung: CAU_KHO }) })), CAU_KHO_LT);
  // việc tốn tiền không phiên vẫn ưu tiên "Cần duyệt lại"
  assert.match(F.cauViec(TAY({ loai: "taovideo" })), /^Cần duyệt lại/);
});

test("P-32 viecTayHn: chỉ viec_tay, can_tra_loi, không tốn tiền, không phiên sống, id hợp lệ", () => {
  assert.equal(F.viecTayHn(TAY()), true);
  assert.equal(F.viecTayHn(TAY({ cau_hoi: JSON.stringify({ loai: "viec_tay", noi_dung: "x" }) })), true);
  for (const loai of F.LOAI_TON_TIEN) assert.equal(F.viecTayHn(TAY({ loai })), false, loai);
  assert.equal(F.viecTayHn(TAY({ phien_song: true })), false);
  assert.equal(F.viecTayHn(TAY({ trang_thai: "cho_duyet" })), false);
  assert.equal(F.viecTayHn(TAY({ cau_hoi: { loai: "chon", noi_dung: "?", lua_chon: ["a"] } })), false);
  assert.equal(F.viecTayHn(TAY({ cau_hoi: { loai: "cau_hoi", noi_dung: "?" } })), false);
  assert.equal(F.viecTayHn(TAY({ id: `j1"><img` })), false);
  assert.equal(F.viecTayHn(null), false);
});

test("P-32 dòng SP: viec_tay không tốn tiền → nút Thử lại + Bỏ việc này tại chỗ; việc khác vẫn link #/viec/<id>", () => {
  const sp = { id: UID, uid: UID, ten: "SP", trang_thai: "cho" };
  let h = F.spHomNayHtml(sp, F.viecCuaSp([TAY()], UID), "");
  assert.ok(h.includes(`<button type="button" class="btn sm" data-hn-tl="${ID(5)}">Thử lại</button>`), h);
  assert.ok(h.includes(`<button type="button" class="btn ghost sm" data-hn-huy="${ID(5)}">Bỏ việc này</button>`));
  assert.ok(h.includes(esc(CAU_KHO_LT)));
  assert.ok(!/href="#\/viec\//.test(h), "không còn nút dẫn sang trang Việc");
  // cho_duyet / tốn tiền / phiên sống / câu hỏi chon → không có nút tại chỗ, vẫn link #/viec/<id>
  for (const v of [V({ id: ID(6), loai: "taovideo", trang_thai: "cho_duyet" }), TAY({ loai: "muse_clip" }), TAY({ phien_song: true }),
    TAY({ cau_hoi: { loai: "chon", noi_dung: "?", lua_chon: ["a"] } })]) {
    h = F.spHomNayHtml({ ...sp, trang_thai: "da_quay" }, F.viecCuaSp([v], UID), "");
    assert.ok(!/data-hn-(tl|huy)/.test(h), JSON.stringify(v));
    assert.ok(h.includes(`href="#/viec/${v.id}"`));
  }
});

test("P-32 phan_tich_uid chờ mà SP đã có bộ cảnh quay → câu 'việc cũ' + nút chính 'Bỏ việc cũ', không Thử lại", () => {
  for (const tt of ["da_phan_tich", "da_quay", "da_lam_video"]) {
    const sp = { id: UID, uid: UID, ten: "SP", trang_thai: tt };
    const d = F.dongSpHomNay(sp, F.viecCuaSp([TAY()], UID));
    assert.match(d.cau, /Sản phẩm này đã có bộ cảnh quay — việc phân tích đang chờ là việc cũ, có thể bỏ\./);
    const h = F.spHomNayHtml(sp, F.viecCuaSp([TAY()], UID), "");
    assert.ok(h.includes(`<button type="button" class="btn sm" data-hn-huy="${ID(5)}" data-hn-cu="1">Bỏ việc cũ</button>`), tt);
    assert.ok(!/data-hn-tl=/.test(h), tt);
  }
  // SP còn "cho" → không phải việc cũ
  let h = F.spHomNayHtml({ id: UID, uid: UID, ten: "SP", trang_thai: "cho" }, F.viecCuaSp([TAY()], UID), "");
  assert.ok(!/Bỏ việc cũ/.test(h));
  // loại khác (douyin_uid) dù SP đã phân tích → Thử lại bình thường
  h = F.spHomNayHtml({ id: UID, uid: UID, ten: "SP", trang_thai: "da_phan_tich" }, F.viecCuaSp([TAY({ loai: "douyin_uid" })], UID), "");
  assert.ok(!/Bỏ việc cũ/.test(h) && /data-hn-tl=/.test(h));
});

test("P-32 khối Cần bạn: cùng điều kiện nút tại chỗ; việc cũ theo trang_thai SP cùng uid", () => {
  const sp = [{ id: UID, uid: UID, ten: "SP A", trang_thai: "da_phan_tich" }, { id: UID2, uid: UID2, ten: "SP B", trang_thai: "cho" }];
  const ID10 = "j20261118100010abcd";
  const ds = [TAY(), TAY({ id: ID(7), tham_so: { uid: UID2 } }), V({ id: ID(8), loai: "taovideo", trang_thai: "cho_duyet" }),
    TAY({ id: ID(9), loai: "voice_genmax" }), TAY({ id: ID10, phien_song: true })];
  const h = F.homNayHtml({ chu: true, nowMs: NOW, sk: SK_OK, viec: { ok: true, ds }, sp: { ok: true, ds: sp }, anh: () => "" });
  const k = khoiCanBan(h);
  assert.ok(k.includes(`data-hn-huy="${ID(5)}" data-hn-cu="1">Bỏ việc cũ`));
  assert.match(k, /Sản phẩm này đã có bộ cảnh quay/);
  assert.ok(!k.includes(`data-hn-tl="${ID(5)}"`));
  assert.ok(k.includes(`data-hn-tl="${ID(7)}">Thử lại`));
  assert.ok(k.includes(`data-hn-huy="${ID(7)}">Bỏ việc này`));
  for (const id of [ID(8), ID(9), ID10]) {
    assert.ok(!k.includes(`data-hn-tl="${id}"`) && !k.includes(`data-hn-huy="${id}"`), id);
    assert.ok(k.includes(`href="#/viec/${id}"`), id);
  }
});

test("P-32 Bắt đầu sản phẩm mới + Cách làm 4 bước: đặt dưới tiêu đề, trên mọi khối; form gắn onAdd", () => {
  const h = F.batDauHnHtml();
  assert.match(h, /<form class="add hn-add" id="form-hn-add">/);
  assert.match(h, /<input id="in-hn-link"[^>]*placeholder="Dán link sản phẩm TikTok Shop…"/);
  assert.match(h, /<button class="btn"[^>]*>Bắt đầu<\/button>/);
  assert.match(h, /id="hn-add-msg"/);
  const buoc = [...h.matchAll(/<li>([\s\S]*?)<\/li>/g)].map((m) => m[1]);
  assert.equal(buoc.length, 4);
  assert.match(buoc[0], /Dán link/);
  assert.match(buoc[1], /Đã quay/);
  assert.match(buoc[2], /Làm video/);
  assert.match(buoc[2], /tối đa/);
  assert.match(buoc[3], /duyệt ngay lúc tạo/);
  assert.match(buoc[3], /Poster V2/);
  assert.ok(!/\son[a-z]+=/i.test(h));
  // renderHomNay: ô Bắt đầu vẽ ngay (trước khi tải), dưới hàng tiêu đề, trước #hn-nd (mọi khối)
  const dom = HN.slice(HN.indexOf("// --- homnay-thuan end ---"));
  const f = dom.slice(dom.indexOf("async function renderHomNay"));
  const iH1 = f.indexOf('class="hn-h1"'), iBd = f.indexOf("${batDauHnHtml()}"), iNd = f.indexOf('id="hn-nd"'), iAwait = f.indexOf("await");
  assert.ok(iH1 > 0 && iH1 < iBd && iBd < iNd && iNd < iAwait, [iH1, iBd, iNd, iAwait].join(","));
  assert.match(f, /\$\("#form-hn-add"\)\.addEventListener\("submit", onAdd\)/);
});

test("P-32 onAdd: ô Hôm nay lưu xong / trùng → #/sp/<id>; lỗi báo dưới ô Hôm nay; chưa đăng nhập giữ linkCho + openLogin", () => {
  const f = APP.slice(APP.indexOf("async function onAdd("), APP.indexOf("// Đợt sale 11/11"));
  assert.match(f, /form-hn-add/);
  assert.match(f, /if \(!auth\.on\) \{ linkCho = raw; linkChoO = o;[^}]*openLogin\(\); return; \}/);
  const sau = f.slice(f.indexOf('await api("them"'));
  assert.match(sau, /if \(r\.trung\)[\s\S]*?location\.hash = `#\/sp\/\$\{encodeURIComponent\(r\.id\)\}`/);
  const nhanhHn = sau.slice(sau.indexOf('if (o === "hn")'));
  assert.match(nhanhHn, /location\.hash = `#\/sp\/\$\{encodeURIComponent\(r\.info\.id\)\}`/);
  assert.ok(nhanhHn.indexOf("location.hash") < nhanhHn.indexOf("renderList()"), "trang Hôm nay không gọi renderList");
  // kho cũ giữ nguyên
  assert.match(APP, /\$\("#form-add"\)\.addEventListener\("submit", onAdd\)/);
  assert.match(sau, /renderList\(\);\s*baoAdd\(cau, "ok"\)/);
  // Worker tự giao máy nhà phân tích → câu báo theo r.may; trang Hôm nay báo bằng toast TRƯỚC khi đổi trang
  assert.match(sau, /const cau = cauMayThem\(r\.may\)/);
  assert.match(nhanhHn, /toast\(cau\); location\.hash/);
  const cm = new Function(`${APP.slice(APP.indexOf("function cauMayThem("), APP.indexOf("async function onAdd("))}\nreturn cauMayThem;`)();
  assert.match(cm("tao"), /đã nhận/);
  assert.match(cm("trung"), /đang có việc/);
  for (const x of ["chua", undefined, "lạ"]) assert.match(cm(x), /Xử lý link mới/);
});

// Fixture: chạy onAdd/baoAdd THẬT của app.js (đoạn tachLink → onAdd) với DOM/API giả.
function dungOnAdd({ coO = ["#in-hn-link", "#form-hn-add button", "#hn-add-msg"], apiTra, authOn = true } = {}) {
  const src = APP.slice(APP.indexOf("// Lấy link từ đoạn chữ dán vào"), APP.indexOf("// Đợt sale 11/11"));
  const dom = Object.fromEntries(coO.map((s) => [s, { value: "", textContent: "", className: "", disabled: false }]));
  const ghi = { toasts: [], login: 0, renderList: 0, hash: "" };
  const auth = { on: authOn };
  const ns = {
    $: (s) => dom[s] || null, auth, toast: (m) => ghi.toasts.push(m), openLogin: () => { ghi.login++; },
    state: { list: [] }, NHAN: { cho: "Chờ xử lý" },
    renderList: () => { ghi.renderList++; if (dom["#in-link"]) dom["#in-link"].value = ""; }, // vẽ lại trang Kho = ô trống
    location: { set hash(h) { ghi.hash = h; }, get hash() { return ghi.hash; } },
    api: async (p, b) => apiTra(p, b),
  };
  const ten = Object.keys(ns);
  const f = new Function(...ten, `"use strict";\n${src}\nreturn { onAdd, lay: () => ({ linkCho, linkChoO }) };`);
  return { A: f(...ten.map((k) => ns[k])), dom, ghi, auth };
}
const suKienHn = () => ({ preventDefault() {}, currentTarget: { id: "form-hn-add" } });
const LINK = "Xem cái này https://vt.tiktok.com/ZSabc123/ nhé";

test("P-32b P2-2 + P3-4 onAdd: hết phiên ngầm (401) giữ linkCho để đăng nhập xong tự lưu; lỗi giữ link trong ô; không ô báo → toast", async () => {
  // 401 khi auth.on vẫn true (hết phiên ngầm)
  let x = dungOnAdd({ apiTra: async () => { throw Object.assign(new Error("Hết phiên đăng nhập — đăng nhập lại"), { status: 401 }); } });
  x.dom["#in-hn-link"].value = LINK;
  await x.A.onAdd(suKienHn());
  assert.deepEqual(x.A.lay(), { linkCho: LINK, linkChoO: "hn" });
  assert.equal(x.dom["#hn-add-msg"].textContent, "Hết phiên — đăng nhập lại, link sẽ tự lưu.");
  assert.equal(x.dom["#in-hn-link"].value, LINK, "link còn trong ô");
  assert.equal(x.dom["#form-hn-add button"].disabled, false);
  assert.equal(x.ghi.renderList, 0);
  // đăng nhập xong: luồng login gọi onAdd() không sự kiện → lưu lại đúng link đã giữ (cùng phạm vi), sang trang SP
  let gui = null;
  let lan = 0;
  x = dungOnAdd({ apiTra: async (p, b) => {
    if (lan++ === 0) throw Object.assign(new Error("401"), { status: 401 });
    gui = [p, b]; return { status: 200, info: { id: "1731898847922259456" } };
  } });
  x.dom["#in-hn-link"].value = LINK;
  await x.A.onAdd(suKienHn());
  x.dom["#in-hn-link"].value = "";
  await x.A.onAdd();
  assert.deepEqual(gui, ["them", { link: "https://vt.tiktok.com/ZSabc123/" }]);
  assert.equal(x.ghi.hash, "#/sp/1731898847922259456");
  // lỗi thường: báo dưới ô Hôm nay, giữ link trong ô, linkCho không bị gán
  x = dungOnAdd({ apiTra: async () => { throw Object.assign(new Error("Lỗi 502"), { status: 502 }); } });
  x.dom["#in-hn-link"].value = LINK;
  await x.A.onAdd(suKienHn());
  assert.equal(x.dom["#hn-add-msg"].textContent, "⚠ Lưu không được: Lỗi 502");
  assert.equal(x.dom["#hn-add-msg"].className, "add-msg loi");
  assert.equal(x.dom["#in-hn-link"].value, LINK);
  assert.deepEqual(x.A.lay(), { linkCho: "", linkChoO: "kho" });
  // lưu tự động sau đăng nhập khi trang hiện tại KHÔNG có ô báo (vd trang SP) → toast
  // (chỉ có ô nhập, không có ô báo #hn-add-msg — như khi đã sang trang khác)
  x = dungOnAdd({ coO: ["#in-hn-link"], authOn: false, apiTra: async () => { throw Object.assign(new Error("Lỗi 500"), { status: 500 }); } });
  x.dom["#in-hn-link"].value = LINK;
  await x.A.onAdd(suKienHn());
  assert.equal(x.ghi.toasts[0], "Đăng nhập xong sẽ tự lưu link này.");
  x.auth.on = true;
  x.dom["#in-hn-link"].value = ""; // trang vừa vẽ lại sau đăng nhập: ô trống
  await x.A.onAdd();
  assert.equal(x.ghi.toasts[1], "⚠ Lưu không được: Lỗi 500");
  assert.equal(x.dom["#in-hn-link"].value, LINK, "lưu tự động lỗi → link trở lại ô");
  // trang Kho: renderList vẽ lại làm trống ô → link phải được điền lại sau lỗi
  x = dungOnAdd({ coO: ["#in-link", "#form-add button", "#add-msg"], apiTra: async () => { throw Object.assign(new Error("Lỗi 502"), { status: 502 }); } });
  x.dom["#in-link"].value = LINK;
  await x.A.onAdd({ preventDefault() {}, currentTarget: { id: "form-add" } });
  assert.equal(x.ghi.renderList, 1);
  assert.equal(x.dom["#in-link"].value, LINK);
  assert.equal(x.dom["#add-msg"].textContent, "⚠ Lưu không được: Lỗi 502");
});

test("P-32 dòng SP: chặng là chữ thường 'Bước k/4 · Tên' (không còn dải ô giống nút); tên + ảnh là link #/sp/<id>; esc", () => {
  assert.equal(F.changChu(0), "Bước 1/4 · Chuẩn bị");
  assert.equal(F.changChu(1), "Bước 2/4 · Quay");
  assert.equal(F.changChu(3), "Bước 4/4 · Chấm và đăng");
  assert.equal(F.changChu(9), "Bước 1/4 · Chuẩn bị");
  assert.equal(F.changChu("x"), "Bước 1/4 · Chuẩn bị");
  const sp = { id: "a b/\"c", uid: UID, ten: BAN, trang_thai: "da_phan_tich" };
  const h = F.spHomNayHtml(sp, F.viecCuaSp([], UID), `x" onerror="alert(1)`);
  assert.ok(!/class="chang"|class="ch\b|<ol/.test(h), "không còn dải chặng dạng ô");
  assert.match(h, /<div class="small muted hn-chang">Bước 2\/4 · Quay<\/div>/);
  const href = esc(`#/sp/${encodeURIComponent(sp.id)}`);
  assert.match(h, new RegExp(`<a class="hn-anh-lk" href="${reEsc(href)}" tabindex="-1" aria-hidden="true"><img class="hn-anh"`));
  assert.ok(h.includes(`<a class="hn-sp-ten" href="${href}">${esc(BAN)}</a>`));
  assert.ok(!h.includes("<img src=x") && !/onerror="alert/.test(h));
  // SP không có id → tên/ảnh không thành link rỗng
  const k = F.spHomNayHtml({ ten: "SP" }, F.viecCuaSp([], UID), "");
  assert.ok(!/class="hn-sp-ten" href/.test(k) && /<div class="hn-sp-ten">SP<\/div>/.test(k));
  // changHtml vẫn còn cho trang SP (Bước tiếp theo)
  assert.match(F.buocTiepHtml(F.buocTiepTheo(null, "da_quay", false), ""), /class="chang"/);
  // CSS: chặng trên Hôm nay là chữ thường, không viền
  assert.match(CSS, /\.hn-chang \{[^}]*\}/);
  assert.ok(!/\.hn-chang \{[^}]*border/.test(CSS));
});

test("P-32 bamViecHn: kiểm RE_ID_VIEC_HN + viecTayHn, confirm khi huỷ, khoá nút trước await, ma_cau_hoi, 409/lỗi → toast lời thường + vẽ lại", () => {
  const dom = HN.slice(HN.indexOf("// --- homnay-thuan end ---"));
  const f = dom.slice(dom.indexOf("async function bamViecHn"));
  const iRe = f.indexOf("RE_ID_VIEC_HN.test("), iTay = f.indexOf("viecTayHn("), iKhoa = f.indexOf("hnDangGui.add(id)"), iAwait = f.indexOf("await");
  assert.ok(iRe > 0 && iTay > iRe && iKhoa > iTay && iKhoa < iAwait, [iRe, iTay, iKhoa, iAwait].join(","));
  assert.ok(f.indexOf("confirm(") > 0 && f.indexOf("confirm(") < iKhoa, "confirm trước khi khoá/gửi");
  assert.match(f, /\.disabled = true/);
  assert.match(f, /tra_loi: "da_lam_xong"/);
  assert.match(f, /maCauHoi\(v\)/);
  assert.match(f, /r\.status === 409/);
  assert.match(f, /catch (\(err\) )?\{/);
  assert.match(f, /toast\(/);
  assert.match(f, /phien === phienCT[^\n]*renderHomNay\(\)/);
  assert.ok(!/err\.message|r\.loi/.test(f), "không đưa chuỗi kỹ thuật của máy chủ lên toast");
  // listener click trên #hn mở rộng (không gắn thêm listener mới)
  assert.equal((dom.match(/\$\("#hn"\)\.addEventListener\("click"/g) || []).length, 1);
  assert.match(dom, /closest\("\[data-hn-tl\], \[data-hn-huy\]"\)/);
});

// Fixture: chạy renderHomNay + bamViecHn thật với DOM/API giả (không mạng). Đếm lời gọi API, kiểm khoá nút trước await.
function dungHn({ traVe = {}, xacNhan = true } = {}) {
  const goi = [], toasts = [], hop = [];
  const nutGia = (attrs) => ({ dataset: { ...attrs }, disabled: false, hasAttribute: (k) => k === "data-hn-huy" ? "hnHuy" in attrs : k === "data-hn-tl" ? "hnTl" in attrs : false });
  const S = { phienCT: 0, nut: [], ndNut: [], choApi: null };
  const el = (s) => ({ innerHTML: "", disabled: false, addEventListener() {}, querySelectorAll: () => (s === "#hn-nd" ? S.ndNut : []) });
  const ns = {
    $: (s) => el(s), toast: (m) => toasts.push(m), confirm: (m) => { hop.push(m); return xacNhan; },
    document: { querySelectorAll: () => S.nut },
    laChu: () => true, needLogin() {}, trangThai: () => "cho", anhBia: () => "", auth: { on: true }, onAdd() {},
    state: { list: [{ id: UID, uid: UID, ten: "SP", trang_thai: "da_phan_tich" }] },
    loadList: async () => { goi.push("ds"); },
    api: async (p, body) => {
      goi.push(body === undefined ? p : [p, body]);
      if (p === "viec?gioi_han=500") return { status: 200, viec: traVe.viec || [] };
      if (p === "suc-khoe") return { status: 200, may_nha: true };
      if (p === "hoc/bao-cao") return { status: 200, ngay: "2026-11-18", lan: { trang_thai: "xong" }, nguon: {} }; // D15: nguồn thứ 4
      // khi bị gọi tra-loi/huy: mọi nút của việc phải đã khoá
      if (S.nut.some((n) => !n.disabled)) throw new Error("chưa khoá nút trước await");
      if (S.choApi) await S.choApi;
      if (traVe.loi) throw Object.assign(new Error("Failed to fetch"), { status: 0 });
      return traVe.r || { status: 200 };
    },
  };
  const ten = Object.keys(ns);
  // phienCT là biến dùng chung của app.js → khai báo let cùng phạm vi (như trình duyệt); nạp NGUYÊN homnay.js (cả phần DOM).
  const f = new Function("esc", ...ten, `"use strict";\nlet phienCT = 0;\n${khoi(LOI, "loi-thuan")}\n${khoi(VIEC, "viec-thuan")}
${HN.replace(/^"use strict";$/m, "")}\nreturn { renderHomNay, bamViecHn };`);
  const H = f(esc, ...ten.map((k) => ns[k]));
  return { H, goi, toasts, hop, S, nutGia };
}

test("P-32 fixture: tải trang gọi đúng 4 nguồn (D15 + hoc/bao-cao); bấm Thử lại → khoá nút, gửi da_lam_xong + ma_cau_hoi, toast, vẽ lại (4 nguồn)", async () => {
  const v = TAY({ cau_hoi: { loai: "viec_tay", noi_dung: CAU_KHO, ma: "q0123456789ab" }, tham_so: { uid: UID2 } });
  const { H, goi, toasts, S, nutGia } = dungHn({ traVe: { viec: [v] } });
  await H.renderHomNay();
  assert.deepEqual(goi, ["ds", "viec?gioi_han=500", "suc-khoe", "hoc/bao-cao"]);
  goi.length = 0;
  const b = nutGia({ hnTl: v.id });
  S.nut = [b, nutGia({ hnHuy: v.id })];
  await H.bamViecHn(b);
  assert.deepEqual(goi[0], [`viec/${v.id}/tra-loi`, { tra_loi: "da_lam_xong", ma_cau_hoi: "q0123456789ab" }]);
  assert.ok(S.nut.every((n) => n.disabled), "khoá mọi nút của việc");
  assert.match(toasts[0], /Đã báo máy nhà thử lại/);
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(goi.slice(1), ["ds", "viec?gioi_han=500", "suc-khoe", "hoc/bao-cao"], "vẽ lại trang = tải lại đúng 4 nguồn");
});

test("P-32 fixture: Bỏ việc cũ → confirm rồi huy; huỷ confirm → không gọi; 409 / lỗi mạng → toast lời thường; id lạ / việc không còn viec_tay → không gửi", async () => {
  const v = TAY();
  let x = dungHn({ traVe: { viec: [v] } });
  await x.H.renderHomNay(); x.goi.length = 0;
  await x.H.bamViecHn(x.nutGia({ hnHuy: v.id, hnCu: "1" }));
  assert.match(x.hop[0], /Bỏ việc phân tích cũ/);
  assert.deepEqual(x.goi[0], [`viec/${v.id}/huy`, {}]);
  assert.match(x.toasts[0], /Đã bỏ việc này/);
  // không đồng ý confirm
  x = dungHn({ traVe: { viec: [v] }, xacNhan: false });
  await x.H.renderHomNay(); x.goi.length = 0;
  await x.H.bamViecHn(x.nutGia({ hnHuy: v.id }));
  assert.deepEqual(x.goi, []);
  // 409
  x = dungHn({ traVe: { viec: [v], r: { status: 409, loi: "Câu hỏi đã đổi (ma lệch) <b>" } } });
  await x.H.renderHomNay(); x.goi.length = 0;
  await x.H.bamViecHn(x.nutGia({ hnTl: v.id }));
  assert.match(x.toasts[0], /vừa thay đổi trên máy nhà/);
  assert.ok(!x.toasts[0].includes("<b>"));
  // lỗi mạng
  x = dungHn({ traVe: { viec: [v], loi: true } });
  await x.H.renderHomNay(); x.goi.length = 0;
  await x.H.bamViecHn(x.nutGia({ hnTl: v.id }));
  assert.match(x.toasts[0], /Chưa gửi được — mạng chập chờn/);
  // id sai mẫu → không gì cả; việc tốn tiền (không còn đủ điều kiện) → không gửi tra-loi
  x = dungHn({ traVe: { viec: [TAY({ loai: "taovideo" })] } });
  await x.H.renderHomNay(); x.goi.length = 0;
  await x.H.bamViecHn(x.nutGia({ hnTl: "../x" }));
  assert.deepEqual(x.goi, []);
  await x.H.bamViecHn(x.nutGia({ hnTl: v.id }));
  assert.ok(!x.goi.some((g) => Array.isArray(g)), "không gửi tra-loi/huy");
});

// ---------- P-32b (review R-32) ----------
test("P-32b P2-1: câu kho bẩn giữ tên file đầu + đếm file khác (kể cả '(+N)' của runner); không hứa tự xong; esc khi vẽ", () => {
  const dau = "Dữ liệu kho có thay đổi chưa đẩy: ";
  assert.equal(F.loiViecTay(dau + "data/a/info.json, data/b/x.md, data/c/y.md").cau,
    "Máy nhà có dữ liệu kho chưa lưu lên mạng (data/a/info.json và 2 file khác). Cần lưu hoặc bỏ thay đổi đó trên máy nhà rồi bấm Thử lại.");
  const muoi = Array.from({ length: 10 }, (_, i) => `data/${i}/f.md`).join(", ");
  assert.match(F.loiViecTay(`${dau}${muoi} (+5)`).cau, /\(data\/0\/f\.md và 14 file khác\)/);
  assert.equal(F.loiViecTay("Dữ liệu kho có thay đổi chưa đẩy").cau,
    "Máy nhà có dữ liệu kho chưa lưu lên mạng. Cần lưu hoặc bỏ thay đổi đó trên máy nhà rồi bấm Thử lại.");
  assert.ok(F.loiViecTay(dau + "x".repeat(400)).cau.length < 260, "tên file cắt ngắn");
  // tên file độc hại → esc ở nơi vẽ (dòng SP + khối Cần bạn)
  const v = TAY({ cau_hoi: { loai: "viec_tay", noi_dung: dau + BAN } });
  const h = F.homNayHtml({ chu: true, nowMs: NOW, sk: SK_OK, viec: { ok: true, ds: [v] },
    sp: { ok: true, ds: [{ id: UID, uid: UID, ten: "SP", trang_thai: "cho" }] }, anh: () => "" });
  assert.ok(!h.includes("<img src=x"));
  assert.equal(h.split(esc(BAN)).length - 1, 2, "tên file hiện (đã esc) ở cả Cần bạn lẫn dòng SP");
});

test("P-32b P3-1: câu việc tay '…bấm Đã làm xong' → 'Thử lại' khi Hôm nay có nút Thử lại; nơi khác giữ nguyên", () => {
  const nd = "Có khoá git cũ `x/.git/index.lock` (lần chạy trước bị ngắt). Kiểm không có cửa sổ git nào rồi xoá file này, bấm Đã làm xong";
  const v = TAY({ cau_hoi: { loai: "viec_tay", noi_dung: nd } });
  assert.match(F.cauViec(v), /bấm Thử lại$/);
  assert.ok(!/Đã làm xong/.test(F.cauViec(v)));
  const h = F.spHomNayHtml({ id: UID, uid: UID, ten: "SP", trang_thai: "cho" }, F.viecCuaSp([v], UID), "");
  assert.match(h, /bấm Thử lại/);
  assert.match(h, /data-hn-tl=/);
  // phiên sống (không có nút Thử lại tại chỗ) → giữ nguyên chữ runner
  assert.match(F.cauViec({ ...v, phien_song: true }), /bấm Đã làm xong$/);
});

test("P-32b P3-3: bước 3 Cách làm là câu chung theo khối 'Bước tiếp theo'", () => {
  const buoc = [...F.batDauHnHtml().matchAll(/<li>([\s\S]*?)<\/li>/g)].map((m) => m[1]);
  assert.equal(buoc[2], "Mở sản phẩm, bấm nút ở khối \"Bước tiếp theo\" (vd Làm video), xem chi phí tối đa rồi duyệt.");
});

test("P-32b P3-2 fixture: Tải lại trong lúc đang gửi → nút mới vẽ của việc đang gửi vẫn bị khoá", async () => {
  const v = TAY({ tham_so: { uid: UID2 } });
  const { H, S, nutGia } = dungHn({ traVe: { viec: [v] } });
  await H.renderHomNay();
  // nút "mới vẽ" mà #hn-nd trả về sau lần vẽ lại
  const moi = [nutGia({ hnTl: v.id }), nutGia({ hnHuy: v.id }), nutGia({ hnTl: ID(9) })];
  S.ndNut = moi;
  let mo;
  S.choApi = new Promise((r) => { mo = r; });
  const b = nutGia({ hnTl: v.id });
  S.nut = [b];
  const dangGui = H.bamViecHn(b);
  await H.renderHomNay(); // người dùng bấm Tải lại trong lúc tra-loi chưa về
  assert.equal(moi[0].disabled, true);
  assert.equal(moi[1].disabled, true);
  assert.equal(moi[2].disabled, false, "việc khác không bị khoá");
  mo();
  await dangGui;
});

// ---------- P-33: người không phải chủ kho (≠ nhan/comeofage) chỉ xem Kho sản phẩm ----------
const dongLaChu = APP.split("\n").find((l) => l.startsWith("const laChu = "));
assert.ok(dongLaChu, "không thấy const laChu trong app.js");
const NGUOI_THUONG = ["linh", "thu", "ai_moi"];
const CHU = ["nhan", "comeofage"];
const authGia = (user) => ({ user, ten: user, get on() { return !!this.user; } });
const theGia = (extra = {}) => ({ innerHTML: "", textContent: "", value: "", dataset: {}, disabled: false, hidden: false,
  classList: { toggle() {}, add() {}, remove() {} }, addEventListener() {}, setAttribute() {}, removeAttribute() {}, ...extra });

// Fixture: renderUser + danhDauNav thật của app.js. coKhung: nạp mnNavHtml/mnMuc thật của khung.js (menu trái, đợt 8).
const KHUNG = doc("khung.js");
const KHUNG_THUAN = new Function("esc", `"use strict";\n${khoi(KHUNG, "khung-thuan")}\nreturn { mnNavHtml, mnMuc };`)(esc);
function dungNav(user, hash, coKhung = false) {
  const src = APP.slice(APP.indexOf("function renderUser()"), APP.indexOf("function openLogin()"));
  const els = { "#user": theGia(), "#nav": theGia() };
  const goi = [], dang = [];
  const ns = {
    $: (s, el) => (el ? null : els[s] || null), auth: authGia(user), esc, location: { hash },
    document: { body: { dataset: {} }, querySelectorAll: () => [...els["#nav"].innerHTML.matchAll(/data-nav="([\w-]+)"/g)].map((m) => theGia({
      dataset: { nav: m[1] }, classList: { toggle: (c, on) => { if (on) dang.push(m[1]); } } })) },
    api: async (p) => { goi.push(p); return {}; }, state: {}, route() {}, openLogin() {}, capNhatHuyHieuViec: () => goi.push("huy-hieu"),
  };
  if (coKhung) Object.assign(ns, KHUNG_THUAN);
  const ten = Object.keys(ns);
  const R = new Function(...ten, `"use strict";\n${dongLaChu}\n${src}\nreturn { renderUser };`)(...ten.map((k) => ns[k]));
  R.renderUser();
  return { nav: els["#nav"].innerHTML, user: els["#user"].innerHTML, goi, dang, vai: ns.document.body.dataset.vai };
}

test("P-33 nav: người thường chỉ còn 'Kho sản phẩm' (không Hôm nay/Việc/Máy nhà, không gọi huy hiệu việc); chủ giữ 3 mục", () => {
  for (const u of NGUOI_THUONG) {
    for (const hash of ["", "#/", "#/kho", "#/la"]) {
      const x = dungNav(u, hash);
      assert.equal((x.nav.match(/<a\b/g) || []).length, 1, `${u}: nav đúng 1 mục`);
      assert.match(x.nav, /<a href="#\/kho" data-nav="kho">Kho sản phẩm<\/a>/);
      assert.ok(!/Hôm nay|#\/viec|href="#\/"/.test(x.nav), `${u}: còn mục chủ kho`);
      assert.ok(!/suc-khoe|Máy nhà/.test(x.user));
      assert.deepEqual(x.goi, [], "không gọi API việc cho huy hiệu");
      assert.deepEqual(x.dang, ["kho"], `${u} ${hash}: tô mục Kho (trang mặc định của họ là Kho)`);
    }
  }
  for (const u of CHU) {
    const x = dungNav(u, "#/");
    assert.equal((x.nav.match(/<a\b/g) || []).length, 3, `${u}: 3 mục`);
    assert.match(x.nav, /href="#\/" data-nav="hom-nay">Hôm nay/);
    assert.match(x.nav, /href="#\/viec" data-nav="viec"/);
    assert.match(x.user, /href="#\/suc-khoe"/);
    assert.deepEqual(x.goi, ["huy-hieu"]);
    assert.deepEqual(x.dang, ["hom-nay"]);
    assert.deepEqual(dungNav(u, "#/kho").dang, ["kho"]);
  }
});

test("P-33 nav khi đã nạp khung.js (menu trái): người thường vẫn đúng 1 mục 'Sản phẩm' (#/kho), không huy hiệu, không vai chủ; chủ 6 mục (mục 5 Poster V2, mục 6 Radar UID)", () => {
  for (const u of NGUOI_THUONG) {
    for (const hash of ["", "#/", "#/kho", "#/la", `#/sp/${UID}`]) {
      const x = dungNav(u, hash, true);
      assert.equal((x.nav.match(/<a\b/g) || []).length, 1, `${u}: nav đúng 1 mục`);
      assert.equal(x.nav, `<a href="#/kho" data-nav="kho">Sản phẩm</a>`);
      assert.ok(!/suc-khoe|Máy nhà/.test(x.user));
      assert.deepEqual(x.goi, [], "không gọi API việc cho huy hiệu");
      assert.deepEqual(x.dang, ["kho"], `${u} ${hash}`);
      assert.equal(x.vai, "thuong");
    }
    assert.deepEqual(dungNav(u, "#/viec", true).dang, [], `${u}: trang chủ kho không tô mục nào`);
  }
  for (const u of CHU) {
    const x = dungNav(u, "#/", true);
    assert.equal((x.nav.match(/<a\b/g) || []).length, 6, `${u}: 6 mục`);
    assert.equal(x.vai, "chu");
    assert.deepEqual(x.goi, ["huy-hieu"]);
    assert.deepEqual(x.dang, ["hom-nay"]);
    assert.ok(!/suc-khoe/.test(x.user), "đã có mục Máy nhà");
    assert.deepEqual(dungNav(u, "#/viec", true).dang, ["may-nha"]);
    assert.deepEqual(dungNav(u, `#/sp/${UID}`, true).dang, ["kho"]);
  }
});

// Fixture: route() thật của app.js; mọi hàm vẽ trang là giả, ghi lại lời gọi.
async function dungRoute(user, hash) {
  const src = APP.slice(APP.indexOf("async function route()"), APP.indexOf("window.addEventListener(\"hashchange\""));
  const goi = [];
  const app = theGia();
  const ghi = (ten) => async () => { goi.push(ten); };
  const ns = {
    $: (s) => (s === "#app" ? app : null), esc, auth: authGia(user), location: { hash },
    dungSua() {}, dungViec() {}, danhDauNav() {}, openLogin() {},
    renderDetail: ghi("renderDetail"), renderSua: ghi("renderSua"), renderSucKhoe: ghi("renderSucKhoe"), renderViec: ghi("renderViec"),
    renderViecChiTiet: ghi("renderViecChiTiet"), renderHomNay: ghi("renderHomNay"), renderList: () => goi.push("renderList"),
    loadList: async () => { goi.push("ds"); }, state: { list: [] }, api: async (p) => { goi.push("api:" + p); return {}; },
    // khung.js giả: chỉ nhận trang Máy nhà của chủ kho (người thường đi tiếp nhánh chặn của route())
    mnRoute: async (h, chu) => { if (chu && (h === "#/viec" || h === "#/suc-khoe")) { goi.push("mnRoute:" + h); return true; } return false; },
  };
  const ten = Object.keys(ns);
  const dongChiChu = APP.split("\n").find((l) => l.startsWith("const CHI_CHU_HTML = ")) || "";
  const route = new Function(...ten, `"use strict";\nlet phienCT = 0;\n${dongLaChu}\n${dongChiChu}\n${src}\nreturn route;`)(...ten.map((k) => ns[k]));
  await route();
  return { goi, html: app.innerHTML };
}

test("P-33 router: người thường mở #/ hay hash lạ → trang Kho; trang chủ kho (#/viec, #/viec/<id>, #/suc-khoe, #/sua) → câu 'chỉ dành cho chủ kho', không gọi API máy nhà", async () => {
  const VID = "j20261118100001abcd";
  for (const u of NGUOI_THUONG) {
    for (const h of ["", "#", "#/", "#/la", "#/kho"]) {
      const x = await dungRoute(u, h);
      assert.deepEqual(x.goi, ["ds", "renderList"], `${u} ${h}`);
    }
    for (const h of ["#/viec", `#/viec/${VID}`, "#/suc-khoe", `#/sua/${UID}/0123456789abcdef`]) {
      const x = await dungRoute(u, h);
      assert.deepEqual(x.goi, [], `${u} ${h}: không vẽ trang chủ kho, không gọi API`);
      assert.match(x.html, /Trang này chỉ dành cho chủ kho\. <a href="#\/kho">← Về kho<\/a>/);
    }
    assert.deepEqual((await dungRoute(u, `#/sp/${UID}`)).goi, ["renderDetail"], "trang SP vẫn mở được");
  }
  for (const u of CHU) {
    assert.deepEqual((await dungRoute(u, "#/")).goi, ["renderHomNay"]);
    assert.deepEqual((await dungRoute(u, "#/la")).goi, ["renderHomNay"]);
    assert.deepEqual((await dungRoute(u, "#/kho")).goi, ["ds", "renderList"]);
    // W-M3: nhánh #/viec, #/suc-khoe cũ trong route() đã xoá — khung.js (mnRoute) vẽ trang Máy nhà
    assert.deepEqual((await dungRoute(u, "#/viec")).goi, ["mnRoute:#/viec"]);
    assert.deepEqual((await dungRoute(u, `#/viec/${VID}`)).goi, ["renderViecChiTiet"]);
    assert.deepEqual((await dungRoute(u, "#/suc-khoe")).goi, ["mnRoute:#/suc-khoe"]);
    assert.deepEqual((await dungRoute(u, `#/sua/${UID}/0123456789abcdef`)).goi, ["renderSua"]);
  }
});

// Fixture: renderDetail thật của app.js với DOM/API giả. $ chỉ trả phần tử có id thật trong HTML đã vẽ.
async function dungDetail(user, tabNho = "video") {
  const src = APP.slice(APP.indexOf("// ---------- trang chi tiết ----------"), APP.indexOf("document.addEventListener(\"click\""));
  const goi = [], nho = [];
  const cache = new Map();
  const app = theGia(), panel = theGia();
  const coId = (id) => app.innerHTML.includes(`id="${id}"`) || panel.innerHTML.includes(`id="${id}"`);
  const $ = (s, el) => {
    if (el) return null;
    if (s === "#app") return app;
    if (s === "#panel") return coId("panel") ? panel : null;
    const m = s.match(/^#([\w-]+)$/);
    if (!m || !coId(m[1])) return null;
    if (!cache.has(s)) cache.set(s, theGia());
    return cache.get(s);
  };
  const info = { id: UID, uid: UID, link: "https://x.test/p", ten: "SP", thu_muc_may: "E:/bi_mat_may_nha", da_phan_tich: true,
    da_lam_video: { xong: true, so_video: 2, luc: "", poster: [{ folder: 1, nhan: "A", so_video: 2 }] } };
  const NHAN = { cho: "Chờ", da_phan_tich: "Đã phân tích", da_quay: "Đã quay", da_lam_video: "Đã làm video" };
  const ns = {
    $, esc, auth: authGia(user), window: {}, MutationObserver: class { observe() {} disconnect() {} },
    api: async (p) => { goi.push(p); return p.startsWith("sp/") ? { info, md: "# Cảnh", caps: "c1", douyin: null, vtk: [], duyet: [] } : {}; },
    document: { querySelectorAll: (s) => (s === ".tab" ? [...app.innerHTML.matchAll(/data-tab="(\w+)"/g)].map((m) => theGia({ dataset: { tab: m[1] } })) : []) },
    sessionStorage: { getItem: () => tabNho, setItem: (k, v) => nho.push(v) },
    NHAN, LOAI_QUAY: { oneshot: "Oneshot", review: "Review" }, TOOL: "kho.py",
    quay: (i, l) => i[`da_quay_${l}`] || { xong: false, boi: "", luc: "" }, trangThai: () => "da_phan_tich", doiTag: (s) => s, anhBia: () => "",
    gio: () => "", gioS: () => "", gioSua: () => "", switchHtml: (i, l) => `<label class="switch" data-quay="${i.id}" data-loai="${l}"></label>`,
    bindVideo() {}, bindSwitches() {}, ruiRoPanel: () => "<p>RUI-RO</p>", toast() {}, copy() {}, needLogin: () => true,
    tinhBuoc: () => [], buocHienTai: () => 0, veViecSp() {}, goiYViec: () => ({ nut: [] }),
    buocTiepTheo: (...a) => { goi.push("buocTiepTheo"); return a; }, buocTiepHtml: () => "<p>BT</p>",
  };
  const ten = Object.keys(ns);
  const R = new Function(...ten, `"use strict";\n${dongLaChu}\n${src}\nreturn { renderDetail };`)(...ten.map((k) => ns[k]));
  await R.renderDetail(UID);
  await new Promise((r) => setTimeout(r, 0));
  return { html: app.innerHTML, panel: panel.innerHTML, goi, nho, tabs: [...app.innerHTML.matchAll(/data-tab="(\w+)"/g)].map((m) => m[1]) };
}

test("P-33 trang SP: người thường không có 'Bước tiếp theo', 8 bước, khối việc, tab Làm video/Duyệt; giữ thông tin, công tắc Đã quay, 7 tab; không gọi API máy nhà", async () => {
  for (const u of NGUOI_THUONG) {
    const x = await dungDetail(u);
    assert.ok(!x.html.includes('id="buoc-tiep"'), `${u}: còn #buoc-tiep`);
    assert.ok(!/id="buoc8"|id="viec-sp"|Xem đủ 8 bước/.test(x.html), `${u}: còn 8 bước / khối việc`);
    assert.deepEqual(x.tabs, ["canh", "douyin", "cap", "tt", "vtk", "note"], u); // W-M3: Rủi ro gộp vào Tóm tắt
    assert.ok(!x.html.includes("#/dang/") && !x.html.includes("#/duyet/"), `${u}: không lộ link trang chủ kho`);
    assert.ok(!x.html.includes('id="vd-btns"'), `${u}: không có Tải về`);
    assert.ok(!x.html.includes("E:/bi_mat_may_nha") && !x.panel.includes("E:/bi_mat_may_nha"), `${u}: lộ thư mục máy nhà`);
    assert.ok(!/Thư mục máy nhà|tao-video-tu-canh-quay/.test(x.html + x.panel));
    // tab đã nhớ "video" (từ tài khoản chủ trước đó) → rơi về tab mặc định, không vẽ panel Làm video
    assert.deepEqual(x.nho, ["canh"]);
    assert.match(x.panel, /Cảnh/);
    assert.match(x.html, /<a href="#\/kho" class="small">← Về kho<\/a>/);
    assert.match(x.html, /data-quay="[^"]+" data-loai="oneshot"/);
    assert.match(x.html, /data-quay="[^"]+" data-loai="review"/);
    assert.match(x.html, /<dt>UID<\/dt>/);
    assert.match(x.html, /<dt>Video<\/dt>/);
    assert.deepEqual(x.goi, [`sp/${UID}`], `${u}: chỉ gọi /api/sp, không gọi video/viec`);
  }
  for (const u of CHU) {
    const x = await dungDetail(u);
    assert.ok(x.html.includes('id="buoc-tiep"') && x.html.includes('id="buoc8"') && x.html.includes('id="viec-sp"'), u);
    assert.deepEqual(x.tabs, ["canh", "douyin", "cap", "tt", "vtk", "video", "note"], u); // W-M3: bỏ tab Duyệt, Rủi ro
    assert.ok(!x.html.includes('id="vd-btns"'), `${u}: không còn Tải về trên trang SP`);
    assert.match(x.html, /<dt>Video<\/dt><dd>[^]*?<a href="#\/poster">Poster V2 →<\/a>/, `${u}: link Poster V2 ở dòng Video`);
    assert.deepEqual(x.nho, ["video"], `${u}: tab Làm video vẫn mở được`);
    assert.match(x.panel, /Thư mục máy nhà: E:\/bi_mat_may_nha/);
    assert.ok(x.goi.includes("buocTiepTheo"));
    assert.ok(x.goi.includes(`video/${UID}/tien-do`) && x.goi.includes(`video/${UID}/ds`), u);
  }
});

// ---------- W-M3: dọn trang SP, Bước tiếp theo trỏ Duyệt / Đăng ----------
test("2026-11-19 buocTiepTheo: bước 7 (Kiểm duyệt) luôn bỏ qua; bước 8 → trang:poster; không còn trang:duyet|dang", () => {
  const b = F.buocTiepTheo(8, "da_lam_video", true);
  assert.equal(b.nut.lam, "trang:poster");
  assert.equal(b.nut.nhan, "Mở Poster V2");
  assert.ok(!b.phu);
  assert.match(b.cau, /Poster V2/);
  // coSan (goiYViec) không đổi nút trang:… (chỉ nút viec:… mới bị chỉnh)
  assert.equal(F.buocTiepTheo(8, "da_lam_video", true, []).nut.lam, "trang:poster");
  for (let ht = 0; ht <= 8; ht++) assert.ok(!/tab:duyet|tab:ruiro|trang:duyet|trang:dang/.test(JSON.stringify(F.buocTiepTheo(ht, "da_lam_video", true))), `ht ${ht}`);
  const h = F.buocTiepHtml(b, "");
  assert.match(h, /<button type="button" class="btn" data-bt-lam="trang:poster">Mở Poster V2<\/button>/);
  assert.ok(!/data-bt-phu/.test(h));
  // nút phụ vẫn vẽ được (dạng chung) và chống XSS
  const x = F.buocTiepHtml({ chang: 3, cau: "c", nut: { nhan: "a", lam: "b" }, phu: { nhan: "<b>x", lam: '"><i>' } }, "");
  assert.ok(!x.includes("<b>x") && !x.includes('"><i>'));
});
test("2026-11-19 trang SP: bộ nghe Bước tiếp theo xử lý trang:poster → #/poster (không còn #/duyet, #/dang)", () => {
  const r = APP.slice(APP.indexOf("async function renderDetail("), APP.indexOf("document.addEventListener(\"click\""));
  const ng = r.slice(r.indexOf('$("#buoc-tiep")?.addEventListener'));
  assert.match(ng, /button\[data-bt-lam\], button\[data-bt-phu\]/);
  assert.match(ng, /lam\.startsWith\("trang:"\)/);
  assert.match(ng, /if \(trang === "poster"\) location\.hash = "#\/poster";/);
  assert.ok(!/#\/duyet|#\/dang|\(duyet\|dang\)/.test(r), "không còn link trang đã gỡ");
  // tab Duyệt / Rủi ro / Tải về đã gỡ khỏi trang SP; kho_tab cũ "ruiro" → "tt"
  assert.ok(!/data-tab="duyet"|data-tab="ruiro"|id="vd-btns"|bindVideo\(/.test(r));
  assert.match(r, /if \(k === "ruiro"\) k = "tt";/);
});
test("W-M3 trang SP fixture: tab đã nhớ 'ruiro' → Tóm tắt (có phần rủi ro); 'duyet' → tab mặc định", async () => {
  let x = await dungDetail("nhan", "ruiro");
  assert.deepEqual(x.nho, ["tt"]);
  assert.match(x.panel, /RUI-RO/);
  x = await dungDetail("linh", "ruiro");
  assert.deepEqual(x.nho, ["tt"]);
  assert.match(x.panel, /RUI-RO/, "người thường vẫn xem rủi ro như trước (trong Tóm tắt)");
  x = await dungDetail("nhan", "duyet");
  assert.deepEqual(x.nho, ["canh"]);
  assert.match(x.html, /📋 Tóm tắt &amp; rủi ro|📋 Tóm tắt & rủi ro/);
});

test("W-M3 thẻ kho hiện 'Bước k/4' theo hệ 4 chặng chung (không còn B7–8 Duyệt/Đăng)", () => {
  const card = APP.slice(APP.indexOf("function cardHtml("), APP.indexOf("// QR link sản phẩm"));
  assert.match(card, /changChu\(changTheoTrangThai\(tt\)\)/);
  assert.ok(!/BUOC_DS/.test(APP), "còn BUOC_DS");
  assert.equal(F.changChu(F.changTheoTrangThai("da_lam_video")), "Bước 4/4 · Chấm và đăng");
  assert.equal(F.changChu(F.changTheoTrangThai("cho")), "Bước 1/4 · Chuẩn bị");
});

test("2026-11-19 Hôm nay: SP đã làm video không có việc → nút #/sp/<id>; Cách làm dòng 4 trỏ Poster V2, không còn Duyệt video / Đăng bài", () => {
  const sp = { id: UID, uid: UID, ten: "SP", trang_thai: "da_lam_video" };
  assert.equal(F.dongSpHomNay(sp, F.viecCuaSp([], UID)).nut.href, `#/sp/${UID}`);
  assert.equal(F.dongSpHomNay({ ...sp, trang_thai: "da_quay" }, F.viecCuaSp([], UID)).nut.href, `#/sp/${UID}`);
  // có việc đang chạy → vẫn tới việc
  const dc = V({ id: ID(2), loai: "poster_day_folder", trang_thai: "dang_chay" });
  assert.equal(F.dongSpHomNay(sp, F.viecCuaSp([dc], UID)).nut.href, `#/viec/${ID(2)}`);
  const buoc = [...F.batDauHnHtml().matchAll(/<li>([\s\S]*?)<\/li>/g)].map((m) => m[1]);
  assert.match(buoc[3], /Poster V2/);
  assert.ok(!/Duyệt video|Đăng bài/.test(F.batDauHnHtml()));
});
test("W-M3 route(): đã xoá nhánh #/viec, #/suc-khoe chết + renderSucKhoe; giữ sucKhoeHtml", () => {
  const r = APP.slice(APP.indexOf("async function route()"), APP.indexOf("window.addEventListener(\"hashchange\""));
  assert.ok(!/renderSucKhoe|renderViec\(\)/.test(r));
  assert.ok(!/function renderSucKhoe/.test(APP));
  assert.match(APP, /function sucKhoeHtml\(/);
});

// ---------- Ô tìm sản phẩm ở trang Hôm nay ----------
test("khopTimHn: khớp tên bỏ dấu, UID, shop; chuỗi rỗng khớp mọi SP", () => {
  const sp = { ten: "Ví da nam đựng thẻ", uid: UID, shop: "TiNiPrinting", link: "https://x" };
  assert.ok(F.khopTimHn(sp, ""));
  assert.ok(F.khopTimHn(sp, "   "));
  assert.ok(F.khopTimHn(sp, "vi da"));
  assert.ok(F.khopTimHn(sp, "ĐỰNG"));
  assert.ok(F.khopTimHn(sp, UID.slice(5, 14)));
  assert.ok(F.khopTimHn(sp, "tiniprint"));
  assert.ok(!F.khopTimHn(sp, "nồi chiên"));
  assert.ok(!F.khopTimHn(null, "a"));
});

test("homNayHtml: tim lọc khối Sản phẩm, hiện hết kết quả, câu rỗng nói không khớp", () => {
  const ds = Array.from({ length: 30 }, (_, i) => ({ id: `1729706628656957${String(700 + i)}`, uid: `1729706628656957${String(700 + i)}`, ten: `Ví số ${i}`, trang_thai: "da_phan_tich" }));
  ds.push({ id: UID2, uid: UID2, ten: "Nồi chiên", trang_thai: "cho" });
  const t = { chu: false, nowMs: NOW, sp: { ok: true, ds } };
  const tatCa = F.homNayHtml(t);
  assert.match(tatCa, /Sản phẩm \(31\)/);
  assert.equal((tatCa.match(/class="hn-muc hn-an" hidden/g) || []).length, 11);
  const loc = F.homNayHtml({ ...t, tim: "noi chien" });
  assert.match(loc, /Sản phẩm khớp tìm kiếm \(1\)/);
  assert.match(loc, /Nồi chiên/);
  assert.ok(!/Ví số/.test(loc));
  const vi = F.homNayHtml({ ...t, tim: "ví" });
  assert.match(vi, /\(30\)/);
  assert.ok(!/hn-muc hn-an/.test(vi), "đang tìm thì không cắt 20 dòng");
  const rong = F.homNayHtml({ ...t, tim: `<b>${BAN}` });
  assert.match(rong, /Không thấy sản phẩm nào khớp/);
  assert.ok(!rong.includes(BAN), "chữ tìm phải được esc");
});

test("renderHomNay: ô tìm nằm ngoài #hn-nd, gõ chỉ vẽ lại từ dữ liệu đã tải", () => {
  const r = HN.slice(HN.indexOf("async function renderHomNay()"), HN.indexOf("async function bamViecHn("));
  assert.ok(r.indexOf('id="hn-tim"') > -1 && r.indexOf('id="hn-tim"') < r.indexOf('id="hn-nd"'));
  assert.match(r, /value="\$\{esc\(hnTim\)\}"/);
  assert.match(r, /#hn-tim"\)\.addEventListener\("input"[^\n]*veNdHn\(\)/);
  const ve = HN.slice(HN.indexOf("function veNdHn()"), HN.indexOf("async function renderHomNay()"));
  assert.ok(!/api\(|loadList\(/.test(ve), "gõ tìm không được gọi lại máy nhà");
});
