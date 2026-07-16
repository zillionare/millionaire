"""B14-strategy: Coverage tests for quantide/web/pages/strategy.py.

Target lines:
- 2116: deploy_backtest_to_paper success return tuple
- 2175: deploy_backtest_to_live success return tuple
- 2356-2358: run_grid_search non-empty results_df -> sort + iter_rows
- 2436, 2438: backtest_result metric value positive/negative branches
- 2808-2814: backtest_result positions multi-date grouping
- 2921: load_saved_backtest_log_panel success path
- 3061, 3063: scan_confirm_modal renders
- 3193: _config_modal_html is_error=True branch
- 3258: save_scan_config success Modal
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl
import pytest

from quantide.web.pages import strategy as strategy_mod
from quantide.web.pages.strategy import (
    _config_modal_html,
    backtest_result,
    deploy_backtest_to_live,
    deploy_backtest_to_paper,
    load_saved_backtest_log_panel,
    run_grid_search,
    save_scan_config,
    scan_confirm_modal,
)


# ---------------------------------------------------------------------------
# Helper: build a fake request
# ---------------------------------------------------------------------------


def _make_req(*, form_data=None, app=None):
    req = MagicMock()
    req.form = AsyncMock(return_value=form_data or {})
    req.app = app or MagicMock()
    req.scope = {"registry": MagicMock()} if app is None else app
    req.query_params = {}
    return req


# ---------------------------------------------------------------------------
# scan_confirm_modal: lines 3061, 3063
# ---------------------------------------------------------------------------


def test_scan_confirm_modal_renders(monkeypatch):
    """scan_confirm_modal returns Div with scan scope list."""
    monkeypatch.setattr(
        strategy_mod.strategy_loader,
        "get_scan_directories",
        lambda: ["/path/a", "/path/b"],
    )
    out = scan_confirm_modal(MagicMock())
    text = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "确认扫描" in text
    assert "/path/a" in text
    assert "/path/b" in text


def test_scan_confirm_modal_empty_dirs(monkeypatch):
    """scan_confirm_modal with empty scan dirs still renders."""
    monkeypatch.setattr(
        strategy_mod.strategy_loader, "get_scan_directories", lambda: []
    )
    out = scan_confirm_modal(MagicMock())
    text = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "确认扫描" in text


# ---------------------------------------------------------------------------
# _config_modal_html: line 3193 (is_error=True branch)
# ---------------------------------------------------------------------------


def test_config_modal_html_is_error_branch(monkeypatch):
    """is_error=True, no error_message -> '请输入有效的用户策略目录' (line 3193)."""
    monkeypatch.setattr(
        strategy_mod.strategy_loader,
        "get_builtin_scan_directory",
        lambda: "/builtin",
    )
    out = _config_modal_html("/some/dir", is_error=True, error_message="")
    text = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "请输入有效的用户策略目录" in text


def test_config_modal_html_error_message_branch(monkeypatch):
    """error_message set -> P(error_message) shown (line 3191)."""
    monkeypatch.setattr(
        strategy_mod.strategy_loader,
        "get_builtin_scan_directory",
        lambda: "/builtin",
    )
    out = _config_modal_html("/some/dir", is_error=False, error_message="boom")
    text = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "boom" in text


def test_config_modal_html_default_message_branch(monkeypatch):
    """Neither error_message nor is_error -> default info message."""
    monkeypatch.setattr(
        strategy_mod.strategy_loader,
        "get_builtin_scan_directory",
        lambda: "/builtin",
    )
    out = _config_modal_html("/some/dir", is_error=False, error_message="")
    text = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "用户策略目录" in text


# ---------------------------------------------------------------------------
# save_scan_config: line 3258 (success Modal)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_scan_config_success_returns_saved_modal(monkeypatch):
    """save_scan_config with valid absolute path -> Modal '配置已保存' (line 3258)."""
    req = _make_req(form_data={"scan-dir-input": "/tmp/strategies"})
    monkeypatch.setattr(
        strategy_mod.strategy_loader, "set_scan_directory", lambda d: None
    )
    # Stub _normalize_scan_directory to skip filesystem existence check.
    monkeypatch.setattr(
        strategy_mod,
        "_normalize_scan_directory",
        lambda d: (d, MagicMock()),
    )
    out = await save_scan_config(req)
    text = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "配置已保存" in text
    assert "/tmp/strategies" in text


# ---------------------------------------------------------------------------
# load_saved_backtest_log_panel: line 2921 (success path)
# ---------------------------------------------------------------------------


def test_load_saved_backtest_log_panel_success(monkeypatch):
    """load_saved_backtest_log_panel with rows -> _build_log_panel called."""
    monkeypatch.setattr(
        strategy_mod, "_resolve_backtest_status", lambda pid: ("finished", "")
    )
    monkeypatch.setattr(
        strategy_mod,
        "load_saved_backtest_logs",
        lambda pid, limit=200: [
            {
                "dt": "2024-01-02 09:30:00",
                "level": "INFO",
                "source": "runner",
                "message": "log entry",
                "extra": "",
            }
        ],
    )
    monkeypatch.setattr(
        strategy_mod,
        "_build_log_meta",
        lambda pid: {"save_requested": True, "saved": True, "saved_path": "/tmp/x.jsonl"},
    )
    out = load_saved_backtest_log_panel("demo-pf")
    text = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "log entry" in text
    assert "已保存文件" in text


# ---------------------------------------------------------------------------
# backtest_result: lines 2436, 2438 (metric positive/negative branches)
# and 2808-2814 (positions multi-date grouping)
# ---------------------------------------------------------------------------


class _FakePageRequest:
    """Minimal fake request for backtest_result."""

    def __init__(self, query=None):
        self.query_params = query or {}


def _monkeypatch_backtest_helpers(monkeypatch, *, metrics=None,
                                   positions_rows=None, trade_rows=None,
                                   log_rows=None):
    """Apply common monkeypatches for backtest_result testing."""
    monkeypatch.setattr(
        strategy_mod, "_resolve_backtest_status", lambda pid: ("finished", "")
    )
    monkeypatch.setattr(
        strategy_mod, "_build_metrics_payload", lambda pid: metrics or {}
    )
    monkeypatch.setattr(
        strategy_mod, "_build_date_axis", lambda pid: ["2024-01-02"]
    )
    monkeypatch.setattr(
        strategy_mod,
        "_build_series_payload",
        lambda pid, da: {
            "date_axis": da,
            "total": [1.0],
            "benchmark": [1.0],
            "daily_pnl": [0.0],
            "trade_count": [0],
        },
    )
    monkeypatch.setattr(
        strategy_mod, "_build_trade_rows", lambda pid, limit=200: trade_rows or []
    )
    monkeypatch.setattr(
        strategy_mod, "_build_daily_positions", lambda pid: positions_rows or []
    )
    monkeypatch.setattr(
        strategy_mod, "_build_log_rows", lambda pid, limit=200: log_rows or []
    )
    monkeypatch.setattr(
        strategy_mod,
        "_build_log_meta",
        lambda pid: {"save_requested": False, "saved": False, "saved_path": "/tmp/x.jsonl"},
    )


def test_backtest_result_metric_positive_branch(monkeypatch):
    """metrics with positive value -> 'text-red-600' (line 2436)."""
    metrics = {
        "annual_return": 0.25,  # positive -> red
        "sharpe": 1.5,
        "max_drawdown": -0.10,  # negative -> green
    }
    _monkeypatch_backtest_helpers(monkeypatch, metrics=metrics)
    html = strategy_mod.to_xml(
        backtest_result(_FakePageRequest(), {"auth": "admin"}, "demo-pf")
    )
    assert "text-red-600" in html
    assert "text-green-600" in html


def test_backtest_result_metric_zero_value_branch(monkeypatch):
    """metrics with zero value -> 'text-gray-700' branch (else case)."""
    metrics = {
        "annual_return": 0,  # zero -> gray
        "sharpe": 0,
    }
    _monkeypatch_backtest_helpers(monkeypatch, metrics=metrics)
    html = strategy_mod.to_xml(
        backtest_result(_FakePageRequest(), {"auth": "admin"}, "demo-pf")
    )
    assert "text-gray-700" in html


def test_backtest_result_positions_multi_date_grouping(monkeypatch):
    """positions with multiple dates -> date group headers inserted
    (lines 2808-2814)."""
    positions_rows = [
        {"dt": "2024-01-02", "asset": "000001.SZ", "shares": 100.0,
         "avail": 100.0, "price": 10.0, "mv": 1000.0, "profit": 50.0},
        {"dt": "2024-01-02", "asset": "600000.SH", "shares": 50.0,
         "avail": 50.0, "price": 5.0, "mv": 250.0, "profit": -10.0},
        {"dt": "2024-01-03", "asset": "000001.SZ", "shares": 100.0,
         "avail": 100.0, "price": 11.0, "mv": 1100.0, "profit": 100.0},
    ]
    _monkeypatch_backtest_helpers(monkeypatch, positions_rows=positions_rows)
    html = strategy_mod.to_xml(
        backtest_result(_FakePageRequest({"tab": "positions"}),
                        {"auth": "admin"}, "demo-pf")
    )
    # Each unique date should render as a date group header row (colspan=6).
    assert "2024-01-02" in html
    assert "2024-01-03" in html
    # Both assets render
    assert "000001.SZ" in html
    assert "600000.SH" in html


# ---------------------------------------------------------------------------
# run_grid_search: lines 2356-2358 (non-empty results_df)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_grid_search_with_non_empty_results(monkeypatch):
    """run_grid_search with non-empty results_df -> sort + iter_rows + render table."""
    form_data = {
        "start_date": "2024-01-01",
        "end_date": "2024-06-01",
        "max_workers": "2",
        "param_window": "5,10",
    }
    req = _make_req(form_data=form_data)
    strategy_cls = MagicMock()
    monkeypatch.setattr(
        strategy_mod.strategy_loader, "load_from_cache", lambda: {"MyStrat": strategy_cls}
    )

    # Non-empty results DataFrame with expected columns.
    fake_results = pl.DataFrame({
        "params": [{"window": 5}, {"window": 10}],
        "annual_return": [0.15, 0.10],
        "sharpe": [1.2, 0.9],
        "max_drawdown": [-0.05, -0.08],
    })

    class FakeGridSearch:
        def __init__(self, **kwargs):
            pass

        def run(self, save_logs=False):
            return fake_results

    monkeypatch.setattr(strategy_mod, "GridSearch", FakeGridSearch)

    out = await run_grid_search(req, "MyStrat")
    text = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    # Modal title and table render.
    assert "网格搜索结果" in text
    assert "参数" in text
    # Should show 2 result rows.
    assert "15.00%" in text
    assert "10.00%" in text


# ---------------------------------------------------------------------------
# deploy_backtest_to_paper: line 2116 (success return tuple)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_backtest_to_paper_success(monkeypatch):
    """deploy_to_paper success -> returns tuple with success message (line 2116)."""
    form_data = {"paper_principal": "1000000"}
    req = _make_req(form_data=form_data)
    # Stub registry to a non-None MagicMock
    req.scope = {"registry": MagicMock()}

    # No existing deployment -> proceeds to deploy
    monkeypatch.setattr(
        strategy_mod.strategy_runtime_manager,
        "get_active_backtest_deployment",
        lambda pid, kind: None,
    )
    monkeypatch.setattr(
        strategy_mod, "_load_backtest_run_config", lambda pid: ({}, {})
    )
    monkeypatch.setattr(strategy_mod, "_form_to_config", lambda form, base: {})
    monkeypatch.setattr(strategy_mod, "_get_market_data", lambda req: MagicMock())

    fake_runtime = MagicMock()
    fake_runtime.portfolio_id = "paper-pf-1"
    fake_runtime.strategy_id = "strat-1"
    monkeypatch.setattr(
        strategy_mod.strategy_runtime_manager,
        "deploy_to_paper",
        lambda **kwargs: fake_runtime,
    )
    # _get_backtest_deploy_capabilities may inspect registry; stub it.
    monkeypatch.setattr(
        strategy_mod, "_get_backtest_deploy_capabilities", lambda req: {}
    )

    out = await deploy_backtest_to_paper(req, "demo-pf")
    # Should be a tuple (Div, _render_deploy_result, _build_backtest_action_cell).
    assert isinstance(out, tuple)
    text = " ".join(
        strategy_mod.to_xml(o) if not isinstance(o, str) else o for o in out
    )
    assert "已转入仿真" in text
    assert "paper-pf-1" in text


# ---------------------------------------------------------------------------
# deploy_backtest_to_live: line 2175 (success return tuple)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_backtest_to_live_success(monkeypatch):
    """deploy_to_live success -> returns tuple with success message (line 2175)."""
    form_data = {"live_account_id": "gateway:default"}
    req = _make_req(form_data=form_data)
    req.scope = {"registry": MagicMock()}

    # Stub all the gating checks.
    monkeypatch.setattr(strategy_mod, "_get_live_accounts", lambda req: [{"id": "a1"}])
    monkeypatch.setattr(
        strategy_mod.strategy_runtime_manager,
        "get_active_backtest_deployment",
        lambda pid, kind: None,
    )
    monkeypatch.setattr(
        strategy_mod, "_load_backtest_run_config", lambda pid: ({}, {})
    )
    monkeypatch.setattr(strategy_mod, "_form_to_config", lambda form, base: {})
    monkeypatch.setattr(strategy_mod, "_get_market_data", lambda req: MagicMock())

    fake_runtime = MagicMock()
    fake_runtime.portfolio_id = "live-pf-1"
    fake_runtime.strategy_id = "strat-2"
    monkeypatch.setattr(
        strategy_mod.strategy_runtime_manager,
        "deploy_to_live",
        lambda **kwargs: fake_runtime,
    )
    monkeypatch.setattr(
        strategy_mod, "_get_backtest_deploy_capabilities", lambda req: {}
    )

    out = await deploy_backtest_to_live(req, "demo-pf")
    assert isinstance(out, tuple)
    text = " ".join(
        strategy_mod.to_xml(o) if not isinstance(o, str) else o for o in out
    )
    assert "已转入实盘" in text
    assert "live-pf-1" in text
