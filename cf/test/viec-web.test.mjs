// Test hàm thuần của web/viec.js (khối // --- viec-thuan start/end ---) + kiểm CSP tĩnh. Chạy: node --test cf/test/
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const doc = (p) => readFileSync(new URL(`../../web/${p}`, import.meta.url), "utf8");
const VIEC = doc("viec.js");
const APP = doc("app.js");

// esc thật lấy từ app.js (một dòng `const esc = ...`), tiêm vào khối thuần.
const dongEsc = APP.split("\n").find((l) => l.startsWith("const esc = "));
assert.ok(dongEsc, "không thấy const esc trong app.js");
const esc = new Function(`${dongEsc}\nreturn esc;`)();
const m = VIEC.match(/\/\/ --- viec-thuan start ---\n([\s\S]*?)\/\/ --- viec-thuan end ---/);
assert.ok(m, "thiếu marker viec-thuan trong viec.js");
const F = new Function("esc", `"use strict";\n${m[1]}\nreturn { goiYViec, nhomViec, nhanTrangThai, nutTraLoi, theViecHtml, chiTietViecHtml, tomTatHtml, dsNhomHtml, laIdViec, dongThamSo, idTrungViec, ketQuaHanhDong, buocLog, demCanBan, canDocLaiLog, LOG_DOC_LAI_TOI_DA };`)(esc);

const UID = "1729706628656957720";
const loaiCua = (g) => g.nut.map((x) => x.loai);

test("goiYViec: bảng §12 ở đợt 3", () => {
  const sp = { uid: UID, da_phan_tich: false };
  const coDy = { uid: UID, da_phan_tich: true, co_douyin: true };
  assert.deepEqual(loaiCua(F.goiYViec(2, sp, 3)), ["phan_tich_uid"]);
  assert.deepEqual(loaiCua(F.goiYViec(2, { uid: UID, da_phan_tich: true }, 3)), ["phan_tich_uid", "douyin_uid"]);
  assert.deepEqual(loaiCua(F.goiYViec(3, coDy, 3)), []);
  assert.match(F.goiYViec(3, coDy, 3).ghi_chu, /Việc của bạn: quay raw\/takes/);
  assert.deepEqual(loaiCua(F.goiYViec(4, coDy, 3)), []);          // muse_clip là đợt 4
  assert.deepEqual(loaiCua(F.goiYViec(5, coDy, 3)), ["voice_pv"]); // voice_genmax là đợt 4
  assert.deepEqual(loaiCua(F.goiYViec(6, coDy, 3)), []);          // taovideo là đợt 5
  assert.deepEqual(loaiCua(F.goiYViec(7, coDy, 3)), []);
  assert.match(F.goiYViec(7, coDy, 3).ghi_chu, /Duyệt/);
  assert.deepEqual(loaiCua(F.goiYViec(8, coDy, 3)), ["poster_day_folder"]);
  assert.deepEqual(loaiCua(F.goiYViec(0, coDy, 3)), []);
});

test("goiYViec: đợt 4/5 mở thêm nút", () => {
  const coDy = { uid: UID, co_douyin: true };
  assert.deepEqual(loaiCua(F.goiYViec(4, coDy, 4)), ["muse_clip"]);
  assert.deepEqual(loaiCua(F.goiYViec(5, coDy, 4)), ["voice_pv", "voice_genmax"]);
  assert.deepEqual(loaiCua(F.goiYViec(8, coDy, 4)), ["poster_day_folder", "poster_len_lich"]);
  assert.deepEqual(loaiCua(F.goiYViec(6, coDy, 4)), []);
  assert.deepEqual(loaiCua(F.goiYViec(6, coDy, 5)), ["taovideo"]);
});

