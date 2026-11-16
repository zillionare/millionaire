"""Wizard step views."""

import datetime
from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    H3,
    Div,
    Li,
    Ol,
    Option,
    P,
    Script,
    Span,
)
from fasthtml.common import Input as _Input
from fasthtml.common import Label as _Label
from monsterui.all import *
from monsterui.all import (
    Input,
    Select,
)

from quantide.config.dev_stubs import (
    dev_stubs_enabled,
    ensure_dev_stubs_started,
)
from quantide.config.features import supports_live_trading
from quantide.config.paths import normalize_data_home
from quantide.web.pages.wizard_components import (
    FormLabel,
    FormRow,
    InfoTooltip,
)
from quantide.web.pages.wizard_forms import (
    _data_init_form_state,
    _gateway_form_state,
    _parse_positive_int_input,
    _runtime_form_state,
)
from quantide.web.pages.wizard_state import (
    ADMIN_FORM_FIELDS,
    DATA_INIT_FORM_FIELDS,
    FONT_STYLES,
    GATEWAY_FORM_FIELDS,
    PRIMARY_COLOR,
    RUNTIME_FORM_FIELDS,
    _with_force_query,
)


def Step1_Welcome() -> Any:
    """步骤1：欢迎页"""
    gateway_text = "配置实时行情数据源，按需选择一次 30 天演示"
    data_text = "配置数据源并检查账号权限；确认全部配置后再开始下载。"
    if dev_stubs_enabled():
        gateway_text = "确认开发 Stub 自动注入的交易/实时行情网关"
        data_text = "导入开发 Stub 内置样本数据。"
    return Div(
        P("本向导将引导您完成以下工作：", style=FONT_STYLES["description"], cls="mb-4 mt-6"),
        Ol(
            Li("配置运行时环境，比如数据存放目录。", style=FONT_STYLES["description"]),
            Li("配置管理员密码", style=FONT_STYLES["description"]),
            Li(data_text, style=FONT_STYLES["description"]),
            Li(gateway_text, style=FONT_STYLES["description"]),
            cls="list-decimal pl-6 space-y-2",
        ),
        cls="w-full",
    )


def _check_password_strength(password: str) -> tuple[str, str]:
    """检查密码强度

    Returns:
        tuple: (强度等级: 'weak'|'medium'|'strong', 提示文本)
    """
    if len(password) < 8:
        return ("weak", "密码长度不足8位")

    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)

    score = sum([has_lower, has_upper, has_digit, has_special])

    if score >= 4 and len(password) >= 10:
        return ("strong", "强密码 ✓")
    elif score >= 3:
        return ("medium", "中等强度")
    else:
        return ("weak", "弱密码：建议使用字母大小写、数字、特殊符号组合")


def Step3_Admin(state: dict[str, Any] | None = None) -> Any:
    """步骤3：管理员密码设置"""
    state = state or {}
    password = state.get(ADMIN_FORM_FIELDS["password"], "")
    strength, strength_text = _check_password_strength(password) if password else ("", "")

    # 根据强度设置颜色
    strength_color = {
        "weak": "#dc2626",  # 红色
        "medium": "#ca8a04",  # 黄色
        "strong": "#16a34a",  # 绿色
        "": "#6b7280",  # 灰色（默认）
    }.get(strength, "#6b7280")

    return Div(
        Div(
            # 管理员密码
            FormLabel(
                "管理员密码",
                required=True,
                tooltip="建议使用8位以上密码，包含字母大小写、数字、特殊符号各一。",
            ),
            Div(
                Input(
                    name=ADMIN_FORM_FIELDS["password"],
                    type="password",
                    value=password,
                    placeholder="请输入管理员密码",
                    required=True,
                    oninput="checkPasswordStrength(this.value)",
                    cls="uk-input",
                ),
                # 密码强度提示
                Div(
                    Span(strength_text, style=f"{FONT_STYLES['hint']} color: {strength_color};"),
                    id="password-strength",
                    cls="mt-1 mb-4",
                )
                if password
                else Div(id="password-strength", cls="mt-1 mb-4"),
            ),
            # 确认密码
            FormLabel("确认密码", required=True),
            Input(
                name=ADMIN_FORM_FIELDS["confirm"],
                type="password",
                value=state.get(ADMIN_FORM_FIELDS["confirm"], ""),
                placeholder="再次输入管理员密码",
                required=True,
                cls="uk-input mb-4",
            ),
        ),
        # 密码强度检查脚本
        Script(r"""
            function checkPasswordStrength(password) {
                const strengthDiv = document.getElementById('password-strength');
                if (!password) {
                    strengthDiv.innerHTML = '';
                    return;
                }

                let strength = 'weak';
                let text = '弱密码：建议使用字母大小写、数字、特殊符号组合';
                let color = '#dc2626';

                const hasLower = /[a-z]/.test(password);
                const hasUpper = /[A-Z]/.test(password);
                const hasDigit = /\d/.test(password);
                const hasSpecial = /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(password);
                const score = [hasLower, hasUpper, hasDigit, hasSpecial].filter(Boolean).length;

                if (password.length < 8) {
                    strength = 'weak';
                    text = '密码长度不足8位';
                    color = '#dc2626';
                } else if (score >= 4 && password.length >= 10) {
                    strength = 'strong';
                    text = '强密码 ✓';
                    color = '#16a34a';
                } else if (score >= 3) {
                    strength = 'medium';
                    text = '中等强度';
                    color = '#ca8a04';
                }

                strengthDiv.innerHTML = '<span style="color: ' + color + '">' + text + '</span>';
            }
        """),
        cls="w-full",
    )


