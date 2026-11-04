"""Strategy report views."""

import json
from typing import Any

import fasthtml.common as fh
from fasthtml.common import *
from fasthtml.common import (
    Div,
    Span,
)
from monsterui.all import *

from quantide.service.strategy_runtime import strategy_runtime_manager
from quantide.web.layouts.main import MainLayout
from quantide.web.pages.strategy_format import (
    _format_number,
    _format_percent,
    _metric_value_class,
    _strategy_modal_script,
)
from quantide.web.pages.strategy_log_views import (
    _build_log_panel,
    _build_log_rows,
)
from quantide.web.pages.strategy_metrics import (
    _build_daily_positions,
    _build_date_axis,
    _build_metrics_payload,
    _build_series_payload,
    _resolve_backtest_status,
)
from quantide.web.pages.strategy_routes import (
    BACKTEST_REPORT_TABS,
    TRADE_SORT_BUY_TIME,
    TRADE_SORT_DIRECTIONS,
    TRADE_SORT_RETURN,
    rt,
)
from quantide.web.pages.strategy_trade_report import (
    _build_trade_pair_rows,
    _build_trade_pair_table,
    _paginate_trade_pairs,
    _sort_trade_pair_rows,
)
from quantide.web.template_assets import render_asset


def _trade_and_position_tables(portfolio_id, trade_sort, trade_direction, trade_page_param):
    """Trade and position tables."""
    trade_pair_rows = _build_trade_pair_rows(portfolio_id)
    trade_pair_rows = _sort_trade_pair_rows(trade_pair_rows, trade_sort, trade_direction)
    trade_pair_rows, trade_page, trade_total_pages, trade_total = _paginate_trade_pairs(
        trade_pair_rows, trade_page_param
    )
    positions_rows = _build_daily_positions(portfolio_id)
    trade_table = _build_trade_pair_table(
        portfolio_id,
        trade_pair_rows,
        trade_page,
        trade_total_pages,
        trade_total,
        sort=trade_sort,
        direction=trade_direction,
    )
    position_trs = []
    last_date = None
    for row in positions_rows:
        dt = row.get("dt")
        if dt != last_date:
            position_trs.append(Tr(Td(dt, colspan="6", cls="bg-gray-50 font-semibold")))
            last_date = dt
        position_trs.append(
            Tr(
                Td(row.get("asset", "")),
                Td(f"{row.get('shares', 0):.2f}"),
                Td(f"{row.get('avail', 0):.2f}"),
                Td(f"{row.get('price', 0):.2f}"),
                Td(f"{row.get('mv', 0):.2f}"),
                Td(f"{row.get('profit', 0):.2f}"),
            )
        )
    positions_table = Table(
        Thead(Tr(Th("标的"), Th("持仓"), Th("可用"), Th("价格"), Th("市值"), Th("浮盈"))),
        Tbody(*position_trs, id="positions_body"),
        cls=TableT.striped + " text-xs",
    )
    return trade_table, positions_table


