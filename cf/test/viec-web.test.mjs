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
const F = new Function("esc", `"use strict";\n${m[1]}\nreturn { goiYViec, nhomViec, nhanTrangThai, nutTraLoi, theViecHtml, chiTietViecHtml, tomTatHtml, dsNhomHtml, laIdViec, dongThamSo, idTrungViec, ketQuaHanhDong, buocLog, demCanBan, canDocLaiLog, LOG_DOC_LAI_TOI_DA,
  duocDuyet, khungDuyetHtml, loiDuyetMau, kiemLoiDuyet, dongUocTinh, thamSoMuse, thamSoPoster, locFolderPoster, formViecSpHtml, TEN_MAU_MUSE, LOI_DUYET_TOI_DA_WEB,
  nutChoViecTonTien, thamSoChuanDuyet, sha256HexWeb, duLieuViecDoi, hanMucHtml };`)(esc);
const WORKER = readFileSync(new URL("../src/worker.js", import.meta.url), "utf8");

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

// ---------- đợt 4 (W-5): duyệt + form tạo việc tốn tiền ----------
const VD = (x = {}) => ({ id: ID, loai: "muse_clip", trang_thai: "cho_duyet", tham_so: { uid: UID, du_an: "abcdef012345", mau: ["xoay_360", "mo_hop"], thoi_luong: 15, ti_le: "9:16" }, ...x });

test("duocDuyet: chỉ nhan/comeofage, trạng thái cho_duyet, loại tốn tiền", () => {
  for (const loai of ["muse_clip", "voice_genmax", "poster_len_lich", "taovideo"]) {
    assert.equal(F.duocDuyet(VD({ loai }), "nhan"), true, loai);
    assert.equal(F.duocDuyet(VD({ loai }), "comeofage"), true, loai);
  }
  for (const u of ["khach", "", undefined, null, "Nhan", "constructor"]) assert.equal(F.duocDuyet(VD(), u), false, String(u));
  for (const tt of ["cho", "dang_chay", "can_tra_loi", "xong", "loi", "huy", undefined]) assert.equal(F.duocDuyet(VD({ trang_thai: tt }), "nhan"), false, String(tt));
  for (const loai of ["voice_pv", "phan_tich_uid", "radar_ban_tin", "constructor", "__proto__", undefined]) assert.equal(F.duocDuyet(VD({ loai }), "nhan"), false, String(loai));
  assert.equal(F.duocDuyet(null, "nhan"), false);
  assert.equal(F.duocDuyet(undefined, "nhan"), false);
});

test("TEN_MAU_MUSE: đúng 7 mã mẫu của Worker (MA_MAU_MUSE), có nhãn tiếng Việt", () => {
  const mm = WORKER.match(/const MA_MAU_MUSE = (\[[^\]]*\]);/);
  assert.ok(mm, "không thấy MA_MAU_MUSE trong worker.js");
  const ma = JSON.parse(mm[1]);
  assert.deepEqual(Object.keys(F.TEN_MAU_MUSE), ma);
  for (const k of ma) assert.ok(F.TEN_MAU_MUSE[k] && F.TEN_MAU_MUSE[k] !== k);
});

test("loiDuyetMau: câu mẫu theo loại, có tham số chính, ≤ 2000 ký tự", () => {
  assert.equal(F.LOI_DUYET_TOI_DA_WEB, 2000);
  let s = F.loiDuyetMau(VD());
  assert.match(s, /2 clip/); assert.match(s, /15 giây/); assert.match(s, /abcdef012345/);
  s = F.loiDuyetMau(VD({ loai: "voice_genmax", tham_so: { uid: UID, du_an: "abcdef012345", me: "20261117-a" } }));
  assert.match(s, /GenMax/); assert.match(s, /20261117-a/);
  s = F.loiDuyetMau(VD({ loai: "poster_len_lich", tham_so: { folder_id: 42, so_video_ngay: 3 } }));
  assert.match(s, /42/); assert.match(s, /3 video\/ngày/);
  assert.match(F.loiDuyetMau(VD({ loai: "poster_len_lich", tham_so: { folder_id: 42, so_video_ngay: 87 } })), /87 video\/ngày/);
  // khung duyệt poster hiện đúng số (lấy từ tham_so_chuan)
  const hp = F.khungDuyetHtml({ viec: VD({ loai: "poster_len_lich", tham_so: { folder_id: 42, so_video_ngay: 87 } }), tham_so_chuan: '{"folder_id":42,"so_video_ngay":87}' }, {});
  assert.match(hp, /<dd>87 video\/ngày<\/dd>/); assert.match(hp, /87 video\/ngày\.<\/textarea>/);
  assert.ok(F.loiDuyetMau(VD({ loai: "taovideo", tham_so: {} })).length > 0);
  assert.ok([...F.loiDuyetMau(VD({ tham_so: { du_an: "x".repeat(5000), mau: [] } }))].length <= 2000);
  assert.ok(F.loiDuyetMau(null).length > 0);
});

