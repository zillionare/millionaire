"""per-strategy dry-run 任务注册/卸载测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from quantide.service.strategy_tasks import StrategyTaskManager
from quantide.service.strategy_tracking import TrackingStore


class _Broker:
    cash = 100000.0
    positions = {}


def test_attach_and_detach_registers_two_jobs(tmp_path, monkeypatch):
    import quantide.service.strategy_tasks as module

    store = TrackingStore(tmp_path / "track.db")
    monkeypatch.setattr(module, "tracking_store", store)
    fake_scheduler = MagicMock()
    monkeypatch.setattr(module.scheduler, "_scheduler", fake_scheduler)
    added = []
    monkeypatch.setattr(
        module.scheduler, "add_job", lambda *args, **kwargs: added.append(kwargs)
    )
    manager = StrategyTaskManager()
    runtime = SimpleNamespace(
        runtime_id="paper:p1:Demo-1",
        portfolio_id="p1",
        mode="paper",
        status="running",
        config={"fill_timing": "auction_close"},
        principal=100000.0,
        broker=_Broker(),
        source_backtest_portfolio_id="bt-1",
    )

    manager.attach(runtime)
    assert len(added) == 2
    assert {job["id"].rsplit(":", 1)[-1] for job in added} == {"eod", "morning"}
    assert all(job["max_instances"] == 1 for job in added)
    assert store.get_run(runtime.runtime_id) is not None
    assert store.get_shadow_state(runtime.runtime_id)["cash"] == 100000.0

    manager.detach(runtime.runtime_id)
    assert fake_scheduler.remove_job.call_count == 2


def test_attach_ignores_backtest_runtime(tmp_path, monkeypatch):
    import quantide.service.strategy_tasks as module

    monkeypatch.setattr(module, "tracking_store", TrackingStore(tmp_path / "t.db"))
    added = []
    monkeypatch.setattr(
        module.scheduler, "add_job", lambda *args, **kwargs: added.append(kwargs)
    )
    manager = StrategyTaskManager()
    manager.attach(
        SimpleNamespace(
            runtime_id="backtest:bt-1",
            portfolio_id="bt-1",
            mode="backtest",
            status="finished",
            config={},
            broker=None,
        )
    )
    assert added == []


def test_run_shadow_writes_daily_snapshot(tmp_path, monkeypatch):
    import datetime

    import polars as pl

    import quantide.service.shadow_broker as shadow_module
    import quantide.service.strategy_tasks as module
    import quantide.service.strategy_runtime as runtime_module
    from quantide.service.discovery import strategy_loader

    class _Bars:
        @staticmethod
        def get_bars_in_range(start, end=None, assets=None, adjust=None, eager_mode=True):
            return pl.DataFrame(
                {
                    "date": [datetime.date(2026, 10, 27)],
                    "asset": ["000001.SZ"],
                    "open": [10.0],
                    "high": [10.5],
                    "low": [9.8],
                    "close": [10.0],
                    "volume": [1000000.0],
                    "amount": [10_000_000.0],
                    "adjust": [1.0],
                    "is_st": [False],
                    "up_limit": [11.0],
                    "down_limit": [9.0],
                }
            )

    class _DummyStrategy:
        def __init__(self, broker, config):
            self.broker = broker

        async def init(self):
            return None

        async def on_bar(self, tm):
            await self.broker.buy_amount("000001.SZ", 10000)

    monkeypatch.setattr(shadow_module, "daily_bars", _Bars())
    monkeypatch.setattr(
        strategy_loader,
        "load_from_cache",
        lambda: {"Dummy": _DummyStrategy},
    )
    store = TrackingStore(tmp_path / "track.db")
    monkeypatch.setattr(module, "tracking_store", store)
    monkeypatch.setattr(runtime_module, "tracking_store", store)
    monkeypatch.setattr("quantide.service.runtime_proxies.tracking_store", store)
    store.ensure_run("paper:p1", "p1", start_date=datetime.date(2026, 10, 27))
    store.save_shadow_state("paper:p1", "p1", cash=100000.0, positions=[])
    manager = StrategyTaskManager()
    runtime = SimpleNamespace(
        runtime_id="paper:p1",
        portfolio_id="p1",
        mode="paper",
        status="running",
        strategy_name="Dummy",
        config={
            "fill_timing": "auction_close",
            "commission": 1e-4,
            "stamp_duty": 5e-4,
            "transfer_fee": 1e-5,
            "min_commission": 5.0,
            "slippage_pct": 0.0,
        },
        principal=100000.0,
        broker=_Broker(),
    )

    result = manager._run_shadow(runtime, datetime.date(2026, 10, 27))
    assert result is not None
    assert result["nav"] > 0
    rows = store.list_daily(runtime_id="paper:p1", source="dry_run")
    assert len(rows) == 1
    assert rows[0]["trades"]


def test_next_open_shadow_queues_then_fills_at_target_open(tmp_path, monkeypatch):
    import datetime

    import polars as pl

    import quantide.service.shadow_broker as shadow_module
    import quantide.service.strategy_tasks as module
    import quantide.service.strategy_runtime as runtime_module
    from quantide.service.discovery import strategy_loader

    class _Bars:
        @staticmethod
        def get_bars_in_range(start, end=None, assets=None, adjust=None, eager_mode=True):
            return pl.DataFrame(
                {
                    "date": [datetime.date(2026, 10, 28)],
                    "asset": ["000001.SZ"],
                    "open": [20.0],
                    "high": [20.5],
                    "low": [19.8],
                    "close": [21.0],
                    "volume": [1000000.0],
                    "amount": [20_000_000.0],
                    "adjust": [1.0],
                    "is_st": [False],
                    "up_limit": [22.0],
                    "down_limit": [18.0],
                }
            )

    class _DummyStrategy:
        def __init__(self, broker, config):
            self.broker = broker

        async def init(self):
            return None

        async def on_bar(self, tm):
            await self.broker.buy_amount("000001.SZ", 10000)

    monkeypatch.setattr(shadow_module, "daily_bars", _Bars())
    monkeypatch.setattr(strategy_loader, "load_from_cache", lambda: {"Dummy": _DummyStrategy})
    store = TrackingStore(tmp_path / "track.db")
    monkeypatch.setattr(module, "tracking_store", store)
    monkeypatch.setattr(runtime_module, "tracking_store", store)
    monkeypatch.setattr("quantide.service.runtime_proxies.tracking_store", store)
    store.ensure_run("paper:p1", "p1", start_date=datetime.date(2026, 10, 27))
    store.save_shadow_state("paper:p1", "p1", cash=100000.0, positions=[])
    manager = StrategyTaskManager()
    runtime = SimpleNamespace(
        runtime_id="paper:p1",
        portfolio_id="p1",
        strategy_name="Dummy",
        strategy_id="s1",
        mode="paper",
        status="running",
        interval="1d",
        config={"fill_timing": "next_open", "slippage_pct": 0.0},
        principal=100000.0,
    )

    assert manager._run_shadow(runtime, datetime.date(2026, 10, 27)) is not None
    pending = store.list_next_open_intents(runtime_id="paper:p1:shadow")
    assert len(pending) == 1
    assert pending[0]["status"] == "pending"

    assert manager._process_shadow_intents(runtime, datetime.date(2026, 10, 28)) == 1
    assert store.list_next_open_intents(runtime_id="paper:p1:shadow") == []
    state = store.get_shadow_state("paper:p1")
    assert state is not None and state["cash"] < 100000.0
    rows = store.list_daily(runtime_id="paper:p1", source="dry_run")
    assert rows[-1]["trades"][0]["price"] == 20.0
