// W-1b — Test chéo chữ ký Worker với vector do Python sinh (tools/runner/vector_ky.json, §8.3).
// Chạy: node --test cf/test/chu-ky-cheo.test.mjs   (Node 24: phải chỉ đường dẫn file, không chỉ thư mục)
// Khoá trong vector là KHOÁ TEST seed công khai — chỉ dùng ở đây.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import worker, { chuoiKyRequest, kyRequest, chuoiKyDuyet, kyDuyet, chuoiTieuDuyet, kyTieuDuyet } from "../src/worker.js";

const VECTOR = JSON.parse(readFileSync(new URL("../../tools/runner/vector_ky.json", import.meta.url), "utf8"));
const KY_RIENG_TEST = VECTOR.khoa_rieng_test_pkcs8_der_b64;
const hex = (u8) => Buffer.from(u8).toString("hex");
const sha256Hex = (text) => createHash("sha256").update(Buffer.from(text, "utf8")).digest("hex");

test("vector có đủ ca request và đúng phiên bản", () => {
  assert.equal(VECTOR.phien_ban, 1);
  assert.ok(Array.isArray(VECTOR.request) && VECTOR.request.length >= 1);
});

for (const [i, v] of VECTOR.request.entries()) {
  test(`chuoiKyRequest khớp byte vector request[${i}] ${v.path}`, () => {
    // sha256 của body (UTF-8) phải khớp vector trước — đây là đầu vào của chuỗi ký.
    assert.equal(sha256Hex(v.body_utf8), v.body_sha256_hex);
    const out = chuoiKyRequest(v.method, v.path, v.ngay_ms, v.nonce, v.body_sha256_hex);
    assert.ok(out instanceof Uint8Array);
    assert.equal(hex(out), v.chuoi_ky_hex);
    assert.equal(new TextDecoder().decode(out), v.chuoi_ky_utf8);
  });

  test(`kyRequest với khoá test cho đúng header + chữ ký vector request[${i}]`, async (t) => {
    // Cố định thời điểm và nonce để kyRequest tất định (Ed25519 tất định → chữ ký phải khớp byte).
    t.mock.method(Date, "now", () => v.ngay_ms);
    const nonceBytes = Buffer.from(v.nonce, "hex");
    t.mock.method(globalThis.crypto, "getRandomValues", (arr) => {
      assert.equal(arr.length, nonceBytes.length);
      arr.set(nonceBytes);
      return arr;
    });
    const h = await kyRequest({ KY_RIENG: KY_RIENG_TEST }, v.method, v.path, v.body_utf8);
    assert.deepEqual(Object.keys(h).sort(), ["x-ky", "x-ky-ngay", "x-ky-nonce"]);
    assert.equal(h["x-ky-ngay"], String(v.ngay_ms));
    assert.equal(h["x-ky-nonce"], v.nonce);
    assert.match(h["x-ky"], /^[A-Za-z0-9_-]{86}$/); // base64url không padding
    assert.equal(h["x-ky"], v.x_ky);
  });
}

test("kyRequest: chữ ký thật kiểm được bằng khoá công khai trong vector", async (t) => {
  const v = VECTOR.request[0];
  t.mock.method(Date, "now", () => v.ngay_ms);
  const h = await kyRequest({ KY_RIENG: KY_RIENG_TEST }, v.method, v.path, v.body_utf8);
  const pub = await crypto.subtle.importKey("raw", Buffer.from(VECTOR.khoa_cong_khai_raw_hex, "hex"), { name: "Ed25519" }, false, ["verify"]);
  const sig = Buffer.from(h["x-ky"], "base64url");
  const msg = chuoiKyRequest(v.method, v.path, Number(h["x-ky-ngay"]), h["x-ky-nonce"], v.body_sha256_hex);
  assert.equal(await crypto.subtle.verify({ name: "Ed25519" }, pub, sig, msg), true);
});

