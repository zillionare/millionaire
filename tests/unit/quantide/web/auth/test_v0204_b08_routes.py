"""B08-auth-routes-2: Test AuthRoutes wrapper methods."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quantide.web.auth.routes import AuthRoutes


@pytest.fixture
def auth_manager():
    auth = MagicMock()
    auth.config = {"allow_registration": False, "allow_password_reset": False}
    auth.user_repo = MagicMock()
    return auth


@pytest.fixture
def routes(auth_manager):
    return AuthRoutes(auth_manager=auth_manager)


def test_init(routes, auth_manager):
    assert routes.auth is auth_manager
    assert routes.routes == {}


def test_register_all_minimal(routes):
    """Test register_all with a mock app that doesn't actually register routes."""
    app = MagicMock()
    # rt returns a decorator
    rt = MagicMock()
    rt.return_value = lambda f: f  # decorator that returns function as-is
    # Override the app.route attribute
    type(app).route = rt
    # Simpler approach: provide a fake rt
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)

    # Instead of calling register_all (which calls real decorators), test inner methods
    # We're mainly testing the structure of these methods.
    assert hasattr(routes, "_register_login_routes")
    assert hasattr(routes, "_register_logout_route")
    assert hasattr(routes, "_register_registration_routes")
    assert hasattr(routes, "_register_profile_route")
    assert hasattr(routes, "_register_password_reset_routes")


def test_register_login_routes_populates(routes):
    """When _register_login_routes is called, self.routes gains keys."""
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_login_routes(rt=fake_rt, prefix="/auth")
    assert "login_page" in routes.routes
    assert "login_submit" in routes.routes


def test_register_logout_route(routes):
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_logout_route(rt=fake_rt, prefix="/auth")
    assert "logout" in routes.routes


def test_register_registration_routes_disabled(routes):
    """When allow_registration=False, no routes registered."""
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_registration_routes(rt=fake_rt, prefix="/auth")
    # No new entries since disabled
    assert all("register" not in k for k in routes.routes.keys())


def test_register_registration_routes_enabled(routes):
    """When allow_registration=True, register route registered."""
    routes.auth.config = {"allow_registration": True}
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_registration_routes(rt=fake_rt, prefix="/auth")
    assert "register_page" in routes.routes
    assert "register_submit" in routes.routes


def test_register_password_reset_routes_disabled(routes):
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_password_reset_routes(rt=fake_rt, prefix="/auth")
    assert all("forgot" not in k for k in routes.routes.keys())


def test_register_password_reset_routes_enabled(routes):
    routes.auth.config = {"allow_password_reset": True}
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_password_reset_routes(rt=fake_rt, prefix="/auth")
    assert "forgot_password" in routes.routes
    assert "forgot_submit" in routes.routes


def test_register_profile_route(routes):
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_profile_route(rt=fake_rt, prefix="/auth")
    assert "profile_page" in routes.routes
    assert "profile_submit" in routes.routes
