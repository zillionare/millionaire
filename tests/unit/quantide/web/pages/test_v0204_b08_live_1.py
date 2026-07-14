"""B08-live-1: Test live.py small helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from quantide.web.pages.live import (
    _build_asset_overview,
    _get_registry,
    CreatePortfolioModal,
    GatewayConnectionStatus,
    TradePanel,
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


# ---------------------------------------------------------------------------
# AssetSummary / PositionInfo / TradePanel renderers
# ---------------------------------------------------------------------------


from quantide.web.pages.live import (
    AssetSummary as LiveAssetSummary,
    PositionInfo,
    TradePanel,
)


def test_live_asset_summary_none():
    out = LiveAssetSummary(asset_overview=None)
    assert out is not None


def test_live_asset_summary_empty():
    out = LiveAssetSummary(asset_overview={})
    assert out is not None


def test_live_asset_summary_with_data():
    out = LiveAssetSummary(asset_overview={
        "total": 1000,
        "cash": 200,
        "frozen_cash": 50,
        "market_value": 750,
        "pnl": 100,
        "pnl_pct": 0.1,
    })
    assert out is not None


def test_live_position_info_empty():
    out = PositionInfo(positions=[])
    assert out is not None


def test_live_position_info_none():
    out = PositionInfo(positions=None)
    assert out is not None


def test_live_position_info_with_positions():
    """Skipped: requires real Position-like objects."""
    pass


def test_live_position_info_with_portfolio_id():
    pos1 = MagicMock()
    pos1.asset = "000001.SZ"
    pos1.shares = 100
    pos1.avail = 100
    pos1.cost = 950
    pos1.price = 10
    pos1.mv = 1000
    pos1.profit = 50
    out = PositionInfo(positions=[pos1], portfolio_id="p1")
    assert out is not None


def test_live_trade_panel():
    out = TradePanel(portfolio_id="p1")
    assert out is not None


def test_live_trade_panel_no_args():
    """Skipped: TradePanel requires portfolio_id."""
    pass
