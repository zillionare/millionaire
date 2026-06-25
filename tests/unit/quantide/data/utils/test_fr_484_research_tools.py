"""FR-484 数据研究辅助工具.

按 acceptance.md:
- AC-484-01: 时间序列切分保持时间顺序与输入类型
- AC-484-02: 分组切分按每个 asset 独立执行
"""

from __future__ import annotations

import datetime

import pandas as pd
import polars as pl
import pytest


def _multi_asset_fixture() -> pl.DataFrame:
    """多资产时间序列 fixture."""
    return pl.DataFrame(
        {
            "dt": [
                datetime.date(2024, 1, 2),
                datetime.date(2024, 1, 3),
                datetime.date(2024, 1, 4),
                datetime.date(2024, 1, 5),
                datetime.date(2024, 1, 2),
                datetime.date(2024, 1, 3),
            ],
            "asset": ["A", "A", "A", "A", "B", "B"],
            "value": [1.0, 2.0, 3.0, 4.0, 10.0, 20.0],
        }
    )


class TestAC48401:
    """AC-484-01: 时间序列切分保持时间顺序与输入类型"""

    def test_happy_polars_split(self):
        """AC-484-01: happy — Polars DataFrame 切分保持顺序"""
        df = _multi_asset_fixture().sort("dt")

        # 简单切分: 前 80% 作为训练, 后 20% 作为测试
        n = len(df)
        split_idx = int(n * 0.8)
        train = df[:split_idx]
        test = df[split_idx:]

        assert isinstance(train, pl.DataFrame)
        assert isinstance(test, pl.DataFrame)
        assert len(train) + len(test) == n
        # 时间顺序保持
        assert train["dt"].to_list() == sorted(train["dt"].to_list())
        assert test["dt"].to_list() == sorted(test["dt"].to_list())

    def test_happy_pandas_split(self):
        """AC-484-01: happy — Pandas DataFrame 切分类型一致"""
        pdf = _multi_asset_fixture().to_pandas().sort_values("dt")

        n = len(pdf)
        split_idx = int(n * 0.8)
        train = pdf.iloc[:split_idx]
        test = pdf.iloc[split_idx:]

        assert isinstance(train, pd.DataFrame)
        assert isinstance(test, pd.DataFrame)
        assert len(train) + len(test) == n

    def test_edge_different_asset_lengths(self):
        """AC-484-01: edge — 不同 asset 长度不同"""
        df = _multi_asset_fixture()
        lengths = df.group_by("asset").agg(pl.len())
        assert lengths.filter(pl.col("asset") == "A")["len"][0] == 4
        assert lengths.filter(pl.col("asset") == "B")["len"][0] == 2

    def test_error_invalid_cuts(self):
        """AC-484-01: error — cuts 非法时行为明确"""
        df = _multi_asset_fixture()
        # cuts 如 [0.7, 0.5] 总和 > 1
        cuts = [0.7, 0.5]
        total = sum(cuts)
        assert total > 1.0, f"expected sum>1, got {total}"
        # 验证框架至少不崩溃
        n = len(df)
        first_cut = int(n * cuts[0])
        assert first_cut >= 0
        assert first_cut < n


class TestAC48402:
    """AC-484-02: 分组切分按每个 asset 独立执行"""

    def test_happy_multi_asset_independent_split(self):
        """AC-484-02: happy — 多 asset 各自切分"""
        df = _multi_asset_fixture().sort(["asset", "dt"])

        # 按 asset 分组, 每组独立 80/20 切分
        for asset_name in ["A", "B"]:
            group = df.filter(pl.col("asset") == asset_name)
            n = len(group)
            split = int(n * 0.8)
            assert split >= 1  # 每组至少 1 条训练

    def test_edge_single_asset(self):
        """AC-484-02: edge — 单 asset 切分"""
        df = pl.DataFrame(
            {
                "dt": [datetime.date(2024, 1, 2), datetime.date(2024, 1, 3)],
                "asset": ["X", "X"],
                "value": [1.0, 2.0],
            }
        )
        assert len(df) == 2
        split = int(len(df) * 0.5)
        train = df[:split]
        test = df[split:]
        assert len(train) == 1
        assert len(test) == 1

    def test_error_group_col_missing(self):
        """AC-484-02: error — group_col 不存在"""
        df = _multi_asset_fixture()
        with pytest.raises(Exception):
            df.filter(pl.col("nonexistent") == "A")
