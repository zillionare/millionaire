"""B09-stores-base: gaps in quantide/data/stores/base.py.

Targets uncovered helpers and branches: ``_as_datetime_bound`` /
``_as_date_bound`` datetime inputs, ``default_error_handler``, ``_dates_file_path``
(partition vs single file), ``_ensure_partition_col`` for year/month/day, the
``__len__`` exception path, ``append_data`` (empty polars DataFrame, LazyFrame,
unsupported type), ``_group_dates`` (month + unknown-key fallback), and the
``partition_by`` + ``.parquet`` suffix ValueError at init.
"""

from __future__ import annotations

import datetime
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import polars as pl
import pytest

from quantide.data.models.calendar import Calendar
from quantide.data.stores.base import (
    ParquetStorage,
    _as_date_bound,
    _as_datetime_bound,
)


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def calendar(asset_dir):
    cal = Calendar()
    cal.load(asset_dir / "baseline_calendar.parquet")
    return cal


@pytest.fixture
def tmp_store_path():
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _make_bars(start: str, end: str, n_assets: int = 2) -> pd.DataFrame:
    """Small bars DataFrame with ``datetime64[ms]`` date column."""
    dates = pd.bdate_range(start, end)
    rows = []
    for d in dates:
        for i in range(n_assets):
            rows.append({
                "date": d,
                "asset": f"{i:06d}.SZ",
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 1000.0,
                "amount": 10000.0,
            })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).astype("datetime64[ms]")
    return df


# ---------------------------------------------------------------------------
# _as_datetime_bound / _as_date_bound - datetime inputs (lines 25, 33-35)
# ---------------------------------------------------------------------------


def test_as_datetime_bound_with_datetime_returns_lit_datetime():
    """[AC-FR0700-130] _as_datetime_bound keeps datetime values as-is."""
    dt = datetime.datetime(2024, 6, 15, 10, 30)
    expr = _as_datetime_bound(dt)
    # pl.lit(datetime) -> Datetime dtype
    df = pl.DataFrame({"x": [0]}).with_columns(expr.alias("d"))
    assert df.schema["d"] == pl.Datetime


def test_as_date_bound_with_datetime_converts_to_date():
    """[AC-FR0700-130] _as_date_bound converts datetime to date."""
    dt = datetime.datetime(2024, 6, 15, 10, 30)
    expr = _as_date_bound(dt)
    df = pl.DataFrame({"x": [0]}).with_columns(expr.alias("d"))
    assert df.schema["d"] == pl.Date


def test_as_date_bound_with_date_returns_lit_date():
    """[AC-FR0700-130] _as_date_bound keeps date values as Date lit."""
    d = datetime.date(2024, 6, 15)
    expr = _as_date_bound(d)
    df = pl.DataFrame({"x": [0]}).with_columns(expr.alias("d"))
    assert df.schema["d"] == pl.Date
    assert df.item(0, "d") == d


# ---------------------------------------------------------------------------
# default_error_handler (line 152-154)
# ---------------------------------------------------------------------------


def test_default_error_handler_logs_each_error(asset_dir, tmp_store_path):
    """[AC-FR0700-131] default_error_handler iterates and logs each error."""
    store_path = tmp_store_path / "err.parquet"
    store = ParquetStorage("err", store_path, Calendar())
    errors = [
        ["000001.SZ", datetime.date(2024, 1, 2), "boom1"],
        ["000002.SZ", datetime.date(2024, 1, 3), "boom2"],
    ]
    # Should not raise; logs via logger.
    store.default_error_handler(errors)
    # Default error handler is set as self._error_handler when none is given.
    assert store._error_handler == store.default_error_handler


# ---------------------------------------------------------------------------
# _dates_file_path (lines 156-161)
# ---------------------------------------------------------------------------


def test_dates_file_path_partition_mode(tmp_store_path, calendar):
    """[AC-FR0700-132] partition mode -> dates.pq in the parent directory."""
    store_dir = tmp_store_path / "year"
    store_dir.mkdir()
    store = ParquetStorage("yearly", store_dir, calendar, partition_by="year")
    path = store._dates_file_path()
    assert path.name == "dates.pq"
    assert path.parent == store_dir.parent


def test_dates_file_path_single_file_mode(tmp_store_path, calendar):
    """[AC-FR0700-132] single-file mode -> {store_name}-dates.pq next to the file."""
    store_file = tmp_store_path / "single.parquet"
    store = ParquetStorage("single", store_file, calendar)
    path = store._dates_file_path()
    assert path.name == "single-dates.pq"
    assert path.parent == store_file.parent


# ---------------------------------------------------------------------------
# _ensure_partition_col (lines 225-239)
# ---------------------------------------------------------------------------


