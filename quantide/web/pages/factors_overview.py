"""Factor overview page widgets and sorting helpers."""

from __future__ import annotations

import math
from statistics import median
from typing import Any
from urllib.parse import urlencode

from fasthtml.common import A, Details, Div, Form, Option, P, Span, Summary, Td, Tr
from fasthtml.common import Button as ActionButton
from fasthtml.common import Input as TextInput
from fasthtml.common import Select as PlainSelect

from quantide.factors.alpha import FEATURE_GROUPS
from quantide.factors.metadata import FactorDefinition
from quantide.service.factor_tracking import TrackingView
from quantide.web.components.data_tables import DatasetTable
from quantide.web.pages.factors_ui import fmt_number, fmt_percent, fmt_time

_SORTABLE_COLUMNS = {
    "rank_ic": "RankIC",
    "annual": "多空年化",
    "annual_long": "纯多年化",
    "t": "t 值",
    "days": "有效日",
    "d1d10": "D1-D10",
}
_TRADING_DAYS = 252


def _primary_deciles(view: TrackingView) -> tuple[dict[str, Any], int | None]:
    current = view.current or {}
    primary = current.get("primary_metrics") or {}
    deciles = primary.get("deciles") or {}
    holding = primary.get("holding_days") or view.profile.primary_holding_days
    try:
        holding_days = int(holding)
    except (TypeError, ValueError):
        return deciles, None
    return deciles, holding_days if holding_days >= 1 else None


def annualized_long_short(view: TrackingView) -> float | None:
    """Estimate annualized D10-minus-D1 return from the holding-period spread."""
    deciles, holding_days = _primary_deciles(view)
    if holding_days is None:
        return None
    d1 = deciles.get("d1_mean_common")
    d10 = deciles.get("d10_mean_common")
    spread: float | None
    if d1 is not None and d10 is not None:
        spread = float(d10) - float(d1)
    elif deciles.get("d1_minus_d10") is not None:
        spread = -float(deciles["d1_minus_d10"])
    else:
        return None
    annualized = spread * _TRADING_DAYS / holding_days
    return annualized if math.isfinite(annualized) else None


def annualized_long_only(view: TrackingView) -> float | None:
    """Estimate annualized D10-only return from the holding-period mean."""
    deciles, holding_days = _primary_deciles(view)
    if holding_days is None:
        return None
    d10 = deciles.get("d10_mean_common")
    if d10 is None:
        for bucket in deciles.get("buckets") or []:
            if bucket.get("bucket") == 10:
                d10 = bucket.get("mean_forward")
                break
    if d10 is None:
        return None
    annualized = float(d10) * _TRADING_DAYS / holding_days
    return annualized if math.isfinite(annualized) else None


def _sort_value(view: TrackingView, key: str) -> float | None:
    current = view.current or {}
    primary = current.get("primary_metrics") or {}
    if key == "annual":
        return annualized_long_short(view)
    if key == "annual_long":
        return annualized_long_only(view)
    if key == "rank_ic":
        return (primary.get("rank_ic") or {}).get("mean")
    if key == "t":
        return (primary.get("rank_ic") or {}).get("t_naive")
    if key == "days":
        return (primary.get("rank_ic") or {}).get("n_days")
    if key == "d1d10":
        return (primary.get("deciles") or {}).get("d1_minus_d10")
    return None


def _sort_entries(
    entries: list[tuple[FactorDefinition, TrackingView]], key: str, direction: str
) -> list[tuple[FactorDefinition, TrackingView]]:
    if key not in _SORTABLE_COLUMNS:
        return entries
    present = [entry for entry in entries if _sort_value(entry[1], key) is not None]
    missing = [entry for entry in entries if _sort_value(entry[1], key) is None]
    present = sorted(
        present,
        key=lambda entry: float(_sort_value(entry[1], key) or 0.0),
        reverse=direction != "asc",
    )
    return present + missing


def _overview_url(
    *,
    query: str,
    group_filter: str,
    sort_key: str = "",
    sort_dir: str = "",
) -> str:
    params = {
        "q": query,
        "group": group_filter,
        "sort": sort_key if sort_key in _SORTABLE_COLUMNS else "",
        "dir": sort_dir if sort_dir in {"asc", "desc"} else "",
    }
    params = {key: value for key, value in params.items() if value}
    return f"/factors/?{urlencode(params)}" if params else "/factors/"


