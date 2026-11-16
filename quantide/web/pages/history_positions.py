"""历史持仓页面"""

from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    Div,
    P,
    Thead,
    Tr,
    to_xml,
)
from monsterui.all import *
from monsterui.all import (
    H1,
    Form,
    Table,
    Tbody,
    Td,
    Th,
)
from starlette.requests import Request
from starlette.responses import HTMLResponse

from quantide.core.enums import BrokerKind
from quantide.data.sqlite import db
from quantide.web.components.history_filters import (
    DateRangePicker as DateRangePicker,
)
from quantide.web.components.history_filters import (
    UnselectedHistory,
)
from quantide.web.components.history_filters import (
    _get_active_account as _get_active_account,
)
from quantide.web.layouts.main import MainLayout
from quantide.web.pages.history_common import (
    display_name,
    history_date_range,
    history_rows,
)
from quantide.web.semantic_styles import profit_text


def _get_registry(req: Request) -> Any:
    return req.scope.get("registry")


def PositionTable(positions: list[dict[str, Any]]) -> Any:
    """持仓表格"""
    if not positions:
        return Div(
            P("暂无持仓数据", cls="text-gray-500 text-center py-8"),
            cls="bg-white rounded-lg shadow",
        )

    return Div(
        Table(
            Thead(
                Tr(
                    Th("日期", cls="pb-3 font-medium text-left"),
                    Th("代码", cls="pb-3 font-medium text-left"),
                    Th("名称", cls="pb-3 font-medium text-left"),
                    Th("持仓数量", cls="pb-3 font-medium text-right"),
                    Th("成本价", cls="pb-3 font-medium text-right"),
                    Th("当前价", cls="pb-3 font-medium text-right"),
                    Th("市值", cls="pb-3 font-medium text-right"),
                    Th("盈亏", cls="pb-3 font-medium text-right"),
                    Th("盈亏率", cls="pb-3 font-medium text-right"),
                ),
                cls="text-sm text-gray-600 border-b",
            ),
            Tbody(
                *[
                    Tr(
                        Td(pos.get("dt", ""), cls="py-3 text-sm"),
                        Td(pos.get("asset", ""), cls="py-3 text-sm font-medium"),
                        Td(pos.get("name", ""), cls="py-3 text-sm text-gray-500"),
                        Td(f"{pos.get('shares', 0):,}", cls="py-3 text-sm text-right"),
                        Td(f"{pos.get('cost_price', 0):.2f}", cls="py-3 text-sm text-right"),
                        Td(f"{pos.get('current_price', 0):.2f}", cls="py-3 text-sm text-right"),
                        Td(
                            f"{pos.get('market_value', 0) / 10000:.2f}万",
                            cls="py-3 text-sm text-right",
                        ),
                        Td(
                            f"{pos.get('pnl', 0) / 10000:.2f}万",
                            cls=(f"py-3 text-sm text-right {profit_text(pos.get('pnl', 0))}"),
                        ),
                        Td(
                            f"{pos.get('pnl_pct', 0) * 100:.2f}%",
                            cls=(f"py-3 text-sm text-right {profit_text(pos.get('pnl_pct', 0))}"),
                        ),
                    )
                    for pos in positions
                ],
                cls="text-sm",
            ),
            cls="w-full",
        ),
        cls="bg-white rounded-lg shadow overflow-hidden",
    )


def HistoryPositionsPage(
    positions: list[dict[str, Any]], start_date: str, end_date: str, account_name: str = ""
) -> Any:
    """历史持仓页面内容"""
    return Div(
        Div(
            H1("历史持仓", cls="text-2xl font-bold text-gray-900"),
            P(
                f"当前账户: {account_name}" if account_name else "",
                cls="text-sm text-gray-500 mt-1",
            ),
            cls="mb-6",
        ),
        Form(
            DateRangePicker(start_date, end_date),
            action="/trade/positions/history",
            method="GET",
            cls="mb-6",
        ),
        PositionTable(positions),
        cls="p-6",
    )


def history_positions_list(request: Request) -> Any:
    """历史持仓列表页面"""
    session = request.scope.get("session", {})
    layout = MainLayout(title="历史持仓", user=session.get("auth"))
    layout.header_active = "交易"
    layout.set_sidebar_active("/trade/positions/history")

    # 获取活动账户
    active = _get_active_account(request)
    if not active:
        return UnselectedHistory(layout)

    kind, account_id = active

    # 获取账户名称
    reg = _get_registry(request)
    account_name = account_id
    if reg:
        broker = reg.get(BrokerKind(kind), account_id)
        if broker and hasattr(broker, "portfolio_name"):
            account_name = broker.portfolio_name

    # 获取查询日期范围
    start_date, end_date = history_date_range(request.query_params)

    # 查询持仓数据
    positions = []
    try:
        positions = [
            _history_position_row(row)
            for row in history_rows(db.query_positions, account_id, start_date, end_date)
        ]
    except Exception as e:
        print(f"Failed to query positions: {e}")

    layout.set_main_block(
        lambda: HistoryPositionsPage(positions, start_date, end_date, account_name)
    )
    return HTMLResponse(to_xml(layout.render()))


def _history_position_row(row: Any) -> Any:
    """Build one historical cost and PnL read model."""
    shares = row.get("shares", 0)
    cost_price = row.get("price", 0)  # 成本价
    current_price = row.get("current_price", cost_price)  # 当前价
    market_value = shares * current_price
    cost_value = shares * cost_price
    pnl = market_value - cost_value
    pnl_pct = (pnl / cost_value) if cost_value else 0

    asset = str(row.get("asset", "") or "")
    return {
        "dt": row.get("dt", ""),
        "asset": asset,
        "name": display_name(asset, row.get("name", "")),
        "shares": shares,
        "cost_price": cost_price,
        "current_price": current_price,
        "market_value": market_value,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
    }
