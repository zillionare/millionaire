"""FR-0201/0202/0203 概览 ViewModel 服务.

聚合 dashboard 三区块数据 (按 Aaron Round 2 Q5=A 决策顺序: 告警 -> 账户 -> 任务):
- D203 告警分类 (策略类/系统类, 每组最多 5 条)
- D201 账户总览 (实盘总账户 + 虚拟账户按总资产降序)
- D202 数据/系统任务状态 (失败置顶, 最近 10 条)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

_DASHBOARD_TASK_LIMIT = 10
_ALERT_GROUP_LIMIT = 5


class AlertCategory(str, Enum):
    """告警分类 (AC-FR0203-1)."""

    STRATEGY = "strategy"
    SYSTEM = "system"


class TaskStatus(str, Enum):
    """任务状态 (AC-FR0202-1)."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    RUNNING = "running"


@dataclass
class AlertItem:
    """告警条目 (interfaces.md §4.4).

    Attributes:
        alert_id: 告警 ID.
        created_at: ISO datetime.
        source: 来源.
        category: 策略类 / 系统类.
        level: error / warning / info.
        summary: 列表摘要.
        detail_url: 点击跳转 URL.
        read: 是否已读.
        confirmed: 是否确认.
    """

    alert_id: str
    created_at: str
    source: str
    category: AlertCategory
    level: str
    summary: str
    detail_url: str
    read: bool
    confirmed: bool


@dataclass
class AccountOverviewItem:
    """账户总览条目 (interfaces.md §4.2 子集).

    Attributes:
        account_id: 账户 ID.
        account_name: 展示名称.
        total_assets: 总资产.
        available_cash: 可用现金.
        market_value: 持仓市值.
        daily_pnl: 当日盈亏.
        mode: total_live / paper / live.
    """

    account_id: str
    account_name: str
    total_assets: float
    available_cash: float
    market_value: float
    daily_pnl: float
    mode: str


@dataclass
class TaskItem:
    """任务条目 (AC-FR0202-1).

    Attributes:
        task_id: 任务 ID.
        task_name: 任务名.
        last_run_at: 上次运行时间 (ISO datetime).
        status: 任务状态.
        duration_seconds: 上次耗时.
        error_summary: 失败时的错误摘要.
    """

    task_id: str
    task_name: str
    last_run_at: str
    status: TaskStatus
    duration_seconds: int
    error_summary: str | None


@dataclass
class DashboardViewModel:
    """概览 ViewModel (三区块聚合).

    Attributes:
        alert_groups: 告警分类分组.
        total_live_account: 实盘总账户 (None 表示无).
        virtual_accounts: 虚拟账户列表 (已排序).
        tasks: 任务列表 (已排序截断).
    """

    alert_groups: dict[AlertCategory, list[AlertItem]]
    total_live_account: AccountOverviewItem | None
    virtual_accounts: list[AccountOverviewItem]
    tasks: list[TaskItem] = field(default_factory=list)


def alert_level_color(level: str) -> Literal["red", "yellow", "blue"]:
    """AC-FR0203-2: 告警级别颜色映射.

    Args:
        level: error / warning / info.

    Returns:
        错误红 / 警告黄 / 提示蓝.
    """
    if level == "error":
        return "red"
    if level == "warning":
        return "yellow"
    return "blue"


def build_alert_groups(alerts: list[AlertItem]) -> dict[AlertCategory, list[AlertItem]]:
    """AC-FR0203-1: 构建告警分类分组.

    按'策略类 / 系统类'两组, 每组最多展示 5 条最新告警 (按 created_at 倒序).

    Args:
        alerts: 全部告警列表.

    Returns:
        分组字典.
    """
    grouped: dict[AlertCategory, list[AlertItem]] = {
        AlertCategory.STRATEGY: [],
        AlertCategory.SYSTEM: [],
    }
    for category in grouped:
        bucket = [a for a in alerts if a.category == category]
        bucket.sort(key=lambda a: a.created_at, reverse=True)
        grouped[category] = bucket[:_ALERT_GROUP_LIMIT]
    return grouped


def sort_virtual_accounts_by_total_assets(
    accounts: list[AccountOverviewItem],
) -> list[AccountOverviewItem]:
    """AC-FR0201-1: 虚拟账户按总资产降序排列.

    Args:
        accounts: 虚拟账户列表.

    Returns:
        排序后的列表.
    """
    return sorted(accounts, key=lambda a: a.total_assets, reverse=True)


def sort_tasks_for_dashboard(tasks: list[TaskItem]) -> list[TaskItem]:
    """AC-FR0202-2: 任务排序 - 失败置顶, 然后按上次运行时间倒序.

    Args:
        tasks: 任务列表.

    Returns:
        排序后的列表 (失败在前, 非失败在后; 同组内按 last_run_at 倒序).
    """
    if not tasks:
        return []
    failed = [t for t in tasks if t.status == TaskStatus.FAILED]
    others = [t for t in tasks if t.status != TaskStatus.FAILED]
    failed.sort(key=lambda t: t.last_run_at, reverse=True)
    others.sort(key=lambda t: t.last_run_at, reverse=True)
    return failed + others


def _truncate_tasks(tasks: list[TaskItem]) -> list[TaskItem]:
    """AC-4: 默认最多显示最近 10 条任务."""
    return tasks[:_DASHBOARD_TASK_LIMIT]


def build_dashboard_view_model(
    alerts: list[AlertItem],
    total_live_account: AccountOverviewItem | None,
    virtual_accounts: list[AccountOverviewItem],
    tasks: list[TaskItem],
) -> DashboardViewModel:
    """聚合 dashboard 三区块 ViewModel.

    Args:
        alerts: 全部告警列表.
        total_live_account: 实盘总账户 (None 表示无).
        virtual_accounts: 虚拟账户列表 (未排序).
        tasks: 任务列表 (未排序).

    Returns:
        DashboardViewModel.
    """
    sorted_tasks = sort_tasks_for_dashboard(tasks)
    return DashboardViewModel(
        alert_groups=build_alert_groups(alerts),
        total_live_account=total_live_account,
        virtual_accounts=sort_virtual_accounts_by_total_assets(virtual_accounts),
        tasks=_truncate_tasks(sorted_tasks),
    )


__all__ = [
    "AccountOverviewItem",
    "AlertCategory",
    "AlertItem",
    "DashboardViewModel",
    "TaskItem",
    "TaskStatus",
    "alert_level_color",
    "build_alert_groups",
    "build_dashboard_view_model",
    "sort_tasks_for_dashboard",
    "sort_virtual_accounts_by_total_assets",
]
