"""B09-sim-broker-round2: Targeted coverage for ``quantide/service/sim_broker.py``.

Covers missing branches in ``PaperBroker``:
- ``create`` raises when portfolio already exists
- ``load`` raises when portfolio does not exist
- ``_validate_data_consistency`` inconsistency branches
- ``_get_history_bars`` daily_bars fallback path / empty-history frame
- ``_extract_forming_bar`` returns None when bar_dt != end_date
- ``_concat_with_forming`` returns hist when hist_date_col is None
- ``trade_target_pct`` equality branch (diff == 0)
- ``sell_percent`` clear-all path
"""

from __future__ import annotations

import datetime as dt
import threading
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

import quantide.service.sim_broker as sb_mod
from quantide.core.enums import OrderSide
from quantide.core.ports.broker import ExecutionResult
from quantide.data.models import Position
from quantide.service.sim_broker import PaperBroker


def _make_broker() -> PaperBroker:
    """Build a PaperBroker shell without invoking ``__init__`` (avoids DB / msg_hub)."""
    broker = PaperBroker.__new__(PaperBroker)
    broker._closed = False
    broker._lock = threading.RLock()
    broker._clock = None
    broker._quote_subscription = MagicMock()
    broker._limit_subscription = MagicMock()
    broker._market_data = None
    broker._commission = 1e-4
    broker._stamp_tax = 0.001
    broker._slippage = 0.0
    broker._dry_run = False
    broker._limits = {}
    broker._positions = {}
    broker._active_orders = {}
    broker._order_trades = {}
    broker._principal = 1_000_000
    broker._cash = 1_000_000
    broker._portfolio_id = "p-test"
    broker._portfolio_name = "test"
    broker._info = ""
    return broker


# ---------------------------------------------------------------------------
# create / load classmethod error branches
# ---------------------------------------------------------------------------


def test_create_raises_when_portfolio_already_exists(monkeypatch):
    """[AC-NFR1101-01] create() raises RuntimeError when portfolio exists in DB."""
    monkeypatch.setattr(sb_mod.db, "get_portfolio", lambda pid: MagicMock())
    with pytest.raises(RuntimeError, match="already exists"):
        PaperBroker.create(portfolio_id="dup")


def test_load_raises_when_portfolio_does_not_exist(monkeypatch):
    """[AC-NFR1101-01] load() raises RuntimeError when portfolio is missing in DB."""
    monkeypatch.setattr(sb_mod.db, "get_portfolio", lambda pid: None)
    with pytest.raises(RuntimeError, match="does not exist"):
        PaperBroker.load(portfolio_id="missing")


# ---------------------------------------------------------------------------
# _validate_data_consistency
# ---------------------------------------------------------------------------


def test_validate_data_consistency_raises_when_portfolio_missing_but_asset_exists(monkeypatch):
    """[AC-NFR1101-01] Portfolio missing but asset present -> RuntimeError."""
    broker = _make_broker()
    monkeypatch.setattr(sb_mod.db, "get_portfolio", lambda pid: None)
    monkeypatch.setattr(sb_mod.db, "get_asset", lambda **kw: MagicMock())
    monkeypatch.setattr(sb_mod.db, "get_positions", lambda **kw: pl.DataFrame())
    with pytest.raises(RuntimeError, match="missing but has asset records"):
        broker._validate_data_consistency()


def test_validate_data_consistency_raises_when_portfolio_exists_but_asset_missing(monkeypatch):
    """[AC-NFR1101-01] Portfolio present but asset None -> RuntimeError."""
    broker = _make_broker()
    monkeypatch.setattr(sb_mod.db, "get_portfolio", lambda pid: MagicMock())
    monkeypatch.setattr(sb_mod.db, "get_asset", lambda **kw: None)
    monkeypatch.setattr(sb_mod.db, "get_positions", lambda **kw: pl.DataFrame())
    with pytest.raises(RuntimeError, match="exists but has no asset records"):
        broker._validate_data_consistency()


# ---------------------------------------------------------------------------
# _get_history_bars: daily_bars fallback path + empty-history frame
# ---------------------------------------------------------------------------


def test_get_history_bars_returns_empty_when_daily_bars_store_is_none(monkeypatch):
    """[AC-NFR1101-01] When daily_bars._store is None and no market_data, returns empty frame."""
    broker = _make_broker()
    bare_daily = MagicMock()
    bare_daily._store = None  # falls through to _empty_history_frame branch
    monkeypatch.setattr(sb_mod, "daily_bars", bare_daily)
    out = broker._get_history_bars("000001.SZ", 5, dt.date(2024, 6, 17), "1d")
    assert isinstance(out, pl.DataFrame)
    assert out.is_empty()


def test_get_history_bars_uses_market_data_get_bars_when_present():
    """[AC-NFR1101-01] market_data.get_bars path returns the provider's frame."""
    broker = _make_broker()
    df = pl.DataFrame({"date": [dt.date(2024, 6, 17)], "asset": ["000001.SZ"], "close": [10.0]})
    market_data = MagicMock()
    market_data.get_history = None  # ensure hasattr False for get_history
    # Use a real class so hasattr check works correctly.
    market_data = _ProviderWithGetBars(df)
    broker._market_data = market_data
    out = broker._get_history_bars("000001.SZ", 1, dt.date(2024, 6, 17), "1d")
    assert "close" in out.columns


