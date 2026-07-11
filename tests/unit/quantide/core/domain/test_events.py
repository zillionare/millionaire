"""v0.2-003 FR-0201 event DTO contract tests."""

import datetime as dt

from quantide.core.domain import ErrorEvent, MarketEvent, OrderEvent, QuoteSnapshot, TradeEvent


def test_events_preserve_supplied_public_fields():
    """FR-0201 AC-1: complete DTO construction preserves every public value."""
    now = dt.datetime(2026, 7, 10, 9, 30)
    market = MarketEvent("000001.SZ", "tick", now, {"price": 10.5}, "feed", "event-1")
    quote = QuoteSnapshot("000001.SZ", 10.5, 10, 11, 9, 100, 1050, now)
    order = OrderEvent("order-1", "portfolio-1", "filled", now, 100, 10.5, "done")
    trade = TradeEvent("trade-1", "order-1", "portfolio-1", "000001.SZ", "buy", 100, 10.5, 1050, now)
    error = ErrorEvent("BAD", "gateway", "unavailable", True, {"retry_after": 1})

    assert (market.symbol, market.payload, market.source, market.event_id) == ("000001.SZ", {"price": 10.5}, "feed", "event-1")
    assert (quote.price, quote.amount, quote.ts) == (10.5, 1050, now)
    assert (order.filled_qty, order.filled_price, order.reason) == (100, 10.5, "done")
    assert (trade.trade_id, trade.amount, trade.ts) == ("trade-1", 1050, now)
    assert (error.code, error.category, error.message, error.retryable, error.details) == ("BAD", "gateway", "unavailable", True, {"retry_after": 1})


def test_event_defaults_and_error_details_are_instance_isolated():
    """FR-0201 AC-2/AC-3: documented defaults and mutable details isolation."""
    now = dt.datetime(2026, 7, 10)
    event = MarketEvent("000001.SZ", "bar", now, {})
    order = OrderEvent("order-1", "portfolio-1", "pending", now)
    first, second = ErrorEvent("A", "x", "first"), ErrorEvent("B", "x", "second")
    first.details["context"] = "only-first"

    assert (event.source, event.event_id) == ("unknown", "")
    assert (order.filled_qty, order.filled_price, order.reason) == (0.0, 0.0, "")
    assert first.retryable is False
    assert second.details == {}
