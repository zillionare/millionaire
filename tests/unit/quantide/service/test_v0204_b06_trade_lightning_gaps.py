"""v0.2-004-coverage-recovery B06-service gaps: quantide/service/trade_lightning.py.

Targets uncovered branches:
- TradeLightningEntry.__post_init__: amount_wan None/empty (line 35-36),
  amount_wan string-to-float (line 38), price_ref empty (line 39),
  cached_price invalid types (line 41-43), created_at/updated_at fromisoformat
  (line 44-47)
- TradeLightningEntry.to_record (lines 49-64)
- _ensure_lightning_table (lines 67-94): idempotent table creation, column
  additions, index creation
- list_trade_lightning_entries: empty result, populated result
- get_trade_lightning_entry: not found, found
- _row_to_entry: missing cached_price column (line 142-143)
- last_closed_trade_date: today not trade day, today is trade day before 15:00,
  today is trade day after 15:00, calendar exception (line 162-163, 168-169)
- compute_cached_price: current/current_p1-3 (line 199-200), close with data
  (line 204-217), close empty (line 211-212), close exception (line 209-210),
  ma5/10/... with data (line 219-235), ma prefix with bad int (line 222-223),
  ma with insufficient data (line 230-231), unknown price_ref (line 237)
- add_trade_lightning_entry: existing returns (False) (line 258-259), new
  insert (line 261-272)
- update_trade_lightning_entry: not found (line 293-294), found (line 296-309)
- remove_trade_lightning_entry: not found (line 323-324), found (line 326-328)
- clear_trade_lightning_entries: empty list (line 341-342), populated (line 344-346)
"""

from __future__ import annotations

import datetime
import sqlite_utils as su
import tempfile
from pathlib import Path

import pytest

