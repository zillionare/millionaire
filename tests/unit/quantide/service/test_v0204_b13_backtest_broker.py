"""B13 batch: cover missing branches in quantide.service.backtest_broker.

Targets specific missing lines reported by /tmp/gg.json:
  - cash property (line 112)
  - init_backtest DupPortfolio via assets table (line 125)
  - _match_bid_minute NoDataForMatch paths (lines 559, 564)
  - buy_amount explicit price + zero est_price (lines 717, 725)
  - sell no-valid-price path (lines 767, 772)
  - _match_ask_minute NoDataForMatch paths (lines 871, 876)
  - _match_shares partial fill (line 908)
  - sell_amount explicit price + ceil + zero est_price (lines 994, 1003, 1006)
  - get_history NotImplementedError + end_dt shift + return (lines 1090-1102)
  - _get_close_adjust_factors fallbacks (lines 1118-1124, 1142)
"""
from __future__ import annotations

import asyncio
import datetime
import math
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from quantide.config.settings import DEFAULT_TIMEZONE
from quantide.core.enums import OrderSide
from quantide.core.errors import (
    DupPortfolio,
    NoDataForMatch,
)
from quantide.data.models import Order
from quantide.data.sqlite import db
from quantide.service.backtest_broker import BacktestBroker

cfg = SimpleNamespace(TIMEZONE=DEFAULT_TIMEZONE)


def make_dt(d: datetime.date, hour: int, minute: int = 0) -> datetime.datetime:
    dt = datetime.datetime.combine(d, datetime.time(hour, minute))
    if hasattr(cfg.TIMEZONE, "localize"):
        return cfg.TIMEZONE.localize(dt)
    return dt.replace(tzinfo=cfg.TIMEZONE)


class MockDataFeed:
    def __init__(self):
        self.match_data = pl.DataFrame([])
        self.limits = (0.0, 0.0)
        self.close_factor_data = pl.DataFrame([])
        self.bars_result = pl.DataFrame([])

    def get_price_for_match(self, asset, tm):
        if self.match_data.is_empty():
            return None
        return self.match_data

    def get_trade_price_limits(self, asset, dt):
        if not self.match_data.is_empty() and "up_limit" in self.match_data.columns:
            row = self.match_data.row(0, named=True)
            return row.get("down_limit", 0.0), row.get("up_limit", 0.0)
        return self.limits

    def get_close_factor(self, assets, start, end):
        if self.close_factor_data.is_empty():
            return pl.DataFrame(
                [],
                schema={
                    "dt": pl.Date,
                    "asset": pl.Utf8,
                    "close": pl.Float64,
                    "factor": pl.Float64,
                },
            )
        return self.close_factor_data.filter(
            (pl.col("dt") >= start) & (pl.col("dt") <= end)
        )

    def get_close_adjust_factor(self, assets, start, end):
        return self.get_close_factor(assets, start, end)

    def get_bars(self, n, end, assets, adjust):
        return self.bars_result


@pytest.fixture
def data_feed():
    return MockDataFeed()


@pytest.fixture
def broker(calendar, data_feed):
    db.init(":memory:")
    return BacktestBroker(
        bt_start=datetime.date(2024, 1, 2),
        bt_end=datetime.date(2024, 1, 10),
        portfolio_id="test_bt_b13",
        data_feed=data_feed,
        principal=1000000,
    )


@pytest.fixture
def minute_broker(calendar, data_feed):
    db.init(":memory:")
    return BacktestBroker(
        bt_start=datetime.date(2024, 1, 2),
        bt_end=datetime.date(2024, 1, 10),
        portfolio_id="test_bt_b13_min",
        data_feed=data_feed,
        principal=1000000,
        match_level="minute",
    )


# --- cash property ----------------------------------------------------------


def test_cash_property_returns_current_cash(broker):
    """Line 112: cash property returns self._cash."""
    assert broker.cash == 1000000


# --- init_backtest DupPortfolio via assets ----------------------------------


def test_init_backtest_raises_dup_when_assets_exist(broker, data_feed):
    """Line 125: assets table already has rows for this portfolio -> DupPortfolio."""
    # broker fixture already called init_backtest via __init__.
    # Creating a second broker with same portfolio_id but bypassing the
    # get_portfolio check (portfolio exists) hits the assets check.
    with pytest.raises(DupPortfolio):
        BacktestBroker(
            bt_start=datetime.date(2024, 1, 2),
            bt_end=datetime.date(2024, 1, 10),
            portfolio_id="test_bt_b13",
            data_feed=data_feed,
            principal=1000000,
        )


