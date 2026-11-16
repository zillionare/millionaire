"""Read-only account-fact attribution page."""

from __future__ import annotations

from typing import Any

from fasthtml.common import Div, P, Table, Tbody, Td, Th, Thead, Tr
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from quantide.service.attribution_facts import (
    attribution_markdown,
    attribution_report,
    facts_from_db,
)
from quantide.web.application import fast_app
from quantide.web.layouts.main import MainLayout
from quantide.web.theme import AppTheme

attribution_app, rt = fast_app(hdrs=AppTheme.headers())


def _rows(values: dict[str, float], label: str) -> Any:
    return Table(
        Thead(Tr(Th(label), Th("贡献", cls="text-right"))),
        Tbody(
            *[
                Tr(Td(name), Td(f"{value:.6f}", cls="text-right"))
                for name, value in sorted(values.items())
            ]
        ),
        cls="w-full text-sm",
    )


@rt("/{portfolio_id}")
def attribution_page(req: Request, portfolio_id: str) -> Any:
    report = attribution_report(facts_from_db(portfolio_id))
    layout = MainLayout(title=f"收益归因 · {portfolio_id}")
    layout.header_active = "策略"
    if report.get("status") == "INSUFFICIENT":
        body = P(f"数据不足：{report.get('reason', '')}", cls="p-8 text-sm text-gray-600")
    else:
        body = P(
            f"权益 {report['start_equity']:.2f} → {report['end_equity']:.2f}，"
            f"成本 {report['costs']:.2f}，残差 {report['residual']:.2f}",
            cls="p-4 text-sm text-gray-700",
        )
        body = (
            body,
            _rows(report["asset_contributions"], "资产"),
            _rows(report["strategy_contributions"], "策略"),
        )
    layout.set_main_block(Div(body, cls="mx-auto max-w-[1000px] p-6"))
    return layout.render(req)


@rt("/{portfolio_id}/markdown")
def attribution_markdown_page(req: Request, portfolio_id: str) -> PlainTextResponse:
    report = attribution_report(facts_from_db(portfolio_id))
    return PlainTextResponse(attribution_markdown(report))
