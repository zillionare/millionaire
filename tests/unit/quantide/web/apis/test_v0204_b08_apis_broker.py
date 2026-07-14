"""B08-apis-broker: Test small helper functions in web/apis/broker.py."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest

from quantide.core.enums import FrameType
from quantide.web.apis import broker as broker_api
from quantide.web.apis.broker import (
    build_asset_overview,
    _backtest_requires_bid_time,
    _get_broker,
    _require_broker,
    status,
)


# ---------------------------------------------------------------------------
# build_asset_overview
# ---------------------------------------------------------------------------


def test_build_asset_overview_profit():
    asset = MagicMock()
    asset.total = 110.0
    asset.principal = 100.0
    asset.cash = 10.0
    asset.frozen_cash = 0.0
    asset.market_value = 100.0
    got = build_asset_overview(asset)
    assert got["total"] == 110.0
    assert got["pnl"] == 10.0
    assert got["pnl_pct"] == 0.1


def test_build_asset_overview_loss():
    asset = MagicMock()
    asset.total = 90.0
    asset.principal = 100.0
    asset.cash = 5.0
    asset.frozen_cash = 0.0
    asset.market_value = 85.0
    got = build_asset_overview(asset)
    assert got["pnl"] == -10.0
    assert got["pnl_pct"] == -0.1


def test_build_asset_overview_zero_principal():
    asset = MagicMock()
    asset.total = 100.0
    asset.principal = 0.0
    asset.cash = 0.0
    asset.frozen_cash = 0.0
    asset.market_value = 0.0
    got = build_asset_overview(asset)
    assert got["pnl_pct"] == 0.0


# ---------------------------------------------------------------------------
# _backtest_requires_bid_time
# ---------------------------------------------------------------------------


def test_backtest_requires_bid_time_no_bid_in_backtest(db):
    """bid_time is None + runtime_mode='backtest' → True."""
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        assert _backtest_requires_bid_time(None) is True


def test_backtest_requires_bid_time_with_bid_in_backtest(db):
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        assert _backtest_requires_bid_time(datetime.datetime.now()) is False


def test_backtest_requires_bid_time_live_mode(db):
    """In live mode, doesn't require bid time."""
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "live"
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        assert _backtest_requires_bid_time(None) is False


# ---------------------------------------------------------------------------
# _get_broker
# ---------------------------------------------------------------------------


def test_get_broker_no_registry_returns_none():
    req = MagicMock()
    req.scope = {}  # no registry
    req.query_params = {}
    assert _get_broker(req) is None


def test_get_broker_query_params_used():
    """When kind+id in query_params, use them."""
    reg = MagicMock()
    reg.get = MagicMock(return_value="broker-1")
    req = MagicMock()
    req.scope = {"registry": reg}
    req.query_params = {"kind": "live", "id": "b1"}
    got = _get_broker(req)
    assert got == "broker-1"
    reg.get.assert_called_once_with("live", "b1")


def test_get_broker_session_active_used():
    """When session has active_account_kind/id, use them."""
    reg = MagicMock()
    reg.get = MagicMock(return_value="broker-2")
    req = MagicMock()
    req.scope = {"registry": reg, "session": {"active_account_kind": "backtest", "active_account_id": "b2"}}
    req.query_params = {}
    got = _get_broker(req)
    assert got == "broker-2"
    reg.get.assert_called_once_with("backtest", "b2")


def test_get_broker_default_used():
    """Falls back to default account."""
    reg = MagicMock()
    reg.get_default = MagicMock(return_value=("live", "default"))
    reg.get = MagicMock(return_value="broker-3")
    req = MagicMock()
    req.scope = {"registry": reg, "session": {}}
    req.query_params = {}
    got = _get_broker(req)
    assert got == "broker-3"
    reg.get.assert_called_once_with("live", "default")


def test_get_broker_no_default_returns_none():
    reg = MagicMock()
    reg.get_default = MagicMock(return_value=None)
    req = MagicMock()
    req.scope = {"registry": reg, "session": {}}
    req.query_params = {}
    assert _get_broker(req) is None


# ---------------------------------------------------------------------------
# _require_broker
# ---------------------------------------------------------------------------


def test_require_broker_raises_when_no_broker():
    reg = MagicMock()
    reg.get_default = MagicMock(return_value=None)
    req = MagicMock()
    req.scope = {"registry": reg, "session": {}}
    req.query_params = {}
    with pytest.raises(RuntimeError, match="broker not found"):
        _require_broker(req)


