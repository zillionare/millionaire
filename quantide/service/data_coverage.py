"""Historical data coverage contracts for backtests and maintenance."""

from __future__ import annotations

import datetime
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl
from loguru import logger

from quantide.config.settings import get_epoch
from quantide.core.enums import FrameType


class DataCoverageError(RuntimeError):
    """A requested backtest range cannot be served by the local data contract."""

    def __init__(self, message: str, report: CoverageReport | None = None) -> None:
        super().__init__(message)
        self.report = report


@dataclass(frozen=True)
class CoverageGap:
    """One contiguous run of missing trading sessions for a dataset."""

    dataset: str
    sessions: tuple[datetime.date, ...]
    blocking: bool = True

    @property
    def start(self) -> datetime.date:
        return self.sessions[0]

    @property
    def end(self) -> datetime.date:
        return self.sessions[-1]

    @property
    def count(self) -> int:
        return len(self.sessions)


@dataclass(frozen=True)
class CoverageReport:
    """Coverage result for one requested interval."""

    start: datetime.date
    end: datetime.date
    epoch: datetime.date
    gaps: tuple[CoverageGap, ...]
    warnings: tuple[str, ...] = ()

    @property
    def blocking_gaps(self) -> tuple[CoverageGap, ...]:
        return tuple(gap for gap in self.gaps if gap.blocking)

    @property
    def ok(self) -> bool:
        return not self.blocking_gaps

    def message(self) -> str:
        blocking = self.blocking_gaps
        if not blocking:
            return ""
        parts = [
            f"{gap.dataset} 缺少 {gap.start}~{gap.end}（{gap.count} 个交易日）" for gap in blocking
        ]
        return "回测区间数据不完整：" + "；".join(parts)


def normalize_session(value: datetime.date | datetime.datetime) -> datetime.date:
    """Normalize calendar frames to a plain date."""
    return value.date() if isinstance(value, datetime.datetime) else value


def _calendar_api(calendar_obj: Any | None) -> Any:
    if calendar_obj is not None:
        return calendar_obj
    from quantide.data.models.calendar import calendar

    return calendar


def expected_sessions(
    start: datetime.date,
    end: datetime.date,
    *,
    calendar_obj: Any | None = None,
) -> tuple[datetime.date, ...]:
    """Return calendar sessions in ``[start, end]`` without surrounding carry-in."""
    if start > end:
        return ()
    frames = _calendar_api(calendar_obj).get_frames(start, end, FrameType.DAY)
    return tuple(day for frame in frames if start <= (day := normalize_session(frame)) <= end)


def missing_session_groups(
    expected: Iterable[datetime.date],
    available: Iterable[datetime.date],
) -> tuple[tuple[datetime.date, ...], ...]:
    """Group consecutive missing sessions in trading-session order."""
    present = set(available)
    groups: list[tuple[datetime.date, ...]] = []
    current: list[datetime.date] = []
    for session in expected:
        if session in present:
            if current:
                groups.append(tuple(current))
                current = []
            continue
        current.append(session)
    if current:
        groups.append(tuple(current))
    return tuple(groups)


def _daily_basic_dates() -> set[datetime.date]:
    from quantide.data.models.daily_basic import daily_basic

    if not getattr(daily_basic, "_loaded", False):
        daily_basic.load()
    if daily_basic.data.is_empty():
        return set()
    return set(daily_basic.data["date"].to_list())


def _index_dates(
    index_code: str | None,
    start: datetime.date,
    end: datetime.date,
) -> set[datetime.date]:
    from quantide.data import get_index_bars_store

    store = get_index_bars_store()
    codes = [index_code] if index_code else None
    frame: pl.DataFrame | pl.LazyFrame | None = store.get(codes, start, end)
    if frame is None:
        return set()
    if isinstance(frame, pl.LazyFrame):
        frame = frame.collect()
    if frame.is_empty():
        return set()
    return set(frame["date"].to_list())


def _limit_dates() -> set[datetime.date]:
    from quantide.data import get_limit_price_store

    return set(get_limit_price_store().available_dates)


def dataset_available_dates(
    dataset: str,
    start: datetime.date,
    end: datetime.date,
    *,
    index_code: str | None = None,
) -> set[datetime.date]:
    """Read the set of locally available sessions for a required dataset."""
    if dataset == "daily_bars":
        from quantide.data.models.daily_bars import daily_bars

        return {day for day in daily_bars.available_dates if start <= day <= end}
    if dataset == "daily_basic":
        return {day for day in _daily_basic_dates() if start <= day <= end}
    if dataset == "limit_price":
        return {day for day in _limit_dates() if start <= day <= end}
    if dataset == "index_bars":
        return _index_dates(index_code, start, end)
    raise ValueError(f"unknown coverage dataset: {dataset}")


