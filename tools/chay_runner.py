"""Điểm vào bộ chạy việc (docs/bo-chay-viec.md §4.1). Chạy từ BẢN CÀI:
    python "E:\\kho-runner\\app\\chay_runner.py"      (hoặc <KHO_RUNNER_DIR>\\app\\chay_runner.py)

Thứ tự trong main() (bước 1 trước MỌI việc đụng job/tiến trình/DB):
  1. giành khoá đơn instance (named mutex + msvcrt.locking runner.lock) — không được → in "Bộ chạy việc đã chạy", mã 3;
     ngay sau đó (khi có HTTP) kiểm ky_cong_khai.pem và đọc/sinh .runner_key — thiếu hoặc hỏng → mã 6, chưa đụng
     DB/việc nào;
  2. tự gắn Job Object (KILL_ON_JOB_CLOSE) — thất bại → cảnh báo trên /suc-khoe;
  3. mở DB, dọn mồ côi, đối soát (BoChay.khoi_dong);
  4. bind 127.0.0.1:<cổng> (thất bại → mã 5);
  5. bật 2 làn.
Trước bước 1 chỉ có phân tích tham số dòng lệnh (không I/O) để `--help` chạy được cả khi runner đang chạy.

Mã thoát: 0 tắt bình thường · 3 đã có instance · 5 không mở được HTTP (bind lỗi / thiếu api.py) · 6 thiếu hoặc hỏng
khoá công khai hoặc khoá runner (.runner_key).
"""
from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import secrets
import sys
import threading
from pathlib import Path

THU_MUC_APP = Path(__file__).resolve().parent
if str(THU_MUC_APP) not in sys.path:
    sys.path.insert(0, str(THU_MUC_APP))

CONG_MAC_DINH = 8788
log = logging.getLogger("kho_runner")


def _phan_tich(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="chay_runner.py",
        description="Bộ chạy việc cho web Kho sản phẩm: 2 làn (gpu/nhe), HTTP 127.0.0.1. "
                    "Thư mục dữ liệu: KHO_RUNNER_DIR hoặc E:\\kho-runner.")
    ap.add_argument("--cong", type=int, default=CONG_MAC_DINH, help=f"cổng HTTP (mặc định {CONG_MAC_DINH})")
    ap.add_argument("--khong-http", action="store_true",
                    help="không mở HTTP (chỉ chạy làn; dùng để thử/chẩn đoán, web không gọi được)")
    return ap.parse_args(argv)


def _cai_log(thu_muc: Path) -> None:
    goc = logging.getLogger()
    goc.setLevel(logging.INFO)
    dang = logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s")
    try:
        fh = logging.handlers.RotatingFileHandler(thu_muc / "runner.log", maxBytes=2_000_000, backupCount=5,
                                                  encoding="utf-8")
        fh.setFormatter(dang)
        goc.addHandler(fh)
    except OSError as e:
        print(f"[CẢNH BÁO] không mở được runner.log: {e}", file=sys.stderr)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(dang)
    goc.addHandler(sh)


def doc_hoac_tao_khoa_runner(thu_muc: Path) -> str:
    """`.runner_key` (tự sinh lần đầu, §4.1). File có mà rỗng/ngắn → lỗi, KHÔNG tự ghi đè."""
    p = thu_muc / ".runner_key"
    try:
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0))
    except FileExistsError:
        k = p.read_text(encoding="utf-8").strip()
        if len(k) < 32:
            raise RuntimeError(f"{p} có nhưng khoá quá ngắn — kiểm tay (không tự ghi đè)") from None
        return k
    k = secrets.token_hex(32)
    try:
        os.write(fd, k.encode("ascii"))
    finally:
        os.close(fd)
    log.info("đã sinh khoá runner mới ở %s — đặt lại secret RUNNER_KEY của Worker", p)
    return k


def _doc_cau_hinh(thu_muc: Path) -> tuple[dict, list[str]]:
    from runner.han_muc import han_muc_hieu_luc
    p = thu_muc / "cau_hinh.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        d = {}
    except (OSError, ValueError) as e:
        hm, cb = han_muc_hieu_luc({})
        return hm, [f"cau_hinh.json hỏng ({e}) — dùng trần trong code"] + cb
    return han_muc_hieu_luc(d)


def _khoa_cong_khai():
    """§8.3: bản cài → app\\ky_cong_khai.pem; chạy từ repo → tools\\runner\\ky_cong_khai.pem."""
    from runner import chu_ky
    for p in (THU_MUC_APP / "ky_cong_khai.pem", THU_MUC_APP / "runner" / "ky_cong_khai.pem"):
        if p.is_file():
            return chu_ky.nap_khoa_cong_khai(p.read_bytes()), p
    return None, None