def test_require_broker_returns_when_present():
    reg = MagicMock()
    reg.get_default = MagicMock(return_value=("live", "default"))
    reg.get = MagicMock(return_value="broker")
    req = MagicMock()
    req.scope = {"registry": reg, "session": {}}
    req.query_params = {}
    assert _require_broker(req) == "broker"


# ---------------------------------------------------------------------------
# status route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_endpoint():
    req = MagicMock()
    req.url = "http://test"
    resp = await status(req)
    assert resp["status"] == "ok"
    assert resp["listen"] == "http://test"
    assert "version" in resp


# ---------------------------------------------------------------------------
# Endpoint delegation tests (mock broker)
# ---------------------------------------------------------------------------


from quantide.web.apis import broker as broker_api
from quantide.web.apis.broker import (
    list_accounts,
    start_backtest,
    stop_backtest,
)


def _req(json=None, scope=None, query_params=None):
    req = MagicMock()
    req.json = json or {}
    req.scope = scope or {}
    req.query_params = query_params or {}
    return req


@pytest.mark.asyncio
async def test_start_backtest_delegates_to_broker():
    fake_broker = MagicMock()
    fake_broker.start_backtest = MagicMock(return_value={"account_name": "x"})
    reg = MagicMock()
    reg.get_default = MagicMock(return_value=("backtest", "b1"))
    reg.get = MagicMock(return_value=fake_broker)
    req = _req(json={"name": "x"}, scope={"registry": reg})
    resp = await start_backtest(req)
    assert resp == {"account_name": "x"}


@pytest.mark.asyncio
async def test_start_backtest_no_broker_raises():
    from quantide.web.apis import broker as broker_api_mod
    req = _req(json={})  # no registry
    with pytest.raises(RuntimeError, match="broker not found"):
        await start_backtest(req)


@pytest.mark.asyncio
async def test_stop_backtest_delegates():
    """stop_backtest is async, awaited for fake broker."""
    fake_broker = MagicMock()
    fake_broker.stop_backtest = AsyncMock(return_value={"stopped": True})
    reg = MagicMock()
    reg.get_default = MagicMock(return_value=("backtest", "b1"))
    reg.get = MagicMock(return_value=fake_broker)
    req = _req(scope={"registry": reg})
    resp = await stop_backtest(req)
    assert resp == {"stopped": True}
    fake_broker.stop_backtest.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_backtest_no_broker_raises():
    req = _req()
    with pytest.raises(RuntimeError):
        await stop_backtest(req)


@pytest.mark.asyncio
async def test_list_accounts_delegates():
    fake_broker = MagicMock()
    fake_broker.list_accounts = MagicMock(return_value=[{"id": "a1"}])
    reg = MagicMock()
    reg.get_default = MagicMock(return_value=("live", "b1"))
    reg.get = MagicMock(return_value=fake_broker)
    req = _req(scope={"registry": reg})
    resp = await list_accounts(req)
    assert resp == [{"id": "a1"}]


@pytest.mark.asyncio
async def test_list_accounts_no_broker_raises():
    req = _req()
    with pytest.raises(RuntimeError):
        await list_accounts(req)


# ---------------------------------------------------------------------------
# buy/sell endpoints
# ---------------------------------------------------------------------------


from quantide.web.apis.broker import (
    buy,
    buy_amount,
    buy_percent,
    positions,
    sell,
    sell_amount,
    sell_percent,
)


def _req_with_broker():
    fake_broker = MagicMock()
    reg = MagicMock()
    reg.get_default = MagicMock(return_value=("backtest", "b1"))
    reg.get = MagicMock(return_value=fake_broker)
    return _req(scope={"registry": reg}), fake_broker


@pytest.mark.asyncio
async def test_buy_no_bid_time_in_backtest_returns_400():
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        req, fake_broker = _req_with_broker()
        resp = await buy(req, asset="000001.SZ", price=10.0, shares=100, bid_time=None)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_buy_with_bid_time_calls_broker():
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    fake_broker = MagicMock()
    fake_broker.buy = AsyncMock(return_value={"filled": True})
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        req = _req()
        req.json = {}
        req.scope = {
            "registry": MagicMock(get_default=MagicMock(return_value=("backtest", "b1")), get=MagicMock(return_value=fake_broker))
        }
        resp = await buy(req, asset="000001.SZ", price=10.0, shares=100, bid_time=datetime.datetime.now())
    assert resp == {"filled": True}


@pytest.mark.asyncio
async def test_buy_live_mode_no_bid_time_ok():
    """In live mode, no bid_time is OK."""
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "live"
    fake_broker = MagicMock()
    fake_broker.buy = AsyncMock(return_value={"ok": True})
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        reg = MagicMock()
        reg.get_default = MagicMock(return_value=("live", "b1"))
        reg.get = MagicMock(return_value=fake_broker)
        req = _req(scope={"registry": reg})
        resp = await buy(req, asset="000001.SZ", price=10.0, shares=100, bid_time=None)
    assert resp == {"ok": True}


