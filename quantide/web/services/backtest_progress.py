"""FR-0080 回测进度可视化服务.

定义回测进度状态、阶段、实时指标可见性与每日持仓过滤规则.

AC-1: 进度百分比 = 已处理交易日 / 总交易日.
AC-3: 实时指标区显示持仓/当日盈亏/累计交易笔数; 年化/Sharpe/Sortino/最大回撤/Calmar 显示占位符.
AC-10: 空仓日不省略, 显示'当日无持仓'.
AC-11: 每日持仓 tab 支持按个股代码过滤.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BacktestStage(str, Enum):
    """回测阶段 (AC-FR0080-3, NFR-0060 AC-5c).

    RUNNING: 回测中.
    EVALUATING: 评估中.
    GENERATING_REPORT: 生成报告中.
    """

    RUNNING = "running"
    EVALUATING = "evaluating"
    GENERATING_REPORT = "generating_report"


_METRICS_AVAILABLE_DURING_PROGRESS: frozenset[str] = frozenset(
    {"current_position", "daily_pnl", "total_trades"}
)

_PLACEHOLDER_TEXT = "回测结束后计算"


@dataclass
class BacktestProgressState:
    """回测进度状态.

    Attributes:
        processed_days: 已处理交易日.
        total_days: 总交易日.
        stage: 当前阶段.
        current_position: 当前持仓 (AC-3 实时指标).
        daily_pnl: 当日盈亏 (AC-3 实时指标).
        total_trades: 累计交易笔数 (AC-3 实时指标).
    """

    processed_days: int
    total_days: int
    stage: BacktestStage
    current_position: float
    daily_pnl: float
    total_trades: int


@dataclass
class DailyPositionRow:
    """每日持仓行 (AC-FR0080-8).

    Attributes:
        date: 日期.
        symbol: 个股代码.
        name: 个股名称.
        shares: 数量.
        cost_price: 成本价.
        close_price: 收盘价.
        market_value: 持仓市值.
        floating_pnl: 浮动盈亏.
    """

    date: str
    symbol: str
    name: str
    shares: int
    cost_price: float
    close_price: float
    market_value: float
    floating_pnl: float


def calculate_progress_percent(processed_days: int, total_days: int) -> int:
    """AC-1: 计算进度百分比.

    Args:
        processed_days: 已处理交易日.
        total_days: 总交易日.

    Returns:
        百分比 (0-100 整数).
    """
    if total_days <= 0:
        return 0
    return int(processed_days / total_days * 100)


def is_metric_available_during_progress(metric: str) -> bool:
    """AC-3: 判断指标在回测进度阶段是否可见.

    Args:
        metric: 指标名.

    Returns:
        True 当指标为持仓/当日盈亏/累计交易笔数.
    """
    return metric in _METRICS_AVAILABLE_DURING_PROGRESS


def placeholder_text_for_unavailable_metric(metric: str) -> str:
    """AC-3: 不可见指标的占位符文案.

    Args:
        metric: 指标名.

    Returns:
        '回测结束后计算'.
    """
    if is_metric_available_during_progress(metric):
        return ""
    return _PLACEHOLDER_TEXT


def should_keep_empty_position_day(positions: list) -> bool:
    """AC-10: 空仓日不省略, 仍出现在列表中.

    Args:
        positions: 当日持仓列表.

    Returns:
        始终 True (空仓日保留).
    """
    return True


def filter_positions_by_symbol(
    rows: list[DailyPositionRow],
    symbol: str,
) -> list[DailyPositionRow]:
    """AC-11: 按个股代码过滤每日持仓.

    Args:
        rows: 每日持仓行列表.
        symbol: 个股代码.

    Returns:
        仅含指定个股的行.
    """
    return [r for r in rows if r.symbol == symbol]


_STAGE_LABELS: dict[BacktestStage, str] = {
    BacktestStage.RUNNING: "回测中",
    BacktestStage.EVALUATING: "评估中",
    BacktestStage.GENERATING_REPORT: "生成报告中",
}


def format_progress_text(
    processed_days: int,
    total_days: int,
    stage: BacktestStage,
) -> str:
    """FR-0380 / NFR-0060 AC-5c: 进度文案.

    格式: "已处理交易日/总交易日 天 · 阶段名".

    Args:
        processed_days: 已处理交易日.
        total_days: 总交易日.
        stage: 当前阶段.

    Returns:
        进度文案.
    """
    return f"{processed_days}/{total_days} 天 · {_STAGE_LABELS[stage]}"


__all__ = [
    "BacktestProgressState",
    "BacktestStage",
    "DailyPositionRow",
    "calculate_progress_percent",
    "filter_positions_by_symbol",
    "format_progress_text",
    "is_metric_available_during_progress",
    "placeholder_text_for_unavailable_metric",
    "should_keep_empty_position_day",
]
