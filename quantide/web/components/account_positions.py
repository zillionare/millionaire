"""Shared position quantities, valuation and profit display for account pages."""

from fasthtml.common import *
from fasthtml.common import (
    Div,
    Tr,
)
from monsterui.all import *
from monsterui.all import (
    H3,
    Button,
    Td,
    UkIcon,
)

from quantide.data.models import Position
from quantide.web.components.asset_label import resolve_asset_name
from quantide.web.components.data_tables import AccountDetailTable


def _position_row(p):
    pnl_pct = (p.profit / (p.mv - p.profit)) if (p.mv - p.profit) != 0 else 0
    current_price = p.mv / p.shares if p.shares > 0 else 0

    # 简单的颜色逻辑：红涨绿跌
    color_cls = "text-red-500" if p.profit > 0 else ("text-green-500" if p.profit < 0 else "")

    return Tr(
        Td(p.asset),
        Td(resolve_asset_name(p.asset)),
        Td(f"{p.shares:,}"),
        Td(f"{p.avail:,}"),
        Td(f"{p.shares - p.avail:,}"),
        Td(f"{p.mv:,.2f}"),
        Td(f"{current_price:,.2f}"),
        Td(f"{p.price:,.2f}"),
        Td(f"{p.profit:,.2f}", cls=color_cls),
        Td(f"{pnl_pct * 100:.2f}%", cls=color_cls),
    )


def AccountPositionInfo(positions: list[Position] | None = None, *, refresh_url: str):
    # 持仓信息表格
    headers = [
        "证券代码",
        "证券名称",
        "当前持股",
        "可用股数",
        "冻结数量",
        "市值",
        "最新价",
        "成本价",
        "盈亏",
        "盈亏比例",
    ]

    rows = []
    if positions:
        rows.extend(_position_row(position) for position in positions)
    else:
        rows.append(
            Tr(
                Td(
                    "暂无持仓",
                    colspan=len(headers),
                    cls="text-center py-10 text-gray-500",
                )
            )
        )

    return Div(
        Div(
            Div(
                UkIcon("briefcase", cls="mr-2 text-[#e41815]"),
                H3("持仓信息", cls="text-lg font-semibold mb-0"),
                cls="flex items-center",
            ),
            Button(
                UkIcon("refresh-cw", size=16),
                " 刷新",
                cls=(
                    "inline-flex items-center gap-1 rounded-lg border border-gray-200 "
                    "bg-white px-3 py-1.5 text-xs font-medium text-gray-600 "
                    "hover:border-[#e41815] hover:text-[#e41815]"
                ),
                hx_get=refresh_url,
                hx_target="#position-info",
                hx_swap="outerHTML",
            ),
            cls="flex justify-between items-center mb-4",
        ),
        AccountDetailTable(headers, rows),
        id="position-info",
        cls="bg-white p-4 rounded-xl shadow-sm border border-gray-100 h-full",
    )