def Step2_Runtime(state: dict[str, Any] | None = None) -> Any:
    """步骤2：运行环境配置"""
    values = _runtime_form_state(state)

    return Div(
        Div(
            # 数据存储位置
            FormLabel(
                "数据存储位置",
                tooltip=(
                    "行情数据和相关缓存将存放在此处。留空时读取环境配置，未配置则使用"
                    "系统临时目录。长期运行请指定持久目录。配置数据库保存在系统配置目录。"
                ),
            ),
            Input(
                name=RUNTIME_FORM_FIELDS["home"],
                value=values[RUNTIME_FORM_FIELDS["home"]],
                placeholder=normalize_data_home(),
                cls="uk-input mb-4",
            ),
            # 只允许本机访问
            Div(
                _Label(
                    _Input(
                        type="checkbox",
                        name=RUNTIME_FORM_FIELDS["localhost_only"],
                        value="true",
                        checked=values[RUNTIME_FORM_FIELDS["localhost_only"]],
                        cls="uk-checkbox mr-2",
                    ),
                    Span("只允许本机访问", style=FONT_STYLES["label"]),
                    InfoTooltip("勾选后仅允许本机访问，取消勾选则允许外部访问。"),
                    cls="flex items-center mb-4",
                ),
            ),
            # 监听端口
            FormRow(
                "监听端口",
                Input(
                    name=RUNTIME_FORM_FIELDS["port"],
                    type="number",
                    value=values[RUNTIME_FORM_FIELDS["port"]],
                    placeholder="8130",
                    cls="uk-input",
                ),
                tooltip="除非端口已被其它应用占用，否则可使用默认值。",
            ),
            # 路径前缀
            FormRow(
                "路径前缀",
                Input(
                    name=RUNTIME_FORM_FIELDS["prefix"],
                    value=values[RUNTIME_FORM_FIELDS["prefix"]],
                    placeholder="/quantide",
                    cls="uk-input",
                ),
                tooltip="可选。如果不明白含义，可保持默认。",
            ),
        ),
        cls="w-full",
    )


def Step4_Gateway(state: dict[str, Any] | None = None) -> Any:
    """Realtime setup, retaining the shared pro-edition gateway form."""
    if not supports_live_trading():
        from quantide.web.pages.wizard_data_views import RealtimeSetup

        return RealtimeSetup()
    if dev_stubs_enabled():
        return _stub_gateway_step()

    values = _gateway_form_state(state)
    enabled = bool(values[GATEWAY_FORM_FIELDS["enabled"]])

    return Div(
        Div(
            # 启用 gateway
            Div(
                _Label(
                    _Input(
                        type="checkbox",
                        name=GATEWAY_FORM_FIELDS["enabled"],
                        value="true",
                        checked=enabled,
                        cls="uk-checkbox mr-2",
                    ),
                    Span("启用 gateway", style=FONT_STYLES["label"]),
                    InfoTooltip("请安装 quantide gateway 并配置，否则无法获得实时行情和执行交易。"),
                    cls="flex items-center mb-4",
                ),
            ),
            # gateway 服务器地址
            FormRow(
                "服务器地址",
                Input(
                    name=GATEWAY_FORM_FIELDS["server"],
                    value=values[GATEWAY_FORM_FIELDS["server"]],
                    placeholder="localhost",
                    disabled=not enabled,
                    cls=f"uk-input {'uk-disabled' if not enabled else ''}",
                ),
                tooltip="gateway 服务器的主机名或 IP 地址。",
            ),
            # gateway 端口
            FormRow(
                "端口",
                Input(
                    name=GATEWAY_FORM_FIELDS["port"],
                    type="number",
                    value=values[GATEWAY_FORM_FIELDS["port"]],
                    placeholder="8000",
                    disabled=not enabled,
                    cls=f"uk-input {'uk-disabled' if not enabled else ''}",
                ),
                tooltip="gateway 服务监听的端口号。",
            ),
            # gateway 访问密钥
            FormRow(
                "访问密钥",
                Input(
                    name=GATEWAY_FORM_FIELDS["api_key"],
                    value=values[GATEWAY_FORM_FIELDS["api_key"]],
                    placeholder="",
                    disabled=not enabled,
                    cls=f"uk-input {'uk-disabled' if not enabled else ''}",
                ),
                tooltip="可在 gateway 用户头像菜单中生成和查看密钥。",
            ),
            # 路径前缀
            FormRow(
                "路径前缀",
                Input(
                    name=GATEWAY_FORM_FIELDS["prefix"],
                    value=values[GATEWAY_FORM_FIELDS["prefix"]],
                    placeholder="/",
                    disabled=not enabled,
                    cls=f"uk-input {'uk-disabled' if not enabled else ''}",
                ),
                tooltip="默认值为 /。",
            ),
        ),
        cls="w-full",
    )


