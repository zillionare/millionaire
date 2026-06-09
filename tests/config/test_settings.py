import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantide.config.branding import DEFAULT_EDITION, get_branding
import quantide.config.dev_stubs as dev_stubs_module
import quantide.config.settings as settings_module
from quantide.config.settings import (
    DEFAULT_TIMEZONE,
    get_data_home,
    get_data_source,
    get_dingtalk_access_token,
    get_dingtalk_secret,
    get_epoch,
    get_mail_receivers,
    get_mail_sender,
    get_mail_server,
    get_settings,
    get_timezone,
    get_tushare_token,
)
from quantide.data.models.app_state import AppState


class FailingTable:
    def get(self, _pk):
        raise RuntimeError("table missing")


class SequenceTable:
    def __init__(self, results):
        self._results = list(results)

    def get(self, _pk):
        if not self._results:
            return None
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeDb:
    def __init__(self, table):
        self._initialized = True
        self._table = table

    def __getitem__(self, name: str):
        assert name == "app_state"
        return self._table


def test_get_settings_uses_defaults_when_db_is_unavailable(monkeypatch):
    monkeypatch.setattr(settings_module, "_load_app_state", lambda: None)

    settings = get_settings()

    assert settings.edition == DEFAULT_EDITION
    assert settings.product_name == get_branding().product_name
    assert settings.release_package == get_branding().release_package
    assert settings.app_home == str(Path("~/.quantide").expanduser())
    assert settings.app_host == "0.0.0.0"
    assert settings.app_port == 8130
    assert settings.app_prefix == "/quantide"
    assert settings.gateway_enabled is False
    assert settings.gateway_base_url == ""
    assert settings.livequote_mode == "gateway"
    assert settings.runtime_mode == "live"
    assert settings.data_source == "tushare"
    assert settings.epoch == datetime.date(2005, 1, 1)
    assert settings.timezone == DEFAULT_TIMEZONE


def test_get_settings_prefers_app_state(db, tmp_path: Path):
    db["app_state"].upsert(
        AppState(
            app_home=str(tmp_path),
            app_prefix="/db-prefix",
            gateway_enabled=True,
            gateway_scheme="https",
            gateway_server="gateway.internal",
            gateway_port=8443,
            gateway_base_url="/qmt",
            gateway_username="db-admin",
            gateway_password="db-secret",
            gateway_timeout=30,
            livequote_mode="gateway",
            runtime_mode="live",
            data_source="tushare",
        ).to_dict(),
        pk="id",
    )

    settings = get_settings()
    assert settings.edition == DEFAULT_EDITION
    assert settings.app_home == str(tmp_path)
    assert settings.app_prefix == "/db-prefix"
    assert settings.gateway_base_url == "https://gateway.internal:8443/qmt"
    assert settings.gateway_username == "db-admin"
    assert settings.gateway_password == "db-secret"
    assert settings.gateway_timeout == 30
    assert settings.livequote_mode == "gateway"
    assert settings.runtime_mode == "live"
    assert settings.data_source == "tushare"


def test_get_settings_allows_db_to_disable_gateway(db):
    db["app_state"].upsert(
        AppState(
            gateway_enabled=False,
            gateway_server="gateway.internal",
            gateway_port=8443,
            gateway_base_url="/qmt",
            livequote_mode="none",
            runtime_mode="backtest",
            data_source="tushare",
        ).to_dict(),
        pk="id",
    )

    settings = get_settings()
    assert settings.gateway_enabled is False
    assert settings.livequote_mode == "none"
    assert settings.runtime_mode == "backtest"


def test_setting_helpers_follow_db_state(db, tmp_path: Path):
    db["app_state"].upsert(
        AppState(
            app_home=str(tmp_path),
            epoch=datetime.date(2020, 1, 2),
        ).to_dict(),
        pk="id",
    )

    assert get_data_home() == str(tmp_path)
    assert get_epoch() == datetime.date(2020, 1, 2)
    assert get_timezone() == DEFAULT_TIMEZONE


def test_notify_and_token_helpers_follow_db_state(db):
    db["app_state"].upsert(
        AppState(
            notify_dingtalk_access_token="db-token",
            notify_dingtalk_secret="db-secret",
            notify_mail_to="a@example.com,b@example.com",
            notify_mail_from="db-from@example.com",
            notify_mail_server="smtp.db.example.com",
            data_source="tushare",
            tushare_token="db-ts-token",
        ).to_dict(),
        pk="id",
    )

    assert get_data_source() == "tushare"
    assert get_dingtalk_access_token() == "db-token"
    assert get_dingtalk_secret() == "db-secret"
    assert get_mail_receivers() == ["a@example.com", "b@example.com"]
    assert get_mail_sender() == "db-from@example.com"
    assert get_mail_server() == "smtp.db.example.com"
    assert get_tushare_token() == "db-ts-token"


