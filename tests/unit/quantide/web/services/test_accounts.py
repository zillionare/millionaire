"""FR-0411 账户隐藏两层语义单元测试.

覆盖 acceptance.md AC-FR0411-1~8:
- 服务端 `account.hidden` 字段决定真隐藏
- localStorage `display_hidden_accounts` 仅决定是否在 UI 显示已隐藏账户
- 隐藏前置条件: 空闲 + 无未结算持仓 + 非风控限制
- 隐藏账户不参与 FR-0201/FR-0390 合计统计
- 无创建/删除/重置账户入口 (AC-8)
"""
from __future__ import annotations

import pytest

from quantide.web.services.accounts import (
    AccountHideEligibility,
    AccountHideRequest,
    AccountHideResult,
    AccountSummary,
    can_hide_account,
    can_unhide_account,
    filter_accounts_for_display,
    is_hidden_account_action_allowed,
    summarize_accounts_excluding_hidden,
)


def _make_account(
    account_id: str = "acc-1",
    name: str = "策略A-仿真",
    hidden: bool = False,
    status: str = "idle",
    has_position: bool = False,
    is_risk_control: bool = False,
    total_assets: float = 100000.0,
) -> AccountSummary:
    return AccountSummary(
        account_id=account_id,
        account_name=name,
        mode="paper",
        strategy_id="strat-a",
        total_assets=total_assets,
        available_cash=50000.0,
        market_value=50000.0,
        account_pnl=1000.0,
        daily_pnl=200.0,
        hidden=hidden,
        status=status,
        has_position=has_position,
        is_risk_control=is_risk_control,
    )


class TestHideEligibility:
    """AC-2, AC-3: 隐藏前置条件 - 空闲 + 无未结算持仓 + 非风控限制."""

    def test_idle_no_position_can_hide(self):
        """AC-2: 空闲 + 无未结算持仓 -> 可隐藏."""
        acc = _make_account(status="idle", has_position=False)
        result = can_hide_account(acc)
        assert result.eligible is True

    def test_running_cannot_hide(self):
        """AC-3: 有运行中策略绑定 -> 按钮置灰."""
        acc = _make_account(status="running", has_position=False)
        result = can_hide_account(acc)
        assert result.eligible is False
        assert "非空闲" in result.reason

    def test_with_position_cannot_hide(self):
        """AC-3: 有未结算持仓 (持仓 != 0) -> 按钮置灰."""
        acc = _make_account(status="idle", has_position=True)
        result = can_hide_account(acc)
        assert result.eligible is False
        assert "未结算持仓" in result.reason

    def test_offline_can_hide(self):
        """offline 状态视为空闲 (无运行中策略)."""
        acc = _make_account(status="offline", has_position=False)
        result = can_hide_account(acc)
        assert result.eligible is True

    def test_fault_can_hide(self):
        acc = _make_account(status="fault", has_position=False)
        result = can_hide_account(acc)
        assert result.eligible is True

    def test_stopped_can_hide(self):
        acc = _make_account(status="stopped", has_position=False)
        result = can_hide_account(acc)
        assert result.eligible is True


class TestHideActionGuard:
    """AC-2, AC-3: 隐藏动作守卫."""

    def test_action_blocked_when_ineligible(self):
        """AC-3: 非空闲或有持仓时不允许触发隐藏."""
        acc = _make_account(status="running", has_position=False)
        assert is_hidden_account_action_allowed(acc) is False

    def test_action_allowed_when_eligible(self):
        acc = _make_account(status="idle", has_position=False)
        assert is_hidden_account_action_allowed(acc) is True


class TestHideRequestConfirmName:
    """AC-2: 二次确认 (输入账户名)."""

    def test_confirm_name_match_succeeds(self):
        req = AccountHideRequest(account_id="acc-1", confirm_name="策略A-仿真")
        result = req.validate(_make_account())
        assert result.ok is True

    def test_confirm_name_mismatch_fails(self):
        req = AccountHideRequest(account_id="acc-1", confirm_name="wrong")
        result = req.validate(_make_account())
        assert result.ok is False
        assert "账户名不匹配" in result.message


class TestUnhideAccount:
    """AC-6: 取消隐藏."""

    def test_can_unhide_hidden_account(self):
        acc = _make_account(hidden=True)
        assert can_unhide_account(acc) is True

    def test_cannot_unhide_visible_account(self):
        acc = _make_account(hidden=False)
        assert can_unhide_account(acc) is False


class TestFilterForDisplay:
    """AC-1, AC-5: display_hidden_accounts 两层语义."""

    def test_default_hides_hidden_accounts(self):
        """AC-1: display_hidden_accounts=false (默认) -> hidden=true 账户不出现."""
        accounts = [
            _make_account("a1", hidden=False),
            _make_account("a2", hidden=True),
            _make_account("a3", hidden=False),
        ]
        visible = filter_accounts_for_display(accounts, display_hidden=False)
        assert [a.account_id for a in visible] == ["a1", "a3"]

    def test_show_hidden_reveals_gray_accounts(self):
        """AC-5: display_hidden_accounts=true -> 已隐藏账户以灰色样式出现."""
        accounts = [
            _make_account("a1", hidden=False),
            _make_account("a2", hidden=True),
        ]
        visible = filter_accounts_for_display(accounts, display_hidden=True)
        assert len(visible) == 2
        hidden_one = next(a for a in visible if a.account_id == "a2")
        assert hidden_one.hidden is True


class TestSummaryExcludesHidden:
    """AC-4: 隐藏账户不参与合计统计."""

    def test_summary_excludes_hidden_from_total(self):
        """AC-4: 被隐藏账户不参与 FR-0201/FR-0390 合计统计."""
        accounts = [
            _make_account("a1", total_assets=100000, hidden=False),
            _make_account("a2", total_assets=200000, hidden=True),
            _make_account("a3", total_assets=300000, hidden=False),
        ]
        summary = summarize_accounts_excluding_hidden(accounts)
        assert summary["total_assets"] == 400000
        assert summary["available_cash"] == 100000
        assert summary["market_value"] == 100000

    def test_summary_with_display_hidden_still_excludes_from_total(self):
        """AC-5: 即使 display_hidden=true 显示隐藏账户, 合计仍不含隐藏账户."""
        accounts = [
            _make_account("a1", total_assets=100000, hidden=False),
            _make_account("a2", total_assets=200000, hidden=True),
        ]
        summary = summarize_accounts_excluding_hidden(accounts)
        assert summary["total_assets"] == 100000


class TestNoCreateDeleteResetEntrance:
    """AC-8: UI 无创建/删除/重置账户入口."""

    def test_account_actions_do_not_include_create(self):
        from quantide.web.services.accounts import ALLOWED_ACCOUNT_ACTIONS

        assert "create" not in ALLOWED_ACCOUNT_ACTIONS
        assert "delete" not in ALLOWED_ACCOUNT_ACTIONS
        assert "reset" not in ALLOWED_ACCOUNT_ACTIONS

    def test_only_hide_and_unhide_allowed(self):
        from quantide.web.services.accounts import ALLOWED_ACCOUNT_ACTIONS

        assert set(ALLOWED_ACCOUNT_ACTIONS) == {"hide", "unhide"}
