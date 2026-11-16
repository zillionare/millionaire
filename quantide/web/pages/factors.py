"""Factor research overview and tracking detail pages."""

from __future__ import annotations

import datetime
import json
from typing import Any

from fasthtml.common import (
    H1,
    H2,
    A,
    Details,
    Div,
    Form,
    Option,
    P,
    Script,
    Span,
    Summary,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
)
from fasthtml.common import (
    Button as ActionButton,
)
from fasthtml.common import (
    Input as TextInput,
)
from fasthtml.common import (
    Select as PlainSelect,
)
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse

from quantide.factors.alpha import FEATURE_GROUPS
from quantide.factors.metadata import (
    FACTOR_METADATA,
    FactorDefinition,
    factor_definition,
    list_factor_definitions,
)
from quantide.factors.research import summarize_ic
from quantide.service.factor_study import CustomStudy
from quantide.service.factor_study_worker import (
    cancel_study,
    load_study,
    study_run,
    submit_study,
)
from quantide.service.factor_tracking import (
    HOLDING_CHOICES,
    TrackingProfile,
    TrackingView,
    reset_profile,
    save_profile,
    tracking_view,
    trigger_refresh,
    trigger_refresh_all,
)
from quantide.service.factor_tracking_summary import tracking_summaries
from quantide.web.application import fast_app
from quantide.web.layouts.main import MainLayout
from quantide.web.pages.factors_custom import custom_form as _custom_form
from quantide.web.pages.factors_custom import custom_result as _custom_result
from quantide.web.pages.factors_overview import (
    _sort_entries,
)
from quantide.web.pages.factors_overview import (
    metric_guide as _metric_guide,
)
from quantide.web.pages.factors_overview import (
    overview_row as _overview_row,
)
from quantide.web.pages.factors_overview import (
    overview_summary as _overview_summary,
)
from quantide.web.pages.factors_overview import (
    overview_table as _overview_table,
)
from quantide.web.pages.factors_overview import (
    overview_toolbar as _overview_toolbar,
)
from quantide.web.pages.factors_overview import (
    tracking_onboarding as _tracking_onboarding,
)
from quantide.web.pages.factors_tasks import study_task_block as _study_task_block
from quantide.web.pages.factors_ui import (
    LOOKBACK_LABELS as _LOOKBACK_LABELS,
)
from quantide.web.pages.factors_ui import (
    PRICE_LABELS as _PRICE_LABELS,
)
from quantide.web.pages.factors_ui import (
    fmt_number as _fmt_number,
)
from quantide.web.pages.factors_ui import (
    fmt_percent as _fmt_percent,
)
from quantide.web.pages.factors_ui import (
    fmt_time as _fmt_time,
)
from quantide.web.pages.factors_ui import (
    status_badge as _status_badge,
)
from quantide.web.theme import ECHARTS_SRC, AppTheme

factor_app, rt = fast_app(hdrs=AppTheme.headers())


def _factor_menu(active_url: str = "") -> list[dict[str, Any]]:
    menu: list[dict[str, Any]] = [
        {"title": "因子总览", "url": "/factors/", "active": active_url == "/factors/"}
    ]
    for group, ids in FEATURE_GROUPS.items():
        children = [
            {
                "title": FACTOR_METADATA[factor_id].display_name,
                "search": f"{FACTOR_METADATA[factor_id].display_name} {factor_id}",
                "url": f"/factors/{factor_id}",
                "active": active_url == f"/factors/{factor_id}",
            }
            for factor_id in ids
        ]
        menu.append({"title": group, "children": children})
    return menu


def _layout(title: str, active_url: str) -> MainLayout:
    layout = MainLayout(title=title)
    layout.content_max_width = "max-w-[1600px]"
    layout.header_active = "因子"
    layout.sidebar_menu = _factor_menu(active_url)
    layout.sidebar_search = "筛选左侧因子目录"
    layout.set_sidebar_active(active_url)
    return layout


def _profile_text(profile: TrackingProfile) -> str:
    return (
        f"{_LOOKBACK_LABELS.get(profile.lookback, profile.lookback)} · "
        f"{profile.primary_holding_days} 日 · "
        f"{_PRICE_LABELS.get(profile.price_field, profile.price_field)}"
    )


