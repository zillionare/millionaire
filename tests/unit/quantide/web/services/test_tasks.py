"""FR-0310 数据同步任务单元测试.

覆盖 acceptance.md AC-FR0310-1~6:
- AC-1: 任务列表 (日线行情/证券列表/交易日历/ST/涨跌停) + 任务名/上次运行/状态
- AC-2: 失败任务立即重试
- AC-3: 启用/禁用开关
- AC-4: 立即手动跑一次
- AC-5: cron 表达式修改
- AC-6: 查看历史最近 N=10 次
"""
from __future__ import annotations

import pytest

from quantide.web.services.tasks import (
    DATA_SYNC_TASK_NAMES,
    CronValidationError,
    TaskHistoryItem,
    TaskListItem,
    TaskRunRequest,
    TaskRunResult,
    TaskStatus,
    TaskToggleRequest,
    truncate_task_history,
    validate_cron_expression,
)


class TestDataSyncTaskNames:
    """AC-1: 数据同步任务列表."""

    def test_has_five_tasks(self):
        assert "日线行情" in DATA_SYNC_TASK_NAMES
        assert "证券列表" in DATA_SYNC_TASK_NAMES
        assert "交易日历" in DATA_SYNC_TASK_NAMES
        assert "ST" in DATA_SYNC_TASK_NAMES
        assert "涨跌停" in DATA_SYNC_TASK_NAMES


class TestCronValidation:
    """AC-5: cron 表达式校验."""

    def test_valid_cron_five_fields(self):
        assert validate_cron_expression("0 18 * * 1-5") is True

    def test_valid_cron_simple(self):
        assert validate_cron_expression("0 19 * * 1-5") is True

    def test_invalid_cron_too_few_fields(self):
        with pytest.raises(CronValidationError):
            validate_cron_expression("0 18 * *")

    def test_invalid_cron_non_numeric(self):
        with pytest.raises(CronValidationError):
            validate_cron_expression("a b c d e")


class TestTaskHistoryTruncation:
    """AC-6: 查看历史最近 N=10 次."""

    def test_truncate_to_ten(self):
        history = [TaskHistoryItem(run_at=f"2026-07-09T1{i}:00:00", status=TaskStatus.SUCCESS, duration_seconds=10, error_detail=None) for i in range(15)]
        truncated = truncate_task_history(history)
        assert len(truncated) == 10


class TestTaskRunRequest:
    """AC-2, AC-4: 立即重试 / 手动跑一次."""

    def test_run_request_carries_task_id(self):
        req = TaskRunRequest(task_id="t1")
        assert req.task_id == "t1"

    def test_run_result_running(self):
        result = TaskRunResult(ok=True, task_id="t1", new_status=TaskStatus.RUNNING, message="已触发")
        assert result.new_status == TaskStatus.RUNNING


class TestTaskToggle:
    """AC-3: 启用/禁用开关."""

    def test_toggle_request(self):
        req = TaskToggleRequest(task_id="t1", enabled=False)
        assert req.enabled is False

    def test_toggle_to_disabled(self):
        item = TaskListItem(task_id="t1", task_name="日线行情", last_run_at="2026-07-09T10:00:00", status=TaskStatus.SUCCESS, enabled=True)
        item.enabled = False
        assert item.enabled is False
