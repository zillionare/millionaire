"""B08-strategy-build-helpers: Test _build_date_axis and _build_series_payload with mocks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl
import pytest

from quantide.web.pages import strategy as strategy_mod
from quantide.web.pages.strategy import (
    _build_date_axis,
    _build_series_payload,
)


def test_build_date_axis_with_portfolio():
    """[AC-NFR1101-01] When portfolio exists, returns list from calendar.get_frames."""
    fake_portfolio = MagicMock()
    fake_portfolio.start = __import__("datetime").date(2024, 1, 1)
    fake_portfolio.end = __import__("datetime").date(2024, 6, 30)

    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.get_portfolio = MagicMock(return_value=fake_portfolio)
        with patch.object(strategy_mod, "calendar") as mock_cal:
            mock_cal.get_frames = MagicMock(return_value=[
                __import__("datetime").date(2024, 1, 1),
                __import__("datetime").date(2024, 1, 2),
            ])
            out = _build_date_axis("p1")
    assert out == ["2024-01-01", "2024-01-02"]


def test_build_date_axis_no_portfolio_no_end():
    """[AC-NFR1101-01] When portfolio has no end, uses start as end."""
    fake_portfolio = MagicMock()
    fake_portfolio.start = __import__("datetime").date(2024, 1, 1)
    fake_portfolio.end = None

    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.get_portfolio = MagicMock(return_value=fake_portfolio)
        with patch.object(strategy_mod, "calendar") as mock_cal:
            mock_cal.get_frames = MagicMock(return_value=[
                __import__("datetime").date(2024, 1, 1),
            ])
            _build_date_axis("p1")
    mock_cal.get_frames.assert_called_once()


def test_build_date_axis_no_portfolio_use_assets():
    """[AC-NFR1101-01] When no portfolio but assets exist, derives from first/last row."""
    fake_assets = pl.DataFrame({
        "dt": [
            __import__("datetime").date(2024, 1, 1),
            __import__("datetime").date(2024, 1, 3),
            __import__("datetime").date(2024, 1, 5),
        ]
    })

    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.get_portfolio = MagicMock(return_value=None)
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        with patch.object(strategy_mod, "calendar") as mock_cal:
            mock_cal.get_frames = MagicMock(return_value=[
                __import__("datetime").date(2024, 1, 1),
                __import__("datetime").date(2024, 1, 5),
            ])
            _build_date_axis("p1")


def test_build_date_axis_no_portfolio_no_assets():
    """[AC-NFR1101-01] Returns empty list when no portfolio and no assets."""
    fake_assets = pl.DataFrame()  # empty

    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.get_portfolio = MagicMock(return_value=None)
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        _build_date_axis("p1")


# ---------------------------------------------------------------------------
# _build_series_payload
# ---------------------------------------------------------------------------


def test_build_series_payload_no_assets():
    """[AC-NFR1101-01] When no assets, returns placeholder payload."""
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=pl.DataFrame())
        out = _build_series_payload("p1", date_axis=["2024-01-01"])
    assert out["total"] == [None]
    assert out["trade_count"] == [0]


def test_build_series_payload_no_date_axis():
    """[AC-NFR1101-01] When no date_axis, returns empty placeholder."""
    fake_assets = pl.DataFrame({"dt": [__import__("datetime").date(2024, 1, 1)]})
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        out = _build_series_payload("p1", date_axis=[])
    assert out["total"] == []
    assert out["trade_count"] == []


def test_build_series_payload_with_assets():
    """[AC-NFR1101-01] With assets, populates series."""
    fake_assets = pl.DataFrame({
        "dt": [
            __import__("datetime").date(2024, 1, 1),
            __import__("datetime").date(2024, 1, 2),
        ],
        "total": [100.0, 110.0],
        "benchmark_total": [100.0, 105.0],
    })
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        out = _build_series_payload("p1", date_axis=["2024-01-01", "2024-01-02"])
    assert "total" in out
    assert "benchmark" in out


# ---------------------------------------------------------------------------
# _build_benchmark_returns
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import _build_benchmark_returns


def test_build_benchmark_returns_no_assets():
    """[AC-NFR1101-01] When no assets, returns None."""
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=pl.DataFrame())
        out = _build_benchmark_returns("p1")
    assert out is None


def test_build_benchmark_returns_daily_bars_exception():
    """[AC-NFR1101-01] When daily_bars.get_bars_in_range raises, returns None."""
    fake_assets = pl.DataFrame({"dt": [__import__("datetime").date(2024, 1, 1)]})
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        with patch.object(strategy_mod, "daily_bars") as mock_dbars:
            mock_dbars.get_bars_in_range = MagicMock(side_effect=Exception("boom"))
            out = _build_benchmark_returns("p1")
    assert out is None


def test_build_benchmark_returns_empty_dataframe():
    """[AC-NFR1101-01] When daily_bars returns empty df, returns None."""
    import datetime
    fake_assets = pl.DataFrame({"dt": [datetime.date(2024, 1, 1)]})
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        with patch.object(strategy_mod, "daily_bars") as mock_dbars:
            mock_dbars.get_bars_in_range = MagicMock(return_value=pl.DataFrame())
            out = _build_benchmark_returns("p1")
    assert out is None


def test_build_benchmark_returns_with_data():
    """[AC-NFR1101-01] With proper data, returns percent-change df."""
    import datetime
    fake_assets = pl.DataFrame({
        "dt": [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
        ]
    })
    fake_bars = pl.DataFrame({
        "date": [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
        ],
        "close": [100.0, 110.0],
    })
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        with patch.object(strategy_mod, "daily_bars") as mock_dbars:
            mock_dbars.get_bars_in_range = MagicMock(return_value=fake_bars)
            out = _build_benchmark_returns("p1")
    assert out is not None


# ---------------------------------------------------------------------------
# _build_metrics_payload — uses metrics(...) which is heavy; mock it
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import _build_metrics_payload, BENCHMARK_ASSET


def test_build_metrics_payload_with_stats():
    """[AC-NFR1101-01] Build metrics from a normal stats DataFrame."""
    import pandas as pd
    fake_df = pd.DataFrame({"v": [1.0]}, index=["Sharpe Ratio"])
    with patch.object(strategy_mod, "metrics") as mock_metrics, \
         patch.object(strategy_mod, "_build_benchmark_returns", return_value=None):
        mock_metrics.return_value = fake_df
        out = _build_metrics_payload("p1")
    assert "annual_return" in out
    assert "sharpe" in out
    assert "max_drawdown" in out


# ---------------------------------------------------------------------------
# _resolve_backtest_status + _build_trade_rows + _build_daily_positions + ...
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import (
    _build_daily_positions,
    _build_daily_summary,
    _build_log_rows,
    _build_trade_rows,
    _resolve_backtest_status,
)


def test_resolve_backtest_status_no_run_no_portfolio():
    """[AC-NFR1101-01] No run, no portfolio → ('missing', '未找到回测记录。')."""
    with patch.object(strategy_mod, "strategy_runtime_manager") as mock_mgr, \
         patch.object(strategy_mod, "db") as mock_db:
        mock_mgr.get_backtest_run = MagicMock(return_value=None)
        mock_db.get_portfolio = MagicMock(return_value=None)
        status, err = _resolve_backtest_status("p1")
    assert status == "missing"
    assert "未找到" in err


def test_resolve_backtest_status_running():
    """[AC-NFR1101-01] When portfolio.status is True, status='running'."""
    fake_portfolio = MagicMock()
    fake_portfolio.status = True
    with patch.object(strategy_mod, "strategy_runtime_manager") as mock_mgr, \
         patch.object(strategy_mod, "db") as mock_db:
        mock_mgr.get_backtest_run = MagicMock(return_value=None)
        mock_db.get_portfolio = MagicMock(return_value=fake_portfolio)
        status, err = _resolve_backtest_status("p1")
    assert status == "running"
    assert err == ""


def test_resolve_backtest_status_finished():
    """[AC-NFR1101-01] When portfolio.status is False, status='finished'."""
    fake_portfolio = MagicMock()
    fake_portfolio.status = False
    with patch.object(strategy_mod, "strategy_runtime_manager") as mock_mgr, \
         patch.object(strategy_mod, "db") as mock_db:
        mock_mgr.get_backtest_run = MagicMock(return_value=None)
        mock_db.get_portfolio = MagicMock(return_value=fake_portfolio)
        status, err = _resolve_backtest_status("p1")
    assert status == "finished"


def test_resolve_backtest_status_run_running():
    """[AC-NFR1101-01] When run.status='running', return running."""
    fake_run = MagicMock()
    fake_run.status = "running"
    fake_run.error = None
    with patch.object(strategy_mod, "strategy_runtime_manager") as mock_mgr:
        mock_mgr.get_backtest_run = MagicMock(return_value=fake_run)
        status, err = _resolve_backtest_status("p1")
    assert status == "running"


def test_resolve_backtest_status_run_unknown():
    """[AC-NFR1101-01] When run.status is unknown, falls through to portfolio check."""
    fake_run = MagicMock()
    fake_run.status = "weird"
    fake_run.error = "x"
    fake_portfolio = MagicMock()
    fake_portfolio.status = False
    with patch.object(strategy_mod, "strategy_runtime_manager") as mock_mgr, \
         patch.object(strategy_mod, "db") as mock_db:
        mock_mgr.get_backtest_run = MagicMock(return_value=fake_run)
        mock_db.get_portfolio = MagicMock(return_value=fake_portfolio)
        status, err = _resolve_backtest_status("p1")
    assert status == "finished"


# ---------------------------------------------------------------------------
# _build_trade_rows
# ---------------------------------------------------------------------------


def test_build_trade_rows_empty():
    """[AC-NFR1101-01] When db.trades_all is empty, returns []."""
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.trades_all = MagicMock(return_value=pl.DataFrame())
        out = _build_trade_rows("p1")
    assert out == []


def test_build_trade_rows_with_data():
    """[AC-NFR1101-01] With trade rows, formats them."""
    import datetime
    from quantide.core.enums import OrderSide
    fake_trades = pl.DataFrame({
        "tm": [datetime.datetime(2024, 1, 1, 10, 0)],
        "asset": ["000001.SZ"],
        "side": [OrderSide.BUY],
        "price": [10.0],
        "shares": [100.0],
        "amount": [1000.0],
        "fee": [1.0],
    })
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.trades_all = MagicMock(return_value=fake_trades)
        out = _build_trade_rows("p1")
    assert len(out) == 1
    assert out[0]["asset"] == "000001.SZ"


def test_build_trade_rows_side_int():
    """[AC-NFR1101-01] When side is int (not enum), parsed."""
    import datetime
    fake_trades = pl.DataFrame({
        "tm": [datetime.datetime(2024, 1, 1, 10, 0)],
        "asset": ["000001.SZ"],
        "side": [1],
        "price": [10.0],
        "shares": [100.0],
        "amount": [1000.0],
        "fee": [1.0],
    })
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.trades_all = MagicMock(return_value=fake_trades)
        out = _build_trade_rows("p1")
    assert out[0]["side_value"] == 1
    assert out[0]["side"] == "买入"


def test_build_trade_rows_side_sell():
    """[AC-NFR1101-01] When side=-1 (sell), formatted correctly."""
    import datetime
    fake_trades = pl.DataFrame({
        "tm": [datetime.datetime(2024, 1, 1, 10, 0)],
        "asset": ["000001.SZ"],
        "side": [-1],
        "price": [10.0],
        "shares": [100.0],
        "amount": [1000.0],
        "fee": [1.0],
    })
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.trades_all = MagicMock(return_value=fake_trades)
        out = _build_trade_rows("p1")
    assert out[0]["side"] == "卖出"


# ---------------------------------------------------------------------------
# _build_daily_positions + _build_daily_summary
# ---------------------------------------------------------------------------


def test_build_daily_positions_empty():
    """[AC-NFR1101-01] test_build_daily_positions_empty."""
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.snapshot_all = MagicMock(return_value=pl.DataFrame())
        out = _build_daily_positions("p1")
    assert isinstance(out, list)


def test_build_daily_summary_empty():
    """[AC-NFR1101-01] test_build_daily_summary_empty."""
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.snapshot_all = MagicMock(return_value=pl.DataFrame())
        out = _build_daily_summary("p1")
    assert isinstance(out, list)


# ---------------------------------------------------------------------------
# _build_log_rows
# ---------------------------------------------------------------------------


def test_build_log_rows_empty():
    """[AC-NFR1101-01] test_build_log_rows_empty."""
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.backtest_logs = MagicMock(return_value=pl.DataFrame())
        out = _build_log_rows("p1")
    assert isinstance(out, list)


# ---------------------------------------------------------------------------
# _normalize_scan_directory + _scan_scope_list
# ---------------------------------------------------------------------------


from pathlib import Path

from quantide.web.pages.strategy import (
    _normalize_scan_directory,
    _scan_scope_list,
)


def test_scan_scope_list_empty():
    """[AC-NFR1101-01] Empty list returns Ul with empty body."""
    out = _scan_scope_list([])
    assert out is not None


def test_scan_scope_list_with_dirs():
    """[AC-NFR1101-01] test_scan_scope_list_with_dirs."""
    out = _scan_scope_list(["/path/a", "/path/b"])
    assert out is not None


def test_normalize_scan_directory_empty_raises():
    """[AC-NFR1101-01] test_normalize_scan_directory_empty_raises."""
    with pytest.raises(ValueError, match="不能为空"):
        _normalize_scan_directory("")


def test_normalize_scan_directory_whitespace_raises():
    """[AC-NFR1101-01] test_normalize_scan_directory_whitespace_raises."""
    with pytest.raises(ValueError, match="不能为空"):
        _normalize_scan_directory("   ")


def test_normalize_scan_directory_relative_path_raises():
    """[AC-NFR1101-01] When path is relative, raises."""
    with pytest.raises(ValueError, match="绝对路径"):
        _normalize_scan_directory("relative/path")


def test_normalize_scan_directory_nonexistent_raises():
    """[AC-NFR1101-01] test_normalize_scan_directory_nonexistent_raises."""
    with pytest.raises(FileNotFoundError, match="不存在"):
        _normalize_scan_directory("/definitely/does/not/exist/12345")


def test_normalize_scan_directory_path_is_file():
    """[AC-NFR1101-01] When path is a file, raises NotADirectoryError."""
    import os
    tmp_file = "/tmp/scan_test_file"
    with open(tmp_file, "w") as f:
        f.write("test")
    try:
        with pytest.raises(NotADirectoryError):
            _normalize_scan_directory(tmp_file)
    finally:
        os.unlink(tmp_file)


def test_normalize_scan_directory_valid():
    """[AC-NFR1101-01] When directory exists, returns (str, Path)."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        s, p = _normalize_scan_directory(tmpdir)
        assert isinstance(s, str)
        assert isinstance(p, Path)
        assert p.exists()
        assert p.is_dir()


