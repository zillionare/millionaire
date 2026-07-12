"""v0.2-003 FR-0202 clock adapter contract tests."""

import datetime as dt

import pytest

from quantide.core.enums import FrameType
from quantide.core.runtime import clock_bridge
from quantide.core.runtime.clock_bridge import BacktestClockAdapter, SystemClockAdapter


def test_backtest_clock_is_instance_local_and_returns_the_injected_time():
    """FR-0202 AC-1: set_now makes only that backtest clock deterministic."""
    first, second = BacktestClockAdapter(), BacktestClockAdapter()
    instant = dt.datetime(2026, 7, 10, 9, 30)
    first.set_now(instant)

    assert first.now() is instant
    assert second.now() != instant


def test_system_clock_rejects_mutation_and_adapters_delegate_frames(monkeypatch):
    """FR-0202 AC-2/AC-3: system time is immutable and calendar inputs pass unchanged."""
    calls = []
    sentinel = ("frame",)

    class Calendar:
        def get_frames(self, start, end, frame_type):
            calls.append((start, end, frame_type))
            return sentinel

    monkeypatch.setattr(clock_bridge, "calendar", Calendar())
    start, end = dt.date(2026, 7, 1), dt.date(2026, 7, 10)
    with pytest.raises(RuntimeError, match="does not support"):
        SystemClockAdapter().set_now(dt.datetime(2026, 7, 10))

    assert SystemClockAdapter().iter_frames(start, end, FrameType.DAY) is sentinel
    assert BacktestClockAdapter().iter_frames(start, end, FrameType.DAY) is sentinel
    assert calls == [(start, end, FrameType.DAY), (start, end, FrameType.DAY)]
