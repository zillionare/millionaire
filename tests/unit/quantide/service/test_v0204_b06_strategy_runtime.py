"""B06-svc-1: Additional tests for quantide/service/strategy_runtime.py.

Target: raise coverage from 59% to >=80% by exercising
StrategyRuntimeManager methods that are not yet covered by
``tests/unit/quantide/service/test_strategy_runtime.py``.

Conventions:
- Each test sets up minimal side-effect-free state (no live broker).
- Where the production method depends on the runtime context, we
  inject a SimpleNamespace stub and skip code paths that require a
  real broker port (those paths are covered by M-E2E tests).
- All tests against the singleton ``strategy_runtime_manager`` run
  against an autouse-isolated fixture and clean up after themselves.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from quantide.service.strategy_runtime import (
    BacktestRun,
    StrategyBrokerProxy,
    StrategyRuntime,
    strategy_runtime_manager,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clear_manager():
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
    monkeypatch.setattr(
        strategy_runtime_manager,
        "_state_file",
        lambda: tmp_path / "strategy_runtimes.json",
    )
    _clear_manager()
    yield
    _clear_manager()


def _make_backtest(portfolio_id: str = "bt-1", status: str = "finished") -> BacktestRun:
    return BacktestRun(
        runtime_id=f"backtest:{portfolio_id}",
        portfolio_id=portfolio_id,
        strategy_name="Demo",
        config={},
        interval="1d",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_cash=100000.0,
        status=status,
        updated_at=datetime.datetime(2024, 1, 31, 10, 0, 0),
    )


# ---------------------------------------------------------------------------
# Existing methods extended coverage
# ---------------------------------------------------------------------------


def test_create_backtest_runtime_records_saved_run():
    strategy_runtime_manager.create_backtest_runtime(
        portfolio_id="bt-new",
        strategy_name="SavedStrategy",
        config={"cheat_on_close": False},
        interval="1d",
        start_date="2024-02-01",
        end_date="2024-02-28",
        initial_cash=50_000,
    )
    run = strategy_runtime_manager.get_backtest_run("bt-new")
    assert run is not None
    assert run.strategy_name == "SavedStrategy"
    assert run.interval == "1d"
    assert run.initial_cash == 50_000
    assert run.status == "running"


def test_complete_backtest_runtime_handles_error_message():
    strategy_runtime_manager.create_backtest_runtime(
        portfolio_id="bt-err",
        strategy_name="Demo",
        config={},
        interval="1d",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_cash=1.0,
    )
    strategy_runtime_manager.complete_backtest_runtime("bt-err", error="boom")
    run = strategy_runtime_manager.get_backtest_run("bt-err")
    assert run is not None
    assert run.status == "failed"
    assert run.error == "boom"


def test_complete_backtest_runtime_for_missing_run_is_noop():
    # Should not raise.
    strategy_runtime_manager.complete_backtest_runtime("does-not-exist")
    assert strategy_runtime_manager.get_backtest_run("does-not-exist") is None


def test_get_backtest_run_or_resolve_falls_back_when_in_memory_missing(
    monkeypatch, db
):
    """When in-memory has no entry, falls back to _resolve_backtest_run path
    which loads from db. We register no portfolio, so the helper returns None."""
    result = strategy_runtime_manager.get_backtest_run_or_resolve("missing-portfolio")
    assert result is None


def test_get_backtest_run_or_resolve_returns_in_memory_when_present():
    """When a run exists in _backtest_history, return it directly."""
    strategy_runtime_manager._backtest_history["bt-found"] = _make_backtest("bt-found")
    run = strategy_runtime_manager.get_backtest_run_or_resolve("bt-found")
    assert run is not None
    assert run.portfolio_id == "bt-found"


def test_remove_backtest_run_drops_missing_in_memory_entry():
    # Removing a non-existent backtest run should not raise.
    strategy_runtime_manager.remove_backtest_run("ghost")
    assert strategy_runtime_manager.get_backtest_run("ghost") is None


# ---------------------------------------------------------------------------
# Risk-event helpers
# ---------------------------------------------------------------------------


def test_risk_summary_empty():
    summary = strategy_runtime_manager.risk_summary()
    assert summary == {
        "blocked_accounts": 0,
        "blocked_strategies": 0,
        "open_events": 0,
        "event_count": 0,
    }


# ---------------------------------------------------------------------------
# StrategyBrokerProxy — covers L70, L73, L83, L93, L103, L123, L143
# ---------------------------------------------------------------------------


class _AsyncRecorder:
    """Simple broker double that records all forwarded calls."""

    def __init__(self):
        self.calls = []

    async def _record(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, "method": kwargs.get("_method")}

    async def buy(self, **kw):
        kw["_method"] = "buy"
        return await self._record(**kw)

    async def sell(self, **kw):
        kw["_method"] = "sell"
        return await self._record(**kw)

    async def buy_percent(self, **kw):
        kw["_method"] = "buy_percent"
        return await self._record(**kw)

    async def sell_percent(self, **kw):
        kw["_method"] = "sell_percent"
        return await self._record(**kw)

    async def buy_amount(self, **kw):
        kw["_method"] = "buy_amount"
        return await self._record(**kw)

    async def sell_amount(self, **kw):
        kw["_method"] = "sell_amount"
        return await self._record(**kw)

    async def cancel(self, **kw):
        kw["_method"] = "cancel"
        return await self._record(**kw)

    async def cancel_all(self, **kw):
        kw["_method"] = "cancel_all"
        return await self._record(**kw)


@pytest.mark.asyncio
async def test_strategy_broker_proxy_buy_forwards_kwargs():
    broker = _AsyncRecorder()
    proxy = StrategyBrokerProxy(broker, "sid-1")
    await proxy.buy("000001.SZ", 100, price=10.0)
    assert broker.calls[0]["_method"] == "buy"
    assert broker.calls[0]["strategy_id"] == "sid-1"
    assert broker.calls[0]["asset"] == "000001.SZ"


@pytest.mark.asyncio
async def test_strategy_broker_proxy_sell_forwards_kwargs():
    broker = _AsyncRecorder()
    proxy = StrategyBrokerProxy(broker, "sid-sell")
    await proxy.sell("000002.SZ", 50, price=20.0)
    assert broker.calls[0]["_method"] == "sell"
    assert broker.calls[0]["shares"] == 50


@pytest.mark.asyncio
async def test_strategy_broker_proxy_buy_percent_forwards_kwargs():
    broker = _AsyncRecorder()
    proxy = StrategyBrokerProxy(broker, "sid-pct")
    await proxy.buy_percent("000003.SZ", 25.0)
    assert broker.calls[0]["_method"] == "buy_percent"
    assert broker.calls[0]["percent"] == 25.0


@pytest.mark.asyncio
async def test_strategy_broker_proxy_sell_percent_forwards_kwargs():
    broker = _AsyncRecorder()
    proxy = StrategyBrokerProxy(broker, "sid-sellpct")
    await proxy.sell_percent("000004.SZ", 75.0)
    assert broker.calls[0]["_method"] == "sell_percent"


@pytest.mark.asyncio
async def test_strategy_broker_proxy_sell_amount_forwards_kwargs():
    broker = _AsyncRecorder()
    proxy = StrategyBrokerProxy(broker, "sid-amt")
    await proxy.sell_amount("000005.SZ", 8000.0, price=12.0)
    assert broker.calls[0]["_method"] == "sell_amount"
    assert broker.calls[0]["amount"] == 8000.0


@pytest.mark.asyncio
async def test_strategy_broker_proxy_cancel_forwards_kwargs():
    broker = _AsyncRecorder()
    proxy = StrategyBrokerProxy(broker, "sid-can")
    await proxy.cancel(qt_oid="abc", order_id="oid-1")
    assert broker.calls[0]["_method"] == "cancel"
    assert broker.calls[0]["qt_oid"] == "abc"


@pytest.mark.asyncio
async def test_strategy_broker_proxy_cancel_all_forwards_kwargs():
    broker = _AsyncRecorder()
    proxy = StrategyBrokerProxy(broker, "sid-canall")
    await proxy.cancel_all()
    assert broker.calls[0]["_method"] == "cancel_all"


def test_strategy_broker_proxy_getattr_fallback():
    """__getattr__ delegates non-overridden attributes to the broker."""

    class _Broker:
        some_method = lambda self: "from-broker"  # noqa: E731

    proxy = StrategyBrokerProxy(_Broker(), "sid-x")
    assert proxy.some_method() == "from-broker"


# ---------------------------------------------------------------------------
# End StrategyBrokerProxy
# ---------------------------------------------------------------------------


def test_risk_summary_after_block_account_and_block_strategy():
    strategy_runtime_manager._blocked_accounts["paper:p1"] = {"reason": "x"}
    strategy_runtime_manager._blocked_strategies["live:s1"] = {"reason": "y"}
    strategy_runtime_manager._risk_events.append({"blocked": True})
    strategy_runtime_manager._risk_events.append({"blocked": False})
    summary = strategy_runtime_manager.risk_summary()
    assert summary["blocked_accounts"] == 1
    assert summary["blocked_strategies"] == 1
    assert summary["open_events"] == 1
    assert summary["event_count"] == 2


def test_list_risk_events_with_limit():
    for i in range(5):
        strategy_runtime_manager._risk_events.append({"i": i})
    listed = strategy_runtime_manager.list_risk_events(limit=3)
    assert len(listed) == 3
    assert [item["i"] for item in listed] == [0, 1, 2]


def test_list_risk_events_returns_independent_copies():
    strategy_runtime_manager._risk_events.append({"x": 1})
    listed = strategy_runtime_manager.list_risk_events()
    listed[0]["x"] = 999
    assert strategy_runtime_manager._risk_events[0]["x"] == 1


# ---------------------------------------------------------------------------
# Runtime summary / list
# ---------------------------------------------------------------------------


def test_runtime_summary_counts_statuses():
    strategy_runtime_manager._strategy_runtimes["s1"] = _make_runtime("running")
    strategy_runtime_manager._strategy_runtimes["s2"] = _make_runtime("idle")
    strategy_runtime_manager._strategy_runtimes["s3"] = _make_runtime("idle")
    summary = strategy_runtime_manager.runtime_summary()
    assert summary["total"] == 3
    assert summary["running"] == 1
    assert summary["idle"] == 2


def test_runtime_summary_handles_unknown_status_as_idle():
    strategy_runtime_manager._strategy_runtimes["sx"] = _make_runtime("weirdstatus")
    summary = strategy_runtime_manager.runtime_summary()
    assert summary["total"] == 1
    assert summary["idle"] == 1


def _make_runtime(status: str) -> StrategyRuntime:
    return StrategyRuntime(
        runtime_id=f"live:fake-{status}",
        mode="live",
        strategy_name="x",
        strategy_id="sid",
        portfolio_id=f"p-{status}",
        account_kind="sim",
        status=status,
        config={},
        broker=SimpleNamespace(),
        updated_at=datetime.datetime(2024, 1, 1),
    )


def test_list_runtime_rows_sorts_by_mode_then_portfolio():
    rt_b = _make_runtime("idle"); rt_b.portfolio_id = "p-b"; rt_b.runtime_id = "paper:p-b"
    rt_a = _make_runtime("idle"); rt_a.portfolio_id = "p-a"; rt_a.runtime_id = "paper:p-a"
    strategy_runtime_manager._account_runtimes["paper:p-b"] = rt_b
    strategy_runtime_manager._account_runtimes["paper:p-a"] = rt_a
    rows = strategy_runtime_manager.list_runtime_rows()
    assert len(rows) == 2
    assert rows[0]["portfolio_id"] == "p-a"
    assert rows[1]["portfolio_id"] == "p-b"


def test_backtest_deployment_modes_filters_by_source_portfolio():
    rt = _make_runtime("running")
    rt.source_backtest_portfolio_id = "bt-100"
    rt.mode = "paper"
    strategy_runtime_manager._strategy_runtimes["paper:bt-100"] = rt
    other = _make_runtime("running")
    other.source_backtest_portfolio_id = "bt-200"
    other.mode = "paper"
    other.runtime_id = "live:bt-200"
    strategy_runtime_manager._strategy_runtimes["live:bt-200"] = other

    modes = strategy_runtime_manager.backtest_deployment_modes("bt-100")
    assert "paper" in modes
    assert "live" not in modes


def test_backtest_deployment_modes_ignores_finished_runtimes():
    rt = _make_runtime("finished")
    rt.source_backtest_portfolio_id = "bt-300"
    rt.mode = "paper"
    rt.runtime_id = "paper:bt-300"
    strategy_runtime_manager._strategy_runtimes["paper:bt-300"] = rt
    assert strategy_runtime_manager.backtest_deployment_modes("bt-300") == {}


def test_get_active_backtest_deployment_returns_running_runtime():
    rt = _make_runtime("running")
    rt.source_backtest_portfolio_id = "bt-x"
    rt.mode = "paper"
    rt.runtime_id = "paper:bt-x"
    strategy_runtime_manager._strategy_runtimes["paper:bt-x"] = rt
    found = strategy_runtime_manager.get_active_backtest_deployment("bt-x", "paper")
    assert found is rt


def test_get_active_backtest_deployment_returns_none_for_missing_mode():
    rt = _make_runtime("running")
    rt.source_backtest_portfolio_id = "bt-y"
    rt.mode = "paper"
    rt.runtime_id = "paper:bt-y"
    strategy_runtime_manager._strategy_runtimes["paper:bt-y"] = rt
    assert strategy_runtime_manager.get_active_backtest_deployment("bt-y", "live") is None


# ---------------------------------------------------------------------------
# Block / unblock account & strategy
# ---------------------------------------------------------------------------


def test_block_and_unblock_account_round_trip():
    strategy_runtime_manager.block_account("paper:p1", reason="limit")
    assert "paper:p1" in strategy_runtime_manager._blocked_accounts
    strategy_runtime_manager.unblock_account("paper:p1")
    assert "paper:p1" not in strategy_runtime_manager._blocked_accounts


def test_block_strategy_records_blocked_event():
    strategy_runtime_manager.block_strategy("live:s1", reason="drawdown")
    strategy_runtime_manager.unblock_strategy("live:s1")
    # unblock removes from _blocked_strategies
    assert "live:s1" not in strategy_runtime_manager._blocked_strategies


def test_block_strategy_updates_runtime_status_when_present():
    rt = _make_runtime("running")
    rt.runtime_id = "live:rt-block-1"
    strategy_runtime_manager._strategy_runtimes[rt.runtime_id] = rt
    strategy_runtime_manager._runtime_specs[rt.runtime_id] = {"runtime_id": rt.runtime_id}
    strategy_runtime_manager.block_strategy(rt.runtime_id, reason="dd")
    assert rt.status == "blocked"
    assert any(ev.get("scope") == "strategy" for ev in strategy_runtime_manager._risk_events)


def test_unblock_strategy_restores_runtime_to_stopped():
    rt = _make_runtime("blocked")
    rt.runtime_id = "live:rt-block-2"
    strategy_runtime_manager._strategy_runtimes[rt.runtime_id] = rt
    strategy_runtime_manager._runtime_specs[rt.runtime_id] = {
        "runtime_id": rt.runtime_id,
        "status": "blocked",
        "block_scope": "strategy",
        "block_reason": "x",
    }
    strategy_runtime_manager.block_strategy(rt.runtime_id, reason="y")
    strategy_runtime_manager.unblock_strategy(rt.runtime_id)
    assert rt.status == "stopped"
    assert "live:rt-block-2" not in strategy_runtime_manager._blocked_strategies


def test_unblock_account_resets_blocked_strategy_runtime_status():
    """unblock_account should restore blocked runtimes that were blocked
    by account block, but leave strategy-blocked runtimes alone."""
    rt = _make_runtime("blocked")
    rt.runtime_id = "paper:rt-acct-reset"
    rt.mode = "paper"
    rt.portfolio_id = "p-reset"
    rt.strategy_id = ""  # account-level runtime
    strategy_runtime_manager._strategy_runtimes[rt.runtime_id] = rt
    strategy_runtime_manager.block_account("paper:p-reset", reason="dd")
    strategy_runtime_manager.unblock_account("paper:p-reset")
    assert rt.status == "stopped"


def test_unblock_strategy_no_block_record_is_noop():
    """When runtime_id has no block record, unblock is a no-op."""
    strategy_runtime_manager.unblock_strategy("non-existent-id")
    assert "non-existent-id" not in strategy_runtime_manager._blocked_strategies


def test_unblock_account_no_block_record_is_noop():
    """When account_runtime_id has no block record, unblock is a no-op."""
    strategy_runtime_manager.unblock_account("non-existent-acct")
    assert "non-existent-acct" not in strategy_runtime_manager._blocked_accounts


# ---------------------------------------------------------------------------
# deploy_to_paper / deploy_to_live early-return (when existing deployed)
# ---------------------------------------------------------------------------


def test_deploy_to_paper_returns_existing_when_active():
    """When an active paper deployment already exists for the backtest,
    deploy_to_paper returns the existing runtime without creating a new one."""
    rt = _make_runtime("running")
    rt.runtime_id = "paper:existing-paper"
    rt.mode = "paper"
    rt.source_backtest_portfolio_id = "bt-deploy"
    strategy_runtime_manager._strategy_runtimes[rt.runtime_id] = rt
    # Need an in-memory backtest record for _resolve_backtest_run
    strategy_runtime_manager._backtest_history["bt-deploy"] = _make_backtest("bt-deploy")
    fake_registry = SimpleNamespace()
    fake_market = SimpleNamespace()
    returned = strategy_runtime_manager.deploy_to_paper(
        portfolio_id="bt-deploy",
        principal=100_000.0,
        registry=fake_registry,
        market_data=fake_market,
    )
    assert returned is rt


def test_deploy_to_live_returns_existing_when_active():
    rt = _make_runtime("running")
    rt.runtime_id = "live:existing-live"
    rt.mode = "live"
    rt.source_backtest_portfolio_id = "bt-deploy-2"
    strategy_runtime_manager._strategy_runtimes[rt.runtime_id] = rt
    strategy_runtime_manager._backtest_history["bt-deploy-2"] = _make_backtest("bt-deploy-2")
    fake_registry = SimpleNamespace()
    fake_market = SimpleNamespace()
    fake_gateway = SimpleNamespace()
    strategy_runtime_manager._gateway_broker = fake_gateway
    returned = strategy_runtime_manager.deploy_to_live(
        portfolio_id="bt-deploy-2",
        account_id="acct",
        registry=fake_registry,
        market_data=fake_market,
    )
    assert returned is rt


def test_deploy_to_live_raises_when_no_gateway_broker():
    """When _gateway_broker is None, deploy_to_live raises. Covers L334-L335."""
    strategy_runtime_manager._backtest_history["bt-no-gw"] = _make_backtest("bt-no-gw")
    strategy_runtime_manager._gateway_broker = None
    fake_registry = SimpleNamespace()
    fake_market = SimpleNamespace()
    with pytest.raises(RuntimeError):
        strategy_runtime_manager.deploy_to_live(
            portfolio_id="bt-no-gw",
            account_id="acct",
            registry=fake_registry,
            market_data=fake_market,
        )


def test_deploy_to_paper_full_flow_with_mocked_dependencies(monkeypatch):
    """Exercise deploy_to_paper with PaperBroker.create and
    register_port_backed_broker stubbed to skip real broker port wiring.
    Covers L283-L295, L305 (post-early-return main flow)."""
    import threading as _threading

    class _NoStartThread:
        def __init__(self, target, args, daemon, name):
            pass
        def start(self):
            pass

    monkeypatch.setattr(_threading, "Thread", _NoStartThread)

    fake_paper = SimpleNamespace(avail=0)
    monkeypatch.setattr(
        "quantide.service.strategy_runtime.PaperBroker.create",
        classmethod(lambda cls, **kw: fake_paper),
    )

    fake_handle = SimpleNamespace()
    monkeypatch.setattr(
        "quantide.service.strategy_runtime.register_port_backed_broker",
        lambda **kw: fake_handle,
    )

    # Set up runtime context for deploy_to_paper
    ctx_registry = SimpleNamespace()
    ctx_adapters = SimpleNamespace()
    ctx_market = SimpleNamespace()
    fake_ctx = SimpleNamespace(
        registry=ctx_registry,
        adapters=ctx_adapters,
        market_data=ctx_market,
    )
    strategy_runtime_manager._runtime = fake_ctx

    strategy_runtime_manager._backtest_history["bt-dp"] = _make_backtest("bt-dp")
    runtime = strategy_runtime_manager.deploy_to_paper(
        portfolio_id="bt-dp",
        principal=10_000.0,
        registry=ctx_registry,
        market_data=ctx_market,
    )
    assert runtime.status == "running"
    assert runtime.mode == "paper"


def test_deploy_to_paper_raises_when_runtime_not_initialized(monkeypatch):
    """When self._runtime is None, deploy_to_paper raises RuntimeError.
    Covers L291-L293."""
    strategy_runtime_manager._runtime = None
    strategy_runtime_manager._backtest_history["bt-no-rt"] = _make_backtest("bt-no-rt")
    with pytest.raises(RuntimeError):
        strategy_runtime_manager.deploy_to_paper(
            portfolio_id="bt-no-rt",
            principal=10_000.0,
            registry=SimpleNamespace(),
            market_data=SimpleNamespace(),
        )


# ---------------------------------------------------------------------------
# _start_strategy_runtime direct invocation - account-block early exit
# ---------------------------------------------------------------------------


def test_start_strategy_runtime_direct_account_block_raises(monkeypatch):
    """Direct call to _start_strategy_runtime must raise when account is
    blocked. This covers lines L730-L740."""
    strategy_runtime_manager._blocked_accounts["paper:p-blocked"] = {
        "reason": "drawdown",
    }
    fake_broker = SimpleNamespace()
    with pytest.raises(RuntimeError):
        strategy_runtime_manager._start_strategy_runtime(
            mode="paper",
            strategy_name="Demo",
            config={},
            broker=fake_broker,
            portfolio_id="p-blocked",
            source_backtest_portfolio_id="bt-sb-1",
            account_kind="sim",
            interval="1d",
            market_data=SimpleNamespace(),
            principal=10_000.0,
            runtime_id="paper:p-blocked:s1",
            strategy_id="s1",
            persist=False,
        )


def test_start_strategy_runtime_direct_strategy_block_raises(monkeypatch):
    """Strategy-blocked runtime_id prevents start. Covers L741-L751."""
    strategy_runtime_manager._blocked_strategies["paper:p-sb:s2"] = {
        "reason": "drawdown",
        "scope": "strategy",
    }
    fake_broker = SimpleNamespace()
    with pytest.raises(RuntimeError):
        strategy_runtime_manager._start_strategy_runtime(
            mode="paper",
            strategy_name="Demo",
            config={},
            broker=fake_broker,
            portfolio_id="p-sb",
            source_backtest_portfolio_id="bt-sb-2",
            account_kind="sim",
            interval="1d",
            market_data=SimpleNamespace(),
            principal=10_000.0,
            runtime_id="paper:p-sb:s2",
            strategy_id="s2",
            persist=False,
        )


def test_start_strategy_runtime_direct_success_path(monkeypatch):
    """When no block record, _start_strategy_runtime creates a runtime
    with a thread. We mock threading.Thread so the test doesn't actually
    start one. Covers L752-L794 (success path)."""
    import threading as _threading

    started = []

    class _FakeThread:
        def __init__(self, target, args, daemon, name):
            self.target = target
            self.args = args
            self.daemon = daemon
            self.name = name

        def start(self):
            started.append(self.name)

    monkeypatch.setattr(_threading, "Thread", _FakeThread)
    fake_broker = SimpleNamespace()
    runtime = strategy_runtime_manager._start_strategy_runtime(
        mode="paper",
        strategy_name="Demo",
        config={"universe": ["000001.SZ"]},
        broker=fake_broker,
        portfolio_id="p-start-ok",
        source_backtest_portfolio_id="bt-start-ok",
        account_kind="sim",
        interval="1d",
        market_data=SimpleNamespace(),
        principal=10_000.0,
        runtime_id="paper:p-start-ok:s1",
        strategy_id="s1",
        persist=True,
    )
    assert runtime.status == "running"
    assert strategy_runtime_manager._strategy_runtimes["paper:p-start-ok:s1"] is runtime
    assert strategy_runtime_manager._runtime_specs["paper:p-start-ok:s1"]["status"] == "running"
    assert "paper:p-start-ok:s1" in strategy_runtime_manager._runtime_specs
    assert started  # the fake thread recorded .start() invocation


def test_start_strategy_runtime_direct_auto_generates_ids(monkeypatch):
    """Without passing runtime_id or strategy_id, both should be auto-generated
    based on uuid.uuid4().hex[:8]."""
    import threading as _threading

    class _NoStartThread:
        def __init__(self, target, args, daemon, name):
            pass

        def start(self):
            pass

    monkeypatch.setattr(_threading, "Thread", _NoStartThread)
    fake_broker = SimpleNamespace()
    runtime = strategy_runtime_manager._start_strategy_runtime(
        mode="live",
        strategy_name="Demo",
        config={},
        broker=fake_broker,
        portfolio_id="p-auto",
        source_backtest_portfolio_id="bt-auto",
        account_kind="gateway",
        interval="1d",
        market_data=SimpleNamespace(),
        principal=0.0,
        persist=False,
    )
    assert runtime.runtime_id.startswith("live:p-auto:")
    assert runtime.strategy_id.startswith("Demo-")



# ---------------------------------------------------------------------------
# Lifecycle methods - stop_strategy_runtime
# ---------------------------------------------------------------------------


def test_stop_strategy_runtime_raises_for_missing_id():
    with pytest.raises(RuntimeError):
        strategy_runtime_manager.stop_strategy_runtime("ghost-runtime")


def test_stop_strategy_runtime_marks_status_and_persists_spec(tmp_path):
    import threading as _threading

    rt = _make_runtime("running")
    rt.runtime_id = "live:stop-target"
    rt.stop_event = _threading.Event()
    strategy_runtime_manager._strategy_runtimes[rt.runtime_id] = rt
    strategy_runtime_manager._runtime_specs[rt.runtime_id] = {
        "status": "running",
        "config": {},
    }
    strategy_runtime_manager.stop_strategy_runtime(rt.runtime_id)
    assert rt.status == "stopping"
    assert rt.stop_event.is_set()
    persisted = strategy_runtime_manager._runtime_specs[rt.runtime_id]
    assert persisted["status"] == "stopped"


def test_stop_strategy_runtime_no_stop_event_skips_set():
    """When runtime has no stop_event attribute, calling stop is safe."""
    rt = _make_runtime("running")
    rt.runtime_id = "live:stop-no-event"
    rt.stop_event = None
    strategy_runtime_manager._strategy_runtimes[rt.runtime_id] = rt
    # No spec either — to cover spec=None branch.
    strategy_runtime_manager._runtime_specs.pop(rt.runtime_id, None)
    strategy_runtime_manager.stop_strategy_runtime(rt.runtime_id)
    assert rt.status == "stopping"


# ---------------------------------------------------------------------------
# start_strategy_runtime — raises on missing spec & on blocked strategy
# ---------------------------------------------------------------------------


def test_start_strategy_runtime_raises_when_spec_missing():
    with pytest.raises(RuntimeError):
        strategy_runtime_manager.start_strategy_runtime("ghost")


def test_start_strategy_runtime_raises_when_blocked(db):
    strategy_runtime_manager._runtime_specs["live:p1:s1"] = {
        "status": "stopped",
        "mode": "paper",
        "portfolio_id": "p1",
        "config": {},
    }
    strategy_runtime_manager._blocked_strategies["live:p1:s1"] = {
        "reason": "drawdown",
        "scope": "strategy",
    }
    with pytest.raises(RuntimeError):
        strategy_runtime_manager.start_strategy_runtime("live:p1:s1")


# ---------------------------------------------------------------------------
# bootstrap_from_runtime path
# ---------------------------------------------------------------------------


def _build_fake_runtime() -> SimpleNamespace:
    """Build a minimal RuntimeContext stand-in for bootstrap_from_runtime."""
    rt = SimpleNamespace()
    fake_registry = SimpleNamespace()
    fake_registry.list = lambda: [
        {"kind": "sim", "id": "p1", "name": "Paper1"},
    ]
    fake_registry.get = lambda kind, pid: SimpleNamespace()
    rt.registry = fake_registry
    rt.adapters = SimpleNamespace()
    rt.market_data = SimpleNamespace()
    return rt


def test_bootstrap_from_runtime_seeds_account_runtimes():
    strategy_runtime_manager.bootstrap_from_runtime(_build_fake_runtime())
    # Should have at least one runtime registered for the listed broker.
    assert any(
        rid.startswith("paper:") for rid in strategy_runtime_manager._account_runtimes
    )


# ---------------------------------------------------------------------------
# _runtime_to_row behaves with empty DB (all try/except paths)
# ---------------------------------------------------------------------------


def test_runtime_to_row_returns_well_formed_dict_for_missing_db_state(monkeypatch):
    """When db functions raise or return empty, _runtime_to_row should
    still return a row dict with zero-valued numeric fields."""
    import quantide.service.strategy_runtime as sr_mod

    fake_db = SimpleNamespace(
        get_asset=lambda _pid: None,
        get_positions=lambda _pid: SimpleNamespace(height=0),
        get_orders=lambda _pid: SimpleNamespace(height=0),
    )
    monkeypatch.setattr(sr_mod, "db", fake_db)
    rt = _make_runtime("running")
    rt.broker = SimpleNamespace(avail=0)
    row = strategy_runtime_manager._runtime_to_row(rt)
    assert row["runtime_id"] == rt.runtime_id
    assert row["cash"] == 0.0
    assert row["positions"] == 0


def test_runtime_to_row_includes_account_block_metadata(monkeypatch):
    import quantide.service.strategy_runtime as sr_mod

    fake_db = SimpleNamespace(
        get_asset=lambda _pid: SimpleNamespace(cash=100, market_value=50, total=150),
        get_positions=lambda _pid: SimpleNamespace(height=2),
        get_orders=lambda _pid: SimpleNamespace(height=3),
    )
    monkeypatch.setattr(sr_mod, "db", fake_db)
    rt = _make_runtime("running")
    rt.strategy_id = "sid"
    strategy_runtime_manager._blocked_strategies[rt.runtime_id] = {
        "reason": "drawdown",
        "scope": "strategy",
    }
    row = strategy_runtime_manager._runtime_to_row(rt)
    assert row["status"] == "blocked"
    assert row["blocked_scope"] == "strategy"
    assert row["can_unblock_strategy"] is True


def test_runtime_to_row_when_account_blocked_returns_blocked_scope(monkeypatch):
    """When account is blocked, status becomes 'blocked' and blocked_scope=='account'."""
    import quantide.service.strategy_runtime as sr_mod

    fake_db = SimpleNamespace(
        get_asset=lambda _pid: None,
        get_positions=lambda _pid: SimpleNamespace(height=0),
        get_orders=lambda _pid: SimpleNamespace(height=0),
    )
    monkeypatch.setattr(sr_mod, "db", fake_db)
    rt = _make_runtime("running")
    rt.strategy_id = ""  # account-level runtime
    rt.broker = SimpleNamespace(avail=0)
    account_key = strategy_runtime_manager._account_key_for_runtime(rt)
    strategy_runtime_manager._blocked_accounts[account_key] = {
        "reason": "drawdown"
    }
    row = strategy_runtime_manager._runtime_to_row(rt)
    assert row["status"] == "blocked"
    assert row["blocked_scope"] == "account"
    assert row["block_target"] == account_key


def test_account_key_for_runtime_format():
    """Helper method: account key derived from mode+portfolio_id."""
    rt = _make_runtime("running")
    rt.mode = "live"
    rt.portfolio_id = "p-x"
    key = strategy_runtime_manager._account_key_for_runtime(rt)
    assert key == "live:p-x"


# ---------------------------------------------------------------------------
# _extract_symbols / _build_quotes
# ---------------------------------------------------------------------------


def test_extract_symbols_handles_list_and_dict():
    syms = strategy_runtime_manager._extract_symbols({"symbols": ["a", "b"]})
    assert syms == ["a", "b"]


def test_extract_symbols_returns_empty_for_unknown_shape():
    syms = strategy_runtime_manager._extract_symbols({"universe": "x"})
    assert syms == []


# ---------------------------------------------------------------------------
# _save_specs / _load_specs via state_file fixture
# ---------------------------------------------------------------------------


def test_save_and_load_specs_roundtrip(tmp_path):
    """Setting + reading _runtime_specs through the file round-trip works."""
    state_file = tmp_path / "state.json"
    strategy_runtime_manager._runtime_specs["x:1"] = {
        "runtime_id": "x:1",
        "status": "stopped",
        "config": {},
    }
    strategy_runtime_manager._state_file = lambda: state_file
    strategy_runtime_manager._save_specs()
    assert state_file.exists()
    # Clear and reload.
    strategy_runtime_manager._runtime_specs.clear()
    strategy_runtime_manager._load_specs()
    assert "x:1" in strategy_runtime_manager._runtime_specs
    assert strategy_runtime_manager._runtime_specs["x:1"]["status"] == "stopped"


def test_load_specs_handles_missing_file(tmp_path):
    """When state file does not exist, _load_specs is a no-op."""
    strategy_runtime_manager._state_file = lambda: tmp_path / "missing.json"
    before = dict(strategy_runtime_manager._runtime_specs)
    strategy_runtime_manager._load_specs()
    assert strategy_runtime_manager._runtime_specs == before
