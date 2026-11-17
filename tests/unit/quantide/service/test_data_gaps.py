"""Durable unfillable data-gap registry."""

import datetime

from quantide.service.data_gaps import DataGapRecord, DataGapStore


def _record(start: datetime.date, end: datetime.date, retryable: bool) -> DataGapRecord:
    return DataGapRecord(
        dataset="daily_bars",
        start=start,
        end=end,
        reason_code="empty_data",
        retryable=retryable,
    )


def test_only_permanent_gaps_block_backtests(tmp_path) -> None:
    store = DataGapStore(tmp_path / "gaps.json")
    store.record(_record(datetime.date(2025, 1, 2), datetime.date(2025, 1, 31), True))
    store.record(_record(datetime.date(2025, 2, 3), datetime.date(2025, 2, 28), False))

    assert store.blocking("daily_bars", datetime.date(2025, 1, 2), datetime.date(2025, 1, 31)) == []
    blocking = store.blocking("daily_bars", datetime.date(2025, 1, 2), datetime.date(2025, 3, 1))
    assert [(item.start, item.end) for item in blocking] == [
        (datetime.date(2025, 2, 3), datetime.date(2025, 2, 28))
    ]


def test_resolving_gap_removes_blocking(tmp_path) -> None:
    store = DataGapStore(tmp_path / "gaps.json")
    start = datetime.date(2025, 1, 2)
    end = datetime.date(2025, 1, 31)
    store.record(_record(start, end, False))

    store.resolve("daily_bars", start, end)

    assert store.active() == []
    assert store.blocking("daily_bars", start, end) == []
