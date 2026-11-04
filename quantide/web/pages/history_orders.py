"""历史委托页面"""

from fasthtml.common import *
from fasthtml.common import (
    Div,
    Tr,
)
from monsterui.all import *
from monsterui.all import (
    Table,
    Tbody,
    Td,
)
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
    status_label,
)
from quantide.web.semantic_styles import trade_side_text


def OrdersTable(orders: list[dict]):
    """委托表格"""
    if not orders:
        return EmptyHistory("暂无委托数据")

    status_colors = {
        "已报": "text-gray-600",
        "已成": "text-green-600",
        "已撤": "text-gray-500",
        "部成": "text-gray-600",
        "废单": "text-red-600",
    }

    return Div(
        Table(
            HistoryTableHeader(
                ["时间", "代码", "名称", "方向", "委托价", "委托量", "已成量", "状态"]
            ),
            Tbody(
                *[
                    Tr(
                        Td(order.get("tm", ""), cls="py-3 text-sm"),
                        Td(order.get("asset", ""), cls="py-3 text-sm font-medium"),
                        Td(order.get("name", ""), cls="py-3 text-sm text-gray-500"),
                        Td(
                            order.get("side", ""),
                            cls=(f"py-3 text-sm {trade_side_text(order.get('side'))}"),
                        ),
                        Td(f"{order.get('price', 0):.2f}", cls="py-3 text-sm text-right"),
                        Td(f"{order.get('shares', 0):,}", cls="py-3 text-sm text-right"),
                        Td(f"{order.get('filled', 0):,}", cls="py-3 text-sm text-right"),
                        Td(
                            order.get("status", ""),
                            cls=(
                                "py-3 text-sm text-center "
                                f"{status_colors.get(order.get('status'), 'text-gray-600')}"
                            ),
                        ),
                    )
                    for order in orders
                ],
                cls="text-sm",
            ),
            cls="w-full",
        ),
        cls="bg-white rounded-lg shadow overflow-hidden",
    )


def history_orders_list(request):
    """历史委托列表页面"""
    session = request.scope.get("session", {})
    layout = MainLayout(title="历史委托", user=session.get("auth"))
    layout.header_active = "交易"
    layout.set_sidebar_active("/trade/orders/history")

    active = _get_active_account(request)
    if not active:
        return UnselectedHistory(layout)

    kind, account_id = active

    start_date, end_date = history_date_range(request.query_params)

    orders = []
    try:
        for row in history_rows(db.query_orders_range, account_id, start_date, end_date):
            orders.append(
                {
                    **history_trade_identity(row),
                    "filled": row.get("filled") or 0,
                    "status": status_label(row.get("status")),
                }
            )
    except Exception as e:
        print(f"Failed to query orders: {e}")

    def main_block():
        return Div(
            Div(H1("历史委托", cls="text-2xl font-bold text-gray-900"), cls="mb-6"),
            Form(
                DateRangePicker(start_date, end_date),
                action="/trade/orders/history",
                method="GET",
                cls="mb-6",
            ),
            OrdersTable(orders),
            cls="p-6",
        )

    layout.main_block = main_block
    return HTMLResponse(to_xml(layout.render()))
