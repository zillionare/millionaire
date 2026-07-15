"""B09-strategy-round2: Targeted coverage for ``quantide/web/pages/strategy.py``.

Covers missing branches:
- ``_build_series_payload`` (date_axis beyond last_date, benchmark path)
- ``_load_backtest_run_config`` (exception branch / no-run branch)
- ``_form_to_config`` / ``_coerce_form_value`` branches
- ``deploy_backtest_to_paper`` (invalid principal / no registry / existing runtime / deploy failure)
- ``deploy_backtest_to_live`` (no registry / no live accounts / existing runtime / deploy failure)
- ``run_grid_search`` (invalid strategy / parse params / generic exception)
- ``run_scan`` (no strategies / with strategies / scan failure)
- ``save_scan_config`` (invalid directory / generic exception)
- ``copy_scan_examples`` (no directory / invalid directory / generic exception)
- ``grid_search_modal`` (not found / with PARAMS)
- ``backtest_ws`` (no portfolio_id / WebSocketDisconnect)
"""

from __future__ import annotations

import asyncio
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl
import pytest
from starlette.websockets import WebSocketDisconnect

from quantide.web.pages import strategy as strategy_mod
from quantide.web.pages.strategy import (
    _build_series_payload,
    _coerce_form_value,
    _form_to_config,
    _load_backtest_run_config,
    backtest_ws,
    copy_scan_examples,
    deploy_backtest_to_live,
    deploy_backtest_to_paper,
    grid_search_modal,
    run_grid_search,
    run_scan,
    save_scan_config,
)


def _make_req(
    *,
    scope: dict | None = None,
    form_data: dict | None = None,
    query_params: dict | None = None,
    app: MagicMock | None = None,
) -> MagicMock:
    """Build a fake Starlette request."""
    req = MagicMock()
    req.scope = scope or {}
    req.query_params = query_params or {}
    req.form = AsyncMock(return_value=form_data or {})
    req.app = app or MagicMock()
    return req


# ---------------------------------------------------------------------------
# _build_series_payload: date_axis beyond last_date + benchmark path
# ---------------------------------------------------------------------------


def test_build_series_payload_appends_none_when_dt_beyond_last_date(monkeypatch):
    """[AC-NFR1101-01] When date_axis has dates beyond last asset row, None is appended."""
    today = dt.date(2024, 1, 10)
    assets_df = pl.DataFrame({
        "dt": [dt.datetime(2024, 1, 1), dt.datetime(2024, 1, 5)],
        "total": [1_000_000.0, 1_010_000.0],
    })
    monkeypatch.setattr(strategy_mod.db, "query_assets", lambda pid: assets_df)
    monkeypatch.setattr(strategy_mod.db, "trades_all", lambda pid: pl.DataFrame())
    # daily_bars.get_bars_in_range returns non-empty frame to exercise benchmark branch.
    benchmark_df = pl.DataFrame({
        "date": [dt.date(2024, 1, 1), dt.date(2024, 1, 5)],
        "close": [10.0, 10.5],
    })
    monkeypatch.setattr(
        strategy_mod.daily_bars, "get_bars_in_range", lambda *a, **k: benchmark_df
    )
    # date_axis beyond last asset row (2024-01-05).
    date_axis = ["2024-01-01", "2024-01-05", "2024-01-10"]
    out = _build_series_payload("p1", date_axis)
    assert out["total"][2] is None  # date beyond last_date
    assert out["daily_pnl"][2] is None
    # Benchmark should be a populated list (not None entries everywhere).
    assert any(v is not None for v in out["benchmark"])


def test_build_series_payload_benchmark_exception_yields_empty_df(monkeypatch):
    """[AC-NFR1101-01] When daily_bars.get_bars_in_range raises, benchmark_df becomes empty frame."""
    assets_df = pl.DataFrame({
        "dt": [dt.datetime(2024, 1, 1)],
        "total": [1_000_000.0],
    })
    monkeypatch.setattr(strategy_mod.db, "query_assets", lambda pid: assets_df)
    monkeypatch.setattr(strategy_mod.db, "trades_all", lambda pid: pl.DataFrame())

    def _boom(*a, **k):
        raise RuntimeError("bars err")

    monkeypatch.setattr(strategy_mod.daily_bars, "get_bars_in_range", _boom)
    out = _build_series_payload("p1", ["2024-01-01"])
    assert out["benchmark"] == [None]


