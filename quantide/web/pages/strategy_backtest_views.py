"""Strategy backtest views."""

from collections.abc import Mapping
from typing import Any

import arrow
import fasthtml.common as fh
from fasthtml.common import *
from fasthtml.common import (
    A,
    Div,
    P,
    Script,
    Span,
    Tr,
)
from monsterui.all import *
from monsterui.all import (
    H3,
    H4,
    Button,
    Details,
    Form,
    Input,
    Summary,
    Td,
    UkIcon,
)
from starlette.requests import Request

from quantide.config.features import (
    supports_live_trading,
)
from quantide.core.enums import BrokerKind
from quantide.core.strategy import Strategy
from quantide.data.sqlite import db
from quantide.factors import FEATURE_DOCS, FEATURE_GROUPS
from quantide.service.backtest_params import (
    default_backtest_params,
    format_changed_params,
)
from quantide.service.discovery import strategy_loader
from quantide.service.risk_programs import (
    ALLOW_SAME_BAR_REPURCHASE_KEY,
    available_risk_programs,
)
from quantide.service.runner import BacktestRunner
from quantide.service.strategy_runtime import strategy_runtime_manager
from quantide.web.components.risk_inputs import RiskParameterInput, RiskProgramCheckbox
from quantide.web.pages.strategy_backtest_config import (
    _decode_backtest_prefill,
    _split_backtest_params,
)
from quantide.web.pages.strategy_format import (
    _extract_params_from_info,
    _foldable_cell,
    _format_date,
    _format_number,
    _format_percent,
    _format_range,
    _get_strategy_default_params,
    _params_to_text,
    _strategy_version,
    _supports_stock_selection,
    strategy_close_button,
)
from quantide.web.pages.strategy_metrics import (
    _build_metrics_payload,
)
from quantide.web.pages.strategy_routes import (
    BACKTEST_WIZARD_SCRIPT,
    TRADE_PARAM_LABELS,
    rt,
)


def _backtest_parameters_text(
    info_params: dict[str, Any] | None, strategy_cls: type[Strategy] | None
) -> str:
    """Backtest parameters text."""
    if info_params:
        # 只展示与默认不同的参数（用户改过的）
        params_text = format_changed_params(info_params, default_backtest_params(strategy_cls))
    elif strategy_cls:
        # 老回测没有落库配置，只能回退到策略默认参数
        params_text = _params_to_text(_get_strategy_default_params(strategy_cls))
    else:
        params_text = "默认"
    return params_text


def _build_backtest_name_cell(
    name: str,
    portfolio_id: str,
    start: object = None,
    end: object = None,
) -> Any:
    """构建回测报告列表中的策略名单元格。"""
    return Td(
        A(
            name,
            href=f"/strategy/backtest/{portfolio_id}",
            cls="text-[#e41815] font-medium hover:underline",
        ),
        P(
            _format_range(start, end),
            cls="mt-1 mb-0 text-xs text-gray-500 whitespace-nowrap",
        ),
        cls="text-gray-900",
    )


def _build_backtest_deploy_button(
    label: str,
    modal_path: str,
    *,
    is_available: bool,
    unavailable_reason: str,
    tone_cls: str = "",
) -> Any:
    """构建回测报告列表中的投放按钮。"""
    button_cls = " ".join(filter(None, ("btn btn-secondary btn-sm", tone_cls)))
    if is_available:
        return Button(
            label,
            cls=button_cls,
            type="button",
            hx_get=modal_path,
            hx_target="#modal-container",
        )
    return Span(
        Button(
            label,
            cls=f"{button_cls} opacity-50 cursor-not-allowed pointer-events-none",
            type="button",
            disabled=True,
        ),
        title=unavailable_reason,
        cls="inline-flex",
    )