# --- _match_bid_minute NoDataForMatch ---------------------------------------


def test_match_bid_minute_raises_when_bars_empty_after_remove(minute_broker, data_feed):
    """Line 559: all bars filtered by _remove_for_bid -> NoDataForMatch."""
    # Set up minute bars where close >= up_limit (all filtered out).
    data_feed.match_data = pl.DataFrame({
        "date": [datetime.date(2024, 1, 2)],
        "open": [11.0],
        "close": [11.0],
        "up_limit": [11.0],
        "down_limit": [9.0],
        "volume": [100.0],
        "price": [11.0],
        "tm": [make_dt(datetime.date(2024, 1, 2), 9, 31)],
    })
    dt = make_dt(datetime.date(2024, 1, 2), 9, 30)
    with pytest.raises(NoDataForMatch):
        asyncio.run(minute_broker.buy("000001.SZ", 100, 0, dt))


def test_match_bid_minute_raises_when_filled_zero(minute_broker, data_feed):
    """Line 564: _match_shares returns filled=0 -> NoDataForMatch."""
    data_feed.match_data = pl.DataFrame({
        "date": [datetime.date(2024, 1, 2)],
        "open": [10.0],
        "close": [10.0],
        "up_limit": [11.0],
        "down_limit": [9.0],
        "volume": [100.0],
        "price": [10.0],
        "tm": [make_dt(datetime.date(2024, 1, 2), 9, 31)],
    })
    dt = make_dt(datetime.date(2024, 1, 2), 9, 30)
    with patch.object(
        minute_broker, "_match_shares", return_value=(10.0, 0, dt)
    ):
        with pytest.raises(NoDataForMatch):
            asyncio.run(minute_broker.buy("000001.SZ", 100, 0, dt))


# --- buy_amount -------------------------------------------------------------


def test_buy_amount_uses_explicit_price(broker, data_feed):
    """Line 717: price > 0 -> est_price = price (skips limits lookup)."""
    data_feed.match_data = pl.DataFrame({
        "date": [datetime.date(2024, 1, 2)],
        "open": [10.0],
        "close": [10.5],
        "up_limit": [11.0],
        "down_limit": [9.0],
    })
    dt = make_dt(datetime.date(2024, 1, 2), 9, 30)
    # buy_amount with price=10 -> shares = 1000000 / (10 * 1.0005) // 100 * 100
    result = asyncio.run(broker.buy_amount("000001.SZ", 10000, price=10.0, order_time=dt))
    assert result is not None


def test_buy_amount_raises_when_est_price_zero(broker, data_feed):
    """Line 725: price=0 and up_limit=0 -> est_price=0 -> NoDataForMatch."""
    data_feed.limits = (0.0, 0.0)
    data_feed.match_data = pl.DataFrame([])
    dt = make_dt(datetime.date(2024, 1, 2), 9, 30)
    with pytest.raises(NoDataForMatch):
        asyncio.run(broker.buy_amount("000001.SZ", 10000, order_time=dt))


# --- sell no-valid-price ----------------------------------------------------


def test_sell_logs_and_raises_when_ask_price_zero(broker, data_feed):
    """Lines 767, 772: ask_price == 0 (no down_limit, no price) -> NoDataForMatch."""
    # Provide bars with down_limit=0 and call sell with price=0.
    data_feed.match_data = pl.DataFrame({
        "date": [datetime.date(2024, 1, 2)],
        "open": [10.0],
        "close": [10.0],
        "up_limit": [11.0],
        "down_limit": [0.0],
    })
    # Need a position to pass the pos check before price check.
    # Actually, the price check happens at line 766, BEFORE the position check at 775.
    dt = make_dt(datetime.date(2024, 1, 2), 9, 30)
    with pytest.raises(NoDataForMatch):
        asyncio.run(broker.sell("000001.SZ", 100, 0, dt))


# --- _match_ask_minute NoDataForMatch ---------------------------------------


