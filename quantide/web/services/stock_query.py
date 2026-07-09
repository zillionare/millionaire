"""FR-0330 个股查询与 K 线服务.

定义股票模糊查询 (名字/代码/拼音) 与 K 线数据 schema.

AC-1: 按名字模糊查询.
AC-2: 按代码查询.
AC-3: 按拼音查询.
AC-4: K 线图 + 关键字段 (开/高/低/收/量) hover tooltip.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StockSearchResult:
    """股票搜索结果.

    Attributes:
        symbol: 证券代码.
        name: 证券名称.
        pinyin: 名称拼音 (小写, 无空格).
    """

    symbol: str
    name: str
    pinyin: str = ""


@dataclass
class KlineBar:
    """K 线数据 (AC-FR0330-4).

    Attributes:
        date: 日期.
        open: 开盘价.
        high: 最高价.
        low: 最低价.
        close: 收盘价.
        volume: 成交量.
    """

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class StockSearchValidator:
    """搜索查询校验."""

    @staticmethod
    def validate(query: str) -> bool:
        """校验搜索查询非空.

        Args:
            query: 用户输入.

        Returns:
            True 当查询去空白后非空.
        """
        return bool(query and query.strip())


def match_stock(stock: StockSearchResult, query: str) -> bool:
    """判断单只股票是否匹配查询 (名字/代码/拼音).

    Args:
        stock: 股票搜索结果.
        query: 查询字符串 (已校验非空).

    Returns:
        True 当 query 出现在 symbol / name / pinyin 中 (大小写不敏感).
    """
    if not query:
        return True
    q = query.lower()
    return q in stock.symbol.lower() or q in stock.name or q in stock.pinyin.lower()


def match_stocks(stocks: list[StockSearchResult], query: str) -> list[StockSearchResult]:
    """在股票列表中模糊查询.

    空查询返回全部; 否则按名字/代码/拼音匹配.

    Args:
        stocks: 股票列表.
        query: 查询字符串.

    Returns:
        匹配的股票列表.
    """
    if not query:
        return list(stocks)
    return [s for s in stocks if match_stock(s, query)]


__all__ = [
    "KlineBar",
    "StockSearchResult",
    "StockSearchValidator",
    "match_stock",
    "match_stocks",
]
