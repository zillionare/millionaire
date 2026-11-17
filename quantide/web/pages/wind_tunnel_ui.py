"""Reusable five-state wind-tunnel badge and evidence card."""

from __future__ import annotations

from typing import Any

from fasthtml.common import A, Details, Div, Form, P, Span, Summary, Table, Tbody, Td, Th, Thead, Tr
from fasthtml.common import Button as ActionButton

from quantide.service.factor_audit import WindTunnelBadgeView

_TONES = {
    "PASS": ("bg-emerald-50 text-emerald-700 border-emerald-200", "风洞 PASS"),
    "FAIL": ("bg-red-50 text-red-700 border-red-200", "风洞 FAIL"),
    "INCONCLUSIVE": ("bg-amber-50 text-amber-700 border-amber-200", "风洞 INCONCLUSIVE"),
    "STALE": ("bg-slate-100 text-slate-700 border-slate-300", "风洞 STALE"),
    "UNVERIFIED": ("bg-gray-50 text-gray-500 border-gray-200", "风洞 UNVERIFIED"),
}
_STATUS_TONES = {
    "PASS": "text-emerald-700",
    "FAIL": "text-red-700",
    "INCONCLUSIVE": "text-amber-700",
    "STALE": "text-slate-600",
    "UNVERIFIED": "text-gray-500",
}


def wind_tunnel_badge(
    view: WindTunnelBadgeView,
    *,
    href: str | None = None,
    compact: bool = True,
) -> Any:
    """Render the badge with a stable identifier for page tests."""
    tone, label = _TONES.get(view.badge_status, _TONES["UNVERIFIED"])
    text = label if not compact else label.replace("风洞 ", "")
    content = Span(
        text,
        cls=(
            f"inline-flex items-center rounded-full border px-2.5 py-0.5 "
            f"text-xs font-semibold {tone}"
        ),
        title=view.message or view.first_difference_summary or label,
    )
    if href:
        return A(
            content,
            href=href,
            id=f"wind_tunnel_badge_{view.target_kind}_{view.target_id}",
            aria_label=f"查看 {view.target_id} 风洞报告",
        )
    return Span(content, id=f"wind_tunnel_badge_{view.target_kind}_{view.target_id}")


def _check_rows(view: WindTunnelBadgeView) -> list[Any]:
    return [
        Tr(
            Td(str(item.get("id") or ""), cls="px-2 py-1 font-mono text-xs text-gray-600"),
            Td(
                str(item.get("status") or ""),
                cls=(
                    "px-2 py-1 text-xs font-semibold "
                    + _STATUS_TONES.get(str(item.get("status")), "text-gray-500")
                ),
            ),
            Td(str(item.get("message") or ""), cls="px-2 py-1 text-xs text-gray-500"),
        )
        for item in view.check_items
    ]


def _fingerprints(view: WindTunnelBadgeView) -> Any:
    rows = [
        ("source_hash", view.source_hash, view.recorded_source_hash),
        ("config_hash", view.config_hash, view.recorded_config_hash),
        ("data_hash", view.data_hash, view.recorded_data_hash),
    ]
    return Table(
        Thead(Tr(Th("指纹"), Th("当前"), Th("记录"))),
        Tbody(
            *[
                Tr(
                    Td(name, cls="px-2 py-1 font-mono text-xs text-gray-500"),
                    Td((current or "—")[:16], cls="px-2 py-1 font-mono text-xs"),
                    Td((recorded or "—")[:16], cls="px-2 py-1 font-mono text-xs text-gray-500"),
                )
                for name, current, recorded in rows
            ]
        ),
        cls="mt-2 w-full text-left",
    )


def wind_tunnel_card(
    view: WindTunnelBadgeView,
    *,
    run_url: str | None = None,
    export_url: str | None = None,
    backtest_url: str | None = None,
) -> Any:
    """Render the foldable evidence card with checks and export entries."""
    actions: list[Any] = []
    if run_url:
        actions.append(
            Form(
                ActionButton("立即运行风洞体检", type="submit", cls="q-btn q-btn--sm"),
                method="post",
                action=run_url,
            )
        )
    if export_url:
        actions.extend(
            [
                A("导出 JSON", href=f"{export_url}?format=json", cls="text-sm text-[#e41815]"),
                A("导出 Markdown", href=f"{export_url}?format=md", cls="text-sm text-[#e41815]"),
            ]
        )
    if backtest_url:
        actions.append(A("查看回测", href=backtest_url, cls="text-sm text-[#e41815]"))
    body = [
        P(view.message, cls="text-sm text-gray-600") if view.message else None,
        P(
            view.first_difference_summary or "无首次差异记录。",
            cls=(
                "mt-1 text-sm text-red-600"
                if view.first_difference_summary
                else "mt-1 text-sm text-gray-500"
            ),
        ),
        P(
            f"运行 ID：{view.run_id or '—'} · 执行时间：{view.checked_at or '—'} · "
            f"数据截至：{view.data_end or '—'}",
            cls="mt-1 text-xs text-gray-500",
        ),
        _fingerprints(view),
        Table(
            Thead(Tr(Th("检查项"), Th("状态"), Th("说明"))),
            Tbody(*_check_rows(view)),
            cls="mt-3 w-full text-left",
        ),
    ]
    return Details(
        Summary(
            Div(
                Span("风洞体检详情", cls="font-medium text-gray-800"),
                wind_tunnel_badge(view),
                cls="inline-flex items-center gap-2",
            ),
            cls="cursor-pointer",
        ),
        *[item for item in body if item is not None],
        Div(*actions, cls="mt-3 flex flex-wrap items-center gap-3") if actions else None,
        cls="mt-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm",
    )


__all__ = ["wind_tunnel_badge", "wind_tunnel_card"]
