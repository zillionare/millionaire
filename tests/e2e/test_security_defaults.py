"""CE security defaults: no implicit admin account and localhost binding."""

from __future__ import annotations

import datetime

import pytest
from starlette.testclient import TestClient

from quantide.app_factory import create_app
from quantide.config.settings import get_settings
from quantide.core.init_wizard_steps import WIZARD_FINAL_STEP
from quantide.data.models.app_state import AppState
from quantide.service.init_wizard import init_wizard
from quantide.web.auth.manager import AuthManager


@pytest.mark.e2e
def test_fresh_app_has_no_default_admin_and_defaults_to_localhost(tmp_path):
    app = create_app(
        app_config_dir=tmp_path / "config-home",
        enforce_single_instance=False,
    )
    auth = AuthManager.get_instance()
    assert auth is not None
    assert auth.user_repo is not None
    assert auth.user_repo.get_by_username("admin") is None
    assert auth.user_repo.authenticate("admin", "admin123") is None
    assert get_settings().app_host == "127.0.0.1"

    with TestClient(app) as client:
        login = client.post(
            "/auth/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=False,
        )
        assert login.status_code == 503
        assert "未初始化" in login.json()["error"]

        root = client.get("/", follow_redirects=False)
        assert root.status_code in (302, 307)
        assert root.headers["location"] == "/init-wizard"


@pytest.mark.e2e
def test_initialized_app_without_admin_rejects_default_credentials_until_wizard_sets_one(
    tmp_path,
):
    market_home = tmp_path / "market-data"
    app = create_app(
        app_config_dir=tmp_path / "config-home",
        enforce_single_instance=False,
    )
    init_wizard.save_state(
        AppState(
            app_home=str(market_home),
            init_completed=True,
            init_started_at=datetime.datetime.now(),
            init_completed_at=datetime.datetime.now(),
            init_step=WIZARD_FINAL_STEP,
            tushare_token="seed-token",
        )
    )

    with TestClient(app) as client:
        rejected = client.post(
            "/auth/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=False,
        )
        assert rejected.status_code == 303
        assert rejected.headers["location"].startswith("/auth/login?error=invalid")

        init_wizard.save_admin_password("StrongPass!123")

        page = client.get("/auth/login")
        assert 'name="password"' in page.text
        assert 'name="username"' not in page.text
        wrong_password = client.post(
            "/auth/login", data={"password": "wrong"}, follow_redirects=False,
        )
        assert wrong_password.headers["location"].startswith("/auth/login?error=invalid")
        password_only = client.post(
            "/auth/login", data={"password": "StrongPass!123"}, follow_redirects=False,
        )
        assert password_only.headers["location"] == "/"
        assert client.get("/system/network/", follow_redirects=False).status_code == 200

        accepted = client.post(
            "/auth/login",
            data={"username": "admin", "password": "StrongPass!123"},
            follow_redirects=False,
        )
        assert accepted.status_code == 303
        assert accepted.headers["location"] == "/"

        still_default = client.post(
            "/auth/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=False,
        )
        assert still_default.status_code == 303
        assert still_default.headers["location"].startswith("/auth/login?error=invalid")
