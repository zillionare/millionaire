"""参数优化页面：配置、后台任务进度、结果对比与样本外告警。"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

import arrow
import fasthtml.common as fh
from fasthtml.common import *
from fasthtml.common import (
    H1,
    H3,
    H4,
    A,
    Button,
    Div,
    Form,
    Input,
    P,
    RedirectResponse,
    Script,
    Span,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
)
from loguru import logger
from starlette.requests import Request

from quantide.service.optimization_tasks import (
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    cancel_optimization,
    get_task,
    list_tasks,
    objective_label,
    start_optimization,
)
from quantide.service.param_optimizer import (
    MODES,
    OBJECTIVES,
    OptimizationSpec,
    parse_metric,
)
from quantide.web.layouts.main import MainLayout
from quantide.web.services.optimization_forms import (
    _parse_param_values as _parse_param_values,
)
from quantide.web.services.optimization_forms import (
    _parse_string_list as _parse_string_list,
)
from quantide.web.services.optimization_forms import (
    _supply_parameter_grid_defaults as _supply_parameter_grid_defaults,
)
from quantide.web.services.optimization_forms import (
    form_choice,
    form_number,
    optimization_parameters,
)
from quantide.web.session_data import SessionData

from .strategy import rt

OPTIMIZE_POLL_SECONDS = 2


def _append_optimization_result_rows(
    ordered: list[dict[str, Any]],
    param_keys: list[str],
    task: dict[str, Any],
    rows: list[Any],
    is_risk: bool,
    name: str,
) -> None:
    """Append optimization result rows."""
    for index, row in enumerate(ordered, start=1):
        params = row.get("params") or {}
        in_sample = row.get("in_sample") or {}
        out_sample = row.get("out_sample") or {}
        overfit = bool(row.get("overfit"))
        param_text = ", ".join(f"{key}={params.get(key)}" for key in param_keys) or "-"
        prefill = _encode_prefill(
            {
                "params": params,
                "start_date": task.get("spec", {}).get("start_date"),
                "end_date": task.get("spec", {}).get("end_date"),
            }
        )
        rows.append(
            Tr(
                Td(str(index), cls="text-xs"),
                Td(param_text, cls="text-xs font-mono"),
                Td(_objective_cell(row.get("objective"), is_risk), cls="text-xs"),
                Td(_objective_cell(row.get("out_objective"), is_risk), cls="text-xs"),
                Td(_metric(in_sample, "CAGR"), cls="text-xs"),
                Td(_metric(out_sample, "CAGR"), cls="text-xs"),
                Td(_metric(in_sample, "Max Drawdown"), cls="text-xs"),
                Td(
                    Span("疑似过拟合", cls="text-xs text-gray-500 bg-gray-100 px-1 rounded")
                    if overfit
                    else Span("-", cls="text-xs text-gray-400"),
                ),
                Td(
                    A(
                        "用这组参数回测",
                        href=(f"/strategy/{name}/backtest/modal?prefill={prefill}"),
                        cls="text-xs text-[#e41815] hover:underline",
                        hx_get=f"/strategy/{name}/backtest/modal?prefill={prefill}",
                        hx_target="#modal-container",
                        hx_indicator="#global-loading",
                    ),
                    cls="text-xs",
                ),
            )
        )


def _optimization_form_and_task(
    strategy_params: dict[str, Any], req: Request, name: str
) -> tuple[Any, Any]:
    """Optimization form and task."""
    param_inputs = []
    for key, value in strategy_params.items():
        param_inputs.append(
            Div(
                Span(key, cls="text-sm font-medium text-gray-500 w-48 shrink-0"),
                Input(
                    name=f"param_{key}",
                    value=(
                        ", ".join(str(v) for v in value)
                        if isinstance(value, (list, tuple))
                        else str(value)
                    ),
                    placeholder="多个取值用逗号分隔，如 45, 90, 120",
                    cls="input input-sm w-full",
                ),
                cls="flex items-center gap-3 mb-2",
            )
        )

    query_params = getattr(req, "query_params", {}) or {}
    task_id = str(query_params.get("task_id") or "")
    sort_key = str(query_params.get("sort") or DEFAULT_SORT)
    if sort_key not in SORT_COLUMNS:
        sort_key = DEFAULT_SORT
    sort_desc = str(query_params.get("dir") or "desc") != "asc"

    today = arrow.now().format("YYYY-MM-DD")
    form = Form(
        Div(
            Div(
                Div(
                    Span("优化目标", cls="text-sm font-medium text-gray-500 w-28 shrink-0"),
                    fh.Select(
                        *[
                            fh.Option(
                                objective_label(obj),
                                value=obj,
                                selected="selected" if obj == "sharpe" else None,
                            )
                            for obj in OBJECTIVES
                        ],
                        name="objective",
                        cls="uk-select uk-form-small flex-1 text-gray-700",
                    ),
                    cls="flex items-center gap-3 mb-2",
                ),
                Div(
                    Span("搜索方式", cls="text-sm font-medium text-gray-500 w-28 shrink-0"),
                    fh.Select(
                        fh.Option("网格枚举", value="grid", selected="selected"),
                        fh.Option("随机采样", value="random"),
                        name="mode",
                        cls="uk-select uk-form-small flex-1 text-gray-700",
                    ),
                    cls="flex items-center gap-3 mb-2",
                ),
                Div(
                    Span("随机样本数", cls="text-sm font-medium text-gray-500 w-28 shrink-0"),
                    Input(
                        name="n_random",
                        type="number",
                        value="20",
                        cls="input input-sm w-full",
                    ),
                    cls="flex items-center gap-3 mb-2",
                ),
                Div(
                    Span("开始日期", cls="text-sm font-medium text-gray-500 w-28 shrink-0"),
                    Input(
                        name="start_date",
                        type="date",
                        value="2024-01-01",
                        required=True,
                        cls="input input-sm w-full",
                    ),
                    cls="flex items-center gap-3 mb-2",
                ),
                Div(
                    Span("结束日期", cls="text-sm font-medium text-gray-500 w-28 shrink-0"),
                    Input(
                        name="end_date",
                        type="date",
                        value=today,
                        required=True,
                        cls="input input-sm w-full",
                    ),
                    cls="flex items-center gap-3 mb-2",
                ),
                Div(
                    Span("区间长度(年)", cls="text-sm font-medium text-gray-500 w-28 shrink-0"),
                    Input(
                        name="years",
                        type="number",
                        value="2",
                        step="0.5",
                        cls="input input-sm w-full",
                    ),
                    cls="flex items-center gap-3 mb-1",
                ),
                Div(
                    Span("样本内占比", cls="text-sm font-medium text-gray-500 w-28 shrink-0"),
                    Input(
                        name="in_sample_ratio",
                        type="number",
                        value="0.7",
                        step="0.05",
                        min="0.1",
                        max="0.9",
                        cls="input input-sm w-full",
                    ),
                    cls="flex items-center gap-3 mb-1",
                ),
                Div(
                    Span("并发进程数", cls="text-sm font-medium text-gray-500 w-28 shrink-0"),
                    Input(
                        name="max_workers",
                        type="number",
                        value="4",
                        min="1",
                        max="16",
                        cls="input input-sm w-full",
                    ),
                    cls="flex items-center gap-3 mb-2",
                ),
                Div(
                    Span("时间预算(分钟)", cls="text-sm font-medium text-gray-500 w-28 shrink-0"),
                    Input(
                        name="time_budget_minutes",
                        type="number",
                        value="0",
                        min="0",
                        cls="input input-sm w-full",
                    ),
                    cls="flex items-center gap-3 mb-1",
                ),
                P(
                    "时间预算为 0 表示不限；超出预算会自动停止并保留已完成结果。",
                    cls="ml-[7.75rem] text-xs text-gray-500 mb-3",
                ),
                Div(
                    Span("初始资金", cls="text-sm font-medium text-gray-500 w-28 shrink-0"),
                    Input(
                        name="initial_cash",
                        type="number",
                        value="1000000",
                        cls="input input-sm w-full",
                    ),
                    cls="flex items-center gap-3 mb-4",
                ),
                Div(
                    H4(
                        "参数取值（仅策略参数）",
                        cls="text-sm font-semibold text-gray-600 mb-1",
                    ),
                    P(
                        "只填一个值表示固定该参数；填多个值表示参与搜索。",
                        cls="text-xs text-gray-500 mb-2",
                    ),
                    *param_inputs,
                ),
                Div(
                    Button(
                        "开始优化",
                        type="button",
                        cls="btn btn-primary",
                        hx_post=f"/strategy/{name}/optimize/run",
                        hx_target="#optimize-task-wrapper",
                        hx_swap="outerHTML",
                        hx_include="closest form",
                    ),
                    cls="flex justify-end mt-4",
                ),
            ),
            cls="bg-white p-6 rounded-lg shadow-sm border border-gray-100",
        )
    )

    task_panel = _render_task_panel(name, task_id, sort=sort_key, desc=sort_desc)
    return form, task_panel


def _optimization_progress(
    done: int, running: bool, status: str | None, task: dict[str, Any], total: int
) -> Any:
    """Optimization progress."""
    if running:
        percent = int(done * 100 / total) if total else 0
        progress = Div(
            Div(
                Div(
                    cls="bg-[#e41815] h-2 rounded transition-all",
                    style=f"width:{percent}%",
                ),
                cls="bg-gray-200 h-2 rounded w-full overflow-hidden",
            ),
            P(
                f"进行中 {done}/{total}（{percent}%）",
                cls="text-xs text-gray-600 mt-2",
            ),
            cls="mb-3",
        )
    else:
        progress = P(
            {
                STATUS_DONE: f"已完成，共 {len(task.get('results') or [])} 个组合。",
                STATUS_CANCELLED: "任务已中断。",
                STATUS_FAILED: f"任务失败：{task.get('error') or '未知错误'}",
            }.get(status or "", f"状态：{status}"),
            cls="text-sm text-gray-600 mb-3",
        )
    return progress


def _encode_prefill(payload: dict[str, Any]) -> str:
    """把回测预填参数编码为 URL 安全字符串。"""
    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _build_spec(
    name: str,
    form: Mapping[str, object],
) -> OptimizationSpec:
    """由表单构造优化配置。"""
    from quantide.service.discovery import strategy_loader

    from .strategy import _get_strategy_default_params, _split_backtest_params

    strategies = strategy_loader.load_from_cache()
    cls = strategies.get(name)
    default_params = _get_strategy_default_params(cls) if cls else {}
    strategy_params, _ = _split_backtest_params(default_params)

    base_config, param_grid = optimization_parameters(strategy_params, default_params, form)
    return OptimizationSpec(
        strategy_name=name,
        base_config=base_config,
        param_grid=param_grid,
        start_date=arrow.get(str(form.get("start_date"))).date(),
        end_date=arrow.get(str(form.get("end_date"))).date(),
        objective=form_choice(form, "objective", OBJECTIVES, "sharpe"),
        mode=form_choice(form, "mode", MODES, "grid"),
        in_sample_ratio=form_number(form, "in_sample_ratio", 0.7, float),
        n_random=form_number(form, "n_random", 20, int),
        max_workers=max(1, form_number(form, "max_workers", 4, int)),
        initial_cash=form_number(form, "initial_cash", 1_000_000.0, float),
        time_budget_minutes=form_number(form, "time_budget_minutes", 0.0, float),
    )


def _format_pct(value: object) -> str:
    """格式化百分比。"""
    try:
        return f"{float(cast(float | int | str, value)):.2%}"
    except (TypeError, ValueError):
        return "-"


def _format_num(value: object) -> str:
    """格式化数值。"""
    try:
        return f"{float(cast(float | int | str, value)):.2f}"
    except (TypeError, ValueError):
        return "-"


def _objective_cell(value: object, is_risk: bool) -> str:
    """目标值展示（回撤类按百分比，其余按数值）。"""
    if is_risk:
        return _format_pct(value)
    return _format_num(value)


def _metric(metrics: dict[str, Any], key: str) -> str:
    """读取指标文本。"""
    return str(metrics.get(key, "-"))


def _monthly_columns(results: list[dict[str, Any]]) -> list[str]:
    """收集所有组合覆盖的月份列。"""
    months: set[str] = set()
    for row in results:
        for item in row.get("monthly") or []:
            month = str(item.get("month") or "")
            if month:
                months.add(month)
    return sorted(months)


def _render_monthly_matrix(task: dict[str, Any]) -> Any:
    """渲染月度分解表：行=参数组合，列=月份，格子=当月收益。

    每列最优的格子加粗高亮，用于直观判断"参数优劣是否随月份变化"。
    """
    results = task.get("results") or []
    months = _monthly_columns(results)
    if not months:
        return Div()

    best_by_month: dict[str, float] = {}
    best_by_month = _best_monthly_returns(results)

    header = [Th("参数", cls="text-xs")]
    for month in months:
        header.append(Th(month, cls="text-xs whitespace-nowrap"))
    header.extend(
        [
            Th("正收益月", cls="text-xs whitespace-nowrap"),
            Th("最差月", cls="text-xs whitespace-nowrap"),
            Th("月度中位", cls="text-xs whitespace-nowrap"),
        ]
    )

    body: list[Any] = []
    body = [_monthly_result_row(row, months, best_by_month, len(results)) for row in results]

    return Div(
        H4("月度分解", cls="text-sm font-semibold text-gray-600 mb-1"),
        P(
            "每格为该参数组当月收益（绿正红负）；加粗为当月最优。"
            "带 * 的月份未覆盖完整交易月。本表仅作诊断，不含参数选择。",
            cls="text-xs text-gray-500 mb-2",
        ),
        Table(
            Thead(Tr(*header)),
            Tbody(*body),
            cls="table table-zebra text-xs",
        ),
        cls="bg-white p-4 rounded-lg border border-gray-100 overflow-x-auto mt-4",
    )


#: 可排序的列：键 -> (表头, 取值函数)
SORT_COLUMNS: dict[str, str] = {
    "in_objective": "样本内目标",
    "out_objective": "样本外",
    "in_cagr": "样本内年化",
    "out_cagr": "样本外年化",
    "in_mdd": "样本内回撤",
}
DEFAULT_SORT = "in_objective"


def _row_sort_value(row: dict[str, Any], key: str) -> float:
    """取用于排序的数值（与表头显示的数值一致）。

    回撤按显示值排序：降序时回撤更浅（-10% > -30%）的组合排在前面。
    """
    in_sample = row.get("in_sample") or {}
    out_sample = row.get("out_sample") or {}
    if key == "in_objective":
        value = row.get("objective")
    elif key == "out_objective":
        value = row.get("out_objective")
    elif key == "in_cagr":
        value = parse_metric(in_sample.get("CAGR"))
    elif key == "out_cagr":
        value = parse_metric(out_sample.get("CAGR"))
    elif key == "in_mdd":
        value = parse_metric(in_sample.get("Max Drawdown"))
    else:
        value = None
    if value is None:
        return float("inf")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float("inf")
    if number != number:  # NaN
        return float("inf")
    return number


def _sort_results(results: list[dict[str, Any]], key: str, desc: bool) -> list[dict[str, Any]]:
    """按指定列排序结果。"""
    if key not in SORT_COLUMNS:
        key = DEFAULT_SORT
    ordered = sorted(
        results,
        key=lambda row: _row_sort_value(row, key),
        reverse=desc,
    )
    return ordered


def _sort_header(
    name: str,
    task_id: str,
    key: str,
    label: str,
    current: str,
    desc: bool,
) -> Any:
    """渲染可点击排序的表头。"""
    next_desc = not desc if current == key else False
    arrow = ""
    if current == key:
        arrow = " ↓" if desc else " ↑"
    href = (
        f"/strategy/{name}/optimize/status/{task_id}"
        f"?sort={key}&dir={'desc' if next_desc else 'asc'}"
    )
    return Th(
        A(
            f"{label}{arrow}",
            href=href,
            hx_get=href,
            hx_target="#optimize-task-wrapper",
            hx_swap="outerHTML",
            cls="text-xs cursor-pointer select-none hover:text-[#e41815]",
        ),
        cls="text-xs whitespace-nowrap",
    )


def _render_results(
    name: str,
    task: dict[str, Any],
    sort: str = DEFAULT_SORT,
    desc: bool = True,
    task_id: str = "",
) -> Any:
    """渲染结果对比表（支持按列排序）。"""
    results = task.get("results") or []
    objective = task.get("objective", "sharpe")
    param_keys = sorted({key for row in results for key in (row.get("params") or {}).keys()})
    is_risk = objective == "max_drawdown"
    direction = "（越小越好）" if is_risk else "（越大越好）"
    if sort not in SORT_COLUMNS:
        sort = DEFAULT_SORT
    ordered = _sort_results(results, sort, desc)

    header_cells = [Th("#", cls="text-xs"), Th("参数", cls="text-xs")]
    header_cells.append(
        _sort_header(
            name,
            task_id,
            "in_objective",
            f"样本内{objective_label(objective)}{direction}",
            sort,
            desc,
        )
    )
    header_cells.append(_sort_header(name, task_id, "out_objective", "样本外", sort, desc))
    header_cells.append(_sort_header(name, task_id, "in_cagr", "样本内年化", sort, desc))
    header_cells.append(_sort_header(name, task_id, "out_cagr", "样本外年化", sort, desc))
    header_cells.append(_sort_header(name, task_id, "in_mdd", "样本内回撤", sort, desc))
    header_cells.append(Th("告警", cls="text-xs"))
    header_cells.append(Th("操作", cls="text-xs"))

    rows: list[Any] = []
    _append_optimization_result_rows(ordered, param_keys, task, rows, is_risk, name)

    if not rows:
        return Div(
            P("暂无结果。", cls="text-sm text-gray-500"),
            cls="bg-white p-4 rounded-lg border border-gray-100",
        )

    return Div(
        Table(
            Thead(Tr(*header_cells)),
            Tbody(*rows),
            cls="table table-zebra text-xs",
        ),
        P(
            "点击表头可排序（再次点击切换升序/降序）；样本内用于挑选参数，"
            "样本外仅用于检验；收益类目标在样本外转负、回撤类目标在样本外变深时"
            "提示疑似过拟合。",
            cls="text-xs text-gray-500 mt-2",
        ),
        cls="bg-white p-4 rounded-lg border border-gray-100 overflow-x-auto",
    )


def _render_task_panel(
    name: str,
    task_id: str,
    sort: str = DEFAULT_SORT,
    desc: bool = True,
) -> Any:
    """渲染任务进度与结果面板（始终返回 #optimize-task-wrapper 容器）。

    容器必须始终存在：否则首次进入页面时「开始优化」按钮的 HTMX 目标缺失，
    点击不会有任何反应。
    """
    task = get_task(task_id) if task_id else None
    if task is None:
        return Div(
            P(
                "任务不存在。" if task_id else "尚未运行任务。",
                cls="text-sm text-gray-500",
            ),
            cls="bg-white p-4 rounded-lg border border-gray-100",
            id="optimize-task-wrapper",
        )

    status = task.get("status")
    total = int(task.get("total") or 0)
    done = int(task.get("done") or 0)
    running = status in {STATUS_PENDING, STATUS_RUNNING}

    progress = _optimization_progress(done, running, status, task, total)

    cancel_button = (
        Button(
            "中断任务",
            type="button",
            cls="btn btn-ghost btn-sm",
            hx_post=f"/strategy/{name}/optimize/cancel/{task_id}",
            hx_target="#optimize-task-wrapper",
            hx_swap="outerHTML",
        )
        if running
        else Div()
    )

    panel = Div(
        Div(
            H3("任务状态", cls="text-base font-semibold"),
            cancel_button,
            cls="flex items-center justify-between mb-2",
        ),
        progress,
        _render_results(name, task, sort=sort, desc=desc, task_id=task_id),
        _render_monthly_matrix(task),
        id="optimize-task-panel",
    )
    if running:
        panel = Div(
            panel,
            hx_get=(
                f"/strategy/{name}/optimize/status/{task_id}"
                f"?sort={sort}&dir={'desc' if desc else 'asc'}"
            ),
            hx_trigger=f"every {OPTIMIZE_POLL_SECONDS}s",
            hx_swap="outerHTML",
            id="optimize-task-wrapper",
        )
    else:
        panel = Div(panel, id="optimize-task-wrapper")
    return panel


def _render_history(name: str) -> Any:
    """渲染历史任务列表。"""
    tasks = list_tasks(name, limit=10)
    if not tasks:
        return Div(
            P("暂无历史任务。", cls="text-sm text-gray-500"),
            cls="bg-white p-4 rounded-lg border border-gray-100",
        )
    rows = []
    for task in tasks:
        spec = task.get("spec") or {}
        rows.append(
            Tr(
                Td(task.get("started_at", "")[:19], cls="text-xs"),
                Td(task.get("status", ""), cls="text-xs"),
                Td(
                    objective_label(task.get("objective", "")),
                    cls="text-xs",
                ),
                Td(
                    f"{task.get('done', 0)}/{task.get('total', 0)}",
                    cls="text-xs",
                ),
                Td(
                    f"{spec.get('start_date', '')} ~ {spec.get('end_date', '')}",
                    cls="text-xs",
                ),
                Td(
                    A(
                        "查看",
                        href=(f"/strategy/{name}/optimize?task_id={task.get('task_id')}"),
                        cls="text-xs text-[#e41815] hover:underline",
                    ),
                    cls="text-xs",
                ),
            )
        )
    return Div(
        Table(
            Thead(
                Tr(
                    Th("开始时间", cls="text-xs"),
                    Th("状态", cls="text-xs"),
                    Th("目标", cls="text-xs"),
                    Th("进度", cls="text-xs"),
                    Th("区间", cls="text-xs"),
                    Th("", cls="text-xs"),
                )
            ),
            Tbody(*rows),
            cls="table table-zebra text-xs",
        ),
        cls="bg-white p-4 rounded-lg border border-gray-100 overflow-x-auto",
    )


@rt("/{name}/optimize")
def optimize_page(req: Request, session: SessionData, name: str) -> Any:
    """参数优化页面。"""
    from quantide.service.discovery import strategy_loader

    from .strategy import _get_strategy_default_params, _split_backtest_params

    layout = MainLayout(title=f"参数优化 - {name}", user=session.get("auth"))
    layout.header_active = "策略"

    strategies = strategy_loader.load_from_cache()
    cls = strategies.get(name)
    if cls is None:
        return RedirectResponse("/strategy")

    default_params = _get_strategy_default_params(cls)
    strategy_params, _ = _split_backtest_params(default_params)

    form, task_panel = _optimization_form_and_task(strategy_params, req, name)

    layout.set_main_block(
        lambda: Div(
            Div(
                Div(
                    A(
                        "← 返回策略",
                        href=f"/strategy/{name}",
                        cls="text-gray-500 hover:text-gray-800 mb-4 inline-block",
                    ),
                    H1(f"参数优化 · {name}", cls="text-2xl font-bold mb-1"),
                    P(
                        "搜索策略参数，按样本内指标挑选，并用样本外区间检验是否过拟合。",
                        cls="text-sm text-gray-600 mb-5",
                    ),
                ),
                form,
                Div(
                    H3("本次任务", cls="text-base font-semibold mb-2"),
                    task_panel,
                    cls="mt-6",
                ),
                Div(
                    H3("历史任务", cls="text-base font-semibold mb-2"),
                    _render_history(name),
                    cls="mt-6",
                ),
                Script(
                    """
                (function(){
                    const form = document.querySelector('form');
                    if (!form) return;
                    const years = form.querySelector('[name=years]');
                    const start = form.querySelector('[name=start_date]');
                    const end = form.querySelector('[name=end_date]');
                    if (!years || !start || !end) return;
                    const apply = () => {
                        const n = parseFloat(years.value);
                        if (!n || n <= 0 || !end.value) return;
                        const endDate = new Date(end.value);
                        if (isNaN(endDate)) return;
                        const startDate = new Date(endDate.getTime());
                        startDate.setFullYear(startDate.getFullYear() - n);
                        start.value = startDate.toISOString().slice(0, 10);
                    };
                    years.addEventListener('change', apply);
                    end.addEventListener('change', apply);
                })();
                """
                ),
                cls="max-w-5xl mx-auto py-8",
            )
        )
    )
    return layout.render(req)


@rt("/{name}/optimize/run", methods=["POST"])
async def run_optimize(req: Request, name: str) -> Any:
    """启动参数优化任务。"""
    form = await req.form()
    try:
        spec = _build_spec(name, form)
    except Exception as exc:
        logger.warning(f"参数优化配置解析失败: {exc}")
        return Div(
            P(f"配置无效：{exc}", cls="text-sm text-red-600"),
            cls="bg-white p-4 rounded-lg border border-red-200",
        )
    if not spec.param_grid and spec.mode == "grid":
        return Div(
            P(
                "请至少为一个策略参数填写多个取值（用逗号分隔）。",
                cls="text-sm text-red-600",
            ),
            cls="bg-white p-4 rounded-lg border border-red-200",
        )
    task_id = start_optimization(spec)
    return _render_task_panel(name, task_id)


@rt("/{name}/optimize/status/{task_id}")
def optimize_status(name: str, task_id: str, sort: str = "", dir: str = "desc") -> Any:
    """查询任务状态（前端轮询 / 排序切换）。"""
    return _render_task_panel(
        name,
        task_id,
        sort=sort or DEFAULT_SORT,
        desc=(dir or "desc") != "asc",
    )


@rt("/{name}/optimize/cancel/{task_id}", methods=["POST"])
def optimize_cancel(name: str, task_id: str, sort: str = "", dir: str = "desc") -> Any:
    """中断运行中的优化任务。"""
    cancel_optimization(task_id)
    return _render_task_panel(
        name,
        task_id,
        sort=sort or DEFAULT_SORT,
        desc=(dir or "desc") != "asc",
    )


def _best_monthly_returns(results: list[dict[str, Any]]) -> dict[str, float]:
    best_by_month: dict[str, float] = {}
    for row in results:
        for item in row.get("monthly") or []:
            month = str(item.get("month") or "")
            ret = float(item.get("ret") or 0.0)
            if month not in best_by_month or ret > best_by_month[month]:
                best_by_month[month] = ret
    return best_by_month


def _monthly_result_row(
    row: dict[str, Any],
    months: Sequence[str],
    best_by_month: Mapping[str, float],
    result_count: int,
) -> Any:
    params = row.get("params") or {}
    param_text = ", ".join(f"{key}={params.get(key)}" for key in sorted(params.keys())) or "-"
    by_month = {str(item.get("month") or ""): item for item in row.get("monthly") or []}
    rets = [float(item.get("ret") or 0.0) for item in row.get("monthly") or []]
    cells: list[Any] = [Td(param_text, cls="text-xs font-mono")]
    cells.extend(
        _monthly_return_cell(month, by_month, best_by_month, result_count) for month in months
    )
    positive = sum(1 for ret in rets if ret > 0)
    worst = min(rets) if rets else 0.0
    worst_label = ""
    if rets:
        worst_month = min(
            row.get("monthly") or [],
            key=lambda item: float(item.get("ret") or 0.0),
        )
        worst_label = f" {worst_month.get('month')}"
    median = sorted(rets)[len(rets) // 2] if rets else 0.0
    cells.extend(
        [
            Td(f"{positive}/{len(rets)}", cls="text-xs"),
            Td(f"{worst * 100:+.1f}%{worst_label}", cls="text-xs"),
            Td(f"{median * 100:+.2f}%", cls="text-xs"),
        ]
    )
    return Tr(*cells)


def _monthly_return_cell(
    month: str,
    by_month: Mapping[str, dict[str, Any]],
    best_by_month: Mapping[str, float],
    result_count: int,
) -> Any:
    item = by_month.get(month)
    if item is None:
        return Td("-", cls="text-xs text-gray-300")
    ret = float(item.get("ret") or 0.0)
    is_best = abs(ret - best_by_month.get(month, ret)) < 1e-12 and result_count > 1
    tone = "text-red-600 bg-red-50" if ret >= 0 else "text-green-600 bg-green-50"
    weight = "font-bold" if is_best else ""
    mark = "*" if item.get("partial") else ""
    return Td(
        f"{ret * 100:+.1f}%{mark}",
        cls=f"text-xs {tone} {weight}".strip(),
    )