test("goiYViec: qua bước 2 mà chưa có Douyin → luôn có nút phụ douyin_uid", () => {
  const sp = { uid: UID, da_phan_tich: true };
  assert.deepEqual(loaiCua(F.goiYViec(3, sp, 3)), ["douyin_uid"]);
  assert.deepEqual(loaiCua(F.goiYViec(5, sp, 3)), ["voice_pv", "douyin_uid"]);
  assert.deepEqual(loaiCua(F.goiYViec(0, sp, 3)), ["douyin_uid"]);
  assert.deepEqual(loaiCua(F.goiYViec(5, { ...sp, douyin: "# có" }, 3)), ["voice_pv"]);
});

test("goiYViec: không UID hợp lệ → không nút; tham số cần chọn đúng", () => {
  assert.deepEqual(F.goiYViec(2, { uid: "" }, 3).nut, []);
  assert.deepEqual(F.goiYViec(2, { uid: "123" }, 3).nut, []);
  assert.deepEqual(F.goiYViec(2, null, 3).nut, []);
  const v = F.goiYViec(5, { uid: UID, co_douyin: true }, 3).nut[0];
  assert.deepEqual(v.can, ["uid", "du_an", "me"]);
  assert.deepEqual(F.goiYViec(8, { uid: UID, co_douyin: true }, 3).nut[0].can, ["uid", "du_an"]);
});

test("nutTraLoi: cau_hoi ở đợt 3 → mảng rỗng; nút cố định đúng giá trị Worker nhận", () => {
  assert.deepEqual(F.nutTraLoi({ loai: "cau_hoi", noi_dung: "Gõ tên?" }, 3), []);
  assert.deepEqual(F.nutTraLoi({ loai: "viec_tay", noi_dung: "Mở Poster" }, 3), [{ nhan: "✓ Tôi đã làm xong", gia_tri: "da_lam_xong" }]);
  assert.deepEqual(F.nutTraLoi({ loai: "khong_ro" }, 3), [{ nhan: "▶ Tiếp tục", gia_tri: "tiep_tuc" }]);
  assert.deepEqual(F.nutTraLoi(null, 3), []);
  assert.deepEqual(F.nutTraLoi("không phải json", 3), []);
  assert.deepEqual(F.nutTraLoi({ loai: "la" }, 3), []);
});

test("nutTraLoi: chon — mỗi lựa chọn 1 nút; bỏ giá trị Worker sẽ từ chối", () => {
  const ch = { loai: "chon", lua_chon: ["A", "B", "A", "", 5, "x".repeat(121), "dòng\nmới", "x".repeat(120)] };
  assert.deepEqual(F.nutTraLoi(ch, 3).map((n) => n.gia_tri), ["A", "B", "x".repeat(120)]);
  assert.deepEqual(F.nutTraLoi(JSON.stringify({ loai: "chon", lua_chon: ["Có", "Không"] }), 3).map((n) => n.nhan), ["Có", "Không"]);
  assert.equal(F.nutTraLoi({ loai: "chon", lua_chon: ["1", "2", "3", "4", "5", "6", "7"] }, 3).length, 6);
});

test("nhomViec: chia 4 nhóm, gần đây mới nhất trước", () => {
  const g = F.nhomViec([
    { id: "a", trang_thai: "xong", cap_nhat_luc: "2026-11-17T10:00" },
    { id: "b", trang_thai: "can_tra_loi" },
    { id: "c", trang_thai: "dang_chay" },
    { id: "d", trang_thai: "cho", tao_luc: "2026-11-17T09:00" },
    { id: "e", trang_thai: "cho_duyet" },
    { id: "f", trang_thai: "loi", cap_nhat_luc: "2026-11-17T11:00" },
    { id: "g", trang_thai: "huy", cap_nhat_luc: "2026-11-17T08:00" },
    { id: "h", trang_thai: "cho", tao_luc: "2026-11-17T08:00" },
    null, 5,
  ]);
  assert.deepEqual(g.can_ban.map((x) => x.id).sort(), ["b", "e"]);
  assert.deepEqual(g.dang_chay.map((x) => x.id), ["c"]);
  assert.deepEqual(g.dang_cho.map((x) => x.id), ["h", "d"]);
  assert.deepEqual(g.gan_day.map((x) => x.id), ["f", "a", "g"]);
  assert.deepEqual(F.nhomViec(undefined), { can_ban: [], dang_chay: [], dang_cho: [], gan_day: [] });
});

