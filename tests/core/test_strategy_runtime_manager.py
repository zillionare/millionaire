import datetime
from pathlib import Path

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
