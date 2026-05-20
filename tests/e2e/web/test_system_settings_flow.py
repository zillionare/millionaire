"""End-to-end tests for system settings flows."""

from __future__ import annotations

import datetime

import pytest

from quantide.service.init_wizard import init_wizard
from quantide.web.pages.system import jobs as jobs_page
from tests.e2e.support.gateway_stub import running_gateway_stub
from tests.e2e.support.system_settings_session import (
    open_system_settings_client,
    system_settings_e2e_session,
)
from tests.e2e.support.tushare_stub import patched_tushare_fetcher


@pytest.mark.e2e
@pytest.mark.release_gate
def test_gateway_settings_can_test_and_persist_configuration():
    with system_settings_e2e_session() as session, running_gateway_stub(prefix="/qmt") as gateway_stub:
        page = session.client.get("/system/gateway/", follow_redirects=False)
        assert page.status_code == 200
        assert "保存配置" in page.text

        test_response = session.client.post(
            "/system/gateway/test",
            data={
                "gateway_enabled": "on",
                "gateway_server": gateway_stub.host,
                "gateway_port": str(gateway_stub.port),
                "gateway_prefix": gateway_stub.prefix,
                "gateway_api_key": "gateway-key",
                "gateway_timeout": "5",
            },
        )
        assert test_response.status_code == 200
        assert "连通性测试通过" in test_response.text
        assert gateway_stub.prefix in test_response.text

        save_response = session.client.post(
            "/system/gateway/save",
            data={
                "gateway_enabled": "on",
                "gateway_server": gateway_stub.host,
                "gateway_port": str(gateway_stub.port),
                "gateway_prefix": gateway_stub.prefix,
                "gateway_api_key": "gateway-key",
                "gateway_timeout": "5",
            },
        )
        assert save_response.status_code == 200
        assert "网关配置已保存" in save_response.text

        state = init_wizard.get_state(force_refresh=True)
        assert state.gateway_enabled is True
        assert state.gateway_server == gateway_stub.host
        assert state.gateway_port == gateway_stub.port
        assert state.gateway_base_url == gateway_stub.prefix
        assert state.gateway_api_key == "gateway-key"
        assert state.gateway_timeout == 5

        persisted_page = session.client.get("/system/gateway/", follow_redirects=False)
        assert persisted_page.status_code == 200
        assert gateway_stub.host in persisted_page.text
        assert str(gateway_stub.port) in persisted_page.text


@pytest.mark.e2e
def test_datasource_settings_can_persist_token_and_epoch():
    with system_settings_e2e_session() as session:
        page = session.client.get("/system/datasource/", follow_redirects=False)
        assert page.status_code == 200
        assert "保存配置" in page.text

        response = session.client.post(
            "/system/datasource/save",
            data={
                "data_source": "tushare",
                "tushare_token": "updated-token",
                "epoch": "2023-06-01",
                "history_years": "2",
            },
        )
        assert response.status_code == 200
        assert "数据源配置已保存" in response.text

        state = init_wizard.get_state(force_refresh=True)
        assert state.data_source == "tushare"
        assert state.tushare_token == "updated-token"
        assert state.epoch == datetime.date(2023, 6, 1)
        assert state.history_years == 2

        persisted_page = session.client.get("/system/datasource/", follow_redirects=False)
        assert persisted_page.status_code == 200
        assert "2023-06-01" in persisted_page.text


@pytest.mark.e2e
def test_jobs_toggle_persists_after_reopening_app():
    with system_settings_e2e_session() as session:
        page = session.client.get("/system/jobs/", follow_redirects=False)
        assert page.status_code == 200
        assert "运行中" in page.text

        toggle_response = session.client.get(
            "/system/jobs/toggle/daily_bars_sync",
            follow_redirects=False,
        )
        assert toggle_response.status_code == 303

        toggled_page = session.client.get("/system/jobs/", follow_redirects=False)
        assert toggled_page.status_code == 200
        assert "已停止" in toggled_page.text

        jobs_page._job_enabled_state.clear()

        with open_system_settings_client(session.app_config_dir) as reopened_client:
            reopened_page = reopened_client.get("/system/jobs/", follow_redirects=False)
            assert reopened_page.status_code == 200
            assert "已停止" in reopened_page.text


