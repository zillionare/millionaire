"""Smoke tests for LiveQuotePortAdapter (B-1b).

Tests the adapter using the real LiveQuote singleton, without mocking
LiveQuote internals. Only the adapter protocol surface is verified.
"""

import asyncio

import pytest

from quantide.core.domain import MarketEvent, QuoteSnapshot
from quantide.core.ports import MarketDataPort
from quantide.service.livequote import LiveQuote, live_quote
from quantide.service.quote_port_adapter import LiveQuotePortAdapter


def _reset_live_quote():
    """Reset LiveQuote singleton state for isolated tests."""
    live_quote._subscribed = set()
    live_quote._quotes = {}
    live_quote._is_running = False


class TestLiveQuotePortAdapterProtocol:
    """Verify LiveQuotePortAdapter satisfies MarketDataPort."""

    def setup_method(self):
        _reset_live_quote()
        self.adapter = LiveQuotePortAdapter(live_quote)

    def test_implements_market_data_port(self):
        """Adapter exposes all MarketDataPort methods."""
        assert hasattr(self.adapter, "start")
        assert hasattr(self.adapter, "stop")
        assert hasattr(self.adapter, "subscribe")
        assert hasattr(self.adapter, "unsubscribe")
        assert hasattr(self.adapter, "stream")
        assert hasattr(self.adapter, "snapshot")

    def test_subscribe_adds_symbols(self):
        self.adapter.subscribe(["000001.SZ", "600000.SH"])
        assert "000001.SZ" in self.adapter._subscribed
        assert "600000.SH" in self.adapter._subscribed

    def test_subscribe_ignores_empty_strings(self):
        self.adapter.subscribe(["", "000001.SZ"])
        assert "" not in self.adapter._subscribed
        assert "000001.SZ" in self.adapter._subscribed

    def test_unsubscribe_removes_symbols(self):
        self.adapter.subscribe(["000001.SZ", "600000.SH"])
        self.adapter.unsubscribe(["000001.SZ"])
        assert "000001.SZ" not in self.adapter._subscribed
        assert "600000.SH" in self.adapter._subscribed

    def test_unsubscribe_missing_symbol_is_noop(self):
        self.adapter.subscribe(["000001.SZ"])
        self.adapter.unsubscribe(["999999.SZ"])  # should not raise
        assert "000001.SZ" in self.adapter._subscribed

    def test_snapshot_empty_quotes(self):
        """No quotes loaded -> snapshot returns empty dict."""
        result = self.adapter.snapshot(["000001.SZ"])
        assert result == {}

    def test_start_stop_idempotent(self):
        """start/stop can be called without error even without real WS."""
        # LiveQuote.start() launches a daemon thread; stop() signals it.
        # We just verify the adapter does not raise.
        self.adapter.stop()  # stop without start is safe


class TestLiveQuotePortAdapterStream:
    """Verify stream boundary behavior."""

    def setup_method(self):
        _reset_live_quote()
        self.adapter = LiveQuotePortAdapter(live_quote)

    @pytest.mark.asyncio
    async def test_stream_returns_async_generator(self):
        """stream() returns an async iterator of MarketEvent."""
        gen = self.adapter.stream()
        assert asyncio.iscoroutine(gen) or hasattr(gen, "__aiter__")
        # Clean up: stop the stream immediately
        self.adapter._streaming = False

    @pytest.mark.asyncio
    async def test_stream_double_start_raises(self):
        """Iterating a second stream() while first is active raises RuntimeError."""
        gen1 = self.adapter.stream()
        # Start consuming the first stream (executes body up to first yield)
        task = asyncio.create_task(gen1.__anext__())
        await asyncio.sleep(0)
        assert self.adapter._stream_queue is not None

        # A second stream() call yields a new generator; iterating it raises
        gen2 = self.adapter.stream()
        with pytest.raises(RuntimeError, match="stream already started"):
            await gen2.__anext__()

        # Cleanup
        self.adapter._streaming = False
        self.adapter._stream_queue = None
        self.adapter._stream_loop = None
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
