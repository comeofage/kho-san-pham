// W-1b — Test chéo chữ ký Worker với vector do Python sinh (tools/runner/vector_ky.json, §8.3).
// Chạy: node --test cf/test/chu-ky-cheo.test.mjs   (Node 24: phải chỉ đường dẫn file, không chỉ thư mục)
// Khoá trong vector là KHOÁ TEST seed công khai — chỉ dùng ở đây.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { chuoiKyRequest, kyRequest } from "../src/worker.js";

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

// Đợt 4: Worker CHƯA có hàm ký lời duyệt (kho-duyet-v1). Khi W-4 thêm hàm, bổ sung test khớp VECTOR.duyet.
test.todo("ký duyệt khớp vector duyet[] — Worker chưa có hàm ký duyệt (đợt 4)");