# ---------------------------------------------------------------------------
# _load_backtest_run_config
# ---------------------------------------------------------------------------


def test_load_backtest_run_config_returns_empty_when_no_run(monkeypatch):
    """[AC-NFR1101-01] No backtest run returns ({}, None)."""
    monkeypatch.setattr(
        strategy_mod.strategy_runtime_manager,
        "get_backtest_run_or_resolve",
        lambda pid: None,
    )
    out = _load_backtest_run_config("p1")
    assert out == ({}, None)


def test_load_backtest_run_config_swallows_strategy_loader_exception(monkeypatch):
    """[AC-NFR1101-01] When strategy_loader.load_from_cache raises, default_config becomes None."""
    fake_run = MagicMock()
    fake_run.config = {"a": 1}
    fake_run.strategy_name = "my-strategy"
    monkeypatch.setattr(
        strategy_mod.strategy_runtime_manager,
        "get_backtest_run_or_resolve",
        lambda pid: fake_run,
    )
    monkeypatch.setattr(strategy_mod.strategy_loader, "load_from_cache", MagicMock(side_effect=RuntimeError("boom")))
    config, default_config = _load_backtest_run_config("p1")
    assert config == {"a": 1}
    assert default_config is None


# ---------------------------------------------------------------------------
# _form_to_config / _coerce_form_value
# ---------------------------------------------------------------------------


def test_form_to_config_uses_base_value_when_form_key_missing():
    """[AC-NFR1101-01] When form lacks custom_*, base value is used."""
    out = _form_to_config({}, {"a": 1, "b": 2})
    assert out == {"a": 1, "b": 2}


def test_coerce_form_value_returns_empty_string_for_empty_text():
    """[AC-NFR1101-01] Empty stripped text returns ''."""
    assert _coerce_form_value("   ") == ""


def test_coerce_form_value_returns_bool_for_true_string():
    """[AC-NFR1101-01] 'true' string coerced to True."""
    assert _coerce_form_value("true") is True
    assert _coerce_form_value("false") is False


def test_coerce_form_value_returns_int_for_integer_string():
    """[AC-NFR1101-01] Integer string coerced to int."""
    assert _coerce_form_value("42") == 42


def test_coerce_form_value_returns_text_for_unparseable_string():
    """[AC-NFR1101-01] Non-numeric string returned as-is."""
    assert _coerce_form_value("hello") == "hello"


# ---------------------------------------------------------------------------
# deploy_backtest_to_paper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_backtest_to_paper_invalid_principal_returns_error_modal(monkeypatch):
    """[AC-NFR1101-01] Non-numeric principal returns error modal."""
    req = _make_req(form_data={"paper_principal": "abc"})
    monkeypatch.setattr(
        strategy_mod, "_load_backtest_run_config", lambda pid: ({}, None)
    )
    monkeypatch.setattr(strategy_mod, "_paper_deploy_modal", lambda *a, **k: "modal")
    out = await deploy_backtest_to_paper(req, "p1")
    assert out == "modal"


@pytest.mark.asyncio
async def test_deploy_backtest_to_paper_no_registry_returns_error_modal(monkeypatch):
    """[AC-NFR1101-01] When registry is None, error modal is returned."""
    req = _make_req(form_data={"paper_principal": "100000"})
    monkeypatch.setattr(strategy_mod, "_get_registry", lambda req: None)
    monkeypatch.setattr(
        strategy_mod, "_load_backtest_run_config", lambda pid: ({}, None)
    )
    monkeypatch.setattr(strategy_mod, "_paper_deploy_modal", lambda *a, **k: "modal")
    out = await deploy_backtest_to_paper(req, "p1")
    assert out == "modal"


@pytest.mark.asyncio
async def test_deploy_backtest_to_paper_existing_runtime_returns_already_message(monkeypatch):
    """[AC-NFR1101-01] Existing paper deployment returns a 'already in paper' message."""
    fake_runtime = MagicMock()
    fake_runtime.portfolio_id = "p-paper"
    fake_runtime.strategy_id = "s-1"
    monkeypatch.setattr(
        strategy_mod.strategy_runtime_manager,
        "get_active_backtest_deployment",
        lambda pid, kind: fake_runtime,
    )
    monkeypatch.setattr(strategy_mod, "_get_registry", lambda req: MagicMock())
    monkeypatch.setattr(strategy_mod, "_get_backtest_deploy_capabilities", lambda req: {})
    monkeypatch.setattr(strategy_mod, "_render_deploy_result", lambda *a, **k: "result")
    monkeypatch.setattr(strategy_mod, "_build_backtest_action_cell", lambda *a, **k: "cell")
    req = _make_req(form_data={"paper_principal": "100000"})
    out = await deploy_backtest_to_paper(req, "p1")
    assert isinstance(out, tuple)


