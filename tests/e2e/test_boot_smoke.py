"""FR-0101 AC-1 implicit: app boots and /login renders.

E2E contract (M-E2E Stage 2, v0.2-003-coverage):

* The application factory `quantide.app_factory.create_app` returns a
  bootable Starlette/FastHTML app from an isolated ``app_config_dir``.
* The redirect route ``/login`` is registered and returns ``200`` (it
  responds with a redirect target or directly renders a login fragment).

This test does NOT depend on any prior conftest fixtures so that it
runs even if the broader e2e support stack is missing.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from starlette.testclient import TestClient

from quantide.app_factory import create_app


def test_app_boot_and_login_page_returns_200() -> None:
    """FR-0101: pytest config + app boot + /login page renders."""
    with TemporaryDirectory() as tmp:
        app = create_app(app_config_dir=Path(tmp), enforce_single_instance=False)
        client = TestClient(app)
        r = client.get("/login", follow_redirects=True)
        assert r.status_code == 200
        body = r.text.lower()
        assert "login" in body or "登录" in r.text or "init" in body or "wizard" in body