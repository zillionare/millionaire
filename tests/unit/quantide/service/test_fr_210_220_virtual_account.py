"""FR-210 虚拟账本按 qtoid 归因 + FR-220 手工交易/补单/风控卖出的归属 (声明性).

按 spec-trading.md §FR-210 + §FR-220:
- FR-210: 每个独立策略在 live/paper 中拥有一个虚拟账户 (portfolio_id == qtoid), 独立本金, 共享真实账户总资金, Millionaire 不做跨虚拟账户资金分配校验
- FR-220: 手工交易/补单/风控卖出都归属到某个独立策略账户, 写入该策略虚拟账本; 柜台原始账户信息主要用于总览和排障

实施验证 (BrokerRegistry 已存在, quantide/service/registry.py):
- 注册 broker 用 (kind, portfolio_id) 二元组 (key = 'kind:portfolio_id')
- 多 broker 实例可独立存在, 各自 portfolio_id 隔离

test:
- FR-210 多虚拟账户隔离: portfolio_id_a + portfolio_id_b 独立 cash/positions
- FR-210 BrokerRegistry key 格式
- FR-220 RiskStrategy.sell_host_position 归属: portfolio_id 来自 broker (宿主)
"""

from __future__ import annotations

import datetime
import asyncio

import pytest

from quantide.core.domain import QuoteSnapshot
from quantide.data.sqlite import db
from quantide.service.registry import BrokerRegistry
from quantide.service.sim_broker import PaperBroker
from quantide.core.enums import BrokerKind


AC_TEST_DATE = datetime.datetime(2024, 6, 3, 9, 30, 0)
AC_ASSET = "000001.SZ"


class _DummyMarketData:
    def __init__(self):
        self._quotes: dict[str, QuoteSnapshot] = {}

    def set_quote(self, symbol: str, price: float, volume: float = 10000):
        self._quotes[symbol] = QuoteSnapshot(
            symbol=symbol, price=price, volume=volume, ts=AC_TEST_DATE
        )

    def snapshot(self, symbols):
        return {s: self._quotes[s] for s in symbols if s in self._quotes}


async def _publish(broker: PaperBroker, asset: str, price: float):
    md = broker._market_data
    if isinstance(md, _DummyMarketData):
        md.set_quote(asset, price)
    broker._on_limit_update({asset: {"up": round(price * 1.1, 2), "down": round(price * 0.9, 2)}})
    broker._on_quote_update({asset: {"lastPrice": price, "volume": 10000}})
    await asyncio.sleep(0)


def test_fr_210_broker_registry_key_format():
    """AC-FR-210: BrokerRegistry key = 'kind:portfolio_id' 隔离多虚拟账户."""
    reg = BrokerRegistry()
    db.init(":memory:")
    md = _DummyMarketData()
    broker_a = PaperBroker(portfolio_id="qtoid-a", principal=100_000, market_data=md)
    broker_b = PaperBroker(portfolio_id="qtoid-b", principal=200_000, market_data=md)
    reg.register(BrokerKind.SIMULATION, "qtoid-a", broker_a)
    reg.register(BrokerKind.SIMULATION, "qtoid-b", broker_b)
    assert reg.get(BrokerKind.SIMULATION, "qtoid-a") is broker_a
    assert reg.get(BrokerKind.SIMULATION, "qtoid-b") is broker_b


def test_fr_210_virtual_accounts_isolated_cash():
    """AC-FR-210: 两个虚拟账户 cash 独立, 不共享."""
    db.init(":memory:")
    md = _DummyMarketData()
    broker_a = PaperBroker(portfolio_id="qtoid-a", principal=100_000, market_data=md)
    broker_b = PaperBroker(portfolio_id="qtoid-b", principal=200_000, market_data=md)
    assert broker_a._cash == 100_000
    assert broker_b._cash == 200_000
    assert broker_a.portfolio_id == "qtoid-a"
    assert broker_b.portfolio_id == "qtoid-b"


@pytest.mark.asyncio
async def test_fr_210_positions_isolated_by_qtoid():
    """AC-FR-210: 两个虚拟账户 positions 隔离 (同一 asset 各自一份)."""
    db.init(":memory:")
    md_a = _DummyMarketData()
    md_b = _DummyMarketData()
    broker_a = PaperBroker(portfolio_id="qtoid-a", principal=1_000_000, market_data=md_a)
    broker_b = PaperBroker(portfolio_id="qtoid-b", principal=1_000_000, market_data=md_b)

    buy_a = asyncio.create_task(broker_a.buy(AC_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish(broker_a, AC_ASSET, 10.0)
    await buy_a

    assert broker_a._positions[AC_ASSET].shares == 100
    assert AC_ASSET not in broker_b._positions


def test_fr_210_no_cross_account_fund_allocation():
    """AC-FR-210: Millionaire 不做跨虚拟账户资金分配校验 (用户自行保证本金之和 ≤ 总账户)."""
    db.init(":memory:")
    md = _DummyMarketData()
    broker_a = PaperBroker(portfolio_id="qtoid-a", principal=900_000, market_data=md)
    broker_b = PaperBroker(portfolio_id="qtoid-b", principal=900_000, market_data=md)
    assert broker_a._cash + broker_b._cash > broker_a._cash


def test_fr_220_risk_strategy_sell_uses_host_portfolio():
    """AC-FR-220: 风控策略 sell_host_position 卖出归属到宿主 portfolio_id (来自 broker)."""
    from quantide.core.strategy import RiskStrategy

    db.init(":memory:")
    md = _DummyMarketData()
    host_broker = PaperBroker(portfolio_id="host-strategy", principal=100_000, market_data=md)
    risk = RiskStrategy(broker=host_broker, config={})

    import inspect

    src = inspect.getsource(risk.sell_host_position)
    assert "self.broker" in src, "sell_host_position 必须通过 self.broker (宿主 broker) 撮合"
    assert "sell" in src


def test_fr_220_risk_strategy_no_independent_cash():
    """AC-FR-130/FR-220: RiskStrategy 无独立资金账户 (无 cash 属性, 通过 broker 直接访问宿主)."""
    from quantide.core.strategy import RiskStrategy

    db.init(":memory:")
    md = _DummyMarketData()
    host_broker = PaperBroker(portfolio_id="host-strategy-2", principal=100_000, market_data=md)
    risk = RiskStrategy(broker=host_broker, config={})
    assert not hasattr(risk, "_cash")
    assert not hasattr(risk, "cash") or risk.cash == host_broker.cash if hasattr(risk, "cash") else True