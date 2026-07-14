"""B06-svc-3: Additional tests for quantide/service/livequote.py.

Target: raise coverage from 73% to >=80% by exercising:
- _parse_ws_payload edge cases (missing fields, invalid json, etc.)
- Singleton reset/initialization lifecycle
- Getter APIs (get_quote, get_price_limits, get_limit, etc.)
- _cache_and_broadcast / _cache_limits
- start/stop behavior (without actually opening websockets)
- subscribe/unsubscribe APIs
"""

from __future__ import annotations

import datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from quantide.service.livequote import LiveQuote


@pytest.fixture(autouse=True)
def _reset_livequote_singleton():
    """Ensure each test starts with a fresh LiveQuote singleton."""
    LiveQuote._instance = None
    yield
    LiveQuote._instance = None


# ---------------------------------------------------------------------------
# Singleton & lifecycle
# ---------------------------------------------------------------------------


def test_livequote_is_singleton():
    a = LiveQuote()
    b = LiveQuote()
    assert a is b


def test_livequote_init_idempotent():
    """Calling init twice does not clobber state."""
    a = LiveQuote()
    a._mode = "test"
    b = LiveQuote()
    # Same instance; second __init__ returns early due to _initialized flag.
    assert b._mode == "test"


def test_livequote_initial_state_is_not_running():
    q = LiveQuote()
    assert q.is_running is False
    assert q.mode is None


def test_livequote_get_quote_returns_none_when_no_data():
    q = LiveQuote()
    assert q.get_quote("000001.SZ") is None


def test_livequote_get_price_limits_returns_zero_when_unknown():
    q = LiveQuote()
    down, up = q.get_price_limits("000777.SZ")
    assert down == 0.0
    assert up == 0.0


def test_livequote_get_limit_returns_none_when_unknown():
    q = LiveQuote()
    assert q.get_limit("000888.SZ") is None


def test_livequote_get_minute_bars_returns_empty_dataframe():
    q = LiveQuote()
    df = q.get_minute_bars("000001.SZ")
    assert df is not None
    assert df.is_empty()


def test_livequote_get_daily_bar_returns_none_when_unknown():
    q = LiveQuote()
    assert q.get_daily_bar("000002.SZ") is None


def test_livequote_all_limits_returns_dict():
    q = LiveQuote()
    out = q.all_limits
    assert isinstance(out, dict)


def test_livequote_all_quotes_returns_dict():
    q = LiveQuote()
    out = q.all_quotes
    assert isinstance(out, dict)


def test_livequote_all_minute_bars_returns_dataframe():
    q = LiveQuote()
    df = q.all_minute_bars
    assert df is not None


def test_livequote_all_daily_bars_returns_dataframe():
    q = LiveQuote()
    df = q.all_daily_bars
    assert df is not None


def test_livequote_subscribe_no_op_when_not_streaming():
    q = LiveQuote()
    q.subscribe(["000001.SZ"])
    assert "000001.SZ" in q._subscribed


def test_livequote_unsubscribe_removes_symbols():
    q = LiveQuote()
    q._subscribed.add("000001.SZ")
    q.unsubscribe(["000001.SZ"])
    assert "000001.SZ" not in q._subscribed


# ---------------------------------------------------------------------------
# _parse_ws_payload — edge cases
# ---------------------------------------------------------------------------


def test_parse_ws_payload_invalid_json_returns_empty():
    q = LiveQuote()
    assert q._parse_ws_payload("not json at all") == {}


def test_parse_ws_payload_bytes_input():
    q = LiveQuote()
    raw = json.dumps(
        {"symbol": "000005.SZ", "timestamp": 1700000000.0, "1m": {"close": 5.0}}
    ).encode("utf-8")
    payload = q._parse_ws_payload(raw)
    assert "000005.SZ" in payload


def test_parse_ws_payload_non_dict_returns_empty():
    q = LiveQuote()
    assert q._parse_ws_payload("[]") == {}


def test_parse_ws_payload_no_symbol_returns_empty():
    q = LiveQuote()
    raw = json.dumps({"timestamp": 1700000000.0})
    assert q._parse_ws_payload(raw) == {}


def test_parse_ws_payload_minute_only_no_daily():
    q = LiveQuote()
    raw = json.dumps(
        {
            "symbol": "000010.SZ",
            "timestamp": 1700000000.0,
            "1m": {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "vol": 100, "amount": 1000},
        }
    )
    payload = q._parse_ws_payload(raw)
    assert "000010.SZ" in payload
    item = payload["000010.SZ"]
    assert item["price"] == 10.2


def test_parse_ws_payload_daily_only_no_minute():
    q = LiveQuote()
    raw = json.dumps(
        {
            "symbol": "000011.SZ",
            "timestamp": 1700000000.0,
            "1d": {"open": 11.0, "high": 11.5, "low": 10.5, "close": 11.2, "vol": 100, "amount": 1000},
        }
    )
    payload = q._parse_ws_payload(raw)
    assert "000011.SZ" in payload


def test_parse_ws_payload_crosses_day_resets_cache():
    q = LiveQuote()
    raw1 = json.dumps(
        {
            "symbol": "000020.SZ",
            "timestamp": 1700000000.0,
            "1d": {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "vol": 100, "amount": 1000},
        }
    )
    raw2 = json.dumps(
        {
            "symbol": "000020.SZ",
            "timestamp": 1700100000.0,  # next day
            "1d": {"open": 11.0, "high": 11.5, "low": 10.5, "close": 11.2, "vol": 50, "amount": 500},
        }
    )
    q._parse_ws_payload(raw1)
    q._parse_ws_payload(raw2)
    daily = q.get_daily_bar("000020.SZ")
    assert daily is not None
    assert daily["open"] == 11.0


