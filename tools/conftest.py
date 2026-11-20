"""Cấu hình chung cho test trong tools/.

20/11/2026 chủ shop bỏ giới hạn chi phí: HAN_MUC_TRAN đặt 999999 cho claude/genmax/codex/taovideo usd-mp3.
Các test cơ chế hạn mức (chặn khi vượt, file chỉ được hạ, đếm theo ngày…) cần trần nhỏ để kích hoạt được, nên
fixture dưới đây vá HAN_MUC_TRAN về bộ trần thử nghiệm cũ cho MỌI test, trừ test kiểm hằng số thật
(`test_hang_so_dung_tai_lieu`). Vá tại chỗ (cùng object dict) nên api/danh_muc/vong_lap đều thấy.
"""
from __future__ import annotations

import pytest

TRAN_THU = {
    "claude_usd_ngay": 40, "claude_viec_ngay": 12,
    "genmax_ban_moi_viec": 25, "genmax_viec_ngay": 2,
    "codex_luot_viec": 6,
    "taovideo_usd_viec": 60, "taovideo_mp3_viec": 25,
}
TEST_DUNG_TRAN_THAT = {"test_hang_so_dung_tai_lieu"}


@pytest.fixture(autouse=True)
def _tran_thu_nghiem(request, monkeypatch):
    if request.node.originalname in TEST_DUNG_TRAN_THAT:
        yield
        return
    try:
        from runner import han_muc
    except ImportError:
        yield
        return
    for k, v in TRAN_THU.items():
        monkeypatch.setitem(han_muc.HAN_MUC_TRAN, k, v)
    yield
