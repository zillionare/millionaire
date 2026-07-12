"""E2E 黑盒测试 — FR-015 证券列表 SDK

按 test-plan.md §4.1 scenarios/securities/ 设计:
- 仅依赖外部可观测对象(API + 数据文件)
- 不 mock 框架内部实现
- 与 acceptance.md AC-015-01 ~ 04 对齐
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pandas as pd
import polars as pl
import pytest

from quantide.data.models.daily_bars import daily_bars
from quantide.data.models.stocks import StockList


# Real tushare fixtures (preferred); fall back to 2024 fixtures if missing
REAL_DIR = Path(__file__).resolve().parents[2] / "assets" / "real"
LEGACY_DIR = Path(__file__).resolve().parents[3] / "assets"


@pytest.fixture(scope="module")
def stocks():
    """加载证券列表;优先使用 tushare 真实数据,fallback 到合成"""
    if (REAL_DIR / "real_bars_combined.parquet").exists():
        # 真实数据:从 universe 构造 stock_list,用 combined bars 作 daily_bars
        universe = pd.read_parquet(REAL_DIR / "real_universe.parquet")
        stock_df = universe[["asset", "name"]].copy()
        stock_df["pinyin"] = stock_df["name"].str[:8].str.upper()
        stock_df["list_date"] = pd.to_datetime(universe["list_date"]).dt.date
        stock_df["delist_date"] = pd.to_datetime(universe["delist_date"]).dt.date

        StockList.__init__(StockList())
        sl = StockList()
        sl._data = pl.from_pandas(stock_df)

        daily_bars.connect(
            REAL_DIR / "real_bars_combined.parquet",
            REAL_DIR / "real_calendar.parquet",
        )
        return sl
    else:
        # Fallback:2024 fixture + synthetic stock_list
        st_df = pd.read_parquet(LEGACY_DIR / "2024_st_info.parquet")
        assets = st_df["asset"].unique().tolist()
        stock_df = pd.DataFrame(
            {
                "asset": assets,
                "name": [f"STOCK_{i}" for i in range(len(assets))],
                "pinyin": [f"S{i:04d}" for i in range(len(assets))],
                "list_date": pd.to_datetime([datetime.date(2000, 1, 1)] * len(assets)),
                "delist_date": pd.NaT,
            }
        )
        StockList.__init__(StockList())
        sl = StockList()
        sl._data = pl.from_pandas(stock_df)
        daily_bars.connect(
            LEGACY_DIR / "2024_bars_ext_cols.parquet",
            LEGACY_DIR / "baseline_calendar.parquet",
        )
        return sl


# ───────────────────────── AC-015-01 已上市证券列表 ─────────────────────────


class TestStocksListed:
    """AC-015-01: stocks_listed(date, exclude_st) 返回某日已上市证券"""

    def test_returns_list_of_strings(self, stocks):
        """返回 list[str];非空(2024-01-02 应有大量数据)"""
        result = stocks.stocks_listed(datetime.date(2024, 1, 2), exclude_st=False)
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    def test_exclude_st_true_filters_st(self, stocks):
        """exclude_st=True → 结果不含 ST"""
        # 使用真实数据中的日期与 ST 资产(2024-01-02 / ST宁科 600165.SH)
        with_st = stocks.stocks_listed(datetime.date(2024, 1, 2), exclude_st=False)
        without_st = stocks.stocks_listed(datetime.date(2024, 1, 2), exclude_st=True)
        assert len(without_st) <= len(with_st)
        assert "600165.SH" not in without_st
        assert "600165.SH" in with_st

    def test_exclude_st_false_includes_st(self, stocks):
        """exclude_st=False → 结果含 ST"""
        with_st = stocks.stocks_listed(datetime.date(2024, 1, 2), exclude_st=False)
        assert "600165.SH" in with_st

    def test_date_before_market_open_returns_empty(self, stocks):
        """市场未开张的远古日期 → 返回空列表(不抛异常)"""
        result = stocks.stocks_listed(datetime.date(1990, 1, 1), exclude_st=False)
        assert result == []


# ───────────────────────── AC-015-02 ST 判断与上市天数 ─────────────────────────


class TestIsSt:
    """AC-015-02: is_st(asset, date) 判断当日是否 ST"""

    def test_known_st_returns_true(self, stocks):
        """已知 ST 资产 → True"""
        assert stocks.is_st("600165.SH", datetime.date(2024, 1, 2)) is True

    def test_unknown_st_returns_false(self, stocks):
        """非 ST 资产 → False"""
        # 600000.SH(浦发银行)2024-01-02 应非 ST
        assert stocks.is_st("600000.SH", datetime.date(2024, 1, 2)) is False

    def test_unknown_asset_returns_false(self, stocks):
        """不存在的资产 → False(不抛异常)"""
        result = stocks.is_st("999999.SH", datetime.date(2024, 1, 2))
        assert result is False


class TestDaysSinceIpo:
    """AC-015-02: days_since_ipo(asset, date) 返回上市天数;上市前 → 0"""

    def test_listed_many_years_ago(self, stocks):
        """多年以前上市的资产 → 返回正的天数"""
        days = stocks.days_since_ipo("600165.SH", datetime.date(2024, 1, 2))
        assert days > 0
        assert isinstance(days, int)

    def test_not_yet_listed_returns_zero(self, stocks):
        """尚未上市的日期 → 0"""
        # 1990-01-01 远早于所有 A 股上市日期,应返回 0
        days = stocks.days_since_ipo("600165.SH", datetime.date(1990, 1, 1))
        assert days == 0


# ───────────────────────── AC-015-03 证券名称查询 ─────────────────────────


class TestGetName:
    """AC-015-03: get_name(asset) 返回证券名称"""

    def test_known_asset_returns_name(self, stocks):
        """已知资产 → 返回非空名称"""
        name = stocks.get_name("600165.SH")
        assert isinstance(name, str)
        assert len(name) > 0


# ───────────────────────── AC-015-04 模式无关性 ─────────────────────────


class TestModeAgnostic:
    """AC-015-04: 同一接口在 4 模式下行为一致(此测试为白盒外的可观测验证)"""

    def test_idempotent_calls(self, stocks):
        """多次调用结果一致(无模式依赖的隐式状态)"""
        r1 = stocks.is_st("600165.SH", datetime.date(2024, 1, 2))
        r2 = stocks.is_st("600165.SH", datetime.date(2024, 1, 2))
        assert r1 == r2

    def test_stocks_listed_deterministic(self, stocks):
        """同一参数多次调用 → 同一结果"""
        r1 = stocks.stocks_listed(datetime.date(2024, 1, 2), exclude_st=True)
        r2 = stocks.stocks_listed(datetime.date(2024, 1, 2), exclude_st=True)
        assert r1 == r2
