"""Strategy."""

import asyncio
import json
import uuid
from typing import Any

import arrow
import fasthtml.common as fh
from fasthtml.common import *
from fasthtml.common import (
    A,
    Div,
    P,
    Pre,
    RedirectResponse,
    Response,
)
from fasthtml.svg import Path as SvgPath
from monsterui.all import *
from monsterui.all import (
    H1,
    H3,
    Button,
    Card,
    CardBody,
    CardHeader,
)
from starlette.websockets import WebSocket, WebSocketDisconnect

from quantide.core.enums import FrameType
from quantide.data.sqlite import db
from quantide.service.discovery import strategy_loader
from quantide.service.risk_programs import (
    ALLOW_SAME_BAR_REPURCHASE_KEY,
    RISK_PROGRAMS_KEY,
)
from quantide.service.runner import BacktestRunner
from quantide.service.strategy_runtime import strategy_runtime_manager
from quantide.web.layouts.main import MainLayout
from quantide.web.pages.strategy_backtest_config import (
    _append_selected_risk_programs as _append_selected_risk_programs,
)
from quantide.web.pages.strategy_backtest_config import (
    _decode_backtest_prefill as _decode_backtest_prefill,
)
from quantide.web.pages.strategy_backtest_config import (
    _deployment_risk_config,
    _form_to_config,
    _parse_params,
    _parse_risk_program_selection,
)
from quantide.web.pages.strategy_backtest_config import (
    _split_backtest_params as _split_backtest_params,
)
from quantide.web.pages.strategy_backtest_views import (
    _backtest_parameters_text as _backtest_parameters_text,
)
from quantide.web.pages.strategy_backtest_views import (
    _build_backtest_action_cell,
    _build_backtest_rows,
    _build_strategy_rows,
)
from quantide.web.pages.strategy_backtest_views import (
    _build_backtest_deploy_button as _build_backtest_deploy_button,
)
from quantide.web.pages.strategy_backtest_views import (
    _build_backtest_name_cell as _build_backtest_name_cell,
)
from quantide.web.pages.strategy_backtest_views import (
    _build_feature_selection_panel as _build_feature_selection_panel,
)
from quantide.web.pages.strategy_backtest_views import (
    _build_param_inputs as _build_param_inputs,
)
from quantide.web.pages.strategy_backtest_views import (
    _build_risk_selection_panel as _build_risk_selection_panel,
)
from quantide.web.pages.strategy_backtest_views import (
    backtest_modal as backtest_modal,
)
from quantide.web.pages.strategy_deploy_views import (
    _delete_backtest_modal as _delete_backtest_modal,
)
from quantide.web.pages.strategy_deploy_views import (
    _live_deploy_modal,
    _paper_deploy_modal,
)
from quantide.web.pages.strategy_deploy_views import (
    _removed_risk_warning as _removed_risk_warning,
)
from quantide.web.pages.strategy_deploy_views import (
    _render_config_table as _render_config_table,
)
from quantide.web.pages.strategy_deploy_views import (
    _render_deploy_risk_selection as _render_deploy_risk_selection,
)
from quantide.web.pages.strategy_deploy_views import (
    _render_fee_inputs as _render_fee_inputs,
)
from quantide.web.pages.strategy_deploy_views import (
    _render_strategy_config_readonly as _render_strategy_config_readonly,
)
from quantide.web.pages.strategy_deploy_views import (
    delete_backtest_execute as delete_backtest_execute,
)
from quantide.web.pages.strategy_deploy_views import (
    delete_backtest_modal as delete_backtest_modal,
)
from quantide.web.pages.strategy_deployment import (
    _get_backtest_deploy_capabilities,
    _get_live_accounts,
    _get_market_data,
    _get_registry,
    _load_backtest_run_config,
    _render_deploy_result,
)
from quantide.web.pages.strategy_deployment import (
    _get_live_deploy_availability as _get_live_deploy_availability,
)
from quantide.web.pages.strategy_deployment import (
    _get_paper_deploy_availability as _get_paper_deploy_availability,
)
from quantide.web.pages.strategy_deployment import (
    _get_runtime as _get_runtime,
)
from quantide.web.pages.strategy_format import (
    _coerce_form_value as _coerce_form_value,
)
from quantide.web.pages.strategy_format import (
    _coerce_parameter_text as _coerce_parameter_text,
)
from quantide.web.pages.strategy_format import (
    _extract_params_from_info as _extract_params_from_info,
)
from quantide.web.pages.strategy_format import (
    _foldable_cell as _foldable_cell,
)
from quantide.web.pages.strategy_format import (
    _format_date as _format_date,
)
from quantide.web.pages.strategy_format import (
    _format_number as _format_number,
)
from quantide.web.pages.strategy_format import (
    _format_percent as _format_percent,
)
from quantide.web.pages.strategy_format import (
    _format_range as _format_range,
)
from quantide.web.pages.strategy_format import (
    _format_score as _format_score,
)
from quantide.web.pages.strategy_format import (
    _format_signed_pct as _format_signed_pct,
)
from quantide.web.pages.strategy_format import (
    _get_strategy_default_params,
    _global_loading_overlay,
    _htmx_indicator_style,
    _parse_checkbox,
    _strategy_dialog_modal,
    _strategy_modal_script,
    _supports_stock_selection,
    strategy_close_footer,
)
from quantide.web.pages.strategy_format import (
    _metric_value as _metric_value,
)
from quantide.web.pages.strategy_format import (
    _metric_value_class as _metric_value_class,
)
from quantide.web.pages.strategy_format import (
    _normalize_stats as _normalize_stats,
)
from quantide.web.pages.strategy_format import (
    _params_to_text as _params_to_text,
)
from quantide.web.pages.strategy_format import (
    _strategy_version as _strategy_version,
)
from quantide.web.pages.strategy_format import (
    _to_number as _to_number,
)
from quantide.web.pages.strategy_log_views import (
    _build_log_meta,
    _build_log_rows,
)
from quantide.web.pages.strategy_log_views import (
    _build_log_panel as _build_log_panel,
)
from quantide.web.pages.strategy_log_views import (
    _format_log_lines as _format_log_lines,
)
from quantide.web.pages.strategy_log_views import (
    load_saved_backtest_log_panel as load_saved_backtest_log_panel,
)
from quantide.web.pages.strategy_metrics import (
    _append_benchmark_series as _append_benchmark_series,
)
from quantide.web.pages.strategy_metrics import (
    _append_equity_after_history as _append_equity_after_history,
)
from quantide.web.pages.strategy_metrics import (
    _build_benchmark_returns as _build_benchmark_returns,
)
from quantide.web.pages.strategy_metrics import (
    _build_daily_positions,
    _build_daily_summary,
    _build_date_axis,
    _build_metrics_payload,
    _build_series_payload,
    _resolve_backtest_status,
)
from quantide.web.pages.strategy_metrics import (
    _build_trade_rows as _build_trade_rows,
)
from quantide.web.pages.strategy_metrics import (
    _is_stale_backtest_run as _is_stale_backtest_run,
)
from quantide.web.pages.strategy_report_views import (
    _build_backtest_sidebar_menu as _build_backtest_sidebar_menu,
)
from quantide.web.pages.strategy_report_views import (
    _build_cheat_on_close_badge as _build_cheat_on_close_badge,
)
from quantide.web.pages.strategy_report_views import (
    _normalize_backtest_tab as _normalize_backtest_tab,
)
from quantide.web.pages.strategy_report_views import (
    _render_backtest_report as _render_backtest_report,
)
from quantide.web.pages.strategy_report_views import (
    backtest_result as backtest_result,
)
from quantide.web.pages.strategy_routes import (
    _MODAL_MAX_HEIGHTS as _MODAL_MAX_HEIGHTS,
)
from quantide.web.pages.strategy_routes import (
    BACKTEST_REPORT_TABS as BACKTEST_REPORT_TABS,
)
from quantide.web.pages.strategy_routes import (
    BACKTEST_WIZARD_SCRIPT as BACKTEST_WIZARD_SCRIPT,
)
from quantide.web.pages.strategy_routes import (
    BENCHMARK_ASSET as BENCHMARK_ASSET,
)
from quantide.web.pages.strategy_routes import (
    BROKER_FEE_PARAM_DEFAULTS as BROKER_FEE_PARAM_DEFAULTS,
)
from quantide.web.pages.strategy_routes import (
    TRADE_PAIRS_PAGE_SIZE as TRADE_PAIRS_PAGE_SIZE,
)
from quantide.web.pages.strategy_routes import (
    TRADE_PARAM_KEYS as TRADE_PARAM_KEYS,
)
from quantide.web.pages.strategy_routes import (
    TRADE_PARAM_LABELS as TRADE_PARAM_LABELS,
)
from quantide.web.pages.strategy_routes import (
    TRADE_SORT_BUY_TIME as TRADE_SORT_BUY_TIME,
)
from quantide.web.pages.strategy_routes import (
    TRADE_SORT_DIRECTIONS as TRADE_SORT_DIRECTIONS,
)
from quantide.web.pages.strategy_routes import (
    TRADE_SORT_RETURN as TRADE_SORT_RETURN,
)
from quantide.web.pages.strategy_routes import (
    rt,
    strategy_app,
)
from quantide.web.pages.strategy_scanning import (
    _config_modal_html as _config_modal_html,
)
from quantide.web.pages.strategy_scanning import (
    _copy_requires_config_modal as _copy_requires_config_modal,
)
from quantide.web.pages.strategy_scanning import (
    _normalize_scan_directory as _normalize_scan_directory,
)
from quantide.web.pages.strategy_scanning import (
    _scan_scope_list as _scan_scope_list,
)
from quantide.web.pages.strategy_scanning import (
    _strategy_scan_toolbar,
)
from quantide.web.pages.strategy_scanning import (
    config_modal_route as config_modal_route,
)
from quantide.web.pages.strategy_scanning import (
    copy_scan_examples as copy_scan_examples,
)
from quantide.web.pages.strategy_scanning import (
    run_scan as run_scan,
)
from quantide.web.pages.strategy_scanning import (
    save_scan_config as save_scan_config,
)
from quantide.web.pages.strategy_scanning import (
    scan_confirm_modal as scan_confirm_modal,
)
from quantide.web.pages.strategy_selection import (
    _append_selection_table_rows as _append_selection_table_rows,
)
from quantide.web.pages.strategy_selection import (
    _get_default_selection_date as _get_default_selection_date,
)
from quantide.web.pages.strategy_selection import (
    _normalize_selection_output as _normalize_selection_output,
)
from quantide.web.pages.strategy_selection import (
    _render_stock_selection_modal as _render_stock_selection_modal,
)
from quantide.web.pages.strategy_selection import (
    _resolve_selection_date_notice as _resolve_selection_date_notice,
)
from quantide.web.pages.strategy_selection import (
    _selection_result_metadata as _selection_result_metadata,
)
from quantide.web.pages.strategy_selection import (
    run_strategy_select as run_strategy_select,
)
from quantide.web.pages.strategy_selection import (
    strategy_select_modal as strategy_select_modal,
)
from quantide.web.pages.strategy_trade_report import (
    _build_trade_pair_rows as _build_trade_pair_rows,
)
from quantide.web.pages.strategy_trade_report import (
    _build_trade_pair_table as _build_trade_pair_table,
)
from quantide.web.pages.strategy_trade_report import (
    _ordered_trade_pairs as _ordered_trade_pairs,
)
from quantide.web.pages.strategy_trade_report import (
    _paginate_trade_pairs as _paginate_trade_pairs,
)
from quantide.web.pages.strategy_trade_report import (
    _sort_trade_pair_rows as _sort_trade_pair_rows,
)
from quantide.web.pages.strategy_trade_report import (
    _trade_kline_modal_footer as _trade_kline_modal_footer,
)
from quantide.web.pages.strategy_trade_report import (
    _trade_kline_modal_title as _trade_kline_modal_title,
)
from quantide.web.pages.strategy_trade_report import (
    _trade_kline_modal_url as _trade_kline_modal_url,
)
from quantide.web.pages.strategy_trade_report import (
    _trade_pair_detail_table as _trade_pair_detail_table,
)
from quantide.web.pages.strategy_trade_report import (
    _trade_pair_nav_url as _trade_pair_nav_url,
)
from quantide.web.pages.strategy_trade_report import (
    trade_kline_modal as trade_kline_modal,
)


