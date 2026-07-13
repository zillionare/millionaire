"""FR-0700 AC-84..91: coverage recovery for quantide/data/stores/index_bars.py.

补充 IndexBarsStore 的 __init__ 分区开关、空存储读写、start/end/symbols 过滤、
非 eager 返回、fetch 移除提示、rec_counts_per_date 日期过滤等分支覆盖。
"""

import datetime as dt

import polars as pl
import pytest

from quantide.data.stores.index_bars import IndexBarsStore


class _CalendarStub:
    """最小化的日历占位，IndexBarsStore 初始化仅需该对象存在。"""


def _index_bars_df() -> pl.DataFrame:
    """构造 3 日期 × 2 指数的最小行情数据。"""
    return pl.DataFrame(
        {
            "date": [
                dt.datetime(2024, 1, 2),
                dt.datetime(2024, 1, 2),
                dt.datetime(2024, 1, 3),
                dt.datetime(2024, 1, 3),
                dt.datetime(2024, 1, 4),
                dt.datetime(2024, 1, 4),
            ],
            "sector_id": ["S1", "S2", "S1", "S2", "S1", "S2"],
            "open": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "close": [1.1, 2.1, 3.1, 4.1, 5.1, 6.1],
        }
    )


def test_index_bars_init_with_dot_parquet_suffix_uses_no_partition(tmp_path):
    """AC-FR0700-84: 传入 .parquet 路径时 partition_by 关闭（None）。"""
    store = IndexBarsStore(tmp_path / "single.parquet", _CalendarStub())

    assert store._partition_by is None


def test_index_bars_get_empty_store_returns_empty_dataframe_eager(tmp_path):
    """AC-FR0700-85: 空存储 eager 模式返回空 DataFrame。"""
    store = IndexBarsStore(tmp_path / "index", _CalendarStub())

    result = store.get()

    assert isinstance(result, pl.DataFrame)
    assert len(result) == 0


def test_index_bars_get_empty_store_returns_empty_lazyframe_when_not_eager(tmp_path):
    """AC-FR0700-86: 空存储非 eager 模式返回空 LazyFrame。"""
    store = IndexBarsStore(tmp_path / "index", _CalendarStub())

    result = store.get(eager_mode=False)

    assert isinstance(result, pl.LazyFrame)
    assert result.collect().height == 0


def test_index_bars_get_filters_by_start_end_symbols_with_real_data(tmp_path):
    """AC-FR0700-87: start/end/symbols 过滤返回预期 (date, sector_id) 元组集合。"""
    store = IndexBarsStore(tmp_path / "index", _CalendarStub())
    store.append_data(_index_bars_df())

    result = store.get(
        symbols=["S1"],
        start=dt.date(2024, 1, 3),
        end=dt.date(2024, 1, 4),
    )

    pairs = set(zip(result["date"].to_list(), result["sector_id"].to_list(), strict=True))
    assert pairs == {
        (dt.datetime(2024, 1, 3), "S1"),
        (dt.datetime(2024, 1, 4), "S1"),
    }
    assert len(result) == 2


def test_index_bars_get_eager_false_returns_lazyframe(tmp_path):
    """AC-FR0700-88: 有数据时 eager_mode=False 返回 LazyFrame 实例。"""
    store = IndexBarsStore(tmp_path / "index", _CalendarStub())
    store.append_data(_index_bars_df())

    result = store.get(eager_mode=False)

    assert isinstance(result, pl.LazyFrame)


def test_index_bars_fetch_raises_runtime_error_with_removed_message(tmp_path):
    """AC-FR0700-89: fetch 调用抛出 RuntimeError 并携带主体移除提示。"""
    store = IndexBarsStore(tmp_path / "index", _CalendarStub())

    with pytest.raises(RuntimeError, match="主体移除"):
        store.fetch("S1", dt.date(2024, 1, 1), dt.date(2024, 1, 2))


def test_index_bars_rec_counts_per_date_empty_store_returns_empty_dict(tmp_path):
    """AC-FR0700-90: 空存储 rec_counts_per_date 返回空字典。"""
    store = IndexBarsStore(tmp_path / "index", _CalendarStub())

    result = store.rec_counts_per_date()

    assert result == {}


def test_index_bars_rec_counts_per_date_filters_by_start_end_with_real_data(tmp_path):
    """AC-FR0700-91: rec_counts_per_date 按 start/end 过滤，仅返回范围内日期及其计数。"""
    store = IndexBarsStore(tmp_path / "index", _CalendarStub())
    store.append_data(_index_bars_df())

    result = store.rec_counts_per_date(start=dt.date(2024, 1, 3), end=dt.date(2024, 1, 3))

    assert result == {dt.date(2024, 1, 3): 2}
