"""[B09] strategy_runtime route-style coverage: start/stop/block/unblock round-trips.

Targeted lines in ``quantide/service/strategy_runtime.py``:
- ``start_strategy_runtime`` happy path + blocked-account path (L363-L399)
- ``stop_strategy_runtime`` happy path + missing-runtime error (L349-L361)
- ``block_account`` / ``unblock_account`` round-trip (L401-L456)
- ``block_strategy`` / ``unblock_strategy`` round-trip (L458-L508)
"""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from quantide.service.strategy_runtime import (
    StrategyRuntime,
    StrategyRuntimeManager,
    strategy_runtime_manager,
)


def _clear_manager() -> None:
    """Reset singleton state between tests to avoid cross-test bleed."""
    for attr in (
        "_account_runtimes",
        "_strategy_runtimes",
        "_backtest_runtimes",
        "_backtest_history",
        "_runtime_specs",
        "_blocked_accounts",
        "_blocked_strategies",
        "_risk_events",
    ):
        getattr(strategy_runtime_manager, attr).clear()
    strategy_runtime_manager._runtime = None
    strategy_runtime_manager._registry = None
    strategy_runtime_manager._adapters = None
    strategy_runtime_manager._market_data = None
    strategy_runtime_manager._gateway_broker = None


@pytest.fixture(autouse=True)
def _isolate_runtime_manager(monkeypatch, tmp_path: Path):
    """Redirect state file to tmp_path and reset all in-memory dicts."""
    monkeypatch.setattr(
        strategy_runtime_manager,
        "_state_file",
        lambda: tmp_path / "strategy_runtimes_b09.json",
    )
    _clear_manager()
    yield
    _clear_manager()


def _make_runtime(status: str = "running", runtime_id: str = "paper:p1:s1") -> StrategyRuntime:
    """Build a minimal StrategyRuntime instance for testing."""
    return StrategyRuntime(
        runtime_id=runtime_id,
        mode="paper",
        strategy_name="Demo",
        strategy_id="sid-1",
        portfolio_id="p1",
        account_kind="sim",
        status=status,
        config={},
        broker=SimpleNamespace(),
        stop_event=threading.Event(),
    )


def _install_fake_thread(monkeypatch) -> list[str]:
    """Replace threading.Thread with a no-op recorder; returns the call log."""
    started: list[str] = []

    class _FakeThread:
        def __init__(self, target, args, daemon, name):
            self.target = target
            self.args = args
            self.daemon = daemon
            self.name = name

        def start(self):
            started.append(self.name)

    monkeypatch.setattr(threading, "Thread", _FakeThread)
    return started


# ---------------------------------------------------------------------------
# start_strategy_runtime
# ---------------------------------------------------------------------------


def test_start_strategy_runtime_happy_path_starts_runtime(monkeypatch):
    """start_strategy_runtime marks spec running and invokes _start_from_spec.

    Covers L363-L399 happy path (no block, spec exists, account unblocked).
    """
    started = _install_fake_thread(monkeypatch)
    strategy_runtime_manager._registry = SimpleNamespace(
        get=lambda kind, pid: SimpleNamespace(),
    )
    strategy_runtime_manager._market_data = SimpleNamespace()
    strategy_runtime_manager._runtime_specs["paper:p1:s1"] = {
        "runtime_id": "paper:p1:s1",
        "mode": "paper",
        "strategy_name": "Demo",
        "strategy_id": "sid-1",
        "portfolio_id": "p1",
        "source_backtest_portfolio_id": "bt-1",
        "account_kind": "sim",
        "status": "stopped",
        "config": {},
        "symbols": ["000001.SZ"],
        "principal": 10000.0,
        "interval": "1m",
    }
    runtime = strategy_runtime_manager.start_strategy_runtime("paper:p1:s1")
    assert runtime.status == "running"
    assert runtime.runtime_id == "paper:p1:s1"
    assert started, "strategy thread should be started"
    assert strategy_runtime_manager._runtime_specs["paper:p1:s1"]["status"] == "running"


def test_start_strategy_runtime_blocked_account_raises(monkeypatch):
    """When the account is blocked, start_strategy_runtime records a risk
    event and raises RuntimeError. Covers L382-L396."""
    strategy_runtime_manager._runtime_specs["paper:p1:s2"] = {
        "runtime_id": "paper:p1:s2",
        "mode": "paper",
        "strategy_name": "Demo",
        "strategy_id": "sid-2",
        "portfolio_id": "p1",
        "account_kind": "sim",
        "status": "stopped",
        "config": {},
        "interval": "1m",
    }
    strategy_runtime_manager._blocked_accounts["paper:p1"] = {"reason": "drawdown"}
    with pytest.raises(RuntimeError, match="账户已被封锁"):
        strategy_runtime_manager.start_strategy_runtime("paper:p1:s2")
    # A critical risk event should have been recorded for the account scope.
    account_events = [
        ev
        for ev in strategy_runtime_manager._risk_events
        if ev.get("scope") == "account" and ev.get("blocked")
    ]
    assert account_events, "blocked-account risk event should be recorded"


