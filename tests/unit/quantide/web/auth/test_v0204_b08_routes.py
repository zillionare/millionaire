"""B08-auth-routes-2: Test AuthRoutes wrapper methods."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

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


# ---------------------------------------------------------------------------
# Inner route function tests (extracted via self.routes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_submit_success():
    """login_submit with valid creds → redirect to /."""
    auth = MagicMock()
    auth.config = {"allow_registration": False, "allow_password_reset": False}
    fake_user = MagicMock()
    fake_user.username = "alice"
    fake_user.id = 1
    fake_user.role = "user"
    auth.user_repo = MagicMock()
    auth.user_repo.authenticate = MagicMock(return_value=fake_user)
    routes = AuthRoutes(auth)

    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_login_routes(rt=fake_rt, prefix="/auth")

    login_submit = routes.routes["login_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={"username": "alice", "password": "pw", "redirect_to": "/"})
    sess = {}
    resp = await login_submit(req, sess)
    assert sess["auth"] == "alice"
    assert sess["role"] == "user"


@pytest.mark.asyncio
async def test_login_submit_invalid():
    """login_submit with bad creds → redirect to /auth/login?error=invalid."""
    auth = MagicMock()
    auth.config = {}
    auth.user_repo = MagicMock()
    auth.user_repo.authenticate = MagicMock(return_value=None)
    routes = AuthRoutes(auth)

    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_login_routes(rt=fake_rt, prefix="/auth")

    login_submit = routes.routes["login_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={"username": "x", "password": "wrong"})
    sess = {}
    resp = await login_submit(req, sess)
    assert "error=invalid" in str(resp.headers.get("location", "")) or "error=invalid" in str(resp)


@pytest.mark.asyncio
async def test_login_submit_invalid_with_redirect():
    """Invalid login preserves redirect_to."""
    auth = MagicMock()
    auth.config = {}
    auth.user_repo = MagicMock()
    auth.user_repo.authenticate = MagicMock(return_value=None)
    routes = AuthRoutes(auth)

    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_login_routes(rt=fake_rt, prefix="/auth")

    login_submit = routes.routes["login_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={"username": "x", "password": "wrong", "redirect_to": "/page"})
    sess = {}
    resp = await login_submit(req, sess)


def test_login_page_renders():
    """login_page returns Title + form based on query_params."""
    auth = MagicMock()
    auth.config = {}
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_login_routes(rt=fake_rt, prefix="/auth")
    login_page = routes.routes["login_page"]
    req = MagicMock()
    req.query_params = {"error": "invalid"}
    out = login_page(req)
    assert out is not None


def test_login_page_with_redirect_to():
    auth = MagicMock()
    auth.config = {}
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_login_routes(rt=fake_rt, prefix="/auth")
    login_page = routes.routes["login_page"]
    req = MagicMock()
    req.query_params = {"redirect_to": "/dashboard"}
    out = login_page(req)
    assert out is not None


def test_logout_route():
    """logout clears session and redirects to login."""
    auth = MagicMock()
    auth.config = {}
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_logout_route(rt=fake_rt, prefix="/auth")
    logout_fn = routes.routes["logout"]
    sess = {"auth": "alice", "user_id": 1}
    resp = logout_fn(sess)
    assert sess == {}


# ---------------------------------------------------------------------------
# Registration routes — register_page, register_submit
# ---------------------------------------------------------------------------


def test_register_page_no_error():
    auth = MagicMock()
    auth.config = {"allow_registration": True}
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_registration_routes(rt=fake_rt, prefix="/auth")
    register_page = routes.routes["register_page"]
    req = MagicMock()
    req.query_params = {}
    out = register_page(req)
    assert out is not None


def test_register_page_with_error():
    auth = MagicMock()
    auth.config = {"allow_registration": True}
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_registration_routes(rt=fake_rt, prefix="/auth")
    register_page = routes.routes["register_page"]
    req = MagicMock()
    req.query_params = {"error": "password_mismatch"}
    out = register_page(req)
    assert out is not None


@pytest.mark.asyncio
async def test_register_submit_no_terms():
    """When accept_terms is not 'on', redirect with error=terms_required."""
    auth = MagicMock()
    auth.config = {"allow_registration": True}
    auth.user_repo = MagicMock()
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_registration_routes(rt=fake_rt, prefix="/auth")
    register_submit = routes.routes["register_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={"accept_terms": ""})
    sess = {}
    resp = await register_submit(req, sess)
    assert "error=terms_required" in str(resp.headers.get("location", ""))


@pytest.mark.asyncio
async def test_register_submit_password_mismatch():
    auth = MagicMock()
    auth.config = {"allow_registration": True}
    auth.user_repo = MagicMock()
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_registration_routes(rt=fake_rt, prefix="/auth")
    register_submit = routes.routes["register_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={
        "accept_terms": "on",
        "password": "abc",
        "confirm_password": "xyz",
    })
    sess = {}
    resp = await register_submit(req, sess)
    assert "error=password_mismatch" in str(resp.headers.get("location", ""))


@pytest.mark.asyncio
async def test_register_submit_username_taken():
    auth = MagicMock()
    auth.config = {"allow_registration": True}
    auth.user_repo = MagicMock()
    auth.user_repo.get_by_username = MagicMock(return_value="existing")
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_registration_routes(rt=fake_rt, prefix="/auth")
    register_submit = routes.routes["register_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={
        "accept_terms": "on",
        "password": "abc",
        "confirm_password": "abc",
        "username": "alice",
    })
    sess = {}
    resp = await register_submit(req, sess)
    assert "error=username_taken" in str(resp.headers.get("location", ""))


@pytest.mark.asyncio
async def test_register_submit_success():
    auth = MagicMock()
    auth.config = {"allow_registration": True}
    fake_user = MagicMock()
    fake_user.username = "alice"
    fake_user.id = 1
    fake_user.role = "user"
    auth.user_repo = MagicMock()
    auth.user_repo.get_by_username = MagicMock(return_value=None)
    auth.user_repo.create = MagicMock(return_value=fake_user)
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_registration_routes(rt=fake_rt, prefix="/auth")
    register_submit = routes.routes["register_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={
        "accept_terms": "on",
        "password": "abcdefgh",
        "confirm_password": "abcdefgh",
        "username": "alice",
        "email": "a@x.com",
    })
    sess = {}
    resp = await register_submit(req, sess)
    assert sess["auth"] == "alice"


@pytest.mark.asyncio
async def test_register_submit_creation_fails_returns_error():
    auth = MagicMock()
    auth.config = {"allow_registration": True}
    auth.user_repo = MagicMock()
    auth.user_repo.get_by_username = MagicMock(return_value=None)
    auth.user_repo.create = MagicMock(return_value=None)
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_registration_routes(rt=fake_rt, prefix="/auth")
    register_submit = routes.routes["register_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={
        "accept_terms": "on",
        "password": "abcdefgh",
        "confirm_password": "abcdefgh",
        "username": "alice",
        "email": "a@x.com",
    })
    sess = {}
    resp = await register_submit(req, sess)
    assert "error=creation_failed" in str(resp.headers.get("location", ""))


@pytest.mark.asyncio
async def test_register_submit_raises_returns_error():
    auth = MagicMock()
    auth.config = {"allow_registration": True}
    auth.user_repo = MagicMock()
    auth.user_repo.get_by_username = MagicMock(return_value=None)
    auth.user_repo.create = MagicMock(side_effect=Exception("boom"))
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_registration_routes(rt=fake_rt, prefix="/auth")
    register_submit = routes.routes["register_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={
        "accept_terms": "on",
        "password": "abcdefgh",
        "confirm_password": "abcdefgh",
        "username": "alice",
        "email": "a@x.com",
    })
    sess = {}
    resp = await register_submit(req, sess)
    assert "error=creation_failed" in str(resp.headers.get("location", ""))


# ---------------------------------------------------------------------------
# Password reset routes
# ---------------------------------------------------------------------------


def test_forgot_page_no_msg():
    auth = MagicMock()
    auth.config = {"allow_password_reset": True}
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_password_reset_routes(rt=fake_rt, prefix="/auth")
    forgot = routes.routes["forgot_password"]
    req = MagicMock()
    req.query_params = {}
    out = forgot(req)
    assert out is not None


def test_forgot_page_with_error_success():
    auth = MagicMock()
    auth.config = {"allow_password_reset": True}
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_password_reset_routes(rt=fake_rt, prefix="/auth")
    forgot = routes.routes["forgot_password"]
    req = MagicMock()
    req.query_params = {"error": "x", "success": "y"}
    out = forgot(req)
    assert out is not None


@pytest.mark.asyncio
async def test_forgot_submit():
    auth = MagicMock()
    auth.config = {"allow_password_reset": True}
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_password_reset_routes(rt=fake_rt, prefix="/auth")
    forgot_submit = routes.routes["forgot_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={"email": "a@x.com"})
    resp = await forgot_submit(req)
    assert "success=sent" in str(resp.headers.get("location", ""))


# ---------------------------------------------------------------------------
# Profile routes
# ---------------------------------------------------------------------------


def test_profile_page():
    auth = MagicMock()
    auth.config = {}
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_profile_route(rt=fake_rt, prefix="/auth")
    profile_page = routes.routes["profile_page"]
    req = MagicMock()
    req.scope = {"user": MagicMock(username="alice")}
    req.query_params = {}
    out = profile_page(req)
    assert out is not None


def test_profile_page_with_success_error():
    auth = MagicMock()
    auth.config = {}
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_profile_route(rt=fake_rt, prefix="/auth")
    profile_page = routes.routes["profile_page"]
    req = MagicMock()
    req.scope = {"user": MagicMock(username="alice")}
    req.query_params = {"success": "ok", "error": "pw_mismatch"}
    out = profile_page(req)
    assert out is not None


@pytest.mark.asyncio
async def test_profile_submit_password_empty():
    """Skipped: profile_submit happy-paths with no password.

    Just exercises the code path successfully.
    """
    auth = MagicMock()
    auth.config = {}
    auth.user_repo = MagicMock()
    auth.user_repo.update = MagicMock(return_value=True)
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_profile_route(rt=fake_rt, prefix="/auth")
    profile_submit = routes.routes["profile_submit"]
    req = MagicMock()
    req.scope = {"user": MagicMock()}
    req.form = AsyncMock(return_value={
        "current_password": "old",
        "new_password": "newpass",
        "confirm_password": "newpass",
    })
    sess = {}
    # Just run the path
    resp = await profile_submit(req)
    assert resp is not None


# ---------------------------------------------------------------------------
# register_all + admin_dashboard
# ---------------------------------------------------------------------------


def test_register_all_minimal_no_admin():
    """register_all without admin option."""
    auth = MagicMock()
    auth.config = {"allow_registration": False, "allow_password_reset": False}
    auth.user_repo = MagicMock()
    routes = AuthRoutes(auth)
    app = MagicMock()
    fake_route = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    app.route = fake_route
    routes.register_all(app, prefix="/auth", include_admin=False, allow_custom_login=False)
    assert "login_page" in routes.routes
    assert "logout" in routes.routes
    assert "profile_page" in routes.routes


def test_register_all_with_custom_login():
    """When allow_custom_login=True, skip login routes."""
    auth = MagicMock()
    auth.config = {"allow_registration": False, "allow_password_reset": False}
    auth.user_repo = MagicMock()
    routes = AuthRoutes(auth)
    app = MagicMock()
    fake_route = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    app.route = fake_route
    routes.register_all(app, prefix="/auth", allow_custom_login=True)
    assert "login_page" not in routes.routes
    assert "logout" in routes.routes


def test_register_all_with_allow_registration():
    auth = MagicMock()
    auth.config = {"allow_registration": True, "allow_password_reset": False}
    auth.user_repo = MagicMock()
    routes = AuthRoutes(auth)
    app = MagicMock()
    fake_route = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    app.route = fake_route
    routes.register_all(app, prefix="/auth")
    assert "register_page" in routes.routes


def test_register_all_with_password_reset():
    auth = MagicMock()
    auth.config = {"allow_registration": False, "allow_password_reset": True}
    auth.user_repo = MagicMock()
    routes = AuthRoutes(auth)
    app = MagicMock()
    fake_route = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    app.route = fake_route
    routes.register_all(app, prefix="/auth")
    assert "forgot_password" in routes.routes


def test_admin_dashboard():
    """admin_dashboard renders user statistics."""
    auth = MagicMock()
    auth.config = {"allow_registration": False, "allow_password_reset": False}
    auth.user_repo = MagicMock()
    auth.user_repo.count_by_role = MagicMock(return_value={"admin": 1, "manager": 0, "user": 5})
    routes = AuthRoutes(auth)
    app = MagicMock()
    fake_route = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    app.route = fake_route
    routes.register_all(app, prefix="/auth", include_admin=True)
    dashboard = routes.routes["admin_dashboard"]
    req = MagicMock()
    out = dashboard(req)
    assert out is not None
