"""Init wizard."""

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    FT,
    Div,
    P,
    RedirectResponse,
    Request,
    Script,
    Span,
)
from loguru import logger
from monsterui.all import *
from starlette.applications import Starlette
from starlette.responses import StreamingResponse

from quantide.config.dev_stubs import (
    DEV_STUB_TUSHARE_TOKEN,
    dev_stubs_enabled,
    ensure_dev_stubs_started,
)
from quantide.config.features import supports_live_trading
from quantide.config.paths import normalize_data_home
from quantide.config.realtime_source import configure_realtime_source, realtime_source
from quantide.config.tencent_trial import configure_trial
from quantide.data.models.app_state import AppState
from quantide.data.models.calendar import calendar
from quantide.data.models.daily_bars import daily_bars
from quantide.data.models.stocks import stock_list
from quantide.service.data_source_access import ensure_access_report, load_access_report
from quantide.service.init_wizard import init_wizard
from quantide.web.pages import wizard_state
from quantide.web.pages.wizard_components import (
    FormHint as FormHint,
)
from quantide.web.pages.wizard_components import (
    FormLabel as FormLabel,
)
from quantide.web.pages.wizard_components import (
    FormRow as FormRow,
)
from quantide.web.pages.wizard_components import (
    InfoTooltip as InfoTooltip,
)
from quantide.web.pages.wizard_components import (
    RequiredMark as RequiredMark,
)
from quantide.web.pages.wizard_components import (
    SectionDescription as SectionDescription,
)
from quantide.web.pages.wizard_components import (
    SectionTitle as SectionTitle,
)
from quantide.web.pages.wizard_components import (
    StepIndicator as StepIndicator,
)
from quantide.web.pages.wizard_components import (
    _get_step_meta as _get_step_meta,
)
from quantide.web.pages.wizard_components import (
    _render_inline_error as _render_inline_error,
)
from quantide.web.pages.wizard_components import (
    _wizard_step_meta as _wizard_step_meta,
)
from quantide.web.pages.wizard_forms import (
    _coerce_checkbox as _coerce_checkbox,
)
from quantide.web.pages.wizard_forms import (
    _data_init_form_state as _data_init_form_state,
)
from quantide.web.pages.wizard_forms import (
    _extract_form_updates,
    _gateway_form_state,
    _merge_state,
    _parse_epoch_input,
    _parse_int_input,
    _parse_positive_int_input,
)
from quantide.web.pages.wizard_forms import (
    _format_date_zh as _format_date_zh,
)
from quantide.web.pages.wizard_forms import (
    _normalize_form_values as _normalize_form_values,
)
from quantide.web.pages.wizard_forms import (
    _pick_first_value as _pick_first_value,
)
from quantide.web.pages.wizard_forms import (
    _runtime_form_state as _runtime_form_state,
)
from quantide.web.pages.wizard_layout import (
    InitWizardPage,
    SyncProgressDialog,
    _render_wizard_main_content,
)
from quantide.web.pages.wizard_layout import (
    WizardButtons as WizardButtons,
)
from quantide.web.pages.wizard_layout import (
    _build_step_content as _build_step_content,
)
from quantide.web.pages.wizard_layout import (
    _build_step_progress as _build_step_progress,
)
from quantide.web.pages.wizard_layout import (
    _render_wizard_body as _render_wizard_body,
)
from quantide.web.pages.wizard_layout import (
    _render_wizard_footer as _render_wizard_footer,
)
from quantide.web.pages.wizard_layout import (
    _render_wizard_form as _render_wizard_form,
)
from quantide.web.pages.wizard_layout import (
    _render_wizard_header as _render_wizard_header,
)
from quantide.web.pages.wizard_state import (
    ADMIN_FORM_FIELDS,
    DATA_INIT_FIELD_ALIASES,
    DATA_INIT_FORM_FIELDS,
    GATEWAY_FIELD_ALIASES,
    GATEWAY_FORM_FIELDS,
    RUNTIME_FIELD_ALIASES,
    RUNTIME_FORM_FIELDS,
    _request_in_force_mode,
    _set_download_error,
    _set_reconfigure_mode,
    rt,
)
from quantide.web.pages.wizard_state import (
    DATA_INIT_DEFAULTS as DATA_INIT_DEFAULTS,
)
from quantide.web.pages.wizard_state import (
    FONT_STYLES as FONT_STYLES,
)
from quantide.web.pages.wizard_state import (
    GATEWAY_DEFAULTS as GATEWAY_DEFAULTS,
)
from quantide.web.pages.wizard_state import (
    PRIMARY_COLOR as PRIMARY_COLOR,
)
from quantide.web.pages.wizard_state import (
    RUNTIME_DEFAULTS as RUNTIME_DEFAULTS,
)
from quantide.web.pages.wizard_state import (
    WIZARD_BODY_INNER_STYLE as WIZARD_BODY_INNER_STYLE,
)
from quantide.web.pages.wizard_state import (
    WIZARD_PANEL_STYLE as WIZARD_PANEL_STYLE,
)
from quantide.web.pages.wizard_state import (
    WIZARD_STEP_WRAPPER_STYLE as WIZARD_STEP_WRAPPER_STYLE,
)
from quantide.web.pages.wizard_state import (
    _download_error_message as _download_error_message,
)
from quantide.web.pages.wizard_state import (
    _get_download_error as _get_download_error,
)
from quantide.web.pages.wizard_state import (
    _reconfigure_mode_active as _reconfigure_mode_active,
)
from quantide.web.pages.wizard_state import (
    _update_sync_status as _update_sync_status,
)
from quantide.web.pages.wizard_state import (
    _with_force_query as _with_force_query,
)
from quantide.web.pages.wizard_state import (
    init_wizard_app as init_wizard_app,
)
from quantide.web.pages.wizard_step_views import (
    Step1_Welcome as Step1_Welcome,
)
from quantide.web.pages.wizard_step_views import (
    Step2_Runtime,
    Step3_Admin,
    Step4_Gateway,
    Step5_DataSetup,
    _render_download_range_info,
)
from quantide.web.pages.wizard_step_views import (
    Step6_Complete as Step6_Complete,
)
from quantide.web.pages.wizard_step_views import (
    _calculate_download_range as _calculate_download_range,
)
from quantide.web.pages.wizard_step_views import (
    _check_password_strength as _check_password_strength,
)
from quantide.web.pages.wizard_sync import (
    start_wizard_sync,
)

