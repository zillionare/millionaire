"""Authoritative monthly bar aggregation and 3/12-month crossover signals."""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from quantide.config.settings import get_timezone

REQUIRED_COLUMNS = ("date", "asset", "open", "high", "low", "close")


@dataclass(frozen=True)
class MonthlyBar:
    asset: str
    month: dt.date
    start_date: dt.date
    end_date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    closed: bool
    available_at: dt.datetime
    trade_days: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "month": self.month.isoformat(),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "amount": self.amount,
            "closed": self.closed,
            "available_at": self.available_at.isoformat(),
            "trade_days": self.trade_days,
        }


@dataclass(frozen=True)
class MonthlySeries:
    asset: str
    closed: tuple[MonthlyBar, ...]
    forming: tuple[MonthlyBar, ...] = ()
    incomplete: tuple[MonthlyBar, ...] = ()
    diagnostics: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MonthlySignal:
    asset: str
    signal_date: dt.date
    execute_date: dt.date
    direction: str
    fast: float
    slow: float
    index: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "signal_date": self.signal_date.isoformat(),
            "execute_date": self.execute_date.isoformat(),
            "direction": self.direction,
            "fast": self.fast,
            "slow": self.slow,
            "index": self.index,
        }


def monthly_grid(calendar: Iterable[dt.date]) -> dict[tuple[int, int], dt.date]:
    """Return the actual last trading day for every closed market month."""
    result: dict[tuple[int, int], dt.date] = {}
    for day in sorted(calendar):
        result[(day.year, day.month)] = day
    return result


def _month_key(value: dt.date) -> tuple[int, int]:
    return (value.year, value.month)