def _metric_cards(snapshot: dict[str, Any]) -> Div:
    primary = snapshot.get("primary_metrics") or {}
    rank_ic = primary.get("rank_ic") or {}
    diagnostics = primary.get("diagnostics") or {}
    deciles = primary.get("deciles") or {}
    cards = [
        ("RankIC", _fmt_number(rank_ic.get("mean"))),
        ("普通 t 值", _fmt_number(rank_ic.get("t_naive"), 2)),
        ("有效交易日", str(rank_ic.get("n_days") or 0)),
        ("有效样本", str(diagnostics.get("n_valid_pairs") or 0)),
        ("D1-D10", _fmt_percent(deciles.get("d1_minus_d10"))),
        ("评价截至", str(diagnostics.get("as_of_date") or "—")),
    ]
    return Div(
        *[
            Div(
                P(label, cls="text-xs text-gray-500"),
                P(value, cls="mt-1 text-lg font-semibold tabular-nums text-gray-900"),
                cls="bg-white px-4 py-3",
            )
            for label, value in cards
        ],
        cls=(
            "mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-xl border "
            "border-gray-100 bg-gray-100 md:grid-cols-3 xl:grid-cols-6"
        ),
    )


def _status_strip(meta: FactorDefinition, view: TrackingView) -> Div:
    current = view.current or {}
    primary = current.get("primary_metrics") or {}
    rank_ic = primary.get("rank_ic") or {}
    right = (
        f"RankIC {_fmt_number(rank_ic.get('mean'))} · t {_fmt_number(rank_ic.get('t_naive'), 2)}"
        if current
        else "尚无跟踪结果"
    )
    return Div(
        Div(
            Div(
                H1(meta.display_name, cls="text-2xl font-bold text-gray-900"),
                Span(meta.factor_id, cls="ml-2 font-mono text-xs text-gray-500"),
                cls="flex flex-wrap items-baseline",
            ),
            P(meta.group, cls="mt-1 text-sm text-gray-500"),
            cls="min-w-0",
        ),
        Div(
            Span(_profile_text(view.profile), cls="text-sm text-gray-600"),
            _status_badge(view.status),
            P(right, cls="mt-1 text-sm font-medium text-gray-900"),
            P(
                f"数据截至 {current.get('data_cutoff') or '—'} · "
                f"更新 {_fmt_time(current.get('computed_at'))}",
                cls="mt-1 text-xs text-gray-400",
            ),
            (
                P(
                    f"最近失败：{view.last_attempt.get('error') or '未知错误'}",
                    cls="mt-1 max-w-md truncate text-xs text-red-600",
                )
                if isinstance(view.last_attempt, dict)
                and view.last_attempt.get("status") == "failed"
                else None
            ),
            cls="flex flex-col items-start gap-1 md:items-end",
        ),
        cls=(
            "flex flex-col justify-between gap-4 rounded-xl border border-gray-100 "
            "bg-white p-4 shadow-sm md:flex-row"
        ),
    )


def _tab_link(factor_id: str, tab: str, label: str, active: bool) -> A:
    tone = (
        "border-[#e41815] text-[#e41815]"
        if active
        else "border-transparent text-gray-500 hover:text-gray-900"
    )
    extra = {"aria_current": "page"} if active else {}
    return A(
        label,
        href=f"/factors/{factor_id}?tab={tab}",
        cls=f"border-b-2 px-3 py-2 text-sm {tone}",
        **extra,
    )


def _coverage_section(meta: FactorDefinition, view: TrackingView) -> Div:
    current = view.current or {}
    primary = current.get("primary_metrics") or {}
    diagnostics = primary.get("diagnostics") or {}
    coverage = current.get("coverage") or {}
    if current:
        detail = (
            f"有效覆盖截至 {diagnostics.get('coverage_end') or '—'}，"
            f"样本 {diagnostics.get('n_rows') or 0} 行；"
            f"最新截面 {coverage.get('latest_symbols') or 0} 个标的"
        )
        if coverage.get("sufficient"):
            detail += "（达到最小截面）"
        else:
            detail += "（低于最小截面，统计可能不足）"
    else:
        detail = "尚未建立跟踪，暂无当前覆盖数据。"
    return Div(
        P("当前覆盖", cls="text-sm font-semibold text-gray-900"),
        P(detail, cls="mt-1 text-sm text-gray-600"),
        cls="rounded-lg border border-gray-100 bg-gray-50 p-3",
    )


