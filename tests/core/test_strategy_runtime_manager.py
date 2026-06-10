import datetime
from pathlib import Path

from quantide.core.enums import BrokerKind
from quantide.service.strategy_runtime import StrategyRuntime, StrategyRuntimeManager


def test_strategy_runtime_manager_extract_symbols():
    manager = StrategyRuntimeManager()
    assert manager._extract_symbols({"symbol": "000001.SZ"}) == ["000001.SZ"]
    assert manager._extract_symbols({"assets": ["000001.SZ", "000002.SZ"]}) == [
        "000001.SZ",
        "000002.SZ",
    ]
    assert manager._extract_symbols({}) == []


def test_strategy_runtime_manager_backtest_runtime_lifecycle():
    manager = StrategyRuntimeManager()
    manager.create_backtest_runtime(
        portfolio_id="p1",
        strategy_name="DemoStrategy",
        config={"symbol": "000001.SZ"},
        interval="1d",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_cash=1000000,
    )
    run = manager.get_backtest_run("p1")
    assert run is not None
    assert run.status == "running"
    manager.complete_backtest_runtime("p1")
    run2 = manager.get_backtest_run("p1")
    assert run2 is not None
    assert run2.status == "finished"


def test_strategy_runtime_manager_save_and_load_specs(tmp_path: Path):
    manager = StrategyRuntimeManager()
    manager._state_file = lambda: tmp_path / "strategy_runtimes.json"
    manager._runtime_specs = {
        "paper:p1:s1": {
            "runtime_id": "paper:p1:s1",
            "mode": "paper",
            "strategy_name": "DemoStrategy",
            "strategy_id": "s1",
            "portfolio_id": "p1",
            "account_kind": "sim",
            "status": "stopped",
            "config": {"symbol": "000001.SZ"},
            "symbols": ["000001.SZ"],
            "principal": 1000000,
            "interval": "1m",
        }
    }
    manager._save_specs()

    manager2 = StrategyRuntimeManager()
    manager2._state_file = lambda: tmp_path / "strategy_runtimes.json"
    manager2._load_specs()
    assert "paper:p1:s1" in manager2._runtime_specs
    assert manager2._runtime_specs["paper:p1:s1"]["status"] == "stopped"


def test_strategy_runtime_manager_persists_block_state_and_risk_events(tmp_path: Path):
    manager = StrategyRuntimeManager()
    manager._state_file = lambda: tmp_path / "strategy_runtimes.json"
    manager._account_runtimes["live:gateway"] = StrategyRuntime(
        runtime_id="live:gateway",
        mode="live",
        strategy_name="",
        strategy_id="",
        portfolio_id="gateway",
        account_kind="gateway",
        status="idle",
        config={},
    )
    manager._strategy_runtimes["live:gateway:demo-1"] = StrategyRuntime(
        runtime_id="live:gateway:demo-1",
        mode="live",
        strategy_name="DemoStrategy",
        strategy_id="demo-1",
        portfolio_id="gateway",
        account_kind="gateway",
        status="running",
        config={},
    )
    manager._runtime_specs["live:gateway:demo-1"] = {
        "runtime_id": "live:gateway:demo-1",
        "mode": "live",
        "strategy_name": "DemoStrategy",
        "strategy_id": "demo-1",
        "portfolio_id": "gateway",
        "account_kind": "gateway",
        "status": "running",
        "config": {},
        "symbols": [],
        "principal": 0,
        "interval": "1m",
    }

    manager.block_account("live:gateway", reason="max drawdown")
    manager.block_strategy("live:gateway:demo-1", reason="manual circuit break")

    manager2 = StrategyRuntimeManager()
    manager2._state_file = lambda: tmp_path / "strategy_runtimes.json"
    manager2._load_specs()

    assert manager2._blocked_accounts["live:gateway"]["reason"] == "max drawdown"
    assert manager2._blocked_strategies["live:gateway:demo-1"]["reason"] == "manual circuit break"
    assert any(event["title"] == "账户已封锁" for event in manager2.list_risk_events())
    assert any(event["title"] == "策略已封锁" for event in manager2.list_risk_events())


