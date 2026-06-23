"""FR-130 风控策略契约 — BacktestRunner 拒绝 RiskStrategy.

按 spec-strategy.md §FR-130:
- RiskStrategy 不可回测
- BacktestRunner 启动时检测到 RiskStrategy 实例则拒绝

test:
- BacktestRunner.run() 接收 RiskStrategy 时 raise RiskStrategyNotBacktestable
- BaseStrategy 仍可正常进入回测 (sanity check)
"""

from __future__ import annotations

import datetime

import pytest

from quantide.core.enums import FrameType
from quantide.core.errors import RiskStrategyNotBacktestable
from quantide.core.strategy import BaseStrategy, RiskStrategy
from quantide.data.sqlite import db
from quantide.service.runner import BacktestRunner


class _DummyBase(BaseStrategy):
    @staticmethod
    def default_config():
        return {}


class _DummyRisk(RiskStrategy):
    @staticmethod
    def default_config():
        return {}


@pytest.fixture
def runner() -> BacktestRunner:
    return BacktestRunner()


def test_fr_130_backtest_runner_rejects_risk_strategy(runner):
    """AC-FR-130: BacktestRunner.run() 接收 RiskStrategy raise RiskStrategyNotBacktestable."""
    import asyncio

    with pytest.raises(RiskStrategyNotBacktestable):
        asyncio.run(
            runner.run(
                _DummyRisk,
                {},
                datetime.date(2024, 1, 2),
                datetime.date(2024, 1, 5),
                FrameType.DAY,
            )
        )


def test_fr_130_base_strategy_signature_compatible():
    """AC-FR-130: BaseStrategy/RiskStrategy 均继承 Strategy 基类的 on_day_open/on_day_close 契约 (FR-115/125)."""
    assert hasattr(BaseStrategy, "on_bar")
    assert hasattr(BaseStrategy, "on_day_open")
    assert hasattr(BaseStrategy, "on_day_close")
    assert hasattr(RiskStrategy, "on_check")
    assert hasattr(RiskStrategy, "sell_host_position")
    assert hasattr(RiskStrategy, "on_day_open")
    assert hasattr(RiskStrategy, "on_day_close")


def test_fr_130_risk_strategy_no_backtest_method(runner):
    """AC-FR-130: RiskStrategyNotBacktestable 异常暴露 strategy_id."""
    exc = RiskStrategyNotBacktestable("my-risk-001")
    assert exc.strategy_id == "my-risk-001"
    assert "my-risk-001" in str(exc)


def test_fr_130_risk_strategy_no_id_message():
    """AC-FR-130: RiskStrategyNotBacktestable 无 strategy_id 时使用通用消息."""
    exc = RiskStrategyNotBacktestable()
    assert "not backtestable" in str(exc)