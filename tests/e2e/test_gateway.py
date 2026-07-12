"""L2 gateway and degradation UI journeys."""

from __future__ import annotations

import pytest

from quantide.core.enums import OrderSide
from quantide.core.ports import OrderRequest
from quantide.core.runtime.gateway_broker import GatewayBrokerAdapter
from quantide.core.runtime.gateway_client import GatewayClient
from tests.e2e.pages import SystemPage, TradePage
from tests.e2e.support.gateway_stub import GatewayScenario, running_gateway_stub


@pytest.mark.e2e
@pytest.mark.e2e_gateway
def test_gateway_settings_page_can_test_and_save_configuration(gateway_session):
    """AC-FR0340-01 AC-FR0340-02: 网关页可连通性测试并持久化保存配置."""
    with running_gateway_stub(prefix="/qmt") as gateway_stub:
        page = SystemPage(gateway_session.client).open_gateway()
        assert page.status_code == 200
        page.require("交易网关", "保存配置")

        test_response = gateway_session.client.post(
            "/system/gateway/test",
            data={
                "gateway_enabled": "on",
                "gateway_server": gateway_stub.host,
                "gateway_port": str(gateway_stub.port),
                "gateway_prefix": gateway_stub.prefix,
                "gateway_api_key": "stub-api-key",
                "gateway_timeout": "5",
            },
        )
        assert test_response.status_code == 200
        assert "连通性测试通过" in test_response.text

        save_response = gateway_session.client.post(
            "/system/gateway/save",
            data={
                "gateway_enabled": "on",
                "gateway_server": gateway_stub.host,
                "gateway_port": str(gateway_stub.port),
                "gateway_prefix": gateway_stub.prefix,
                "gateway_api_key": "stub-api-key",
                "gateway_timeout": "5",
            },
        )
        assert save_response.status_code == 200
        assert "网关配置已保存" in save_response.text


@pytest.mark.e2e
@pytest.mark.e2e_gateway
def test_missing_gateway_disables_live_trade_but_keeps_gateway_page_available(gateway_session):
    """AC-FR0180-01 AC-FR0180-03 AC-FR0340-03: A 类降级下实盘入口返回 503, 网关管理页仍可访问."""
    live_page = TradePage(gateway_session.client).open_live()
    assert live_page.status_code == 503
    live_page.require("功能已禁用", "前往交易网关")

    gateway_page = SystemPage(gateway_session.client).open_gateway()
    assert gateway_page.status_code == 200
    gateway_page.require("交易网关", "保存配置")


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@pytest.mark.e2e
@pytest.mark.e2e_gateway
async def test_gateway_reject_response_does_not_create_local_trade_state():
    """AC-FR0180-10 AC-FR0420-09: 网关拒单时不产生本地委托/成交残留."""
    scenario = GatewayScenario(asset={"principal": 200000, "total": 200000, "cash": 200000, "market_value": 0, "frozen_cash": 0}, reject_next_orders=["price out of range"])
    with running_gateway_stub(prefix="/qmt", scenario=scenario) as stub:
        adapter = GatewayBrokerAdapter(
            GatewayClient(stub.base_url, username="u", password="p", timeout=2)
        )
        ack = await adapter.submit(
            OrderRequest(
                asset="000001.SZ",
                side=OrderSide.BUY,
                value=100,
                price=10.0,
                extra={"qtoid": "shield-gateway-reject"},
            )
        )

        assert ack.order_id is None
        assert ack.status == "rejected"
        assert "price out of range" in ack.message
        assert adapter.query_orders() == []
        assert adapter.query_trades() == []
