"""FR-0400 委托成交记录 + FR-0430 仿真交易服务.

定义委托/成交记录 schema、三态 (回测/paper/live) tab 过滤与组合筛选规则.

AC-FR0400-1: tab 切换 回测/paper/live.
AC-FR0400-2: 委托记录按 策略/个股/时间段 组合筛选 (三者均可留空).
AC-FR0400-3: 成交记录列表 (策略/个股/时间段/成交价/成交量/成交时间).
AC-FR0430-2: 仿真交易界面无'下单辅助'区块.
AC-FR0430-3: 仿真提供'补单'入口, 流程与实盘下单表单一致.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HistoryRecordType(str, Enum):
    """记录类型."""

    ORDER = "order"
    TRADE = "trade"


@dataclass
class HistoryRecord:
    """委托/成交记录.

    Attributes:
        record_id: 记录 ID.
        record_type: 记录类型 (委托/成交).
        mode: 回测/paper/live.
        strategy_id: 策略 ID.
        symbol: 个股代码.
        timestamp: 时间.
        price: 价格.
        quantity: 数量.
        status: 状态.
    """

    record_id: str
    record_type: HistoryRecordType
    mode: str
    strategy_id: str
    symbol: str
    timestamp: str
    price: float
    quantity: int
    status: str


@dataclass
class HistoryFilter:
    """历史记录筛选条件 (AC-FR0400-2).

    Attributes:
        mode: 模式过滤 (None 表示不限定).
        strategy_id: 策略过滤 (None 表示不限定).
        symbol: 个股过滤 (None 表示不限定).
        date_from: 起始日期 (None 表示不限定).
        date_to: 结束日期 (None 表示不限定).
    """

    mode: str | None
    strategy_id: str | None
    symbol: str | None
    date_from: str | None
    date_to: str | None


def filter_history_records(
    records: list[HistoryRecord],
    flt: HistoryFilter,
) -> list[HistoryRecord]:
    """AC-FR0400-2, AC-3: 按组合条件筛选委托/成交记录.

    三者 (策略/个股/时间段) 均可留空表示不限定.

    Args:
        records: 全部记录.
        flt: 筛选条件.

    Returns:
        筛选后的记录列表.
    """
    result = list(records)
    if flt.mode:
        result = [r for r in result if r.mode == flt.mode]
    if flt.strategy_id:
        result = [r for r in result if r.strategy_id == flt.strategy_id]
    if flt.symbol:
        result = [r for r in result if r.symbol == flt.symbol]
    if flt.date_from:
        result = [r for r in result if r.timestamp >= flt.date_from]
    if flt.date_to:
        result = [r for r in result if r.timestamp <= flt.date_to + "T23:59:59"]
    return result


def has_trade_assist_in_paper() -> bool:
    """AC-FR0430-2: 仿真交易界面无'下单辅助'区块.

    无参考价切换、无可卖数量计算、无双击持仓带入.

    Returns:
        始终 False (仿真无下单辅助).
    """
    return False


def supports_makeup_order(mode: str) -> bool:
    """AC-FR0430-3: 判断模式是否支持'补单'入口.

    仿真提供补单入口 (防止自动化失败); 回测无补单.

    Args:
        mode: 运行模式.

    Returns:
        True 当模式为 paper.
    """
    return mode == "paper"


__all__ = [
    "HistoryFilter",
    "HistoryRecord",
    "HistoryRecordType",
    "filter_history_records",
    "has_trade_assist_in_paper",
    "supports_makeup_order",
]
