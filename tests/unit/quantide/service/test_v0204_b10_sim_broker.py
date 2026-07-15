"""B10-sim-broker: Tests for missing lines in quantide/service/sim_broker.py.

Targets specific missing branches:
- _validate_data_consistency: portfolio missing with position records (487)
- positions/cash/principal properties (607, 611, 615)
- _match_orders_for_asset: remaining_shares<=0 continue (674-675)
- _try_match: last_price<=0 / buy up_limit / sell down_limit (787-789, 800)
- _concat_with_forming: cast exception drop col (416-417), empty hist return (388)
"""

from __future__ import annotations

import datetime as dt
import threading
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

import quantide.service.sim_broker as sb_mod
from quantide.core.enums import BidType, OrderSide
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
    return broker


# ---------------------------------------------------------------------------
# _validate_data_consistency: portfolio missing but has position records (487)
# ---------------------------------------------------------------------------


def test_validate_data_consistency_raises_when_portfolio_missing_but_has_positions():
    """[AC-NFR1101-01] Portfolio missing but has position records raises (line 487)."""
    broker = _make_broker()
    empty_positions_df = pl.DataFrame({"a": [1, 2]})  # non-empty df
    with patch.object(sb_mod.db, "get_portfolio", return_value=None), \
         patch.object(sb_mod.db, "get_asset", return_value=None), \
         patch.object(sb_mod.db, "get_positions", return_value=empty_positions_df):
        with pytest.raises(RuntimeError, match="Data Inconsistency"):
            broker._validate_data_consistency()


# ---------------------------------------------------------------------------
# positions / cash / principal properties (607, 611, 615)
# ---------------------------------------------------------------------------


def test_positions_property_returns_list_of_positions():
    """[AC-NFR1101-01] positions property returns list of position values (line 607)."""
    broker = _make_broker()
    pos1 = MagicMock()
    pos2 = MagicMock()
    broker._positions = {"A": pos1, "B": pos2}
    out = broker.positions
    assert len(out) == 2
    assert pos1 in out
    assert pos2 in out


def test_cash_property_returns_cash_value():
    """[AC-NFR1101-01] cash property returns _cash (line 611)."""
    broker = _make_broker()
    broker._cash = 12345.67
    assert broker.cash == 12345.67


def test_principal_property_returns_principal_value():
    """[AC-NFR1101-01] principal property returns _principal (line 615)."""
    broker = _make_broker()
    broker._principal = 999999.0
    assert broker.principal == 999999.0


# ---------------------------------------------------------------------------
# _try_match: last_price <= 0 (787), buy at up_limit (787), sell at down_limit (789)
# ---------------------------------------------------------------------------


def test_try_match_returns_zero_when_last_price_le_zero():
    """[AC-NFR1101-01] _try_match returns (0.0, None) when lastPrice <= 0 (line 787)."""
    broker = _make_broker()
    order = MagicMock()
    order.side = OrderSide.BUY
    quote = {"lastPrice": 0}
    matched, trade = broker._try_match(order, quote, available_shares_limit=100)
    assert matched == 0.0
    assert trade is None


def test_try_match_returns_zero_when_buy_at_up_limit():
    """[AC-NFR1101-01] Buy at up_limit returns (0.0, None) (line 787)."""
    broker = _make_broker()
    broker._limits = {"A": {"down": 9.0, "up": 11.0}}
    order = MagicMock()
    order.side = OrderSide.BUY
    order.asset = "A"
    order.bid_type = BidType.LATEST
    order.price = 0
    order.shares = 100
    order.filled = 0
    quote = {"lastPrice": 11.0}  # at up_limit
    matched, trade = broker._try_match(order, quote, available_shares_limit=100)
    assert matched == 0.0
    assert trade is None


def test_try_match_returns_zero_when_sell_at_down_limit():
    """[AC-NFR1101-01] Sell at down_limit returns (0.0, None) (line 789)."""
    broker = _make_broker()
    broker._limits = {"A": {"down": 9.0, "up": 11.0}}
    order = MagicMock()
    order.side = OrderSide.SELL
    order.asset = "A"
    order.bid_type = BidType.LATEST
    order.price = 0
    order.shares = 100
    order.filled = 0
    quote = {"lastPrice": 9.0}  # at down_limit
    matched, trade = broker._try_match(order, quote, available_shares_limit=100)
    assert matched == 0.0
    assert trade is None


def test_try_match_returns_zero_when_fixed_buy_price_below_last():
    """[AC-NFR1101-01] Fixed buy with price < last_price returns (0.0, None) (line 800)."""
    broker = _make_broker()
    order = MagicMock()
    order.side = OrderSide.BUY
    order.asset = "A"
    order.bid_type = BidType.FIXED
    order.price = 9.5
    order.shares = 100
    order.filled = 0
    quote = {"lastPrice": 10.0}
    matched, trade = broker._try_match(order, quote, available_shares_limit=100)
    assert matched == 0.0
    assert trade is None


# ---------------------------------------------------------------------------
# _concat_with_forming: cast exception drop col (416-417)
# ---------------------------------------------------------------------------


def test_concat_with_forming_drops_col_on_cast_exception():
    """[AC-NFR1101-01] _concat_with_forming drops col when cast fails (416-417).

    When forming bar has a non-coercible value in a typed column, the cast
    except-branch drops the column (lines 416-417). The downstream
    ``forming_df.select(hist.columns)`` then raises ColumnNotFoundError
    because the dropped column is absent; we assert that propagation to
    confirm the drop branch was exercised.
    """
    hist = pl.DataFrame({
        "date": [dt.date(2024, 1, 1)],
        "asset": ["A"],
        "open": [10.0],
        "high": [11.0],
        "low": [9.0],
        "close": [10.5],
        "volume": [1000.0],
        "amount": [10500.0],
        "adjust": [1.0],
        "is_st": [False],
        "up_limit": [11.0],
        "down_limit": [9.0],
    })
    # Forming bar has a string in a float column, which will cause cast to fail
    forming = {
        "asset": "A",
        "dt": dt.datetime(2024, 1, 2, 10, 0),
        "open": "not_a_float",  # will cause cast exception -> drop branch (416-417)
        "high": 11.5,
        "low": 9.5,
        "close": 10.8,
        "volume": 500.0,
        "amount": 5400.0,
    }
    with patch.object(sb_mod.live_quote, "_limits", {}):
        # Lines 416-417 (drop on cast exception) are exercised; the subsequent
        # select(hist.columns) propagates ColumnNotFoundError due to the drop.
        with pytest.raises(pl.exceptions.ColumnNotFoundError):
            PaperBroker._concat_with_forming(hist, forming, count=5)


def test_concat_with_forming_returns_hist_when_empty():
    """[AC-NFR1101-01] _concat_with_forming returns hist when empty (line 388)."""
    empty_hist = pl.DataFrame(schema={
        "date": pl.Date,
        "asset": pl.Utf8,
        "open": pl.Float64,
        "close": pl.Float64,
        "adjust": pl.Float64,
        "is_st": pl.Boolean,
        "up_limit": pl.Float64,
        "down_limit": pl.Float64,
    })
    forming = {
        "asset": "A",
        "dt": dt.datetime(2024, 1, 2, 10, 0),
        "close": 10.8,
    }
    with patch.object(sb_mod.live_quote, "_limits", {}):
        result = PaperBroker._concat_with_forming(empty_hist, forming, count=5)
    # When hist is empty, returns hist directly
    assert result is empty_hist
