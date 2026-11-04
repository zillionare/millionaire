"""基于正式 BrokerPort 的兼容句柄。"""

import datetime
from typing import Any, cast

import polars as pl

from quantide.core.enums import BidType, BrokerKind, OrderSide, OrderStatus
from quantide.core.order_values import coerce_order_side, coerce_order_status
from quantide.core.ports import BrokerPort, CancelAck, ExecutionResult
from quantide.data.models import Asset, Order, Position


class PortBackedBroker:
    """将正式 BrokerPort 暴露为 UI/过渡层可消费的 broker 句柄。"""

    def __init__(
        self,
        port: BrokerPort,
        portfolio_id: str,
        kind: BrokerKind | str,
        portfolio_name: str = "",
        status: bool = True,
        is_connected: bool | None = None,
    ) -> None:
        self._port = port
        self._portfolio_id = portfolio_id
        self._kind = kind if isinstance(kind, BrokerKind) else BrokerKind(kind)
        self._portfolio_name = portfolio_name or portfolio_id
        self._status = status
        self._is_connected = status if is_connected is None else is_connected

    @property
    def port(self) -> BrokerPort:
        """返回正式 broker port。"""
        return self._port

    @property
    def portfolio_id(self) -> str:
        return self._portfolio_id

    @property
    def portfolio_name(self) -> str:
        return self._portfolio_name

    @property
    def kind(self) -> BrokerKind:
        return self._kind

    @property
    def status(self) -> bool:
        return self._status

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def asset(self) -> Asset:
        view = self._port.query_assets()
        if view is not None:
            return Asset(
                portfolio_id=self._portfolio_id,
                dt=view.dt,
                principal=view.principal,
                cash=view.cash,
                frozen_cash=view.frozen_cash,
                market_value=view.market_value,
                total=view.total,
            )
        return Asset(
            portfolio_id=self._portfolio_id,
            dt=datetime.date.today(),
            principal=0.0,
            cash=0.0,
            frozen_cash=0.0,
            market_value=0.0,
            total=0.0,
        )

    @property
    def cash(self) -> float:
        return float(self.asset.cash)

    @property
    def principal(self) -> float:
        return float(self.asset.principal)

    @property
    def total_assets(self) -> float:
        return float(self.asset.total)

    @property
    def positions(self) -> dict[str, Position]:
        views = list(self._port.query_positions())
        prices: dict[str, float] = {}
        if views:
            try:
                raw_prices = self.get_prices([view.asset for view in views])
                if isinstance(raw_prices, dict):
                    prices = raw_prices
            except Exception:
                prices = {}
        result: dict[str, Position] = {}
        for view in views:
            shares = float(view.shares)
            cost = shares * float(view.price)
            price = float(prices.get(view.asset) or 0)
            mv = shares * price if price > 0 else float(view.mv)
            profit = mv - cost if shares > 0 else 0.0
            result[view.asset] = Position(
                portfolio_id=self._portfolio_id,
                dt=view.dt,
                asset=view.asset,
                shares=shares,
                avail=view.avail,
                price=view.price,
                profit=profit,
                mv=mv,
            )
        return result

    def get_bars_range(
        self,
        assets: list[str] | None,
        start_dt: datetime.datetime | datetime.date,
        end_dt: datetime.datetime | datetime.date | None = None,
        adjust: str | None = None,
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        """把批量行情请求转发给底层 broker（PaperBroker 等）。"""
        handler = getattr(self._port, "get_bars_range", None)
        if not callable(handler):
            raise AttributeError("底层 broker 不支持 get_bars_range")
        return cast(
            pl.DataFrame,
            handler(
                assets,
                start_dt,
                end_dt,
                adjust=adjust,
                include_forming_bar=include_forming_bar,
            ),
        )

    def get_history(
        self,
        asset: str,
        count: int,
        end_dt: datetime.datetime | None = None,
        frame_type: str = "1d",
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        """把单标的历史行情请求转发给底层 broker。"""
        handler = getattr(self._port, "get_history", None)
        if not callable(handler):
            raise AttributeError("底层 broker 不支持 get_history")
        return cast(
            pl.DataFrame,
            handler(
                asset,
                count,
                end_dt,
                frame_type,
                include_forming_bar=include_forming_bar,
            ),
        )

    def get_prices(self, assets: list[str]) -> dict[str, float]:
        getter = getattr(self._port, "get_prices", None)
        if callable(getter):
            return cast(dict[str, float], getter(assets))
        result: dict[str, float] = {}
        requested = set(assets)
        for pos in self._port.query_positions():
            if pos.asset in requested and pos.shares > 0 and pos.mv > 0:
                result[pos.asset] = pos.mv / pos.shares
        return result

    @property
    def orders(self) -> list[Order]:
        return [self._to_order(row) for row in self._port.query_orders()]

    def record(
        self,
        key: str,
        value: float,
        dt: datetime.datetime | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._port.record(key, value, dt=dt, extra=extra)

    def set_clock(self, now: datetime.datetime) -> None:
        """设置底层 broker 时钟 (paper/live 策略循环用)."""
        broker = getattr(self._port, "_broker", None)
        if broker is not None and hasattr(broker, "set_clock"):
            broker.set_clock(now)

    async def buy(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        return await self._port.buy(
            asset=asset,
            shares=shares,
            price=price,
            order_time=order_time,
            timeout=timeout,
            **kwargs,
        )

    async def buy_percent(
        self,
        asset: str,
        percent: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        return await self._port.buy_percent(
            asset=asset,
            percent=percent,
            price=price,
            order_time=order_time,
            timeout=timeout,
            **kwargs,
        )

    async def buy_amount(
        self,
        asset: str,
        amount: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        return await self._port.buy_amount(
            asset=asset,
            amount=amount,
            price=price,
            order_time=order_time,
            timeout=timeout,
            **kwargs,
        )

    async def sell(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        return await self._port.sell(
            asset=asset,
            shares=shares,
            price=price,
            order_time=order_time,
            timeout=timeout,
            **kwargs,
        )

    async def sell_percent(
        self,
        asset: str,
        percent: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        return await self._port.sell_percent(
            asset=asset,
            percent=percent,
            price=price,
            order_time=order_time,
            timeout=timeout,
            **kwargs,
        )

    async def sell_amount(
        self,
        asset: str,
        amount: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        return await self._port.sell_amount(
            asset=asset,
            amount=amount,
            price=price,
            order_time=order_time,
            timeout=timeout,
            **kwargs,
        )

    async def trade_target_pct(
        self,
        asset: str,
        target_pct: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        return await self._port.trade_target_pct(
            asset=asset,
            target_pct=target_pct,
            price=price,
            order_time=order_time,
            timeout=timeout,
            **kwargs,
        )

    async def cancel_order(self, qt_oid: str) -> CancelAck:
        return await self._port.cancel(qt_oid)

    async def cancel_all_orders(self, side: OrderSide | None = None) -> int:
        return await self._port.cancel_all(side=side)

    def get_position(self, asset: str, date: datetime.date | None = None) -> Position | None:
        _ = date
        return self.positions.get(asset)

    def _to_order(self, row: Any) -> Order:
        return Order(
            portfolio_id=self._portfolio_id,
            asset=str(row.asset),
            side=self._to_side(row.side),
            shares=float(row.shares),
            bid_type=BidType.UNKNOWN,
            tm=row.tm,
            price=float(row.price),
            filled=float(row.filled),
            qtoid=str(row.order_id),
            status=self._to_status(row.status),
            error=str(getattr(row, "error", "") or ""),
        )

    def _to_side(self, value: Any) -> OrderSide:
        return coerce_order_side(value)

    def _to_status(self, value: Any) -> OrderStatus:
        return coerce_order_status(value)
