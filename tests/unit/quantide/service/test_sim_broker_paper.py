import asyncio
import datetime
from unittest.mock import AsyncMock

import pytest

from quantide.core.domain import QuoteSnapshot
from quantide.core.enums import OrderSide, OrderStatus
from quantide.core.errors import (
    InsufficientCash,
    InsufficientPosition,
    LimitPrice,
    NonMultipleOfLotSize,
)
from quantide.data.models import Position
from quantide.data.sqlite import db
from quantide.service.sim_broker import PaperBroker


class DummyMarketData:
    def __init__(self):
        self._quotes: dict[str, QuoteSnapshot] = {}

    def set_quote(self, symbol: str, price: float, volume: float | None = None):
        self._quotes[symbol] = QuoteSnapshot(
            symbol=symbol,
            price=price,
            open=price,
            high=price,
            low=price,
            volume=volume,
            amount=(price * volume) if volume is not None else None,
            ts=datetime.datetime.now(),
        )

    def snapshot(self, symbols: list[str]) -> dict[str, QuoteSnapshot]:
        return {
            symbol: self._quotes[symbol]
            for symbol in symbols
            if symbol in self._quotes
        }


async def publish_market(
    broker: PaperBroker,
    asset: str,
    price: float,
    *,
    volume: float | None = None,
    up_limit: float | None = None,
    down_limit: float | None = None,
):
    market_data = broker._market_data
    if isinstance(market_data, DummyMarketData):
        market_data.set_quote(asset, price, volume)
    if up_limit is not None or down_limit is not None:
        broker._on_limit_update(
            {
                asset: {
                    "up": float(up_limit or 0),
                    "down": float(down_limit or 0),
                }
            }
        )
    quote = {asset: {"lastPrice": price, "amount": 1_000_000.0}}
    if volume is not None:
        quote[asset]["volume"] = volume
    broker._on_quote_update(quote)
    await asyncio.sleep(0)


@pytest.fixture
def paper_broker() -> PaperBroker:
    db.init(":memory:")
    broker = PaperBroker(
        portfolio_id="paper-unit",
        principal=100000,
        market_data=DummyMarketData(),
        market_value_update_interval=0.0,
    )
    yield broker
    broker.close()


@pytest.mark.asyncio
async def test_paper_broker_buy_and_sell_with_mock_market_data(paper_broker):
    asset = "000001.SZ"

    buy_task = asyncio.create_task(paper_broker.buy(asset, 100, timeout=1.0))
    await asyncio.sleep(0)
    await publish_market(
        paper_broker,
        asset,
        10.0,
        volume=1,
        up_limit=11.0,
        down_limit=9.0,
    )
    buy_result = await buy_task

    assert buy_result.qt_oid is not None
    assert len(buy_result.trades or []) == 1
    assert paper_broker._positions[asset].shares == 100
    assert paper_broker._positions[asset].avail == 0
    # 成本价含买入手续费：1000 元成交 + 5 元佣金 → 1005 / 100
    assert paper_broker._positions[asset].price == pytest.approx(10.05)

    orders = db.orders_all(portfolio_id="paper-unit")
    trades = db.trades_all(portfolio_id="paper-unit")
    assert orders.height == 1
    assert trades.height == 1

    paper_broker._positions[asset].avail = paper_broker._positions[asset].shares
    sell_task = asyncio.create_task(paper_broker.sell(asset, 100, timeout=1.0))
    await asyncio.sleep(0)
    await publish_market(paper_broker, asset, 10.5, volume=1)
    sell_result = await sell_task

    assert sell_result.qt_oid is not None
    assert len(sell_result.trades or []) == 1
    assert asset not in paper_broker._positions

    all_trades = db.trades_all(portfolio_id="paper-unit")
    assert all_trades.height == 2
    assert all_trades["side"].to_list() == [1, -1]


