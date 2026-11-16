"""Versioned daily equal-weight factor research statistics.

The calendar defaults to the dates present in the panel; pass an authoritative
calendar when the panel can omit an entire market session. ``available_at`` is
the availability date of a row and its prices when present. A factor row is only
eligible when it is available by its entry day, and labels are only eligible
when the entry and exit prices are available by the evaluation cutoff.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from quantide.factors.alphatest import MIN_CROSS_SECTION

#: 统计与标签口径版本：源码内容哈希，口径变化时缓存与跟踪快照自动失效。
STATISTICS_VERSION = hashlib.sha1(
    Path(__file__).read_bytes() + Path(__file__).with_name("alphatest.py").read_bytes()
).hexdigest()[:12]


def _serialize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


class _Serializable:
    def as_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))  # type: ignore[call-overload,no-any-return]


@dataclass(frozen=True)
class DailyIC(_Serializable):
    date: dt.date
    ic: float
    n_samples: int


@dataclass(frozen=True)
class ICSummary(_Serializable):
    mean: float | None
    t_naive: float | None
    t_status: str
    n_days: int
    std: float | None = None
    icir: float | None = None
    annualized_icir: float | None = None
    annualization: int = 252


@dataclass(frozen=True)
class Bucket(_Serializable):
    bucket: int
    mean_forward: float | None
    n_days: int
    n_samples: int
    status: str


@dataclass(frozen=True)
class DecileProfile(_Serializable):
    buckets: list[Bucket]
    d1_mean_common: float | None
    d10_mean_common: float | None
    d1_minus_d10: float | None
    n_common_days: int
    status: str
    weighting: str = "equal_day"


@dataclass(frozen=True)
class DailyPearson(_Serializable):
    date: Any
    ic: float
    n_samples: int


@dataclass(frozen=True)
class HorizonDiagnostics(_Serializable):
    requested_start: dt.date
    requested_end: dt.date
    actual_start: dt.date | None
    actual_end: dt.date | None
    as_of_date: dt.date | None
    latest_valid_signal_date: dt.date | None
    coverage_start: dt.date | None
    coverage_end: dt.date | None
    data_cutoff: dt.date
    min_cross_section: int
    n_rows: int
    n_valid_pairs: int
    n_valid_days: int
    exclusion_counts: dict[str, int]


@dataclass(frozen=True)
class HorizonRequest:
    factor: str
    holding_days: int
    start: dt.date
    end: dt.date
    data_cutoff: dt.date
    price: str = "open"
    min_cross_section: int = MIN_CROSS_SECTION
    calendar: tuple[Any, ...] | None = None
    interval: str = "1d"
    holding_bars: int | None = None
    annualization: int = 252

    @property
    def effective_holding(self) -> int:
        if self.interval not in {"1d", "30m", "1M", "1w"}:
            raise ValueError(f"unsupported research interval: {self.interval}")
        if self.interval == "1d":
            if self.holding_bars is not None and self.holding_bars != self.holding_days:
                raise ValueError("holding_bars conflicts with holding_days for 1d")
            return self.holding_days
        if self.holding_bars is None or self.holding_bars < 1:
            raise ValueError("non-daily intervals require explicit holding_bars")
        return self.holding_bars


@dataclass(frozen=True)
class HorizonResult(_Serializable):
    factor: str
    holding_days: int
    price: str
    diagnostics: HorizonDiagnostics
    daily_ic: list[DailyIC]
    rank_ic: ICSummary
    deciles: DecileProfile
    statistics_version: str = STATISTICS_VERSION
    pearson_daily: list[DailyPearson] = field(default_factory=list)
    pearson_ic: ICSummary = field(
        default_factory=lambda: ICSummary(None, None, "insufficient_days", 0)
    )
    interval: str = "1d"
    holding_bars: int | None = None


@dataclass(frozen=True)
class CommonCohort(_Serializable):
    dates: list[Any]
    n_days: int
    per_horizon: dict[int, ICSummary]
    status: str
    pearson_per_horizon: dict[int, ICSummary] = field(default_factory=dict)


@dataclass(frozen=True)
class _PreparedPanel:
    rows: list[dict[str, Any]]
    days: list[dt.date]
    positions: dict[dt.date, int]
    indexed: dict[tuple[str, dt.date], dict[str, Any]]


def summarize_ic(values: list[float], annualization: int = 252) -> ICSummary:
    if annualization < 1:
        raise ValueError("annualization must be positive")
    if not values:
        return ICSummary(None, None, "insufficient_days", 0, annualization=annualization)
    mean = float(np.mean(values))
    if len(values) < 2:
        return ICSummary(mean, None, "insufficient_days", len(values), annualization=annualization)
    std = float(np.std(values, ddof=1))
    if std == 0:
        return ICSummary(
            mean, None, "zero_variance", len(values), std=0.0, annualization=annualization
        )
    value = mean / (std / math.sqrt(len(values)))
    icir = mean / std
    annualized = icir * math.sqrt(annualization)
    finite = math.isfinite(value)
    return ICSummary(
        mean,
        value if finite else None,
        "ok" if finite else "non_finite",
        len(values),
        std=std,
        icir=icir if math.isfinite(icir) else None,
        annualized_icir=annualized if math.isfinite(annualized) else None,
        annualization=annualization,
    )


def _ranks(values: np.ndarray) -> np.ndarray:
    return pl.Series(values).rank(method="average").to_numpy()


def daily_rank_ic(
    frame: pl.DataFrame,
    factor: str,
    min_cross_section: int = MIN_CROSS_SECTION,
    forward_col: str = "forward",
) -> list[DailyIC]:
    if min_cross_section < 2:
        raise ValueError("min_cross_section must be at least 2")
    points: list[DailyIC] = []
    for (day,), group in frame.sort("date").group_by("date", maintain_order=True):
        x = group[factor].cast(pl.Float64).to_numpy()
        y = group[forward_col].cast(pl.Float64).to_numpy()
        mask = np.isfinite(x) & np.isfinite(y)
        x, y = x[mask], y[mask]
        if len(x) < min_cross_section:
            continue
        rx, ry = _ranks(x), _ranks(y)
        if np.std(rx) == 0 or np.std(ry) == 0:
            continue
        value = float(np.corrcoef(rx, ry)[0, 1])
        if math.isfinite(value):
            points.append(DailyIC(day, value, len(x)))
    return points


def daily_pearson_ic(
    frame: pl.DataFrame,
    factor: str,
    min_cross_section: int = MIN_CROSS_SECTION,
    forward_col: str = "forward",
) -> list[DailyPearson]:
    if min_cross_section < 2:
        raise ValueError("min_cross_section must be at least 2")
    points: list[DailyPearson] = []
    for (day,), group in frame.sort("date").group_by("date", maintain_order=True):
        x = group[factor].cast(pl.Float64).to_numpy()
        y = group[forward_col].cast(pl.Float64).to_numpy()
        mask = np.isfinite(x) & np.isfinite(y)
        x, y = x[mask], y[mask]
        if len(x) < min_cross_section or np.std(x) == 0 or np.std(y) == 0:
            continue
        value = float(np.corrcoef(x, y)[0, 1])
        if math.isfinite(value):
            points.append(DailyPearson(day, value, len(x)))
    return points


def _daily_bucket_means(
    x: np.ndarray, y: np.ndarray, min_cross_section: int
) -> tuple[dict[int, float], dict[int, int]] | None:
    if len(x) < min_cross_section:
        return None
    labels = np.floor((_ranks(x) - 1) / len(x) * 10).astype(int)
    daily: dict[int, float] = {}
    daily_counts: dict[int, int] = {}
    for bucket in range(10):
        picked = y[labels == bucket]
        if len(picked):
            daily[bucket] = float(np.mean(picked))
            daily_counts[bucket] = len(picked)
    return (daily, daily_counts) if daily else None


def _build_buckets(means: list[list[float]], counts: list[int]) -> list[Bucket]:
    return [
        Bucket(
            i + 1,
            float(np.mean(values)) if values else None,
            len(values),
            counts[i],
            "ok" if values else "empty",
        )
        for i, values in enumerate(means)
    ]


def _day_decile_means(
    group: pl.DataFrame, factor: str, forward_col: str, min_cross_section: int
) -> tuple[dict[int, float], dict[int, int]] | None:
    x = group[factor].cast(pl.Float64).to_numpy()
    y = group[forward_col].cast(pl.Float64).to_numpy()
    mask = np.isfinite(x) & np.isfinite(y)
    return _daily_bucket_means(x[mask], y[mask], min_cross_section)


def _collect_deciles(
    frame: pl.DataFrame, factor: str, min_cross_section: int, forward_col: str = "forward"
) -> tuple[list[list[float]], list[int], list[tuple[float, float]]]:
    means: list[list[float]] = [[] for _ in range(10)]
    counts = [0] * 10
    endpoints: list[tuple[float, float]] = []
    for _, group in frame.sort("date").group_by("date", maintain_order=True):
        daily = _day_decile_means(group, factor, forward_col, min_cross_section)
        if daily is None:
            continue
        bucket_means, bucket_counts = daily
        for bucket, value in bucket_means.items():
            means[bucket].append(value)
            counts[bucket] += bucket_counts[bucket]
        if 0 in bucket_means and 9 in bucket_means:
            endpoints.append((bucket_means[0], bucket_means[9]))
    return means, counts, endpoints


def decile_profile(
    frame: pl.DataFrame,
    factor: str,
    min_cross_section: int = MIN_CROSS_SECTION,
    forward_col: str = "forward",
) -> DecileProfile:
    if min_cross_section < 2:
        raise ValueError("min_cross_section must be at least 2")
    means, counts, endpoints = _collect_deciles(frame, factor, min_cross_section, forward_col)
    low = float(np.mean([value[0] for value in endpoints])) if endpoints else None
    high = float(np.mean([value[1] for value in endpoints])) if endpoints else None
    return DecileProfile(
        _build_buckets(means, counts),
        low,
        high,
        low - high if low is not None and high is not None else None,
        len(endpoints),
        "ok" if endpoints else "missing_endpoints",
    )


def _prepare_panel(panel: pl.DataFrame, calendar: Sequence[dt.date] | None) -> _PreparedPanel:
    rows = panel.to_dicts()
    days = sorted(set(calendar if calendar is not None else panel["date"].to_list()))
    positions = {day: index for index, day in enumerate(days)}
    indexed = {(row["asset"], row["date"]): row for row in rows}
    if len(indexed) != len(rows) or any(row["date"] not in positions for row in rows):
        raise ValueError("duplicate asset/date or panel date absent from calendar")
    return _PreparedPanel(rows, days, positions, indexed)


def _validate_request(panel: pl.DataFrame, request: HorizonRequest) -> None:
    if request.effective_holding < 1 or request.start > request.end:
        raise ValueError("invalid holding period or interval")
    if request.price not in ("open", "close"):
        raise ValueError("price must be open or close")
    if request.min_cross_section < 2:
        raise ValueError("min_cross_section must be at least 2")
    if request.factor not in panel.columns:
        raise KeyError(f"panel missing factor: {request.factor}")


def _positive_price(row: dict[str, Any], price: str) -> bool:
    value = _number(row.get(price))
    return value is not None and value > 0


def _label_exclusion(
    row: dict[str, Any], prepared: _PreparedPanel, request: HorizonRequest
) -> str | None:
    index = prepared.positions[row["date"]]
    exit_index = index + request.effective_holding + 1
    if exit_index >= len(prepared.days) or prepared.days[exit_index] > request.data_cutoff:
        return "unmatured"
    path = [
        prepared.indexed.get((row["asset"], prepared.days[position]))
        for position in range(index + 1, exit_index + 1)
    ]
    if any(item is None for item in path):
        return "missing_price_or_calendar"
    entry, exit_row = path[0], path[-1]
    assert entry is not None and exit_row is not None
    if any(_late(item.get("available_at"), request.data_cutoff) for item in (entry, exit_row)):
        return "unavailable_price"
    if not (_positive_price(entry, request.price) and _positive_price(exit_row, request.price)):
        return "missing_price_or_calendar"
    return None


def _matured_dates(prepared: _PreparedPanel, request: HorizonRequest) -> list[dt.date]:
    return sorted(
        {
            row["date"]
            for row in prepared.rows
            if request.start <= row["date"] <= request.end
            and _label_exclusion(row, prepared, request) is None
        }
    )


def _forward_for_row(
    row: dict[str, Any], prepared: _PreparedPanel, request: HorizonRequest
) -> tuple[float | None, str | None]:
    if _late(row.get("available_at"), request.data_cutoff):
        return None, "unavailable_factor"
    index = prepared.positions[row["date"]]
    if index + 1 >= len(prepared.days):
        return None, "missing_price_or_calendar"
    if not _available_before_bar(row.get("available_at"), prepared.days[index + 1], request):
        return None, "late_factor"
    path = [
        prepared.indexed.get((row["asset"], prepared.days[position]))
        for position in range(index + 1, index + request.effective_holding + 2)
    ]
    if any(item is None for item in path):
        return None, "missing_price_or_calendar"
    entry, exit_row = path[0], path[-1]
    assert entry is not None and exit_row is not None
    if any(_late(item.get("available_at"), request.data_cutoff) for item in (entry, exit_row)):
        return None, "unavailable_price"
    entry_price = _number(entry.get(request.price))
    exit_price = _number(exit_row.get(request.price))
    if entry_price is None or exit_price is None or entry_price <= 0 or exit_price <= 0:
        return None, "missing_price_or_calendar"
    if _number(row.get(request.factor)) is None:
        return None, "invalid_factor"
    forward = exit_price / entry_price - 1
    return (forward, None) if math.isfinite(forward) else (None, "missing_price_or_calendar")


def _collect_pairs(
    selected: list[dict[str, Any]],
    allowed: set[dt.date],
    prepared: _PreparedPanel,
    request: HorizonRequest,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    exclusions = {
        "unmatured": 0,
        "missing_price_or_calendar": 0,
        "unavailable_factor": 0,
        "late_factor": 0,
        "unavailable_price": 0,
        "invalid_factor": 0,
    }
    pairs: list[dict[str, Any]] = []
    for row in selected:
        if row["date"] not in allowed:
            exclusions[_label_exclusion(row, prepared, request) or "unmatured"] += 1
            continue
        forward, reason = _forward_for_row(row, prepared, request)
        if reason is not None:
            exclusions[reason] += 1
        else:
            assert forward is not None
            pairs.append(
                {"date": row["date"], request.factor: row[request.factor], "forward": forward}
            )
    return pairs, exclusions


def _diagnostics(
    request: HorizonRequest,
    prepared: _PreparedPanel,
    selected: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
    points: list[DailyIC],
    allowed: list[dt.date],
    coverage: list[dt.date],
    exclusions: dict[str, int],
) -> HorizonDiagnostics:
    actual = sorted({row["date"] for row in selected})
    return HorizonDiagnostics(
        request.start,
        request.end,
        actual[0] if actual else None,
        actual[-1] if actual else None,
        allowed[-1] if allowed else None,
        points[-1].date if points else None,
        coverage[0] if coverage else None,
        coverage[-1] if coverage else None,
        request.data_cutoff,
        request.min_cross_section,
        len(selected),
        len(pairs),
        len(points),
        exclusions,
    )


def study_horizon(panel: pl.DataFrame, request: HorizonRequest) -> HorizonResult:
    _validate_request(panel, request)
    prepared = _prepare_panel(panel, request.calendar)
    allowed = _matured_dates(prepared, request)
    coverage = sorted(
        {
            row["date"]
            for row in prepared.rows
            if row["date"] <= request.data_cutoff
            and _finite(row.get(request.factor))
            and not _late(row.get("available_at"), request.data_cutoff)
        }
    )
    selected = [
        row
        for row in prepared.rows
        if request.start <= row["date"] <= request.end and row["date"] <= request.data_cutoff
    ]
    pairs, exclusions = _collect_pairs(selected, set(allowed), prepared, request)
    frame = (
        pl.DataFrame(pairs)
        if pairs
        else pl.DataFrame(
            schema={"date": pl.Date, request.factor: pl.Float64, "forward": pl.Float64}
        )
    )
    if "forward" not in frame.columns:
        frame = frame.with_columns(pl.lit(None, dtype=pl.Float64).alias("forward"))
    points = daily_rank_ic(frame, request.factor, request.min_cross_section)
    pearson_points = daily_pearson_ic(frame, request.factor, request.min_cross_section)
    return HorizonResult(
        request.factor,
        request.effective_holding,
        request.price,
        _diagnostics(request, prepared, selected, pairs, points, allowed, coverage, exclusions),
        points,
        summarize_ic([point.ic for point in points], request.annualization),
        decile_profile(frame, request.factor, request.min_cross_section),
        pearson_daily=pearson_points,
        pearson_ic=summarize_ic([point.ic for point in pearson_points], request.annualization),
        interval=request.interval,
        holding_bars=request.holding_bars,
    )


_ENTRY_CUTOFFS = {"open": dt.time(9, 30), "close": dt.time(15, 0)}


def _available_by_entry(value: Any, entry_day: dt.date, price: str) -> bool:
    """Return whether a factor is available before its entry moment."""
    if value is None:
        return True
    if isinstance(value, dt.datetime):
        moment = value
        if moment.tzinfo is not None:
            from quantide.config.settings import get_timezone

            moment = moment.astimezone(get_timezone()).replace(tzinfo=None)
        cutoff = dt.datetime.combine(entry_day, _ENTRY_CUTOFFS.get(price, dt.time(9, 30)))
        return bool(moment <= cutoff)
    return bool(value < entry_day)


def _available_before_bar(value: Any, bar: Any, request: HorizonRequest) -> bool:
    if request.interval == "1d":
        return _available_by_entry(value, bar, request.price)
    if value is None:
        return True
    if isinstance(value, dt.datetime):
        if isinstance(bar, dt.datetime):
            return bool(value <= bar)
        return bool(value.date() <= bar)
    if isinstance(bar, dt.datetime):
        return bool(value < bar.date())
    return bool(value < bar)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _finite(value: Any) -> bool:
    return _number(value) is not None


def _late(value: Any, cutoff: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, dt.datetime):
        if isinstance(cutoff, dt.datetime):
            return bool(value > cutoff)
        return bool(value.date() > cutoff)
    if isinstance(cutoff, dt.datetime):
        return bool(value > cutoff.date())
    return bool(value > cutoff)


def common_cohort(results: list[HorizonResult], min_days: int = 2) -> CommonCohort:
    if min_days < 1 or len({result.holding_days for result in results}) != len(results):
        raise ValueError("invalid minimum or duplicate horizons")
    maps = {
        result.holding_days: {point.date: point.ic for point in result.daily_ic}
        for result in results
    }
    dates = sorted(set.intersection(*(set(values) for values in maps.values()))) if maps else []
    summaries = {
        horizon: summarize_ic([values[day] for day in dates])
        for horizon, values in sorted(maps.items())
    }
    pearson_maps = {
        result.holding_days: {point.date: point.ic for point in result.pearson_daily}
        for result in results
    }
    pearson_summaries = {
        horizon: summarize_ic([values[day] for day in dates if day in values])
        for horizon, values in sorted(pearson_maps.items())
    }
    return CommonCohort(
        dates,
        len(dates),
        summaries,
        "ok" if len(dates) >= min_days else "insufficient_common_sample",
        pearson_summaries,
    )


def study_panel(
    panel: pl.DataFrame,
    factors: Sequence[str],
    request: HorizonRequest,
) -> dict[str, HorizonResult]:
    """Run each available factor independently; missing columns do not affect others."""
    results: dict[str, HorizonResult] = {}
    for factor in factors:
        if factor not in panel.columns:
            continue
        results[factor] = study_horizon(panel, replace(request, factor=factor))
    return results
