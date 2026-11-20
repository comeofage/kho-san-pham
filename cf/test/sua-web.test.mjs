// Test màn sửa video (W-9, docs/sua-video.md §9): hàm thuần trong web/sua.js (khối // --- sua-thuan start/end ---)
// + kiểm tĩnh app.js/index.html. Chạy: node --test cf/test/sua-web.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { kiemBanSua } from "../src/worker.js";

const doc = (p) => readFileSync(new URL(`../../web/${p}`, import.meta.url), "utf8");
const SUA = doc("sua.js");
const APP = doc("app.js");
const VIEC = doc("viec.js");
const HTML = doc("index.html");

const dongEsc = APP.split("\n").find((l) => l.startsWith("const esc = "));
assert.ok(dongEsc, "không thấy const esc trong app.js");
const esc = new Function(`${dongEsc}\nreturn esc;`)();
const m = SUA.match(/\/\/ --- sua-thuan start ---\n([\s\S]*?)\/\/ --- sua-thuan end ---/);
assert.ok(m, "thiếu marker sua-thuan trong sua.js");
const F = new Function("esc", `"use strict";\n${m[1]}\nreturn { gopDau, gioCau, gioCanh, kiemCauPhuDe, ghepVideoSua, nhomCanh, nhapRong, dongThayDoi, thanLuu,
  nhapLuu, nhapDoc, luuNhapSua, docNhapSua, khoaNhapSua, ketQuaLuu, cauHtml, canhDongHtml, ungVienHtml, lichSuHtml, nutSuaHtml, tienHtml, chuanSua, kiemDoiCho };`)(esc);

const UID = "1736818222555104357";
const MA = "0123456789abcdef";
const SHA = "a".repeat(64);
const BAN = `<script>alert(1)</script><img src=x onerror=alert(1)>"'`;
const VIEC_ID = "j20261117100000abcd";

const chiTiet = (x = {}) => F.chuanSua({
  video: { ma_video: MA, du_an: "abcdef012345", goc: "GOC", thu_muc: "output_poster", ten: "50oto2809_061.mp4", sua_luc: 1790585841123, luong: "C", sua_duoc: true, ly_do: "" },
  luong: "C", me: null,
  phu_de: { sha: SHA, co_words: true, bien_the: false, so_video_cung_take: 6, take_idx: 2,
    cau: [{ i: 0, start: 0, end: 4.24, text: "Cho nha , cái này hay lắm !" }, { i: 1, start: 4.24, end: 7.5, text: "Mua đi" }, { i: 2, start: 7.5, end: 9, text: "Chốt" }] },
  canh: [
    { i: 0, kind: "BASE", out_start: 0, out_end: 20, role: "", clip: "", doi_duoc: false, ly_do: "" },
    { i: 2, kind: "OVL", out_start: 7.2, out_end: 9.9, role: "proof", clip: "raw-1_002_proof_b.mp4", doi_duoc: true, ly_do: "" },
    { i: 1, kind: "OVL", out_start: 4.0, out_end: 6.5, role: "benefit", clip: "raw-1_001_benefit_a.mp4", doi_duoc: true, ly_do: "" },
    { i: 3, kind: "OVL", out_start: 11, out_end: 13, role: "cta", clip: "raw-1_003_cta_c.mp4", doi_duoc: false, ly_do: "đoạn chốt" },
  ],
  ghi_chu_luong_a: false, viec_mo: null, lich_su: [],
  ...x,
});

test("gopDau / gioCau / gioCanh", () => {
  assert.equal(F.gopDau("Cho nha , cái này hay lắm !"), "Cho nha, cái này hay lắm!");
  assert.equal(F.gopDau("  a   b . "), "a b.");
  assert.equal(F.gopDau(null), "");
  assert.equal(F.gioCau(3.24), "00:03.2");
  assert.equal(F.gioCau(65.06), "01:05.1");
  assert.equal(F.gioCau("x"), "00:00.0");
  assert.equal(F.gioCanh(7.9), "00:07");
  assert.equal(F.gioCanh(125), "02:05");
});