def _sort_header(
    label: str,
    key: str,
    *,
    query: str,
    group_filter: str,
    sort_key: str,
    sort_dir: str,
    description: str = "",
) -> A:
    active = sort_key == key
    next_dir = "asc" if active and sort_dir != "asc" else "desc"
    marker = "↓" if active and sort_dir != "asc" else ("↑" if active else "↕")
    return A(
        Span(label),
        Span(marker, cls="ml-1 text-[10px]", aria_hidden="true"),
        href=_overview_url(
            query=query,
            group_filter=group_filter,
            sort_key=key,
            sort_dir=next_dir,
        ),
        aria_label=f"按{label}排序",
        title=description or None,
        cls=(
            "inline-flex w-full items-center justify-end gap-1 whitespace-nowrap "
            + ("font-semibold text-[#e41815]" if active else "text-gray-500 hover:text-gray-900")
        ),
    )


def _header_label(label: str, description: str) -> Span:
    return Span(label, title=description)


def _summary_card(label: str, value: str, *, tone: str = "text-gray-900") -> Div:
    return Div(
        P(label, cls="text-xs text-gray-500"),
        P(value, cls=f"mt-1 text-xl font-semibold tabular-nums {tone}"),
        cls="rounded-xl border border-gray-100 bg-white px-4 py-3 shadow-sm",
    )


def overview_summary(entries: list[tuple[FactorDefinition, TrackingView]]) -> Div:
    computed = sum(1 for _, view in entries if view.current)
    annualized = [
        value for _, view in entries if (value := annualized_long_short(view)) is not None
    ]
    long_only = [value for _, view in entries if (value := annualized_long_only(view)) is not None]
    median_annualized = fmt_percent(median(annualized)) if annualized else "—"
    median_long_only = fmt_percent(median(long_only)) if long_only else "—"
    updates = [
        fmt_time((view.current or {}).get("computed_at"))
        for _, view in entries
        if (view.current or {}).get("computed_at")
    ]
    latest_update = max(updates) if updates else "—"
    return Div(
        _summary_card("因子总数", str(len(entries))),
        _summary_card("已有结果", str(computed)),
        _summary_card("多空年化中位数", median_annualized),
        _summary_card("纯多年化中位数", median_long_only),
        _summary_card("最近更新", latest_update),
        cls="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5",
    )


def overview_toolbar(
    *,
    query: str,
    group_filter: str,
    sort_key: str,
    sort_dir: str,
    result_count: int,
    total_count: int,
) -> Div:
    filter_form = Form(
        Div(
            P("关键词", cls="mb-1 text-xs text-gray-500"),
            TextInput(
                type="search",
                name="q",
                value=query,
                placeholder="名称或 ID",
                aria_label="按名称或 ID 筛选",
                cls="q-input h-9 w-56",
            ),
        ),
        Div(
            P("分组", cls="mb-1 text-xs text-gray-500"),
            PlainSelect(
                Option("全部分组", value="", selected=not group_filter),
                *[
                    Option(group, value=group, selected=group_filter == group)
                    for group in FEATURE_GROUPS
                ],
                name="group",
                aria_label="按因子分组筛选",
                cls="q-input h-9 w-56",
            ),
        ),
        TextInput(type="hidden", name="sort", value=sort_key),
        TextInput(type="hidden", name="dir", value=sort_dir),
        Div(
            ActionButton("应用筛选", type="submit", cls="q-btn q-btn--primary h-9 px-3"),
            (
                A(
                    "清除",
                    href="/factors/",
                    cls="px-2 text-sm text-gray-500 hover:text-[#e41815]",
                )
                if query or group_filter
                else None
            ),
            cls="flex items-center gap-2",
        ),
        method="get",
        cls="flex flex-wrap items-end gap-3",
        aria_label="因子筛选",
    )
    return Div(
        Div(
            P("因子列表", cls="text-base font-semibold text-gray-900"),
            P(
                f"当前 {result_count} / 共 {total_count} 个因子；点击数值列标题可切换排序。",
                cls="mt-1 text-xs text-gray-500",
            ),
        ),
        filter_form,
        cls="flex flex-wrap items-end justify-between gap-4",
    )


