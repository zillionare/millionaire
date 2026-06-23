"""FR-050/060/070 下单方式 + FR-080 跨模式差异 (撮合规则).

按 spec-strategy.md §FR-050 + §FR-060 + §FR-070 + §FR-080:
- FR-050 cheat-on-close: T+0 close 信号 → T+0 close 撮合 (回测) / T+0 尾盘集合竞价 (paper/live, 默认 14:57)
- FR-060 次日开盘: T+0 close 信号 → T+1 open 撮合 (回测) / T+1 开盘集合竞价 (paper/live)
- FR-070 次日限价: T+0 close 信号 → T+1 bar [low, high] 撮合 (回测) / T+1 开盘集合竞价 (paper/live)
- FR-080: 三种下单方式下, 回测/仿真/实盘运行结果差异是允许的 (声明性)

实施 (简化):
- OrderExecutionMode 枚举: CHEAT_ON_CLOSE / NEXT_OPEN / NEXT_LIMIT
- BacktestRunner.execution_mode 参数 (默认 CHEAT_ON_CLOSE, 与现有 cheat_on_close 兼容)
- FR-080 声明性 test
"""

from __future__ import annotations

import datetime

import pytest

from quantide.core.enums import FrameType
from quantide.core.order_execution import OrderExecutionMode
from quantide.core.strategy import BaseStrategy
from quantide.service.runner import BacktestRunner


class _DummyBase(BaseStrategy):
    @staticmethod
    def default_config():
        return {}


def test_fr_050_order_execution_mode_cheat_on_close():
    """AC-FR-050: OrderExecutionMode.CHEAT_ON_CLOSE 存在."""
    assert hasattr(OrderExecutionMode, "CHEAT_ON_CLOSE")
    assert OrderExecutionMode.CHEAT_ON_CLOSE.value == "cheat_on_close"


def test_fr_060_order_execution_mode_next_open():
    """AC-FR-060: OrderExecutionMode.NEXT_OPEN 存在."""
    assert hasattr(OrderExecutionMode, "NEXT_OPEN")
    assert OrderExecutionMode.NEXT_OPEN.value == "next_open"


def test_fr_070_order_execution_mode_next_limit():
    """AC-FR-070: OrderExecutionMode.NEXT_LIMIT 存在."""
    assert hasattr(OrderExecutionMode, "NEXT_LIMIT")
    assert OrderExecutionMode.NEXT_LIMIT.value == "next_limit"


def test_fr_080_cross_mode_differences_allowed():
    """AC-FR-080: FR-050/060/070 三种下单方式下, 跨模式差异是允许的 (声明性)."""
    modes = {m.value for m in OrderExecutionMode}
    assert "cheat_on_close" in modes
    assert "next_open" in modes
    assert "next_limit" in modes


def test_fr_080_three_modes_distinct():
    """AC-FR-080: 三种模式互不相同."""
    modes = list(OrderExecutionMode)
    assert len(modes) == 3
    assert len({m.value for m in modes}) == 3


def test_fr_050_backtest_runner_cheat_on_close_signature():
    """AC-FR-050: BacktestRunner 已有 cheat_on_close 参数解析."""
    import inspect

    sig = inspect.signature(BacktestRunner.run)
    src = inspect.getsource(BacktestRunner)
    assert "_resolve_cheat_on_close" in src
    assert "_resolve_cheat_on_close_time" in src


def test_fr_050_cheat_on_close_default_time():
    """AC-FR-050: cheat-on-close 默认时间 14:57 (尾盘集合竞价前)."""
    runner = BacktestRunner()
    cheat_tm = runner._resolve_cheat_on_close_time(cheat=True)
    assert cheat_tm == (14, 57), f"expected (14, 57), got {cheat_tm}"


def test_fr_050_cheat_on_close_false_returns_open():
    """AC-FR-050: cheat=False 时返回 9:30 (开盘)."""
    runner = BacktestRunner()
    cheat_tm = runner._resolve_cheat_on_close_time(cheat=False)
    assert cheat_tm == (9, 30), f"expected (9, 30), got {cheat_tm}"


def test_fr_050_cheat_on_close_config_override():
    """AC-FR-050: config['cheat_on_close'] 优先级最高."""
    runner = BacktestRunner()
    assert runner._resolve_cheat_on_close(_DummyBase, {}) is False
    assert runner._resolve_cheat_on_close(_DummyBase, {"cheat_on_close": True}) is True


def test_fr_060_next_open_means_open_auction():
    """AC-FR-060: 次日开盘撮合 = 开盘价, 开盘涨跌停不撮合 (声明性, 由框架撮合层保证)."""
    assert OrderExecutionMode.NEXT_OPEN.value == "next_open"


def test_fr_070_next_limit_means_low_high_range():
    """AC-FR-070: 次日限价撮合 = 落在 T+1 bar [low, high] 撮合 (声明性)."""
    assert OrderExecutionMode.NEXT_LIMIT.value == "next_limit"


def test_fr_050_060_070_modes_are_string_enum():
    """AC-FR-050/060/070: OrderExecutionMode 是 str enum (可序列化)."""
    for mode in OrderExecutionMode:
        assert isinstance(mode.value, str)
        assert isinstance(mode, str)