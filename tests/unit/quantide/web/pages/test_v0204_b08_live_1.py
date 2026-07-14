"""B08-live-1: Test live.py small helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from quantide.web.pages.live import (
    _build_asset_overview,
    _get_registry,
    CreatePortfolioModal,
    GatewayConnectionStatus,
)


def test_get_registry_present():
    req = MagicMock()
    req.scope = {"registry": "reg-1"}
    assert _get_registry(req) == "reg-1"


def test_get_registry_missing():
    req = MagicMock()
    req.scope = {}
    assert _get_registry(req) is None


def test_build_asset_overview_none():
    got = _build_asset_overview(None)
    assert got["total"] == 0
    assert got["pnl"] == 0


def test_build_asset_overview_with_asset():
    asset = MagicMock()
    asset.total = 110.0
    asset.principal = 100.0
    asset.cash = 10.0
    asset.frozen_cash = 0.0
    asset.market_value = 100.0
    got = _build_asset_overview(asset)
    assert got["total"] == 110.0
    assert got["pnl"] == 10.0
    assert got["pnl_pct"] == 0.1


def test_build_asset_overview_zero_principal():
    asset = MagicMock()
    asset.total = 100.0
    asset.principal = 0.0
    asset.cash = 0.0
    asset.frozen_cash = 0.0
    asset.market_value = 0.0
    got = _build_asset_overview(asset)
    assert got["pnl_pct"] == 0.0


def test_build_asset_overview_loss():
    asset = MagicMock()
    asset.total = 90.0
    asset.principal = 100.0
    asset.cash = 5.0
    asset.frozen_cash = 0.0
    asset.market_value = 85.0
    got = _build_asset_overview(asset)
    assert got["pnl"] == -10.0
    assert got["pnl_pct"] == -0.1


def test_gateway_connection_status_connected():
    out = GatewayConnectionStatus(connected=True)
    assert out is not None


def test_gateway_connection_status_disconnected():
    out = GatewayConnectionStatus(connected=False)
    assert out is not None


def test_create_portfolio_modal():
    out = CreatePortfolioModal()
    assert out is not None
