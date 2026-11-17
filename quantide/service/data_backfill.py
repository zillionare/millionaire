"""Prioritized historical backfill planning from ``epoch`` to the latest session."""

from __future__ import annotations

import datetime
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from quantide.data.fetchers.budget import DataSourceErrorKind, classify_source_error, retryable


@dataclass(frozen=True)
class BackfillWindow:
    """One bounded sync request ordered by usefulness."""

    start: datetime.date
    end: datetime.date
    phase: str
    datasets: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"{self.phase}:{self.start.isoformat()}~{self.end.isoformat()}"


def _month_key(day: datetime.date) -> tuple[int, int]:
    return day.year, day.month


def _group_by_month(days: Iterable[datetime.date]) -> dict[tuple[int, int], list[datetime.date]]:
    groups: dict[tuple[int, int], list[datetime.date]] = defaultdict(list)
    for day in sorted(set(days)):
        groups[_month_key(day)].append(day)
    return groups


def _window_datasets(
    dataset_days: Mapping[str, set[datetime.date]],
    start: datetime.date,
    end: datetime.date,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            dataset
            for dataset, covered in dataset_days.items()
            if any(start <= day <= end for day in covered)
        )
    )


def _windows_for_months(
    months: Mapping[tuple[int, int], list[datetime.date]],
    dataset_days: Mapping[str, set[datetime.date]],
    phase: str,
    *,
    reverse: bool = False,
) -> list[BackfillWindow]:
    windows: list[BackfillWindow] = []
    for key in sorted(months, reverse=reverse):
        days = months[key]
        start, end = min(days), max(days)
        windows.append(
            BackfillWindow(start, end, phase, _window_datasets(dataset_days, start, end))
        )
    return windows


def plan_backfill(
    epoch: datetime.date,
    end: datetime.date,
    missing_by_dataset: Mapping[str, Iterable[datetime.date]],
    *,
    available_end: datetime.date | None = None,
) -> tuple[BackfillWindow, ...]:
    """Plan tail first, then newest historical gaps back toward ``epoch``.

    Windows are month-bounded so a task can checkpoint and resume without
    re-downloading a multi-year range.  ``available_end`` is the newest locally
    available session; missing sessions after it are tail work.
    """
    if end < epoch:
        return ()
    dataset_days: dict[str, set[datetime.date]] = {}
    for dataset, days in missing_by_dataset.items():
        normalized = {day for day in days if epoch <= day <= end}
        if normalized:
            dataset_days[dataset] = normalized
    if not dataset_days:
        return ()
    all_missing = set().union(*dataset_days.values())
    tail_days = {day for day in all_missing if available_end is not None and day > available_end}
    historical_days = all_missing - tail_days
    return tuple(
        _windows_for_months(_group_by_month(tail_days), dataset_days, "tail")
        + _windows_for_months(
            _group_by_month(historical_days),
            dataset_days,
            "historical",
            reverse=True,
        )
    )


def classify_backfill_error(error: BaseException | str) -> DataSourceErrorKind:
    """Expose the shared classifier for maintenance and tests."""
    return classify_source_error(error)


def should_retry_gap(error: BaseException | str) -> bool:
    """Return whether the source failure is temporary rather than unfillable."""
    return retryable(classify_backfill_error(error))


__all__ = [
    "BackfillWindow",
    "classify_backfill_error",
    "plan_backfill",
    "should_retry_gap",
]
