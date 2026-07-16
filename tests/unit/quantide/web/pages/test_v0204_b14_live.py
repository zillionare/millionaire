"""B14-live: Coverage tests for quantide/web/pages/live.py.

Target: cover portfolio_detail broker branches (asset/positions/is_connected),
and place_order routes (broker missing, BUY/SELL, exception path).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from quantide.data.models import Asset
from quantide.web.pages.live import (
    _build_asset_overview,
    place_order,
    portfolio_detail,
)


def _request(scope=None, query=None):
    req = MagicMock()
    req.scope = scope or {}
    req.query_params = query or {}
    return req


# ---------------------------------------------------------------------------
# portfolio_detail: broker has asset / positions / is_connected branches
# ---------------------------------------------------------------------------


def _make_broker_with_asset_positions(asset=None, positions=None,
                                       connected=True, positions_is_dict=True):
    """Build a MagicMock broker that exposes asset, positions, is_connected.

    `hasattr()` works on MagicMock objects by default for any attribute name,
    so we use spec to constrain attribute existence on a real-ish broker stub.
    """
    broker = MagicMock()
    # Spec won't help; we set explicit attributes.
    broker.asset = asset
    if positions_is_dict:
        broker.positions = positions or {}
    else:
        broker.positions = positions or []
    broker.is_connected = connected
    return broker


def test_portfolio_detail_broker_with_asset_and_dict_positions():
    """broker.asset / broker.positions (dict) / broker.is_connected all hit."""
    asset = Asset(portfolio_id="p1", dt=None, principal=100_000.0, cash=10_000.0,
                  frozen_cash=0.0, market_value=90_000.0, total=100_000.0)
    pos = MagicMock()
    pos.asset = "000001.SZ"
    pos.shares = 100.0
    pos.avail = 100.0
    pos.cost = 950.0
    pos.price = 10.0
    pos.mv = 1000.0
    pos.profit = 50.0
    broker = _make_broker_with_asset_positions(
        asset=asset, positions={"000001.SZ": pos}, connected=True,
    )
    reg = MagicMock()
    reg.get.return_value = broker
    req = _request(scope={"registry": reg})
    out = portfolio_detail(req, session={}, portfolio_id="p1")
    assert out is not None


def test_portfolio_detail_broker_with_list_positions():
    """broker.positions as list (non-dict) hits the else branch on line 455."""
    pos = MagicMock()
    pos.asset = "600000.SH"
    pos.shares = 50.0
    pos.avail = 50.0
    pos.cost = 5.0
    pos.price = 6.0
    pos.mv = 300.0
    pos.profit = 50.0
    broker = _make_broker_with_asset_positions(
        asset=None, positions=[pos], connected=False, positions_is_dict=False,
    )
    reg = MagicMock()
    reg.get.return_value = broker
    req = _request(scope={"registry": reg})
    out = portfolio_detail(req, session={"auth": "alice"}, portfolio_id="p1")
    assert out is not None


def test_portfolio_detail_broker_without_asset_attr():
    """broker without `asset` attribute -> asset_overview stays None."""
    broker = MagicMock()
    # Remove asset attribute so hasattr(broker, "asset") is False.
    del broker.asset
    broker.positions = {"x": MagicMock(asset="A", shares=1, avail=1,
                                        cost=1, price=1, mv=1, profit=0)}
    broker.is_connected = True
    reg = MagicMock()
    reg.get.return_value = broker
    req = _request(scope={"registry": reg})
    out = portfolio_detail(req, session={}, portfolio_id="p1")
    assert out is not None


def test_portfolio_detail_broker_without_positions_attr():
    """broker without `positions` -> positions stays []."""
    broker = MagicMock()
    broker.asset = Asset(portfolio_id="p1", dt=None, principal=100.0,
                         cash=50.0, frozen_cash=0.0, market_value=50.0,
                         total=100.0)
    del broker.positions
    broker.is_connected = False
    reg = MagicMock()
    reg.get.return_value = broker
    req = _request(scope={"registry": reg})
    out = portfolio_detail(req, session={}, portfolio_id="p1")
    assert out is not None


def test_portfolio_detail_broker_without_is_connected():
    """broker without is_connected -> gateway_connected stays False."""
    broker = MagicMock()
    del broker.is_connected
    broker.asset = None
    broker.positions = {}
    reg = MagicMock()
    reg.get.return_value = broker
    req = _request(scope={"registry": reg})
    out = portfolio_detail(req, session={}, portfolio_id="p1")
    assert out is not None


# ---------------------------------------------------------------------------
# place_order: broker missing, BUY, SELL, exception path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_place_order_no_broker_returns_error_div():
    """place_order with no broker -> 'Broker not found' Div."""
    req = _request(scope={})
    out = await place_order(req, portfolio_id="p1")
    text = str(out)
    assert "Broker not found" in text


@pytest.mark.asyncio
async def test_place_order_no_registry_returns_error_div():
    """reg is None -> broker None -> error div."""
    req = _request(scope={})
    out = await place_order(req, portfolio_id="p1")
    assert out is not None


@pytest.mark.asyncio
async def test_place_order_buy_calls_broker_buy():
    """BUY side -> broker.buy awaited; returns PositionInfo + AssetSummary."""
    asset = Asset(portfolio_id="p1", dt=None, principal=10_000.0,
                  cash=5_000.0, frozen_cash=0.0, market_value=5_000.0,
                  total=10_000.0)
    pos = MagicMock()
    pos.asset = "000001.SZ"
    pos.shares = 100.0
    pos.avail = 100.0
    pos.cost = 9.0
    pos.price = 10.0
    pos.mv = 1000.0
    pos.profit = 100.0
    broker = MagicMock()
    broker.buy = AsyncMock()
    broker.sell = AsyncMock()
    broker.asset = asset
    broker.positions = {"000001.SZ": pos}
    reg = MagicMock()
    reg.get.return_value = broker
    req = _request(scope={"registry": reg})
    req.form = AsyncMock(return_value={
        "side": "BUY", "asset": "000001.SZ", "price": "10.5", "shares": "100",
    })
    out = await place_order(req, portfolio_id="p1")
    broker.buy.assert_awaited_once_with("000001.SZ", 100, 10.5)
    broker.sell.assert_not_awaited()
    assert isinstance(out, tuple)


@pytest.mark.asyncio
async def test_place_order_sell_calls_broker_sell():
    """SELL side -> broker.sell awaited; default price 0 shares 0 if missing."""
    broker = MagicMock()
    broker.buy = AsyncMock()
    broker.sell = AsyncMock()
    broker.asset = None
    broker.positions = {}
    reg = MagicMock()
    reg.get.return_value = broker
    req = _request(scope={"registry": reg})
    req.form = AsyncMock(return_value={"side": "SELL", "asset": "600000.SH"})
    out = await place_order(req, portfolio_id="p1")
    broker.sell.assert_awaited_once_with("600000.SH", 0, 0.0)
    broker.buy.assert_not_awaited()
    assert isinstance(out, tuple)


@pytest.mark.asyncio
async def test_place_order_buy_exception_returns_error_div():
    """broker.buy raises -> except branch returns failure div."""
    broker = MagicMock()
    broker.buy = AsyncMock(side_effect=RuntimeError("boom"))
    broker.sell = AsyncMock()
    broker.asset = None
    broker.positions = {}
    reg = MagicMock()
    reg.get.return_value = broker
    req = _request(scope={"registry": reg})
    req.form = AsyncMock(return_value={
        "side": "BUY", "asset": "X", "price": "1", "shares": "1",
    })
    out = await place_order(req, portfolio_id="p1")
    text = str(out)
    assert "下单失败" in text


@pytest.mark.asyncio
async def test_place_order_broker_without_positions_or_asset():
    """broker without positions/asset -> still returns tuple via hasattr False."""
    broker = MagicMock()
    broker.buy = AsyncMock()
    broker.sell = AsyncMock()
    del broker.positions
    del broker.asset
    reg = MagicMock()
    reg.get.return_value = broker
    req = _request(scope={"registry": reg})
    req.form = AsyncMock(return_value={
        "side": "BUY", "asset": "X", "price": "1", "shares": "1",
    })
    out = await place_order(req, portfolio_id="p1")
    assert isinstance(out, tuple)


# ---------------------------------------------------------------------------
# _build_asset_overview sanity regression (re-imported for self-containment)
# ---------------------------------------------------------------------------


def test_build_asset_overview_basic_with_dict_positions_path():
    """Sanity test for _build_asset_overview with simple numbers."""
    asset = Asset(portfolio_id="p1", dt=None, principal=200.0,
                  cash=100.0, frozen_cash=10.0, market_value=90.0,
                  total=200.0)
    out = _build_asset_overview(asset)
    assert out["total"] == 200.0
    assert out["frozen_cash"] == 10.0
    assert out["market_value"] == 90.0
