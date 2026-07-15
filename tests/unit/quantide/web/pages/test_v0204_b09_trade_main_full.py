"""B09-trade-main-full: Cover remaining missing lines in trade_main.py helpers.

Targets gaps left by earlier B08/B09 test files:
- _extract_recent_trade_dates: empty calendar / pandas-Timestamp .date() path
- _resolve_trade_reference_dates: calendar exception -> [] branch, fetcher fallback
- _build_asset_stats: empty-bars payload + closes-but-empty payload branches
- _load_trade_reference_bars: daily_bars ok path + fallback-frame empty branch
- _resolve_trade_reference_close: close <= 0 exception branch
- _get_all_accounts: full QMT+SIM enumeration
- _get_active_account: no accounts / active present / no-active-but-default
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import polars as pl

from quantide.core.enums import BrokerKind
from quantide.web.pages import trade_main as tm
from quantide.web.pages.trade_main import (
    _build_asset_stats,
    _extract_recent_trade_dates,
    _get_active_account,
    _get_all_accounts,
    _load_trade_reference_bars,
    _resolve_trade_reference_close,
    _resolve_trade_reference_dates,
)


# ---------------------------------------------------------------------------
# _extract_recent_trade_dates - empty calendar + Timestamp .date() path
# ---------------------------------------------------------------------------


def test_extract_recent_trade_dates_empty_calendar_returns_empty():
    """An empty DataFrame returns [] early (covers the `if not dates: return []` branch)."""
    empty_df = pd.DataFrame(columns=["date", "is_open"])
    out = _extract_recent_trade_dates(empty_df, datetime.date(2024, 1, 5), 3)
    assert out == []


def test_extract_recent_trade_dates_converts_timestamp_to_date():
    """When the `date` column holds pandas Timestamps, the .date() path is taken."""
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "is_open": [1, 1],
    })
    out = _extract_recent_trade_dates(df, datetime.date(2024, 1, 5), 3)
    assert len(out) == 2
    # All entries should be datetime.date instances (not Timestamps).
    for entry in out:
        assert isinstance(entry, datetime.date)
        assert not isinstance(entry, pd.Timestamp)


# ---------------------------------------------------------------------------
# _resolve_trade_reference_dates - calendar exception + fetcher fallback
# ---------------------------------------------------------------------------


def test_resolve_trade_reference_dates_calendar_exception_falls_back_to_fetcher():
    """When calendar.get_trade_dates raises, trade_dates=[] and the fetcher path is used."""
    fetcher = MagicMock()
    df = pd.DataFrame({
        "date": [datetime.date(2024, 1, 3), datetime.date(2024, 1, 4)],
        "is_open": [1, 1],
    })
    fetcher.fetch_calendar.return_value = df
    with patch.object(tm, "calendar") as fake_calendar:
        fake_calendar.get_trade_dates.side_effect = Exception("calendar boom")
        out = _resolve_trade_reference_dates(fetcher, datetime.date(2024, 1, 5), 2)
    assert isinstance(out, list)
    assert len(out) >= 1


def test_resolve_trade_reference_dates_fetcher_exception_returns_end():
    """When both calendar and fetcher.fetch_calendar raise, returns [end]."""
    fetcher = MagicMock()
    fetcher.fetch_calendar.side_effect = Exception("fetcher boom")
    with patch.object(tm, "calendar") as fake_calendar:
        fake_calendar.get_trade_dates.side_effect = Exception("calendar boom")
        out = _resolve_trade_reference_dates(fetcher, datetime.date(2024, 1, 5), 2)
    assert out == [datetime.date(2024, 1, 5)]


# ---------------------------------------------------------------------------
# _build_asset_stats - empty bars / empty closes branches
# ---------------------------------------------------------------------------


def test_build_asset_stats_returns_invisible_payload_when_bars_empty():
    """When _load_trade_reference_bars returns empty DataFrame, payload stays invisible."""
    with patch.object(tm, "_load_trade_reference_bars", return_value=pl.DataFrame()):
        out = _build_asset_stats("000001.SZ")
    assert out["visible"] is False
    assert out["close"] == ""


def test_build_asset_stats_returns_invisible_payload_when_closes_empty():
    """When bars are non-empty but the close column has no rows, payload stays invisible.

    The `if not closes: return payload` branch (line 197) is reached only when
    `closes` is an empty list. This happens when the close column exists but
    contains zero rows -- a degenerate frame with a schema but no data.
    """
    df = pl.DataFrame(schema={"date": pl.Date, "close": pl.Float64})
    with patch.object(tm, "_load_trade_reference_bars", return_value=df), \
         patch.object(tm, "_resolve_live_current_price", return_value=0.0):
        out = _build_asset_stats("000001.SZ")
    assert out["visible"] is False


# ---------------------------------------------------------------------------
# _load_trade_reference_bars - daily_bars ok path + fallback empty branch
# ---------------------------------------------------------------------------


def test_load_trade_reference_bars_returns_local_bars_when_available():
    """When daily_bars.get_bars returns a non-empty frame, it is returned (sorted by date)."""
    df = pl.DataFrame({
        "date": [datetime.date(2024, 1, 2), datetime.date(2024, 1, 1)],
        "close": [10.0, 9.0],
    })
    with patch.object(tm.daily_bars, "get_bars", return_value=df):
        out = _load_trade_reference_bars("000001.SZ", datetime.date(2024, 1, 5), 2)
    assert not out.is_empty()
    # Sorted ascending by date.
    dates = out.get_column("date").to_list()
    assert dates == sorted(dates)


def test_load_trade_reference_bars_fallback_empty_frame_returns_empty():
    """When local bars are empty and the fetcher fallback yields an empty frame, returns empty."""
    with patch.object(tm.daily_bars, "get_bars", return_value=pl.DataFrame()), \
         patch.object(tm, "get_data_fetcher") as fake_fetcher, \
         patch.object(tm, "_resolve_trade_reference_dates", return_value=[datetime.date(2024, 1, 4)]):
        fake_fetcher.return_value.fetch_bars_ext.return_value = (pd.DataFrame(), None)
        out = _load_trade_reference_bars("000001.SZ", datetime.date(2024, 1, 5), 2)
    assert out.is_empty()


# ---------------------------------------------------------------------------
# _resolve_trade_reference_close - close <= 0 exception branch
# ---------------------------------------------------------------------------


def test_resolve_trade_reference_close_returns_zero_when_close_non_positive():
    """When the latest close value is 0 (or non-positive), returns 0.0."""
    df = pl.DataFrame({"date": [datetime.date(2024, 1, 1)], "close": [0.0]})
    with patch.object(tm, "_load_trade_reference_bars", return_value=df):
        out = _resolve_trade_reference_close("000001.SZ")
    assert out == 0.0


# ---------------------------------------------------------------------------
# _get_all_accounts - full QMT+SIM enumeration
# ---------------------------------------------------------------------------


def test_get_all_accounts_enumerates_qmt_and_simulation():
    """Both BrokerKind.QMT and BrokerKind.SIMULATION are enumerated into the accounts list."""
    reg = MagicMock()

    def _list_by_kind(kind):
        if kind == BrokerKind.QMT:
            return [{"id": "qmt-1", "name": "实盘1", "status": True}]
        return [{"id": "sim-1", "name": "仿真1", "status": True}]

    reg.list_by_kind.side_effect = _list_by_kind
    out = _get_all_accounts(reg)
    assert len(out) == 2
    kinds = {a["kind"] for a in out}
    assert kinds == {BrokerKind.QMT.value, BrokerKind.SIMULATION.value}
    qmt = next(a for a in out if a["kind"] == BrokerKind.QMT.value)
    assert qmt["is_live"] is True
    assert qmt["label"] == "实盘"
    sim = next(a for a in out if a["kind"] == BrokerKind.SIMULATION.value)
    assert sim["is_live"] is False
    assert sim["label"] == "仿真"


# ---------------------------------------------------------------------------
# _get_active_account - no accounts / active present / no-active-but-default
# ---------------------------------------------------------------------------


def test_get_active_account_returns_none_when_no_active_and_no_default():
    """When session has no active account and registry has no default, returns None."""
    reg = MagicMock()
    reg.get_default.return_value = None
    out = _get_active_account(reg, {})
    assert out is None


def test_get_active_account_returns_dict_when_session_active_present():
    """When session carries active_account_kind/id, the broker is resolved from the registry."""
    reg = MagicMock()
    fake_broker = SimpleNamespace(portfolio_name="MyAcc", status=True)
    reg.get.return_value = fake_broker
    out = _get_active_account(
        reg,
        {"active_account_kind": BrokerKind.QMT.value, "active_account_id": "qmt-1"},
    )
    assert out is not None
    assert out["id"] == "qmt-1"
    assert out["name"] == "MyAcc"
    assert out["is_live"] is True


def test_get_active_account_uses_default_when_no_session_active():
    """When session lacks active account, falls back to registry default."""
    reg = MagicMock()
    reg.get_default.return_value = (BrokerKind.SIMULATION.value, "sim-1")
    fake_broker = SimpleNamespace(portfolio_name="SimAcc", status=True)
    reg.get.return_value = fake_broker
    out = _get_active_account(reg, {})
    assert out is not None
    assert out["id"] == "sim-1"
    assert out["is_live"] is False