test("kiemCauPhuDe: khớp luật Worker (1–200 code point, cấm điều khiển/xuống dòng/{ } \\ < > -->)", () => {
  assert.equal(F.kiemCauPhuDe("Trời ơi, chạy trớn nha!"), "");
  assert.equal(F.kiemCauPhuDe("😀".repeat(200)), "");
  for (const sai of ["", "   ", "a".repeat(201), "a\nb", "a\tb", "a{b", "a}b", "a\\b", "a<b", "a>b", "a --> b", "a b", "\ud800", 5, null]) {
    assert.notEqual(F.kiemCauPhuDe(sai), "", JSON.stringify(sai));
  }
});

test("ghepVideoSua(nguon, ds): ghép theo (goc, ten), bỏ mục sai mẫu, không theo sua_luc", () => {
  const nguon = [{ goc: "GOC", chi_tiet: [{ ten: "a.mp4", sua_luc: 1790585841 }, { ten: "b.mp4" }] }, { goc: "GOC#x/output", chi_tiet: [{ ten: "a.mp4" }] }, null, { goc: "Z" }];
  const ds = [
    { ma_video: MA, goc: "GOC", ten: "a.mp4", sua_luc: 1790585841123, sua_duoc: true, ly_do: "" },
    { ma_video: "fedcba9876543210", goc: "GOC#x/output", ten: "a.mp4", sua_duoc: false, ly_do: "Không chứng minh được" },
    { ma_video: "../../x", goc: "GOC", ten: "b.mp4", sua_duoc: true },
    { ma_video: "1111111111111111", goc: "KHAC", ten: "c.mp4", sua_duoc: true },
    null, 5,
  ];
  const g = F.ghepVideoSua(nguon, ds);
  assert.equal(g.size, 2);
  assert.equal(g.get(JSON.stringify(["GOC", "a.mp4"])).ma_video, MA);
  assert.equal(g.get(JSON.stringify(["GOC#x/output", "a.mp4"])).sua_duoc, false);
  assert.equal(g.get(JSON.stringify(["GOC", "b.mp4"])), undefined);
  assert.equal(F.ghepVideoSua(null, ds).size, 0);
  assert.equal(F.ghepVideoSua(nguon, { videos: ds }).size, 0);
});

test("nhomCanh: sắp theo giờ, BASE là nền, chỉ OVL doi_duoc vào danh sách đổi", () => {
  const n = F.nhomCanh(chiTiet().canh);
  assert.deepEqual(n.ds.map((x) => x.i), [0, 1, 2, 3]);
  assert.equal(n.ds[0].laNen, true);
  assert.deepEqual(n.phu.map((x) => x.i), [1, 2]);
  assert.equal(n.ds[1].vai, "Lợi ích");
  assert.equal(F.nhomCanh([{ i: 9, kind: "OVL", out_start: 0, out_end: 1, role: BAN, clip: "x.mp4", doi_duoc: true }]).ds[0].vai, BAN);
  assert.deepEqual(F.nhomCanh(null).ds, []);
  assert.deepEqual(F.nhomCanh([null, { i: "x" }, { i: 1, kind: "OVL" }]).ds.length, 1);
});

test("dongThayDoi: bỏ câu giống bản cũ (đã gộp dấu), đếm thay đổi, body qua được kiemBanSua của Worker", () => {
  const d = chiTiet();
  const nh = F.nhapRong();
  nh.phu_de.set(0, "Cho nha, cái này hay lắm!");      // y như cũ sau gộp dấu → bỏ
  nh.phu_de.set(1, "Mua liền đi");
  nh.phu_de.set(99, "câu không có thật");
  nh.doi_clip.set(1, "raw-2_010_benefit_z.mp4");
  nh.doi_clip.set(2, "raw-1_002_proof_b.mp4");        // trùng clip cũ → bỏ
  nh.doi_clip.set(3, "raw-2_011_cta_y.mp4");           // không đổi được → bỏ
  nh.doi_clip.set(0, "raw-2_012_hook_y.mp4");          // BASE → bỏ
  const t = F.dongThayDoi(d, nh);
  assert.equal(t.loi, "");
  assert.equal(t.so, 2);
  assert.equal(t.coChu, true);
  assert.deepEqual(t.body, { sua_luc: 1790585841123, phu_de_sha: SHA, phu_de: [{ i: 1, text: "Mua liền đi" }], doi_clip: [{ seg: 1, clip: "raw-2_010_benefit_z.mp4" }], doi_cho: [] });
  const w = kiemBanSua(F.thanLuu(t.body, "mk"));
  assert.notEqual(typeof w, "string", w);
  // chỉ đổi clip: không gửi phu_de_sha, không chữ
  const nh2 = F.nhapRong(); nh2.doi_cho.push([1, 2]);
  const t2 = F.dongThayDoi(d, nh2);
  assert.equal(t2.coChu, false); assert.equal(t2.so, 1);
  assert.ok(!("phu_de_sha" in t2.body));
  assert.notEqual(typeof kiemBanSua(F.thanLuu(t2.body, "")), "string");
  // không có gì
  assert.equal(F.dongThayDoi(d, F.nhapRong()).so, 0);
});