test("nhanTrangThai: nhãn đủ 7 trạng thái; lạ → lớp cố định", () => {
  for (const tt of ["cho", "dang_chay", "can_tra_loi", "cho_duyet", "xong", "loi", "huy"]) {
    const n = F.nhanTrangThai(tt);
    assert.equal(n.lop, `tt-${tt}`);
    assert.ok(n.nhan && n.nhan !== tt);
  }
  assert.deepEqual(F.nhanTrangThai("x\" onmouseover=\"a"), { nhan: "x\" onmouseover=\"a", lop: "tt-khac" });
  assert.equal(F.nhanTrangThai("constructor").lop, "tt-khac");
});

const BAN = `<img src=x onerror=alert(1)>"'`;
test("dựng HTML: mọi chuỗi từ runner/agent đều qua esc", () => {
  const v = {
    id: "j20261117100000abcd", loai: BAN, trang_thai: "can_tra_loi", tao_boi: BAN, tao_luc: BAN, can_ban: BAN, ghi_chu: BAN, loi: BAN,
    tham_so: { uid: UID, x: BAN }, cau_hoi: { loai: "chon", noi_dung: BAN, lua_chon: [BAN] },
    ket_qua: { trang_thai_agent: BAN, tom_tat: BAN, file_ra: [BAN], co_lo_ngai: true, goi_y_viec: ["douyin_uid", BAN] },
  };
  const html = [
    F.theViecHtml(v),
    F.chiTietViecHtml({ viec: v, tra_loi: [{ luc: BAN, boi: BAN, noi_dung: BAN }], su_kien: [{ luc: BAN, tu: BAN, den: BAN, boi: BAN, ghi_chu: BAN }], xem_truoc: BAN }, { dotBat: 3 }),
    F.tomTatHtml({ phien_ban: BAN, canh_bao: [BAN], tam_dung_claude_den: BAN, lan: { gpu: { id: BAN, loai: BAN } } }),
    F.dsNhomHtml(F.nhomViec([v])),
  ].join("\n");
  assert.ok(!html.includes("<img"), "lọt thẻ <img chưa esc");
  assert.ok(html.includes("&lt;img src=x onerror=alert(1)&gt;&quot;&#39;"));
  assert.ok(!/<[^>]*\son[a-z]+=/i.test(html), "có thuộc tính on…= trong thẻ HTML");
});

test("theViecHtml: id sai mẫu thì không thành link", () => {
  assert.ok(F.theViecHtml({ id: "j20261117100000abcd", trang_thai: "xong", loai: "voice_pv" }).includes('href="#/viec/j20261117100000abcd"'));
  assert.ok(!F.theViecHtml({ id: "../../x", trang_thai: "xong" }).includes("href"));
});

