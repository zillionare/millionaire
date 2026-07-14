"""FR-360 风控评估事件层测试 (risk.triggered + activation_id).

按 spec-trading.md §FR-360 + interfaces.md §6:
- risk.triggered event 在 RiskStrategy.sell_host_position 触发时发出
- activation_id 在 RiskStrategy 启动时分配 (UUID)
- payload 字段: event_id, activation_id, risk_strategy_id, host_strategy_id, asset, trigger_price, cost_basis, reason, trigger_ts

test:
- RiskStrategy 初始化时分配 activation_id (UUID)
- sell_host_position 发出 risk.triggered event
- payload 字段完整
- PullbackSellStrategy reason="drawback" (FR-100 spec)
- CostStopLossStrategy reason="cost_stop" (FR-110 spec)
- 多 RiskStrategy 实例 activation_id 不同
"""

from __future__ import annotations

import asyncio
import datetime
import re
import uuid
from unittest.mock import MagicMock, AsyncMock

import pytest

from quantide.core.message import msg_hub
from quantide.core.risk_events import (
    RISK_EXCESS_FINALIZED_TOPIC,
    RISK_TRIGGERED_TOPIC,
    BarrierHit,
    emit_risk_excess_finalized,
    emit_risk_triggered,
)
from quantide.core.strategy import RiskStrategy
from quantide.strategies.cost_stop_loss import CostStopLossStrategy
from quantide.strategies.pullback_sell import PullbackSellStrategy


AC_TEST_DATE = datetime.datetime(2024, 6, 3, 9, 30, 0)


def _wait_dispatch():
    """msg_hub 异步 dispatch (0.1s 间隔), 等待直到所有 pending 消息分发完."""
    import time
    time.sleep(0.3)


@pytest.fixture
def captured_events():
    """订阅 risk events topic 收集 events."""
    captured: list[dict] = []

    def _on_triggered(d):
        captured.append(d)

    def _on_finalized(d):
        captured.append(d)

    msg_hub.subscribe(RISK_TRIGGERED_TOPIC, _on_triggered)
    msg_hub.subscribe(RISK_EXCESS_FINALIZED_TOPIC, _on_finalized)
    yield captured
    msg_hub.unsubscribe(RISK_TRIGGERED_TOPIC, _on_triggered)
    msg_hub.unsubscribe(RISK_EXCESS_FINALIZED_TOPIC, _on_finalized)


def test_fr_360_risk_strategy_has_activation_id():
    """AC-FR-360: RiskStrategy 启动时分配 activation_id (UUID)."""
    broker = MagicMock()
    broker.portfolio_id = "host-1"
    risk = PullbackSellStrategy(broker, {"m": 7.0, "k": 0.5})
    assert hasattr(risk, "activation_id")
    assert re.match(r"^[0-9a-f-]{36}$", risk.activation_id), f"activation_id 不是 UUID: {risk.activation_id}"


def test_fr_360_two_risk_strategies_different_activation_id():
    """AC-FR-360: 多 RiskStrategy 实例 activation_id 不同."""
    broker = MagicMock()
    broker.portfolio_id = "host-1"
    r1 = PullbackSellStrategy(broker, {})
    r2 = CostStopLossStrategy(broker, {})
    assert r1.activation_id != r2.activation_id


def test_fr_360_risk_strategy_id_format():
    """AC-FR-360: risk_strategy_id 格式 module.ClassName."""
    broker = MagicMock()
    broker.portfolio_id = "host-1"
    risk = PullbackSellStrategy(broker, {})
    assert risk.risk_strategy_id == "quantide.strategies.pullback_sell.PullbackSellStrategy"


def test_fr_360_emit_risk_triggered_returns_event_id(captured_events):
    """AC-FR-360: emit_risk_triggered 返回 event_id (UUID) 并发出 event."""
    eid = emit_risk_triggered(
        activation_id="act-1",
        risk_strategy_id="r-1",
        host_strategy_id="h-1",
        asset="000001.SZ",
        trigger_price=10.0,
        cost_basis=9.5,
        reason="drawback",
        trigger_ts=AC_TEST_DATE,
    )
    _wait_dispatch()
    assert re.match(r"^[0-9a-f-]{36}$", eid)
    assert len(captured_events) == 1
    ev = captured_events[0]
    assert ev["event_id"] == eid
    assert ev["activation_id"] == "act-1"
    assert ev["risk_strategy_id"] == "r-1"
    assert ev["host_strategy_id"] == "h-1"
    assert ev["asset"] == "000001.SZ"
    assert ev["trigger_price"] == 10.0
    assert ev["cost_basis"] == 9.5
    assert ev["reason"] == "drawback"
    assert ev["trigger_ts"] == AC_TEST_DATE.isoformat()
    assert ev["barrier_hit"] == "expire"


def test_fr_360_emit_risk_excess_finalized(captured_events):
    """AC-FR-360: emit_risk_excess_finalized 发出 event payload."""
    eid = emit_risk_excess_finalized(
        activation_id="act-1",
        triggered_event_id="trig-1",
        excess_return=0.05,
        finalized_at=AC_TEST_DATE,
    )
    _wait_dispatch()
    assert re.match(r"^[0-9a-f-]{36}$", eid)
    assert len(captured_events) == 1
    ev = captured_events[0]
    assert ev["activation_id"] == "act-1"
    assert ev["triggered_event_id"] == "trig-1"
    assert ev["excess_return"] == 0.05


