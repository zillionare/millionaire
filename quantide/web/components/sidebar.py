"""Sidebar 组件。"""

from collections.abc import Mapping
from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    A,
    Aside,
    Details,
    Div,
    Nav,
    Span,
    Summary,
    Svg,
)
from fasthtml.common import (
    Input as PlainInput,
)
from fasthtml.svg import Path as SvgPath
from monsterui.all import *
from monsterui.all import UkIcon


def sidebar_component(
    menu_items: list[dict[str, Any]] | None = None,
    *,
    enable_fragment_navigation: bool = False,
    hx_swap_oob: bool = False,
    search_placeholder: str | None = None,
) -> Any:
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
            "hx_select": "#layout-main-content",
            "hx_push_url": "true",
        }

    aside_attrs: dict[str, str] = {
        "id": "layout-sidebar",
        "cls": "w-64 shrink-0 bg-white min-h-screen border-r border-gray-200",
    }
    if hx_swap_oob:
        aside_attrs["hx_swap_oob"] = "true"

    search = None
    if search_placeholder:
        search = PlainInput(
            type="search",
            placeholder=search_placeholder,
            aria_label=search_placeholder,
            autocomplete="off",
            cls="q-input w-full mb-3",
            oninput=(
                "var q=this.value.toLowerCase();"
                "document.querySelectorAll('#layout-sidebar [data-sidebar-entry]').forEach"
                "(function(a){var hit=!q||(a.dataset.search||'').includes(q);"
                "a.style.display=hit?'':'none';});"
                "document.querySelectorAll('#layout-sidebar details').forEach"
                "(function(d){var any=false;d.querySelectorAll('[data-sidebar-entry]').forEach"
                "(function(a){if(a.style.display!=='none')any=true;});"
                "d.style.display=any?'':'none';if(q&&any)d.open=true;});"
            ),
        )
    nav = Nav(*items, cls="p-4 space-y-1", **nav_attrs)
    return Aside(
        Div(search, nav, cls="p-3") if search else nav,
        **aside_attrs,
    )


_BASE_TEXT = "text-gray-600"
_HOVER = "hover:bg-gray-50"
_ACTIVE = "text-[#e41815] font-medium"


def _menu_icon(item: Mapping[str, Any], default: str, cls: str) -> Any:
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


def _menu_text_class(active: bool) -> Any:
    return f"bg-gray-50 {_ACTIVE}" if active else f"{_BASE_TEXT} {_HOVER}"


def _child_item(child: Mapping[str, Any]) -> Any:
    return A(
        Div(
            _menu_icon(child, "file", "w-4 h-4 shrink-0"),
            Span(child.get("title", ""), cls="min-w-0 break-words"),
            cls="flex items-center gap-2",
        ),
        href=child.get("url", "#"),
        data_sidebar_entry="true",
        data_search=str(child.get("search") or child.get("title", "")).lower(),
        cls="block px-3 py-2 rounded-lg text-xs leading-5 transition-colors "
        + _menu_text_class(child.get("active", False)),
    )


def _sidebar_item(item: Mapping[str, Any]) -> Any:
    children = item.get("children", [])
    active = item.get("active", False)
    icon = _menu_icon(item, "folder" if children else "file", "w-5 h-5")
    label = Div(icon, Span(item.get("title", "")), cls="flex items-center gap-3")
    if not children:
        return A(
            label,
            href=item.get("url", "#"),
            data_sidebar_entry="true",
            data_search=str(item.get("title", "")).lower(),
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
