from __future__ import annotations

import datetime
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from quantide.core.enums import FrameType
from quantide.core.ports.broker import ExecutionResult
from quantide.core.strategy import RiskStrategy
from quantide.service.data_readiness import DataReadinessMonitor
from quantide.service.backtest_orders import BacktestOrders
from quantide.service.runner import BacktestRunner, _BacktestNextOpenBrokerProxy
from quantide.service.strategy_runtime import (
    NextOpenBarBrokerProxy,
    NextOpenBrokerProxy,
    StrategyRuntimeManager,
)
from quantide.service.strategy_tracking import TrackingStore


def test_risk_strategy_cannot_be_started_as_independent_backtest(monkeypatch):
    from quantide.service.strategy_runtime import strategy_loader

    class ExampleRisk(RiskStrategy):
        pass

    monkeypatch.setattr(strategy_loader, "load_from_cache", lambda: {"Risk": ExampleRisk})
    manager = StrategyRuntimeManager()
    with pytest.raises(ValueError, match="风控策略不能作为独立策略运行"):
        manager.create_backtest_runtime(
            "portfolio", "Risk", {}, "1d", "2024-01-01", "2024-02-01", 10000
        )


@pytest.mark.asyncio
async def test_target_percent_preserves_next_open_timing_for_both_directions():
    buy, sell = AsyncMock(), AsyncMock()
    broker = SimpleNamespace(
        total_asset=lambda: 10000.0, _positions={}, buy_amount=buy, sell_amount=sell
    )
    tm = datetime.datetime(2024, 1, 2, 10, 30)
    await BacktestOrders.trade_target_pct(
        broker, "000001.SZ", 0.5, order_time=tm, timeout=2.0, fill_timing="next_open"
    )
    buy.assert_awaited_once_with("000001.SZ", 5000.0, 0, tm, 2.0, fill_timing="next_open")

    broker._positions["000001.SZ"] = SimpleNamespace(mv=5000.0)
    await BacktestOrders.trade_target_pct(
        broker, "000001.SZ", 0.3, order_time=tm, timeout=2.0, fill_timing="next_open"
    )
    sell.assert_awaited_once_with(
        "000001.SZ", 2000.0, 0, tm, 2.0, method="floor", fill_timing="next_open"
    )


class _DailyStrategy:
    BAR_INTERVAL = "1d"

    @staticmethod
    def default_config():
        return {"bar_interval": "1d"}


class _ThirtyMinuteStrategy:
    BAR_INTERVAL = "30m"

    @staticmethod
    def default_config():
        return {"bar_interval": "30m"}


def test_strategy_interval_is_declared_and_conflicting_override_is_rejected():
    assert BacktestRunner.strategy_interval(_DailyStrategy) == "1d"
    assert BacktestRunner.strategy_interval(_ThirtyMinuteStrategy) == "30m"

    with pytest.raises(ValueError, match="bar_interval"):
        BacktestRunner.validate_strategy_interval(
            _DailyStrategy, {"bar_interval": "30m"}, FrameType.DAY
        )

    with pytest.raises(ValueError, match="30m"):
        BacktestRunner.validate_strategy_interval(_ThirtyMinuteStrategy, {}, FrameType.DAY)


def test_runtime_spec_interval_must_match_strategy_definition():
    manager = StrategyRuntimeManager()
    manager._runtime_specs["paper:p1:s1"] = {
        "runtime_id": "paper:p1:s1",
        "mode": "paper",
        "strategy_name": "Daily",
        "strategy_id": "s1",
        "portfolio_id": "p1",
        "interval": "30m",
        "config": {},
    }

    with pytest.raises(ValueError, match="interval"):
        manager.validate_runtime_interval(manager._runtime_specs["paper:p1:s1"], _DailyStrategy)


def test_daily_readiness_requires_post_close_persisted_data_without_1505_assumption():
    day = datetime.date(2026, 10, 27)

    class _Calendar:
        def is_trade_day(self, value):
            return value.date() == day if isinstance(value, datetime.datetime) else value == day

    class _Daily:
        end = day

        def get_bars_in_range(self, *args, **kwargs):
            import polars as pl

            return pl.DataFrame(
                {
                    "date": [day],
                    "asset": ["000001.SZ"],
                    "open": [10.0],
                    "high": [10.5],
                    "low": [9.8],
                    "close": [10.2],
                    "volume": [1000.0],
                }
            )

    monitor = DataReadinessMonitor(
        daily_store=_Daily(), calendar=_Calendar(), recorder=lambda **_: None
    )
    assert not monitor.is_daily_ready(datetime.datetime(2026, 10, 27, 14, 59))
    assert monitor.is_daily_ready(datetime.datetime(2026, 10, 27, 15, 0))


