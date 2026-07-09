import datetime
from types import SimpleNamespace

import pytest

from quantide.core.init_wizard_steps import WIZARD_TOTAL_STEPS
from quantide.data.models.app_state import AppState
from quantide.web.pages import init_wizard as init_wizard_page


class FakeRequest:
    def __init__(self, form_data, query_params=None):
        self._form_data = form_data
        self.query_params = query_params or {}

    async def form(self):
        return self._form_data


class FakePageRequest:
    def __init__(self, query_params=None):
        self.query_params = query_params or {}


class FakeInitWizard:
    def __init__(self):
        self.state = AppState(
            app_home="/existing/home",
            app_host="0.0.0.0",
            app_port=8130,
            app_prefix="/",
        )
        self.runtime_calls: list[dict[str, object]] = []
        self.gateway_calls: list[dict[str, object]] = []
        self.gateway_test_calls: list[dict[str, object]] = []
        self.data_calls: list[dict[str, object]] = []
        self.gateway_test_result = (True, "ok")
        self.updated_step: int | None = None
        self.initialization_starts: list[bool] = []
        self.complete_calls = 0

    def get_state(self, force_refresh: bool = False):
        return self.state

    def is_initialized(self):
        return self.state.init_completed

    def start_initialization(self, reset_step: bool = False):
        self.initialization_starts.append(reset_step)
        if reset_step:
            self.state.init_step = 1
        return self.state

    def save_runtime_config(self, home: str, host: str, port: int, prefix: str):
        self.runtime_calls.append(
            {
                "home": home,
                "host": host,
                "port": port,
                "prefix": prefix,
            }
        )
        self.state.app_home = home
        self.state.app_host = host
        self.state.app_port = port
        self.state.app_prefix = prefix

    def test_gateway_connection(
        self,
        server: str,
        port: int,
        prefix: str,
        api_key: str,
    ):
        self.gateway_test_calls.append(
            {
                "server": server,
                "port": port,
                "prefix": prefix,
                "api_key": api_key,
            }
        )
        return self.gateway_test_result

    def save_gateway_config(
        self,
        enabled: bool,
        server: str,
        port: int,
        prefix: str,
        api_key: str,
    ):
        self.gateway_calls.append(
            {
                "enabled": enabled,
                "server": server,
                "port": port,
                "prefix": prefix,
                "api_key": api_key,
            }
        )
        if enabled and not str(server).strip():
            raise ValueError("启用 gateway 时必须填写服务器地址")
        if enabled and not str(api_key).strip():
            raise ValueError("启用 gateway 时必须填写访问密钥")
        self.state.gateway_enabled = enabled
        self.state.gateway_server = server
        self.state.gateway_port = port
        self.state.gateway_base_url = prefix
        self.state.gateway_api_key = api_key

    def save_data_init_config(
        self,
        epoch: datetime.date,
        data_source: str,
        tushare_token: str,
        history_years: int,
    ):
        self.data_calls.append(
            {
                "epoch": epoch,
                "data_source": data_source,
                "tushare_token": tushare_token,
                "history_years": history_years,
            }
        )
        if data_source == "tushare" and not str(tushare_token).strip():
            raise ValueError("必须填写 Tushare Token")
        self.state.epoch = epoch
        self.state.data_source = data_source
        self.state.tushare_token = tushare_token
        self.state.history_years = history_years

    def update_step(self, step: int):
        self.updated_step = step
        self.state.init_step = step

    def complete_initialization(self):
        self.complete_calls += 1
        self.state.init_completed = True
        self.state.init_step = 6

    def get_completion_redirect(self):
        return "/"


@pytest.fixture(autouse=True)
def reset_init_wizard_page_state():
    init_wizard_page._sync_status = {
        "is_running": False,
        "current_task": "",
        "progress": 0,
        "stage": "",
        "message": "",
        "completed": False,
        "error": None,
    }
    init_wizard_page._set_download_error(None)
    init_wizard_page._set_reconfigure_mode(False)
    yield
    init_wizard_page._sync_status = {
        "is_running": False,
        "current_task": "",
        "progress": 0,
        "stage": "",
        "message": "",
        "completed": False,
        "error": None,
    }
    init_wizard_page._set_download_error(None)
    init_wizard_page._set_reconfigure_mode(False)


def test_runtime_form_state_uses_canonical_defaults():
    values = init_wizard_page._runtime_form_state({})

    assert values[init_wizard_page.RUNTIME_FORM_FIELDS["home"]] == "~/.quantide"
    assert values[init_wizard_page.RUNTIME_FORM_FIELDS["port"]] == 8130
    assert values[init_wizard_page.RUNTIME_FORM_FIELDS["prefix"]] == "/quantide"
    assert values[init_wizard_page.RUNTIME_FORM_FIELDS["localhost_only"]] is True