def _strategy_backtest_history(name):
    """Strategy backtest history."""
    portfolios = db.get_portfolios_by_strategy(name)
    history_rows = []

    if not portfolios.is_empty():
        # Sort by start time desc (assuming DB returns roughly in order, or we sort manually)
        # Polars sort:
        portfolios = portfolios.sort("start", descending=True)

        for row in portfolios.iter_rows(named=True):
            pid = row["portfolio_id"]
            start = row["start"]
            end = row["end"]

            history_rows.append(
                Tr(
                    Td(pid[:8]),
                    Td(str(start)),
                    Td(str(end)),
                    Td(
                        A(
                            "查看报告",
                            href=f"/strategy/backtest/{pid}",
                            cls="text-[#e41815] hover:underline",
                        ),
                    ),
                )
            )

    history_table = Table(
        Thead(Tr(Th("ID"), Th("开始时间"), Th("结束时间"), Th("操作"))),
        Tbody(*history_rows),
        cls=TableT.striped,
    )
    return history_table


@rt("/")
def index(req, session):
    layout = MainLayout(title="策略列表", user=session.get("auth"))
    layout.header_active = "策略"
    layout.sidebar_menu = [
        {
            "title": "策略列表",
            "url": "/strategy",
            ("icon_path"): (
                "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 "
                "5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
            ),
            "active": True,
        },
        {
            "title": "回测报告",
            "url": "/strategy#backtest-list",
            ("icon_path"): (
                "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 "
                "0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 "
                "2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
            ),
        },
    ]

    strategy_loader.ensure_builtin_strategies()
    strategies = strategy_loader.load_from_cache()
    strategy_rows = _build_strategy_rows(strategies)
    backtest_rows = _build_backtest_rows(strategies, **_get_backtest_deploy_capabilities(req))

    strategy_table = Table(
        Thead(
            Tr(
                Th("操作", cls="px-6 py-3 font-medium w-20"),
                Th("名称", cls="px-6 py-3 font-medium"),
                Th("简介", cls="px-6 py-3 font-medium"),
                Th("版本", cls="px-6 py-3 font-medium"),
                Th("历史回测", cls="px-6 py-3 font-medium"),
                Th("最新回测", cls="px-6 py-3 font-medium"),
                cls="text-left text-sm text-gray-600 border-b border-gray-200",
            )
        ),
        Tbody(*strategy_rows, cls="text-sm"),
        cls="w-full",
    )

    backtest_table = Table(
        Thead(
            Tr(
                Th("策略名", cls="px-6 py-3 font-medium"),
                Th("版本", cls="px-6 py-3 font-medium"),
                Th("参数", cls="px-6 py-3 font-medium"),
                Th("回测区间", cls="px-6 py-3 font-medium"),
                Th("年化收益", cls="px-6 py-3 font-medium"),
                Th("夏普", cls="px-6 py-3 font-medium"),
                Th("最大回撤", cls="px-6 py-3 font-medium"),
                Th("索提诺", cls="px-6 py-3 font-medium"),
                Th("操作", cls="px-6 py-3 font-medium"),
                cls="text-left text-sm text-gray-600 border-b border-gray-200",
            )
        ),
        Tbody(*backtest_rows, cls="text-sm"),
        cls="w-full",
    )

    section_toggle_script = Script(src="/static/strategy-sidebar.js")

    layout.main_block = lambda: Div(
        Div(
            Nav(
                A("首页", href="/", cls="hover:text-[#e41815]"),
                Span(">", cls="text-gray-400"),
                A("策略", href="/strategy", cls="hover:text-[#e41815]"),
                Span(">", cls="text-gray-400"),
                Span("策略列表", cls="text-gray-900 font-medium"),
                cls="flex w-fit items-center justify-start space-x-2 text-sm text-gray-600",
            ),
            cls="mb-4",
        ),
        Div(
            Div(
                Div(
                    H2("策略列表", cls="text-lg font-semibold text-gray-900"),
                    P(
                        "内置示例已自动加载；如需复制到自己的策略目录，请点击“复制示例策略”。",
                        cls="mt-1 text-sm text-gray-500",
                    ),
                ),
                _strategy_scan_toolbar(),
                cls="p-6 border-b border-gray-200 flex justify-between items-center",
            ),
            Div(strategy_table, cls="overflow-x-auto"),
            cls="bg-white rounded-lg shadow mb-6",
            id="strategy-list-section",
        ),
        Div(
            Div(
                Div(
                    H2("回测报告列表", cls="text-lg font-semibold text-gray-900"),
                    Div(id="deploy-result", cls="mt-2 text-sm"),
                    cls="flex flex-col items-start",
                ),
                Div(
                    Div(
                        Input(
                            type="text",
                            placeholder="按策略名过滤...",
                            cls="q-input text-gray-900",
                            style="padding-left: 2.5rem; width: 16rem;",
                        ),
                        Svg(
                            SvgPath(
                                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
                                **{
                                    "stroke-linecap": "round",
                                    "stroke-linejoin": "round",
                                    "stroke-width": "2",
                                },
                            ),
                            cls="w-5 h-5 text-gray-400",
                            style="position: absolute; left: 0.75rem; top: 50%; "
                            "transform: translateY(-50%); pointer-events: none;",
                            fill="none",
                            stroke="currentColor",
                            viewBox="0 0 24 24",
                        ),
                        cls="relative",
                    ),
                    fh.Select(
                        fh.Option("按年化收益排序", value="annual", selected=True),
                        fh.Option("按夏普比率排序", value="sharpe"),
                        fh.Option("按最大回撤排序", value="drawdown"),
                        fh.Option("按索提诺排序", value="sortino"),
                        cls="uk-select uk-form-small text-gray-900",
                    ),
                    cls="flex items-center space-x-4",
                ),
                cls="p-6 border-b border-gray-200 flex justify-between items-center",
            ),
            Div(backtest_table, cls="overflow-x-auto"),
            cls="bg-white rounded-lg shadow",
            id="backtest-list",
        ),
        section_toggle_script,
        _strategy_modal_script(),
        _htmx_indicator_style(),
        _global_loading_overlay(),
        Div(id="modal-container"),
        cls="space-y-6",
    )

    return layout.render()


