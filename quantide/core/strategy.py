import datetime
from abc import ABC
from typing import Any

import polars as pl
from loguru import logger

from quantide.core.enums import FrameType
from quantide.service.base_broker import Broker, TradeResult


class Strategy(ABC):
    def __init__(self, broker: Broker, config: dict[str, Any]):
        self.broker = broker
        self.config = config
        logger_kwargs = {"strategy": self.__class__.__name__}
        portfolio_id = getattr(broker, "portfolio_id", "")
        if portfolio_id:
            logger_kwargs["portfolio_id"] = portfolio_id
        self.logger = logger.bind(**logger_kwargs)
        self.interval: str = "1d"
        self._current_time: datetime.datetime | None = None

    @staticmethod
    def default_config() -> dict[str, Any]:
        return {}

    async def init(self) -> None:
        pass

    async def on_start(self) -> None:
        pass

    async def on_stop(self) -> None:
        pass

    async def on_day_open(self, tm: datetime.datetime) -> None:
        pass

    async def on_day_close(self, tm: datetime.datetime) -> None:
        pass

    def get_bars(
        self,
        asset: str,
        count: int,
        end_dt: datetime.datetime | None = None,
        frame_type: str = "1d",
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        return self.broker.get_history(
            asset, count, end_dt, frame_type, include_forming_bar=include_forming_bar
        )

    get_history = get_bars

    def _render_log_message(self, msg: str, *args: Any, **kwargs: Any) -> str:
        if not args and not kwargs:
            return msg
        try:
            return msg.format(*args, **kwargs)
        except Exception:
            return msg

    def log(
        self,
        msg: str,
        *args,
        tm: datetime.datetime | datetime.date | None = None,
        level: str = "INFO",
        **kwargs,
    ):
        log_time = tm
        if log_time is None:
            log_time = self._current_time
        rendered_message = self._render_log_message(msg, *args, **kwargs)
        if log_time:
            def _temp_patcher(record):
                record["time"] = log_time
            self.logger.patch(_temp_patcher).log(level, msg, *args, **kwargs)
        else:
            self.logger.log(level, msg, *args, **kwargs)
        write_backtest_log = getattr(self.broker, "write_backtest_log", None)
        if callable(write_backtest_log):
            write_backtest_log(
                level=level,
                source="strategy",
                message=rendered_message,
                dt=log_time,
            )

    def record(
        self,
        key: str,
        value: float,
        dt: datetime.datetime | None = None,
        extra: dict | None = None,
    ):
        if dt is None:
            dt = self._current_time
        self.broker.record(key, value, dt, extra)


class BaseStrategy(Strategy):
    @staticmethod
    def default_config() -> dict[str, Any]:
        return {}

    async def on_bar(self, tm: datetime.datetime) -> None:
        pass

    @property
    def positions(self) -> dict[str, Any]:
        return self.broker.positions

    @property
    def cash(self) -> float:
        return self.broker.cash

    async def buy(self, asset: str, shares: int, price: float = 0,
                  order_time: datetime.datetime | None = None) -> TradeResult:
        return await self.broker.buy(asset, shares, price, order_time)

    async def buy_percent(self, asset: str, percent: float, price: float = 0,
                          order_time: datetime.datetime | None = None) -> TradeResult:
        return await self.broker.buy_percent(asset, percent, price, order_time)

    async def buy_amount(self, asset: str, amount: int | float, price: float = 0,
                         order_time: datetime.datetime | None = None) -> TradeResult:
        return await self.broker.buy_amount(asset, amount, price, order_time)

    async def sell(self, asset: str, shares: int, price: float = 0,
                   order_time: datetime.datetime | None = None) -> TradeResult:
        return await self.broker.sell(asset, shares, price, order_time)

    async def sell_percent(self, asset: str, percent: float, price: float = 0,
                           order_time: datetime.datetime | None = None) -> TradeResult:
        return await self.broker.sell_percent(asset, percent, price, order_time)

    async def sell_amount(self, asset: str, amount: int | float, price: float = 0,
                          order_time: datetime.datetime | None = None) -> TradeResult:
        return await self.broker.sell_amount(asset, amount, price, order_time)

    async def cancel_order(self, qt_oid: str) -> None:
        return await self.broker.cancel_order(qt_oid)

    async def cancel_all_orders(self, side: str | None = None) -> int:
        return await self.broker.cancel_all_orders(side)

    async def trade_target_pct(self, asset: str, target_pct: float,
                               price: float = 0,
                               order_time: datetime.datetime | None = None) -> TradeResult:
        return await self.broker.trade_target_pct(asset, target_pct, price, order_time)


class RiskStrategy(Strategy):
    async def on_check(self, positions: dict[str, Any],
                       tm: datetime.datetime) -> None:
        pass

    def get_prices(self, assets: list[str]) -> dict[str, float]:
        if hasattr(self.broker, "get_prices"):
            return self.broker.get_prices(assets)
        raise NotImplementedError("get_prices is only available in paper/live mode")

    def get_ticks(self, asset: str, count: int) -> pl.DataFrame:
        if hasattr(self.broker, "get_ticks"):
            return self.broker.get_ticks(asset, count)
        raise NotImplementedError("get_ticks is only available in paper/live mode")

    async def sell_host_position(self, asset: str, shares: int,
                                  reason: str = "") -> TradeResult:
        return await self.broker.sell(asset, shares, price=0)