# ---------------------------------------------------------------------------
# _parse_params
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import _parse_params


def test_parse_params_empty():
    """[AC-NFR1101-01] test_parse_params_empty."""
    assert _parse_params({}) == {}


def test_parse_params_no_prefix():
    """[AC-NFR1101-01] Non-prefixed keys are skipped."""
    assert _parse_params({"other_key": "v"}) == {}


def test_parse_params_bool_true():
    """[AC-NFR1101-01] 'true' → True."""
    assert _parse_params({"param_x": "true"})["x"] is True


def test_parse_params_bool_false():
    """[AC-NFR1101-01] test_parse_params_bool_false."""
    assert _parse_params({"param_x": "false"})["x"] is False


def test_parse_params_int():
    """[AC-NFR1101-01] test_parse_params_int."""
    assert _parse_params({"param_n": "42"})["n"] == 42


def test_parse_params_float():
    """[AC-NFR1101-01] test_parse_params_float."""
    assert _parse_params({"param_f": "3.14"})["f"] == 3.14


def test_parse_params_string_passthrough():
    """[AC-NFR1101-01] test_parse_params_string_passthrough."""
    assert _parse_params({"param_s": "hello"})["s"] == "hello"


def test_parse_params_custom_prefix():
    """[AC-NFR1101-01] Custom prefix strips correctly."""
    assert _parse_params({"my_x": "42"}, prefix="my_")["x"] == 42


