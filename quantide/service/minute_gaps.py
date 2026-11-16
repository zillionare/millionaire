"""Find internal minute-history gaps using stored bars and explicit suspension evidence."""

from __future__ import annotations

import datetime
import json
from collections.abc import Collection, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, cast

import polars as pl
from filelock import FileLock

from quantide.core.atomic_files import write_json
from quantide.data.coverage import _SessionCalendar, trading_sessions
from quantide.service.minute_backfill import _asset_lifespans, asset_interval

if TYPE_CHECKING:
    from quantide.data.stores.minute_bars import MinuteBarsStore


def _evidence_path(store: MinuteBarsStore) -> Path:
    return Path(str(store._store_path) + ".suspensions.json")


def suspension_evidence(store: MinuteBarsStore) -> dict[str, list[str]]:
    path = _evidence_path(store)
    if not path.exists():
        return {}
    return cast(dict[str, list[str]], json.loads(path.read_text(encoding="utf-8")))


def record_suspensions(
    store: MinuteBarsStore,
    asset: str,
    start: datetime.date,
    end: datetime.date,
    inactive: Collection[datetime.date],
) -> None:
    """Persist only source-confirmed absences, replacing the checked interval."""
    path = _evidence_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".transaction.lock", timeout=30):
        evidence = suspension_evidence(store)
        previous = {
            day
            for day in evidence.get(asset, [])
            if not start.isoformat() <= day <= end.isoformat()
        }
        evidence[asset] = sorted(previous | {day.isoformat() for day in inactive})
        write_json(path, evidence)


def _complete_sessions(
    store: MinuteBarsStore, start: datetime.date, end: datetime.date, period: int
) -> dict[str, set[datetime.date]]:
    frame = cast(pl.LazyFrame, store.get(start=start, end=end, eager_mode=False))
    if "date" not in frame.collect_schema().names():
        return {}
    times = [
        (datetime.datetime.combine(start, opening) + datetime.timedelta(minutes=offset)).time()
        for opening in (datetime.time(9, 30), datetime.time(13))
        for offset in range(period, 121, period)
    ]
    valid = pl.col("date").dt.time().is_in(times) & pl.all_horizontal(
        [pl.col(key).is_finite() & (pl.col(key) > 0) for key in ("open", "high", "low", "close")]
    )
    complete = (
        frame.group_by("asset", pl.col("date").cast(pl.Date).alias("day"))
        .agg(pl.col("date").n_unique().alias("count"), valid.all().alias("valid"))
        .filter((pl.col("count") == len(times)) & pl.col("valid"))
        .collect()
    )
    result: dict[str, set[datetime.date]] = {}
    for asset, day in complete.select("asset", "day").iter_rows():
        result.setdefault(asset, set()).add(day)
    return result


def coverage_starts(
    store: MinuteBarsStore,
    assets: Iterable[str],
    start: datetime.date,
    end: datetime.date,
    period: str | int,
) -> dict[str, datetime.date | None]:
    """Return the first missing session per asset, or None for complete history."""
    from quantide.data.models.calendar import calendar

    complete = _complete_sessions(store, start, end, int(period))
    evidence, lifespans = suspension_evidence(store), _asset_lifespans()
    result: dict[str, datetime.date | None] = {}
    for asset in assets:
        first, last = asset_interval(lifespans.get(asset, {}), start, end)
        if first > last:
            result[asset] = None
            continue
        inactive = {datetime.date.fromisoformat(day) for day in evidence.get(asset, [])}
        result[asset] = _first_missing(calendar, first, last, complete.get(asset, set()) | inactive)
    return result


def _first_missing(
    calendar: _SessionCalendar,
    start: datetime.date,
    end: datetime.date,
    covered: set[datetime.date],
) -> datetime.date | None:
    missing = set(trading_sessions(calendar, start, end)) - covered
    return min(missing) if missing else None
