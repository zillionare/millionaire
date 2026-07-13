"""v0.2-004-coverage-recovery B07-dual-ma gaps: quantide/strategies/example/dual_ma.py.

Targets uncovered branches:
- default_config returns expected dict
- __init__ defaults and overrides for fast/slow/symbol/invest
- init() logs initialization
- on_day_open() is a no-op
- on_bar(): insufficient data branch (line 40-41), golden cross no-position
  branch (line 58-64), death cross with-position branch (line 67-71),
  no-cross branches
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, AsyncMock

import numpy as np
import polars as pl
import pytest

from quantide.strategies.example.dual_ma import DualMAStrategy


def _make_bars_with_closes(closes: list[float], symbol: str = "000001.SZ") -> pl.DataFrame:
    """Build a polars DataFrame of historical bars with given close prices."""
    n = len(closes)
    dates = [datetime.date(2024, 1, i + 1) for i in range(n)]
    return pl.DataFrame({
        "asset": [symbol] * n,
        "frame": [datetime.datetime.combine(d, datetime.time(15, 0)) for d in dates],
        "open": closes,
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes,
        "volume": [1000.0] * n,
        "amount": [c * 1000 for c in closes],
    })


# ---------------------------------------------------------------------------
# default_config / __init__
# ---------------------------------------------------------------------------


def test_default_config_returns_expected_dict() -> None:
    """AC-FR0700-322: DualMAStrategy.default_config returns fast=5, slow=20."""
    cfg = DualMAStrategy.default_config()
    assert cfg == {"fast": 5, "slow": 20}


def test_init_uses_config_overrides() -> None:
    """AC-FR0700-323: __init__ uses config values for fast, slow, symbol, invest."""
    broker = MagicMock()
    cfg = {"fast": 10, "slow": 30, "symbol": "600000.SH", "invest": 50000}
    s = DualMAStrategy(broker, cfg)
    assert s.fast_window == 10
    assert s.slow_window == 30
    assert s.symbol == "600000.SH"
    assert s.invest_amount == 50000.0


def test_init_uses_defaults_when_keys_missing() -> None:
    """AC-FR0700-324: __init__ falls back to defaults when config keys missing."""
    s = DualMAStrategy(MagicMock(), {})
    assert s.fast_window == 5
    assert s.slow_window == 20
    assert s.symbol == "000001.SZ"
    assert s.invest_amount == 100000.0


# ---------------------------------------------------------------------------
# init() / on_day_open()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_logs_initialization() -> None:
    """AC-FR0700-325: init() logs initialization message."""
    s = DualMAStrategy(MagicMock(), {"fast": 5, "slow": 20})
    s.log = MagicMock()  # mock log
    await s.init()
    s.log.assert_called_once()
    msg = s.log.call_args[0][0]
    assert "DualMAStrategy Initialized" in msg
    assert "Fast=5" in msg
    assert "Slow=20" in msg


@pytest.mark.asyncio
async def test_on_day_open_is_noop() -> None:
    """AC-FR0700-326: on_day_open() is a no-op (just passes)."""
    s = DualMAStrategy(MagicMock(), {})
    s.broker.buy_amount = AsyncMock()
    s.broker.sell = AsyncMock()
    await s.on_day_open(datetime.datetime(2024, 6, 15))
    s.broker.buy_amount.assert_not_called()
    s.broker.sell.assert_not_called()


# ---------------------------------------------------------------------------
# on_bar()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_bar_insufficient_data_no_action() -> None:
    """AC-FR0700-327: on_bar() with insufficient bars does not place an order."""
    broker = MagicMock()
    broker.buy_amount = AsyncMock()
    broker.sell = AsyncMock()
    broker.positions = {}
    s = DualMAStrategy(broker, {"fast": 5, "slow": 20})

    # Provide fewer than slow_window + 2 = 22 bars.
    s.get_bars = MagicMock(return_value=_make_bars_with_closes([10.0] * 10))

    await s.on_bar(datetime.datetime(2024, 6, 15))
    broker.buy_amount.assert_not_called()
    broker.sell.assert_not_called()


@pytest.mark.asyncio
async def test_on_bar_golden_cross_buys_when_no_position() -> None:
    """AC-FR0700-328: golden cross (fast crosses up) → buy when no position."""
    broker = MagicMock()
    broker.buy_amount = AsyncMock()
    broker.sell = AsyncMock()
    broker.positions = {}
    s = DualMAStrategy(broker, {"fast": 5, "slow": 20, "invest": 100000})

    # Build 22 closes. Need: prev_fast <= prev_slow AND curr_fast > curr_slow.
    # Use 22 closes where first 16 are low (10), 17-20 are medium (11), 21-22 are high (20).
    # prev_fast = avg of closes[16:21] = avg(11,11,11,11,10) = 10.8
    # prev_slow = avg of closes[1:21] = avg(10*15 + 11*5) / 20 = 10.25
    # curr_fast = avg of closes[17:22] = avg(11,11,11,11,20) = 12.8
    # curr_slow = avg of closes[2:22] = avg(10*14 + 11*5 + 20) / 20 = 10.75
    # prev_fast(10.8) <= prev_slow(10.25)? No — fails golden cross!
    #
    # Need to engineer it differently. Use a stepped pattern:
    # closes[0..15] = 20 (high), closes[16..20] = 5 (low), closes[21] = 30 (very high)
    # prev_fast = avg of closes[16:21] = 5
    # prev_slow = avg of closes[1:21] = (20*15 + 5*5) / 20 = 16.25
    # curr_fast = avg of closes[17:22] = avg(5,5,5,5,30) = 10
    # curr_slow = avg of closes[2:22] = (20*14 + 5*5 + 30) / 20 = 15.4
    # prev_fast(5) <= prev_slow(16.25)? YES. curr_fast(10) > curr_slow(15.4)? No.
    #
    # Try: closes[0..10] = 5, closes[11..21] = 20
    # prev_fast = avg of closes[16:21] = avg(20,20,20,20,20) = 20
    # prev_slow = avg of closes[1:21] = avg(5*10 + 20*10) / 20 = 12.5
    # curr_fast = avg of closes[17:22] = avg(20,20,20,20,20) = 20
    # curr_slow = avg of closes[2:22] = avg(5*9 + 20*11) / 20 = (45+220)/20 = 13.25
    # prev_fast(20) <= prev_slow(12.5)? NO. Not golden.
    #
    # Try: closes[0..15] = 5 (low), closes[16..20] = 5 (still low), closes[21] = 30
    # prev_fast = avg of closes[16:21] = avg(5,5,5,5,5) = 5
    # prev_slow = avg of closes[1:21] = avg(5*20) / 20 = 5
    # curr_fast = avg of closes[17:22] = avg(5,5,5,5,30) = 10
    # curr_slow = avg of closes[2:22] = avg(5*19 + 30) / 20 = (95+30)/20 = 6.25
    # prev_fast(5) <= prev_slow(5)? YES. curr_fast(10) > curr_slow(6.25)? YES. GOLDEN!
    closes = [5.0] * 21 + [30.0]
    s.get_bars = MagicMock(return_value=_make_bars_with_closes(closes))

    await s.on_bar(datetime.datetime(2024, 6, 15))
    broker.buy_amount.assert_called_once()


@pytest.mark.asyncio
async def test_on_bar_death_cross_sells_when_holding() -> None:
    """AC-FR0700-329: death cross (fast crosses down) → sell when holding position."""
    broker = MagicMock()
    broker.buy_amount = AsyncMock()
    broker.sell = AsyncMock()
    pos = MagicMock(shares=100)
    broker.positions = {"000001.SZ": pos}
    s = DualMAStrategy(broker, {"fast": 5, "slow": 20})

    # Construct death cross: prev_fast >= prev_slow AND curr_fast < curr_slow.
    # Need curr_fast < curr_slow while prev_fast >= prev_slow.
    # Use: closes[0..15] = 20 (high), closes[16..20] = 20, closes[21] = 1
    # prev_fast = avg(closes[16:21]) = avg(20,20,20,20,20) = 20
    # prev_slow = avg(closes[1:21]) = avg(20*20)/20 = 20
    # curr_fast = avg(closes[17:22]) = avg(20,20,20,20,1) = 12.2
    # curr_slow = avg(closes[2:22]) = avg(20*19 + 1)/20 = (380+1)/20 = 19.05
    # prev_fast(20) >= prev_slow(20)? YES. curr_fast(12.2) < curr_slow(19.05)? YES. DEATH!
    closes = [20.0] * 21 + [1.0]
    s.get_bars = MagicMock(return_value=_make_bars_with_closes(closes))

    await s.on_bar(datetime.datetime(2024, 6, 15))
    broker.sell.assert_called_once()


@pytest.mark.asyncio
async def test_on_bar_no_cross_no_action() -> None:
    """AC-FR0700-330: when fast and slow don't cross, no order is placed."""
    broker = MagicMock()
    broker.buy_amount = AsyncMock()
    broker.sell = AsyncMock()
    broker.positions = {}
    s = DualMAStrategy(broker, {"fast": 5, "slow": 20})

    # 22 constant closes: no crossing.
    closes = [10.0] * 22
    s.get_bars = MagicMock(return_value=_make_bars_with_closes(closes))

    await s.on_bar(datetime.datetime(2024, 6, 15))
    broker.buy_amount.assert_not_called()
    broker.sell.assert_not_called()


