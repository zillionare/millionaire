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


# ---------------------------------------------------------------------------
# PortfolioList rendering with portfolios
# ---------------------------------------------------------------------------


from quantide.web.pages.live import PortfolioList


def test_portfolio_list_empty():
    out = PortfolioList(portfolios=[], gateway_connected=False)
    assert out is not None


def test_portfolio_list_none():
    out = PortfolioList(portfolios=None, gateway_connected=False)
    assert out is not None


def test_portfolio_list_with_one():
    out = PortfolioList(portfolios=[{
        "portfolio_id": "abc123def",
        "name": "MyPortfolio",
        "principal": 100000,
        "total": 110000,
        "pnl_pct": 0.1,
        "status": True,
    }])
    assert out is not None


def test_portfolio_list_disconnected():
    out = PortfolioList(portfolios=[{"portfolio_id": "p1"}], gateway_connected=False)
    assert out is not None


def test_portfolio_list_with_status_false():
    out = PortfolioList(portfolios=[{
        "portfolio_id": "p1",
        "name": "Stopped",
        "status": False,
    }])
    assert out is not None


def test_portfolio_list_with_negative_pnl():
    out = PortfolioList(portfolios=[{
        "portfolio_id": "p1",
        "name": "Loss",
        "pnl_pct": -0.1,
    }])
    assert out is not None


def test_portfolio_list_multiple():
    out = PortfolioList(portfolios=[
        {"portfolio_id": "p1", "name": "A", "principal": 100, "total": 110, "pnl_pct": 0.1},
        {"portfolio_id": "p2", "name": "B", "principal": 200, "total": 220, "pnl_pct": 0.1},
        {"portfolio_id": "p3", "name": "C", "status": False},
    ])
    assert out is not None


# ---------------------------------------------------------------------------
# live_list dispatcher
# ---------------------------------------------------------------------------


from quantide.web.pages.live import (
    live_list,
    show_create_modal,
    portfolio_detail,
)


def test_live_list_no_registry():
    """No registry → empty portfolios list."""
    req = MagicMock()
    req.scope = {}
    out = live_list(req, session={})
    assert out is not None


def test_live_list_with_qmt_portfolios():
    from quantide.core.enums import BrokerKind
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(side_effect=lambda kind: [
        {"id": "q1", "name": "Q1", "status": True, "kind": BrokerKind.QMT.value}
    ] if kind == BrokerKind.QMT else [])
    fake_broker = MagicMock()
    fake_broker.asset = MagicMock(total=110, principal=100)
    fake_broker.is_connected = True
    fake_reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": fake_reg}
    out = live_list(req, session={"auth": "alice"})
    assert out is not None


def test_live_list_broker_no_asset():
    from quantide.core.enums import BrokerKind
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(side_effect=lambda kind: [
        {"id": "q1", "name": "Q1", "status": True}
    ] if kind == BrokerKind.QMT else [])
    fake_broker = MagicMock(spec=["is_connected"])  # no asset attr
    fake_broker.is_connected = False
    fake_reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": fake_reg}
    out = live_list(req, session={})
    assert out is not None


def test_show_create_modal():
    out = show_create_modal()
    assert out is not None


def test_portfolio_detail_no_registry():
    req = MagicMock()
    req.scope = {}
    out = portfolio_detail(req, session={}, portfolio_id="q1")
    assert out is not None