def test_gateway_form_state_reads_persisted_prefix_alias():
    values = init_wizard_page._gateway_form_state({"gateway_base_url": "/gateway"})

    assert values[init_wizard_page.GATEWAY_FORM_FIELDS["prefix"]] == "/gateway"


def test_wizard_buttons_uses_shared_total_steps():
    assert init_wizard_page.WizardButtons.__defaults__ == (WIZARD_TOTAL_STEPS,)


def test_render_wizard_main_content_uses_three_region_layout():
    html = str(init_wizard_page._render_wizard_main_content(2, {"init_step": 2}))

    assert 'id="wizard-header-region"' in html
    assert 'id="wizard-body-region"' in html
    assert 'id="wizard-footer-region"' in html
    assert html.index('id="wizard-header-region"') < html.index('id="wizard-body-region"')
    assert html.index('id="wizard-body-region"') < html.index('id="wizard-footer-region"')


@pytest.mark.asyncio
async def test_handle_step_keeps_progress_indicator_in_main_container_swap(monkeypatch):
    fake_wizard = FakeInitWizard()
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)

    response = await init_wizard_page.handle_step(
        FakeRequest(
            {
                "_current_step": "1",
                "nav": "next",
            },
            query_params={"force": "true"},
        ),
        2,
    )

    html = str(response)

    assert 'id="step-indicator-wrapper"' in html
    assert 'hx-swap-oob' not in html
    assert 'id="wizard-main-container"' not in html


@pytest.mark.asyncio
async def test_handle_step_runtime_config_uses_app_field_names(monkeypatch):
    fake_wizard = FakeInitWizard()
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)

    await init_wizard_page.handle_step(
        FakeRequest(
            {
                "_current_step": "2",
                "nav": "next",
                "app_home": "/tmp/market-data",
                "app_port": "9100",
                "app_prefix": "/quantide",
                "localhost_only": "true",
            }
        ),
        3,
    )

    assert fake_wizard.runtime_calls == [
        {
            "home": "/tmp/market-data",
            "host": "127.0.0.1",
            "port": 9100,
            "prefix": "/quantide",
        }
    ]
    assert fake_wizard.updated_step == 3


@pytest.mark.asyncio
async def test_handle_step_runtime_config_accepts_legacy_field_names(monkeypatch):
    fake_wizard = FakeInitWizard()
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)

    await init_wizard_page.handle_step(
        FakeRequest(
            {
                "_current_step": "2",
                "nav": "next",
                "home": "/tmp/legacy-home",
                "port": "9200",
                "prefix": "/legacy",
            }
        ),
        3,
    )

    assert fake_wizard.runtime_calls == [
        {
            "home": "/tmp/legacy-home",
            "host": "0.0.0.0",
            "port": 9200,
            "prefix": "/legacy",
        }
    ]
    assert fake_wizard.updated_step == 3


@pytest.mark.asyncio
async def test_handle_step_gateway_config_uses_canonical_field_names(monkeypatch):
    fake_wizard = FakeInitWizard()
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)

    await init_wizard_page.handle_step(
        FakeRequest(
            {
                "_current_step": "4",
                "nav": "next",
                "gateway_enabled": "true",
                "gateway_server": "127.0.0.1",
                "gateway_port": "8001",
                "gateway_api_key": "gateway-key",
                "gateway_prefix": "/gateway",
            }
        ),
        5,
    )

    assert fake_wizard.gateway_test_calls == [
        {
            "server": "127.0.0.1",
            "port": 8001,
            "prefix": "/gateway",
            "api_key": "gateway-key",
        }
    ]
    assert fake_wizard.gateway_calls == [
        {
            "enabled": True,
            "server": "127.0.0.1",
            "port": 8001,
            "prefix": "/gateway",
            "api_key": "gateway-key",
        }
    ]
    assert fake_wizard.updated_step == 5


