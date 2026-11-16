"""Strategy attribution and durable next-open order proxies."""

from __future__ import annotations

import datetime
import json
from typing import Any, cast

from quantide.core.enums import FrameType
from quantide.core.order_execution import BROKER_ORDER_METHODS
from quantide.core.ports.broker import BrokerPort, ExecutionResult
from quantide.data.models.calendar import calendar
from quantide.service.strategy_tracking import TrackingStore, tracking_store


class StrategyBrokerProxy:
    def __init__(self, broker: BrokerPort, strategy_id: str) -> None:
        self._broker = broker
        self._strategy_id = strategy_id

    def __getattr__(self, item: str) -> Any:
        return getattr(self._broker, item)

    async def buy(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        kwargs.update(
            asset=asset,
            shares=shares,
            price=price,
            order_time=order_time,
            timeout=timeout,
            strategy_id=self._strategy_id,
        )
        return await self._broker.buy(
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
        kwargs.update(
            asset=asset,
            shares=shares,
            price=price,
            order_time=order_time,
            timeout=timeout,
            strategy_id=self._strategy_id,
        )
        return await self._broker.sell(
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
        kwargs.update(
            asset=asset,
            percent=percent,
            price=price,
            order_time=order_time,
            timeout=timeout,
            strategy_id=self._strategy_id,
        )
        return await self._broker.buy_percent(
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
        kwargs.update(
            asset=asset,
            percent=percent,
            price=price,
            order_time=order_time,
            timeout=timeout,
            strategy_id=self._strategy_id,
        )
        return await self._broker.sell_percent(
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
        kwargs.update(
            asset=asset,
            amount=amount,
            price=price,
            order_time=order_time,
            timeout=timeout,
            strategy_id=self._strategy_id,
        )
        return await self._broker.buy_amount(
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
        kwargs.update(
            asset=asset,
            amount=amount,
            price=price,
            order_time=order_time,
            timeout=timeout,
            strategy_id=self._strategy_id,
        )
        return await self._broker.sell_amount(
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
        kwargs.update(
            asset=asset,
            target_pct=target_pct,
            price=price,
            order_time=order_time,
            timeout=timeout,
            strategy_id=self._strategy_id,
        )
        return await self._broker.trade_target_pct(**kwargs)


class NextOpenBrokerProxy:
    """Turn strategy orders into durable next-trading-day-open intents."""

    _ORDER_METHODS = BROKER_ORDER_METHODS

    def __init__(
        self,
        broker: Any,
        *,
        runtime_id: str,
        portfolio_id: str,
        strategy_id: str,
        signal_date: datetime.date,
        store: TrackingStore | None = None,
    ) -> None:
        self._broker = broker
        self._store = store or tracking_store
        self._runtime_id = runtime_id
        self._portfolio_id = portfolio_id
        self._strategy_id = strategy_id
        self._signal_date = signal_date

    def __getattr__(self, item: str) -> Any:
        return getattr(self._broker, item)

    def _target_date(self) -> datetime.date:
        try:
            return calendar.day_shift(self._signal_date, 1)
        except Exception:
            return self._signal_date + datetime.timedelta(days=1)

    def _enqueue(
        self, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> ExecutionResult:
        key_payload = {
            "method": method,
            "args": list(args),
            # order_time identifies when the caller happened to retry, not
            # the order intent.  Excluding it makes persistence idempotent
            # for keyword and positional calls alike.
            "kwargs": {key: value for key, value in kwargs.items() if key != "order_time"},
            "signal_date": self._signal_date.isoformat(),
        }
        intent_key = json.dumps(key_payload, sort_keys=True, default=str)
        self._store.enqueue_next_open_intent(
            runtime_id=self._runtime_id,
            portfolio_id=self._portfolio_id,
            strategy_id=self._strategy_id,
            signal_date=self._signal_date,
            target_date=self._target_date(),
            method=method,
            args=list(args),
            kwargs=kwargs,
            intent_key=intent_key,
        )
        return ExecutionResult.empty()

    def __getattribute__(self, item: str) -> Any:
        if item in object.__getattribute__(self, "_ORDER_METHODS"):

            async def queued(*args: Any, **kwargs: Any) -> ExecutionResult:
                return cast(
                    ExecutionResult, object.__getattribute__(self, "_enqueue")(item, args, kwargs)
                )

            return queued
        return object.__getattribute__(self, item)


class NextOpenBarBrokerProxy:
    """Persist 30m strategy orders until the next eligible bar boundary."""

    _ORDER_METHODS = BROKER_ORDER_METHODS

    def __init__(
        self,
        broker: Any,
        *,
        runtime_id: str,
        portfolio_id: str,
        strategy_id: str,
        signal_bar: datetime.datetime,
        store: TrackingStore | None = None,
    ) -> None:
        self._broker = broker
        self._store = store or tracking_store
        self._runtime_id = runtime_id
        self._portfolio_id = portfolio_id
        self._strategy_id = strategy_id
        self._signal_bar = signal_bar.replace(tzinfo=None)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._broker, item)

    def _target_bar(self) -> datetime.datetime:
        try:
            next_completed = calendar.shift(self._signal_bar, 1, FrameType.MIN30)
        except Exception as exc:
            raise RuntimeError(
                "无法确定 30m next_open 的下一个交易时段，拒绝以内存队列下单"
            ) from exc
        if not isinstance(next_completed, datetime.datetime):
            raise RuntimeError("30m next_open target bar 无效，拒绝下单")
        # Calendar minute frames are bar-end timestamps: 13:30 is the end of
        # the first afternoon bar, whose executable next-open is 13:00.
        return (next_completed - datetime.timedelta(minutes=30)).replace(tzinfo=None)

    def _enqueue(
        self, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> ExecutionResult:
        target_bar = self._target_bar()
        key_payload = {
            "interval": "30m",
            "method": method,
            "args": list(args),
            # order_time identifies a retry, not the order intent.
            "kwargs": {key: value for key, value in kwargs.items() if key != "order_time"},
            "signal_bar": self._signal_bar.isoformat(timespec="seconds"),
            "target_bar": target_bar.isoformat(timespec="seconds"),
        }
        intent_key = json.dumps(key_payload, sort_keys=True, default=str)
        self._store.enqueue_next_open_intent(
            runtime_id=self._runtime_id,
            portfolio_id=self._portfolio_id,
            strategy_id=self._strategy_id,
            signal_date=self._signal_bar.date(),
            target_date=target_bar.date(),
            signal_bar=self._signal_bar,
            target_bar=target_bar,
            method=method,
            args=list(args),
            kwargs=kwargs,
            intent_key=intent_key,
        )
        return ExecutionResult.empty()

    def __getattribute__(self, item: str) -> Any:
        if item in object.__getattribute__(self, "_ORDER_METHODS"):

            async def queued(*args: Any, **kwargs: Any) -> ExecutionResult:
                return cast(
                    ExecutionResult, object.__getattribute__(self, "_enqueue")(item, args, kwargs)
                )

            return queued
        return object.__getattribute__(self, item)