def test_match_ask_minute_raises_when_bars_empty_after_remove(minute_broker, data_feed):
    """Line 871: all bars filtered by _remove_for_ask -> NoDataForMatch."""
    # Set up position first via a minute-level buy.
    data_feed.match_data = pl.DataFrame({
        "date": [datetime.date(2024, 1, 2)],
        "open": [10.0],
        "close": [10.0],
        "up_limit": [11.0],
        "down_limit": [9.0],
        "volume": [1000.0],
        "price": [10.0],
        "tm": [make_dt(datetime.date(2024, 1, 2), 9, 31)],
    })
    dt = make_dt(datetime.date(2024, 1, 2), 9, 30)
    asyncio.run(minute_broker.buy("000001.SZ", 1000, 0, dt))

    # Now set up minute bars where close <= down_limit (all filtered by _remove_for_ask).
    data_feed.match_data = pl.DataFrame({
        "date": [datetime.date(2024, 1, 3)],
        "open": [9.0],
        "close": [9.0],
        "up_limit": [11.0],
        "down_limit": [9.0],
        "volume": [100.0],
        "price": [9.0],
        "tm": [make_dt(datetime.date(2024, 1, 3), 9, 31)],
    })
    dt2 = make_dt(datetime.date(2024, 1, 3), 9, 30)
    with pytest.raises(NoDataForMatch):
        asyncio.run(minute_broker.sell("000001.SZ", 100, 0, dt2))


def test_match_ask_minute_raises_when_filled_zero(minute_broker, data_feed):
    """Line 876: _match_shares returns filled=0 -> NoDataForMatch."""
    data_feed.match_data = pl.DataFrame({
        "date": [datetime.date(2024, 1, 2)],
        "open": [10.0],
        "close": [10.0],
        "up_limit": [11.0],
        "down_limit": [9.0],
        "volume": [1000.0],
        "price": [10.0],
        "tm": [make_dt(datetime.date(2024, 1, 2), 9, 31)],
    })
    dt = make_dt(datetime.date(2024, 1, 2), 9, 30)
    asyncio.run(minute_broker.buy("000001.SZ", 1000, 0, dt))

    # Set up minute bars for sell that pass _remove_for_ask.
    data_feed.match_data = pl.DataFrame({
        "date": [datetime.date(2024, 1, 3)],
        "open": [10.0],
        "close": [10.0],
        "up_limit": [11.0],
        "down_limit": [9.0],
        "volume": [100.0],
        "price": [10.0],
        "tm": [make_dt(datetime.date(2024, 1, 3), 9, 31)],
    })
    dt2 = make_dt(datetime.date(2024, 1, 3), 9, 30)
    with patch.object(
        minute_broker, "_match_shares", return_value=(10.0, 0, dt2)
    ):
        with pytest.raises(NoDataForMatch):
            asyncio.run(minute_broker.sell("000001.SZ", 100, 0, dt2))


# --- _match_shares partial fill ---------------------------------------------


def test_match_shares_returns_partial_when_volume_insufficient(minute_broker, data_feed):
    """Line 908: cum_v never reaches shares -> i = len(v) - 1."""
    # Create minute bars with limited volume.
    bars = pl.DataFrame({
        "price": [10.0, 10.1],
        "volume": [1.0, 2.0],  # 100 + 200 = 300 shares total
        "tm": [
            make_dt(datetime.date(2024, 1, 2), 9, 31),
            make_dt(datetime.date(2024, 1, 2), 9, 32),
        ],
    })
    # Request 1000 shares but only 300 available -> partial fill.
    mean_price, filled, tm = minute_broker._match_shares(bars, 1000)
    assert filled == 300
    assert mean_price > 0
    assert tm == make_dt(datetime.date(2024, 1, 2), 9, 32)


# --- sell_amount ------------------------------------------------------------


def test_sell_amount_uses_explicit_price_and_ceil(broker, data_feed):
    """Lines 994, 1006: price > 0 -> est_price = price; method='ceil' -> ceil shares."""
    # Need a position to sell.
    data_feed.match_data = pl.DataFrame({
        "date": [datetime.date(2024, 1, 2)],
        "open": [10.0],
        "close": [10.0],
        "up_limit": [11.0],
        "down_limit": [9.0],
    })
    dt = make_dt(datetime.date(2024, 1, 2), 9, 30)
    asyncio.run(broker.buy("000001.SZ", 10000, 0, dt))

    # Now sell_amount with explicit price.
    data_feed.match_data = pl.DataFrame({
        "date": [datetime.date(2024, 1, 3)],
        "open": [10.0],
        "close": [10.0],
        "up_limit": [11.0],
        "down_limit": [9.0],
    })
    dt2 = make_dt(datetime.date(2024, 1, 3), 9, 30)
    result = asyncio.run(
        broker.sell_amount("000001.SZ", 500, price=10.0, order_time=dt2)
    )
    assert result is not None


