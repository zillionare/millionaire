"""Factor preset management and ablation comparison pages."""

from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any

from fasthtml.common import (
    H1,
    H2,
    A,
    Div,
    Form,
    Input,
    Option,
    P,
    Select,
    Span,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
)
from fasthtml.common import Button as ActionButton
from starlette.requests import Request
from starlette.responses import RedirectResponse

from quantide.factors.registry import all_factor_ids
from quantide.service.factor_presets import (
    delete_preset,
    list_presets,
    load_preset,
    save_preset,
)
from quantide.service.research_backtest import AblationStudySpec, run_ablation
from quantide.web.layouts.main import MainLayout
from quantide.web.pages.strategy_routes import rt
from quantide.web.session_data import SessionData


def _layout(title: str) -> MainLayout:
    layout = MainLayout(title=title)
    layout.header_active = "策略"
    layout.sidebar_menu = [
        {"title": "策略列表", "url": "/strategy"},
        {"title": "因子预设与消融", "url": "/strategy/presets", "active": True},
    ]
    return layout


def _preset_rows() -> list[Any]:
    rows = []
    for preset in list_presets():
        rows.append(
            Tr(
                Td(preset.preset_id, cls="px-3 py-2 font-mono text-xs"),
                Td(preset.name, cls="px-3 py-2"),
                Td(str(len(preset.features)), cls="px-3 py-2 text-right"),
                Td(preset.label_kind, cls="px-3 py-2 text-xs"),
                Td(preset.bar_interval, cls="px-3 py-2 text-xs"),
                Td(preset.updated_at, cls="px-3 py-2 text-xs text-gray-500"),
                Td(
                    Form(
                        ActionButton("删除", type="submit", cls="text-xs text-red-600"),
                        method="post",
                        action=f"/strategy/presets/{preset.preset_id}/delete",
                    ),
                    cls="px-3 py-2",
                ),
            )
        )
    return rows


def _create_form() -> Any:
    features = ", ".join(all_factor_ids()[:8])
    return Div(
        H2("新建因子预设", cls="text-lg font-semibold"),
        Form(
            Div(
                Input(name="preset_id", placeholder="preset_id", cls="q-input"),
                Input(name="name", placeholder="显示名称", cls="q-input"),
                cls="grid grid-cols-2 gap-2",
            ),
            Input(name="features", value=features, cls="q-input w-full mt-2"),
            Div(
                Select(
                    Option("raw_return", value="raw_return", selected=True),
                    Option("excess_mean", value="excess_mean"),
                    Option("cs_rank", value="cs_rank"),
                    name="label_kind",
                    cls="q-input",
                ),
                ActionButton("保存预设", type="submit", cls="q-btn q-btn--primary"),
                cls="mt-2 flex gap-2",
            ),
            method="post",
            action="/strategy/presets/save",
            cls="mt-2",
        ),
        cls="rounded-xl border border-gray-100 bg-white p-4 shadow-sm",
    )


def _ablation_form() -> Any:
    presets = list_presets()
    options = [Option(preset.preset_id, value=preset.preset_id) for preset in presets]
    variant_boxes = [
        Span(
            Input(type="checkbox", name="variant", value=preset.preset_id),
            Span(f" {preset.preset_id}", cls="ml-1"),
            cls="mr-3 inline-flex items-center text-sm",
        )
        for preset in presets
    ]
    return Div(
        H2("一键消融对比", cls="text-lg font-semibold"),
        P(
            "Baseline 与 Variants 强制使用同一区间、本金、费用、PIT 规则与随机种子。",
            cls="text-xs text-gray-500",
        ),
        Form(
            Div(
                Span("Baseline", cls="text-sm text-gray-500 mr-2"),
                Select(*options, name="baseline", cls="q-input"),
                cls="flex items-center gap-2",
            ),
            Div(*variant_boxes, cls="mt-2"),
            Div(
                Input(name="start", type="date", value="2024-01-01", cls="q-input"),
                Input(name="end", type="date", value=dt.date.today().isoformat(), cls="q-input"),
                Input(name="principal", type="number", value="1000000", cls="q-input"),
                ActionButton("运行消融对比", type="submit", cls="q-btn q-btn--primary"),
                cls="mt-2 flex flex-wrap items-center gap-2",
            ),
            method="post",
            action="/strategy/presets/ablation/run",
            cls="mt-2",
        ),
        cls="rounded-xl border border-gray-100 bg-white p-4 shadow-sm",
    )