"""应用程序初始化向导页面

使用 MonsterUI 实现多步骤初始化向导。
"""


@rt("/")
async def get(request: Request) -> FT | RedirectResponse:
    """初始化向导主页"""
    session = getattr(request, "scope", {}).get("session")
    if isinstance(session, dict):
        session["initializing"] = True
    force = _request_in_force_mode(request)
    _set_reconfigure_mode(force)

    if not force:
        try:
            is_init = init_wizard.is_initialized()
            if is_init:
                return RedirectResponse("/")
        except RuntimeError as e:
            logger.warning(f"检查初始化状态时出错：{e}")

    try:
        init_wizard.start_initialization(reset_step=True)
    except RuntimeError as e:
        logger.warning(f"开始初始化流程时出错：{e}")

    state = init_wizard.get_state(force_refresh=True)
    return InitWizardPage(step=1, form_data=state.to_dict())


async def _save_runtime_step(form_dict: Mapping[str, object], step: int) -> FT | None:
    """Validate and save wizard step 2, returning its error view when necessary."""
    state = init_wizard.get_state(force_refresh=True)
    state_dict = _merge_state(
        state.to_dict(), _extract_form_updates(form_dict, RUNTIME_FIELD_ALIASES)
    )
    state_dict[RUNTIME_FORM_FIELDS["localhost_only"]] = (
        RUNTIME_FORM_FIELDS["localhost_only"] in form_dict
    )
    state_dict[RUNTIME_FORM_FIELDS["host"]] = (
        "127.0.0.1" if state_dict[RUNTIME_FORM_FIELDS["localhost_only"]] else "0.0.0.0"
    )
    try:
        init_wizard.save_runtime_config(
            home=str(state_dict[RUNTIME_FORM_FIELDS["home"]]).strip(),
            host=str(state_dict[RUNTIME_FORM_FIELDS["host"]]).strip(),
            port=_parse_int_input(
                state_dict[RUNTIME_FORM_FIELDS["port"]],
                "监听端口",
                8130,
            ),
            prefix=str(state_dict[RUNTIME_FORM_FIELDS["prefix"]]).strip(),
        )
    except Exception as e:
        state = init_wizard.get_state(force_refresh=True)
        state_dict = state.to_dict()
        return _render_wizard_main_content(
            2,
            state_dict,
            step_content=Step2_Runtime(state_dict),
            current_step_value=2,
            error_message=str(e),
        )
    return None