def _card_tab(meta: FactorDefinition, view: TrackingView) -> Div:
    sections = [
        ("原理", meta.principle),
        ("计算方式", meta.formula),
        ("参数", "；".join(meta.parameters)),
        ("示例", meta.example),
        ("数据要求", meta.data_requirements),
        ("注意事项", meta.caveats),
    ]
    return Div(
        Div(
            *[
                Div(
                    P(title, cls="text-xs font-medium uppercase tracking-wide text-gray-400"),
                    P(value, cls="mt-1 whitespace-pre-line text-sm leading-6 text-gray-700"),
                    cls="border-b border-gray-100 py-3",
                )
                for title, value in sections
            ],
            cls="rounded-xl border border-gray-100 bg-white p-4 shadow-sm",
        ),
        _coverage_section(meta, view),
        cls="mt-4 space-y-4",
    )


def _rolling(values: list[float], window: int = 20) -> list[float | None]:
    result: list[float | None] = []
    for index in range(len(values)):
        if index + 1 < window:
            result.append(None)
        else:
            chunk = values[index + 1 - window : index + 1]
            result.append(sum(chunk) / len(chunk))
    return result


def _yearly_rows(daily_ic: list[dict[str, Any]]) -> list[Any]:
    by_year: dict[str, list[float]] = {}
    for point in daily_ic:
        day = str(point.get("date") or "")
        if len(day) >= 4:
            by_year.setdefault(day[:4], []).append(float(point["ic"]))
    rows = []
    for year, values in sorted(by_year.items()):
        summary = summarize_ic(values)
        rows.append(
            Tr(
                Td(year),
                Td(_fmt_number(summary.mean)),
                Td(_fmt_number(summary.t_naive, 2)),
                Td(str(summary.n_days)),
            )
        )
    return rows


def _scaled(value: Any) -> float | None:
    return None if value is None else float(value) * 100


def _chart_script(factor_id: str, snapshot: dict[str, Any]) -> str:
    primary = snapshot.get("primary_metrics") or {}
    daily = primary.get("daily_ic") or []
    dates = [str(point.get("date")) for point in daily]
    ics = [float(point["ic"]) * 100 for point in daily]
    rolling = _rolling(ics)
    deciles = (primary.get("deciles") or {}).get("buckets") or []
    horizons = snapshot.get("horizon_metrics") or {}
    cohort = (snapshot.get("common_cohort") or {}).get("per_horizon") or {}
    horizon_labels = [f"{key}日" for key in horizons]
    horizon_values = [_scaled((cohort.get(str(key)) or {}).get("mean")) for key in horizons]
    safe_id = json.dumps(factor_id)
    payload = {
        "dates": dates,
        "ics": ics,
        "rolling": rolling,
        "deciles": [f"D{bucket.get('bucket')}" for bucket in deciles],
        "decile_values": [_scaled(bucket.get("mean_forward")) for bucket in deciles],
        "horizon_labels": horizon_labels,
        "horizon_values": horizon_values,
    }
    encoded = json.dumps(payload, ensure_ascii=False)
    return f"""
(function() {{
  var data = {encoded};
  var id = {safe_id};
  var icEl = document.getElementById('factor-ic-' + id);
  var decileEl = document.getElementById('factor-decile-' + id);
  var horizonEl = document.getElementById('factor-horizon-' + id);
  if (typeof echarts === 'undefined') return;
  if (icEl && data.dates.length) {{
    var chart = echarts.init(icEl);
    chart.setOption({{grid:{{left:45,right:20,top:20,bottom:35}},tooltip:{{trigger:'axis'}},
      xAxis:{{type:'category',data:data.dates}}, yAxis:{{type:'value'}},
      series:[{{name:'RankIC',type:'line',showSymbol:false,data:data.ics}},
              {{name:'20日滚动',type:'line',showSymbol:false,data:data.rolling}}]}});
    window.addEventListener('resize', function(){{chart.resize();}});
  }}
  if (decileEl && data.deciles.length) {{
    var chart2 = echarts.init(decileEl);
    chart2.setOption({{grid:{{left:45,right:20,top:20,bottom:35}},tooltip:{{trigger:'axis'}},
      xAxis:{{type:'category',data:data.deciles}}, yAxis:{{type:'value'}},
      series:[{{name:'平均前瞻收益(%)',type:'bar',data:data.decile_values}}]}});
    window.addEventListener('resize', function(){{chart2.resize();}});
  }}
  if (horizonEl && data.horizon_labels.length) {{
    var chart3 = echarts.init(horizonEl);
    chart3.setOption({{grid:{{left:45,right:20,top:20,bottom:35}},tooltip:{{trigger:'axis'}},
      xAxis:{{type:'category',data:data.horizon_labels}}, yAxis:{{type:'value'}},
      series:[{{name:'RankIC(%)',type:'line',data:data.horizon_values}}]}});
    window.addEventListener('resize', function(){{chart3.resize();}});
  }}
}})();
"""


