"""B10-strategy-runtime: Tests for missing lines in quantide/service/strategy_runtime.py.

Targets specific missing branches:
- _resolve_backtest_run: portfolio without strategy name (682), cache-load path (690-694)
- _start_from_spec: registry None (1055), gateway broker path (1060), broker missing (1064)
- _apply_live_broker_config: load_from_cache exception (814-815), setter not callable (821)
- list_runtime_rows: backtest row branch (547)
- get_active_backtest_deployment: status-not-active continue (604, 606)
- backtest_deployment_modes: non-paper/live continue (586)
- unblock_account: spec account_key mismatch continue (443)
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

import quantide.service.strategy_runtime as sr_mod
from quantide.service.strategy_runtime import (
    BacktestRun,
    StrategyRuntime,
    StrategyRuntimeManager,
)


def _make_manager() -> StrategyRuntimeManager:
    """Build a StrategyRuntimeManager without running __init__ side effects."""
    mgr = StrategyRuntimeManager.__new__(StrategyRuntimeManager)
    mgr._lock = threading.RLock()
    mgr._account_runtimes = {}
    mgr._strategy_runtimes = {}
    mgr._backtest_runtimes = {}
    mgr._backtest_history = {}
    mgr._runtime_specs = {}
    mgr._blocked_accounts = {}
    mgr._blocked_strategies = {}
    mgr._risk_events = []
    mgr._runtime = None
    mgr._registry = None
    mgr._adapters = None
    mgr._market_data = None
    mgr._gateway_broker = None
    return mgr


# ---------------------------------------------------------------------------
# _resolve_backtest_run
# ---------------------------------------------------------------------------


def test_resolve_backtest_run_raises_when_portfolio_has_no_name():
    """[AC-NFR1101-01] Portfolio without name raises "无法识别回测策略名" (line 682)."""
    mgr = _make_manager()
    portfolio = MagicMock()
    portfolio.name = ""
    portfolio.start = "2024-01-01"
    portfolio.end = "2024-06-01"
    with patch.object(sr_mod.db, "get_portfolio", return_value=portfolio):
        with pytest.raises(RuntimeError, match="无法识别回测策略名"):
            mgr._resolve_backtest_run("pf-no-name")


def test_resolve_backtest_run_uses_strategy_loader_when_no_spec():
    """[AC-NFR1101-01] Without persisted spec, loads PARAMS from strategy cache (690-694)."""
    mgr = _make_manager()
    portfolio = MagicMock()
    portfolio.name = "MyStrategy"
    portfolio.start = "2024-01-01"
    portfolio.end = "2024-06-01"

    strategy_cls = MagicMock()
    strategy_cls.PARAMS = {"cheat_on_close": True}

    with patch.object(sr_mod.db, "get_portfolio", return_value=portfolio), \
         patch.object(sr_mod.strategy_loader, "load_from_cache", return_value={"MyStrategy": strategy_cls}), \
         patch.object(sr_mod, "get_cheat_on_close_time", return_value="14:55"), \
         patch.object(sr_mod, "get_backtest_log_path") as mock_log_path:
        mock_log_path.return_value.exists.return_value = False
        mock_log_path.return_value.__str__ = lambda self: "/tmp/log"
        run = mgr._resolve_backtest_run("pf-x")
    assert run.strategy_name == "MyStrategy"
    assert run.cheat_on_close is True
    assert run.cheat_on_close_time == "14:55"
    assert run.config == {"cheat_on_close": True}


# ---------------------------------------------------------------------------
# _start_from_spec
# ---------------------------------------------------------------------------


def test_start_from_spec_raises_when_registry_none():
    """[AC-NFR1101-01] _start_from_spec raises when registry not initialized (line 1055)."""
    mgr = _make_manager()
    mgr._registry = None
    with pytest.raises(RuntimeError, match="registry 未初始化"):
        mgr._start_from_spec({"mode": "live", "portfolio_id": "p1"})


def test_start_from_spec_raises_when_broker_missing():
    """[AC-NFR1101-01] Raises "账户不存在" when registry has no broker (line 1064)."""
    mgr = _make_manager()
    registry = MagicMock()
    registry.get.return_value = None
    mgr._registry = registry
    mgr._gateway_broker = None
    spec = {"mode": "paper", "portfolio_id": "p1", "account_kind": "simulation"}
    with pytest.raises(RuntimeError, match="账户不存在"):
        mgr._start_from_spec(spec)


def test_start_from_spec_uses_gateway_broker_for_gateway_kind():
    """[AC-NFR1101-01] When account_kind=="gateway", uses _gateway_broker (line 1060)."""
    mgr = _make_manager()
    gateway_broker = MagicMock()
    mgr._gateway_broker = gateway_broker
    registry = MagicMock()
    mgr._registry = registry
    spec = {
        "mode": "live",
        "portfolio_id": "gw",
        "account_kind": "gateway",
        "strategy_name": "S",
        "config": {},
        "interval": "1m",
        "principal": 0.0,
        "runtime_id": "live:gw:s1",
        "strategy_id": "s1",
        "source_backtest_portfolio_id": "",
    }
    with patch.object(mgr, "_start_strategy_runtime", return_value="started") as mock_start:
        result = mgr._start_from_spec(spec)
    assert result == "started"
    call_kwargs = mock_start.call_args.kwargs
    assert call_kwargs["broker"] is gateway_broker
    # registry.get should NOT have been called since gateway broker was set
    registry.get.assert_not_called()


# ---------------------------------------------------------------------------
# _apply_live_broker_config
# ---------------------------------------------------------------------------


def test_apply_live_broker_config_returns_when_setter_not_callable():
    """[AC-NFR1101-01] Returns early when broker has no set_strategy_runtime_config (line 821)."""
    mgr = _make_manager()
    runtime = MagicMock()
    runtime.config = {"cheat_on_close": True}
    runtime.broker = MagicMock(spec=[])  # no set_strategy_runtime_config attribute
    # Should not raise; returns None
    mgr._apply_live_broker_config(runtime)


def test_apply_live_broker_config_handles_strategy_loader_exception():
    """[AC-NFR1101-01] load_from_cache exception sets strategy_cls=None (814-815)."""
    mgr = _make_manager()
    runtime = MagicMock()
    runtime.config = {}  # no cheat_on_close key -> triggers load_from_cache path
    runtime.strategy_name = "UnknownStrategy"
    broker = MagicMock()
    runtime.broker = broker
    with patch.object(sr_mod.strategy_loader, "load_from_cache", side_effect=RuntimeError("cache error")):
        mgr._apply_live_broker_config(runtime)
    # setter should have been called with cheat_on_close=False (default)
    broker.set_strategy_runtime_config.assert_called_once()
    call_kwargs = broker.set_strategy_runtime_config.call_args.kwargs
    assert call_kwargs["cheat_on_close"] is False


# ---------------------------------------------------------------------------
# list_runtime_rows: backtest row branch (line 547)
# ---------------------------------------------------------------------------


def test_list_runtime_rows_includes_backtest_rows():
    """[AC-NFR1101-01] list_runtime_rows appends backtest rows (line 547)."""
    mgr = _make_manager()
    backtest_run = BacktestRun(
        runtime_id="backtest:pf1",
        portfolio_id="pf1",
        strategy_name="MyStrategy",
        config={},
        interval="1m",
        start_date="2024-01-01",
        end_date="2024-06-01",
        initial_cash=100000,
        status="finished",
    )
    mgr._backtest_runtimes["pf1"] = backtest_run
    rows = mgr.list_runtime_rows()
    backtest_rows = [r for r in rows if r["mode"] == "backtest"]
    assert len(backtest_rows) == 1
    assert backtest_rows[0]["portfolio_id"] == "pf1"
    assert backtest_rows[0]["strategy_name"] == "MyStrategy"


# ---------------------------------------------------------------------------
# get_active_backtest_deployment: continue on non-active status (604, 606)
# ---------------------------------------------------------------------------


def test_get_active_backtest_deployment_skips_non_active_status():
    """[AC-NFR1101-01] Skips runtimes with wrong mode and non-active status (604, 606)."""
    mgr = _make_manager()
    # runtime with wrong mode (should be skipped via continue on line 604)
    wrong_mode = StrategyRuntime(
        runtime_id="paper:p1:s1",
        mode="paper",
        strategy_name="S",
        strategy_id="s1",
        portfolio_id="p1",
        account_kind="sim",
        status="running",
        config={},
        source_backtest_portfolio_id="pf-backtest",
    )
    # runtime with correct mode but non-active status (line 606 continue)
    stopped_live = StrategyRuntime(
        runtime_id="live:p2:s2",
        mode="live",
        strategy_name="S",
        strategy_id="s2",
        portfolio_id="p2",
        account_kind="gateway",
        status="stopped",
        config={},
        source_backtest_portfolio_id="pf-backtest",
    )
    # runtime with correct mode and active status (returned)
    active_live = StrategyRuntime(
        runtime_id="live:p3:s3",
        mode="live",
        strategy_name="S",
        strategy_id="s3",
        portfolio_id="p3",
        account_kind="gateway",
        status="running",
        config={},
        source_backtest_portfolio_id="pf-backtest",
    )
    mgr._strategy_runtimes = {
        wrong_mode.runtime_id: wrong_mode,
        stopped_live.runtime_id: stopped_live,
        active_live.runtime_id: active_live,
    }
    result = mgr.get_active_backtest_deployment("pf-backtest", "live")
    assert result is active_live
