"""系统维护 - 行情数据模块"""

import asyncio
import datetime

from fasthtml.common import *
from fasthtml.common import (
    A,
    Div,
    P,
    Span,
    Tr,
)

# Use FastHTML's plain Label for form elements to avoid MonsterUI's uk-label styling
from fasthtml.common import Label as _Label
from loguru import logger
from monsterui.all import *
from monsterui.all import (
    H2,
    Button,
    Form,
    Input,
    Td,
    UkIcon,
)

from quantide.data.models.daily_bars import daily_bars
from quantide.data.models.stocks import stock_list
from quantide.web.application import fast_app
from quantide.web.components.data_tables import DatasetPagination, DatasetTable
from quantide.web.layouts.main import MainLayout
from quantide.web.theme import PRIMARY_COLOR, AppTheme

# 定义子路由应用
system_market_app, rt = fast_app(hdrs=AppTheme.headers())


def _get_market_data(
    code: str = "",
    start_date: str = "",
    end_date: str = "",
    adjust: str = "none",
    page: int = 1,
    per_page: int = 20,
):
    """获取行情数据"""
    try:
        if not code and not start_date and not end_date:
            df = daily_bars.get_bars(
                1,
                end=datetime.datetime.now(),
                assets=None,
                adjust=None,
                eager_mode=True,
            )
            if df is None or len(df) == 0:
                return [], 0

            data = df.sort("asset").to_pandas().to_dict("records")
            total = len(data)
            start_idx = (page - 1) * per_page
            end_idx = min(start_idx + per_page, total)
            return data[start_idx:end_idx], total

        if not start_date:
            start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime(
                "%Y-%m-%d"
            )
        if not end_date:
            end_date = datetime.datetime.now().strftime("%Y-%m-%d")

        start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()

        if not code:
            return [], 0

        df = daily_bars.get_bars_in_range(
            start=start_dt,
            end=end_dt,
            assets=[code],
            adjust=adjust if adjust != "none" else None,
            eager_mode=True,
        )

        if df is None or len(df) == 0:
            return [], 0

        data = df.to_pandas().to_dict("records")
        total = len(data)

        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, total)
        page_data = data[start_idx:end_idx]

        return page_data, total

    except Exception as e:
        logger.error(f"获取行情数据失败: {e}")
        return [], 0


def _load_asset_names() -> dict[str, str]:
    """加载证券代码到名称的映射。"""
    try:
        data = stock_list.data
        if data is None or len(data) == 0:
            return {}
        if "asset" not in data.columns or "name" not in data.columns:
            return {}
        return dict(zip(data["asset"].to_list(), data["name"].to_list(), strict=True))
    except Exception as e:
        logger.debug(f"加载证券名称失败: {e}")
        return {}


def _market_row(row, show_identity, asset_names):
    """Render one row with its display values and available actions."""
    trade_date = str(row.get("date", "")).split(" ")[0] if row.get("date") else "-"
    is_st = "是" if row.get("is_st") else "否"

    pre_close = row.get("pre_close", row.get("open", 0))
    cur_close = row.get("close", 0)
    if pre_close and cur_close and pre_close != 0:
        change = cur_close - pre_close
        change_pct = (change / pre_close) * 100
        change_cls = (
            "text-red-500" if change > 0 else ("text-green-500" if change < 0 else "text-gray-500")
        )
        change_str = f"{change_pct:+.2f}%"
    else:
        change_cls = "text-gray-500"
        change_str = "-"

    cells = []
    if show_identity:
        asset = str(row.get("asset") or "-")
        cells.extend(
            [
                Td(asset, cls="px-4 py-2 text-sm font-medium text-gray-900"),
                Td(asset_names.get(asset, "-"), cls="px-4 py-2 text-sm text-gray-900"),
            ]
        )
    cells.extend(
        [
            Td(trade_date, cls="px-4 py-2 text-sm text-gray-900"),
            Td(_market_number(row, "open", ".2f"), cls="px-4 py-2 text-sm text-gray-900"),
            Td(_market_number(row, "high", ".2f"), cls="px-4 py-2 text-sm text-gray-900"),
            Td(_market_number(row, "low", ".2f"), cls="px-4 py-2 text-sm text-gray-900"),
            Td(_market_number(row, "close", ".2f"), cls="px-4 py-2 text-sm text-gray-900"),
            Td(Span(change_str, cls=change_cls), cls="px-4 py-2 text-sm"),
            Td(_market_number(row, "volume", ",.0f"), cls="px-4 py-2 text-sm text-gray-500"),
            Td(_market_number(row, "amount", ",.2f"), cls="px-4 py-2 text-sm text-gray-500"),
            Td(_market_number(row, "up_limit", ".2f"), cls="px-4 py-2 text-sm text-gray-500"),
            Td(_market_number(row, "down_limit", ".2f"), cls="px-4 py-2 text-sm text-gray-500"),
            Td(_market_number(row, "adjust", ".4f"), cls="px-4 py-2 text-sm text-gray-500"),
            Td(is_st, cls="px-4 py-2 text-sm text-gray-500"),
        ]
    )
    return Tr(*cells, cls="hover:bg-gray-50")


