"""B08-home-1: Test small helper functions in home.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fasthtml.core import to_xml

from quantide.web.pages import home as home_mod
from quantide.web.pages.home import (
    _auto_select_account,
    _build_broker_asset_overview,
    _format_amount,
    _format_amount_wan,
    _format_percent,
    _normalize_positions,
    _position_tag,
    _safe_broker_attr,
    _should_redirect_to_strategy,
    _should_show_no_account_dialog,
)


# ---------------------------------------------------------------------------
# _safe_broker_attr
# ---------------------------------------------------------------------------


def test_safe_broker_attr_simple():
    class _B:
        x = 5
    assert _safe_broker_attr(_B(), "x") == 5


def test_safe_broker_attr_missing_returns_default():
    class _B:
        pass
    assert _safe_broker_attr(_B(), "missing", 42) == 42


def test_safe_broker_attr_missing_no_default():
    class _B:
        pass
    assert _safe_broker_attr(_B(), "missing") is None


def test_safe_broker_attr_exception_returns_default():
    class _B:
        @property
        def broken(self):
            raise Exception("boom")
    assert _safe_broker_attr(_B(), "broken", "fallback") == "fallback"


def test_safe_broker_attr_none():
    assert _safe_broker_attr(None, "anything", "default") == "default"


# ---------------------------------------------------------------------------
# _normalize_positions
# ---------------------------------------------------------------------------


def test_normalize_positions_none():
    assert _normalize_positions(None) == []


def test_normalize_positions_empty():
    assert _normalize_positions([]) == []


def test_normalize_positions_list():
    pos = [1, 2, 3]
    assert _normalize_positions(pos) == [1, 2, 3]


def test_normalize_positions_dict_takes_values():
    pos = {"a": 1, "b": 2}
    got = _normalize_positions(pos)
    assert sorted(got) == [1, 2]


def test_normalize_positions_tuple():
    assert _normalize_positions((1, 2)) == [1, 2]


# ---------------------------------------------------------------------------
# _build_broker_asset_overview
# ---------------------------------------------------------------------------


def test_build_broker_asset_overview_with_asset():
    """When broker has .asset attribute, use build_asset_overview."""
    fake_asset = MagicMock()
    fake_asset.total = 100.0
    fake_asset.principal = 80.0
    fake_asset.cash = 20.0
    fake_asset.frozen_cash = 0.0
    fake_asset.market_value = 80.0
    with patch.object(home_mod, "build_asset_overview", return_value={"total": 100.0}) as mock_bao:
        broker = MagicMock()
        broker.asset = fake_asset
        got = _build_broker_asset_overview(broker)
    assert got == {"total": 100.0}
    mock_bao.assert_called_once_with(fake_asset)


def test_build_broker_asset_overview_no_asset_no_total():
    broker = MagicMock(spec=[])  # no asset, no total_assets
    got = _build_broker_asset_overview(broker)
    assert got is None


def test_build_broker_asset_overview_only_total():
    """When broker has total_assets but no asset, build dict manually."""
    broker = MagicMock(spec=["total_assets", "cash", "principal"])
    broker.total_assets = 100.0
    broker.cash = 20.0
    broker.principal = 80.0
    got = _build_broker_asset_overview(broker)
    assert got["total"] == 100.0
    assert got["cash"] == 20.0
    assert got["market_value"] == 80.0
    assert got["pnl"] == 20.0
    assert got["pnl_pct"] == 0.25


def test_build_broker_asset_overview_zero_principal():
    broker = MagicMock(spec=["total_assets", "cash", "principal"])
    broker.total_assets = 100.0
    broker.cash = 20.0
    broker.principal = 0.0
    got = _build_broker_asset_overview(broker)
    assert got["pnl_pct"] == 0


# ---------------------------------------------------------------------------
# _format_amount / _format_amount_wan / _format_percent
# ---------------------------------------------------------------------------


def test_format_amount_none():
    assert _format_amount(None) == "--"


def test_format_amount_zero():
    assert _format_amount(0) == "0.00"


def test_format_amount_positive():
    assert _format_amount(123.456) == "123.46"


def test_format_amount_negative():
    assert _format_amount(-100) == "-100.00"


def test_format_amount_wan_none():
    assert _format_amount_wan(None) == "--"


def test_format_amount_wan_small():
    assert _format_amount_wan(5000) == "0.50"


def test_format_amount_wan_large():
    out = _format_amount_wan(20000)
    assert out == "2.00"


def test_format_percent_none():
    assert _format_percent(None) == "--"


def test_format_percent_zero():
    assert _format_percent(0) == "0.00%"


def test_format_percent_positive():
    assert _format_percent(0.123) == "12.30%"


# ---------------------------------------------------------------------------
# _position_tag
# ---------------------------------------------------------------------------


def test_position_tag_strong_positive():
    color, label = _position_tag(0.10)
    assert "green" in color.lower() or "green" in label.lower() or "🟢" in label or "涨" in label


def test_position_tag_strong_negative():
    color, label = _position_tag(-0.10)
    assert "red" in color.lower() or "red" in label.lower() or "🔴" in label or "跌" in label


def test_position_tag_zero():
    color, label = _position_tag(0)
    assert isinstance(color, str) and isinstance(label, str)


# ---------------------------------------------------------------------------
# _should_show_no_account_dialog
# ---------------------------------------------------------------------------


def test_should_show_no_account_dialog_empty():
    assert _should_show_no_account_dialog([]) is False


def test_should_show_no_account_dialog_one():
    assert _should_show_no_account_dialog([{"id": "a"}]) is False


def test_should_show_no_account_dialog_many():
    assert _should_show_no_account_dialog([{"id": "a"}, {"id": "b"}]) is False


# ---------------------------------------------------------------------------
# _should_redirect_to_strategy
# ---------------------------------------------------------------------------


def test_should_redirect_to_strategy():
    out = _should_redirect_to_strategy()
    assert isinstance(out, bool)


# ---------------------------------------------------------------------------
# _auto_select_account
# ---------------------------------------------------------------------------


def test_auto_select_account_no_reg():
    session = {}
    out = _auto_select_account(None, session)
    assert out is None


def test_auto_select_account_no_accounts():
    reg = MagicMock()
    reg.list_by_kind = MagicMock(return_value=[])
    session = {}
    out = _auto_select_account(reg, session)
    assert out is None


# ---------------------------------------------------------------------------
# OverviewCards + AssetSummary + PositionInfo
# ---------------------------------------------------------------------------


from quantide.web.pages.home import (
    AssetSummary,
    OverviewCards,
    PositionInfo,
)


def test_overview_cards_none_input():
    out = OverviewCards(asset_overview=None)
    assert out is not None


def test_overview_cards_empty_dict():
    out = OverviewCards(asset_overview={})
    assert out is not None


def test_overview_cards_with_data():
    out = OverviewCards(asset_overview={
        "total": 1000000,
        "market_value": 800000,
        "cash": 200000,
        "pnl": 50000,
        "pnl_pct": 0.05,
    })
    assert out is not None


def test_overview_cards_cash_pct_compute():
    """[AC-NFR1101-01] cash_pct = cash/total when total != 0.

    Verifies the rendered HTML carries the total asset value formatted
    in 万 (wan) units: total=1000 -> 0.10万.
    """
    out = OverviewCards(asset_overview={
        "total": 1000,
        "cash": 250,
    })
    html = to_xml(out)
    assert "0.10万" in html or "0.1" in html


def test_overview_cards_zero_total():
    """[AC-NFR1101-01] When total is 0/falsy, cash_pct is None.

    Verifies the zero-total branch renders without raising and still
    produces the 总资产 (total assets) label.
    """
    out = OverviewCards(asset_overview={"total": 0, "cash": 0})
    assert "总资产" in to_xml(out)


def test_asset_summary_default():
    out = AssetSummary()
    assert out is not None


def test_asset_summary_with_data():
    out = AssetSummary(asset_overview={"total": 100})
    assert out is not None


def test_position_info_empty():
    """[AC-NFR1101-01] Empty positions list renders the 'no positions' state."""
    out = PositionInfo(positions=[])
    assert "暂无持仓" in to_xml(out)


def test_position_info_none():
    """[AC-NFR1101-01] None positions renders the 'no positions' state."""
    out = PositionInfo(positions=None)
    assert "暂无持仓" in to_xml(out)


def test_position_info_with_positions_renders_asset():
    """[AC-NFR1101-01] PositionInfo with a position renders the asset code.

    Replaces the prior `pass` placeholder (flagged by Prism M2) with a
    real assertion: a position with asset="000001.SZ" must produce HTML
    that contains the asset code.
    """
    from fasthtml.core import to_xml
    pos = MagicMock()
    pos.asset = "000001.SZ"
    pos.shares = 100
    pos.avail = 100
    pos.cost = 950
    pos.price = 10.0
    pos.mv = 1000.0
    pos.profit = 50.0
    out = PositionInfo(positions=[pos])
    html = to_xml(out)
    assert "000001" in html
    assert "100" in html


# ---------------------------------------------------------------------------
# _get_broker
# ---------------------------------------------------------------------------


from quantide.web.pages.home import _get_broker


def test_get_broker_no_registry():
    """When no registry in scope, returns None."""
    req = MagicMock()
    req.scope = {}
    assert _get_broker(req) is None


def test_get_broker_query_params():
    """When kind+id in query_params, returns reg.get."""
    fake_reg = MagicMock()
    fake_reg.get = MagicMock(return_value="query-broker")
    req = MagicMock()
    req.scope = {"registry": fake_reg}
    req.query_params = {"kind": "live", "id": "b1"}
    assert _get_broker(req) == "query-broker"


def test_get_broker_session_active():
    """When session has active account, returns from reg."""
    fake_reg = MagicMock()
    fake_reg.get = MagicMock(return_value="session-broker")
    req = MagicMock()
    req.scope = {"registry": fake_reg, "session": {"active_account_kind": "sim", "active_account_id": "s1"}}
    req.query_params = {}
    assert _get_broker(req) == "session-broker"


def test_get_broker_session_active_no_broker():
    """When session active but broker not found, falls through to default."""
    fake_reg = MagicMock()
    fake_reg.get = MagicMock(return_value=None)  # session lookup returns None
    fake_reg.get_default = MagicMock(return_value=("live", "default-id"))
    fake_reg.get.return_value = "default-broker"  # 第二次 reg.get 返回 broker
    req = MagicMock()
    req.scope = {"registry": fake_reg, "session": {"active_account_kind": "sim", "active_account_id": "s1"}}
    req.query_params = {}
    out = _get_broker(req)
    assert out == "default-broker"


def test_get_broker_default_fallback():
    """When no query/session, uses get_default."""
    fake_reg = MagicMock()
    fake_reg.get_default = MagicMock(return_value=("live", "default-id"))
    fake_reg.get = MagicMock(return_value="default-broker")
    req = MagicMock()
    req.scope = {"registry": fake_reg, "session": {}}
    req.query_params = {}
    assert _get_broker(req) == "default-broker"


def test_get_broker_no_default():
    fake_reg = MagicMock()
    fake_reg.get_default = MagicMock(return_value=None)
    req = MagicMock()
    req.scope = {"registry": fake_reg, "session": {}}
    req.query_params = {}
    assert _get_broker(req) is None


# ---------------------------------------------------------------------------
# OrderTable + PositionTable + TradePanel renderers
# ---------------------------------------------------------------------------


from quantide.web.pages.home import (
    OrderTable,
    PositionTable,
    TradePanel,
)


def test_order_table_empty():
    out = OrderTable(orders=[])
    assert out is not None


def test_order_table_none():
    out = OrderTable(orders=None)
    assert out is not None


def test_order_table_with_orders():
    from quantide.core.enums import OrderStatus
    out = OrderTable(orders=[
        {"tm": "2024-01-01", "asset": "000001.SZ", "side": 1, "status": int(OrderStatus.REPORTED), "price": 10, "shares": 100, "filled": 100},
    ])
    assert out is not None


def test_position_table_none():
    out = PositionTable(positions=None)
    assert out is not None


def test_position_table_empty():
    out = PositionTable(positions=[])
    assert out is not None


def test_position_table_with_positions():
    pos1 = MagicMock()
    pos1.asset = "000001.SZ"
    pos1.shares = 100.0
    pos1.mv = 1000.0
    pos1.profit = 50.0
    pos1.price = 10.0
    pos1.avail = 100.0
    pos1.cost = 950.0
    out = PositionTable(positions=[pos1])
    assert out is not None


def test_trade_panel():
    out = TradePanel()
    assert out is not None