def _gaps_for_dataset(
    dataset: str,
    sessions: Sequence[datetime.date],
    start: datetime.date,
    end: datetime.date,
    *,
    blocking: bool,
    index_code: str | None = None,
) -> list[CoverageGap]:
    available = dataset_available_dates(dataset, start, end, index_code=index_code)
    return [
        CoverageGap(dataset, group, blocking)
        for group in missing_session_groups(sessions, available)
    ]


def _optional_gaps(
    optional: Sequence[tuple[str, str | None]],
    sessions: Sequence[datetime.date],
    start: datetime.date,
    end: datetime.date,
) -> tuple[list[CoverageGap], list[str]]:
    gaps: list[CoverageGap] = []
    warnings: list[str] = []
    for dataset, index_code in optional:
        try:
            gaps.extend(
                _gaps_for_dataset(
                    dataset,
                    sessions,
                    start,
                    end,
                    blocking=False,
                    index_code=index_code,
                )
            )
        except Exception as exc:
            warnings.append(f"{dataset} 不可用：{exc}")
    return gaps, warnings


def build_coverage_report(
    start: datetime.date,
    end: datetime.date,
    *,
    required: Sequence[str] = ("daily_bars",),
    optional: Sequence[tuple[str, str | None]] = (),
    epoch: datetime.date | None = None,
    calendar_obj: Any | None = None,
) -> CoverageReport:
    """Build a coverage report over the requested backtest interval."""
    epoch = epoch or get_epoch()
    if start < epoch:
        raise DataCoverageError(f"回测起点 {start} 早于数据起点 epoch={epoch}")
    if calendar_obj is None:
        from quantide.data.models.calendar import calendar as calendar_obj
    calendar_end = getattr(calendar_obj, "end", None)
    if isinstance(calendar_end, datetime.date) and end > calendar_end:
        raise DataCoverageError(f"交易日历仅覆盖到 {calendar_end}，无法校验 {end}")

    sessions = expected_sessions(start, end, calendar_obj=calendar_obj)
    if not sessions:
        raise DataCoverageError(f"{start}~{end} 没有可用交易日")
    gaps: list[CoverageGap] = []
    for dataset in required:
        try:
            gaps.extend(_gaps_for_dataset(dataset, sessions, start, end, blocking=True))
        except Exception as exc:
            raise DataCoverageError(f"{dataset} 不可用：{exc}") from exc
    optional_gaps, warnings = _optional_gaps(optional, sessions, start, end)
    gaps.extend(optional_gaps)
    return CoverageReport(start, end, epoch, tuple(gaps), tuple(warnings))


def validate_backtest_coverage(
    start: datetime.date,
    end: datetime.date,
    *,
    config: dict[str, Any] | None = None,
    calendar_obj: Any | None = None,
) -> CoverageReport | None:
    """Raise when the requested interval has a blocking market-level gap."""
    from quantide.data.models.daily_bars import daily_bars

    if not getattr(daily_bars, "_initialized", False):
        return None
    calendar_api = _calendar_api(calendar_obj)
    start = calendar_api.ceiling(start, FrameType.DAY)
    end = calendar_api.floor(end, FrameType.DAY)
    data_end = getattr(daily_bars, "end", None)
    if isinstance(data_end, datetime.date):
        end = min(end, data_end)
    if start > end:
        return None
    config = config or {}
    optional: list[tuple[str, str | None]] = [("daily_basic", None)]
    benchmark = str(config.get("benchmark") or "").strip()
    if benchmark:
        optional.append(("index_bars", benchmark))
    from quantide.service.data_gaps import DataGapStore

    blocked = DataGapStore().blocking("daily_bars", start, end)
    if blocked:
        first = blocked[0]
        raise DataCoverageError(
            f"回测区间包含不可补全的日线缺口：{first.start}~{first.end}（{first.reason_code}）"
        )
    report = build_coverage_report(
        start,
        end,
        required=("daily_bars",),
        optional=tuple(optional),
        calendar_obj=calendar_obj,
    )
    if not report.ok:
        raise DataCoverageError(report.message(), report)
    for gap in report.gaps:
        if not gap.blocking:
            logger.warning(
                "可选数据缺口 {} {}~{}（{} 个交易日），不阻断回测",
                gap.dataset,
                gap.start,
                gap.end,
                gap.count,
            )
    return report
