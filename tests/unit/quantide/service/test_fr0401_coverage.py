"""FR-0401 coverage tests for service strategy runtime and runner behavior."""

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantide.core.enums import BrokerKind, FrameType
from quantide.core.runtime.clock_bridge import BacktestClockAdapter
from quantide.service.registry import BrokerRegistry
from quantide.service.runner import BacktestRunner
from quantide.service.strategy_runtime import StrategyRuntimeManager


@pytest.fixture
def lifecycle_recorder() -> list[str]:
    """FR-0401 AC-6: provide an isolated BacktestRunner lifecycle call record."""
    return []


def test_registry_replaces_registration_and_reassigns_default() -> None:
    """FR-0401 AC-4: registry keys brokers by kind and portfolio, with a valid default."""
    # BrokerRegistry is a process-wide singleton. Snapshot/restore state
    # so this test does not leak registrations into later tests.
    registry = BrokerRegistry()
    saved_brokers = dict(registry._brokers)
    saved_default = registry._default
    try:
        registry._brokers.clear()
        registry._default = None
        first, replacement, second = object(), object(), object()

        registry.register(BrokerKind.BACKTEST, "first", first)
        registry.register(BrokerKind.BACKTEST, "first", replacement)
        registry.register(BrokerKind.SIMULATION, "second", second)
        registry.unregister(BrokerKind.BACKTEST, "first")

        assert registry.get(BrokerKind.BACKTEST, "first") is None
        assert registry.get(BrokerKind.SIMULATION, "second") is second
        assert registry.get_default() == (BrokerKind.SIMULATION.value, "second")
    finally:
        # Restore the singleton to the state we found it in.
        registry._brokers.clear()
        registry._brokers.update(saved_brokers)
        registry._default = saved_default


def test_backtest_runtime_completes_and_is_removed(monkeypatch, tmp_path) -> None:
    """FR-0401 AC-5: a backtest run exposes its finished status before removal."""
    manager = StrategyRuntimeManager()
    monkeypatch.setattr(manager, "_state_file", lambda: tmp_path / "runtime.json")

    manager.create_backtest_runtime(
        portfolio_id="bt-1",
        strategy_name="Demo",
        config={},
        interval="1d",
        start_date="2024-01-02",
        end_date="2024-01-02",
        initial_cash=1000,
    )
    manager.complete_backtest_runtime("bt-1")

    assert manager.get_backtest_run("bt-1").status == "finished"
    manager.remove_backtest_run("bt-1")
    assert manager.get_backtest_run("bt-1") is None


@pytest.mark.asyncio
async def test_runner_calls_one_day_lifecycle_in_order(
    monkeypatch, lifecycle_recorder
) -> None:
    """FR-0401 AC-6: BacktestClockAdapter drives start, open, bar, close, and stop in order."""
    day = datetime.date(2024, 1, 2)
    clock = BacktestClockAdapter()
    monkeypatch.setattr(clock, "iter_frames", lambda *_: [day])
    calendar = MagicMock()
    calendar.ceiling.return_value = day
    calendar.floor.return_value = day
    calendar.replace_time.side_effect = lambda date, hour, minute: datetime.datetime(
        date.year, date.month, date.day, hour, minute
    )
    monkeypatch.setattr("quantide.service.runner.calendar", calendar)
    broker = MagicMock(positions={})
    broker.stop_backtest = AsyncMock()
    monkeypatch.setattr("quantide.service.runner.BacktestBroker", lambda **_: broker)
    monkeypatch.setattr("quantide.service.runner.record_backtest_log", lambda **_: None)
    monkeypatch.setattr("quantide.service.runner.metrics", lambda *_1, **_2: None)

    strategy = MagicMock()
    strategy.init = AsyncMock(side_effect=lambda: lifecycle_recorder.append("init"))
    strategy.on_start = AsyncMock(side_effect=lambda: lifecycle_recorder.append("start"))
    strategy.on_day_open = AsyncMock(side_effect=lambda _: lifecycle_recorder.append("open"))
    strategy.on_bar = AsyncMock(side_effect=lambda *_: lifecycle_recorder.append("bar"))
    strategy.on_day_close = AsyncMock(side_effect=lambda _: lifecycle_recorder.append("close"))
    strategy.on_stop = AsyncMock(side_effect=lambda: lifecycle_recorder.append("stop"))
    strategy._current_time = None
    strategy_cls = MagicMock(return_value=strategy)
    strategy_cls.__name__ = "RecordedStrategy"

    await BacktestRunner(clock=clock).run(strategy_cls, {}, day, day, FrameType.DAY)

    assert lifecycle_recorder == ["init", "start", "open", "bar", "close", "stop"]
    broker.stop_backtest.assert_awaited_once()
