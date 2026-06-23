"""FR-050/060/070 下单方式枚举."""

from __future__ import annotations

from enum import Enum


class OrderExecutionMode(str, Enum):
    """下单方式 (FR-050/060/070).

    - CHEAT_ON_CLOSE: T+0 close 信号, T+0 close 撮合 (回测) / T+0 尾盘集合竞价 (paper/live, 默认 14:57)
    - NEXT_OPEN: T+0 close 信号, T+1 open 撮合 (开盘涨跌停不撮合)
    - NEXT_LIMIT: T+0 close 信号, T+1 bar [low, high] 撮合
    """

    CHEAT_ON_CLOSE = "cheat_on_close"
    NEXT_OPEN = "next_open"
    NEXT_LIMIT = "next_limit"