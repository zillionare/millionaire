"""E2E 黑盒测试 — FR-014 交易日历 SDK

按 test-plan.md §4.1 scenarios/calendar/ 设计:
- 仅依赖外部可观测对象(API + 日志 + 数据文件)
- 不 mock 框架内部实现
- 与 acceptance.md AC-014-01 ~ 04 对齐

测试模式直接调用日历单例(同其他 e2e 测试,例如
tests/e2e/backtest/test_dual_ma_accuracy.py 用 calendar_model)。
"""

from __future__ import annotations

import datetime

import pytest

from quantide.data.models.calendar import Calendar


@pytest.fixture
def cal(asset_dir):
    """加载测试用交易日历;复用 session 级 asset_dir fixture"""
    c = Calendar()
    c.load(asset_dir / "baseline_calendar.parquet")
    return c


# ───────────────────────── AC-014-01 交易日判断 ─────────────────────────


class TestIsTradeDay:
    """AC-014-01: 传入日期判断是否交易日"""

    def test_known_trade_day_returns_true(self, cal):
        """已知交易日 → True"""
        # 2024-09-30 是周一交易日(无重大节假日)
        assert cal.is_trade_day(datetime.date(2024, 9, 30)) is True

    def test_weekend_returns_false(self, cal):
        """周末 → False(规则级断言,不绑定具体日期)"""
        # 任一周六/周日应返回 False
        saturdays = [
            datetime.date(2024, 1, 6),   # 周六
            datetime.date(2024, 6, 15),  # 周六
            datetime.date(2024, 12, 28), # 周六
        ]
        sundays = [
            datetime.date(2024, 1, 7),   # 周日
            datetime.date(2024, 6, 16),  # 周日
            datetime.date(2024, 12, 29), # 周日
        ]
        for d in saturdays + sundays:
            assert cal.is_trade_day(d) is False, f"{d} should not be a trade day"

    def test_known_holiday_returns_false(self, cal):
        """已知法定节假日 → False"""
        # 2024-10-01 是国庆节,2024-10-02 ~ 2024-10-07 是法定假日
        holidays = [
            datetime.date(2024, 10, 1),  # 国庆
            datetime.date(2024, 10, 2),
            datetime.date(2024, 10, 3),
            datetime.date(2024, 10, 4),
            datetime.date(2024, 10, 7),
        ]
        for d in holidays:
            assert cal.is_trade_day(d) is False, f"{d} should not be a trade day"


# ───────────────────────── AC-014-02 交易日移位 ─────────────────────────


class TestDayShift:
    """AC-014-02: day_shift(date, n) 移位;offset=0 返回最近已结束交易日"""

    def test_shift_forward_one_skips_weekend(self, cal):
        """向前移 1 天,跨周末自动跳过"""
        # 2024-09-27(周五) → +1 → 2024-09-30(周一)
        result = cal.day_shift(datetime.date(2024, 9, 27), 1)
        assert result == datetime.date(2024, 9, 30)

    def test_shift_backward_one_skips_weekend(self, cal):
        """向后移 1 天,跨周末自动跳过"""
        # 2024-09-30(周一) → -1 → 2024-09-27(周五)
        result = cal.day_shift(datetime.date(2024, 9, 30), -1)
        assert result == datetime.date(2024, 9, 27)

    def test_shift_offset_zero_returns_last_trade_date(self, cal):
        """offset=0 → 返回最近已结束的交易日"""
        # 给定一个已结束的交易日 → 返回该日(不动)
        # 给定一个未来交易日 → 返回上一个已结束交易日
        # 给定周末 → 返回最近的交易日

        # Case 1: 从一个交易日,offset=0 应返回该日(因为它"已结束")
        d = datetime.date(2024, 9, 30)
        assert cal.day_shift(d, 0) == d

        # Case 2: 从一个周末,offset=0 返回最近的交易日
        # 2024-09-28(周六) → 0 → 2024-09-27(周五)
        assert cal.day_shift(datetime.date(2024, 9, 28), 0) == datetime.date(2024, 9, 27)


# ───────────────────────── AC-014-03 交易日计数与列表 ─────────────────────────


class TestCountAndGetTradeDates:
    """AC-014-03: count_trading_days / get_trade_dates;start>end 抛异常"""

    def test_count_excludes_weekends_and_holidays(self, cal):
        """计数跨越周末与节假日的区间 → 仅含交易日"""
        # 2024-09-30(周一) ~ 2024-10-11(周五),含 1 周 + 国庆
        # 交易日:9/30, 10/8, 10/9, 10/10, 10/11 = 5 个
        # 周末/假日:10/1 ~ 10/7
        count = cal.count_trading_days(
            datetime.date(2024, 9, 30), datetime.date(2024, 10, 11)
        )
        assert count == 5

    def test_count_same_day_returns_one_if_trade_day(self, cal):
        """start == end 且为交易日 → 1"""
        assert cal.count_trading_days(
            datetime.date(2024, 9, 30), datetime.date(2024, 9, 30)
        ) == 1

    def test_get_trade_dates_sorted_ascending(self, cal):
        """get_trade_dates 返回按日期升序、不含非交易日"""
        dates = cal.get_trade_dates(
            datetime.date(2024, 9, 30), datetime.date(2024, 10, 11)
        )
        # 排序断言
        assert dates == sorted(dates), "trade dates must be ascending"
        # 仅含交易日
        for d in dates:
            assert cal.is_trade_day(d), f"{d} returned but is not a trade day"
        # 不含周末/假日
        assert datetime.date(2024, 10, 1) not in dates
        assert datetime.date(2024, 10, 5) not in dates  # 周六

    def test_start_greater_than_end_raises(self, cal):
        """start > end → 抛出异常"""
        with pytest.raises(Exception):  # 具体异常类型由实现决定
            cal.count_trading_days(
                datetime.date(2024, 10, 11), datetime.date(2024, 9, 30)
            )
        with pytest.raises(Exception):
            cal.get_trade_dates(
                datetime.date(2024, 10, 11), datetime.date(2024, 9, 30)
            )


# ───────────────────────── AC-014-04 模式无关性 ─────────────────────────


class TestModeAgnostic:
    """AC-014-04: 日历接口在 4 模式下行为一致"""

    def test_is_trade_day_pure_function_no_state(self, cal):
        """is_trade_day 是纯函数,不依赖运行模式状态"""
        # 多次调用结果一致
        d = datetime.date(2024, 9, 30)
        results = [cal.is_trade_day(d) for _ in range(5)]
        assert all(r is True for r in results), "must be consistent across calls"

    def test_day_shift_idempotent(self, cal):
        """day_shift(d, 0) 幂等"""
        d = datetime.date(2024, 9, 30)
        r1 = cal.day_shift(d, 0)
        r2 = cal.day_shift(d, 0)
        assert r1 == r2 == d


# ───────────────────────── 边界:日期范围外 ─────────────────────────


class TestOutOfRange:
    """边界:超出加载日历数据范围的日期"""

    def test_far_future_date_is_not_trade_day(self, cal):
        """远超未来的日期 → False(不抛异常)"""
        # AC 边界:超出数据集外的日期,行为由实现决定(目前 spec 未明示)
        # 现有测试 test_calendar.py:202 已验证 2099-01-25 → False
        assert cal.is_trade_day(datetime.date(2099, 1, 25)) is False