@pytest.mark.asyncio
async def test_deploy_backtest_to_paper_deploy_failure_returns_error_modal(monkeypatch):
    """[AC-NFR1101-01] When deploy_to_paper raises, error modal is returned."""
    monkeypatch.setattr(
        strategy_mod.strategy_runtime_manager,
        "get_active_backtest_deployment",
        lambda pid, kind: None,
    )
    monkeypatch.setattr(strategy_mod, "_get_registry", lambda req: MagicMock())
    monkeypatch.setattr(strategy_mod, "_get_market_data", lambda req: None)
    monkeypatch.setattr(
        strategy_mod.strategy_runtime_manager,
        "deploy_to_paper",
        MagicMock(side_effect=RuntimeError("deploy failed")),
    )
    monkeypatch.setattr(
        strategy_mod, "_load_backtest_run_config", lambda pid: ({}, None)
    )
    monkeypatch.setattr(strategy_mod, "_paper_deploy_modal", lambda *a, **k: "error-modal")
    req = _make_req(form_data={"paper_principal": "100000"})
    out = await deploy_backtest_to_paper(req, "p1")
    assert out == "error-modal"


# ---------------------------------------------------------------------------
# deploy_backtest_to_live
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_backtest_to_live_no_registry_returns_live_modal(monkeypatch):
    """[AC-NFR1101-01] No registry returns the live deploy modal."""
    req = _make_req(form_data={"live_account_id": "gw:1"})
    monkeypatch.setattr(strategy_mod, "_get_registry", lambda req: None)
    monkeypatch.setattr(
        strategy_mod, "_load_backtest_run_config", lambda pid: ({}, None)
    )
    monkeypatch.setattr(strategy_mod, "_live_deploy_modal", lambda *a, **k: "live-modal")
    out = await deploy_backtest_to_live(req, "p1")
    assert out == "live-modal"


@pytest.mark.asyncio
async def test_deploy_backtest_to_live_no_live_accounts_returns_live_modal(monkeypatch):
    """[AC-NFR1101-01] No live accounts returns the live deploy modal."""
    req = _make_req(form_data={"live_account_id": "gw:1"})
    monkeypatch.setattr(strategy_mod, "_get_registry", lambda req: MagicMock())
    monkeypatch.setattr(strategy_mod, "_get_live_accounts", lambda req: [])
    monkeypatch.setattr(
        strategy_mod, "_load_backtest_run_config", lambda pid: ({}, None)
    )
    monkeypatch.setattr(strategy_mod, "_live_deploy_modal", lambda *a, **k: "live-modal")
    out = await deploy_backtest_to_live(req, "p1")
    assert out == "live-modal"


@pytest.mark.asyncio
async def test_deploy_backtest_to_live_deploy_failure_returns_dialog_modal(monkeypatch):
    """[AC-NFR1101-01] When deploy_to_live raises, dialog modal is returned."""
    monkeypatch.setattr(
        strategy_mod.strategy_runtime_manager,
        "get_active_backtest_deployment",
        lambda pid, kind: None,
    )
    monkeypatch.setattr(strategy_mod, "_get_registry", lambda req: MagicMock())
    monkeypatch.setattr(
        strategy_mod, "_get_live_accounts", lambda req: [{"id": "gw:1", "name": "live"}]
    )
    monkeypatch.setattr(strategy_mod, "_get_market_data", lambda req: None)
    monkeypatch.setattr(
        strategy_mod.strategy_runtime_manager,
        "deploy_to_live",
        MagicMock(side_effect=RuntimeError("deploy failed")),
    )
    monkeypatch.setattr(
        strategy_mod, "_load_backtest_run_config", lambda pid: ({}, None)
    )
    monkeypatch.setattr(strategy_mod, "_strategy_dialog_modal", lambda *a, **k: "error-dialog")
    req = _make_req(form_data={"live_account_id": "gw:1"})
    out = await deploy_backtest_to_live(req, "p1")
    assert out == "error-dialog"


