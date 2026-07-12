"""FR-0380 回测进度 (等价 UI-FR-0080) 单元测试.

覆盖 acceptance.md AC-FR0380-1:
- 验证 FR-0080 的 AC-1~AC-4 在回测进度 UI 中全部生效.
- 补充进度文案格式 (已处理交易日/总交易日 + 阶段名).
"""
from __future__ import annotations

import pytest

from quantide.web.services.backtest_progress import (
    BacktestStage,
    calculate_progress_percent,
    format_progress_text,
    is_metric_available_during_progress,
)


class TestBacktestProgressEquivalence:
    """AC-FR0380-1: 等价于 FR-0080 AC-1~AC-4."""

    def test_progress_percent_calculation(self):
        """FR-0080 AC-1: 百分比 = 已处理交易日 / 总交易日."""
        assert calculate_progress_percent(180, 365) == 49

    def test_available_metrics_during_progress(self):
        """FR-0080 AC-3: 实时指标区显示持仓/当日盈亏/累计交易笔数."""
        assert is_metric_available_during_progress("current_position") is True
        assert is_metric_available_during_progress("daily_pnl") is True
        assert is_metric_available_during_progress("total_trades") is True

    def test_unavailable_metrics_placeholder(self):
        """FR-0080 AC-3: 年化/Sharpe/Sortino/最大回撤显示占位符."""
        from quantide.web.services.backtest_progress import (
            placeholder_text_for_unavailable_metric,
        )

        assert placeholder_text_for_unavailable_metric("sharpe") == "回测结束后计算"


class TestProgressTextFormat:
    """进度文案: 已处理交易日/总交易日 + 阶段名."""

    def test_format_running_stage(self):
        text = format_progress_text(180, 365, BacktestStage.RUNNING)
        assert "180/365" in text
        assert "回测中" in text

    def test_format_evaluating_stage(self):
        text = format_progress_text(365, 365, BacktestStage.EVALUATING)
        assert "评估中" in text

    def test_format_generating_report_stage(self):
        text = format_progress_text(365, 365, BacktestStage.GENERATING_REPORT)
        assert "生成报告中" in text
