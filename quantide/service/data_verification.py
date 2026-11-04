"""Offline daily-bar verification against calendar and security listing boundaries."""

import datetime
from typing import Any, cast

import polars as pl

from quantide.core.market_time import market_today
from quantide.data.coverage import _SessionCalendar, trading_sessions


def verify_daily_history(
    start: datetime.date, end: datetime.date, assets: list[str] | None = None
) -> dict[str, Any]:
    """Report actual missing or invalid rows; absence is never proof of suspension."""
    from quantide.data.models.calendar import calendar
    from quantide.data.models.daily_bars import daily_bars
    from quantide.service.minute_backfill import _asset_lifespans

    end = min(end, market_today())
    if start > end:
        raise ValueError("校验范围没有已发生的交易日")
    if start < calendar.epoch or end > calendar.end:
        raise ValueError("交易日历未覆盖校验区间，请先同步日历")
    lifespans = _asset_lifespans()
    assets = assets or list(lifespans)
    if not assets:
        raise ValueError("证券列表为空，无法校验覆盖")
    frame = cast(
        pl.DataFrame, daily_bars.get_bars_in_range(start, end, assets=assets, eager_mode=True)
    )
    coverage, invalid = _daily_coverage(frame)
    missing, examples = _missing_daily_sessions(assets, lifespans, coverage, start, end, calendar)
    return {"assets": len(assets), "missing": missing, "examples": examples, "invalid": invalid}


def _daily_coverage(frame: pl.DataFrame | None) -> tuple[dict[str, set[datetime.date]], int]:
    if frame is None or frame.is_empty():
        return {}, 0
    rows = frame.select("asset", pl.col("date").cast(pl.Date)).unique()
    coverage: dict[str, set[datetime.date]] = {}
    for asset, day in rows.iter_rows():
        coverage.setdefault(asset, set()).add(day)
    valid = pl.all_horizontal(
        [pl.col(key).is_finite() & (pl.col(key) > 0) for key in ("open", "high", "low", "close")]
    )
    invalid = frame.filter(~valid.fill_null(False)).height
    duplicates = frame.height - rows.height
    return coverage, invalid + duplicates


def _missing_daily_sessions(
    assets: list[str],
    lifespans: dict[str, dict[str, Any]],
    coverage: dict[str, set[datetime.date]],
    start: datetime.date,
    end: datetime.date,
    calendar: _SessionCalendar,
) -> tuple[int, list[str]]:
    from quantide.service.minute_backfill import _date_value

    missing = 0
    examples: list[str] = []
    for asset in assets:
        metadata = lifespans.get(asset, {})
        first = max(start, _date_value(metadata.get("list_date")) or start)
        last = min(end, _date_value(metadata.get("delist_date")) or end)
        if first > last:
            continue
        absent = set(trading_sessions(calendar, first, last)) - coverage.get(asset, set())
        missing += len(absent)
        examples.extend(f"{asset}: {day}" for day in sorted(absent)[: max(0, 5 - len(examples))])
    return missing, examples