def _build_backtest_action_cell(
    portfolio_id: str,
    deployment_modes: dict[str, dict[str, Any]] | None = None,
    *,
    paper_available: bool = True,
    paper_unavailable_reason: str = "",
    live_available: bool = True,
    live_unavailable_reason: str = "",
    hx_swap_oob: bool = False,
) -> Any:
    """构建回测报告列表操作列。"""
    deployment_modes = deployment_modes or strategy_runtime_manager.backtest_deployment_modes(
        portfolio_id
    )
    controls: list[Any] = []

    if "paper" in deployment_modes:
        controls.append(
            Span(
                "仿真中",
                cls=(
                    "inline-flex items-center rounded-full bg-[#fff3f2] px-3 py-1 "
                    "text-xs font-medium text-[#e41815]"
                ),
            )
        )
    else:
        controls.append(
            _build_backtest_deploy_button(
                "转仿真",
                f"/strategy/backtest/{portfolio_id}/deploy/paper/modal",
                is_available=paper_available,
                unavailable_reason=paper_unavailable_reason,
                tone_cls="q-btn--paper",
            )
        )

    if supports_live_trading():
        if "live" in deployment_modes:
            controls.append(
                Span(
                    "实盘中",
                    cls=(
                        "inline-flex items-center rounded-full bg-green-50 px-3 py-1 "
                        "text-xs font-medium text-green-600"
                    ),
                )
            )
        else:
            controls.append(
                _build_backtest_deploy_button(
                    "转实盘",
                    f"/strategy/backtest/{portfolio_id}/deploy/live/modal",
                    is_available=live_available,
                    unavailable_reason=live_unavailable_reason,
                )
            )

    controls.append(
        Button(
            UkIcon("trash-2", size=14),
            title="删除回测",
            hx_get=f"/strategy/backtest/{portfolio_id}/delete/modal",
            hx_target="#modal-container",
            cls=(
                "w-8 h-8 flex items-center justify-center bg-transparent border-0 "
                "shadow-none p-0 text-red-500 hover:text-red-700"
            ),
            type="button",
        )
    )

    attrs: dict[str, Any] = {"id": f"backtest-actions-{portfolio_id}"}
    if hx_swap_oob:
        attrs["hx_swap_oob"] = "true"

    return Td(Div(*controls, cls="flex flex-wrap items-center gap-2"), **attrs)


def _build_strategy_rows(strategies: dict[str, Any]) -> list[Any]:
    """构建策略列表行。

    Args:
        strategies: 策略字典

    Returns:
        list: 行数据
    """
    rows = []
    for name, cls in strategies.items():
        doc = cls.__doc__ or "暂无描述"
        version = _strategy_version(cls)
        portfolios = db.get_portfolios_by_strategy(name)
        history_count = portfolios.height if hasattr(portfolios, "height") else 0
        latest_link = None
        latest_date = "--"
        if not portfolios.is_empty():
            portfolios = portfolios.sort("start", descending=True)
            latest_row = portfolios.row(0, named=True)
            latest_date = _format_date(latest_row.get("end") or latest_row.get("start"))
            latest_link = latest_row.get("portfolio_id")

        latest_cell = (
            A(
                latest_date,
                href=f"/strategy/backtest/{latest_link}",
                cls="text-[#e41815] hover:underline",
            )
            if latest_link
            else Span("--", cls="text-gray-400")
        )

        action_controls: list[Any] = [
            fh.Button(
                UkIcon("play", size=16, cls="text-[#e41815]"),
                title="重新运行回测",
                hx_get=f"/strategy/{name}/backtest/modal",
                hx_target="#modal-container",
                hx_indicator="#global-loading",
                cls="q-btn q-btn--sm q-btn--ghost",
                type="button",
            )
        ]
        action_controls.append(
            A(
                "优化",
                title="参数优化：在样本内挑选参数并用样本外检验",
                href=f"/strategy/{name}/optimize",
                cls="q-btn q-btn--sm",
            )
        )
        if _supports_stock_selection(cls):
            action_controls.append(
                fh.Button(
                    "选股",
                    title="运行机器学习模型选出当日个股",
                    hx_get=f"/strategy/{name}/select/modal",
                    hx_target="#modal-container",
                    hx_indicator="#global-loading",
                    cls="q-btn q-btn--sm q-btn--success",
                    type="button",
                )
            )

        rows.append(
            Tr(
                Td(Div(*action_controls, cls="strategy-actions flex items-center gap-2")),
                Td(name, cls="text-gray-900 font-medium"),
                Td(doc, cls="text-gray-600"),
                Td(version, cls="text-gray-900"),
                Td(f"{history_count}次", cls="text-gray-900"),
                Td(latest_cell),
                cls="border-b border-gray-200 hover:bg-gray-50",
            )
        )
    return rows