test("kiemLoiDuyet: 1–2000 ký tự (code point), không rỗng", () => {
  assert.equal(F.kiemLoiDuyet("Đồng ý"), "");
  assert.notEqual(F.kiemLoiDuyet(""), "");
  assert.notEqual(F.kiemLoiDuyet("   \n "), "");
  assert.notEqual(F.kiemLoiDuyet(null), "");
  assert.equal(F.kiemLoiDuyet("😀".repeat(2000)), "");   // 2000 code point (4000 đơn vị UTF-16) vẫn hợp lệ
  assert.notEqual(F.kiemLoiDuyet("a".repeat(2001)), "");
});

test("dongUocTinh: ket_qua.uoc_tinh (object/chuỗi), uoc_tinh của việc, xem_truoc — không trùng", () => {
  const d = { viec: VD({ loai: "voice_genmax", ket_qua: { uoc_tinh: { so_ban: 12, ky_tu: 3400, credit: 50 } } }) };
  const ds = F.dongUocTinh(d);
  assert.ok(ds.includes("Số bản: 12"), ds.join("|"));
  assert.ok(ds.includes("Ký tự: 3400"));
  assert.ok(ds.includes("Credit: 50"));
  assert.deepEqual(F.dongUocTinh({ viec: VD({ uoc_tinh: "12 bản" }), xem_truoc: "12 bản" }), ["12 bản"]);
  assert.deepEqual(F.dongUocTinh({ viec: VD({ uoc_tinh: JSON.stringify({ so_ban: 3 }) }) }), ["Số bản: 3"]);
  assert.deepEqual(F.dongUocTinh({ viec: VD() }), []);
  assert.deepEqual(F.dongUocTinh(null), []);
});

test("khungDuyetHtml: đủ thành phần, mật khẩu không có value, nút khoá khi đang gửi, mọi chuỗi qua esc", () => {
  const d = { viec: VD({ ket_qua: { uoc_tinh: { so_ban: 4 } } }), tham_so_chuan: JSON.stringify(VD().tham_so) };
  const sk = { han_muc: { muse_clip_moi_viec: 10, muse_clip_ngay: 15, genmax_viec_ngay: 2 } };
  let h = F.khungDuyetHtml(d, { sk });
  assert.match(h, /B-roll AI \(Muse\)/);
  assert.match(h, /Xoay 360° nền trơn/); assert.match(h, /Mở hộp/);
  assert.match(h, /15 giây/);
  assert.match(h, /Số bản: 4/);
  assert.match(h, /15 clip\/ngày/);                      // hạn mức từ /suc-khoe
  assert.ok(!h.includes("việc GenMax"), "không hiện hạn mức của loại khác");
  const pw = h.match(/<input[^>]*type="password"[^>]*>/);
  assert.ok(pw, "thiếu ô mật khẩu");
  assert.match(pw[0], /autocomplete="current-password"/);
  assert.ok(!/\svalue=/.test(pw[0]), "ô mật khẩu không được có value");
  const ta = h.match(/<textarea[^>]*>([\s\S]*?)<\/textarea>/);
  assert.ok(ta, "thiếu ô Lời duyệt");
  assert.match(ta[0], /maxlength="2000"/);
  assert.equal(ta[1], esc(F.loiDuyetMau(d.viec)));
  assert.match(h, /data-vd-act="duyet"[^>]*>[^<]*Duyệt &amp; chạy/);
  assert.match(h, /data-vd-act="tu-choi"/);
  for (const b of h.match(/<button[^>]*>/g)) assert.ok(!/disabled/.test(b));
  h = F.khungDuyetHtml(d, { sk, khoa: true });
  for (const b of h.match(/<button[^>]*>/g)) assert.match(b, /disabled/);
  // chuỗi xấu từ runner
  h = F.khungDuyetHtml({ viec: VD({ loai: "voice_genmax", tham_so: { uid: UID, du_an: BAN, me: BAN }, uoc_tinh: BAN, ket_qua: { uoc_tinh: { [BAN]: BAN } } }), xem_truoc: BAN }, { sk: { han_muc: { genmax_viec_ngay: BAN } } });
  assert.ok(!h.includes("<img"), "lọt thẻ <img");
  assert.ok(h.includes("&lt;img src=x onerror=alert(1)&gt;"));
  assert.ok(!/<[^>]*\son[a-z]+=/i.test(h), "có thuộc tính on…=");
  // mẫu lạ: hiện mã đã esc, không vỡ
  h = F.khungDuyetHtml({ viec: VD({ tham_so: { mau: [BAN, "xoay_360"] } }) }, {});
  assert.ok(!h.includes("<img"));
});

