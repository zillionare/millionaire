"""FR-0201/0202/0203 概览 ViewModel 单元测试.

覆盖 acceptance.md:
- AC-FR0203-1~4: 告警分类 (策略类/系统类, 每组最多 5 条, 按级别着色)
- AC-FR0201-1~2: 账户总览 (实盘总账户 + 虚拟账户列表, 按总资产降序)
- AC-FR0202-1~5: 数据/系统任务状态 (失败置顶, 最近 10 条, 无"今日计划")
"""
from __future__ import annotations

from datetime import datetime

import pytest

from quantide.web.services.dashboard import (
    AlertCategory,
    AlertItem,
    DashboardViewModel,
    TaskItem,
    TaskStatus,
    build_alert_groups,
    build_dashboard_view_model,
    sort_virtual_accounts_by_total_assets,
    sort_tasks_for_dashboard,
)


def _alert(alert_id, category, level="error", created_at="2026-07-09T10:00:00"):
    return AlertItem(
        alert_id=alert_id,
        created_at=created_at,
        source="strategy" if category == AlertCategory.STRATEGY else "system",
        category=category,
        level=level,
        summary=f"alert {alert_id}",
        detail_url=f"/alert/{alert_id}",
        read=False,
        confirmed=False,
    )


def _task(task_id, status, last_run="2026-07-09T10:00:00", name="日线行情"):
    return TaskItem(
        task_id=task_id,
        task_name=name,
        last_run_at=last_run,
        status=status,
        duration_seconds=12,
        error_summary=None if status != TaskStatus.FAILED else "timeout",
    )


class TestAlertGroups:
    """AC-FR0203-1~4: 告警分类."""

    def test_split_into_strategy_and_system_groups(self):
        """AC-1: 按'策略类 / 系统类'两组."""
        alerts = [
            _alert("a1", AlertCategory.STRATEGY),
            _alert("a2", AlertCategory.SYSTEM),
            _alert("a3", AlertCategory.STRATEGY),
        ]
        groups = build_alert_groups(alerts)
        assert len(groups[AlertCategory.STRATEGY]) == 2
        assert len(groups[AlertCategory.SYSTEM]) == 1

    def test_each_group_max_five(self):
        """AC-1: 每组最多展示 5 条最新告警."""
        alerts = [_alert(f"a{i}", AlertCategory.STRATEGY, created_at=f"2026-07-09T10:0{i}:00") for i in range(10)]
        groups = build_alert_groups(alerts)
        assert len(groups[AlertCategory.STRATEGY]) == 5

    def test_keeps_latest_five(self):
        """AC-1: 保留最新 5 条 (按 created_at 倒序)."""
        alerts = [
            _alert("old", AlertCategory.STRATEGY, created_at="2026-07-09T09:00:00"),
            _alert("new1", AlertCategory.STRATEGY, created_at="2026-07-09T11:00:00"),
            _alert("new2", AlertCategory.STRATEGY, created_at="2026-07-09T12:00:00"),
        ]
        groups = build_alert_groups(alerts)
        ids = [a.alert_id for a in groups[AlertCategory.STRATEGY]]
        assert ids == ["new2", "new1", "old"]

    def test_level_color_mapping(self):
        """AC-2: 错误红/警告黄/提示蓝."""
        from quantide.web.services.dashboard import alert_level_color

        assert alert_level_color("error") == "red"
        assert alert_level_color("warning") == "yellow"
        assert alert_level_color("info") == "blue"


class TestVirtualAccountsSorting:
    """AC-FR0201-1: 虚拟账户按总资产降序."""

    def test_sort_desc_by_total_assets(self):
        from quantide.web.services.dashboard import AccountOverviewItem

        accounts = [
            AccountOverviewItem(account_id="a1", account_name="A", total_assets=100000, available_cash=0, market_value=0, daily_pnl=0, mode="paper"),
            AccountOverviewItem(account_id="a2", account_name="B", total_assets=300000, available_cash=0, market_value=0, daily_pnl=0, mode="live"),
            AccountOverviewItem(account_id="a3", account_name="C", total_assets=200000, available_cash=0, market_value=0, daily_pnl=0, mode="paper"),
        ]
        sorted_accs = sort_virtual_accounts_by_total_assets(accounts)
        assert [a.account_id for a in sorted_accs] == ["a2", "a3", "a1"]


class TestTaskSorting:
    """AC-FR0202-2: 失败任务置顶, 然后按上次运行时间倒序."""

    def test_failed_tasks_on_top(self):
        tasks = [
            _task("t1", TaskStatus.SUCCESS, last_run="2026-07-09T12:00:00"),
            _task("t2", TaskStatus.FAILED, last_run="2026-07-09T10:00:00"),
            _task("t3", TaskStatus.SUCCESS, last_run="2026-07-09T11:00:00"),
        ]
        sorted_tasks = sort_tasks_for_dashboard(tasks)
        assert sorted_tasks[0].task_id == "t2"

    def test_non_failed_sorted_by_last_run_desc(self):
        tasks = [
            _task("t1", TaskStatus.SUCCESS, last_run="2026-07-09T10:00:00"),
            _task("t2", TaskStatus.SUCCESS, last_run="2026-07-09T12:00:00"),
            _task("t3", TaskStatus.SUCCESS, last_run="2026-07-09T11:00:00"),
        ]
        sorted_tasks = sort_tasks_for_dashboard(tasks)
        assert [t.task_id for t in sorted_tasks] == ["t2", "t3", "t1"]


class TestDashboardViewModel:
    """AC-FR0201/0202/0203 聚合."""

    def test_view_model_has_three_blocks(self):
        """区块顺序: 告警 -> 账户 -> 任务."""
        vm = build_dashboard_view_model(
            alerts=[_alert("a1", AlertCategory.STRATEGY)],
            total_live_account=None,
            virtual_accounts=[],
            tasks=[],
        )
        assert vm.alert_groups is not None
        assert vm.total_live_account is None
        assert vm.tasks is not None

    def test_tasks_truncated_to_ten(self):
        """AC-4: 默认最多显示最近 10 条任务."""
        tasks = [_task(f"t{i}", TaskStatus.SUCCESS, last_run=f"2026-07-09T1{i}:00:00") for i in range(15)]
        vm = build_dashboard_view_model(
            alerts=[], total_live_account=None, virtual_accounts=[], tasks=tasks
        )
        assert len(vm.tasks) == 10

    def test_no_today_plan_block(self):
        """AC-5: 概览底部不包含'今日计划运行'或'未来 N 天计划'区块."""
        vm = build_dashboard_view_model(
            alerts=[], total_live_account=None, virtual_accounts=[], tasks=[]
        )
        assert not hasattr(vm, "today_plan")
        assert not hasattr(vm, "future_plan")
