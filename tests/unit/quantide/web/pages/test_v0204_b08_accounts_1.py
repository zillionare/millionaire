"""B08-accounts-1: Test small helpers in accounts.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quantide.core.enums import BrokerKind
from quantide.web.pages import accounts as accounts_mod
from quantide.web.pages.accounts import (
    ConfirmDialogModal,
    CreateSimAccountForm,
    _auto_select_latest_account,
    _get_sim_accounts_list,
)


# ---------------------------------------------------------------------------
# ConfirmDialogModal — pure render
# ---------------------------------------------------------------------------


def test_confirm_dialog_modal_returns():
    out = ConfirmDialogModal(
        dialog_id="del",
        title="Delete",
        message="Sure?",
        confirm_url="/x",
        confirm_method="POST",
    )
    assert out is not None


def test_confirm_dialog_modal_default_method():
    out = ConfirmDialogModal(
        dialog_id="del",
        title="Delete",
        message="Sure?",
        confirm_url="/x",
    )
    assert out is not None


# ---------------------------------------------------------------------------
# CreateSimAccountForm
# ---------------------------------------------------------------------------


def test_create_sim_account_form():
    out = CreateSimAccountForm()
    assert out is not None


# ---------------------------------------------------------------------------
# _auto_select_latest_account
# ---------------------------------------------------------------------------


def test_auto_select_no_registry_returns_none():
    session = {}
    got = _auto_select_latest_account(None, session)
    assert got is None


def test_auto_select_sim_latest():
    """When SIM accounts exist, select the latest."""
    fake_db = MagicMock()
    fake_db.get_portfolio = MagicMock(return_value=MagicMock(start="2024-01-01"))
    accounts_mod.db = fake_db

    reg = MagicMock()
    reg.list_by_kind = MagicMock(return_value=[
        {"id": "sim1", "kind": BrokerKind.SIMULATION.value},
        {"id": "sim2", "kind": BrokerKind.SIMULATION.value},
    ])
    # Make first portfolio newer than second
    fake_db.get_portfolio = MagicMock(side_effect=lambda aid: MagicMock(start="2024-01-01") if aid == "sim1" else MagicMock(start="2024-02-01"))

    session = {}
    got = _auto_select_latest_account(reg, session)
    assert got["id"] == "sim2"
    assert session["active_account_id"] == "sim2"


def test_auto_select_live_when_no_sim():
    """When no sim accounts exist, pick first live."""
    fake_db = MagicMock()
    fake_db.get_portfolio = MagicMock(return_value=None)
    accounts_mod.db = fake_db

    reg = MagicMock()
    reg.list_by_kind = MagicMock(side_effect=lambda kind: [] if kind == BrokerKind.SIMULATION else [{"id": "live1"}])

    session = {}
    got = _auto_select_latest_account(reg, session)
    assert got["id"] == "live1"
    assert session["active_account_id"] == "live1"


def test_auto_select_no_accounts():
    fake_db = MagicMock()
    fake_db.get_portfolio = MagicMock(return_value=None)
    accounts_mod.db = fake_db

    reg = MagicMock()
    reg.list_by_kind = MagicMock(return_value=[])

    session = {}
    got = _auto_select_latest_account(reg, session)
    assert got is None
    assert session["active_account_id"] == ""


# ---------------------------------------------------------------------------
# _get_sim_accounts_list
# ---------------------------------------------------------------------------


def test_get_sim_accounts_list_no_reg():
    out = _get_sim_accounts_list(None)
    assert out is not None


def test_get_sim_accounts_list_no_accounts():
    reg = MagicMock()
    reg.list_by_kind = MagicMock(return_value=[])
    out = _get_sim_accounts_list(reg)
    assert out is not None


def test_get_sim_accounts_list_with_accounts():
    reg = MagicMock()
    reg.list_by_kind = MagicMock(return_value=[
        {"id": "sim1", "name": "S1", "kind": BrokerKind.SIMULATION.value, "status": True},
    ])
    fake_broker = MagicMock()
    fake_broker.principal = 100.0
    fake_broker.total_assets = 120.0
    reg.get = MagicMock(return_value=fake_broker)
    out = _get_sim_accounts_list(reg, active_kind=BrokerKind.SIMULATION.value, active_id="sim1")
    assert out is not None


def test_get_sim_accounts_list_with_accounts_no_broker():
    """When reg.get returns None, principal/total default to 0."""
    reg = MagicMock()
    reg.list_by_kind = MagicMock(return_value=[{"id": "sim1", "kind": "sim"}])
    reg.get = MagicMock(return_value=None)
    out = _get_sim_accounts_list(reg)
    assert out is not None


def test_get_sim_accounts_list_skips_empty_id():
    reg = MagicMock()
    reg.list_by_kind = MagicMock(return_value=[
        {"id": "", "kind": "sim"},
        {"id": "sim1", "kind": "sim", "name": "S1"},
    ])
    reg.get = MagicMock(return_value=None)
    out = _get_sim_accounts_list(reg)
    assert out is not None
