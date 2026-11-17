"""Shared interior cutoff selection for deterministic audit sampling."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from typing import Any


def _as_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    return value if isinstance(value, dt.date) else None


def interior_cutoffs(values: Iterable[Any], count: int = 3) -> tuple[dt.date, ...]:
    """Pick evenly spaced dates strictly inside the available range."""
    dates = [day for value in values if (day := _as_date(value)) is not None]
    dates = sorted(set(dates))
    if len(dates) < 2:
        return ()
    chosen: list[dt.date] = []
    for index in range(1, count + 1):
        position = min(int(len(dates) * index / (count + 1)), len(dates) - 2)
        chosen.append(dates[max(position, 0)])
    return tuple(dict.fromkeys(chosen))


__all__ = ["interior_cutoffs"]
