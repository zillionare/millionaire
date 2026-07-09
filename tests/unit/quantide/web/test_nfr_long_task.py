"""NFR-0060 长任务交互单元测试.

覆盖 acceptance.md AC-NFR0060-1~5c:
- init-wizard 步骤式进度 (百分比 + 步骤名 + current/total)
- 数据同步任务列表进度 (百分比 + 任务名)
- 回测进度 (天数 + 阶段名, 由 FR-0380 覆盖)
- SSE 断线重连提示
- 中断后恢复、页面重入
"""
from __future__ import annotations

import pytest

from quantide.web.nfr_long_task import (
    format_step_progress,
    format_task_progress,
    is_progress_page_reentry_valid,
    resume_from_checkpoint,
    sse_reconnect_message,
)


class TestStepProgress:
    """AC-NFR0060-1/AC-5: init-wizard 步骤式进度."""

    def test_format_includes_percent(self):
        text = format_step_progress(60, "正在下载交易日历", 3, 7)
        assert "60%" in text

    def test_format_includes_step_name_and_counter(self):
        text = format_step_progress(60, "正在下载交易日历", 3, 7)
        assert "正在下载交易日历" in text
        assert "(3/7)" in text


class TestTaskProgress:
    """AC-NFR0060-5b: 数据同步任务列表进度."""

    def test_format_includes_percent_and_task_name(self):
        text = format_task_progress(60, "正在同步日线行情 (A 股)")
        assert "60%" in text
        assert "正在同步日线行情 (A 股)" in text


class TestSseReconnect:
    """AC-NFR0060-3: SSE 断线重连提示."""

    def test_message_contains_reconnect(self):
        msg = sse_reconnect_message()
        assert "连接中断" in msg
        assert "重连" in msg


class TestResumeFromCheckpoint:
    """AC-NFR0060-2: 中断后从失败步骤继续."""

    def test_resume_info_points_to_failed_step(self):
        info = resume_from_checkpoint(4)
        assert info["resume_from_step"] == 4
        assert info["preserve_completed_steps"] is True


class TestProgressPageReentry:
    """AC-NFR0060-4: 页面重入恢复到当前步骤."""

    def test_reentry_valid_when_step_within_range(self):
        assert is_progress_page_reentry_valid(4, 7) is True

    def test_reentry_invalid_when_out_of_range(self):
        assert is_progress_page_reentry_valid(8, 7) is False
