"""Dò dự án theo UID (docs/bo-chay-viec.md §5, D8).

GOCS_MAC_DINH là bản SAO Y tools/video_server.py:24 (không import video_server từ repo vì runner chạy từ bản cài).
Test tools/test_runner_danh_muc.py đọc file nguồn video_server bằng regex để phát hiện lệch.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path

from .kieu import ThamSoLoi

log = logging.getLogger(__name__)

GOCS_MAC_DINH: list[str] = ["E:/oneshottramcanh", "F:/2010", "F:/2210", "F:/2310/ncm", "F:/2610/1026/ncm",
                            "F:/2710/1028", "F:/3010/3010/ncm", "E:/Aff anh nhan/review"]

RE_UID = re.compile(r"^\d{19}$", re.ASCII)  # ASCII: \d không nhận chữ số Unicode (１２３)
RE_MA = re.compile(r"^[0-9a-f]{12}$")
RE_ME = re.compile(r"^\d{8}-[a-z0-9]{1,12}$", re.ASCII)
_RE_FILE_ME = re.compile(r"^(\d{8}-[a-z0-9]{1,12})_kich-ban-da-cham\.md$", re.ASCII)


def kiem_uid(uid: object) -> str:
    if not isinstance(uid, str) or not RE_UID.fullmatch(uid):
        raise ThamSoLoi("uid phải là 19 chữ số")
    return uid


def gocs_tu_moi_truong() -> list[Path]:
    """KHO_VIDEO_GOC (cách nhau ';', giống video_server) hoặc mặc định."""
    nguon = os.environ.get("KHO_VIDEO_GOC", ";".join(GOCS_MAC_DINH))
    return [Path(g) for g in nguon.split(";") if g.strip()]


def ma_du_an(p: Path) -> str:
    return hashlib.sha1(Path(p).as_posix().encode("utf-8")).hexdigest()[:12]


def _thu_muc_cua_uid(uid: str, gocs: list[Path]) -> list[tuple[Path, Path]]:
    """[(goc, thư mục)] khớp '<GOC>/*<UID>' — ký tự ngay trước UID không được là chữ số."""
    kiem_uid(uid)
    kq: list[tuple[Path, Path]] = []
    for g in gocs:
        try:
            if not g.is_dir():
                continue
            for d in sorted(g.glob(f"*{uid}")):
                ten = d.name
                if not d.is_dir() or not ten.endswith(uid):
                    continue
                if len(ten) > len(uid) and ten[-len(uid) - 1] in "0123456789":
                    continue
                kq.append((g, d))
        except OSError as e:  # ổ F: rút ra / không có quyền: bỏ gốc này, không sập cả danh sách
            log.warning("không đọc được thư mục gốc %s: %s", g, e)
    return kq


def ds_me(p: Path) -> list[str]:
    kb = Path(p) / "kich-ban"
    try:
        ten = [f.name for f in kb.iterdir() if f.is_file()] if kb.is_dir() else []
    except OSError as e:
        log.warning("không đọc được %s: %s", kb, e)
        return []
    return sorted({m.group(1) for t in ten if (m := _RE_FILE_ME.fullmatch(t))})


def ds_du_an(uid: str, gocs: list[Path]) -> list[dict]:
    return [{"ma": ma_du_an(d), "ten": d.name, "goc": g.as_posix(), "me": ds_me(d),
             "co_captions": (d / "kich-ban" / "poster_captions.txt").is_file()}
            for g, d in _thu_muc_cua_uid(uid, gocs)]


def tim_du_an(ma: str, uid: str, gocs: list[Path]) -> Path | None:
    if not isinstance(ma, str) or not RE_MA.fullmatch(ma):
        raise ThamSoLoi("mã dự án phải là 12 ký tự hex")
    for _g, d in _thu_muc_cua_uid(uid, gocs):
        if ma_du_an(d) == ma:
            return d
    return None
