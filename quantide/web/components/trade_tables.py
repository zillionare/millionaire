"""Position and order tables shared by trading views."""

from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    A,
    Div,
    Thead,
    Tr,
)
from monsterui.all import *
from monsterui.all import (
    H3,
    Button,
    Table,
    Tbody,
    Td,
    Th,
    UkIcon,
)

from quantide.core.enums import OrderSide, OrderStatus
from quantide.data.models import Order, Position
from quantide.web.components.asset_label import resolve_asset_name


def _position_row(p: Any) -> Any:
    """Render one row with its display values and available actions."""
    pnl_pct = (p.profit / (p.mv - p.profit) * 100) if (p.mv - p.profit) != 0 else 0
    current_price = p.mv / p.shares if p.shares > 0 else 0
    color_cls = "text-red-600" if p.profit > 0 else ("text-green-600" if p.profit < 0 else "")
    avail_lots = int(p.avail / 100) if p.avail >= 100 and p.avail % 100 == 0 else ""
    return Tr(
        Td(p.asset),
        Td(resolve_asset_name(p.asset)),
        Td(f"{p.shares:,}"),
        Td(f"{p.avail:,}"),
        Td(f"{p.mv:,.2f}"),
        Td(f"{current_price:,.2f}"),
        Td(f"{p.price:,.2f}"),
        Td(f"{p.profit:,.2f}", cls=color_cls),
        Td(f"{pnl_pct:.2f}%", cls=color_cls),
        Td(
            Button(
                "卖出",
                type="button",
                cls=(
                    "position-sell-btn uk-button uk-button-small "
                    "bg-green-600 text-white hover:bg-green-700"
                ),
            )
        ),
        cls="trade-position-row cursor-pointer",
        data_asset=p.asset,
        data_display=f"{resolve_asset_name(p.asset)}（{p.asset}）",
        data_price=f"{current_price:.2f}" if current_price > 0 else "",
        data_avail_lots=str(avail_lots),
    )


def PositionTable(positions: list[Position], hx_swap_oob: bool = False) -> Any:
    """持仓明细表格"""
    headers = [
        "证券代码",
        "证券名称",
        "当前持股",
        "可用股数",
        "市值",
        "最新价",
        "成本价",
        "盈亏",
        "盈亏比例",
        "操作",
    ]

    rows: list[Any] = []
    if positions:
        rows.extend(_position_row(p) for p in positions)
    else:
        rows.append(Tr(Td("暂无持仓", colspan=len(headers), cls="text-center py-10 text-gray-500")))

    return Div(
        Div(
            H3("持仓明细", cls="text-lg font-semibold text-gray-900 dark:text-white"),
            Button(
                UkIcon("refresh-cw", size=16),
                " 刷新",
                cls="uk-button uk-button-primary uk-button-small",
                style="background-color: #d32f2f;",
                hx_get="/trade/positions",
                hx_target="#position-table",
                hx_swap="outerHTML",
            ),
            cls="flex items-center justify-between mb-4 px-6 pt-4",
        ),
        Table(
            Thead(Tr(*[Th(h, cls="text-xs font-bold bg-gray-50") for h in headers])),
            Tbody(*rows),
            cls="uk-table uk-table-divider uk-table-small uk-table-hover",
        ),
        id="position-table",
        cls="bg-white dark:bg-gray-800 rounded-lg shadow mb-6 overflow-hidden",
        hx_get="/trade/positions",
        hx_trigger="every 3s [document.visibilityState === 'visible']",
        hx_swap="outerHTML",
        **({"hx_swap_oob": "true"} if hx_swap_oob else {}),
    )


def _today_order_row(o: Any) -> Any:
    """Render one row with its display values and available actions."""
    if o.side == OrderSide.BUY:
        side_color = "text-red-600"
        side_text = "买入"
    elif o.side == OrderSide.SELL:
        side_color = "text-green-600"
        side_text = "卖出"
    else:
        side_color = "text-gray-500"
        side_text = "未知"

    # 与 ``gateway_broker._coerce_order_status`` 一一对应；只有真实存在的
    # ``OrderStatus`` 成员才会命中，否则一律显示 "未知"。
    status_map = {
        OrderStatus.UNREPORTED: ("未报", "text-gray-500"),
        OrderStatus.WAIT_REPORTING: ("待报", "text-gray-600"),
        OrderStatus.REPORTED: ("已报", "text-gray-600"),
        OrderStatus.REPORTED_CANCEL: ("已报待撤", "text-gray-500"),
        OrderStatus.PARTSUCC_CANCEL: ("部成待撤", "text-gray-500"),
        OrderStatus.PART_CANCEL: ("部成已撤", "text-gray-500"),
        OrderStatus.CANCELED: ("已撤", "text-gray-500"),
        OrderStatus.PART_SUCC: ("部分成交", "text-[#e41815]"),
        OrderStatus.SUCCEEDED: ("已成交", "text-green-600"),
        OrderStatus.JUNK: ("已拒绝", "text-red-600"),
    }
    status_text, status_color = status_map.get(o.status, ("未知", "text-gray-500"))
    return Tr(
        Td(o.tm.strftime("%H:%M:%S") if hasattr(o, "tm") else "--"),
        Td(o.asset),
        Td(resolve_asset_name(o.asset)),
        Td(side_text, cls=side_color),
        Td(f"{o.price:,.2f}"),
        Td(f"{o.shares:,}"),
        Td(f"{o.filled:,}"),
        Td(status_text, cls=status_color),
        Td(
            Button(
                "撤单",
                cls="uk-button uk-button-small uk-button-default",
                hx_post=f"/trade/cancel/{o.qtoid}",
                hx_target="#trade-toast-slot",
                hx_confirm="确定要撤单吗？",
            )
            if o.status
            in {
                OrderStatus.UNREPORTED,
                OrderStatus.WAIT_REPORTING,
                OrderStatus.REPORTED,
                OrderStatus.PART_SUCC,
            }
            else ""
        ),
    )


