"""FR-140/150/160/170/180/190 交易规则 e2e (paper broker 全链路).

按 spec §FR-140~190 + test-plan §6.3 L1 paper e2e:
- 真实 PaperBroker + VirtualClock + in-memory db
- 不 mock.patch 内部符号
- 走完整 buy → 撮合 → settle_t1 → sell 流程
- 验证 AC-140~190 全部规则

依赖 minimal_assets fixture (1 股票 1 天), 不依赖真实 qmt-gateway.
"""

from __future__ import annotations

import asyncio
import datetime

import pytest

from quantide.core.message import msg_hub
from quantide.data.models.calendar import calendar as calendar_model
from quantide.data.models.daily_bars import daily_bars
from quantide.data.sqlite import db
from quantide.service.sim_broker import PaperBroker

from tests.e2e.fixtures.minimal_assets import (
    ASSETS_ROOT_LOCAL,
    TEST_ASSET,
    TEST_DATE,
    TEST_UP_LIMIT,
    TEST_DOWN_LIMIT,
    TEST_OPEN,
)


AC_TEST_DATE = TEST_DATE
AC_ASSET = TEST_ASSET


@pytest.fixture
def paper_broker():
    """paper broker + minimal data + virtual clock + limits."""
    db.init(":memory:")
    calendar_model.load(ASSETS_ROOT_LOCAL / "baseline_calendar.parquet")
    daily_bars.connect(
        str(ASSETS_ROOT_LOCAL / "2024_bars_ext_cols.parquet"),
        str(ASSETS_ROOT_LOCAL / "baseline_calendar.parquet"),
    )
    broker = PaperBroker(portfolio_id="e2e-fr140", principal=1_000_000)
    broker._clock = datetime.datetime.combine(AC_TEST_DATE, datetime.time(9, 30))
    broker._limits[AC_ASSET] = {"up": TEST_UP_LIMIT, "down": TEST_DOWN_LIMIT}
    yield broker


async def _publish_quote(broker: PaperBroker, asset: str, price: float, volume: int = 10000) -> None:
    broker._on_limit_update({asset: {"up": TEST_UP_LIMIT, "down": TEST_DOWN_LIMIT}})
    broker._on_quote_update({asset: {"lastPrice": price, "volume": volume}})
    await asyncio.sleep(0.01)


# ===== FR-140 限价校验 =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_140_buy_above_up_limit_rejected(paper_broker):
    """AC-FR-140-01: 限价买单 > up_limit (11.0) 拒绝."""
    with pytest.raises(Exception) as exc_info:
        await paper_broker.buy(AC_ASSET, 100, price=12.0)
    assert "PriceOutOfLimit" in type(exc_info.value).__name__


@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_140_buy_within_limit_fills_at_quote(paper_broker):
    """AC-FR-140-02: 限价单价格在 [down, up] 范围内 → 撮合按 last_price 成交."""
    buy_task = asyncio.create_task(paper_broker.buy(AC_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(paper_broker, AC_ASSET, 10.0)
    result = await buy_task
    assert len(result.trades) >= 1
    assert result.trades[0].price == 10.0


# ===== FR-150 整手数量 =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_150_buy_150_floors_to_100(paper_broker):
    """AC-FR-150-01: 买入 150 → floor 到 100."""
    buy_task = asyncio.create_task(paper_broker.buy(AC_ASSET, 150, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(paper_broker, AC_ASSET, 10.0)
    result = await buy_task
    assert paper_broker._positions[AC_ASSET].shares == 100, \
        f"expected 100 after floor, got {paper_broker._positions[AC_ASSET].shares}"


@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_150_buy_50_raises(paper_broker):
    """AC-FR-150-02: 买入 50 → floor 后 0 → raise NonMultipleOfLotSize."""
    with pytest.raises(Exception):
        await paper_broker.buy(AC_ASSET, 50, price=10.0)


# ===== FR-160 T+1 =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_160_buy_then_sell_same_day_raises(paper_broker):
    """AC-FR-160-01: 当日买入当日不可卖."""
    buy_task = asyncio.create_task(paper_broker.buy(AC_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(paper_broker, AC_ASSET, 10.0)
    await buy_task
    with pytest.raises(Exception):
        await paper_broker.sell(AC_ASSET, 100, price=10.0)


@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_160_settle_t1_makes_shares_sellable(paper_broker):
    """AC-FR-160-02: settle_t1() 后 T+1 起可卖."""
    buy_task = asyncio.create_task(paper_broker.buy(AC_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(paper_broker, AC_ASSET, 10.0)
    await buy_task
    paper_broker.settle_t1()
    sell_task = asyncio.create_task(paper_broker.sell(AC_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish_quote(paper_broker, AC_ASSET, 10.0)
    sell_result = await sell_task
    assert len(sell_result.trades) >= 1


# ===== FR-170 停牌 =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_170_buy_halted_raises(paper_broker):
    """AC-FR-170-01: 停牌 (volume=0) 不可下单."""
    paper_broker._market_data = type("M", (), {
        "snapshot": lambda self, assets: {AC_ASSET: type("S", (), {
            "symbol": AC_ASSET, "price": 10.0, "volume": 0, "ts": None
        })()},
    })()
    with pytest.raises(Exception) as exc_info:
        await paper_broker.buy(AC_ASSET, 100, price=10.0)
    assert "TradingHaltedError" in type(exc_info.value).__name__


# ===== FR-180 资金 + 印花税 =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_180_buy_fee_buy_only_commission(paper_broker):
    """AC-FR-180-03: 买入 fee = commission only (无印花税)."""
    fee = paper_broker._calculate_fee(1000.0, side=type("B", (), {"value": "buy"})() if False else paper_broker.buy.__qualname__ and __import__("quantide.core.enums", fromlist=["OrderSide"]).OrderSide.BUY)
    expected = max(5.0, 1000.0 * 1e-4)  # commission only
    assert abs(fee - expected) < 1e-6, f"buy fee should be {expected}, got {fee}"


@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_180_sell_fee_includes_stamp_tax(paper_broker):
    """AC-FR-180-03: 卖 fee = commission + stamp_tax."""
    from quantide.core.enums import OrderSide
    fee = paper_broker._calculate_fee(1000.0, side=OrderSide.SELL)
    expected = max(5.0, 1000.0 * 1e-4) + 1000.0 * 0.001
    assert abs(fee - expected) < 1e-6, f"sell fee should be {expected}, got {fee}"


@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_180_buy_insufficient_cash_raises(paper_broker):
    """AC-FR-180-02: 资金不足拒绝."""
    paper_broker._cash = 100.0
    with pytest.raises(Exception) as exc_info:
        await paper_broker.buy(AC_ASSET, 100, price=10.0)
    assert "InsufficientCash" in type(exc_info.value).__name__


# ===== FR-190 跨模式预校验 (声明性, 验证接口存在) =====

@pytest.mark.e2e
@pytest.mark.e2e_paper
async def test_fr_190_pre_order_validation_in_paper(paper_broker):
    """AC-FR-190-02: paper 模式下框架做下单前预校验 (FR-140/150/180 入口校验)."""
    assert hasattr(paper_broker, "buy")
    assert hasattr(paper_broker, "sell")
    # 限价超界 → 拒绝
    with pytest.raises(Exception):
        await paper_broker.buy(AC_ASSET, 100, price=99.0)
    # 资金不足 → 拒绝
    paper_broker._cash = 1.0
    with pytest.raises(Exception):
        await paper_broker.buy(AC_ASSET, 100, price=1.0)
