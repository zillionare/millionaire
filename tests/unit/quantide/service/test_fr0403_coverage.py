"""FR-0403 coverage tests for mock-only bar feed and live quote boundaries."""

import datetime
import json
from types import SimpleNamespace

import polars as pl
import pytest

from quantide.service.datafeed import BarsFeedImpl
from quantide.service.livequote import LiveQuote


class _HistoryPort:
    """FR-0403 history port double returning a fixed daily bar."""

    def get_bars_in_range(self, **_kwargs):
        return pl.DataFrame(
            {
                "date": [datetime.datetime(2024, 1, 2)],
                "asset": ["000001.SZ"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.0],
                "close": [10.5],
                "volume": [100],
            }
        )


@pytest.fixture
def quote() -> LiveQuote:
    """FR-0403: construct a fresh in-memory quote singleton without a network worker."""
    LiveQuote._instance = None
    instance = LiveQuote()
    yield instance
    instance.stop()
    LiveQuote._instance = None


def test_bars_feed_normalizes_history_port_response() -> None:
    """FR-0403 AC-1: history bars are normalized to the documented standard columns."""
    bars = BarsFeedImpl(daily_bars=_HistoryPort()).get_bars(
        "000001.SZ", datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)
    )

    assert bars.columns == [
        "asset", "frame", "open", "high", "low", "close", "volume", "amount",
        "adjust", "is_st", "up_limit", "down_limit",
    ]
    assert bars.row(0, named=True)["close"] == 10.5
    assert bars.row(0, named=True)["is_st"] is False


def test_bars_feed_returns_typed_empty_frame_when_history_is_absent() -> None:
    """FR-0403 AC-2: a feed without history has an explicit empty frame result."""
    bars = BarsFeedImpl().get_bars("missing", datetime.date(2024, 1, 1))

    assert bars.is_empty()
    assert bars.schema["asset"] == pl.String


def test_live_quote_payload_updates_snapshot_and_malformed_input_preserves_cache(quote) -> None:
    """FR-0403 AC-3: valid payloads populate snapshots while malformed payloads do not pollute cache."""
    raw = json.dumps(
        {
            "symbol": "000001.SZ",
            "timestamp": 1_704_153_600,
            "1m": {"open": "10", "high": "11", "low": "9", "close": "10.5"},
            "1d": {"open": "10", "high": "11", "low": "9", "close": "10.5", "vol": 3},
        }
    )
    quote._cache_and_broadcast(quote._parse_ws_payload(raw))
    before = quote.all_quotes.copy()
    snapshot = quote.snapshot(["000001.SZ", "unknown"])

    assert snapshot["000001.SZ"].price == 10.5
    assert "unknown" not in snapshot
    assert quote._parse_ws_payload("not-json") == {}
    assert quote.all_quotes == before


def test_live_quote_builds_websocket_url_and_tracks_subscriptions(monkeypatch, quote) -> None:
    """FR-0403 AC-4/5: subscriptions are local and HTTPS gateway URLs become WSS URLs."""
    monkeypatch.setattr(
        "quantide.service.livequote.get_settings",
        lambda: SimpleNamespace(gateway_base_url="https://gateway.example/api"),
    )
    quote.subscribe(["000001.SZ", "000002.SZ"])
    quote.unsubscribe(["000002.SZ"])

    assert quote._build_ws_url() == "wss://gateway.example/api/ws/quotes"
    assert quote._subscribed == {"000001.SZ"}
