"""交易端口抽象."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

from quantide.core.enums import BidType, OrderSide

if TYPE_CHECKING:
    from quantide.data.sqlite import Trade

OrderStyle = Literal["shares", "amount", "percent", "target_pct"]


@dataclass
class OrderRequest:
    """统一下单请求."""

    asset: str
    side: OrderSide
    value: float
    style: OrderStyle = "shares"
    price: float = 0.0
    bid_type: BidType = BidType.MARKET
    order_time: datetime.datetime | None = None
    timeout: float = 0.5
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionView:
    """持仓视图."""

    asset: str
    shares: float
    avail: float
    price: float
    mv: float
    dt: datetime.date


@dataclass
class AssetView:
    """资产视图."""

    cash: float
    total: float
    market_value: float
    frozen_cash: float
    principal: float
    dt: datetime.date


@dataclass
class OrderView:
    """订单视图."""

    order_id: str
    asset: str
    side: str
    shares: float
    price: float
    status: str
    tm: datetime.datetime
    filled: float = 0.0
    error: str = ""


@dataclass
class OrderAck:
    """下单响应."""

    qt_oid: str | None
    status: str
    trades: list[Trade] = field(default_factory=list)
    message: str = ""

    @property
    def order_id(self) -> str | None:
        """兼容别名."""
        return self.qt_oid


@dataclass
class ExecutionResult:
    """高阶交易语义的统一返回值."""

    qt_oid: str | None
    trades: list[Trade] = field(default_factory=list)
    status: str = "submitted"
    message: str = ""

    @property
    def order_id(self) -> str | None:
        """兼容旧返回值字段名."""
        return self.qt_oid

    @classmethod
    def empty(cls) -> ExecutionResult:
        """返回空交易结果."""
        return cls(qt_oid=None, trades=[])


@dataclass
class CancelAck:
    """撤单响应."""

    success: bool
    message: str = ""


class BrokerPort(Protocol):
    """交易端口."""

    def record(
        self,
        key: str,
        value: float,
        dt: datetime.datetime | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """记录策略运行数据."""
        ...

    async def submit(self, request: OrderRequest) -> OrderAck:
        """提交订单."""
        ...

    async def buy(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """按股数买入."""
        ...

    async def buy_percent(
        self,
        asset: str,
        percent: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """按比例买入."""
        ...

    async def buy_amount(
        self,
        asset: str,
        amount: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """按金额买入."""
        ...

    async def sell(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """按股数卖出."""
        ...

    async def sell_percent(
        self,
        asset: str,
        percent: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """按比例卖出."""
        ...

    async def sell_amount(
        self,
        asset: str,
        amount: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """按金额卖出."""
        ...

    async def trade_target_pct(
        self,
        asset: str,
        target_pct: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """调整目标仓位占比."""
        ...

    async def cancel(self, order_id: str) -> CancelAck:
        """撤销订单."""
        ...

    async def cancel_all(self, side: OrderSide | None = None) -> int:
        """撤销全部订单."""
        ...

    def query_positions(self) -> list[PositionView]:
        """查询持仓."""
        ...

    def query_assets(self) -> AssetView | None:
        """查询资产."""
        ...

    def query_orders(self, status: str | None = None) -> list[OrderView]:
        """查询订单."""
        ...

    def query_trades(self, order_id: str | None = None) -> list[Trade]:
        """查询成交."""
        ...
