"""FR-180 交易规则 — 资金（印花税 + 佣金 + 资金校验）单元测试.

按 spec-trading.md §FR-180 + issue #76 + 实施 roadmap PR3:
- 卖出回款当日可用于继续买入 (A 股现金账户规则) — 框架已有, sell() 立即入账
- 印花税（卖方收取, 按比率）、佣金（按比率, 不低于单笔最低佣金）按 FR-200 配置扣除, 扣减发生在成交后立即结算
- 资金校验在虚拟账户层进行: 买入下单时检查虚拟账户可用资金是否足以覆盖 (成交金额 + 佣金)

测试:
- _calculate_fee(buy) = 佣金 only (max(5.0, amount * commission))
- _calculate_fee(sell) = 佣金 + 印花税 (sell side 加 stamp_tax)
- 默认参数 (commission=1e-4, stamp_tax=0.001) 验证
- 大额成交佣金比例 > 5.0, 小额成交固定 5.0
"""

from __future__ import annotations

import datetime

import pytest

from quantide.core.enums import OrderSide
from quantide.core.errors import InsufficientCash
from quantide.data.sqlite import db
from quantide.service.sim_broker import PaperBroker


AC_TEST_DATE = datetime.datetime(2024, 6, 3, 9, 30, 0)
AC_ASSET = "000001.SZ"


@pytest.fixture
def paper_broker() -> PaperBroker:
    db.init(":memory:")
    return PaperBroker(portfolio_id="paper-unit", principal=100000)


@pytest.mark.asyncio
async def test_fr_180_calculate_fee_buy_commission_only(paper_broker):
    """AC-FR-180: _calculate_fee(buy) = max(5.0, amount * commission), 无印花税."""
    amount = 10000.0
    fee = paper_broker._calculate_fee(amount, OrderSide.BUY)
    expected = max(5.0, amount * paper_broker._commission)
    assert fee == expected, f"buy fee 应等于 max(5.0, amount*commission)={expected}, 实际 {fee}"


@pytest.mark.asyncio
async def test_fr_180_calculate_fee_sell_with_stamp_tax(paper_broker):
    """AC-FR-180: _calculate_fee(sell) = 佣金 + 印花税 (amount * stamp_tax)."""
    amount = 10000.0
    fee = paper_broker._calculate_fee(amount, OrderSide.SELL)
    commission = max(5.0, amount * paper_broker._commission)
    stamp = amount * paper_broker._stamp_tax
    expected = commission + stamp
    assert fee == expected


@pytest.mark.asyncio
async def test_fr_180_small_amount_fixed_min_commission(paper_broker):
    """AC-FR-180: 小额成交 (< 5/commission = 50000) 固定 5.0 佣金 (buy side)."""
    fee = paper_broker._calculate_fee(1000.0, OrderSide.BUY)
    assert fee == 5.0, f"小额成交应固定 5.0, 实际 {fee}"


@pytest.mark.asyncio
async def test_fr_180_large_amount_proportional_commission(paper_broker):
    """AC-FR-180: 大额成交 (>= 5/commission = 50000) 按比率佣金 (buy side)."""
    fee = paper_broker._calculate_fee(100000.0, OrderSide.BUY)
    expected = max(5.0, 100000.0 * paper_broker._commission)
    assert fee == expected


@pytest.mark.asyncio
async def test_fr_180_sell_fee_higher_than_buy(paper_broker):
    """AC-FR-180: 同 amount sell fee > buy fee (sell 加印花税)."""
    amount = 10000.0
    buy_fee = paper_broker._calculate_fee(amount, OrderSide.BUY)
    sell_fee = paper_broker._calculate_fee(amount, OrderSide.SELL)
    assert sell_fee > buy_fee, f"sell fee 应 > buy fee (sell 加印花税), 实际 buy={buy_fee} sell={sell_fee}"
    assert sell_fee - buy_fee == pytest.approx(amount * paper_broker._stamp_tax)


@pytest.mark.asyncio
async def test_fr_180_buy_insufficient_cash_raises(paper_broker):
    """AC-FR-180: 买入资金不足 raise InsufficientCash (L902-905)."""
    paper_broker._cash = 100.0
    with pytest.raises(InsufficientCash):
        await paper_broker.buy(AC_ASSET, 100, price=10.0)


@pytest.mark.asyncio
async def test_fr_180_buy_with_exact_cash_allowed(paper_broker):
    """AC-FR-180: 买入资金刚好够 (含佣金) 允许下单."""
    price = 10.0
    shares = 100
    commission_cost = price * shares * paper_broker._commission
    paper_broker._cash = price * shares + commission_cost  # 刚够
    paper_broker._market_data = None
    try:
        await paper_broker.buy(AC_ASSET, shares, price=price)
    except InsufficientCash as e:
        pytest.fail(f"exact cash should be allowed: {e!r}")


@pytest.mark.asyncio
async def test_fr_180_stamp_tax_default(paper_broker):
    """AC-FR-180: 默认 stamp_tax = 0.001 (A 股印花税 0.1%)."""
    assert paper_broker._stamp_tax == 0.001


@pytest.mark.asyncio
async def test_fr_180_commission_default(paper_broker):
    """AC-FR-180: 默认 commission = 1e-4 (A 股佣金 0.01%)."""
    assert paper_broker._commission == 1e-4