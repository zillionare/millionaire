"""True monthly 3/12 moving-average strategy example."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any

from quantide.config.settings import get_timezone
from quantide.core.enums import FrameType
from quantide.core.ports.broker import StrategyBroker
from quantide.core.strategy import BaseStrategy
from quantide.data.models.calendar import calendar
from quantide.service.monthly_bars import aggregate_monthly, monthly_ma_signals
from quantide.service.monthly_intents import (
    MonthlyIntentStore,
    execute_intent,
    intent_key,
    intent_namespace,
    monthly_intent_store,
    position_shares,
)


class MonthlyMAStrategy(BaseStrategy):
    """Fixed 1M strategy: 3-month/12-month crossover on closed bars."""

    BAR_INTERVAL = "1M"
    VERSION = "1.0.0"
    fill_timing = "next_open"
    HISTORY_TRADING_DAYS = 800
    PARAMS: dict[str, Any] = {
        "signal_asset": "000001.SZ",
        "invest_amount": 100_000,
        "short_window": 3,
        "long_window": 12,
    }

    @staticmethod
    def default_config() -> dict[str, Any]:
        return dict(MonthlyMAStrategy.PARAMS)

    def __init__(
        self,
        broker: StrategyBroker,
        config: dict[str, Any],
        *,
        store: MonthlyIntentStore | None = None,
        history_loader: Callable[[datetime.date], Any] | None = None,
    ) -> None:
        super().__init__(broker, config)
        supplied = config.get("bar_interval")
        if supplied is not None and str(supplied) != "1M":
            raise ValueError("MonthlyMAStrategy only supports the 1M interval")
        if int(config.get("short_window", 3)) != 3 or int(config.get("long_window", 12)) != 12:
            raise ValueError("MonthlyMAStrategy windows are fixed at 3/12 months")
        self.asset = str(config.get("signal_asset", "000001.SZ"))
        self.invest_amount = float(config.get("invest_amount", 100_000))
        kind = getattr(broker, "kind", "")
        kind_value = str(getattr(kind, "value", kind))
        self.lifecycle = str(
            config.get("lifecycle")
            or {"bt": "backtest", "sim": "paper", "qmt": "live"}.get(kind_value, "unknown")
        )
        self.account_id = str(config.get("account_id") or getattr(broker, "portfolio_id", ""))
        self.strategy_id = f"{self.__class__.__module__}.{self.__class__.__name__}"
        self.params = {
            "bar_interval": self.BAR_INTERVAL,
            "signal_asset": self.asset,
            "invest_amount": self.invest_amount,
            "short_window": 3,
            "long_window": 12,
        }
        self.namespace = intent_namespace(
            self.lifecycle,
            self.account_id,
            self.strategy_id,
            self.VERSION,
            self.params,
        )
        self._store = store or monthly_intent_store
        self._history_loader = history_loader or self._daily_history
        self._history_warned = False

    async def init(self) -> None:
        self.log(f"MonthlyMAStrategy initialized for {self.asset} (3/12 months)")

    async def on_bar(self, tm: datetime.datetime) -> None:
        """Execute due intents, then persist at most one signal for a closed month."""
        day = tm.date() if isinstance(tm, datetime.datetime) else tm
        await self._execute_due(day)
        if isinstance(tm, datetime.datetime) and tm.time() < datetime.time(15):
            return
        days = tuple(
            calendar.get_trade_dates(calendar.day_shift(day, -self.HISTORY_TRADING_DAYS), day)
        )
        if not days or days[-1] != day:
            return
        full_days = tuple(
            calendar.get_trade_dates(
                calendar.day_shift(day, -self.HISTORY_TRADING_DAYS),
                calendar.day_shift(day, 40),
            )
        )
        daily = self._history_loader(day)
        if daily.is_empty():
            if not self._history_warned:
                self.log(
                    f"No daily bars for {self.asset}; check signal_asset",
                    level="WARNING",
                )
                self._history_warned = True
            return
        series = aggregate_monthly(daily, full_days, as_of=day)
        asset_series = series.get(self.asset)
        if asset_series is None:
            return
        signals = monthly_ma_signals(asset_series, full_days)
        if not signals or signals[-1].signal_date != day:
            return
        signal = signals[-1]
        key = intent_key(self.namespace, self.asset, signal.signal_date, signal.direction)
        if self._store.seen(key):
            return
        shares = position_shares(self.broker, self.asset) if signal.direction == "sell" else 0
        if signal.direction == "sell" and shares <= 0:
            self.log(f"sell {self.asset} at {signal.signal_date} ignored: no position")
            return
        intent = {
            "key": key,
            "order_id": f"monthly:{key}",
            "namespace": self.namespace,
            "account_id": self.account_id,
            "lifecycle": self.lifecycle,
            "strategy_id": self.strategy_id,
            "strategy_version": self.VERSION,
            "params": self.params,
            "asset": self.asset,
            "signal_date": signal.signal_date.isoformat(),
            "execute_date": signal.execute_date.isoformat(),
            "direction": signal.direction,
            "amount": self.invest_amount,
            "shares": shares,
            "strategy": self.__class__.__name__,
        }
        self._store.enqueue(intent)
        self.log(
            f"{signal.direction} {self.asset} at {signal.signal_date}, "
            f"execute {signal.execute_date}"
        )

    async def _submit(self, intent: dict[str, Any], day: datetime.date) -> None:
        if (
            intent["direction"] == "sell"
            and position_shares(self.broker, str(intent["asset"])) <= 0
        ):
            self._store.complete(str(intent["key"]))
            return
        execute_date = max(datetime.date.fromisoformat(str(intent["execute_date"])), day)
        order_time = datetime.datetime.combine(
            execute_date, datetime.time(9, 30), tzinfo=get_timezone()
        )
        try:
            result = await execute_intent(self.broker, intent, order_time=order_time)
        except Exception as exc:
            self.log(f"monthly intent {intent.get('key')} failed: {exc}", level="WARNING")
            return
        if result is None or not getattr(result, "qt_oid", ""):
            return
        self._store.complete(str(intent["key"]))

    async def _execute_due(self, day: datetime.date) -> None:
        for intent in self._store.due(day, namespace=self.namespace):
            await self._submit(intent, day)

    def _daily_history(self, day: datetime.date) -> Any:
        from quantide.data.models.daily_bars import daily_bars

        start = calendar.day_shift(day, -self.HISTORY_TRADING_DAYS)
        return daily_bars.get_bars_in_range(
            start, day, assets=[self.asset], adjust=None, eager_mode=True
        )


def strategy_interval() -> FrameType:
    return FrameType.MONTH
