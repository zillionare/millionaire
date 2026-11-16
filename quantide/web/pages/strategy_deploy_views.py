"""Strategy deploy views."""

from typing import Any

import fasthtml.common as fh
from fasthtml.common import *
from fasthtml.common import (
    Code,
    Div,
    P,
    Response,
    Span,
    Thead,
    Tr,
)
from monsterui.all import *
from monsterui.all import (
    H4,
    Button,
    Details,
    Form,
    Input,
    Summary,
    Table,
    Tbody,
    Td,
    Th,
)

from quantide.data.sqlite import db
from quantide.service.backtest_logs import (
    delete_saved_backtest_log,
)
from quantide.service.risk_programs import (
    RISK_PROGRAMS_KEY,
    available_risk_programs,
    risk_program_names,
    unavailable_risk_program_ids,
)
from quantide.service.strategy_runtime import strategy_runtime_manager
from quantide.web.components.risk_inputs import RiskParameterInput, RiskProgramCheckbox
from quantide.web.pages.strategy_format import (
    _strategy_dialog_modal,
    strategy_close_button,
    strategy_close_footer,
)
from quantide.web.pages.strategy_metrics import (
    _resolve_backtest_status,
)
from quantide.web.pages.strategy_routes import (
    BROKER_FEE_PARAM_DEFAULTS,
    TRADE_PARAM_LABELS,
    rt,
)


def _render_strategy_config_readonly(
    config: dict[str, Any],
    default_config: dict[str, Any] | None = None,
) -> Any:
    """策略参数只读展示（转入后以回测参数为准）。"""
    defaults = default_config or {}
    keys = [
        key
        for key in dict.fromkeys(list(config.keys()) + list(defaults.keys()))
        if key not in BROKER_FEE_PARAM_DEFAULTS
    ]
    if not keys:
        return None
    rows = [
        Tr(
            Td(Code(key), cls="text-xs"),
            Td(repr(config.get(key, defaults.get(key))), cls="text-xs text-gray-700"),
            Td(repr(defaults.get(key, config.get(key))), cls="text-xs text-gray-400"),
        )
        for key in keys
    ]
    return Details(
        Summary(
            "策略参数（以回测为准，只读）",
            cls="cursor-pointer text-sm font-semibold text-gray-600",
        ),
        P(
            "转入后沿用回测时的参数，不能在此修改。",
            cls="text-xs text-gray-500 mt-1 mb-2",
        ),
        Div(
            Table(
                Thead(
                    Tr(
                        Th("key", cls="text-xs"),
                        Th("回测值", cls="text-xs"),
                        Th("默认值", cls="text-xs"),
                    )
                ),
                Tbody(*rows),
                cls="table table-sm w-full",
            ),
            cls="max-h-48 overflow-y-auto rounded-lg border border-gray-200",
        ),
        cls="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2",
    )


def _render_config_table(
    config: dict[str, Any],
    default_config: dict[str, Any] | None = None,
    form_id_suffix: str = "paper",
) -> Any:
    """兼容旧接口：策略参数只读展示（form_id_suffix 保留兼容）。"""
    _ = form_id_suffix
    return _render_strategy_config_readonly(config, default_config)


def _render_fee_inputs(config: dict[str, Any]) -> Any:
    """交易费用输入（转入时唯一允许覆盖的配置项）。"""
    inputs = []
    for key, default in BROKER_FEE_PARAM_DEFAULTS.items():
        inputs.append(
            Div(
                fh.Label(
                    TRADE_PARAM_LABELS.get(key, key),
                    cls="text-xs text-gray-500",
                ),
                Input(
                    name=f"custom_{key}",
                    type="number",
                    step="any",
                    value=str(config.get(key, default)),
                    cls="input input-sm w-full",
                ),
                cls="space-y-1",
            )
        )
    return Div(
        H4("交易费用（可修改）", cls="text-sm font-semibold text-gray-600 mt-4 mb-2"),
        Div(*inputs, cls="grid grid-cols-2 gap-3"),
    )