def test_strategy_runtime_manager_restart_recovery_skips_blocked_specs(tmp_path: Path):
    manager = StrategyRuntimeManager()
    manager._state_file = lambda: tmp_path / "strategy_runtimes.json"
    manager._runtime_specs = {
        "live:gateway:demo-1": {
            "runtime_id": "live:gateway:demo-1",
            "mode": "live",
            "strategy_name": "DemoStrategy",
            "strategy_id": "demo-1",
            "portfolio_id": "gateway",
            "account_kind": "gateway",
            "status": "running",
            "config": {},
            "symbols": [],
            "principal": 0,
            "interval": "1m",
        }
    }
    manager._blocked_strategies = {
        "live:gateway:demo-1": {
            "target_id": "live:gateway:demo-1",
            "reason": "manual hold",
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
    }

    manager._restore_persisted_runtimes()

    spec = manager._runtime_specs["live:gateway:demo-1"]
    assert spec["status"] == "blocked"
    assert spec["block_scope"] == "strategy"
    assert any(event["title"] == "重启恢复跳过封锁运行时" for event in manager.list_risk_events())


def test_strategy_runtime_manager_backtest_deployment_modes_only_reports_active_runtime():
    manager = StrategyRuntimeManager()
    manager._strategy_runtimes["paper:acct:demo-1"] = StrategyRuntime(
        runtime_id="paper:acct:demo-1",
        mode="paper",
        strategy_name="DemoStrategy",
        strategy_id="demo-1",
        portfolio_id="paper-acct",
        account_kind="sim",
        status="running",
        config={},
        source_backtest_portfolio_id="bt-1",
    )
    manager._strategy_runtimes["live:gateway:demo-2"] = StrategyRuntime(
        runtime_id="live:gateway:demo-2",
        mode="live",
        strategy_name="DemoStrategy",
        strategy_id="demo-2",
        portfolio_id="gateway",
        account_kind="gateway",
        status="stopped",
        config={},
        source_backtest_portfolio_id="bt-1",
    )

    result = manager.backtest_deployment_modes("bt-1")

    assert "paper" in result
    assert "live" not in result
    assert result["paper"]["source_backtest_portfolio_id"] == "bt-1"


def test_apply_live_broker_config_wires_cheat_off_to_wrapper():
    """#45 followup: 启动 live runtime 时必须把 cheat_on_close 等参数注入 broker wrapper.

    回归 #45 review (Aaron): 原 set_strategy_runtime_config 从未被调用,
    生产路径上 _strategy_cheat_on_close 永远默认 True, deferred_orders 分支死代码.
    """
    manager = StrategyRuntimeManager()

    class _SpyWrapper:
        def __init__(self):
            self.calls: list[dict] = []

        def set_strategy_runtime_config(self, **kwargs):
            self.calls.append(kwargs)

    spy = _SpyWrapper()
    runtime = StrategyRuntime(
        runtime_id="live:gateway:demo",
        mode="live",
        strategy_name="DemoStrategy",
        strategy_id="demo",
        portfolio_id="gateway",
        account_kind=BrokerKind.QMT.value,
        status="running",
        config={
            "cheat_on_close": False,
            "live_execution_window": "post_auction",
            "live_execution_slippage": 0.005,
        },
        broker=spy,
    )
    manager._apply_live_broker_config(runtime)

    assert len(spy.calls) == 1, (
        f"set_strategy_runtime_config 应被调一次, got {spy.calls}"
    )
    assert spy.calls[0]["cheat_on_close"] is False
    assert spy.calls[0]["live_execution_window"] == "post_auction"
    assert spy.calls[0]["live_execution_slippage"] == 0.005


def test_apply_live_broker_config_defaults_when_strategy_omits_params():
    """#45 followup: 策略 config 不写 cheat_on_close 时, 默认 False (post-bar decision)."""
    manager = StrategyRuntimeManager()

    class _SpyWrapper:
        def __init__(self):
            self.calls: list[dict] = []

        def set_strategy_runtime_config(self, **kwargs):
            self.calls.append(kwargs)

    spy = _SpyWrapper()
    runtime = StrategyRuntime(
        runtime_id="live:gateway:demo2",
        mode="live",
        strategy_name="DemoStrategy",
        strategy_id="demo2",
        portfolio_id="gateway",
        account_kind=BrokerKind.QMT.value,
        status="running",
        config={"symbol": "000001.SZ"},
        broker=spy,
    )
    manager._apply_live_broker_config(runtime)

    assert spy.calls[0]["cheat_on_close"] is False
    assert spy.calls[0]["live_execution_window"] == "auction"
    assert spy.calls[0]["live_execution_slippage"] == 0.001


def test_create_backtest_runtime_persists_cheat_metadata(tmp_path: Path):
    """#49 followup: cheat_on_close + cheat_on_close_time 进入 runtime_specs 持久化文件."""
    manager = StrategyRuntimeManager()
    manager._state_file = lambda: tmp_path / "strategy_runtimes.json"
    manager.create_backtest_runtime(
        portfolio_id="p1",
        strategy_name="DemoStrategy",
        config={"symbol": "000001.SZ", "cheat_on_close": True},
        interval="1d",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_cash=1000000,
    )

    manager2 = StrategyRuntimeManager()
    manager2._state_file = lambda: tmp_path / "strategy_runtimes.json"
    manager2._load_specs()
    spec = manager2._runtime_specs.get("backtest:p1")
    assert spec is not None, "runtime_specs 应持久化 backtest:p1"
    assert spec.get("cheat_on_close") is True
    assert spec.get("cheat_on_close_time") == "14:57"


def test_resolve_backtest_run_restores_cheat_from_persisted_specs(tmp_path: Path):
    """#49 followup: 重启后 _resolve_backtest_run 必须从持久化 specs 恢复 cheat 字段,
    而不是用策略 PARAMS class attr + 当前 settings.cheat_on_close_time 推断.
    """
    manager = StrategyRuntimeManager()
    manager._state_file = lambda: tmp_path / "strategy_runtimes.json"
    manager._runtime_specs = {
        "backtest:bt-historic": {
            "runtime_id": "backtest:bt-historic",
            "mode": "backtest",
            "strategy_name": "DualMAStrategy",
            "strategy_id": "s-historic",
            "portfolio_id": "bt-historic",
            "account_kind": "bt",
            "status": "finished",
            "config": {"symbol": "000001.SZ", "cheat_on_close": True},
            "cheat_on_close": True,
            "cheat_on_close_time": "14:30",
            "interval": "1d",
        }
    }
    manager._save_specs()

    class _FakePortfolio:
        name = "DualMAStrategy"
        start = "2024-01-01"
        end = "2024-01-31"

    manager2 = StrategyRuntimeManager()
    manager2._state_file = lambda: tmp_path / "strategy_runtimes.json"
    manager2._load_specs()

    from quantide.service import strategy_runtime as _rt_mod
    manager2.get_backtest_run = lambda pid: None  # type: ignore[assignment]
    monkeypatch_obj = _rt_mod.db
    original_get_portfolio = monkeypatch_obj.get_portfolio

    def _fake_get_portfolio(pid):
        if pid == "bt-historic":
            return _FakePortfolio()
        return original_get_portfolio(pid)

    monkeypatch_obj.get_portfolio = _fake_get_portfolio  # type: ignore[assignment]
    try:
        run = manager2._resolve_backtest_run("bt-historic")
        assert run.cheat_on_close is True
        assert run.cheat_on_close_time == "14:30", (
            f"应从持久化 specs 恢复 14:30, got {run.cheat_on_close_time!r}"
        )
    finally:
        monkeypatch_obj.get_portfolio = original_get_portfolio  # type: ignore[assignment]


def test_strategy_loop_live_wires_broker_config_and_uses_real_time(monkeypatch):
    """#46 / #45 integration: live runtime 必须先调 _apply_live_broker_config,
    on_bar 用 datetime.now() (real time), 不是 9:30/14:57 控制时钟.

    反驳 #46 review 的部分观点: paper/live bar trigger time 应是 real time,
    只有 backtest runner 才有 9:30 vs 14:57 选择.
    """
    import asyncio
    from quantide.core.enums import FrameType
    from quantide.service import strategy_runtime as _rt_mod

    class _DemoStrategy:
        def __init__(self, broker, config):
            self.broker = broker
            self.config = config
            self.interval = "1d"
            self.on_bar_calls: list = []

        async def init(self):
            pass

        async def on_start(self, tm):
            self._on_start_tm = tm

        async def on_bar(self, tm, quotes, frame_type):
            self.on_bar_calls.append((tm, frame_type))
            self.broker._spy_stop = True
            raise RuntimeError("stop loop")

        async def on_stop(self, tm):
            pass

    class _SpyBroker:
        def __init__(self):
            self.set_strategy_runtime_config_called: list[dict] = []
            self.set_clock_calls: list = []

        def set_strategy_runtime_config(self, **kwargs):
            self.set_strategy_runtime_config_called.append(kwargs)

        def set_clock(self, tm):
            self.set_clock_calls.append(tm)

    spy = _SpyBroker()
    monkeypatch.setattr(_rt_mod.strategy_loader, "load_from_cache",
                        lambda: {"DemoStrategy": _DemoStrategy})

    manager = _rt_mod.StrategyRuntimeManager()
    runtime = _rt_mod.StrategyRuntime(
        runtime_id="live:gateway:demo",
        mode="live",
        strategy_name="DemoStrategy",
        strategy_id="demo",
        portfolio_id="gateway",
        account_kind="gateway",
        status="running",
        config={
            "cheat_on_close": False,
            "live_execution_window": "auction",
            "live_execution_slippage": 0.001,
        },
        symbols=["000001.SZ"],
        stop_event=_rt_mod.threading.Event(),
        broker=spy,
    )

    async def _noop_sleep():
        pass

    strategy_holder: dict[str, Any] = {}

    original_strategy_cls = _DemoStrategy
    wrapped_cls = type(
        "WrappedDemoStrategy",
        (original_strategy_cls,),
        {
            "__init__": lambda self, broker, config: (
                original_strategy_cls.__init__(self, broker, config),
                strategy_holder.update({"instance": self}),
            )[-1],
        },
    )

    with monkeypatch.context() as m:
        m.setattr(
            _rt_mod.strategy_loader,
            "load_from_cache",
            lambda: {"DemoStrategy": wrapped_cls},
        )
        m.setattr(_rt_mod.asyncio, "sleep", lambda *_a, **_kw: _noop_sleep())

        async def _run_loop():
            await manager._strategy_loop(runtime, "1d", market_data=None)

        _rt_mod.asyncio.run(_run_loop())

    assert len(spy.set_strategy_runtime_config_called) == 1, (
        f"live loop 必须先调 set_strategy_runtime_config, got {spy.set_strategy_runtime_config_called}"
    )
    assert spy.set_strategy_runtime_config_called[0]["cheat_on_close"] is False

    strategy_instance = strategy_holder["instance"]
    assert len(strategy_instance.on_bar_calls) == 1, (
        f"应触发一次 on_bar, got {len(strategy_instance.on_bar_calls)} calls"
    )
    bar_tm, frame = strategy_instance.on_bar_calls[0]
    assert frame == FrameType.DAY
    delta = abs((bar_tm - _rt_mod.datetime.datetime.now()).total_seconds())
    assert delta < 5, (
        f"live loop 的 bar_tm 应是 real time (now), 偏差 {delta:.1f}s"
    )
    assert runtime.status == "failed"
    assert runtime.error == "stop loop"
