"""Forward-close label contracts for the ML momentum strategy."""

from __future__ import annotations

import datetime
from typing import Any

import polars as pl

LABEL_KINDS = ("raw_return", "excess_mean", "cs_rank")


def _cross_section_label(frame: pl.DataFrame, label_kind: str) -> pl.DataFrame:
    label = "future_n_trading_day_close_return"
    if label_kind == "raw_return":
        return frame
    date_count = pl.len().over("date")
    immature = pl.col(label).is_null().any().over("date")
    if label_kind == "excess_mean":
        value = pl.col(label) - pl.col(label).mean().over("date")
    else:
        value = pl.col(label).rank(method="average").over("date") / date_count - 0.5
    return frame.with_columns(
        pl.when(~immature & (date_count >= 2))
        .then(value)
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias(label)
    )


def _calendar_module() -> Any:
    """Read through ``_ml_support`` so its calendar override stays authoritative."""
    from quantide.strategies.example import _ml_support

    return _ml_support.calendar


def _authoritative_exit_dates(
    dates: list[datetime.date], horizon: int
) -> dict[datetime.date, datetime.date] | None:
    """Map each signal date to the exact authoritative session ``h`` days later."""
    calendar = _calendar_module()
    if not dates or calendar.day_frames is None:
        return None
    start, end = min(dates), max(dates)
    try:
        sessions = list(calendar.get_trade_dates(start, end))
    except Exception:
        return None
    if not sessions or not set(dates).issubset(set(sessions)):
        return None
    index = {day: position for position, day in enumerate(sessions)}
    mapping: dict[datetime.date, datetime.date] = {}
    for day in dates:
        position = index[day] + horizon
        if position < len(sessions):
            mapping[day] = sessions[position]
    return mapping


def compute_future_close_return_labels(
    df: pl.DataFrame, horizon: int = 3, label_kind: str = "raw_return"
) -> pl.DataFrame:
    """Attach a supervised future close-return target to a daily-bar panel.

    ``horizon`` counts authoritative trading sessions.  A missing exit-day quote
    yields a missing label; it is never silently replaced by the next existing
    row.  ``excess_mean`` and ``cs_rank`` are computed strictly inside each
    signal date's mature cross section; a date with any missing forward price is
    excluded as a whole.  Callers must pass a history frame cut off at the
    signal date when training.
    """
    horizon = max(1, int(horizon))
    if label_kind not in LABEL_KINDS:
        raise ValueError(f"unsupported label_kind: {label_kind}")
    if df.is_empty():
        return df.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("future_n_trading_day_close_return")
        )
    ordered = df.sort(["asset", "date"])
    dates = sorted(
        {value for value in ordered["date"].to_list() if isinstance(value, datetime.date)}
    )
    mapping = _authoritative_exit_dates(dates, horizon)
    close = pl.col("close").cast(pl.Float64)
    if mapping is not None:
        exits = pl.DataFrame(
            {
                "date": list(mapping),
                "_exit_date": list(mapping.values()),
            },
            schema={"date": pl.Date, "_exit_date": pl.Date},
        )
        future = ordered.select(
            "asset",
            pl.col("date").alias("_exit_date"),
            pl.col("close").cast(pl.Float64).alias("_exit_close"),
        )
        labeled = (
            ordered.join(exits, on="date", how="left")
            .join(future, on=["asset", "_exit_date"], how="left")
            .with_columns(
                pl.when(pl.col("_exit_close").is_not_null() & (close != 0.0))
                .then(pl.col("_exit_close") / close - 1.0)
                .otherwise(pl.lit(None, dtype=pl.Float64))
                .alias("future_n_trading_day_close_return")
            )
            .drop("_exit_date", "_exit_close")
        )
    else:
        labeled = ordered.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("future_n_trading_day_close_return")
        )
    return _cross_section_label(labeled, label_kind)


__all__ = [
    "LABEL_KINDS",
    "_authoritative_exit_dates",
    "_cross_section_label",
    "compute_future_close_return_labels",
]
