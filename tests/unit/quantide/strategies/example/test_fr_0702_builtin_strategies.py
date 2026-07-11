"""v0.2-003 FR-0702 AC-FR-0702-1..6 built-in strategy contracts."""

from __future__ import annotations

import datetime as dt
import inspect
from types import SimpleNamespace

import polars as pl

from quantide.strategies.cost_stop_loss import CostStopLossStrategy
from quantide.strategies.example.dual_ma import DualMAStrategy
from quantide.strategies.pullback_sell import PullbackSellStrategy


class Broker:
    """Boundary fake that records orders without accessing market services."""

    def __init__(self, prices: list[float], position: object | None = None) -> None:
        self.prices = iter(prices)
        self.positions = {"000001.SZ": position} if position else {}
        self.orders: list[tuple[str, int, str]] = []

    def get_prices(self, assets: list[str]) -> dict[str, float]:
        return {assets[0]: next(self.prices)}

    async def buy_amount(self, asset: str, amount: float, **kwargs: object) -> None:
        self.orders.append((asset, int(amount), "buy"))

    async def sell(self, asset: str, shares: int, **kwargs: object) -> None:
        self.orders.append((asset, shares, "sell"))


async def test_dual_ma_uses_public_on_bar_signature_and_crosses():
    """AC-FR-0702-1..2: on_bar(tm) pulls bars, buying only on an upward cross."""
    broker = Broker([])
    strategy = DualMAStrategy(broker, {"fast": 2, "slow": 3, "invest": 1000})
    strategy.get_bars = lambda *args, **kwargs: pl.DataFrame({"close": [3, 2, 2, 2, 3]})

    assert DualMAStrategy.default_config() == {"fast": 5, "slow": 20}
    assert list(inspect.signature(DualMAStrategy.on_bar).parameters) == ["self", "tm"]
    await strategy.on_bar(dt.datetime(2026, 1, 2, 10))
    assert broker.orders == [("000001.SZ", 1000, "buy")]


async def test_pullback_sells_available_position_only_within_n_minute_window():
    """AC-FR-0702-3..4: qualifying pullback sells once within its configured window."""
    position = SimpleNamespace(avail=30, price=10.0)
    broker = Broker([10.0, 10.8, 10.7], position)
    strategy = PullbackSellStrategy(broker, {"m": 7, "k": 0.5, "n": 1})
    strategy.sell_host_position = lambda asset, shares, reason: broker.sell(asset, shares, reason=reason)
    start = dt.datetime(2026, 1, 2, 10)

    await strategy.on_check(broker.positions, start)
    await strategy.on_check(broker.positions, start + dt.timedelta(seconds=30))
    await strategy.on_check(broker.positions, start + dt.timedelta(seconds=45))

    assert PullbackSellStrategy.default_config() == {"m": 7.0, "k": 0.5, "n": 1}
    assert broker.orders == [("000001.SZ", 30, "sell")]


async def test_pullback_does_not_sell_after_its_n_minute_window():
    """AC-FR-0702-4: a rollback after the n-minute monitoring window is ignored."""
    position = SimpleNamespace(avail=30, price=10.0)
    broker = Broker([10.0, 10.8, 10.7], position)
    strategy = PullbackSellStrategy(broker, {"m": 7, "k": 0.5, "n": 1})
    strategy.sell_host_position = lambda asset, shares, reason: broker.sell(asset, shares, reason=reason)
    start = dt.datetime(2026, 1, 2, 10)

    await strategy.on_check(broker.positions, start)
    await strategy.on_check(broker.positions, start + dt.timedelta(seconds=30))
    await strategy.on_check(broker.positions, start + dt.timedelta(minutes=2))

    assert broker.orders == []


async def test_cost_stop_sells_available_shares_once_at_threshold():
    """AC-FR-0702-5: 9.50 on a 10.00 basis triggers one cost_stop sale."""
    position = SimpleNamespace(avail=40, price=10.0)
    broker = Broker([9.5, 9.49], position)
    strategy = CostStopLossStrategy(broker, {})
    strategy.sell_host_position = lambda asset, shares, reason: broker.sell(asset, shares, reason=reason)
    now = dt.datetime(2026, 1, 2, 10)

    await strategy.on_check(broker.positions, now)
    await strategy.on_check(broker.positions, now)

    assert CostStopLossStrategy.default_config() == {"k": -5.0}
    assert broker.orders == [("000001.SZ", 40, "sell")]
