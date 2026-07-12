"""FR-0303 AC-1..AC-4: isolated Parquet storage and index-store contracts."""

import datetime as dt

import polars as pl
import pytest

from quantide.data.stores.base import ParquetStorage
from quantide.data.stores.index_bars import IndexBarsStore


class _CalendarStub:
    """Minimal calendar boundary needed by storage-only tests."""


def _bars() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "date": [dt.datetime(2023, 12, 29), dt.datetime(2024, 1, 2)],
            "asset": ["A", "A"],
            "close": [10.0, 11.0],
        }
    )


def test_parquet_store_appends_deduplicates_and_filters_closed_date_range(tmp_path):
    """FR-0303 AC-1/2: temp store tracks dates and returns inclusive selected columns."""
    store = ParquetStorage("bars", tmp_path / "bars.parquet", _CalendarStub())
    store.append_data(_bars())
    store.append_data(pl.DataFrame({"date": [dt.datetime(2024, 1, 2)], "asset": ["A"], "close": [12.0]}))

    result = store.get(start=dt.date(2024, 1, 2), end=dt.date(2024, 1, 2), cols=["asset", "close"])

    assert store.available_dates == [dt.date(2023, 12, 29), dt.date(2024, 1, 2)]
    assert result.to_dicts() == [{"asset": "A", "close": 12.0}]
    assert isinstance(store.get(eager_mode=False), pl.LazyFrame)


def test_index_store_filters_sector_and_reports_removed_remote_fetch(tmp_path):
    """FR-0303 AC-3/4: local index reads filter sector/date; remote fetch is retired."""
    store = IndexBarsStore(tmp_path / "index", _CalendarStub())
    store.append_data(
        pl.DataFrame(
            {
                "date": [dt.datetime(2024, 1, 2), dt.datetime(2024, 1, 3)],
                "sector_id": ["S1", "S2"],
                "open": [1.0, 2.0],
            }
        )
    )

    result = store.get(["S1"], dt.date(2024, 1, 2), dt.date(2024, 1, 2))

    assert result["sector_id"].to_list() == ["S1"]
    assert store.rec_counts_per_date() == {dt.date(2024, 1, 2): 1, dt.date(2024, 1, 3): 1}
    with pytest.raises(RuntimeError, match="主体移除"):
        store.fetch("S1", dt.date(2024, 1, 1), dt.date(2024, 1, 2))