def test_load_app_state_logs_repeated_failure_once(monkeypatch):
    messages: list[str] = []

    monkeypatch.setattr(settings_module, "_LAST_APP_STATE_LOAD_ERROR", None)
    monkeypatch.setattr("quantide.data.sqlite.db", FakeDb(FailingTable()))
    monkeypatch.setattr(settings_module.logger, "debug", messages.append)

    assert settings_module._load_app_state() is None
    assert settings_module._load_app_state() is None
    assert messages == ["load app_state failed: table missing"]


def test_load_app_state_resets_failure_marker_after_success(monkeypatch):
    messages: list[str] = []
    table = SequenceTable(
        [
            RuntimeError("table missing"),
            {"id": 1},
            RuntimeError("table missing"),
        ]
    )

    monkeypatch.setattr(settings_module, "_LAST_APP_STATE_LOAD_ERROR", None)
    monkeypatch.setattr("quantide.data.sqlite.db", FakeDb(table))
    monkeypatch.setattr(
        "quantide.data.models.app_state.AppState.from_dict",
        staticmethod(lambda row: row),
    )
    monkeypatch.setattr(settings_module.logger, "debug", messages.append)

    assert settings_module._load_app_state() is None
    assert settings_module._load_app_state() == {"id": 1}
    assert settings_module._load_app_state() is None
    assert messages == [
        "load app_state failed: table missing",
        "load app_state failed: table missing",
    ]


def test_app_state_can_project_to_settings(tmp_path: Path):
    state = AppState(app_home=str(tmp_path), app_prefix="/demo", data_source="tushare")

    settings = state.to_settings()

    assert settings.app_home == str(tmp_path)
    assert settings.app_prefix == "/demo"


def test_get_settings_applies_dev_stub_overrides(monkeypatch, tmp_path: Path):
    monkeypatch.setenv(dev_stubs_module.DEV_STUBS_ENV_VAR, "1")
    monkeypatch.setattr(
        settings_module,
        "_load_app_state",
        lambda: AppState(
            app_home=str(tmp_path),
            gateway_enabled=False,
            gateway_server="real-gateway",
            gateway_port=9000,
            gateway_base_url="/real",
            livequote_mode="none",
            runtime_mode="backtest",
            runtime_market_adapter="",
            runtime_broker_adapter="",
            data_source="csv",
            tushare_token="real-token",
        ),
    )
    monkeypatch.setattr(
        settings_module,
        "ensure_dev_stubs_started",
        lambda: SimpleNamespace(
            gateway_base_url="http://127.0.0.1:19001/qmt",
            gateway_api_key="stub-api-key",
            gateway_username="stub-user",
            gateway_password="stub-password",
            gateway_scheme="http",
            gateway_server="127.0.0.1",
            gateway_port=19001,
        ),
    )

    settings = get_settings()

    assert settings.gateway_enabled is True
    assert settings.gateway_base_url == "http://127.0.0.1:19001/qmt"
    assert settings.gateway_username == "stub-user"
    assert settings.gateway_password == "stub-password"
    assert settings.livequote_mode == "gateway"
    assert settings.runtime_mode == "live"
    assert settings.runtime_market_adapter == "gateway"
    assert settings.runtime_broker_adapter == "gateway"
    assert settings.data_source == "tushare"


def test_cheat_on_close_time_default_is_14_57(monkeypatch):
    monkeypatch.setattr(settings_module, "_load_app_state", lambda: None)
    assert settings_module.get_cheat_on_close_time() == "14:57"
    assert settings_module.parse_cheat_on_close_time("14:57") == (
        datetime.time(14, 57)
    )


def test_cheat_on_close_time_rejects_out_of_range(monkeypatch):
    monkeypatch.setattr(settings_module, "_load_app_state", lambda: None)
    for bad in ("08:59", "15:01", "23:00", "00:00", "ab:cd", ""):
        with pytest.raises(ValueError):
            settings_module.parse_cheat_on_close_time(bad)
    for good in ("09:00", "09:05", "09:30", "14:57", "15:00", "14:50"):
        h, m = map(int, good.split(":"))
        assert settings_module.parse_cheat_on_close_time(good) == datetime.time(h, m)


def test_cheat_on_close_time_loaded_from_app_state(db, tmp_path: Path):
    db["app_state"].upsert(
        AppState(app_home=str(tmp_path), cheat_on_close_time="14:50").to_dict(),
        pk="id",
    )
    assert settings_module.get_cheat_on_close_time() == "14:50"


def test_cheat_on_close_time_invalid_persisted_value_falls_back(monkeypatch, db, tmp_path: Path):
    db["app_state"].upsert(
        AppState(app_home=str(tmp_path), cheat_on_close_time="99:99").to_dict(),
        pk="id",
    )
    assert settings_module.get_cheat_on_close_time() == "14:57"