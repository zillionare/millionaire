"""历史成交页面"""

from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    H1,
    Div,
    Form,
    Tr,
    to_xml,
)
from monsterui.all import *
from monsterui.all import (
    Table,
    Tbody,
    Td,
)
from starlette.requests import Request
from starlette.responses import HTMLResponse

from quantide.data.sqlite import db
from quantide.web.components.history_filters import (
    DateRangePicker as DateRangePicker,
)
from quantide.web.components.history_filters import (
    EmptyHistory,
    HistoryTableHeader,
    UnselectedHistory,
)
from quantide.web.components.history_filters import (
    _get_active_account as _get_active_account,
)
from quantide.web.layouts.main import MainLayout
from quantide.web.pages.history_common import (
    history_date_range,
    history_rows,
    history_trade_identity,
)
from quantide.web.semantic_styles import trade_side_text


def TradesTable(trades: list[dict[str, Any]]) -> Any:
    """成交表格"""
    if not trades:
        return EmptyHistory("暂无成交数据")

    return Div(
        Table(
            HistoryTableHeader(
                ["时间", "代码", "名称", "方向", "成交价", "成交量", "成交金额", "手续费"]
            ),
            Tbody(
                *[
                    Tr(
                        Td(trade.get("tm", ""), cls="py-3 text-sm"),
                        Td(trade.get("asset", ""), cls="py-3 text-sm font-medium"),
                        Td(trade.get("name", ""), cls="py-3 text-sm text-gray-500"),
                        Td(
                            trade.get("side", ""),
                            cls=(f"py-3 text-sm {trade_side_text(trade.get('side'))}"),
                        ),
                        Td(f"{trade.get('price', 0):.2f}", cls="py-3 text-sm text-right"),
                        Td(f"{trade.get('shares', 0):,}", cls="py-3 text-sm text-right"),
                        Td(
                            f"{trade.get('amount', 0) / 10000:.2f}万", cls="py-3 text-sm text-right"
                        ),
                        Td(f"{trade.get('fee', 0):.2f}", cls="py-3 text-sm text-right"),
                    )
                    for trade in trades
                ],
                cls="text-sm",
            ),
            cls="w-full",
        ),
        cls="bg-white rounded-lg shadow overflow-hidden",
    )


def history_trades_list(request: Request) -> Any:
    """历史成交列表页面"""
    session = request.scope.get("session", {})
    layout = MainLayout(title="历史成交", user=session.get("auth"))
    layout.header_active = "交易"
    layout.set_sidebar_active("/trade/records/history")

    active = _get_active_account(request)
    if not active:
        return UnselectedHistory(layout)

    kind, account_id = active

    start_date, end_date = history_date_range(request.query_params)

    trades = []
    try:
        # 从数据库查询成交记录
        for row in history_rows(db.query_trades_range, account_id, start_date, end_date):
            trades.append(
                {
                    **history_trade_identity(row),
                    "amount": row.get("amount") or 0,
                    "fee": row.get("fee") or 0,
                }
            )
    except Exception as e:
        print(f"Failed to query trades: {e}")

    def main_block() -> Any:
        return Div(
            Div(H1("历史成交", cls="text-2xl font-bold text-gray-900"), cls="mb-6"),
            Form(
                DateRangePicker(start_date, end_date),
                action="/trade/records/history",
                method="GET",
                cls="mb-6",
            ),
            TradesTable(trades),
            cls="p-6",
        )

    layout.set_main_block(main_block)
    return HTMLResponse(to_xml(layout.render()))