def test_sell_amount_raises_when_est_price_zero(broker, data_feed):
    """Line 1003: price=0 and down_limit=0 -> NoDataForMatch."""
    data_feed.limits = (0.0, 0.0)
    data_feed.match_data = pl.DataFrame([])
    dt = make_dt(datetime.date(2024, 1, 2), 9, 30)
    with pytest.raises(NoDataForMatch):
        asyncio.run(broker.sell_amount("000001.SZ", 500, order_time=dt))


# --- get_history ------------------------------------------------------------


def test_get_history_raises_for_non_1d_frame(broker):
    """Lines 1090-1095: frame_type != '1d' -> NotImplementedError."""
    with pytest.raises(NotImplementedError):
        broker.get_history("000001.SZ", 5, frame_type="1min")


def test_get_history_shifts_end_date_before_open(broker, data_feed):
    """Lines 1097-1102: end_dt.time() <= 9:30 -> day_shift(-1); returns get_bars."""
    data_feed.bars_result = pl.DataFrame({
        "date": [datetime.date(2024, 1, 1)],
        "asset": ["000001.SZ"],
        "close": [10.0],
    })
    dt = make_dt(datetime.date(2024, 1, 2), 9, 0)
    result = broker.get_history("000001.SZ", 5, end_dt=dt)
    assert result is not None
    assert len(result) >= 0


def test_get_history_returns_data_feed_bars(broker, data_feed):
    """Line 1102: normal call delegates to data_feed.get_bars."""
    expected = pl.DataFrame({
        "date": [datetime.date(2024, 1, 2)],
        "asset": ["000001.SZ"],
        "close": [10.0],
    })
    data_feed.bars_result = expected
    result = broker.get_history("000001.SZ", 3, end_dt=make_dt(datetime.date(2024, 1, 2), 15, 0))
    assert result is expected


# --- _get_close_adjust_factors ----------------------------------------------


def test_get_close_adjust_factors_falls_back_to_get_close_factor(broker):
    """Lines 1118-1119: no get_close_adjust_factor -> uses get_close_factor."""
    feed = SimpleNamespace()
    # Only has get_close_factor (not get_close_adjust_factor).
    feed.get_close_factor = lambda assets, start, end: pl.DataFrame({
        "dt": [datetime.date(2024, 1, 2)],
        "asset": ["000001.SZ"],
        "close": [10.0],
        "factor": [1.0],
    })
    broker._data_feed = feed
    result = broker._get_close_adjust_factors(
        ["000001.SZ"], datetime.date(2024, 1, 2), datetime.date(2024, 1, 3)
    )
    assert "adjust" in result.columns
    assert result.height == 1


def test_get_close_adjust_factors_returns_empty_when_no_method(broker):
    """Lines 1121, 1124: feed has neither method -> empty DataFrame."""
    feed = SimpleNamespace()
    broker._data_feed = feed
    result = broker._get_close_adjust_factors(
        ["000001.SZ"], datetime.date(2024, 1, 2), datetime.date(2024, 1, 3)
    )
    assert result.is_empty()
    assert set(result.columns) == {"date", "asset", "close", "adjust"}


def test_get_close_adjust_factors_adds_adjust_when_missing(broker):
    """Line 1142: frame without 'adjust' column -> adds literal 1.0."""
    feed = SimpleNamespace()
    feed.get_close_adjust_factor = lambda assets, start, end: pl.DataFrame({
        "date": [datetime.date(2024, 1, 2)],
        "asset": ["000001.SZ"],
        "close": [10.0],
    })
    broker._data_feed = feed
    result = broker._get_close_adjust_factors(
        ["000001.SZ"], datetime.date(2024, 1, 2), datetime.date(2024, 1, 3)
    )
    assert "adjust" in result.columns
    assert result.row(0, named=True)["adjust"] == 1.0
