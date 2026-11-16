"""Temporary custom factor studies that never publish tracking snapshots."""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, cast

import polars as pl

from quantide.core.market_time import market_now
from quantide.data.models.calendar import calendar as trade_calendar
from quantide.factors.alphatest import load_factor_panel
from quantide.factors.metadata import FACTOR_METADATA, Holding
from quantide.factors.research import (
    STATISTICS_VERSION,
    Bucket,
    CommonCohort,
    DailyIC,
    DailyPearson,
    DecileProfile,
    HorizonDiagnostics,
    HorizonRequest,
    HorizonResult,
    ICSummary,
    common_cohort,
    study_horizon,
)

_HOLDING_CHOICES = (1, 2, 3, 5, 10, 20)


def trading_days(start: dt.date, end: dt.date) -> tuple[dt.date, ...]:
    """Authoritative exchange sessions used for label maturity."""
    days = tuple(trade_calendar.get_trade_dates(start, end))
    if not days:
        raise RuntimeError("交易日历在请求区间内没有可用数据")
    return days


def calendar_version(days: tuple[dt.date, ...]) -> str:
    encoded = ",".join(day.isoformat() for day in days)
    digest = hashlib.sha256(encoded.encode()).hexdigest()[:16]
    return f"{days[0].isoformat()}:{days[-1].isoformat()}:{len(days)}:{digest}"


@dataclass(frozen=True)
class CustomStudy:
    study_id: str
    factor_id: str
    start: dt.date
    end: dt.date
    price_field: str
    data_cutoff: dt.date
    holding_days: tuple[Holding, ...]
    results: tuple[HorizonResult, ...]
    cohort: CommonCohort
    created_at: str
    calendar_version: str = ""
    statistics_version: str = STATISTICS_VERSION

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CustomStudy:
        return cls(
            study_id=str(payload["study_id"]),
            factor_id=str(payload["factor_id"]),
            start=_date(payload["start"]),
            end=_date(payload["end"]),
            price_field=str(payload["price_field"]),
            data_cutoff=_date(payload["data_cutoff"]),
            holding_days=cast(
                tuple[Holding, ...], tuple(int(value) for value in payload["holding_days"])
            ),
            results=tuple(_horizon_from_dict(item) for item in payload["results"]),
            cohort=_cohort_from_dict(payload["common_cohort"]),
            created_at=str(payload["created_at"]),
            calendar_version=str(payload.get("calendar_version", "")),
            statistics_version=str(payload.get("statistics_version", STATISTICS_VERSION)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "custom_study",
            "study_id": self.study_id,
            "factor_id": self.factor_id,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "price_field": self.price_field,
            "data_cutoff": self.data_cutoff.isoformat(),
            "holding_days": list(self.holding_days),
            "results": [result.as_dict() for result in self.results],
            "common_cohort": self.cohort.as_dict(),
            "created_at": self.created_at,
            "calendar_version": self.calendar_version,
            "statistics_version": self.statistics_version,
        }


def _date(value: Any) -> dt.date:
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))


def _summary_from_dict(raw: dict[str, Any]) -> ICSummary:
    return ICSummary(
        mean=raw.get("mean"),
        t_naive=raw.get("t_naive"),
        t_status=str(raw.get("t_status", "insufficient_days")),
        n_days=int(raw.get("n_days", 0)),
        std=raw.get("std"),
        icir=raw.get("icir"),
        annualized_icir=raw.get("annualized_icir"),
        annualization=int(raw.get("annualization", 252)),
    )


def _daily_from_dict(raw: dict[str, Any]) -> DailyIC:
    return DailyIC(_date(raw["date"]), float(raw["ic"]), int(raw["n_samples"]))


def _pearson_from_dict(raw: dict[str, Any]) -> DailyPearson:
    return DailyPearson(_date(raw["date"]), float(raw["ic"]), int(raw["n_samples"]))


def _diagnostics_from_dict(raw: dict[str, Any]) -> HorizonDiagnostics:
    return HorizonDiagnostics(
        requested_start=_date(raw["requested_start"]),
        requested_end=_date(raw["requested_end"]),
        actual_start=_date(raw["actual_start"]) if raw.get("actual_start") else None,
        actual_end=_date(raw["actual_end"]) if raw.get("actual_end") else None,
        as_of_date=_date(raw["as_of_date"]) if raw.get("as_of_date") else None,
        latest_valid_signal_date=(
            _date(raw["latest_valid_signal_date"]) if raw.get("latest_valid_signal_date") else None
        ),
        coverage_start=_date(raw["coverage_start"]) if raw.get("coverage_start") else None,
        coverage_end=_date(raw["coverage_end"]) if raw.get("coverage_end") else None,
        data_cutoff=_date(raw["data_cutoff"]),
        min_cross_section=int(raw["min_cross_section"]),
        n_rows=int(raw["n_rows"]),
        n_valid_pairs=int(raw["n_valid_pairs"]),
        n_valid_days=int(raw["n_valid_days"]),
        exclusion_counts=dict(raw.get("exclusion_counts") or {}),
    )


def _deciles_from_dict(raw: dict[str, Any]) -> DecileProfile:
    buckets = [
        Bucket(
            bucket=int(item["bucket"]),
            mean_forward=item.get("mean_forward"),
            n_days=int(item["n_days"]),
            n_samples=int(item["n_samples"]),
            status=str(item["status"]),
        )
        for item in raw.get("buckets") or []
    ]
    return DecileProfile(
        buckets=buckets,
        d1_mean_common=raw.get("d1_mean_common"),
        d10_mean_common=raw.get("d10_mean_common"),
        d1_minus_d10=raw.get("d1_minus_d10"),
        n_common_days=int(raw.get("n_common_days", 0)),
        status=str(raw.get("status", "")),
        weighting=str(raw.get("weighting", "equal_day")),
    )


