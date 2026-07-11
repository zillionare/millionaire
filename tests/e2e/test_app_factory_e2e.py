"""FR-0703: create_app honors tmp_path + enforce_single_instance=False; routes register.

E2E contract (M-E2E Stage 2, v0.2-003-coverage):

* Two ``create_app`` invocations in two distinct ``app_config_dir`` values
  must not collide (no PID file / no SQLite lock contention).
* ``/login`` is registered as a route (the public, spec-visible contract).
* Routes list is non-empty for an initialized config dir.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from quantide.app_factory import create_app


def test_create_app_isolated_config_dirs() -> None:
    """AC-FR0703-03 / AC-FR0703-04: two apps in two tmp dirs coexist without PID collision."""
    with TemporaryDirectory() as tmp:
        app_a = create_app(app_config_dir=Path(tmp) / "a", enforce_single_instance=False)
        app_b = create_app(app_config_dir=Path(tmp) / "b", enforce_single_instance=False)
        assert app_a is not app_b
        assert len(app_a.routes) > 0
        assert len(app_b.routes) > 0


def test_create_app_registers_login_route() -> None:
    """AC-FR0703-05: /login route is registered on the app instance."""
    with TemporaryDirectory() as tmp:
        app = create_app(app_config_dir=Path(tmp), enforce_single_instance=False)
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/login" in paths