"""统一 UI 组件（基于设计系统类）。

页面只需要使用这些组件，不需要直接写 Tailwind/uk-* 类。
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import (
    H1,
    A,
    Button,
    Div,
    Input,
    Label,
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


def page_header(
    title: str,
    subtitle: str | None = None,
    *,
    actions: Any | None = None,
) -> Div:
    """页面头部：标题 + 副标题 + 操作区。"""
    left = Div(
        H1(title, cls="page__title"),
        P(subtitle, cls="page__subtitle") if subtitle else None,
    )
    if actions is None:
        return Div(left, cls="page__header")
    return Div(left, Div(actions, cls="flex items-center gap-2"), cls="page__header")


def card(*children: Any, padded: bool = True, cls: str = "", **attrs: Any) -> Div:
    """统一卡片容器。"""
    cls_list = ["card"]
    if padded:
        cls_list.append("card--padded")
    if cls:
        cls_list.append(cls)
    return Div(*children, cls=" ".join(cls_list), **attrs)


def btn(
    label: str | Any,
    *,
    variant: str = "secondary",
    size: str = "md",
    disabled: bool = False,
    icon: Any | None = None,
    **attrs: Any,
) -> Button:
    """统一按钮。

    variant: secondary / primary / ghost / danger / success / buy / sell
    size: md / sm
    """
    classes = ["q-btn"]
    if size == "sm":
        classes.append("q-btn--sm")
    if variant != "secondary":
        classes.append(f"q-btn--{variant}")
    if disabled:
        classes.append("q-btn:disabled")
    children = [label]
    if icon is not None:
        children = [icon, label]
    return Button(*children, cls=" ".join(classes), disabled=disabled, **attrs)


def icon_btn(
    icon: Any, *, label: str | None = None, variant: str = "secondary", **attrs: Any
) -> Button:
    """图标按钮。"""
    return Button(icon, cls="q-btn q-btn--icon", **attrs)


def subtle_icon_button(icon: Any, *, post_url: str, target: str, label: str) -> Button:
    """Lightweight header action icon; no button chrome or full-width layout."""
    return Button(
        icon,
        hx_post=post_url,
        hx_target=target,
        hx_swap="innerHTML",
        cls=(
            "inline-flex h-5 w-5 items-center justify-center p-0 "
            "border-0 bg-transparent text-gray-500 transition-colors "
            "hover:text-gray-900"
        ),
        title="立即更新",
        aria_label=label,
    )


def input_(
    name: str,
    *,
    label: str | None = None,
    type: str = "text",
    value: Any | None = None,
    placeholder: str = "",
    required: bool = False,
    **attrs: Any,
) -> Div:
    """表单输入框（带标签）。"""
    children = []
    if label is not None:
        children.append(Label(label, cls="q-label", **{"for": name}))
    children.append(
        Input(
            name=name,
            type=type,
            value=str(value) if value is not None else None,
            placeholder=placeholder,
            required=required,
            cls="q-input",
            **attrs,
        )
    )
    return Div(*children)


def select_(
    name: str,
    options: list[tuple[str, Any]],
    *,
    label: str | None = None,
    value: Any | None = None,
    **attrs: Any,
) -> Div:
    """表单下拉框。"""
    from fasthtml.common import Option

    children = []
    if label is not None:
        children.append(Label(label, cls="q-label", **{"for": name}))
    children.append(
        Select(
            *[Option(text, value=str(v), selected=v == value or None) for text, v in options],
            name=name,
            cls="q-input",
            **attrs,
        )
    )
    return Div(*children)


def data_table(
    headers: list[str],
    rows: list[list[Any]],
    *,
    cls: str = "",
    **attrs: Any,
) -> Table:
    """统一数据表格。"""
    return Table(
        Thead(Tr(*[Th(h) for h in headers])),
        Tbody(*[Tr(*[Td(c) for c in row]) for row in rows]),
        cls=f"q-table {cls}".strip(),
        **attrs,
    )


def badge(label: str, *, variant: str = "neutral", **attrs: Any) -> Span:
    """状态徽章。"""
    cls = "q-badge" if variant == "neutral" else f"q-badge q-badge--{variant}"
    return Span(label, cls=cls, **attrs)


def modal(
    title: str,
    body: Any,
    footer: Any,
    *,
    modal_id: str,
    width: str = "max-w-md",
) -> Div:
    """统一对话框（红色标题栏）。

    Args:
        width: 宽度类，比如 ``max-w-md`` / ``max-w-lg`` / ``max-w-2xl``。
    """
    return Div(
        Div(
            Div(
                Div(title, cls="q-modal__header"),
                Div(body, cls="q-modal__body"),
                Div(footer, cls="q-modal__footer"),
                cls=f"q-modal {width}",
            ),
            cls="q-modal-backdrop",
        ),
        id=modal_id,
    )


def breadcrumb(*items: tuple[str, str | None]) -> Div:
    """面包屑；最后一个项目如果 url 为 None 则视为当前页。"""
    nodes: list[Any] = []
    for i, (title, url) in enumerate(items):
        if i > 0:
            nodes.append(Span("›", cls="q-breadcrumb__sep"))
        if url is None or i == len(items) - 1:
            nodes.append(Span(title, cls="q-breadcrumb__current"))
        else:
            nodes.append(A(title, href=url))
    return Div(*nodes, cls="q-breadcrumb")


def tabs(
    items: list[tuple[str, Any]],
    *,
    active: Any | None = None,
    hx_get: str | None = None,
    hx_target: str | None = None,
) -> Div:
    """页签。

    items: [(标题, key_or_url), ...]。active 传入当前 key。
    若提供 hx_get 且 hx_target，则使用 HTMX 切换；否则只展示。
    """
    children = []
    for title, key in items:
        cls = "q-tab q-tab--active" if key == active else "q-tab"
        attrs: dict[str, Any] = {"cls": cls}
        if hx_get and hx_target:
            attrs.update(
                {
                    "hx_get": hx_get,
                    "hx_target": hx_target,
                    "hx_vals": f'{{"tab": "{key}"}}',
                }
            )
        children.append(A(title, **attrs) if not hx_get else A(title, href="#", **attrs))
    return Div(*children, cls="q-tabs")


__all__ = [
    "badge",
    "btn",
    "card",
    "data_table",
    "icon_btn",
    "subtle_icon_button",
    "input_",
    "modal",
    "page_header",
    "select_",
    "tabs",
    "breadcrumb",
]
