"""End-to-end tests for the init-wizard user journey."""

from __future__ import annotations

import datetime
import json
from unittest.mock import patch

import pytest

from quantide.config.dev_stubs import (
    DEV_STUB_TUSHARE_TOKEN,
    DEV_STUBS_ENV_VAR,
    reset_dev_stub_runtime_for_tests,
)
from quantide.service.init_wizard import init_wizard
from tests.e2e.support.gateway_stub import running_gateway_stub
from tests.e2e.support.init_wizard_session import init_wizard_e2e_session
from tests.e2e.support.tushare_stub import patched_tushare_fetcher


def _next_step(client, step: int, current_step: int, **form_data):
    payload = {"_current_step": str(current_step), "nav": "next"}
    payload.update(form_data)
    return client.post(f"/init-wizard/step/{step}", data=payload)


def _parse_sync_progress_payload(response_text: str) -> dict:
    lines = [line for line in response_text.splitlines() if line.startswith("data: ")]
    assert lines, response_text
    return json.loads(lines[-1][6:])


def _advance_to_gateway_step(client, market_home) -> None:
    response = client.get("/init-wizard/", follow_redirects=False)
    assert response.status_code == 200
    assert "欢迎使用 Millionaire!" in response.text

    response = _next_step(client, 2, 1)
    assert response.status_code == 200
    assert "数据存储位置" in response.text

    response = _next_step(
        client,
        3,
        2,
        app_home=str(market_home),
        app_port="9130",
        app_prefix="/quantide",
        localhost_only="true",
    )
    assert response.status_code == 200
    assert "管理员密码" in response.text

    response = _next_step(
        client,
        4,
        3,
        admin_password="StrongPass!123",
        admin_password_confirm="StrongPass!123",
    )
    assert response.status_code == 200
    assert "启用 gateway" in response.text


