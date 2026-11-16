"""Typed high-level order helpers shared by gateway port and legacy facade."""

import datetime
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Protocol, cast

from quantide.core.enums import OrderSide
from quantide.core.ports import ExecutionResult, OrderRequest
from quantide.core.ports.broker import OrderStyle


class _MarkedPosition(Protocol):
    asset: str
    mv: float


class OrderConvenience:
    """Translate the public sizing methods to one implementation-owned dispatcher."""

    if TYPE_CHECKING:

        async def _submit_execution(
            self,
            asset: str,
            side: OrderSide,
            value: int | float,
            style: str,
            price: float,
            order_time: datetime.datetime | None,
            timeout: float,
            extra: dict[str, Any],
        ) -> ExecutionResult: ...

    async def buy(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """Submit a buy sized by shares."""
        return await self._submit_execution(
            asset, OrderSide.BUY, shares, "shares", float(price), order_time, timeout, kwargs
        )

    async def buy_percent(
        self,
        asset: str,
        percent: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """Submit a buy sized by percent."""
        return await self._submit_execution(
            asset, OrderSide.BUY, percent, "percent", float(price), order_time, timeout, kwargs
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
        """Submit a buy sized by amount."""
        return await self._submit_execution(
            asset, OrderSide.BUY, amount, "amount", float(price), order_time, timeout, kwargs
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
        """Submit a sell sized by shares."""
        return await self._submit_execution(
            asset, OrderSide.SELL, shares, "shares", float(price), order_time, timeout, kwargs
        )

    async def sell_percent(
        self,
        asset: str,
        percent: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """Submit a sell sized by percent."""
        return await self._submit_execution(
            asset, OrderSide.SELL, percent, "percent", float(price), order_time, timeout, kwargs
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
        """Submit a sell sized by amount."""
        return await self._submit_execution(
            asset, OrderSide.SELL, amount, "amount", float(price), order_time, timeout, kwargs
        )


def execution_request(
    asset: str,
    side: OrderSide,
    value: int | float,
    style: str,
    price: float,
    order_time: datetime.datetime | None,
    timeout: float,
    extra: dict[str, Any],
) -> OrderRequest:
    """Normalize the shared legacy sizing call to the typed order contract."""
    return OrderRequest(
        asset=asset,
        side=side,
        value=float(value),
        style=cast(OrderStyle, style),
        price=price,
        order_time=order_time,
        timeout=timeout,
        extra=extra,
    )


def target_order_side(
    asset: str, target_pct: float, total: float, positions: Iterable[_MarkedPosition]
) -> OrderSide:
    """Use current marked market value to choose a target-position direction."""
    current = next((float(position.mv) for position in positions if position.asset == asset), 0.0)
    return OrderSide.BUY if total * target_pct >= current else OrderSide.SELL