@pytest.mark.asyncio
async def test_handle_step_gateway_config_uses_persisted_prefix_alias_when_omitted(monkeypatch):
    fake_wizard = FakeInitWizard()
    fake_wizard.state.gateway_server = "persisted-host"
    fake_wizard.state.gateway_port = 8002
    fake_wizard.state.gateway_base_url = "/persisted"
    fake_wizard.state.gateway_api_key = "persisted-key"
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)

    await init_wizard_page.handle_step(
        FakeRequest(
            {
                "_current_step": "4",
                "nav": "next",
            }
        ),
        5,
    )

    assert fake_wizard.gateway_test_calls == []
    assert fake_wizard.gateway_calls == [
        {
            "enabled": False,
            "server": "persisted-host",
            "port": 8002,
            "prefix": "/persisted",
            "api_key": "persisted-key",
        }
    ]
    assert fake_wizard.updated_step == 5


@pytest.mark.asyncio
async def test_step4_gateway_shows_dev_stub_runtime_notice(monkeypatch):
    monkeypatch.setattr(init_wizard_page, "dev_stubs_enabled", lambda: True)
    monkeypatch.setattr(
        init_wizard_page,
        "ensure_dev_stubs_started",
        lambda: SimpleNamespace(
            gateway_base_url="http://127.0.0.1:19001/qmt",
            gateway_server="127.0.0.1",
            gateway_port=19001,
            gateway_prefix="/qmt",
        ),
    )

    html = str(init_wizard_page.Step4_Gateway({}))

    assert "开发 Stub 模式已自动配置交易网关" in html
    assert "不会要求你手动填写地址、端口或路径前缀" in html
    assert "http://127.0.0.1:19001/qmt" in html
    assert "/qmt" in html


@pytest.mark.asyncio
async def test_handle_step_gateway_config_uses_dev_stub_runtime_when_enabled(monkeypatch):
    fake_wizard = FakeInitWizard()
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)
    monkeypatch.setattr(init_wizard_page, "dev_stubs_enabled", lambda: True)
    monkeypatch.setattr(
        init_wizard_page,
        "ensure_dev_stubs_started",
        lambda: SimpleNamespace(
            gateway_server="127.0.0.1",
            gateway_port=19001,
            gateway_prefix="/qmt",
            gateway_api_key="stub-api-key",
        ),
    )

    await init_wizard_page.handle_step(
        FakeRequest(
            {
                "_current_step": "4",
                "nav": "next",
            }
        ),
        5,
    )

    assert fake_wizard.gateway_test_calls == []
    assert fake_wizard.gateway_calls == [
        {
            "enabled": True,
            "server": "127.0.0.1",
            "port": 19001,
            "prefix": "/qmt",
            "api_key": "stub-api-key",
        }
    ]
    assert fake_wizard.updated_step == 5


@pytest.mark.asyncio
async def test_handle_step_gateway_config_requires_api_key_when_enabled(monkeypatch):
    fake_wizard = FakeInitWizard()
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)

    response = await init_wizard_page.handle_step(
        FakeRequest(
            {
                "_current_step": "4",
                "nav": "next",
                "gateway_enabled": "true",
                "gateway_server": "127.0.0.1",
                "gateway_port": "8001",
                "gateway_api_key": "   ",
                "gateway_prefix": "/gateway",
            }
        ),
        5,
    )

    html = str(response)

    assert "启用 gateway 时必须填写访问密钥" in html
    assert fake_wizard.gateway_test_calls == []
    assert fake_wizard.updated_step is None


@pytest.mark.asyncio
async def test_handle_step_data_setup_uses_canonical_field_names(monkeypatch):
    fake_wizard = FakeInitWizard()
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)

    await init_wizard_page.handle_step(
        FakeRequest(
            {
                "_current_step": "5",
                "nav": "next",
                "epoch": "2024-01-01",
                "data_source": "tushare",
                "tushare_token": "ts-token",
                "history_years": "3",
            }
        ),
        6,
    )

    assert fake_wizard.data_calls == [
        {
            "epoch": datetime.date(2024, 1, 1),
            "data_source": "tushare",
            "tushare_token": "ts-token",
            "history_years": 3,
        }
    ]
    assert fake_wizard.updated_step == 6


@pytest.mark.asyncio
async def test_handle_step_data_setup_requires_tushare_token(monkeypatch):
    fake_wizard = FakeInitWizard()
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)

    response = await init_wizard_page.handle_step(
        FakeRequest(
            {
                "_current_step": "5",
                "nav": "next",
                "epoch": "2024-01-01",
                "data_source": "tushare",
                "tushare_token": "   ",
                "history_years": "3",
            }
        ),
        6,
    )

    html = str(response)

    assert "必须填写 Tushare Token" in html
    assert fake_wizard.updated_step is None


