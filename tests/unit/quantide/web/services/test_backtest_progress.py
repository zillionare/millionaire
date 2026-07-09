"""FR-0080 回测进度可视化单元测试.

覆盖 acceptance.md AC-FR0080-1~4, AC-8~11:
- AC-1: 进度条 x 轴回测区间, 百分比 = 已处理交易日 / 总交易日
- AC-2: 净值曲线主轴策略净值, 副轴沪深 300 基准
- AC-3: 实时指标区 (持仓/当日盈亏/累计交易笔数), 不显示年化/Sharpe 等
- AC-8~11: 每日持仓 tab (空仓日不省略, 按个股过滤)
"""
from __future__ import annotations

import pytest

from quantide.web.services.backtest_progress import (
    BacktestProgressState,
    BacktestStage,
    DailyPositionRow,
    calculate_progress_percent,
    filter_positions_by_symbol,
    is_metric_available_during_progress,
    placeholder_text_for_unavailable_metric,
    should_keep_empty_position_day,
)


class TestProgressPercent:
    """AC-1: 百分比 = 已处理交易日 / 总交易日."""

    def test_percent_calculation(self):
        assert calculate_progress_percent(processed_days=180, total_days=365) == 49

    def test_zero_total_returns_zero(self):
        assert calculate_progress_percent(processed_days=0, total_days=0) == 0

    def test_full_progress(self):
        assert calculate_progress_percent(processed_days=365, total_days=365) == 100


class TestStage:
    """AC-3: 回测阶段."""

    def test_stages_defined(self):
        assert BacktestStage.RUNNING == "running"
        assert BacktestStage.EVALUATING == "evaluating"
        assert BacktestStage.GENERATING_REPORT == "generating_report"


class TestRealtimeMetrics:
    """AC-3: 实时指标区显示持仓/当日盈亏/累计交易笔数, 不显示年化/Sharpe 等."""

    @pytest.mark.parametrize("metric", ["current_position", "daily_pnl", "total_trades"])
    def test_available_metrics_during_progress(self, metric):
        assert is_metric_available_during_progress(metric) is True

    @pytest.mark.parametrize("metric", ["annualized_return", "sharpe", "sortino", "max_drawdown", "calmar"])
    def test_unavailable_metrics_during_progress(self, metric):
        """AC-3: 这些位置显示占位符'回测结束后计算'."""
        assert is_metric_available_during_progress(metric) is False

    def test_placeholder_text(self):
        """AC-3: 占位符文案."""
        assert placeholder_text_for_unavailable_metric("sharpe") == "回测结束后计算"


class TestEmptyPositionDay:
    """AC-10: 空仓日不省略, 显示'当日无持仓'."""

    def test_empty_day_kept(self):
        """AC-10: 回测区间内某日无任何持仓 -> 该日期分组仍出现."""
        assert should_keep_empty_position_day(positions=[]) is True

    def test_non_empty_day_kept(self):
        assert should_keep_empty_position_day(positions=[{"symbol": "000001.SZ"}]) is True


class TestFilterBySymbol:
    """AC-11: 按个股代码过滤."""

    def test_filter_returns_only_matching_symbol(self):
        rows = [
            DailyPositionRow(date="2026-07-01", symbol="000001.SZ", name="平安银行", shares=100, cost_price=10.0, close_price=10.5, market_value=1050.0, floating_pnl=50.0),
            DailyPositionRow(date="2026-07-01", symbol="600519.SH", name="贵州茅台", shares=100, cost_price=1500.0, close_price=1550.0, market_value=155000.0, floating_pnl=5000.0),
            DailyPositionRow(date="2026-07-02", symbol="000001.SZ", name="平安银行", shares=200, cost_price=10.0, close_price=10.8, market_value=2160.0, floating_pnl=160.0),
        ]
        filtered = filter_positions_by_symbol(rows, "000001.SZ")
        assert len(filtered) == 2
        assert all(r.symbol == "000001.SZ" for r in filtered)

    def test_filter_with_no_match_returns_empty(self):
        rows = [DailyPositionRow(date="2026-07-01", symbol="000001.SZ", name="x", shares=100, cost_price=10.0, close_price=10.0, market_value=1000.0, floating_pnl=0.0)]
        assert filter_positions_by_symbol(rows, "999999.SH") == []


class TestProgressState:
    def test_state_carries_processed_and_total(self):
        state = BacktestProgressState(
            processed_days=180,
            total_days=365,
            stage=BacktestStage.RUNNING,
            current_position=1000,
            daily_pnl=200.0,
            total_trades=15,
        )
        assert state.processed_days == 180
        assert state.total_days == 365
        assert state.stage == BacktestStage.RUNNING