def _calculate_download_range(years: int) -> tuple[datetime.date, datetime.date]:
    """计算下载起止日期

    Args:
        years: 下载年数

    Returns:
        tuple: (开始日期, 结束日期)
    """
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=int(years * 365.25))
    return start_date, end_date


def _render_download_range_info(years: int) -> Any:
    """渲染下载范围信息"""
    download_start, download_end = _calculate_download_range(years)
    return P(
        (
            "当前设置将下载从 "
            f"{download_start.strftime('%Y年%m月%d日')}"
            " 到 "
            f"{download_end.strftime('%Y年%m月%d日')}"
            " 的数据。"
        ),
        style=FONT_STYLES["description"],
        cls="mb-4 mt-4",
    )


def Step5_DataSetup(state: dict[str, Any] | None = None) -> Any:
    """Configure and check the historical source, now displayed as step four."""
    if dev_stubs_enabled():
        state = state or {}
        app_home = normalize_data_home(state.get(RUNTIME_FORM_FIELDS["home"]))
        return Div(
            Div(
                P(
                    (
                        "当前进程已启用开发 Stub 模式。向导将直接导入内置样本数据到本地数"
                        "据目录，不会访问真实 Tushare，也不需要填写 Tushare Token。"
                    ),
                    style=FONT_STYLES["description"],
                    cls="mb-4",
                ),
                Div(
                    Div(
                        Span("数据目录", cls="font-medium text-gray-700 mr-2"),
                        Span(app_home, cls="text-gray-900"),
                        cls="mb-2",
                    ),
                    Div(
                        Span("数据源", cls="font-medium text-gray-700 mr-2"),
                        Span("fixture-backed Tushare stub", cls="text-gray-900"),
                        cls="mb-2",
                    ),
                    Div(
                        Span("导入内容", cls="font-medium text-gray-700 mr-2"),
                        Span(
                            "证券日历、全A证券列表、历史日线样本、复权因子、涨跌停价格、ST 数据",
                            cls="text-gray-900",
                        ),
                    ),
                    cls="rounded-lg border border-gray-200 bg-gray-50 px-4 py-4",
                ),
                P(
                    "点击下一步后，系统会快速导入这组内置样本，并直接进入完成页，不再弹出首次下载对话框。",
                    style=FONT_STYLES["description"],
                    cls="mt-4",
                ),
            ),
            cls="w-full",
        )

    values = _data_init_form_state(state)
    epoch = values[DATA_INIT_FORM_FIELDS["epoch"]]
    data_source = (
        str(values[DATA_INIT_FORM_FIELDS["data_source"]] or "tushare").strip().lower() or "tushare"
    )
    years_raw = values[DATA_INIT_FORM_FIELDS["history_years"]]
    try:
        years = _parse_positive_int_input(years_raw, "首次下载时长", 1)
    except ValueError:
        years = 1

    # 计算下载起止时间
    download_start, download_end = _calculate_download_range(years)

    return Div(
        Div(
            FormRow(
                "当前数据源",
                Select(
                    Option("Tushare", value="tushare", selected=data_source == "tushare"),
                    name=DATA_INIT_FORM_FIELDS["data_source"],
                    cls="uk-select",
                ),
                required=True,
                tooltip="当前版本先接入 Tushare，后续可以在同一标准接口下扩展更多数据源。",
            ),
            # 数据起始日
            FormRow(
                "数据起始日",
                Input(
                    name=DATA_INIT_FORM_FIELDS["epoch"],
                    value=epoch,
                    placeholder="2005-01-01",
                    required=True,
                    cls="uk-input",
                ),
                required=True,
                tooltip=(
                    "行情数据的起始日，为确保数据有效、一致，不建议配置太早的起始日。比如"
                    "，tushare 的数据集中，ST/涨跌停历史数据可能会从2016年起。"
                ),
            ),
            # Tushare 访问密钥
            FormRow(
                "Tushare 访问密钥",
                Input(
                    name=DATA_INIT_FORM_FIELDS["tushare_token"],
                    value=values[DATA_INIT_FORM_FIELDS["tushare_token"]],
                    placeholder="请输入您的 tushare token",
                    type="password",
                    autocomplete="off",
                    required=True,
                    cls="uk-input",
                ),
                required=True,
                tooltip="访问 tushare 需要密钥，请在 https://tushare.pro/user/token 页面获取。",
            ),
            # 首次下载时长
            FormRow(
                "首次下载时长（年）",
                Input(
                    type="number",
                    name=DATA_INIT_FORM_FIELDS["history_years"],
                    min="1",
                    value=years_raw,
                    required=True,
                    cls="uk-input",
                    hx_trigger="change",
                    hx_post=_with_force_query("/init-wizard/update-download-range"),
                    hx_target="#download-range-info",
                    hx_include="[name='history_years']",
                ),
                required=True,
                tooltip="本次初始化时，会下载从今天起往前推若干年的数据，默认为1年。后续还会有后台任务继续下载，所以为使您快速进入系统使用，建议就设置为1年。下载一年的数据，大约需要30分钟左右，也取决于您账号的限速。",
            ),
        ),
        # 下载范围描述
        Div(
            _render_download_range_info(years),
            id="download-range-info",
        ),
        _access_report_view(),
        cls="w-full",
    )


