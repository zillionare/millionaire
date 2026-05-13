"""Tests for the local qmt-gateway stub support server."""

from __future__ import annotations

import json
import urllib.request

import pytest

from quantide.core.enums import OrderSide
from quantide.core.ports import OrderRequest
from quantide.core.runtime.gateway_broker import GatewayBrokerAdapter
from quantide.core.runtime.gateway_client import GatewayClient
from tests.e2e.support.gateway_stub import (
    GatewayCancelScript,
    GatewayScenario,
    GatewaySubmitScript,
    running_gateway_stub,
)


def test_gateway_stub_keeps_prefixed_ping_compatibility() -> None:
    with running_gateway_stub(prefix="/qmt") as stub:
        with urllib.request.urlopen(f"{stub.base_url}/ping", timeout=2) as response:
            assert json.loads(response.read().decode("utf-8")) == {"ok": True}


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_gateway_stub_exercises_trade_asset_order_trade_and_cancel_paths() -> (
    None
):
    scenario = GatewayScenario(
        asset={
            "principal": 100_000,
            "total": 101_000,
            "cash": 80_000,
            "market_value": 21_000,
            "frozen_cash": 0,
        },
        positions=[
            {
                "symbol": "000001.SZ",
                "shares": 100,
                "avail": 100,
                "cost": 10,
                "market_value": 1000,
            }
        ],
        auto_fill=False,
    )
    with running_gateway_stub(prefix="/qmt", scenario=scenario) as stub:
        client = GatewayClient(stub.base_url, username="u", password="p", timeout=2)
        adapter = GatewayBrokerAdapter(client)

        assert adapter.query_assets().total == 101_000
        assert adapter.query_positions()[0].asset == "000001.SZ"

        ack = await adapter.submit(
            OrderRequest(asset="000001.SZ", side=OrderSide.BUY, value=200, price=10)
        )
        assert ack.status == "submitted"
        assert ack.order_id

        orders = adapter.query_orders()
        assert orders[0].order_id == ack.order_id
        assert orders[0].status == "submitted"

        cancel = await adapter.cancel(ack.order_id)
        assert cancel.success is True
        assert adapter.query_orders(status="cancelled")[0].order_id == ack.order_id


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_gateway_stub_streams_scripted_ws_quotes() -> None:
    websockets = pytest.importorskip("websockets")
    quote = {
        "symbol": "000002.SZ",
        "timestamp": "2026-05-08 09:31:00",
        "1m": {
            "open": 9,
            "high": 11,
            "low": 8,
            "close": 10.5,
            "volume": 100,
            "amount": 1050,
        },
    }
    with running_gateway_stub(
        prefix="/qmt", scenario=GatewayScenario(quotes=[quote])
    ) as stub:
        async with websockets.connect(stub.ws_url) as ws:
            payload = json.loads(await ws.recv())

    assert payload == quote


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_gateway_stub_preserves_qtoid_when_query_snapshots_only_expose_external_order_id() -> None:
    scenario = GatewayScenario(
        submit_scripts=[
            GatewaySubmitScript(
                side="buy",
                symbol="000001.SZ",
                response={"success": True, "order_id": "ext-qt-1"},
                order={
                    "symbol": "000001.SZ",
                    "side": "buy",
                    "shares": 200,
                    "price": 10.2,
                    "status": "submitted",
                    "filled": 0,
                    "time": "2026-05-13 09:31:00",
                },
                trades=[
                    {
                        "tid": "gw-t1",
                        "symbol": "000001.SZ",
                        "side": "buy",
                        "shares": 200,
                        "price": 10.2,
                        "amount": 2040,
                        "time": "2026-05-13 09:31:05",
                    }
                ],
                expose_order_qtoid=False,
                expose_trade_qtoid=False,
            )
        ]
    )

    with running_gateway_stub(prefix="/qmt", scenario=scenario) as stub:
        client = GatewayClient(stub.base_url, username="u", password="p", timeout=2)
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


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_gateway_stub_accepts_dict_scenario_with_scripted_partial_fill_and_cancel() -> None:
    scenario = {
        "submit_scripts": [
            {
                "side": "buy",
                "symbol": "000001.SZ",
                "response": {"success": True, "qtoid": "qt-partial", "order_id": "ext-qt-partial"},
                "order": {
                    "symbol": "000001.SZ",
                    "side": "buy",
                    "shares": 500,
                    "price": 10.0,
                    "status": "partial",
                    "filled": 100,
                    "time": "2026-05-13 09:32:00",
                },
                "trades": [
                    {
                        "tid": "gw-partial-1",
                        "symbol": "000001.SZ",
                        "side": "buy",
                        "shares": 100,
                        "price": 10.0,
                        "amount": 1000,
                        "time": "2026-05-13 09:32:03",
                    }
                ],
            }
        ],
        "cancel_scripts": [
            {
                "qtoid": "qt-partial",
                "response": {"success": True, "qtoid": "qt-partial"},
                "order_status": "cancelled",
            }
        ],
    }

    with running_gateway_stub(prefix="/qmt", scenario=scenario) as stub:
        client = GatewayClient(stub.base_url, username="u", password="p", timeout=2)
        adapter = GatewayBrokerAdapter(client)

        ack = await adapter.submit(
            OrderRequest(
                asset="000001.SZ",
                side=OrderSide.BUY,
                value=500,
                price=10.0,
                extra={"qtoid": "qt-partial"},
            )
        )
        orders = adapter.query_orders()
        cancel = await adapter.cancel(ack.order_id)
        cancelled_orders = adapter.query_orders(status="cancelled")

    assert ack.order_id == "qt-partial"
    assert orders[0].filled == 100
    assert orders[0].status == "partial"
    assert cancel.success is True
    assert cancelled_orders[0].order_id == "qt-partial"