test("chiTietViecHtml: cho_duyet có khung duyệt riêng → không vẽ khối cũ; không có → giữ nút Từ chối", () => {
  const d = { viec: VD() };
  let h = F.chiTietViecHtml(d, { dotBat: 4, khungDuyet: true });
  assert.ok(!h.includes('data-vj-act="tu-choi"'));
  assert.ok(!h.includes("mở ở đợt 4"));
  assert.match(h, /data-vj-act="huy"/); // vẫn huỷ được
  h = F.chiTietViecHtml({ viec: VD({ loai: "voice_pv", uoc_tinh: "3 bản" }) }, { dotBat: 4 });
  assert.match(h, /data-vj-act="tu-choi"/);
  assert.match(h, /3 bản/);
});

test("ketQuaHanhDong: duyệt thành công → toast đã duyệt; 409 → báo đổi trạng thái", () => {
  assert.match(F.ketQuaHanhDong("duyet", { status: 200, viec: { id: ID, trang_thai: "cho" } }, ID).toast, /Đã duyệt/);
  assert.equal(F.ketQuaHanhDong("duyet", { status: 200, viec: { id: ID2 } }, ID).chuyen, "");
  assert.deepEqual(F.ketQuaHanhDong("duyet", { status: 409, loi: "Việc không còn chờ duyệt" }, ID), { toast: "⚠ Việc không còn chờ duyệt", chuyen: "", canhBao: "" });
});

test("thamSoMuse: dự án 12 hex, 1–7 mẫu không trùng trong danh mục, thời lượng 10|15, tỉ lệ 9:16", () => {
  const r = F.thamSoMuse(UID, "abcdef012345", ["xoay_360", "mo_hop"], 15);
  assert.deepEqual(r, { tham_so: { uid: UID, du_an: "abcdef012345", mau: ["xoay_360", "mo_hop"], thoi_luong: 15, ti_le: "9:16" } });
  assert.ok(F.thamSoMuse(UID, "abcdef012345", [], 10).loi);
  assert.ok(F.thamSoMuse(UID, "abcdef012345", ["xoay_360", "xoay_360"], 10).loi);
  assert.ok(F.thamSoMuse(UID, "abcdef012345", ["la"], 10).loi);
  assert.ok(F.thamSoMuse(UID, "abcdef012345", ["constructor"], 10).loi);
  assert.ok(F.thamSoMuse(UID, "abcdef012345", ["xoay_360"], 12).loi);
  assert.ok(F.thamSoMuse(UID, "abcdef012345", ["xoay_360"], "10").loi);
  assert.ok(F.thamSoMuse(UID, "ABC", ["xoay_360"], 10).loi);
  assert.ok(F.thamSoMuse("123", "abcdef012345", ["xoay_360"], 10).loi);
  // giữ thứ tự danh mục, không phụ thuộc thứ tự bấm
  assert.deepEqual(F.thamSoMuse(UID, "abcdef012345", ["mo_hop", "xoay_360"], 10).tham_so.mau, ["xoay_360", "mo_hop"]);
});