def test_ensure_partition_col_year_adds_year_column(tmp_store_path, calendar):
    """[AC-FR0700-133] year partition -> adds partition_key_year column."""
    store_dir = tmp_store_path / "year"
    store_dir.mkdir()
    store = ParquetStorage("yearly", store_dir, calendar, partition_by="year")
    lf = pl.DataFrame({
        "date": [
            datetime.datetime(2024, 1, 1),
            datetime.datetime(2024, 1, 2),
            datetime.datetime(2024, 1, 3),
        ],
        "asset": ["000001.SZ", "000001.SZ", "000001.SZ"],
        "close": [10.0, 10.5, 11.0],
    }).lazy()
    out = store._ensure_partition_col(lf).collect()
    assert "partition_key_year" in out.columns
    assert out["partition_key_year"].to_list() == [2024, 2024, 2024]


def test_ensure_partition_col_month_adds_month_column(tmp_store_path, calendar):
    """[AC-FR0700-133] month partition -> adds partition_key_month YYYY-MM column."""
    store_dir = tmp_store_path / "month"
    store_dir.mkdir()
    store = ParquetStorage("monthly", store_dir, calendar, partition_by="month")
    lf = pl.DataFrame({
        "date": [
            datetime.datetime(2024, 1, 15),
            datetime.datetime(2024, 2, 15),
        ],
        "asset": ["000001.SZ", "000001.SZ"],
        "close": [10.0, 11.0],
    }).lazy()
    out = store._ensure_partition_col(lf).collect()
    assert "partition_key_month" in out.columns
    assert "2024-01" in out["partition_key_month"].to_list()
    assert "2024-02" in out["partition_key_month"].to_list()


def test_ensure_partition_col_day_adds_day_column(tmp_store_path, calendar):
    """[AC-FR0700-133] day partition -> adds partition_key_day YYYY-MM-DD column."""
    store_dir = tmp_store_path / "day"
    store_dir.mkdir()
    store = ParquetStorage("daily", store_dir, calendar, partition_by="day")
    lf = pl.DataFrame({
        "date": [
            datetime.datetime(2024, 1, 1),
            datetime.datetime(2024, 1, 2),
        ],
        "asset": ["000001.SZ", "000001.SZ"],
        "close": [10.0, 11.0],
    }).lazy()
    out = store._ensure_partition_col(lf).collect()
    assert "partition_key_day" in out.columns
    assert "2024-01-01" in out["partition_key_day"].to_list()


def test_ensure_partition_col_noop_when_already_present(tmp_store_path, calendar):
    """[AC-FR0700-133] When the partition column is already present, no-op."""
    store_dir = tmp_store_path / "year"
    store_dir.mkdir()
    store = ParquetStorage("yearly", store_dir, calendar, partition_by="year")
    lf = pl.DataFrame({
        "date": [
            datetime.datetime(2024, 1, 1),
            datetime.datetime(2024, 1, 2),
        ],
        "asset": ["000001.SZ", "000001.SZ"],
        "close": [10.0, 11.0],
        "partition_key_year": [2024, 2024],
    }).lazy()
    out = store._ensure_partition_col(lf).collect()
    assert "partition_key_year" in out.columns
    # Values preserved unchanged.
    assert out["partition_key_year"].to_list() == [2024, 2024]


# ---------------------------------------------------------------------------
# partition_by with .parquet suffix raises ValueError (line 78)
# ---------------------------------------------------------------------------


def test_partition_by_with_parquet_suffix_raises_value_error(tmp_store_path, calendar):
    """[AC-FR0700-134] partition_by is rejected when store_path is a .parquet file."""
    store_file = tmp_store_path / "illegal.parquet"
    with pytest.raises(ValueError, match="partition_by is not allowed"):
        ParquetStorage("illegal", store_file, calendar, partition_by="year")


# ---------------------------------------------------------------------------
# __len__ exception path returns 0 (line 115)
# ---------------------------------------------------------------------------


def test_len_returns_zero_on_scan_exception(tmp_store_path, calendar):
    """[AC-FR0700-135] __len__ returns 0 when _scan_store raises."""
    store_file = tmp_store_path / "broken.parquet"
    store = ParquetStorage("broken", store_file, calendar)
    # Force _scan_store to raise by replacing it with a broken stub.
    store._scan_store = MagicMock(side_effect=Exception("scan broken"))
    assert len(store) == 0


# ---------------------------------------------------------------------------
# append_data: empty polars DataFrame, LazyFrame, unsupported type (lines 596-601)
# ---------------------------------------------------------------------------