class _ProviderWithGetBars:
    def __init__(self, df):
        self._df = df

    def get_bars(self, **kwargs):
        return self._df


# ---------------------------------------------------------------------------
# _extract_forming_bar: bar_dt != end_date returns None
# ---------------------------------------------------------------------------


def test_extract_forming_bar_returns_none_when_bar_dt_does_not_match_end_date(monkeypatch):
    """[AC-NFR1101-01] When bar dt != end_date, _extract_forming_bar returns None."""
    broker = _make_broker()
    today = dt.date(2024, 6, 17)
    bar = {"dt": dt.datetime(2024, 6, 16, 10, 0), "close": 11.0}
    monkeypatch.setattr(sb_mod.live_quote, "get_daily_bar", lambda asset: bar)
    out = broker._extract_forming_bar("000001.SZ", today)
    assert out is None


# ---------------------------------------------------------------------------
# _concat_with_forming: hist_date_col None returns hist
# ---------------------------------------------------------------------------


def test_concat_with_forming_returns_hist_unchanged_when_no_date_column():
    """[AC-NFR1101-01] When hist has neither frame nor date column, returns hist unchanged."""
    hist = pl.DataFrame({"asset": ["000001.SZ"], "close": [10.0]})
    forming = {"asset": "000001.SZ", "close": 11.0, "dt": dt.datetime(2024, 6, 17, 10, 0)}
    out = PaperBroker._concat_with_forming(hist, forming, 5)
    assert out is hist


# ---------------------------------------------------------------------------
# trade_target_pct: diff == 0 equality branch (no trade)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trade_target_pct_returns_empty_when_diff_zero(monkeypatch):
    """[AC-NFR1101-01] trade_target_pct returns ExecutionResult.empty() when target == current."""
    broker = _make_broker()
    monkeypatch.setattr(broker, "_get_quote", lambda asset: {"lastPrice": 10.0})
    broker._positions["000001.SZ"] = Position(
        portfolio_id="p-test",
        dt=dt.date(2024, 6, 17),
        asset="000001.SZ",
        shares=1000,
        avail=1000,
        price=10.0,
        mv=10000.0,
        profit=0.0,
    )
    broker._cash = 990_000.0  # total = 990k + 10k = 1M, target_pct=0.01 -> 10k == current
    out = await broker.trade_target_pct("000001.SZ", 0.01, price=10.0)
    assert out.qt_oid is None  # ExecutionResult.empty() has qt_oid=None


# ---------------------------------------------------------------------------
# sell_percent: clear-all path (percent >= 0.9999)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sell_percent_clear_all_calls_sell_with_full_shares(monkeypatch):
    """[AC-NFR1101-01] sell_percent with percent >= 0.9999 clears all shares."""
    broker = _make_broker()
    broker._positions["000001.SZ"] = Position(
        portfolio_id="p-test",
        dt=dt.date(2024, 6, 17),
        asset="000001.SZ",
        shares=500,
        avail=500,
        price=10.0,
        mv=5000.0,
        profit=0.0,
    )
    called = {}

    async def _fake_sell(asset, shares, price=0, order_time=None, timeout=0.5):
        called["shares"] = shares
        return ExecutionResult(qt_oid="ok", trades=[])

    monkeypatch.setattr(broker, "sell", _fake_sell)
    await broker.sell_percent("000001.SZ", 1.0, price=10.0)
    assert called.get("shares") == 500


# ---------------------------------------------------------------------------
# sell_percent: empty ExecutionResult when asset not in positions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sell_percent_returns_empty_when_asset_not_held():
    """[AC-NFR1101-01] sell_percent for unheld asset returns ExecutionResult.empty()."""
    broker = _make_broker()
    out = await broker.sell_percent("999999.SZ", 0.5, price=10.0)
    assert out.qt_oid is None


# ---------------------------------------------------------------------------
# _persist_updates: error path re-raises after logging
# ---------------------------------------------------------------------------


def test_persist_updates_logs_and_reraises_on_db_error(monkeypatch):
    """[AC-NFR1101-01] _persist_updates logs and re-raises when db.upsert_positions raises."""
    broker = _make_broker()
    broker._positions = {
        "000001.SZ": Position(
            portfolio_id="p-test",
            dt=dt.date(2024, 6, 17),
            asset="000001.SZ",
            shares=100,
            avail=100,
            price=10.0,
            mv=1000.0,
            profit=0.0,
        )
    }
    monkeypatch.setattr(broker, "_get_today", lambda: dt.date(2024, 6, 17))

    def _boom(*_args, **_kwargs):
        raise RuntimeError("db write failed")

    monkeypatch.setattr(sb_mod.db, "upsert_positions", _boom)
    with pytest.raises(RuntimeError, match="db write failed"):
        broker._persist_updates({"000001.SZ"})


# ---------------------------------------------------------------------------
# _on_quote_update: caught exception path (logs, no raise)
# ---------------------------------------------------------------------------


def test_on_quote_update_swallows_exception_in_lock(monkeypatch):
    """[AC-NFR1101-01] _on_quote_update swallows exceptions raised inside the lock."""
    broker = _make_broker()

    # Force _update_positions_market_value to raise.
    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(broker, "_update_positions_market_value", _boom)
    # Should not raise.
    broker._on_quote_update({"000001.SZ": {"lastPrice": 10.0}})