test("thamSoPoster: folder_id số nguyên dương < 1e9 (chuỗi từ dropdown/ô số), so_video_ngay 1–100", () => {
  assert.deepEqual(F.thamSoPoster("42", "3"), { tham_so: { folder_id: 42, so_video_ngay: 3 } });
  assert.deepEqual(F.thamSoPoster(7, 1), { tham_so: { folder_id: 7, so_video_ngay: 1 } });
  assert.deepEqual(F.thamSoPoster("42", "6"), { tham_so: { folder_id: 42, so_video_ngay: 6 } });
  assert.deepEqual(F.thamSoPoster("42", "100"), { tham_so: { folder_id: 42, so_video_ngay: 100 } });
  assert.match(F.thamSoPoster("42", "101").loi, /1 đến 100/);
  for (const [f, n] of [["", 1], ["0", 1], ["-1", 1], ["1.5", 1], ["1e3", 1], ["1000000000", 1], ["abc", 1], ["42", 0], ["42", 101], ["42", "1000"], ["42", ""], ["42", "-3"], ["42", "2.5"], [null, 2]]) {
    assert.ok(F.thamSoPoster(f, n).loi, `${f}/${n}`);
  }
});

test("locFolderPoster: chỉ giữ {id nguyên dương, ten chuỗi}", () => {
  const r = { folders: [{ id: 1, ten: "A" }, { id: "2", ten: "B" }, { id: 0, ten: "C" }, { id: 3 }, null, { id: 4, ten: BAN }, { id: 1e9, ten: "x" }] };
  assert.deepEqual(F.locFolderPoster(r), [{ id: 1, ten: "A" }, { id: 3, ten: "#3" }, { id: 4, ten: BAN }]);
  assert.deepEqual(F.locFolderPoster(null), []);
  assert.deepEqual(F.locFolderPoster({ folders: "x" }), []);
});

test("formViecSpHtml: muse (checkbox 7 mẫu, thời lượng), poster (dropdown folder, số video/ngày), esc, không on…=", () => {
  let h = F.formViecSpHtml({ loai: "muse_clip", nhan: BAN, mau: ["can_canh"], thoi_luong: 15 }, {});
  assert.equal((h.match(/type="checkbox"/g) || []).length, 7);
  assert.match(h, /data-vs-mau="can_canh" checked/);
  assert.ok(!/data-vs-mau="xoay_360" checked/.test(h));
  assert.match(h, /data-vs-tl="15" checked/);
  assert.match(h, /data-vs-gui="muse_clip"/);
  assert.ok(!h.includes("<img"));
  h = F.formViecSpHtml({ loai: "poster_len_lich", folder_id: 4, so_video_ngay: 2 }, { folders: [{ id: 1, ten: "A" }, { id: 4, ten: BAN }] });
  assert.match(h, /<select[^>]*data-vs-folder/);
  assert.match(h, /<option value="4" selected>/);
  // số video/ngày: ô nhập số 1–100 (không còn dropdown 1–5)
  assert.ok(!/<select[^>]*data-vs-so/.test(h), "còn dropdown số video/ngày");
  const oSo = h.match(/<input[^>]*data-vs-so[^>]*>/);
  assert.ok(oSo, "thiếu ô nhập số video/ngày");
  assert.match(oSo[0], /type="number"/); assert.match(oSo[0], /min="1"/); assert.match(oSo[0], /max="100"/); assert.match(oSo[0], /value="2"/);
  assert.match(F.formViecSpHtml({ loai: "poster_len_lich", folder_id: 4, so_video_ngay: "77" }, { folders: [{ id: 4, ten: "A" }] }).match(/<input[^>]*data-vs-so[^>]*>/)[0], /value="77"/);
  for (const sai of [undefined, 0, 101, "abc", "2.5"]) {
    assert.match(F.formViecSpHtml({ loai: "poster_len_lich", folder_id: 4, so_video_ngay: sai }, { folders: [{ id: 4, ten: "A" }] }).match(/<input[^>]*data-vs-so[^>]*>/)[0], /value="1"/, String(sai));
  }
  assert.ok(!h.includes("<img"));
  assert.ok(h.includes("&lt;img"));
  // đang tải / lỗi / không có folder
  assert.match(F.formViecSpHtml({ loai: "poster_len_lich" }, { folders: null }), /Đang/);
  assert.ok(F.formViecSpHtml({ loai: "poster_len_lich" }, { folders: null, loi: BAN }).includes("&lt;img"));
  assert.ok(!/data-vs-gui/.test(F.formViecSpHtml({ loai: "poster_len_lich" }, { folders: [] })));
  // khoá khi đang gửi
  h = F.formViecSpHtml({ loai: "muse_clip", nhan: "x", mau: [], thoi_luong: 10 }, { khoa: true });
  assert.match(h.match(/<button[^>]*data-vs-gui[^>]*>/)[0], /disabled/);
  for (const x of [F.formViecSpHtml({ loai: "muse_clip", nhan: BAN }, {}), F.formViecSpHtml({ loai: "poster_len_lich" }, { folders: [{ id: 1, ten: BAN }] })]) {
    assert.ok(!/<[^>]*\son[a-z]+=/i.test(x), "có on…=");
  }
  assert.equal(F.formViecSpHtml(null, {}), "");
});