async def _save_admin_step(form_dict: Mapping[str, object], step: int) -> FT | None:
    """Validate and save wizard step 3, returning its error view when necessary."""
    password = str(form_dict.get(ADMIN_FORM_FIELDS["password"], "")).strip()
    confirm = str(form_dict.get(ADMIN_FORM_FIELDS["confirm"], "")).strip()
    state = init_wizard.get_state(force_refresh=True)
    state_dict = state.to_dict()
    state_dict[ADMIN_FORM_FIELDS["password"]] = password
    state_dict[ADMIN_FORM_FIELDS["confirm"]] = confirm
    if password != confirm:
        return _render_wizard_main_content(
            3,
            state_dict,
            step_content=Step3_Admin(state_dict),
            current_step_value=3,
            error_message="两次输入的管理员密码不一致",
        )
    try:
        init_wizard.save_admin_password(password)
    except Exception as e:
        return _render_wizard_main_content(
            3,
            state_dict,
            step_content=Step3_Admin(state_dict),
            current_step_value=3,
            error_message=str(e),
        )
    return None


async def _save_gateway_step(form_dict: Mapping[str, object], step: int) -> FT | None:
    """Apply the fixed demo window and the edition-specific gateway configuration."""
    try:
        _configure_wizard_realtime(form_dict)
    except ValueError as exc:
        state = init_wizard.get_state(force_refresh=True).to_dict()
        return _render_wizard_main_content(
            5,
            state,
            step_content=Step4_Gateway(state),
            current_step_value=5,
            error_message=str(exc),
        )
    if not supports_live_trading():
        _disable_ce_gateway()
        return None
    if dev_stubs_enabled():
        return _save_stub_gateway()
    return _save_custom_gateway(form_dict)


def _disable_ce_gateway() -> None:
    state = init_wizard.get_state(force_refresh=True)
    state.gateway_enabled = False
    state.gateway_server = ""
    state.gateway_base_url = "/"
    state.gateway_api_key = ""
    init_wizard.save_state(state)


def _save_stub_gateway() -> FT | None:
    runtime = ensure_dev_stubs_started()
    if runtime is None:
        state = init_wizard.get_state(force_refresh=True)
        state_dict = state.to_dict()
        return _render_wizard_main_content(
            5,
            state_dict,
            step_content=Step4_Gateway(state_dict),
            current_step_value=5,
            error_message="开发 Stub gateway 尚未就绪，请重新启动应用后再试。",
        )
    try:
        init_wizard.save_gateway_config(
            enabled=True,
            server=runtime.gateway_server,
            port=runtime.gateway_port,
            prefix=runtime.gateway_prefix,
            api_key=runtime.gateway_api_key,
        )
    except Exception as e:
        state = init_wizard.get_state(force_refresh=True)
        state_dict = state.to_dict()
        return _render_wizard_main_content(
            5,
            state_dict,
            step_content=Step4_Gateway(state_dict),
            current_step_value=5,
            error_message=str(e),
        )
    return None


