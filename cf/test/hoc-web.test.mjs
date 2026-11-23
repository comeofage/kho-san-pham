// Test HT-W2 (D15, docs/hoc-tu-dong.md §3.8, §3.9, §8.3): khối "📈 Học hôm nay" trong trang Hôm nay + trang #/hoc (web/hoc.js),
// nút Hoàn tác / Bật lại (chỉ chủ kho), cảnh báo nguồn view cũ, nhãn 2 loại việc mới. Không mạng: api/DOM giả. Chạy: node --test cf/test/
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const doc = (p) => readFileSync(new URL(`../../web/${p}`, import.meta.url), "utf8");
const APP = doc("app.js");
const LOI = doc("loi.js");
const VIEC = doc("viec.js");
const HN = doc("homnay.js");
const HOC = doc("hoc.js");
const HTML = doc("index.html");
// Nguồn sinh dữ liệu (CHỈ ĐỌC): bộ mã của runner + thân lỗi của Worker — để web lệch là test đỏ (HT-W2b).
const goc = (p) => readFileSync(new URL(`../../${p}`, import.meta.url), "utf8");
const PY_DM = goc("tools/runner/hoc_danh_muc.py");
const PY_KHO = goc("tools/runner/kho_hoc.py");
const WORKER = goc("cf/src/worker.js");
const CF_HOC = goc("cf/src/hoc.js");
const VSV = goc("tools/video_server.py");
const DOC = goc("docs/hoc-tu-dong.md");
// Khối `TEN: kiểu = {…}` / `(…)` của file .py → danh sách khoá/chuỗi.
const pyKhoi = (ten, mo, dong) => {
  const i = PY_DM.indexOf(`\n${ten}:`);
  assert.ok(i >= 0, `hoc_danh_muc.py thiếu ${ten}`);
  const a = PY_DM.indexOf(mo, i), b = PY_DM.indexOf(`\n${dong}`, a);
  return PY_DM.slice(a, b);
};
const pyKhoaDict = (ten) => [...pyKhoi(ten, "{", "}").matchAll(/^\s+"([a-z0-9_]+)":/gm)].map((m) => m[1]);
const pyTuple = (ten) => [...pyKhoi(ten, "(", ")").matchAll(/"([a-z0-9_]+)"/g)].map((m) => m[1]);
const pyTenLyDo = (ma) => {
  const m = pyKhoi("TEN_LY_DO", "{", "}").match(new RegExp(`^\\s+"${ma}": "([^"]*)"`, "m"));
  assert.ok(m, `TEN_LY_DO thiếu ${ma}`);
  return m[1];
};

const esc = new Function(`${APP.split("\n").find((l) => l.startsWith("const esc = "))}\nreturn esc;`)();
const khoi = (src, ten) => {
  const m = src.match(new RegExp(`// --- ${ten} start ---\\n([\\s\\S]*?)// --- ${ten} end ---`));
  assert.ok(m, `thiếu marker ${ten}`);
  return m[1];
};
// Khối thuần của loi/viec/homnay/hoc chung một phạm vi (như trình duyệt), esc thật của app.js.
const F = new Function("esc", `"use strict";\n${khoi(LOI, "loi-thuan")}\n${khoi(VIEC, "viec-thuan")}\n${khoi(HN, "homnay-thuan")}\n${khoi(HOC, "hoc-thuan")}
return { homNayHtml, hcKhoiHomNayHtml, hcTrangHtml, hcCanhBao, hcCauHomNay, hcNutHtml, hcCauXacNhan, hcDm, hcCauLoiTai,
  hcBaiHtml, hcLoaiLoi, HC_THIEU, HC_LY_DO_NGAN, HC_LOI_CHUA_CO_LAN, HC_LOI_KHONG_BAI, HC_LOI_CHUA_BAT,
  LOI_LOAI_VIEC, loiLoaiViec, TEN_LOAI_VIEC, LOAI_VIEC_SP };`)(esc);
// Chỉ khối thuần của homnay (không có hoc.js) — "bản cũ" để so.
const F_CU = new Function("esc", `"use strict";\n${khoi(LOI, "loi-thuan")}\n${khoi(VIEC, "viec-thuan")}\n${khoi(HN, "homnay-thuan")}
return { homNayHtml };`)(esc);

const BAN = `<img src=x onerror=alert(1)>`;
const KHONG_LOT = (h, ten) => {
  assert.ok(!h.includes("<img"), `${ten}: lọt thẻ <img`);
  assert.ok(!/\son[a-z]+=/i.test(h.replace(/&lt;img src=x onerror=alert\(1\)&gt;/g, "")), `${ten}: lọt thuộc tính on…=`);
};
const CHIEU = Date.parse("2026-11-23T13:00:00+07:00"); // sau 12:00 giờ VN
const SANG = Date.parse("2026-11-23T10:00:00+07:00");
const MA = (n) => `bh2026112${n}abcd`;

const BH = (x = {}) => ({
  ma: MA(0), khoa: "cap_co_so", ten: "Caption có con số", goi_y: "Viết ít nhất 40 caption có con số.", huong: "tang", nguon: "poster_view",
  trang_thai: "hieu_luc", ngay_dat_lien_tiep: 3, bat_luc: "2026-11-20T12:01:00+07:00", het_han_luc: "2026-12-04",
  tat_luc: null, tat_boi: null, ly_do_tat: null, ten_ly_do_tat: null, bang_chung: { so_uid: 21, nhat_quan_pt: 81, lift_pt: 22 },
  so_sp_da_ap: 4, tuan_thu: null, co_the_hoan_tac: true, co_the_bat_lai: false, bat_lai_den: null, ...x,
});
const BC = (x = {}) => ({
  ngay: "2026-11-23",
  lan: { trang_thai: "xong", ly_do: "", ten_ly_do: "", viec_id: "j20261123120000abcd", bat_dau_luc: "2026-11-23T12:00:05+07:00", ket_thuc_luc: "2026-11-23T12:00:40+07:00", du_lieu_moi: true },
  nguon: {
    poster_view: { trang_thai: "ok", ngay_moi_nhat: "2026-11-23", so_ngay_cu: 0, so_video_hop_le: 247, so_uid: 47, so_lan_do_ngay: 130, trung_vi_lan_do_7_ngay: 120,
      bo_caption_ngoai_kho: 3, bo_mo_ho: 1, quet_hom_nay: { trang_thai: "ok", ly_do: null, ten_ly_do: null, viec_id: "j20261123090000abcd" } },
    van_hanh: { trang_thai: "ok", so_viec: 40, so_loi: 3 },
    sua_tay: { trang_thai: "chua_co_nguon" },
  },
  thay_doi: [], hieu_luc: [], ung_vien: [], da_tat: [],
  do_luong: [{ khoa: "cap_co_so", ten: "Caption có con số", nguon: "poster_view", huong: "tang", so_uid: 7, so_nhom: 9, so_caption: 60, so_video: 120, lift_pt: 12, nhat_quan_pt: 57, dat: false, thieu: ["so_uid"] }],
  canh_bao_van_hanh: [],
  chi_so_7_ngay: { ngay_may_bat: 7, ngay_quet_ok: 6, ngay_hoc_chay: 7, ngay_du_lieu_moi: 5 },
  nguong: { so_uid_toi_thieu: 20, so_video_toi_thieu: 200, lift_toi_thieu_pt: 15, nhat_quan_toi_thieu_pt: 80, ngay_lien_tiep: 3, van_hanh: {} },
  ...x,
});
const pv = (x) => ({ ...BC().nguon, poster_view: { ...BC().nguon.poster_view, ...x } });
const demNut = (h, act) => (h.match(new RegExp(`data-hc-act="${act}"`, "g")) || []).length;

// ---------- 1. escape ----------
test("escape: mọi chuỗi từ API (ten, goi_y, ten_ly_do*, tat_boi, thieu, ngày, mã) qua esc ở khối Hôm nay và trang #/hoc", () => {
  const xau = BH({ ten: BAN, goi_y: BAN, ten_ly_do_tat: BAN, tat_boi: BAN, khoa: BAN, het_han_luc: BAN, bat_lai_den: BAN, nguon: BAN, huong: BAN });
  const bc = BC({
    ngay: BAN,
    lan: { trang_thai: "tu_dung", ten_ly_do: BAN },
    nguon: { poster_view: { so_ngay_cu: 3, ngay_moi_nhat: BAN, trang_thai: BAN, quet_hom_nay: { trang_thai: "loi", ten_ly_do: BAN } }, van_hanh: { trang_thai: BAN }, sua_tay: { trang_thai: BAN } },
    thay_doi: [{ ma: MA(1), khoa: BAN, ten: BAN, huong: BAN, tu: BAN, den: BAN, ly_do: BAN, boi: BAN }],
    hieu_luc: [xau], ung_vien: [{ ...xau, trang_thai: "ung_vien" }],
    da_tat: [{ ...xau, trang_thai: "hoan_tac", co_the_bat_lai: true }, { ...xau, trang_thai: "tat_tu_dong", co_the_bat_lai: true }],
    do_luong: [{ khoa: BAN, ten: BAN, nguon: BAN, huong: BAN, so_uid: BAN, dat: BAN, thieu: [BAN] }],
    canh_bao_van_hanh: [{ khoa: BAN, ten: BAN, so_lan: BAN, so_viec: 2, cua_so_ngay: 14 }],
    chi_so_7_ngay: { ngay_may_bat: BAN },
    nguong: { so_uid_toi_thieu: BAN },
  });
  const h = F.hcTrangHtml(bc, CHIEU, true);
  KHONG_LOT(h, "trang #/hoc");
  assert.ok(h.includes(esc(BAN)), "chuỗi xấu vẫn hiện (đã esc)");
  const k = F.hcKhoiHomNayHtml(bc, CHIEU);
  KHONG_LOT(k, "khối Hôm nay");
  assert.ok(k.includes(esc(BAN)), "ten_ly_do của lượt quét hiện đã esc");
  // mã sai dạng (chèn thuộc tính) → không có nút, không lọt vào thuộc tính
  const t = F.hcTrangHtml(BC({ hieu_luc: [BH({ ma: `${MA(0)}" autofocus x="` })] }), CHIEU, true);
  assert.equal(demNut(t, "hoan-tac"), 0);
  assert.ok(!t.includes("autofocus"));
  // số giả dạng chuỗi không vẽ thô
  assert.ok(!F.hcTrangHtml(BC({ chi_so_7_ngay: { ngay_may_bat: "<b>9</b>" } }), CHIEU, true).includes("<b>9</b>"));
});

