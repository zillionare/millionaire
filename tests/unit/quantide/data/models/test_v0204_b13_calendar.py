"""B13 batch: cover missing branches in quantide.data.models.calendar.

Targets specific missing lines reported by /tmp/gg.json:
  - epoch property when _data is None (line 77)
  - path property when _path is None (line 103)
  - data property when _data is None (lines 110-112)
  - load() exception -> fetch from server (lines 136-141)
  - week_shift / month_shift when frames None (lines 316, 335)
  - count_day_frames Arrow/datetime conversion (lines 479, 481, 483, 485)
  - is_open_time non-trade day (line 610)
  - is_opening_call_auction_time None default + non-trade day (lines 625, 628)
  - get_frames_by_count naive datetime (line 986)
  - ceiling day-level datetime -> date (line 1030)
  - get_trade_dates start > end (line 1113)
  - count_trading_days start > end + same-day non-trade (lines 1137-1142)
"""
from __future__ import annotations

import datetime
from pathlib import Path
from unittest import mock

import arrow
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import pytz
from freezegun import freeze_time

from quantide.config.settings import DEFAULT_TIMEZONE, get_epoch
from quantide.core.enums import FrameType
from quantide.data.models.calendar import Calendar


@pytest.fixture
def tf(asset_dir):
    """Load the baseline calendar into the singleton instance."""
    cal = Calendar()
    cal.load(asset_dir / "baseline_calendar.parquet")
    return cal


# --- property guards: _data / _path None ------------------------------------


def test_epoch_returns_get_epoch_when_data_none(tf, monkeypatch):
    """Line 77: when _data is None or empty, epoch falls back to get_epoch()."""
    monkeypatch.setattr(tf, "_data", None)
    assert tf.epoch == get_epoch()


def test_path_raises_when_not_set(tf, monkeypatch):
    """Line 103: accessing path before load() raises ValueError."""
    monkeypatch.setattr(tf, "_path", None)
    with pytest.raises(ValueError, match="日历数据文件路径未指定"):
        _ = tf.path


def test_data_raises_when_not_loaded(tf, monkeypatch):
    """Lines 110-112: data property raises when _data is None."""
    monkeypatch.setattr(tf, "_data", None)
    with pytest.raises(ValueError, match="日历数据未加载"):
        _ = tf.data


# --- load() exception path --------------------------------------------------


def test_load_fetches_from_server_when_read_fails(tf, tmp_path, monkeypatch):
    """Lines 136-141: pq.read_table raises -> fetch_calendar + save fallback."""
    # Use the already-loaded calendar as the "server-fetched" payload.
    original_table = tf._data
    fetched_df = original_table.to_pandas()
    expected_rows = original_table.num_rows

    target_path = tmp_path / "recovered.parquet"

    def raise_on_read(_path):
        raise RuntimeError("disk read failed")

    monkeypatch.setattr("quantide.data.models.calendar.pq.read_table", raise_on_read)

    fetcher = mock.MagicMock()
    fetcher.fetch_calendar.return_value = fetched_df
    monkeypatch.setattr(
        "quantide.data.models.calendar.get_data_fetcher", lambda: fetcher
    )

    cal = Calendar()
    cal.load(target_path)

    assert fetcher.fetch_calendar.called
    # save() wrote the fetched data so subsequent reads succeed.
    monkeypatch.undo()
    assert pq.read_table(target_path).num_rows == expected_rows


# --- week_shift / month_shift guards ----------------------------------------


def test_week_shift_raises_when_frames_not_initialized(tf, monkeypatch):
    """Line 316: week_frames is None -> ValueError."""
    monkeypatch.setattr(tf, "week_frames", None)
    with pytest.raises(ValueError, match="week_frames 未初始化"):
        tf.week_shift(datetime.date(2020, 3, 26), 0)