test("trang chi tiết: khung duyệt — khoá trước await, xoá mật khẩu trước khi gửi, kiểm phienViec, không lưu mật khẩu", () => {
  const r = VIEC.slice(VIEC.indexOf("async function renderViecChiTiet("), VIEC.indexOf("// ---------- khối việc trong trang chi tiết SP"));
  const i0 = r.indexOf("const guiDuyet");
  assert.ok(i0 > 0, "thiếu guiDuyet");
  const g = r.slice(i0, i0 + 1500);
  const iXoa = g.search(/\.value = ""/);
  const iGui = g.indexOf('hanhDong("duyet"');
  assert.ok(iXoa > 0 && iGui > iXoa, "phải xoá ô mật khẩu trước khi gửi");
  const iKhoa = g.indexOf("khoaKhungDuyet(true)");
  assert.ok(iKhoa > 0 && iKhoa < iGui, "khoá nút trước khi gửi");
  assert.ok(!/await/.test(g.slice(0, iGui)), "không có await trước khi khoá + gửi");
  assert.match(r, /const khoaKhungDuyet[\s\S]{0,120}tk !== phienViec/);
  assert.ok(!/(localStorage|sessionStorage)/.test(VIEC), "viec.js không dùng storage");
  assert.ok(!/(window|globalThis)\.[a-zA-Z_]*[mM]at_?[kK]hau/.test(VIEC));
  // hanhDong: khoá trước await (giữ hành vi cũ)
  const h = r.slice(r.indexOf("const hanhDong"), r.indexOf("const hanhDong") + 400);
  assert.ok(h.indexOf("dangGuiViec.add(id)") < h.indexOf("await"));
});

