"""FR-440 dry-run + FR-450 通知事件 + FR-200 slippage e2e (paper broker).

按 spec §FR-440 + §FR-450 + §FR-200:
- 真实 PaperBroker + minimal_assets fixture
- dry_run=True 时 buy/sell 记录信号不实际下单
- NotificationEvent 5 事件 + 风险事件 + slippage 计算

不依赖真实 qmt-gateway, 不 mock.patch 内部符号.
"""

from __future__ import annotations

import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantide.core.message import msg_hub
from quantide.core.notifications import NotificationEvent
from quantide.core.risk_events import (
    RISK_EXCESS_FINALIZED_TOPIC,
    RISK_TRIGGERED_TOPIC,
    BarrierHit,
)
from quantide.core.enums import OrderSide
from quantide.data.models.calendar import calendar as calendar_model
from quantide.data.models.daily_bars import daily_bars
from quantide.data.sqlite import db
from quantide.service.sim_broker import PaperBroker
from quantide.strategies.cost_stop_loss import CostStopLossStrategy
from quantide.strategies.pullback_sell import PullbackSellStrategy

from tests.e2e.fixtures.minimal_assets import (
    ASSETS_ROOT_LOCAL,
    TEST_ASSET,
    TEST_DATE,
    TEST_UP_LIMIT,
    TEST_DOWN_LIMIT,
)


def _wait_dispatch():
    """msg_hub async dispatch (0.1s 间隔)."""
    import time
    time.sleep(0.3)


@pytest.fixture
def paper_broker():
    db.init(":memory:")
    calendar_model.load(ASSETS_ROOT_LOCAL / "baseline_calendar.parquet")
    daily_bars.connect(
        str(ASSETS_ROOT_LOCAL / "2024_bars_ext_cols.parquet"),
        str(ASSETS_ROOT_LOCAL / "baseline_calendar.parquet"),
    )
    broker = PaperBroker(portfolio_id="e2e-fr440", principal=1_000_000)
    broker._clock = datetime.datetime.combine(TEST_DATE, datetime.time(9, 30))
    broker._limits[TEST_ASSET] = {"up": TEST_UP_LIMIT, "down": TEST_DOWN_LIMIT}
    yield broker


async def _publish_quote(broker, asset, price, volume=10000):
    broker._on_limit_update({asset: {"up": TEST_UP_LIMIT, "down": TEST_DOWN_LIMIT}})
    broker._on_quote_update({asset: {"lastPrice": price, "volume": volume}})
    await asyncio.sleep(0.01)


# ===== FR-440 dry-run =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_440_dry_run_buy_no_state_change(paper_broker):
    """AC-FR-440-01: dry_run=True buy 记录信号不实际下单 (cash/positions 不变)."""
    dry_broker = PaperBroker(
        portfolio_id="e2e-fr440-dry", principal=1_000_000, dry_run=True
    )
    dry_broker._clock = paper_broker._clock
    dry_broker._limits[TEST_ASSET] = {"up": TEST_UP_LIMIT, "down": TEST_DOWN_LIMIT}
    cash_before = dry_broker._cash
    result = await dry_broker.buy(TEST_ASSET, 100, price=10.0)
    assert len(result.trades) == 0
    assert dry_broker._cash == cash_before
    assert TEST_ASSET not in dry_broker._positions
    assert len(dry_broker._dry_run_signals) == 1
    assert dry_broker._dry_run_signals[0]["side"] == OrderSide.BUY


@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_440_dry_run_sell_signal_recorded(paper_broker):
    """AC-FR-440-01: dry_run=True sell 记录信号."""
    dry_broker = PaperBroker(
        portfolio_id="e2e-fr440-dry2", principal=1_000_000, dry_run=True
    )
    dry_broker._clock = paper_broker._clock
    dry_broker._limits[TEST_ASSET] = {"up": TEST_UP_LIMIT, "down": TEST_DOWN_LIMIT}
    result = await dry_broker.sell(TEST_ASSET, 100, price=10.0)
    assert len(result.trades) == 0
    assert len(dry_broker._dry_run_signals) == 1
    assert dry_broker._dry_run_signals[0]["side"] == OrderSide.SELL