@rt("/{name}")
def strategy_detail(req, session, name: str):
    layout = MainLayout(title=f"策略详情 - {name}", user=session.get("auth"))

    strategies = strategy_loader.load_from_cache()

    if name not in strategies:
        return RedirectResponse("/strategy")

    cls = strategies[name]
    doc = cls.__doc__ or "暂无描述"
    params = _get_strategy_default_params(cls)

    # Get history
    history_table = _strategy_backtest_history(name)

    detail_actions: list[Any] = [
        Button(
            "运行回测",
            type="button",
            cls=(
                "px-4 py-2 bg-[#e41815] text-white rounded-lg "
                "hover:bg-[#c91412] text-sm font-medium"
            ),
            hx_get=f"/strategy/{name}/backtest/modal",
            hx_target="#modal-container",
            hx_indicator="#global-loading",
        )
    ]
    detail_actions.append(
        A(
            "参数优化",
            title="在样本内挑选参数并用样本外区间检验",
            href=f"/strategy/{name}/optimize",
            cls=(
                "uk-btn px-4 py-2 bg-[#e41815] text-white rounded-lg "
                "hover:bg-[#c91412] text-sm font-medium inline-block"
            ),
        )
    )
    if _supports_stock_selection(cls):
        detail_actions.append(
            Button(
                "一键选股",
                type="button",
                cls=(
                    "px-4 py-2 bg-green-600 text-white rounded-lg "
                    "hover:bg-green-700 text-sm font-medium"
                ),
                hx_get=f"/strategy/{name}/select/modal",
                hx_target="#modal-container",
                hx_indicator="#global-loading",
            )
        )

    layout.main_block = lambda: Div(
        Div(
            A(
                "← 返回列表",
                href="/strategy",
                cls="text-gray-500 hover:text-gray-800 mb-4 inline-block",
            ),
            Div(
                Div(
                    H1(name, cls="text-3xl font-bold mb-2"),
                    P(doc, cls="text-gray-600"),
                ),
                Div(*detail_actions, cls="flex items-center gap-3 shrink-0"),
                cls=("flex flex-col md:flex-row md:items-start md:justify-between gap-4 mb-6"),
            ),
            Card(
                CardHeader(H3("默认参数")),
                CardBody(Pre(str(params), cls="bg-gray-50 p-4 rounded text-sm")),
                cls="mb-6",
            ),
            Div(
                H3("回测历史", cls="text-xl font-bold mb-4"),
                history_table,
                cls="bg-white p-6 rounded-lg shadow-sm border border-gray-100",
            ),
            _strategy_modal_script(),
            _htmx_indicator_style(),
            _global_loading_overlay(),
            Div(id="modal-container"),
            cls="max-w-4xl mx-auto py-8",
        )
    )

    return layout.render()


