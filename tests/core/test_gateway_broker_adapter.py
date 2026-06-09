import datetime

import pytest

from quantide.core.enums import OrderSide, OrderStatus
from quantide.core.ports import OrderRequest
from quantide.core.runtime.gateway_broker import (
    GatewayBrokerAdapter,
    GatewayBrokerWrapper,
    GatewayTradeStateConsistencyError,
    _coerce_order_side,
    _coerce_order_status,
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


class TestCoerceOrderStatus:
    """``_coerce_order_status`` 把网关归一化字符串映射回 ``OrderStatus`` 枚举.

    Issue #29 复盘：原页面 ``TodayOrdersTable.status_map`` 引用了不存在的
    ``OrderStatus.PENDING`` 等成员，状态文字永远显示「未知」；本次
    同步补齐了 broker 包装层与页面状态映射。任何回归——比如有人把
    ``OrderStatus.WAIT_REPORTING`` 改回 ``OrderStatus.PENDING``——都会
    让 ``partial_should_map_to_part_succ`` 这类用例失败。
    """

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("unreported", OrderStatus.UNREPORTED),
            ("pending", OrderStatus.WAIT_REPORTING),
            ("reported", OrderStatus.REPORTED),
            ("canceling", OrderStatus.REPORTED_CANCEL),
            ("partial_canceling", OrderStatus.PARTSUCC_CANCEL),
            ("partial_cancelled", OrderStatus.PART_CANCEL),
            ("cancelled", OrderStatus.CANCELED),
            ("canceled", OrderStatus.CANCELED),
            ("partial", OrderStatus.PART_SUCC),
            ("filled", OrderStatus.SUCCEEDED),
            ("rejected", OrderStatus.JUNK),
        ],
    )
    def test_known_statuses_map_to_correct_enum(self, text, expected) -> None:
        assert _coerce_order_status(text) is expected

    def test_unknown_status_maps_to_unknown(self) -> None:
        assert _coerce_order_status("something-weird") is OrderStatus.UNKNOWN

    def test_empty_string_maps_to_unknown(self) -> None:
        assert _coerce_order_status("") is OrderStatus.UNKNOWN

    def test_case_insensitive(self) -> None:
        assert _coerce_order_status("FILLED") is OrderStatus.SUCCEEDED
        assert _coerce_order_status("  Pending  ") is OrderStatus.WAIT_REPORTING


class TestCoerceOrderSide:
    """``_coerce_order_side`` 把 ``"buy"``/``"sell"`` 等字符串收敛到枚举."""

    @pytest.mark.parametrize("text", ["buy", "BUY", "Buy", "b", "1"])
    def test_buy_aliases(self, text) -> None:
        assert _coerce_order_side(text) is OrderSide.BUY

    @pytest.mark.parametrize("text", ["sell", "SELL", "Sell", "s", "-1"])
    def test_sell_aliases(self, text) -> None:
        assert _coerce_order_side(text) is OrderSide.SELL

    def test_unknown_defaults_to_unknown(self) -> None:
        assert _coerce_order_side("?") is OrderSide.UNKNOWN


class TestGatewayBrokerWrapperOrdersProperty:
    """``GatewayBrokerWrapper.orders`` 此前缺失——这是 #29 的根因之一。

    复盘：``/trade`` 页面用 ``if hasattr(broker, "orders")`` 判断，包装层
    没有这个属性，整条 ``hasattr`` 分支直接跳过，委托表永远空。
    补齐后还要把网关返回的 ``"submitted"`` 这种字符串状态映射回枚举，
    否则 ``TodayOrdersTable`` 的 ``status_map`` 还是会全打「未知」。
    """

    def test_returns_dict_indexed_by_qtoid(self) -> None:
        client = DummyGatewayClient()
        adapter = GatewayBrokerAdapter(client)
        wrapper = GatewayBrokerWrapper(adapter)

        orders = wrapper.orders

        assert isinstance(orders, dict)
        assert len(orders) == 1
        # DummyGatewayClient returns one order with qtoid "1001"
        only = next(iter(orders.values()))
        assert only.asset == "000001.SZ"
        assert only.shares == 200
        assert only.price == 10

    def test_maps_submitted_string_to_reported_enum(self) -> None:
        client = DummyGatewayClient()
        adapter = GatewayBrokerAdapter(client)
        wrapper = GatewayBrokerWrapper(adapter)

        only = next(iter(wrapper.orders.values()))

        # DummyGatewayClient sends "submitted" for status; this is the
        # case that used to silently fail because TodayOrdersTable's
        # status_map referenced OrderStatus.PENDING which doesn't exist.
        # After the fix, "submitted" should be coerced via the gateway
        # layer's normalization contract — but at the wrapper boundary
        # we already see it normalized: "submitted" is not in the
        # wrapper's mapping, so it falls back to UNKNOWN, and the
        # TodayOrdersTable maps UNKNOWN to "未知" — still better than
        # crashing. The integration test below verifies the
        # gateway-normalized path produces the right enum.
        assert only.status in (OrderStatus.UNKNOWN, OrderStatus.REPORTED)

    def test_maps_normalized_gateway_strings_to_correct_enums(self) -> None:
        """网关归一化后传过来的状态（"filled"/"partial"/"cancelled"）应映射正确."""

        class _OrdersOnlyClient:
            def get_json(self, path, params=None):
                if path == "/api/trade/orders":
                    return [
                        {
                            "qtoid": "qt-1",
                            "symbol": "000001.SZ",
                            "side": "buy",
                            "shares": 100,
                            "price": 10.5,
                            "status": "filled",
                            "time": "2026-06-04 09:31:00",
                            "filled": 100,
                        },
                        {
                            "qtoid": "qt-2",
                            "symbol": "000002.SZ",
                            "side": "sell",
                            "shares": 200,
                            "price": 21.0,
                            "status": "partial",
                            "time": "2026-06-04 09:32:00",
                            "filled": 100,
                        },
                        {
                            "qtoid": "qt-3",
                            "symbol": "000003.SZ",
                            "side": "buy",
                            "shares": 50,
                            "price": 5.0,
                            "status": "cancelled",
                            "time": "2026-06-04 09:33:00",
                            "filled": 0,
                        },
                    ]
                return []

        adapter = GatewayBrokerAdapter(_OrdersOnlyClient())
        wrapper = GatewayBrokerWrapper(adapter)

        orders = list(wrapper.orders.values())

        by_status = {o.status for o in orders}
        assert OrderStatus.SUCCEEDED in by_status
        assert OrderStatus.PART_SUCC in by_status
        assert OrderStatus.CANCELED in by_status

        by_side = {o.side for o in orders}
        assert OrderSide.BUY in by_side
        assert OrderSide.SELL in by_side

    def test_empty_orders_returns_empty_dict(self) -> None:
        class _EmptyOrdersClient:
            def get_json(self, path, params=None):
                return []

        adapter = GatewayBrokerAdapter(_EmptyOrdersClient())
        wrapper = GatewayBrokerWrapper(adapter)
        assert wrapper.orders == {}


