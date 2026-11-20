"""Kiểu dữ liệu và ngoại lệ dùng chung của bộ chạy việc (docs/bo-chay-viec.md §13 B-1)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

TRANG_THAI = ("cho", "dang_chay", "can_tra_loi", "cho_duyet", "xong", "loi", "huy")
DANG_MO = ("cho", "dang_chay", "can_tra_loi", "cho_duyet")
LAN_CHAY = ("gpu", "nhe")
LOAI_CAU_HOI = ("viec_tay", "chon", "khong_ro", "cau_hoi")

# Kết quả đối soát đầu ra (kiem_dau_ra). "xong_lo_ngai" = đầu ra chính đã có nhưng thiếu phần phụ
# (vd phan_tich_uid xong mà chưa có douyin.md, §5.1 P2-4) → job `xong` + `co_lo_ngai`.
DAU_RA = ("xong", "xong_lo_ngai", "chua", "khong_ro")

MUI_GIO_VN = timezone(timedelta(hours=7))


def gio_vn(dt: datetime) -> datetime:
    """Đưa về giờ VN có múi giờ. Datetime không múi giờ được coi là giờ VN sẵn."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=MUI_GIO_VN)
    return dt.astimezone(MUI_GIO_VN)


class ThamSoLoi(ValueError):
    """Tham số / loại việc / giá trị trả lời không hợp lệ (API trả 400)."""


class TrungViec(Exception):
    """Đã có việc đang mở cùng (loai, khoa) — API trả 409 kèm việc đó."""

    def __init__(self, viec: dict):
        super().__init__(f"trùng việc đang mở {viec.get('id')}")
        self.viec = viec


class SaiTrangThai(Exception):
    """Chuyển trạng thái CAS thất bại (việc không ở trạng thái mong đợi hoặc không tồn tại)."""


class VuotHanMuc(Exception):
    """Vượt hạn mức (D5, §10)."""


class KhongCoPhien(Exception):
    """D11 §7.6: việc không còn phiên Claude sống để nhận trả lời qua stdin (API trả 409 "dùng Xin duyệt lại")."""


@dataclass(frozen=True)
class BuocChay:
    ten: str
    argv: list[str]
    cwd: str
    stdin: str | None
    env_them: dict[str, str]
    la_claude: bool
    het_gio_s: int
    hien_cua_so: bool = False
    file_log_phu: str | None = None
    # D11 §7.2: bước là MỘT phiên Claude sống (stdin giữ mở, stream-json vào) — vòng chạy dùng phien_song (A-5).
    song: bool = False


# §7.6 (S-4 #4): mã câu hỏi trong phiên sống = "q" + secrets.token_hex(6). Dùng fullmatch khi kiểm input ngoài
# (`$` của re còn khớp trước "\n" cuối chuỗi).
RE_MA_CAU_HOI = re.compile(r"^q[0-9a-f]{12}$", re.ASCII)


@dataclass(frozen=True)
class CanNguoiDung:
    loai: str                     # 'viec_tay' | 'chon' | 'khong_ro' | 'cau_hoi'
    noi_dung: str
    lua_chon: tuple[str, ...] = ()
    # §7.6: mã câu hỏi của phiên sống ("" = câu hỏi không thuộc phiên sống / dữ liệu cũ).
    ma: str = ""

    def thanh_dict(self) -> dict:
        d = {"loai": self.loai, "noi_dung": self.noi_dung, "lua_chon": list(self.lua_chon)}
        if self.ma:
            d["ma"] = self.ma
        return d

    @staticmethod
    def tu_dict(d: dict) -> "CanNguoiDung":
        ma = d.get("ma")
        return CanNguoiDung(str(d.get("loai", "viec_tay")), str(d.get("noi_dung", "")),
                            tuple(str(x) for x in d.get("lua_chon") or ()), ma if isinstance(ma, str) else "")


@dataclass(frozen=True)
class KetQuaAgent:
    trang_thai: str               # DONE|DONE_WITH_CONCERNS|BLOCKED|NEEDS_CONTEXT|NEEDS_APPROVAL|CAN_USER|KHONG_RO
    cau_hoi: CanNguoiDung | None
    tom_tat: str


def _khong_co_folder() -> list[dict]:
    return []


def _khong_ro_ma_voice(p: Path, me: str) -> list[str] | None:
    return None


@dataclass
class MoiTruong:
    gocs: list[Path]
    repo_kho: Path
    thu_muc_scripts: Path
    python_poster: Path
    claude_exe: Path
    agy_exe: Path
    thu_muc_radar: Path
    thu_muc_sp: Path
    thu_muc_du_lieu: Path
    cong_song: Callable[[int], bool]
    chan_doan_kho: Callable[[Path], CanNguoiDung | str | None]   # None = sạch; 'ban' = đợi; CanNguoiDung = việc tay
    ffmpeg_ngoai: Callable[[], bool]
    thoi_luong_media: Callable[[Path], float | None]             # ffprobe
    bay_gio: Callable[[], datetime]
    doc_folder_poster: Callable[[], list[dict]] = field(default=_khong_co_folder)
    # MỞ RỘNG (ngoài chữ ký §13, có mặc định nên không phá chỗ gọi): danh sách mã bản của mẻ
    # (`trang_thai.py --project P --batch me ma`, §5.1 P2-7). None = không xác định → đối soát 'khong_ro'.
    ds_ma_voice: Callable[[Path, str], list[str] | None] = field(default=_khong_ro_ma_voice)
