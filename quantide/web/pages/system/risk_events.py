"""系统维护 - 风险事件中心页面。"""

from __future__ import annotations

from fasthtml.common import A, Div, Nav, Span, fast_app

from quantide.web.layouts.main import MainLayout
from quantide.web.pages.system.runtime_support import (
    build_risk_event_center_card,
    build_risk_event_center_content,
)
from quantide.web.theme import AppTheme

system_risk_events_app, rt = fast_app(hdrs=AppTheme.headers())


def _breadcrumb() -> Div:
    """构建页面面包屑。"""
    return Div(
        Nav(
            A("首页", href="/", cls="hover:text-blue-600"),
            Span(">", cls="text-gray-400"),
            A("系统维护", href="/system/", cls="hover:text-blue-600"),
            Span(">", cls="text-gray-400"),
            Span("风险事件中心", cls="text-gray-900 font-medium"),
            cls="flex items-center space-x-2 text-sm text-gray-600",
        ),
        cls="mb-4",
    )


@rt("/")
def index(req, session):
    """渲染风险事件中心页面。"""
    layout = MainLayout(title="风险事件中心", user=session.get("auth"))
    layout.set_sidebar_active("/system/risk-events")
    layout.main_block = lambda: Div(
        _breadcrumb(),
        build_risk_event_center_card(refresh_path="/system/risk-events/panel"),
        cls="space-y-6 max-w-[1400px] mx-auto w-full",
    )
    return layout.render()


@rt("/panel")
def panel(req):
    """返回风险事件中心刷新片段。"""
    return build_risk_event_center_content()