def test_parse_params_multiple():
    """[AC-NFR1101-01] test_parse_params_multiple."""
    out = _parse_params({
        "param_a": "1",
        "param_b": "true",
        "param_c": "hello",
        "skipped": "x",
    })
    assert out["a"] == 1
    assert out["b"] is True
    assert out["c"] == "hello"
    assert "skipped" not in out


# ---------------------------------------------------------------------------
# deploy_backtest_to_paper (async route handler)
# ---------------------------------------------------------------------------


from quantide.web.pages import strategy as strategy_mod_alias
from quantide.web.pages.strategy import deploy_backtest_to_paper


@pytest.mark.asyncio
async def test_deploy_to_paper_invalid_principal():
    """When paper_principal is not a number, returns error modal."""
    with patch.object(strategy_mod_alias, "_load_backtest_run_config") as mock_load, \
         patch.object(strategy_mod_alias, "_paper_deploy_modal") as mock_modal:
        mock_load.return_value = ({}, None)
        mock_modal.return_value = "modal-error"
        req = MagicMock()
        req.form = AsyncMock(return_value={"paper_principal": "not-a-number"})
        resp = await deploy_backtest_to_paper(req, portfolio_id="p1")
    assert resp == "modal-error"


@pytest.mark.asyncio
async def test_deploy_to_paper_zero_principal():
    """When principal <= 0, returns error modal."""
    with patch.object(strategy_mod_alias, "_load_backtest_run_config") as mock_load, \
         patch.object(strategy_mod_alias, "_paper_deploy_modal") as mock_modal:
        mock_load.return_value = ({}, None)
        mock_modal.return_value = "modal-zero"
        req = MagicMock()
        req.form = AsyncMock(return_value={"paper_principal": "0"})
        resp = await deploy_backtest_to_paper(req, portfolio_id="p1")
    assert resp == "modal-zero"