test("chiTietViecHtml: nút theo trạng thái", () => {
  const id = "j20261117100000abcd";
  const html = (viec, opt = { dotBat: 3 }) => F.chiTietViecHtml({ viec: { id, loai: "phan_tich_uid", tham_so: { uid: UID }, ...viec } }, opt);
  // can_tra_loi viec_tay: nút Tôi đã làm xong + Huỷ
  let h = html({ trang_thai: "can_tra_loi", cau_hoi: { loai: "viec_tay", noi_dung: "Mở Poster" } });
  assert.match(h, /data-vj-tl="0"[^>]*>✓ Tôi đã làm xong/);
  assert.match(h, /data-vj-act="huy"/);
  // cau_hoi đợt 3: không nút trả lời, có hướng dẫn
  h = html({ trang_thai: "can_tra_loi", cau_hoi: { loai: "cau_hoi", noi_dung: "?" } });
  assert.ok(!h.includes("data-vj-tl"));
  assert.match(h, /chỉ trả lời bằng nút/);
  // loi có thể chạy tiếp
  h = html({ trang_thai: "loi", co_the_chay_tiep: true, loi: "x" });
  assert.match(h, /data-vj-act="chay-tiep"/); assert.match(h, /data-vj-act="chay-lai"/); assert.ok(!h.includes('data-vj-act="huy"'));
  h = html({ trang_thai: "loi", co_the_chay_tiep: false });
  assert.ok(!h.includes("chay-tiep"));
  // xong: không nút điều khiển
  h = html({ trang_thai: "xong" });
  assert.ok(!h.includes("data-vj-act"));
  // dang_chay: Huỷ
  assert.match(html({ trang_thai: "dang_chay" }), /data-vj-act="huy"/);
  // khoá: mọi nút disabled
  h = html({ trang_thai: "can_tra_loi", cau_hoi: { loai: "khong_ro" } }, { dotBat: 3, khoa: true });
  for (const b of h.match(/<button[^>]*>/g)) assert.match(b, /disabled/);
  // gợi ý douyin_uid từ kết quả
  h = html({ trang_thai: "xong", ket_qua: { trang_thai_agent: "DONE_WITH_CONCERNS", co_lo_ngai: true, goi_y_viec: ["douyin_uid"], tom_tat: "captcha" } });
  assert.match(h, /data-vj-goi-y="douyin_uid"/);
  // radar: md() được dùng cho tóm tắt; loại khác thì <pre>
  const md = (s) => `<p>MD:${esc(s)}</p>`;
  assert.ok(F.chiTietViecHtml({ viec: { id, loai: "radar_ban_tin", trang_thai: "xong", ket_qua: { tom_tat: "# a" } } }, { md }).includes("<p>MD:# a</p>"));
  assert.ok(!F.chiTietViecHtml({ viec: { id, loai: "voice_pv", trang_thai: "xong", ket_qua: { tom_tat: "# a" } } }, { md }).includes("MD:"));
});

const ID = "j20261117100000abcd";
const ID2 = "j20261117100001wxyz";

test("idTrungViec: 409 trung là object {id} hoặc chuỗi id; sai mẫu → rỗng", () => {
  assert.equal(F.idTrungViec({ status: 409, trung: { id: ID2, loai: "voice_pv" } }), ID2);
  assert.equal(F.idTrungViec({ status: 409, trung: ID2 }), ID2);
  assert.equal(F.idTrungViec({ status: 409, trung: { id: "../x" } }), "");
  assert.equal(F.idTrungViec({ status: 409 }), "");
  assert.equal(F.idTrungViec(null), "");
});

test("ketQuaHanhDong: huỷ có canh_bao (runner không dừng được tiến trình) → cảnh báo rõ, không báo 'Đã huỷ' trơn", () => {
  const cb = "Đã huỷ nhưng chưa dừng được tiến trình (OSError) — kiểm trên máy";
  const k = F.ketQuaHanhDong("huy", { status: 200, viec: { id: ID, trang_thai: "huy" }, canh_bao: cb }, ID);
  assert.equal(k.canhBao, cb);
  assert.match(k.toast, /^⚠ /);
  assert.ok(k.toast.includes("chưa dừng được tiến trình"));
  assert.equal(k.chuyen, "");
  const t = F.ketQuaHanhDong("huy", { status: 200, viec: { id: ID, trang_thai: "huy" } }, ID);
  assert.deepEqual(t, { toast: "Đã huỷ", chuyen: "", canhBao: "" });
  // canh_bao không phải chuỗi → bỏ qua
  assert.equal(F.ketQuaHanhDong("huy", { status: 200, canh_bao: { x: 1 } }, ID).canhBao, "");
});

