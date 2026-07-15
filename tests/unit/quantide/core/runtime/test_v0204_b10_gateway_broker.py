"""B10-gateway-broker: Tests for missing lines in quantide/core/runtime/gateway_broker.py.

Targets specific missing branches:
- _maybe_attach_forming_bar: end_date != today (185), end_dt <= 9:30 (187), bar is None (190)
- _now: clock is not None (601)
- _compute_scheduled_at: post_auction window (611)
- _estimate_limit_price: scheduled_at non-datetime (673), KeyError (674-675), calendar exception (686-687)
- _resolve_price: quote is falsy (1081-1082), quote keys (1083-1087)
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import pytest

import quantide.core.runtime.gateway_broker as gb_mod
from quantide.core.enums import OrderSide
from quantide.core.runtime.gateway_broker import (
    GatewayBrokerAdapter,
    GatewayBrokerWrapper,
)
from quantide.core.ports import OrderRequest


def _make_wrapper() -> GatewayBrokerWrapper:
    """Build a GatewayBrokerWrapper with a dummy adapter."""
    wrapper = GatewayBrokerWrapper(object())  # type: ignore[arg-type]
    return wrapper


# ---------------------------------------------------------------------------
# _maybe_attach_forming_bar: end_date != today (185), end_dt <= 9:30 (187),
# bar is None (190)
# ---------------------------------------------------------------------------


def test_maybe_attach_forming_bar_returns_hist_when_end_date_not_today():
    """[AC-NFR1101-01] Returns hist unchanged when end_date != today (line 185)."""
    wrapper = _make_wrapper()
    hist = MagicMock()
    end_date = dt.date(2024, 1, 1)
    with patch.object(wrapper, "_today", return_value=dt.date(2024, 6, 1)):
        result = wrapper._maybe_attach_forming_bar("A", hist, end_date, None, 5)
    assert result is hist


def test_maybe_attach_forming_bar_returns_hist_when_end_dt_before_open():
    """[AC-NFR1101-01] Returns hist when end_dt.time() <= 9:30 (line 187)."""
    wrapper = _make_wrapper()
    hist = MagicMock()
    today = dt.date(2024, 6, 1)
    end_dt = dt.datetime(2024, 6, 1, 9, 0)  # before 9:30
    with patch.object(wrapper, "_today", return_value=today):
        result = wrapper._maybe_attach_forming_bar("A", hist, today, end_dt, 5)
    assert result is hist


def test_maybe_attach_forming_bar_returns_prev_bars_when_bar_none():
    """[AC-NFR1101-01] Returns _provider_get_bars when live_quote bar is None (line 190)."""
    wrapper = _make_wrapper()
    wrapper._history_provider = None  # attribute referenced at line 191
    hist = MagicMock()
    today = dt.date(2024, 6, 1)
    end_dt = dt.datetime(2024, 6, 1, 10, 0)  # after 9:30
    prev_date = dt.date(2024, 5, 31)
    expected = MagicMock()
    with patch.object(wrapper, "_today", return_value=today), \
         patch.object(gb_mod.live_quote, "get_daily_bar", return_value=None), \
         patch.object(wrapper, "_previous_trade_date", return_value=prev_date), \
         patch.object(wrapper, "_provider_get_bars", return_value=expected) as mock_get:
        result = wrapper._maybe_attach_forming_bar("A", hist, today, end_dt, 5)
    assert result is expected
    mock_get.assert_called_once()


# ---------------------------------------------------------------------------
# _now: clock is not None (601)
# ---------------------------------------------------------------------------


def test_now_returns_clock_when_set():
    """[AC-NFR1101-01] _now returns _clock when set (line 601)."""
    wrapper = _make_wrapper()
    now = dt.datetime(2024, 6, 1, 10, 30)
    wrapper.set_clock(now)
    assert wrapper._now() == now


# ---------------------------------------------------------------------------
# _compute_scheduled_at: post_auction window (611)
# ---------------------------------------------------------------------------


def test_compute_scheduled_at_post_auction_window():
    """[AC-NFR1101-01] post_auction window combines next trade date with 9:30:00.001 (line 611)."""
    wrapper = _make_wrapper()
    wrapper._live_execution_window = "post_auction"
    today = dt.date(2024, 6, 3)  # Monday
    next_trade = dt.date(2024, 6, 4)
    with patch.object(wrapper, "_today", return_value=today), \
         patch.object(gb_mod.calendar, "day_shift", return_value=next_trade):
        result = wrapper._compute_scheduled_at()
    assert result.date() == next_trade
    assert result.time() == dt.time(9, 30, 0, 1000)


# ---------------------------------------------------------------------------
# _estimate_limit_price: scheduled_at non-datetime (673), KeyError (674-675),
# calendar exception (686-687)
# ---------------------------------------------------------------------------


def test_estimate_limit_price_handles_non_datetime_scheduled_at():
    """[AC-NFR1101-01] target_date set from non-datetime scheduled_at (line 673)."""
    wrapper = _make_wrapper()
    order = {
        "asset": "A",
        "scheduled_at": dt.date(2024, 6, 4),  # date, not datetime -> line 673
        "execution_window": "auction",
        "price": 10.0,
        "slippage": 0.0,
    }
    with patch.object(gb_mod.daily_bars, "get_bars") as mock_get:
        mock_get.return_value = MagicMock(
            is_empty=MagicMock(return_value=False),
            row=MagicMock(return_value={"close": 10.5}),
        )
        result = wrapper._estimate_limit_price(order)
    assert result == 10.5


def test_estimate_limit_price_handles_key_error_for_scheduled_at():
    """[AC-NFR1101-01] Missing scheduled_at key sets target_date=None (674-675)."""
    wrapper = _make_wrapper()
    order = {
        "asset": "A",
        # no scheduled_at key -> KeyError -> target_date=None
        "execution_window": "post_auction",
        "price": 10.0,
        "slippage": 0.0,
    }
    with patch.object(wrapper, "_today", return_value=dt.date(2024, 6, 4)), \
         patch.object(gb_mod.daily_bars, "get_bars") as mock_get:
        mock_get.return_value = MagicMock(
            is_empty=MagicMock(return_value=False),
            row=MagicMock(return_value={"open": 11.0}),
        )
        result = wrapper._estimate_limit_price(order)
    assert result == 11.0


def test_estimate_limit_price_handles_calendar_exception_in_auction():
    """[AC-NFR1101-01] calendar.day_shift exception in auction path (686-687)."""
    wrapper = _make_wrapper()
    order = {
        "asset": "A",
        "scheduled_at": dt.datetime(2024, 6, 4, 9, 25),
        "execution_window": "auction",
        "price": 10.0,
        "slippage": 0.0,
    }
    with patch.object(gb_mod.calendar, "day_shift", side_effect=RuntimeError("cal error")), \
         patch.object(gb_mod.daily_bars, "get_bars") as mock_get:
        mock_get.return_value = MagicMock(
            is_empty=MagicMock(return_value=False),
            row=MagicMock(return_value={"close": 9.8}),
        )
        result = wrapper._estimate_limit_price(order)
    # end_date falls back to scheduled_at - 1 day; daily_bars.get_bars returns 9.8
    assert result == 9.8


# ---------------------------------------------------------------------------
# _resolve_price: quote falsy (1081-1082), quote keys (1083-1087)
# ---------------------------------------------------------------------------


def test_resolve_price_returns_zero_when_quote_falsy():
    """[AC-NFR1101-01] _resolve_price returns 0.0 when quote is falsy (1081-1082)."""
    adapter = GatewayBrokerAdapter(MagicMock())
    request = OrderRequest(
        asset="A",
        side=OrderSide.BUY,
        value=100,
        style="shares",
        price=0,
        order_time=None,
        timeout=0.5,
        extra={},
    )
    with patch.object(gb_mod.live_quote, "get_quote", return_value={}):
        result = adapter._resolve_price(request)
    assert result == 0.0


def test_resolve_price_returns_value_from_quote_keys():
    """[AC-NFR1101-01] _resolve_price returns first positive value from price/open/high/low (1083-1087)."""
    adapter = GatewayBrokerAdapter(MagicMock())
    request = OrderRequest(
        asset="A",
        side=OrderSide.BUY,
        value=100,
        style="shares",
        price=0,
        order_time=None,
        timeout=0.5,
        extra={},
    )
    quote = {"price": 0, "open": 0, "high": 12.5, "low": 10.0}
    with patch.object(gb_mod.live_quote, "get_quote", return_value=quote):
        result = adapter._resolve_price(request)
    assert result == 12.5
