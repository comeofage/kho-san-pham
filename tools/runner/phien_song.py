"""Phiên Claude SỐNG cho `taovideo` (docs/bo-chay-viec.md §7.2, §7.3, phiếu A-5).

Một tiến trình `claude -p --input-format stream-json --output-format stream-json`, stdin GIỮ MỞ suốt việc.
Khác `thuc_thi.chay_tien_trinh` (luôn đóng stdin ngay sau phiếu) nên có module riêng; dùng lại `_cach_mo`,
`_tao_job_rieng`, `giet_cay`, `_dong_handle` của thuc_thi (không sửa thuc_thi).

Luật ghi stdin (S-4 mục 1: tin ghi lúc agent đang làm KHÔNG được đọc trong lượt đó):
- `gui()` chỉ XẾP HÀNG (thread-safe, API gọi được). Luồng làn (trong `chay`) là nơi DUY NHẤT quyết định ghi; việc ghi
  thật do một luồng ghi riêng làm (pipe đầy cũng không chặn vòng chính).
- Mỗi nhịp (~NHIP_S): gọi `khi_nhip(tinh_trang, luc)` TRƯỚC, rồi mới ghi tối đa MỘT tin nếu agent rảnh: chưa ghi tin
  nào, hoặc tình trạng == ket_luot VÀ đã có result cấp cao MỚI kể từ tin ghi gần nhất (mỗi result tối đa một tin,
  §7.2). Như vậy bên gọi luôn thấy kết luận lượt trước khi tin đang chờ được ghi (§7.3).
- Tin trả lời mang mã câu hỏi (§7.6, FX-26): `dat_cau_hoi(ma, so_ket_luot)` ghi result sinh ra câu hỏi; lúc ghi mà
  so_ket_luot hiện tại khác (câu hỏi bị thay/rút) hoặc mã chưa đăng ký → BỎ tin + log, xét tin kế trong hàng.
- `dong()` / `giet()` chỉ đặt yêu cầu; vòng chính thực hiện ngay trong vòng lặp kế (sau callback đang chạy).

Thời gian truyền cho callback là `time.monotonic()`.
"""
from __future__ import annotations

import logging
import queue
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import psutil

from . import stream_json as sj
from . import thuc_thi as tt
from .theo_doi_phien import TheoDoiPhien, TinhTrang

log = logging.getLogger("kho_runner.phien_song")

NHIP_S = 1.0                    # chu kỳ gọi khi_nhip (test hạ xuống)
DUOI_STDERR_TOI_DA = 4000       # ký tự stderr cuối giữ lại (đã che) cho thông báo lỗi


@dataclass(frozen=True)
class CauHinhPhien:
    argv: list[str]
    cwd: str
    env: dict[str, str]
    file_log: Path
    file_jsonl: Path
    im_lang_s: float = 10.0
    cho_thoat_s: float = 90.0


@dataclass
class KetQuaPhien:
    ma_thoat: int | None
    ly_do_dung: str               # 'dong_stdin' | 'tu_thoat' | 'giet:<lý do>'
    khong_giet_duoc: bool
    pid: int | None
    pid_tao_luc: float | None
    duoi_stderr: str = ""         # MỞ RỘNG (ngoài chữ ký §13): ≤4000 ký tự stderr cuối, đã che