def _build_backtest_rows(
    strategies: dict[str, Any],
    *,
    paper_available: bool = True,
    paper_unavailable_reason: str = "",
    live_available: bool = True,
    live_unavailable_reason: str = "",
) -> list[Any]:
    """构建回测报告列表行。

    Args:
        strategies: 策略字典
        paper_available: 是否允许转入仿真。
        paper_unavailable_reason: 仿真不可用原因。
        live_available: 是否允许转入实盘。
        live_unavailable_reason: 实盘不可用原因。

    Returns:
        list: 行数据
    """
    rows: list[Any] = []
    portfolios = db.portfolios_all()
    if portfolios.is_empty():
        return rows
    if "start" in portfolios.columns:
        portfolios = portfolios.sort("start", descending=True)
    capabilities = {
        "paper_available": paper_available,
        "paper_unavailable_reason": paper_unavailable_reason,
        "live_available": live_available,
        "live_unavailable_reason": live_unavailable_reason,
    }
    for row in portfolios.iter_rows(named=True):
        rendered = _backtest_report_row(row, strategies, capabilities)
        if rendered is not None:
            rows.append(rendered)
    return rows


def _build_param_inputs(
    params: dict[str, Any],
    *,
    labeled: bool,
    overrides: dict[str, Any] | None = None,
) -> list[Any]:
    """构建参数输入行。

    Args:
        params: 参数默认值。
        labeled: 是否显示中文标签。
        overrides: 覆盖值（如参数优化结果回填）。

    Returns:
        list: 输入行。
    """
    inputs = []
    override_map = overrides or {}
    for k, v in params.items():
        label = f"{TRADE_PARAM_LABELS.get(k, k)} {k}" if labeled else k
        value = override_map.get(k, v)
        inputs.append(
            Div(
                Span(label, cls="text-sm font-medium text-gray-500 w-48 shrink-0"),
                Input(name=f"param_{k}", value=str(value), cls="q-input w-full"),
                cls="flex items-center gap-2 mb-2",
            )
        )
    return inputs


def _build_feature_selection_panel() -> Any:
    """构建因子勾选面板（向导第二步）。"""
    groups: list[Any] = []
    for group, names in FEATURE_GROUPS.items():
        items: list[Any] = []
        for name in names:
            doc = FEATURE_DOCS.get(name, "")
            items.append(
                Div(
                    fh.Label(
                        fh.Input(
                            type="checkbox",
                            name="param_features",
                            value=name,
                            checked=True,
                            cls="checkbox checkbox-sm",
                        ),
                        Span(name, cls="text-xs font-medium text-gray-700"),
                        title=doc,
                        cls="flex items-center gap-2 cursor-pointer",
                    ),
                    cls="py-0.5",
                )
            )
        groups.append(
            Div(
                Div(group, cls="text-xs font-semibold text-gray-600 mb-1"),
                Div(*items, cls="grid grid-cols-2 gap-x-3"),
                cls="mb-2",
            )
        )
    return Div(
        Div(
            H4("选择因子", cls="text-sm font-semibold text-gray-600 mb-1"),
            P(
                "取消勾选即不参与训练与打分（全部取消表示使用全部因子）。鼠标悬停因子名可查看计算方法、含义与示例。",
                cls="text-xs text-gray-500 mb-2",
            ),
            *groups,
        )
    )


