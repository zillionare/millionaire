"""Ground truth implementations of FR-015 (Securities/Stocks).

Same purity rules as tests/ground_truth/calendar.py: NO `quantide.*` imports.
"""
from __future__ import annotations

from datetime import date

import polars as pl
from polars import DataFrame


def is_st(st_info: DataFrame, asset: str, on_date: str) -> bool:
    """Return True iff `asset` is ST/*ST on `on_date`.

    st_info must have columns: asset, date (str YYYYMMDD), is_st (int 0/1).
    """
    row = st_info.filter((pl.col("asset") == asset) & (pl.col("date") == on_date))
    if row.is_empty():
        return False
    return bool(row["is_st"].item() == 1)


def stocks_listed(universe: DataFrame, on_date: str) -> list[str]:
    """Return assets listed (or still listed) on `on_date`.

    An asset is "listed" on a date if list_date <= on_date AND
    (delist_date is null OR delist_date >= on_date).

    universe must have: asset, list_date (str YYYYMMDD), delist_date (str|null).
    """
    return universe.filter(
        (pl.col("list_date") <= on_date)
        & (pl.col("delist_date").is_null() | (pl.col("delist_date") >= on_date))
    )["asset"].to_list()


def days_since_ipo(universe: DataFrame, asset: str, on_date: str) -> int:
    """Number of calendar days from asset's list_date to on_date (inclusive of both ends).

    Returns -1 if the asset is not yet listed on `on_date`.
    Raises ValueError if asset not in universe.
    """
    row = universe.filter(pl.col("asset") == asset)
    if row.is_empty():
        raise ValueError(f"asset {asset!r} not in universe")
    list_date_str = row["list_date"].item()
    list_date = _parse(list_date_str)
    target = _parse(on_date)
    if target < list_date:
        return -1
    return (target - list_date).days + 1


def get_name(universe: DataFrame, asset: str) -> str | None:
    """Return asset's name, or None if not in universe."""
    row = universe.filter(pl.col("asset") == asset)
    if row.is_empty():
        return None
    return row["name"].item()


def _parse(s: str) -> date:
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