def tracking_onboarding(entries: list[tuple[FactorDefinition, TrackingView]]) -> Any:
    if not entries or any(view.current for _, view in entries):
        return None
    return Div(
        P("还没有因子跟踪结果", cls="text-sm font-medium text-gray-900"),
        P(
            "系统会在每日 18:45 自动更新；错过后会在服务启动时补查。",
            cls="mt-1 text-sm text-gray-600",
        ),
        cls="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-4",
    )


def _overview_empty(query: str, group_filter: str) -> Div:
    has_filter = bool(query or group_filter)
    return Div(
        P(
            "没有匹配的因子" if has_filter else "暂无因子",
            cls="text-sm font-medium text-gray-900",
        ),
        P(
            "调整搜索词或分组后重试。" if has_filter else "系统尚未发现可用因子。",
            cls="mt-1 text-sm text-gray-500",
        ),
        (
            A("清除筛选", href="/factors/", cls="mt-3 inline-flex text-sm text-[#e41815]")
            if has_filter
            else None
        ),
        cls="p-10 text-center",
    )


def _return_tone(value: float | None) -> str:
    if value is None or value == 0:
        return "text-gray-500"
    return "text-red-600" if value > 0 else "text-green-700"


def overview_row(meta: FactorDefinition, view: TrackingView) -> Any:
    current = view.current or {}
    primary = current.get("primary_metrics") or {}
    rank_ic = primary.get("rank_ic") or {}
    diagnostics = primary.get("diagnostics") or {}
    deciles = primary.get("deciles") or {}
    annualized = annualized_long_short(view)
    long_only = annualized_long_only(view)
    return Tr(
        Td(
            A(
                Div(
                    Span(
                        meta.display_name,
                        cls="font-medium text-gray-900 hover:text-[#e41815] hover:underline",
                    ),
                    Div(meta.factor_id, cls="mt-0.5 font-mono text-xs text-gray-500"),
                ),
                href=f"/factors/{meta.factor_id}",
                aria_label=f"查看因子 {meta.display_name}",
                cls="block",
            ),
            cls="min-w-[220px] px-4 py-3",
        ),
        Td(meta.group, cls="hidden px-4 py-3 text-xs text-gray-500 lg:table-cell"),
        Td(
            fmt_number(rank_ic.get("mean")),
            cls="px-4 py-3 text-right font-medium tabular-nums whitespace-nowrap",
        ),
        Td(
            fmt_percent(annualized),
            cls=(
                "px-4 py-3 text-right font-medium tabular-nums whitespace-nowrap "
                + _return_tone(annualized)
            ),
        ),
        Td(
            fmt_percent(long_only),
            cls=(
                "px-4 py-3 text-right font-medium tabular-nums whitespace-nowrap "
                + _return_tone(long_only)
            ),
        ),
        Td(
            fmt_number(rank_ic.get("t_naive"), 2),
            cls="px-4 py-3 text-right tabular-nums whitespace-nowrap",
        ),
        Td(
            str(rank_ic.get("n_days") or 0) if current else "—",
            cls="px-4 py-3 text-right tabular-nums whitespace-nowrap",
        ),
        Td(
            fmt_percent(deciles.get("d1_minus_d10")),
            cls="px-4 py-3 text-right tabular-nums whitespace-nowrap",
        ),
        Td(
            f"{view.profile.primary_holding_days} 日",
            cls="px-4 py-3 text-right tabular-nums whitespace-nowrap",
        ),
        Td(
            Div(
                P(str(current.get("data_cutoff") or "—"), cls="text-sm text-gray-700"),
                P(
                    fmt_time(current.get("computed_at")),
                    cls="mt-0.5 text-xs text-gray-400",
                ),
            ),
            title=f"评价截至 {diagnostics.get('as_of_date') or '—'}",
            cls="px-4 py-3 text-right whitespace-nowrap",
        ),
    )


