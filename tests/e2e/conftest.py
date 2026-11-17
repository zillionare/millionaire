"""Shared fixtures for UI e2e journeys."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from starlette.testclient import TestClient

from quantide.app_factory import _attach_runtime_to_app_states, create_app
from quantide.config.dev_stubs import (
    DEV_STUBS_ENV_VAR,
    reset_dev_stub_runtime_for_tests,
)
from quantide.config.paths import clear_app_config_dir_override
from quantide.core.runtime.modes import RuntimeBootstrap
from quantide.service.strategy_runtime import strategy_runtime_manager
from tests.e2e.support.auth_fixture import ensure_test_admin
from tests.e2e.support.system_settings_session import (
    _reset_broker_registry,
    _reset_global_state,
    _reset_market_data_hub,
    _seed_initialized_state,
    _seed_market_data,
    system_settings_e2e_session,
)
from tests.e2e.support.tushare_stub import patched_tushare_fetcher


@pytest.fixture(scope="session", autouse=True)
def _isolate_committed_assets(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Route fixture loads through copies so tests never write into tests/assets."""
    from quantide.data.models.calendar import calendar as calendar_instance
    from quantide.data.models.daily_bars import daily_bars as daily_bars_instance

    calendar_cls = type(calendar_instance)
    daily_bars_cls = type(daily_bars_instance)
    assets_root = Path(__file__).resolve().parents[1]
    cache = tmp_path_factory.mktemp("committed-assets")

    def _copy(path: str | Path) -> Path:
        source = Path(path).expanduser()
        try:
            relative = source.resolve().relative_to(assets_root)
        except (OSError, ValueError):
            return source
        target = cache / relative
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return target

    original_calendar_load = calendar_cls.load
    original_daily_connect = daily_bars_cls.connect

    def calendar_load(self, path: str | Path, **kwargs):
        return original_calendar_load(self, _copy(path), **kwargs)

    def daily_connect(self, store_path: str | Path, calendar_store_path: str | Path, **kwargs):
        return original_daily_connect(self, _copy(store_path), _copy(calendar_store_path), **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(calendar_cls, "load", calendar_load)
        patch.setattr(daily_bars_cls, "connect", daily_connect)
        yield


def _clear_runtime_manager() -> None:
    with strategy_runtime_manager._lock:
        strategy_runtime_manager._strategy_runtimes.clear()
        strategy_runtime_manager._account_runtimes.clear()
        strategy_runtime_manager._backtest_runtimes.clear()
        strategy_runtime_manager._backtest_history.clear()
        strategy_runtime_manager._runtime_specs.clear()
        strategy_runtime_manager._blocked_accounts.clear()
        strategy_runtime_manager._blocked_strategies.clear()
        strategy_runtime_manager._risk_events.clear()
        strategy_runtime_manager._runtime = None
        strategy_runtime_manager._registry = None
        strategy_runtime_manager._adapters = None
        strategy_runtime_manager._market_data = None
        strategy_runtime_manager._gateway_broker = None


def _reset_market_data_singletons() -> None:
    """Drop data paths opened by a previous app lifespan in this process."""
    import quantide.data as data_module

    data_module._limit_price_store = None


@pytest.fixture(autouse=True)
def clean_runtime_state() -> Iterator[None]:
    """Reset shared runtime state around each UI e2e test."""
    from quantide.core.message import msg_hub

    msg_hub.stop()
    msg_hub.start()
    _reset_market_data_singletons()
    _clear_runtime_manager()
    _reset_broker_registry()
    _reset_market_data_hub()
    yield
    _clear_runtime_manager()
    _reset_global_state()
    clear_app_config_dir_override()
    reset_dev_stub_runtime_for_tests()


@pytest.fixture(autouse=True)
def skip_private_only_contracts(request) -> None:
    """Keep private-edition gateway UI contracts out of the CE E2E run."""
    if request.node.get_closest_marker("private_only") is None:
        return
    enabled = str(os.getenv("QUANTIDE_ENABLE_EDITION_OVERRIDE", "")).lower()
    edition = str(os.getenv("QUANTIDE_EDITION", "")).lower()
    if enabled not in {"1", "true", "yes", "on"} or edition != "zillionaire":
        pytest.skip("private-only contract; enable the zillionaire edition override")


@contextmanager
def initialized_client() -> Iterator[TestClient]:
    """Open an initialized app client without logging in."""
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        app_config_dir = root / "config-home"
        market_home = root / "market-data"

        _reset_global_state()
        _seed_market_data(market_home)

        with patched_tushare_fetcher():
            app = create_app(
                app_config_dir=app_config_dir,
                enforce_single_instance=False,
            )
            ensure_test_admin()
            _seed_initialized_state(market_home)
            runtime = RuntimeBootstrap().bootstrap()
            strategy_runtime_manager.bootstrap_from_runtime(runtime)
            app.state.runtime = runtime
            _attach_runtime_to_app_states(runtime)
            with TestClient(app) as client:
                yield client


@pytest.fixture
def anonymous_initialized_client() -> Iterator[TestClient]:
    """Yield an initialized-but-anonymous TestClient."""
    with initialized_client() as client:
        yield client


@pytest.fixture
def paper_session(monkeypatch) -> Iterator:
    """Yield an authenticated dev-stub backed UI session."""
    monkeypatch.setenv(DEV_STUBS_ENV_VAR, "1")
    reset_dev_stub_runtime_for_tests()
    with system_settings_e2e_session() as session:
        yield session


@pytest.fixture
def gateway_session() -> Iterator:
    """Yield an authenticated session with fixture-backed Tushare."""
    with patched_tushare_fetcher():
        with system_settings_e2e_session() as session:
            yield session