@pytest.mark.e2e
@pytest.mark.release_gate
def test_init_wizard_happy_path_uses_gateway_ping(
):
    with init_wizard_e2e_session() as session, running_gateway_stub(
        prefix="/qmt", api_key="gateway-key"
    ) as gateway_stub, patched_tushare_fetcher():
        _advance_to_gateway_step(session.client, session.market_home)

        response = session.client.post(
            "/init-wizard/gateway-test",
            data={
                "gateway_enabled": "true",
                "gateway_server": gateway_stub.host,
                "gateway_port": str(gateway_stub.port),
                "gateway_api_key": "gateway-key",
                "gateway_prefix": gateway_stub.prefix,
            },
        )
        assert response.status_code == 200
        assert "连通性测试正确" in response.text
        assert f"{gateway_stub.prefix}/api/ping" in response.text

        response = _next_step(
            session.client,
            5,
            4,
            gateway_enabled="true",
            gateway_server=gateway_stub.host,
            gateway_port=str(gateway_stub.port),
            gateway_api_key="gateway-key",
            gateway_prefix=gateway_stub.prefix,
        )
        assert response.status_code == 200
        assert "当前数据源" in response.text
        assert "Tushare 访问密钥" in response.text

        state = init_wizard.get_state(force_refresh=True)
        assert state.app_home == str(session.market_home)
        assert state.gateway_enabled is True
        assert state.gateway_server == gateway_stub.host
        assert state.gateway_port == gateway_stub.port
        assert state.gateway_base_url == gateway_stub.prefix

        response = _next_step(
            session.client,
            6,
            5,
            epoch="2024-01-01",
            data_source="tushare",
            tushare_token="ts-token",
            history_years="2",
        )
        assert response.status_code == 200
        assert "配置已保存，您可以立即进入系统开始使用。" in response.text

        state = init_wizard.get_state(force_refresh=True)
        assert state.data_source == "tushare"
        assert state.tushare_token == "ts-token"
        assert state.history_years == 2

        response = session.client.post("/init-wizard/complete")
        assert response.status_code == 200
        assert "window.location.href = '/'" in response.text

        state = init_wizard.get_state(force_refresh=True)
        assert state.init_completed is True
        assert state.init_step == 6

        response = session.client.get("/init-wizard/", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert response.headers["location"] == "/"


@pytest.mark.e2e
def test_init_wizard_download_validation_stays_on_data_setup(
):
    with init_wizard_e2e_session() as session:
        _advance_to_gateway_step(session.client, session.market_home)

        response = _next_step(session.client, 5, 4)
        assert response.status_code == 200
        assert "当前数据源" in response.text

        response = session.client.post(
            "/init-wizard/download",
            data={
                "epoch": "2024-01-01",
                "data_source": "tushare",
                "tushare_token": "   ",
                "history_years": "3",
            },
        )
        assert response.status_code == 200
        assert "下载前参数校验失败：必须填写 Tushare Token" in response.text
        assert "当前数据源" in response.text


@pytest.mark.e2e
def test_init_wizard_dev_stub_step_five_imports_samples_without_download_dialog(monkeypatch):
    monkeypatch.setenv(DEV_STUBS_ENV_VAR, "1")
    reset_dev_stub_runtime_for_tests()

    try:
        with init_wizard_e2e_session() as session:
            response = session.client.get("/init-wizard/", follow_redirects=False)
            assert response.status_code == 200
            assert "导入开发 Stub 内置样本数据。" in response.text

            response = _next_step(session.client, 2, 1)
            assert response.status_code == 200

            response = _next_step(
                session.client,
                3,
                2,
                app_home=str(session.market_home),
                app_port="9130",
                app_prefix="/quantide",
                localhost_only="true",
            )
            assert response.status_code == 200

            response = _next_step(
                session.client,
                4,
                3,
                admin_password="StrongPass!123",
                admin_password_confirm="StrongPass!123",
            )
            assert response.status_code == 200
            assert "本步骤只展示运行时网关信息" in response.text

            response = _next_step(session.client, 5, 4)
            assert response.status_code == 200
            assert "当前进程已启用开发 Stub 模式" in response.text
            assert "Tushare 访问密钥" not in response.text
            assert "/init-wizard/download" not in response.text
            assert "/init-wizard/step/6" in response.text

            response = _next_step(session.client, 6, 5)
            assert response.status_code == 200
            assert "配置已保存，您可以立即进入系统开始使用。" in response.text
            assert "sync-progress-bar" not in response.text

            state = init_wizard.get_state(force_refresh=True)
            assert state.tushare_token == DEV_STUB_TUSHARE_TOKEN
            assert state.history_years == 1

            complete_response = session.client.post("/init-wizard/complete")
            assert complete_response.status_code == 200
            assert "window.location.href = '/'" in complete_response.text

            login_response = session.client.post(
                "/auth/login",
                data={"username": "admin", "password": "StrongPass!123"},
                follow_redirects=False,
            )
            assert login_response.status_code == 303

            live_response = session.client.get("/trade/live/", follow_redirects=False)
            assert live_response.status_code == 200
            assert "Gateway 已连接" in live_response.text
            assert "Gateway 未连接" not in live_response.text
            assert "实盘网关" in live_response.text
    finally:
        reset_dev_stub_runtime_for_tests()


@pytest.mark.e2e
@pytest.mark.release_gate
def test_init_wizard_download_success_reports_completed_progress():
    with init_wizard_e2e_session() as session, patch(
        "quantide.data.init_data", lambda home, init_db=True: None
    ), patch(
        "quantide.web.pages.init_wizard.stock_list.update", lambda *a, **kw: None
    ), patch(
        "quantide.web.pages.init_wizard.daily_bars.fetch_with_daily_progress", lambda *a, **kw: 0
    ), patch(
        "quantide.web.pages.init_wizard.calendar.update", lambda: None
    ), patch(
        "quantide.web.pages.init_wizard.calendar.last_trade_date",
        lambda: datetime.date(2024, 12, 31),
    ), patch(
        "quantide.web.pages.init_wizard.msg_hub.subscribe", lambda *args, **kwargs: None
    ), patch(
        "quantide.web.pages.init_wizard.msg_hub.unsubscribe", lambda *args, **kwargs: None
    ):
        _advance_to_gateway_step(session.client, session.market_home)

        response = _next_step(session.client, 5, 4)
        assert response.status_code == 200
        assert "当前数据源" in response.text

        response = session.client.post(
            "/init-wizard/download",
            data={
                "epoch": "2024-01-01",
                "data_source": "tushare",
                "tushare_token": "ts-token",
                "history_years": "1",
            },
        )
        assert response.status_code == 200
        assert "sync-progress-bar" in response.text
        assert "/init-wizard/sync-progress" in response.text

        progress_response = session.client.get("/init-wizard/sync-progress?force=true")
        assert progress_response.status_code == 200
        payload = _parse_sync_progress_payload(progress_response.text)
        assert payload["completed"] is True
        assert payload["error"] is None
        assert payload["stage"] == "初始化数据下载完成"

        state = init_wizard.get_state(force_refresh=True)
        assert state.init_completed is True
        assert state.tushare_token == "ts-token"
        assert state.history_years == 1

        complete_response = session.client.post("/init-wizard/complete")
        assert complete_response.status_code == 200
        assert "window.location.href = '/'" in complete_response.text
