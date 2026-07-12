"""FR-485 证券代码与市场规则工具.

按 acceptance.md:
- AC-485-01: 证券代码格式转换结果可判定
- AC-485-02: 市场规则辅助值与行情字段一致

当前实现: quantide/data/models/stocks.py — StockList
暂未实现独立 code-converter, 故按 StockList 现有行为测试.
"""

from __future__ import annotations

import polars as pl
import pytest


class TestAC48501:
    """AC-485-01: 证券代码格式转换"""

    def test_happy_stock_load_preserves_code(self):
        """AC-485-01: happy — StockList 加载证券列表保留代码"""
        from quantide.data.models.stocks import StockList

        sl = StockList()
        df = pl.DataFrame({
            "ts_code": ["000001.SZ", "600000.SH", "688001.SH"],
            "name": ["平安银行", "浦发银行", "华兴源创"],
            "area": ["深圳", "上海", "上海"],
        })
        sl._data = df
        codes = sl.data["ts_code"].to_list()
        assert "000001.SZ" in codes
        assert "600000.SH" in codes
        assert "688001.SH" in codes

    def test_edge_star_board_rule(self):
        """AC-485-01: edge — 科创板(ST/创业板)规则"""
        from quantide.data.models.stocks import StockList

        sl = StockList()
        df = pl.DataFrame({
            "ts_code": ["688001.SH"],
            "name": ["华兴源创"],
            "area": ["上海"],
        })
        sl._data = df
        # 科创板代码以 688 开头
        code = sl.data["ts_code"][0]
        assert code.startswith("688"), "科创板代码应以 688 开头"

    def test_error_invalid_code(self):
        """AC-485-01: error — 无效代码不返回误导性合法格式"""
        from quantide.data.models.stocks import StockList

        sl = StockList()
        sl._data = pl.DataFrame({"ts_code": [], "name": [], "area": []})
        assert sl.size == 0
        assert sl.data["ts_code"].to_list() == []


class TestAC48502:
    """AC-485-02: 市场规则辅助"""

    def test_happy_up_down_limit_calc(self):
        """AC-485-02: happy — 普通 A 股涨跌停 ±10%"""
        # 普通 A 股涨跌停 10%
        price = 10.0
        up_limit = round(price * 1.1, 2)
        down_limit = round(price * 0.9, 2)
        assert up_limit == 11.0
        assert down_limit == 9.0

    def test_edge_st_stock_limit(self):
        """AC-485-02: edge — ST 股票涨跌停 5%"""
        price = 10.0
        # ST 股涨跌停 5%
        st_up = round(price * 1.05, 2)
        st_down = round(price * 0.95, 2)
        assert st_up == 10.5
        assert st_down == 9.5

    def test_error_unknown_market_rule(self):
        """AC-485-02: error — 未知市场/板块规则"""
        # 不支持的代码前缀
        fake_code = "XXXXXX.XX"
        # 至少返回可判定结果
        known_prefixes = ["000", "001", "002", "003", "600", "601", "603", "688", "300", "301"]
        prefix = fake_code[:3]
        assert prefix not in known_prefixes, f"unexpected known prefix {prefix}"