test("dongThayDoi: lỗi giới hạn, biến thể, thiếu Whisper, chữ cấm, body > 16 KB", () => {
  const nh = F.nhapRong(); nh.phu_de.set(1, "a<b");
  assert.match(F.dongThayDoi(chiTiet(), nh).loi, /Câu 2/);
  const nhOk = F.nhapRong(); nhOk.phu_de.set(1, "khác");
  assert.match(F.dongThayDoi(chiTiet({ phu_de: { ...chiTiet().phu_de, bien_the: true } }), nhOk).loi, /biến thể/);
  assert.match(F.dongThayDoi(chiTiet({ phu_de: { ...chiTiet().phu_de, co_words: false } }), nhOk).loi, /Whisper/);
  assert.match(F.dongThayDoi(chiTiet({ phu_de: { ...chiTiet().phu_de, sha: "" } }), nhOk).loi, /tải lại/);
  // biến thể chỉ chặn chữ, không chặn đổi clip
  const nhClip = F.nhapRong(); nhClip.doi_clip.set(1, "raw-2_010_benefit_z.mp4");
  assert.equal(F.dongThayDoi(chiTiet({ phu_de: { ...chiTiet().phu_de, bien_the: true } }), nhClip).loi, "");
  // 31 câu
  const nhieu = Array.from({ length: 40 }, (_, i) => ({ i, start: i, end: i + 1, text: `câu ${i}` }));
  const d = chiTiet({ phu_de: { ...chiTiet().phu_de, cau: nhieu } });
  const nh31 = F.nhapRong(); for (let i = 0; i < 31; i++) nh31.phu_de.set(i, `mới ${i}`);
  assert.match(F.dongThayDoi(d, nh31).loi, /30 câu/);
  // 30 câu × 200 ký tự 3 byte ≈ 18 KB > 16 KB
  const nh30 = F.nhapRong(); for (let i = 0; i < 30; i++) nh30.phu_de.set(i, "ở".repeat(200));
  assert.match(F.dongThayDoi(d, nh30).loi, /ít câu hơn/);
  // sua_luc hỏng
  assert.match(F.dongThayDoi(chiTiet({ video: { ...chiTiet().video, sua_luc: "x" } }), nhOk).loi, /tải lại/);
});

test("kiemDoiCho: đoạn phủ đổi được, khác nhau, không trùng đổi clip/cặp khác, ≤ 3 cặp", () => {
  const d = chiTiet();
  const nh = F.nhapRong();
  assert.equal(F.kiemDoiCho(d, nh, 1, 2), "");
  assert.notEqual(F.kiemDoiCho(d, nh, 1, 1), "");
  assert.notEqual(F.kiemDoiCho(d, nh, 1, 3), "");   // 3 không đổi được
  assert.notEqual(F.kiemDoiCho(d, nh, 0, 1), "");   // BASE
  nh.doi_clip.set(1, "raw-2_010_benefit_z.mp4");
  assert.notEqual(F.kiemDoiCho(d, nh, 1, 2), "");
  const nh2 = F.nhapRong(); nh2.doi_cho.push([1, 2]);
  assert.notEqual(F.kiemDoiCho(d, nh2, 2, 1), "");
});

test("thanLuu: chỉ đổi clip → KHÔNG có mat_khau; có sửa chữ → có mat_khau", () => {
  const b = { sua_luc: 1, phu_de: [], doi_clip: [{ seg: 1, clip: "a.mp4" }], doi_cho: [] };
  const r = F.thanLuu(b, "bimat");
  assert.ok(!("mat_khau" in r));
  assert.ok(!JSON.stringify(r).includes("bimat"));
  const r2 = F.thanLuu({ ...b, phu_de_sha: SHA, phu_de: [{ i: 0, text: "x" }] }, "bimat");
  assert.equal(r2.mat_khau, "bimat");
  assert.ok(!("mat_khau" in b), "không sửa body gốc");
});