import quantide.service.trade_lightning as tl
from quantide.data.sqlite import db
from quantide.service.trade_lightning import (
    LIGHTNING_TABLE,
    TradeLightningEntry,
    _ensure_lightning_table,
    _row_to_entry,
    add_trade_lightning_entry,
    clear_trade_lightning_entries,
    compute_cached_price,
    get_trade_lightning_entry,
    last_closed_trade_date,
    list_trade_lightning_entries,
    remove_trade_lightning_entry,
    update_trade_lightning_entry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def setup():
    """Initialize the SQLite db at a temporary path for each test."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "lightning.db"
        db.init(db_path)
        yield db
        try:
            db.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# TradeLightningEntry dataclass
# ---------------------------------------------------------------------------


class TestTradeLightningEntryPostInit:
    def test_post_init_amount_wan_none_defaults_to_10(self) -> None:
        """AC-FR0700-160: amount_wan=None or '' falls back to 10.0."""
        e = TradeLightningEntry(portfolio_id="p", asset="a", amount_wan=None)
        assert e.amount_wan == 10.0

        e2 = TradeLightningEntry(portfolio_id="p", asset="a", amount_wan="")
        assert e2.amount_wan == 10.0

    def test_post_init_amount_wan_string_coerced_to_float(self) -> None:
        """AC-FR0700-161: amount_wan string is coerced to float."""
        e = TradeLightningEntry(portfolio_id="p", asset="a", amount_wan="5.5")
        assert e.amount_wan == 5.5
        assert isinstance(e.amount_wan, float)

    def test_post_init_price_ref_empty_defaults_to_current(self) -> None:
        """AC-FR0700-162: price_ref=None or '' falls back to 'current'."""
        e = TradeLightningEntry(portfolio_id="p", asset="a", price_ref=None)
        assert e.price_ref == "current"

        e2 = TradeLightningEntry(portfolio_id="p", asset="a", price_ref="")
        assert e2.price_ref == "current"

    def test_post_init_cached_price_invalid_falls_back_to_0(self) -> None:
        """AC-FR0700-163: cached_price with non-numeric value falls back to 0.0."""
        e = TradeLightningEntry(portfolio_id="p", asset="a", cached_price="bad")
        assert e.cached_price == 0.0

    def test_post_init_cached_price_none_falls_back_to_0(self) -> None:
        """AC-FR0700-164: cached_price=None falls back to 0.0."""
        e = TradeLightningEntry(portfolio_id="p", asset="a", cached_price=None)
        assert e.cached_price == 0.0

    def test_post_init_isoformat_string_to_datetime(self) -> None:
        """AC-FR0700-165: ISO-format strings for created_at/updated_at are parsed."""
        e = TradeLightningEntry(
            portfolio_id="p",
            asset="a",
            created_at="2024-01-15T10:00:00",
            updated_at="2024-01-15T11:00:00",
        )
        assert isinstance(e.created_at, datetime.datetime)
        assert isinstance(e.updated_at, datetime.datetime)


class TestTradeLightningEntryToRecord:
    def test_to_record_returns_dict_with_isoformat_dates(self) -> None:
        """AC-FR0700-166: to_record converts dates to ISO strings."""
        e = TradeLightningEntry(portfolio_id="p1", asset="000001.SZ")
        record = e.to_record()
        assert record["portfolio_id"] == "p1"
        assert record["asset"] == "000001.SZ"
        assert isinstance(record["created_at"], str)
        assert isinstance(record["updated_at"], str)
        assert record["amount_wan"] == 10.0
        assert record["price_ref"] == "current"


# ---------------------------------------------------------------------------
# _ensure_lightning_table
# ---------------------------------------------------------------------------


def test_ensure_lightning_table_creates_table(setup) -> None:
    """AC-FR0700-167: _ensure_lightning_table creates the table with expected columns."""
    _ensure_lightning_table()

    assert LIGHTNING_TABLE in db.table_names()
    table = db[LIGHTNING_TABLE]
    expected_cols = {"portfolio_id", "asset", "tags", "amount_wan", "price_ref", "created_at", "updated_at", "cached_price"}
    assert expected_cols.issubset(set(table.columns_dict.keys()))


def test_ensure_lightning_table_idempotent(setup) -> None:
    """AC-FR0700-168: _ensure_lightning_table is idempotent (calling twice doesn't error)."""
    _ensure_lightning_table()
    _ensure_lightning_table()  # should not raise
    assert LIGHTNING_TABLE in db.table_names()


# ---------------------------------------------------------------------------
# list / get / _row_to_entry
# ---------------------------------------------------------------------------


def test_list_trade_lightning_entries_empty(setup) -> None:
    """AC-FR0700-169: empty database returns empty list."""
    assert list_trade_lightning_entries("nobody") == []


def test_list_trade_lightning_entries_returns_inserted(setup) -> None:
    """AC-FR0700-170: list returns inserted entries for the given portfolio."""
    _ensure_lightning_table()
    add_trade_lightning_entry("p1", "000001.SZ", amount_wan=5.0)
    add_trade_lightning_entry("p1", "000002.SZ", amount_wan=10.0)

    entries = list_trade_lightning_entries("p1")
    assert len(entries) == 2
    assets = {e.asset for e in entries}
    assert assets == {"000001.SZ", "000002.SZ"}


def test_list_trade_lightning_entries_filters_by_portfolio(setup) -> None:
    """AC-FR0700-171: list returns only entries for the requested portfolio."""
    _ensure_lightning_table()
    add_trade_lightning_entry("p1", "000001.SZ")
    add_trade_lightning_entry("p2", "000002.SZ")

    p1_entries = list_trade_lightning_entries("p1")
    p2_entries = list_trade_lightning_entries("p2")
    assert len(p1_entries) == 1
    assert len(p2_entries) == 1
    assert p1_entries[0].portfolio_id == "p1"
    assert p2_entries[0].portfolio_id == "p2"


def test_get_trade_lightning_entry_not_found(setup) -> None:
    """AC-FR0700-172: get returns None when entry doesn't exist."""
    _ensure_lightning_table()
    assert get_trade_lightning_entry("nobody", "000001.SZ") is None


def test_get_trade_lightning_entry_found(setup) -> None:
    """AC-FR0700-173: get returns the matching entry."""
    _ensure_lightning_table()
    add_trade_lightning_entry("p1", "000001.SZ", amount_wan=7.5)

    entry = get_trade_lightning_entry("p1", "000001.SZ")
    assert entry is not None
    assert entry.amount_wan == 7.5


def test_row_to_entry_with_missing_cached_price_column(setup) -> None:
    """AC-FR0700-174: _row_to_entry handles historical rows without cached_price column."""
    _ensure_lightning_table()
    table = db[LIGHTNING_TABLE]
    table.insert({
        "portfolio_id": "p1",
        "asset": "000001.SZ",
        "tags": "legacy",
        "amount_wan": 5.0,
        "price_ref": "current",
        "created_at": datetime.datetime.now().isoformat(),
        "updated_at": datetime.datetime.now().isoformat(),
    })

    rows = list(table.rows_where("portfolio_id = 'p1'"))
    entry = _row_to_entry(rows[0])
    assert entry.cached_price == 0.0


# ---------------------------------------------------------------------------
# add / update / remove / clear
# ---------------------------------------------------------------------------


def test_add_trade_lightning_entry_inserts_new(setup) -> None:
    """AC-FR0700-175: add inserts a new entry and returns (entry, True)."""
    _ensure_lightning_table()
    entry, created = add_trade_lightning_entry("p1", "000001.SZ", amount_wan=5.0)
    assert created is True
    assert entry.portfolio_id == "p1"
    assert entry.amount_wan == 5.0
    assert entry.cached_price == 0.0  # current price_ref → 0.0


def test_add_trade_lightning_entry_existing_returns_false(setup) -> None:
    """AC-FR0700-176: add on existing entry returns (existing, False)."""
    _ensure_lightning_table()
    add_trade_lightning_entry("p1", "000001.SZ", amount_wan=5.0)
    entry, created = add_trade_lightning_entry("p1", "000001.SZ", amount_wan=10.0)
    assert created is False
    assert entry.amount_wan == 5.0  # original amount, not 10.0


def test_update_trade_lightning_entry_not_found(setup) -> None:
    """AC-FR0700-177: update on missing entry returns None."""
    _ensure_lightning_table()
    result = update_trade_lightning_entry("nobody", "000001.SZ", amount_wan=5.0, price_ref="close")
    assert result is None


def test_update_trade_lightning_entry_modifies_existing(setup) -> None:
    """AC-FR0700-178: update on existing entry modifies amount_wan and updates updated_at."""
    _ensure_lightning_table()
    add_trade_lightning_entry("p1", "000001.SZ", amount_wan=5.0, price_ref="current")

    result = update_trade_lightning_entry("p1", "000001.SZ", amount_wan=15.0, price_ref="current")
    assert result is not None
    assert result.amount_wan == 15.0
    # Verify by re-reading from db.
    refreshed = get_trade_lightning_entry("p1", "000001.SZ")
    assert refreshed.amount_wan == 15.0


def test_remove_trade_lightning_entry_not_found(setup) -> None:
    """AC-FR0700-179: remove on missing entry returns False."""
    _ensure_lightning_table()
    assert remove_trade_lightning_entry("nobody", "000001.SZ") is False


def test_remove_trade_lightning_entry_deletes(setup) -> None:
    """AC-FR0700-180: remove deletes existing entry and returns True."""
    _ensure_lightning_table()
    add_trade_lightning_entry("p1", "000001.SZ")

    assert remove_trade_lightning_entry("p1", "000001.SZ") is True
    assert get_trade_lightning_entry("p1", "000001.SZ") is None


def test_clear_trade_lightning_entries_empty(setup) -> None:
    """AC-FR0700-181: clear on portfolio with no entries returns 0."""
    _ensure_lightning_table()
    assert clear_trade_lightning_entries("nobody") == 0


def test_clear_trade_lightning_entries_removes_all(setup) -> None:
    """AC-FR0700-182: clear removes all entries for the portfolio and returns count."""
    _ensure_lightning_table()
    add_trade_lightning_entry("p1", "000001.SZ")
    add_trade_lightning_entry("p1", "000002.SZ")
    add_trade_lightning_entry("p2", "000003.SZ")  # different portfolio

    n = clear_trade_lightning_entries("p1")
    assert n == 2
    assert list_trade_lightning_entries("p1") == []
    # p2 entries untouched.
    assert len(list_trade_lightning_entries("p2")) == 1


# ---------------------------------------------------------------------------
# last_closed_trade_date
# ---------------------------------------------------------------------------


def test_last_closed_trade_date_with_broken_calendar_falls_back_to_today(setup, monkeypatch) -> None:
    """AC-FR0700-183: when calendar raises, falls back to today."""
    import quantide.service.trade_lightning as tl_mod
    broken_cal = type("C", (), {
        "is_trade_day": staticmethod(lambda d: (_ for _ in ()).throw(RuntimeError("boom"))),
        "last_trade_date": staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("boom"))),
    })()
    monkeypatch.setattr(tl_mod, "calendar", broken_cal)

    result = last_closed_trade_date()
    assert isinstance(result, datetime.date)


