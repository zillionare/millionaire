"""Pytest configuration for tests/unit/quantide/web/.

Provides an autouse fixture that initializes the app state in the DB
before each test in this subtree, so the InitCheckMiddleware allows
requests to flow through to the actual page handlers.
"""

from __future__ import annotations

import datetime

import pytest


@pytest.fixture(autouse=True)
def init_app_state_for_web_tests(monkeypatch):
    """Force init_wizard.is_initialized() to return True so the middleware
    passes requests through.

    Also seeds the app_state DB row to fully-initialized to make the
    stub more realistic for any code that reads from db directly.
    """
    from quantide.data.sqlite import db

    # Ensure the DB connection is open. Other test files (service,
    # data, etc.) re-init the DB on tmp paths and may leave it closed,
    # which would break web tests that run later in the session.
    try:
        if not getattr(db, "_initialized", False):
            db.init(":memory:")
        else:
            # Verify the connection is still alive.
            try:
                db.execute("SELECT 1")
            except Exception:
                # Re-init a fresh memory DB if the connection was closed.
                db._initialized = False
                db.init(":memory:")
    except Exception:
        pass

    # Seed the app_state row as fully initialized.
    try:
        from quantide.data.models.app_state import AppState
        state = AppState(
            id=1,
            init_completed=True,
            init_started_at=datetime.datetime(2024, 1, 1),
            init_completed_at=datetime.datetime(2024, 1, 2),
            init_step=10,
            gateway_enabled=False,
            tushare_token="test-token",
        )
        try:
            db["app_state"].upsert(state.to_dict(), pk="id")
        except Exception:
            pass
    except Exception:
        pass

    # Monkeypatch is_initialized to return True.
    try:
        from quantide.service import init_wizard as init_wizard_mod

        monkeypatch.setattr(
            init_wizard_mod.init_wizard, "is_initialized", lambda: True
        )
    except Exception:
        pass

    yield