@pytest.mark.asyncio
async def test_buy_percent_invalid_returns_400():
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        req, _ = _req_with_broker()
        resp = await buy_percent(req, asset="000001.SZ", percent=2.0, bid_time=datetime.datetime.now())
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_buy_percent_zero_returns_400():
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        req, _ = _req_with_broker()
        resp = await buy_percent(req, asset="000001.SZ", percent=0, bid_time=datetime.datetime.now())
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_buy_percent_valid_calls_broker():
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    fake_broker = MagicMock()
    fake_broker.buy_percent = AsyncMock(return_value={"ok": True})
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        reg = MagicMock()
        reg.get_default = MagicMock(return_value=("backtest", "b1"))
        reg.get = MagicMock(return_value=fake_broker)
        req = _req(scope={"registry": reg})
        resp = await buy_percent(req, asset="000001.SZ", percent=0.5, bid_time=datetime.datetime.now())
    assert resp == {"ok": True}


@pytest.mark.asyncio
async def test_buy_amount_delegates():
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    fake_broker = MagicMock()
    fake_broker.buy_amount = AsyncMock(return_value={"ok": True})
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        reg = MagicMock()
        reg.get_default = MagicMock(return_value=("backtest", "b1"))
        reg.get = MagicMock(return_value=fake_broker)
        req = _req(scope={"registry": reg})
        resp = await buy_amount(req, asset="000001.SZ", amount=1000, bid_time=datetime.datetime.now())
    assert resp == {"ok": True}


@pytest.mark.asyncio
async def test_buy_amount_no_bid_in_backtest():
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        req, _ = _req_with_broker()
        resp = await buy_amount(req, asset="000001.SZ", amount=1000, bid_time=None)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_sell_no_bid_returns_400():
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        req, _ = _req_with_broker()
        resp = await sell(req, asset="000001.SZ", price=10.0, shares=100, bid_time=None)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_sell_calls_broker():
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    fake_broker = MagicMock()
    fake_broker.sell = AsyncMock(return_value={"sold": True})
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        reg = MagicMock()
        reg.get_default = MagicMock(return_value=("backtest", "b1"))
        reg.get = MagicMock(return_value=fake_broker)
        req = _req(scope={"registry": reg})
        resp = await sell(req, asset="000001.SZ", price=10.0, shares=100, bid_time=datetime.datetime.now())
    assert resp == {"sold": True}


@pytest.mark.asyncio
async def test_sell_percent_invalid():
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        req, _ = _req_with_broker()
        resp = await sell_percent(req, asset="000001.SZ", percent=1.5, bid_time=datetime.datetime.now())
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_sell_percent_valid():
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    fake_broker = MagicMock()
    fake_broker.sell_percent = AsyncMock(return_value={"ok": True})
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        reg = MagicMock()
        reg.get_default = MagicMock(return_value=("backtest", "b1"))
        reg.get = MagicMock(return_value=fake_broker)
        req = _req(scope={"registry": reg})
        resp = await sell_percent(req, asset="000001.SZ", percent=0.3, bid_time=datetime.datetime.now())
    assert resp == {"ok": True}


@pytest.mark.asyncio
async def test_sell_amount_no_bid():
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        req, _ = _req_with_broker()
        resp = await sell_amount(req, asset="000001.SZ", amount=1000, bid_time=None)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_sell_amount_valid():
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    fake_broker = MagicMock()
    fake_broker.sell_amount = AsyncMock(return_value={"ok": True})
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        reg = MagicMock()
        reg.get_default = MagicMock(return_value=("backtest", "b1"))
        reg.get = MagicMock(return_value=fake_broker)
        req = _req(scope={"registry": reg})
        resp = await sell_amount(req, asset="000001.SZ", amount=1000, bid_time=datetime.datetime.now())
    assert resp == {"ok": True}


@pytest.mark.asyncio
async def test_positions_delegates():
    fake_broker = MagicMock()
    fake_broker.get_position = MagicMock(return_value={"shares": 100})
    reg = MagicMock()
    reg.get_default = MagicMock(return_value=("live", "b1"))
    reg.get = MagicMock(return_value=fake_broker)
    req = _req(scope={"registry": reg})
    resp = await positions(req, asset="000001.SZ")
    assert resp == {"shares": 100}


from unittest.mock import AsyncMock, patch
