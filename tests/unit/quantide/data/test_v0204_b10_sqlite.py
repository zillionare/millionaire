"""B10-sqlite: Tests for missing lines in quantide/data/sqlite.py.

Targets specific missing branches:
- get_order: returns None when no order found (299)
- get_strategy_logs: start/end date filters (427-431)
- get_backtest_logs: start/end date filters + .rows branch (469-473, 480)
- get_trade: returns None when no trade found (500)
- query_trade: returns None when no trades found (532)
- get_asset: datetime conversion (605)
- delete_portfolio (731)
- get_portfolios_by_strategy: empty result (761-762)
"""

from __future__ import annotations

import datetime as dt

import pytest

from quantide.core.enums import BidType, BrokerKind, OrderSide
from quantide.data.models.entities import (
    Asset,
    BacktestLogEntry,
    Order,
    Portfolio,
    Position,
    StrategyLog,
    Trade,
)


def _seed_portfolio(db, portfolio_id: str = "pf1", name: str = "") -> Portfolio:
    """Insert a portfolio and return it."""
    pf = Portfolio(portfolio_id, BrokerKind.BACKTEST, dt.date(2024, 1, 1), name=name)
    db.insert_portfolio(pf)
    return pf


# ---------------------------------------------------------------------------
# get_order: returns None when not found (line 299)
# ---------------------------------------------------------------------------


def test_get_order_returns_none_when_not_found(db):
    """[AC-NFR1101-01] get_order returns None when qtoid not in db (line 299)."""
    result = db.get_order("nonexistent-qtoid")
    assert result is None


# ---------------------------------------------------------------------------
# get_strategy_logs: start/end date filters (427-431)
# ---------------------------------------------------------------------------


def test_get_strategy_logs_filters_by_start_and_end_dates(db):
    """[AC-NFR1101-01] get_strategy_logs applies start/end date filters (427-431)."""
    _seed_portfolio(db, "pf-strat", name="StratA")
    db.insert_strategy_logs([
        StrategyLog("pf-strat", dt.datetime(2024, 1, 10), "k", 1.0),
        StrategyLog("pf-strat", dt.datetime(2024, 1, 20), "k", 2.0),
        StrategyLog("pf-strat", dt.datetime(2024, 1, 30), "k", 3.0),
    ])
    result = db.get_strategy_logs(
        portfolio_id="pf-strat",
        start=dt.date(2024, 1, 15),
        end=dt.date(2024, 1, 25),
    )
    assert result.height == 1


# ---------------------------------------------------------------------------
# get_backtest_logs: start/end date filters + .rows branch (469-473, 480)
# ---------------------------------------------------------------------------


def test_get_backtest_logs_filters_by_dates_and_rows_branch(db):
    """[AC-NFR1101-01] get_backtest_logs applies date filters (469-473) and .rows branch (480)."""
    _seed_portfolio(db, "pf-bt", name="StratB")
    db.insert_backtest_logs([
        BacktestLogEntry("e1", "pf-bt", dt.datetime(2024, 1, 10), "INFO", "src", "msg1"),
        BacktestLogEntry("e2", "pf-bt", dt.datetime(2024, 1, 20), "INFO", "src", "msg2"),
    ])
    # With date filter (lines 469-473)
    result_filtered = db.get_backtest_logs(
        portfolio_id="pf-bt",
        start=dt.date(2024, 1, 15),
        end=dt.date(2024, 1, 25),
    )
    assert result_filtered.height == 1
    # Without any filter -> uses .rows branch (line 480)
    result_all = db.get_backtest_logs()
    assert result_all.height >= 2


# ---------------------------------------------------------------------------
# get_trade: returns None when not found (line 500)
# ---------------------------------------------------------------------------


def test_get_trade_returns_none_when_not_found(db):
    """[AC-NFR1101-01] get_trade returns None when tid not found (line 500)."""
    result = db.get_trade("nonexistent-tid")
    assert result is None


# ---------------------------------------------------------------------------
# query_trade: returns None when no trades found (line 532)
# ---------------------------------------------------------------------------


def test_query_trade_returns_none_when_no_trades_found(db):
    """[AC-NFR1101-01] query_trade returns None when filter matches no trades (line 532)."""
    result = db.query_trade(qtoid="nonexistent-qtoid")
    assert result is None


# ---------------------------------------------------------------------------
# get_asset: datetime conversion (line 605)
# ---------------------------------------------------------------------------


def test_get_asset_converts_datetime_to_date(db):
    """[AC-NFR1101-01] get_asset converts datetime dt to date (line 605)."""
    _seed_portfolio(db, "pf-asset")
    db.upsert_asset(Asset("pf-asset", dt.date(2024, 1, 15), 100, 80, 0, 20, 100))
    # Pass datetime instead of date; line 605 should convert it
    result = db.get_asset(dt=dt.datetime(2024, 1, 15, 10, 30), portfolio_id="pf-asset")
    assert result is not None
    assert result.portfolio_id == "pf-asset"


# ---------------------------------------------------------------------------
# get_portfolios_by_strategy: empty result (761-762)
# ---------------------------------------------------------------------------


def test_get_portfolios_by_strategy_returns_empty_when_no_match(db):
    """[AC-NFR1101-01] get_portfolios_by_strategy returns empty DataFrame when no match (761-762)."""
    result = db.get_portfolios_by_strategy("NonExistentStrategy")
    assert result.is_empty()
