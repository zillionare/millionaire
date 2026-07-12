"""FR-0310 数据同步任务服务.

定义数据同步任务列表、cron 校验、任务运行/启停/历史 schema.

AC-1: 任务列表 (日线行情/证券列表/交易日历/ST/涨跌停).
AC-2: 失败任务立即重试.
AC-3: 启用/禁用开关.
AC-4: 立即手动跑一次.
AC-5: cron 表达式修改.
AC-6: 查看历史最近 N=10 次.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

DATA_SYNC_TASK_NAMES: tuple[str, ...] = (
    "日线行情",
    "证券列表",
    "交易日历",
    "ST",
    "涨跌停",
)

_TASK_HISTORY_LIMIT = 10


class TaskStatus(str, Enum):
    """任务状态."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    RUNNING = "running"


class CronValidationError(ValueError):
    """cron 表达式校验错误."""


@dataclass
class TaskHistoryItem:
    """任务历史条目 (AC-6).

    Attributes:
        run_at: 运行时间.
        status: 运行状态.
        duration_seconds: 耗时.
        error_detail: 失败时的错误详情.
    """

    run_at: str
    status: TaskStatus
    duration_seconds: int
    error_detail: str | None


@dataclass
class TaskListItem:
    """任务列表条目 (AC-1).

    Attributes:
        task_id: 任务 ID.
        task_name: 任务名.
        last_run_at: 上次运行时间.
        status: 上次运行状态.
        enabled: 是否启用.
    """

    task_id: str
    task_name: str
    last_run_at: str
    status: TaskStatus
    enabled: bool = True


@dataclass
class TaskRunRequest:
    """AC-2, AC-4: 立即重试 / 手动跑一次请求.

    Attributes:
        task_id: 任务 ID.
    """

    task_id: str


@dataclass
class TaskRunResult:
    """任务运行结果.

    Attributes:
        ok: 是否成功触发.
        task_id: 任务 ID.
        new_status: 触发后的新状态.
        message: 结果消息.
    """

    ok: bool
    task_id: str
    new_status: TaskStatus
    message: str


@dataclass
class TaskToggleRequest:
    """AC-3: 启用/禁用开关请求.

    Attributes:
        task_id: 任务 ID.
        enabled: 目标启用状态.
    """

    task_id: str
    enabled: bool


def validate_cron_expression(cron: str) -> bool:
    """AC-5: 校验 cron 表达式 (5 字段).

    Args:
        cron: cron 表达式 (分 时 日 月 周).

    Returns:
        True 当表达式为 5 个字段且各字段为合法 cron 值.

    Raises:
        CronValidationError: 当字段数不为 5 或含非法值.
    """
    fields = cron.strip().split()
    if len(fields) != 5:
        raise CronValidationError("cron 表达式必须为 5 个字段 (分 时 日 月 周)")
    for field in fields:
        if not _is_valid_cron_field(field):
            raise CronValidationError(f"cron 字段非法: {field}")
    return True


def _is_valid_cron_field(field: str) -> bool:
    """校验单个 cron 字段.

    支持: *, 数字, 逗号分隔, 范围 (1-5), 步长 (*/5).
    """
    if field == "*":
        return True
    parts = field.replace("-", " ").replace(",", " ").replace("/", " ").split()
    for part in parts:
        if not part.isdigit():
            return False
    return True


def truncate_task_history(history: list[TaskHistoryItem]) -> list[TaskHistoryItem]:
    """AC-6: 截断任务历史到最近 N=10 次.

    Args:
        history: 完整历史列表.

    Returns:
        最近 10 条历史.
    """
    return history[-_TASK_HISTORY_LIMIT:]


__all__ = [
    "DATA_SYNC_TASK_NAMES",
    "CronValidationError",
    "TaskHistoryItem",
    "TaskListItem",
    "TaskRunRequest",
    "TaskRunResult",
    "TaskStatus",
    "TaskToggleRequest",
    "truncate_task_history",
    "validate_cron_expression",
]
