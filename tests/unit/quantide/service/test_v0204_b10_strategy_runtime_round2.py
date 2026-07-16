"""B10-strategy-runtime round 2: Additional missing-line tests for strategy_runtime.py.

Targets lines NOT covered by test_v0204_b10_strategy_runtime.py:
- deploy_to_live: gateway broker present -> _start_strategy_runtime call (336)
- _strategy_loop: strategy_cls is None -> failed status (832-835)
- _strategy_loop: exception -> failed/error recorded (855-856), finally spec update (874-875),
  on_stop exception swallow (878-879)
- _build_quotes: empty symbols fallback (884), snapshot iteration (887-892), result (900)
- _load_specs: exception -> reset to empty (955-959)
- _restore_persisted_runtimes: account block reason (974), start success (993-995),
  start failure (1003-1007)
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

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
# deploy_to_live: gateway broker present -> _start_strategy_runtime (336)
# ---------------------------------------------------------------------------


def test_deploy_to_live_calls_start_strategy_runtime_when_gateway_broker_present():
    """[AC-NFR1101-01] deploy_to_live reaches _start_strategy_runtime (line 336)."""
    mgr = _make_manager()
    mgr._gateway_broker = MagicMock(name="gateway_broker")
    run = BacktestRun(
        runtime_id="backtest:pf1",
        portfolio_id="pf1",
        strategy_name="MyStrategy",
        config={"symbol": "000001.SZ"},
        interval="1m",
        start_date="2024-01-01",
        end_date="2024-06-01",
        initial_cash=100000,
        status="finished",
    )
    with patch.object(mgr, "_resolve_backtest_run", return_value=run), \
         patch.object(mgr, "get_active_backtest_deployment", return_value=None), \
         patch.object(mgr, "_start_strategy_runtime", return_value="started") as mock_start:
        result = mgr.deploy_to_live("pf1", "acc1", MagicMock(), MagicMock())
    assert result == "started"
    call_kwargs = mock_start.call_args.kwargs
    assert call_kwargs["mode"] == "live"
    assert call_kwargs["broker"] is mgr._gateway_broker
    assert call_kwargs["account_kind"] == "gateway"
    assert call_kwargs["portfolio_id"] == "gateway"


# ---------------------------------------------------------------------------
# _strategy_loop: strategy_cls is None -> failed status (832-835)
# ---------------------------------------------------------------------------


def test_strategy_loop_marks_failed_when_strategy_cls_is_none():
    """[AC-NFR1101-01] _strategy_loop sets failed status when strategy_cls is None (832-835)."""
    mgr = _make_manager()
    runtime = StrategyRuntime(
        runtime_id="live:p1:s1",
        mode="live",
        strategy_name="NonexistentStrategy",
        strategy_id="s1",
        portfolio_id="p1",
        account_kind="gateway",
        status="running",
        config={},
        stop_event=threading.Event(),
    )
    with patch.object(sr_mod.strategy_loader, "load_from_cache", return_value={}):
        asyncio.run(mgr._strategy_loop(runtime, "1m", None))
    assert runtime.status == "failed"
    assert "策略不存在" in runtime.error


# ---------------------------------------------------------------------------
# _strategy_loop: exception -> failed/error (855-856), finally spec update (874-875),
# on_stop exception swallow (878-879)
# ---------------------------------------------------------------------------


def test_strategy_loop_handles_exception_and_updates_spec():
    """[AC-NFR1101-01] _strategy_loop handles exception (855-856), updates spec (874-875), swallows on_stop error (878-879)."""
    mgr = _make_manager()
    stop_event = threading.Event()
    stop_event.set()  # so the loop exits after first iteration

    runtime = StrategyRuntime(
        runtime_id="live:p2:s2",
        mode="live",
        strategy_name="MyStrategy",
        strategy_id="s2",
        portfolio_id="p2",
        account_kind="gateway",
        status="running",
        config={},
        stop_event=stop_event,
    )
    # Register a spec so the finally branch can update it (874-875)
    mgr._runtime_specs[runtime.runtime_id] = {
        "runtime_id": runtime.runtime_id,
        "status": "running",
    }

    strategy_cls = MagicMock()
    strategy_instance = MagicMock()
    strategy_cls.return_value = strategy_instance
    # init returns awaitable None (must be async-compatible)
    strategy_instance.init = AsyncMock(return_value=None)
    # on_start raises to trigger the exception branch (855-856)
    strategy_instance.on_start = AsyncMock(side_effect=RuntimeError("boom"))
    # on_stop also raises to trigger the swallow branch (878-879)
    strategy_instance.on_stop = AsyncMock(side_effect=RuntimeError("on_stop boom"))

    with patch.object(sr_mod.strategy_loader, "load_from_cache", return_value={"MyStrategy": strategy_cls}), \
         patch.object(mgr, "_save_specs") as mock_save:
        asyncio.run(mgr._strategy_loop(runtime, "1m", None))

    assert runtime.status == "failed"
    assert "boom" in runtime.error
    # spec status updated in finally (874-875)
    assert mgr._runtime_specs[runtime.runtime_id]["status"] == "failed"
    # on_stop was called (its exception was swallowed)
    strategy_instance.on_stop.assert_called_once()


# ---------------------------------------------------------------------------
# _build_quotes: empty symbols fallback (884), snapshot iteration (887-892), result (900)
# ---------------------------------------------------------------------------


def test_build_quotes_uses_fallback_symbol_when_empty():
    """[AC-NFR1101-01] _build_quotes falls back to ['000001.SZ'] when symbols empty (line 884)."""
    mgr = _make_manager()
    market_data = MagicMock()
    snap = MagicMock()
    snap.price = 10.0
    snap.open = 9.5
    snap.high = 10.5
    snap.low = 9.0
    snap.volume = 1000
    snap.amount = 10000.0
    market_data.snapshot.return_value = {"000001.SZ": snap}
    result = mgr._build_quotes([], market_data)
    assert "000001.SZ" in result
    assert result["000001.SZ"]["lastPrice"] == 10.0
    market_data.snapshot.assert_called_once_with(["000001.SZ"])


def test_build_quotes_skips_missing_snap_and_returns_result():
    """[AC-NFR1101-01] _build_quotes skips None snap (890-891) and returns dict (900)."""
    mgr = _make_manager()
    market_data = MagicMock()
    snap = MagicMock()
    snap.price = 20.0
    snap.open = 19.0
    snap.high = 21.0
    snap.low = 18.0
    snap.volume = 500
    snap.amount = 10000.0
    # A only returns a snap, B returns None -> B skipped
    market_data.snapshot.return_value = {"A": snap, "B": None}
    result = mgr._build_quotes(["A", "B"], market_data)
    assert set(result.keys()) == {"A"}
    assert result["A"]["lastPrice"] == 20.0


def test_build_quotes_returns_empty_when_market_data_none():
    """[AC-NFR1101-01] _build_quotes returns empty dict when market_data is None (line 886)."""
    mgr = _make_manager()
    result = mgr._build_quotes(["A"], None)
    assert result == {}


# ---------------------------------------------------------------------------
# _load_specs: exception -> reset to empty (955-959)
# ---------------------------------------------------------------------------


def test_load_specs_resets_to_empty_on_exception():
    """[AC-NFR1101-01] _load_specs resets state on JSON parse exception (955-959)."""
    mgr = _make_manager()
    # Pre-populate with stale data to confirm reset clears it
    mgr._runtime_specs = {"old": {"status": "running"}}
    mgr._blocked_accounts = {"acc": {"reason": "x"}}
    mgr._blocked_strategies = {"rt": {"reason": "y"}}
    mgr._risk_events = [{"event": "stale"}]

    state_file = MagicMock()
    state_file.exists.return_value = True
    state_file.read_text.return_value = "{not valid json"
    with patch.object(sr_mod, "get_strategy_runtime_state_path", return_value=state_file):
        mgr._load_specs()
    assert mgr._runtime_specs == {}
    assert mgr._blocked_accounts == {}
    assert mgr._blocked_strategies == {}
    assert mgr._risk_events == []


# ---------------------------------------------------------------------------
# _restore_persisted_runtimes: account block reason (974), start success (993-995),
# start failure (1003-1007)
# ---------------------------------------------------------------------------


def test_restore_persisted_runtimes_records_account_block_reason():
    """[AC-NFR1101-01] _restore_persisted_runtimes reads account_block reason (line 974)."""
    mgr = _make_manager()
    runtime_id = "live:p1:s1"
    account_key = "live:p1"
    mgr._runtime_specs = {
        runtime_id: {
            "runtime_id": runtime_id,
            "mode": "live",
            "portfolio_id": "p1",
            "status": "running",
            "account_kind": "gateway",
        }
    }
    mgr._blocked_accounts = {
        account_key: {"target_id": account_key, "reason": "manual block"},
    }
    with patch.object(mgr, "_save_specs") as mock_save, \
         patch.object(mgr, "_record_risk_event") as mock_record:
        mgr._restore_persisted_runtimes()
    # spec should be marked blocked with account scope
    assert mgr._runtime_specs[runtime_id]["status"] == "blocked"
    assert mgr._runtime_specs[runtime_id]["block_scope"] == "account"
    assert mgr._runtime_specs[runtime_id]["block_reason"] == "manual block"
    mock_save.assert_called()
    # risk event recorded with account scope
    account_events = [c for c in mock_record.call_args_list if c.kwargs.get("scope") == "account"]
    assert len(account_events) >= 1


def test_restore_persisted_runtimes_starts_unblocked_spec():
    """[AC-NFR1101-01] _restore_persisted_runtimes starts an unblocked spec (993-995)."""
    mgr = _make_manager()
    runtime_id = "live:p1:s1"
    mgr._runtime_specs = {
        runtime_id: {
            "runtime_id": runtime_id,
            "mode": "live",
            "portfolio_id": "p1",
            "status": "running",
            "account_kind": "gateway",
        }
    }
    # No blocks -> should call _start_from_spec
    with patch.object(mgr, "_start_from_spec") as mock_start, \
         patch.object(mgr, "_record_risk_event") as mock_record:
        mgr._restore_persisted_runtimes()
    mock_start.assert_called_once()
    # success risk event recorded
    success_events = [
        c for c in mock_record.call_args_list
        if c.kwargs.get("title") == "重启恢复完成"
    ]
    assert len(success_events) == 1


def test_restore_persisted_runtimes_records_start_failure():
    """[AC-NFR1101-01] _restore_persisted_runtimes records failure when _start_from_spec raises (1003-1007)."""
    mgr = _make_manager()
    runtime_id = "live:p1:s1"
    mgr._runtime_specs = {
        runtime_id: {
            "runtime_id": runtime_id,
            "mode": "live",
            "portfolio_id": "p1",
            "status": "running",
            "account_kind": "gateway",
        }
    }
    with patch.object(mgr, "_start_from_spec", side_effect=RuntimeError("start failed")), \
         patch.object(mgr, "_save_specs") as mock_save, \
         patch.object(mgr, "_record_risk_event") as mock_record:
        mgr._restore_persisted_runtimes()
    assert mgr._runtime_specs[runtime_id]["status"] == "failed"
    assert mgr._runtime_specs[runtime_id]["error"] == "start failed"
    # failure risk event recorded
    failure_events = [
        c for c in mock_record.call_args_list
        if c.kwargs.get("title") == "重启恢复失败"
    ]
    assert len(failure_events) == 1