test("ketQuaHanhDong: chạy lại bị 409 trùng → chuyển sang việc đang mở (như taoViec)", () => {
  let k = F.ketQuaHanhDong("chay-lai", { status: 409, loi: "đã có việc đang mở cùng loại và khoá", trung: { id: ID2, trang_thai: "dang_chay" } }, ID);
  assert.equal(k.chuyen, ID2);
  assert.ok(!k.toast.startsWith("⚠"));
  k = F.ketQuaHanhDong("chay-lai", { status: 409, trung: ID2 }, ID);
  assert.equal(k.chuyen, ID2);
  // 409 không có trung (vd. "chỉ chạy lại được việc lỗi hoặc đã huỷ") → chỉ báo lỗi
  k = F.ketQuaHanhDong("chay-lai", { status: 409, loi: "chỉ chạy lại được việc lỗi hoặc đã huỷ" }, ID);
  assert.deepEqual(k, { toast: "⚠ chỉ chạy lại được việc lỗi hoặc đã huỷ", chuyen: "", canhBao: "" });
  // 409 ở hành động khác: giữ hành vi cũ
  assert.deepEqual(F.ketQuaHanhDong("huy", { status: 409 }, ID), { toast: "⚠ Việc đã đổi trạng thái — tải lại", chuyen: "", canhBao: "" });
  // chạy lại thành công → sang việc mới
  k = F.ketQuaHanhDong("chay-lai", { status: 201, viec: { id: ID2 } }, ID);
  assert.deepEqual(k, { toast: "↻ Đã tạo việc chạy lại", chuyen: ID2, canhBao: "" });
  assert.equal(F.ketQuaHanhDong("chay-lai", { status: 201, viec: { id: ID } }, ID).chuyen, "");
});

test("chiTietViecHtml: opt.canhBao hiện khối cảnh báo (đã esc)", () => {
  const h = F.chiTietViecHtml({ viec: { id: ID, loai: "voice_pv", trang_thai: "huy" } }, { canhBao: BAN });
  assert.match(h, /vj-can-ban/);
  assert.ok(h.includes("&lt;img src=x onerror=alert(1)&gt;"));
  assert.ok(!h.includes("<img"));
  assert.ok(!F.chiTietViecHtml({ viec: { id: ID, loai: "voice_pv", trang_thai: "huy" } }, {}).includes("vj-can-ban"));
});

test("buocLog: đọc tiếp đến khi het; không tiến được thì dừng", () => {
  assert.deepEqual(F.buocLog({ tu: 0, den: 65536, noi_dung: "a", het: false }, 0), { tu: 65536, them: "a", het: false, con: true });
  assert.deepEqual(F.buocLog({ tu: 65536, den: 70000, noi_dung: "b", het: true }, 65536), { tu: 70000, them: "b", het: true, con: false });
  // đang chạy, chưa có dữ liệu mới: het=false nhưng rỗng → dừng vòng
  assert.deepEqual(F.buocLog({ tu: 10, den: 10, noi_dung: "", het: false }, 10), { tu: 10, them: "", het: false, con: false });
  // den lùi/hỏng → giữ tu cũ, không lặp vô hạn
  assert.deepEqual(F.buocLog({ den: "x", noi_dung: "c", het: false }, 50), { tu: 50, them: "c", het: false, con: false });
  assert.equal(F.buocLog(null, 0).het, true);
});

test("canDocLaiLog: việc đã dừng mà het=false → đọc lại, tối đa ~20 lần", () => {
  assert.equal(F.LOG_DOC_LAI_TOI_DA, 20);
  // runner chưa ghi xong đuôi log sau khi huỷ/kết thúc
  for (const tt of ["huy", "xong", "loi", "can_tra_loi", "cho_duyet", "cho"]) assert.equal(F.canDocLaiLog(tt, { het: false, con: false }, 0), true, tt);
  assert.equal(F.canDocLaiLog("huy", { het: false, con: false }, 19), true);
  // đủ 20 lần → dừng
  assert.equal(F.canDocLaiLog("huy", { het: false, con: false }, 20), false);
  assert.equal(F.canDocLaiLog("huy", { het: false, con: false }, 99), false);
  // đã het → dừng
  assert.equal(F.canDocLaiLog("huy", { het: true, con: false }, 0), false);
  // đang chạy: polling 3 s lo, không hẹn đọc lại
  assert.equal(F.canDocLaiLog("dang_chay", { het: false, con: false }, 0), false);
  // chưa biết trạng thái việc → không hẹn
  assert.equal(F.canDocLaiLog(undefined, { het: false, con: false }, 0), false);
  // còn dữ liệu đọc tiếp ngay (hết lượt 8 trang) → nút "Tải thêm" lo, không tự đọc
  assert.equal(F.canDocLaiLog("xong", { het: false, con: true }, 0), false);
  // lượt đọc lỗi (không có kết quả) → không hẹn; het phải đúng false, không suy từ giá trị khác
  assert.equal(F.canDocLaiLog("xong", null, 0), false);
  assert.equal(F.canDocLaiLog("xong", { het: undefined, con: false }, 0), false);
  assert.equal(F.canDocLaiLog("xong", { het: false, con: false }, "0"), false);
});

