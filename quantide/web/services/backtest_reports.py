"""FR-0091/0092/0093 回测报告管理服务.

定义回测报告列表、排序字段、单报告删除与批量删除/日志清理规则.

AC-FR0091-2: 按年化降序; AC-3 切换 Sharpe/Sortino/最大回撤.
AC-FR0092-1: 删除单报告二次确认 (输入报告名).
AC-FR0092-2: 删除成功后关联日志文件一并删除.
AC-FR0092-3: 不提供撤销入口.
AC-FR0093-1: 批量删除二次确认 (输入策略名).
AC-FR0093-3: 无单条日志删除按钮 (要不全保留, 要不全清空).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BacktestReportSortField(str, Enum):
    """报告排序字段."""

    ANNUALIZED = "annualized"
    SHARPE = "sharpe"
    SORTINO = "sortino"
    MAX_DRAWDOWN = "max_drawdown"


@dataclass
class BacktestReportItem:
    """回测报告条目 (AC-FR0091-1).

    Attributes:
        run_id: 运行 ID.
        report_name: 报告名.
        backtest_range: 回测区间.
        run_at: 运行时间.
        annualized_return: 年化.
        sharpe: Sharpe.
        sortino: Sortino.
        max_drawdown: 最大回撤.
    """

    run_id: str
    report_name: str
    backtest_range: str
    run_at: str
    annualized_return: float
    sharpe: float
    sortino: float
    max_drawdown: float


@dataclass
class ReportDeleteRequest:
    """AC-FR0092-1: 单报告删除请求 (二次确认输入报告名).

    Attributes:
        run_id: 运行 ID.
        confirm_name: 用户输入的确认名称.
    """

    run_id: str
    confirm_name: str

    def validate(self, report: BacktestReportItem) -> ReportDeleteResult:
        """校验删除请求.

        Args:
            report: 目标报告.

        Returns:
            校验结果.
        """
        if self.confirm_name != report.report_name:
            return ReportDeleteResult(ok=False, message="报告名不匹配", has_undo=False)
        return ReportDeleteResult(ok=True, message="已删除", has_undo=False)


@dataclass
class ReportDeleteResult:
    """删除结果.

    Attributes:
        ok: 是否成功.
        message: 结果消息.
        has_undo: 是否提供撤销 (始终 False, AC-3).
    """

    ok: bool
    message: str
    has_undo: bool


@dataclass
class ReportsBulkDeleteRequest:
    """AC-FR0093-1: 批量删除请求 (二次确认输入策略名).

    Attributes:
        strategy_id: 策略 ID.
        confirm_strategy_name: 用户输入的确认策略名.
    """

    strategy_id: str
    confirm_strategy_name: str

    def validate(self, strategy_name: str) -> bool:
        """校验批量删除请求.

        Args:
            strategy_name: 目标策略名.

        Returns:
            True 当用户输入的名称与策略名匹配.
        """
        return self.confirm_strategy_name == strategy_name


def sort_backtest_reports(
    reports: list[BacktestReportItem],
    field: BacktestReportSortField,
) -> list[BacktestReportItem]:
    """AC-FR0091-2, AC-3: 按指定字段降序排序报告.

    Args:
        reports: 报告列表.
        field: 排序字段.

    Returns:
        排序后的列表 (该字段值最高/最优在前).
    """
    field_map = {
        BacktestReportSortField.ANNUALIZED: "annualized_return",
        BacktestReportSortField.SHARPE: "sharpe",
        BacktestReportSortField.SORTINO: "sortino",
        BacktestReportSortField.MAX_DRAWDOWN: "max_drawdown",
    }
    key = field_map[field]
    return sorted(reports, key=lambda r: getattr(r, key), reverse=True)


def supports_single_log_delete() -> bool:
    """AC-FR0093-3: UI 不存在'单条日志删除'按钮.

    Aaron 决策: 要不全保留, 要不全清空.

    Returns:
        始终 False.
    """
    return False


__all__ = [
    "BacktestReportItem",
    "BacktestReportSortField",
    "ReportDeleteRequest",
    "ReportDeleteResult",
    "ReportsBulkDeleteRequest",
    "sort_backtest_reports",
    "supports_single_log_delete",
]