def _render_deploy_risk_selection(
    config: dict[str, Any], warning_message: str = "", interval: str = "1d"
) -> Any:
    """Allow paper/live transition to remove inherited adapted programs."""
    selected = config.get(RISK_PROGRAMS_KEY) or []
    selected_by_id = {str(item.get("id")): item for item in selected if isinstance(item, dict)}
    unavailable = unavailable_risk_program_ids(selected, frame_type=interval)
    cards = []
    for index, program in enumerate(available_risk_programs(None, interval)):
        program_id = str(program["id"])
        item = selected_by_id.get(program_id)
        params = dict(program.get("params") or {})
        params.update((item or {}).get("params") or {})
        cards.append(
            Div(
                RiskProgramCheckbox(program, item is not None, "text-sm font-medium"),
                Div(
                    Input(
                        name=f"risk_priority_{index}",
                        type="number",
                        value=str((item or {}).get("priority", index)),
                        min="0",
                        cls="input input-xs w-20",
                    ),
                    *[
                        RiskParameterInput(index, key, value, "input input-xs w-24")
                        for key, value in params.items()
                    ],
                    cls="flex flex-wrap gap-1 mt-2",
                ),
                cls="rounded border border-gray-200 bg-gray-50 p-2 mb-1",
            )
        )
    unavailable_cards = [
        Div(
            Span("不可用/已阻止", cls="font-medium text-amber-700"),
            Span(f"：{program_id}", cls="font-mono text-xs text-amber-800"),
            P(
                "该风险程序未由当前 CE 宿主注册，不能静默替换；移除后才能启动。",
                cls="text-xs text-amber-700 mt-1",
            ),
            cls="rounded border border-amber-200 bg-amber-50 p-2 mb-1",
        )
        for program_id in unavailable
    ]
    warning = (
        P(
            warning_message,
            cls="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded p-2",
        )
        if warning_message
        else None
    )
    return Div(
        Input(type="hidden", name="risk_selection_present", value="1"),
        H4("沿用回测风控程序", cls="text-sm font-semibold text-gray-600 mt-4 mb-1"),
        P("默认继承回测选择，可移除；参数保持回测值。", cls="text-xs text-gray-500 mb-2"),
        warning,
        *unavailable_cards,
        *cards,
    )


def _removed_risk_warning(
    source: dict[str, Any], selected: list[dict[str, Any]], interval: str = "1d"
) -> str:
    """Describe exactly which backtest programs were removed at transition."""
    source_ids = {
        str(item.get("id"))
        for item in source.get(RISK_PROGRAMS_KEY) or []
        if isinstance(item, dict)
    }
    selected_ids = {str(item.get("id")) for item in selected if isinstance(item, dict)}
    removed = sorted(source_ids - selected_ids)
    if not removed:
        return ""
    names = risk_program_names(source.get(RISK_PROGRAMS_KEY) or [], frame_type=interval)
    removed_names = [
        name
        for name, item in zip(names, source.get(RISK_PROGRAMS_KEY) or [], strict=True)
        if isinstance(item, dict) and str(item.get("id")) in set(removed)
    ]
    return (
        "已移除回测使用的风控程序：" + "、".join(removed_names) + "；实盘/仿真结果可能与回测不同。"
    )


def _paper_deploy_modal(
    portfolio_id: str,
    principal: str = "1000000",
    config: dict[str, Any] | None = None,
    default_config: dict[str, Any] | None = None,
    error_message: str = "",
    warning_message: str = "",
    interval: str = "1d",
) -> Any:
    """渲染转入仿真确认弹窗。"""
    error_block = P(error_message, cls="text-sm text-red-600") if error_message else None
    return _strategy_dialog_modal(
        "确认转入仿真",
        Div(
            P("请输入仿真本金后确认转入仿真运行。", cls="text-sm text-gray-500"),
            error_block,
            Form(
                Input(type="hidden", name="portfolio_id", value=portfolio_id),
                _render_strategy_config_readonly(config or {}, default_config),
                _render_deploy_risk_selection(config or {}, warning_message, interval=interval),
                _render_fee_inputs(config or {}),
                Div(
                    fh.Label("仿真本金", cls="text-sm text-gray-500"),
                    Input(
                        name="paper_principal",
                        type="number",
                        min="1",
                        step="0.01",
                        value=principal,
                        cls="input input-sm w-full",
                        required=True,
                    ),
                    cls="space-y-2 mt-4",
                ),
                id="deploy-paper-form",
            ),
            cls="space-y-4",
        ),
        Div(
            strategy_close_button("取消"),
            Button(
                "确认转入仿真",
                type="button",
                cls="btn btn-primary",
                onclick="this.disabled=true;this.setAttribute('aria-busy','true');this.textContent='提交中...';",
                hx_post=f"/strategy/backtest/{portfolio_id}/deploy/paper",
                hx_target="#modal-container",
                hx_include="#deploy-paper-form",
            ),
            cls="flex justify-end gap-2",
        ),
        modal_id="deploy-paper-modal",
        width_cls="max-w-2xl",
    )


