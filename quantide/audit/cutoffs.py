"""Shared interior cutoff selection for deterministic audit sampling."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from typing import Any


def _as_value(value: Any) -> dt.date | dt.datetime | None:
    if isinstance(value, (dt.datetime, dt.date)):
        return value
    return None


def interior_cutoffs(values: Iterable[Any], count: int = 3) -> tuple[Any, ...]:
    """Pick evenly spaced native-precision cutoffs strictly inside the range."""
    dates = [day for value in values if (day := _as_value(value)) is not None]
    dates = sorted(set(dates))
    if len(dates) < 2:
        return ()
    chosen: list[Any] = []
    for index in range(1, count + 1):
        position = min(int(len(dates) * index / (count + 1)), len(dates) - 2)
        chosen.append(dates[max(position, 0)])
    return tuple(dict.fromkeys(chosen))


__all__ = ["interior_cutoffs"]
