// Test W-M1 (đợt 8): khung menu trái web/khung.js + web/menu.css + móc trong app.js + chống trùng khai báo giữa các script (P2-7).
// Thiết kế: docs/giao-dien-menu-trai.md §2, §3, §6, §7, §9. Chạy: node --test cf/test/
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import vm from "node:vm";

const duong = (p) => new URL(`../../web/${p}`, import.meta.url);
const doc = (p) => readFileSync(duong(p), "utf8");
const APP = doc("app.js");
const VIEC = doc("viec.js");
const KHUNG = doc("khung.js");
const CSS = doc("menu.css");
const HTML = doc("index.html");

const dong = (src, dau) => {
  const l = src.split("\n").find((x) => x.startsWith(dau));
  assert.ok(l, `không thấy dòng bắt đầu bằng "${dau}"`);
  return l;
};
const esc = new Function(`${dong(APP, "const esc = ")}\nreturn esc;`)();
const SRC_QUAY = `${dong(APP, "const LOAI_QUAY = ")}\n${APP.slice(APP.indexOf("function quay(i, loai)"), APP.indexOf("function trangThai(i)"))}\n${dong(APP, "const soLoaiDaQuay = ")}`;
const CHI_CHU_HTML = new Function(`${dong(APP, "const CHI_CHU_HTML = ")}\nreturn CHI_CHU_HTML;`)();
const khoi = (src, ten) => {
  const m = src.match(new RegExp(`// --- ${ten} start ---\\n([\\s\\S]*?)// --- ${ten} end ---`));
  assert.ok(m, `thiếu marker ${ten}`);
  return m[1];
};
const BAN = `<img src=x onerror=alert(1)>`;
const UID = "1729706628656957720";

// Khối thuần: tiêm esc thật, quay/soLoaiDaQuay thật của app.js; cardHtml giả (ghi lại SP được vẽ).
const F = new Function("esc", "cardHtml", `"use strict";\n${SRC_QUAY}\n${khoi(KHUNG, "khung-thuan")}
return { mnMENU, mnMuc, mnNavHtml, mnDsCanQuay, mnCanQuayHtml, mnLOC_CQ, mnPhanTichHash };`)(esc, (x, stt) => `<div class="card" data-the="${esc(x.id)}">#${stt} ${esc(x.ten)}</div>`);

// ---------- mnMuc: bảng §2.3 ----------
test("mnMuc: đủ bảng §2.3 cho chủ kho và người thường", () => {
  const BANG = [
    // [hash, chủ, người thường]
    ["", "hom-nay", "kho"], ["#", "hom-nay", "kho"], ["#/", "hom-nay", "kho"],
    ["#/kho", "kho", "kho"], [`#/sp/${UID}`, "kho", "kho"], ["#/sp/tam-abc", "kho", "kho"],
    ["#/can-quay", "can-quay", ""],
    // 2026-11-19: #/duyet, #/dang (đã gỡ) chỉ còn là link cũ chuyển hướng → không tô mục nào; màn sửa thuộc Sản phẩm.
    ["#/duyet", "", ""], [`#/duyet/${UID}`, "", ""], [`#/sua/${UID}/0123456789abcdef`, "", ""],
    ["#/dang", "", ""], [`#/dang/${UID}`, "", ""],
    ["#/may-nha", "may-nha", ""], ["#/viec", "may-nha", ""], ["#/viec/j20261118100001abcd", "may-nha", ""], ["#/suc-khoe", "may-nha", ""],
    ["#/la", "", "kho"], ["#/khoxyz", "", "kho"], ["#/dangky", "", "kho"], ["#/viecx", "", "kho"], [`#/sua/${UID}`, "", "kho"],
  ];
  for (const [h, chu, thuong] of BANG) {
    assert.equal(F.mnMuc(h, true), chu, `chủ ${JSON.stringify(h)}`);
    assert.equal(F.mnMuc(h, false), thuong, `người thường ${JSON.stringify(h)}`);
  }
  assert.equal(F.mnMuc(undefined, true), "hom-nay");
  assert.equal(F.mnMuc(null, false), "kho");
});

