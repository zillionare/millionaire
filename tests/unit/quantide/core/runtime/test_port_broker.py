"""v0.2-003 FR-0204 PortBackedBroker compatibility tests."""

import datetime as dt

from quantide.core.enums import BrokerKind, OrderSide, OrderStatus
from quantide.core.ports import ExecutionResult, OrderView, PositionView
from quantide.core.runtime.port_broker import PortBackedBroker


class RecordingPort:
    def __init__(self):
        self.calls = []

    def query_assets(self): return None
    def query_positions(self): return [PositionView("000001.SZ", 100, 100, 10, 1000, dt.date(2026, 7, 10))]
    def query_orders(self, status=None): return [OrderView("qt-1", "000001.SZ", "unexpected", 100, 10, "unexpected", dt.datetime(2026, 7, 10))]
    def record(self, *args, **kwargs): self.calls.append(("record", args, kwargs))
    async def buy(self, **kwargs): self.calls.append(("buy", kwargs)); return ExecutionResult("qt-1")
    async def buy_percent(self, **kwargs): return await self.buy(**kwargs)
    async def buy_amount(self, **kwargs): return await self.buy(**kwargs)
    async def sell(self, **kwargs): return await self.buy(**kwargs)
    async def sell_percent(self, **kwargs): return await self.buy(**kwargs)
    async def sell_amount(self, **kwargs): return await self.buy(**kwargs)
    async def trade_target_pct(self, **kwargs): return await self.buy(**kwargs)
    async def cancel(self, order_id): self.calls.append(("cancel", order_id)); return order_id
    async def cancel_all(self, side=None): self.calls.append(("cancel_all", side)); return 1


async def test_port_backed_broker_maps_empty_assets_views_and_unknown_order_values():
    """FR-0204 AC-4/AC-5: legacy views retain portfolio identity and unknown maps."""
    broker = PortBackedBroker(RecordingPort(), "portfolio-1", BrokerKind.SIMULATION)

    assert (broker.asset.portfolio_id, broker.asset.total) == ("portfolio-1", 0.0)
    assert broker.positions["000001.SZ"].portfolio_id == "portfolio-1"
    assert broker.orders[0].side is OrderSide.UNKNOWN
    assert broker.orders[0].status is OrderStatus.UNKNOWN


async def test_port_backed_broker_transparently_delegates_trade_and_cancellation():
    """FR-0204 AC-5: high-level arguments and return values pass through unchanged."""
    port = RecordingPort()
    broker = PortBackedBroker(port, "portfolio-1", BrokerKind.SIMULATION)
    result = await broker.buy("000001.SZ", 100, price=10, strategy_id="strategy-1")

    assert result.order_id == "qt-1"
    assert port.calls == [("buy", {"asset": "000001.SZ", "shares": 100, "price": 10, "order_time": None, "timeout": 0.5, "strategy_id": "strategy-1"})]
    assert await broker.cancel_order("qt-1") == "qt-1"
