"""Shared shell for the small system settings pages."""

from __future__ import annotations

from typing import Any

from fasthtml.common import H2, A, Div
from starlette.requests import Request

from quantide.web.components.navigation import SystemBreadcrumb
from quantide.web.layouts.main import MainLayout


def render_settings_page(
    req: Request,
    *,
    title: str,
    active: str,
    body: Any,
    error: str = "",
    saved: bool = False,
    saved_message: str = "设置已保存。",
) -> Any:
    layout = MainLayout(title=title, user=req.session.get("auth"))
    layout.set_sidebar_active(active)
    layout.set_main_block(
        lambda: Div(
            SystemBreadcrumb(title),
            H2(title, cls="text-2xl font-bold mb-4"),
            Div(error, role="alert", cls="text-red-700 mb-4") if error else None,
            Div(saved_message, cls="text-green-700 mb-4") if saved else None,
            body,
            A("返回系统维护", href="/system/", cls="text-sm text-gray-600"),
            cls="space-y-4",
        )
    )
    return layout.render(req)


__all__ = ["render_settings_page"]