# ---------------------------------------------------------------------------
# grid_search_modal
# ---------------------------------------------------------------------------


def test_grid_search_modal_returns_string_when_strategy_not_found(monkeypatch):
    """[AC-NFR1101-01] When strategy is missing, returns 'Strategy not found'."""
    monkeypatch.setattr(
        strategy_mod.strategy_loader, "load_from_cache", lambda: {}
    )
    out = grid_search_modal("missing")
    assert out == "Strategy not found"


def test_grid_search_modal_renders_param_inputs_from_params(monkeypatch):
    """[AC-NFR1101-01] Strategy with PARAMS dict renders param input fields."""
    class _FakeStrategy:
        PARAMS = {"window": 10}

    monkeypatch.setattr(
        strategy_mod.strategy_loader,
        "load_from_cache",
        lambda: {"my-strategy": _FakeStrategy},
    )
    out = grid_search_modal("my-strategy")
    rendered = strategy_mod.to_xml(out) if hasattr(out, "render") else str(out)
    assert "window" in rendered


# ---------------------------------------------------------------------------
# run_grid_search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_grid_search_returns_error_when_strategy_not_found(monkeypatch):
    """[AC-NFR1101-01] Missing strategy raises and the handler returns error div."""
    form = MagicMock()
    form.get = lambda key, default="": {"start_date": "2024-01-01", "end_date": "2024-12-31"}.get(key, default)
    form.items = lambda: [("start_date", "2024-01-01"), ("end_date", "2024-12-31")].__iter__().__next__()
    # Use a real dict-like form for items iteration.
    real_form = {"start_date": "2024-01-01", "end_date": "2024-12-31", "max_workers": "4"}
    req = _make_req(form_data=real_form)
    monkeypatch.setattr(
        strategy_mod.strategy_loader, "load_from_cache", lambda: {}
    )
    out = await run_grid_search(req, "missing")
    rendered = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "搜索失败" in rendered or "not found" in rendered.lower() or "Strategy" in rendered


# ---------------------------------------------------------------------------
# run_scan
# ---------------------------------------------------------------------------


def test_run_scan_returns_zero_strategies_modal(monkeypatch):
    """[AC-NFR1101-01] When scan finds 0 strategies, 'no strategies' modal is returned."""
    monkeypatch.setattr(
        strategy_mod.strategy_loader, "scan_and_cache", lambda: {}
    )
    monkeypatch.setattr(strategy_mod.strategy_loader, "get_scan_directories", lambda: [])
    out = run_scan(MagicMock())
    rendered = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "未发现任何策略" in rendered


def test_run_scan_returns_success_modal_when_strategies_found(monkeypatch):
    """[AC-NFR1101-01] Successful scan returns a success modal."""
    class _FakeStrategy:
        pass

    monkeypatch.setattr(
        strategy_mod.strategy_loader,
        "scan_and_cache",
        lambda: {"s1": _FakeStrategy, "s2": _FakeStrategy},
    )
    monkeypatch.setattr(strategy_mod.strategy_loader, "get_scan_directories", lambda: [])
    out = run_scan(MagicMock())
    rendered = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "成功发现 2 个策略" in rendered


def test_run_scan_failure_modal_when_scan_raises(monkeypatch):
    """[AC-NFR1101-01] When scan_and_cache raises, error modal is returned."""
    monkeypatch.setattr(
        strategy_mod.strategy_loader,
        "scan_and_cache",
        MagicMock(side_effect=RuntimeError("scan failed")),
    )
    out = run_scan(MagicMock())
    rendered = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "扫描失败" in rendered


# ---------------------------------------------------------------------------
# save_scan_config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_scan_config_invalid_directory_returns_error_modal(monkeypatch):
    """[AC-NFR1101-01] Invalid scan directory returns the config modal with error."""
    req = _make_req(form_data={"scan-dir-input": "relative/path"})
    monkeypatch.setattr(strategy_mod.strategy_loader, "set_scan_directory", lambda d: None)
    # _normalize_scan_directory raises ValueError for non-absolute paths.
    out = await save_scan_config(req)
    rendered = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "绝对路径" in rendered