def _finite(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("monthly aggregate is not finite")
    return number


def _aggregate_rows(asset: str, month: dt.date, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "asset": asset,
        "month": month.replace(day=1),
        "start_date": rows[0]["date"],
        "end_date": rows[-1]["date"],
        "open": _finite(rows[0]["open"]),
        "high": max(_finite(row["high"]) for row in rows),
        "low": min(_finite(row["low"]) for row in rows),
        "close": _finite(rows[-1]["close"]),
        "volume": sum(_finite(row.get("volume") or 0.0) for row in rows),
        "amount": sum(_finite(row.get("amount") or 0.0) for row in rows),
        "trade_days": len(rows),
    }


def _rows_by_asset(daily: pl.DataFrame, cutoff: dt.date) -> dict[str, list[dict[str, Any]]]:
    series: dict[str, list[dict[str, Any]]] = {}
    for row in daily.sort(["asset", "date"]).iter_rows(named=True):
        if row["date"] <= cutoff:
            series.setdefault(str(row["asset"]), []).append(row)
    return series


def _rows_by_month(rows: list[dict[str, Any]]) -> dict[tuple[int, int], list[dict[str, Any]]]:
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(_month_key(row["date"]), []).append(row)
    return grouped


def _month_bar(
    asset: str,
    key: tuple[int, int],
    month_rows: list[dict[str, Any]],
    month_last: dt.date,
    cutoff: dt.date,
) -> tuple[MonthlyBar, str]:
    month_rows.sort(key=lambda item: item["date"])
    data = _aggregate_rows(asset, month_rows[0]["date"], month_rows)
    timezone = get_timezone()
    market_closed = month_last <= cutoff
    available = (
        dt.datetime.combine(month_last, dt.time(15, 0), tzinfo=timezone)
        if market_closed
        else dt.datetime.combine(cutoff, dt.time(15, 0), tzinfo=timezone)
    )
    closed = bool(market_closed and data["end_date"] == month_last)
    bar = MonthlyBar(closed=closed, available_at=available, **data)
    diagnostic = (
        ""
        if closed or not market_closed
        else f"{asset} {key}: missing month-end {month_last} (last row {data['end_date']})"
    )
    return bar, diagnostic


def _asset_series(
    asset: str,
    rows: list[dict[str, Any]],
    grid: dict[tuple[int, int], dt.date],
    cutoff: dt.date,
) -> MonthlySeries:
    closed: list[MonthlyBar] = []
    forming: list[MonthlyBar] = []
    incomplete: list[MonthlyBar] = []
    diagnostics: list[str] = []
    for key, month_rows in sorted(_rows_by_month(rows).items()):
        month_last = grid.get(key)
        if month_last is None:
            diagnostics.append(f"{asset} {key}: month absent from authoritative calendar")
            continue
        bar, diagnostic = _month_bar(asset, key, month_rows, month_last, cutoff)
        if diagnostic:
            diagnostics.append(diagnostic)
        bucket = closed if bar.closed else incomplete if month_last <= cutoff else forming
        bucket.append(bar)
    return MonthlySeries(
        asset, tuple(closed), tuple(forming), tuple(incomplete), tuple(diagnostics)
    )


def aggregate_monthly(
    daily: pl.DataFrame,
    calendar: Iterable[dt.date],
    *,
    as_of: dt.date | None = None,
) -> dict[str, MonthlySeries]:
    """Aggregate daily bars by asset/month with forming and incomplete states."""
    missing = set(REQUIRED_COLUMNS) - set(daily.columns)
    if missing:
        raise ValueError(f"daily panel missing columns: {sorted(missing)}")
    grid = monthly_grid(calendar)
    cutoff = as_of or daily["date"].max()
    if not isinstance(cutoff, dt.date):
        raise ValueError("monthly aggregation needs an as_of date")
    return {
        asset: _asset_series(asset, rows, grid, cutoff)
        for asset, rows in _rows_by_asset(daily, cutoff).items()
    }


def _next_trade_day(calendar: Iterable[dt.date], after: dt.date) -> dt.date | None:
    for day in sorted(calendar):
        if day > after:
            return day
    return None


def monthly_ma_signals(
    series: MonthlySeries,
    calendar: Iterable[dt.date],
    *,
    short: int = 3,
    long: int = 12,
) -> list[MonthlySignal]:
    """Return 3/12 crossovers from closed bars; at least long+1 closes are required."""
    if short < 1 or long < short + 1:
        raise ValueError("monthly windows require long >= short + 1")
    bars = series.closed
    if len(bars) < long + 1:
        return []
    closes = [bar.close for bar in bars]
    signals: list[MonthlySignal] = []
    for index in range(long, len(bars)):
        fast_now = sum(closes[index - short + 1 : index + 1]) / short
        slow_now = sum(closes[index - long + 1 : index + 1]) / long
        fast_prev = sum(closes[index - short : index]) / short
        slow_prev = sum(closes[index - long : index]) / long
        direction = ""
        if fast_prev <= slow_prev and fast_now > slow_now:
            direction = "buy"
        elif fast_prev >= slow_prev and fast_now < slow_now:
            direction = "sell"
        if not direction:
            continue
        execute = _next_trade_day(calendar, bars[index].end_date)
        if execute is None:
            continue
        signals.append(
            MonthlySignal(
                series.asset,
                bars[index].end_date,
                execute,
                direction,
                fast_now,
                slow_now,
                index,
            )
        )
    return signals


def monthly_history(
    asset: str,
    count: int,
    end: dt.date,
    calendar: Iterable[dt.date],
    *,
    include_forming: bool = False,
) -> pl.DataFrame:
    """Build monthly OHLCV from the connected daily store for strategy history."""
    from quantide.data.models.daily_bars import daily_bars

    full_calendar = tuple(sorted(calendar))
    calendar_days = tuple(day for day in full_calendar if day <= end)
    if not calendar_days:
        return pl.DataFrame()
    start = calendar_days[max(0, len(calendar_days) - count * 35)]
    daily = daily_bars.get_bars_in_range(start, end, assets=[asset], adjust=None, eager_mode=True)
    if daily.is_empty():
        return pl.DataFrame()
    series = aggregate_monthly(daily, full_calendar, as_of=end).get(asset)
    if series is None:
        return pl.DataFrame()
    bars = list(series.closed) + (list(series.forming) if include_forming else [])
    selected = bars[-count:]
    return pl.DataFrame(
        [
            {
                "date": bar.end_date,
                "asset": bar.asset,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "amount": bar.amount,
                "closed": bar.closed,
                "available_at": bar.available_at,
            }
            for bar in selected
        ]
    )