def _build_risk_selection_panel(
    strategy_cls: Any,
    interval: str = "1d",
    selected: list[dict[str, Any]] | None = None,
) -> Any:
    """Build the explicit, priority-ordered risk-program step."""
    selected_by_id = {
        str(item.get("id")): item for item in (selected or []) if isinstance(item, dict)
    }
    cards: list[Any] = []
    try:
        programs = available_risk_programs(strategy_cls, interval)
    except Exception:
        programs = []
    for index, program in enumerate(programs):
        program_id = str(program["id"])
        item = selected_by_id.get(program_id)
        checked = item is not None
        params = dict(program.get("params") or {})
        params.update((item or {}).get("params") or {})
        priority = (item or {}).get("priority", index)
        param_inputs = [
            Div(
                Span(key, cls="text-xs text-gray-500 w-32 shrink-0"),
                RiskParameterInput(index, key, value, "q-input w-full"),
                cls="flex items-center gap-2 mb-1",
            )
            for key, value in params.items()
        ]
        cards.append(
            Div(
                RiskProgramCheckbox(program, checked, "font-medium text-sm"),
                P(str(program.get("description") or ""), cls="text-xs text-gray-500 mt-1"),
                Div(
                    Span("优先级", cls="text-xs text-gray-500 w-32 shrink-0"),
                    Input(
                        name=f"risk_priority_{index}",
                        value=str(priority),
                        type="number",
                        min="0",
                        cls="q-input w-24",
                    ),
                    cls="flex items-center gap-2 mt-2 mb-1",
                ),
                Div(*param_inputs, cls="mt-1"),
                cls="rounded-lg border border-gray-200 bg-gray-50 p-3 mb-2",
            )
        )
    if not cards:
        cards.append(P("当前周期没有可安全回测的风控程序。", cls="text-sm text-gray-500"))
    return Div(
        Input(type="hidden", name="risk_selection_present", value="1"),
        H4("选择风控程序", cls="text-sm font-semibold text-gray-600 mb-1"),
        P(
            "可不选，也可选择多个；优先级越小越先执行。只有提供了明确回测适配器的风控程序会显示。",
            cls="text-xs text-gray-500 mb-2",
        ),
        *cards,
        fh.Label(
            fh.Input(
                type="checkbox",
                name=ALLOW_SAME_BAR_REPURCHASE_KEY,
                value="true",
                checked=True,
                cls="checkbox checkbox-sm",
            ),
            Span("允许风控卖出后同一 bar 再买入", cls="text-sm text-gray-700"),
            cls="flex items-center gap-2 mt-3",
        ),
        P(
            "日线回测仍遵守 T+1；该选项只决定风控卖出后宿主是否可在同一 bar 重新买入。",
            cls="text-xs text-gray-500 mt-1",
        ),
    )