// Đợt 4 (W-4): ký lời duyệt kho-duyet-v1 phải khớp từng byte vector Python.
test("vector có ít nhất một ca duyet", () => {
  assert.ok(Array.isArray(VECTOR.duyet) && VECTOR.duyet.length >= 1);
});

for (const [i, v] of VECTOR.duyet.entries()) {
  test(`chuoiKyDuyet khớp byte vector duyet[${i}] ${v.loai}`, async () => {
    // tham_so_chuan dùng NGUYÊN CHUỖI của vector (không stringify lại).
    assert.equal(sha256Hex(v.tham_so_chuan), v.tham_so_chuan_sha256_hex);
    assert.equal(sha256Hex(v.loi_duyet), v.loi_duyet_sha256_hex);
    const out = await chuoiKyDuyet(v.id, v.loai, v.tham_so_chuan, v.loi_duyet, v.duyet_luc, v.boi);
    assert.ok(out instanceof Uint8Array);
    assert.equal(hex(out), v.chuoi_ky_hex);
    assert.equal(new TextDecoder().decode(out), v.chuoi_ky_utf8);
  });

  test(`kyDuyet với khoá test cho đúng chu_ky_duyet vector duyet[${i}]`, async () => {
    const ky = await kyDuyet({ KY_RIENG: KY_RIENG_TEST }, v.id, v.loai, v.tham_so_chuan, v.loi_duyet, v.duyet_luc, v.boi);
    assert.match(ky, /^[A-Za-z0-9_-]{86}$/);
    assert.equal(ky, v.chu_ky_duyet);
    const pub = await crypto.subtle.importKey("raw", Buffer.from(VECTOR.khoa_cong_khai_raw_hex, "hex"), { name: "Ed25519" }, false, ["verify"]);
    assert.equal(await crypto.subtle.verify({ name: "Ed25519" }, pub, Buffer.from(ky, "base64url"), Buffer.from(v.chuoi_ky_hex, "hex")), true);
  });
}

// D9 (FX-9): ký xác nhận tiêu lời duyệt kho-tieu-v1 phải khớp từng byte vector Python (mục tieu[]).
// Vector do phiếu backend thêm song song; chưa có thì để todo — KHÔNG tự sinh/sửa vector ở đây.
// Tên trường theo khuôn duyet[]: id, chu_ky_duyet, nonce, chu_ky_duyet_sha256_hex, chuoi_ky_hex, chuoi_ky_utf8, ky.
if (!Array.isArray(VECTOR.tieu) || VECTOR.tieu.length === 0) {
  test.todo("vector tieu[] chưa có trong tools/runner/vector_ky.json — chờ phiếu backend thêm rồi chạy lại");
} else {
  for (const [i, v] of VECTOR.tieu.entries()) {
    test(`chuoiTieuDuyet khớp byte vector tieu[${i}]`, async () => {
      if (v.chu_ky_duyet_sha256_hex !== undefined) assert.equal(sha256Hex(v.chu_ky_duyet), v.chu_ky_duyet_sha256_hex);
      const out = await chuoiTieuDuyet(v.id, v.chu_ky_duyet, v.nonce);
      assert.ok(out instanceof Uint8Array);
      assert.equal(hex(out), v.chuoi_tieu_hex);
      if (v.chuoi_tieu_utf8 !== undefined) assert.equal(new TextDecoder().decode(out), v.chuoi_tieu_utf8);
    });

    test(`kyTieuDuyet với khoá test cho đúng ky vector tieu[${i}]`, async () => {
      const ky = await kyTieuDuyet({ KY_RIENG: KY_RIENG_TEST }, v.id, v.chu_ky_duyet, v.nonce);
      assert.match(ky, /^[A-Za-z0-9_-]{86}$/);
      assert.equal(ky, v.ky);
      const pub = await crypto.subtle.importKey("raw", Buffer.from(VECTOR.khoa_cong_khai_raw_hex, "hex"), { name: "Ed25519" }, false, ["verify"]);
      assert.equal(await crypto.subtle.verify({ name: "Ed25519" }, pub, Buffer.from(ky, "base64url"), Buffer.from(v.chuoi_tieu_hex, "hex")), true);
    });
  }
}

