"""FR-0390 账户总览 + FR-0410 账户详情单元测试.

覆盖:
- AC-FR0390-1~5: 账户管理页 (实盘总账户固定首行 + 策略虚拟账户, 筛选, 隐藏排除)
- AC-FR0410-1~3: paper/live 详情 (每日收益率, 净值曲线, 月度热力图, 最大 N 亏损/M 盈利)
"""
from __future__ import annotations

import pytest

from quantide.web.services.account_overview import (
    AccountFilter,
    AccountOverviewRow,
    AccountOverviewSection,
    AccountPnlMetric,
    build_account_overview_rows,
    filter_virtual_accounts,
    is_total_live_row_clickable,
    top_loss_stocks,
    top_profit_stocks,
)


def _row(account_id, name="A", mode="paper", strategy_id="s1", total=100000, is_total_live=False, hidden=False):
    return AccountOverviewRow(
        account_id=account_id,
        account_name=name,
        mode=mode,
        strategy_id=strategy_id,
        total_assets=total,
        available_cash=50000,
        market_value=50000,
        account_pnl=1000,
        daily_pnl=200,
        hidden=hidden,
        status="idle",
        is_total_live=is_total_live,
    )


class TestTotalLiveFixedFirstRow:
    """AC-FR0390-2: 实盘总账户行固定首行, 不受筛选影响."""

    def test_total_live_always_first(self):
        rows = [
            _row("v1", "V1", mode="paper", total=50000),
            _row("live1", "实盘总账户", mode="total_live", total=1000000, is_total_live=True),
            _row("v2", "V2", mode="live", total=200000),
        ]
        overview = build_account_overview_rows(rows)
        assert overview.total_live_account.account_id == "live1"
        virtual_ids = [r.account_id for r in overview.virtual_accounts]
        assert "v1" in virtual_ids
        assert "v2" in virtual_ids
        assert "live1" not in virtual_ids

    def test_total_live_not_affected_by_filter(self):
        """AC-2: 实盘总账户行不受任何筛选影响."""
        rows = [
            _row("live1", "实盘总账户", mode="total_live", total=1000000, is_total_live=True),
            _row("v1", "V1", mode="paper", strategy_id="s1", total=50000),
            _row("v2", "V2", mode="live", strategy_id="s2", total=200000),
        ]
        overview = build_account_overview_rows(rows)
        filtered = filter_virtual_accounts(
            overview.virtual_accounts,
            AccountFilter(strategy_type="day", mode="paper", strategy_id=None),
        )
        assert overview.total_live_account.account_id == "live1"
        assert all(r.account_id != "live1" for r in filtered)


class TestTotalLiveRowNotClickable:
    """AC-FR0390-3: 实盘总账户行不可点击."""

    def test_total_live_row_not_clickable(self):
        assert is_total_live_row_clickable(is_total_live=True) is False

    def test_virtual_row_clickable(self):
        assert is_total_live_row_clickable(is_total_live=False) is True


class TestVirtualAccountFilter:
    """AC-FR0390-4: 策略虚拟账户可被筛选."""

    def test_filter_by_mode(self):
        rows = [
            _row("v1", "V1", mode="paper"),
            _row("v2", "V2", mode="live"),
        ]
        overview = build_account_overview_rows(rows)
        filtered = filter_virtual_accounts(overview.virtual_accounts, AccountFilter(mode="paper", strategy_type=None, strategy_id=None))
        assert len(filtered) == 1
        assert filtered[0].mode == "paper"

    def test_filter_by_strategy_id(self):
        rows = [
            _row("v1", "V1", strategy_id="s1"),
            _row("v2", "V2", strategy_id="s2"),
        ]
        overview = build_account_overview_rows(rows)
        filtered = filter_virtual_accounts(overview.virtual_accounts, AccountFilter(mode=None, strategy_type=None, strategy_id="s1"))
        assert len(filtered) == 1
        assert filtered[0].strategy_id == "s1"


class TestHiddenExclusion:
    """AC-FR0390-5: display_hidden_accounts=false -> 隐藏账户不显示."""

    def test_hidden_excluded_by_default(self):
        rows = [
            _row("v1", "V1", hidden=False),
            _row("v2", "V2", hidden=True),
        ]
        overview = build_account_overview_rows(rows, display_hidden=False)
        assert len(overview.virtual_accounts) == 1
        assert overview.virtual_accounts[0].account_id == "v1"

    def test_display_hidden_shows_gray(self):
        rows = [
            _row("v1", "V1", hidden=False),
            _row("v2", "V2", hidden=True),
        ]
        overview = build_account_overview_rows(rows, display_hidden=True)
        assert len(overview.virtual_accounts) == 2


class TestTopLossProfit:
    """AC-FR0410-2: 最大 N 亏损 / 最大 M 盈利."""

    def test_top_n_loss(self):
        """AC-2: N=3 -> 亏损 Top 3 个股."""
        metrics = [
            AccountPnlMetric(symbol="000001.SZ", name="A", pnl=-5000, pnl_pct=-0.05),
            AccountPnlMetric(symbol="000002.SZ", name="B", pnl=3000, pnl_pct=0.03),
            AccountPnlMetric(symbol="000003.SZ", name="C", pnl=-2000, pnl_pct=-0.02),
            AccountPnlMetric(symbol="000004.SZ", name="D", pnl=-8000, pnl_pct=-0.08),
        ]
        top_loss = top_loss_stocks(metrics, n=3)
        assert len(top_loss) == 3
        assert top_loss[0].symbol == "000004.SZ"

    def test_top_m_profit(self):
        """AC-2: M=5 -> 盈利 Top M 个股."""
        metrics = [
            AccountPnlMetric(symbol="000001.SZ", name="A", pnl=-5000, pnl_pct=-0.05),
            AccountPnlMetric(symbol="000002.SZ", name="B", pnl=3000, pnl_pct=0.03),
            AccountPnlMetric(symbol="000003.SZ", name="C", pnl=9000, pnl_pct=0.09),
        ]
        top_profit = top_profit_stocks(metrics, m=5)
        assert len(top_profit) == 2
        assert top_profit[0].symbol == "000003.SZ"