test("bản nháp sessionStorage: lưu → khôi phục; lệch sua_luc/sha → bỏ; không bao giờ có mật khẩu", () => {
  const kho = new Map();
  const store = { getItem: (k) => (kho.has(k) ? kho.get(k) : null), setItem: (k, v) => kho.set(k, String(v)), removeItem: (k) => kho.delete(k) };
  const d = chiTiet();
  const nh = F.nhapRong();
  nh.phu_de.set(1, "Mua liền <script>x</script>");
  nh.doi_clip.set(1, "raw-2_010_benefit_z.mp4");
  F.luuNhapSua(store, MA, nh, d);
  assert.equal(kho.size, 1);
  assert.ok([...kho.keys()][0].includes(MA));
  assert.ok(!/mat_khau|mk/.test([...kho.values()][0]));
  const lai = F.docNhapSua(store, MA, d);
  assert.equal(lai.trang_thai, "ok");
  assert.equal(lai.nhap.phu_de.get(1), "Mua liền <script>x</script>");
  assert.equal(lai.nhap.doi_clip.get(1), "raw-2_010_benefit_z.mp4");
  // đổi chỗ khôi phục được; cặp vi phạm luật (trùng đoạn đã đổi clip) bị bỏ
  const nhCho = F.nhapRong(); nhCho.doi_cho.push([1, 2]);
  F.luuNhapSua(store, MA, nhCho, d);
  assert.deepEqual(F.docNhapSua(store, MA, d).nhap.doi_cho, [[1, 2]]);
  kho.set(F.khoaNhapSua(MA), JSON.stringify({ v: 1, sua_luc: d.video.sua_luc, sha: SHA, phu_de: [], doi_clip: [{ seg: 1, clip: "raw-2_010_benefit_z.mp4" }], doi_cho: [[1, 2], [1, 3]] }));
  const tron = F.docNhapSua(store, MA, d);
  assert.equal(tron.trang_thai, "ok");
  assert.deepEqual(tron.nhap.doi_cho, []);
  kho.clear();
  F.luuNhapSua(store, MA, nh, d);
  // video đã dựng lại (sua_luc khác) → bỏ nháp
  const lech = F.docNhapSua(store, MA, chiTiet({ video: { ...d.video, sua_luc: 1790585849999 } }));
  assert.equal(lech.trang_thai, "bo");
  assert.equal(kho.size, 0, "nháp lệch phải bị xoá");
  // không có nháp
  assert.equal(F.docNhapSua(store, MA, d).trang_thai, "khong");
  // phụ đề đổi sha → bỏ
  F.luuNhapSua(store, MA, nh, d);
  assert.equal(F.docNhapSua(store, MA, chiTiet({ phu_de: { ...d.phu_de, sha: "b".repeat(64) } })).trang_thai, "bo");
  // rác / storage ném lỗi
  kho.set(F.khoaNhapSua(MA), "{rác");
  assert.equal(F.docNhapSua(store, MA, d).trang_thai, "bo");
  const hong = { getItem: () => { throw new Error("x"); }, setItem: () => { throw new Error("x"); }, removeItem: () => { throw new Error("x"); } };
  assert.equal(F.docNhapSua(hong, MA, d).trang_thai, "khong");
  F.luuNhapSua(hong, MA, nh, d); // không ném
  // nháp rỗng → xoá khoá
  F.luuNhapSua(store, MA, nh, d); F.luuNhapSua(store, MA, F.nhapRong(), d);
  assert.equal(kho.size, 0);
});

test("ketQuaLuu: 201 → viec; 409 trùng → id việc đang dựng; 409 khác → lỗi", () => {
  assert.deepEqual(F.ketQuaLuu({ status: 201, viec: { id: VIEC_ID }, ban_sua: "b0123456789abcdef" }), { viec: VIEC_ID, trung: "", loi: "" });
  assert.deepEqual(F.ketQuaLuu({ status: 409, loi: "Video này đang được dựng lại", trung: VIEC_ID }), { viec: "", trung: VIEC_ID, loi: "Video này đang được dựng lại" });
  assert.deepEqual(F.ketQuaLuu({ status: 409, loi: "Phụ đề đã đổi từ lúc bạn mở — tải lại" }), { viec: "", trung: "", loi: "Phụ đề đã đổi từ lúc bạn mở — tải lại" });
  assert.equal(F.ketQuaLuu({ status: 409, trung: "../x" }).trung, "");
  assert.notEqual(F.ketQuaLuu({ status: 201, viec: { id: "x" } }).loi, "");
  assert.notEqual(F.ketQuaLuu(null).loi, "");
});