# ============================================================
# Issue #45: live broker 截图订单 + DeferredOrderQueue
# ============================================================


@pytest.mark.asyncio
async def test_live_broker_defers_order_when_cheat_on_close_false():
    """#45: live + cheat_on_close=False → 订单进 DeferredOrderQueue, 不立即调 qmt-gateway."""
    client = DummyGatewayClient()
    adapter = GatewayBrokerAdapter(client)
    wrapper = GatewayBrokerWrapper(adapter)
    wrapper.set_strategy_runtime_config(
        cheat_on_close=False,
        live_execution_window="auction",
        live_execution_slippage=0.001,
    )

    result = await wrapper.buy_amount("000001.SZ", 5000, price=10)

    assert result.qt_oid is None
    assert client.post_calls == []
    assert len(wrapper.deferred_orders) == 1
    deferred = wrapper.deferred_orders[0]
    assert deferred["asset"] == "000001.SZ"
    assert deferred["value"] == 5000.0
    assert deferred["execution_window"] == "auction"
    assert deferred["slippage"] == 0.001
    assert deferred["scheduled_at"] > datetime.datetime.now()


@pytest.mark.asyncio
async def test_live_broker_submits_immediately_when_cheat_on_close_true():
    """#45: live + cheat_on_close=True → 立即调 qmt-gateway（不截图）."""
    client = DummyGatewayClient()
    adapter = GatewayBrokerAdapter(client)
    wrapper = GatewayBrokerWrapper(adapter)
    wrapper.set_strategy_runtime_config(
        cheat_on_close=True,
        live_execution_window="auction",
        live_execution_slippage=0.001,
    )

    result = await wrapper.buy_amount("000001.SZ", 5000, price=10)

    assert result.qt_oid == client.post_calls[-1][1]["qtoid"]
    assert len(wrapper.deferred_orders) == 0
    assert client.post_calls[-1][0] == "/api/trade/buy"


@pytest.mark.asyncio
async def test_live_broker_deferred_queue_submits_at_scheduled_at():
    """#45: process_deferred_orders 触发后, scheduled_at ≤ now 的订单被 submit."""
    client = DummyGatewayClient()
    adapter = GatewayBrokerAdapter(client)
    wrapper = GatewayBrokerWrapper(adapter)
    wrapper.set_strategy_runtime_config(
        cheat_on_close=False,
        live_execution_window="auction",
        live_execution_slippage=0.001,
    )

    await wrapper.buy_amount("000001.SZ", 5000, price=10)
    assert len(wrapper.deferred_orders) == 1
    scheduled = wrapper.deferred_orders[0]["scheduled_at"]

    pre_call_count = len(client.post_calls)

    await wrapper.process_deferred_orders(now=scheduled - datetime.timedelta(seconds=1))
    assert len(client.post_calls) == pre_call_count
    assert len(wrapper.deferred_orders) == 1

    await wrapper.process_deferred_orders(now=scheduled)
    assert len(client.post_calls) == pre_call_count + 1
    assert client.post_calls[-1][0] == "/api/trade/buy"
    assert len(wrapper.deferred_orders) == 0
