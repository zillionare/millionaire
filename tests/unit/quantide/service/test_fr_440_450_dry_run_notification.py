"""FR-440 dry-run 模式 + FR-450 通知事件定义 (声明性).

按 spec-trading.md §FR-440 + §FR-450:
- FR-440 dry-run: 策略正常运行但不实际下单, 信号被记录, 指标参考并行仿真
- FR-450 通知事件: 委托提交 / 成交 / 委托失败 / 成交失败 / 实盘交易网关断开 (UI 部分已迁移)

实施:
- FR-440: PaperBroker dry_run 参数, buy/sell 入口检查并记录信号 (不实际下单)
- FR-450: NotificationEvent enum 定义 5 个事件 (通知发送留给 UI)

test:
- FR-440 default dry_run=False
- FR-440 dry_run=True buy 记录信号不成交 (cash 不变)
- FR-440 dry_run=True sell 记录信号不成交 (positions 不变)
- FR-440 _dry_run_signals 列表记录所有信号
- FR-450 NotificationEvent 5 个事件常量存在
"""

from __future__ import annotations

import asyncio
import datetime

import pytest

from quantide.core.domain import QuoteSnapshot
from quantide.core.enums import OrderSide
from quantide.core.notifications import NotificationEvent
from quantide.data.sqlite import db
from quantide.service.sim_broker import PaperBroker


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


def test_fr_440_default_dry_run_false():
    """AC-FR-440: 默认 dry_run=False."""
    db.init(":memory:")
    broker = PaperBroker(portfolio_id="paper-fr440a", principal=100_000)
    assert broker._dry_run is False


@pytest.mark.asyncio
async def test_fr_440_buy_signal_recorded_no_trade():
    """AC-FR-440: dry_run=True buy 记录信号不实际下单 (cash/positions 不变)."""
    db.init(":memory:")
    md = _DummyMarketData()
    broker = PaperBroker(
        portfolio_id="paper-fr440b", principal=100_000,
        market_data=md, dry_run=True,  # type: ignore[arg-type]
    )
    cash_before = broker._cash
    result = await broker.buy(AC_ASSET, 100, price=10.0)
    assert len(result.trades) == 0
    assert broker._cash == cash_before
    assert AC_ASSET not in broker._positions
    assert len(broker._dry_run_signals) == 1
    sig = broker._dry_run_signals[0]
    assert sig["side"] == OrderSide.BUY
    assert sig["asset"] == AC_ASSET
    assert sig["shares"] == 100


@pytest.mark.asyncio
async def test_fr_440_sell_signal_recorded_no_trade():
    """AC-FR-440: dry_run=True sell 记录信号不实际下单."""
    db.init(":memory:")
    md = _DummyMarketData()
    broker = PaperBroker(
        portfolio_id="paper-fr440c", principal=100_000,
        market_data=md, dry_run=True,  # type: ignore[arg-type]
    )
    result = await broker.sell(AC_ASSET, 100, price=10.0)
    assert len(result.trades) == 0
    assert len(broker._dry_run_signals) == 1
    assert broker._dry_run_signals[0]["side"] == OrderSide.SELL


@pytest.mark.asyncio
async def test_fr_440_real_buy_modifies_state():
    """AC-FR-440: dry_run=False 时 buy 正常成交 (回归测试)."""
    db.init(":memory:")
    md = _DummyMarketData()
    broker = PaperBroker(
        portfolio_id="paper-fr440d", principal=1_000_000, market_data=md  # type: ignore[arg-type]
    )
    cash_before = broker._cash
    buy_task = asyncio.create_task(broker.buy(AC_ASSET, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await _publish(broker, AC_ASSET, 10.0)
    result = await buy_task
    assert len(result.trades) >= 1
    assert broker._cash < cash_before
    assert broker._positions[AC_ASSET].shares == 100


def test_fr_450_notification_events():
    """AC-FR-450: NotificationEvent 5 个事件常量存在."""
    assert hasattr(NotificationEvent, "ORDER_SUBMITTED")
    assert hasattr(NotificationEvent, "TRADE_FILLED")
    assert hasattr(NotificationEvent, "ORDER_FAILED")
    assert hasattr(NotificationEvent, "TRADE_FAILED")
    assert hasattr(NotificationEvent, "GATEWAY_DISCONNECTED")


def test_fr_450_notification_event_values():
    """AC-FR-450: NotificationEvent 值是字符串常量."""
    assert NotificationEvent.ORDER_SUBMITTED.value == "order_submitted"
    assert NotificationEvent.TRADE_FILLED.value == "trade_filled"
    assert NotificationEvent.ORDER_FAILED.value == "order_failed"
    assert NotificationEvent.TRADE_FAILED.value == "trade_failed"
    assert NotificationEvent.GATEWAY_DISCONNECTED.value == "gateway_disconnected"