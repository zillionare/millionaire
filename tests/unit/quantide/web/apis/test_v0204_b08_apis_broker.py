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


from unittest.mock import patch
