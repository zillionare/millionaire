"""Date-window helpers for factor tracking panels."""

from __future__ import annotations

import datetime


def lookback_start(end: datetime.date, lookback: str) -> datetime.date:
    if lookback == "all":
        return datetime.date(2005, 1, 1)
    years = {"1y": 1, "3y": 3, "5y": 5}[lookback]
    try:
        return end.replace(year=end.year - years)
    except ValueError:
        return end.replace(year=end.year - years, day=28)


def panel_start(lookback: str, end: datetime.date) -> datetime.date:
    evaluation_start = lookback_start(end, lookback)
    return (
        datetime.date(2005, 1, 1)
        if lookback == "all"
        else evaluation_start - datetime.timedelta(days=120)
    )
