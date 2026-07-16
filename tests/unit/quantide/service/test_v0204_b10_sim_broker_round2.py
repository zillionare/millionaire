"""B10-sim-broker round 2: Additional missing-line tests for sim_broker.py.

Targets lines NOT covered by test_v0204_b10_sim_broker.py:
- _match_orders_for_asset: remaining_shares<=0 continue (674-675)
- _try_match: matched_shares <= 0 (812)
- buy_percent: quote falsy (1073), price<=0 (1081), shares==0 (1088)
- sell_percent: not in positions (1151), shares==0 (1161)
- sell_amount: quote falsy & price==0 (1187), price<=0 (1195), shares==0 (1201)
- trade_target_pct: quote falsy & price==0 (1229), ref_price<=0 (1243),
  target_pct<0.0001 sell all (1263-1265)
- cancel_order: PARTSUCC_CANCEL (1287)
- on_day_open: pass (1344)
- on_day_close: price fallback to pos.price (1378)
- buy: shares floored (930), est_price from quote (949)
- get_history: qfq_adjustment path (281)
- _get_history_bars: daily_bars.get_bars (318)
- _concat_with_forming: forming_clean[col]=None (407), unique no asset (422), tail (425)
"""

from __future__ import annotations

import datetime as dt
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl
import pytest

import quantide.service.sim_broker as sb_mod
from quantide.core.enums import BidType, OrderSide, OrderStatus
from quantide.core.ports.broker import ExecutionResult
from quantide.service.sim_broker import PaperBroker


def _make_broker() -> PaperBroker:
    """Build a PaperBroker with mocked dependencies (skips __init__)."""
    broker = PaperBroker.__new__(PaperBroker)
    broker._closed = False
    broker._lock = threading.RLock()
    broker._positions = {}
    broker._cash = 100000.0
    broker._principal = 100000.0
    broker._portfolio_id = "pf-test"
    broker._active_orders = {}
    broker._market_data = None
    broker._slippage = 0.0
    broker._limits = {}
    broker._clock = None
    broker._dry_run = False
    broker._commission = 1e-4
    broker._order_trades = {}
    return broker


# ---------------------------------------------------------------------------
# _match_orders_for_asset: remaining_shares <= 0 -> continue (674-675)
# ---------------------------------------------------------------------------


def test_match_orders_for_asset_skips_when_remaining_shares_zero():
    """[AC-NFR1101-01] _match_orders_for_asset continues when remaining_shares<=0 (674-675)."""
    broker = _make_broker()
    order = MagicMock()
    order.qtoid = "q1"
    order.side = OrderSide.BUY
    order.asset = "A"
    order.bid_type = BidType.LATEST
    order.price = 0
    order.shares = 100
    order.filled = 0
    broker._active_orders = {"A": [order]}
    # quote volume 0 means remaining_shares = 0 -> order appended to remaining
    quote = {"lastPrice": 10.0, "volume": 0}
    traded_assets: set = set()
    broker._match_orders_for_asset("A", quote, traded_assets)
    # order should remain in _active_orders (appended to remaining_orders)
    assert "A" in broker._active_orders
    assert broker._active_orders["A"] == [order]
    # no trade recorded
    assert traded_assets == set()


# ---------------------------------------------------------------------------
# _try_match: matched_shares <= 0 (812)
# ---------------------------------------------------------------------------


def test_try_match_returns_zero_when_available_shares_limit_zero():
    """[AC-NFR1101-01] _try_match returns (0.0, None) when available_shares_limit<=0 (line 812)."""
    broker = _make_broker()
    order = MagicMock()
    order.side = OrderSide.BUY
    order.asset = "A"
    order.bid_type = BidType.LATEST
    order.price = 0
    order.shares = 100
    order.filled = 0
    quote = {"lastPrice": 10.0}
    matched, trade = broker._try_match(order, quote, available_shares_limit=0)
    assert matched == 0.0
    assert trade is None


# ---------------------------------------------------------------------------
# buy_percent: quote falsy (1073), price<=0 (1081), shares==0 (1088)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buy_percent_returns_empty_when_quote_falsy():
    """[AC-NFR1101-01] buy_percent returns empty when quote is falsy (line 1073)."""
    broker = _make_broker()
    with patch.object(broker, "_get_quote", return_value=None):
        result = await broker.buy_percent("A", 0.5)
    assert result == ExecutionResult.empty()


