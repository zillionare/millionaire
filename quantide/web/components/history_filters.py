"""Shared session selection and date range controls for account history."""

import datetime

from fasthtml.common import *
from fasthtml.common import (
    Div,
    Span,
)
from monsterui.all import *
from monsterui.all import (
    Button,
    Input,
)


def _get_active_account(req) -> tuple[str, str] | None:
    """获取当前活动账户"""
    session = req.scope.get("session", {})
    kind = session.get("active_account_kind")
    account_id = session.get("active_account_id")
    if kind and account_id:
        return kind, account_id
    return None


def DateRangePicker(start_date: str = "", end_date: str = ""):
    """日期范围选择器"""
    today = datetime.date.today().isoformat()
    if not start_date:
        start_date = today
    if not end_date:
        end_date = today

    return Div(
        Div(
            Span("开始日期", cls="text-sm text-gray-600 mr-2"),
            Input(
                type="date",
                name="start_date",
                value=start_date,
                cls="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500",
            ),
            cls="flex items-center",
        ),
        Div(
            Span("结束日期", cls="text-sm text-gray-600 mr-2"),
            Input(
                type="date",
                name="end_date",
                value=end_date,
                cls="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500",
            ),
            cls="flex items-center ml-4",
        ),
        Button(
            "查询",
            type="submit",
            cls="ml-4 px-4 py-2 bg-[#e41815] text-white rounded-lg hover:bg-[#c91412]",
        ),
        cls="flex items-center mb-6",
    )


def UnselectedHistory(layout):
    """Render the common empty state before an account has been selected."""
    from starlette.responses import HTMLResponse

    layout.main_block = lambda: Div(
        P("请先选择活动账户", cls="text-gray-500 text-center py-8"), cls="p-6"
    )
    return HTMLResponse(to_xml(layout.render()))


def HistoryTableHeader(labels, left_columns=4):
    """Render account-history columns with consistent alignment."""
    return Thead(
        Tr(
            *[
                Th(
                    label,
                    cls="pb-3 font-medium " + ("text-left" if i < left_columns else "text-right"),
                )
                for i, label in enumerate(labels)
            ],
            cls="text-sm text-gray-600 border-b",
        )
    )


def EmptyHistory(message):
    return Div(P(message, cls="text-gray-500 text-center py-8"), cls="bg-white rounded-lg shadow")
