"""系统维护 - 运行时监控页面。"""

from __future__ import annotations

from fasthtml.common import A, Div, Nav, Span, fast_app

from quantide.service.strategy_runtime import strategy_runtime_manager
from quantide.web.layouts.main import MainLayout
from quantide.web.pages.system.runtime_support import (
    build_runtime_table_card,
    build_runtime_table_content,
)
from quantide.web.theme import AppTheme

system_runtime_monitor_app, rt = fast_app(hdrs=AppTheme.headers())


def _breadcrumb() -> Div:
    """构建页面面包屑。"""
    return Div(
        Nav(
            A("首页", href="/", cls="hover:text-blue-600"),
            Span(">", cls="text-gray-400"),
            A("系统维护", href="/system/", cls="hover:text-blue-600"),
            Span(">", cls="text-gray-400"),
            Span("运行时监控", cls="text-gray-900 font-medium"),
            cls="flex items-center space-x-2 text-sm text-gray-600",
        ),
        cls="mb-4",
    )


@rt("/")
def index(req, session):
    """渲染运行时监控页面。"""
    layout = MainLayout(title="运行时监控", user=session.get("auth"))
    layout.set_sidebar_active("/system/runtime-monitor")
    layout.main_block = lambda: Div(
        _breadcrumb(),
        build_runtime_table_card(
            refresh_path="/system/runtime-monitor/table",
            action_base_path="/system/runtime-monitor",
            target_selector="#runtime-monitor",
        ),
        cls="space-y-6 max-w-[1400px] mx-auto w-full",
    )
    return layout.render(req)


@rt("/table")
def table(req):
    """返回运行时监控刷新片段。"""
    return build_runtime_table_content(
        action_base_path="/system/runtime-monitor",
        target_selector="#runtime-monitor",
    )


async def _read_runtime_action(req) -> tuple[str, str]:
    """读取运行时操作表单。"""
    form = await req.form()
    return str(form.get("target_kind") or ""), str(form.get("target_id") or form.get("runtime_id") or "")


def _runtime_response() -> Div:
    """返回运行时监控刷新内容。"""
    return build_runtime_table_content(
        action_base_path="/system/runtime-monitor",
        target_selector="#runtime-monitor",
    )


@rt("/stop", methods=["POST"])
async def stop(req):
    """停止运行时。"""
    _, runtime_id = await _read_runtime_action(req)
    if runtime_id:
        try:
            strategy_runtime_manager.stop_strategy_runtime(runtime_id)
        except Exception:
            pass
    return _runtime_response()


@rt("/start", methods=["POST"])
async def start(req):
    """启动运行时。"""
    _, runtime_id = await _read_runtime_action(req)
    if runtime_id:
        try:
            strategy_runtime_manager.start_strategy_runtime(runtime_id)
        except Exception:
            pass
    return _runtime_response()


@rt("/block", methods=["POST"])
async def block(req):
    """封锁账户或策略运行时。"""
    target_kind, target_id = await _read_runtime_action(req)
    if target_kind == "account" and target_id:
        strategy_runtime_manager.block_account(target_id)
    elif target_kind == "strategy" and target_id:
        strategy_runtime_manager.block_strategy(target_id)
    return _runtime_response()


@rt("/unblock", methods=["POST"])
async def unblock(req):
    """解除账户或策略运行时封锁。"""
    target_kind, target_id = await _read_runtime_action(req)
    if target_kind == "account" and target_id:
        strategy_runtime_manager.unblock_account(target_id)
    elif target_kind == "strategy" and target_id:
        strategy_runtime_manager.unblock_strategy(target_id)
    return _runtime_response()
