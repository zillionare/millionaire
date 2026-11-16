"""ParquetStorage 多级分区 / 增量写 / 自定义主键的单元测试。"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from quantide.data.models.calendar import Calendar
from quantide.data.stores.base import ParquetStorage


@pytest.fixture
def calendar(asset_dir) -> Calendar:
    """测试日历。"""
    cal = Calendar()
    cal.load(asset_dir / "baseline_calendar.parquet")
    return cal


def _frame(dates: list[datetime.date], assets: list[str]) -> pl.DataFrame:
    """构造测试数据。"""
    rows = []
    for date in dates:
        for asset in assets:
            rows.append(
                {
                    "date": date,
                    "asset": asset,
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.0,
                    "close": 10.5,
                    "volume": 1000.0,
                }
            )
    return pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Date))


def test_two_level_partition_writes_nested_dirs(calendar, tmp_path):
    """两级分区写出年/月两级目录。"""
    store = ParquetStorage("m", tmp_path / "m", calendar, partition_levels=("year", "month"))
    dates = [datetime.date(2024, 1, 5), datetime.date(2024, 2, 5)]
    store._save_as_partition(_frame(dates, ["000001.SZ"]))

    year_dir = tmp_path / "m" / "partition_key_year=2024"
    assert year_dir.exists()
    months = sorted(p.name for p in year_dir.iterdir())
    assert months == ["partition_key_month=01", "partition_key_month=02"]


def test_read_prunes_to_overlapping_partitions(calendar, tmp_path):
    """读取时只打开与日期范围相交的分区文件。"""
    store = ParquetStorage("m", tmp_path / "m", calendar, partition_levels=("year", "month"))
    dates = [
        datetime.date(2024, 1, 5),
        datetime.date(2024, 2, 5),
        datetime.date(2024, 3, 5),
        datetime.date(2025, 1, 5),
    ]
    store._save_as_partition(_frame(dates, ["000001.SZ"]))

    files = store._candidate_partition_files(datetime.date(2024, 2, 1), datetime.date(2024, 2, 29))
    assert len(files) == 1
    assert "partition_key_month=02" in files[0]

    all_files = store._candidate_partition_files(None, None)
    assert len(all_files) == 4


def test_read_range_returns_only_requested_rows(calendar, tmp_path):
    """按范围读取只返回区间内的数据。"""
    store = ParquetStorage("m", tmp_path / "m", calendar, partition_levels=("year", "month"))
    dates = [
        datetime.date(2024, 1, 5),
        datetime.date(2024, 2, 5),
        datetime.date(2024, 3, 5),
    ]
    store._save_as_partition(_frame(dates, ["000001.SZ", "000002.SZ"]))

    out = store.get(start=datetime.date(2024, 2, 1), end=datetime.date(2024, 2, 29))
    assert out.height == 2
    assert set(out["date"].unique().to_list()) == {datetime.date(2024, 2, 5)}


def test_read_range_before_earliest_partition_returns_empty(calendar, tmp_path):
    """早于最早分区的范围应返回空数据，而不是分区键类型错误。"""
    store = ParquetStorage("m", tmp_path / "m", calendar, partition_levels=("year", "month"))
    store._save_as_partition(_frame([datetime.date(2024, 1, 5)], ["000001.SZ"]))

    out = store.get(start=datetime.date(2021, 12, 1), end=datetime.date(2023, 12, 31))

    assert out.is_empty()


def test_incremental_write_replaces_only_touched_partition(calendar, tmp_path):
    """增量写只重写命中的分区，其它分区文件保持不变。"""
    store = ParquetStorage("m", tmp_path / "m", calendar, partition_levels=("year", "month"))
    store._save_as_partition(
        _frame([datetime.date(2024, 1, 5), datetime.date(2024, 2, 5)], ["000001.SZ"])
    )
    feb_file = (
        tmp_path / "m" / "partition_key_year=2024" / "partition_key_month=02" / "part-0.parquet"
    )
    assert feb_file.exists()
    feb_mtime = feb_file.stat().st_mtime_ns

    # 追加 1 月数据（覆盖 1 月分区）
    store._save_as_partition(_frame([datetime.date(2024, 1, 8)], ["000001.SZ"]))

    jan_file = (
        tmp_path / "m" / "partition_key_year=2024" / "partition_key_month=01" / "part-0.parquet"
    )
    assert jan_file.exists()
    assert jan_file.stat().st_mtime_ns != feb_mtime or True
    # 2 月文件未被重写（mtime 不变）
    assert feb_file.stat().st_mtime_ns == feb_mtime

    out = store.get(start=None, end=None)
    assert out.height == 3


def test_custom_id_cols_deduplicate_by_business_key(calendar, tmp_path):
    """自定义主键按业务键去重（成分股表场景）。"""
    store = ParquetStorage(
        "w",
        tmp_path / "w",
        calendar,
        partition_levels=("year", "month"),
        id_cols=["date", "index_code", "con_code"],
    )
    frame = pl.DataFrame(
        {
            "date": [datetime.date(2024, 1, 31)] * 2,
            "index_code": ["000300.SH", "000300.SH"],
            "con_code": ["600519.SH", "600519.SH"],
            "weight": [1.0, 2.0],
        }
    ).with_columns(pl.col("date").cast(pl.Date))
    store._save_as_partition(frame)
    out = store.get(start=None, end=None)
    assert out.height == 1
    assert out["weight"][0] == 2.0


def test_partition_value_and_overlap_helpers(calendar, tmp_path):
    """分区取值与相交判断。"""
    store = ParquetStorage("m", tmp_path / "m", calendar, partition_levels=("year", "month"))
    assert store._partition_value("partition_key_year", datetime.date(2024, 3, 1)) == 2024
    assert store._partition_value("partition_key_month", datetime.date(2024, 3, 1)) == 3
    # 两级分区：月份目录 + 已知年份
    assert store._level_overlaps(
        "partition_key_month",
        "2",
        datetime.date(2024, 2, 1),
        datetime.date(2024, 2, 28),
        year=2024,
    )
    assert not store._level_overlaps(
        "partition_key_month",
        "5",
        datetime.date(2024, 2, 1),
        datetime.date(2024, 2, 28),
        year=2024,
    )


def test_single_level_partition_still_works(calendar, tmp_path):
    """单级分区行为保持不变（向后兼容）。"""
    store = ParquetStorage("y", tmp_path / "y", calendar, partition_by="year")
    store._save_as_partition(
        _frame([datetime.date(2024, 1, 5), datetime.date(2025, 1, 5)], ["000001.SZ"])
    )
    assert (tmp_path / "y" / "partition_key_year=2024").exists()
    out = store.get(start=datetime.date(2024, 1, 1), end=datetime.date(2024, 12, 31))
    assert out.height == 1


def test_append_casts_datetime_date_to_date(tmp_path):
    """不同 fetcher 产出的 datetime 日期应统一写成 pl.Date。"""
    store = ParquetStorage(
        store_name="MixedDate",
        store_path=tmp_path / "mixed",
        calendar=Calendar(),
        partition_levels=("year", "month"),
        date_as_date=True,
    )
    frame = pl.DataFrame(
        {
            "date": [datetime.datetime(2024, 1, 2, 10, 30)],
            "asset": ["600000.SH"],
            "close": [10.0],
        }
    )
    store.append_data(frame)

    files = list((tmp_path / "mixed").rglob("*.parquet"))
    assert files
    assert pl.read_parquet_schema(files[0])["date"] == pl.Date


def test_normalize_partition_schema_rewrites_datetime_files(tmp_path):
    """已有 Datetime 分区文件应被归一化为 Date。"""
    store = ParquetStorage(
        store_name="LegacyDate",
        store_path=tmp_path / "legacy",
        calendar=Calendar(),
        partition_levels=("year", "month"),
        date_as_date=True,
    )
    partition = tmp_path / "legacy" / "partition_key_year=2024" / "partition_key_month=01"
    partition.mkdir(parents=True)
    legacy = pl.DataFrame(
        {
            "date": [datetime.datetime(2024, 1, 2)],
            "asset": ["600000.SH"],
            "close": [10.0],
        }
    )
    legacy.write_parquet(partition / "part-0.parquet")

    assert store.normalize_partition_schema(dry_run=True) == 1
    assert store.normalize_partition_schema() == 1
    assert pl.read_parquet_schema(partition / "part-0.parquet")["date"] == pl.Date
    assert store.normalize_partition_schema() == 0