test("trang chi tiết: hẹn đọc lại log dùng canDocLaiLog + kiểm phienViec, cờ hẹn đặt trước khi hẹn", () => {
  const r = VIEC.slice(VIEC.indexOf("async function renderViecChiTiet("), VIEC.indexOf("// ---------- khối việc trong trang chi tiết SP"));
  assert.match(r, /canDocLaiLog\(/);
  assert.match(r, /setTimeout\(/);
  const hen = r.slice(r.indexOf("setTimeout("), r.indexOf("setTimeout(") + 300);
  assert.match(hen, /tk !== phienViec/);
});

test("demCanBan: huy hiệu = can_tra_loi + cho_duyet từ dem của tom_tat=1", () => {
  assert.equal(F.demCanBan({ cho: 4, can_tra_loi: 2, cho_duyet: 3, xong: 90 }), 5);
  assert.equal(F.demCanBan({ can_tra_loi: "x" }), 0);
  assert.equal(F.demCanBan(null), 0);
  assert.equal(F.demCanBan([1, 2]), 0);
});

test("#/viec: huy hiệu không đếm từ danh sách 50 việc", () => {
  const r = VIEC.slice(VIEC.indexOf("async function renderViec()"), VIEC.indexOf("async function renderViecChiTiet("));
  assert.ok(!/datHuyHieuViec\(list/.test(r), "còn đếm huy hiệu từ list");
  assert.match(r, /capNhatHuyHieuViec\(\)/);
  assert.match(VIEC, /api\("viec\?tom_tat=1"\)/);
});

test("tomTatHtml: lan là object {id, loai} hoặc chuỗi id", () => {
  let h = F.tomTatHtml({ lan: { gpu: { id: ID, loai: "voice_pv" }, nhe: ID2 } });
  assert.match(h, new RegExp(`GPU: <a href="#/viec/${ID}">bận · Voice PerfectVoice</a>`));
  assert.match(h, new RegExp(`Nhẹ: <a href="#/viec/${ID2}">bận</a>`));
  h = F.tomTatHtml({ lan: { gpu: null, nhe: { id: null, loai: null } } });
  assert.match(h, /GPU: rảnh/);
  assert.match(h, /Nhẹ: rảnh/);
  h = F.tomTatHtml({ lan: { nhe: { id: "sai", loai: "douyin_uid" } } });
  assert.match(h, /Nhẹ: bận · Tìm video Douyin/);
});

test("CSP: không script inline, không on…= trong viec.js/app.js/index.html", () => {
  assert.equal((VIEC.match(/on[a-z]+="/g) || []).length, 0);
  assert.equal((APP.match(/onclick=/g) || []).length, 0);
  assert.equal((APP.match(/\son[a-z]+="/g) || []).length, 0);
  const html = doc("index.html");
  assert.ok(!/<script(?![^>]*\ssrc=)[^>]*>/i.test(html), "có <script> không src");
  assert.match(html, /<script src="viec\.js\?v=\d+" defer><\/script>\s*<script src="app\.js\?v=\d+" defer>/);
});