def _save_custom_gateway(form_dict: Mapping[str, object]) -> FT | None:
    state = init_wizard.get_state(force_refresh=True)
    state_dict = _merge_state(
        _gateway_form_state(state.to_dict()),
        _extract_form_updates(form_dict, GATEWAY_FIELD_ALIASES),
    )
    state_dict[GATEWAY_FORM_FIELDS["enabled"]] = GATEWAY_FORM_FIELDS["enabled"] in form_dict
    enabled = bool(state_dict[GATEWAY_FORM_FIELDS["enabled"]])
    server = str(state_dict[GATEWAY_FORM_FIELDS["server"]]).strip()
    prefix = str(state_dict[GATEWAY_FORM_FIELDS["prefix"]]).strip() or "/"
    api_key = str(state_dict[GATEWAY_FORM_FIELDS["api_key"]]).strip()
    try:
        port = _parse_int_input(
            state_dict[GATEWAY_FORM_FIELDS["port"]],
            "网关端口",
            8000,
        )
    except ValueError as e:
        return _render_wizard_main_content(
            5,
            state_dict,
            step_content=Step4_Gateway(state_dict),
            current_step_value=5,
            error_message=str(e),
        )

    if enabled and not server:
        return _render_wizard_main_content(
            5,
            state_dict,
            step_content=Step4_Gateway(state_dict),
            current_step_value=5,
            error_message="启用 gateway 时必须填写服务器地址",
        )
    if enabled and not api_key:
        return _render_wizard_main_content(
            5,
            state_dict,
            step_content=Step4_Gateway(state_dict),
            current_step_value=5,
            error_message="启用 gateway 时必须填写访问密钥",
        )

    if enabled:
        ok, msg = init_wizard.test_gateway_connection(
            server=server, port=port, prefix=prefix, api_key=api_key
        )
        if not ok:
            state_dict[GATEWAY_FORM_FIELDS["enabled"]] = enabled
            state_dict[GATEWAY_FORM_FIELDS["server"]] = server
            state_dict[GATEWAY_FORM_FIELDS["port"]] = port
            state_dict[GATEWAY_FORM_FIELDS["prefix"]] = prefix
            state_dict[GATEWAY_FORM_FIELDS["api_key"]] = api_key
            return _render_wizard_main_content(
                5,
                state_dict,
                step_content=Step4_Gateway(state_dict),
                current_step_value=5,
                error_message=f"{msg}",
            )

    try:
        init_wizard.save_gateway_config(
            enabled=enabled,
            server=server,
            port=port,
            prefix=prefix,
            api_key=api_key,
        )
    except Exception as e:
        return _render_wizard_main_content(
            5,
            state_dict,
            step_content=Step4_Gateway(state_dict),
            current_step_value=5,
            error_message=str(e),
        )
    return None


async def _save_history_step(form_dict: Mapping[str, object], step: int) -> FT | None:
    """Validate and save the historical source before any bulk download."""
    state = init_wizard.get_state(force_refresh=True)
    state_dict = _merge_state(
        state.to_dict(), _extract_form_updates(form_dict, DATA_INIT_FIELD_ALIASES)
    )
    epoch_str = str(state_dict[DATA_INIT_FORM_FIELDS["epoch"]]).strip()
    try:
        epoch = _parse_epoch_input(epoch_str)
        history_years = (
            1
            if dev_stubs_enabled()
            else _parse_positive_int_input(
                state_dict[DATA_INIT_FORM_FIELDS["history_years"]],
                "首次下载时长",
                1,
            )
        )
    except ValueError as e:
        step_content = Step5_DataSetup(state_dict)
        return _render_wizard_main_content(
            4,
            state_dict,
            step_content=step_content,
            current_step_value=4,
            error_message=str(e),
        )
    if dev_stubs_enabled():
        try:
            if not supports_live_trading():
                _disable_ce_gateway()
            init_wizard.save_data_init_config(
                epoch=epoch,
                data_source="tushare",
                tushare_token=DEV_STUB_TUSHARE_TOKEN,
                history_years=history_years,
            )
            state = init_wizard.get_state(force_refresh=True)
            await asyncio.to_thread(_prepare_dev_stub_sample_data, state)
        except Exception as e:
            step_content = Step5_DataSetup(state_dict)
            return _render_wizard_main_content(
                4,
                state_dict,
                step_content=step_content,
                current_step_value=4,
                error_message=str(e),
            )
        init_wizard.update_step(6)
        state = init_wizard.get_state(force_refresh=True)
        state_dict = state.to_dict()
        return _render_wizard_main_content(6, state_dict, current_step_value=6)

    data_source = str(state_dict[DATA_INIT_FORM_FIELDS["data_source"]]).strip().lower() or "tushare"
    token = str(state_dict[DATA_INIT_FORM_FIELDS["tushare_token"]]).strip()
    if data_source == "tushare" and not token:
        step_content = Step5_DataSetup(state_dict)
        return _render_wizard_main_content(
            4,
            state_dict,
            step_content=step_content,
            current_step_value=4,
            error_message="必须填写 Tushare Token",
        )
    try:
        init_wizard.save_data_init_config(
            epoch=epoch,
            data_source=data_source,
            tushare_token=token,
            history_years=history_years,
        )
    except Exception as e:
        step_content = Step5_DataSetup(state_dict)
        return _render_wizard_main_content(
            4,
            state_dict,
            step_content=step_content,
            current_step_value=4,
            error_message=str(e),
        )
    if not supports_live_trading():
        _disable_ce_gateway()
    return await _check_configured_data_source(force=True)