def _gio() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class PhienSong:
    def __init__(self, ch: CauHinhPhien, theo_doi: TheoDoiPhien, che: Callable[[str], str]):
        self.ch = ch
        self.td = theo_doi
        self.che = che
        self._khoa = threading.Lock()
        self._hang: deque[tuple[str, str | None]] = deque()
        self._cau_hoi: dict[str, int] = {}     # mã câu hỏi → so_ket_luot của result sinh ra câu hỏi
        self._ma_da_ghi: set[str] = set()       # mã câu hỏi mà tin trả lời của nó ĐÃ ghi vào stdin
        self._da_dong = False                 # đã yêu cầu đóng stdin (hoặc tiến trình đã kết thúc)
        self._ket_thuc = False
        self._ly_do_giet: str | None = None
        self._dang_chay = False

    # ------------------------------------------------------------ API thread-safe
    def gui(self, text: str, ma_cau_hoi: str | None = None) -> bool:
        """Xếp `text` vào hàng đợi stdin, gắn mã câu hỏi nếu là tin trả lời. False nếu phiên đã đóng/kết thúc."""
        if not isinstance(text, str):
            raise TypeError("gui cần str")
        if ma_cau_hoi is not None and not isinstance(ma_cau_hoi, str):
            raise TypeError("ma_cau_hoi cần str hoặc None")
        with self._khoa:
            if self._da_dong or self._ket_thuc or self._ly_do_giet is not None:
                return False
            self._hang.append((text, ma_cau_hoi))
            return True

    def dat_cau_hoi(self, ma_cau_hoi: str, so_ket_luot: int) -> None:
        """Gọi khi hành động 'hoi': câu `ma_cau_hoi` sinh ra ở result thứ `so_ket_luot`."""
        with self._khoa:
            self._cau_hoi[ma_cau_hoi] = int(so_ket_luot)

    def bo_hang_doi(self) -> int:
        """Huỷ các tin TRẢ LỜI chưa ghi (tin có mã câu hỏi; câu hỏi bị agent rút lại/thay, §7.3). Tin hệ thống
        (TIN_NHAC, TIN_TRAN_CODEX — không có mã) GIỮ nguyên (FX-27 P2-1). Trả số tin đã huỷ."""
        with self._khoa:
            giu = deque(x for x in self._hang if x[1] is None)
            n = len(self._hang) - len(giu)
            self._hang = giu
            return n

    def da_ghi_tra_loi(self, ma_cau_hoi: str) -> bool:
        """MỞ RỘNG (FX-27): tin trả lời mang mã này đã được ghi vào stdin chưa."""
        with self._khoa:
            return ma_cau_hoi in self._ma_da_ghi

    @property
    def so_tin_cho(self) -> int:
        """MỞ RỘNG: số tin đang chờ ghi."""
        with self._khoa:
            return len(self._hang)

    def dong(self) -> None:
        """Yêu cầu đóng stdin (kết thúc gọn). Tin còn trong hàng đợi bị bỏ."""
        with self._khoa:
            self._da_dong = True

    def giet(self, ly_do: str) -> None:
        """Yêu cầu giết cả cây (lý do đầu tiên được giữ)."""
        with self._khoa:
            if self._ly_do_giet is None:
                self._ly_do_giet = str(ly_do) or "không rõ"

    def con_song(self) -> bool:
        with self._khoa:
            return self._dang_chay and not (self._da_dong or self._ket_thuc or self._ly_do_giet is not None)

    # ------------------------------------------------------------ vòng chính (luồng làn)
    def chay(self, khi_bat_dau: Callable[[int, float], None],
             khi_su_kien: Callable[[dict, float, float], None],
             khi_nhip: Callable[[TinhTrang, float], None],
             huy: threading.Event) -> KetQuaPhien:
        """Sinh tiến trình, chặn tới khi nó kết thúc. Popen lỗi → ghi log, ném OSError. Callback ném lỗi → giết cả
        cây rồi ném lại (lỗi mang cờ không-giết-được của thuc_thi nếu gốc vẫn sống)."""
        ch = self.ch
        q: queue.Queue = queue.Queue()
        q_ghi: queue.Queue = queue.Queue()
        f_log = open(ch.file_log, "a", encoding="utf-8", newline="\n")
        f_jsonl = None
        proc: subprocess.Popen | None = None
        job = None
        tao_luc: float | None = None
        luong: list[threading.Thread] = []
        con_chau: dict[int, psutil.Process] = {}
        loi_chinh: BaseException | None = None
        khong_giet_duoc = False
        da_giet = False
        duoi_err: deque[str] = deque(maxlen=200)

        def ghi_log(s: str) -> None:
            f_log.write(s + "\n")
            f_log.flush()

        def giet_het(ly_do: str) -> None:
            ghi_log(f"[runner {_gio()}] giết cả cây pid {proc.pid}: {ly_do}")
            if job:
                if not tt._k32.TerminateJobObject(job, 1):
                    e = tt._loi_win("TerminateJobObject")
                    log.error("%s", e)
                    ghi_log(f"[runner] {e}")
            if not tt.giet_cay(proc.pid, tao_luc):
                ghi_log(f"[runner] giet_cay pid {proc.pid} không chắc đã giết hết (xem log runner)")
            for p in list(con_chau.values()):
                try:
                    if p.is_running():
                        p.kill()
                except psutil.NoSuchProcess:
                    pass
                except psutil.Error as e:
                    log.error("kill con cháu pid %s lỗi: %s", p.pid, e)
                    ghi_log(f"[runner] kill con cháu pid {p.pid} lỗi: {e}")

        def luong_ghi() -> None:
            try:
                while True:
                    b = q_ghi.get()
                    if b is None:
                        break
                    proc.stdin.write(b)
                    proc.stdin.flush()
            except (OSError, ValueError) as e:      # BrokenPipe: tiến trình đã thoát
                q.put(("runner", f"ghi stdin lỗi: {e}"))
            finally:
                try:
                    proc.stdin.close()
                except (OSError, ValueError) as e:
                    q.put(("runner", f"đóng stdin lỗi: {e}"))
                q.put(("runner", "đã đóng stdin"))

        try:
            f_jsonl = open(ch.file_jsonl, "a", encoding="utf-8", newline="\n")
            flags, si = tt._cach_mo(False)
            ghi_log(f"[runner {_gio()}] bắt đầu phiên sống: {Path(ch.argv[0]).name} (cwd {ch.cwd})")
            try:
                proc = subprocess.Popen(list(ch.argv), cwd=ch.cwd, env=ch.env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        creationflags=flags, startupinfo=si)
            except OSError as e:
                ghi_log(f"[runner {_gio()}] Không chạy được {ch.argv[0]}: {e}")
                raise
            job = tt._tao_job_rieng(proc)
            try:
                tao_luc = psutil.Process(proc.pid).create_time()
            except psutil.Error:
                tao_luc = time.time()
            for nguon, s in (("out", proc.stdout), ("err", proc.stderr)):
                t = threading.Thread(target=tt._luong_doc, args=(s, nguon, q), name=f"{nguon}-{proc.pid}",
                                     daemon=True)
                t.start()
                luong.append(t)
            t = threading.Thread(target=luong_ghi, name=f"stdin-{proc.pid}", daemon=True)
            t.start()
            luong.append(t)
            with self._khoa:
                self._dang_chay = True
            khi_bat_dau(proc.pid, tao_luc)

            cho_eof = {"out", "err"}
            da_gui_lan_nao = False
            so_ket_luot_khi_gui = -1
            stdin_da_dong = False
            han_thoat: float | None = None
            han_sau_giet: float | None = None
            lan_nhip = float("-inf")
            lan_chup = 0.0
            thoat_luc: float | None = None
            da_giet_giu_pipe = False
            ly_do_dung: str | None = None

            while True:
                try:
                    nguon, dong = q.get(timeout=0.05)
                except queue.Empty:
                    nguon, dong = None, None
                bay = time.monotonic()
                if nguon == "runner":
                    ghi_log(f"[runner {_gio()}] {dong}")
                elif nguon is not None and dong is None:
                    cho_eof.discard(nguon)
                elif nguon == "out":
                    sk = sj.doc_su_kien(dong)
                    if sk is None:
                        ghi_log(self.che(dong))
                    else:
                        f_jsonl.write(dong + "\n")
                        f_jsonl.flush()
                        nguoi_doc = sj.dich_dong(sk, self.che)
                        if nguoi_doc:
                            ghi_log(nguoi_doc)
                        d = self.td.nap(sk, bay)
                        if not da_giet:
                            khi_su_kien(sk, bay, d)
                elif nguon == "err":
                    s = self.che(dong)
                    ghi_log("[stderr] " + s)
                    duoi_err.append(s)

                dang_song = proc.poll() is None
                if not da_giet:
                    if huy.is_set():
                        self.giet("bị huỷ")
                    if dang_song and bay - lan_nhip >= NHIP_S:
                        lan_nhip = bay
                        tinh = self.td.tinh_trang(bay, ch.im_lang_s)
                        khi_nhip(tinh, bay)
                        with self._khoa:
                            ly_giet, xin_dong = self._ly_do_giet, self._da_dong
                            ranh = (not da_gui_lan_nao) or (tinh.loai == "ket_luot"
                                                             and tinh.so_ket_luot > so_ket_luot_khi_gui)
                            tin = None
                            bo: list[str] = []
                            while ranh and self._hang and not xin_dong and ly_giet is None and not stdin_da_dong:
                                text, ma = self._hang.popleft()
                                if ma is not None and self._cau_hoi.get(ma) != tinh.so_ket_luot:
                                    bo.append(ma)              # câu hỏi đã đổi (có result mới) → không trả nhầm
                                    continue
                                tin = text
                                if ma is not None:
                                    self._ma_da_ghi.add(ma)
                                break
                        for ma in bo:
                            ghi_log(f"[runner {_gio()}] bỏ câu trả lời cho câu hỏi {ma} — câu hỏi đã đổi")
                        if tin is not None:
                            q_ghi.put(sj.tin_user(tin))
                            da_gui_lan_nao = True
                            so_ket_luot_khi_gui = tinh.so_ket_luot
                            ghi_log(f"[runner {_gio()}] gửi tin vào stdin ({len(tin)} ký tự)")
                    with self._khoa:
                        ly_giet, xin_dong = self._ly_do_giet, self._da_dong
                        if xin_dong:
                            self._hang.clear()
                    if ly_giet is not None and dang_song:
                        da_giet = True
                        ly_do_dung = "giet:" + ly_giet
                        giet_het(ly_giet)
                        han_sau_giet = time.monotonic() + tt.CHO_SAU_GIET_S
                        dang_song = proc.poll() is None
                    elif xin_dong and not stdin_da_dong:
                        stdin_da_dong = True
                        q_ghi.put(None)
                        han_thoat = bay + ch.cho_thoat_s
                        ghi_log(f"[runner {_gio()}] đóng stdin — chờ thoát ≤ {ch.cho_thoat_s:g} s")
                    elif stdin_da_dong and dang_song and han_thoat is not None and bay >= han_thoat:
                        self.giet(f"không thoát sau {ch.cho_thoat_s:g} s kể từ khi đóng stdin")
                elif dang_song and han_sau_giet is not None and bay >= han_sau_giet:
                    khong_giet_duoc = True
                    ghi_log(f"[runner {_gio()}] KHÔNG giết được pid {proc.pid} sau {tt.CHO_SAU_GIET_S} s — bỏ "
                            "chờ, tiến trình có thể còn chạy (kiểm tay trên máy)")
                    log.error("pid %s vẫn sống %s s sau khi giết — bỏ chờ", proc.pid, tt.CHO_SAU_GIET_S)
                    break

                if dang_song and bay - lan_chup >= tt.CHU_KY_CHUP_CON_S:
                    lan_chup = bay
                    try:
                        for c in psutil.Process(proc.pid).children(recursive=True):
                            con_chau.setdefault(c.pid, c)
                    except psutil.Error:
                        pass

                if not dang_song:
                    if ly_do_dung is None:
                        ly_do_dung = "dong_stdin" if stdin_da_dong else "tu_thoat"
                    if not cho_eof:
                        break
                    if thoat_luc is None:
                        thoat_luc = bay
                    elif bay - thoat_luc > tt.CHO_EOF_S:
                        if not da_giet_giu_pipe:
                            da_giet_giu_pipe = True
                            thoat_luc = bay
                            giet_het("tiến trình gốc đã thoát nhưng con cháu còn giữ pipe")
                        else:
                            ghi_log(f"[runner {_gio()}] pipe vẫn chưa đóng sau khi giết con cháu — bỏ đọc")
                            break

            ma_thoat = proc.poll() if khong_giet_duoc else proc.wait(timeout=tt.CHO_DON_S)
            ghi_log(f"[runner {_gio()}] phiên sống kết thúc: mã {ma_thoat} · {ly_do_dung}"
                    + (" · KHÔNG giết được" if khong_giet_duoc else ""))
            return KetQuaPhien(ma_thoat=ma_thoat, ly_do_dung=ly_do_dung or "tu_thoat",
                               khong_giet_duoc=khong_giet_duoc, pid=proc.pid, pid_tao_luc=tao_luc,
                               duoi_stderr="\n".join(duoi_err)[-DUOI_STDERR_TOI_DA:])
        except BaseException as e:
            loi_chinh = e
            raise
        finally:
            with self._khoa:
                self._ket_thuc = True
                self._dang_chay = False
                self._hang.clear()
            loi_don: list[BaseException] = []

            def buoc(ten: str, f) -> None:
                try:
                    f()
                except Exception as e:  # noqa: BLE001 — ghi lại, chạy tiếp các bước dọn còn lại
                    log.error("Dọn %s lỗi: %s", ten, e, exc_info=True)
                    loi_don.append(e)
                    try:
                        if not f_log.closed:
                            ghi_log(f"[runner {_gio()}] dọn {ten} lỗi: {e}")
                    except Exception:  # noqa: BLE001
                        pass

            q_ghi.put(None)                              # luồng ghi luôn thoát
            if proc is not None and proc.poll() is None and not khong_giet_duoc:
                buoc("tiến trình còn sống", lambda: giet_het(f"dọn sau lỗi: {loi_chinh!r}"))
                buoc("chờ tiến trình", lambda: proc.wait(timeout=tt.CHO_DON_S))
                if proc.poll() is None:
                    buoc("ghi log không giết được", lambda: ghi_log(
                        f"[runner {_gio()}] KHÔNG giết được pid {proc.pid} khi dọn sau lỗi — kiểm tay trên máy"))
                    log.error("pid %s vẫn sống sau khi giết + chờ (dọn phiên sống)", proc.pid)
                    if loi_chinh is not None:
                        try:
                            setattr(loi_chinh, tt.THUOC_TINH_KHONG_GIET, (proc.pid, tao_luc))
                        except (AttributeError, TypeError) as e:
                            log.error("không gắn được cờ không-giết-được lên lỗi %r: %s", loi_chinh, e)
            if job:
                buoc("handle Job Object riêng", lambda: tt._dong_handle(job))
            for t in luong:
                t.join(timeout=2)
                if t.is_alive():
                    log.error("Luồng %s vẫn kẹt sau khi dọn (pipe bị giữ)", t.name)
            if proc is not None:
                for ten, tien_to, s in (("stdout", "out-", proc.stdout), ("stderr", "err-", proc.stderr)):
                    if s is not None and not any(t.is_alive() and t.name.startswith(tien_to) for t in luong):
                        buoc(ten, s.close)
            if f_jsonl is not None:
                buoc("file jsonl", f_jsonl.close)
            buoc("file log", f_log.close)
            if loi_don and loi_chinh is None:
                raise loi_don[0]
