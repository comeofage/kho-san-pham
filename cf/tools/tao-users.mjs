// Sinh JSON cho secret USERS (mật khẩu đã băm PBKDF2, không lưu mật khẩu thật).
// Dùng: node tools/tao-users.mjs "nhan:<mật khẩu>:Nhân" "thu:<mật khẩu>:Thu" | npx wrangler secret put USERS
// Mỗi tham số = tên_đăng_nhập:mật_khẩu:Tên hiển thị (tên hiển thị được ghi vào "ai gạt đã quay").
import { bamMatKhau } from "../src/worker.js";

const args = process.argv.slice(2);
if (!args.length) {
  console.error('Dùng: node tools/tao-users.mjs "user:pass:Tên hiển thị" ...');
  process.exit(1);
}
const out = {};
for (const a of args) {
  const [user, pass, ...ten] = a.split(":");
  if (!user || !pass) { console.error(`Sai dạng: ${a}`); process.exit(1); }
  out[user.trim().toLowerCase()] = { ten: ten.join(":") || user, hash: await bamMatKhau(pass) };
}
process.stdout.write(JSON.stringify(out));