def _build_backtest_step1(cls: Any, interval: str, prefill: dict[str, Any]) -> Any:
    """Build the date, cash, strategy and trade parameter step."""
    default_params = _get_strategy_default_params(cls)
    strategy_params, trade_params = _split_backtest_params(default_params)
    prefill_params = prefill.get("params") or {}
    param_inputs = _build_param_inputs(strategy_params, labeled=False, overrides=prefill_params)
    trade_param_inputs = _build_param_inputs(trade_params, labeled=True)
    return Div(
        Div(
            Span("开始日期", cls="text-sm font-medium text-gray-500 w-24 shrink-0"),
            Input(
                name="start_date",
                type="date",
                value=str(prefill.get("start_date") or "2024-01-01"),
                required=True,
                cls="q-input w-full",
            ),
            cls="flex items-center gap-2 mb-2",
        ),
        Div(
            Span("结束日期", cls="text-sm font-medium text-gray-500 w-24 shrink-0"),
            Input(
                name="end_date",
                type="date",
                value=str(prefill.get("end_date") or arrow.now().format("YYYY-MM-DD")),
                required=True,
                cls="q-input w-full",
            ),
            cls="flex items-center gap-2 mb-2",
        ),
        Div(
            Span("初始资金", cls="text-sm font-medium text-gray-500 w-24 shrink-0"),
            Input(
                name="initial_cash",
                type="number",
                value="1000000",
                cls="q-input w-full",
            ),
            cls="flex items-center gap-2 mb-2",
        ),
        Div(
            Span("周期", cls="text-sm font-medium text-gray-500 w-24 shrink-0"),
            Input(type="hidden", name="interval", value=interval),
            Span(
                {"1d": "日线", "30m": "30分钟线", "1M": "月线"}.get(interval, interval),
                cls="text-sm text-gray-700",
            ),
            Span("（由策略固定）", cls="text-xs text-gray-500"),
            cls="flex items-center gap-2 mb-2",
        ),
        Div(
            Span("日志保存", cls="text-sm font-medium text-gray-500 w-24 shrink-0"),
            fh.Label(
                fh.Input(name="save_logs", type="checkbox", cls="checkbox checkbox-sm"),
                Span("保存回测日志到本地文件", cls="text-sm text-gray-700"),
                cls="flex items-center gap-2",
            ),
            cls="flex items-center gap-3 mb-1",
        ),
        P(
            "开启后会在回测运行时同步写入本地 backtest_logs 目录，报告页可反复加载。",
            cls="ml-[6.75rem] mb-2 text-xs text-gray-500",
        ),
        Div(H4("策略参数", cls="text-sm font-semibold text-gray-600 mt-3 mb-2"), *param_inputs),
        Details(
            Summary(
                "交易参数（风险程序 / 滑点 / 手续费，一般无需修改）",
                cls="cursor-pointer text-sm font-semibold text-gray-600",
            ),
            P(
                "这些参数决定风险程序、成交与费用口径，默认按上次使用的值。",
                cls="text-xs text-gray-500 mt-2 mb-2",
            ),
            *trade_param_inputs,
            cls="mt-3 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2",
        ),
        data_bt_step="1",
    )


def _build_backtest_steps(
    step1: Any,
    cls: Any,
    interval: str,
    supports_feature_selection: bool,
) -> list[Any]:
    """Build only the steps relevant to the selected strategy."""
    steps: list[Any] = [step1]
    if supports_feature_selection:
        steps.append(Div(_build_feature_selection_panel(), data_bt_step="2", cls="hidden"))
    steps.append(
        Div(
            _build_risk_selection_panel(cls, interval),
            data_bt_step="3" if supports_feature_selection else "2",
            cls="hidden",
        )
    )
    return steps


def _build_backtest_footer(name: str, supports_feature_selection: bool) -> list[Any]:
    """Build wizard navigation controls for the available steps."""
    controls: list[Any] = [
        strategy_close_button("取消", data_bt_show="1"),
        Button(
            "上一步",
            type="button",
            cls="btn btn-ghost",
            onclick="showBacktestStep(1)",
            data_bt_show="2",
        ),
    ]
    next_class = "q-btn q-btn--outline-brand"
    if supports_feature_selection:
        controls.extend(
            [
                Button(
                    "上一步",
                    type="button",
                    cls="btn btn-ghost",
                    onclick="showBacktestStep(2)",
                    data_bt_show="3",
                ),
                Button(
                    "下一步：选择因子",
                    type="button",
                    cls=next_class,
                    onclick="showBacktestStep(2)",
                    data_bt_show="1",
                ),
                Button(
                    "下一步：选择风控",
                    type="button",
                    cls=next_class,
                    onclick="showBacktestStep(3)",
                    data_bt_show="2",
                ),
            ]
        )
        start_step = "3"
    else:
        controls.append(
            Button(
                "下一步：选择风控",
                type="button",
                cls=next_class,
                onclick="showBacktestStep(2)",
                data_bt_show="1",
            )
        )
        start_step = "2"
    controls.append(
        Button(
            "开始运行",
            type="button",
            cls="q-btn",
            onclick="this.disabled=true;this.setAttribute('aria-busy','true');this.textContent='启动中...';",
            hx_post=f"/strategy/{name}/backtest/run",
            hx_target="#modal-container",
            hx_include="closest form",
            data_bt_show=start_step,
        )
    )
    return controls


