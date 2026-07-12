"""v0.2-003 FR-0207 structural port and DTO contract tests."""

import asyncio
import datetime as dt

from quantide.core.domain import MarketEvent, QuoteSnapshot
from quantide.core.enums import OrderSide
from quantide.core.ports import ExecutionResult, OrderAck, OrderRequest
from quantide.core.ports.broker import BrokerPort
from quantide.core.ports.data_fetcher import DataFetcherPort
from quantide.core.ports.market_data import MarketDataPort


class MarketFake:
    def start(self): pass
    def stop(self): pass
    def subscribe(self, symbols): self.symbols = symbols
    def unsubscribe(self, symbols): self.symbols = []
    async def stream(self):
        yield MarketEvent("000001.SZ", "tick", dt.datetime(2026, 7, 10), {})
    def snapshot(self, symbols): return {symbol: QuoteSnapshot(symbol, 10.0) for symbol in symbols}


def test_port_protocols_expose_the_documented_structural_method_sets():
    """FR-0207 AC-1/AC-3/AC-5: consumers rely on method shape, not ABC construction."""
    assert {"record", "submit", "buy", "sell", "cancel", "cancel_all", "query_positions", "query_assets", "query_orders", "query_trades"} <= set(BrokerPort.__dict__)
    assert {"fetch_calendar", "fetch_stock_list", "fetch_adjust_factor", "fetch_bars", "fetch_limit_price", "fetch_st_info", "fetch_bars_ext"} <= set(DataFetcherPort.__dict__)
    assert {"start", "stop", "subscribe", "unsubscribe", "stream", "snapshot"} <= set(MarketDataPort.__dict__)


def test_port_dto_mutable_defaults_are_isolated_and_market_fake_is_consumable():
    """FR-0207 AC-2/AC-4: port data containers and async market stream do not leak state."""
    first, second = OrderRequest("000001.SZ", OrderSide.BUY, 100), OrderRequest("000002.SZ", OrderSide.SELL, 100)
    ack_first, ack_second = OrderAck("qt-1", "submitted"), OrderAck("qt-2", "submitted")
    result_first, result_second = ExecutionResult("qt-1"), ExecutionResult("qt-2")
    first.extra["source"] = "test"
    ack_first.trades.append("trade")
    result_first.trades.append("trade")

    assert (second.extra, ack_second.trades, result_second.trades) == ({}, [], [])
    fake = MarketFake()
    fake.subscribe(["000001.SZ"])
    event = asyncio.run(anext(fake.stream()))
    assert (event.symbol, fake.snapshot([event.symbol])[event.symbol].price) == ("000001.SZ", 10.0)