// ---------- 2. nút theo cờ ----------
test("nút Hoàn tác chỉ khi co_the_hoan_tac === true (hiệu lực + ứng viên); người thường (chu≠true) không có nút ghi nào", () => {
  const bc = BC({
    hieu_luc: [BH({ ma: MA(1) }), BH({ ma: MA(2), co_the_hoan_tac: false }), BH({ ma: MA(3), co_the_hoan_tac: "true" })],
    ung_vien: [BH({ ma: MA(4), trang_thai: "ung_vien", bat_luc: null, ngay_dat_lien_tiep: 2 }), BH({ ma: MA(5), trang_thai: "ung_vien", co_the_hoan_tac: false })],
  });
  const h = F.hcTrangHtml(bc, CHIEU, true);
  assert.equal(demNut(h, "hoan-tac"), 2);
  assert.match(h, new RegExp(`data-hc-act="hoan-tac" data-hc-ma="${MA(1)}"`));
  assert.match(h, new RegExp(`data-hc-act="hoan-tac" data-hc-ma="${MA(4)}"`));
  assert.equal(demNut(h, "bat-lai"), 0);
  assert.match(h, /đạt 2\/3 ngày liền/);
  for (const chu of [false, undefined, "true"]) {
    const t = F.hcTrangHtml({ ...bc, da_tat: [BH({ ma: MA(6), trang_thai: "het_han", co_the_bat_lai: true })] }, CHIEU, chu);
    assert.equal(demNut(t, "hoan-tac") + demNut(t, "bat-lai"), 0, `chu=${chu}`);
  }
});

test("mục 'Đã tự tắt / hết hạn / đã hoàn tác': nút Bật lại chỉ khi co_the_bat_lai (kể cả bài hoan_tac); web không tự tính điều kiện", () => {
  const bc = BC({
    da_tat: [
      BH({ ma: MA(1), trang_thai: "tat_tu_dong", ly_do_tat: "het_bang_chung", ten_ly_do_tat: "hết bằng chứng giữ", co_the_hoan_tac: false, co_the_bat_lai: true, tat_luc: "2026-11-22T12:00:00+07:00", tat_boi: "may" }),
      BH({ ma: MA(2), trang_thai: "het_han", co_the_hoan_tac: false, co_the_bat_lai: false }),
      BH({ ma: MA(3), trang_thai: "hoan_tac", co_the_hoan_tac: false, co_the_bat_lai: true, tat_luc: "2026-11-22T09:00:00+07:00", tat_boi: "nhan", bat_lai_den: "2026-11-29" }),
      BH({ ma: MA(4), trang_thai: "hoan_tac", co_the_hoan_tac: false, co_the_bat_lai: false, tat_luc: "2026-11-10T09:00:00+07:00", tat_boi: "nhan", bat_lai_den: "2026-11-17" }),
      BH({ ma: MA(5), trang_thai: "tat_tu_dong", co_the_hoan_tac: true, co_the_bat_lai: false }), // cờ hoàn tác sai chỗ → vẫn không nút
    ],
  });
  const h = F.hcTrangHtml(bc, CHIEU, true);
  assert.match(h, /Đã tự tắt \/ hết hạn \/ đã hoàn tác/);
  assert.equal(demNut(h, "bat-lai"), 2);
  assert.match(h, new RegExp(`data-hc-act="bat-lai" data-hc-ma="${MA(1)}"`));
  assert.match(h, new RegExp(`data-hc-act="bat-lai" data-hc-ma="${MA(3)}"`));
  assert.equal(demNut(h, "hoan-tac"), 0);
  // đủ 3 trạng thái hiện trong mục (bài đã đổi trạng thái không biến mất)
  for (const n of [1, 2, 3, 4, 5]) assert.ok(h.includes(MA(n)) || n === 2 || n === 4 || n === 5, MA(n));
  assert.match(h, /Tự tắt/); assert.match(h, /Hết hạn/); assert.match(h, /Đã hoàn tác/);
  assert.match(h, /hết bằng chứng giữ/);
});

test("bài hoan_tac (Q8): trong hạn có nút + 'Bật lại được tới hết dd/mm' từ bat_lai_den; quá hạn không nút + câu 'Đã quá 7 ngày…'", () => {
  const trong = F.hcNutHtml(BH({ trang_thai: "hoan_tac", co_the_hoan_tac: false, co_the_bat_lai: true, bat_lai_den: "2026-11-29" }), CHIEU, true);
  assert.match(trong, /data-hc-act="bat-lai"/);
  assert.match(trong, /Bật lại được tới hết 29\/11/);
  assert.ok(!/Đã quá 7 ngày/.test(trong));
  const qua = F.hcNutHtml(BH({ trang_thai: "hoan_tac", co_the_hoan_tac: false, co_the_bat_lai: false, bat_lai_den: "2026-11-15" }), CHIEU, true);
  assert.ok(!/data-hc-act/.test(qua), "quá hạn không nút");
  assert.match(qua, /Đã quá 7 ngày, chờ bộ học tự học lại sau 30 ngày cấm/);
  // ngày cuối (bat_lai_den = hôm nay) mà máy nhà vẫn cho → có nút; máy nhà không cho (lý do khác) → không nút, không nói "quá 7 ngày"
  assert.match(F.hcNutHtml(BH({ trang_thai: "hoan_tac", co_the_bat_lai: true, bat_lai_den: "2026-11-23" }), CHIEU, true), /tới hết 23\/11/);
  const khac = F.hcNutHtml(BH({ trang_thai: "hoan_tac", co_the_bat_lai: false, bat_lai_den: "2026-11-25" }), CHIEU, true);
  assert.ok(!/data-hc-act/.test(khac));
  assert.ok(!/Đã quá 7 ngày/.test(khac));
  assert.match(khac, /25\/11/);
  // thiếu bat_lai_den → coi như hết hạn
  assert.match(F.hcNutHtml(BH({ trang_thai: "hoan_tac", co_the_bat_lai: false, bat_lai_den: null }), CHIEU, true), /Đã quá 7 ngày/);
});

test("hộp xác nhận: hoàn tác; bật lại (14 ngày + ngưỡng giữ); vận hành 28 ngày; hoan_tac không có bat_luc → 'Khôi phục … về ứng viên'", () => {
  assert.match(F.hcCauXacNhan("hoan-tac", BH()), /^Hoàn tác gợi ý 'Caption có con số'\?/);
  assert.equal(F.hcCauXacNhan("bat-lai", BH({ trang_thai: "tat_tu_dong" })),
    "Bật lại gợi ý 'Caption có con số'? Gợi ý sẽ vào phiếu phân tích mới trong 14 ngày, và tự tắt lại nếu lần học kế tiếp không còn đủ bằng chứng giữ (≥ 20 SP, ≥ 60% cùng chiều).");
  assert.match(F.hcCauXacNhan("bat-lai", BH({ trang_thai: "hoan_tac", bat_luc: "2026-11-20T12:00:00+07:00" })), /^Bật lại gợi ý .*14 ngày/);
  assert.match(F.hcCauXacNhan("bat-lai", BH({ trang_thai: "het_han", nguon: "van_hanh" })), /trong 28 ngày/);
  assert.equal(F.hcCauXacNhan("bat-lai", BH({ trang_thai: "hoan_tac", bat_luc: null })),
    "Khôi phục 'Caption có con số' về ứng viên? Gợi ý chưa vào phiếu, vẫn phải đạt đủ ngày liên tiếp như thường.");
  // ký tự điều khiển trong tên bị bỏ, tên dài bị cắt
  const c = F.hcCauXacNhan("bat-lai", BH({ trang_thai: "hoan_tac", bat_luc: null, ten: "a\nb" + "x".repeat(300) }));
  assert.ok(!c.includes("\n") && c.length < 260);
});

