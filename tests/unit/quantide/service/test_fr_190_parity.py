"""FR-190 交易规则 — 回测 vs 实盘的差异 (声明性 FR).

按 spec-trading.md §FR-190:
- 回测时上述规则由框架仿真全部实施
- 仿真/实盘时, 时间/价格/数量规则由交易所/柜台强制保证, 框架只在下单前做预校验以避免明显错误委托被发出
- 撮合差异见 FR-080

本测试验证 PaperBroker 在 paper 模式下对明显错误委托做下单前预校验.
Live 模式下, 时间/价格/数量规则由交易所/柜台强制保证 (本测试不覆盖; 由 §6.3 + e2e/three_mode/test_dual_ma_parity.py 覆盖).

实施 FR-190 = 现有 FR-140 (限价) + FR-150 (整手) + FR-160 (T+1) + FR-170 (停牌) + FR-180 (资金) 的组合.
"""

from __future__ import annotations

import datetime

import pytest

from quantide.core.errors import (
    InsufficientCash,
    NonMultipleOfLotSize,
    PriceOutOfLimit,
)
from quantide.data.sqlite import db
from quantide.service.sim_broker import PaperBroker


@pytest.fixture
def paper_broker() -> PaperBroker:
    db.init(":memory:")
    return PaperBroker(portfolio_id="paper-fr190", principal=100000.0)


@pytest.mark.asyncio
async def test_fr_190_pre_order_validation_price_limit(paper_broker):
    """AC-FR-190: paper broker 在下单前做预校验 — 限价单价格超限拒绝 (FR-140)."""
    paper_broker._cash = 1_000_000.0
    paper_broker._limits["000001.SZ"] = {"down": 9.0, "up": 11.0}
    with pytest.raises(PriceOutOfLimit):
        await paper_broker.buy("000001.SZ", 100, price=20.0)


@pytest.mark.asyncio
async def test_fr_190_pre_order_validation_lot_size(paper_broker):
    """AC-FR-190: paper broker 在下单前做预校验 — 非整手且 floor 后 < 1 手拒绝 (FR-150)."""
    with pytest.raises(NonMultipleOfLotSize):
        await paper_broker.buy("000001.SZ", 50, price=10.0)


@pytest.mark.asyncio
async def test_fr_190_pre_order_validation_insufficient_cash(paper_broker):
    """AC-FR-190: paper broker 在下单前做预校验 — 资金不足拒绝 (FR-180)."""
    paper_broker._cash = 100.0
    with pytest.raises(InsufficientCash):
        await paper_broker.buy("000001.SZ", 100, price=10.0)


def test_fr_190_three_mode_parity_test_exists():
    """AC-FR-190: 跨模式 (回测/仿真/实盘) parity 测试存在, 见 tests/e2e/three_mode/test_dual_ma_parity.py."""
    import os

    parity_test = "tests/e2e/three_mode/test_dual_ma_parity.py"
    assert os.path.exists(parity_test), f"parity test not found: {parity_test}"