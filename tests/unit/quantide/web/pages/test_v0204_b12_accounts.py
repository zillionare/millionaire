"""B12-accounts: Cover specific missing lines in accounts.py routes.

Targets previously uncovered branches:
- accounts_list: sim account with empty id (line 332)
- delete_sim_account: registry unregister + db error + active-account auto-select (lines 465-476)
- reset_sim_account: broker.reset() path (lines 489-492)
- create_sim_account: success path with no runtime (lines 604-643)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantide.core.enums import BrokerKind
from quantide.web.pages import accounts as accounts_mod
from quantide.web.pages.accounts import (
    accounts_list,
    create_sim_account,
    delete_sim_account,
    reset_sim_account,
)


def _req_with_session(scope=None):
    """Build a fake request with session + scope."""
    req = MagicMock()
    req.scope = scope or {"session": {}}
    req.query_params = {}
    return req


# ---------------------------------------------------------------------------
# Line 332: accounts_list skips sim account whose id is empty
# ---------------------------------------------------------------------------


def test_accounts_list_skips_empty_sim_account_id():
    """[AC-NFR1101-01] Sim account with empty id is skipped (line 332 `continue`).

    A sim entry with id="" must be skipped while a valid sibling entry is
    still rendered. We assert the broker lookup is never attempted for the
    empty-id entry and the page still renders.
    """
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(
        side_effect=lambda kind: [
            {"id": "", "name": "Empty", "kind": "sim"},
            {"id": "s1", "name": "S1", "kind": "sim", "status": True},
        ]
        if kind.value == "sim"
        else []
    )
    fake_reg.get = MagicMock(return_value=None)
    req = _req_with_session(scope={"session": {}, "registry": fake_reg})

    out = accounts_list(req)

    assert out is not None
    # reg.get should be called exactly once (for "s1"), never for "".
    called_ids = [call.args[1] for call in fake_reg.get.call_args_list]
    assert called_ids == ["s1"]


# ---------------------------------------------------------------------------
# Lines 465, 466, 471, 472: delete_sim_account with registry + db failure
# ---------------------------------------------------------------------------


def test_delete_sim_account_with_registry_and_db_error():
    """[AC-NFR1101-01] delete_sim_account unregisters then swallows db error.

    Covers:
      - 465: reg.unregister(...) called when registry present
      - 466: logger.info after unregister
      - 471-472: except branch printing when db.delete_portfolio raises
    """
    fake_reg = MagicMock()
    fake_db = MagicMock()
    fake_db.delete_portfolio = MagicMock(side_effect=RuntimeError("db down"))
    accounts_mod.db = fake_db

    req = MagicMock()
    req.scope = {"session": {}, "registry": fake_reg}

    resp = delete_sim_account(req, account_id="s1")

    # registry unregister invoked with correct kind + id
    fake_reg.unregister.assert_called_once_with(BrokerKind.SIMULATION, "s1")
    # db delete attempted
    fake_db.delete_portfolio.assert_called_once_with("s1")
    # redirect returned despite db error
    assert resp.status_code == 303
    assert resp.headers["location"] == "/system/accounts"


# ---------------------------------------------------------------------------
# Line 476: delete_sim_account auto-selects latest when active account deleted
# ---------------------------------------------------------------------------


def test_delete_sim_account_active_account_triggers_auto_select():
    """[AC-NFR1101-01] Deleting the active sim account triggers auto-select (line 476).

    When active_kind == SIMULATION and active_id matches the deleted account,
    _auto_select_latest_account must be invoked with the registry + session.
    """
    fake_reg = MagicMock()
    fake_db = MagicMock()
    accounts_mod.db = fake_db

    session = {
        "active_account_kind": BrokerKind.SIMULATION.value,
        "active_account_id": "s1",
    }
    req = MagicMock()
    req.scope = {"session": session, "registry": fake_reg}

    with patch.object(accounts_mod, "_auto_select_latest_account") as mock_auto:
        resp = delete_sim_account(req, account_id="s1")

    mock_auto.assert_called_once_with(fake_reg, session)
    assert resp.status_code == 303


# ---------------------------------------------------------------------------
# Lines 489, 490, 491, 492: reset_sim_account calls broker.reset()
# ---------------------------------------------------------------------------


def test_reset_sim_account_calls_broker_reset():
    """[AC-NFR1101-01] reset_sim_account invokes broker.reset() when available.

    Covers:
      - 489: broker = reg.get(SIMULATION, account_id)
      - 490: broker truthy and hasattr(broker, "reset")
      - 491: broker.reset() invocation
      - 492: logger.info after reset
    """
    fake_reg = MagicMock()
    fake_broker = MagicMock()
    fake_broker.reset = MagicMock()
    fake_reg.get = MagicMock(return_value=fake_broker)

    req = MagicMock()
    req.scope = {"session": {}, "registry": fake_reg}

    resp = reset_sim_account(req, account_id="s1")

    fake_reg.get.assert_called_once_with(BrokerKind.SIMULATION, "s1")
    fake_broker.reset.assert_called_once()
    assert resp.status_code == 303
    assert resp.headers["location"] == "/system/accounts"


# ---------------------------------------------------------------------------
# Lines 604, 605, 610, 612, 613, 615, 621, 622, 635, 638, 639, 640, 643:
# create_sim_account success path (no runtime -> else branch registers directly)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_sim_account_success_no_runtime():
    """[AC-NFR1101-01] create_sim_account success path with runtime=None.

    Covers the full happy-path when app.state.runtime is None:
      - 604-605: principal parsing (valid float)
      - 610: account_id generation
      - 612-615: PaperBroker.create invocation
      - 621-622: runtime check (None -> else branch)
      - 635: reg.register direct call
      - 638-640: session active-account assignment
      - 643: redirect on success
    """
    fake_reg = MagicMock()
    fake_reg.list_by_kind = MagicMock(return_value=[])
    fake_db = MagicMock()
    fake_db.get_portfolio = MagicMock(return_value=None)
    accounts_mod.db = fake_db

    fake_broker = MagicMock()

    session = {}
    req = MagicMock()
    req.scope = {"session": session, "registry": fake_reg}
    req.app.state.runtime = None
    req.form = AsyncMock(return_value={"name": "NewAcct", "principal": "100"})

    with patch.object(accounts_mod, "PaperBroker") as MockPaper:
        MockPaper.create = MagicMock(return_value=fake_broker)
        resp = await create_sim_account(req)

    # PaperBroker.create called with parsed principal (100 * 10000 = 1_000_000)
    create_kwargs = MockPaper.create.call_args.kwargs
    assert create_kwargs["portfolio_name"] == "NewAcct"
    assert create_kwargs["principal"] == 1_000_000.0
    assert create_kwargs["market_data"] is None

    # registry.register invoked directly (else branch, line 635)
    reg_args = fake_reg.register.call_args.args
    assert reg_args[0] == BrokerKind.SIMULATION
    assert reg_args[1].startswith("sim_")
    assert reg_args[2] is fake_broker

    # session updated to the new account
    assert session["active_account_kind"] == BrokerKind.SIMULATION.value
    assert session["active_account_id"] == reg_args[1]

    # success redirect
    assert resp.status_code == 303
    assert resp.headers["location"] == "/system/accounts"