def _horizon_from_dict(raw: dict[str, Any]) -> HorizonResult:
    return HorizonResult(
        factor=str(raw["factor"]),
        holding_days=int(raw["holding_days"]),
        price=str(raw["price"]),
        diagnostics=_diagnostics_from_dict(raw["diagnostics"]),
        daily_ic=[_daily_from_dict(item) for item in raw.get("daily_ic") or []],
        rank_ic=_summary_from_dict(raw["rank_ic"]),
        deciles=_deciles_from_dict(raw["deciles"]),
        statistics_version=str(raw.get("statistics_version", STATISTICS_VERSION)),
        pearson_daily=[_pearson_from_dict(item) for item in raw.get("pearson_daily") or []],
        pearson_ic=_summary_from_dict(
            raw.get("pearson_ic") or {"t_status": "insufficient_days", "n_days": 0}
        ),
        interval=str(raw.get("interval", "1d")),
        holding_bars=raw.get("holding_bars"),
    )


def _cohort_from_dict(raw: dict[str, Any]) -> CommonCohort:
    return CommonCohort(
        dates=[_date(value) for value in raw.get("dates") or []],
        n_days=int(raw.get("n_days", 0)),
        per_horizon={
            int(key): _summary_from_dict(value)
            for key, value in (raw.get("per_horizon") or {}).items()
        },
        status=str(raw.get("status", "")),
        pearson_per_horizon={
            int(key): _summary_from_dict(value)
            for key, value in (raw.get("pearson_per_horizon") or {}).items()
        },
    )


def _holdings(values: list[int] | tuple[int, ...]) -> tuple[Holding, ...]:
    unique = set(values)
    if not unique or any(value not in _HOLDING_CHOICES for value in unique):
        raise ValueError("自定义检验包含非法持有期")
    return cast(tuple[Holding, ...], tuple(sorted(unique)))


def validate_study_request(
    factor_id: str,
    start: dt.date,
    end: dt.date,
    holding_days: list[int] | tuple[int, ...],
    price_field: str = "open",
) -> tuple[Holding, ...]:
    if factor_id not in FACTOR_METADATA:
        raise KeyError(factor_id)
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")
    if price_field not in ("open", "close"):
        raise ValueError("价格口径只能是开盘价或收盘价")
    return _holdings(holding_days)


def _load_study_panel(
    factor_id: str,
    start: dt.date,
    end: dt.date,
    should_cancel: Any,
    checkpoint: Any,
) -> tuple[pl.DataFrame, dt.date, tuple[dt.date, ...]]:
    load_start = start - dt.timedelta(days=140)
    load_end = end + dt.timedelta(days=90)
    if callable(should_cancel) and should_cancel():
        raise InterruptedError("custom study cancelled")
    if callable(checkpoint):
        checkpoint(
            "load",
            {"factor": factor_id, "start": start.isoformat(), "end": end.isoformat()},
        )
    panel = load_factor_panel(load_start, load_end)
    if panel.is_empty():
        raise ValueError("指定区间没有可用行情")
    data_cutoff = panel["date"].max()
    if not isinstance(data_cutoff, dt.date) or data_cutoff < start:
        raise ValueError("指定区间没有可用行情")
    return panel, data_cutoff, trading_days(load_start, data_cutoff)


def run_custom_study(
    factor_id: str,
    start: dt.date,
    end: dt.date,
    holding_days: list[int] | tuple[int, ...],
    price_field: str = "open",
    *,
    should_cancel: Any = None,
    checkpoint: Any = None,
) -> CustomStudy:
    holdings = validate_study_request(factor_id, start, end, holding_days, price_field)
    panel, data_cutoff, days = _load_study_panel(factor_id, start, end, should_cancel, checkpoint)
    results: list[HorizonResult] = []
    for holding in holdings:
        if callable(should_cancel) and should_cancel():
            raise InterruptedError("custom study cancelled")
        results.append(
            study_horizon(
                panel,
                HorizonRequest(
                    factor=factor_id,
                    holding_days=holding,
                    start=start,
                    end=end,
                    data_cutoff=data_cutoff,
                    price=price_field,
                    calendar=days,
                ),
            )
        )
        if callable(checkpoint):
            checkpoint("study", {"completed": len(results), "total": len(holdings)})
    now = market_now()
    return CustomStudy(
        study_id=uuid.uuid4().hex[:12],
        factor_id=factor_id,
        start=start,
        end=end,
        price_field=price_field,
        data_cutoff=data_cutoff,
        holding_days=holdings,
        results=tuple(results),
        cohort=common_cohort(results),
        created_at=now.isoformat(),
        calendar_version=calendar_version(days),
    )


def primary_result(study: CustomStudy, holding: int) -> HorizonResult:
    for result in study.results:
        if result.holding_days == holding:
            return result
    raise KeyError(holding)


def panel_columns() -> tuple[str, ...]:
    return ("date", "asset", "open", "close")


def validate_panel(panel: pl.DataFrame) -> None:
    missing = set(panel_columns()) - set(panel.columns)
    if missing:
        raise ValueError(f"panel missing columns: {sorted(missing)}")