def TodayOrdersTable(orders: list[Order], hx_swap_oob: bool = False) -> Any:
    """当日委托表格"""
    headers = ["时间", "代码", "名称", "方向", "委托价", "委托量", "成交量", "状态", "操作"]

    rows: list[Any] = []
    if orders:
        rows.extend(_today_order_row(o) for o in orders)
    else:
        rows.append(
            Tr(Td("暂无当日委托", colspan=len(headers), cls="text-center py-10 text-gray-500"))
        )

    return Div(
        Div(
            H3("当日委托", cls="text-lg font-semibold text-gray-900 dark:text-white"),
            Button(
                UkIcon("refresh-cw", size=16),
                " 刷新",
                cls="uk-button uk-button-primary uk-button-small",
                style="background-color: #d32f2f;",
                hx_get="/trade/orders",
                hx_target="#today-orders",
                hx_swap="outerHTML",
            ),
            cls="flex items-center justify-between mb-4 px-6 pt-4",
        ),
        Table(
            Thead(Tr(*[Th(h, cls="text-xs font-bold bg-gray-50") for h in headers])),
            Tbody(*rows),
            cls="uk-table uk-table-divider uk-table-small uk-table-hover",
        ),
        id="today-orders",
        cls="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden",
        **({"hx_swap_oob": "true"} if hx_swap_oob else {}),
    )


POSITIONS_TABS: dict[str, str] = {
    "positions": "持仓",
    "orders": "委托",
}


DEFAULT_POSITIONS_TAB = "positions"


POSITIONS_TABS_PANEL_ID = "positions-orders-tab-panel"


def _normalize_positions_tab(value: Any) -> str:
    """规范化持仓/委托 tab 参数.

    Args:
        value: 任意传入值（request.query_params、字典、字符串、None 均可）。

    Returns:
        合法的 tab key（``positions`` / ``orders``），非法值回退到 ``DEFAULT_POSITIONS_TAB``。
    """
    if isinstance(value, str):
        key = value.strip().lower()
    else:
        key = str(value or "").strip().lower()
    return key if key in POSITIONS_TABS else DEFAULT_POSITIONS_TAB


def PositionsOrdersTabs(positions: list[Position], orders: list[Order], active_tab: str) -> Any:
    """持仓/委托 tab 容器 (Issue #30, #41).

    服务端只渲染当前 tab 对应内容；tab 链接走 HTMX 局部刷新（参
    ``09-backtest-report-tabs-and-logs.md``）：点击 tab 只替换
    ``#positions-orders-tab-panel`` DOM 片段，URL 通过
    ``hx-push-url`` 同步更新，页面其他部分（资产条、闪电单、表单输入）保持不变。

    Args:
        positions: 持仓数据。
        orders: 当日委托数据。
        active_tab: 当前激活的 tab key（非法值会回退到默认）。

    Returns:
        包含 tab 导航条 + 当前 tab 内容的 ``Div``，整体带 id 供 HTMX swap。
    """
    active_tab = _normalize_positions_tab(active_tab)

    nav_items = [
        A(
            title,
            href=f"/trade?tab={tab_key}",
            cls=(
                "inline-flex items-center px-4 py-2 text-sm font-medium border-b-2 "
                + (
                    "border-red-600 text-red-600"
                    if tab_key == active_tab
                    else (
                        "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                    )
                )
            ),
            aria_current=("page" if tab_key == active_tab else None),
            data_tab=tab_key,
            hx_get=f"/trade?tab={tab_key}",
            hx_target=f"#{POSITIONS_TABS_PANEL_ID}",
            hx_swap="outerHTML",
            hx_push_url="true",
            hx_select=f"#{POSITIONS_TABS_PANEL_ID}",
        )
        for tab_key, title in POSITIONS_TABS.items()
    ]

    panels = {
        "positions": PositionTable(positions),
        "orders": TodayOrdersTable(orders),
    }
    active_panel = panels[active_tab]

    return Div(
        Div(
            *nav_items,
            role="tablist",
            cls="flex border-b border-gray-200 dark:border-gray-700 mb-4",
        ),
        Div(active_panel, role="tabpanel", data_active_tab=active_tab),
        id=POSITIONS_TABS_PANEL_ID,
        cls="mb-6",
    )