@pytest.mark.e2e
def test_trade_main_hides_fake_placeholder_metrics_with_gateway_stub():
    with (
        system_settings_e2e_session() as session,
        running_gateway_stub(prefix="/qmt") as gateway_stub,
        patched_tushare_fetcher(),
    ):
        state = init_wizard.get_state(force_refresh=True)
        state.gateway_enabled = True
        state.gateway_server = gateway_stub.host
        state.gateway_port = gateway_stub.port
        state.gateway_base_url = gateway_stub.prefix
        state.gateway_api_key = "gateway-key"
        state.runtime_mode = "live"
        state.runtime_market_adapter = "gateway"
        state.runtime_broker_adapter = "gateway"
        state.livequote_mode = "gateway"
        init_wizard.save_state(state)

        with open_system_settings_client(session.app_config_dir, session.market_home) as reopened_client:
            response = reopened_client.get("/trade/", follow_redirects=False)

        assert response.status_code == 200
        assert "昨收" in response.text
        assert "现价" in response.text
        assert "1678.23" not in response.text
        assert ">--<" not in response.text
        assert "reference-price-panel" in response.text
        assert "grid-cols-[88px_minmax(0,1fr)]" in response.text
        assert "quick-price-btn aspect-square" in response.text
        assert "涨停" in response.text
        assert "跌停" in response.text
        assert 'hx-trigger="input changed delay:200ms"' in response.text
        assert "setActiveSearchIndex(0);" in response.text


@pytest.mark.e2e
def test_trade_main_keeps_side_controls_mutually_exclusive_with_gateway_stub():
    with (
        system_settings_e2e_session() as session,
        running_gateway_stub(prefix="/qmt") as gateway_stub,
        patched_tushare_fetcher(),
    ):
        state = init_wizard.get_state(force_refresh=True)
        state.gateway_enabled = True
        state.gateway_server = gateway_stub.host
        state.gateway_port = gateway_stub.port
        state.gateway_base_url = gateway_stub.prefix
        state.gateway_api_key = "gateway-key"
        state.runtime_mode = "live"
        state.runtime_market_adapter = "gateway"
        state.runtime_broker_adapter = "gateway"
        state.livequote_mode = "gateway"
        init_wizard.save_state(state)

        with open_system_settings_client(session.app_config_dir, session.market_home) as reopened_client:
            response = reopened_client.get("/trade/", follow_redirects=False)

        assert response.status_code == 200
        assert 'id="buy-star"' in response.text
        assert 'id="sell-star"' in response.text
        assert "function handleTradeSubmitIntent(nextSide)" in response.text
        assert "activateTradeSide(nextSide, true);" in response.text
        assert "buyStar.classList.add('hidden');" in response.text
        assert "document.body.addEventListener('dblclick'" in response.text


@pytest.mark.e2e
def test_trade_main_shows_limit_placeholder_and_price_hint_markup_with_gateway_stub():
    with (
        system_settings_e2e_session() as session,
        running_gateway_stub(prefix="/qmt") as gateway_stub,
        patched_tushare_fetcher(),
    ):
        state = init_wizard.get_state(force_refresh=True)
        state.gateway_enabled = True
        state.gateway_server = gateway_stub.host
        state.gateway_port = gateway_stub.port
        state.gateway_base_url = gateway_stub.prefix
        state.gateway_api_key = "gateway-key"
        state.runtime_mode = "live"
        state.runtime_market_adapter = "gateway"
        state.runtime_broker_adapter = "gateway"
        state.livequote_mode = "gateway"
        init_wizard.save_state(state)

        with open_system_settings_client(session.app_config_dir, session.market_home) as reopened_client:
            response = reopened_client.get("/trade/", follow_redirects=False)

        assert response.status_code == 200
        assert 'id="price-input"' in response.text
        assert 'id="price-change-hint"' in response.text
        assert 'value="0.00"' not in response.text
        assert "function updatePriceChangeHint()" in response.text
        assert "function setLimitPlaceholderPrice(value)" in response.text


@pytest.mark.e2e
def test_trade_search_supports_name_and_pinyin_in_stub_mode():
    with system_settings_e2e_session() as session, patched_tushare_fetcher():
        with open_system_settings_client(session.app_config_dir, session.market_home) as reopened_client:
            pinyin_response = reopened_client.get("/trade/search?q=payh", follow_redirects=False)
            name_response = reopened_client.get("/trade/search?q=%E5%B9%B3%E5%AE%89", follow_redirects=False)

        assert pinyin_response.status_code == 200
        assert "平安银行" in pinyin_response.text
        assert 'data-display="平安银行（000001.SZ）"' in pinyin_response.text
        assert 'data-price="' in pinyin_response.text
        assert 'data-price=""' not in pinyin_response.text

        assert name_response.status_code == 200
        assert "平安银行" in name_response.text


@pytest.mark.e2e
def test_system_stock_list_uses_real_name_and_pinyin_in_stub_mode():
    with system_settings_e2e_session() as session, patched_tushare_fetcher():
        with open_system_settings_client(session.app_config_dir, session.market_home) as reopened_client:
            response = reopened_client.get("/system/stocks/search?q=payh", follow_redirects=False)

        assert response.status_code == 200
        assert "平安银行" in response.text
        assert "PAYH" in response.text
