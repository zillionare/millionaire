"""Consistent navigation and download progress for dataset management pages."""

from collections.abc import Callable, Sequence
from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    H2,
    H3,
    A,
    Button,
    Div,
    P,
    Script,
)
from monsterui.all import *
from monsterui.all import UkIcon
from starlette.requests import Request

from quantide.web.layouts.main import MainLayout
from quantide.web.template_assets import render_asset
from quantide.web.theme import PRIMARY_COLOR


def DatasetTabs(base_path: str, active_tab: str, tabs: Sequence[tuple[str, str]]) -> Any:
    tab_items = []
    for tab_id, label in tabs:
        is_active = active_tab == tab_id
        base_cls = "px-4 py-2 font-medium transition-colors duration-200"
        if is_active:
            cls = f"{base_cls} text-red-600 border-b-2 border-red-600"
        else:
            cls = (
                f"{base_cls}"
                " text-gray-500 hover:text-gray-700 hover:border-b-2 "
                "hover:border-gray-300"
            )

        tab_items.append(A(label, href=f"{base_path}?tab={tab_id}", cls=cls))

    return Div(Div(*tab_items, cls="flex space-x-2"), cls="border-b border-gray-200 mb-6")


def DatasetPage(
    request: Request,
    base_path: str,
    title: str,
    icon: str,
    active_tab: str,
    tabs: Sequence[tuple[str, str]],
    content: Any,
) -> Any:
    layout = MainLayout()
    layout.set_sidebar_active(base_path)
    layout.set_main_block(
        Div(
            Div(
                Div(
                    UkIcon(icon, size=32, cls="mr-3", style=f"color: {PRIMARY_COLOR};"),
                    H2(title, cls="text-2xl font-bold"),
                    cls="flex items-center",
                ),
                cls="mb-8",
            ),
            DatasetTabs(base_path, active_tab, tabs),
            content,
            cls="p-8",
        )
    )
    return layout.render(request)


def new_sync_status(**extras: object) -> dict[str, Any]:
    return dict(is_running=False, progress=0, message="", completed=False, error=None, **extras)


def DatasetProgressDialog(prefix: str, title: str, url: str, close_id: str | None = None) -> Any:
    bar_id, status_id = f"{prefix}-progress-bar", f"{prefix}-status"
    close_id = close_id or f"{prefix}-close-btn"
    return Div(
        Div(
            Div(
                H3(title, cls="text-lg font-bold mb-4"),
                Div(
                    Div(id=bar_id, cls="bg-red-600 h-2 rounded-full", style="width: 0%"),
                    cls="w-full bg-gray-200 rounded-full h-2 mb-2",
                ),
                P(id=status_id, children=["准备中..."], cls="text-sm text-gray-600"),
                Div(
                    Button(
                        "关闭",
                        id=close_id,
                        cls="btn btn-ghost mt-6",
                        disabled=True,
                        onclick="this.closest('.fixed').remove()",
                    ),
                    cls="flex justify-end",
                ),
                cls="bg-white p-6 rounded-xl shadow-xl max-w-md w-full",
            ),
            cls="fixed inset-0 bg-black/50 flex items-center justify-center z-50",
        ),
        Script(
            render_asset(
                "dataset-progress.js.tmpl",
                BAR_ID=bar_id,
                STATUS_ID=status_id,
                CLOSE_ID=close_id,
                URL=url,
            )
        ),
    )


def dataset_content(
    active_tab: str,
    overview: Callable[[], Any],
    update: Callable[[], Any],
    **tabs: Callable[[], Any],
) -> Any:
    return tabs.get(active_tab, update if active_tab == "update" else overview)()


def dataset_progress_response(status: dict[str, Any]) -> Any:
    import asyncio
    import json

    from starlette.responses import StreamingResponse

    async def events() -> Any:
        while True:
            yield f"data: {json.dumps(status)}\n\n"
            if status["completed"] or status["error"]:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(events(), media_type="text/event-stream")
