#!/usr/bin/env bash
# Kiểm chứng tối thiểu trước khi báo xong việc — xem AGENTS.md.
# Chỉ đứng tên cho lệnh gốc của Phòng Kỹ sư Culiapp (đã có từ trước, đừng trùng lặp logic ở đây).
set -euo pipefail
cd "$(dirname "$0")"
python .culiapp/kiem-chung.py
