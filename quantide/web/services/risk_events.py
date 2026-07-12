"""FR-0070 风控触发事件详情服务.

定义风控事件 schema、超额收益窗口校验与 reason 分组规则.

AC-1: 事件列表字段 (时间戳/标的/触发价/成本价/原因/超额收益).
AC-2: 超额收益 N 日窗口未关闭显示'计算中...'.
AC-3: 触发原因分布饼图按 reason 分组.
AC-4: 超额收益窗口 N 日 (默认 0, 范围 0~30 含边界).
AC-5, AC-6: N 字段仅在创建实例时配置, 列表页/曲线页无配置入口.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum


class RiskEventReason(str, Enum):
    """风控触发原因."""

    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"


@dataclass
class RiskEventItem:
    """风控事件条目 (AC-FR0070-1).

    Attributes:
        event_id: 事件 ID.
        timestamp: 时间戳.
        symbol: 标的.
        trigger_price: 触发价.
        cost_price: 成本价.
        reason: 触发原因.
        excess_return: 超额收益 (None 表示未计算).
        window_closed: N 日窗口是否已关闭.
    """

    event_id: str
    timestamp: str
    symbol: str
    trigger_price: float
    cost_price: float
    reason: RiskEventReason
    excess_return: float | None
    window_closed: bool


@dataclass
class ExcessReturnWindowConfig:
    """AC-4: 超额收益窗口 N 日配置.

    Attributes:
        days: N 日窗口 (默认 0, 范围 0~30 含边界).
    """

    days: int = 0


def is_excess_return_pending(event: RiskEventItem) -> bool:
    """AC-2: 判断超额收益是否处于'计算中...'状态.

    N 日窗口未关闭且尚未计算时显示占位.

    Args:
        event: 风控事件.

    Returns:
        True 当窗口未关闭且 excess_return 为 None.
    """
    return event.window_closed is False and event.excess_return is None


def group_risk_events_by_reason(
    events: list[RiskEventItem],
) -> dict[RiskEventReason, list[RiskEventItem]]:
    """AC-3: 按 reason 分组风控事件.

    Args:
        events: 风控事件列表.

    Returns:
        按 reason 分组的字典.
    """
    groups: dict[RiskEventReason, list[RiskEventItem]] = defaultdict(list)
    for event in events:
        groups[event.reason].append(event)
    return dict(groups)


def validate_excess_return_window(days: int) -> bool:
    """AC-4: 校验超额收益窗口 N 日.

    Args:
        days: N 日窗口.

    Returns:
        True 当 0 <= days <= 30.

    Raises:
        ValueError: 当 days 越界.
    """
    if not (0 <= days <= 30):
        raise ValueError("超额收益窗口 N 日必须在 0~30 (含边界)")
    return True


__all__ = [
    "ExcessReturnWindowConfig",
    "RiskEventItem",
    "RiskEventReason",
    "group_risk_events_by_reason",
    "is_excess_return_pending",
    "validate_excess_return_window",
]
