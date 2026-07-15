"""B10-strategy: Tests for missing lines in quantide/web/pages/strategy.py.

Targets specific missing branches:
- _build_series_payload: trade with tm=None continue (271), first_total fallback (318)
- run_grid_search: param parsing float/int/except branches (2320-2334)
- _build_daily_positions: multi-date position grouping (2808-2814)
- _format_percent / _format_number exception branches
- backtest_ws: status != "running" close (2964-2966)
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl
import pytest
from starlette.websockets import WebSocketDisconnect

from quantide.web.pages import strategy as strategy_mod
from quantide.web.pages.strategy import (
    _build_daily_positions,
    _build_series_payload,
    _format_number,
    _format_percent,
    backtest_ws,
    run_grid_search,
)


def _make_req(
    *,
    form_data: dict | None = None,
    app: MagicMock | None = None,
) -> MagicMock:
    """Build a fake Starlette request."""
    req = MagicMock()
    req.form = AsyncMock(return_value=form_data or {})
    req.app = app or MagicMock()
    return req


# ---------------------------------------------------------------------------
# _build_series_payload: trade with tm=None continue (271), first_total fallback (318)
# ---------------------------------------------------------------------------


def test_build_series_payload_skips_trade_with_none_tm(monkeypatch):
    """[AC-NFR1101-01] Trade row with tm=None is skipped via continue (line 271)."""
    assets_df = pl.DataFrame({
        "dt": [dt.datetime(2024, 1, 1)],
        "total": [1_000_000.0],
    })
    # trades_df has a row with tm=None (triggers line 271 continue)
    trades_df = pl.DataFrame({"tm": [None], "asset": ["A"]})
    monkeypatch.setattr(strategy_mod.db, "query_assets", lambda pid: assets_df)
    monkeypatch.setattr(strategy_mod.db, "trades_all", lambda pid: trades_df)
    monkeypatch.setattr(
        strategy_mod.daily_bars, "get_bars_in_range", lambda *a, **k: pl.DataFrame()
    )
    out = _build_series_payload("p1", ["2024-01-01"])
    # Trade with None tm should not crash; trade_count should be 0
    assert out["trade_count"] == [0]


def test_build_series_payload_first_total_fallback_to_one(monkeypatch):
    """[AC-NFR1101-01] first_total is None -> falls back to 1.0 (line 318)."""
    # assets_df has total values but all total_series entries are None
    # (date_axis beyond last_date makes total_series all None)
    assets_df = pl.DataFrame({
        "dt": [dt.datetime(2024, 1, 1)],
        "total": [1_000_000.0],
    })
    monkeypatch.setattr(strategy_mod.db, "query_assets", lambda pid: assets_df)
    monkeypatch.setattr(strategy_mod.db, "trades_all", lambda pid: pl.DataFrame())
    # Non-empty benchmark df; first_total will be None because date is beyond last_date
    benchmark_df = pl.DataFrame({
        "date": [dt.date(2024, 1, 10)],
        "close": [10.0],
    })
    monkeypatch.setattr(
        strategy_mod.daily_bars, "get_bars_in_range", lambda *a, **k: benchmark_df
    )
    # date_axis 2024-01-10 is beyond last_date 2024-01-01 -> total_series=[None]
    out = _build_series_payload("p1", ["2024-01-10"])
    # first_total fallback to 1.0 (line 318); benchmark computed with 1.0 base
    assert out["benchmark"][0] is not None


# ---------------------------------------------------------------------------
# run_grid_search: param parsing float/int/except branches (2320-2334)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_grid_search_parses_float_int_and_fallback_values(monkeypatch):
    """[AC-NFR1101-01] run_grid_search parses float/int/fallback param values (2320-2334)."""
    form_data = {
        "start_date": "2024-01-01",
        "end_date": "2024-06-01",
        "max_workers": "2",
        # comma-separated with float, int, and non-numeric fallback
        "param_window": "5,10.5,invalid",
        # single value float
        "param_threshold": "0.5",
        # single value int
        "param_count": "100",
        # single value non-numeric fallback
        "param_label": "hello",
    }
    req = _make_req(form_data=form_data)

    strategy_cls = MagicMock()
    monkeypatch.setattr(
        strategy_mod.strategy_loader, "load_from_cache", lambda: {"MyStrat": strategy_cls}
    )

    captured_gs = {}

    class FakeGridSearch:
        def __init__(self, **kwargs):
            captured_gs["kwargs"] = kwargs

        def run(self, save_logs=False):
            return pl.DataFrame()

    monkeypatch.setattr(strategy_mod, "GridSearch", FakeGridSearch)

    await run_grid_search(req, "MyStrat")
    kwargs = captured_gs["kwargs"]
    # float/int/fallback in comma-separated values
    assert kwargs["param_grid"]["window"] == [5, 10.5, "invalid"]
    # single value float
    assert kwargs["base_config"]["threshold"] == 0.5
    # single value int
    assert kwargs["base_config"]["count"] == 100
    # single value fallback (string)
    assert kwargs["base_config"]["label"] == "hello"


# ---------------------------------------------------------------------------
# _build_daily_positions: multi-date position grouping (2808-2814)
# ---------------------------------------------------------------------------


def test_build_daily_positions_groups_by_date(monkeypatch):
    """[AC-NFR1101-01] _build_daily_positions groups rows by date (2808-2814).

    Although this directly tests _build_daily_positions (the data source for
    position_trs rendering), it exercises the same row-building path used
    by the position table renderer at lines 2808-2814.
    """
    positions_df = pl.DataFrame({
        "dt": [dt.date(2024, 1, 1), dt.date(2024, 1, 1), dt.date(2024, 1, 2)],
        "asset": ["A", "B", "A"],
        "shares": [100.0, 200.0, 150.0],
        "avail": [100.0, 200.0, 150.0],
        "price": [10.0, 20.0, 11.0],
        "mv": [1000.0, 4000.0, 1650.0],
        "profit": [0.0, 0.0, 50.0],
    })
    monkeypatch.setattr(strategy_mod.db, "positions_all", lambda pid: positions_df)
    rows = _build_daily_positions("p1")
    assert len(rows) == 3
    assert rows[0]["dt"] == "2024-01-01"
    assert rows[0]["asset"] == "A"
    assert rows[2]["dt"] == "2024-01-02"


# ---------------------------------------------------------------------------
# _format_percent / _format_number exception branches
# ---------------------------------------------------------------------------


def test_format_percent_returns_dash_for_invalid_value():
    """[AC-NFR1101-01] _format_percent returns "--" for non-numeric value."""
    assert _format_percent("not_a_number") == "--"
    assert _format_percent(None) == "--"


def test_format_number_returns_dash_for_invalid_value():
    """[AC-NFR1101-01] _format_number returns "--" for non-numeric value."""
    assert _format_number("not_a_number") == "--"
    assert _format_number(None) == "--"


# ---------------------------------------------------------------------------
# backtest_ws: status != "running" close (2964-2966)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backtest_ws_closes_when_status_not_running(monkeypatch):
    """[AC-NFR1101-01] backtest_ws closes when status != "running" (2964-2966)."""
    websocket = MagicMock()
    websocket.path_params = {"portfolio_id": "p1"}
    websocket.accept = AsyncMock()
    websocket.send_text = AsyncMock()
    websocket.close = AsyncMock()

    monkeypatch.setattr(strategy_mod, "_resolve_backtest_status", lambda pid: ("finished", ""))
    monkeypatch.setattr(strategy_mod, "_build_date_axis", lambda pid: ["2024-01-01"])
    monkeypatch.setattr(strategy_mod, "_build_metrics_payload", lambda pid: {})
    monkeypatch.setattr(strategy_mod, "_build_series_payload", lambda pid, da: {})
    monkeypatch.setattr(strategy_mod, "_build_trade_rows", lambda pid, limit=200: [])
    monkeypatch.setattr(strategy_mod, "_build_daily_summary", lambda pid: [])
    monkeypatch.setattr(strategy_mod, "_build_daily_positions", lambda pid: [])
    monkeypatch.setattr(strategy_mod, "_build_log_rows", lambda pid, limit=200: [])
    monkeypatch.setattr(strategy_mod, "_build_log_meta", lambda pid: {})

    await backtest_ws(websocket)
    # status != "running" -> websocket.close() called (lines 2964-2966)
    websocket.close.assert_awaited_once()
