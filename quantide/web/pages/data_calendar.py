"""交易日历管理页面"""

import calendar as cal_lib
import datetime
from collections.abc import Collection
from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    H3,
    A,
    Button,
    Card,
    Div,
    Form,
    P,
    Span,
    Td,
    Thead,
    Tr,
)
from loguru import logger
from monsterui.all import *
from monsterui.all import (
    H4,
    CardBody,
    Table,
    Tbody,
    Th,
    UkIcon,
)
from starlette.requests import Request

from quantide.data.models.calendar import calendar
from quantide.web.application import fast_app
from quantide.web.components.dataset_pages import DatasetPage, DatasetTabs, dataset_content
from quantide.web.theme import AppTheme

# 定义子路由应用
data_calendar_app, rt = fast_app(hdrs=AppTheme.headers())


def _get_active_tab(req: Request) -> str:
    return req.query_params.get("tab", "overview")


def _TabNav(active_tab: str) -> Any:
    return DatasetTabs(
        "/data/calendar",
        active_tab,
        [("overview", "概要"), ("calendar", "日历"), ("update", "手动更新")],
    )


def _OverviewTab() -> Any:
    """概要 Tab 内容"""
    try:
        start_date = calendar.epoch
        end_date = calendar.end
        file_path = str(calendar.path)
    except Exception as e:
        return Div(Card(CardBody(P(f"获取日历信息失败: {e}", cls="text-red-500"))))

    return Div(
        H3("日历概要", cls="text-xl font-semibold mb-6"),
        Div(
            P(Span("开始日期：", cls="font-medium"), str(start_date), cls="mb-3"),
            P(Span("结束日期：", cls="font-medium"), str(end_date), cls="mb-3"),
            P(
                Span("文件位置：", cls="font-medium"),
                file_path,
                cls="text-sm text-gray-600 break-all",
            ),
            cls="space-y-2",
        ),
        cls="animate-in fade-in duration-500",
    )


def _CalendarGrid(year: int, month: int) -> Any:
    """构建单月日历网格"""
    month_days = cal_lib.monthcalendar(year, month)
    month_name = f"{year}年{month}月"

    # 获取该月的所有交易日，用于比对
    start_of_month = datetime.date(year, month, 1)
    if month == 12:
        end_of_month = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        end_of_month = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)

    try:
        trade_dates = set(calendar.get_trade_dates(start_of_month, end_of_month))
    except Exception:
        trade_dates = set()

    headers = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    header_row = Tr(*[Th(h, cls="text-center py-2 bg-gray-50 border") for h in headers])

    rows = []
    rows = [
        Tr(*[_month_day_cell(year, month, day, trade_dates) for day in week]) for week in month_days
    ]

    return Div(
        Div(H4(month_name, cls="text-lg font-bold"), cls="flex justify-between items-center mb-4"),
        Table(Thead(header_row), Tbody(*rows), cls="w-full border-collapse border"),
        cls="mb-8",
    )


def _CalendarTab(req: Request) -> Any:
    """日历可视化 Tab 内容"""
    # 默认显示当前月和下个月
    today = datetime.date.today()
    curr_year, curr_month = today.year, today.month

    # 允许通过 query 参数切换年份/月份
    try:
        year = int(req.query_params.get("year", curr_year))
        month = int(req.query_params.get("month", curr_month))
    except (TypeError, ValueError):
        year, month = curr_year, curr_month

    # 计算上个月和下个月
    prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
    next_year, next_month = (year, month + 1) if month < 12 else (year + 1, 1)

    return Div(
        Div(
            A(
                UkIcon("chevron-left"),
                href=f"/data/calendar?tab=calendar&year={prev_year}&month={prev_month}",
                cls="btn btn-ghost btn-sm",
            ),
            H3(f"{year}年{month}月", cls="text-xl font-semibold mx-4"),
            A(
                UkIcon("chevron-right"),
                href=f"/data/calendar?tab=calendar&year={next_year}&month={next_month}",
                cls="btn btn-ghost btn-sm",
            ),
            cls="flex items-center justify-center mb-6",
        ),
        _CalendarGrid(year, month),
        cls="animate-in slide-in-from-bottom-4 duration-500",
    )


def _UpdateTab() -> Any:
    """手动更新 Tab 内容"""
    return Div(
        H3("手动更新日历", cls="text-xl font-semibold mb-4"),
        P("点击下方按钮从服务器获取最新的交易日历数据并同步到本地。", cls="text-gray-600 mb-6"),
        Form(
            Button(
                Div(UkIcon("refresh-cw", cls="mr-2"), "执行日历更新", cls="flex items-center"),
                type="submit",
                cls="btn btn-primary",
                id="update-btn",
                hx_post="/data/calendar/do-update",
                hx_target="#update-result",
                hx_indicator="#update-spinner",
            ),
            cls="mb-4",
        ),
        Div(
            id="update-spinner",
            cls="htmx-indicator mb-4",
            children=[
                Div(
                    cls="flex items-center text-[#e41815]",
                    children=[UkIcon("loader", cls="animate-spin mr-2"), "正在更新，请稍候..."],
                )
            ],
        ),
        Div(id="update-result"),
        cls="animate-in fade-in duration-500",
    )


@rt("/")
async def index(req: Request) -> Any:
    active_tab = _get_active_tab(req)

    # 根据 Tab 选择内容
    content = dataset_content(
        active_tab, _OverviewTab, _UpdateTab, calendar=lambda: _CalendarTab(req)
    )

    return DatasetPage(
        req,
        "/data/calendar",
        "交易日历",
        "calendar",
        active_tab,
        [("overview", "概要"), ("calendar", "日历"), ("update", "手动更新")],
        content,
    )


@rt("/do-update", methods="post")
async def do_update() -> Any:
    """执行日历更新动作"""
    try:
        import asyncio

        # 在线程池中执行耗时的更新操作
        await asyncio.to_thread(calendar.update)
        return Div(
            UkIcon("check-circle", cls="text-green-500 mr-2"),
            "交易日历更新成功！",
            cls=(
                "flex items-center p-4 bg-green-50 text-green-700 rounded-lg animate-in "
                "zoom-in duration-300"
            ),
        )
    except Exception as e:
        logger.error(f"更新交易日历失败: {e}")
        return Div(
            UkIcon("alert-circle", cls="text-red-500 mr-2"),
            f"更新失败: {str(e)}",
            cls=(
                "flex items-center p-4 bg-red-50 text-red-700 rounded-lg animate-in "
                "shake duration-300"
            ),
        )


def _month_day_cell(year: int, month: int, day: int, trade_dates: Collection[datetime.date]) -> Any:
    """Render a calendar cell from explicit trading-day membership."""
    if day == 0:
        return Td("", cls="bg-gray-50 border h-24")
    else:
        curr_date = datetime.date(year, month, day)
        is_trade = curr_date in trade_dates

        # 样式处理
        content_cls = "flex flex-col h-full p-2"
        date_cls = "text-sm font-semibold"
        status_cls = "text-xs mt-auto self-end"

        if is_trade:
            bg_cls = "bg-white"
            status_text = ""
            status_color = ""
        else:
            bg_cls = "bg-red-50/30"
            status_text = "休市"
            status_color = "text-red-500"

        return Td(
            Div(
                Span(str(day), cls=date_cls),
                Span(status_text, cls=f"{status_cls} {status_color}"),
                cls=content_cls,
            ),
            cls=f"{bg_cls} border h-24 p-0 align-top",
        )
