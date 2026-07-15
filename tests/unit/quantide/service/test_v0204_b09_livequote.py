"""B09-livequote: Cover remaining missing lines in livequote.py.

Targets gaps not covered by earlier livequote test files:
- _build_ws_url: http:// -> ws:// branch (line 93)
- _refresh_limits: missing up_limit/down_limit columns (lines 228, 232-236)
- all_minute_bars: data aggregation branch (line 302)
- all_daily_bars: values branch (line 313)
- stream: already-started RuntimeError + yield sentinel branch (lines 344, 354)
- _on_quotes_all: payload dispatch (lines 386-401)
- _put_event_safe: queue full / no-queue branches (lines 405-410)
- _to_float_or_none: None + invalid branches (lines 414-419)
"""

from __future__ import annotations

import asyncio
import datetime
import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from quantide.core.domain import MarketEvent
from quantide.service.livequote import LiveQuote


@pytest.fixture(autouse=True)
def _reset_livequote_singleton():
    """Ensure each test starts with a fresh LiveQuote singleton."""
    LiveQuote._instance = None
    yield
    LiveQuote._instance = None


# ---------------------------------------------------------------------------
# _build_ws_url: http:// -> ws:// branch (line 93)
# ---------------------------------------------------------------------------


def test_build_ws_url_http_scheme_converts_to_ws():
    """An http:// gateway base URL is converted to a ws:// websocket URL."""
    q = LiveQuote()
    fake_settings = MagicMock()
    fake_settings.gateway_base_url = "http://gateway.local:8000"
    with patch("quantide.service.livequote.get_settings", return_value=fake_settings):
        url = q._build_ws_url()
    assert url == "ws://gateway.local:8000/ws/quotes"


# ---------------------------------------------------------------------------
# _refresh_limits: missing up_limit/down_limit columns (lines 228, 232-236)
# ---------------------------------------------------------------------------


def test_refresh_limits_adds_missing_limit_columns():
    """When the limit-price frame lacks up_limit/down_limit, zero-filled columns are added."""
    q = LiveQuote()
    df = pd.DataFrame({"ts_code": ["000050.SZ"], "up_limit": [11.0]})  # no down_limit
    fake_fetcher = MagicMock()
    fake_fetcher.fetch_limit_price.return_value = (df, None)
    with patch("quantide.service.livequote.get_data_fetcher", return_value=fake_fetcher):
        q._refresh_limits(datetime.date(2024, 1, 5))
    # The down_limit should default to 0.0 for the asset.
    assert q.get_limit("000050.SZ") is not None
    down, up = q.get_price_limits("000050.SZ")
    assert up == 11.0
    assert down == 0.0


# ---------------------------------------------------------------------------
# all_minute_bars / all_daily_bars: non-empty aggregation branches (302, 313)
# ---------------------------------------------------------------------------


def test_all_minute_bars_and_all_daily_bars_aggregate_multiple_symbols():
    """Feeding ticks for two symbols exercises the data.extend / values branches."""
    q = LiveQuote()
    for sym in ("000040.SZ", "000041.SZ"):
        raw = json.dumps({
            "symbol": sym,
            "timestamp": 1700000000.0,
            "1m": {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "vol": 100, "amount": 1000},
            "1d": {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "vol": 100, "amount": 1000},
        })
        q._parse_ws_payload(raw)
    minute_df = q.all_minute_bars
    assert not minute_df.is_empty()
    assert len(minute_df) >= 2
    daily_df = q.all_daily_bars
    assert not daily_df.is_empty()
    assert len(daily_df) >= 2


# ---------------------------------------------------------------------------
# stream: already-started RuntimeError (line 344)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_raises_when_already_started():
    """A second stream() call raises RuntimeError('stream already started')."""
    q = LiveQuote()
    q._stream_queue = asyncio.Queue(maxsize=10)  # simulate already-started state
    try:
        with pytest.raises(RuntimeError, match="stream already started"):
            async for _ in q.stream():
                break  # pragma: no cover
    finally:
        q._stream_queue = None


# ---------------------------------------------------------------------------
# _on_quotes_all + _put_event_safe: dispatch / no-queue / queue-full (386-410)
# ---------------------------------------------------------------------------


def test_on_quotes_all_noop_when_stream_not_active():
    """When no stream queue/loop is set, _on_quotes_all returns immediately."""
    q = LiveQuote()
    # _stream_queue and _stream_loop are None by default.
    q._on_quotes_all({"000001.SZ": {"price": 10.0}})
    # No exception raised; nothing enqueued.


def test_on_quotes_all_dispatches_event_to_loop():
    """When a stream is active, _on_quotes_all schedules _put_event_safe on the loop."""
    q = LiveQuote()
    fake_loop = MagicMock()
    q._stream_queue = MagicMock()
    q._stream_loop = fake_loop
    q._subscribed = {"000001.SZ"}
    q._on_quotes_all({"000001.SZ": {"price": 10.0}, "999999.SZ": {"price": 99.0}})
    # Only the subscribed symbol is dispatched; call_soon_threadsafe is invoked once.
    assert fake_loop.call_soon_threadsafe.call_count == 1
    scheduled_fn, scheduled_event = fake_loop.call_soon_threadsafe.call_args[0]
    assert scheduled_fn == q._put_event_safe
    assert isinstance(scheduled_event, MarketEvent)
    assert scheduled_event.symbol == "000001.SZ"


def test_on_quotes_all_skips_when_payload_empty():
    """An empty payload returns early without dispatching."""
    q = LiveQuote()
    fake_loop = MagicMock()
    q._stream_queue = MagicMock()
    q._stream_loop = fake_loop
    q._on_quotes_all({})
    assert fake_loop.call_soon_threadsafe.call_count == 0


# ---------------------------------------------------------------------------
# _put_event_safe: no-queue + queue-full branches (lines 405-410)
# ---------------------------------------------------------------------------


def test_put_event_safe_noop_when_no_queue():
    """When _stream_queue is None, _put_event_safe returns without error."""
    q = LiveQuote()
    q._stream_queue = None
    q._put_event_safe(MagicMock(spec=MarketEvent))  # must not raise


def test_put_event_safe_swallows_queue_full():
    """When put_nowait raises QueueFull, the exception is swallowed."""
    q = LiveQuote()
    fake_queue = MagicMock()
    fake_queue.put_nowait.side_effect = asyncio.QueueFull()
    q._stream_queue = fake_queue
    q._put_event_safe(MagicMock(spec=MarketEvent))  # must not raise


# ---------------------------------------------------------------------------
# _to_float_or_none: None + invalid branches (lines 414-419)
# ---------------------------------------------------------------------------


def test_to_float_or_none_returns_none_for_none_and_invalid():
    """None -> None; invalid string -> None; valid number -> float."""
    q = LiveQuote()
    assert q._to_float_or_none(None) is None
    assert q._to_float_or_none("not-a-number") is None
    assert q._to_float_or_none("3.14") == 3.14
    assert q._to_float_or_none(42) == 42.0