def _empty_report(
    meta: FactorDefinition,
    view: TrackingView,
    error_block: Any,
    task_block: Any,
    custom_block: Any,
) -> Div:
    return Div(
        error_block,
        task_block,
        custom_block,
        Div(
            P("尚未建立跟踪。", cls="text-sm font-medium text-gray-700"),
            P(
                "系统将在每日数据维护后生成快照，也可以立即建立一次。",
                cls="mt-1 text-sm text-gray-500",
            ),
            Form(
                ActionButton("立即建立跟踪", type="submit", cls="q-btn q-btn--sm mt-3"),
                method="post",
                action=f"/factors/{meta.factor_id}/refresh",
            ),
            cls="mt-4 rounded-xl border border-dashed border-gray-200 bg-white p-8 text-center",
        ),
        _custom_form(meta, view.profile),
    )


def _horizon_rows(current: dict[str, Any]) -> list[Any]:
    rows = []
    for holding, result in sorted(
        (current.get("horizon_metrics") or {}).items(), key=lambda item: int(item[0])
    ):
        rank_ic = result.get("rank_ic") or {}
        diagnostics = result.get("diagnostics") or {}
        deciles = result.get("deciles") or {}
        rows.append(
            Tr(
                Td(f"{holding} 日"),
                Td(_fmt_number(rank_ic.get("mean"))),
                Td(_fmt_number(rank_ic.get("t_naive"), 2)),
                Td(str(rank_ic.get("n_days") or 0)),
                Td(str(diagnostics.get("n_valid_pairs") or 0)),
                Td(_fmt_percent(deciles.get("d1_minus_d10"))),
                Td(str(diagnostics.get("as_of_date") or "—")),
            )
        )
    return rows


def _horizon_chart(meta: FactorDefinition, cohort: dict[str, Any]) -> Any:
    if cohort.get("status") != "ok":
        return P(
            "共同有效日期不足，无法可靠比较持有期衰减。",
            cls="rounded-lg bg-amber-50 p-3 text-sm text-amber-700",
        )
    return Div(
        P("持有期 RankIC 衰减", cls="mb-2 text-sm font-medium text-gray-700"),
        P(
            f"共同有效信号日 {cohort.get('n_days') or 0} 个；只比较各持有期共同成熟的日期。",
            cls="mb-2 text-xs text-gray-500",
        ),
        Div(id=f"factor-horizon-{meta.factor_id}", cls="h-64 w-full"),
        cls="rounded-xl border border-gray-100 bg-white p-4 shadow-sm",
    )


def _report_charts(meta: FactorDefinition, cohort: dict[str, Any]) -> Div:
    return Div(
        Div(
            P("RankIC 时序", cls="mb-2 text-sm font-medium text-gray-700"),
            Div(id=f"factor-ic-{meta.factor_id}", cls="h-64 w-full"),
            cls="rounded-xl border border-gray-100 bg-white p-4 shadow-sm",
        ),
        Div(
            P("十分位平均前瞻收益", cls="mb-2 text-sm font-medium text-gray-700"),
            Div(id=f"factor-decile-{meta.factor_id}", cls="h-64 w-full"),
            cls="rounded-xl border border-gray-100 bg-white p-4 shadow-sm",
        ),
        _horizon_chart(meta, cohort),
        cls="mt-4 space-y-4",
    )


def _report_details(rows: list[Any], daily: list[dict[str, Any]]) -> Details:
    return Details(
        Summary("明细与年度稳定性", cls="cursor-pointer text-sm font-medium text-gray-700"),
        Table(
            Thead(
                Tr(
                    *[
                        Th(label, cls="px-3 py-2 text-left text-xs text-gray-500")
                        for label in (
                            "持有期",
                            "RankIC",
                            "t",
                            "有效日",
                            "样本",
                            "D1-D10",
                            "评价截至",
                        )
                    ]
                )
            ),
            Tbody(*rows),
            cls="mt-3 w-full text-sm",
        ),
        P("年度 RankIC", cls="mt-4 text-xs font-medium text-gray-500"),
        Table(
            Thead(Tr(Th("年份"), Th("RankIC"), Th("t"), Th("有效日"))),
            Tbody(*_yearly_rows(daily)),
            cls="mt-2 w-full text-sm",
        ),
        cls="mt-4 rounded-xl border border-gray-100 bg-white p-4 shadow-sm",
    )


