"""Malformed manual orders cannot reach a broker."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from quantide.web.pages.trade_main import place_order_trade
from quantide.web.services import trade_accounts


@pytest.mark.parametrize(
    "changes",
    [
        {"side": "unexpected"},
        {"order_mode": "unexpected"},
        {"price_mode": "unexpected"},
        {"price": "nan"},
        {"price": "inf"},
        {"value": "nan"},
        {"value": "inf"},
    ],
)
async def test_invalid_manual_order_never_calls_broker(monkeypatch, changes):
    broker = SimpleNamespace(buy=AsyncMock(), buy_amount=AsyncMock(), sell=AsyncMock())
    form = {
        "asset": "000001.SZ", "side": "BUY", "price_mode": "LIMIT",
        "order_mode": "AMOUNT", "price": "10", "value": "1", **changes,
    }

    async def request_form():
        return form

    monkeypatch.setattr(
        "quantide.web.pages.trade_main.resolve_order_account", lambda *args: (broker, "simulation")
    )
    request = SimpleNamespace(scope={}, form=request_form)
    response = await place_order_trade(request)
    assert "下单失败" not in response.body.decode()
    assert "委托已提交" not in response.body.decode()
    broker.buy.assert_not_called()
    broker.buy_amount.assert_not_called()
    broker.sell.assert_not_called()


def test_ce_default_live_account_cannot_be_resolved_without_simulation():
    registry = SimpleNamespace(
        get_default=lambda: ("qmt", "real-account"), list_by_kind=lambda kind: []
    )
    assert trade_accounts.resolve_active_account(registry, {}, {}, False) is None
    assert trade_accounts.resolve_order_account(registry, {}, {}, False) == (None, "")
