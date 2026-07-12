"""Ground truth implementations of FR-014 (Calendar).

These compute expected values from raw 2022 data fixtures WITHOUT importing
the `quantide.*` module under test. Tests can use these to verify impl
correctness per test plan §3.

Restriction: This module MUST NOT import `quantide.*`. Only polars, numpy,
pandas, empyrical, stdlib are allowed. (Verified by test_ground_truth_purity.)
"""
from __future__ import annotations

from typing import Iterable

import polars as pl
from polars import DataFrame


def is_trade_day(calendar: DataFrame, date: str) -> bool:
    """Return True iff `date` is an open trading day in `calendar`.

    calendar must have columns: `date` (str YYYYMMDD) and `is_open` (int 0/1).
    """
    row = calendar.filter(pl.col("date") == date)
    if row.is_empty():
        return False
    return bool(row["is_open"].item() == 1)


def day_shift(calendar: DataFrame, date: str, n: int) -> str:
    """Shift `date` by `n` trading days. n=0 returns `date` if open, else next open.

    n>0: roll forward by n open days.
    n<0: roll backward by |n| open days.
    n=0: if `date` is open, return it; else return the next open day.
    """
    opens = calendar.filter(pl.col("is_open") == 1).sort("date")["date"].to_list()
    if date not in opens:
        if n > 0:
            idx = next((i for i, d in enumerate(opens) if d > date), len(opens))
        elif n < 0:
            idx = next((len(opens) - 1 - i for i, d in enumerate(reversed(opens)) if d < date), -1)
            idx = len(opens) + idx + 1 if idx < 0 else idx
        else:
            idx = next((i for i, d in enumerate(opens) if d >= date), len(opens))
    else:
        idx = opens.index(date)

    target_idx = idx + n
    if target_idx < 0 or target_idx >= len(opens):
        raise ValueError(
            f"day_shift({date}, {n}) out of range: idx={idx} -> {target_idx} "
            f"(opens has {len(opens)} entries)"
        )
    return opens[target_idx]


def count_trading_days(calendar: DataFrame, start: str, end: str) -> int:
    """Count open trading days in [start, end] (inclusive).

    start/end are YYYYMMDD strings.
    """
    return calendar.filter(
        (pl.col("is_open") == 1) & (pl.col("date") >= start) & (pl.col("date") <= end)
    ).height


def last_trade_date(calendar: DataFrame, on_or_before: str) -> str | None:
    """Return the latest open trading day on or before `on_or_before`.

    Returns None if no such day exists in the calendar.
    """
    opens = calendar.filter(
        (pl.col("is_open") == 1) & (pl.col("date") <= on_or_before)
    ).sort("date", descending=True)
    if opens.is_empty():
        return None
    return opens["date"].item()


def first_trade_date(calendar: DataFrame, on_or_after: str) -> str | None:
    """Return the earliest open trading day on or after `on_or_after`."""
    opens = calendar.filter(
        (pl.col("is_open") == 1) & (pl.col("date") >= on_or_after)
    ).sort("date")
    if opens.is_empty():
        return None
    return opens["date"].item()
