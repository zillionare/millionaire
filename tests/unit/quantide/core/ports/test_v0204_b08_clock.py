"""B08-core-ports-1: Tests for quantide/core/ports/clock.py.

Target: cover the Protocol import + any helper code.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from typing import Protocol

import pytest

from quantide.core.enums import FrameType
from quantide.core.ports.clock import ClockPort


# ---------------------------------------------------------------------------
# Protocol structure
# ---------------------------------------------------------------------------


def test_clock_port_is_a_protocol():
    """ClockPort should be defined as a Protocol class."""
    from typing import Protocol as _Protocol

    assert issubclass(ClockPort, _Protocol)


def test_clock_port_has_now_method():
    """ClockPort declares now() returning datetime."""
    assert hasattr(ClockPort, "now")


def test_clock_port_has_set_now_method():
    assert hasattr(ClockPort, "set_now")


def test_clock_port_has_iter_frames_method():
    assert hasattr(ClockPort, "iter_frames")


# ---------------------------------------------------------------------------
# Concrete implementation conformance
# ---------------------------------------------------------------------------


class _ConcreteClock:
    """Minimal concrete class satisfying ClockPort Protocol."""

    def __init__(self, start: datetime.datetime):
        self._now = start

    def now(self) -> datetime.datetime:
        return self._now

    def set_now(self, tm: datetime.datetime) -> None:
        self._now = tm

    def iter_frames(
        self,
        start: datetime.date | datetime.datetime,
        end: datetime.date | datetime.datetime,
        frame_type: FrameType,
    ) -> Iterable[datetime.date | datetime.datetime]:
        if not isinstance(start, datetime.datetime):
            start = datetime.datetime.combine(start, datetime.time())
        if not isinstance(end, datetime.datetime):
            end = datetime.datetime.combine(end, datetime.time())
        cur = start
        while cur <= end:
            yield cur
            cur += datetime.timedelta(days=1)


def test_concrete_clock_satisfies_protocol():
    """A class implementing the required methods has matching attributes."""
    clock = _ConcreteClock(datetime.datetime(2024, 1, 1))
    # Protocol structural check (without @runtime_checkable).
    assert callable(getattr(clock, "now", None))
    assert callable(getattr(clock, "set_now", None))
    assert callable(getattr(clock, "iter_frames", None))


def test_concrete_clock_now_returns_datetime():
    fixed = datetime.datetime(2024, 1, 1, 10, 0)
    clock = _ConcreteClock(fixed)
    assert clock.now() == fixed


def test_concrete_clock_set_now_updates_time():
    clock = _ConcreteClock(datetime.datetime(2024, 1, 1))
    new = datetime.datetime(2024, 6, 1, 12, 0)
    clock.set_now(new)
    assert clock.now() == new


def test_concrete_clock_iter_frames_yields_dates():
    clock = _ConcreteClock(datetime.datetime(2024, 1, 1))
    frames = list(
        clock.iter_frames(
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 3),
            FrameType.DAY,
        )
    )
    assert len(frames) == 3


def test_concrete_clock_iter_frames_handles_datetime_inputs():
    clock = _ConcreteClock(datetime.datetime(2024, 1, 1))
    frames = list(
        clock.iter_frames(
            datetime.datetime(2024, 1, 1),
            datetime.datetime(2024, 1, 2),
            FrameType.DAY,
        )
    )
    assert len(frames) == 2