def _configure_wizard_realtime(form: Mapping[str, object]) -> None:
    state = init_wizard.get_state(force_refresh=True)
    report = load_access_report(state)
    if not dev_stubs_enabled() and not supports_live_trading():
        if not report or not report.get("history_ready"):
            raise ValueError("请先完成数据源配置和历史数据权限检查。")
    if report and report.get("realtime_ready"):
        configure_trial(False)
        configure_realtime_source("tushare")
        return
    demo = str(form.get("tencent_trial_enabled", "")) == "on"
    extension = str(form.get("use_quote_extension", "")) == "on"
    if demo and extension:
        raise ValueError("腾讯演示与自定义行情扩展请选择一项。")
    configure_trial(demo)
    configure_realtime_source("tencent" if demo else ("extension" if extension else "none"))


def _source_check_error(state: AppState, message: str) -> FT:
    init_wizard.update_step(4)
    values = state.to_dict()
    return _render_wizard_main_content(
        4, values, step_content=Step5_DataSetup(values), current_step_value=4, error_message=message
    )


async def _check_configured_data_source(*, force: bool = False) -> FT | None:
    state = init_wizard.get_state(force_refresh=True)
    try:
        report = await asyncio.to_thread(ensure_access_report, state, force=force)
    except Exception:
        return _source_check_error(state, "数据源检测未完成，请检查配置和网络后重试。")
    if not report["history_ready"]:
        return _source_check_error(
            state, "历史数据所需接口尚未全部通过检测，请查看下方结果并处理后重试。"
        )
    if report["realtime_ready"]:
        configure_trial(False)
        configure_realtime_source("tushare")
        if not supports_live_trading():
            init_wizard.update_step(6)
            return _render_wizard_main_content(6, state.to_dict(), current_step_value=6)
    return None


async def _validate_download_source(state: AppState) -> FT | None:
    result = await _check_configured_data_source()
    report = load_access_report(state)
    if not report or not report.get("history_ready"):
        return result
    selected = realtime_source()
    needs_choice = not selected or (selected == "tushare" and not report.get("realtime_ready"))
    if needs_choice and not supports_live_trading():
        init_wizard.update_step(5)
        return _render_wizard_main_content(
            5,
            state.to_dict(),
            current_step_value=5,
            error_message="请先选择实时行情方案，也可以暂不启用。",
        )
    return None


def _download_progress_view(state: AppState) -> FT:
    return _render_wizard_main_content(
        6, state.to_dict(), current_step_value=6, extra_nodes=(SyncProgressDialog(),)
    )


@rt("/step/{step}")
async def handle_step(request: Request, step: int) -> Any:
    """处理步骤导航"""
    _set_reconfigure_mode(_request_in_force_mode(request))
    form_data = await request.form()
    form_dict = dict(form_data)
    nav = str(form_dict.get("nav", "next")).lower()
    current_step = int(str(form_dict.get("_current_step", step)).strip() or step)

    if nav == "prev" and step == 5 and not supports_live_trading():
        report = load_access_report(init_wizard.get_state())
        if report and report.get("realtime_ready"):
            step = 4

    if nav != "prev":
        handlers = {
            2: _save_runtime_step,
            3: _save_admin_step,
            4: _save_history_step,
            5: _save_gateway_step,
        }
        handler = handlers.get(current_step)
        if handler is not None:
            result = await handler(form_dict, step)
            if result is not None:
                return result

    init_wizard.update_step(step)
    state = init_wizard.get_state(force_refresh=True)
    state_dict = state.to_dict()
    return _render_wizard_main_content(step, state_dict, current_step_value=step)


