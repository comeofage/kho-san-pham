# Thư viện tự host (web/vendor/)

Nguồn: tarball npm đúng phiên bản, tải bằng
`npm pack marked@12.0.2 dompurify@3.4.18 qrcode-generator@1.4.4` trong thư mục tạm,
chép nguyên file (không sửa nội dung). Hợp đồng: `docs/bo-chay-viec.md` §9 mục 1.

| Gói | Phiên bản | File trong tarball | File trong web/vendor/ | sha256 |
|---|---|---|---|---|
| marked | 12.0.2 | `package/marked.min.js` | `marked-12.0.2.min.js` | 15fabce5b65898b32b03f5ed25e9f891a729ad4c0d6d877110a7744aa847a894 |
| dompurify | 3.4.18 | `package/dist/purify.min.js` | `purify-3.4.18.min.js` | 8053ee2a6a09f9d50f7fcd6fb7f07072f52c7f3fa9aa12147cab4feaf65ee970 |
| qrcode-generator | 1.4.4 | `package/qrcode.js` (gói npm không có bản .min) | `qrcode-generator-1.4.4.js` | 18ae399f81182bc9de916e9c77b195df20cc58d6f2d55a62b085a299f1bf1780 |

Kiểm lại: `sha256sum web/vendor/*.js` phải khớp cột sha256.
Nâng phiên bản = tải lại theo cách trên, đổi tên file, cập nhật bảng này và `web/index.html`.