// ---------- 3. cảnh báo nguồn ----------
test("3 mức cảnh báo nguồn: đỏ khi so_ngay_cu ≥ 2; vàng khi quét lỗi hoặc (sau 12:00 và so_ngay_cu == 1); bình thường không cảnh báo", () => {
  let c = F.hcCanhBao(BC({ nguon: pv({ so_ngay_cu: 2, ngay_moi_nhat: "2026-11-21" }) }), CHIEU);
  assert.deepEqual(c, [{ muc: "do", cau: "Nguồn view đã cũ 2 ngày (lần có số mới nhất 21/11) — bộ học đang tạm dừng" }]);
  c = F.hcCanhBao(BC({ nguon: pv({ quet_hom_nay: { trang_thai: "loi", ly_do: "kenh_loi", ten_ly_do: "Một kênh quét lỗi" } }) }), SANG);
  assert.deepEqual(c, [{ muc: "vang", cau: "Quét view hôm nay lỗi: Một kênh quét lỗi" }]);
  c = F.hcCanhBao(BC({ nguon: pv({ so_ngay_cu: 1, ngay_moi_nhat: "2026-11-22" }) }), CHIEU);
  assert.deepEqual(c, [{ muc: "vang", cau: "Hôm nay chưa có view mới" }]);
  assert.deepEqual(F.hcCanhBao(BC({ nguon: pv({ so_ngay_cu: 1 }) }), SANG), [], "trước 12:00 chưa báo");
  assert.deepEqual(F.hcCanhBao(BC(), CHIEU), []);
  assert.deepEqual(F.hcCanhBao(BC({ nguon: pv({ so_ngay_cu: null }) }), CHIEU), []);
  // đỏ + quét lỗi cùng lúc → 2 dòng
  c = F.hcCanhBao(BC({ nguon: pv({ so_ngay_cu: 4, ngay_moi_nhat: "2026-11-19", quet_hom_nay: { trang_thai: "loi", ten_ly_do: "Quá giờ" } }) }), CHIEU);
  assert.deepEqual(c.map((x) => x.muc), ["do", "vang"]);
  // khối Hôm nay: dòng đỏ dùng lớp đỏ, vàng lớp vàng, câu thường; link #/hoc
  const k = F.hcKhoiHomNayHtml(BC({ nguon: pv({ so_ngay_cu: 4, ngay_moi_nhat: "2026-11-19", quet_hom_nay: { trang_thai: "loi", ten_ly_do: "Quá giờ" } }) }), CHIEU);
  assert.match(k, /<h2 class="hn-tieu-de">📈 Học hôm nay<\/h2>/);
  assert.match(k, /class="hn-tt hn-loi" data-hc-muc="do">Nguồn view đã cũ 4 ngày \(lần có số mới nhất 19\/11\)/);
  assert.match(k, /class="hn-tt hn-cho-ban" data-hc-muc="vang">Quét view hôm nay lỗi: Quá giờ/);
  assert.match(k, /href="#\/hoc"/);
  const thuong = F.hcKhoiHomNayHtml(BC(), CHIEU);
  assert.ok(!/data-hc-muc="(do|vang)"/.test(thuong));
  assert.equal((thuong.match(/data-hc-muc=/g) || []).length, 1, "chỉ 1 dòng thường");
});

test("câu bình thường: không đổi gì — chưa đủ mẫu (cần 20 SP, đang có N); đã bật N gợi ý mới; đã tự tắt N gợi ý (hết bằng chứng); lần học lỗi/tạm dừng", () => {
  const C = (bc) => F.hcCauHomNay(bc, CHIEU);
  assert.equal(C(BC()), "Hôm nay: không đổi gì — chưa đủ mẫu (cần 20 SP, đang có 7)");
  assert.equal(C(BC({ do_luong: [] })), "Hôm nay: không đổi gì — chưa đủ mẫu (cần 20 SP, đang có 0)");
  assert.equal(C(BC({ do_luong: [{ nguon: "poster_view", so_uid: 22 }, { nguon: "van_hanh", so_uid: 99 }] })), "Hôm nay: không đổi gì");
  assert.equal(C(BC({ thay_doi: [{ ma: MA(1), tu: "ung_vien", den: "hieu_luc", ly_do: "dat_nguong_3_ngay" }] })), "Đã bật 1 gợi ý mới");
  assert.equal(C(BC({ thay_doi: [{ ma: MA(1), tu: "hieu_luc", den: "tat_tu_dong", ly_do: "het_bang_chung" }] })), "Đã tự tắt 1 gợi ý (hết bằng chứng)");
  assert.equal(C(BC({ thay_doi: [{ tu: "ung_vien", den: "hieu_luc" }, { tu: "hieu_luc", den: "tat_tu_dong", ly_do: "__proto__" }] })), "Đã bật 1 gợi ý mới · Đã tự tắt 1 gợi ý");
  assert.equal(C(BC({ lan: { trang_thai: "tu_dung", ten_ly_do: "Hôm nay chưa có số view mới" } })), "Hôm nay bộ học tạm dừng: Hôm nay chưa có số view mới");
  assert.equal(C(BC({ lan: { trang_thai: "loi", ten_ly_do: "" } })), "Lần học hôm nay bị lỗi");
});

// ---------- HT-W2b mục 1 (P1-1): so ngày báo cáo với hôm nay giờ VN ----------
test("W2b-1 ngày số liệu: cùng ngày → 'Hôm nay:' + 'Số liệu ngày dd/mm (hôm nay)', không đỏ 'chưa chạy'", () => {
  const bc = BC();
  assert.ok(!F.hcCanhBao(bc, CHIEU).some((c) => /chưa chạy từ/.test(c.cau)));
  assert.match(F.hcCauHomNay(bc, CHIEU), /^Hôm nay: không đổi gì/);
  const k = F.hcKhoiHomNayHtml(bc, CHIEU);
  assert.match(k, /Số liệu ngày 23\/11 \(hôm nay\)/);
  assert.ok(!/data-hc-muc="do"/.test(k));
  const t = F.hcTrangHtml(bc, CHIEU, true);
  assert.match(t, /Số liệu ngày 23\/11 \(hôm nay\)/);
  assert.match(t, /Thay đổi hôm nay/);
});

test("W2b-1 ngày số liệu: cũ 1 ngày TRƯỚC 12:00 → không đỏ, ghi 'Số liệu ngày dd/mm', câu 'Ngày dd/mm:' (không 'Hôm nay:')", () => {
  const bc = BC({ ngay: "2026-11-22" });
  assert.deepEqual(F.hcCanhBao(bc, SANG), []);
  assert.equal(F.hcCauHomNay(bc, SANG), "Ngày 22/11: không đổi gì — chưa đủ mẫu (cần 20 SP, đang có 7)");
  const k = F.hcKhoiHomNayHtml(bc, SANG);
  assert.match(k, /Số liệu ngày 22\/11</);
  assert.ok(!/\(hôm nay\)|Hôm nay:/.test(k), k);
  assert.ok(!/data-hc-muc="do"/.test(k));
  const t = F.hcTrangHtml(bc, SANG, true);
  assert.match(t, /Số liệu ngày 22\/11</);
  assert.match(t, /Thay đổi ngày 22\/11/);
  assert.ok(!/Hôm nay:|Thay đổi hôm nay|Đo lường hôm nay/.test(t));
  // 00:30 sáng 23/11 giờ VN (= 17:30 UTC ngày 22): vẫn là "cũ 1 ngày, trước 12:00" theo giờ VN
  assert.deepEqual(F.hcCanhBao(bc, Date.parse("2026-11-22T17:30:00Z")), []);
  assert.match(F.hcCauHomNay(bc, Date.parse("2026-11-22T17:30:00Z")), /^Ngày 22\/11:/);
  // 23:30 ngày 22 giờ VN (= 16:30 UTC): cùng ngày
  assert.match(F.hcCauHomNay(bc, Date.parse("2026-11-22T16:30:00Z")), /^Hôm nay:/);
});

test("W2b-1 ngày số liệu: cũ 1 ngày SAU 12:00 và cũ ≥ 2 ngày (kể cả sáng) → dòng ĐỎ 'Bộ học chưa chạy từ dd/mm'", () => {
  const cu1 = BC({ ngay: "2026-11-22" });
  assert.deepEqual(F.hcCanhBao(cu1, CHIEU), [{ muc: "do", cau: "Bộ học chưa chạy từ 22/11" }]);
  const cu3 = BC({ ngay: "2026-11-20" });
  assert.deepEqual(F.hcCanhBao(cu3, SANG), [{ muc: "do", cau: "Bộ học chưa chạy từ 20/11" }]);
  assert.deepEqual(F.hcCanhBao(cu3, CHIEU), [{ muc: "do", cau: "Bộ học chưa chạy từ 20/11" }]);
  assert.match(F.hcCauHomNay(cu3, CHIEU), /^Ngày 20\/11: không đổi gì/);
  // Tái hiện phiếu: bc.ngay = 18/11, 15:00 ngày 23 → dòng đỏ, không 'Hôm nay:'
  const k = F.hcKhoiHomNayHtml(BC({ ngay: "2026-11-18" }), Date.parse("2026-11-23T15:00:00+07:00"));
  assert.match(k, /class="hn-tt hn-loi" data-hc-muc="do">Bộ học chưa chạy từ 18\/11</);
  assert.match(k, /Số liệu ngày 18\/11</);
  assert.ok(!/Hôm nay:/.test(k), k);
  assert.match(k, /Ngày 18\/11: không đổi gì/);
  // cảnh báo nguồn của báo cáo cũ ghi theo ngày của báo cáo, không nói "hôm nay"
  const c = F.hcCanhBao(BC({ ngay: "2026-11-20", nguon: pv({ so_ngay_cu: 1, quet_hom_nay: { trang_thai: "loi", ten_ly_do: "Quá giờ" } }) }), CHIEU);
  assert.equal(c[0].cau, "Bộ học chưa chạy từ 20/11");
  assert.ok(c.slice(1).every((x) => !/hôm nay/i.test(x.cau) && /20\/11/.test(x.cau)), JSON.stringify(c));
  // trạng thái lần học của ngày cũ: không nói "hôm nay"
  for (const tt of ["loi", "tu_dung", "dang_chay", "khong_chay"]) {
    const cau = F.hcCauHomNay(BC({ ngay: "2026-11-20", lan: { trang_thai: tt } }), CHIEU);
    assert.ok(!/hôm nay/i.test(cau) && /20\/11/.test(cau), `${tt}: ${cau}`);
  }
  // tóm tắt thay đổi của ngày cũ ghi rõ ngày
  assert.equal(F.hcCauHomNay(BC({ ngay: "2026-11-20", thay_doi: [{ tu: "ung_vien", den: "hieu_luc" }] }), CHIEU), "Ngày 20/11: Đã bật 1 gợi ý mới");
});