test("HTML: chữ có <script> hiện như chữ thường, mọi chuỗi runner qua esc, không on…=", () => {
  const cau = { i: 0, start: 1, end: 2, text: BAN };
  const html = [
    F.cauHtml(cau, { daSua: true, khoa: false }),
    F.cauHtml(cau, { daSua: false, khoa: true }),
    F.canhDongHtml({ i: 1, kind: "OVL", tu: 1, den: 2, vai: BAN, clip: BAN, doi_duoc: false, ly_do: BAN, laNen: false }, { uid: UID, duAn: BAN, luong: "C" }),
    F.canhDongHtml({ i: 1, kind: "OVL", tu: 1, den: 2, vai: "x", clip: "a.mp4", doi_duoc: true, ly_do: "", laNen: false }, { uid: UID, duAn: "abcdef012345", luong: "C", clipMoi: BAN, choVoi: 2 }),
    F.ungVienHtml({ clip: "a.mp4", role: BAN, dur: BAN, desc: BAN, tags: [BAN], co_anh: true, dung_duoc: false, ly_do: BAN }, 0, { uid: UID, duAn: "abcdef012345" }),
    F.lichSuHtml([{ viec: VIEC_ID, loai: "sua_video", trang_thai: BAN, luc: BAN, boi: BAN, hoan_tac_duoc: true }, { viec: BAN, loai: BAN, trang_thai: "xong", luc: "", boi: "", hoan_tac_duoc: true }], {}),
    F.nutSuaHtml({ ma_video: MA, sua_duoc: false, ly_do: BAN }, UID),
    F.tienHtml({ id: VIEC_ID, loai: "sua_video", tt: BAN, log: BAN, loi: BAN }),
  ].join("\n");
  assert.ok(!/<script/i.test(html), "lọt <script");
  assert.ok(!html.includes("<img src=x"), "lọt <img src=x");
  assert.ok(html.includes("&lt;script&gt;alert(1)&lt;/script&gt;"));
  // bỏ giá trị thuộc tính trong ngoặc kép (chữ đã esc nằm trong đó là vô hại) rồi tìm thuộc tính on…= thật
  assert.ok(!/<[^>]*\son[a-z]+=/i.test(html.replace(/"[^"]*"/g, '""')), "có thuộc tính on…=");
  assert.ok(!html.replace(/=\s*"[^"]*"/g, "").includes('"'), "ngoặc kép lọt khỏi giá trị thuộc tính");
  // textarea câu phụ đề rỗng trong HTML (chữ gán bằng .value)
  for (const ta of F.cauHtml(cau, { daSua: false }).match(/<textarea[^>]*>([\s\S]*?)<\/textarea>/g)) assert.match(ta, /><\/textarea>$/);
  assert.match(F.cauHtml(cau, {}), /maxlength="200"/);
  assert.match(F.cauHtml(cau, { khoa: true }), /readonly/);
});

test("nutSuaHtml: sửa được → link #/sua; không → nút mờ mang lý do; đang dựng → nhãn + link việc", () => {
  assert.match(F.nutSuaHtml({ ma_video: MA, sua_duoc: true }, UID), new RegExp(`href="#/sua/${UID}/${MA}"`));
  const mo = F.nutSuaHtml({ ma_video: MA, sua_duoc: false, ly_do: "Không chứng minh được" }, UID);
  assert.ok(!mo.includes("href"));
  assert.match(mo, /data-dv-sua-ly-do="Không chứng minh được"/);
  assert.match(mo, /mo/);
  const dang = F.nutSuaHtml({ ma_video: MA, sua_duoc: true, viec_mo: VIEC_ID }, UID);
  assert.match(dang, /đang dựng lại…/);
  assert.match(dang, new RegExp(`#/viec/${VIEC_ID}`));
  assert.equal(F.nutSuaHtml(null, UID), "");
  assert.equal(F.nutSuaHtml({ ma_video: "x", sua_duoc: true }, UID), "");
  assert.equal(F.nutSuaHtml({ ma_video: MA, sua_duoc: true }, "123"), "");
});

test("lichSuHtml: nút hoàn tác chỉ ở lần gần nhất có hoan_tac_duoc (sua_video, id hợp lệ)", () => {
  const ls = [
    { viec: "j20261117090000aaaa", loai: "sua_video", trang_thai: "xong", luc: "2026-11-17T09:00", boi: "nhan", hoan_tac_duoc: true },
    { viec: VIEC_ID, loai: "sua_video", trang_thai: "xong", luc: "2026-11-17T10:00", boi: "nhan", hoan_tac_duoc: true },
  ];
  const h = F.lichSuHtml(ls, {});
  assert.equal((h.match(/data-ls-hoan=/g) || []).length, 1);
  assert.match(h, new RegExp(`data-ls-hoan="${VIEC_ID}"`));
  assert.equal((F.lichSuHtml(ls, { khoa: true }).match(/<button[^>]*disabled/g) || []).length, 1);
  assert.equal((F.lichSuHtml([{ ...ls[0], hoan_tac_duoc: false }], {}).match(/data-ls-hoan=/g) || []).length, 0);
  assert.match(F.lichSuHtml([], {}), /Chưa sửa lần nào/);
});

test("tienHtml: xong → Xem bản mới + Dùng lại bản cũ; lỗi → link việc; đang chạy → không nút", () => {
  const xong = F.tienHtml({ id: VIEC_ID, loai: "sua_video", tt: "xong", log: "", loi: "" });
  assert.match(xong, /data-tien-xem/); assert.match(xong, /data-tien-hoan/);
  const ht = F.tienHtml({ id: VIEC_ID, loai: "hoan_tac_sua", tt: "xong", log: "", loi: "" });
  assert.match(ht, /data-tien-xem/); assert.ok(!ht.includes("data-tien-hoan"));
  const loi = F.tienHtml({ id: VIEC_ID, loai: "sua_video", tt: "loi", log: "", loi: "bận" });
  assert.match(loi, new RegExp(`href="#/viec/${VIEC_ID}"`)); assert.ok(!loi.includes("data-tien-hoan"));
  assert.ok(!F.tienHtml({ id: VIEC_ID, loai: "sua_video", tt: "dang_chay", log: "x", loi: "" }).includes("data-tien-"));
});

// ---------- kiểm tĩnh ----------
const khaiBao = (src) => [...src.matchAll(/^(?:const|let|var|function|async function|class)\s+([A-Za-z_$][\w$]*)/gm)].map((x) => x[1]);
test("không trùng tên khai báo cấp cao giữa app.js, viec.js, sua.js (trùng → script hỏng)", () => {
  const thay = new Map();
  for (const [ten, src] of [["app.js", APP], ["viec.js", VIEC], ["sua.js", SUA]]) {
    for (const k of khaiBao(src)) {
      assert.ok(!thay.has(k), `${k} khai báo ở cả ${thay.get(k)} và ${ten}`);
      thay.set(k, ten);
    }
  }
});

test("CSP: sua.js không inline handler, index.html nạp sua.js sau app.js (W-M3: sua.js?v ≥ 2), app.js?v tăng", () => {
  assert.equal((SUA.match(/\son[a-z]+="/g) || []).length, 0);
  assert.ok(!/innerHTML\s*=\s*[^;]*\.value/.test(SUA));
  assert.match(HTML, /<script src="app\.js\?v=(\d+)" defer><\/script>\s*<script src="sua\.js\?v=(\d+)" defer><\/script>/);
  assert.ok(Number(HTML.match(/sua\.js\?v=(\d+)/)[1]) >= 2, "sua.js đã đổi (W-M3) → nâng ?v");
  assert.ok(Number(HTML.match(/app\.js\?v=(\d+)/)[1]) >= 15);
  assert.ok(!/<script(?![^>]*\ssrc=)[^>]*>/i.test(HTML));
});

test("app.js: router #/sua/<uid>/<ma>, dừng màn sửa khi đổi trang; nút ✏ đã gỡ cùng trang Duyệt video (2026-11-19)", () => {
  assert.match(APP, /#\\\/sua\\\/\(\\d\{19\}\)\\\/\(\[0-9a-f\]\{16\}\)/);
  assert.match(APP, /renderSua\(/);
  const r = APP.slice(APP.indexOf("async function route()"), APP.indexOf("window.addEventListener(\"hashchange\""));
  assert.ok(r.indexOf("dungSua") >= 0 && r.indexOf("dungSua") < r.indexOf("auth.on"), "route phải dừng màn sửa trước tiên");
  assert.ok(!/viec\/sua-video\/\$\{|ghepVideoSua\(|nutSuaHtml\(|taiDsSua/.test(APP), "app.js không có nút ✏ của tab Duyệt cũ");
  assert.ok(!/duyet\.js/.test(doc("index.html")), "duyet.js đã gỡ khỏi index.html");
});
test("sua.js: mật khẩu xoá trước khi gửi, khoá trước await, không lưu storage, phản hồi muộn bị bỏ", () => {
  const i0 = SUA.indexOf("const luu = async");
  assert.ok(i0 > 0, "thiếu luu");
  const g = SUA.slice(i0, SUA.indexOf("// --- het luu ---", i0));
  const iGui = g.indexOf("/luu`");
  assert.ok(iGui > 0);
  const truoc = g.slice(0, iGui);
  const iAwait = truoc.lastIndexOf("await api(");
  assert.ok(iAwait > 0, "thiếu await api( của lượt gửi");
  assert.ok(!/await/.test(truoc.slice(0, iAwait)), "có await trước khi khoá + gửi");
  assert.ok(truoc.indexOf("s.dangLuu = true") < iAwait && truoc.indexOf('.value = ""') < iAwait);
  assert.match(truoc, /\.value = ""/);
  assert.match(truoc, /s\.dangLuu = true/);
  assert.match(g.slice(iGui), /tk !== phienSua/);
  assert.ok(!/localStorage/.test(SUA));
  for (const dong of SUA.split("\n").filter((l) => /sessionStorage/.test(l))) assert.ok(!/mk|mat_khau|matKhau/.test(dong), dong);
  assert.ok(!/(window|globalThis)\.[a-zA-Z_]*[mM]at_?[kK]hau/.test(SUA));
  // ô mật khẩu không value, có autocomplete
  const pw = SUA.match(/<input[^>]*type="password"[^>]*>/);
  assert.ok(pw); assert.ok(!/\svalue=/.test(pw[0])); assert.match(pw[0], /autocomplete="current-password"/);
  // thăm dò 3 s, ngăn kéo ứng viên bỏ phản hồi muộn
  assert.match(SUA, /setInterval\([\s\S]{0,80}3000\)/);
  const j0 = SUA.indexOf("const moNgan = async");
  assert.ok(j0 > 0);
  const n = SUA.slice(j0, SUA.indexOf("// ----- lưu -----", j0));
  assert.ok(n.indexOf("++s.ngan") < n.indexOf("await"), "đánh số lần mở trước await");
  assert.match(n.slice(n.indexOf("await")), /tk !== phienSua \|\| lan !== s\.ngan/);
  assert.match(SUA, /ung-vien\?seg=\$\{/);
});

test("W-M3 P2-3: màn sửa trỏ về trang SP (#/sp/<uid>, 2026-11-19 gỡ Duyệt video) — tab Duyệt trên trang SP đã bỏ", () => {
  const r = SUA.slice(SUA.indexOf("async function renderSua("));
  const link = [...r.matchAll(/<a href="([^"]*)" class="small">([^<]*)<\/a>/g)].map((m) => [m[1], m[2]]);
  assert.ok(link.length >= 2, "thiếu link quay về");
  for (const [href, chu] of link) {
    if (href === "#/kho") continue; // câu chặn người thường / mã sai giữ "← Về kho"
    assert.equal(href, "#/sp/${uid}"); // 2026-11-19: trang Duyệt video đã gỡ → về trang SP
    assert.equal(chu, "← Về sản phẩm");
  }
  assert.equal(link.filter(([h]) => h === "#/sp/${uid}").length, 2, "cả 2 chỗ (lỗi + màn sửa)");
  assert.ok(!/href="#\/duyet\//.test(SUA), "còn link #/duyet/<uid> (trang đã gỡ)");
});
