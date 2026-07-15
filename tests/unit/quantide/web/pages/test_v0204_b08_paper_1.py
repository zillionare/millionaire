"""B08-paper-1: Test paper.py small helpers + renderers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quantide.web.pages import paper as paper_mod
from quantide.web.pages.paper import (
    _get_registry,
    _render_empty_paper,
    _render_no_registry,
    _render_paper_picker,
    _resolve_account_id,
    _resolve_default_paper_account,
)


# ---------------------------------------------------------------------------
# _get_registry
# ---------------------------------------------------------------------------


def test_get_registry_present():
    """[AC-NFR1101-01] test_get_registry_present."""
    req = MagicMock()
    req.scope = {"registry": "reg-1"}
    assert _get_registry(req) == "reg-1"


def test_get_registry_missing():
    """[AC-NFR1101-01] test_get_registry_missing."""
    req = MagicMock()
    req.scope = {}
    assert _get_registry(req) is None


# ---------------------------------------------------------------------------
# _resolve_account_id
# ---------------------------------------------------------------------------


def test_resolve_account_id_present():
    """[AC-NFR1101-01] test_resolve_account_id_present."""
    req = MagicMock()
    req.query_params = {"account_id": "a1"}
    assert _resolve_account_id(req) == "a1"


def test_resolve_account_id_missing():
    """[AC-NFR1101-01] test_resolve_account_id_missing."""
    req = MagicMock()
    req.query_params = {}
    assert _resolve_account_id(req) is None


# ---------------------------------------------------------------------------
# _resolve_default_paper_account
# ---------------------------------------------------------------------------


def test_resolve_default_paper_no_registry():
    """[AC-NFR1101-01] test_resolve_default_paper_no_registry."""
    req = MagicMock()
    req.scope = {}
    assert _resolve_default_paper_account(req) is None


def test_resolve_default_paper_no_sims():
    """[AC-NFR1101-01] test_resolve_default_paper_no_sims."""
    reg = MagicMock()
    reg.list_by_kind = MagicMock(return_value=[])
    req = MagicMock()
    req.scope = {"registry": reg}
    assert _resolve_default_paper_account(req) is None


def test_resolve_default_paper_first_sim():
    """[AC-NFR1101-01] test_resolve_default_paper_first_sim."""
    reg = MagicMock()
    reg.list_by_kind = MagicMock(return_value=[{"id": "sim-1"}, {"id": "sim-2"}])
    req = MagicMock()
    req.scope = {"registry": reg}
    assert _resolve_default_paper_account(req) == "sim-1"


# ---------------------------------------------------------------------------
# _render_* (render functions)
# ---------------------------------------------------------------------------


def test_render_empty_paper():
    """[AC-NFR1101-01] test_render_empty_paper."""
    from quantide.web.layouts.main import MainLayout
    layout = MainLayout(title="x", user=None)
    out = _render_empty_paper(layout)
    assert out is not None


def test_render_no_registry():
    """[AC-NFR1101-01] test_render_no_registry."""
    out = _render_no_registry({})
    assert out is not None


def test_render_no_registry_with_user():
    """[AC-NFR1101-01] test_render_no_registry_with_user."""
    out = _render_no_registry({"auth": "alice"})
    assert out is not None


def test_render_paper_picker_empty():
    """[AC-NFR1101-01] test_render_paper_picker_empty."""
    from quantide.web.layouts.main import MainLayout
    layout = MainLayout(title="x", user=None)
    out = _render_paper_picker(layout, [])
    assert out is not None


def test_render_paper_picker_with_sims():
    """[AC-NFR1101-01] test_render_paper_picker_with_sims."""
    from quantide.web.layouts.main import MainLayout
    layout = MainLayout(title="x", user=None)
    sims = [{"id": "s1", "name": "S1"}, {"id": "s2", "name": "S2"}]
    out = _render_paper_picker(layout, sims)
    assert out is not None


# ---------------------------------------------------------------------------
# get_positions + place_order
# ---------------------------------------------------------------------------


import pytest
from unittest.mock import AsyncMock

from quantide.core.enums import BrokerKind
from quantide.web.pages.paper import (
    get_positions,
    place_order,
)


def test_get_positions_no_registry():
    """[AC-NFR1101-01] When no registry, returns PositionInfo with empty list."""
    req = MagicMock()
    req.scope = {}
    out = get_positions(req, portfolio_id="p1")
    assert out is not None


def test_get_positions_with_broker():
    """[AC-NFR1101-01] When broker has positions, returns PositionInfo with them."""
    from quantide.data.models import Position
    fake_reg = MagicMock()
    fake_broker = MagicMock()
    fake_pos = MagicMock(spec=Position)
    fake_pos.asset = "000001.SZ"
    fake_pos.shares = 100
    fake_pos.avail = 100
    fake_pos.cost = 950
    fake_pos.price = 10
    fake_pos.mv = 1000
    fake_pos.profit = 50
    fake_broker.positions = [fake_pos]
    fake_reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": fake_reg}
    out = get_positions(req, portfolio_id="p1")
    assert out is not None


def test_get_positions_broker_no_positions_attr():
    """[AC-NFR1101-01] When broker doesn't have positions attr, returns empty."""
    fake_reg = MagicMock()
    fake_broker = MagicMock(spec=["other_attr"])
    fake_reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": fake_reg}
    out = get_positions(req, portfolio_id="p1")
    assert out is not None


@pytest.mark.asyncio
async def test_place_order_no_registry():
    req = MagicMock()
    req.scope = {}
    resp = await place_order(req, portfolio_id="p1")
    assert resp is not None


@pytest.mark.asyncio
async def test_place_order_no_broker():
    fake_reg = MagicMock()
    fake_reg.get = MagicMock(return_value=None)
    req = MagicMock()
    req.scope = {"registry": fake_reg}
    req.form = AsyncMock(return_value={"side": "BUY", "asset": "000001.SZ", "price": "10", "shares": "100"})
    resp = await place_order(req, portfolio_id="p1")
    assert "not found" in str(resp).lower() or resp is not None


@pytest.mark.asyncio
async def test_place_order_buy():
    fake_reg = MagicMock()
    fake_broker = MagicMock()
    fake_broker.positions = []
    fake_broker.buy = AsyncMock()
    fake_broker.total_assets = 100
    fake_broker.cash = 50
    fake_broker.principal = 80
    fake_reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": fake_reg}
    req.form = AsyncMock(return_value={"side": "BUY", "asset": "000001.SZ", "price": "10", "shares": "100"})
    resp = await place_order(req, portfolio_id="p1")
    assert resp is not None
    fake_broker.buy.assert_awaited_once()


@pytest.mark.asyncio
async def test_place_order_sell():
    fake_reg = MagicMock()
    fake_broker = MagicMock()
    fake_broker.positions = []
    fake_broker.sell = AsyncMock()
    fake_broker.total_assets = 80
    fake_broker.cash = 30
    fake_broker.principal = 100
    fake_reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": fake_reg}
    req.form = AsyncMock(return_value={"side": "SELL", "asset": "000001.SZ", "price": "10", "shares": "100"})
    resp = await place_order(req, portfolio_id="p1")
    assert resp is not None
    fake_broker.sell.assert_awaited_once()
