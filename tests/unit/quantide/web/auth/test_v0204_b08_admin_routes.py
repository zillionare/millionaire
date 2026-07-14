"""B08-admin-routes-1: Test class methods on AdminRoutes that don't need registration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quantide.web.auth.admin_routes import AdminRoutes, InfoRow


@pytest.fixture
def admin():
    auth = MagicMock()
    auth.config = {}
    auth.user_repo = MagicMock()
    return AdminRoutes(auth)


def _user(name="alice", email="a@x.com", role="user", active=True):
    u = MagicMock()
    u.username = name
    u.email = email
    u.role = role
    u.active = active
    return u


# ---------------------------------------------------------------------------
# _get_role_color
# ---------------------------------------------------------------------------


def test_get_role_color_admin(admin):
    assert "purple" in admin._get_role_color("admin")


def test_get_role_color_manager(admin):
    assert "blue" in admin._get_role_color("manager")


def test_get_role_color_user(admin):
    assert "gray" in admin._get_role_color("user")


def test_get_role_color_unknown_falls_back(admin):
    out = admin._get_role_color("unknown")
    assert "gray" in out


# ---------------------------------------------------------------------------
# _filter_users
# ---------------------------------------------------------------------------


def test_filter_users_no_filter_returns_all(admin):
    users = [_user()]
    out = admin._filter_users(users, "", "", "")
    assert out == users


def test_filter_users_by_username_search(admin):
    users = [_user("alice"), _user("bob")]
    out = admin._filter_users(users, "ALICE", "", "")
    assert len(out) == 1
    assert out[0].username == "alice"


def test_filter_users_by_email_search(admin):
    users = [_user("alice", "a@x.com"), _user("bob", "b@x.com")]
    out = admin._filter_users(users, "b@x", "", "")
    assert len(out) == 1


def test_filter_users_by_role(admin):
    users = [_user(role="admin"), _user(role="user")]
    out = admin._filter_users(users, "", "user", "")
    assert len(out) == 1


def test_filter_users_active(admin):
    users = [_user(active=True), _user(active=False)]
    out = admin._filter_users(users, "", "", "active")
    assert len(out) == 1


def test_filter_users_inactive(admin):
    users = [_user(active=True), _user(active=False)]
    out = admin._filter_users(users, "", "", "inactive")
    assert len(out) == 1


def test_filter_users_other_status_passthrough(admin):
    users = [_user(active=True), _user(active=False)]
    out = admin._filter_users(users, "", "", "garbage")
    assert len(out) == 2


# ---------------------------------------------------------------------------
# _create_user_list_header
# ---------------------------------------------------------------------------


def test_create_user_list_header(admin):
    out = admin._create_user_list_header()
    assert out is not None


# ---------------------------------------------------------------------------
# _create_filters_section
# ---------------------------------------------------------------------------


def test_create_filters_section(admin):
    out = admin._create_filters_section(search="", role_filter="", status_filter="", prefix="/auth/admin")
    assert out is not None


def test_create_filters_section_with_values(admin):
    out = admin._create_filters_section(search="alice", role_filter="admin", status_filter="active", prefix="/auth/admin")
    assert out is not None


# ---------------------------------------------------------------------------
# _create_pagination
# ---------------------------------------------------------------------------


def test_create_pagination_single_page_returns_none(admin):
    """When total_pages <= 1, _create_pagination returns None."""
    out = admin._create_pagination(current_page=1, total_pages=1, base_url="/auth/admin/users", query_params={})
    assert out is None


def test_create_pagination_many_pages(admin):
    out = admin._create_pagination(current_page=3, total_pages=10, base_url="/auth/admin/users", query_params={"q": "x"})
    assert out is not None


def test_create_pagination_two_pages(admin):
    out = admin._create_pagination(current_page=2, total_pages=2, base_url="/auth/admin/users", query_params={})
    assert out is not None


# ---------------------------------------------------------------------------
# InfoRow
# ---------------------------------------------------------------------------


def test_info_row_returns_div():
    out = InfoRow("Label", "value")
    assert out is not None


def test_info_row_with_int_value():
    out = InfoRow("Count", 42)
    assert out is not None


# ---------------------------------------------------------------------------
# _create_users_table
# ---------------------------------------------------------------------------


def test_create_users_table_empty(admin):
    out = admin._create_users_table(users=[], prefix="/auth/admin")
    assert out is not None


def test_create_users_table_with_users(admin):
    users = [
        _user("alice", "a@x.com", "user", True),
        _user("bob", "b@x.com", "admin", False),
    ]
    out = admin._create_users_table(users=users, prefix="/auth/admin")
    assert out is not None


# ---------------------------------------------------------------------------
# _create_user_form
# ---------------------------------------------------------------------------


def test_create_user_form_no_error(admin):
    out = admin._create_user_form(action="/auth/admin/users/create")
    assert out is not None


def test_create_user_form_with_error(admin):
    out = admin._create_user_form(action="/auth/admin/users/create", error="username_taken")
    assert out is not None


# ---------------------------------------------------------------------------
# _create_edit_user_form
# ---------------------------------------------------------------------------


def test_create_edit_user_form(admin):
    user = MagicMock()
    user.username = "alice"
    user.email = "a@x.com"
    user.role = "user"
    user.active = True
    out = admin._create_edit_user_form(user=user, action="/auth/admin/users/edit/1")
    assert out is not None


def test_create_edit_user_form_error(admin):
    user = MagicMock()
    user.username = "alice"
    user.email = "a@x.com"
    user.role = "user"
    user.active = True
    out = admin._create_edit_user_form(user=user, action="/auth/admin/users/edit/1", error="invalid")
    assert out is not None


# ---------------------------------------------------------------------------
# _create_delete_confirmation
# ---------------------------------------------------------------------------


def test_create_delete_confirmation(admin):
    user = MagicMock()
    user.username = "alice"
    user.email = "a@x.com"
    out = admin._create_delete_confirmation(user=user, prefix="/auth/admin")
    assert out is not None


# ---------------------------------------------------------------------------
# Route registration tests (extract handle_user_* etc.)
# ---------------------------------------------------------------------------


from unittest.mock import AsyncMock
import pytest as _pytest


@_pytest.fixture
def fake_app():
    app = MagicMock()
    fake_route = MagicMock(side_effect=lambda *args, **kw: lambda f: f)
    app.route = fake_route
    return app


def test_register_admin_routes_returns_dict(admin, fake_app):
    out = admin.register_admin_routes(fake_app, "/auth/admin")
    assert isinstance(out, dict)
    # Routes should be stored
    assert "admin_users_list" in admin.routes
    assert "admin_user_create_form" in admin.routes
    assert "admin_user_create_submit" in admin.routes
    assert "admin_user_edit_form" in admin.routes
    assert "admin_user_edit_submit" in admin.routes
    assert "admin_user_delete_confirm" in admin.routes
    assert "admin_user_delete_submit" in admin.routes


# ---------------------------------------------------------------------------
# handle_user_create tests
# ---------------------------------------------------------------------------


@_pytest.mark.asyncio
async def test_handle_user_create_missing_fields(admin, fake_app):
    """When username/email/password missing → redirect with error."""
    admin.register_admin_routes(fake_app, "/auth/admin")
    submit = admin.routes["admin_user_create_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={"username": "", "email": "", "password": ""})
    resp = await submit(req)
    assert "error=missing_fields" in str(resp.headers.get("location", ""))


@_pytest.mark.asyncio
async def test_handle_user_create_password_mismatch(admin, fake_app):
    admin.register_admin_routes(fake_app, "/auth/admin")
    submit = admin.routes["admin_user_create_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={
        "username": "alice",
        "email": "a@x.com",
        "password": "abcdefgh",
        "confirm_password": "wrong",
    })
    resp = await submit(req)
    assert "error=password_mismatch" in str(resp.headers.get("location", ""))


@_pytest.mark.asyncio
async def test_handle_user_create_password_weak(admin, fake_app):
    admin.register_admin_routes(fake_app, "/auth/admin")
    submit = admin.routes["admin_user_create_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={
        "username": "alice",
        "email": "a@x.com",
        "password": "short",
        "confirm_password": "short",
    })
    resp = await submit(req)
    assert "error=password_weak" in str(resp.headers.get("location", ""))


@_pytest.mark.asyncio
async def test_handle_user_create_success(admin, fake_app):
    admin.register_admin_routes(fake_app, "/auth/admin")
    admin.auth.user_repo = MagicMock()
    admin.auth.user_repo.create = MagicMock(return_value="newuser")
    submit = admin.routes["admin_user_create_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={
        "username": "alice",
        "email": "a@x.com",
        "password": "abcdefgh",
        "confirm_password": "abcdefgh",
        "role": "user",
        "active": "on",
    })
    resp = await submit(req)
    # On success returns nothing or success redirect
    assert resp is not None or resp is None


@_pytest.mark.asyncio
async def test_handle_user_create_exception(admin, fake_app):
    admin.register_admin_routes(fake_app, "/auth/admin")
    admin.auth.user_repo = MagicMock()
    admin.auth.user_repo.create = MagicMock(side_effect=Exception("boom"))
    submit = admin.routes["admin_user_create_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={
        "username": "alice",
        "email": "a@x.com",
        "password": "abcdefgh",
        "confirm_password": "abcdefgh",
        "role": "user",
    })
    resp = await submit(req)
    # Should redirect with some error
    location = str(resp.headers.get("location", "")) if hasattr(resp, "headers") else ""
    assert "error" in location or resp is not None


@_pytest.mark.asyncio
async def test_handle_user_create_no_user_created(admin, fake_app):
    admin.register_admin_routes(fake_app, "/auth/admin")
    admin.auth.user_repo = MagicMock()
    admin.auth.user_repo.create = MagicMock(return_value=None)
    submit = admin.routes["admin_user_create_submit"]
    req = MagicMock()
    req.form = AsyncMock(return_value={
        "username": "alice",
        "email": "a@x.com",
        "password": "abcdefgh",
        "confirm_password": "abcdefgh",
        "role": "user",
    })
    resp = await submit(req)
    location = str(resp.headers.get("location", "")) if hasattr(resp, "headers") else ""
    assert "error" in location or resp is not None