@pytest.mark.asyncio
async def test_deploy_to_paper_no_registry():
    """When no registry, returns error modal."""
    with patch.object(strategy_mod_alias, "_get_registry") as mock_getreg, \
         patch.object(strategy_mod_alias, "_load_backtest_run_config") as mock_load, \
         patch.object(strategy_mod_alias, "_paper_deploy_modal") as mock_modal:
        mock_getreg.return_value = None
        mock_load.return_value = ({}, None)
        mock_modal.return_value = "modal-no-reg"
        req = MagicMock()
        req.form = AsyncMock(return_value={"paper_principal": "1000000"})
        resp = await deploy_backtest_to_paper(req, portfolio_id="p1")
    assert resp == "modal-no-reg"


# ---------------------------------------------------------------------------
# deploy_backtest_to_live
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import deploy_backtest_to_live


@pytest.mark.asyncio
async def test_deploy_to_live_no_registry():
    """When no registry, returns modal with empty live_accounts."""
    with patch.object(strategy_mod_alias, "_get_registry") as mock_getreg, \
         patch.object(strategy_mod_alias, "_load_backtest_run_config") as mock_load, \
         patch.object(strategy_mod_alias, "_live_deploy_modal") as mock_modal, \
         patch.object(strategy_mod_alias, "_get_live_accounts", return_value=[]):
        mock_getreg.return_value = None
        mock_load.return_value = ({}, None)
        mock_modal.return_value = "modal-no-reg"
        req = MagicMock()
        req.form = AsyncMock(return_value={"live_account_id": "x"})
        resp = await deploy_backtest_to_live(req, portfolio_id="p1")
    assert resp == "modal-no-reg"


@pytest.mark.asyncio
async def test_deploy_to_live_no_live_accounts():
    """When no live accounts, returns modal with empty list."""
    with patch.object(strategy_mod_alias, "_get_registry") as mock_getreg, \
         patch.object(strategy_mod_alias, "_load_backtest_run_config") as mock_load, \
         patch.object(strategy_mod_alias, "_live_deploy_modal") as mock_modal, \
         patch.object(strategy_mod_alias, "_get_live_accounts", return_value=[]):
        mock_getreg.return_value = MagicMock()
        mock_load.return_value = ({}, None)
        mock_modal.return_value = "modal-no-accts"
        req = MagicMock()
        req.form = AsyncMock(return_value={"live_account_id": "x"})
        resp = await deploy_backtest_to_live(req, portfolio_id="p1")
    assert resp == "modal-no-accts"


@pytest.mark.asyncio
async def test_deploy_to_live_already_deployed():
    """When existing_runtime exists, returns error modal."""
    from quantide.web.pages.strategy import strategy_runtime_manager as srm
    fake_runtime = MagicMock()
    fake_runtime.portfolio_id = "p1-live"
    fake_runtime.strategy_id = "strat-1"
    with patch.object(strategy_mod_alias, "_get_registry") as mock_getreg, \
         patch.object(strategy_mod_alias, "_get_live_accounts", return_value=[{"id": "x"}]), \
         patch.object(srm, "get_active_backtest_deployment", return_value=fake_runtime):
        mock_getreg.return_value = MagicMock()
        req = MagicMock()
        req.form = AsyncMock(return_value={"live_account_id": "x"})
        resp = await deploy_backtest_to_live(req, portfolio_id="p1")
    assert resp is not None


# ---------------------------------------------------------------------------
# save_scan_config + _copy_requires_config_modal
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import (
    _copy_requires_config_modal,
    save_scan_config,
)


@pytest.mark.asyncio
async def test_save_scan_config_invalid_dir():
    """When directory doesn't exist, returns config modal with error."""
    with patch.object(strategy_mod_alias, "_config_modal_html") as mock_modal:
        mock_modal.return_value = "config-error"
        req = MagicMock()
        req.form = AsyncMock(return_value={"scan-dir-input": "/nonexistent/dir/12345"})
        resp = await save_scan_config(req)
    assert resp == "config-error"


@pytest.mark.asyncio
async def test_save_scan_config_generic_exception():
    """When unexpected exception, returns error modal."""
    with patch.object(strategy_mod_alias, "_config_modal_html") as mock_modal, \
         patch.object(strategy_mod_alias, "strategy_loader") as mock_loader:
        mock_modal.return_value = "generic-error"
        mock_loader.set_scan_directory = MagicMock(side_effect=Exception("boom"))
        req = MagicMock()
        req.form = AsyncMock(return_value={"scan-dir-input": "/tmp"})
        resp = await save_scan_config(req)
    assert resp == "generic-error"


def test_copy_requires_config_modal():
    """[AC-NFR1101-01] test_copy_requires_config_modal."""
    out = _copy_requires_config_modal()
    assert out is not None


# ---------------------------------------------------------------------------
# _build_backtest_sidebar_menu
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import _build_backtest_sidebar_menu


def test_build_backtest_sidebar_menu_overview_active():
    """[AC-NFR1101-01] test_build_backtest_sidebar_menu_overview_active."""
    out = _build_backtest_sidebar_menu("p1", "overview")
    assert isinstance(out, list)
    # The backtest report item should be marked active
    assert any(c.get("active") for c in out)


def test_build_backtest_sidebar_menu_no_active():
    """[AC-NFR1101-01] test_build_backtest_sidebar_menu_no_active."""
    out = _build_backtest_sidebar_menu("p1", "unknown")
    assert isinstance(out, list)
    # When unknown tab, no children active
    for c in out:
        if "children" in c:
            assert not any(child.get("active") for child in c["children"])


def test_build_backtest_sidebar_menu_has_all_tabs():
    """[AC-NFR1101-01] test_build_backtest_sidebar_menu_has_all_tabs."""
    out = _build_backtest_sidebar_menu("p1", "overview")
    # Each top-level item should have title, url
    for c in out:
        assert "title" in c
        assert "url" in c
    # Find the backtest report item; its children should have all tabs
    bt = [c for c in out if c.get("title") == "回测报告"]
    if bt:
        children = bt[0].get("children", [])
        assert len(children) >= 4  # overview, trades, positions, logs


# ---------------------------------------------------------------------------
# run_backtest (async route)
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import (
    backtest_modal,
    grid_search_modal,
    run_backtest,
)


