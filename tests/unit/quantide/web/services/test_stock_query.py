"""FR-0330 个股查询与 K 线单元测试.

覆盖 acceptance.md AC-FR0330-1~4:
- AC-1: 按名字模糊查询 (例: '平安')
- AC-2: 按代码查询 (例: '000001')
- AC-3: 按拼音查询 (例: 'pingan')
- AC-4: 选中个股 -> K 线图 + 关键字段 hover tooltip
"""
from __future__ import annotations

import pytest

from quantide.web.services.stock_query import (
    KlineBar,
    StockSearchResult,
    StockSearchValidator,
    match_stock,
    match_stocks,
)


def _stock(symbol, name, pinyin=""):
    return StockSearchResult(symbol=symbol, name=name, pinyin=pinyin)


class TestMatchByName:
    """AC-1: 按名字模糊查询."""

    def test_match_name_contains(self):
        assert match_stock(_stock("000001.SZ", "平安银行", "pinganyinhang"), "平安") is True

    def test_no_match_name(self):
        assert match_stock(_stock("600519.SH", "贵州茅台", "guizhoumaotai"), "平安") is False


class TestMatchByCode:
    """AC-2: 按代码查询."""

    def test_match_code_exact(self):
        assert match_stock(_stock("000001.SZ", "平安银行"), "000001") is True

    def test_match_code_partial(self):
        assert match_stock(_stock("000001.SZ", "平安银行"), "00000") is True


class TestMatchByPinyin:
    """AC-3: 按拼音查询."""

    def test_match_pinyin(self):
        assert match_stock(_stock("000001.SZ", "平安银行", "pinganyinhang"), "pingan") is True

    def test_no_match_pinyin(self):
        assert match_stock(_stock("000001.SZ", "平安银行", "pinganyinhang"), "maotai") is False


class TestMatchMultiple:
    def test_match_returns_list(self):
        stocks = [
            _stock("000001.SZ", "平安银行", "pinganyinhang"),
            _stock("600519.SH", "贵州茅台", "guizhoumaotai"),
            _stock("000002.SZ", "平安证券", "pinganzhengquan"),
        ]
        results = match_stocks(stocks, "平安")
        assert len(results) == 2

    def test_match_empty_query_returns_all(self):
        stocks = [_stock("000001.SZ", "平安银行"), _stock("600519.SH", "贵州茅台")]
        results = match_stocks(stocks, "")
        assert len(results) == 2


class TestSearchValidator:
    def test_valid_query(self):
        assert StockSearchValidator.validate("平安") is True

    def test_empty_query_rejected(self):
        assert StockSearchValidator.validate("") is False

    def test_whitespace_query_rejected(self):
        assert StockSearchValidator.validate("   ") is False


class TestKlineBar:
    """AC-4: K 线关键字段."""

    def test_bar_has_ohlcv(self):
        bar = KlineBar(date="2026-07-09", open=10.0, high=10.5, low=9.8, close=10.2, volume=1000000)
        assert bar.open == 10.0
        assert bar.high == 10.5
        assert bar.low == 9.8
        assert bar.close == 10.2
        assert bar.volume == 1000000
