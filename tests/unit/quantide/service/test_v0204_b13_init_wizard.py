"""B13 batch: cover missing branches in quantide.service.init_wizard.

Targets specific missing lines reported by /tmp/gg.json:
  - _ensure_db raises when db not initialized (line 125)
  - _is_gateway_available dev_stubs / no-server / not-live paths (lines 210, 214, 216)
  - start_initialization elif init_step<=0 (lines 238-239)
  - save_gateway_config requires server (line 307)
  - save_admin_password empty / repo-None / create / no-id / update-fail (lines 337, 344, 348-355, 358, 360)
  - save_data_init_config happy path (lines 389-396)
  - test_gateway_connection prefix prepend / non-200 / HTTPError (lines 431, 448, 453)
  - _normalize_gateway_url netloc-only (line 478)
"""
from __future__ import annotations

import datetime
import urllib.error
from types import SimpleNamespace

import pytest

import quantide.service.init_wizard as init_wizard_module
from quantide.core.init_wizard_steps import WIZARD_FINAL_STEP
from quantide.data.models.app_state import AppState
from quantide.service.init_wizard import InitWizardService


@pytest.fixture(autouse=True)
def reset_service_state(db):
    db["app_state"].delete_where("1=1")
    service = InitWizardService()
    service._state = None
    yield
    db["app_state"].delete_where("1=1")
    service._state = None


# --- _ensure_db -------------------------------------------------------------


def test_ensure_db_raises_when_db_not_initialized(monkeypatch):
    """Line 125: db._initialized is False -> RuntimeError."""
    monkeypatch.setattr(init_wizard_module.db, "_initialized", False)
    service = InitWizardService()
    with pytest.raises(RuntimeError, match="数据库未初始化"):
        service._ensure_db()


# --- _is_gateway_available --------------------------------------------------


def test_is_gateway_available_dev_stubs_returns_stub_status(db, monkeypatch):
    """Line 210: dev_stubs enabled + fully initialized -> ensure_dev_stubs_started()."""
    monkeypatch.setattr(init_wizard_module, "dev_stubs_enabled", lambda: True)
    monkeypatch.setattr(
        init_wizard_module, "ensure_dev_stubs_started", lambda: SimpleNamespace()
    )
    service = InitWizardService()
    state = AppState(
        init_completed=True,
        init_step=WIZARD_FINAL_STEP,
        app_home="/tmp/x",
    )
    assert service._is_gateway_available(state) is True

    monkeypatch.setattr(init_wizard_module, "ensure_dev_stubs_started", lambda: None)
    assert service._is_gateway_available(state) is False


def test_is_gateway_available_false_when_cannot_use_live_trading(db, monkeypatch):
    """Line 214: can_use_live_trading False -> return False."""
    monkeypatch.setattr(init_wizard_module, "dev_stubs_enabled", lambda: False)
    service = InitWizardService()
    # gateway_enabled=False -> can_use_live_trading() False
    state = AppState(
        init_completed=True,
        init_step=WIZARD_FINAL_STEP,
        app_home="/tmp/x",
        gateway_enabled=False,
    )
    assert service._is_gateway_available(state) is False


def test_is_gateway_available_false_when_no_server(db, monkeypatch):
    """Line 216: gateway_server empty -> return False."""
    monkeypatch.setattr(init_wizard_module, "dev_stubs_enabled", lambda: False)
    service = InitWizardService()
    state = AppState(
        init_completed=True,
        init_step=WIZARD_FINAL_STEP,
        app_home="/tmp/x",
        gateway_enabled=True,
        gateway_server="",
        gateway_api_key="k1",
    )
    assert service._is_gateway_available(state) is False


# --- start_initialization ---------------------------------------------------


def test_start_initialization_sets_step_to_1_when_zero(db):
    """Lines 238-239: init_step <= 0 and not reset_step -> set to 1."""
    service = InitWizardService()
    service.save_state(AppState(init_step=0, app_home="/tmp/x"))
    state = service.start_initialization()
    assert state.init_step == 1


# --- save_gateway_config ----------------------------------------------------


def test_save_gateway_config_requires_server_when_enabled(db):
    """Line 307: enabled=True, server empty -> ValueError."""
    service = InitWizardService()
    with pytest.raises(ValueError, match="服务器地址"):
        service.save_gateway_config(
            enabled=True, server="   ", port=8000, prefix="/", api_key="k1"
        )


# --- save_admin_password ----------------------------------------------------


def test_save_admin_password_rejects_empty(db):
    """Line 337: empty password -> ValueError."""
    service = InitWizardService()
    with pytest.raises(ValueError, match="管理员密码不能为空"):
        service.save_admin_password("   ")


def test_save_admin_password_raises_when_repo_unavailable(db, monkeypatch):
    """Line 344: repo is None after initialize() -> RuntimeError."""
    fake_auth = SimpleNamespace(user_repo=None, initialize=lambda: None)
    monkeypatch.setattr(
        init_wizard_module.AuthManager,
        "get_instance",
        staticmethod(lambda: fake_auth),
    )
    service = InitWizardService()
    with pytest.raises(RuntimeError, match="认证仓库尚未初始化"):
        service.save_admin_password("secret")


