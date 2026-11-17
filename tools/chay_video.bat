@echo off
rem Bật server phát video + tunnel cho nút "Tải video kế tiếp" trên web kho.
cd /d "%~dp0"
start "kho-video-server" python video_server.py
rem Bộ chạy việc: chạy BẢN CÀI (python tools/cai_runner.py), không chạy code trong repo. Đã chạy thì tự thoát mã 3.
start "kho-runner" /min python "E:\kho-runner\app\chay_runner.py"
"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --config "%~dp0tunnel.yml" run kho-video