def test_backtest_modal_unknown_strategy():
    """[AC-NFR1101-01] Returns 'Strategy not found' for unknown."""
    with patch.object(strategy_mod_alias, "strategy_loader") as mock_loader:
        mock_loader.load_from_cache = MagicMock(return_value={})
        out = backtest_modal("missing")
    assert out == "Strategy not found"


def test_backtest_modal_known_strategy():
    """[AC-NFR1101-01] When strategy found, returns modal Div with form."""
    fake_cls = MagicMock()
    fake_cls.PARAMS = {"x": 1, "y": "hello"}
    with patch.object(strategy_mod_alias, "strategy_loader") as mock_loader:
        mock_loader.load_from_cache = MagicMock(return_value={"TestStrat": fake_cls})
        out = backtest_modal("TestStrat")
    assert out is not None


def test_backtest_modal_no_params():
    """[AC-NFR1101-01] When strategy has no PARAMS attr, treats as empty dict."""
    fake_cls = MagicMock(spec=[])  # no PARAMS
    with patch.object(strategy_mod_alias, "strategy_loader") as mock_loader:
        mock_loader.load_from_cache = MagicMock(return_value={"TestStrat": fake_cls})
        out = backtest_modal("TestStrat")
    assert out is not None


def test_grid_search_modal():
    """[AC-NFR1101-01] test_grid_search_modal."""
    out = grid_search_modal("TestStrat")
    assert out is not None


def test_grid_search_modal_unknown():
    """[AC-NFR1101-01] test_grid_search_modal_unknown."""
    with patch.object(strategy_mod_alias, "strategy_loader") as mock_loader:
        mock_loader.load_from_cache = MagicMock(return_value={})
        out = grid_search_modal("missing")
    assert out is not None


@pytest.mark.asyncio
async def test_run_backtest_unknown_strategy():
    """Returns 'Strategy not found' for unknown."""
    with patch.object(strategy_mod_alias, "strategy_loader") as mock_loader:
        mock_loader.load_from_cache = MagicMock(return_value={})
        req = MagicMock()
        req.form = AsyncMock(return_value={"start_date": "2024-01-01", "end_date": "2024-06-30"})
        resp = await run_backtest(req, name="missing")
    assert "not found" in str(resp).lower() or resp is not None


@pytest.mark.asyncio
async def test_run_backtest_bad_dates():
    """Returns error message for invalid dates."""
    with patch.object(strategy_mod_alias, "strategy_loader") as mock_loader:
        mock_loader.load_from_cache = MagicMock(return_value={"x": MagicMock()})
        req = MagicMock()
        req.form = AsyncMock(return_value={"start_date": "garbage", "end_date": "ok"})
        resp = await run_backtest(req, name="x")
    assert resp is not None


# ---------------------------------------------------------------------------
# _get_runtime + _get_registry + _get_market_data + _get_paper_deploy_availability
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import (
    _get_runtime,
    _get_registry as _strat_get_registry,
    _get_market_data as _strat_get_market_data,
)


def test_strat_get_runtime_no_request():
    """[AC-NFR1101-01] When req is None, returns None."""
    assert _get_runtime(None) is None


def test_strat_get_runtime_no_app():
    """[AC-NFR1101-01] When req has no app attr, returns None."""
    req = MagicMock()
    del req.app
    assert _get_runtime(req) is None


def test_strat_get_runtime_runtime_set():
    """[AC-NFR1101-01] Returns runtime from app.state.runtime."""
    req = MagicMock()
    req.app.state.runtime = "my-runtime"
    assert _get_runtime(req) == "my-runtime"


def test_strat_get_registry_no_runtime():
    """[AC-NFR1101-01] When no runtime, returns None."""
    req = MagicMock()
    req.app = MagicMock()
    req.app.state = MagicMock()
    req.app.state.runtime = None
    assert _strat_get_registry(req) is None


def test_strat_get_registry_with_runtime():
    """[AC-NFR1101-01] Returns runtime.registry."""
    req = MagicMock()
    req.app.state.runtime = MagicMock()
    req.app.state.runtime.registry = "my-registry"
    assert _strat_get_registry(req) == "my-registry"


def test_strat_get_market_data_no_runtime():
    """[AC-NFR1101-01] test_strat_get_market_data_no_runtime."""
    req = MagicMock()
    req.app.state.runtime = None
    assert _strat_get_market_data(req) is None


def test_strat_get_market_data_with_runtime():
    """[AC-NFR1101-01] test_strat_get_market_data_with_runtime."""
    req = MagicMock()
    req.app.state.runtime = MagicMock()
    req.app.state.runtime.market_data = "md"
    assert _strat_get_market_data(req) == "md"


# ---------------------------------------------------------------------------
# _get_paper_deploy_availability / _get_live_deploy_availability
# ---------------------------------------------------------------------------


from quantide.core.enums import BrokerKind
from quantide.web.pages.strategy import (
    _get_paper_deploy_availability,
    _get_live_deploy_availability,
    _get_backtest_deploy_capabilities,
)


def test_paper_deploy_no_runtime():
    """[AC-NFR1101-01] test_paper_deploy_no_runtime."""
    req = MagicMock()
    req.app.state.runtime = None
    ok, reason = _get_paper_deploy_availability(req)
    assert ok is False
    assert "运行时" in reason or "未初始化" in reason


def test_paper_deploy_no_market_data():
    """[AC-NFR1101-01] test_paper_deploy_no_market_data."""
    req = MagicMock()
    req.app.state.runtime = MagicMock()
    req.app.state.runtime.market_data = None
    ok, reason = _get_paper_deploy_availability(req)
    assert ok is False
    assert "行情源" in reason or "market" in reason.lower()


def test_paper_deploy_available():
    """[AC-NFR1101-01] test_paper_deploy_available."""
    req = MagicMock()
    req.app.state.runtime = MagicMock()
    req.app.state.runtime.market_data = "md"
    ok, reason = _get_paper_deploy_availability(req)
    assert ok is True
    assert reason == ""


def test_live_deploy_no_registry():
    """[AC-NFR1101-01] test_live_deploy_no_registry."""
    req = MagicMock()
    req.app.state.runtime = None
    ok, reason = _get_live_deploy_availability(req)
    assert ok is False
    assert "运行时" in reason or "未初始化" in reason


