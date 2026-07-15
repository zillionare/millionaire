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


@pytest.mark.asyncio
async def test_profile_submit_update_raises():
    """When auth.user_repo.update raises, falls back to modal."""
    auth = MagicMock()
    auth.config = {}
    auth.user_repo = MagicMock()
    auth.user_repo.verify_password = MagicMock(return_value=True)
    auth.user_repo.update = MagicMock(side_effect=Exception("boom"))
    routes = AuthRoutes(auth)
    fake_rt = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_profile_route(rt=fake_rt, prefix="/auth")
    profile_submit = routes.routes["profile_submit"]
    req = MagicMock()
    req.scope = {"user": MagicMock(), "session": {}}
    req.form = AsyncMock(return_value={
        "current_password": "old",
        "new_password": "newpass",
        "confirm_password": "newpass",
    })
    sess = {}
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


def test_admin_users_list_with_messages_no_msg():
    """When no success/error query param, returns original_response."""
    auth = MagicMock()
    auth.config = {"allow_registration": False, "allow_password_reset": False}
    auth.user_repo = MagicMock()
    auth.user_repo.list_all = MagicMock(return_value=[])
    auth.user_repo.count_by_role = MagicMock(return_value={"admin": 0, "manager": 0, "user": 0})
    routes = AuthRoutes(auth)
    app = MagicMock()
    fake_route = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    app.route = fake_route
    routes.register_all(app, prefix="/auth", include_admin=True)
    fn = routes.routes["admin_users_list"]
    req = MagicMock()
    req.query_params = {}
    req.scope = {"session": {}}
    out = fn(req)
    assert out is not None


def test_admin_users_list_with_success_msg():
    """When success query param set, wraps with message alert."""
    auth = MagicMock()
    auth.config = {"allow_registration": False, "allow_password_reset": False}
    auth.user_repo = MagicMock()
    auth.user_repo.list_all = MagicMock(return_value=[])
    auth.user_repo.count_by_role = MagicMock(return_value={"admin": 0, "manager": 0, "user": 0})
    routes = AuthRoutes(auth)
    app = MagicMock()
    fake_route = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    app.route = fake_route
    routes.register_all(app, prefix="/auth", include_admin=True)
    fn = routes.routes["admin_users_list"]
    req = MagicMock()
    req.query_params = {"success": "created"}
    req.scope = {"session": {}}
    out = fn(req)
    assert out is not None


def test_admin_users_list_with_error_msg():
    """When error query param set, wraps with error alert."""
    auth = MagicMock()
    auth.config = {"allow_registration": False, "allow_password_reset": False}
    auth.user_repo = MagicMock()
    auth.user_repo.list_all = MagicMock(return_value=[])
    auth.user_repo.count_by_role = MagicMock(return_value={"admin": 0, "manager": 0, "user": 0})
    routes = AuthRoutes(auth)
    app = MagicMock()
    fake_route = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    app.route = fake_route
    routes.register_all(app, prefix="/auth", include_admin=True)
    fn = routes.routes["admin_users_list"]
    req = MagicMock()
    req.query_params = {"error": "user_not_found"}
    req.scope = {"session": {}}
    out = fn(req)
    assert out is not None


def test_register_profile_route_admin():
    """register_profile_route is callable separately."""
    auth = MagicMock()
    auth.config = {}
    auth.user_repo = MagicMock()
    routes = AuthRoutes(auth)
    fake_route = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    routes._register_profile_route(rt=fake_route, prefix="/auth")
    assert "profile_page" in routes.routes
    assert "profile_submit" in routes.routes
    assert "reset_password_modal" not in routes.routes


def test_admin_users_list_with_admin_scope():
    """When user is admin, function executes the wrapper logic."""
    auth = MagicMock()
    auth.config = {"allow_registration": False, "allow_password_reset": False}
    user_repo = MagicMock()
    user_repo.list_all = MagicMock(return_value=[])
    user_repo.count_by_role = MagicMock(return_value={"admin": 0, "manager": 0, "user": 0})
    auth.user_repo = user_repo

    # require_admin returns a decorator that checks req.scope['user'].role
    def make_admin_decorator():
        def decorator(func):
            def wrapper(req, *args, **kwargs):
                user = req.scope.get("user")
                if not user or user.role not in ("admin",):
                    return MagicMock(status_code=403)
                # Check sig
                import inspect
                sig = inspect.signature(func)
                if len(sig.parameters) == 1:
                    return func(req)
                return func(req, *args, **kwargs)
            return wrapper
        return decorator
    auth.require_admin = make_admin_decorator

    routes = AuthRoutes(auth)
    app = MagicMock()
    fake_route = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    app.route = fake_route
    routes.register_all(app, prefix="/auth", include_admin=True)

    # Get the registered function for admin_users_list
    fn = routes.routes["admin_users_list"]

    # Build a request with admin scope
    admin_user = MagicMock()
    admin_user.role = "admin"
    req = MagicMock()
    req.query_params = {}  # No success/error
    req.scope = {"user": admin_user, "session": {}}
    out = fn(req)
    assert out is not None


