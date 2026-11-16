"""Maintenance must recover earlier dataset gaps instead of trusting the latest daily bar."""

import datetime

from quantide.service.maintenance import maintenance_start


def test_minute_gap_is_not_hidden_by_newer_daily_bars():
    history = datetime.date(2024, 1, 1)
    assert maintenance_start(history, [datetime.date(2024, 6, 5),
                                       datetime.date(2024, 6, 4),
                                       datetime.date(2024, 2, 1)]) == datetime.date(2024, 2, 1)


def test_absent_dataset_restarts_from_user_history_floor():
    history = datetime.date(2024, 1, 1)
    assert maintenance_start(history, [datetime.date(2024, 6, 5), None]) == history
    assert maintenance_start(history, [datetime.date(2020, 1, 1)]) == history