def Step6_Complete(state: dict[str, Any] | None = None) -> Any:
    """步骤6：完成页面"""
    state = state or {}
    if not state.get("init_completed") and not dev_stubs_enabled():
        from quantide.web.pages.wizard_data_views import HistoryConfirmation

        return HistoryConfirmation(state)
    return Div(
        Div(
            "✓",
            cls=(
                "w-16 h-16 rounded-full flex items-center justify-center text-2xl "
                "font-semibold mx-auto"
            ),
            style=f"background: rgba(209, 53, 39, 0.12); color: {PRIMARY_COLOR};",
        ),
        P(
            "配置已保存，您可以立即进入系统开始使用。",
            cls="text-center mt-6",
            style=FONT_STYLES["description"],
        ),
        P(
            "已经运行的服务更换实时源后，请通过服务控件重启服务，使新配置生效。",
            cls="text-sm text-gray-500 mt-2",
        )
        if state.get("init_completed")
        else None,
        cls="w-full py-8",
    )


def _stub_gateway_step() -> Any:
    """Render connection facts from the locally running demonstration gateway."""
    runtime = ensure_dev_stubs_started()
    gateway_url = getattr(runtime, "gateway_base_url", "") if runtime is not None else ""
    gateway_server = getattr(runtime, "gateway_server", "") if runtime is not None else ""
    gateway_port = getattr(runtime, "gateway_port", "") if runtime is not None else ""
    gateway_prefix = getattr(runtime, "gateway_prefix", "/") if runtime is not None else "/"
    return Div(
        Div(
            H3(
                "开发 Stub 模式已自动配置交易网关",
                cls="text-lg font-semibold text-gray-900 mb-3",
            ),
            P(
                (
                    "当前进程已自动启动并启用本地 gateway "
                    "stub。初始化向导在该模式下不会要求你手动填写地址、端口或路径前缀"
                    "。"
                ),
                style=FONT_STYLES["description"],
                cls="mb-4",
            ),
            Div(
                Div(
                    Span("运行地址", cls="font-medium text-gray-700 mr-2"),
                    Span(gateway_url or "未初始化", cls="text-gray-900"),
                    cls="mb-2",
                ),
                Div(
                    Span("服务器", cls="font-medium text-gray-700 mr-2"),
                    Span(str(gateway_server or "未初始化"), cls="text-gray-900"),
                    cls="mb-2",
                ),
                Div(
                    Span("端口", cls="font-medium text-gray-700 mr-2"),
                    Span(str(gateway_port or "未初始化"), cls="text-gray-900"),
                    cls="mb-2",
                ),
                Div(
                    Span("路径前缀", cls="font-medium text-gray-700 mr-2"),
                    Span(str(gateway_prefix or "/"), cls="text-gray-900"),
                ),
                cls="rounded-lg border border-gray-200 bg-gray-50 px-4 py-4",
            ),
            P(
                (
                    "点击下一步后，向导会把这组 stub gateway "
                    "配置写入初始化状态，用于当前开发态演示与验收。"
                ),
                style=FONT_STYLES["description"],
                cls="mt-4",
            ),
        ),
        cls="w-full",
    )


def _access_report_view() -> Any:
    from quantide.web.pages.wizard_data_views import AccessReport

    return Div(
        P(
            "日线与参考数据使用 Tushare；30 分钟历史由 BaoStock 提供，无需额外 Token。",
            cls="text-sm mt-4",
        ),
        P("正在检测数据源权限，请稍候…", id="data-source-checking", cls="htmx-indicator mt-4"),
        AccessReport(),
    )
