"""FR-200 运行时参数 — slippage (滑点) 单元测试.

按 spec-trading.md §FR-200:
- 滑点: 比率, 作用于撮合价格 (买价 +slippage, 卖价 -slippage)
- 默认 0.0 (无滑点), 可在启动时配置

测试:
- 默认 slippage = 0.0, 撮合价格 = last_price
- 买入正滑点: match_price = last_price * (1 + slippage)
- 卖出正滑点: match_price = last_price * (1 - slippage)
- slippage 不影响 order_price 检查 (限价单仍按 order_price 比较)

撮合机制 (与 test_sim_broker_paper.py 一致): buy 异步任务 → publish quote → 撮合.
"""

from __future__ import annotations

import asyncio
import datetime

import pytest

from quantide.core.domain import QuoteSnapshot
from quantide.core.enums import OrderSide
from quantide.data.sqlite import db
from quantide.service.sim_broker import PaperBroker


AC_TEST_DATE = datetime.datetime(2024, 6, 3, 9, 30, 0)
AC_ASSET = "000001.SZ"


class _DummyMarketData:
    def __init__(self):
        self._quotes: dict[str, QuoteSnapshot] = {}

    def set_quote(self, symbol: str, price: float, volume: float = 10000):
        self._quotes[symbol] = QuoteSnapshot(
            symbol=symbol,
            price=price,
            volume=volume,
            ts=AC_TEST_DATE,
        )

    def snapshot(self, symbols):
        return {s: self._quotes[s] for s in symbols if s in self._quotes}


async def _publish(broker: PaperBroker, asset: str, price: float, volume: float = 10000):
    md = broker._market_data
    if isinstance(md, _DummyMarketData):
        md.set_quote(asset, price, volume)
    broker._on_limit_update({asset: {"up": 11.0, "down": 9.0}})
    broker._on_quote_update({asset: {"lastPrice": price, "volume": volume}})
    await asyncio.sleep(0)


@pytest.fixture
def paper_broker():
    """默认 slippage = 0.0."""
    db.init(":memory:")
    md = _DummyMarketData()
    broker = PaperBroker(
        portfolio_id="paper-fr200a", principal=1_000_000, market_data=md  # type: ignore[arg-type]
    )
    return broker


@pytest.mark.asyncio
async def test_fr_200_default_slippage_zero(paper_broker):
    """AC-FR-200: 默认 slippage = 0.0, 撮合价 = last_price."""
    assert paper_broker._slippage == 0.0
    buy_task = asyncio.create_task(paper_broker.buy(AC_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish(paper_broker, AC_ASSET, 10.0)
    buy_result = await buy_task
    assert len(buy_result.trades) >= 1
    assert buy_result.trades[0].price == 10.0, f"expected 10.0, got {buy_result.trades[0].price}"


@pytest.mark.asyncio
async def test_fr_200_buy_slippage_increases_price():
    """AC-FR-200: 买入滑点 +0.001 (0.1%), match_price = 10.0 * 1.001 = 10.01."""
    db.init(":memory:")
    md = _DummyMarketData()
    broker = PaperBroker(
        portfolio_id="paper-fr200b", principal=1_000_000, market_data=md, slippage=0.001  # type: ignore[arg-type]
    )
    buy_task = asyncio.create_task(broker.buy(AC_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish(broker, AC_ASSET, 10.0)
    buy_result = await buy_task
    assert len(buy_result.trades) >= 1
    expected = round(10.0 * 1.001, 4)
    assert buy_result.trades[0].price == expected, f"buy slippage expected {expected}, got {buy_result.trades[0].price}"


@pytest.mark.asyncio
async def test_fr_200_sell_slippage_decreases_price():
    """AC-FR-200: 卖出滑点 +0.001 (0.1%), match_price = 10.0 * (1 - 0.001) = 9.99."""
    db.init(":memory:")
    md = _DummyMarketData()
    broker = PaperBroker(
        portfolio_id="paper-fr200c", principal=1_000_000, market_data=md, slippage=0.001  # type: ignore[arg-type]
    )
    buy_task = asyncio.create_task(broker.buy(AC_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish(broker, AC_ASSET, 10.0)
    await buy_task
    broker.settle_t1()
    sell_task = asyncio.create_task(broker.sell(AC_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish(broker, AC_ASSET, 10.0)
    sell_result = await sell_task
    assert len(sell_result.trades) >= 1
    expected = round(10.0 * (1 - 0.001), 4)
    assert sell_result.trades[0].price == expected, f"sell slippage expected {expected}, got {sell_result.trades[0].price}"


@pytest.mark.asyncio
async def test_fr_200_slippage_does_not_affect_limit_order_price_check():
    """AC-FR-200: slippage 不影响 order_price 与 last_price 的限价单比较 (L889 price check 在 slippage 之前)."""
    from quantide.core.errors import PriceOutOfLimit

    db.init(":memory:")
    md = _DummyMarketData()
    broker = PaperBroker(
        portfolio_id="paper-fr200d", principal=1_000_000, market_data=md, slippage=0.1  # type: ignore[arg-type]
    )
    broker._limits[AC_ASSET] = {"down": 9.0, "up": 11.0}
    with pytest.raises(PriceOutOfLimit):
        await broker.buy(AC_ASSET, 100, price=20.0)


@pytest.mark.asyncio
async def test_fr_200_runtime_params_signature():
    """AC-FR-200: 运行时参数 (本金 / 滑点 / 手续费) 由框架统一管理, 策略代码不可见 (契约)."""
    import inspect

    sig = inspect.signature(PaperBroker.__init__)
    params = list(sig.parameters.keys())
    assert "principal" in params
    assert "slippage" in params
    assert "commission" in params
    assert "stamp_tax" in params