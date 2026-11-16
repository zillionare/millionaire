"""Real-store regression for holes hidden by newer minute bars."""

import datetime
from types import SimpleNamespace

import polars as pl

from quantide.data.stores.minute_bars import MinuteBarsStore
from quantide.service.minute_gaps import coverage_starts, record_suspensions


def test_internal_gap_and_partial_session_are_not_hidden_by_latest_bar(tmp_path, monkeypatch):
    days = [datetime.date(2024, 1, day) for day in (2, 3, 4)]
    calendar = SimpleNamespace(get_frames=lambda *args: days)
    stocks = SimpleNamespace(data=pl.DataFrame({"asset": ["600000.SH"]}))
    monkeypatch.setattr("quantide.data.models.calendar.calendar", calendar)
    monkeypatch.setattr("quantide.data.models.stocks.stock_list", stocks)
    store = MinuteBarsStore(tmp_path / "minutes.parquet", calendar)
    times = [datetime.time(h, m) for h, m in
             ((10, 0), (10, 30), (11, 0), (11, 30), (13, 30), (14, 0), (14, 30), (15, 0))]
    rows = [{"date": datetime.datetime.combine(day, tm), "asset": "600000.SH",
             "open": 10., "high": 10., "low": 10., "close": 10., "volume": 100.,
             "amount": 1000.} for day in (days[0], days[2]) for tm in times]
    store.append_data(pl.DataFrame(rows))
    assert store.last_dates()["600000.SH"] == days[2]
    assert coverage_starts(store, ["600000.SH"], days[0], days[2], "30") == {"600000.SH": days[1]}
    record_suspensions(store, "600000.SH", days[1], days[1], {days[1]})
    reloaded = MinuteBarsStore(tmp_path / "minutes.parquet", calendar)
    assert coverage_starts(reloaded, ["600000.SH"], days[0], days[2], "30") == {"600000.SH": None}
    # Removing one historical bar invalidates coverage even though the last bar is unchanged.
    pl.DataFrame(rows[1:]).write_parquet(store._store_path)
    assert coverage_starts(reloaded, ["600000.SH"], days[0], days[2], "30")["600000.SH"] == days[0]