@pytest.mark.asyncio
async def test_on_bar_golden_cross_no_buy_when_already_holding() -> None:
    """AC-FR0700-331: golden cross doesn't buy if already holding a position."""
    broker = MagicMock()
    broker.buy_amount = AsyncMock()
    broker.sell = AsyncMock()
    pos = MagicMock(shares=100)
    broker.positions = {"000001.SZ": pos}
    s = DualMAStrategy(broker, {"fast": 5, "slow": 20, "invest": 100000})

    closes = [5.0] * 21 + [30.0]  # golden cross
    s.get_bars = MagicMock(return_value=_make_bars_with_closes(closes))

    await s.on_bar(datetime.datetime(2024, 6, 15))
    broker.buy_amount.assert_not_called()  # already holding, no additional buy


@pytest.mark.asyncio
async def test_on_bar_death_cross_no_sell_when_no_position() -> None:
    """AC-FR0700-332: death cross doesn't sell if position is zero."""
    broker = MagicMock()
    broker.buy_amount = AsyncMock()
    broker.sell = AsyncMock()
    broker.positions = {}  # no position
    s = DualMAStrategy(broker, {"fast": 5, "slow": 20})

    closes = [20.0] * 21 + [1.0]  # death cross
    s.get_bars = MagicMock(return_value=_make_bars_with_closes(closes))

    await s.on_bar(datetime.datetime(2024, 6, 15))
    broker.sell.assert_not_called()  # no position to sell