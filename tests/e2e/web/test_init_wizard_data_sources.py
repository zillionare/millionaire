"""Configure first, conditionally offer demo data, then explicitly start history import."""

from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from quantide.config.realtime_source import realtime_source
from quantide.config.tencent_trial import trial_status
from quantide.service.init_wizard import init_wizard
from tests.e2e.support.init_wizard_session import init_wizard_e2e_session
from tests.e2e.web.test_init_wizard_flow import _advance_to_runtime_step, _next_step
from tests.init_access_support import AccessClient

pytestmark = [pytest.mark.e2e, pytest.mark.release_gate]


def _configure(session):
    return _next_step(session.client, 5, 4, epoch="2024-01-01", data_source="tushare",
                      tushare_token="not-a-real-token", history_years="1")


def _step(response):
    return BeautifulSoup(response.text, "html.parser").select_one('[name="_current_step"]')["value"]


def test_no_realtime_account_sees_optional_demo_then_explicit_download_confirmation():
    with init_wizard_e2e_session() as session, patch(
        "quantide.web.pages.init_wizard.start_wizard_sync"
    ) as download:
        _advance_to_runtime_step(session.client, session.market_home)
        response = _configure(session)
        assert _step(response) == "5"
        assert "配置实时行情数据源" in response.text
        assert "MarketDataHub" not in response.text
        assert "仿真行情" not in response.text
        assert "30 天" in response.text
        assert not trial_status().enabled
        download.assert_not_called()
        response = _next_step(session.client, 6, 5)
        assert _step(response) == "6"
        assert "开始下载历史数据" in response.text
        assert "not-a-real-token" not in response.text
        assert realtime_source() == "none"
        assert not init_wizard.get_state().init_completed
        download.assert_not_called()


def test_supported_realtime_account_skips_demo_without_starting_its_clock():
    with init_wizard_e2e_session() as session, patch(
        "quantide.service.data_source_access.create_probe_client",
        return_value=AccessClient(realtime=True),
    ), patch("quantide.web.pages.init_wizard.start_wizard_sync") as download:
        _advance_to_runtime_step(session.client, session.market_home)
        response = _configure(session)
        assert _step(response) == "6"
        assert 'name="tencent_trial_enabled"' not in response.text
        assert realtime_source() == "tushare"
        assert not trial_status().first_enabled_at
        download.assert_not_called()


@pytest.mark.parametrize("endpoint,label", [("stock_st", "历史 ST 标记"),
                                           ("stk_limit", "历史涨跌停价格")])
def test_critical_permissions_block_bulk_download_and_explain_account_upgrade(endpoint, label):
    with init_wizard_e2e_session() as session, patch(
        "quantide.service.data_source_access.create_probe_client",
        return_value=AccessClient(failures={endpoint: PermissionError("权限不足 secret")}),
    ), patch("quantide.web.pages.init_wizard.start_wizard_sync") as download:
        _advance_to_runtime_step(session.client, session.market_home)
        response = _configure(session)
        assert _step(response) == "4"
        assert label in response.text
        assert "权限中心" in response.text
        assert "secret" not in response.text
        response = session.client.post("/init-wizard/download")
        assert _step(response) == "4"
        download.assert_not_called()


def test_demo_requires_opt_in_and_completion_requires_successful_history_import():
    with init_wizard_e2e_session() as session:
        _advance_to_runtime_step(session.client, session.market_home)
        _configure(session)
        response = _next_step(session.client, 6, 5, tencent_trial_enabled="on")
        assert _step(response) == "6"
        assert trial_status().enabled
        assert realtime_source() == "tencent"
        response = session.client.post("/init-wizard/complete")
        assert "请先完成历史数据下载" in response.text
        assert not init_wizard.get_state().init_completed


def test_back_from_auto_selected_realtime_returns_to_source_configuration():
    with init_wizard_e2e_session() as session, patch(
        "quantide.service.data_source_access.create_probe_client",
        return_value=AccessClient(realtime=True),
    ):
        _advance_to_runtime_step(session.client, session.market_home)
        assert _step(_configure(session)) == "6"
        response = session.client.post("/init-wizard/step/5",
                                       data={"nav": "prev", "_current_step": "6"})
        assert _step(response) == "4"
        assert "Tushare 访问密钥" in response.text
