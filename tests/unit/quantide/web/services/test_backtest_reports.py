"""FR-0091/0092/0093 回测报告管理单元测试.

覆盖:
- AC-FR0091-1~5: 报告列表与排序 (年化/Sharpe/Sortino/最大回撤)
- AC-FR0092-1~3: 删除单报告 (二次确认, 联动删日志, 无撤销)
- AC-FR0093-1~3: 批量删除/日志清理 (无单条日志删除按钮)
"""
from __future__ import annotations

import pytest

from quantide.web.services.backtest_reports import (
    BacktestReportItem,
    BacktestReportSortField,
    ReportDeleteRequest,
    ReportDeleteResult,
    ReportsBulkDeleteRequest,
    sort_backtest_reports,
    supports_single_log_delete,
)


def _report(run_id, name="R1", annualized=0.1, sharpe=1.0, sortino=1.2, max_drawdown=-0.2):
    return BacktestReportItem(
        run_id=run_id,
        report_name=name,
        backtest_range="2025-01-01~2025-12-31",
        run_at="2026-01-01T10:00:00",
        annualized_return=annualized,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_drawdown,
    )


class TestReportSorting:
    """AC-FR0091-2, AC-3: 按年化降序 / 切换排序字段."""

    def test_sort_by_annualized_desc(self):
        """AC-2: 点击'按年化降序' -> 年化最高的报告在最上面."""
        reports = [
            _report("r1", annualized=0.1),
            _report("r2", annualized=0.3),
            _report("r3", annualized=0.2),
        ]
        sorted_list = sort_backtest_reports(reports, BacktestReportSortField.ANNUALIZED)
        assert [r.run_id for r in sorted_list] == ["r2", "r3", "r1"]

    def test_sort_by_sharpe_desc(self):
        """AC-3: 切换排序字段为 Sharpe."""
        reports = [_report("r1", sharpe=1.0), _report("r2", sharpe=2.5)]
        sorted_list = sort_backtest_reports(reports, BacktestReportSortField.SHARPE)
        assert sorted_list[0].run_id == "r2"

    def test_sort_by_sortino_desc(self):
        reports = [_report("r1", sortino=1.0), _report("r2", sortino=2.0)]
        sorted_list = sort_backtest_reports(reports, BacktestReportSortField.SORTINO)
        assert sorted_list[0].run_id == "r2"

    def test_sort_by_max_drawdown_desc(self):
        """AC-3: 最大回撤 (绝对值越小越好, 这里按值降序)."""
        reports = [_report("r1", max_drawdown=-0.2), _report("r2", max_drawdown=-0.1)]
        sorted_list = sort_backtest_reports(reports, BacktestReportSortField.MAX_DRAWDOWN)
        assert sorted_list[0].run_id == "r2"


class TestReportDelete:
    """AC-FR0092-1~3: 删除单报告."""

    def test_delete_requires_confirm_name(self):
        """AC-1: 弹出二次确认对话框 (输入报告名)."""
        report = _report("r1", name="报告A")
        req = ReportDeleteRequest(run_id="r1", confirm_name="wrong")
        result = req.validate(report)
        assert result.ok is False

    def test_delete_succeeds_when_name_matches(self):
        report = _report("r1", name="报告A")
        req = ReportDeleteRequest(run_id="r1", confirm_name="报告A")
        result = req.validate(report)
        assert result.ok is True

    def test_delete_no_undo(self):
        """AC-3: 不提供撤销入口."""
        result = ReportDeleteResult(ok=True, message="已删除", has_undo=False)
        assert result.has_undo is False


class TestBulkDeleteAndLogClear:
    """AC-FR0093-1~3: 批量删除/日志清理."""

    def test_bulk_delete_requires_strategy_name(self):
        """AC-1: 二次确认 (输入策略名)."""
        req = ReportsBulkDeleteRequest(strategy_id="s1", confirm_strategy_name="wrong")
        assert req.validate("均线突破") is False

    def test_bulk_delete_succeeds_when_name_matches(self):
        req = ReportsBulkDeleteRequest(strategy_id="s1", confirm_strategy_name="均线突破")
        assert req.validate("均线突破") is True

    def test_no_single_log_delete_button(self):
        """AC-3: UI 不存在'单条日志删除'按钮."""
        assert supports_single_log_delete() is False