test("khối việc SP: form tạo đợt 4 dùng taoViec + kiểm phienCT trước khi vẽ", () => {
  const r = VIEC.slice(VIEC.indexOf("// ---------- khối việc trong trang chi tiết SP"));
  assert.match(r, /api\("viec\/poster\/folders"\)/);
  assert.match(r, /thamSoMuse\(/);
  assert.match(r, /thamSoPoster\(/);
  const i0 = r.indexOf("async function taiFolderPoster(");
  assert.ok(i0 > 0, "thiếu taiFolderPoster");
  const f = r.slice(i0, i0 + 700);
  assert.match(f, /phien !== phienCT/);
  assert.ok(f.indexOf("dangTaiFolder = true") < f.indexOf("await"), "khoá tải folder trước await");
});

// ---------- FX-12 (D9): duyệt gắn sha tham số + xin duyệt lại việc tốn tiền ----------
test("nutChoViecTonTien: loại tốn tiền ở loi/can_tra_loi → xin duyệt lại, ẩn chạy tiếp", () => {
  for (const loai of ["muse_clip", "voice_genmax", "poster_len_lich", "taovideo"]) {
    assert.deepEqual(F.nutChoViecTonTien({ loai, trang_thai: "loi" }), { xinDuyetLai: true, anChayTiep: true, anTraLoi: false }, `${loai}/loi`);
    assert.deepEqual(F.nutChoViecTonTien({ loai, trang_thai: "can_tra_loi" }), { xinDuyetLai: true, anChayTiep: true, anTraLoi: true }, `${loai}/can_tra_loi`);
    for (const tt of ["cho", "dang_chay", "cho_duyet", "xong", "huy", undefined]) assert.deepEqual(F.nutChoViecTonTien({ loai, trang_thai: tt }), { xinDuyetLai: false, anChayTiep: false, anTraLoi: false }, `${loai}/${tt}`);
  }
  for (const loai of ["voice_pv", "phan_tich_uid", "constructor", "__proto__", undefined]) {
    for (const tt of ["loi", "can_tra_loi"]) assert.deepEqual(F.nutChoViecTonTien({ loai, trang_thai: tt }), { xinDuyetLai: false, anChayTiep: false, anTraLoi: false }, `${String(loai)}/${tt}`);
  }
  assert.deepEqual(F.nutChoViecTonTien(null), { xinDuyetLai: false, anChayTiep: false, anTraLoi: false });
  assert.deepEqual(F.nutChoViecTonTien("muse_clip"), { xinDuyetLai: false, anChayTiep: false, anTraLoi: false });
});

// ---------- FX-13 (D9): việc tốn tiền hỏi giữa chừng → không trả lời trên web, chỉ xin duyệt lại ----------
test("chiTietViecHtml: việc tốn tiền can_tra_loi → ẩn MỌI nút trả lời, giữ câu hỏi (esc) + Xin duyệt lại + giải thích", () => {
  const BAN = `<img src=x onerror=alert(1)>"'&`;
  const ca = [
    { loai: "chon", lua_chon: ["A", "B"], noi_dung: BAN },
    { loai: "viec_tay", noi_dung: BAN },
    { loai: "khong_ro", noi_dung: BAN },
    { loai: "cau_hoi", noi_dung: BAN },
  ];
  for (const loai of ["muse_clip", "voice_genmax", "poster_len_lich", "taovideo"]) {
    for (const ch of ca) {
      const h = F.chiTietViecHtml({ viec: VD({ loai, trang_thai: "can_tra_loi", cau_hoi: ch }) }, { dotBat: 4 });
      const nhan = `${loai}/${ch.loai}`;
      assert.ok(!h.includes("data-vj-tl"), `còn nút trả lời ${nhan}`);
      assert.ok(!h.includes("Tiếp tục"), `còn Tiếp tục ${nhan}`);
      assert.ok(!h.includes("Tôi đã làm xong"), `còn nút việc tay ${nhan}`);
      assert.ok(h.includes(esc(BAN)) && !h.includes("<img"), `câu hỏi phải hiện và đã esc ${nhan}`);
      assert.match(h, /data-vj-act="xin-duyet-lai"[^>]*>[^<]*Xin duyệt lại/, nhan);
      assert.match(h, /Việc tốn tiền: trả lời xong phải duyệt lại bằng mật khẩu/, nhan);
      assert.ok(!h.includes("đợt 3 chỉ trả lời bằng nút"), `hướng dẫn sai ${nhan}`);
    }
  }
  // việc thường can_tra_loi: giữ nguyên nút trả lời
  const hThuong = F.chiTietViecHtml({ viec: { id: ID, loai: "voice_pv", trang_thai: "can_tra_loi", cau_hoi: { loai: "chon", lua_chon: ["A", "B"] } } }, { dotBat: 4 });
  assert.match(hThuong, /data-vj-tl="1"[^>]*>B</);
  assert.ok(!hThuong.includes("Việc tốn tiền: trả lời xong"));
});

test("handler trả lời: việc tốn tiền đang hỏi → không gửi tra-loi (chặn cả khi DOM cũ còn nút)", () => {
  const r = VIEC.slice(VIEC.indexOf("async function renderViecChiTiet("), VIEC.indexOf("// ---------- khối việc trong trang chi tiết SP"));
  const i0 = r.indexOf("b.dataset.vjTl !== undefined");
  assert.ok(i0 > 0);
  const k = r.slice(i0, i0 + 400);
  assert.match(k.slice(0, k.indexOf('hanhDong("tra-loi"')), /anTraLoi/);
});

test("hanMucHtml: poster_video_ngay_toi_da hiển thị video/tài khoản/ngày", () => {
  const h = F.hanMucHtml("poster_len_lich", { han_muc: { poster_len_lich_ngay: 2, poster_video_ngay_toi_da: 100 } });
  assert.match(h, /100 video\/tài khoản\/ngày/);
  assert.match(h, /2 việc\/ngày/);
  assert.ok(!h.includes("video/ngày tối đa"));
});

test("chiTietViecHtml: việc tốn tiền lỗi/hỏi → không Chạy tiếp/Tiếp tục, có Xin duyệt lại; việc thường giữ nguyên", () => {
  const h1 = F.chiTietViecHtml({ viec: VD({ trang_thai: "loi", co_the_chay_tiep: true, loi: "x" }) }, { dotBat: 4 });
  assert.ok(!h1.includes('data-vj-act="chay-tiep"'));
  assert.match(h1, /data-vj-act="xin-duyet-lai"[^>]*>[^<]*Xin duyệt lại/);
  assert.match(h1, /data-vj-act="chay-lai"/);
  const h2 = F.chiTietViecHtml({ viec: VD({ trang_thai: "can_tra_loi", cau_hoi: { loai: "khong_ro" } }) }, { dotBat: 4 });
  assert.ok(!h2.includes("Tiếp tục"), "còn nút Tiếp tục");
  assert.match(h2, /data-vj-act="xin-duyet-lai"/);
  assert.match(h2, /data-vj-act="huy"/);
  // câu hỏi chon của việc tốn tiền (FX-13): không còn nút trả lời, chỉ xin duyệt lại
  const h3 = F.chiTietViecHtml({ viec: VD({ loai: "taovideo", trang_thai: "can_tra_loi", cau_hoi: { loai: "chon", lua_chon: ["A", "B"] } }) }, { dotBat: 4 });
  assert.ok(!h3.includes("data-vj-tl"));
  assert.match(h3, /data-vj-act="xin-duyet-lai"/);
  // khoá: nút xin duyệt lại cũng disabled
  const h4 = F.chiTietViecHtml({ viec: VD({ trang_thai: "loi" }) }, { dotBat: 4, khoa: true });
  assert.match(h4.match(/<button[^>]*data-vj-act="xin-duyet-lai"[^>]*>/)[0], /disabled/);
  // việc không tốn tiền: hành vi cũ
  const h5 = F.chiTietViecHtml({ viec: { id: ID, loai: "voice_pv", trang_thai: "loi", co_the_chay_tiep: true } }, { dotBat: 4 });
  assert.match(h5, /data-vj-act="chay-tiep"/);
  assert.ok(!h5.includes("xin-duyet-lai"));
  assert.match(F.chiTietViecHtml({ viec: { id: ID, loai: "voice_pv", trang_thai: "can_tra_loi", cau_hoi: { loai: "khong_ro" } } }, { dotBat: 4 }), /Tiếp tục/);
  // xong/cho_duyet: không có xin duyệt lại
  assert.ok(!F.chiTietViecHtml({ viec: VD({ trang_thai: "xong" }) }, {}).includes("xin-duyet-lai"));
  assert.ok(!F.chiTietViecHtml({ viec: VD() }, { khungDuyet: true }).includes("xin-duyet-lai"));
});

test("ketQuaHanhDong: xin duyệt lại → toast hướng dẫn duyệt", () => {
  const k = F.ketQuaHanhDong("xin-duyet-lai", { status: 200, viec: { id: ID, trang_thai: "cho_duyet" } }, ID);
  assert.match(k.toast, /duyệt lại/i);
  assert.equal(k.chuyen, "");
});

test("thamSoChuanDuyet: chỉ nhận chuỗi JSON object, giữ NGUYÊN chuỗi", () => {
  const s = '{"a":"Bình", "b":1}';
  assert.equal(F.thamSoChuanDuyet({ tham_so_chuan: s }), s);
  for (const x of [undefined, null, "", "[]", "1", "null", "{x", { a: 1 }, 5]) assert.equal(F.thamSoChuanDuyet({ tham_so_chuan: x }), "", String(x));
  assert.equal(F.thamSoChuanDuyet(null), "");
});

test("sha256HexWeb: SHA-256 UTF-8 hex khớp vector ký của runner", async () => {
  const vec = JSON.parse(readFileSync(new URL("../../tools/runner/vector_ky.json", import.meta.url), "utf8"));
  const tim = (o) => (o && typeof o === "object" ? (typeof o.tham_so_chuan_sha256_hex === "string" ? [o] : Object.values(o).flatMap(tim)) : []);
  const ds = tim(vec);
  assert.ok(ds.length > 0, "không thấy vector");
  for (const v of ds) assert.equal(await F.sha256HexWeb(v.tham_so_chuan), v.tham_so_chuan_sha256_hex);
  assert.equal(await F.sha256HexWeb(""), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
});

test("duLieuViecDoi: 409 'Dữ liệu việc đã đổi' → true; 409 khác/200 → false", () => {
  assert.equal(F.duLieuViecDoi({ status: 409, loi: "Dữ liệu việc đã đổi — tải lại" }), true);
  assert.equal(F.duLieuViecDoi({ status: 409, loi: "Việc không còn chờ duyệt" }), false);
  assert.equal(F.duLieuViecDoi({ status: 200, loi: "Dữ liệu việc đã đổi" }), false);
  assert.equal(F.duLieuViecDoi(null), false);
});

test("khungDuyetHtml: hiện tham số từ tham_so_chuan; thiếu → khoá nút Duyệt + báo tải lại", () => {
  const tsc = JSON.stringify({ uid: UID, du_an: "abcdef012345", mau: ["can_canh"], thoi_luong: 10, ti_le: "9:16" });
  let h = F.khungDuyetHtml({ viec: VD(), tham_so_chuan: tsc }, {});
  assert.match(h, /Cận cảnh chất liệu/);          // lấy từ chuỗi chuẩn, không từ viec.tham_so
  assert.ok(!h.includes("Mở hộp"));
  assert.ok(!/data-vd-act="duyet"[^>]*disabled/.test(h));
  h = F.khungDuyetHtml({ viec: VD() }, {});
  assert.match(h, /<button[^>]*data-vd-act="duyet"[^>]*disabled/);
  assert.match(h, /tải lại/i);
  assert.match(h, /data-vd-act="tai-lai"/);
  assert.ok(!/data-vd-act="tu-choi"[^>]*disabled/.test(h), "vẫn từ chối được");
});

test("trang chi tiết: gửi duyệt kèm sha_tham_so của chuỗi đã hiển thị, khoá trước await, 409 dữ liệu đổi → tải lại", () => {
  const r = VIEC.slice(VIEC.indexOf("async function renderViecChiTiet("), VIEC.indexOf("// ---------- khối việc trong trang chi tiết SP"));
  const i0 = r.indexOf("const guiDuyet");
  const g = r.slice(i0, r.indexOf("$(\"#vj-duyet\").addEventListener", i0));
  assert.match(g, /sha_tham_so/);
  assert.match(g, /sha256HexWeb\(/);
  assert.match(g, /khungTsc/);                      // chuỗi chụp lúc vẽ khung, không lấy d mới
  assert.ok(!/await/.test(g.slice(0, g.indexOf('hanhDong("duyet"'))), "await trước khi khoá + gửi");
  const h = r.slice(r.indexOf("const hanhDong"), r.indexOf("const guiDuyet"));
  assert.ok(h.indexOf("dangGuiViec.add(id)") < h.indexOf("await"), "khoá trước await");
  const iBody = h.indexOf("await body()");
  assert.ok(iBody > 0, "body tạo sau khi khoá");
  assert.match(h.slice(iBody, iBody + 120), /tk !== phienViec/);
  assert.match(h, /duLieuViecDoi\(/);
  assert.match(r, /data-vd-act|vdAct === "tai-lai"/);
  assert.match(VIEC, /crypto\.subtle\.digest\("SHA-256"/);
});

test("index.html: viec.js?v= đã tăng (FX-13)", () => {
  const v = Number(doc("index.html").match(/viec\.js\?v=(\d+)/)[1]);
  assert.ok(v >= 6, `viec.js?v=${v}`);
});