def test_month_shift_raises_when_frames_not_initialized(tf, monkeypatch):
    """Line 335: month_frames is None -> ValueError."""
    monkeypatch.setattr(tf, "month_frames", None)
    with pytest.raises(ValueError, match="month_frames 未初始化"):
        tf.month_shift(datetime.date(2020, 3, 26), 0)


# --- count_day_frames type coercion -----------------------------------------


def test_count_day_frames_converts_arrow_inputs(tf):
    """Lines 478-479, 482-483: Arrow start/end converted to date."""
    start = arrow.get("2020-03-16")
    end = arrow.get("2020-03-20")
    expected = tf.count_day_frames(
        datetime.date(2020, 3, 16), datetime.date(2020, 3, 20)
    )
    assert tf.count_day_frames(start, end) == expected


def test_count_day_frames_converts_datetime_inputs(tf):
    """Lines 480-481, 484-485: plain datetime start/end converted to date."""
    start = datetime.datetime(2020, 3, 16, 10, 0)
    end = datetime.datetime(2020, 3, 20, 14, 30)
    expected = tf.count_day_frames(
        datetime.date(2020, 3, 16), datetime.date(2020, 3, 20)
    )
    assert tf.count_day_frames(start, end) == expected


# --- is_open_time / is_opening_call_auction_time ----------------------------


def test_is_open_time_returns_false_for_non_trade_day(tf):
    """Line 610: non-trade day -> False before tick lookup."""
    # 2020-03-21 is Saturday
    tm = datetime.datetime(2020, 3, 21, 10, 0, tzinfo=DEFAULT_TIMEZONE)
    assert tf.is_open_time(tm) is False


def test_is_opening_call_auction_time_none_tm_defaults_and_non_trade_day(tf):
    """Lines 625, 628: tm=None -> now; Saturday -> False."""
    # 2020-03-21 is Saturday, 09:20 would be in auction window on a trade day.
    fake_now = datetime.datetime(2020, 3, 21, 9, 20)
    with freeze_time(fake_now):
        assert tf.is_opening_call_auction_time() is False


# --- get_frames_by_count naive datetime -------------------------------------


def test_get_frames_by_count_min1_naive_datetime_returns_list(tf):
    """Line 986: end.tzinfo is None -> result.tolist() (no tz reattachment)."""
    end = datetime.datetime(2020, 3, 26, 9, 31)  # naive
    result = tf.get_frames_by_count(end, 2, FrameType.MIN1)
    assert len(result) == 2
    assert all(getattr(x, "tzinfo", None) is None for x in result)


# --- ceiling day-level datetime -> date -------------------------------------


def test_ceiling_day_level_converts_datetime_to_date(tf):
    """Line 1030: day-level frame + datetime moment -> moment.date()."""
    # 2020-03-26 is a trade day; ceiling of intra-day datetime returns the date.
    result = tf.ceiling(datetime.datetime(2020, 3, 26, 10, 0), FrameType.DAY)
    assert result == datetime.date(2020, 3, 26)


# --- get_trade_dates / count_trading_days guards ----------------------------


def test_get_trade_dates_raises_when_start_after_end(tf):
    """Line 1113: start > end -> ValueError."""
    with pytest.raises(ValueError, match="不能大于"):
        tf.get_trade_dates(datetime.date(2020, 3, 27), datetime.date(2020, 3, 26))


def test_count_trading_days_raises_when_start_after_end(tf):
    """Lines 1137-1138: start > end -> ValueError."""
    with pytest.raises(ValueError, match="不能大于"):
        tf.count_trading_days(datetime.date(2020, 3, 27), datetime.date(2020, 3, 26))


def test_count_trading_days_same_day_non_trade_returns_zero(tf):
    """Lines 1140-1141: start == end and non-trade day -> 0 (not 1)."""
    # 2020-03-21 is Saturday
    assert (
        tf.count_trading_days(
            datetime.date(2020, 3, 21), datetime.date(2020, 3, 21)
        )
        == 0
    )