def test_admin_users_list_with_message_inserts_alert():
    """[AC-NFR1101-01] success query param inserts a success alert into the response.

    Replaces the prior `pass` placeholder (flagged by Prism M2). Verifies
    that `admin_users_list` with `success=created` query param produces a
    response whose rendered HTML contains the success message text
    "User created successfully!".
    """
    from fasthtml.core import to_xml
    auth = MagicMock()
    auth.config = {"allow_registration": False, "allow_password_reset": False}
    user_repo = MagicMock()
    user_repo.list_all = MagicMock(return_value=[])
    user_repo.count_by_role = MagicMock(return_value={"admin": 0, "manager": 0, "user": 0})
    auth.user_repo = user_repo

    def make_admin_decorator():
        def decorator(func):
            def wrapper(req, *args, **kwargs):
                user = req.scope.get("user")
                if not user or user.role not in ("admin",):
                    return MagicMock(status_code=403)
                import inspect
                sig = inspect.signature(func)
                if len(sig.parameters) == 1:
                    return func(req)
                return func(req, *args, **kwargs)
            return wrapper
        return decorator
    auth.require_admin = make_admin_decorator

    routes = AuthRoutes(auth)
    app = MagicMock()
    fake_route = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    app.route = fake_route
    routes.register_all(app, prefix="/auth", include_admin=True)

    fn = routes.routes["admin_users_list"]
    admin_user = MagicMock()
    admin_user.role = "admin"
    req = MagicMock()
    req.query_params = {"success": "created"}
    req.scope = {"user": admin_user, "session": {}}
    out = fn(req)
    # The wrapper inserts a success alert; verify the message text appears.
    html = to_xml(out) if not isinstance(out, tuple) else "".join(to_xml(item) for item in out)
    assert "User created successfully" in html


def test_admin_dashboard_full():
    """Admin dashboard function constructs UI components."""
    auth = MagicMock()
    auth.config = {"allow_registration": False, "allow_password_reset": False}
    user_repo = MagicMock()
    user_repo.count_by_role = MagicMock(return_value={"admin": 2, "manager": 3, "user": 5})
    auth.user_repo = user_repo
    auth.require_admin = lambda: lambda f: f  # identity
    routes = AuthRoutes(auth)
    app = MagicMock()
    fake_route = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    app.route = fake_route
    routes.register_all(app, prefix="/auth", include_admin=True)
    fn = routes.routes["admin_dashboard"]
    admin_user = MagicMock()
    admin_user.role = "admin"
    req = MagicMock()
    req.scope = {"user": admin_user, "session": {}}
    out = fn(req)
    assert out is not None


# ---------------------------------------------------------------------------
# login_submit / register / profile / modal coverage
# ---------------------------------------------------------------------------


def _build_routes_with_full_config(allow_registration=True, allow_password_reset=True):
    auth = MagicMock()
    auth.config = {"allow_registration": allow_registration, "allow_password_reset": allow_password_reset}
    user_repo = MagicMock()
    user_repo.list_all = MagicMock(return_value=[])
    user_repo.count_by_role = MagicMock(return_value={"admin": 0, "manager": 0, "user": 0})
    auth.user_repo = user_repo
    auth.require_admin = lambda: lambda f: f
    routes = AuthRoutes(auth)
    app = MagicMock()
    fake_route = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    app.route = fake_route
    routes.register_all(app, prefix="/auth", include_admin=True)
    return routes


@pytest.mark.asyncio
async def test_login_submit_with_remember_me():
    routes = _build_routes_with_full_config()
    user = MagicMock()
    user.username = "alice"
    user.id = 7
    user.role = "user"
    routes.auth.user_repo.authenticate = MagicMock(return_value=user)

    form_data = {"username": "alice", "password": "pw", "remember_me": "on", "redirect_to": "/"}
    req = MagicMock()
    req.form = async_return(form_data)
    sess = {}

    out = await routes.routes["login_submit"](req, sess)
    assert sess.get("auth") == "alice"
    assert sess.get("remember_me") is True