@pytest.mark.asyncio
async def test_step5_data_setup_shows_dev_stub_sample_import_notice(monkeypatch):
    monkeypatch.setattr(init_wizard_page, "dev_stubs_enabled", lambda: True)

    html = str(init_wizard_page.Step5_DataSetup({"app_home": "/tmp/dev-stub-home"}))

    assert "当前进程已启用开发 Stub 模式" in html
    assert "不会访问真实 Tushare" in html
    assert "Tushare 访问密钥" not in html
    assert "首次下载时长" not in html
    assert "/tmp/dev-stub-home" in html


def test_wizard_buttons_step_five_uses_direct_next_in_dev_stub(monkeypatch):
    monkeypatch.setattr(init_wizard_page, "dev_stubs_enabled", lambda: True)

    html = str(init_wizard_page.WizardButtons(5))

    assert "/init-wizard/step/6" in html
    assert "/init-wizard/download" not in html


@pytest.mark.asyncio
async def test_handle_step_data_setup_uses_dev_stub_token_and_imports_samples(monkeypatch):
    fake_wizard = FakeInitWizard()
    fake_wizard.state.epoch = datetime.date(2024, 1, 1)
    fake_wizard.state.history_years = 1
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)
    monkeypatch.setattr(init_wizard_page, "dev_stubs_enabled", lambda: True)

    imported = []
    monkeypatch.setattr(
        init_wizard_page,
        "_prepare_dev_stub_sample_data",
        lambda state: imported.append(state.app_home),
    )

    response = await init_wizard_page.handle_step(
        FakeRequest(
            {
                "_current_step": "5",
                "nav": "next",
            }
        ),
        6,
    )

    html = str(response)

    assert fake_wizard.data_calls == [
        {
            "epoch": datetime.date(2024, 1, 1),
            "data_source": "tushare",
            "tushare_token": init_wizard_page.DEV_STUB_TUSHARE_TOKEN,
            "history_years": 1,
        }
    ]
    assert imported == ["/existing/home"]
    assert fake_wizard.updated_step == 6
    assert "配置已保存，您可以立即进入系统开始使用。" in html


@pytest.mark.asyncio
async def test_handle_download_skips_progress_dialog_in_dev_stub(monkeypatch):
    fake_wizard = FakeInitWizard()
    fake_wizard.state.epoch = datetime.date(2024, 1, 1)
    fake_wizard.state.history_years = 1
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)
    monkeypatch.setattr(init_wizard_page, "dev_stubs_enabled", lambda: True)

    imported = []
    monkeypatch.setattr(
        init_wizard_page,
        "_prepare_dev_stub_sample_data",
        lambda state: imported.append(state.app_home),
    )

    response = await init_wizard_page.handle_download(FakeRequest({}))
    html = str(response)

    assert imported == ["/existing/home"]
    assert fake_wizard.data_calls == [
        {
            "epoch": datetime.date(2024, 1, 1),
            "data_source": "tushare",
            "tushare_token": init_wizard_page.DEV_STUB_TUSHARE_TOKEN,
            "history_years": 1,
        }
    ]
    assert fake_wizard.updated_step == 6
    assert "sync-progress-bar" not in html
    assert "/init-wizard/sync-progress" not in html


@pytest.mark.asyncio
async def test_run_data_sync_failure_persists_error_to_step_five_header(monkeypatch):
    fake_wizard = FakeInitWizard()
    fake_wizard.state.app_home = "/tmp/market-data"
    fake_wizard.state.data_source = "tushare"
    fake_wizard.state.tushare_token = "ts-token"
    fake_wizard.state.epoch = datetime.date(2024, 1, 1)
    fake_wizard.state.history_start_date = datetime.date(2023, 1, 1)
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)
    monkeypatch.setattr(init_wizard_page.calendar, "update", lambda: None)
    monkeypatch.setattr(
        init_wizard_page.calendar,
        "last_trade_date",
        lambda: datetime.date(2024, 12, 31),
    )
    monkeypatch.setattr(init_wizard_page.stock_list, "update", lambda *a, **kw: None)
    def _failing_fetch(*a, **kw):
        raise RuntimeError("network broken")
    monkeypatch.setattr(init_wizard_page.daily_bars, "fetch_with_daily_progress", _failing_fetch)
    monkeypatch.setattr("quantide.data.init_data", lambda home, init_db=True: None)
    monkeypatch.setattr(init_wizard_page.msg_hub, "subscribe", lambda *args, **kwargs: None)
    monkeypatch.setattr(init_wizard_page.msg_hub, "unsubscribe", lambda *args, **kwargs: None)

    await init_wizard_page._run_data_sync(fake_wizard.state.history_start_date)

    html = str(
        init_wizard_page._render_wizard_main_content(
            5,
            fake_wizard.state.to_dict(),
            step_content=init_wizard_page.Step5_DataSetup(fake_wizard.state.to_dict()),
            current_step_value=5,
        )
    )

    assert init_wizard_page._sync_status["error"] == "network broken"
    assert "下载失败：network broken" in html