// ---------- HT-W2b mục 2 (P3-1): bộ mã khớp runner ----------
test("W2b-2 HC_THIEU khớp ĐÚNG bộ khoá TEN_THIEU của hoc_danh_muc.py (không thiếu, không thừa)", () => {
  const py = pyKhoaDict("TEN_THIEU");
  assert.ok(py.length >= 8, py.join(","));
  assert.deepEqual(Object.keys(F.HC_THIEU).sort(), [...py].sort());
  for (const k of py) assert.ok(typeof F.HC_THIEU[k] === "string" && F.HC_THIEU[k], k);
  // mã vận hành/hướng lệch hiện nhãn, không hiện mã thô
  const h = F.hcTrangHtml(BC({ do_luong: [{ ten: "Phân tích bị quá giờ", nguon: "van_hanh", so_uid: 2, so_video: 30, nhat_quan_pt: 6, dat: false, thieu: ["so_lan", "ty_le"] },
    { ten: "Caption có emoji", nguon: "poster_view", so_uid: 21, dat: false, thieu: ["huong_lech", "chua_co_nguon"] }] }), CHIEU, true);
  for (const k of ["so_lan", "ty_le", "huong_lech", "chua_co_nguon"]) {
    assert.ok(h.includes(esc(F.HC_THIEU[k])), k);
    assert.ok(!new RegExp(`[ ,]${k}[,<]`).test(h), `lộ mã thô ${k}`);
  }
});

test("W2b-2 HC_LY_DO_NGAN phủ mọi mã chuyển trạng thái hiện trong thay_doi (LY_DO_CHUYEN trừ LY_DO_THUONG_NGAY), không khoá lạ", () => {
  const chuyen = pyTuple("LY_DO_CHUYEN");
  const m = PY_DM.match(/\nLY_DO_THUONG_NGAY[^=]*= frozenset\(\{([^}]*)\}\)/);
  assert.ok(m, "thiếu LY_DO_THUONG_NGAY");
  const thuong = [...m[1].matchAll(/"([a-z0-9_]+)"/g)].map((x) => x[1]);
  assert.ok(chuyen.length >= 12 && thuong.length >= 3);
  const can = chuyen.filter((k) => !thuong.includes(k));
  for (const k of can) assert.ok(typeof F.HC_LY_DO_NGAN[k] === "string" && F.HC_LY_DO_NGAN[k], `thiếu nhãn ${k}`);
  for (const k of Object.keys(F.HC_LY_DO_NGAN)) assert.ok(can.includes(k), `khoá thừa ${k}`);
  // báo cáo lọc LY_DO_THUONG_NGAY khỏi thay_doi (kho_hoc.py) — giả định của test này
  assert.match(PY_KHO, /for t in thay if t\["ly_do"\] not in dm\.LY_DO_THUONG_NGAY\]/);
});

