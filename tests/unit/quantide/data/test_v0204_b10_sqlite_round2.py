"""B10-sqlite round 2: Additional missing-line tests for sqlite.py.

Targets lines NOT covered by test_v0204_b10_sqlite.py:
- _init_tables: add_column when col not in existing table (151)
- get_trades: dt not None -> query_trades_by_date (545-546), dt None -> trades_all (548)
- query_trades_by_date: datetime conversion (562-563), where clause (565-570),
  rows_where (572), empty df (574-575), cast (577)
- get_portfolios_by_strategy: non-empty result with cast (759, 765-767)
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import tempfile
from pathlib import Path

import polars as pl
import pytest

from quantide.core.enums import BidType, BrokerKind, OrderSide
from quantide.data.models.entities import (
    Asset,
    Order,
    Portfolio,
    Trade,
)
from quantide.data.sqlite import db as _db


def _seed_portfolio(db, portfolio_id: str = "pf1", name: str = "") -> Portfolio:
    """Insert a portfolio and return it."""
    pf = Portfolio(portfolio_id, BrokerKind.BACKTEST, dt.date(2024, 1, 1), name=name)
    db.insert_portfolio(pf)
    return pf


def _seed_order(db, portfolio_id: str, qtoid: str = "q1") -> Order:
    """Insert an order and return it (needed for trade FK)."""
    order = Order(
        portfolio_id=portfolio_id,
        asset="A",
        price=10.0,
        shares=100,
        side=OrderSide.BUY,
        bid_type=BidType.MARKET,
        tm=dt.datetime(2024, 1, 15, 10, 0),
        qtoid=qtoid,
    )
    db.insert_order(order)
    return order


def _make_trade(portfolio_id: str, tid: str, qtoid: str, asset: str = "A") -> Trade:
    return Trade(
        portfolio_id=portfolio_id,
        tid=tid,
        qtoid=qtoid,
        foid="",
        asset=asset,
        shares=100,
        price=10.0,
        amount=1000.0,
        tm=dt.datetime(2024, 1, 15, 10, 30),
        side=OrderSide.BUY,
        cid="",
        fee=0.0,
    )


# ---------------------------------------------------------------------------
# _init_tables: add_column when col not in existing table (151)
# ---------------------------------------------------------------------------


def test_init_tables_adds_missing_column_to_existing_table():
    """[AC-NFR1101-01] _init_tables adds missing columns to a pre-existing table (line 151).

    Uses a fresh temp DB so we can control table state. We create the 'trades'
    table manually with only the pk column, then re-run init so the missing-col
    branch (line 151) executes.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        # First init creates all tables properly
        _db._initialized = False
        _db.init(db_path)
        # Drop and recreate trades with only tid column to simulate a partial table
        conn = sqlite3.connect(str(db_path))
        conn.execute("DROP TABLE trades")
        conn.execute("CREATE TABLE trades (tid TEXT PRIMARY KEY)")
        conn.commit()
        cols_before = {row[1] for row in conn.execute("PRAGMA table_info(trades)").fetchall()}
        conn.close()
        assert "tm" not in cols_before

        # Re-run init; is_initialized_for returns False (path same but we reset _initialized),
        # so _init_tables runs again and hits line 151 (t.add_column) for missing cols.
        _db._initialized = False
        _db.init(db_path)

        conn = sqlite3.connect(str(db_path))
        cols_after = {row[1] for row in conn.execute("PRAGMA table_info(trades)").fetchall()}
        conn.close()
        assert "tm" in cols_after


# ---------------------------------------------------------------------------
# get_trades: dt not None -> query_trades_by_date (545-546)
# ---------------------------------------------------------------------------


def test_get_trades_with_date_routes_to_query_trades_by_date(db):
    """[AC-NFR1101-01] get_trades with dt routes to query_trades_by_date (545-546)."""
    _seed_portfolio(db, "pf-trades")
    _seed_order(db, "pf-trades", "q-trades")
    db.insert_trades([_make_trade("pf-trades", "t1", "q-trades")])
    result = db.get_trades(dt=dt.date(2024, 1, 15))
    assert result.height == 1
    assert result.row(0, named=True)["tid"] == "t1"


def test_get_trades_with_date_and_portfolio_filter(db):
    """[AC-NFR1101-01] get_trades with dt and portfolio_id applies both filters (568-570)."""
    # Use a unique date to avoid interference from session-scoped db
    unique_date = dt.date(2024, 3, 15)
    _seed_portfolio(db, "pf-filter-a")
    _seed_portfolio(db, "pf-filter-b")
    _seed_order(db, "pf-filter-a", "q-filter-a")
    _seed_order(db, "pf-filter-b", "q-filter-b")
    trade_a = _make_trade("pf-filter-a", "t-fa", "q-filter-a")
    trade_a.tm = dt.datetime(2024, 3, 15, 10, 30)
    trade_b = _make_trade("pf-filter-b", "t-fb", "q-filter-b")
    trade_b.tm = dt.datetime(2024, 3, 15, 11, 0)
    db.insert_trades([trade_a])
    db.insert_trades([trade_b])
    # Filter by date AND portfolio_id
    result = db.get_trades(dt=unique_date, portfolio_id="pf-filter-a")
    assert result.height == 1
    assert result.row(0, named=True)["portfolio_id"] == "pf-filter-a"


# ---------------------------------------------------------------------------
# get_trades: dt None -> trades_all (548)
# ---------------------------------------------------------------------------


def test_get_trades_without_date_routes_to_trades_all(db):
    """[AC-NFR1101-01] get_trades with dt=None routes to trades_all (line 548)."""
    _seed_portfolio(db, "pf-all")
    _seed_order(db, "pf-all", "q-all")
    db.insert_trades([_make_trade("pf-all", "t1", "q-all")])
    result = db.get_trades()
    assert result.height >= 1


# ---------------------------------------------------------------------------
# query_trades_by_date: datetime conversion (562-563), cast (577)
# ---------------------------------------------------------------------------


def test_query_trades_by_date_converts_datetime_to_date(db):
    """[AC-NFR1101-01] query_trades_by_date converts datetime dt to date (562-563), casts tm (577)."""
    # Use a unique date to avoid interference from session-scoped db
    unique_date = dt.date(2024, 5, 20)
    _seed_portfolio(db, "pf-dtc")
    _seed_order(db, "pf-dtc", "q-dtc")
    trade = _make_trade("pf-dtc", "t-dtc", "q-dtc")
    trade.tm = dt.datetime(2024, 5, 20, 10, 30)
    db.insert_trades([trade])
    # Pass a datetime instead of a date; line 562-563 should convert it
    result = db.query_trades_by_date(dt.datetime(2024, 5, 20, 12, 0))
    assert result.height == 1
    # Verify the cast (line 577) - tm column should be Datetime
    assert result.schema["tm"] == pl.Datetime


# ---------------------------------------------------------------------------
# get_portfolios_by_strategy: non-empty result with cast (759, 765-767)
# ---------------------------------------------------------------------------


def test_get_portfolios_by_strategy_returns_matching_with_date_cast(db):
    """[AC-NFR1101-01] get_portfolios_by_strategy returns matching rows with date cast (759, 765-767)."""
    _seed_portfolio(db, "pf-strat1", name="MyStrategy")
    result = db.get_portfolios_by_strategy("MyStrategy")
    assert result.height == 1
    # start/end should be Date type after cast (lines 765-767)
    assert result.schema["start"] == pl.Date
    assert result.schema["end"] == pl.Date
