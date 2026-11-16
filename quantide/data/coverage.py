"""Coverage contracts for date-based historical source responses."""

import datetime
from collections.abc import Iterable
from typing import Protocol

import pandas as pd
import polars as pl

from quantide.core.enums import FrameType


class _SessionCalendar(Protocol):
    def get_frames(
        self, start: datetime.date, end: datetime.date, frame_type: FrameType
    ) -> list[datetime.date | datetime.datetime]: ...


def trading_sessions(
    calendar: _SessionCalendar, start: datetime.date, end: datetime.date
) -> list[datetime.date]:
    """Request only sessions within the source interval, excluding calendar floor carry-in."""
    return [day for day in calendar.get_frames(start, end, FrameType.DAY) if start <= day <= end]


def require_date_coverage(
    frame: pd.DataFrame | pl.DataFrame | None, dates: Iterable[datetime.date], dataset: str
) -> None:
    """Reject empty or partial responses before recording a successful checkpoint."""
    expected = {day.date() if isinstance(day, datetime.datetime) else day for day in dates}
    if not expected:
        return
    if frame is None or len(frame) == 0:
        raise RuntimeError(f"{dataset} returned no coverage for requested sessions")
    values = frame["date"].to_list() if isinstance(frame, pl.DataFrame) else list(frame["date"])
    actual = set(pd.to_datetime(values, errors="raise").date)
    missing = sorted(expected - actual)
    if missing:
        raise RuntimeError(f"{dataset} missing requested sessions: {missing[:5]}")
