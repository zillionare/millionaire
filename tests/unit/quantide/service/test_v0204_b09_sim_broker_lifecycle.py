"""[AC-NFR1101-01] B09 sim_broker lifecycle helpers coverage.

Targets ~50 missing lines in ``quantide/service/sim_broker.py``:
- ``close()`` idempotent / unsubscribe path (lines 108-113)
- ``_previous_trade_date`` calendar success + fallback (lines 287-290)
- ``_resolve_history_end_date`` early-time branch + calendar-failure fallback
  (lines 437-441)
- ``_should_attach_forming_bar`` true/false branches (lines 334-338)
- ``_empty_history_frame`` schema (lines 444-460)
"""

from __future__ import annotations

import datetime as dt
import threading
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

import quantide.service.sim_broker as sb_mod
from quantide.service.sim_broker import PaperBroker


def _make_broker() -> PaperBroker:
    """Build a PaperBroker shell without invoking ``__init__`` (avoids DB / msg_hub)."""
    broker = PaperBroker.__new__(PaperBroker)
    broker._closed = False
    broker._lock = threading.RLock()
    broker._clock = None
    broker._quote_subscription = MagicMock()
    broker._limit_subscription = MagicMock()
    return broker


# ---------------------------------------------------------------------------
# close() lifecycle
# ---------------------------------------------------------------------------


def test_close_unsubscribes_both_topics() -> None:
    """First ``close()`` unsubscribes QUOTES_ALL and STOCK_LIMIT and flips ``_closed``."""
    broker = _make_broker()
    with patch.object(sb_mod, "msg_hub") as mock_hub, patch.object(sb_mod, "Topics") as mock_topics:
        mock_topics.QUOTES_ALL.value = "quotes"
        mock_topics.STOCK_LIMIT.value = "limits"
        broker.close()
    assert broker._closed is True
    unsub_topics = [call.args[0] for call in mock_hub.unsubscribe.call_args_list]
    assert "quotes" in unsub_topics
    assert "limits" in unsub_topics


def test_close_idempotent_when_already_closed() -> None:
    """Calling ``close()`` twice does not invoke ``msg_hub.unsubscribe`` again."""
    broker = _make_broker()
    broker._closed = True
    with patch.object(sb_mod, "msg_hub") as mock_hub:
        broker.close()
    mock_hub.unsubscribe.assert_not_called()


# ---------------------------------------------------------------------------
# _previous_trade_date
# ---------------------------------------------------------------------------


def test_previous_trade_date_uses_calendar_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``calendar.day_shift`` succeeds, its result is returned unchanged."""
    broker = _make_broker()
    today = dt.date(2024, 6, 17)
    expected = dt.date(2024, 6, 14)
    monkeypatch.setattr(
        sb_mod.calendar, "day_shift", lambda d, n: expected if d == today and n == -1 else d
    )
    assert broker._previous_trade_date(today) == expected


def test_previous_trade_date_falls_back_on_calendar_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``calendar.day_shift`` raises, fallback returns ``today - 1 day``."""
    broker = _make_broker()
    today = dt.date(2024, 6, 17)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("calendar not loaded")

    monkeypatch.setattr(sb_mod.calendar, "day_shift", _raise)
    assert broker._previous_trade_date(today) == today - dt.timedelta(days=1)


# ---------------------------------------------------------------------------
# _resolve_history_end_date
# ---------------------------------------------------------------------------


def test_resolve_history_end_date_returns_today_when_no_end_dt(monkeypatch: pytest.MonkeyPatch) -> None:
    """``end_dt=None`` resolves to broker's ``_get_today()``."""
    broker = _make_broker()
    today = dt.date(2024, 6, 17)
    monkeypatch.setattr(broker, "_get_today", lambda: today)
    assert broker._resolve_history_end_date(None) == today


def test_resolve_history_end_date_pre_930_uses_previous_trade_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``end_dt`` at or before 09:30 shifts end_date back via ``calendar.day_shift``."""
    broker = _make_broker()
    end_dt = dt.datetime(2024, 6, 17, 9, 15)
    expected = dt.date(2024, 6, 14)
    monkeypatch.setattr(sb_mod.calendar, "day_shift", lambda d, n: expected if n == -1 else d)
    assert broker._resolve_history_end_date(end_dt) == expected


def test_resolve_history_end_date_pre_930_falls_back_on_calendar_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-9:30 path with ``calendar.day_shift`` raising falls back to natural ``-1 day``."""
    broker = _make_broker()
    end_dt = dt.datetime(2024, 6, 17, 9, 15)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("calendar not loaded")

    monkeypatch.setattr(sb_mod.calendar, "day_shift", _raise)
    assert broker._resolve_history_end_date(end_dt) == dt.date(2024, 6, 16)


def test_resolve_history_end_date_after_930_keeps_same_date() -> None:
    """``end_dt`` after 09:30 returns the same calendar date."""
    broker = _make_broker()
    end_dt = dt.datetime(2024, 6, 17, 14, 30)
    assert broker._resolve_history_end_date(end_dt) == dt.date(2024, 6, 17)


# ---------------------------------------------------------------------------
# _should_attach_forming_bar
# ---------------------------------------------------------------------------


def test_should_attach_forming_bar_false_when_end_date_not_today() -> None:
    """``end_date`` != today -> False (no forming bar for historical dates)."""
    broker = _make_broker()
    broker._clock = dt.datetime(2024, 6, 17, 10, 0)
    assert broker._should_attach_forming_bar(dt.date(2024, 6, 16), None) is False


def test_should_attach_forming_bar_false_when_end_dt_at_or_before_930() -> None:
    """``end_date`` == today but ``end_dt.time() <= 09:30`` -> False."""
    broker = _make_broker()
    broker._clock = dt.datetime(2024, 6, 17, 10, 0)
    assert (
        broker._should_attach_forming_bar(dt.date(2024, 6, 17), dt.datetime(2024, 6, 17, 9, 30))
        is False
    )


def test_should_attach_forming_bar_true_when_today_and_after_930() -> None:
    """``end_date`` == today and ``end_dt`` after 09:30 -> True."""
    broker = _make_broker()
    broker._clock = dt.datetime(2024, 6, 17, 10, 0)
    assert (
        broker._should_attach_forming_bar(dt.date(2024, 6, 17), dt.datetime(2024, 6, 17, 15, 0))
        is True
    )


def test_should_attach_forming_bar_true_when_today_and_no_end_dt() -> None:
    """``end_date`` == today and ``end_dt=None`` -> True (treated as intraday)."""
    broker = _make_broker()
    broker._clock = dt.datetime(2024, 6, 17, 10, 0)
    assert broker._should_attach_forming_bar(dt.date(2024, 6, 17), None) is True


# ---------------------------------------------------------------------------
# _empty_history_frame
# ---------------------------------------------------------------------------


def test_empty_history_frame_schema_complete() -> None:
    """``_empty_history_frame`` returns an empty DataFrame with the full OHLCV+ schema."""
    broker = _make_broker()
    df = broker._empty_history_frame()
    assert isinstance(df, pl.DataFrame)
    assert df.is_empty()
    assert df.height == 0
    expected_schema = {
        "date": pl.Date,
        "asset": pl.Utf8,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "amount": pl.Float64,
        "adjust": pl.Float64,
        "is_st": pl.Boolean,
        "up_limit": pl.Float64,
        "down_limit": pl.Float64,
    }
    assert dict(df.schema) == expected_schema