def metric_guide() -> Details:
    definitions = [
        ("分组", "因子所属的研究分组，用于筛选同类因子，不参与评分。"),
        ("RankIC", "每日因子排名与未来收益排名的相关系数均值；绝对值越大信号越强。"),
        (
            "多空年化",
            "按 D10-D1 的持有期平均收益线性年化（×252/持有期），用于横向比较，"
            "不是可直接交易的组合收益。",
        ),
        (
            "纯多年化",
            "按 D10 组合的持有期平均收益线性年化；包含市场 beta，不能与多空收益直接比较。",
        ),
        ("t 值", "RankIC 均值的普通 t 值；越大越显著，但未校正自相关和多重检验。"),
        ("有效日", "参与统计的有效交易日数量，过少时结论不稳定。"),
        (
            "D1-D10",
            "D1 减 D10 的持有期平均前瞻收益差，保持原始持有期，未年化；符号与多空年化相反。",
        ),
        ("持有期", "评价使用的前瞻收益窗口；不同持有期的结果不能直接横向比较。"),
        (
            "数据 / 更新",
            "数据截至是参与计算的最后交易日；更新是快照生成时间。"
            "评价截至（最后成熟信号日）见因子详情页。",
        ),
    ]
    return Details(
        Summary("字段说明", cls="cursor-pointer text-sm font-medium text-gray-700"),
        Div(
            *[
                Div(
                    Span(label, cls="font-medium text-gray-700"),
                    Span(description, cls="text-gray-500"),
                    cls="grid gap-1 md:grid-cols-[120px_1fr]",
                )
                for label, description in definitions
            ],
            cls="mt-3 space-y-2 text-xs leading-5",
        ),
        cls="rounded-xl border border-gray-100 bg-white p-4 shadow-sm",
    )


def overview_table(
    rows: list[Any],
    *,
    query: str,
    group_filter: str,
    sort_key: str,
    sort_dir: str,
) -> Div:
    if not rows:
        return _overview_empty(query, group_filter)
    sort_args = {
        "query": query,
        "group_filter": group_filter,
        "sort_key": sort_key,
        "sort_dir": sort_dir,
    }
    headers = [
        _header_label("因子", "因子名称与唯一 ID；点击进入因子详情。"),
        _header_label("分组", "因子所属研究分组，用于筛选同类因子。"),
        _sort_header(
            "RankIC",
            "rank_ic",
            description="每日因子排名与未来收益排名的相关系数均值；绝对值越大信号越强。",
            **sort_args,
        ),
        _sort_header(
            "多空年化",
            "annual",
            description=(
                "按 D10-D1 的持有期平均收益线性年化；仅用于量级比较，不是可直接交易的组合收益。"
            ),
            **sort_args,
        ),
        _sort_header(
            "纯多年化",
            "annual_long",
            description=(
                "按 D10 组合的持有期平均收益线性年化；包含市场 beta，不能与多空收益直接比较。"
            ),
            **sort_args,
        ),
        _sort_header(
            "t 值",
            "t",
            description="RankIC 均值的普通 t 值；越大越显著，但未校正自相关与多重检验。",
            **sort_args,
        ),
        _sort_header(
            "有效日",
            "days",
            description="参与统计的有效交易日数量。",
            **sort_args,
        ),
        _sort_header(
            "D1-D10",
            "d1d10",
            description=(
                "D1 减 D10 的持有期平均前瞻收益差，未年化；正数表示最低组跑赢，符号与多空年化相反。"
            ),
            **sort_args,
        ),
        _header_label("持有期", "当前评价使用的前瞻收益窗口。"),
        _header_label("数据 / 更新", "评价数据截至日期与快照生成时间。"),
    ]
    return Div(
        DatasetTable(
            headers,
            rows,
            column_classes=[
                "",
                "hidden lg:table-cell",
                "text-right",
                "text-right",
                "text-right",
                "text-right",
                "text-right",
                "text-right",
                "text-right",
                "text-right",
            ],
            sticky_header=True,
            aria_label="因子总览列表",
        ),
        cls="overflow-hidden rounded-xl border border-gray-100 bg-white shadow-sm",
    )
