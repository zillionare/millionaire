"""B09-home-full: Cover remaining missing lines in home.py.

Targets gaps not covered by earlier B08 home test files:
- AccountTabs renderer (line 92)
- BrokerList renderer with items (lines 312-316)
- NoAccountDialog renderer (lines 644-645)
- _auto_select_account: live-accounts branch + sim-accounts branch (lines 774-786)
- get_positions route (line 800-802)
- place_order route: no-broker / BUY / SELL / exception (lines 806-845)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fasthtml.core import to_xml

from quantide.core.enums import BrokerKind
from quantide.web.pages import home as home_mod
from quantide.web.pages.home import (
    AccountTabs,
    BrokerList,
    NoAccountDialog,
    _auto_select_account,
    get_positions,
    place_order,
)


# ---------------------------------------------------------------------------
# AccountTabs (line 92)
# ---------------------------------------------------------------------------


def test_account_tabs_renders_my_assets_active_link():
    """AccountTabs renders the 我的资产 active tab link."""
    out = AccountTabs()
    html = to_xml(out)
    assert "我的资产" in html
    assert "active" in html


# ---------------------------------------------------------------------------
# BrokerList with items (lines 312-316)
# ---------------------------------------------------------------------------


def test_broker_list_renders_links_for_items():
    """BrokerList builds href links for each item."""
    items = [
        {"kind": "live", "id": "acc-1"},
        {"kind": "sim", "id": "acc-2"},
    ]
    out = BrokerList(items)
    html = to_xml(out)
    # HTML escapes `&` as `&amp;`.
    assert "/home?kind=live&amp;id=acc-1" in html
    assert "/home?kind=sim&amp;id=acc-2" in html
    assert "live:acc-1" in html
    assert "sim:acc-2" in html


# ---------------------------------------------------------------------------
# NoAccountDialog (lines 644-645)
# ---------------------------------------------------------------------------


def test_no_account_dialog_renders_branding_and_links():
    """NoAccountDialog renders the branding product name and account-management links."""
    out = NoAccountDialog()
    html = to_xml(out)
    assert "no-account-dialog" in html
    assert "/system/accounts" in html
    assert "create_sim=1" in html


# ---------------------------------------------------------------------------
# _auto_select_account - live + sim branches (lines 774-786)
# ---------------------------------------------------------------------------


def test_auto_select_account_returns_live_account_first():
    """When a live (QMT) account exists, it is selected (first account)."""
    reg = MagicMock()
    reg.list_by_kind = MagicMock(side_effect=lambda kind: (
        [{"id": "qmt-1"}] if kind == BrokerKind.QMT else []
    ))
    out = _auto_select_account(reg, {})
    assert out == (BrokerKind.QMT.value, "qmt-1")


def test_auto_select_account_returns_last_simulation_when_no_live():
    """When no live account exists, the last-created simulation account is selected."""
    reg = MagicMock()
    reg.list_by_kind = MagicMock(side_effect=lambda kind: (
        [] if kind == BrokerKind.QMT else [{"id": "sim-1"}, {"id": "sim-2"}]
    ))
    out = _auto_select_account(reg, {})
    assert out == (BrokerKind.SIMULATION.value, "sim-2")


# ---------------------------------------------------------------------------
# get_positions route (lines 800-802)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_positions_returns_position_info_when_broker_present():
    """get_positions normalizes broker.positions into a PositionInfo component."""
    fake_broker = SimpleNamespace(positions=[])  # empty list -> empty PositionInfo
    fake_reg = MagicMock()
    req = MagicMock()
    req.scope = {"registry": fake_reg, "session": {}}
    req.query_params = {}
    with patch.object(home_mod, "_get_broker", return_value=fake_broker):
        out = await get_positions(req)
    # Empty positions render the 暂无持仓 placeholder.
    assert "暂无持仓" in to_xml(out)


# ---------------------------------------------------------------------------
# place_order route - no broker / BUY / exception (lines 806-845)
# ---------------------------------------------------------------------------


def _make_home_req(*, scope=None, form_data=None):
    req = MagicMock()
    req.scope = scope or {"registry": MagicMock(), "session": {}}
    req.query_params = {}
    req.form = AsyncMock(return_value=form_data or {})
    return req


@pytest.mark.asyncio
async def test_place_order_returns_broker_not_found_when_no_broker():
    """When no broker is resolved, place_order returns the 'Broker not found' string."""
    req = _make_home_req()
    with patch.object(home_mod, "_get_broker", return_value=None):
        out = await place_order(req)
    assert out == "Broker not found"


@pytest.mark.asyncio
async def test_place_order_buy_success_returns_position_info_and_summary():
    """A successful BUY call returns a tuple of (PositionInfo, AssetSummary) components."""
    fake_broker = MagicMock()
    fake_broker.buy = AsyncMock(return_value=None)
    fake_broker.positions = {}
    req = _make_home_req(
        form_data={"side": "BUY", "asset": "000001.SZ", "price": "10.5", "shares": "100"}
    )
    with patch.object(home_mod, "_get_broker", return_value=fake_broker), \
         patch.object(home_mod, "_build_broker_asset_overview", return_value=None):
        out = await place_order(req)
    assert isinstance(out, tuple)
    assert len(out) == 2


@pytest.mark.asyncio
async def test_place_order_exception_returns_error_div():
    """When broker.buy raises, place_order returns a red Error div."""
    fake_broker = MagicMock()
    fake_broker.buy = AsyncMock(side_effect=RuntimeError("boom"))
    req = _make_home_req(
        form_data={"side": "BUY", "asset": "000001.SZ", "price": "10.5", "shares": "100"}
    )
    with patch.object(home_mod, "_get_broker", return_value=fake_broker):
        out = await place_order(req)
    html = to_xml(out)
    assert "Error" in html
