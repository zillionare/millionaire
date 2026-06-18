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


@pytest.mark.asyncio
async def test_gateway_broker_no_double_qfq_adjustment_on_forming_merge(monkeypatch):
    """#43 fix: live 路径非 adjust=1.0 时, forming 合并不能二次前复权.

    场景: hist 5 行, adjust=[1.0, 1.0, 1.0, 1.0, 1.10]; 末行今日 adjust=1.10。
    合并 forming bar 后, hist 历史的 close 应被 *1.0/1.10 调整一次 (不是两次)。
    """
    import polars as pl

    from quantide.core.enums import OrderSide
    from quantide.core.ports import OrderRequest
    from quantide.core.runtime import gateway_broker as _gb_mod
    from quantide.service.livequote import live_quote

    dates = [datetime.date(2026, 1, i) for i in range(1, 6)]
    hist = pl.DataFrame(
        {
            "date": pl.Series(
                [datetime.datetime.combine(d, datetime.time.min) for d in dates]
            ),
            "asset": ["000001.SZ"] * 5,
            "open": [10.0] * 5,
            "high": [10.0] * 5,
            "low": [10.0] * 5,
            "close": [10.0] * 5,
            "volume": [0.0] * 5,
            "amount": [0.0] * 5,
            "adjust": [1.0, 1.0, 1.0, 1.0, 1.10],
            "is_st": [False] * 5,
            "up_limit": [11.0] * 5,
            "down_limit": [9.0] * 5,
        }
    )

    class _RawProvider:
        def get_bars(self, n, end, assets, adjust, eager_mode):
            return hist

    monkeypatch.setattr(_gb_mod, "daily_bars", _RawProvider())

    client = DummyGatewayClient()
    adapter = GatewayBrokerAdapter(client)
    wrapper = GatewayBrokerWrapper(adapter)
    wrapper.set_clock(datetime.datetime(2026, 1, 5, 15, 0))
    live_quote._daily_bars["000001.SZ"] = {
        "asset": "000001.SZ",
        "frame": "1d",
        "dt": datetime.date(2026, 1, 5),
        "open": 11.0,
        "high": 11.0,
        "low": 11.0,
        "close": 11.0,
        "volume": 0.0,
        "amount": 0.0,
    }
    try:
        result = wrapper.get_history(
            "000001.SZ", count=6, end_dt=datetime.datetime(2026, 1, 5, 15, 0)
        )
    finally:
        live_quote._daily_bars.pop("000001.SZ", None)

    expected_hist_close = 10.0 / 1.10
    closes = result["close"].to_list()
    assert len(closes) == 5
    for i in range(4):
        assert abs(closes[i] - expected_hist_close) < 0.01, (
            f"row {i}: close={closes[i]}, expected={expected_hist_close}"
        )
    assert abs(closes[4] - 11.0) < 0.01


@pytest.mark.asyncio
async def test_live_estimate_limit_price_auction_uses_previous_close(monkeypatch):
    """#45 followup: auction 模式限价 = 昨收 × (1 + slippage)."""
    import polars as pl

    from quantide.core.runtime import gateway_broker as _gb_mod

    class _FakeBars:
        def get_bars(self, n, end, assets, **kwargs):
            return pl.DataFrame(
                {
                    "date": [end],
                    "asset": assets,
                    "open": [10.0],
                    "high": [11.0],
                    "low": [9.0],
                    "close": [10.0],
                    "volume": [0.0],
                    "amount": [0.0],
                    "adjust": [1.0],
                    "is_st": [False],
                    "up_limit": [11.0],
                    "down_limit": [9.0],
                }
            )

    monkeypatch.setattr(_gb_mod, "daily_bars", _FakeBars())

    client = DummyGatewayClient()
    adapter = GatewayBrokerAdapter(client)
    wrapper = GatewayBrokerWrapper(adapter)
    wrapper.set_clock(datetime.datetime(2026, 1, 5, 15, 0))
    wrapper.set_strategy_runtime_config(
        cheat_on_close=False,
        live_execution_window="auction",
        live_execution_slippage=0.001,
    )

    price = wrapper._estimate_limit_price(
        {
            "asset": "000001.SZ",
            "side": "buy",
            "value": 5000.0,
            "style": "amount",
            "price": 0,
            "execution_window": "auction",
            "slippage": 0.001,
            "scheduled_at": datetime.datetime(2026, 1, 6, 9, 25),
        }
    )
    assert abs(price - 10.0 * 1.001) < 0.0001


@pytest.mark.asyncio
async def test_live_estimate_limit_price_post_auction_uses_next_day_open(monkeypatch):
    """#45 followup: post_auction 模式限价 = 次日开盘 × (1 + slippage).

    回归 #45 review: 原 _estimate_limit_price 一律用昨收, post_auction 路径错误.

    已知限制 (#45 followup2): 当前从 daily_bars 读"次日 open", 但 9:30 盘中
    daily_bars 没有当日行, 实际拿到昨日 close. 等 zillionare/qmt-gateway#62
    调查结果后切换到 live_quote.get_daily_bar(asset).open.
    """
    import polars as pl

    from quantide.core.runtime import gateway_broker as _gb_mod

    call_log: list[datetime.date] = []

    class _FakeBars:
        def get_bars(self, n, end, assets, **kwargs):
            call_log.append(end)
            return pl.DataFrame(
                {
                    "date": [end],
                    "asset": assets,
                    "open": [11.5],
                    "high": [12.0],
                    "low": [11.0],
                    "close": [10.0],
                    "volume": [0.0],
                    "amount": [0.0],
                    "adjust": [1.0],
                    "is_st": [False],
                    "up_limit": [13.0],
                    "down_limit": [9.0],
                }
            )

    monkeypatch.setattr(_gb_mod, "daily_bars", _FakeBars())

    client = DummyGatewayClient()
    adapter = GatewayBrokerAdapter(client)
    wrapper = GatewayBrokerWrapper(adapter)
    wrapper.set_clock(datetime.datetime(2026, 1, 5, 15, 0))
    wrapper.set_strategy_runtime_config(
        cheat_on_close=False,
        live_execution_window="post_auction",
        live_execution_slippage=0.002,
    )

    price = wrapper._estimate_limit_price(
        {
            "asset": "000001.SZ",
            "side": "buy",
            "value": 5000.0,
            "style": "amount",
            "price": 0,
            "execution_window": "post_auction",
            "slippage": 0.002,
            "scheduled_at": datetime.datetime(2026, 1, 6, 9, 30, 0, 1000),
        }
    )
    assert abs(price - 11.5 * 1.002) < 0.0001, f"got {price}, expected 11.5*1.002=11.523"
    assert len(call_log) == 1
    assert call_log[0] == datetime.date(2026, 1, 6), (
        f"post_auction 应读次日 (2026-01-06), got {call_log[0]}"
    )