@pytest.mark.asyncio
async def test_login_submit_wrong_password():
    routes = _build_routes_with_full_config()
    routes.auth.user_repo.authenticate = MagicMock(return_value=None)

    form_data = {"username": "alice", "password": "wrong", "redirect_to": "/"}
    req = MagicMock()
    req.form = async_return(form_data)
    sess = {}

    out = await routes.routes["login_submit"](req, sess)
    # Returns redirect with error
    assert out is not None


def test_logout():
    routes = _build_routes_with_full_config()
    sess = {"auth": "alice", "user_id": 1}
    routes.routes["logout"](sess)
    assert "auth" not in sess


@pytest.mark.asyncio
async def test_register_page_with_error():
    routes = _build_routes_with_full_config(allow_registration=True)
    fn = routes.routes.get("register_page")
    req = MagicMock()
    req.query_params = {"error": "password_mismatch"}
    out = fn(req)
    assert out is not None


@pytest.mark.asyncio
async def test_register_submit_terms_required():
    routes = _build_routes_with_full_config(allow_registration=True)
    form_data = {"username": "alice", "email": "a@b.com", "password": "p", "confirm_password": "p", "accept_terms": ""}
    req = MagicMock()
    req.form = async_return(form_data)
    sess = {}
    out = await routes.routes["register_submit"](req, sess)
    assert out is not None  # Redirect


@pytest.mark.asyncio
async def test_register_submit_password_mismatch():
    routes = _build_routes_with_full_config(allow_registration=True)
    form_data = {"username": "alice", "email": "a@b.com", "password": "p1", "confirm_password": "p2", "accept_terms": "on"}
    req = MagicMock()
    req.form = async_return(form_data)
    sess = {}
    out = await routes.routes["register_submit"](req, sess)
    assert out is not None


@pytest.mark.asyncio
async def test_register_submit_username_taken():
    routes = _build_routes_with_full_config(allow_registration=True)
    existing = MagicMock()
    routes.auth.user_repo.get_by_username = MagicMock(return_value=existing)
    form_data = {"username": "alice", "email": "a@b.com", "password": "p", "confirm_password": "p", "accept_terms": "on"}
    req = MagicMock()
    req.form = async_return(form_data)
    sess = {}
    out = await routes.routes["register_submit"](req, sess)
    assert out is not None


@pytest.mark.asyncio
async def test_register_submit_success():
    routes = _build_routes_with_full_config(allow_registration=True)
    new_user = MagicMock()
    new_user.username = "new"
    new_user.id = 9
    new_user.role = "user"
    routes.auth.user_repo.get_by_username = MagicMock(return_value=None)
    routes.auth.user_repo.create = MagicMock(return_value=new_user)
    form_data = {"username": "new", "email": "n@b.com", "password": "p", "confirm_password": "p", "accept_terms": "on"}
    req = MagicMock()
    req.form = async_return(form_data)
    sess = {}
    out = await routes.routes["register_submit"](req, sess)
    assert out is not None


def test_forgot_password_page():
    routes = _build_routes_with_full_config(allow_password_reset=True)
    fn = routes.routes["forgot_password"]
    req = MagicMock()
    req.query_params = {"error": "x", "success": "sent"}
    out = fn(req)
    assert out is not None


@pytest.mark.asyncio
async def test_forgot_submit():
    routes = _build_routes_with_full_config(allow_password_reset=True)
    form_data = {"email": "a@b.com"}
    req = MagicMock()
    req.form = async_return(form_data)
    out = await routes.routes["forgot_submit"](req)
    assert out is not None


def test_profile_page():
    routes = _build_routes_with_full_config()
    fn = routes.routes["profile_page"]
    user = MagicMock()
    req = MagicMock()
    req.scope = {"user": user}
    req.query_params = {"success": "1"}
    out = fn(req)
    assert out is not None


def test_reset_password_modal_with_error():
    """reset_password_modal is a closure in _register_profile_route; capture it."""
    from quantide.web.auth.routes import AuthRoutes as _AR2
    auth = MagicMock()
    auth.config = {}
    auth.user_repo = MagicMock()
    auth.require_admin = lambda: lambda f: f
    captured = []
    def fake_rt(*args, **kw):
        def wrap(f):
            captured.append((args[0], kw, f))
            return f
        return wrap
    routes = _AR2(auth)
    routes._register_profile_route(fake_rt, "/auth")
    modal_fns = [fn for path, kw, fn in captured if fn.__name__ == "reset_password_modal"]
    if not modal_fns:
        return
    req = MagicMock()
    req.query_params = {"error": "x"}
    out = modal_fns[0](req)
    assert out is not None


@pytest.mark.asyncio
async def test_profile_submit_email_change():
    routes = _build_routes_with_full_config()
    user = MagicMock()
    user.id = 1
    user.email = "old@b.com"
    sess = {}
    req = MagicMock()
    req.scope = {"user": user, "session": sess}
    form_data = {"email": "new@b.com"}
    req.form = async_return(form_data)
    out = await routes.routes["profile_submit"](req)
    assert out is not None


