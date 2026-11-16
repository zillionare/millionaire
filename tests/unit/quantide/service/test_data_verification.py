"""A coverage check must report missing sessions, invalid prices and duplicates."""

import datetime
from types import SimpleNamespace

import polars as pl
import pytest

from quantide.service.data_verification import verify_daily_history


def test_daily_verification_reports_holes_and_invalid_data(monkeypatch):
    days = [datetime.date(2024, 1, number) for number in (2, 3, 4)]
    calendar = SimpleNamespace(epoch=days[0], end=days[-1], get_frames=lambda *args: days)
    frame = pl.DataFrame({
        "date": [days[0], days[0], days[2]], "asset": ["600000.SH"] * 3,
        "open": [10., 10., -1.], "high": [10.] * 3, "low": [10.] * 3, "close": [10.] * 3,
    })
    monkeypatch.setattr("quantide.data.models.calendar.calendar", calendar)
    monkeypatch.setattr("quantide.data.models.stocks.stock_list", SimpleNamespace(
        data=pl.DataFrame({"asset": ["600000.SH"]})))
    monkeypatch.setattr("quantide.data.models.daily_bars.daily_bars", SimpleNamespace(
        get_bars_in_range=lambda *args, **kwargs: frame))
    result = verify_daily_history(days[0], days[-1])
    assert result == {"assets": 1, "missing": 1, "invalid": 2,
                      "examples": ["600000.SH: 2024-01-03"]}
    with pytest.raises(ValueError, match="交易日历"):
        verify_daily_history(datetime.date(2023, 1, 1), days[-1])
