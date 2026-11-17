"""Point-in-time listing-age eligibility for the ML strategy."""

from __future__ import annotations

import datetime
from typing import Any

import polars as pl

from quantide.data.models.calendar import calendar
from quantide.data.models.stocks import stock_list


def _listing_date(value: Any) -> datetime.date | None:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if value in (None, ""):
        return None
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _listing_meta(frame: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
    meta = stock_list.data.select(
        [column for column in ("asset", "list_date", "delist_date") if column in columns]
    ).unique("asset")
    return frame.join(meta, on="asset", how="left")


def _listing_session_positions(frame: pl.DataFrame) -> dict[datetime.date, int] | None:
    list_dates = [_listing_date(value) for value in frame["list_date"].to_list()]
    available = [value for value in list_dates if value is not None]
    if not available:
        return None
    end = max(value for value in frame["date"].to_list() if isinstance(value, datetime.date))
    try:
        sessions = list(calendar.get_trade_dates(min(available), end))
    except Exception:
        return None
    return {value: index for index, value in enumerate(sessions)}


def _listing_row_keep(
    trade_date: datetime.date,
    list_date: datetime.date | None,
    delist_date: Any,
    min_days: int,
    positions: dict[datetime.date, int] | None,
) -> bool:
    if list_date is not None and trade_date < list_date:
        return False
    delisted = _listing_date(delist_date)
    if delisted is not None and delisted <= trade_date:
        return False
    if min_days <= 0 or positions is None or list_date is None:
        return True
    start = positions.get(list_date)
    stop = positions.get(trade_date) if isinstance(trade_date, datetime.date) else None
    if start is None or stop is None:
        return True
    return stop - start + 1 >= min_days


def _listing_keep_mask(
    frame: pl.DataFrame, min_days: int, positions: dict[datetime.date, int] | None
) -> list[bool]:
    list_dates = [_listing_date(value) for value in frame["list_date"].to_list()]
    delist_values = (
        frame["delist_date"].to_list() if "delist_date" in frame.columns else [None] * frame.height
    )
    return [
        _listing_row_keep(trade_date, list_date, delist_date, min_days, positions)
        for trade_date, list_date, delist_date in zip(
            frame["date"].to_list(), list_dates, delist_values, strict=True
        )
    ]


def _apply_listing_eligibility(
    frame: pl.DataFrame, min_days: int, diagnostics: dict[str, Any] | None = None
) -> pl.DataFrame:
    if stock_list.size <= 0 or not {"list_date", "delist_date"}.intersection(
        stock_list.data.columns
    ):
        return frame
    frame = _listing_meta(frame, list(stock_list.data.columns))
    warnings: list[str] = []
    positions = _listing_session_positions(frame) if min_days > 0 else None
    if min_days > 0 and positions is None:
        warnings.append("calendar_unavailable")
    before = frame.height
    filtered = frame.filter(pl.Series(_listing_keep_mask(frame, min_days, positions)))
    if diagnostics is not None:
        diagnostics["historical_listing"] = {
            "warnings": warnings,
            "exclusion_counts": {"listing_days": before - filtered.height},
        }
    return filtered


__all__ = ["_apply_listing_eligibility"]
