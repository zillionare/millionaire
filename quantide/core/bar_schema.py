"""Canonical market bar columns and typed empty frames at data boundaries."""

import polars as pl

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume", "amount"]
STANDARD_MINUTE_BAR_COLUMNS = ["date", "asset", *OHLCV_COLUMNS]
STANDARD_BAR_COLUMNS = [*STANDARD_MINUTE_BAR_COLUMNS, "adjust", "is_st", "up_limit", "down_limit"]
STANDARD_INDEX_BAR_COLUMNS = ["date", "index_code", *OHLCV_COLUMNS]
STANDARD_INDEX_WEIGHT_COLUMNS = ["date", "index_code", "con_code", "weight"]
STANDARD_STOCK_LIST_COLUMNS = ["asset", "name", "pinyin", "list_date", "delist_date"]


def bar_schema(
    *,
    time_column: str = "date",
    time_type: pl.DataType | type[pl.DataType] = pl.Date,
    asset_column: str = "asset",
    extended: bool = True,
) -> dict[str, pl.DataType | type[pl.DataType]]:
    """Produce a fresh schema for stock, index and strategy-feed frames."""
    schema: dict[str, pl.DataType | type[pl.DataType]] = {
        time_column: time_type,
        asset_column: pl.Utf8,
    }
    schema.update(dict.fromkeys(OHLCV_COLUMNS, pl.Float64))
    if extended:
        schema.update(
            adjust=pl.Float64, is_st=pl.Boolean, up_limit=pl.Float64, down_limit=pl.Float64
        )
    return schema
