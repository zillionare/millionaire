"""B08-core-ports-2: Tests for quantide/core/ports/market_data.py."""

from __future__ import annotations

from typing import Protocol as _Protocol

from quantide.core.ports.market_data import MarketDataPort


def test_market_data_port_is_a_protocol():
    assert issubclass(MarketDataPort, _Protocol)


def test_market_data_port_has_start_method():
    assert hasattr(MarketDataPort, "start")


def test_market_data_port_has_stop_method():
    assert hasattr(MarketDataPort, "stop")


def test_market_data_port_has_subscribe_method():
    assert hasattr(MarketDataPort, "subscribe")


def test_market_data_port_has_unsubscribe_method():
    assert hasattr(MarketDataPort, "unsubscribe")


def test_market_data_port_has_stream_method():
    assert hasattr(MarketDataPort, "stream")


def test_market_data_port_has_snapshot_method():
    assert hasattr(MarketDataPort, "snapshot")


class _FakeMarketData:
    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def subscribe(self, symbols):
        pass

    def unsubscribe(self, symbols):
        pass

    async def stream(self):
        if False:
            yield None

    def snapshot(self, symbols):
        return {}


def test_fake_market_data_has_all_required_methods():
    md = _FakeMarketData()
    for name in ("start", "stop", "subscribe", "unsubscribe", "stream", "snapshot"):
        assert callable(getattr(md, name, None)), f"missing {name}"
