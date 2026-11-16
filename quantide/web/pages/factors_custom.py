"""Custom factor study form and temporary result rendering."""

from __future__ import annotations

import datetime
from typing import Any

from fasthtml.common import (
    Button as ActionButton,
)
from fasthtml.common import (
    Details,
    Div,
    Form,
    Option,
    P,
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
    Input as TextInput,
)
from fasthtml.common import (
    Select as PlainSelect,
)

from quantide.factors.metadata import FactorDefinition
from quantide.service.factor_study import CustomStudy
from quantide.service.factor_tracking import HOLDING_CHOICES, TrackingProfile
from quantide.web.pages.factors_ui import LOOKBACK_LABELS, PRICE_LABELS, fmt_number, fmt_percent


def _holding_checks(name: str, selected: tuple[int, ...] | list[int], *, prefix: str = "") -> Div:
    return Div(
        *[
            Div(
                TextInput(
                    type="checkbox",
                    name=name,
                    value=str(value),
                    checked=value in selected,
                    cls="checkbox checkbox-sm",
                ),
                Span(f"{value} 日", cls="ml-1 text-xs text-gray-600"),
                cls="flex items-center",
            )
            for value in HOLDING_CHOICES
        ],
        cls=f"mt-1 flex flex-wrap gap-3 {prefix}",
    )


def custom_form(meta: FactorDefinition, profile: TrackingProfile) -> Details:
    today = datetime.date.today()
    start = today - datetime.timedelta(days=365)
    return Details(
        Summary("自定义检验", cls="cursor-pointer text-sm font-medium text-gray-700"),
        P(
            "临时指定固定区间和持有期；结果标记为自定义检验，不会修改自动跟踪方案或快照。",
            cls="mt-2 text-xs text-gray-500",
        ),
        Form(
            Div(
                Div(
                    P("开始日期", cls="text-xs text-gray-500"),
                    TextInput(type="date", name="start", value=start.isoformat(), cls="q-input"),
                ),
                Div(
                    P("结束日期", cls="text-xs text-gray-500"),
                    TextInput(type="date", name="end", value=today.isoformat(), cls="q-input"),
                ),
                Div(
                    P("买入价", cls="text-xs text-gray-500"),
                    PlainSelect(
                        *[
                            Option(label, value=value, selected=profile.price_field == value)
                            for value, label in PRICE_LABELS.items()
                        ],
                        name="price_field",
                        cls="q-input",
                    ),
                ),
                cls="grid gap-3 md:grid-cols-3",
            ),
            P("持有期", cls="mt-3 text-xs text-gray-500"),
            _holding_checks(
                "holding_days",
                profile.comparison_holding_days,
            ),
            ActionButton("运行自定义检验", type="submit", cls="q-btn q-btn--sm mt-3"),
            method="post",
            action=f"/factors/{meta.factor_id}/study",
        ),
        cls="mt-4 rounded-xl border border-gray-100 bg-white p-4 shadow-sm",
    )


def _result_rows(study: CustomStudy) -> list[Any]:
    return [
        Tr(
            Td(f"{result.holding_days} 日"),
            Td(fmt_number(result.rank_ic.mean)),
            Td(fmt_number(result.rank_ic.t_naive, 2)),
            Td(str(result.rank_ic.n_days)),
            Td(str(result.diagnostics.n_valid_pairs)),
            Td(fmt_percent(result.deciles.d1_minus_d10)),
            Td(str(result.diagnostics.as_of_date or "—")),
        )
        for result in study.results
    ]


def _result_table(study: CustomStudy) -> Table:
    return Table(
        Thead(
            Tr(
                *[
                    Th(label, cls="px-3 py-2 text-left text-xs text-gray-500")
                    for label in ("持有期", "RankIC", "t", "有效日", "样本", "D1-D10", "评价截至")
                ]
            )
        ),
        Tbody(*_result_rows(study)),
        cls="mt-3 w-full text-sm",
    )


def _promotion_form(meta: FactorDefinition, study: CustomStudy) -> Any:
    if len(study.holding_days) > 5:
        return P(
            "跟踪方案最多保留 5 个持有期；请减少自定义检验的持有期后再保存。",
            cls="mt-3 border-t border-gray-100 pt-3 text-xs text-gray-500",
        )
    return Form(
        *[
            TextInput(type="hidden", name="holding_days", value=str(value))
            for value in study.holding_days
        ],
        TextInput(type="hidden", name="study_id", value=study.study_id),
        TextInput(type="hidden", name="price_field", value=study.price_field),
        Div(
            Div(
                P("滚动窗口", cls="text-xs text-gray-500"),
                PlainSelect(
                    *[Option(label, value=value) for value, label in LOOKBACK_LABELS.items()],
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
                            selected=value == study.holding_days[0],
                        )
                        for value in study.holding_days
                    ],
                    name="primary_holding_days",
                    cls="q-input",
                ),
            ),
            cls="mt-3 grid gap-3 md:grid-cols-2",
        ),
        P(
            "确认后固定日期不会继续作为跟踪边界；系统按所选滚动窗口重新计算。",
            cls="mt-2 text-xs text-gray-500",
        ),
        ActionButton("确认设为跟踪方案", type="submit", cls="q-btn q-btn--sm mt-3"),
        method="post",
        action=f"/factors/{meta.factor_id}/profile/from-study",
        cls="mt-3 border-t border-gray-100 pt-3",
    )


def custom_result(meta: FactorDefinition, study: CustomStudy) -> Div:
    return Div(
        P("自定义检验结果", cls="text-sm font-semibold text-gray-900"),
        P(
            f"研究 ID {study.study_id} · 区间 {study.start} 至 {study.end} · "
            f"数据截至 {study.data_cutoff} · "
            f"{PRICE_LABELS.get(study.price_field, study.price_field)}",
            cls="mt-1 text-xs text-gray-500",
        ),
        _result_table(study),
        P(
            "这是按历史区间选择的结果，可能存在选择偏差；不能自动视为样本外验证或盈利保证。",
            cls="mt-3 text-xs text-amber-700",
        ),
        _promotion_form(meta, study),
        cls="rounded-xl border border-amber-200 bg-amber-50/40 p-4",
    )
