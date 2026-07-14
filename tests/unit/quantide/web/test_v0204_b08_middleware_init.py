"""B08-middleware-init-1: Tests for quantide/web/middleware_init.py.

Target: raise coverage from 42% to >=80%.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantide.web.middleware_init import InitCheckMiddleware, check_init_redirect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(path: str = "/", method: str = "GET", query: dict | None = None):
    req = MagicMock()
    req.url.path = path
    req.method = method
    req.query_params = query or {}
    return req


@pytest.fixture
def patched_init_wizard():
    """Patch init_wizard singleton to control is_initialized behavior."""
    from quantide.web import middleware_init as mi
    original_get = mi.init_wizard.is_initialized
    yield mi.init_wizard
    mi.init_wizard.is_initialized = original_get


@pytest.mark.asyncio
async def test_init_middleware_passes_through_allowed_path(patched_init_wizard):
    """ALLOWED_PATHS are passed through regardless of init state."""
    patched_init_wizard.is_initialized = lambda: False
    middleware = InitCheckMiddleware(app=MagicMock())
    req = _make_request("/static/foo.css")
    call_next = AsyncMock(return_value="OK")
    out = await middleware.dispatch(req, call_next)
    assert out == "OK"
    call_next.assert_awaited_once()


@pytest.mark.asyncio
async def test_init_middleware_uninitialized_get_redirects(patched_init_wizard):
    """Uninitialized app + GET non-allowed path → redirect to /init-wizard."""
    patched_init_wizard.is_initialized = lambda: False
    middleware = InitCheckMiddleware(app=MagicMock())
    req = _make_request("/home", method="GET")
    call_next = AsyncMock()
    out = await middleware.dispatch(req, call_next)
    assert "init-wizard" in str(out.headers.get("location", ""))


@pytest.mark.asyncio
async def test_init_middleware_uninitialized_post_returns_503(patched_init_wizard):
    """Uninitialized app + POST → 503 JSON error."""
    patched_init_wizard.is_initialized = lambda: False
    middleware = InitCheckMiddleware(app=MagicMock())
    req = _make_request("/home", method="POST")
    call_next = AsyncMock()
    out = await middleware.dispatch(req, call_next)
    assert out.status_code == 503


@pytest.mark.asyncio
async def test_init_middleware_initialized_passes_through(patched_init_wizard):
    """Initialized app + non-allowed path → call_next."""
    patched_init_wizard.is_initialized = lambda: True
    middleware = InitCheckMiddleware(app=MagicMock())
    req = _make_request("/home", method="GET")
    call_next = AsyncMock(return_value="OK")
    out = await middleware.dispatch(req, call_next)
    assert out == "OK"


@pytest.mark.asyncio
async def test_init_middleware_initialized_get_redirects_for_init_wizard(patched_init_wizard):
    """Initialized + /init-wizard GET → redirect to / (302)."""
    patched_init_wizard.is_initialized = lambda: True
    middleware = InitCheckMiddleware(app=MagicMock())
    req = _make_request("/init-wizard", method="GET")
    call_next = AsyncMock()
    out = await middleware.dispatch(req, call_next)
    assert out.status_code == 302


@pytest.mark.asyncio
async def test_init_middleware_init_wizard_complete_path_passes(patched_init_wizard):
    """/init-wizard/complete is exempt from the redirect."""
    patched_init_wizard.is_initialized = lambda: True
    middleware = InitCheckMiddleware(app=MagicMock())
    req = _make_request("/init-wizard/complete", method="GET")
    call_next = AsyncMock(return_value="OK")
    out = await middleware.dispatch(req, call_next)
    assert out == "OK"


@pytest.mark.asyncio
async def test_init_middleware_init_wizard_with_force(patched_init_wizard):
    """force=true query param bypasses redirect."""
    patched_init_wizard.is_initialized = lambda: True
    middleware = InitCheckMiddleware(app=MagicMock())
    req = _make_request("/init-wizard", method="GET", query={"force": "true"})
    call_next = AsyncMock(return_value="OK")
    out = await middleware.dispatch(req, call_next)
    assert out == "OK"


@pytest.mark.asyncio
async def test_init_middleware_init_wizard_post_returns_403(patched_init_wizard):
    """Initialized + /init-wizard POST → 403 JSON."""
    patched_init_wizard.is_initialized = lambda: True
    middleware = InitCheckMiddleware(app=MagicMock())
    req = _make_request("/init-wizard", method="POST")
    call_next = AsyncMock()
    out = await middleware.dispatch(req, call_next)
    assert out.status_code == 403


@pytest.mark.asyncio
async def test_init_middleware_handles_is_initialized_exception(patched_init_wizard):
    """When is_initialized raises, treat as uninitialized (allows continued access)."""
    def _boom():
        raise RuntimeError("db error")
    patched_init_wizard.is_initialized = _boom
    middleware = InitCheckMiddleware(app=MagicMock())
    req = _make_request("/home", method="GET")
    call_next = AsyncMock(return_value="OK")
    out = await middleware.dispatch(req, call_next)
    # Because initialized=False (exception), it should redirect.
    assert out.status_code == 302


# ---------------------------------------------------------------------------
# check_init_redirect
# ---------------------------------------------------------------------------


def test_check_init_redirect_uninitialized(patched_init_wizard):
    """Returns RedirectResponse when not initialized."""
    patched_init_wizard.is_initialized = lambda: False
    out = check_init_redirect()
    assert out is not None


def test_check_init_redirect_initialized(patched_init_wizard):
    """Returns None when initialized."""
    patched_init_wizard.is_initialized = lambda: True
    assert check_init_redirect() is None


def test_check_init_redirect_handles_exception(patched_init_wizard):
    """When is_initialized raises, returns None (no redirect)."""
    def _boom():
        raise RuntimeError("err")
    patched_init_wizard.is_initialized = _boom
    assert check_init_redirect() is None