def test_append_data_empty_polars_dataframe_is_noop(tmp_store_path, calendar):
    """[AC-FR0700-136] append_data with empty polars DataFrame returns early."""
    store_file = tmp_store_path / "empty.parquet"
    store = ParquetStorage("empty", store_file, calendar)
    store.append_data(pl.DataFrame())
    # No file should have been written.
    assert not store_file.exists()


def test_append_data_polars_lazyframe_writes(tmp_store_path, calendar):
    """[AC-FR0700-136] append_data accepts polars LazyFrame and writes it."""
    store_file = tmp_store_path / "lazy.parquet"
    store = ParquetStorage("lazy", store_file, calendar)
    lf = pl.DataFrame({
        "date": [datetime.datetime(2024, 1, 2)],
        "asset": ["000001.SZ"],
        "close": [10.0],
    }).lazy()
    store.append_data(lf)
    assert store_file.exists()
    df = pl.read_parquet(store_file)
    assert len(df) == 1


def test_append_data_unsupported_type_raises_typeerror(tmp_store_path, calendar):
    """[AC-FR0700-136] append_data with unsupported type raises TypeError."""
    store_file = tmp_store_path / "bad.parquet"
    store = ParquetStorage("bad", store_file, calendar)
    with pytest.raises(TypeError, match="Unsupported data type"):
        store.append_data(12345)


# ---------------------------------------------------------------------------
# _group_dates: month partition + unknown-key fallback (lines 750, 754)
# ---------------------------------------------------------------------------


def test_group_dates_by_month_returns_chunks_per_month(tmp_store_path, calendar):
    """[AC-FR0700-137] _group_dates returns one chunk per month for month partition."""
    store_dir = tmp_store_path / "month"
    store_dir.mkdir()
    store = ParquetStorage("monthly", store_dir, calendar, partition_by="month")
    dates = [
        datetime.date(2024, 1, 5),
        datetime.date(2024, 1, 20),
        datetime.date(2024, 2, 15),
    ]
    chunks = store._group_dates(dates)
    assert len(chunks) == 2  # 2024-01 + 2024-02
    flat = [d for chunk in chunks for d in chunk]
    assert sorted(flat) == sorted(dates)


def test_group_dates_no_partition_groups_by_month(tmp_store_path, calendar):
    """[AC-FR0700-137] _group_dates with no partition groups by YYYY-MM by default."""
    store_file = tmp_store_path / "nopartition.parquet"
    store = ParquetStorage("np", store_file, calendar)
    dates = [
        datetime.date(2024, 1, 5),
        datetime.date(2024, 2, 15),
    ]
    chunks = store._group_dates(dates)
    assert len(chunks) == 2  # default key_fn groups by %Y-%m
    flat = [d for chunk in chunks for d in chunk]
    assert sorted(flat) == sorted(dates)


# ---------------------------------------------------------------------------
# get / get_by_date with lf is None -> empty eager / lazy (lines 676-679, 727-730)
# ---------------------------------------------------------------------------


def test_get_empty_store_eager_returns_empty_dataframe(tmp_store_path, calendar):
    """[AC-FR0700-138] get() on empty store in eager mode -> empty pl.DataFrame."""
    store_file = tmp_store_path / "none.parquet"
    store = ParquetStorage("none", store_file, calendar)
    df = store.get()
    assert isinstance(df, pl.DataFrame)
    assert len(df) == 0


def test_get_empty_store_lazy_returns_empty_lazyframe(tmp_store_path, calendar):
    """[AC-FR0700-138] get() on empty store in lazy mode -> empty pl.LazyFrame."""
    store_file = tmp_store_path / "none.parquet"
    store = ParquetStorage("none", store_file, calendar)
    lf = store.get(eager_mode=False)
    assert isinstance(lf, pl.LazyFrame)


def test_get_by_date_empty_store_eager_returns_empty_dataframe(tmp_store_path, calendar):
    """[AC-FR0700-138] get_by_date on empty store in eager mode -> empty pl.DataFrame."""
    store_file = tmp_store_path / "none.parquet"
    store = ParquetStorage("none", store_file, calendar)
    df = store.get_by_date(datetime.date(2024, 1, 5))
    assert isinstance(df, pl.DataFrame)
    assert len(df) == 0


def test_get_by_date_empty_store_lazy_returns_empty_lazyframe(tmp_store_path, calendar):
    """[AC-FR0700-138] get_by_date on empty store in lazy mode -> empty pl.LazyFrame."""
    store_file = tmp_store_path / "none.parquet"
    store = ParquetStorage("none", store_file, calendar)
    lf = store.get_by_date(datetime.date(2024, 1, 5), eager_mode=False)
    assert isinstance(lf, pl.LazyFrame)
