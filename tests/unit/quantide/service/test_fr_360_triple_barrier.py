"""FR-360 Triple Barrier 公式测试 (F-TB-1 ~ F-TB-5).

按 spec-trading.md §FR-360 + story §1.9:
- F-TB-1: up 屏障触发 excess_return = -1 * (up_threshold / 100)
- F-TB-2: down 屏障触发 excess_return = +1 * (down_threshold / 100)
- F-TB-3: expire excess_return = P_sell / Close_n - 1
- F-TB-4: up 屏障触发判断 high >= P_sell * (1 + up_threshold / 100)
- F-TB-5: down 屏障触发判断 low <= P_sell * (1 - down_threshold / 100)

单位:
- up_threshold / down_threshold: 百分点 (5.0 = 5%)
- excess_return: 小数比率 (0.05 = 5%)

一日内同时触达上下界: 以开盘价更接近者为准 (FR-013).
"""

from __future__ import annotations

import pytest

from quantide.service.triple_barrier import (
    BarrierHit,
    check_down_barrier,
    check_up_barrier,
    evaluate_day,
    evaluate_window,
    excess_return_down,
    excess_return_expire,
    excess_return_up,
)


def test_fr_360_ftb1_up_excess_return():
    """AC-FR-360 F-TB-1: up 屏障 excess_return = -1 * (up_threshold / 100)."""
    assert excess_return_up(5.0) == -0.05
    assert excess_return_up(10.0) == -0.10
    assert excess_return_up(0.0) == 0.0


def test_fr_360_ftb2_down_excess_return():
    """AC-FR-360 F-TB-2: down 屏障 excess_return = +1 * (down_threshold / 100)."""
    assert excess_return_down(5.0) == 0.05
    assert excess_return_down(10.0) == 0.10


def test_fr_360_ftb3_expire_excess_return():
    """AC-FR-360 F-TB-3: expire excess_return = P_sell / Close_n - 1."""
    assert excess_return_expire(10.0, 10.0) == 0.0
    assert excess_return_expire(10.0, 9.0) == pytest.approx(1 / 9)
    assert excess_return_expire(10.0, 11.0) == pytest.approx(-1 / 11)


def test_fr_360_ftb3_expire_semantics():
    """AC-FR-360 F-TB-3 语义: 收盘价 < 卖出价 → 正收益 (风控避开下跌)."""
    assert excess_return_expire(10.0, 9.0) > 0
    assert excess_return_expire(10.0, 11.0) < 0


def test_fr_360_ftb4_up_barrier_check():
    """AC-FR-360 F-TB-4: up 屏障触发 high >= P_sell * (1 + up_threshold/100)."""
    p_sell = 10.0
    up_threshold = 5.0
    up_price = 10.5
    assert check_up_barrier(up_price, p_sell, up_threshold) is True
    assert check_up_barrier(up_price + 0.1, p_sell, up_threshold) is True
    assert check_up_barrier(up_price - 0.1, p_sell, up_threshold) is False
    assert check_up_barrier(10.0, p_sell, up_threshold) is False


def test_fr_360_ftb5_down_barrier_check():
    """AC-FR-360 F-TB-5: down 屏障触发 low <= P_sell * (1 - down_threshold/100)."""
    p_sell = 10.0
    down_threshold = 5.0
    down_price = 9.5
    assert check_down_barrier(down_price, p_sell, down_threshold) is True
    assert check_down_barrier(down_price - 0.1, p_sell, down_threshold) is True
    assert check_down_barrier(down_price + 0.1, p_sell, down_threshold) is False


def test_fr_360_evaluate_day_up_trigger():
    """AC-FR-360 evaluate_day: 触发 up 屏障时返回 BarrierHit.UP + -0.05 excess_return."""
    ev = evaluate_day(
        high=10.6, low=10.0, open_=10.0, close=10.4,
        p_sell=10.0, up_threshold=5.0, down_threshold=5.0,
    )
    assert ev.barrier_hit == BarrierHit.UP
    assert ev.excess_return == -0.05
    assert ev.trigger_price == pytest.approx(10.5)


def test_fr_360_evaluate_day_down_trigger():
    """AC-FR-360 evaluate_day: 触发 down 屏障时返回 BarrierHit.DOWN + +0.05 excess_return."""
    ev = evaluate_day(
        high=10.0, low=9.4, open_=10.0, close=9.6,
        p_sell=10.0, up_threshold=5.0, down_threshold=5.0,
    )
    assert ev.barrier_hit == BarrierHit.DOWN
    assert ev.excess_return == 0.05
    assert ev.trigger_price == pytest.approx(9.5)