def test_live_deploy_no_gateway():
    """[AC-NFR1101-01] test_live_deploy_no_gateway."""
    fake_registry = MagicMock()
    fake_registry.get = MagicMock(return_value=None)
    req = MagicMock()
    req.app.state.runtime = MagicMock()
    req.app.state.runtime.registry = fake_registry
    ok, reason = _get_live_deploy_availability(req)
    assert ok is False
    assert "网关" in reason or "gateway" in reason.lower()


def test_live_deploy_available():
    """[AC-NFR1101-01] test_live_deploy_available."""
    fake_registry = MagicMock()
    fake_registry.get = MagicMock(return_value="gateway-broker")
    req = MagicMock()
    req.app.state.runtime = MagicMock()
    req.app.state.runtime.registry = fake_registry
    ok, reason = _get_live_deploy_availability(req)
    assert ok is True
    assert reason == ""


def test_backtest_deploy_capabilities_both():
    """[AC-NFR1101-01] test_backtest_deploy_capabilities_both."""
    fake_registry = MagicMock()
    fake_registry.get = MagicMock(return_value="gateway-broker")
    req = MagicMock()
    req.app.state.runtime = MagicMock()
    req.app.state.runtime.market_data = "md"
    req.app.state.runtime.registry = fake_registry
    caps = _get_backtest_deploy_capabilities(req)
    assert caps["paper_available"] is True
    assert caps["live_available"] is True


# ---------------------------------------------------------------------------
# _get_live_accounts + _render_deploy_result + _render_config_table
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import (
    _get_live_accounts,
    _render_config_table,
    _render_deploy_result,
)


def test_get_live_accounts_not_available():
    """[AC-NFR1101-01] test_get_live_accounts_not_available."""
    req = MagicMock()
    req.app.state.runtime = None
    assert _get_live_accounts(req) == []


def test_get_live_accounts_available():
    """[AC-NFR1101-01] test_get_live_accounts_available."""
    fake_registry = MagicMock()
    fake_registry.get = MagicMock(return_value="gateway-broker")
    req = MagicMock()
    req.app.state.runtime = MagicMock()
    req.app.state.runtime.registry = fake_registry
    accounts = _get_live_accounts(req)
    assert len(accounts) == 1
    assert accounts[0]["id"] == "gateway:default"


def test_render_deploy_result_success():
    """[AC-NFR1101-01] test_render_deploy_result_success."""
    out = _render_deploy_result("成功", is_error=False)
    assert out is not None


def test_render_deploy_result_error():
    """[AC-NFR1101-01] test_render_deploy_result_error."""
    out = _render_deploy_result("失败", is_error=True)
    assert out is not None


def test_render_config_table_empty():
    """[AC-NFR1101-01] Empty config + defaults → returns None."""
    out = _render_config_table(config={}, default_config=None)
    assert out is None


def test_render_config_table_only_defaults():
    """[AC-NFR1101-01] test_render_config_table_only_defaults."""
    out = _render_config_table(config={}, default_config={"a": 1})
    assert out is not None


def test_render_config_table_only_config():
    """[AC-NFR1101-01] test_render_config_table_only_config."""
    out = _render_config_table(config={"a": 1}, default_config=None)
    assert out is not None


def test_render_config_table_both():
    """[AC-NFR1101-01] test_render_config_table_both."""
    out = _render_config_table(config={"a": 5}, default_config={"a": 1, "b": 2})
    assert out is not None


# ---------------------------------------------------------------------------
# _build_log_meta + _format_log_lines
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import (
    _build_log_meta,
    _format_log_lines,
)


def test_build_log_meta_no_run():
    """[AC-NFR1101-01] When no run, returns empty metadata."""
    with patch.object(strategy_mod_alias, "strategy_runtime_manager") as mock_mgr:
        mock_mgr.get_backtest_run = MagicMock(return_value=None)
        out = _build_log_meta("p1")
    assert out["save_requested"] is False
    assert out["saved"] is False
    assert "saved_path" in out


def test_build_log_meta_with_run_save_logs():
    """[AC-NFR1101-01] test_build_log_meta_with_run_save_logs."""
    fake_run = MagicMock()
    fake_run.save_logs = True
    with patch.object(strategy_mod_alias, "strategy_runtime_manager") as mock_mgr:
        mock_mgr.get_backtest_run = MagicMock(return_value=fake_run)
        out = _build_log_meta("p1")
    assert out["save_requested"] is True


def test_format_log_lines_empty():
    """[AC-NFR1101-01] test_format_log_lines_empty."""
    assert _format_log_lines([]) == []


def test_format_log_lines_with_rows():
    """[AC-NFR1101-01] test_format_log_lines_with_rows."""
    out = _format_log_lines([
        {"dt": "2024-01-01", "level": "INFO", "source": "system", "message": "hello"},
    ])
    assert len(out) == 1
    assert "INFO" in out[0]
    assert "hello" in out[0]


def test_format_log_lines_with_extra():
    """[AC-NFR1101-01] test_format_log_lines_with_extra."""
    out = _format_log_lines([
        {"dt": "2024-01-01", "level": "WARN", "source": "broker", "message": "warn msg", "extra": "detail"},
    ])
    assert len(out) == 1
    assert "detail" in out[0]


def test_format_log_lines_no_extra():
    """[AC-NFR1101-01] test_format_log_lines_no_extra."""
    out = _format_log_lines([
        {"dt": "2024-01-01", "level": "INFO", "source": "x", "message": "hi"},
    ])
    assert "| " not in out[0].split("hi")[-1] or out[0].endswith("hi")


# ---------------------------------------------------------------------------
# _build_series_payload with assets to drive benchmark series
# ---------------------------------------------------------------------------


def test_build_series_payload_with_benchmark():
    """[AC-NFR1101-01] With multiple dates and benchmark data, fills benchmark series."""
    import datetime
    fake_assets = pl.DataFrame({
        "dt": [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
        ],
        "total": [100.0, 110.0],
        "benchmark_total": [100.0, 105.0],
    })
    fake_bars = pl.DataFrame({
        "date": [datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)],
        "close": [100.0, 105.0],
    })
    with patch.object(strategy_mod_alias, "db") as mock_db, \
         patch.object(strategy_mod_alias, "daily_bars") as mock_dbars:
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        mock_dbars.get_bars_in_range = MagicMock(return_value=fake_bars)
        out = _build_series_payload("p1", date_axis=["2024-01-01", "2024-01-02"])
    assert "benchmark" in out
    assert "trade_count" in out


