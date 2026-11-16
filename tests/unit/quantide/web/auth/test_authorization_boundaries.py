"""Authentication and write authorization regressions using the real role guard."""

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from quantide.web.auth.admin_routes import AdminRoutes
from quantide.web.auth.middleware import AuthBeforeware


class Router:
    def route(self, *args, **kwargs):
        return lambda function: function


def test_forged_username_cookie_cannot_authenticate_an_existing_administrator():
    auth = SimpleNamespace(get_user=Mock())
    guard = AuthBeforeware(auth)
    before = guard.create_beforeware()
    request = SimpleNamespace(cookies={"remember_user": "admin"}, scope={})
    session = {}
    response = before.f(request, session)
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"
    assert session == {}
    auth.get_user.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [None, "user"])
@pytest.mark.parametrize("action", ["create", "edit", "delete"])
async def test_admin_writes_reject_unprivileged_callers_before_reading_form_or_writing(role, action):
    repository = Mock()
    auth = SimpleNamespace(user_repo=repository)
    auth.require_admin = AuthBeforeware(auth).require_admin
    admin = AdminRoutes(auth)
    admin.register_admin_routes(Router())
    request = SimpleNamespace(
        scope={"user": SimpleNamespace(id=1, role=role)} if role else {},
        form=AsyncMock(return_value={"username": "elevated", "role": "admin"}),
    )
    submit = admin.routes[f"admin_user_{action}_submit"]
    assert inspect.iscoroutinefunction(submit), "The router must await protected async handlers"
    kwargs = {} if action == "create" else {"id": 2}
    result = await submit(request, **kwargs)
    assert result.status_code == 403
    request.form.assert_not_awaited()
    assert repository.mock_calls == []


def test_auth_storage_releases_file_and_can_reopen_after_shutdown(tmp_path, monkeypatch):
    from quantide.web.auth.manager import AuthManager

    monkeypatch.setattr(AuthManager, "_instance", None)
    database = tmp_path / "auth.db"
    auth = AuthManager(database)
    auth.initialize()
    auth.close()
    retired = tmp_path / "auth-retired.db"
    database.replace(retired)
    retired.replace(database)
    auth.reopen()
    assert auth.user_repo.get_by_username("unknown") is None
    auth.close()
    database.unlink()
