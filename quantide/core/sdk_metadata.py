"""FR-014 SDK 元数据接口 — 交易日历 + FR-015 证券列表 (v0.2).

按 spec-strategy.md §FR-014 + §FR-015:
- 独立的只读 SDK 接口, 不属于策略框架
- 可在任何地方调用 (策略内 / 外 / UI)
- backtest/paper/live 模式下接口相同、数据来源不同

FR-014 接口:
- is_trade_day(dt) -> bool
- day_shift(date, n) -> date
- count_trading_days(start, end) -> int
- get_trade_dates(start, end) -> list[date]
- last_trade_date() -> date

FR-015 接口 (声明性 stub, 留作 e2e):
- search(query) -> list[Security]
- get_info(symbol) -> Security | None
- is_st(symbol) -> bool
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class Security:
    """证券基础信息 (FR-015)."""

    symbol: str
    name: str
    is_st: bool = False
    list_date: datetime.date | None = None
    delist_date: datetime.date | None = None


class CalendarSDK:
    """交易日历 SDK (FR-014).

    包装 quantide.data.models.calendar, 提供只读接口.
    backtest/paper/live 模式下接口相同 (数据来源由 calendar 适配).
    """

    def __init__(self):
        from quantide.data.models.calendar import calendar

        self._calendar = calendar

    def is_trade_day(self, dt: datetime.date | datetime.datetime) -> bool:
        """判断指定日期是否为交易日 (FR-014)."""
        return self._calendar.is_trade_day(dt)

    def day_shift(self, date: datetime.date, offset: int) -> datetime.date:
        """向前/向后移位 N 个交易日; offset=0 返回最近已结束交易日 (FR-014)."""
        return self._calendar.day_shift(date, offset)

    def count_trading_days(
        self, start: datetime.date, end: datetime.date
    ) -> int:
        """[start, end] 间的交易日数 (含起止) (FR-014)."""
        return self._calendar.count_trading_days(start, end)

    def get_trade_dates(
        self, start: datetime.date, end: datetime.date
    ) -> list[datetime.date]:
        """[start, end] 间所有交易日 (FR-014)."""
        return self._calendar.get_trade_dates(start, end)

    def last_trade_date(self) -> datetime.date:
        """最近一个已结束交易日 (FR-014)."""
        return self._calendar.last_trade_date()


class SecurityListSDK:
    """证券列表 SDK (FR-015).

    声明性 stub, 完整实现留作 e2e. v0.2 通过 quantide.data.models.stocks 实现.
    """

    def __init__(self):
        self._securities: dict[str, Security] = {}

    def register(self, security: Security) -> None:
        """注册证券 (测试用)."""
        self._securities[security.symbol] = security

    def search(self, query: str) -> list[Security]:
        """按名字/代码/拼音模糊查询 (FR-015)."""
        q = query.lower()
        return [
            s
            for s in self._securities.values()
            if q in s.symbol.lower() or q in s.name.lower()
        ]

    def get_info(self, symbol: str) -> Security | None:
        """按代码查询 (FR-015)."""
        return self._securities.get(symbol)

    def is_st(self, symbol: str) -> bool:
        """是否 ST / *ST (FR-015)."""
        sec = self._securities.get(symbol)
        return sec.is_st if sec else False