def test_start_strategy_runtime_returns_current_when_already_running():
    """When a runtime exists and is running, return it immediately. Covers L366-L367."""
    rt = _make_runtime(status="running", runtime_id="paper:p1:s3")
    strategy_runtime_manager._strategy_runtimes[rt.runtime_id] = rt
    returned = strategy_runtime_manager.start_strategy_runtime(rt.runtime_id)
    assert returned is rt


# ---------------------------------------------------------------------------
# stop_strategy_runtime
# ---------------------------------------------------------------------------


def test_stop_strategy_runtime_marks_stopping_and_persists():
    """stop_strategy_runtime sets stop_event, status=stopping, spec=stopped.

    Covers L349-L361 happy path.
    """
    rt = _make_runtime(status="running", runtime_id="paper:p1:stop")
    strategy_runtime_manager._strategy_runtimes[rt.runtime_id] = rt
    strategy_runtime_manager._runtime_specs[rt.runtime_id] = {
        "runtime_id": rt.runtime_id,
        "status": "running",
        "config": {},
    }
    strategy_runtime_manager.stop_strategy_runtime(rt.runtime_id)
    assert rt.status == "stopping"
    assert rt.stop_event.is_set()
    assert strategy_runtime_manager._runtime_specs[rt.runtime_id]["status"] == "stopped"


def test_stop_strategy_runtime_raises_for_missing_runtime():
    """Missing runtime_id raises RuntimeError. Covers L352-L353 error path."""
    with pytest.raises(RuntimeError, match="策略运行时不存在"):
        strategy_runtime_manager.stop_strategy_runtime("ghost-runtime-id")


# ---------------------------------------------------------------------------
# block_account / unblock_account round-trip
# ---------------------------------------------------------------------------


def test_block_and_unblock_account_round_trip_with_strategy_runtime():
    """block_account marks related strategy runtime blocked + records spec
    block_scope; unblock_account restores runtime to stopped and clears scope.

    Covers L401-L456 including spec block_scope/account branch (L416-L418,
    L442-L447) that the existing b06 suite did not exercise with a spec.
    """
    rt = _make_runtime(status="running", runtime_id="paper:p-rt:block-acct")
    rt.mode = "paper"
    rt.portfolio_id = "p-rt"
    rt.strategy_id = "sid-block-acct"
    strategy_runtime_manager._strategy_runtimes[rt.runtime_id] = rt
    strategy_runtime_manager._runtime_specs[rt.runtime_id] = {
        "runtime_id": rt.runtime_id,
        "mode": "paper",
        "portfolio_id": "p-rt",
        "status": "running",
        "config": {},
    }
    # Block the account.
    strategy_runtime_manager.block_account("paper:p-rt", reason="drawdown")
    assert rt.status == "blocked"
    assert rt.error == "drawdown"
    spec = strategy_runtime_manager._runtime_specs[rt.runtime_id]
    assert spec["status"] == "blocked"
    assert spec["block_scope"] == "account"
    assert spec["block_reason"] == "drawdown"
    assert "paper:p-rt" in strategy_runtime_manager._blocked_accounts
    # Unblock the account.
    strategy_runtime_manager.unblock_account("paper:p-rt")
    assert "paper:p-rt" not in strategy_runtime_manager._blocked_accounts
    assert rt.status == "stopped"
    spec = strategy_runtime_manager._runtime_specs[rt.runtime_id]
    assert spec["status"] == "stopped"
    assert "block_scope" not in spec
    assert "block_reason" not in spec


# ---------------------------------------------------------------------------
# block_strategy / unblock_strategy round-trip
# ---------------------------------------------------------------------------


def test_block_and_unblock_strategy_round_trip_with_spec():
    """block_strategy marks spec blocked with block_scope=strategy;
    unblock_strategy restores spec to stopped and clears block metadata.

    Covers L458-L508 including spec block_scope=strategy branch (L469-L473,
    L495-L499) with persisted spec data.
    """
    runtime_id = "paper:p-sb:block-strat"
    rt = _make_runtime(status="running", runtime_id=runtime_id)
    strategy_runtime_manager._strategy_runtimes[runtime_id] = rt
    strategy_runtime_manager._runtime_specs[runtime_id] = {
        "runtime_id": runtime_id,
        "mode": "paper",
        "portfolio_id": "p-sb",
        "status": "running",
        "config": {},
    }
    # Block the strategy.
    strategy_runtime_manager.block_strategy(runtime_id, reason="risk limit")
    assert rt.status == "blocked"
    assert rt.error == "risk limit"
    spec = strategy_runtime_manager._runtime_specs[runtime_id]
    assert spec["status"] == "blocked"
    assert spec["block_scope"] == "strategy"
    assert spec["block_reason"] == "risk limit"
    assert runtime_id in strategy_runtime_manager._blocked_strategies
    # Unblock the strategy.
    strategy_runtime_manager.unblock_strategy(runtime_id)
    assert runtime_id not in strategy_runtime_manager._blocked_strategies
    assert rt.status == "stopped"
    spec = strategy_runtime_manager._runtime_specs[runtime_id]
    assert spec["status"] == "stopped"
    assert "block_scope" not in spec
    assert "block_reason" not in spec