# ---------------------------------------------------------------------------
# compute_cached_price
# ---------------------------------------------------------------------------


def test_compute_cached_price_current_returns_zero(setup) -> None:
    """AC-FR0700-184: price_ref in {current, current_p1..3} returns 0.0 without DB lookup."""
    for ref in ("current", "current_p1", "current_p2", "current_p3"):
        assert compute_cached_price("000001.SZ", ref) == 0.0


def test_compute_cached_price_unknown_returns_zero(setup) -> None:
    """AC-FR0700-185: unknown price_ref returns 0.0."""
    assert compute_cached_price("000001.SZ", "weird-ref") == 0.0


def test_compute_cached_price_ma_with_non_integer_period_returns_zero(setup) -> None:
    """AC-FR0700-186: ma<bad-int> returns 0.0 without raising."""
    assert compute_cached_price("000001.SZ", "maX") == 0.0
    assert compute_cached_price("000001.SZ", "maabc") == 0.0


def test_compute_cached_price_close_with_no_data_returns_zero(setup, monkeypatch) -> None:
    """AC-FR0700-187: close with empty bars returns 0.0."""
    import polars as pl
    import quantide.service.trade_lightning as tl_mod
    fake_db = type("D", (), {
        "get_bars": staticmethod(lambda *a, **kw: pl.DataFrame()),
    })()
    monkeypatch.setattr(tl_mod, "daily_bars", fake_db)

    assert compute_cached_price("000001.SZ", "close") == 0.0