def _reading_guide() -> Details:
    return Details(
        Summary("指标怎么读", cls="cursor-pointer text-sm font-medium text-gray-700"),
        P(
            "RankIC 是同日因子排名与未来收益排名的相关性；t 为普通 t 值，"
            "未调整序列相关和多次选择。D1 是最低组、D10 是最高组；"
            "持有期结果只使用已成熟的前瞻收益。IC 不等于策略净收益。",
            cls="mt-2 text-sm leading-6 text-gray-600",
        ),
        cls="mt-4 rounded-xl border border-gray-100 bg-white p-4 shadow-sm",
    )


def _report_tab(
    meta: FactorDefinition,
    view: TrackingView,
    *,
    custom: CustomStudy | None = None,
    task: Any = None,
    error: str | None = None,
) -> Div:
    current = view.current
    custom_block = _custom_result(meta, custom) if custom else None
    task_block = _study_task_block(meta, task)
    error_block = (
        P(f"自定义检验失败：{error}", cls="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700")
        if error
        else None
    )
    if not current:
        return _empty_report(meta, view, error_block, task_block, custom_block)
    primary = current.get("primary_metrics") or {}
    rows = _horizon_rows(current)
    return Div(
        error_block,
        task_block,
        custom_block,
        _metric_cards(current),
        Div(
            H2("检验报告", cls="text-lg font-semibold text-gray-900"),
            P(
                "以下指标描述因子与未来收益的统计关系，不代表策略净收益。",
                cls="mt-1 text-xs text-gray-500",
            ),
            _tracking_settings(meta, view.profile),
            _custom_form(meta, view.profile),
            _report_charts(meta, current.get("common_cohort") or {}),
            cls="mt-4 space-y-4",
        ),
        _report_details(rows, primary.get("daily_ic") or []),
        _reading_guide(),
        Script(src=ECHARTS_SRC),
        Script(_chart_script(meta.factor_id, current)),
    )


def _tracking_settings(meta: FactorDefinition, profile: TrackingProfile) -> Details:
    holding_options = [
        Div(
            TextInput(
                type="checkbox",
                name="comparison_holding_days",
                value=str(value),
                checked=value in profile.comparison_holding_days,
                cls="checkbox checkbox-sm",
            ),
            Span(f"{value} 日", cls="ml-1 text-xs text-gray-600"),
            cls="flex items-center",
        )
        for value in HOLDING_CHOICES
    ]
    return Details(
        Summary("跟踪设置", cls="cursor-pointer text-sm font-medium text-gray-700"),
        Form(
            Div(
                Div(
                    P("回看窗口", cls="text-xs text-gray-500"),
                    PlainSelect(
                        *[
                            Option(
                                label,
                                value=value,
                                selected=profile.lookback == value,
                            )
                            for value, label in _LOOKBACK_LABELS.items()
                        ],
                        name="lookback",
                        cls="q-input",
                    ),
                ),
                Div(
                    P("主持有期", cls="text-xs text-gray-500"),
                    PlainSelect(
                        *[
                            Option(
                                f"{value} 日",
                                value=str(value),
                                selected=profile.primary_holding_days == value,
                            )
                            for value in HOLDING_CHOICES
                        ],
                        name="primary_holding_days",
                        cls="q-input",
                    ),
                ),
                Div(
                    P("买入价", cls="text-xs text-gray-500"),
                    PlainSelect(
                        *[
                            Option(
                                label,
                                value=value,
                                selected=profile.price_field == value,
                            )
                            for value, label in _PRICE_LABELS.items()
                        ],
                        name="price_field",
                        cls="q-input",
                    ),
                ),
                cls="grid gap-3 md:grid-cols-3",
            ),
            Div(
                P("对照持有期", cls="mt-3 text-xs text-gray-500"),
                Div(*holding_options, cls="mt-1 flex flex-wrap gap-3"),
            ),
            Div(
                TextInput(
                    type="checkbox",
                    name="enabled",
                    checked=profile.enabled,
                    cls="checkbox checkbox-sm",
                ),
                Span("启用自动跟踪", cls="ml-1 text-xs text-gray-600"),
                cls="mt-3 flex items-center",
            ),
            Div(
                ActionButton("保存跟踪设置", type="submit", cls="q-btn q-btn--sm"),
                cls="mt-3",
            ),
            method="post",
            action=f"/factors/{meta.factor_id}/profile",
        ),
        Form(
            ActionButton("恢复推荐方案", type="submit", cls="q-btn q-btn--sm mt-2"),
            method="post",
            action=f"/factors/{meta.factor_id}/profile/reset",
        ),
        cls="mt-4 rounded-xl border border-gray-100 bg-white p-4 shadow-sm",
    )