@rt("/gateway-test")
async def gateway_test(request: Request) -> Any:
    """网关连通性测试"""
    _set_reconfigure_mode(_request_in_force_mode(request))
    if dev_stubs_enabled():
        runtime = ensure_dev_stubs_started()
        gateway_url = getattr(runtime, "gateway_base_url", "") if runtime is not None else ""
        return Div(
            Span("ℹ️", cls="mr-2"),
            Span(f"开发 Stub 模式下已自动启用 gateway：{gateway_url or '未初始化'}。"),
            cls="text-sm text-[#e41815] mt-2 flex items-center",
        )
    form_data = await request.form()
    form_dict = dict(form_data)
    values = _merge_state(
        _gateway_form_state({}),
        _extract_form_updates(form_dict, GATEWAY_FIELD_ALIASES),
    )
    values[GATEWAY_FORM_FIELDS["enabled"]] = GATEWAY_FORM_FIELDS["enabled"] in form_dict
    if not values[GATEWAY_FORM_FIELDS["enabled"]]:
        return Div(
            Span("ℹ️", cls="mr-2"),
            Span("未启用 gateway，已禁用连通性测试。"),
            cls="text-sm text-gray-500 mt-2 flex items-center",
        )
    server = str(values[GATEWAY_FORM_FIELDS["server"]]).strip()
    prefix = str(values[GATEWAY_FORM_FIELDS["prefix"]]).strip() or "/"
    try:
        port = _parse_int_input(values[GATEWAY_FORM_FIELDS["port"]], "网关端口", 8000)
    except ValueError as e:
        return Div(
            Span("❌", cls="mr-2"),
            Span(str(e)),
            cls="text-sm text-red-600 mt-2 flex items-center",
        )
    ok, msg = init_wizard.test_gateway_connection(
        server=server,
        port=port,
        prefix=prefix,
        api_key=str(values.get(GATEWAY_FORM_FIELDS["api_key"], "") or ""),
    )
    if ok:
        return Div(
            Span("✅", cls="mr-2"),
            Span("连通性测试正确：", cls="font-semibold mr-1"),
            Span(msg),
            cls="text-sm text-green-600 mt-2 flex items-center",
        )
    return Div(
        Span("❌", cls="mr-2"),
        Span(msg),
        cls="text-sm text-red-600 mt-2 flex items-center",
    )


def _prepare_dev_stub_sample_data(state: AppState) -> None:
    """Import local fixture-backed sample data for dev-stub initialization."""
    from quantide.data import init_data

    home = normalize_data_home(getattr(state, "app_home", ""))
    init_data(home, init_db=True)

    calendar.update()
    stock_list.update()

    sync_end = calendar.last_trade_date()
    sync_start = getattr(state, "epoch", None) or sync_end
    if sync_start > sync_end:
        sync_start = sync_end
    daily_bars.fetch_with_daily_progress(sync_start, sync_end)


def _bootstrap_runtime_for_initialized_app(app: Starlette) -> None:
    """Bootstrap the effective runtime into the current app after init completes."""
    from quantide.app_factory import _attach_runtime_to_app_states
    from quantide.config.settings import get_data_home
    from quantide.core.runtime import RuntimeBootstrap
    from quantide.data import init_data
    from quantide.service.strategy_runtime import strategy_runtime_manager

    root_app = getattr(getattr(app, "state", None), "root_app", None) or app
    if getattr(root_app.state, "runtime", None) is not None:
        return

    init_data(get_data_home(), init_db=False)
    runtime = RuntimeBootstrap().bootstrap()
    strategy_runtime_manager.bootstrap_from_runtime(runtime)
    root_app.state.runtime = runtime
    root_app.state.strategy_runtime_manager = strategy_runtime_manager
    _attach_runtime_to_app_states(runtime)


@rt("/update-download-range")
async def handle_update_download_range(request: Request) -> Any:
    """更新下载范围显示"""
    _set_reconfigure_mode(_request_in_force_mode(request))
    form_data = await request.form()
    years_raw = str(form_data.get(DATA_INIT_FORM_FIELDS["history_years"], "1")).strip()
    try:
        years = _parse_positive_int_input(years_raw, "首次下载时长", 1)
    except ValueError:
        years = 1
    return _render_download_range_info(years)