// ---------- HT-W2b mục 3 (P3-2): bài vận hành ----------
test("W2b-3 bài VẬN HÀNH hiện 'N lần / M việc (x%)', không 'SP / cùng chiều / lệch'; bài caption giữ nguyên", () => {
  const vh = F.hcBaiHtml(BH({ khoa: "pt_qua_gio", ten: "Phân tích bị quá giờ", nguon: "van_hanh", huong: "tang",
    bang_chung: { so_uid: 4, so_video: 15, nhat_quan_pt: 26, lift_pt: 0 } }), CHIEU, true, 3);
  assert.match(vh, /4 lần \/ 15 việc \(26%\)/);
  assert.ok(!/ SP|cùng chiều|lệch /.test(vh), vh);
  const cap = F.hcBaiHtml(BH(), CHIEU, true, 3);
  assert.match(cap, /21 SP · 81% cùng chiều · lệch 22%/);
  assert.ok(!/ lần \//.test(cap));
  // thiếu số → không vẽ số giả
  assert.ok(!/undefined|NaN/.test(F.hcBaiHtml(BH({ nguon: "van_hanh", bang_chung: {} }), CHIEU, true, 3)));
  // tuan_thu (dict số nguyên, phiếu song song) có hay null đều không vỡ
  for (const tt of [null, { so_uid_ap: 3, so_uid_theo: 2 }, "x"]) assert.doesNotThrow(() => F.hcBaiHtml(BH({ tuan_thu: tt }), CHIEU, true, 3));
});

// ---------- HT-W2b mục 4 (P3-3, P3-7): tóm tắt đủ sự kiện, câu Bật lại đúng nghĩa ----------
test("W2b-4 tóm tắt: hoàn tác, bật lại về ứng viên, ứng viên dừng (dut_chuoi) KHÔNG đếm là 'tự tắt gợi ý'", () => {
  const C = (td) => F.hcCauHomNay(BC({ thay_doi: td }), CHIEU);
  assert.equal(C([{ tu: "hieu_luc", den: "hoan_tac", ly_do: "nguoi_hoan_tac" }]), "Đã hoàn tác 1 gợi ý");
  assert.equal(C([{ tu: "ung_vien", den: "hoan_tac", ly_do: "nguoi_hoan_tac" }, { tu: "hieu_luc", den: "hoan_tac", ly_do: "nguoi_hoan_tac" }]), "Đã hoàn tác 2 gợi ý");
  assert.equal(C([{ tu: "hoan_tac", den: "ung_vien", ly_do: "nguoi_bat_lai" }]), "Đã khôi phục 1 gợi ý về ứng viên");
  assert.equal(C([{ tu: "hoan_tac", den: "hieu_luc", ly_do: "nguoi_bat_lai" }]), "Đã bật lại 1 gợi ý");
  const dc = C([{ tu: "ung_vien", den: "tat_tu_dong", ly_do: "dut_chuoi" }]);
  assert.equal(dc, "1 ứng viên dừng (không còn đạt ngưỡng)");
  assert.ok(!/tự tắt/.test(dc));
  assert.equal(C([{ tu: "ung_vien", den: "tat_tu_dong", ly_do: "dut_chuoi" }, { tu: "hieu_luc", den: "tat_tu_dong", ly_do: "doi_chieu" }]),
    "Đã tự tắt 1 gợi ý (đổi chiều) · 1 ứng viên dừng (không còn đạt ngưỡng)");
  assert.equal(C([{ tu: "ung_vien", den: "ung_vien", ly_do: "cho_suc_chua" }]), "1 ứng viên đủ ngày, chờ chỗ trống");
  assert.equal(C([{ tu: null, den: "ung_vien", ly_do: "dat_lan_dau" }]), "1 ứng viên mới");
  // khối Hôm nay sau khi hoàn tác không còn "không đổi gì"
  assert.ok(!/không đổi gì/.test(F.hcKhoiHomNayHtml(BC({ thay_doi: [{ tu: "hieu_luc", den: "hoan_tac", ly_do: "nguoi_hoan_tac" }] }), CHIEU)));
});

test("W2b-4 nút: ứng viên tự tắt (không bat_luc) → câu 'không bật lại được' vĩnh viễn, không 'lúc này'; bài từng hiệu lực mà máy nhà không cho → 'lúc này'", () => {
  const uv = F.hcNutHtml(BH({ trang_thai: "tat_tu_dong", bat_luc: null, ly_do_tat: "dut_chuoi", co_the_hoan_tac: false, co_the_bat_lai: false }), CHIEU, true);
  assert.ok(!/data-hc-act/.test(uv));
  assert.ok(!/lúc này/.test(uv), uv);
  assert.match(uv, /không bật lại được/);
  assert.match(uv, /tự xét lại/);
  const hl = F.hcNutHtml(BH({ trang_thai: "tat_tu_dong", co_the_hoan_tac: false, co_the_bat_lai: false }), CHIEU, true);
  assert.match(hl, /Chưa bật lại được lúc này/);
  const hh = F.hcNutHtml(BH({ trang_thai: "het_han", co_the_hoan_tac: false, co_the_bat_lai: false }), CHIEU, true);
  assert.match(hh, /Chưa bật lại được lúc này/);
});

// ---------- HT-W2b mục 5 (P3-4): bởi hệ thống ----------
test("W2b-5 tat_boi 'he_thong' (kho_hoc.BOI_HE_THONG) hiện 'bởi hệ thống'; tên người giữ nguyên", () => {
  assert.match(PY_KHO, /^BOI_HE_THONG = "he_thong"$/m);
  const h = F.hcBaiHtml(BH({ trang_thai: "tat_tu_dong", tat_luc: "2026-11-22T12:00:00+07:00", tat_boi: "he_thong", co_the_bat_lai: false }), CHIEU, true, 3);
  assert.match(h, /ngày 22\/11 bởi hệ thống/);
  assert.ok(!h.includes("he_thong"));
  assert.match(F.hcBaiHtml(BH({ trang_thai: "hoan_tac", tat_luc: "2026-11-22T09:00:00+07:00", tat_boi: "nhan" }), CHIEU, true, 3), /bởi nhan/);
});

// ---------- HT-W2b mục 6 (P3-5): phân biệt lỗi theo nguồn ----------
test("W2b-6 thân lỗi web dựa vào khớp nguồn thật: runner (TEN_LY_DO, §3.8), Worker (hoc.js/worker.js), video_server", () => {
  assert.equal(F.HC_LOI_CHUA_CO_LAN, pyTenLyDo("chua_co_lan_hoc"));
  assert.equal(F.HC_LOI_KHONG_BAI, pyTenLyDo("khong_co_bai_hoc"));
  assert.ok(DOC.includes(`{"loi":"${F.HC_LOI_CHUA_BAT}"}`), "§3.8: runner 503 Học tự động chưa bật");
  assert.ok(WORKER.includes("Khoá ký bộ chạy việc không hợp lệ (KY_RIENG)"));
  assert.ok(CF_HOC.includes('loi("Chưa cấu hình bộ chạy việc", 503)'));
  assert.ok(VSV.includes('_tu_choi(h, 404, "Đường dẫn không hợp lệ")'));
});

test("W2b-6 lỗi tải #/hoc: 404 'chưa có lần học' ≠ 404 khác (máy nhà chưa hỗ trợ); 503 runner chưa bật ≠ 503 Worker (KY_RIENG/cấu hình) ≠ 503 lạ (tạm)", () => {
  const L = (st, msg) => F.hcCauLoiTai(Object.assign(new Error(msg), { status: st }));
  assert.match(L(404, F.HC_LOI_CHUA_CO_LAN), /Bộ học chưa chạy lần nào/);
  for (const msg of ["Đường dẫn không hợp lệ", "không có API này", "Không có API này", "Lỗi 404", "chưa có lần học nào <b>"]) {
    const c = L(404, msg);
    assert.match(c, /Máy nhà chưa hỗ trợ học tự động — cần cập nhật máy nhà/, msg);
    assert.ok(!/chưa chạy lần nào|<b>/.test(c), msg);
  }
  assert.match(L(503, F.HC_LOI_CHUA_BAT), /Học tự động chưa bật trên máy nhà/);
  for (const msg of ["Khoá ký bộ chạy việc không hợp lệ (KY_RIENG)", "Chưa cấu hình bộ chạy việc"]) {
    const c = L(503, msg);
    assert.ok(!/Học tự động chưa bật/.test(c), c);
    assert.match(c, /cấu hình/, msg);
  }
  assert.match(L(503, "Lỗi 503"), /Bấm Tải lại/);
  assert.equal(F.hcLoaiLoi(new TypeError("Failed to fetch")), "tam");
});

// ---------- 4. homNayHtml ----------
const T = (x = {}) => ({ chu: true, nowMs: CHIEU, sk: { ok: true, d: { may_nha: true, apps: [] } }, viec: { ok: true, ds: [] },
  sp: { ok: true, ds: [{ id: "1729706628656957720", uid: "1729706628656957720", ten: "SP", trang_thai: "cho" }] }, anh: () => "", ...x });
test("homNayHtml: thiếu t.hoc → giống hệt bản cũ; hoc lỗi → không vẽ; có hoc (chủ kho) → khối trước danh sách SP; người thường không thấy", () => {
  const cu = F_CU.homNayHtml(T());
  assert.equal(F.homNayHtml(T()), cu, "thiếu t.hoc");
  assert.equal(F.homNayHtml(T({ hoc: { ok: false, loai: "tam" } })), cu, "nguồn học lỗi");
  assert.equal(F.homNayHtml(T({ hoc: { ok: true, d: null } })), cu, "báo cáo rỗng");
  const h = F.homNayHtml(T({ hoc: { ok: true, d: BC() } }));
  const iHoc = h.indexOf("📈 Học hôm nay"), iXong = h.indexOf("Xong hôm nay"), iSp = h.indexOf("hn-ds-sp");
  assert.ok(iXong > 0 && iXong < iHoc && iHoc < iSp, [iXong, iHoc, iSp].join(","));
  assert.match(h, /href="#\/hoc"/);
  // việc lỗi tạm vẫn hiện khối học
  assert.match(F.homNayHtml(T({ viec: { ok: false, loai: "tam" }, hoc: { ok: true, d: BC() } })), /📈 Học hôm nay/);
  // người thường: không khối, kể cả khi lỡ có dữ liệu
  const t = F.homNayHtml(T({ chu: false, hoc: { ok: true, d: BC() } }));
  assert.ok(!/Học hôm nay|#\/hoc/.test(t));
  assert.equal(t, F_CU.homNayHtml(T({ chu: false })));
});

// ---------- 5. trang #/hoc ----------
test("trang #/hoc: dòng 7 ngày (có dữ liệu mới tách riêng), nguồn (sửa tay: chưa có nguồn), đo lường, cảnh báo vận hành, ngưỡng", () => {
  const h = F.hcTrangHtml(BC({ canh_bao_van_hanh: [{ khoa: "pt_thieu_dau_ra", ten: "Phân tích thiếu đầu ra", so_lan: 4, so_viec: 15, cua_so_ngay: 14 }] }), CHIEU, true);
  assert.match(h, /7 ngày qua: máy bật 7 · quét view ổn 6 · học chạy 7 · <b>có dữ liệu mới 5<\/b>/);
  assert.match(h, /chưa có nguồn sửa tay/);
  assert.match(h, /247 video dùng được/);
  assert.match(h, /Caption có con số/);
  assert.match(h, /Phân tích thiếu đầu ra: 4 lần \/ 15 việc trong 14 ngày/);
  assert.match(h, /80% cùng chiều/);
  // khối "Đang dùng": hạn dùng + số phiếu đã áp
  const d = F.hcTrangHtml(BC({ hieu_luc: [BH()] }), CHIEU, true);
  assert.match(d, /dùng tới hết 04\/12/);
  assert.match(d, /đã vào 4 phiếu/);
  // báo cáo hỏng → không ném
  for (const x of [null, undefined, "x", [], { nguon: "x", hieu_luc: "x", da_tat: [null, 1] }]) assert.doesNotThrow(() => F.hcTrangHtml(x, CHIEU, true));
  assert.equal(F.hcKhoiHomNayHtml(null, CHIEU), "");
  assert.equal(F.hcKhoiHomNayHtml([], CHIEU), "");
});

test("lỗi tải trang #/hoc: phân biệt vĩnh viễn (401/403), chưa có lần học (404), chưa bật (503), tạm (mạng/5xx)", () => {
  const L = (st, msg = "x <b>") => F.hcCauLoiTai(Object.assign(new Error(msg), { status: st }));
  assert.match(L(401), /đăng nhập lại/);
  assert.match(L(403), /không xem được/);
  assert.match(L(404, "chưa có lần học nào"), /chưa chạy lần nào/);
  assert.match(L(503, "Học tự động chưa bật"), /chưa bật/);
  for (const st of [0, 500, 502, 504, undefined]) assert.match(L(st), /Bấm Tải lại/, `status ${st}`);
  assert.ok(!L(500).includes("<b>"), "không đưa chuỗi lỗi kỹ thuật ra");
  assert.match(F.hcCauLoiTai(new TypeError("Failed to fetch")), /Bấm Tải lại/);
});

test("hcDm: YYYY-MM-DD và ISO có giờ → dd/mm theo giờ VN; rác → ''", () => {
  assert.equal(F.hcDm("2026-11-29"), "29/11");
  assert.equal(F.hcDm("2026-11-22T18:30:00+00:00"), "23/11");
  for (const x of [null, 5, "", "29/11", BAN, "2026-11-29x"]) assert.equal(F.hcDm(x), "", String(x));
});

// ---------- 6. nhãn loại việc ----------
test("nhãn loại việc: TEN_LOAI_VIEC + LOI_LOAI_VIEC có hoc_hang_ngay, quet_view_hang_ngay; LOAI_VIEC_SP không có", () => {
  assert.equal(F.TEN_LOAI_VIEC.hoc_hang_ngay, "Học mỗi ngày");
  assert.equal(F.TEN_LOAI_VIEC.quet_view_hang_ngay, "Quét view video của mình");
  assert.equal(F.LOI_LOAI_VIEC.hoc_hang_ngay, "Học mỗi ngày");
  assert.equal(F.LOI_LOAI_VIEC.quet_view_hang_ngay, "Quét view video của mình");
  assert.equal(F.loiLoaiViec("quet_view_hang_ngay"), "Quét view video của mình");
  for (const l of ["hoc_hang_ngay", "quet_view_hang_ngay"]) assert.ok(!Object.prototype.hasOwnProperty.call(F.LOAI_VIEC_SP, l), l);
});

// ---------- 7. index.html, CSP, điện thoại ----------
// khung.js cũng đổi nhưng cf/test/poster-web.test.mjs:782 ghim cứng khung.js?v=4 (ngoài phạm vi phiếu) → chưa tăng, chờ trưởng phòng.
test("index.html: hoc.js?v=3 (HT-W3 đổi hoc.js) ngay sau homnay.js; tăng ?v= loi/homnay/viec; hoc.js không on…=, không style cứng/bảng (375px không cuộn ngang)", () => {
  assert.match(HTML, /<script src="homnay\.js\?v=\d+" defer><\/script>\s*<script src="hoc\.js\?v=3" defer><\/script>\s*<script src="viec\.js/);
  const v = (f) => Number((HTML.match(new RegExp(`${f.replace(".", "\\.")}\\?v=(\\d+)`)) || [])[1]);
  assert.ok(v("loi.js") >= 7, "loi.js");
  assert.ok(v("homnay.js") >= 7, "homnay.js");
  assert.ok(v("viec.js") >= 17, "viec.js");
  assert.ok(v("khung.js") >= 4, "khung.js");
  assert.ok(!/\son[a-z]+\s*=/i.test(HOC), "hoc.js có on…=");
  assert.ok(!/<table|style="|white-space:\s*nowrap|width:\s*\d/.test(HOC), "hoc.js có bảng/độ rộng cố định");
  assert.match(HOC, /addEventListener\("click"/);
  const tenDinh = [...HOC.matchAll(/^(?:async )?function\*? ?(\w+)|^(?:const|let|var|class) (\w+)/gm)].map((m) => m[1] || m[2]);
  assert.ok(tenDinh.length >= 10);
  for (const t of tenDinh) assert.ok(t.toLowerCase().startsWith("hc"), `hoc.js: "${t}" phải bắt đầu bằng hc`);
});

// ---------- 8. phần có DOM: hcRender / hcTai / hcBam với DOM + api giả ----------
function dungHc({ bc = BC({ hieu_luc: [BH({ ma: MA(1) })], da_tat: [BH({ ma: MA(2), trang_thai: "hoan_tac", co_the_hoan_tac: false, co_the_bat_lai: true, bat_luc: null, bat_lai_den: "2099-01-01" })] }),
  r = null, loi = null, loiTai = null, xacNhan = true, chu = true } = {}) {
  const goi = [], toasts = [], hop = [];
  const S = { cho: null, loiTai, bc, khoiHn: null };
  const taoNut = (h) => [...h.matchAll(/data-hc-act="([^"]*)" data-hc-ma="([^"]*)"/g)].map((m) => ({ dataset: { hcAct: m[1], hcMa: m[2] }, disabled: false }));
  const nd = { _h: "", nut: [], get innerHTML() { return this._h; }, set innerHTML(v) { this._h = v; this.nut = taoNut(v); },
    querySelectorAll(s) { return s === "[data-hc-ma]" ? this.nut : []; } };
  // Đổi trang (#app) → khối "Học hôm nay" cũ (nếu có) rời DOM.
  const app = { _h: "", get innerHTML() { return this._h; },
    set innerHTML(v) { this._h = v; nd.innerHTML = ""; if (S.khoiHn) S.khoiHn.isConnected = false; S.khoiHn = null; } };
  const hc = { nghe: {}, addEventListener(ev, f) { this.nghe[ev] = f; } };
  const taiLai = { disabled: false };
  const coHc = () => app._h.includes('id="hc"');
  const coHn = () => app._h.includes('id="hn"');
  const ns = {
    $: (s) => (s === "#app" ? app : s === "#hn .hn-hoc" ? (coHn() ? S.khoiHn : null)
      : !coHc() ? null : s === "#hc" ? hc : s === "#hc-nd" ? nd : s === "#hc-tai-lai" ? taiLai : null),
    document: { querySelectorAll: (s) => (s === "#hc [data-hc-ma]" && coHc() ? nd.nut : []) },
    toast: (m) => toasts.push(m), confirm: (m) => { hop.push(m); return xacNhan; }, laChu: () => chu,
    api: async (p, body) => {
      goi.push(body === undefined ? p : [p, body]);
      if (p === "hoc/bao-cao") {
        const bcLuc = S.bc, cho = S.choTai; // chụp lúc gửi: lượt về muộn mang dữ liệu CŨ
        if (cho) await cho;
        if (S.loiTai) throw S.loiTai;
        return { status: 200, ...bcLuc };
      }
      const m = p.match(/^hoc\/bai-hoc\/([^/]+)\/(hoan-tac|bat-lai)$/);
      if (!m) throw new Error("đường dẫn lạ " + p);
      if (nd.nut.some((n) => n.dataset.hcMa === m[1] && !n.disabled)) throw new Error("chưa khoá nút trước await");
      if (S.cho) await S.cho;
      if (loi) throw loi;
      return r || { status: 200, bai_hoc: {} };
    },
  };
  const ten = Object.keys(ns);
  const H = new Function("esc", ...ten, `"use strict";\nlet phienCT = 0;\n${HOC.replace(/^"use strict";$/m, "")}
return { hcRender, hcTai, hcBam, sang: () => ++phienCT, phien: () => phienCT, dangGui: () => hcDangGui.size };`)(esc, ...ten.map((k) => ns[k]));
  const nut = (ma, act) => nd.nut.find((n) => n.dataset.hcMa === ma && n.dataset.hcAct === act);
  // Mở trang Hôm nay (phiên mới) có khối "📈 Học hôm nay" (như renderHomNay của homnay.js vẽ).
  const moHomNay = () => {
    H.sang(); app.innerHTML = '<div class="hn" id="hn"><div id="hn-nd">…</div></div>';
    S.khoiHn = { outerHTML: '<section class="hn-khoi hn-hoc">CŨ</section>', isConnected: true };
    return S.khoiHn;
  };
  return { H, goi, toasts, hop, S, nd, app, hc, taiLai, nut, moHomNay };
}
const loiSt = (st) => Object.assign(new Error("x"), { status: st });

test("DOM: mở #/hoc gọi đúng 1 lần hoc/bao-cao, vẽ nút; bấm Hoàn tác → confirm → khoá nút TRƯỚC await → POST hoan-tac {} → toast → vẽ lại", async () => {
  const x = dungHc();
  await x.H.hcRender(x.H.sang());
  assert.deepEqual(x.goi, ["hoc/bao-cao"]);
  assert.match(x.app.innerHTML, /id="hc-nd"/);
  assert.equal(typeof x.hc.nghe.click, "function", "gắn click bằng addEventListener");
  const b = x.nut(MA(1), "hoan-tac");
  assert.ok(b);
  x.goi.length = 0;
  await x.H.hcBam(b);
  assert.match(x.hop[0], /^Hoàn tác gợi ý/);
  assert.deepEqual(x.goi, [[`hoc/bai-hoc/${MA(1)}/hoan-tac`, {}], "hoc/bao-cao"]);
  assert.match(x.toasts[0], /Đã hoàn tác/);
  assert.equal(x.H.dangGui(), 0);
});

test("DOM: bấm đúp (2 lần trước khi API trả) chỉ gửi 1 lần; huỷ confirm không gửi; người thường không gửi", async () => {
  const x = dungHc();
  await x.H.hcRender(x.H.sang());
  let mo; x.S.cho = new Promise((r) => { mo = r; });
  x.goi.length = 0;
  const b = x.nut(MA(1), "hoan-tac");
  const p1 = x.H.hcBam(b);
  const p2 = x.H.hcBam(b);
  assert.equal(b.disabled, true, "khoá ngay");
  mo(); await Promise.all([p1, p2]);
  assert.equal(x.goi.filter((g) => Array.isArray(g)).length, 1);
  assert.equal(x.hop.length, 1, "confirm 1 lần");
  const y = dungHc({ xacNhan: false });
  await y.H.hcRender(y.H.sang()); y.goi.length = 0;
  await y.H.hcBam(y.nut(MA(1), "hoan-tac"));
  assert.deepEqual(y.goi, []);
  assert.equal(y.nut(MA(1), "hoan-tac").disabled, false);
  const z = dungHc({ chu: false });
  await z.H.hcRender(z.H.sang()); z.goi.length = 0;
  // trang vẽ bởi người thường không có nút; bấm nút giả cũng không gửi
  assert.equal(z.nd.nut.length, 0);
  await z.H.hcBam({ dataset: { hcAct: "hoan-tac", hcMa: MA(1) }, disabled: false });
  assert.deepEqual(z.goi, []);
});

test("DOM: Bật lại bài hoàn tác lúc còn ứng viên dùng hộp 'Khôi phục … về ứng viên'; mã/hành động lạ hoặc cờ đã tắt → không gửi", async () => {
  const x = dungHc();
  await x.H.hcRender(x.H.sang()); x.goi.length = 0;
  await x.H.hcBam(x.nut(MA(2), "bat-lai"));
  assert.match(x.hop[0], /^Khôi phục 'Caption có con số' về ứng viên\?/);
  assert.deepEqual(x.goi[0], [`hoc/bai-hoc/${MA(2)}/bat-lai`, {}]);
  assert.match(x.toasts[0], /Đã bật lại/);
  x.goi.length = 0;
  await x.H.hcBam({ dataset: { hcAct: "xoa", hcMa: MA(1) }, disabled: false });
  await x.H.hcBam({ dataset: { hcAct: "hoan-tac", hcMa: "../x" }, disabled: false });
  await x.H.hcBam({ dataset: { hcAct: "bat-lai", hcMa: MA(1) }, disabled: false }); // MA(1) không có co_the_bat_lai
  assert.deepEqual(x.goi.filter((g) => Array.isArray(g)), []);
});

test("DOM: 409 → toast câu cố định của máy nhà + vẽ lại; 401 → giữ trang (không vẽ lại), mở khoá nút; 502/lỗi mạng → 'Chưa chắc đã xong…', giữ khoá tới khi Tải lại", async () => {
  const CAU = "đã quá 7 ngày kể từ lúc hoàn tác, không bật lại được nữa";
  let x = dungHc({ r: { status: 409, loi: CAU } });
  await x.H.hcRender(x.H.sang()); x.goi.length = 0;
  await x.H.hcBam(x.nut(MA(2), "bat-lai"));
  assert.ok(x.toasts[0].includes(CAU), x.toasts[0]);
  assert.deepEqual(x.goi.slice(1), ["hoc/bao-cao"], "vẽ lại");
  // 401
  x = dungHc({ loi: loiSt(401) });
  await x.H.hcRender(x.H.sang()); x.goi.length = 0;
  const truoc = x.nd.innerHTML;
  const b = x.nut(MA(1), "hoan-tac");
  await x.H.hcBam(b);
  assert.match(x.toasts[0], /Hết phiên đăng nhập/);
  assert.equal(x.goi.length, 1, "không tải lại");
  assert.equal(x.nd.innerHTML, truoc, "giữ nguyên trang");
  assert.equal(b.disabled, false, "mở khoá để bấm lại sau khi đăng nhập");
  // 502 (Worker: máy nhà lỗi) và lỗi mạng
  for (const e of [loiSt(502), loiSt(504), new TypeError("Failed to fetch")]) {
    x = dungHc({ loi: e });
    await x.H.hcRender(x.H.sang()); x.goi.length = 0;
    const n = x.nut(MA(1), "hoan-tac");
    await x.H.hcBam(n);
    assert.match(x.toasts[0], /Chưa chắc đã xong — bấm Tải lại để xem trạng thái thật/);
    assert.equal(x.goi.length, 1, "không tự tải lại");
    assert.equal(n.disabled, true, "giữ khoá");
    await x.H.hcBam(n); // bấm lại khi chưa rõ → không gửi
    assert.equal(x.goi.length, 1);
    // Tải lại thành công → nút mới mở
    await x.H.hcTai(x.H.phien(), true);
    assert.equal(x.nut(MA(1), "hoan-tac").disabled, false);
  }
});

test("DOM: đổi trang trong lúc chờ → không vẽ đè trang mới; vẫn dọn cờ đang gửi (tác dụng phụ không gắn phiên trang)", async () => {
  const x = dungHc();
  await x.H.hcRender(x.H.sang()); x.goi.length = 0;
  let mo; x.S.cho = new Promise((r) => { mo = r; });
  const p = x.H.hcBam(x.nut(MA(1), "hoan-tac"));
  x.H.sang(); x.app.innerHTML = "<p>trang khác</p>";
  mo(); await p;
  assert.equal(x.app.innerHTML, "<p>trang khác</p>");
  assert.deepEqual(x.goi.filter((g) => !Array.isArray(g)), [], "không tải lại báo cáo cho trang cũ");
  assert.equal(x.H.dangGui(), 0, "đã dọn cờ đang gửi");
  assert.equal(x.toasts.length, 1, "vẫn báo kết quả");
  // tải trang về muộn sau khi đã sang trang khác → bỏ
  const y = dungHc();
  let moTai; y.S.choTai = new Promise((r) => { moTai = r; });
  const q = y.H.hcRender(y.H.sang());
  y.H.sang(); y.app.innerHTML = "<p>khác</p>";
  moTai(); await q;
  assert.equal(y.app.innerHTML, "<p>khác</p>");
});

test("DOM: lượt tải cũ về muộn không vẽ đè — rời rồi quay lại #/hoc; hoặc Tải lại chậm bị lượt vẽ lại sau thao tác vượt", async () => {
  const CU = BC({ hieu_luc: [BH({ ma: MA(7), ten: "Bản CŨ" })] }), MOI = BC({ hieu_luc: [BH({ ma: MA(8), ten: "Bản MỚI" })] });
  // (a) mở #/hoc (lượt 1 chậm) → sang trang khác → quay lại #/hoc (lượt 2 nhanh) → lượt 1 về sau
  const x = dungHc({ bc: CU });
  let mo; x.S.choTai = new Promise((r) => { mo = r; });
  const p1 = x.H.hcRender(x.H.sang());
  x.H.sang(); x.app.innerHTML = "<p>khác</p>";
  x.S.choTai = null; x.S.bc = MOI;
  await x.H.hcRender(x.H.sang());
  assert.match(x.nd.innerHTML, /Bản MỚI/);
  mo(); await p1;
  assert.match(x.nd.innerHTML, /Bản MỚI/, "lượt cũ không vẽ đè trang mới");
  assert.ok(!x.nd.innerHTML.includes("Bản CŨ"));
  // (b) cùng trang: Tải lại chậm (dữ liệu cũ) → trong lúc đó Hoàn tác xong + vẽ lại (dữ liệu mới) → Tải lại về sau
  const y = dungHc({ bc: BC({ hieu_luc: [BH({ ma: MA(1) })] }) });
  await y.H.hcRender(y.H.sang());
  let moTai; y.S.choTai = new Promise((r) => { moTai = r; }); y.S.bc = CU;
  const tai = y.H.hcTai(y.H.phien(), true);
  y.S.choTai = null; y.S.bc = MOI;
  await y.H.hcBam(y.nut(MA(1), "hoan-tac"));
  assert.match(y.nd.innerHTML, /Bản MỚI/);
  moTai(); await tai;
  assert.match(y.nd.innerHTML, /Bản MỚI/, "lượt tải cũ hơn không vẽ đè lượt mới hơn");
});

test("DOM: Tải lại khoá nút TRƯỚC await (bấm liên tiếp chỉ 1 lần gọi); vẽ lại trong lúc đang gửi vẫn khoá nút của bài đang gửi", async () => {
  const x = dungHc();
  await x.H.hcRender(x.H.sang()); x.goi.length = 0;
  let moTai; x.S.choTai = new Promise((r) => { moTai = r; });
  const p = x.H.hcTai(x.H.phien(), true);
  assert.equal(x.taiLai.disabled, true);
  await x.H.hcTai(x.H.phien(), true);
  moTai(); await p;
  assert.deepEqual(x.goi, ["hoc/bao-cao"]);
  assert.equal(x.taiLai.disabled, false);
  x.S.choTai = null;
  let mo; x.S.cho = new Promise((r) => { mo = r; });
  const g = x.H.hcBam(x.nut(MA(1), "hoan-tac"));
  await x.H.hcTai(x.H.phien(), true); // vẽ lại giữa chừng
  assert.equal(x.nut(MA(1), "hoan-tac").disabled, true, "nút mới vẽ của bài đang gửi vẫn khoá");
  assert.equal(x.nut(MA(2), "bat-lai").disabled, false, "bài khác không khoá");
  mo(); await g;
});

test("DOM: lỗi tải báo câu lời thường theo loại (404 chưa có lần học), không lộ chuỗi lỗi máy chủ", async () => {
  const x = dungHc({ loiTai: Object.assign(new Error("chưa có lần học nào"), { status: 404 }) });
  await x.H.hcRender(x.H.sang());
  assert.match(x.nd.innerHTML, /chưa chạy lần nào/);
  assert.equal(x.taiLai.disabled, false);
  const y = dungHc({ loiTai: Object.assign(new Error("Đường dẫn không hợp lệ <b>"), { status: 404 }) }); // video_server chưa khởi động lại
  await y.H.hcRender(y.H.sang());
  assert.match(y.nd.innerHTML, /Máy nhà chưa hỗ trợ học tự động/);
  assert.ok(!y.nd.innerHTML.includes("<b>") && !y.nd.innerHTML.includes("Đường dẫn"));
});

test("W2b-6 DOM: POST 404 'không có bài học' → 'Không còn gợi ý này' + tải lại; 404 khác → 'chưa hỗ trợ', mở khoá, không tải lại", async () => {
  let x = dungHc({ loi: Object.assign(new Error("không có bài học"), { status: 404 }) });
  await x.H.hcRender(x.H.sang()); x.goi.length = 0;
  await x.H.hcBam(x.nut(MA(1), "hoan-tac"));
  assert.match(x.toasts[0], /Không còn gợi ý này trên máy nhà/);
  assert.deepEqual(x.goi.slice(1), ["hoc/bao-cao"]);
  for (const msg of ["Đường dẫn không hợp lệ", "không có API này", "Lỗi 404"]) {
    x = dungHc({ loi: Object.assign(new Error(msg), { status: 404 }) });
    await x.H.hcRender(x.H.sang()); x.goi.length = 0;
    const b = x.nut(MA(1), "hoan-tac");
    await x.H.hcBam(b);
    assert.match(x.toasts[0], /Máy nhà chưa hỗ trợ học tự động — cần cập nhật máy nhà/, msg);
    assert.ok(!/Không còn gợi ý/.test(x.toasts[0]), msg);
    assert.equal(x.goi.length, 1, "không tải lại");
    assert.equal(b.disabled, false, "mở khoá (chưa làm gì)");
  }
});

test("W2b-6 DOM: POST 503 runner chưa bật / Worker KY_RIENG / cấu hình → câu riêng, mở khoá; 503 lạ → 'Chưa chắc đã xong', giữ khoá", async () => {
  const ca = [["Học tự động chưa bật", /Học tự động chưa bật trên máy nhà — chưa làm gì/],
    ["Khoá ký bộ chạy việc không hợp lệ (KY_RIENG)", /cấu hình.*chưa làm gì/], ["Chưa cấu hình bộ chạy việc", /cấu hình.*chưa làm gì/]];
  for (const [msg, cau] of ca) {
    const x = dungHc({ loi: Object.assign(new Error(msg), { status: 503 }) });
    await x.H.hcRender(x.H.sang()); x.goi.length = 0;
    const b = x.nut(MA(1), "hoan-tac");
    await x.H.hcBam(b);
    assert.match(x.toasts[0], cau, msg);
    if (msg !== "Học tự động chưa bật") assert.ok(!/Học tự động chưa bật/.test(x.toasts[0]), msg);
    assert.equal(b.disabled, false, msg);
    assert.equal(x.goi.length, 1, msg);
  }
  const y = dungHc({ loi: Object.assign(new Error("Lỗi 503"), { status: 503 }) });
  await y.H.hcRender(y.H.sang()); y.goi.length = 0;
  const n = y.nut(MA(1), "hoan-tac");
  await y.H.hcBam(n);
  assert.match(y.toasts[0], /Chưa chắc đã xong/);
  assert.equal(n.disabled, true);
});

// ---------- HT-W2b mục 7 (P3-6): rời rồi quay lại #/hoc trong lúc POST chờ ----------
test("W2b-7 DOM: rời rồi quay lại #/hoc khi POST đang chờ → POST xong vẽ lại trang #/hoc phiên MỚI, nút mở khoá", async () => {
  const x = dungHc();
  await x.H.hcRender(x.H.sang()); x.goi.length = 0;
  let mo; x.S.cho = new Promise((r) => { mo = r; });
  const p = x.H.hcBam(x.nut(MA(1), "hoan-tac"));
  x.H.sang(); x.app.innerHTML = "<p>trang khác</p>"; // rời
  await x.H.hcRender(x.H.sang()); // quay lại #/hoc
  assert.equal(x.nut(MA(1), "hoan-tac").disabled, true, "đang gửi → nút trang mới khoá");
  x.goi.length = 0;
  mo(); await p;
  assert.deepEqual(x.goi, ["hoc/bao-cao"], "vẽ lại phiên hiện hành");
  assert.equal(x.nut(MA(1), "hoan-tac").disabled, false, "nút mở khoá sau khi POST xong");
  assert.match(x.toasts[0], /Đã hoàn tác/);
  // 401 (không vẽ lại, mở khoá) cũng mở khoá nút của trang mới
  const y = dungHc({ loi: loiSt(401) });
  await y.H.hcRender(y.H.sang());
  let mo2; y.S.cho = new Promise((r) => { mo2 = r; });
  const q = y.H.hcBam(y.nut(MA(1), "hoan-tac"));
  y.H.sang(); y.app.innerHTML = "<p>khác</p>";
  await y.H.hcRender(y.H.sang());
  mo2(); await q;
  assert.equal(y.nut(MA(1), "hoan-tac").disabled, false);
});

test("W2b-7 DOM: POST xong khi đang ở trang Hôm nay → chỉ vẽ lại khối 'Học hôm nay' (không đè trang); trang khác → không gọi gì", async () => {
  const x = dungHc();
  await x.H.hcRender(x.H.sang()); x.goi.length = 0;
  let mo; x.S.cho = new Promise((r) => { mo = r; });
  const p = x.H.hcBam(x.nut(MA(1), "hoan-tac"));
  const khoi = x.moHomNay();
  const trangHn = x.app.innerHTML;
  x.S.bc = BC({ thay_doi: [{ tu: "hieu_luc", den: "hoan_tac", ly_do: "nguoi_hoan_tac" }] });
  mo(); await p;
  assert.deepEqual(x.goi.filter((g) => !Array.isArray(g)), ["hoc/bao-cao"]);
  assert.match(khoi.outerHTML, /📈 Học hôm nay/);
  assert.match(khoi.outerHTML, /Đã hoàn tác 1 gợi ý/);
  assert.equal(x.app.innerHTML, trangHn, "không vẽ đè cả trang");
  // GET khối về muộn sau khi đã rời trang Hôm nay → không ghi
  const y = dungHc();
  await y.H.hcRender(y.H.sang()); y.goi.length = 0;
  let mo2; y.S.cho = new Promise((r) => { mo2 = r; });
  const q = y.H.hcBam(y.nut(MA(1), "hoan-tac"));
  const k2 = y.moHomNay();
  let moTai; y.S.choTai = new Promise((r) => { moTai = r; });
  mo2(); await new Promise((r) => setTimeout(r, 0));
  y.H.sang(); y.app.innerHTML = "<p>khác</p>";
  moTai(); await q;
  assert.equal(k2.outerHTML, '<section class="hn-khoi hn-hoc">CŨ</section>');
  assert.equal(y.app.innerHTML, "<p>khác</p>");
  // trang khác (không phải #/hoc, không phải Hôm nay) → không GET
  const z = dungHc();
  await z.H.hcRender(z.H.sang()); z.goi.length = 0;
  let mo3; z.S.cho = new Promise((r) => { mo3 = r; });
  const g = z.H.hcBam(z.nut(MA(1), "hoan-tac"));
  z.H.sang(); z.app.innerHTML = "<p>khác</p>";
  mo3(); await g;
  assert.deepEqual(z.goi.filter((v) => !Array.isArray(v)), []);
});

// ---------- HT-W3 (P2): báo cáo nói đúng bài nào thật sự vào phiếu (han_muc + vao_phieu từ HT-B4) ----------
const CAU_TAT = "Gợi ý học đang TẮT (cau_hinh.json: hoc_bat_ngay = 0) — không bài nào vào phiếu.";
const khoiDangDung = (h) => (h.match(/<section class="hn-khoi hc-hieu-luc">[\s\S]*?<\/section>/) || [""])[0];

test("W3 cầu dao: han_muc.bat_ngay === 0 → dòng TẮT cố định ở khối Học hôm nay và trang #/hoc; bat_ngay > 0 / vắng → không có", () => {
  const tat = BC({ han_muc: { bat_ngay: 0, hieu_luc_toi_da: 5 } });
  const k = F.hcKhoiHomNayHtml(tat, CHIEU);
  assert.ok(k.includes(esc(CAU_TAT)), k);
  assert.match(k, /data-hc-muc="(do|vang)">Gợi ý học đang TẮT/);
  const t = F.hcTrangHtml(tat, CHIEU, true);
  assert.ok(t.includes(esc(CAU_TAT)), "trang #/hoc");
  for (const hm of [{ bat_ngay: 1, hieu_luc_toi_da: 5 }, undefined, null, "x", { bat_ngay: "0" }, { bat_ngay: null }]) {
    const bc = hm === undefined ? BC() : BC({ han_muc: hm });
    assert.ok(!F.hcKhoiHomNayHtml(bc, CHIEU).includes("đang TẮT"), JSON.stringify(hm));
    assert.ok(!F.hcTrangHtml(bc, CHIEU, true).includes("đang TẮT"), JSON.stringify(hm));
  }
});

test("W3 vao_phieu: bài hieu_luc vao_phieu false → không 'Đang dùng'/'dùng tới hết', ghi 'Hiệu lực nhưng KHÔNG vào phiếu (vượt trần …)'; true giữ 'Đang dùng'", () => {
  const vuot = BH({ ma: MA(2), ten: "Bài vượt trần", vao_phieu: false });
  const vao = BH({ ma: MA(1), ten: "Bài vào phiếu", vao_phieu: true });
  const bc = BC({ han_muc: { bat_ngay: 2, hieu_luc_toi_da: 1 }, hieu_luc: [vao, vuot] });
  const h = F.hcTrangHtml(bc, CHIEU, true);
  // bài vượt trần không nằm trong khối "Đang dùng"
  const dd = khoiDangDung(h);
  assert.match(dd, /Đang dùng \(1\)/);
  assert.ok(dd.includes("Bài vào phiếu") && !dd.includes("Bài vượt trần"), dd);
  // bài vượt trần: câu đúng, không "Đang dùng" / "dùng tới hết"
  const b = F.hcBaiHtml(vuot, CHIEU, true, 3, bc.han_muc);
  assert.match(b, /Hiệu lực nhưng KHÔNG vào phiếu \(vượt trần hieu_luc_toi_da = 1\)/);
  assert.ok(!/Đang dùng|dùng tới hết/.test(b), b);
  assert.ok(h.includes("Hiệu lực nhưng KHÔNG vào phiếu (vượt trần hieu_luc_toi_da = 1)"));
  // bài vào phiếu giữ "Đang dùng" + "dùng tới hết"
  const a = F.hcBaiHtml(vao, CHIEU, true, 3, bc.han_muc);
  assert.match(a, /Đang dùng/);
  assert.match(a, /dùng tới hết 04\/12/);
  // cầu dao tắt: lý do là cầu dao, không nói "vượt trần"
  const c = F.hcBaiHtml(vuot, CHIEU, true, 3, { bat_ngay: 0, hieu_luc_toi_da: 5 });
  assert.match(c, /Hiệu lực nhưng KHÔNG vào phiếu \(gợi ý học đang tắt: hoc_bat_ngay = 0\)/);
  assert.ok(!/\(vượt trần|Đang dùng|dùng tới hết/.test(c), c);
  const hTat = F.hcTrangHtml(BC({ han_muc: { bat_ngay: 0, hieu_luc_toi_da: 5 }, hieu_luc: [vuot] }), CHIEU, true);
  assert.match(khoiDangDung(hTat), /Đang dùng \(0\)/);
  // trần không phải số nguyên → không vẽ số giả
  const r = F.hcBaiHtml(vuot, CHIEU, true, 3, { bat_ngay: 2, hieu_luc_toi_da: "<b>9</b>" });
  assert.match(r, /Hiệu lực nhưng KHÔNG vào phiếu/);
  assert.ok(!/<b>9|undefined|NaN/.test(r), r);
  // nút Hoàn tác vẫn theo cờ máy nhà
  assert.match(h, new RegExp(`data-hc-act="hoan-tac" data-hc-ma="${MA(2)}"`));
});

test("W3 runner bản cũ (không han_muc, không vao_phieu) → trang + khối giống hệt khi chưa có trường mới, không ném", () => {
  const bc = BC({ hieu_luc: [BH()] });
  const h = F.hcTrangHtml(bc, CHIEU, true);
  assert.match(khoiDangDung(h), /Đang dùng \(1\)/);
  assert.match(h, /dùng tới hết 04\/12/);
  assert.ok(!/KHÔNG vào phiếu|đang TẮT/.test(h));
  assert.equal(F.hcBaiHtml(BH(), CHIEU, true, 3), F.hcBaiHtml(BH(), CHIEU, true, 3, undefined));
  // vao_phieu không phải boolean → coi như vắng
  for (const v of ["false", 0, null]) assert.match(F.hcBaiHtml(BH({ vao_phieu: v }), CHIEU, true, 3, { bat_ngay: 1, hieu_luc_toi_da: 1 }), /Đang dùng/, String(v));
  for (const hm of [null, "x", [], { bat_ngay: BAN, hieu_luc_toi_da: BAN }]) {
    assert.doesNotThrow(() => F.hcTrangHtml(BC({ han_muc: hm, hieu_luc: [BH({ vao_phieu: false })] }), CHIEU, true));
    assert.doesNotThrow(() => F.hcKhoiHomNayHtml(BC({ han_muc: hm }), CHIEU));
  }
});

test("W3 escape: tên/gợi ý độc hại của bài không vào phiếu vẫn qua esc; han_muc rác không lọt HTML", () => {
  const bc = BC({ han_muc: { bat_ngay: 0, hieu_luc_toi_da: BAN }, hieu_luc: [BH({ ten: BAN, goi_y: BAN, vao_phieu: false }), BH({ ma: MA(3), ten: BAN, vao_phieu: true })] });
  const h = F.hcTrangHtml(bc, CHIEU, true);
  KHONG_LOT(h, "trang #/hoc W3");
  assert.ok(h.includes(esc(BAN)));
  const k = F.hcKhoiHomNayHtml(bc, CHIEU);
  KHONG_LOT(k, "khối Hôm nay W3");
  const b = F.hcTrangHtml(BC({ han_muc: { bat_ngay: 3, hieu_luc_toi_da: BAN }, hieu_luc: [BH({ ten: BAN, vao_phieu: false })] }), CHIEU, true);
  KHONG_LOT(b, "trần rác");
});