def test_save_admin_password_creates_admin_when_missing(db, monkeypatch):
    """Lines 348-355: admin is None -> repo.create() + return."""
    created = {}

    class FakeRepo:
        def get_by_username(self, username):
            assert username == "admin"
            return None

        def create(self, **kwargs):
            created.update(kwargs)

    fake_auth = SimpleNamespace(user_repo=FakeRepo())
    monkeypatch.setattr(
        init_wizard_module.AuthManager,
        "get_instance",
        staticmethod(lambda: fake_auth),
    )
    service = InitWizardService()
    service.save_admin_password("new-secret")
    assert created["username"] == "admin"
    assert created["password"] == "new-secret"
    assert created["role"] == "admin"


def test_save_admin_password_raises_when_admin_has_no_id(db, monkeypatch):
    """Line 358: admin.id is None -> RuntimeError."""
    class FakeRepo:
        def get_by_username(self, username):
            return SimpleNamespace(id=None, username="admin")

        def update(self, *a, **kw):
            return True

    fake_auth = SimpleNamespace(user_repo=FakeRepo())
    monkeypatch.setattr(
        init_wizard_module.AuthManager,
        "get_instance",
        staticmethod(lambda: fake_auth),
    )
    service = InitWizardService()
    with pytest.raises(RuntimeError, match="缺少主键"):
        service.save_admin_password("secret")


def test_save_admin_password_raises_when_update_fails(db, monkeypatch):
    """Line 360: repo.update returns False -> RuntimeError."""
    class FakeRepo:
        def get_by_username(self, username):
            return SimpleNamespace(id=7, username="admin")

        def update(self, *a, **kw):
            return False

    fake_auth = SimpleNamespace(user_repo=FakeRepo())
    monkeypatch.setattr(
        init_wizard_module.AuthManager,
        "get_instance",
        staticmethod(lambda: fake_auth),
    )
    service = InitWizardService()
    with pytest.raises(RuntimeError, match="更新管理员密码失败"):
        service.save_admin_password("secret")


# --- save_data_init_config happy path ---------------------------------------


def test_save_data_init_config_persists_valid_tushare_config(db):
    """Lines 389-396: valid config -> state fields set and saved."""
    service = InitWizardService()
    service.save_data_init_config(
        epoch=datetime.date(2020, 1, 1),
        data_source="tushare",
        tushare_token="valid-token",
        history_years=5,
    )
    state = service.get_state(force_refresh=True)
    assert state.epoch == datetime.date(2020, 1, 1)
    assert state.data_source == "tushare"
    assert state.tushare_token == "valid-token"
    assert state.history_years == 5
    assert state.history_start_date is not None


# --- test_gateway_connection ------------------------------------------------


class _FakeResponse:
    def __init__(self, code):
        self._code = code

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self._code


def test_test_gateway_connection_prepends_slash_to_prefix(db, monkeypatch):
    """Line 431: prefix without leading '/' gets one prepended."""
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse(200)

    monkeypatch.setattr(
        "quantide.service.init_wizard.urllib.request.urlopen", fake_urlopen
    )
    service = InitWizardService()
    ok, _ = service.test_gateway_connection(
        server="127.0.0.1", port=8000, prefix="qmt", api_key="k1"
    )
    assert ok is True
    assert captured["url"] == "http://127.0.0.1:8000/qmt/api/ping"


def test_test_gateway_connection_returns_false_on_non200(db, monkeypatch):
    """Line 448: response code != 200 -> False with status code in message."""
    monkeypatch.setattr(
        "quantide.service.init_wizard.urllib.request.urlopen",
        lambda req, timeout=None: _FakeResponse(500),
    )
    service = InitWizardService()
    ok, msg = service.test_gateway_connection(
        server="127.0.0.1", port=8000, prefix="/", api_key="k1"
    )
    assert ok is False
    assert "500" in msg


def test_test_gateway_connection_returns_false_on_other_http_error(db, monkeypatch):
    """Line 453: HTTPError code 500 (not 401/403) -> generic cannot-connect msg."""
    def raise_http_error(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, None)

    monkeypatch.setattr(
        "quantide.service.init_wizard.urllib.request.urlopen", raise_http_error
    )
    service = InitWizardService()
    ok, msg = service.test_gateway_connection(
        server="127.0.0.1", port=8000, prefix="/", api_key="k1"
    )
    assert ok is False
    assert "HTTP 500" in msg


# --- _normalize_gateway_url -------------------------------------------------


def test_normalize_gateway_url_adds_http_for_netloc_only(monkeypatch):
    """Line 478: parsed.netloc without scheme -> 'http:{value}'."""
    fake_parsed = SimpleNamespace(scheme="", netloc="host:8000", path="")
    monkeypatch.setattr(
        init_wizard_module.urllib.parse, "urlparse", lambda value: fake_parsed
    )
    service = InitWizardService()
    assert service._normalize_gateway_url("host:8000") == "http:host:8000"
