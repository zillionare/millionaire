"""FR-160 交易规则 — 时间（T+1）单元测试.

按 spec-trading.md §FR-160 + issue #74 + 实施 roadmap PR3:
- T+1: 当日买入的持仓当日不可卖 (avail 不变); 次日起方可卖 (avail = shares)
- 框架按"可卖持仓"avail + "在途持仓"in-transit 分别记账 (Position.shares - avail)
- settle_t1() 在 day_end 触发, 把 in-transit 转 avail (FR-160 实施)

测试策略:
- 直接构造 Trade + _apply_trade_to_portfolio 验证 shares/avail
- 手动调 settle_t1() 验证 T+1 结算后 avail == shares
- 验证 T+1 前 sell 0 avail raise InsufficientPosition
- 验证 T+1 后 sell avail 允许
"""

from __future__ import annotations

import datetime

import pytest

from quantide.core.enums import OrderSide
from quantide.core.errors import InsufficientPosition
from quantide.data.sqlite import db
from quantide.service.sim_broker import PaperBroker


AC_TEST_DATE = datetime.datetime(2024, 6, 3, 9, 30, 0)
AC_ASSET = "000001.SZ"


@pytest.fixture
def paper_broker() -> PaperBroker:
    db.init(":memory:")
    return PaperBroker(
        portfolio_id="paper-unit",
        principal=100000,
        market_value_update_interval=0.0,
    )


def _buy(paper_broker, shares: int, price: float = 10.0):
    paper_broker._apply_trade_to_portfolio(
        type("T", (), {
            "portfolio_id": "paper-unit", "tid": "t1", "qtoid": "o1", "foid": "f1",
            "asset": AC_ASSET, "shares": shares, "price": price, "amount": shares * price,
            "tm": AC_TEST_DATE, "side": OrderSide.BUY, "cid": "c1", "fee": 0.0,
        })()
    )


@pytest.mark.asyncio
async def test_fr_160_buy_initializes_in_transit(paper_broker):
    """AC-FR-160: 当日 BUY 后 shares=100, avail=0 (in-transit, 当日不可卖)."""
    _buy(paper_broker, shares=100)
    pos = paper_broker._positions[AC_ASSET]
    assert pos.shares == 100
    assert pos.avail == 0


@pytest.mark.asyncio
async def test_fr_160_sell_before_t1_raises(paper_broker):
    """AC-FR-160: T+1 前 sell 任何数量都 raise InsufficientPosition (avail=0)."""
    _buy(paper_broker, shares=100)
    with pytest.raises(InsufficientPosition):
        await paper_broker.sell(AC_ASSET, 100, price=10.0)


@pytest.mark.asyncio
async def test_fr_160_settle_t1_promotes_in_transit_to_avail(paper_broker):
    """AC-FR-160: settle_t1() 后 avail == shares (T+1 结算)."""
    _buy(paper_broker, shares=100)
    paper_broker.settle_t1()
    pos = paper_broker._positions[AC_ASSET]
    assert pos.shares == 100
    assert pos.avail == 100


@pytest.mark.asyncio
async def test_fr_160_sell_after_t1_allowed(paper_broker):
    """AC-FR-160: settle_t1() 后 sell 全部持仓 (清仓) 允许."""
    _buy(paper_broker, shares=100)
    paper_broker.settle_t1()
    try:
        await paper_broker.sell(AC_ASSET, 100, price=10.0)
    except InsufficientPosition as e:
        pytest.fail(f"sell after T+1 rejected: {e!r}")


@pytest.mark.asyncio
async def test_fr_160_multiple_buys_in_transit(paper_broker):
    """AC-FR-160: 多笔 buy 都 in-transit, settle_t1 后一次释放."""
    _buy(paper_broker, shares=100)
    _buy(paper_broker, shares=200)
    pos = paper_broker._positions[AC_ASSET]
    assert pos.shares == 300
    assert pos.avail == 0

    paper_broker.settle_t1()
    assert pos.shares == 300
    assert pos.avail == 300


@pytest.mark.asyncio
async def test_fr_160_settle_t1_only_affects_in_transit(paper_broker):
    """AC-FR-160: settle_t1 后再次 buy, 新 buy 仍 in-transit (不追溯生效)."""
    _buy(paper_broker, shares=100)
    paper_broker.settle_t1()
    _buy(paper_broker, shares=50)
    pos = paper_broker._positions[AC_ASSET]
    assert pos.shares == 150
    assert pos.avail == 100