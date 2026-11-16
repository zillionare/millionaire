"""系统维护 - 风险事件中心页面。"""

from __future__ import annotations

from typing import Any

from fasthtml.common import Div
from starlette.requests import Request

from quantide.web.application import fast_app
from quantide.web.components.navigation import SystemBreadcrumb
from quantide.web.layouts.main import MainLayout
from quantide.web.pages.system.runtime_support import (
    build_risk_event_center_card,
    build_risk_event_center_content,
)
from quantide.web.session_data import SessionData
from quantide.web.theme import AppTheme

system_risk_events_app, rt = fast_app(hdrs=AppTheme.headers())


def _breadcrumb() -> Div:
    return SystemBreadcrumb("风险事件中心")


@rt("/")
def index(req: Request, session: SessionData) -> Any:
    """渲染风险事件中心页面。"""
    layout = MainLayout(title="风险事件中心", user=session.get("auth"))
    layout.set_sidebar_active("/system/risk-events")
    layout.set_main_block(
        lambda: Div(
            _breadcrumb(),
            build_risk_event_center_card(refresh_path="/system/risk-events/panel"),
            cls="space-y-6 max-w-[1400px] mx-auto w-full",
        )
    )
    return layout.render(req)


@rt("/panel")
def panel(req: Request) -> Any:
    """返回风险事件中心刷新片段。"""
    return build_risk_event_center_content()
