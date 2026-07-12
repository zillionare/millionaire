"""FR-170 交易规则 — 特殊状态（停牌）单元测试.

按 spec-trading.md §FR-170 + issue #75 + 实施 roadmap PR3:
- 停牌股票 (volume == 0) 不可下单
- 持仓中的停牌股票按停牌前最后收盘价估值 (持仓估值由 _update_positions_market_value 处理, 本 FR 只覆盖下单拒绝)
"""

from __future__ import annotations

import asyncio
import datetime

import pytest

from quantide.core.domain import QuoteSnapshot
from quantide.core.enums import OrderSide
from quantide.core.errors import TradingHaltedError
from quantide.data.sqlite import db
from quantide.service.sim_broker import PaperBroker


AC_TEST_DATE = datetime.datetime(2024, 6, 3, 9, 30, 0)
AC_ASSET = "000001.SZ"


class _DummyMarketData:
    def __init__(self):
        self._quotes: dict[str, QuoteSnapshot] = {}

    def set_quote(self, symbol: str, price: float, volume: float):
        self._quotes[symbol] = QuoteSnapshot(
            symbol=symbol, price=price, open=price, high=price, low=price,
            volume=volume, amount=price * volume, ts=datetime.datetime.now(),
        )

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


def _publish_halted(broker, asset: str = AC_ASSET, price: float = 10.0):
    """推送 volume=0 (停牌) quote."""
    broker._market_data.set_quote(asset, price, volume=0)
    broker._on_quote_update({asset: {"lastPrice": price, "volume": 0, "amount": 0}})


def _publish_active(broker, asset: str = AC_ASSET, price: float = 10.0, volume: float = 1_000_000):
    """推送正常 volume (非停牌) quote."""
    broker._market_data.set_quote(asset, price, volume=volume)
    broker._on_quote_update({asset: {"lastPrice": price, "volume": volume, "amount": price * volume}})


@pytest.mark.asyncio
async def test_fr_170_buy_halted_raises(paper_broker):
    """AC-FR-170: 停牌股票 (volume=0) 不可下单, raise TradingHaltedError."""
    paper_broker.set_clock(AC_TEST_DATE)
    _publish_halted(paper_broker)
    with pytest.raises(TradingHaltedError) as exc_info:
        await paper_broker.buy(AC_ASSET, 100, price=10.0)
    assert exc_info.value.security == AC_ASSET


@pytest.mark.asyncio
async def test_fr_170_buy_active_allowed(paper_broker):
    """AC-FR-170: 正常股票 (volume > 0) 下单不抛 TradingHaltedError (其他校验可能 raise, 但不 TradingHaltedError)."""
    paper_broker.set_clock(AC_TEST_DATE)
    _publish_active(paper_broker)
    try:
        await paper_broker.buy(AC_ASSET, 100, price=10.0)
    except TradingHaltedError as e:
        pytest.fail(f"active stock raised TradingHaltedError: {e!r}")


@pytest.mark.asyncio
async def test_fr_170_no_quote_not_blocked(paper_broker):
    """AC-170-01: 边界 - 无 quote (paper/live 未推送) 不视为停牌, 不阻止下单 (测试 setup 阶段)."""
    paper_broker.set_clock(AC_TEST_DATE)
    try:
        await paper_broker.buy(AC_ASSET, 100, price=10.0)
    except TradingHaltedError as e:
        pytest.fail(f"no-quote raised TradingHaltedError (FR-170 应只在 volume==0 判定): {e!r}")


@pytest.mark.asyncio
async def test_fr_170_halt_detection_helper(paper_broker):
    """AC-170-01: 边界 - _is_halted() 直接验证 (单元层)."""
    _publish_halted(paper_broker)
    assert paper_broker._is_halted(AC_ASSET) is True

    _publish_active(paper_broker)
    assert paper_broker._is_halted(AC_ASSET) is False

    paper_broker._market_data._quotes.pop(AC_ASSET, None)
    assert paper_broker._is_halted(AC_ASSET) is False  # 无 quote 不视为停牌