@rt("/download")
async def handle_download(request: Request) -> Any:
    """开始下载初始化数据"""
    _set_reconfigure_mode(_request_in_force_mode(request))
    form_dict = dict(await request.form())
    state = init_wizard.get_state(force_refresh=True)
    state_dict = _merge_state(
        state.to_dict(), _extract_form_updates(form_dict, DATA_INIT_FIELD_ALIASES)
    )
    if dev_stubs_enabled():
        epoch_str = str(state_dict[DATA_INIT_FORM_FIELDS["epoch"]]).strip()
        try:
            epoch = _parse_epoch_input(epoch_str) if epoch_str else state.epoch
            history_years = 1
            init_wizard.save_data_init_config(
                epoch=epoch,
                data_source="tushare",
                tushare_token=DEV_STUB_TUSHARE_TOKEN,
                history_years=history_years,
            )
            state = init_wizard.get_state(force_refresh=True)
            await asyncio.to_thread(_prepare_dev_stub_sample_data, state)
            init_wizard.update_step(6)
            state = init_wizard.get_state(force_refresh=True)
        except Exception as e:
            step_content = Step5_DataSetup(state_dict)
            return _render_wizard_main_content(
                4,
                state_dict,
                step_content=step_content,
                current_step_value=4,
                error_message=f"导入开发 Stub 样本失败：{e}",
            )
        return _render_wizard_main_content(6, state.to_dict(), current_step_value=6)

    epoch_str = str(state_dict[DATA_INIT_FORM_FIELDS["epoch"]]).strip()
    data_source = (
        str(state_dict[DATA_INIT_FORM_FIELDS["data_source"]]).strip().lower() or state.data_source
    )
    token_str = str(state_dict[DATA_INIT_FORM_FIELDS["tushare_token"]]).strip()
    years_raw = str(state_dict[DATA_INIT_FORM_FIELDS["history_years"]]).strip()
    if epoch_str or data_source or token_str or years_raw:
        try:
            epoch = _parse_epoch_input(epoch_str) if epoch_str else state.epoch
            years = _parse_positive_int_input(years_raw, "首次下载时长", state.history_years)
            token = token_str or state.tushare_token
            init_wizard.save_data_init_config(
                epoch=epoch,
                data_source=data_source,
                tushare_token=token,
                history_years=years,
            )
            state = init_wizard.get_state(force_refresh=True)
        except Exception as e:
            step_content = Step5_DataSetup(state_dict)
            return _render_wizard_main_content(
                4,
                state_dict,
                step_content=step_content,
                current_step_value=4,
                error_message=f"下载前参数校验失败：{e}",
            )

    error = await _validate_download_source(state)
    if error is not None:
        return error
    if wizard_state._sync_status.get("is_running"):
        return _download_progress_view(state)
    init_wizard.update_step(6)
    state = init_wizard.get_state(force_refresh=True)
    _set_download_error(None)

    wizard_state._sync_status.clear()
    wizard_state._sync_status.update(
        {
            "is_running": True,
            "current_task": "",
            "progress": 0,
            "stage": "正在初始化",
            "message": "正在初始化...",
            "completed": False,
            "error": None,
        }
    )

    start_wizard_sync(state.history_start_date)
    logger.info(f"开始下载历史数据，起始日期: {state.history_start_date}")

    return _download_progress_view(state)


@rt("/complete")
async def handle_complete(request: Request) -> Any:
    """完成初始化并跳转目标菜单"""
    try:
        if not dev_stubs_enabled() and not init_wizard.get_state().init_completed:
            return _render_wizard_main_content(
                6,
                init_wizard.get_state().to_dict(),
                error_message="请先完成历史数据下载，再进入系统。",
            )
        init_wizard.complete_initialization()
        _bootstrap_runtime_for_initialized_app(request.app)
        target = init_wizard.get_completion_redirect()
        _set_reconfigure_mode(False)
        return Div(
            Script(f"window.location.href = '{target}'"),
            P("正在跳转...", cls="text-center p-4"),
        )
    except Exception as e:
        logger.error(f"完成初始化失败: {e}")
        return Div(
            P(f"初始化失败: {e}", cls="text-red-500"),
            cls="text-center p-4",
        )


@rt("/sync-progress")
async def sync_progress(request: Request) -> Any:
    """SSE 端点：提供同步进度更新"""

    async def event_generator() -> AsyncIterator[str]:
        while True:
            # 发送当前状态
            data = {
                "progress": wizard_state._sync_status["progress"],
                "stage": wizard_state._sync_status.get("stage", ""),
                "message": wizard_state._sync_status["message"],
                "completed": wizard_state._sync_status["completed"],
                "error": wizard_state._sync_status["error"],
            }
            yield f"data: {json.dumps(data)}\n\n"

            # 如果完成或出错，结束流
            if wizard_state._sync_status["completed"] or wizard_state._sync_status["error"]:
                break

            # 等待一段时间后再次发送
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@rt("/reset")
async def reset_initialization() -> Any:
    """重置初始化状态（调试用）"""
    init_wizard.reset_initialization()
    _set_download_error(None)
    _set_reconfigure_mode(False)
    return RedirectResponse("/init-wizard")
