"""Helpers for authenticated system-settings end-to-end sessions."""

from __future__ import annotations

import datetime
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from starlette.testclient import TestClient

from quantide.app_factory import _attach_runtime_to_app_states, create_app
from quantide.config.paths import clear_app_config_dir_override
from quantide.core.init_wizard_steps import WIZARD_FINAL_STEP
from quantide.core.runtime.modes import RuntimeBootstrap
from quantide.data.models.app_state import AppState
from quantide.data.sqlite import db
from quantide.service.init_wizard import init_wizard
from quantide.service.registry import BrokerRegistry
from quantide.service.strategy_runtime import strategy_runtime_manager
from quantide.web.auth.manager import AuthManager
from quantide.web.pages import init_wizard as init_wizard_page
from tests.e2e.support.auth_fixture import ensure_test_admin

TESTS_ROOT = Path(__file__).resolve().parents[2]
ASSETS_ROOT = TESTS_ROOT / "assets"


_SYNC_STATUS_TEMPLATE = {
    "is_running": False,
    "current_task": "",
    "progress": 0,
    "stage": "",
    "message": "",
    "completed": False,
    "error": None,
}


def _reset_market_data_hub() -> None:
    from quantide.service.market_data_hub import market_data_hub

    # ``MarketDataHub`` is intentionally a production singleton, but each
    # e2e app session must get a fresh test view of its in-memory state.
    market_data_hub.stop()
    with market_data_hub._lock:
        market_data_hub._snapshots.clear()
        market_data_hub._limits.clear()
        market_data_hub._subscribed.clear()


def _reset_broker_registry() -> None:
    """Clear process-global broker registrations between isolated e2e apps."""
    registry = BrokerRegistry()
    registry._brokers.clear()
    registry._default = None


def _reset_global_state() -> None:
    init_wizard._state = None
    previous_auth = AuthManager.get_instance()
    if previous_auth is not None:
        previous_auth.close()
    AuthManager._instance = None
    init_wizard_page._sync_status = dict(_SYNC_STATUS_TEMPLATE)
    init_wizard_page._set_download_error(None)
    init_wizard_page._set_reconfigure_mode(False)
    _reset_broker_registry()
    _reset_market_data_hub()


@dataclass
class SystemSettingsE2ESession:
    """Runtime objects used by system-settings e2e tests."""

    client: TestClient
    market_home: Path
    app_config_dir: Path


def _login_as_admin(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        data={
            "username": "admin",
            "password": "admin123",
            "redirect_to": "/system/gateway/",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


@contextmanager
def open_system_settings_client(app_config_dir: Path, market_home: Path | None = None):
    """Open an authenticated client against an existing app config dir."""
    if market_home is not None:
        _seed_market_data(market_home)
    app = create_app(
        app_config_dir=app_config_dir,
        enforce_single_instance=False,
    )
    ensure_test_admin()
    if market_home is not None:
        _seed_initialized_state(market_home)
        runtime = RuntimeBootstrap().bootstrap()
        strategy_runtime_manager.bootstrap_from_runtime(runtime)
        app.state.runtime = runtime
        _attach_runtime_to_app_states(runtime)
    with TestClient(app) as client:
        _login_as_admin(client)
        yield client


def _seed_initialized_state(market_home: Path) -> None:
    state = AppState(
        app_home=str(market_home),
        init_completed=True,
        init_step=WIZARD_FINAL_STEP,
        init_started_at=datetime.datetime.now(),
        init_completed_at=datetime.datetime.now(),
        data_source="tushare",
        tushare_token="seed-token",
        epoch=datetime.date(2024, 1, 1),
        history_years=2,
    )
    init_wizard.save_state(state)


def _seed_market_data(market_home: Path) -> None:
    """Seed the minimal market files required by reopened e2e app instances.

    Args:
        market_home: Temporary market-data home used by the reopened app.
    """
    data_dir = market_home / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    calendar_path = data_dir / "calendar.parquet"
    if not calendar_path.exists():
        shutil.copy2(ASSETS_ROOT / "baseline_calendar.parquet", calendar_path)


@contextmanager
def system_settings_e2e_session():
    """Create an initialized and authenticated session for system pages."""
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        app_config_dir = tmp_path / "config-home"
        market_home = tmp_path / "market-data"

        _reset_global_state()

        try:
            with open_system_settings_client(app_config_dir, market_home) as client:
                yield SystemSettingsE2ESession(
                    client=client,
                    market_home=market_home,
                    app_config_dir=app_config_dir,
                )
        finally:
            db.close()
            _reset_global_state()
            clear_app_config_dir_override()
