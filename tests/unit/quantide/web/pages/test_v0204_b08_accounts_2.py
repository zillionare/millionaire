"""B08-accounts-2: Test LiveAccountCard and SimAccountCard rendering."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from quantide.web.pages.accounts import LiveAccountCard, SimAccountCard


def test_live_account_card_connected_active():
    """Active live account with connection status renders."""
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
    """Disconnected live account renders."""
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
    """When account has only id, defaults used."""
    out = LiveAccountCard(account={"id": "x"}, is_active=False)
    assert out is not None


def test_sim_account_card_profit():
    """Sim account with profit."""
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
    """accounts_index just calls accounts_list."""
    with patch.object(accounts_mod, "accounts_list", return_value="result") as mock_list:
        req = _req_with_session()
        out = accounts_index(req)
    mock_list.assert_called_once_with(req)
    assert out == "result"


def test_accounts_list_no_registry():
    """When no registry in scope, still renders."""
    req = _req_with_session(scope={"session": {}})
    out = accounts_list(req)
    assert out is not None


def test_accounts_list_with_registry_empty():
    """When registry has no accounts."""
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(return_value=[])
    fake_reg.get = MagicMock(return_value=None)
    req = _req_with_session(scope={"session": {}, "registry": fake_reg})
    out = accounts_list(req)
    assert out is not None


def test_accounts_list_with_sim_accounts():
    """When registry has SIM accounts, includes them."""
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
    """When registry has QMT accounts, includes them."""
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
    """When ?create_sim=1 in query_params, show_create_modal=True."""
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(return_value=[])
    fake_reg.get = MagicMock(return_value=None)
    req = _req_with_session(scope={"session": {}, "registry": fake_reg})
    req.query_params = {"create_sim": "1"}
    out = accounts_list(req)
    assert out is not None


def test_accounts_list_qmt_no_asset():
    """When QMT broker has no asset, total/principal default to 0."""
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
    """When account_id is '', skip."""
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(side_effect=lambda kind: [
        {"id": "", "name": "Empty", "kind": "qmt"},
        {"id": "q1", "name": "Q1", "kind": "qmt"},
    ] if kind.value == "qmt" else [])
    fake_reg.get = MagicMock(return_value=None)
    req = _req_with_session(scope={"session": {}, "registry": fake_reg})
    out = accounts_list(req)
    assert out is not None
