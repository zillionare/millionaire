"""FR-090 双均线 + FR-100 回落卖出 + FR-110 成本止损 (内置策略).

按 spec-strategy.md §FR-090 + §FR-100 + §FR-110 + issue #66/#67/#68:
- FR-090 双均线: fast 上穿 slow → 买入, slow 上穿 fast → 卖出. 参数 [fast, slow] 默认 [5, 20]. (DualMAStrategy 已有)
- FR-100 回落卖出: 个股当天上涨 m% 后, n 分钟内下跌超过 k%, 立即卖出. 参数 [m, k] 默认 [7, 0.5]. (PullbackSellStrategy 新建)
- FR-110 成本止损: price <= cost_basis * (1 + k/100) 触发卖出. 参数 [k] 默认 [-5.0]. (CostStopLossStrategy 新建)

test:
- FR-090 DualMAStrategy default_config [5, 20] + 类是 BaseStrategy 子类
- FR-100 PullbackSellStrategy default_config [7, 0.5] + 触发逻辑
- FR-110 CostStopLossStrategy default_config [-5.0] + 触发逻辑
"""

from __future__ import annotations

import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantide.core.strategy import BaseStrategy, RiskStrategy
from quantide.strategies.cost_stop_loss import CostStopLossStrategy
from quantide.strategies.example.dual_ma import DualMAStrategy
from quantide.strategies.pullback_sell import PullbackSellStrategy


AC_TEST_DATE = datetime.datetime(2024, 6, 3, 9, 30, 0)


def test_fr_090_dual_ma_is_base_strategy():
    """AC-FR-090: DualMAStrategy 是 BaseStrategy 子类."""
    assert issubclass(DualMAStrategy, BaseStrategy)


def test_fr_090_dual_ma_default_config():
    """AC-FR-090: default_config 默认参数 [fast=5, slow=20]."""
    cfg = DualMAStrategy.default_config()
    assert "fast" in cfg
    assert "slow" in cfg
    assert cfg["fast"] == 5
    assert cfg["slow"] == 20


def test_fr_090_dual_ma_signature():
    """AC-FR-090: DualMAStrategy 提供 on_bar / on_day_open 回调."""
    assert hasattr(DualMAStrategy, "on_bar")
    assert hasattr(DualMAStrategy, "on_day_open")


def test_fr_100_pullback_sell_is_risk_strategy():
    """AC-FR-100: PullbackSellStrategy 是 RiskStrategy 子类."""
    assert issubclass(PullbackSellStrategy, RiskStrategy)


def test_fr_100_pullback_sell_default_config():
    """AC-FR-100: default_config 默认 [m=7, k=0.5]."""
    cfg = PullbackSellStrategy.default_config()
    assert cfg["m"] == 7.0
    assert cfg["k"] == 0.5


def test_fr_100_pullback_sell_triggers_on_pullback():
    """AC-FR-100: 上涨达 m% 后回落超过 k% 触发 sell_host_position."""
    broker = MagicMock()
    broker.get_prices = MagicMock(return_value={"000001.SZ": 10.0})
    broker.sell_host_position = AsyncMock()
    pos = MagicMock()
    pos.avail = 100
    pos.asset = "000001.SZ"
    positions = {"000001.SZ": pos}

    strategy = PullbackSellStrategy(broker, {"m": 5.0, "k": 1.0})
    strategy.sell_host_position = AsyncMock()  # type: ignore[method-assign]
    asyncio.run(strategy.on_day_open(AC_TEST_DATE))

    broker.get_prices.return_value = {"000001.SZ": 10.6}
    asyncio.run(strategy.on_check(positions, AC_TEST_DATE))
    assert "000001.SZ" not in strategy._triggered

    broker.get_prices.return_value = {"000001.SZ": 11.5}
    asyncio.run(strategy.on_check(positions, AC_TEST_DATE))
    assert "000001.SZ" in strategy._monitoring

    broker.get_prices.return_value = {"000001.SZ": 11.4}
    asyncio.run(strategy.on_check(positions, AC_TEST_DATE))
    assert strategy.sell_host_position.call_count == 0

    broker.get_prices.return_value = {"000001.SZ": 10.0}
    asyncio.run(strategy.on_check(positions, AC_TEST_DATE))
    strategy.sell_host_position.assert_called()


def test_fr_110_cost_stop_loss_is_risk_strategy():
    """AC-FR-110: CostStopLossStrategy 是 RiskStrategy 子类."""
    assert issubclass(CostStopLossStrategy, RiskStrategy)


def test_fr_110_cost_stop_loss_default_config():
    """AC-FR-110: default_config 默认 k=-5.0."""
    cfg = CostStopLossStrategy.default_config()
    assert cfg["k"] == -5.0


def test_fr_110_cost_stop_loss_triggers_on_price_drop():
    """AC-FR-110: price <= cost_basis * (1 + k/100) 触发 sell_host_position."""
    broker = MagicMock()
    broker.get_prices = MagicMock(return_value={"000001.SZ": 9.4})
    broker.sell_host_position = AsyncMock()
    pos = MagicMock()
    pos.price = 10.0
    pos.avail = 100
    pos.asset = "000001.SZ"
    positions = {"000001.SZ": pos}

    strategy = CostStopLossStrategy(broker, {"k": -5.0})
    strategy.sell_host_position = AsyncMock()  # type: ignore[method-assign]
    asyncio.run(strategy.on_day_open(AC_TEST_DATE))
    asyncio.run(strategy.on_check(positions, AC_TEST_DATE))
    strategy.sell_host_position.assert_called_with(
        "000001.SZ", 100, reason="cost_stop_loss"
    )


def test_fr_110_cost_stop_loss_no_trigger_when_price_above_cost():
    """AC-FR-110: 价格高于成本价不触发 (price > cost_basis * (1 + k/100))."""
    broker = MagicMock()
    broker.get_prices = MagicMock(return_value={"000001.SZ": 10.5})
    broker.sell_host_position = AsyncMock()
    pos = MagicMock()
    pos.price = 10.0
    pos.avail = 100
    pos.asset = "000001.SZ"
    positions = {"000001.SZ": pos}

    strategy = CostStopLossStrategy(broker, {"k": -5.0})
    strategy.sell_host_position = AsyncMock()  # type: ignore[method-assign]
    asyncio.run(strategy.on_day_open(AC_TEST_DATE))
    asyncio.run(strategy.on_check(positions, AC_TEST_DATE))
    strategy.sell_host_position.assert_not_called()


def test_fr_110_cost_stop_loss_idempotent():
    """AC-FR-110: 同一标的当日多次 tick 触发只卖出一次 (去重 _triggered)."""
    broker = MagicMock()
    broker.get_prices = MagicMock(return_value={"000001.SZ": 9.0})
    broker.sell_host_position = AsyncMock()
    pos = MagicMock()
    pos.price = 10.0
    pos.avail = 100
    pos.asset = "000001.SZ"
    positions = {"000001.SZ": pos}

    strategy = CostStopLossStrategy(broker, {"k": -5.0})
    strategy.sell_host_position = AsyncMock()  # type: ignore[method-assign]
    asyncio.run(strategy.on_day_open(AC_TEST_DATE))
    asyncio.run(strategy.on_check(positions, AC_TEST_DATE))
    asyncio.run(strategy.on_check(positions, AC_TEST_DATE))
    assert strategy.sell_host_position.call_count == 1