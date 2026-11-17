"""Prioritized historical backfill planning."""

import datetime

from quantide.service.data_backfill import plan_backfill


def _day(month: int, day: int) -> datetime.date:
    return datetime.date(2025, month, day)


def test_tail_gap_windows_come_before_historical_gaps() -> None:
    windows = plan_backfill(
        datetime.date(2025, 1, 1),
        datetime.date(2025, 12, 31),
        {
            "daily_bars": [_day(2, 3), _day(11, 3), _day(12, 2)],
            "daily_basic": [_day(2, 3), _day(12, 2)],
        },
        available_end=_day(12, 1),
    )

    assert [(window.phase, window.start) for window in windows] == [
        ("tail", _day(12, 2)),
        ("historical", _day(11, 3)),
        ("historical", _day(2, 3)),
    ]
    assert windows[0].datasets == ("daily_bars", "daily_basic")
    assert windows[-1].datasets == ("daily_bars", "daily_basic")


def test_historical_gaps_are_newest_first_and_month_bounded() -> None:
    windows = plan_backfill(
        datetime.date(2025, 1, 1),
        datetime.date(2025, 12, 31),
        {"daily_bars": [_day(1, 2), _day(2, 3), _day(9, 3), _day(9, 10)]},
        available_end=_day(12, 31),
    )

    assert [window.start for window in windows] == [_day(9, 3), _day(2, 3), _day(1, 2)]
    assert windows[0].end == _day(9, 10)


def test_no_gaps_produces_empty_plan() -> None:
    assert (
        plan_backfill(
            datetime.date(2025, 1, 1),
            datetime.date(2025, 12, 31),
            {"daily_bars": []},
            available_end=datetime.date(2025, 12, 31),
        )
        == ()
    )