@pytest.mark.asyncio
async def test_save_scan_config_generic_exception_logs_and_returns_error_modal(monkeypatch):
    """[AC-NFR1101-01] Generic exception path returns config modal with '保存失败' message."""
    req = _make_req(form_data={"scan-dir-input": "/tmp/exists"})
    monkeypatch.setattr(strategy_mod.strategy_loader, "set_scan_directory", lambda d: None)
    # Force the directory normalization to pass by patching _normalize_scan_directory.
    monkeypatch.setattr(
        strategy_mod,
        "_normalize_scan_directory",
        lambda d: (d, MagicMock()),
    )
    monkeypatch.setattr(strategy_mod.strategy_loader, "set_scan_directory", MagicMock(side_effect=RuntimeError("boom")))
    out = await save_scan_config(req)
    rendered = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "保存失败" in rendered


# ---------------------------------------------------------------------------
# copy_scan_examples
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_copy_scan_examples_no_directory_returns_requires_config_modal(monkeypatch):
    """[AC-NFR1101-01] Empty user scan directory returns the requires-config modal."""
    req = MagicMock()
    monkeypatch.setattr(
        strategy_mod.strategy_loader, "get_user_scan_directory", lambda: ""
    )
    out = await copy_scan_examples(req)
    rendered = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "请先设置用户策略目录" in rendered


@pytest.mark.asyncio
async def test_copy_scan_examples_invalid_directory_returns_error_modal(monkeypatch):
    """[AC-NFR1101-01] Invalid directory raises ValueError and returns error modal."""
    req = MagicMock()
    monkeypatch.setattr(
        strategy_mod.strategy_loader, "get_user_scan_directory", lambda: "relative/path"
    )
    out = await copy_scan_examples(req)
    rendered = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "复制失败" in rendered


@pytest.mark.asyncio
async def test_copy_scan_examples_generic_exception_returns_error_modal(monkeypatch, tmp_path):
    """[AC-NFR1101-01] Generic exception path returns '复制失败' modal."""
    req = MagicMock()
    monkeypatch.setattr(
        strategy_mod.strategy_loader, "get_user_scan_directory", lambda: str(tmp_path)
    )
    monkeypatch.setattr(
        strategy_mod.strategy_loader,
        "copy_examples_to_directory",
        MagicMock(side_effect=RuntimeError("copy boom")),
    )
    out = await copy_scan_examples(req)
    rendered = strategy_mod.to_xml(out) if not isinstance(out, str) else out
    assert "复制失败" in rendered


# ---------------------------------------------------------------------------
# backtest_ws: missing portfolio_id + WebSocketDisconnect path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backtest_ws_closes_when_no_portfolio_id():
    """[AC-NFR1101-01] Missing portfolio_id closes the websocket and returns."""
    ws = MagicMock()
    ws.path_params = {}
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    await backtest_ws(ws)
    ws.accept.assert_awaited_once()
    ws.close.assert_awaited_once_with(code=1008)


@pytest.mark.asyncio
async def test_backtest_ws_returns_on_websocket_disconnect(monkeypatch):
    """[AC-NFR1101-01] WebSocketDisconnect exception during loop is caught and returns."""
    ws = MagicMock()
    ws.path_params = {"portfolio_id": "p1"}
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_text = AsyncMock(side_effect=WebSocketDisconnect())

    # _resolve_backtest_status returns running so loop continues until send_text raises.
    monkeypatch.setattr(
        strategy_mod, "_resolve_backtest_status", lambda pid: ("running", "")
    )
    monkeypatch.setattr(strategy_mod, "_build_date_axis", lambda pid: [])
    monkeypatch.setattr(strategy_mod, "_build_metrics_payload", lambda pid: {})
    monkeypatch.setattr(strategy_mod, "_build_series_payload", lambda pid, da: {})
    monkeypatch.setattr(strategy_mod, "_build_trade_rows", lambda *a, **k: [])
    monkeypatch.setattr(strategy_mod, "_build_daily_summary", lambda pid: {})
    monkeypatch.setattr(strategy_mod, "_build_daily_positions", lambda pid: {})
    monkeypatch.setattr(strategy_mod, "_build_log_rows", lambda *a, **k: [])
    monkeypatch.setattr(strategy_mod, "_build_log_meta", lambda pid: {})
    await backtest_ws(ws)
    ws.accept.assert_awaited_once()