def test_daily_readiness_rejects_previous_or_future_persisted_dates():
    day = datetime.date(2026, 10, 27)

    class _Calendar:
        def is_trade_day(self, value):
            return value == day

    class _Daily:
        end = day

        def get_bars_in_range(self, *args, **kwargs):
            import polars as pl

            return pl.DataFrame(
                {
                    "date": [day],
                    "asset": ["000001.SZ"],
                    "open": [10.0],
                    "high": [10.5],
                    "low": [9.8],
                    "close": [10.2],
                    "volume": [1000.0],
                }
            )

    monitor = DataReadinessMonitor(
        daily_store=_Daily(), calendar=_Calendar(), recorder=lambda **_: None
    )
    assert not monitor.is_daily_ready(datetime.datetime(2026, 10, 28, 9, 25), day=day)

    class _FutureDaily(_Daily):
        end = day + datetime.timedelta(days=1)

    future_monitor = DataReadinessMonitor(
        daily_store=_FutureDaily(), calendar=_Calendar(), recorder=lambda **_: None
    )
    assert not future_monitor.is_daily_ready(datetime.datetime(2026, 10, 27, 15, 0))


def test_next_open_decision_does_not_replay_yesterday_after_restart(monkeypatch):
    from quantide.service import data_readiness as readiness_module
    from quantide.service import strategy_runtime as module

    day = datetime.date(2026, 10, 27)
    monkeypatch.setattr(module, "daily_bars", type("_Bars", (), {"end": day})())
    monkeypatch.setattr(
        readiness_module.data_readiness_monitor,
        "is_daily_ready",
        lambda now, *, day=None: True,
        raising=False,
    )
    manager = StrategyRuntimeManager()

    assert manager._next_open_decision_day(datetime.datetime(2026, 10, 28, 9, 25)) is None


def test_persisted_runtime_without_interval_is_rejected():
    from types import SimpleNamespace

    manager = StrategyRuntimeManager()
    manager._registry = SimpleNamespace(get=lambda *_: SimpleNamespace())
    with pytest.raises(RuntimeError, match="周期"):
        manager._start_from_spec(
            {
                "runtime_id": "paper:p1:s1",
                "mode": "paper",
                "strategy_name": "Daily",
                "strategy_id": "s1",
                "portfolio_id": "p1",
                "account_kind": "simulation",
                "config": {},
            }
        )


