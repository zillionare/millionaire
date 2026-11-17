"""Coverage contracts for backtest data preflight."""

import datetime

import pytest

from quantide.service import data_coverage


class _Calendar:
    end = datetime.date(2026, 11, 30)

    def __init__(self, days: list[datetime.date]) -> None:
        self.days = sorted(days)

    def get_frames(self, start, end, frame_type=None):
        return [day for day in self.days if start <= day <= end]

    def ceiling(self, target, frame_type=None):
        return next(day for day in self.days if day >= target)

    def floor(self, target, frame_type=None):
        return max(day for day in self.days if day <= target)


def _trading_days(start: datetime.date, count: int) -> list[datetime.date]:
    days: list[datetime.date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += datetime.timedelta(days=1)
    return days


def test_missing_session_groups_are_contiguous_in_trading_order() -> None:
    days = _trading_days(datetime.date(2024, 1, 2), 10)
    groups = data_coverage.missing_session_groups(days, set(days) - {days[2], days[3], days[7]})

    assert groups == ((days[2], days[3]), (days[7],))


def test_coverage_report_marks_market_gap_blocking(monkeypatch) -> None:
    days = _trading_days(datetime.date(2025, 1, 2), 6)
    monkeypatch.setattr(
        data_coverage,
        "dataset_available_dates",
        lambda dataset, start, end, index_code=None: {days[0], days[-1]},
    )

    report = data_coverage.build_coverage_report(
        days[0],
        days[-1],
        required=("daily_bars",),
        epoch=datetime.date(2024, 1, 1),
        calendar_obj=_Calendar(days),
    )

    assert report.ok is False
    assert len(report.blocking_gaps) == 1
    assert report.blocking_gaps[0].sessions == tuple(days[1:-1])
    assert "daily_bars" in report.message()


def test_optional_dataset_gap_is_a_warning_not_blocking(monkeypatch) -> None:
    days = _trading_days(datetime.date(2025, 1, 2), 4)
    monkeypatch.setattr(
        data_coverage,
        "dataset_available_dates",
        lambda dataset, start, end, index_code=None: set(days)
        if dataset == "daily_bars"
        else set(),
    )

    report = data_coverage.build_coverage_report(
        days[0],
        days[-1],
        required=("daily_bars",),
        optional=(("daily_basic", None),),
        epoch=datetime.date(2024, 1, 1),
        calendar_obj=_Calendar(days),
    )

    assert report.ok is True
    assert len(report.blocking_gaps) == 0
    assert len(report.gaps) == 1
    assert report.gaps[0].dataset == "daily_basic"


def test_coverage_rejects_range_before_epoch() -> None:
    with pytest.raises(data_coverage.DataCoverageError, match="早于数据起点"):
        data_coverage.build_coverage_report(
            datetime.date(2024, 12, 31),
            datetime.date(2025, 1, 2),
            epoch=datetime.date(2025, 1, 1),
            calendar_obj=_Calendar(_trading_days(datetime.date(2024, 1, 2), 5)),
        )


def test_validate_backtest_coverage_raises_on_blocking_gap(monkeypatch) -> None:
    days = _trading_days(datetime.date(2025, 1, 2), 5)
    calendar_obj = _Calendar(days)
    from quantide.data.models.daily_bars import daily_bars
    from quantide.service import data_gaps

    monkeypatch.setattr(daily_bars, "_initialized", True, raising=False)
    monkeypatch.setattr(type(daily_bars), "end", property(lambda self: days[-1]))
    monkeypatch.setattr(
        data_coverage,
        "dataset_available_dates",
        lambda dataset, start, end, index_code=None: {days[0], days[-1]},
    )
    monkeypatch.setattr(
        data_gaps,
        "DataGapStore",
        lambda: type("Store", (), {"blocking": lambda self, *args: []})(),
    )

    with pytest.raises(data_coverage.DataCoverageError, match="daily_bars"):
        data_coverage.validate_backtest_coverage(
            days[0],
            days[-1],
            calendar_obj=calendar_obj,
        )


def test_validate_backtest_coverage_skips_when_store_not_ready(monkeypatch) -> None:
    from quantide.data.models.daily_bars import daily_bars

    monkeypatch.setattr(daily_bars, "_initialized", False, raising=False)

    assert data_coverage.validate_backtest_coverage(
        datetime.date(2025, 1, 2),
        datetime.date(2025, 1, 3),
    ) is None


def test_daily_basic_dates_loads_store_on_first_read(monkeypatch) -> None:
    import polars as pl

    from quantide.data.models.daily_basic import daily_basic

    calls = []
    monkeypatch.setattr(daily_basic, "_loaded", False, raising=False)
    monkeypatch.setattr(
        daily_basic,
        "_data",
        pl.DataFrame({"date": [datetime.date(2025, 1, 2)]}),
    )
    monkeypatch.setattr(daily_basic, "load", lambda: calls.append(True) or daily_basic)

    assert data_coverage._daily_basic_dates() == {datetime.date(2025, 1, 2)}
    assert calls == [True]
