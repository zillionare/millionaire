import pytest

from quantide.core.enums import OrderSide
from quantide.core.ports import OrderRequest
from quantide.core.runtime.gateway_broker import (
    GatewayBrokerAdapter,
    GatewayBrokerWrapper,
    GatewayTradeStateConsistencyError,
)


class DummyGatewayClient:
    def __init__(self):
        self.post_calls = []
        self.get_calls = []

    def post_form(self, path, data):
        self.post_calls.append((path, data))
        if path == "/api/trade/buy":
            return {"success": True, "qtoid": data.get("qtoid", "q1"), "order_id": "1001"}
        if path == "/api/trade/sell":
            return {"success": True, "qtoid": data.get("qtoid", "q2"), "order_id": "1002"}
        return {"success": True}

    def get_json(self, path, params=None):
        self.get_calls.append((path, params))
        if path == "/api/trade/asset":
            return {
                "principal": 100000,
                "total": 101000,
                "cash": 50000,
                "market_value": 51000,
                "frozen_cash": 0,
            }
        if path == "/api/trade/positions":
            return [{"symbol": "000001.SZ", "shares": 200, "avail": 200, "cost": 10, "market_value": 2100}]
        if path == "/api/trade/orders":
            return [{"qtoid": "1001", "symbol": "000001.SZ", "side": "buy", "shares": 200, "price": 10, "status": "submitted"}]
        return []


class MappingAwareGatewayClient(DummyGatewayClient):
    def __init__(self):
        super().__init__()
        self.last_submit_payload = None

    def post_form(self, path, data):
        self.post_calls.append((path, data))
        if path in {"/api/trade/buy", "/api/trade/sell"}:
            self.last_submit_payload = dict(data)
            return {
                "success": True,
                "qtoid": data.get("qtoid"),
                "order_id": f"ext-{data.get('qtoid')}",
            }
        return {"success": True}

    def get_json(self, path, params=None):
        self.get_calls.append((path, params))
        if path == "/api/trade/orders":
            return [
                {
                    "order_id": f"ext-{self.last_submit_payload['qtoid']}",
                    "symbol": self.last_submit_payload["symbol"],
                    "side": "buy",
                    "shares": self.last_submit_payload["shares"],
                    "price": self.last_submit_payload["price"],
                    "status": "submitted",
                }
            ]
        if path == "/api/trade/trades":
            return [
                {
                    "tid": "gw-t1",
                    "order_id": f"ext-{self.last_submit_payload['qtoid']}",
                    "symbol": self.last_submit_payload["symbol"],
                    "side": "buy",
                    "shares": self.last_submit_payload["shares"],
                    "price": self.last_submit_payload["price"],
                    "amount": self.last_submit_payload["shares"] * self.last_submit_payload["price"],
                    "time": "2026-05-08 12:00:00",
                }
            ]
        return super().get_json(path, params=params)


class BrokenMappingGatewayClient(DummyGatewayClient):
    def __init__(self, *, response_qtoid="gw-other", orders=None, trades=None):
        super().__init__()
        self.response_qtoid = response_qtoid
        self.orders = orders or []
        self.trades = trades or []

    def post_form(self, path, data):
        self.post_calls.append((path, data))
        if path in {"/api/trade/buy", "/api/trade/sell"}:
            return {
                "success": True,
                "qtoid": self.response_qtoid,
                "order_id": "ext-broken",
            }
        return {"success": True}

    def get_json(self, path, params=None):
        self.get_calls.append((path, params))
        if path == "/api/trade/orders":
            return list(self.orders)
        if path == "/api/trade/trades":
            return list(self.trades)
        return super().get_json(path, params=params)


@pytest.mark.asyncio
async def test_gateway_broker_submit_shares():
    client = DummyGatewayClient()
    adapter = GatewayBrokerAdapter(client)
    req = OrderRequest(asset="000001.SZ", side=OrderSide.BUY, value=200, price=10.2)
    ack = await adapter.submit(req)
    assert ack.status == "submitted"
    assert ack.order_id == client.post_calls[-1][1]["qtoid"]


@pytest.mark.asyncio
async def test_gateway_broker_submit_amount_style():
    adapter = GatewayBrokerAdapter(DummyGatewayClient())
    req = OrderRequest(
        asset="000001.SZ",
        side=OrderSide.BUY,
        value=5000,
        style="amount",
        price=10,
    )
    ack = await adapter.submit(req)
    assert ack.status == "submitted"


