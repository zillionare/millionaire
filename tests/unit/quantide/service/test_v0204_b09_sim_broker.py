"""[AC-NFR1101-01] sim_broker.py helpers."""

from unittest.mock import MagicMock, patch

import datetime as dt

import polars as pl

import quantide.service.sim_broker as sb_mod
from quantide.service.sim_broker import PaperBroker


def _make_broker():
    """Build broker with mocked dependencies."""
    broker = PaperBroker.__new__(PaperBroker)
    broker._closed = False
    return broker


def test_previous_trade_date_basic():
    """Returns trading day before given date."""
    broker = _make_broker()
    out = broker._previous_trade_date(dt.date(2024, 6, 15))
    assert isinstance(out, dt.date)
    assert out < dt.date(2024, 6, 15)


def test_empty_history_frame():
    """Returns empty DataFrame with expected schema."""
    broker = _make_broker()
    out = broker._empty_history_frame()
    assert isinstance(out, pl.DataFrame)
    assert out.is_empty()
    expected_cols = {
        "date", "asset", "open", "high", "low", "close",
        "volume", "amount", "adjust", "is_st", "up_limit", "down_limit",
    }
    assert set(out.columns) == expected_cols
    assert out.schema["date"] == pl.Date
    assert out.schema["asset"] == pl.Utf8
    assert out.schema["close"] == pl.Float64
    assert out.schema["is_st"] == pl.Boolean


def test_close_idempotent():
    """Calling close twice doesn't error."""
    broker = _make_broker()
    broker._closed = True  # Already closed
    broker._lock = MagicMock()
    broker._quote_subscription = MagicMock()
    broker._limit_subscription = MagicMock()
    broker.close()  # Should not raise


def test_close_unsubscribes():
    """First close subscribes/unsubscribes properly."""
    broker = _make_broker()
    broker._quote_subscription = MagicMock()
    broker._limit_subscription = MagicMock()
    broker._lock = MagicMock()
    with patch.object(sb_mod, "msg_hub") as mock_hub, \
         patch.object(sb_mod, "Topics") as mock_topics:
        mock_topics.QUOTES_ALL.value = "quotes"
        mock_topics.STOCK_LIMIT.value = "limits"
        broker.close()
    assert broker._closed is True
    mock_hub.unsubscribe.assert_called()
