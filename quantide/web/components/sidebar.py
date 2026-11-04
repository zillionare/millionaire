"""Sidebar 组件。"""

from fasthtml.common import *
from fasthtml.common import (
    Aside,
    Nav,
)
from fasthtml.svg import Path as SvgPath
from monsterui.all import *


def sidebar_component(
    menu_items: list[dict] | None = None,
    *,
    enable_fragment_navigation: bool = False,
    hx_swap_oob: bool = False,
):
    """渲染侧边栏一级菜单。

    Args:
        menu_items: 菜单列表。
        enable_fragment_navigation: 是否启用共享布局 fragment 导航。
        hx_swap_oob: 是否作为 OOB 片段返回。
    """
    items = [_sidebar_item(item) for item in menu_items or []]

    nav_attrs: dict[str, str] = {}
    if enable_fragment_navigation:
        nav_attrs = {
            "hx_boost": "true",
            "hx_target": "#layout-main-content",
            "hx_swap": "outerHTML show:none",
            "hx_push_url": "true",
        }

    aside_attrs: dict[str, str] = {
        "id": "layout-sidebar",
        "cls": "w-64 shrink-0 bg-white min-h-screen border-r border-gray-200",
    }
    if hx_swap_oob:
        aside_attrs["hx_swap_oob"] = "true"

    return Aside(
        Nav(*items, cls="p-4 space-y-1", **nav_attrs),
        **aside_attrs,
    )


_BASE_TEXT = "text-gray-600"
_HOVER = "hover:bg-gray-50"
_ACTIVE = "text-[#e41815] font-medium"


def _menu_icon(item, default, cls):
    path = item.get("icon_path")
    if path:
        return Svg(
            SvgPath(
                d=path,
                stroke="currentColor",
                fill="none",
                stroke_width="2",
                stroke_linecap="round",
                stroke_linejoin="round",
            ),
            cls=cls,
        )
    return UkIcon(item.get("icon", default), cls=cls)


def _menu_text_class(active):
    return f"bg-gray-50 {_ACTIVE}" if active else f"{_BASE_TEXT} {_HOVER}"


def _child_item(child):
    return A(
        Div(
            _menu_icon(child, "file", "w-4 h-4 mr-2"),
            Span(child.get("title", "")),
            cls="flex items-center gap-2",
        ),
        href=child.get("url", "#"),
        cls="block px-3 py-2 rounded-lg text-sm transition-colors "
        + _menu_text_class(child.get("active", False)),
    )


def _sidebar_item(item):
    children = item.get("children", [])
    active = item.get("active", False)
    icon = _menu_icon(item, "folder" if children else "file", "w-5 h-5")
    label = Div(icon, Span(item.get("title", "")), cls="flex items-center gap-3")
    if not children:
        return A(
            label,
            href=item.get("url", "#"),
            cls="w-full flex items-center px-3 py-2 rounded-lg transition-colors "
            + _menu_text_class(active),
        )
    child_active = any(child.get("active", False) for child in children)
    return Details(
        Summary(
            label,
            UkIcon(
                "chevron-down",
                cls="w-4 h-4 transition-transform duration-200 group-open:-rotate-180",
            ),
            cls=(
                "flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer "
                "list-none [&::-webkit-details-marker]:hidden [&::marker]:hidden "
                "transition-colors "
                + (_ACTIVE if active and not child_active else _BASE_TEXT)
                + " "
                + _HOVER
            ),
        ),
        Div(*[_child_item(child) for child in children], cls="pl-9 pr-3 py-1 space-y-1"),
        cls="group m-0",
        open=active or child_active,
    )