@pytest.mark.asyncio
async def test_run_data_sync_clamps_future_start_to_calendar_end(monkeypatch):
    fake_wizard = FakeInitWizard()
    fake_wizard.state.app_home = "/tmp/market-data"
    fake_wizard.state.data_source = "tushare"
    fake_wizard.state.tushare_token = "ts-token"
    fake_wizard.state.epoch = datetime.date(2005, 1, 1)
    fake_wizard.state.history_start_date = datetime.date(2025, 5, 15)
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)
    monkeypatch.setattr(init_wizard_page.calendar, "update", lambda: None)
    monkeypatch.setattr(
        init_wizard_page.calendar,
        "last_trade_date",
        lambda: datetime.date(2024, 12, 31),
    )
    monkeypatch.setattr(init_wizard_page.stock_list, "update", lambda *a, **kw: None)
    observed: dict[str, datetime.date] = {}

    def _recording_fetch(start, end, progress_callback=None, force=False):
        observed["start"] = start
        observed["end"] = end
        return 1
    monkeypatch.setattr(init_wizard_page.daily_bars, "fetch_with_daily_progress", _recording_fetch)
    monkeypatch.setattr("quantide.data.init_data", lambda home, init_db=True: None)
    monkeypatch.setattr(init_wizard_page.msg_hub, "subscribe", lambda *args, **kwargs: None)
    monkeypatch.setattr(init_wizard_page.msg_hub, "unsubscribe", lambda *args, **kwargs: None)

    await init_wizard_page._run_data_sync(fake_wizard.state.history_start_date)

    assert observed == {
        "start": datetime.date(2024, 12, 31),
        "end": datetime.date(2024, 12, 31),
    }
    assert fake_wizard.complete_calls == 1
    assert init_wizard_page._sync_status["completed"] is True
    assert init_wizard_page._sync_status["error"] is None


@pytest.mark.asyncio
async def test_handle_download_clears_stale_header_error_before_retry(monkeypatch):
    fake_wizard = FakeInitWizard()
    fake_wizard.state.tushare_token = "persisted-token"
    fake_wizard.state.epoch = datetime.date(2024, 1, 1)
    fake_wizard.state.history_years = 3
    fake_wizard.state.history_start_date = datetime.date(2021, 1, 1)
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)

    def fake_create_task(coro):
        coro.close()
        return None

    init_wizard_page._set_download_error("下载失败：old error")
    monkeypatch.setattr(init_wizard_page.asyncio, "create_task", fake_create_task)

    response = await init_wizard_page.handle_download(
        FakeRequest(
            {
                "epoch": "2024-01-01",
                "data_source": "tushare",
                "tushare_token": "ts-token",
                "history_years": "3",
            }
        )
    )

    html = str(response)

    assert "下载失败：old error" not in html
    assert "sync-return-button" in html


@pytest.mark.asyncio
async def test_force_reconfigure_keeps_query_and_prefills_saved_values(monkeypatch):
    fake_wizard = FakeInitWizard()
    fake_wizard.state.init_completed = True
    fake_wizard.state.app_home = "/persisted/home"
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)

    await init_wizard_page.get(FakePageRequest({"force": "true"}))
    landing_html = str(init_wizard_page._render_wizard_main_content(1, fake_wizard.state.to_dict()))

    response = await init_wizard_page.handle_step(
        FakeRequest(
            {
                "_current_step": "1",
                "nav": "next",
            },
            query_params={"force": "true"},
        ),
        2,
    )
    html = str(response)

    assert fake_wizard.initialization_starts == [True]
    assert "/init-wizard/step/2?force=true" in landing_html
    assert "/init-wizard/step/3?force=true" in html
    assert "/persisted/home" in html


@pytest.mark.asyncio
async def test_handle_complete_redirects_to_root(monkeypatch):
    fake_wizard = FakeInitWizard()
    monkeypatch.setattr(init_wizard_page, "init_wizard", fake_wizard)
    monkeypatch.setattr(init_wizard_page, "_bootstrap_runtime_for_initialized_app", lambda app: None)

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(root_app=None, runtime=None)))

    response = await init_wizard_page.handle_complete(request)
    html = str(response)

    assert fake_wizard.complete_calls == 1
    assert "window.location.href = '/'" in html