# ===== FR-450 通知事件 =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
def test_fr_450_notification_event_5_constants():
    """AC-FR-450: NotificationEvent 5 个事件常量存在 + 值是 snake_case strings."""
    for event in NotificationEvent:
        assert isinstance(event.value, str)
        assert "_" in event.value or event.value in ("orderfailed",)
    assert len(list(NotificationEvent)) == 5


@pytest.mark.e2e
@pytest.mark.e2e_paper
def test_fr_450_notification_event_values_match_spec():
    """AC-FR-450: NotificationEvent 值与 spec §FR-450 表格一致."""
    assert NotificationEvent.ORDER_SUBMITTED.value == "order_submitted"
    assert NotificationEvent.TRADE_FILLED.value == "trade_filled"
    assert NotificationEvent.ORDER_FAILED.value == "order_failed"
    assert NotificationEvent.TRADE_FAILED.value == "trade_failed"
    assert NotificationEvent.GATEWAY_DISCONNECTED.value == "gateway_disconnected"


# ===== FR-200 slippage e2e =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_200_slippage_buy_increases_price(paper_broker):
    """AC-FR-200-01: slippage=0.001 (0.1%) 买入, 撮合价 = 10.0 * 1.001 = 10.01."""
    slip_broker = PaperBroker(
        portfolio_id="e2e-fr200b", principal=1_000_000, market_data=None, slippage=0.001
    )
    slip_broker._clock = paper_broker._clock
    slip_broker._limits[TEST_ASSET] = {"up": TEST_UP_LIMIT, "down": TEST_DOWN_LIMIT}
    buy_task = asyncio.create_task(slip_broker.buy(TEST_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(slip_broker, TEST_ASSET, 10.0)
    result = await buy_task
    assert len(result.trades) >= 1
    assert result.trades[0].price == 10.01, f"expected 10.01, got {result.trades[0].price}"


@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_200_slippage_sell_decreases_price(paper_broker):
    """AC-FR-200-01: slippage=0.001 卖出, 撮合价 = 10.0 * (1 - 0.001) = 9.99."""
    slip_broker = PaperBroker(
        portfolio_id="e2e-fr200s", principal=1_000_000, market_data=None, slippage=0.001
    )
    slip_broker._clock = paper_broker._clock
    slip_broker._limits[TEST_ASSET] = {"up": TEST_UP_LIMIT, "down": TEST_DOWN_LIMIT}
    buy_task = asyncio.create_task(slip_broker.buy(TEST_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(slip_broker, TEST_ASSET, 10.0)
    await buy_task
    slip_broker.settle_t1()
    sell_task = asyncio.create_task(slip_broker.sell(TEST_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(slip_broker, TEST_ASSET, 10.0)
    sell_result = await sell_task
    assert len(sell_result.trades) >= 1
    assert sell_result.trades[0].price == 9.99, f"expected 9.99, got {sell_result.trades[0].price}"


# ===== FR-360 risk.triggered event e2e (via RiskStrategy) =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_360_risk_triggered_event_on_cost_stop(paper_broker):
    """AC-FR-360 + AC-FR-110: CostStopLossStrategy 触发时 emit risk.triggered event."""
    captured: list[dict] = []
    msg_hub.subscribe(RISK_TRIGGERED_TOPIC, lambda d: captured.append(d))

    host_broker = PaperBroker(portfolio_id="host-cm-e2e", principal=100_000, market_data=None)
    host_broker._clock = paper_broker._clock
    host_broker._limits[TEST_ASSET] = {"up": TEST_UP_LIMIT, "down": TEST_DOWN_LIMIT}
    host_broker.get_prices = MagicMock(return_value={TEST_ASSET: 9.4})
    host_broker.sell = AsyncMock(return_value=type("R", (), {"trades": []})())

    pos = MagicMock()
    pos.price = 10.0
    pos.avail = 100
    pos.asset = TEST_ASSET
    positions = {TEST_ASSET: pos}

    strategy = CostStopLossStrategy(host_broker, {"k": -5.0})
    await strategy.on_check(positions, paper_broker._clock)
    _wait_dispatch()

    assert len(captured) == 1
    ev = captured[0]
    assert ev["reason"] == "cost_stop"
    assert ev["asset"] == TEST_ASSET
    assert ev["activation_id"] == strategy.activation_id

    msg_hub.unsubscribe(RISK_TRIGGERED_TOPIC, lambda d: captured.append(d))


@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_360_risk_triggered_event_on_pullback(paper_broker):
    """AC-FR-360 + AC-FR-100: PullbackSellStrategy 触发时 emit risk.triggered event."""
    captured: list[dict] = []
    msg_hub.subscribe(RISK_TRIGGERED_TOPIC, lambda d: captured.append(d))

    host_broker = PaperBroker(portfolio_id="host-pm-e2e", principal=100_000, market_data=None)
    host_broker._clock = paper_broker._clock
    host_broker._limits[TEST_ASSET] = {"up": TEST_UP_LIMIT, "down": TEST_DOWN_LIMIT}
    host_broker.get_prices = MagicMock(return_value={TEST_ASSET: 10.0})
    host_broker.sell = AsyncMock(return_value=type("R", (), {"trades": []})())

    pos = MagicMock()
    pos.avail = 100
    pos.asset = TEST_ASSET
    positions = {TEST_ASSET: pos}

    strategy = PullbackSellStrategy(host_broker, {"m": 5.0, "k": 5.0})
    strategy._open_prices[TEST_ASSET] = 10.0
    strategy._monitoring.add(TEST_ASSET)
    strategy._monitoring_started_at[TEST_ASSET] = paper_broker._clock
    strategy._peak_prices[TEST_ASSET] = 11.5
    await strategy.on_check(positions, paper_broker._clock)
    _wait_dispatch()

    assert len(captured) == 1
    ev = captured[0]
    assert ev["reason"] == "drawback"
    assert ev["asset"] == TEST_ASSET

    msg_hub.unsubscribe(RISK_TRIGGERED_TOPIC, lambda d: captured.append(d))


# ===== FR-360 risk.excess_return.finalized event =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
def test_fr_360_risk_excess_finalized_event_via_msg_hub():
    """AC-FR-360: emit_risk_excess_finalized 发 risk.excess_return.finalized event."""
    captured: list[dict] = []
    msg_hub.subscribe(RISK_EXCESS_FINALIZED_TOPIC, lambda d: captured.append(d))

    from quantide.core.risk_events import emit_risk_excess_finalized
    eid = emit_risk_excess_finalized(
        activation_id="act-1", triggered_event_id="trig-1",
        excess_return=0.05, finalized_at=datetime.datetime.now(),
    )
    _wait_dispatch()
    assert len(captured) == 1
    ev = captured[0]
    assert ev["activation_id"] == "act-1"
    assert ev["triggered_event_id"] == "trig-1"
    assert ev["excess_return"] == 0.05
    msg_hub.unsubscribe(RISK_EXCESS_FINALIZED_TOPIC, lambda d: captured.append(d))


# ===== FR-115 BaseStrategy 驱动契约 e2e (在 paper 模式下) =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
def test_fr_115_base_strategy_in_paper_has_required_callbacks():
    """AC-FR-115: BaseStrategy 在 paper 模式下仍有 on_day_open / on_bar / on_day_close."""
    from quantide.core.strategy import BaseStrategy
    import inspect
    for name in ("on_day_open", "on_bar", "on_day_close", "buy", "sell", "get_bars"):
        assert hasattr(BaseStrategy, name)
        assert inspect.iscoroutinefunction(getattr(BaseStrategy, name)) or name == "get_bars"


@pytest.mark.e2e
@pytest.mark.e2e_paper
def test_fr_115_risk_strategy_in_paper_has_required_callbacks():
    """AC-FR-125: RiskStrategy 在 paper 模式下有 on_check / sell_host_position / get_prices."""
    from quantide.core.strategy import RiskStrategy
    for name in ("on_check", "sell_host_position", "get_prices", "get_ticks"):
        assert hasattr(RiskStrategy, name)