@rt("/{name}/backtest/run", methods=["POST"])
async def run_backtest(req, name: str):
    form = await req.form()

    try:
        start_date = arrow.get(form.get("start_date")).date()
        end_date = arrow.get(form.get("end_date")).date()
        initial_cash = float(form.get("initial_cash", 1000000))
        save_logs = _parse_checkbox(form.get("save_logs"))
        cls, config, interval = _backtest_form_strategy(name, form)

        portfolio_id = uuid.uuid4().hex
        strategy_runtime_manager.create_backtest_runtime(
            portfolio_id=portfolio_id,
            strategy_name=name,
            config=config,
            interval=interval,
            start_date=str(start_date),
            end_date=str(end_date),
            initial_cash=initial_cash,
            save_logs=save_logs,
        )
        _launch_backtest_job(
            cls, config, start_date, end_date, interval, initial_cash, portfolio_id, save_logs
        )
        return Response(
            "",
            headers={"HX-Redirect": f"/strategy/backtest/{portfolio_id}"},
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        return Div(
            Div(f"回测失败: {str(e)}", cls="text-red-500 mb-4"),
            Button("关闭", cls="btn btn-secondary", onclick="this.closest('.modal').remove()"),
            cls="p-4 bg-white rounded shadow",
        )


@rt("/backtest/{portfolio_id}/deploy/paper/modal")
def deploy_backtest_to_paper_modal(portfolio_id: str):
    """渲染转入仿真确认弹窗。"""
    config, default_config = _load_backtest_run_config(portfolio_id)
    run = strategy_runtime_manager.get_backtest_run_or_resolve(portfolio_id)
    interval = run.interval if run is not None else "1d"
    return _paper_deploy_modal(
        portfolio_id,
        config=config,
        default_config=default_config,
        interval=interval,
    )


@rt("/backtest/{portfolio_id}/deploy/live/modal")
def deploy_backtest_to_live_modal(req, portfolio_id: str):
    """渲染转入实盘确认弹窗。"""
    config, default_config = _load_backtest_run_config(portfolio_id)
    run = strategy_runtime_manager.get_backtest_run_or_resolve(portfolio_id)
    interval = run.interval if run is not None else "1d"
    return _live_deploy_modal(
        portfolio_id,
        _get_live_accounts(req),
        config=config,
        default_config=default_config,
        interval=interval,
    )


@rt("/backtest/{portfolio_id}/deploy/paper", methods=["POST"])
async def deploy_backtest_to_paper(req, portfolio_id: str):
    form = await req.form()
    principal_raw = str(form.get("paper_principal", "1000000") or "1000000")
    try:
        principal = float(principal_raw)
    except ValueError:
        return _paper_deployment_error(portfolio_id, principal_raw, "请输入有效的仿真本金")
    if principal <= 0:
        return _paper_deployment_error(portfolio_id, principal_raw, "仿真本金必须大于 0")
    registry = _get_registry(req)
    if registry is None:
        return _paper_deployment_error(portfolio_id, principal_raw, "运行时未初始化")
    existing_runtime = strategy_runtime_manager.get_active_backtest_deployment(
        portfolio_id, "paper"
    )
    if existing_runtime is not None:
        return (
            Div(id="modal-container"),
            _render_deploy_result(
                f"该回测已在仿真中：{existing_runtime.portfolio_id}，策略ID={existing_runtime.strategy_id}",
                is_error=False,
            ),
            _build_backtest_action_cell(
                portfolio_id,
                hx_swap_oob=True,
                **_get_backtest_deploy_capabilities(req),
            ),
        )
    try:
        custom_config, warning_message = _deployment_form_config(portfolio_id, form)
        runtime = strategy_runtime_manager.deploy_to_paper(
            portfolio_id=portfolio_id,
            principal=principal,
            registry=registry,
            market_data=_get_market_data(req),
            config=custom_config,
        )
        return (
            Div(id="modal-container"),
            _render_deploy_result(
                f"已转入仿真：{runtime.portfolio_id}，策略ID={runtime.strategy_id}"
                + (f"；{warning_message}" if warning_message else ""),
                is_error=False,
            ),
            _build_backtest_action_cell(
                portfolio_id,
                hx_swap_oob=True,
                **_get_backtest_deploy_capabilities(req),
            ),
        )
    except Exception as e:
        return _paper_deployment_error(portfolio_id, principal_raw, f"转入仿真失败: {e}")


@rt("/backtest/{portfolio_id}/deploy/live", methods=["POST"])
async def deploy_backtest_to_live(req, portfolio_id: str):
    form = await req.form()
    account_id = str(form.get("live_account_id") or "gateway:default")
    registry = _get_registry(req)
    if registry is None:
        config, default_config = _load_backtest_run_config(portfolio_id)
        return _live_deploy_modal(portfolio_id, [], config=config, default_config=default_config)
    live_accounts = _get_live_accounts(req)
    if not live_accounts:
        config, default_config = _load_backtest_run_config(portfolio_id)
        return _live_deploy_modal(portfolio_id, [], config=config, default_config=default_config)
    existing_runtime = strategy_runtime_manager.get_active_backtest_deployment(portfolio_id, "live")
    if existing_runtime is not None:
        return (
            Div(id="modal-container"),
            _render_deploy_result(
                f"该回测已在实盘中：{existing_runtime.portfolio_id}，策略ID={existing_runtime.strategy_id}",
                is_error=False,
            ),
            _build_backtest_action_cell(
                portfolio_id,
                hx_swap_oob=True,
                **_get_backtest_deploy_capabilities(req),
            ),
        )
    try:
        custom_config, warning_message = _deployment_form_config(portfolio_id, form)
        runtime = strategy_runtime_manager.deploy_to_live(
            portfolio_id=portfolio_id,
            account_id=account_id,
            registry=registry,
            market_data=_get_market_data(req),
            config=custom_config,
        )
        return (
            Div(id="modal-container"),
            _render_deploy_result(
                f"已转入实盘：{runtime.portfolio_id}，策略ID={runtime.strategy_id}"
                + (f"；{warning_message}" if warning_message else ""),
                is_error=False,
            ),
            _build_backtest_action_cell(
                portfolio_id,
                hx_swap_oob=True,
                **_get_backtest_deploy_capabilities(req),
            ),
        )
    except Exception as e:
        return _strategy_dialog_modal(
            "转入实盘失败",
            Div(P(str(e), cls="text-sm text-red-600")),
            strategy_close_footer(),
            modal_id="deploy-live-error-modal",
            width_cls="max-w-md",
        )


async def backtest_ws(websocket: WebSocket) -> None:
    """回测报告 websocket 推送。

    Args:
        websocket: WebSocket 连接
    """
    await websocket.accept()
    portfolio_id = websocket.path_params.get("portfolio_id")
    if not portfolio_id:
        await websocket.close(code=1008)
        return
    try:
        while True:
            status, backtest_error = _resolve_backtest_status(portfolio_id)
            date_axis = _build_date_axis(portfolio_id)
            payload = {
                "status": status,
                "error": backtest_error,
                "metrics": _build_metrics_payload(portfolio_id),
                "series": _build_series_payload(portfolio_id, date_axis),
                "daily_summary": _build_daily_summary(portfolio_id),
                "positions": _build_daily_positions(portfolio_id),
                "logs": _build_log_rows(portfolio_id, limit=200),
                "log_meta": _build_log_meta(portfolio_id),
            }
            await websocket.send_text(json.dumps(payload))
            if status != "running":
                await websocket.close()
                return
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        return


strategy_app.add_websocket_route("/backtest/{portfolio_id}/ws", backtest_ws)


def _paper_deployment_error(portfolio_id, principal_raw, message):
    config, defaults = _load_backtest_run_config(portfolio_id)
    run = strategy_runtime_manager.get_backtest_run_or_resolve(portfolio_id)
    return _paper_deploy_modal(
        portfolio_id,
        principal=principal_raw,
        config=config,
        default_config=defaults,
        error_message=message,
        interval=run.interval if run is not None else "1d",
    )


def _deployment_form_config(portfolio_id, form):
    """Apply risk selections using the immutable period of the source backtest."""
    base_config, _ = _load_backtest_run_config(portfolio_id)
    run = strategy_runtime_manager.get_backtest_run_or_resolve(portfolio_id)
    risk_config, warning = _deployment_risk_config(
        form,
        base_config,
        run.strategy_name if run is not None else "",
        run.interval if run is not None else "1d",
    )
    return _form_to_config(form, risk_config), warning


def _backtest_form_strategy(name, form):
    """Resolve strategy configuration and validate its declared interval."""
    config = _parse_params(form)

    strategies = strategy_loader.load_from_cache()
    cls = strategies.get(name)

    if not cls:
        raise Exception("Strategy not found")

    expected_interval = BacktestRunner.strategy_interval(cls)
    submitted_interval = form.get("interval")
    interval = str(submitted_interval or expected_interval).strip().lower()
    BacktestRunner.validate_strategy_interval(cls, config, interval)

    if form.get("risk_selection_present"):
        selected, allow_same_bar = _parse_risk_program_selection(form, cls, str(interval))
        config[RISK_PROGRAMS_KEY] = selected
        config[ALLOW_SAME_BAR_REPURCHASE_KEY] = allow_same_bar
    return cls, config, interval


def _launch_backtest_job(
    cls, config, start_date, end_date, interval, initial_cash, portfolio_id, save_logs
):
    """Run the validated backtest and persist its terminal status."""
    runner = BacktestRunner()
    from quantide.service.background import run_blocking, start_background

    def _job() -> None:
        try:
            asyncio.run(
                runner.run(
                    strategy_cls=cls,
                    config=config,
                    start_date=start_date,
                    end_date=end_date,
                    frame_type=FrameType(interval),
                    initial_cash=initial_cash,
                    portfolio_id=portfolio_id,
                    save_logs=save_logs,
                )
            )
            strategy_runtime_manager.complete_backtest_runtime(portfolio_id)
        except Exception as e:
            strategy_runtime_manager.complete_backtest_runtime(portfolio_id, error=str(e))
            raise

    start_background(run_blocking(_job, on_cancel=runner.stop))