@rt("/presets")
def preset_index(req: Request, session: SessionData) -> Any:
    layout = _layout("因子预设")
    rows = _preset_rows()
    table = Table(
        Thead(
            Tr(
                Th("ID"),
                Th("名称"),
                Th("因子数"),
                Th("标签"),
                Th("周期"),
                Th("更新"),
                Th("操作"),
            )
        ),
        Tbody(*rows)
        if rows
        else Tbody(Tr(Td("暂无因子预设", colspan="7", cls="p-4 text-gray-500"))),
        cls="w-full text-left",
    )
    layout.set_main_block(
        lambda: Div(
            H1("因子预设与消融对比", cls="text-2xl font-bold"),
            P(
                "预设保存后仍会在每次加载时逐项校验因子存在、周期和风洞准入状态。",
                cls="mt-1 text-sm text-gray-500",
            ),
            Div(table, cls="mt-4 rounded-xl border border-gray-100 bg-white p-4 shadow-sm"),
            Div(_create_form(), cls="mt-4"),
            Div(_ablation_form(), cls="mt-4"),
            cls="max-w-6xl mx-auto py-8",
        )
    )
    return layout.render(req)


@rt("/presets/save", methods=["POST"])
async def preset_save(req: Request) -> Any:
    form = await req.form()
    features = [item.strip() for item in str(form.get("features") or "").split(",") if item.strip()]
    save_preset(
        str(form.get("preset_id") or ""),
        str(form.get("name") or ""),
        features,
        label_kind=str(form.get("label_kind") or "raw_return"),
    )
    return RedirectResponse("/strategy/presets", status_code=303)


@rt("/presets/{preset_id}/delete", methods=["POST"])
def preset_delete(req: Request, preset_id: str) -> RedirectResponse:
    delete_preset(preset_id)
    return RedirectResponse("/strategy/presets", status_code=303)


def _ablation_result_view(report: dict[str, Any]) -> Any:
    rows = []
    for item in report.get("variants") or []:
        rows.append(
            Tr(
                Td(str(item.get("preset_id") or "")),
                Td(f"{(item.get('annual_return') or 0) * 100:.2f}%"),
                Td(f"{(item.get('annual_excess') or 0) * 100:.2f}%"),
                Td(f"{(item.get('max_drawdown') or 0) * 100:.2f}%"),
                Td(str(item.get("sharpe") or "—")),
                Td(str(item.get("calmar") or "—")),
                Td(f"{item.get('turnover') or 0:.2f}"),
                Td(f"{item.get('total_fees') or 0:.2f}"),
            )
        )
    return Div(
        H2("消融对比结果", cls="text-lg font-semibold"),
        P(
            f"Baseline: {report['spec']['baseline_preset_id']} · "
            f"{report['spec']['start']} ~ {report['spec']['end']}",
            cls="text-xs text-gray-500",
        ),
        Table(
            Thead(
                Tr(
                    Th("Variant"),
                    Th("年化"),
                    Th("年化超额"),
                    Th("最大回撤"),
                    Th("Sharpe"),
                    Th("Calmar"),
                    Th("换手"),
                    Th("费用"),
                )
            ),
            Tbody(*rows),
            cls="mt-2 w-full text-sm",
        ),
        cls="mt-4 rounded-xl border border-gray-100 bg-white p-4 shadow-sm",
    )


@rt("/presets/ablation/run", methods=["POST"])
async def preset_ablation_run(req: Request) -> Any:
    form = await req.form()
    baseline = str(form.get("baseline") or "")
    variants = tuple(str(value) for value in form.getlist("variant"))
    start = dt.date.fromisoformat(str(form.get("start")))
    end = dt.date.fromisoformat(str(form.get("end")))
    principal = float(str(form.get("principal") or 1_000_000))
    spec = AblationStudySpec(
        baseline_preset_id=baseline,
        variant_preset_ids=variants[:5],
        start=start,
        end=end,
        principal=principal,
        strategy_id=load_preset(baseline).strategy_id,
    )
    report = await asyncio.to_thread(run_ablation, spec)
    layout = _layout("消融对比")
    layout.set_main_block(
        lambda: Div(
            A("← 返回因子预设", href="/strategy/presets", cls="text-gray-500"),
            _ablation_result_view(report),
            cls="max-w-6xl mx-auto py-8",
        )
    )
    return layout.render(req)


__all__ = ["preset_index"]
