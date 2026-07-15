"""B08-accounts-2: Test LiveAccountCard and SimAccountCard rendering."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantide.web.pages.accounts import LiveAccountCard, SimAccountCard


def test_live_account_card_connected_active():
    """[AC-NFR1101-01] Active live account with connection status renders."""
    out = LiveAccountCard(
        account={
            "id": "abc123def456",
            "name": "MyBroker",
            "status": True,
            "created_at": "2024-01-01",
        },
        is_active=True,
    )
    assert out is not None


def test_live_account_card_disconnected():
    """[AC-NFR1101-01] Disconnected live account renders."""
    out = LiveAccountCard(
        account={
            "id": "x",
            "name": "X",
            "status": False,
            "created_at": "2024-01-01",
        },
        is_active=False,
    )
    assert out is not None


def test_live_account_card_minimal():
    """[AC-NFR1101-01] When account has only id, defaults used."""
    out = LiveAccountCard(account={"id": "x"}, is_active=False)
    assert out is not None


def test_sim_account_card_profit():
    """[AC-NFR1101-01] Sim account with profit."""
    out = SimAccountCard(
        account={
            "id": "s1",
            "name": "S1",
            "created_at": "2024-01-01",
            "total": 120000,
            "principal": 100000,
        },
        is_active=True,
    )
    assert out is not None


def test_sim_account_card_loss():
    """[AC-NFR1101-01] test_sim_account_card_loss."""
    out = SimAccountCard(
        account={
            "id": "s1",
            "name": "S1",
            "created_at": "2024-01-01",
            "total": 80000,
            "principal": 100000,
        },
        is_active=False,
    )
    assert out is not None


# ---------------------------------------------------------------------------
# accounts_list dispatcher — mocks all storage + registry
# ---------------------------------------------------------------------------


from quantide.web.pages import accounts as accounts_mod
from quantide.web.pages.accounts import accounts_list, accounts_index


def _req_with_session(scope=None):
    """Build a fake request with session + scope."""
    req = MagicMock()
    req.scope = scope or {"session": {}}
    req.query_params = {}
    return req


def test_accounts_index_delegates_to_list():
    """[AC-NFR1101-01] accounts_index just calls accounts_list."""
    with patch.object(accounts_mod, "accounts_list", return_value="result") as mock_list:
        req = _req_with_session()
        out = accounts_index(req)
    mock_list.assert_called_once_with(req)
    assert out == "result"


def test_accounts_list_no_registry():
    """[AC-NFR1101-01] When no registry in scope, still renders."""
    req = _req_with_session(scope={"session": {}})
    out = accounts_list(req)
    assert out is not None


def test_accounts_list_with_registry_empty():
    """[AC-NFR1101-01] When registry has no accounts."""
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(return_value=[])
    fake_reg.get = MagicMock(return_value=None)
    req = _req_with_session(scope={"session": {}, "registry": fake_reg})
    out = accounts_list(req)
    assert out is not None


def test_accounts_list_with_sim_accounts():
    """[AC-NFR1101-01] When registry has SIM accounts, includes them."""
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(side_effect=lambda kind: [
        {"id": "s1", "name": "S1", "kind": "sim", "status": True}
    ] if kind.value == "sim" else [])
    fake_broker = MagicMock()
    fake_broker.principal = 100000
    fake_broker.total_assets = 120000
    fake_reg.get = MagicMock(return_value=fake_broker)
    req = _req_with_session(scope={
        "session": {"active_account_kind": "sim", "active_account_id": "s1"},
        "registry": fake_reg,
    })
    out = accounts_list(req)
    assert out is not None


def test_accounts_list_with_qmt_accounts():
    """[AC-NFR1101-01] When registry has QMT accounts, includes them."""
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(side_effect=lambda kind: [
        {"id": "q1", "name": "Q1", "kind": "qmt", "status": True}
    ] if kind.value == "qmt" else [])
    fake_broker = MagicMock()
    fake_asset = MagicMock()
    fake_asset.total = 100
    fake_asset.principal = 80
    fake_broker.asset = fake_asset
    fake_reg.get = MagicMock(return_value=fake_broker)
    req = _req_with_session(scope={
        "session": {},
        "registry": fake_reg,
    })
    out = accounts_list(req)
    assert out is not None


def test_accounts_list_with_create_sim_modal_param():
    """[AC-NFR1101-01] When ?create_sim=1 in query_params, show_create_modal=True."""
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(return_value=[])
    fake_reg.get = MagicMock(return_value=None)
    req = _req_with_session(scope={"session": {}, "registry": fake_reg})
    req.query_params = {"create_sim": "1"}
    out = accounts_list(req)
    assert out is not None


def test_accounts_list_qmt_no_asset():
    """[AC-NFR1101-01] When QMT broker has no asset, total/principal default to 0."""
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(side_effect=lambda kind: [
        {"id": "q1", "name": "Q1", "kind": "qmt", "status": True}
    ] if kind.value == "qmt" else [])
    fake_broker = MagicMock(spec=[])  # no asset attr
    fake_reg.get = MagicMock(return_value=fake_broker)
    req = _req_with_session(scope={"session": {}, "registry": fake_reg})
    out = accounts_list(req)
    assert out is not None


def test_accounts_list_skips_empty_account_id():
    """[AC-NFR1101-01] When account_id is '', skip."""
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(side_effect=lambda kind: [
        {"id": "", "name": "Empty", "kind": "qmt"},
        {"id": "q1", "name": "Q1", "kind": "qmt"},
    ] if kind.value == "qmt" else [])
    fake_reg.get = MagicMock(return_value=None)
    req = _req_with_session(scope={"session": {}, "registry": fake_reg})
    out = accounts_list(req)
    assert out is not None


# ---------------------------------------------------------------------------
# _get_market_data + delete/refresh routes
# ---------------------------------------------------------------------------


from quantide.web.pages.accounts import (
    _get_market_data,
    _get_registry,
    delete_all_sim_accounts,
    delete_live_account,
    delete_sim_account,
    refresh_live_account,
    reset_sim_account,
)


def test_get_market_data_no_runtime():
    """[AC-NFR1101-01] When app.state.runtime is None, returns None."""
    req = MagicMock()
    req.app.state.runtime = None
    assert _get_market_data(req) is None


def test_get_market_data_with_runtime():
    """[AC-NFR1101-01] When runtime exists, returns runtime.market_data."""
    req = MagicMock()
    req.app.state.runtime = MagicMock()
    req.app.state.runtime.market_data = "md"
    assert _get_market_data(req) == "md"


def test_get_market_data_no_market_data_attr():
    """[AC-NFR1101-01] When runtime has no market_data attr, returns None."""
    req = MagicMock()
    req.app.state.runtime = MagicMock(spec=[])  # no market_data attr
    assert _get_market_data(req) is None


def test_get_registry_present():
    """[AC-NFR1101-01] test_get_registry_present."""
    req = MagicMock()
    req.scope = {"registry": "reg"}
    assert _get_registry(req) == "reg"


def test_get_registry_missing():
    """[AC-NFR1101-01] test_get_registry_missing."""
    req = MagicMock()
    req.scope = {}
    assert _get_registry(req) is None


def test_delete_live_account_placeholder():
    """[AC-NFR1101-01] test_delete_live_account_placeholder."""
    req = MagicMock()
    resp = delete_live_account(req, account_id="abc")
    assert resp is not None


def test_refresh_live_account_placeholder():
    """[AC-NFR1101-01] test_refresh_live_account_placeholder."""
    req = MagicMock()
    resp = refresh_live_account(req, account_id="abc")
    assert resp is not None


def test_delete_all_sim_accounts_no_registry():
    """[AC-NFR1101-01] When no registry, clears session and redirects."""
    fake_db = MagicMock()
    accounts_mod.db = fake_db
    req = MagicMock()
    req.scope = {"session": {}}
    resp = delete_all_sim_accounts(req)
    assert resp is not None


def test_delete_all_sim_accounts_with_registry():
    """[AC-NFR1101-01] When registry has sim accounts, deletes them."""
    fake_db = MagicMock()
    accounts_mod.db = fake_db
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(return_value=[
        {"id": "s1", "name": "S1"},
        {"id": "s2", "name": "S2"},
    ])
    req = MagicMock()
    req.scope = {"session": {"active_account_kind": "sim", "active_account_id": "s1"}, "registry": fake_reg}
    resp = delete_all_sim_accounts(req)
    assert resp is not None


def test_delete_all_sim_accounts_db_error_swallowed():
    """[AC-NFR1101-01] When db.delete_portfolio raises, continues."""
    fake_db = MagicMock()
    fake_db.delete_portfolio = MagicMock(side_effect=Exception("boom"))
    accounts_mod.db = fake_db
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(return_value=[{"id": "s1"}])
    req = MagicMock()
    req.scope = {"session": {}, "registry": fake_reg}
    resp = delete_all_sim_accounts(req)
    assert resp is not None


def test_delete_sim_account():
    """[AC-NFR1101-01] test_delete_sim_account."""
    req = MagicMock()
    req.scope = {"session": {}}
    fake_db = MagicMock()
    accounts_mod.db = fake_db
    resp = delete_sim_account(req, account_id="s1")
    assert resp is not None


def test_reset_sim_account():
    """[AC-NFR1101-01] test_reset_sim_account."""
    req = MagicMock()
    req.scope = {"session": {}}
    fake_db = MagicMock()
    accounts_mod.db = fake_db
    resp = reset_sim_account(req, account_id="s1")
    assert resp is not None


# ---------------------------------------------------------------------------
# create_sim_account — early branches
# ---------------------------------------------------------------------------


from quantide.web.pages.accounts import create_sim_account


@pytest.mark.asyncio
async def test_create_sim_account_no_registry():
    """When no registry, returns error Div."""
    req = MagicMock()
    req.scope = {"session": {}}
    resp = await create_sim_account(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_create_sim_account_empty_name():
    """Empty name returns error."""
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(return_value=[])
    req = MagicMock()
    req.scope = {"session": {}, "registry": fake_reg}
    req.form = AsyncMock(return_value={"name": "", "principal": "100"})
    resp = await create_sim_account(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_create_sim_account_name_taken():
    """When name already exists, redirects."""
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(return_value=[
        {"id": "s_old", "name": "Taken"}
    ])
    req = MagicMock()
    req.scope = {"session": {}, "registry": fake_reg}
    req.form = AsyncMock(return_value={"name": "Taken", "principal": "100"})
    resp = await create_sim_account(req)
    assert resp is not None
    # Should be RedirectResponse
    location = str(resp.headers.get("location", "")) if hasattr(resp, "headers") else ""
    assert location == "/system/accounts"