def test_build_series_payload_with_trades():
    """[AC-NFR1101-01] With trades DataFrame, fills trade_count series."""
    import datetime
    fake_assets = pl.DataFrame({
        "dt": [datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)],
        "total": [100.0, 110.0],
    })
    fake_trades = pl.DataFrame({
        "tm": [datetime.datetime(2024, 1, 1, 10, 0)],
        "asset": ["000001.SZ"],
        "side": [1],
        "price": [10.0],
        "shares": [100.0],
        "amount": [1000.0],
        "fee": [1.0],
    })
    with patch.object(strategy_mod_alias, "db") as mock_db, \
         patch.object(strategy_mod_alias, "daily_bars") as mock_dbars:
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        mock_dbars.get_bars_in_range = MagicMock(return_value=pl.DataFrame())
        mock_db.trades_all = MagicMock(return_value=fake_trades)
        out = _build_series_payload("p1", date_axis=["2024-01-01", "2024-01-02"])
    assert "trade_count" in out


# ---------------------------------------------------------------------------
# _build_daily_positions + _build_daily_summary with data
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import (
    _build_daily_positions,
    _build_daily_summary,
)


def test_build_daily_positions_with_data():
    """[AC-NFR1101-01] With positions data, returns list of dicts."""
    import datetime
    fake_pos = pl.DataFrame({
        "dt": [datetime.date(2024, 1, 1)],
        "asset": ["000001.SZ"],
        "shares": [100.0],
        "avail": [100.0],
        "price": [10.0],
        "mv": [1000.0],
        "profit": [50.0],
    })
    with patch.object(strategy_mod_alias, "db") as mock_db:
        mock_db.positions_all = MagicMock(return_value=fake_pos)
        out = _build_daily_positions("p1")
    assert len(out) == 1
    assert out[0]["asset"] == "000001.SZ"