def _render_backtest_report(query_params, portfolio_id, active_tab, layout, trade_page_param):
    """Populate the selected report tab and its supporting data views."""
    trade_sort = str(query_params.get("sort") or "").strip()
    if trade_sort not in {TRADE_SORT_BUY_TIME, TRADE_SORT_RETURN}:
        trade_sort = ""
    trade_direction = str(query_params.get("dir") or "asc").strip()
    if trade_direction not in TRADE_SORT_DIRECTIONS:
        trade_direction = "asc"
    layout.sidebar_menu = _build_backtest_sidebar_menu(portfolio_id, active_tab)

    status, backtest_error = _resolve_backtest_status(portfolio_id)
    trade_table, positions_table = _trade_and_position_tables(
        portfolio_id, trade_sort, trade_direction, trade_page_param
    )
    active_panel = {
        "overview": _report_overview(portfolio_id),
        "trades": _report_data_panel("交易详情", "trades", trade_table),
        "positions": _report_data_panel("每日持仓", "positions", positions_table),
        "logs": _build_log_panel(
            portfolio_id=portfolio_id, status=status, rows=_build_log_rows(portfolio_id, limit=200)
        ),
    }[active_tab]
    layout.main_block = lambda: Div(
        Script(src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"),
        Div(
            Div(
                A(
                    "← 返回策略详情",
                    href="javascript:history.back()",
                    cls="text-gray-500 hover:text-gray-800 mb-4 inline-block",
                ),
                _report_error_panel(backtest_error),
                _build_cheat_on_close_badge(portfolio_id),
                active_panel,
                cls="max-w-6xl mx-auto py-8",
            )
        ),
        _strategy_modal_script(),
        Div(id="modal-container"),
    )


def _normalize_backtest_tab(value: Any) -> str:
    """规范化回测报告标签。"""
    key = str(value or "overview").strip().lower()
    if key not in BACKTEST_REPORT_TABS:
        return "overview"
    return key


def _build_backtest_sidebar_menu(
    portfolio_id: str,
    active_tab: str,
) -> list[dict[str, Any]]:
    """构建回测报告侧边栏。"""
    children = []
    for tab, title in BACKTEST_REPORT_TABS.items():
        children.append(
            {
                "title": title,
                "url": f"/strategy/backtest/{portfolio_id}?tab={tab}",
                "active": tab == active_tab,
            }
        )

    return [
        {
            "title": "策略列表",
            "url": "/strategy",
            ("icon_path"): (
                "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 "
                "5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
            ),
        },
        {
            "title": "回测报告",
            "url": f"/strategy/backtest/{portfolio_id}",
            ("icon_path"): (
                "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 "
                "0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 "
                "2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
            ),
            "active": True,
            "children": children,
        },
    ]


def _build_cheat_on_close_badge(portfolio_id: str):
    """回测报告 header 区 amber badge (#49).

    当 cheat_on_close=True 时显示 amber badge + cheat_on_close_time, 提示用户
    此回测使用了 14:57 forming bar 撮合, 与实盘有偏差.

    进程重启后 _backtest_history 为空, 必须回退到 _resolve_backtest_run 从持久化
    specs 恢复 cheat metadata, 否则历史报告永远走 hidden 分支.
    """
    run = strategy_runtime_manager.get_backtest_run_or_resolve(portfolio_id)
    if run is None or not getattr(run, "cheat_on_close", False):
        return Div(id="cheat_badge", cls="hidden")
    cheat_tm = getattr(run, "cheat_on_close_time", "") or "?"
    return Div(
        Span(
            "⚠ ",
            Span("cheat_on_close"),
            Span(f" @ {cheat_tm}", cls="font-mono"),
            cls=(
                "inline-flex items-center px-3 py-1 rounded-full "
                "text-xs font-semibold bg-gray-100 text-gray-700 "
                "border border-gray-300"
            ),
        ),
        Span(
            " 撮合价基于 forming bar (实盘有 < 1 tick 偏差)",
            cls="ml-2 text-xs text-gray-500",
        ),
        cls="mb-4 flex items-center",
        id="cheat_badge",
    )


@rt("/backtest/{portfolio_id}")
def backtest_result(req, session, portfolio_id: str):
    layout = MainLayout(title="回测报告", user=session.get("auth"))
    layout.header_active = "策略"
    query_params = getattr(req, "query_params", {}) or {}
    active_tab = _normalize_backtest_tab(query_params.get("tab"))
    try:
        trade_page_param = int(query_params.get("page") or 1)
    except (TypeError, ValueError):
        trade_page_param = 1
    _render_backtest_report(query_params, portfolio_id, active_tab, layout, trade_page_param)

    return layout.render()


REPORT_METRICS = [
    ("annual_return", "年化收益", "percent"),
    ("total_returns", "累计收益", "percent"),
    ("max_drawdown", "最大回撤", "percent"),
    ("volatility", "波动率", "percent"),
    ("sharpe", "夏普比率", "number"),
    ("sortino", "索提诺比率", "number"),
    ("calmar", "卡玛比率", "number"),
    ("alpha", "Alpha", "number"),
    ("beta", "Beta", "number"),
    ("win_rate", "胜率", "percent"),
    ("profit_factor", "盈亏比", "number"),
    ("payoff_ratio", "收益风险比", "number"),
    ("avg_return", "平均收益", "percent"),
    ("avg_win", "平均盈利", "percent"),
    ("avg_loss", "平均亏损", "percent"),
    ("best_day", "最佳单日", "percent"),
    ("worst_day", "最差单日", "percent"),
    ("tail_ratio", "尾部比", "number"),
    ("skew", "偏度", "number"),
    ("kurtosis", "峰度", "number"),
    ("value_at_risk", "VaR", "percent"),
    ("information_ratio", "信息比率", "number"),
]


def _report_metrics(metrics_payload):
    """Render the named metrics with one formatting rule."""
    metrics_entries = []
    for key, label, fmt in REPORT_METRICS:
        value = metrics_payload.get(key)
        value_text = _format_percent(value) if fmt == "percent" else _format_number(value)
        value_cls = _metric_value_class(value)
        metrics_entries.append(
            Div(
                Span(f"{label}:", cls="text-gray-500"),
                Span(value_text, id=f"metric_{key}", cls=f"{value_cls} ml-1"),
                cls="text-sm",
            )
        )
    metrics_text = Div(*metrics_entries, cls="flex flex-wrap gap-x-6 gap-y-2")
    return metrics_text


def _report_overview(portfolio_id):
    """Compose the metrics, date filters and equity chart for one report."""
    date_axis = _build_date_axis(portfolio_id)
    series_payload = _build_series_payload(portfolio_id, date_axis)
    metrics_text = _report_metrics(_build_metrics_payload(portfolio_id))
    filter_start_value = date_axis[0] if date_axis else ""
    filter_end_value = date_axis[-1] if date_axis else ""
    chart_id = f"chart_{portfolio_id}"
    chart_script = Script(
        render_asset(
            "backtest-chart.js.tmpl",
            chart_id=chart_id,
            date_axis_json=json.dumps(series_payload["date_axis"]),
            total_series_json=json.dumps(series_payload["total"]),
            benchmark_series_json=json.dumps(series_payload["benchmark"]),
            daily_pnl_json=json.dumps(series_payload["daily_pnl"]),
            trade_count_json=json.dumps(series_payload["trade_count"]),
            portfolio_id=portfolio_id,
            metric_format_json=json.dumps({key: fmt for key, _, fmt in REPORT_METRICS}),
        )
    )
    overview_panel = Div(
        Div(
            H3("收益概述", cls="text-xl font-bold mb-3"),
            metrics_text,
            cls="mb-4",
            id="overview",
        ),
        Div(
            H3("收益曲线", cls="text-xl font-bold mb-4"),
            Div(
                Div(
                    fh.Label("开始日期", cls="block text-xs text-gray-500 mb-1"),
                    Input(
                        id="filter_start",
                        type="date",
                        value=filter_start_value,
                        cls="input input-sm",
                    ),
                    cls="flex flex-col",
                ),
                Div(
                    fh.Label("结束日期", cls="block text-xs text-gray-500 mb-1"),
                    Input(
                        id="filter_end",
                        type="date",
                        value=filter_end_value,
                        cls="input input-sm",
                    ),
                    cls="flex flex-col",
                ),
                cls="flex flex-wrap gap-4 mb-4",
            ),
            Div(
                id=chart_id,
                cls="w-full h-[560px] bg-white p-4 rounded-xl shadow-sm border border-gray-100",
            ),
            chart_script,
            cls="mt-6",
        ),
    )
    return overview_panel


def _report_error_panel(backtest_error):
    return (
        Div(
            H3("运行错误", cls="text-sm font-semibold text-red-700 mb-2"),
            P(backtest_error, id="backtest_error", cls="text-sm text-red-600 whitespace-pre-wrap"),
            cls="mb-4 rounded-lg border border-red-200 bg-red-50 p-4",
        )
        if backtest_error
        else Div(id="backtest_error", cls="hidden")
    )


def _report_data_panel(title, panel_id, table):
    return Div(
        H3(title, cls="text-xl font-bold mb-4"),
        table,
        cls="bg-white p-6 rounded-lg shadow-sm border border-gray-100 mt-6",
        id=panel_id,
    )