@rt("/{name}/backtest/modal")
def backtest_modal(name: str, req: Request | None = None) -> Any:
    """运行回测向导：参数、因子和显式风控程序选择。

    Args:
        name: 策略名。
        req: 请求对象（框架按参数名注入），用于读取参数优化回填。
    """
    strategies = strategy_loader.load_from_cache()
    cls = strategies.get(name)
    if not cls:
        return "Strategy not found"

    interval = BacktestRunner.strategy_interval(cls)
    prefill = _decode_backtest_prefill(req)
    supports_feature_selection = bool(getattr(cls, "SUPPORTS_FEATURE_SELECTION", False))
    steps = _build_backtest_steps(
        _build_backtest_step1(cls, interval, prefill),
        cls,
        interval,
        supports_feature_selection,
    )
    footer_controls = _build_backtest_footer(name, supports_feature_selection)
    return Div(
        Div(
            Div(
                H3(f"运行回测 - {name}", cls="text-lg font-bold"),
                Span(
                    f"第 1 / {len(steps)} 步",
                    id="backtest-step-indicator",
                    cls="text-xs text-gray-500 ml-2",
                ),
                cls="backtest-dialog__header",
            ),
            Form(
                Div(*steps, cls="backtest-dialog__body"),
                Div(*footer_controls, cls="backtest-dialog__footer"),
                cls="backtest-dialog__form",
            ),
            cls="backtest-dialog",
            role="dialog",
            aria_modal="true",
            aria_label=f"运行回测 - {name}",
        ),
        Script(BACKTEST_WIZARD_SCRIPT),
        cls="backtest-dialog-overlay",
        id="strategy-modal",
    )


def _backtest_report_row(
    row: Mapping[str, Any],
    strategies: Mapping[str, type[Strategy]],
    capabilities: Mapping[str, Any],
) -> Any:
    """Render one backtest report after validating its portfolio kind."""
    kind = row.get("kind")
    if isinstance(kind, str):
        try:
            kind = BrokerKind(kind)
        except ValueError:
            return None
    if kind != BrokerKind.BACKTEST:
        return None
    portfolio_id = str(row.get("portfolio_id") or "")
    if not portfolio_id:
        return None
    name = str(row.get("name") or "--")
    strategy_cls = strategies.get(name)
    params_text = _backtest_parameters_text(
        _extract_params_from_info(row.get("info")), strategy_cls
    )
    deployment_modes = strategy_runtime_manager.backtest_deployment_modes(portfolio_id)
    metrics_payload = _build_metrics_payload(portfolio_id)
    annual_return = metrics_payload.get("annual_return")
    max_drawdown = metrics_payload.get("max_drawdown")
    annual_cls = (
        "text-gray-900"
        if annual_return is None
        else ("text-green-600" if annual_return >= 0 else "text-red-600")
    )
    drawdown_cls = (
        "text-gray-900"
        if max_drawdown is None
        else ("text-red-600" if max_drawdown < 0 else "text-gray-900")
    )

    return Tr(
        _build_backtest_name_cell(name, portfolio_id, row.get("start"), row.get("end")),
        Td(_strategy_version(strategy_cls), cls="text-gray-600"),
        _foldable_cell(params_text),
        Td(_format_percent(annual_return), cls=f"{annual_cls} font-medium"),
        Td(_format_number(metrics_payload.get("sharpe")), cls="text-gray-900"),
        Td(_format_percent(max_drawdown), cls=drawdown_cls),
        Td(_format_number(metrics_payload.get("sortino")), cls="text-gray-900"),
        _build_backtest_action_cell(
            portfolio_id,
            deployment_modes,
            paper_available=capabilities["paper_available"],
            paper_unavailable_reason=capabilities["paper_unavailable_reason"],
            live_available=capabilities["live_available"],
            live_unavailable_reason=capabilities["live_unavailable_reason"],
        ),
        cls="border-b border-gray-200 hover:bg-gray-50",
    )
