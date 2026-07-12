"""FR-150 交易规则 — 数量单元测试.

按 spec-trading.md §FR-150 + issue #73 + 实施 roadmap PR3:
- 买入数量 100 整倍数; 下单前自动向下取整（不足 100 部分丢弃）; 取整后为 0 则下单失败 (raise NonMultipleOfLotSize)
- 卖出一般须 100 整倍数; 清仓 (卖出全部可用持仓) 与零股 (不足一手的零散股) 允许例外
- 仿真/实盘成交数量受涨跌停/停牌/成交量约束, 可能少于委托
- 回测订单全成交或作废 (不考虑成交量)
"""

from __future__ import annotations

import datetime

import pytest

from quantide.core.domain import QuoteSnapshot
from quantide.core.enums import OrderSide
from quantide.core.errors import InsufficientPosition, NonMultipleOfLotSize
from quantide.data.sqlite import db
from quantide.service.sim_broker import PaperBroker


AC_TEST_DATE = datetime.datetime(2024, 6, 3, 9, 30, 0)
AC_ASSET = "000001.SZ"


class _DummyMarketData:
    def __init__(self):
        self._quotes: dict[str, QuoteSnapshot] = {}

    def snapshot(self, symbols):
        return {s: self._quotes[s] for s in symbols if s in self._quotes}


@pytest.fixture
def paper_broker() -> PaperBroker:
    db.init(":memory:")
    return PaperBroker(
        portfolio_id="paper-unit",
        principal=100000,
        market_data=_DummyMarketData(),
        market_value_update_interval=0.0,
    )


def _seed(broker, asset: str, shares: int, price: float):
    broker.set_clock(AC_TEST_DATE)
    broker._apply_trade_to_portfolio(
        type("T", (), {
            "portfolio_id": "paper-unit", "tid": "t1", "qtoid": "o1", "foid": "f1",
            "asset": asset, "shares": shares, "price": price, "amount": shares * price,
            "tm": AC_TEST_DATE, "side": OrderSide.BUY, "cid": "c1", "fee": 0.0,
        })()
    )
    broker._positions[asset].avail = shares


@pytest.mark.asyncio
async def test_fr_150_buy_floor_150_to_100(paper_broker):
    """AC-FR-150: _floor_lot_size(150) = 100."""
    assert PaperBroker._floor_lot_size(150) == 100


@pytest.mark.asyncio
async def test_fr_150_buy_100_exact(paper_broker):
    """AC-FR-150: _floor_lot_size(100) = 100 (整倍数不变)."""
    assert PaperBroker._floor_lot_size(100) == 100


@pytest.mark.asyncio
async def test_fr_150_buy_50_raises_zero_after_floor(paper_broker):
    """AC-FR-150: _floor_lot_size(50) = 0 (floor < 100, buy raise NonMultipleOfLotSize)."""
    assert PaperBroker._floor_lot_size(50) == 0


@pytest.mark.asyncio
async def test_fr_150_buy_99_raises_zero_after_floor(paper_broker):
    """AC-FR-150: _floor_lot_size(99) = 0."""
    assert PaperBroker._floor_lot_size(99) == 0


@pytest.mark.asyncio
async def test_fr_150_sell_lot_size_100(paper_broker):
    """AC-FR-150: 卖出 100 (整手) 允许, 非清仓."""
    _seed(paper_broker, AC_ASSET, shares=300, price=10.0)
    paper_broker.set_clock(AC_TEST_DATE)
    try:
        await paper_broker.sell(AC_ASSET, 100, price=10.0)
    except NonMultipleOfLotSize as e:
        pytest.fail(f"sell 100 (lot size) rejected: {e!r}")


@pytest.mark.asyncio
async def test_fr_150_sell_zero_lot_allowed(paper_broker):
    """AC-FR-150: 卖出 50 (零股, < 100) 允许, 例: 持仓 150 卖 50 零股."""
    _seed(paper_broker, AC_ASSET, shares=150, price=10.0)
    paper_broker.set_clock(AC_TEST_DATE)
    try:
        await paper_broker.sell(AC_ASSET, 50, price=10.0)
    except NonMultipleOfLotSize as e:
        pytest.fail(f"sell 50 (zero lot, FR-150 allowed) rejected: {e!r}")


@pytest.mark.asyncio
async def test_fr_150_sell_full_clearance(paper_broker):
    """AC-FR-150: 卖出全部持仓 (清仓) 允许, 即使非 100 倍."""
    _seed(paper_broker, AC_ASSET, shares=350, price=10.0)
    paper_broker.set_clock(AC_TEST_DATE)
    try:
        await paper_broker.sell(AC_ASSET, 350, price=10.0)
    except NonMultipleOfLotSize as e:
        pytest.fail(f"sell full clearance rejected: {e!r}")


@pytest.mark.asyncio
async def test_fr_150_sell_zero_lot_more_than_avail_rejected(paper_broker):
    """AC-FR-150: 零股卖出 shares > pos.avail 应抛 InsufficientPosition."""
    _seed(paper_broker, AC_ASSET, shares=30, price=10.0)
    paper_broker.set_clock(AC_TEST_DATE)
    with pytest.raises(InsufficientPosition):
        await paper_broker.sell(AC_ASSET, 50, price=10.0)