def test_fr_360_pullback_sell_emits_risk_triggered_with_drawback_reason(captured_events):
    """AC-FR-100 + AC-FR-360: PullbackSellStrategy 触发时 reason='drawback'."""
    broker = MagicMock()
    broker.portfolio_id = "host-pm"
    broker.get_prices = MagicMock(return_value={"000001.SZ": 10.0})
    broker.sell = AsyncMock()
    broker.positions = {}

    strategy = PullbackSellStrategy(broker, {"m": 5.0, "k": 5.0})
    pos = MagicMock()
    pos.avail = 100
    pos.asset = "000001.SZ"
    positions = {"000001.SZ": pos}
    strategy._open_prices["000001.SZ"] = 10.0
    strategy._monitoring.add("000001.SZ")
    strategy._monitoring_started_at["000001.SZ"] = AC_TEST_DATE
    strategy._peak_prices["000001.SZ"] = 11.5

    asyncio.run(strategy.on_check(positions, AC_TEST_DATE))
    _wait_dispatch()

    assert len(captured_events) == 1
    ev = captured_events[0]
    assert ev["reason"] == "drawback"
    assert ev["asset"] == "000001.SZ"
    assert ev["risk_strategy_id"] == "quantide.strategies.pullback_sell.PullbackSellStrategy"
    assert ev["host_strategy_id"] == "host-pm"
    assert ev["activation_id"] == strategy.activation_id


def test_fr_360_cost_stop_emits_risk_triggered_with_cost_stop_reason(captured_events):
    """AC-FR-110 + AC-FR-360: CostStopLossStrategy 触发时 reason='cost_stop' (spec 字符串)."""
    broker = MagicMock()
    broker.portfolio_id = "host-cm"
    broker.get_prices = MagicMock(return_value={"000001.SZ": 9.4})
    broker.sell = AsyncMock()
    broker.positions = {}

    strategy = CostStopLossStrategy(broker, {"k": -5.0})
    pos = MagicMock()
    pos.price = 10.0
    pos.avail = 100
    pos.asset = "000001.SZ"
    positions = {"000001.SZ": pos}

    asyncio.run(strategy.on_check(positions, AC_TEST_DATE))
    _wait_dispatch()

    assert len(captured_events) == 1
    ev = captured_events[0]
    assert ev["reason"] == "cost_stop", f"expected 'cost_stop', got {ev['reason']!r}"
    assert ev["asset"] == "000001.SZ"
    assert ev["risk_strategy_id"] == "quantide.strategies.cost_stop_loss.CostStopLossStrategy"
    assert ev["host_strategy_id"] == "host-cm"
    assert ev["activation_id"] == strategy.activation_id


def test_fr_360_barrier_hit_default_is_expire(captured_events):
    """AC-FR-360: 默认 barrier_hit=expire (F-TB-3 语义)."""
    eid = emit_risk_triggered(
        activation_id="act",
        risk_strategy_id="r",
        host_strategy_id="h",
        asset="X",
        trigger_price=10.0,
        cost_basis=None,
        reason="x",
        trigger_ts=AC_TEST_DATE,
    )
    _wait_dispatch()
    assert captured_events[0]["barrier_hit"] == "expire"


def test_fr_360_barrier_hit_up_down(captured_events):
    """AC-FR-360: F-TB-1/2 触发时 barrier_hit=up/down."""
    emit_risk_triggered(
        activation_id="act", risk_strategy_id="r", host_strategy_id="h",
        asset="X", trigger_price=11.0, cost_basis=None,
        reason="up", trigger_ts=AC_TEST_DATE, barrier_hit=BarrierHit.UP,
    )
    emit_risk_triggered(
        activation_id="act", risk_strategy_id="r", host_strategy_id="h",
        asset="X", trigger_price=9.0, cost_basis=None,
        reason="down", trigger_ts=AC_TEST_DATE, barrier_hit=BarrierHit.DOWN,
    )
    _wait_dispatch()
    assert captured_events[0]["barrier_hit"] == "up"
    assert captured_events[1]["barrier_hit"] == "down"


def test_fr_360_pullback_sell_no_event_when_not_triggered(captured_events):
    """AC-FR-360: PullbackSellStrategy 未触发时不应发 risk.triggered."""
    broker = MagicMock()
    broker.portfolio_id = "host"
    broker.get_prices = MagicMock(return_value={"000001.SZ": 9.0})
    strategy = PullbackSellStrategy(broker, {"m": 5.0, "k": 5.0})
    pos = MagicMock()
    pos.avail = 100
    positions = {"000001.SZ": pos}
    asyncio.run(strategy.on_check(positions, AC_TEST_DATE))
    _wait_dispatch()
    assert len(captured_events) == 0


def test_fr_360_cost_stop_no_event_when_price_above_cost(captured_events):
    """AC-FR-360: CostStopLossStrategy 价格高于成本时不应发 event."""
    broker = MagicMock()
    broker.portfolio_id = "host"
    broker.get_prices = MagicMock(return_value={"000001.SZ": 10.5})
    strategy = CostStopLossStrategy(broker, {"k": -5.0})
    pos = MagicMock()
    pos.price = 10.0
    pos.avail = 100
    positions = {"000001.SZ": pos}
    asyncio.run(strategy.on_check(positions, AC_TEST_DATE))
    _wait_dispatch()
    assert len(captured_events) == 0
