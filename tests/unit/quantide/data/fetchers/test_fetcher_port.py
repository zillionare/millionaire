"""数据源端口契约与多源切换的单元测试。"""

from __future__ import annotations

import datetime

import pandas as pd

from quantide.core.ports import DataFetcherPort, HistoricalDataFetcherPort
from quantide.core.ports.data_fetcher import (
    STANDARD_BAR_COLUMNS,
    STANDARD_INDEX_BAR_COLUMNS,
    STANDARD_INDEX_WEIGHT_COLUMNS,
    STANDARD_MINUTE_BAR_COLUMNS,
    STANDARD_STOCK_LIST_COLUMNS,
)
from quantide.data.fetchers.registry import get_data_fetcher
from quantide.data.fetchers.tencent import TencentDataFetcher
from quantide.data.fetchers.tushare import TushareDataFetcher


def test_data_fetcher_port_has_explicit_column_contracts():
    """端口契约暴露标准化字段集。"""
    assert "date" in STANDARD_BAR_COLUMNS and "asset" in STANDARD_BAR_COLUMNS
    assert (
        "date" in STANDARD_INDEX_BAR_COLUMNS
        and "index_code" in STANDARD_INDEX_BAR_COLUMNS
    )
    assert "con_code" in STANDARD_INDEX_WEIGHT_COLUMNS
    assert STANDARD_STOCK_LIST_COLUMNS[0] == "asset"
    assert STANDARD_MINUTE_BAR_COLUMNS == [
        "date",
        "asset",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ]


def test_port_protocol_methods_exist():
    """协议声明全部方法（含分钟线与实时快照）。"""
    expected = [
        "fetch_calendar",
        "fetch_stock_list",
        "fetch_adjust_factor",
        "fetch_bars",
        "fetch_limit_price",
        "fetch_st_info",
        "fetch_bars_ext",
        "fetch_daily_basic",
        "fetch_index_bars",
        "fetch_index_weights",
        "fetch_minute_bars",
        "fetch_quote_snapshot",
    ]
    for name in expected:
        assert hasattr(DataFetcherPort, name)


def test_tushare_fetcher_implements_port():
    """Tushare 适配器实现标准端口。"""
    fetcher = TushareDataFetcher()
    assert isinstance(fetcher, HistoricalDataFetcherPort)
    assert fetcher.source_name == "tushare"
    for name in [
        "fetch_calendar",
        "fetch_stock_list",
        "fetch_bars_ext",
        "fetch_index_bars",
        "fetch_index_weights",
    ]:
        assert callable(getattr(fetcher, name))


def test_tencent_fetcher_registered_and_switchable():
    """注册表可按名称取到腾讯适配器；默认仍为 tushare。"""
    tencent = get_data_fetcher("tencent")
    assert isinstance(tencent, TencentDataFetcher)
    assert tencent.source_name == "tencent"

    default_fetcher = get_data_fetcher()
    assert isinstance(default_fetcher, TushareDataFetcher)


def test_tencent_unsupported_methods_report_errors():
    """腾讯不覆盖的能力返回空表 + 明确错误，让聚合器回落到主源。"""
    fetcher = TencentDataFetcher()
    day = datetime.date(2024, 1, 2)

    for method in (
        fetcher.fetch_bars,
        fetcher.fetch_adjust_factor,
        fetcher.fetch_limit_price,
        fetcher.fetch_st_info,
        fetcher.fetch_daily_basic,
    ):
        frame, errors = method(day)
        assert isinstance(frame, pd.DataFrame)
        assert frame.empty
        assert errors

    frame, errors = fetcher.fetch_index_weights(["000300.SH"], [day])
    assert frame.empty
    assert errors