// ---------- mnNavHtml ----------
test("mnNavHtml: chủ 5 mục đúng thứ tự (mục 5 Poster V2), có icon/nhãn/aria-label, huy hiệu viec-hh trên Máy nhà; người thường đúng 1 mục 'Sản phẩm'", () => {
  const h = F.mnNavHtml(true);
  const a = [...h.matchAll(/<a href="([^"]+)" data-nav="([\w-]+)" aria-label="([^"]+)"/g)].map((m) => [m[1], m[2], m[3]]);
  assert.deepEqual(a, [["#/", "hom-nay", "Hôm nay"], ["#/kho", "kho", "Sản phẩm"], ["#/can-quay", "can-quay", "Cần quay"],
    ["#/may-nha", "may-nha", "Máy nhà"], ["#/poster", "poster", "Poster V2"]]);
  assert.equal((h.match(/<a\b/g) || []).length, 5);
  assert.equal((h.match(/class="mn-ic" aria-hidden="true"/g) || []).length, 5);
  assert.ok(!/Duyệt video|Đăng bài|#\/duyet|#\/dang/.test(h), "đã gỡ Duyệt video + Đăng bài (2026-11-19)");
  assert.equal((h.match(/id="viec-hh"/g) || []).length, 1, "huy hiệu đúng 1 chỗ");
  assert.match(h, /data-nav="may-nha"(?:(?!<\/a>)[^])*<span class="huy-hieu" id="viec-hh" hidden><\/span><\/a><a href="#\/poster"/, "huy hiệu nằm trong mục Máy nhà");
  assert.match(h, /class="mn-ngan"[^>]*>Poster</, "nhãn ngắn cho thanh đáy");
  assert.ok(!/Kho sản phẩm/.test(h), "nhãn mới là 'Sản phẩm'");
  for (const m of F.mnMENU) assert.equal(F.mnMuc(m.href, true), m.ma, `href ${m.href} tô đúng mục ${m.ma}`);
  const t = F.mnNavHtml(false);
  assert.equal(t, `<a href="#/kho" data-nav="kho">Sản phẩm</a>`);
  assert.equal(F.mnNavHtml(undefined), t);
});

// ---------- Cần quay ----------
const SP = (id, x = {}) => ({ id, ten: id, trang_thai: "da_phan_tich", ...x });
const XONG = { xong: true, boi: "a", luc: "2026-11-18T09:00" };
test("mnDsCanQuay: chỉ SP da_phan_tich/da_quay; 3 chip; sắp chưa quay gì lên đầu (giữ thứ tự cũ trong nhóm)", () => {
  const list = [
    SP("cho", { trang_thai: "cho" }),
    SP("video", { trang_thai: "da_lam_video", da_quay_oneshot: XONG, da_quay_review: XONG }),
    SP("q-ca-hai", { trang_thai: "da_quay", da_quay_oneshot: XONG, da_quay_review: XONG }),
    SP("q-one", { trang_thai: "da_quay", da_quay_oneshot: XONG }),
    SP("pt1"),
    SP("q-review-cu", { trang_thai: "da_quay", da_quay: XONG }), // dữ liệu cũ: da_quay = review
    SP("pt2"),
    SP("khong-tt", { trang_thai: undefined, da_phan_tich: true }),
  ];
  const ids = (loc) => F.mnDsCanQuay(list, loc).map((x) => x.id);
  assert.deepEqual(ids("chua_gi"), ["pt1", "pt2", "khong-tt"]);
  assert.deepEqual(ids("chua_oneshot"), ["pt1", "pt2", "khong-tt", "q-review-cu"]);
  assert.deepEqual(ids("chua_review"), ["pt1", "pt2", "khong-tt", "q-one"]);
  assert.deepEqual(ids("la"), ids("chua_gi"), "chip lạ → mặc định");
  assert.deepEqual(F.mnDsCanQuay(null, "chua_gi"), []);
  assert.deepEqual(Object.keys(F.mnLOC_CQ), ["chua_gi", "chua_oneshot", "chua_review"]);
});

test("mnCanQuayHtml: chip có số đếm + chip đang chọn; thẻ dùng cardHtml; trống thì có câu; esc", () => {
  const list = [SP("a", { ten: BAN }), SP("b", { trang_thai: "da_quay", da_quay_review: XONG })];
  const h = F.mnCanQuayHtml(list, "chua_oneshot");
  assert.match(h, /data-mn-loc="chua_gi"[^>]*>[^<]*\(1\)/);
  assert.match(h, /class="chip on" data-mn-loc="chua_oneshot"[^>]*>[^<]*\(2\)/);
  assert.match(h, /data-mn-loc="chua_review"[^>]*>[^<]*\(1\)/);
  assert.equal((h.match(/class="card"/g) || []).length, 2);
  assert.ok(!h.includes(BAN), "tên SP đã esc");
  assert.match(F.mnCanQuayHtml([], "chua_gi"), /Không còn sản phẩm nào/);
});

// ---------- fixture DOM giả cho phần chạy của khung.js ----------
const theGia = (extra = {}) => ({ innerHTML: "", textContent: "", dataset: {}, disabled: false, hidden: false, isConnected: true, nghe: {},
  classList: { toggle() {}, add() {}, remove() {} }, addEventListener(ev, f) { this.nghe[ev] = f; }, setAttribute() {}, removeAttribute() {},
  insertAdjacentHTML(vt, html) { this.chen = (this.chen || []).concat([[vt, html]]); }, ...extra });

function dungKhung({ chu = true, list = [], apiGia, dg = false, dy = false, viTri = { replace: () => {} } } = {}) {
  const goi = [];
  const app = theGia();
  const dauKhung = theGia(), khung = theGia({ firstElementChild: dauKhung });
  const nut = {}; // phần tử theo id, tạo khi HTML đã vẽ có id đó
  const coId = (id) => app.innerHTML.includes(`id="${id}"`) || (dauKhung.chen || []).some(([, h]) => h.includes(`id="${id}"`));
  const $ = (s) => {
    if (s === "#app") return app;
    if (s === "#app .vt-khung") return app.innerHTML.includes("vt-khung") ? khung : null;
    const m = s.match(/^#([\w-]+)$/);
    if (!m || !coId(m[1])) return null;
    return (nut[m[1]] ||= theGia());
  };
  const state = { list: [...list] };
  const route = () => goi.push("route");
  route.reload = false;
  const ns = {
    $, esc, CHI_CHU_HTML, state, route, location: viTri, sessionStorage: { setItem: (k, v) => goi.push(`ss:${k}=${v}`) },
    document: { querySelectorAll: (s) => (s === "[data-mn-loc]" ? [...app.innerHTML.matchAll(/data-mn-loc="(\w+)"/g)].map((m) => theGia({ dataset: { mnLoc: m[1] } }))
      : s === "#app .card a.body" ? [...app.innerHTML.matchAll(/data-the="([^"]+)"/g)].map(() => theGia()) : []) },
    loadList: async () => { goi.push("ds"); state.list = [SP("moi")]; },
    cardHtml: (x, stt) => `<div class="card" data-the="${esc(x.id)}">#${stt} ${esc(x.ten)}</div>`,
    bindSwitches: () => goi.push("bindSwitches"),
    renderViec: () => {
      goi.push("renderViec");
      app.innerHTML = `<div class="vt-khung"><div class="row"><h2>⚙ Máy nhà</h2></div></div>`;
      return Promise.resolve();
    },
    api: apiGia || (async (p) => { goi.push("api:" + p); return { may_nha: true, apps: [] }; }),
    sucKhoeHtml: (d) => `<div class="sk-kq-gia">${d.may_nha ? "song" : "tat"}</div>`,
  };
  if (dg) Object.assign(ns, { dgRenderDs: async () => goi.push("dgRenderDs"), dgRender: async (id) => goi.push(`dgRender:${id}`), dgDung: () => goi.push("dgDung") });
  if (dy) Object.assign(ns, { dyRenderDs: async () => goi.push("dyRenderDs"), dyRender: async (id) => goi.push(`dyRender:${id}`), dyDung: () => goi.push("dyDung") });
  const ten = Object.keys(ns);
  const K = new Function(...ten, `"use strict";\nlet phienCT = 0;\n${SRC_QUAY}\n${KHUNG}
return { mnRoute, mnKiemSk, phien: () => phienCT, doiPhien: () => ++phienCT };`)(...ten.map((k) => ns[k]));
  return { K, goi, app, nut, dauKhung, chu };
}

const ROUTE_CHU = ["#/can-quay", "#/duyet", `#/duyet/${UID}`, "#/dang", `#/dang/${UID}`, "#/may-nha", "#/viec", "#/suc-khoe", "#/poster"];

test("mnRoute: người thường mở route chủ kho → CHI_CHU_HTML, trả true, không gọi API / không vẽ trang", async () => {
  for (const h of ROUTE_CHU) {
    const x = dungKhung({ chu: false, dg: true, dy: true });
    assert.equal(await x.K.mnRoute(h, false), true, h);
    assert.equal(x.app.innerHTML, CHI_CHU_HTML, h);
    assert.deepEqual(x.goi.filter((g) => !/Dung$/.test(g)), [], `${h}: không gọi gì ngoài dừng trang cũ`);
    assert.equal(x.K.phien(), 1, `${h}: tăng phienCT`);
  }
});

test("mnRoute: hash ngoài phạm vi trả false, không vẽ; không còn gọi dgDung/dyDung (2 trang đã gỡ)", async () => {
  for (const chu of [true, false]) {
    for (const h of ["", "#/", "#/kho", `#/sp/${UID}`, "#/viec/j20261118100001abcd", `#/sua/${UID}/0123456789abcdef`, "#/la", "#/dang/a/b", "#/can-quayx"]) {
      const x = dungKhung({ chu, dg: true, dy: true });
      assert.equal(await x.K.mnRoute(h, chu), false, `${chu} ${h}`);
      assert.deepEqual(x.goi, [], `${chu} ${h}`);
      assert.equal(x.app.innerHTML, "");
      assert.equal(x.K.phien(), 0);
    }
  }
});

test("mnRoute: link cũ #/dang, #/duyet (2 trang đã gỡ 2026-11-19) → có SP chuyển #/sp/<id>, không có → #/poster; không gọi dg*/dy*", async () => {
  for (const [h, dich] of [["#/dang", "#/poster"], ["#/duyet", "#/poster"], [`#/dang/${UID}`, `#/sp/${UID}`], ["#/duyet/tam%2Dx", "#/sp/tam%2Dx"]]) {
    const di = [];
    const x = dungKhung({ dg: true, dy: true, viTri: { replace: (u) => di.push(u) } });
    assert.equal(await x.K.mnRoute(h, true), true, h);
    assert.deepEqual(di, [dich], h);
    assert.deepEqual(x.goi, [], `${h}: không gọi trang cũ`);
  }
});

test("Cần quay: tải ds khi kho trống, vẽ thẻ + chip, gắn công tắc; bấm chip vẽ lại; bấm thẻ nhớ tab 'canh'", async () => {
  const x = dungKhung();
  assert.equal(await x.K.mnRoute("#/can-quay", true), true);
  assert.deepEqual(x.goi, ["ds", "bindSwitches"]);
  assert.match(x.app.innerHTML, /🎥 Cần quay/);
  assert.match(x.app.innerHTML, /data-the="moi"/);
  // đã có danh sách → không tải lại
  const y = dungKhung({ list: [SP("a"), SP("b", { trang_thai: "da_quay", da_quay_review: XONG })] });
  await y.K.mnRoute("#/can-quay", true);
  assert.deepEqual(y.goi, ["bindSwitches"]);
  assert.match(y.app.innerHTML, /data-the="a"/);
  assert.ok(!/data-the="b"/.test(y.app.innerHTML), "chip mặc định 'chưa quay gì'");
});

test("Cần quay: trang cũ về muộn (đã sang trang khác) thì không vẽ đè", async () => {
  const x = dungKhung(); // kho trống → phải chờ loadList; đổi phiên trong lúc chờ
  const p = x.K.mnRoute("#/can-quay", true);
  x.K.doiPhien();
  await p;
  assert.ok(!/Cần quay/.test(x.app.innerHTML), "không vẽ đè sau khi phiên đổi");
  assert.ok(!x.goi.includes("bindSwitches"));
});

test("Máy nhà: vẽ trang việc (renderViec) + chèn khối sức khoẻ dưới tiêu đề; khoá 'Kiểm lại' TRƯỚC await (bấm đúp chỉ gọi 1 lần)", async () => {
  let tra;
  const goiApi = [];
  const x = dungKhung({ apiGia: (p) => { goiApi.push(p); return new Promise((r) => { tra = r; }); } });
  const p = x.K.mnRoute("#/may-nha", true);
  assert.ok(x.goi.includes("renderViec"));
  const chen = x.dauKhung.chen || [];
  assert.equal(chen.length, 1);
  assert.equal(chen[0][0], "afterend");
  assert.match(chen[0][1], /<section id="mn-sk"/);
  assert.match(chen[0][1], /id="mn-sk-lai"/);
  const nut = x.nut["mn-sk-lai"];
  assert.equal(nut.disabled, true, "khoá ngay, trước khi API trả lời");
  x.K.mnKiemSk(x.K.phien()); // bấm lần 2 trong lúc đang kiểm
  assert.deepEqual(goiApi, ["suc-khoe"]);
  tra({ may_nha: true, apps: [] });
  assert.equal(await p, true);
  assert.equal(x.nut["mn-sk-kq"].innerHTML, `<div class="sk-kq-gia">song</div>`);
  assert.equal(nut.disabled, false);
});

test("Máy nhà: lỗi sức khoẻ → câu lỗi đã esc; #/viec và #/suc-khoe cũng ra Máy nhà", async () => {
  for (const h of ["#/viec", "#/suc-khoe"]) {
    const x = dungKhung({ apiGia: async () => { throw new Error(BAN); } });
    assert.equal(await x.K.mnRoute(h, true), true);
    assert.ok(x.goi.includes("renderViec"), h);
    const kq = x.nut["mn-sk-kq"].innerHTML;
    assert.match(kq, /Không kiểm được/);
    assert.ok(!kq.includes(BAN));
  }
});

// ---------- móc trong app.js (§2.4) ----------
const dongLaChu = dong(APP, "const laChu = ");
const K_THAT = new Function("esc", `"use strict";\n${khoi(KHUNG, "khung-thuan")}\nreturn { mnNavHtml, mnMuc };`)(esc);
function dungNavApp(user, hash, coKhung) {
  const src = APP.slice(APP.indexOf("function renderUser()"), APP.indexOf("function openLogin()"));
  const els = { "#user": theGia(), "#nav": theGia() };
  const body = { dataset: {} };
  const ns = {
    $: (s, el) => (el ? null : els[s] || null), auth: { user, ten: user, get on() { return !!this.user; } }, esc, location: { hash },
    document: { body, querySelectorAll: () => [] }, api: async () => ({}), state: {}, route() {}, openLogin() {}, capNhatHuyHieuViec() {},
  };
  if (coKhung) Object.assign(ns, K_THAT);
  const ten = Object.keys(ns);
  new Function(...ten, `"use strict";\n${dongLaChu}\n${src}\nreturn renderUser;`)(...ten.map((k) => ns[k]))();
  return { nav: els["#nav"].innerHTML, user: els["#user"].innerHTML, body };
}

test("app.js renderUser + danhDauNav: dùng mnNavHtml/mnMuc khi có khung.js; gán data-vai, data-trang; bỏ link 🩺 góc phải", () => {
  for (const u of ["linh", "thu"]) {
    const x = dungNavApp(u, "#/", true);
    assert.equal(x.nav, `<a href="#/kho" data-nav="kho">Sản phẩm</a>`, `${u}: đúng 1 mục Sản phẩm`);
    assert.equal(x.body.dataset.vai, "thuong");
    assert.equal(x.body.dataset.trang, "kho");
    assert.ok(!/suc-khoe|Máy nhà/.test(x.user));
  }
  for (const u of ["nhan", "comeofage"]) {
    const x = dungNavApp(u, `#/sua/${UID}/0123456789abcdef`, true);
    assert.equal((x.nav.match(/<a\b/g) || []).length, 5);
    assert.equal(x.body.dataset.vai, "chu");
    assert.equal(x.body.dataset.trang, "sua");
    assert.ok(!/suc-khoe/.test(x.user), "đã có mục Máy nhà, bỏ 🩺 góc phải");
    assert.equal(dungNavApp(u, "#/poster", true).body.dataset.trang, "poster");
  }
  // chưa nạp khung.js: giữ chuỗi cũ
  const cu = dungNavApp("nhan", "#/", false);
  assert.match(cu.nav, /href="#\/viec" data-nav="viec"/);
  assert.match(cu.user, /href="#\/suc-khoe"/);
  assert.equal(dungNavApp("", "#/", true).nav, "", "chưa đăng nhập: không có menu");
});

async function dungRouteApp(user, hash, mnRoute) {
  const src = APP.slice(APP.indexOf("async function route()"), APP.indexOf("window.addEventListener(\"hashchange\""));
  const goi = [];
  const app = theGia();
  const ghi = (ten) => async () => { goi.push(ten); };
  const ns = {
    $: (s) => (s === "#app" ? app : null), esc, auth: { user, ten: user, get on() { return !!this.user; } }, location: { hash },
    dungSua() {}, dungViec: () => goi.push("dungViec"), danhDauNav() {}, openLogin() {},
    renderDetail: ghi("renderDetail"), renderSua: ghi("renderSua"), renderSucKhoe: ghi("renderSucKhoe"), renderViec: ghi("renderViec"),
    renderViecChiTiet: ghi("renderViecChiTiet"), renderHomNay: ghi("renderHomNay"), renderList: () => goi.push("renderList"),
    loadList: async () => { goi.push("ds"); }, state: { list: [] }, mnRoute,
  };
  const ten = Object.keys(ns);
  const route = new Function(...ten, `"use strict";\nlet phienCT = 0;\n${dongLaChu}\n${dong(APP, "const CHI_CHU_HTML = ")}\n${src}\nreturn route;`)(...ten.map((k) => ns[k]));
  await route();
  return { goi, html: app.innerHTML };
}

test("app.js route(): gọi mnRoute sau dungViec; true → dừng; false → nhánh cũ; mnRoute ném → câu lỗi, không vỡ trang", async () => {
  const nhan = [];
  let x = await dungRouteApp("nhan", "#/can-quay", async (h, chu) => { nhan.push([h, chu]); return true; });
  assert.deepEqual(x.goi, ["dungViec"]);
  assert.deepEqual(nhan, [["#/can-quay", true]]);
  x = await dungRouteApp("linh", "#/dang", async (h, chu) => { nhan.push([h, chu]); return true; });
  assert.deepEqual(nhan[1], ["#/dang", false]);
  x = await dungRouteApp("nhan", "#/kho", async () => false);
  assert.deepEqual(x.goi, ["dungViec", "ds", "renderList"]);
  x = await dungRouteApp("nhan", `#/sp/${UID}`, async () => false);
  assert.deepEqual(x.goi, ["dungViec", "renderDetail"]);
  x = await dungRouteApp("nhan", "#/", async () => { throw new Error(BAN); });
  assert.match(x.html, /class="err"/);
  assert.ok(!x.html.includes(BAN));
  // W-M3: nhánh #/viec, #/suc-khoe cũ đã xoá (khung.js lo) — thiếu khung.js thì về Hôm nay, không lỗi
  x = await dungRouteApp("nhan", "#/viec", undefined);
  assert.deepEqual(x.goi, ["dungViec", "renderHomNay"]);
  x = await dungRouteApp("nhan", `#/viec/j20261118100001abcd`, undefined);
  assert.deepEqual(x.goi, ["dungViec", "renderViecChiTiet"], "link cũ #/viec/<id> vẫn chạy");
  x = await dungRouteApp("linh", "#/suc-khoe", undefined);
  assert.match(x.html, /chỉ dành cho chủ kho/);
});

// Fixture bindSwitches thật: api có thể chờ (cho) để đổi trang giữa chừng; route giả ghi lại + có thể chờ.
function dungSwitch({ hash = "#/can-quay", cho = null, choRoute = null } = {}) {
  const src = APP.slice(APP.indexOf("function bindSwitches()"), APP.indexOf("// Lấy link từ đoạn chữ dán vào"));
  const goi = [];
  const nut = theGia({ dataset: { id: "a", tag: "can_dang" }, classList: { contains: () => false, toggle() {}, add() {}, remove() {} } });
  const cb = theGia({ checked: true });
  const sw = theGia({ dataset: { quay: "a", loai: "oneshot" }, classList: { add() {}, remove() {} } });
  const location = { hash };
  const ns = {
    document: { querySelectorAll: (s) => (s === "[data-tag]" ? [nut] : s === "[data-quay]" ? [sw] : []) }, $: (s) => (s === "input" ? cb : null), needLogin: () => true,
    api: async (p) => { if (cho) await cho; return { info: p === "tag" ? { can_dang: true, cap_nhat_luc: "x" } : { da_quay_oneshot: { xong: true }, cap_nhat_luc: "x" } }; },
    state: { list: [{ id: "a" }] }, toast: (m) => goi.push("toast:" + m),
    TAG_RIENG: { can_dang: ["⬆", "Cần đăng"] }, LOAI_QUAY: { oneshot: "Oneshot" }, trangThai: () => "da_quay", confirm: () => true,
    renderList: () => goi.push("renderList"), route: async () => { goi.push("route"); if (choRoute) await choRoute; goi.push("route-xong"); }, location,
  };
  const ten = Object.keys(ns);
  const P = new Function(...ten, `"use strict";\nlet phienCT = 0;\n${src}\nreturn { bindSwitches, sang: () => ++phienCT };`)(...ten.map((k) => ns[k]));
  P.bindSwitches();
  return { P, goi, nut, cb, location, ns };
}

test("P2-5: gắn thẻ (bindSwitches thật) gọi route() — không vẽ đè trang kho lên trang Cần quay", async () => {
  const { nut, goi } = dungSwitch();
  await nut.nghe.click();
  assert.deepEqual(goi.filter((g) => !g.startsWith("toast")), ["route", "route-xong"], "await route() xong mới thôi");
});

test("W-M3 P3: bindSwitches — phản hồi về muộn sau khi đã đổi trang (hash hoặc phiên) → KHÔNG gọi route() vẽ đè", async () => {
  // gắn thẻ: đổi hash giữa chừng
  let mo; let x = dungSwitch({ cho: new Promise((r) => { mo = r; }) });
  let p = x.nut.nghe.click();
  x.location.hash = "#/dang";
  mo(); await p;
  assert.ok(!x.goi.includes("route"), "đổi hash → không vẽ lại");
  assert.ok(x.goi.some((g) => g.startsWith("toast:")), "vẫn báo đã gắn");
  // gắn thẻ: cùng hash nhưng phiên đã đổi (mở lại trang khác rồi quay về)
  x = dungSwitch({ cho: new Promise((r) => { mo = r; }) });
  p = x.nut.nghe.click();
  x.P.sang();
  mo(); await p;
  assert.ok(!x.goi.includes("route"), "đổi phiên → không vẽ lại");
  // gạt Đã quay: tương tự
  x = dungSwitch({ cho: new Promise((r) => { mo = r; }) });
  p = x.cb.nghe.change({});
  x.location.hash = "#/kho";
  mo(); await p;
  assert.ok(!x.goi.includes("route"), "gạt: đổi hash → không vẽ lại");
  // gạt Đã quay đúng trang → await route()
  x = dungSwitch();
  await x.cb.nghe.change({});
  assert.deepEqual(x.goi.filter((g) => !g.startsWith("toast")), ["route", "route-xong"]);
});

// ---------- CSS, index.html, viec.js ----------
test("menu.css: chỉ áp cho chủ kho; cột trái ≥900px; thanh đáy 6 ô không cuộn ngang, chừa safe-area; ẩn ở màn sửa; .sua-thanh né cột", () => {
  const boChuThich = CSS.replace(/\/\*[\s\S]*?\*\//g, "").replace(/@media[^{]*\{/g, "");
  const boChon = boChuThich.split("}").map((r) => r.split("{")[0].trim()).filter((s) => s && !s.startsWith(":root"));
  assert.ok(boChon.length >= 15, `đọc được ${boChon.length} bộ chọn`);
  for (const sel of boChon) {
    for (const s of sel.split(",")) assert.match(s.trim(), /^body\[data-(vai="chu"|trang="sua")\]/, `quy tắc không giới hạn vai: ${s}`);
  }
  assert.match(CSS, /@media \(min-width: 900px\)/);
  assert.match(CSS, /@media \(max-width: 899\.98px\)/);
  assert.match(CSS, /grid-auto-columns: minmax\(0, 1fr\)/);
  assert.match(CSS, /env\(safe-area-inset-bottom\)/);
  assert.match(CSS, /body\[data-trang="sua"\] \.nav \{ display: none; \}/);
  assert.match(CSS, /\.sua-thanh \{ left: var\(--mn-rong\)/);
  assert.match(CSS, /overflow-x: hidden/);
  assert.ok(!/overflow-x: (auto|scroll)/.test(boChuThich), "không cuộn ngang");
});

test("index.html: menu.css sau style.css, poster.css sau menu.css; script đúng thứ tự loi → homnay → viec → khung → poster → 9 pv-* → app → sua", () => {
  const css = [...HTML.matchAll(/<link rel="stylesheet" href="([^"?]+)/g)].map((m) => m[1]);
  assert.deepEqual(css, ["style.css", "menu.css", "poster.css"]);
  const js = [...HTML.matchAll(/<script src="([^"?]+)\?v=\d+" defer><\/script>/g)].map((m) => m[1]).filter((s) => !s.startsWith("vendor/"));
  assert.deepEqual(js, ["loi.js", "homnay.js", "viec.js", "khung.js", "poster.js", "pv-dashboard.js", "pv-accounts.js",
    "pv-folders.js", "pv-calendar.js", "pv-views.js", "pv-queue.js", "pv-post.js", "pv-logs.js", "pv-settings.js", "app.js", "sua.js"]);
  assert.ok(!/app\.js\?v=20"|viec\.js\?v=9"/.test(HTML), "đã nâng ?v app.js, viec.js");
});

test("viec.js (W-M1 chỉ chữ/link): trang việc là 'Máy nhà', link về Hôm nay; trang chi tiết về Máy nhà", () => {
  const rv = VIEC.slice(VIEC.indexOf("async function renderViec()"), VIEC.indexOf("// ---------- #/viec/<id> ----------"));
  assert.match(rv, /<a href="#\/" class="small">← Hôm nay<\/a>/);
  assert.match(rv, /<h2 class="sk-tieu-de">⚙ Máy nhà<\/h2>/);
  const ct = VIEC.slice(VIEC.indexOf("async function renderViecChiTiet("), VIEC.indexOf("async function renderViecChiTiet(") + 1200);
  assert.equal((ct.match(/<a href="#\/may-nha"[^>]*>← Máy nhà<\/a>/g) || []).length, 2);
  assert.ok(!/← Việc</.test(ct));
});

// ---------- P2-7: chống trùng khai báo giữa các script cùng phạm vi ----------
const SCRIPTS = [...HTML.matchAll(/<script src="([^"?]+)(?:\?[^"]*)?"/g)].map((m) => m[1]).filter((s) => !s.startsWith("vendor/"));
const THIEU = SCRIPTS.filter((s) => !existsSync(duong(s)));
const CO = SCRIPTS.filter((s) => existsSync(duong(s)));
// Poster V2 (docs/poster-v2-tren-web.md §6.3): poster.js "pv" + 9 trang con; pv-*.js chưa có (lượt sau) thì phần của file đó skip.
const TIEN_TO = { "khung.js": "mn", "poster.js": "pv",
  "pv-dashboard.js": "pvdb", "pv-views.js": "pvvi", "pv-logs.js": "pvlo", "pv-settings.js": "pvse", "pv-accounts.js": "pvac",
  "pv-post.js": "pvpo", "pv-folders.js": "pvfo", "pv-calendar.js": "pvca", "pv-queue.js": "pvqu" };
const tenDinh = (src) => [...src.matchAll(/^(?:async )?function\*? ?(\w+)|^(?:const|let|var|class) (\w+)/gm)].map((m) => m[1] || m[2]);

for (const f of THIEU) {
  test(`P2-7: ${f}`, { skip: `${f} chưa tồn tại (do phiếu song song / lượt sau viết) — bỏ qua phần kiểm của file này, khi có file test tự chạy` }, () => {});
}

test(`P2-7: nối các script theo index.html (${CO.join(", ")}) — vm.Script không lỗi, không tên cấp đỉnh trùng giữa 2 file, tiền tố mn/dg/dy/pv*`, () => {
  assert.ok(CO.includes("khung.js") && CO.includes("app.js"), "thiếu file bắt buộc");
  const noi = CO.map((f) => doc(f)).join("\n;\n");
  assert.doesNotThrow(() => new vm.Script(noi, { filename: "noi-script.js" }));
  const chu = new Map();
  for (const f of CO) {
    for (const t of new Set(tenDinh(doc(f)))) {
      assert.ok(!chu.has(t), `"${t}" khai báo ở cả ${chu.get(t)} và ${f}`);
      chu.set(t, f);
      // Hằng VIẾT_HOA dùng tiền tố hoa (DG_…, DY_…) cũng tính là đúng tiền tố: so không phân biệt hoa thường.
      if (TIEN_TO[f]) assert.ok(t.toLowerCase().startsWith(TIEN_TO[f]), `${f}: "${t}" phải bắt đầu bằng "${TIEN_TO[f]}"`);
    }
  }
  assert.ok([...chu.values()].filter((f) => f === "khung.js").length >= 7, "regex đọc được tên trong khung.js");
});

test("P2-7: bộ dò thật sự bắt được trùng tên (tự kiểm test)", () => {
  assert.deepEqual(tenDinh("function a() {}\nasync function b() {}\nconst c = 1;\nlet d;\nclass E {}\n  const khongDinh = 1;"), ["a", "b", "c", "d", "E"]);
  assert.throws(() => new vm.Script("const x = 1;\nconst x = 2;"));
});