def test_fr_360_evaluate_day_expire():
    """AC-FR-360 evaluate_day: 未触发屏障 → EXPIRE + excess_return = P_sell / close - 1."""
    ev = evaluate_day(
        high=10.3, low=9.8, open_=10.0, close=10.2,
        p_sell=10.0, up_threshold=5.0, down_threshold=5.0,
    )
    assert ev.barrier_hit == BarrierHit.EXPIRE
    assert ev.excess_return == pytest.approx(10.0 / 10.2 - 1)


def test_fr_360_evaluate_day_both_triggered_closer_to_up():
    """AC-FR-360 FR-013: 同日触达上下界, 开盘价更接近 up 屏障 → UP."""
    p_sell = 10.0
    up_price = 10.5
    down_price = 9.5
    open_ = 10.4
    ev = evaluate_day(
        high=10.6, low=9.4, open_=open_, close=10.0,
        p_sell=p_sell, up_threshold=5.0, down_threshold=5.0,
    )
    assert abs(open_ - up_price) < abs(open_ - down_price)
    assert ev.barrier_hit == BarrierHit.UP


def test_fr_360_evaluate_day_both_triggered_closer_to_down():
    """AC-FR-360 FR-013: 同日触达上下界, 开盘价更接近 down 屏障 → DOWN."""
    p_sell = 10.0
    up_price = 10.5
    down_price = 9.5
    open_ = 9.6
    ev = evaluate_day(
        high=10.6, low=9.4, open_=open_, close=10.0,
        p_sell=p_sell, up_threshold=5.0, down_threshold=5.0,
    )
    assert abs(open_ - down_price) < abs(open_ - up_price)
    assert ev.barrier_hit == BarrierHit.DOWN


def test_fr_360_evaluate_window_first_day_trigger():
    """AC-FR-360 evaluate_window: 第 1 天触发 → 返回该日评估."""
    bars = [
        (10.6, 10.0, 10.0, 10.4),
        (10.2, 9.8, 10.1, 10.0),
        (10.1, 9.9, 10.0, 10.0),
    ]
    ev = evaluate_window(bars, p_sell=10.0, up_threshold=5.0, down_threshold=5.0)
    assert ev.barrier_hit == BarrierHit.UP


def test_fr_360_evaluate_window_third_day_trigger():
    """AC-FR-360 evaluate_window: 第 3 天触发 → 返回该日评估 (非首日 expire)."""
    bars = [
        (10.3, 9.8, 10.0, 10.2),
        (10.2, 9.9, 10.1, 10.0),
        (10.6, 10.0, 10.0, 10.4),
    ]
    ev = evaluate_window(bars, p_sell=10.0, up_threshold=5.0, down_threshold=5.0)
    assert ev.barrier_hit == BarrierHit.UP


def test_fr_360_evaluate_window_no_trigger_expire():
    """AC-FR-360 evaluate_window: 全部未触发 → 最后一日 close 的 expire."""
    bars = [
        (10.3, 9.8, 10.0, 10.2),
        (10.2, 9.9, 10.1, 10.0),
    ]
    ev = evaluate_window(bars, p_sell=10.0, up_threshold=5.0, down_threshold=5.0)
    assert ev.barrier_hit == BarrierHit.EXPIRE
    assert ev.trigger_price == 10.0


def test_fr_360_evaluate_window_empty_raises():
    """AC-FR-360 evaluate_window: 空 bars raise ValueError."""
    with pytest.raises(ValueError):
        evaluate_window([], p_sell=10.0, up_threshold=5.0, down_threshold=5.0)


def test_fr_360_units_threshold_in_percent():
    """AC-FR-360: up_threshold/down_threshold 用百分点 (5.0 = 5%), 不是小数 (0.05)."""
    assert excess_return_up(5.0) == -0.05
    assert excess_return_down(5.0) == 0.05


def test_fr_360_units_excess_return_decimal():
    """AC-FR-360: excess_return 是小数比率 (0.05 = 5%)."""
    ev = evaluate_day(
        high=10.6, low=10.0, open_=10.0, close=10.4,
        p_sell=10.0, up_threshold=5.0, down_threshold=5.0,
    )
    assert -0.05 == ev.excess_return
    assert isinstance(ev.excess_return, float)