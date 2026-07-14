"""B08-accounts-2: Test LiveAccountCard and SimAccountCard rendering."""

from __future__ import annotations

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
