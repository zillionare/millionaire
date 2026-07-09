"""FR-0040 调度操作界面 + FR-0060 dry-run 单元测试.

覆盖:
- AC-FR0040-1~7: 启动回测/转仿真/转实盘表单规则, 本金只读
- AC-FR0060-1~4: dry-run 切换, 并行仿真视图, 运行时实例生命周期
"""
from __future__ import annotations

import pytest

from quantide.web.services.runtime_control import (
    PromoteMode,
    PromoteRequest,
    PromoteValidationError,
    RuntimeInstance,
    RuntimeInstanceStatus,
    RuntimeMode,
    can_promote_to_live,
    can_promote_to_paper,
    can_start_backtest,
    is_principal_editable,
    is_strategy_backtestable,
    validate_promote_request,
)


class TestBacktestAvailability:
    """AC-FR0040-1, AC-2: 启动回测."""

    def test_day_strategy_backtestable(self):
        assert is_strategy_backtestable(strategy_type="day") is True

    def test_live_strategy_not_backtestable(self):
        """AC-2: 实时策略走 001-FR-240, 无回测入口."""
        assert is_strategy_backtestable(strategy_type="live") is False

    def test_risk_strategy_not_backtestable(self):
        assert is_strategy_backtestable(strategy_type="risk") is False

    def test_can_start_backtest_for_day(self):
        assert can_start_backtest(strategy_type="day") is True


class TestPromoteForms:
    """AC-FR0040-5: 转入表单规则."""

    def test_paper_form_requires_account_name(self):
        """AC-5: 仿真表单: 运行时参数 + 账户名 (不允许空) + 本金 (>0)."""
        req = PromoteRequest(
            mode=PromoteMode.PAPER,
            strategy_id="s1",
            account_name="",
            principal=100000,
        )
        with pytest.raises(PromoteValidationError):
            validate_promote_request(req)

    def test_paper_form_requires_positive_principal(self):
        req = PromoteRequest(
            mode=PromoteMode.PAPER,
            strategy_id="s1",
            account_name="acc",
            principal=0,
        )
        with pytest.raises(PromoteValidationError):
            validate_promote_request(req)

    def test_paper_form_valid(self):
        req = PromoteRequest(
            mode=PromoteMode.PAPER,
            strategy_id="s1",
            account_name="acc",
            principal=100000,
        )
        assert validate_promote_request(req) is True

    def test_live_form_valid(self):
        """AC-5: 实盘表单: 运行时参数 + 账户名 + 本金 (从实盘总账户分配)."""
        req = PromoteRequest(
            mode=PromoteMode.LIVE,
            strategy_id="s1",
            account_name="live-acc",
            principal=50000,
        )
        assert validate_promote_request(req) is True


class TestPrincipalReadOnly:
    """AC-FR0040-6: 创建账户后本金只读."""

    def test_paper_principal_not_editable(self):
        """AC-6: 仿真账户创建后本金只读."""
        assert is_principal_editable(RuntimeMode.PAPER) is False

    def test_live_virtual_principal_not_editable(self):
        """AC-6: 虚拟实盘账户本金只读."""
        assert is_principal_editable(RuntimeMode.LIVE) is False

    def test_total_live_principal_editable(self):
        """AC-7: 实盘总账户本金可编辑 (FR-0420 入口)."""
        assert is_principal_editable(RuntimeMode.TOTAL_LIVE) is True


class TestPromoteAvailability:
    """AC-FR0040-2: 转仿真/转实盘入口可见性."""

    def test_day_strategy_can_promote(self):
        """AC-2: 已完成回测结果的日线策略有转仿真/转实盘入口."""
        assert can_promote_to_paper(strategy_type="day", has_backtest=True) is True
        assert can_promote_to_live(strategy_type="day", has_backtest=True) is True

    def test_live_strategy_no_promote_from_backtest(self):
        """AC-2: 实时策略无回测, 不显示转仿真/转实盘按钮."""
        assert can_promote_to_paper(strategy_type="live", has_backtest=False) is False
        assert can_promote_to_live(strategy_type="live", has_backtest=False) is False

    def test_day_without_backtest_no_promote(self):
        assert can_promote_to_paper(strategy_type="day", has_backtest=False) is False


class TestRuntimeInstanceLifecycle:
    """AC-FR0060-4: 运行时实例生命周期."""

    def test_idle_can_start(self):
        inst = RuntimeInstance(instance_id="i1", status=RuntimeInstanceStatus.IDLE, mode=RuntimeMode.LIVE)
        assert inst.can_start() is True

    def test_running_can_stop(self):
        inst = RuntimeInstance(instance_id="i1", status=RuntimeInstanceStatus.RUNNING, mode=RuntimeMode.LIVE)
        assert inst.can_stop() is True

    def test_running_live_can_pause(self):
        """AC-FR0060-1: 实盘策略可进入 dry-run (暂停)."""
        inst = RuntimeInstance(instance_id="i1", status=RuntimeInstanceStatus.RUNNING, mode=RuntimeMode.LIVE)
        assert inst.can_pause() is True

    def test_running_paper_cannot_pause(self):
        """暂停仅实盘 dry-run."""
        inst = RuntimeInstance(instance_id="i1", status=RuntimeInstanceStatus.RUNNING, mode=RuntimeMode.PAPER)
        assert inst.can_pause() is False

    def test_paused_can_resume(self):
        """AC-FR0060-3: 退出 dry-run 恢复为 live."""
        inst = RuntimeInstance(instance_id="i1", status=RuntimeInstanceStatus.PAUSED, mode=RuntimeMode.LIVE)
        assert inst.can_resume() is True

    def test_stopped_cannot_restart(self):
        """AC-FR0060-4: 停止后不可重启, 需全新实例."""
        inst = RuntimeInstance(instance_id="i1", status=RuntimeInstanceStatus.STOPPED, mode=RuntimeMode.LIVE)
        assert inst.can_start() is False
        assert inst.can_pause() is False
        assert inst.can_resume() is False
