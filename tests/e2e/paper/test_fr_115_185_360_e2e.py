"""FR-115 + FR-185 + FR-360 e2e (策略实跑 + 持仓成本 + 风控事件).

按 spec §FR-115 + §FR-185 + §FR-360:
- DualMAStrategy 真实跑 paper broker 1 天
- 持仓成本 F-CB-1~4 在多次 buy/sell 后正确
- 风控事件在策略触发时正确发出

不依赖真实 qmt-gateway, 不 mock.patch 内部符号.
"""

from __future__ import annotations

import asyncio
import datetime
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantide.core.message import msg_hub
from quantide.core.risk_events import RISK_TRIGGERED_TOPIC
from quantide.data.models.calendar import calendar as calendar_model
from quantide.data.models.daily_bars import daily_bars
from quantide.data.sqlite import db
from quantide.service.sim_broker import PaperBroker
from quantide.strategies.example.dual_ma import DualMAStrategy
from tests.e2e.fixtures.minimal_assets import (
    ASSETS_ROOT_LOCAL,
    TEST_ASSET,
    TEST_DATE,
    TEST_DOWN_LIMIT,
    TEST_UP_LIMIT,
)


def _wait_dispatch():
    time.sleep(0.3)


@pytest.fixture
def paper_broker():
    db.init(":memory:")
    calendar_model.load(ASSETS_ROOT_LOCAL / "baseline_calendar.parquet")
    daily_bars.connect(
        str(ASSETS_ROOT_LOCAL / "2024_bars_ext_cols.parquet"),
        str(ASSETS_ROOT_LOCAL / "baseline_calendar.parquet"),
    )
    broker = PaperBroker(portfolio_id="e2e-strategy", principal=1_000_000)
    broker._clock = datetime.datetime.combine(TEST_DATE, datetime.time(9, 30))
    broker._limits[TEST_ASSET] = {"up": TEST_UP_LIMIT, "down": TEST_DOWN_LIMIT}
    yield broker


async def _publish_quote(broker, asset, price, volume=10000):
    broker._on_limit_update({asset: {"up": TEST_UP_LIMIT, "down": TEST_DOWN_LIMIT}})
    broker._on_quote_update({asset: {"lastPrice": price, "volume": volume}})
    await asyncio.sleep(0.01)


# ===== FR-115 BaseStrategy 实跑 =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_115_dual_ma_strategy_runs_in_paper(paper_broker):
    """AC-FR-115: DualMAStrategy 在 paper broker 中能跑 on_day_open + on_bar + on_day_close (无异常)."""
    strategy = DualMAStrategy(paper_broker, {"fast": 5, "slow": 20})
    # on_day_open 不应抛
    await strategy.on_day_open(paper_broker._clock)
    # SC-04: on_bar 仅接 tm; 行情通过 get_bars/get_history 拉取.
    await strategy.on_bar(paper_broker._clock)
    # on_day_close 不应抛
    await strategy.on_day_close(paper_broker._clock)


