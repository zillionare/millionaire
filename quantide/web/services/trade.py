"""FR-0420 实盘交易订单校验服务.

定义 OrderRequest / OrderResponse schema (interfaces.md §4.3) 与下单校验规则:
- 风控策略不可作为手动交易目标 (AC-11)
- 卖出可卖数量 = 持仓 - 已挂单 (AC-4)
- 金额反算股数 = floor(amount / price / 100) * 100 (AC-6)
- 数量必须 100 股整数倍
- 限价单价格必填, 市价单价格可空 (AC-12)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class OrderSide(str, Enum):
    """委托方向."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """委托方式."""

    LIMIT = "limit"
    MARKET = "market"


class PriceSource(str, Enum):
    """价格来源 (interfaces.md §4.3)."""

    PREV_CLOSE = "prev_close"
    REALTIME = "realtime"
    MA5 = "ma5"
    MA10 = "ma10"
    LIMIT_UP = "limit_up"
    LIMIT_DOWN = "limit_down"
    MANUAL = "manual"


@dataclass
class OrderRequest:
    """下单请求 (interfaces.md §4.3).

    Attributes:
        mode: paper / live.
        strategy_id: 目标策略 ID (风控策略不可作为目标).
        strategy_type: 策略类型 (day / live / risk), 用于风控判定.
        account_id: 归属账户.
        symbol: 证券代码.
        side: buy / sell.
        quantity: 100 股整数倍.
        price: 委托价; 市价可空.
        price_source: 价格来源.
        order_type: limit / market.
    """

    mode: str
    strategy_id: str
    strategy_type: str
    account_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float | None
    price_source: PriceSource
    order_type: OrderType


class OrderValidationError(ValueError):
    """下单校验错误."""


def is_risk_strategy_target(strategy_type: str) -> bool:
    """AC-11: 判定目标策略是否为风控策略.

    Args:
        strategy_type: 策略类型 (day / live / risk).

    Returns:
        True 当策略类型为 risk (不可作为手动交易目标).
    """
    return strategy_type == "risk"


def calculate_sellable_quantity(position: int, pending_orders: int) -> int:
    """AC-4: 计算卖出可卖数量.

    可卖数量 = 持仓 - 已挂单.

    Args:
        position: 当前持仓数量.
        pending_orders: 已挂单数量.

    Returns:
        可卖数量 (不低于 0).
    """
    return max(0, position - pending_orders)


def calculate_shares_from_amount(amount: float, price: float) -> int:
    """AC-6: 金额反算股数.

    股数 = floor(amount / price / 100) * 100 (100 股整数倍).

    Args:
        amount: 金额.
        price: 单价.

    Returns:
        股数 (100 股整数倍, 不足一手返回 0).
    """
    if price <= 0 or amount <= 0:
        return 0
    return math.floor(amount / price / 100) * 100


def validate_order_request(order: OrderRequest) -> bool:
    """校验下单请求 (AC-4, AC-9, AC-11, AC-12).

    Args:
        order: 待校验订单.

    Returns:
        True 当订单通过校验.

    Raises:
        OrderValidationError: 当任一校验失败, message 指明原因.
    """
    if not order.strategy_id:
        raise OrderValidationError("目标策略必选")
    if is_risk_strategy_target(order.strategy_type):
        raise OrderValidationError("风控策略不可作为手动交易目标")
    if not order.symbol:
        raise OrderValidationError("证券代码不能为空")
    if order.quantity <= 0:
        raise OrderValidationError("数量必须大于 0")
    if order.quantity % 100 != 0:
        raise OrderValidationError("数量必须为 100 股整数倍")
    if order.order_type == OrderType.LIMIT:
        if order.price is None or order.price <= 0:
            raise OrderValidationError("限价单委托价必须 > 0")
    elif order.price is not None and order.price < 0:
        raise OrderValidationError("委托价不能为负数")
    return True


__all__ = [
    "OrderRequest",
    "OrderSide",
    "OrderType",
    "OrderValidationError",
    "PriceSource",
    "calculate_sellable_quantity",
    "calculate_shares_from_amount",
    "is_risk_strategy_target",
    "validate_order_request",
]