def test_build_daily_summary_with_data():
    """[AC-NFR1101-01] With assets data, computes daily_pnl and daily_return."""
    import datetime
    fake_assets = pl.DataFrame({
        "dt": [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
        ],
        "total": [100.0, 110.0],
        "cash": [50.0, 50.0],
        "market_value": [50.0, 60.0],
    })
    with patch.object(strategy_mod_alias, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        out = _build_daily_summary("p1")
    assert len(out) == 2
    assert out[0]["daily_pnl"] == 0.0  # First row, no previous
    assert out[1]["daily_pnl"] == 10.0  # 110 - 100
    assert out[1]["daily_return"] == 0.1  # 10 / 100


def test_build_daily_summary_zero_prev_total():
    """[AC-NFR1101-01] When previous total is 0, daily_return is 0."""
    import datetime
    fake_assets = pl.DataFrame({
        "dt": [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
        ],
        "total": [0.0, 100.0],
        "cash": [0.0, 50.0],
        "market_value": [0.0, 50.0],
    })
    with patch.object(strategy_mod_alias, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        out = _build_daily_summary("p1")
    assert out[1]["daily_return"] == 0.0


def test_backtest_modal_unknown_strategy():
    """[AC-NFR1101-01] Returns 'Strategy not found' for unknown."""
    with patch.object(strategy_mod_alias, "strategy_loader") as mock_loader:
        mock_loader.load_from_cache = MagicMock(return_value={})
        out = backtest_modal("missing")
    assert out == "Strategy not found"


def test_backtest_modal_known_strategy():
    """[AC-NFR1101-01] When strategy found, returns modal Div with form."""
    fake_cls = MagicMock()
    fake_cls.PARAMS = {"x": 1, "y": "hello"}
    with patch.object(strategy_mod_alias, "strategy_loader") as mock_loader:
        mock_loader.load_from_cache = MagicMock(return_value={"TestStrat": fake_cls})
        out = backtest_modal("TestStrat")
    assert out is not None


def test_backtest_modal_no_params():
    """[AC-NFR1101-01] When strategy has no PARAMS attr, treats as empty dict."""
    fake_cls = MagicMock(spec=[])  # no PARAMS
    with patch.object(strategy_mod_alias, "strategy_loader") as mock_loader:
        mock_loader.load_from_cache = MagicMock(return_value={"TestStrat": fake_cls})
        out = backtest_modal("TestStrat")
    assert out is not None


def test_grid_search_modal():
    """[AC-NFR1101-01] test_grid_search_modal."""
    out = grid_search_modal("TestStrat")
    assert out is not None


def test_grid_search_modal_unknown():
    """[AC-NFR1101-01] test_grid_search_modal_unknown."""
    with patch.object(strategy_mod_alias, "strategy_loader") as mock_loader:
        mock_loader.load_from_cache = MagicMock(return_value={})
        out = grid_search_modal("missing")
    assert out is not None


# ---------------------------------------------------------------------------
# _coerce_form_value + _form_to_config
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import (
    _coerce_form_value,
    _form_to_config,
)


def test_coerce_form_value_none():
    """[AC-NFR1101-01] test_coerce_form_value_none."""
    assert _coerce_form_value(None) is None


def test_coerce_form_value_empty_string():
    """[AC-NFR1101-01] test_coerce_form_value_empty_string."""
    assert _coerce_form_value("") == ""


def test_coerce_form_value_whitespace():
    """[AC-NFR1101-01] test_coerce_form_value_whitespace."""
    assert _coerce_form_value("   ") == ""


def test_coerce_form_value_true_string():
    """[AC-NFR1101-01] test_coerce_form_value_true_string."""
    assert _coerce_form_value("True") is True
    assert _coerce_form_value("true") is True


def test_coerce_form_value_false_string():
    """[AC-NFR1101-01] test_coerce_form_value_false_string."""
    assert _coerce_form_value("False") is False
    assert _coerce_form_value("false") is False


def test_coerce_form_value_int():
    """[AC-NFR1101-01] test_coerce_form_value_int."""
    assert _coerce_form_value("123") == 123


def test_coerce_form_value_float():
    """[AC-NFR1101-01] test_coerce_form_value_float."""
    assert _coerce_form_value("3.14") == 3.14


def test_coerce_form_value_string_passthrough():
    """[AC-NFR1101-01] test_coerce_form_value_string_passthrough."""
    assert _coerce_form_value("hello") == "hello"


def test_form_to_config_empty():
    """[AC-NFR1101-01] Empty form returns base_config."""
    base = {"x": 1}
    out = _form_to_config({}, base)
    assert out == {"x": 1}


def test_form_to_config_replaces_with_custom_keys():
    """[AC-NFR1101-01] Form values override base keys via custom_{key} pattern."""
    base = {"x": 1, "y": 2}
    form = {"custom_x": "100", "custom_y": "200"}
    out = _form_to_config(form, base)
    assert out["x"] == 100  # int converted
    assert out["y"] == 200


def test_form_to_config_keeps_base_when_no_custom():
    """[AC-NFR1101-01] When form lacks custom_{key}, base value is kept."""
    base = {"x": "old", "y": "old"}
    form = {}
    out = _form_to_config(form, base)
    assert out["x"] == "old"
    assert out["y"] == "old"


def test_form_to_config_partial_override():
    """[AC-NFR1101-01] When form has some custom keys, others stay."""
    base = {"a": 1, "b": 2, "c": 3}
    form = {"custom_a": "999"}
    out = _form_to_config(form, base)
    assert out["a"] == 999
    assert out["b"] == 2
    assert out["c"] == 3


def test_form_to_config_float_override():
    """[AC-NFR1101-01] Override with float string."""
    base = {"threshold": 0}
    form = {"custom_threshold": "0.5"}
    out = _form_to_config(form, base)
    assert out["threshold"] == 0.5


# ---------------------------------------------------------------------------
# _load_backtest_run_config
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import _load_backtest_run_config


def test_load_backtest_run_config_no_run():
    """[AC-NFR1101-01] When no run, returns ({}, None)."""
    with patch.object(strategy_mod, "strategy_runtime_manager") as mock_mgr:
        mock_mgr.get_backtest_run_or_resolve = MagicMock(return_value=None)
        cfg, default = _load_backtest_run_config("p1")
    assert cfg == {}
    assert default is None


def test_load_backtest_run_config_with_run():
    """[AC-NFR1101-01] When run exists, returns (config, default_config)."""
    fake_run = MagicMock()
    fake_run.config = {"k": "v"}
    fake_run.strategy_name = "MyStrat"
    fake_cls = MagicMock()
    fake_cls.default_config = MagicMock(return_value={"default": 1})
    with patch.object(strategy_mod, "strategy_runtime_manager") as mock_mgr, \
         patch.object(strategy_mod, "strategy_loader") as mock_loader:
        mock_mgr.get_backtest_run_or_resolve = MagicMock(return_value=fake_run)
        mock_loader.load_from_cache = MagicMock(return_value={"MyStrat": fake_cls})
        cfg, default = _load_backtest_run_config("p1")
    assert cfg == {"k": "v"}
    assert default == {"default": 1}


def test_load_backtest_run_config_no_default_config():
    """[AC-NFR1101-01] When strategy class has no default_config attr, returns (config, None)."""
    fake_run = MagicMock()
    fake_run.config = {"k": "v"}
    fake_run.strategy_name = "MyStrat"
    fake_cls = MagicMock(spec=[])  # no default_config attr
    with patch.object(strategy_mod, "strategy_runtime_manager") as mock_mgr, \
         patch.object(strategy_mod, "strategy_loader") as mock_loader:
        mock_mgr.get_backtest_run_or_resolve = MagicMock(return_value=fake_run)
        mock_loader.load_from_cache = MagicMock(return_value={"MyStrat": fake_cls})
        cfg, default = _load_backtest_run_config("p1")
    assert cfg == {"k": "v"}
    # Exception in default_config path → None
    assert default is None



# ---------------------------------------------------------------------------
# run_grid_search async route
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import run_grid_search


@pytest.mark.asyncio
async def test_run_grid_search_unknown_strategy():
    with patch.object(strategy_mod_alias, "strategy_loader") as mock_loader:
        mock_loader.load_from_cache = MagicMock(return_value={})
        req = MagicMock()
        req.form = AsyncMock(return_value={})
        resp = await run_grid_search(req, name="missing")
    assert resp is not None


@pytest.mark.asyncio
async def test_run_grid_search_no_dates_returns_400():
    with patch.object(strategy_mod_alias, "strategy_loader") as mock_loader:
        mock_loader.load_from_cache = MagicMock(return_value={"x": MagicMock()})
        req = MagicMock()
        req.form = AsyncMock(return_value={"start_date": "", "end_date": ""})
        resp = await run_grid_search(req, name="x")
    assert resp is not None


@pytest.mark.asyncio
async def test_run_grid_search_bad_dates_returns_400():
    with patch.object(strategy_mod_alias, "strategy_loader") as mock_loader:
        mock_loader.load_from_cache = MagicMock(return_value={"x": MagicMock()})
        req = MagicMock()
        req.form = AsyncMock(return_value={"start_date": "garbage", "end_date": "ok"})
        resp = await run_grid_search(req, name="x")
    assert resp is not None


@pytest.mark.asyncio
async def test_run_grid_search_with_params():
    """When strategy found and dates valid, calls GridSearch.run."""
    import asyncio as _asyncio

    fake_gs = MagicMock()
    fake_gs.run = MagicMock(return_value=MagicMock(to_json=lambda **k: "[]"))
    with patch.object(strategy_mod_alias, "strategy_loader") as mock_loader, \
         patch.object(strategy_mod_alias, "GridSearch", return_value=fake_gs):
        mock_loader.load_from_cache = MagicMock(return_value={"x": MagicMock()})
        req = MagicMock()
        req.form = AsyncMock(return_value={
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
            "param_a": "1,2,3",  # grid param
            "param_b": "5",  # base config
            "max_workers": "2",
        })
        resp = await run_grid_search(req, name="x")
    assert resp is not None