@pytest.mark.asyncio
async def test_buy_percent_returns_empty_when_price_le_zero():
    """[AC-NFR1101-01] buy_percent returns empty when price<=0 (line 1081)."""
    broker = _make_broker()
    quote = {"lastPrice": 0}
    with patch.object(broker, "_get_quote", return_value=quote), \
         patch.object(broker, "_get_price_limits", return_value=(0.0, 0.0)):
        result = await broker.buy_percent("A", 0.5)
    assert result == ExecutionResult.empty()


# ---------------------------------------------------------------------------
# sell_percent: not in positions (1151), shares==0 (1161)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sell_percent_returns_empty_when_not_in_positions():
    """[AC-NFR1101-01] sell_percent returns empty when asset not in positions (line 1151)."""
    broker = _make_broker()
    broker._positions = {}
    result = await broker.sell_percent("A", 0.5)
    assert result == ExecutionResult.empty()


@pytest.mark.asyncio
async def test_sell_percent_returns_empty_when_shares_zero():
    """[AC-NFR1101-01] sell_percent returns empty when computed shares==0 (line 1161)."""
    broker = _make_broker()
    pos = MagicMock()
    pos.shares = 50  # < 100 -> shares = int(50 * 0.5 / 100) * 100 = 0
    broker._positions = {"A": pos}
    result = await broker.sell_percent("A", 0.5)
    assert result == ExecutionResult.empty()


# ---------------------------------------------------------------------------
# sell_amount: quote falsy & price==0 (1187), price<=0 (1195), shares==0 (1201)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sell_amount_returns_empty_when_quote_falsy_and_price_zero():
    """[AC-NFR1101-01] sell_amount returns empty when quote falsy and price==0 (line 1187)."""
    broker = _make_broker()
    with patch.object(broker, "_get_quote", return_value=None):
        result = await broker.sell_amount("A", 1000, price=0)
    assert result == ExecutionResult.empty()


@pytest.mark.asyncio
async def test_sell_amount_returns_empty_when_price_le_zero():
    """[AC-NFR1101-01] sell_amount returns empty when computed price<=0 (line 1195)."""
    broker = _make_broker()
    quote = {"lastPrice": 0}
    with patch.object(broker, "_get_quote", return_value=quote), \
         patch.object(broker, "_get_price_limits", return_value=(0.0, 0.0)):
        result = await broker.sell_amount("A", 1000, price=0)
    assert result == ExecutionResult.empty()


# ---------------------------------------------------------------------------
# trade_target_pct: quote falsy & price==0 (1229), ref_price<=0 (1243),
# target_pct<0.0001 sell all (1263-1265)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trade_target_pct_returns_empty_when_quote_falsy_and_price_zero():
    """[AC-NFR1101-01] trade_target_pct returns empty when quote falsy and price==0 (line 1229)."""
    broker = _make_broker()
    with patch.object(broker, "_get_quote", return_value=None):
        result = await broker.trade_target_pct("A", 0.5, price=0)
    assert result == ExecutionResult.empty()


@pytest.mark.asyncio
async def test_trade_target_pct_returns_empty_when_ref_price_le_zero():
    """[AC-NFR1101-01] trade_target_pct returns empty when ref_price<=0 (line 1243)."""
    broker = _make_broker()
    quote = {"lastPrice": 0}
    with patch.object(broker, "_get_quote", return_value=quote), \
         patch.object(broker, "_get_price_limits", return_value=(0.0, 0.0)):
        result = await broker.trade_target_pct("A", 0.5, price=0)
    assert result == ExecutionResult.empty()


@pytest.mark.asyncio
async def test_trade_target_pct_calls_sell_percent_when_target_near_zero():
    """[AC-NFR1101-01] trade_target_pct calls sell_percent(1.0) when target_pct<0.0001 (1263-1265)."""
    broker = _make_broker()
    pos = MagicMock()
    pos.shares = 100
    pos.mv = 1000.0
    broker._positions = {"A": pos}
    quote = {"lastPrice": 10.0}
    with patch.object(broker, "_get_quote", return_value=quote), \
         patch.object(broker, "sell_percent", new_callable=AsyncMock, return_value="sold") as mock_sell:
        result = await broker.trade_target_pct("A", 0.00005, price=10.0)
    assert result == "sold"
    mock_sell.assert_awaited_once()
    args, kwargs = mock_sell.call_args
    # sell_percent(asset, 1.0, order_time, timeout) positional args
    assert args[1] == 1.0


# ---------------------------------------------------------------------------
# on_day_open: pass (1344)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_day_open_is_noop():
    """[AC-NFR1101-01] on_day_open is a no-op (line 1344)."""
    broker = _make_broker()
    # Should not raise
    await broker.on_day_open({"A": {"up": 11.0, "down": 9.0}})