def main(argv: list[str] | None = None) -> int:
    ts = _phan_tich(argv)

    # ---- BƯỚC 1: khoá đơn instance, trước mọi việc đụng DB/job/tiến trình (P1-1) ----
    from runner import thuc_thi as tt
    from runner.vong_lap import ten_mutex, thu_muc_runner
    thu_muc = thu_muc_runner()
    khoa = tt.gianh_don_instance(thu_muc, ten_mutex(thu_muc))
    if khoa is None:
        print("Bộ chạy việc đã chạy", flush=True)
        return 3

    srv = None
    bo = None
    try:
        _cai_log(thu_muc)
        log.info("bắt đầu runner pid %s, dữ liệu %s, mã %s", os.getpid(), thu_muc, THU_MUC_APP)

        # ---- kiểm khoá công khai TRƯỚC khi đụng DB/đối soát (R-05 P3-8): thiếu → thoát, không giết/đổi việc nào ----
        kcc = nguon_pem = None
        khoa_runner = None
        if not ts.khong_http:
            try:
                kcc, nguon_pem = _khoa_cong_khai()
            except Exception as e:  # noqa: BLE001 — R-06 P3-4: pem hỏng → mã 6, không traceback mã 1
                log.error("ky_cong_khai.pem hỏng, không nạp được (%s: %s) — không mở HTTP, thoát",
                          type(e).__name__, e)
                return 6
            if kcc is None:
                log.error("thiếu ky_cong_khai.pem (bản cài hoặc tools/runner) — không mở HTTP, thoát")
                return 6
            # R-07 P3-7: đọc/sinh .runner_key cũng TRƯỚC khoi_dong — lỗi ở đây không được để việc đã bị đổi
            try:
                khoa_runner = doc_hoac_tao_khoa_runner(thu_muc)
            except (OSError, RuntimeError, ValueError) as e:      # UnicodeDecodeError là ValueError
                log.error("không đọc/sinh được khoá runner .runner_key (%s: %s) — không mở HTTP, thoát",
                          type(e).__name__, e)
                return 6

        # ---- BƯỚC 2: Job Object ----
        canh_bao_khoi: list[str] = []
        if not tt.tu_gan_job_object():
            c = "Không gắn được Job Object — tiến trình con có thể mồ côi khi runner chết"
            log.error(c)
            canh_bao_khoi.append(c)                 # R-05 P2-3: hiện trên /suc-khoe (api đọc list canh_bao)

        # ---- BƯỚC 3: DB, dọn mồ côi, đối soát ----
        from runner.kho_viec import KhoViec
        from runner.vong_lap import BoChay, kiem_tong, tao_moi_truong
        mt = tao_moi_truong()
        hm, canh_bao = _doc_cau_hinh(thu_muc)
        canh_bao = canh_bao_khoi + list(canh_bao) + kiem_tong(THU_MUC_APP)
        for c in canh_bao:
            log.warning("cảnh báo: %s", c)
        kho = KhoViec(thu_muc / "runner.db", mt.bay_gio)
        che = tt.bo_che(tt.NguonBiMat(
            settings_json=Path.home() / ".claude" / "settings.json",
            file_khoa=[mt.repo_kho / "tools" / ".video_key", thu_muc / ".runner_key"],
            cau_hinh_radar=Path(mt.thu_muc_radar) / "cau-hinh.json",
            ten_bien_moi_truong=["GENMAX_API_KEY"]))
        bo = BoChay(kho, mt, hm, thu_muc / "log", che, canh_bao=canh_bao)   # R-06 P3-5: cùng list với /suc-khoe
        kq = bo.khoi_dong()
        log.info("khởi động lại: %s", json.dumps(kq, ensure_ascii=False))
        if kq.get("con_song"):
            c = (f"Khởi động lại: tiến trình cũ còn sống (pid {', '.join(map(str, kq['con_song']))}) — việc của "
                 "chúng đã chuyển loi, kiểm tay trên máy")
            log.error(c)
            canh_bao.append(c)

        # ---- BƯỚC 4: HTTP ----
        if not ts.khong_http:
            try:
                from runner import api
            except ImportError as e:
                log.error("không nạp được runner/api.py: %s", e)
                return 5
            from http.server import ThreadingHTTPServer
            handler = api.tao_handler(kho, mt, khoa_runner, kcc, hm, canh_bao,
                                      bo.bao_huy, bo.doc_log, bo.trang_thai_lan, che=che)
            try:
                srv = ThreadingHTTPServer(("127.0.0.1", ts.cong), handler)
            except OSError as e:
                log.error("không bind được 127.0.0.1:%s: %s", ts.cong, e)
                return 5
            srv.daemon_threads = True
            log.info("HTTP nghe 127.0.0.1:%s (khoá công khai %s)", ts.cong, nguon_pem)

        # ---- BƯỚC 5: 2 làn ----
        bo.bat_lan()
        log.info("đã bật 2 làn")
        if srv is not None:
            srv.serve_forever(poll_interval=0.5)
        else:
            cho = threading.Event()
            while not cho.wait(1.0):
                pass
        return 0
    except KeyboardInterrupt:
        log.info("nhận Ctrl+C — tắt runner")
        return 0
    finally:
        if bo is not None:
            try:
                bo.dung()
            except Exception:  # noqa: BLE001 — vẫn phải nhả khoá bên dưới
                log.exception("lỗi khi dừng làn")
        if srv is not None:
            try:
                srv.server_close()
            except OSError as e:
                log.error("lỗi đóng HTTP: %s", e)
        try:
            khoa.nha()                      # luôn nhả, lỗi được ghi (không nuốt im)
        except OSError as e:
            log.error("lỗi nhả khoá đơn instance: %s", e)
            print(f"[LỖI] nhả khoá đơn instance: {e}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
