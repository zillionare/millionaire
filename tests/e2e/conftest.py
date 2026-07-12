"""Shared fixtures for UI e2e journeys."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from starlette.testclient import TestClient

from quantide.app_factory import _attach_runtime_to_app_states, create_app
from quantide.config.dev_stubs import DEV_STUBS_ENV_VAR, reset_dev_stub_runtime_for_tests
from quantide.config.paths import clear_app_config_dir_override
from quantide.core.runtime.modes import RuntimeBootstrap
from quantide.service.strategy_runtime import strategy_runtime_manager
from tests.e2e.support.system_settings_session import (
    _reset_global_state,
    _seed_initialized_state,
    _seed_market_data,
    system_settings_e2e_session,
)
from tests.e2e.support.tushare_stub import patched_tushare_fetcher


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


@pytest.fixture(autouse=True)
def clean_runtime_state() -> Iterator[None]:
    """Reset shared runtime state around each UI e2e test."""
    _clear_runtime_manager()
    yield
    _clear_runtime_manager()
    _reset_global_state()
    clear_app_config_dir_override()
    reset_dev_stub_runtime_for_tests()


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