// Không phụ thuộc vector: chữ ký tiêu duyệt bằng khoá test kiểm được bằng khoá công khai Python công bố.
test("kyTieuDuyet: chữ ký với khoá test kiểm được bằng khoa_cong_khai_raw_hex", async () => {
  const id = "j20261117150000ab12", ck = VECTOR.duyet[0].chu_ky_duyet, nonce = "0123456789abcdef0123456789abcdef";
  const ky = await kyTieuDuyet({ KY_RIENG: KY_RIENG_TEST }, id, ck, nonce);
  const msg = await chuoiTieuDuyet(id, ck, nonce);
  assert.equal(new TextDecoder().decode(msg), `kho-tieu-v1\n${id}\n${sha256Hex(ck)}\n${nonce}`);
  const pub = await crypto.subtle.importKey("raw", Buffer.from(VECTOR.khoa_cong_khai_raw_hex, "hex"), { name: "Ed25519" }, false, ["verify"]);
  assert.equal(await crypto.subtle.verify({ name: "Ed25519" }, pub, Buffer.from(ky, "base64url"), msg), true);
});

// FX-17 P1-1: chu_ky_duyet do Python/Worker sinh luôn ở dạng base64url chuẩn → route tieu-duyet nhận (200);
// 15 biến thể bit thừa ở ký tự cuối (cùng 64 byte) → 400; khoá KV = "tieu:" + sha256hex(64 byte).
test("tieu-duyet nhận chu_ky_duyet chuẩn của vector, từ chối biến thể không chuẩn", async () => {
  const BANG = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
  // tieu[] có cả chuỗi thử không phải chữ ký (chỉ để khớp byte) → chỉ lấy chuỗi đúng hình dạng 86 ký tự base64url.
  const ds = [...VECTOR.duyet.map((v) => v.chu_ky_duyet), ...(Array.isArray(VECTOR.tieu) ? VECTOR.tieu.map((v) => v.chu_ky_duyet) : [])]
    .filter((s) => /^[A-Za-z0-9_-]{86}$/.test(s));
  assert.ok(ds.length >= 1);
  for (const ck of new Set(ds)) {
    const kho = new Map();
    const env = {
      RUNNER_KEY: "rk", KY_RIENG: KY_RIENG_TEST,
      SO_DUYET: { async get(k) { return kho.has(k) ? kho.get(k) : null; }, async put(k, v) { kho.set(k, v); } },
    };
    const goi = (chu_ky_duyet) => worker.fetch(new Request("https://kho.test/api/runner/tieu-duyet", {
      method: "POST", headers: { "content-type": "application/json", "x-runner-key": "rk" },
      body: JSON.stringify({ id: "j20261117150000ab12", chu_ky_duyet, nonce: "0123456789abcdef0123456789abcdef" }),
    }), env, { waitUntil() {} });
    const byte = Buffer.from(ck, "base64url");
    assert.equal(byte.length, 64);
    assert.equal(byte.toString("base64url"), ck, "vector phải ở dạng chuẩn");
    const goc = BANG.indexOf(ck[85]) & ~15;
    for (let i = 0; i < 16; i++) {
      const bt = ck.slice(0, 85) + BANG[goc + i];
      if (bt !== ck) assert.equal((await goi(bt)).status, 400, bt);
    }
    assert.equal(kho.size, 0);
    assert.equal((await goi(ck)).status, 200);
    assert.deepEqual([...kho.keys()], [`tieu:${createHash("sha256").update(byte).digest("hex")}`]);
    assert.equal((await goi(ck)).status, 409);
  }
});