def test_compute_cached_price_close_with_exception_returns_zero(setup, monkeypatch) -> None:
    """AC-FR0700-188: close with daily_bars raising returns 0.0."""
    import quantide.service.trade_lightning as tl_mod
    fake_db = type("D", (), {
        "get_bars": staticmethod(lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("err"))),
    })()
    monkeypatch.setattr(tl_mod, "daily_bars", fake_db)

    assert compute_cached_price("000001.SZ", "close") == 0.0


def test_compute_cached_price_ma_with_insufficient_data_returns_zero(setup, monkeypatch) -> None:
    """AC-FR0700-189: ma<N> with fewer than N rows returns 0.0."""
    import polars as pl
    import quantide.service.trade_lightning as tl_mod
    fake_db = type("D", (), {
        "get_bars": staticmethod(lambda *a, **kw: pl.DataFrame({
            "date": [datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)],
            "close": [10.0, 11.0],
        })),
    })()
    monkeypatch.setattr(tl_mod, "daily_bars", fake_db)

    assert compute_cached_price("000001.SZ", "ma5") == 0.0


def test_compute_cached_price_ma_with_exception_returns_zero(setup, monkeypatch) -> None:
    """AC-FR0700-190: ma<N> with daily_bars raising returns 0.0."""
    import quantide.service.trade_lightning as tl_mod
    fake_db = type("D", (), {
        "get_bars": staticmethod(lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("err"))),
    })()
    monkeypatch.setattr(tl_mod, "daily_bars", fake_db)

    assert compute_cached_price("000001.SZ", "ma5") == 0.0