@pytest.mark.asyncio
async def test_paper_broker_average_cost_includes_fees(paper_broker):
    asset = "000002.SZ"
    await publish_market(paper_broker, asset, 10.0, up_limit=13.0, down_limit=8.0)
    first = asyncio.create_task(paper_broker.buy(asset, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0)
    await publish_market(paper_broker, asset, 10.0, volume=1000)
    await first
    assert paper_broker._positions[asset].price == pytest.approx(10.05)

    second = asyncio.create_task(paper_broker.buy(asset, 100, price=12.0, timeout=1.0))
    await asyncio.sleep(0)
    await publish_market(paper_broker, asset, 12.0, volume=1000)
    await second
    # 100*10.05 + 1200 + 5 = 2210; 2210 / 200 = 11.05
    assert paper_broker._positions[asset].price == pytest.approx(11.05)

    # 重启后从成交流水恢复成本价时，同样包含手续费
    paper_broker._positions.clear()
    paper_broker._init_or_sync_state()
    assert paper_broker._positions[asset].price == pytest.approx(11.05)


@pytest.mark.asyncio
async def test_paper_broker_error_and_cancel_paths(paper_broker):
    asset = "000005.SZ"
    await publish_market(
        paper_broker,
        asset,
        10.0,
        up_limit=11.0,
        down_limit=9.0,
    )

    with pytest.raises(InsufficientCash):
        await paper_broker.buy(asset, 20000, price=10.0)

    with pytest.raises(NonMultipleOfLotSize):
        await paper_broker.buy(asset, 50, price=10.0)

    with pytest.raises(InsufficientPosition):
        await paper_broker.sell(asset, 100, price=10.0)

    task = asyncio.create_task(paper_broker.buy(asset, 100, price=9.0, timeout=1.0))
    await asyncio.sleep(0.05)
    order = paper_broker._active_orders[asset][0]
    await paper_broker.cancel_order(order.qtoid)

    result = await task
    assert len(result.trades or []) == 0
    assert db.get_order(order.qtoid).status == OrderStatus.CANCELED

    paper_broker._positions[asset] = Position(
        portfolio_id=paper_broker.portfolio_id,
        dt=datetime.date.today(),
        asset=asset,
        shares=100,
        avail=100,
        price=10.0,
        mv=1000.0,
        profit=0.0,
    )
    buy_task = asyncio.create_task(paper_broker.buy(asset, 100, price=9.0, timeout=1.0))
    sell_task = asyncio.create_task(paper_broker.sell(asset, 100, price=11.0, timeout=1.0))
    await asyncio.sleep(0.05)

    await paper_broker.cancel_all_orders(side=OrderSide.BUY)

    active_orders = paper_broker._active_orders[asset]
    assert len(active_orders) == 1
    assert active_orders[0].side == OrderSide.SELL

    await paper_broker.cancel_all_orders()
    await buy_task
    await sell_task


@pytest.mark.asyncio
async def test_target_zero_passes_order_details_to_full_sell(paper_broker, monkeypatch):
    asset = "000007.SZ"
    paper_broker._positions[asset] = Position(
        portfolio_id=paper_broker.portfolio_id,
        dt=datetime.date.today(),
        asset=asset,
        shares=1000,
        avail=1000,
        price=10.0,
        profit=0.0,
        mv=10000.0,
    )
    sell = AsyncMock()
    monkeypatch.setattr(paper_broker, "sell_percent", sell)
    order_time = datetime.datetime(2026, 11, 3, 10, 30)

    await paper_broker.trade_target_pct(asset, 0, price=10.0, order_time=order_time, timeout=2.0)

    sell.assert_awaited_once_with(asset, 1.0, price=10.0, order_time=order_time, timeout=2.0)


@pytest.mark.asyncio
async def test_paper_broker_trade_helper_methods(paper_broker):
    asset = "000007.SZ"
    await publish_market(
        paper_broker,
        asset,
        10.0,
        up_limit=11.0,
        down_limit=9.0,
    )

    buy_percent_task = asyncio.create_task(
        paper_broker.buy_percent(asset, 0.5, price=10.0)
    )
    await asyncio.sleep(0.05)
    assert paper_broker._active_orders[asset][0].shares == 5000
    await paper_broker.cancel_all_orders()
    await buy_percent_task

    trade_target_task = asyncio.create_task(
        paper_broker.trade_target_pct(asset, 0.1, price=10.0)
    )
    await asyncio.sleep(0.05)
    target_order = paper_broker._active_orders[asset][0]
    assert target_order.side == OrderSide.BUY
    assert target_order.shares == 1000
    await paper_broker.cancel_all_orders()
    await trade_target_task

    buy_amount_task = asyncio.create_task(paper_broker.buy_amount(asset, 100000))
    await asyncio.sleep(0.05)
    assert paper_broker._active_orders[asset][0].shares == 9000
    await paper_broker.cancel_all_orders()
    await buy_amount_task

    paper_broker._positions[asset] = Position(
        portfolio_id=paper_broker.portfolio_id,
        dt=datetime.date.today(),
        asset=asset,
        shares=1000,
        avail=1000,
        price=10.0,
        mv=10000.0,
        profit=0.0,
    )

    sell_percent_task = asyncio.create_task(paper_broker.sell_percent(asset, 0.5))
    await asyncio.sleep(0.05)
    sell_percent_order = paper_broker._active_orders[asset][0]
    assert sell_percent_order.side == OrderSide.SELL
    assert sell_percent_order.shares == 500
    await paper_broker.cancel_all_orders()
    await sell_percent_task

    sell_percent_all_task = asyncio.create_task(paper_broker.sell_percent(asset, 1.0))
    await asyncio.sleep(0.05)
    assert paper_broker._active_orders[asset][0].shares == 1000
    await paper_broker.cancel_all_orders()
    await sell_percent_all_task

    sell_amount_task = asyncio.create_task(paper_broker.sell_amount(asset, 5000))
    await asyncio.sleep(0.05)
    assert paper_broker._active_orders[asset][0].shares == 500
    await paper_broker.cancel_all_orders()
    await sell_amount_task


@pytest.mark.asyncio
async def test_paper_broker_matching_and_t1_rules(paper_broker):
    asset = "000008.SZ"
    await publish_market(
        paper_broker,
        asset,
        10.0,
        up_limit=11.0,
        down_limit=9.0,
    )

    task = asyncio.create_task(paper_broker.buy(asset, 100, price=10.0, timeout=1.0))
    await asyncio.sleep(0.05)
    await publish_market(paper_broker, asset, 10.0, volume=100)
    result = await task
    assert result.trades[0].fee == 5.0

    paper_broker._cash = 2_000_000
    big_task = asyncio.create_task(
        paper_broker.buy(asset, 100000, price=10.0, timeout=1.0)
    )
    await asyncio.sleep(0.05)
    await publish_market(paper_broker, asset, 10.0, volume=100000)
    big_result = await big_task
    assert abs(big_result.trades[0].fee - 100.0) < 0.001
    assert paper_broker._positions[asset].avail == 0

    with pytest.raises(InsufficientPosition):
        await paper_broker.sell(asset, 100, price=10.0)

    zero_asset = "000009.SZ"
    await publish_market(paper_broker, zero_asset, 0.0, up_limit=11.0, down_limit=9.0)
    zero_result = await paper_broker.buy(zero_asset, 100, price=0.0, timeout=0.2)
    assert len(zero_result.trades or []) == 0

    await publish_market(paper_broker, zero_asset, -10.0)
    negative_result = await paper_broker.buy(zero_asset, 100, price=0.0, timeout=0.2)
    assert len(negative_result.trades or []) == 0


@pytest.mark.asyncio
async def test_paper_broker_limit_price_and_volume_behaviour(paper_broker):
    asset = "SIM.SH"
    await publish_market(
        paper_broker,
        asset,
        10.0,
        up_limit=11.0,
        down_limit=9.0,
    )

    task = asyncio.create_task(paper_broker.buy(asset, 1000, price=9.9, timeout=1.0))
    await asyncio.sleep(0.05)
    assert paper_broker._active_orders[asset][0].filled == 0

    await publish_market(paper_broker, asset, 9.8, volume=5000)
    buy_result = await task
    assert len(buy_result.trades or []) == 1
    assert buy_result.trades[0].price == 9.8
    assert paper_broker._positions[asset].shares == 1000

    paper_broker._positions[asset].avail = 1000
    sell_task = asyncio.create_task(paper_broker.sell(asset, 500, price=10.1, timeout=1.0))
    await asyncio.sleep(0.05)
    await publish_market(paper_broker, asset, 10.2, volume=5000)
    sell_result = await sell_task
    assert len(sell_result.trades or []) == 1
    assert sell_result.trades[0].price == 10.2
    assert paper_broker._positions[asset].shares == 500

    limit_asset = "000004.SZ"
    await publish_market(
        paper_broker,
        limit_asset,
        12.0,
        up_limit=13.0,
        down_limit=9.0,
    )
    limit_task = asyncio.create_task(
        paper_broker.buy(limit_asset, 200, price=10.0, timeout=1.0)
    )
    await asyncio.sleep(0.05)
    await publish_market(paper_broker, limit_asset, 11.0, volume=100)
    assert paper_broker._active_orders[limit_asset][0].filled == 0
    await publish_market(paper_broker, limit_asset, 10.0, volume=100)
    limit_result = await limit_task
    assert len(limit_result.trades or []) == 1
    assert limit_result.trades[0].price == 10.0

    no_volume_asset = "000010.SZ"
    await publish_market(
        paper_broker,
        no_volume_asset,
        10.0,
        up_limit=11.0,
        down_limit=9.0,
    )
    no_volume_task = asyncio.create_task(
        paper_broker.buy(no_volume_asset, 1000, price=10.0, timeout=1.0)
    )
    await asyncio.sleep(0.05)
    await publish_market(paper_broker, no_volume_asset, 10.0)
    no_volume_result = await no_volume_task
    assert len(no_volume_result.trades or []) == 1
    assert no_volume_result.trades[0].shares == 1000

    up_limit_asset = "000011.SZ"
    await publish_market(
        paper_broker,
        up_limit_asset,
        11.0,
        up_limit=11.0,
        down_limit=9.0,
    )
    with pytest.raises(LimitPrice):
        await paper_broker.buy(up_limit_asset, 100, price=11.0, timeout=0.2)


@pytest.mark.asyncio
async def test_paper_broker_sell_all_removes_position(paper_broker):
    asset = "000012.SZ"
    paper_broker._positions[asset] = Position(
        portfolio_id=paper_broker.portfolio_id,
        dt=datetime.date.today(),
        asset=asset,
        shares=100,
        avail=100,
        price=10.0,
        mv=1000.0,
        profit=0.0,
    )

    sell_task = asyncio.create_task(paper_broker.sell(asset, 100, timeout=1.0))
    await asyncio.sleep(0.05)
    await publish_market(paper_broker, asset, 10.0, volume=10000)
    await sell_task

    assert asset not in paper_broker._positions


@pytest.mark.asyncio
async def test_paper_broker_auction_fills_at_last_price(paper_broker, monkeypatch):
    """集合竞价窗口：成交价=竞价价，限价容差=竞价价×(1+eps)。"""
    from quantide.service.execution_clock import ExecutionClock

    monkeypatch.setattr(ExecutionClock, "in_auction", lambda self, now: True)
    asset = "000001.SZ"
    buy_task = asyncio.create_task(paper_broker.buy(asset, 100, timeout=1.0))
    await asyncio.sleep(0)
    await publish_market(paper_broker, asset, 10.0, volume=1, up_limit=11.0, down_limit=9.0)
    result = await buy_task

    assert len(result.trades or []) == 1
    assert result.trades[0].price == 10.0


@pytest.mark.asyncio
async def test_paper_broker_auction_rejects_limit_below_epsilon(paper_broker, monkeypatch):
    """集合竞价：限价低于 竞价价×(1+eps) 的买单不成交。"""
    from quantide.service.execution_clock import ExecutionClock

    monkeypatch.setattr(ExecutionClock, "in_auction", lambda self, now: True)
    asset = "000001.SZ"
    await publish_market(paper_broker, asset, 10.0, volume=1, up_limit=11.0, down_limit=9.0)
    buy_task = asyncio.create_task(
        paper_broker.buy(asset, 100, price=10.005, timeout=0.3)
    )
    result = await buy_task
    assert len(result.trades or []) == 0


def test_normalize_quote_accepts_price_key(paper_broker):
    """发布者使用 price 键时，Paper 撮合仍能识别。"""
    normalized = PaperBroker._normalize_quotes(
        {"600519.SH": {"price": 10.0, "volume": 500}}
    )
    assert normalized["600519.SH"]["lastPrice"] == 10.0
    assert normalized["600519.SH"]["volume"] == 500


@pytest.mark.asyncio
async def test_paper_fills_from_publisher_price_payload(paper_broker):
    """腾讯发布者使用 price 键时，Paper 能正常成交。"""
    asset = "600519.SH"
    paper_broker._on_limit_update(
        {asset: {"up_limit": 11.0, "down_limit": 9.0}}
    )
    task = asyncio.create_task(paper_broker.buy(asset, 100, price=0, timeout=1.0))
    await asyncio.sleep(0)
    paper_broker._on_quote_update(
        {asset: {"price": 10.0, "volume": 5000.0, "amount": 50000.0}}
    )
    result = await task
    assert len(result.trades or []) == 1
    assert result.trades[0].price == pytest.approx(10.0)


def test_port_backed_broker_forwards_get_bars_range():
    """PortBackedBroker 必须把 get_bars_range 转发给 PaperBroker。"""
    from quantide.core.runtime.port_broker import PortBackedBroker

    class _Port:
        def get_bars_range(self, *args, **kwargs):
            return "range-ok"

        def get_history(self, *args, **kwargs):
            return "history-ok"

    wrapper = PortBackedBroker(_Port(), "p1", "sim")
    assert wrapper.get_bars_range([], datetime.date(2024, 1, 1)) == "range-ok"
    assert wrapper.get_history("600519.SH", 2, frame_type="30m") == "history-ok"


def test_paper_broker_fee_config_includes_min_transfer_stamp(paper_broker):
    """费用配置：最低佣金 + 过户费（双边）+ 印花税（卖出）。"""
    paper_broker.apply_fee_config(
        commission=1e-4,
        stamp_tax=5e-4,
        transfer_fee=1e-5,
        min_commission=5.0,
        slippage=0.001,
    )
    # 买入 1000 元：5 元最低佣金 + 0.01 元过户费
    assert paper_broker._calculate_fee(1000.0, OrderSide.BUY) == pytest.approx(5.01)
    # 卖出 1000 元：5 + 0.01 + 0.5 印花税
    assert paper_broker._calculate_fee(1000.0, OrderSide.SELL) == pytest.approx(5.51)
    assert paper_broker._slippage == pytest.approx(0.001)
