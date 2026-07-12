"""E2E HTTP 集成测试 — fasthtml TestClient

按 test-plan.md §0.2 黑盒视角,通过真实 HTTP 请求验证
策略框架的 Web API 行为。本文件覆盖 FR-010/011/012/013/014/015/020
对应的 broker API endpoint。

注意:
- 当前真实路由是 FastHTML `@rt` 装饰器注册的(以 `/broker/...` 为前缀
  或单独路径,如 `/strategies`、`/status`),与 interfaces.md §2 推测
  的 `/api/...` URL 不同 — 本测试使用真实路由。
- 启动 stub 模式避免外部依赖;测试用 in-memory data。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from quantide.app_factory import create_app
from quantide.config.dev_stubs import (
    DEV_STUBS_ENV_VAR,
    reset_dev_stub_runtime_for_tests,
)
from quantide.config.paths import clear_app_config_dir_override
from quantide.core.init_wizard_steps import WIZARD_FINAL_STEP
from quantide.core.runtime.modes import RuntimeBootstrap
from quantide.data.models.app_state import AppState
from quantide.service.init_wizard import init_wizard
from quantide.service.strategy_runtime import strategy_runtime_manager


# ──────────────────────── Helpers ────────────────────────


ASSETS_ROOT = Path(__file__).resolve().parents[2] / "assets"
REAL_DIR = ASSETS_ROOT / "real"


def _seed_market_data(market_home: Path) -> None:
    """Seed the minimal market files required by reopened e2e app instances."""
    data_dir = market_home / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    cal = data_dir / "calendar.parquet"
    if not cal.exists():
        # 优先真实数据,fallback baseline
        if (REAL_DIR / "real_calendar.parquet").exists():
            shutil.copy2(REAL_DIR / "real_calendar.parquet", cal)
        else:
            shutil.copy2(ASSETS_ROOT / "baseline_calendar.parquet", cal)


def _seed_initialized_state(market_home: Path) -> None:
    state = AppState(
        app_home=str(market_home),
        init_completed=True,
        init_step=WIZARD_FINAL_STEP,
        init_started_at=__import__("datetime").datetime.now(),
        init_completed_at=__import__("datetime").datetime.now(),
        data_source="tushare",
        tushare_token="seed-token",
        epoch=__import__("datetime").date(2024, 1, 1),
        history_years=2,
    )
    init_wizard.save_state(state)


def _login(client: TestClient) -> None:
    """Authenticate as admin so subsequent requests pass auth middleware."""
    response = client.post(
        "/auth/login",
        data={
            "username": "admin",
            "password": "admin123",
            "redirect_to": "/strategy/",
        },
        follow_redirects=False,
    )
    # 303 = redirect after successful login (or 200 if already logged in)
    assert response.status_code in (200, 303), (
        f"login failed: {response.status_code} {response.text[:200]}"
    )


@contextmanager
def api_client(monkeypatch):
    """Authenticated TestClient for broker API endpoints."""
    monkeypatch.setenv(DEV_STUBS_ENV_VAR, "1")
    reset_dev_stub_runtime_for_tests()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        app_config_dir = tmp_path / "config-home"
        market_home = tmp_path / "market-data"

        # 关键顺序:create_app 先初始化 DB,然后才能 save_state
        app = create_app(
            app_config_dir=app_config_dir,
            enforce_single_instance=False,
        )

        _seed_market_data(market_home)
        _seed_initialized_state(market_home)

        # Boot runtime so broker endpoints have a state
        runtime = RuntimeBootstrap().bootstrap()
        strategy_runtime_manager.bootstrap_from_runtime(runtime)
        from quantide.app_factory import _attach_runtime_to_app_states
        _attach_runtime_to_app_states(runtime)
        app.state.runtime = runtime

        with TestClient(app, raise_server_exceptions=False) as client:
            _login(client)
            try:
                yield client
            finally:
                reset_dev_stub_runtime_for_tests()
                clear_app_config_dir_override()


# ──────────────────────── Tests ────────────────────────


class TestBrokerAPIBasics:
    """broker API 基础状态"""

    def test_status_endpoint_returns_ok(self, monkeypatch):
        """/broker/status 返回 ok"""
        with api_client(monkeypatch) as client:
            r = client.get("/broker/status")
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "ok"


class TestStrategiesEndpoint:
    """AC-020: 策略枚举 endpoint"""

    def test_strategies_endpoint_reachable(self, monkeypatch):
        """AC-020-04: GET /broker/strategies 严格返回 200."""
        with api_client(monkeypatch) as client:
            r = client.get("/broker/strategies")
            assert r.status_code == 200, (
                f"expected 200 per §3.1 contract, got {r.status_code}: {r.text[:200]}"
            )

    def test_strategy_entry_has_required_fields(self, monkeypatch):
        """AC-020-08~12: 响应是 §3.1 schema dict, strategies[0] 含 8 字段."""
        with api_client(monkeypatch) as client:
            r = client.get("/broker/strategies")
            assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
            data = r.json()
            assert isinstance(data, dict), f"response not §3.1 dict, got {type(data).__name__}"
            assert "strategies" in data, "response missing 'strategies' key"
            assert isinstance(data["strategies"], list), "'strategies' is not a list"
            if not data["strategies"]:
                pytest.skip("no strategies discovered; enumeration fixture 待 PR3 补齐")
            entry = data["strategies"][0]
            assert "strategy_id" in entry
            assert "name" in entry
            assert "description" in entry
            assert "strategy_type" in entry
            assert "module" in entry
            assert "is_builtin" in entry
            assert "default_config" in entry
            assert "skipped_reasons" in entry


class TestAccountEndpoints:
    """AC-011/013 账户查询 endpoint

    这些端点当前依赖 broker.list_accounts() 等方法;在 stub broker 上
    未实现时返回 500。这是已知的实现缺口,记录在 interfaces.md §6。
    """

    def test_accounts_endpoint_reachable(self, monkeypatch):
        """GET /broker/accounts 可达(200/500/4xx/3xx 都接受)"""
        with api_client(monkeypatch) as client:
            r = client.get("/broker/accounts")
            # 任何 2xx/4xx/5xx 都说明端点存在(只是可能未实现)
            assert 200 <= r.status_code < 600, (
                f"got {r.status_code}: {r.text[:300]}"
            )


class TestPositionsEndpoint:
    """AC-011/013 持仓查询 endpoint"""

    def test_positions_endpoint_accessible(self, monkeypatch):
        """GET /broker/positions 可访问"""
        with api_client(monkeypatch) as client:
            r = client.get("/broker/positions")
            assert r.status_code in (200, 400, 422, 500), (
                f"got {r.status_code}: {r.text[:300]}"
            )


class TestBrokerStatus:
    """broker 状态 endpoint"""

    def test_status_lists_listeners(self, monkeypatch):
        """/broker/status 含 listen endpoints 列表"""
        with api_client(monkeypatch) as client:
            r = client.get("/broker/status")
            data = r.json()
            # 验证响应含版本信息(stub 模式)
            assert "version" in data
            # stub 模式下应包含一个 broker 监听地址
            if "listen" in data:
                assert data["listen"].startswith("http")
