"""FR-115 BaseStrategy 驱动契约 + FR-125 RiskStrategy 驱动契约 (声明性).

按 spec-strategy.md §FR-115 + §FR-125:
- FR-115: BaseStrategy 回调时序 on_day_open -> on_bar -> on_day_close, 模式差异 (回测/paper/live)
- FR-125: RiskStrategy tick 级独立驱动, on_check 接收 positions 快照, sell_host_position 即时市价成交

本测试验证策略契约:
- Strategy 基类提供 on_day_open / on_bar / on_day_close 回调
- RiskStrategy 提供 on_check / sell_host_position / get_prices / get_ticks
- 回调时序由 BacktestRunner 在 run() 中调用 (FR-115)
- RiskStrategy 不在回测中可驱动 (FR-130 已强制; FR-125 仅在 paper/live)
"""

from __future__ import annotations

import inspect

import pytest

from quantide.core.strategy import BaseStrategy, RiskStrategy


def test_fr_115_base_strategy_callback_signatures():
    """AC-FR-115: BaseStrategy 继承 Strategy 基类 on_day_open / on_bar / on_day_close."""
    for name in ("on_day_open", "on_bar", "on_day_close"):
        assert hasattr(BaseStrategy, name), f"BaseStrategy missing {name}"
        assert inspect.iscoroutinefunction(getattr(BaseStrategy, name)), \
            f"BaseStrategy.{name} must be async"


def test_fr_115_on_bar_signature_accepts_datetime():
    """AC-FR-115: on_bar(tm: datetime) 签名."""
    sig = inspect.signature(BaseStrategy.on_bar)
    params = list(sig.parameters.keys())
    assert "tm" in params, f"on_bar must accept tm parameter, got {params}"


def test_fr_115_strategy_base_methods_are_no_ops():
    """AC-FR-115: Strategy 基类默认实现为空 (no-op), 由子类覆盖."""
    import asyncio

    from quantide.core.strategy import Strategy

    class _Bare(Strategy):
        pass

    inst = _Bare(broker=None, config={})  # type: ignore[arg-type]
    asyncio.run(inst.on_day_open(None))  # type: ignore[arg-type]
    asyncio.run(inst.on_day_close(None))  # type: ignore[arg-type]


def test_fr_125_risk_strategy_callback_signatures():
    """AC-FR-125: RiskStrategy 提供 on_check / sell_host_position."""
    assert hasattr(RiskStrategy, "on_check")
    assert hasattr(RiskStrategy, "sell_host_position")
    assert hasattr(RiskStrategy, "get_prices")
    assert hasattr(RiskStrategy, "get_ticks")


def test_fr_125_on_check_signature_accepts_positions_and_time():
    """AC-FR-125: on_check(positions: dict, tm: datetime) 签名."""
    sig = inspect.signature(RiskStrategy.on_check)
    params = list(sig.parameters.keys())
    assert "positions" in params, f"on_check must accept positions, got {params}"
    assert "tm" in params, f"on_check must accept tm, got {params}"


def test_fr_125_sell_host_position_signature():
    """AC-FR-125: sell_host_position(asset: str, shares: int, reason: str = '')."""
    sig = inspect.signature(RiskStrategy.sell_host_position)
    params = list(sig.parameters.keys())
    assert "asset" in params
    assert "shares" in params
    assert "reason" in params


def test_fr_125_get_prices_raises_in_backtest():
    """AC-FR-125: get_prices 在无 broker.get_prices 时 raise NotImplementedError (仅 paper/live)."""
    inst = RiskStrategy(broker=None, config={})  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError):
        inst.get_prices(["000001.SZ"])


def test_fr_125_get_ticks_raises_in_backtest():
    """AC-FR-125: get_ticks 在无 broker.get_ticks 时 raise NotImplementedError (仅 paper/live)."""
    inst = RiskStrategy(broker=None, config={})  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError):
        inst.get_ticks("000001.SZ", 100)


def test_fr_115_get_bars_signature_supports_frame_type():
    """AC-FR-115: get_bars(asset, count, end_dt, frame_type='1d', include_forming_bar=True) — 数据粒度声明."""
    sig = inspect.signature(BaseStrategy.get_bars)
    params = list(sig.parameters.keys())
    assert "asset" in params
    assert "frame_type" in params
    assert "include_forming_bar" in params


def test_fr_115_get_bars_default_frame_type_is_1d():
    """AC-FR-115: get_bars 默认 frame_type='1d' (日线, 可回测)."""
    sig = inspect.signature(BaseStrategy.get_bars)
    assert sig.parameters["frame_type"].default == "1d"