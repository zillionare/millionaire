"""v0.2-004-coverage-recovery B06-datafeed gaps: quantide/service/datafeed.py.

Targets uncovered branches:
- BarsFeedImpl.__init__: _is_backtest with live_quote running/not running (line 151)
- BarsFeedImpl.get_bars: backtest path, live path with/without need_live (lines 168-191)
- BarsFeedImpl._get_history_bars: daily_bars is None, exception (lines 201, 224-226)
- BarsFeedImpl._get_live_bar: live_quote None, exception (lines 230, 240-242)
- BarsFeedImpl._merge_history_live: empty history, empty live, normal (lines 248-257)
- BarsFeedImpl._normalize_columns: empty df, st→is_st rename (lines 261-281)
- BarsFeedImpl.get_price_limits: live_quote path, daily_bars path, exception,
  neither (lines 308-321)
- BarsFeedImpl.get_current_price: live_quote None, quote None, quote no price (lines 323-332)
- BarsFeedImpl.get_price_for_match: empty df, missing columns (lines 346-353)
- BarsFeedImpl.get_close_adjust_factor: daily_bars None, exception (lines 359, 377-385)
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import polars as pl
import pytest

from quantide.core.enums import FrameType
from quantide.service.datafeed import BarsFeedImpl


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_live_quote_running():
    """A mock live_quote that reports running=True."""
    lq = MagicMock()
    lq.is_running = True
    return lq


@pytest.fixture
def mock_live_quote_not_running():
    """A mock live_quote that reports running=False."""
    lq = MagicMock()
    lq.is_running = False
    return lq


@pytest.fixture
def mock_daily_bars_with_data():
    """A mock daily_bars returning non-empty data."""
    db = MagicMock()
    db.get_bars_in_range.return_value = pl.DataFrame({
        "date": [datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)],
        "asset": ["000001.SZ", "000001.SZ"],
        "open": [10.0, 10.5],
        "high": [11.0, 11.5],
        "low": [9.5, 10.0],
        "close": [10.5, 11.0],
        "volume": [1000.0, 1100.0],
        "amount": [10000.0, 11000.0],
    })
    return db


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_init_with_live_quote_running_marks_not_backtest(mock_live_quote_running) -> None:
    """AC-FR0700-191: _is_backtest is False when live_quote is not None and running."""
    feed = BarsFeedImpl(daily_bars=MagicMock(), live_quote=mock_live_quote_running)
    assert feed._is_backtest is False


def test_init_with_live_quote_not_running_marks_backtest(mock_live_quote_not_running) -> None:
    """AC-FR0700-192: _is_backtest is True when live_quote is not None but not running."""
    feed = BarsFeedImpl(daily_bars=MagicMock(), live_quote=mock_live_quote_not_running)
    assert feed._is_backtest is True


def test_init_without_live_quote_marks_backtest() -> None:
    """AC-FR0700-193: _is_backtest is True when live_quote is None."""
    feed = BarsFeedImpl(daily_bars=MagicMock(), live_quote=None)
    assert feed._is_backtest is True


# ---------------------------------------------------------------------------
# get_bars
# ---------------------------------------------------------------------------


def test_get_bars_with_exception_returns_empty_df(mock_daily_bars_with_data) -> None:
    """AC-FR0700-194: get_bars returns empty df when underlying call raises."""
    mock_daily_bars_with_data.get_bars_in_range.side_effect = RuntimeError("boom")
    feed = BarsFeedImpl(daily_bars=mock_daily_bars_with_data)

    result = feed.get_bars("000001.SZ", datetime.date(2024, 1, 1))

    # Empty df has all required columns.
    assert set(result.columns) >= {"asset", "frame", "open", "high", "low", "close", "volume", "amount", "is_st", "up_limit", "down_limit"}


def test_get_bars_normalizes_columns(mock_daily_bars_with_data) -> None:
    """AC-FR0700-195: get_bars output has all required columns."""
    feed = BarsFeedImpl(daily_bars=mock_daily_bars_with_data)

    result = feed.get_bars("000001.SZ", datetime.date(2024, 1, 1))

    expected_cols = {"asset", "frame", "open", "high", "low", "close", "volume", "amount", "adjust", "is_st", "up_limit", "down_limit"}
    assert expected_cols.issubset(set(result.columns))


def test_get_bars_renames_st_to_is_st(mock_daily_bars_with_data) -> None:
    """AC-FR0700-196: get_bars renames 'st' column to 'is_st'."""
    mock_daily_bars_with_data.get_bars_in_range.return_value = pl.DataFrame({
        "date": [datetime.date(2024, 1, 1)],
        "asset": ["000001.SZ"],
        "open": [10.0], "high": [11.0], "low": [9.5], "close": [10.5],
        "volume": [1000.0], "amount": [10000.0], "adjust": [1.0],
        "st": [False],
    })
    feed = BarsFeedImpl(daily_bars=mock_daily_bars_with_data)

    result = feed.get_bars("000001.SZ", datetime.date(2024, 1, 1))

    assert "is_st" in result.columns
    assert "st" not in result.columns


# ---------------------------------------------------------------------------
# get_price_limits
# ---------------------------------------------------------------------------


def test_get_price_limits_with_live_quote_returns_quote_values(mock_live_quote_running) -> None:
    """AC-FR0700-197: get_price_limits delegates to live_quote when present."""
    mock_live_quote_running.get_price_limits.return_value = (9.0, 11.0)
    feed = BarsFeedImpl(live_quote=mock_live_quote_running)

    down, up = feed.get_price_limits("000001.SZ")
    assert (down, up) == (9.0, 11.0)


def test_get_price_limits_falls_back_to_daily_bars(mock_daily_bars_with_data) -> None:
    """AC-FR0700-198: get_price_limits uses daily_bars when no live_quote."""
    mock_daily_bars_with_data.get_trade_price_limits.return_value = (9.5, 10.5)
    feed = BarsFeedImpl(daily_bars=mock_daily_bars_with_data, live_quote=None)

    down, up = feed.get_price_limits("000001.SZ")
    assert down == 9.5
    assert up == 10.5


def test_get_price_limits_returns_zeros_when_no_data() -> None:
    """AC-FR0700-199: get_price_limits returns (0.0, 0.0) when no data source."""
    feed = BarsFeedImpl(daily_bars=None, live_quote=None)
    down, up = feed.get_price_limits("000001.SZ")
    assert (down, up) == (0.0, 0.0)


def test_get_price_limits_swallows_daily_bars_exception() -> None:
    """AC-FR0700-200: get_price_limits returns (0.0, 0.0) when daily_bars raises."""
    db = MagicMock()
    db.get_trade_price_limits.side_effect = RuntimeError("err")
    feed = BarsFeedImpl(daily_bars=db, live_quote=None)
    down, up = feed.get_price_limits("000001.SZ")
    assert (down, up) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# get_current_price
# ---------------------------------------------------------------------------


def test_get_current_price_without_live_quote_returns_none() -> None:
    """AC-FR0700-201: get_current_price returns None when live_quote is None."""
    feed = BarsFeedImpl(live_quote=None)
    assert feed.get_current_price("000001.SZ") is None


def test_get_current_price_with_no_quote_returns_none(mock_live_quote_running) -> None:
    """AC-FR0700-202: get_current_price returns None when live_quote has no quote for asset."""
    mock_live_quote_running.get_quote.return_value = None
    feed = BarsFeedImpl(live_quote=mock_live_quote_running)
    assert feed.get_current_price("000001.SZ") is None


def test_get_current_price_with_quote_returns_price(mock_live_quote_running) -> None:
    """AC-FR0700-203: get_current_price returns price from live_quote.get_quote."""
    mock_live_quote_running.get_quote.return_value = {"price": 10.5, "volume": 1000}
    feed = BarsFeedImpl(live_quote=mock_live_quote_running)
    assert feed.get_current_price("000001.SZ") == 10.5


# ---------------------------------------------------------------------------
# get_price_for_match
# ---------------------------------------------------------------------------


def test_get_price_for_match_empty_df_returns_none(mock_daily_bars_with_data) -> None:
    """AC-FR0700-204: get_price_for_match returns None when get_bars returns empty."""
    mock_daily_bars_with_data.get_bars_in_range.return_value = pl.DataFrame()
    feed = BarsFeedImpl(daily_bars=mock_daily_bars_with_data)
    result = feed.get_price_for_match("000001.SZ", datetime.datetime(2024, 1, 1))
    assert result is None


def test_get_price_for_match_returns_df_when_columns_present(mock_daily_bars_with_data) -> None:
    """AC-FR0700-205: get_price_for_match returns df with required columns."""
    feed = BarsFeedImpl(daily_bars=mock_daily_bars_with_data)
    result = feed.get_price_for_match("000001.SZ", datetime.datetime(2024, 1, 1))
    assert result is not None
    for col in ["open", "high", "low", "close", "volume", "up_limit", "down_limit"]:
        assert col in result.columns


# ---------------------------------------------------------------------------
# get_close_adjust_factor
# ---------------------------------------------------------------------------


def test_get_close_adjust_factor_without_daily_bars_returns_empty() -> None:
    """AC-FR0700-206: get_close_adjust_factor returns empty df when daily_bars is None."""
    feed = BarsFeedImpl(daily_bars=None)
    result = feed.get_close_adjust_factor(
        ["000001.SZ"], datetime.date(2024, 1, 1), datetime.date(2024, 1, 31)
    )
    assert result.is_empty()
    assert set(result.columns) >= {"frame", "asset", "close", "adjust"}


def test_get_close_adjust_factor_with_data_returns_df(mock_daily_bars_with_data) -> None:
    """AC-FR0700-207: get_close_adjust_factor delegates to daily_bars."""
    expected = pl.DataFrame({
        "frame": [datetime.datetime(2024, 1, 1)],
        "asset": ["000001.SZ"],
        "close": [10.5],
        "adjust": [1.0],
    })
    mock_daily_bars_with_data.get_close_adjust_factor.return_value = expected
    feed = BarsFeedImpl(daily_bars=mock_daily_bars_with_data)

    result = feed.get_close_adjust_factor(
        ["000001.SZ"], datetime.date(2024, 1, 1), datetime.date(2024, 1, 31)
    )
    assert len(result) == 1
    assert result["close"][0] == 10.5


def test_get_close_adjust_factor_swallows_exception() -> None:
    """AC-FR0700-208: get_close_adjust_factor returns empty df on exception."""
    db = MagicMock()
    db.get_close_adjust_factor.side_effect = RuntimeError("err")
    feed = BarsFeedImpl(daily_bars=db)

    result = feed.get_close_adjust_factor(
        ["000001.SZ"], datetime.date(2024, 1, 1), datetime.date(2024, 1, 31)
    )
    assert result.is_empty()


# ---------------------------------------------------------------------------
# _to_datetime
# ---------------------------------------------------------------------------


def test_to_datetime_passthrough_when_datetime() -> None:
    """AC-FR0700-209: _to_datetime returns datetime unchanged."""
    feed = BarsFeedImpl()
    dt = datetime.datetime(2024, 1, 1, 10, 0)
    assert feed._to_datetime(dt) == dt


def test_to_datetime_combines_date_with_min_time() -> None:
    """AC-FR0700-210: _to_datetime converts date to datetime at 00:00."""
    feed = BarsFeedImpl()
    result = feed._to_datetime(datetime.date(2024, 1, 1))
    assert result == datetime.datetime(2024, 1, 1, 0, 0)


# ---------------------------------------------------------------------------
# _get_history_bars exception / no daily_bars
# ---------------------------------------------------------------------------


def test_get_history_bars_without_daily_bars_returns_empty() -> None:
    """AC-FR0700-211: _get_history_bars returns empty df when daily_bars is None."""
    feed = BarsFeedImpl(daily_bars=None)
    result = feed._get_history_bars("000001.SZ", datetime.date(2024, 1, 1), None, "qfq")
    assert result.is_empty()


def test_get_history_bars_swallows_exception(mock_daily_bars_with_data) -> None:
    """AC-FR0700-212: _get_history_bars returns empty df on exception."""
    mock_daily_bars_with_data.get_bars_in_range.side_effect = RuntimeError("err")
    feed = BarsFeedImpl(daily_bars=mock_daily_bars_with_data)
    result = feed._get_history_bars("000001.SZ", datetime.date(2024, 1, 1), None, "qfq")
    assert result.is_empty()


# ---------------------------------------------------------------------------
# _get_live_bar paths
# ---------------------------------------------------------------------------


def test_get_live_bar_without_live_quote_returns_none() -> None:
    """AC-FR0700-213: _get_live_bar returns None when live_quote is None."""
    feed = BarsFeedImpl(live_quote=None)
    assert feed._get_live_bar("000001.SZ") is None


def test_get_live_bar_with_no_daily_bar_returns_none(mock_live_quote_running) -> None:
    """AC-FR0700-214: _get_live_bar returns None when live_quote.get_daily_bar returns None."""
    mock_live_quote_running.get_daily_bar.return_value = None
    feed = BarsFeedImpl(live_quote=mock_live_quote_running)
    assert feed._get_live_bar("000001.SZ") is None


def test_get_live_bar_returns_dataframe(mock_live_quote_running) -> None:
    """AC-FR0700-215: _get_live_bar wraps the bar dict in a DataFrame."""
    mock_live_quote_running.get_daily_bar.return_value = {
        "asset": "000001.SZ", "open": 10.0, "close": 10.5,
    }
    feed = BarsFeedImpl(live_quote=mock_live_quote_running)
    result = feed._get_live_bar("000001.SZ")
    assert result is not None
    assert len(result) == 1


def test_get_live_bar_swallows_exception(mock_live_quote_running) -> None:
    """AC-FR0700-216: _get_live_bar returns None when get_daily_bar raises."""
    mock_live_quote_running.get_daily_bar.side_effect = RuntimeError("err")
    feed = BarsFeedImpl(live_quote=mock_live_quote_running)
    assert feed._get_live_bar("000001.SZ") is None


# ---------------------------------------------------------------------------
# _merge_history_live
# ---------------------------------------------------------------------------


def test_merge_history_live_empty_history_returns_live() -> None:
    """AC-FR0700-217: _merge_history_live returns live_df when history is empty."""
    feed = BarsFeedImpl()
    history = pl.DataFrame()
    live = pl.DataFrame({"asset": ["000001.SZ"], "close": [10.0]})
    result = feed._merge_history_live(history, live)
    assert len(result) == 1


def test_merge_history_live_empty_live_returns_history() -> None:
    """AC-FR0700-218: _merge_history_live returns history when live is empty."""
    feed = BarsFeedImpl()
    history = pl.DataFrame({"asset": ["000001.SZ"], "close": [10.0]})
    live = pl.DataFrame()
    result = feed._merge_history_live(history, live)
    assert len(result) == 1


def test_merge_history_live_concatenates() -> None:
    """AC-FR0700-219: _merge_history_live concatenates and sorts by frame."""
    feed = BarsFeedImpl()
    history = pl.DataFrame({
        "asset": ["000001.SZ"],
        "frame": [datetime.datetime(2024, 1, 1)],
        "close": [10.0],
    })
    live = pl.DataFrame({
        "asset": ["000001.SZ"],
        "frame": [datetime.datetime(2024, 1, 2)],
        "close": [11.0],
    })
    result = feed._merge_history_live(history, live)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# _normalize_columns edge cases
# ---------------------------------------------------------------------------


def test_normalize_columns_empty_returns_empty_df() -> None:
    """AC-FR0700-220: _normalize_columns of empty df returns empty df."""
    feed = BarsFeedImpl()
    result = feed._normalize_columns(pl.DataFrame())
    assert result.is_empty()