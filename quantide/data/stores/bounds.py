"""Date bounds shared by partitioned and single-file stores."""

import datetime

import polars as pl


def _as_datetime_bound(value: datetime.date | datetime.datetime) -> pl.Expr:
    if isinstance(value, datetime.datetime):
        return pl.lit(value)
    return pl.lit(
        datetime.datetime.combine(value, datetime.time.min),
        dtype=pl.Datetime("ms"),
    )


def _as_date_bound(value: datetime.date | datetime.datetime) -> pl.Expr:
    if isinstance(value, datetime.datetime):
        value = value.date()
    return pl.lit(
        datetime.datetime.combine(value, datetime.time.min),
        dtype=pl.Date,
    )