def _live_deploy_modal(
    portfolio_id: str,
    live_accounts: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
    default_config: dict[str, Any] | None = None,
    warning_message: str = "",
    interval: str = "1d",
) -> Any:
    """渲染转入实盘确认弹窗."""
    if not live_accounts:
        return _strategy_dialog_modal(
            "无法转入实盘",
            Div(
                P("未检测到可用的实盘网关，请先配置并启动实盘网关。", cls="text-sm text-red-600"),
            ),
            strategy_close_footer(),
            modal_id="deploy-live-unavailable-modal",
            width_cls="max-w-md",
        )

    account_id = str(live_accounts[0].get("id") or "gateway:default")
    account_name = str(live_accounts[0].get("name") or account_id)
    strategy_config = _render_strategy_config_readonly(config or {}, default_config)
    fee_inputs = _render_fee_inputs(config or {})
    return _strategy_dialog_modal(
        "确认转入实盘",
        Div(
            P("确认后会把当前回测参数转入实盘运行。", cls="text-sm text-gray-500"),
            P(f"实盘网关：{account_name}", cls="mt-3 text-sm text-gray-700"),
            Form(
                Input(type="hidden", name="live_account_id", value=account_id),
                strategy_config,
                _render_deploy_risk_selection(config or {}, warning_message, interval=interval),
                fee_inputs,
                id="deploy-live-form",
            ),
            cls="space-y-4",
        ),
        Div(
            strategy_close_button("取消"),
            Button(
                "确认转入实盘",
                type="button",
                cls="btn btn-secondary",
                onclick="this.disabled=true;this.setAttribute('aria-busy','true');this.textContent='提交中...';",
                hx_post=f"/strategy/backtest/{portfolio_id}/deploy/live",
                hx_target="#modal-container",
                hx_include="#deploy-live-form",
            ),
            cls="flex justify-end gap-2",
        ),
        modal_id="deploy-live-modal",
        width_cls="max-w-2xl",
    )


def _delete_backtest_modal(portfolio_id: str) -> Any:
    """渲染删除回测确认弹窗。"""
    portfolio = db.get_portfolio(portfolio_id)
    name = portfolio.name if portfolio else "--"
    id_short = portfolio_id[:8]
    status, _ = _resolve_backtest_status(portfolio_id)
    is_running = status == "running"
    deployment_modes = strategy_runtime_manager.backtest_deployment_modes(portfolio_id)
    is_deployed = bool(deployment_modes)

    warning_block: Any = None
    if is_running:
        warning_block = P(
            "回测正在运行，无法删除。请先等待回测结束。",
            cls="text-sm text-gray-500",
        )
    elif is_deployed:
        warning_block = P(
            "此回测已投放，删除报告不影响投放运行。",
            cls="text-sm text-[#e41815]",
        )

    return _strategy_dialog_modal(
        "确认删除回测",
        Div(
            P(
                "确定要删除回测报告吗？此操作不可恢复。",
                cls="text-sm text-gray-700",
            ),
            P(
                f"策略：{name}",
                cls="text-sm text-gray-500 mt-2",
            ),
            P(
                f"ID：{id_short}",
                cls="text-sm text-gray-500",
            ),
            warning_block,
            cls="space-y-3",
        ),
        Div(
            strategy_close_button("取消"),
            Button(
                "确认删除",
                type="button",
                cls="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700",
                disabled=is_running,
                onclick="this.disabled=true;this.setAttribute('aria-busy','true');this.textContent='删除中...';",
                hx_post=f"/strategy/backtest/{portfolio_id}/delete",
                hx_target="#modal-container",
            ),
            cls="flex justify-end gap-2",
        ),
        modal_id="delete-backtest-modal",
        width_cls="max-w-md",
    )


@rt("/backtest/{portfolio_id}/delete/modal")
def delete_backtest_modal(portfolio_id: str) -> Any:
    """删除回测确认弹窗路由。"""
    return _delete_backtest_modal(portfolio_id)


@rt("/backtest/{portfolio_id}/delete", methods=["POST"])
def delete_backtest_execute(portfolio_id: str) -> Any:
    """执行删除回测。"""
    status, _ = _resolve_backtest_status(portfolio_id)
    if status == "running":
        return _strategy_dialog_modal(
            "无法删除",
            Div(
                P("回测正在运行，无法删除。", cls="text-sm text-red-600"),
            ),
            strategy_close_footer(),
            modal_id="delete-backtest-error-modal",
            width_cls="max-w-md",
        )
    db.delete_portfolio_cascade(portfolio_id)
    delete_saved_backtest_log(portfolio_id)
    strategy_runtime_manager.remove_backtest_run(portfolio_id)
    return Response(
        "",
        headers={"HX-Redirect": "/strategy"},
    )
