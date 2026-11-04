"""Coverage evidence required before discarding in-memory minute bars."""

import datetime
from collections.abc import Collection

import pandas as pd

from quantide.data.coverage import _SessionCalendar, trading_sessions


def _require_session_minutes(
    frame: pd.DataFrame,
    inactive_dates: Collection[datetime.date],
    period: int | str,
    expected: list[datetime.date],
) -> None:
    """Require session minutes."""
    dates = pd.to_datetime(frame["date"], errors="raise")
    counts = dates.drop_duplicates().dt.date.value_counts()
    if set(dates.dt.date) & set(inactive_dates):
        raise RuntimeError("分钟线与停牌状态证据冲突")
    period = int(period)
    per_session = 240 // period
    missing = [day for day in expected if counts.get(day, 0) != per_session]
    if missing:
        raise RuntimeError(f"分钟线缺失或不完整的交易日: {missing[:5]}")
    for day in expected:
        actual = set(dates[dates.dt.date == day])
        required_times = {
            pd.Timestamp(
                datetime.datetime.combine(day, opening) + datetime.timedelta(minutes=offset)
            )
            for opening in (datetime.time(9, 30), datetime.time(13))
            for offset in range(period, 121, period)
        }
        if actual != required_times:
            raise RuntimeError(f"分钟线时间戳不符合收盘边界: {day}")
    required = frame[["open", "high", "low", "close"]]
    if required.isna().any().any():
        raise RuntimeError("分钟线价格包含空值")


def missing_minute_sessions(
    frame: pd.DataFrame | None,
    start: datetime.date,
    end: datetime.date,
    period: int | str,
    calendar: _SessionCalendar,
) -> list[datetime.date]:

    expected = list(trading_sessions(calendar, start, end))
    if frame is None or frame.empty:
        return expected
    counts = pd.to_datetime(frame["date"]).drop_duplicates().dt.date.value_counts()
    return [day for day in expected if counts.get(day, 0) != 240 // int(period)]


def require_minute_coverage(
    frame: pd.DataFrame | None,
    start: datetime.date,
    end: datetime.date,
    period: int | str,
    calendar: _SessionCalendar,
    inactive_dates: Collection[datetime.date] = (),
) -> None:
    """Require complete sessions; missing or partial source responses fail closed."""
    expected = list(trading_sessions(calendar, start, end))
    if not expected:
        raise RuntimeError("交易日历无法确定分钟线覆盖范围")
    expected = [day for day in expected if day not in inactive_dates]
    if frame is None or frame.empty:
        if not expected:
            return
        raise RuntimeError("分钟源未提供覆盖证据")
    _require_session_minutes(frame, inactive_dates, period, expected)