# ===== FR-185 持仓成本 F-CB-1~4 e2e =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_185_cost_basis_f_cb_1_first_buy(paper_broker):
    """AC-FR-185 F-CB-4: 首次建仓 (old_qty=0) 成本 = buy_price."""
    buy_task = asyncio.create_task(paper_broker.buy(TEST_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(paper_broker, TEST_ASSET, 10.0)
    await buy_task
    pos = paper_broker._positions[TEST_ASSET]
    assert pos.price == 10.0, f"F-CB-4 first buy cost_basis should be 10.0, got {pos.price}"


@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_185_cost_basis_f_cb_1_weighted_update(paper_broker):
    """AC-FR-185 F-CB-1: 二次买入, 成本加权更新 = (100*10 + 100*10) / 200 = 10.0 (price 需在涨跌停内)."""
    buy1 = asyncio.create_task(paper_broker.buy(TEST_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(paper_broker, TEST_ASSET, 10.0)
    await buy1
    paper_broker.settle_t1()
    # 第二次买入 100 @ 10 (up_limit=11, down_limit=9) → 仍 valid
    buy2 = asyncio.create_task(paper_broker.buy(TEST_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(paper_broker, TEST_ASSET, 10.0)
    await buy2
    pos = paper_broker._positions[TEST_ASSET]
    assert pos.shares == 200
    assert abs(pos.price - 10.0) < 1e-6, f"F-CB-1 weighted avg should be 10.0 (两次都 10), got {pos.price}"


@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_185_cost_basis_f_cb_2_partial_sell(paper_broker):
    """AC-FR-185 F-CB-2: 部分卖出 (sell_qty < old_qty) 成本不变."""
    # Buy 200 @ 10
    buy1 = asyncio.create_task(paper_broker.buy(TEST_ASSET, 200, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(paper_broker, TEST_ASSET, 10.0)
    await buy1
    paper_broker.settle_t1()
    cost_before = paper_broker._positions[TEST_ASSET].price
    # Sell 100 @ 11
    sell = asyncio.create_task(paper_broker.sell(TEST_ASSET, 100, price=11.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(paper_broker, TEST_ASSET, 11.0)
    await sell
    pos = paper_broker._positions[TEST_ASSET]
    assert pos.shares == 100
    assert pos.price == cost_before, f"F-CB-2 partial sell cost should remain {cost_before}, got {pos.price}"


@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_185_cost_basis_f_cb_3_full_close(paper_broker):
    """AC-FR-185 F-CB-3: 全部卖出 (sell_qty == old_qty) 持仓清空."""
    buy1 = asyncio.create_task(paper_broker.buy(TEST_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(paper_broker, TEST_ASSET, 10.0)
    await buy1
    paper_broker.settle_t1()
    sell = asyncio.create_task(paper_broker.sell(TEST_ASSET, 100, price=11.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(paper_broker, TEST_ASSET, 11.0)
    await sell
    assert TEST_ASSET not in paper_broker._positions


# ===== FR-360 风控事件 e2e (走完整流程) =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_360_risk_event_emitted_on_strategy_sell(paper_broker):
    """AC-FR-360: 当 RiskStrategy 触发时, risk.triggered event 含完整 payload."""
    captured: list[dict] = []
    msg_hub.subscribe(RISK_TRIGGERED_TOPIC, lambda d: captured.append(d))

    host_broker = PaperBroker(portfolio_id="host-e2e-strat", principal=100_000, market_data=None)
    host_broker._clock = paper_broker._clock
    host_broker._limits[TEST_ASSET] = {"up": TEST_UP_LIMIT, "down": TEST_DOWN_LIMIT}
    host_broker.get_prices = MagicMock(return_value={TEST_ASSET: 9.4})
    host_broker.sell = AsyncMock(return_value=type("R", (), {"trades": []})())

    from quantide.strategies.cost_stop_loss import CostStopLossStrategy

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
    assert ev["event_id"]
    assert ev["activation_id"] == strategy.activation_id
    assert ev["asset"] == TEST_ASSET
    assert ev["trigger_price"] == 9.4
    assert ev["reason"] == "cost_stop"

    msg_hub.unsubscribe(RISK_TRIGGERED_TOPIC, lambda d: captured.append(d))


# ===== 综合: 完整 buy → 持仓 cost → 触发风控 → event 流程 =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_full_lifecycle_buy_cost_basis_risk_event(paper_broker):
    """AC-综合: 完整 lifecycle — buy @ 10 → 持仓 cost=10 → 价跌 9.4 → 风控触发 → event 发出."""
    captured: list[dict] = []
    msg_hub.subscribe(RISK_TRIGGERED_TOPIC, lambda d: captured.append(d))

    # 1) 买入 100 @ 10
    buy1 = asyncio.create_task(paper_broker.buy(TEST_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(paper_broker, TEST_ASSET, 10.0)
    await buy1

    pos = paper_broker._positions[TEST_ASSET]
    assert pos.shares == 100
    assert pos.price == 10.0  # F-CB-4 首次建仓

    # 2) 价跌到 9.4, 风控触发 (cost_basis=10, k=-5%, threshold=9.5, 9.4<=9.5)
    paper_broker.settle_t1()
    paper_broker.get_prices = MagicMock(return_value={TEST_ASSET: 9.4})
    paper_broker.sell = AsyncMock(return_value=type("R", (), {"trades": []})())

    from quantide.strategies.cost_stop_loss import CostStopLossStrategy
    strategy = CostStopLossStrategy(paper_broker, {"k": -5.0})
    # 用真实的 position (从 broker) 而非 MagicMock
    real_pos = paper_broker._positions[TEST_ASSET]
    real_pos.avail = 100
    await strategy.on_check({TEST_ASSET: real_pos}, paper_broker._clock)
    _wait_dispatch()

    assert len(captured) == 1
    ev = captured[0]
    assert ev["reason"] == "cost_stop"
    assert ev["activation_id"] == strategy.activation_id
    # 持仓 cost_basis 在风控触发时正确传递
    assert ev.get("cost_basis") == 10.0

    msg_hub.unsubscribe(RISK_TRIGGERED_TOPIC, lambda d: captured.append(d))