def _form_text(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _require_maintenance(req: Request) -> None:
    if not req.scope.get("user_is_admin"):
        raise HTTPException(status_code=403, detail="需要维护权限")


@rt("/")
def index(req: Request) -> Any:
    group_filter = req.query_params.get("group", "")
    query = req.query_params.get("q", "").strip().lower()
    sort_key = req.query_params.get("sort", "")
    sort_dir = req.query_params.get("dir", "desc")
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "desc"
    all_definitions = list_factor_definitions()
    definitions = all_definitions
    if group_filter:
        definitions = [item for item in definitions if item.group == group_filter]
    if query:
        definitions = [
            item
            for item in definitions
            if query in item.factor_id.lower() or query in item.display_name.lower()
        ]
    summaries = tracking_summaries([item.factor_id for item in definitions])
    entries = _sort_entries(
        [(item, summaries[item.factor_id]) for item in definitions],
        sort_key,
        sort_dir,
    )
    rows = [_overview_row(item, view) for item, view in entries]
    layout = _layout("因子", "/factors/")
    content = Div(
        Div(
            H1("因子总览", cls="text-2xl font-bold text-gray-900"),
            P(
                "在策略使用前，先验证因子与未来收益的统计关系。",
                cls="mt-1 text-sm text-gray-500",
            ),
        ),
        _overview_summary(entries),
        _tracking_onboarding(entries),
        Div(
            _overview_toolbar(
                query=query,
                group_filter=group_filter,
                sort_key=sort_key,
                sort_dir=sort_dir,
                result_count=len(entries),
                total_count=len(all_definitions),
            ),
            cls="rounded-xl border border-gray-100 bg-white p-4 shadow-sm",
        ),
        _overview_table(
            rows,
            query=query,
            group_filter=group_filter,
            sort_key=sort_key,
            sort_dir=sort_dir,
        ),
        _metric_guide(),
        cls="space-y-4",
    )
    layout.set_main_block(content)
    return layout.render(req)


@rt("/refresh-all", methods=["post"])
def refresh_all(req: Request) -> RedirectResponse:
    _require_maintenance(req)
    trigger_refresh_all()
    return RedirectResponse("/factors/", status_code=303)


@rt("/{factor_id}/refresh", methods=["post"])
def refresh_one(req: Request, factor_id: str) -> RedirectResponse:
    _require_maintenance(req)
    if factor_id not in FACTOR_METADATA:
        return RedirectResponse("/factors/", status_code=303)
    trigger_refresh(factor_id)
    return RedirectResponse(f"/factors/{factor_id}?tab=report", status_code=303)


@rt("/{factor_id}/profile/reset", methods=["post"])
def reset_tracking_profile(req: Request, factor_id: str) -> RedirectResponse:
    _require_maintenance(req)
    if factor_id not in FACTOR_METADATA:
        return RedirectResponse("/factors/", status_code=303)
    reset_profile(factor_id)
    trigger_refresh(factor_id)
    return RedirectResponse(f"/factors/{factor_id}?tab=report", status_code=303)


@rt("/{factor_id}/profile/from-study", methods=["post"])
async def profile_from_study(req: Request, factor_id: str) -> Any:
    _require_maintenance(req)
    if factor_id not in FACTOR_METADATA:
        return RedirectResponse("/factors/", status_code=303)
    form = await req.form()
    holdings = [int(value) for value in form.getlist("holding_days") if isinstance(value, str)]
    try:
        primary = int(_form_text(form.get("primary_holding_days"), "5"))
        save_profile(
            factor_id,
            lookback=_form_text(form.get("lookback"), "3y"),
            primary_holding_days=primary,
            comparison_holding_days=holdings,
            price_field=_form_text(form.get("price_field"), "open"),
            source_study_id=_form_text(form.get("study_id"), ""),
        )
    except (TypeError, ValueError) as exc:
        return _render_detail(req, factor_definition(factor_id), "report", error=str(exc))
    trigger_refresh(factor_id)
    return RedirectResponse(f"/factors/{factor_id}?tab=report", status_code=303)


@rt("/{factor_id}/study", methods=["post"])
async def custom_study(req: Request, factor_id: str) -> Any:
    _require_maintenance(req)
    if factor_id not in FACTOR_METADATA:
        return PlainTextResponse("因子不存在", status_code=404)
    meta = factor_definition(factor_id)
    form = await req.form()
    try:
        start = datetime.date.fromisoformat(_form_text(form.get("start"), ""))
        end = datetime.date.fromisoformat(_form_text(form.get("end"), ""))
        holdings = [int(value) for value in form.getlist("holding_days") if isinstance(value, str)]
        if not holdings:
            holdings = list(tracking_view(factor_id).profile.comparison_holding_days)
        run_id = submit_study(
            factor_id,
            start,
            end,
            holdings,
            _form_text(form.get("price_field"), "open"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        return _render_detail(req, meta, "report", error=str(exc))
    return RedirectResponse(f"/factors/{factor_id}?tab=report&study={run_id}", status_code=303)


@rt("/{factor_id}/study/{run_id}/cancel", methods=["post"])
async def cancel_custom_study(req: Request, factor_id: str, run_id: str) -> Any:
    _require_maintenance(req)
    if factor_id not in FACTOR_METADATA:
        return PlainTextResponse("因子不存在", status_code=404)
    task = study_run(run_id)
    if task is not None and factor_id in task.factor_ids:
        cancel_study(run_id)
    return RedirectResponse(f"/factors/{factor_id}?tab=report&study={run_id}", status_code=303)


@rt("/{factor_id}/profile", methods=["post"])
async def update_profile(req: Request, factor_id: str) -> Any:
    _require_maintenance(req)
    if factor_id not in FACTOR_METADATA:
        return RedirectResponse("/factors/", status_code=303)
    form = await req.form()
    try:
        comparisons = [
            int(value)
            for value in form.getlist("comparison_holding_days")
            if isinstance(value, str)
        ]
        save_profile(
            factor_id,
            lookback=_form_text(form.get("lookback"), "3y"),
            primary_holding_days=int(_form_text(form.get("primary_holding_days"), "5")),
            comparison_holding_days=comparisons,
            price_field=_form_text(form.get("price_field"), "open"),
            enabled=form.get("enabled") == "on",
        )
    except (TypeError, ValueError) as exc:
        return _render_detail(req, factor_definition(factor_id), "report", error=str(exc))
    trigger_refresh(factor_id)
    return RedirectResponse(f"/factors/{factor_id}?tab=report", status_code=303)


def _render_detail(
    req: Request,
    meta: FactorDefinition,
    tab: str,
    *,
    custom: CustomStudy | None = None,
    error: str | None = None,
) -> Any:
    view = tracking_view(meta.factor_id)
    task = study_run(req.query_params.get("study") or "")
    if task is not None and meta.factor_id not in task.factor_ids:
        task = None
    if task is not None and custom is None:
        custom = load_study(task.run_id)
    if tab not in {"card", "report"}:
        tab = "card"
    layout = _layout(meta.display_name, f"/factors/{meta.factor_id}")
    content = Div(
        _status_strip(meta, view),
        Div(
            _tab_link(meta.factor_id, "card", "因子卡片", tab == "card"),
            _tab_link(meta.factor_id, "report", "检验报告", tab == "report"),
            cls="mt-4 flex border-b border-gray-100",
        ),
        _card_tab(meta, view)
        if tab == "card"
        else _report_tab(meta, view, custom=custom, task=task, error=error),
        cls="max-w-[1200px] mx-auto p-8",
    )
    layout.set_main_block(content)
    return layout.render(req)


@rt("/{factor_id}")
def detail(req: Request, factor_id: str) -> Any:
    if factor_id not in FACTOR_METADATA:
        return PlainTextResponse("因子不存在", status_code=404)
    meta = factor_definition(factor_id)
    view = tracking_view(factor_id)
    tab = req.query_params.get("tab") or ("report" if view.current else "card")
    return _render_detail(req, meta, tab)