def _build_market_table(
    data: list,
    page: int = 1,
    per_page: int = 20,
    total: int = 0,
    code: str = "",
    start_date: str = "",
    end_date: str = "",
    adjust: str = "none",
):
    """构建行情数据表格"""
    show_identity = not str(code or "").strip()
    asset_names = _load_asset_names() if show_identity else {}

    rows = []
    if data:
        rows.extend(_market_row(row, show_identity, asset_names) for row in data)
    else:
        rows.append(
            Tr(
                Td(
                    "暂无数据",
                    colspan="14" if show_identity else "12",
                    cls="px-4 py-8 text-center text-gray-500",
                )
            )
        )

    total_pages = max(1, (total + per_page - 1) // per_page) if total > 0 else 1
    pagination_info = (
        f"显示第 {(page - 1) * per_page + 1} 到 {min(page * per_page, total)} 条，共 {total} 条"
        if total > 0
        else "暂无数据"
    )

    def page_url(p):
        return (
            "/system/market/?code="
            f"{code}"
            "&start_date="
            f"{start_date}"
            "&end_date="
            f"{end_date}"
            "&adjust="
            f"{adjust}"
            "&page="
            f"{p}"
            "&per_page="
            f"{per_page}"
        )

    return Div(
        DatasetTable(
            (["证券代码", "证券名称"] if show_identity else [])
            + [
                "日期",
                "开盘",
                "最高",
                "最低",
                "收盘",
                "涨跌",
                "成交量",
                "成交额",
                "涨停价",
                "跌停价",
                "复权因子",
                "ST",
            ],
            rows,
        ),
        DatasetPagination(
            pagination_info,
            page,
            per_page,
            total_pages,
            lambda number, size: page_url(number).replace(
                f"per_page={per_page}", f"per_page={size}"
            ),
            lambda active: (
                "q-btn q-btn--sm mx-0.5"
                + (" border-gray-900 bg-gray-900 text-white" if active else "")
            ),
        ),
        cls="bg-white rounded-lg shadow overflow-hidden",
    )


@rt("/")
async def index(
    req,
    code: str = "",
    start_date: str = "",
    end_date: str = "",
    adjust: str = "none",
    page: int = 1,
    per_page: int = 20,
):
    """行情数据页面"""
    code = code or req.query_params.get("code", "")
    start_date = start_date or req.query_params.get("start_date", "")
    end_date = end_date or req.query_params.get("end_date", "")
    adjust = adjust or req.query_params.get("adjust", "none")
    page = int(req.query_params.get("page", page))
    per_page = int(req.query_params.get("per_page", per_page))

    logger.info(
        f"market_page called with code='{code}', start_date='{start_date}', end_date='{end_date}'"
    )

    data, total = _get_market_data(code, start_date, end_date, adjust, page, per_page)

    layout = MainLayout(title="行情数据")
    layout.set_sidebar_active("/system/market")

    def adjust_btn(label: str, value: str) -> A:
        url = (
            "/system/market/?code="
            f"{code}"
            "&start_date="
            f"{start_date}"
            "&end_date="
            f"{end_date}"
            "&adjust="
            f"{value}"
            "&page=1&per_page="
            f"{per_page}"
        )
        active_cls = " border-gray-900 bg-gray-900 text-white" if adjust == value else ""
        return A(label, href=url, cls=f"q-btn q-btn--sm whitespace-nowrap{active_cls}")

    page_content = Div(
        Div(
            Div(
                UkIcon("bar-chart-2", size=32, cls="mr-3", style=f"color: {PRIMARY_COLOR};"),
                H2("行情数据", cls="text-2xl font-bold"),
                cls="flex items-center",
            ),
            cls="mb-6",
        ),
        Div(
            Form(
                Div(
                    Div(
                        _Label("证券代码", cls="q-label"),
                        Input(
                            type="text",
                            name="code",
                            value=code,
                            placeholder="输入股票代码",
                            cls="q-input w-full",
                        ),
                        cls="min-w-0",
                    ),
                    Div(
                        _Label("起始日期", cls="q-label"),
                        Input(
                            type="date", name="start_date", value=start_date, cls="q-input w-full"
                        ),
                        cls="min-w-0",
                    ),
                    Div(
                        _Label("结束日期", cls="q-label"),
                        Input(type="date", name="end_date", value=end_date, cls="q-input w-full"),
                        cls="min-w-0",
                    ),
                    Div(
                        Button("查询", type="submit", cls="q-btn min-w-[72px] whitespace-nowrap"),
                        cls="flex items-end",
                    ),
                    cls=(
                        "grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1f"
                        "r)_minmax(0,1fr)_auto]"
                    ),
                ),
                cls="card p-4 mb-3",
            ),
            cls="mb-4",
        ),
        P(
            "未提供筛选条件时，默认展示最近一个交易日的首页数据。",
            cls="text-sm text-gray-500 mb-4",
        ),
        Div(
            Div(
                Span("复权方式", cls="whitespace-nowrap text-sm font-medium text-gray-700"),
                Div(
                    adjust_btn("不复权", "none"),
                    adjust_btn("前复权", "qfq"),
                    cls="flex flex-wrap items-center gap-1.5",
                ),
                cls="flex min-w-0 flex-wrap items-center gap-2",
            ),
            Button(
                "立即刷新",
                hx_post="/system/market/sync",
                hx_target="#market-content",
                hx_swap="innerHTML",
                cls="q-btn q-btn--sm shrink-0 whitespace-nowrap",
            ),
            cls="card mb-4 flex flex-wrap items-center justify-between gap-3 p-3",
        ),
        Div(
            _build_market_table(data, page, per_page, total, code, start_date, end_date, adjust),
            id="market-content",
        ),
        cls="p-8",
    )

    layout.main_block = page_content
    return layout.render(req)


@rt("/sync", methods="post")
async def sync_market(req):
    """同步行情数据"""
    try:
        await asyncio.to_thread(daily_bars.store.update)
        logger.info("行情数据同步完成")
        try:
            from quantide.service.data_readiness import data_readiness_monitor

            if datetime.datetime.now().time() >= datetime.time(18, 30):
                data_readiness_monitor.check_end_of_day()
            else:
                data_readiness_monitor.check_morning()
        except Exception:
            pass

        code = req.query_params.get("code", "")
        start_date = req.query_params.get("start_date", "")
        end_date = req.query_params.get("end_date", "")
        adjust = req.query_params.get("adjust", "none")

        data, total = _get_market_data(code, start_date, end_date, adjust, 1, 20)
        return _build_market_table(data, 1, 20, total, code, start_date, end_date, adjust)
    except Exception as e:
        logger.error(f"同步行情数据失败: {e}")
        return Div(
            UkIcon("alert-circle", cls="text-red-500 mr-2"),
            f"同步失败: {str(e)}",
            cls="flex items-center p-4 bg-red-50 text-red-700 rounded-lg",
        )


def _market_number(row, key, spec):
    value = row.get(key)
    return format(value, spec) if value is not None else "-"
