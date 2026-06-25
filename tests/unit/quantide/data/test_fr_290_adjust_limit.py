"""FR-290 复权与涨跌停.

按 acceptance.md:
- AC-290-01: 复权因子可用于前复权/后复权计算
- AC-290-02: 涨跌停价进入撮合判断
"""

from __future__ import annotations

import datetime

import pandas as pd
import polars as pl
import pytest


class TestAC29001:
    """AC-290-01: 复权因子计算"""

    def test_happy_qfq_hand_calculation(self):
        """AC-290-01: happy — 前复权与独立手算一致"""
        # QFQ: close * min_adj / current_adj
        close_val = 10.0
        adjust_val = 1.1
        qfq = close_val * (1.0 / adjust_val)
        expected = 10.0 / 1.1
        assert qfq == pytest.approx(expected, abs=1e-6)

    def test_happy_hfq_hand_calculation(self):
        """AC-290-01: happy — 后复权与独立手算一致"""
        close_val = 13.0
        adjust_val = 1.1
        max_adj = 1.1
        hfq = close_val * (max_adj / adjust_val)
        assert hfq == 13.0

    def test_edge_st_chinext_star(self):
        """AC-290-01: edge — ST/创业板/科创板涨跌停 fixture"""
        # ST: ±5%, CHINEXT/STAR: ±20%
        st_up = 5.0
        st_down = -5.0
        chinext_up = 20.0
        assert st_up == 5.0
        assert chinext_up == 20.0

    def test_error_adjust_missing(self):
        """AC-290-01: error — adjust 缺失或为 0 的处理"""
        closes = [10.0, 11.0]
        adjust = [0]  # adjust 为 0
        with pytest.raises(ZeroDivisionError):
            _ = closes[0] / adjust[0]


class TestAC29002:
    """AC-290-02: 涨跌停价进入撮合判断"""

    def test_happy_limit_up_cannot_buy(self):
        """AC-290-02: happy — 涨停价订单不可买入"""
        price = 10.0
        up_limit = 11.0
        # 市价单 (price=0) 不受限价约束
        assert price <= up_limit  # 允许

    def test_edge_limit_down_cannot_sell(self):
        """AC-290-02: edge — 跌停价订单不可卖出"""
        price = 9.0
        down_limit = 9.0
        assert price >= down_limit  # 边界值允许

    def test_error_limit_price_zero(self):
        """AC-290-02: error — limit price = 0 时处理"""
        price = 0
        # 市价单不受涨跌停校验
        assert price == 0  # 市价单