@pytest.mark.asyncio
async def test_gateway_broker_buy_amount_returns_execution_result():
    client = DummyGatewayClient()
    adapter = GatewayBrokerAdapter(client)

    result = await adapter.buy_amount("000001.SZ", 5000, price=10, strategy_id="s1")

    assert result.order_id == client.post_calls[-1][1]["qtoid"]
    assert result.status == "submitted"
    assert client.post_calls[-1][1]["strategy_id"] == "s1"


def test_gateway_broker_query_assets():
    adapter = GatewayBrokerAdapter(DummyGatewayClient())
    assets = adapter.query_assets()
    assert assets is not None
    assert assets.total == 101000


@pytest.mark.asyncio
async def test_gateway_broker_submit_target_pct_style():
    adapter = GatewayBrokerAdapter(DummyGatewayClient())
    req = OrderRequest(
        asset="000001.SZ",
        side=OrderSide.BUY,
        value=0.2,
        style="target_pct",
        price=10,
    )
    ack = await adapter.submit(req)
    assert ack.status == "submitted"


@pytest.mark.asyncio
async def test_gateway_broker_trade_target_pct_submits_sell_when_overweight():
    client = DummyGatewayClient()
    adapter = GatewayBrokerAdapter(client)

    result = await adapter.trade_target_pct("000001.SZ", 0, price=10)

    path, payload = client.post_calls[-1]
    assert result.order_id is not None
    assert path == "/api/trade/sell"
    assert payload["symbol"] == "000001.SZ"
    assert payload["qtoid"] == result.order_id


@pytest.mark.asyncio
async def test_gateway_broker_wrapper_submit_amount_and_cancel_all():
    client = DummyGatewayClient()
    adapter = GatewayBrokerAdapter(client)
    wrapper = GatewayBrokerWrapper(adapter)

    result = await wrapper.buy_amount("000001.SZ", 5000, price=10)

    assert result.qt_oid == client.post_calls[-1][1]["qtoid"]

    await wrapper.cancel_all_orders(side=OrderSide.BUY)

    assert client.get_calls[-1] == ("/api/trade/orders", None)
    assert client.post_calls[-1][0] == "/api/trade/cancel"
    assert "qtoid" in client.post_calls[-1][1]


@pytest.mark.asyncio
async def test_gateway_broker_wrapper_trade_target_pct_submits_sell_when_overweight():
    client = DummyGatewayClient()
    adapter = GatewayBrokerAdapter(client)
    wrapper = GatewayBrokerWrapper(adapter)

    await wrapper.trade_target_pct("000001.SZ", 0, price=10)

    path, payload = client.post_calls[-1]
    assert path == "/api/trade/sell"
    assert payload["symbol"] == "000001.SZ"


@pytest.mark.asyncio
async def test_gateway_broker_preserves_qtoid_when_gateway_returns_external_order_id_only():
    client = MappingAwareGatewayClient()
    adapter = GatewayBrokerAdapter(client)

    ack = await adapter.submit(
        OrderRequest(
            asset="000001.SZ",
            side=OrderSide.BUY,
            value=200,
            price=10.2,
            extra={"qtoid": "qt-1"},
        )
    )

    orders = adapter.query_orders()
    trades = adapter.query_trades(order_id=ack.order_id)

    assert ack.order_id == "qt-1"
    assert orders[0].order_id == "qt-1"
    assert trades[0].order_id == "qt-1"


@pytest.mark.asyncio
async def test_gateway_broker_rejects_submit_when_gateway_rewrites_qtoid():
    client = BrokenMappingGatewayClient(response_qtoid="gw-rewritten")
    adapter = GatewayBrokerAdapter(client)

    with pytest.raises(GatewayTradeStateConsistencyError):
        await adapter.submit(
            OrderRequest(
                asset="000001.SZ",
                side=OrderSide.BUY,
                value=200,
                price=10.2,
                extra={"qtoid": "qt-1"},
            )
        )


@pytest.mark.asyncio
async def test_gateway_broker_raises_when_known_external_mapping_points_to_other_qtoid():
    client = MappingAwareGatewayClient()
    adapter = GatewayBrokerAdapter(client)
    await adapter.submit(
        OrderRequest(
            asset="000001.SZ",
            side=OrderSide.BUY,
            value=200,
            price=10.2,
            extra={"qtoid": "qt-1"},
        )
    )

    adapter._client = BrokenMappingGatewayClient(
        orders=[
            {
                "qtoid": "qt-other",
                "order_id": "ext-qt-1",
                "symbol": "000001.SZ",
                "side": "buy",
                "shares": 200,
                "price": 10.2,
                "status": "submitted",
            }
        ]
    )

    with pytest.raises(GatewayTradeStateConsistencyError):
        adapter.query_orders()
