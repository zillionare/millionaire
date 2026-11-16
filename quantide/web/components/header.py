"""Header 组件。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from fasthtml.common import A, Button, Div, Header, Nav, Script, Span
from monsterui.all import UkIcon

from quantide.web.design_system import BRAND


def _normalize_nav_item(
    item: tuple[str, str] | Mapping[str, Any],
) -> Mapping[str, Any]:
    """规范化导航项。"""
    if isinstance(item, dict):
        return item
    title, url = item
    return {"title": title, "url": url}


def _nav_link(
    index: int,
    raw_item: tuple[str, str] | Mapping[str, Any],
    active_title: str,
) -> Any:
    """Render one header item, including its optional dropdown."""
    item = _normalize_nav_item(raw_item)
    title = str(item.get("title", ""))
    url = str(item.get("url", "#"))
    disabled = bool(item.get("disabled", False)) or bool(item.get("requires_gateway", False))
    children = item.get("children") or []
    is_active = title == active_title
    active_cls = "text-gray-900 border-b-2 border-primary"
    inactive_cls = "text-gray-500 hover:text-gray-900 border-b-2 border-transparent"
    attrs: dict[str, Any] = {}
    display_text = str(item.get("label_override") or title)

    if item.get("boost"):
        attrs.update(
            {
                "hx_get": url,
                "hx_target": "#layout-main-content",
                "hx_swap": "outerHTML show:none",
                "hx_select": "#layout-main-content",
                "hx_push_url": "true",
            }
        )

    if children:
        menu_id = f"header-menu-{index}"
        return Div(
            Button(
                Span(display_text, cls="inline-flex items-center text-sm font-medium"),
                UkIcon("chevron-down", cls="w-4 h-4 ml-1"),
                type="button",
                id=f"{menu_id}-button",
                data_header_menu_button="true",
                aria_haspopup="menu",
                aria_expanded="false",
                onclick=f"toggleHeaderMenu(event, '{menu_id}')",
                cls=(
                    "inline-flex h-16 items-center border-0 bg-transparent px-4 "
                    "text-sm font-medium shadow-none m-0 "
                    + (active_cls if is_active else inactive_cls)
                ),
            ),
            Div(
                *[
                    A(
                        str(c.get("title", "")),
                        href=str(c.get("url", "#")),
                        cls="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50",
                    )
                    for c in children
                ],
                id=menu_id,
                data_header_menu="true",
                cls=(
                    "absolute left-0 top-full z-50 mt-1 hidden min-w-[160px] "
                    "rounded-lg border border-gray-100 bg-white shadow-lg"
                ),
            ),
            data_header_menu_wrap="true",
            cls="relative inline-flex",
        )

    if disabled:
        attrs = {
            "aria_disabled": "true",
            "title": str(item.get("title_attr") or "请先配置交易网关"),
        }
    return A(
        display_text,
        href=url,
        cls=(
            "inline-flex h-16 items-center px-4 text-sm font-medium transition "
            + (active_cls if is_active else inactive_cls)
            + (" opacity-60 cursor-not-allowed" if disabled else "")
        ),
        **attrs,
    )


def _build_nav_links(
    nav_items: Sequence[tuple[str, str] | Mapping[str, Any]], active_title: str
) -> list[Any]:
    """Build header links in the configured order."""
    return [_nav_link(index, item, active_title) for index, item in enumerate(nav_items or [])]


def _build_alert_button(
    unread_count: int,
    risk_summary: dict[str, int],
    recent_risk_events: list[dict[str, Any]],
    runtime_summary: dict[str, int],
) -> Div:
    """构建告警中心按钮与弹层。"""
    return Div(
        Button(
            UkIcon("bell", cls="w-[18px] h-[18px]"),
            _build_unread_badge(unread_count),
            cls=(
                "relative inline-flex h-10 w-10 items-center justify-center rounded-full "
                "bg-gray-100 text-gray-600 transition hover:bg-gray-200 "
                "hover:text-gray-900"
            ),
            type="button",
            id="alert-center-button",
            onclick="toggleAlertCenter(event)",
            aria_label="告警中心",
            aria_haspopup="dialog",
            aria_expanded="false",
        ),
        _build_alert_popover(risk_summary, recent_risk_events, runtime_summary),
        id="alert-center",
        cls="relative",
    )


def _build_unread_badge(unread_count: int) -> Span | None:
    """构建未读告警徽标。"""
    if unread_count <= 0:
        return None
    return Span(
        "99+" if unread_count > 99 else str(unread_count),
        cls=(
            "absolute top-1 right-1 inline-flex min-w-[14px] h-[14px] items-center "
            "justify-center rounded-full bg-[#10b981] px-1 text-[9px] font-bold "
            "text-white shadow-sm border border-white"
        ),
    )


def _build_recent_alert_items(recent_risk_events: list[dict[str, Any]]) -> list[Any]:
    """构建最近告警列表。"""
    if not recent_risk_events:
        return [
            Div(
                "当前没有待处理风险事件",
                cls="rounded-lg bg-gray-50 px-3 py-3 text-sm text-gray-500",
            )
        ]

    items: list[Any] = []
    for event in recent_risk_events:
        title = str(event.get("title") or "风险事件")
        message = str(event.get("message") or "")
        created_at = str(event.get("created_at") or "-")
        items.append(
            Div(
                Div(title, cls="text-sm font-medium text-gray-900"),
                Div(message, cls="mt-1 line-clamp-2 text-xs text-gray-500"),
                Div(created_at, cls="mt-2 text-[11px] text-gray-400"),
                cls="rounded-lg border border-gray-100 px-3 py-3",
            )
        )
    return items


def _summary_chip(label: str, value: int, cls: str) -> Div:
    """构建摘要标签。"""
    return Div(
        Span(label, cls="text-[11px] text-gray-500"),
        Span(str(value), cls=f"text-sm font-semibold {cls}"),
        cls="flex flex-col rounded-lg bg-gray-50 px-3 py-2",
    )


def _build_alert_popover(
    risk_summary: dict[str, int],
    recent_risk_events: list[dict[str, Any]],
    runtime_summary: dict[str, int],
) -> Div:
    """构建告警中心弹层。"""
    return Div(
        Div(
            Div(
                Span("告警中心", cls="text-sm font-semibold text-gray-900"),
                Span("风险事件与运行时概览", cls="text-xs text-gray-500"),
                cls="flex flex-col",
            ),
            Div(
                _summary_chip("活动告警", risk_summary.get("open_events", 0), "text-[#e41815]"),
                _summary_chip(
                    "账户风控", risk_summary.get("blocked_accounts", 0), "text-[#e41815]"
                ),
                _summary_chip(
                    "策略风控", risk_summary.get("blocked_strategies", 0), "text-gray-700"
                ),
                cls="grid grid-cols-3 gap-2",
            ),
            Div(
                Span(
                    "最近风险事件", cls="text-xs font-medium uppercase tracking-wide text-gray-500"
                ),
                Div(*_build_recent_alert_items(recent_risk_events), cls="mt-2 space-y-2"),
            ),
            Div(
                Span("运行时概览", cls="text-xs font-medium uppercase tracking-wide text-gray-500"),
                Div(
                    _summary_chip("总数", runtime_summary.get("total", 0), "text-gray-700"),
                    _summary_chip("运行中", runtime_summary.get("running", 0), "text-green-700"),
                    _summary_chip("封锁", runtime_summary.get("blocked", 0), "text-gray-700"),
                    _summary_chip("失败", runtime_summary.get("failed", 0), "text-[#e41815]"),
                    cls="mt-2 grid grid-cols-4 gap-2",
                ),
            ),
            Div(
                A(
                    "查看风险事件中心",
                    href="/system/risk-events/",
                    cls=(
                        "block rounded-lg border border-gray-200 px-3 py-2 text-center "
                        "text-sm font-medium text-gray-700 hover:bg-gray-50"
                    ),
                ),
                A(
                    "查看运行时监控",
                    href="/system/runtime-monitor/",
                    cls=(
                        "block rounded-lg bg-[#e41815] px-3 py-2 text-center text-sm "
                        "font-medium text-white hover:bg-[#c91412]"
                    ),
                ),
                cls="grid grid-cols-2 gap-2 pt-1",
            ),
            cls="space-y-4",
        ),
        id="alert-center-popover",
        cls=(
            "quantide-surface absolute right-0 top-[calc(100%+12px)] z-50 hidden "
            "w-[360px] rounded-2xl border border-gray-100 bg-white p-4 shadow-lg"
        ),
        role="dialog",
        aria_label="告警中心",
    )


def _menu_action(label: str, href: str, icon_name: str, attrs: dict[str, Any] | None = None) -> A:
    """构建下拉菜单项。"""
    attrs = attrs or {}
    return A(
        Div(
            UkIcon(icon_name, size=16, cls="text-primary"),
            Span(label, cls="text-sm font-medium"),
            cls="flex items-center gap-3",
        ),
        href=href,
        cls=(
            "flex items-center rounded-xl px-3 py-3 text-[#2c3030] transition "
            "hover:bg-[#fff3f2] hover:text-primary"
        ),
        **attrs,
    )


def _build_user_menu(
    user: str | None, accounts: list[dict[str, Any]], active_account: dict[str, Any] | None
) -> Div:
    """构建用户菜单。"""
    initial = (user or "U")[:1]
    return Div(
        Div(
            Button(
                Div(
                    Div(
                        Span(
                            initial,
                            cls=(
                                "flex h-9 w-9 items-center justify-center rounded-full "
                                "bg-gray-200 text-sm font-semibold uppercase "
                                "text-gray-600 shadow-md"
                            ),
                        ),
                        cls="relative",
                    ),
                    UkIcon("chevron-down", cls="w-[14px] h-[14px]"),
                    cls="flex items-center gap-2",
                ),
                cls=(
                    "flex items-center rounded-full p-1 text-left transition "
                    "hover:bg-gray-100 focus:outline-none bg-transparent border-none "
                    "outline-none"
                ),
                onclick="toggleUserMenu(event)",
                type="button",
                id="user-menu-button",
                aria_haspopup="menu",
                aria_expanded="false",
            ),
            Div(
                Div(
                    cls=(
                        "absolute -top-2 left-1/2 -translate-x-1/2 w-4 h-4 bg-white "
                        "border-l border-t border-gray-100 rotate-45 z-50"
                    )
                ),
                Div(
                    _menu_action(
                        "重设密码",
                        "#",
                        "settings",
                        {"onclick": "showGlobalResetPasswordModal(event)"},
                    ),
                    _menu_action("退出登录", "/auth/logout", "log-out"),
                    cls="p-2 relative z-10 bg-white rounded-xl",
                ),
                id="user-dropdown",
                cls=(
                    "quantide-surface absolute top-[calc(100%+12px)] left-1/2 "
                    "-translate-x-1/2 z-50 hidden w-32 overflow-hidden rounded-xl "
                    "bg-white shadow-lg border border-gray-100"
                ),
                role="menu",
            ),
            id="user-menu",
            cls="relative",
        ),
    )


def header_component(
    logo: str,
    brand: str,
    nav_items: list[tuple[str, str]] | list[dict[str, Any]],
    user: str | None = None,
    accounts: list[dict[str, Any]] | None = None,
    active_account: dict[str, Any] | None = None,
    active_title: str = "",
    unread_count: int = 0,
    risk_summary: dict[str, int] | None = None,
    recent_risk_events: list[dict[str, Any]] | None = None,
    runtime_summary: dict[str, int] | None = None,
    hx_swap_oob: bool = False,
) -> Any:
    """构建主导航栏。

    黑白灰 + 品牌红强调（品牌字、当前导航、告警）。
    """
    accounts = accounts or []
    risk_summary = risk_summary or {
        "blocked_accounts": 0,
        "blocked_strategies": 0,
        "open_events": 0,
        "event_count": 0,
    }
    recent_risk_events = recent_risk_events or []
    runtime_summary = runtime_summary or {
        "total": 0,
        "running": 0,
        "blocked": 0,
        "failed": 0,
        "idle": 0,
    }
    return Header(
        Div(
            Div(
                Div(
                    cls=(
                        "h-10 w-10 rounded-xl bg-gray-50 bg-center bg-contain "
                        "bg-no-repeat shadow-sm"
                    ),
                    style=f"background-image: url('{logo}')",
                    role="img",
                    aria_label=brand,
                ),
                Span(brand, cls=f"text-lg font-semibold tracking-[0.08em] text-[{BRAND}]"),
                cls="flex items-center gap-3",
            ),
            Div(cls="flex-1"),
            Div(
                Nav(
                    *_build_nav_links(nav_items, active_title),
                    cls="hidden items-center self-stretch lg:flex",
                ),
                _build_alert_button(
                    unread_count, risk_summary, recent_risk_events, runtime_summary
                ),
                _build_user_menu(user, accounts, active_account),
                cls="flex items-center gap-3",
            ),
            cls="mx-auto flex h-full max-w-[1280px] items-center gap-4 px-5",
        ),
        Div(
            Div(
                Div(
                    UkIcon("alert-triangle", cls="w-8 h-8 text-gray-500"), cls="flex justify-center"
                ),
                Span(
                    "请先配置交易网关",
                    cls="mt-4 block text-lg font-semibold text-gray-900 text-center",
                ),
                Span(
                    "当前尚未启用 gateway，因此还不能进入实盘或仿真交易。请先完成交易网关配置。",
                    cls="mt-2 block text-sm leading-6 text-gray-600 text-center",
                ),
                Div(
                    A(
                        "前往交易网关",
                        href="/system/gateway/",
                        cls=(
                            "inline-flex items-center justify-center rounded-lg "
                            "bg-[#e41815] px-4 py-2 text-sm font-medium text-white "
                            "hover:bg-[#c91412]"
                        ),
                    ),
                    Button(
                        "稍后配置",
                        type="button",
                        cls=(
                            "inline-flex items-center justify-center rounded-lg border "
                            "border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 "
                            "hover:bg-gray-50"
                        ),
                        onclick="closeGatewayRequiredModal()",
                    ),
                    cls="mt-6 flex justify-center gap-3",
                ),
                cls="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl",
            ),
            id="gateway-required-modal",
            cls="fixed inset-0 z-[60] hidden items-center justify-center bg-black/40 px-4",
            onclick="if(event.target===this){closeGatewayRequiredModal()}",
        ),
        Div(id="global-reset-password-modal-container"),
        _header_script(),
        id="layout-header",
        **({"hx_swap_oob": "true"} if hx_swap_oob else {}),
        cls=(
            "sticky top-0 z-50 h-16 border-b border-black/5 bg-white "
            "shadow-[0_4px_15px_rgba(0,0,0,0.1)]"
        ),
    )


def _header_script() -> Script:
    """构建 header 交互脚本。"""
    return Script(
        "function setUserMenu(open){const button=document.getElementById('user-menu-b"
        "utton');const dropdown=document.getElementById('user-dropdown');if(!button||"
        "!dropdown){return;}if(open){dropdown.classList.remove('hidden');button.setAt"
        "tribute('aria-expanded','true');}else{dropdown.classList.add('hidden');butto"
        "n.setAttribute('aria-expanded','false');}}function "
        "toggleUserMenu(event){if(event){event.stopPropagation();}const "
        "dropdown=document.getElementById('user-dropdown');if(!dropdown){return;}setA"
        "lertCenter(false);setUserMenu(dropdown.classList.contains('hidden'));}functi"
        "on setAlertCenter(open){const button=document.getElementById('alert-center-b"
        "utton');const popover=document.getElementById('alert-center-popover');if(!bu"
        "tton||!popover){return;}if(open){popover.classList.remove('hidden');button.s"
        "etAttribute('aria-expanded','true');}else{popover.classList.add('hidden');bu"
        "tton.setAttribute('aria-expanded','false');}}function "
        "toggleAlertCenter(event){if(event){event.preventDefault();event.stopPropagat"
        "ion();}const popover=document.getElementById('alert-center-popover');if(!pop"
        "over){return;}setUserMenu(false);setAlertCenter(popover.classList.contains('"
        "hidden'));}function closeHeaderMenus(){document.querySelectorAll('[data-head"
        "er-menu]').forEach(function(menu){menu.classList.add('hidden');});document.q"
        "uerySelectorAll('[data-header-menu-button]').forEach(function(button){button"
        ".setAttribute('aria-expanded','false');});}function "
        "toggleHeaderMenu(event,id){if(event){event.preventDefault();event.stopPropag"
        "ation();}const menu=document.getElementById(id);if(!menu){return;}const "
        "opening=menu.classList.contains('hidden');closeHeaderMenus();if(opening){men"
        "u.classList.remove('hidden');const button=document.getElementById(id+'-butto"
        "n');if(button){button.setAttribute('aria-expanded','true');}}}document.addEv"
        "entListener('click',function(event){const "
        "menu=document.getElementById('user-menu');if(menu&&!menu.contains(event.targ"
        "et)){setUserMenu(false);}const alertCenter=document.getElementById('alert-ce"
        "nter');if(alertCenter&&!alertCenter.contains(event.target)){setAlertCenter(f"
        "alse);}document.querySelectorAll('[data-header-menu-wrap]').forEach(function"
        "(wrap){if(!wrap.contains(event.target)){const "
        "menu=wrap.querySelector('[data-header-menu]');const "
        "button=wrap.querySelector('[data-header-menu-button]');if(menu){menu.classLi"
        "st.add('hidden');}if(button){button.setAttribute('aria-expanded','false');}}"
        "});});document.addEventListener('keydown',function(event){if(event.key==='Es"
        "cape'){setUserMenu(false);setAlertCenter(false);closeHeaderMenus();}});funct"
        "ion showGlobalResetPasswordModal(event){if(event){event.preventDefault(); "
        "event.stopPropagation();} setUserMenu(false); htmx.ajax('GET', "
        "'/auth/modal/reset-password', {target: '#global-reset-password-modal-contain"
        "er'});}function showGatewayRequiredModal(event){if(event){event.preventDefau"
        "lt(); event.stopPropagation();} const modal=document.getElementById('gateway"
        "-required-modal'); if(!modal){return;} modal.classList.remove('hidden'); "
        "modal.classList.add('flex');}function closeGatewayRequiredModal(){const "
        "modal=document.getElementById('gateway-required-modal');if(!modal){return;} "
        "modal.classList.remove('flex'); modal.classList.add('hidden');}"
    )
