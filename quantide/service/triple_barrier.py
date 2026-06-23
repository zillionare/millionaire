"""FR-360 Triple Barrier 公式实施 (F-TB-1 ~ F-TB-5).

按 spec-trading.md §FR-360 + story §1.9:

单位说明:
- up_threshold / down_threshold: 百分点 (5.0 表示 5%)
- excess_return: 小数比率 (0.05 表示 5%)
- P_sell: 卖出价
- Close_n: T_n 日收盘价 (N=0 即当日收盘)
- high / low: 当日最高 / 最低价

公式:
- F-TB-1: up 屏障触发 excess_return = -1 * (up_threshold / 100)
- F-TB-2: down 屏障触发 excess_return = +1 * (down_threshold / 100)
- F-TB-3: expire excess_return = P_sell / Close_n - 1
- F-TB-4: up 屏障触发判断 high >= P_sell * (1 + up_threshold / 100)
- F-TB-5: down 屏障触发判断 low <= P_sell * (1 - down_threshold / 100)

一日内同时触达上下界: 以开盘价更接近者为准 (FR-013 / story §1.9).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class BarrierHit(str, Enum):
    """屏障触发类型."""

    UP = "up"
    DOWN = "down"
    EXPIRE = "expire"


@dataclass(frozen=True)
class BarrierConfig:
    """屏障配置."""

    up_threshold: float  # 百分点, 如 5.0 = 5%
    down_threshold: float  # 百分点, 如 5.0 = 5%
    n: int = 0  # 观察期 N 日, 0 = 当日


@dataclass(frozen=True)
class BarEvaluation:
    """单日屏障评估结果."""

    barrier_hit: BarrierHit
    excess_return: float
    trigger_price: float


def check_up_barrier(high: float, p_sell: float, up_threshold: float) -> bool:
    """F-TB-4: up 屏障触发判断.

    Args:
        high: 当日最高价
        p_sell: 卖出价
        up_threshold: 上阈值 (百分点, 如 5.0)

    Returns:
        True 当 high >= P_sell * (1 + up_threshold / 100)
    """
    return high >= p_sell * (1 + up_threshold / 100)


def check_down_barrier(low: float, p_sell: float, down_threshold: float) -> bool:
    """F-TB-5: down 屏障触发判断.

    Args:
        low: 当日最低价
        p_sell: 卖出价
        down_threshold: 下阈值 (百分点, 如 5.0)

    Returns:
        True 当 low <= P_sell * (1 - down_threshold / 100)
    """
    return low <= p_sell * (1 - down_threshold / 100)


def excess_return_up(up_threshold: float) -> float:
    """F-TB-1: up 屏障触发的超额收益.

    Args:
        up_threshold: 上阈值 (百分点)

    Returns:
        excess_return = -1 * (up_threshold / 100) (小数)
    """
    return -1 * (up_threshold / 100)


def excess_return_down(down_threshold: float) -> float:
    """F-TB-2: down 屏障触发的超额收益.

    Args:
        down_threshold: 下阈值 (百分点)

    Returns:
        excess_return = +1 * (down_threshold / 100) (小数)
    """
    return down_threshold / 100


def excess_return_expire(p_sell: float, close_n: float) -> float:
    """F-TB-3: 观察期到但未触发的超额收益.

    Args:
        p_sell: 卖出价
        close_n: T_n 日收盘价

    Returns:
        excess_return = P_sell / Close_n - 1
        收盘价 < 卖出价 → 正收益 (风控避开下跌)
        收盘价 > 卖出价 → 负收益 (错过上涨)
    """
    if close_n <= 0:
        raise ValueError(f"close_n must be positive, got {close_n}")
    return p_sell / close_n - 1


def evaluate_day(
    high: float,
    low: float,
    open_: float,
    close: float,
    p_sell: float,
    up_threshold: float,
    down_threshold: float,
) -> BarEvaluation:
    """评估单日屏障触发 (含同日触达上下界判断).

    一日内同时触达上下界: 以开盘价更接近者为准 (FR-013 / story §1.9).
    - up 触发价: P_sell * (1 + up_threshold / 100)
    - down 触发价: P_sell * (1 - down_threshold / 100)
    - 开盘价离 up 触发价近 → up; 离 down 触发价近 → down; 等距时优先 down (保守)

    Args:
        high: 当日最高价
        low: 当日最低价
        open_: 当日开盘价
        close: 当日收盘价
        p_sell: 卖出价
        up_threshold: 上阈值 (百分点)
        down_threshold: 下阈值 (百分点)

    Returns:
        BarEvaluation: barrier_hit + excess_return + trigger_price
        当日无触发 (high < up 且 low > down) 时返回 expire, 用当日收盘价
    """
    up_triggered = check_up_barrier(high, p_sell, up_threshold)
    down_triggered = check_down_barrier(low, p_sell, down_threshold)

    if up_triggered and down_triggered:
        up_price = p_sell * (1 + up_threshold / 100)
        down_price = p_sell * (1 - down_threshold / 100)
        up_dist = abs(open_ - up_price)
        down_dist = abs(open_ - down_price)
        if down_dist < up_dist:
            return BarEvaluation(
                barrier_hit=BarrierHit.DOWN,
                excess_return=excess_return_down(down_threshold),
                trigger_price=down_price,
            )
        elif up_dist < down_dist:
            return BarEvaluation(
                barrier_hit=BarrierHit.UP,
                excess_return=excess_return_up(up_threshold),
                trigger_price=up_price,
            )
        else:
            return BarEvaluation(
                barrier_hit=BarrierHit.DOWN,
                excess_return=excess_return_down(down_threshold),
                trigger_price=down_price,
            )

    if up_triggered:
        return BarEvaluation(
            barrier_hit=BarrierHit.UP,
            excess_return=excess_return_up(up_threshold),
            trigger_price=p_sell * (1 + up_threshold / 100),
        )

    if down_triggered:
        return BarEvaluation(
            barrier_hit=BarrierHit.DOWN,
            excess_return=excess_return_down(down_threshold),
            trigger_price=p_sell * (1 - down_threshold / 100),
        )

    return BarEvaluation(
        barrier_hit=BarrierHit.EXPIRE,
        excess_return=excess_return_expire(p_sell, close),
        trigger_price=close,
    )


def evaluate_window(
    bars: list[tuple[float, float, float, float]],
    p_sell: float,
    up_threshold: float,
    down_threshold: float,
) -> BarEvaluation:
    """评估 N 日窗口 (N = len(bars), N=0 时立即 expire 用当日 close).

    Args:
        bars: [(high, low, open, close), ...] 按时间顺序
        p_sell: 卖出价
        up_threshold: 上阈值 (百分点)
        down_threshold: 下阈值 (百分点)

    Returns:
        BarEvaluation: 首个触发日的评估, 或全窗口未触发时最后一日 close 的 expire
    """
    if not bars:
        raise ValueError("bars must not be empty")
    for high, low, open_, close in bars:
        ev = evaluate_day(high, low, open_, close, p_sell, up_threshold, down_threshold)
        if ev.barrier_hit != BarrierHit.EXPIRE:
            return ev
    last_close = bars[-1][3]
    return BarEvaluation(
        barrier_hit=BarrierHit.EXPIRE,
        excess_return=excess_return_expire(p_sell, last_close),
        trigger_price=last_close,
    )