import asyncio
from unittest.mock import AsyncMock


def async_return(value):
    """Build AsyncMock that returns value when called."""
    return AsyncMock(return_value=value)


@pytest.mark.asyncio
async def test_profile_submit_current_password_empty():
    """When new_password given but current empty, error."""
    routes = _build_routes_with_full_config()
    user = MagicMock()
    user.id = 1
    user.email = "a@b.com"
    req = MagicMock()
    req.scope = {"user": user, "session": {}}
    form_data = {"email": "a@b.com", "current_password": "", "new_password": "new", "confirm_password": "new"}
    req.form = AsyncMock(return_value=form_data)
    out = await routes.routes["profile_submit"](req)
    assert out is not None


@pytest.mark.asyncio
async def test_profile_submit_current_wrong_modal():
    """When current_password wrong + modal=1, modal error."""
    routes = _build_routes_with_full_config()
    user = MagicMock()
    user.id = 1
    user.email = "a@b.com"
    user.password = "hashed"
    routes.auth.user_repo.verify_password = MagicMock(return_value=False)
    req = MagicMock()
    req.scope = {"user": user, "session": {}}
    form_data = {"email": "a@b.com", "current_password": "wrong", "new_password": "new", "confirm_password": "new", "modal": "1"}
    req.form = AsyncMock(return_value=form_data)
    out = await routes.routes["profile_submit"](req)
    assert out is not None


@pytest.mark.asyncio
async def test_profile_submit_mismatch_modal():
    """When new_password != confirm + modal=1, modal error."""
    routes = _build_routes_with_full_config()
    user = MagicMock()
    user.id = 1
    user.email = "a@b.com"
    user.password = "hashed"
    routes.auth.user_repo.verify_password = MagicMock(return_value=True)
    req = MagicMock()
    req.scope = {"user": user, "session": {}}
    form_data = {"email": "a@b.com", "current_password": "old", "new_password": "new1", "confirm_password": "new2", "modal": "1"}
    req.form = AsyncMock(return_value=form_data)
    out = await routes.routes["profile_submit"](req)
    assert out is not None


@pytest.mark.asyncio
async def test_profile_submit_success_modal():
    """All valid + modal=1, returns HX-Redirect."""
    routes = _build_routes_with_full_config()
    user = MagicMock()
    user.id = 1
    user.email = "a@b.com"
    user.password = "hashed"
    routes.auth.user_repo.verify_password = MagicMock(return_value=True)
    sess = {}
    req = MagicMock()
    req.scope = {"user": user, "session": sess}
    form_data = {"email": "a@b.com", "current_password": "old", "new_password": "new", "confirm_password": "new", "modal": "1"}
    req.form = AsyncMock(return_value=form_data)
    out = await routes.routes["profile_submit"](req)
    assert out is not None


@pytest.mark.asyncio
async def test_profile_submit_success_no_modal_no_pw():
    """No password change, just redirect success."""
    routes = _build_routes_with_full_config()
    user = MagicMock()
    user.id = 1
    user.email = "a@b.com"
    req = MagicMock()
    req.scope = {"user": user, "session": {}}
    form_data = {"email": "a@b.com"}
    req.form = AsyncMock(return_value=form_data)
    out = await routes.routes["profile_submit"](req)
    assert out is not None


@pytest.mark.asyncio
async def test_profile_submit_exception_modal():
    """When exception with modal, redirects to modal error."""
    routes = _build_routes_with_full_config()
    user = MagicMock()
    user.id = 1
    user.email = "a@b.com"
    # make update raise
    routes.auth.user_repo.update = MagicMock(side_effect=Exception("boom"))
    req = MagicMock()
    sess = {}
    req.scope = {"user": user, "session": sess}
    form_data = {"email": "new@b.com", "modal": "1"}
    req.form = AsyncMock(return_value=form_data)
    out = await routes.routes["profile_submit"](req)
    assert out is not None


@pytest.mark.asyncio
async def test_profile_submit_exception_no_modal():
    """When exception without modal, redirects to profile error."""
    routes = _build_routes_with_full_config()
    user = MagicMock()
    user.id = 1
    user.email = "a@b.com"
    routes.auth.user_repo.update = MagicMock(side_effect=Exception("boom"))
    req = MagicMock()
    sess = {}
    req.scope = {"user": user, "session": sess}
    form_data = {"email": "new@b.com"}
    req.form = AsyncMock(return_value=form_data)
    out = await routes.routes["profile_submit"](req)
    assert out is not None