@pytest.mark.asyncio
async def test_next_open_processor_drains_persisted_intent(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import quantide.service.strategy_runtime as runtime_module

    store = TrackingStore(tmp_path / "intents.db")
    monkeypatch.setattr(runtime_module, "tracking_store", store)
    monkeypatch.setattr("quantide.service.runtime_proxies.tracking_store", store)
    store.enqueue_next_open_intent(
        runtime_id="paper:p1:s1",
        portfolio_id="p1",
        strategy_id="s1",
        signal_date=datetime.date(2026, 10, 27),
        target_date=datetime.date(2026, 10, 28),
        method="buy_amount",
        args=["000001.SZ", 10000],
        kwargs={},
        intent_key="buy:2026-10-27",
    )

    calls = []

    class _Broker:
        async def buy_amount(self, *args, **kwargs):
            calls.append((args, kwargs))
            return ExecutionResult(qt_oid="q1")

    manager = StrategyRuntimeManager()
    manager._strategy_runtimes["paper:p1:s1"] = SimpleNamespace(
        runtime_id="paper:p1:s1",
        mode="paper",
        status="running",
        broker=_Broker(),
        strategy_id="s1",
    )

    assert (
        await manager.process_next_open_intents(
            "paper:p1:s1", datetime.datetime(2026, 10, 28, 9, 25)
        )
        == 1
    )
    assert calls[0][0] == ("000001.SZ", 10000)
    assert calls[0][1]["order_time"] == datetime.datetime(2026, 10, 28, 9, 25)
    assert store.list_next_open_intents(runtime_id="paper:p1:s1") == []


@pytest.mark.asyncio
async def test_next_open_proxy_is_async_and_returns_empty_execution_result(monkeypatch, tmp_path):
    import quantide.service.strategy_runtime as runtime_module

    store = TrackingStore(tmp_path / "proxy.db")
    monkeypatch.setattr(runtime_module, "tracking_store", store)
    monkeypatch.setattr("quantide.service.runtime_proxies.tracking_store", store)
    proxy = NextOpenBrokerProxy(
        object(),
        runtime_id="paper:p1:s1",
        portfolio_id="p1",
        strategy_id="s1",
        signal_date=datetime.date(2026, 10, 27),
    )

    assert inspect.iscoroutinefunction(proxy.buy)
    first = await proxy.buy(asset="000001.SZ", shares=1000, order_time="retry-1")
    second = await proxy.buy(asset="000001.SZ", shares=1000, order_time="retry-2")
    assert isinstance(first, ExecutionResult)
    assert first == ExecutionResult.empty()
    assert second == ExecutionResult.empty()
    assert len(store.list_next_open_intents(runtime_id="paper:p1:s1")) == 1


def test_next_open_intent_is_durable_and_idempotent(tmp_path):
    store = TrackingStore(tmp_path / "tracking.db")
    kwargs = {"price": 0, "order_time": "2026-10-27T15:00:00"}
    first = store.enqueue_next_open_intent(
        runtime_id="paper:p1:s1",
        portfolio_id="p1",
        strategy_id="s1",
        signal_date=datetime.date(2026, 10, 27),
        target_date=datetime.date(2026, 10, 28),
        method="buy_amount",
        args=["000001.SZ", 10000],
        kwargs=kwargs,
        intent_key="buy_amount:000001.SZ:10000:2026-10-27",
    )
    second = store.enqueue_next_open_intent(
        runtime_id="paper:p1:s1",
        portfolio_id="p1",
        strategy_id="s1",
        signal_date=datetime.date(2026, 10, 27),
        target_date=datetime.date(2026, 10, 28),
        method="buy_amount",
        args=["000001.SZ", 10000],
        kwargs=kwargs,
        intent_key="buy_amount:000001.SZ:10000:2026-10-27",
    )

    assert first["intent_id"] == second["intent_id"]
    assert len(store.list_next_open_intents(runtime_id="paper:p1:s1")) == 1

    reopened = TrackingStore(tmp_path / "tracking.db")
    rows = reopened.list_next_open_intents(
        runtime_id="paper:p1:s1", target_date=datetime.date(2026, 10, 28)
    )
    assert rows[0]["status"] == "pending"
    assert rows[0]["args"] == ["000001.SZ", 10000]


@pytest.mark.asyncio
async def test_backtest_next_open_proxy_flushes_at_following_open():
    calls = []

    class _Broker:
        async def buy_amount(self, *args, **kwargs):
            calls.append((args, kwargs))

    proxy = _BacktestNextOpenBrokerProxy(_Broker())
    result = await proxy.buy_amount("000001.SZ", 10000, order_time="signal")
    assert result.trades == []
    assert calls == []

    open_time = datetime.datetime(2026, 10, 28, 9, 30)
    await proxy.flush(open_time)
    assert calls == [(("000001.SZ", 10000), {"order_time": open_time})]


@pytest.mark.asyncio
async def test_30m_next_open_survives_restart_and_does_not_resubmit(monkeypatch, tmp_path):
    import quantide.service.strategy_runtime as runtime_module

    signal_bar = datetime.datetime(2026, 10, 27, 11, 30)
    target_bar = datetime.datetime(2026, 10, 27, 13, 0)

    class _Calendar:
        @staticmethod
        def shift(moment, offset, frame):
            assert offset == 1
            assert frame is FrameType.MIN30
            return target_bar + datetime.timedelta(minutes=30)

    store_path = tmp_path / "30m-restart.db"
    store = TrackingStore(store_path)
    monkeypatch.setattr(runtime_module, "tracking_store", store)
    monkeypatch.setattr("quantide.service.runtime_proxies.tracking_store", store)
    monkeypatch.setattr(runtime_module, "calendar", _Calendar)
    monkeypatch.setattr("quantide.service.runtime_proxies.calendar", _Calendar)
    monkeypatch.setattr("quantide.service.runtime_intents.calendar", _Calendar)

    first_proxy = NextOpenBarBrokerProxy(
        object(),
        runtime_id="paper:p1:s30",
        portfolio_id="p1",
        strategy_id="s30",
        signal_bar=signal_bar,
    )
    await first_proxy.buy_amount(
        "000001.SZ", 10000, order_time=datetime.datetime(2026, 10, 27, 11, 31)
    )

    # A restarted strategy replays the completed signal bar, but the durable
    # natural key makes the enqueue idempotent.
    reopened = TrackingStore(store_path)
    monkeypatch.setattr(runtime_module, "tracking_store", reopened)
    second_proxy = NextOpenBarBrokerProxy(
        object(),
        runtime_id="paper:p1:s30",
        portfolio_id="p1",
        strategy_id="s30",
        signal_bar=signal_bar,
    )
    await second_proxy.buy_amount(
        "000001.SZ", 10000, order_time=datetime.datetime(2026, 10, 27, 12, 1)
    )
    rows = reopened.list_next_open_intents(runtime_id="paper:p1:s30", target_bar=target_bar)
    assert len(rows) == 1
    assert rows[0]["target_bar"] == target_bar.isoformat(timespec="seconds")

    calls = []

    class _Broker:
        async def buy_amount(self, *args, **kwargs):
            calls.append((args, kwargs))
            return ExecutionResult(qt_oid="paper-order-1")

    manager = StrategyRuntimeManager()
    manager._strategy_runtimes["paper:p1:s30"] = type(
        "_Runtime",
        (),
        {
            "runtime_id": "paper:p1:s30",
            "mode": "paper",
            "status": "running",
            "interval": "30m",
            "broker": _Broker(),
            "strategy_id": "s30",
        },
    )()

    assert await manager.process_next_open_30m_intents("paper:p1:s30", target_bar) == 1
    assert calls == [
        (
            ("000001.SZ", 10000),
            {"order_time": target_bar},
        )
    ]

    # A new manager/process sees the processed SQLite row and submits nothing.
    restarted_manager = StrategyRuntimeManager()
    restarted_manager._strategy_runtimes["paper:p1:s30"] = manager._strategy_runtimes[
        "paper:p1:s30"
    ]
    assert await restarted_manager.process_next_open_30m_intents("paper:p1:s30", target_bar) == 0
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_30m_restart_fails_closed_for_ambiguous_inflight_intent(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import quantide.service.strategy_runtime as runtime_module

    store = TrackingStore(tmp_path / "30m-inflight.db")
    monkeypatch.setattr(runtime_module, "tracking_store", store)
    monkeypatch.setattr("quantide.service.runtime_proxies.tracking_store", store)
    intent = store.enqueue_next_open_intent(
        runtime_id="paper:p1:s30",
        portfolio_id="p1",
        strategy_id="s30",
        signal_date=datetime.date(2026, 10, 27),
        target_date=datetime.date(2026, 10, 27),
        signal_bar=datetime.datetime(2026, 10, 27, 11, 30),
        target_bar=datetime.datetime(2026, 10, 27, 13, 0),
        method="buy_amount",
        args=["000001.SZ", 10000],
        kwargs={},
        intent_key="30m-inflight",
    )
    assert store.claim_next_open_intent(intent["intent_id"])["status"] == "processing"

    calls = []

    class _Broker:
        async def buy_amount(self, *args, **kwargs):
            calls.append((args, kwargs))

    manager = StrategyRuntimeManager()
    manager._strategy_runtimes["paper:p1:s30"] = SimpleNamespace(
        runtime_id="paper:p1:s30",
        mode="paper",
        status="running",
        interval="30m",
        broker=_Broker(),
        strategy_id="s30",
    )
    with pytest.raises(RuntimeError, match="processing intent"):
        await manager.process_next_open_30m_intents(
            "paper:p1:s30", datetime.datetime(2026, 10, 27, 13, 0)
        )
    assert calls == []


def test_30m_next_open_target_skips_lunch_and_overnight(monkeypatch):
    from quantide.service import strategy_runtime as runtime_module

    boundaries = {
        datetime.datetime(2026, 10, 27, 11, 30): datetime.datetime(2026, 10, 27, 13, 30),
        datetime.datetime(2026, 10, 27, 15, 0): datetime.datetime(2026, 10, 28, 10, 0),
    }

    class _Calendar:
        @staticmethod
        def shift(moment, offset, frame):
            assert offset == 1
            assert frame is FrameType.MIN30
            return boundaries[moment]

    monkeypatch.setattr(runtime_module, "calendar", _Calendar)
    monkeypatch.setattr("quantide.service.runtime_proxies.calendar", _Calendar)
    monkeypatch.setattr("quantide.service.runtime_intents.calendar", _Calendar)
    assert StrategyRuntimeManager._next_eligible_30m_bar(
        datetime.datetime(2026, 10, 27, 11, 30)
    ) == datetime.datetime(2026, 10, 27, 13, 0)
    assert StrategyRuntimeManager._next_eligible_30m_bar(
        datetime.datetime(2026, 10, 27, 15, 0)
    ) == datetime.datetime(2026, 10, 28, 9, 30)