def test_parse_ws_payload_close_falls_back_to_prev():
    """When 2nd tick lacks a close field, parser should fall back to the
    previous tick's close (verified via daily_bar cache)."""
    q = LiveQuote()
    raw1 = json.dumps(
        {
            "symbol": "000030.SZ",
            "timestamp": 1700000000.0,
            "1d": {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "vol": 100, "amount": 1000},
        }
    )
    raw2 = json.dumps(
        {
            "symbol": "000030.SZ",
            "timestamp": 1700001000.0,
            "1m": {"open": 10.3, "high": 10.6, "low": 10.1},
        }
    )
    q._parse_ws_payload(raw1)
    q._parse_ws_payload(raw2)
    # Daily bar should reflect accumulated state with close = 10.2 (prev value).
    daily = q.get_daily_bar("000030.SZ")
    assert daily is not None
    assert daily["close"] == 10.2


def test_parse_ws_payload_updates_minute_bars_queue():
    q = LiveQuote()
    for i in range(3):
        raw = json.dumps(
            {
                "symbol": "000040.SZ",
                "timestamp": 1700000000.0 + i * 60,
                "1m": {"close": 10.0 + i * 0.1, "open": 10.0, "high": 10.5, "low": 9.5, "vol": 100, "amount": 1000},
            }
        )
        q._parse_ws_payload(raw)
    df = q.get_minute_bars("000040.SZ")
    assert len(df) >= 3


# ---------------------------------------------------------------------------
# _build_ws_url
# ---------------------------------------------------------------------------


def test_build_ws_url_returns_string():
    q = LiveQuote()
    url = q._build_ws_url()
    assert isinstance(url, str)


# ---------------------------------------------------------------------------
# _refresh_limits
# ---------------------------------------------------------------------------


def test_refresh_limits_with_valid_data():
    q = LiveQuote()
    df = pd.DataFrame(
        {
            "ts_code": ["000050.SZ", "000051.SZ"],
            "up_limit": [11.0, 22.0],
            "down_limit": [9.0, 18.0],
        }
    )
    fake_fetcher = MagicMock()
    fake_fetcher.fetch_limit_price.return_value = (df, None)
    with patch("quantide.service.livequote.get_data_fetcher", return_value=fake_fetcher):
        q._refresh_limits(datetime.date(2024, 1, 5))
    down, up = q.get_price_limits("000050.SZ")
    assert up == 11.0
    assert down == 9.0
    # Second asset should also be there.
    down2, up2 = q.get_price_limits("000051.SZ")
    assert up2 == 22.0
    assert down2 == 18.0


def test_refresh_limits_handles_exception():
    q = LiveQuote()
    with patch("quantide.service.livequote.get_data_fetcher", side_effect=Exception("boom")):
        # Should swallow the exception, not raise.
        q._refresh_limits(datetime.date(2024, 1, 6))


def test_refresh_limits_handles_none_result():
    q = LiveQuote()
    fake_fetcher = MagicMock()
    fake_fetcher.fetch_limit_price.return_value = (None, None)
    with patch("quantide.service.livequote.get_data_fetcher", return_value=fake_fetcher):
        q._refresh_limits(datetime.date(2024, 1, 7))
    # No data → no limits set
    assert q.get_limit("000060.SZ") is None


# ---------------------------------------------------------------------------
# _cache_and_broadcast / _cache_limits / _cache_limits_and_broadcast
# ---------------------------------------------------------------------------


def test_cache_and_broadcast_stores_quote():
    q = LiveQuote()
    q._cache_and_broadcast({"000070.SZ": {"price": 7.0}})
    assert q.get_quote("000070.SZ") is not None


def test_cache_limits_stores_data():
    q = LiveQuote()
    q._cache_limits({"000080.SZ": {"up": 8.0, "down": 7.0}})
    assert q.get_limit("000080.SZ") == {"up": 8.0, "down": 7.0}


def test_cache_limits_handles_none():
    q = LiveQuote()
    # Should not raise.
    q._cache_limits(None)


def test_cache_limits_and_broadcast():
    q = LiveQuote()
    q._cache_limits_and_broadcast({"000090.SZ": {"up": 9.0, "down": 8.0}})
    assert q.get_limit("000090.SZ") == {"up": 9.0, "down": 8.0}


def test_cache_limits_and_broadcast_with_none():
    q = LiveQuote()
    # Should not raise.
    q._cache_limits_and_broadcast(None)


# ---------------------------------------------------------------------------
# start / stop — without opening websocket
# ---------------------------------------------------------------------------


def test_start_is_idempotent():
    q = LiveQuote()
    q.start()
    # First start marks as running. Second start should be a no-op (return early).
    initial_state = q._is_running
    q.start()
    assert q._is_running == initial_state


def test_start_then_stop_resets_running():
    q = LiveQuote()
    q.start()
    q.stop()
    assert q.is_running is False


def test_stop_when_not_running_is_noop():
    q = LiveQuote()
    assert q.is_running is False
    q.stop()  # Should not raise.
    assert q.is_running is False


# ---------------------------------------------------------------------------
# _to_float helper
# ---------------------------------------------------------------------------


def test_to_float_handles_various_types():
    q = LiveQuote()
    assert q._to_float(1.5) == 1.5
    assert q._to_float("2.5") == 2.5
    assert q._to_float(None, 99.0) == 99.0
    assert q._to_float("not-a-number", 99.0) == 99.0
    assert q._to_float(0) == 0.0
